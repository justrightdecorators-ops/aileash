# Codebase — part 3 of 38

Contains:
- `modules/bind.py`
- `modules/binddesk.py`
- `modules/blocks.py`
- `modules/capture.py`
- `modules/cinema.py`
- `modules/cinemafeed.py`


## `modules/bind.py`

733 lines, 35203 bytes

```python
#!/usr/bin/env python3
"""modules/bind.py - the signed lane.

A peer signs their own submission with a credential, so binding rests on
possession of a secret rather than on a fetcher reaching a url.

v1.2.0 - block indices now carry their chain epoch.

A block_index on its own is not a reference. The chain restarted from
genesis on 7 September 2026, and an index issued before that became wrong
in the last day - not dangling, but resolving to a real, correctly-sealed
block belonging to someone else, as the chain grew past it. A dangling
pointer announces itself. A pointer that quietly lands on another party's
record does not.

So: every row this module writes from now on records the genesis hash of
the chain it was sealed under, and every route publishing an index says
which epoch it belongs to and whether that epoch is still current. Rows
written before this version have no epoch recorded and cannot be given
one retroactively - inventing it would be the same fault one step back -
so they publish as epoch unknown with the index marked unresolvable
against this chain. Raised by Ishaan (Shango MID), whose own rule is that
a grant carries the epoch it was decided under and is refused when the
epoch has moved.

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

VERSION = "1.2.0"

PUBLIC = {("GET", "name"), ("GET", "conflicts"), ("GET", "spec")}

SIG_PREFIX = b"AILEASH-BIND-v1:"
CLOCK_SKEW = 300
NONCE_KEEP = 3600

RESET_DATE = "2026-09-07"

SECRET_SCOPE = (
    "A credential is a shared secret. Holding it proves the submitter had "
    "the secret, and nothing more. This platform holds a copy, so it does "
    "not exclude the operator. Anyone the secret has been shown to - a "
    "screenshot, a paste into another tool, a colleague - holds it too, and "
    "this lane cannot tell them apart. To exclude the operator, use the "
    "Ed25519 lane at /x/signed/enroll, where the private half never leaves "
    "the peer.")

EPOCH_VOCABULARY = {
    "what_an_epoch_is":
        "The genesis hash of the chain a block index was issued under. An "
        "index without it is not a reference: this chain restarted from "
        "genesis on " + RESET_DATE + ", and an index from before that now "
        "resolves to a real, correctly-sealed block belonging to someone "
        "else. Published so a stale pointer is detectably stale rather "
        "than quietly wrong.",
    "current":
        "Issued under the chain this deployment is serving now. The index "
        "resolves to the block it was issued against.",
    "retired":
        "Issued under an earlier chain. The number may still resolve here, "
        "but to a DIFFERENT block. Do not follow it.",
    "unknown":
        "Recorded before this module stored epochs, so the chain it was "
        "issued under is not known. It cannot be resolved against this "
        "chain and no epoch can be assigned to it after the fact.",
}

_ready = False
_genesis_cache = {"hash": None, "blocks": 0}


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
        c.execute("CREATE TABLE IF NOT EXISTS bind_seq("
                  "name TEXT PRIMARY KEY,seq INTEGER DEFAULT 0)")
        # v1.2.0. Added rather than backfilled: a row written before this
        # version has no epoch and must not be given one now.
        for table in ("bind_credential", "bind_claim", "bind_submission"):
            try:
                c.execute("ALTER TABLE %s ADD COLUMN chain_epoch TEXT" % table)
            except Exception:
                pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_name ON bind_submission(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_claim ON bind_claim(name)")
        c.commit()
    _ready = True


def _genesis(ctx):
    """The current chain's genesis hash, read from audit_log itself.

    Cached against the block count so it costs one cheap query per change.
    Returns None if it cannot be read, and a None epoch is recorded as
    unknown rather than guessed.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()
            blocks = int(row[0]) if row else 0
            if _genesis_cache["hash"] and _genesis_cache["blocks"] == blocks:
                return _genesis_cache["hash"]
            g = ctx["conn"].execute(
                "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1"
            ).fetchone()
        h = g[0] if g else None
        _genesis_cache["hash"] = h
        _genesis_cache["blocks"] = blocks
        return h
    except Exception:
        return None


def _ref(ctx, block_index, stored_epoch):
    """A block index published with the epoch it was issued under."""
    current = _genesis(ctx)
    if not stored_epoch:
        state = "unknown"
    elif current and stored_epoch == current:
        state = "current"
    else:
        state = "retired"
    out = {"block_index": block_index,
           "chain_epoch": stored_epoch,
           "epoch_state": state,
           "current_chain_epoch": current,
           "meaning": EPOCH_VOCABULARY[state]}
    if state == "current":
        out["resolve_at"] = ("https://sebbi.pro/x/walk/block?index=%s"
                             % block_index)
    else:
        out["do_not_resolve"] = (
            "This number may still return a block on this chain. It would "
            "be a different block. Nothing here points at it.")
    return out


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


def _latest_seq(ctx, name):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


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
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "credential_issued",
          "amount": 0, "country": "UK", "device_id": "bind",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "CREDENTIAL_ISSUED", "score": 0, "bind_version": VERSION,
           "name": name, "key_id": key_id, "issued_to": to,
           "secret_sealed": False, "chain_epoch": epoch,
           "detail": "name=%s;key_id=%s;issued_to=%s" % (name, key_id, to)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        if live:
            ctx["conn"].execute(
                "UPDATE bind_credential SET revoked=?, revoke_reason=? "
                "WHERE key_id=?", (now, "replaced by " + key_id, live[0]))
        ctx["conn"].execute(
            "INSERT INTO bind_credential(key_id,name,secret,issued_to,issued,"
            "audit_hash,block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (key_id, name, secret, to, now, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "key_id": key_id, "secret": secret,
            "issued_to": to, "issued_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "current_submission_seq": _latest_seq(ctx, name),
            "send_this_once": ("The secret is shown here and nowhere else. It "
                               "is not sealed into the chain and cannot be "
                               "recovered - if it is lost, revoke and reissue."),
            "how_to_sign": "/x/bind/spec",
            "what_it_proves": ("Possession of this secret. It does not prove "
                               "domain ownership and this platform does not "
                               "check that."),
            "secret_scope": SECRET_SCOPE,
            "note_on_sequence": ("current_submission_seq is where this name's "
                                 "receipt numbering stands. Reissuing a "
                                 "credential does not reset it - the sequence "
                                 "belongs to the name's submission history, "
                                 "not to the key."),
            "replaced": live[0] if live else None}, 200


def _claim(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    claimant = str(data.get("claimant", "")).strip()[:200]
    if not name or not claimant:
        return {"error": "name_and_claimant_required"}, 400
    note = str(data.get("note", "")).strip()[:500] or None
    now = time.time()
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "name_claimed", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "NAME_CLAIMED", "score": 0, "bind_version": VERSION,
           "name": name, "claimant": claimant, "note": note,
           "chain_epoch": epoch,
           "detail": "name=%s;claimant=%s" % (name, claimant)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO bind_claim(name,claimant,claimed_at,note,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?)",
            (name, claimant, now, note, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "claimant": claimant, "claimed_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "what_this_is": ("A dated marker, not a binding. Anyone can still "
                             "submit under this name - but their block is "
                             "provably later than this one, and the conflict "
                             "is public."),
            "what_this_is_not": ("Proof that the claimant owns the name, and "
                                 "not a substitute for a credential.")}, 200


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

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + row[0][:40], "action": "credential_revoked",
          "amount": 0, "country": "UK", "device_id": "bind", "anomaly": 0,
          "device_risk": 1}
    res = {"decision": "CREDENTIAL_REVOKED", "score": 0, "name": row[0],
           "key_id": key_id, "reason": reason, "chain_epoch": epoch,
           "detail": "key_id=%s;reason=%s" % (key_id, reason)}
    h, idx, _ = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE bind_credential SET revoked=?, revoke_reason=? WHERE key_id=?",
            (now, reason, key_id))
        ctx["conn"].commit()

    return {"key_id": key_id, "name": row[0], "revoked_at": _iso(now),
            "reason": reason, "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "note": "Submissions already bound stay bound. Revocation stops "
                    "future ones and does not rewrite the past."}, 200


def _submit(ctx, data):
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

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + name[:40], "action": "signed_tip", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "TIP_BOUND", "score": 0, "bind_version": VERSION,
           "name": name, "tip": tip, "key_id": key_id, "binding": "signature",
           "chain_epoch": epoch,
           "detail": "name=%s;tip=%s;key_id=%s" % (name, tip, key_id)}

    try:
        h, idx, key_seq = ctx["seal"](ev, res, now, None)
    except Exception as exc:
        return {"ok": False, "bound": False, "error": "seal_failed",
                "detail": "Your signature verified, but the audit chain did "
                          "not seal the submission, so there is no receipt to "
                          "give you. This is a fault on this deployment and "
                          "not a problem with your submission.",
                "seal_error": "%s: %s" % (type(exc).__name__, str(exc)[:300]),
                "recorded": False,
                "retry": "Nothing was written. Your nonce is unused and the "
                         "identical submission can be resent once this is "
                         "fixed.",
                "name": name, "tip": tip}, 500
    if not h:
        return {"ok": False, "bound": False, "error": "seal_incomplete",
                "detail": "The audit chain returned no hash, so nothing was "
                          "sealed and no receipt exists. Fault on this "
                          "deployment.",
                "recorded": False, "name": name, "tip": tip}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO bind_seq(name,seq) VALUES(?,0)", (name,))
        ctx["conn"].execute(
            "UPDATE bind_seq SET seq = COALESCE(seq,0) + 1 WHERE name=?", (name,))
        srow = ctx["conn"].execute(
            "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        receipt_seq = int(srow[0]) if srow and srow[0] is not None else None

        ctx["conn"].execute(
            "INSERT INTO bind_submission(name,tip,key_id,ts,nonce,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (name, tip, key_id, now, nonce, h, idx, epoch))
        ctx["conn"].execute("INSERT OR IGNORE INTO bind_nonce(nonce,ts) "
                            "VALUES(?,?)", (nonce, now))
        ctx["conn"].execute("DELETE FROM bind_nonce WHERE ts < ?",
                            (now - NONCE_KEEP,))
        ctx["conn"].commit()

    return {"bound": True, "name": name, "tip": tip, "key_id": key_id,
            "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "receipt_seq": receipt_seq,
            "receipt_seq_scope": "per-name",
            "key_seq": key_seq,
            "binding": "signature",
            "gapless": ("receipt_seq increments by exactly one for each "
                        "accepted submission under this name. Two receipts "
                        "numbered N and N+2 prove a third exists and you did "
                        "not receive it. The current highest is published at "
                        "/x/bind/name?name=" + name + " so the check does not "
                        "depend on asking us."),
            "key_seq_note": ("The server-wide per-API-key sequence, null on "
                             "this lane and always will be. That counter lives "
                             "on an api_key and this lane authenticates by "
                             "signature with no key to count against. Returned "
                             "rather than omitted so the absence is visible "
                             "instead of inferred."),
            "what_this_proves": ("that a holder of the credential issued for "
                                 "this name submitted this tip, and that the "
                                 "submission has not been altered since it was "
                                 "signed"),
            "what_this_does_not_prove": ("which holder. The secret is shared, "
                                         "so this does not exclude the "
                                         "operator or anyone else it has been "
                                         "disclosed to. It also does not prove "
                                         "domain ownership, or that anything "
                                         "in their chain is true"),
            "secret_scope": SECRET_SCOPE,
            "check_it": "/x/bind/name?name=" + name}, 200


def _name(ctx, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT key_id, issued, revoked, issued_to, block_index, "
            "chain_epoch FROM bind_credential WHERE name=? ORDER BY issued DESC",
            (name,)).fetchall()
        claims = ctx["conn"].execute(
            "SELECT claimant, claimed_at, note, block_index, chain_epoch "
            "FROM bind_claim WHERE name=? ORDER BY claimed_at ASC",
            (name,)).fetchall()
        subs = ctx["conn"].execute(
            "SELECT tip, key_id, ts, block_index, chain_epoch "
            "FROM bind_submission WHERE name=? ORDER BY ts DESC LIMIT 20",
            (name,)).fetchall()

    live = [c for c in cred if not c[2]]
    state = ("bound" if live else
             "claimed" if claims else
             "unbound")

    out = {
        "name": name,
        "state": state,
        "lane": "signed (credential). The open lane records a separate "
                "address-level binding, published per entry on "
                "/x/roster/list. The two answer different questions and can "
                "differ without either being wrong.",
        "latest_receipt_seq": _latest_seq(ctx, name),
        "credential": ({"key_id": live[0][0], "issued_at": _iso(live[0][1]),
                        "issued_to": live[0][3],
                        "sealed_at": _ref(ctx, live[0][4], live[0][5])}
                       if live else None),
        "claims": [{"claimant": c[0], "claimed_at": _iso(c[1]), "note": c[2],
                    "sealed_at": _ref(ctx, c[3], c[4])} for c in claims],
        "signed_submissions": [{"tip": s[0], "key_id": s[1], "at": _iso(s[2]),
                                "sealed_at": _ref(ctx, s[3], s[4])}
                               for s in subs],
        "revoked_credentials": [{"key_id": c[0], "revoked_at": _iso(c[2]),
                                 "sealed_at": _ref(ctx, c[4], c[5])}
                                for c in cred if c[2]],
        "chain_epoch": EPOCH_VOCABULARY,
    }
    out["receipt_seq_note"] = (
        "latest_receipt_seq is the highest receipt number issued under this "
        "name. A holder whose own highest receipt is lower than this has not "
        "received one of them, and can say exactly how many. Public on "
        "purpose - a gap you can only see from the inside is not evidence of "
        "anything.")
    if state == "bound":
        out["meaning"] = ("A live credential exists for this name, and every "
                          "submission under it carries a signature made with "
                          "that credential. A submission establishes that "
                          "SOMEONE holding the secret sent it - not which "
                          "holder, and not that the holder is the party the "
                          "name names.")
        out["secret_scope"] = SECRET_SCOPE
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
        "unstealable by a third party on this network, not a claim honest, "
        "and not unsubmittable by the operator.")
    return out, 200


def _conflicts(ctx):
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


def _spec(ctx):
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
        "secret_scope": SECRET_SCOPE,
        "block_indices": dict(
            EPOCH_VOCABULARY,
            current_chain_epoch=_genesis(ctx),
            shape="Every index is published as an object - block_index, "
                  "chain_epoch, epoch_state, current_chain_epoch - never as "
                  "a bare number. A bare number cannot be checked for "
                  "staleness by whoever receives it.",
            rows_before_1_2_0="Recorded without an epoch and published as "
                              "unknown. No epoch is assigned to them now: "
                              "guessing one would be the same fault the "
                              "field exists to prevent.",
        ),
        "on_acceptance": {
            "receipt_seq": ("An integer, never null, incremented by exactly "
                            "one for each accepted submission UNDER THIS NAME "
                            "on this lane. Issued inside the same lock that "
                            "writes the record. Two receipts numbered N and "
                            "N+2 prove a third exists that you did not "
                            "receive. The current highest is published at "
                            "/x/bind/name."),
            "receipt_seq_scope": {
                "values": ["per-peer", "per-name", "per-chain"],
                "per-peer": "issued per registered peer_id. /x/peer/submit.",
                "per-name": "issued per bound name. /x/bind/submit.",
                "per-chain": "issued per enrolled chain name. /x/signed/submit.",
                "why_it_is_here": "The three signed lanes each count within "
                                  "their own scope, so a receipt carries the "
                                  "scope of its own sequence. The set is "
                                  "closed: a value outside this list is an "
                                  "error on our side.",
                "not_comparable_across_scopes": "Two receipts with different "
                                                "scopes are counting different "
                                                "things.",
            },
            "sealed_at": ("Where the submission landed in the chain, as an "
                          "epoch-qualified reference rather than a bare "
                          "index. See block_indices."),
            "key_seq": ("The server-wide per-API-key sequence, null on this "
                        "lane and always will be. That counter lives on an "
                        "api_key and this lane authenticates by signature "
                        "with no key to count against. Returned rather than "
                        "omitted so the absence is visible."),
            "sequence_survives_rotation": ("Reissuing or revoking a credential "
                                           "does not reset the sequence, so a "
                                           "rotation cannot be used to erase a "
                                           "gap."),
            "seal_failure": ("If the audit chain does not seal your "
                             "submission, you get 500 seal_failed and nothing "
                             "is recorded - no nonce, no sequence number, no "
                             "receipt. Resend the identical submission once "
                             "the fault is fixed."),
        },
        "what_a_signed_binding_proves": (
            "that a holder of the credential issued for that name submitted, "
            "and that the submission is unaltered since signing"),
        "what_it_does_not_prove": [
            "which holder. The secret is shared, so this does not exclude the "
            "operator or anyone it has been disclosed to.",
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
            "in principle it could sign on a peer's behalf - which is why the "
            "public-key lane at /x/signed/enroll is the right end state and "
            "this is the interim.",
            "A secret that has been screenshotted, pasted into another tool or "
            "shown to a colleague is held by more parties than two, and this "
            "lane cannot tell them apart. Revoke and reissue, or move to the "
            "key lane.",
            "Revoking a credential stops future submissions and does not "
            "unbind past ones.",
            "An index recorded before 1.2.0 cannot be resolved against this "
            "chain and will never be resolvable. The epoch it was issued "
            "under was not recorded and cannot honestly be reconstructed.",
            "Nothing here checks DNS, TLS or WHOIS.",
            "receipt_seq proves you are missing a receipt. It does not prove "
            "why, and cannot distinguish a lost response from one never sent.",
        ],
        "changed_in_1_2_0": [
            "Block indices now travel with the genesis hash of the chain "
            "they were issued under, and every route publishing one reports "
            "whether that epoch is current, retired or unknown. Before this, "
            "an index issued under the pre-7-September chain was published "
            "as a bare number; once the chain grew past it, it resolved to a "
            "real, correctly-sealed block belonging to a different party. A "
            "dangling pointer is visibly broken - a pointer that resolves to "
            "someone else's record is not. Raised by Ishaan (Shango MID).",
            "Rows written before this version have no epoch and publish as "
            "unknown, marked unresolvable against this chain. They are not "
            "backfilled.",
            "The sealing path is unchanged except that chain_epoch now "
            "appears in the sealed result of new blocks.",
        ],
        "changed_in_1_1_2": [
            "The bound-state text no longer says only the holder can submit. "
            "SECRET_SCOPE appears wherever a secret is issued, used or "
            "reported. Raised by Ishaan (Shango MID).",
        ],
        "changed_in_1_1_1": [
            "receipt_seq_scope is a bare token from a closed set. Asked for "
            "by Philip Pinol (PRAXIS).",
        ],
        "changed_in_1_1": [
            "receipt_seq is a real per-name gapless sequence issued by this "
            "module, not the api_key counter that was always null here.",
            "A failed seal returns 500 and records nothing.",
        ],
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec(ctx)
        if action == "name":
            return _name(ctx, data)
        if action == "conflicts":
            return _conflicts(ctx)

    if method == "POST":
        if action == "submit":
            return _submit(ctx, data)
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


## `modules/binddesk.py`

312 lines, 13381 bytes

```python
#!/usr/bin/env python3
"""
modules/binddesk.py  -  buttons for the signed lane

modules/bind.py is the engine. It answers POST requests with a key, which is
correct and completely unusable from a phone: a browser address bar can only
send GET, and nothing in it can attach an Authorization header.

So this is the page. Paste the key once, tap a button. Same routes underneath,
nothing new in the trust path.

Served at /bind-desk by the same runtime do_GET patch console.py uses. The
page holds nothing - the key is typed in, kept in the tab, and sent on each
request. Every route it calls checks that key itself.

PUBLIC is empty. Nothing here is reachable without a key except the page
itself, and the page is inert until one is pasted into it.
"""

