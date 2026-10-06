# Codebase — part 4 of 52

Contains:
- `modules/blocks.py`
- `modules/brand.py`
- `modules/capture.py`
- `modules/cinema.py`
- `modules/cinemafeed.py`
- `modules/codebase.py`


## `modules/blocks.py`

397 lines, 15562 bytes

```python
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

```


## `modules/brand.py`

217 lines, 8075 bytes

```python
"""
modules/brand.py  v1.0.0  -  one brand on every page: Monop Content

    Arm:  https://sebbi.pro/x/brand/status   (also armed by /x/arm/status)

The pages carry the founder's name and town in footers, taglines, buttons and
form placeholders. This presents them as Monop Content instead, without
editing a single page file: every HTML response is rewritten on its way out
of the server, whichever file or module produced it.

HOW
---
It wraps the request handler's handle_one_request, so it sits outside every
page patch whatever order modules were armed in. The response is held only
until its headers show what it is: anything that is not HTML (JSON, images,
video, downloads, event streams) is passed straight through untouched and
unbuffered. HTML is rewritten and its Content-Length corrected.

LEFT AS THEY ARE, ON PURPOSE
----------------------------
  /terms, /data-protection, /risk-policy, /human-oversight   the law and auditors
      expect the privacy notice and policies to name who is responsible
  /investor-prospectus                                investors expect the founder
  /admin, /console and other operator screens         your own tools

To switch it off without a deploy: https://sebbi.pro/x/brand/off
(back on with /x/brand/on). Both need your API key.
"""

import sys
import threading

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec")}

# Longest and most specific first, so a shorter rule never splits a longer one.
RULES = [
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; ",
     "&copy; 2026 Monop Content &middot; "),
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK", "&copy; 2026 Monop Content"),
    ("built by Monop Content in Blyth, United Kingdom", "built by Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content · Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland", "Monop Content"),
    ("Monop Content &middot; Blyth, UK", "Monop Content"),
    ("Monop Content · Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth", "Monop Content"),
    (" &middot; Blyth, Northumberland, UK", ""),
    (" &middot; Blyth, UK", ""),
    (" · Blyth, UK", ""),
    (" &middot; Justin Antony Dobson", ""),
    (" · Justin Antony Dobson", ""),
    ("Contact Justin at Monop Content", "Contact Monop Content"),
    ("Contact Justin", "Contact us"),
    ("talk to Justin", "talk to us"),
    ("Justin has been notified", "Our team has been notified"),
    ('placeholder="Justin Antony Dobson"', 'placeholder="Your full name"'),
    ('placeholder="Justin"', 'placeholder="First name"'),
    ("Building tamper-evident AI compliance from Blyth.", "Building tamper-evident AI compliance."),
]
RULES_B = [(a.encode("utf-8"), b.encode("utf-8")) for a, b in RULES]

SKIP_PATHS = ("/terms", "/data-protection", "/risk-policy", "/human-oversight", "/investor-prospectus",
              "/admin", "/console", "/peers", "/pack", "/lineage-desk")

_state = {"installed": False, "on": True, "rewritten": 0, "replacements": 0, "last_error": None}
_lock = threading.Lock()


def rewrite(body):
    n = 0
    for old, new in RULES_B:
        if old in body:
            n += body.count(old)
            body = body.replace(old, new)
    return body, n


class _Out(object):
    """Stands in for wfile for one request. Passes non-HTML straight through."""

    def __init__(self, real):
        self.real = real
        self.buf = bytearray()
        self.mode = None  # None = reading headers, "pass", "html"

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            if b"content-type: text/html" in head and b"content-encoding" not in head:
                self.mode = "html"
            else:
                self._go_pass()
        elif len(self.buf) > 8 * 1024 * 1024:
            self._go_pass()  # an enormous page is sent as it is rather than held
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if self.mode != "html" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        new_body, n = rewrite(body)
        if n:
            lines = head.split(b"\r\n")
            lines = [l for l in lines if not l.lower().startswith(b"content-length:")]
            lines.append(b"Content-Length: " + str(len(new_body)).encode())
            head = b"\r\n".join(lines)
            _state["rewritten"] += 1
            _state["replacements"] += n
        self.real.write(head + b"\r\n\r\n" + new_body)
        try:
            self.real.flush()
        except Exception:
            pass


def _handler_class():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return getattr(m, "Handler", None)


def _install():
    with _lock:
        if _state["installed"]:
            return True
        H = _handler_class()
        if H is None:
            return False
        if getattr(H, "_brand_patched", False):
            _state["installed"] = True
            return True
        original = H.handle_one_request

        def handle_one_request(self):
            if not _state["on"]:
                return original(self)
            real = self.wfile
            out = _Out(real)
            self.wfile = out
            try:
                original(self)
            finally:
                self.wfile = real
                try:
                    path = (getattr(self, "path", "") or "").split("?")[0]
                    if path.startswith(SKIP_PATHS) and out.mode == "html":
                        out.mode = "pass_html"
                        real.write(bytes(out.buf))
                        out.buf = bytearray()
                    out.finish()
                except Exception as e:
                    _state["last_error"] = str(e)[:200]
                    try:
                        if out.buf:
                            real.write(bytes(out.buf))
                    except Exception:
                        pass

        H.handle_one_request = handle_one_request
        H._brand_patched = True
        _state["installed"] = True
        return True


def handle(method, action, data, api_key, ctx):
    armed = _install()
    if action in ("off", "on"):
        if not api_key:
            return {"error": "api_key_required"}, 401
        _state["on"] = action == "on"
    if action == "spec":
        return {"module": "brand", "version": VERSION,
                "what": "Every HTML page presented as Monop Content, rewritten as it is served. No page file is edited.",
                "rules": [{"from": a, "to": b} for a, b in RULES],
                "left_as_they_are": list(SKIP_PATHS)}, 200
    return {"module": "brand", "version": VERSION, "armed": armed, "on": _state["on"],
            "pages_rewritten": _state["rewritten"], "replacements": _state["replacements"],
            "left_as_they_are": list(SKIP_PATHS), "last_error": _state["last_error"]}, 200

```


## `modules/capture.py`

385 lines, 17851 bytes

