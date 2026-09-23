# Codebase — part 7 of 40

Contains:
- `modules/credits.py`
- `modules/custody.py`
- `modules/declare.py`
- `modules/demo.py`
- `modules/disclosure.py`
- `modules/dsr.py`


## `modules/credits.py`

505 lines, 21189 bytes

```python
"""
modules/credits.py  v1.1.0
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
    POST /c/topup                    send the buyer to Stripe         (public)
    POST /c/stripe                   Stripe tells us a payment cleared (Stripe only, signed)
    GET  /c/grant?key=&viewer=&pence=&session=   credit by hand       (admin key)
    GET  /c/earnings?creator=        a creator's balance and views    (public)
    GET  /x/credits/status           counts                           (public)

NEW IN 1.1.0
  * /c/stripe: Stripe's webhook. Checks Stripe's signature, then adds the paid
    amount to the viewer's balance and seals the payment in the chain. The same
    Stripe payment can never be credited twice.
  * The checkout link now carries the viewer id (client_reference_id), so the
    webhook knows whose balance to top up.
  * Payments that arrive without a viewer id are kept as "unmatched" and can be
    credited by hand with /c/grant.

RAILWAY VARIABLES
  STRIPE_TOPUP_LINK       the Stripe payment link (already set)
  STRIPE_WEBHOOK_SECRET   the signing secret Stripe shows when you add the webhook
  CREDITS_ADMIN_KEY       any long password you choose, for /c/grant
  CREDITS_TEST_MODE       set to 0 to stop giving new viewers 100p free
"""

import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.parse

VERSION = "1.1.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

TEST_MODE = os.environ.get("CREDITS_TEST_MODE", "1") != "0"
TEST_GRANT = 100          # pence handed to a new viewer while in test mode
CREATOR_SHARE = 0.70      # 7p of every 10p
MAX_PRICE = 500
SIG_TOLERANCE = 300       # seconds a Stripe signature stays valid
KEY = "public-credits"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
VID_RE = re.compile(r"^[A-Za-z0-9_.:-]{4,120}$")
NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]")
SESSION_RE = re.compile(r"^[A-Za-z0-9_:.-]{4,200}$")

_ready = False
_patched = False
_ctx = {}


def _checkout_url(pence, viewer=""):
    """Stripe payment link, carrying the viewer id so the webhook knows who paid."""
    link = os.environ.get("STRIPE_TOPUP_LINK", "").strip()
    if not link:
        return None
    ref = viewer if ID_RE.match(viewer or "") else "topup_%d" % pence
    return link + ("&" if "?" in link else "?") + "client_reference_id=" + urllib.parse.quote(ref)


def _webhook_secret():
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def _admin_key():
    return os.environ.get("CREDITS_ADMIN_KEY", "").strip()


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
        c.execute("CREATE TABLE IF NOT EXISTS credit_payment(session TEXT PRIMARY KEY,viewer TEXT,"
                  "pence INTEGER,status TEXT,source TEXT,at REAL,audit_hash TEXT,block_index INTEGER)")
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


def _credit_payment(session, viewer, pence, source):
    """Record one payment exactly once; credit the viewer if we know who it is."""
    now = time.time()
    with _ctx["lock"]:
        c = _ctx["conn"]
        row = c.execute("SELECT status,viewer,block_index FROM credit_payment WHERE session=?",
                        (session,)).fetchone()
        if row and row[0] != "unmatched":
            return {"duplicate": True, "status": row[0], "block_index": row[2]}
        if row and row[0] == "unmatched" and not viewer:
            return {"duplicate": True, "status": "unmatched"}
        if not row:
            c.execute("INSERT INTO credit_payment(session,viewer,pence,status,source,at) VALUES(?,?,?,?,?,?)",
                      (session, viewer or "", pence, "pending", source, now))
        else:
            c.execute("UPDATE credit_payment SET status='pending',viewer=? WHERE session=?", (viewer, session))
        c.commit()

    if viewer:
        _viewer(viewer)
    status = "credited" if viewer else "unmatched"
    audit_hash, block = _seal("card_topup" if viewer else "card_topup_unmatched",
                              "session=%s;pence=%d;status=%s;source=%s" % (session[-12:], pence, status, source),
                              {"pence": pence, "status": status, "source": source})
    with _ctx["lock"]:
        c = _ctx["conn"]
        if viewer:
            c.execute("UPDATE credit_viewer SET balance=balance+? WHERE id=?", (pence, viewer))
        c.execute("UPDATE credit_payment SET status=?,audit_hash=?,block_index=? WHERE session=?",
                  (status, audit_hash, block, session))
        c.commit()
    out = {"duplicate": False, "status": status, "pence": pence,
           "sealed_in_chain": audit_hash, "block_index": block}
    if viewer:
        out["balance_pence"] = _viewer(viewer)["balance"]
    return out


def _verify_stripe(raw, sig_header, secret):
    if not secret or not sig_header:
        return False
    t, v1 = None, []
    for part in sig_header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            t = v
        elif k == "v1":
            v1.append(v)
    if not t or not v1:
        return False
    try:
        if abs(time.time() - int(t)) > SIG_TOLERANCE:
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode("utf-8"), t.encode("utf-8") + b"." + raw, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in v1)


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
    _viewer(vid)
    url = _checkout_url(pence, vid)
    if url:
        return {"paid": False, "checkout": url, "pence": pence,
                "message": "Pay there and your credit lands within a few seconds."}, 200
    if not TEST_MODE:
        return {"paid": False, "error": "no_checkout_configured",
                "message": "Card top-ups are not switched on yet."}, 503
    audit_hash, block = _seal("test_topup", "viewer=%s;pence=%d" % (vid[:12], pence),
                              {"pence": pence, "test_mode": True})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_viewer SET balance=balance+? WHERE id=?", (pence, vid))
        _ctx["conn"].commit()
    v = _viewer(vid)
    return {"paid": True, "test_mode": True, "added_pence": pence, "balance_pence": v["balance"],
            "sealed_in_chain": audit_hash, "block_index": block}, 200


def c_stripe(raw, headers):
    secret = _webhook_secret()
    if not secret:
        return {"error": "webhook_not_configured"}, 503
    if not _verify_stripe(raw, headers.get("Stripe-Signature", "") or "", secret):
        return {"error": "bad_signature"}, 400
    try:
        ev = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"error": "bad_json"}, 400
    etype = str(ev.get("type") or "")
    if etype not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {"received": True, "ignored": etype}, 200
    s = (ev.get("data") or {}).get("object") or {}
    if s.get("payment_status") != "paid":
        return {"received": True, "ignored": "not_paid_yet"}, 200
    session = str(s.get("id") or "")[:200]
    if not SESSION_RE.match(session):
        return {"error": "no_session_id"}, 400
    try:
        pence = int(s.get("amount_total") or 0)
    except (TypeError, ValueError):
        pence = 0
    if pence <= 0:
        return {"received": True, "ignored": "zero_amount"}, 200
    ref = str(s.get("client_reference_id") or "").strip()
    viewer = ref if (ID_RE.match(ref) and not ref.startswith("topup_")) else ""
    out = _credit_payment(session, viewer, pence, "stripe")
    out["received"] = True
    return out, 200


def c_grant(q, body):
    key = _admin_key()
    given = str(q.get("key") or body.get("key") or "")
    if not key or not hmac.compare_digest(key, given):
        return {"error": "not_allowed"}, 403
    vid = str(q.get("viewer") or body.get("viewer") or "").strip()
    if not ID_RE.match(vid):
        return {"error": "viewer id needed"}, 400
    session = str(q.get("session") or body.get("session") or "").strip()
    pence = None
    if session:
        if not SESSION_RE.match(session):
            return {"error": "bad session id"}, 400
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT pence FROM credit_payment WHERE session=?", (session,)).fetchone()
        if row:
            pence = row[0]
    if pence is None:
        try:
            pence = max(1, min(10000, int(float(q.get("pence") or body.get("pence") or 0))))
        except (TypeError, ValueError):
            return {"error": "pence needed"}, 400
    if not session:
        session = "manual:%d" % int(time.time() * 1000)
    out = _credit_payment(session, vid, pence, "manual")
    out["viewer"] = vid
    return out, 200


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


CMDS = {"hello": c_hello, "check": c_check, "unlock": c_unlock, "topup": c_topup,
        "grant": c_grant, "earnings": c_earnings}


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
    if name not in CMDS and name != "stripe":
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/credits/status once"}, 503)
        return True
    _setup()

    raw = b""
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
            raw = h.rfile.read(n) if n else b""
        except Exception:
            raw = b""

    if name == "stripe":
        if method != "POST":
            _send(h, {"endpoint": "stripe webhook", "ready": bool(_webhook_secret())}, 200)
            return True
        try:
            out, code = c_stripe(raw, h.headers)
        except Exception as e:
            out, code = {"error": "failed", "detail": str(e)[:160]}, 500
        _send(h, out, code)
        return True

    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if raw:
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
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
                      "creator_balances_pence": c.execute("SELECT COALESCE(SUM(balance),0) FROM credit_creator").fetchone()[0],
                      "card_payments": c.execute("SELECT COUNT(*) FROM credit_payment WHERE status='credited'").fetchone()[0],
                      "card_pence": c.execute("SELECT COALESCE(SUM(pence),0) FROM credit_payment WHERE status='credited'").fetchone()[0],
                      "unmatched_payments": c.execute("SELECT COUNT(*) FROM credit_payment WHERE status='unmatched'").fetchone()[0]}
    return {"module": "credits", "version": VERSION, "armed": armed,
            "test_mode": TEST_MODE, "card_topups_ready": bool(_checkout_url(500)),
            "webhook_ready": bool(_webhook_secret()), "manual_grant_ready": bool(_admin_key()),
            "creator_share": CREATOR_SHARE, "counts": counts,
            "endpoints": ["/c/hello", "/c/check", "/c/unlock", "/c/topup", "/c/stripe",
                          "/c/grant", "/c/earnings"]}, 200

```


