"""
SEBDOG ENGINE v1.2.0
Local compliance engine. Runs on your hardware. Data never leaves it.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

WHAT CHANGED IN 1.2
-------------------
1. NO PHONE HOME. v1.1 called sebbi.pro on startup and every 24 hours,
   returned 403 without a valid licence and exited if it could not reach
   the server. So "sovereign" described the data and not the engine, and
   an air-gapped box could not run it at all. Licensing is now an
   Ed25519 token validated locally by sebdog_licence v2. This process
   makes no outbound call to sebbi.pro, ever. Verify that with a packet
   capture rather than taking it from a docstring.

2. IT CAN BE WITNESSED. Two new routes:
       GET  /tip               your current chain head, for peers to seal
       POST /witness/observe   seal a peer's head into your chain
   That is the whole witness protocol. Point meshwitness.py at this
   engine and your on-premise chain is sealed into chains held by
   operators neither you nor your vendor controls. A local hash chain
   proves nothing against the party who owns the file - this is what
   turns it into evidence.

3. THE SEAL RACE IS FIXED. v1.1 read the chain tip under the lock,
   released it, then took the lock again to insert. Two concurrent
   requests could read the same prev_hash and both write against it.
   Tip read, hash and insert now happen inside one lock hold, which is
   how server.py has done it since the same bug was found there.

4. /govern NO LONGER ACCEPTS AN EMPTY BEARER. v1.1 checked
   `if bearer and bearer != key`, so a request with no Authorization
   header passed straight through and was rate-limited under "default".
   Any process on the host could drive the engine. A matching bearer is
   now required.

5. BACKUPS CANNOT BE TORN. shutil.copy2 on a live WAL database can copy
   a half-written file. Backups now use sqlite3's own backup API, which
   is transactionally safe on a running database, and each backup is
   sealed into the chain - so restoring an older backup is visible
   rather than silent.

SOVEREIGNTY, STATED PRECISELY
-----------------------------
    The engine makes no outbound connection of any kind.
    Your decisions, your events and your chain stay on your disk.
    If you enable witnessing, ONE hash leaves - your chain head. It
    cannot be reversed into anything and it reveals nothing but the
    fact that your chain exists and has moved.

WHAT IT DOES NOT DO
-------------------
    It does not prove a decision was correct. Wrong answers seal as
    cleanly as right ones.
    It does not prove your records are complete. A chain can be intact
    and simply not contain what matters.
    Witnessing does not make your log true. It makes it impossible to
    rewrite quietly after the fact.

RUN IT
    python3 sebdog_engine.py --token <your licence token>
    python3 sebdog_engine.py --token-file licence.txt --port 9090
"""

import argparse
import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

try:
    import sebdog_licence as licence
except ImportError:
    licence = None

VERSION = "1.2.0"
HOME = "https://sebbi.pro"
DB_FILE = "sebdog_audit.db"
CHAIN_NAME = "sebdog-local"
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK",
        "FI", "IE", "NZ"}
REQ = {"user_id", "action", "amount", "country", "device_id", "anomaly",
       "device_risk"}
HEX64 = set("0123456789abcdef")

_db_lock = threading.Lock()
_key_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

_licence = {"valid": False, "plan": "free", "product": "aileash",
            "devices": 1, "email": "", "checked_at": 0, "key": "",
            "expires": 0, "grace": False}

_conn = None


# ==============================================================================
# LICENCE - validated locally, no network
# ==============================================================================

def load_licence(token, pubkey=None):
    """Validate an Ed25519 licence token offline. No outbound call."""
    global _licence
    if licence is None:
        print("[SEBDOG] sebdog_licence.py not found next to this file.",
              flush=True)
        return False
    data, err = licence.validate_token(token, pubkey)
    if err:
        explain = {
            "no_public_key": "No licence public key is configured. Set "
                             "SEBDOG_LICENCE_PUBKEY or edit LICENCE_PUBKEY "
                             "in sebdog_licence.py.",
            "invalid_signature": "This token was not signed by the expected "
                                 "key, or it has been altered.",
            "token_expired": "This licence expired more than 7 days ago.",
            "version_mismatch": "This is an old v1 token. v1 tokens were "
                                "verifiable by anyone holding the shared "
                                "secret and have been withdrawn. Request a "
                                "replacement.",
            "invalid_format": "This does not decode as a licence token.",
        }.get(err, err)
        print("[SEBDOG] Licence rejected: %s\n           %s" % (err, explain),
              flush=True)
        return False

    _licence.update({
        "valid": True, "plan": data.get("plan", "free"),
        "devices": data.get("devices", 1), "email": data.get("email", ""),
        "key": data.get("key", ""), "expires": data.get("expires", 0),
        "checked_at": time.time(),
        "grace": licence.is_in_grace_period(data),
    })
    days = licence.days_until_expiry(data)
    print("[SEBDOG] Licence valid, checked locally. Plan:%s Devices:%s"
          % (_licence["plan"], _licence["devices"]), flush=True)
    if _licence["grace"]:
        print("[SEBDOG] EXPIRED - running on the 7 day grace period. Renew "
              "at %s" % HOME, flush=True)
    elif days < 30:
        print("[SEBDOG] Licence expires in %d days." % days, flush=True)
    return True


