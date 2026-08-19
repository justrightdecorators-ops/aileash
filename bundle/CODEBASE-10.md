# Codebase — part 10 of 22

Contains:
- `modules/spec.py`
- `modules/standard.py`
- `modules/stats.py`
- `modules/verifier.py`
- `modules/warmup.py`
- `modules/witness.py`


## `modules/spec.py`

121 lines, 5086 bytes

```python
"""
Live API specification - /x/spec

/api/spec is a hardcoded constant. It describes the API as it was when
somebody last remembered to update it, which is a documentation problem
pretending to be a feature.

This discovers what is actually loaded, right now, by reading the modules
directory and each module's own docstring. Add a module and the spec
updates itself. Delete one and it disappears. There is no separate list to
maintain and therefore no list that can drift.

That matters here more than it would elsewhere: a platform whose pitch is
"check it, don't trust it" should not ship a self-description that is
quietly out of date.

    GET /x/spec           everything currently live
    GET /x/spec/modules   just the module list
"""

import importlib, os, pkgutil, re

VERSION = "1.0"

_EP = re.compile(r"^\s*(GET|POST|PUT|DELETE)\s+(/\S+)\s*(.*)$")


def _describe(name):
    """Pull a module's summary and endpoint list out of its own docstring."""
    try:
        m = importlib.import_module("modules." + name)
    except Exception as e:
        return {"module": name, "loaded": False, "error": str(e)}
    doc = (m.__doc__ or "").strip()
    lines = doc.splitlines()
    summary = ""
    for ln in lines:
        t = ln.strip()
        if t and not t.startswith("-") and not _EP.match(ln):
            summary = t
            break
    endpoints = []
    for ln in lines:
        mm = _EP.match(ln)
        if mm:
            endpoints.append({"method": mm.group(1),
                              "path": mm.group(2),
                              "takes": mm.group(3).strip() or None})
    out = {"module": name, "loaded": True, "summary": summary,
           "endpoints": endpoints,
           "version": getattr(m, "VERSION", None)}
    if not hasattr(m, "handle"):
        out["warning"] = "module has no handle() - it will not route"
    return out


def _modules():
    d = os.path.dirname(__file__)
    names = sorted(x.name for x in pkgutil.iter_modules([d])
                   if x.name not in ("router", "spec"))
    return [_describe(n) for n in names]


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404

    mods = _modules()

    if action == "modules":
        return {"count": len(mods), "modules": mods}, 200

    if action in ("", "all"):
        return {
            "spec_version": VERSION,
            "generated": "live - discovered at request time, not a stored list",
            "core": {
                "decision_engine": {
                    "path": "/api/govern",
                    "method": "POST",
                    "auth": "Bearer key",
                    "note": "deterministic scoring, verdict sealed before the response returns"
                },
                "notaries_public": [
                    {"method": "POST", "path": "/api/post/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/verify-post", "auth": "none"},
                    {"method": "POST", "path": "/api/identity/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/identity/check", "auth": "none"},
                    {"method": "POST", "path": "/api/payment/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/payment/check", "auth": "none"}
                ],
                "verification_public": [
                    {"method": "GET", "path": "/api/verify-chain",
                     "returns": "whole-chain integrity, recomputed"},
                    {"method": "GET", "path": "/api/inclusion",
                     "returns": "whether a given 64-char hash is sealed"},
                    {"method": "GET", "path": "/api/anchor-status",
                     "returns": "current tip, OpenTimestamps proof, calendar count"},
                    {"method": "GET", "path": "/api/regulation-map",
                     "returns": "engine features mapped to legal obligations"}
                ]
            },
            "modules": {
                "prefix": "/x/<module>/<action>",
                "auth": "Bearer key on every module route",
                "count": len(mods),
                "loaded": mods
            },
            "chain": {
                "algorithm": "SHA-256 hash chain",
                "scope": "one chain - every module seals into the same sequence as /api/govern",
                "anchoring": "chain tip submitted to OpenTimestamps, aggregated into a Merkle root, root committed to Bitcoin by several independent calendars",
                "receipts": "gapless per-key sequence issued in the same transaction as the chain write",
                "verify": "/api/verify-chain and /api/anchor-status, both without a key"
            },
            "honest_note": "This spec is generated by reading the modules directory at request time rather than from a stored list, so it cannot describe capabilities that are not actually loaded."
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["", "modules"]}, 404

```


## `modules/standard.py`

422 lines, 19423 bytes

