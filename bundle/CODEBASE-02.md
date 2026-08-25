# Codebase — part 2 of 26

Contains:
- `modules/_ _ i n i t _ _ . p y`
- `modules/bind.py`
- `modules/capture.py`
- `modules/codebase.py`
- `modules/complete.py`


## `modules/_ _ i n i t _ _ . p y`

2 lines, 37 bytes

```
# makes this folder a python package

```


## `modules/bind.py`

483 lines, 21914 bytes

```python
#!/usr/bin/env python3
"""
modules/bind.py  -  the signed lane

WHY THIS EXISTS
---------------
Name binding used to depend on a fetcher reaching a URL and parsing JSON out
of it. Three things were wrong with that and a reviewer found all three:

  - a page that is reachable but serves HTML does not bind, and the platform
    described it as if it did
  - a name with no binding is claimable by anybody, so a peer who followed
    that description was left one submission away from being squatted
  - the failure text asserted the URL was unreachable, when all the check had
    established was that the response was not JSON. Reachability and
    parseability are two different facts and conflating them put a false
    statement in a sealed block

This module removes the fetcher from the trust path entirely.

A peer signs their own submission with a credential. Binding then rests on
possession of a secret rather than on my crawler reaching anything, parsing
anything, or on my description of what happens when it cannot. Nobody has to
stand up an endpoint whose only purpose is to satisfy someone else's fetcher.

WHAT A SIGNED BINDING PROVES, EXACTLY
-------------------------------------
That whoever submitted holds the credential issued for that name, on the date
it was issued, and that the submission has not been altered since signing.

WHAT IT DOES NOT PROVE
----------------------
That they own the domain. That they are who the name suggests. That anything
in their chain is true. A credential is a shared secret between two parties
and nothing more - it makes a name unstealable, not a claim honest. Domain
control is a separate check this module does not perform and does not imply.

    POST /x/bind/issue      issue a credential for a name   (operator key)
    POST /x/bind/claim      seal a dated claim marker       (operator key)
    POST /x/bind/revoke     revoke a credential             (operator key)
    POST /x/bind/submit     signed tip submission           (signature only)
    GET  /x/bind/name       binding state and history       (public)
    GET  /x/bind/conflicts  every contested name            (public)
    GET  /x/bind/spec       how to sign, in full            (public)
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

VERSION = "1.0"

PUBLIC = {("GET", "name"), ("GET", "conflicts"), ("GET", "spec")}

SIG_PREFIX = b"AILEASH-BIND-v1:"
CLOCK_SKEW = 300          # seconds either side that a signature stays valid
NONCE_KEEP = 3600         # how long a used nonce is remembered

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS bind_credential("
                  "key_id TEXT PRIMARY KEY,name TEXT NOT NULL,secret TEXT NOT NULL,"
                  "issued_to TEXT,issued REAL,revoked REAL,revoke_reason TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_claim("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "claimant TEXT,claimed_at REAL,note TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_submission("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "tip TEXT,key_id TEXT,ts REAL,nonce TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_nonce("
                  "nonce TEXT PRIMARY KEY,ts REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_name ON bind_submission(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_claim ON bind_claim(name)")
        c.commit()
    _ready = True


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _clean_name(n):
    n = str(n or "").strip().lower()[:120]
    return "".join(ch for ch in n if ch.isalnum() or ch in ".-_/:")


def _sig(secret, name, tip, ts, nonce):
    material = SIG_PREFIX + _canon({"name": name, "tip": tip,
                                    "ts": int(ts), "nonce": nonce}).encode("utf-8")
    return hmac.new(bytes.fromhex(secret), material, hashlib.sha256).hexdigest()


# ----------------------------------------------------------------------

def _issue(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400
    to = str(data.get("issued_to", "")).strip()[:200] or None

    with ctx["lock"]:
        live = ctx["conn"].execute(
            "SELECT key_id FROM bind_credential WHERE name=? AND revoked IS NULL",
            (name,)).fetchone()
    if live and not data.get("replace"):
        return {"error": "credential_already_issued", "name": name,
                "key_id": live[0],
                "message": "A live credential exists for this name. Send "
                           "replace true to revoke it and issue another, which "
                           "is itself sealed."}, 409

    secret = secrets.token_hex(32)
    key_id = "bk_" + secrets.token_hex(8)
    now = time.time()

    ev = {"user_id": "bind:" + name[:40], "action": "credential_issued",
          "amount": 0, "country": "UK", "device_id": "bind",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "CREDENTIAL_ISSUED", "score": 0, "bind_version": VERSION,
           "name": name, "key_id": key_id, "issued_to": to,
           "secret_sealed": False,
           "detail": "name=%s;key_id=%s;issued_to=%s" % (name, key_id, to)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        if live:
            ctx["conn"].execute(
                "UPDATE bind_credential SET revoked=?, revoke_reason=? "
                "WHERE key_id=?", (now, "replaced by " + key_id, live[0]))
        ctx["conn"].execute(
            "INSERT INTO bind_credential(key_id,name,secret,issued_to,issued,"
            "audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
            (key_id, name, secret, to, now, h, idx))
        ctx["conn"].commit()

    return {"name": name, "key_id": key_id, "secret": secret,
            "issued_to": to, "issued_at": _iso(now),
            "sealed_in_chain": h, "block_index": idx, "receipt_seq": seq,
            "send_this_once": ("The secret is shown here and nowhere else. It "
                               "is not sealed into the chain and cannot be "
                               "recovered - if it is lost, revoke and reissue."),
            "how_to_sign": "/x/bind/spec",
            "what_it_proves": ("Possession of this secret. It does not prove "
                               "domain ownership and this platform does not "
                               "check that."),
            "replaced": live[0] if live else None}, 200


def _claim(ctx, api_key, data):
    """A dated marker, for a name that cannot yet be bound.

    This does not bind anything. It puts the claim in the chain at a known
    time, so a later competing submission is provably second and the conflict
    is on the public record rather than being settled privately by whoever
    runs the platform.
    """
    name = _clean_name(data.get("name"))
    claimant = str(data.get("claimant", "")).strip()[:200]
    if not name or not claimant:
        return {"error": "name_and_claimant_required"}, 400
    note = str(data.get("note", "")).strip()[:500] or None
    now = time.time()

    ev = {"user_id": "bind:" + name[:40], "action": "name_claimed", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "NAME_CLAIMED", "score": 0, "bind_version": VERSION,
           "name": name, "claimant": claimant, "note": note,
           "detail": "name=%s;claimant=%s" % (name, claimant)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO bind_claim(name,claimant,claimed_at,note,audit_hash,"
            "block_index) VALUES(?,?,?,?,?,?)",
            (name, claimant, now, note, h, idx))
        ctx["conn"].commit()

    return {"name": name, "claimant": claimant, "claimed_at": _iso(now),
            "sealed_in_chain": h, "block_index": idx, "receipt_seq": seq,
            "what_this_is": ("A dated marker, not a binding. Anyone can still "
                             "submit under this name - but their block is "
                             "provably later than this one, and the conflict "
                             "is public."),
            "what_this_is_not": ("Proof that the claimant owns the name, and "
                                 "not a substitute for a credential. Issue one "
                                 "at /x/bind/issue and the name stops being "
                                 "claimable at all.")}, 200


def _revoke(ctx, api_key, data):
    key_id = str(data.get("key_id", "")).strip()
    if not key_id:
        return {"error": "key_id_required"}, 400
    reason = str(data.get("reason", "")).strip()[:300] or "not stated"
    now = time.time()

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT name, revoked FROM bind_credential WHERE key_id=?",
            (key_id,)).fetchone()
    if not row:
        return {"error": "unknown_key_id"}, 404
    if row[1]:
        return {"error": "already_revoked", "revoked_at": _iso(row[1])}, 409

    ev = {"user_id": "bind:" + row[0][:40], "action": "credential_revoked",
          "amount": 0, "country": "UK", "device_id": "bind", "anomaly": 0,
          "device_risk": 1}
    res = {"decision": "CREDENTIAL_REVOKED", "score": 0, "name": row[0],
           "key_id": key_id, "reason": reason,
           "detail": "key_id=%s;reason=%s" % (key_id, reason)}
    h, idx, _ = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE bind_credential SET revoked=?, revoke_reason=? WHERE key_id=?",
            (now, reason, key_id))
        ctx["conn"].commit()

    return {"key_id": key_id, "name": row[0], "revoked_at": _iso(now),
            "reason": reason, "sealed_in_chain": h,
            "note": "Submissions already bound stay bound. Revocation stops "
                    "future ones and does not rewrite the past."}, 200


def _submit(ctx, data):
    """Signed submission. No account, no operator key - the signature is the
    authentication, which is the whole point of the lane."""
    name = _clean_name(data.get("name"))
    tip = str(data.get("tip", "")).strip().lower()
    key_id = str(data.get("key_id", "")).strip()
    sig = str(data.get("signature", "")).strip().lower()
    nonce = str(data.get("nonce", "")).strip()[:80]
    try:
        ts = int(data.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0

    missing = [k for k, v in (("name", name), ("tip", tip), ("key_id", key_id),
                              ("signature", sig), ("nonce", nonce)) if not v]
    if missing or not ts:
        return {"error": "incomplete_submission",
                "missing": missing + ([] if ts else ["ts"]),
                "how_to_sign": "/x/bind/spec"}, 400
    if len(tip) != 64:
        return {"error": "tip_must_be_64_hex"}, 400

    now = time.time()
    if abs(now - ts) > CLOCK_SKEW:
        return {"error": "timestamp_outside_window",
                "your_ts": ts, "our_ts": int(now),
                "window_seconds": CLOCK_SKEW,
                "why": "a signature valid forever is a signature that can be "
                       "replayed forever"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT secret, revoked, issued_to FROM bind_credential "
            "WHERE key_id=? AND name=?", (key_id, name)).fetchone()
        used = ctx["conn"].execute(
            "SELECT 1 FROM bind_nonce WHERE nonce=?", (nonce,)).fetchone()

    if not cred:
        return {"error": "no_credential_for_that_name_and_key"}, 401
    if cred[1]:
        return {"error": "credential_revoked", "revoked_at": _iso(cred[1])}, 401
    if used:
        return {"error": "nonce_already_used",
                "why": "each signature may be presented once"}, 409

    expected = _sig(cred[0], name, tip, ts, nonce)
    if not hmac.compare_digest(expected, sig):
        return {"error": "signature_did_not_verify",
                "check": "/x/bind/spec sets out the exact bytes signed"}, 401

    ev = {"user_id": "bind:" + name[:40], "action": "signed_tip", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "TIP_BOUND", "score": 0, "bind_version": VERSION,
           "name": name, "tip": tip, "key_id": key_id, "binding": "signature",
           "detail": "name=%s;tip=%s;key_id=%s" % (name, tip, key_id)}
    h, idx, seq = ctx["seal"](ev, res, now, None)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO bind_submission(name,tip,key_id,ts,nonce,audit_hash,"
            "block_index) VALUES(?,?,?,?,?,?,?)",
            (name, tip, key_id, now, nonce, h, idx))
        ctx["conn"].execute("INSERT OR IGNORE INTO bind_nonce(nonce,ts) "
                            "VALUES(?,?)", (nonce, now))
        ctx["conn"].execute("DELETE FROM bind_nonce WHERE ts < ?",
                            (now - NONCE_KEEP,))
        ctx["conn"].commit()

    return {"bound": True, "name": name, "tip": tip, "key_id": key_id,
            "sealed_in_chain": h, "block_index": idx, "receipt_seq": seq,
            "binding": "signature",
            "what_this_proves": ("that the holder of the credential issued for "
                                 "this name submitted this tip, and that the "
                                 "submission has not been altered since it was "
                                 "signed"),
            "what_this_does_not_prove": ("that they own the domain the name "
                                         "resembles, or that anything in their "
                                         "chain is true"),
            "check_it": "/x/bind/name?name=" + name}, 200


# ----------------------------------------------------------------------

def _name(ctx, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT key_id, issued, revoked, issued_to FROM bind_credential "
            "WHERE name=? ORDER BY issued DESC", (name,)).fetchall()
        claims = ctx["conn"].execute(
            "SELECT claimant, claimed_at, note, block_index FROM bind_claim "
            "WHERE name=? ORDER BY claimed_at ASC", (name,)).fetchall()
        subs = ctx["conn"].execute(
            "SELECT tip, key_id, ts, block_index FROM bind_submission "
            "WHERE name=? ORDER BY ts DESC LIMIT 20", (name,)).fetchall()

    live = [c for c in cred if not c[2]]
    state = ("bound" if live else
             "claimed" if claims else
             "unbound")

    out = {
        "name": name,
        "state": state,
        "credential": ({"key_id": live[0][0], "issued_at": _iso(live[0][1]),
                        "issued_to": live[0][3]} if live else None),
        "claims": [{"claimant": c[0], "claimed_at": _iso(c[1]), "note": c[2],
                    "block_index": c[3]} for c in claims],
        "signed_submissions": [{"tip": s[0], "key_id": s[1],
                                "at": _iso(s[2]), "block_index": s[3]}
                               for s in subs],
        "revoked_credentials": [{"key_id": c[0], "revoked_at": _iso(c[2])}
                                for c in cred if c[2]],
    }
    if state == "bound":
        out["meaning"] = ("A live credential exists for this name. Only the "
                          "holder of it can submit under this name, and every "
                          "submission is signed.")
    elif state == "claimed":
        out["meaning"] = ("Claimed but not bound. The dated claim above is in "
                          "the chain, so a competing submission would be "
                          "provably later - but nothing prevents one being "
                          "made. Issue a credential to close that.")
        out["flag"] = "claimable"
    else:
        out["meaning"] = ("Nobody holds a credential for this name and nobody "
                          "has claimed it. It is claimable by anyone.")
        out["flag"] = "claimable"
    out["what_binding_never_proves"] = (
        "domain ownership. A credential is a shared secret; it makes a name "
        "unstealable on this network, not a claim honest.")
    return out, 200


def _conflicts(ctx):
    """Names where more than one party has a foot in the door. Published
    rather than resolved quietly, because who arbitrates is exactly the
    question a network like this should not be answering privately."""
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT claimant) FROM bind_claim "
            "GROUP BY name HAVING COUNT(DISTINCT claimant) > 1").fetchall()
        keys = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT key_id) FROM bind_credential "
            "WHERE revoked IS NULL GROUP BY name "
            "HAVING COUNT(DISTINCT key_id) > 1").fetchall()
    return {"contested_claims": [{"name": r[0], "claimants": r[1]} for r in rows],
            "names_with_multiple_live_credentials":
                [{"name": k[0], "credentials": k[1]} for k in keys],
            "note": ("A conflict is recorded, not arbitrated. This platform "
                     "does not decide who owns a name and should not.")}, 200


def _spec():
    return {
        "bind_version": VERSION,
        "why_it_exists": ("Name binding used to depend on a fetcher reaching a "
                          "URL and parsing JSON. A reachable page serving HTML "
                          "did not bind, an unbound name was claimable by "
                          "anyone, and the failure text asserted the URL was "
                          "unreachable when the check had only established the "
                          "response was not JSON. This lane removes the fetcher "
                          "from the trust path."),
        "signing": {
            "material": "AILEASH-BIND-v1: || canonical JSON of "
                        "{name, tip, ts, nonce}, keys sorted, separators "
                        "(',',':'), UTF-8",
            "algorithm": "HMAC-SHA256, secret as raw bytes from the hex issued",
            "signature": "lower-case hex digest",
            "ts": "unix seconds, must be within %d seconds of ours" % CLOCK_SKEW,
            "nonce": "any string, once only, remembered for %d seconds"
                     % NONCE_KEEP,
        },
        "worked_example": {
            "1": "material = b'AILEASH-BIND-v1:' + "
                 '\'{"name":"example.com","nonce":"abc123",'
                 '"tip":"<64 hex>","ts":1787000000}\'.encode()',
            "2": "signature = hmac.new(bytes.fromhex(secret), material, "
                 "hashlib.sha256).hexdigest()",
            "3": "POST /x/bind/submit with name, tip, ts, nonce, key_id, signature",
            "note": "the JSON in step 1 has its keys sorted, which is why "
                    "nonce appears before tip",
        },
        "what_a_signed_binding_proves": (
            "possession of the credential issued for that name, and that the "
            "submission is unaltered since signing"),
        "what_it_does_not_prove": [
            "domain ownership - not checked, not implied",
            "that the submitter is who the name suggests",
            "that anything in their chain is true",
        ],
        "claims": ("A name with no credential can be given a dated claim "
                   "marker. That is not a binding. It means a later competing "
                   "submission is provably second and the conflict is public."),
        "conflicts": ("Recorded at /x/bind/conflicts and never arbitrated here. "
                      "A network that lets its operator decide who owns a name "
                      "has replaced one trusted party with another."),
        "honest_limits": [
            "A credential is a shared secret. This platform holds a copy, so "
            "in principle it could sign on a peer's behalf - which is why a "
            "public-key lane is the right end state and this is the interim.",
            "Revoking a credential stops future submissions and does not "
            "unbind past ones.",
            "Nothing here checks DNS, TLS or WHOIS. Name resemblance to a real "
            "domain is not evidence of anything.",
        ],
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "name":
            return _name(ctx, data)
        if action == "conflicts":
            return _conflicts(ctx)

    if method == "POST":
        if action == "submit":
            return _submit(ctx, data)      # signature is the authentication
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "issue":
            return _issue(ctx, api_key, data)
        if action == "claim":
            return _claim(ctx, api_key, data)
        if action == "revoke":
            return _revoke(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "name", "conflicts"],
            "POST": ["issue", "claim", "revoke", "submit"]}, 404

```


