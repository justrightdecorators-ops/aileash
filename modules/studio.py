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
Stripe's card fee (1.5% + 20p) is added on top of the credit and shown before
paying, so the full credit is spent on videos: GBP 1 credit costs GBP 1.22.

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
  STUDIO_MAX_MB       biggest upload in MB (default 20000 - about three hours of phone video)
  STUDIO_PACKS        credit packs in pence (default 100,500)
  STUDIO_MONTHLY_FEE  pence per video per month, from its earnings (default 50)
  STUDIO_CARD_FEE_PCT / STUDIO_CARD_FEE_PENCE   the card fee added on top (1.5 / 20)
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
import math
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


MAX_BYTES = _int_env("STUDIO_MAX_MB", 20000, 20, 100000) * 1024 * 1024
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


def _fee_env(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return float(default)


CARD_FEE_PCT = _fee_env("STUDIO_CARD_FEE_PCT", 1.5)
CARD_FEE_PENCE = _fee_env("STUDIO_CARD_FEE_PENCE", 20)


def _charge(credit):
    """What the viewer pays so that, after Stripe's card fee, the full credit is left."""
    return int(math.ceil((credit + CARD_FEE_PENCE) / (1 - CARD_FEE_PCT / 100.0)))

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
        try:
            c.execute("ALTER TABLE studio_video ADD COLUMN tags TEXT DEFAULT ''")
        except Exception:
            pass
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


def _size(n):
    return "%.1f GB" % (n / 1073741824.0) if n >= 1073741824 else "%d MB" % max(1, n // 1048576)


def _gbp(p):
    return "£%d.%02d" % (p // 100, p % 100) if p >= 100 else "%dp" % p


COLS = ("id,account,creator,title,price,free_seconds,created,status,full_size,full_mime,teaser_size,"
        "teaser_mime,plays,unlocks,earned,fees,fee_period,fee_taken,likes,comments,sha256,audit_hash,"
        "block_index,live_at,tags")


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
            "live_at": v["live_at"], "block_index": v["block_index"],
            "tags": [t for t in (v.get("tags") or "").split(" ") if t]}


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
    tags = []
    for t in re.split(r"[\s,]+", str(b.get("tags") or "")):
        t = re.sub(r"[^A-Za-z0-9_]", "", t.lstrip("#"))[:24].lower()
        if t and "#" + t not in tags:
            tags.append("#" + t)
    tags = " ".join(tags[:8])
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
        print("STUDIO: upload of %d MB refused, %d MB free on the video volume" % (size // 1048576, free_disk // 1048576), flush=True)
        return {"error": "full", "message": "That video is %s. There isn't room for it right now - try a shorter clip, "
                "or try again later." % _size(size)}, 507
    _sweep()
    with _ctx["lock"]:
        c = _ctx["conn"]
        for _ in range(20):
            vid = "".join(secrets.choice(ALPHA) for _ in range(8))
            if not c.execute("SELECT 1 FROM studio_video WHERE id=?", (vid,)).fetchone():
                break
        c.execute("INSERT INTO studio_video(id,account,creator,title,price,free_seconds,created,status,"
                  "full_size,full_mime,tags) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (vid, acct["id"], acct["name"], title, price, free, time.time(), "uploading", size, mime, tags))
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
    os.replace(fp, _path(v["id"], "full"))
    os.replace(tp, _path(v["id"], "teaser"))
    if os.path.exists(pp):
        os.replace(pp, _path(v["id"], "poster"))
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE studio_video SET status='live',teaser_size=?,teaser_mime=?,live_at=? WHERE id=?",
                             (ts, tmime, time.time(), v["id"]))
        _ctx["conn"].commit()
    threading.Thread(target=_fingerprint, args=(v["id"], v["creator"], v["price"], fs), daemon=True).start()
    return {"live": True, "video": _public(_video(v["id"]))}, 200


def _fingerprint(vid, creator, price, size):
    """Hash the full video and seal it. Runs after the video is live, so a long video never holds the upload up."""
    try:
        digest = _sha_file(_path(vid, "full"))
        ah, blk = _seal("studio_video_live", "video=%s;creator=%s;price=%d;sha256=%s" % (vid, creator, price, digest),
                        {"video": vid, "creator": creator, "price_pence": price, "video_sha256": digest, "bytes": size})
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE studio_video SET sha256=?,audit_hash=?,block_index=? WHERE id=?",
                                 (digest, ah, blk, vid))
            _ctx["conn"].commit()
    except Exception as e:
        print("STUDIO: fingerprint of %s failed: %s" % (vid, e), flush=True)


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
    packs = [p for p in PACKS if p >= v["price"]] or [v["price"]]
    out = {"video": _public(v),
           "packs": [{"pence": p, "label": _gbp(p), "views": p // max(1, v["price"]),
                      "charge": _charge(p), "charge_label": _gbp(_charge(p)),
                      "fee": _charge(p) - p, "fee_label": _gbp(_charge(p) - p)} for p in packs],
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
    charge = _charge(pence)
    _ensure_viewer(viewer)
    back = SITE + "/cinema/v/" + v["id"]
    params = {
        "mode": "payment",
        "submit_type": "pay",
        "success_url": back + "?paid={CHECKOUT_SESSION_ID}",
        "cancel_url": back,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][unit_amount]": str(charge),
        "line_items[0][price_data][product_data][name]": "10p Wing credit %s + %s card fee" % (_gbp(pence), _gbp(charge - pence)),
        "line_items[0][price_data][product_data][description]":
            "%s credit unlocks \"%s\" now, the rest stays on this phone. The %s card fee is Stripe's charge "
            "for taking the payment." % (_gbp(pence), v["title"][:50], _gbp(charge - pence)),
        "metadata[studio_video]": v["id"],
        "metadata[viewer]": viewer,
        "metadata[credit_pence]": str(pence),
        "payment_intent_data[description]": "10p Wing credit (sebbi.pro)",
        "payment_intent_data[metadata][studio_video]": v["id"],
    }
    data, err = cr._stripe("POST", "checkout/sessions", params,
                           idem="st-%s-%s-%d-%d" % (v["id"], viewer, charge, int(time.time() // 30)))
    if err or not data or not data.get("url"):
        return {"error": "stripe", "message": "Couldn't open the payment page: %s" % (err or "no link")}, 502
    return {"checkout": data["url"], "pence": pence, "charge": charge}, 200


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
    meta = s.get("metadata") or {}
    if str(meta.get("viewer") or s.get("client_reference_id") or "") != viewer:
        return {"error": "other_phone", "message": "That payment was made on another phone."}, 403
    try:
        paid = int(s.get("amount_total") or 0)
        pence = int(meta.get("credit_pence") or paid)
    except (TypeError, ValueError):
        paid, pence = 0, 0
    if pence <= 0 or paid < pence or str(s.get("currency") or "gbp").lower() != "gbp":
        return {"error": "bad_amount"}, 400
    credit = cr._credit_payment(session, viewer, pence, "studio")
    out, code = _unlock(v, viewer) if v["status"] == "live" else ({"unlocked": False}, 404)
    out["payment"] = {"credit_pence": pence, "paid_pence": paid, "duplicate": credit.get("duplicate", False)}
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
            "payments_ready": stripe, "packs_pence": PACKS,
            "viewer_pays": {str(p): _charge(p) for p in PACKS}, "prices_pence": list(PRICES),
            "max_upload_mb": MAX_BYTES // 1048576, "monthly_fee_pence": MONTHLY_FEE,
            "creator_share": SHARE, "counts": counts,
            "create": SITE + "/create", "wing": SITE + "/cinema?wing=ten"}, 200
