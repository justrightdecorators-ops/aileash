"""
Peer-signed submissions - /x/signed/<action>

WHAT CHANGED IN 1.1
-------------------
Three things, all of the same kind: a field that read stronger than it was.

1. receipt_seq is a real number now.

   This lane returned whatever server.py's seal() gave back for the
   sequence, and passed the literal string "public-signed" as the api_key.
   That is not a row in api_keys, so the UPDATE matched nothing, the SELECT
   returned nothing, and the value was always null. The field sat in the
   response named as though it were a receipt sequence, carrying nothing.

   The point of a sequence is that a holder of receipts N and N+2 can PROVE
   N+1 exists and was not received. A null cannot do that, so this lane had
   no completeness property while appearing to offer one.

   Found on the sibling lane at /x/peer/submit by Philip Pinol (PRAXIS),
   whose schema required an integer and got a null. Same fault here, fixed
   before anybody hit it. The sequence is now issued by this module, per
   enrolled name, inside the same lock hold that writes the row.

2. A failed seal no longer returns a receipt.

   ctx["seal"] was called and its result used without checking. If it
   raised or came back without a hash, this lane would have returned a
   success body with nothing behind it - the exact hollow receipt that
   turned up on the peer lane on 2026-08-26. It now returns 500, records
   nothing, and says why.

3. Enrolment and rotation report whether they sealed.

   Both were sealing as a side effect and ignoring the outcome. The
   operation still happens - a key is a database row and a failed audit
   note does not un-enrol it - but the response says sealed true or false
   with the error, rather than leaving it to be assumed.

The server-wide key counter is still returned, as key_seq, and is still
null. Reported rather than omitted so the absence is visible instead of
inferred, which is the confusion that made this worth fixing at all.

THE GAP THIS CLOSES
-------------------
Two people arrived at the same missing piece from opposite directions on the
same day.

Ishaan (Shango MID) read the existing signed lane and said, correctly, that
"binds a name to a secret rather than to an address" reads stronger than it
is. An HMAC uses a shared secret. A shared secret is held by both parties. So
it proves the submission came from SOMEONE HOLDING THE SECRET - which is the
peer and also the operator of this deployment. It closes third-party
submission under a peer's name. It does not close operator submission under a
peer's name.

Chidi (ViriSIM) came at it from the regulator's side: for the evidence to mean
anything to a third party, the customer has to sign, not the platform holding
the customer's records.

Same gap. This module closes it.

HOW
---
The peer generates an Ed25519 keypair and keeps the private half. This
deployment is given ONLY the public half. A public key is not a secret and
grants nothing: it verifies a signature and cannot produce one.

From then on, a submission under that name is accepted only if it carries a
signature this deployment can verify against that public key - and this
deployment CANNOT create such a signature, because it does not hold the
private key and never has. The property is not a promise about our conduct.
It is arithmetic.

WHAT THIS MEANS FOR THE RECORD
------------------------------
The other lanes answer "did somebody hand us this tip". This lane answers
"did the holder of this key hand us this tip", and the difference matters
precisely when the operator is the party you are worried about.

A regulator or auditor reading a signed observation does not have to trust
this deployment about who submitted it. They can take the public key from
/x/signed/keys, take the canonical message and the signature from the record,
and check it themselves with any Ed25519 library in any language.

WHAT IT STILL DOES NOT DO
-------------------------
- It does not prove the records behind the tip are true. Nothing here does.
- It does not prove completeness of the peer's own chain. A signed chain can
  still omit records. Catching that needs an audit protocol, not
  cryptography - see Chidi's incognito-user test, which is the only thing
  anyone has proposed that attacks it. Note this is a different claim from
  the receipt sequence below, which is about completeness of the receipts WE
  issued, not of the records THEY sealed.
- It does not prove who the keyholder IS. It proves the same party signed
  each time. Identity is a separate problem and this does not solve it.
- Enrolment is open, so the first party to enrol a name gets it. Same as
  everywhere else in this standard, that is detection rather than
  prevention: an enrolment is sealed, permanent and public, and an enrolment
  placed over a name already seen in the witness log is flagged as such.

WHY THE OPERATOR CANNOT QUIETLY SWAP A KEY
------------------------------------------
The obvious attack on the whole idea: the operator replaces the peer's public
key with one of their own, then signs freely. So there is no route that
overwrites a key. Rotation exists, and a rotation must itself be signed by
the key being replaced. An operator who does not hold the current private key
cannot rotate it, and every rotation is sealed into the chain with both keys
recorded. A peer who has lost their key cannot rotate either - they enrol a
new name, and the abandoned one stays visible.

CANONICAL MESSAGE
-----------------
Exactly this, UTF-8, no trailing newline, four lines joined by \\n:

    aileash-signed-v1
    <chain>
    <tip>
    <ts>

  chain  the peer name, lowercase, as enrolled
  tip    64 lowercase hex characters
  ts     integer epoch seconds, no decimal point

Sign those bytes with the Ed25519 private key. Send the 64-byte signature as
128 lowercase hex characters. The message is deliberately short, positional
and free of JSON so that two implementations cannot disagree about how to
build it.

Rotation signs a different message with the SAME shape:

    aileash-rotate-v1
    <chain>
    <new public key, 64 hex>
    <ts>

REPLAY
------
A signature is a bearer token for the statement it signs. Anyone who sees one
can send it again. So: ts must be within SKEW_PAST seconds behind and
SKEW_FUTURE ahead of our clock, ts must be strictly greater than the last ts
we accepted for that name, and an exact repeat of a signature already stored
is refused. None of that is exotic - it is the ordinary set, written down so
nobody has to guess which of them we do.

WHY THIS LANE REJECTS, WHEN THE OPEN LANE NEVER DOES
----------------------------------------------------
/x/witness/observe seals everything and describes what it sealed, because
refusing an anonymous submission would mean deciding who is allowed to be
recorded. This lane is the opposite case. A submission whose signature does
not verify has no business being written into a name's history at all - the
harm is exactly that it would sit in the record looking like an event
involving that peer. So this lane refuses, says why, and seals nothing.

    GET  /x/signed/spec                  the protocol
    GET  /x/signed/keys                  every enrolled name and public key
    POST /x/signed/enroll                chain, pubkey
    POST /x/signed/submit                chain, tip, ts, signature
    POST /x/signed/rotate                chain, new_pubkey, ts, signature
    GET  /x/signed/verify?peer=&tip=     the receipt, with everything a third
                                         party needs to check it themselves
"""

