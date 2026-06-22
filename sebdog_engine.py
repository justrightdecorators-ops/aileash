# ==============================================================================
# SEBDOG ENGINE v1.0.0
# AILeash Standalone Compliance Engine
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
#
# This engine runs entirely inside your own infrastructure.
# Your data never leaves your network.
# Licence validated against sebbi.pro on startup only.
# All decisions are local. Sub-20ms. No network hop per decision.
#
# Usage:
#   python sebdog_engine.py --key YOUR_API_KEY --port 9090
#
# Then call it locally:
#   POST http://localhost:9090/govern
#   Authorization: Bearer YOUR_API_KEY
# ==============================================================================

import json, math, time, sqlite3, hashlib, threading, argparse, sys, os
import urllib.request, urllib.parse, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

VERSION = "1.0.0"
HOME = "https://sebbi.pro"
VALIDATE_URL = HOME + "/api/validate-engine"
DB_FILE = "sebdog_audit.db"
SAFE = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ = {"user_id","action","amount","country","device_id","anomaly","device_risk"}

_db_lock = threading.Lock()
_key_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

_licence = {
    "valid": False,
    "plan": "free",
    "product": "aileash",
    "devices": 1,
    "email": "",
    "checked_at": 0,
    "key": ""
}

# ==============================================================================
# LICENCE VALIDATION
# Phones home to sebbi.pro once on startup, then every 24 hours.
# All decisions run locally between checks.
# ==============================================================================

def validate_licence(api_key):
    global _licence
    try:
        req = urllib.request.Request(
            VALIDATE_URL,
            method="POST",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json"
            },
            data=json.dumps({}).encode()
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data.get("valid"):
            _licence["valid"] = True
            _licence["plan"] = data.get("plan", "free")
            _licence["product"] = data.get("product", "aileash")
            _licence["devices"] = data.get("devices", 1)
            _licence["email"] = data.get("email", "")
            _licence["checked_at"] = time.time()
            _licence["key"] = api_key
            print(f"[SEBDOG] Licence valid. Plan:{_licence['plan']} Devices:{_licence['devices']} Email:{_licence['email']}", flush=True)
            return True
        else:
            err = data.get("error", "unknown")
            print(f"[SEBDOG] Licence rejected: {err}", flush=True)
            if err == "quota_exceeded":
                print(f"[SEBDOG] Free quota used. Upgrade at {HOME}/#pricing", flush=True)
            _licence["valid"] = False
            return False
    except Exception as e:
        print(f"[SEBDOG] Licence check failed: {e}", flush=True)
        if _licence["valid"] and (time.time() - _licence["checked_at"]) < 86400:
            print("[SEBDOG] Using cached licence (within 24h grace)", flush=True)
            return True
        return False

def revalidate_loop(api_key):
    while True:
        time.sleep(86400)
        validate_licence(api_key)

# ==============================================================================
# DATABASE
# Local SQLite — audit chain lives on your own machine.
# ==============================================================================

