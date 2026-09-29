"""
modules/studio.py  v4.0.2
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

VERSION = "4.0.2"
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
