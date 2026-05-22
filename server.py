import os
import time
import json
import hashlib
import sqlite3
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify, redirect

# ─────────────────────────────────────────────
# CONFIG (was config.py)
# ─────────────────────────────────────────────

PORT = int(os.getenv("PORT", 8080))
VERSION = "2.0"
PRODUCT = "AILeash"
FREE_TIER_LIMIT = 1000

STRIPE_SECRET = os.getenv("STRIPE_SECRET", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")

# ─────────────────────────────────────────────
# AUTH (was auth.py)
# ─────────────────────────────────────────────

_keys = {}

def generate_key(email, plan="free"):
    raw = email + str(time.time()) + "aileash_secret_2026"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    _keys[key] = {"email": email, "plan": plan, "created": time.time()}
    return key

def validate_key(key):
    return _keys.get(key)

def upgrade_key(key):
    if key in _keys:
        _keys[key]["plan"] = "paid"
        return True
    return False

# ─────────────────────────────────────────────
# ENGINE (was engine.py)
# ─────────────────────────────────────────────

COUNTRY_RISK = {
    "UK": 0.05, "US": 0.05, "DE": 0.05, "FR": 0.05,
    "CA": 0.05, "AU": 0.05, "JP": 0.10, "BR": 0.25,
    "IN": 0.20, "CN": 0.40, "RU": 0.70, "KP": 0.90,
    "IR": 0.80, "NG": 0.50,
}

DEFAULT_COUNTRY_RISK = 0.35

def score(event, trust=0.5):
    s = 0.0
    s += (1.0 - trust) * 0.25
    s += min(float(event.get("amount", 0)) / 10000.0, 1.0) * 0.25
    s += float(event.get("device_risk", 0.0)) * 0.20
    s += float(event.get("anomaly", 0.0)) * 0.20
    s += COUNTRY_RISK.get(event.get("country", "US"), DEFAULT_COUNTRY_RISK) * 0.10
    return round(max(0.0, min(1.0, s)), 4)

def decide(score):
    if score < 0.30:
        return "ALLOW"
    if score < 0.70:
        return "CHALLENGE"
    return "BLOCK"

# ─────────────────────────────────────────────
# MEMORY (was memory.py)
# ─────────────────────────────────────────────

DB = "aileash.db"

def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            user TEXT,
            event TEXT,
            decision TEXT,
            score REAL
        )
    """)
    conn.commit()
    return conn

_db = get_db()

def log(user, event, decision, score):
    _db.execute(
        "INSERT INTO audit(ts, user, event, decision, score) VALUES(?,?,?,?,?)",
        (time.time(), user, json.dumps(event), decision, score)
    )
    _db.commit()

def recent(limit=50):
    rows = _db.execute(
        "SELECT * FROM audit ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]

def count_for_user(user):
    row = _db.execute(
        "SELECT COUNT(*) FROM audit WHERE user=?",
        (user,)
    ).fetchone()
    return row[0]

# ─────────────────────────────────────────────
# BILLING (was billing.py)
# ─────────────────────────────────────────────

def create_checkout(email, api_key):
    if not STRIPE_SECRET or not STRIPE_SECRET.startswith("sk_"):
        return None

    params = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": "AILeash Pro",
        "line_items[0][price_data][product_data][description]": "AI Action Firewall",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][unit_amount]": "9900",
        "line_items[0][quantity]": "1",
        "customer_email": email,
        "metadata[api_key]": api_key,
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=params,
        headers={
            "Authorization": "Bearer " + STRIPE_SECRET,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    resp = urllib.request.urlopen(req, timeout=10)
    session = json.loads(resp.read())
    return session["url"]

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = Flask(__name__)

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>AILeash</title>
</head>
<body style="background:#000;color:#0f0;font-family:monospace">
<h1>AILeash Running</h1>
<p>System is live.</p>
</body>
</html>
"""

@app.route("/")
def index():
    return INDEX_HTML

@app.route("/health")
def health():
    return jsonify({"status": "ok", "product": PRODUCT, "version": VERSION})

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"error": "invalid_email"}), 400

    key = generate_key(email)

    return jsonify({
        "api_key": key,
        "plan": "free",
        "limit": FREE_TIER_LIMIT
    })

@app.route("/govern", methods=["POST"])
def govern():
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        return jsonify({"error": "missing_key"}), 401

    user = validate_key(api_key)
    if not user:
        return jsonify({"error": "invalid_key"}), 401

    plan = user.get("plan", "free")
    usage = count_for_user(api_key)

    if plan == "free" and usage >= FREE_TIER_LIMIT:
        return jsonify({
            "error": "limit_reached",
            "upgrade_url": "/checkout?key=" + api_key
        }), 402

    event = request.get_json(silent=True) or {}

    s = score(event)
    d = decide(s)

    log(api_key, event, d, s)

    return jsonify({
        "decision": d,
        "score": s,
        "usage": usage + 1,
        "plan": plan
    })

@app.route("/checkout")
def checkout():
    api_key = request.args.get("key", "")
    email = request.args.get("email", "")

    user = validate_key(api_key) if api_key else None
    if user:
        email = user.get("email", email)

    if not email:
        return jsonify({"error": "missing_email"}), 400

    if not api_key:
        api_key = generate_key(email)

    url = create_checkout(email, api_key)
    if not url:
        return jsonify({"error": "billing_not_configured"}), 500

    return redirect(url)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        event = json.loads(request.data)
        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            api_key = session.get("metadata", {}).get("api_key")
            if api_key:
                upgrade_key(api_key)
        return jsonify({"received": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/audit")
def audit():
    api_key = request.headers.get("x-api-key", "")
    if not validate_key(api_key):
        return jsonify({"error": "invalid_key"}), 401
    return jsonify(recent(50))

# ─────────────────────────────────────────────

if __name__ == "__main__":
    print(f"{PRODUCT} v{VERSION} running on {PORT}")
    app.run(host="0.0.0.0", port=PORT)
