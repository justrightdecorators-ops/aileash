"""
modules/notary.py  v1.0.0  -  Bitcoin Notary, Forever Proofs, Human Keys in Bitcoin

    Arm:       https://sebbi.pro/x/arm/status
    Notary:    https://sebbi.pro/bitcoin   (/notary is the existing profile notary, left alone)
    Receipt:   https://sebbi.pro/n/<code>
    Forever:   https://sebbi.pro/forever
    Verifier:  https://sebbi.pro/forever-verify.py

THREE THINGS, ONE ENGINE
------------------------
1. THE BITCOIN NOTARY. Anyone - a person, a company, another AI governance
   tool, an auditor - sends a SHA-256 fingerprint and gets back a receipt.
   Fingerprints are gathered into a Merkle tree every few minutes and the
   tree's root is committed to Bitcoin through the public OpenTimestamps
   calendars. Thousands of fingerprints share one Bitcoin commitment, so it
   costs nothing to run and is free to use. Files are fingerprinted in the
   visitor's browser; only the 64-character fingerprint is ever sent.

2. FOREVER PROOFS. Every block on the sebbi.pro chain is included in an
   hourly checkpoint: the RFC 6962 Merkle root over every chain hash in
   order (the same root /x/consistency/root serves), committed to Bitcoin.
   A Forever Proof is a small JSON file - fingerprint, Merkle path, root and
   the OpenTimestamps proof - that anyone can check against the Bitcoin
   blockchain with no help from sebbi.pro, in their browser at /forever or
   with the one-file verifier /forever-verify.py. If sebbi.pro disappeared
   the proofs would still check.

3. HUMAN KEYS IN BITCOIN. Every Human Keys proof (code, text fingerprint,
   verdict, time) joins the next Bitcoin batch automatically, and its check
   page shows the Bitcoin block once confirmed.

THE CHAIN IS NEVER WRITTEN TO
-----------------------------
This module only READS audit_log. It never calls seal(), never inserts,
updates or deletes a chain row, and never touches anchor.py, ots.py or their
files. Its own records live in three tables of its own (notary_leaf,
notary_batch, notary_usage) and its Bitcoin proofs are stored inside
notary_batch, not in the anchor folder.

ROUTES  (/x/notary/<action>)
------
  GET  status, spec, receipt?code=, lookup?digest=, bundle?code=|block=,
       hk?code=, checkpoints, ots?batch=                         public
  POST stamp {digests:[...]|digest, label}                     public (API key = higher limit)
  POST verify {bundle}                                          public
  POST run                                                      API key - run the worker now
"""

import base64
import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

try:
    import forever_verify as FV
except Exception:  # pragma: no cover - the file sits next to server.py
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import forever_verify as FV

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "receipt"), ("GET", "lookup"), ("GET", "bundle"),
          ("GET", "hk"), ("GET", "checkpoints"), ("GET", "ots"), ("POST", "stamp"), ("POST", "verify"),
          ("GET", "")}


def _env_list(name, default):
    v = os.environ.get(name, "").strip()
    return [x.strip().rstrip("/") for x in v.split(",") if x.strip()] if v else list(default)


SUBMIT_CALENDARS = _env_list("NOTARY_CALENDARS", [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
])
UPGRADE_CALENDARS = set(_env_list("NOTARY_UPGRADE_CALENDARS", [
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
    "https://btc.calendar.catallaxy.com",
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
])) | set(SUBMIT_CALENDARS)
EXPLORERS = _env_list("NOTARY_EXPLORERS", FV.EXPLORERS)

AUTO = os.environ.get("NOTARY_AUTO", "1") == "1"
TICK = int(os.environ.get("NOTARY_TICK", "30"))
BATCH_INTERVAL = int(os.environ.get("NOTARY_BATCH_INTERVAL", "600"))
CHAIN_INTERVAL = int(os.environ.get("NOTARY_CHAIN_INTERVAL", "3600"))
UPGRADE_INTERVAL = int(os.environ.get("NOTARY_UPGRADE_INTERVAL", "1800"))
UPGRADE_MIN_AGE = int(os.environ.get("NOTARY_UPGRADE_MIN_AGE", "3600"))
CAL_TIMEOUT = 15
CAL_PAUSE = float(os.environ.get("NOTARY_CAL_PAUSE", "0.4"))

MAX_PER_REQUEST = 1000
DAILY_PUBLIC = 500
DAILY_KEYED = 100000
MAX_BATCH = 100000
MAX_CHAIN = 2000000

