"""
modules/blocks.py  v1.0.1
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

v1.0.1 -- THE COMMENT WAS WRONG, SO THE CODE IS NOW RIGHT
---------------------------------------------------------
v1.0 said column names were read from the live schema so a future ALTER TABLE
could not silently break it. They were not. The SELECT was hardcoded and rows
were unpacked by position, r[0] through r[5], with the discovered column set
passed into the row shaper and never used. Renaming or reordering a column
would have 500'd every route.

Now it genuinely does what it said: PRAGMA table_info picks the real column
names once, each candidate is resolved against what actually exists, rows come
back as dicts keyed by name, and a missing column is reported in /status
instead of surfacing as a query error later. Same discipline complete.py uses.

ROUTES
------
  GET  /x/blocks/status                       module state, row count, schema
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

VERSION = "1.0.1"

# Nothing here is public. Audit rows are customer data.
PUBLIC = set()

MAX_LIMIT = 200          # a page, not a dump
DEFAULT_LIMIT = 50
MAX_SPAN = 100

# What this module needs, and the column names it will accept for each. The
# first name that exists in the live table wins. Nothing is assumed.
WANTED = {
    "seq": ["id", "rowid", "block_index", "seq"],
    "ts": ["ts", "timestamp", "created", "time"],
    "user_id": ["user_id", "subject", "customer_id"],
    "result": ["result_json", "result", "payload", "event_json"],
    "prev_hash": ["prev_hash", "previous_hash", "prev"],
    "audit_hash": ["audit_hash", "hash", "seal"],
}

_schema = {"resolved": None, "missing": None, "columns": None}


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
        return [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    except Exception:
        return []


def _resolve(conn):
    """Work out, once, which real column serves each role. Cached because the
    schema does not change between requests, re-derived if it ever comes back
    empty so a transient failure does not stick."""
    if _schema["resolved"]:
        return _schema["resolved"], _schema["missing"]
    cols = _cols(conn)
    lower = {c.lower(): c for c in cols}
    resolved, missing = {}, []
    for role, candidates in WANTED.items():
        hit = None
        for cand in candidates:
            if cand.lower() in lower:
                hit = lower[cand.lower()]
                break
        if hit:
            resolved[role] = hit
        else:
            missing.append(role)
    if resolved:
        _schema["resolved"] = resolved
        _schema["missing"] = missing
        _schema["columns"] = cols
    return resolved, missing


def _select(resolved, roles):
    """Build a SELECT from real column names, aliased to the role names, so
    rows come back keyed by role and never by position."""
    parts = ["%s AS %s" % (resolved[r], r) for r in roles if r in resolved]
    return "SELECT " + ",".join(parts) + " FROM audit_log"


def _dicts(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


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


def _shape(d):
    """One row, from a dict keyed by role. Missing roles come back as None
    rather than raising, so a partial schema degrades instead of failing."""
    out = {
        "seq": d.get("seq"),
        "ts": d.get("ts"),
        "user_id": d.get("user_id"),
        "prev_hash": d.get("prev_hash"),
        "audit_hash": d.get("audit_hash"),
    }
    raw = d.get("result")
    try:
        res = json.loads(raw) if raw else {}
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


ROLES = ["seq", "ts", "user_id", "result", "prev_hash", "audit_hash"]


def handle(method, action, data, api_key, ctx):
    if not isinstance(data, dict):
        data = {}

    conn = _ctx_get(ctx, "conn")
    lock = _ctx_get(ctx, "lock") or _NoLock()
    if conn is None:
        return {"error": "no database handle on ctx",
                "ctx_type": type(ctx).__name__}, 500

    with lock:
        resolved, missing = _resolve(conn)
    if not resolved or "seq" not in resolved or "audit_hash" not in resolved:
        return {"error": "audit_log schema not recognised",
                "columns_found": _schema.get("columns") or _cols(conn),
                "roles_missing": missing,
                "note": ("This module maps roles onto real column names. Add the "
                         "actual name to WANTED rather than assuming a shape.")}, 500

    SEL = _select(resolved, ROLES)
    idc = resolved["seq"]
    hashc = resolved["audit_hash"]
    prevc = resolved.get("prev_hash")

    # ---------------------------------------------------------------- status
    if action == "status":
        with lock:
            try:
                n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                lo = conn.execute("SELECT MIN(%s) FROM audit_log" % idc).fetchone()[0]
                hi = conn.execute("SELECT MAX(%s) FROM audit_log" % idc).fetchone()[0]
            except Exception as e:
                return {"error": "audit_log unreadable: " + str(e)}, 500
        return {
            "module": "blocks",
            "version": VERSION,
            "rows": n,
            "lowest_seq": lo,
            "highest_seq": hi,
            "schema_columns": _schema.get("columns"),
            "role_mapping": resolved,
            "roles_missing": missing,
            "has_api_key_column": "api_key" in [c.lower() for c in (_schema.get("columns") or [])],
            "max_limit": MAX_LIMIT,
            "note": "reads only. no chain verification happens on this route.",
        }, 200

    # ------------------------------------------------------------------ list
    if action == "list":
        limit = _int(data, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        order = _str(data, "order", "desc").lower()
        order = "ASC" if order == "asc" else "DESC"
        filt = _str(data, "api_key", "")
        has_key_col = "api_key" in [c.lower() for c in (_schema.get("columns") or [])]

        with lock:
            try:
                if filt and has_key_col:
                    cur = conn.execute(
                        SEL + " WHERE api_key=? ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (filt, limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE api_key=?", (filt,)).fetchone()[0]
                else:
                    cur = conn.execute(
                        SEL + " ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            except Exception as e:
                return {"error": "query failed: " + str(e)}, 500

        return {
            "blocks": recs,
            "count": len(recs),
            "total": total,
            "limit": limit,
            "offset": offset,
            "order": order.lower(),
            "has_more": (offset + len(recs)) < total,
            "next_offset": offset + len(recs),
            "filtered_by_key": bool(filt and has_key_col),
            "filter_ignored": bool(filt and not has_key_col) or None,
        }, 200

    # ------------------------------------------------------------------- get
    if action == "get":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        with lock:
            cur = conn.execute(SEL + " WHERE %s=?" % idc, (seq,))
            rows = _dicts(cur)
            if not rows:
                return {"error": "no block with that seq", "seq": seq}, 404
            below = conn.execute(
                "SELECT %s,%s FROM audit_log WHERE %s<? ORDER BY %s DESC LIMIT 1"
                % (idc, hashc, idc, idc), (seq,)).fetchone()
        block = _shape(rows[0])
        if below and prevc:
            block["links_to"] = below[0]
            block["link_holds"] = (str(block.get("prev_hash") or "") == str(below[1] or ""))
            block["expected_prev"] = below[1]
        elif not prevc:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "this table has no prev_hash column, so no link can be checked"
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
            cur = conn.execute(
                SEL + " WHERE %s BETWEEN ? AND ? ORDER BY %s DESC" % (idc, idc),
                (seq - span, seq + span))
            rows = _dicts(cur)
        return {
            "centre": seq,
            "span": span,
            "blocks": [_shape(d) for d in rows],
        }, 200

    # ----------------------------------------------------------------- links
    if action == "links":
        if not prevc:
            return {"error": "no prev_hash column in this table",
                    "note": "there is no link to check without one"}, 400
        limit = _int(data, "limit", DEFAULT_LIMIT, 2, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        with lock:
            rows = conn.execute(
                "SELECT %s,%s,%s FROM audit_log ORDER BY %s DESC LIMIT ? OFFSET ?"
                % (idc, prevc, hashc, idc), (limit, offset)).fetchall()
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
            "schema_handling": ("column names are resolved against PRAGMA "
                                "table_info at first use and rows are read by "
                                "name, so a renamed column is reported in "
                                "/status rather than breaking a query"),
            "role_mapping": resolved,
            "routes": {
                "GET status": "row count, lowest and highest seq, resolved column names",
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
