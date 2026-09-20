"""
modules/held.py  v1.0  -  the tips sebbi.pro holds for other chains

Every time a peer submits its tip, sebbi.pro seals the observation into its
own chain as a block under user_id "wit:<peer>", with the peer's tip inside.
Those blocks are already public in the walk. This module lists them per
peer, so another chain can point a verifier at sebbi.pro as its witness and
have a machine confirm it.

Reads only. Seals nothing, writes nothing, creates no tables. All public.

Routes:
  https://sebbi.pro/x/held/status
  https://sebbi.pro/x/held/peers
  https://sebbi.pro/x/held/tips?peer=mir
"""

import json
import re
import time

VERSION = "1.0"
BASE = "https://sebbi.pro/x/held/"
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "peers"),
          ("GET", "tips")}

_PEER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _q(data, name, default=None):
    v = (data or {}).get(name, default)
    if isinstance(v, list):
        v = v[0] if v else default
    return v


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _peers(ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT user_id, COUNT(*), MAX(id), MAX(ts) FROM audit_log "
            "WHERE user_id LIKE 'wit:%' GROUP BY user_id").fetchall()
    out = []
    for uid, n, last_idx, last_ts in rows:
        name = str(uid)[4:]
        out.append({"peer": name, "tips_held": n,
                    "last_block_index": last_idx,
                    "last_observed_at": _iso(last_ts),
                    "list": BASE + "tips?peer=" + name})
    out.sort(key=lambda r: -(r["tips_held"] or 0))
    return {"ok": True, "holder": "sebbi.pro", "count": len(out),
            "peers": out}, 200


def _tips(data, ctx):
    peer = str(_q(data, "peer", "") or "").strip().lower()
    if not _PEER_RE.match(peer):
        return {"ok": False, "error": "peer_required",
                "example": BASE + "tips?peer=mir",
                "peers": BASE + "peers"}, 400
    try:
        limit = max(1, min(MAX_LIMIT, int(_q(data, "limit", DEFAULT_LIMIT))))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            ("wit:" + peer, limit)).fetchall()
    tips = []
    for idx, ts, h, rj in rows:
        try:
            res = json.loads(rj)
        except Exception:
            res = {}
        tip = str(res.get("peer_tip") or "").lower()
        if not re.match(r"^[0-9a-f]{64}$", tip):
            continue
        tips.append({
            "peer_tip": tip,
            "observed_at": _iso(ts),
            "liveness": res.get("liveness"),
            "sealed_in_block": idx,
            "sealed_block_hash": h,
            "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
        })
    return {
        "ok": True,
        "holder": "sebbi.pro",
        "peer": peer,
        "count": len(tips),
        "newest_first": True,
        "tips": tips,
        "what_this_proves": (
            "sebbi.pro recorded each of these tips from %s and sealed the "
            "observation into its own public chain. Open check_block to see "
            "the sealed block, recompute its hash, and confirm peer_tip is "
            "inside it. sebbi.pro is run independently of %s and cannot be "
            "made to rewrite these blocks by %s." % (peer, peer, peer)),
        "what_this_does_not_prove": (
            "That the tip was correct when submitted - only that this is the "
            "tip sebbi.pro was shown, and when."),
    }, 200


def _status():
    return {"ok": True, "module": "held", "version": VERSION,
            "what": "Tips sebbi.pro holds for other chains, from its own "
                    "sealed witness blocks.",
            "routes": {"peers": BASE + "peers",
                       "tips": BASE + "tips?peer=mir",
                       "status": BASE + "status"},
            "use_as_witness": "In an AI Integrity Declaration, set a "
                              "witness tip_endpoint to " + BASE +
                              "tips?peer=<your peer name>. The checker at "
                              "https://sebbi.pro/x/integrity/check then "
                              "confirms sebbi.pro holds your tip."}


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action in ("status", "spec", ""):
            return _status(), 200
        if method == "GET" and action == "peers":
            return _peers(ctx)
        if method == "GET" and action == "tips":
            return _tips(data, ctx)
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": []}, 404
    except Exception as exc:
        return {"ok": False, "error": "held_failed",
                "detail": str(exc)[:200]}, 500
