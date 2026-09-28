"""
modules/studio.py  v4.0.0
Monop Studio. Creators upload a video at /create and get back:

  * a teaser video saved to their phone, ready for TikTok, Instagram,
    Facebook and YouTube - the first few seconds play clear, then the picture
    blurs behind an end card with the video's link and a QR code burned into
    the pixels, so it survives any upload anywhere;
  * a short link, https://sebbi.pro/v/<id>, that opens straight onto that
    video in the 10p Wing (modules/cinema.py);
  * a channel link for their bio, https://sebbi.pro/cinema/@<name>.

Viewers watch the teaser free, then pay 10p to watch the rest. A viewer with
no credit taps Google Pay or Apple Pay once (Stripe Checkout), GBP 1 or GBP 5
lands on their phone as credit, 10p comes off and the video plays. No account.

The creator gets 70% of every paid view, less 50p a month per video which is
only ever taken from that video's own earnings - a video that earns nothing
costs nothing. Balances and payouts run on modules/credits.py (/earn), and
every paid view, payment and upload is sealed into the chain.

Routes (all served by a runtime do_GET / do_POST patch, like credits.py):
  GET  /create                       the creator page
  GET  /v/<id>                       one tap -> the video in the 10p Wing
  GET  /v/<id>/teaser                the free teaser video
  GET  /v/<id>/poster.jpg            the still
  GET  /v/<id>/full?viewer=&t=       the full video, for viewers who paid
  POST /v/api/join | signin | new | chunk | finish | mine | delete
  GET  /v/api/state?id=&viewer=      unlocked? balance? price?
  POST /v/api/unlock | pay | paid | report
  GET  /v/api/admin?key=&do=list|remove&id=     (CREDITS_ADMIN_KEY)
  GET  /x/studio/status              arms the routes after a deploy

Railway variables (all optional):
  STUDIO_DIR          where videos are kept (default: the folder DB_PATH is in)
  STUDIO_MAX_MB       biggest upload in MB (default 500)
  STUDIO_PACKS        credit packs in pence (default 100,500)
  STUDIO_MONTHLY_FEE  pence per video per month, from its earnings (default 50)
Stripe uses the key server.py already has (STRIPE_SECRET). Apple Pay and
Google Pay show on the Stripe payment page when they are switched on in the
Stripe dashboard (Settings > Payment methods).
"""

import base64
import gzip
import hashlib
import hmac
import importlib
import json
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
from collections import defaultdict, deque

VERSION = "4.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

SITE = (os.environ.get("HOST") or "https://sebbi.pro").strip().rstrip("/")