## `modules/custody.py`

491 lines, 19866 bytes

```python
"""
modules/custody.py  v1.0.2  -  independent copies, proven and counted

The self-proving archive file (/x/archive) can be checked anywhere. This
module proves WHERE it is actually held, by parties other than sebbi.pro.

Every day it:
  1. asks the Internet Archive whether it holds each recent sealed file, and
     if it does, fetches that copy and checks its fingerprint;
  2. fetches every registered holder's copy and checks its fingerprint;
  3. counts the independent holders whose copy is byte-for-byte a sealed
     file, and SEALS that count - with every holder, address and
     fingerprint - into the chain as a public block.

A copy only counts if it matches a fingerprint sealed in the chain. A holder
only counts if it is not sebbi.pro. The count can be checked by anyone, and
cannot be inflated: every entry names an address you can fetch yourself.

Anyone can become a holder:
  - tap the Internet Archive link on /x/custody/status, or
  - keep the file anywhere public and register the address:
      https://sebbi.pro/x/custody/offer?url=https://your.site/sebbi.json&name=You
    (it is fetched and checked before it is listed), or
  - run the keeper script (/x/custody/keeper) daily to fetch, verify and keep
    each day's file automatically.

Routes (public): status, holders, offer, keeper, spec. run is keyed.
Armed by the first visit to /x/custody/status.
"""

import gzip
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.2"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/custody/"
USER_ID = "system_custody"
UA = "sebbi-custody/1.0.2 (+https://sebbi.pro/x/custody/spec)"
TIMEOUT = 60
MAX_BYTES = 256 * 1024 * 1024
RECENT_FILES = 3
OPERATOR_HOSTS = ("sebbi.pro", "www.sebbi.pro")

PUBLIC = {("GET", a) for a in ("status", "holders", "offer", "keeper", "spec")}

_state = {"armed": False, "ctx": None, "last_run": None, "last_result": None}
_lock = threading.Lock()
_run_lock = threading.Lock()
_offer_busy = threading.BoundedSemaphore(2)


# ---------------------------------------------------------------- helpers

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_holders ("
        "url TEXT PRIMARY KEY, name TEXT, host TEXT, added_at REAL, "
        "last_checked REAL, last_verified REAL, last_fingerprint TEXT, "
        "last_date TEXT, last_status TEXT, times_verified INTEGER DEFAULT 0)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_runs ("
        "day TEXT PRIMARY KEY, sealed_block INTEGER, sealed_hash TEXT, "
        "independent_holders INTEGER, holding_latest INTEGER, "
        "latest_sha256 TEXT, ran_at REAL)")
    conn.commit()


def _host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _public_https(url):
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if p.scheme != "https" or p.port not in (None, 443) or not p.hostname:
        return False
    if p.username or p.password:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443,
                                       proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
    except Exception:
        return False
    return True


def _get(url, max_bytes=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("too large")
    if raw[:2] == b"\x1f\x8b":
        # Archives keep a page exactly as it was sent - often zipped.
        raw = gzip.decompress(raw)
    return raw


def _canonical_sha(raw):
    obj = json.loads(raw.decode("utf-8"))
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _sealed_files():
    """date -> sha256, and sha256 -> file row, from the archive manifest."""
    data = json.loads(_get(SITE + "/x/archive/manifest").decode("utf-8"))
    files = data.get("files") or []
    return files, {f["sha256"]: f for f in files if f.get("sha256")}


def _seal(ctx, action, result):
    seal = (ctx or {}).get("seal")
    if not callable(seal):
        return None, None
    now = time.time()
    result = dict(result, decision=action.upper(), score=0, timestamp=now)
    event = {"user_id": USER_ID, "action": action, "amount": 0,
             "country": "UK", "device_id": "custody", "anomaly": 0,
             "device_risk": 0}
    try:
        res = seal(event, result, now)
    except Exception:
        return None, None
    if isinstance(res, (list, tuple)):
        return res[0], (res[1] if len(res) > 1 else None)
    if isinstance(res, dict):
        return (res.get("audit_hash") or res.get("hash"),
                res.get("block_index") or res.get("index"))
    return res, None


# ---------------------------------------------------------------- checks

def _wayback_captures(target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = json.loads(_get(
            "https://web.archive.org/cdx/search/cdx?url=" +
            urllib.parse.quote(target, safe="") +
            "&output=json&filter=statuscode:200&limit=-10",
            4 * 1024 * 1024).decode("utf-8"))
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = json.loads(_get(
            "https://archive.org/wayback/available?url=" +
            urllib.parse.quote(target, safe=""), 1024 * 1024).decode("utf-8"))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def _check_internet_archive(files):
    """For each recent sealed file: does the Internet Archive hold it, and
    is its copy byte-for-byte the sealed file?"""
    out = []
    for f in files[:RECENT_FILES]:
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
        row = {"holder": "Internet Archive", "date": f.get("date"),
               "sealed_sha256": f["sha256"],
               "archive_it": "https://web.archive.org/save/" + target}
        stamps = _wayback_captures(target)
        if stamps is None:
            row.update({"held": None, "note": "archive could not be asked"})
        elif not stamps:
            row.update({"held": False})
        else:
            row.update({"held": False, "captures_listed": len(stamps)})
            for stamp in stamps[:3]:
                raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, target)
                try:
                    fp = _canonical_sha(_get(raw_url))
                except Exception:
                    continue
                row.update({"held": fp == f["sha256"], "copy": raw_url,
                            "captured": stamp, "fingerprint": fp})
                if fp == f["sha256"]:
                    break
        out.append(row)
    return out


def _check_holder(url, by_sha):
    try:
        fp = _canonical_sha(_get(url))
    except Exception as exc:
        return {"fingerprint": None, "status": "unreachable (%s)"
                % exc.__class__.__name__}
    f = by_sha.get(fp)
    if not f:
        return {"fingerprint": fp,
                "status": "serves a file that is not a sealed archive file"}
    return {"fingerprint": fp, "date": f.get("date"), "status": "verified"}


def _run(ctx, force=False):
    conn, dblock = ctx.get("conn"), ctx.get("lock")
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        done = conn.execute("SELECT sealed_block FROM custody_runs WHERE day = ?",
                            (day,)).fetchone()
        if done and not force:
            return {"ok": True, "skipped": "already counted today",
                    "sealed_block": done[0]}
        holders = conn.execute("SELECT url, name FROM custody_holders").fetchall()

    files, by_sha = _sealed_files()
    if not files:
        return {"ok": False, "error": "no sealed archive files yet"}
    latest = files[0]["sha256"]

    ia = _check_internet_archive(files)
    results = []
    for url, name in holders:
        r = _check_holder(url, by_sha)
        r.update({"holder": name, "url": url})
        results.append(r)
        now = time.time()
        with dblock:
            if r["status"] == "verified":
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_verified = ?, last_fingerprint = ?, last_date = ?, "
                    "last_status = ?, times_verified = times_verified + 1 "
                    "WHERE url = ?", (now, now, r["fingerprint"], r.get("date"),
                                      r["status"], url))
            else:
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_status = ? WHERE url = ?", (now, r["status"], url))
            conn.commit()

    verified = [r for r in results if r["status"] == "verified"]
    ia_held = [r for r in ia if r.get("held")]
    hosts = set(_host(r["url"]) for r in verified)
    if ia_held:
        hosts.add("web.archive.org")
    holding_latest = len([r for r in verified if r["fingerprint"] == latest]) + \
        (1 if any(r["sealed_sha256"] == latest for r in ia_held) else 0)

    result = {"day": day, "latest_file_sha256": latest,
              "independent_holders": len(hosts),
              "holding_latest_file": holding_latest,
              "internet_archive": ia, "registered_holders": results,
              "rule": "A copy counts only if its canonical fingerprint is a "
                      "sealed archive file, and only if it is held somewhere "
                      "other than sebbi.pro. Every entry names an address "
                      "anyone can fetch to check it."}
    sealed_hash, sealed_block = _seal(ctx, "custody_counted", result)
    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO custody_runs (day, sealed_block, sealed_hash, "
            "independent_holders, holding_latest, latest_sha256, ran_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (day, sealed_block, sealed_hash, len(hosts), holding_latest,
             latest, time.time()))
        conn.commit()
    return {"ok": True, "day": day, "independent_holders": len(hosts),
            "holding_latest_file": holding_latest, "sealed_block": sealed_block,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, sealed_block))
            if sealed_block else None}


def _loop():
    time.sleep(120)
    while True:
        ctx = _state.get("ctx")
        if ctx and _run_lock.acquire(blocking=False):
            try:
                _state["last_result"] = _run(ctx)
            except Exception as exc:
                _state["last_result"] = {"ok": False, "error": str(exc)[:200]}
            finally:
                _run_lock.release()
            _state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
        time.sleep(3600)


def _arm(ctx):
    with _lock:
        _state["ctx"] = ctx
        if _state["armed"]:
            return
        _state["armed"] = True
    threading.Thread(target=_loop, name="custody", daemon=True).start()


# ---------------------------------------------------------------- routes

def _q(data, k):
    v = (data or {}).get(k)
    return v[0] if isinstance(v, list) and v else v


def _offer(data, ctx):
    url = str(_q(data, "url") or "").strip()
    name = re.sub(r"[^A-Za-z0-9 .,&'()_-]", "", str(_q(data, "name") or ""))[:60]
    if not url:
        return {"ok": False, "error": "url_required",
                "example": BASE + "offer?url=https://your.site/sebbi.json&name=Your%20Name"}, 400
    if _host(url) in OPERATOR_HOSTS:
        return {"ok": False, "error": "operator_host",
                "detail": "A copy on sebbi.pro is not independent of sebbi.pro."}, 400
    if not _public_https(url):
        return {"ok": False, "error": "not_a_public_https_address"}, 400
    if not _offer_busy.acquire(timeout=10):
        return {"ok": False, "error": "busy"}, 429
    try:
        files, by_sha = _sealed_files()
        r = _check_holder(url, by_sha)
    finally:
        _offer_busy.release()
    if r["status"] != "verified":
        return {"ok": False, "error": "copy_not_verified", "detail": r["status"],
                "fingerprint": r.get("fingerprint"),
                "sealed_files": SITE + "/x/archive/manifest"}, 400
    conn, dblock = ctx["conn"], ctx["lock"]
    now = time.time()
    with dblock:
        _ensure(conn)
        conn.execute(
            "INSERT OR IGNORE INTO custody_holders (url, name, host, added_at, "
            "last_checked, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (url, name or _host(url), _host(url), now, now, now,
             r["fingerprint"], r.get("date"), "verified"))
        conn.commit()
    _, block = _seal(ctx, "custody_holder_registered", {
        "holder": name or _host(url), "url": url,
        "fingerprint": r["fingerprint"], "file_date": r.get("date")})
    return {"ok": True, "registered": url, "holder": name or _host(url),
            "fingerprint": r["fingerprint"], "file_date": r.get("date"),
            "sealed_in_block": block,
            "note": "Your copy was fetched and matches a sealed file. It will "
                    "be re-checked daily and counted in the sealed custody "
                    "count."}, 200


def _holders(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        rows = conn.execute(
            "SELECT url, name, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified FROM custody_holders "
            "ORDER BY added_at").fetchall()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)) if t else None
    return {"ok": True, "holders": [
        {"url": u, "name": n, "last_verified": iso(lv),
         "last_fingerprint": fp, "file_date": d, "status": st,
         "times_verified": tv} for u, n, lv, fp, d, st, tv in rows]}, 200


def _status(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        runs = conn.execute(
            "SELECT day, sealed_block, independent_holders, holding_latest, "
            "latest_sha256 FROM custody_runs ORDER BY day DESC LIMIT 14").fetchall()
        n_holders = conn.execute("SELECT COUNT(*) FROM custody_holders").fetchone()[0]
    latest_link = None
    try:
        files, _ = _sealed_files()
        if files:
            latest_link = ("https://web.archive.org/save/%s/x/archive/file?"
                           "sha256=%s" % (SITE, files[0]["sha256"]))
    except Exception:
        pass
    return {
        "ok": True, "module": "custody", "version": VERSION,
        "armed": _state["armed"], "last_run": _state["last_run"],
        "last_result": _state["last_result"],
        "independent_holders_today": runs[0][2] if runs else None,
        "registered_holders": n_holders,
        "recent_counts": [{"day": d, "sealed_block": b,
                           "check_block": ("%s/x/walk/block?index=%s" % (SITE, b))
                           if b else None,
                           "independent_holders": i, "holding_latest_file": h,
                           "latest_file": s} for d, b, i, h, s in runs],
        "become_a_holder": {
            "one_tap": latest_link,
            "register_your_own_copy": BASE + "offer?url=https://your.site/sebbi.json&name=You",
            "keep_it_automatically": BASE + "keeper"},
        "rule": "Counted only if byte-for-byte a sealed file, and only if held "
                "somewhere other than sebbi.pro. Each day's count is sealed.",
    }, 200


KEEPER = r'''#!/usr/bin/env python3
"""sebbi.pro keeper - fetch, verify and keep each day's self-proving file.

Run daily (for example from cron). Standard library only.
    python3 keeper.py /path/to/public/folder
Keeps every day's file that PASSES its own built-in checks, plus latest.json.
Serve that folder publicly, then register your latest.json once at:
    https://sebbi.pro/x/custody/offer?url=https://YOUR.SITE/latest.json&name=YOU
"""
import json, os, subprocess, sys, tempfile, urllib.request

out = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out, exist_ok=True)
ua = {"User-Agent": "sebbi-keeper/1.0"}
latest = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://sebbi.pro/x/archive/latest", headers=ua), timeout=60))
url = latest["file"]
raw = urllib.request.urlopen(urllib.request.Request(url, headers=ua),
                             timeout=300).read()
fd, tmp = tempfile.mkstemp(suffix=".json")
os.write(fd, raw); os.close(fd)
check = subprocess.run([sys.executable, "-c",
    "import json,sys;exec(json.load(open(sys.argv[1]))['verifier_py'])", tmp],
    capture_output=True, text=True)
print(check.stdout)
if check.returncode != 0:
    os.remove(tmp)
    sys.exit("Not kept: the file failed its own checks.")
name = "sebbi-chain-%s-%s.json" % (latest["date"], latest["sha256"])
os.replace(tmp, os.path.join(out, name))
with open(os.path.join(out, "latest.json"), "wb") as fh:
    fh.write(raw)
print("Kept", name, "and latest.json in", out)
'''


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "holders":
            return _holders(ctx)
        if action == "offer":
            return _offer(data, ctx)
        if action == "keeper":
            return {"ok": True, "keeper_py": KEEPER,
                    "how": "Save keeper_py as keeper.py, run it daily with a "
                           "folder you serve publicly, then register that "
                           "folder's latest.json once."}, 200
        if action == "spec":
            return {"module": "custody", "version": VERSION,
                    "counts": "independent holders whose copy is byte-for-byte "
                              "a sealed archive file",
                    "sealed": "each day's count, with every holder and "
                              "fingerprint, is sealed into the chain",
                    "routes": {"status": BASE + "status",
                               "holders": BASE + "holders",
                               "offer": BASE + "offer?url=<https address>&name=<name>",
                               "keeper": BASE + "keeper"}}, 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            with _run_lock:
                return _run(ctx, force=True), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET")}, 404
    except Exception as exc:
        return {"ok": False, "error": "custody_failed",
                "detail": str(exc)[:200]}, 500

```