## `modules/capture.py`

385 lines, 17851 bytes

```python
"""
One-button decision capture - /x/capture/<action>

WHAT IT IS
----------
A drop-in button for an operator's own review screen. A human reviews an AI
output, clicks once, and the decision is sealed into the chain with who
reviewed it, on what device, against which inputs, and how long they took.

WHY IT IS TWO CALLS AND NOT ONE
-------------------------------
The obvious version is a single POST carrying a dwell time measured in the
browser. That number is the whole point - it is what makes rubber stamping
visible - and a number the reviewed party computes for itself is not
evidence. Anyone can set it to whatever looks diligent.

So the widget opens a case first. The server records the open time. When the
reviewer commits, the server computes the dwell itself from two timestamps it
owns. The browser never supplies the figure it is being judged on.

Same reason the verdict is withheld between the two calls: the machine's
answer is sealed at open and only returned at seal, so the chain shows the
human committed before they saw it. Ordering is the one thing that separates
judgement from agreement.

KEYS IN BROWSERS
----------------
An API key pasted into page JavaScript is public. Anyone reading the source
can post as that operator, forever.

So capture accepts a CAPTURE TOKEN: minted server-side by the operator from
their real key, bound to one origin, short-lived, and able to do exactly two
things - open a case and seal it. It cannot read records, cannot see other
cases, cannot touch any other module. Same idea as a publishable key.

The real API key still works for server-to-server calls. It should never
appear in a page.

DEVICES ARE THE BILLING UNIT
----------------------------
Every capture carries a device_id, and distinct devices per calendar month is
what billing is counted on. The registry here is that count: first seen, last
seen, events, per month. An operator can query their own figure at any time
and reconcile it against an invoice, rather than being told a number.

Device identifiers are hashed on arrival. The chain and the registry hold a
fingerprint, never the raw identifier.

    POST /x/capture/token     mint a browser-safe capture token (real key only)
    POST /x/capture/open      start a case, server records the clock
    POST /x/capture/seal      commit a verdict, server computes the dwell
    GET  /x/capture/devices   this month's billable device count
    GET  /x/capture/case?id=  the sealed record of one capture
    GET  /x/capture/summary   dwell and divergence across recent captures
"""

import hashlib, hmac, json, os, re, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate", "approve", "reject"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN_TTL = 3600 * 12
MAX_OPEN_AGE = 3600 * 6

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_cases(case_id TEXT PRIMARY KEY,api_key TEXT,operator_fp TEXT,device_fp TEXT,input_hash TEXT,output_hash TEXT,machine_verdict TEXT,opened REAL,sealed REAL,human_verdict TEXT,dwell REAL,agreed INTEGER,note TEXT)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_devices(api_key TEXT,device_fp TEXT,month TEXT,first_seen REAL,last_seen REAL,events INTEGER DEFAULT 0,PRIMARY KEY(api_key,device_fp,month))")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_key ON capture_cases(api_key,opened)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_dev ON capture_devices(api_key,month)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("CAPTURE_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def _fp(v):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(v).strip().lower().encode(), hashlib.sha256).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _month(ts=None):
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m")


# ------------------------------------------------------------ capture token

def _mint(ctx, api_key, data):
    """Real key only. Returns a token safe to put in a page."""
    s = _secret()
    if not s:
        return {"error": "capture_secret_not_set",
                "message": "Set CAPTURE_SECRET in the environment first."}, 503
    origin = str(data.get("origin", "")).strip().lower()[:120]
    if not origin:
        return {"error": "origin_required",
                "message": "Bind the token to the site that will use it, e.g. https://app.yourcompany.com"}, 400
    try:
        ttl = min(int(data.get("ttl_seconds", TOKEN_TTL)), TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = TOKEN_TTL
    exp = int(time.time()) + max(60, ttl)
    body = api_key + "|" + origin + "|" + str(exp)
    sig = hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32]
    token = "cap_" + str(exp) + "_" + hashlib.sha256(origin.encode()).hexdigest()[:8] + "_" + sig
    return {"capture_token": token, "origin": origin,
            "expires": _iso(exp), "expires_in_seconds": exp - int(time.time()),
            "scope": ["capture:open", "capture:seal"],
            "note": "Safe to place in a page. It cannot read records, cannot see other cases, and cannot reach any other module. Mint a fresh one from your server as needed - never put your real API key in a browser."}, 200


def _verify_token(ctx, token, origin):
    """Returns the owning api_key, or None."""
    s = _secret()
    if not s or not token or not token.startswith("cap_"):
        return None
    parts = token.split("_")
    if len(parts) != 4:
        return None
    try:
        exp = int(parts[1])
    except ValueError:
        return None
    if exp < time.time():
        return None
    ohash, sig = parts[2], parts[3]
    if origin:
        o = str(origin).strip().lower()[:120]
        if hashlib.sha256(o.encode()).hexdigest()[:8] != ohash:
            return None
    else:
        o = None
    with ctx["lock"]:
        keys = ctx["conn"].execute("SELECT key FROM api_keys WHERE active=1").fetchall()
    for (k,) in keys:
        if o is None:
            continue
        body = k + "|" + o + "|" + str(exp)
        if hmac.compare_digest(hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32], sig):
            return k
    return None


def _resolve(ctx, api_key, data):
    """A real key wins; otherwise try a capture token bound to an origin."""
    if api_key:
        return api_key, "api_key"
    tok = str(data.get("capture_token", "")).strip()
    origin = str(data.get("origin", "")).strip()
    owner = _verify_token(ctx, tok, origin)
    if owner:
        return owner, "capture_token"
    return None, None


# ------------------------------------------------------------------ devices

def _touch_device(ctx, api_key, device_fp, ts):
    m = _month(ts)
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT events FROM capture_devices WHERE api_key=? AND device_fp=? AND month=?", (api_key, device_fp, m)).fetchone()
        if row:
            ctx["conn"].execute("UPDATE capture_devices SET last_seen=?,events=events+1 WHERE api_key=? AND device_fp=? AND month=?", (ts, api_key, device_fp, m))
            new = False
        else:
            ctx["conn"].execute("INSERT INTO capture_devices(api_key,device_fp,month,first_seen,last_seen,events) VALUES(?,?,?,?,?,1)", (api_key, device_fp, m, ts, ts))
            new = True
        ctx["conn"].commit()
    return new


def _devices(ctx, api_key, data):
    m = str(data.get("month", "")).strip() or _month()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT COUNT(*),SUM(events) FROM capture_devices WHERE api_key=? AND month=?", (api_key, m)).fetchone()
        months = ctx["conn"].execute("SELECT month,COUNT(*) FROM capture_devices WHERE api_key=? GROUP BY month ORDER BY month DESC LIMIT 12", (api_key,)).fetchall()
    n = rows[0] or 0
    return {"month": m, "billable_devices": n, "captures": rows[1] or 0,
            "rate_per_device": 0.50, "currency": "GBP",
            "estimated_charge": round(n * 0.50, 2),
            "history": [{"month": a, "devices": b} for a, b in months],
            "note": "A device counts once per calendar month however many captures it makes. Distinct devices is the billing unit - this is the same figure the invoice uses, so you can reconcile it yourself rather than being told a number."}, 200


# -------------------------------------------------------------------- cases

def _open(ctx, api_key, data):
    if not _secret():
        return {"error": "capture_secret_not_set"}, 503
    operator = str(data.get("operator_id", "")).strip()
    if not operator:
        return {"error": "operator_id_required",
                "message": "A capture with no named reviewer is not oversight."}, 400
    device = str(data.get("device_id", "")).strip()
    if not device:
        return {"error": "device_id_required",
                "message": "Devices are the billing unit and the record needs to say which one acted."}, 400

    ih = str(data.get("input_hash", "")).strip().lower()
    oh = str(data.get("output_hash", "")).strip().lower()
    for name, v in (("input_hash", ih), ("output_hash", oh)):
        if v and not HEX64.match(v):
            return {"error": "invalid_" + name,
                    "message": "Hash the content locally and send 64 hex characters. Never send the content itself."}, 400

    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    ts = time.time()
    ofp, dfp = _fp(operator), _fp(device)
    cid = "CAP-" + secrets.token_hex(5).upper()
    new_device = _touch_device(ctx, api_key, dfp, ts)

    detail = ("operator=" + (ofp or "")[:32] + ";device=" + (dfp or "")[:32] +
              ";input=" + (ih or "none") + ";output=" + (oh or "none") +
              ";machine_verdict_sealed=" + (mv or "none"))
    ev = {"user_id": "cap:" + cid, "action": "capture_opened", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "opened",
           "capture_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "no personal data and no content in this block - fingerprints and hashes only"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO capture_cases(case_id,api_key,operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed,note) VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                            (cid, api_key, ofp, dfp, ih or None, oh or None, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until seal",
            "new_device_this_month": new_device,
            "next": "POST the reviewer's verdict to /x/capture/seal with this case_id",
            "note": "The clock started here, on the server. The dwell time is not something the browser gets to report."}, 200


def _seal(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,machine_verdict,opened,sealed FROM capture_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_sealed",
                "message": "A capture commits once."}, 400

    hv = str(data.get("verdict", "")).strip().lower()
    if hv not in VERDICTS:
        return {"error": "invalid_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()

    ts = time.time()
    dwell = round(ts - row[3], 3)
    if dwell > MAX_OPEN_AGE:
        return {"error": "case_expired",
                "opened": _iso(row[3]),
                "message": "This case was opened more than six hours ago. Open a fresh one rather than sealing a stale clock."}, 400
    agreed = None if not row[2] else (1 if hv == row[2] else 0)

    detail = ("verdict=" + hv + ";dwell_seconds=" + str(dwell) +
              ";server_measured=true;reasoning=" + reasoning[:600])
    ev = {"user_id": "cap:" + cid, "action": "capture_sealed", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "sealed",
           "capture_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE capture_cases SET sealed=?,human_verdict=?,dwell=?,agreed=? WHERE case_id=? AND api_key=?",
                            (ts, hv, dwell, agreed, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "verdict": hv, "dwell_seconds": dwell,
           "machine_verdict": row[2], "sealed": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "measured_by": "server",
           "note": "Your verdict was sealed before this response revealed ours. The chain fixes that order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "sealed " + str(dwell) + "s after the case opened - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed FROM capture_cases WHERE case_id=? AND api_key=?", (cid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("cap:" + cid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("capture_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    return {"case_id": cid.upper(),
            "operator_fingerprint": (row[0] or "")[:16] + "...",
            "device_fingerprint": (row[1] or "")[:16] + "...",
            "input_hash": row[2], "output_hash": row[3],
            "machine_verdict": row[4], "opened": _iso(row[5]),
            "sealed": _iso(row[6]), "human_verdict": row[7],
            "dwell_seconds": row[8],
            "agreed": (None if row[9] is None else bool(row[9])),
            "events": events,
            "ordering_proof": "The opened block precedes the sealed block in the chain, and both timestamps are the server's."}, 200


def _summary(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM capture_cases WHERE api_key=? AND sealed IS NOT NULL", (api_key,)).fetchall()
        openc = ctx["conn"].execute("SELECT COUNT(*) FROM capture_cases WHERE api_key=? AND sealed IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"captures": 0, "open_cases": openc,
                "note": "No sealed captures yet."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    under2 = len([d for d in dwells if d < 2])
    out = {"captures": len(rows), "open_cases": openc,
           "median_dwell_seconds": (dwells[n // 2] if n else None),
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " captures"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "token":
            if not api_key:
                return {"error": "api_key_required",
                        "message": "Mint capture tokens from your server using your real key."}, 401
            return _mint(ctx, api_key, data)
        owner, how = _resolve(ctx, api_key, data)
        if not owner:
            return {"error": "invalid_credentials",
                    "message": "Send a real API key server-side, or a valid capture_token with the origin it was bound to."}, 401
        if action == "open":
            return _open(ctx, owner, data)
        if action == "seal":
            return _seal(ctx, owner, data)
    else:
        if not api_key:
            return {"error": "api_key_required",
                    "message": "Reading capture records needs the real key, not a capture token."}, 401
        if action == "devices":
            return _devices(ctx, api_key, data)
        if action == "summary":
            return _summary(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/codebase.py`