HEX64 = re.compile(r"^[0-9a-f]{64}$")
NT_RE = re.compile(r"^NT-[A-Z2-9]{4}-[A-Z2-9]{4}$")
HK_RE = re.compile(r"^HK-[A-Z2-9]{4}-[A-Z2-9]{4}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
SITE = "https://sebbi.pro"

_state = {"ready": False, "pages": False, "inject": False, "worker": False,
          "last_batch": None, "last_chain": None, "last_upgrade": None, "next_batch_at": None,
          "last_error": None, "injected": 0}
_lock = threading.Lock()
_work_lock = threading.Lock()
_EPHEMERAL = secrets.token_bytes(32)
_batch_cache = {}
_chain_cache = {"size": -1, "lh": []}
_cache_lock = threading.Lock()


# ---------------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------------

def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _secret():
    s = os.environ.get("LICENCE_SECRET") or ""
    return s.encode() if s else _EPHEMERAL


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _db(sql, args=(), one=False, many=False, write=False):
    s = _srv()
    with s._db_lock:
        if many:
            s._conn.executemany(sql, args)
            s._conn.commit()
            return None
        cur = s._conn.execute(sql, args)
        if write:
            s._conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS notary_leaf("
                  "code TEXT PRIMARY KEY, kind TEXT, digest TEXT, leaf TEXT, label TEXT,"
                  "submitted REAL, who TEXT, batch_id INTEGER, leaf_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notary_digest ON notary_leaf(digest)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notary_batch ON notary_leaf(batch_id, leaf_index)")
        c.execute("CREATE TABLE IF NOT EXISTS notary_batch("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, created REAL, size INTEGER, root TEXT,"
                  "chain_size INTEGER, state TEXT, calendars INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0,"
                  "last_try REAL, ots BLOB, btc_height INTEGER, btc_hash TEXT, btc_time INTEGER,"
                  "btc_checked TEXT, confirmed_at REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_notary_batch_kind ON notary_batch(kind, chain_size)")
        c.execute("CREATE TABLE IF NOT EXISTS notary_usage(who TEXT, day TEXT, n INTEGER, PRIMARY KEY(who, day))")
        c.commit()


def _caller_ip():
    """The router does not hand modules the request, so find it on the stack."""
    f = inspect.currentframe()
    try:
        for _ in range(12):
            f = f.f_back
            if f is None:
                break
            h = f.f_locals.get("h") or f.f_locals.get("self")
            if h is not None and hasattr(h, "headers") and hasattr(h, "client_address"):
                try:
                    xff = h.headers.get("X-Forwarded-For", "")
                    if xff:
                        return xff.split(",")[0].strip()[:64]
                    return str(h.client_address[0])[:64]
                except Exception:
                    return "unknown"
    finally:
        del f
    return "unknown"


def _original_body(key):
    """The router turns {"a": [x, y]} into {"a": x} when the first value is a list.
    Find the body as it arrived, so a list of fingerprints is never cut to one."""
    f = inspect.currentframe()
    try:
        for _ in range(15):
            f = f.f_back
            if f is None:
                break
            for name in ("body", "data"):
                v = f.f_locals.get(name)
                if isinstance(v, dict) and isinstance(v.get(key), list):
                    return v
    finally:
        del f
    return None


def _who(api_key, ip):
    if api_key:
        return "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:20]
    return "ip:" + hmac.new(_secret(), (ip or "unknown").encode(), hashlib.sha256).hexdigest()[:20]


def _new_code(prefix="NT"):
    raw = secrets.token_bytes(8)
    chars = "".join(ALPHABET[b % len(ALPHABET)] for b in raw)
    return "%s-%s-%s" % (prefix, chars[:4], chars[4:8])


def _clean_label(v):
    t = re.sub(r"[\x00-\x1f\x7f<>]", "", str(v or "")).strip()
    return t[:80] or None


# ---------------------------------------------------------------------------
# taking fingerprints in
# ---------------------------------------------------------------------------

def stamp(digests, label=None, api_key=None, ip=None):
    """Accept fingerprints for the next Bitcoin batch. Returns (payload, status)."""
    if isinstance(digests, str):
        digests = [digests]
    if not isinstance(digests, list) or not digests:
        return {"error": "digests_required",
                "message": "Send {\"digests\": [\"<64 hex SHA-256>\", ...]} or {\"digest\": \"...\"}."}, 400
    if len(digests) > MAX_PER_REQUEST:
        return {"error": "too_many", "limit": MAX_PER_REQUEST}, 413
    clean = []
    for d in digests:
        d = str(d or "").strip().lower()
        if not HEX64.match(d):
            return {"error": "bad_digest", "digest": d[:80],
                    "message": "Each fingerprint must be a SHA-256: 64 hex characters."}, 400
        clean.append(d)
    who = _who(api_key, ip)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    cap = DAILY_KEYED if api_key else DAILY_PUBLIC
    row = _db("SELECT n FROM notary_usage WHERE who=? AND day=?", (who, day), one=True)
    used = row[0] if row else 0
    if used + len(clean) > cap:
        return {"error": "daily_limit", "limit_per_day": cap, "used_today": used,
                "message": "Free daily limit reached. An API key from https://sebbi.pro/connect raises it to %d a day." % DAILY_KEYED}, 429
    label = _clean_label(label)
    now = time.time()
    rows, out = [], []
    for d in clean:
        code = _new_code()
        rows.append((code, "hash", d, FV.notary_leaf(d), label, now, who))
        out.append({"code": code, "digest": d, "receipt": "%s/n/%s" % (SITE, code)})
    s = _srv()
    with s._db_lock:
        s._conn.executemany("INSERT INTO notary_leaf(code,kind,digest,leaf,label,submitted,who) VALUES(?,?,?,?,?,?,?)", rows)
        s._conn.execute("INSERT INTO notary_usage(who,day,n) VALUES(?,?,?) ON CONFLICT(who,day) DO UPDATE SET n=n+?",
                        (who, day, len(clean), len(clean)))
        s._conn.commit()
    nb = _state.get("next_batch_at")
    return {"ok": True, "received": len(out), "receipts": out, "label": label,
            "next_batch_utc": _iso(nb) if nb else None,
            "what_happens": "Your fingerprints join the next Bitcoin batch (every %d minutes). The batch root is "
                            "committed to Bitcoin through OpenTimestamps and confirms in a Bitcoin block, normally "
                            "within a few hours. Each receipt then gives a Forever Proof anyone can check against "
                            "Bitcoin without sebbi.pro." % max(1, BATCH_INTERVAL // 60)}, 200


def _sweep_humankeys(limit=5000):
    """Every Human Keys proof joins the Bitcoin batches. Reads humankeys_proof only."""
    try:
        rows = _db("SELECT code,text_hash,verdict,sealed_at FROM humankeys_proof "
                   "WHERE code NOT IN (SELECT code FROM notary_leaf) LIMIT ?", (limit,))
    except Exception:
        return 0
    add = []
    for code, th, verdict, sealed_at in rows:
        if not code or not th:
            continue
        add.append((code, "humankeys", th, FV.humankeys_leaf(code, th, verdict or "", sealed_at or 0),
                    None, time.time(), "humankeys"))
    if add:
        _db("INSERT OR IGNORE INTO notary_leaf(code,kind,digest,leaf,label,submitted,who) VALUES(?,?,?,?,?,?,?)",
            add, many=True)
    return len(add)


# ---------------------------------------------------------------------------
# batches
# ---------------------------------------------------------------------------

def _make_batch():
    rows = _db("SELECT code, leaf FROM notary_leaf WHERE batch_id IS NULL ORDER BY submitted, rowid LIMIT ?",
               (MAX_BATCH,))
    if not rows:
        return None
    lh = [FV.leaf_hash(r[1]) for r in rows]
    root = FV.merkle_root_of(lh).hex()
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute("INSERT INTO notary_batch(kind,created,size,root,state) VALUES('notary',?,?,?,'new')",
                              (time.time(), len(rows), root))
        bid = cur.lastrowid
        s._conn.executemany("UPDATE notary_leaf SET batch_id=?, leaf_index=? WHERE code=? AND batch_id IS NULL",
                            [(bid, i, r[0]) for i, r in enumerate(rows)])
        s._conn.commit()
    _state["last_batch"] = {"batch": bid, "size": len(rows), "root": root, "utc": _iso(time.time())}
    return bid


def _chain_hashes():
    """Every chain hash in write order, as leaf hashes. Read only."""
    n = _db("SELECT COUNT(*) FROM audit_log", one=True)[0]
    with _cache_lock:
        have = _chain_cache["size"]
        if have == n:
            return _chain_cache["lh"]
    if n > MAX_CHAIN:
        raise RuntimeError("chain holds %d blocks, above the %d cap" % (n, MAX_CHAIN))
    if 0 < have < n:
        # append-only: read just the new blocks
        rows = _db("SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT -1 OFFSET ?", (have,))
        lh = _chain_cache["lh"] + [FV.leaf_hash(str(r[0])) for r in rows]
    else:
        rows = _db("SELECT audit_hash FROM audit_log ORDER BY id ASC")
        lh = [FV.leaf_hash(str(r[0])) for r in rows]
    with _cache_lock:
        _chain_cache["size"] = len(lh)
        _chain_cache["lh"] = lh
    return lh


def _make_chain_checkpoint():
    lh = _chain_hashes()
    n = len(lh)
    if n == 0:
        return None
    last = _db("SELECT MAX(chain_size) FROM notary_batch WHERE kind='chain'", one=True)
    if last and last[0] and last[0] >= n:
        return None
    root = FV.merkle_root_of(lh).hex()
    bid = _db("INSERT INTO notary_batch(kind,created,size,root,chain_size,state) VALUES('chain',?,?,?,?,'new')",
              (time.time(), n, root, n), write=True)
    _state["last_chain"] = {"batch": bid, "chain_size": n, "root": root, "utc": _iso(time.time())}
    return bid


def _http(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"Accept": "application/vnd.opentimestamps.v1",
                                          "User-Agent": "sebbi.pro-notary/" + VERSION})
    with urllib.request.urlopen(req, timeout=CAL_TIMEOUT) as r:
        return r.status, r.read(65536)


def _submit(bid):
    row = _db("SELECT root, attempts FROM notary_batch WHERE id=?", (bid,), one=True)
    if not row:
        return False
    root = bytes.fromhex(row[0])
    ts = FV.Timestamp(root)
    got = 0
    for cal in SUBMIT_CALENDARS:
        try:
            st, raw = _http("POST", cal + "/digest", root)
            if st == 200 and raw:
                ts.merge(FV.Timestamp.from_bytes(raw, root))
                got += 1
        except Exception:
            pass
        time.sleep(CAL_PAUSE)
    if got:
        blob = FV.serialize_detached(root, ts)
        _db("UPDATE notary_batch SET state='pending', calendars=?, ots=?, last_try=?, attempts=attempts+1 WHERE id=?",
            (got, blob, time.time(), bid), write=True)
        return True
    _db("UPDATE notary_batch SET attempts=attempts+1, last_try=? WHERE id=?", (time.time(), bid), write=True)
    return False


def _explorer_check(height, merkle_root):
    agreed, when, bhash = [], None, None
    for base in EXPLORERS:
        try:
            b = FV.block_from_explorer(base, height)
        except Exception:
            continue
        if b["merkle_root"] == merkle_root:
            agreed.append(base)
            when = b.get("time")
            bhash = b.get("hash")
        else:
            return None, None, None, "explorer %s disagrees" % base
    return agreed, when, bhash, None


def _upgrade(bid):
    row = _db("SELECT ots, state, btc_checked FROM notary_batch WHERE id=?", (bid,), one=True)
    if not row or not row[0]:
        return None
    _, digest, ts = FV.parse_detached(bytes(row[0]))
    merged = 0
    if row[1] != "confirmed":
        for node in list(ts.nodes()):
            for tag, payload in list(node.attestations):
                d = FV.describe_attestation(tag, payload)
                if d["kind"] != "pending":
                    continue
                uri = d["calendar"].rstrip("/")
                if uri not in UPGRADE_CALENDARS:
                    continue
                try:
                    st, raw = _http("GET", uri + "/timestamp/" + node.msg.hex())
                    if st == 200 and raw:
                        node.merge(FV.Timestamp.from_bytes(raw, node.msg))
                        merged += 1
                except Exception:
                    pass  # not ready yet is the normal answer
                time.sleep(CAL_PAUSE)
    summ = FV.summarise(ts)
    blob = FV.serialize_detached(digest, ts) if merged else None
    if summ["bitcoin"]:
        b = summ["bitcoin"][0]
        agreed, when, bhash, why = _explorer_check(b["height"], b["merkle_root"])
        if why:
            _state["last_error"] = "batch %d: %s" % (bid, why)
            if blob:
                _db("UPDATE notary_batch SET ots=?, last_try=? WHERE id=?", (blob, time.time(), bid), write=True)
            return "disputed"
        _db("UPDATE notary_batch SET state='confirmed', ots=COALESCE(?, ots), btc_height=?, btc_hash=?, btc_time=?, "
            "btc_checked=?, confirmed_at=COALESCE(confirmed_at, ?), last_try=? WHERE id=?",
            (blob, b["height"], bhash, when, json.dumps(agreed) if agreed else None, time.time(), time.time(), bid),
            write=True)
        with _cache_lock:
            _batch_cache.pop(bid, None)
        return "confirmed"
    if blob:
        _db("UPDATE notary_batch SET ots=?, last_try=? WHERE id=?", (blob, time.time(), bid), write=True)
    else:
        _db("UPDATE notary_batch SET last_try=? WHERE id=?", (time.time(), bid), write=True)
    return "pending"


def run_once(force=False):
    """One pass of the worker: batch, checkpoint, send, upgrade. Never raises."""
    out = {"batched": None, "checkpoint": None, "sent": 0, "upgraded": {}}
    if not _work_lock.acquire(blocking=False):
        return {"busy": True}
    try:
        now = time.time()
        _sweep_humankeys()
        if force or not _state.get("next_batch_at") or now >= _state["next_batch_at"]:
            out["batched"] = _make_batch()
            _state["next_batch_at"] = now + BATCH_INTERVAL
        if force or not _state.get("_next_chain") or now >= _state["_next_chain"]:
            try:
                out["checkpoint"] = _make_chain_checkpoint()
            except Exception as e:
                _state["last_error"] = "checkpoint: %s" % e
            _state["_next_chain"] = now + CHAIN_INTERVAL
        for (bid,) in _db("SELECT id FROM notary_batch WHERE state='new' AND (last_try IS NULL OR last_try < ?) "
                          "ORDER BY id LIMIT 20", (now - (0 if force else 120),)):
            if _submit(bid):
                out["sent"] += 1
        age = 0 if force else UPGRADE_MIN_AGE
        retry = 0 if force else UPGRADE_INTERVAL
        for (bid,) in _db("SELECT id FROM notary_batch WHERE ((state='pending' AND created < ?) OR "
                          "(state='confirmed' AND btc_checked IS NULL)) AND (last_try IS NULL OR last_try < ?) "
                          "ORDER BY id DESC LIMIT 30", (now - age, now - retry)):
            out["upgraded"][bid] = _upgrade(bid)
        _state["last_upgrade"] = {"utc": _iso(time.time()), "result": out["upgraded"]}
    except Exception as e:
        _state["last_error"] = "worker: %s" % str(e)[:200]
        out["error"] = str(e)[:200]
    finally:
        _work_lock.release()
    return out


def _worker():
    time.sleep(min(60, TICK * 2))
    while True:
        run_once()
        time.sleep(TICK)


def _start_worker():
    if _state["worker"] or not AUTO:
        return
    _state["worker"] = True
    if not _state.get("next_batch_at"):
        _state["next_batch_at"] = time.time() + min(BATCH_INTERVAL, 120)
    threading.Thread(target=_worker, name="notary", daemon=True).start()


# ---------------------------------------------------------------------------
# proofs
# ---------------------------------------------------------------------------

def _batch_row(bid):
    r = _db("SELECT id,kind,created,size,root,chain_size,state,calendars,btc_height,btc_hash,btc_time,btc_checked,ots "
            "FROM notary_batch WHERE id=?", (bid,), one=True)
    if not r:
        return None
    return {"id": r[0], "kind": r[1], "created": r[2], "size": r[3], "root": r[4], "chain_size": r[5],
            "state": r[6], "calendars": r[7], "btc_height": r[8], "btc_hash": r[9], "btc_time": r[10],
            "btc_checked": json.loads(r[11]) if r[11] else None, "ots": bytes(r[12]) if r[12] else None}


def _batch_public(b):
    if not b:
        return None
    state = {"new": "sending", "pending": "pending", "confirmed": "confirmed"}.get(b["state"], b["state"])
    out = {"batch": b["id"], "kind": b["kind"], "created_utc": _iso(b["created"]), "size": b["size"],
           "root": b["root"], "state": state, "calendars": b["calendars"]}
    if b["kind"] == "chain":
        out["chain_size"] = b["chain_size"]
    if b["btc_height"]:
        out["bitcoin"] = {"height": b["btc_height"], "block_hash": b["btc_hash"],
                          "block_time_utc": _iso(b["btc_time"]) if b["btc_time"] else None,
                          "checked_with": b["btc_checked"],
                          "explorer": "https://mempool.space/block/%s" % (b["btc_hash"] or b["btc_height"])}
    return out


def _batch_leaves(bid):
    with _cache_lock:
        if bid in _batch_cache:
            return _batch_cache[bid]
    rows = _db("SELECT leaf FROM notary_leaf WHERE batch_id=? ORDER BY leaf_index", (bid,))
    lh = [FV.leaf_hash(r[0]) for r in rows]
    with _cache_lock:
        if len(_batch_cache) > 32:
            _batch_cache.clear()
        _batch_cache[bid] = lh
    return lh


def _bundle(subject, leaf, index, size, path, root, b):
    summ = FV.summarise(FV.parse_detached(b["ots"])[2]) if b and b["ots"] else None
    return {
        "format": "sebbi-forever-proof/1",
        "what": "Proof that this fingerprint existed before a Bitcoin block was mined. Check it with nothing from "
                "sebbi.pro: in your browser at https://sebbi.pro/forever or with https://sebbi.pro/forever-verify.py",
        "issued_utc": _iso(time.time()),
        "subject": subject,
        "leaf": leaf,
        "merkle": {"algorithm": "RFC 6962 SHA-256 (leaf 0x00, node 0x01)", "index": index, "tree_size": size,
                   "path": [p.hex() for p in path], "root": root},
        "bitcoin": {"state": (summ or {}).get("state", "sending"),
                    "heights": [x["height"] for x in (summ or {}).get("bitcoin", [])],
                    "block_time_utc": _iso(b["btc_time"]) if b and b.get("btc_time") else None,
                    "calendars": (summ or {}).get("pending", []),
                    "proof_ots_base64": base64.b64encode(b["ots"]).decode() if b and b["ots"] else None},
        "batch": _batch_public(b),
        "verify": {"in_your_browser": SITE + "/forever",
                   "offline": "python3 forever-verify.py this-file.json",
                   "verifier": SITE + "/forever-verify.py",
                   "with_your_own_node": "python3 forever-verify.py this-file.json --node",
                   "standard_tool": "the proof_ots_base64 field is a standard OpenTimestamps proof of the root"},
    }


def _leaf_record(code):
    r = _db("SELECT code,kind,digest,leaf,label,submitted,batch_id,leaf_index FROM notary_leaf WHERE code=?",
            (code,), one=True)
    if not r:
        return None
    return {"code": r[0], "kind": r[1], "digest": r[2], "leaf": r[3], "label": r[4], "submitted": r[5],
            "batch_id": r[6], "leaf_index": r[7]}


def _subject_for(rec):
    if rec["kind"] == "humankeys":
        parts = rec["leaf"].split("|")
        return {"kind": "humankeys", "code": parts[1], "text_hash": parts[2], "verdict": parts[3],
                "sealed_at": int(parts[4]), "sealed_utc": _iso(int(parts[4])), "check_page": "%s/k/%s" % (SITE, parts[1])}
    return {"kind": "hash", "code": rec["code"], "digest": rec["digest"], "label": rec["label"],
            "submitted_utc": _iso(rec["submitted"]), "receipt": "%s/n/%s" % (SITE, rec["code"])}


def receipt(code, with_bundle=False):
    code = str(code or "").strip().upper()
    if not (NT_RE.match(code) or HK_RE.match(code)):
        return {"error": "bad_code", "message": "A receipt code looks like NT-7Q2M-X9KD (or HK-... for Human Keys)."}, 400
    rec = _leaf_record(code)
    if rec is None and HK_RE.match(code):
        _sweep_humankeys()
        rec = _leaf_record(code)
    if rec is None:
        return {"error": "not_found", "code": code}, 404
    subject = _subject_for(rec)
    out = {"code": code, "subject": subject, "received_utc": _iso(rec["submitted"])}
    if rec["batch_id"] is None:
        nb = _state.get("next_batch_at")
        out.update({"state": "queued", "next_batch_utc": _iso(nb) if nb else None,
                    "message": "Waiting for the next Bitcoin batch."})
        return out, 200
    b = _batch_row(rec["batch_id"])
    out["batch"] = _batch_public(b)
    out["state"] = out["batch"]["state"]
    out["message"] = {"sending": "In a batch, being sent to the Bitcoin calendars.",
                      "pending": "Committed to the Bitcoin calendars. Waiting for its Bitcoin block - normally a few hours.",
                      "confirmed": "In Bitcoin. Anyone can check this against the Bitcoin blockchain, with nothing from sebbi.pro."
                      }.get(out["state"], "")
    out["forever_proof"] = "%s/x/notary/bundle?code=%s" % (SITE, code)
    out["verify"] = "%s/forever?code=%s" % (SITE, code)
    if with_bundle:
        lh = _batch_leaves(b["id"])
        path = FV.inclusion_path(lh, rec["leaf_index"])
        if FV.root_from_path(lh[rec["leaf_index"]], rec["leaf_index"], len(lh), path).hex() != b["root"]:
            return {"error": "batch_mismatch", "message": "This batch no longer rebuilds to its sealed root."}, 500
        return _bundle(subject, rec["leaf"], rec["leaf_index"], len(lh), path, b["root"], b), 200
    return out, 200


def chain_proof(block, api_key=None):
    try:
        block = int(block)
    except (TypeError, ValueError):
        return {"error": "bad_block", "message": "block must be a whole number"}, 400
    r = _db("SELECT id,audit_hash,api_key,event_json,result_json,prev_hash,ts FROM audit_log WHERE id=?", (block,), one=True)
    if not r:
        return {"error": "not_found", "block": block}, 404
    pos = _db("SELECT COUNT(*) FROM audit_log WHERE id<?", (block,), one=True)[0]
    rows = _db("SELECT id FROM notary_batch WHERE kind='chain' AND chain_size>? AND state='confirmed' "
               "ORDER BY chain_size ASC LIMIT 1", (pos,))
    if not rows:
        rows = _db("SELECT id FROM notary_batch WHERE kind='chain' AND chain_size>? ORDER BY chain_size ASC LIMIT 1", (pos,))
    if not rows:
        nc = _state.get("_next_chain")
        return {"state": "queued", "block": block, "audit_hash": r[1],
                "message": "This block joins the next hourly Bitcoin checkpoint.",
                "next_checkpoint_utc": _iso(nc) if nc else None}, 202
    b = _batch_row(rows[0][0])
    lh = _chain_hashes()[:b["chain_size"]]
    if len(lh) != b["chain_size"] or FV.merkle_root_of(lh).hex() != b["root"]:
        return {"error": "chain_mismatch",
                "message": "The chain no longer rebuilds to this checkpoint's root. This should never happen."}, 500
    path = FV.inclusion_path(lh, pos)
    subject = {"kind": "chain_block", "block": block, "position": pos, "audit_hash": r[1],
               "checkpoint_size": b["chain_size"],
               "meaning": "This chain block - and every block before it - existed before the Bitcoin block below.",
               "public_check": "%s/x/consistency/root" % SITE}
    if api_key and r[2] and hmac.compare_digest(str(r[2]), str(api_key)):
        try:
            subject["block_content"] = {"prev_hash": r[5], "ts": r[6], "event": json.loads(r[3]), "result": json.loads(r[4])}
            subject["block_content_note"] = "Yours alone - this key sealed the block. Keep it private. Re-hashing it proves the decision itself."
        except Exception:
            pass
    return _bundle(subject, r[1], pos, len(lh), path, b["root"], b), 200


def hk_status(code):
    code = str(code or "").strip().upper()
    if not HK_RE.match(code):
        return {"error": "bad_code"}, 400
    return receipt(code)


def _checkpoints(limit=20):
    rows = _db("SELECT id FROM notary_batch WHERE kind='chain' ORDER BY id DESC LIMIT ?", (limit,))
    return [_batch_public(_batch_row(r[0])) for r in rows]


def status():
    def cnt(sql, a=()):
        try:
            return _db(sql, a, one=True)[0]
        except Exception:
            return None
    nb = _state.get("next_batch_at")
    return {"module": "notary", "version": VERSION, "armed": _state["pages"],
            "pages": {"notary": SITE + "/bitcoin", "forever": SITE + "/forever", "verifier": SITE + "/forever-verify.py"},
            "fingerprints": cnt("SELECT COUNT(*) FROM notary_leaf WHERE kind='hash'"),
            "human_keys_anchored": cnt("SELECT COUNT(*) FROM notary_leaf WHERE kind='humankeys' AND batch_id IS NOT NULL"),
            "waiting_for_next_batch": cnt("SELECT COUNT(*) FROM notary_leaf WHERE batch_id IS NULL"),
            "batches": cnt("SELECT COUNT(*) FROM notary_batch"),
            "batches_in_bitcoin": cnt("SELECT COUNT(*) FROM notary_batch WHERE state='confirmed'"),
            "chain_checkpoints": cnt("SELECT COUNT(*) FROM notary_batch WHERE kind='chain'"),
            "chain_blocks_in_bitcoin": cnt("SELECT MAX(chain_size) FROM notary_batch WHERE kind='chain' AND state='confirmed'") or 0,
            "latest_bitcoin_block": cnt("SELECT MAX(btc_height) FROM notary_batch WHERE state='confirmed'"),
            "next_batch_utc": _iso(nb) if nb else None,
            "next_batch_in_seconds": max(0, int(nb - time.time())) if nb else None,
            "batch_every_minutes": BATCH_INTERVAL // 60, "checkpoint_every_minutes": CHAIN_INTERVAL // 60,
            "worker": _state["worker"], "ai_connector_tools": bool(_state.get("mcp")), "last_batch": _state["last_batch"], "last_checkpoint": _state["last_chain"],
            "last_upgrade": _state["last_upgrade"], "price": "Free",
            "writes_to_chain": False, "last_error": _state["last_error"]}, 200


def spec():
    return {"module": "notary", "version": VERSION,
            "what": "A free Bitcoin notary for anyone, Forever Proofs for every sebbi.pro chain block, and Human Keys "
                    "proofs timestamped in Bitcoin.",
            "fingerprint": "SHA-256 of the file's bytes, 64 lowercase hex. Only the fingerprint is ever sent.",
            "leaf": {"notary": "sebbi-notary/1|<digest>",
                     "humankeys": "sebbi-humankeys/1|<code>|<text_hash>|<verdict>|<sealed_at unix>",
                     "chain_block": "<audit_hash> (the same leaves /x/consistency/root uses)"},
            "tree": "RFC 6962: leaf = SHA-256(0x00 || leaf), node = SHA-256(0x01 || left || right)",
            "bitcoin": "Each batch root is submitted to the public OpenTimestamps calendars and upgraded once its "
                       "Bitcoin transaction confirms. Confirmations are checked against two block explorers.",
            "forever_proof_format": "sebbi-forever-proof/1 - subject, leaf, merkle {index, tree_size, path, root}, "
                                    "bitcoin {proof_ots_base64}",
            "limits": {"per_request": MAX_PER_REQUEST, "per_day_without_key": DAILY_PUBLIC, "per_day_with_key": DAILY_KEYED},
            "routes": {"stamp": "POST %s/x/notary/stamp {\"digests\": [...], \"label\": \"optional, public\"}" % SITE,
                       "receipt": "GET %s/x/notary/receipt?code=NT-XXXX-XXXX" % SITE,
                       "lookup": "GET %s/x/notary/lookup?digest=<sha256>" % SITE,
                       "bundle": "GET %s/x/notary/bundle?code=NT-XXXX-XXXX | ?block=<chain block>" % SITE,
                       "human_keys": "GET %s/x/notary/hk?code=HK-XXXX-XXXX" % SITE,
                       "checkpoints": "GET %s/x/notary/checkpoints" % SITE,
                       "verify": "POST %s/x/notary/verify {\"bundle\": {...}}" % SITE,
                       "discovery": "%s/.well-known/sebbi-notary.json" % SITE},
            "verifier": SITE + "/forever-verify.py",
            "writes_to_chain": False}, 200


def _discovery():
    return {"name": "sebbi.pro Bitcoin Notary", "version": VERSION,
            "stamp": SITE + "/x/notary/stamp", "receipt": SITE + "/x/notary/receipt?code={code}",
            "lookup": SITE + "/x/notary/lookup?digest={sha256}", "bundle": SITE + "/x/notary/bundle?code={code}",
            "forever_proof_for_chain_block": SITE + "/x/notary/bundle?block={block}",
            "proof_format": "sebbi-forever-proof/1", "hash": "sha256",
            "verifier": SITE + "/forever-verify.py", "verify_page": SITE + "/forever",
            "mcp": SITE + "/mcp", "price": "free", "spec": SITE + "/x/notary/spec"}


# ---------------------------------------------------------------------------
# AI assistants - three tools added to the /mcp connector at runtime.
# modules/mcp.py itself is not edited; if this module fails to arm, the
# connector carries on with its own tools exactly as before.
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {"name": "sebbi_notarize",
     "description": "Timestamp fingerprints (SHA-256, 64 hex) in Bitcoin through sebbi.pro's free notary. Hash the file or "
                    "text yourself and send only the fingerprint. Returns a receipt code and link for each.",
     "inputSchema": {"type": "object", "required": ["digests"],
                     "properties": {"digests": {"type": "array", "items": {"type": "string"}},
                                    "label": {"type": "string", "description": "Optional public label, up to 80 characters"},
                                    "api_key": {"type": "string"}}}},
    {"name": "sebbi_notary_receipt",
     "description": "Where a notary receipt (NT-XXXX-XXXX) or Human Keys code (HK-XXXX-XXXX) stands: queued, sent to "
                    "Bitcoin, or confirmed in a Bitcoin block - and the link to its Forever Proof.",
     "inputSchema": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}}}},
    {"name": "sebbi_forever_proof",
     "description": "A Forever Proof anyone can check against Bitcoin without sebbi.pro: for a notary receipt, a Human "
                    "Keys code, or any block on the sebbi.pro chain. Give code or block.",
     "inputSchema": {"type": "object",
                     "properties": {"code": {"type": "string"}, "block": {"type": "integer"}, "api_key": {"type": "string"}}}},
]
MCP_NOTE = (" To prove a file, text or decision existed at a point in time, hash it and call sebbi_notarize (free, "
            "timestamped in Bitcoin); sebbi_forever_proof gives a proof anyone can check against Bitcoin at "
            "https://sebbi.pro/forever.")


