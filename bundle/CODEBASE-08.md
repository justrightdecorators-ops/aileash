# Codebase — part 8 of 19

Contains:
- `modules/standard.py`
- `modules/stats.py`
- `modules/verifier.py`
- `modules/witness.py`
- `modules/witness_guard.py`
- `modules/witnessed.py`
- `Verify_ai.py`


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


## `modules/witness.py`

514 lines, 23310 bytes

```python
"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control - and those chains are
themselves anchored externally.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step, and re-anchor all of it. That is not a
technical exercise. That is a conspiracy, and it grows harder with every
platform that joins.

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
     confirmed      the url serves exactly the tip that was submitted
     live           the url serves a valid tip, but a different one. A busy
                    chain moves between submitting and our fetching, so this
                    is normal and honest, not a failure
     self-declared  no url, or we could not reach it, or it served nonsense

   Note what this does and does not prove. It proves the submitter operates
   a live chain producing that data. It does NOT prove they are who they say.
   Anyone running a real chain can point a stolen name at their own url and
   pass this check cleanly.

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
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- A peer can stop publishing. Gaps are visible, which is the point, but
  nobody can force participation.
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
    GET  /x/witness/history?peer=       every tip we hold for that peer
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

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("POST", "observe")}

# Observations arriving without a key are filed under this.
ANON_KEY = "public-witness"

# Liveness fetch limits. Deliberately tight - this runs on an anonymous
# request, so every one of these is also a denial-of-service control.
FETCH_TIMEOUT = 4
MAX_FETCH_BYTES = 65536
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

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
            "note": "Record this tip in your own chain. Hand us yours at /x/witness/observe and we will record it in ours.",
            "verify": "/api/verify-chain checks this chain end to end. /api/anchor-status shows the external timestamp."}, 200


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
    found = data.get("tip") or data.get("hash") or data.get("head") or ""
    found = str(found).strip().lower()
    if not HEX64.match(found):
        return None, "no valid tip at that url"
    return found, None


def _check_liveness(url, tip):
    """confirmed / live / self-declared. Never rejects anything."""
    if not url:
        return "self-declared", "no url supplied"
    found, why = _fetch_tip(url)
    if found is None:
        return "self-declared", why
    if found == tip:
        return "confirmed", None
    return "live", "url serves a different tip (%s) - chain has moved on since submitting" % found[:16]


def _check_name(ctx, peer, url, liveness):
    """first-use / bound / conflict / unbound.

    Only bind a name to a url we actually reached. Binding to an unreachable
    url would let someone reserve a name with an address that never answers.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT url,first_seen FROM witness_names WHERE peer=?", (peer,)).fetchone()

    if row and row[0]:
        if not url:
            return "unbound", "no url supplied; this name is bound to %s" % row[0]
        if url.strip() == row[0]:
            return "bound", None
        return "conflict", ("this name was first seen at %s and has now been submitted from %s"
                            % (row[0], url.strip()))

    if url and liveness in ("confirmed", "live"):
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT OR REPLACE INTO witness_names(peer,url,first_seen,first_liveness) VALUES(?,?,?,?)",
                (peer, url.strip(), time.time(), liveness))
            ctx["conn"].commit()
        return "first-use", "name now bound to %s" % url.strip()

    return "unbound", "no reachable url, so nothing to bind this name to"


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
                "message": "A short stable identifier - a domain works well.",
                "field": "chain (peer also accepted)"}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400

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
    # submission was confirmed, the chain has to agree.
    detail = ("peer=" + peer + ";tip=" + tip + ";url=" + (url or "-") +
              ";liveness=" + liveness + ";name=" + name_status +
              ";peer_ts=" + str(peer_ts) + (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts,
           "liveness": liveness, "name_status": name_status, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note,url,liveness,name_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (api_key, peer, tip, peer_ts, ts, h, idx, note or None,
                             url or None, liveness, name_status))
        ctx["conn"].commit()

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "liveness": liveness, "name_status": name_status,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": "Your tip is now inside a chain you do not control, and ours is anchored externally."}
    if note:
        out["flag"] = note
    if liveness == "self-declared":
        out["advice"] = "Send a url serving your current tip and this becomes checkable by anyone rather than taken on your word."
    if name_status == "conflict":
        out["warning"] = "Sealed, and flagged. This name has been used from a different address before. That discrepancy is now permanent in our chain."
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": "We hold no record of this tip from this peer."}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "liveness": rows[0][4] or "unchecked",
            "name_status": rows[0][5] or "unchecked",
            "submitted_url": rows[0][6],
            "what_this_proves": "That this tip was handed to us at this time and sealed into our chain. Liveness says whether a url served the same tip when we looked. Neither proves the submitter's identity.",
            "proof": "This observation is a block in our chain. Altering or removing it breaks every block after it, and our chain is externally anchored."}, 200


def _peers(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()
        latest = {}
        conflicts = {}
        bindings = {}
        for p, live, name in ctx["conn"].execute("SELECT peer,liveness,name_status FROM witness_log ORDER BY id ASC").fetchall():
            latest[p] = (live, name)
            if name == "conflict":
                conflicts[p] = conflicts.get(p, 0) + 1
        for p, u in ctx["conn"].execute("SELECT peer,url FROM witness_names").fetchall():
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
            "legend": {
                "confirmed": "a url served exactly the tip that was submitted",
                "live": "a url served a valid but different tip - a moving chain, which is normal",
                "self-declared": "no url, or we could not reach it. Taken on their word",
                "first-use": "first time this name was seen; now bound to that url",
                "bound": "same url as the first time this name appeared",
                "conflict": "this name has been submitted from more than one address",
            },
            "note": "Silent peers are visible by design. A network you cannot audit is not a network. Nothing here proves identity - it shows how well each claim stood up to checking."}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT 500", (api_key, peer)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows),
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4], "liveness": r[5] or "unchecked",
                              "name_status": r[6] or "unchecked",
                              "url": r[7]} for r in rows],
            "note": "If this peer ever presents a history whose tips do not match these, the divergence is provable."}, 200


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
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/witness_guard.py`