489 lines, 21403 bytes

```python
#!/usr/bin/env python3
"""
modules/codebase.py  -  dated evidence of what you held, and when
=================================================================

WHAT THIS IS, STATED HONESTLY FIRST
-----------------------------------
This does not prove ownership. Nothing cryptographic can. Ownership of
software is a legal fact established by authorship, company records and
signed assignment - not by a hash.

What it does produce is the evidence that decides most disputes about
software in practice: a dated, tamper-evident, externally anchored record
that a specific person held a specific body of code, in a specific form, at
a specific moment. When two parties later disagree about who had what
first, that is the question a court, a mediator or an investor actually
asks - and it is normally answered with commit dates, which are settable
fields that prove nothing.

This answers it with arithmetic instead.

WHAT IT DOES
------------
    POST /x/codebase/seal

Walks the deployed source tree, hashes every file, builds one manifest root
over all of them, and seals that root - together with a declaration of
authorship you supply - into the chain. From there it is anchored
externally and handed to peer chains like every other block.

Run it again next week and you get a second dated point. Run it on every
deploy and you accumulate a continuous, uneditable record of the codebase
evolving under your hand, which is a far stronger thing than a single
snapshot: a body of work with a history is much harder to dispute than a
file that appeared once.

WHAT THE MANIFEST CONTAINS - AND WHAT IT DOES NOT
-------------------------------------------------
For each file: its path and the SHA-256 of its exact bytes. Nothing else.
No contents leave the server, ever, by any route here. The hashes are
one-way, so the manifest reveals nothing about what the code does; it only
lets you demonstrate later that a file you hold now is byte-identical to
the file you held then.

The manifest route is deliberately KEYED rather than public. Only the root,
the file count and the total byte size are public. A public file listing
would hand an attacker a map of the deployment for no gain - the root is
all a third party needs in order to check a manifest you show them.

Excluded by default and never hashed: version control internals, caches,
databases, and anything that looks like a secret. Sealing a hash of your
own credentials file would be a poor way to protect them.

HOW YOU USE IT IN A DISPUTE
---------------------------
  1. You produce the sealed root, its block index, and the chain's
     external anchor.
  2. You produce your copy of the code.
  3. Anyone recomputes the manifest from your copy - the rules are
     published at /x/codebase/spec - and compares.

If it matches, you demonstrably held exactly that code no later than the
sealing time, and the record of it has not been altered since, because it
is a block in an anchored chain that peers also hold.

WHAT STILL HAS TO HAPPEN OUTSIDE THIS FILE
------------------------------------------
Stated plainly, because a module that let you believe it had settled your
legal position would be doing you harm:

  - Copyright arises on authorship. Sealing evidences it; it does not
    create or register it.
  - If a company operates the platform, the IP needs to sit with the right
    entity in writing, or the position is muddier than it looks.
  - Where two parties have collaborated, the only reliable answer is an
    agreement saying who owns what, signed before it matters rather than
    after.

This module makes the factual record unarguable. The legal position is a
separate job and needs a solicitor, not a hash.

    POST /x/codebase/seal      hash the tree, seal the root      (keyed)
    GET  /x/codebase/manifest  the full file list for a seal     (keyed)
    GET  /x/codebase/history   every seal, with root changes     (public)
    GET  /x/codebase/root      the latest sealed root            (public)
    GET  /x/codebase/spec      how to recompute it yourself      (public)
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Roots and history are public - a dated claim nobody can check is not
# evidence. The file listing is keyed, because it is a map of the
# deployment and a third party never needs it to verify a manifest.
PUBLIC = {("GET", "history"), ("GET", "root"), ("GET", "spec")}

FILE_PREFIX = b"AILEASH-FILE-v1:"
MANIFEST_PREFIX = b"AILEASH-MANIFEST-v1:"

MAX_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

# Never walked into.
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
             "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
             "dist", "build", ".cache", "backups"}

# Never hashed. Secrets and databases are excluded on purpose - a hash of
# your credentials file is not evidence of anything you want to prove.
SKIP_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal",
                 ".db-shm", ".pyc", ".pyo", ".log", ".ots", ".pem", ".key",
                 ".crt", ".p12", ".pfx")
SKIP_NAMES = {".env", ".env.local", ".env.production", "secrets.json",
              "credentials.json", ".netrc", "id_rsa", ".DS_Store"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS codebase_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "manifest_root TEXT,file_count INTEGER,total_bytes INTEGER,"
                  "declaration TEXT,manifest TEXT,sealed REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cb_root ON codebase_seal(manifest_root)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _app_root():
    """The directory the application is deployed from.

    This module lives in modules/, so the parent of that directory is the
    tree we want. Resolved rather than assumed, so it is correct whatever
    the working directory happens to be when the server starts.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    return parent if parent else here


def _skip(name):
    if name in SKIP_NAMES:
        return True
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in SKIP_SUFFIXES)


def _file_hash(path):
    """SHA-256 of the exact bytes, read in chunks so a large file cannot
    exhaust memory."""
    digest = hashlib.sha256()
    digest.update(FILE_PREFIX)
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                return None, size
            digest.update(chunk)
    return digest.hexdigest(), size


def _walk(root):
    """Every file under root, sorted by relative path.

    Sorting matters: the manifest must be reproducible by anyone holding
    the same files, and directory order is not stable across systems.
    """
    entries, skipped, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if _skip(filename):
                skipped.append(os.path.relpath(os.path.join(dirpath, filename), root))
                continue
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                digest, size = _file_hash(full)
            except OSError:
                skipped.append(relative)
                continue
            if digest is None:
                skipped.append(relative)
                continue
            entries.append({"path": relative, "sha256": digest, "bytes": size})
            total += size
            if len(entries) >= MAX_FILES:
                return entries, skipped, total, True
    return entries, skipped, total, False


def _manifest_root(entries):
    """One root over the whole tree.

    Deliberately a flat, ordered digest rather than a Merkle tree: there is
    no need for per-file proofs here, and a rule anyone can reimplement in
    four lines is worth more than a clever structure nobody checks.
    """
    digest = hashlib.sha256()
    digest.update(MANIFEST_PREFIX)
    for entry in entries:
        digest.update(("%s\0%s\n" % (entry["path"], entry["sha256"])).encode("utf-8"))
    return digest.hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _seal(ctx, api_key, data):
    author = str(data.get("author", "") or "").strip()[:120]
    entity = str(data.get("entity", "") or "").strip()[:120]
    statement = str(data.get("statement", "") or "").strip()[:1000]

    if not author:
        return {"error": "author_required",
                "message": "The name of the person declaring authorship. This is sealed "
                           "verbatim and becomes part of the permanent record."}, 400

    root_path = _app_root()
    started = time.time()
    entries, skipped, total_bytes, truncated = _walk(root_path)
    if not entries:
        return {"error": "nothing_to_seal",
                "message": "No files found to hash under the application root."}, 500

    manifest_root = _manifest_root(entries)
    now = time.time()

    declaration = {
        "author": author,
        "entity": entity or None,
        "statement": statement or None,
        "declared_at": _iso(now),
    }

    ev = {"user_id": "cb:" + manifest_root[:16], "action": "codebase_sealed", "amount": 0,
          "country": "UK", "device_id": "codebase", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CODEBASE_SEALED", "score": 0, "codebase_version": VERSION,
           "manifest_root": manifest_root, "file_count": len(entries),
           "total_bytes": total_bytes, "author": author, "entity": entity or None,
           "statement": statement or None,
           "detail": "root=%s;files=%d;bytes=%d;author=%s"
                     % (manifest_root, len(entries), total_bytes, author)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT manifest_root,sealed FROM codebase_seal ORDER BY id ASC").fetchall()
        ctx["conn"].execute(
            "INSERT INTO codebase_seal(api_key,manifest_root,file_count,total_bytes,"
            "declaration,manifest,sealed,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, manifest_root, len(entries), total_bytes,
             json.dumps(declaration), json.dumps(entries), now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "manifest_root": manifest_root,
        "file_count": len(entries), "total_bytes": total_bytes,
        "files_skipped": len(skipped),
        "sealed_at": _iso(now),
        "took_seconds": round(now - started, 2),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "declaration": declaration,
        "seal_number": len(prior) + 1,
        "codebase_version": VERSION,
        "what_this_establishes": ("That the person named above held a body of code producing "
                                  "exactly this manifest root, no later than this moment, and "
                                  "that the record cannot be altered afterwards - it is a block "
                                  "in a chain that is externally anchored and held by peers."),
        "what_it_does_not": ("It does not establish legal ownership. Ownership comes from "
                             "authorship, company records and signed assignment. This is the "
                             "dated factual record those arguments rest on, not a substitute "
                             "for them."),
        "how_to_use_it": ("Keep this response. To demonstrate the claim later, produce your copy "
                          "of the code and let anyone recompute the manifest root from it using "
                          "the published rules. If it matches, you held exactly that code by "
                          "this date."),
        "verify_the_block": "/x/consistency/ancestor?tip=" + audit_hash,
        "spec": "/x/codebase/spec",
    }

    if truncated:
        out["truncated"] = ("Hit the %d file cap. The root covers the files listed and no more - "
                            "raise MAX_FILES if the tree is genuinely larger." % MAX_FILES)
    if prior:
        last_root, last_time = prior[-1]
        if last_root == manifest_root:
            out["unchanged_since"] = _iso(last_time)
            out["message"] = ("Identical to the previous seal. The codebase has not changed "
                              "since %s and now carries an additional dated witness."
                              % _iso(last_time))
        else:
            out["previous_root"] = last_root
            out["previous_sealed_at"] = _iso(last_time)
            out["message"] = ("The codebase has changed since the last seal. Both roots remain "
                              "in the chain - a dated history of the work, which is stronger "
                              "evidence than any single snapshot.")
    else:
        out["message"] = ("First seal. Run this on every deploy and the history becomes a "
                          "continuous record of the work developing under one hand.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _manifest(ctx, data):
    root = str(data.get("root", data.get("manifest_root", ""))).strip().lower()
    with ctx["lock"]:
        if root:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal WHERE manifest_root=? LIMIT 1",
                (root,)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "not_found", "root": root or None}, 404

    try:
        files = json.loads(row[4])
    except Exception:
        files = []
    try:
        declaration = json.loads(row[3])
    except Exception:
        declaration = None

    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "declaration": declaration, "sealed_at": _iso(row[5]),
            "sealed_in_chain": row[6], "block_index": row[7],
            "files": files,
            "codebase_version": VERSION,
            "note": "Paths and hashes only. No file contents are held or returned by any route "
                    "in this module."}, 200


def _history(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,declaration,sealed,audit_hash,"
            "block_index FROM codebase_seal ORDER BY id ASC LIMIT 500").fetchall()
    if not rows:
        return {"count": 0, "seals": [],
                "message": "No codebase seal recorded yet."}, 200

    seals, last = [], None
    for root, count, total, declaration, sealed, audit_hash, block_index in rows:
        try:
            parsed = json.loads(declaration)
            author = parsed.get("author")
        except Exception:
            author = None
        seals.append({"manifest_root": root, "file_count": count, "total_bytes": total,
                      "author": author, "sealed_at": _iso(sealed),
                      "sealed_in_chain": audit_hash, "block_index": block_index,
                      "changed_from_previous": last is not None and root != last})
        last = root

    authors = {s["author"] for s in seals if s["author"]}
    return {"count": len(seals),
            "first_sealed": seals[0]["sealed_at"], "latest_sealed": seals[-1]["sealed_at"],
            "distinct_roots": len({s["manifest_root"] for s in seals}),
            "declared_authors": sorted(authors),
            "seals": seals,
            "codebase_version": VERSION,
            "what_this_is": "A dated, uneditable record of one body of code developing over "
                            "time under a declared author. A continuous history is materially "
                            "harder to dispute than a single snapshot.",
            "file_list": "Keyed - /x/codebase/manifest. The root is all anyone needs to check a "
                         "manifest you show them."}, 200


def _root(ctx):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,sealed,audit_hash,block_index,"
            "declaration FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "never_sealed"}, 404
    try:
        author = json.loads(row[6]).get("author")
    except Exception:
        author = None
    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "sealed_at": _iso(row[3]), "sealed_in_chain": row[4], "block_index": row[5],
            "declared_author": author,
            "codebase_version": VERSION,
            "verify_the_block": "/x/consistency/ancestor?tip=" + row[4],
            "recompute_it": "/x/codebase/spec"}, 200


def _spec():
    return {
        "codebase_version": VERSION,
        "purpose": "Dated, tamper-evident evidence that a named person held a specific body of "
                   "code at a specific moment.",
        "not_ownership": "This does not establish legal ownership and is not offered as though "
                         "it does. Ownership comes from authorship, company records and signed "
                         "assignment. This is the factual record those arguments rest on.",
        "file_hash": "sha256('AILEASH-FILE-v1:' || exact_file_bytes) as lowercase hex",
        "manifest_root": "sha256('AILEASH-MANIFEST-v1:' || for each file in path order: "
                         "path + NUL + file_hash + newline) as lowercase hex",
        "ordering": "files sorted by relative path, forward slashes, relative to the "
                    "application root",
        "excluded": {
            "directories": sorted(SKIP_DIRS),
            "suffixes": list(SKIP_SUFFIXES),
            "names": sorted(SKIP_NAMES),
            "why": "Version control internals and caches are not the work. Databases and "
                   "anything resembling a secret are excluded because hashing them proves "
                   "nothing worth proving and risks something worth protecting.",
        },
        "recompute_it_yourself": [
            "Take your copy of the source tree.",
            "Drop the excluded directories, suffixes and names above.",
            "Hash each remaining file with the file rule.",
            "Sort by relative path and apply the manifest rule.",
            "Compare with the sealed root. A match means byte-identical code.",
        ],
        "privacy": "No file contents are stored or returned by any route. The manifest holds "
                   "paths and one-way hashes only, and the file list itself is keyed.",
        "the_discipline": "Seal on every deploy. A single snapshot is a claim about one day; a "
                          "continuous dated history is a record of the work.",
        "what_to_do_as_well": "Get the legal position in writing - entity ownership of the IP, "
                              "and a signed agreement with any collaborator saying who owns "
                              "what. Do it before it matters. This module makes the facts "
                              "unarguable; it cannot make the paperwork exist.",
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
        if action == "history":
            return _history(ctx)
        if action == "root":
            return _root(ctx)
        if action == "manifest":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _manifest(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "root", "manifest (keyed)"],
            "POST": ["seal (keyed)"]}, 404

```


