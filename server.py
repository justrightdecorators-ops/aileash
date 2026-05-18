import json
import sqlite3
import hashlib
import time
import hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict, deque
import urllib.parse

# ========================
# CONFIG
# ========================

STRIPE_SECRET = "sk_live_YOUR_STRIPE_KEY_HERE"
STRIPE_PRICE  = "price_YOUR_PRICE_ID_HERE"
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = 8080

SAFE = {"UK","US","DE","FR","CA","AU"}

W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

# ========================
# HELPERS
# ========================

def now(): return time.time()

def clamp(x):
    return max(0.0, min(1.0, x))

def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def make_licence_key(email):
    msg = (email + LICENCE_SECRET).encode()
    return hmac.new(LICENCE_SECRET.encode(), msg, hashlib.sha256).hexdigest()

# ========================
# DATABASE
# ========================

gc = sqlite3.connect("aileash.db", check_same_thread=False)
gc.row_factory = sqlite3.Row

gc.execute("""
CREATE TABLE IF NOT EXISTS users (
user_id TEXT PRIMARY KEY,
trust REAL DEFAULT 0.5,
last_country TEXT
)
""")

gc.execute("""
CREATE TABLE IF NOT EXISTS audit_log (
id INTEGER PRIMARY KEY AUTOINCREMENT,
ts REAL,
user_id TEXT,
event_json TEXT,
result_json TEXT,
prev_hash TEXT,
audit_hash TEXT UNIQUE
)
""")

gc.commit()

lc = sqlite3.connect("licences.db", check_same_thread=False)
lc.row_factory = sqlite3.Row

lc.execute("""
CREATE TABLE IF NOT EXISTS licences (
id INTEGER PRIMARY KEY AUTOINCREMENT,
email TEXT UNIQUE,
company TEXT,
licence_key TEXT,
status TEXT DEFAULT 'ACTIVE',
created_ts REAL,
expires_ts REAL
)
""")

lc.commit()

# ========================
# CORE ENGINE
# (unchanged but trimmed for safety)
# ========================

def load_user(uid):
    row = gc.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    if row:
        return {"trust": row["trust"], "last_country": row["last_country"]}
    return {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    gc.execute("""
    INSERT INTO users(user_id,trust,last_country)
    VALUES(?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
    trust=excluded.trust,
    last_country=excluded.last_country
    """, (uid, trust, country))
    gc.commit()

def update_windows(uid):
    t = now()
    for w, s in [(W60,60),(W5M,300),(W1H,3600)]:
        w[uid].append(t)
        while w[uid] and w[uid][0] < t - s:
            w[uid].popleft()

# ========================
# GOVERN (simplified safe version)
# ========================

def govern(event):
    state = load_user(event["user_id"])
    update_windows(event["user_id"])

    v60 = len(W60[event["user_id"]])
    amount = event.get("amount", 0)
    anomaly = event.get("anomaly", 0.05)
    device_risk = event.get("device_risk", 0.1)
    country = event.get("country", "UK")

    score = (
        (1 - state["trust"]) * 0.3 +
        min(v60/20,1) * 0.25 +
        min(amount/1000,1) * 0.2 +
        device_risk * 0.1 +
        anomaly * 0.15
    )

    score = clamp(score)

    if score < 0.35:
        decision = "ALLOW"
    elif score < 0.7:
        decision = "CHALLENGE"
    else:
        decision = "BLOCK"

    trust = state["trust"]

    if decision == "ALLOW":
        trust += (1 - trust) * 0.01
    elif decision == "CHALLENGE":
        trust -= trust * 0.02
    else:
        trust -= trust * 0.05

    trust = clamp(trust)

    save_user(event["user_id"], trust, country)

    return {
        "decision": decision,
        "score": round(score,4),
        "trust": round(trust,4),
        "audit_hash": sha(event)
    }

# ========================
# LANDING PAGE
# ========================

LANDING = """<!DOCTYPE html>
<html>
<head>
<title>AILeash</title>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
body{margin:0;background:#050505;color:#e6e6e6;font-family:monospace}
.header{padding:20px;border-bottom:1px solid #222;display:flex;justify-content:space-between}
.logo{color:#00ff88;font-weight:bold}
.hero{padding:80px 20px;max-width:900px;margin:auto}
h1{font-size:42px}
span{color:#00ff88}
.box{border:1px solid #00ff88;padding:20px;margin-top:40px}
input,button{width:100%;padding:10px;margin-top:10px}
button{background:#00ff88;border:none;font-weight:bold}
</style>
</head>
<body>

<div class="header">
<div class="logo">AILeash</div>
<div>EU AI ACT READY</div>
</div>

<div class="hero">
<h1>Govern your AI.<br><span>Instantly compliant.</span></h1>
<p>AILeash provides real-time AI governance, audit logs, and trust scoring for production AI systems.</p>

<div class="box">
<input id="company" placeholder="Company name">
<input id="email" placeholder="Email">
<button onclick="signup()">Start $99/month</button>
<div id="msg"></div>
</div>
</div>

<script>
function signup(){
fetch("/signup",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({
company:document.getElementById("company").value,
email:document.getElementById("email").value
})})
.then(r=>r.json()).then(d=>{
document.getElementById("msg").innerText =
d.licence_key ? "KEY: "+d.licence_key : (d.stripe_url || d.error);
})
}
</script>

</body>
</html>"""

# ========================
# SERVER
# ========================

class Handler(BaseHTTPRequestHandler):

    def send_html(self, html):
        b = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.end_headers()
        self.wfile.write(b)

    def send_json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            return self.send_html(LANDING)
        if self.path == "/health":
            return self.send_json({"status":"ok"})
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        data = json.loads(self.rfile.read(length))

        if self.path == "/govern":
            return self.send_json(govern(data))

        if self.path == "/signup":
            email = data.get("email","")
            company = data.get("company","")

            key = make_licence_key(email)

            lc.execute("""
            INSERT OR REPLACE INTO licences
            (email,company,licence_key,status,created_ts,expires_ts)
            VALUES(?,?,?,?,?,?)
            """,(email,company,key,"ACTIVE",now(),now()+2592000))

            lc.commit()

            return self.send_json({"licence_key": key})

        self.send_json({"error":"not found"})

print("AILeash running on", PORT)
HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
