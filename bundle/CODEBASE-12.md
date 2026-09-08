# Codebase — part 12 of 32

Contains:
- `modules/register.py`
- `modules/replay.py`
- `modules/reset.py`


## `modules/register.py`

1517 lines, 61178 bytes

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

VERSION = "1.2.0"
SUITE_VERSION = "oaas-checks-1"

# ---------------------------------------------------------------- constants

STALE_AFTER_DAYS = 90
CHALLENGE_TTL_SECONDS = 86400
MAX_FETCH_BYTES = 512 * 1024
FETCH_TIMEOUT = 8
WELL_KNOWN_PATH = "/.well-known/aileash-register.txt"
AI_TXT_PATHS = ["/.well-known/ai.txt", "/ai.txt"]
AI_TXT_PATH = AI_TXT_PATHS[0]   # the one quoted in guidance
FIELD_ALIASES = {
    "chain_tip_url": ["chain-tip-url", "chain-head", "witness-tip", "chain-anchor"],
    "verifier": ["verifier", "verify-chain", "consistency-proof", "self-check"],
    "contact": ["contact", "security-contact"],
}

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
    ("GET", "sealcheck"),
    ("GET", "tokens"),
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
        # v1.1: every issued token stays valid until it expires, so asking
        # for a new one never invalidates the one already published.
        c.execute("""CREATE TABLE IF NOT EXISTS register_token (
            token   TEXT PRIMARY KEY,
            domain  TEXT NOT NULL,
            issued  REAL NOT NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_token_domain ON register_token(domain, issued)")
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


def _extract_hash(result):
    """server.py's seal has returned different shapes over time. Accept them all."""
    if result is None:
        return None
    if isinstance(result, str):
        return result or None
    if isinstance(result, dict):
        for k in ("audit_hash", "hash", "audit", "block_hash", "sealed_hash"):
            v = result.get(k)
            if isinstance(v, str) and v:
                return v
        return None
    if isinstance(result, (tuple, list)):
        for item in result:
            h = _extract_hash(item)
            if h:
                return h
    return None


def _do_seal(ctx, event, result=None):
    """Call ctx['seal'] with the ONE correct signature and exactly once.

    This is the signature witness.py uses and that is proven against this
    server: seal(event, result, ts, api_key), returning (audit_hash,
    block_index, seq).

    WHY THIS WAS REWRITTEN (v1.2.0 -> safe):
    The previous version tried four different argument shapes in a loop. seal
    WRITES a block to the chain as a side effect. A shape that partially
    succeeded — wrote a block but returned something _extract_hash could not
    read — would fall through and the loop would call seal AGAIN, writing a
    SECOND block. Two blocks for one logical event, or a written-then-retried
    call, breaks the chain's prev-hash linkage. That is the fault that broke
    the chain. This calls seal once, the correct way, and never retries a call
    that may already have written.
    """
    seal = ctx["seal"]
    ts = _now()
    if result is None:
        result = event.get("kind") or event.get("type") or "register"
    if not isinstance(result, str):
        result = _canon(result)

    # Register events are not tied to a customer key. A stable module key
    # partitions them the way witness.py partitions anonymous observations.
    api_key = "register"

    out = seal(event, result, ts, api_key)

    h = _extract_hash(out)
    if h:
        return h
    if isinstance(out, (tuple, list)) and out and isinstance(out[0], str) and out[0]:
        return out[0]
    raise RuntimeError("seal returned no audit_hash: %r" % (out,))


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
    audit_hash = _do_seal(ctx, event, result=kind)

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
    audit_hash = _do_seal(ctx, event, result="checkpoint")

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

def _find_manifest(domain):
    """Try the well-known path first, then the root. Return (path, body, note)."""
    tried = []
    for path in AI_TXT_PATHS:
        ok, body, note = _fetch("https://%s%s" % (domain, path))
        tried.append({"path": path, "ok": ok, "note": note})
        if ok and body:
            return path, body, {"served_at": path, "attempts": tried, "observed": note}
    return None, None, {"served_at": None, "attempts": tried}


def _pick(fields, key):
    """Return (alias_used, value) for the first alias present."""
    for alias in FIELD_ALIASES[key]:
        if fields.get(alias):
            return alias, fields[alias]
    return None, None


def _run_checks(domain):
    """Observe what the domain serves. Every check names what it looked at."""
    checks = []

    path, body, mnote = _find_manifest(domain)
    checks.append({
        "id": "ai_txt_reachable",
        "asks": "Does %s serve a manifest at %s?" % (domain, " or ".join(AI_TXT_PATHS)),
        "pass": bool(body),
        "observed": mnote,
    })

    fields = {}
    if body:
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k and v and k not in fields:
                fields[k] = v

    tip_alias, tip_url = _pick(fields, "chain_tip_url")
    ver_alias, verifier = _pick(fields, "verifier")
    con_alias, contact = _pick(fields, "contact")

    missing = []
    if not tip_url:
        missing.append("chain tip url (%s)" % "/".join(FIELD_ALIASES["chain_tip_url"]))
    if not verifier:
        missing.append("verifier (%s)" % "/".join(FIELD_ALIASES["verifier"]))
    if not contact:
        missing.append("contact (%s)" % "/".join(FIELD_ALIASES["contact"]))

    checks.append({
        "id": "ai_txt_declares_required_fields",
        "asks": "Does the manifest declare a chain tip url, a verifier and a contact, under any accepted field name?",
        "pass": bool(body) and not missing,
        "observed": {
            "matched": {"chain_tip_url": tip_alias, "verifier": ver_alias, "contact": con_alias},
            "missing": missing,
            "field_count": len(fields),
        },
    })

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
                stripped = tbody.strip()
                if re.fullmatch(r"[0-9a-fA-F]{64}", stripped):
                    parsed_tip = stripped
        tip_value = parsed_tip
        checks.append({
            "id": "chain_tip_served",
            "asks": "Does the declared chain tip url return a tip value?",
            "pass": bool(parsed_tip),
            "observed": dict(tnote, declared_as=tip_alias, tip_field_found=bool(parsed_tip)),
        })
        checks.append({
            "id": "chain_tip_is_sha256",
            "asks": "Is the served tip a 64-character hex digest?",
            "pass": bool(parsed_tip) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", parsed_tip or "")),
            "observed": {"tip": parsed_tip},
        })
    else:
        for cid, asks in (("chain_tip_served", "Does the declared chain tip url return a tip value?"),
                          ("chain_tip_is_sha256", "Is the served tip a 64-character hex digest?")):
            checks.append({"id": cid, "asks": asks, "pass": False,
                           "observed": {"error": "no chain tip url declared"}})

    checks.append({
        "id": "verifier_named",
        "asks": "Does the manifest name instructions or a tool a third party can use to check the chain themselves?",
        "pass": bool(verifier),
        "observed": {"verifier": verifier, "declared_as": ver_alias},
    })

    passed = all(c["pass"] for c in checks)
    return {
        "suite": SUITE_VERSION,
        "ran_at": _iso(_now()),
        "manifest_path": path,
        "all_passed": passed,
        "failed": [c["id"] for c in checks if not c["pass"]],
        "checks": checks,
        "tip_observed": tip_value,
        "contact": contact,
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
            "Simplest, nothing to edit: if your manifest already carries a `Domain: <yourdomain>` line matching the domain you are claiming, POST /x/register/claim and you are listed. A manifest served from your domain naming your domain could only have been published by you.",
            "If your manifest does not name itself, use the token route instead:",
            "1. POST /x/register/challenge with {\"domain\": \"example.com\"} — returns a one-time token.",
            "2. Serve that token at https://example.com%s, or add a `Register-Token: <token>` line to your manifest at %s" % (WELL_KNOWN_PATH, " or ".join(AI_TXT_PATHS)),
            "Any token issued in the last 24 hours will verify — asking for a new one does not invalidate one you already published. See /x/register/tokens?domain=example.com",
            "3. POST /x/register/claim with {\"domain\": \"example.com\"} — we fetch, verify, run the checks and seal the result.",
            "Opt out at any time with a `Register: no` line in the manifest — the register refuses the claim and says so.",
            "Nobody is listed by the operator. A domain lists itself by proving it controls the domain.",
        ],
        "manifest_paths_tried": AI_TXT_PATHS,
        "field_aliases": FIELD_ALIASES,
        "checks_run": [
            "ai_txt_reachable", "ai_txt_declares_required_fields",
            "chain_tip_served", "chain_tip_is_sha256", "verifier_named",
        ],
        "trees": {
            "event_tree": "RFC 6962 ordered tree over every register event in write order. Answers append-only. Verifies with any standard Certificate Transparency verifier.",
            "domain_tree": "Sorted tree over the domains listed at a checkpoint, odd nodes promoted, domain-separated prefixes. Answers absence.",
            "note": "The two roots answer different questions and deliberately never match.",
        },
        "proof_of_control": {"preferred": "manifest-self-declaration (a Domain: line naming itself)",
                             "fallback": "one-time token served at a path we name",
                             "opt_out": "a `Register: no` line in the manifest"},
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

    # Idempotent: if a live token already exists for this domain, return THAT
    # one. Minting a new token on every request is how an operator ends up with
    # a published token the register no longer recognises.
    existing = _live_tokens(ctx, domain)
    if existing:
        token, issued = existing[0]
        return {
            "ok": True,
            "domain": domain,
            "token": token,
            "reused": True,
            "issued_at": _iso(issued),
            "expires_at": _iso(issued + CHALLENGE_TTL_SECONDS),
            "serve_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                         "or a `Register-Token: %s` line in your manifest at %s"
                         % (token, " or ".join(AI_TXT_PATHS))],
            "then": "POST /x/register/claim {\"domain\": \"%s\"}" % domain,
            "note": "This is the token already issued for this domain. Requesting "
                    "again does not replace it, so anything you have already "
                    "published stays valid.",
        }, 200

    token = "aileash-register-" + secrets.token_hex(16)
    ts = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO register_challenge (domain, token, issued) VALUES (?,?,?)"
            " ON CONFLICT(domain) DO UPDATE SET token=excluded.token, issued=excluded.issued",
            (domain, token, ts))
        ctx["conn"].execute(
            "INSERT OR REPLACE INTO register_token (token, domain, issued) VALUES (?,?,?)",
            (token, domain, ts))
        ctx["conn"].execute(
            "DELETE FROM register_token WHERE domain=? AND issued<?",
            (domain, ts - CHALLENGE_TTL_SECONDS))
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