def _int_env(name, default, lo, hi):
    try:
        return max(lo, min(hi, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


MAX_BYTES = _int_env("STUDIO_MAX_MB", 500, 20, 4000) * 1024 * 1024
TEASER_MAX = 120 * 1024 * 1024
POSTER_MAX = 4 * 1024 * 1024
CHUNK_MAX = 9 * 1024 * 1024
MONTHLY_FEE = _int_env("STUDIO_MONTHLY_FEE", 50, 0, 1000)
FEE_PERIOD = 30 * 86400
SHARE = 0.70
PRICES = (10, 20, 50, 100)
KEEP_FREE = 1024 * 1024 * 1024


def _packs():
    out = []
    for p in (os.environ.get("STUDIO_PACKS") or "100,500").split(","):
        try:
            v = int(p.strip())
        except ValueError:
            continue
        if 50 <= v <= 10000 and v not in out:
            out.append(v)
    return sorted(out) or [100, 500]


PACKS = _packs()

ID_RE = re.compile(r"^[a-z0-9]{8}$")
VIEWER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_RE = re.compile(r"^owner:cr_[a-f0-9]{20}$")
SESSION_RE = re.compile(r"^cs_[A-Za-z0-9_]{8,200}$")
TITLE_CLEAN = re.compile(r"[<>\"\\\x00-\x1f]")
ALPHA = "abcdefghijkmnpqrstuvwxyz23456789"

KINDS = {"full": ("full", MAX_BYTES), "teaser": ("teaser", TEASER_MAX), "poster": ("jpg", POSTER_MAX)}

_ctx = {}
_cr = None
_ready = False
_patched = False
_dir_cache = None
_ulocks = defaultdict(threading.Lock)
_wins = defaultdict(deque)
_wins_lock = threading.Lock()

_CREATE_GZ = (
    "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"
)


def _page(b):
    return gzip.decompress(base64.b64decode("".join(b.split())))


CREATE_HTML = _page(_CREATE_GZ)


# ------------------------------------------------------------------ plumbing

def _credits():
    """The credits module holds balances, creator accounts and Stripe."""
    global _cr
    if _cr is not None:
        return _cr
    m = sys.modules.get("modules.credits") or importlib.import_module("modules.credits")
    if "conn" in _ctx:
        m._ctx.update(_ctx)
        m._setup()
    _cr = m
    return m


def _storage():
    """(folder, survives_redeploys)"""
    global _dir_cache
    if _dir_cache:
        return _dir_cache
    cands = []
    if os.environ.get("STUDIO_DIR", "").strip():
        cands.append((os.environ["STUDIO_DIR"].strip(), True))
    db = os.environ.get("DB_PATH", "").strip()
    if db and os.path.dirname(db):
        cands.append((os.path.join(os.path.dirname(db), "studio"), True))
    if os.path.isdir("/data"):
        cands.append(("/data/studio", True))
    cands.append((os.path.abspath("studio_media"), False))
    for d, persistent in cands:
        try:
            os.makedirs(d, exist_ok=True)
            if os.access(d, os.W_OK):
                _dir_cache = (d, persistent)
                return _dir_cache
        except Exception:
            continue
    _dir_cache = (os.path.abspath("."), False)
    return _dir_cache


def _path(vid, kind, part=False):
    return os.path.join(_storage()[0], "%s.%s%s" % (vid, KINDS[kind][0], ".part" if part else ""))


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS studio_video(id TEXT PRIMARY KEY,account TEXT,creator TEXT,"
                  "title TEXT,price INTEGER,free_seconds INTEGER,created REAL,status TEXT,"
                  "full_size INTEGER,full_mime TEXT,teaser_size INTEGER,teaser_mime TEXT,"
                  "plays INTEGER DEFAULT 0,unlocks INTEGER DEFAULT 0,earned INTEGER DEFAULT 0,"
                  "fees INTEGER DEFAULT 0,fee_period INTEGER DEFAULT -1,fee_taken INTEGER DEFAULT 0,"
                  "likes INTEGER DEFAULT 0,comments INTEGER DEFAULT 0,sha256 TEXT,"
                  "audit_hash TEXT,block_index INTEGER,live_at REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS studio_video_account ON studio_video(account)")
        c.execute("CREATE INDEX IF NOT EXISTS studio_video_status ON studio_video(status)")
        c.execute("CREATE TABLE IF NOT EXISTS studio_meta(k TEXT PRIMARY KEY,v TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS studio_report(id INTEGER PRIMARY KEY AUTOINCREMENT,video TEXT,"
                  "reason TEXT,at REAL,who TEXT)")
        row = c.execute("SELECT v FROM studio_meta WHERE k='secret'").fetchone()
        if not row:
            c.execute("INSERT INTO studio_meta(k,v) VALUES('secret',?)", (secrets.token_hex(32),))
        c.commit()
    _credits()
    _ready = True


def _secret():
    with _ctx["lock"]:
        return _ctx["conn"].execute("SELECT v FROM studio_meta WHERE k='secret'").fetchone()[0]


def _token(vid, viewer):
    return hmac.new(_secret().encode(), ("%s|%s" % (vid, viewer)).encode(), hashlib.sha256).hexdigest()[:40]


def _seal(kind, detail, extra):
    ex = {"studio_version": VERSION}
    ex.update(extra or {})
    try:
        return _credits()._seal(kind, detail, ex)
    except Exception:
        return None, None


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
        if xff:
            return xff.split(",")[0].strip()[:64]
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def _slug(name):
    return urllib.parse.quote(str(name or "").replace(" ", "_"))


def _gbp(p):
    return "£%d.%02d" % (p // 100, p % 100) if p >= 100 else "%dp" % p


COLS = ("id,account,creator,title,price,free_seconds,created,status,full_size,full_mime,teaser_size,"
        "teaser_mime,plays,unlocks,earned,fees,fee_period,fee_taken,likes,comments,sha256,audit_hash,"
        "block_index,live_at")


def _video(vid):
    if not ID_RE.match(vid or ""):
        return None
    with _ctx["lock"]:
        r = _ctx["conn"].execute("SELECT " + COLS + " FROM studio_video WHERE id=?", (vid,)).fetchone()
    return dict(zip(COLS.split(","), r)) if r else None


def _public(v):
    return {"id": v["id"], "title": v["title"], "creator": v["creator"], "price": v["price"],
            "price_label": _gbp(v["price"]), "free_seconds": v["free_seconds"],
            "plays": v["plays"], "paid_views": v["unlocks"], "likes": v["likes"],
            "comments": v["comments"], "link": SITE + "/v/" + v["id"],
            "teaser": "/v/%s/teaser" % v["id"], "poster": "/v/%s/poster.jpg" % v["id"],
            "channel": SITE + "/cinema/@" + _slug(v["creator"]),
            "live_at": v["live_at"], "block_index": v["block_index"]}


def _acct(q, b):
    key = str(b.get("key") or q.get("key") or "").strip()
    return _credits()._account(key)


def _ensure_viewer(viewer):
    with _ctx["lock"]:
        _ctx["conn"].execute("INSERT OR IGNORE INTO credit_viewer(id,balance,spent,created) VALUES(?,0,0,?)",
                             (viewer, time.time()))
        _ctx["conn"].commit()
        r = _ctx["conn"].execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()
    return r[0] if r else 0


def _unlocked(vid, viewer):
    with _ctx["lock"]:
        r = _ctx["conn"].execute("SELECT block_index FROM credit_unlock WHERE viewer=? AND video=?",
                                 (viewer, "st:" + vid)).fetchone()
    return (True, r[0]) if r else (False, None)


# ------------------------------------------------------------------ creators

def a_join(q, b, h):
    if not _limit(_ip(h), "join", 3, 10):
        return {"error": "slow_down", "message": "Too many tries. Wait a minute."}, 429
    return _credits().c_creator_join(q, b)


def a_signin(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 403
    return {"name": acct["name"], "creator_id": acct["id"],
            "channel": SITE + "/cinema/@" + _slug(acct["name"])}, 200


def a_new(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again, your key wasn't recognised."}, 403
    if not _limit(acct["id"], "new", 6, 40):
        return {"error": "slow_down", "message": "That's a lot of uploads. Try again in a few minutes."}, 429
    title = TITLE_CLEAN.sub("", str(b.get("title") or "")).strip()[:80]
    if len(title) < 2:
        return {"error": "title", "message": "Give your video a name so people can find it."}, 400
    if not b.get("rights"):
        return {"error": "rights", "message": "Tick the box to confirm the video is yours to sell."}, 400
    try:
        price = int(b.get("price") or 10)
    except (TypeError, ValueError):
        price = 10
    if price not in PRICES:
        price = 10
    try:
        free = max(3, min(30, int(b.get("free_seconds") or 8)))
    except (TypeError, ValueError):
        free = 8
    try:
        size = int(b.get("full_size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return {"error": "no_video", "message": "Pick a video first."}, 400
    if size > MAX_BYTES:
        return {"error": "too_big", "message": "That video is %d MB. The limit is %d MB - trim it and try again."
                % (size // 1048576, MAX_BYTES // 1048576)}, 413
    mime = str(b.get("full_mime") or "video/mp4")[:60]
    if not mime.startswith("video/"):
        mime = "video/mp4"
    try:
        free_disk = shutil.disk_usage(_storage()[0]).free
    except Exception:
        free_disk = 0
    if free_disk < size + TEASER_MAX + KEEP_FREE:
        return {"error": "full", "message": "Uploads are paused for a moment while we add space. Try again soon."}, 507
    _sweep()
    with _ctx["lock"]:
        c = _ctx["conn"]
        for _ in range(20):
            vid = "".join(secrets.choice(ALPHA) for _ in range(8))
            if not c.execute("SELECT 1 FROM studio_video WHERE id=?", (vid,)).fetchone():
                break
        c.execute("INSERT INTO studio_video(id,account,creator,title,price,free_seconds,created,status,"
                  "full_size,full_mime) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (vid, acct["id"], acct["name"], title, price, free, time.time(), "uploading", size, mime))
        c.commit()
    return {"id": vid, "link": SITE + "/v/" + vid, "short": SITE.split("//")[-1] + "/v/" + vid,
            "title": title, "price": price, "free_seconds": free, "creator": acct["name"],
            "channel": SITE + "/cinema/@" + _slug(acct["name"]), "chunk": 4 * 1024 * 1024}, 200


def _sweep():
    """Clear uploads that were started and never finished (older than a day)."""
    cutoff = time.time() - 86400
    with _ctx["lock"]:
        old = [r[0] for r in _ctx["conn"].execute(
            "SELECT id FROM studio_video WHERE status='uploading' AND created<? LIMIT 50", (cutoff,)).fetchall()]
    for vid in old:
        for kind in KINDS:
            try:
                os.remove(_path(vid, kind, True))
            except OSError:
                pass
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE studio_video SET status='abandoned' WHERE id=?", (vid,))
            _ctx["conn"].commit()


def _magic_ok(kind, head):
    if kind == "poster":
        return head[:3] == b"\xff\xd8\xff"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    return False


def chunk(h, q):
    """Raw bytes, appended at an offset. Retries and resumes are safe."""
    vid = str(q.get("id") or "")
    kind = str(q.get("kind") or "")
    try:
        offset = int(q.get("offset") or 0)
        n = int(h.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        return {"error": "bad_request"}, 400
    if kind not in KINDS or n < 0 or n > CHUNK_MAX:
        return {"error": "bad_request", "message": "Bad upload piece."}, 400
    data = _read(h, n)
    if data is None:
        return {"error": "cut_off", "message": "Connection dropped. Retrying."}, 400
    acct = _credits()._account(h.headers.get("X-Creator-Key", ""))
    if not acct:
        return {"error": "bad_key", "message": "Sign in again."}, 403
    v = _video(vid)
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    if v["status"] != "uploading":
        return {"error": "finished", "message": "That video is already live."}, 409
    cap = KINDS[kind][1] if kind != "full" else v["full_size"]
    p = _path(vid, kind, True)
    with _ulocks[vid + kind]:
        got = os.path.getsize(p) if os.path.exists(p) else 0
        if offset > got:
            return {"error": "gap", "got": got}, 409
        if offset + len(data) > cap:
            return {"error": "too_big", "message": "That file is bigger than it said it was."}, 413
        if offset == 0 and not _magic_ok(kind, data[:16]):
            return {"error": "not_video", "message": "That doesn't look like a video file we can play."}, 415
        if offset + len(data) <= got and offset < got:
            return {"got": got}, 200
        with open(p, "r+b" if os.path.exists(p) else "wb") as f:
            f.seek(offset)
            f.write(data)
            f.truncate(offset + len(data))
        got = offset + len(data)
    return {"got": got}, 200


def _read(h, n):
    out = bytearray()
    while len(out) < n:
        try:
            part = h.rfile.read(min(65536, n - len(out)))
        except Exception:
            return None
        if not part:
            return None
        out += part
    return bytes(out)


def _sha_file(p):
    s = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1048576), b""):
            s.update(blk)
    return s.hexdigest()


def a_finish(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again."}, 403
    v = _video(str(b.get("id") or ""))
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    if v["status"] == "live":
        return {"live": True, "video": _public(v)}, 200
    if v["status"] != "uploading":
        return {"error": "gone"}, 410
    fp, tp, pp = _path(v["id"], "full", True), _path(v["id"], "teaser", True), _path(v["id"], "poster", True)
    fs = os.path.getsize(fp) if os.path.exists(fp) else 0
    ts = os.path.getsize(tp) if os.path.exists(tp) else 0
    if fs != v["full_size"]:
        return {"error": "incomplete", "message": "The video didn't finish uploading.", "got": fs}, 409
    if ts <= 0:
        return {"error": "incomplete", "message": "The teaser didn't finish uploading."}, 409
    tmime = str(b.get("teaser_mime") or "video/mp4")
    tmime = "video/webm" if "webm" in tmime else "video/mp4"
    digest = _sha_file(fp)
    os.replace(fp, _path(v["id"], "full"))
    os.replace(tp, _path(v["id"], "teaser"))
    if os.path.exists(pp):
        os.replace(pp, _path(v["id"], "poster"))
    ah, blk = _seal("studio_video_live", "video=%s;creator=%s;price=%d;sha256=%s"
                    % (v["id"], v["creator"], v["price"], digest),
                    {"video": v["id"], "creator": v["creator"], "price_pence": v["price"],
                     "video_sha256": digest, "bytes": fs})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE studio_video SET status='live',teaser_size=?,teaser_mime=?,sha256=?,"
                             "audit_hash=?,block_index=?,live_at=? WHERE id=?",
                             (ts, tmime, digest, ah, blk, time.time(), v["id"]))
        _ctx["conn"].commit()
    return {"live": True, "video": _public(_video(v["id"])), "sealed_in_chain": ah, "block_index": blk}, 200


def a_mine(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again, your key wasn't recognised."}, 403
    with _ctx["lock"]:
        rows = _ctx["conn"].execute("SELECT " + COLS + " FROM studio_video WHERE account=? AND status='live' "
                                    "ORDER BY created DESC LIMIT 200", (acct["id"],)).fetchall()
    vids = []
    owner = "owner:" + acct["id"]
    for r in rows:
        v = dict(zip(COLS.split(","), r))
        p = _public(v)
        p.update({"earned": v["earned"], "fees": v["fees"],
                  "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], owner, _token(v["id"], owner))})
        vids.append(p)
    balance, views = _credits()._creator_totals(acct["name"])
    return {"name": acct["name"], "balance_pence": balance, "balance_label": _gbp(balance) if balance else "0p",
            "paid_views": views, "videos": vids, "earn": SITE + "/earn",
            "channel": SITE + "/cinema/@" + _slug(acct["name"])}, 200


def a_delete(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key"}, 403
    v = _video(str(b.get("id") or ""))
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    _remove(v, "creator")
    return {"removed": True}, 200


def _remove(v, by):
    for kind in KINDS:
        for part in (False, True):
            try:
                os.remove(_path(v["id"], kind, part))
            except OSError:
                pass
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE studio_video SET status='removed' WHERE id=?", (v["id"],))
        _ctx["conn"].commit()
    _seal("studio_video_removed", "video=%s;by=%s" % (v["id"], by), {"video": v["id"], "by": by})


# ------------------------------------------------------------------ viewers

def _viewer_from(q, b):
    viewer = str(b.get("viewer") or q.get("viewer") or "").strip()
    return viewer if VIEWER_RE.match(viewer) else None


def a_state(q, b, h):
    v = _video(str(q.get("id") or b.get("id") or ""))
    if not v or v["status"] != "live":
        return {"error": "not_found", "message": "That video isn't here any more."}, 404
    viewer = _viewer_from(q, b)
    out = {"video": _public(v), "packs": [{"pence": p, "label": _gbp(p), "views": p // max(1, v["price"])}
                                         for p in PACKS if p >= v["price"]] or
           [{"pence": v["price"], "label": _gbp(v["price"]), "views": 1}],
           "pay_ready": bool(_credits()._stripe_key())}
    if viewer:
        out["balance_pence"] = _ensure_viewer(viewer)
        done, blk = _unlocked(v["id"], viewer)
        out["unlocked"] = done
        if done:
            out["block_index"] = blk
            out["full"] = "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer))
    return out, 200


def _period_fee(v, share, now):
    period = int((now - (v["live_at"] or v["created"])) // FEE_PERIOD)
    taken = v["fee_taken"] if v["fee_period"] == period else 0
    fee = min(share, max(0, MONTHLY_FEE - taken))
    return period, taken + fee, fee


def _unlock(v, viewer):
    """Spend the viewer's credit on one video. Returns (payload, code)."""
    done, blk = _unlocked(v["id"], viewer)
    if done:
        return {"unlocked": True, "already": True, "block_index": blk,
                "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer)),
                "balance_pence": _ensure_viewer(viewer)}, 200
    _ensure_viewer(viewer)
    price = v["price"]
    now = time.time()
    with _ctx["lock"]:
        c = _ctx["conn"]
        cur = c.execute("UPDATE credit_viewer SET balance=balance-?,spent=spent+? WHERE id=? AND balance>=?",
                        (price, price, viewer, price))
        if cur.rowcount != 1:
            bal = c.execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()[0]
            c.commit()
            return {"unlocked": False, "reason": "not_enough_credit", "price_pence": price,
                    "balance_pence": bal}, 402
        ins = c.execute("INSERT OR IGNORE INTO credit_unlock(viewer,video,creator,price,at) VALUES(?,?,?,?,?)",
                        (viewer, "st:" + v["id"], v["creator"], price, now))
        if ins.rowcount != 1:
            c.execute("UPDATE credit_viewer SET balance=balance+?,spent=spent-? WHERE id=?", (price, price, viewer))
            c.commit()
            return _unlock(v, viewer)
        fresh = dict(zip(COLS.split(","), c.execute("SELECT " + COLS + " FROM studio_video WHERE id=?",
                                                     (v["id"],)).fetchone()))
        share = int(round(price * SHARE))
        period, taken, fee = _period_fee(fresh, share, now)
        net = share - fee
        c.execute("INSERT OR IGNORE INTO credit_creator(name,balance,views) VALUES(?,0,0)", (v["creator"],))
        c.execute("UPDATE credit_creator SET balance=balance+?,views=views+1 WHERE name=?", (net, v["creator"]))
        c.execute("UPDATE studio_video SET unlocks=unlocks+1,earned=earned+?,fees=fees+?,fee_period=?,fee_taken=? "
                  "WHERE id=?", (share, fee, period, taken, v["id"]))
        bal = c.execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()[0]
        c.commit()
    ah, blk = _seal("paid_view", "video=st:%s;creator=%s;price=%d;creator_share=%d;monthly_fee=%d"
                    % (v["id"], v["creator"], price, net, fee),
                    {"video": "st:" + v["id"], "creator": v["creator"], "price_pence": price,
                     "creator_share_pence": share, "monthly_fee_pence": fee, "creator_pence": net,
                     "platform_pence": price - net})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_unlock SET audit_hash=?,block_index=? WHERE viewer=? AND video=?",
                             (ah, blk, viewer, "st:" + v["id"]))
        _ctx["conn"].commit()
    return {"unlocked": True, "price_pence": price, "creator_pence": net, "balance_pence": bal,
            "sealed_in_chain": ah, "block_index": blk,
            "verify": SITE + "/x/walk/block?index=%s" % blk,
            "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer))}, 200


def a_unlock(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    if not v or v["status"] != "live" or not viewer:
        return {"error": "not_found"}, 404
    if not _limit(viewer, "unlock", 20, 300):
        return {"error": "slow_down", "message": "Slow down a moment."}, 429
    return _unlock(v, viewer)


def a_pay(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    if not v or v["status"] != "live" or not viewer:
        return {"error": "not_found"}, 404
    if not _limit(_ip(h), "pay", 6, 40):
        return {"error": "slow_down", "message": "Wait a moment and tap again."}, 429
    cr = _credits()
    if not cr._stripe_key():
        return {"error": "pay_off", "message": "Payments are being switched on. Try again shortly."}, 503
    try:
        pence = int(b.get("pence") or PACKS[0])
    except (TypeError, ValueError):
        pence = PACKS[0]
    if pence not in PACKS:
        pence = PACKS[0]
    pence = max(pence, v["price"])
    _ensure_viewer(viewer)
    back = SITE + "/cinema/v/" + v["id"]
    params = {
        "mode": "payment",
        "submit_type": "pay",
        "client_reference_id": viewer,
        "success_url": back + "?paid={CHECKOUT_SESSION_ID}",
        "cancel_url": back,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][unit_amount]": str(pence),
        "line_items[0][price_data][product_data][name]": "10p Wing credit - %s" % _gbp(pence),
        "line_items[0][price_data][product_data][description]":
            "Unlocks \"%s\" now. The rest stays on this phone for more videos." % v["title"][:60],
        "metadata[studio_video]": v["id"],
        "metadata[viewer]": viewer,
        "payment_intent_data[description]": "10p Wing credit (sebbi.pro)",
        "payment_intent_data[metadata][studio_video]": v["id"],
    }
    data, err = cr._stripe("POST", "checkout/sessions", params,
                           idem="st-%s-%s-%d-%d" % (v["id"], viewer, pence, int(time.time() // 30)))
    if err or not data or not data.get("url"):
        return {"error": "stripe", "message": "Couldn't open the payment page: %s" % (err or "no link")}, 502
    return {"checkout": data["url"], "pence": pence}, 200


def a_paid(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    session = str(b.get("session") or "").strip()
    if not v or not viewer or not SESSION_RE.match(session):
        return {"error": "bad_request"}, 400
    cr = _credits()
    s, err = cr._stripe("GET", "checkout/sessions/" + session)
    if err or not s:
        return {"error": "stripe", "message": "Couldn't confirm the payment yet. Tap unlock again in a moment."}, 502
    if s.get("payment_status") != "paid":
        return {"error": "not_paid", "message": "The payment hasn't gone through."}, 402
    if str(s.get("client_reference_id") or "") != viewer:
        return {"error": "other_phone", "message": "That payment was made on another phone."}, 403
    try:
        pence = int(s.get("amount_total") or 0)
    except (TypeError, ValueError):
        pence = 0
    if pence <= 0 or str(s.get("currency") or "gbp").lower() != "gbp":
        return {"error": "bad_amount"}, 400
    credit = cr._credit_payment(session, viewer, pence, "studio")
    out, code = _unlock(v, viewer) if v["status"] == "live" else ({"unlocked": False}, 404)
    out["payment"] = {"pence": pence, "duplicate": credit.get("duplicate", False)}
    return out, code


def a_report(q, b, h):
    v = _video(str(b.get("id") or ""))
    if not v:
        return {"error": "not_found"}, 404
    if not _limit(_ip(h), "report", 3, 20):
        return {"received": True}, 200
    reason = TITLE_CLEAN.sub("", str(b.get("reason") or ""))[:300]
    who = hashlib.sha256(_ip(h).encode()).hexdigest()[:16]
    with _ctx["lock"]:
        _ctx["conn"].execute("INSERT INTO studio_report(video,reason,at,who) VALUES(?,?,?,?)",
                             (v["id"], reason, time.time(), who))
        _ctx["conn"].commit()
    _seal("studio_report", "video=%s" % v["id"], {"video": v["id"]})
    return {"received": True, "message": "Thanks. It will be looked at."}, 200


def a_admin(q, b, h):
    key = os.environ.get("CREDITS_ADMIN_KEY", "").strip()
    given = str(q.get("key") or b.get("key") or "")
    if not key or not hmac.compare_digest(key, given):
        return {"error": "not_allowed"}, 403
    do = str(q.get("do") or b.get("do") or "list")
    if do == "remove":
        v = _video(str(q.get("id") or b.get("id") or ""))
        if not v:
            return {"error": "not_found"}, 404
        _remove(v, "admin")
        return {"removed": v["id"]}, 200
    with _ctx["lock"]:
        c = _ctx["conn"]
        reps = c.execute("SELECT video,reason,at FROM studio_report ORDER BY id DESC LIMIT 100").fetchall()
        vids = c.execute("SELECT id,creator,title,status,unlocks,earned,created FROM studio_video "
                         "ORDER BY created DESC LIMIT 100").fetchall()
    return {"reports": [{"video": r[0], "link": SITE + "/v/" + r[0], "reason": r[1],
                         "at": time.strftime("%Y-%m-%d %H:%M", time.gmtime(r[2]))} for r in reps],
            "videos": [{"id": r[0], "creator": r[1], "title": r[2], "status": r[3], "paid_views": r[4],
                        "earned": r[5], "link": SITE + "/v/" + r[0],
                        "remove": SITE + "/v/api/admin?key=KEY&do=remove&id=" + r[0]} for r in vids]}, 200


API = {"join": a_join, "signin": a_signin, "new": a_new, "finish": a_finish, "mine": a_mine,
       "delete": a_delete, "state": a_state, "unlock": a_unlock, "pay": a_pay, "paid": a_paid,
       "report": a_report, "admin": a_admin}


# ------------------------------------------------------------------ transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _send_bytes(h, body, ctype, code=200, cache="no-cache", extra=None):
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", cache)
    for k, val in (extra or {}).items():
        h.send_header(k, val)
    h.end_headers()
    h.wfile.write(body)


def _send_file(h, path, ctype, cache="public, max-age=86400"):
    try:
        size = os.path.getsize(path)
    except OSError:
        _send(h, {"error": "not_found"}, 404)
        return
    start, end, code = 0, size - 1, 200
    m = re.match(r"^bytes=(\d*)-(\d*)$", (h.headers.get("Range") or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            h.send_response(416)
            h.send_header("Content-Range", "bytes */%d" % size)
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        code = 206
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Cache-Control", cache)
    if code == 206:
        h.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    h.end_headers()
    try:
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                blk = f.read(min(262144, left))
                if not blk:
                    break
                h.wfile.write(blk)
                left -= len(blk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def _playable(mime):
    return "video/mp4" if mime in ("video/quicktime", "video/x-m4v", "") else mime


def _get(h, path, q):
    if path in ("/create", "/create/"):
        _send_bytes(h, CREATE_HTML, "text/html; charset=utf-8")
        return True
    if path.startswith("/v/api/"):
        name = path[7:].strip("/")
        if name in ("state", "admin"):
            _api(h, name, q, {})
            return True
        _send(h, {"error": "use_post"}, 405)
        return True
    parts = [x for x in path.split("/") if x]
    if len(parts) < 2 or parts[0] != "v":
        return False
    vid = parts[1].lower()
    v = _video(vid)
    if not v or v["status"] != "live":
        if len(parts) == 2:
            h.send_response(302)
            h.send_header("Location", "/cinema?wing=ten")
            h.send_header("Content-Length", "0")
            h.end_headers()
            return True
        _send(h, {"error": "not_found"}, 404)
        return True
    if len(parts) == 2:
        h.send_response(302)
        h.send_header("Location", "/cinema/v/" + vid)
        h.send_header("Cache-Control", "no-store")
        h.send_header("Content-Length", "0")
        h.end_headers()
        return True
    what = parts[2]
    if what == "teaser":
        if not h.headers.get("Range") or h.headers.get("Range", "").startswith("bytes=0-"):
            with _ctx["lock"]:
                _ctx["conn"].execute("UPDATE studio_video SET plays=plays+1 WHERE id=?", (vid,))
                _ctx["conn"].commit()
        _send_file(h, _path(vid, "teaser"), v["teaser_mime"] or "video/mp4")
        return True
    if what in ("poster.jpg", "poster"):
        p = _path(vid, "poster")
        if os.path.exists(p):
            _send_file(h, p, "image/jpeg")
        else:
            _send_bytes(h, b"", "image/jpeg", 404)
        return True
    if what == "full":
        viewer = str(q.get("viewer") or "")
        t = str(q.get("t") or "")
        good = (VIEWER_RE.match(viewer) or OWNER_RE.match(viewer)) and hmac.compare_digest(t, _token(vid, viewer))
        if good and OWNER_RE.match(viewer):
            good = viewer == "owner:" + v["account"]
        elif good:
            good = _unlocked(vid, viewer)[0]
        if not good:
            _send(h, {"error": "locked", "message": "Unlock this video to watch it."}, 403)
            return True
        _send_file(h, _path(vid, "full"), _playable(v["full_mime"] or ""), cache="private, max-age=3600")
        return True
    _send(h, {"error": "not_found"}, 404)
    return True


def _api(h, name, q, body):
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "Open /x/studio/status once."}, 503)
        return
    _setup()
    fn = API.get(name)
    if not fn:
        _send(h, {"error": "not_found"}, 404)
        return
    try:
        out, code = fn(q, body, h)
    except Exception as e:
        print("STUDIO ERR %s: %s" % (name, e), flush=True)
        out, code = {"error": "failed", "message": "Something went wrong. Try again."}, 500
    _send(h, out, code)


def _post(h, path, q):
    name = path[7:].strip("/")
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed"}, 503)
        return True
    _setup()
    if name == "chunk":
        try:
            out, code = chunk(h, q)
        except Exception as e:
            print("STUDIO CHUNK ERR: %s" % e, flush=True)
            out, code = {"error": "failed", "message": "Upload piece failed. Retrying."}, 500
        _send(h, out, code)
        return True
    try:
        n = min(int(h.headers.get("Content-Length") or 0), 20000)
        raw = _read(h, n) if n else b""
        body = json.loads((raw or b"{}").decode("utf-8") or "{}")
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    _api(h, name, q, body)
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


def _split(h):
    u = urllib.parse.urlparse(h.path)
    return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}


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
    if getattr(cls, "_studio4_patched", False):
        _patched = True
        return True
    og = cls.do_GET
    op = getattr(cls, "do_POST", None)

    def do_GET(self):
        path, q = _split(self)
        if path in ("/create", "/create/") or path.startswith("/v/"):
            try:
                if _get(self, path, q):
                    return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as e:
                print("STUDIO GET ERR: %s" % e, flush=True)
                try:
                    _send(self, {"error": "failed"}, 500)
                except Exception:
                    pass
                return
        return og(self)

    def do_POST(self):
        path, q = _split(self)
        if path.startswith("/v/api/"):
            _post(self, path, q)
            return
        return op(self) if op else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls._studio4_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    d, persistent = _storage()
    counts = {}
    if "conn" in _ctx:
        with _ctx["lock"]:
            c = _ctx["conn"]
            counts = {"live_videos": c.execute("SELECT COUNT(*) FROM studio_video WHERE status='live'").fetchone()[0],
                      "paid_views": c.execute("SELECT COALESCE(SUM(unlocks),0) FROM studio_video").fetchone()[0],
                      "creator_earnings_pence": c.execute("SELECT COALESCE(SUM(earned),0) FROM studio_video").fetchone()[0],
                      "reports": c.execute("SELECT COUNT(*) FROM studio_report").fetchone()[0]}
    try:
        free_gb = round(shutil.disk_usage(d).free / 1073741824, 1)
    except Exception:
        free_gb = None
    stripe = False
    try:
        stripe = bool(_credits()._stripe_key())
    except Exception:
        pass
    return {"module": "studio", "version": VERSION, "armed": armed,
            "serves": ["/create", "/v/<id>", "/v/api/*"],
            "storage": {"folder": d, "survives_redeploys": persistent, "free_gb": free_gb},
            "payments_ready": stripe, "packs_pence": PACKS, "prices_pence": list(PRICES),
            "max_upload_mb": MAX_BYTES // 1048576, "monthly_fee_pence": MONTHLY_FEE,
            "creator_share": SHARE, "counts": counts,
            "create": SITE + "/create", "wing": SITE + "/cinema?wing=ten"}, 200