```python
"""
modules/standard.py  -  the Ordering Test discovery document for this domain

WHAT IT SERVES
--------------
  GET /.well-known/ordering-test.json   this operator's discovery document
  GET /x/standard/hash                  sha256 of that document
  GET /x/standard/status                what is installed, and honest counts

SHAPE
-----
Deliberately identical to the shape Red Flag AI Pro published first:

    checks: { <name>: { supported, demonstrable_publicly, endpoint, note } }

Two fields, not one, and the second is the better idea. "We built it" and
"you can verify it without an account" are different claims, and most of this
market blurs them. Separating them lets a vendor be honest about having
something real that an outsider still has to take on trust.

WHAT THE HOST HEADER IS DOING HERE
----------------------------------
base_url is derived from the request rather than written into the file. An
earlier draft had the domain hardcoded, which meant any operator running it
would publish somebody else's domain as the source - the opposite of a mirror.
Deriving it means this file can be lifted to any domain and tells the truth
about wherever it is actually running.

EVERY PUBLISHED ENDPOINT MUST WORK AS WRITTEN
---------------------------------------------
An endpoint marked demonstrable_publicly is a promise that a stranger can copy
it out of this document and get an answer. If the route needs a parameter, the
document names that parameter. If a value has to be discovered first, the
document says where to discover it. An endpoint that errors when followed
literally is a failed check, not a documentation detail.

HONESTY RULES THIS FILE FOLLOWS
-------------------------------
  - A check we have not built says supported: false. It does not quietly go
    missing from the document.
  - A check that exists but needs an account says demonstrable_publicly:
    false, however much we would like the tick.
  - runner is null. A runner exists in draft, but the checks have not been
    jointly agreed with the other mirror, so publishing one as though it were
    a settled standard would claim something neither operator has earned yet.

None of that is modesty. A conformance document whose author scores full marks
on the day they publish it is a marketing page.
"""

import hashlib
import json
import sys

VERSION = "1.2"
ORDERING_TEST_VERSION = "0.1"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec"),
          ("GET", "document")}

# Several paths on purpose. /.well-known/ is where the standard says to look,
# but some platforms and static handlers reserve that prefix, so a plain root
# path is served as well. /x/standard/document goes through the normal router
# and cannot be intercepted by anything, which makes it the diagnostic.
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",
                   "/ordering-test.json",
                   "/well-known/ordering-test.json")

VENDOR = "AILeash"
FALLBACK_BASE = "https://sebbi.pro"

RUNNER = None
RUNNER_NOTE = (
    "No shared runner file is published here yet. The checks themselves have "
    "not been jointly agreed with the other mirrors as of this document's "
    "publication. This describes AILeash's own side only, not a settled "
    "cross-vendor standard.")

# Order follows the other mirror's document so the two read side by side.
CHECKS = {
    "rule_binding": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/rulebind/prove",
        "note": ("The ruleset version is a component of a digest sealed with the "
                 "decision, not a field beside it. POST any inputs without an "
                 "account and the response returns the exact string that was "
                 "hashed - SHA-256 it yourself and confirm it matches. Alter the "
                 "ruleset hash and the digest stops recomputing; alter the digest "
                 "and the chain breaks. Verify a past record at "
                 "/x/rulebind/verify?receipt=... and see ruleset history at "
                 "/x/rulebind/packs. No scoring logic is disclosed at any point - "
                 "inputs are published as a digest, never as values."),
    },
    "commit_before_reveal": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/demo/review",
        "note": ("The reviewer receives the case with the machine verdict "
                 "withheld. Their own call and dwell time are sealed first, "
                 "then the verdict is revealed, and the chain fixes that order "
                 "permanently. No account needed - open a case, commit a "
                 "verdict, and check the block indices yourself. Commit "
                 "endpoint is /x/demo/commit."),
    },
    "authority_tokens": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/continuity/decisions",
        "note": ("Authority is derived, not looked up. Every grant points at a "
                 "parent and terminates at a human principal; scope, limits, "
                 "purpose and validity must narrow at every hop; and the whole "
                 "chain is re-derived at the instant of execution rather than "
                 "trusted from the instant of issue. A decision beyond delegated "
                 "authority escalates rather than executes. Issuing and exercising "
                 "authority are keyed, but the record is not: /x/continuity/decisions "
                 "lists real sealed evaluations without an account, and any id from "
                 "it opens at /x/continuity/decision and /x/continuity/trace, which "
                 "returns the full authority path with the grant and invariant that "
                 "broke. Blocks are listed alongside allows, because a refusal with "
                 "no public record is indistinguishable from never having been asked. "
                 "An empty list means no authority has been exercised yet, not that "
                 "none failed. Derivation rules at /x/continuity/spec."),
    },
    "mutual_witnessing": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/witness/peers",
        "note": ("Live, running both directions with an external peer chain "
                 "hourly since 1 August 2026. No account needed, run it "
                 "yourself. Our current tip is at /x/witness/tip and any party "
                 "can submit theirs at /x/witness/observe without an account."),
    },
    "completeness_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/root?period={period}&kind=receipts",
        "note": ("Per-period sorted Merkle root and exact leaf count, committed "
                 "before any export is requested. An export can then be checked "
                 "against a number fixed before anyone knew it would be asked "
                 "for. Committed periods are listed at /x/complete/periods - "
                 "take a period identifier from there and substitute it. Only "
                 "closed periods can be committed, so the current period will "
                 "not appear until it ends. A period listed nowhere is a period "
                 "nobody committed, which is itself the finding."),
    },
    "absence_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/prove?period={period}&value={value}",
        "note": ("Two adjacent leaves with consecutive indices demonstrate that "
                 "nothing sits between them, so absence is proved rather than "
                 "asserted. Both parameters are required: take a period from "
                 "/x/complete/periods and supply any value you like. Try a "
                 "value that is not there."),
    },
    "reconciliation": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/reconcile/public",
        "note": ("The sample is derived from the chain tip and sealed BEFORE any "
                 "data is requested, so the operator cannot choose which records "
                 "get examined or prepare only the flattering ones. Planning and "
                 "submitting are keyed because they touch an operator's own "
                 "records, but the part that decides whether any of it means "
                 "anything is not: /x/reconcile/public gives run counts, match "
                 "rates and mismatches without an account, and "
                 "/x/reconcile/proof?id=RUN-XXXXXXXX shows the two sealed block "
                 "indices so anyone can confirm the selection block precedes the "
                 "result block. Abandoned runs are published too - a plan is "
                 "sealed when it is planned, so a test that came back badly and "
                 "was dropped stays visible forever as a plan with no result. "
                 "What this does not prove: that the records are true. Two "
                 "systems the operator controls agreeing with each other is "
                 "consistency, not truth."),
    },
    "reproducibility": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/replay/challenge",
        "note": ("Determinism proved by public challenge without disclosing any "
                 "scoring logic. Submit inputs, the run is sealed, resubmit the "
                 "same inputs later and the verdict must be identical under an "
                 "unchanged code fingerprint at /x/replay/fingerprint."),
    },
    "consistency_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/consistency/proof?first={first}&second={second}",
        "note": ("RFC 6962 consistency proofs, deliberately unmodified so "
                 "existing Certificate Transparency verifiers work against them "
                 "directly. first and second are tree sizes - read the current "
                 "size from /x/consistency/root and pick any earlier one. "
                 "Anyone holding any earlier tip we served can show it is a "
                 "prefix of the current log at /x/consistency/ancestor."),
    },

    # ---- proposed addition, flagged as a proposal rather than assumed ----
    "external_anchoring": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/api/anchor-status",
        "note": ("PROPOSED AS A SEPARATE CHECK, not settled. The other mirror "
                 "currently folds anchoring into consistency_proof, but they "
                 "answer different questions: consistency shows the log only "
                 "ever grew, anchoring shows the time was fixed somewhere the "
                 "operator cannot reach. A log can be perfectly append-only and "
                 "still have been built last week. Here the tip is submitted to "
                 "OpenTimestamps and committed into Bitcoin; the other mirror "
                 "uses an RFC 3161 timestamp. The spec should permit any "
                 "external authority the operator does not control and require "
                 "it to be named - not mandate one. Offered for the joint "
                 "session."),
    },
}

DOCUMENT_NOTE = (
    "Every endpoint marked demonstrable_publicly is unauthenticated by design - "
    "run it yourself without asking us. Where an endpoint carries a {parameter}, "
    "the note for that check says where to get a valid value; every published "
    "endpoint is meant to work when followed literally, and one that does not is "
    "a failed check on our side, not a quibble. Checks marked supported but not "
    "demonstrable_publicly are real and built, but currently need a key to see, "
    "and say so plainly rather than passing on the day this was published. "
    "Nothing here proves the records are true. It describes the order things "
    "were committed in, which is a narrower claim and the only one that holds.")

_patched = [False]


def _base_from(handler):
    """Derive our own base URL from the request. An operator running this file
    on their own domain publishes their domain, not whoever wrote it."""
    try:
        host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host")
        if not host:
            return FALLBACK_BASE
        host = host.split(",")[0].strip()[:200]
        proto = (handler.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return proto + "://" + host
    except Exception:
        return FALLBACK_BASE


def _base_from_ctx(ctx):
    """Same derivation for the routed /x/standard/document call.

    The router's ctx may or may not carry the request handler. If it does, the
    document served through the router names the same domain as the one served
    at /.well-known/ - which matters on a mirror, where hardcoding would make
    this file publish somebody else's domain again."""
    try:
        if isinstance(ctx, dict):
            for key in ("handler", "h", "request", "req", "self"):
                obj = ctx.get(key)
                if obj is not None and hasattr(obj, "headers"):
                    return _base_from(obj)
            headers = ctx.get("headers")
            if headers is not None:
                class _Shim(object):
                    pass
                shim = _Shim()
                shim.headers = headers
                return _base_from(shim)
        elif ctx is not None and hasattr(ctx, "headers"):
            return _base_from(ctx)
    except Exception:
        pass
    return FALLBACK_BASE


def _document(base):
    checks = {}
    for name, c in CHECKS.items():
        checks[name] = {
            "supported": c["supported"],
            "demonstrable_publicly": c["demonstrable_publicly"],
            "endpoint": c["endpoint"],
            "note": c["note"],
        }
    return {
        "ordering_test_version": ORDERING_TEST_VERSION,
        "vendor": VENDOR,
        "base_url": base,
        "runner": RUNNER,
        "runner_note": RUNNER_NOTE,
        "checks": checks,
        "witness_peers": base + "/x/witness/peers",
        "witness_tip": base + "/x/witness/tip",
        "committed_periods": base + "/x/complete/periods",
        "note": DOCUMENT_NOTE,
    }


def _digest(doc):
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in DISCOVERY_PATHS:
            body = json.dumps(_document(_base_from(self)), indent=2).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /.well-known/ordering-test.json installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    base = _base_from_ctx(ctx)
    doc = _document(base)

    if method == "GET" and action == "document":
        return doc, 200

    if method == "GET" and action == "hash":
        canonical = _document(FALLBACK_BASE)
        return {
            "sha256": _digest(canonical),
            "of": "this operator's discovery document",
            "canonicalisation": ("JSON, keys sorted, no whitespace, UTF-8, "
                                 "base_url fixed to " + FALLBACK_BASE +
                                 " so the digest does not move with the "
                                 "requesting host"),
            "what_this_is_for": (
                "Confirming our own document has not changed. It is NOT the "
                "cross-mirror check - two operators publish different documents "
                "by design, because they list different endpoints, so their "
                "digests should differ and a mismatch would prove nothing. The "
                "cross-mirror comparison only means something once every mirror "
                "serves a byte-identical runner file and hashes that instead. "
                "No runner is agreed yet."),
            "document": canonical,
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        supported = [k for k, c in CHECKS.items() if c["supported"]]
        public = [k for k, c in CHECKS.items() if c["demonstrable_publicly"]]
        parameterised = [k for k, c in CHECKS.items()
                         if c["endpoint"] and "{" in c["endpoint"]]
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "ordering_test_version": ORDERING_TEST_VERSION,
            "serving": list(DISCOVERY_PATHS),
            "always_available": "/x/standard/document",
            "checks_total": len(CHECKS),
            "checks_supported": len(supported),
            "checks_publicly_demonstrable": len(public),
            "publicly_demonstrable": public,
            "supported_but_not_public": [k for k in supported if k not in public],
            "endpoints_needing_a_parameter": parameterised,
            "runner": RUNNER,
            "note": ("base_url is derived from the Host header, so this file "
                     "publishes whichever domain is actually serving it. Checks "
                     "listed under endpoints_needing_a_parameter cannot be "
                     "demonstrated until a real value exists to substitute - "
                     "for the completeness and absence checks that means at "
                     "least one committed period at /x/complete/periods."),
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash", "document"]}, 404

```


## `modules/stats.py`

143 lines, 5540 bytes

```python
"""
Live figures for the Proving Ground - /x/stats

Charts on a compliance site are usually decoration. These are not, provided
they show something a visitor could otherwise only take on trust: that the
chain is genuinely growing, that decisions really are distributed across the
thresholds rather than hand-picked, and that people who click through a
review case behave exactly as the oversight argument predicts.

WHAT IS PUBLISHED, AND WHAT IS NOT
----------------------------------
Public and no key, because a figure nobody can see proves nothing.

Published: total chain height, hourly block counts, the verdict mix and score
distribution of PUBLIC DEMO decisions only, and dwell times from public review
cases.

Never published: anything scoped to a customer key. No customer verdict mix,
no customer volumes, no per-key anything. A visitor learns how the engine
behaves, not how any operator's business is going. That distinction is the
whole reason this endpoint can be open.

    GET /x/stats        everything below
    GET /x/stats/chain  chain height and hourly growth only
"""

import json, time
from datetime import datetime, timezone

VERSION = "1.0"
PUBLIC = {("GET", ""), ("GET", "stats"), ("GET", "chain")}

DEMO_KEY = "public_demo"


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _chain(ctx):
    t = time.time()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*),MIN(ts),MAX(ts) FROM audit_log").fetchone()
        recent = ctx["conn"].execute("SELECT ts FROM audit_log WHERE ts>? ORDER BY ts ASC", (t - 86400,)).fetchall()
    height = row[0] if row else 0
    buckets = [0] * 24
    for (ts,) in recent:
        h = int((t - ts) // 3600)
        if 0 <= h < 24:
            buckets[23 - h] += 1
    return {"height": height,
            "first_block": _iso(row[1] if row else None),
            "latest_block": _iso(row[2] if row else None),
            "last_24h": buckets,
            "blocks_last_24h": sum(buckets),
            "note": "Every block, from every source. The chain is one sequence."}


def _demo(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT result_json,ts FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (DEMO_KEY,)).fetchall()
    verdicts = {"ALLOW": 0, "CHALLENGE": 0, "BLOCK": 0}
    # ten buckets of 0.1 across the score range
    hist = [0] * 10
    scores = []
    for res, _ts in rows:
        try:
            r = json.loads(res)
        except Exception:
            continue
        d = r.get("decision")
        if d in verdicts:
            verdicts[d] += 1
            s = r.get("score")
            if isinstance(s, (int, float)):
                scores.append(s)
                b = min(int(float(s) * 10), 9)
                hist[b] += 1
    total = sum(verdicts.values())
    out = {"decisions": total, "verdicts": verdicts,
           "score_histogram": hist,
           "buckets": ["0.0-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5",
                       "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"],
           "thresholds": {"allow_below": 0.35, "block_at_or_above": 0.70}}
    if scores:
        scores.sort()
        out["median_score"] = round(scores[len(scores) // 2], 4)
    return out


def _oversight(ctx):
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT dwell,human_verdict,machine_verdict FROM demo_cases WHERE committed IS NOT NULL").fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"reviews": 0,
                "note": "Nobody has taken a review case yet."}
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    agreed = len([r for r in rows if (r[1] or "").upper() == (r[2] or "").upper()])
    # dwell buckets in seconds
    edges = [2, 5, 10, 20, 45, 90]
    labels = ["under 2s", "2-5s", "5-10s", "10-20s", "20-45s", "45-90s", "over 90s"]
    hist = [0] * 7
    for d in dwells:
        placed = False
        for i, e in enumerate(edges):
            if d < e:
                hist[i] += 1
                placed = True
                break
        if not placed:
            hist[6] += 1
    n = len(dwells)
    return {"reviews": len(rows),
            "agreed_with_engine": agreed,
            "agreement_rate_pct": round(100 * agreed / len(rows), 1),
            "median_dwell_seconds": (dwells[n // 2] if n else None),
            "under_2_seconds": hist[0],
            "under_2_seconds_pct": (round(100 * hist[0] / n, 1) if n else 0),
            "dwell_histogram": hist,
            "dwell_labels": labels,
            "note": "Visitors who committed in under two seconds did not read the case. That is the pattern the oversight record is designed to make visible."}


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404
    if action == "chain":
        return {"stats_version": VERSION, "chain": _chain(ctx)}, 200
    if action in ("", "stats"):
        return {"stats_version": VERSION,
                "generated": _iso(time.time()),
                "chain": _chain(ctx),
                "public_decisions": _demo(ctx),
                "public_reviews": _oversight(ctx),
                "scope": "Public demonstration activity and total chain height only. Nothing scoped to a customer key is published here."}, 200
    return {"error": "unknown_action", "action": action,
            "available": ["GET stats", "GET chain"]}, 404

```


