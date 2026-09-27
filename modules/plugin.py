"""
modules/plugin.py  v2.0.2
The public proof log: legacy systems send sebbi.pro the SHA-256 of a state
change, and get back a receipt proving that hash is in an append-only log.

  * An RFC 6962 Merkle tree (the Certificate Transparency construction):
        leaf hash  = SHA-256(0x00 || entry)      entry = the 32-byte state hash
        node hash  = SHA-256(0x01 || left || right)
    so any receipt can be checked by anyone, with any RFC 6962 verifier,
    without trusting this server.
  * Receipts come back straight away: leaf index, tree size, root and the
    inclusion (audit) path.
  * Tree heads are sealed into the sebbi.pro chain on a schedule (every 60s or
    every 1,000 leaves, whichever comes first). That chain is walkable at
    /x/walk and its tip is timestamped in Bitcoin with OpenTimestamps by the
    existing anchor, so a leaf becomes Bitcoin-anchored once a confirmed
    anchored tip is at or after the block that sealed its tree head.
  * Hash-only. No payloads, labels or customer data are sent or stored.
  * Idempotent: the client sends its own id with each hash, so a retry after a
    lost response returns the original leaf instead of adding a duplicate.

Routes (clean /p/ prefix, armed by /x/plugin/status):

    POST /p/submit        {"items":[{"hash":"<64 hex>","cid":"<client id>"}]}
                          or {"hash":"<64 hex>"}      needs an API key
    GET  /p/receipt?leaf=N        receipt against the sealed tree head
    GET  /p/proof?leaf=N&size=M   inclusion path at tree size M
    GET  /p/consistency?first=M&second=N   RFC 6962 consistency proof
    GET  /p/sth                   latest sealed tree head + current size
    GET  /p/find?hash=<64 hex>    leaf indexes holding that entry hash
    GET  /p/                      what this log is and how to check it

The customer journey (2.0.0), reached from the "plug in" bubble on the homepage:

    GET  /plugin              the product page: price, sign-up, set-up for Python,
                              JavaScript or any language, account, pricing,
                              receipt checker
    POST /p/signup            {name,email,org} -> a new key on the page and by email
                              (free 90 days; an existing email gets its key re-sent
                              to that inbox only)
    POST /p/account           {key} -> devices this month, bill, trial days, records
    POST /p/pay               {key} -> Stripe checkout for the real device count, or
                              the Stripe billing page for customers already paying
    GET  /p/sebbi_adapter.py  the Python adapter download

Keys are ordinary sebbi.pro keys (server.py's create_key, product "aileash"), so
the trial, the 50p device meter, the Stripe webhook and the 6-hourly quantity
sync all apply exactly as for the engine.

Billing (1.4.0): the same meter as the engine - 50p per device per month.
Each fingerprint can say which device it is about (a phone, terminal, till,
car...), sent as a one-way hash. Every distinct device seen on the key in a
calendar month counts once, through server.py's own record_device(), so a
customer running one central server for 20 million phones is billed for 20
million devices. Fingerprints with no device named count the installation
that sent them. Free for the key's 90-day trial. When a key's trial ends unpaid, /p/submit
answers 402 with the same Stripe checkout the engine gives (server.py's own
trial_checkout, quantity = real devices). Receipts, proofs and every GET route
stay free for good; the client keeps queuing and sends once paid.

The API key goes in the X-Sebbi-Key header (or "key" in the body). Set
ADAPTER_OPEN=1 in Railway to accept submissions without a key (not advised).

Size: kept well under 100,000 characters (the page and the adapter download are
stored compressed), because longer files get cut off when pasted into GitHub.

Loading: the live server loads modules through modules/router.py and calls
handle(). ALIASES and register(MODULE_MAP) are also provided so a loader that
maps modules by name (e.g. brain.py) can pick it up under "adapter",
"sidecar" or "anchor".

Assumes one server process (as on Railway today). If a second process ever
writes the same database, appends detect it and reload before continuing.
"""

import base64
import hashlib
import zlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse

VERSION = "2.0.2"
ALIASES = ["adapter", "sidecar", "anchor"]
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "sth"), ("GET", "proof"),
          ("GET", "receipt"), ("GET", "consistency"), ("GET", "find")}

