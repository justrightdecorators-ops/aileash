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
        where.append("(v.title LIKE ? OR v.creator LIKE ?)")
        args += [like, like]
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