## `modules/verifier.py`

717 lines, 26299 bytes

```python
#!/usr/bin/env python3
"""
modules/verifier.py  -  hand the verifier out at a URL

WHY THIS EXISTS
---------------
A proof that can only be checked by the party who issued it is not a proof.
So the proof bundles at /x/continuity/proof are useless unless somebody can
easily get hold of something that checks them, and telling people to clone a
repository is a gate.

This serves the standalone verifier as a plain file:

    curl -sO https://sebbi.pro/verify-authority.py
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify-authority.py -

The script it hands out has no dependencies and makes no network calls. It
checks the Ed25519 signature, recomputes every digest, re-runs the whole
derivation from the published rules, and reaches its own verdict - then says
so if that verdict disagrees with ours.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not phone home, and this module records nothing about who downloaded
it. A verification tool that reports back to the party being verified is not
a verification tool.

    GET /verify-authority.py   the script
    GET /x/verifier/status     what is installed, and the script's digest
"""

import hashlib
import sys

VERSION = "1.1"

PUBLIC = {("GET", "status")}

# Deliberately NOT "/verify" - that is the sealed-post verification page and
# this module would silently hijack it, handing a visitor a Python download
# where they expected a page. A route grab is a bug even when the code works.
FILE_PATHS = ("/verify-authority.py", "/verify_authority.py")

_patched = [False]


SCRIPT = r'''#!/usr/bin/env python3
"""
verify_authority.py  -  check an AILeash authority proof without AILeash

    python3 verify_authority.py proof.json
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify_authority.py -

WHAT THIS IS FOR
----------------
A proof that can only be checked by the party who issued it is not a proof.
This script takes a bundle and reaches its own conclusion using nothing but
the Python standard library. It does not call the issuing system, it does not
import anything you have to install, and it does not take a single field of
the bundle at face value.

It does four separate things, and each one can fail on its own:

  1. SIGNATURE   Ed25519 over the canonical bundle. Confirms the bundle came
                 from the holder of the named key and has not been edited by
                 anybody since.

  2. INTEGRITY   Recomputes every grant digest, the lineage digest and the
                 parameter digest from the fields in front of it. Confirms
                 the bundle is internally consistent with its own contents.

  3. DERIVATION  Re-runs the authority rules from scratch: root issued by a
                 human, an unbroken parent chain, scope covered at every hop,
                 constraints narrowing on every axis, purpose narrowing,
                 validity windows contained, nothing revoked, and the action
                 itself inside the effective limits of the whole lineage.

  4. AGREEMENT   Compares the verdict this script reached with the verdict the
                 bundle claims. Disagreement is reported as a failure of the
                 issuer, not of this script.

WHAT A PASS MEANS
-----------------
That the authority for this action was derivable, at that time, from that
human grant - or, for a refusal, that it genuinely was not, and that the named
grant and invariant really are where it broke.

WHAT A PASS DOES NOT MEAN
-------------------------
That the root grant should ever have been issued. That the parameters describe
something that really happened. That the risk engine was right. Derivation is
not merit and it is not truth.

The risk half of a composed verdict cannot be re-derived here, because that
needs the issuer's scoring engine. Where the bundle's authority verdict is
BLOCK, the composed verdict stands regardless, because the composition takes
the worse of the two.
"""

import binascii
import hashlib
import json
import sys

GRANT_PREFIX = b"AILEASH-GRANT-v1:"
EVAL_PREFIX = b"AILEASH-AUTHEVAL-v1:"
BUNDLE_PREFIX = b"AILEASH-AUTHORITY-PROOF-v1:"

MAX_DEPTH = 32
RANK = {"ALLOW": 0, "CHALLENGE": 1, "BLOCK": 2}


# ======================================================================
# Ed25519, RFC 8032, standard library only
# ======================================================================

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _h(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_BX = _xrecover(_BY)
_B = (_BX % _Q, _BY % _Q, 1, (_BX * _BY) % _Q)
_IDENT = (0, 1, 1, 0)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    dd = z1 * 2 * z2 % _Q
    e, f, g, hh = b - a, dd - c, dd + c, b + a
    return (e * f % _Q, g * hh % _Q, f * g % _Q, e * hh % _Q)


def _scalarmult(p, e):
    if e == 0:
        return _IDENT
    q = _scalarmult(p, e // 2)
    q = _add(q, q)
    if e & 1:
        q = _add(q, p)
    return q


def _encodepoint(p):
    x, y, z, _t = p
    zi = _inv(z)
    x, y = x * zi % _Q, y * zi % _Q
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _hint(m):
    h = _h(m)
    return sum(2 ** i * _bit(h, i) for i in range(512))


def _isoncurve(p):
    x, y, z, t = p
    return (z % _Q != 0 and x * y % _Q == z * t % _Q
            and (y * y - x * x - z * z - _D * t * t) % _Q == 0)


def _decodepoint(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if x & 1 != _bit(s, 255):
        x = _Q - x
    p = (x, y, 1, (x * y) % _Q)
    if not _isoncurve(p):
        raise ValueError("point off curve")
    return p


def ed25519_verify(sig, msg, pk):
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        rr = _decodepoint(sig[:32])
        a = _decodepoint(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:64], "little")
    if s >= _L:
        return False
    hh = _hint(sig[:32] + pk + msg)
    return _encodepoint(_scalarmult(_B, s)) == _encodepoint(_add(rr, _scalarmult(a, hh)))


# ======================================================================
# the rules, reimplemented from the published spec
# ======================================================================

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(prefix, text):
    return hashlib.sha256(prefix + text.encode("utf-8")).hexdigest()


def grant_digest(g):
    material = {
        "id": g["id"], "parent": g["parent"], "issuer": g["issuer"],
        "issuer_kind": g["issuer_kind"], "subject": g["subject"],
        "subject_kind": g["subject_kind"], "scope": sorted(g["scope"]),
        "constraints": g["constraints"], "purpose": g["purpose"],
        "purpose_tags": sorted(g["purpose_tags"]),
        "not_before": g["not_before"], "not_after": g["not_after"],
        "depth": g["depth"], "delegations_left": g["delegations_left"],
        "created": g["created"], "risk_accepted_by": g.get("risk_accepted_by"),
    }
    return sha(GRANT_PREFIX, canon(material))


def covers(held, wanted):
    if held == wanted or held == "*":
        return True
    if held.endswith(".*"):
        return wanted == held[:-2] or wanted.startswith(held[:-1])
    return False


def wildcard_breadth(scope, capability):
    best = None
    for held in scope:
        if not covers(held, capability):
            continue
        if held == capability:
            return 0
        width = (capability.count(".") + 2 if held == "*"
                 else capability.count(".") - held[:-2].count("."))
        best = width if best is None else min(best, width)
    return best


def direction(key):
    for p in ("max_", "min_", "allowed_", "denied_", "may_"):
        if key.startswith(p):
            return p
    return None


def num(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("not a number")
    return float(v)


def as_set(v):
    if isinstance(v, (list, tuple, set)):
        return set(v)
    return {v}


def narrower(parent_c, child_c):
    for key in sorted(child_c):
        d = direction(key)
        cval = child_c[key]
        if d is None:
            return False, "constraint '%s' has no narrowing rule" % key
        if key not in parent_c:
            return False, "constraint '%s' is not expressed by the parent" % key
        pval = parent_c[key]
        try:
            if d == "max_" and num(cval) > num(pval):
                return False, "%s raised from %s to %s" % (key, pval, cval)
            if d == "min_" and num(cval) < num(pval):
                return False, "%s lowered from %s to %s" % (key, pval, cval)
            if d == "allowed_" and not as_set(cval) <= as_set(pval):
                return False, "%s adds values the parent does not hold" % key
            if d == "denied_" and not as_set(pval) <= as_set(cval):
                return False, "%s drops values the parent denies" % key
            if d == "may_" and bool(cval) and not bool(pval):
                return False, "%s enabled where the parent withholds it" % key
        except (TypeError, ValueError):
            return False, "constraint '%s' is not comparable" % key
    return True, None


def effective(chain):
    eff = {}
    for g in chain:
        for k, v in g["constraints"].items():
            d = direction(k)
            if k not in eff:
                eff[k] = v
                continue
            cur = eff[k]
            try:
                if d == "max_":
                    eff[k] = min(num(cur), num(v))
                elif d == "min_":
                    eff[k] = max(num(cur), num(v))
                elif d == "allowed_":
                    eff[k] = sorted(as_set(cur) & as_set(v))
                elif d == "denied_":
                    eff[k] = sorted(as_set(cur) | as_set(v))
                elif d == "may_":
                    eff[k] = bool(cur) and bool(v)
            except (TypeError, ValueError):
                eff[k] = v
    return eff


def params_against(params, eff):
    hard, unconstrained = [], []
    for key in sorted(params):
        val = params[key]
        checked = False
        for cname, cval in eff.items():
            d = direction(cname)
            if not d or cname[len(d):] != key:
                continue
            checked = True
            try:
                if d == "max_" and num(val) > num(cval):
                    hard.append("%s=%s exceeds %s=%s" % (key, val, cname, cval))
                elif d == "min_" and num(val) < num(cval):
                    hard.append("%s=%s is below %s=%s" % (key, val, cname, cval))
                elif d == "allowed_" and val not in as_set(cval):
                    hard.append("%s=%s is outside %s" % (key, val, cname))
                elif d == "denied_" and val in as_set(cval):
                    hard.append("%s=%s is denied by %s" % (key, val, cname))
                elif d == "may_" and bool(val) and not bool(cval):
                    hard.append("%s requested where %s withholds it" % (key, cname))
            except (TypeError, ValueError):
                hard.append("%s cannot be compared with %s" % (key, cname))
        if not checked:
            unconstrained.append(key)
    return hard, unconstrained


# ======================================================================
# the four checks
# ======================================================================

class Report(object):
    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, ok, name, detail=""):
        self.rows.append((ok, name, detail))
        if not ok:
            self.failed = True

    def note(self, name, detail=""):
        self.rows.append((None, name, detail))

    def render(self):
        out = []
        for ok, name, detail in self.rows:
            mark = "  ok  " if ok else ("FAIL  " if ok is False else "  --  ")
            out.append(mark + name + (("\n        " + detail) if detail else ""))
        return "\n".join(out)


def check_signature(bundle, rep):
    sig_hex = bundle.get("signature")
    pk_hex = (bundle.get("issued_by") or {}).get("public_key")
    if not sig_hex or not pk_hex:
        rep.add(False, "Signature present", "the bundle carries no signature or no key")
        return
    body = dict(bundle)
    body.pop("signature", None)
    body.pop("verify_with", None)
    try:
        sig = binascii.unhexlify(sig_hex)
        pk = binascii.unhexlify(pk_hex)
    except Exception:
        rep.add(False, "Signature is readable hex")
        return
    ok = ed25519_verify(sig, BUNDLE_PREFIX + canon(body).encode("utf-8"), pk)
    rep.add(ok, "Ed25519 signature over the canonical bundle",
            "key " + pk_hex[:16] + "…  Verify this key independently at the issuer's "
            "published address before trusting who signed." if ok else
            "the bundle was altered after signing, or it was not signed by this key")


def check_integrity(bundle, rep):
    lineage = bundle.get("lineage") or []
    bad = []
    for g in lineage:
        try:
            if grant_digest(g) != g.get("digest"):
                bad.append(g.get("id"))
        except Exception:
            bad.append(g.get("id"))
    rep.add(not bad, "Every grant digest recomputes from its own fields",
            "" if not bad else "mismatched: " + ", ".join(str(b) for b in bad))

    claimed = (bundle.get("decision") or {}).get("lineage_digest")
    mine = sha(EVAL_PREFIX, canon([g.get("digest") for g in lineage]))
    rep.add(mine == claimed, "Lineage digest matches the ordered path",
            "" if mine == claimed else "computed " + mine[:20] + "… claimed " + str(claimed)[:20] + "…")

    req = bundle.get("request") or {}
    claimed_p = (bundle.get("decision") or {}).get("params_digest")
    mine_p = sha(EVAL_PREFIX, canon({"action": req.get("action"),
                                     "params": req.get("params") or {}}))
    rep.add(mine_p == claimed_p, "Parameter digest matches the request as stated",
            "" if mine_p == claimed_p else "the parameters shown are not the "
            "parameters that were judged")


def rederive(bundle, rep):
    """Run the published rules from scratch and reach an independent verdict."""
    lineage = bundle.get("lineage") or []
    decision = bundle.get("decision") or {}
    req = bundle.get("request") or {}
    at = decision.get("evaluated_at_epoch")

    hard, soft = [], []
    broken_at = broken_invariant = None

    def fail(grant, invariant, detail):
        nonlocal broken_at, broken_invariant
        hard.append(detail)
        if broken_at is None:
            broken_at, broken_invariant = grant, invariant

    if not lineage:
        fail(None, "authority_continuity", "the bundle carries no authority path")
    else:
        root = lineage[0]
        if root.get("parent") is not None:
            fail(root["id"], "authority_continuity",
                 "the path does not begin at a parentless root")
        if root.get("issuer_kind") != "human":
            fail(root["id"], "identity_continuity",
                 "the root grant was not issued by a human principal")

        previous = None
        for g in lineage:
            if g.get("revoked_at") is not None:
                fail(g["id"], "authority_continuity",
                     "grant %s was revoked" % g["id"])
            if at is not None:
                if at < g["not_before"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s was not yet valid at the time of the decision" % g["id"])
                if at >= g["not_after"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s had expired at the time of the decision" % g["id"])
            if previous is not None:
                if g.get("parent") != previous.get("id"):
                    fail(g["id"], "authority_continuity",
                         "grant %s does not point at the grant above it" % g["id"])
                missing = [c for c in g["scope"]
                           if not any(covers(p, c) for p in previous["scope"])]
                if missing:
                    fail(g["id"], "boundary_integrity",
                         "%s holds scope its parent does not: %s"
                         % (g["id"], ", ".join(sorted(missing))))
                ok, why = narrower(previous["constraints"], g["constraints"])
                if not ok:
                    fail(g["id"], "boundary_integrity", "%s: %s" % (g["id"], why))
                if not set(g["purpose_tags"]) <= set(previous["purpose_tags"]):
                    fail(g["id"], "intent_continuity",
                         "%s carries purpose tags its parent does not" % g["id"])
                if (g["not_before"] < previous["not_before"]
                        or g["not_after"] > previous["not_after"]):
                    fail(g["id"], "temporal_validity",
                         "%s is valid outside its parent's window" % g["id"])
                if g["depth"] != previous["depth"] + 1:
                    fail(g["id"], "authority_continuity",
                         "%s records a depth inconsistent with its parent" % g["id"])
            previous = g

        if len(lineage) - 1 > MAX_DEPTH:
            fail(lineage[-1]["id"], "boundary_integrity", "delegation depth exceeds the ceiling")

        if not any(g.get("risk_accepted_by") for g in lineage):
            fail(lineage[0]["id"], "identity_continuity",
                 "no grant in this path names who accepted the risk")

        leaf = lineage[-1]
        action = req.get("action")
        params = req.get("params") or {}

        if action and not any(covers(c, action) for c in leaf["scope"]):
            fail(leaf["id"], "boundary_integrity",
                 "action '%s' is outside the scope of the grant exercised" % action)
        elif action:
            breadth = wildcard_breadth(leaf["scope"], action)
            if breadth and breadth >= 2:
                soft.append("action '%s' is only covered by a broad wildcard" % action)

        eff = effective(lineage)
        failures, unconstrained = params_against(params, eff)
        for f in failures:
            fail(leaf["id"], "boundary_integrity", f)
        for u in unconstrained:
            soft.append("parameter '%s' is not constrained anywhere in the path" % u)

        tag = req.get("purpose_tag")
        if tag:
            if tag not in leaf["purpose_tags"]:
                soft.append("declared purpose '%s' is not carried by the grant" % tag)
        else:
            soft.append("the action declared no purpose")

    verdict = "BLOCK" if hard else ("CHALLENGE" if soft else "ALLOW")
    return verdict, hard, soft, broken_at, broken_invariant


def check_agreement(bundle, rep, mine, hard, soft, broken_at, broken_invariant):
    decision = bundle.get("decision") or {}
    claimed = decision.get("authority_verdict") or decision.get("verdict")

    rep.add(mine == claimed,
            "Independently re-derived authority verdict: " + mine,
            "" if mine == claimed else
            "the issuer claims " + str(claimed) + " and this script reaches " + mine +
            " from the same path. One of us is wrong and the rules are published.")

    if mine == "BLOCK":
        same_grant = (broken_at == decision.get("broken_at"))
        same_inv = (broken_invariant == decision.get("broken_invariant"))
        rep.add(same_grant and same_inv,
                "Refusal reproduces at the same grant and invariant",
                ("grant %s, invariant %s" % (broken_at, broken_invariant))
                if same_grant and same_inv else
                "this script breaks at grant %s / %s, the issuer says %s / %s"
                % (broken_at, broken_invariant,
                   decision.get("broken_at"), decision.get("broken_invariant")))
        rep.note("Why authority could not be derived")
        for h in hard:
            rep.note("  " + h)
    elif soft:
        rep.note("Why this could not be settled without a person")
        for x in soft:
            rep.note("  " + x)

    risk = decision.get("risk_verdict")
    if risk and mine != "BLOCK":
        rep.note("Risk verdict reported as " + str(risk) + ", not re-derivable here",
                 "the composed verdict is the worse of the two; the scoring engine "
                 "is not part of this bundle and is not checked by this script")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    raw = sys.stdin.read() if src == "-" else open(src, "r").read()
    try:
        bundle = json.loads(raw)
    except Exception as exc:
        print("Not readable JSON: " + str(exc))
        return 2

    rep = Report()
    print("=" * 66)
    print("AUTHORITY PROOF  ·  independent verification")
    print("=" * 66)
    d = bundle.get("decision") or {}
    print("evaluation   " + str(d.get("evaluation")))
    print("action       " + str((bundle.get("request") or {}).get("action")))
    print("at           " + str(d.get("evaluated_at")))
    print("hops         " + str(max(0, len(bundle.get("lineage") or []) - 1)))
    if bundle.get("lineage"):
        print("authorised   " + str(bundle["lineage"][0].get("issuer")))
        print("executed     " + str(bundle["lineage"][-1].get("subject")))
        acc = [g.get("risk_accepted_by") for g in bundle["lineage"] if g.get("risk_accepted_by")]
        print("risk owner   " + str(acc[-1] if acc else None))
    print("-" * 66)

    check_signature(bundle, rep)
    check_integrity(bundle, rep)
    mine, hard, soft, ba, bi = rederive(bundle, rep)
    check_agreement(bundle, rep, mine, hard, soft, ba, bi)

    print(rep.render())
    print("-" * 66)
    if rep.failed:
        print("RESULT: NOT VERIFIED. Something above did not hold.")
        return 1
    print("RESULT: VERIFIED - " + mine)
    if mine == "BLOCK":
        print("This is a proof that the action was NOT authorised, and where it failed.")
    print("Checked with no network access, no dependencies, and nothing taken on")
    print("the issuer's word except the meaning of their public key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _digest():
    return hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_verifier_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in FILE_PATHS:
            body = SCRIPT.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition",
                                 'attachment; filename="verify-authority.py"')
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._verifier_patched = True
    _patched[0] = True
    print("VERIFIER: /verify-authority.py installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("VERIFIER: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "serving": list(FILE_PATHS),
            "script_bytes": len(SCRIPT),
            "script_sha256": _digest(),
            "how_to_use": [
                "curl -sO https://sebbi.pro/verify-authority.py",
                "curl -s 'https://sebbi.pro/x/continuity/proof?evaluation=<id>' "
                "| python3 verify-authority.py -",
            ],
            "dependencies": "none - Python standard library only",
            "network": "the script makes no network calls and reports nothing back. "
                       "A verification tool that phones home to the party being "
                       "verified is not a verification tool.",
            "note": "Check script_sha256 against the file you downloaded. And read it "
                    "before you run it, as you would with anything else handed to you "
                    "by the party you are checking.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/warmup.py`

