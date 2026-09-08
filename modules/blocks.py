"""
modules/blocks.py  v1.0.0
=========================
Paged reads of the audit chain, for the command centre.

WHY THIS EXISTS
---------------
/admin/audit calls verify_chain() on every single request. That rewalks and
rehashes every block in the chain while holding the database lock, so the
cost of asking for twenty rows is the cost of re-verifying the whole log.
On a single replica that hold is long enough for Railway to decide the app
has stopped responding, and the container gets killed -- which also wipes
the in-memory admin tokens, so the next call comes back 401.

This module does the one thing the block view actually needs: read rows.
No verification, no rehashing, no full-table walk. Verification stays where
it belongs, on its own route, run deliberately.

WHAT IT ADDS
------------
offset. /admin/audit has no offset and caps at 1000, so nothing older than
the newest thousand blocks could ever be reached. This pages through the
entire chain, oldest to newest or newest to oldest, in small bites.

ROUTES
------
  GET  /x/blocks/status                       module state and row count
  GET  /x/blocks/list?limit=&offset=&order=   a page of blocks
  GET  /x/blocks/get?seq=                     one block in full
  GET  /x/blocks/around?seq=&span=            a window either side of a block
  GET  /x/blocks/links?limit=&offset=         link check over a page only
  GET  /x/blocks/spec                         what this serves

Every route is keyed. Audit rows are not public.

LINK CHECKING
-------------
/links checks prev_hash against the preceding row's audit_hash across the
page you asked for, and nothing else. It reports which pairs it compared so
a caller can never mistake a clean page for a clean chain. Whole-chain
verification is /api/verify-chain and is deliberately not duplicated here.
"""

import json

VERSION = "1.0.0"

# Nothing here is public. Audit rows are customer data.
PUBLIC = set()

MAX_LIMIT = 200          # a page, not a dump
DEFAULT_LIMIT = 50
MAX_SPAN = 100


def _ctx_get(ctx, name):
    """ctx may be an object with attributes or a plain dict, depending on how
    the router builds it. Take either rather than assuming."""
    v = getattr(ctx, name, None)
    if v is None and isinstance(ctx, dict):
        v = ctx.get(name)
    return v


class _NoLock(object):
    """Used only if the router hands us no lock, so a missing lock degrades
    to running without one instead of raising on entry."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _one(v):
    """A query value can arrive as a string or as a one-item list, depending
    on how the querystring was parsed. Take either."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else ""
    return v


def _cols(conn):
    try:
        return set(r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall())
    except Exception:
        return set()


def _int(data, name, default, lo, hi):
    try:
        v = int(_one(data.get(name, default)))
    except Exception:
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _str(data, name, default=""):
    v = _one(data.get(name, default))
    return "" if v is None else str(v).strip()


def _row(r, cols):
    """Shape one row. Column names are read from the live schema rather than
    assumed, so a future ALTER TABLE cannot silently break this."""
    out = {
        "seq": r[0],
        "ts": r[1],
        "user_id": r[2],
        "prev_hash": r[4],
        "audit_hash": r[5],
    }
    try:
        res = json.loads(r[3]) if r[3] else {}
    except Exception:
        res = {}
    if isinstance(res, dict):
        out["decision"] = res.get("decision", res.get("result", ""))
        out["score"] = res.get("score", "")
        rs = res.get("reasons", [])
        out["reasons"] = rs if isinstance(rs, list) else ([str(rs)] if rs else [])
    else:
        out["decision"] = ""
        out["score"] = ""
        out["reasons"] = []
    return out


SELECT = "SELECT id,ts,user_id,result_json,prev_hash,audit_hash FROM audit_log"


