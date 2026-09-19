"""
disclosure.py v1.0.0 - the chain reset, put on the record inside the chain.

Lives at modules/disclosure.py and answers at https://sebbi.pro/x/disclosure/<action>.
All routes are public.

WHAT IT DOES
The audit chain restarted from genesis on 7 September 2026. Until now that
was said in messages and in route text, but not sealed. This module seals one
fixed statement about the reset into the chain, exactly once, and then serves
the block number so anyone can find it and recompute it.

The first visit to /status seals it. Every visit after that returns the same
block. Nothing is ever sealed twice, and the text cannot be changed by calling
the route - it is fixed in this file.

The statement is sealed under user_id "system_reset_disclosure", which is on
the public list in walk.py, so its full preimage is served at /x/walk and can be
recomputed by anyone.

Module contract: handle(method, action, data, api_key, ctx) -> (dict, status).
"""

import json
import threading
import time

VERSION = "1.0.0"
HOST = "https://sebbi.pro"
BASE = HOST + "/x/disclosure/"
USER_ID = "system_reset_disclosure"

RESET_DATE = "2026-09-07"

# If you still hold the final tip hash or block count of the chain as it stood
# before the reset, put them here before deploying. Left empty, the statement
# says plainly that they are not recorded in this disclosure.
PREVIOUS_CHAIN_FINAL_TIP = ""
PREVIOUS_CHAIN_FINAL_HEIGHT = ""

STATEMENT = (
    "On " + RESET_DATE + " the operator of sebbi.pro reset the audit chain and "
    "it restarted from genesis. Blocks sealed before that date are not part of "
    "this chain and cannot be verified against it. A block index quoted before "
    "that date belongs to the earlier chain; if the same number exists on this "
    "chain, it is a different block. Some records kept outside the chain from "
    "before the reset, including completeness period commitments, still quote "
    "block indexes from the earlier chain. This disclosure is sealed into the "
    "current chain so the break is on the record rather than something a "
    "verifier has to ask about."
)

_lock = threading.Lock()

PUBLIC = {("GET", "status"), ("GET", "statement"), ("GET", "spec")}


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reset_disclosure("
        "id INTEGER PRIMARY KEY CHECK (id = 1), block_index INTEGER, "
        "audit_hash TEXT, ts REAL, statement_json TEXT)")
    conn.commit()


def _stored(conn):
    r = conn.execute(
        "SELECT block_index, audit_hash, ts, statement_json FROM reset_disclosure "
        "WHERE id = 1").fetchone()
    if not r:
        return None
    try:
        body = json.loads(r[3])
    except Exception:
        body = {}
    return {"block_index": r[0], "audit_hash": r[1], "ts": r[2], "statement": body}


def _genesis_hash(conn):
    r = conn.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1").fetchone()
    return r[0] if r else None


def _links(rec):
    idx = rec["block_index"]
    return {
        "block": HOST + "/x/walk/block?index=" + str(idx),
        "verify_method": HOST + "/x/walk/spec",
        "statement": BASE + "statement",
    }


def _seal_once(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with _lock:
        with dblock:
            _ensure_table(conn)
            rec = _stored(conn)
            if rec:
                return rec, False
            genesis = _genesis_hash(conn)
        body = {
            "kind": "chain_reset_disclosure",
            "reset_date": RESET_DATE,
            "current_chain_genesis_hash": genesis,
            "current_chain_genesis_block_index": 1,
            "previous_chain_final_tip": PREVIOUS_CHAIN_FINAL_TIP or "not recorded in this disclosure",
            "previous_chain_final_height": PREVIOUS_CHAIN_FINAL_HEIGHT or "not recorded in this disclosure",
            "statement": STATEMENT,
            "disclosure_version": VERSION,
        }
        ts = time.time()
        event = {
            "user_id": USER_ID,
            "action": "chain_reset_disclosed",
            "amount": 0,
            "country": "UK",
            "device_id": "server",
            "anomaly": 0,
            "device_risk": 0,
        }
        result = dict(body)
        result["decision"] = "DISCLOSED"
        result["score"] = 0
        result["timestamp"] = ts
        # ctx seal takes its own lock - do not hold the db lock here.
        out = ctx["seal"](event, result, ts)
        if isinstance(out, (list, tuple)):
            h = out[0]
            idx = out[1] if len(out) > 1 else None
        elif isinstance(out, dict):
            h = out.get("audit_hash") or out.get("hash")
            idx = out.get("block_index") or out.get("index")
        else:
            h, idx = out, None
        with dblock:
            conn.execute(
                "INSERT OR IGNORE INTO reset_disclosure(id, block_index, audit_hash, ts, statement_json) "
                "VALUES (1, ?, ?, ?, ?)", (idx, h, ts, json.dumps(body)))
            conn.commit()
            rec = _stored(conn)
        return rec, True


def _spec():
    return {
        "module": "disclosure",
        "version": VERSION,
        "purpose": "Seals one fixed statement about the " + RESET_DATE + " chain reset "
                   "into the current chain, once, and serves where it is.",
        "routes": {
            "status": BASE + "status",
            "statement": BASE + "statement",
            "spec": BASE + "spec",
        },
        "behaviour": "The first call to status seals the statement. Every later call "
                     "returns the same block. The text is fixed in the module and "
                     "cannot be changed through any route.",
        "verify": "Open the block link in the response. Its preimage is served in full; "
                  "sha256 of it must equal audit_hash, and its prev_hash must equal the "
                  "block before. Method: " + HOST + "/x/walk/spec",
    }


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action == "spec":
            return _spec(), 200
        if method == "GET" and action == "status":
            rec, new = _seal_once(ctx)
            if not rec or rec.get("block_index") is None:
                return {"error": "seal_failed", "detail": "no block index returned"}, 500
            return {
                "module": "disclosure",
                "version": VERSION,
                "sealed": True,
                "sealed_just_now": new,
                "block_index": rec["block_index"],
                "audit_hash": rec["audit_hash"],
                "sealed_at": rec["ts"],
                "links": _links(rec),
                "statement": rec["statement"],
            }, 200
        if method == "GET" and action == "statement":
            conn, dblock = ctx["conn"], ctx["lock"]
            with dblock:
                _ensure_table(conn)
                rec = _stored(conn)
            if not rec:
                return {"sealed": False,
                        "note": "Not sealed yet. The first visit to " + BASE + "status seals it."}, 404
            return {"sealed": True, "block_index": rec["block_index"],
                    "audit_hash": rec["audit_hash"], "sealed_at": rec["ts"],
                    "links": _links(rec), "statement": rec["statement"]}, 200
        return {"error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": [], "spec": BASE + "spec"}, 404
    except Exception as e:
        return {"error": "disclosure_failed", "detail": str(e)[:300]}, 500
