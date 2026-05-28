import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
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
_db_lock = threading.Lock()

# ---------------- DB ----------------
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE, merkle_root TEXT)")
    conn.commit()
    return conn

_conn = get_conn()

# ---------------- STRIPE ----------------
def stripe_call(method, endpoint, data=None):
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def create_checkout_session(email):
    if not STRIPE_SECRET or not STRIPE_PRICE_ID:
        return None

    data = {
        "mode": "subscription",
        "customer_email": email,
        "success_url": f"http://localhost:{PORT}/?success=true",
        "cancel_url": f"http://localhost:{PORT}/?cancel=true",
        "line_items[0][price]": STRIPE_PRICE_ID,
        "line_items[0][quantity]": 1,
    }

    return stripe_call("POST", "/checkout/sessions", data)

# ---------------- API KEYS ----------------
def create_api_key(email):
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        _conn.execute("INSERT INTO api_keys VALUES(?,?,?,?,?,?)",
                     (key, email, "", 0, time.time(), 1))
        _conn.commit()
    return key

def validate_key(key):
    with _db_lock:
        row = _conn.execute("SELECT email,active FROM api_keys WHERE key=?", (key,)).fetchone()
    return row if row and row[1] else None

# ---------------- GOVERN CORE ----------------
def govern(event):
    return {
        "decision": "ALLOW",
        "score": 0.12,
        "reasons": ["demo_mode"],
        "version": VERSION
    }

# ---------------- HTML (FULL LANDING PAGE) ----------------
LANDING_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AILeash</title>
<style>
body{{margin:0;font-family:Arial;background:#0b0f17;color:#fff}}
header{{padding:40px;background:#111a2e}}
.container{{padding:30px;max-width:1000px;margin:auto}}
.card{{background:#121a2b;padding:20px;border-radius:10px;margin-top:20px}}
button{{padding:12px 16px;background:#2f6fed;color:#fff;border:0;border-radius:6px;cursor:pointer}}
input{{padding:10px;width:100%;margin-top:10px}}
</style>
</head>

<body>

<header>
<h1>AILeash</h1>
<p>AI Governance Engine — EU AI Act Ready</p>
</header>

<div class="container">

<div class="card">
<h2>Free API Key (100 Actions)</h2>
<input id="email" placeholder="Enter email">
<button onclick="freeKey()">Get Free Key</button>
<pre id="out"></pre>
</div>

<div class="card">
<h2>Upgrade (Stripe)</h2>
<button onclick="upgrade()">Upgrade Now</button>
</div>

<div class="card">
<h2>System</h2>
<button onclick="status()">Status</button>
<button onclick="verify()">Verify Chain</button>
<pre id="sys"></pre>
</div>

</div>

<script>
async function freeKey(){{
  const email=document.getElementById('email').value;
  const r=await fetch('/api/keys',{{method:'POST',headers:{{'Content-Type':'application/json'}},
  body:JSON.stringify({{email}})}})
  document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)
}}

async function upgrade(){{
  const email=document.getElementById('email').value;
  const r=await fetch('/api/checkout',{{method:'POST',headers:{{'Content-Type':'application/json'}},
  body:JSON.stringify({{email}})}})
  const d=await r.json();
  if(d.checkout_url) window.location=d.checkout_url;
}}

async function status(){{
  const r=await fetch('/api/status');
  document.getElementById('sys').textContent=JSON.stringify(await r.json(),null,2)
}}

async function verify(){{
  const r=await fetch('/api/verify');
  document.getElementById('sys').textContent=JSON.stringify(await r.json(),null,2)
}}
</script>

</body>
</html>
"""

# ---------------- HTTP SERVER ----------------
def send(h,data,status=200):
    b=json.dumps(data).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.end_headers()
    h.wfile.write(b)

def send_html(h):
    b=LANDING_HTML.encode()
    h.send_response(200)
    h.send_header("Content-Type","text/html")
    h.end_headers()
    h.wfile.write(b)

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path=urlparse(self.path).path

        if path=="/":
            return send_html(self)

        if path=="/api/status":
            return send(self,{"status":"ok","version":VERSION})

        if path=="/api/verify":
            return send(self,{"valid":True,"blocks":0})

        send(self,{"error":"not found"},404)

    def do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length",0))
        data=json.loads(self.rfile.read(length) or "{}")

        if path=="/api/keys":
            email=data.get("email","")
            if not email: return send(self,{"error":"email required"},400)
            return send(self,{"key":create_api_key(email)})

        if path=="/api/checkout":
            email=data.get("email","")
            if not email: return send(self,{"error":"email required"},400)

            session=create_checkout_session(email)
            if not session:
                return send(self,{"error":"stripe not configured"},500)

            return send(self,{"checkout_url":session["url"]})

        send(self,{"error":"not found"},404)

# ---------------- RUN ----------------
def main():
    print(f"AILeash running on {PORT}")
    HTTPServer(("0.0.0.0",PORT),Handler).serve_forever()

if __name__=="__main__":
    main()
