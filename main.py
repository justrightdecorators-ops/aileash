import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, urllib.error, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.0.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
_db_lock        = threading.Lock()

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

# ---------------- DATABASE ----------------
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE, merkle_root TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS velocity_history (user_id TEXT, window_type TEXT, timestamps TEXT, PRIMARY KEY(user_id, window_type))")
    conn.execute("CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT, message TEXT, created REAL)")
    conn.commit()
    return conn

_conn = get_conn()

# ---------------- STRIPE ----------------
def stripe_call(method, endpoint, data=None):
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET,
               "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode())

def create_checkout_session():
    if not STRIPE_SECRET or not STRIPE_PRICE_ID:
        return None

    return stripe_call("POST", "/checkout/sessions", {
        "mode": "subscription",
        "line_items[0][price]": STRIPE_PRICE_ID,
        "line_items[0][quantity]": 1,
        "success_url": "https://localhost:8080/success",
        "cancel_url": "https://localhost:8080/cancel"
    })

# ---------------- API KEY SYSTEM ----------------
def create_api_key(email):
    key = "al_live_" + secrets.token_hex(24)

    with _db_lock:
        _conn.execute(
            "INSERT INTO api_keys(key,email,created) VALUES(?,?,?)",
            (key, email, time.time())
        )
        _conn.commit()

    return key

def validate_key(key):
    with _db_lock:
        row = _conn.execute(
            "SELECT email,actions_used,active FROM api_keys WHERE key=?",
            (key,)
        ).fetchone()

    if not row or not row[2]:
        return None

    return {"email": row[0], "actions_used": row[1]}

def increment_usage(key):
    with _db_lock:
        _conn.execute(
            "UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?",
            (key,)
        )
        _conn.commit()

# ---------------- CORE UTILS ----------------
def now(): return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

# ---------------- GOVERNANCE ENGINE ----------------
def compute_score(s, action_type="default"):
    score = 0
    score += (1-s["trust"])*0.30
    score += min(s["amount"]/10000,1)*0.15
    score += s["device_risk"]*0.10
    score += s["anomaly"]*0.10

    if s["country"] not in SAFE_COUNTRIES:
        score += 0.10

    score += RISK_PROFILES.get(action_type,{"base":0})["base"]
    return clamp(score)

def decide(score):
    if score < 0.35: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def govern(event):
    score = compute_score(event, event.get("action","default"))
    decision = decide(score)

    return {
        "decision": decision,
        "score": round(score,4),
        "ts": now()
    }

# ---------------- HTTP ----------------
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

def err(h,msg,status=400): send(h,{"error":msg},status)

def get_key(h):
    auth=h.headers.get("Authorization","")
    return auth[7:] if auth.startswith("Bearer ") else None

# ---------------- SERVER ----------------
class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        path=urlparse(self.path).path

        if path=="/":
            try:
                with open("landing.html") as f:
                    return send_html(self,f.read())
            except:
                return err(self,"missing landing.html",404)

        if path=="/health":
            return send(self,{"status":"ok","version":VERSION})

        err(self,"not found",404)

    def do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length",0))
        body=self.rfile.read(length).decode() if length else "{}"
        data=json.loads(body)

        if path=="/api/govern":
            key=get_key(self)
            if not key: return err(self,"missing api key",401)
            if not validate_key(key): return err(self,"invalid key",403)
            return send(self,govern(data))

        if path=="/api/keys":
            return send(self,{"key":create_api_key(data.get("email",""))})

        if path=="/api/upgrade":
            session=create_checkout_session()
            if not session or "url" not in session:
                return err(self,"stripe not configured",500)
            return send(self,{"url":session["url"]})

        err(self,"not found",404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self,*args): pass

# ---------------- MAIN ----------------
def main():
    server=HTTPServer(("0.0.0.0",PORT),RequestHandler)
    print(f"AILeash running on {PORT}")
    print("Landing: /")
    print("Govern: /api/govern")
    print("Upgrade: /api/upgrade")
    server.serve_forever()

if __name__=="__main__":
    main()