## `modules/declare.py`

345 lines, 13493 bytes

```python
"""
Declaration notary - /x/declare/<action>

THE IDEA
--------
An operator uploads their own file saying what must always be true of their
decisions. It is sealed, versioned, and published. Every record is then tested
against it, and every violation is sealed.

WHY THIS ISN'T CIRCULAR
-----------------------
The obvious objection: if they write their own rules AND supply their own
data, checking one against the other proves nothing. They could declare
nothing and pass.

Two things stop that.

1. THE RULES COME FIRST. A declaration is sealed before the records it judges.
   You cannot write the rule after seeing the outcome, because the chain shows
   which came first. Retrofitting a standard to a result is exactly what this
   makes impossible.

2. YOU CANNOT QUIETLY WEAKEN IT. Every version is kept and sealed. If you
   published a strict rule in March and a loose one in September, both are
   permanent and the change is dated. Nobody can pretend the strict one never
   existed. Weakening your own standard becomes a visible act.

So the file does not prove you are honest. It converts your claims into
something that can be tested, and takes away your ability to move the goalposts
afterwards. An auditor reads the declaration, reads the violations, and reads
the version history. All three are sealed.

RULE FORMAT
-----------
    {"rules": [
      {"id": "no-silent-high-value",
       "describe": "Payments over 10000 are never auto-allowed",
       "when":    {"field": "amount",   "op": ">",  "value": 10000},
       "require": {"field": "decision", "op": "in", "value": ["CHALLENGE","BLOCK"]}}
    ]}

    ops: == != > >= < <= in not_in exists

HONEST LIMITS
-------------
- Weak rules prove weak things. A declaration that requires nothing passes
  everything. Publish it and let people judge the rules themselves.
- This tests what was sealed. A decision never recorded cannot violate a rule
  - gapless receipts are what cover that gap, not this.
- The operator still supplies the data. This is not an external audit. It is a
  published standard, sealed before the evidence, that they can be held to.

    POST /x/declare/publish     declaration file - sealed and versioned
    GET  /x/declare/current     the live declaration
    GET  /x/declare/history     every version ever published
    POST /x/declare/check       test sealed records against it, seal the result
    GET  /x/declare/violations  what failed, and when
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.0"
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "exists"}
MAX_RULES = 100

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declarations(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,version INTEGER,body TEXT,sha256 TEXT,published REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declare_checks(check_id TEXT PRIMARY KEY,api_key TEXT,decl_version INTEGER,ran REAL,tested INTEGER,passed INTEGER,violated INTEGER,detail TEXT,audit_hash TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dec_key ON declarations(api_key,version)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, ref, action, detail):
    ts = time.time()
    ev = {"user_id": "dec:" + ref, "action": "declare_" + action, "amount": 0,
          "country": "UK", "device_id": "declare", "anomaly": 0, "device_risk": 0}
    res = {"decision": "DECLARATION_SEALED", "score": 0, "declare_action": action,
           "declare_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _validate(body):
    if not isinstance(body, dict):
        return "declaration must be an object"
    rules = body.get("rules")
    if not isinstance(rules, list) or not rules:
        return "declaration needs a non-empty rules list"
    if len(rules) > MAX_RULES:
        return "too many rules (max " + str(MAX_RULES) + ")"
    seen = set()
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            return "rule " + str(i) + " is not an object"
        rid = str(r.get("id", "")).strip()
        if not rid:
            return "rule " + str(i) + " has no id"
        if rid in seen:
            return "duplicate rule id: " + rid
        seen.add(rid)
        req = r.get("require")
        if not isinstance(req, dict) or not req.get("field"):
            return "rule " + rid + " has no require.field"
        for part in ("when", "require"):
            c = r.get(part)
            if c is None:
                continue
            if not isinstance(c, dict):
                return "rule " + rid + ": " + part + " must be an object"
            if c.get("op", "==") not in OPS:
                return "rule " + rid + ": unknown op " + str(c.get("op"))
    return None


def _get(record, field):
    cur = record
    for part in str(field).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _test(cond, record):
    if not cond:
        return True
    val = _get(record, cond["field"])
    op = cond.get("op", "==")
    want = cond.get("value")
    if op == "exists":
        return (val is not None) == bool(want if want is not None else True)
    if val is None:
        return False
    try:
        if op == "==":
            return str(val).strip().lower() == str(want).strip().lower()
        if op == "!=":
            return str(val).strip().lower() != str(want).strip().lower()
        if op == "in":
            return str(val).strip().lower() in [str(x).strip().lower() for x in want]
        if op == "not_in":
            return str(val).strip().lower() not in [str(x).strip().lower() for x in want]
        v, w = float(val), float(want)
        if op == ">":
            return v > w
        if op == ">=":
            return v >= w
        if op == "<":
            return v < w
        if op == "<=":
            return v <= w
    except Exception:
        return False
    return False


def _current(ctx, api_key):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT version,body,sha256,published,audit_hash FROM declarations WHERE api_key=? ORDER BY version DESC LIMIT 1", (api_key,)).fetchone()


def _publish(ctx, api_key, data):
    body = data.get("declaration")
    if body is None:
        body = {k: v for k, v in data.items() if k != "declaration"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"error": "declaration_not_json"}, 400
    err = _validate(body)
    if err:
        return {"error": "invalid_declaration", "detail": err}, 400

    prev = _current(ctx, api_key)
    ver = (prev[0] + 1) if prev else 1
    sha = _sha(body)
    if prev and prev[2] == sha:
        return {"error": "unchanged",
                "message": "Identical to version " + str(prev[0]) + ". Nothing to publish."}, 400

    ref = "V" + str(ver)
    ids = [str(r.get("id")) for r in body["rules"]]
    detail = ("version=" + str(ver) + ";sha256=" + sha + ";rules=" + str(len(ids)) +
              ";ids=" + ",".join(ids[:40]) +
              (";replaces=" + prev[2] if prev else ";first_declaration=true"))
    h, idx, seq, ts = _seal_event(ctx, api_key, ref, "published", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO declarations(api_key,version,body,sha256,published,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
                            (api_key, ver, json.dumps(body), sha, ts, h, idx))
        ctx["conn"].commit()

    out = {"version": ver, "sha256": sha, "rules": len(ids), "rule_ids": ids,
           "published": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "Sealed. Every record from this point is judged against it, and this version cannot be removed."}
    if prev:
        out["replaces_version"] = prev[0]
        out["warning"] = "Version " + str(prev[0]) + " remains sealed and readable. Changes to your own standard are permanent and dated."
    return out, 200


def _current_view(ctx, api_key):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration",
                "message": "Nothing published yet."}, 404
    return {"version": row[0], "declaration": json.loads(row[1]),
            "sha256": row[2], "published": _iso(row[3]),
            "sealed": row[4]}, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT version,sha256,published,audit_hash,body FROM declarations WHERE api_key=? ORDER BY version ASC", (api_key,)).fetchall()
    if not rows:
        return {"count": 0, "versions": []}, 200
    out = []
    for v, sha, ts, ah, body in rows:
        try:
            n = len(json.loads(body).get("rules", []))
        except Exception:
            n = None
        out.append({"version": v, "sha256": sha, "published": _iso(ts),
                    "sealed": ah, "rules": n})
    return {"count": len(out), "versions": out,
            "note": "Every version ever published. Loosening a standard is visible here permanently."}, 200


def _check(ctx, api_key, data):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration"}, 404
    ver, body = row[0], json.loads(row[1])
    rules = body["rules"]

    try:
        limit = min(int(data.get("limit", 500)), 5000)
    except Exception:
        limit = 500

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT id,user_id,event_json,result_json,ts FROM audit_log WHERE api_key=? AND ts>=? ORDER BY id DESC LIMIT ?", (api_key, row[3], limit)).fetchall()

    violations = []
    tested = 0
    for bid, uid, ev_json, res_json, bts in recs:
        try:
            rec = {}
            rec.update(json.loads(ev_json))
            rec.update(json.loads(res_json))
        except Exception:
            continue
        if rec.get("decision", "").endswith("_SEALED"):
            continue
        tested += 1
        for r in rules:
            if not _test(r.get("when"), rec):
                continue
            if not _test(r.get("require"), rec):
                violations.append({"block_index": bid, "record_id": uid,
                                   "rule": r.get("id"),
                                   "describe": r.get("describe"),
                                   "at": _iso(bts)})

    ts = time.time()
    cid = "CHK-" + _sha(str(ts) + api_key)[:8].upper()
    detail = ("decl_version=" + str(ver) + ";tested=" + str(tested) +
              ";violated=" + str(len(violations)) +
              ";rules=" + ",".join(sorted({v["rule"] for v in violations})[:20]))
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "checked", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO declare_checks(check_id,api_key,decl_version,ran,tested,passed,violated,detail,audit_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                            (cid, api_key, ver, ts, tested, tested - len({v["block_index"] for v in violations}), len(violations), json.dumps(violations[:200]), h))
        ctx["conn"].commit()

    out = {"check_id": cid, "declaration_version": ver, "records_tested": tested,
           "violations": len(violations), "ran_at": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "note": "Result sealed whichever way it went."}
    if violations:
        out["failed_rules"] = sorted({v["rule"] for v in violations})
        out["detail"] = violations[:20]
        out["flag"] = str(len(violations)) + " record(s) violate your own published rules"
    return out, 200


def _violations(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT check_id,decl_version,ran,tested,violated,detail FROM declare_checks WHERE api_key=? ORDER BY ran DESC LIMIT 50", (api_key,)).fetchall()
    if not rows:
        return {"checks": 0, "note": "No checks run yet."}, 200
    latest = rows[0]
    try:
        detail = json.loads(latest[5])
    except Exception:
        detail = []
    return {"checks": len(rows),
            "latest": {"check_id": latest[0], "declaration_version": latest[1],
                       "ran": _iso(latest[2]), "tested": latest[3],
                       "violations": latest[4], "detail": detail[:50]},
            "history": [{"check_id": r[0], "ran": _iso(r[2]), "tested": r[3],
                         "violations": r[4]} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "publish":
            return _publish(ctx, api_key, data)
        if action == "check":
            return _check(ctx, api_key, data)
    else:
        if action == "current":
            return _current_view(ctx, api_key)
        if action == "history":
            return _history(ctx, api_key)
        if action == "violations":
            return _violations(ctx, api_key)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/demo.py`