def _live_tokens(ctx, domain):
    """Every token issued for this domain that has not expired, newest first."""
    cutoff = _now() - CHALLENGE_TTL_SECONDS
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT token, issued FROM register_token WHERE domain=? AND issued>=?"
            " ORDER BY issued DESC", (domain, cutoff)).fetchall()
    return [(r[0], r[1]) for r in rows]


def _verify_self_declaration(domain):
    """Proof of control with nothing to edit.

    A manifest served over https from the domain, whose own `Domain:` line
    names that same domain, was published by whoever controls the domain.
    Nobody else can put a file there. That IS the consent a token was
    standing in for, so a token is only needed when the manifest does not
    name itself (or the operator has opted out).

    An operator who does not want to be listed writes `Register: no`.
    """
    path, body, mnote = _find_manifest(domain)
    if not body:
        return False, {"reason": "no manifest served", "attempts": mnote}

    declared = None
    opted_out = False
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip().lower()
        if k == "domain" and declared is None:
            declared = v.lstrip("www.")
        if k == "register" and v in ("no", "false", "off", "opt-out"):
            opted_out = True

    if opted_out:
        return False, {"reason": "manifest declares Register: no",
                       "respected": True, "served_at": path}
    if not declared:
        return False, {"reason": "manifest does not declare a Domain: line",
                       "served_at": path}
    if declared != domain:
        return False, {"reason": "manifest declares a different domain",
                       "declared": declared, "claimed": domain, "served_at": path}

    return True, {"method": "manifest-self-declaration", "served_at": path,
                  "declared_domain": declared, "observed": mnote.get("observed"),
                  "what_this_proves": "The manifest at this path names this domain "
                                      "as its own. Only the party controlling the "
                                      "domain can serve that file."}


