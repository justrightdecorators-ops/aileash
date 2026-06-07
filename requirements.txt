import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, urllib.error
import os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# =========================
# CONFIG
# =========================

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.0.0"

SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}

STRIPE_PRICE_ID = ""
_db_lock = threading.Lock()

RISK_PROFILES = {
    "default":{"base":0.0},
    "wire_transfer":{"base":0.18},
    "financial_transfer":{"base":0.18},
    "payment":{"base":0.12},
    "content_action":{"base":0.08},
    "tool_call":{"base":0.12},
    "data_export":{"base":0.15},
    "account_change":{"base":0.14},
}

# =========================
# DB
# =========================

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE, merkle_root TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS velocity_history (user_id TEXT, window_type TEXT, timestamps TEXT, PRIMARY KEY(user_id, window_type))")
    conn.commit()
    return conn

_conn = get_conn()

# =========================
# STRIPE SAFE WRAPPER
# =========================

def stripe_call(method, endpoint, data=None):
    url = "https://api.stripe.com/v1" + endpoint
    headers = {
        "Authorization": "Bearer " + STRIPE_SECRET,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except:
            return {"error": e.read().decode()}

# =========================
# STRIPE SETUP
# =========================

def setup_stripe():
    global STRIPE_PRICE_ID

    if not STRIPE_SECRET:
        print("WARNING: No STRIPE_SECRET set")
        return

    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()

    if row:
        STRIPE_PRICE_ID = row[0]
        print("Stripe ready")
        return

    product = stripe_call("POST", "/products", {
        "name": "AILeash Governance API",
        "description": "AI governance engine"
    })

    if "error" in product:
        print("Stripe error:", product)
        return

    price = stripe_call("POST", "/prices", {
        "product": product["id"],
        "currency": "gbp",
        "unit_amount": 1,
        "recurring[interval]": "month",
        "recurring[usage_type]": "metered"
    })

    STRIPE_PRICE_ID = price["id"]

    with _db_lock:
        _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()

# =========================
# CORE HELPERS
# =========================

def now():
    return time.time()

def clamp(x,a=0.0,b=1.0):
    return max(a,min(b,x))

def sha(p):
    return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def load_user(uid):
    with _db_lock:
        row = _conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"trust": row[0], "last_country": row[1]} if row else {"trust":0.5,"last_country":None}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",
            (uid,trust,country)
        )
        _conn.commit()

# =========================
# GOVERN ENGINE
# =========================

def compute_score(s, action_type="default"):
    score = 0
    score += (1-s["trust"])*0.30
    score += min(s["amount"]/10000,1)*0.15
    score += s["device_risk"]*0.10
    score += s["anomaly"]*0.10
    if s["country_shift"]: score += 0.10
    if s["unsafe_country"]: score += 0.10
    score += RISK_PROFILES.get(action_type,{"base":0}).get("base",0)
    return clamp(score)

def decide(score):
    if score < 0.35:
        return "ALLOW"
    if score < 0.70:
        return "CHALLENGE"
    return "BLOCK"

def update_trust(trust, decision):
    if decision=="ALLOW":
        trust += (1-trust)*0.01
    elif decision=="CHALLENGE":
        trust -= trust*0.02
    else:
        trust -= trust*0.08
    return clamp(trust,0.05,1.0)

def append_audit(event,result):
    prev = "GENESIS"
    payload = {"prev_hash":prev,"event":event,"result":result,"ts":now()}
    h = sha(payload)

    with _db_lock:
        _conn.execute(
            "INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash,merkle_root) "
            "VALUES(?,?,?,?,?,?,?)",
            (payload["ts"], event["user_id"], json.dumps(event), json.dumps(result), prev, h, h)
        )
        _conn.commit()

    return h

def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - set(event.keys())
    if missing:
        raise ValueError(f"Missing fields: {missing}")

    state = load_user(event["user_id"])

    signals = {
        "trust": state["trust"],
        "amount": event["amount"],
        "device_risk": event["device_risk"],
        "anomaly": event["anomaly"],
        "country_shift": state["last_country"] and state["last_country"] != event["country"],
        "unsafe_country": event["country"] not in SAFE_COUNTRIES
    }

    score = compute_score(signals, event.get("action","default"))
    decision = decide(score)
    trust = update_trust(state["trust"], decision)

    save_user(event["user_id"], trust, event["country"])

    result = {
        "decision": decision,
        "score": round(score,4),
        "trust": round(trust,4),
        "version": VERSION
    }

    result["audit_hash"] = append_audit(event,result)

    return result

# =========================
# HTTP RESPONSES
# =========================

def send(h,data,status=200):
    body=json.dumps(data).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.end_headers()
    h.wfile.write(body)

def send_html(h,html):
    body=html.encode()
    h.send_response(200)
    h.send_header("Content-Type","text/html")
    h.end_headers()
    h.wfile.write(body)

def err(h,msg,status=400):
    send(h,{"error":msg},status)

# =========================
# LANDING PAGE (UNCHANGED)
# =========================

LANDING = """PASTE YOUR ORIGINAL LANDING PAGE HERE EXACTLY AS YOU SENT IT ()"""

# =========================
# HTTP SERVER
# =========================

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" :
            return send_html(self, LANDING)
        if path == "/health":
            return send(self, {"status":"ok","version":VERSION})
        return err(self,"Not found",404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path == "/govern":
            try:
                return send(self, govern(body))
            except Exception as e:
                return err(self,str(e),500)

        return err(self,"Not found",404)

# =========================
# START
# =========================

if __name__ == "__main__":
    print("AILeash v3 starting")
    setup_stripe()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