KEY = "public-proof-adapter"
SITE = "https://sebbi.pro"
MAX_ITEMS = 500
MAX_BODY = 262144
CHECKPOINT_SECONDS = max(10, int(os.environ.get("ADAPTER_CHECKPOINT_SECONDS", "60") or 60))
CHECKPOINT_EVERY = max(1, int(os.environ.get("ADAPTER_CHECKPOINT_EVERY", "1000") or 1000))
OPEN = os.environ.get("ADAPTER_OPEN", "0") == "1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SPEC = ("RFC 6962 Merkle tree, SHA-256. leaf_hash = SHA256(0x00 || entry); "
        "node = SHA256(0x01 || left || right); entry = the 32 raw bytes of the submitted hash.")

_PAGE_B64 = (
    "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"
)
_ADAPTER_B64 = (
    "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"
)


def _d(b):
    return zlib.decompress(base64.b64decode("".join(b.split())))


_FILES = {
    "/plugin": (_d(_PAGE_B64), "text/html; charset=utf-8", None),
    "/p/sebbi_adapter.py": (_d(_ADAPTER_B64), "text/x-python; charset=utf-8", "sebbi_adapter.py"),
}

_ctx = {}
_ready = False
_patched = False
_loaded = False
_leaves = []            # leaf hashes (bytes), index = leaf index
_cache = {}             # (start, size) -> hash, for complete power-of-two subtrees
_tree_lock = threading.Lock()
_cp_lock = threading.Lock()
_loop_started = False


# ---------------------------------------------------------------- RFC 6962

def _h(b):
    return hashlib.sha256(b).digest()


def _leaf_hash(entry):
    return _h(b"\x00" + entry)


def _node(left, right):
    return _h(b"\x01" + left + right)


def _split(n):
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(start, n):
    """Merkle Tree Hash of leaves[start:start+n]."""
    if n == 0:
        return _h(b"")
    if n == 1:
        return _leaves[start]
    full = n >= 16 and (n & (n - 1)) == 0
    if full:
        hit = _cache.get((start, n))
        if hit is not None:
            return hit
    k = _split(n)
    out = _node(_mth(start, k), _mth(start + k, n - k))
    if full:
        _cache[(start, n)] = out
    return out


def _path(m, start, n):
    """Audit path for leaf m within leaves[start:start+n]."""
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, start, k) + [_mth(start + k, n - k)]
    return _path(m - k, start + k, n - k) + [_mth(start, k)]


def _subproof(m, start, n, b):
    if m == n:
        return [] if b else [_mth(start, n)]
    k = _split(n)
    if m <= k:
        return _subproof(m, start, k, b) + [_mth(start + k, n - k)]
    return _subproof(m - k, start + k, n - k, False) + [_mth(start, k)]


def _consistency(m, n):
    if m <= 0 or m >= n:
        return []
    return _subproof(m, 0, n, True)


# ---------------------------------------------------------------- storage

def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS ppa_leaf(idx INTEGER PRIMARY KEY,entry_hash TEXT NOT NULL,"
                  "leaf_hash TEXT NOT NULL,client TEXT,cid TEXT,ts REAL,UNIQUE(client,cid))")
        c.execute("CREATE INDEX IF NOT EXISTS ppa_leaf_entry ON ppa_leaf(entry_hash)")
        c.execute("CREATE TABLE IF NOT EXISTS ppa_sth(tree_size INTEGER PRIMARY KEY,root TEXT NOT NULL,"
                  "ts REAL,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _reload_locked(c):
    """Rebuild the in-memory tree from the database. Caller holds _ctx['lock']."""
    rows = c.execute("SELECT idx,leaf_hash FROM ppa_leaf ORDER BY idx").fetchall()
    fresh = []
    for i, (idx, lh) in enumerate(rows):
        if idx != i:
            raise RuntimeError("leaf index gap at %d" % i)
        fresh.append(bytes.fromhex(lh))
    _cache.clear()
    _leaves[:] = fresh


def _load():
    global _loaded
    if _loaded:
        return
    with _tree_lock:
        if _loaded:
            return
        with _ctx["lock"]:
            _reload_locked(_ctx["conn"])
        _loaded = True


def _seal(kind, detail, extra):
    ev = {"user_id": "ppa:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "public-proof-adapter", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "adapter_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _sth_rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _latest_sth():
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth ORDER BY tree_size DESC LIMIT 1")
    return _sth_dict(r[0]) if r else None


def _covering_sth(idx):
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth WHERE tree_size>? "
                  "ORDER BY tree_size ASC LIMIT 1", (idx,))
    return _sth_dict(r[0]) if r else None


def _sth_dict(r):
    return {"tree_size": r[0], "root": r[1],
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2] or 0)),
            "audit_hash": r[3], "block_index": r[4],
            "walk": SITE + "/x/walk/block?index=%s" % r[4] if r[4] is not None else None,
            "ts": r[2] or 0}


