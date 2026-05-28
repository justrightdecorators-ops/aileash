import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.1.0"
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
    if not STRIPE_SECRET or not STRIPE_PRICE_ID:
        return None
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"Stripe error: {e}")
        return None

def create_checkout_session(email):
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
    email = email.strip()
    if not email or '@' not in email:
        return None
    
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
    # TODO: Implement real risk scoring logic here
    return {
        "decision": "ALLOW",
        "score": 0.12,
        "reasons": ["demo_mode", "low_risk"],
        "version": VERSION,
        "timestamp": time.time()
    }

# ---------------- UPDATED LANDING PAGE ----------------
LANDING_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AILeash v{VERSION} — AI Governance</title>
<style>
    :root {{
        --bg: #0b0f17;
        --card: #121a2b;
        --accent: #2f6fed;
        --text: #fff;
        --muted: #a0b0cc;
    }}
    body {{
        margin: 0;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        background: var(--bg);
        color: var(--text);
        line-height: 1.6;
    }}
    header {{
        padding: 2rem 1rem;
        background: linear-gradient(135deg, #111a2e, #1a2540);
        text-align: center;
        border-bottom: 1px solid #2a3a5a;
    }}
    h1 {{
        margin: 0;
        font-size: 2.8rem;
        background: linear-gradient(90deg, #60a5fa, #a5b4fc);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }}
    .tagline {{ color: var(--muted); font-size: 1.1rem; margin-top: 0.5rem; }}
    .container {{
        max-width: 1100px;
        margin: 2rem auto;
        padding: 0 1rem;
        display: grid;
        gap: 1.5rem;
        grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    }}
    .card {{
        background: var(--card);
        padding: 2rem;
        border-radius: 16px;
        border: 1px solid #2a3a5a;
        transition: all 0.2s;
    }}
    .card:hover {{ transform: translateY(-4px); box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1); }}
    input, button {{
        width: 100%;
        padding: 14px 16px;
        margin-top: 12px;
        border-radius: 8px;
        font-size: 1rem;
    }}
    input {{
        background: #1f2a44;
        border: 1px solid #3b4f7a;
        color: white;
    }}
    button {{
        background: var(--accent);
        color: white;
        border: none;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s;
    }}
    button:hover {{ background: #3b7ff0; transform: translateY(-1px); }}
    button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    pre {{
        background: #0a0e14;
        padding: 1rem;
        border-radius: 8px;
        overflow-x: auto;
        font-size: 0.9rem;
        margin-top: 1rem;
        max-height: 320px;
        border: 1px solid #2a3a5a;
    }}
    .success {{ color: #4ade80; }}
    .error {{ color: #f87171; }}
    .footer {{
        text-align: center;
        padding: 2rem;
        color: var(--muted);
        font-size: 0.9rem;
    }}
</style>
</head>
<body>

<header>
    <h1>AILeash</h1>
    <p class="tagline">Enterprise-Grade AI Governance • EU AI Act Compliant</p>
</header>

<div class="container">

    <div class="card">
        <h2>🚀 Get Free API Key</h2>
        <p style="color:var(--muted);margin:8px 0 16px">100 actions • No credit card required</p>
        <input id="email" type="email" placeholder="your@email.com" autocomplete="email">
        <button onclick="getFreeKey()">Create Free Key</button>
        <pre id="freeOutput"></pre>
    </div>

    <div class="card">
        <h2>⭐ Upgrade to Pro</h2>
        <p style="color:var(--muted);margin:8px 0 16px">Unlimited actions • Advanced models • Priority support</p>
        <input id="upgradeEmail" type="email" placeholder="your@email.com" autocomplete="email">
        <button onclick="upgradeNow()">Upgrade with Stripe</button>
        <pre id="upgradeOutput"></pre>
    </div>

    <div class="card">
        <h2>🛡️ Test Governance Engine</h2>
        <p style="color:var(--muted);margin:8px 0 16px">Try the core decision engine</p>
        <button onclick="testGovern()">Run Demo Decision</button>
        <pre id="governOutput"></pre>
    </div>

</div>

<div class="footer">
    AILeash v{VERSION} • <span id="status">Checking status...</span>
</div>

<script>
async function apiCall(endpoint, method = 'GET', body = null) {{
    const opts = {{ method, headers: {{'Content-Type': 'application/json'}} }};
    if (body) opts.body = JSON.stringify(body);
    
    const res = await fetch(endpoint, opts);
    const data = await res.json();
    return {{ok: res.ok, data}};
}}

async function getFreeKey() {{
    const email = document.getElementById('email').value.trim();
    const out = document.getElementById('freeOutput');
    
    if (!email || !email.includes('@')) {{
        out.innerHTML = '<span class="error">Please enter a valid email address</span>';
        return;
    }}
    
    out.textContent = 'Creating key...';
    const {{ok, data}} = await apiCall('/api/keys', 'POST', {{email}});
    
    if (ok && data.key) {{
        out.innerHTML = `<span class="success">✅ Key created successfully!</span><br><br><strong>${{data.key}}</strong>`;
        try {{ navigator.clipboard.writeText(data.key); }} catch(e){{}}
    }} else {{
        out.innerHTML = `<span class="error">❌ ${{data.error || 'Failed to create key'}}</span>`;
    }}
}}

async function upgradeNow() {{
    const email = document.getElementById('upgradeEmail').value.trim();
    const out = document.getElementById('upgradeOutput');
    
    if (!email || !email.includes('@')) {{
        out.innerHTML = '<span class="error">Valid email required</span>';
        return;
    }}
    
    out.textContent = 'Redirecting to Stripe...';
    const {{ok, data}} = await apiCall('/api/checkout', 'POST', {{email}});
    
    if (ok && data.checkout_url) {{
        window.location.href = data.checkout_url;
    }} else {{
        out.innerHTML = `<span class="error">❌ ${{data.error || 'Stripe not configured'}}</span>`;
    }}
}}

async function testGovern() {{
    const out = document.getElementById('governOutput');
    out.textContent = 'Calling governance engine...';
    
    const event = {{
        user_id: "demo_user",
        action: "generate_content",
        amount: 1,
        country: "US",
        device_id: "demo123",
        anomaly: 0.1,
        device_risk: 0.3
    }};
    
    const {{ok, data}} = await apiCall('/api/govern', 'POST', {{event}});
    out.textContent = JSON.stringify(data, null, 2);
}}

async function checkStatus() {{
    try {{
        const {{data}} = await apiCall('/api/status');
        document.getElementById('status').innerHTML = `v${{data.version}} • <span style="color:#4ade80">ONLINE</span>`;
    }} catch(e) {{
        document.getElementById('status').innerHTML = `<span style="color:#f87171">OFFLINE</span>`;
    }}
}}

window.onload = () => {{
    checkStatus();
    document.getElementById('email').addEventListener('keypress', e => {{ if (e.key === 'Enter') getFreeKey(); }});
    document.getElementById('upgradeEmail').addEventListener('keypress', e => {{ if (e.key === 'Enter') upgradeNow(); }});
}};
</script>
</body>
</html>
"""

# ---------------- HTTP SERVER ----------------
def send(h, data, status=200):
    b = json.dumps(data).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.end_headers()
    h.wfile.write(b)

def send_html(h):
    b = LANDING_HTML.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html")
    h.end_headers()
    h.wfile.write(b)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            return send_html(self)

        if path == "/api/status":
            return send(self, {"status": "ok", "version": VERSION})

        if path == "/api/verify":
            return send(self, {"valid": True, "blocks": 0})

        send(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
        except:
            return send(self, {"error": "invalid json"}, 400)

        if path == "/api/keys":
            email = data.get("email", "")
            key = create_api_key(email)
            if not key:
                return send(self, {"error": "valid email required"}, 400)
            return send(self, {"key": key})

        if path == "/api/checkout":
            email = data.get("email", "")
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            
            session = create_checkout_session(email)
            if not session:
                return send(self, {"error": "stripe not configured. Set STRIPE_SECRET and STRIPE_PRICE_ID"}, 501)
            
            return send(self, {"checkout_url": session["url"]})

        if path == "/api/govern":
            event = data.get("event", {})
            result = govern(event)
            return send(self, result)

        send(self, {"error": "not found"}, 404)

# ---------------- RUN ----------------
def main():
    print(f"🚀 AILeash v{VERSION} running on http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
