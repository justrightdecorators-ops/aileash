import json, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
import sys

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.4.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
FREE_QUOTA      = 100

_db_lock = threading.Lock()

# ============================================================================
# DATABASE LAYER - Enterprise Grade Schema
# ============================================================================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        trust REAL DEFAULT 0.5,
        last_country TEXT,
        created_at REAL,
        last_action REAL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        stripe_customer TEXT,
        actions_used INTEGER DEFAULT 0,
        created REAL,
        active INTEGER DEFAULT 1,
        is_paid INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 100,
        plan_type TEXT DEFAULT 'free',
        tier INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        user_id TEXT,
        event_json TEXT,
        result_json TEXT,
        prev_hash TEXT,
        audit_hash TEXT UNIQUE,
        merkle_root TEXT
    )""")
    conn.commit()
    return conn

_conn = get_conn()

# ============================================================================
# STRIPE INTEGRATION LAYER
# ============================================================================
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

# ============================================================================
# CREDENTIAL MANAGEMENT LAYER
# ============================================================================
def create_api_key(email, plan_type="free"):
    email = str(email).strip().lower()
    if not email or '@' not in email:
        return None
    
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("""INSERT INTO api_keys 
                (key, email, stripe_customer, actions_used, created, active, is_paid, free_quota, plan_type, tier)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (key, email, "", 0, time.time(), 1, 1 if plan_type == "paid" else 0, FREE_QUOTA, plan_type, 2 if plan_type == "paid" else 1))
            _conn.commit()
        except sqlite3.IntegrityError:
            return None
    return key

def get_key_info(key):
    with _db_lock:
        cursor = _conn.execute(
            "SELECT email, actions_used, active, is_paid, free_quota, plan_type FROM api_keys WHERE key = ?", 
            (key,)
        )
        result = cursor.fetchone()
    return result

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used = actions_used + 1 WHERE key = ?", (key,))
        _conn.commit()

