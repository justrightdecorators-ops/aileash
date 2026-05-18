import json
import sqlite3
import hashlib
import time
import hmac
import threading
from datetime import datetime
from collections import Counter
from collections import defaultdict
from collections import deque

STRIPE_SECRET = "sk_live_YOUR_STRIPE_KEY_HERE"
STRIPE_PRICE  = "price_YOUR_PRICE_ID_HERE"
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = 8080

SAFE = {"UK","US","DE","FR","CA","AU"}
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

def now(): return time.time()

def clamp(x):
    if x < 0.0: return 0.0
    if x > 1.0: return 1.0
    return x

def sha(p):
    s = json.dumps(p, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

def make_licence_key(email):
    msg = (email + LICENCE_SECRET).encode()
    return hmac.new(LICENCE_SECRET.encode(), msg, hashlib.sha256).hexdigest()

gc = sqlite3.connect("aileash.db", check_same_thread=False)
gc.row_factory = sqlite3.Row
gc.execute(
    "CREATE TABLE IF NOT EXISTS users ("
    "user_id TEXT PRIMARY KEY,"
    "trust REAL DEFAULT 0.5,"
    "last_country TEXT)"
)
gc.execute(
    "CREATE TABLE IF NOT EXISTS audit_log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts REAL, user_id TEXT,"
    "event_json TEXT, result_json TEXT,"
    "prev_hash TEXT, audit_hash TEXT UNIQUE)"
)
gc.commit()

lc = sqlite3.connect("licences.db", check_same_thread=False)
lc.row_factory = sqlite3.Row
lc.execute(
    "CREATE TABLE IF NOT EXISTS licences ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "email TEXT UNIQUE, company TEXT,"
    "licence_key TEXT, stripe_customer TEXT,"
    "stripe_subscription TEXT,"
    "status TEXT DEFAULT 'ACTIVE',"
    "created_ts REAL, expires_ts REAL)"
)
lc.commit()

def load_user(uid):
    row = gc.execute(
        "SELECT trust, last_country FROM users WHERE user_id=?", (uid,)
    ).fetchone()
    if row:
        return {"trust": row[0], "last_country": row[1]}
    return {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    gc.execute(
        "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " trust=excluded.trust, last_country=excluded.last_country",
        (uid, trust, country)
    )
    gc.commit()

def prune(q, s):
    c = now() - s
    while q and q[0] < c:
        q.popleft()

def update_windows(uid):
    t = now()
    W60[uid].append(t)
    W5M[uid].append(t)
    W1H[uid].append(t)
    prune(W60[uid], 60)
    prune(W5M[uid], 300)
    prune(W1H[uid], 3600)

def chain_tip():
    row = gc.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row: return row[0]
    return "GENESIS"

def do_audit(event, result):
    prev = chain_tip()
    payload = {"prev_hash": prev, "ts": now(), "event": event, "result": result}
    h = sha(payload)
    gc.execute(
        "INSERT INTO audit_log"
        "(ts,user_id,event_json,result_json,prev_hash,audit_hash)"
        " VALUES(?,?,?,?,?,?)",
        (now(), event["user_id"], json.dumps(event), json.dumps(result), prev, h)
    )
    gc.commit()
    return h

def govern(event):
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v60 = len(W60[event["user_id"]])
    v5m = len(W5M[event["user_id"]])
    v1h = len(W1H[event["user_id"]])
    country = event.get("country", "UK")
    amount = event.get("amount", 0)
    device_risk = event.get("device_risk", 0.1)
    anomaly = event.get("anomaly", 0.05)
    s = 0.0
    s += (1.0 - state["trust"]) * 0.30
    s += min(v60 / 20.0, 1.0) * 0.15
    s += min(v5m / 50.0, 1.0) * 0.10
    s += min(v1h / 200.0, 1.0) * 0.10
    s += min(amount / 1000.0, 1.0) * 0.15
    s += device_risk * 0.10
    s += anomaly * 0.10
    if state["last_country"] and state["last_country"] != country: s += 0.10
    if country not in SAFE: s += 0.10
    s = clamp(s)
    if s < 0.35: decision = "ALLOW"
    elif s < 0.70: decision = "CHALLENGE"
    else: decision = "BLOCK"
    reasons = []
    if state["trust"] < 0.4: reasons.append("low_trust")
    if v60 > 10: reasons.append("velocity_spike")
    if amount > 500: reasons.append("high_amount")
    if device_risk > 0.5: reasons.append("risky_device")
    if state["last_country"] and state["last_country"] != country: reasons.append("country_shift")
    if country not in SAFE: reasons.append("unsafe_country")
    if anomaly > 0.5: reasons.append("behaviour_anomaly")
    trust = state["trust"]
    if decision == "ALLOW": trust += (1.0 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK": trust -= trust * 0.08
    trust = clamp(trust)
    if trust < 0.05: trust = 0.05
    save_user(event["user_id"], trust, country)
    result = {
        "decision": decision,
        "score": round(s, 4),
        "trust": round(trust, 4),
        "reasons": reasons
    }
    result["audit_hash"] = do_audit(event, result)
    return result

LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash - AI Compliance</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e8e8e8;font-family:'Courier New',monospace;line-height:1.6}
nav{border-bottom:1px solid #2a2a2a;padding:1.2rem 2rem;display:flex;justify-content:space-between;align-items:center;background:#0a0a0a}
.logo{font-size:1.2rem;color:#00ff88;font-weight:bold;letter-spacing:2px}
.logo span{color:#e8e8e8}
.hero{max-width:800px;margin:0 auto;padding:5rem 2rem;text-align:center}
.badge{display:inline-block;border:1px solid #ffaa00;color:#ffaa00;padding:.3rem 1rem;font-size:.8rem;letter-spacing:2px;margin-bottom:2rem}
h1{font-size:2.8rem;line-height:1.2;margin-bottom:1.5rem}
h1 em{color:#00ff88;font-style:normal}
.sub{color:#888;max-width:580px;margin:0 auto 3rem;font-size:1.05rem}
.price-box{background:#181818;border:2px solid #00ff88;border-radius:4px;padding:2.5rem;max-width:420px;margin:0 auto 3rem}
.price{font-size:3rem;color:#00ff88;font-weight:bold}
.price span{font-size:1rem;color:#888}
.features{text-align:left;margin:1.5rem 0;list-style:none}
.features li{padding:.4rem 0;font-size:.9rem}
.features li:before{content:"[OK] ";color:#00ff88}
.btn{display:block;background:#00ff88;color:#0a0a0a;padding:1rem;font-family:'Courier New',monospace;font-size:1rem;font-weight:bold;border:none;cursor:pointer;width:100%;margin-top:1.5rem}
.btn:hover{background:#00cc66}
.form-group{margin:.8rem 0;text-align:left}
.form-group label{font-size:.8rem;color:#888;display:block;margin-bottom:.3rem}
.form-group input{width:100%;background:#0a0a0a;border:1px solid #2a2a2a;color:#e8e8e8;padding:.6rem;font-family:'Courier New',monospace;font-size:.9rem}
.form-group input:focus{outline:none;border-color:#00ff88}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.5rem;margin:3rem auto;max-width:800px;padding:0 2rem}
.step{background:#181818;border:1px solid #2a2a2a;padding:1.5rem;border-radius:4px}
.step-n{color:#00ff88;font-size:1.5rem;font-weight:bold;margin-bottom:.5rem}
.step p{color:#888;font-size:.85rem}
footer{border-top:1px solid #2a2a2a;padding:2rem;text-align:center;color:#888;font-size:.8rem;margin-top:3rem}
.msg{padding:1rem;margin-top:1rem;border-radius:4px;font-size:.9rem;display:none}
.msg-ok{background:rgba(0,255,136,.1);color:#00ff88;border:1px solid #00ff88}
.msg-err{background:rgba(255,68,68,.1);color:#ff4444;border:1px solid #ff4444}
</style>
</head>
<body>
<nav>
  <div class="logo">AI<span>Leash</span></div>
  <span style="color:#ffaa00;font-size:.85rem">EU AI Act: August 2026</span>
</nav>
<div class="hero">
  <div class="badge">UK AND US AI COMPLIANCE</div>
  <h1>Make your AI<br><em>instantly compliant.</em></h1>
  <p class="sub">One command. Your AI agents governed, audited, and compliant. Cancel anytime. Compliance stops when you do.</p>
  <div class="price-box">
    <div class="price">$99 <span>/ month</span></div>
    <ul class="features">
      <li>Real-time AI governance engine</li>
      <li>Tamper-evident audit chain</li>
      <li>EU AI Act Article 9 ready</li>
      <li>Flask and FastAPI support</li>
      <li>Zero dependencies</li>
      <li>Instant pip install</li>
      <li>Cancel anytime</li>
    </ul>
    <div class="form-group">
      <label>Company name</label>
      <input type="text" id="company" placeholder="Acme AI Ltd">
    </div>
    <div class="form-group">
      <label>Email address</label>
      <input type="email" id="email" placeholder="cto@yourcompany.com">
    </div>
    <button class="btn" onclick="signup()">Get compliant now</button>
    <div class="msg msg-ok" id="msg-ok"></div>
    <div class="msg msg-err" id="msg-err"></div>
  </div>
</div>
<div class="steps">
  <div class="step"><div class="step-n">01</div><h3>Sign up</h3><p>Enter your email. Pay $99/month. Get your licence key instantly.</p></div>
  <div class="step"><div class="step-n">02</div><h3>Install</h3><p>pip install aileash. Add your key. One line in your app.</p></div>
  <div class="step"><div class="step-n">03</div><h3>Done</h3><p>Every AI action governed. Every decision audited. You are compliant.</p></div>
</div>
<footer>AILeash by Monopcontent &nbsp;|&nbsp; hello@monopcontent.com</footer>
<script>
function signup() {
  var company = document.getElementById("company").value.trim();
  var email = document.getElementById("email").value.trim();
  var ok = document.getElementById("msg-ok");
  var err = document.getElementById("msg-err");
  ok.style.display = "none";
  err.style.display = "none";
  if (!email || !company) {
    err.textContent = "Please enter your company name and email.";
    err.style.display = "block";
    return;
  }
  fetch("/signup", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({email: email, company: company})
  })
  .then(function(r){ return r.json(); })
  .then(function(data){
    if (data.stripe_url) {
      window.location.href = data.stripe_url;
    } else if (data.licence_key) {
      ok.textContent = "Licence issued. Key: " + data.licence_key;
      ok.style.display = "block";
    } else {
      err.textContent = data.error || "Something went wrong.";
      err.style.display = "block";
    }
  })
  .catch(function(){
    err.textContent = "Connection error. Please try again.";
    err.style.display = "block";
  });
}
</script>
</body>
</html>"""

from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler
import urllib.parse

class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_html(self, code, html):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_html(200, LANDING)
            return
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        if self.path == "/stats":
            total = lc.execute("SELECT COUNT(*) FROM licences").fetchone()[0]
            active = lc.execute("SELECT COUNT(*) FROM licences WHERE status='ACTIVE'").fetchone()[0]
            self.send_json(200, {
                "total": total,
                "active": active,
                "mrr": active * 99,
                "arr": active * 99 * 12
            })
            return
        self.send_html(404, "<h1>Not found</h1>")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self.send_json(400, {"error": "invalid json"})
            return

        if self.path == "/govern":
            try:
                result = govern(data)
                self.send_json(200, result)
            except Exception as e:
                self.send_json(500, {"error": str(e)})
            return

        if self.path == "/signup":
            email = data.get("email", "").strip()
            company = data.get("company", "").strip()
            if not email or not company:
                self.send_json(400, {"error": "missing fields"})
                return
            if not STRIPE_SECRET.startswith("sk_live_YOUR"):
                try:
                    import urllib.request
                    params = urllib.parse.urlencode({
                        "success_url": "https://sebbi.pro/success",
                        "cancel_url": "https://sebbi.pro",
                        "mode": "subscription",
                        "line_items[0][price]": STRIPE_PRICE,
                        "line_items[0][quantity]": "1",
                        "customer_email": email,
                        "metadata[company]": company,
                    }).encode()
                    req = urllib.request.Request(
                        "https://api.stripe.com/v1/checkout/sessions",
                        data=params,
                        headers={
                            "Authorization": "Bearer " + STRIPE_SECRET,
                            "Content-Type": "application/x-www-form-urlencoded"
                        }
                    )
                    resp = urllib.request.urlopen(req)
                    session = json.loads(resp.read())
                    self.send_json(200, {"stripe_url": session["url"]})
                    return
                except Exception as e:
                    self.send_json(500, {"error": str(e)})
                    return
            key = make_licence_key(email)
            expires = now() + (30 * 86400)
            lc.execute(
                "INSERT OR REPLACE INTO licences"
                "(email,company,licence_key,stripe_customer,"
                "stripe_subscription,status,created_ts,expires_ts)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (email, company, key, "demo", "demo", "ACTIVE", now(), expires)
            )
            lc.commit()
            print("NEW SIGNUP: " + email + " | " + company)
            self.send_json(200, {"licence_key": key, "email": email})
            return

        if self.path == "/webhook":
            try:
                event = json.loads(body)
                if event.get("type") == "checkout.session.completed":
                    session = event["data"]["object"]
                    email = session.get("customer_email", "")
                    company = session.get("metadata", {}).get("company", "")
                    stripe_customer = session.get("customer", "")
                    stripe_sub = session.get("subscription", "")
                    if email:
                        key = make_licence_key(email)
                        expires = now() + (30 * 86400)
                        lc.execute(
                            "INSERT OR REPLACE INTO licences"
                            "(email,company,licence_key,stripe_customer,"
                            "stripe_subscription,status,created_ts,expires_ts)"
                            " VALUES(?,?,?,?,?,?,?,?)",
                            (email, company, key, stripe_customer, stripe_sub,
                             "ACTIVE", now(), expires)
                        )
                        lc.commit()
                        print("STRIPE PAYMENT: " + email + " | " + company)
                self.send_json(200, {"received": True})
            except Exception as e:
                self.send_json(400, {"error": str(e)})
            return

        if self.path == "/verify":
            email = data.get("email", "")
            key = data.get("licence_key", "")
            row = lc.execute(
                "SELECT status FROM licences WHERE email=? AND licence_key=?",
                (email, key)
            ).fetchone()
            if not row:
                self.send_json(403, {"status": "INVALID"})
                return
            if row["status"] != "ACTIVE":
                self.send_json(403, {"status": "EXPIRED"})
                return
            self.send_json(200, {"status": "ACTIVE"})
            return

        self.send_json(404, {"error": "not found"})

print("AILeash server starting on port " + str(PORT))
server = HTTPServer(("0.0.0.0", PORT), Handler)
server.serve_forever()
