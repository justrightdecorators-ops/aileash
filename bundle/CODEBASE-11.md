# Codebase — part 11 of 30

Contains:
- `modules/register.py`
- `modules/replay.py`
- `modules/roster.py`
- `modules/router.py`


## `modules/register.py`

1287 lines, 50021 bytes

```python
"""
modules/register.py  v1.0.0  —  The Safe AI Registry

What makes this different from every other registry, trust mark and
certification list:

  Ordinary registries are mutable databases. The operator can insert an
  entry, back-date it, quietly delist someone, or revoke a seal and leave
  no trace. You must trust the registrar absolutely.

  This one publishes proofs about its own behaviour:

    * ABSENCE   — prove a domain was NOT listed on a given date.
                  Not "we have no record": a sorted-tree proof showing two
                  adjacent leaves with consecutive indices, so nothing can
                  sit between them.

    * APPEND-ONLY — RFC 6962 consistency proof that the register at any
                  past size is a prefix of the register now. A back-dated
                  listing is arithmetically impossible to hide, and the
                  proof verifies with any standard Certificate Transparency
                  verifier, not one of ours.

    * REVOCATION — a delisted entry does not vanish. The revocation is
                  sealed and the history stays readable. "Listed from D1,
                  revoked D2, reason R" is permanent.

  The registrar is auditable against the registrar. That is the product.

CONSENT
  No domain is ever listed because the operator typed it in. A domain
  lists itself by proving it controls the domain:

    1. POST /x/register/challenge {"domain": "example.com"}
         -> returns a one-time token, sealed.
    2. The domain serves that token at
         https://example.com/.well-known/aileash-register.txt
       (or puts a `Register-Token:` line in its ai.txt).
    3. POST /x/register/claim {"domain": "example.com"}
         -> we fetch, verify the token, run the checks, seal the result
            and list it.

  Peers on the witness network are not auto-listed. A listing they
  claimed themselves is better evidence than one we granted them.

VOCABULARY  (deliberately not "compliant", "covered" or "certified")
    unverified    claimed, checks not yet run
    checks-passed every check in the suite returned pass, on the date shown
    checks-failed at least one check did not pass
    stale         last successful check is older than STALE_AFTER_DAYS
    withdrawn     the domain asked to be removed
    revoked       the operator removed it; reason sealed

Module contract:
    handle(method, action, data, api_key, ctx) -> (dict, status)
    PUBLIC is a set of (METHOD, action) tuples
    ctx exposes conn, lock, seal
    every sealed event carries a user_id
    no seal is wrapped in a bare except
"""

import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.0.0"
SUITE_VERSION = "oaas-checks-1"

# ---------------------------------------------------------------- constants

STALE_AFTER_DAYS = 90
CHALLENGE_TTL_SECONDS = 86400
MAX_FETCH_BYTES = 512 * 1024
FETCH_TIMEOUT = 8
WELL_KNOWN_PATH = "/.well-known/aileash-register.txt"
AI_TXT_PATH = "/ai.txt"
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

STATUS_UNVERIFIED = "unverified"
STATUS_PASSED = "checks-passed"
STATUS_FAILED = "checks-failed"
STATUS_STALE = "stale"
STATUS_WITHDRAWN = "withdrawn"
STATUS_REVOKED = "revoked"

LIVE_STATUSES = (STATUS_UNVERIFIED, STATUS_PASSED, STATUS_FAILED, STATUS_STALE)

# Domain-separation prefixes. Two different trees answer two different
# questions and their roots deliberately never match.
LEAF_PREFIX = b"\x00"          # RFC 6962 ordered tree, over events
NODE_PREFIX = b"\x01"
SORTED_LEAF = b"AILEASH-REGISTER-LEAF-v1\x00"    # sorted tree, over domains
SORTED_NODE = b"AILEASH-REGISTER-NODE-v1\x00"

VOCABULARY = {
    STATUS_UNVERIFIED: "The domain proved control and is listed. The check suite has not been run against it yet.",
    STATUS_PASSED: "Every check in suite %s returned pass on the date shown. This describes what the checks observed on that date and nothing else." % SUITE_VERSION,
    STATUS_FAILED: "At least one check did not pass. The failing check names are published.",
    STATUS_STALE: "The last successful check is more than %d days old. Nothing was withdrawn; the evidence simply aged." % STALE_AFTER_DAYS,
    STATUS_WITHDRAWN: "The domain asked to be removed. The listing history remains readable.",
    STATUS_REVOKED: "The operator removed the listing. The reason is sealed alongside it and the history remains readable.",
}

WHAT_THIS_IS_NOT = [
    "Not a certification. Nobody has been certified by anyone.",
    "Not a statement that any law applies to a listed domain, or that a listed domain satisfies it. Whether a regulation applies to an organisation is a question for that organisation's own advisers.",
    "Not an audit. No third party has audited this registry or any domain on it.",
    "Not a claim about anything a domain did not seal. A check observes what is served at a URL at a moment in time.",
]

MESSAGES = {
    "domain_required": "domain is required",
    "bad_domain": "domain must be a bare hostname, e.g. example.com — no scheme, no path",
    "no_challenge": "no live challenge for this domain. POST /x/register/challenge first.",
    "challenge_expired": "challenge expired. Request a new one.",
    "token_not_found": "the token was not served at either location",
    "not_listed": "this domain has no entry in the register",
    "already_final": "this entry is withdrawn or revoked and cannot be changed",
    "no_checkpoint": "no checkpoint has been sealed at or before that time",
    "seal_failed": "the register could not seal this event, so nothing was written. Retry.",
}

PUBLIC = {
    ("GET", "spec"),
    ("GET", "list"),
    ("GET", "entry"),
    ("GET", "history"),
    ("GET", "absence"),
    ("GET", "consistency"),
    ("GET", "inclusion"),
    ("GET", "checkpoints"),
    ("GET", "roots"),
    ("GET", "vocabulary"),
    ("POST", "challenge"),
    ("POST", "claim"),
    ("POST", "recheck"),
    ("POST", "withdraw"),
}


# ---------------------------------------------------------------- utilities

def _now():
    return time.time()


def _iso(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_when(s):
    """Accept an ISO date, an ISO datetime or an epoch. Return epoch seconds."""
    if s is None or s == "":
        return None
    s = str(s).strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    t = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            if fmt is None:
                d = datetime.fromisoformat(t)
            else:
                d = datetime.strptime(t, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.timestamp()
        except (TypeError, ValueError):
            continue
    return None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _clean_domain(raw):
    if not raw:
        return None
    d = str(raw).strip().lower()
    if "://" in d:
        d = urllib.parse.urlsplit(d).netloc or d
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if d.startswith("www."):
        d = d[4:]
    if "@" in d or ":" in d:
        return None
    if not DOMAIN_RE.match(d):
        return None
    return d


# ------------------------------------------------------------------- fetch
# Same posture as witness.py: http/https only, ports 80/443, resolve first,
# reject non-public addresses, no redirects, hard timeout, size cap.

def _is_public_addr(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return False, "dns_failed: %s" % e
    if not infos:
        return False, "dns_empty"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, "unparseable_address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, "non_public_address"
    return True, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url):
    """Return (ok, body_text_or_none, note_dict)."""
    parts = urllib.parse.urlsplit(url)
    note = {"url": url, "fetched_at": _iso(_now())}
    if parts.scheme not in ("http", "https"):
        note["error"] = "scheme_not_allowed"
        return False, None, note
    if parts.port not in (None, 80, 443):
        note["error"] = "port_not_allowed"
        return False, None, note
    host = parts.hostname
    if not host:
        note["error"] = "no_host"
        return False, None, note
    ok, why = _is_public_addr(host)
    if not ok:
        note["error"] = why
        return False, None, note

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={
        "User-Agent": "AILeash-Register/%s (+https://sebbi.pro/x/register/spec)" % VERSION,
        "Accept": "text/plain, application/json, */*",
    })
    started = time.time()
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            note["http_status"] = resp.getcode()
            raw = resp.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as e:
        note["http_status"] = e.code
        note["error"] = "http_%s" % e.code
        note["took_ms"] = int((time.time() - started) * 1000)
        return False, None, note
    except Exception as e:
        note["error"] = "fetch_failed: %s" % type(e).__name__
        note["took_ms"] = int((time.time() - started) * 1000)
        return False, None, note

    note["took_ms"] = int((time.time() - started) * 1000)
    if len(raw) > MAX_FETCH_BYTES:
        note["error"] = "too_large"
        return False, None, note
    note["bytes"] = len(raw)
    note["body_sha256"] = _sha(raw)
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:
        note["error"] = "undecodable"
        return False, None, note
    return True, text, note


# ------------------------------------------------------------------ merkle

def _ct_leaf(data_bytes):
    return hashlib.sha256(LEAF_PREFIX + data_bytes).digest()


def _ct_node(l, r):
    return hashlib.sha256(NODE_PREFIX + l + r).digest()


def _ct_root(leaves):
    """RFC 6962 root over an ordered list of leaf digests (bytes)."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return _ct_node(_ct_root(leaves[:k]), _ct_root(leaves[k:]))


def _ct_inclusion(leaves, index):
    """RFC 6962 inclusion proof for leaves[index]. Returns list of hex."""
    def walk(sub, i):
        if len(sub) <= 1:
            return []
        k = 1
        while k * 2 < len(sub):
            k *= 2
        if i < k:
            return walk(sub[:k], i) + [_ct_root(sub[k:])]
        return walk(sub[k:], i - k) + [_ct_root(sub[:k])]
    return [h.hex() for h in walk(leaves, index)]


def _ct_consistency(leaves, m):
    """RFC 6962 consistency proof between size m and size len(leaves)."""
    n = len(leaves)
    if m <= 0 or m > n:
        return None

    def subproof(m_, sub, is_complete):
        if m_ == len(sub):
            return [] if is_complete else [_ct_root(sub)]
        k = 1
        while k * 2 < len(sub):
            k *= 2
        if m_ <= k:
            return subproof(m_, sub[:k], is_complete) + [_ct_root(sub[k:])]
        return subproof(m_ - k, sub[k:], False) + [_ct_root(sub[:k])]

    return [h.hex() for h in subproof(m, leaves, True)]


def _sorted_leaf(value):
    return hashlib.sha256(SORTED_LEAF + value.encode("utf-8")).digest()


def _sorted_root(leaves):
    """Sorted tree. Odd nodes are promoted, never self-paired."""
    if not leaves:
        return hashlib.sha256(SORTED_LEAF + b"EMPTY").digest()
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        i = 0
        while i + 1 < len(level):
            nxt.append(hashlib.sha256(SORTED_NODE + level[i] + level[i + 1]).digest())
            i += 2
        if i < len(level):
            nxt.append(level[i])
        level = nxt
    return level[0]


def _sorted_path(leaves, index):
    """Audit path in the promoted-odd sorted tree."""
    path = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        nxt = []
        i = 0
        new_idx = idx
        while i + 1 < len(level):
            pair = (level[i], level[i + 1])
            if idx == i:
                path.append({"side": "right", "hash": pair[1].hex()})
                new_idx = len(nxt)
            elif idx == i + 1:
                path.append({"side": "left", "hash": pair[0].hex()})
                new_idx = len(nxt)
            nxt.append(hashlib.sha256(SORTED_NODE + pair[0] + pair[1]).digest())
            i += 2
        if i < len(level):
            if idx == i:
                new_idx = len(nxt)
            nxt.append(level[i])
        level = nxt
        idx = new_idx
    return path


# ------------------------------------------------------------------ schema

def _ensure(ctx):
    conn = ctx["conn"]
    with ctx["lock"]:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS register_entry (
            domain        TEXT PRIMARY KEY,
            status        TEXT NOT NULL,
            first_listed  REAL NOT NULL,
            last_event    REAL NOT NULL,
            last_checked  REAL,
            last_pass     REAL,
            checks_json   TEXT,
            contact       TEXT,
            claim_method  TEXT,
            reason        TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS register_event (
            seq        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         REAL NOT NULL,
            domain     TEXT NOT NULL,
            kind       TEXT NOT NULL,
            detail     TEXT NOT NULL,
            leaf_hex   TEXT NOT NULL,
            audit_hash TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_event_domain ON register_event(domain, seq)")
        c.execute("""CREATE TABLE IF NOT EXISTS register_checkpoint (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            REAL NOT NULL,
            tree_size     INTEGER NOT NULL,
            event_root    TEXT NOT NULL,
            domain_root   TEXT NOT NULL,
            domain_count  INTEGER NOT NULL,
            domains_json  TEXT NOT NULL,
            audit_hash    TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_checkpoint_ts ON register_checkpoint(ts)")
        c.execute("""CREATE TABLE IF NOT EXISTS register_challenge (
            domain  TEXT PRIMARY KEY,
            token   TEXT NOT NULL,
            issued  REAL NOT NULL
        )""")
        conn.commit()


def _event_leaves(ctx):
    """Ordered list of leaf digests for the whole event log."""
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT leaf_hex FROM register_event ORDER BY seq ASC").fetchall()
    return [bytes.fromhex(r[0]) for r in rows]


def _live_domains(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain FROM register_entry WHERE status IN (?,?,?,?)",
            LIVE_STATUSES).fetchall()
    return sorted(r[0] for r in rows)


def _seal_event(ctx, domain, kind, detail):
    """Seal, then write. A failed seal writes nothing and raises."""
    ts = _now()
    leaf_payload = _canon({"v": 1, "ts": round(ts, 3), "domain": domain,
                           "kind": kind, "detail": detail}).encode("utf-8")
    leaf_hex = _ct_leaf(leaf_payload).hex()

    event = {
        "user_id": "register:%s" % domain,
        "type": "register_event",
        "domain": domain,
        "kind": kind,
        "leaf": leaf_hex,
        "suite": SUITE_VERSION,
        "detail": detail,
    }
    result = ctx["seal"](event)
    audit_hash = None
    if isinstance(result, dict):
        audit_hash = result.get("audit_hash") or result.get("hash")
    elif isinstance(result, str):
        audit_hash = result
    if not audit_hash:
        raise RuntimeError("seal returned no audit_hash")

    with ctx["lock"]:
        cur = ctx["conn"].execute(
            "INSERT INTO register_event (ts, domain, kind, detail, leaf_hex, audit_hash)"
            " VALUES (?,?,?,?,?,?)",
            (ts, domain, kind, _canon(detail), leaf_hex, audit_hash))
        seq = cur.lastrowid
        ctx["conn"].commit()

    return {"seq": seq, "ts": ts, "at": _iso(ts), "leaf": leaf_hex,
            "audit_hash": audit_hash, "kind": kind}


def _seal_checkpoint(ctx):
    """Seal the current state: ordered event root + sorted domain root."""
    leaves = _event_leaves(ctx)
    domains = _live_domains(ctx)
    event_root = _ct_root(leaves).hex()
    domain_root = _sorted_root([_sorted_leaf(d) for d in domains]).hex()
    ts = _now()

    event = {
        "user_id": "register:checkpoint",
        "type": "register_checkpoint",
        "tree_size": len(leaves),
        "event_root": event_root,
        "domain_root": domain_root,
        "domain_count": len(domains),
        "suite": SUITE_VERSION,
    }
    result = ctx["seal"](event)
    audit_hash = None
    if isinstance(result, dict):
        audit_hash = result.get("audit_hash") or result.get("hash")
    elif isinstance(result, str):
        audit_hash = result
    if not audit_hash:
        raise RuntimeError("seal returned no audit_hash")

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO register_checkpoint (ts, tree_size, event_root, domain_root,"
            " domain_count, domains_json, audit_hash) VALUES (?,?,?,?,?,?,?)",
            (ts, len(leaves), event_root, domain_root, len(domains),
             _canon(domains), audit_hash))
        ctx["conn"].commit()

    return {"at": _iso(ts), "tree_size": len(leaves), "event_root": event_root,
            "domain_root": domain_root, "domain_count": len(domains),
            "audit_hash": audit_hash}


# ------------------------------------------------------------- check suite

def _run_checks(domain):
    """Observe what the domain serves. Every check names what it looked at."""
    checks = []
    base = "https://%s" % domain

    ok, body, note = _fetch(base + AI_TXT_PATH)
    checks.append({
        "id": "ai_txt_reachable",
        "asks": "Does %s%s return a document over https?" % (domain, AI_TXT_PATH),
        "pass": bool(ok),
        "observed": note,
    })

    fields = {}
    if ok and body:
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            fields[k.strip().lower()] = v.strip()

    required = ["chain-tip-url", "verifier", "contact"]
    missing = [f for f in required if f not in fields]
    checks.append({
        "id": "ai_txt_declares_required_fields",
        "asks": "Does the document declare %s?" % ", ".join(required),
        "pass": ok and not missing,
        "observed": {"present": sorted(fields.keys()), "missing": missing},
    })

    tip_url = fields.get("chain-tip-url")
    tip_value = None
    if tip_url:
        tok, tbody, tnote = _fetch(tip_url)
        parsed_tip = None
        if tok and tbody:
            try:
                obj = json.loads(tbody)
                for key in ("tip", "tip_sha256", "chain_tip", "head", "root",
                            "current_tip", "latest", "hash"):
                    if isinstance(obj.get(key), str):
                        parsed_tip = obj[key]
                        break
            except Exception:
                parsed_tip = None
        tip_value = parsed_tip
        checks.append({
            "id": "chain_tip_served",
            "asks": "Does the declared chain-tip-url return JSON carrying a tip value?",
            "pass": bool(parsed_tip),
            "observed": dict(tnote, tip_field_found=bool(parsed_tip)),
        })
        checks.append({
            "id": "chain_tip_is_sha256",
            "asks": "Is the served tip a 64-character hex digest?",
            "pass": bool(parsed_tip) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", parsed_tip or "")),
            "observed": {"tip": parsed_tip},
        })
    else:
        checks.append({
            "id": "chain_tip_served",
            "asks": "Does the declared chain-tip-url return JSON carrying a tip value?",
            "pass": False,
            "observed": {"error": "no chain-tip-url declared"},
        })
        checks.append({
            "id": "chain_tip_is_sha256",
            "asks": "Is the served tip a 64-character hex digest?",
            "pass": False,
            "observed": {"error": "no tip to inspect"},
        })

    verifier = fields.get("verifier")
    checks.append({
        "id": "verifier_named",
        "asks": "Does the document name instructions or a tool a third party can use to check the chain themselves?",
        "pass": bool(verifier),
        "observed": {"verifier": verifier},
    })

    passed = all(c["pass"] for c in checks)
    return {
        "suite": SUITE_VERSION,
        "ran_at": _iso(_now()),
        "all_passed": passed,
        "failed": [c["id"] for c in checks if not c["pass"]],
        "checks": checks,
        "tip_observed": tip_value,
        "declared": fields,
    }


# ------------------------------------------------------------------ actions

def _spec(ctx):
    return {
        "module": "register",
        "version": VERSION,
        "suite_version": SUITE_VERSION,
        "what_this_is":
            "A registry that publishes proofs about its own behaviour. Absence proofs "
            "show a domain was not listed on a date. RFC 6962 consistency proofs show "
            "no entry was inserted behind an earlier position. Revocations are sealed "
            "rather than deleted, so a removed listing stays readable.",
        "why_that_matters":
            "Every other registry is a mutable database whose operator can add, "
            "back-date or quietly delete entries. Trusting the list means trusting the "
            "registrar. This one is checkable against its own operator.",
        "what_this_is_not": WHAT_THIS_IS_NOT,
        "status_vocabulary": VOCABULARY,
        "how_to_get_listed": [
            "1. POST /x/register/challenge with {\"domain\": \"example.com\"} — returns a one-time token.",
            "2. Serve that token at https://example.com%s, or add a `Register-Token: <token>` line to https://example.com%s" % (WELL_KNOWN_PATH, AI_TXT_PATH),
            "3. POST /x/register/claim with {\"domain\": \"example.com\"} — we fetch, verify, run the checks and seal the result.",
            "Nobody is listed by the operator. A domain lists itself by proving it controls the domain.",
        ],
        "checks_run": [
            "ai_txt_reachable", "ai_txt_declares_required_fields",
            "chain_tip_served", "chain_tip_is_sha256", "verifier_named",
        ],
        "trees": {
            "event_tree": "RFC 6962 ordered tree over every register event in write order. Answers append-only. Verifies with any standard Certificate Transparency verifier.",
            "domain_tree": "Sorted tree over the domains listed at a checkpoint, odd nodes promoted, domain-separated prefixes. Answers absence.",
            "note": "The two roots answer different questions and deliberately never match.",
        },
        "stale_after_days": STALE_AFTER_DAYS,
        "challenge_ttl_seconds": CHALLENGE_TTL_SECONDS,
        "routes": {
            "public": sorted("%s /x/register/%s" % (m, a) for m, a in PUBLIC),
            "keyed": ["POST /x/register/recheck-all", "POST /x/register/checkpoint",
                      "POST /x/register/revoke"],
        },
        "honest_limits": [
            "A check observes what a URL served at a moment in time. It cannot know what a domain did not seal.",
            "Domain control proves control of the domain, not the truth of anything the domain declares.",
            "Absence proofs are only as good as the checkpoint they are made against. A period with no checkpoint has nothing to prove absence from.",
            "Nobody can be forced to keep publishing. A listing goes stale when the evidence ages, and that is the honest outcome rather than a failure of the register.",
        ],
    }, 200


def _challenge(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not data.get("domain"):
        return {"error": MESSAGES["domain_required"]}, 400
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
    if row and row[0] in (STATUS_REVOKED,):
        return {"error": MESSAGES["already_final"], "domain": domain,
                "status": row[0]}, 409

    token = "aileash-register-" + secrets.token_hex(16)
    ts = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO register_challenge (domain, token, issued) VALUES (?,?,?)"
            " ON CONFLICT(domain) DO UPDATE SET token=excluded.token, issued=excluded.issued",
            (domain, token, ts))
        ctx["conn"].commit()

    try:
        sealed = _seal_event(ctx, domain, "challenge_issued",
                             {"token_sha256": _sha(token.encode())})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    return {
        "ok": True,
        "domain": domain,
        "token": token,
        "expires_at": _iso(ts + CHALLENGE_TTL_SECONDS),
        "serve_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                     "or a `Register-Token: %s` line in https://%s%s" % (token, domain, AI_TXT_PATH)],
        "then": "POST /x/register/claim {\"domain\": \"%s\"}" % domain,
        "sealed": sealed,
        "note": "The token itself is not sealed — only its digest, so the challenge cannot be replayed from the public chain.",
    }, 200


def _verify_token(domain, token):
    ok, body, note = _fetch("https://%s%s" % (domain, WELL_KNOWN_PATH))
    if ok and body and token in body:
        return True, {"method": "well-known", "observed": note}
    ok2, body2, note2 = _fetch("https://%s%s" % (domain, AI_TXT_PATH))
    if ok2 and body2:
        for line in body2.splitlines():
            if line.strip().lower().startswith("register-token:") and token in line:
                return True, {"method": "ai.txt", "observed": note2}
    return False, {"method": None, "well_known": note, "ai_txt": note2}


def _claim(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT token, issued FROM register_challenge WHERE domain=?", (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["no_challenge"], "domain": domain}, 404
    token, issued = row[0], row[1]
    if _now() - issued > CHALLENGE_TTL_SECONDS:
        return {"error": MESSAGES["challenge_expired"], "domain": domain}, 410

    verified, evidence = _verify_token(domain, token)
    if not verified:
        try:
            _seal_event(ctx, domain, "claim_refused", {"reason": "token_not_found",
                                                       "evidence": evidence})
        except Exception as e:
            return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500
        return {"ok": False, "domain": domain, "error": MESSAGES["token_not_found"],
                "looked_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                              "https://%s%s" % (domain, AI_TXT_PATH)],
                "evidence": evidence,
                "note": "The refusal is sealed. Fix the token and claim again."}, 400

    checks = _run_checks(domain)
    status = STATUS_PASSED if checks["all_passed"] else STATUS_FAILED
    contact = checks["declared"].get("contact")
    ts = _now()

    try:
        sealed = _seal_event(ctx, domain, "listed", {
            "claim_method": evidence.get("method"),
            "status": status,
            "suite": SUITE_VERSION,
            "failed": checks["failed"],
            "tip_observed": checks["tip_observed"],
        })
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        existing = ctx["conn"].execute(
            "SELECT first_listed FROM register_entry WHERE domain=?", (domain,)).fetchone()
        first = existing[0] if existing else ts
        ctx["conn"].execute(
            "INSERT INTO register_entry (domain, status, first_listed, last_event,"
            " last_checked, last_pass, checks_json, contact, claim_method, reason)"
            " VALUES (?,?,?,?,?,?,?,?,?,NULL)"
            " ON CONFLICT(domain) DO UPDATE SET status=excluded.status,"
            " last_event=excluded.last_event, last_checked=excluded.last_checked,"
            " last_pass=excluded.last_pass, checks_json=excluded.checks_json,"
            " contact=excluded.contact, claim_method=excluded.claim_method, reason=NULL",
            (domain, status, first, ts, ts,
             ts if checks["all_passed"] else None,
             _canon(checks), contact, evidence.get("method")))
        ctx["conn"].execute("DELETE FROM register_challenge WHERE domain=?", (domain,))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": status,
            "status_means": VOCABULARY[status],
            "claim_method": evidence.get("method"),
            "checks": checks, "sealed": sealed, "checkpoint": cp,
            "entry_url": "/x/register/entry?domain=%s" % domain}, 200


def _recheck(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status, first_listed FROM register_entry WHERE domain=?",
            (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404
    if row[0] in (STATUS_WITHDRAWN, STATUS_REVOKED):
        return {"error": MESSAGES["already_final"], "domain": domain, "status": row[0]}, 409

    checks = _run_checks(domain)
    status = STATUS_PASSED if checks["all_passed"] else STATUS_FAILED
    ts = _now()

    try:
        sealed = _seal_event(ctx, domain, "rechecked", {
            "status": status, "suite": SUITE_VERSION, "failed": checks["failed"],
            "tip_observed": checks["tip_observed"],
        })
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, last_checked=?,"
            " last_pass=COALESCE(?, last_pass), checks_json=? WHERE domain=?",
            (status, ts, ts, ts if checks["all_passed"] else None,
             _canon(checks), domain))
        ctx["conn"].commit()

    return {"ok": True, "domain": domain, "status": status,
            "status_means": VOCABULARY[status], "checks": checks, "sealed": sealed}, 200


def _withdraw(ctx, data):
    """A domain removes itself. Proved the same way it listed itself."""
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
        ch = ctx["conn"].execute(
            "SELECT token, issued FROM register_challenge WHERE domain=?", (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404
    if not ch:
        return {"error": MESSAGES["no_challenge"], "domain": domain,
                "note": "Withdrawal is proved the same way listing is. Request a challenge, serve the token, then withdraw."}, 404
    if _now() - ch[1] > CHALLENGE_TTL_SECONDS:
        return {"error": MESSAGES["challenge_expired"]}, 410

    verified, evidence = _verify_token(domain, ch[0])
    if not verified:
        return {"ok": False, "error": MESSAGES["token_not_found"], "evidence": evidence}, 400

    ts = _now()
    try:
        sealed = _seal_event(ctx, domain, "withdrawn",
                             {"by": "domain", "method": evidence.get("method")})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, reason=? WHERE domain=?",
            (STATUS_WITHDRAWN, ts, "withdrawn by domain", domain))
        ctx["conn"].execute("DELETE FROM register_challenge WHERE domain=?", (domain,))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": STATUS_WITHDRAWN,
            "status_means": VOCABULARY[STATUS_WITHDRAWN],
            "sealed": sealed, "checkpoint": cp,
            "note": "The listing history remains readable at /x/register/history?domain=%s" % domain}, 200


def _revoke(ctx, data):
    domain = _clean_domain(data.get("domain"))
    reason = (data.get("reason") or "").strip()
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    if not reason:
        return {"error": "reason is required — a revocation with no sealed reason is exactly what this register exists to prevent"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404

    ts = _now()
    try:
        sealed = _seal_event(ctx, domain, "revoked", {"by": "operator", "reason": reason})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, reason=? WHERE domain=?",
            (STATUS_REVOKED, ts, reason, domain))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": STATUS_REVOKED,
            "reason": reason, "sealed": sealed, "checkpoint": cp,
            "note": "Nothing was deleted. The revocation is sealed and the history stays public."}, 200


def _recheck_all(ctx):
    domains = _live_domains(ctx)
    results = []
    for d in domains:
        body, _ = _recheck(ctx, {"domain": d})
        results.append({"domain": d, "status": body.get("status"),
                        "failed": (body.get("checks") or {}).get("failed")})
    # age anything whose last pass is old
    cutoff = _now() - STALE_AFTER_DAYS * 86400
    aged = []
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain, last_pass FROM register_entry WHERE status=?",
            (STATUS_PASSED,)).fetchall()
    for domain, last_pass in rows:
        if last_pass is None or last_pass < cutoff:
            try:
                _seal_event(ctx, domain, "stale", {"last_pass": _iso(last_pass) if last_pass else None})
            except Exception:
                continue
            with ctx["lock"]:
                ctx["conn"].execute(
                    "UPDATE register_entry SET status=?, last_event=? WHERE domain=?",
                    (STATUS_STALE, _now(), domain))
                ctx["conn"].commit()
            aged.append(domain)

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}
    return {"ok": True, "rechecked": results, "moved_to_stale": aged,
            "checkpoint": cp}, 200


def _list(ctx, q):
    want = (q.get("status") or "").strip().lower()
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain, status, first_listed, last_event, last_checked, last_pass,"
            " checks_json, reason FROM register_entry ORDER BY domain ASC").fetchall()
    out = []
    for r in rows:
        checks = {}
        try:
            checks = json.loads(r[6]) if r[6] else {}
        except Exception:
            checks = {}
        entry = {
            "domain": r[0],
            "status": r[1],
            "status_means": VOCABULARY.get(r[1], "unexplained value — treat as unverified"),
            "first_listed": _iso(r[2]),
            "last_event": _iso(r[3]),
            "last_checked": _iso(r[4]) if r[4] else None,
            "last_pass": _iso(r[5]) if r[5] else None,
            "failed_checks": checks.get("failed") or [],
            "reason": r[7],
        }
        if not want or entry["status"] == want:
            out.append(entry)

    with ctx["lock"]:
        cp = ctx["conn"].execute(
            "SELECT ts, tree_size, event_root, domain_root, domain_count"
            " FROM register_checkpoint ORDER BY id DESC LIMIT 1").fetchone()

    return {
        "registry_version": VERSION,
        "suite_version": SUITE_VERSION,
        "count": len(out),
        "entries": out,
        "status_vocabulary": VOCABULARY,
        "what_this_list_is_not": WHAT_THIS_IS_NOT,
        "latest_checkpoint": ({
            "at": _iso(cp[0]), "tree_size": cp[1], "event_root": cp[2],
            "domain_root": cp[3], "domain_count": cp[4],
        } if cp else None),
        "prove_absence": "/x/register/absence?domain=example.com&at=2026-01-01",
        "prove_append_only": "/x/register/consistency?first=<size>&second=<size>",
    }, 200


def _entry(ctx, q):
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        r = ctx["conn"].execute(
            "SELECT domain, status, first_listed, last_event, last_checked, last_pass,"
            " checks_json, contact, claim_method, reason FROM register_entry WHERE domain=?",
            (domain,)).fetchone()
    if not r:
        return {"error": MESSAGES["not_listed"], "domain": domain,
                "prove_it": "/x/register/absence?domain=%s&at=<date>" % domain}, 404
    try:
        checks = json.loads(r[6]) if r[6] else {}
    except Exception:
        checks = {}
    return {
        "domain": r[0], "status": r[1],
        "status_means": VOCABULARY.get(r[1], "unexplained value — treat as unverified"),
        "first_listed": _iso(r[2]), "last_event": _iso(r[3]),
        "last_checked": _iso(r[4]) if r[4] else None,
        "last_pass": _iso(r[5]) if r[5] else None,
        "claim_method": r[8], "reason": r[9],
        "checks": checks,
        "what_this_is_not": WHAT_THIS_IS_NOT,
        "history": "/x/register/history?domain=%s" % domain,
    }, 200


def _history(ctx, q):
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT seq, ts, kind, detail, leaf_hex, audit_hash FROM register_event"
            " WHERE domain=? ORDER BY seq ASC", (domain,)).fetchall()
    events = []
    for s, ts, kind, detail, leaf, ah in rows:
        try:
            d = json.loads(detail)
        except Exception:
            d = detail
        events.append({"seq": s, "at": _iso(ts), "kind": kind, "detail": d,
                       "leaf": leaf, "audit_hash": ah,
                       "inclusion": "/x/register/inclusion?seq=%d" % s})
    return {"domain": domain, "count": len(events), "events": events,
            "note": "Nothing is ever removed from this history, including revocations."}, 200


def _absence(ctx, q):
    """Prove a domain was NOT listed at a given time."""
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    at = _parse_when(q.get("at"))
    with ctx["lock"]:
        if at is None:
            cp = ctx["conn"].execute(
                "SELECT ts, tree_size, domain_root, domain_count, domains_json, audit_hash"
                " FROM register_checkpoint ORDER BY id DESC LIMIT 1").fetchone()
        else:
            cp = ctx["conn"].execute(
                "SELECT ts, tree_size, domain_root, domain_count, domains_json, audit_hash"
                " FROM register_checkpoint WHERE ts<=? ORDER BY ts DESC LIMIT 1",
                (at,)).fetchone()
    if not cp:
        return {"error": MESSAGES["no_checkpoint"], "domain": domain,
                "asked_about": _iso(at) if at else "now"}, 404

    domains = json.loads(cp[4])
    leaves = [_sorted_leaf(d) for d in domains]
    root = _sorted_root(leaves).hex()

    if domain in domains:
        idx = domains.index(domain)
        return {
            "domain": domain,
            "present": True,
            "at": _iso(cp[0]),
            "checkpoint_root": root,
            "index": idx,
            "path": _sorted_path(leaves, idx),
            "proves": "This domain WAS listed at the checkpoint shown. This is an inclusion proof, not an absence proof.",
        }, 200

    # find the two adjacent leaves it would sit between
    lo, hi = None, None
    for i, d in enumerate(domains):
        if d < domain:
            lo = i
        if d > domain and hi is None:
            hi = i
    neighbours = []
    if lo is not None:
        neighbours.append({"position": "before", "index": lo, "domain": domains[lo],
                           "leaf": leaves[lo].hex(), "path": _sorted_path(leaves, lo)})
    if hi is not None:
        neighbours.append({"position": "after", "index": hi, "domain": domains[hi],
                           "leaf": leaves[hi].hex(), "path": _sorted_path(leaves, hi)})

    if lo is not None and hi is not None:
        proves = ("Indices %d and %d are consecutive in a sorted tree committed at %s. "
                  "Nothing can sit between them, and %s sorts between them, so it was "
                  "not listed at that checkpoint." % (lo, hi, _iso(cp[0]), domain))
    elif not domains:
        proves = ("The register held no listings at all at that checkpoint "
                  "(count 0, sealed root %s), so %s was not listed." % (root, domain))
    elif lo is None:
        proves = ("%s sorts before the first leaf at index 0, and the leaf count was "
                  "committed in advance, so it was not listed at that checkpoint." % domain)
    else:
        proves = ("%s sorts after the last leaf at index %d, and the leaf count was "
                  "committed in advance, so it was not listed at that checkpoint." % (domain, lo))

    return {
        "domain": domain,
        "present": False,
        "asked_about": _iso(at) if at else "now",
        "checkpoint_at": _iso(cp[0]),
        "checkpoint_root": root,
        "sealed_root": cp[2],
        "roots_agree": root == cp[2],
        "domain_count": cp[3],
        "neighbours": neighbours,
        "proves": proves,
        "how_to_check_yourself": [
            "leaf   = SHA256('AILEASH-REGISTER-LEAF-v1\\x00' + domain)",
            "node   = SHA256('AILEASH-REGISTER-NODE-v1\\x00' + left + right)",
            "Odd nodes are promoted to the next level, never paired with themselves.",
            "Recompute each neighbour's path to the root and confirm it equals checkpoint_root.",
        ],
        "limit": "An absence proof is against a checkpoint. It says nothing about moments between checkpoints.",
    }, 200


def _consistency(ctx, q):
    """RFC 6962 proof that the register at size `first` is a prefix of size `second`."""
    leaves = _event_leaves(ctx)
    n = len(leaves)
    try:
        first = int(q.get("first")) if q.get("first") else None
        second = int(q.get("second")) if q.get("second") else n
    except (TypeError, ValueError):
        return {"error": "first and second must be integers"}, 400
    if first is None:
        return {"error": "first is required — the tree size you already hold",
                "current_size": n}, 400
    if not (0 < first <= second <= n):
        return {"error": "need 0 < first <= second <= current size",
                "current_size": n}, 400

    proof = _ct_consistency(leaves[:second], first)
    return {
        "first": first,
        "second": second,
        "current_size": n,
        "first_root": _ct_root(leaves[:first]).hex(),
        "second_root": _ct_root(leaves[:second]).hex(),
        "proof": proof,
        "algorithm": "RFC 6962 consistency proof, SHA-256, leaf prefix 0x00, node prefix 0x01",
        "proves": ("The register at size %d is a prefix of the register at size %d. "
                   "No entry was inserted, altered or removed behind an earlier "
                   "position — including by the operator." % (first, second)),
        "verify_with": "Any standard Certificate Transparency verifier. This tree is deliberately unmodified so you do not have to use ours.",
    }, 200


def _inclusion(ctx, q):
    leaves = _event_leaves(ctx)
    try:
        seq = int(q.get("seq"))
    except (TypeError, ValueError):
        return {"error": "seq is required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT seq, ts, domain, kind, leaf_hex, audit_hash FROM register_event"
            " WHERE seq=?", (seq,)).fetchone()
    if not row:
        return {"error": "no event at that seq"}, 404
    index = seq - 1
    if index < 0 or index >= len(leaves):
        return {"error": "seq out of range of the current tree"}, 409
    return {
        "seq": seq, "index": index, "at": _iso(row[1]), "domain": row[2],
        "kind": row[3], "leaf": row[4], "audit_hash": row[5],
        "tree_size": len(leaves),
        "root": _ct_root(leaves).hex(),
        "proof": _ct_inclusion(leaves, index),
        "algorithm": "RFC 6962 inclusion proof, SHA-256",
    }, 200


def _checkpoints(ctx, q):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT id, ts, tree_size, event_root, domain_root, domain_count, audit_hash"
            " FROM register_checkpoint ORDER BY id DESC LIMIT 200").fetchall()
    return {
        "count": len(rows),
        "checkpoints": [{
            "id": r[0], "at": _iso(r[1]), "tree_size": r[2],
            "event_root": r[3], "domain_root": r[4],
            "domain_count": r[5], "audit_hash": r[6],
        } for r in rows],
        "note": "event_root answers append-only. domain_root answers absence. They are different trees and never match.",
    }, 200


def _roots(ctx):
    leaves = _event_leaves(ctx)
    domains = _live_domains(ctx)
    return {
        "tree_size": len(leaves),
        "event_root": _ct_root(leaves).hex(),
        "domain_count": len(domains),
        "domain_root": _sorted_root([_sorted_leaf(d) for d in domains]).hex(),
        "at": _iso(_now()),
        "note": "Live values. A root only becomes evidence once it is sealed by a checkpoint.",
    }, 200


# ------------------------------------------------------------------ handle

def handle(method, action, data, api_key, ctx):
    _ensure(ctx)
    data = data or {}
    q = data if isinstance(data, dict) else {}

    if method == "GET":
        if action == "spec":
            return _spec(ctx)
        if action == "vocabulary":
            return {"status_vocabulary": VOCABULARY,
                    "what_this_is_not": WHAT_THIS_IS_NOT,
                    "suite_version": SUITE_VERSION}, 200
        if action == "list":
            return _list(ctx, q)
        if action == "entry":
            return _entry(ctx, q)
        if action == "history":
            return _history(ctx, q)
        if action == "absence":
            return _absence(ctx, q)
        if action == "consistency":
            return _consistency(ctx, q)
        if action == "inclusion":
            return _inclusion(ctx, q)
        if action == "checkpoints":
            return _checkpoints(ctx, q)
        if action == "roots":
            return _roots(ctx)
        return {"error": "unknown action", "see": "/x/register/spec"}, 404

    if method == "POST":
        if action == "challenge":
            return _challenge(ctx, q)
        if action == "claim":
            return _claim(ctx, q)
        if action == "recheck":
            return _recheck(ctx, q)
        if action == "withdraw":
            return _withdraw(ctx, q)
        # keyed below
        if not api_key:
            return {"error": "api key required for this action"}, 401
        if action == "revoke":
            return _revoke(ctx, q)
        if action == "checkpoint":
            try:
                return {"ok": True, "checkpoint": _seal_checkpoint(ctx)}, 200
            except Exception as e:
                return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500
        if action == "recheck-all":
            return _recheck_all(ctx)
        return {"error": "unknown action", "see": "/x/register/spec"}, 404

    return {"error": "method not allowed"}, 405

```


