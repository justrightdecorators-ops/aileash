import json, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.1.1"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}

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
        print(f"Stripe API error: {e}")
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
    email = str(email).strip()
    if not email or '@' not in email:
        return None
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        _conn.execute("INSERT INTO api_keys VALUES(?,?,?,?,?,?)",
                     (key, email, "", 0, time.time(), 1))
        _conn.commit()
    return key

# ---------------- GOVERN CORE ----------------
def govern(event):
    return {
        "decision": "ALLOW",
        "score": 0.12,
        "reasons": ["demo_mode", "low_risk"],
        "version": VERSION,
        "timestamp": time.time()
    }

# ---------------- LANDING PAGE (v3.1.1) ----------------
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AILeash - AI Governance Engine</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 500px;
            width: 100%;
            padding: 40px;
            text-align: center;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 28px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        input[type="email"] {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 6px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input[type="email"]:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 32px;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            width: 100%;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.4);
        }
        .btn:disabled {
            opacity: 0.7;
            cursor: not-allowed;
        }
        .message {
            margin-top: 20px;
            padding: 12px;
            border-radius: 6px;
            font-size: 14px;
            display: none;
        }
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .loader {
            display: none;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔐 AILeash</h1>
        <p class="subtitle">AI Governance Engine for the EU AI Act</p>
        
        <form id="signupForm">
            <div class="form-group">
                <input 
                    type="email" 
                    id="email" 
                    placeholder="Enter your email" 
                    required 
                    aria-label="Email address"
                >
            </div>
            <button type="submit" class="btn" id="signupBtn">
                Sign Up & Go to Stripe
            </button>
            <div class="loader" id="loader"></div>
        </form>
        
        <div class="message" id="message"></div>
    </div>

    <script>
        const form = document.getElementById('signupForm');
        const emailInput = document.getElementById('email');
        const signupBtn = document.getElementById('signupBtn');
        const loader = document.getElementById('loader');
        const message = document.getElementById('message');

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = emailInput.value.trim();
            if (!email) {
                showMessage('Please enter a valid email', 'error');
                return;
            }

            signupBtn.disabled = true;
            loader.style.display = 'block';
            message.style.display = 'none';

            try {
                const response = await fetch('/api/checkout', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (!response.ok) {
                    showMessage(data.error || 'An error occurred', 'error');
                    signupBtn.disabled = false;
                    loader.style.display = 'none';
                    return;
                }

                if (data.checkout_url) {
                    // Redirect to Stripe checkout
                    window.location.href = data.checkout_url;
                } else {
                    showMessage('Error getting checkout URL', 'error');
                    signupBtn.disabled = false;
                    loader.style.display = 'none';
                }
            } catch (error) {
                showMessage('Network error: ' + error.message, 'error');
                signupBtn.disabled = false;
                loader.style.display = 'none';
            }
        });

        function showMessage(text, type) {
            message.textContent = text;
            message.className = 'message ' + type;
            message.style.display = 'block';
        }

        // Check for success/cancel from Stripe redirect
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('success')) {
            showMessage('✅ Payment successful! Welcome to AILeash.', 'success');
            emailInput.disabled = true;
            signupBtn.disabled = true;
        } else if (urlParams.has('cancel')) {
            showMessage('❌ Payment cancelled. Please try again.', 'error');
        }
    </script>
</body>
</html>
"""

# ---------------- HTTP HELPERS ----------------
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

# ---------------- REQUEST HANDLER ----------------
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
        
        # === FIXED JSON PARSING ===
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = self.rfile.read(length)
                data = json.loads(body)
            else:
                data = {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return send(self, {"error": "invalid json"}, 400)
        except Exception as e:
            print(f"POST error: {e}")
            return send(self, {"error": "bad request"}, 400)

        # Routes
        if path == "/api/keys":
            email = data.get("email", "")
            key = create_api_key(email)
            if not key:
                return send(self, {"error": "valid email required"}, 400)
            return send(self, {"key": key, "message": "API key created successfully"})

        if path == "/api/checkout":
            email = data.get("email", "")
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            
            session = create_checkout_session(email)
            if not session:
                return send(self, {
                    "error": "Stripe not configured. Set STRIPE_SECRET and STRIPE_PRICE_ID environment variables."
                }, 501)
            return send(self, {"checkout_url": session["url"]})

        if path == "/api/govern":
            event = data.get("event", data)  # accept event directly or wrapped
            result = govern(event)
            return send(self, result)

        send(self, {"error": "not found"}, 404)

# ---------------- MAIN ----------------
def main():
    print(f"🚀 AILeash v{VERSION} running on http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