import hashlib
import re
import time
from datetime import datetime, timezone

VERSION = "1.1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX128 = re.compile(r"^[0-9a-f]{128}$")

MSG_PREFIX = "aileash-signed-v1"
ROTATE_PREFIX = "aileash-rotate-v1"

# Replay window. Generous enough for a batch job on a slow link, tight enough
# that a captured signature is not useful for long.
SKEW_PAST = 900
SKEW_FUTURE = 120

# Everything here is readable and usable without an account. A verification
# lane that only account holders can check is not a verification lane.
PUBLIC = {("GET", "spec"), ("GET", "keys"), ("GET", "verify"),
          ("POST", "enroll"), ("POST", "submit"), ("POST", "rotate")}

MAX_LIST = 500

# What this lane files its own audit rows under. Deliberately not a real
# api_key - it is a label, and it is exactly why server.py's per-key
# sequence comes back null here. See _seq_note.
FILED_UNDER = "public-signed"

MESSAGES = {
    "what_this_proves": (
        "That the holder of the enrolled private key produced this exact "
        "statement - name, tip and timestamp - and that we sealed it at the "
        "recorded time. This deployment holds only the public key and cannot "
        "produce such a signature, so it is not a claim you have to take on "
        "our word. Recheck it yourself with any Ed25519 library."),
    "what_this_does_not_prove": (
        "Nothing about whether the records behind the tip are true, nothing "
        "about whether the peer's chain is complete, and nothing about who "
        "the keyholder is in the world. It proves the same party signed each "
        "time."),
    "enrolled": (
        "This name is now bound to this public key permanently. We cannot "
        "change it - rotation requires a signature from the key being "
        "replaced, which we do not hold."),
    "keys_note": (
        "Public keys are not secrets. They are published so that anyone can "
        "verify a signed observation without asking us for anything."),
    "seq": (
        "An integer, never null, incremented by exactly one for each accepted "
        "submission UNDER THIS NAME on this lane. Issued inside the same lock "
        "that writes the record, so a number is never spent on a submission "
        "that was not stored. Two receipts numbered N and N+2 prove a third "
        "exists that you did not receive. The current highest is published at "
        "/x/signed/keys, so the check does not depend on asking us."),
    "key_seq": (
        "The server-wide per-API-key sequence, which is null on this lane and "
        "always will be. That counter lives on an api_key row, and this lane "
        "files under a label rather than a key because it authenticates by "
        "signature and issues nobody an account. It is returned rather than "
        "omitted so the absence is visible instead of inferred. Before 1.1 "
        "this null was reported as receipt_seq, which made a missing property "
        "look like a broken field."),
    "seq_survives_rotation": (
        "Rotating the key does not reset the sequence. It belongs to the "
        "name's submission history rather than to the key, so a rotation "
        "cannot be used to erase a gap."),
}