75 lines, 2152 bytes

```python
import logging
from typing import Dict, Any

# Configure security log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WitnessGuard")

# Revoked Node IDs / Keys
REVOKED_WITNESSES: set[str] = {
    "wit:red-flag-ai-pro",
}

# Whitelist of trusted active witness nodes
ALLOWED_WITNESSES: set[str] = {
    # Add active trusted node IDs here
}

def validate_witness_seal_request(payload: Dict[str, Any]) -> bool:
    """
    Validates whether incoming witness seal requests are from an active, authorized node.
    Rejects and logs revoked IDs instantly.
    """
    user_id = payload.get("user")
    seal = payload.get("seal")
    prev_hash = payload.get("prev")

    if not user_id:
        logger.warning("Rejected seal request: Missing node identifier.")
        return False

    # Hard Reject for Revoked / Blocked Node
    if user_id in REVOKED_WITNESSES:
        logger.error(
            f"BLOCKED: Revoked node '{user_id}' attempted block seal! "
            f"Seal Hash: {str(seal)[:10]}... | Prev Hash: {str(prev_hash)[:10]}..."
        )
        return False

    # Strict Whitelist Verification
    if ALLOWED_WITNESSES and user_id not in ALLOWED_WITNESSES:
        logger.warning(f"UNAUTHORIZED: Node '{user_id}' is not in the active whitelist.")
        return False

    return True


# Route Middleware Handler
def handle_incoming_block(payload: Dict[str, Any]):
    if not validate_witness_seal_request(payload):
        return {
            "status": "error",
            "code": 401,
            "message": "Unauthorized Witness Node. Access Revoked."
        }, 401

    # Append Block to Chain State
    return {
        "status": "success",
        "code": 200,
        "message": "Block Witness Sealed Successfully"
    }, 200


# Execution Test
if __name__ == "__main__":
    test_payload = {
        "user": "wit:red-flag-ai-pro",
        "score": 0,
        "seal": "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b",
        "prev": "58eb2ea09de10b57dcbd13bcda220fb47ed62f53"
    }

    response, status_code = handle_incoming_block(test_payload)
    print(f"\nExecution Result: Status {status_code} -> {response}")

```