def licence_watch():
    """Re-check expiry hourly against the local clock. Still no network."""
    while True:
        time.sleep(3600)
        if _licence["expires"] and _licence["expires"] < time.time():
            if not _licence["grace"]:
                _licence["grace"] = True
                print("[SEBDOG] Licence has expired. 7 day grace period "
                      "started. Renew at %s" % HOME, flush=True)
            if _licence["expires"] + licence.GRACE_SECONDS < time.time():
                _licence["valid"] = False
                print("[SEBDOG] Grace period over. Governing is disabled; "
                      "your chain and data are untouched.", flush=True)


# ==============================================================================
# DATABASE + BACKUP
# ==============================================================================

def get_conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5,
        last_country TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT,
        audit_hash TEXT UNIQUE)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.execute("""CREATE TABLE IF NOT EXISTS chain_snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL,
        block_count INTEGER, tip_hash TEXT, snapshot_file TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS witness_seen(
        id INTEGER PRIMARY KEY AUTOINCREMENT, peer TEXT, tip TEXT,
        url TEXT, observed REAL, audit_hash TEXT,
        UNIQUE(peer, tip))""")
    c.commit()
    return c


def init_db():
    global _conn
    _conn = get_conn()


def backup_db():
    """
    Timestamped backup using sqlite3's own backup API.

    v1.1 used shutil.copy2, which on a live WAL database can copy a file
    mid-write and produce a backup that will not open. The backup API is
    transactionally consistent against a running connection.

    The backup is then SEALED into the chain, so restoring an older
    database later is detectable rather than silent.
    """
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)),
                              "sebdog_backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(backup_dir, "sebdog_audit_%s.db" % stamp)
    try:
        with _db_lock:
            dest = sqlite3.connect(path)
            _conn.backup(dest)
            dest.close()
            blocks = _conn.execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()[0]
            tip = _conn.execute("SELECT audit_hash FROM audit_log "
                                "ORDER BY id DESC LIMIT 1").fetchone()
            tip_hash = tip[0] if tip else "GENESIS"
            _conn.execute("INSERT INTO chain_snapshots(ts,block_count,"
                          "tip_hash,snapshot_file) VALUES(?,?,?,?)",
                          (time.time(), blocks, tip_hash, path))
            _conn.commit()

        # sealed outside the lock - seal() takes it itself
        seal({"user_id": "sebdog", "action": "backup_created",
              "amount": 0, "country": "UK", "device_id": "sebdog",
              "anomaly": 0, "device_risk": 0},
             {"decision": "BACKUP", "score": 0, "version": VERSION,
              "blocks_at_backup": blocks, "tip_at_backup": tip_hash,
              "note": "backup sealed so a later restore of an older "
                      "database is visible in the chain"},
             time.time())
        print("[SEBDOG] Backup created and sealed: %s (%d blocks)"
              % (path, blocks), flush=True)
        _cleanup_old_backups(backup_dir)
    except Exception as e:
        print("[SEBDOG] Backup failed: %s" % e, flush=True)


def _cleanup_old_backups(backup_dir, keep=7):
    try:
        files = sorted(os.path.join(backup_dir, f)
                       for f in os.listdir(backup_dir)
                       if f.startswith("sebdog_audit_") and f.endswith(".db"))
        for old in files[:-keep]:
            os.remove(old)
    except Exception:
        pass


def backup_loop():
    while True:
        time.sleep(86400)
        backup_db()


