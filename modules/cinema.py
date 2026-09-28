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