211 lines, 7688 bytes

```python
"""
modules/warmup.py  v1.0  -  arm every page module in one request

THE PROBLEM THIS ENDS
---------------------
console.py, packconsole.py, peerconsole.py, selfcheck.py and the rest all
install their page by patching do_GET at runtime, and that only happens the
first time their handle() runs. So after every deploy the pages 404 until
somebody happens to hit each module's /x/ route.

Worse, most of those modules only make `status` public. A keyless request to
/x/console/ is rejected by the router before the module is ever imported, so
the obvious way of arming them does not work and looks like a broken site
instead of a cold one.

WHAT THIS DOES
--------------
One public route that imports each page module and calls its handle() once,
which is exactly what installs the patch. Every page comes back in a single
request, with no key.

    GET /x/warmup/all       arm everything, report what happened
    GET /x/warmup/status    what is armed right now, arms nothing
    GET /x/warmup/spec      what this is

POINT RAILWAY AT IT
-------------------
Set the healthcheck path to:

    /x/warmup/all

Railway calls it after every deploy, so the site is armed before anyone
opens it. It always returns 200 as long as the process is up - a module
that fails to arm is reported in the body rather than failing the
healthcheck, because one broken page should not roll back a good deploy.

SAFE TO RUN REPEATEDLY
----------------------
Every module guards its own patch with a `_patched` flag, so a second call
is a no-op. Call it every minute if you like.

ADDING A MODULE
---------------
Put its name in PAGE_MODULES. Nothing else. If the module is not deployed
it is reported as missing and the others still arm.
"""

import importlib
import sys
import time
import traceback

VERSION = "1.0"

PUBLIC = {("GET", "all"), ("GET", "status"), ("GET", "spec"), ("GET", "")}

# Modules that serve an HTML page by patching do_GET at runtime.
# Name only - no path, no .py.
PAGE_MODULES = [
    "console",
    "packconsole",
    "peerconsole",
    "selfcheck",
    "savings",
    "standard",
    "network",
    "demo",
]

# Import prefixes tried in order. Different deployments load modules
# differently and guessing once and failing is how you get a 404 you
# cannot explain.
_PREFIXES = ("modules.", "", "aileash.modules.")

_last_run = {"at": None, "results": None}


def _find(name):
    """Return an already-imported module, or import it. (module, how) or (None, why)."""
    for pre in _PREFIXES:
        mod = sys.modules.get(pre + name)
        if mod is not None:
            return mod, "already imported as " + pre + name
    errors = []
    for pre in _PREFIXES:
        try:
            return importlib.import_module(pre + name), "imported as " + pre + name
        except ImportError as exc:
            errors.append(pre + name + ": " + str(exc))
        except Exception as exc:
            # A real error inside the module - a syntax error, a bad import
            # of its own. Worth reporting properly rather than as "missing",
            # because those look identical from outside and cost hours.
            return None, "FAILED TO LOAD (%s): %s" % (
                type(exc).__name__, str(exc)[:200])
    return None, "not found (" + "; ".join(errors[:1]) + ")"


def _arm(name, ctx):
    """Import a page module and call handle() once, which installs its patch."""
    mod, how = _find(name)
    if mod is None:
        return {"module": name, "armed": False, "detail": how}

    fn = getattr(mod, "handle", None)
    if not callable(fn):
        return {"module": name, "armed": False,
                "detail": "loaded but has no handle()"}

    try:
        body, status = fn("GET", "status", {}, None, ctx)
    except Exception as exc:
        return {"module": name, "armed": False,
                "detail": "handle() raised %s: %s" % (
                    type(exc).__name__, str(exc)[:200]),
                "traceback": traceback.format_exc(limit=3).splitlines()[-3:]}

    body = body if isinstance(body, dict) else {}
    armed = bool(body.get("installed", True))
    out = {"module": name, "armed": armed, "http": status, "load": how}
    for k in ("page", "install_result", "version"):
        if k in body:
            out[k] = body[k]
    if not armed:
        out["detail"] = body.get("install_result") or "reported not installed"
    return out


def _status_only(ctx):
    """What is armed, without arming anything. Read-only."""
    rows = []
    for name in PAGE_MODULES:
        found = None
        for pre in _PREFIXES:
            if (pre + name) in sys.modules:
                found = sys.modules[pre + name]
                break
        if found is None:
            rows.append({"module": name, "loaded": False, "armed": False})
            continue
        flag = getattr(found, "_patched", None)
        armed = bool(flag[0]) if isinstance(flag, list) and flag else None
        rows.append({"module": name, "loaded": True, "armed": armed,
                     "page": getattr(found, "PAGE_PATHS", [None])[0]
                             if hasattr(found, "PAGE_PATHS") else None})
    return rows


def handle(method, action, data, api_key, ctx):
    action = (action or "").strip().lower()

    if method != "GET":
        return {"error": "unknown_action", "action": action,
                "GET": ["all", "status", "spec"]}, 404

    if action == "spec":
        return {
            "module": "warmup",
            "version": VERSION,
            "what_it_is": (
                "Page modules install their route by patching do_GET the "
                "first time they run, so every deploy leaves those pages "
                "404 until something touches each one. This touches all of "
                "them in one public request."),
            "routes": {
                "/x/warmup/all": "arm every page module, report each",
                "/x/warmup/status": "what is armed now, arms nothing",
                "/x/warmup/spec": "this",
            },
            "railway_healthcheck_path": "/x/warmup/all",
            "modules": list(PAGE_MODULES),
            "safe_to_repeat": True,
            "note": ("Always returns 200 while the process is up. A module "
                     "that fails to arm is reported in the body, because one "
                     "bad page should not roll back a good deploy."),
        }, 200

    if action == "status":
        return {"armed_now": _status_only(ctx),
                "last_warmup": _last_run["at"],
                "note": "Read-only. Call /x/warmup/all to actually arm."}, 200

    # "" or "all"
    t0 = time.time()
    results = [_arm(name, ctx) for name in PAGE_MODULES]
    _last_run["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _last_run["results"] = results

    armed = [r["module"] for r in results if r.get("armed")]
    failed = [r for r in results if not r.get("armed")]

    for r in failed:
        print("WARMUP: %s did not arm - %s"
              % (r["module"], r.get("detail", "?")), flush=True)
    print("WARMUP: %d/%d armed in %.0fms"
          % (len(armed), len(results), (time.time() - t0) * 1000), flush=True)

    return {
        "ok": True,
        "armed": len(armed),
        "of": len(results),
        "took_ms": round((time.time() - t0) * 1000, 1),
        "pages_ready": [r.get("page") for r in results
                        if r.get("armed") and r.get("page")],
        "results": results,
        "at": _last_run["at"],
        "note": ("A module listed as not armed is either not deployed or "
                 "raised on load - the detail says which. The rest still "
                 "armed."),
    }, 200

```


