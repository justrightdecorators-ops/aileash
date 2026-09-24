"""
modules/credits.py  v1.2.0
Credits: the money side of Monop Studio, running on the chain.

A viewer tops up once. Every unlock spends a few pence of that balance, the
creator's 7p share lands on the creator's balance, and both sides are sealed
into the chain. Creators withdraw their balance to their own bank account
through Stripe Connect, and every payout is sealed too.

Served with permissive CORS from a clean /c/ prefix:

  Viewers
    GET  /c/hello?viewer=            balance, or a new viewer id
    GET  /c/check?viewer=&video=     is this already unlocked
    POST /c/unlock                   spend the credit, seal it
    POST /c/topup                    send the buyer to Stripe
    POST /c/stripe                   Stripe says a payment cleared (signed)

  Creators  (the /earn page uses these)
    POST /c/creator/join             claim a creator name, get a private key
    POST /c/creator/me               balance, views, payout status
    POST /c/creator/connect          set up payouts with Stripe (bank details)
    POST /c/creator/dashboard        open the creator's own Stripe page
    POST /c/creator/withdraw         send the whole balance to their bank

  Other
    GET  /c/grant?key=&viewer=&pence=&session=   credit a viewer by hand (admin)
    GET  /c/earnings?creator=        public view of a creator's balance
    GET  /x/credits/status           counts

NEW IN 1.2.0
  * Creator accounts. A creator claims their name once on /earn and gets a
    private key. Earnings recorded under that name can only be withdrawn with
    that key. Names are unique, ignoring capitals.
  * Withdrawals. The creator links a bank account through Stripe Connect
    (Express). Withdraw sends their whole balance as a Stripe transfer; Stripe
    then pays it into their bank automatically. If the transfer fails, the
    balance is put straight back and the failure is sealed.

RAILWAY VARIABLES
  STRIPE_TOPUP_LINK       the Stripe payment link for top-ups
  STRIPE_WEBHOOK_SECRET   the signing secret for /c/stripe
  STRIPE_SECRET_KEY       your Stripe secret key (needed for creator payouts)
  CREDITS_MIN_WITHDRAW    smallest withdrawal in pence (default 1000 = GBP 10)
  CREDITS_ADMIN_KEY       any long password, for /c/grant
  CREDITS_TEST_MODE       set to 0 to stop giving new viewers 100p free
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.2.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

TEST_MODE = os.environ.get("CREDITS_TEST_MODE", "1") != "0"
TEST_GRANT = 100          # pence handed to a new viewer while in test mode
CREATOR_SHARE = 0.70      # 7p of every 10p
MAX_PRICE = 500
SIG_TOLERANCE = 300       # seconds a Stripe signature stays valid
KEY = "public-credits"
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
VID_RE = re.compile(r"^[A-Za-z0-9_.:-]{4,120}$")
NAME_RE = re.compile(r"[^A-Za-z0-9 ._-]")
SESSION_RE = re.compile(r"^[A-Za-z0-9_:.-]{4,200}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{20,80}$")
RESERVED = {"anonymous", "sebbi", "sebbi.pro", "monop", "monop studio", "admin"}
SITE = "https://sebbi.pro"

_ready = False
_patched = False
_ctx = {}


def _checkout_url(pence, viewer=""):
    """Stripe payment link, carrying the viewer id so the webhook knows who paid."""
    link = os.environ.get("STRIPE_TOPUP_LINK", "").strip()
    if not link:
        return None
    ref = viewer if ID_RE.match(viewer or "") else "topup_%d" % pence
    return link + ("&" if "?" in link else "?") + "client_reference_id=" + urllib.parse.quote(ref)


def _webhook_secret():
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def _admin_key():
    return os.environ.get("CREDITS_ADMIN_KEY", "").strip()


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS credit_viewer(id TEXT PRIMARY KEY,balance INTEGER,"
                  "spent INTEGER DEFAULT 0,created REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS credit_unlock(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "viewer TEXT,video TEXT,creator TEXT,price INTEGER,at REAL,audit_hash TEXT,"
                  "block_index INTEGER,UNIQUE(viewer,video))")
        c.execute("CREATE TABLE IF NOT EXISTS credit_creator(name TEXT PRIMARY KEY,balance INTEGER,"
                  "views INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS credit_payment(session TEXT PRIMARY KEY,viewer TEXT,"
                  "pence INTEGER,status TEXT,source TEXT,at REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS credit_account(id TEXT PRIMARY KEY,name TEXT,"
                  "name_key TEXT UNIQUE,key_hash TEXT UNIQUE,stripe_account TEXT,"
                  "payouts_enabled INTEGER DEFAULT 0,details_submitted INTEGER DEFAULT 0,created REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS credit_payout(id TEXT PRIMARY KEY,account TEXT,pence INTEGER,"
                  "status TEXT,stripe_transfer TEXT,error TEXT,at REAL,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _seal(kind, detail, extra):
    now = time.time()
    ev = {"user_id": "crd:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "credits", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "credits_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, now, KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _viewer(vid, make=True):
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT balance,spent FROM credit_viewer WHERE id=?", (vid,)).fetchone()
        if row:
            return {"balance": row[0], "spent": row[1]}
        if not make:
            return None
        start = TEST_GRANT if TEST_MODE else 0
        _ctx["conn"].execute("INSERT INTO credit_viewer(id,balance,spent,created) VALUES(?,?,0,?)",
                             (vid, start, time.time()))
        _ctx["conn"].commit()
    return {"balance": start, "spent": 0}


def _credit_payment(session, viewer, pence, source):
    """Record one payment exactly once; credit the viewer if we know who it is."""
    now = time.time()
    with _ctx["lock"]:
        c = _ctx["conn"]
        row = c.execute("SELECT status,viewer,block_index FROM credit_payment WHERE session=?",
                        (session,)).fetchone()
        if row and row[0] != "unmatched":
            return {"duplicate": True, "status": row[0], "block_index": row[2]}
        if row and row[0] == "unmatched" and not viewer:
            return {"duplicate": True, "status": "unmatched"}
        if not row:
            c.execute("INSERT INTO credit_payment(session,viewer,pence,status,source,at) VALUES(?,?,?,?,?,?)",
                      (session, viewer or "", pence, "pending", source, now))
        else:
            c.execute("UPDATE credit_payment SET status='pending',viewer=? WHERE session=?", (viewer, session))
        c.commit()

    if viewer:
        _viewer(viewer)
    status = "credited" if viewer else "unmatched"
    audit_hash, block = _seal("card_topup" if viewer else "card_topup_unmatched",
                              "session=%s;pence=%d;status=%s;source=%s" % (session[-12:], pence, status, source),
                              {"pence": pence, "status": status, "source": source})
    with _ctx["lock"]:
        c = _ctx["conn"]
        if viewer:
            c.execute("UPDATE credit_viewer SET balance=balance+? WHERE id=?", (pence, viewer))
        c.execute("UPDATE credit_payment SET status=?,audit_hash=?,block_index=? WHERE session=?",
                  (status, audit_hash, block, session))
        c.commit()
    out = {"duplicate": False, "status": status, "pence": pence,
           "sealed_in_chain": audit_hash, "block_index": block}
    if viewer:
        out["balance_pence"] = _viewer(viewer)["balance"]
    return out


def _verify_stripe(raw, sig_header, secret):
    if not secret or not sig_header:
        return False
    t, v1 = None, []
    for part in sig_header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            t = v
        elif k == "v1":
            v1.append(v)
    if not t or not v1:
        return False
    try:
        if abs(time.time() - int(t)) > SIG_TOLERANCE:
            return False
    except ValueError:
        return False
    expected = hmac.new(secret.encode("utf-8"), t.encode("utf-8") + b"." + raw, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in v1)


# ---------------------------------------------------------------- commands

def c_hello(q, body):
    vid = (q.get("viewer") or body.get("viewer") or "").strip()
    if not ID_RE.match(vid):
        return {"error": "viewer id needed (8 to 64 characters, letters and numbers)"}, 400
    v = _viewer(vid)
    return {"viewer": vid, "balance_pence": v["balance"], "spent_pence": v["spent"],
            "test_mode": TEST_MODE, "topup": "https://sebbi.pro/credits"}, 200


def c_check(q, body):
    vid = (q.get("viewer") or body.get("viewer") or "").strip()
    video = (q.get("video") or body.get("video") or "").strip()
    if not ID_RE.match(vid) or not VID_RE.match(video):
        return {"unlocked": False, "error": "viewer and video needed"}, 400
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT block_index,at FROM credit_unlock WHERE viewer=? AND video=?",
                                   (vid, video)).fetchone()
    v = _viewer(vid)
    return {"unlocked": bool(row), "block_index": row[0] if row else None,
            "balance_pence": v["balance"]}, 200


def c_unlock(q, body):
    vid = str(body.get("viewer") or q.get("viewer") or "").strip()
    video = str(body.get("video") or q.get("video") or "").strip()
    creator = NAME_RE.sub("", str(body.get("creator") or "Anonymous"))[:40] or "Anonymous"
    try:
        price = max(1, min(MAX_PRICE, int(float(body.get("price") or q.get("price") or 10))))
    except (TypeError, ValueError):
        price = 10
    if not ID_RE.match(vid) or not VID_RE.match(video):
        return {"unlocked": False, "error": "viewer and video needed"}, 400

    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT block_index FROM credit_unlock WHERE viewer=? AND video=?",
                                   (vid, video)).fetchone()
    if row:
        v = _viewer(vid)
        return {"unlocked": True, "already": True, "block_index": row[0],
                "balance_pence": v["balance"]}, 200

    v = _viewer(vid)
    if v["balance"] < price:
        return {"unlocked": False, "reason": "not_enough_credit", "price_pence": price,
                "balance_pence": v["balance"], "topup": "https://sebbi.pro/credits",
                "message": "You need %dp and have %dp. Top up and it unlocks straight away."
                           % (price, v["balance"])}, 402

    share = int(round(price * CREATOR_SHARE))
    audit_hash, block = _seal("paid_view", "video=%s;creator=%s;price=%d;creator_share=%d"
                              % (video, creator, price, share),
                              {"video": video, "creator": creator, "price_pence": price,
                               "creator_pence": share, "platform_pence": price - share})
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("UPDATE credit_viewer SET balance=balance-?, spent=spent+? WHERE id=?", (price, price, vid))
        c.execute("INSERT OR IGNORE INTO credit_creator(name,balance,views) VALUES(?,0,0)", (creator,))
        c.execute("UPDATE credit_creator SET balance=balance+?, views=views+1 WHERE name=?", (share, creator))
        c.execute("INSERT OR IGNORE INTO credit_unlock(viewer,video,creator,price,at,audit_hash,block_index)"
                  " VALUES(?,?,?,?,?,?,?)", (vid, video, creator, price, time.time(), audit_hash, block))
        c.commit()
    v = _viewer(vid)
    return {"unlocked": True, "price_pence": price, "creator_pence": share,
            "balance_pence": v["balance"], "sealed_in_chain": audit_hash, "block_index": block,
            "verify": "https://sebbi.pro/x/walk/block?index=%s" % block}, 200


def c_topup(q, body):
    vid = str(body.get("viewer") or q.get("viewer") or "").strip()
    try:
        pence = max(50, min(10000, int(float(body.get("pence") or q.get("pence") or 500))))
    except (TypeError, ValueError):
        pence = 500
    if not ID_RE.match(vid):
        return {"error": "viewer id needed"}, 400
    _viewer(vid)
    url = _checkout_url(pence, vid)
    if url:
        return {"paid": False, "checkout": url, "pence": pence,
                "message": "Pay there and your credit lands within a few seconds."}, 200
    if not TEST_MODE:
        return {"paid": False, "error": "no_checkout_configured",
                "message": "Card top-ups are not switched on yet."}, 503
    audit_hash, block = _seal("test_topup", "viewer=%s;pence=%d" % (vid[:12], pence),
                              {"pence": pence, "test_mode": True})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_viewer SET balance=balance+? WHERE id=?", (pence, vid))
        _ctx["conn"].commit()
    v = _viewer(vid)
    return {"paid": True, "test_mode": True, "added_pence": pence, "balance_pence": v["balance"],
            "sealed_in_chain": audit_hash, "block_index": block}, 200


def c_stripe(raw, headers):
    secret = _webhook_secret()
    if not secret:
        return {"error": "webhook_not_configured"}, 503
    if not _verify_stripe(raw, headers.get("Stripe-Signature", "") or "", secret):
        return {"error": "bad_signature"}, 400
    try:
        ev = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"error": "bad_json"}, 400
    etype = str(ev.get("type") or "")
    if etype not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return {"received": True, "ignored": etype}, 200
    s = (ev.get("data") or {}).get("object") or {}
    if s.get("payment_status") != "paid":
        return {"received": True, "ignored": "not_paid_yet"}, 200
    session = str(s.get("id") or "")[:200]
    if not SESSION_RE.match(session):
        return {"error": "no_session_id"}, 400
    try:
        pence = int(s.get("amount_total") or 0)
    except (TypeError, ValueError):
        pence = 0
    if pence <= 0:
        return {"received": True, "ignored": "zero_amount"}, 200
    ref = str(s.get("client_reference_id") or "").strip()
    viewer = ref if (ID_RE.match(ref) and not ref.startswith("topup_")) else ""
    out = _credit_payment(session, viewer, pence, "stripe")
    out["received"] = True
    return out, 200


def c_grant(q, body):
    key = _admin_key()
    given = str(q.get("key") or body.get("key") or "")
    if not key or not hmac.compare_digest(key, given):
        return {"error": "not_allowed"}, 403
    vid = str(q.get("viewer") or body.get("viewer") or "").strip()
    if not ID_RE.match(vid):
        return {"error": "viewer id needed"}, 400
    session = str(q.get("session") or body.get("session") or "").strip()
    pence = None
    if session:
        if not SESSION_RE.match(session):
            return {"error": "bad session id"}, 400
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT pence FROM credit_payment WHERE session=?", (session,)).fetchone()
        if row:
            pence = row[0]
    if pence is None:
        try:
            pence = max(1, min(10000, int(float(q.get("pence") or body.get("pence") or 0))))
        except (TypeError, ValueError):
            return {"error": "pence needed"}, 400
    if not session:
        session = "manual:%d" % int(time.time() * 1000)
    out = _credit_payment(session, vid, pence, "manual")
    out["viewer"] = vid
    return out, 200


def c_earnings(q, body):
    name = NAME_RE.sub("", str(q.get("creator") or body.get("creator") or ""))[:40]
    if not name:
        return {"error": "creator needed"}, 400
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT balance,views FROM credit_creator WHERE name=?", (name,)).fetchone()
        recent = _ctx["conn"].execute("SELECT video,price,at,block_index FROM credit_unlock WHERE creator=?"
                                      " ORDER BY id DESC LIMIT 25", (name,)).fetchall()
    return {"creator": name, "balance_pence": row[0] if row else 0, "paid_views": row[1] if row else 0,
            "recent": [{"video": r[0], "price_pence": r[1],
                        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2])),
                        "block_index": r[3]} for r in recent]}, 200


# ---------------------------------------------------------------- creators

def _stripe_key():
    return os.environ.get("STRIPE_SECRET_KEY", "").strip()


def _min_withdraw():
    try:
        return max(100, int(os.environ.get("CREDITS_MIN_WITHDRAW", "1000")))
    except ValueError:
        return 1000


def _stripe(method, path, params=None, idem=None):
    """Call Stripe's API. Returns (data, None) or (None, error message)."""
    key = _stripe_key()
    if not key:
        return None, "Stripe secret key not set"
    url = "https://api.stripe.com/v1/" + path
    data = None
    if params:
        enc = urllib.parse.urlencode(params)
        if method == "GET":
            url += "?" + enc
        else:
            data = enc.encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if idem:
        req.add_header("Idempotency-Key", idem)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8") or "{}"), None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8") or "{}").get("error") or {}
            return None, str(err.get("message") or err.get("code") or ("HTTP %d" % e.code))
        except Exception:
            return None, "HTTP %d" % e.code
    except Exception as e:
        return None, str(e)[:160]