# ---------------------------------------------------------------- appends and checkpoints

def _append(client, items):
    """items: list of (entry_hex, cid or None). Returns list of (idx, entry_hex, replayed, error)."""
    for attempt in range(3):
        out = []
        with _ctx["lock"]:
            c = _ctx["conn"]
            top = c.execute("SELECT COALESCE(MAX(idx),-1) FROM ppa_leaf").fetchone()[0]
            if top + 1 != len(_leaves):
                _reload_locked(c)
            start_len = len(_leaves)
            try:
                for eh, cid in items:
                    if cid:
                        row = c.execute("SELECT idx,entry_hash FROM ppa_leaf WHERE client=? AND cid=?",
                                        (client, cid)).fetchone()
                        if row:
                            if row[1] != eh:
                                out.append((None, eh, False, "cid_reused_for_a_different_hash"))
                            else:
                                out.append((row[0], eh, True, None))
                            continue
                    idx = len(_leaves)
                    lh = _leaf_hash(bytes.fromhex(eh))
                    c.execute("INSERT INTO ppa_leaf(idx,entry_hash,leaf_hash,client,cid,ts) VALUES(?,?,?,?,?,?)",
                              (idx, eh, lh.hex(), client, cid or None, time.time()))
                    _leaves.append(lh)
                    out.append((idx, eh, False, None))
                c.commit()
                return out
            except sqlite3.IntegrityError:
                c.rollback()
                del _leaves[start_len:]
                _reload_locked(c)
            except Exception:
                c.rollback()
                del _leaves[start_len:]
                raise
    raise RuntimeError("could not append after retries")


def _checkpoint(force=False):
    """Seal the current tree head into the chain if it is due. Never runs twice at once."""
    if "conn" not in _ctx or not _cp_lock.acquire(blocking=False):
        return None
    try:
        _load()
        n = len(_leaves)
        last = _latest_sth()
        last_size = last["tree_size"] if last else 0
        if n == 0 or n == last_size:
            return last
        due = force or (n - last_size) >= CHECKPOINT_EVERY or \
            (time.time() - (last["ts"] if last else 0)) >= CHECKPOINT_SECONDS
        if not due:
            return last
        root = _mth(0, n).hex()
        ah, blk = _seal("tree_head", "size=%d;root=%s" % (n, root),
                        {"tree_size": n, "root": root, "prev_tree_size": last_size,
                         "log": "sebbi public proof log", "spec": "RFC6962-SHA256"})
        with _ctx["lock"]:
            _ctx["conn"].execute("INSERT OR IGNORE INTO ppa_sth(tree_size,root,ts,audit_hash,block_index) "
                                 "VALUES(?,?,?,?,?)", (n, root, time.time(), ah, blk))
            _ctx["conn"].commit()
        return _latest_sth()
    finally:
        _cp_lock.release()


def _loop():
    while True:
        time.sleep(10)
        try:
            _checkpoint()
        except Exception as e:
            print("plugin checkpoint: " + str(e)[:160], flush=True)


def _start_loop():
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, name="ppa-checkpoint", daemon=True).start()


# ---------------------------------------------------------------- receipts

def _anchoring_note(cp):
    if not cp:
        return ("pending: this leaf is covered by the next tree head, sealed into the chain within about "
                "%d seconds. Fetch /p/receipt?leaf=N again after that." % CHECKPOINT_SECONDS)
    return ("tree head sealed in chain block %s. The chain tip is timestamped in Bitcoin via OpenTimestamps; "
            "once a confirmed anchored tip is at or after that block, this leaf is Bitcoin-anchored. "
            "Check: %s/x/ots/latest_confirmed" % (cp["block_index"], SITE))