import sys

VERSION = "1.1"

# ("GET", "status") is public on purpose. The page is installed by a runtime
# patch that only runs once this module is touched, and every other route here
# needs a key - which locked the operator out of their own page, because a
# browser cannot send an Authorization header. The status route reveals only
# that the desk exists and where the page is.
PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/bind-desk", "/bind-desk.html", "/binddesk")
_patched = [False]


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Bind desk</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0f1e;color:#e8ecf5;font-family:ui-monospace,Menlo,monospace;
 font-size:14px;line-height:1.55;padding:0 0 80px}
.w{max-width:620px;margin:0 auto;padding:22px 16px}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:#6b7894;font-size:12.5px;margin-bottom:22px}
h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#c9a84c;
 margin:0 0 12px}
label{display:block;font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#6b7894;margin:12px 0 6px}
input{width:100%;background:#131b2e;border:1px solid #223052;color:#e8ecf5;
 font-family:inherit;font-size:14px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:#c9a84c}
button{width:100%;background:#c9a84c;color:#0a0f1e;border:0;border-radius:4px;
 padding:14px;font-family:inherit;font-weight:700;font-size:14px;margin-top:12px;
 cursor:pointer}
button:active{opacity:.8}
button.q{background:transparent;color:#8f98ad;border:1px solid #223052;font-weight:400}
button.danger{background:transparent;color:#ff8a80;border:1px solid #4a2422;font-weight:400}
.card{background:#131b2e;border:1px solid #223052;border-radius:7px;
 padding:18px;margin:16px 0}
.note{color:#6b7894;font-size:11.5px;line-height:1.6;margin-top:10px}
.out{margin-top:12px;font-size:12px;white-space:pre-wrap;word-break:break-all;
 background:#080c16;border:1px solid #223052;border-radius:4px;padding:12px;
 max-height:320px;overflow:auto}
.ok{color:#7fe3b0}.bad{color:#ff8a80}.warn{color:#c9a84c}
.secret{background:#0f1c15;border:1px solid #2c5c44;border-radius:5px;
 padding:14px;margin-top:12px}
.secret .lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#7fe3b0;margin-bottom:6px}
.secret .val{font-size:13px;color:#7fe3b0;word-break:break-all;line-height:1.8}
.secret .warnline{color:#c9a84c;font-size:11.5px;margin-top:10px;line-height:1.6}
.step{display:inline-block;background:#223052;color:#8f98ad;border-radius:3px;
 padding:2px 8px;font-size:11px;margin-bottom:10px}
</style></head><body><div class="w">

<h1>Bind desk</h1>
<p class="sub">Names on the witness network. Your key stays in this tab.</p>

<div class="card">
  <label for="k">Your API key</label>
  <input id="k" type="password" placeholder="paste it here" autocomplete="off">
  <p class="note">Typed once, used by every button below. Nothing is stored.</p>
</div>

<div class="card">
  <span class="step">STEP 1</span>
  <h2>Claim a name</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">Puts a dated marker in
  the chain. Does not stop anyone else submitting — but theirs is provably
  later. Do this first if the name is exposed.</p>
  <label for="cn">Name</label>
  <input id="cn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="cc">Who is claiming it</label>
  <input id="cc" placeholder="Ishaan">
  <label for="cnote">Note (optional)</label>
  <input id="cnote" placeholder="pending credential">
  <button onclick="doClaim()">Seal the claim</button>
  <div id="o-claim"></div>
</div>

<div class="card">
  <span class="step">STEP 2</span>
  <h2>Issue a credential</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">This is the real fix.
  Once issued, only the holder of the secret can submit under that name.</p>
  <label for="in">Name</label>
  <input id="in" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="ito">Issued to</label>
  <input id="ito" placeholder="Ishaan">
  <button onclick="doIssue(false)">Issue it</button>
  <button class="q" onclick="doIssue(true)">Replace the existing one</button>
  <div id="o-issue"></div>
</div>

<div class="card">
  <h2>Check a name</h2>
  <label for="qn">Name</label>
  <input id="qn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <button class="q" onclick="doLook()">Look it up</button>
  <button class="q" onclick="doConflicts()">Show every contested name</button>
  <div id="o-look"></div>
</div>

<div class="card">
  <h2>Revoke a credential</h2>
  <label for="rk">Key id</label>
  <input id="rk" placeholder="bk_..." autocapitalize="off" autocorrect="off">
  <label for="rr">Reason</label>
  <input id="rr" placeholder="rotating">
  <button class="danger" onclick="doRevoke()">Revoke</button>
  <p class="note">Stops future submissions. Anything already bound stays bound.</p>
  <div id="o-revoke"></div>
</div>

</div>
<script>
var $=function(i){return document.getElementById(i)};
function key(){var k=$('k').value.trim();return k||null}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function show(id,cls,txt){$(id).innerHTML='<div class="out '+cls+'">'+esc(txt)+'</div>'}
function shown(id,html){$(id).innerHTML=html}

async function call(path,method,body){
  var k=key();
  if(!k){return {status:0,data:{error:'paste your key at the top first'}}}
  var o={method:method,headers:{'Authorization':'Bearer '+k}};
  if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  try{
    var r=await fetch(path,o);
    var d; try{d=await r.json()}catch(e){d={error:'unreadable response'}}
    return {status:r.status,data:d};
  }catch(e){return {status:0,data:{error:'could not reach the server'}}}
}

async function doClaim(){
  var n=$('cn').value.trim(), c=$('cc').value.trim();
  if(!n||!c){show('o-claim','bad','Fill in the name and who is claiming it.');return}
  show('o-claim','','Sealing...');
  var r=await call('/x/bind/claim','POST',{name:n,claimant:c,note:$('cnote').value.trim()});
  if(r.status!==200){show('o-claim','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-claim','ok','CLAIMED\\n\\nname     '+r.data.name
    +'\\nclaimant '+r.data.claimant
    +'\\nsealed   '+r.data.sealed_in_chain
    +'\\nblock    '+r.data.block_index
    +'\\n\\nThis is a dated marker, not a binding. Do step 2.');
}

async function doIssue(replace){
  var n=$('in').value.trim(), t=$('ito').value.trim();
  if(!n){show('o-issue','bad','Enter the name.');return}
  show('o-issue','','Issuing...');
  var r=await call('/x/bind/issue','POST',{name:n,issued_to:t,replace:!!replace});
  if(r.status===409){
    show('o-issue','warn','A credential already exists for '+n
      +'.\\n\\nUse "Replace the existing one" if you mean to revoke it and issue another.');
    return;
  }
  if(r.status!==200){show('o-issue','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  shown('o-issue','<div class="secret">'
    +'<div class="lbl">send both of these to them privately</div>'
    +'<div class="val">key_id&nbsp;&nbsp;'+esc(r.data.key_id)+'</div>'
    +'<div class="val">secret&nbsp;&nbsp;'+esc(r.data.secret)+'</div>'
    +'<div class="warnline">The secret is shown here once and is not stored '
    +'anywhere. Copy it now. If it is lost you have to revoke and reissue.</div>'
    +'<div class="warnline">Do not send it over LinkedIn or anywhere public.</div>'
    +'</div>'
    +'<div class="out ok">sealed  '+esc(r.data.sealed_in_chain)
    +'\\nblock   '+esc(r.data.block_index)+'</div>');
}

async function doLook(){
  var n=$('qn').value.trim();
  if(!n){show('o-look','bad','Enter a name.');return}
  show('o-look','','Looking...');
  var r=await call('/x/bind/name?name='+encodeURIComponent(n),'GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'not found');return}
  var d=r.data;
  var cls = d.state==='bound' ? 'ok' : 'warn';
  var t='STATE   '+d.state.toUpperCase()+'\\n\\n'+d.meaning+'\\n';
  if(d.credential){t+='\\nkey_id     '+d.credential.key_id
    +'\\nissued to  '+(d.credential.issued_to||'-')
    +'\\nissued at  '+d.credential.issued_at;}
  if(d.claims&&d.claims.length){t+='\\n\\nCLAIMS';
    d.claims.forEach(function(c){t+='\\n  '+c.claimant+'  '+c.claimed_at
      +'  block '+c.block_index;});}
  if(d.signed_submissions&&d.signed_submissions.length){
    t+='\\n\\nSIGNED SUBMISSIONS  '+d.signed_submissions.length;
    d.signed_submissions.slice(0,5).forEach(function(s){
      t+='\\n  '+s.at+'  block '+s.block_index;});}
  show('o-look',cls,t);
}

async function doConflicts(){
  show('o-look','','Checking...');
  var r=await call('/x/bind/conflicts','GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'failed');return}
  var d=r.data, t='';
  if(!d.contested_claims.length && !d.names_with_multiple_live_credentials.length){
    t='No contested names.';
  } else {
    d.contested_claims.forEach(function(c){t+='CONTESTED  '+c.name+'  ('+c.claimants+' claimants)\\n'});
    d.names_with_multiple_live_credentials.forEach(function(c){
      t+='MULTIPLE CREDENTIALS  '+c.name+'  ('+c.credentials+')\\n'});
  }
  show('o-look', t==='No contested names.'?'ok':'warn', t+'\\n\\n'+d.note);
}

async function doRevoke(){
  var k=$('rk').value.trim();
  if(!k){show('o-revoke','bad','Enter the key id.');return}
  show('o-revoke','','Revoking...');
  var r=await call('/x/bind/revoke','POST',{key_id:k,reason:$('rr').value.trim()});
  if(r.status!==200){show('o-revoke','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-revoke','ok','REVOKED\\n\\nname    '+r.data.name
    +'\\nkey_id  '+r.data.key_id
    +'\\nsealed  '+r.data.sealed_in_chain
    +'\\n\\n'+r.data.note);
}
</script></body></html>"""


def _install():
    if _patched[0]:
        return "already installed"
    m = sys.modules.get("__main__")
    srv = m if (m is not None and hasattr(m, "get_bearer")) else sys.modules.get("server")
    if srv is None:
        return "no server"
    H = getattr(srv, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_binddesk_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._binddesk_patched = True
    _patched[0] = True
    print("BINDDESK: /bind-desk installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    state = _install()
    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"binddesk_version": VERSION,
                "installed": bool(_patched[0]),
                "install_result": state,
                "page": "/bind-desk",
                "engine": "/x/bind/spec",
                "what_it_does": ("Buttons for the signed lane. Claim a name, "
                                 "issue a credential, look one up, revoke one. "
                                 "The page sends the same POST requests the "
                                 "engine already accepts."),
                "note": "The page is not public in any useful sense - it is "
                        "inert until a key is pasted into it, and every route "
                        "it calls checks that key."}, 200

    if not api_key:
        return {"error": "invalid_api_key",
                "note": "Use the page at /bind-desk."}, 401

    return {"error": "unknown_action", "GET": ["status"]}, 404

```


## `modules/blocks.py`

397 lines, 15562 bytes

```python
"""
modules/blocks.py  v1.0.1
=========================
Paged reads of the audit chain, for the command centre.

WHY THIS EXISTS
---------------
/admin/audit calls verify_chain() on every single request. That rewalks and
rehashes every block in the chain while holding the database lock, so the
cost of asking for twenty rows is the cost of re-verifying the whole log.
On a single replica that hold is long enough for Railway to decide the app
has stopped responding, and the container gets killed -- which also wipes
the in-memory admin tokens, so the next call comes back 401.

This module does the one thing the block view actually needs: read rows.
No verification, no rehashing, no full-table walk. Verification stays where
it belongs, on its own route, run deliberately.

WHAT IT ADDS
------------
offset. /admin/audit has no offset and caps at 1000, so nothing older than
the newest thousand blocks could ever be reached. This pages through the
entire chain, oldest to newest or newest to oldest, in small bites.

v1.0.1 -- THE COMMENT WAS WRONG, SO THE CODE IS NOW RIGHT
---------------------------------------------------------
v1.0 said column names were read from the live schema so a future ALTER TABLE
could not silently break it. They were not. The SELECT was hardcoded and rows
were unpacked by position, r[0] through r[5], with the discovered column set
passed into the row shaper and never used. Renaming or reordering a column
would have 500'd every route.

Now it genuinely does what it said: PRAGMA table_info picks the real column
names once, each candidate is resolved against what actually exists, rows come
back as dicts keyed by name, and a missing column is reported in /status
instead of surfacing as a query error later. Same discipline complete.py uses.

ROUTES
------
  GET  /x/blocks/status                       module state, row count, schema
  GET  /x/blocks/list?limit=&offset=&order=   a page of blocks
  GET  /x/blocks/get?seq=                     one block in full
  GET  /x/blocks/around?seq=&span=            a window either side of a block
  GET  /x/blocks/links?limit=&offset=         link check over a page only
  GET  /x/blocks/spec                         what this serves

Every route is keyed. Audit rows are not public.

LINK CHECKING
-------------
/links checks prev_hash against the preceding row's audit_hash across the
page you asked for, and nothing else. It reports which pairs it compared so
a caller can never mistake a clean page for a clean chain. Whole-chain
verification is /api/verify-chain and is deliberately not duplicated here.
"""

import json

VERSION = "1.0.1"

# Nothing here is public. Audit rows are customer data.
PUBLIC = set()

MAX_LIMIT = 200          # a page, not a dump
DEFAULT_LIMIT = 50
MAX_SPAN = 100

# What this module needs, and the column names it will accept for each. The
# first name that exists in the live table wins. Nothing is assumed.
WANTED = {
    "seq": ["id", "rowid", "block_index", "seq"],
    "ts": ["ts", "timestamp", "created", "time"],
    "user_id": ["user_id", "subject", "customer_id"],
    "result": ["result_json", "result", "payload", "event_json"],
    "prev_hash": ["prev_hash", "previous_hash", "prev"],
    "audit_hash": ["audit_hash", "hash", "seal"],
}

_schema = {"resolved": None, "missing": None, "columns": None}


def _ctx_get(ctx, name):
    """ctx may be an object with attributes or a plain dict, depending on how
    the router builds it. Take either rather than assuming."""
    v = getattr(ctx, name, None)
    if v is None and isinstance(ctx, dict):
        v = ctx.get(name)
    return v


class _NoLock(object):
    """Used only if the router hands us no lock, so a missing lock degrades
    to running without one instead of raising on entry."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _one(v):
    """A query value can arrive as a string or as a one-item list, depending
    on how the querystring was parsed. Take either."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else ""
    return v


def _cols(conn):
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    except Exception:
        return []


def _resolve(conn):
    """Work out, once, which real column serves each role. Cached because the
    schema does not change between requests, re-derived if it ever comes back
    empty so a transient failure does not stick."""
    if _schema["resolved"]:
        return _schema["resolved"], _schema["missing"]
    cols = _cols(conn)
    lower = {c.lower(): c for c in cols}
    resolved, missing = {}, []
    for role, candidates in WANTED.items():
        hit = None
        for cand in candidates:
            if cand.lower() in lower:
                hit = lower[cand.lower()]
                break
        if hit:
            resolved[role] = hit
        else:
            missing.append(role)
    if resolved:
        _schema["resolved"] = resolved
        _schema["missing"] = missing
        _schema["columns"] = cols
    return resolved, missing


def _select(resolved, roles):
    """Build a SELECT from real column names, aliased to the role names, so
    rows come back keyed by role and never by position."""
    parts = ["%s AS %s" % (resolved[r], r) for r in roles if r in resolved]
    return "SELECT " + ",".join(parts) + " FROM audit_log"


def _dicts(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _int(data, name, default, lo, hi):
    try:
        v = int(_one(data.get(name, default)))
    except Exception:
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _str(data, name, default=""):
    v = _one(data.get(name, default))
    return "" if v is None else str(v).strip()


def _shape(d):
    """One row, from a dict keyed by role. Missing roles come back as None
    rather than raising, so a partial schema degrades instead of failing."""
    out = {
        "seq": d.get("seq"),
        "ts": d.get("ts"),
        "user_id": d.get("user_id"),
        "prev_hash": d.get("prev_hash"),
        "audit_hash": d.get("audit_hash"),
    }
    raw = d.get("result")
    try:
        res = json.loads(raw) if raw else {}
    except Exception:
        res = {}
    if isinstance(res, dict):
        out["decision"] = res.get("decision", res.get("result", ""))
        out["score"] = res.get("score", "")
        rs = res.get("reasons", [])
        out["reasons"] = rs if isinstance(rs, list) else ([str(rs)] if rs else [])
    else:
        out["decision"] = ""
        out["score"] = ""
        out["reasons"] = []
    return out


ROLES = ["seq", "ts", "user_id", "result", "prev_hash", "audit_hash"]


def handle(method, action, data, api_key, ctx):
    if not isinstance(data, dict):
        data = {}

    conn = _ctx_get(ctx, "conn")
    lock = _ctx_get(ctx, "lock") or _NoLock()
    if conn is None:
        return {"error": "no database handle on ctx",
                "ctx_type": type(ctx).__name__}, 500

    with lock:
        resolved, missing = _resolve(conn)
    if not resolved or "seq" not in resolved or "audit_hash" not in resolved:
        return {"error": "audit_log schema not recognised",
                "columns_found": _schema.get("columns") or _cols(conn),
                "roles_missing": missing,
                "note": ("This module maps roles onto real column names. Add the "
                         "actual name to WANTED rather than assuming a shape.")}, 500

    SEL = _select(resolved, ROLES)
    idc = resolved["seq"]
    hashc = resolved["audit_hash"]
    prevc = resolved.get("prev_hash")

    # ---------------------------------------------------------------- status
    if action == "status":
        with lock:
            try:
                n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                lo = conn.execute("SELECT MIN(%s) FROM audit_log" % idc).fetchone()[0]
                hi = conn.execute("SELECT MAX(%s) FROM audit_log" % idc).fetchone()[0]
            except Exception as e:
                return {"error": "audit_log unreadable: " + str(e)}, 500
        return {
            "module": "blocks",
            "version": VERSION,
            "rows": n,
            "lowest_seq": lo,
            "highest_seq": hi,
            "schema_columns": _schema.get("columns"),
            "role_mapping": resolved,
            "roles_missing": missing,
            "has_api_key_column": "api_key" in [c.lower() for c in (_schema.get("columns") or [])],
            "max_limit": MAX_LIMIT,
            "note": "reads only. no chain verification happens on this route.",
        }, 200

    # ------------------------------------------------------------------ list
    if action == "list":
        limit = _int(data, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        order = _str(data, "order", "desc").lower()
        order = "ASC" if order == "asc" else "DESC"
        filt = _str(data, "api_key", "")
        has_key_col = "api_key" in [c.lower() for c in (_schema.get("columns") or [])]

        with lock:
            try:
                if filt and has_key_col:
                    cur = conn.execute(
                        SEL + " WHERE api_key=? ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (filt, limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE api_key=?", (filt,)).fetchone()[0]
                else:
                    cur = conn.execute(
                        SEL + " ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            except Exception as e:
                return {"error": "query failed: " + str(e)}, 500

        return {
            "blocks": recs,
            "count": len(recs),
            "total": total,
            "limit": limit,
            "offset": offset,
            "order": order.lower(),
            "has_more": (offset + len(recs)) < total,
            "next_offset": offset + len(recs),
            "filtered_by_key": bool(filt and has_key_col),
            "filter_ignored": bool(filt and not has_key_col) or None,
        }, 200

    # ------------------------------------------------------------------- get
    if action == "get":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        with lock:
            cur = conn.execute(SEL + " WHERE %s=?" % idc, (seq,))
            rows = _dicts(cur)
            if not rows:
                return {"error": "no block with that seq", "seq": seq}, 404
            below = conn.execute(
                "SELECT %s,%s FROM audit_log WHERE %s<? ORDER BY %s DESC LIMIT 1"
                % (idc, hashc, idc, idc), (seq,)).fetchone()
        block = _shape(rows[0])
        if below and prevc:
            block["links_to"] = below[0]
            block["link_holds"] = (str(block.get("prev_hash") or "") == str(below[1] or ""))
            block["expected_prev"] = below[1]
        elif not prevc:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "this table has no prev_hash column, so no link can be checked"
        else:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "oldest row in the table; nothing beneath it to link to"
        return {"block": block}, 200

    # ---------------------------------------------------------------- around
    if action == "around":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        span = _int(data, "span", 10, 1, MAX_SPAN)
        with lock:
            cur = conn.execute(
                SEL + " WHERE %s BETWEEN ? AND ? ORDER BY %s DESC" % (idc, idc),
                (seq - span, seq + span))
            rows = _dicts(cur)
        return {
            "centre": seq,
            "span": span,
            "blocks": [_shape(d) for d in rows],
        }, 200

    # ----------------------------------------------------------------- links
    if action == "links":
        if not prevc:
            return {"error": "no prev_hash column in this table",
                    "note": "there is no link to check without one"}, 400
        limit = _int(data, "limit", DEFAULT_LIMIT, 2, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        with lock:
            rows = conn.execute(
                "SELECT %s,%s,%s FROM audit_log ORDER BY %s DESC LIMIT ? OFFSET ?"
                % (idc, prevc, hashc, idc), (limit, offset)).fetchall()
        broken = []
        for i in range(len(rows) - 1):
            newer, older = rows[i], rows[i + 1]
            if str(newer[1] or "") != str(older[2] or ""):
                broken.append({
                    "between": newer[0],
                    "and": older[0],
                    "expected_prev": older[2],
                    "found_prev": newer[1],
                })
        checked = max(0, len(rows) - 1)
        return {
            "pairs_checked": checked,
            "broken": broken,
            "clean": len(broken) == 0,
            "range": {"newest_seq": rows[0][0] if rows else None,
                      "oldest_seq": rows[-1][0] if rows else None},
            "scope": ("this page only. a clean page is not a clean chain — "
                      "whole-chain verification is /api/verify-chain"),
        }, 200

    # ------------------------------------------------------------------ spec
    if action == "spec":
        return {
            "module": "blocks",
            "version": VERSION,
            "purpose": ("paged reads of audit_log for the operator block view, "
                        "without re-verifying the whole chain on every request"),
            "auth": "every route requires a key",
            "schema_handling": ("column names are resolved against PRAGMA "
                                "table_info at first use and rows are read by "
                                "name, so a renamed column is reported in "
                                "/status rather than breaking a query"),
            "role_mapping": resolved,
            "routes": {
                "GET status": "row count, lowest and highest seq, resolved column names",
                "GET list": "limit (max %d), offset, order=asc|desc, api_key" % MAX_LIMIT,
                "GET get": "seq — one block, plus whether its link to the row below holds",
                "GET around": "seq, span (max %d) — a window either side" % MAX_SPAN,
                "GET links": "limit, offset — link check across that page only",
            },
            "deliberately_not_here": [
                "whole-chain verification — that is /api/verify-chain",
                "writes of any kind",
                "any public route",
            ],
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["GET status", "GET list", "GET get",
                          "GET around", "GET links", "GET spec"]}, 404

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


## `modules/cinema.py`

273 lines, 21953 bytes

```python
"""
modules/cinema.py  v1.2.0
The sebbi.pro Cinema at /cinema. A spinning axle of screens, each a channel of
AI governance videos; robots in the audience; a screening room with a spinning
TV and a channel bar. Videos play from their original YouTube channels.
To add a permanent channel, add a line to CHANNELS in the page (base64 below
is generated from cinema.html); visitors can also add their own on their device.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/cinema/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.2.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPnNlYmJpLnBybyBDaW5lbWEg4oCUIEFJIGdvdmVybmFuY2Ugb24gZXZlcnkgc2NyZWVuPC90aXRsZT4KPG1ldGEgbmFtZT0i"
    "ZGVzY3JpcHRpb24iIGNvbnRlbnQ9IlNwaW4gdGhlIHNjcmVlbnMsIHBpY2sgYSBjaGFubmVsLCBhbmQgd2F0Y2ggQUkgZ292ZXJu"
    "YW5jZSBleHBsYWluZWQsIGluIHRoZSBzZWJiaS5wcm8gY2luZW1hLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xl"
    "YXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs1MDAmZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0"
    "QDYuLjcyLDUwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzA1MDcwZjstLWlu"
    "azI6IzBkMTQyNDstLWdvbGQ6I2M5YTg0YzstLW9rOiM3ZmUzYjA7LS1ibHVlOiM4ZmQwZmY7LS1tdXRlOiM4YTkzYWR9Cip7Ym94"
    "LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3BhZGRpbmc6MDstd2Via2l0LXRhcC1oaWdobGlnaHQtY29sb3I6dHJhbnNwYXJl"
    "bnR9Cmh0bWwsYm9keXtoZWlnaHQ6MTAwJTtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAzMCUsIzEx"
    "MWEzMyAwJSwjMDUwNzBmIDcwJSk7Y29sb3I6I2U4ZWRmNztmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsdWktbW9ub3NwYWNl"
    "LG1vbm9zcGFjZTtvdmVyZmxvdzpoaWRkZW59Ci52aWV3e3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7ZGlzcGxheTpmbGV4O2ZsZXgt"
    "ZGlyZWN0aW9uOmNvbHVtbjthbGlnbi1pdGVtczpjZW50ZXI7dHJhbnNpdGlvbjpvcGFjaXR5IC42c30KLmhpZGRlbntvcGFjaXR5"
    "OjA7cG9pbnRlci1ldmVudHM6bm9uZX0KaGVhZGVye3dpZHRoOjEwMCU7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVh"
    "LWluc2V0LXRvcCkpIDE2cHggMDt0ZXh0LWFsaWduOmNlbnRlcn0KLmJyYW5ke2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11"
    "dGUpfS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KaDF7Zm9udC1mYW1pbHk6J05ld3NyZWFkZXIn"
    "LEdlb3JnaWEsc2VyaWY7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyOHB4LDZ2dyw0NnB4KTttYXJnaW46NnB4IDAg"
    "MnB4O2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLCNjOWE4NGMsIzdmZTNiMCwjOGZkMGZmKTstd2Via2l0LWJhY2tn"
    "cm91bmQtY2xpcDp0ZXh0O2JhY2tncm91bmQtY2xpcDp0ZXh0O2NvbG9yOnRyYW5zcGFyZW50fQouc3Vie2ZvbnQtc2l6ZToxMS41"
    "cHg7Y29sb3I6dmFyKC0tbXV0ZSk7bGV0dGVyLXNwYWNpbmc6LjA2ZW19Ci8qIHRoZSBzcGlubmluZyBheGxlICovCi5zdGFnZXtm"
    "bGV4OjE7d2lkdGg6MTAwJTtwZXJzcGVjdGl2ZToxMTAwcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5"
    "LWNvbnRlbnQ6Y2VudGVyO3RvdWNoLWFjdGlvbjpwYW4teX0KLnJpbmd7cG9zaXRpb246cmVsYXRpdmU7d2lkdGg6MjQwcHg7aGVp"
    "Z2h0OjE1MHB4O3RyYW5zZm9ybS1zdHlsZTpwcmVzZXJ2ZS0zZH0KLnNjcmVlbntwb3NpdGlvbjphYnNvbHV0ZTtpbnNldDowO2Jv"
    "cmRlci1yYWRpdXM6MTBweDtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMGIxMjI0O2JvcmRlcjoxLjVweCBzb2xpZCByZ2Jh"
    "KDIwMSwxNjgsNzYsLjQ1KTtib3gtc2hhZG93OjAgMCAzMHB4IHJnYmEoMTQzLDIwOCwyNTUsLjE4KTtiYWNrZmFjZS12aXNpYmls"
    "aXR5OmhpZGRlbjtjdXJzb3I6cG9pbnRlcjt0cmFuc2l0aW9uOmJvcmRlci1jb2xvciAuM3MsYm94LXNoYWRvdyAuM3N9Ci5zY3Jl"
    "ZW4gaW1ne3dpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb3ZlcjtvcGFjaXR5Oi44NX0KLnNjcmVlbiAubGFie3Bv"
    "c2l0aW9uOmFic29sdXRlO2xlZnQ6MDtyaWdodDowO2JvdHRvbTowO3BhZGRpbmc6MThweCA5cHggN3B4O2ZvbnQtc2l6ZToxMC41"
    "cHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQodHJhbnNwYXJlbnQscmdiYSg1LDcsMTUsLjkyKSl9Ci5zY3JlZW4gLmNoe3Bv"
    "c2l0aW9uOmFic29sdXRlO3RvcDo3cHg7bGVmdDo4cHg7Zm9udC1zaXplOjkuNXB4O2xldHRlci1zcGFjaW5nOi4xZW07Y29sb3I6"
    "dmFyKC0tZ29sZCk7YmFja2dyb3VuZDpyZ2JhKDUsNywxNSwuNzUpO3BhZGRpbmc6MnB4IDZweDtib3JkZXItcmFkaXVzOjNweH0K"
    "LnNjcmVlbi5vbntib3JkZXItY29sb3I6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDQwcHggcmdiYSgxMjcsMjI3LDE3NiwuNDUp"
    "fQouYXhsZXtwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjUwJTt0b3A6NTAlO3dpZHRoOjZweDtoZWlnaHQ6MjQwcHg7bWFyZ2luOi0x"
    "MjBweCAwIDAgLTNweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgjYzlhODRjLCM1YTRhMWMpO2JvcmRlci1yYWRpdXM6M3B4"
    "O3RyYW5zZm9ybTp0cmFuc2xhdGVaKDApO2JveC1zaGFkb3c6MCAwIDE2cHggcmdiYSgyMDEsMTY4LDc2LC41KX0KLyogcm9ib3Qg"
    "YXVkaWVuY2UgKi8KLmNyb3dke2Rpc3BsYXk6ZmxleDtnYXA6NnB4O2p1c3RpZnktY29udGVudDpjZW50ZXI7bWFyZ2luLWJvdHRv"
    "bTo4cHg7aGVpZ2h0Ojc0cHg7YWxpZ24taXRlbXM6ZmxleC1lbmR9Ci5ib3R7d2lkdGg6NDBweDtoZWlnaHQ6NjZweDtwb3NpdGlv"
    "bjpyZWxhdGl2ZTthbmltYXRpb246Ym9iIDNzIGVhc2UtaW4tb3V0IGluZmluaXRlfQouYm90Om50aC1jaGlsZCgybil7YW5pbWF0"
    "aW9uLWRlbGF5Oi42c30uYm90Om50aC1jaGlsZCgzbil7YW5pbWF0aW9uLWRlbGF5OjEuMXN9CkBrZXlmcmFtZXMgYm9iezUwJXt0"
    "cmFuc2Zvcm06dHJhbnNsYXRlWSgtMnB4KX19Ci5ib3QgLmhlYWR7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDo5cHg7d2lk"
    "dGg6MjJweDtoZWlnaHQ6MThweDtib3JkZXItcmFkaXVzOjVweDtiYWNrZ3JvdW5kOiNkOGRkZTZ9Ci5ib3QgLnZpc29ye3Bvc2l0"
    "aW9uOmFic29sdXRlO3RvcDo2cHg7bGVmdDozcHg7d2lkdGg6MTZweDtoZWlnaHQ6NXB4O2JvcmRlci1yYWRpdXM6MnB4O2JhY2tn"
    "cm91bmQ6dmFyKC0tZ29sZCk7Ym94LXNoYWRvdzowIDAgOHB4IHZhcigtLWdvbGQpO3RyYW5zaXRpb246YmFja2dyb3VuZCAuNHMs"
    "Ym94LXNoYWRvdyAuNHN9Ci5ib3QgLmJvZHl7cG9zaXRpb246YWJzb2x1dGU7dG9wOjIwcHg7bGVmdDo2cHg7d2lkdGg6MjhweDto"
    "ZWlnaHQ6MjRweDtib3JkZXItcmFkaXVzOjVweDtiYWNrZ3JvdW5kOiNjM2M5ZDR9Ci5ib3QgLnNlYXR7cG9zaXRpb246YWJzb2x1"
    "dGU7Ym90dG9tOjA7bGVmdDowO3dpZHRoOjQwcHg7aGVpZ2h0OjI0cHg7Ym9yZGVyLXJhZGl1czo2cHggNnB4IDNweCAzcHg7YmFj"
    "a2dyb3VuZDojMWIyMzM2O2JvcmRlci10b3A6MnB4IHNvbGlkICMyYTM1NTJ9Ci5ub3d7Zm9udC1zaXplOjEycHg7dGV4dC1hbGln"
    "bjpjZW50ZXI7bWluLWhlaWdodDoxOHB4O21hcmdpbi1ib3R0b206OHB4O2NvbG9yOnZhcigtLW9rKTtwYWRkaW5nOjAgMTJweH0K"
    "LmJhcntkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3BhZGRpbmc6MCAx"
    "MnB4IGNhbGMoMTZweCArIGVudihzYWZlLWFyZWEtaW5zZXQtYm90dG9tKSl9Ci5idG57Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czo4"
    "cHg7cGFkZGluZzoxMXB4IDE1cHg7Zm9udDo1MDAgMTIuNXB4ICdJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7YmFja2dyb3VuZDp2"
    "YXIoLS1nb2xkKTtjb2xvcjojMDUwNzBmO2N1cnNvcjpwb2ludGVyfQouYnRuLmdob3N0e2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7"
    "Y29sb3I6I2U4ZWRmNztib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KX0KLyogdGhlIHJvb20gKi8KLnJvb217"
    "cGVyc3BlY3RpdmU6OTAwcHh9Ci5mbG9vcntwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0Oi01MCU7cmlnaHQ6LTUwJTtib3R0b206LTEw"
    "JTtoZWlnaHQ6NjAlO2JhY2tncm91bmQ6cmVwZWF0aW5nLWxpbmVhci1ncmFkaWVudCg5MGRlZyxyZ2JhKDIwMSwxNjgsNzYsLjE4"
    "KSAwIDFweCx0cmFuc3BhcmVudCAxcHggNjBweCkscmVwZWF0aW5nLWxpbmVhci1ncmFkaWVudCgwZGVnLHJnYmEoMjAxLDE2OCw3"
    "NiwuMTgpIDAgMXB4LHRyYW5zcGFyZW50IDFweCA2MHB4KTt0cmFuc2Zvcm06cm90YXRlWCg3MmRlZyk7dHJhbnNmb3JtLW9yaWdp"
    "bjpib3R0b207cG9pbnRlci1ldmVudHM6bm9uZX0KLnR2d3JhcHtmbGV4OjE7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRl"
    "cjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3dpZHRoOjEwMCU7cGVyc3BlY3RpdmU6MTAwMHB4fQoudHZ7d2lkdGg6bWluKDkydncs"
    "NzIwcHgpO2FzcGVjdC1yYXRpbzoxNi85O2JvcmRlci1yYWRpdXM6MTRweDtiYWNrZ3JvdW5kOiMwMDA7Ym9yZGVyOjEwcHggc29s"
    "aWQgIzFiMjMzNjtvdXRsaW5lOjJweCBzb2xpZCByZ2JhKDIwMSwxNjgsNzYsLjUpO2JveC1zaGFkb3c6MCAwIDYwcHggcmdiYSgx"
    "NDMsMjA4LDI1NSwuMjUpLDAgMzBweCA2MHB4IHJnYmEoMCwwLDAsLjYpO3RyYW5zaXRpb246dHJhbnNmb3JtIC44c30KLnR2Lmlk"
    "bGV7YW5pbWF0aW9uOnN3YXkgOXMgZWFzZS1pbi1vdXQgaW5maW5pdGV9Ci50dmxpbmt7ZGlzcGxheTpibG9jazt0ZXh0LWFsaWdu"
    "OmNlbnRlcjtmb250LXNpemU6MTFweDtjb2xvcjojOGZkMGZmO21hcmdpbi10b3A6OHB4O3RleHQtZGVjb3JhdGlvbjpub25lfQou"
    "dHYuc3BpbnthbmltYXRpb246ZnVsbHNwaW4gMTRzIGxpbmVhciBpbmZpbml0ZX0KQGtleWZyYW1lcyBzd2F5ezAlLDEwMCV7dHJh"
    "bnNmb3JtOnJvdGF0ZVkoLTEwZGVnKSByb3RhdGVYKDNkZWcpfTUwJXt0cmFuc2Zvcm06cm90YXRlWSgxMGRlZykgcm90YXRlWCgt"
    "MmRlZyl9fQpAa2V5ZnJhbWVzIGZ1bGxzcGlue3Rve3RyYW5zZm9ybTpyb3RhdGVZKDM2MGRlZyl9fQoudHYgaWZyYW1le3dpZHRo"
    "OjEwMCU7aGVpZ2h0OjEwMCU7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czo0cHg7ZGlzcGxheTpibG9ja30KLmNoYW5ze2Rpc3BsYXk6"
    "ZmxleDtnYXA6NnB4O292ZXJmbG93LXg6YXV0bzttYXgtd2lkdGg6MTAwJTtwYWRkaW5nOjhweCAxMnB4O3Njcm9sbGJhci13aWR0"
    "aDpub25lfQouY2hhbnMgYnV0dG9ue2ZsZXg6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAxLDE2OCw3NiwuMzUpO2JhY2tn"
    "cm91bmQ6cmdiYSgxMywyMCwzNiwuOCk7Y29sb3I6I2U4ZWRmNztib3JkZXItcmFkaXVzOjdweDtwYWRkaW5nOjhweCAxMXB4O2Zv"
    "bnQ6NTAwIDExLjVweCAnSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2N1cnNvcjpwb2ludGVyfQouY2hhbnMgYnV0dG9uLm9ue2Jv"
    "cmRlci1jb2xvcjp2YXIoLS1vayk7Y29sb3I6dmFyKC0tb2spfQouZm9vdHtmb250LXNpemU6MTAuNXB4O2NvbG9yOnZhcigtLW11"
    "dGUpO3RleHQtYWxpZ246Y2VudGVyO3BhZGRpbmc6MCAxNnB4IDZweH0KPC9zdHlsZT48L2hlYWQ+PGJvZHk+Cgo8c2VjdGlvbiBj"
    "bGFzcz0idmlldyIgaWQ9ImxvYmJ5Ij4KIDxoZWFkZXI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgQ0lO"
    "RU1BPC9kaXY+PGgxPkFJIGdvdmVybmFuY2UsIG9uIGV2ZXJ5IHNjcmVlbi48L2gxPjxkaXYgY2xhc3M9InN1YiI+RFJBRyBUTyBT"
    "UElOIMK3IFRBUCBBIFNDUkVFTiDCtyBFTlRFUiBUSEUgUk9PTSBUTyBXQVRDSDwvZGl2PjwvaGVhZGVyPgogPGRpdiBjbGFzcz0i"
    "c3RhZ2UiIGlkPSJzdGFnZSI+PGRpdiBjbGFzcz0icmluZyIgaWQ9InJpbmciPjxkaXYgY2xhc3M9ImF4bGUiPjwvZGl2PjwvZGl2"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0ibm93IiBpZD0ibm93Ij48L2Rpdj48ZGl2IGNsYXNzPSJiYXIiIHN0eWxlPSJwYWRkaW5nLWJv"
    "dHRvbTo2cHgiPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0icmVlbFN0ZXAoLTEpIj7il4AgUmVlbDwvYnV0dG9u"
    "PjxzcGFuIGNsYXNzPSJzdWIiIGlkPSJyZWVsTGFiIiBzdHlsZT0iYWxpZ24tc2VsZjpjZW50ZXIiPjwvc3Bhbj48YnV0dG9uIGNs"
    "YXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InJlZWxTdGVwKDEpIj5SZWVsIOKWtjwvYnV0dG9uPjwvZGl2PgogPGRpdiBjbGFzcz0i"
    "Y3Jvd2QiIGlkPSJjcm93ZCI+PC9kaXY+CiA8ZGl2IGNsYXNzPSJiYXIiPjxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0iZW50"
    "ZXIoKSI+RW50ZXIgdGhlIHJvb20g4pa2PC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBvbmNsaWNrPSJhZGRWaWRl"
    "bygpIj4rIEFkZCBhIHZpZGVvPC9idXR0b24+PGEgY2xhc3M9ImJ0biBnaG9zdCIgaHJlZj0iLyIgc3R5bGU9InRleHQtZGVjb3Jh"
    "dGlvbjpub25lIj5Ib21lPC9hPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlvbiBjbGFzcz0idmlldyByb29tIGhpZGRlbiIgaWQ9"
    "InJvb20iPgogPGRpdiBjbGFzcz0iZmxvb3IiPjwvZGl2PgogPGhlYWRlcj48ZGl2IGNsYXNzPSJicmFuZCI+c2ViYmk8Yj4ucHJv"
    "PC9iPiDCtyBUSEUgU0NSRUVOSU5HIFJPT008L2Rpdj48ZGl2IGNsYXNzPSJzdWIiIGlkPSJyb29tTm93Ij48L2Rpdj48L2hlYWRl"
    "cj4KIDxkaXYgY2xhc3M9InR2d3JhcCIgc3R5bGU9ImZsZXgtZGlyZWN0aW9uOmNvbHVtbiI+PGRpdiBjbGFzcz0idHYiIGlkPSJ0"
    "diI+PC9kaXY+PGEgY2xhc3M9InR2bGluayIgaWQ9InR2bGluayIgdGFyZ2V0PSJfYmxhbmsiIHJlbD0ibm9vcGVuZXIiPjwvYT48"
    "L2Rpdj4KIDxkaXYgY2xhc3M9ImNoYW5zIiBpZD0iY2hhbnMiPjwvZGl2PgogPGRpdiBjbGFzcz0iY3Jvd2QiIGlkPSJjcm93ZDIi"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0iYmFyIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InN0ZXAoLTEpIj7il4Ag"
    "Q2hhbm5lbDwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0ic3RlcCgxKSI+Q2hhbm5lbCDilrY8L2J1"
    "dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InRvZ2dsZVNwaW4oKSIgaWQ9InNwaW5CdG4iPlNwaW4gdGhl"
    "IFRWPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJsZWF2ZSgpIj5CYWNrIHRvIHRoZSBsb2JieTwvYnV0dG9u"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0iZm9vdCI+VmlkZW9zIHBsYXkgZnJvbSB0aGVpciBvcmlnaW5hbCBjaGFubmVscyBvbiBZb3VU"
    "dWJlLiBzZWJiaS5wcm8gZG9lcyBub3Qgb3duIG9yIGVuZG9yc2UgdGhpcmQtcGFydHkgY29udGVudC48L2Rpdj4KPC9zZWN0aW9u"
    "PgoKPHNjcmlwdD4KKGZ1bmN0aW9uKCl7CnZhciBDSEFOTkVMUz1bCiB7aWQ6ImdNMWRMZHBEUjUwIix0aXRsZToiV2hhdCBJcyBU"
    "cnVzdHdvcnRoeSBBST8iLGNoYW5uZWw6Ik5WSURJQSJ9LAoge2lkOiJmNmR4M1loLVR3dyIsdGl0bGU6IldoYXQgaXMgQUkgZ292"
    "ZXJuYW5jZT8iLGNoYW5uZWw6IklCTSBSZXNlYXJjaCJ9LAoge2lkOiJRMDIwQy1KdzBvOCIsdGl0bGU6IlRoZSBJbXBvcnRhbmNl"
    "IG9mIEFJIEdvdmVybmFuY2UiLGNoYW5uZWw6IklCTSBUZWNobm9sb2d5In0KXTsKdHJ5e3ZhciBzYXZlZD1KU09OLnBhcnNlKGxv"
    "Y2FsU3RvcmFnZS5nZXRJdGVtKCJzZWJiaS5jaW5lbWEiKXx8IltdIik7aWYoQXJyYXkuaXNBcnJheShzYXZlZCkpQ0hBTk5FTFM9"
    "Q0hBTk5FTFMuY29uY2F0KHNhdmVkKX1jYXRjaChlKXt9CnZhciBjdXI9MCxhbmdsZT0wLHZlbD0uMTIsZHJhZz1udWxsLGxhc3RY"
    "PTAsc3Bpbm5pbmc9ZmFsc2UscmVlbD0wLFBFUj0xMDsKdmFyIHJpbmc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJpbmciKSxu"
    "b3c9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm5vdyIpOwpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmluZyhzKS5yZXBsYWNl"
    "KC9bJjw+Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7"
    "In1bY119KX0KZnVuY3Rpb24gY3Jvd2QoZWwsbil7dmFyIGg9IiI7Zm9yKHZhciBpPTA7aTxuO2krKyloKz0nPGRpdiBjbGFzcz0i"
    "Ym90Ij48ZGl2IGNsYXNzPSJoZWFkIj48ZGl2IGNsYXNzPSJ2aXNvciI+PC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iYm9keSI+PC9k"
    "aXY+PGRpdiBjbGFzcz0ic2VhdCI+PC9kaXY+PC9kaXY+Jztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChlbCkuaW5uZXJIVE1MPWh9"
    "CmNyb3dkKCJjcm93ZCIsTWF0aC5taW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7Y3Jvd2QoImNyb3dkMiIsTWF0aC5t"
    "aW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7CnZhciBWSVM9WyIjYzlhODRjIiwiIzdmZTNiMCIsIiM4ZmQwZmYiLCIj"
    "ZmY4YTgwIiwiI2Q1OWJmZiJdOwpmdW5jdGlvbiB2aXNvcigpe3ZhciBjPVZJU1tjdXIlVklTLmxlbmd0aF07QXJyYXkucHJvdG90"
    "eXBlLmZvckVhY2guY2FsbChkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCIudmlzb3IiKSxmdW5jdGlvbih2KXt2LnN0eWxlLmJh"
    "Y2tncm91bmQ9Yzt2LnN0eWxlLmJveFNoYWRvdz0iMCAwIDhweCAiK2N9KX0KZnVuY3Rpb24gYnVpbGQoKXsKIEFycmF5LnByb3Rv"
    "dHlwZS5mb3JFYWNoLmNhbGwocmluZy5xdWVyeVNlbGVjdG9yQWxsKCIuc2NyZWVuIiksZnVuY3Rpb24ocyl7cy5yZW1vdmUoKX0p"
    "OwogdmFyIHJlZWxzPU1hdGgubWF4KDEsTWF0aC5jZWlsKENIQU5ORUxTLmxlbmd0aC9QRVIpKTtyZWVsPU1hdGgubWluKHJlZWws"
    "cmVlbHMtMSk7CiB2YXIgaXRlbXM9Q0hBTk5FTFMuc2xpY2UocmVlbCpQRVIscmVlbCpQRVIrUEVSKSxiYXNlPXJlZWwqUEVSLG49"
    "TWF0aC5tYXgoaXRlbXMubGVuZ3RoLDUpLHI9TWF0aC5yb3VuZCgxMzUvTWF0aC50YW4oTWF0aC5QSS9uKSkrNDA7CiBmb3IodmFy"
    "IGk9MDtpPG47aSsrKXt2YXIgaz1iYXNlKyhpJWl0ZW1zLmxlbmd0aCksYz1DSEFOTkVMU1trXSxkPWRvY3VtZW50LmNyZWF0ZUVs"
    "ZW1lbnQoImRpdiIpO2QuY2xhc3NOYW1lPSJzY3JlZW4iO2QuZGF0YXNldC5pPWs7CiAgZC5zdHlsZS50cmFuc2Zvcm09InJvdGF0"
    "ZVkoIisoMzYwL24qaSkrImRlZykgdHJhbnNsYXRlWigiK3IrInB4KSI7CiAgZC5pbm5lckhUTUw9JzxpbWcgYWx0PSIiIGxvYWRp"
    "bmc9ImxhenkiIHNyYz0iaHR0cHM6Ly9pbWcueW91dHViZS5jb20vdmkvJytlbmNvZGVVUklDb21wb25lbnQoYy5pZCkrJy9ocWRl"
    "ZmF1bHQuanBnIj48ZGl2IGNsYXNzPSJjaCI+Q0ggJysoaysxKSsnIMK3ICcrZXNjKGMuY2hhbm5lbCkrJzwvZGl2PjxkaXYgY2xh"
    "c3M9ImxhYiI+Jytlc2MoYy50aXRsZSkrJzwvZGl2Pic7CiAgZC5vbmNsaWNrPWZ1bmN0aW9uKCl7cGljaygrdGhpcy5kYXRhc2V0"
    "LmkpfTtyaW5nLmFwcGVuZENoaWxkKGQpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJlZWxMYWIiKS50ZXh0Q29udGVudD0i"
    "UmVlbCAiKyhyZWVsKzEpKyIgb2YgIityZWVscysiIMK3ICIrQ0hBTk5FTFMubGVuZ3RoKyIgdmlkZW9zIjsKIGlmKGN1cjxiYXNl"
    "fHxjdXI+PWJhc2UraXRlbXMubGVuZ3RoKWN1cj1iYXNlO21hcmsoKTtjaGFucygpfQp3aW5kb3cucmVlbFN0ZXA9ZnVuY3Rpb24o"
    "ZCl7dmFyIHJlZWxzPU1hdGgubWF4KDEsTWF0aC5jZWlsKENIQU5ORUxTLmxlbmd0aC9QRVIpKTtyZWVsPShyZWVsK2QrcmVlbHMp"
    "JXJlZWxzO2N1cj1yZWVsKlBFUjtidWlsZCgpfTsKZnVuY3Rpb24gbWFyaygpe0FycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwo"
    "cmluZy5xdWVyeVNlbGVjdG9yQWxsKCIuc2NyZWVuIiksZnVuY3Rpb24ocyl7cy5jbGFzc0xpc3QudG9nZ2xlKCJvbiIsK3MuZGF0"
    "YXNldC5pPT09Y3VyKX0pOwogdmFyIGM9Q0hBTk5FTFNbY3VyXTtub3cudGV4dENvbnRlbnQ9IkNIICIrKGN1cisxKSsiIMK3ICIr"
    "Yy5jaGFubmVsKyIgwrcgIitjLnRpdGxlO3Zpc29yKCl9CmZ1bmN0aW9uIHBpY2soaSl7Y3VyPWk7bWFyaygpO3ZlbD0uMDN9CmZ1"
    "bmN0aW9uIGxvb3AoKXtpZihkcmFnPT09bnVsbCl7YW5nbGUrPXZlbDt2ZWwrPSggLjEyLXZlbCkqLjAxfXJpbmcuc3R5bGUudHJh"
    "bnNmb3JtPSJyb3RhdGVZKCIrYW5nbGUrImRlZykiO3JlcXVlc3RBbmltYXRpb25GcmFtZShsb29wKX1sb29wKCk7CnZhciBzdD1k"
    "b2N1bWVudC5nZXRFbGVtZW50QnlJZCgic3RhZ2UiKTsKc3QuYWRkRXZlbnRMaXN0ZW5lcigicG9pbnRlcmRvd24iLGZ1bmN0aW9u"
    "KGUpe2RyYWc9ZS5jbGllbnRYO2xhc3RYPWUuY2xpZW50WH0pOwphZGRFdmVudExpc3RlbmVyKCJwb2ludGVybW92ZSIsZnVuY3Rp"
    "b24oZSl7aWYoZHJhZyE9PW51bGwpe3ZhciBkeD1lLmNsaWVudFgtbGFzdFg7YW5nbGUrPWR4Ki40O3ZlbD1keCouNDtsYXN0WD1l"
    "LmNsaWVudFh9fSk7CmFkZEV2ZW50TGlzdGVuZXIoInBvaW50ZXJ1cCIsZnVuY3Rpb24oKXtkcmFnPW51bGx9KTsKd2luZG93LmFk"
    "ZFZpZGVvPWZ1bmN0aW9uKCl7dmFyIHU9cHJvbXB0KCJQYXN0ZSBhIFlvdVR1YmUgbGluayBhYm91dCBBSSBnb3Zlcm5hbmNlOiIp"
    "O2lmKCF1KXJldHVybjsKIHZhciBtPXUubWF0Y2goLyg/OnY9fHlvdXR1XC5iZVwvfGVtYmVkXC98c2hvcnRzXC8pKFtBLVphLXow"
    "LTlfLV17MTF9KS8pO2lmKCFtKXthbGVydCgiVGhhdCBkb2Vzbid0IGxvb2sgbGlrZSBhIFlvdVR1YmUgbGluay4iKTtyZXR1cm59"
    "CiB2YXIgdD1wcm9tcHQoIlRpdGxlIGZvciB0aGlzIHNjcmVlbjoiLCJOZXcgY2hhbm5lbCIpfHwiTmV3IGNoYW5uZWwiLG5jPXBy"
    "b21wdCgiQ2hhbm5lbCBuYW1lOiIsIllvdXIgY2hhbm5lbCIpfHwiWW91ciBjaGFubmVsIjsKIHZhciB2PXtpZDptWzFdLHRpdGxl"
    "OnQuc2xpY2UoMCw2MCksY2hhbm5lbDpuYy5zbGljZSgwLDMwKX07Q0hBTk5FTFMucHVzaCh2KTsKIHRyeXt2YXIgcz1KU09OLnBh"
    "cnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKCJzZWJiaS5jaW5lbWEiKXx8IltdIik7cy5wdXNoKHYpO2xvY2FsU3RvcmFnZS5zZXRJ"
    "dGVtKCJzZWJiaS5jaW5lbWEiLEpTT04uc3RyaW5naWZ5KHMuc2xpY2UoLTIwKSkpfWNhdGNoKGUpe30KIGN1cj1DSEFOTkVMUy5s"
    "ZW5ndGgtMTtyZWVsPU1hdGguZmxvb3IoY3VyL1BFUik7YnVpbGQoKX07CmZ1bmN0aW9uIHR2KCl7dmFyIGM9Q0hBTk5FTFNbY3Vy"
    "XSx0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0diIpOwogaWYoc3Bpbm5pbmcpe3NwaW5uaW5nPWZhbHNlO3QuY2xhc3NMaXN0"
    "LnJlbW92ZSgic3BpbiIpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzcGluQnRuIikudGV4dENvbnRlbnQ9IlNwaW4gdGhlIFRW"
    "In0KIHQuY2xhc3NMaXN0LnJlbW92ZSgiaWRsZSIpOwogdC5pbm5lckhUTUw9JzxpZnJhbWUgc3JjPSJodHRwczovL3d3dy55b3V0"
    "dWJlLmNvbS9lbWJlZC8nK2VuY29kZVVSSUNvbXBvbmVudChjLmlkKSsnP2F1dG9wbGF5PTEmbXV0ZT0xJnJlbD0wJnBsYXlzaW5s"
    "aW5lPTEmbW9kZXN0YnJhbmRpbmc9MSIgcmVmZXJyZXJwb2xpY3k9InN0cmljdC1vcmlnaW4td2hlbi1jcm9zcy1vcmlnaW4iIGFs"
    "bG93PSJhY2NlbGVyb21ldGVyOyBhdXRvcGxheTsgY2xpcGJvYXJkLXdyaXRlOyBlbmNyeXB0ZWQtbWVkaWE7IGd5cm9zY29wZTsg"
    "cGljdHVyZS1pbi1waWN0dXJlOyB3ZWItc2hhcmU7IGZ1bGxzY3JlZW4iIGFsbG93ZnVsbHNjcmVlbiB0aXRsZT0iJytlc2MoYy50"
    "aXRsZSkrJyI+PC9pZnJhbWU+JzsKIHZhciBhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0dmxpbmsiKTthLmhyZWY9Imh0dHBz"
    "Oi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9IitlbmNvZGVVUklDb21wb25lbnQoYy5pZCk7YS50ZXh0Q29udGVudD0iUGxheWlu"
    "ZyBtdXRlZCDCtyB0YXAgdGhlIHZpZGVvIHRvIHVubXV0ZSDCtyBvciB3YXRjaCBvbiBZb3VUdWJlIOKGlyI7CiBkb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgicm9vbU5vdyIpLnRleHRDb250ZW50PSJOT1cgU0hPV0lORyDCtyBDSCAiKyhjdXIrMSkrIiDCtyAiK2Mu"
    "Y2hhbm5lbCsiIMK3ICIrYy50aXRsZTtjaGFucygpO3Zpc29yKCl9CmZ1bmN0aW9uIGNoYW5zKCl7ZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoImNoYW5zIikuaW5uZXJIVE1MPUNIQU5ORUxTLm1hcChmdW5jdGlvbihjLGkpe3JldHVybiAnPGJ1dHRvbiBjbGFzcz0i"
    "JysoaT09PWN1cj8ib24iOiIiKSsnIiBkYXRhLWk9IicraSsnIj5DSCAnKyhpKzEpKycgwrcgJytlc2MoYy5jaGFubmVsKSsnPC9i"
    "dXR0b24+J30pLmpvaW4oIiIpOwogQXJyYXkucHJvdG90eXBlLmZvckVhY2guY2FsbChkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxs"
    "KCIjY2hhbnMgYnV0dG9uIiksZnVuY3Rpb24oYil7Yi5vbmNsaWNrPWZ1bmN0aW9uKCl7Y3VyPStiLmRhdGFzZXQuaTtyZWVsPU1h"
    "dGguZmxvb3IoY3VyL1BFUik7dHYoKTtidWlsZCgpfX0pfQp3aW5kb3cuZW50ZXI9ZnVuY3Rpb24oKXtkb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgibG9iYnkiKS5jbGFzc0xpc3QuYWRkKCJoaWRkZW4iKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicm9vbSIpLmNs"
    "YXNzTGlzdC5yZW1vdmUoImhpZGRlbiIpO3R2KCl9Owp3aW5kb3cubGVhdmU9ZnVuY3Rpb24oKXtkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgidHYiKS5pbm5lckhUTUw9IiI7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJvb20iKS5jbGFzc0xpc3QuYWRkKCJoaWRk"
    "ZW4iKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibG9iYnkiKS5jbGFzc0xpc3QucmVtb3ZlKCJoaWRkZW4iKTttYXJrKCl9Owp3"
    "aW5kb3cuc3RlcD1mdW5jdGlvbihkKXtjdXI9KGN1citkK0NIQU5ORUxTLmxlbmd0aCklQ0hBTk5FTFMubGVuZ3RoO3JlZWw9TWF0"
    "aC5mbG9vcihjdXIvUEVSKTt0digpO2J1aWxkKCl9Owp3aW5kb3cudG9nZ2xlU3Bpbj1mdW5jdGlvbigpe3ZhciB0PWRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJ0diIpO3NwaW5uaW5nPSFzcGlubmluZzsKIGlmKHNwaW5uaW5nKXt0LmlubmVySFRNTD0nPGltZyBh"
    "bHQ9IiIgc3R5bGU9IndpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb3Zlcjtib3JkZXItcmFkaXVzOjRweCIgc3Jj"
    "PSJodHRwczovL2ltZy55b3V0dWJlLmNvbS92aS8nK2VuY29kZVVSSUNvbXBvbmVudChDSEFOTkVMU1tjdXJdLmlkKSsnL2hxZGVm"
    "YXVsdC5qcGciPic7dC5jbGFzc0xpc3QuYWRkKCJzcGluIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInR2bGluayIpLnRleHRD"
    "b250ZW50PSJUaGUgVFYgaXMgc3Bpbm5pbmcgwrcgdGFwIFN0b3Agc3Bpbm5pbmcgdG8gd2F0Y2gifQogZWxzZXt0LmNsYXNzTGlz"
    "dC5yZW1vdmUoInNwaW4iKTt0digpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNwaW5CdG4iKS50ZXh0Q29udGVudD1zcGlu"
    "bmluZz8iU3RvcCBzcGlubmluZyI6IlNwaW4gdGhlIFRWIn07CmJ1aWxkKCk7CmZldGNoKCcveC9jaW5lbWFmZWVkL2xpc3QnLHtj"
    "YWNoZTonbm8tc3RvcmUnfSkudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpe2lmKGQm"
    "JmQudmlkZW9zJiZkLnZpZGVvcy5sZW5ndGgpe3ZhciBleHRyYT1bXTt0cnl7ZXh0cmE9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2Uu"
    "Z2V0SXRlbSgnc2ViYmkuY2luZW1hJyl8fCdbXScpfWNhdGNoKGUpe31DSEFOTkVMUz1kLnZpZGVvcy5jb25jYXQoQXJyYXkuaXNB"
    "cnJheShleHRyYSk/ZXh0cmE6W10pO3JlZWw9MDtjdXI9MDtidWlsZCgpfX0pLmNhdGNoKGZ1bmN0aW9uKCl7fSk7Cn0pKCk7Cjwv"
    "c2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/cinema": (_d(_HTML_B64), "text/html; charset=utf-8"),
}
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_cinema_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._cinema_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "cinema", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/cinemafeed.py`

80 lines, 4430 bytes

```python
"""
modules/cinemafeed.py  v1.0.0
The video feed for the sebbi.pro Cinema (/cinema).

    GET /x/cinemafeed/list     every video, grouped by channel   (public)
    GET /x/cinemafeed/status   count and channels                (public)

To add or remove a video, edit the VIDEOS list below: one line per video,
(YouTube id, title, channel). The id is the 11 characters after "v=" in a
YouTube link. Nothing else needs changing; the cinema page reads this feed.
"""

VERSION = "1.0.0"
PUBLIC = {("GET", "list"), ("GET", "status"), ("GET", "spec")}

VIDEOS = [
    # NVIDIA and IBM
    ("gM1dLdpDR50", "What Is Trustworthy AI?", "NVIDIA"),
    ("f6dx3Yh-Tww", "What is AI governance?", "IBM Research"),
    ("Q020C-Jw0o8", "The Importance of AI Governance", "IBM Technology"),
    ("0oeD2Wf25wY", "Mastering AI Risk: NIST's Framework Explained", "IBM Technology"),
    # EU AI Act
    ("ya5uBFs41Ug", "EU's AI Act explained for everyone", "EU AI Act"),
    ("oWHCyLfUgUw", "EU AI Act Explained: Everything You Must Know", "EU AI Act"),
    ("s_rxOnCt3HQ", "The EU's AI Act Explained", "EU AI Act"),
    ("xUHuR5qXbMY", "EU AI Act explained for your business", "EU AI Act"),
    ("1Z6NA7Chkn4", "The EU AI Act explained in the time of a coffee", "EU AI Act"),
    ("GELAXU9XReI", "Understanding the EU AI Act: key facts", "EU AI Act"),
    ("lwJXCPsBJfc", "The EU AI Act: what it means for AI and DevOps", "EU AI Act"),
    ("4A33y0B9V0k", "The EU AI Act: what you need to know", "EU AI Act"),
    # AI safety
    ("qe9QSCF-d88", "The Catastrophic Risks of AI and a Safer Path", "Yoshua Bengio · TED"),
    ("dc3R_G5DJ50", "Yoshua Bengio's warning on AI safety", "Yoshua Bengio"),
    ("95xpd9FadVk", "We need AI systems to be 10 million times safer", "Stuart Russell"),
    ("qrvK_KuIeJk", "Godfather of AI: the 60 Minutes interview", "Geoffrey Hinton"),
    ("AUGHMx7iAxk", "AI safety risks and the future of AI", "Geoffrey Hinton"),
    ("eHSn50wnBRQ", "Hinton warns about the future of AI", "Geoffrey Hinton"),
    ("5qBDQgfeB6s", "AI has progressed even faster than I thought", "Geoffrey Hinton"),
    ("giT0ytynSqg", "Godfather of AI: trying to warn them", "Geoffrey Hinton"),
    ("hrnQ7chut7A", "Mapping the catastrophic risks of AI", "AI Safety"),
    # Microsoft responsible AI
    ("poMZXS6iQeU", "Responsible AI: Microsoft's AI principles", "Microsoft"),
    ("8Ra5L1aQ5YM", "Responsible AI Principles, episode 3", "Microsoft"),
    ("dnC8-uUZXSc", "Our approach to responsible AI", "Microsoft"),
    ("lkIlsgrIMtU", "Developing Microsoft's Responsible AI Standard", "Microsoft"),
    ("7Mv9VZEDBC4", "How Microsoft drives responsible AI", "Microsoft"),
    ("XWpXxUc-GJY", "Responsible AI in action: principles to engineering", "Microsoft"),
    # NIST AI RMF
    ("CkplyRCYuco", "NIST AI Risk Management Framework explained simply", "NIST AI RMF"),
    ("y3foG0ALLVc", "NIST AI Risk Management Framework explained", "NIST AI RMF"),
    ("3B0ELJTViMs", "NIST AI RMF: a practical guide", "NIST AI RMF"),
    ("7xcM_edGNyE", "NIST AI RMF: the full guide", "NIST AI RMF"),
    ("rbFt34UmngY", "The NIST AI Risk Management Framework", "NIST AI RMF"),
    ("Ufr3aklALVo", "AI risk management explained", "NIST AI RMF"),
    # Agentic AI
    ("mJjTLRQtJdo", "Agent risk, security and AI sprawl in 2026", "Agentic AI"),
    ("YtgQ0q53GV4", "Agentic AI will redefine risk", "Agentic AI"),
    # ISO 42001
    ("YdPyeVvYtzs", "ISO/IEC 42001:2023 explained", "ISO 42001"),
    ("0BXySa973Q4", "ISO 42001 explained in 5 minutes", "ISO 42001"),
    ("FAQhV3iG6Fg", "Navigating the ISO 42001 standard", "ISO 42001"),
    ("O4iKEr5AIi4", "What is ISO/IEC 42001?", "ISO 42001"),
    ("hSz71vISZMA", "What is the AI management system standard?", "ISO 42001"),
    ("yxE3bCP3aTg", "ISO 42001: simple explanation with examples", "ISO 42001"),
    ("jhQRtCO_5n0", "ISO/IEC 42001 AI governance bootcamp", "ISO 42001"),
]


def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()
    vids = [{"id": i, "title": t, "channel": c} for i, t, c in VIDEOS]
    if action == "list":
        return {"count": len(vids), "videos": vids}, 200
    chans = []
    for v in vids:
        if v["channel"] not in chans:
            chans.append(v["channel"])
    return {"module": "cinemafeed", "version": VERSION, "count": len(vids),
            "channels": chans, "list": "https://sebbi.pro/x/cinemafeed/list"}, 200

```
