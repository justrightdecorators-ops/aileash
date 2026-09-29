# Codebase — part 25 of 45

Contains:
- `modules/studio.py`


## `modules/studio.py`

1404 lines, 73250 bytes

```python
"""
modules/studio.py  v4.0.5
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

VERSION = "4.0.5"
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
PI_RE = re.compile(r"^pi_[A-Za-z0-9_]{8,200}$")
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
    "ArsKMKkC0wAA"
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
           "pay_ready": bool(_credits()._stripe_key()),
           "wallet_publishable": _pub_key()}
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


def _pub_key():
    return (os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
            or os.environ.get("STRIPE_PUBLISHABLE", "").strip())


def a_intent(q, b, h):
    """Create a PaymentIntent so the wallet (Apple/Google Pay) can be tapped
    on this page, with no redirect and no email box. Card still works too."""
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
    params = {
        "amount": str(charge),
        "currency": "gbp",
        "payment_method_types[0]": "card",
        "description": "10p Wing credit (sebbi.pro)",
        "metadata[studio_video]": v["id"],
        "metadata[viewer]": viewer,
        "metadata[credit_pence]": str(pence),
    }
    data, err = cr._stripe("POST", "payment_intents", params,
                           idem="pi-%s-%s-%d-%d" % (v["id"], viewer, charge, int(time.time() // 30)))
    if err or not data or not data.get("client_secret"):
        return {"error": "stripe", "message": "Couldn't start the payment: %s" % (err or "no intent")}, 502
    return {"client_secret": data["client_secret"], "pi": data.get("id"),
            "pence": pence, "charge": charge, "charge_label": _gbp(charge),
            "publishable": _pub_key(), "currency": "gbp"}, 200


def a_intent_done(q, b, h):
    """Confirm a wallet/card PaymentIntent succeeded, then credit and unlock."""
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    pi = str(b.get("payment_intent") or "").strip()
    if not v or not viewer or not PI_RE.match(pi):
        return {"error": "bad_request"}, 400
    cr = _credits()
    d, err = cr._stripe("GET", "payment_intents/" + pi)
    if err or not d:
        return {"error": "stripe", "message": "Couldn't confirm the payment yet. Tap unlock again in a moment."}, 502
    if d.get("status") != "succeeded":
        return {"error": "not_paid", "message": "The payment hasn't gone through."}, 402
    meta = d.get("metadata") or {}
    if str(meta.get("viewer") or "") != viewer:
        return {"error": "other_phone", "message": "That payment was made on another phone."}, 403
    try:
        paid = int(d.get("amount_received") or d.get("amount") or 0)
        pence = int(meta.get("credit_pence") or 0)
    except (TypeError, ValueError):
        paid, pence = 0, 0
    if pence <= 0 or paid < pence or str(d.get("currency") or "gbp").lower() != "gbp":
        return {"error": "bad_amount"}, 400
    credit = cr._credit_payment(pi, viewer, pence, "studio_wallet")
    out, code = _unlock(v, viewer) if v["status"] == "live" else ({"unlocked": False}, 404)
    out["payment"] = {"credit_pence": pence, "paid_pence": paid, "duplicate": credit.get("duplicate", False)}
    return out, code


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
       "intent": a_intent, "intent_done": a_intent_done,
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
