import json
import sqlite3
import hashlib
import time
import hmac
import os
from collections import defaultdict, deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse

STRIPE_SECRET = os.environ.get("STRIPE_SECRET", "")
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = int(os.environ.get("PORT", 8080))
BASE_URL = os.environ.get("BASE_URL", "https://sebbi.pro")

SAFE = {"UK", "US", "DE", "FR", "CA", "AU"}

W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)


def now():
    return time.time()


def clamp(x):
    return max(0.0, min(1.0, x))


def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()


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

gc.execute("""
CREATE TABLE IF NOT EXISTS system_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL,
    event_type TEXT,
    detail TEXT
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
    stripe_sub TEXT,
    status TEXT DEFAULT 'ACTIVE',
    created_ts REAL,
    expires_ts REAL
)
""")

lc.commit()


def syslog(t, d=""):
    gc.execute(
        "INSERT INTO system_log(ts,event_type,detail) VALUES(?,?,?)",
        (now(), t, d)
    )
    gc.commit()


def load_user(uid):
    row = gc.execute(
        "SELECT trust,last_country FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()

    return {"trust": row[0], "last_country": row[1]} if row else {"trust": 0.5, "last_country": None}


def save_user(uid, trust, country):
    gc.execute("""
    INSERT INTO users(user_id,trust,last_country)
    VALUES(?,?,?)
    ON CONFLICT(user_id)
    DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country
    """, (uid, trust, country))
    gc.commit()


def govern(event):
    state = load_user(event["user_id"])

    country = event.get("country", "UK")
    amount = event.get("amount", 0)

    device_risk = event.get("device_risk", 0.1)
    anomaly = event.get("anomaly", 0.05)

    score = (
        (1.0 - state["trust"]) * 0.30 +
        min(amount / 1000.0, 1.0) * 0.15 +
        device_risk * 0.10 +
        anomaly * 0.10 +
        (0.10 if country not in SAFE else 0.0)
    )

    score = clamp(score)

    if score < 0.35:
        decision = "ALLOW"
    elif score < 0.70:
        decision = "CHALLENGE"
    else:
        decision = "BLOCK"

    trust = state["trust"]

    if decision == "ALLOW":
        trust += (1.0 - trust) * 0.01
    elif decision == "CHALLENGE":
        trust -= trust * 0.02
    else:
        trust -= trust * 0.08

    trust = clamp(trust)

    save_user(event["user_id"], trust, country)

    return {
        "decision": decision,
        "score": round(score, 4),
        "trust": round(trust, 4),
        "compliance": "AI governance middleware active"
    }


def stripe_checkout(email, company):
    params = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success",
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": "AILeash Compliance",
        "line_items[0][price_data][unit_amount]": "9900",
        "line_items[0][quantity]": "1",
        "customer_email": email,
        "metadata[company]": company
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=params,
        headers={
            "Authorization": "Bearer " + STRIPE_SECRET,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    return json.loads(urllib.request.urlopen(req, timeout=10).read())["url"]


# =========================
# YOUR ORIGINAL LANDING PAGE
# (ONLY FIXED: properly closed string)
# =========================

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash - AI Governance and Compliance</title>

<style>
body{background:#080808;color:#ccc;font-family:Courier New,monospace;padding:40px;line-height:1.7}
h1{color:#00ff88;font-size:48px}
.box{border:1px solid #222;padding:24px;margin-top:20px;background:#0d0d0d}
.btn{display:inline-block;background:#00ff88;color:#000;padding:14px 24px;text-decoration:none;margin-top:20px;font-weight:bold}
.small{color:#555;font-size:14px}
</style>

</head>

<body>

<h1>AILeash</h1>

<div class="box">
    <h2>AI Governance Infrastructure</h2>
    <p>Runtime AI governance, auditability, oversight, and compliance tooling.</p>
    <p>Real-time risk scoring, behavioural monitoring, and tamper-evident audit chains.</p>

    <a class="btn" href="/health">System Health</a>
</div>

<div class="box">
    <h2>API Endpoints</h2>
    <p>POST /govern</p>
    <p>POST /create-checkout</p>
    <p>GET /health</p>
</div>

<p class="small">Designed to support AI governance workflows.</p>

</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        if self.path == "/":
            return self.send_html(PAGE)

        if self.path == "/health":
            return self.send_json({"status": "ok", "service": "AILeash", "ts": now()})

        return self.send_json({"error": "not_found"}, 404)

    def do_POST(self):

        if self.path == "/govern":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            event = json.loads(body.decode())
            return self.send_json(govern(event))

        if self.path == "/create-checkout":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode())

            url = stripe_checkout(data["email"], data.get("company", ""))
            return self.send_json({"checkout_url": url})

        return self.send_json({"error": "not_found"}, 404)


if __name__ == "__main__":
    print(f"AILeash running on port {PORT}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