def _hash_key(k):
    return hashlib.sha256(("sebbi-creator:" + k).encode("utf-8")).hexdigest()


def _account(key):
    key = str(key or "").strip()
    if not KEY_RE.match(key):
        return None
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT id,name,stripe_account,payouts_enabled,details_submitted,created "
                                   "FROM credit_account WHERE key_hash=?", (_hash_key(key),)).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "stripe_account": row[2] or "",
            "payouts_enabled": bool(row[3]), "details_submitted": bool(row[4]), "created": row[5]}


def _creator_totals(name):
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT balance,views FROM credit_creator WHERE name=?", (name,)).fetchone()
    return (row[0] or 0, row[1] or 0) if row else (0, 0)


def _refresh_stripe(acct):
    """Ask Stripe whether this creator can be paid yet, and remember the answer."""
    if not acct["stripe_account"] or acct["payouts_enabled"] or not _stripe_key():
        return acct
    data, err = _stripe("GET", "accounts/" + acct["stripe_account"])
    if err or not data:
        return acct
    acct["payouts_enabled"] = bool(data.get("payouts_enabled"))
    acct["details_submitted"] = bool(data.get("details_submitted"))
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_account SET payouts_enabled=?,details_submitted=? WHERE id=?",
                             (int(acct["payouts_enabled"]), int(acct["details_submitted"]), acct["id"]))
        _ctx["conn"].commit()
    return acct