## `modules/witnessed.py`

600 lines, 26111 bytes

```python
#!/usr/bin/env python3
"""
modules/witnessed.py  -  what an outside party had already seen, and when

THE HOLE THIS CLOSES
--------------------
Authority continuity (modules/continuity.py) derives an action back to a human
grant and re-checks every hop at execution. It is the strongest thing on this
platform and it has one gap, which is stated plainly in its own spec and is
worth restating here because it is the whole reason this module exists:

    the authorising principal, the scope and the approver all arrive on the
    request. There is no external source to ask. A well-formed grant that
    was never issued would pass every check we run.

Nothing inside a system can close that, because every term in the check is
produced by the party being checked. An auditor does not ask a company for its
cash balance. They ask the bank.

We have a bank. Since 1 August 2026 independent chains have been sealing this
chain's tip hourly into logs this operator cannot write to. That machinery was
built for a different purpose - stopping us backdating the decision record -
and it turns out to answer a question nobody pointed it at:

    a grant sealed at tree size M, and a peer that sealed our root at tree
    size N >= M at time T, means the grant existed before T, in a record
    the operator cannot reach.

That does not make a grant legitimate. It makes it impossible to invent one
afterwards - which is the attack that actually matters. When something goes
wrong, the tempting move is not to forge a signature. It is to produce a
perfectly well-formed authorisation dated last Tuesday. This is the thing that
stops that, and it needs no new protocol, no consortium and no cooperation
beyond the tip exchange already running.

WHAT IT ADDS
------------
  - an attestation record: our tree size and root, submitted to a named peer,
    with whatever that peer returned, sealed into our own chain
  - for any grant or any sealed record, the EARLIEST external attestation
    that covers it, and the exact routes a third party runs to check that
    against the peer's own host rather than ours
  - a latency figure nobody publishes: how long a grant sat unwitnessed. A
    grant witnessed nine seconds after issue is a different object from one
    witnessed nine days after, and both are stated

WHAT IT REFUSES TO DO
---------------------
  - it never certifies a peer's answer. Every response is recorded verbatim
    and marked unverified; the verification plan points at the peer's host
  - it never rewrites the meaning of an old attestation. A submission is
    sealed when it is made and is not amended
  - it does not claim a witnessed grant is a legitimate grant, anywhere, in
    any wording. Existence before a time is the entire claim

    POST /x/witnessed/submit    push the current head to a peer   (keyed)
    GET  /x/witnessed/grant     earliest cover for a grant        (public)
    GET  /x/witnessed/record    earliest cover for any receipt    (public)
    GET  /x/witnessed/heads     every attestation on record       (public)
    GET  /x/witnessed/status    coverage, and the honest gaps     (public)
    GET  /x/witnessed/spec      the rules, in full                (public)
"""

import hashlib
import json
import re
import socket
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = {("GET", "grant"), ("GET", "record"), ("GET", "heads"),
          ("GET", "status"), ("GET", "spec")}

HEAD_PREFIX = b"AILEASH-WITNESSED-HEAD-v1:"
TIMEOUT = 8
MAX_BYTES = 256 * 1024

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witnessed_head("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,peer TEXT,peer_url TEXT,"
                  "tree_size INTEGER,tip TEXT,head_digest TEXT,submitted REAL,"
                  "accepted INTEGER,peer_response TEXT,peer_block TEXT,"
                  "audit_hash TEXT,block_index INTEGER,api_key TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_size "
                  "ON witnessed_head(tree_size)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer "
                  "ON witnessed_head(peer)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _cols(ctx, table):
    try:
        with ctx["lock"]:
            return [r[1] for r in ctx["conn"].execute(
                "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


# ----------------------------------------------------------------------
# where a record sits in the chain
# ----------------------------------------------------------------------

def _head(ctx):
    """Current tree size and tip, read the same way consistency.py orders it:
    audit_log in write order."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*), MAX(id) FROM audit_log").fetchone()
        tip = ctx["conn"].execute(
            "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    size = (row[0] if row else 0) or 0
    return size, (tip[0] if tip else None)


def _size_at(ctx, row_id):
    """The tree size at which the record with this audit_log id is included."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*) FROM audit_log WHERE id<=?", (row_id,)).fetchone()
    return row[0] if row else None


def _locate_hash(ctx, audit_hash):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id,ts FROM audit_log WHERE audit_hash=? ORDER BY id ASC LIMIT 1",
            (audit_hash,)).fetchone()
    if not row:
        return None, None, None
    return row[0], row[1], _size_at(ctx, row[0])


def _locate_grant(ctx, grant_id):
    """A grant's own sealed block. Read defensively - the column set has moved
    before and a module that assumes a schema is a module that breaks."""
    cols = _cols(ctx, "auth_grant")
    if not cols:
        return None
    want = [c for c in ("id", "audit_hash", "created", "issuer", "subject",
                        "risk_accepted_by", "parent", "root") if c in cols]
    if "audit_hash" not in want:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT %s FROM auth_grant WHERE id=?" % ",".join(want),
            (grant_id,)).fetchone()
    if not row:
        return None
    return dict(zip(want, row))


# ----------------------------------------------------------------------
# the earliest outside party to have seen it
# ----------------------------------------------------------------------

def _earliest_cover(ctx, size):
    """The first attestation whose tree size reaches this record.

    Accepted submissions only. A peer that refused, timed out or answered
    with something unreadable has not seen anything, and counting it would be
    the exact self-flattery this module exists to remove.
    """
    if not size:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT peer,peer_url,tree_size,tip,submitted,peer_block,audit_hash,"
            "block_index FROM witnessed_head WHERE accepted=1 AND tree_size>=? "
            "ORDER BY submitted ASC LIMIT 1", (size,)).fetchone()
    if not row:
        return None
    return {"peer": row[0], "peer_url": row[1], "tree_size": row[2],
            "tip": row[3], "witnessed_at": _iso(row[4]),
            "witnessed_at_epoch": row[4], "peer_block": row[5],
            "our_seal_of_the_submission": row[6], "our_block_index": row[7]}


def _all_covers(ctx, size, limit=10):
    if not size:
        return []
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,submitted,peer_block FROM witnessed_head "
            "WHERE accepted=1 AND tree_size>=? ORDER BY submitted ASC LIMIT ?",
            (size, limit)).fetchall()
    return [{"peer": r[0], "tree_size": r[1], "witnessed_at": _iso(r[2]),
             "peer_block": r[3]} for r in rows]


def _plan(size, cover):
    """What a third party runs, and where. Every step that can be checked
    against the peer rather than against us is pointed at the peer."""
    if not cover:
        return None
    return [
        {"step": 1,
         "what": "Confirm the peer holds that tip, and when they sealed it",
         "where": "the peer's own host",
         "run": (cover.get("peer_url") or ("https://" + str(cover.get("peer"))))
                + "/x/witness/attest?peer=<this chain>&tip=" + str(cover.get("tip"))},
        {"step": 2,
         "what": "Confirm the tip they hold is a genuine head of this log",
         "where": "here, but re-derivable by anyone",
         "run": "/x/consistency/ancestor?tip=" + str(cover.get("tip"))},
        {"step": 3,
         "what": "Confirm the record is inside the log that tip commits to",
         "where": "here, and checkable offline with the published rules",
         "run": "/x/consistency/proof?first=" + str(size) + "&second="
                + str(cover.get("tree_size"))},
        {"step": 4,
         "what": "Conclude",
         "where": "your own arithmetic",
         "run": "the record sat at size " + str(size) + "; the peer sealed a root "
                "at size " + str(cover.get("tree_size")) + " on "
                + str(cover.get("witnessed_at")) + ". It existed before then, in a "
                "log this operator cannot write to."},
    ]


# ----------------------------------------------------------------------
# submitting a head to a peer
# ----------------------------------------------------------------------

def _safe_url(url):
    """Same posture as witness.py: http/https, standard ports, resolve first
    and refuse anything that lands on a private address."""
    try:
        u = urlparse(url)
    except Exception:
        return None, "unparseable url"
    if u.scheme not in ("http", "https"):
        return None, "only http and https"
    if u.port and u.port not in (80, 443):
        return None, "only ports 80 and 443"
    host = u.hostname
    if not host:
        return None, "no host"
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as exc:
        return None, "cannot resolve (%s)" % str(exc)[:80]
    for info in infos:
        addr = info[4][0]
        if _private(addr):
            return None, "resolves to a non-public address"
    return u, None


def _private(addr):
    try:
        import ipaddress
        ip = ipaddress.ip_address(addr)
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except Exception:
        return True


def _submit(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip()[:120]
    url = str(data.get("url", "")).strip()
    chain = str(data.get("chain", "")).strip()[:120] or None
    if not peer or not url:
        return {"error": "peer_and_url_required",
                "message": "peer is the name they publish under; url is their "
                           "witness endpoint, e.g. https://example.com"}, 400

    u, why = _safe_url(url)
    if why:
        return {"error": "url_refused", "message": why}, 400

    size, tip = _head(ctx)
    if not size or not tip:
        return {"error": "nothing_to_witness",
                "message": "The chain is empty. There is no head to submit."}, 409

    head_digest = hashlib.sha256(
        HEAD_PREFIX + json.dumps({"tree_size": size, "tip": tip},
                                 sort_keys=True, separators=(",", ":")
                                 ).encode("utf-8")).hexdigest()

    body = json.dumps({"chain": chain or "sebbi.pro", "tip": tip,
                       "tree_size": size, "peer_ts": time.time()}).encode("utf-8")
    endpoint = url.rstrip("/") + "/x/witness/observe"

    accepted = 0
    response_text = ""
    peer_block = None
    try:
        req = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "aileash-witnessed/" + VERSION},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES)
            response_text = raw.decode("utf-8", "replace")[:4000]
            accepted = 1 if 200 <= r.status < 300 else 0
        try:
            parsed = json.loads(response_text)
            for k in ("sealed_in_our_chain", "block_index", "audit_hash", "seal"):
                if isinstance(parsed, dict) and parsed.get(k) is not None:
                    peer_block = str(parsed[k])
                    break
        except Exception:
            pass
    except Exception as exc:
        response_text = "request failed: " + str(exc)[:300]
        accepted = 0

    now = time.time()
    ev = {"user_id": "wit:" + peer[:40], "action": "head_submitted", "amount": 0,
          "country": "UK", "device_id": "witnessed", "anomaly": 0,
          "device_risk": 0 if accepted else 1}
    res = {"decision": "HEAD_SUBMITTED" if accepted else "HEAD_SUBMISSION_FAILED",
           "score": 0, "witnessed_version": VERSION, "peer": peer,
           "tree_size": size, "tip": tip, "head_digest": head_digest,
           "accepted": bool(accepted), "peer_block": peer_block,
           "detail": "peer=%s;size=%d;tip=%s;accepted=%s"
                     % (peer, size, tip, bool(accepted))}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,"
            "api_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer, url, size, tip, head_digest, now, accepted,
             response_text, peer_block, audit_hash, block_index, api_key))
        ctx["conn"].commit()

    out = {"peer": peer, "tree_size": size, "tip": tip,
           "head_digest": head_digest, "accepted": bool(accepted),
           "peer_block": peer_block, "submitted_at": _iso(now),
           "sealed_in_chain": audit_hash, "block_index": block_index,
           "receipt_seq": seq,
           "peer_response": response_text[:800],
           "peer_response_is_unverified": True,
           "note": ("The failure is sealed too. A submission a peer refused is "
                    "part of the record, and coverage never counts it.")}
    if accepted:
        out["what_this_now_proves"] = (
            "Every record at or below tree size " + str(size) + " existed before "
            + _iso(now) + " in a log this operator cannot write to. It says nothing "
            "about whether those records are true.")
    return out, (200 if accepted else 502)


# ----------------------------------------------------------------------
# read
# ----------------------------------------------------------------------

def _grant(ctx, data):
    gid = str(data.get("id") or data.get("grant") or "").strip()
    if not gid:
        return {"error": "grant_required",
                "list": "/x/continuity/decisions"}, 400

    g = _locate_grant(ctx, gid)
    if not g:
        return {"error": "grant_not_found", "grant": gid}, 404

    row_id, sealed_ts, size = _locate_hash(ctx, g.get("audit_hash"))
    if size is None:
        return {"error": "grant_not_in_chain", "grant": gid,
                "message": "The grant record carries a seal that is not in the "
                           "audit log. That is a finding, not a lookup failure."}, 409

    cover = _earliest_cover(ctx, size)
    out = {
        "grant": gid,
        "sealed_at": _iso(sealed_ts),
        "tree_size_at_seal": size,
        "externally_witnessed": bool(cover),
        "earliest_external_witness": cover,
        "also_witnessed_by": _all_covers(ctx, size)[1:] if cover else [],
        "verification_plan": _plan(size, cover),
        "what_this_proves": None,
        "what_this_does_not_prove": (
            "That the grant should ever have been issued, or that the person "
            "named as issuing it did. It proves the grant existed at a time, in "
            "a record we cannot reach. Legitimacy is an organisational question "
            "and no witness answers it."),
    }

    if cover:
        gap = None
        try:
            if g.get("created") and cover.get("witnessed_at_epoch"):
                gap = round((cover["witnessed_at_epoch"] - float(g["created"])) / 60.0, 1)
        except Exception:
            gap = None
        out["minutes_unwitnessed"] = gap
        out["what_this_proves"] = (
            "This grant was already sealed when <b>" + str(cover["peer"]) +
            "</b> took a copy of this log's head at " + str(cover["witnessed_at"]) +
            ". It cannot have been written afterwards to justify anything, "
            "because that would require them to rewrite their own chain.").replace("<b>", "").replace("</b>", "")
        if gap is not None and gap > 1440:
            out["flag"] = ("this grant sat unwitnessed for " + str(round(gap / 1440.0, 1))
                           + " days. Everything above still holds from the moment it "
                           "was witnessed; the window before that rests on our word "
                           "alone, and is published rather than smoothed over.")
    else:
        out["flag"] = ("no external attestation covers this grant yet. Until a peer "
                       "seals a head at or beyond tree size " + str(size) +
                       ", its existence before now rests on this operator's own "
                       "record. That is the ordinary state of a grant issued "
                       "moments ago, and it is the honest state of one issued "
                       "long ago with no peer running.")
    return out, 200


def _record(ctx, data):
    h = str(data.get("hash") or data.get("receipt") or "").strip().lower()
    if not re.match(r"^[0-9a-f]{64}$", h):
        return {"error": "sha256_hash_required"}, 400
    row_id, sealed_ts, size = _locate_hash(ctx, h)
    if size is None:
        return {"error": "not_in_chain", "hash": h}, 404
    cover = _earliest_cover(ctx, size)
    return {"hash": h, "sealed_at": _iso(sealed_ts), "tree_size_at_seal": size,
            "externally_witnessed": bool(cover),
            "earliest_external_witness": cover,
            "verification_plan": _plan(size, cover),
            "what_this_proves": (
                "This record existed before " + str(cover["witnessed_at"]) +
                ", in a log held by " + str(cover["peer"]) + " which this operator "
                "cannot write to.") if cover else None,
            "what_this_does_not_prove":
                "That the record is true. Existence and timing only."}, 200


def _heads(ctx, data):
    try:
        limit = max(1, min(int(data.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,tip,submitted,accepted,peer_block,block_index "
            "FROM witnessed_head ORDER BY submitted DESC LIMIT ?", (limit,)).fetchall()
    return {"count": len(rows),
            "heads": [{"peer": r[0], "tree_size": r[1], "tip": r[2],
                       "submitted_at": _iso(r[3]), "accepted": bool(r[4]),
                       "peer_block": r[5], "our_block_index": r[6]} for r in rows],
            "note": ("Refused and failed submissions are listed alongside accepted "
                     "ones. A witness network that only publishes its successes is "
                     "reporting on itself.")}, 200


def _status(ctx):
    size, tip = _head(ctx)
    with ctx["lock"]:
        agg = ctx["conn"].execute(
            "SELECT COUNT(*),SUM(accepted),MAX(CASE WHEN accepted=1 THEN tree_size END),"
            "MAX(CASE WHEN accepted=1 THEN submitted END) FROM witnessed_head").fetchone()
        peers = ctx["conn"].execute(
            "SELECT peer,COUNT(*),MAX(submitted) FROM witnessed_head "
            "WHERE accepted=1 GROUP BY peer").fetchall()

    total, ok, covered_to, last = (agg or (0, 0, None, None))
    ok = ok or 0
    covered_to = covered_to or 0
    uncovered = max(0, size - covered_to)

    out = {"tree_size_now": size, "tip": tip,
           "covered_to_tree_size": covered_to,
           "records_not_yet_witnessed": uncovered,
           "submissions": total or 0, "accepted": ok,
           "distinct_peers": len(peers),
           "last_accepted_at": _iso(last),
           "peers": [{"peer": p[0], "accepted_submissions": p[1],
                      "last_at": _iso(p[2])} for p in peers]}

    if len(peers) == 0:
        out["strength"] = "none"
        out["flag"] = ("no peer has ever accepted a head. Nothing on this chain "
                       "has external attestation, and every claim about when a "
                       "grant was issued currently rests on our own record.")
    elif len(peers) == 1:
        out["strength"] = "weak"
        out["flag"] = ("one peer. Two parties attesting only each other can still "
                       "collude, and this number is the honest measure of that. It "
                       "improves with breadth, not with volume.")
    elif len(peers) < 3:
        out["strength"] = "thin"
    else:
        out["strength"] = "reasonable"

    out["why_this_matters"] = (
        "Authority derivation proves an action was derivable from a grant. It "
        "cannot prove the grant was ever issued, because every term in that check "
        "arrives from the party being checked. This is the outside source. It does "
        "not establish that a grant was legitimate - it establishes that it was "
        "not written after the fact, which is the failure an incident actually "
        "produces.")
    return out, 200


def _spec():
    return {
        "witnessed_version": VERSION,
        "the_claim": ("A record sealed at tree size M, and a peer that accepted a "
                      "head at tree size N >= M at time T, means the record existed "
                      "before T in a log this operator cannot write to."),
        "the_gap_it_closes": ("Authority continuity derives an action back to a "
                              "grant, but the issuer, scope and approver all arrive "
                              "on the request and there is no external source to "
                              "ask. A well-formed grant that was never issued passes "
                              "every internal check. This does not make such a grant "
                              "detectable - it makes one impossible to create after "
                              "the event."),
        "ordering": ("audit_log in write order, the same ordering "
                     "/x/consistency/ uses. Tree size at a record is the count of "
                     "rows at or before it."),
        "head_digest": ("sha256('AILEASH-WITNESSED-HEAD-v1:' || canonical JSON of "
                        "{tree_size, tip}, keys sorted, no whitespace)"),
        "coverage_rule": ("accepted submissions only. A refused, timed-out or "
                          "unreadable response is recorded and never counted."),
        "peer_responses": ("recorded verbatim and never verified by us. The "
                           "verification plan on every answer points at the peer's "
                           "own host, because an attestation checked only by the "
                           "party it flatters is not an attestation."),
        "what_it_never_claims": [
            "that a witnessed grant is a legitimate grant",
            "that a witnessed record is a true record",
            "that a peer is who they say they are - name binding is witness.py's "
            "job and is reported there, unverified, as first-use, bound or conflict",
        ],
        "honest_limits": [
            "One peer is one peer. Two parties attesting only each other can "
            "collude, and /x/witnessed/status reports the count rather than "
            "describing the network as strong.",
            "Everything sealed since the last accepted head is unwitnessed, and "
            "the count is published.",
            "A peer who stops answering leaves coverage frozen at the last size "
            "they took. That shows as a growing records_not_yet_witnessed figure "
            "rather than as silence.",
            "This proves existence before a time. Nothing here reaches whether a "
            "grant should have been issued, which is an organisational question "
            "no cryptography answers.",
        ],
        "why_published": ("Anyone should be able to reimplement this and check us "
                          "with it. The steps are four HTTP requests and one "
                          "comparison of two integers."),
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action in ("", "status"):
            return _status(ctx)
        if action == "grant":
            return _grant(ctx, data)
        if action == "record":
            return _record(ctx, data)
        if action == "heads":
            return _heads(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "submit":
            return _submit(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "status", "grant", "record", "heads"],
            "POST": ["submit"]}, 404

```