def _verify_any_token(ctx, domain):
    """Accept ANY live token for this domain. Requesting a new one must never
    invalidate one the operator has already published."""
    tokens = _live_tokens(ctx, domain)
    if not tokens:
        return False, None, {"error": "no_live_token"}
    last = None
    for token, issued in tokens:
        ok, evidence = _verify_token(domain, token)
        if ok:
            evidence["token_issued"] = _iso(issued)
            evidence["tokens_live"] = len(tokens)
            return True, token, evidence
        last = evidence
    return False, None, {"tokens_live": len(tokens), "none_matched": True,
                         "last_attempt": last}


def _verify_token(domain, token):
    ok, body, note = _fetch("https://%s%s" % (domain, WELL_KNOWN_PATH))
    if ok and body and token in body:
        return True, {"method": "well-known", "observed": note}
    tried = [{"path": WELL_KNOWN_PATH, "note": note}]
    for path in AI_TXT_PATHS:
        ok2, body2, note2 = _fetch("https://%s%s" % (domain, path))
        tried.append({"path": path, "note": note2})
        if ok2 and body2:
            for line in body2.splitlines():
                if line.strip().lower().startswith("register-token:") and token in line:
                    return True, {"method": "manifest:%s" % path, "observed": note2}
    return False, {"method": None, "tried": tried}