def _key_from(q, body):
    return str(body.get("key") or q.get("key") or "").strip()


def c_creator_join(q, body):
    name = NAME_RE.sub("", str(body.get("name") or q.get("name") or "")).strip()[:40]
    if len(name) < 3:
        return {"error": "name_too_short", "message": "Pick a creator name of at least 3 letters or numbers."}, 400
    key_name = name.lower()
    if key_name in RESERVED:
        return {"error": "name_reserved", "message": "That name is reserved. Pick another."}, 400
    cid = "cr_" + secrets.token_hex(10)
    key = "ck_" + secrets.token_urlsafe(30)
    with _ctx["lock"]:
        c = _ctx["conn"]
        if c.execute("SELECT 1 FROM credit_account WHERE name_key=?", (key_name,)).fetchone():
            return {"error": "name_taken", "message": "That name is already claimed. Pick another."}, 409
        c.execute("INSERT INTO credit_account(id,name,name_key,key_hash,created) VALUES(?,?,?,?,?)",
                  (cid, name, key_name, _hash_key(key), time.time()))
        c.commit()
    audit_hash, block = _seal("creator_join", "creator=%s;name=%s" % (cid, name), {"creator_id": cid, "name": name})
    return {"creator_id": cid, "name": name, "key": key, "sealed_in_chain": audit_hash, "block_index": block,
            "message": "Save your key. It is the only way to withdraw your earnings."}, 200