## `modules/replay.py`

678 lines, 30538 bytes

```python
#!/usr/bin/env python3
"""
modules/replay.py  -  proving the same inputs still produce the same verdict
                      WITHOUT ever disclosing how the verdict is reached
============================================================================

THE QUESTION NOBODY ELSE IN THIS MARKET CAN ANSWER
--------------------------------------------------
Every compliance platform can tell you what it decided. Not one of them can
prove it would decide the same way again.

Ask any of them to re-run decision 4,117 from its sealed inputs and show the
same verdict falls out. They cannot. Not because they will not - because
their scoring goes through a model call, and model calls are not
reproducible. Same inputs, different day, different answer. Their audit
trail describes a decision that can never be performed twice.

Ours is arithmetic. Deterministic below the model layer, and always has
been. This module lets anyone establish that for themselves.

THE SCORING LOGIC IS NEVER DISCLOSED
------------------------------------
Read this before changing anything in here.

Nothing in this module publishes, returns, echoes or hints at the contents
of the decision function. Not the source, not the weights, not the
thresholds, not the signal names, not the intermediate values. The only
thing that leaves the building is a SHA-256 of the deployed source, which
is one-way and reveals nothing about what it hashes.

Determinism is proved as a BLACK BOX instead: same inputs in, same verdict
out, demonstrated repeatedly, by the challenger, on their own schedule,
with every run sealed into the chain. That is a stronger proof than showing
the code, because it is behaviour observed over time rather than a claim
about a listing nobody can confirm is what actually runs in production.

  A competitor who reads every route here learns exactly one thing: that
  our verdicts are reproducible. Which is the point, and which they cannot
  copy, because reproducibility is a property of the architecture and not a
  feature that can be bolted on.

HOW SOMEONE CHECKS US WITHOUT SEEING ANYTHING
---------------------------------------------
  POST /x/replay/challenge   send any inputs you like. We run them, seal
                             the run into the chain, and hand you back the
                             verdict, the audit hash, and a fingerprint of
                             your own inputs.

Send the same inputs again - an hour later, a year later, from a different
address. If the verdict ever moves, you have caught us, and both runs are
independently sealed and anchored so we cannot revise either one. If it
never moves, you have established determinism yourself, empirically,
adversarially, without a line of our code.

We also report how many times that exact input has been challenged, when it
was first seen, and every audit hash it produced, so the whole history is
verifiable through routes we do not control the answers to.

THE HONEST COST, WHICH IS REAL
------------------------------
An open scoring oracle can be probed. Feed it a thousand variations, watch
the verdicts move, and a determined party can map the decision boundary
without ever seeing the code. That is a genuine exposure and it is the
price of this proof.

It is mitigated, not eliminated: challenges are rate limited per address,
inputs are fingerprinted so repeat submissions are cheap and novel ones are
not, and boundary-probing patterns are already logged elsewhere in the
platform. Anyone systematically mapping the function leaves an obvious,
sealed trail while doing it.

The trade is deliberate. A closed engine nobody can test is worth less than
a testable one somebody might partially map, because the first cannot be
sold to a regulator and the second can.

CONFIGURATION
-------------
This module does not import server.py - nothing here does. It finds the
live decision function at runtime among already-loaded modules, so it can
only observe the engine, never change it. If your scorer is named something
not in SCORER_NAMES below, add it there. Everything else is read from the
audit_log schema at startup rather than assumed.

    POST /x/replay/challenge     run any inputs, sealed          (public)
    GET  /x/replay/history       every run of a given input       (public)
    GET  /x/replay/self          reproduction rate over a sample  (public)
    GET  /x/replay/fingerprint   hash of the deployed code        (public)
    GET  /x/replay/spec          how to test us                   (public)
    GET  /x/replay/check         re-run one sealed decision       (keyed)
    POST /x/replay/attest        seal the current fingerprint     (keyed)
"""

import hashlib
import inspect
import json
import sys
import time
from datetime import datetime, timezone

VERSION = "1.0"

# Challenge, history, self, fingerprint and spec are open - a
# reproducibility claim you need an account to test is not a claim anyone
# should accept. check stays keyed: it reads back a specific sealed
# decision, which belongs to whoever owns it.
PUBLIC = {("POST", "challenge"), ("GET", "history"), ("GET", "self"),
          ("GET", "fingerprint"), ("GET", "spec")}

# Names the live decision function might go by. Add yours if it is not
# here - this is the one thing that has to match your code.
SCORER_NAMES = (
    "score_event", "decide", "score", "evaluate", "run_decision",
    "make_decision", "assess", "score_decision", "engine_decide",
)

# Columns the sealed inputs might live in. Detected, never assumed.
INPUT_COLUMNS = ("event", "event_json", "payload", "inputs", "request",
                 "ev", "data", "event_data")
RESULT_COLUMNS = ("result", "result_json", "res", "decision_json", "outcome",
                  "response")
VERDICT_COLUMNS = ("decision", "verdict", "action_taken")
SCORE_COLUMNS = ("score", "risk_score", "points")

SELF_SAMPLE_DEFAULT = 50
SELF_SAMPLE_MAX = 500

# Challenge throttle. Repeat submissions of an input we have already seen
# are cheap; novel inputs are what a prober needs, so those are what get
# limited.
NOVEL_PER_HOUR = 40
MAX_PAYLOAD_KEYS = 40

_ready = False
_columns = []


def _setup(ctx):
    global _ready, _columns
    if _ready:
        return
    cols = []
    try:
        with ctx["lock"]:
            for row in ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall():
                cols.append(row[1])
    except Exception:
        pass
    _columns = cols
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS replay_attest("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "fingerprint TEXT,function TEXT,taken REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        # One row per challenge run. The input fingerprint is stored, the
        # input itself is not - we have no reason to keep a stranger's
        # payload and every reason not to.
        c.execute("CREATE TABLE IF NOT EXISTS replay_challenge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,input_hash TEXT,"
                  "verdict TEXT,score TEXT,code_fingerprint TEXT,ran REAL,"
                  "audit_hash TEXT,block_index INTEGER,client TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_input "
                  "ON replay_challenge(input_hash,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_ran ON replay_challenge(ran)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _pick(candidates):
    for name in candidates:
        if name in _columns:
            return name
    return None


def _canonical(payload):
    """Stable rendering of an input payload, so the same inputs always
    fingerprint to the same value regardless of key order or spacing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _input_hash(payload):
    return hashlib.sha256(("AILEASH-INPUT-v1:" + _canonical(payload)).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# finding the live decision function
# ----------------------------------------------------------------------

def _find_scorer():
    """Locate the deployed decision function among loaded modules.

    Deliberately does not import server.py. It looks at what is already
    running, so this module can observe the engine and never alter it.
    """
    for module_name in ("__main__", "server", "app", "main"):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in SCORER_NAMES:
            candidate = getattr(module, name, None)
            if callable(candidate):
                return candidate, "%s.%s" % (module_name, name), None
    return None, None, ("no decision function found. Add its real name to SCORER_NAMES at the "
                        "top of modules/replay.py.")


def _fingerprint_of(function):
    """SHA-256 of the deployed source. One-way: it commits to which code is
    running without revealing any of it."""
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        return None, "source not readable for this callable"
    normalised = "\n".join(line.rstrip() for line in source.splitlines()).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest(), None


# ----------------------------------------------------------------------
# running the engine
# ----------------------------------------------------------------------

def _rerun(function, inputs):
    """Execute the live decision function against a set of inputs.

    Never raises. On failure it reports that the call failed and nothing
    about why the engine is shaped the way it is.
    """
    if inputs is None:
        return None, "no inputs"
    attempts = []
    if isinstance(inputs, dict):
        attempts.append(lambda: function(**inputs))
        attempts.append(lambda: function(inputs))
    else:
        attempts.append(lambda: function(inputs))
    for call in attempts:
        try:
            return call(), None
        except TypeError:
            continue
        except Exception:
            return None, "the decision function could not process those inputs"
    return None, "those inputs do not match the shape the engine expects"


def _extract(output):
    """Pull (verdict, score) out of whatever the scorer returns. Nothing
    else from the return value is ever surfaced."""
    if isinstance(output, dict):
        return (output.get("decision") or output.get("verdict"), output.get("score"))
    if isinstance(output, (tuple, list)) and len(output) >= 2:
        return output[0], output[1]
    return output, None


def _same(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    return str(a).strip().upper() == str(b).strip().upper()


# ----------------------------------------------------------------------
# challenge - the public proof
# ----------------------------------------------------------------------

def _novel_recently(ctx):
    since = time.time() - 3600
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT input_hash) FROM replay_challenge WHERE ran>=?",
            (since,)).fetchone()
    return int(row[0]) if row else 0


def _challenge(ctx, api_key, data):
    inputs = data.get("inputs", data.get("event", data.get("payload")))
    if not isinstance(inputs, dict) or not inputs:
        return {"error": "inputs_required",
                "message": "Send an inputs object. We will run it, seal the run, and hand you "
                           "back the verdict. Send the same object again whenever you like - "
                           "if the answer ever moves, you have caught us."}, 400
    if len(inputs) > MAX_PAYLOAD_KEYS:
        return {"error": "payload_too_wide", "message": "at most %d keys" % MAX_PAYLOAD_KEYS}, 400

    fingerprint_in = _input_hash(inputs)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC",
            (fingerprint_in,)).fetchall()

    if not prior and _novel_recently(ctx) >= NOVEL_PER_HOUR:
        return {"error": "rate_limited",
                "message": "Too many distinct inputs in the last hour. Repeat submissions of "
                           "inputs already seen are never limited - testing whether the answer "
                           "moves is the whole point. Mapping the function is not.",
                "repeat_freely": "any input_hash already in /x/replay/history"}, 429

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable", "message": "the decision engine is not reachable "
                                                          "from this route right now"}, 503

    output, problem = _rerun(function, inputs)
    if problem:
        return {"error": "not_runnable", "message": problem}, 422

    verdict, score = _extract(output)
    code_fingerprint, _p = _fingerprint_of(function)
    now = time.time()

    ev = {"user_id": "chal:" + fingerprint_in[:16], "action": "replay_challenge", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": str(verdict), "score": score, "replay_version": VERSION,
           "input_hash": fingerprint_in, "code_fingerprint": code_fingerprint,
           "detail": "input=%s;verdict=%s;code=%s" % (fingerprint_in, verdict, code_fingerprint)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key or "public-replay")

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO replay_challenge(input_hash,verdict,score,code_fingerprint,ran,"
            "audit_hash,block_index,client) VALUES(?,?,?,?,?,?,?,?)",
            (fingerprint_in, str(verdict), str(score), code_fingerprint, now,
             audit_hash, block_index, "keyed" if api_key else "anonymous"))
        ctx["conn"].commit()

    out = {
        "input_hash": fingerprint_in,
        "verdict": verdict, "score": score,
        "ran_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "code_fingerprint": code_fingerprint,
        "runs_of_this_input": len(prior) + 1,
        "replay_version": VERSION,
        "how_to_use_this": "Send the identical inputs again, whenever you like, from wherever "
                           "you like. Every run is sealed into a chain that is externally "
                           "anchored and independently witnessed, so neither this answer nor "
                           "the next one can be revised afterwards.",
        "history": "/x/replay/history?input_hash=" + fingerprint_in,
        "verify_this_run": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if prior:
        first_verdict, first_score = prior[0][0], prior[0][1]
        stable = _same(verdict, first_verdict) and _same(score, first_score)
        out["first_seen"] = _iso(prior[0][2])
        out["stable"] = stable
        out["verdict_moved"] = not stable
        if stable:
            out["what_this_shows"] = ("Identical to the first run of these inputs on %s, and to "
                                      "every run since. Determinism observed rather than "
                                      "asserted." % _iso(prior[0][2]))
        else:
            out["what_this_shows"] = ("These inputs previously produced a different answer. "
                                      "Either the code changed - compare the code fingerprints "
                                      "in the history - or the engine is not deterministic. "
                                      "Both runs are sealed and neither can be withdrawn.")
    else:
        out["stable"] = None
        out["what_this_shows"] = ("First time these inputs have been seen. Send them again to "
                                  "start building the record.")
    return out, 200


def _history(ctx, data):
    input_hash = str(data.get("input_hash", data.get("hash", ""))).strip().lower()
    if not input_hash:
        return {"error": "input_hash_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint,client "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC LIMIT 500",
            (input_hash,)).fetchall()
    if not rows:
        return {"error": "unknown_input", "input_hash": input_hash,
                "message": "No run recorded for that input fingerprint."}, 404

    verdicts = {r[0] for r in rows}
    codes = {r[5] for r in rows if r[5]}
    return {
        "input_hash": input_hash,
        "runs": len(rows),
        "first_run": _iso(rows[0][2]), "latest_run": _iso(rows[-1][2]),
        "distinct_verdicts": len(verdicts),
        "stable": len(verdicts) == 1,
        "code_versions_seen": len(codes),
        "history": [{"verdict": r[0], "score": r[1], "ran_at": _iso(r[2]),
                     "sealed_in_chain": r[3], "block_index": r[4],
                     "code_fingerprint": r[5], "submitted_by": r[6]} for r in rows],
        "what_this_is": "Every recorded run of one exact set of inputs, each sealed separately "
                        "into the chain. Verify any of them independently at "
                        "/x/consistency/ancestor - we cannot alter one after the fact.",
        "note": "More than one distinct verdict across a single code fingerprint would mean the "
                "engine is not deterministic. That is exactly what this is here to expose.",
    }, 200


# ----------------------------------------------------------------------
# self audit
# ----------------------------------------------------------------------

def _fetch(ctx, where, args):
    input_col = _pick(INPUT_COLUMNS)
    result_col = _pick(RESULT_COLUMNS)
    verdict_col = _pick(VERDICT_COLUMNS)
    score_col = _pick(SCORE_COLUMNS)
    if not input_col:
        return None, ("audit_log does not store decision inputs on this deployment, so sealed "
                      "decisions cannot be re-executed. Seal the event payload alongside the "
                      "verdict and replay becomes available from that point on.")
    fields = ["id", "audit_hash", "ts", input_col]
    for extra in (result_col, verdict_col, score_col):
        if extra and extra not in fields:
            fields.append(extra)
    sql = "SELECT %s FROM audit_log WHERE %s" % (", ".join(fields), where)
    with ctx["lock"]:
        rows = ctx["conn"].execute(sql, tuple(args)).fetchall()
    if not rows:
        return None, "no sealed decision matched"
    out = []
    for row in rows:
        record = dict(zip(fields, row))
        raw = record.get(input_col)
        try:
            parsed = raw if isinstance(raw, (dict, list)) else json.loads(raw)
        except Exception:
            parsed = None
        sealed_result = None
        if result_col:
            raw_result = record.get(result_col)
            try:
                sealed_result = raw_result if isinstance(raw_result, dict) else json.loads(raw_result)
            except Exception:
                sealed_result = None
        out.append({"id": record.get("id"), "audit_hash": record.get("audit_hash"),
                    "ts": record.get("ts"), "inputs": parsed,
                    "sealed_result": sealed_result,
                    "sealed_verdict": record.get(verdict_col) if verdict_col else None,
                    "sealed_score": record.get(score_col) if score_col else None})
    return out, None


def _sealed_pair(record):
    verdict = record.get("sealed_verdict")
    score = record.get("sealed_score")
    result = record.get("sealed_result")
    if isinstance(result, dict):
        if verdict is None:
            verdict = result.get("decision") or result.get("verdict")
        if score is None:
            score = result.get("score")
    return verdict, score


def _compare(record, function):
    output, why = _rerun(function, record.get("inputs"))
    sealed_verdict, sealed_score = _sealed_pair(record)
    if why:
        return {"audit_hash": record["audit_hash"], "result": "not_replayable"}
    verdict, score = _extract(output)
    identical = _same(verdict, sealed_verdict) and _same(score, sealed_score)
    return {"audit_hash": record["audit_hash"], "sealed_at": _iso(record.get("ts")),
            "result": "identical" if identical else "divergent"}


def _self(ctx, data):
    try:
        sample = int(data.get("sample", SELF_SAMPLE_DEFAULT))
    except (TypeError, ValueError):
        sample = SELF_SAMPLE_DEFAULT
    sample = max(1, min(sample, SELF_SAMPLE_MAX))

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503

    records, fetch_why = _fetch(ctx, "1=1 ORDER BY id DESC LIMIT ?", [sample])
    if fetch_why:
        return {"error": "cannot_replay", "message": fetch_why}, 400

    identical = divergent = skipped = 0
    divergent_hashes = []
    started = time.time()
    for record in records:
        outcome = _compare(record, function)
        if outcome["result"] == "identical":
            identical += 1
        elif outcome["result"] == "divergent":
            divergent += 1
            if len(divergent_hashes) < 10:
                divergent_hashes.append(outcome["audit_hash"])
        else:
            skipped += 1

    checked = identical + divergent
    rate = round((identical / checked) * 100, 4) if checked else None
    code_fingerprint, _p = _fingerprint_of(function)

    body = {
        "sampled": len(records), "replayable": checked,
        "identical": identical, "divergent": divergent, "not_replayable": skipped,
        "reproduction_rate_percent": rate,
        "took_seconds": round(time.time() - started, 3),
        "code_fingerprint": code_fingerprint,
        "replay_version": VERSION,
        "headline": ("%d of %d sealed decisions reproduce identically under the code deployed "
                     "right now." % (identical, checked)) if checked else
                    "Nothing replayable in this sample.",
        "why_this_matters": "A platform whose scoring runs through a model call cannot do this "
                            "at all. Reproducibility is a property of the architecture, not a "
                            "feature that can be added later.",
        "honest": "Divergences are counted here, not filtered out. A falling rate is the most "
                  "useful thing this route can tell you.",
        "independent_check": "Do not take our word for this - /x/replay/challenge lets you run "
                             "your own inputs and repeat them whenever you like.",
    }
    if divergent_hashes:
        body["divergent_receipts"] = divergent_hashes
    return body, 200


# ----------------------------------------------------------------------
# fingerprint, keyed check, attest
# ----------------------------------------------------------------------

def _fingerprint(ctx):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    return {"code_fingerprint": digest, "problem": problem, "replay_version": VERSION,
            "what_this_is": "A SHA-256 of the source of the code currently deciding. It commits "
                            "to which version is running. It is one-way and discloses nothing "
                            "about the logic, the weights or the thresholds.",
            "what_it_is_for": "Sealed alongside verdicts via /x/replay/attest, so a change in "
                              "behaviour can be attributed to a dated code change rather than "
                              "looking like a fault - or hidden as one.",
            "note": "The function name and signature are deliberately not published."}, 200


def _check(ctx, data):
    """Keyed. Re-runs one sealed decision and reports match or divergence."""
    target = str(data.get("hash", data.get("receipt", ""))).strip().lower()
    if not target:
        return {"error": "hash_required"}, 400
    records, why = _fetch(ctx, "audit_hash=? LIMIT 1", [target])
    if why:
        return {"error": "cannot_replay", "message": why}, 400
    function, name, scorer_why = _find_scorer()
    if scorer_why:
        return {"error": "engine_unavailable"}, 503
    outcome = _compare(records[0], function)
    digest, _p = _fingerprint_of(function)
    outcome.update({"code_fingerprint": digest, "replay_version": VERSION,
                    "what_this_proves": "The sealed inputs were fed back through the live "
                                        "decision function and the output compared with what "
                                        "was sealed."})
    return outcome, 200


def _attest(ctx, api_key):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    if not digest:
        return {"error": "no_fingerprint", "message": problem}, 503

    now = time.time()
    ev = {"user_id": "rep:" + digest[:16], "action": "code_fingerprint_sealed", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_SEALED", "score": 0, "replay_version": VERSION,
           "fingerprint": digest, "detail": "fingerprint=%s" % digest}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO replay_attest(api_key,fingerprint,function,taken,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, digest, name, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"fingerprint": digest, "taken_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Records which code was deciding at this moment, inside the chain "
                              "the decisions are sealed in. Every verdict after this point is "
                              "attributable to a known, timestamped version of the logic - "
                              "without that logic being published.",
            "do_this": "Attest on every deploy that touches scoring. A later divergence then "
                       "reads as a dated policy change rather than an unexplained fault."}, 200


def _spec():
    return {
        "replay_version": VERSION,
        "claim": "The same inputs produce the same verdict, and you can establish that yourself "
                 "without an account and without seeing any of our logic.",
        "the_logic_is_not_published": "No route here returns the scoring source, the weights, "
                                      "the thresholds, the signal names or any intermediate "
                                      "value. The only thing published is a SHA-256 of the "
                                      "deployed source, which is one-way.",
        "how_to_test_us": [
            "POST /x/replay/challenge with any inputs object you like.",
            "Keep the input_hash it returns.",
            "Send the identical inputs again tomorrow, next month, next year, from anywhere.",
            "GET /x/replay/history?input_hash=... to see every run, each sealed separately.",
            "If the verdict ever moves under an unchanged code fingerprint, the engine is not "
            "deterministic and you have proof of it that we cannot withdraw.",
        ],
        "why_black_box_is_stronger": "A published listing only shows what the code says. "
                                     "Repeated challenge shows what production actually does, "
                                     "over time, on inputs we did not choose.",
        "what_breaks_determinism": [
            "a wall-clock read inside the scoring path",
            "iteration over an unordered structure",
            "an unseeded random call",
            "any model call in the decision path - which is why most platforms cannot do this",
        ],
        "what_this_does_not_prove": "That a decision was correct, or that the inputs were "
                                    "honestly captured. Only that the same inputs still yield "
                                    "the same output under known code. Determinism is not "
                                    "fairness.",
        "rate_limits": "Repeat submissions of inputs already seen are never limited - retesting "
                       "is the point. Novel inputs are limited, because bulk novel inputs are "
                       "how a decision boundary gets mapped rather than how a claim gets tested.",
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
        if action == "fingerprint":
            return _fingerprint(ctx)
        if action == "history":
            return _history(ctx, data)
        if action == "self":
            return _self(ctx, data)
        if action == "check":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _check(ctx, data)

    if method == "POST":
        if action == "challenge":
            return _challenge(ctx, api_key, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "attest":
            return _attest(ctx, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "fingerprint", "history", "self", "check (keyed)"],
            "POST": ["challenge", "attest (keyed)"]}, 404

```


