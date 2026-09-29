"""
modules/studio.py  v4.0.1
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

VERSION = "4.0.1"
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
    "cuCVwPANfibZNDh59H8BEp6hAJG2AAA="
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
