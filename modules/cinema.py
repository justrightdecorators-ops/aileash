"""
modules/cinema.py  v3.0.0
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

VERSION = "3.0.0"
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
    "33x4dDBLFvPh3v8Dm1JjdJyUAAA="
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
