# ----------------------------------------------------------------------
# Schema addition inside _setup(ctx)
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
        c.execute("CREATE TABLE IF NOT EXISTS signed_seq("
                  "peer TEXT PRIMARY KEY, last_seq INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_peer ON signed_log(peer,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_tip ON signed_log(tip)")
        c.commit()
    _ready = True


def _next_receipt_seq(ctx, peer):
    """Monotonic gapless sequence counter per peer chain."""
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("INSERT INTO signed_seq(peer, last_seq) VALUES(?, 1) "
                  "ON CONFLICT(peer) DO UPDATE SET last_seq = last_seq + 1", (peer,))
        seq = c.execute("SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()[0]
        c.commit()
        return seq


# ----------------------------------------------------------------------
# Updated _submit(ctx, data)
# ----------------------------------------------------------------------
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
    pubkey, _enrolled, _h, _idx, rotations, last_ts = row

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

    # Execute seal safely
    try:
        h, idx, _ = ctx["seal"](ev, res, observed, "public-signed")
        if not h:
            raise ValueError("Seal returned empty hash")
    except Exception as e:
        return {"error": "seal_failed",
                "message": "Failed to seal submission into the witness chain. Nothing was saved.",
                "detail": str(e)}, 500

    # Assign gapless sequence only after successful seal
    seq = _next_receipt_seq(ctx, peer)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO signed_log(peer,tip,peer_ts,observed,signature,"
            "pubkey,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?)",
            (peer, tip, float(ts_int), observed, signature, pubkey, h, idx))
        ctx["conn"].execute("UPDATE signed_keys SET last_ts=? WHERE peer=?",
                            (float(ts_int), peer))
        ctx["conn"].commit()

    mirrored = False
    try:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,"
                "audit_hash,block_index,note,url,liveness,name_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("public-signed", peer, tip, float(ts_int), observed, h, idx,
                 "signed submission - verified against enrolled Ed25519 key",
                 None, "peer-signed", "key-bound"))
            ctx["conn"].commit()
        mirrored = True
    except Exception:
        pass

    return {"chain": peer, "witnessed_tip": tip, "observed_at": _iso(observed),
            "peer_claimed_time": _iso(ts_int),
            "sealed_in_our_chain": h, "block_index": idx,
            "receipt_seq": seq, "key_seq": (rotations or 0) + 1,
            "verification": "peer-signed",
            "verified_against_pubkey": pubkey,
            "on_public_roster": mirrored,
            "signed_version": VERSION,
            "verify": "/x/signed/verify?peer=" + peer + "&tip=" + tip,
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200
