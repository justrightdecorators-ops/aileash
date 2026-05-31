import json, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import sys

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.3.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
FREE_QUOTA      = 100  # Free tries per account

_db_lock = threading.Lock()

# ---------------- DB ----------------
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0, free_quota INTEGER DEFAULT 100)")
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
        print(f"Stripe API error: {e}", file=sys.stderr)
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
def create_api_key(email, is_paid=False):
    email = str(email).strip()
    if not email or '@' not in email:
        return None
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        _conn.execute("INSERT INTO api_keys VALUES(?,?,?,?,?,?,?,?)",
                     (key, email, "", 0, time.time(), 1, 1 if is_paid else 0, FREE_QUOTA))
        _conn.commit()
    return key

def get_key_info(key):
    with _db_lock:
        cursor = _conn.execute("SELECT email, actions_used, active, is_paid, free_quota FROM api_keys WHERE key = ?", (key,))
        result = cursor.fetchone()
    return result

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used = actions_used + 1 WHERE key = ?", (key,))
        _conn.commit()

# ---------------- GOVERN CORE ----------------
def govern(event, key=None):
    # Check quota if key is provided
    if key:
        key_info = get_key_info(key)
        if not key_info:
            return {
                "decision": "BLOCK",
                "score": 1.0,
                "reasons": ["invalid_api_key"],
                "version": VERSION,
                "timestamp": time.time()
            }
        
        email, actions_used, active, is_paid, free_quota = key_info
        
        if not active:
            return {
                "decision": "BLOCK",
                "score": 1.0,
                "reasons": ["key_inactive"],
                "version": VERSION,
                "timestamp": time.time()
            }
        
        # Check free quota
        if not is_paid and actions_used >= free_quota:
            return {
                "decision": "BLOCK",
                "score": 1.0,
                "reasons": ["free_quota_exceeded"],
                "message": f"Free quota ({free_quota}) exceeded. Upgrade to continue.",
                "version": VERSION,
                "timestamp": time.time()
            }
        
        increment_usage(key)
    
    return {
        "decision": "ALLOW",
        "score": 0.12,
        "reasons": ["demo_mode", "low_risk"],
        "version": VERSION,
        "timestamp": time.time()
    }