def _receipt(idx, size=None):
    _load()
    n = len(_leaves)
    if idx < 0 or idx >= n:
        return None
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT entry_hash FROM ppa_leaf WHERE idx=?", (idx,)).fetchone()
    cp = _covering_sth(idx) if size is None else None
    tsize = size if size is not None else (cp["tree_size"] if cp else n)
    tsize = max(idx + 1, min(tsize, n))
    root = _mth(0, tsize).hex()
    rec = {"log": "sebbi.pro public proof log", "spec": SPEC,
           "entry_hash": row[0] if row else None, "leaf_index": idx,
           "leaf_hash": _leaves[idx].hex(), "tree_size": tsize, "root": root,
           "audit_path": [p.hex() for p in _path(idx, 0, tsize)],
           "checkpoint": None, "anchoring": _anchoring_note(cp)}
    if cp:
        c2 = dict(cp)
        c2.pop("ts", None)
        c2["root_matches"] = (cp["root"] == root)
        rec["checkpoint"] = c2
    return rec


# ---------------------------------------------------------------- commands

def _meter(key, devices):
    """Count each distinct device on the key's monthly meter - the engine's own record_device()."""
    key = str(key or "").strip()
    devices = [d for d in dict.fromkeys(devices) if d and CID_RE.match(d)]
    if not key or not devices:
        return None
    rd = _server_fn("record_device")
    n = None
    for d in devices:
        dev_id = "adapter:" + d
        if rd:
            try:
                n = rd(key, dev_id)
                continue
            except Exception:
                pass
        try:
            with _ctx["lock"]:
                c = _ctx["conn"]
                c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                          (key, dev_id, time.time()))
                c.commit()
                n = c.execute("SELECT COUNT(*) FROM device_seen WHERE api_key=?", (key,)).fetchone()[0]
        except Exception:
            try:
                _ctx["conn"].rollback()
            except Exception:
                pass
    return n


TRIAL_DAYS = 90


def _server_fn(name):
    """Borrow a function from the running server (server.py) if it is there."""
    for modname in ("__main__", "server"):
        m = sys.modules.get(modname)
        fn = getattr(m, name, None) if m else None
        if callable(fn):
            return fn
    return None