def _claim(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400

    verified, evidence = _verify_self_declaration(domain)
    if not verified:
        self_decl_evidence = evidence
        if evidence.get("respected"):
            return {"ok": False, "domain": domain,
                    "error": "this domain has opted out with a `Register: no` line",
                    "evidence": evidence}, 403
        if not _live_tokens(ctx, domain):
            return {"ok": False, "domain": domain,
                    "error": "could not prove control of this domain",
                    "self_declaration": self_decl_evidence,
                    "how_to_fix": [
                        "Easiest: add a `Domain: %s` line to your manifest at %s."
                        % (domain, " or ".join(AI_TXT_PATHS)),
                        "Or: POST /x/register/challenge and serve the token it returns.",
                    ]}, 400
        verified, matched_token, tok_evidence = _verify_any_token(ctx, domain)
        evidence = dict(tok_evidence or {}, self_declaration=self_decl_evidence)
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
    contact = checks.get("contact")
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
        ctx["conn"].execute("DELETE FROM register_token WHERE domain=?", (domain,))
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
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404
    verified, evidence = _verify_self_declaration(domain)
    if not verified:
        if not _live_tokens(ctx, domain):
            return {"error": MESSAGES["no_challenge"], "domain": domain,
                    "note": "Withdrawal is proved the same way listing is."}, 404
        verified, matched_token, evidence = _verify_any_token(ctx, domain)
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
        ctx["conn"].execute("DELETE FROM register_token WHERE domain=?", (domain,))
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
        if action == "tokens":
            d = _clean_domain(q.get("domain"))
            if not d:
                return {"error": MESSAGES["bad_domain"]}, 400
            live = _live_tokens(ctx, d)
            return {"domain": d, "live_tokens": len(live),
                    "tokens": [{"token": t, "issued": _iso(i),
                                "expires": _iso(i + CHALLENGE_TTL_SECONDS)} for t, i in live],
                    "note": "Any of these will verify. Requesting a new token does not "
                            "invalidate one you have already published."}, 200
        if action == "sealcheck":
            probe = {"user_id": "register:sealcheck", "type": "register_sealcheck",
                     "kind": "probe", "at": _iso(_now())}
            try:
                h = _do_seal(ctx, probe, result="sealcheck")
                return {"ok": True, "audit_hash": h,
                        "note": "The register can seal. This probe is a real sealed block."}, 200
            except Exception as e:
                return {"ok": False, "error": "seal_failed", "detail": str(e),
                        "note": "Nothing was written. The detail names what server.py's seal did."}, 500
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


## `modules/reset.py`

126 lines, 4723 bytes

```python
# modules/reset.py
"""
modules/reset.py  —  ONE-TIME chain reset

Clears the audit_log so the chain starts fresh at genesis. Use this once,
after deploying the fixed register.py, to recover from a broken chain when
there is no backup worth keeping and no real customer data to preserve.

SAFETY:
  * KEYED. Requires the operator API key. A stranger cannot trigger it.
  * Requires an explicit confirm word in the body, so it cannot fire by
    accident or from a stray click.
  * Reports the block count before and after, so you can see it worked.
  * Touches ONLY audit_log. It does not delete files, does not touch the
    OTS anchors, does not touch customer/signup tables.

USE:
  1. Deploy this file into modules/.
  2. Deploy the FIXED register.py FIRST (single-seal version) or the fresh
     chain will just break again.
  3. Open, with your key, a POST to /x/reset/chain carrying
     {"confirm": "RESET-THE-CHAIN"}.
     Easiest from a phone: use the console, or any tool that can send a POST
     with the Authorization header. A plain browser GET will NOT do it — that
     is deliberate.
  4. Check /x/reset/status (GET, keyed) to see the block count.
  5. REMOVE this file afterwards. Do not leave a reset route deployed.

After it runs, the very next seal writes block 1 of a clean chain, and
/api/verify-chain should read OK again.
"""

import time

VERSION = "1.0.0"

# Nothing here is public. Reset must never be reachable without the key.
PUBLIC = set()

CONFIRM_WORD = "RESET-THE-CHAIN"


def _count(ctx):
    with ctx["lock"]:
        try:
            r = ctx["conn"].execute("SELECT COUNT(*) FROM audit_log").fetchone()
            return int(r[0]) if r else 0
        except Exception as e:  # noqa: BLE001
            return "error: " + type(e).__name__


def _tip(ctx):
    with ctx["lock"]:
        try:
            r = ctx["conn"].execute(
                "SELECT audit_hash, id FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not r:
                return None, 0
            return r[0], r[1]
        except Exception:
            return None, 0


def handle(method, action, data, api_key, ctx):
    # Keyed, always. No key, no reset — no matter the method or action.
    if not api_key:
        return {"error": "api key required — reset is operator-only"}, 401

    data = data or {}

    if method == "GET" and action == "status":
        tip, height = _tip(ctx)
        return {
            "module": "reset",
            "version": VERSION,
            "audit_log_blocks": _count(ctx),
            "current_tip": tip,
            "current_height": height,
            "how_to_reset": "POST /x/reset/chain with your key and "
                            '{"confirm": "%s"}' % CONFIRM_WORD,
            "warning": "Reset clears audit_log and cannot be undone. There is "
                       "no backup. Only do this if you mean it.",
        }, 200

    if method == "POST" and action == "chain":
        if data.get("confirm") != CONFIRM_WORD:
            return {
                "error": "confirmation required",
                "send": {"confirm": CONFIRM_WORD},
                "note": "This clears the whole chain and cannot be undone. "
                        "The confirm word is there so this cannot happen by accident.",
            }, 400

        before = _count(ctx)

        with ctx["lock"]:
            try:
                # Clear the chain table only. Nothing else is touched.
                ctx["conn"].execute("DELETE FROM audit_log")
                # Reset the autoincrement so the fresh chain starts at id 1.
                try:
                    ctx["conn"].execute(
                        "DELETE FROM sqlite_sequence WHERE name='audit_log'")
                except Exception:
                    pass  # table may not use sqlite_sequence; harmless
                ctx["conn"].commit()
            except Exception as e:  # noqa: BLE001
                return {"error": "reset failed",
                        "detail": type(e).__name__ + ": " + str(e),
                        "note": "Nothing may have been cleared. Check status."}, 500

        after = _count(ctx)
        return {
            "ok": True,
            "reset_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "blocks_before": before,
            "blocks_after": after,
            "next": "The next seal writes block 1 of a clean chain. Check "
                    "/api/verify-chain — it should read OK. Then REMOVE this "
                    "reset module from modules/ so the route is gone.",
        }, 200

    return {"error": "unknown action",
            "use": ["GET /x/reset/status", "POST /x/reset/chain"]}, 404

```