_ready = False


# ----------------------------------------------------------------------
# Ed25519 verification, RFC 8032, pure standard library
#
# Deliberately no third-party dependency. This deployment runs on a small
# box and a verification routine that needs a native extension is a
# verification routine that stops working on a platform migration. Extended
# homogeneous coordinates so a verify is milliseconds rather than seconds.
#
# Verify only. There is no signing function in this file, and that is not an
# oversight - there is nothing here that could be turned into a way for this
# deployment to produce a peer's signature.
# ----------------------------------------------------------------------

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _double(p):
    return _add(p, p)


def _scalarmult(p, e):
    if e == 0:
        return (0, 1, 1, 0)
    q = _scalarmult(p, e >> 1)
    q = _double(q)
    if e & 1:
        q = _add(q, p)
    return q


def _decodepoint(raw):
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _xrecover(y)
    if x & 1 != (raw[31] >> 7) & 1:
        x = _P - x
    point = (x, y, 1, x * y % _P)
    # on-curve check: -x^2 + y^2 = 1 + d x^2 y^2
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return point


def _equal(p, q):
    x1, y1, z1, _t1 = p
    x2, y2, z2, _t2 = q
    if (x1 * z2 - x2 * z1) % _P != 0:
        return False
    if (y1 * z2 - y2 * z1) % _P != 0:
        return False
    return True


def ed25519_verify(public_key, message, signature):
    """True if signature is a valid Ed25519 signature of message under
    public_key. Bytes in, bool out, never raises."""
    try:
        if len(public_key) != 32 or len(signature) != 64:
            return False
        a = _decodepoint(public_key)
        if a is None:
            return False
        r_raw = signature[:32]
        r = _decodepoint(r_raw)
        if r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _L:
            return False
        h = int.from_bytes(
            hashlib.sha512(r_raw + public_key + message).digest(), "little") % _L
        left = _scalarmult(_B, s)
        right = _add(r, _scalarmult(a, h))
        return _equal(left, right)
    except Exception:
        return False


# ----------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------

def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS signed_keys("
                  "peer TEXT PRIMARY KEY,pubkey TEXT,enrolled REAL,"
                  "audit_hash TEXT,block_index INTEGER,"
                  "rotations INTEGER DEFAULT 0,last_ts REAL,note TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS signed_log("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,peer TEXT,tip TEXT,"
                  "peer_ts REAL,observed REAL,signature TEXT,pubkey TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_peer ON signed_log(peer,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_tip ON signed_log(tip)")

        # Added in 1.1. The receipt counter, per enrolled name, in its own
        # table so the counter survives anything that happens to the key row
        # - including a rotation. A rotation that reset the sequence could be
        # used to erase a gap, which is the one thing the sequence exists to
        # make impossible.
        c.execute("CREATE TABLE IF NOT EXISTS signed_seq("
                  "peer TEXT PRIMARY KEY, last_seq INTEGER DEFAULT 0)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _peer_name(data):
    return str(data.get("chain") or data.get("peer") or "").strip().lower()


def _key_row(ctx, peer):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT pubkey,enrolled,audit_hash,block_index,rotations,last_ts "
            "FROM signed_keys WHERE peer=?", (peer,)).fetchone()


