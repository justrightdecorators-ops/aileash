# Codebase — part 4 of 45

Contains:
- `modules/cinema.py`
- `modules/cinemafeed.py`
- `modules/codebase.py`
- `modules/complete.py`


## `modules/cinema.py`

695 lines, 38980 bytes

```python
"""
modules/cinema.py  v3.1.0
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

VERSION = "3.1.0"
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


## `modules/complete.py`

862 lines, 37023 bytes

```python
#!/usr/bin/env python3
"""
modules/complete.py  -  proving what ISN'T there
================================================

THE PROBLEM NOBODY IN THIS MARKET ANSWERS
-----------------------------------------
A hash chain proves inclusion. It cannot prove exclusion.

So when a firm hands an auditor four hundred decisions, nothing on earth
shows it wasn't six hundred. Every audit ever conducted runs on the
assumption that the sample handed over is the whole set, and that
assumption has never once been provable. The chain says "these four
hundred happened". It says nothing about the two hundred that also
happened and quietly didn't make the export.

Three questions follow, and none of them can be answered by an
append-only log on its own:

  1. Is this the complete set, or the flattering subset?
  2. Do you hold a record about me? Prove the NO.
  3. You erased my data - prove it, without holding my data to prove it.

Question 3 is the contradiction sitting inside every
blockchain-for-compliance product, this one included. Append-only and
right-to-erasure do not obviously coexist. Most vendors disclaim it.

WHAT THIS DOES
--------------
At the end of each period we take every leaf sealed in that period, SORT
them, build a Merkle tree over the sorted list, and seal the root plus the
exact count into the chain. That root is then anchored externally like
everything else.

Sorting is the whole trick. In an unsorted tree you can only prove a leaf
is present. In a sorted one you can prove a leaf is absent, by showing the
two leaves either side of where it would have sorted and proving they are
ADJACENT in the tree. Nothing can sit between two adjacent leaves. The
record provably does not exist.

  INCLUSION     standard Merkle path. This receipt is in the period.
  ABSENCE       the two neighbours, and proof they are adjacent. No record
                for that key exists in the period, and we cannot pretend
                otherwise after the fact.
  COMPLETENESS  the count was sealed BEFORE anyone asked for anything.
                Hand over four hundred against a root that says six
                hundred and the arithmetic exposes it.

ERASURE
-------
Erasing a record deletes the payload and leaves the leaf as a tombstone.
We can then prove: a record existed, it was erased, and when - while
holding none of the erased content. The subject gets a proof of erasure
rather than a promise of one, and the chain does not have to be broken to
give it to them.

WHY COMMITMENTS ARE FROZEN
--------------------------
A commitment is only worth anything if it cannot be recomputed to suit
later circumstances. So:

  - Only CLOSED periods can be committed. You cannot commit a period that
    is still running, because more leaves could still arrive.
  - The sorted leaf list is STORED at commit time, not recomputed on
    demand. If rows are erased next year, the proofs from this year still
    verify against the root that was sealed and anchored this year.
  - A period can only be committed once. A second attempt returns the
    existing commitment rather than a new root.

WHY COMMITTING IS AUTOMATIC
---------------------------
It was not, and that was a real hole rather than an oversight worth
defending. Committing was a keyed POST somebody had to remember to make,
which meant that for the first week of publication this module had zero
committed periods while the discovery document advertised completeness and
absence as publicly demonstrable checks. Both were true claims about code
that existed and false claims about anything an outsider could run.

A control that depends on the operator remembering to run it is the exact
control an auditor should distrust, so the schedule now runs itself. Once
a month closes, the first request to reach this module commits it.

Two honest limits on that:

  - The automatic commitment is DEPLOYMENT-WIDE. It covers every record
    sealed in the period regardless of which key sealed it, because that
    is what a public completeness claim has to mean. Per-tenant
    commitments are still made by POSTing /x/complete/commit with that
    tenant's key, and the two live side by side.
  - A period committed late is committed at the date it was actually
    committed, and /x/complete/periods reports the gap in days. Backfilled
    history still proves the count was fixed before any export was asked
    for. It does not prove the count was fixed when the period closed, and
    nothing published here will claim it does.

HONEST LIMITS
-------------
  - This proves completeness of what was SEALED. A decision that never
    reached the chain at all is outside anything we can see. Garbage in
    still applies; what changes is that the operator can no longer choose
    which of the sealed records to show.
  - Absence proofs are scoped to a period. "No record of you, ever"
    means checking every period, which is why the period list is public.
  - The tree is built over key material only. It never contains payloads,
    so a leaf reveals whether something exists, not what it said.
  - Adjacent-leaf absence proofs disclose the two neighbouring keys. If
    keys are themselves sensitive, hash them before they become leaves -
    the proof still works, and we hold nothing legible.

    POST /x/complete/commit    close and seal a period      (keyed)
    POST /x/complete/erase     tombstone a leaf             (keyed)
    GET  /x/complete/periods   every sealed period          (public)
    GET  /x/complete/root      root, count, block index     (public)
    GET  /x/complete/prove     inclusion or absence proof   (public)
    POST /x/complete/verify    check a proof we handed out  (public)
    GET  /x/complete/spec      the exact hashing rules      (public)
"""

