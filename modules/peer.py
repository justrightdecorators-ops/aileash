"""
modules/peer.py  v1.3.2  --  signed peer submission (shared secret)

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

VERSION = "1.3.2"

PUBLIC = {
    ("GET", "spec"),
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


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if action == "spec":
        return _spec(), 200
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
