"""
walk.py v1.0.0 - the whole chain, genesis to tip, readable by anyone.

Lives at modules/walk.py and answers at https://sebbi.pro/x/walk/<action>.
Every route is public. Nothing is written, nothing is sealed, no table is
created. It only reads audit_log.

WHY IT EXISTS
Until now nobody outside could walk the chain end to end: /api/verify-chain
returns a count and a tip, and /x/witness/chain needs a key. A verifier could
check pieces (inclusion, consistency, witnessed tips) but never the whole run
from the first block. This serves every block in write order, from genesis,
in pages, so the full walk can be done from outside without asking anyone.

HOW A BLOCK IS SEALED (server.py seal(), unchanged)
    audit_hash = sha256( json.dumps(
        {"prev_hash": prev, "ts": ts, "event": event, "result": result},
        sort_keys=True).encode() ).hexdigest()
    The first block's prev is the literal string "GENESIS".

WHAT A VERIFIER DOES WITH THIS
For a public block the exact preimage string is served. So, in any language:
    1. sha256(utf8(preimage)) must equal audit_hash
    2. parse preimage; its prev_hash must equal the previous block's audit_hash
    3. the first block's prev_hash must be "GENESIS"
No need to copy Python's JSON formatting - the bytes that were hashed are given.

WHAT IS WITHHELD, AND WHY
Blocks sealed under a customer's API key, blocks from sources not on the public
list below, and any block whose payload contains a field that looks like a
secret, are served WITHOUT their payload: index, position, time, prev_hash and
audit_hash only. Publishing customer decisions or child-safety events to the
open internet is not something a verification route gets to decide. For a
withheld block an outsider can check linkage but cannot recompute the hash; the
customer who holds the original event can. Every withheld block says why.

THE RESET
The chain restarted from genesis on 7 September 2026. A block index quoted
before that date belongs to the earlier chain. If the same number exists here,
it is a different block.

Module contract: handle(method, action, data, api_key, ctx) -> (dict, status).
"""

import json
import hashlib
import re
import threading

VERSION = "1.0.0"
HOST = "https://sebbi.pro"
BASE = HOST + "/x/walk/"
GENESIS_PREV = "GENESIS"
RESET_DATE = "2026-09-07"
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# user_id prefixes whose payloads are protocol traffic and safe to publish.
# Anything not starting with one of these is withheld. Extend here, one line.
PUBLIC_PREFIXES = (
    "wit:",
    "peer:",
    "praxis:",
    "bind:",
    "signed:",
    "system_",
    "public-witness",
)

# Field names that must never be published, anywhere in a payload.
SENSITIVE_KEY = re.compile(
    r"(secret|password|passwd|passcode|token|api_?key|credential|private|"
    r"seed|authori[sz]ation|bearer|cookie|session|^pin$)",
    re.I,
)
# Values that look like AILeash API keys.
SENSITIVE_VALUE = re.compile(r"^(al|sb|se)_live_[0-9a-f]{16,}")

PUBLIC = {
    ("GET", "spec"),
    ("GET", "status"),
    ("GET", "genesis"),
    ("GET", "blocks"),
    ("GET", "block"),
    ("GET", "verify"),
}

WHAT_THIS_PROVES = (
    "For public blocks: that each served preimage hashes to the stored "
    "audit_hash and names the previous block's hash, from genesis forward. "
    "For withheld blocks: only that the stored links are continuous - the "
    "hash cannot be recomputed without the payload. Pair the tip with a "
    "witnessed or anchored tip to show this chain is the one other parties "
    "saw. This route is served by the operator; the evidence is the "
    "arithmetic you do on it, not the operator's word."
)

RESET_NOTE = (
    "This chain restarted from genesis on " + RESET_DATE + ". A block index "
    "quoted before that date belongs to the earlier chain. If the same number "
    "exists here, it is a different block."
)

_cache_lock = threading.Lock()
_cache = {"key": None, "result": None}


# ---------------------------------------------------------------- helpers

def _q(data, name, default=None):
    if not isinstance(data, dict):
        return default
    v = data.get(name, default)
    if isinstance(v, list):
        v = v[0] if v else default
    return v


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _preimage(prev, ts, event, result):
    return json.dumps(
        {"prev_hash": prev, "ts": ts, "event": event, "result": result},
        sort_keys=True,
    )