import hashlib
import json
import re
import time
from datetime import datetime, timezone, timedelta

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# A third party must be able to check completeness without an account. A
# completeness claim you have to hold credentials to verify is not a
# completeness claim, it is a marketing line.
PUBLIC = {("GET", "periods"), ("GET", "root"), ("GET", "prove"),
          ("GET", "spec"), ("POST", "verify")}

# Domain separation. Leaf and node hashes must never be confusable, or an
# attacker can present an internal node as though it were a leaf.
LEAF_PREFIX = b"AILEASH-LEAF-v1:"
NODE_PREFIX = b"AILEASH-NODE-v1:"

MAX_LEAVES = 200000

# ---- automatic commitment --------------------------------------------
AUTO_COMMIT = True          # set False to go back to committing by hand
AUTO_KINDS = ("receipts", "subjects")
AUTO_INTERVAL = 600         # seconds between sweeps, not per request
AUTO_MAX_MONTHS = 24        # how far back a first run will backfill

# The deployment-wide commitment is stored under an empty key, which is
# also what an unauthenticated read looks for. Not a magic value with
# privileges - the absence of a key, meaning "everything sealed here".
AUTO_KEY = ""

_last_auto = [0.0]
_auto_log = []              # recent sweep outcomes, surfaced on /periods

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS complete_commit("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,period TEXT,kind TEXT,"
                  "root TEXT,leaf_count INTEGER,period_start REAL,period_end REAL,"
                  "committed REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cmp_unique "
                  "ON complete_commit(api_key,period,kind)")
        c.execute("CREATE TABLE IF NOT EXISTS complete_leaf("
                  "commit_id INTEGER,idx INTEGER,leaf TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_leaf "
                  "ON complete_leaf(commit_id,idx)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_leaf_val "
                  "ON complete_leaf(commit_id,leaf)")
        c.execute("CREATE TABLE IF NOT EXISTS complete_tomb("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,leaf TEXT,"
                  "reason TEXT,erased REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cmp_tomb ON complete_tomb(api_key,leaf)")
        c.commit()
    _ready = True


def _audit_columns(ctx):
    """What the audit_log actually looks like on this deployment.

    Read rather than assumed - the schema has moved before and will again,
    and a completeness module that guesses column names is worse than none.
    """
    have = []
    try:
        with ctx["lock"]:
            for row in ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall():
                have.append(row[1])
    except Exception:
        pass
    return have


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# periods
# ----------------------------------------------------------------------

def _period_bounds(period):
    """Turn a period label into [start, end) as epoch seconds.

    Accepts  2026, 2026-08, 2026-08-02, 2026-Q3.
    Returns (start, end, None) or (None, None, why).
    """
    period = (period or "").strip().upper()

    def _utc(y, m, d):
        return datetime(y, m, d, tzinfo=timezone.utc).timestamp()

    try:
        m = re.match(r"^(\d{4})$", period)
        if m:
            y = int(m.group(1))
            return _utc(y, 1, 1), _utc(y + 1, 1, 1), None

        m = re.match(r"^(\d{4})-Q([1-4])$", period)
        if m:
            y, q = int(m.group(1)), int(m.group(2))
            start_month = (q - 1) * 3 + 1
            end_month = start_month + 3
            if end_month > 12:
                return _utc(y, start_month, 1), _utc(y + 1, 1, 1), None
            return _utc(y, start_month, 1), _utc(y, end_month, 1), None

        m = re.match(r"^(\d{4})-(\d{2})$", period)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            if not 1 <= mo <= 12:
                return None, None, "month out of range"
            if mo == 12:
                return _utc(y, 12, 1), _utc(y + 1, 1, 1), None
            return _utc(y, mo, 1), _utc(y, mo + 1, 1), None

        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", period)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            start = datetime(y, mo, d, tzinfo=timezone.utc)
            return start.timestamp(), (start + timedelta(days=1)).timestamp(), None
    except ValueError as exc:
        return None, None, "unreadable period (%s)" % exc

    return None, None, "period must be YYYY, YYYY-MM, YYYY-MM-DD or YYYY-Qn"