def restore_latest_backup():
    backup_dir = os.path.join(os.path.dirname(os.path.abspath(DB_FILE)),
                              "sebdog_backups")
    if not os.path.exists(backup_dir):
        return False
    files = sorted(os.path.join(backup_dir, f)
                   for f in os.listdir(backup_dir)
                   if f.startswith("sebdog_audit_") and f.endswith(".db"))
    if not files:
        return False
    try:
        shutil.copy2(files[-1], DB_FILE)
        print("[SEBDOG] Restored from backup: %s" % files[-1], flush=True)
        return True
    except Exception as e:
        print("[SEBDOG] Restore failed: %s" % e, flush=True)
        return False


def list_snapshots():
    with _db_lock:
        rows = _conn.execute(
            "SELECT ts,block_count,tip_hash,snapshot_file FROM "
            "chain_snapshots ORDER BY id DESC LIMIT 10").fetchall()
    return [{"ts": r[0], "blocks": r[1], "tip": r[2], "file": r[3]}
            for r in rows]


# ==============================================================================
# RATE LIMITING
# ==============================================================================

def check_rate(key):
    t = time.time()
    with _key_lock:
        w = _key_wins[key]
        while w["min"] and w["min"][0] < t - 60:
            w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600:
            w["hour"].popleft()
        if len(w["min"]) >= 60:
            return False, "rate_limit_minute"
        if len(w["hour"]) >= 1000:
            return False, "rate_limit_hour"
        w["min"].append(t)
        w["hour"].append(t)
        return True, None


# ==============================================================================
# CORE ENGINE
# ==============================================================================

def now():
    return time.time()


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


def upd_vel(uid):
    t = now()
    for q in (W60[uid], W5M[uid], W1H[uid]):
        q.append(t)
    c = now()
    W60[uid] = deque(x for x in W60[uid] if x >= c - 60)
    W5M[uid] = deque(x for x in W5M[uid] if x >= c - 300)
    W1H[uid] = deque(x for x in W1H[uid] if x >= c - 3600)


def vel(uid):
    return {"60s": len(W60[uid]), "5m": len(W5M[uid]), "1h": len(W1H[uid])}


def load_user(uid):
    with _db_lock:
        r = _conn.execute("SELECT trust,last_country FROM users WHERE "
                          "user_id=?", (uid,)).fetchone()
    return ({"trust": r[0], "last_country": r[1]} if r
            else {"trust": 0.5, "last_country": None})


def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,"
            "last_country=excluded.last_country", (uid, trust, country))
        _conn.commit()


def score_event(s):
    reasons = []
    sc = (1 - s["trust"]) * 0.30
    v60 = s["v60"]
    sc += min(v60 / 20, 1) * 0.15
    if v60 > 10:
        reasons.append("velocity_spike")
    sc += min(s["v5m"] / 50, 1) * 0.10 + min(s["v1h"] / 200, 1) * 0.10
    amt = float(s.get("amount", 0))
    sc += min(math.log1p(amt) / math.log1p(10000), 1) * 0.15
    if amt > 500:
        reasons.append("high_amount")
    dr = float(s.get("device_risk", 0))
    sc += dr * 0.10
    if dr > 0.5:
        reasons.append("risky_device")
    an = float(s.get("anomaly", 0))
    sc += an * 0.10
    if an > 0.5:
        reasons.append("behaviour_anomaly")
    if s.get("country_shift"):
        sc += 0.10
        reasons.append("country_shift")
    if s.get("unsafe_country"):
        sc += 0.10
        reasons.append("unsafe_country")
    if s["trust"] < 0.4:
        reasons.append("low_trust")
    return round(clamp(sc), 4), reasons


def decide(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def upd_trust(t, d):
    if d == "ALLOW":
        t += (1 - t) * 0.01
    elif d == "CHALLENGE":
        t -= t * 0.02
    elif d == "BLOCK":
        t -= t * 0.08
    return clamp(t, 0.05, 1.0)


def chain_tip():
    with _db_lock:
        r = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id "
                          "DESC LIMIT 1").fetchone()
    return r[0] if r else "GENESIS"