def _install_mcp():
    if _state.get("mcp"):
        return True
    try:
        try:
            from modules import mcp as M
        except Exception:
            import mcp as M
    except Exception as e:
        _state["last_error"] = "mcp: %s" % e
        return False
    if getattr(M, "_notary_tools", False):
        _state["mcp"] = True
        return True
    names = {t["name"] for t in M.TOOLS}
    for t in MCP_TOOLS:
        if t["name"] not in names:
            M.TOOLS.append(t)
    original = M._call

    def _call(name, a, ip, agent):
        if name not in ("sebbi_notarize", "sebbi_notary_receipt", "sebbi_forever_proof"):
            return original(name, a, ip, agent)
        a = a or {}
        key = str(a.get("api_key") or "").strip() or None
        if key and not _srv().get_key(key):
            key = None
        if name == "sebbi_notarize":
            d = a.get("digests") if a.get("digests") is not None else a.get("digest")
            return stamp(d, a.get("label"), key, ip)
        if name == "sebbi_notary_receipt":
            return receipt(a.get("code"))
        if a.get("block") not in (None, ""):
            return chain_proof(a.get("block"), key)
        return receipt(a.get("code"), with_bundle=True)

    M._call = _call
    if isinstance(getattr(M, "INSTRUCTIONS", None), str) and MCP_NOTE not in M.INSTRUCTIONS:
        M.INSTRUCTIONS = M.INSTRUCTIONS + MCP_NOTE
    M._notary_tools = True
    _state["mcp"] = True
    return True


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _send(h, body, ctype, status=200, extra=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store" if ("json" in ctype or "svg" in ctype) else "public, max-age=60")
    h.send_header("Access-Control-Allow-Origin", "*")
    for k, v in (extra or {}).items():
        h.send_header(k, v)
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _badge(code):
    rec = _leaf_record(code) if NT_RE.match(code) or HK_RE.match(code) else None
    b = _batch_row(rec["batch_id"]) if rec and rec["batch_id"] else None
    if b and b["state"] == "confirmed" and b["btc_height"]:
        right, colour = "block %d" % b["btc_height"], "#f7931a"
    elif rec:
        right, colour = "confirming", "#c9a84c"
    else:
        right, colour = "not found", "#9aa0ae"
    left = "In Bitcoin" if b and b["state"] == "confirmed" else "Bitcoin"
    w = 250
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="28" role="img" aria-label="%s %s via sebbi.pro">'
            '<rect width="%d" height="28" rx="5" fill="#0a0f1e"/><rect x="1" y="1" width="%d" height="26" rx="4" fill="none" stroke="%s" stroke-opacity=".7"/>'
            '<circle cx="15" cy="14" r="7" fill="%s"/><text x="15" y="18" fill="#0a0f1e" font-family="Verdana,sans-serif" font-size="10" font-weight="bold" text-anchor="middle">B</text>'
            '<text x="29" y="18" fill="#fff" font-family="Verdana,sans-serif" font-size="11.5" font-weight="bold">%s</text>'
            '<text x="%d" y="18" fill="%s" font-family="Verdana,sans-serif" font-size="10.5" text-anchor="end">%s · sebbi.pro</text></svg>'
            % (w, _esc(left), _esc(right), w, w - 2, colour, colour, _esc(left), w - 10, colour, _esc(right)))