# ----------------------------------------------------------------------
# the tree
# ----------------------------------------------------------------------

def _leaf_hash(value):
    return hashlib.sha256(LEAF_PREFIX + value.encode("utf-8")).hexdigest()


def _node_hash(left, right):
    return hashlib.sha256(NODE_PREFIX + left.encode() + right.encode()).hexdigest()


def _build(leaves):
    """Build the tree over already-sorted leaf VALUES.

    Returns (root, levels). levels[0] is the leaf-hash level. An odd node
    at any level is promoted unchanged to the next - it is never paired
    with itself, which is the classic duplication weakness.
    """
    if not leaves:
        return hashlib.sha256(LEAF_PREFIX + b"EMPTY").hexdigest(), []

    level = [_leaf_hash(v) for v in leaves]
    levels = [level]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(_node_hash(level[i], level[i + 1]))
        if len(level) % 2 == 1:
            nxt.append(level[-1])
        levels.append(nxt)
        level = nxt
    return level[0], levels


def _path(levels, index):
    """Sibling path for a leaf index. Each step says which side to hash on."""
    proof = []
    idx = index
    for level in levels[:-1]:
        if idx % 2 == 0:
            sibling = idx + 1
            if sibling < len(level):
                proof.append({"side": "right", "hash": level[sibling]})
            # No sibling means this node was promoted - nothing to hash.
        else:
            proof.append({"side": "left", "hash": level[idx - 1]})
        idx //= 2
    return proof


def _replay(leaf_value, proof):
    """Recompute a root from a leaf and its path. This is what a verifier
    runs, and it is deliberately five lines so anyone can reimplement it."""
    current = _leaf_hash(leaf_value)
    for step in proof:
        if step.get("side") == "left":
            current = _node_hash(step["hash"], current)
        else:
            current = _node_hash(current, step["hash"])
    return current


# ----------------------------------------------------------------------
# reading leaves out of the audit log
# ----------------------------------------------------------------------

def _collect(ctx, api_key, start, end, kind, columns):
    """Every distinct leaf sealed in [start, end).

    kind = receipts  -> the audit hash of each sealed decision
    kind = subjects  -> the distinct subject each decision was about, so
                        "do you hold anything on me" becomes answerable

    A falsy api_key means no scoping: every record sealed on this
    deployment in the window. That is what the automatic commitment uses,
    and what a public completeness claim has to cover.
    """
    if "ts" not in columns:
        return None, "audit_log has no ts column on this deployment"

    if kind == "receipts":
        if "audit_hash" not in columns:
            return None, "audit_log has no audit_hash column"
        field = "audit_hash"
    else:
        field = None
        for candidate in ("user_id", "subject", "subject_id", "customer_id"):
            if candidate in columns:
                field = candidate
                break
        if not field:
            return None, "no subject column on this deployment - receipts only"

    scoped = "api_key" in columns and api_key
    sql = "SELECT DISTINCT %s FROM audit_log WHERE ts>=? AND ts<?" % field
    args = [start, end]
    if scoped:
        sql += " AND api_key=?"
        args.append(api_key)

    with ctx["lock"]:
        rows = ctx["conn"].execute(sql, tuple(args)).fetchall()

    values = sorted({str(r[0]) for r in rows if r[0] is not None})
    if len(values) > MAX_LEAVES:
        return None, "period holds %d leaves, above the %d cap" % (len(values), MAX_LEAVES)
    return values, None


# ----------------------------------------------------------------------
# commit
# ----------------------------------------------------------------------

