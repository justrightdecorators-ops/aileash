import json
import math
import time
import sqlite3
import hashlib
import threading
from collections import defaultdict, deque

DB = "aileash.db"
SAFE_COUNTRIES = {"UK", "US", "DE", "FR", "CA", "AU"}
REQUIRED_FIELDS = {"user_id", "action", "amount", "country", "device_id", "anomaly", "device_risk"}

_db_lock = threading.Lock()

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()
WINDOW_60S = defaultdict(deque)
WINDOW_5M = defaultdict(deque)
WINDOW_1H = defaultdict(deque)

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(payload): return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

def load_user(user_id):
    with _db_lock:
        row = _conn.execute("SELECT trust, last_country FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row: return {"trust": 0.5, "last_country": None}
    return {"trust": row[0], "last_country": row[1]}

def save_user(user_id, trust, country):
    with _db_lock:
        _conn.execute("""INSERT INTO users(user_id, trust, last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust, last_country=excluded.last_country""", (user_id, trust, country))
        _conn.commit()

def prune(q, seconds):
    cutoff = now() - seconds
    while q and q[0] < cutoff: q.popleft()

def update_windows(user_id):
    t = now()
    WINDOW_60S[user_id].append(t)
    WINDOW_5M[user_id].append(t)
    WINDOW_1H[user_id].append(t)
    prune(WINDOW_60S[user_id], 60)
    prune(WINDOW_5M[user_id], 300)
    prune(WINDOW_1H[user_id], 3600)

def velocity(user_id):
    return {"60s": len(WINDOW_60S[user_id]), "5m": len(WINDOW_5M[user_id]), "1h": len(WINDOW_1H[user_id])}

def compute_score(signals):
    score = 0
    score += (1 - signals["trust"]) * 0.30
    score += min(signals["v60"] / 20, 1) * 0.15
    score += min(signals["v5m"] / 50, 1) * 0.10
    score += min(signals["v1h"] / 200, 1) * 0.10
    score += min(math.log1p(signals["amount"]) / math.log1p(10000), 1) * 0.15
    score += signals["device_risk"] * 0.10
    score += signals["anomaly"] * 0.10
    if signals["country_shift"]: score += 0.10
    if signals["unsafe_country"]: score += 0.10
    return clamp(score)

def decide(score):
    if score < 0.35: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def update_trust(trust, decision):
    if decision == "ALLOW": trust += (1 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK": trust -= trust * 0.08
    return clamp(trust, 0.05, 1.0)

def explain(signals):
    reasons = []
    if signals["trust"] < 0.4: reasons.append("low_trust")
    if signals["v60"] > 10: reasons.append("velocity_spike")
    if signals["amount"] > 500: reasons.append("high_amount")
    if signals["device_risk"] > 0.5: reasons.append("risky_device")
    if signals["country_shift"]: reasons.append("country_shift")
    if signals["unsafe_country"]: reasons.append("unsafe_country")
    if signals["anomaly"] > 0.5: reasons.append("behaviour_anomaly")
    return reasons

def chain_tip():
    with _db_lock:
        row = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event, result, ts):
    prev_hash = chain_tip()
    payload = {"prev_hash": prev_hash, "ts": ts, "event": event, "result": result}
    audit_hash = sha(payload)
    with _db_lock:
        _conn.execute("""INSERT INTO audit_log(ts, user_id, event_json, result_json, prev_hash, audit_hash) VALUES(?,?,?,?,?,?)""", (ts, event["user_id"], json.dumps(event), json.dumps(result), prev_hash, audit_hash))
        _conn.commit()
    return audit_hash

def govern(event):
    missing = REQUIRED_FIELDS - event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    ts = now()
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v = velocity(event["user_id"])
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"], "v1h": v["1h"],
        "amount": event["amount"], "device_risk": event["device_risk"], "anomaly": event["anomaly"],
        "country_shift": state["last_country"] is not None and state["last_country"] != event["country"],
        "unsafe_country": event["country"] not in SAFE_COUNTRIES,
    }
    score = compute_score(signals)
    decision = decide(score)
    reasons = explain(signals)
    trust = update_trust(state["trust"], decision)
    save_user(event["user_id"], trust, event["country"])
    result = {"decision": decision, "score": round(score, 4), "trust": round(trust, 4), "reasons": reasons}
    result["audit_hash"] = append_audit(event, result, ts)
    return result