```python
"""
One-button decision capture - /x/capture/<action>

WHAT IT IS
----------
A drop-in button for an operator's own review screen. A human reviews an AI
output, clicks once, and the decision is sealed into the chain with who
reviewed it, on what device, against which inputs, and how long they took.

WHY IT IS TWO CALLS AND NOT ONE
-------------------------------
The obvious version is a single POST carrying a dwell time measured in the
browser. That number is the whole point - it is what makes rubber stamping
visible - and a number the reviewed party computes for itself is not
evidence. Anyone can set it to whatever looks diligent.

So the widget opens a case first. The server records the open time. When the
reviewer commits, the server computes the dwell itself from two timestamps it
owns. The browser never supplies the figure it is being judged on.

Same reason the verdict is withheld between the two calls: the machine's
answer is sealed at open and only returned at seal, so the chain shows the
human committed before they saw it. Ordering is the one thing that separates
judgement from agreement.

KEYS IN BROWSERS
----------------
An API key pasted into page JavaScript is public. Anyone reading the source
can post as that operator, forever.

So capture accepts a CAPTURE TOKEN: minted server-side by the operator from
their real key, bound to one origin, short-lived, and able to do exactly two
things - open a case and seal it. It cannot read records, cannot see other
cases, cannot touch any other module. Same idea as a publishable key.

The real API key still works for server-to-server calls. It should never
appear in a page.

DEVICES ARE THE BILLING UNIT
----------------------------
Every capture carries a device_id, and distinct devices per calendar month is
what billing is counted on. The registry here is that count: first seen, last
seen, events, per month. An operator can query their own figure at any time
and reconcile it against an invoice, rather than being told a number.

Device identifiers are hashed on arrival. The chain and the registry hold a
fingerprint, never the raw identifier.

    POST /x/capture/token     mint a browser-safe capture token (real key only)
    POST /x/capture/open      start a case, server records the clock
    POST /x/capture/seal      commit a verdict, server computes the dwell
    GET  /x/capture/devices   this month's billable device count
    GET  /x/capture/case?id=  the sealed record of one capture
    GET  /x/capture/summary   dwell and divergence across recent captures
"""

import hashlib, hmac, json, os, re, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate", "approve", "reject"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN_TTL = 3600 * 12
MAX_OPEN_AGE = 3600 * 6

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_cases(case_id TEXT PRIMARY KEY,api_key TEXT,operator_fp TEXT,device_fp TEXT,input_hash TEXT,output_hash TEXT,machine_verdict TEXT,opened REAL,sealed REAL,human_verdict TEXT,dwell REAL,agreed INTEGER,note TEXT)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_devices(api_key TEXT,device_fp TEXT,month TEXT,first_seen REAL,last_seen REAL,events INTEGER DEFAULT 0,PRIMARY KEY(api_key,device_fp,month))")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_key ON capture_cases(api_key,opened)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_dev ON capture_devices(api_key,month)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("CAPTURE_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def _fp(v):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(v).strip().lower().encode(), hashlib.sha256).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _month(ts=None):
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m")


# ------------------------------------------------------------ capture token

def _mint(ctx, api_key, data):
    """Real key only. Returns a token safe to put in a page."""
    s = _secret()
    if not s:
        return {"error": "capture_secret_not_set",
                "message": "Set CAPTURE_SECRET in the environment first."}, 503
    origin = str(data.get("origin", "")).strip().lower()[:120]
    if not origin:
        return {"error": "origin_required",
                "message": "Bind the token to the site that will use it, e.g. https://app.yourcompany.com"}, 400
    try:
        ttl = min(int(data.get("ttl_seconds", TOKEN_TTL)), TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = TOKEN_TTL
    exp = int(time.time()) + max(60, ttl)
    body = api_key + "|" + origin + "|" + str(exp)
    sig = hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32]
    token = "cap_" + str(exp) + "_" + hashlib.sha256(origin.encode()).hexdigest()[:8] + "_" + sig
    return {"capture_token": token, "origin": origin,
            "expires": _iso(exp), "expires_in_seconds": exp - int(time.time()),
            "scope": ["capture:open", "capture:seal"],
            "note": "Safe to place in a page. It cannot read records, cannot see other cases, and cannot reach any other module. Mint a fresh one from your server as needed - never put your real API key in a browser."}, 200


def _verify_token(ctx, token, origin):
    """Returns the owning api_key, or None."""
    s = _secret()
    if not s or not token or not token.startswith("cap_"):
        return None
    parts = token.split("_")
    if len(parts) != 4:
        return None
    try:
        exp = int(parts[1])
    except ValueError:
        return None
    if exp < time.time():
        return None
    ohash, sig = parts[2], parts[3]
    if origin:
        o = str(origin).strip().lower()[:120]
        if hashlib.sha256(o.encode()).hexdigest()[:8] != ohash:
            return None
    else:
        o = None
    with ctx["lock"]:
        keys = ctx["conn"].execute("SELECT key FROM api_keys WHERE active=1").fetchall()
    for (k,) in keys:
        if o is None:
            continue
        body = k + "|" + o + "|" + str(exp)
        if hmac.compare_digest(hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32], sig):
            return k
    return None


def _resolve(ctx, api_key, data):
    """A real key wins; otherwise try a capture token bound to an origin."""
    if api_key:
        return api_key, "api_key"
    tok = str(data.get("capture_token", "")).strip()
    origin = str(data.get("origin", "")).strip()
    owner = _verify_token(ctx, tok, origin)
    if owner:
        return owner, "capture_token"
    return None, None


# ------------------------------------------------------------------ devices

def _touch_device(ctx, api_key, device_fp, ts):
    m = _month(ts)
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT events FROM capture_devices WHERE api_key=? AND device_fp=? AND month=?", (api_key, device_fp, m)).fetchone()
        if row:
            ctx["conn"].execute("UPDATE capture_devices SET last_seen=?,events=events+1 WHERE api_key=? AND device_fp=? AND month=?", (ts, api_key, device_fp, m))
            new = False
        else:
            ctx["conn"].execute("INSERT INTO capture_devices(api_key,device_fp,month,first_seen,last_seen,events) VALUES(?,?,?,?,?,1)", (api_key, device_fp, m, ts, ts))
            new = True
        ctx["conn"].commit()
    return new


def _devices(ctx, api_key, data):
    m = str(data.get("month", "")).strip() or _month()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT COUNT(*),SUM(events) FROM capture_devices WHERE api_key=? AND month=?", (api_key, m)).fetchone()
        months = ctx["conn"].execute("SELECT month,COUNT(*) FROM capture_devices WHERE api_key=? GROUP BY month ORDER BY month DESC LIMIT 12", (api_key,)).fetchall()
    n = rows[0] or 0
    return {"month": m, "billable_devices": n, "captures": rows[1] or 0,
            "rate_per_device": 0.50, "currency": "GBP",
            "estimated_charge": round(n * 0.50, 2),
            "history": [{"month": a, "devices": b} for a, b in months],
            "note": "A device counts once per calendar month however many captures it makes. Distinct devices is the billing unit - this is the same figure the invoice uses, so you can reconcile it yourself rather than being told a number."}, 200


# -------------------------------------------------------------------- cases

def _open(ctx, api_key, data):
    if not _secret():
        return {"error": "capture_secret_not_set"}, 503
    operator = str(data.get("operator_id", "")).strip()
    if not operator:
        return {"error": "operator_id_required",
                "message": "A capture with no named reviewer is not oversight."}, 400
    device = str(data.get("device_id", "")).strip()
    if not device:
        return {"error": "device_id_required",
                "message": "Devices are the billing unit and the record needs to say which one acted."}, 400

    ih = str(data.get("input_hash", "")).strip().lower()
    oh = str(data.get("output_hash", "")).strip().lower()
    for name, v in (("input_hash", ih), ("output_hash", oh)):
        if v and not HEX64.match(v):
            return {"error": "invalid_" + name,
                    "message": "Hash the content locally and send 64 hex characters. Never send the content itself."}, 400

    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    ts = time.time()
    ofp, dfp = _fp(operator), _fp(device)
    cid = "CAP-" + secrets.token_hex(5).upper()
    new_device = _touch_device(ctx, api_key, dfp, ts)

    detail = ("operator=" + (ofp or "")[:32] + ";device=" + (dfp or "")[:32] +
              ";input=" + (ih or "none") + ";output=" + (oh or "none") +
              ";machine_verdict_sealed=" + (mv or "none"))
    ev = {"user_id": "cap:" + cid, "action": "capture_opened", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "opened",
           "capture_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "no personal data and no content in this block - fingerprints and hashes only"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO capture_cases(case_id,api_key,operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed,note) VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                            (cid, api_key, ofp, dfp, ih or None, oh or None, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until seal",
            "new_device_this_month": new_device,
            "next": "POST the reviewer's verdict to /x/capture/seal with this case_id",
            "note": "The clock started here, on the server. The dwell time is not something the browser gets to report."}, 200


def _seal(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,machine_verdict,opened,sealed FROM capture_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_sealed",
                "message": "A capture commits once."}, 400

    hv = str(data.get("verdict", "")).strip().lower()
    if hv not in VERDICTS:
        return {"error": "invalid_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()

    ts = time.time()
    dwell = round(ts - row[3], 3)
    if dwell > MAX_OPEN_AGE:
        return {"error": "case_expired",
                "opened": _iso(row[3]),
                "message": "This case was opened more than six hours ago. Open a fresh one rather than sealing a stale clock."}, 400
    agreed = None if not row[2] else (1 if hv == row[2] else 0)

    detail = ("verdict=" + hv + ";dwell_seconds=" + str(dwell) +
              ";server_measured=true;reasoning=" + reasoning[:600])
    ev = {"user_id": "cap:" + cid, "action": "capture_sealed", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "sealed",
           "capture_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE capture_cases SET sealed=?,human_verdict=?,dwell=?,agreed=? WHERE case_id=? AND api_key=?",
                            (ts, hv, dwell, agreed, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "verdict": hv, "dwell_seconds": dwell,
           "machine_verdict": row[2], "sealed": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "measured_by": "server",
           "note": "Your verdict was sealed before this response revealed ours. The chain fixes that order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "sealed " + str(dwell) + "s after the case opened - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed FROM capture_cases WHERE case_id=? AND api_key=?", (cid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("cap:" + cid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("capture_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    return {"case_id": cid.upper(),
            "operator_fingerprint": (row[0] or "")[:16] + "...",
            "device_fingerprint": (row[1] or "")[:16] + "...",
            "input_hash": row[2], "output_hash": row[3],
            "machine_verdict": row[4], "opened": _iso(row[5]),
            "sealed": _iso(row[6]), "human_verdict": row[7],
            "dwell_seconds": row[8],
            "agreed": (None if row[9] is None else bool(row[9])),
            "events": events,
            "ordering_proof": "The opened block precedes the sealed block in the chain, and both timestamps are the server's."}, 200


def _summary(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM capture_cases WHERE api_key=? AND sealed IS NOT NULL", (api_key,)).fetchall()
        openc = ctx["conn"].execute("SELECT COUNT(*) FROM capture_cases WHERE api_key=? AND sealed IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"captures": 0, "open_cases": openc,
                "note": "No sealed captures yet."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    under2 = len([d for d in dwells if d < 2])
    out = {"captures": len(rows), "open_cases": openc,
           "median_dwell_seconds": (dwells[n // 2] if n else None),
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " captures"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "token":
            if not api_key:
                return {"error": "api_key_required",
                        "message": "Mint capture tokens from your server using your real key."}, 401
            return _mint(ctx, api_key, data)
        owner, how = _resolve(ctx, api_key, data)
        if not owner:
            return {"error": "invalid_credentials",
                    "message": "Send a real API key server-side, or a valid capture_token with the origin it was bound to."}, 401
        if action == "open":
            return _open(ctx, owner, data)
        if action == "seal":
            return _seal(ctx, owner, data)
    else:
        if not api_key:
            return {"error": "api_key_required",
                    "message": "Reading capture records needs the real key, not a capture token."}, 401
        if action == "devices":
            return _devices(ctx, api_key, data)
        if action == "summary":
            return _summary(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/cinema.py`

