# Codebase — part 10 of 34

Contains:
- `modules/peer.py`
- `modules/peerconsole.py`
- `modules/praxis.py`


## `modules/peer.py`

1303 lines, 58656 bytes

```python
"""
modules/peer.py  v1.4.0  --  signed peer submission (shared secret)

WHAT CHANGED IN 1.2.1 -- THE ACTUAL FAULT
    Every seal from this module had always failed, from the day it was
    written. Not intermittently. Every call, every action.

    server.py's seal() writes the row with event["user_id"] -- a direct key
    lookup, not a .get(). This module's events never carried a user_id, so
    the insert raised KeyError every time. witness.py passes
    "user_id": "wit:<peer>" and seals fine, which is why the hourly witness
    traffic worked either side of a peer submission that did not.

    Found by comparing the two modules' event shapes against seal() after
    four consecutive failures from praesidium / PRAXIS on 2026-08-26. The
    1.2 change is what made it findable: before that the KeyError was
    swallowed and reported as a successful receipt.

    Every event this module seals now carries "user_id": "peer:<peer_id>",
    following the same convention witness.py uses.

    Note what this means for history: peer registrations before this version
    were never sealed either. The credential exists in peer_registry and
    works, but there is no audit block for it. That gap is real and is not
    retro-fillable -- sealing it now would date it now.

WHAT CHANGED IN 1.2
    A failed seal no longer returns success.

    In 1.1 the call into the audit chain was wrapped in a bare exception
    handler that swallowed anything it threw. If sealing failed, the peer
    still got ok=true and accepted=true, with audit_hash, block_index and
    receipt_seq all null. The submission was counted in the registry and
    stored, but nothing entered the chain. From the peer's side it looked
    like a receipt. It was not one.

    That happened in the wild on 2026-08-26 to the first external peer to
    use this route (praesidium / PRAXIS). Found by checking the chain for
    a block at the submission timestamp and finding none. The peer's own
    verifier had already refused the receipt, which is the only reason it
    surfaced at all.

    Now: if the seal throws, or returns without an audit hash, submit
    returns 500 and says so. Nothing is recorded, the nonce stays unused,
    and the peer can resend the identical envelope once the underlying
    fault is fixed. The exception text is returned so the peer can tell
    the operator what actually broke.

    The three operator routes (register, rotate, suspend/resume) seal an
    audit note as a side effect. A failure there does not undo the
    operation, but it is no longer hidden: the response carries
    sealed=false and the exception text.

    Also in 1.2: the stored copy of the response is now written after any
    rotation warning is added, so the stored body is byte-identical to
    what the peer received. Peers that hash the response to prove they
    received it need that to hold.

READ THIS FIRST: WHAT THIS LANE BINDS, AND WHAT IT DOES NOT
    This lane authenticates with HMAC-SHA256 over a shared secret.

    A shared secret is held by BOTH parties. So a valid signature proves
    the submission came from someone holding that secret -- which is the
    peer, and also the operator of this deployment.

        It closes third-party submission under your name.
        It does NOT close operator submission under your name.

    That is a normal property of HMAC and not a defect. It is stated here,
    at the top, because "signed" reads stronger than it is, and a peer
    choosing between lanes should not have to work that out for
    themselves. Raised by Ishaan (Shango MID), who was right.

    If you need the operator excluded as well, use /x/signed/submit
    instead. There you generate an Ed25519 keypair, keep the private half,
    and this deployment holds only the public half -- so it can verify a
    signature and can never produce one. That property is arithmetic
    rather than a promise about our conduct.

    Both lanes stay open. This one is simpler to implement and costs the
    peer no key custody, which is a real advantage if a long-lived private
    key is a liability you would rather not carry. The other is stronger.
    Pick deliberately.

WHY THIS EXISTS
    /x/witness/observe is unauthenticated on purpose. Anyone can submit a
    tip without an account, and that openness is what answers the
    collusion objection -- nobody has to trust us to audit the network.

    The cost of that openness is that anyone can submit a tip under any
    name. Name binding catches most of it; it does not prevent it.

    A named peer exchanging period roots wants a stronger guarantee than
    the open endpoint gives. This module provides one WITHOUT changing the
    open endpoint. All three run side by side.

WHAT IT COVERS
    canonicalization, HMAC-SHA256 signing, nonce, replay window, clock
    skew, idempotency, retry semantics, suspension, key rotation with
    overlap, and honest reporting of seal failure.

AUTH LIVES IN THE BODY, NOT IN HEADERS
    The module router hands modules a parsed body, not the raw headers,
    so every authentication field travels in the JSON body. This also
    makes the scheme trivial to implement from any language and easy to
    replay in a test.

THE SCHEME, IN FULL
    Envelope:
        {
          "peer_id":         "prae-001",
          "ts":              1755432000,          integer unix seconds
          "nonce":           "<>=16 chars, unique per peer>",
          "idempotency_key": "<optional, <=128 chars>",
          "payload":         { ... the thing being submitted ... },
          "signature":       "<hex hmac-sha256>"
        }

    THOSE FIELDS AND NO OTHERS. The server rebuilds the envelope from the
    known field names before checking the signature, so any extra
    top-level field you signed will not be part of what we verify and the
    signature will not match. Put anything of your own inside payload.
    This trips people up and now it is written down.

    String to sign:
        "AILEASH-PEER-v1\\n" + canonical(envelope_without_signature)

    canonical() is exactly:
        json.dumps(obj, sort_keys=True, separators=(",",":"),
                   ensure_ascii=True)

    signature = hmac_sha256(secret, string_to_sign).hexdigest()

    POST /x/peer/canonical returns the exact string to sign for a given
    envelope, so an implementer can debug canonicalization without
    holding or revealing a secret.

WHAT COMES BACK ON ACCEPTANCE
    The full response shape, so a peer can pin a schema to it:

        ok                true
        accepted          true
        peer_id           string
        chain_name        string
        payload_digest    sha256 hex of canonical(payload)
        signed_with       "current" or "previous"
        auth              "hmac-shared-secret"
        auth_scope        the paragraph at the top of this file
        received_at       ISO 8601 Z, server clock at acceptance
        receipt           { audit_hash, block_index, receipt_seq }
        verify            { inclusion, ancestry, append_only }
        warning           present only when signed_with is "previous"
        replayed          present only on an idempotent retry
        note              present only on an idempotent retry

    received_at is TOP LEVEL. It is a sibling of receipt, not a member
    of it. The receipt object contains exactly three fields. This is
    spelled out because pinning a schema against the wrong nesting is an
    easy mistake to make and the earlier spec did not say where the field
    lived.

    received_at is this server's clock at the moment of acceptance. It is
    not evidence of when anything happened. The audit_hash is.

RULES
    clock skew      +/- 300s. Outside that: 401 clock_skew.
    nonce           unique per peer for 900s. Reused: 409 replay.
    idempotency     same key + same payload digest returns the FIRST
                    response verbatim, sealed once. Same key + different
                    payload: 409 idempotency_conflict.
    retry           safe. Retry the identical envelope; idempotency makes
                    it a no-op that returns the original receipt.
    suspension      403 peer_suspended. Submissions refused, nothing
                    deleted, the peer's history stands.
    rotation        two secrets live at once. A new secret is issued and
                    the previous one stays valid for ROTATION_OVERLAP
                    (default 24h) so a peer can roll without downtime.

                    Note the asymmetry with the other lane: here the
                    OPERATOR issues and rotates the secret, because the
                    operator holds it too. At /x/signed/rotate the peer
                    rotates their own key and the operator cannot, because
                    a rotation must be signed by the key being replaced.

    seal failure    500 seal_failed or 500 seal_incomplete. Nothing is
                    recorded and no receipt is issued. A receipt that
                    cannot be verified is worse than no receipt, so this
                    lane refuses to issue one.

ROUTES
    GET  spec       public   full implementation guide
    POST canonical  public   the exact string to sign. no secret needed.
    GET  peers      public   peer ids, status, rotation state. no secrets.
    POST submit     public route, SIGNATURE authenticated
    POST register   keyed    operator issues a peer credential
    POST rotate     keyed    issue a new secret, overlap the old
    POST suspend    keyed
    POST resume     keyed
    GET  history    keyed    submissions by peer, with stored response

TABLES OWNED
    peer_registry, peer_nonce, peer_submission
"""

import hashlib
import hmac
import json
import os
import re
import time

VERSION = "1.4.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "schema"),
    ("POST", "canonical"),
    ("GET", "peers"),
    ("POST", "submit"),
}

SIGN_PREFIX = "AILEASH-PEER-v1\n"

CLOCK_SKEW_SECONDS = 300
NONCE_TTL_SECONDS = 900
NONCE_MIN_LENGTH = 16
ROTATION_OVERLAP_SECONDS = 86400
MAX_PAYLOAD_BYTES = 65536
MAX_IDEMPOTENCY_KEY = 128

# The one paragraph that must appear anywhere this lane describes itself.
# Kept as a constant so it cannot drift between the spec route, the
# register response and the peers listing.
SHARED_SECRET_SCOPE = (
    "This lane authenticates with a shared secret, held by both the peer "
    "and the operator of this deployment. A valid signature proves the "
    "submission came from a holder of that secret. It closes third-party "
    "submission under your name and it does not close operator submission "
    "under your name. That is a normal property of HMAC, stated rather "
    "than implied. For a lane where the operator is excluded too, use "
    "/x/signed/submit - you keep the private key and we hold only the "
    "public half, so we can verify a signature and can never produce one."
)

_PEER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")

_ready = False


# ---------------------------------------------------------------- storage

def _setup(ctx):
    global _ready
    if _ready:
        return
    conn = ctx["conn"]
    with ctx["lock"]:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_registry (
                peer_id          TEXT PRIMARY KEY,
                chain_name       TEXT,
                url              TEXT,
                secret_current   TEXT,
                secret_previous  TEXT,
                rotated_at       REAL,
                status           TEXT DEFAULT 'active',
                created          REAL,
                submissions      INTEGER DEFAULT 0,
                last_seen        REAL,
                seq              INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_nonce (
                peer_id   TEXT,
                nonce     TEXT,
                seen_at   REAL,
                PRIMARY KEY (peer_id, nonce)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_submission (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id          TEXT,
                ts               REAL,
                idempotency_key  TEXT,
                payload_digest   TEXT,
                response_json    TEXT,
                audit_hash       TEXT
            )
        """)
        # Added in 1.3.0. Existing rows get NULL, read as 0 by
        # COALESCE, so the first submission after upgrading is seq 1.
        have = set()
        try:
            for r in conn.execute("PRAGMA table_info(peer_registry)").fetchall():
                have.add(r[1])
        except Exception:
            pass
        if "seq" not in have:
            try:
                conn.execute("ALTER TABLE peer_registry ADD COLUMN seq INTEGER DEFAULT 0")
            except Exception:
                pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_sub_idem "
            "ON peer_submission(peer_id, idempotency_key)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_nonce_time "
            "ON peer_nonce(seen_at)")
        conn.commit()
    _ready = True


# ------------------------------------------------------------ primitives

def canonical(obj):
    """
    THE canonicalization. Any implementation in any language must produce
    this byte-for-byte. Sorted keys, no whitespace, ASCII-escaped.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def string_to_sign(envelope):
    """Envelope WITHOUT the signature field, prefixed and canonicalized."""
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    return SIGN_PREFIX + canonical(unsigned)


def sign(secret, envelope):
    return hmac.new(secret.encode("utf-8"),
                    string_to_sign(envelope).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _digest(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _new_secret():
    return os.urandom(32).hex()


def _now():
    return time.time()


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _describe_exception(exc):
    """
    Short, safe description of what went wrong. Type and message only --
    no traceback, no local variables, nothing that leaks a secret. The
    peer needs enough to tell us what broke; they do not need our stack.
    """
    text = str(exc) or "(no message)"
    return "%s: %s" % (type(exc).__name__, text[:400])


def _sweep_nonces(ctx):
    cutoff = _now() - NONCE_TTL_SECONDS
    with ctx["lock"]:
        ctx["conn"].execute("DELETE FROM peer_nonce WHERE seen_at < ?",
                            (cutoff,))
        ctx["conn"].commit()


def _try_seal(ctx, event, result, when):
    """
    Seal, and say plainly whether it worked.

    Returns (audit_hash, block_index, receipt_seq, error) where error is
    None on success and a short string on failure. Nothing here swallows
    a failure silently. That was the 1.1 bug and it is the whole point of
    this version.
    """
    try:
        audit_hash, block_index, receipt_seq = ctx["seal"](
            event, result, when, None)
    except Exception as exc:
        return None, None, None, _describe_exception(exc)

    if not audit_hash:
        return None, None, None, ("seal returned no audit hash")

    return audit_hash, block_index, receipt_seq, None


# ------------------------------------------------------------ the submit

def _submit(ctx, data):
    """
    Signature-authenticated. No API key. Every rule on the list is
    enforced here, in a fixed order, and each failure names itself.
    """
    _setup(ctx)

    # ---- shape
    peer_id = (data.get("peer_id") or "").strip()
    signature = (data.get("signature") or "").strip()
    nonce = (data.get("nonce") or "").strip()
    payload = data.get("payload")
    idem = (data.get("idempotency_key") or "").strip()[:MAX_IDEMPOTENCY_KEY]

    if not peer_id or not signature or not nonce or payload is None:
        return {"ok": False, "error": "malformed_envelope",
                "required": ["peer_id", "ts", "nonce", "payload",
                             "signature"]}, 400

    try:
        ts = int(data.get("ts"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "malformed_ts",
                "detail": "ts must be an integer of unix seconds"}, 400

    if len(nonce) < NONCE_MIN_LENGTH:
        return {"ok": False, "error": "nonce_too_short",
                "minimum": NONCE_MIN_LENGTH}, 400

    if len(canonical(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return {"ok": False, "error": "payload_too_large",
                "max_bytes": MAX_PAYLOAD_BYTES}, 413

    # ---- peer known and active
    row = ctx["conn"].execute(
        "SELECT peer_id, chain_name, secret_current, secret_previous, "
        "rotated_at, status FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer", "peer_id": peer_id}, 401
    if row[5] == "suspended":
        return {"ok": False, "error": "peer_suspended",
                "detail": "Submissions refused. Existing history stands "
                          "and nothing has been removed."}, 403

    # ---- clock skew, before any expensive work
    skew = abs(_now() - ts)
    if skew > CLOCK_SKEW_SECONDS:
        return {"ok": False, "error": "clock_skew",
                "detail": "Timestamp is %.0fs from server time; the window "
                          "is +/-%ds." % (skew, CLOCK_SKEW_SECONDS),
                "server_time": int(_now())}, 401

    # ---- signature, against current then previous secret
    #
    # Note the envelope is rebuilt from KNOWN field names only. Any extra
    # top-level field the caller signed is not part of what we verify, so
    # the signature will not match. Documented in the spec; the failure
    # response points at /x/peer/canonical, which is the fastest way for
    # an implementer to see the difference.
    envelope = {"peer_id": peer_id, "ts": ts, "nonce": nonce,
                "payload": payload}
    if idem:
        envelope["idempotency_key"] = idem

    accepted_with = None
    if row[2] and hmac.compare_digest(sign(row[2], envelope), signature):
        accepted_with = "current"
    elif row[3] and (row[4] or 0) + ROTATION_OVERLAP_SECONDS > _now():
        if hmac.compare_digest(sign(row[3], envelope), signature):
            accepted_with = "previous"

    if not accepted_with:
        return {"ok": False, "error": "bad_signature",
                "detail": "HMAC did not match. POST the same envelope to "
                          "/x/peer/canonical to see the exact string this "
                          "server signs.",
                "common_cause": "An extra top-level field in your envelope. "
                                "Only peer_id, ts, nonce, payload and "
                                "idempotency_key are signed; anything else "
                                "belongs inside payload.",
                "string_to_sign_sha256":
                    hashlib.sha256(
                        string_to_sign(envelope).encode()).hexdigest(),
                }, 401

    payload_digest = _digest(payload)

    # ---- idempotency, before the nonce check so a retry is a clean no-op
    if idem:
        prior = ctx["conn"].execute(
            "SELECT payload_digest, response_json FROM peer_submission "
            "WHERE peer_id = ? AND idempotency_key = ?",
            (peer_id, idem)).fetchone()
        if prior:
            if prior[0] != payload_digest:
                return {"ok": False, "error": "idempotency_conflict",
                        "detail": "That idempotency key was used with a "
                                  "different payload."}, 409
            out = json.loads(prior[1])
            out["replayed"] = True
            out["note"] = ("Idempotent retry. This is the original receipt; "
                           "nothing was sealed twice.")
            return out, 200

    # ---- replay
    _sweep_nonces(ctx)
    seen = ctx["conn"].execute(
        "SELECT seen_at FROM peer_nonce WHERE peer_id = ? AND nonce = ?",
        (peer_id, nonce)).fetchone()
    if seen:
        return {"ok": False, "error": "replay",
                "detail": "That nonce has already been used by this peer "
                          "within the %ds window. Use a fresh nonce, or "
                          "send an idempotency_key if you meant to retry."
                          % NONCE_TTL_SECONDS}, 409

    # ---- seal it FIRST, and only claim success if it actually sealed
    #
    # This ordering is deliberate. Before 1.2 the response was built and
    # returned whether or not the seal worked, with null receipt fields
    # and ok=true. A peer had no way to tell a real receipt from an empty
    # one without going and looking at the chain. Now nothing is recorded
    # and nothing is claimed unless there is an audit hash to point at.
    now = _now()
    event = {"user_id": "peer:" + peer_id,
             "module": "peer", "action": "submit", "peer_id": peer_id,
             "chain_name": row[1], "payload_digest": payload_digest,
             "payload": payload}
    result = {"accepted": True, "signed_with": accepted_with,
              "auth": "hmac-shared-secret"}

    audit_hash, block_index, receipt_seq, seal_error = _try_seal(
        ctx, event, result, now)

    if seal_error:
        return {
            "ok": False,
            "accepted": False,
            "error": "seal_failed",
            "detail": "Your envelope verified correctly, but the audit "
                      "chain did not seal it, so there is no receipt to "
                      "give you. This is a fault on this deployment and "
                      "not a problem with your submission.",
            "seal_error": seal_error,
            "recorded": False,
            "retry": "Nothing was written. Your nonce is unused and your "
                     "idempotency key is free, so the identical envelope "
                     "can be resent once this is fixed.",
            "peer_id": peer_id,
            "payload_digest": payload_digest,
            "received_at": _iso(now),
        }, 500

    # ---- accepted and sealed. Issue the receipt sequence.
    #
    # New in 1.3.0. server.py's seal() only issues its sequence number
    # when an api_key is passed, because that counter lives on the key.
    # This lane authenticates by signature and holds no key, so seal()
    # returned None and the gapless property - the one that lets a peer
    # holding N and N+2 PROVE N+1 is missing - simply did not exist here.
    # Raised by Philip Pinol (PRAXIS) whose schema required an integer and
    # got a null. He was right to require it.
    #
    # So the sequence is issued here instead, per peer, from a counter on
    # peer_registry. It is incremented and read inside the SAME lock hold
    # that writes the submission row, so a number is never issued for a
    # submission that was not stored, and never skipped for one that was.
    #
    # Note the difference from the api_key sequence deliberately: that one
    # counts everything a key ever sealed across all modules. This one
    # counts what THIS peer submitted to THIS lane. Both are gapless
    # within their own scope and they are not comparable to each other.
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET seq = COALESCE(seq, 0) + 1 "
            "WHERE peer_id = ?", (peer_id,))
        srow = ctx["conn"].execute(
            "SELECT seq FROM peer_registry WHERE peer_id = ?",
            (peer_id,)).fetchone()
        peer_seq = int(srow[0]) if srow and srow[0] is not None else None

        out = {
            "ok": True,
            "accepted": True,
            "peer_id": peer_id,
            "chain_name": row[1],
            "payload_digest": payload_digest,
            "signed_with": accepted_with,
            "auth": "hmac-shared-secret",
            "auth_scope": SHARED_SECRET_SCOPE,
            "received_at": _iso(now),
            "receipt": {"audit_hash": audit_hash,
                        "block_index": block_index,
                        "receipt_seq": peer_seq,
                        "receipt_seq_scope": "per-peer",
                        "key_seq": receipt_seq},
            "verify": {
                "inclusion": "/x/complete/prove",
                "ancestry": "/x/consistency/ancestor?tip=<any tip we served>",
                "append_only": "/x/consistency/proof?first=&second=",
            },
            # Top level, not inside verify. In 1.3.0 this sat inside the
            # verify object, which the spec documented as exactly three
            # keys - so the response carried a fourth key the written shape
            # did not have. Philip Pinol (PRAXIS) caught it as
            # verify_format_invalid. It is a property of the sequence
            # rather than a route to call, so it never belonged in a map of
            # verification routes.
            "gapless": "receipt_seq increments by exactly one per accepted "
                       "submission from this peer. Two receipts numbered N "
                       "and N+2 prove a third exists and you did not "
                       "receive it. The current highest is published per "
                       "peer at /x/peer/peers.",
        }

        # Rotation warning is added BEFORE storing, so the stored copy is
        # byte-identical to what the peer receives. A peer that hashes the
        # response to prove what it got needs that to be true.
        if accepted_with == "previous":
            out["warning"] = ("Accepted with the previous secret. The "
                              "overlap window ends %s."
                              % _iso((row[4] or 0) +
                                     ROTATION_OVERLAP_SECONDS))

        ctx["conn"].execute(
            "INSERT OR IGNORE INTO peer_nonce (peer_id, nonce, seen_at) "
            "VALUES (?,?,?)", (peer_id, nonce, now))
        ctx["conn"].execute(
            "INSERT INTO peer_submission (peer_id, ts, idempotency_key, "
            "payload_digest, response_json, audit_hash) VALUES (?,?,?,?,?,?)",
            (peer_id, now, idem or None, payload_digest,
             json.dumps(out), audit_hash))
        ctx["conn"].execute(
            "UPDATE peer_registry SET submissions = submissions + 1, "
            "last_seen = ? WHERE peer_id = ?", (now, peer_id))
        ctx["conn"].commit()

    return out, 200


# ------------------------------------------------------------- operator

def _register(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not _PEER_ID_RE.match(peer_id):
        return {"ok": False, "error": "bad_peer_id",
                "detail": "lowercase letters, digits, dot, dash, "
                          "underscore; 2-63 chars"}, 400
    if ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                           (peer_id,)).fetchone():
        return {"ok": False, "error": "peer_exists",
                "detail": "Use /x/peer/rotate to issue a new secret."}, 409

    secret = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO peer_registry (peer_id, chain_name, url, "
            "secret_current, secret_previous, rotated_at, status, created) "
            "VALUES (?,?,?,?,NULL,NULL,'active',?)",
            (peer_id, (data.get("chain_name") or peer_id).strip()[:120],
             (data.get("url") or "").strip()[:400], secret, now))
        ctx["conn"].commit()

    audit_hash, _bi, _rs, seal_error = _try_seal(
        ctx, {"user_id": "peer:" + peer_id, "module": "peer",
              "action": "register", "peer_id": peer_id},
        {"registered": True}, now)

    out = {
        "ok": True,
        "peer_id": peer_id,
        "secret": secret,
        "warning": "This secret is shown once and is not recoverable. "
                   "Send it to the peer over a channel you trust.",
        "tell_the_peer_this": SHARED_SECRET_SCOPE,
        "endpoint": "/x/peer/submit",
        "spec": "/x/peer/spec",
        "stronger_lane": "/x/signed/spec",
        "sealed": seal_error is None,
        "audit_hash": audit_hash,
    }
    if seal_error:
        out["seal_error"] = seal_error
        out["seal_note"] = ("The credential was issued and is usable. The "
                            "audit note about issuing it did not seal. "
                            "That is a fault worth chasing, but it does "
                            "not affect the credential.")
    return out, 200


def _rotate(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    row = ctx["conn"].execute(
        "SELECT secret_current FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer"}, 404

    new = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET secret_previous = secret_current, "
            "secret_current = ?, rotated_at = ? WHERE peer_id = ?",
            (new, now, peer_id))
        ctx["conn"].commit()

    audit_hash, _bi, _rs, seal_error = _try_seal(
        ctx, {"user_id": "peer:" + peer_id, "module": "peer",
              "action": "rotate", "peer_id": peer_id},
        {"rotated": True}, now)

    out = {
        "ok": True,
        "peer_id": peer_id,
        "secret": new,
        "previous_valid_until": _iso(now + ROTATION_OVERLAP_SECONDS),
        "detail": "Both secrets are accepted until then, so the peer can "
                  "roll over without downtime. Submissions signed with the "
                  "old one come back marked.",
        "note": "The operator rotates this credential because the operator "
                "holds it. At /x/signed/rotate the peer rotates their own "
                "key and the operator cannot, because a rotation there must "
                "be signed by the key being replaced.",
        "sealed": seal_error is None,
        "audit_hash": audit_hash,
    }
    if seal_error:
        out["seal_error"] = seal_error
        out["seal_note"] = ("The rotation happened and the new secret is "
                            "live. The audit note about it did not seal.")
    return out, 200


def _set_status(ctx, data, status):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                               (peer_id,)).fetchone():
        return {"ok": False, "error": "unknown_peer"}, 404
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET status = ? WHERE peer_id = ?",
            (status, peer_id))
        ctx["conn"].commit()

    audit_hash, _bi, _rs, seal_error = _try_seal(
        ctx, {"user_id": "peer:" + peer_id, "module": "peer",
              "action": status, "peer_id": peer_id},
        {"status": status}, _now())

    out = {"ok": True, "peer_id": peer_id, "status": status,
           "sealed": seal_error is None, "audit_hash": audit_hash}
    if seal_error:
        out["seal_error"] = seal_error
        out["seal_note"] = ("The status change took effect. The audit note "
                            "about it did not seal.")
    return out, 200


def _peers(ctx):
    _setup(ctx)
    now = _now()
    rows = ctx["conn"].execute(
        "SELECT peer_id, chain_name, url, status, created, submissions, "
        "last_seen, rotated_at, seq FROM peer_registry ORDER BY created"
    ).fetchall()
    return {
        "ok": True,
        "count": len(rows),
        "auth": "hmac-shared-secret",
        "auth_scope": SHARED_SECRET_SCOPE,
        "peers": [{
            "peer_id": r[0], "chain_name": r[1], "url": r[2] or None,
            "status": r[3], "registered": _iso(r[4]),
            "submissions": r[5], "last_seen": _iso(r[6]) if r[6] else None,
            "rotation_overlap_active":
                bool(r[7] and r[7] + ROTATION_OVERLAP_SECONDS > now),
            "latest_receipt_seq": r[8] or 0,
        } for r in rows],
        "note": "Secrets are never returned by any route.",
        "receipt_seq_note":
            "latest_receipt_seq is the highest receipt number issued to "
            "that peer on this lane. A peer whose own highest receipt is "
            "lower than this has not received one of them, and can say "
            "exactly how many. Public on purpose - a gap you can only see "
            "from the inside is not evidence of anything.",
    }, 200


def _history(ctx, data):
    """
    Keyed. Now returns the stored response body as well as the summary.

    A peer that hashed the response it received can ask the operator to
    hash the stored copy and compare. Without the body on this route
    there is no way to settle a disagreement about what was sent, which
    came up the first time a peer's verifier disagreed with a receipt.

    Pass full=false to get the summary only.
    """
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    full = data.get("full", True)
    if isinstance(full, str):
        full = full.strip().lower() not in ("0", "false", "no")
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50

    q = ("SELECT peer_id, ts, idempotency_key, payload_digest, audit_hash, "
         "response_json FROM peer_submission")
    args = []
    if peer_id:
        q += " WHERE peer_id = ?"
        args.append(peer_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = ctx["conn"].execute(q, args).fetchall()

    subs = []
    for r in rows:
        item = {
            "peer_id": r[0], "at": _iso(r[1]), "idempotency_key": r[2],
            "payload_digest": r[3], "audit_hash": r[4],
            "sealed": bool(r[4]),
        }
        body = r[5]
        if body:
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = None
            if parsed is not None:
                item["response_digest"] = hashlib.sha256(
                    canonical(parsed).encode("ascii")).hexdigest()
                if full:
                    item["response"] = parsed
        subs.append(item)

    return {
        "ok": True, "count": len(subs),
        "response_digest_recipe":
            "sha256(json.dumps(response, sort_keys=True, "
            "separators=(\",\",\":\"), ensure_ascii=True).encode(\"ascii\"))",
        "note": "response_digest is over the stored copy of exactly what "
                "was returned to the peer. A peer that hashed what it "
                "received the same way can compare directly.",
        "submissions": subs,
    }, 200


def _canonical_route(data):
    """
    Debugging aid. Give it an envelope, get back the exact string this
    server will sign. Reveals nothing -- the secret is not involved.
    """
    env = dict(data or {})
    env.pop("signature", None)
    if "ts" in env:
        try:
            env["ts"] = int(env["ts"])
        except (TypeError, ValueError):
            return {"ok": False, "error": "malformed_ts"}, 400
    s = string_to_sign(env)
    known = {"peer_id", "ts", "nonce", "payload", "idempotency_key"}
    extra = sorted(k for k in env if k not in known)
    out = {
        "ok": True,
        "string_to_sign": s,
        "sha256": hashlib.sha256(s.encode("utf-8")).hexdigest(),
        "byte_length": len(s.encode("utf-8")),
        "recipe": "\"AILEASH-PEER-v1\\n\" + json.dumps(envelope_without_"
                  "signature, sort_keys=True, separators=(\",\",\":\"), "
                  "ensure_ascii=True)",
        "then": "signature = hmac_sha256(secret, string_to_sign).hexdigest()",
    }
    if extra:
        out["warning"] = (
            "This route echoes whatever you sent, but /x/peer/submit "
            "rebuilds the envelope from known fields only. These extra "
            "top-level fields would NOT be part of what submit verifies, "
            "so a signature over the string above would be rejected: %s. "
            "Move them inside payload." % ", ".join(extra))
    return out, 200


# ------------------------------------------------------------------ spec

def _spec():
    return {
        "module": "peer",
        "version": VERSION,
        "auth": "hmac-shared-secret",
        "read_this_first": SHARED_SECRET_SCOPE,
        "purpose":
            "Signed submission for named peers. Sits beside the open "
            "/x/witness/observe endpoint rather than replacing it. The "
            "open endpoint stays unauthenticated so anyone can audit the "
            "network without an account; this one guarantees that only a "
            "holder of the peer secret can submit as that chain -- noting "
            "that the operator is also a holder.",
        "choosing_a_lane": {
            "/x/witness/observe": "Open. No credential. Anyone can submit "
                                  "under any name; the record says how "
                                  "strong the claim is rather than "
                                  "refusing it.",
            "/x/peer/submit": "This lane. Shared secret. Excludes third "
                              "parties, does not exclude the operator. No "
                              "key custody burden on the peer.",
            "/x/signed/submit": "Ed25519. The peer holds the private key "
                                "and this deployment holds only the public "
                                "half, so the operator is excluded too. "
                                "Strongest, at the cost of the peer "
                                "carrying a long-lived private key.",
        },
        "envelope": {
            "peer_id": "string, issued at registration",
            "ts": "integer unix seconds",
            "nonce": "string, at least %d chars, unique per peer for %ds"
                     % (NONCE_MIN_LENGTH, NONCE_TTL_SECONDS),
            "idempotency_key": "optional string, max %d chars"
                               % MAX_IDEMPOTENCY_KEY,
            "payload": "object. period roots, tips, whatever is agreed. "
                       "max %d bytes canonicalized." % MAX_PAYLOAD_BYTES,
            "signature": "hex hmac-sha256",
            "no_other_top_level_fields":
                "The server rebuilds the envelope from exactly the field "
                "names above before verifying. Any extra top-level field "
                "you signed is not part of what we verify and your "
                "signature will not match. Put your own data inside "
                "payload.",
        },
        "canonicalization": {
            "recipe": "json.dumps(obj, sort_keys=True, "
                      "separators=(\",\",\":\"), ensure_ascii=True)",
            "string_to_sign": "\"AILEASH-PEER-v1\\n\" + canonical(envelope "
                              "with the signature field removed)",
            "signature": "hmac_sha256(secret, string_to_sign).hexdigest()",
            "debug": "POST the envelope to /x/peer/canonical to get the "
                     "exact string back. No secret required.",
        },
        "rules": {
            "clock_skew": "+/-%ds. Outside: 401 clock_skew, with the "
                          "server's time in the body."
                          % CLOCK_SKEW_SECONDS,
            "replay": "A nonce is single-use per peer for %ds. Reused: "
                      "409 replay." % NONCE_TTL_SECONDS,
            "idempotency": "Same idempotency_key and same payload returns "
                           "the original receipt verbatim with "
                           "replayed=true; nothing is sealed twice. Same "
                           "key with a different payload: 409 "
                           "idempotency_conflict.",
            "retry": "Retry the identical envelope. With an "
                     "idempotency_key that is a safe no-op. Without one, "
                     "a retry inside the nonce window returns 409 replay "
                     "-- so send an idempotency_key if you intend to "
                     "retry at all.",
            "suspension": "403 peer_suspended. Nothing is deleted and the "
                          "peer's sealed history stands.",
            "rotation": "A new secret is issued and the previous one stays "
                        "valid for %ds. Submissions accepted on the old "
                        "secret come back with signed_with=previous and a "
                        "warning naming the cutoff. The operator performs "
                        "the rotation, because the operator holds the "
                        "secret."
                        % ROTATION_OVERLAP_SECONDS,
            "seal_failure":
                "If the audit chain does not seal your submission, you get "
                "500 seal_failed with the reason, and nothing is recorded "
                "-- no nonce, no counter, no receipt. Resend the identical "
                "envelope once the fault is fixed. A receipt you cannot "
                "verify is worse than no receipt, so this lane will not "
                "issue one.",
        },
        "on_acceptance": {
            "summary":
                "The payload is sealed into the audit chain and you get a "
                "receipt. Verify independently: inclusion at "
                "/x/complete/prove, ancestry at /x/consistency/ancestor, "
                "append-only at /x/consistency/proof. Both offline "
                "verifiers (aileash_verify.py, verify_authority.py) are "
                "stdlib only and touch no network.",
            "response_shape": {
                "ok": "true",
                "accepted": "true",
                "peer_id": "string",
                "chain_name": "string",
                "payload_digest": "sha256 hex of canonical(payload)",
                "signed_with": "current | previous",
                "auth": "hmac-shared-secret",
                "auth_scope": "the shared-secret paragraph",
                "received_at": "ISO 8601 Z. TOP LEVEL, beside receipt, "
                               "not inside it.",
                "receipt": "{ audit_hash, block_index, receipt_seq, "
                           "receipt_seq_scope, key_seq }",
                "verify": "{ inclusion, ancestry, append_only } "
                          "-- exactly these three keys",
                "gapless": "string. TOP LEVEL, not inside verify.",
                "warning": "present only when signed_with is previous",
                "replayed": "present only on an idempotent retry",
                "note": "present only on an idempotent retry",
            },
            "where_received_at_lives":
                "Top level. It is a sibling of receipt, not a member of "
                "it. The receipt object holds three fields and no others. "
                "Pin your schema accordingly -- the earlier version of "
                "this document listed the three receipt fields without "
                "saying where received_at sat, and a peer reasonably "
                "pinned it in the wrong place.",
            "receipt_seq":
                "An integer, never null, incremented by exactly one for "
                "each accepted submission FROM THIS PEER on this lane. "
                "Issued inside the same lock that writes the record, so a "
                "number is never spent on a submission that was not "
                "stored. Two receipts numbered N and N+2 prove a third "
                "exists that you did not receive. The current highest is "
                "published per peer at /x/peer/peers, so the check does "
                "not depend on asking us.",
            "receipt_seq_scope": {'values': ['per-peer', 'per-name', 'per-chain'], 'per-peer': 'issued per registered peer_id. Used by /x/peer/submit.', 'per-name': 'issued per bound name. Used by /x/bind/submit.', 'per-chain': 'issued per enrolled chain name. Used by /x/signed/submit.', 'why_it_is_here': 'The three signed lanes each count within their own scope, so a receipt carries the scope of its own sequence rather than requiring the holder to remember which lane produced it. The set is closed: a value outside this list is an error on our side, not a new scope you should widen a schema for.', 'not_comparable_across_scopes': 'Two receipts with different scopes are counting different things and their numbers say nothing about each other.'},
            "key_seq":
                "The server-wide per-API-key sequence, which is null on "
                "this lane and always will be. That counter lives on an "
                "api_key and this lane authenticates by signature with no "
                "key to count against. It is returned rather than omitted "
                "so the absence is visible instead of inferred. Before "
                "1.3.0 this null was reported as receipt_seq, which made "
                "a missing property look like a broken field. Raised by "
                "Philip Pinol (PRAXIS), correctly.",
            "what_received_at_is":
                "This server's clock at the moment of acceptance. It is "
                "not evidence of when anything happened and should not be "
                "relied on as such. The audit_hash is the evidence.",
            "proving_what_you_received":
                "The full response body is stored server side. A peer who "
                "hashes the response with sha256 over "
                "json.dumps(response, sort_keys=True, separators=(\",\","
                "\":\"), ensure_ascii=True) can ask the operator to "
                "compare against the stored copy via GET history.",
        },
        "routes": {
            "GET spec": "public. this document.",
            "GET schema": "public. the same response shape as a JSON Schema "
                          "a validator can load directly, so nobody has to "
                          "transcribe prose into rules.",
            "POST canonical": "public. the exact string to sign.",
            "GET peers": "public. peer ids and status. never secrets.",
            "POST submit": "signature authenticated. no API key.",
            "POST register": "keyed. operator issues a credential.",
            "POST rotate": "keyed. new secret, old one overlaps.",
            "POST suspend / POST resume": "keyed.",
            "GET history": "keyed. submissions with the stored response "
                           "body and its digest. Pass full=false for the "
                           "summary only.",
        },
        "what_this_does_not_do": [
            "It does not exclude the operator of this deployment. A shared "
            "secret is held by both parties, so a valid signature means a "
            "holder of the secret submitted - which is you and also us. "
            "Use /x/signed/submit if that matters to you.",
            "It does not make a submitted root true. It proves who "
            "submitted it and when, and that it has not changed since.",
            "It does not replace /x/witness/observe. Peers who prefer the "
            "open path keep using it and lose nothing.",
            "A shared secret authenticates a channel, not a person. If "
            "the secret leaks, rotate it.",
        ],
        "worked_example": {
            "envelope_before_signing": {
                "peer_id": "example-001",
                "ts": 1755432000,
                "nonce": "0123456789abcdef",
                "payload": {"period": "2026-Q3", "root": "ab12...", "count": 4096},
            },
            "note": "POST exactly that to /x/peer/canonical and you will "
                    "get the string to sign, so you can confirm your "
                    "implementation before you hold a secret.",
        },
        "machine_readable_schema": "/x/peer/schema",
        "changed_in_1_4_0": [
            "Added GET /x/peer/schema - the accepted-response shape as a "
            "JSON Schema, additionalProperties false throughout, loadable "
            "straight into a validator. Every failure this lane had in its "
            "first week came from a peer transcribing a written description "
            "into a closed schema and the two disagreeing. This removes the "
            "transcription step.",
        ],
        "changed_in_1_3_2": [
            "gapless moved out of the verify object to the top level. In "
            "1.3.0 and 1.3.1 verify carried four keys while the spec "
            "documented three, so a closed schema pinned to the written "
            "shape refused a correct response. Caught by Philip Pinol "
            "(PRAXIS). verify now carries exactly inclusion, ancestry and "
            "append_only, as documented.",
            "auth_scope is unchanged and is 535 bytes of prose on one "
            "line. There is no published length limit on it and there "
            "never has been - if you have been told otherwise, that rule "
            "did not come from this spec.",
        ],
        "changed_in_1_3_1": [
            "receipt_seq_scope is now a bare token from a closed set - "
            "per-peer, per-name, per-chain - rather than a sentence. The "
            "set is published under on_acceptance.receipt_seq_scope so a "
            "closed schema can pin an enum rather than a bounded string. "
            "Asked for by Philip Pinol (PRAXIS). Value change only; the "
            "response shape is unchanged from 1.3.0.",
        ],
        "changed_in_1_3_0": [
            "receipt_seq is now a real per-peer gapless sequence issued by "
            "this module, not the api_key counter that was always null "
            "here. The completeness property applies to this lane for the "
            "first time.",
            "The api_key counter is still returned, as key_seq, and is "
            "null by design so the absence is stated rather than hidden.",
            "/x/peer/peers publishes latest_receipt_seq per peer, so a "
            "peer can detect a missing receipt without asking us.",
        ],
        "changed_in_1_2": [
            "A failed seal returns 500 instead of a receipt with null "
            "fields and ok=true. Found in production on 2026-08-26.",
            "Operator routes report sealed true/false rather than "
            "swallowing a seal failure.",
            "GET history returns the stored response body and its digest.",
            "The response shape is documented in full, including where "
            "received_at lives.",
        ],
    }



# ----------------------------------------------------------------------
# machine-readable schema
# ----------------------------------------------------------------------

# The three scopes any lane on this deployment can issue a sequence in.
# Referenced by the schema below AND by the spec prose, so the enum cannot
# say one thing in one place and another somewhere else.
SEQ_SCOPES = ("per-peer", "per-name", "per-chain")


def _schema():
    """JSON Schema for the accepted-submission response.

    WHY THIS EXISTS
        Every failure in this lane's first week was the same failure: a peer
        transcribing a written description into a closed schema, and the
        description and the bytes disagreeing. received_at in the wrong
        place. key_seq at the wrong level. receipt_seq_scope pinned as an
        identifier when it was prose. gapless inside verify when the prose
        said three keys.

        None of those were disagreements about behaviour. Every one was a
        human reading a paragraph and writing a rule from it. So the
        paragraph stops being the interface.

        This route returns a schema a validator loads directly. Nobody
        transcribes anything, and if the shape changes the schema changes
        with it rather than a sentence somewhere needing to be noticed.

    WHAT IT DOES NOT DO
        It does not make the shape correct - it makes the shape STATED in a
        form that cannot be misread. If this deployment returns something
        the schema forbids, that is a fault here and your validator should
        refuse it. That is the point.

        additionalProperties is false on every object on purpose. A schema
        that quietly tolerates unknown keys would have hidden the gapless
        mistake instead of catching it.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://sebbi.pro/x/peer/schema",
        "title": "AILEASH-PEER-v1 accepted submission response",
        "module_version": VERSION,
        "type": "object",
        "additionalProperties": False,
        "required": ["ok", "accepted", "peer_id", "chain_name",
                     "payload_digest", "signed_with", "auth", "auth_scope",
                     "received_at", "receipt", "verify", "gapless"],
        "properties": {
            "ok": {"const": True},
            "accepted": {"const": True},
            "peer_id": {"type": "string"},
            "chain_name": {"type": ["string", "null"]},
            "payload_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "signed_with": {"enum": ["current", "previous"]},
            "auth": {"const": "hmac-shared-secret"},
            "auth_scope": {
                "type": "string",
                "description": "Prose, not an identifier. The shared-secret "
                               "scope paragraph. No length limit is defined "
                               "and none should be assumed.",
            },
            "received_at": {
                "type": ["string", "null"],
                "description": "ISO 8601 Z, this server's clock at "
                               "acceptance. TOP LEVEL, beside receipt. Not "
                               "evidence of when anything happened.",
            },
            "receipt": {
                "type": "object",
                "additionalProperties": False,
                "required": ["audit_hash", "block_index", "receipt_seq",
                             "receipt_seq_scope", "key_seq"],
                "properties": {
                    "audit_hash": {"type": "string",
                                   "pattern": "^[0-9a-f]{64}$"},
                    "block_index": {"type": "integer"},
                    "receipt_seq": {"type": "integer", "minimum": 1},
                    "receipt_seq_scope": {"enum": list(SEQ_SCOPES)},
                    "key_seq": {
                        "type": "null",
                        "description": "Null on this lane and always will "
                                       "be. Returned so the absence is "
                                       "visible rather than inferred.",
                    },
                },
            },
            "verify": {
                "type": "object",
                "additionalProperties": False,
                "required": ["inclusion", "ancestry", "append_only"],
                "properties": {
                    "inclusion": {"type": "string"},
                    "ancestry": {"type": "string"},
                    "append_only": {"type": "string"},
                },
                "description": "Exactly three route hints. Strings, not "
                               "structured objects.",
            },
            "gapless": {"type": "string"},
            "warning": {
                "type": "string",
                "description": "Present ONLY when signed_with is previous.",
            },
            "replayed": {
                "const": True,
                "description": "Present ONLY on an idempotent retry.",
            },
            "note": {
                "type": "string",
                "description": "Present ONLY on an idempotent retry.",
            },
        },
        "conditional_fields": {
            "warning": "signed_with == previous",
            "replayed": "idempotent retry",
            "note": "idempotent retry",
        },
        "on_failure": {
            "note": "Failure responses are NOT covered by this schema. They "
                    "carry ok false with an error string, and a validator "
                    "should branch on the status code before validating.",
            "errors": ["malformed_envelope", "malformed_ts", "nonce_too_short",
                       "payload_too_large", "unknown_peer", "peer_suspended",
                       "clock_skew", "bad_signature", "idempotency_conflict",
                       "replay", "seal_failed"],
        },
        "how_to_use_it": (
            "Load this document into any JSON Schema validator and point it "
            "at the response body. Do not transcribe it into your own rules "
            "- transcription is what went wrong every time this lane broke."),
        "if_we_break_it": (
            "additionalProperties is false everywhere. If this deployment "
            "returns a key not listed here, your validator refuses it and "
            "that refusal is correct. Tell us; it is our fault, not a "
            "schema you should widen."),
    }, 200

# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if action == "spec":
        return _spec(), 200
    if action == "schema":
        return _schema()
    if action == "canonical":
        return _canonical_route(data)
    if action == "peers":
        return _peers(ctx)
    if action == "submit":
        return _submit(ctx, data)

    if not api_key:
        return {"ok": False, "error": "api_key_required"}, 401

    if action == "register":
        return _register(ctx, data)
    if action == "rotate":
        return _rotate(ctx, data)
    if action == "suspend":
        return _set_status(ctx, data, "suspended")
    if action == "resume":
        return _set_status(ctx, data, "active")
    if action == "history":
        return _history(ctx, data)

    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


## `modules/peerconsole.py`

376 lines, 15478 bytes

```python
"""
modules/peerconsole.py  v1.0  -  the peer credential page at /peers

Register a peer, rotate their secret, suspend them, see who is on.
Keyed POSTs a browser address bar cannot reach.

Own patch attribute so it composes with console.py and packconsole.py.
After a deploy, one /x/ request arms it: /x/peerconsole/status
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0"
PUBLIC = {("GET", "status")}
PAGE_PATHS = ("/peers", "/peers.html", "/peer-console")

_patched = [False]

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Peers — AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0f1e;--panel:#131b2e;--panel2:#1a2338;--edge:rgba(201,168,76,.22);
--gold:#c9a84c;--text:#f2efe6;--mute:rgba(242,239,230,.42);--ok:#7fe3b0;--err:#ff8a80;
--mono:'IBM Plex Mono',ui-monospace,monospace;--body:system-ui,-apple-system,sans-serif}
body{background:var(--ink);color:var(--text);font-family:var(--body);font-size:16px;
line-height:1.6;padding:0 0 60px}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}
header{padding:30px 0 20px;border-bottom:1px solid var(--edge);margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
text-transform:uppercase;color:var(--gold);margin-bottom:8px}
h1{font-size:34px;line-height:1;font-weight:800;letter-spacing:-.02em}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14px;margin-top:10px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--mute);margin-bottom:6px}
input{width:100%;background:var(--panel);border:1px solid var(--edge);color:var(--text);
font-family:var(--mono);font-size:13px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:var(--gold)}
.keybar{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
padding:16px;margin-bottom:24px}
.keynote{font-size:12px;color:var(--mute);margin-top:8px}
.op{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
margin-bottom:12px;overflow:hidden}
.op-head{display:flex;align-items:baseline;gap:10px;padding:15px 16px;cursor:pointer}
.op-head:hover{background:var(--panel2)}
.op-n{font-family:var(--mono);font-size:10px;color:var(--gold);opacity:.6}
.op-t{font-size:17px;font-weight:700}
.op-r{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--mute)}
.op-body{padding:0 16px 16px;display:none}
.op.open .op-body{display:block}
.op-why{font-size:13.5px;color:var(--mute);margin-bottom:14px}
.field{margin-bottom:12px}
button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;
padding:14px;font-weight:700;font-size:14.5px;cursor:pointer}
button:hover:not(:disabled){background:#dbbd63}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--edge)}
.two{display:flex;gap:10px}
.two button{flex:1}
#out{margin-top:24px}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.6;background:#080c16;
color:var(--ok);padding:14px;border-radius:5px;overflow-x:auto;
border:1px solid var(--edge);max-height:320px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;border-radius:5px;
border:1px solid var(--edge);color:var(--mute);margin-bottom:12px}
.msg.bad{color:var(--err);border-color:rgba(200,54,43,.5);background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);background:rgba(26,158,110,.08)}
.secret{background:#080c16;border:2px solid var(--gold);border-radius:6px;padding:18px;
margin-bottom:14px}
.secret .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.secret .val{font-family:var(--mono);font-size:13px;color:var(--text);word-break:break-all;
line-height:1.7;background:var(--panel);padding:12px;border-radius:4px}
.secret .warn{color:var(--err);font-size:13px;margin-top:12px}
.peer{padding:12px 0;border-bottom:1px solid var(--edge)}
.peer:last-child{border-bottom:none}
.peer .id{font-family:var(--mono);font-size:13.5px;color:var(--gold)}
.peer .meta{font-size:12.5px;color:var(--mute);margin-top:3px}
.pill{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 7px;
border-radius:3px;letter-spacing:.1em;text-transform:uppercase}
.pill.active{background:rgba(26,158,110,.18);color:var(--ok)}
.pill.suspended{background:rgba(200,54,43,.15);color:var(--err)}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--edge);
font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash · peer credentials</p>
  <h1>Signed <span>peers</span></h1>
  <p class="sub">The open endpoint stays open. This issues credentials to peers who need a guarantee that only they can submit as their chain.</p>
</header>

<div class="keybar">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_…" autocomplete="off" spellcheck="false">
  <p class="keynote">Held in this tab only. Close it and the key is gone.</p>
</div>

<div class="op open" id="op-reg">
  <div class="op-head" onclick="tog('op-reg')">
    <span class="op-n">01</span><span class="op-t">Register a peer</span>
    <span class="op-r">POST /x/peer/register</span>
  </div>
  <div class="op-body">
    <p class="op-why">Issues their secret. It is shown once here and never again — send it to them over a channel you trust, not the same email as everything else.</p>
    <div class="field">
      <label for="r-id">Peer id (lowercase, no spaces)</label>
      <input id="r-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-name">Chain name</label>
      <input id="r-name" placeholder="PRAXIS" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-url">Their public tip URL</label>
      <input id="r-url" placeholder="https://example.com/api/tip" autocomplete="off">
    </div>
    <button onclick="run('register')">Issue the credential</button>
  </div>
</div>

<div class="op" id="op-rot">
  <div class="op-head" onclick="tog('op-rot')">
    <span class="op-n">02</span><span class="op-t">Rotate a secret</span>
    <span class="op-r">POST /x/peer/rotate</span>
  </div>
  <div class="op-body">
    <p class="op-why">New secret now, old one keeps working for 24 hours so they can roll over without downtime.</p>
    <div class="field">
      <label for="o-id">Peer id</label>
      <input id="o-id" placeholder="praesidium" autocomplete="off">
    </div>
    <button onclick="run('rotate')">Rotate</button>
  </div>
</div>

<div class="op" id="op-sus">
  <div class="op-head" onclick="tog('op-sus')">
    <span class="op-n">03</span><span class="op-t">Suspend or resume</span>
    <span class="op-r">POST /x/peer/suspend</span>
  </div>
  <div class="op-body">
    <p class="op-why">Suspending refuses new submissions. Nothing is deleted and their sealed history stands.</p>
    <div class="field">
      <label for="s-id">Peer id</label>
      <input id="s-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="two">
      <button onclick="run('suspend')">Suspend</button>
      <button class="quiet" onclick="run('resume')">Resume</button>
    </div>
  </div>
</div>

<div class="op" id="op-list">
  <div class="op-head" onclick="tog('op-list')">
    <span class="op-n">04</span><span class="op-t">Who is registered</span>
    <span class="op-r">GET /x/peer/peers</span>
  </div>
  <div class="op-body">
    <p class="op-why">Public route. Secrets are never returned by anything.</p>
    <button class="quiet" onclick="run('peers')">List them</button>
  </div>
</div>

<div class="op" id="op-hist">
  <div class="op-head" onclick="tog('op-hist')">
    <span class="op-n">05</span><span class="op-t">Submissions</span>
    <span class="op-r">GET /x/peer/history</span>
  </div>
  <div class="op-body">
    <p class="op-why">What has come in, with the receipt for each. Leave the id blank for everything.</p>
    <div class="field">
      <label for="h-id">Peer id (optional)</label>
      <input id="h-id" placeholder="leave blank for all" autocomplete="off">
    </div>
    <button class="quiet" onclick="run('history')">Show them</button>
  </div>
</div>

<div id="out"></div>

<footer>
  Spec for peers to implement: <a href="/x/peer/spec">/x/peer/spec</a><br>
  Open endpoint, unchanged: <a href="/x/witness/peers">/x/witness/peers</a><br>
  Other consoles: <a href="/console">/console</a> · <a href="/pack">/pack</a>
</footer>

</div>

<script>
(function(){
  var out=document.getElementById('out'), busy=false;
  window.tog=function(id){document.getElementById(id).classList.toggle('open');};
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function msg(t,k){out.innerHTML='<div class="msg '+(k||'')+'">'+esc(t)+'</div>';}
  function raw(o){return '<pre>'+esc(JSON.stringify(o,null,2))+'</pre>';}
  function val(id){return document.getElementById(id).value.trim();}
  function key(){var k=val('key');if(!k){msg('Paste your API key at the top first.','bad');return null;}return k;}

  async function call(path,method,body){
    var k=key(); if(!k) return null;
    var o={method:method,headers:{'Authorization':'Bearer '+k}};
    if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body);}
    var r=await fetch(path,o); var d;
    try{d=await r.json();}catch(e){d={error:'unreadable_response'};}
    return {status:r.status,data:d};
  }

  function showSecret(d,title,extra){
    return '<div class="secret"><div class="lbl">'+esc(title)+' — '+esc(d.peer_id)+'</div>'
      +'<div class="val">'+esc(d.secret)+'</div>'
      +'<div class="warn">Shown once. Not recoverable. Copy it now and send it to them '
      +'separately from anything else.</div>'
      +(extra?'<div class="warn" style="color:var(--mute)">'+esc(extra)+'</div>':'')
      +'</div>';
  }

  function showPeers(d){
    if(!d.peers||!d.peers.length) return '<div class="msg">No peers registered yet.</div>';
    var h='<div class="msg good">'+d.count+' registered</div><div class="op open"><div class="op-body" style="padding:16px">';
    d.peers.forEach(function(p){
      h+='<div class="peer"><span class="id">'+esc(p.peer_id)+'</span> '
        +'<span class="pill '+esc(p.status)+'">'+esc(p.status)+'</span>'
        +'<div class="meta">'+esc(p.chain_name||'')
        +' · '+esc(p.submissions)+' submissions'
        +(p.last_seen?' · last '+esc(p.last_seen):' · never submitted')
        +(p.rotation_overlap_active?' · rotating':'')
        +'</div>'
        +(p.url?'<div class="meta">'+esc(p.url)+'</div>':'')
        +'</div>';
    });
    return h+'</div></div>';
  }

  window.run=async function(what){
    if(busy) return;
    var path,method='POST',body=null;

    if(what==='register'){
      var id=val('r-id');
      if(!id){msg('Give the peer an id.','bad');return;}
      path='/x/peer/register';
      body={peer_id:id.toLowerCase(),chain_name:val('r-name')||id,url:val('r-url')};
    }
    else if(what==='rotate'){
      var oid=val('o-id');
      if(!oid){msg('Which peer?','bad');return;}
      path='/x/peer/rotate'; body={peer_id:oid.toLowerCase()};
    }
    else if(what==='suspend'||what==='resume'){
      var sid=val('s-id');
      if(!sid){msg('Which peer?','bad');return;}
      path='/x/peer/'+what; body={peer_id:sid.toLowerCase()};
    }
    else if(what==='peers'){path='/x/peer/peers';method='GET';}
    else if(what==='history'){
      var hid=val('h-id');
      path='/x/peer/history'+(hid?'?peer_id='+encodeURIComponent(hid.toLowerCase()):'');
      method='GET';
    }
    else return;

    busy=true;
    out.innerHTML='<div class="msg">Working…</div>';
    try{
      var res=await call(path,method,body);
      if(!res){busy=false;return;}
      var d=res.data;
      if(res.status===401){msg('That key was refused.','bad');}
      else if(res.status===404&&d&&d.error==='unknown_module'){
        msg('modules/peer.py is not deployed yet.','bad');}
      else if(res.status>=400){
        out.innerHTML='<div class="msg bad">'+esc((d&&(d.detail||d.error))||('HTTP '+res.status))+'</div>'+raw(d);}
      else if(what==='register'&&d.secret){
        out.innerHTML=showSecret(d,'Peer secret')
          +'<div class="msg good">Registered. Send them /x/peer/spec so they can implement the signing.</div>'+raw(d);}
      else if(what==='rotate'&&d.secret){
        out.innerHTML=showSecret(d,'New secret','Previous secret valid until '+(d.previous_valid_until||''))+raw(d);}
      else if(what==='peers'){out.innerHTML=showPeers(d)+raw(d);}
      else{out.innerHTML='<div class="msg good">Done.</div>'+raw(d);}
    }catch(e){msg('Could not reach the server.','bad');}
    busy=false;
  };
})();
</script>
</body>
</html>
"""


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
    if getattr(H, "_peerconsole_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
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
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._peerconsole_patched = True
    _patched[0] = True
    print("PEERCONSOLE: /peers page installed at runtime", flush=True)
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
            print("PEERCONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/peers",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "paths": list(PAGE_PATHS),
            "note": "The page holds no credentials. Every route it calls "
                    "checks the key itself.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/praxis.py`

697 lines, 24699 bytes

```python
"""
modules/praxis.py  v1.0.2

Outbound submitter for the PRAXIS external-witness observe endpoint (chain 4).

Contract implemented against the SERVED schema route, not prose:
    GET  https://chain4.thepraesidium.ai/api/external-witness/observe/schema
    POST https://chain4.thepraesidium.ai/api/external-witness/observe

Signing:
    preimage  = b"PRAXIS-OBSERVE-v1\\n" + canonical JSON of the envelope
                with the "signature" field REMOVED
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    signature = lowercase hex HMAC-SHA256, carried in the body

Secret:
    environment variable PRAXIS_OBSERVE_SECRET
    (never written to a file, never returned by any route)

Routes
    GET  /x/praxis/spec      public   what this module does and how it signs
    GET  /x/praxis/status    public   config check + arms the /praxis page
    GET  /x/praxis/schema    public   fetches THEIR live contract, reports version
    GET  /x/praxis/history   keyed    past attempts from our own chain
    POST /x/praxis/canonical keyed    dry run: envelope, preimage, signature, NO send
    POST /x/praxis/submit    keyed    signs and sends ONE bounded submission

v1.0.1 fixes a real fault found on 7 Sep 2026. _seal called the host seal()
with one argument when it requires three, so every submit reported
sealed:false while the response still said ok:true. A remote call was being
recorded by the peer with no matching entry in our own chain. A failed seal
now makes the whole response ok:false and says so at the top level.

v1.0.2 fixes the follow-on. The host seal() returns a tuple
(audit_hash, block_index, key_seq); v1.0.1 only read dicts and strings and
so reported a successful seal as "seal returned no hash".
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

VERSION = "1.0.2"

# ---------------------------------------------------------------- constants

BASE = "https://chain4.thepraesidium.ai"
OBSERVE_URL = BASE + "/api/external-witness/observe"
SCHEMA_URL = BASE + "/api/external-witness/observe/schema"

DOMAIN = b"PRAXIS-OBSERVE-v1\n"
ENVELOPE_SCHEMA = "praxis_external_observe_request_v1"

OUR_PEER_ID = "aileash"
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"

SECRET_ENV = "PRAXIS_OBSERVE_SECRET"

TIMEOUT = 20
MAX_RESPONSE_BYTES = 262144

PUBLIC = {
    ("GET", "spec"),
    ("GET", "status"),
    ("GET", "schema"),
}


# ---------------------------------------------------------------- helpers

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def _secret():
    s = os.environ.get(SECRET_ENV, "")
    return s.strip()


def _fresh_nonce():
    # matches ^[A-Za-z0-9_.:-]{12,128}$
    return secrets.token_hex(20)


def _fresh_idem():
    # matches ^[0-9a-f]{64}(\.attempt-N)?$
    return secrets.token_hex(32)


def _http(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "AILeash-praxis/" + VERSION)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_RESPONSE_BYTES)
            return r.status, dict(r.headers), raw, None
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read(MAX_RESPONSE_BYTES)
        except Exception:
            pass
        return e.code, dict(getattr(e, "headers", {}) or {}), raw, None
    except Exception as e:
        return 0, {}, b"", "%s: %s" % (type(e).__name__, e)


def _parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _build_envelope(tip_digest, witnessed_peer_id, source_url,
                    receipt_digest=None, attempt=None, observed_at=None):
    payload = {
        "witnessed_peer_id": witnessed_peer_id,
        "data_class": "HASH_ONLY",
        "tip_digest": tip_digest,
        "source_url": source_url,
        "observed_at": observed_at or _now_iso(),
    }
    # receipt_digest is OPTIONAL in contract v1_1 and is omitted for a pure
    # chain-tip observation. Never duplicate tip_digest into it.
    if receipt_digest:
        payload["receipt_digest"] = receipt_digest

    key = _fresh_idem()
    if attempt:
        key = "%s.attempt-%s" % (key, attempt)

    return {
        "schema_version": ENVELOPE_SCHEMA,
        "peer_id": OUR_PEER_ID,
        "ts": _now_iso(),
        "nonce": _fresh_nonce(),
        "idempotency_key": key,
        "payload": payload,
    }


def _sign(envelope, secret):
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    canonical = _canonical(unsigned)
    preimage = DOMAIN + canonical
    sig = hmac.new(secret.encode("utf-8"), preimage, hashlib.sha256).hexdigest()
    return canonical, preimage, sig


def _validate(tip_digest, witnessed_peer_id, source_url, receipt_digest):
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", tip_digest or ""):
        return "tip_digest must be 64 lowercase hex characters"
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{2,63}", witnessed_peer_id or ""):
        return "witnessed_peer_id must match ^[a-z][a-z0-9_.:-]{2,63}$"
    if not (source_url or "").startswith("https://") or (source_url or "").count("/") < 3:
        return "source_url must be an https URL with a path"
    if len(source_url) > 512:
        return "source_url exceeds 512 characters"
    if receipt_digest and not re.fullmatch(r"[0-9a-f]{64}", receipt_digest):
        return "receipt_digest, if supplied, must be 64 lowercase hex characters"
    if receipt_digest and receipt_digest == tip_digest:
        return "receipt_digest must not duplicate tip_digest"
    return None


def _record_seal_result(out, res):
    """Read whatever the host seal() handed back.

    This deployment's seal() returns a TUPLE: (audit_hash, block_index,
    key_seq). v1.0.1 only understood dicts and strings, so a successful seal
    was reported as "seal returned no hash". Tuples are handled first.
    """
    if isinstance(res, (tuple, list)):
        if len(res) > 0:
            out["audit_hash"] = res[0]
        if len(res) > 1:
            out["block_index"] = res[1]
        if len(res) > 2:
            out["key_seq"] = res[2]
    elif isinstance(res, dict):
        out["audit_hash"] = (res.get("audit_hash") or res.get("hash")
                             or res.get("seal") or res.get("block_hash"))
        out["block_index"] = res.get("block_index") or res.get("index")
        out["key_seq"] = res.get("key_seq") or res.get("seq")
    elif isinstance(res, str):
        out["audit_hash"] = res
    out["sealed"] = bool(out["audit_hash"])
    return out


def _seal(ctx, event):
    """Seal into our own chain.

    The host seal() takes three positional arguments (event, result, ts).
    v1.0.0 called it with one and every submit failed silently. We try the
    three-argument form first and fall back only if the host is older, and
    we record which call shape worked so this is never guesswork again.
    """
    out = {"sealed": False, "audit_hash": None, "error": None,
           "call_shape": None}
    sealer = ctx.get("seal")
    if not sealer:
        out["error"] = "no seal function in ctx"
        return out

    result_value = event.get("result") or "sent"
    ts_value = event.get("ts") or _now_iso()

    attempts = [
        ("seal(event, result, ts)", lambda: sealer(event, result_value, ts_value)),
        ("seal(event, result)", lambda: sealer(event, result_value)),
        ("seal(event)", lambda: sealer(event)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            res = call()
        except TypeError as e:
            errors.append("%s -> TypeError: %s" % (shape, e))
            continue
        except Exception as e:
            out["error"] = "%s -> %s: %s" % (shape, type(e).__name__, e)
            out["call_shape"] = shape
            return out
        out["call_shape"] = shape
        _record_seal_result(out, res)
        if not out["sealed"]:
            out["error"] = "seal returned no hash"
        return out

    out["error"] = "no accepted call shape; " + " | ".join(errors)
    return out


# ---------------------------------------------------------------- page

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>PRAXIS submit</title>
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--ink);color:#e8ecf5;
     font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1{font-size:18px;margin:0 0 4px;color:var(--gold)}
p.sub{margin:0 0 18px;color:#8b96ad;font-size:13px}
label{display:block;margin:12px 0 4px;font-size:12px;color:#8b96ad;
      text-transform:uppercase;letter-spacing:.06em}
input{width:100%;padding:11px;background:var(--ink2);border:1px solid #24304e;
      border-radius:8px;color:#e8ecf5;font:14px monospace}
input:focus{outline:none;border-color:var(--gold)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
button{flex:1;min-width:120px;padding:13px;border:0;border-radius:8px;
       background:var(--gold);color:#0a0f1e;font-weight:600;font-size:15px}
button.alt{background:var(--ink2);color:#e8ecf5;border:1px solid #24304e}
button:disabled{opacity:.45}
pre{margin-top:16px;padding:12px;background:var(--ink2);border:1px solid #24304e;
    border-radius:8px;white-space:pre-wrap;word-break:break-all;
    font:12px/1.45 monospace;max-height:60vh;overflow:auto}
.ok{color:var(--ok)}.err{color:var(--err)}
</style></head><body>

<h1>PRAXIS observe &mdash; chain 4</h1>
<p class="sub">Signs one bounded submission and sends it. Fresh ts, nonce and
idempotency key every press.</p>

<label>API key</label>
<input id="key" type="password" placeholder="AILeash API key" autocomplete="off">

<label>Tip digest (64 hex)</label>
<input id="tip" placeholder="press Load tip">

<label>Witnessed peer id</label>
<input id="wpid" value="aileash">

<label>Source URL</label>
<input id="src" value="https://sebbi.pro/x/witness/tip">

<label>Attempt marker (optional)</label>
<input id="att" placeholder="leave blank for a first attempt">

<div class="row">
  <button class="alt" onclick="loadTip()">Load tip</button>
  <button class="alt" onclick="theirSchema()">Their schema</button>
</div>
<div class="row">
  <button class="alt" onclick="go('canonical')">Dry run</button>
  <button onclick="send()">Send</button>
</div>

<pre id="out">Ready.</pre>

<script>
var out = document.getElementById('out');
function show(t, cls){ out.className = cls || ''; out.textContent = t; }
function val(id){ return document.getElementById(id).value.trim(); }

function loadTip(){
  show('Loading our tip...');
  fetch('/x/witness/tip').then(function(r){ return r.json(); }).then(function(j){
    var t = j.tip || j.hash || j.head || j.chain_tip || j.latest || '';
    document.getElementById('tip').value = t;
    show('Tip loaded.\\n\\n' + JSON.stringify(j, null, 2), 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function theirSchema(){
  show('Fetching their live contract...');
  fetch('/x/praxis/schema').then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.receipt_digest_required ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function body(){
  return {
    tip_digest: val('tip'),
    witnessed_peer_id: val('wpid'),
    source_url: val('src'),
    attempt: val('att') || null
  };
}

function go(action){
  var k = val('key');
  if(!k){ show('API key required.', 'err'); return; }
  show('Working...');
  fetch('/x/praxis/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + k },
    body: JSON.stringify(body())
  }).then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.ok === false ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function send(){
  if(!confirm('Send one bounded submission to chain 4 now?')) return;
  go('submit');
}
</script>
</body></html>"""


def _install_page():
    """Serve /praxis by wrapping the running handler's do_GET, once."""
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            names = dir(mod)
        except Exception:
            continue
        for name in names:
            try:
                obj = getattr(mod, name, None)
            except Exception:
                continue
            if not isinstance(obj, type):
                continue
            if not (hasattr(obj, "do_GET") and hasattr(obj, "do_POST")):
                continue
            if getattr(obj, "_praxis_patched", False):
                return True
            original = obj.do_GET

            def patched(self, _original=original):
                try:
                    path = self.path.split("?")[0].rstrip("/")
                except Exception:
                    path = ""
                if path == "/praxis":
                    data = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Robots-Tag", "noindex")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return _original(self)

            obj.do_GET = patched
            obj._praxis_patched = True
            return True
    return False


# ---------------------------------------------------------------- actions

def _spec():
    return {
        "module": "praxis",
        "version": VERSION,
        "what_this_is": (
            "Outbound submitter for the PRAXIS external-witness observe "
            "endpoint. One bounded submission per press. This module sends; "
            "it does not receive."
        ),
        "target": {"observe": OBSERVE_URL, "schema": SCHEMA_URL},
        "signing": {
            "algorithm": "hmac-sha256",
            "domain": "PRAXIS-OBSERVE-v1\\n",
            "canonicalization": "sort_keys=true, separators=(',',':'), ensure_ascii=true, utf-8",
            "preimage": "domain bytes + canonical JSON of the envelope with 'signature' removed",
            "signature_encoding": "lowercase hex",
            "auth_transport": "body, not headers",
        },
        "payload_policy": (
            "receipt_digest is optional under their contract v1_1 and is "
            "omitted for a pure chain-tip observation. It is never filled "
            "with a duplicate of tip_digest or a placeholder."
        ),
        "freshness": "fresh ts, fresh nonce and a fresh idempotency key on every submit",
        "seal_policy": (
            "a submit that reaches the peer but fails to seal into our own "
            "chain returns ok:false with seal_failed true. The send is still "
            "reported in full, because it happened and the peer may hold a "
            "durable record of it."
        ),
        "not_claimed": [
            "this lane is one-directional and does not establish mutual witnessing",
            "their acceptance is a transport and signature outcome, not verification "
            "of anything in our chain",
        ],
        "routes": {
            "public": ["GET spec", "GET status", "GET schema"],
            "keyed": ["GET history", "POST canonical", "POST submit"],
        },
    }


def _status():
    installed = _install_page()
    s = _secret()
    return {
        "module": "praxis",
        "version": VERSION,
        "page": "/praxis",
        "page_installed": installed,
        "peer_id": OUR_PEER_ID,
        "secret_configured": bool(s),
        "secret_env": SECRET_ENV,
        "secret_length": len(s) if s else 0,
        "target": OBSERVE_URL,
        "note": (
            "secret_configured false means the environment variable is not set "
            "on this replica; the secret itself is never returned by any route"
        ),
    }


def _their_schema():
    code, headers, raw, err = _http("GET", SCHEMA_URL)
    if err:
        return {"ok": False, "error": "fetch_failed", "detail": err}, 502
    doc = _parse_json(raw)
    if doc is None:
        return {"ok": False, "error": "unparseable", "status": code}, 502

    req = (((doc.get("request_schema") or {}).get("properties") or {})
           .get("payload") or {})
    required = req.get("required") or []
    hdr = {}
    for k, v in (headers or {}).items():
        if k.lower().startswith("x-praxis") or k.lower() == "cache-control":
            hdr[k.lower()] = v

    return {
        "ok": True,
        "fetched_at": _now_iso(),
        "http_status": code,
        "contract_version": doc.get("schema_version"),
        "payload_required": required,
        "receipt_digest_required": "receipt_digest" in required,
        "canonicalization": ((doc.get("signing") or {}).get("canonicalization")),
        "domain": ((doc.get("signing") or {}).get("domain")),
        "clock_skew_seconds": ((doc.get("freshness") or {}).get("clock_skew_seconds")),
        "headers": hdr,
        "body_sha256": _sha256_hex(raw),
    }, 200


def _canonical_action(data):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig

    return {
        "ok": True,
        "dry_run": True,
        "sent": False,
        "envelope": signed,
        "canonical_json": canonical.decode("utf-8"),
        "canonical_sha256": _sha256_hex(canonical),
        "preimage_sha256": _sha256_hex(preimage),
        "signature": sig,
        "note": "nothing was sent; ts, nonce and idempotency_key here are "
                "single-use and will be regenerated on an actual submit",
    }, 200


def _submit(data, ctx):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig
    wire = _canonical(signed)

    started = time.time()
    code, headers, raw, err = _http("POST", OBSERVE_URL, wire)
    took = round(time.time() - started, 3)

    parsed = _parse_json(raw)
    transport_ok = err is None and code in (200, 202)
    result = {
        "ok": transport_ok,
        "sent": err is None,
        "took_seconds": took,
        "http_status": code,
        "transport_error": err,
        "request": {
            "idempotency_key": env["idempotency_key"],
            "nonce": env["nonce"],
            "ts": env["ts"],
            "peer_id": env["peer_id"],
            "payload": env["payload"],
            "signature": sig,
            "canonical_sha256": _sha256_hex(canonical),
            "wire_sha256": _sha256_hex(wire),
            "wire_bytes": len(wire),
        },
        "response": {
            "body": parsed,
            "raw_sha256": _sha256_hex(raw) if raw else None,
            "raw_bytes": len(raw),
            "raw_text": (raw.decode("utf-8", "replace")[:4000] if raw else None),
        },
    }

    if isinstance(parsed, dict):
        result["their_error"] = parsed.get("error")
        result["their_accepted"] = parsed.get("accepted")
        result["their_replayed"] = parsed.get("replayed")
        result["their_request_digest"] = parsed.get("request_digest")
        result["their_durable_event_recorded"] = parsed.get("durable_event_recorded")
        result["their_accepted_decision_recorded"] = parsed.get(
            "accepted_decision_recorded")

    event = {
        "user_id": "praxis:" + OUR_PEER_ID,
        "event": "praxis_observe_submit",
        "kind": "praxis_observe_submit",
        "ts": _now_iso(),
        "target": OBSERVE_URL,
        "idempotency_key": env["idempotency_key"],
        "request_wire_sha256": result["request"]["wire_sha256"],
        "http_status": code,
        "response_sha256": result["response"]["raw_sha256"],
        "their_error": result.get("their_error"),
        "their_accepted": result.get("their_accepted"),
        "result": "sent" if err is None else "transport_error",
    }
    result["our_seal"] = _seal(ctx, event)

    # A send that the peer accepted but our own chain has no entry for is a
    # failure of this deployment, not a success. Say so at the top level.
    if not result["our_seal"].get("sealed"):
        result["ok"] = False
        result["seal_failed"] = True
        result["seal_failed_note"] = (
            "the submission reached the peer but was NOT sealed into our "
            "chain. The peer may hold a durable record with no counterpart "
            "here. Do not treat this submission as evidenced on our side."
        )

    if not transport_ok:
        status = 502 if err else 200
    elif not result["our_seal"].get("sealed"):
        status = 500
    else:
        status = 200
    return result, status


def _history(ctx, data):
    limit = 20
    try:
        limit = max(1, min(100, int(data.get("limit") or 20)))
    except Exception:
        pass
    rows = []
    try:
        conn = ctx.get("conn")
        lock = ctx.get("lock")
        sql = ("SELECT rowid, * FROM audit_log "
               "WHERE user_id = ? ORDER BY rowid DESC LIMIT ?")
        if lock:
            with lock:
                cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return {"ok": False, "error": "query_failed",
                "detail": "%s: %s" % (type(e).__name__, e)}, 500
    return {"ok": True, "count": len(rows), "rows": rows}, 200


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "status":
        return _status(), 200

    if method == "GET" and action == "schema":
        return _their_schema()

    if method == "GET" and action == "history":
        return _history(ctx, data)

    if method == "POST" and action == "canonical":
        return _canonical_action(data)

    if method == "POST" and action == "submit":
        return _submit(data, ctx)

    return {"ok": False, "error": "unknown_action", "action": action,
            "available": ["spec", "status", "schema", "history",
                          "canonical", "submit"]}, 404

```