## `modules/complete.py`

862 lines, 37023 bytes

```python
#!/usr/bin/env python3
"""
modules/complete.py  -  proving what ISN'T there
================================================

THE PROBLEM NOBODY IN THIS MARKET ANSWERS
-----------------------------------------
A hash chain proves inclusion. It cannot prove exclusion.

So when a firm hands an auditor four hundred decisions, nothing on earth
shows it wasn't six hundred. Every audit ever conducted runs on the
assumption that the sample handed over is the whole set, and that
assumption has never once been provable. The chain says "these four
hundred happened". It says nothing about the two hundred that also
happened and quietly didn't make the export.

Three questions follow, and none of them can be answered by an
append-only log on its own:

  1. Is this the complete set, or the flattering subset?
  2. Do you hold a record about me? Prove the NO.
  3. You erased my data - prove it, without holding my data to prove it.

Question 3 is the contradiction sitting inside every
blockchain-for-compliance product, this one included. Append-only and
right-to-erasure do not obviously coexist. Most vendors disclaim it.

WHAT THIS DOES
--------------
At the end of each period we take every leaf sealed in that period, SORT
them, build a Merkle tree over the sorted list, and seal the root plus the
exact count into the chain. That root is then anchored externally like
everything else.

Sorting is the whole trick. In an unsorted tree you can only prove a leaf
is present. In a sorted one you can prove a leaf is absent, by showing the
two leaves either side of where it would have sorted and proving they are
ADJACENT in the tree. Nothing can sit between two adjacent leaves. The
record provably does not exist.

  INCLUSION     standard Merkle path. This receipt is in the period.
  ABSENCE       the two neighbours, and proof they are adjacent. No record
                for that key exists in the period, and we cannot pretend
                otherwise after the fact.
  COMPLETENESS  the count was sealed BEFORE anyone asked for anything.
                Hand over four hundred against a root that says six
                hundred and the arithmetic exposes it.

ERASURE
-------
Erasing a record deletes the payload and leaves the leaf as a tombstone.
We can then prove: a record existed, it was erased, and when - while
holding none of the erased content. The subject gets a proof of erasure
rather than a promise of one, and the chain does not have to be broken to
give it to them.

WHY COMMITMENTS ARE FROZEN
--------------------------
A commitment is only worth anything if it cannot be recomputed to suit
later circumstances. So:

  - Only CLOSED periods can be committed. You cannot commit a period that
    is still running, because more leaves could still arrive.
  - The sorted leaf list is STORED at commit time, not recomputed on
    demand. If rows are erased next year, the proofs from this year still
    verify against the root that was sealed and anchored this year.
  - A period can only be committed once. A second attempt returns the
    existing commitment rather than a new root.

WHY COMMITTING IS AUTOMATIC
---------------------------
It was not, and that was a real hole rather than an oversight worth
defending. Committing was a keyed POST somebody had to remember to make,
which meant that for the first week of publication this module had zero
committed periods while the discovery document advertised completeness and
absence as publicly demonstrable checks. Both were true claims about code
that existed and false claims about anything an outsider could run.

A control that depends on the operator remembering to run it is the exact
control an auditor should distrust, so the schedule now runs itself. Once
a month closes, the first request to reach this module commits it.

Two honest limits on that:

  - The automatic commitment is DEPLOYMENT-WIDE. It covers every record
    sealed in the period regardless of which key sealed it, because that
    is what a public completeness claim has to mean. Per-tenant
    commitments are still made by POSTing /x/complete/commit with that
    tenant's key, and the two live side by side.
  - A period committed late is committed at the date it was actually
    committed, and /x/complete/periods reports the gap in days. Backfilled
    history still proves the count was fixed before any export was asked
    for. It does not prove the count was fixed when the period closed, and
    nothing published here will claim it does.

HONEST LIMITS
-------------
  - This proves completeness of what was SEALED. A decision that never
    reached the chain at all is outside anything we can see. Garbage in
    still applies; what changes is that the operator can no longer choose
    which of the sealed records to show.
  - Absence proofs are scoped to a period. "No record of you, ever"
    means checking every period, which is why the period list is public.
  - The tree is built over key material only. It never contains payloads,
    so a leaf reveals whether something exists, not what it said.
  - Adjacent-leaf absence proofs disclose the two neighbouring keys. If
    keys are themselves sensitive, hash them before they become leaves -
    the proof still works, and we hold nothing legible.

    POST /x/complete/commit    close and seal a period      (keyed)
    POST /x/complete/erase     tombstone a leaf             (keyed)
    GET  /x/complete/periods   every sealed period          (public)
    GET  /x/complete/root      root, count, block index     (public)
    GET  /x/complete/prove     inclusion or absence proof   (public)
    POST /x/complete/verify    check a proof we handed out  (public)
    GET  /x/complete/spec      the exact hashing rules      (public)
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# A third party must be able to check completeness without an account. A
# completeness claim you have to hold credentials to verify is not a
# completeness claim, it is a marketing line.
PUBLIC = {("GET", "periods"), ("GET", "root"), ("GET", "prove"),
          ("GET", "spec"), ("POST", "verify")}

# Domain separation. Leaf and node hashes must never be confusable, or an
# attacker can present an internal node as though it were a leaf.
LEAF_PREFIX = b"AILEASH-LEAF-v1:"
NODE_PREFIX = b"AILEASH-NODE-v1:"

MAX_LEAVES = 200000

# ---- automatic commitment --------------------------------------------
AUTO_COMMIT = True          # set False to go back to committing by hand
AUTO_KINDS = ("receipts", "subjects")
AUTO_INTERVAL = 600         # seconds between sweeps, not per request
AUTO_MAX_MONTHS = 24        # how far back a first run will backfill

# The deployment-wide commitment is stored under an empty key, which is
# also what an unauthenticated read looks for. Not a magic value with
# privileges - the absence of a key, meaning "everything sealed here".
AUTO_KEY = ""

_last_auto = [0.0]
_auto_log = []              # recent sweep outcomes, surfaced on /periods

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS complete_commit("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,period TEXT,kind TEXT,"
                  "root TEXT,leaf_count INTEGER,period_start REAL,period_end REAL,"
                  "committed REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cmp_unique "
                  "ON complete_commit(api_key,period,kind)")
        c.execute("CREATE TABLE IF NOT EXISTS complete_leaf("
                  "commit_id INTEGER,idx INTEGER,leaf TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_leaf "
                  "ON complete_leaf(commit_id,idx)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_leaf_val "
                  "ON complete_leaf(commit_id,leaf)")
        c.execute("CREATE TABLE IF NOT EXISTS complete_tomb("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,leaf TEXT,"
                  "reason TEXT,erased REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_tomb ON complete_tomb(api_key,leaf)")
        c.commit()
    _ready = True


def _audit_columns(ctx):
    """What the audit_log actually looks like on this deployment.

    Read rather than assumed - the schema has moved before and will again,
    and a completeness module that guesses column names is worse than none.
    """
    have = []
    try:
        with ctx["lock"]:
            for row in ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall():
                have.append(row[1])
    except Exception:
        pass
    return have


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# periods
# ----------------------------------------------------------------------

def _period_bounds(period):
    """Turn a period label into [start, end) as epoch seconds.

    Accepts  2026, 2026-08, 2026-08-02, 2026-Q3.
    Returns (start, end, None) or (None, None, why).
    """
    period = (period or "").strip().upper()

    def _utc(y, m, d):
        return datetime(y, m, d, tzinfo=timezone.utc).timestamp()

    try:
        m = re.match(r"^(\d{4})$", period)
        if m:
            y = int(m.group(1))
            return _utc(y, 1, 1), _utc(y + 1, 1, 1), None

        m = re.match(r"^(\d{4})-Q([1-4])$", period)
        if m:
            y, q = int(m.group(1)), int(m.group(2))
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 3
            if end_month > 12:
                return _utc(y, start_month, 1), _utc(y + 1, 1, 1), None
            return _utc(y, start_month, 1), _utc(y, end_month, 1), None

        m = re.match(r"^(\d{4})-(\d{2})$", period)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            if not 1 <= mo <= 12:
                return None, None, "month out of range"
            if mo == 12:
                return _utc(y, 12, 1), _utc(y + 1, 1, 1), None
            return _utc(y, mo, 1), _utc(y, mo + 1, 1), None

        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", period)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            start = datetime(y, mo, d, tzinfo=timezone.utc)
            return start.timestamp(), (start + timedelta(days=1)).timestamp(), None
    except ValueError as exc:
        return None, None, "unreadable period (%s)" % exc

    return None, None, "period must be YYYY, YYYY-MM, YYYY-MM-DD or YYYY-Qn"


# ----------------------------------------------------------------------
# the tree
# ----------------------------------------------------------------------

def _leaf_hash(value):
    return hashlib.sha256(LEAF_PREFIX + value.encode("utf-8")).hexdigest()


def _node_hash(left, right):
    return hashlib.sha256(NODE_PREFIX + left.encode() + right.encode()).hexdigest()


def _build(leaves):
    """Build the tree over already-sorted leaf VALUES.

    Returns (root, levels). levels[0] is the leaf-hash level. An odd node
    at any level is promoted unchanged to the next - it is never paired
    with itself, which is the classic duplication weakness.
    """
    if not leaves:
        return hashlib.sha256(LEAF_PREFIX + b"EMPTY").hexdigest(), []

    level = [_leaf_hash(v) for v in leaves]
    levels = [level]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(_node_hash(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])
        levels.append(nxt)
        level = nxt
    return level[0], levels


def _path(levels, index):
    """Sibling path for a leaf index. Each step says which side to hash on."""
    proof = []
    idx = index
    for level in levels[:-1]:
        if idx % 2 == 0:
            sibling = idx + 1
            if sibling < len(level):
                proof.append({"side": "right", "hash": level[sibling]})
            # No sibling means this node was promoted - nothing to hash.
        else:
            proof.append({"side": "left", "hash": level[idx - 1]})
        idx //= 2
    return proof


def _replay(leaf_value, proof):
    """Recompute a root from a leaf and its path. This is what a verifier
    runs, and it is deliberately five lines so anyone can reimplement it."""
    current = _leaf_hash(leaf_value)
    for step in proof:
        if step.get("side") == "left":
            current = _node_hash(step["hash"], current)
        else:
            current = _node_hash(current, step["hash"])
    return current


# ----------------------------------------------------------------------
# reading leaves out of the audit log
# ----------------------------------------------------------------------

def _collect(ctx, api_key, start, end, kind, columns):
    """Every distinct leaf sealed in [start, end).

    kind = receipts  -> the audit hash of each sealed decision
    kind = subjects  -> the distinct subject each decision was about, so
                        "do you hold anything on me" becomes answerable

    A falsy api_key means no scoping: every record sealed on this
    deployment in the window. That is what the automatic commitment uses,
    and what a public completeness claim has to cover.
    """
    if "ts" not in columns:
        return None, "audit_log has no ts column on this deployment"

    if kind == "receipts":
        if "audit_hash" not in columns:
            return None, "audit_log has no audit_hash column"
        field = "audit_hash"
    else:
        field = None
        for candidate in ("user_id", "subject", "subject_id", "customer_id"):
            if candidate in columns:
                field = candidate
                break
        if not field:
            return None, "no subject column on this deployment - receipts only"

    scoped = "api_key" in columns and api_key
    sql = "SELECT DISTINCT %s FROM audit_log WHERE ts>=? AND ts<?" % field
    args = [start, end]
    if scoped:
        sql += " AND api_key=?"
        args.append(api_key)

    with ctx["lock"]:
        rows = ctx["conn"].execute(sql, tuple(args)).fetchall()

    values = sorted({str(r[0]) for r in rows if r[0] is not None})
    if len(values) > MAX_LEAVES:
        return None, "period holds %d leaves, above the %d cap" % (len(values), MAX_LEAVES)
    return values, None


# ----------------------------------------------------------------------
# commit
# ----------------------------------------------------------------------

def _commit(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    if kind not in ("receipts", "subjects"):
        return {"error": "bad_kind", "message": "kind is receipts or subjects"}, 400

    start, end, why = _period_bounds(period)
    if why:
        return {"error": "bad_period", "message": why}, 400

    now = time.time()
    if end > now:
        return {"error": "period_open",
                "message": "That period has not finished. Committing a live period would let "
                           "later entries change the root, which defeats the point.",
                "closes_at": _iso(end)}, 409

    with ctx["lock"]:
        existing = ctx["conn"].execute(
            "SELECT root,leaf_count,committed,audit_hash,block_index FROM complete_commit "
            "WHERE api_key=? AND period=? AND kind=?", (api_key, period, kind)).fetchone()
    if existing:
        return {"already_committed": True, "period": period, "kind": kind,
                "root": existing[0], "leaf_count": existing[1],
                "committed_at": _iso(existing[2]),
                "sealed_in_chain": existing[3], "block_index": existing[4],
                "message": "A period is committed once. Recommitting is how a commitment "
                           "stops meaning anything."}, 200

    columns = _audit_columns(ctx)
    leaves, why = _collect(ctx, api_key, start, end, kind, columns)
    if why:
        return {"error": "cannot_collect", "message": why}, 400

    root, levels = _build(leaves)

    scope = "deployment" if not api_key else "key"
    late_days = round(max(0.0, (now - end)) / 86400.0, 1)

    ev = {"user_id": "cmp:" + period, "action": "completeness_committed", "amount": 0,
          "country": "UK", "device_id": "complete", "anomaly": 0, "device_risk": 0}
    res = {"decision": "COMPLETENESS_SEALED", "score": 0, "complete_version": VERSION,
           "period": period, "kind": kind, "root": root, "leaf_count": len(leaves),
           "period_start": start, "period_end": end, "scope": scope,
           "days_after_period_end": late_days,
           "detail": "period=%s;kind=%s;scope=%s;root=%s;count=%d;late_days=%s"
                     % (period, kind, scope, root, len(leaves), late_days)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("INSERT INTO complete_commit(api_key,period,kind,root,leaf_count,"
                  "period_start,period_end,committed,audit_hash,block_index) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (api_key, period, kind, root, len(leaves), start, end, now,
                   audit_hash, block_index))
        commit_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.executemany("INSERT INTO complete_leaf(commit_id,idx,leaf) VALUES(?,?,?)",
                      [(commit_id, i, v) for i, v in enumerate(leaves)])
        c.commit()

    return {"period": period, "kind": kind, "root": root, "leaf_count": len(leaves),
            "period_start": _iso(start), "period_end": _iso(end),
            "committed_at": _iso(now), "sealed_in_chain": audit_hash,
            "block_index": block_index, "receipt_seq": seq,
            "scope": scope, "days_after_period_end": late_days,
            "frozen": "The sorted leaf list is stored as committed. Later erasures cannot "
                      "change what this root proved.",
            "message": "%d leaves committed. Any export from this period claiming a different "
                       "total now contradicts a sealed, externally anchored number."
                       % len(leaves)}, 200


# ----------------------------------------------------------------------
# automatic commitment
# ----------------------------------------------------------------------

def _closed_months(first_ts, now):
    """Every whole month between the first sealed record and this one.

    The current month is excluded because it is still running, which is
    the same rule a manual commit is held to.
    """
    try:
        first = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        current = datetime.fromtimestamp(now, tz=timezone.utc)
    except Exception:
        return []

    labels = []
    y, m = first.year, first.month
    while (y, m) < (current.year, current.month):
        labels.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if len(labels) > 600:
            break
    return labels[-AUTO_MAX_MONTHS:]


def _auto_commit(ctx):
    """Commit any closed month that nobody has committed yet.

    Runs on request rather than on a thread. A sleeping container has no
    timer worth trusting, and this way the sweep happens before the answer
    that depends on it - including for the auditor whose visit to
    /x/complete/periods is what triggered it.
    """
    if not AUTO_COMMIT:
        return

    now = time.time()
    if now - _last_auto[0] < AUTO_INTERVAL:
        return
    _last_auto[0] = now

    columns = _audit_columns(ctx)
    if "ts" not in columns:
        return

    try:
        with ctx["lock"]:
            row = ctx["conn"].execute("SELECT MIN(ts) FROM audit_log").fetchone()
    except Exception:
        return
    if not row or not row[0]:
        return

    months = _closed_months(row[0], now)
    if not months:
        return

    try:
        with ctx["lock"]:
            done = {(r[0], r[1]) for r in ctx["conn"].execute(
                "SELECT period,kind FROM complete_commit WHERE api_key=?",
                (AUTO_KEY,)).fetchall()}
    except Exception:
        done = set()

    for period in months:
        for kind in AUTO_KINDS:
            if (period, kind) in done:
                continue
            try:
                body, code = _commit(ctx, AUTO_KEY, {"period": period, "kind": kind})
            except Exception as exc:
                _note_auto(period, kind, "failed: " + str(exc)[:120])
                continue
            if code == 200 and not body.get("already_committed"):
                _note_auto(period, kind, "committed %d leaves %s days after the period closed"
                           % (body.get("leaf_count", 0), body.get("days_after_period_end")))
            elif code != 200:
                # A deployment with no subject column cannot do kind=subjects.
                # That is a real limit of the deployment, recorded rather than
                # retried every ten minutes.
                _note_auto(period, kind, "skipped: " + str(body.get("message")
                                                           or body.get("error"))[:120])


def _note_auto(period, kind, outcome):
    _auto_log.append({"at": _iso(time.time()), "period": period,
                      "kind": kind, "outcome": outcome})
    del _auto_log[:-40]
    print("COMPLETE: auto %s/%s - %s" % (period, kind, outcome), flush=True)


# ----------------------------------------------------------------------
# proofs
# ----------------------------------------------------------------------

def _load(ctx, api_key, period, kind):
    with ctx["lock"]:
        if api_key:
            row = ctx["conn"].execute(
                "SELECT id,root,leaf_count,committed,audit_hash,block_index,period_start,period_end "
                "FROM complete_commit WHERE api_key=? AND period=? AND kind=?",
                (api_key, period, kind)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT id,root,leaf_count,committed,audit_hash,block_index,period_start,period_end "
                "FROM complete_commit WHERE period=? AND kind=? ORDER BY id ASC LIMIT 1",
                (period, kind)).fetchone()
        if not row:
            return None, None
        leaves = [r[0] for r in ctx["conn"].execute(
            "SELECT leaf FROM complete_leaf WHERE commit_id=? ORDER BY idx ASC",
            (row[0],)).fetchall()]
    return row, leaves


def _tombstone_for(ctx, api_key, value):
    with ctx["lock"]:
        if api_key:
            row = ctx["conn"].execute(
                "SELECT erased,reason,audit_hash,block_index FROM complete_tomb "
                "WHERE api_key=? AND leaf=? ORDER BY id ASC LIMIT 1",
                (api_key, value)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT erased,reason,audit_hash,block_index FROM complete_tomb "
                "WHERE leaf=? ORDER BY id ASC LIMIT 1", (value,)).fetchone()
    if not row:
        return None
    return {"erased_at": _iso(row[0]), "reason": row[1],
            "sealed_in_chain": row[2], "block_index": row[3],
            "note": "The payload is gone. This proves it existed and that it was erased, "
                    "without holding any of it."}


def _prove(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    value = str(data.get("value", "")).strip()
    if not period or not value:
        return {"error": "period_and_value_required",
                "message": "Both are required. Committed periods are listed at "
                           "/x/complete/periods; value is any key you want proved "
                           "present or absent.",
                "example": "/x/complete/prove?period=2026-07&value=<key>"}, 400

    row, leaves = _load(ctx, api_key, period, kind)
    if not row:
        return {"error": "not_committed", "period": period, "kind": kind,
                "message": "No sealed commitment for that period. Nothing can be proved "
                           "either way until the period is closed and committed."}, 404

    _cid, root, count, committed, chain_hash, block_index, start, end = row
    _r, levels = _build(leaves)

    base = {"period": period, "kind": kind, "value": value, "root": root,
            "leaf_count": count, "committed_at": _iso(committed),
            "period_start": _iso(start), "period_end": _iso(end),
            "sealed_in_chain": chain_hash, "block_index": block_index,
            "complete_version": VERSION,
            "verify": "/x/complete/verify, or reimplement it - the rules are at /x/complete/spec"}

    # Present?
    try:
        index = leaves.index(value)
    except ValueError:
        index = None

    if index is not None:
        base.update({
            "result": "present",
            "index": index,
            "proof": _path(levels, index),
            "what_this_proves": "This exact record is inside the sealed set for the period. "
                                "It cannot have been added afterwards.",
        })
        tomb = _tombstone_for(ctx, api_key, value)
        if tomb:
            base["erased"] = tomb
        return base, 200

    # Absent - find the neighbours it sorts between.
    lower_index = None
    upper_index = None
    for i, leaf in enumerate(leaves):
        if leaf < value:
            lower_index = i
        else:
            upper_index = i
            break

    neighbours = {}
    if lower_index is not None:
        neighbours["lower"] = {"index": lower_index, "value": leaves[lower_index],
                               "proof": _path(levels, lower_index)}
    if upper_index is not None:
        neighbours["upper"] = {"index": upper_index, "value": leaves[upper_index],
                               "proof": _path(levels, upper_index)}

    if not leaves:
        adjacency = "The period is committed and empty. Nothing was sealed in it at all."
    elif lower_index is None:
        adjacency = ("The value sorts before every leaf in the set. The first leaf is proved, "
                     "and nothing precedes index 0.")
    elif upper_index is None:
        adjacency = ("The value sorts after every leaf in the set. The last leaf is proved, "
                     "and nothing follows the final index.")
    else:
        adjacency = ("The two proved leaves are adjacent - indices %d and %d, consecutive. "
                     "Nothing can exist between two adjacent leaves of a sorted tree, so no "
                     "record for this value exists in the period."
                     % (lower_index, upper_index))

    base.update({
        "result": "absent",
        "neighbours": neighbours,
        "adjacency": adjacency,
        "what_this_proves": "No record for this value was sealed in this period. Not that we "
                            "declined to look - that it is not there, against a root fixed "
                            "before you asked.",
        "scope": "This period only. /x/complete/periods lists every committed period.",
    })
    tomb = _tombstone_for(ctx, api_key, value)
    if tomb:
        base["erased"] = tomb
        base["note"] = ("Absent from this period AND carrying an erasure record. That is the "
                        "expected shape after a valid erasure request.")
    return base, 200


def _verify(ctx, api_key, data):
    """Check a proof we handed out. Convenience only - a verifier who
    trusts us to check our own proof has not verified anything. The spec
    route exists so this can be done independently."""
    value = str(data.get("value", "")).strip()
    root = str(data.get("root", "")).strip().lower()
    proof = data.get("proof")
    if not value or not HEX64.match(root) or not isinstance(proof, list):
        return {"error": "value_root_and_proof_required"}, 400
    try:
        computed = _replay(value, proof)
    except Exception as exc:
        return {"error": "bad_proof", "message": str(exc)[:200]}, 400
    return {"valid": computed == root, "computed_root": computed, "given_root": root,
            "note": "Recomputed from the leaf upward. If these match, the leaf was in the tree "
                    "when the root was sealed."}, 200


# ----------------------------------------------------------------------
# erasure
# ----------------------------------------------------------------------

def _erase(ctx, api_key, data):
    value = str(data.get("value", "")).strip()
    reason = str(data.get("reason", "erasure request")).strip()[:200]
    if not value:
        return {"error": "value_required",
                "message": "The leaf being tombstoned - a receipt hash or a subject key."}, 400

    now = time.time()
    ev = {"user_id": "era:" + value[:32], "action": "erasure_recorded", "amount": 0,
          "country": "UK", "device_id": "complete", "anomaly": 0, "device_risk": 0}
    res = {"decision": "ERASURE_SEALED", "score": 0, "complete_version": VERSION,
           "leaf": value, "reason": reason,
           "detail": "leaf=%s;reason=%s" % (value, reason)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO complete_tomb(api_key,leaf,reason,erased,audit_hash,"
                            "block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, value, reason, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"leaf": value, "erased_at": _iso(now), "reason": reason,
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Records the erasure as a sealed event. It does not delete the "
                              "payload - your own system does that. This is the receipt that "
                              "proves you did.",
            "what_the_subject_gets": "Proof their record existed, proof it was erased, and the "
                                     "time it happened - none of which requires anyone to still "
                                     "hold the data.",
            "note": "Earlier committed roots still contain the leaf. That is correct and not a "
                    "leak: a leaf is key material, not content, and a root that changed after "
                    "the fact would prove nothing about anything."}, 200


# ----------------------------------------------------------------------
# read-only
# ----------------------------------------------------------------------

def _periods(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute(
                "SELECT period,kind,root,leaf_count,committed,block_index,period_end,api_key "
                "FROM complete_commit WHERE api_key=? ORDER BY period_start DESC",
                (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT period,kind,root,leaf_count,committed,block_index,period_end,api_key "
                "FROM complete_commit ORDER BY period_start DESC").fetchall()

    out = []
    for r in rows:
        late = None
        try:
            if r[4] and r[6]:
                late = round(max(0.0, r[4] - r[6]) / 86400.0, 1)
        except Exception:
            late = None
        out.append({"period": r[0], "kind": r[1], "root": r[2], "leaf_count": r[3],
                    "committed_at": _iso(r[4]), "block_index": r[5],
                    "scope": "deployment" if not r[7] else "key",
                    "committed_days_after_period_end": late})

    return {"count": len(out),
            "periods": out,
            "auto_commit": AUTO_COMMIT,
            "recent_auto_activity": list(reversed(_auto_log[-10:])),
            "on_lateness": "committed_days_after_period_end is published rather than hidden. A "
                           "small number means the count was fixed when the period closed. A "
                           "large one means history was backfilled later, which still proves "
                           "the count was fixed before any export was requested and proves "
                           "nothing more than that.",
            "note": "Gaps are visible on purpose. A missing period is a period nobody committed, "
                    "and that is exactly the thing an auditor should be asking about."}, 200


def _root(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    row, _leaves = _load(ctx, api_key, period, kind)
    if not row:
        return {"error": "not_committed", "period": period, "kind": kind,
                "committed_periods": "/x/complete/periods"}, 404
    _cid, root, count, committed, chain_hash, block_index, start, end = row
    late = None
    try:
        late = round(max(0.0, committed - end) / 86400.0, 1)
    except Exception:
        pass
    return {"period": period, "kind": kind, "root": root, "leaf_count": count,
            "period_start": _iso(start), "period_end": _iso(end),
            "committed_at": _iso(committed), "sealed_in_chain": chain_hash,
            "block_index": block_index, "committed_days_after_period_end": late,
            "what_this_is": "The number of records sealed in this period, fixed before anybody "
                            "asked for an export. Any export claiming a different total is "
                            "arguing with an externally anchored figure."}, 200


def _spec():
    return {
        "complete_version": VERSION,
        "leaf_hash": "sha256('AILEASH-LEAF-v1:' || value) as lowercase hex",
        "node_hash": "sha256('AILEASH-NODE-v1:' || left_hex || right_hex) as lowercase hex",
        "empty_root": hashlib.sha256(LEAF_PREFIX + b"EMPTY").hexdigest(),
        "ordering": "leaf VALUES sorted ascending as UTF-8 strings, duplicates removed, "
                    "before any hashing",
        "odd_nodes": "an unpaired node at any level is promoted unchanged to the next level. "
                     "It is never hashed with itself.",
        "inclusion": "recompute upward from the leaf using the sibling path. Each step gives a "
                     "side; hash the sibling on that side.",
        "absence": "verify the two neighbouring leaves independently, check their values sort "
                   "either side of the queried value, and check their indices are consecutive. "
                   "Consecutive indices in a sorted tree leave no room for anything between.",
        "completeness": "the leaf count is sealed with the root, before any export is requested",
        "schedule": "closed months are committed automatically, deployment-wide, on the first "
                    "request to reach this module after the month ends. Per-key commitments "
                    "remain a keyed POST. Lateness is published per period rather than smoothed "
                    "over.",
        "why_published": "Anyone should be able to write their own verifier and check us without "
                         "running our code or holding an account. A proof you can only check "
                         "with the prover's own tool is not a proof.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)

    # Sweep before answering, never at the cost of answering.
    try:
        _auto_commit(ctx)
    except Exception as exc:
        print("COMPLETE: auto sweep failed - " + str(exc)[:200], flush=True)

    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "periods":
            return _periods(ctx, api_key)
        if action == "root":
            return _root(ctx, api_key, data)
        if action == "prove":
            return _prove(ctx, api_key, data)

    if method == "POST":
        if action == "verify":
            return _verify(ctx, api_key, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "commit":
            return _commit(ctx, api_key, data)
        if action == "erase":
            return _erase(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "periods", "root", "prove"],
            "POST": ["verify", "commit", "erase"]}, 404

```
