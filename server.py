import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets, base64
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "2.1.0"
HOST            = os.environ.get("HOST", "https://sebbi.pro")
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA      = 100
STRIPE_PRICE_ID = ""
_db_lock        = threading.Lock()

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT UNIQUE, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0, free_quota INTEGER DEFAULT 100, plan_type TEXT DEFAULT 'free')")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()

def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET:
        return None
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET, "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return None
    except Exception as e:
        print("Stripe error: " + str(e), flush=True)
        return None

def setup_stripe():
    global STRIPE_PRICE_ID
    if not STRIPE_SECRET:
        print("WARNING: No STRIPE_SECRET set.", flush=True)
        return
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row and row[0]:
        STRIPE_PRICE_ID = row[0]
        print("Stripe ready: " + STRIPE_PRICE_ID, flush=True)
        return
    print("Setting up Stripe...", flush=True)
    product = stripe_call("POST", "/products", {"name": "AILeash Professional", "description": "Unlimited AI governance. EU AI Act compliant."})
    if not product or "id" not in product:
        print("Stripe product failed: " + str(product), flush=True)
        return
    price = stripe_call("POST", "/prices", {"product": product["id"], "currency": "gbp", "unit_amount": 4900, "recurring[interval]": "month"})
    if not price or "id" not in price:
        print("Stripe price failed: " + str(price), flush=True)
        return
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()
    print("Stripe ready: " + STRIPE_PRICE_ID, flush=True)

def create_api_key(email, plan_type="free"):
    email = str(email).strip().lower()
    if not email or "@" not in email:
        return None, "invalid_email"
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("INSERT INTO api_keys (key,email,stripe_customer,actions_used,created,active,is_paid,free_quota,plan_type) VALUES(?,?,?,?,?,?,?,?,?)",
                (key, email, "", 0, time.time(), 1, 1 if plan_type == "paid" else 0, FREE_QUOTA, plan_type))
            _conn.commit()
        except sqlite3.IntegrityError:
            return None, "email_exists"
    return key, None

def get_key_info(key):
    with _db_lock:
        return _conn.execute("SELECT email,actions_used,active,is_paid,free_quota,plan_type FROM api_keys WHERE key=?", (key,)).fetchone()

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?", (key,))
        _conn.commit()

WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(p): return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def update_windows(uid):
    t = now()
    for q in [WINDOW_60S[uid], WINDOW_5M[uid], WINDOW_1H[uid]]:
        q.append(t)
    c60 = t-60;  c5m = t-300;  c1h = t-3600
    while WINDOW_60S[uid] and WINDOW_60S[uid][0] < c60: WINDOW_60S[uid].popleft()
    while WINDOW_5M[uid]  and WINDOW_5M[uid][0]  < c5m: WINDOW_5M[uid].popleft()
    while WINDOW_1H[uid]  and WINDOW_1H[uid][0]  < c1h: WINDOW_1H[uid].popleft()

def velocity(uid):
    return {"60s": len(WINDOW_60S[uid]), "5m": len(WINDOW_5M[uid]), "1h": len(WINDOW_1H[uid])}

def load_user(uid):
    with _db_lock:
        row = _conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"trust": row[0], "last_country": row[1]} if row else {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country", (uid, trust, country))
        _conn.commit()

def compute_score(s):
    score = 0
    score += (1 - s["trust"]) * 0.30
    score += min(s["v60"] / 20, 1) * 0.15
    score += min(s["v5m"] / 50, 1) * 0.10
    score += min(s["v1h"] / 200, 1) * 0.10
    score += min(math.log1p(s["amount"]) / math.log1p(10000), 1) * 0.15
    score += s["device_risk"] * 0.10
    score += s["anomaly"] * 0.10
    if s["country_shift"]: score += 0.10
    if s["unsafe_country"]: score += 0.10
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

def explain(s):
    r = []
    if s["trust"] < 0.4: r.append("low_trust")
    if s["v60"] > 10: r.append("velocity_spike")
    if s["amount"] > 500: r.append("high_amount")
    if s["device_risk"] > 0.5: r.append("risky_device")
    if s["country_shift"]: r.append("country_shift")
    if s["unsafe_country"]: r.append("unsafe_country")
    if s["anomaly"] > 0.5: r.append("behaviour_anomaly")
    return r

def chain_tip():
    with _db_lock:
        row = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event, result, ts):
    prev = chain_tip()
    h = sha({"prev_hash": prev, "ts": ts, "event": event, "result": result})
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result), prev, h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows = _conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows:
        return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        payload = {"prev_hash": row[2], "ts": row[4], "event": json.loads(row[0]), "result": json.loads(row[1])}
        if sha(payload) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at_block": i, "message": "Chain broken at block " + str(i)}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "message": "Chain intact"}

