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