def c_creator_me(q, body):
    acct = _account(_key_from(q, body))
    if not acct:
        return {"error": "bad_key", "message": "That key was not recognised."}, 403
    acct = _refresh_stripe(acct)
    balance, views = _creator_totals(acct["name"])
    with _ctx["lock"]:
        rows = _ctx["conn"].execute("SELECT id,pence,status,at,block_index,error FROM credit_payout "
                                    "WHERE account=? ORDER BY at DESC LIMIT 20", (acct["id"],)).fetchall()
    return {"creator_id": acct["id"], "name": acct["name"], "balance_pence": balance, "paid_views": views,
            "payouts_ready_on_site": bool(_stripe_key()),
            "bank_linked": bool(acct["stripe_account"]), "details_submitted": acct["details_submitted"],
            "payouts_enabled": acct["payouts_enabled"], "min_withdraw_pence": _min_withdraw(),
            "payouts": [{"id": r[0], "pence": r[1], "status": r[2],
                         "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[3])),
                         "block_index": r[4], "error": r[5] or None} for r in rows]}, 200


def c_creator_connect(q, body):
    acct = _account(_key_from(q, body))
    if not acct:
        return {"error": "bad_key", "message": "That key was not recognised."}, 403
    if not _stripe_key():
        return {"error": "payouts_not_switched_on", "message": "Payouts are not switched on yet."}, 503
    if not acct["stripe_account"]:
        data, err = _stripe("POST", "accounts", {
            "type": "express", "country": "GB",
            "capabilities[transfers][requested]": "true",
            "business_profile[product_description]": "Creator on Monop Studio (sebbi.pro)",
            "metadata[creator_id]": acct["id"], "metadata[creator_name]": acct["name"]},
            idem="acct-" + acct["id"])
        if err or not data or not data.get("id"):
            return {"error": "stripe_failed", "message": "Stripe could not start the setup: %s" % err}, 502
        acct["stripe_account"] = data["id"]
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE credit_account SET stripe_account=? WHERE id=?", (data["id"], acct["id"]))
            _ctx["conn"].commit()
        _seal("creator_bank_link", "creator=%s" % acct["id"], {"creator_id": acct["id"]})
    link, err = _stripe("POST", "account_links", {
        "account": acct["stripe_account"], "type": "account_onboarding",
        "refresh_url": SITE + "/earn?retry=1", "return_url": SITE + "/earn?connected=1"})
    if err or not link or not link.get("url"):
        return {"error": "stripe_failed", "message": "Stripe could not open the setup page: %s" % err}, 502
    return {"url": link["url"]}, 200


