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

VERSION = "1.1.0"
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
    """Call ctx['seal'] whichever signature it has. Never swallow the reason.

    server.py's seal is seal(event, result, ts) — the audit_log row is built from
    {prev_hash, ts, event, result}, so result and ts are not optional. The other
    shapes are kept so this module still works against an older or newer server.
    """
    seal = ctx["seal"]
    ts = _now()
    if result is None:
        result = event.get("kind") or event.get("type") or "register"
    result_json = _canon(result) if not isinstance(result, str) else result
    attempts = []
    for args in ((event, result_json, ts),
                 (event, result, ts),
                 (event, result_json),
                 (event,)):
        try:
            result = seal(*args)
        except TypeError as e:
            attempts.append("%d-arg: TypeError %s" % (len(args), e))
            continue
        except Exception as e:
            raise RuntimeError("seal raised %s: %s" % (type(e).__name__, e))
        h = _extract_hash(result)
        if h:
            return h
        attempts.append("%d-arg: returned %r with no hash" % (len(args), result))
    raise RuntimeError("seal produced no audit_hash — " + " | ".join(attempts))


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
            "1. POST /x/register/challenge with {\"domain\": \"example.com\"} — returns a one-time token.",
            "2. Serve that token at https://example.com%s, or add a `Register-Token: <token>` line to your manifest at %s" % (WELL_KNOWN_PATH, " or ".join(AI_TXT_PATHS)),
            "Any token issued in the last 24 hours will verify — asking for a new one does not invalidate one you already published. See /x/register/tokens?domain=example.com",
            "3. POST /x/register/claim with {\"domain\": \"example.com\"} — we fetch, verify, run the checks and seal the result.",
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

    if not _live_tokens(ctx, domain):
        return {"error": MESSAGES["no_challenge"], "domain": domain}, 404

    verified, matched_token, evidence = _verify_any_token(ctx, domain)
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
    if not _live_tokens(ctx, domain):
        return {"error": MESSAGES["no_challenge"], "domain": domain,
                "note": "Withdrawal is proved the same way listing is. Request a challenge, serve the token, then withdraw."}, 404

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
