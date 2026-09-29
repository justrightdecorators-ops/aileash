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