# ================ LANDING PAGE (v3.3.0) ================
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
            cursor: pointer;
        }

        nav .nav-links {
            display: flex;
            gap: 2rem;
        }

        nav a {
            color: var(--dark);
            text-decoration: none;
            font-weight: 500;
            transition: color 0.3s;
            font-size: 0.95rem;
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

        /* Info Section */
        .info-section {
            padding: 4rem 2rem;
            background: var(--light);
        }

        .info-section .container {
            max-width: 1000px;
            margin: 0 auto;
        }

        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 2rem;
            margin-top: 2rem;
        }

        .info-box {
            background: white;
            padding: 2rem;
            border-radius: 12px;
            border-left: 4px solid var(--primary);
        }

        .info-box h4 {
            color: var(--primary);
            margin-bottom: 0.5rem;
        }

        .info-box p {
            color: #666;
            font-size: 0.95rem;
        }

        /* Pricing Section */
        .pricing {
            padding: 6rem 2rem;
            background: white;
        }

        .pricing .container {
            max-width: 1000px;
            margin: 0 auto;
        }

        .pricing-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-top: 3rem;
        }

        .pricing-card {
            border: 2px solid var(--border);
            border-radius: 12px;
            padding: 2rem;
            text-align: center;
            transition: all 0.3s;
        }

        .pricing-card:hover {
            border-color: var(--primary);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.15);
        }

        .pricing-card.featured {
            border-color: var(--primary);
            transform: scale(1.05);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.25);
        }

        .pricing-card h3 {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
        }

        .price {
            font-size: 2.5rem;
            color: var(--primary);
            font-weight: bold;
            margin: 1rem 0;
        }

        .price-period {
            color: #666;
            font-size: 0.95rem;
        }

        .features-list {
            text-align: left;
            margin: 2rem 0;
            list-style: none;
        }

        .features-list li {
            padding: 0.5rem 0;
            color: #666;
            border-bottom: 1px solid var(--border);
        }

        .features-list li:before {
            content: "✓ ";
            color: var(--success);
            font-weight: bold;
            margin-right: 0.5rem;
        }

        /* Auth Sections */
        .auth-section {
            background: linear-gradient(135deg, #667eea15 0%, #764ba215 100%);
            padding: 6rem 2rem;
        }

        .auth-container {
            max-width: 450px;
            margin: 0 auto;
            background: white;
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
        }

        .auth-container h2 {
            text-align: center;
            margin-bottom: 0.5rem;
            color: var(--dark);
        }

        .auth-container .subtitle {
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

        input[type="email"], input[type="text"] {
            width: 100%;
            padding: 0.875rem;
            border: 2px solid var(--border);
            border-radius: 8px;
            font-size: 1rem;
            transition: all 0.3s;
            font-family: inherit;
        }

        input[type="email"]:focus, input[type="text"]:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        input::placeholder {
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

        .toggle-auth {
            text-align: center;
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
        }

        .toggle-auth a {
            color: var(--primary);
            text-decoration: none;
            font-weight: 600;
            cursor: pointer;
        }

        .toggle-auth a:hover {
            text-decoration: underline;
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

        .hidden {
            display: none !important;
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

            nav .nav-links {
                gap: 1rem;
                font-size: 0.85rem;
            }

            .pricing-card.featured {
                transform: scale(1);
            }
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
    </style>
</head>
<body>
    <!-- Navigation -->
    <nav>
        <div class="container">
            <div class="logo" onclick="window.location.href='/'">🔐 AILeash</div>
            <div class="nav-links">
                <a href="#features">Features</a>
                <a href="#how-it-works">How It Works</a>
                <a href="#pricing">Pricing</a>
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
                <button class="btn btn-primary" onclick="showAuthSection('free')">Get 100 Free Uses</button>
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

    <!-- How It Works -->
    <section class="info-section" id="how-it-works">
        <div class="container">
            <h2 class="section-title">How It Works</h2>
            <p class="section-subtitle">Complete AI governance in 3 simple steps</p>
            
            <div class="info-grid">
                <div class="info-box">
                    <h4>1️⃣ Get API Key</h4>
                    <p>Sign up for free and receive an API key with 100 governance calls included. No credit card required.</p>
                </div>

                <div class="info-box">
                    <h4>2️⃣ Make Risk Calls</h4>
                    <p>Send AI actions to our endpoint. We analyze 9 risk signals and return instant ALLOW/CHALLENGE/BLOCK decisions.</p>
                </div>

                <div class="info-box">
                    <h4>3️⃣ Scale & Comply</h4>
                    <p>Hit your quota? Upgrade to unlimited. All decisions are cryptographically audited and compliant with EU AI Act.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Risk Scoring Info -->
    <section class="info-section">
        <div class="container">
            <h2 class="section-title">Advanced Risk Scoring</h2>
            <p class="section-subtitle">Multi-signal analysis for enterprise-grade AI governance</p>
            
            <div class="info-grid">
                <div class="info-box">
                    <h4>Trust Scoring (30%)</h4>
                    <p>User-specific trust history with exponential decay. Learns from past behavior patterns and adjusts risk dynamically.</p>
                </div>

                <div class="info-box">
                    <h4>Velocity Tracking (35%)</h4>
                    <p>Actions in last 60s, 5m, 1h windows with configurable thresholds. Detects sudden bursts of activity.</p>
                </div>

                <div class="info-box">
                    <h4>Amount Scoring (15%)</h4>
                    <p>Log-scale analysis up to $10k. Higher amounts = higher risk with exponential weighting.</p>
                </div>

                <div class="info-box">
                    <h4>Device Risk (10%)</h4>
                    <p>External device risk integration. Links to your existing device fingerprinting systems.</p>
                </div>

                <div class="info-box">
                    <h4>Behavioral Anomaly (10%)</h4>
                    <p>Detects unusual patterns in user behavior. Machine learning ready for custom models.</p>
                </div>

                <div class="info-box">
                    <h4>Geographic Signals (+20%)</h4>
                    <p>Country shift detection and unsafe jurisdiction penalties. 28 whitelisted countries by default.</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Pricing Section -->
    <section class="pricing" id="pricing">
        <div class="container">
            <h2 class="section-title">Simple Pricing</h2>
            <p class="section-subtitle">Start free, upgrade when you need to scale</p>
            
            <div class="pricing-cards">
                <div class="pricing-card">
                    <h3>🎯 Starter</h3>
                    <div class="price">Free</div>
                    <p class="price-period">Perfect for exploring</p>
                    <ul class="features-list">
                        <li>100 governance calls</li>
                        <li>Full risk scoring</li>
                        <li>Audit logs</li>
                        <li>API access</li>
                        <li>Community support</li>
                    </ul>
                    <button class="btn btn-primary" onclick="showAuthSection('free')" style="width: 100%; margin-top: 1rem;">Get Started Free</button>
                </div>

                <div class="pricing-card featured">
                    <h3>⚡ Professional</h3>
                    <div class="price">$99</div>
                    <p class="price-period">per month</p>
                    <ul class="features-list">
                        <li>Unlimited calls</li>
                        <li>All Starter features</li>
                        <li>Priority support</li>
                        <li>Custom integrations</li>
                        <li>Advanced analytics</li>
                        <li>SLA guarantee</li>
                    </ul>
                    <button class="btn btn-submit" onclick="showAuthSection('paid')" style="width: 100%; margin-top: 1rem;">Upgrade Now</button>
                </div>

                <div class="pricing-card">
                    <h3>🏢 Enterprise</h3>
                    <div class="price">Custom</div>
                    <p class="price-period">per month</p>
                    <ul class="features-list">
                        <li>Unlimited everything</li>
                        <li>Dedicated support</li>
                        <li>Custom models</li>
                        <li>On-premise option</li>
                        <li>Legal agreement</li>
                        <li>Training included</li>
                    </ul>
                    <a href="mailto:support@aileash.dev" class="btn btn-primary" style="width: 100%; margin-top: 1rem;">Contact Sales</a>
                </div>
            </div>
        </div>
    </section>

    <!-- Auth Sections -->
    <section class="auth-section" id="free-auth-section" style="display: none;">
        <div class="auth-container">
            <h2>Free Account</h2>
            <p class="subtitle">Get 100 free governance calls, no credit card needed</p>
            
            <form id="freeSignupForm">
                <div class="form-group">
                    <label for="free-email">Email Address</label>
                    <input type="email" id="free-email" placeholder="you@example.com" required>
                </div>
                <div class="form-group">
                    <label for="free-name">Full Name (optional)</label>
                    <input type="text" id="free-name" placeholder="John Doe">
                </div>
                
                <div class="loader" id="free-loader"></div>
                <button type="submit" class="btn btn-submit" id="freeSignupBtn">Create Free Account</button>
                
                <div class="message" id="free-message"></div>
            </form>

            <div class="toggle-auth">
                Want to upgrade instead? <a onclick="showAuthSection('paid')">Go to Stripe</a>
            </div>
        </div>
    </section>

    <section class="auth-section" id="paid-auth-section" style="display: none;">
        <div class="auth-container">
            <h2>Professional Plan</h2>
            <p class="subtitle">$99/month for unlimited governance calls</p>
            
            <form id="paidSignupForm">
                <div class="form-group">
                    <label for="paid-email">Email Address</label>
                    <input type="email" id="paid-email" placeholder="you@example.com" required>
                </div>
                
                <div class="loader" id="paid-loader"></div>
                <button type="submit" class="btn btn-submit" id="paidSignupBtn">Proceed to Payment</button>
                
                <div class="message" id="paid-message"></div>
            </form>

            <div class="toggle-auth">
                Prefer to start free? <a onclick="showAuthSection('free')">Create Free Account</a>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer>
        <div class="container">
            <p><strong>AILeash v3.3.0</strong> — AI Governance for EU AI Act Compliance</p>
            <p>
                <a href="https://github.com/justrightdecorators-ops/aileash">GitHub</a> •
                <a href="https://github.com/justrightdecorators-ops/aileash/issues">Issues</a> •
                MIT License
            </p>
            <p style="margin-top: 1.5rem; opacity: 0.6;">Built by Just Right Decorators Ops</p>
        </div>
    </footer>

    <script>
        function showAuthSection(type) {
            document.getElementById('free-auth-section').style.display = type === 'free' ? 'block' : 'none';
            document.getElementById('paid-auth-section').style.display = type === 'paid' ? 'block' : 'none';
            document.querySelector('html').scrollIntoView({ behavior: 'smooth' });
            setTimeout(() => {
                const target = type === 'free' ? document.getElementById('free-auth-section') : document.getElementById('paid-auth-section');
                target.scrollIntoView({ behavior: 'smooth' });
            }, 100);
        }

        // Free Signup
        const freeForm = document.getElementById('freeSignupForm');
        const freeEmail = document.getElementById('free-email');
        const freeName = document.getElementById('free-name');
        const freeSignupBtn = document.getElementById('freeSignupBtn');
        const freeLoader = document.getElementById('free-loader');
        const freeMessage = document.getElementById('free-message');

        freeForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = freeEmail.value.trim();
            if (!email) {
                showMessage(freeMessage, 'Please enter a valid email', 'error');
                return;
            }

            freeSignupBtn.disabled = true;
            freeLoader.style.display = 'block';
            freeMessage.style.display = 'none';

            try {
                const response = await fetch('/api/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, name: freeName.value })
                });

                const data = await response.json();

                if (!response.ok) {
                    showMessage(freeMessage, data.error || 'An error occurred', 'error');
                    freeSignupBtn.disabled = false;
                    freeLoader.style.display = 'none';
                    return;
                }

                showMessage(freeMessage, `✅ API Key created! Key: <code>${data.key}</code>. Check your email for details.`, 'success');
                freeForm.reset();
                freeSignupBtn.disabled = true;
            } catch (error) {
                showMessage(freeMessage, 'Network error: ' + error.message, 'error');
                freeSignupBtn.disabled = false;
            }
            freeLoader.style.display = 'none';
        });

        // Paid Signup
        const paidForm = document.getElementById('paidSignupForm');
        const paidEmail = document.getElementById('paid-email');
        const paidSignupBtn = document.getElementById('paidSignupBtn');
        const paidLoader = document.getElementById('paid-loader');
        const paidMessage = document.getElementById('paid-message');

        paidForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const email = paidEmail.value.trim();
            if (!email) {
                showMessage(paidMessage, 'Please enter a valid email', 'error');
                return;
            }

            paidSignupBtn.disabled = true;
            paidLoader.style.display = 'block';
            paidMessage.style.display = 'none';

            try {
                const response = await fetch('/api/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });

                const data = await response.json();

                if (!response.ok) {
                    showMessage(paidMessage, data.error || 'An error occurred', 'error');
                    paidSignupBtn.disabled = false;
                    paidLoader.style.display = 'none';
                    return;
                }

                if (data.checkout_url) {
                    window.location.href = data.checkout_url;
                } else {
                    showMessage(paidMessage, 'Error getting checkout URL', 'error');
                    paidSignupBtn.disabled = false;
                }
            } catch (error) {
                showMessage(paidMessage, 'Network error: ' + error.message, 'error');
                paidSignupBtn.disabled = false;
            }
            paidLoader.style.display = 'none';
        });

        function showMessage(container, text, type) {
            container.innerHTML = text;
            container.className = 'message ' + type;
            container.style.display = 'block';
        }

        // Check for success/cancel
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('success')) {
            setTimeout(() => {
                alert('✅ Payment successful! Check your email for next steps.');
            }, 500);
        } else if (urlParams.has('cancel')) {
            showAuthSection('paid');
            showMessage(paidMessage, '❌ Payment cancelled. Try again whenever you\'re ready.', 'error');
        }
    </script>
</body>
</html>
"""

# ================ HTTP HELPERS ================
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

# ================ REQUEST HANDLER ================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
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
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            
            key = create_api_key(email, is_paid=False)
            if not key:
                return send(self, {"error": "error creating key"}, 500)
            
            return send(self, {
                "key": key,
                "email": email,
                "message": "Free account created! 100 governance calls included.",
                "free_quota": FREE_QUOTA
            })

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
            auth_header = self.headers.get("Authorization", "")
            key = None
            
            if auth_header.startswith("Bearer "):
                key = auth_header[7:]
            
            event = data.get("event", data)
            result = govern(event, key)
            return send(self, result)

        send(self, {"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

# ================ MAIN ================
def main():
    print(f"🚀 AILeash v{VERSION} running on http://0.0.0.0:{PORT}")
    print(f"📖 Open http://localhost:{PORT} in your browser")
    print(f"💳 Stripe configured: {bool(STRIPE_SECRET and STRIPE_PRICE_ID)}")
    print(f"📊 Free quota: {FREE_QUOTA} calls per account")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