def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - event.keys()
    if missing:
        raise ValueError("Missing fields: " + str(missing))
    if api_key:
        key_info = get_key_info(api_key)
        if not key_info:
            return {"error": "invalid_api_key"}, 401
        email, actions_used, active, is_paid, free_quota, plan_type = key_info
        if not active:
            return {"error": "account_inactive"}, 403
        if not is_paid and actions_used >= free_quota:
            return {"error": "quota_exceeded", "message": "Free quota reached. Upgrade at " + HOST + "/pricing"}, 429
    ts = now()
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v = velocity(event["user_id"])
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"], "v1h": v["1h"],
        "amount": float(event.get("amount", 0)), "device_risk": float(event.get("device_risk", 0)),
        "anomaly": float(event.get("anomaly", 0)),
        "country_shift": state["last_country"] is not None and state["last_country"] != event["country"],
        "unsafe_country": event["country"] not in SAFE_COUNTRIES
    }
    score    = compute_score(signals)
    decision = decide(score)
    reasons  = explain(signals)
    trust    = update_trust(state["trust"], decision)
    save_user(event["user_id"], trust, event["country"])
    result   = {"decision": decision, "score": round(score, 4), "trust": round(trust, 4), "reasons": reasons, "version": VERSION, "timestamp": ts}
    result["audit_hash"] = append_audit(event, result, ts)
    if api_key:
        increment_usage(api_key)
    return result, 200

def send_json(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h, html, status=200):
    body = html.encode() if isinstance(html, str) else html
    h.send_response(status)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    length = int(h.headers.get("Content-Length", 0))
    if length:
        try:
            return json.loads(h.rfile.read(length))
        except Exception:
            return {}
    return {}

def get_api_key(h):
    auth = h.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return h.headers.get("X-API-Key", "").strip()