_HEAD = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,500;1,6..72,500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--ink3:#0d1426;--gold:#c9a84c;--gold2:#f0d78a;--btc:#f7931a;--ok:#2fbf71;--ok2:#7fe3b0;--err:#ff8a80;--mut:rgba(255,255,255,.62);--line:rgba(201,168,76,.22);
--sans:'IBM Plex Sans',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:#fff;font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased;padding-bottom:env(safe-area-inset-bottom,0)}
.wrap{max-width:880px;margin:0 auto;padding:0 16px}
.top{border-bottom:1px solid var(--line);padding:14px 0}.top .wrap{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.brand{font-family:var(--mono);font-size:13px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
.top nav a{font-family:var(--mono);font-size:12px;color:var(--mut);text-decoration:none;margin-left:14px;white-space:nowrap}@media(max-width:560px){.top nav a:nth-child(n+3){display:none}}.top nav a:hover{color:var(--gold2)}
.hero{padding:44px 0 10px;position:relative}
.kick{font-family:var(--mono);font-size:12px;color:var(--btc);letter-spacing:.1em;margin-bottom:12px;display:flex;align-items:center;gap:10px}
.kick i{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--btc);box-shadow:0 0 0 0 rgba(247,147,26,.6);animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(247,147,26,.55)}70%{box-shadow:0 0 0 10px rgba(247,147,26,0)}100%{box-shadow:0 0 0 0 rgba(247,147,26,0)}}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(36px,7.4vw,64px);line-height:1.02;margin-bottom:14px;letter-spacing:-.01em}h1 em{color:var(--gold);font-style:italic}
.hero p{color:var(--mut);font-size:17px;max-width:60ch}
.live{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:26px 0 8px}
@media(max-width:620px){.live{grid-template-columns:repeat(2,1fr)}}
.live div{background:var(--ink3);padding:14px 14px 12px}.live b{display:block;font-family:var(--mono);font-size:20px;font-weight:500;color:#fff}.live span{font-size:12px;color:var(--mut)}
.live b.btc{color:var(--btc)}
.card{background:var(--ink2);border:1px solid var(--line);border-radius:12px;padding:20px;margin:18px 0}
.card h2{font-family:var(--serif);font-weight:500;font-size:26px;line-height:1.15;margin-bottom:6px}
.card p.sub{color:var(--mut);font-size:14.5px;margin-bottom:14px}
.drop{display:block;border:1.5px dashed rgba(201,168,76,.45);border-radius:12px;padding:30px 16px;text-align:center;cursor:pointer;transition:background .2s,border-color .2s;background:rgba(201,168,76,.03)}
.drop:hover,.drop.on{background:rgba(201,168,76,.08);border-color:var(--gold)}
.drop b{display:block;font-family:var(--serif);font-weight:500;font-size:22px;margin-bottom:4px}.drop span{color:var(--mut);font-size:13.5px}
textarea{width:100%;min-height:110px;background:var(--ink);border:1px solid var(--line);border-radius:8px;color:#fff;padding:12px;font-family:var(--sans);font-size:15.5px;line-height:1.55;resize:vertical;outline:none}
textarea:focus,input:focus{border-color:var(--gold);outline:none}
input[type=text],input[type=number]{width:100%;background:var(--ink);border:1px solid var(--line);border-radius:8px;color:#fff;padding:12px;font-family:var(--mono);font-size:14px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:12px}.row>input{flex:1;min-width:180px}
.btn{background:var(--gold);color:var(--ink);border:0;border-radius:8px;padding:13px 18px;font-family:var(--mono);font-size:14px;font-weight:500;cursor:pointer;text-decoration:none;display:inline-block;white-space:nowrap}
.btn.g{background:transparent;color:var(--gold);border:1px solid var(--gold)}.btn.b{background:var(--btc);color:#1a0f00}.btn[disabled]{opacity:.45;cursor:default}
.tabs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}.tabs button{background:transparent;border:1px solid var(--line);color:var(--mut);border-radius:20px;padding:7px 14px;font-family:var(--mono);font-size:12.5px;cursor:pointer}
.tabs button.on{background:var(--gold);color:var(--ink);border-color:var(--gold)}
.list{margin-top:12px;display:flex;flex-direction:column;gap:6px}
.it{display:grid;grid-template-columns:1fr auto;gap:4px 10px;background:var(--ink);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:10px 12px;font-size:13.5px}
.it .n{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.it .h{font-family:var(--mono);font-size:11.5px;color:var(--mut);grid-column:1/-1;word-break:break-all}
.it a{color:var(--gold2);font-family:var(--mono);font-size:12.5px;text-decoration:none}
.msg{font-family:var(--mono);font-size:13px;margin-top:10px;min-height:1em;color:var(--mut)}.msg.err{color:var(--err)}.msg.ok{color:var(--ok2)}
.steps{list-style:none;margin-top:14px;border-left:1px solid var(--line);padding-left:18px}
.steps li{position:relative;padding:8px 0 10px;font-size:14.5px}.steps li:before{content:"";position:absolute;left:-24px;top:13px;width:11px;height:11px;border-radius:50%;background:var(--ink);border:1.5px solid var(--mut)}
.steps li.ok:before{background:var(--ok);border-color:var(--ok)}.steps li.bad:before{background:var(--err);border-color:var(--err)}.steps li.run:before{border-color:var(--btc);animation:pulse 1.4s infinite}
.steps li.wait:before{border-color:var(--gold)}
.steps b{display:block;font-weight:500}.steps span{color:var(--mut);font-size:13px;font-family:var(--mono);word-break:break-all}
.verdict{margin-top:16px;border-radius:12px;padding:20px;border:1px solid rgba(247,147,26,.55);background:linear-gradient(160deg,rgba(247,147,26,.14),rgba(16,24,46,1) 62%)}
.verdict.bad{border-color:rgba(255,138,128,.5);background:linear-gradient(160deg,rgba(255,138,128,.10),rgba(16,24,46,1) 60%)}
.verdict.wait{border-color:rgba(201,168,76,.5);background:linear-gradient(160deg,rgba(201,168,76,.10),rgba(16,24,46,1) 60%)}
.verdict h3{font-family:var(--serif);font-weight:500;font-size:28px;line-height:1.12;margin-bottom:6px}.verdict p{color:var(--mut);font-size:14.5px}
.how{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:6px 0 10px}@media(max-width:720px){.how{grid-template-columns:1fr 1fr}}@media(max-width:420px){.how{grid-template-columns:1fr}}
.how div{border-top:1px solid var(--line);padding-top:10px}.how b{font-family:var(--mono);font-size:12px;color:var(--gold);letter-spacing:.06em}.how p{color:var(--mut);font-size:14px;margin-top:4px}
pre{background:var(--ink);border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:12px;font-family:var(--mono);font-size:12.5px;color:#e8e8e8;overflow-x:auto;white-space:pre;margin-top:8px}
.code{font-family:var(--mono);font-size:26px;letter-spacing:.06em;color:var(--gold2)}
dl{display:grid;grid-template-columns:minmax(110px,170px) 1fr;gap:6px 14px;font-size:14px;margin-top:14px}
dt{color:var(--mut);font-size:13px}dd{font-family:var(--mono);font-size:13px;word-break:break-all}
.tl{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:16px}.tl div{border-top:3px solid rgba(255,255,255,.12);padding-top:8px;font-size:12.5px;color:var(--mut)}
.tl div.on{border-color:var(--btc);color:#fff}.tl div b{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.06em}
.chain{display:flex;gap:4px;margin:18px 0 0;overflow:hidden;height:34px;mask-image:linear-gradient(90deg,transparent,#000 12%,#000 88%,transparent)}
.chain span{flex:none;width:34px;height:34px;border:1px solid rgba(247,147,26,.4);border-radius:6px;background:rgba(247,147,26,.06);animation:slide 18s linear infinite}
@keyframes slide{from{transform:translateX(0)}to{transform:translateX(-380px)}}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}td,th{text-align:left;padding:8px 6px;border-bottom:1px solid rgba(255,255,255,.06)}th{color:var(--mut);font-weight:500;font-size:12px}td{font-family:var(--mono);font-size:12.5px}
a{color:var(--gold2)}
footer{border-top:1px solid var(--line);margin-top:34px;padding:22px 0 30px;font-size:12.5px;color:var(--mut)}footer a{color:var(--gold);text-decoration:none;margin-right:14px}
.sr{position:absolute;left:-9999px}
</style>"""

_TOP = r"""<header class="top"><div class="wrap"><a class="brand" href="/">sebbi<b>.pro</b></a>
<nav><a href="/bitcoin">Notary</a><a href="/forever">Forever Proof</a><a href="/keys">Human Keys</a><a href="/connect">Connect</a></nav></div></header>"""

_FOOT = r"""<footer><div class="wrap"><a href="/bitcoin">Bitcoin Notary</a><a href="/forever">Forever Proof</a><a href="/forever-verify.py">Verifier</a><a href="/x/notary/spec">Spec</a><a href="/terms">Terms</a>
<p style="margin-top:12px">&copy; 2026 Monop Content &middot; sebbi.pro</p></div></footer>"""

# The browser verifier. It is the same algorithm as forever_verify.py, written
# again in JavaScript so a visitor's own browser does the checking.
_FV_JS = r"""
const FV=(()=>{
const MAGIC=unhex('__MAGIC__');
function hex(b){return Array.from(b,x=>x.toString(16).padStart(2,'0')).join('')}
function unhex(s){return new Uint8Array((s.match(/../g)||[]).map(h=>parseInt(h,16)))}
function cat(a,b){const o=new Uint8Array(a.length+b.length);o.set(a);o.set(b,a.length);return o}
function eq(a,b){return a.length===b.length&&a.every((x,i)=>x===b[i])}
async function sha(alg,b){return new Uint8Array(await crypto.subtle.digest(alg,b))}
function R(b){this.b=b;this.i=0}
R.prototype.take=function(n){if(n<0||this.i+n>this.b.length)throw Error('the proof ends early');const o=this.b.slice(this.i,this.i+n);this.i+=n;return o};
R.prototype.byte=function(){return this.take(1)[0]};
R.prototype.vu=function(){let v=0,s=0,b;do{b=this.byte();v+=(b&127)*Math.pow(2,s);s+=7;if(s>56)throw Error('number too long')}while(b&128);return v};
R.prototype.vb=function(l){const n=this.vu();if(n>l)throw Error('field too long');return this.take(n)};
const TB='0588960d73d71901',TP='83dfe30d2ef90c8e',OPS=new Set([0x02,0x03,0x08,0x67,0xf0,0xf1,0xf2,0xf3]);
async function op(t,a,m){
 if(t===0x08)return sha('SHA-256',m);if(t===0x02)return sha('SHA-1',m);
 if(t===0xf0)return cat(m,a);if(t===0xf1)return cat(a,m);if(t===0xf2)return m.slice().reverse();
 if(t===0xf3)return new TextEncoder().encode(hex(m));
 throw Error('this proof uses an operation only the Python verifier checks');}
async function walk(r,m,out,d,c){
 if(d>256)throw Error('proof nested too deeply');
 const item=async t=>{
  if(t===0){const tag=hex(r.take(8));const p=new R(r.vb(8192));
   if(tag===TB)out.push({kind:'bitcoin',height:p.vu(),root:hex(m.slice().reverse())});
   else if(tag===TP)out.push({kind:'pending',cal:new TextDecoder().decode(p.vb(1000))});
   else out.push({kind:'other'});return}
  if(!OPS.has(t))throw Error('unknown tag in proof');
  const a=(t===0xf0||t===0xf1)?r.vb(4096):null;c.n++;const nm=await op(t,a,m);if(nm.length>4096)throw Error('message grew too long');
  await walk(r,nm,out,d+1,c)};
 let t=r.byte();while(t===0xff){await item(r.byte());t=r.byte()}await item(t)}
async function readOts(bytes){const r=new R(bytes);if(!eq(r.take(MAGIC.length),MAGIC))throw Error('not an OpenTimestamps proof');
 if(r.vu()!==1)throw Error('unsupported proof version');const f=r.byte();const n={8:32,2:20,3:20,103:32}[f];if(!n)throw Error('unsupported file hash');
 const dg=r.take(n);const out=[],c={n:0};await walk(r,dg,out,0,c);if(r.i!==bytes.length)throw Error('unexpected bytes after the proof');return{digest:hex(dg),atts:out,ops:c.n}}
async function leafHash(s){return sha('SHA-256',cat(new Uint8Array([0]),new TextEncoder().encode(s)))}
async function node(l,r){return sha('SHA-256',cat(cat(new Uint8Array([1]),l),r))}
async function rootFromPath(leaf,i,size,path){if(i<0||i>=size)return null;let fn=i,sn=size-1,r=leaf;
 for(const ph of path){const p=unhex(ph);if(sn===0)return null;
  if((fn%2===1)||fn===sn){r=await node(p,r);if(fn%2===0){while(fn%2===0&&fn!==0){fn=Math.floor(fn/2);sn=Math.floor(sn/2)}}}else r=await node(r,p);
  fn=Math.floor(fn/2);sn=Math.floor(sn/2)}return sn===0?r:null}
const EXPL=[['mempool.space','https://mempool.space/api'],['blockstream.info','https://blockstream.info/api']];
async function block(base,h){const id=(await (await fetch(base+'/block-height/'+h)).text()).trim();if(!/^[0-9a-f]{64}$/.test(id))throw Error('no block hash');
 const j=await (await fetch(base+'/block/'+id)).json();return{hash:id,root:String(j.merkle_root||'').toLowerCase(),time:j.timestamp}}
function norm(s){return s.normalize('NFC').replace(/\r\n?/g,'\n').trim()}
async function sha256hex(bytes){return hex(await sha('SHA-256',bytes))}
async function check(b,step,extra){
 extra=extra||{};
 if(!b||b.format!=='sebbi-forever-proof/1'){step('Format',false,'This is not a sebbi.pro Forever Proof.');return{ok:false}}
 const s=b.subject||{},m=b.merkle||{};
 if(s.kind==='hash'&&extra.file){const d=await sha256hex(extra.file);const ok=('sebbi-notary/1|'+d)===b.leaf;step('Your file',ok,'SHA-256 '+d+(ok?' — matches':' — does NOT match'));if(!ok)return{ok:false}}
 if(s.kind==='humankeys'&&extra.text!=null){const th=await sha256hex(new TextEncoder().encode(norm(extra.text)));const ok=th===s.text_hash;step('Your text',ok,'fingerprint '+th+(ok?' — matches':' — does NOT match'));if(!ok)return{ok:false}}
 if(s.kind==='hash'&&b.leaf!=='sebbi-notary/1|'+String(s.digest||'')){step('Fingerprint',false,'The leaf does not match the fingerprint.');return{ok:false}}
 if(s.kind==='humankeys'){const want=['sebbi-humankeys/1',s.code,s.text_hash,s.verdict,Math.floor(s.sealed_at||0)].join('|');if(want!==b.leaf){step('Human Keys record',false,'The leaf does not match the record.');return{ok:false}}
  step('Human Keys record',true,s.code+' · '+s.verdict)}
 if(s.kind==='chain_block'){if(b.leaf!==s.audit_hash){step('Chain block',false,'The leaf is not the block hash.');return{ok:false}}step('Chain block',true,'block '+s.block+' · '+s.audit_hash)}
 const root=await rootFromPath(await leafHash(b.leaf),+m.index,+m.tree_size,m.path||[]);
 const okRoot=root&&hex(root)===String(m.root).toLowerCase();
 step('Merkle path',okRoot,'fingerprint '+(+m.index+1)+' of '+m.tree_size+' folds up to root '+m.root);if(!okRoot)return{ok:false};
 const raw=Uint8Array.from(atob((b.bitcoin||{}).proof_ots_base64||''),c=>c.charCodeAt(0));
 if(!raw.length){step('Bitcoin',null,'This batch is still being sent to the Bitcoin calendars. Try again in a few minutes.');return{ok:false,pending:true}}
 const o=await readOts(raw);
 const okD=o.digest===String(m.root).toLowerCase();step('OpenTimestamps proof',okD,o.ops+' operations replayed in your browser from that root');if(!okD)return{ok:false};
 const btc=o.atts.filter(a=>a.kind==='bitcoin').sort((x,y)=>x.height-y.height);
 if(!btc.length){step('Bitcoin',null,'Pending: the calendars have promised this to Bitcoin. It normally confirms within a few hours.');return{ok:false,pending:true}}
 for(const a of btc){const got=[];
  for(const [name,base] of EXPL){try{const bl=await block(base,a.height);if(bl.root!==a.root){step('Bitcoin block '+a.height,false,name+' reports a different Merkle root');return{ok:false}}got.push([name,bl])}catch(e){step(name,null,'did not answer — trying the next')}}
  if(got.length){step('Bitcoin block '+a.height,true,'Merkle root '+a.root+' confirmed by '+got.map(g=>g[0]).join(' and '));return{ok:true,height:a.height,time:got[0][1].time,hash:got[0][1].hash,sources:got.map(g=>g[0])}}}
 step('Bitcoin',false,'No block explorer could be reached. Use the offline verifier.');return{ok:false}}
return{check,sha256hex,norm,hex}})();
"""


NOTARY_PAGE = _HEAD + r"""<title>Bitcoin Notary — sebbi.pro</title>
<meta name="description" content="Prove anything existed. Drop a file, get a receipt, and it is timestamped in Bitcoin — forever, free, and checkable without us.">
</head><body>""" + _TOP + r"""
<main class="wrap">
<section class="hero">
<div class="kick"><i></i>BITCOIN NOTARY · FREE FOR EVERYONE</div>
<h1>Prove it existed.<br><em>Forever.</em></h1>
<p>Drop any file — a contract, a model card, a dataset, a design, an AI decision log. Your device fingerprints it, the fingerprint is written into Bitcoin, and you get a receipt anyone on earth can check against the Bitcoin blockchain. The file never leaves your hands.</p>
<div class="chain" aria-hidden="true"><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div>
<div class="live">
<div><b class="btc" id="lh">—</b><span>Bitcoin block now</span></div>
<div><b id="lnext">—</b><span>Next Bitcoin batch</span></div>
<div><b id="lfp">—</b><span>Fingerprints notarised</span></div>
<div><b id="lcb">—</b><span>sebbi.pro blocks in Bitcoin</span></div>
</div>
</section>

<section class="card" id="stamp">
<div class="tabs"><button class="on" data-t="files">Files</button><button data-t="text">Text</button><button data-t="hash">Fingerprint</button><button data-t="check">Check a file</button></div>
<div data-p="files">
<label class="drop" id="drop"><input type="file" id="fi" multiple class="sr"><b>Drop files here, or tap to choose</b><span>Fingerprinted on this device. Nothing is uploaded.</span></label>
</div>
<div data-p="text" hidden><textarea id="tx" placeholder="Paste or type anything — an idea, a claim, a prompt, a policy"></textarea></div>
<div data-p="hash" hidden><input type="text" id="hx" placeholder="SHA-256 fingerprint — 64 hex characters, one per line for several"></div>
<div data-p="check" hidden><label class="drop" id="drop2"><input type="file" id="fc" class="sr"><b>Drop a file to check</b><span>We look up its fingerprint and show the earliest Bitcoin receipt.</span></label></div>
<div class="row" id="lrow"><input type="text" id="lb" maxlength="80" placeholder="Label (optional, public)"></div>
<div class="list" id="ls"></div>
<div class="row"><button class="btn b" id="go" disabled>Timestamp in Bitcoin</button><span class="msg" id="m"></span></div>
</section>

<section class="card">
<h2>How it works</h2>
<div class="how">
<div><b>01 · FINGERPRINT</b><p>Your browser computes the file's SHA-256. Only those 64 characters travel.</p></div>
<div><b>02 · BATCH</b><p>Every few minutes, every fingerprint is folded into one Merkle tree.</p></div>
<div><b>03 · BITCOIN</b><p>The tree's root goes into Bitcoin through the public OpenTimestamps calendars.</p></div>
<div><b>04 · FOREVER</b><p>Your Forever Proof checks against Bitcoin itself. No account. No trust in us.</p></div>
</div>
</section>

<section class="card">
<h2>Built for AI companies, governance tools and auditors</h2>
<p class="sub">Anchor your own logs, model releases or evidence packs in Bitcoin through one call. Free — 500 fingerprints a day without a key, 100,000 with one.</p>
<pre>curl -X POST https://sebbi.pro/x/notary/stamp \
  -H "Content-Type: application/json" \
  -d '{"digests": ["'$(sha256sum report.pdf | cut -c1-64)'"], "label": "Q3 model card"}'</pre>
<p class="sub" style="margin-top:12px">Or let an AI assistant do it: connect <a href="/connect">https://sebbi.pro/mcp</a> and ask it to notarise a file — agents can also read the discovery file below. Show you are anchored with a live badge:</p>
<pre>&lt;img src="https://sebbi.pro/n/NT-XXXX-XXXX.svg" alt="Anchored in Bitcoin via sebbi.pro"&gt;</pre>
<p class="sub" style="margin-top:12px">Machine-readable: <a href="/.well-known/sebbi-notary.json">/.well-known/sebbi-notary.json</a> · <a href="/x/notary/spec">full spec</a></p>
</section>

<section class="card">
<h2>Every sebbi.pro decision is already in Bitcoin</h2>
<p class="sub">Each hour the whole sebbi.pro chain is folded into one root and written into Bitcoin. Any sealed AI decision gets a Forever Proof that outlives us.</p>
<a class="btn g" href="/forever">Get a Forever Proof</a>
</section>
</main>""" + _FOOT + r"""
<script>""" + _FV_JS + r"""
const $=s=>document.querySelector(s);let mode='files',items=[];
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{mode=b.dataset.t;document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));
 document.querySelectorAll('[data-p]').forEach(p=>p.hidden=p.dataset.p!==mode);$('#lrow').hidden=mode==='check';$('#go').hidden=mode==='check';items=[];render();refresh()});
function esc(t){return String(t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(){$('#ls').innerHTML=items.map(i=>'<div class="it"><span class="n">'+esc(i.name)+'</span>'+(i.code?'<a href="/n/'+i.code+'">'+i.code+' →</a>':'<span></span>')+'<span class="h">'+i.digest+'</span></div>').join('')}
function refresh(){$('#go').disabled=!items.length||items.some(i=>i.code)}
async function addFiles(fl){$('#m').textContent='Fingerprinting on this device…';$('#m').className='msg';
 for(const f of fl){const d=await FV.sha256hex(new Uint8Array(await f.arrayBuffer()));items.push({name:f.name+' · '+(f.size/1024).toFixed(1)+' KB',digest:d})}
 $('#m').textContent=items.length+' ready';render();refresh()}
['drop','drop2'].forEach(id=>{const d=$('#'+id);d.addEventListener('dragover',e=>{e.preventDefault();d.classList.add('on')});d.addEventListener('dragleave',()=>d.classList.remove('on'));
 d.addEventListener('drop',e=>{e.preventDefault();d.classList.remove('on');id==='drop'?addFiles(e.dataTransfer.files):checkFile(e.dataTransfer.files[0])})});
$('#fi').onchange=e=>addFiles(e.target.files);$('#fc').onchange=e=>checkFile(e.target.files[0]);
$('#tx').oninput=async e=>{const t=e.target.value;items=t.trim()?[{name:'Text · '+t.length+' characters',digest:await FV.sha256hex(new TextEncoder().encode(t))}]:[];render();refresh()};
$('#hx').oninput=e=>{items=e.target.value.split(/\s+/).map(x=>x.trim().toLowerCase()).filter(x=>/^[0-9a-f]{64}$/.test(x)).map(d=>({name:'Fingerprint',digest:d}));render();refresh()};
async function checkFile(f){if(!f)return;$('#m').className='msg';$('#m').textContent='Fingerprinting…';const d=await FV.sha256hex(new Uint8Array(await f.arrayBuffer()));
 const r=await (await fetch('/x/notary/lookup?digest='+d)).json();items=[{name:f.name,digest:d,code:(r.receipts&&r.receipts[0]||{}).code}];render();
 if(r.receipts&&r.receipts.length){const x=r.receipts[0];$('#m').className='msg ok';$('#m').textContent='Found. First notarised '+new Date(x.received_utc).toLocaleString('en-GB')+(x.bitcoin_block?' · Bitcoin block '+x.bitcoin_block:'')}
 else{$('#m').className='msg err';$('#m').textContent='Never notarised here. Switch to Files to timestamp it now.'}}
$('#go').onclick=async()=>{$('#go').disabled=true;$('#m').className='msg';$('#m').textContent='Sending fingerprints…';
 try{const r=await fetch('/x/notary/stamp',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:$('#lb').value,digests:items.map(i=>i.digest)})});const j=await r.json();
  if(!r.ok)throw Error(j.message||j.error);j.receipts.forEach((x,i)=>items[i].code=x.code);render();$('#m').className='msg ok';
  $('#m').textContent='Received. In the next Bitcoin batch'+(j.next_batch_utc?' at '+new Date(j.next_batch_utc).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):'')+'. Tap a receipt.';
  if(items.length===1)setTimeout(()=>location.href='/n/'+items[0].code,900)}
 catch(e){$('#m').className='msg err';$('#m').textContent=e.message;$('#go').disabled=false}};
let nextAt=null;
async function stats(){try{const s=await (await fetch('/x/notary/status')).json();$('#lfp').textContent=(s.fingerprints||0).toLocaleString('en-GB');$('#lcb').textContent=(s.chain_blocks_in_bitcoin||0).toLocaleString('en-GB');nextAt=s.next_batch_utc?Date.parse(s.next_batch_utc):null}catch(e){}
 try{const h=await (await fetch('https://mempool.space/api/blocks/tip/height')).text();if(/^\d+$/.test(h.trim()))$('#lh').textContent='#'+(+h).toLocaleString('en-GB')}catch(e){}}
setInterval(()=>{if(!nextAt)return;let s=Math.max(0,Math.round((nextAt-Date.now())/1000));$('#lnext').textContent=s?Math.floor(s/60)+'m '+String(s%60).padStart(2,'0')+'s':'now'},1000);
stats();setInterval(stats,60000);
</script></body></html>"""


RECEIPT_PAGE = _HEAD + r"""<title>__CODE__ — Bitcoin receipt — sebbi.pro</title></head><body>""" + _TOP + r"""
<main class="wrap">
<section class="hero"><div class="kick"><i></i>BITCOIN RECEIPT</div><h1 id="hd">Receipt</h1><p id="hp">Loading…</p></section>
<section class="card" id="cert" hidden>
<div class="code" id="cd">__CODE__</div>
<div class="tl"><div id="t1"><b>RECEIVED</b><span id="t1s"></span></div><div id="t2"><b>BATCHED</b><span id="t2s"></span></div><div id="t3"><b>SENT TO BITCOIN</b><span id="t3s"></span></div><div id="t4"><b>IN BITCOIN</b><span id="t4s"></span></div></div>
<dl id="dl"></dl>
<div class="row"><button class="btn b" id="dlb" disabled>Download Forever Proof</button><a class="btn g" id="vf" href="/forever?code=__CODE__">Verify against Bitcoin</a></div>
<p class="msg" id="m"></p>
</section>
<section class="card" id="cmp" hidden><h2>Is this the same file?</h2><p class="sub">Drop the file here. It is fingerprinted on your device and compared.</p>
<label class="drop"><input type="file" id="fc" class="sr"><b>Drop the file</b><span>Nothing is uploaded</span></label><p class="msg" id="cm"></p></section>
<section class="card" id="emb" hidden><h2>Show it</h2><p class="sub">A live badge for your site, README or report. It turns orange when the block lands.</p>
<p><img id="bimg" alt="Anchored in Bitcoin via sebbi.pro"></p><pre id="bcode"></pre></section>
</main>""" + _FOOT + r"""
<script>""" + _FV_JS + r"""
const $=s=>document.querySelector(s),CODE='__CODE__';
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
const fmt=t=>t?new Date(t).toLocaleString('en-GB',{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'';
let rec=null;
async function load(){
 if(!/^(NT|HK)-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(CODE)){$('#hd').textContent='Find a receipt';$('#hp').innerHTML='Receipt codes look like NT-7Q2M-X9KD. <a href="/bitcoin">Notarise a file</a>.';return}
 const r=await fetch('/x/notary/receipt?code='+CODE);rec=await r.json();
 if(!r.ok){$('#hd').textContent='Not found';$('#hp').textContent='No receipt with that code.';return}
 const s=rec.subject,b=rec.batch||{},st=rec.state;$('#cert').hidden=false;$('#emb').hidden=false;$('#cmp').hidden=s.kind!=='hash';
 $('#hd').innerHTML=st==='confirmed'?'In Bitcoin <em>block '+b.bitcoin.height.toLocaleString('en-GB')+'</em>':(st==='pending'?'Sent to <em>Bitcoin</em>':'Received');
 $('#hp').textContent=rec.message;
 const on=[true,!!rec.batch,st==='pending'||st==='confirmed',st==='confirmed'];['t1','t2','t3','t4'].forEach((id,i)=>$('#'+id).classList.toggle('on',on[i]));
 $('#t1s').textContent=fmt(rec.received_utc);$('#t2s').textContent=b.created_utc?fmt(b.created_utc):(rec.next_batch_utc?'next at '+new Date(rec.next_batch_utc).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'}):'');
 $('#t3s').textContent=b.calendars?b.calendars+' calendar'+(b.calendars>1?'s':''):'';$('#t4s').textContent=b.bitcoin?(b.bitcoin.block_time_utc?fmt(b.bitcoin.block_time_utc):'block '+b.bitcoin.height):'usually a few hours';
 const rows=[];if(s.kind==='hash'){rows.push(['Fingerprint',s.digest]);if(s.label)rows.push(['Label',s.label])}else{rows.push(['Human Keys',s.code+' · '+s.verdict]);rows.push(['Text fingerprint',s.text_hash]);rows.push(['Typed',fmt(s.sealed_utc)])}
 if(b.root)rows.push(['Batch root',b.root]);if(b.size)rows.push(['Batch','#'+b.batch+' · '+b.size.toLocaleString('en-GB')+' fingerprints']);
 if(b.bitcoin){rows.push(['Bitcoin block','<a href="'+b.bitcoin.explorer+'" target="_blank" rel="noopener">'+b.bitcoin.height+'</a>']);if(b.bitcoin.checked_with)rows.push(['Checked with',b.bitcoin.checked_with.map(x=>x.replace('https://','').replace('/api','')).join(', ')])}
 $('#dl').innerHTML=rows.map(r=>'<dt>'+r[0]+'</dt><dd>'+(r[0]==='Bitcoin block'?r[1]:esc(r[1]))+'</dd>').join('');
 $('#dlb').disabled=!rec.batch;const src=location.origin+'/n/'+CODE+'.svg';$('#bimg').src=src+'?'+Date.now();$('#bcode').textContent='<a href="'+location.origin+'/n/'+CODE+'"><img src="'+src+'" alt="Anchored in Bitcoin via sebbi.pro"></a>';
 if(st!=='confirmed')setTimeout(load,60000)}
$('#dlb').onclick=async()=>{const r=await fetch('/x/notary/bundle?code='+CODE);const j=await r.json();if(!r.ok){$('#m').className='msg err';$('#m').textContent=j.message||j.error;return}
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(j,null,1)],{type:'application/json'}));a.download=CODE+'.forever.json';a.click();
 $('#m').className='msg ok';$('#m').textContent=j.bitcoin.state==='confirmed'?'Saved. It checks against Bitcoin with nothing from us.':'Saved. Download again once it is in Bitcoin for the complete proof.'};
$('#fc').onchange=async e=>{const f=e.target.files[0];if(!f||!rec)return;const d=await FV.sha256hex(new Uint8Array(await f.arrayBuffer()));const ok=d===rec.subject.digest;
 $('#cm').className='msg '+(ok?'ok':'err');$('#cm').textContent=ok?'Same file — exact match.':'Different file. Its fingerprint is '+d};
load();
</script></body></html>"""


FOREVER_PAGE = _HEAD + r"""<title>Forever Proof — sebbi.pro</title>
<meta name="description" content="Proof that outlives us. Check any sebbi.pro decision, notary receipt or Human Keys proof against Bitcoin itself, in your own browser.">
</head><body>""" + _TOP + r"""
<main class="wrap">
<section class="hero">
<div class="kick"><i></i>FOREVER PROOF</div>
<h1>Proof that <em>outlives us.</em></h1>
<p>Every AI decision sealed on sebbi.pro, every notary receipt and every Human Keys proof can be checked against the Bitcoin blockchain — in your own browser, right here, or offline with one small file. If sebbi.pro vanished tomorrow, the proof would still stand.</p>
<div class="live">
<div><b class="btc" id="lh">—</b><span>Bitcoin block now</span></div>
<div><b id="lcb">—</b><span>Chain blocks in Bitcoin</span></div>
<div><b id="lcp">—</b><span>Hourly checkpoints</span></div>
<div><b id="lbb">—</b><span>Batches confirmed</span></div>
</div>
</section>

<section class="card">
<div class="tabs"><button class="on" data-t="get">Get a proof</button><button data-t="file">Check a proof file</button></div>
<div data-p="get">
<p class="sub">A chain block number, a notary receipt (NT-…) or a Human Keys code (HK-…).</p>
<div class="row"><input type="text" id="q" placeholder="e.g. 1042   or   NT-7Q2M-X9KD   or   HK-4FJ8-2KQP" autocomplete="off"><button class="btn b" id="getb">Verify against Bitcoin</button></div>
</div>
<div data-p="file" hidden>
<label class="drop" id="drop"><input type="file" id="fi" accept=".json,application/json" class="sr"><b>Drop a Forever Proof (.json)</b><span>Checked entirely in this browser</span></label>
<div class="row"><label class="btn g" style="cursor:pointer">Also compare the original file<input type="file" id="orig" class="sr"></label><span class="msg" id="om"></span></div>
</div>
<ol class="steps" id="steps" hidden></ol>
<div id="vd"></div>
<div class="row" id="dlr" hidden><button class="btn g" id="dlb">Download this Forever Proof</button></div>
</section>

<section class="card">
<h2>Check it with nothing of ours</h2>
<p class="sub">One Python file, standard library only. It replays every step and asks two independent block explorers — or your own Bitcoin node — for the block.</p>
<pre>python3 forever-verify.py proof.json
python3 forever-verify.py proof.json --file contract.pdf
python3 forever-verify.py proof.json --node</pre>
<div class="row"><a class="btn" href="/forever-verify.py">Download forever-verify.py</a><a class="btn g" href="/x/notary/spec">Proof format</a></div>
</section>

<section class="card">
<h2>Hourly checkpoints</h2>
<p class="sub">The whole sebbi.pro chain, folded into one Merkle root and written into Bitcoin. The same root anyone can recompute at <a href="/x/consistency/root">/x/consistency/root</a>.</p>
<table><thead><tr><th>Checkpoint</th><th>Chain blocks</th><th>Bitcoin</th></tr></thead><tbody id="cps"><tr><td colspan="3">Loading…</td></tr></tbody></table>
</section>
</main>""" + _FOOT + r"""
<script>""" + _FV_JS + r"""
const $=s=>document.querySelector(s);let bundle=null,orig=null;
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));document.querySelectorAll('[data-p]').forEach(p=>p.hidden=p.dataset.p!==b.dataset.t)});
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function step(name,ok,detail){const li=document.createElement('li');li.className=ok===true?'ok':(ok===false?'bad':'wait');li.innerHTML='<b>'+esc(name)+'</b><span>'+esc(detail)+'</span>';$('#steps').appendChild(li)}
async function run(b){bundle=b;$('#steps').innerHTML='';$('#steps').hidden=false;$('#vd').innerHTML='';$('#dlr').hidden=!b;
 if(b&&b.subject){const s=b.subject;step('Subject',true,s.kind==='chain_block'?'sebbi.pro chain block '+s.block:(s.kind==='humankeys'?'Human Keys '+s.code:'Notary receipt '+s.code+(s.label?' · '+s.label:'')))}
 let r;try{r=await FV.check(b,step,{file:orig})}catch(e){step('Proof',false,e.message);r={ok:false}}
 if(r.ok){const d=r.time?new Date(r.time*1000).toLocaleString('en-GB',{day:'numeric',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'}):'';
  $('#vd').innerHTML='<div class="verdict"><h3>Verified in Bitcoin block '+r.height.toLocaleString('en-GB')+'</h3><p>This existed before '+esc(d)+'. Checked in your browser against '+esc(r.sources.join(' and '))+'. Nothing from sebbi.pro was trusted.</p></div>'}
 else if(r.pending)$('#vd').innerHTML='<div class="verdict wait"><h3>On its way into Bitcoin</h3><p>Everything checks so far. The Bitcoin block normally lands within a few hours — come back and check again.</p></div>';
 else $('#vd').innerHTML='<div class="verdict bad"><h3>Not verified</h3><p>A step above failed. This proof does not show what it claims.</p></div>'}
async function fetchProof(q){q=q.trim().toUpperCase();if(!q)return;$('#getb').disabled=true;$('#steps').hidden=false;$('#steps').innerHTML='';step('Fetching the proof',null,'only the proof comes from sebbi.pro — the checking happens here');
 const url=/^\d+$/.test(q)?'/x/notary/bundle?block='+q:'/x/notary/bundle?code='+encodeURIComponent(q);
 try{const r=await fetch(url);const j=await r.json();$('#getb').disabled=false;
  if(r.status===202||j.state==='queued'){$('#steps').innerHTML='';step('Queued',null,j.message||'Joins the next Bitcoin batch.');$('#vd').innerHTML='<div class="verdict wait"><h3>Joining the next Bitcoin batch</h3><p>'+esc(j.message||'')+'</p></div>';return}
  if(!r.ok){$('#steps').innerHTML='';step('Proof',false,j.message||j.error);return}
  history.replaceState(null,'','/forever?'+(/^\d+$/.test(q)?'block=':'code=')+q);await run(j)}catch(e){$('#getb').disabled=false;step('Proof',false,e.message)}}
$('#getb').onclick=()=>fetchProof($('#q').value);$('#q').onkeydown=e=>{if(e.key==='Enter')fetchProof($('#q').value)};
async function loadFile(f){if(!f)return;try{await run(JSON.parse(await f.text()))}catch(e){$('#steps').hidden=false;$('#steps').innerHTML='';step('Proof file',false,'Could not read that file as a Forever Proof.')}}
const d=$('#drop');d.addEventListener('dragover',e=>{e.preventDefault();d.classList.add('on')});d.addEventListener('dragleave',()=>d.classList.remove('on'));d.addEventListener('drop',e=>{e.preventDefault();d.classList.remove('on');loadFile(e.dataTransfer.files[0])});
$('#fi').onchange=e=>loadFile(e.target.files[0]);
$('#orig').onchange=async e=>{const f=e.target.files[0];if(!f)return;orig=new Uint8Array(await f.arrayBuffer());$('#om').textContent=f.name+' will be compared';if(bundle)run(bundle)};
$('#dlb').onclick=()=>{if(!bundle)return;const s=bundle.subject||{};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(bundle,null,1)],{type:'application/json'}));a.download=(s.code||('block-'+s.block))+'.forever.json';a.click()};
async function side(){try{const s=await (await fetch('/x/notary/status')).json();$('#lcb').textContent=(s.chain_blocks_in_bitcoin||0).toLocaleString('en-GB');$('#lcp').textContent=(s.chain_checkpoints||0).toLocaleString('en-GB');$('#lbb').textContent=(s.batches_in_bitcoin||0).toLocaleString('en-GB')}catch(e){}
 try{const c=await (await fetch('/x/notary/checkpoints')).json();$('#cps').innerHTML=(c.checkpoints||[]).map(x=>'<tr><td>#'+x.batch+' · '+new Date(x.created_utc).toLocaleString('en-GB',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})+'</td><td>'+(x.chain_size||0).toLocaleString('en-GB')+'</td><td>'+(x.bitcoin?'<a href="'+x.bitcoin.explorer+'" target="_blank" rel="noopener">block '+x.bitcoin.height+'</a>':x.state)+'</td></tr>').join('')||'<tr><td colspan="3">The first checkpoint is on its way.</td></tr>'}catch(e){}
 try{const h=await (await fetch('https://mempool.space/api/blocks/tip/height')).text();if(/^\d+$/.test(h.trim()))$('#lh').textContent='#'+(+h).toLocaleString('en-GB')}catch(e){}}