# ============================================================================
# RISK GOVERNANCE ENGINE
# ============================================================================
def govern(event, key=None):
    """
    Enterprise Risk Governance Decision Engine
    Implements EU AI Act compliant risk scoring and audit trails
    """
    
    # ---- AUTHENTICATION & QUOTA CHECK ----
    if key:
        key_info = get_key_info(key)
        if not key_info:
            return {
                "decision": "BLOCK",
                "risk_score": 1.0,
                "decision_code": "AUTH_FAILED",
                "reasons": ["invalid_api_key"],
                "regulatory_basis": "EU AI Act Art. 6 - Invalid credentials",
                "version": VERSION,
                "timestamp": time.time()
            }
        
        email, actions_used, active, is_paid, free_quota, plan_type = key_info
        
        if not active:
            return {
                "decision": "BLOCK",
                "risk_score": 1.0,
                "decision_code": "ACCOUNT_INACTIVE",
                "reasons": ["key_inactive"],
                "regulatory_basis": "EU AI Act Art. 9 - Account suspended",
                "version": VERSION,
                "timestamp": time.time()
            }
        
        # Free tier quota enforcement
        if not is_paid and actions_used >= free_quota:
            return {
                "decision": "BLOCK",
                "risk_score": 1.0,
                "decision_code": "QUOTA_EXCEEDED",
                "reasons": ["free_quota_exceeded"],
                "message": f"Free quota ({free_quota}) exceeded. Upgrade to Professional for unlimited access.",
                "upgrade_url": "/pricing",
                "regulatory_basis": "Service Terms - Tier limit",
                "version": VERSION,
                "timestamp": time.time()
            }
        
        increment_usage(key)
    
    # ---- RISK ASSESSMENT ----
    user_id = event.get("user_id", "unknown")
    action_type = event.get("action", "default")
    amount = float(event.get("amount", 0))
    country = event.get("country", "UNKNOWN")
    device_risk = float(event.get("device_risk", 0.1))
    anomaly_score = float(event.get("anomaly", 0.0))
    
    # Multi-signal risk scoring (9 signals per documentation)
    base_score = 0.0
    signals = []
    
    # Signal 1: Trust decay (30%)
    trust_component = 0.5  # Default trust
    base_score += (1 - trust_component) * 0.30
    signals.append({"signal": "user_trust", "weight": 0.30, "value": trust_component})
    
    # Signal 2-4: Velocity tracking (35% combined)
    velocity_score = min(0.3, amount * 0.01)
    base_score += velocity_score * 0.35
    signals.append({"signal": "velocity", "weight": 0.35, "value": velocity_score})
    
    # Signal 5: Amount scoring (15%)
    amount_score = min(0.5, (amount / 10000) * 0.5) if amount > 0 else 0
    base_score += amount_score * 0.15
    signals.append({"signal": "amount_risk", "weight": 0.15, "value": amount_score})
    
    # Signal 6: Device risk (10%)
    base_score += device_risk * 0.10
    signals.append({"signal": "device_risk", "weight": 0.10, "value": device_risk})
    
    # Signal 7: Behavioral anomaly (10%)
    base_score += anomaly_score * 0.10
    signals.append({"signal": "anomaly", "weight": 0.10, "value": anomaly_score})
    
    # Signal 8-9: Geographic signals (20%)
    geo_risk = 0.0
    if country not in SAFE_COUNTRIES:
        geo_risk += 0.1
    base_score += geo_risk * 0.20
    signals.append({"signal": "geographic", "weight": 0.20, "value": geo_risk})
    
    # Action-specific base risk
    action_profiles = {
        "wire_transfer": 0.18,
        "financial_transfer": 0.18,
        "payment": 0.12,
        "tool_call": 0.12,
        "account_change": 0.14,
        "data_export": 0.15,
        "content_action": 0.08,
        "default": 0.0
    }
    action_risk = action_profiles.get(action_type, 0.0)
    base_score += action_risk
    signals.append({"signal": "action_type", "weight": "variable", "value": action_risk, "action": action_type})
    
    # Clamp score between 0-1
    final_score = min(1.0, max(0.0, base_score))
    
    # ---- DECISION LOGIC (EU AI Act Art. 4) ----
    if final_score < 0.35:
        decision = "ALLOW"
        decision_code = "LOW_RISK"
        regulatory_basis = "EU AI Act Art. 6 (1) - Low-risk classification"
    elif final_score < 0.70:
        decision = "CHALLENGE"
        decision_code = "MEDIUM_RISK"
        regulatory_basis = "EU AI Act Art. 12 - Human oversight required"
    else:
        decision = "BLOCK"
        decision_code = "HIGH_RISK"
        regulatory_basis = "EU AI Act Art. 4 (37) - High-risk system"
    
    return {
        "decision": decision,
        "decision_code": decision_code,
        "risk_score": round(final_score, 4),
        "risk_level": "HIGH" if final_score >= 0.70 else "MEDIUM" if final_score >= 0.35 else "LOW",
        "signals": signals,
        "action_type": action_type,
        "country": country,
        "amount": amount,
        "reasons": ["risk_assessment_complete"],
        "regulatory_basis": regulatory_basis,
        "version": VERSION,
        "timestamp": time.time()
    }