703 lines, 39776 bytes

```python
"""
modules/cinema.py  v3.2.0
The sebbi.pro Cinema at /cinema, in two wings.

GOVERNANCE spins the videos in modules/cinemafeed.py on the ring and plays
them in the screening room, as before.

THE 10p WING is the creators' channel. Every video made on Monop Studio
(/create, modules/studio.py) plays here:

  * one tap from TikTok, Instagram, Facebook or YouTube (the creator's link,
    https://sebbi.pro/v/<id>) opens that video on the Wing's TV;
  * the free teaser plays, then 10p unlocks the rest - one tap on Google Pay
    or Apple Pay when there's no credit on the phone yet;
  * a searchable library (video name or creator name), Trending / New /
    Most watched, a spinning ring of screens, likes, comments from people who
    have actually paid to watch, and a Top Creators board;
  * every paid view is sealed into the chain, so the board and each creator's
    earnings link to the block that proves them, with a live ticker;
  * a channel page per creator at https://sebbi.pro/cinema/@<name>.

Page routes (runtime do_GET / do_POST patch):
  GET  /cinema   /cinema/v/<id>   /cinema/@<name>
  GET  /cinema/api/list?q=&sort=trending|new|top&creator=&offset=
  GET  /cinema/api/video?id=&viewer=
  GET  /cinema/api/comments?id=
  GET  /cinema/api/leaders      GET /cinema/api/ticker
  POST /cinema/api/like  {id, viewer}
  POST /cinema/api/comment {id, viewer, name, text}
  POST /cinema/api/flag  {comment}
  GET  /cinema/api/admin?key=&do=hide&comment=      (CREDITS_ADMIN_KEY)
  GET  /x/cinema/status  arms the routes after a deploy
"""

import base64
import gzip
import hashlib
import hmac
import html
import importlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from collections import defaultdict, deque

VERSION = "3.2.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
SITE = (os.environ.get("HOST") or "https://sebbi.pro").strip().rstrip("/")

VIEWER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ID_RE = re.compile(r"^[a-z0-9]{8}$")
CLEAN = re.compile(r"[<>\\\x00-\x08\x0b-\x1f]")
PAGE = 24

_ctx = {}
_st = None
_ready = False
_patched = False
_wins = defaultdict(deque)
_wins_lock = threading.Lock()

_CINEMA_GZ = (
    "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"
    "q+xRT0o5DItsLApvrArHjm4AMe1PACD6iKexQP/j95EbvBM7xRwdcsu/rgWFfKo1Kiteb6RLC+ZixCKA83k5Cxc38SaDml7LEsqE"
    "NAWvDaoakLBj8fSBZmdyyMLgkgQki20NLjkO0fnFGCjLJci0Bk3NsI2unoereka5OnHT/j79yVkJqJhPIQkpYOGCCtYVZdFdoBLU"
    "MjTS1HFlm2fkn83Bv8F9Yz3dr92Ldnxs2cUHlr0AEa0BFwqdcWDWLLPCooK7qJhTkv1MhlEYeEQgvI39/ewdu/bTz7P33HPY8rKu"
    "OwxGleUnMLj93ewBjspeLPiJyJiCGABqZavUn7NF5OGeWSH++oRTYn8/p9H+PowBPi3ej3oJHQf9+puLNw6W7b1L2CgMvOT29qx7"
    "ZlkZC2y2TUy1k4Up+YwcN5V0J48d02Pony/dWb2q//7+J1sYjq9LjuztmugunG/sTrMJwKDdz8oeLUeW8ytw/Q2cOJ0K/WbvY8zW"
    "FrqgV8q8rARWpVAZMqkEsRDfhNiDK9Ivqf5/IL9+h0d/iBE0h7MCVfdzSDNjzlGarRpWpGhV1UyRkSITZeOJJW7quYWjfzEt2NN5"
    "hSugPeNvQL17ONTkpHM72uPZ6GFf99F6wyo3jHnG+z//gwkvdRfOCK/wYeb1icUBmxBWLMWDlwOJgjl0N/xE1uP7gcFL2cwD+ntg"
    "aiX6DvTHq4xMCXXa11lVul5IkCIdCZycPB/M0luYRxVa9NXIOlP8owZ1HLPSYqnpwgrE62gsRj88my29Mt7TtNe+10UHxubuTpc7"
    "O5sKb2dYdM5LLtj6bh+MB3jQDVNZ4diAt+4MN6bfRRD6MIg4THADhmi6K2jP3QvcSCr0Qw9DlFDiPSWFCkrjdYlLNKjQP88YhKN4"
    "Ixf3LgGYOs02X9xLgKkw9e1tU+2UQ+05c5YkYPVvb80n4WLmBbVU0NPAnVMjCFeOcRnf8KJyBGHoesgNZR4q4V5BzvMQK20DcflW"
    "5YAbXf/gKmANnJeTNNc1NpXc9oE76cPt7ds1rREPUPJkedf8yz+3nGbTJH7B66M2tmhzrLY5VtocNzc/iOib1zLrbh9AcoFFlMbU"
    "XTJBXoQuIymsKYyMBZ1dEPgj4iJpIfrEal8s+jFWfjo1lHrgMM7rgTFoe1MI77CqFEYZj8WpIll16ZgSWqw/tpSEND1x5m6U0yay"
    "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"
    "44f8hwgPp+l8Ntj7fydKEo6upAAA"
)


def _page(b):
    return gzip.decompress(base64.b64decode("".join(b.split()))).decode("utf-8")


CINEMA_HTML = _page(_CINEMA_GZ)


def _studio():
    global _st
    if _st is None:
        _st = sys.modules.get("modules.studio") or importlib.import_module("modules.studio")
    if "conn" in _ctx and not _st._ready:
        _st._ctx.update(_ctx)
        _st._setup()
    return _st


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    _studio()
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS cinema_like(video TEXT,viewer TEXT,at REAL,PRIMARY KEY(video,viewer))")
        c.execute("CREATE TABLE IF NOT EXISTS cinema_comment(id INTEGER PRIMARY KEY AUTOINCREMENT,video TEXT,"
                  "viewer TEXT,name TEXT,text TEXT,at REAL,hidden INTEGER DEFAULT 0,flags INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS cinema_comment_video ON cinema_comment(video,id)")
        c.execute("CREATE INDEX IF NOT EXISTS credit_unlock_video ON credit_unlock(video,at)")
        c.commit()
    _ready = True


def _limit(who, group, per_min, per_hour):
    t = time.time()
    k = group + "|" + who
    with _wins_lock:
        w = _wins[k]
        while w and w[0] < t - 3600:
            w.popleft()
        if len(w) >= per_hour or sum(1 for x in w if x > t - 60) >= per_min:
            return False
        w.append(t)
        if len(_wins) > 20000:
            for key in [x for x, v in _wins.items() if not v or v[-1] < t - 3600][:5000]:
                del _wins[key]
    return True


def _ip(h):
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        return (xff.split(",")[0].strip() if xff else str(h.client_address[0]))[:64]
    except Exception:
        return "unknown"


def _ago(t):
    s = max(0, int(time.time() - (t or 0)))
    if s < 60:
        return "just now"
    if s < 3600:
        return "%dm ago" % (s // 60)
    if s < 86400:
        return "%dh ago" % (s // 3600)
    return "%dd ago" % (s // 86400)


def _rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _cards(rows):
    st = _studio()
    cols = st.COLS.split(",")
    return [st._public(dict(zip(cols, r))) for r in rows]


# ------------------------------------------------------------------ reads

def a_list(q, b, h):
    st = _studio()
    sort = str(q.get("sort") or "trending")
    term = CLEAN.sub("", str(q.get("q") or "")).strip()[:60]
    creator = CLEAN.sub("", str(q.get("creator") or "")).strip()[:40]
    try:
        off = max(0, min(5000, int(q.get("offset") or 0)))
    except ValueError:
        off = 0
    where, args = ["v.status='live'"], []
    if term:
        like = "%" + term.replace("%", "").replace("_", "") + "%"
        where.append("(v.title LIKE ? OR v.creator LIKE ? OR v.tags LIKE ?)")
        args += [like, like, like]
    if creator:
        where.append("(v.creator=? COLLATE NOCASE OR replace(v.creator,' ','_')=? COLLATE NOCASE)")
        args += [creator, creator]
    cols = ",".join("v." + c for c in st.COLS.split(","))
    sql = "SELECT " + cols + " FROM studio_video v WHERE " + " AND ".join(where)
    extra = []
    if sort == "new":
        sql += " ORDER BY v.live_at DESC"
    elif sort == "top":
        sql += " ORDER BY v.unlocks DESC, v.likes DESC, v.live_at DESC"
    else:
        sort = "trending"
        sql += (" ORDER BY (SELECT COUNT(*) FROM credit_unlock u WHERE u.video='st:'||v.id AND u.at>?)*3"
                " + v.likes + v.plays/20.0 DESC, v.live_at DESC")
        extra = [time.time() - 7 * 86400]
    rows = _rows(sql + " LIMIT ? OFFSET ?", tuple(args + extra + [PAGE + 1, off]))
    return {"sort": sort, "q": term, "creator": creator, "videos": _cards(rows[:PAGE]),
            "more": len(rows) > PAGE, "next": off + PAGE}, 200


def a_video(q, b, h):
    st = _studio()
    v = st._video(str(q.get("id") or ""))
    if not v or v["status"] != "live":
        return {"error": "not_found", "message": "That video isn't here any more."}, 404
    out = {"video": st._public(v)}
    viewer = str(q.get("viewer") or "")
    if VIEWER_RE.match(viewer):
        out["liked"] = bool(_rows("SELECT 1 FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer)))
        out["can_comment"] = st._unlocked(v["id"], viewer)[0]
    return out, 200


def a_comments(q, b, h):
    vid = str(q.get("id") or "")
    if not ID_RE.match(vid):
        return {"comments": []}, 200
    rows = _rows("SELECT id,name,text,at FROM cinema_comment WHERE video=? AND hidden=0 ORDER BY id DESC LIMIT 100",
                 (vid,))
    return {"comments": [{"id": r[0], "name": r[1], "text": r[2], "ago": _ago(r[3])} for r in rows]}, 200


def a_leaders(q, b, h):
    rows = _rows("SELECT creator,SUM(unlocks),SUM(earned),SUM(status='live'),SUM(likes) FROM studio_video "
                 "WHERE status IN ('live','removed') GROUP BY creator COLLATE NOCASE "
                 "ORDER BY SUM(earned) DESC, SUM(unlocks) DESC LIMIT 25")
    out = []
    for r in rows:
        if not r[1] and not r[4]:
            continue
        proof = _rows("SELECT block_index FROM credit_unlock WHERE creator=? AND video LIKE 'st:%' "
                      "AND block_index IS NOT NULL ORDER BY id DESC LIMIT 1", (r[0],))
        blk = proof[0][0] if proof else None
        out.append({"creator": r[0], "paid_views": r[1] or 0, "earned_pence": r[2] or 0,
                    "videos": r[3], "likes": r[4] or 0,
                    "channel": SITE + "/cinema/@" + _studio()._slug(r[0]),
                    "proof_block": blk,
                    "proof": (SITE + "/x/walk/block?index=%s" % blk) if blk else None})
    tot = _rows("SELECT COALESCE(SUM(unlocks),0),COALESCE(SUM(earned),0),COUNT(DISTINCT creator) "
                "FROM studio_video WHERE status IN ('live','removed')")[0]
    return {"leaders": out, "total_paid_views": tot[0], "total_earned_pence": tot[1], "creators": tot[2]}, 200


def a_ticker(q, b, h):
    rows = _rows("SELECT u.creator,u.at,u.block_index,v.title,v.id FROM credit_unlock u "
                 "LEFT JOIN studio_video v ON v.id=substr(u.video,4) WHERE u.video LIKE 'st:%' "
                 "ORDER BY u.id DESC LIMIT 20")
    return {"ticker": [{"creator": r[0], "ago": _ago(r[1]), "block": r[2], "title": r[3] or "",
                        "id": r[4], "proof": (SITE + "/x/walk/block?index=%s" % r[2]) if r[2] else None}
                       for r in rows]}, 200


def a_creator(q, b, h):
    name = CLEAN.sub("", str(q.get("name") or "")).strip()[:40]
    if not name:
        return {"error": "not_found"}, 404
    r = _rows("SELECT creator,COALESCE(SUM(unlocks),0),COALESCE(SUM(earned),0),COALESCE(SUM(status='live'),0),"
              "COALESCE(SUM(likes),0) "
              "FROM studio_video WHERE (creator=? COLLATE NOCASE OR replace(creator,' ','_')=? COLLATE NOCASE) "
              "AND status IN ('live','removed')", (name, name))[0]
    if not r[0]:
        return {"error": "not_found", "message": "No channel called that yet."}, 404
    return {"creator": r[0], "paid_views": r[1], "earned_pence": r[2], "videos": r[3], "likes": r[4],
            "channel": SITE + "/cinema/@" + _studio()._slug(r[0])}, 200


# ------------------------------------------------------------------ writes

def a_like(q, b, h):
    st = _studio()
    v = st._video(str(b.get("id") or ""))
    viewer = str(b.get("viewer") or "")
    if not v or v["status"] != "live" or not VIEWER_RE.match(viewer):
        return {"error": "not_found"}, 404
    if not _limit(viewer, "like", 30, 400) or not _limit(_ip(h), "likeip", 60, 1500):
        return {"error": "slow_down"}, 429
    with _ctx["lock"]:
        c = _ctx["conn"]
        if c.execute("SELECT 1 FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer)).fetchone():
            c.execute("DELETE FROM cinema_like WHERE video=? AND viewer=?", (v["id"], viewer))
            c.execute("UPDATE studio_video SET likes=MAX(0,likes-1) WHERE id=?", (v["id"],))
            liked = False
        else:
            c.execute("INSERT INTO cinema_like(video,viewer,at) VALUES(?,?,?)", (v["id"], viewer, time.time()))
            c.execute("UPDATE studio_video SET likes=likes+1 WHERE id=?", (v["id"],))
            liked = True
        n = c.execute("SELECT likes FROM studio_video WHERE id=?", (v["id"],)).fetchone()[0]
        c.commit()
    return {"liked": liked, "likes": n}, 200


def a_comment(q, b, h):
    st = _studio()
    v = st._video(str(b.get("id") or ""))
    viewer = str(b.get("viewer") or "")
    if not v or v["status"] != "live" or not VIEWER_RE.match(viewer):
        return {"error": "not_found"}, 404
    if not st._unlocked(v["id"], viewer)[0]:
        return {"error": "watch_first", "message": "Unlock the video to join the chat."}, 403
    name = CLEAN.sub("", str(b.get("name") or "")).strip()[:24]
    text = CLEAN.sub("", str(b.get("text") or "")).strip()[:400]
    if len(name) < 2:
        return {"error": "name", "message": "Add a name (2 letters or more)."}, 400
    if len(text) < 1:
        return {"error": "empty", "message": "Write something first."}, 400
    if not _limit(viewer, "comment", 2, 30) or not _limit(_ip(h), "commentip", 6, 120):
        return {"error": "slow_down", "message": "Easy - wait a few seconds between comments."}, 429
    with _ctx["lock"]:
        c = _ctx["conn"]
        cur = c.execute("INSERT INTO cinema_comment(video,viewer,name,text,at) VALUES(?,?,?,?,?)",
                        (v["id"], viewer, name, text, time.time()))
        c.execute("UPDATE studio_video SET comments=comments+1 WHERE id=?", (v["id"],))
        c.commit()
        cid = cur.lastrowid
    return {"posted": True, "comment": {"id": cid, "name": name, "text": text, "ago": "just now"}}, 200


def a_flag(q, b, h):
    try:
        cid = int(b.get("comment") or 0)
    except (TypeError, ValueError):
        return {"error": "bad"}, 400
    if not _limit(_ip(h), "flag", 5, 40):
        return {"received": True}, 200
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("UPDATE cinema_comment SET flags=flags+1,hidden=CASE WHEN flags+1>=3 THEN 1 ELSE hidden END "
                  "WHERE id=?", (cid,))
        c.commit()
    return {"received": True}, 200


def a_admin(q, b, h):
    key = os.environ.get("CREDITS_ADMIN_KEY", "").strip()
    if not key or not hmac.compare_digest(key, str(q.get("key") or "")):
        return {"error": "not_allowed"}, 403
    do = str(q.get("do") or "list")
    if do == "hide":
        try:
            cid = int(q.get("comment") or 0)
        except ValueError:
            return {"error": "bad"}, 400
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE cinema_comment SET hidden=1 WHERE id=?", (cid,))
            _ctx["conn"].commit()
        return {"hidden": cid}, 200
    rows = _rows("SELECT id,video,name,text,flags,hidden,at FROM cinema_comment ORDER BY flags DESC, id DESC LIMIT 100")
    return {"comments": [{"id": r[0], "video": SITE + "/v/" + r[1], "name": r[2], "text": r[3], "flags": r[4],
                          "hidden": bool(r[5]), "ago": _ago(r[6]),
                          "hide": SITE + "/cinema/api/admin?key=KEY&do=hide&comment=%d" % r[0]} for r in rows]}, 200


GETS = {"list": a_list, "video": a_video, "comments": a_comments, "leaders": a_leaders,
        "ticker": a_ticker, "creator": a_creator, "admin": a_admin}
POSTS = {"like": a_like, "comment": a_comment, "flag": a_flag}


# ------------------------------------------------------------------ pages

def _esc(s):
    return html.escape(str(s or ""), quote=True)


def _render(path):
    st = _studio()
    boot = {"route": "wing", "site": SITE}
    title = "sebbi.pro Cinema — the 10p Wing"
    desc = "Watch creators' videos free, then 10p for the rest. No followers needed to earn. Every penny proven."
    image, video, url = "", None, SITE + "/cinema"
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[1] == "v":
        v = st._video(parts[2].lower())
        if v and v["status"] == "live":
            pub = st._public(v)
            boot.update({"route": "video", "video": pub})
            title = "%s — by %s · 10p Wing" % (v["title"], v["creator"])
            desc = "Watch the start free, then %s for the rest. 7p of every 10p goes to %s." % (
                pub["price_label"], v["creator"])
            image, url = SITE + pub["poster"], SITE + "/cinema/v/" + v["id"]
            if (v["teaser_mime"] or "").endswith("mp4"):
                video = SITE + pub["teaser"]
    elif len(parts) >= 2 and parts[1].startswith("@"):
        name = CLEAN.sub("", urllib.parse.unquote(parts[1][1:])).strip()[:40]
        boot.update({"route": "channel", "creator": name})
        title = "%s on the 10p Wing" % name
        desc = "Every video by %s. Watch free, then 10p for the rest." % name
        url = SITE + "/cinema/@" + _studio()._slug(name)
    elif len(parts) >= 2 and parts[1] == "governance":
        boot["route"] = "gov"
    og = ['<title>%s</title>' % _esc(title),
          '<meta name="description" content="%s">' % _esc(desc),
          '<meta property="og:site_name" content="sebbi.pro">',
          '<meta property="og:title" content="%s">' % _esc(title),
          '<meta property="og:description" content="%s">' % _esc(desc),
          '<meta property="og:url" content="%s">' % _esc(url),
          '<meta property="og:type" content="%s">' % ("video.other" if video else "website"),
          '<meta name="twitter:card" content="summary_large_image">',
          '<meta name="twitter:title" content="%s">' % _esc(title),
          '<meta name="twitter:description" content="%s">' % _esc(desc)]
    if boot["route"] == "video":
        og += ['<meta property="og:image" content="%s">' % _esc(image),
               '<meta name="twitter:image" content="%s">' % _esc(image)]
    if video:
        og += ['<meta property="og:video" content="%s">' % _esc(video),
               '<meta property="og:video:secure_url" content="%s">' % _esc(video),
               '<meta property="og:video:type" content="video/mp4">']
    data = json.dumps(boot).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return CINEMA_HTML.replace("<!--OG-->", "\n".join(og)).replace("__BOOT__", data).encode("utf-8")


# ------------------------------------------------------------------ transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _serve(h, method):
    u = urllib.parse.urlparse(h.path)
    path = u.path.rstrip("/") or "/"
    if path != "/cinema" and not path.startswith("/cinema/"):
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "Open /x/cinema/status once."}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    if path.startswith("/cinema/api/"):
        name = path[12:].strip("/")
        table = GETS if method == "GET" else POSTS
        fn = table.get(name)
        if not fn:
            _send(h, {"error": "not_found"}, 404)
            return True
        body = {}
        if method == "POST":
            try:
                n = min(int(h.headers.get("Content-Length") or 0), 20000)
                raw = h.rfile.read(n) if n else b""
                body = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(body, dict):
                    body = {}
            except Exception:
                body = {}
        try:
            out, code = fn(q, body, h)
        except Exception as e:
            print("CINEMA ERR %s: %s" % (name, e), flush=True)
            out, code = {"error": "failed"}, 500
        _send(h, out, code)
        return True
    if method != "GET":
        return False
    body = _render(path)
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-cache")
    h.end_headers()
    h.wfile.write(body)
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
        _setup()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_cinema3_patched", False):
        _patched = True
        return True
    og = cls.do_GET
    op = getattr(cls, "do_POST", None)

    def do_GET(self):
        try:
            if _serve(self, "GET"):
                return
        except (BrokenPipeError, ConnectionResetError):
            return
        return og(self)

    def do_POST(self):
        try:
            if _serve(self, "POST"):
                return
        except (BrokenPipeError, ConnectionResetError):
            return
        return op(self) if op else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls._cinema3_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    counts = {}
    if "conn" in _ctx:
        try:
            r = _rows("SELECT COUNT(*),COALESCE(SUM(unlocks),0),COALESCE(SUM(likes),0),COALESCE(SUM(comments),0) "
                      "FROM studio_video WHERE status='live'")[0]
            counts = {"videos": r[0], "paid_views": r[1], "likes": r[2], "comments": r[3]}
        except Exception:
            pass
    return {"module": "cinema", "version": VERSION, "armed": armed,
            "serves": ["/cinema", "/cinema/v/<id>", "/cinema/@<name>", "/cinema/api/*"],
            "counts": counts, "wing": SITE + "/cinema"}, 200

```


