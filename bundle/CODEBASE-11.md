# Codebase — part 11 of 27

Contains:
- `modules/signed.py`
- `modules/sortition.py`
- `modules/spec.py`
- `modules/standard.py`
- `modules/stats.py`


## `modules/signed.py`

953 lines, 44350 bytes

```python
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

```


## `modules/sortition.py`

789 lines, 33138 bytes

```python
"""
sortition.py - selection by lot. The operator stops choosing who gets audited.

THE HOLE THIS FILLS
-------------------
Every system claiming human oversight reviews a sample of decisions. In
every one of them, the operator picks the sample. So the sample proves
nothing: you can review the easy ones, or the ones you already know are
clean, and nobody outside can tell the difference. It is the softest spot
in every Article 14 claim in the industry, and it has stayed soft because
there was no alternative.

There is one now. heartbeat.py seals a public beacon value on a cadence -
a number nobody, including the operator, can know before its tick. That is
a dice roll no one owns.

THE THREE LOCKS, IN ORDER. THE ORDER IS THE WHOLE POINT.
--------------------------------------------------------
1. COMMIT THE POOL. Every record eligible for review in a period is
   listed, hashed into one pool digest, and sealed. The pool is now fixed.
2. WAIT FOR A TICK. The draw may only use a beacon value sealed AFTER the
   pool commit. This module refuses otherwise. So the pool was fixed
   before the dice existed, and cannot be edited once they do.
3. DRAW. The beacon value deterministically ranks the pool. The lowest k
   ranks are selected. Anyone can recompute it from public values.

Break any one and the sample is choosable again. Enforced here, not
promised.

WHAT IT CATCHES
---------------
A selected record with no review sealed against it is a permanent, visible
hole with a name on it. You cannot quietly skip an awkward case, because
the case was chosen for you in public, and its absence is the evidence.

Refusal is allowed and is not hidden - it is sealed as a refusal with a
reason. An honest refusal on the record is worth more than a silent gap.

THE SELECTION FUNCTION, PUBLISHED SO IT IS NOT OURS
---------------------------------------------------
  seed = SHA256("AILEASH-SORTITION-v1" | period | pool_digest | beacon_value)
  rank(i) = SHA256(seed | ":" | record_hash_i)
  selected = the k records with the lowest rank, ties by record hash

No random number generator, no language-specific behaviour, no library.
Ten lines in any language. A stranger recomputes it and either gets our
list or catches us.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the reviews were any good. It proves nobody chose
  which ones happened.
- It does not stop an operator declining to draw at all. A period with no
  draw is a period with no sample, and /outstanding says so.
- Pool membership is asserted by this server. What stops a record being
  left out of the pool is complete.py, which commits the period's record
  count in advance - separate module, separate check.
- Selection is uniform. Risk-weighted sampling is deliberately not offered:
  a weighting the operator sets is a choice the operator made.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec         public  what this is and the exact selection function
  GET  draws        public  every draw ever made
  GET  draw         public  ?id= - one draw, its beacon value, its selection
  GET  verify       public  ?id= - recompute the draw from scratch, here
  GET  outstanding  public  selected records with no review yet, and how late
  GET  status       public  coverage, response rate, oldest unanswered
  POST pool         keyed   commit the pool for a period
  POST draw         keyed   draw a sample against a sealed beacon tick
  POST review       keyed   record a review, or a refusal with a reason
"""

import json
import time
import hashlib

VERSION = "1.1.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "draws"),
    ("GET", "draw"),
    ("GET", "verify"),
    ("GET", "outstanding"),
    ("GET", "status"),
}

DOMAIN_SEED = b"AILEASH-SORTITION-v1"
DOMAIN_POOL = b"AILEASH-POOL-v1"

DEFAULT_RATE = 0.05          # 5 percent
MIN_SELECT = 1
MAX_SELECT = 500
MAX_POOL = 200000
REVIEW_DUE_HOURS = 72

DDL = [
    """CREATE TABLE IF NOT EXISTS sortition_pool (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        period       TEXT NOT NULL,
        pool_digest  TEXT NOT NULL,
        pool_size    INTEGER NOT NULL,
        members      TEXT NOT NULL,
        committed_at REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_pool ON sortition_pool(period)",
    """CREATE TABLE IF NOT EXISTS sortition_draw (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        period        TEXT NOT NULL,
        pool_id       INTEGER NOT NULL,
        pool_digest   TEXT NOT NULL,
        pool_size     INTEGER NOT NULL,
        rate          REAL NOT NULL,
        select_count  INTEGER NOT NULL,
        beacon_source TEXT,
        beacon_round  INTEGER,
        beacon_value  TEXT NOT NULL,
        beacon_rowid  INTEGER,
        seed          TEXT NOT NULL,
        selected      TEXT NOT NULL,
        drawn_at      REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sortition_review (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        draw_id      INTEGER NOT NULL,
        record_hash  TEXT NOT NULL,
        outcome      TEXT NOT NULL,
        reviewer     TEXT,
        reason       TEXT,
        recorded_at  REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_rev ON sortition_review(draw_id, record_hash)",
]

OUTCOMES = ("agreed", "disagreed", "escalated", "refused")

VOCABULARY = {
    "pool": "Every record eligible for review in a period, fixed and sealed before any dice exist.",
    "draw": "The selection, computed from a beacon value that did not exist when the pool was sealed.",
    "selected": "Chosen by the beacon, not by us. We could not have known which.",
    "outstanding": "Selected and not yet answered. Visible, named, and counting.",
    "refused": "Declined on the record with a reason. Not a gap - a decision that is now permanent.",
    "gap": "Selected, past due, and never answered. The thing this module exists to make impossible to hide.",
}

WHAT_THIS_PROVES = (
    "That nobody chose which records were reviewed. It does not prove the "
    "reviews were competent, honest or useful. Those are different problems "
    "and this module does not touch them."
)


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        conn.commit()


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("audit_hash", "hash", "block_hash"):
        if n in c:
            return n
    return None


def _ts_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("ts", "timestamp", "created", "observed"):
        if n in c:
            return n
    return None


def _period_bounds(period):
    """YYYY, YYYY-MM, YYYY-MM-DD -> (start_epoch, end_epoch) UTC."""
    p = str(period).strip()
    try:
        if len(p) == 4:
            s = time.strptime(p + "-01-01", "%Y-%m-%d")
            e = time.strptime(str(int(p) + 1) + "-01-01", "%Y-%m-%d")
        elif len(p) == 7:
            s = time.strptime(p + "-01", "%Y-%m-%d")
            y, m = int(p[:4]), int(p[5:7])
            y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
            e = time.strptime("%04d-%02d-01" % (y2, m2), "%Y-%m-%d")
        elif len(p) == 10:
            s = time.strptime(p, "%Y-%m-%d")
            e = time.gmtime(_cal(s) + 86400)
        else:
            return None
    except ValueError:
        return None
    return _cal(s), _cal(e)


def _cal(st):
    import calendar
    return calendar.timegm(st)


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes" % (s // 60)
    if s < 86400:
        return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)
    return "%d days %d hours" % (s // 86400, (s % 86400) // 3600)


def _pool_digest(members):
    h = hashlib.sha256()
    h.update(DOMAIN_POOL + b"\n")
    for m in members:
        h.update(m.encode() + b"\n")
    return h.hexdigest()


def _seed(period, pool_digest, beacon_value):
    h = hashlib.sha256()
    h.update(DOMAIN_SEED + b"|")
    h.update(str(period).encode() + b"|")
    h.update(pool_digest.encode() + b"|")
    h.update(str(beacon_value).encode())
    return h.hexdigest()


def select(members, seed, k):
    """The published selection function. Deterministic, no RNG."""
    ranked = []
    for m in members:
        r = hashlib.sha256((seed + ":" + m).encode()).hexdigest()
        ranked.append((r, m))
    ranked.sort()
    return [m for _, m in ranked[:k]]


def _seal(ctx, action, payload):
    """Seal through the host's seal().

    server.py: seal(event, result, ts, api_key=None) where EVENT IS A DICT
    carrying user_id (subscripted inside), returning
    (audit_hash, block_index, key_seq).
    """
    fn = ctx.get("seal")
    if fn is None:
        return None, None
    ts = time.time()
    event = {"user_id": "sortition", "action": action, "amount": 0,
             "country": "UK", "device_id": "sortition", "anomaly": 0,
             "device_risk": 0}
    result = dict(payload)
    result.setdefault("decision", "SORTITION")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)
    for call in (lambda: fn(event, result, ts),
                 lambda: fn(event, result, ts, None),
                 lambda: fn(event, result)):
        try:
            out = call()
        except TypeError:
            continue
        except Exception:
            return None, None
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return h, idx
    return None, None


def _backfill(conn, lock, table, rowid_field, pk):
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        r = cur.fetchone()
        rid = r[0] if r and r[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute("UPDATE %s SET chain_rowid=?, audit_hash=? WHERE id=?" % table,
                    (rid, h, pk))
        conn.commit()
    return rid, h


def _latest_beat_after(conn, rowid):
    """The first heartbeat sealed strictly after a given chain row."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT source, beacon_round, value, chain_rowid, fetched_at"
            " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
            " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
        return cur.fetchone()
    except Exception:
        return None


def _beats_available(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick")
        return cur.fetchone()[0]
    except Exception:
        return None


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    if method == "GET" and action == "spec":
        return _spec(), 200

    # -------------------------------------------------- pool
    if method == "POST" and action == "pool":
        period = data.get("period")
        bounds = _period_bounds(period) if period else None
        if not bounds:
            return {"error": "period_required",
                    "formats": ["YYYY", "YYYY-MM", "YYYY-MM-DD"]}, 400
        start, end = bounds
        if end > time.time():
            return {"error": "period_not_closed",
                    "note": ("A pool can only be committed for a period that "
                             "has ended. Committing a live period would let "
                             "records arrive after the pool was fixed."),
                    "period_ends": _iso(end)}, 409

        hcol, tcol = _hash_col(conn), _ts_col(conn)
        if not hcol or not tcol:
            return {"error": "audit_log_schema_unrecognised"}, 500

        cur = conn.cursor()
        kind = data.get("event")
        if kind:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? AND event=?"
                " ORDER BY rowid" % (hcol, tcol, tcol), (start, end, kind))
        else:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? ORDER BY rowid"
                % (hcol, tcol, tcol), (start, end))
        members = sorted({r[0] for r in cur.fetchall() if r[0]})
        if not members:
            return {"error": "empty_period", "period": period}, 404
        if len(members) > MAX_POOL:
            return {"error": "pool_too_large", "size": len(members),
                    "max": MAX_POOL}, 413

        digest = _pool_digest(members)
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id, pool_digest FROM sortition_pool WHERE period=?",
                        (period,))
            prior = cur.fetchone()
            if prior:
                return {"error": "pool_already_committed", "period": period,
                        "pool_digest": prior[1],
                        "note": "A pool commits once. That is what makes it a pool."}, 409
            cur.execute(
                "INSERT INTO sortition_pool (period, pool_digest, pool_size,"
                " members, committed_at) VALUES (?,?,?,?,?)",
                (period, digest, len(members), json.dumps(members), now))
            pid = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_pool", {
            "period": period, "pool_digest": digest, "pool_size": len(members),
            "event_filter": kind,
            "note": ("Pool fixed. Any draw against it must use a beacon value "
                     "sealed after this block."),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_pool", "chain_rowid", pid)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_pool SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, pid))
                conn.commit()

        return {"pool_id": pid, "period": period, "pool_digest": digest,
                "pool_size": len(members), "sealed_at_chain_rowid": rid,
                "audit_hash": h,
                "next": ("Wait for a heartbeat sealed after block %s, then "
                         "POST /x/sortition/draw." % rid)}, 200

    # -------------------------------------------------- draw
    if method == "POST" and action == "draw":
        period = data.get("period")
        cur = conn.cursor()
        cur.execute("SELECT id, pool_digest, pool_size, members, chain_rowid"
                    " FROM sortition_pool WHERE period=?", (period,))
        pool = cur.fetchone()
        if not pool:
            return {"error": "no_pool_for_period", "period": period,
                    "next": "POST /x/sortition/pool first"}, 404
        pid, digest, size, members_json, pool_rowid = pool

        cur.execute("SELECT id FROM sortition_draw WHERE period=?", (period,))
        if cur.fetchone():
            return {"error": "already_drawn", "period": period,
                    "note": "One draw per pool. A second draw is a second chance."}, 409

        if pool_rowid is None:
            return {"error": "pool_not_located_in_chain"}, 500

        beat = _latest_beat_after(conn, pool_rowid)
        if not beat:
            n = _beats_available(conn)
            return {"error": "no_beacon_since_pool_commit",
                    "beats_in_system": n,
                    "why": ("The draw must use a value that did not exist when "
                            "the pool was sealed. Wait for the next heartbeat."),
                    "check": "/x/heartbeat/latest"}, 409

        b_source, b_round, b_value, b_rowid, b_at = beat
        members = json.loads(members_json)

        try:
            rate = float(data.get("rate", DEFAULT_RATE))
        except (TypeError, ValueError):
            rate = DEFAULT_RATE
        rate = max(0.0001, min(1.0, rate))
        k = int(round(size * rate))
        k = max(MIN_SELECT, min(k, MAX_SELECT, size))

        seed = _seed(period, digest, b_value)
        chosen = select(members, seed, k)
        now = time.time()

        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sortition_draw (period, pool_id, pool_digest,"
                " pool_size, rate, select_count, beacon_source, beacon_round,"
                " beacon_value, beacon_rowid, seed, selected, drawn_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (period, pid, digest, size, rate, k, b_source, b_round,
                 b_value, b_rowid, seed, json.dumps(chosen), now))
            did = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_draw", {
            "draw_id": did, "period": period, "pool_digest": digest,
            "pool_size": size, "rate": rate, "selected_count": k,
            "beacon": {"source": b_source, "round": b_round, "value": b_value,
                       "sealed_at_block": b_rowid},
            "seed": seed, "selected": chosen,
            "note": ("Selection is recomputable by anyone from pool_digest and "
                     "the beacon value. See /x/sortition/spec."),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_draw", "chain_rowid", did)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_draw SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, did))
                conn.commit()

        return {"draw_id": did, "period": period, "pool_size": size,
                "rate": rate, "selected_count": k, "selected": chosen,
                "beacon": {"source": b_source, "round": b_round,
                           "value": b_value, "sealed_at_block": b_rowid,
                           "sealed_at": _iso(b_at)},
                "seed": seed, "sealed_at_chain_rowid": rid, "audit_hash": h,
                "review_due": _iso(now + REVIEW_DUE_HOURS * 3600),
                "recompute_this_yourself": "/x/sortition/verify?id=%d" % did}, 200

    # -------------------------------------------------- review
    if method == "POST" and action == "review":
        did = data.get("draw_id")
        rec = data.get("record")
        outcome = str(data.get("outcome", "")).lower()
        if not did or not rec:
            return {"error": "draw_id_and_record_required"}, 400
        if outcome not in OUTCOMES:
            return {"error": "outcome_invalid", "allowed": list(OUTCOMES)}, 400
        if outcome == "refused" and not data.get("reason"):
            return {"error": "reason_required_to_refuse",
                    "why": ("A refusal without a reason is a gap wearing a "
                            "label. The reason is sealed and permanent.")}, 400

        cur = conn.cursor()
        cur.execute("SELECT selected FROM sortition_draw WHERE id=?", (did,))
        row = cur.fetchone()
        if not row:
            return {"error": "unknown_draw", "draw_id": did}, 404
        if rec not in json.loads(row[0]):
            return {"error": "record_not_selected",
                    "note": ("Reviews can only be filed against records the "
                             "beacon chose. Volunteering extra reviews does "
                             "not count toward the sample.")}, 409

        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id FROM sortition_review WHERE draw_id=? AND record_hash=?",
                        (did, rec))
            if cur.fetchone():
                return {"error": "already_reviewed",
                        "note": "A review is filed once and cannot be replaced."}, 409
            cur.execute(
                "INSERT INTO sortition_review (draw_id, record_hash, outcome,"
                " reviewer, reason, recorded_at) VALUES (?,?,?,?,?,?)",
                (did, rec, outcome, data.get("reviewer"), data.get("reason"), now))
            rvid = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_review", {
            "draw_id": did, "record": rec, "outcome": outcome,
            "reviewer": data.get("reviewer"), "reason": data.get("reason"),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_review", "chain_rowid", rvid)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_review SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, rvid))
                conn.commit()
        return {"recorded": True, "review_id": rvid, "outcome": outcome,
                "sealed_at_chain_rowid": rid, "audit_hash": h}, 200

    # -------------------------------------------------- draws
    if method == "GET" and action == "draws":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, period, pool_size, rate, select_count, beacon_source,"
            " beacon_round, drawn_at, audit_hash FROM sortition_draw"
            " ORDER BY id DESC LIMIT 100")
        out = []
        for r in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM sortition_review WHERE draw_id=?", (r[0],))
            done = cur2.fetchone()[0]
            out.append({"draw_id": r[0], "period": r[1], "pool_size": r[2],
                        "rate": r[3], "selected": r[4], "reviewed": done,
                        "outstanding": r[4] - done,
                        "beacon": {"source": r[5], "round": r[6]},
                        "drawn_at": _iso(r[7]), "audit_hash": r[8]})
        return {"count": len(out), "draws": out, "vocabulary": VOCABULARY}, 200

    # -------------------------------------------------- one draw
    if method == "GET" and action == "draw":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT record_hash, outcome, reviewer, reason, recorded_at"
                    " FROM sortition_review WHERE draw_id=?", (did,))
        revs = {r[0]: {"outcome": r[1], "reviewer": r[2], "reason": r[3],
                       "at": _iso(r[4])} for r in cur.fetchall()}
        items = []
        for m in json.loads(d["selected_json"]):
            items.append({"record": m, "review": revs.get(m),
                          "state": "answered" if m in revs else "outstanding"})
        return {"draw_id": did, "period": d["period"],
                "pool_digest": d["pool_digest"], "pool_size": d["pool_size"],
                "rate": d["rate"], "selected_count": d["select_count"],
                "beacon": {"source": d["beacon_source"], "round": d["beacon_round"],
                           "value": d["beacon_value"],
                           "sealed_at_block": d["beacon_rowid"]},
                "seed": d["seed"], "drawn_at": _iso(d["drawn_at"]),
                "items": items,
                "what_this_proves": WHAT_THIS_PROVES,
                "recompute": "/x/sortition/verify?id=%s" % did}, 200

    # -------------------------------------------------- verify
    if method == "GET" and action == "verify":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT members FROM sortition_pool WHERE id=?", (d["pool_id"],))
        row = cur.fetchone()
        members = json.loads(row[0]) if row else []
        recomputed_digest = _pool_digest(members)
        recomputed_seed = _seed(d["period"], d["pool_digest"], d["beacon_value"])
        recomputed = select(members, recomputed_seed, d["select_count"])
        stored = json.loads(d["selected_json"])
        ok = (recomputed_digest == d["pool_digest"]
              and recomputed_seed == d["seed"]
              and sorted(recomputed) == sorted(stored))
        return {
            "draw_id": did,
            "matches": ok,
            "pool_digest_recomputed": recomputed_digest,
            "pool_digest_sealed": d["pool_digest"],
            "seed_recomputed": recomputed_seed,
            "seed_sealed": d["seed"],
            "selection_matches": sorted(recomputed) == sorted(stored),
            "beacon_value": d["beacon_value"],
            "beacon_check": ("Confirm this value independently at "
                             "/x/heartbeat/verify?round=%s, then at the beacon "
                             "operator's own endpoint." % d["beacon_round"]),
            "do_it_without_us": {
                "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
                "rank": 'SHA256(seed + ":" + record_hash)',
                "select": "lowest k ranks, ascending",
                "note": ("This route runs the same function on our server, so "
                         "it is a convenience, not the proof. The proof is you "
                         "running those three lines yourself."),
            },
        }, 200

    # -------------------------------------------------- outstanding
    if method == "GET" and action == "outstanding":
        now = time.time()
        cur = conn.cursor()
        cur.execute("SELECT id, period, selected, drawn_at FROM sortition_draw"
                    " ORDER BY id DESC")
        items = []
        for did, period, sel, drawn in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT record_hash FROM sortition_review WHERE draw_id=?", (did,))
            done = {r[0] for r in cur2.fetchall()}
            due = drawn + REVIEW_DUE_HOURS * 3600
            for m in json.loads(sel):
                if m in done:
                    continue
                items.append({
                    "draw_id": did, "period": period, "record": m,
                    "drawn_at": _iso(drawn), "due": _iso(due),
                    "state": "gap" if now > due else "outstanding",
                    "late_by": _human(now - due) if now > due else None,
                })
        gaps = [i for i in items if i["state"] == "gap"]
        return {"outstanding_count": len(items), "gap_count": len(gaps),
                "due_after_hours": REVIEW_DUE_HOURS,
                "items": items[:500],
                "meaning": VOCABULARY["gap"]}, 200

    # -------------------------------------------------- status
    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(select_count) FROM sortition_draw")
        ndraws, nsel = cur.fetchone()
        nsel = nsel or 0
        cur.execute("SELECT COUNT(*) FROM sortition_review")
        nrev = cur.fetchone()[0]
        cur.execute("SELECT outcome, COUNT(*) FROM sortition_review GROUP BY outcome")
        mix = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM sortition_pool")
        npool = cur.fetchone()[0]
        beats = _beats_available(conn)
        return {
            "version": VERSION,
            "pools_committed": npool,
            "draws": ndraws,
            "records_selected": nsel,
            "reviews_recorded": nrev,
            "response_rate": round(nrev / nsel, 4) if nsel else None,
            "outcome_mix": mix,
            "beacon_available": beats is not None,
            "beats_in_system": beats,
            "depends_on": {
                "heartbeat": ("supplies the dice. Without a beacon sealed "
                              "after the pool, no draw is possible."),
                "complete": ("commits the period's record count in advance. "
                             "Without it, a record could be kept out of the "
                             "pool. Separate module, separate check: "
                             "/x/complete/periods"),
            },
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "draws", "draw", "verify", "outstanding",
                        "status", "pool", "review"]}, 404


def _draw_row(conn, did):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, period, pool_id, pool_digest, pool_size, rate, select_count,"
        " beacon_source, beacon_round, beacon_value, beacon_rowid, seed,"
        " selected, drawn_at FROM sortition_draw WHERE id=?", (did,))
    r = cur.fetchone()
    if not r:
        return None
    keys = ["id", "period", "pool_id", "pool_digest", "pool_size", "rate",
            "select_count", "beacon_source", "beacon_round", "beacon_value",
            "beacon_rowid", "seed", "selected_json", "drawn_at"]
    return dict(zip(keys, r))


def _spec():
    return {
        "module": "sortition",
        "version": VERSION,
        "name_means": "selection by lot - the ancient method for stopping the powerful choosing who gets scrutinised",
        "the_hole": (
            "Every system claiming human oversight reviews a sample. In every "
            "one, the operator picks the sample, so the sample proves nothing."
        ),
        "the_three_locks": [
            "1. The pool of eligible records is fixed and sealed first.",
            "2. The draw may only use a beacon value sealed AFTER the pool. "
            "Refused otherwise. So the pool was fixed before the dice existed.",
            "3. The beacon value ranks the pool. Lowest k are selected. "
            "Anyone recomputes it from public values.",
        ],
        "selection_function": {
            "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
            "rank": 'SHA256(seed + ":" + record_hash)',
            "select": "the k lowest ranks in ascending order",
            "why_no_rng": ("A random number generator is a library, a version "
                           "and a seed we control. Two SHA-256 calls are none "
                           "of those and run in any language."),
        },
        "uniform_only": (
            "Risk-weighted sampling is deliberately not offered. A weighting "
            "the operator sets is a choice the operator made, which is the "
            "thing this module exists to remove."
        ),
        "refusal": (
            "A reviewer may refuse a selected case, with a reason, sealed. "
            "An honest refusal on the record beats a silent gap. A selection "
            "left unanswered past the due window is published as a gap with "
            "the record named."
        ),
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It does not prove the reviews were any good.",
            "It does not force anyone to draw at all. A period with no draw "
            "is a period with no sample and status says so.",
            "Pool membership is asserted by this server; completeness of the "
            "pool is complete.py's job, not this module's.",
            "The beacon is a third party. If drand and Bitcoin both vanish, "
            "new draws stop. Old draws stay verifiable.",
        ],
        "routes": {
            "POST /x/sortition/pool": "keyed - commit the pool for a closed period",
            "POST /x/sortition/draw": "keyed - draw against a beacon sealed after the pool",
            "POST /x/sortition/review": "keyed - file a review or a refusal with a reason",
            "GET /x/sortition/draws": "every draw",
            "GET /x/sortition/draw?id=": "one draw and its answers",
            "GET /x/sortition/verify?id=": "recompute the draw",
            "GET /x/sortition/outstanding": "selected and unanswered, with gaps named",
            "GET /x/sortition/status": "coverage and response rate",
        },
    }

```


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