def _latest_seq(ctx, peer):
    """Highest receipt number issued to this name. 0 if none."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _try_seal(ctx, event, result, when, api_key):
    """Seal, and say plainly whether it worked.

    Returns (audit_hash, block_index, key_seq, error). Nothing here swallows
    a failure. Before 1.1 the result was used without checking, which is how
    a hollow receipt gets issued.
    """
    try:
        h, idx, seq = ctx["seal"](event, result, when, api_key)
    except Exception as exc:
        return None, None, None, "%s: %s" % (type(exc).__name__, str(exc)[:300])
    if not h:
        return None, None, None, "seal returned no audit hash"
    return h, idx, seq, None


def _seen_in_open_lane(ctx, peer):
    """Has this name already appeared in the open witness log?

    An enrolment over a name somebody else has been using is the same shape as
    the url squat, and gets the same treatment: we cannot prevent it, so we
    record it permanently at the moment it happens.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM witness_log WHERE peer=?", (peer,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _check_ts(ts, last_ts):
    now = time.time()
    if ts > now + SKEW_FUTURE:
        return False, ("timestamp is %d seconds in the future; limit is %d"
                       % (int(ts - now), SKEW_FUTURE))
    if ts < now - SKEW_PAST:
        return False, ("timestamp is %d seconds old; limit is %d"
                       % (int(now - ts), SKEW_PAST))
    if last_ts is not None and ts <= last_ts:
        return False, ("timestamp %d is not later than the last one accepted "
                       "for this name (%d) - a signature cannot be replayed "
                       "and submissions must move forward"
                       % (int(ts), int(last_ts)))
    return True, None


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _enroll(ctx, data):
    peer = _peer_name(data)
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works well."}, 400
    pubkey = str(data.get("pubkey") or data.get("public_key") or "").strip().lower()
    if not HEX64.match(pubkey):
        return {"error": "invalid_pubkey",
                "message": "An Ed25519 public key is 32 bytes - 64 lowercase "
                           "hex characters. Send the public half only. Never "
                           "send us a private key; we have no use for one and "
                           "no route that accepts one."}, 400
    if _decodepoint(bytes.fromhex(pubkey)) is None:
        return {"error": "invalid_pubkey",
                "message": "That value is 64 hex characters but is not a "
                           "point on the curve, so it is not an Ed25519 "
                           "public key."}, 400

    existing = _key_row(ctx, peer)
    if existing:
        if existing[0] == pubkey:
            return {"already_enrolled": True, "chain": peer, "pubkey": pubkey,
                    "enrolled_at": _iso(existing[1]),
                    "block_index": existing[3],
                    "latest_receipt_seq": _latest_seq(ctx, peer),
                    "message": "This name is already bound to this key. "
                               "Nothing changed."}, 200
        return {"error": "name_already_enrolled", "chain": peer,
                "enrolled_pubkey": existing[0],
                "enrolled_at": _iso(existing[1]),
                "message": "This name is bound to a different key. We do not "
                           "overwrite a binding. If you hold the enrolled "
                           "private key, use /x/signed/rotate. If you do not, "
                           "this name is not available to you and this "
                           "attempt is not sealed."}, 409

    prior = _seen_in_open_lane(ctx, peer)
    ts = time.time()
    note = "enrolled"
    if prior:
        note = ("WARNING: this name had already been submitted %d time(s) to "
                "the open witness lane before this key was enrolled, so it "
                "was not a fresh name when it was claimed" % prior)

    ev = {"user_id": "sig:" + peer, "action": "signed_key_enrolled", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "KEY_ENROLLED", "score": 0, "signed_version": VERSION,
           "peer": peer, "pubkey": pubkey, "timestamp": ts, "detail": note}
    h, idx, _seq, seal_error = _try_seal(ctx, ev, res, ts, FILED_UNDER)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO signed_keys(peer,pubkey,enrolled,audit_hash,"
            "block_index,rotations,last_ts,note) VALUES(?,?,?,?,?,0,NULL,?)",
            (peer, pubkey, ts, h, idx, note))
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO signed_seq(peer,last_seq) VALUES(?,0)", (peer,))
        ctx["conn"].commit()

    out = {"enrolled": True, "chain": peer, "pubkey": pubkey,
           "enrolled_at": _iso(ts), "sealed_in_our_chain": h,
           "block_index": idx, "signed_version": VERSION,
           "sealed": seal_error is None,
           "latest_receipt_seq": 0,
           "message": MESSAGES["enrolled"],
           "canonical_message": _canonical_help(peer),
           "submit": "/x/signed/submit"}
    if seal_error:
        out["seal_error"] = seal_error
        out["seal_note"] = ("The key is enrolled and usable - it is a database "
                            "row and a failed audit note does not un-enrol it. "
                            "But the record of the enrolment did not seal, "
                            "which is a fault worth chasing and is reported "
                            "rather than hidden.")
    if prior:
        out["flag"] = note
    return out, 200


def _canonical_help(peer):
    return {"format": MSG_PREFIX + "\\n<chain>\\n<tip>\\n<ts>",
            "example_for_this_name": MSG_PREFIX + "\\n" + peer +
                                     "\\n<64 hex tip>\\n<integer epoch seconds>",
            "encoding": "UTF-8, no trailing newline, lines joined with a "
                        "single \\n",
            "signature": "Ed25519 over those bytes, sent as 128 lowercase hex"}


