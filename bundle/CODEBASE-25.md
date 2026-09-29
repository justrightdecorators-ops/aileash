# Codebase — part 25 of 45

Contains:
- `modules/studio.py`


## `modules/studio.py`

1320 lines, 68971 bytes

```python
"""
modules/studio.py  v4.0.3
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

VERSION = "4.0.3"
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

```
