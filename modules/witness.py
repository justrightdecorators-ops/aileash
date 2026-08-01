"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control - and those chains are
themselves anchored externally.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step, and re-anchor all of it. That is not a
technical exercise. That is a conspiracy, and it grows harder with every
platform that joins.

That is an integrity property no single vendor can offer alone. It is not
bought, it is not licensed, and no company owns it.

WHY IT COSTS NOTHING
--------------------
A tip is 64 characters. Witnessing one is a single sealed block. Ten peers
exchanging tips hourly is a few hundred blocks a day between them.

WHY observe IS OPEN
-------------------
A witnessing network that only accepts tips from account holders is not a
witnessing network, it is a customer list. Anyone must be able to hand us a
tip without asking permission, or the claim that the network is open is not
true. Unauthenticated observations are filed under ANON_KEY rather than a
customer key, and the router meters them per client address.

The tradeoff, stated plainly: the peer name is self-declared, so anyone can
submit under any name. That is why /x/witness/peers reports observation
counts and staleness rather than endorsements - a name in that list is a
claim, not a credential, and the history behind it is what carries weight.

HONEST LIMITS
-------------
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- A peer can stop publishing. Gaps in a peer's witness history are visible,
  which is the point, but nobody can force participation.
- Two colluding platforms witnessing only each other prove very little. The
  guarantee comes from breadth - witness widely, and publish who witnesses you
  so anyone can judge for themselves.
- This module does not verify a peer's chain is internally valid. It records
  what they claimed and when. Verification is the peer's own endpoint to offer.

    GET  /x/witness/tip                 our current tip, for peers to record
    POST /x/witness/observe             peer, tip  - we seal their tip
    GET  /x/witness/attest?peer=&tip=   did we witness this, and when
    GET  /x/witness/peers               who we witness, and how consistently
    GET  /x/witness/history?peer=       every tip we hold for that peer
"""

import json, re, time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true. Everything else stays behind a key.
#
# observe is here as well: submitting a tip is how you join, and requiring
# a key to join makes the network closed by definition.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("POST", "observe")}

# Observations arriving without a key are filed under this instead. Keeps
# NULL out of the witness_log partition and out of seal().
ANON_KEY = "public-witness"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS witness_log(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,peer TEXT,tip TEXT,peer_ts REAL,observed REAL,audit_hash TEXT,block_index INTEGER,note TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_wit_peer ON witness_log(api_key,peer)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_wit_tip ON witness_log(tip)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _our_tip(ctx):
    with ctx["lock"]:
        r = ctx["conn"].execute("SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def _tip(ctx, api_key):
    tip, ts, height = _our_tip(ctx)
    return {"tip": tip, "height": height, "sealed_at": _iso(ts),
            "witness_version": VERSION,
            "note": "Record this tip in your own chain. Hand us yours at /x/witness/observe and we will record it in ours.",
            "verify": "/api/verify-chain checks this chain end to end. /api/anchor-status shows the external timestamp."}, 200


def _observe(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "peer_required", "message": "A short stable identifier - a domain works well."}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400

    peer_ts = data.get("peer_ts")
    try:
        peer_ts = float(peer_ts) if peer_ts else None
    except Exception:
        peer_ts = None

    ts = time.time()
    note = ""

    with ctx["lock"]:
        prev = ctx["conn"].execute("SELECT tip,observed FROM witness_log WHERE api_key=? AND peer=? ORDER BY id DESC LIMIT 1", (api_key, peer)).fetchone()
        seen = ctx["conn"].execute("SELECT observed FROM witness_log WHERE api_key=? AND peer=? AND tip=? LIMIT 1", (api_key, peer, tip)).fetchone()

    if seen:
        note = "tip already witnessed at " + str(_iso(seen[0])) + " - chain has not advanced, or history was replayed"
    elif prev and prev[0] == tip:
        note = "unchanged since last observation"

    detail = ("peer=" + peer + ";tip=" + tip + ";peer_ts=" + str(peer_ts) +
              (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note) VALUES(?,?,?,?,?,?,?,?)",
                            (api_key, peer, tip, peer_ts, ts, h, idx, note or None))
        ctx["conn"].commit()

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": "Your tip is now inside a chain you do not control, and ours is anchored externally."}
    if note:
        out["flag"] = note
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": "We hold no record of this tip from this peer."}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "proof": "This observation is a block in our chain. Altering or removing it breaks every block after it, and our chain is externally anchored."}, 200


def _peers(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()
    t = time.time()
    peers = []
    for p, n, first, last, distinct in rows:
        hours = round((t - last) / 3600, 1)
        peers.append({"peer": p, "observations": n, "distinct_tips": distinct,
                      "first_seen": _iso(first), "last_seen": _iso(last),
                      "hours_since_last": hours,
                      "status": ("current" if hours < 6 else "stale" if hours < 48 else "silent")})
    return {"count": len(peers), "peers": peers,
            "note": "Silent peers are visible by design. A network you cannot audit is not a network."}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT 500", (api_key, peer)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows),
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4]} for r in rows],
            "note": "If this peer ever presents a history whose tips do not match these, the divergence is provable."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "observe":
            # No key needed. Anonymous submissions are partitioned under
            # ANON_KEY so they never mix with a customer's own witness log.
            return _observe(ctx, api_key or ANON_KEY, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
    else:
        if action == "tip":
            return _tip(ctx, api_key)
        if action == "peers":
            return _peers(ctx, api_key)
        if action == "attest":
            return _attest(ctx, api_key, data)
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404