def _submit(ctx, data):
    peer = _peer_name(data)
    if not peer:
        return {"error": "chain_required"}, 400
    row = _key_row(ctx, peer)
    if not row:
        return {"error": "not_enrolled", "chain": peer,
                "message": "No public key is enrolled for this name. Enrol at "
                           "/x/signed/enroll, or use the open lane at "
                           "/x/witness/observe which needs nothing."}, 404
    pubkey, _enrolled, _h, _idx, _rot, last_ts = row

    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip",
                "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400
    signature = str(data.get("signature") or data.get("sig") or "").strip().lower()
    if not HEX128.match(signature):
        return {"error": "invalid_signature_format",
                "message": "An Ed25519 signature is 64 bytes - 128 lowercase "
                           "hex characters."}, 400
    raw_ts = data.get("ts", data.get("peer_ts"))
    try:
        ts_int = int(raw_ts)
    except (TypeError, ValueError):
        return {"error": "invalid_ts",
                "message": "ts must be integer epoch seconds, and must be the "
                           "same value you signed."}, 400

    ok, why = _check_ts(ts_int, last_ts)
    if not ok:
        return {"error": "timestamp_rejected", "message": why,
                "our_time": int(time.time())}, 400

    with ctx["lock"]:
        dup = ctx["conn"].execute(
            "SELECT observed FROM signed_log WHERE peer=? AND signature=? LIMIT 1",
            (peer, signature)).fetchone()
    if dup:
        return {"error": "replayed_signature",
                "message": "This exact signature was already accepted at %s."
                           % _iso(dup[0])}, 409

    message = "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]).encode("utf-8")
    if not ed25519_verify(bytes.fromhex(pubkey), message, bytes.fromhex(signature)):
        return {"error": "signature_did_not_verify",
                "chain": peer,
                "message": "Nothing has been sealed. The signature does not "
                           "verify against the key enrolled for this name. "
                           "The usual cause is a canonical message built "
                           "differently - check it byte for byte below.",
                "we_verified_against": _canonical_help(peer),
                "the_exact_bytes_we_hashed":
                    "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]),
                "enrolled_pubkey": pubkey}, 400

    observed = time.time()
    detail = ("peer=" + peer + ";tip=" + tip + ";ts=" + str(ts_int) +
              ";pubkey=" + pubkey + ";sig=" + signature)
    ev = {"user_id": "sig:" + peer, "action": "signed_tip_observed", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "SIGNED_TIP_SEALED", "score": 0, "signed_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": observed,
           "verification": "peer-signed", "detail": detail}

    # Seal FIRST, and only claim success if it produced a hash. A signed
    # submission that returns a receipt with no block behind it is worse than
    # a refusal, because the peer has no way to tell the difference without
    # going and looking at the chain.
    h, idx, key_seq, seal_error = _try_seal(ctx, ev, res, observed, FILED_UNDER)
    if seal_error:
        return {"ok": False, "accepted": False, "error": "seal_failed",
                "chain": peer, "tip": tip,
                "detail": "Your signature verified correctly, but the audit "
                          "chain did not seal the submission, so there is no "
                          "receipt to give you. This is a fault on this "
                          "deployment and not a problem with your submission.",
                "seal_error": seal_error,
                "recorded": False,
                "retry": "Nothing was written. No sequence number was spent "
                         "and your signature is not recorded as used, so a "
                         "fresh submission with a later ts can be sent once "
                         "this is fixed.",
                "observed_at": _iso(observed)}, 500

    # Issue the receipt number inside the same lock hold that writes the row.
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO signed_seq(peer,last_seq) VALUES(?,0)", (peer,))
        ctx["conn"].execute(
            "UPDATE signed_seq SET last_seq = COALESCE(last_seq,0) + 1 "
            "WHERE peer=?", (peer,))
        srow = ctx["conn"].execute(
            "SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()
        receipt_seq = int(srow[0]) if srow and srow[0] is not None else None

        ctx["conn"].execute(
            "INSERT INTO signed_log(peer,tip,peer_ts,observed,signature,"
            "pubkey,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?)",
            (peer, tip, float(ts_int), observed, signature, pubkey, h, idx))
        ctx["conn"].execute("UPDATE signed_keys SET last_ts=? WHERE peer=?",
                            (float(ts_int), peer))
        ctx["conn"].commit()

    # Mirror into the open witness log so the peer appears on the public
    # roster alongside everyone else. Guarded: the roster is a convenience
    # and the seal above is the evidence, so a failure here must not turn a
    # good submission into an error.
    mirrored = False
    try:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,"
                "audit_hash,block_index,note,url,liveness,name_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (FILED_UNDER, peer, tip, float(ts_int), observed, h, idx,
                 "signed submission - verified against enrolled Ed25519 key",
                 None, "peer-signed", "key-bound"))
            ctx["conn"].commit()
        mirrored = True
    except Exception:
        pass

    return {"chain": peer, "witnessed_tip": tip, "observed_at": _iso(observed),
            "peer_claimed_time": _iso(ts_int),
            "sealed_in_our_chain": h, "block_index": idx,
            "receipt_seq": receipt_seq,
            "receipt_seq_scope": "per-chain",
            "key_seq": key_seq,
            "verification": "peer-signed",
            "verified_against_pubkey": pubkey,
            "on_public_roster": mirrored,
            "signed_version": VERSION,
            "verify": "/x/signed/verify?peer=" + peer + "&tip=" + tip,
            "gapless": MESSAGES["seq"],
            "key_seq_note": MESSAGES["key_seq"],
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200


def _rotate(ctx, data):
    peer = _peer_name(data)
    row = _key_row(ctx, peer)
    if not row:
        return {"error": "not_enrolled", "chain": peer}, 404
    current, _enrolled, _h, _idx, rotations, last_ts = row

    new_pubkey = str(data.get("new_pubkey") or data.get("pubkey") or "").strip().lower()
    if not HEX64.match(new_pubkey) or _decodepoint(bytes.fromhex(new_pubkey)) is None:
        return {"error": "invalid_pubkey",
                "message": "new_pubkey must be an Ed25519 public key - 64 "
                           "lowercase hex characters."}, 400
    if new_pubkey == current:
        return {"error": "no_change",
                "message": "That is already the enrolled key."}, 400
    signature = str(data.get("signature") or data.get("sig") or "").strip().lower()
    if not HEX128.match(signature):
        return {"error": "invalid_signature_format"}, 400
    try:
        ts_int = int(data.get("ts"))
    except (TypeError, ValueError):
        return {"error": "invalid_ts"}, 400
    ok, why = _check_ts(ts_int, last_ts)
    if not ok:
        return {"error": "timestamp_rejected", "message": why,
                "our_time": int(time.time())}, 400

    message = "\n".join([ROTATE_PREFIX, peer, new_pubkey, str(ts_int)]).encode("utf-8")
    if not ed25519_verify(bytes.fromhex(current), message, bytes.fromhex(signature)):
        return {"error": "signature_did_not_verify",
                "message": "Nothing has been changed. A rotation must be "
                           "signed by the key being replaced. This is what "
                           "stops anyone - including the operator of this "
                           "deployment - swapping a peer's key.",
                "we_verified_against": {
                    "format": ROTATE_PREFIX + "\\n<chain>\\n<new pubkey>\\n<ts>",
                    "the_exact_bytes_we_hashed":
                        "\n".join([ROTATE_PREFIX, peer, new_pubkey,
                                   str(ts_int)])},
                "signed_by_key_expected": current}, 400

    ts = time.time()
    ev = {"user_id": "sig:" + peer, "action": "signed_key_rotated", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "KEY_ROTATED", "score": 0, "signed_version": VERSION,
           "peer": peer, "timestamp": ts,
           "detail": "from=" + current + ";to=" + new_pubkey +
                     ";authorised_by=" + current}
    h, idx, _seq, seal_error = _try_seal(ctx, ev, res, ts, FILED_UNDER)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE signed_keys SET pubkey=?,rotations=?,last_ts=? WHERE peer=?",
            (new_pubkey, (rotations or 0) + 1, float(ts_int), peer))
        ctx["conn"].commit()

    out = {"rotated": True, "chain": peer, "previous_pubkey": current,
           "pubkey": new_pubkey, "rotations": (rotations or 0) + 1,
           "sealed_in_our_chain": h, "block_index": idx,
           "sealed": seal_error is None,
           "latest_receipt_seq": _latest_seq(ctx, peer),
           "signed_version": VERSION,
           "sequence_note": MESSAGES["seq_survives_rotation"],
           "message": "Rotation sealed. Both keys are permanently in the "
                      "chain, so the history of this name's keys is public "
                      "and cannot be tidied up later."}
    if seal_error:
        out["seal_error"] = seal_error
        out["message"] = ("The rotation took effect and the new key is live. "
                          "The audit note about it did not seal, which is "
                          "reported rather than hidden.")
    return out, 200