def c_creator_dashboard(q, body):
    acct = _account(_key_from(q, body))
    if not acct:
        return {"error": "bad_key", "message": "That key was not recognised."}, 403
    if not acct["stripe_account"]:
        return {"error": "no_bank", "message": "Set up payouts first."}, 409
    data, err = _stripe("POST", "accounts/%s/login_links" % acct["stripe_account"])
    if err or not data or not data.get("url"):
        return {"error": "stripe_failed", "message": "Finish setting up payouts first, then this opens."}, 409
    return {"url": data["url"]}, 200


def c_creator_withdraw(q, body):
    acct = _account(_key_from(q, body))
    if not acct:
        return {"error": "bad_key", "message": "That key was not recognised."}, 403
    if not _stripe_key():
        return {"error": "payouts_not_switched_on", "message": "Payouts are not switched on yet."}, 503
    acct = _refresh_stripe(acct)
    if not acct["payouts_enabled"]:
        return {"error": "bank_not_ready",
                "message": "Finish setting up payouts first. Stripe needs to check the bank details."}, 409
    minimum = _min_withdraw()
    pid = "po_" + secrets.token_hex(10)
    now = time.time()
    with _ctx["lock"]:
        c = _ctx["conn"]
        row = c.execute("SELECT balance FROM credit_creator WHERE name=?", (acct["name"],)).fetchone()
        pence = row[0] if row else 0
        if pence < minimum:
            return {"error": "below_minimum", "balance_pence": pence, "min_withdraw_pence": minimum,
                    "message": "You can withdraw once you have %s." % _gbp(minimum)}, 400
        cur = c.execute("UPDATE credit_creator SET balance=balance-? WHERE name=? AND balance=?",
                        (pence, acct["name"], pence))
        if cur.rowcount != 1:
            return {"error": "busy", "message": "Your balance just changed. Try again."}, 409
        c.execute("INSERT INTO credit_payout(id,account,pence,status,at) VALUES(?,?,?,?,?)",
                  (pid, acct["id"], pence, "sending", now))
        c.commit()

    tr, err = _stripe("POST", "transfers", {
        "amount": str(pence), "currency": "gbp", "destination": acct["stripe_account"],
        "description": "Monop Studio earnings for %s" % acct["name"],
        "metadata[payout_id]": pid, "metadata[creator_id]": acct["id"]}, idem="payout-" + pid)

    if err or not tr or not tr.get("id"):
        with _ctx["lock"]:
            c = _ctx["conn"]
            c.execute("UPDATE credit_creator SET balance=balance+? WHERE name=?", (pence, acct["name"]))
            c.execute("UPDATE credit_payout SET status='failed',error=? WHERE id=?", (str(err)[:200], pid))
            c.commit()
        try:
            h, b = _seal("creator_payout_failed", "payout=%s;creator=%s;pence=%d" % (pid, acct["id"], pence),
                         {"payout_id": pid, "pence": pence, "status": "failed"})
            with _ctx["lock"]:
                _ctx["conn"].execute("UPDATE credit_payout SET audit_hash=?,block_index=? WHERE id=?", (h, b, pid))
                _ctx["conn"].commit()
        except Exception:
            pass
        msg = "The payout did not go through, so your full balance is back on your account."
        if "insufficient" in str(err).lower():
            msg += " Card payments take a few days to clear before they can be paid out. Try again in a few days."
        return {"paid": False, "error": "transfer_failed", "message": msg}, 502

    h, b = _seal("creator_payout", "payout=%s;creator=%s;pence=%d" % (pid, acct["id"], pence),
                 {"payout_id": pid, "creator_id": acct["id"], "pence": pence, "status": "sent"})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_payout SET status='sent',stripe_transfer=?,audit_hash=?,block_index=? "
                             "WHERE id=?", (tr["id"], h, b, pid))
        _ctx["conn"].commit()
    return {"paid": True, "pence": pence, "payout_id": pid, "sealed_in_chain": h, "block_index": b,
            "verify": "https://sebbi.pro/x/walk/block?index=%s" % b,
            "message": "%s is on its way to your bank. Stripe usually pays it in within a few working days."
                       % _gbp(pence)}, 200


