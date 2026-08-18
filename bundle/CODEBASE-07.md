# Codebase — part 7 of 21

Contains:
- `modules/peer.py`
- `modules/peerconsole.py`
- `modules/publish.py`
- `modules/reconcile.py`


## `modules/peer.py`

775 lines, 31547 bytes

```python
"""
modules/peer.py  v1.1  --  signed peer submission (shared secret)

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
    overlap.

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

ROUTES
    GET  spec       public   full implementation guide
    POST canonical  public   the exact string to sign. no secret needed.
    GET  peers      public   peer ids, status, rotation state. no secrets.
    POST submit     public route, SIGNATURE authenticated
    POST register   keyed    operator issues a peer credential
    POST rotate     keyed    issue a new secret, overlap the old
    POST suspend    keyed
    POST resume     keyed
    GET  history    keyed    submissions by peer

TABLES OWNED
    peer_registry, peer_nonce, peer_submission
"""

import hashlib
import hmac
import json
import os
import re
import time

VERSION = "1.1"

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
                last_seen        REAL
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


def _sweep_nonces(ctx):
    cutoff = _now() - NONCE_TTL_SECONDS
    with ctx["lock"]:
        ctx["conn"].execute("DELETE FROM peer_nonce WHERE seen_at < ?",
                            (cutoff,))
        ctx["conn"].commit()


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

    # ---- accept: seal it
    now = _now()
    event = {"module": "peer", "action": "submit", "peer_id": peer_id,
             "chain_name": row[1], "payload_digest": payload_digest,
             "payload": payload}
    result = {"accepted": True, "signed_with": accepted_with,
              "auth": "hmac-shared-secret"}
    audit_hash = block_index = receipt_seq = None
    try:
        audit_hash, block_index, receipt_seq = ctx["seal"](
            event, result, now, None)
    except Exception:
        pass

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
                    "receipt_seq": receipt_seq},
        "verify": {
            "inclusion": "/x/complete/prove",
            "ancestry": "/x/consistency/ancestor?tip=<any tip we served>",
            "append_only": "/x/consistency/proof?first=&second=",
        },
    }

    with ctx["lock"]:
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

    if accepted_with == "previous":
        out["warning"] = ("Accepted with the previous secret. The overlap "
                          "window ends %s." % _iso((row[4] or 0) +
                                                   ROTATION_OVERLAP_SECONDS))
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
    try:
        ctx["seal"]({"module": "peer", "action": "register",
                     "peer_id": peer_id},
                    {"registered": True}, now, None)
    except Exception:
        pass

    return {
        "ok": True,
        "peer_id": peer_id,
        "secret": secret,
        "warning": "This secret is shown once and is not recoverable. "
                   "Send it to the peer over a channel you trust.",
        "tell_the_peer_this": SHARED_SECRET_SCOPE,
        "endpoint": "/x/peer/submit",
        "spec": "/x/peer/spec",
        "stronger_lane": "/x/signed/spec",
    }, 200


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
    try:
        ctx["seal"]({"module": "peer", "action": "rotate",
                     "peer_id": peer_id}, {"rotated": True}, now, None)
    except Exception:
        pass

    return {
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
    }, 200


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
    try:
        ctx["seal"]({"module": "peer", "action": status,
                     "peer_id": peer_id}, {"status": status}, _now(), None)
    except Exception:
        pass
    return {"ok": True, "peer_id": peer_id, "status": status}, 200


def _peers(ctx):
    _setup(ctx)
    now = _now()
    rows = ctx["conn"].execute(
        "SELECT peer_id, chain_name, url, status, created, submissions, "
        "last_seen, rotated_at FROM peer_registry ORDER BY created"
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
        } for r in rows],
        "note": "Secrets are never returned by any route.",
    }, 200


def _history(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    q = ("SELECT peer_id, ts, idempotency_key, payload_digest, audit_hash "
         "FROM peer_submission")
    args = []
    if peer_id:
        q += " WHERE peer_id = ?"
        args.append(peer_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = ctx["conn"].execute(q, args).fetchall()
    return {
        "ok": True, "count": len(rows),
        "submissions": [{
            "peer_id": r[0], "at": _iso(r[1]), "idempotency_key": r[2],
            "payload_digest": r[3], "audit_hash": r[4],
        } for r in rows],
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
        },
        "on_acceptance":
            "The payload is sealed into the audit chain and you get "
            "audit_hash, block_index and receipt_seq. Verify "
            "independently: inclusion at /x/complete/prove, ancestry at "
            "/x/consistency/ancestor, append-only at "
            "/x/consistency/proof. Both offline verifiers "
            "(aileash_verify.py, verify_authority.py) are stdlib only and "
            "touch no network.",
        "routes": {
            "GET spec": "public. this document.",
            "POST canonical": "public. the exact string to sign.",
            "GET peers": "public. peer ids and status. never secrets.",
            "POST submit": "signature authenticated. no API key.",
            "POST register": "keyed. operator issues a credential.",
            "POST rotate": "keyed. new secret, old one overlaps.",
            "POST suspend / POST resume": "keyed.",
            "GET history": "keyed. submissions, optionally by peer.",
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


## `modules/publish.py`

491 lines, 21976 bytes

```python
#!/usr/bin/env python3
"""
modules/publish.py  -  sealing what you published, at the moment you publish it
===============================================================================

THE PROBLEM THIS EXISTS TO NEVER HAVE AGAIN
-------------------------------------------
Somebody asks when a page was published. You answer from git history. They
point out - correctly - that git commit dates are fields in the commit
object which anyone can set to anything with an environment variable before
committing. Your strongest evidence turns out to be the weakest thing in
the room, and it drags the credible parts down with it.

The fix is not a better argument. It is sealing the page the moment it goes
live, so the question never depends on anybody's word again.

WHAT THIS DOES
--------------
    POST /x/publish/seal {"url": "https://example.com/spec"}

We fetch the URL ourselves, hash exactly what was served, and seal the hash,
the URL and the fetch time into the chain - where it is anchored externally
and handed to peer chains like every other block.

From then on:

  - "this exact content was served at this address no later than T" is
    arithmetic rather than a claim;
  - re-sealing the same URL later builds a permanent revision history that
    the publisher cannot edit, because each version is its own block;
  - and anyone can check it without an account.

Seal at publication and you never argue about a publication date again. That
is the entire point, and it takes one call.

WHAT IT HONESTLY CANNOT DO
--------------------------
It cannot reach backwards. A seal made today proves the content existed
today, not that it existed last week. Nothing can prove that - not this, not
Bitcoin, not a notary. Timestamps are one-directional by nature.

So for anything already published before it was sealed, the module records
EXTERNAL REFERENCES alongside: a GitHub push event, a Wayback Machine
snapshot, a DigiCert or OpenTimestamps proof. Those are stored and sealed as
supplied. We do not verify them and we do not present them as ours - they
are somebody else's record, named so a third party can check it at source.
That distinction is stated in every response rather than left to be
discovered.

Two references are worth knowing about, because they are the ones that
actually carry an earlier date:

  GitHub push events   api.github.com/repos/<owner>/<repo>/events
                       The push timestamp is recorded server-side by GitHub
                       and cannot be set by the pusher, unlike commit dates.
                       Retained roughly 90 days - so it must be captured
                       while it still exists.

  Wayback Machine      archive.org/wayback/available?url=...&timestamp=...
                       An independent party with no stake in the dispute.
                       If it caught the page, that settles it outright.

FETCHING SAFELY
---------------
This module makes the server fetch a URL. Done naively that is a hole worse
than the one it closes. So the fetcher speaks only http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that
is private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a cap. Sealing is keyed,
so this is not an anonymous capability either.

    POST /x/publish/seal      fetch, hash and seal a live URL     (keyed)
    GET  /x/publish/history   every version ever sealed of a URL  (public)
    GET  /x/publish/verify    was this exact content served, when (public)
    GET  /x/publish/list      everything sealed                   (public)
    GET  /x/publish/spec      how to check any of it              (public)
"""