def chain_head():
    """Tip plus height, in one lock hold, for /tip."""
    with _db_lock:
        r = _conn.execute("SELECT audit_hash,ts,id FROM audit_log "
                          "ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def seal(event, result, ts):
    """
    Tip read, hash and insert inside ONE lock hold.

    v1.1 read the tip under the lock, released it, then re-acquired to
    insert. Between those two points another thread could read the same
    prev_hash, and both writes would claim the same predecessor. The
    same bug was found and fixed in server.py; this is that fix.
    """
    with _db_lock:
        r = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id "
                          "DESC LIMIT 1").fetchone()
        prev = r[0] if r else "GENESIS"
        h = sha({"prev_hash": prev, "ts": ts, "event": event,
                 "result": result})
        _conn.execute(
            "INSERT INTO audit_log(ts,user_id,event_json,result_json,"
            "prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result),
             prev, h))
        _conn.commit()
    return h


def verify_chain():
    with _db_lock:
        rows = _conn.execute(
            "SELECT event_json,result_json,prev_hash,audit_hash,ts FROM "
            "audit_log ORDER BY id ASC").fetchall()
    if not rows:
        return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        p = {"prev_hash": row[2], "ts": row[4],
             "event": json.loads(row[0]), "result": json.loads(row[1])}
        if sha(p) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at": i,
                    "message": "Tampered at block %d" % i}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "tip": rows[-1][3],
            "message": "Chain intact"}


def govern(event):
    missing = REQ - event.keys()
    if missing:
        raise ValueError("Missing fields: %s" % missing)
    if not _licence["valid"]:
        return {"error": "licence_invalid",
                "message": "A valid licence token is required. Get one at "
                           "%s. Your chain and data are untouched." % HOME}, 403
    ts = now()
    uid = event["user_id"]
    state = load_user(uid)
    upd_vel(uid)
    v = vel(uid)
    country = event["country"]
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"],
        "v1h": v["1h"], "amount": float(event.get("amount", 0)),
        "device_risk": float(event.get("device_risk", 0)),
        "anomaly": float(event.get("anomaly", 0)),
        "country_shift": (state["last_country"] is not None
                          and state["last_country"] != country),
        "unsafe_country": country not in SAFE,
    }
    sc, reasons = score_event(signals)
    dec = decide(sc)
    trust = upd_trust(state["trust"], dec)
    save_user(uid, trust, country)
    result = {"decision": dec, "score": sc, "trust": round(trust, 4),
              "reasons": reasons, "version": VERSION, "engine": "sebdog",
              "local": True, "timestamp": ts}
    result["audit_hash"] = seal(event, result, ts)
    return result, 200


# ==============================================================================
# WITNESSING
#
# A local hash chain proves nothing against the person who owns the file.
# These two routes are what let somebody else hold your history.
# ==============================================================================

def observe(data):
    """Seal a peer's chain head into this chain. Never rejects a
    well-formed submission - the record says what arrived, not whether
    we approve of it."""
    peer = str(data.get("chain") or data.get("peer") or "").strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works."}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if len(tip) != 64 or not all(c in HEX64 for c in tip):
        return {"error": "invalid_tip",
                "message": "A tip is 64 hex characters."}, 400
    url = str(data.get("url") or "").strip()[:400]

    with _db_lock:
        seen = _conn.execute("SELECT observed,audit_hash FROM witness_seen "
                             "WHERE peer=? AND tip=?", (peer, tip)).fetchone()
    if seen:
        return {"witnessed": True, "already_seen": True, "peer": peer,
                "tip": tip, "observed_at": seen[0],
                "sealed_in_our_chain": seen[1],
                "message": "Already witnessed. Their chain has not moved, "
                           "or this is a replay."}, 200

    ts = now()
    h = seal({"user_id": "witness:" + peer, "action": "peer_tip_observed",
              "amount": 0, "country": "UK", "device_id": "witness",
              "anomaly": 0, "device_risk": 0},
             {"decision": "WITNESS_SEALED", "score": 0, "version": VERSION,
              "peer": peer, "peer_tip": tip, "peer_url": url or None,
              "timestamp": ts,
              "note": "a peer's chain head, sealed here. This records what "
                      "they handed us and when. It says nothing about "
                      "whether their chain is honest."}, ts)
    with _db_lock:
        _conn.execute("INSERT OR IGNORE INTO witness_seen(peer,tip,url,"
                      "observed,audit_hash) VALUES(?,?,?,?,?)",
                      (peer, tip, url or None, ts, h))
        _conn.commit()

    our, _t, height = chain_head()
    return {"witnessed": True, "peer": peer, "tip": tip, "observed_at": ts,
            "sealed_in_our_chain": h, "our_tip_now": our,
            "our_height": height, "engine": "sebdog",
            "what_this_proves": "That this value was handed to us at this "
                                "time and sealed into a chain we control. "
                                "Nothing about whether it is true."}, 200


