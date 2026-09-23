"""
modules/credits.py  v1.0.0
Credits: the money side of Monop Studio, running on the chain.

A viewer tops up once. Every unlock spends a few pence of that balance, the
creator's share lands in their balance, and both sides are sealed into the
chain. Creators paste no payment links, viewers set nothing up, and a card is
touched once per top-up instead of once per view.

Served with permissive CORS from a clean /c/ prefix, because locked players
live on other people's sites and call in from there:

    GET  /c/hello?viewer=            balance, or a new viewer id     (public)
    GET  /c/check?viewer=&video=     is this already unlocked         (public)
    POST /c/unlock                   spend the credit, seal it        (public)
    POST /c/topup                    add credit (see STRIPE below)    (public)
    GET  /c/earnings?creator=        a creator's balance and views    (public)
    GET  /x/credits/status           counts                           (public)

THE ONE THING LEFT TO WIRE: _checkout_url() below. Set the environment
variable STRIPE_TOPUP_LINK to a Stripe payment link and /credits sends buyers
there; until then, TEST_MODE hands out test credit so the whole flow runs end
to end. Nothing else in this file changes when Stripe goes in.
"""

import json
import os
import re
import sys
import time
import urllib.parse

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

TEST_MODE = os.environ.get("CREDITS_TEST_MODE", "1") != "0"
TEST_GRANT = 100          # pence handed to a new viewer while in test mode
CREATOR_SHARE = 0.70      # 7p of every 10p
MAX_PRICE = 500
KEY = "public-credits"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
VID_RE = re.compile(r"^[A-Za-z0-9_.:-]{4,120}$")
NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]")

_ready = False
_patched = False
_ctx = {}


def _checkout_url(pence):
    """The only Stripe-shaped hole. Return a URL to send a buyer to, or None."""
    link = os.environ.get("STRIPE_TOPUP_LINK", "").strip()
    return (link + ("&" if "?" in link else "?") + "client_reference_id=topup_%d" % pence) if link else None


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS credit_viewer(id TEXT PRIMARY KEY,balance INTEGER,"
                  "spent INTEGER DEFAULT 0,created REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS credit_unlock(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "viewer TEXT,video TEXT,creator TEXT,price INTEGER,at REAL,audit_hash TEXT,"
                  "block_index INTEGER,UNIQUE(viewer,video))")
        c.execute("CREATE TABLE IF NOT EXISTS credit_creator(name TEXT PRIMARY KEY,balance INTEGER,"
                  "views INTEGER DEFAULT 0)")
        c.commit()
    _ready = True


def _seal(kind, detail, extra):
    now = time.time()
    ev = {"user_id": "crd:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "credits", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "credits_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, now, KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _viewer(vid, make=True):
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT balance,spent FROM credit_viewer WHERE id=?", (vid,)).fetchone()
        if row:
            return {"balance": row[0], "spent": row[1]}
        if not make:
            return None
        start = TEST_GRANT if TEST_MODE else 0
        _ctx["conn"].execute("INSERT INTO credit_viewer(id,balance,spent,created) VALUES(?,?,0,?)",
                             (vid, start, time.time()))
        _ctx["conn"].commit()
    return {"balance": start, "spent": 0}


# ---------------------------------------------------------------- commands

def c_hello(q, body):
    vid = (q.get("viewer") or body.get("viewer") or "").strip()
    if not ID_RE.match(vid):
        return {"error": "viewer id needed (8 to 64 characters, letters and numbers)"}, 400
    v = _viewer(vid)
    return {"viewer": vid, "balance_pence": v["balance"], "spent_pence": v["spent"],
            "test_mode": TEST_MODE, "topup": "https://sebbi.pro/credits"}, 200


def c_check(q, body):
    vid = (q.get("viewer") or body.get("viewer") or "").strip()
    video = (q.get("video") or body.get("video") or "").strip()
    if not ID_RE.match(vid) or not VID_RE.match(video):
        return {"unlocked": False, "error": "viewer and video needed"}, 400
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT block_index,at FROM credit_unlock WHERE viewer=? AND video=?",
                                   (vid, video)).fetchone()
    v = _viewer(vid)
    return {"unlocked": bool(row), "block_index": row[0] if row else None,
            "balance_pence": v["balance"]}, 200