_LD = "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5BSUxlYXNoIC0gRW50ZXJwcmlzZSBBSSBHb3Zlcm5hbmNlIFBsYXRmb3JtPC90aXRsZT4KPG1ldGEgbmFtZT0iZGVzY3JpcHRpb24iIGNvbnRlbnQ9IlJlYWwtdGltZSBBSSBnb3Zlcm5hbmNlLCB0cnVzdCBzY29yaW5nLCBTSEEtMjU2IGF1ZGl0IGNoYWlucyBhbmQgRVUgQUkgQWN0IGNvbXBsaWFuY2UuIERlcGxveSBpbiBtaW51dGVzLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9QmViYXMrTmV1ZSZmYW1pbHk9RE0rU2Fuczp3Z2h0QDMwMDs0MDA7NTAwOzYwMDs3MDAmZmFtaWx5PUpldEJyYWlucytNb25vOndnaHRANDAwOzcwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1yZWQ6I2NjMDAwMDstLXJlZDI6Izk5MDAwMDstLWJsYWNrOiMwYTBhMGE7LS13aGl0ZTojZmZmOy0tb2ZmOiNmOGY4Zjg7LS1ib3JkZXI6I2UwZTBlMDstLW11dGVkOiM2NjY7LS1tb25vOidKZXRCcmFpbnMgTW9ubycsbW9ub3NwYWNlOy0tc2FuczonRE0gU2Fucycsc2Fucy1zZXJpZjstLWRpc3BsYXk6J0JlYmFzIE5ldWUnLHNhbnMtc2VyaWZ9Cip7Ym94LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3BhZGRpbmc6MH1odG1se3Njcm9sbC1iZWhhdmlvcjpzbW9vdGh9CmJvZHl7YmFja2dyb3VuZDojZmZmO2NvbG9yOiMwYTBhMGE7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7b3ZlcmZsb3cteDpoaWRkZW59Cm5hdntwb3NpdGlvbjpmaXhlZDt0b3A6MDtsZWZ0OjA7cmlnaHQ6MDt6LWluZGV4OjEwMDtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyLWJvdHRvbTozcHggc29saWQgdmFyKC0tcmVkKTtwYWRkaW5nOjAgNDBweDtoZWlnaHQ6NjRweDtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVufQoubG9nb3tmb250LWZhbWlseTp2YXIoLS1kaXNwbGF5KTtmb250LXNpemU6MjhweDtsZXR0ZXItc3BhY2luZzoycHh9LmxvZ28gc3Bhbntjb2xvcjp2YXIoLS1yZWQpfQoubmF2LWxpbmtze2Rpc3BsYXk6ZmxleDtnYXA6MjhweDthbGlnbi1pdGVtczpjZW50ZXJ9Ci5uYXYtbGlua3MgYXtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7Zm9udC1zaXplOjE0cHg7Zm9udC13ZWlnaHQ6NTAwO3RyYW5zaXRpb246Y29sb3IgLjJzfS5uYXYtbGlua3MgYTpob3Zlcntjb2xvcjp2YXIoLS1yZWQpfQoubmF2LWN0YXtiYWNrZ3JvdW5kOnZhcigtLXJlZCkhaW1wb3J0YW50O2NvbG9yOiNmZmYhaW1wb3J0YW50O3BhZGRpbmc6MTBweCAyMHB4O2JvcmRlci1yYWRpdXM6NHB4O2ZvbnQtd2VpZ2h0OjcwMCFpbXBvcnRhbnR9Ci5oZXJve3BhZGRpbmc6MTIwcHggNDBweCA4MHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWJvcmRlcil9Ci5oZXJvLWlubmVye21heC13aWR0aDoxMjAwcHg7bWFyZ2luOjAgYXV0bztkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjgwcHg7YWxpZ24taXRlbXM6Y2VudGVyfQouZXllYnJvd3tkaXNwbGF5OmlubGluZS1mbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6OHB4O2JhY2tncm91bmQ6dmFyKC0tcmVkKTtjb2xvcjojZmZmO3BhZGRpbmc6NnB4IDE0cHg7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MnB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjI0cHh9Ci5leWVicm93OjpiZWZvcmV7Y29udGVudDonJzt3aWR0aDo2cHg7aGVpZ2h0OjZweDtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyLXJhZGl1czo1MCU7YW5pbWF0aW9uOnB1bHNlIDJzIGluZmluaXRlfQpAa2V5ZnJhbWVzIHB1bHNlezAlLDEwMCV7b3BhY2l0eToxfTUwJXtvcGFjaXR5Oi4zfX0KaDF7Zm9udC1mYW1pbHk6dmFyKC0tZGlzcGxheSk7Zm9udC1zaXplOmNsYW1wKDUycHgsNS41dncsODRweCk7bGluZS1oZWlnaHQ6Ljk1O2xldHRlci1zcGFjaW5nOjJweDttYXJnaW4tYm90dG9tOjI0cHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQpoMSAucmVke2NvbG9yOnZhcigtLXJlZCl9Ci5oZXJvLXB7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO2xpbmUtaGVpZ2h0OjEuNzU7bWFyZ2luLWJvdHRvbTozNnB4O21heC13aWR0aDo1MDBweH0KLmJ0bnN7ZGlzcGxheTpmbGV4O2dhcDoxMnB4O2ZsZXgtd3JhcDp3cmFwfQouYnRuLXB7YmFja2dyb3VuZDp2YXIoLS1yZWQpO2NvbG9yOiNmZmY7cGFkZGluZzoxNHB4IDI4cHg7Ym9yZGVyOm5vbmU7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQtc2l6ZToxNHB4O2xldHRlci1zcGFjaW5nOjFweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y3Vyc29yOnBvaW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmU7dHJhbnNpdGlvbjpiYWNrZ3JvdW5kIC4ycztib3JkZXItcmFkaXVzOjRweDtkaXNwbGF5OmlubGluZS1ibG9ja30KLmJ0bi1wOmhvdmVye2JhY2tncm91bmQ6dmFyKC0tcmVkMil9Ci5idG4tb3tiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2NvbG9yOnZhcigtLWJsYWNrKTtwYWRkaW5nOjE0cHggMjhweDtib3JkZXI6MnB4IHNvbGlkIHZhcigtLWJsYWNrKTtmb250LWZhbWlseTp2YXIoLS1zYW5zKTtmb250LXdlaWdodDo3MDA7Zm9udC1zaXplOjE0cHg7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtjdXJzb3I6cG9pbnRlcjt0ZXh0LWRlY29yYXRpb246bm9uZTt0cmFuc2l0aW9uOmFsbCAuMnM7Ym9yZGVyLXJhZGl1czo0cHg7ZGlzcGxheTppbmxpbmUtYmxvY2t9Ci5idG4tbzpob3ZlcntiYWNrZ3JvdW5kOnZhcigtLWJsYWNrKTtjb2xvcjojZmZmfQoucGlsbHN7ZGlzcGxheTpmbGV4O2ZsZXgtd3JhcDp3cmFwO2dhcDo4cHg7bWFyZ2luLXRvcDoyOHB4fQoucGlsbHtib3JkZXI6MXB4IHNvbGlkIHZhcigtLXJlZCk7Y29sb3I6dmFyKC0tcmVkKTtwYWRkaW5nOjRweCAxMnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2JvcmRlci1yYWRpdXM6MnB4fQoudGVybWluYWx7YmFja2dyb3VuZDojMGEwYTBhO2JvcmRlci1yYWRpdXM6OHB4O292ZXJmbG93OmhpZGRlbjtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTNweDtib3gtc2hhZG93OjhweCA4cHggMCB2YXIoLS1yZWQpfQoudGVybS1iYXJ7YmFja2dyb3VuZDojMWExYTFhO3BhZGRpbmc6MTJweCAxNnB4O2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweDtib3JkZXItYm90dG9tOjFweCBzb2xpZCAjMzMzfQouZG90e3dpZHRoOjEwcHg7aGVpZ2h0OjEwcHg7Ym9yZGVyLXJhZGl1czo1MCV9LmRye2JhY2tncm91bmQ6I2ZmNWY1Nn0uZHl7YmFja2dyb3VuZDojZmZiZDJlfS5kZ3tiYWNrZ3JvdW5kOiMyN2M5M2Z9Ci50bGJse21hcmdpbi1sZWZ0OmF1dG87Zm9udC1zaXplOjEwcHg7Y29sb3I6IzY2NjtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQoudGVybS1ib2R5e3BhZGRpbmc6MjRweDtsaW5lLWhlaWdodDoyLjI7Y29sb3I6I2NjY30KLnRje2NvbG9yOiM1NTV9LnRre2NvbG9yOiM3OWI4ZmZ9LnR2e2NvbG9yOiNmMGM2NzR9LnRze2NvbG9yOiM5ZWNiZmZ9Ci50YXtjb2xvcjojMDBmZjg4O2ZvbnQtd2VpZ2h0OjcwMH0udHd7Y29sb3I6I2ZmYWEwMDtmb250LXdlaWdodDo3MDB9LnRie2NvbG9yOiNmZjNiNWM7Zm9udC13ZWlnaHQ6NzAwfQouc3RhdHN7YmFja2dyb3VuZDojMGEwYTBhO3BhZGRpbmc6NDhweH0KLnN0YXRzLWlubmVye21heC13aWR0aDoxMjAwcHg7bWFyZ2luOjAgYXV0bztkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCg1LDFmcil9Ci5zdGF0e3BhZGRpbmc6MjRweDtib3JkZXItcmlnaHQ6MXB4IHNvbGlkICMyMjI7dGV4dC1hbGlnbjpjZW50ZXJ9LnN0YXQ6bGFzdC1jaGlsZHtib3JkZXI6bm9uZX0KLnN0YXQtbntmb250LWZhbWlseTp2YXIoLS1kaXNwbGF5KTtmb250LXNpemU6NDRweDtjb2xvcjp2YXIoLS1yZWQpO2xldHRlci1zcGFjaW5nOjJweH0KLnN0YXQtbHtmb250LXNpemU6MTJweDtjb2xvcjojNjY2O21hcmdpbi10b3A6NHB4O2xldHRlci1zcGFjaW5nOjFweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2V9Ci5zZWN7cGFkZGluZzo4MHB4IDQwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tYm9yZGVyKX0KLnNlYy1pbm5lcnttYXgtd2lkdGg6MTIwMHB4O21hcmdpbjowIGF1dG99Ci5zZWMtbGJse2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2xldHRlci1zcGFjaW5nOjNweDtjb2xvcjp2YXIoLS1yZWQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjEycHh9Cmgye2ZvbnQtZmFtaWx5OnZhcigtLWRpc3BsYXkpO2ZvbnQtc2l6ZTpjbGFtcCgzNnB4LDR2dyw1NnB4KTtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206MTZweH0KaDIgc3Bhbntjb2xvcjp2YXIoLS1yZWQpfQouc2VjLXN1Yntmb250LXNpemU6MTdweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWF4LXdpZHRoOjYwMHB4O2xpbmUtaGVpZ2h0OjEuNzttYXJnaW4tYm90dG9tOjQ4cHh9Ci5ncmlkM3tkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgzLDFmcik7Z2FwOjFweDtiYWNrZ3JvdW5kOnZhcigtLWJvcmRlcik7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO21hcmdpbi10b3A6NDBweH0KLmdjYXJke2JhY2tncm91bmQ6I2ZmZjtwYWRkaW5nOjMycHg7cG9zaXRpb246cmVsYXRpdmV9Ci5nY2FyZDo6YmVmb3Jle2NvbnRlbnQ6Jyc7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDowO3JpZ2h0OjA7aGVpZ2h0OjNweDtiYWNrZ3JvdW5kOnZhcigtLXJlZCl9Ci5nY2FyZC1yZWZ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tcmVkKTtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO21hcmdpbi1ib3R0b206MTJweH0KLmdjYXJkIGgze2ZvbnQtZmFtaWx5OnZhcigtLWRpc3BsYXkpO2ZvbnQtc2l6ZToyMHB4O2xldHRlci1zcGFjaW5nOjFweDttYXJnaW4tYm90dG9tOjEwcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQouZ2NhcmQgcHtmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1tdXRlZCk7bGluZS1oZWlnaHQ6MS42NX0KLnByaWNlLWdyaWR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczpyZXBlYXQoMywxZnIpO2dhcDoyNHB4O21hcmdpbi10b3A6NDBweH0KLnByaWNlLWNhcmR7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MzZweDtwb3NpdGlvbjpyZWxhdGl2ZX0KLnByaWNlLWNhcmQuZmVhdHVyZWR7Ym9yZGVyOjJweCBzb2xpZCB2YXIoLS1yZWQpO2JhY2tncm91bmQ6dmFyKC0tb2ZmKX0KLnByaWNlLWJhZGdle3Bvc2l0aW9uOmFic29sdXRlO3RvcDotMTRweDtsZWZ0OjUwJTt0cmFuc2Zvcm06dHJhbnNsYXRlWCgtNTAlKTtiYWNrZ3JvdW5kOnZhcigtLXJlZCk7Y29sb3I6I2ZmZjtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTBweDtmb250LXdlaWdodDo3MDA7cGFkZGluZzo0cHggMTZweDtsZXR0ZXItc3BhY2luZzoycHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO3doaXRlLXNwYWNlOm5vd3JhcH0KLnByaWNlLXRpZXJ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MnB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7bWFyZ2luLWJvdHRvbToxNnB4fQoucHJpY2UtbnVte2ZvbnQtZmFtaWx5OnZhcigtLWRpc3BsYXkpO2ZvbnQtc2l6ZTo1NnB4O2xldHRlci1zcGFjaW5nOi0xcHg7Y29sb3I6dmFyKC0tYmxhY2spO21hcmdpbi1ib3R0b206NHB4fQoucHJpY2UtbnVtIHN1cHtmb250LXNpemU6MjRweDt2ZXJ0aWNhbC1hbGlnbjpzdXBlcjtjb2xvcjp2YXIoLS1yZWQpfQoucHJpY2UtdW5pdHtmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbToyOHB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pfQoucHJpY2UtZmVhdHVyZXN7bGlzdC1zdHlsZTpub25lO21hcmdpbi1ib3R0b206MzJweH0KLnByaWNlLWZlYXR1cmVzIGxpe2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLW11dGVkKTtwYWRkaW5nOjEwcHggMDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7Z2FwOjEwcHh9Ci5wcmljZS1mZWF0dXJlcyBsaTo6YmVmb3Jle2NvbnRlbnQ6J+Kckyc7Y29sb3I6dmFyKC0tcmVkKTtmb250LXdlaWdodDo3MDB9Ci5zaWdudXAtc2Vje3BhZGRpbmc6ODBweCA0MHB4O2JhY2tncm91bmQ6dmFyKC0tb2ZmKTtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpfQouc2lnbnVwLWlubmVye21heC13aWR0aDo2NDBweDttYXJnaW46MCBhdXRvfQouZmd7