def _gbp(p):
    return "\u00a3%d.%02d" % (p // 100, p % 100)


CMDS = {"hello": c_hello, "check": c_check, "unlock": c_unlock, "topup": c_topup,
        "grant": c_grant, "earnings": c_earnings,
        "creator/join": c_creator_join, "creator/me": c_creator_me, "creator/connect": c_creator_connect,
        "creator/dashboard": c_creator_dashboard, "creator/withdraw": c_creator_withdraw}


# ---------------------------------------------------------------- transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


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


def _run(h, method):
    u = urllib.parse.urlparse(h.path)
    name = u.path[3:].strip("/").lower()
    if name not in CMDS and name != "stripe":
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/credits/status once"}, 503)
        return True
    _setup()

    raw = b""
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
            raw = h.rfile.read(n) if n else b""
        except Exception:
            raw = b""

    if name == "stripe":
        if method != "POST":
            _send(h, {"endpoint": "stripe webhook", "ready": bool(_webhook_secret())}, 200)
            return True
        try:
            out, code = c_stripe(raw, h.headers)
        except Exception as e:
            out, code = {"error": "failed", "detail": str(e)[:160]}, 500
        _send(h, out, code)
        return True

    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if raw:
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}
    try:
        out, code = CMDS[name](q, body)
    except Exception as e:
        out, code = {"error": "failed", "detail": str(e)[:160]}, 500
    _send(h, out, code)
    return True


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
    if getattr(cls, "_credits_patched", False):
        _patched = True
        return True
    og, op = cls.do_GET, getattr(cls, "do_POST", None)
    oo = getattr(cls, "do_OPTIONS", None)

    def do_GET(self):
        if self.path.startswith("/c/") and _run(self, "GET"):
            return
        return og(self)

    def do_POST(self):
        if self.path.startswith("/c/") and _run(self, "POST"):
            return
        return op(self) if op else None

    def do_OPTIONS(self):
        if self.path.startswith("/c/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return oo(self) if oo else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls.do_OPTIONS = do_OPTIONS
    cls._credits_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    counts = {}
    if "conn" in _ctx:
        with _ctx["lock"]:
            c = _ctx["conn"]
            counts = {"viewers": c.execute("SELECT COUNT(*) FROM credit_viewer").fetchone()[0],
                      "paid_views": c.execute("SELECT COUNT(*) FROM credit_unlock").fetchone()[0],
                      "creators": c.execute("SELECT COUNT(*) FROM credit_creator").fetchone()[0],
                      "creator_balances_pence": c.execute("SELECT COALESCE(SUM(balance),0) FROM credit_creator").fetchone()[0],
                      "card_payments": c.execute("SELECT COUNT(*) FROM credit_payment WHERE status='credited'").fetchone()[0],
                      "card_pence": c.execute("SELECT COALESCE(SUM(pence),0) FROM credit_payment WHERE status='credited'").fetchone()[0],
                      "unmatched_payments": c.execute("SELECT COUNT(*) FROM credit_payment WHERE status='unmatched'").fetchone()[0],
                      "creator_accounts": c.execute("SELECT COUNT(*) FROM credit_account").fetchone()[0],
                      "creators_bank_ready": c.execute("SELECT COUNT(*) FROM credit_account WHERE payouts_enabled=1").fetchone()[0],
                      "payouts_sent": c.execute("SELECT COUNT(*) FROM credit_payout WHERE status='sent'").fetchone()[0],
                      "payouts_sent_pence": c.execute("SELECT COALESCE(SUM(pence),0) FROM credit_payout WHERE status='sent'").fetchone()[0]}
    return {"module": "credits", "version": VERSION, "armed": armed,
            "test_mode": TEST_MODE, "card_topups_ready": bool(_checkout_url(500)),
            "webhook_ready": bool(_webhook_secret()), "manual_grant_ready": bool(_admin_key()),
            "creator_payouts_ready": bool(_stripe_key()), "min_withdraw_pence": _min_withdraw(),
            "creator_share": CREATOR_SHARE, "counts": counts,
            "endpoints": ["/c/hello", "/c/check", "/c/unlock", "/c/topup", "/c/stripe",
                          "/c/grant", "/c/earnings", "/c/creator/join", "/c/creator/me",
                          "/c/creator/connect", "/c/creator/dashboard", "/c/creator/withdraw"]}, 200