def _trial_gate(key):
    """None if the key may submit; otherwise the same 402 answer the engine gives at trial end."""
    try:
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT email,is_paid,created,product FROM api_keys WHERE key=?",
                                       (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    email, is_paid, created, product = row
    ts = _server_fn("trial_state")
    in_trial = ts(created, is_paid)[0] if ts else (bool(is_paid) or time.time() - (created or 0) <= TRIAL_DAYS * 86400)
    if in_trial:
        return None
    dc = _server_fn("device_count")
    tc = _server_fn("trial_checkout")
    try:
        devices = dc(key) if dc else None
    except Exception:
        devices = None
    try:
        url = tc(key, email, product or "aileash") if tc else SITE + "/#signup"
    except Exception:
        url = SITE + "/#signup"
    return {"error": "trial_expired",
            "message": "Your 90-day free trial has ended. Your receipts, proofs and queued fingerprints are "
                       "untouched - pay to continue exactly where you left off. The bill is 50p for each real "
                       "device that used your key.",
            "billable_devices": devices, "rate_per_device_gbp": 0.50, "checkout_url": url}


def _client_for(key):
    key = str(key or "").strip()
    if key:
        try:
            with _ctx["lock"]:
                row = _ctx["conn"].execute("SELECT active FROM api_keys WHERE key=?", (key,)).fetchone()
        except Exception:
            row = None
        if row and row[0] in (1, None):
            return "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "open" if OPEN else None


# ---------------------------------------------------------------- sign-up, account, payment

_signups = {}
_signup_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _welcome_html(name, key, trial_ends):
    k = _esc(key)
    return ("<div style='font-family:Arial,sans-serif;max-width:560px;color:#1f2937'>"
            "<h2 style='color:#0b1220'>Your sebbi.pro plug-in key</h2>"
            "<p>Hi " + _esc(name or "there") + ", your key is below. Keep it private.</p>"
            "<p style='font-family:monospace;font-size:15px;background:#f1f5f9;padding:12px;border-radius:8px;"
            "word-break:break-all'>" + k + "</p>"
            "<h3>Plug it in</h3><ol>"
            "<li>Download the adapter: <a href='" + SITE + "/p/sebbi_adapter.py'>" + SITE + "/p/sebbi_adapter.py</a></li>"
            "<li>Set <code>SEBBI_API_KEY=" + k + "</code></li>"
            "<li>Add <code>@anchor_state(\"orders.update\", device=\"handset\")</code> above any function "
            "that changes something important.</li></ol>"
            "<p>Other languages, your account and your bill: <a href='" + SITE + "/plugin'>" + SITE + "/plugin</a></p>"
            "<p><b>Free until " + _esc(trial_ends) + "</b>, then 50p per device per month - every phone, till "
            "or machine you record for, counted once a month.</p>"
            "<p style='color:#64748b;font-size:13px'>Questions: justrightdecorators@gmail.com</p></div>")


def _send_mail(to, name, subject, html):
    fn = _server_fn("send_email")
    if fn:
        threading.Thread(target=fn, args=(to, name or "", subject, html), daemon=True).start()
        return True
    return False


def _trial_end(created):
    return time.strftime("%d %B %Y", time.gmtime((created or time.time()) + TRIAL_DAYS * 86400))


def c_signup(q, body, key, ip=""):
    email = str(body.get("email") or "").strip().lower()
    name = str(body.get("name") or "").strip()[:80]
    org = str(body.get("org") or "").strip()[:120]
    if not EMAIL_RE.match(email):
        return {"error": "invalid_email", "message": "Please enter a valid email address."}, 400
    now = time.time()
    with _signup_lock:
        hits = [t for t in _signups.get(ip, []) if now - t < 3600]
        if len(hits) >= 5:
            return {"error": "slow_down", "message": "Too many sign-ups from here. Try again in an hour."}, 429
        hits.append(now)
        _signups[ip] = hits
    create = _server_fn("create_key")
    if not create:
        return {"error": "unavailable", "message": "Sign-up isn't available just now."}, 503
    new_key, err = create(email, "", name, org, "plugin", "aileash", 1)
    if err == "email_exists":
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT key,name,created FROM api_keys WHERE email=? AND product='aileash'",
                                       (email,)).fetchone()
        if row:
            _send_mail(email, row[1] or name, "Your sebbi.pro key", _welcome_html(row[1] or name, row[0], _trial_end(row[2])))
        return {"error": "email_exists",
                "message": "That email already has a sebbi.pro key. We've emailed it to you - the same key works here."}, 409
    if err or not new_key:
        return {"error": err or "failed", "message": "Couldn't create a key just now."}, 400
    ends = _trial_end(now)
    _send_mail(email, name, "Your sebbi.pro plug-in key", _welcome_html(name, new_key, ends))
    _send_mail("justrightdecorators@gmail.com", "sebbi.pro", "New plug-in sign-up: " + (org or email),
               "<p>New plug-in customer: " + _esc(name) + " &middot; " + _esc(email) + " &middot; " + _esc(org) + "</p>")
    return {"key": new_key, "trial_ends": ends, "rate_per_device_gbp": 0.50}, 200


def _key_row(key):
    key = str(key or "").strip()
    if not key:
        return None
    try:
        with _ctx["lock"]:
            return _ctx["conn"].execute("SELECT email,is_paid,created,product,stripe_customer,active FROM api_keys "
                                        "WHERE key=?", (key,)).fetchone()
    except Exception:
        return None


def _devices_this_month(key):
    m = sys.modules.get("modules.meter") or sys.modules.get("meter")
    if m is not None and hasattr(m, "month_count"):
        try:
            return m.month_count(key)
        except Exception:
            pass
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else 0
    except Exception:
        return 0


def _billable(key):
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else _devices_this_month(key)
    except Exception:
        return _devices_this_month(key)


