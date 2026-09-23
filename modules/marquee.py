"""
modules/marquee.py  v1.0.0
The 10p Wing: creator submissions for the sebbi.pro cinema.

    POST /x/marquee/submit    {url, title, creator, price}   (public)
    GET  /x/marquee/list      approved screens                (public)
    GET  /x/marquee/status    counts                          (public)
    GET  /x/marquee/pending   everything waiting              (keyed)
    POST /x/marquee/approve   {id, approved}                  (keyed)

We never hold anyone's video. A submission is a link, a title, a name and a
price, nothing else. Every submission is sealed into the chain when it lands,
so the date it was sent is provable, and nothing appears in the cinema until
it has been approved.
"""

import re
import time

VERSION = "1.0.0"
PUBLIC = {("POST", "submit"), ("GET", "list"), ("GET", "status"), ("GET", "spec")}
KEY = "public-marquee"
URL_RE = re.compile(r"^https://[A-Za-z0-9.\-]{3,253}(/[^\s<>\"']{0,300})?$")
CLEAN = re.compile(r"[<>\"'\\]")
_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS marquee(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                            "url TEXT UNIQUE,title TEXT,creator TEXT,price INTEGER,at REAL,"
                            "approved INTEGER DEFAULT 0,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _clean(s, n):
    return CLEAN.sub("", str(s or "")).strip()[:n]


def _rows(ctx, approved=None):
    q = "SELECT id,url,title,creator,price,at,approved,audit_hash,block_index FROM marquee"
    if approved is not None:
        q += " WHERE approved=%d" % (1 if approved else 0)
    q += " ORDER BY id DESC LIMIT 200"
    with ctx["lock"]:
        rows = ctx["conn"].execute(q).fetchall()
    return [{"id": r[0], "url": r[1], "title": r[2], "creator": r[3], "price": r[4],
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[5])),
             "approved": bool(r[6]), "sealed_in_chain": r[7], "block_index": r[8]} for r in rows]


def _submit(ctx, data):
    url = str(data.get("url", "")).strip()
    if not URL_RE.match(url):
        return {"received": False, "message": "That link does not look right. It needs to start with https://"}, 400
    title = _clean(data.get("title"), 80) or "Untitled"
    creator = _clean(data.get("creator"), 40) or "Anonymous"
    try:
        price = max(1, min(500, int(float(data.get("price", 10)))))
    except (TypeError, ValueError):
        price = 10
    with ctx["lock"]:
        if ctx["conn"].execute("SELECT 1 FROM marquee WHERE url=?", (url,)).fetchone():
            return {"received": False, "message": "That link is already in the queue."}, 200
    now = time.time()
    ev = {"user_id": "mrq:" + creator[:24], "action": "marquee_submission", "amount": 0,
          "country": "UK", "device_id": "cinema", "anomaly": 0, "device_risk": 0}
    res = {"decision": "MARQUEE_SUBMITTED", "score": 0, "marquee_version": VERSION,
           "detail": "creator=%s;title=%s;price=%d;url=%s" % (creator, title, price, url)}
    out = ctx["seal"](ev, res, now, KEY)
    audit_hash = out[0] if isinstance(out, (list, tuple)) else out
    block = out[1] if isinstance(out, (list, tuple)) and len(out) > 1 else None
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO marquee(url,title,creator,price,at,approved,audit_hash,block_index)"
                            " VALUES(?,?,?,?,?,0,?,?)", (url, title, creator, price, now, audit_hash, block))
        ctx["conn"].commit()
    return {"received": True, "title": title, "creator": creator, "price": price,
            "sealed_in_chain": audit_hash, "block_index": block,
            "message": "Sealed. It goes up once it has been looked at."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}
    if action == "submit" and method == "POST":
        return _submit(ctx, data)
    if action == "list":
        return {"screens": _rows(ctx, True)}, 200
    if action == "pending":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        return {"waiting": _rows(ctx, False)}, 200
    if action == "approve" and method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        try:
            i = int(data.get("id"))
        except (TypeError, ValueError):
            return {"error": "id_required"}, 400
        ok = 0 if str(data.get("approved", "1")).lower() in ("0", "false", "no") else 1
        with ctx["lock"]:
            ctx["conn"].execute("UPDATE marquee SET approved=? WHERE id=?", (ok, i))
            ctx["conn"].commit()
        return {"id": i, "approved": bool(ok)}, 200
    with ctx["lock"]:
        a = ctx["conn"].execute("SELECT COUNT(*) FROM marquee WHERE approved=1").fetchone()[0]
        w = ctx["conn"].execute("SELECT COUNT(*) FROM marquee WHERE approved=0").fetchone()[0]
    return {"module": "marquee", "version": VERSION, "on_screen": a, "waiting": w,
            "list": "https://sebbi.pro/x/marquee/list"}, 200