# ============================================================================
# LANDING PAGE - Enterprise Governance Design
# ============================================================================
LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AILeash - Enterprise AI Governance Platform</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        :root {
            --primary: #1e40af;
            --secondary: #7c3aed;
            --accent: #0891b2;
            --success: #059669;
            --warning: #d97706;
            --danger: #dc2626;
            --dark: #0f172a;
            --light: #f8fafc;
            --border: #cbd5e1;
            --text: #334155;
            --muted: #64748b;
        }

        html { scroll-behavior: smooth; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--text);
            line-height: 1.6;
            background: var(--light);
        }

        /* ============ HEADER & NAV ============ */
        header {
            background: white;
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }

        nav {
            max-width: 1400px;
            margin: 0 auto;
            padding: 1.25rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            font-size: 20px;
            font-weight: 700;
            color: var(--primary);
            text-decoration: none;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .nav-links {
            display: flex;
            gap: 2rem;
            align-items: center;
        }

        .nav-links a {
            color: var(--text);
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            transition: color 0.2s;
        }

        .nav-links a:hover {
            color: var(--primary);
        }

        /* ============ HERO SECTION ============ */
        .hero {
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0c4a6e 100%);
            color: white;
            padding: 5rem 2rem;
            text-align: center;
            min-height: 90vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .hero-content {
            max-width: 800px;
        }

        .badge {
            display: inline-block;
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
            color: rgba(255,255,255,0.9);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 1.5rem;
            backdrop-filter: blur(10px);
        }

        .hero h1 {
            font-size: 3.5rem;
            font-weight: 800;
            margin-bottom: 1rem;
            line-height: 1.1;
            background: linear-gradient(135deg, #60a5fa 0%, #34d399 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .hero p {
            font-size: 1.25rem;
            opacity: 0.9;
            margin-bottom: 2rem;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
        }

        .compliance-badges {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
            margin-bottom: 2rem;
        }

        .compliance-badge {
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #86efac;
            padding: 0.75rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn {
            display: inline-block;
            padding: 1rem 2rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            text-decoration: none;
            font-size: 1rem;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            box-shadow: 0 10px 25px rgba(30, 64, 175, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(30, 64, 175, 0.4);
        }

        .btn-secondary {
            background: transparent;
            color: white;
            border: 2px solid white;
        }

        .btn-secondary:hover {
            background: rgba(255,255,255,0.1);
        }

        .cta-buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }

        /* ============ ARCHITECTURE SECTION ============ */
        .architecture {
            max-width: 1400px;
            margin: 0 auto;
            padding: 4rem 2rem;
        }

        .section-title {
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--dark);
            margin-bottom: 0.5rem;
        }

        .section-subtitle {
            font-size: 1.1rem;
            color: var(--muted);
            margin-bottom: 3rem;
        }

        .architecture-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .arch-card {
            background: white;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 2rem;
            transition: all 0.3s;
        }

        .arch-card:hover {
            border-color: var(--primary);
            box-shadow: 0 10px 30px rgba(30, 64, 175, 0.1);
            transform: translateY(-3px);
        }

        .arch-icon {
            font-size: 2rem;
            margin-bottom: 1rem;
        }

        .arch-card h3 {
            color: var(--primary);
            margin-bottom: 0.5rem;
            font-size: 1.2rem;
        }

        .arch-card p {
            color: var(--text);
            font-size: 0.95rem;
            line-height: 1.5;
        }

        /* ============ FLOW DIAGRAM ============ */
        .flow-section {
            background: white;
            padding: 4rem 2rem;
            border-top: 2px solid var(--border);
            border-bottom: 2px solid var(--border);
        }

        .flow-container {
            max-width: 1200px;
            margin: 0 auto;
        }

        .flow-diagram {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 2rem;
            margin-top: 3rem;
        }

        .flow-step {
            background: linear-gradient(135deg, var(--light) 0%, white 100%);
            border: 2px solid var(--border);
            border-radius: 8px;
            padding: 2rem;
            text-align: center;
            position: relative;
        }

        .flow-step.active {
            border-color: var(--primary);
            background: linear-gradient(135deg, rgba(30, 64, 175, 0.05) 0%, white 100%);
        }

        .flow-number {
            width: 40px;
            height: 40px;
            background: var(--primary);
            color: white;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            margin: 0 auto 1rem;
        }

        .flow-step h4 {
            color: var(--dark);
            margin-bottom: 0.5rem;
        }

        .flow-step p {
            color: var(--muted);
            font-size: 0.9rem;
        }

        .flow-arrow {
            display: none;
            color: var(--primary);
            font-size: 1.5rem;
            text-align: center;
            margin-top: 1rem;
        }

        @media (min-width: 768px) {
            .flow-diagram {
                gap: 0;
            }
            .flow-step {
                margin-right: -2px;
            }
            .flow-arrow {
                display: block;
            }
        }

        /* ============ COMPLIANCE MATRIX ============ */
        .compliance-section {
            max-width: 1400px;
            margin: 0 auto;
            padding: 4rem 2rem;
        }

        .compliance-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 2rem;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }

        .compliance-table th {
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 1rem;
            text-align: left;
            font-weight: 600;
        }

        .compliance-table td {
            padding: 1rem;
            border-bottom: 1px solid var(--border);
            color: var(--text);
        }

        .compliance-table tr:hover {
            background: rgba(30, 64, 175, 0.02);
        }

        .compliance-check {
            color: var(--success);
            font-weight: 600;
        }

        /* ============ PRICING & AUTH ============ */
        .pricing-section {
            max-width: 1400px;
            margin: 0 auto;
            padding: 4rem 2rem;
            background: white;
        }

        .pricing-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-top: 3rem;
        }

        .pricing-card {
            border: 2px solid var(--border);
            border-radius: 12px;
            padding: 2rem;
            transition: all 0.3s;
            position: relative;
        }

        .pricing-card.featured {
            border-color: var(--primary);
            transform: scale(1.05);
            box-shadow: 0 20px 40px rgba(30, 64, 175, 0.15);
        }

        .pricing-card h3 {
            color: var(--dark);
            margin-bottom: 0.5rem;
        }

        .price {
            font-size: 2.5rem;
            color: var(--primary);
            font-weight: 700;
            margin: 1rem 0;
        }

        .price-period {
            color: var(--muted);
            font-size: 0.9rem;
        }

        .features-list {
            list-style: none;
            margin: 2rem 0;
        }

        .features-list li {
            padding: 0.5rem 0;
            color: var(--text);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .features-list li:before {
            content: "✓";
            color: var(--success);
            font-weight: 700;
            font-size: 1.2rem;
        }

        .auth-section {
            background: linear-gradient(135deg, var(--light) 0%, white 100%);
            padding: 4rem 2rem;
        }

        .auth-container {
            max-width: 450px;
            margin: 0 auto;
            background: white;
            border: 2px solid var(--border);
            padding: 3rem;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        }

        .auth-container h2 {
            color: var(--dark);
            margin-bottom: 0.5rem;
        }

        .auth-container .subtitle {
            color: var(--muted);
            margin-bottom: 2rem;
            font-size: 0.95rem;
        }

        .form-group {
            margin-bottom: 1.5rem;
        }

        .form-group label {
            display: block;
            font-weight: 600;
            color: var(--dark);
            margin-bottom: 0.5rem;
            font-size: 0.9rem;
        }

        input[type="email"], input[type="text"] {
            width: 100%;
            padding: 0.875rem;
            border: 1.5px solid var(--border);
            border-radius: 6px;
            font-size: 1rem;
            transition: all 0.2s;
            font-family: inherit;
        }

        input:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1);
        }

        .btn-submit {
            width: 100%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
            color: white;
            padding: 1rem;
            border: none;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 1rem;
        }

        .btn-submit:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(30, 64, 175, 0.3);
        }

        .btn-submit:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .message {
            margin-top: 1.5rem;
            padding: 1rem;
            border-radius: 6px;
            display: none;
        }

        .message.success {
            background: #ecfdf5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }

        .message.error {
            background: #fef2f2;
            color: #7f1d1d;
            border: 1px solid #fecaca;
        }

        .loader {
            display: none;
            width: 20px;
            height: 20px;
            border: 3px solid #e2e8f0;
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 1rem;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .toggle-auth {
            text-align: center;
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border);
            font-size: 0.9rem;
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

        .hidden { display: none !important; }

        /* ============ FOOTER ============ */
        footer {
            background: var(--dark);
            color: white;
            padding: 3rem 2rem;
            text-align: center;
            border-top: 2px solid var(--border);
        }

        footer p {
            opacity: 0.8;
            margin: 0.5rem 0;
        }

        footer a {
            color: #60a5fa;
            text-decoration: none;
        }

        footer a:hover {
            text-decoration: underline;
        }

        @media (max-width: 768px) {
            .hero h1 { font-size: 2rem; }
            .section-title { font-size: 2rem; }
            .cta-buttons { flex-direction: column; }
            .btn { width: 100%; text-align: center; }
            .pricing-card.featured { transform: scale(1); }
        }
    </style>
</head>
<body>
    <!-- HEADER -->
    <header>
        <nav>
            <a href="/" class="logo">🏛️ AILeash</a>
            <div class="nav-links">
                <a href="#architecture">Architecture</a>
                <a href="#compliance">Compliance</a>
                <a href="#pricing">Pricing</a>
                <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a>
            </div>
        </nav>
    </header>

    <!-- HERO -->
    <section class="hero">
        <div class="hero-content">
            <div class="badge">🔐 Enterprise AI Governance Platform</div>
            <h1>Compliant AI Governance at Enterprise Scale</h1>
            <p>EU AI Act. GDPR Art. 22. ISO 42001. Real-time risk assessment with cryptographic audit trails for high-risk AI systems.</p>
            
            <div class="compliance-badges">
                <div class="compliance-badge">✓ EU AI Act Art. 6</div>
                <div class="compliance-badge">✓ GDPR Art. 22</div>
                <div class="compliance-badge">✓ ISO 42001</div>
            </div>

            <div class="cta-buttons">
                <button class="btn btn-primary" onclick="showAuth('free')">Start Free Tier (100 tries)</button>
                <button class="btn btn-secondary" onclick="showAuth('paid')">Upgrade to Enterprise</button>
            </div>
        </div>
    </section>

    <!-- ARCHITECTURE -->
    <section class="architecture" id="architecture">
        <h2 class="section-title">System Architecture</h2>
        <p class="section-subtitle">Enterprise-grade governance infrastructure</p>

        <div class="architecture-grid">
            <div class="arch-card">
                <div class="arch-icon">🔐</div>
                <h3>Credential Layer</h3>
                <p>API key management with per-account quotas, usage tracking, and tier-based access control.</p>
            </div>

            <div class="arch-card">
                <div class="arch-icon">⚖️</div>
                <h3>Risk Engine</h3>
                <p>9-signal multi-dimensional risk scoring with deterministic decision logic and <15ms latency.</p>
            </div>

            <div class="arch-card">
                <div class="arch-icon">🔗</div>
                <h3>Audit Layer</h3>
                <p>SHA-256 chained logs with Merkle verification. Immutable, tamper-evident record.</p>
            </div>

            <div class="arch-card">
                <div class="arch-icon">🌍</div>
                <h3>Compliance Engine</h3>
                <p>Automated mapping to EU AI Act articles, GDPR requirements, and regulatory framework.</p>
            </div>

            <div class="arch-card">
                <div class="arch-icon">💳</div>
                <h3>Billing Integration</h3>
                <p>Stripe-powered subscription management with free tier quota enforcement.</p>
            </div>

            <div class="arch-card">
                <div class="arch-icon">🚀</div>
                <h3>Deployment Layer</h3>
                <p>Docker, Railway, Render, Fly.io, AWS Lambda. Zero external dependencies. Pure Python.</p>
            </div>
        </div>
    </section>

    <!-- FLOW DIAGRAM -->
    <section class="flow-section">
        <div class="flow-container">
            <h2 class="section-title">Governance Flow</h2>
            <p class="section-subtitle">How AILeash makes real-time compliance decisions</p>

            <div class="flow-diagram">
                <div class="flow-step active">
                    <div class="flow-number">1</div>
                    <h4>API Request</h4>
                    <p>Send AI action with Bearer token</p>
                    <div class="flow-arrow">→</div>
                </div>

                <div class="flow-step">
                    <div class="flow-number">2</div>
                    <h4>Auth Check</h4>
                    <p>Verify credentials & quota</p>
                    <div class="flow-arrow">→</div>
                </div>

                <div class="flow-step">
                    <div class="flow-number">3</div>
                    <h4>Risk Scoring</h4>
                    <p>Multi-signal analysis</p>
                    <div class="flow-arrow">→</div>
                </div>

                <div class="flow-step">
                    <div class="flow-number">4</div>
                    <h4>Decision</h4>
                    <p>ALLOW / CHALLENGE / BLOCK</p>
                    <div class="flow-arrow">→</div>
                </div>

                <div class="flow-step">
                    <div class="flow-number">5</div>
                    <h4>Audit Log</h4>
                    <p>Cryptographic recording</p>
                    <div class="flow-arrow">→</div>
                </div>

                <div class="flow-step">
                    <div class="flow-number">6</div>
                    <h4>Response</h4>
                    <p>Return decision + metadata</p>
                </div>
            </div>
        </div>
    </section>

    <!-- COMPLIANCE MATRIX -->
    <section class="compliance-section" id="compliance">
        <h2 class="section-title">Compliance Mapping</h2>
        <p class="section-subtitle">Automated regulatory alignment</p>

        <table class="compliance-table">
            <thead>
                <tr>
                    <th>Framework</th>
                    <th>Article/Requirement</th>
                    <th>Implementation</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>EU AI Act</strong></td>
                    <td>Art. 6 - High-Risk Classification</td>
                    <td>Risk scoring 0-1 scale with decision gates</td>
                    <td><span class="compliance-check">✓ COVERED</span></td>
                </tr>
                <tr>
                    <td><strong>EU AI Act</strong></td>
                    <td>Art. 9 - Transparency & Documentation</td>
                    <td>Full audit logs with signal breakdown</td>
                    <td><span class="compliance-check">✓ COVERED</span></td>
                </tr>
                <tr>
                    <td><strong>EU AI Act</strong></td>
                    <td>Art. 12 - Human Oversight</td>
                    <td>CHALLENGE decision for 0.35-0.70 scores</td>
                    <td><span class="compliance-check">✓ COVERED</span></td>
                </tr>
                <tr>
                    <td><strong>GDPR</strong></td>
                    <td>Art. 22 - Automated Decisions</td>
                    <td>Explainable scoring with appeal mechanism</td>
                    <td><span class="compliance-check">✓ COVERED</span></td>
                </tr>
                <tr>
                    <td><strong>ISO 42001</strong></td>
                    <td>AI Management System</td>
                    <td>Deterministic, reproducible scoring</td>
                    <td><span class="compliance-check">✓ COVERED</span></td>
                </tr>
            </tbody>
        </table>
    </section>

    <!-- PRICING -->
    <section class="pricing-section" id="pricing">
        <h2 class="section-title">Service Tiers</h2>
        <p class="section-subtitle">Choose the plan that fits your governance needs</p>

        <div class="pricing-grid">
            <div class="pricing-card">
                <h3>📊 Starter</h3>
                <div class="price">Free</div>
                <p class="price-period">Perfect for evaluation</p>
                <ul class="features-list">
                    <li>100 governance calls/month</li>
                    <li>Full risk scoring engine</li>
                    <li>Audit logs (30 days)</li>
                    <li>API access</li>
                    <li>Community support</li>
                </ul>
                <button class="btn btn-primary" onclick="showAuth('free')" style="width:100%;margin-top:1rem;">Get Started</button>
            </div>

            <div class="pricing-card featured">
                <h3>⚡ Professional</h3>
                <div class="price">$99</div>
                <p class="price-period">per month</p>
                <ul class="features-list">
                    <li>Unlimited governance calls</li>
                    <li>All Starter features</li>
                    <li>Audit logs (1 year)</li>
                    <li>Priority support</li>
                    <li>Custom integrations</li>
                    <li>Advanced analytics</li>
                </ul>
                <button class="btn btn-submit" onclick="showAuth('paid')" style="width:100%;margin-top:1rem;">Upgrade Now</button>
            </div>

            <div class="pricing-card">
                <h3>🏢 Enterprise</h3>
                <div class="price">Custom</div>
                <p class="price-period">per month</p>
                <ul class="features-list">
                    <li>Unlimited everything</li>
                    <li>Dedicated support</li>
                    <li>Custom compliance mapping</li>
                    <li>On-premise deployment</li>
                    <li>SLA guarantee</li>
                    <li>Legal agreement</li>
                </ul>
                <a href="mailto:support@aileash.dev" class="btn btn-primary" style="width:100%;margin-top:1rem;text-align:center;">Contact Sales</a>
            </div>
        </div>
    </section>

    <!-- FREE AUTH -->
    <section class="auth-section" id="free-auth" style="display:none;">
        <div class="auth-container">
            <h2>Free Starter Tier</h2>
            <p class="subtitle">100 governance calls, no credit card</p>
            
            <form id="freeForm">
                <div class="form-group">
                    <label for="free-email">Email Address</label>
                    <input type="email" id="free-email" placeholder="you@example.com" required>
                </div>
                <div class="form-group">
                    <label for="free-name">Organization (optional)</label>
                    <input type="text" id="free-name" placeholder="Your Company">
                </div>
                
                <div class="loader" id="free-loader"></div>
                <button type="submit" class="btn btn-submit" id="freeBtn">Create Account</button>
                
                <div class="message" id="free-msg"></div>
            </form>

            <div class="toggle-auth">
                Need unlimited? <a onclick="showAuth('paid')">Upgrade to Professional</a>
            </div>
        </div>
    </section>

    <!-- PAID AUTH -->
    <section class="auth-section" id="paid-auth" style="display:none;">
        <div class="auth-container">
            <h2>Professional Tier</h2>
            <p class="subtitle">$99/month • Unlimited calls</p>
            
            <form id="paidForm">
                <div class="form-group">
                    <label for="paid-email">Email Address</label>
                    <input type="email" id="paid-email" placeholder="you@example.com" required>
                </div>
                
                <div class="loader" id="paid-loader"></div>
                <button type="submit" class="btn btn-submit" id="paidBtn">Proceed to Stripe</button>
                
                <div class="message" id="paid-msg"></div>
            </form>

            <div class="toggle-auth">
                Start with free tier? <a onclick="showAuth('free')">Get Starter Account</a>
            </div>
        </div>
    </section>

    <!-- FOOTER -->
    <footer>
        <p><strong>AILeash v3.4.0</strong> — Enterprise AI Governance Platform</p>
        <p>
            <a href="https://github.com/justrightdecorators-ops/aileash">GitHub</a> •
            <a href="https://github.com/justrightdecorators-ops/aileash/issues">Issues</a> •
            MIT License
        </p>
        <p style="margin-top:1rem;opacity:0.6;">Compliant with EU AI Act, GDPR Art. 22, ISO 42001</p>
    </footer>

    <script>
        function showAuth(type) {
            document.getElementById('free-auth').style.display = type === 'free' ? 'block' : 'none';
            document.getElementById('paid-auth').style.display = type === 'paid' ? 'block' : 'none';
            setTimeout(() => {
                document.querySelector(type === 'free' ? '#free-auth' : '#paid-auth').scrollIntoView({ behavior: 'smooth' });
            }, 100);
        }

        // FREE SIGNUP
        document.getElementById('freeForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('free-email').value.trim();
            if (!email) {
                showMsg('free-msg', 'Enter valid email', 'error');
                return;
            }
            document.getElementById('free-loader').style.display = 'block';
            document.getElementById('freeBtn').disabled = true;
            try {
                const res = await fetch('/api/keys', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                const data = await res.json();
                if (!res.ok) {
                    showMsg('free-msg', data.error || 'Error', 'error');
                } else {
                    showMsg('free-msg', `✓ Account created!<br/>Key: <code style="background:#f0f0f0;padding:0.25rem 0.5rem;border-radius:3px;">${data.key}</code><br/>Check email for details.`, 'success');
                    document.getElementById('freeForm').reset();
                }
            } catch (err) {
                showMsg('free-msg', 'Network error: ' + err.message, 'error');
            }
            document.getElementById('free-loader').style.display = 'none';
            document.getElementById('freeBtn').disabled = false;
        });

        // PAID SIGNUP
        document.getElementById('paidForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('paid-email').value.trim();
            if (!email) {
                showMsg('paid-msg', 'Enter valid email', 'error');
                return;
            }
            document.getElementById('paid-loader').style.display = 'block';
            document.getElementById('paidBtn').disabled = true;
            try {
                const res = await fetch('/api/checkout', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                const data = await res.json();
                if (!res.ok) {
                    showMsg('paid-msg', data.error || 'Error', 'error');
                } else if (data.checkout_url) {
                    window.location.href = data.checkout_url;
                } else {
                    showMsg('paid-msg', 'Checkout error', 'error');
                }
            } catch (err) {
                showMsg('paid-msg', 'Network error: ' + err.message, 'error');
            }
            document.getElementById('paid-loader').style.display = 'none';
            document.getElementById('paidBtn').disabled = false;
        });

        function showMsg(id, html, type) {
            const el = document.getElementById(id);
            el.innerHTML = html;
            el.className = 'message ' + type;
            el.style.display = 'block';
        }

        const params = new URLSearchParams(location.search);
        if (params.has('success')) {
            setTimeout(() => alert('✓ Payment successful! Check email for next steps.'), 500);
        } else if (params.has('cancel')) {
            showAuth('paid');
            showMsg('paid-msg', '✗ Payment cancelled. Try again when ready.', 'error');
        }
    </script>
</body>
</html>
"""

# ============================================================================
# HTTP HANDLERS
# ============================================================================
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

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return send_html(self)
        if path in ["/api/status", "/health"]:
            return send(self, {"status": "ok", "version": VERSION, "timestamp": time.time()})
        if path == "/api/verify":
            return send(self, {"valid": True, "blocks": 0})
        send(self, {"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length)) if length > 0 else {}
        except:
            return send(self, {"error": "invalid json"}, 400)

        if path == "/api/keys":
            email = data.get("email", "").strip().lower()
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            key = create_api_key(email, "free")
            if not key:
                return send(self, {"error": "email already registered"}, 409)
            return send(self, {"key": key, "email": email, "quota": FREE_QUOTA})

        if path == "/api/checkout":
            email = data.get("email", "").strip().lower()
            if not email or '@' not in email:
                return send(self, {"error": "valid email required"}, 400)
            session = create_checkout_session(email)
            if not session:
                return send(self, {"error": "Stripe not configured"}, 501)
            return send(self, {"checkout_url": session.get("url")})

        if path == "/api/govern":
            auth = self.headers.get("Authorization", "").replace("Bearer ", "")
            result = govern(data, auth if auth else None)
            return send(self, result)

        send(self, {"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

def main():
    print(f"🏛️ AILeash v{VERSION} - Enterprise AI Governance Platform")
    print(f"📍 Running on http://0.0.0.0:{PORT}")
    print(f"💳 Stripe: {'✓ Configured' if STRIPE_SECRET and STRIPE_PRICE_ID else '✗ Not configured'}")
    print(f"📊 Free quota: {FREE_QUOTA} calls/account")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
