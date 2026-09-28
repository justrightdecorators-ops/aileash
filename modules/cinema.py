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
    "msxng73/Bz9c6hOHigAA"
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