## `modules/roster.py`

537 lines, 21691 bytes

```python
"""
modules/roster.py  v1.2  -  the canonical network list

WHY
    Witnessing runs on each operator's own machine. A new chain can join
    the network and nobody else's server knows it exists, because nobody
    told it. The result is a star with one operator in the middle, which
    is the shape a witnessed log is supposed to avoid.

    This publishes the list. Every peer, every tip URL, one public route.
    A peer's sync reads it and witnesses everyone on it, including
    whoever joined this morning.

    It does not witness anything itself. It is a phone book.

WHERE THE DATA COMES FROM
    witness_log and witness_names, which witness.py already maintains,
    plus signed_keys from signed.py where it exists. Nothing new is
    recorded and no existing module changes. A chain appears here because
    it submitted a tip, which is the same thing that binds its name today.

WHAT MAKES THE LIST HONEST
    Every entry carries its own evidence: when it was first and last
    seen, how many observations, whether its name is bound to a host or
    to a key, and whether it has gone quiet. Nothing is filtered out for
    looking bad. A silent chain stays listed and is marked silent,
    because hiding it would make the list a claim rather than a record.

WHAT CHANGED IN 1.2, AND WHY
    Two things, both prompted by peers reading their own entries.

    1. THE STATUS WORDS NOW MEAN WHAT THE OTHER ROUTE MEANS.
       /x/witness/peers has always used three bands - current under 6h,
       stale from 6 to 48, silent beyond. This route used two, so the
       same peer could read "silent" here and "stale" there in the same
       minute, with no way to tell which was the real one. They now match,
       and both publish what the bands mean.

       The words describe elapsed time since we last recorded an
       observation. Nothing else. A peer who publishes on a human
       schedule rather than a timer reads stale between sessions, and
       that is correct rather than a fault. It is never a claim that
       anyone's endpoint was unavailable, and Philip Pinol (PRAXIS) had
       to point that out from his own seat, which he should not have had
       to do.

    2. THE LIST NOW EXPLAINS ITS OWN VOCABULARY.
       Entries carry liveness and name_status values written by
       witness.py, and signed.py adds two more of them. Publishing a word
       a reader cannot look up is the same failure as "confirmed" was:
       the meaning lives somewhere else and does not travel with the
       record. Every value this route can emit is now defined in the
       response that emits it.

ROUTES
    GET  list      public   the roster. this is the one peers poll.
    GET  spec      public   what this is and how to consume it
    GET  health    public   one-line network summary
"""

import time

VERSION = "1.2"

PUBLIC = {("GET", "list"), ("GET", "spec"), ("GET", "health")}

# Status bands, in hours. These MUST match witness.py's _peers, or the
# same peer reads two different words about itself on two public routes.
CURRENT_UNDER_HOURS = 6
SILENT_AFTER_HOURS = 48

# Our own entry, so a consumer of the roster does not have to be told
# separately who publishes it.
SELF_CHAIN = "sebbi.pro"
SELF_TIP = "https://sebbi.pro/x/witness/tip"
SELF_OBSERVE = "https://sebbi.pro/x/witness/observe"
SELF_SIGNED = "https://sebbi.pro/x/signed/submit"

# Every value this route can publish, and what it means. A word that
# leaves here without its meaning attached is the same mistake as
# "confirmed", one field over.
LIVENESS_VOCABULARY = {
    "self-consistent":
        "The url the submitter gave served exactly the tip the submitter "
        "sent. Both halves came from the submitter, so this records "
        "self-consistency - NOT verification by us or any third party.",
    "confirmed":
        "The same check as self-consistent, under the name used before "
        "witness v1.2. Sealed blocks cannot be altered, so older records "
        "still carry the original word.",
    "live":
        "The url served a valid but different tip. A chain that moves "
        "between submitting and our fetching is the normal case, not a "
        "failure.",
    "self-declared":
        "No url, or we could not reach it. Taken on the submitter's word "
        "and checked by nobody.",
    "peer-signed":
        "Submitted through /x/signed/submit and verified against an "
        "Ed25519 public key the submitter enrolled. We hold only the "
        "public half, so we could not have produced that signature. This "
        "is the only value on this list that excludes us as well as third "
        "parties.",
    "self":
        "This deployment's own entry. Not a check of anything.",
    "unchecked":
        "Recorded before liveness checking existed.",
}

NAME_VOCABULARY = {
    "first-use":
        "First time this name was seen with a reachable url, so the name "
        "is now bound to it network-wide. A later submission under this "
        "name from a different address records as conflict, permanently.",
    "bound":
        "Submitted from the same url this name was first bound to. Same "
        "operator, consistently.",
    "conflict":
        "This name has been submitted from a different address than the "
        "one it was first bound to. Not proof of theft - operators move "
        "hosts - but it is the event an auditor needs to see.",
    "unbound":
        "No reachable url, so there is nothing to bind this name to. An "
        "unbound name stays claimable by whoever submits it next WITH a "
        "reachable url.",
    "key-bound":
        "This name is bound to an Ed25519 public key rather than to a "
        "host address. Only the holder of the matching private key can "
        "submit under it, and that holder is not us.",
    "publisher":
        "The deployment publishing this roster.",
    "unchecked":
        "Recorded before name binding existed.",
}

STATUS_VOCABULARY = {
    "current": "observed within the last %dh" % CURRENT_UNDER_HOURS,
    "stale": "last observed between %dh and %dh ago"
             % (CURRENT_UNDER_HOURS, SILENT_AFTER_HOURS),
    "silent": "not observed for more than %dh" % SILENT_AFTER_HOURS,
    "unknown": "we hold no usable timestamp for this entry",
    "read_this": "These describe elapsed time since we last recorded an "
                 "observation, and nothing else. A peer that publishes on "
                 "a human schedule rather than from an always-on timer "
                 "will read stale between sessions, correctly. It is not "
                 "a claim that anyone's endpoint was unavailable, and it "
                 "is not a judgement about anyone.",
}


def _epoch(ts):
    """
    Accept either a unix number or an ISO-8601 string. witness.py stores
    ISO strings; other tables store floats. Guessing wrong here silently
    turned every peer's status into 'unknown', so it takes both.
    """
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        import datetime
        t = s.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(t).timestamp()
    except Exception:
        return None


def _iso(ts):
    e = _epoch(ts)
    if e is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e))
    except Exception:
        return None


def _cols(conn, table):
    try:
        return [r[1] for r in conn.execute(
            "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


def _status_for(hours):
    if hours is None:
        return "unknown"
    if hours <= CURRENT_UNDER_HOURS:
        return "current"
    if hours <= SILENT_AFTER_HOURS:
        return "stale"
    return "silent"


def _signed_keys(ctx):
    """
    Which names have enrolled an Ed25519 key with signed.py.

    Defensive on purpose: signed.py may not be deployed, in which case
    the table does not exist and every entry simply reports no key. This
    module must never be the reason a deploy breaks.
    """
    keys = {}
    try:
        rows = ctx["conn"].execute(
            "SELECT peer, pubkey, rotations FROM signed_keys").fetchall()
        for peer, pubkey, rotations in rows:
            if peer:
                keys[peer.strip()] = {"pubkey": pubkey,
                                      "rotations": rotations or 0}
    except Exception:
        pass
    return keys


def _gather(ctx):
    """
    Read whatever witness.py has. Written defensively: this module must
    never be the reason a deploy breaks, so a missing table or column
    degrades to a shorter list rather than a 500.
    """
    conn = ctx["conn"]
    now = time.time()
    out = {}

    cols = _cols(conn, "witness_log")
    if not cols:
        return out

    chain_col = None
    for c in ("chain", "peer", "chain_name", "name"):
        if c in cols:
            chain_col = c
            break
    if not chain_col:
        return out

    # witness.py calls this "observed" and stores an epoch float.
    # Other tables have used "ts". Try the real names in order.
    ts_col = None
    for c in ("observed", "ts", "seen", "peer_ts"):
        if c in cols:
            ts_col = c
            break
    url_col = "url" if "url" in cols else None
    live_col = "liveness" if "liveness" in cols else None
    name_col = "name_status" if "name_status" in cols else None

    sel = [chain_col]
    for c in (ts_col, url_col, live_col, name_col):
        sel.append(c if c else "NULL")

    try:
        rows = conn.execute(
            "SELECT %s FROM witness_log ORDER BY rowid" % ", ".join(sel)
        ).fetchall()
    except Exception:
        return out

    for r in rows:
        chain = (r[0] or "").strip()
        if not chain:
            continue
        e = out.setdefault(chain, {
            "chain": chain, "observations": 0, "first_seen": None,
            "last_seen": None, "url": None, "liveness": None,
            "name_status": None,
        })
        e["observations"] += 1
        ts = _epoch(r[1])
        if ts is not None:
            if e["first_seen"] is None or ts < e["first_seen"]:
                e["first_seen"] = ts
            if e["last_seen"] is None or ts > e["last_seen"]:
                e["last_seen"] = ts
        if r[2]:
            e["url"] = r[2]
        if r[3]:
            e["liveness"] = r[3]
        if r[4]:
            e["name_status"] = r[4]

    for e in out.values():
        last = e["last_seen"]
        hours = ((now - last) / 3600.0) if last else None
        e["hours_since"] = round(hours, 1) if hours is not None else None
        e["status"] = _status_for(hours)
    return out


def _entries(ctx):
    peers = _gather(ctx)
    keys = _signed_keys(ctx)
    now = time.time()

    listed = []
    for chain, e in sorted(peers.items(), key=lambda kv: kv[0]):
        entry = {
            "chain": e["chain"],
            "tip_url": e["url"],
            "observations": e["observations"],
            "first_seen": _iso(e["first_seen"]),
            "last_seen": _iso(e["last_seen"]),
            "hours_since": e["hours_since"],
            "status": e["status"],
            "liveness": e["liveness"],
            "name_status": e["name_status"],
            "witnessable": bool(e["url"]),
        }
        key = keys.get(chain)
        if key:
            # A peer with an enrolled key can be submitted for by nobody
            # but the keyholder. Worth surfacing on the list a regulator
            # or a buyer actually reads.
            entry["signing_key"] = {
                "algorithm": "ed25519",
                "pubkey": key["pubkey"],
                "rotations": key["rotations"],
                "means": "Only the holder of the matching private key can "
                         "submit under this name. This deployment holds "
                         "the public half only and cannot sign for them.",
                "verify_at": "/x/signed/keys",
            }
        listed.append(entry)

    listed.insert(0, {
        "chain": SELF_CHAIN,
        "tip_url": SELF_TIP,
        "observations": None,
        "first_seen": None,
        "last_seen": _iso(now),
        "hours_since": 0,
        "status": "current",
        "liveness": "self",
        "name_status": "publisher",
        "witnessable": True,
        "note": "The publisher of this roster. Listed so a consumer does "
                "not have to be told separately who to witness.",
    })
    return listed


def _used_vocabulary(entries):
    """
    Only define the words actually present in this response, plus a
    pointer to the full set. A legend listing values nobody has used
    reads as padding; a value with no definition is the failure this
    version exists to fix.
    """
    live = {}
    names = {}
    stats = {}
    for e in entries:
        v = e.get("liveness")
        if v:
            live[v] = LIVENESS_VOCABULARY.get(
                v, "Undefined in roster v%s. If you are reading this, the "
                   "word was introduced by another module and this route "
                   "has not been told what it means - treat it as "
                   "unexplained rather than as a claim." % VERSION)
        n = e.get("name_status")
        if n:
            names[n] = NAME_VOCABULARY.get(
                n, "Undefined in roster v%s - see above." % VERSION)
        s = e.get("status")
        if s:
            stats[s] = STATUS_VOCABULARY.get(s, "")
    stats["read_this"] = STATUS_VOCABULARY["read_this"]
    return {"liveness": live, "name_status": names, "status": stats}


def _list(ctx):
    entries = _entries(ctx)
    usable = [e for e in entries if e["witnessable"]]
    signed = [e for e in entries if e.get("signing_key")]
    return {
        "ok": True,
        "roster_version": VERSION,
        "generated": _iso(time.time()),
        "submit_to": SELF_OBSERVE,
        "submit_signed_to": SELF_SIGNED,
        "count": len(entries),
        "witnessable": len(usable),
        "stale": len([e for e in entries if e["status"] == "stale"]),
        "silent": len([e for e in entries if e["status"] == "silent"]),
        "with_signing_key": len(signed),
        "peers": entries,
        "vocabulary": _used_vocabulary(entries),
        "what_this_list_is":
            "Parties that have submitted a tip to this deployment. That is "
            "all it records. It is not a membership list, not a set of "
            "partners, and not participants in anything AILeash is building. "
            "Being listed implies no relationship beyond having sent a hash, "
            "and no endorsement of anything sealed in anyone else's chain "
            "including ours. A party appears here because they posted to an "
            "open endpoint; they did not join anything and were not asked to "
            "agree to anything.",
        "how_to_use":
            "Poll this route on your own schedule. For every entry with "
            "witnessable=true, fetch tip_url, seal the tip in your own "
            "chain, and POST your tip to their submit endpoint. A chain "
            "that joins tomorrow appears here and gets picked up on your "
            "next cycle with nothing to configure.",
        "note":
            "Chains that have gone quiet stay listed and are marked stale "
            "or silent. Removing them would make this a claim rather than "
            "a record. An entry with witnessable=false has never bound a "
            "url and cannot be fetched from. Read the status vocabulary "
            "before drawing a conclusion from either word - they measure "
            "elapsed time and nothing else.",
    }, 200


def _health(ctx):
    entries = _entries(ctx)
    others = [e for e in entries if e["chain"] != SELF_CHAIN]
    current = [e for e in others if e["status"] == "current"]
    return {
        "ok": True,
        "chains_listed": len(entries),
        "submitting_currently": len(current),
        "stale": len([e for e in others if e["status"] == "stale"]),
        "silent": len([e for e in others if e["status"] == "silent"]),
        "with_signing_key": len([e for e in others if e.get("signing_key")]),
        "status_vocabulary": STATUS_VOCABULARY,
        "what_this_counts":
            "Parties that have submitted a tip to this deployment, and how "
            "recently. Nothing more.",
        "what_this_does_not_tell_you": [
            "Whether any of these parties witness each other. They may not. "
            "Ask them, or read their own rosters.",
            "Whether any of them has agreed to anything, with us or with "
            "each other.",
            "Whether the records behind any of these tips are true.",
            "Whether a peer was reachable. A stale or silent entry means we "
            "have not recorded an observation recently, which is a fact "
            "about this list and not about their infrastructure.",
        ],
    }, 200


def _spec():
    return {
        "module": "roster",
        "version": VERSION,
        "what": "A list of parties that have submitted a tip to this "
                "deployment, with the tip URL each supplied.",
        "what_it_is_not":
            "Not a membership list. Not a set of partners, adopters, "
            "validators or participants in anything AILeash is building. "
            "Appearing here means a party posted a hash to an open endpoint. "
            "It implies no agreement, no relationship and no endorsement in "
            "any direction. Two surfaces, two separate things: being sealed "
            "in the chain, and being named on this list. Neither is consent "
            "to the other.",
        "why":
            "Witnessing runs on each operator's own machine, so a server "
            "only witnesses chains it has been told about. Without a "
            "shared list, every new joiner connects to whoever invited "
            "them and the network becomes a star with one operator in "
            "the middle. This route is the list, so a peer's sync can "
            "witness everybody instead of just its introducer.",
        "routes": {
            "GET list": "public. the roster. poll this.",
            "GET health": "public. one-line network summary.",
            "GET spec": "public. this document.",
        },
        "entry_fields": {
            "chain": "the chain's name as it submitted it",
            "tip_url": "where to fetch their current tip. null if they "
                       "have never bound one.",
            "witnessable": "true when tip_url is present",
            "status": "current, stale, silent or unknown - see "
                      "status_vocabulary. Matches the bands on "
                      "/x/witness/peers.",
            "observations": "how many tips they have submitted to us",
            "liveness": "as recorded at submission - see "
                        "liveness_vocabulary for every possible value",
            "name_status": "as recorded at submission - see "
                           "name_vocabulary for every possible value",
            "signing_key": "present only when the chain has enrolled an "
                           "Ed25519 public key at /x/signed/enroll. When "
                           "present, submissions under that name are "
                           "verified against a key this deployment does "
                           "not hold.",
        },
        "liveness_vocabulary": LIVENESS_VOCABULARY,
        "name_vocabulary": NAME_VOCABULARY,
        "status_vocabulary": STATUS_VOCABULARY,
        "joining": {
            "open": "POST a tip to %s with {\"chain\", \"tip\", \"url\"}. "
                    "No account, no key. The url field is what makes you "
                    "witnessable by everyone else, so do not omit it."
                    % SELF_OBSERVE,
            "signed": "If you would rather nobody - including the operator "
                      "of this deployment - be able to submit under your "
                      "name, enrol an Ed25519 public key at "
                      "/x/signed/enroll and submit at %s. You keep the "
                      "private key. See /x/signed/spec." % SELF_SIGNED,
        },
        "what_this_does_not_do": [
            "It does not witness anything. It is a phone book.",
            "It does not establish that anyone listed is a peer of anyone "
            "else listed, or of us.",
            "It does not prove a listed chain is honest, only that it "
            "submitted to us and when.",
            "It cannot make another operator witness you. Their server "
            "decides that. This only makes sure they know you exist.",
            "It reflects submissions to this deployment. Another node "
            "publishing its own roster may list a different set.",
            "The status word is not a statement about anyone's uptime. It "
            "is elapsed time since our last recorded observation.",
        ],
        "drop_in":
            "meshwitness.py reads this route and witnesses every entry on "
            "it. Standard library, one file, one cron line.",
    }


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return _spec(), 200
    if action == "health":
        return _health(ctx)
    if action in ("list", "", "status"):
        return _list(ctx)
    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


## `modules/router.py`

234 lines, 7196 bytes

```python
"""
Module router - /x/<module>/<action>

Dispatches to modules/<module>.py, which exposes:

    def handle(method, action, data, api_key, ctx): return payload, status

A module may declare PUBLIC = {("GET","attest"), ...} for routes that need no
API key. Default is closed - a route has to be opted open deliberately.

RATE LIMITING
-------------
Authenticated routes reuse the server's own check_rate (60/min, 1000/hour per
key), so module traffic counts against the same budget as /api/govern rather
than sitting outside it.

Public routes have no key to meter, so they are metered per client address on
a deliberately tighter budget. Without this, an unauthenticated endpoint is an
open invitation. The window store is bounded and self-pruning.

PAYLOAD CAP
-----------
Module bodies are capped. Nothing here needs a megabyte of JSON, and an
uncapped body on a public route is a memory exhaustion vector.

POST SUPPORT WITHOUT EDITING server.py
--------------------------------------
server.py has an /x/ branch in do_GET but not in do_POST, so POST routes
return the server's 404. The correct fix is four lines in do_POST. This is
the fix for when that is not practical.

On first import, this module patches Handler.do_POST to check for /x/ before
falling through to the original. The patch is idempotent, keeps the original
behaviour for every other path, and reverts on restart because it lives in
memory rather than on disk.

The catch, stated plainly: a module is only imported when a request reaches
the router, and the only working entry point is do_GET. So after every deploy
the first /x/ request must be a GET - after that, POST works until the next
restart. Anything hitting /x/ with a GET does it, including a browser.

This is a workaround for an editing constraint, not good architecture. If the
four lines ever go into do_POST, this patch detects the branch is already
there and does nothing.
"""

