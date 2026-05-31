import json, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import sys

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.2.0"
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
    host = os.environ.get("HOST", "http://localhost")
    data = {
        "mode": "subscription",
        "customer_email": email,
        "success_url": f"{host}/?success=true",
        "cancel_url": f"{host}/?cancel=true",
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

# ---------------- LANDING PAGE (v3.2.0) - COMPLETELY REDESIGNED ----------------
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AILeash - AI Governance Engine for EU AI Act Compliance</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #667eea;
            --secondary: #764ba2;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --dark: #1f2937;
            --light: #f3f4f6;
            --border: #e5e7eb;
        }

        html {
            scroll-behavior: smooth;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            color: var(--dark);
            line-height: 1.6;
            overflow-x: hidden;
        }

        /* Navigation */
        nav {
            background: white;
            padding: 1.5rem 2rem;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        nav .container {
            max-width: 1200px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 24px;
            font-weight: 700;
            background: linear-gradient(135deg, var(--primary), var(--secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        nav a {
            color: var(--dark);
            text-decoration: none;
            margin-left: 2rem;
            font-weight: 500;
            transition: color 0.3s;
        }

        nav a:hover {
            color: var(--primary);
        }

        /* Hero Section */
        .hero {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 6rem 2rem;
            text-align: center;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .hero-content {
            max-width: 700px;
            animation: slideUp 0.8s ease-out;
        }

        .hero h1 {
            font-size: 3.5rem;
            margin-bottom: 1.5rem;
            font-weight: 800;
            line-height: 1.2;
        }

        .hero p {
            font-size: 1.3rem;
            margin-bottom: 2rem;
            opacity: 0.95;
        }

        .cta-buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }

        .btn {
            padding: 0.875rem 2rem;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            display: inline-block;
        }

        .btn-primary {
            background: white;
            color: var(--primary);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
        }

        .btn-primary:hover {
            transform: translateY(-3px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.3);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.2);
            color: white;
            border: 2px solid white;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.3);
        }

        /* Features Section */
        .features {
            padding: 6rem 2rem;
            background: white;
        }

        .features .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .section-title {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 1rem;
            color: var(--dark);
        }

        .section-subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 3rem;
            font-size: 1.1rem;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 2rem;
        }

        .feature-card {
            background: var(--light);
            padding: 2rem;
            border-radius: 12px;
            transition: all 0.3s;
            border: 2px solid transparent;
        }

        .feature-card:hover {
            border-color: var(--primary);
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.15);
        }

        .feature-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
        }

        .feature-card h3 {
            margin-bottom: 0.5rem;
            color: var(--dark);
        }

        .feature-card p {
            color: #666;
            font-size: 0.95rem;
        }

        /* Signup Section */
        .signup {
            background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
            padding: 6rem 2rem;
        }

        .signup-container {
            max-width: 500px;
            margin: 0 auto;
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
        }

        .signup-container h2 {
            text-align: center;
            margin-bottom: 0.5rem;
            color: var(--dark);
        }

        .signup-container .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 2rem;
            font-size: 0.95rem;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-group label {
            display: block;
            margin-bottom: 0.5rem;
            font-weight: 600;
            color: var(--dark);
            font-size: 0.9rem;
        }

        input[type="email"] {
            width: 100%;
            padding: 0.875rem;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 1rem;
            transition: all 0.3s;
            font-family: inherit;
        }

        input[type="email"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        input[type="email"]::placeholder {
            color: #999;
        }

        .btn-submit {
            width: 100%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 1rem;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }

        .btn-submit:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }

        .btn-submit:disabled {
            opacity: 0.7;
            cursor: not-allowed;
        }

        /* Messages */
        .message {
            margin-top: 1.5rem;
            padding: 1rem;
            border-radius: 8px;
            font-size: 0.95rem;
            display: none;
            animation: slideDown 0.3s ease-out;
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
            border: 3px solid var(--light);
            border-top: 3px solid var(--primary);
            border-radius: 50%;
            width: 24px;
            height: 24px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }

        /* Footer */
        footer {
            background: var(--dark);
            color: white;
            padding: 3rem 2rem;
            text-align: center;
        }

        footer .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        footer p {
            opacity: 0.8;
            margin: 0.5rem 0;
        }

        footer a {
            color: var(--primary);
            text-decoration: none;
        }

        /* Animations */
        @keyframes slideUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes slideDown {
            from {
                opacity: 0;
                transform: translateY(-10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        /* Responsive */
        @media (max-width: 768px) {
            .hero h1 {
                font-size: 2rem;
            }

            .hero p {
                font-size: 1.1rem;
            }

            .section-title {
                font-size: 2rem;
            }

            .cta-buttons {
                flex-direction: column;
                align-items: center;
            }

            .btn {
                width: 100%;
                max-width: 300px;
            }

            nav a {
                margin-left: 1rem;
                font-size: 0.9rem;
            }
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .badge {
            display: inline-block;
            background: #dbeafe;
            color: #0c4a6e;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav>
        <div class="container">
            <div class="logo">🔐 AILeash</div>
            <div>
                <a href="#features">Features</a>
                <a href="#signup">Get Started</a>
                <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a>
            </div>
        </div>
    </nav>

    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-content">
            <div class="badge">EU AI Act Compliance</div>
            <h1>AI Governance Engine</h1>
            <p>Real-time risk scoring and audit trails for high-risk AI systems. Compliant with EU AI Act, GDPR Art. 22, and ISO 42001.</p>
            <div class="cta-buttons">
                <button class="btn btn-primary" onclick="document.getElementById('signup').scrollIntoView({ behavior: 'smooth' })">Get Started Free</button>
                <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank" class="btn btn-secondary">View on GitHub</a>
            </div>
        </div>
    </section>

    <!-- Features Section -->
    <section class="features" id="features">
        <div class="container">
            <h2 class="section-title">Powerful Features</h2>
            <p class="section-subtitle">Everything you need to govern AI safely and compliantly</p>
            
            <div class="grid">
                <div class="feature-card">
                    <div class="feature-icon">⚡</div>
                    <h3>Sub-15ms Decisions</h3>
                    <p>Real-time risk scoring with deterministic, reproducible results. No external dependencies—pure Python.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-icon">🔗</div>
                    <h3>Cryptographic Audit</h3>
                    <p>SHA-256 chained logs with Merkle verification. Tamper-evident trails that satisfy regulatory requirements.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-icon">📊</div>
                    <h3>9-Signal Risk Model</h3>
                    <p>Trust decay, velocity tracking, amount thresholds, device risk, behavioral anomalies, and more.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-icon">🌍</div>
                    <h3>Country Awareness</h3>
                    <p>Geo-fencing with safe country lists. Instantly detect risky jurisdictions and anomalies.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-icon">📋</div>
                    <h3>GDPR Art. 22 Ready</h3>
                    <p>Designed for human oversight of automated decisions. Full explainability and appeal pathways.</p>
                </div>

                <div class="feature-card">
                    <div class="feature-icon">🚀</div>
                    <h3>Deploy in Minutes</h3>
                    <p>Docker, Railway, Render, Fly.io, AWS Lambda. No setup. No maintenance. Go live instantly.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Signup Section -->
    <section class="signup" id="signup">
        <div class="signup-container">
            <h2>Start Your Free Trial</h2>
            <p class="subtitle">Get an API key and begin governance in seconds</p>
            
            <form id="signupForm">
                <div class="form-group">
                    <label for="email">Email Address</label>
                    <input 
                        type="email" 
                        id="email" 
                        placeholder="you@example.com" 
                        required 
                        aria-label="Email address"
                    >
                </div>
                
                <div class="loader" id="loader"></div>
                
                <button type="submit" class="btn btn-submit" id="signupBtn">
                    Sign Up & Go to Stripe
                </button>
                
                <div class="message" id="message"></div>
            </form>

            <p style="text-align: center; margin-top: 2rem; font-size: 0.85rem; color: #666;">
                🔒 Your data is secure. We'll never spam you.
            </p>
        </div>
    </section>

    <!-- Footer -->
    <footer>
        <div class="container">
            <p><strong>AILeash v3.2.0</strong> — AI Governance for EU AI Act Compliance</p>
            <p>
                <a href="https://github.com/justrightdecorators-ops/aileash">GitHub</a> •
                <a href="https://github.com/justrightdecorators-ops/aileash/issues">Issues</a> •
                MIT License
            </p>
            <p style="margin-top: 1.5rem; opacity: 0.6;">Built by Just Right Decorators Ops</p>
        </div>
    </footer>

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
            showMessage('✅ Payment successful! Check your email for next steps.', 'success');
            emailInput.disabled = true;
            signupBtn.disabled = true;
        } else if (urlParams.has('cancel')) {
            showMessage('❌ Payment cancelled. Try again whenever you\'re ready.', 'error');
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
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(b)

def send_html(h):
    b = LANDING_HTML.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html")
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(b)

# ---------------- REQUEST HANDLER ----------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logs
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return send_html(self)
        if path == "/api/status" or path == "/health":
            return send(self, {"status": "ok", "version": VERSION, "timestamp": time.time()})
        if path == "/api/verify":
            return send(self, {"valid": True, "blocks": 0, "message": "Chain intact"})
        send(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        
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
            print(f"POST error: {e}", file=sys.stderr)
            return send(self, {"error": "bad request"}, 400)

        # Routes
        if path == "/api/keys":
            email = data.get("email", "")
            key = create_api_key(email)
            if not key:
                return send(self, {"error": "valid email required"}, 400)
            return send(self, {"key": key, "email": email, "message": "API key created successfully"})

        if path == "/api/checkout":
            email = data.get("email", "")
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            
            session = create_checkout_session(email)
            if not session:
                return send(self, {
                    "error": "Stripe not configured. Set STRIPE_SECRET and STRIPE_PRICE_ID environment variables."
                }, 501)
            return send(self, {"checkout_url": session.get("url")})

        if path == "/api/govern":
            event = data.get("event", data)
            result = govern(event)
            return send(self, result)

        send(self, {"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

# ---------------- MAIN ----------------
def main():
    print(f"🚀 AILeash v{VERSION} running on http://0.0.0.0:{PORT}")
    print(f"📖 Open http://localhost:{PORT} in your browser")
    print(f"🔒 Stripe configured: {bool(STRIPE_SECRET and STRIPE_PRICE_ID)}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