def c_unlock(q, body):
    vid = str(body.get("viewer") or q.get("viewer") or "").strip()
    video = str(body.get("video") or q.get("video") or "").strip()
    creator = NAME_RE.sub("", str(body.get("creator") or "Anonymous"))[:40] or "Anonymous"
    try:
        price = max(1, min(MAX_PRICE, int(float(body.get("price") or q.get("price") or 10))))
    except (TypeError, ValueError):
        price = 10
    if not ID_RE.match(vid) or not VID_RE.match(video):
        return {"unlocked": False, "error": "viewer and video needed"}, 400

    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT block_index FROM credit_unlock WHERE viewer=? AND video=?",
                                   (vid, video)).fetchone()
    if row:
        v = _viewer(vid)
        return {"unlocked": True, "already": True, "block_index": row[0],
                "balance_pence": v["balance"]}, 200

    v = _viewer(vid)
    if v["balance"] < price:
        return {"unlocked": False, "reason": "not_enough_credit", "price_pence": price,
                "balance_pence": v["balance"], "topup": "https://sebbi.pro/credits",
                "message": "You need %dp and have %dp. Top up and it unlocks straight away."
                           % (price, v["balance"])}, 402

    share = int(round(price * CREATOR_SHARE))
    audit_hash, block = _seal("paid_view", "video=%s;creator=%s;price=%d;creator_share=%d"
                              % (video, creator, price, share),
                              {"video": video, "creator": creator, "price_pence": price,
                               "creator_pence": share, "platform_pence": price - share})
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("UPDATE credit_viewer SET balance=balance-?, spent=spent+? WHERE id=?", (price, price, vid))
        c.execute("INSERT OR IGNORE INTO credit_creator(name,balance,views) VALUES(?,0,0)", (creator,))
        c.execute("UPDATE credit_creator SET balance=balance+?, views=views+1 WHERE name=?", (share, creator))
        c.execute("INSERT OR IGNORE INTO credit_unlock(viewer,video,creator,price,at,audit_hash,block_index)"
                  " VALUES(?,?,?,?,?,?,?)", (vid, video, creator, price, time.time(), audit_hash, block))
        c.commit()
    v = _viewer(vid)
    return {"unlocked": True, "price_pence": price, "creator_pence": share,
            "balance_pence": v["balance"], "sealed_in_chain": audit_hash, "block_index": block,
            "verify": "https://sebbi.pro/x/walk/block?index=%s" % block}, 200


def c_topup(q, body):
    vid = str(body.get("viewer") or q.get("viewer") or "").strip()
    try:
        pence = max(50, min(10000, int(float(body.get("pence") or q.get("pence") or 500))))
    except (TypeError, ValueError):
        pence = 500
    if not ID_RE.match(vid):
        return {"error": "viewer id needed"}, 400
    url = _checkout_url(pence)
    if url:
        return {"paid": False, "checkout": url, "pence": pence,
                "message": "Pay there and your credit lands when you come back."}, 200
    if not TEST_MODE:
        return {"paid": False, "error": "no_checkout_configured",
                "message": "Card top-ups are not switched on yet."}, 503
    _viewer(vid)
    audit_hash, block = _seal("test_topup", "viewer=%s;pence=%d" % (vid[:12], pence),
                              {"pence": pence, "test_mode": True})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_viewer SET balance=balance+? WHERE id=?", (pence, vid))
        _ctx["conn"].commit()
    v = _viewer(vid)
    return {"paid": True, "test_mode": True, "added_pence": pence, "balance_pence": v["balance"],
            "sealed_in_chain": audit_hash, "block_index": block}, 200


def c_earnings(q, body):
    name = NAME_RE.sub("", str(q.get("creator") or body.get("creator") or ""))[:40]
    if not name:
        return {"error": "creator needed"}, 400
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT balance,views FROM credit_creator WHERE name=?", (name,)).fetchone()
        recent = _ctx["conn"].execute("SELECT video,price,at,block_index FROM credit_unlock WHERE creator=?"
                                      " ORDER BY id DESC LIMIT 25", (name,)).fetchall()
    return {"creator": name, "balance_pence": row[0] if row else 0, "paid_views": row[1] if row else 0,
            "recent": [{"video": r[0], "price_pence": r[1],
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2])),
                        "block_index": r[3]} for r in recent]}, 200


CMDS = {"hello": c_hello, "check": c_check, "unlock": c_unlock, "topup": c_topup, "earnings": c_earnings}


# ---------------------------------------------------------------- transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


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


def _run(h, method):
    u = urllib.parse.urlparse(h.path)
    name = u.path[3:].strip("/").lower()
    if name not in CMDS:
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/credits/status once"}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
            if n:
                body = json.loads(h.rfile.read(n).decode("utf-8") or "{}")
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    try:
        out, code = CMDS[name](q, body)
    except Exception as e:
        out, code = {"error": "failed", "detail": str(e)[:160]}, 500
    _send(h, out, code)
    return True


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
    if getattr(cls, "_credits_patched", False):
        _patched = True
        return True
    og, op = cls.do_GET, getattr(cls, "do_POST", None)
    oo = getattr(cls, "do_OPTIONS", None)

    def do_GET(self):
        if self.path.startswith("/c/") and _run(self, "GET"):
            return
        return og(self)

    def do_POST(self):
        if self.path.startswith("/c/") and _run(self, "POST"):
            return
        return op(self) if op else None

    def do_OPTIONS(self):
        if self.path.startswith("/c/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return oo(self) if oo else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls.do_OPTIONS = do_OPTIONS
    cls._credits_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    counts = {}
    if "conn" in _ctx:
        with _ctx["lock"]:
            c = _ctx["conn"]
            counts = {"viewers": c.execute("SELECT COUNT(*) FROM credit_viewer").fetchone()[0],
                      "paid_views": c.execute("SELECT COUNT(*) FROM credit_unlock").fetchone()[0],
                      "creators": c.execute("SELECT COUNT(*) FROM credit_creator").fetchone()[0],
                      "creator_balances_pence": c.execute("SELECT COALESCE(SUM(balance),0) FROM credit_creator").fetchone()[0]}
    return {"module": "credits", "version": VERSION, "armed": armed,
            "test_mode": TEST_MODE, "card_topups_ready": bool(_checkout_url(500)),
            "creator_share": CREATOR_SHARE, "counts": counts,
            "endpoints": ["/c/hello", "/c/check", "/c/unlock", "/c/topup", "/c/earnings"]}, 200