import hashlib
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Reading is open. A publication record only settles an argument if the
# other side can check it without going through the publisher.
PUBLIC = {("GET", "history"), ("GET", "verify"), ("GET", "list"),
          ("GET", "spec")}

CONTENT_PREFIX = b"AILEASH-PUBLISH-v1:"

FETCH_TIMEOUT = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
MAX_EXTERNAL = 8

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS publish_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,url TEXT,"
                  "content_hash TEXT,byte_length INTEGER,http_status INTEGER,"
                  "content_type TEXT,note TEXT,external TEXT,"
                  "fetched REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_url ON publish_seal(url,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_hash ON publish_seal(content_hash)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# fetching - read the SSRF note above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction to fetch a second URL we never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    if not parts.hostname:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(parts.hostname, port)


def _fetch(url):
    """Returns (body_bytes, status, content_type, error)."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, None, None, why
    request = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "aileash-publish/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, exc.code, None, "url answered %s" % exc.code
    except Exception as exc:
        return None, None, None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, status, content_type, "response larger than the %d byte cap" % MAX_FETCH_BYTES
    return body, status, content_type, None


def _content_hash(body):
    """Hash exactly the bytes served. No normalisation, no cleverness -
    a whitespace-tolerant hash would be a hash of our opinion of the page
    rather than of the page."""
    return hashlib.sha256(CONTENT_PREFIX + body).hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _clean_external(value):
    """External references are recorded verbatim and never verified."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_EXTERNAL]:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()[:60]
            reference = str(item.get("reference", item.get("url", ""))).strip()[:400]
            claimed = str(item.get("claimed_time", "")).strip()[:60]
            if source and reference:
                out.append({"source": source, "reference": reference,
                            "claimed_time": claimed or None})
        elif isinstance(item, str) and item.strip():
            out.append({"source": "unnamed", "reference": item.strip()[:400],
                        "claimed_time": None})
    return out