## `modules/cinemafeed.py`

80 lines, 4430 bytes

```python
"""
modules/cinemafeed.py  v1.0.0
The video feed for the sebbi.pro Cinema (/cinema).

    GET /x/cinemafeed/list     every video, grouped by channel   (public)
    GET /x/cinemafeed/status   count and channels                (public)

To add or remove a video, edit the VIDEOS list below: one line per video,
(YouTube id, title, channel). The id is the 11 characters after "v=" in a
YouTube link. Nothing else needs changing; the cinema page reads this feed.
"""

VERSION = "1.0.0"
PUBLIC = {("GET", "list"), ("GET", "status"), ("GET", "spec")}

VIDEOS = [
    # NVIDIA and IBM
    ("gM1dLdpDR50", "What Is Trustworthy AI?", "NVIDIA"),
    ("f6dx3Yh-Tww", "What is AI governance?", "IBM Research"),
    ("Q020C-Jw0o8", "The Importance of AI Governance", "IBM Technology"),
    ("0oeD2Wf25wY", "Mastering AI Risk: NIST's Framework Explained", "IBM Technology"),
    # EU AI Act
    ("ya5uBFs41Ug", "EU's AI Act explained for everyone", "EU AI Act"),
    ("oWHCyLfUgUw", "EU AI Act Explained: Everything You Must Know", "EU AI Act"),
    ("s_rxOnCt3HQ", "The EU's AI Act Explained", "EU AI Act"),
    ("xUHuR5qXbMY", "EU AI Act explained for your business", "EU AI Act"),
    ("1Z6NA7Chkn4", "The EU AI Act explained in the time of a coffee", "EU AI Act"),
    ("GELAXU9XReI", "Understanding the EU AI Act: key facts", "EU AI Act"),
    ("lwJXCPsBJfc", "The EU AI Act: what it means for AI and DevOps", "EU AI Act"),
    ("4A33y0B9V0k", "The EU AI Act: what you need to know", "EU AI Act"),
    # AI safety
    ("qe9QSCF-d88", "The Catastrophic Risks of AI and a Safer Path", "Yoshua Bengio · TED"),
    ("dc3R_G5DJ50", "Yoshua Bengio's warning on AI safety", "Yoshua Bengio"),
    ("95xpd9FadVk", "We need AI systems to be 10 million times safer", "Stuart Russell"),
    ("qrvK_KuIeJk", "Godfather of AI: the 60 Minutes interview", "Geoffrey Hinton"),
    ("AUGHMx7iAxk", "AI safety risks and the future of AI", "Geoffrey Hinton"),
    ("eHSn50wnBRQ", "Hinton warns about the future of AI", "Geoffrey Hinton"),
    ("5qBDQgfeB6s", "AI has progressed even faster than I thought", "Geoffrey Hinton"),
    ("giT0ytynSqg", "Godfather of AI: trying to warn them", "Geoffrey Hinton"),
    ("hrnQ7chut7A", "Mapping the catastrophic risks of AI", "AI Safety"),
    # Microsoft responsible AI
    ("poMZXS6iQeU", "Responsible AI: Microsoft's AI principles", "Microsoft"),
    ("8Ra5L1aQ5YM", "Responsible AI Principles, episode 3", "Microsoft"),
    ("dnC8-uUZXSc", "Our approach to responsible AI", "Microsoft"),
    ("lkIlsgrIMtU", "Developing Microsoft's Responsible AI Standard", "Microsoft"),
    ("7Mv9VZEDBC4", "How Microsoft drives responsible AI", "Microsoft"),
    ("XWpXxUc-GJY", "Responsible AI in action: principles to engineering", "Microsoft"),
    # NIST AI RMF
    ("CkplyRCYuco", "NIST AI Risk Management Framework explained simply", "NIST AI RMF"),
    ("y3foG0ALLVc", "NIST AI Risk Management Framework explained", "NIST AI RMF"),
    ("3B0ELJTViMs", "NIST AI RMF: a practical guide", "NIST AI RMF"),
    ("7xcM_edGNyE", "NIST AI RMF: the full guide", "NIST AI RMF"),
    ("rbFt34UmngY", "The NIST AI Risk Management Framework", "NIST AI RMF"),
    ("Ufr3aklALVo", "AI risk management explained", "NIST AI RMF"),
    # Agentic AI
    ("mJjTLRQtJdo", "Agent risk, security and AI sprawl in 2026", "Agentic AI"),
    ("YtgQ0q53GV4", "Agentic AI will redefine risk", "Agentic AI"),
    # ISO 42001
    ("YdPyeVvYtzs", "ISO/IEC 42001:2023 explained", "ISO 42001"),
    ("0BXySa973Q4", "ISO 42001 explained in 5 minutes", "ISO 42001"),
    ("FAQhV3iG6Fg", "Navigating the ISO 42001 standard", "ISO 42001"),
    ("O4iKEr5AIi4", "What is ISO/IEC 42001?", "ISO 42001"),
    ("hSz71vISZMA", "What is the AI management system standard?", "ISO 42001"),
    ("yxE3bCP3aTg", "ISO 42001: simple explanation with examples", "ISO 42001"),
    ("jhQRtCO_5n0", "ISO/IEC 42001 AI governance bootcamp", "ISO 42001"),
]


def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()
    vids = [{"id": i, "title": t, "channel": c} for i, t, c in VIDEOS]
    if action == "list":
        return {"count": len(vids), "videos": vids}, 200
    chans = []
    for v in vids:
        if v["channel"] not in chans:
            chans.append(v["channel"])
    return {"module": "cinemafeed", "version": VERSION, "count": len(vids),
            "channels": chans, "list": "https://sebbi.pro/x/cinemafeed/list"}, 200

```