def _keys(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT k.peer,k.pubkey,k.enrolled,k.block_index,k.rotations,k.note,"
            "COALESCE(s.last_seq,0) FROM signed_keys k "
            "LEFT JOIN signed_seq s ON s.peer = k.peer "
            "ORDER BY k.enrolled ASC LIMIT ?", (MAX_LIST,)).fetchall()
    out = []
    for peer, pubkey, enrolled, idx, rotations, note, seq in rows:
        entry = {"chain": peer, "pubkey": pubkey, "algorithm": "ed25519",
                 "enrolled_at": _iso(enrolled), "enrolment_block": idx,
                 "rotations": rotations or 0,
                 "latest_receipt_seq": seq or 0}
        if note and note.startswith("WARNING"):
            entry["flag"] = note
        out.append(entry)
    return {"count": len(out), "keys": out, "signed_version": VERSION,
            "note": MESSAGES["keys_note"],
            "receipt_seq_note": (
                "latest_receipt_seq is the highest receipt number issued to "
                "that name on this lane. A keyholder whose own highest "
                "receipt is lower than this has not received one of them, and "
                "can say exactly how many. Public on purpose - a gap you can "
                "only see from the inside is not evidence of anything."),
            "how_to_check_a_record": (
                "Take the pubkey from here, rebuild the canonical message "
                "from the record at /x/signed/verify, and check the signature "
                "with any Ed25519 implementation. You do not need anything "
                "from us to do it and you do not have to believe us.")}, 200