def _commit(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    if kind not in ("receipts", "subjects"):
        return {"error": "bad_kind", "message": "kind is receipts or subjects"}, 400

    start, end, why = _period_bounds(period)
    if why:
        return {"error": "bad_period", "message": why}, 400

    now = time.time()
    if end > now:
        return {"error": "period_open",
                "message": "That period has not finished. Committing a live period would let "
                           "later entries change the root, which defeats the point.",
                "closes_at": _iso(end)}, 409

    with ctx["lock"]:
        existing = ctx["conn"].execute(
            "SELECT root,leaf_count,committed,audit_hash,block_index FROM complete_commit "
            "WHERE api_key=? AND period=? AND kind=?", (api_key, period, kind)).fetchone()
    if existing:
        return {"already_committed": True, "period": period, "kind": kind,
                "root": existing[0], "leaf_count": existing[1],
                "committed_at": _iso(existing[2]),
                "sealed_in_chain": existing[3], "block_index": existing[4],
                "message": "A period is committed once. Recommitting is how a commitment "
                           "stops meaning anything."}, 200

    columns = _audit_columns(ctx)
    leaves, why = _collect(ctx, api_key, start, end, kind, columns)
    if why:
        return {"error": "cannot_collect", "message": why}, 400

    root, levels = _build(leaves)

    scope = "deployment" if not api_key else "key"
    late_days = round(max(0.0, (now - end)) / 86400.0, 1)

    ev = {"user_id": "cmp:" + period, "action": "completeness_committed", "amount": 0,
          "country": "UK", "device_id": "complete", "anomaly": 0, "device_risk": 0}
    res = {"decision": "COMPLETENESS_SEALED", "score": 0, "complete_version": VERSION,
           "period": period, "kind": kind, "root": root, "leaf_count": len(leaves),
           "period_start": start, "period_end": end, "scope": scope,
           "days_after_period_end": late_days,
           "detail": "period=%s;kind=%s;scope=%s;root=%s;count=%d;late_days=%s"
                     % (period, kind, scope, root, len(leaves), late_days)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("INSERT INTO complete_commit(api_key,period,kind,root,leaf_count,"
                  "period_start,period_end,committed,audit_hash,block_index) "
                  "VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (api_key, period, kind, root, len(leaves), start, end, now,
                   audit_hash, block_index))
        commit_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.executemany("INSERT INTO complete_leaf(commit_id,idx,leaf) VALUES(?,?,?)",
                      [(commit_id, i, v) for i, v in enumerate(leaves)])
        c.commit()

    return {"period": period, "kind": kind, "root": root, "leaf_count": len(leaves),
            "period_start": _iso(start), "period_end": _iso(end),
            "committed_at": _iso(now), "sealed_in_chain": audit_hash,
            "block_index": block_index, "receipt_seq": seq,
            "scope": scope, "days_after_period_end": late_days,
            "frozen": "The sorted leaf list is stored as committed. Later erasures cannot "
                      "change what this root proved.",
            "message": "%d leaves committed. Any export from this period claiming a different "
                       "total now contradicts a sealed, externally anchored number."
                       % len(leaves)}, 200


# ----------------------------------------------------------------------
# automatic commitment
# ----------------------------------------------------------------------

def _closed_months(first_ts, now):
    """Every whole month between the first sealed record and this one.

    The current month is excluded because it is still running, which is
    the same rule a manual commit is held to.
    """
    try:
        first = datetime.fromtimestamp(first_ts, tz=timezone.utc)
        current = datetime.fromtimestamp(now, tz=timezone.utc)
    except Exception:
        return []

    labels = []
    y, m = first.year, first.month
    while (y, m) < (current.year, current.month):
        labels.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
        if len(labels) > 600:
            break
    return labels[-AUTO_MAX_MONTHS:]


def _auto_commit(ctx):
    """Commit any closed month that nobody has committed yet.

    Runs on request rather than on a thread. A sleeping container has no
    timer worth trusting, and this way the sweep happens before the answer
    that depends on it - including for the auditor whose visit to
    /x/complete/periods is what triggered it.
    """
    if not AUTO_COMMIT:
        return

    now = time.time()
    if now - _last_auto[0] < AUTO_INTERVAL:
        return
    _last_auto[0] = now

    columns = _audit_columns(ctx)
    if "ts" not in columns:
        return

    try:
        with ctx["lock"]:
            row = ctx["conn"].execute("SELECT MIN(ts) FROM audit_log").fetchone()
    except Exception:
        return
    if not row or not row[0]:
        return

    months = _closed_months(row[0], now)
    if not months:
        return

    try:
        with ctx["lock"]:
            done = {(r[0], r[1]) for r in ctx["conn"].execute(
                "SELECT period,kind FROM complete_commit WHERE api_key=?",
                (AUTO_KEY,)).fetchall()}
    except Exception:
        done = set()

    for period in months:
        for kind in AUTO_KINDS:
            if (period, kind) in done:
                continue
            try:
                body, code = _commit(ctx, AUTO_KEY, {"period": period, "kind": kind})
            except Exception as exc:
                _note_auto(period, kind, "failed: " + str(exc)[:120])
                continue
            if code == 200 and not body.get("already_committed"):
                _note_auto(period, kind, "committed %d leaves %s days after the period closed"
                           % (body.get("leaf_count", 0), body.get("days_after_period_end")))
            elif code != 200:
                # A deployment with no subject column cannot do kind=subjects.
                # That is a real limit of the deployment, recorded rather than
                # retried every ten minutes.
                _note_auto(period, kind, "skipped: " + str(body.get("message")
                                                           or body.get("error"))[:120])


def _note_auto(period, kind, outcome):
    _auto_log.append({"at": _iso(time.time()), "period": period,
                      "kind": kind, "outcome": outcome})
    del _auto_log[:-40]
    print("COMPLETE: auto %s/%s - %s" % (period, kind, outcome), flush=True)


# ----------------------------------------------------------------------
# proofs
# ----------------------------------------------------------------------

def _load(ctx, api_key, period, kind):
    with ctx["lock"]:
        if api_key:
            row = ctx["conn"].execute(
                "SELECT id,root,leaf_count,committed,audit_hash,block_index,period_start,period_end "
                "FROM complete_commit WHERE api_key=? AND period=? AND kind=?",
                (api_key, period, kind)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT id,root,leaf_count,committed,audit_hash,block_index,period_start,period_end "
                "FROM complete_commit WHERE period=? AND kind=? ORDER BY id ASC LIMIT 1",
                (period, kind)).fetchone()
        if not row:
            return None, None
        leaves = [r[0] for r in ctx["conn"].execute(
            "SELECT leaf FROM complete_leaf WHERE commit_id=? ORDER BY idx ASC",
            (row[0],)).fetchall()]
    return row, leaves


def _tombstone_for(ctx, api_key, value):
    with ctx["lock"]:
        if api_key:
            row = ctx["conn"].execute(
                "SELECT erased,reason,audit_hash,block_index FROM complete_tomb "
                "WHERE api_key=? AND leaf=? ORDER BY id ASC LIMIT 1",
                (api_key, value)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT erased,reason,audit_hash,block_index FROM complete_tomb "
                "WHERE leaf=? ORDER BY id ASC LIMIT 1", (value,)).fetchone()
    if not row:
        return None
    return {"erased_at": _iso(row[0]), "reason": row[1],
            "sealed_in_chain": row[2], "block_index": row[3],
            "note": "The payload is gone. This proves it existed and that it was erased, "
                    "without holding any of it."}


def _prove(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    value = str(data.get("value", "")).strip()
    if not period or not value:
        return {"error": "period_and_value_required",
                "message": "Both are required. Committed periods are listed at "
                           "/x/complete/periods; value is any key you want proved "
                           "present or absent.",
                "example": "/x/complete/prove?period=2026-07&value=<key>"}, 400

    row, leaves = _load(ctx, api_key, period, kind)
    if not row:
        return {"error": "not_committed", "period": period, "kind": kind,
                "message": "No sealed commitment for that period. Nothing can be proved "
                           "either way until the period is closed and committed."}, 404

    _cid, root, count, committed, chain_hash, block_index, start, end = row
    _r, levels = _build(leaves)

    base = {"period": period, "kind": kind, "value": value, "root": root,
            "leaf_count": count, "committed_at": _iso(committed),
            "period_start": _iso(start), "period_end": _iso(end),
            "sealed_in_chain": chain_hash, "block_index": block_index,
            "complete_version": VERSION,
            "verify": "/x/complete/verify, or reimplement it - the rules are at /x/complete/spec"}

    # Present?
    try:
        index = leaves.index(value)
    except ValueError:
        index = None

    if index is not None:
        base.update({
            "result": "present",
            "index": index,
            "proof": _path(levels, index),
            "what_this_proves": "This exact record is inside the sealed set for the period. "
                                "It cannot have been added afterwards.",
        })
        tomb = _tombstone_for(ctx, api_key, value)
        if tomb:
            base["erased"] = tomb
        return base, 200

    # Absent - find the neighbours it sorts between.
    lower_index = None
    upper_index = None
    for i, leaf in enumerate(leaves):
        if leaf < value:
            lower_index = i
        else:
            upper_index = i
            break

    neighbours = {}
    if lower_index is not None:
        neighbours["lower"] = {"index": lower_index, "value": leaves[lower_index],
                               "proof": _path(levels, lower_index)}
    if upper_index is not None:
        neighbours["upper"] = {"index": upper_index, "value": leaves[upper_index],
                               "proof": _path(levels, upper_index)}

    if not leaves:
        adjacency = "The period is committed and empty. Nothing was sealed in it at all."
    elif lower_index is None:
        adjacency = ("The value sorts before every leaf in the set. The first leaf is proved, "
                     "and nothing precedes index 0.")
    elif upper_index is None:
        adjacency = ("The value sorts after every leaf in the set. The last leaf is proved, "
                     "and nothing follows the final index.")
    else:
        adjacency = ("The two proved leaves are adjacent - indices %d and %d, consecutive. "
                     "Nothing can exist between two adjacent leaves of a sorted tree, so no "
                     "record for this value exists in the period."
                     % (lower_index, upper_index))

    base.update({
        "result": "absent",
        "neighbours": neighbours,
        "adjacency": adjacency,
        "what_this_proves": "No record for this value was sealed in this period. Not that we "
                            "declined to look - that it is not there, against a root fixed "
                            "before you asked.",
        "scope": "This period only. /x/complete/periods lists every committed period.",
    })
    tomb = _tombstone_for(ctx, api_key, value)
    if tomb:
        base["erased"] = tomb
        base["note"] = ("Absent from this period AND carrying an erasure record. That is the "
                        "expected shape after a valid erasure request.")
    return base, 200


def _verify(ctx, api_key, data):
    """Check a proof we handed out. Convenience only - a verifier who
    trusts us to check our own proof has not verified anything. The spec
    route exists so this can be done independently."""
    value = str(data.get("value", "")).strip()
    root = str(data.get("root", "")).strip().lower()
    proof = data.get("proof")
    if not value or not HEX64.match(root) or not isinstance(proof, list):
        return {"error": "value_root_and_proof_required"}, 400
    try:
        computed = _replay(value, proof)
    except Exception as exc:
        return {"error": "bad_proof", "message": str(exc)[:200]}, 400
    return {"valid": computed == root, "computed_root": computed, "given_root": root,
            "note": "Recomputed from the leaf upward. If these match, the leaf was in the tree "
                    "when the root was sealed."}, 200


# ----------------------------------------------------------------------
# erasure
# ----------------------------------------------------------------------

def _erase(ctx, api_key, data):
    value = str(data.get("value", "")).strip()
    reason = str(data.get("reason", "erasure request")).strip()[:200]
    if not value:
        return {"error": "value_required",
                "message": "The leaf being tombstoned - a receipt hash or a subject key."}, 400

    now = time.time()
    ev = {"user_id": "era:" + value[:32], "action": "erasure_recorded", "amount": 0,
          "country": "UK", "device_id": "complete", "anomaly": 0, "device_risk": 0}
    res = {"decision": "ERASURE_SEALED", "score": 0, "complete_version": VERSION,
           "leaf": value, "reason": reason,
           "detail": "leaf=%s;reason=%s" % (value, reason)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO complete_tomb(api_key,leaf,reason,erased,audit_hash,"
                            "block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, value, reason, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"leaf": value, "erased_at": _iso(now), "reason": reason,
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Records the erasure as a sealed event. It does not delete the "
                              "payload - your own system does that. This is the receipt that "
                              "proves you did.",
            "what_the_subject_gets": "Proof their record existed, proof it was erased, and the "
                                     "time it happened - none of which requires anyone to still "
                                     "hold the data.",
            "note": "Earlier committed roots still contain the leaf. That is correct and not a "
                    "leak: a leaf is key material, not content, and a root that changed after "
                    "the fact would prove nothing about anything."}, 200


# ----------------------------------------------------------------------
# read-only
# ----------------------------------------------------------------------

def _periods(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute(
                "SELECT period,kind,root,leaf_count,committed,block_index,period_end,api_key "
                "FROM complete_commit WHERE api_key=? ORDER BY period_start DESC",
                (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT period,kind,root,leaf_count,committed,block_index,period_end,api_key "
                "FROM complete_commit ORDER BY period_start DESC").fetchall()

    out = []
    for r in rows:
        late = None
        try:
            if r[4] and r[6]:
                late = round(max(0.0, r[4] - r[6]) / 86400.0, 1)
        except Exception:
            late = None
        out.append({"period": r[0], "kind": r[1], "root": r[2], "leaf_count": r[3],
                    "committed_at": _iso(r[4]), "block_index": r[5],
                    "scope": "deployment" if not r[7] else "key",
                    "committed_days_after_period_end": late})

    return {"count": len(out),
            "periods": out,
            "auto_commit": AUTO_COMMIT,
            "recent_auto_activity": list(reversed(_auto_log[-10:])),
            "on_lateness": "committed_days_after_period_end is published rather than hidden. A "
                           "small number means the count was fixed when the period closed. A "
                           "large one means history was backfilled later, which still proves "
                           "the count was fixed before any export was requested and proves "
                           "nothing more than that.",
            "note": "Gaps are visible on purpose. A missing period is a period nobody committed, "
                    "and that is exactly the thing an auditor should be asking about."}, 200


def _root(ctx, api_key, data):
    period = str(data.get("period", "")).strip()
    kind = str(data.get("kind", "receipts")).strip().lower()
    row, _leaves = _load(ctx, api_key, period, kind)
    if not row:
        return {"error": "not_committed", "period": period, "kind": kind,
                "committed_periods": "/x/complete/periods"}, 404
    _cid, root, count, committed, chain_hash, block_index, start, end = row
    late = None
    try:
        late = round(max(0.0, committed - end) / 86400.0, 1)
    except Exception:
        pass
    return {"period": period, "kind": kind, "root": root, "leaf_count": count,
            "period_start": _iso(start), "period_end": _iso(end),
            "committed_at": _iso(committed), "sealed_in_chain": chain_hash,
            "block_index": block_index, "committed_days_after_period_end": late,
            "what_this_is": "The number of records sealed in this period, fixed before anybody "
                            "asked for an export. Any export claiming a different total is "
                            "arguing with an externally anchored figure."}, 200


def _spec():
    return {
        "complete_version": VERSION,
        "leaf_hash": "sha256('AILEASH-LEAF-v1:' || value) as lowercase hex",
        "node_hash": "sha256('AILEASH-NODE-v1:' || left_hex || right_hex) as lowercase hex",
        "empty_root": hashlib.sha256(LEAF_PREFIX + b"EMPTY").hexdigest(),
        "ordering": "leaf VALUES sorted ascending as UTF-8 strings, duplicates removed, "
                    "before any hashing",
        "odd_nodes": "an unpaired node at any level is promoted unchanged to the next level. "
                     "It is never hashed with itself.",
        "inclusion": "recompute upward from the leaf using the sibling path. Each step gives a "
                     "side; hash the sibling on that side.",
        "absence": "verify the two neighbouring leaves independently, check their values sort "
                   "either side of the queried value, and check their indices are consecutive. "
                   "Consecutive indices in a sorted tree leave no room for anything between.",
        "completeness": "the leaf count is sealed with the root, before any export is requested",
        "schedule": "closed months are committed automatically, deployment-wide, on the first "
                    "request to reach this module after the month ends. Per-key commitments "
                    "remain a keyed POST. Lateness is published per period rather than smoothed "
                    "over.",
        "why_published": "Anyone should be able to write their own verifier and check us without "
                         "running our code or holding an account. A proof you can only check "
                         "with the prover's own tool is not a proof.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)

    # Sweep before answering, never at the cost of answering.
    try:
        _auto_commit(ctx)
    except Exception as exc:
        print("COMPLETE: auto sweep failed - " + str(exc)[:200], flush=True)

    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "periods":
            return _periods(ctx, api_key)
        if action == "root":
            return _root(ctx, api_key, data)
        if action == "prove":
            return _prove(ctx, api_key, data)

    if method == "POST":
        if action == "verify":
            return _verify(ctx, api_key, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "commit":
            return _commit(ctx, api_key, data)
        if action == "erase":
            return _erase(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "periods", "root", "prove"],
            "POST": ["verify", "commit", "erase"]}, 404

```