def get_conn():
    c = sqlite3.connect(DB_FILE, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.commit()
    return c

_conn = None

def init_db():
    global _conn
    _conn = get_conn()

# ==============================================================================
# RATE LIMITING
# ==============================================================================

def check_rate(key):
    t = time.time()
    with _key_lock:
        w = _key_wins[key]
        while w["min"] and w["min"][0] < t - 60: w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600: w["hour"].popleft()
        if len(w["min"]) >= 60: return False, "rate_limit_minute"
        if len(w["hour"]) >= 1000: return False, "rate_limit_hour"
        w["min"].append(t)
        w["hour"].append(t)
        return True, None

# ==============================================================================
# CORE ENGINE
# 9-signal weighted scoring. EWMA trust decay. Deterministic decisioning.
# ==============================================================================

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(p): return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def upd_vel(uid):
    t = now()
    for q in [W60[uid], W5M[uid], W1H[uid]]: q.append(t)
    c = now()
    W60[uid] = deque(x for x in W60[uid] if x >= c - 60)
    W5M[uid] = deque(x for x in W5M[uid] if x >= c - 300)
    W1H[uid] = deque(x for x in W1H[uid] if x >= c - 3600)

def vel(uid): return {"60s": len(W60[uid]), "5m": len(W5M[uid]), "1h": len(W1H[uid])}

def load_user(uid):
    with _db_lock:
        r = _conn.execute("SELECT trust, last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"trust": r[0], "last_country": r[1]} if r else {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id, trust, last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust, last_country=excluded.last_country",
            (uid, trust, country)
        )
        _conn.commit()

def score_event(s):
    reasons = []
    sc = (1 - s["trust"]) * 0.30
    v60 = s["v60"]
    sc += min(v60 / 20, 1) * 0.15
    if v60 > 10: reasons.append("velocity_spike")
    sc += min(s["v5m"] / 50, 1) * 0.10 + min(s["v1h"] / 200, 1) * 0.10
    amt = float(s.get("amount", 0))
    sc += min(math.log1p(amt) / math.log1p(10000), 1) * 0.15
    if amt > 500: reasons.append("high_amount")
    dr = float(s.get("device_risk", 0))
    sc += dr * 0.10
    if dr > 0.5: reasons.append("risky_device")
    an = float(s.get("anomaly", 0))
    sc += an * 0.10
    if an > 0.5: reasons.append("behaviour_anomaly")
    if s.get("country_shift"): sc += 0.10; reasons.append("country_shift")
    if s.get("unsafe_country"): sc += 0.10; reasons.append("unsafe_country")
    if s["trust"] < 0.4: reasons.append("low_trust")
    return round(clamp(sc), 4), reasons

def decide(sc):
    if sc < 0.35: return "ALLOW"
    if sc < 0.70: return "CHALLENGE"
    return "BLOCK"

def upd_trust(t, d):
    if d == "ALLOW": t += (1 - t) * 0.01
    elif d == "CHALLENGE": t -= t * 0.02
    elif d == "BLOCK": t -= t * 0.08
    return clamp(t, 0.05, 1.0)

def chain_tip():
    with _db_lock:
        r = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else "GENESIS"

def seal(event, result, ts):
    prev = chain_tip()
    h = sha({"prev_hash": prev, "ts": ts, "event": event, "result": result})
    with _db_lock:
        _conn.execute(
            "INSERT INTO audit_log(ts, user_id, event_json, result_json, prev_hash, audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result), prev, h)
        )
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows = _conn.execute(
            "SELECT event_json, result_json, prev_hash, audit_hash, ts FROM audit_log ORDER BY id ASC"
        ).fetchall()
    if not rows: return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        p = {"prev_hash": row[2], "ts": row[4], "event": json.loads(row[0]), "result": json.loads(row[1])}
        if sha(p) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at": i, "message": f"Tampered at block {i}"}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "tip": rows[-1][3], "message": "Chain intact"}

def govern(event):
    missing = REQ - event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    if not _licence["valid"]:
        return {"error": "licence_invalid", "message": f"Valid API key required. Get yours at {HOME}"}, 403
    ts = now()
    uid = event["user_id"]
    state = load_user(uid)
    upd_vel(uid)
    v = vel(uid)
    country = event["country"]
    signals = {
        "trust": state["trust"],
        "v60": v["60s"], "v5m": v["5m"], "v1h": v["1h"],
        "amount": float(event.get("amount", 0)),
        "device_risk": float(event.get("device_risk", 0)),
        "anomaly": float(event.get("anomaly", 0)),
        "country_shift": state["last_country"] is not None and state["last_country"] != country,
        "unsafe_country": country not in SAFE
    }
    sc, reasons = score_event(signals)
    dec = decide(sc)
    trust = upd_trust(state["trust"], dec)
    save_user(uid, trust, country)
    result = {
        "decision": dec,
        "score": sc,
        "trust": round(trust, 4),
        "reasons": reasons,
        "version": VERSION,
        "engine": "sebdog",
        "local": True,
        "timestamp": ts
    }
    result["audit_hash"] = seal(event, result, ts)
    return result, 200

# ==============================================================================
# HTTP SERVER
# Lightweight local server. Runs on your own machine or container.
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
    n = int(h.headers.get("Content-Length", 0))
    if n:
        try: return json.loads(h.rfile.read(n))
        except: return {}
    return {}

def get_bearer(h):
    auth = h.headers.get("Authorization", "")
    if auth.startswith("Bearer "): return auth[7:]
    return h.headers.get("X-API-Key", "").strip()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            send_json(self, {
                "status": "ok",
                "version": VERSION,
                "engine": "sebdog",
                "local": True,
                "licence": {
                    "valid": _licence["valid"],
                    "plan": _licence["plan"],
                    "devices": _licence["devices"],
                    "email": _licence["email"]
                }
            })
        elif path == "/verify-chain":
            send_json(self, verify_chain())
        elif path == "/stats":
            with _db_lock:
                blocks = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                users = _conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            send_json(self, {
                "audit_blocks": blocks,
                "users_tracked": users,
                "version": VERSION,
                "engine": "sebdog",
                "licence_valid": _licence["valid"]
            })
        else:
            send_json(self, {"error": "not_found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)

        if path in ("/govern", "/api/govern"):
            bearer = get_bearer(self)
            if bearer and bearer != _licence["key"]:
                send_json(self, {"error": "invalid_api_key"}, 401)
                return
            ok, ec = check_rate(bearer or "default")
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
        else:
            send_json(self, {"error": "not_found"}, 404)

class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Sebdog Engine — AILeash local compliance engine")
    parser.add_argument("--key", required=True, help="Your AILeash API key from sebbi.pro")
    parser.add_argument("--port", type=int, default=9090, help="Port to run on (default: 9090)")
    parser.add_argument("--db", default="sebdog_audit.db", help="SQLite audit database path")
    args = parser.parse_args()

    global DB_FILE
    DB_FILE = args.db

    print(f"[SEBDOG] Sebdog Engine v{VERSION} starting...", flush=True)
    print(f"[SEBDOG] Validating licence with sebbi.pro...", flush=True)

    init_db()

    if not validate_licence(args.key):
        print(f"[SEBDOG] Licence validation failed. Get your key at {HOME}", flush=True)
        sys.exit(1)

    threading.Thread(target=revalidate_loop, args=(args.key,), daemon=True).start()

    server = ThreadedServer(("0.0.0.0", args.port), Handler)
    print(f"[SEBDOG] Engine running on port {args.port}", flush=True)
    print(f"[SEBDOG] POST http://localhost:{args.port}/govern", flush=True)
    print(f"[SEBDOG] GET  http://localhost:{args.port}/health", flush=True)
    print(f"[SEBDOG] GET  http://localhost:{args.port}/verify-chain", flush=True)
    print(f"[SEBDOG] Audit chain: {args.db}", flush=True)
    print(f"[SEBDOG] All decisions are local. No data leaves your network.", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[SEBDOG] Shutting down.", flush=True)

if __name__ == "__main__":
    main()