358 lines, 15159 bytes

```python
"""
Public proving ground - /x/demo/<action>

WHY THIS EXISTS
---------------
Every page on this platform says "check it, don't trust it" and then asks for
an email address before anyone can check anything. That is the same bargain
every other vendor offers, dressed in better language.

This removes the bargain. No key, no account, no email. A visitor sends a
scenario, gets a real verdict from the live engine, and it is sealed into the
production chain - the same chain, the same sequence, covered by the same
external anchor. They get the block index back and can verify it themselves at
a public endpoint that has never heard of them.

The demonstration is not a simulation of the product. It IS the product, run
once, by a stranger, for free.

WHAT IS DELIBERATELY REAL
-------------------------
  - the scoring is the engine's own arithmetic, not a mock
  - the seal is a genuine block in the live chain
  - the counterfactual is computed by inverting the real function
  - the review flow really does withhold the verdict until commitment
  - the dwell time is really measured and really sealed

WHAT IS DELIBERATELY NOT REAL
-----------------------------
  - demo events do not touch any customer's trust history; user ids are
    namespaced to demo: and scored from a neutral starting trust
  - nothing about a visitor is recorded beyond what they typed

ABUSE
-----
Public routes are rate limited per client by the router. A visitor cannot
flood the chain, and the cost of a demo block is a few hundred bytes.

    POST /x/demo/govern   scenario -> verdict, seal, counterfactual
    POST /x/demo/review   open a review case, verdict withheld
    POST /x/demo/commit   commit a verdict, then see what the machine said
    GET  /x/demo/stats    how many people have tried it
"""

import json, math, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"

# No key required for any of these - that is the entire point.
PUBLIC = {("POST", "govern"), ("POST", "review"), ("POST", "commit"),
          ("GET", "stats"), ("GET", "")}

DEMO_KEY = "public_demo"
LN_CAP = math.log1p(10000)
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK", "FI", "IE", "NZ"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_cases(case_id TEXT PRIMARY KEY,opened REAL,material TEXT,machine_verdict TEXT,score REAL,committed REAL,human_verdict TEXT,dwell REAL)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_stats(k TEXT PRIMARY KEY,v INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _bump(ctx, k):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_stats(k,v) VALUES(?,1) ON CONFLICT(k) DO UPDATE SET v=v+1", (k,))
        ctx["conn"].commit()


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _signals(data):
    country = str(data.get("country", "UK")).strip().upper()[:4] or "UK"
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, min(_f(data, "v60"), 10000)),
        "v5m": max(0.0, min(_f(data, "v5m"), 10000)),
        "v1h": max(0.0, min(_f(data, "v1h"), 100000)),
        "amount": max(0.0, min(_f(data, "amount"), 10000000)),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country": country,
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": country not in SAFE,
    }


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _reasons(s):
    r = []
    if s["trust"] < 0.4:
        r.append("low_trust")
    if s["v60"] > 10:
        r.append("velocity_spike")
    if s["amount"] > 500:
        r.append("high_amount")
    if s["device_risk"] > 0.5:
        r.append("risky_device")
    if s["anomaly"] > 0.5:
        r.append("behaviour_anomaly")
    if s["country_shift"]:
        r.append("country_shift")
    if s["unsafe_country"]:
        r.append("unsafe_country")
    return r


def _verdict(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def _counterfactual(s, score, verdict):
    """Exact inversion. Returns the cheapest single change, or None."""
    if verdict == "ALLOW":
        return None, "Already the most permissive verdict."
    ceiling = 0.70 if verdict == "BLOCK" else 0.35
    target = "CHALLENGE" if verdict == "BLOCK" else "ALLOW"
    needed = score - ceiling + 0.0001

    contribs = [
        ("trust", (1 - s["trust"]) * 0.30),
        ("amount", min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15),
        ("v60", min(s["v60"] / 20.0, 1) * 0.15),
        ("v5m", min(s["v5m"] / 50.0, 1) * 0.10),
        ("v1h", min(s["v1h"] / 200.0, 1) * 0.10),
        ("device_risk", s["device_risk"] * 0.10),
        ("anomaly", s["anomaly"] * 0.10),
        ("country_shift", 0.10 if s["country_shift"] else 0.0),
        ("unsafe_country", 0.10 if s["unsafe_country"] else 0.0),
    ]
    contribs.sort(key=lambda kv: -kv[1])

    for name, c in contribs:
        if c <= 0 or c < needed:
            continue
        t = c - needed
        if name == "trust":
            v = 1 - (t / 0.30)
            if v <= 1.0:
                return {"factor": "trust", "required": round(_clamp(v), 3),
                        "was": round(s["trust"], 3)}, ("a trust score of "
                        + str(round(_clamp(v), 3)) + " instead of "
                        + str(round(s["trust"], 3)) + " would have made this "
                        + target)
        if name == "amount":
            v = math.expm1((t / 0.15) * LN_CAP)
            return {"factor": "amount", "required": round(v, 2),
                    "was": round(s["amount"], 2)}, ("an amount of "
                    + str(round(v, 2)) + " instead of " + str(round(s["amount"], 2))
                    + " would have made this " + target)
        if name in ("v60", "v5m", "v1h"):
            cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[name]
            v = (t / w) * cap
            lbl = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[name]
            return {"factor": name, "required": int(v), "was": int(s[name])}, (
                "a " + lbl + " velocity of " + str(int(v)) + " instead of "
                + str(int(s[name])) + " would have made this " + target)
        if name in ("device_risk", "anomaly"):
            v = t / 0.10
            lbl = "device risk" if name == "device_risk" else "behavioural anomaly"
            return {"factor": name, "required": round(_clamp(v), 3), "was": round(s[name], 3)}, (
                "a " + lbl + " of " + str(round(_clamp(v), 3)) + " instead of "
                + str(round(s[name], 3)) + " would have made this " + target)
        if name in ("country_shift", "unsafe_country"):
            lbl = ("no country change from the previous event" if name == "country_shift"
                   else "an event from a jurisdiction on the safe list")
            return {"factor": name, "required": 0, "was": 1}, (
                lbl + " would have made this " + target)
    return None, ("no single factor, changed alone, would have reached "
                  + target + " - several drove this together")


def _govern(ctx, data):
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    reasons = _reasons(s)
    cf, cf_text = _counterfactual(s, score, verdict)

    ts = time.time()
    uid = "demo:" + secrets.token_hex(3)
    ev = {"user_id": uid, "action": str(data.get("action", "payment"))[:40],
          "amount": s["amount"], "country": s["country"],
          "device_id": "demo", "anomaly": s["anomaly"],
          "device_risk": s["device_risk"]}
    res = {"decision": verdict, "score": score, "reasons": reasons,
           "demo": True, "demo_version": VERSION, "timestamp": ts,
           "signals": {k: s[k] for k in ("trust", "v60", "v5m", "v1h",
                                          "country_shift", "unsafe_country")},
           "note": "public demonstration - sealed into the live chain like any other decision"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)
    _bump(ctx, "govern")

    return {"decision": verdict, "score": score, "reasons": reasons,
            "sealed_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "counterfactual": cf,
            "counterfactual_statement": cf_text,
            "verify": {
                "this_block": "/api/inclusion?hash=" + h,
                "whole_chain": "/api/verify-chain",
                "external_anchor": "/api/anchor-status"},
            "what_just_happened": [
                "Your scenario was scored by the live engine, not a simulation.",
                "The verdict was sealed into the production chain as block " + str(idx) + ".",
                "That block is now covered by the next external timestamp.",
                "Nothing about you was recorded. No account, no email, no key.",
                "Verify any of it at the links above - they have never heard of you."]}, 200


def _review(ctx, data):
    """Open a review case. The verdict is computed and sealed - and withheld."""
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    cid = "DEMO-" + secrets.token_hex(4).upper()
    ts = time.time()
    material = {"action": str(data.get("action", "payment"))[:40],
                "amount": s["amount"], "country": s["country"],
                "60_second_velocity": int(s["v60"]),
                "5_minute_velocity": int(s["v5m"]),
                "device_risk": s["device_risk"],
                "behavioural_anomaly": s["anomaly"],
                "country_changed": s["country_shift"],
                "trust_history": round(s["trust"], 3)}
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_cases(case_id,opened,material,machine_verdict,score,committed,human_verdict,dwell) VALUES(?,?,?,?,?,NULL,NULL,NULL)",
                            (cid, ts, json.dumps(material), verdict, score))
        ctx["conn"].commit()
    _bump(ctx, "review_opened")
    return {"case_id": cid, "opened": _iso(ts), "material": material,
            "machine_verdict": "withheld until you commit",
            "your_options": ["allow", "challenge", "block"],
            "instruction": "Decide for yourself, then POST your verdict to /x/demo/commit with this case_id. The clock is running and your answer is sealed before ours is shown."}, 200


def _commit(ctx, data):
    cid = str(data.get("case_id", "")).strip().upper()
    hv = str(data.get("verdict", "")).strip().upper()
    if hv not in ("ALLOW", "CHALLENGE", "BLOCK"):
        return {"error": "verdict_required", "allowed": ["allow", "challenge", "block"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT opened,material,machine_verdict,score,committed FROM demo_cases WHERE case_id=?", (cid,)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_committed",
                "message": "You commit once. That is the point of it."}, 400

    ts = time.time()
    dwell = round(ts - row[0], 2)
    agreed = (hv == row[2])

    ev = {"user_id": "demo:" + cid, "action": "demo_oversight_commit",
          "amount": 0, "country": "UK", "device_id": "demo",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "DEMO_OVERSIGHT_SEALED", "score": 0, "demo": True,
           "timestamp": ts, "human_verdict": hv, "dwell_seconds": dwell,
           "detail": "human verdict sealed before the machine verdict was revealed"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE demo_cases SET committed=?,human_verdict=?,dwell=? WHERE case_id=?",
                            (ts, hv, dwell, cid))
        ctx["conn"].commit()
    _bump(ctx, "review_committed")

    out = {"case_id": cid, "your_verdict": hv,
           "machine_verdict": row[2], "machine_score": row[3],
           "agreed": agreed, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "what_just_happened": [
               "Your verdict was sealed as block " + str(idx) + " BEFORE this response revealed ours.",
               "The chain fixes that order permanently and it cannot be reversed.",
               "Your dwell time of " + str(dwell) + "s is part of the record.",
               "That is the difference between a reviewer who decided and one who agreed."]}
    if dwell < 2:
        out["flag"] = ("committed in " + str(dwell) + " seconds - on a real system that would sit "
                       "in your record permanently, and a pattern of it would be visible to an auditor")
    if agreed:
        out["note"] = "You agreed with the engine - but the chain shows you did so without having seen it."
    else:
        out["note"] = "You diverged from the engine. On a real system that is evidence of independent judgement."
    return out, 200


def _stats(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT k,v FROM demo_stats").fetchall()
        cases = ctx["conn"].execute("SELECT COUNT(*),AVG(dwell) FROM demo_cases WHERE committed IS NOT NULL").fetchone()
        fast = ctx["conn"].execute("SELECT COUNT(*) FROM demo_cases WHERE dwell IS NOT NULL AND dwell<2").fetchone()
    d = {k: v for k, v in rows}
    out = {"decisions_run": d.get("govern", 0),
           "review_cases_opened": d.get("review_opened", 0),
           "review_cases_committed": d.get("review_committed", 0)}
    if cases and cases[0]:
        out["median_dwell_seconds"] = round(cases[1] or 0, 2)
        out["committed_under_2_seconds"] = fast[0] if fast else 0
        out["note"] = ("Visitors who committed in under two seconds did not read the case. "
                       "On a real deployment that is exactly what the record would show.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "govern":
            return _govern(ctx, data)
        if action == "review":
            return _review(ctx, data)
        if action == "commit":
            return _commit(ctx, data)
    else:
        if action in ("", "stats"):
            return _stats(ctx)
    return {"error": "unknown_action", "action": action,
            "available": ["POST govern", "POST review", "POST commit", "GET stats"]}, 404

```


## `modules/disclosure.py`

201 lines, 7648 bytes

```python
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

```


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```
