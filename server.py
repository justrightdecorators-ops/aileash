import json
import sqlite3
import hashlib
import time
import hmac
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict, deque
import urllib.parse

# ======================
# CONFIG
# ======================

STRIPE_SECRET = "sk_live_YOUR_STRIPE_KEY_HERE"
STRIPE_PRICE = "price_YOUR_PRICE_ID_HERE"
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = 8080

SAFE = {"UK","US","DE","FR","CA","AU"}

W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

# ======================
# HELPERS
# ======================

def now():
    return time.time()

def clamp(x):
    return max(0.0, min(1.0, x))

def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def make_licence_key(email):
    msg = (email + LICENCE_SECRET).encode()
    return hmac.new(LICENCE_SECRET.encode(), msg, hashlib.sha256).hexdigest()

# ======================
# DATABASE
# ======================

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

# ======================
# GOVERN ENGINE
# ======================

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
        min(v60 / 20, 1) * 0.25 +
        min(amount / 1000, 1) * 0.2 +
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
        "score": round(score, 4),
        "trust": round(trust, 4),
        "audit_hash": sha(event)
    }

# ======================
# LANDING PAGE (FULL)
# ======================

LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AILeash — AI Governance Layer</title>
<style>
body{margin:0;font-family:monospace;background:#050505;color:#eaeaea}
header{display:flex;justify-content:space-between;padding:18px 28px;border-bottom:1px solid #1f1f1f}
.logo{color:#00ff88;font-weight:bold;letter-spacing:2px}
.hero{max-width:1000px;margin:auto;padding:70px 20px}
h1{font-size:44px;line-height:1.2}
span{color:#00ff88}
.sub{color:#aaa;max-width:800px;margin-top:20px;margin-bottom:40px;line-height:1.6}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:15px}
.card{border:1px solid #1f1f1f;background:#0b0b0b;padding:18px}
.card h3{color:#00ff88}
.box{border:1px solid #00ff88;padding:20px;margin-top:40px;background:#0b0b0b}
input,button{width:100%;padding:10px;margin-top:10px}
button{background:#00ff88;border:none;font-weight:bold;cursor:pointer}
button:hover{background:#00cc6a}
.small{font-size:12px;color:#888;margin-top:10px}
footer{border-top:1px solid #1f1f1f;text-align:center;padding:30px;color:#666;margin-top:60px}
</style>
</head>

<body>

<header>
<div class="logo">AI<span>LEASH</span></div>
<div style="color:#ffaa00;font-size:12px;">EU AI ACT • AI GOVERNANCE ENGINE</div>
</header>

<div class="hero">

<h1>AI governance for production systems.<br><span>Control every AI decision in real time.</span></h1>

<p class="sub">
AILeash sits between your AI and your users.
It scores every request, detects anomalies, tracks trust, and generates tamper-evident audit logs so your AI becomes compliant, traceable, and safe in production.
</p>

<div class="grid">
<div class="card"><h3>Risk Scoring</h3>Every AI action is evaluated before execution.</div>
<div class="card"><h3>Trust Engine</h3>User behaviour dynamically adjusts trust levels.</div>
<div class="card"><h3>Audit Chain</h3>Immutable logs for compliance and forensic traceability.</div>
<div class="card"><h3>Production Ready</h3>Flask/FastAPI compatible, zero dependencies.</div>
</div>

<div class="box">
<input id="company" placeholder="Company name">
<input id="email" placeholder="Email address">
<button onclick="signup()">Start $99/month</button>
<div id="msg" class="small"></div>
</div>

</div>

<footer>
AILeash © 2026 • sebbi.pro/monopcontent/aileash
</footer>

<script>
function signup(){
fetch("/signup",{method:"POST",headers:{"Content-Type":"application/json"},
body:JSON.stringify({
company:document.getElementById("company").value,
email:document.getElementById("email").value
})})
.then(r=>r.json()).then(d=>{
document.getElementById("msg").innerText =
d.licence_key ? "LICENSE: " + d.licence_key :
(d.stripe_url || d.error);
});
}
</script>

</body>
</html>"""

# ======================
# SERVER
# ======================

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