## `modules/codebase.py`

489 lines, 21403 bytes

```python
#!/usr/bin/env python3
"""
modules/codebase.py  -  dated evidence of what you held, and when
=================================================================

WHAT THIS IS, STATED HONESTLY FIRST
-----------------------------------
This does not prove ownership. Nothing cryptographic can. Ownership of
software is a legal fact established by authorship, company records and
signed assignment - not by a hash.

What it does produce is the evidence that decides most disputes about
software in practice: a dated, tamper-evident, externally anchored record
that a specific person held a specific body of code, in a specific form, at
a specific moment. When two parties later disagree about who had what
first, that is the question a court, a mediator or an investor actually
asks - and it is normally answered with commit dates, which are settable
fields that prove nothing.

This answers it with arithmetic instead.

WHAT IT DOES
------------
    POST /x/codebase/seal

Walks the deployed source tree, hashes every file, builds one manifest root
over all of them, and seals that root - together with a declaration of
authorship you supply - into the chain. From there it is anchored
externally and handed to peer chains like every other block.

Run it again next week and you get a second dated point. Run it on every
deploy and you accumulate a continuous, uneditable record of the codebase
evolving under your hand, which is a far stronger thing than a single
snapshot: a body of work with a history is much harder to dispute than a
file that appeared once.

WHAT THE MANIFEST CONTAINS - AND WHAT IT DOES NOT
-------------------------------------------------
For each file: its path and the SHA-256 of its exact bytes. Nothing else.
No contents leave the server, ever, by any route here. The hashes are
one-way, so the manifest reveals nothing about what the code does; it only
lets you demonstrate later that a file you hold now is byte-identical to
the file you held then.

The manifest route is deliberately KEYED rather than public. Only the root,
the file count and the total byte size are public. A public file listing
would hand an attacker a map of the deployment for no gain - the root is
all a third party needs in order to check a manifest you show them.

Excluded by default and never hashed: version control internals, caches,
databases, and anything that looks like a secret. Sealing a hash of your
own credentials file would be a poor way to protect them.

HOW YOU USE IT IN A DISPUTE
---------------------------
  1. You produce the sealed root, its block index, and the chain's
     external anchor.
  2. You produce your copy of the code.
  3. Anyone recomputes the manifest from your copy - the rules are
     published at /x/codebase/spec - and compares.

If it matches, you demonstrably held exactly that code no later than the
sealing time, and the record of it has not been altered since, because it
is a block in an anchored chain that peers also hold.

WHAT STILL HAS TO HAPPEN OUTSIDE THIS FILE
------------------------------------------
Stated plainly, because a module that let you believe it had settled your
legal position would be doing you harm:

  - Copyright arises on authorship. Sealing evidences it; it does not
    create or register it.
  - If a company operates the platform, the IP needs to sit with the right
    entity in writing, or the position is muddier than it looks.
  - Where two parties have collaborated, the only reliable answer is an
    agreement saying who owns what, signed before it matters rather than
    after.

This module makes the factual record unarguable. The legal position is a
separate job and needs a solicitor, not a hash.

    POST /x/codebase/seal      hash the tree, seal the root      (keyed)
    GET  /x/codebase/manifest  the full file list for a seal     (keyed)
    GET  /x/codebase/history   every seal, with root changes     (public)
    GET  /x/codebase/root      the latest sealed root            (public)
    GET  /x/codebase/spec      how to recompute it yourself      (public)
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Roots and history are public - a dated claim nobody can check is not
# evidence. The file listing is keyed, because it is a map of the
# deployment and a third party never needs it to verify a manifest.
PUBLIC = {("GET", "history"), ("GET", "root"), ("GET", "spec")}

FILE_PREFIX = b"AILEASH-FILE-v1:"
MANIFEST_PREFIX = b"AILEASH-MANIFEST-v1:"

MAX_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

# Never walked into.
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
             "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
             "dist", "build", ".cache", "backups"}

# Never hashed. Secrets and databases are excluded on purpose - a hash of
# your credentials file is not evidence of anything you want to prove.
SKIP_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal",
                 ".db-shm", ".pyc", ".pyo", ".log", ".ots", ".pem", ".key",
                 ".crt", ".p12", ".pfx")
SKIP_NAMES = {".env", ".env.local", ".env.production", "secrets.json",
              "credentials.json", ".netrc", "id_rsa", ".DS_Store"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS codebase_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "manifest_root TEXT,file_count INTEGER,total_bytes INTEGER,"
                  "declaration TEXT,manifest TEXT,sealed REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cb_root ON codebase_seal(manifest_root)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _app_root():
    """The directory the application is deployed from.

    This module lives in modules/, so the parent of that directory is the
    tree we want. Resolved rather than assumed, so it is correct whatever
    the working directory happens to be when the server starts.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    return parent if parent else here


def _skip(name):
    if name in SKIP_NAMES:
        return True
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in SKIP_SUFFIXES)


def _file_hash(path):
    """SHA-256 of the exact bytes, read in chunks so a large file cannot
    exhaust memory."""
    digest = hashlib.sha256()
    digest.update(FILE_PREFIX)
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                return None, size
            digest.update(chunk)
    return digest.hexdigest(), size


def _walk(root):
    """Every file under root, sorted by relative path.

    Sorting matters: the manifest must be reproducible by anyone holding
    the same files, and directory order is not stable across systems.
    """
    entries, skipped, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if _skip(filename):
                skipped.append(os.path.relpath(os.path.join(dirpath, filename), root))
                continue
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                digest, size = _file_hash(full)
            except OSError:
                skipped.append(relative)
                continue
            if digest is None:
                skipped.append(relative)
                continue
            entries.append({"path": relative, "sha256": digest, "bytes": size})
            total += size
            if len(entries) >= MAX_FILES:
                return entries, skipped, total, True
    return entries, skipped, total, False


def _manifest_root(entries):
    """One root over the whole tree.

    Deliberately a flat, ordered digest rather than a Merkle tree: there is
    no need for per-file proofs here, and a rule anyone can reimplement in
    four lines is worth more than a clever structure nobody checks.
    """
    digest = hashlib.sha256()
    digest.update(MANIFEST_PREFIX)
    for entry in entries:
        digest.update(("%s\0%s\n" % (entry["path"], entry["sha256"])).encode("utf-8"))
    return digest.hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _seal(ctx, api_key, data):
    author = str(data.get("author", "") or "").strip()[:120]
    entity = str(data.get("entity", "") or "").strip()[:120]
    statement = str(data.get("statement", "") or "").strip()[:1000]

    if not author:
        return {"error": "author_required",
                "message": "The name of the person declaring authorship. This is sealed "
                           "verbatim and becomes part of the permanent record."}, 400

    root_path = _app_root()
    started = time.time()
    entries, skipped, total_bytes, truncated = _walk(root_path)
    if not entries:
        return {"error": "nothing_to_seal",
                "message": "No files found to hash under the application root."}, 500

    manifest_root = _manifest_root(entries)
    now = time.time()

    declaration = {
        "author": author,
        "entity": entity or None,
        "statement": statement or None,
        "declared_at": _iso(now),
    }

    ev = {"user_id": "cb:" + manifest_root[:16], "action": "codebase_sealed", "amount": 0,
          "country": "UK", "device_id": "codebase", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CODEBASE_SEALED", "score": 0, "codebase_version": VERSION,
           "manifest_root": manifest_root, "file_count": len(entries),
           "total_bytes": total_bytes, "author": author, "entity": entity or None,
           "statement": statement or None,
           "detail": "root=%s;files=%d;bytes=%d;author=%s"
                     % (manifest_root, len(entries), total_bytes, author)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT manifest_root,sealed FROM codebase_seal ORDER BY id ASC").fetchall()
        ctx["conn"].execute(
            "INSERT INTO codebase_seal(api_key,manifest_root,file_count,total_bytes,"
            "declaration,manifest,sealed,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, manifest_root, len(entries), total_bytes,
             json.dumps(declaration), json.dumps(entries), now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "manifest_root": manifest_root,
        "file_count": len(entries), "total_bytes": total_bytes,
        "files_skipped": len(skipped),
        "sealed_at": _iso(now),
        "took_seconds": round(now - started, 2),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "declaration": declaration,
        "seal_number": len(prior) + 1,
        "codebase_version": VERSION,
        "what_this_establishes": ("That the person named above held a body of code producing "
                                  "exactly this manifest root, no later than this moment, and "
                                  "that the record cannot be altered afterwards - it is a block "
                                  "in a chain that is externally anchored and held by peers."),
        "what_it_does_not": ("It does not establish legal ownership. Ownership comes from "
                             "authorship, company records and signed assignment. This is the "
                             "dated factual record those arguments rest on, not a substitute "
                             "for them."),
        "how_to_use_it": ("Keep this response. To demonstrate the claim later, produce your copy "
                          "of the code and let anyone recompute the manifest root from it using "
                          "the published rules. If it matches, you held exactly that code by "
                          "this date."),
        "verify_the_block": "/x/consistency/ancestor?tip=" + audit_hash,
        "spec": "/x/codebase/spec",
    }

    if truncated:
        out["truncated"] = ("Hit the %d file cap. The root covers the files listed and no more - "
                            "raise MAX_FILES if the tree is genuinely larger." % MAX_FILES)
    if prior:
        last_root, last_time = prior[-1]
        if last_root == manifest_root:
            out["unchanged_since"] = _iso(last_time)
            out["message"] = ("Identical to the previous seal. The codebase has not changed "
                              "since %s and now carries an additional dated witness."
                              % _iso(last_time))
        else:
            out["previous_root"] = last_root
            out["previous_sealed_at"] = _iso(last_time)
            out["message"] = ("The codebase has changed since the last seal. Both roots remain "
                              "in the chain - a dated history of the work, which is stronger "
                              "evidence than any single snapshot.")
    else:
        out["message"] = ("First seal. Run this on every deploy and the history becomes a "
                          "continuous record of the work developing under one hand.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _manifest(ctx, data):
    root = str(data.get("root", data.get("manifest_root", ""))).strip().lower()
    with ctx["lock"]:
        if root:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal WHERE manifest_root=? LIMIT 1",
                (root,)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "not_found", "root": root or None}, 404

    try:
        files = json.loads(row[4])
    except Exception:
        files = []
    try:
        declaration = json.loads(row[3])
    except Exception:
        declaration = None

    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "declaration": declaration, "sealed_at": _iso(row[5]),
            "sealed_in_chain": row[6], "block_index": row[7],
            "files": files,
            "codebase_version": VERSION,
            "note": "Paths and hashes only. No file contents are held or returned by any route "
                    "in this module."}, 200


def _history(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,declaration,sealed,audit_hash,"
            "block_index FROM codebase_seal ORDER BY id ASC LIMIT 500").fetchall()
    if not rows:
        return {"count": 0, "seals": [],
                "message": "No codebase seal recorded yet."}, 200

    seals, last = [], None
    for root, count, total, declaration, sealed, audit_hash, block_index in rows:
        try:
            parsed = json.loads(declaration)
            author = parsed.get("author")
        except Exception:
            author = None
        seals.append({"manifest_root": root, "file_count": count, "total_bytes": total,
                      "author": author, "sealed_at": _iso(sealed),
                      "sealed_in_chain": audit_hash, "block_index": block_index,
                      "changed_from_previous": last is not None and root != last})
        last = root

    authors = {s["author"] for s in seals if s["author"]}
    return {"count": len(seals),
            "first_sealed": seals[0]["sealed_at"], "latest_sealed": seals[-1]["sealed_at"],
            "distinct_roots": len({s["manifest_root"] for s in seals}),
            "declared_authors": sorted(authors),
            "seals": seals,
            "codebase_version": VERSION,
            "what_this_is": "A dated, uneditable record of one body of code developing over "
                            "time under a declared author. A continuous history is materially "
                            "harder to dispute than a single snapshot.",
            "file_list": "Keyed - /x/codebase/manifest. The root is all anyone needs to check a "
                         "manifest you show them."}, 200


def _root(ctx):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,sealed,audit_hash,block_index,"
            "declaration FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "never_sealed"}, 404
    try:
        author = json.loads(row[6]).get("author")
    except Exception:
        author = None
    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "sealed_at": _iso(row[3]), "sealed_in_chain": row[4], "block_index": row[5],
            "declared_author": author,
            "codebase_version": VERSION,
            "verify_the_block": "/x/consistency/ancestor?tip=" + row[4],
            "recompute_it": "/x/codebase/spec"}, 200


def _spec():
    return {
        "codebase_version": VERSION,
        "purpose": "Dated, tamper-evident evidence that a named person held a specific body of "
                   "code at a specific moment.",
        "not_ownership": "This does not establish legal ownership and is not offered as though "
                         "it does. Ownership comes from authorship, company records and signed "
                         "assignment. This is the factual record those arguments rest on.",
        "file_hash": "sha256('AILEASH-FILE-v1:' || exact_file_bytes) as lowercase hex",
        "manifest_root": "sha256('AILEASH-MANIFEST-v1:' || for each file in path order: "
                         "path + NUL + file_hash + newline) as lowercase hex",
        "ordering": "files sorted by relative path, forward slashes, relative to the "
                    "application root",
        "excluded": {
            "directories": sorted(SKIP_DIRS),
            "suffixes": list(SKIP_SUFFIXES),
            "names": sorted(SKIP_NAMES),
            "why": "Version control internals and caches are not the work. Databases and "
                   "anything resembling a secret are excluded because hashing them proves "
                   "nothing worth proving and risks something worth protecting.",
        },
        "recompute_it_yourself": [
            "Take your copy of the source tree.",
            "Drop the excluded directories, suffixes and names above.",
            "Hash each remaining file with the file rule.",
            "Sort by relative path and apply the manifest rule.",
            "Compare with the sealed root. A match means byte-identical code.",
        ],
        "privacy": "No file contents are stored or returned by any route. The manifest holds "
                   "paths and one-way hashes only, and the file list itself is keyed.",
        "the_discipline": "Seal on every deploy. A single snapshot is a claim about one day; a "
                          "continuous dated history is a record of the work.",
        "what_to_do_as_well": "Get the legal position in writing - entity ownership of the IP, "
                              "and a signed agreement with any collaborator saying who owns "
                              "what. Do it before it matters. This module makes the facts "
                              "unarguable; it cannot make the paperwork exist.",
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
            return _history(ctx)
        if action == "root":
            return _root(ctx)
        if action == "manifest":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _manifest(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "root", "manifest (keyed)"],
            "POST": ["seal (keyed)"]}, 404

```