def _verify(ctx, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required",
                "usage": "/x/signed/verify?peer=<name>&tip=<64 hex>"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT observed,peer_ts,signature,pubkey,audit_hash,block_index "
            "FROM signed_log WHERE peer=? AND tip=? ORDER BY id ASC",
            (peer, tip)).fetchall()
    if not rows:
        return {"signed_observation": False, "peer": peer, "tip": tip,
                "message": "We hold no signed observation of this tip from "
                           "this name. It may still be in the open lane - "
                           "check /x/witness/attest."}, 404
    observed, peer_ts, signature, pubkey, h, idx = rows[0]
    ts_int = int(peer_ts)
    return {"signed_observation": True, "chain": peer, "tip": tip,
            "observed_at": _iso(observed), "peer_claimed_time": _iso(peer_ts),
            "sealed_in_our_chain": h, "block_index": idx,
            "times_observed": len(rows),
            "latest_receipt_seq": _latest_seq(ctx, peer),
            "signature": signature, "pubkey": pubkey, "algorithm": "ed25519",
            "canonical_message": "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]),
            "canonical_message_bytes_note": (
                "Those four lines joined by a single newline, UTF-8, no "
                "trailing newline. Hash nothing yourself - Ed25519 takes the "
                "message, not a digest of it."),
            "signed_version": VERSION,
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"],
            "recheck_it_yourself": (
                "python: pip install pynacl, then "
                "nacl.signing.VerifyKey(bytes.fromhex(pubkey))"
                ".verify(canonical_message.encode(), bytes.fromhex(signature))")}, 200


