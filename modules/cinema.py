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
    "Z4O9fwc3yc8TGYkAAA=="
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