def handle(method, action, data, api_key, ctx):
    if not isinstance(data, dict):
        data = {}

    conn = _ctx_get(ctx, "conn")
    lock = _ctx_get(ctx, "lock") or _NoLock()
    if conn is None:
        return {"error": "no database handle on ctx",
                "ctx_type": type(ctx).__name__}, 500

    # ---------------------------------------------------------------- status
    if action == "status":
        with lock:
            cols = _cols(conn)
            try:
                n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                lo = conn.execute("SELECT MIN(id) FROM audit_log").fetchone()[0]
                hi = conn.execute("SELECT MAX(id) FROM audit_log").fetchone()[0]
            except Exception as e:
                return {"error": "audit_log unreadable: " + str(e)}, 500
        return {
            "module": "blocks",
            "version": VERSION,
            "rows": n,
            "lowest_seq": lo,
            "highest_seq": hi,
            "has_api_key_column": "api_key" in cols,
            "max_limit": MAX_LIMIT,
            "note": "reads only. no chain verification happens on this route.",
        }, 200

    # ------------------------------------------------------------------ list
    if action == "list":
        limit = _int(data, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10_000_000)
        order = _str(data, "order", "desc").lower()
        order = "ASC" if order == "asc" else "DESC"
        filt = _str(data, "api_key", "")

        with lock:
            cols = _cols(conn)
            try:
                if filt and "api_key" in cols:
                    rows = conn.execute(
                        SELECT + " WHERE api_key=? ORDER BY id " + order + " LIMIT ? OFFSET ?",
                        (filt, limit, offset)).fetchall()
                    total = conn.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE api_key=?", (filt,)).fetchone()[0]
                else:
                    rows = conn.execute(
                        SELECT + " ORDER BY id " + order + " LIMIT ? OFFSET ?",
                        (limit, offset)).fetchall()
                    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            except Exception as e:
                return {"error": "query failed: " + str(e)}, 500

        recs = [_row(r, cols) for r in rows]
        return {
            "blocks": recs,
            "count": len(recs),
            "total": total,
            "limit": limit,
            "offset": offset,
            "order": order.lower(),
            "has_more": (offset + len(recs)) < total,
            "next_offset": offset + len(recs),
        }, 200

    # ------------------------------------------------------------------- get
    if action == "get":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        with lock:
            cols = _cols(conn)
            r = conn.execute(SELECT + " WHERE id=?", (seq,)).fetchone()
            if not r:
                return {"error": "no block with that seq", "seq": seq}, 404
            below = conn.execute(
                "SELECT id,audit_hash FROM audit_log WHERE id<? ORDER BY id DESC LIMIT 1",
                (seq,)).fetchone()
        block = _row(r, cols)
        if below:
            block["links_to"] = below[0]
            block["link_holds"] = (str(block.get("prev_hash") or "") == str(below[1] or ""))
            block["expected_prev"] = below[1]
        else:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "oldest row in the table; nothing beneath it to link to"
        return {"block": block}, 200

    # ---------------------------------------------------------------- around
    if action == "around":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        span = _int(data, "span", 10, 1, MAX_SPAN)
        with lock:
            cols = _cols(conn)
            rows = conn.execute(
                SELECT + " WHERE id BETWEEN ? AND ? ORDER BY id DESC",
                (seq - span, seq + span)).fetchall()
        return {
            "centre": seq,
            "span": span,
            "blocks": [_row(r, cols) for r in rows],
        }, 200

    # ----------------------------------------------------------------- links
    if action == "links":
        limit = _int(data, "limit", DEFAULT_LIMIT, 2, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10_000_000)
        with lock:
            rows = conn.execute(
                "SELECT id,prev_hash,audit_hash FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()
        broken = []
        for i in range(len(rows) - 1):
            newer, older = rows[i], rows[i + 1]
            if str(newer[1] or "") != str(older[2] or ""):
                broken.append({
                    "between": newer[0],
                    "and": older[0],
                    "expected_prev": older[2],
                    "found_prev": newer[1],
                })
        checked = max(0, len(rows) - 1)
        return {
            "pairs_checked": checked,
            "broken": broken,
            "clean": len(broken) == 0,
            "range": {"newest_seq": rows[0][0] if rows else None,
                      "oldest_seq": rows[-1][0] if rows else None},
            "scope": ("this page only. a clean page is not a clean chain — "
                      "whole-chain verification is /api/verify-chain"),
        }, 200

    # ------------------------------------------------------------------ spec
    if action == "spec":
        return {
            "module": "blocks",
            "version": VERSION,
            "purpose": ("paged reads of audit_log for the operator block view, "
                        "without re-verifying the whole chain on every request"),
            "auth": "every route requires a key",
            "routes": {
                "GET status": "row count, lowest and highest seq",
                "GET list": "limit (max %d), offset, order=asc|desc, api_key" % MAX_LIMIT,
                "GET get": "seq — one block, plus whether its link to the row below holds",
                "GET around": "seq, span (max %d) — a window either side" % MAX_SPAN,
                "GET links": "limit, offset — link check across that page only",
            },
            "deliberately_not_here": [
                "whole-chain verification — that is /api/verify-chain",
                "writes of any kind",
                "any public route",
            ],
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["GET status", "GET list", "GET get",
                          "GET around", "GET links", "GET spec"]}, 404