def _spec():
    return {"signed_version": VERSION,
            "what_this_lane_is": (
                "Submissions signed by a key this deployment does not hold. "
                "The open lane at /x/witness/observe proves somebody handed "
                "us a tip. This lane proves the holder of a specific private "
                "key did - including against us, because we only ever hold "
                "the public half."),
            "why_it_exists": (
                "The HMAC lane binds a name to a shared secret, and a shared "
                "secret is held by both parties. It closes third-party "
                "submission under your name and does not close operator "
                "submission under your name. This lane closes both, and it "
                "does so by arithmetic rather than by our promise."),
            "steps": [
                "1. Generate an Ed25519 keypair. Keep the private half. It "
                "never leaves your side and we have no route that accepts one.",
                "2. POST /x/signed/enroll with {\"chain\":\"<name>\","
                "\"pubkey\":\"<64 hex>\"}.",
                "3. Build the canonical message, sign it, and POST "
                "/x/signed/submit with {\"chain\",\"tip\",\"ts\",\"signature\"}.",
                "4. GET /x/signed/verify?peer=&tip= for the receipt, which "
                "carries everything a third party needs to recheck it "
                "without us.",
            ],
            "canonical_message": {
                "submit": MSG_PREFIX + "\\n<chain>\\n<tip>\\n<ts>",
                "rotate": ROTATE_PREFIX + "\\n<chain>\\n<new pubkey>\\n<ts>",
                "encoding": "UTF-8, single \\n between lines, no trailing "
                            "newline. ts is integer epoch seconds.",
            },
            "replay_controls": {
                "max_age_seconds": SKEW_PAST,
                "max_future_seconds": SKEW_FUTURE,
                "monotonic": "ts must be strictly greater than the last ts "
                             "accepted for the name",
                "duplicate_signatures": "refused",
            },
            "on_acceptance": {
                "receipt_seq": MESSAGES["seq"],
                "receipt_seq_scope": {'values': ['per-peer', 'per-name', 'per-chain'], 'per-peer': 'issued per registered peer_id. Used by /x/peer/submit.', 'per-name': 'issued per bound name. Used by /x/bind/submit.', 'per-chain': 'issued per enrolled chain name. Used by /x/signed/submit.', 'why_it_is_here': 'The three signed lanes each count within their own scope, so a receipt carries the scope of its own sequence rather than requiring the holder to remember which lane produced it. The set is closed: a value outside this list is an error on our side, not a new scope you should widen a schema for.', 'not_comparable_across_scopes': 'Two receipts with different scopes are counting different things and their numbers say nothing about each other.'},
                "key_seq": MESSAGES["key_seq"],
                "sequence_survives_rotation": MESSAGES["seq_survives_rotation"],
                "seal_failure": (
                    "If the audit chain does not seal your submission you get "
                    "500 seal_failed with the reason, and nothing is "
                    "recorded - no sequence number, no log row, no receipt. "
                    "Send a fresh submission with a later ts once the fault "
                    "is fixed. A receipt you cannot verify is worse than no "
                    "receipt, so this lane will not issue one."),
                "two_different_completeness_claims": (
                    "receipt_seq is about completeness of the receipts WE "
                    "issued to you. It says nothing about completeness of the "
                    "records YOUR chain sealed, which no signature can reach "
                    "and which is listed under honest_limits."),
            },
            "this_lane_rejects": (
                "Unlike the open lane, a submission that does not verify is "
                "refused and nothing is sealed. Writing an unverifiable "
                "signature into a name's history is the harm, not the "
                "protection."),
            "key_rotation": (
                "A rotation must be signed by the key being replaced. Nobody "
                "who lacks the current private key can rotate it, this "
                "deployment included, and every rotation is sealed with both "
                "keys recorded."),
            "honest_limits": [
                "Does not prove the records behind the tip are true.",
                "Does not prove the peer's own chain is complete. Catching an "
                "omission there needs an audit protocol, not cryptography.",
                "Does not prove who the keyholder is in the world - only that "
                "the same party signed each time.",
                "Enrolment is open, so the first party to enrol a name gets "
                "it. An enrolment over a name already seen in the open lane "
                "is flagged permanently, which is detection and not "
                "prevention.",
                "receipt_seq proves you are missing a receipt. It does not "
                "prove why, and it cannot distinguish a lost response from "
                "one that was never sent.",
            ],
            "changed_in_1_1_1": [
                "receipt_seq_scope is now a bare token from a closed set - "
                "per-peer, per-name, per-chain - rather than a sentence, "
                "and the set is published so a closed schema can pin an "
                "enum. Asked for by Philip Pinol (PRAXIS). Value change "
                "only; the response shape is unchanged from 1.1.",
            ],
            "changed_in_1_1": [
                "receipt_seq is a real per-chain gapless sequence issued by "
                "this module, not the api_key counter that was always null "
                "here because this lane files under a label rather than a "
                "key. The completeness property applies to this lane for the "
                "first time.",
                "The api_key counter is still returned, as key_seq, and is "
                "null by design so the absence is stated rather than hidden.",
                "A failed seal returns 500 and records nothing, instead of "
                "returning a receipt with no block behind it.",
                "Enrolment and rotation report sealed true or false with the "
                "error, rather than sealing as a side effect and ignoring "
                "the outcome.",
                "/x/signed/keys publishes latest_receipt_seq per name.",
            ],
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "enroll":
            return _enroll(ctx, data)
        if action == "submit":
            return _submit(ctx, data)
        if action == "rotate":
            return _rotate(ctx, data)
    else:
        if action == "spec":
            return _spec()
        if action == "keys":
            return _keys(ctx)
        if action == "verify":
            return _verify(ctx, data)
    return {"error": "unknown_action", "action": action}, 404