def _has_api_key_col(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    return "api_key" in cols


def _select(conn):
    ak = "api_key" if _has_api_key_col(conn) else "''"
    return ("SELECT id, ts, user_id, event_json, result_json, prev_hash, "
            "audit_hash, " + ak + " FROM audit_log")


def _scan(obj):
    """True if any key or string value looks like a secret."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if SENSITIVE_KEY.search(str(k)):
                return True
            if _scan(v):
                return True
    elif isinstance(obj, list):
        for v in obj:
            if _scan(v):
                return True
    elif isinstance(obj, str):
        if SENSITIVE_VALUE.match(obj):
            return True
    return False


def _classify(user_id, api_key, event, result):
    if api_key:
        return False, "customer_key"
    uid = str(user_id or "")
    if not uid.startswith(PUBLIC_PREFIXES):
        return False, "not_on_public_list"
    if _scan(event) or _scan(result):
        return False, "sensitive_field"
    return True, None


def _prefix(uid):
    uid = str(uid or "")
    return uid.split(":")[0] + ":" if ":" in uid else uid[:12]


def _block(row, position):
    bid, ts, uid, ej, rj, prev, h, ak = row
    out = {
        "block_index": bid,
        "position": position,
        "ts": ts,
        "prev_hash": prev,
        "audit_hash": h,
    }
    try:
        event = json.loads(ej)
        result = json.loads(rj)
    except Exception:
        out["payload"] = "withheld"
        out["withheld_reason"] = "unparseable"
        out["server_recomputes"] = False
        return out, False, "unparseable"
    pre = _preimage(prev, ts, event, result)
    out["server_recomputes"] = (_sha(pre) == h)
    public, reason = _classify(uid, ak, event, result)
    if public:
        out["preimage"] = pre
    else:
        out["payload"] = "withheld"
        out["withheld_reason"] = reason
    return out, public, reason


def _position_of(conn, bid):
    """Zero-based write-order position of block bid."""
    r = conn.execute("SELECT COUNT(*) FROM audit_log WHERE id < ?", (bid,)).fetchone()
    return r[0] if r else 0


def _hash_before(conn, bid):
    r = conn.execute(
        "SELECT audit_hash FROM audit_log WHERE id < ? ORDER BY id DESC LIMIT 1",
        (bid,)).fetchone()
    return r[0] if r else GENESIS_PREV


def _full_walk(ctx):
    """Walk every block once. Cached until the chain grows."""
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        key = conn.execute("SELECT COUNT(*), MAX(id) FROM audit_log").fetchone()
    with _cache_lock:
        if _cache["key"] == key and _cache["result"] is not None:
            return _cache["result"]
    with lock:
        rows = conn.execute(_select(conn) + " ORDER BY id ASC").fetchall()

    withheld = {}
    hidden_prefixes = {}
    public_count = 0
    links_ok = True
    recompute_ok = True
    first_break = None
    prev_hash = GENESIS_PREV
    for pos, row in enumerate(rows):
        blk, public, reason = _block(row, pos)
        if public:
            public_count += 1
        else:
            withheld[reason] = withheld.get(reason, 0) + 1
            if reason == "not_on_public_list":
                p = _prefix(row[2])
                hidden_prefixes[p] = hidden_prefixes.get(p, 0) + 1
        if blk["prev_hash"] != prev_hash:
            links_ok = False
            if first_break is None:
                first_break = {"block_index": blk["block_index"], "position": pos,
                               "problem": "prev_hash does not match the previous block"}
        if not blk["server_recomputes"]:
            recompute_ok = False
            if first_break is None:
                first_break = {"block_index": blk["block_index"], "position": pos,
                               "problem": "stored payload does not recompute to audit_hash"}
        prev_hash = blk["audit_hash"]

    result = {
        "blocks": len(rows),
        "first_block_index": rows[0][0] if rows else None,
        "last_block_index": rows[-1][0] if rows else None,
        "genesis_hash": rows[0][6] if rows else None,
        "genesis_prev_is_GENESIS": (rows[0][5] == GENESIS_PREV) if rows else None,
        "tip": rows[-1][6] if rows else None,
        "links_ok": links_ok,
        "recompute_ok": recompute_ok,
        "first_break": first_break,
        "public_blocks": public_count,
        "withheld_blocks": withheld,
    }
    if hidden_prefixes:
        print("WALK not_on_public_list prefixes: " +
              json.dumps(hidden_prefixes, sort_keys=True), flush=True)
    with _cache_lock:
        _cache["key"] = key
        _cache["result"] = result
    return result


# ---------------------------------------------------------------- routes

def _spec():
    return {
        "module": "walk",
        "version": VERSION,
        "purpose": "Every block of the chain, genesis to tip, in write order, "
                   "public, so the whole chain can be walked from outside.",
        "routes": {
            "status": BASE + "status",
            "genesis": BASE + "genesis",
            "blocks": BASE + "blocks?after=0&limit=" + str(DEFAULT_LIMIT),
            "block": BASE + "block?index=1",
            "verify": BASE + "verify",
            "spec": BASE + "spec",
        },
        "paging": "blocks?after=<block_index>&limit=<1-" + str(MAX_LIMIT) + ">. "
                  "Start with after=0. Each page gives previous_audit_hash (the "
                  "hash of the block just before the page) and next_after for "
                  "the next call. has_more false means you have reached the tip.",
        "seal_formula": "audit_hash = sha256(json.dumps({\"prev_hash\": prev, "
                        "\"ts\": ts, \"event\": event, \"result\": result}, "
                        "sort_keys=True)). First block prev = \"GENESIS\".",
        "verify_steps": [
            "sha256(utf8(preimage)) must equal audit_hash",
            "json-parse preimage; its prev_hash must equal the previous block's audit_hash",
            "the first block's prev_hash must be the literal string GENESIS",
            "for withheld blocks, check prev_hash equals the previous audit_hash (linkage only)",
        ],
        "fields": {
            "block_index": "the database id - the number receipts quote as block_index",
            "position": "zero-based order in the chain. This is the leaf index in "
                        "the RFC 6962 tree at " + HOST + "/x/consistency/root. "
                        "block_index and position are different numbers; do not mix them",
            "preimage": "the exact string that was hashed (public blocks only)",
            "server_recomputes": "our own server's check that the stored row hashes "
                                 "to audit_hash. Our word, not proof - recompute it yourself",
            "withheld_reason": "customer_key | not_on_public_list | sensitive_field | unparseable",
        },
        "withholding": "Blocks sealed under a customer API key, blocks from sources "
                       "not on the public list, and payloads carrying anything that "
                       "looks like a secret are served without payload. Linkage stays "
                       "checkable; the hash is recomputable only by whoever holds the "
                       "original event.",
        "public_sources": list(PUBLIC_PREFIXES),
        "reset": RESET_NOTE,
        "what_this_proves": WHAT_THIS_PROVES,
    }


def _status(ctx):
    w = _full_walk(ctx)
    out = {
        "module": "walk",
        "version": VERSION,
        "blocks": w["blocks"],
        "first_block_index": w["first_block_index"],
        "last_block_index": w["last_block_index"],
        "genesis_hash": w["genesis_hash"],
        "tip": w["tip"],
        "public_blocks": w["public_blocks"],
        "withheld_blocks": w["withheld_blocks"],
        "start_here": BASE + "blocks?after=0&limit=" + str(DEFAULT_LIMIT),
        "reset": RESET_NOTE,
        "what_this_proves": WHAT_THIS_PROVES,
    }
    return out


def _genesis(ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        row = conn.execute(_select(conn) + " ORDER BY id ASC LIMIT 1").fetchone()
    if not row:
        return {"error": "empty_chain"}, 404
    blk, _, _ = _block(row, 0)
    return {
        "genesis": blk,
        "prev_is_GENESIS": row[5] == GENESIS_PREV,
        "reset": RESET_NOTE,
        "next": BASE + "blocks?after=" + str(row[0]) + "&limit=" + str(DEFAULT_LIMIT),
    }, 200


def _blocks(data, ctx):
    after = _int(_q(data, "after", 0), 0, 0, 10 ** 12)
    limit = _int(_q(data, "limit", DEFAULT_LIMIT), DEFAULT_LIMIT, 1, MAX_LIMIT)
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(_select(conn) + " WHERE id > ? ORDER BY id ASC LIMIT ?",
                            (after, limit + 1)).fetchall()
        if rows:
            base = _position_of(conn, rows[0][0])
            prev_hash = _hash_before(conn, rows[0][0])
        else:
            base, prev_hash = None, None
    has_more = len(rows) > limit
    rows = rows[:limit]
    out_blocks = []
    for i, row in enumerate(rows):
        blk, _, _ = _block(row, base + i)
        out_blocks.append(blk)
    out = {
        "after": after,
        "count": len(out_blocks),
        "previous_audit_hash": prev_hash,
        "blocks": out_blocks,
        "has_more": has_more,
    }
    if out_blocks:
        last = out_blocks[-1]["block_index"]
        out["next_after"] = last
        if has_more:
            out["next"] = BASE + "blocks?after=" + str(last) + "&limit=" + str(limit)
    return out, 200


def _one(data, ctx):
    idx = _int(_q(data, "index"), None, 0, 10 ** 12)
    if idx is None:
        return {"error": "index_required", "example": BASE + "block?index=1"}, 400
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        row = conn.execute(_select(conn) + " WHERE id = ?", (idx,)).fetchone()
        if not row:
            return {"error": "not_on_this_chain", "block_index": idx,
                    "reset": RESET_NOTE}, 404
        pos = _position_of(conn, idx)
        prev_hash = _hash_before(conn, idx)
    blk, _, _ = _block(row, pos)
    return {
        "block": blk,
        "previous_audit_hash": prev_hash,
        "link_ok": blk["prev_hash"] == prev_hash,
        "reset": RESET_NOTE,
    }, 200


def _verify(ctx):
    w = _full_walk(ctx)
    out = dict(w)
    out["valid"] = bool(w["blocks"]) and w["links_ok"] and w["recompute_ok"] \
        and bool(w["genesis_prev_is_GENESIS"])
    out["note"] = ("This is our server checking itself. It is a convenience, "
                   "not evidence. Walk " + BASE + "blocks?after=0 and do the "
                   "arithmetic yourself.")
    return out


# ---------------------------------------------------------------- entry

def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET":
            if action == "spec":
                return _spec(), 200
            if action == "status":
                return _status(ctx), 200
            if action == "genesis":
                return _genesis(ctx)
            if action == "blocks":
                return _blocks(data, ctx)
            if action == "block":
                return _one(data, ctx)
            if action == "verify":
                return _verify(ctx), 200
        return {
            "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": [],
            "spec": BASE + "spec",
        }, 404
    except Exception as e:
        return {"error": "walk_failed", "detail": str(e)[:300]}, 500
