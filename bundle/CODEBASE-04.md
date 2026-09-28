# Codebase — part 4 of 43

Contains:
- `modules/cinema.py`
- `modules/cinemafeed.py`
- `modules/codebase.py`
- `modules/complete.py`


## `modules/cinema.py`

675 lines, 36785 bytes

```python
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