import importlib, json, sys, time
from collections import defaultdict, deque

VERSION = "3.2"

MAX_BODY_KEYS = 200
MAX_BODY_CHARS = 200000

PUBLIC_PER_MIN = 30
PUBLIC_PER_HOUR = 300
_ip_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_ip_last_prune = [0.0]

_c = {}
_patched = [False]


def _install_post(s):
    """Add an /x/ branch to do_POST at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_POST"):
        return "no handler"
    if getattr(H, "_x_post_patched", False):
        _patched[0] = True
        return "already installed"
    original = H.do_POST

    def do_POST(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.startswith("/x/"):
            try:
                body = s.read_body(self)
            except Exception:
                body = {}
            payload, status = route(self, p, body)
            s.send_json(self, payload, status)
            return
        return original(self)

    H.do_POST = do_POST
    H._x_post_patched = True
    _patched[0] = True
    print("ROUTER: /x/ POST branch installed at runtime", flush=True)
    return "installed"


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _load(name):
    m = _c.get(name)
    if m is None:
        m = importlib.import_module("modules." + name)
        _c[name] = m
    return m


def _client(h):
    """Prefer the forwarded address - behind a proxy the socket address is
    the proxy, which would meter every visitor as one client."""
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
    except Exception:
        pass
    try:
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def _prune_ips(t):
    if t - _ip_last_prune[0] < 300:
        return
    _ip_last_prune[0] = t
    dead = [k for k, w in _ip_wins.items()
            if (not w["hour"]) or w["hour"][-1] < t - 3600]
    for k in dead:
        del _ip_wins[k]


def _check_ip(ip):
    t = time.time()
    _prune_ips(t)
    w = _ip_wins[ip]
    while w["min"] and w["min"][0] < t - 60:
        w["min"].popleft()
    while w["hour"] and w["hour"][0] < t - 3600:
        w["hour"].popleft()
    if len(w["min"]) >= PUBLIC_PER_MIN:
        return False, "rate_limit_minute"
    if len(w["hour"]) >= PUBLIC_PER_HOUR:
        return False, "rate_limit_hour"
    w["min"].append(t)
    w["hour"].append(t)
    return True, None


def _too_big(data):
    if not isinstance(data, dict):
        return False
    if len(data) > MAX_BODY_KEYS:
        return True
    try:
        return len(json.dumps(data)) > MAX_BODY_CHARS
    except Exception:
        return True


def route(h, path, data):
    try:
        s = _srv()
        if s is None:
            return {"error": "server_not_found"}, 500

        if not _patched[0]:
            try:
                _install_post(s)
            except Exception as _e:
                print("ROUTER: post patch failed - " + str(_e), flush=True)

        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path",
                    "expected": "/x/<module>/<action>"}, 404
        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""

        if isinstance(data, dict) and data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}

        if _too_big(data):
            return {"error": "payload_too_large",
                    "limit_chars": MAX_BODY_CHARS,
                    "limit_keys": MAX_BODY_KEYS}, 413

        try:
            m = _load(name)
        except Exception:
            return {"error": "unknown_module", "module": name}, 404
        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle"}, 500

        method = h.command
        public = getattr(m, "PUBLIC", set())
        is_public = (method, act) in public or (method, "") in public

        a = s.get_bearer(h)

        if is_public:
            if a and not s.get_key(a):
                a = None
            if not a:
                ok, why = _check_ip(_client(h))
                if not ok:
                    return {"error": why,
                            "message": "Public endpoints are rate limited per client. Use an API key for the normal budget."}, 429
        else:
            if not a or not s.get_key(a):
                return {"error": "invalid_api_key"}, 401

        if a:
            try:
                ok, why = s.check_rate(a)
                if not ok:
                    return {"error": why}, 429
            except Exception:
                pass

        ctx = {"conn": s._conn, "lock": s._db_lock,
               "seal": s.seal, "get_key": s.get_key}
        return m.handle(method, act, data, a, ctx)

    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500

```