## `modules/witness.py`

959 lines, 43983 bytes

```python
"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last CONFIRMED anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step. That is not a technical exercise. That is a
conspiracy, and it grows harder with every platform that joins.

WHY observe IS OPEN
-------------------
A witnessing network that only accepts tips from account holders is not a
witnessing network, it is a customer list. Anyone must be able to hand us a
tip without asking permission. Unauthenticated observations are filed under
ANON_KEY, and the router meters them per client address.

NAMES, AND WHAT WE CAN ACTUALLY PROVE ABOUT THEM
------------------------------------------------
The chain name in a submission is self-declared. Anyone can post under any
name. We do not solve that with accounts, because accounts would make the
network closed. We solve it by publishing how strong each claim is, and by
remembering.

Two independent checks run on every submission, and NEITHER of them can
reject it. A submission is always sealed. What changes is what we say about it.

1. LIVENESS - is there a real chain behind this name?
   If the submission carries a url, we fetch it and compare what it serves
   to what was submitted.
     self-consistent  the url serves exactly the tip that was submitted
     live             the url serves a valid tip, but a different one. A busy
                      chain moves between submitting and our fetching, so this
                      is normal and honest, not a failure
     self-declared    no url, or we could not reach it, or it served nonsense

   WHY "self-consistent" AND NOT "confirmed" (changed in 1.2)
   ----------------------------------------------------------
   Both halves of this check come from the same party. The submitter tells us
   the tip and the submitter tells us where to look. Agreement between them
   establishes that the submitter's endpoint agrees with the submitter. That
   is self-consistency, not verification by anyone else.

   Up to v1.1 this value was written as "confirmed", which was the only
   approving word in a schema deliberately built without adjectives - and the
   permanent one, since it is sealed. The docstring carried the caveat and the
   field name contradicted it. Raised by Ishaan (Shango MID), correctly, and
   changed rather than defended.

   Blocks sealed before 1.2 say "confirmed" and cannot be altered - that is
   the property working as intended. Both values mean the same check. The
   legend on /x/witness/peers names both.

   It still proves the submitter operates a live chain producing that data. It
   does NOT prove they are who they say. Anyone running a real chain can point
   a stolen name at their own url and pass this check cleanly.

2. NAME BINDING - is this the same operator as last time?
   The first time a name is seen with a url we can reach, we record that url
   against the name. Every later submission under that name is compared.
     first-use      never seen this name before, binding recorded
     bound          same url as the first time. Same operator, consistently
     conflict       this name has been submitted from a different url than
                    the one it was first bound to

   A conflict is not proof of theft. Operators move hosts. But it is exactly
   the event anyone auditing the network needs to see, and it is recorded
   permanently in our chain rather than resolved quietly by us.

   This is what actually closes name theft. Check 1 alone does not.

WHY EVERY READER-FACING PHRASE LIVES IN ONE BLOCK (added in 1.3)
-----------------------------------------------------------------
Four separate corrections in one week were all the same job: find the
sentence, change the sentence, and hope there is not a second copy of it
somewhere else in the file. There usually was. A word that goes into a sealed
record, or into a response a peer will quote back at us, is not incidental
prose - it is part of the interface, and it needs one home.

Everything a reader sees now lives in VOCABULARY and MESSAGES at the top of
this file. The code below references those keys and never spells a claim out
inline. The next peer who finds an overstatement costs one line in one place,
and the wording can be reviewed on its own without reading the logic.

SSRF
----
Check 1 makes our server fetch a url chosen by an anonymous stranger. Done
naively that is a hole considerably worse than the one it fixes: it would let
anyone use us to reach services on our own private network, and to bounce
traffic at a third party. So the fetcher only speaks http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that is
private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a small cap.

HONEST LIMITS
-------------
- Nobody can be forced to keep publishing. A witness network's guarantee is
  only as durable as its least persistent member, and that is not a property
  any amount of design can fix. Listed first because it is the one that
  actually bites.
- ANCHORING IS PER-PROOF, NOT A PROPERTY OF THE CHAIN. Up to v1.2 this module
  told readers "our chain is externally anchored" as a standing fact. It is
  not. A proof is submitted to the OpenTimestamps calendars immediately, and
  only becomes Bitcoin-confirmed once it has been upgraded and independently
  verified. A given block is anchored when a proof covering it has confirmed,
  and not before. Raised by Philip Pinol (PRAXIS / ThePraesidium.ai) against
  block 846, correctly. Every route now points at /x/ots/status rather than
  asserting a state this module cannot see.
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- Two colluding platforms witnessing only each other prove very little. The
  guarantee comes from breadth.
- This module does not verify a peer's chain is internally valid. It records
  what they claimed, when, and how well it stood up to checking.
- The liveness fetch resolves a hostname and then fetches it. An attacker
  controlling DNS could answer differently between those two steps. Closing
  that needs the connection pinned to the checked address, which is more
  machinery than this warrants today. It is written down rather than hidden.

    GET  /x/witness/tip                 our current tip, for peers to record
    POST /x/witness/observe             chain, tip, url - we seal their tip
                                        (peer accepted as an alias for chain;
                                         optional peer_ts or ts, epoch or ISO)
    GET  /x/witness/attest?peer=&tip=   did we witness this, and when
    GET  /x/witness/peers               who we witness, and how consistently
    GET  /x/witness/spec                the protocol, in four calls
    GET  /x/witness/history?peer=       every tip we hold for that peer (keyed)
"""

import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.3"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# ----------------------------------------------------------------------
# values that get sealed
#
# Anything in this section is written into a permanent record AND compared
# against in code. Both roles are invisible to each other from outside, which
# is exactly how renaming the match value in 1.2 silently broke first-use
# binding. One constant, one meaning, every comparison through the name.
# ----------------------------------------------------------------------

# The liveness value written when a submitted url serves exactly the submitted
# tip. Was "confirmed" up to v1.1 - see the docstring.
LIVENESS_MATCH = "self-consistent"

# Historical value for the same check, still present in blocks sealed before
# v1.2. Sealed blocks cannot be altered, so both are accepted wherever a
# comparison is made.
LIVENESS_MATCH_LEGACY = "confirmed"

# The url answered with a valid tip, but a different one. A moving chain.
LIVENESS_MOVED = "live"

# No url, unreachable url, or the url served something that was not a tip.
LIVENESS_NONE = "self-declared"

# Values that count as "we reached a url and it served a valid tip", for the
# purpose of binding a name to that url.
LIVENESS_REACHED = (LIVENESS_MATCH, LIVENESS_MATCH_LEGACY, LIVENESS_MOVED)

NAME_FIRST = "first-use"
NAME_BOUND = "bound"
NAME_CONFLICT = "conflict"
NAME_UNBOUND = "unbound"

# ----------------------------------------------------------------------
# everything a reader sees
#
# Nothing below this block spells out a claim inline. If a phrase needs
# correcting it is corrected here, once, and every route that returns it
# changes together.
# ----------------------------------------------------------------------

# Said wherever this module would previously have asserted that the chain is
# anchored. It is not this module's fact to assert - anchoring state lives in
# the OTS proofs and only /x/ots/status can see it.
ANCHOR_NOTE = (
    "Separately from the hash chain: this deployment submits its chain to the "
    "OpenTimestamps calendars for Bitcoin anchoring. Submission is not "
    "confirmation. A block is Bitcoin-confirmed only once a proof covering it "
    "has been upgraded and verified with a standard OpenTimestamps client. "
    "Check /x/ots/status for the state of the proof covering this block. "
    "Until that proof confirms, the guarantee here is the hash chain and not "
    "Bitcoin."
)

VOCABULARY = {
    LIVENESS_MATCH: (
        "The submitted url served exactly the submitted tip. Both halves came "
        "from the submitter, so this records self-consistency - NOT "
        "verification by us or any third party. Written as '%s' from witness "
        "v1.2 onward." % LIVENESS_MATCH),
    LIVENESS_MATCH_LEGACY: (
        "The same check as '%s', under the name used before witness v1.2. It "
        "was renamed because the old name implied third-party verification "
        "that the check does not perform. Sealed blocks cannot be altered, so "
        "this record keeps the original word." % LIVENESS_MATCH),
    LIVENESS_MOVED: (
        "The url served a valid but different tip. A chain that moves between "
        "submitting and our fetching is the normal case, not a failure."),
    LIVENESS_NONE: (
        "No url was supplied, or we could not reach it. Taken on the "
        "submitter's word and checked by nobody."),
    None: "Not checked. Recorded before liveness checking existed.",
}

NAME_VOCABULARY = {
    NAME_FIRST: (
        "First time this name was seen with a reachable url, so the name is "
        "now bound to it network-wide. Any later submission under this name "
        "from a different address records as conflict, permanently."),
    NAME_BOUND: (
        "Submitted from the same url this name was first bound to. Same "
        "operator, consistently."),
    NAME_CONFLICT: (
        "This name has been submitted from a different address than the one "
        "it was first bound to. Not proof of theft - operators move hosts - "
        "but it is the event an auditor needs to see, and it is permanent."),
    NAME_UNBOUND: (
        "No reachable url, so there is nothing to bind this name to. "
        "IMPORTANT: an unbound name stays claimable. Whoever submits it next "
        "WITH a reachable url takes the binding, and your own later "
        "submission would then read conflict. We cannot prevent that - an "
        "open endpoint has no way to tell two claimants apart - but a binding "
        "placed over a name that was submitted before is recorded as such. If "
        "the name matters, either submit with a url serving your tip, or use "
        "the signed lane at /x/peer/submit."),
    None: "Not checked.",
}

# What the signed lane does and does not bind. Agreed wording, unsoftened:
# a shared secret is held by both parties, so it excludes third parties and
# does not exclude the operator. Stated here rather than left for a peer to
# work out from the word "signed".
SIGNED_LANE_NOTE = (
    "The signed lane at /x/peer/submit binds a name to knowledge of a shared "
    "secret, not to control of an address. Because the operator of this "
    "deployment holds the same secret, it closes third-party submission under "
    "your name and does not close operator submission under your name. That "
    "is a normal property of HMAC and it is stated rather than implied."
)

MESSAGES = {
    "tip_note": (
        "Record this tip in your own chain. Hand us yours at "
        "/x/witness/observe and we will record it in ours."),
    "tip_verify": (
        "/api/verify-chain checks this chain end to end. /x/ots/status shows "
        "the state of each external timestamp proof."),
    "observe_ok": (
        "Your tip is now inside a chain you do not control. What that block "
        "carries is stated in what_this_proves - it is a record that this "
        "value was handed to us at this time, and nothing about whether the "
        "records behind it are true."),
    "observe_advice": (
        "Send a url serving your current tip and this becomes checkable by "
        "anyone rather than taken on your word. Read name_vocabulary first: "
        "withholding a url also leaves the name claimable."),
    "observe_conflict": (
        "Sealed, and flagged. This name has been used from a different "
        "address before. That discrepancy is now permanent in our chain."),
    "attest_proves": (
        "That this tip was handed to us at this time and sealed into our "
        "chain. Liveness records whether a url the submitter supplied served "
        "the same tip the submitter sent - self-consistency, not verification "
        "by us. Neither proves the submitter's identity."),
    "attest_proof": (
        "This observation is a block in our chain. Altering or removing it "
        "breaks every block after it, and that is checkable by anyone at "
        "/api/verify-chain. " + ANCHOR_NOTE),
    "list_is": (
        "Parties that have submitted a tip to this deployment. Being listed "
        "here is not membership of anything, not endorsement of anything "
        "sealed in this chain, and implies no relationship beyond having sent "
        "a hash."),
    "list_note": (
        "Silent peers are visible by design. A network you cannot audit is "
        "not a network. Nothing here proves identity - it shows how well each "
        "claim stood up to checking."),
    "history_note": (
        "If this peer ever presents a history whose tips do not match these, "
        "the divergence is provable."),
    "chain_required": "A short stable identifier - a domain works well.",
    "invalid_tip": "A tip is 64 hex characters - a SHA-256 chain head.",
    "not_witnessed": "We hold no record of this tip from this peer.",
}

LEGEND = {
    LIVENESS_MATCH: VOCABULARY[LIVENESS_MATCH],
    LIVENESS_MATCH_LEGACY: VOCABULARY[LIVENESS_MATCH_LEGACY],
    LIVENESS_MOVED: VOCABULARY[LIVENESS_MOVED],
    LIVENESS_NONE: VOCABULARY[LIVENESS_NONE],
    NAME_FIRST: VOCABULARY.get(NAME_FIRST) or NAME_VOCABULARY[NAME_FIRST],
    NAME_BOUND: NAME_VOCABULARY[NAME_BOUND],
    NAME_CONFLICT: NAME_VOCABULARY[NAME_CONFLICT],
    NAME_UNBOUND: NAME_VOCABULARY[NAME_UNBOUND],
    "unbound_costs_you_the_name": (
        "A submission with no reachable url does not bind the name. Whoever "
        "submits it next with a url takes the binding. Choosing the accurate "
        "weaker liveness status therefore leaves the name claimable - a "
        "coupling worth knowing before it bites."),
    "signed_lane": SIGNED_LANE_NOTE,
    "anchoring": ANCHOR_NOTE,
}

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("GET", "spec"), ("POST", "observe")}

# Observations arriving without a key are filed under this.
ANON_KEY = "public-witness"

# Liveness fetch limits. Deliberately tight - this runs on an anonymous
# request, so every one of these is also a denial-of-service control.
FETCH_TIMEOUT = 4
MAX_FETCH_BYTES = 65536
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# Field names other implementations serve their tip under. Being strict about
# a name we never published is a bug in the receiver, not in the peer. Kept
# identical to the list mutual.py advertises.
TIP_FIELDS = ("tip", "hash", "head", "tip_sha256", "root", "current_tip",
              "chain_tip", "latest")

MAX_HISTORY = 500

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witness_log(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,peer TEXT,tip TEXT,peer_ts REAL,observed REAL,audit_hash TEXT,block_index INTEGER,note TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer ON witness_log(api_key,peer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_tip ON witness_log(tip)")

        # Added in 1.1. Existing rows keep NULL, which reads as unchecked -
        # correct, because they were.
        have = set()
        try:
            for row in c.execute("PRAGMA table_info(witness_log)").fetchall():
                have.add(row[1])
        except Exception:
            pass
        for col in ("url", "liveness", "name_status"):
            if col not in have:
                try:
                    c.execute("ALTER TABLE witness_log ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass

        # Added in 1.3. /x/witness/peers previously read every row in the
        # table on every call to work out each peer's latest status. At 700
        # observations that is wasteful; at 70,000 it is a problem. This index
        # lets the same answer come from a grouped query.
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer_id ON witness_log(peer,id)")
        except Exception:
            pass

        # Name bindings are network-wide, not per api_key. A name means one
        # operator across the whole network or it means nothing.
        c.execute("CREATE TABLE IF NOT EXISTS witness_names(peer TEXT PRIMARY KEY,url TEXT,first_seen REAL,first_liveness TEXT)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _our_tip(ctx):
    with ctx["lock"]:
        r = ctx["conn"].execute("SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def _tip(ctx, api_key):
    tip, ts, height = _our_tip(ctx)
    return {"tip": tip, "height": height, "sealed_at": _iso(ts),
            "witness_version": VERSION,
            "note": MESSAGES["tip_note"],
            "verify": MESSAGES["tip_verify"],
            "anchoring": ANCHOR_NOTE}, 200


# ----------------------------------------------------------------------
# liveness fetch - see the SSRF section above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction from a stranger to fetch a second url we
    never checked. Refuse rather than follow."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    """Resolve and refuse anything that isn't plainly on the public internet."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    host = parts.hostname
    if not host:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(host, port)


def _norm_url(url):
    """Normalise a url for COMPARISON only. The raw string is what gets stored
    and shown.

    Added in 1.3. Binding compared raw strings, so the same endpoint submitted
    as https://x.test/w and https://X.test/w/ recorded a permanent conflict
    against an operator who had done nothing wrong. A conflict is the loudest
    thing this module can say about somebody and it cannot be withdrawn, so it
    should fire on a genuinely different address and not on a trailing slash.

    Deliberately conservative: case on scheme and host, the default port, and
    one trailing slash. Path case, query order and anything else still count
    as different, because they can be.
    """
    if not url:
        return ""
    raw = url.strip()
    try:
        p = urlparse(raw)
    except Exception:
        return raw.lower()
    scheme = (p.scheme or "").lower()
    host = (p.hostname or "").lower()
    if not scheme or not host:
        return raw.lower()
    port = p.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = host + (":%d" % port if port else "")
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    out = scheme + "://" + netloc + path
    if p.query:
        out += "?" + p.query
    return out


def _fetch_tip(url):
    """Returns (tip_or_None, note). Never raises."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, why
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "aileash-witness/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            if response.getcode() != 200:
                return None, "url answered %s" % response.getcode()
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, "url answered %s" % exc.code
    except Exception as exc:
        return None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, "response too large"
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None, "url did not return json"
    if not isinstance(data, dict):
        return None, "url did not return an object"
    found = ""
    for field in TIP_FIELDS:
        value = data.get(field)
        if value:
            found = str(value).strip().lower()
            break
    if not HEX64.match(found or ""):
        return None, "no valid tip at that url"
    return found, None


def _check_liveness(url, tip):
    """self-consistent / live / self-declared. Never rejects anything.

    Note what self-consistent means: the submitter told us the tip AND told us
    where to look, and the two agreed. That is the submitter agreeing with
    themselves. It is worth recording and it is not third-party verification.
    """
    if not url:
        return LIVENESS_NONE, "no url supplied"
    found, why = _fetch_tip(url)
    if found is None:
        return LIVENESS_NONE, why
    if found == tip:
        return LIVENESS_MATCH, ("the submitted url served exactly the submitted "
                                "tip - both sides of this check come from the "
                                "submitter, so this is self-consistency, not "
                                "third-party verification")
    return LIVENESS_MOVED, ("url serves a different tip (%s) - chain has moved "
                            "on since submitting" % found[:16])


def _prior_unbound(ctx, peer):
    """How many times this name has been submitted with no bindable url.

    Exists because of a gap Ishaan (Shango MID) found: a submission without
    a url does not bind, so a recognisable name can be used honestly by its
    owner and then bound by somebody else who supplies a url first. The
    owner's later submission would read conflict, and they would be the one
    looking like the impostor.

    An anonymous endpoint cannot tell two claimants apart - there is nothing
    to bind to - so this does not prevent the squat. What it does is make it
    visible: a binding over a name that has been submitted before is
    recorded as such, permanently, in the sealed note. An auditor sees the
    name was not fresh when it was claimed.

    Detection rather than prevention. Prevention needs a credential, which
    is what the signed lane at /x/peer/submit is for - within the limit
    stated in SIGNED_LANE_NOTE.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM witness_log WHERE peer=? AND "
                "(url IS NULL OR url='')", (peer,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _check_name(ctx, peer, url, liveness):
    """first-use / bound / conflict / unbound.

    Only bind a name to a url we actually reached. Binding to an unreachable
    url would let someone reserve a name with an address that never answers.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT url,first_seen FROM witness_names WHERE peer=?", (peer,)).fetchone()

    if row and row[0]:
        if not url:
            return NAME_UNBOUND, "no url supplied; this name is bound to %s" % row[0]
        if _norm_url(url) == _norm_url(row[0]):
            if url.strip() != row[0]:
                return NAME_BOUND, ("same address as the binding, written "
                                    "differently (bound as %s, submitted as "
                                    "%s)" % (row[0], url.strip()))
            return NAME_BOUND, None
        return NAME_CONFLICT, ("this name was first seen at %s and has now been submitted from %s"
                               % (row[0], url.strip()))

    # LIVENESS_REACHED, not a literal - renaming the match value in 1.2 would
    # otherwise have silently stopped first-use binding for exact matches.
    if url and liveness in LIVENESS_REACHED:
        prior = _prior_unbound(ctx, peer)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT OR REPLACE INTO witness_names(peer,url,first_seen,first_liveness) VALUES(?,?,?,?)",
                (peer, url.strip(), time.time(), liveness))
            ctx["conn"].commit()
        note = "name now bound to %s" % url.strip()
        if prior:
            note += ("; WARNING: this name was submitted %d time(s) before "
                     "this binding with no url, so it was not a fresh name "
                     "when it was claimed - if that was not you, the earlier "
                     "submissions are permanently in this chain and so is "
                     "this warning" % prior)
        return NAME_FIRST, note

    return NAME_UNBOUND, ("no reachable url, so nothing to bind this name to. "
                          "This name remains claimable by anyone who submits "
                          "it with a reachable url - see name_vocabulary")


# ----------------------------------------------------------------------
# observe
# ----------------------------------------------------------------------

def _observe(ctx, api_key, data):
    # The published standard calls this field "chain"; earlier internal
    # callers used "peer". Accept either. A receiver being strict about
    # field names it never published is a bug in the receiver.
    peer = str(data.get("chain") or data.get("peer") or "").strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": MESSAGES["chain_required"],
                "field": "chain (peer also accepted)"}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": MESSAGES["invalid_tip"]}, 400

    url = data.get("url")
    url = str(url).strip() if url else ""
    if len(url) > 500:
        url = ""

    # Time the peer claims it sealed at. Epoch or ISO, either field name.
    # Carry on without it - supporting detail, not the evidence.
    peer_ts = data.get("peer_ts", data.get("ts"))
    if peer_ts is not None:
        try:
            peer_ts = float(peer_ts)
        except (TypeError, ValueError):
            try:
                s = str(peer_ts).strip().replace("Z", "+00:00")
                peer_ts = datetime.fromisoformat(s).timestamp()
            except Exception:
                peer_ts = None

    liveness, live_note = _check_liveness(url, tip)
    name_status, name_note = _check_name(ctx, peer, url, liveness)

    ts = time.time()
    notes = []

    with ctx["lock"]:
        prev = ctx["conn"].execute("SELECT tip,observed FROM witness_log WHERE api_key=? AND peer=? ORDER BY id DESC LIMIT 1", (api_key, peer)).fetchone()
        seen = ctx["conn"].execute("SELECT observed FROM witness_log WHERE api_key=? AND peer=? AND tip=? LIMIT 1", (api_key, peer, tip)).fetchone()

    if seen:
        notes.append("tip already witnessed at " + str(_iso(seen[0])) + " - chain has not advanced, or history was replayed")
    elif prev and prev[0] == tip:
        notes.append("unchanged since last observation")
    if live_note:
        notes.append(live_note)
    if name_note:
        notes.append(name_note)
    note = "; ".join(notes)

    # The verification result is sealed alongside the tip. If we later claim a
    # submission was self-consistent, the chain has to agree.
    detail = ("peer=" + peer + ";tip=" + tip + ";url=" + (url or "-") +
              ";liveness=" + liveness + ";name=" + name_status +
              ";peer_ts=" + str(peer_ts) + (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts,
           "liveness": liveness, "name_status": name_status, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    # The seal is the record. If this insert fails the block still exists and
    # is still valid - the index row is a convenience for lookup, not the
    # evidence - so a failure here must not be reported as a failed
    # observation.
    index_ok = True
    try:
        with ctx["lock"]:
            ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note,url,liveness,name_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                (api_key, peer, tip, peer_ts, ts, h, idx, note or None,
                                 url or None, liveness, name_status))
            ctx["conn"].commit()
    except Exception as exc:
        index_ok = False
        index_error = type(exc).__name__

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "liveness": liveness, "name_status": name_status,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": MESSAGES["observe_ok"],
           "anchoring": ANCHOR_NOTE}
    if note:
        out["flag"] = note
    out["witness_version"] = VERSION
    out["liveness_vocabulary"] = _vocab(liveness)
    out["name_vocabulary"] = _name_vocab(name_status)
    if not index_ok:
        out["index_warning"] = (
            "Sealed into the chain, but our lookup index did not accept the "
            "row (%s). The block is valid and permanent; /x/witness/attest "
            "may not find it until the index is repaired. Reported rather "
            "than hidden." % index_error)
    if liveness == LIVENESS_NONE:
        out["advice"] = MESSAGES["observe_advice"]
    if name_status == NAME_CONFLICT:
        out["warning"] = MESSAGES["observe_conflict"]
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required",
                "usage": "/x/witness/attest?peer=<name>&tip=<64 hex>"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": MESSAGES["not_witnessed"]}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "last_observed": _iso(rows[-1][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "liveness": rows[0][4] or "unchecked",
            "liveness_vocabulary": _vocab(rows[0][4]),
            "name_status": rows[0][5] or "unchecked",
            "name_vocabulary": _name_vocab(rows[0][5]),
            "submitted_url": rows[0][6],
            "witness_version": VERSION,
            "what_this_proves": MESSAGES["attest_proves"],
            "proof": MESSAGES["attest_proof"],
            "anchoring": ANCHOR_NOTE}, 200


def _vocab(liveness):
    """Make the vocabulary travel with the value.

    The legend on /x/witness/peers reconciles self-consistent and confirmed
    for whoever reads the legend. Sealed blocks travel and legends do not:
    anyone quoting a block elsewhere carries the word without the
    reconciliation attached. Raised by Ishaan (Shango MID) after hitting the
    same thing on his own register - the correction reached the page and not
    the metadata that gets shared with the link.

    So any route that returns an observation returns what the word means at
    the point it is read, rather than pointing at a legend that may not
    follow it.

    General form worth keeping: a name a reader treats as documentation may
    be a value the code branches on, and the two roles are invisible to each
    other from outside.
    """
    return VOCABULARY.get(liveness, VOCABULARY[None])


def _name_vocab(name_status):
    """What the name status means, and what it costs.

    Travels with the value for the same reason liveness vocabulary does. The
    unbound entry states the exposure plainly rather than leaving a submitter
    to work it out: choosing the accurate weaker liveness status by
    withholding a url also leaves the name claimable, and nobody should have
    to discover that coupling by being squatted.
    """
    return NAME_VOCABULARY.get(name_status, NAME_VOCABULARY[None])


def _peers(ctx, api_key):
    """Who we witness, and how consistently.

    Rewritten in 1.3. This used to read every row in witness_log to find each
    peer's most recent liveness and name status. Now the same answer comes
    from a grouped query against the (peer,id) index, so the cost stops
    growing with the size of the log.
    """
    with ctx["lock"]:
        c = ctx["conn"]
        if api_key:
            rows = c.execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = c.execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()

        latest = {}
        for p, live, name in c.execute(
                "SELECT w.peer,w.liveness,w.name_status FROM witness_log w "
                "JOIN (SELECT peer,MAX(id) AS mid FROM witness_log GROUP BY peer) m "
                "ON w.id=m.mid").fetchall():
            latest[p] = (live, name)

        conflicts = {}
        for p, n in c.execute(
                "SELECT peer,COUNT(*) FROM witness_log WHERE name_status=? "
                "GROUP BY peer", (NAME_CONFLICT,)).fetchall():
            conflicts[p] = n

        bindings = {}
        for p, u in c.execute("SELECT peer,url FROM witness_names").fetchall():
            bindings[p] = u

    t = time.time()
    peers = []
    for p, n, first, last, distinct in rows:
        hours = round((t - last) / 3600, 1)
        live, name = latest.get(p, (None, None))
        entry = {"peer": p, "observations": n, "distinct_tips": distinct,
                 "first_seen": _iso(first), "last_seen": _iso(last),
                 "hours_since_last": hours,
                 "status": ("current" if hours < 6 else "stale" if hours < 48 else "silent"),
                 "liveness": live or "unchecked",
                 "name_status": name or "unchecked",
                 "bound_to": bindings.get(p)}
        if conflicts.get(p):
            entry["name_conflicts"] = conflicts[p]
        peers.append(entry)
    return {"count": len(peers), "peers": peers,
            "witness_version": VERSION,
            "what_this_list_is": MESSAGES["list_is"],
            "status_vocabulary": {
                "current": "observed within the last 6 hours",
                "stale": "last observed between 6 and 48 hours ago",
                "silent": "not observed for more than 48 hours",
                "note": ("These describe elapsed time since we last recorded "
                         "an observation and nothing else. A peer that "
                         "publishes on a human schedule rather than a timer "
                         "will read stale between sessions, correctly. It is "
                         "not a claim that anyone's endpoint was unavailable."),
            },
            "legend": LEGEND,
            "note": MESSAGES["list_note"]}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT ?", (api_key, peer, MAX_HISTORY)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows), "limit": MAX_HISTORY,
            "witness_version": VERSION,
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4], "liveness": r[5] or "unchecked",
                              "name_status": r[6] or "unchecked",
                              "url": r[7]} for r in rows],
            "note": MESSAGES["history_note"]}, 200


def _spec():
    """The whole protocol, for someone who is not going to run our code.

    Added in 1.3. Every other module publishes a spec route and this one did
    not, which meant the four calls a new peer needs were only written down
    in a page they had to be sent a link to.
    """
    return {"witness_version": VERSION,
            "the_protocol_in_four_calls": [
                "1. GET /x/witness/tip - our current chain head.",
                "2. Seal that value into your own chain, however your chain works.",
                "3. POST /x/witness/observe with {\"chain\":\"<your name>\","
                "\"tip\":\"<your 64 hex head>\",\"url\":\"<where you publish "
                "your head>\"}. No account, no key.",
                "4. GET /x/witness/attest?peer=<your name>&tip=<your head> - "
                "your receipt, readable by anyone.",
            ],
            "fields": {
                "chain": "required. Short stable identifier, 80 chars max. "
                         "'peer' accepted as an alias.",
                "tip": "required. 64 lowercase hex characters.",
                "url": "optional but strongly advised - see name_vocabulary. "
                       "http or https, port 80 or 443, must resolve to a "
                       "publicly routable address, no redirects followed.",
                "peer_ts": "optional. Epoch seconds or ISO 8601. 'ts' accepted "
                           "as an alias.",
            },
            "tip_fields_we_accept_at_your_url": list(TIP_FIELDS),
            "nothing_is_rejected": (
                "Both checks are non-rejecting. Every well-formed submission "
                "is sealed. What varies is what the record says about it."),
            "liveness_vocabulary": {k: v for k, v in VOCABULARY.items() if k},
            "name_vocabulary": {k: v for k, v in NAME_VOCABULARY.items() if k},
            "signed_lane": SIGNED_LANE_NOTE,
            "anchoring": ANCHOR_NOTE,
            "what_this_is_not": MESSAGES["list_is"]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "observe":
            # No key needed. Anonymous submissions are partitioned under
            # ANON_KEY so they never mix with a customer's own witness log.
            return _observe(ctx, api_key or ANON_KEY, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
    else:
        if action == "tip":
            return _tip(ctx, api_key)
        if action == "peers":
            return _peers(ctx, api_key)
        if action == "attest":
            return _attest(ctx, api_key, data)
        if action == "spec":
            return _spec()
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404

```