def c_account(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    ts = _server_fn("trial_state")
    in_trial, left = ts(created, is_paid) if ts else (time.time() - (created or 0) <= TRIAL_DAYS * 86400,
                                                       max(0, TRIAL_DAYS - int((time.time() - (created or 0)) // 86400)))
    billable = _billable(key)
    client = "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    rows = _sth_rows("SELECT COUNT(*) FROM ppa_leaf WHERE client=?", (client,))
    return {"email_hint": (email[:2] + "***" + email[email.find("@"):]) if email and "@" in email else "",
            "paid": bool(is_paid), "in_trial": bool(in_trial) and not is_paid,
            "trial_days_left": None if is_paid else left, "trial_ends": _trial_end(created),
            "devices_this_month": _devices_this_month(key), "billable_devices": billable,
            "monthly_bill_gbp": round(billable * 0.50, 2), "rate_per_device_gbp": 0.50,
            "records_logged": rows[0][0] if rows else 0, "active": bool(active)}, 200


def c_pay(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    if is_paid and cust:
        call = _server_fn("stripe_call")
        r = call("POST", "/billing_portal/sessions", {"customer": cust, "return_url": SITE + "/plugin#account"}) if call else None
        if r and r.get("url"):
            return {"url": r["url"]}, 200
        return {"error": "portal_unavailable", "message": "Your account is paid. To change billing, email "
                                                         "justrightdecorators@gmail.com."}, 200
    tc = _server_fn("trial_checkout")
    if not tc:
        return {"error": "unavailable", "message": "Payments aren't available just now."}, 503
    try:
        url = tc(key, email, product or "aileash")
    except Exception:
        url = None
    if not url or "stripe.com" not in url:
        return {"error": "unavailable", "message": "Payments aren't available just now - try again shortly."}, 503
    return {"url": url}, 200


def c_submit(q, body, key):
    client = _client_for(key)
    if not client:
        return {"error": "api_key_required",
                "message": "Send your sebbi.pro API key in the X-Sebbi-Key header."}, 401
    if client != "open":
        gate = _trial_gate(str(key).strip())
        if gate:
            return gate, 402
    raw = body.get("items")
    if raw is None and body.get("hashes") is not None:
        raw = [{"hash": h} for h in body.get("hashes") or []]
    if raw is None and body.get("hash") is not None:
        raw = [{"hash": body.get("hash"), "cid": body.get("cid")}]
    if not isinstance(raw, list) or not raw:
        return {"error": "nothing_to_submit", "message": 'Send {"items":[{"hash":"<64 hex>","cid":"..."}]}'}, 400
    if len(raw) > MAX_ITEMS:
        return {"error": "too_many", "max_items": MAX_ITEMS}, 413
    items, bad, devs = [], [], []
    install = str(body.get("device") or "").strip()
    for i, it in enumerate(raw):
        it = it if isinstance(it, dict) else {"hash": it}
        h = str(it.get("hash") or "").strip().lower()
        cid = str(it.get("cid") or "").strip() or None
        dev = str(it.get("device") or "").strip() or install
        if not HEX64.match(h):
            bad.append({"position": i, "error": "hash must be 64 hex characters (SHA-256)"})
        elif cid and not CID_RE.match(cid):
            bad.append({"position": i, "error": "cid must be 1-80 letters, numbers, _ . : -"})
        elif dev and not CID_RE.match(dev):
            bad.append({"position": i, "error": "device must be 1-80 letters, numbers, _ . : -"})
        else:
            items.append((h, cid))
            devs.append(dev)
    if bad:
        return {"error": "bad_items", "items": bad}, 400
    _load()
    devices = _meter(key, devs) if client != "open" else None
    placed = _append(client, items)
    n = len(_leaves)
    last = _latest_sth()
    if n - (last["tree_size"] if last else 0) >= CHECKPOINT_EVERY:
        threading.Thread(target=_checkpoint, daemon=True).start()
    receipts = []
    for (idx, eh, replayed, err), (_, cid) in zip(placed, items):
        if err:
            receipts.append({"cid": cid, "entry_hash": eh, "error": err})
            continue
        r = _receipt(idx, size=n)
        r["cid"] = cid
        r["replayed"] = replayed
        r["anchoring"] = _anchoring_note(None)
        receipts.append(r)
    return {"accepted": sum(1 for r in receipts if "error" not in r), "tree_size": n,
            "devices_this_month": devices,
            "root": _mth(0, n).hex(), "receipts": receipts}, 200


def _int(q, name, default=None):
    try:
        return int(str(q.get(name, default)))
    except (TypeError, ValueError):
        return None


def c_receipt(q, body, key):
    idx = _int(q, "leaf")
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx)
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_proof(q, body, key):
    idx, size = _int(q, "leaf"), _int(q, "size", 0)
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx, size=size or len(_leaves))
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_consistency(q, body, key):
    _load()
    m, n = _int(q, "first"), _int(q, "second", len(_leaves))
    if m is None or n is None or m < 1 or m > n or n > len(_leaves):
        return {"error": "need 1 <= first <= second <= tree size", "tree_size": len(_leaves)}, 400
    return {"first": m, "second": n, "first_root": _mth(0, m).hex(), "second_root": _mth(0, n).hex(),
            "proof": [p.hex() for p in _consistency(m, n)], "spec": SPEC}, 200


def c_sth(q, body, key):
    _load()
    last = _latest_sth()
    if last:
        last.pop("ts", None)
    return {"tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "spec": SPEC}, 200


def c_find(q, body, key):
    h = str(q.get("hash") or "").strip().lower()
    if not HEX64.match(h):
        return {"error": "hash must be 64 hex characters"}, 400
    rows = _sth_rows("SELECT idx FROM ppa_leaf WHERE entry_hash=? ORDER BY idx LIMIT 50", (h,))
    return {"entry_hash": h, "leaf_indexes": [r[0] for r in rows]}, 200


def c_index(q, body, key):
    return {"log": "sebbi.pro public proof log", "version": VERSION, "spec": SPEC,
            "submit": "POST " + SITE + "/p/submit with X-Sebbi-Key",
            "check": ["GET " + SITE + "/p/receipt?leaf=N", "GET " + SITE + "/p/consistency?first=M&second=N",
                      "GET " + SITE + "/p/sth"],
            "hash_only": True}, 200


GETS = {"receipt": c_receipt, "proof": c_proof, "consistency": c_consistency, "sth": c_sth,
        "find": c_find, "": c_index}
POSTS = {"submit": c_submit, "signup": c_signup, "account": c_account, "pay": c_pay}


# ---------------------------------------------------------------- transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _run(h, method):
    u = urllib.parse.urlparse(h.path)
    name = u.path[3:].strip("/").lower()
    table = GETS if method == "GET" else POSTS
    if name not in table:
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/plugin/status once"}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            _send(h, {"error": "body_too_large", "max_bytes": MAX_BODY}, 413)
            return True
        try:
            body = json.loads(h.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if not isinstance(body, dict):
                body = {}
        except Exception:
            _send(h, {"error": "bad_json"}, 400)
            return True
    key = h.headers.get("X-Sebbi-Key") or body.get("key") or q.get("key")
    try:
        if name == "signup":
            ip = (h.headers.get("X-Forwarded-For") or h.client_address[0] or "").split(",")[0].strip()
            out, code = c_signup(q, body, key, ip)
        else:
            out, code = table[name](q, body, key)
    except Exception as e:
        out, code = {"error": "failed", "detail": str(e)[:160]}, 500
    _send(h, out, code)
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
        _load()
        _start_loop()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_ppa_patched", False):
        _patched = True
        return True
    og, op, oo = cls.do_GET, getattr(cls, "do_POST", None), getattr(cls, "do_OPTIONS", None)

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype, fname = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if fname:
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return
        if (self.path == "/p" or self.path.startswith("/p/")) and _run(self, "GET"):
            return
        return og(self)

    def do_POST(self):
        if self.path.startswith("/p/") and _run(self, "POST"):
            return
        return op(self) if op else None

    def do_OPTIONS(self):
        if self.path.startswith("/p/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return oo(self) if oo else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls.do_OPTIONS = do_OPTIONS
    cls._ppa_patched = True
    _patched = True
    return True


def _flat(d):
    if not isinstance(d, dict):
        return {}
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in d.items()}


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    action = (action or "status").strip("/").lower()
    data = _flat(data)
    if "conn" in _ctx and action in POSTS and method == "POST":
        return POSTS[action](data, data, api_key or data.get("key"))
    if "conn" in _ctx and action in GETS and action not in ("",):
        return GETS[action](data, data, api_key)
    last = _latest_sth() if "conn" in _ctx else None
    if last:
        last.pop("ts", None)
    return {"module": "plugin", "version": VERSION, "armed": armed,
            "aliases": ALIASES, "tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "checkpoint_every_leaves": CHECKPOINT_EVERY,
            "open_submissions": OPEN, "spec": SPEC,
            "pages": sorted(_FILES.keys()),
            "endpoints": ["POST /p/submit", "/p/receipt", "/p/proof", "/p/consistency", "/p/sth", "/p/find"]}, 200


def register(MODULE_MAP):
    """For name-based loaders: map this module under its own name and its aliases."""
    mod = sys.modules[__name__]
    for name in ["plugin"] + ALIASES:
        MODULE_MAP.setdefault(name, mod)
    return MODULE_MAP
