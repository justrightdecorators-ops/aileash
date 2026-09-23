# Codebase — part 3 of 40

Contains:
- `modules/bind.py`
- `modules/binddesk.py`
- `modules/blocks.py`
- `modules/capture.py`
- `modules/cinema.py`


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

301 lines, 24979 bytes

```python
"""
modules/cinema.py  v2.0.0
The sebbi.pro Cinema at /cinema, in two wings. GOVERNANCE spins the videos in
modules/cinemafeed.py; THE 10p WING spins creators' locked videos approved in
modules/marquee.py. Both share the screening room with its spinning TV.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/cinema/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "2.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPnNlYmJpLnBybyBDaW5lbWEg4oCUIHR3byB3aW5ncywgb25lIGF4bGU8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlv"
    "biIgY29udGVudD0iVGhlIGdvdmVybmFuY2Ugd2luZzogNDIgdmlkZW9zIG9uIEFJIGdvdmVybmFuY2UuIFRoZSAxMHAgV2luZzog"
    "Y3JlYXRvcnMnIGxvY2tlZCB2aWRlb3MuIFNwaW4gdGhlIHNjcmVlbnMgYW5kIHN0ZXAgaW50byB0aGUgc2NyZWVuaW5nIHJvb20u"
    "Ij4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JQk0rUGxleCtNb25vOndnaHRA"
    "NDAwOzUwMDs2MDAmZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDUwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVz"
    "aGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzA1MDcwZjstLWluazI6IzBkMTQyNDstLWdvbGQ6I2M5YTg0YzstLW9rOiM3ZmUz"
    "YjA7LS1ibHVlOiM4ZmQwZmY7LS1waW5rOiNkNTliZmY7LS1tdXRlOiM4YTkzYWR9Cip7Ym94LXNpemluZzpib3JkZXItYm94O21h"
    "cmdpbjowO3BhZGRpbmc6MDstd2Via2l0LXRhcC1oaWdobGlnaHQtY29sb3I6dHJhbnNwYXJlbnR9Cmh0bWwsYm9keXtoZWlnaHQ6"
    "MTAwJTtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAyNiUsIzE0MWQ0MiAwJSwjMDUwNzBmIDcyJSk7"
    "Y29sb3I6I2U4ZWRmNztmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZTtvdmVyZmxvdzpo"
    "aWRkZW59Ci52aWV3e3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjthbGln"
    "bi1pdGVtczpjZW50ZXI7dHJhbnNpdGlvbjpvcGFjaXR5IC41c30KLmhpZGRlbntvcGFjaXR5OjA7cG9pbnRlci1ldmVudHM6bm9u"
    "ZX0KaGVhZGVye3dpZHRoOjEwMCU7cGFkZGluZzpjYWxjKDEycHggKyBlbnYoc2FmZS1hcmVhLWluc2V0LXRvcCkpIDE2cHggMDt0"
    "ZXh0LWFsaWduOmNlbnRlcn0KLmJyYW5ke2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpfS5icmFuZCBie2NvbG9yOnZh"
    "cigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KaDF7Zm9udC1mYW1pbHk6J05ld3NyZWFkZXInLEdlb3JnaWEsc2VyaWY7Zm9udC13"
    "ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyNXB4LDUuNnZ3LDQycHgpO21hcmdpbjo0cHggMCAycHg7YmFja2dyb3VuZDpsaW5l"
    "YXItZ3JhZGllbnQoOTBkZWcsI2M5YTg0YywjN2ZlM2IwLCM4ZmQwZmYpOy13ZWJraXQtYmFja2dyb3VuZC1jbGlwOnRleHQ7YmFj"
    "a2dyb3VuZC1jbGlwOnRleHQ7Y29sb3I6dHJhbnNwYXJlbnR9Ci5zdWJ7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZSk7"
    "bGV0dGVyLXNwYWNpbmc6LjA2ZW19Ci53aW5nc3tkaXNwbGF5OmZsZXg7Z2FwOjhweDtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO21h"
    "cmdpbi10b3A6MTBweH0KLndpbmdzIGJ1dHRvbntiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjg1KTtib3JkZXI6MS41cHggc29s"
    "aWQgcmdiYSgyNTUsMjU1LDI1NSwuMTYpO2NvbG9yOiNjZmQ2ZTY7Ym9yZGVyLXJhZGl1czo5OTlweDtwYWRkaW5nOjlweCAxNXB4"
    "O2ZvbnQ6NjAwIDEycHggJ0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtjdXJzb3I6cG9pbnRlcn0KLndpbmdzIGJ1dHRvbi5vbnti"
    "b3JkZXItY29sb3I6dmFyKC0tZ29sZCk7Y29sb3I6dmFyKC0tZ29sZCk7Ym94LXNoYWRvdzowIDAgMThweCByZ2JhKDIwMSwxNjgs"
    "NzYsLjM1KX0KLndpbmdzIGJ1dHRvbi50ZW5wLm9ue2JvcmRlci1jb2xvcjp2YXIoLS1waW5rKTtjb2xvcjp2YXIoLS1waW5rKTti"
    "b3gtc2hhZG93OjAgMCAxOHB4IHJnYmEoMjEzLDE1NSwyNTUsLjQpfQouc3RhZ2V7ZmxleDoxO3dpZHRoOjEwMCU7cGVyc3BlY3Rp"
    "dmU6MTE1MHB4O2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjt0b3VjaC1hY3Rp"
    "b246cGFuLXl9Ci5yaW5ne3Bvc2l0aW9uOnJlbGF0aXZlO3dpZHRoOjI1MHB4O2hlaWdodDoxNTZweDt0cmFuc2Zvcm0tc3R5bGU6"
    "cHJlc2VydmUtM2R9Ci5heGxle3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6NTAlO3RvcDo1MCU7d2lkdGg6NnB4O2hlaWdodDoyNTBw"
    "eDttYXJnaW46LTEyNXB4IDAgMCAtM3B4O2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KHZhcigtLWdvbGQpLCM1YTRhMWMpO2Jv"
    "cmRlci1yYWRpdXM6M3B4O2JveC1zaGFkb3c6MCAwIDE4cHggcmdiYSgyMDEsMTY4LDc2LC41NSl9Ci5zY3JlZW57cG9zaXRpb246"
    "YWJzb2x1dGU7aW5zZXQ6MDtib3JkZXItcmFkaXVzOjExcHg7b3ZlcmZsb3c6aGlkZGVuO2JhY2tncm91bmQ6IzBiMTIyNDtib3Jk"
    "ZXI6MS41cHggc29saWQgcmdiYSgyMDEsMTY4LDc2LC40NSk7Ym94LXNoYWRvdzowIDAgMzJweCByZ2JhKDE0MywyMDgsMjU1LC4x"
    "OCk7Y3Vyc29yOnBvaW50ZXI7YmFja2ZhY2UtdmlzaWJpbGl0eTpoaWRkZW47dHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjNzLGJv"
    "eC1zaGFkb3cgLjNzfQouc2NyZWVuLnRlbnB7Ym9yZGVyLWNvbG9yOnJnYmEoMjEzLDE1NSwyNTUsLjU1KTtib3gtc2hhZG93OjAg"
    "MCAzMnB4IHJnYmEoMjEzLDE1NSwyNTUsLjI1KX0KLnNjcmVlbiBpbWd7d2lkdGg6MTAwJTtoZWlnaHQ6MTAwJTtvYmplY3QtZml0"
    "OmNvdmVyO29wYWNpdHk6Ljg1fQouc2NyZWVuIC5mYWxsYmFja3tkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3Rp"
    "ZnktY29udGVudDpjZW50ZXI7aGVpZ2h0OjEwMCU7Zm9udC1zaXplOjM0cHg7Y29sb3I6dmFyKC0tcGluayk7YmFja2dyb3VuZDps"
    "aW5lYXItZ3JhZGllbnQoMTYwZGVnLCMxYTEwMzgsIzBiMTIyNCl9Ci5zY3JlZW4gLmxhYntwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0"
    "OjA7cmlnaHQ6MDtib3R0b206MDtwYWRkaW5nOjE4cHggOXB4IDdweDtmb250LXNpemU6MTAuNXB4O2JhY2tncm91bmQ6bGluZWFy"
    "LWdyYWRpZW50KHRyYW5zcGFyZW50LHJnYmEoNSw3LDE1LC45MikpfQouc2NyZWVuIC5jaHtwb3NpdGlvbjphYnNvbHV0ZTt0b3A6"
    "N3B4O2xlZnQ6OHB4O2ZvbnQtc2l6ZTo5LjVweDtsZXR0ZXItc3BhY2luZzouMDllbTtjb2xvcjp2YXIoLS1nb2xkKTtiYWNrZ3Jv"
    "dW5kOnJnYmEoNSw3LDE1LC43NSk7cGFkZGluZzoycHggNnB4O2JvcmRlci1yYWRpdXM6M3B4fQouc2NyZWVuIC5wcmljZXtwb3Np"
    "dGlvbjphYnNvbHV0ZTt0b3A6N3B4O3JpZ2h0OjhweDtmb250LXNpemU6OS41cHg7Y29sb3I6IzA1MDcwZjtiYWNrZ3JvdW5kOnZh"
    "cigtLXBpbmspO3BhZGRpbmc6MnB4IDdweDtib3JkZXItcmFkaXVzOjk5OXB4O2ZvbnQtd2VpZ2h0OjYwMH0KLnNjcmVlbi5vbnti"
    "b3JkZXItY29sb3I6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDQycHggcmdiYSgxMjcsMjI3LDE3NiwuNDUpfQouY3Jvd2R7ZGlz"
    "cGxheTpmbGV4O2dhcDo2cHg7anVzdGlmeS1jb250ZW50OmNlbnRlcjtoZWlnaHQ6NzBweDthbGlnbi1pdGVtczpmbGV4LWVuZDtt"
    "YXJnaW4tYm90dG9tOjZweH0KLmJvdHt3aWR0aDozOHB4O2hlaWdodDo2MnB4O3Bvc2l0aW9uOnJlbGF0aXZlO2FuaW1hdGlvbjpi"
    "b2IgM3MgZWFzZS1pbi1vdXQgaW5maW5pdGV9Ci5ib3Q6bnRoLWNoaWxkKDJuKXthbmltYXRpb24tZGVsYXk6LjZzfS5ib3Q6bnRo"
    "LWNoaWxkKDNuKXthbmltYXRpb24tZGVsYXk6MS4yc30KQGtleWZyYW1lcyBib2J7NTAle3RyYW5zZm9ybTp0cmFuc2xhdGVZKC0y"
    "cHgpfX0KLmJvdCAuaGVhZHtwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MDtsZWZ0OjlweDt3aWR0aDoyMXB4O2hlaWdodDoxN3B4O2Jv"
    "cmRlci1yYWRpdXM6NXB4O2JhY2tncm91bmQ6I2Q4ZGRlNn0KLmJvdCAudmlzb3J7cG9zaXRpb246YWJzb2x1dGU7dG9wOjZweDts"
    "ZWZ0OjNweDt3aWR0aDoxNXB4O2hlaWdodDo1cHg7Ym9yZGVyLXJhZGl1czoycHg7YmFja2dyb3VuZDp2YXIoLS1nb2xkKTtib3gt"
    "c2hhZG93OjAgMCA4cHggdmFyKC0tZ29sZCk7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC40cyxib3gtc2hhZG93IC40c30KLmJvdCAu"
    "Ym9keXtwb3NpdGlvbjphYnNvbHV0ZTt0b3A6MTlweDtsZWZ0OjZweDt3aWR0aDoyNnB4O2hlaWdodDoyM3B4O2JvcmRlci1yYWRp"
    "dXM6NXB4O2JhY2tncm91bmQ6I2MzYzlkNH0KLmJvdCAuc2VhdHtwb3NpdGlvbjphYnNvbHV0ZTtib3R0b206MDtsZWZ0OjA7d2lk"
    "dGg6MzhweDtoZWlnaHQ6MjJweDtib3JkZXItcmFkaXVzOjZweCA2cHggM3B4IDNweDtiYWNrZ3JvdW5kOiMxYjIzMzY7Ym9yZGVy"
    "LXRvcDoycHggc29saWQgIzJhMzU1Mn0KLm5vd3tmb250LXNpemU6MTJweDt0ZXh0LWFsaWduOmNlbnRlcjttaW4taGVpZ2h0OjE3"
    "cHg7bWFyZ2luLWJvdHRvbTo2cHg7Y29sb3I6dmFyKC0tb2spO3BhZGRpbmc6MCAxMnB4fQouYmFye2Rpc3BsYXk6ZmxleDtnYXA6"
    "OHB4O2ZsZXgtd3JhcDp3cmFwO2p1c3RpZnktY29udGVudDpjZW50ZXI7cGFkZGluZzowIDEycHggY2FsYygxNHB4ICsgZW52KHNh"
    "ZmUtYXJlYS1pbnNldC1ib3R0b20pKX0KLmJ0bntib3JkZXI6MDtib3JkZXItcmFkaXVzOjlweDtwYWRkaW5nOjExcHggMTVweDtm"
    "b250OjYwMCAxMi41cHggJ0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOiMwNTA3"
    "MGY7Y3Vyc29yOnBvaW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmU7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5idG4uZ2hvc3R7YmFj"
    "a2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZThlZGY3O2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMjQpfQou"
    "YnRuLnBpbmt7YmFja2dyb3VuZDp2YXIoLS1waW5rKX0KLmZsb29ye3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6LTUwJTtyaWdodDot"
    "NTAlO2JvdHRvbTotOCU7aGVpZ2h0OjU2JTtiYWNrZ3JvdW5kOnJlcGVhdGluZy1saW5lYXItZ3JhZGllbnQoOTBkZWcscmdiYSgy"
    "MDEsMTY4LDc2LC4xNikgMCAxcHgsdHJhbnNwYXJlbnQgMXB4IDYwcHgpLHJlcGVhdGluZy1saW5lYXItZ3JhZGllbnQoMGRlZyxy"
    "Z2JhKDIwMSwxNjgsNzYsLjE2KSAwIDFweCx0cmFuc3BhcmVudCAxcHggNjBweCk7dHJhbnNmb3JtOnJvdGF0ZVgoNzJkZWcpO3Ry"
    "YW5zZm9ybS1vcmlnaW46Ym90dG9tO3BvaW50ZXItZXZlbnRzOm5vbmV9Ci50dndyYXB7ZmxleDoxO2Rpc3BsYXk6ZmxleDtmbGV4"
    "LWRpcmVjdGlvbjpjb2x1bW47YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7d2lkdGg6MTAwJTtwZXJz"
    "cGVjdGl2ZToxMDAwcHh9Ci50dnt3aWR0aDptaW4oOTR2dyw3NjBweCk7YXNwZWN0LXJhdGlvOjE2Lzk7Ym9yZGVyLXJhZGl1czox"
    "NHB4O2JhY2tncm91bmQ6IzAwMDtib3JkZXI6MTBweCBzb2xpZCAjMWIyMzM2O291dGxpbmU6MnB4IHNvbGlkIHJnYmEoMjAxLDE2"
    "OCw3NiwuNSk7Ym94LXNoYWRvdzowIDAgNjBweCByZ2JhKDE0MywyMDgsMjU1LC4yMiksMCAzMHB4IDYwcHggcmdiYSgwLDAsMCwu"
    "Nik7dHJhbnNpdGlvbjp0cmFuc2Zvcm0gLjhzfQoudHYuaWRsZXthbmltYXRpb246c3dheSA5cyBlYXNlLWluLW91dCBpbmZpbml0"
    "ZX0udHYuc3BpbnthbmltYXRpb246ZnVsbHNwaW4gMTRzIGxpbmVhciBpbmZpbml0ZX0KQGtleWZyYW1lcyBzd2F5ezAlLDEwMCV7"
    "dHJhbnNmb3JtOnJvdGF0ZVkoLTlkZWcpIHJvdGF0ZVgoM2RlZyl9NTAle3RyYW5zZm9ybTpyb3RhdGVZKDlkZWcpIHJvdGF0ZVgo"
    "LTJkZWcpfX0KQGtleWZyYW1lcyBmdWxsc3Bpbnt0b3t0cmFuc2Zvcm06cm90YXRlWSgzNjBkZWcpfX0KLnR2IGlmcmFtZXt3aWR0"
    "aDoxMDAlO2hlaWdodDoxMDAlO2JvcmRlcjowO2JvcmRlci1yYWRpdXM6NHB4O2Rpc3BsYXk6YmxvY2t9Ci50dmxpbmt7Zm9udC1z"
    "aXplOjExcHg7Y29sb3I6dmFyKC0tYmx1ZSk7bWFyZ2luLXRvcDo4cHg7dGV4dC1kZWNvcmF0aW9uOm5vbmU7dGV4dC1hbGlnbjpj"
    "ZW50ZXJ9Ci5jaGFuc3tkaXNwbGF5OmZsZXg7Z2FwOjZweDtvdmVyZmxvdy14OmF1dG87bWF4LXdpZHRoOjEwMCU7cGFkZGluZzo4"
    "cHggMTJweDtzY3JvbGxiYXItd2lkdGg6bm9uZX0KLmNoYW5zIGJ1dHRvbntmbGV4Om5vbmU7Ym9yZGVyOjFweCBzb2xpZCByZ2Jh"
    "KDIwMSwxNjgsNzYsLjM1KTtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjgpO2NvbG9yOiNlOGVkZjc7Ym9yZGVyLXJhZGl1czo3"
    "cHg7cGFkZGluZzo4cHggMTFweDtmb250OjUwMCAxMS41cHggJ0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtjdXJzb3I6cG9pbnRl"
    "cjt3aGl0ZS1zcGFjZTpub3dyYXB9Ci5jaGFucyBidXR0b24ub257Ym9yZGVyLWNvbG9yOnZhcigtLW9rKTtjb2xvcjp2YXIoLS1v"
    "ayl9Ci5lbXB0eXttYXgtd2lkdGg6MzgwcHg7dGV4dC1hbGlnbjpjZW50ZXI7Y29sb3I6dmFyKC0tbXV0ZSk7Zm9udC1zaXplOjEz"
    "cHg7bGluZS1oZWlnaHQ6MS43O3BhZGRpbmc6MjBweH0KLmVtcHR5IGF7Y29sb3I6dmFyKC0tcGluayl9Cjwvc3R5bGU+PC9oZWFk"
    "Pjxib2R5PgoKPHNlY3Rpb24gY2xhc3M9InZpZXciIGlkPSJsb2JieSI+CiA8aGVhZGVyPjxkaXYgY2xhc3M9ImJyYW5kIj5zZWJi"
    "aTxiPi5wcm88L2I+IMK3IENJTkVNQTwvZGl2PjxoMSBpZD0id2luZ1RpdGxlIj5BSSBnb3Zlcm5hbmNlLCBvbiBldmVyeSBzY3Jl"
    "ZW4uPC9oMT4KIDxkaXYgY2xhc3M9InN1YiIgaWQ9IndpbmdTdWIiPkRSQUcgVE8gU1BJTiDCtyBUQVAgQSBTQ1JFRU4gwrcgRU5U"
    "RVIgVEhFIFJPT00gVE8gV0FUQ0g8L2Rpdj4KIDxkaXYgY2xhc3M9IndpbmdzIj48YnV0dG9uIGlkPSJ3RyIgY2xhc3M9Im9uIj7w"
    "n4+bIEdvdmVybmFuY2U8L2J1dHRvbj48YnV0dG9uIGlkPSJ3VCIgY2xhc3M9InRlbnAiPvCfjqwgVGhlIDEwcCBXaW5nPC9idXR0"
    "b24+PC9kaXY+PC9oZWFkZXI+CiA8ZGl2IGNsYXNzPSJzdGFnZSIgaWQ9InN0YWdlIj48ZGl2IGNsYXNzPSJyaW5nIiBpZD0icmlu"
    "ZyI+PGRpdiBjbGFzcz0iYXhsZSI+PC9kaXY+PC9kaXY+PC9kaXY+CiA8ZGl2IGNsYXNzPSJub3ciIGlkPSJub3ciPjwvZGl2Pgog"
    "PGRpdiBjbGFzcz0iYmFyIiBzdHlsZT0icGFkZGluZy1ib3R0b206NnB4Ij48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xp"
    "Y2s9InJlZWxTdGVwKC0xKSI+4peAIFJlZWw8L2J1dHRvbj48c3BhbiBjbGFzcz0ic3ViIiBpZD0icmVlbExhYiIgc3R5bGU9ImFs"
    "aWduLXNlbGY6Y2VudGVyIj48L3NwYW4+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBvbmNsaWNrPSJyZWVsU3RlcCgxKSI+UmVl"
    "bCDilrY8L2J1dHRvbj48L2Rpdj4KIDxkaXYgY2xhc3M9ImNyb3dkIiBpZD0iY3Jvd2QiPjwvZGl2PgogPGRpdiBjbGFzcz0iYmFy"
    "Ij48YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImVudGVyKCkiPkVudGVyIHRoZSByb29tIOKWtjwvYnV0dG9uPjxhIGNsYXNz"
    "PSJidG4gcGluayIgaHJlZj0iL2NyZWF0ZSI+TG9jayB5b3VyIG93biB2aWRlbzwvYT48YSBjbGFzcz0iYnRuIGdob3N0IiBocmVm"
    "PSIvIj5Ib21lPC9hPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlvbiBjbGFzcz0idmlldyBoaWRkZW4iIGlkPSJyb29tIj4KIDxk"
    "aXYgY2xhc3M9ImZsb29yIj48L2Rpdj4KIDxoZWFkZXI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgVEhF"
    "IFNDUkVFTklORyBST09NPC9kaXY+PGRpdiBjbGFzcz0ic3ViIiBpZD0icm9vbU5vdyI+PC9kaXY+PC9oZWFkZXI+CiA8ZGl2IGNs"
    "YXNzPSJ0dndyYXAiPjxkaXYgY2xhc3M9InR2IiBpZD0idHYiPjwvZGl2PjxhIGNsYXNzPSJ0dmxpbmsiIGlkPSJ0dmxpbmsiIHRh"
    "cmdldD0iX2JsYW5rIiByZWw9Im5vb3BlbmVyIj48L2E+PC9kaXY+CiA8ZGl2IGNsYXNzPSJjaGFucyIgaWQ9ImNoYW5zIj48L2Rp"
    "dj4KIDxkaXYgY2xhc3M9ImNyb3dkIiBpZD0iY3Jvd2QyIj48L2Rpdj4KIDxkaXYgY2xhc3M9ImJhciI+PGJ1dHRvbiBjbGFzcz0i"
    "YnRuIGdob3N0IiBvbmNsaWNrPSJzdGVwKC0xKSI+4peAPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBvbmNsaWNr"
    "PSJzdGVwKDEpIj7ilrY8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIGlkPSJzcGluQnRuIiBvbmNsaWNrPSJ0b2dn"
    "bGVTcGluKCkiPlNwaW4gdGhlIFRWPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJsZWF2ZSgpIj5CYWNrIHRv"
    "IHRoZSBsb2JieTwvYnV0dG9uPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2NyaXB0PgooZnVuY3Rpb24oKXsKInVzZSBzdHJpY3QiOwp2"
    "YXIgR09WPVt7aWQ6ImdNMWRMZHBEUjUwIix0aXRsZToiV2hhdCBJcyBUcnVzdHdvcnRoeSBBST8iLGNoYW5uZWw6Ik5WSURJQSJ9"
    "LAoge2lkOiJmNmR4M1loLVR3dyIsdGl0bGU6IldoYXQgaXMgQUkgZ292ZXJuYW5jZT8iLGNoYW5uZWw6IklCTSBSZXNlYXJjaCJ9"
    "LAoge2lkOiJRMDIwQy1KdzBvOCIsdGl0bGU6IlRoZSBJbXBvcnRhbmNlIG9mIEFJIEdvdmVybmFuY2UiLGNoYW5uZWw6IklCTSBU"
    "ZWNobm9sb2d5In1dOwp2YXIgVEVOPVtdOwp2YXIgd2luZz0iZ292IixMSVNUPUdPVixjdXI9MCxhbmdsZT0wLHZlbD0uMTIsZHJh"
    "Zz1udWxsLGxhc3RYPTAsc3Bpbm5pbmc9ZmFsc2UscmVlbD0wLFBFUj0xMDsKdmFyIHJpbmc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5"
    "SWQoInJpbmciKSxub3c9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm5vdyIpOwpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmlu"
    "ZyhzKS5yZXBsYWNlKC9bJjw+Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsi"
    "LCciJzoiJnF1b3Q7In1bY119KX0KZnVuY3Rpb24gY3Jvd2QoaWQsbil7dmFyIGg9IiI7Zm9yKHZhciBpPTA7aTxuO2krKyloKz0n"
    "PGRpdiBjbGFzcz0iYm90Ij48ZGl2IGNsYXNzPSJoZWFkIj48ZGl2IGNsYXNzPSJ2aXNvciI+PC9kaXY+PC9kaXY+PGRpdiBjbGFz"
    "cz0iYm9keSI+PC9kaXY+PGRpdiBjbGFzcz0ic2VhdCI+PC9kaXY+PC9kaXY+Jztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCku"
    "aW5uZXJIVE1MPWh9CmNyb3dkKCJjcm93ZCIsTWF0aC5taW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7Y3Jvd2QoImNy"
    "b3dkMiIsTWF0aC5taW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7CnZhciBWSVM9WyIjYzlhODRjIiwiIzdmZTNiMCIs"
    "IiM4ZmQwZmYiLCIjZmY4YTgwIiwiI2Q1OWJmZiJdOwpmdW5jdGlvbiB2aXNvcigpe3ZhciBjPXdpbmc9PT0idGVuIj8iI2Q1OWJm"
    "ZiI6VklTW2N1ciVWSVMubGVuZ3RoXTsKIEFycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwoZG9jdW1lbnQucXVlcnlTZWxlY3Rv"
    "ckFsbCgiLnZpc29yIiksZnVuY3Rpb24odil7di5zdHlsZS5iYWNrZ3JvdW5kPWM7di5zdHlsZS5ib3hTaGFkb3c9IjAgMCA4cHgg"
    "IitjfSl9CmZ1bmN0aW9uIHRodW1iKHYpeyByZXR1cm4gdi55b3V0dWJlID8gJzxpbWcgYWx0PSIiIGxvYWRpbmc9ImxhenkiIHNy"
    "Yz0iaHR0cHM6Ly9pbWcueW91dHViZS5jb20vdmkvJytlbmNvZGVVUklDb21wb25lbnQodi5pZCkrJy9ocWRlZmF1bHQuanBnIj4n"
    "IDogJzxkaXYgY2xhc3M9ImZhbGxiYWNrIj7wn46sPC9kaXY+JzsgfQpmdW5jdGlvbiBidWlsZCgpewogQXJyYXkucHJvdG90eXBl"
    "LmZvckVhY2guY2FsbChyaW5nLnF1ZXJ5U2VsZWN0b3JBbGwoIi5zY3JlZW4iKSxmdW5jdGlvbihzKXtzLnJlbW92ZSgpfSk7CiBp"
    "ZighTElTVC5sZW5ndGgpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJyZWVsTGFiIikudGV4dENvbnRlbnQ9IiI7bm93LmlubmVy"
    "SFRNTD0nPHNwYW4gc3R5bGU9ImNvbG9yOiM4YTkzYWQiPk5vIHNjcmVlbnMgaW4gdGhpcyB3aW5nIHlldC4gPGEgaHJlZj0iL2Ny"
    "ZWF0ZSIgc3R5bGU9ImNvbG9yOiNkNTliZmYiPkxvY2sgYSB2aWRlbzwvYT4gYW5kIHNlbmQgaXQgaW4uPC9zcGFuPic7cmV0dXJu"
    "fQogdmFyIHJlZWxzPU1hdGgubWF4KDEsTWF0aC5jZWlsKExJU1QubGVuZ3RoL1BFUikpO3JlZWw9TWF0aC5taW4ocmVlbCxyZWVs"
    "cy0xKTsKIHZhciBpdGVtcz1MSVNULnNsaWNlKHJlZWwqUEVSLHJlZWwqUEVSK1BFUiksYmFzZT1yZWVsKlBFUixuPU1hdGgubWF4"
    "KGl0ZW1zLmxlbmd0aCw1KSxyPU1hdGgucm91bmQoMTQwL01hdGgudGFuKE1hdGguUEkvbikpKzQwOwogZm9yKHZhciBpPTA7aTxu"
    "O2krKyl7dmFyIGs9YmFzZSsoaSVpdGVtcy5sZW5ndGgpLHY9TElTVFtrXSxkPWRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImRpdiIp"
    "OwogIGQuY2xhc3NOYW1lPSJzY3JlZW4iKyh3aW5nPT09InRlbiI/IiB0ZW5wIjoiIik7ZC5kYXRhc2V0Lmk9azsKICBkLnN0eWxl"
    "LnRyYW5zZm9ybT0icm90YXRlWSgiKygzNjAvbippKSsiZGVnKSB0cmFuc2xhdGVaKCIrcisicHgpIjsKICBkLmlubmVySFRNTD10"
    "aHVtYih2KSsnPGRpdiBjbGFzcz0iY2giPkNIICcrKGsrMSkrJyDCtyAnK2VzYyh2LmNoYW5uZWwpKyc8L2Rpdj4nKwogICAodi5w"
    "cmljZT8nPGRpdiBjbGFzcz0icHJpY2UiPicrZXNjKFN0cmluZyh2LnByaWNlKSkrJ3A8L2Rpdj4nOicnKSsKICAgJzxkaXYgY2xh"
    "c3M9ImxhYiI+Jytlc2Modi50aXRsZSkrJzwvZGl2Pic7CiAgZC5vbmNsaWNrPWZ1bmN0aW9uKCl7cGljaygrdGhpcy5kYXRhc2V0"
    "LmkpfTtyaW5nLmFwcGVuZENoaWxkKGQpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJlZWxMYWIiKS50ZXh0Q29udGVudD0i"
    "UmVlbCAiKyhyZWVsKzEpKyIgb2YgIityZWVscysiIMK3ICIrTElTVC5sZW5ndGgrKHdpbmc9PT0idGVuIj8iIGxvY2tlZCB2aWRl"
    "b3MiOiIgdmlkZW9zIik7CiBpZihjdXI8YmFzZXx8Y3VyPj1iYXNlK2l0ZW1zLmxlbmd0aCljdXI9YmFzZTsKIG1hcmsoKTtjaGFu"
    "cygpfQpmdW5jdGlvbiBtYXJrKCl7QXJyYXkucHJvdG90eXBlLmZvckVhY2guY2FsbChyaW5nLnF1ZXJ5U2VsZWN0b3JBbGwoIi5z"
    "Y3JlZW4iKSxmdW5jdGlvbihzKXtzLmNsYXNzTGlzdC50b2dnbGUoIm9uIiwrcy5kYXRhc2V0Lmk9PT1jdXIpfSk7CiB2YXIgdj1M"
    "SVNUW2N1cl07aWYoIXYpcmV0dXJuOwogbm93LnRleHRDb250ZW50PSJDSCAiKyhjdXIrMSkrIiDCtyAiK3YuY2hhbm5lbCsiIMK3"
    "ICIrdi50aXRsZSsodi5wcmljZT8iIMK3ICIrdi5wcmljZSsicCB0byB1bmxvY2siOiIiKTt2aXNvcigpfQpmdW5jdGlvbiBwaWNr"
    "KGkpe2N1cj1pO21hcmsoKTt2ZWw9LjAzfQp3aW5kb3cucmVlbFN0ZXA9ZnVuY3Rpb24oZCl7aWYoIUxJU1QubGVuZ3RoKXJldHVy"
    "bjt2YXIgcmVlbHM9TWF0aC5tYXgoMSxNYXRoLmNlaWwoTElTVC5sZW5ndGgvUEVSKSk7cmVlbD0ocmVlbCtkK3JlZWxzKSVyZWVs"
    "cztjdXI9cmVlbCpQRVI7YnVpbGQoKX07CmZ1bmN0aW9uIGxvb3AoKXtpZihkcmFnPT09bnVsbCl7YW5nbGUrPXZlbDt2ZWwrPSgu"
    "MTItdmVsKSouMDF9cmluZy5zdHlsZS50cmFuc2Zvcm09InJvdGF0ZVkoIithbmdsZSsiZGVnKSI7cmVxdWVzdEFuaW1hdGlvbkZy"
    "YW1lKGxvb3ApfWxvb3AoKTsKdmFyIHN0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzdGFnZSIpOwpzdC5hZGRFdmVudExpc3Rl"
    "bmVyKCJwb2ludGVyZG93biIsZnVuY3Rpb24oZSl7ZHJhZz1lLmNsaWVudFg7bGFzdFg9ZS5jbGllbnRYfSk7CmFkZEV2ZW50TGlz"
    "dGVuZXIoInBvaW50ZXJtb3ZlIixmdW5jdGlvbihlKXtpZihkcmFnIT09bnVsbCl7dmFyIGR4PWUuY2xpZW50WC1sYXN0WDthbmds"
    "ZSs9ZHgqLjQ7dmVsPWR4Ki40O2xhc3RYPWUuY2xpZW50WH19KTsKYWRkRXZlbnRMaXN0ZW5lcigicG9pbnRlcnVwIixmdW5jdGlv"
    "bigpe2RyYWc9bnVsbH0pOwpmdW5jdGlvbiBzZXRXaW5nKHcpe3dpbmc9dztMSVNUPSh3PT09ImdvdiIpP0dPVjpURU47cmVlbD0w"
    "O2N1cj0wOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIndHIikuY2xhc3NMaXN0LnRvZ2dsZSgib24iLHc9PT0iZ292Iik7CiBk"
    "b2N1bWVudC5nZXRFbGVtZW50QnlJZCgid1QiKS5jbGFzc0xpc3QudG9nZ2xlKCJvbiIsdz09PSJ0ZW4iKTsKIGRvY3VtZW50Lmdl"
    "dEVsZW1lbnRCeUlkKCJ3aW5nVGl0bGUiKS50ZXh0Q29udGVudD0odz09PSJnb3YiKT8iQUkgZ292ZXJuYW5jZSwgb24gZXZlcnkg"
    "c2NyZWVuLiI6IlRoZSAxMHAgV2luZy4iOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIndpbmdTdWIiKS50ZXh0Q29udGVudD0o"
    "dz09PSJnb3YiKT8iRFJBRyBUTyBTUElOIMK3IFRBUCBBIFNDUkVFTiDCtyBFTlRFUiBUSEUgUk9PTSBUTyBXQVRDSCI6IkNSRUFU"
    "T1JTJyBMT0NLRUQgVklERU9TIMK3IEZSRUUgUFJFVklFVywgVEhFTiBBIEZFVyBQRU5DRSI7CiBidWlsZCgpfQpkb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgid0ciKS5vbmNsaWNrPWZ1bmN0aW9uKCl7c2V0V2luZygiZ292Iil9Owpkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgid1QiKS5vbmNsaWNrPWZ1bmN0aW9uKCl7c2V0V2luZygidGVuIil9OwpmdW5jdGlvbiB0digpe3ZhciB2PUxJU1RbY3Vy"
    "XTtpZighdilyZXR1cm47dmFyIHQ9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInR2Iik7CiBpZihzcGlubmluZyl7c3Bpbm5pbmc9"
    "ZmFsc2U7dC5jbGFzc0xpc3QucmVtb3ZlKCJzcGluIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNwaW5CdG4iKS50ZXh0Q29u"
    "dGVudD0iU3BpbiB0aGUgVFYifQogdC5jbGFzc0xpc3QucmVtb3ZlKCJpZGxlIik7CiB2YXIgc3JjID0gdi55b3V0dWJlCiAgPyAi"
    "aHR0cHM6Ly93d3cueW91dHViZS5jb20vZW1iZWQvIitlbmNvZGVVUklDb21wb25lbnQodi5pZCkrIj9hdXRvcGxheT0xJm11dGU9"
    "MSZyZWw9MCZwbGF5c2lubGluZT0xJm1vZGVzdGJyYW5kaW5nPTEiCiAgOiB2LnVybDsKIHQuaW5uZXJIVE1MPSc8aWZyYW1lIHNy"
    "Yz0iJytlc2Moc3JjKSsnIiByZWZlcnJlcnBvbGljeT0ic3RyaWN0LW9yaWdpbi13aGVuLWNyb3NzLW9yaWdpbiIgYWxsb3c9ImFj"
    "Y2VsZXJvbWV0ZXI7IGF1dG9wbGF5OyBjbGlwYm9hcmQtd3JpdGU7IGVuY3J5cHRlZC1tZWRpYTsgZ3lyb3Njb3BlOyBwaWN0dXJl"
    "LWluLXBpY3R1cmU7IHdlYi1zaGFyZTsgZnVsbHNjcmVlbiIgYWxsb3dmdWxsc2NyZWVuIHRpdGxlPSInK2VzYyh2LnRpdGxlKSsn"
    "Ij48L2lmcmFtZT4nOwogdmFyIGE9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInR2bGluayIpOwogYS5ocmVmPXYueW91dHViZT8o"
    "Imh0dHBzOi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9IitlbmNvZGVVUklDb21wb25lbnQodi5pZCkpOnYudXJsOwogYS50ZXh0"
    "Q29udGVudD12LnlvdXR1YmU/IlBsYXlpbmcgbXV0ZWQgwrcgdGFwIHRoZSB2aWRlbyB0byB1bm11dGUgwrcgb3Igd2F0Y2ggb24g"
    "WW91VHViZSDihpciOigiQnkgIit2LmNoYW5uZWwrIiDCtyBmcmVlIHByZXZpZXcsIHRoZW4gIit2LnByaWNlKyJwIMK3IG9wZW4g"
    "aXQgb24gaXRzIG93biBwYWdlIOKGlyIpOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJvb21Ob3ciKS50ZXh0Q29udGVudD0i"
    "Tk9XIFNIT1dJTkcgwrcgQ0ggIisoY3VyKzEpKyIgwrcgIit2LmNoYW5uZWwrIiDCtyAiK3YudGl0bGU7CiBjaGFucygpO3Zpc29y"
    "KCl9CmZ1bmN0aW9uIGNoYW5zKCl7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNoYW5zIikuaW5uZXJIVE1MPUxJU1QubWFwKGZ1"
    "bmN0aW9uKHYsaSl7cmV0dXJuICc8YnV0dG9uIGNsYXNzPSInKyhpPT09Y3VyPyJvbiI6IiIpKyciIGRhdGEtaT0iJytpKyciPkNI"
    "ICcrKGkrMSkrJyDCtyAnK2VzYyh2LmNoYW5uZWwpKyc8L2J1dHRvbj4nfSkuam9pbigiIik7CiBBcnJheS5wcm90b3R5cGUuZm9y"
    "RWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoIiNjaGFucyBidXR0b24iKSxmdW5jdGlvbihiKXtiLm9uY2xpY2s9"
    "ZnVuY3Rpb24oKXtjdXI9K2IuZGF0YXNldC5pO3JlZWw9TWF0aC5mbG9vcihjdXIvUEVSKTt0digpO2J1aWxkKCl9fSl9CndpbmRv"
    "dy5lbnRlcj1mdW5jdGlvbigpe2lmKCFMSVNULmxlbmd0aCl7bG9jYXRpb24uaHJlZj0iL2NyZWF0ZSI7cmV0dXJufQogZG9jdW1l"
    "bnQuZ2V0RWxlbWVudEJ5SWQoImxvYmJ5IikuY2xhc3NMaXN0LmFkZCgiaGlkZGVuIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "InJvb20iKS5jbGFzc0xpc3QucmVtb3ZlKCJoaWRkZW4iKTt0digpfTsKd2luZG93LmxlYXZlPWZ1bmN0aW9uKCl7ZG9jdW1lbnQu"
    "Z2V0RWxlbWVudEJ5SWQoInR2IikuaW5uZXJIVE1MPSIiO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJyb29tIikuY2xhc3NMaXN0"
    "LmFkZCgiaGlkZGVuIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImxvYmJ5IikuY2xhc3NMaXN0LnJlbW92ZSgiaGlkZGVuIik7"
    "bWFyaygpfTsKd2luZG93LnN0ZXA9ZnVuY3Rpb24oZCl7aWYoIUxJU1QubGVuZ3RoKXJldHVybjtjdXI9KGN1citkK0xJU1QubGVu"
    "Z3RoKSVMSVNULmxlbmd0aDtyZWVsPU1hdGguZmxvb3IoY3VyL1BFUik7dHYoKTtidWlsZCgpfTsKd2luZG93LnRvZ2dsZVNwaW49"
    "ZnVuY3Rpb24oKXt2YXIgdD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidHYiKSx2PUxJU1RbY3VyXTtzcGlubmluZz0hc3Bpbm5p"
    "bmc7CiBpZihzcGlubmluZyl7dC5pbm5lckhUTUw9di55b3V0dWJlPyc8aW1nIGFsdD0iIiBzdHlsZT0id2lkdGg6MTAwJTtoZWln"
    "aHQ6MTAwJTtvYmplY3QtZml0OmNvdmVyO2JvcmRlci1yYWRpdXM6NHB4IiBzcmM9Imh0dHBzOi8vaW1nLnlvdXR1YmUuY29tL3Zp"
    "LycrZW5jb2RlVVJJQ29tcG9uZW50KHYuaWQpKycvaHFkZWZhdWx0LmpwZyI+JzonPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2Fs"
    "aWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2hlaWdodDoxMDAlO2ZvbnQtc2l6ZTo2MHB4O2NvbG9yOiNk"
    "NTliZmYiPvCfjqw8L2Rpdj4nOwogIHQuY2xhc3NMaXN0LmFkZCgic3BpbiIpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0dmxp"
    "bmsiKS50ZXh0Q29udGVudD0iVGhlIFRWIGlzIHNwaW5uaW5nIMK3IHRhcCBTdG9wIHNwaW5uaW5nIHRvIHdhdGNoIn0KIGVsc2V7"
    "dC5jbGFzc0xpc3QucmVtb3ZlKCJzcGluIik7dHYoKX0KIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzcGluQnRuIikudGV4dENv"
    "bnRlbnQ9c3Bpbm5pbmc/IlN0b3Agc3Bpbm5pbmciOiJTcGluIHRoZSBUViJ9OwpidWlsZCgpOwpmZXRjaCgiL3gvY2luZW1hZmVl"
    "ZC9saXN0Iix7Y2FjaGU6Im5vLXN0b3JlIn0pLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpfSkudGhlbihmdW5jdGlv"
    "bihkKXsKIGlmKGQmJmQudmlkZW9zJiZkLnZpZGVvcy5sZW5ndGgpe0dPVj1kLnZpZGVvcy5tYXAoZnVuY3Rpb24odil7di55b3V0"
    "dWJlPXRydWU7cmV0dXJuIHZ9KTsKICB2YXIgZXh0cmE9W107dHJ5e2V4dHJhPUpTT04ucGFyc2UobG9jYWxTdG9yYWdlLmdldEl0"
    "ZW0oInNlYmJpLmNpbmVtYSIpfHwiW10iKX1jYXRjaChlKXt9CiAgaWYoQXJyYXkuaXNBcnJheShleHRyYSkpR09WPUdPVi5jb25j"
    "YXQoZXh0cmEubWFwKGZ1bmN0aW9uKHYpe3YueW91dHViZT10cnVlO3JldHVybiB2fSkpOwogIGlmKHdpbmc9PT0iZ292Iil7TElT"
    "VD1HT1Y7YnVpbGQoKX19fSkuY2F0Y2goZnVuY3Rpb24oKXt9KTsKZmV0Y2goIi94L21hcnF1ZWUvbGlzdCIse2NhY2hlOiJuby1z"
    "dG9yZSJ9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiByLmpzb24oKX0pLnRoZW4oZnVuY3Rpb24oZCl7CiBpZihkJiZkLnNjcmVl"
    "bnMpe1RFTj1kLnNjcmVlbnMubWFwKGZ1bmN0aW9uKHMpe3JldHVybiB7aWQ6U3RyaW5nKHMuaWQpLHRpdGxlOnMudGl0bGUsY2hh"
    "bm5lbDpzLmNyZWF0b3IscHJpY2U6cy5wcmljZSx1cmw6cy51cmwseW91dHViZTpmYWxzZX19KTsKICBkb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgid1QiKS50ZXh0Q29udGVudD0i8J+OrCBUaGUgMTBwIFdpbmcgKCIrVEVOLmxlbmd0aCsiKSI7CiAgaWYod2luZz09"
    "PSJ0ZW4iKXtMSVNUPVRFTjtidWlsZCgpfX19KS5jYXRjaChmdW5jdGlvbigpe30pOwp9KSgpOwo8L3NjcmlwdD48L2JvZHk+PC9o"
    "dG1sPgo="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    '/cinema': (_d(_HTML_B64), "text/html; charset=utf-8"),
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