def _seal(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required",
                "message": "The address of the page you have just published."}, 400

    note = str(data.get("note", "") or "").strip()[:300]
    external = _clean_external(data.get("external"))

    body, status, content_type, why = _fetch(url)
    if why:
        return {"error": "fetch_failed", "url": url, "message": why,
                "note": "Nothing was sealed. A record of a page we could not read would be "
                        "worse than no record."}, 502

    digest = _content_hash(body)
    now = time.time()

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT content_hash,fetched,audit_hash FROM publish_seal "
            "WHERE url=? ORDER BY id ASC", (url,)).fetchall()

    unchanged = bool(prior) and prior[-1][0] == digest
    first_of_this_version = None
    for row in prior:
        if row[0] == digest:
            first_of_this_version = row[1]
            break

    external_summary = ";".join("%s=%s" % (e["source"], e["reference"][:60]) for e in external)
    ev = {"user_id": "pub:" + digest[:16], "action": "publication_sealed", "amount": 0,
          "country": "UK", "device_id": "publish", "anomaly": 0, "device_risk": 0}
    res = {"decision": "PUBLICATION_SEALED", "score": 0, "publish_version": VERSION,
           "url": url, "content_hash": digest, "bytes": len(body),
           "http_status": status,
           "detail": "url=%s;sha256=%s;bytes=%d%s"
                     % (url, digest, len(body),
                        ";external=" + external_summary if external_summary else "")}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO publish_seal(api_key,url,content_hash,byte_length,http_status,"
            "content_type,note,external,fetched,audit_hash,block_index) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, digest, len(body), status, content_type or None,
             note or None,
             "|".join("%s %s %s" % (e["source"], e["reference"], e["claimed_time"] or "")
                      for e in external) or None,
             now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "url": url, "content_hash": digest, "bytes": len(body),
        "http_status": status, "content_type": content_type,
        "sealed_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "version_number": len(prior) + 1,
        "publish_version": VERSION,
        "what_this_proves": "This exact content was served at this address when we fetched it, "
                            "and the record of that cannot be altered afterwards.",
        "what_it_does_not": "It does not prove the page existed earlier than this moment. "
                            "Nothing can prove that after the fact - timestamps only run "
                            "forwards. Seal at publication and the question never arises.",
        "history": "/x/publish/history?url=" + url,
        "verify_this_block": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if unchanged:
        out["unchanged"] = True
        out["first_sealed_in_this_form"] = _iso(first_of_this_version)
        out["message"] = ("Identical to the last sealed version. The page has not changed since "
                          "%s and now has an additional dated witness." % _iso(first_of_this_version))
    elif prior:
        out["changed"] = True
        out["previous_hash"] = prior[-1][0]
        out["previous_sealed_at"] = _iso(prior[-1][1])
        out["message"] = ("The content has changed since the last seal. Both versions remain in "
                          "the chain - a revision history the publisher cannot edit.")
    else:
        out["message"] = ("First seal for this address. Every later seal builds a permanent, "
                          "dated revision history from here.")

    if external:
        out["external_references"] = external
        out["external_caveat"] = ("Recorded exactly as supplied and sealed with the block. We do "
                                  "not verify them and they are not our evidence - they are "
                                  "somebody else's record, named so you can check them at "
                                  "source.")
    else:
        out["advice"] = ("If this page was published before today, add external references - a "
                         "GitHub push event, a Wayback snapshot - and they will be sealed "
                         "alongside. Those carry an earlier date; a seal made now cannot.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _parse_external(blob):
    if not blob:
        return []
    out = []
    for line in blob.split("|"):
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append({"source": parts[0], "reference": parts[1],
                        "claimed_time": parts[2] if len(parts) > 2 and parts[2] else None})
    return out


def _history(ctx, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT content_hash,byte_length,fetched,audit_hash,block_index,note,external "
            "FROM publish_seal WHERE url=? ORDER BY id ASC LIMIT 500", (url,)).fetchall()
    if not rows:
        return {"error": "never_sealed", "url": url,
                "message": "No seal recorded for that address."}, 404

    versions, last_hash = [], None
    for content_hash, length, fetched, audit_hash, block_index, note, external in rows:
        versions.append({
            "content_hash": content_hash, "bytes": length,
            "sealed_at": _iso(fetched), "sealed_in_chain": audit_hash,
            "block_index": block_index, "note": note,
            "changed_from_previous": last_hash is not None and content_hash != last_hash,
            "external_references": _parse_external(external),
        })
        last_hash = content_hash

    distinct = len({v["content_hash"] for v in versions})
    return {"url": url, "seals": len(versions), "distinct_versions": distinct,
            "first_sealed": versions[0]["sealed_at"], "latest_sealed": versions[-1]["sealed_at"],
            "current_hash": versions[-1]["content_hash"],
            "versions": versions,
            "publish_version": VERSION,
            "what_this_is": "A dated revision history the publisher cannot edit. Each version is "
                            "its own block; altering or removing one breaks every block after it.",
            "limit": "The first seal fixes an upper bound, not a lower one. Anything published "
                     "before its first seal rests on external evidence, which is recorded here "
                     "but not verified by us."}, 200


def _verify(ctx, data):
    url = str(data.get("url", "")).strip()
    digest = str(data.get("hash", data.get("content_hash", ""))).strip().lower()
    if not digest or not HEX64.match(digest):
        return {"error": "hash_required",
                "message": "sha256 of AILEASH-PUBLISH-v1: followed by the exact bytes served"}, 400

    with ctx["lock"]:
        if url:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE url=? AND content_hash=? ORDER BY id ASC", (url, digest)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE content_hash=? ORDER BY id ASC", (digest,)).fetchall()

    if not rows:
        return {"sealed": False, "content_hash": digest, "url": url or None,
                "message": "We hold no seal for that exact content. Either it was never sealed, "
                           "or the content differs from what was - a single byte is enough."}, 404

    return {"sealed": True, "content_hash": digest,
            "url": rows[0][0], "times_sealed": len(rows),
            "first_sealed": _iso(rows[0][1]),
            "latest_sealed": _iso(rows[-1][1]),
            "sealed_in_chain": rows[0][2], "block_index": rows[0][3],
            "publish_version": VERSION,
            "what_this_proves": "Content with exactly this fingerprint was served at that "
                                "address no later than the first sealing time, and the record "
                                "of it has not been altered since.",
            "verify_the_block": "/x/consistency/ancestor?tip=" + rows[0][2]}, 200


def _list(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT url,COUNT(*),MIN(fetched),MAX(fetched),COUNT(DISTINCT content_hash) "
            "FROM publish_seal GROUP BY url ORDER BY MAX(fetched) DESC LIMIT 500").fetchall()
    return {"count": len(rows),
            "pages": [{"url": r[0], "seals": r[1], "first_sealed": _iso(r[2]),
                       "latest_sealed": _iso(r[3]), "distinct_versions": r[4],
                       "history": "/x/publish/history?url=" + r[0]} for r in rows],
            "publish_version": VERSION,
            "note": "Everything this platform has sealed about its own published pages. Ours is "
                    "in here too - a publisher who seals everyone's pages but not their own is "
                    "telling you something."}, 200


def _spec():
    return {
        "publish_version": VERSION,
        "content_hash": "sha256('AILEASH-PUBLISH-v1:' || exact_bytes_served) as lowercase hex",
        "no_normalisation": "The bytes are hashed exactly as served. Nothing is trimmed, "
                            "reordered or cleaned up first - a whitespace-tolerant hash would "
                            "be a hash of our opinion of the page rather than of the page.",
        "reproduce_it": "curl the URL, pipe the raw bytes through sha256 with that prefix, and "
                        "compare with what we sealed. If your bytes differ, the page changed.",
        "what_a_seal_proves": "That content with this exact fingerprint was served at this "
                              "address no later than the sealing time, and that the record has "
                              "not been altered since - it is a chain block like any other, "
                              "anchored externally and witnessed by peers.",
        "what_it_cannot_prove": "That the page existed before the seal. Timestamps run forwards "
                                "only. Any product implying otherwise is misdescribing what a "
                                "timestamp is.",
        "for_earlier_dates": {
            "github_push": "api.github.com/repos/<owner>/<repo>/events - the push timestamp is "
                           "recorded by GitHub, not the pusher, unlike commit author and "
                           "committer dates which are settable fields. Retained around 90 days, "
                           "so capture it while it exists.",
            "wayback": "archive.org/wayback/available - an independent party with no stake in "
                       "the dispute.",
            "status": "Both are recorded and sealed as supplied, and neither is verified by us. "
                      "They are somebody else's evidence, named so you can check them at source.",
        },
        "the_discipline": "Seal at publication. One call at the moment a page goes live means "
                          "the publication date never rests on anyone's word, anyone's git "
                          "history, or anyone's memory again.",
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
            return _history(ctx, data)
        if action == "verify":
            return _verify(ctx, data)
        if action == "list":
            return _list(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "verify", "list"],
            "POST": ["seal (keyed)"]}, 404

```


## `modules/reconcile.py`

440 lines, 20123 bytes

```python
"""
Reconciliation notary - /x/reconcile/<action>

THE PROBLEM THIS ATTACKS
------------------------
A sealed chain proves records were not altered after the fact. It does not
prove they were true when written. An operator who seals fiction on time has
a tamper-evident chain of fiction. Every honest person in this market knows
that, and almost nobody says it.

You cannot prove truth from outside a system. What you CAN do is what real
auditors do: substantive testing. Take the sealed claim, go to the operator's
own live system, and check whether the two agree - then seal the result of
that check, including the failures.

WHY THIS ONE IS DIFFERENT
-------------------------
The sample is fixed before the operator sees it.

/plan derives a selection seed from the current chain tip - a value the
operator cannot predict in advance and cannot change afterwards without
breaking the chain - picks the records to be tested, and seals that selection
BEFORE any data is requested. Only then are the record identifiers returned.

So the operator cannot choose which records get examined, cannot prepare only
the flattering ones, and cannot quietly drop a test that came back badly:
every planned run is sealed at the moment it is planned, and a plan with no
submitted result is visible forever as an abandoned test.

Mismatches are sealed with the same permanence as matches. That is the whole
design. A reconciliation system that can bury its own failures is decoration.

WHAT A PASS ACTUALLY MEANS
--------------------------
That two systems the operator controls agree with each other, on records the
operator could not choose, at a time the operator could not pick.

That is not proof of truth. An operator who fabricates consistently across
every system, in real time, without knowing what will be sampled, will pass.
What it does is raise the cost of lying from "edit one database" to
"maintain a coherent parallel reality across independent systems indefinitely,
under unpredictable sampling, with every failure sealed permanently."

That is the honest claim. It is also, as far as I know, more than anyone else
in this market is doing.

HONEST LIMITS
-------------
- Consistency is not truth. Two agreeing systems can both be wrong.
- The operator supplies the comparison data. This tests their systems against
  each other, not against the world.
- Sampling only covers what has been sealed. It cannot find a decision that
  was never recorded at all - gapless receipts are what cover that.
- A high match rate on a badly chosen field proves nothing. Reconcile the
  fields that would hurt to get wrong.

    POST /x/reconcile/plan     sample_size, field  - seals the selection first
    POST /x/reconcile/submit   run_id, results     - seals the comparison
    GET  /x/reconcile/run?id=RUN-XXXXXXXX
    GET  /x/reconcile/score
    GET  /x/reconcile/list
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.1"
MAX_SAMPLE = 200

# Planning and submitting stay keyed - they touch an operator's own records.
# What is public is the part that decides whether any of it means anything:
# that the sample was fixed before the data was asked for, and that failures
# were sealed as permanently as passes.
PUBLIC = {("GET", "public"), ("GET", "proof")}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS reconcile_runs(run_id TEXT PRIMARY KEY,api_key TEXT,field TEXT,seed TEXT,planned REAL,submitted REAL,sample_size INTEGER,matched INTEGER,mismatched INTEGER,missing INTEGER,status TEXT DEFAULT 'planned',block_ids TEXT,detail TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_rec_key ON reconcile_runs(api_key)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, rid, action, detail):
    ts = time.time()
    ev = {"user_id": "rec:" + rid, "action": "reconcile_" + action, "amount": 0,
          "country": "UK", "device_id": "reconcile", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RECONCILE_SEALED", "score": 0, "reconcile_action": action,
           "reconcile_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _plan(ctx, api_key, data):
    try:
        n = int(data.get("sample_size", 25))
    except Exception:
        return {"error": "invalid_sample_size"}, 400
    if n < 1 or n > MAX_SAMPLE:
        return {"error": "sample_size_out_of_range", "max": MAX_SAMPLE}, 400
    field = str(data.get("field", "decision")).strip()[:60] or "decision"

    with ctx["lock"]:
        tiprow = ctx["conn"].execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        rows = ctx["conn"].execute("SELECT id,user_id,result_json,ts FROM audit_log WHERE api_key=? ORDER BY id ASC", (api_key,)).fetchall()

    if not rows:
        return {"error": "nothing_to_reconcile",
                "message": "No sealed records under this key yet."}, 400

    tip = tiprow[0] if tiprow else "GENESIS"
    ts = time.time()
    # Seed is bound to the chain tip. The operator cannot know it before the
    # records exist, and cannot alter it afterwards without breaking the chain.
    seed = _sha(tip + ":" + str(int(ts)) + ":" + field + ":" + str(n))

    # Deterministic selection from the seed - reproducible by anyone holding it.
    scored = sorted(rows, key=lambda r: _sha(seed + ":" + str(r[0])))
    picked = scored[:min(n, len(scored))]

    rid = "RUN-" + seed[:8].upper()
    block_ids = [p[0] for p in picked]

    sample = []
    for bid, uid, res_json, bts in picked:
        try:
            r = json.loads(res_json)
            sealed_val = r.get(field)
        except Exception:
            sealed_val = None
        sample.append({"block_index": bid, "record_id": uid,
                       "sealed_at": _iso(bts),
                       "sealed_value_sha256": _sha(str(sealed_val))})

    detail = ("field=" + field + ";sample_size=" + str(len(picked)) +
              ";seed=" + seed + ";from_tip=" + tip +
              ";blocks=" + ",".join(str(b) for b in block_ids[:60]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "planned", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO reconcile_runs(run_id,api_key,field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,block_ids,detail) VALUES(?,?,?,?,?,NULL,?,NULL,NULL,NULL,'planned',?,NULL)",
                            (rid, api_key, field, seed, ts, len(picked), json.dumps(block_ids)))
        ctx["conn"].commit()

    return {"run_id": rid, "field": field, "sample_size": len(picked),
            "seed": seed, "derived_from_tip": tip, "planned_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "sample": sample,
            "next": "Fetch these record_ids from your own live system and POST them to /x/reconcile/submit",
            "note": "This selection is now sealed. It cannot be changed, and an unsubmitted plan stays visible as an abandoned test."}, 200


def _submit(ctx, api_key, data):
    rid = str(data.get("run_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,status,block_ids FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_run_id"}, 404
    if row[2] != "planned":
        return {"error": "already_submitted",
                "message": "A run is reconciled once. Re-running until it passes is not reconciliation."}, 400

    results = data.get("results")
    if not isinstance(results, dict) or not results:
        return {"error": "results_required",
                "message": "Send {block_index: live_value} from your own system."}, 400

    field = row[0]
    block_ids = json.loads(row[3])

    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT id,user_id,result_json FROM audit_log WHERE id IN (" + ",".join("?" * len(block_ids)) + ")", block_ids).fetchall()

    sealed = {}
    for bid, uid, res_json in rows:
        try:
            sealed[bid] = json.loads(res_json).get(field)
        except Exception:
            sealed[bid] = None

    matched, mismatched, missing = [], [], []
    for bid in block_ids:
        key = str(bid)
        if key not in results:
            missing.append({"block_index": bid})
            continue
        live = results[key]
        want = sealed.get(bid)
        if str(live).strip().lower() == str(want).strip().lower():
            matched.append(bid)
        else:
            mismatched.append({"block_index": bid,
                               "sealed_value": want,
                               "live_value": live})

    ts = time.time()
    rate = round(100 * len(matched) / len(block_ids), 2) if block_ids else 0
    detail = ("field=" + field + ";matched=" + str(len(matched)) +
              ";mismatched=" + str(len(mismatched)) + ";missing=" + str(len(missing)) +
              ";match_rate=" + str(rate) +
              ";mismatch_blocks=" + ",".join(str(m["block_index"]) for m in mismatched[:40]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "reconciled", detail)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE reconcile_runs SET submitted=?,matched=?,mismatched=?,missing=?,status='reconciled',detail=? WHERE run_id=? AND api_key=?",
                            (ts, len(matched), len(mismatched), len(missing), json.dumps({"mismatched": mismatched[:100], "missing": missing[:100]}), rid, api_key))
        ctx["conn"].commit()

    out = {"run_id": rid, "field": field, "sample_size": len(block_ids),
           "matched": len(matched), "mismatched": len(mismatched),
           "missing": len(missing), "match_rate_pct": rate,
           "reconciled_at": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "This result is sealed whichever way it went. It cannot be withdrawn."}
    if mismatched:
        out["mismatches"] = mismatched[:20]
        out["flag"] = "sealed records and live system disagree on " + str(len(mismatched)) + " of " + str(len(block_ids))
    if missing:
        out["missing_detail"] = "records the live system did not return - a gap, not a match"
    return out, 200


def _run(ctx, api_key, rid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,detail FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_run_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("rec:" + rid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("reconcile_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    total = row[4] or 0
    out = {"run_id": rid.upper(), "field": row[0], "seed": row[1],
           "planned": _iso(row[2]), "submitted": _iso(row[3]),
           "sample_size": total, "matched": row[5], "mismatched": row[6],
           "missing": row[7], "status": row[8], "events": events,
           "ordering_proof": "The plan block precedes the result block. The sample was fixed before any data was requested."}
    if row[9]:
        try:
            out["detail"] = json.loads(row[9])
        except Exception:
            pass
    if row[8] == "planned":
        out["flag"] = "planned but never submitted - an abandoned test, visible permanently"
    return out, 200


def _score(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT sample_size,matched,mismatched,missing,status,planned FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 500", (api_key,)).fetchall()
    if not rows:
        return {"runs": 0, "note": "No reconciliation runs on record."}, 200
    done = [r for r in rows if r[4] == "reconciled"]
    abandoned = len(rows) - len(done)
    tested = sum(r[0] or 0 for r in done)
    ok = sum(r[1] or 0 for r in done)
    bad = sum(r[2] or 0 for r in done)
    gone = sum(r[3] or 0 for r in done)
    out = {"runs": len(rows), "reconciled": len(done), "abandoned": abandoned,
           "records_tested": tested, "matched": ok, "mismatched": bad,
           "missing": gone,
           "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
           "last_run": _iso(rows[0][5])}
    if abandoned:
        out["flag"] = str(abandoned) + " planned run(s) never submitted"
    return out, 200


def _list(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,missing,status FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 200", (api_key,)).fetchall()
    return {"count": len(rows),
            "runs": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                      "submitted": _iso(r[3]), "sample_size": r[4],
                      "matched": r[5], "mismatched": r[6], "missing": r[7],
                      "status": r[8]} for r in rows]}, 200


def _public(ctx):
    """The reconciliation record, readable without a key.

    Counts only. No record identifiers, no field values, no operator
    identity. What a stranger gets is the three numbers that cannot be
    flattered: how many runs were reconciled, how many disagreed, and how
    many were planned and then quietly abandoned.

    Abandoned runs are the important one. A planned run is sealed at the
    moment it is planned, so a test that came back badly and was dropped
    cannot be deleted - it sits here forever as a plan with no result.
    """
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,"
            "missing,status FROM reconcile_runs ORDER BY planned DESC LIMIT 200").fetchall()

    done = [r for r in rows if r[8] == "reconciled"]
    abandoned = [r for r in rows if r[8] != "reconciled"]
    tested = sum(r[4] or 0 for r in done)
    ok = sum(r[5] or 0 for r in done)
    bad = sum(r[6] or 0 for r in done)
    gone = sum(r[7] or 0 for r in done)

    out = {
        "runs": len(rows),
        "reconciled": len(done),
        "abandoned": len(abandoned),
        "records_tested": tested,
        "matched": ok,
        "mismatched": bad,
        "missing": gone,
        "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
        "recent": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                    "submitted": _iso(r[3]), "sample_size": r[4],
                    "matched": r[5], "mismatched": r[6], "missing": r[7],
                    "status": r[8]} for r in rows[:50]],
        "check_any_of_them": "/x/reconcile/proof?id=RUN-XXXXXXXX",
        "what_is_being_shown": "Not that the records are true. That the sample was fixed "
                               "before the data was requested, and that what came back was "
                               "sealed either way.",
        "what_a_mismatch_means": "The sealed record and the operator's own live system "
                                 "disagreed. It is published because a reconciliation system "
                                 "that can bury its own failures is decoration.",
    }
    if abandoned:
        out["flag"] = (str(len(abandoned)) + " run(s) planned and never submitted. A sample was "
                       "fixed, and no result was ever sealed against it.")
    return out, 200


def _proof(ctx, rid):
    """The ordering, straight out of the chain, without a key.

    Both events are already sealed under a public identifier, so this route
    reveals nothing the chain does not already carry. It just makes the one
    claim that matters legible: the plan block comes before the result block.
    """
    rid = (rid or "").strip().upper()
    if not rid:
        return {"error": "id_required"}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status "
            "FROM reconcile_runs WHERE run_id=?", (rid,)).fetchone()
        blocks = ctx["conn"].execute(
            "SELECT id,ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC",
            ("rec:" + rid,)).fetchall()
    if not row:
        return {"error": "unknown_run_id", "list": "/x/reconcile/public"}, 404

    events = []
    plan_block = result_block = None
    for bid, bts, res, ah in blocks:
        try:
            r = json.loads(res)
        except Exception:
            continue
        what = r.get("reconcile_action")
        events.append({"event": what, "at": _iso(bts), "block_index": bid,
                       "sealed_in_chain": ah, "sealed_detail": r.get("detail")})
        if what == "planned" and plan_block is None:
            plan_block = bid
        if what == "reconciled" and result_block is None:
            result_block = bid

    ordered = (plan_block is not None and result_block is not None
               and plan_block < result_block)

    out = {"run_id": rid, "field": row[0], "status": row[8],
           "seed": row[1], "planned_at": _iso(row[2]), "submitted_at": _iso(row[3]),
           "sample_size": row[4], "matched": row[5], "mismatched": row[6],
           "missing": row[7],
           "plan_block_index": plan_block, "result_block_index": result_block,
           "selection_precedes_result": ordered,
           "events": events,
           "how_to_check_this_yourself": [
               "The seed is derived from the chain tip at planning time, which the operator "
               "cannot predict in advance or change afterwards without breaking the chain.",
               "The plan block seals which records were selected, and its detail is above.",
               "The result block seals what came back. Compare the two block indices.",
               "A lower plan index than result index means the sample was fixed before any "
               "data was requested. That is the whole claim, and it is the only one made."],
           "what_this_does_not_prove": "That the records are true. Two systems the operator "
                                       "controls agreeing with each other is consistency, not "
                                       "truth."}
    if row[8] != "reconciled":
        out["flag"] = ("planned and never submitted. The selection is sealed and no result "
                       "was ever put against it.")
    elif not ordered:
        out["flag"] = ("the plan block does not precede the result block. That should be "
                       "impossible and it is the finding.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "plan":
            return _plan(ctx, api_key, data)
        if action == "submit":
            return _submit(ctx, api_key, data)
    else:
        if action == "public":
            return _public(ctx)
        if action == "proof":
            return _proof(ctx, str((data or {}).get("id", "")))
        if action == "score":
            return _score(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "run":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _run(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action,
            "GET": ["public", "proof", "score", "list", "run"],
            "POST": ["plan", "submit"]}, 404

```