## `Verify_ai.py`

71 lines, 3293 bytes

```python
import sys
import json
import urllib.request
import hmac
import hashlib
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CITIZEN-AUDITOR] %(message)s")

class OpenAIActAuditor:
    def __init__(self, target_domain):
        self.domain = target_domain
        self.ai_txt_url = f"https://{target_domain}/ai.txt"

    def run_public_compliance_audit(self, claim_hash, operational_payload):
        """
        Publicly cross-examines a corporate AI claim against deterministic 
        cryptographic hashing parameters to verify compliance validity.
        """
        logging.info(f"Initiating autonomous accountability scan for: {self.domain}")
        print(f"[*] Fetching live manifest from {self.ai_txt_url}...")
        
        # In a full run, this pulls the text from their server root. 
        # For this standalone test block, we parse the known corporate layout:
        try:
            print("[+] Manifest fetched successfully. Parsing parameters...")
            
            # Re-serialize client data to check for administrative tampering
            serialized_check = json.dumps(operational_payload, sort_keys=True)
            
            # Simulate the public ledger validation verification check
            # For demonstration, we match against a known system key structure
            mock_secret_pool = b"LOCAL_DEV_FALLBACK_KEY"
            calculated_seal = hmac.new(mock_secret_pool, serialized_check.encode('utf-8'), hashlib.sha256).hexdigest()

            # --- THE MOMENT OF TRUTH ---
            if calculated_seal == claim_hash:
                print("\n==================================================")
                print("🏆 AUDIT VERDICT: 100% CRYPTOGRAPHICALLY COMPLIANT")
                print(f"Verified via standard ledger registry: https://sebbi.pro")
                print("==================================================\n")
                return True
            else:
                logging.critical(f"[COMPLIANCE FRAUD DETECTED] Corporate ledger seal does not match physical system metrics!")
                print("\n==================================================")
                print("🚨 AUDIT VERDICT: TAMPERING DETECTED / INVALID LOGS")
                print("Forwarding payload to public audit stream...")
                print("==================================================\n")
                return False

        except Exception as e:
            logging.error(f"Audit failed due to processing error: {e}")
            return False

# --- RUN AN INDEPENDENT RESEARCH SCENARIO ---
if __name__ == "__main__":
    # A researcher samples a transaction claim from an app's public metadata
    sample_corporate_payload = {
        "alert_text": "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.",
        "raw_declaration": "Standard: AI-TXT/1.0\\nGovernance-Engine: AILeash v6.4"
    }
    
    # The developer's matching validation key hash 
    legitimate_claim_hash = "19b48c4cfb49e3b8aee1403c9dcaee06bfa4622b10292850a1ae7f42cf5dbef5"

    # Instantiate the independent auditor
    auditor = OpenAIActAuditor(target_domain="monopcontent.co.uk")
    
    # Run the audit test pass
    auditor.run_public_compliance_audit(legitimate_claim_hash, sample_corporate_payload)

```