# ==============================================================================
# HTTP
# ==============================================================================

def send_json(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)


def read_body(h):
    n = int(h.headers.get("Content-Length", 0) or 0)
    if n:
        try:
            return json.loads(h.rfile.read(n))
        except Exception:
            return {}
    return {}


def get_bearer(h):
    auth = h.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return h.headers.get("X-API-Key", "").strip()


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"

        if path == "/tip":
            # The witness protocol's first call. Public on purpose: a peer
            # cannot seal what it cannot read, and a chain head reveals
            # nothing but that the chain exists and has moved.
            tip, ts, height = chain_head()
            send_json(self, {
                "chain": CHAIN_NAME, "tip": tip, "height": height,
                "sealed_at": ts, "engine": "sebdog", "version": VERSION,
                "note": "Seal this into your own chain. Hand us yours at "
                        "POST /witness/observe and we will seal it here.",
                "what_this_is": "The head of a hash chain held on this "
                                "operator's own hardware. It is a hash and "
                                "nothing else - no event, no record, no "
                                "personal data, and it cannot be reversed.",
            })

        elif path == "/health":
            send_json(self, {
                "status": "ok", "version": VERSION, "engine": "sebdog",
                "local": True, "phones_home": False,
                "licence": {"valid": _licence["valid"],
                            "plan": _licence["plan"],
                            "devices": _licence["devices"],
                            "email": _licence["email"],
                            "in_grace_period": _licence["grace"],
                            "validated": "locally, no network"}})

        elif path == "/verify-chain":
            send_json(self, verify_chain())

        elif path == "/stats":
            with _db_lock:
                blocks = _conn.execute(
                    "SELECT COUNT(*) FROM audit_log").fetchone()[0]
                users = _conn.execute(
                    "SELECT COUNT(*) FROM users").fetchone()[0]
                peers = _conn.execute(
                    "SELECT COUNT(DISTINCT peer) FROM witness_seen"
                ).fetchone()[0]
            send_json(self, {"audit_blocks": blocks, "users_tracked": users,
                             "peers_witnessed": peers, "version": VERSION,
                             "engine": "sebdog",
                             "licence_valid": _licence["valid"]})

        elif path == "/peers":
            with _db_lock:
                rows = _conn.execute(
                    "SELECT peer,COUNT(*),MAX(observed),MAX(url) FROM "
                    "witness_seen GROUP BY peer ORDER BY MAX(observed) DESC"
                ).fetchall()
            send_json(self, {
                "count": len(rows),
                "peers": [{"chain": r[0], "observations": r[1],
                           "last_seen": r[2], "tip_url": r[3]}
                          for r in rows],
                "note": "Chains whose heads we have sealed here. Being "
                        "listed is not endorsement of anything in their "
                        "chain."})

        elif path == "/snapshots":
            send_json(self, {"snapshots": list_snapshots()})

        elif path == "/backup":
            # keyed - a backup writes to disk and seals a block
            if get_bearer(self) != _licence["key"]:
                send_json(self, {"error": "invalid_api_key"}, 401)
                return
            backup_db()
            send_json(self, {"ok": True, "message": "Backup created and "
                                                    "sealed"})
        else:
            send_json(self, {"error": "not_found",
                             "routes": ["/tip", "/health", "/verify-chain",
                                        "/stats", "/peers", "/snapshots",
                                        "/backup (keyed)",
                                        "POST /govern (keyed)",
                                        "POST /witness/observe"]}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)

        if path in ("/witness/observe", "/api/witness/observe"):
            # Open by design. A witnessing endpoint that needs an account
            # is a customer list, not a witness network.
            ok, ec = check_rate("witness:" + str(self.client_address[0]))
            if not ok:
                send_json(self, {"error": ec}, 429)
                return
            try:
                result, status = observe(data)
                send_json(self, result, status)
            except Exception as e:
                send_json(self, {"error": "internal", "detail": str(e)}, 500)
            return

        if path in ("/govern", "/api/govern"):
            # v1.1 allowed a missing bearer through. It does not now.
            bearer = get_bearer(self)
            if not bearer or bearer != _licence["key"]:
                send_json(self, {"error": "invalid_api_key",
                                 "message": "Send your licence key as "
                                            "Authorization: Bearer <key>."},
                          401)
                return
            ok, ec = check_rate(bearer)
            if not ok:
                send_json(self, {"error": ec}, 429)
                return
            try:
                result, status = govern(data)
                send_json(self, result, status)
            except ValueError as e:
                send_json(self, {"error": str(e)}, 400)
            except Exception as e:
                send_json(self, {"error": "internal", "detail": str(e)}, 500)
            return

        send_json(self, {"error": "not_found"}, 404)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    p = argparse.ArgumentParser(
        description="Sebdog Engine - local compliance engine, no phone home")
    p.add_argument("--token", help="Your licence token from sebbi.pro")
    p.add_argument("--token-file", help="File containing the licence token")
    p.add_argument("--pubkey", help="Licence public key hex (overrides the "
                                    "built-in one; for testing)")
    p.add_argument("--port", type=int, default=9090)
    p.add_argument("--db", default="sebdog_audit.db")
    p.add_argument("--chain", default=None,
                   help="Chain name other operators record you as")
    p.add_argument("--backup-on-start", action="store_true")
    args = p.parse_args()

    global DB_FILE, CHAIN_NAME
    DB_FILE = args.db
    if args.chain:
        CHAIN_NAME = args.chain.strip().lower()

    token = args.token
    if not token and args.token_file:
        try:
            with open(args.token_file, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except Exception as e:
            print("[SEBDOG] Could not read token file: %s" % e, flush=True)
            sys.exit(1)
    if not token:
        token = os.environ.get("SEBDOG_TOKEN", "").strip()
    if not token:
        print("[SEBDOG] No licence token. Pass --token, --token-file, or "
              "set SEBDOG_TOKEN.", flush=True)
        sys.exit(1)

    print("[SEBDOG] Sebdog Engine v%s starting..." % VERSION, flush=True)

    if not os.path.exists(DB_FILE):
        print("[SEBDOG] Database not found. Checking for backups...",
              flush=True)
        if not restore_latest_backup():
            print("[SEBDOG] No backup found. Starting a fresh chain.",
                  flush=True)

    init_db()

    print("[SEBDOG] Validating licence locally. No network call is made.",
          flush=True)
    if not load_licence(token, args.pubkey):
        print("[SEBDOG] Licence validation failed. Get a token at %s" % HOME,
              flush=True)
        sys.exit(1)

    if licence is not None:
        try:
            licence.save_licence_locally(DB_FILE, token, {
                "key": _licence["key"], "devices": _licence["devices"],
                "plan": _licence["plan"], "email": _licence["email"],
                "issued": 0, "expires": _licence["expires"]})
        except Exception:
            pass

    if args.backup_on_start:
        backup_db()

    threading.Thread(target=licence_watch, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()

    srv = ThreadedServer(("0.0.0.0", args.port), Handler)
    base = "http://localhost:%d" % args.port
    print("[SEBDOG] Engine running on port %d" % args.port, flush=True)
    print("[SEBDOG] POST %s/govern            (needs your key)" % base,
          flush=True)
    print("[SEBDOG] GET  %s/tip               (your chain head)" % base,
          flush=True)
    print("[SEBDOG] POST %s/witness/observe   (peers seal their head here)"
          % base, flush=True)
    print("[SEBDOG] GET  %s/verify-chain      (rewalks every block)" % base,
          flush=True)
    print("[SEBDOG] GET  %s/peers             (who you have witnessed)"
          % base, flush=True)
    print("[SEBDOG] Backups: ./sebdog_backups/ daily, last 7 kept, sealed",
          flush=True)
    print("[SEBDOG] This process makes no outbound connection. Check it "
          "with tcpdump if you like.", flush=True)
    print("[SEBDOG] To be witnessed by others, point meshwitness.py at "
          "this engine:", flush=True)
    print("[SEBDOG]   MESH_TIP_URL=<your public url>/tip", flush=True)
    print("[SEBDOG]   MESH_SEAL_URL=<your public url>/witness/observe",
          flush=True)
    print("[SEBDOG]   MESH_CHAIN=%s" % CHAIN_NAME, flush=True)

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("[SEBDOG] Shutting down.", flush=True)


if __name__ == "__main__":
    main()