side();const P=new URLSearchParams(location.search);if(P.get('block')||P.get('code')){$('#q').value=P.get('block')||P.get('code');fetchProof($('#q').value)}
</script></body></html>"""

# shown on the homepage, above the existing feature strip
HOME_STRIP = r"""<section class="ntx" aria-label="Bitcoin Notary">
<style>
.ntx{background:#070b17;border-top:1px solid rgba(247,147,26,.28);padding:52px 16px;color:#fff;font-family:'IBM Plex Sans',system-ui,sans-serif}
.ntx *{box-sizing:border-box}.ntx-in{max-width:1080px;margin:0 auto}
.ntx-k{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;letter-spacing:.1em;color:#f7931a;display:flex;align-items:center;gap:10px;margin-bottom:12px}
.ntx-k i{width:8px;height:8px;border-radius:50%;background:#f7931a;display:inline-block}
.ntx h3{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:clamp(28px,4vw,42px);line-height:1.08;margin:0 0 10px}.ntx h3 em{color:#c9a84c}
.ntx p.l{color:rgba(255,255,255,.66);font-size:15.5px;max-width:62ch;margin:0 0 22px}
.ntx-g{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid rgba(247,147,26,.25);border-radius:14px;overflow:hidden}
@media(max-width:760px){.ntx-g{grid-template-columns:1fr}}
.ntx-g a{display:block;padding:22px;background:#0b1122;color:#fff;text-decoration:none;border-right:1px solid rgba(247,147,26,.15);transition:background .2s}
.ntx-g a:hover,.ntx-g a:focus-visible{background:#111a33;outline:none}
.ntx-g b{display:block;font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:21px;margin-bottom:6px}
.ntx-g span{display:block;color:rgba(255,255,255,.6);font-size:14px;line-height:1.5}.ntx-g em{display:block;font-style:normal;color:#f7931a;font-size:13px;margin-top:12px;font-family:'IBM Plex Mono',ui-monospace,monospace}
</style>
<div class="ntx-in">
<div class="ntx-k"><i></i>NEW · BITCOIN</div>
<h3>Proof that <em>outlives us.</em></h3>
<p class="l">Every decision sealed here is written into Bitcoin every hour. Anyone can now timestamp anything in Bitcoin for free — and check it without trusting us.</p>
<div class="ntx-g">
<a href="/bitcoin"><b>Bitcoin Notary</b><span>Drop any file. Get a receipt written into Bitcoin. Free for everyone, open to every AI company.</span><em>sebbi.pro/bitcoin →</em></a>
<a href="/forever"><b>Forever Proof</b><span>Check any sealed decision against Bitcoin itself, in your own browser. No account, no trust.</span><em>sebbi.pro/forever →</em></a>
<a href="/keys"><b>Human Keys, in Bitcoin</b><span>Proof a human typed it — now dated by Bitcoin, so the original always comes first.</span><em>sebbi.pro/keys →</em></a>
</div></div></section>"""

# shown on every Human Keys check page
HK_PANEL = r"""<section id="ntxhk" style="max-width:820px;margin:0 auto;padding:0 16px">
<div style="background:#10182e;border:1px solid rgba(247,147,26,.35);border-radius:10px;padding:16px 18px;margin:18px 0;font-family:'IBM Plex Sans',system-ui,sans-serif;color:#fff">
<div style="font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.08em;color:#f7931a;margin-bottom:6px">TIMESTAMPED IN BITCOIN</div>
<div id="ntxhk-s" style="font-size:15px">Checking…</div>
<div id="ntxhk-a" style="margin-top:10px;display:none"><a id="ntxhk-v" style="display:inline-block;background:#f7931a;color:#1a0f00;border-radius:6px;padding:10px 14px;font-family:'IBM Plex Mono',monospace;font-size:13px;text-decoration:none">Verify against Bitcoin</a></div>
</div></section>
<script>(function(){var c=(location.pathname.split('/')[2]||'').toUpperCase();if(!/^HK-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(c)){var e=document.getElementById('ntxhk');if(e)e.remove();return}
fetch('/x/notary/hk?code='+c).then(function(r){return r.json()}).then(function(j){var s=document.getElementById('ntxhk-s');if(!j||j.error){document.getElementById('ntxhk').remove();return}
var b=j.batch&&j.batch.bitcoin;s.textContent=j.state==='confirmed'?('In Bitcoin block '+b.height.toLocaleString('en-GB')+(b.block_time_utc?' · '+new Date(b.block_time_utc).toLocaleString('en-GB',{day:'numeric',month:'short',year:'numeric'}):'')+'. Anyone can check it against Bitcoin, without sebbi.pro.'):(j.state==='pending'?'Sent to Bitcoin. The block normally lands within a few hours.':'Joining the next Bitcoin batch.');
var a=document.getElementById('ntxhk-v');a.href='/forever?code='+c;document.getElementById('ntxhk-a').style.display='block'}).catch(function(){})})();</script>"""

# two buttons added to the homepage button list, just above the machine-proof report
HOME_BUTTONS_B = (b'<a href="/bitcoin" style="border:1.5px solid #f7931a"><span class="tag" style="background:#f7931a">BITCOIN</span>Bitcoin Notary &rarr;</a>'
                  b'<a href="/forever" style="border:1.5px solid #f7931a"><span class="tag" style="background:#f7931a">FOREVER</span>Forever Proof &rarr;</a>')
HOME_BUTTONS_AT = b'<a href="/dossier" style='
HOME_STRIP_B = HOME_STRIP.encode("utf-8")
HK_PANEL_B = HK_PANEL.encode("utf-8")


def _page(tpl, code=""):
    return tpl.replace("__MAGIC__", FV.HEADER_MAGIC.hex()).replace("__CODE__", code)


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_notary_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if p == "/bitcoin":
                return _send(self, _page(NOTARY_PAGE), "text/html; charset=utf-8")
            if p == "/forever":
                return _send(self, _page(FOREVER_PAGE), "text/html; charset=utf-8")
            if p == "/n" or p.startswith("/n/"):
                code = p[3:].upper()
                if code.endswith(".SVG"):
                    return _send(self, _badge(code[:-4]), "image/svg+xml")
                return _send(self, _page(RECEIPT_PAGE, code if (NT_RE.match(code) or HK_RE.match(code)) else ""),
                             "text/html; charset=utf-8")
            if p in ("/forever-verify.py", "/forever_verify.py"):
                with open(FV.__file__, "rb") as fh:
                    return _send(self, fh.read(), "text/x-python; charset=utf-8",
                                 extra={"Content-Disposition": 'attachment; filename="forever-verify.py"'})
            if p == "/.well-known/sebbi-notary.json":
                return _send(self, json.dumps(_discovery(), indent=1), "application/json")
        except Exception as e:
            _state["last_error"] = "page: %s" % str(e)[:200]
        return orig(self)

    H.do_GET = do_GET
    H._notary_pages = True
    _state["pages"] = True
    return True


class _Out(object):
    """Holds one HTML response so a panel can be added. Everything else passes straight through."""

    def __init__(self, real):
        self.real = real
        self.buf = bytearray()
        self.mode = None

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            if b"content-type: text/html" in head and b"content-encoding" not in head:
                self.mode = "html"
            else:
                self._go_pass()
        elif len(self.buf) > 8 * 1024 * 1024:
            self._go_pass()
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self, where):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if not where or self.mode != "html" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        if where == "home" and b'class="ntx"' not in body:
            at = body.find(b'<section class="sbx"')
            if at < 0:
                at = body.find(b"<footer")
            if at < 0:
                at = body.rfind(b"</body>")
            if at >= 0:
                body = body[:at] + HOME_STRIP_B + body[at:]
            if b'href="/bitcoin" style=' not in body:
                bt = body.find(HOME_BUTTONS_AT)
                if bt >= 0:
                    body = body[:bt] + HOME_BUTTONS_B + body[bt:]
        elif where == "hk" and b'id="ntxhk"' not in body:
            at = body.rfind(b"<footer")
            if at < 0:
                at = body.rfind(b"</body>")
            if at >= 0:
                body = body[:at] + HK_PANEL_B + body[at:]
        lines = [l for l in head.split(b"\r\n") if not l.lower().startswith(b"content-length:")]
        lines.append(b"Content-Length: " + str(len(body)).encode())
        self.real.write(b"\r\n".join(lines) + b"\r\n\r\n" + body)
        _state["injected"] += 1
        try:
            self.real.flush()
        except Exception:
            pass


def _install_inject():
    if _state["inject"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_notary_inject", False):
        _state["inject"] = True
        return True
    original = H.handle_one_request

    def handle_one_request(self):
        real = self.wfile
        out = _Out(real)
        self.wfile = out
        try:
            original(self)
        finally:
            self.wfile = real
            try:
                path = (getattr(self, "path", "") or "").split("?")[0]
                where = None
                if getattr(self, "command", "") == "GET":
                    if path in ("/", "/index.html"):
                        where = "home"
                    elif path.startswith("/k/") and HK_RE.match(path[3:].rstrip("/").upper()):
                        where = "hk"
                out.finish(where)
            except Exception as e:
                _state["last_error"] = "inject: %s" % str(e)[:200]
                try:
                    if out.buf:
                        real.write(bytes(out.buf))
                except Exception:
                    pass

    H.handle_one_request = handle_one_request
    H._notary_inject = True
    _state["inject"] = True
    return True


def arm(ctx=None):
    with _lock:
        if not _state["ready"]:
            _setup()
            _state["ready"] = True
        _install_pages()
        _install_inject()
        try:
            _install_mcp()
        except Exception as e:
            _state["last_error"] = "mcp: %s" % str(e)[:200]
        _start_worker()


# ---------------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:200]
    data = data or {}
    if action in ("", "status"):
        return status()
    if action == "spec":
        return spec()
    if action == "stamp" and method == "POST":
        body = _original_body("digests") or data
        digests = body.get("digests") if body.get("digests") is not None else body.get("digest")
        if isinstance(digests, str) and ("," in digests or "\n" in digests or " " in digests.strip()):
            digests = [x for x in re.split(r"[\s,]+", digests) if x]
        return stamp(digests, body.get("label"), api_key, _caller_ip())
    if action == "receipt":
        return receipt(data.get("code"))
    if action == "lookup":
        d = str(data.get("digest", "")).strip().lower()
        if not HEX64.match(d):
            return {"error": "bad_digest"}, 400
        rows = _db("SELECT code FROM notary_leaf WHERE digest=? AND kind='hash' ORDER BY submitted LIMIT 20", (d,))
        out = []
        for (code,) in rows:
            r, _ = receipt(code)
            out.append({"code": code, "received_utc": r.get("received_utc"), "state": r.get("state"),
                        "label": (r.get("subject") or {}).get("label"),
                        "bitcoin_block": ((r.get("batch") or {}).get("bitcoin") or {}).get("height"),
                        "receipt": "%s/n/%s" % (SITE, code)})
        return {"digest": d, "found": len(out), "receipts": out}, 200
    if action == "bundle":
        if data.get("block") not in (None, ""):
            return chain_proof(data.get("block"), api_key)
        return receipt(data.get("code"), with_bundle=True)
    if action == "hk":
        return hk_status(data.get("code"))
    if action == "checkpoints":
        return {"checkpoints": _checkpoints()}, 200
    if action == "ots":
        try:
            b = _batch_row(int(data.get("batch")))
        except Exception:
            b = None
        if not b or not b["ots"]:
            return {"error": "not_found"}, 404
        return {"batch": b["id"], "root": b["root"], "state": b["state"],
                "ots_base64": base64.b64encode(b["ots"]).decode()}, 200
    if action == "verify" and method == "POST":
        bundle = data.get("bundle") if isinstance(data.get("bundle"), dict) else data
        return FV.check(bundle, explorers=EXPLORERS), 200
    if action == "run":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return run_once(force=True), 200
    return {"error": "unknown_action", "action": action}, 404
