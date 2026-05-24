import os
import time
import json
import hashlib
import threading
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify

app = Flask(__name__)

# ─────────────────────────────
# CONFIG
# ─────────────────────────────
PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")
FREE_TIER_LIMIT = 1000

# ─────────────────────────────
# IN-MEMORY STORAGE (FAST)
# ─────────────────────────────
_keys = {}
_audit = []
_lock = threading.Lock()

# ─────────────────────────────
# CORE LOGIC (YOUR ENGINE)
# ─────────────────────────────
def generate_key(email, plan="free"):
    raw = f"{email}:{time.time()}:aileash_core"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]

    with _lock:
        _keys[key] = {
            "email": email,
            "plan": plan,
            "created": time.time(),
            "usage": 0
        }

    return key


def validate_key(key):
    return _keys.get(key)


def log_event(user, event, decision, score):
    with _lock:
        _audit.append({
            "ts": time.time(),
            "user": user,
            "event": event,
            "decision": decision,
            "score": score
        })


def count_for_user(user):
    return sum(1 for x in _audit if x["user"] == user)


def score_event(event):
    amount = float(event.get("amount", 0))
    device = float(event.get("device_risk", 0.1))
    anomaly = float(event.get("anomaly", 0.05))

    # lightweight scoring (fast execution)
    return round(min(1.0, max(0.0,
        (amount / 10000) * 0.3 +
        device * 0.3 +
        anomaly * 0.4
    )), 4)


def decide(score):
    if score < 0.3:
        return "ALLOW"
    elif score < 0.7:
        return "CHALLENGE"
    return "BLOCK"


# ─────────────────────────────
# API CORE ENDPOINT (FAST PATH)
# ─────────────────────────────
@app.route("/govern", methods=["POST"])
def govern():
    data = request.json or {}
    api_key = request.headers.get("x-api-key")

    user = validate_key(api_key)
    if not user:
        return jsonify({"error": "invalid key"}), 403

    # usage limit check
    if user["plan"] == "free" and user.get("usage", 0) >= FREE_TIER_LIMIT:
        return jsonify({"error": "limit reached"}), 429

    score = score_event(data)
    decision = decide(score)

    log_event(api_key, data, decision, score)

    user["usage"] = user.get("usage", 0) + 1

    return jsonify({
        "decision": decision,
        "score": score,
        "usage": user["usage"],
        "plan": user["plan"]
    })


# ─────────────────────────────
# KEY CREATION (CONSENT FORM TARGET)
# ─────────────────────────────
@app.route("/create-key", methods=["POST"])
def create_key():
    data = request.json or {}
    email = data.get("email")

    if not email:
        return jsonify({"error": "email required"}), 400

    key = generate_key(email)

    return jsonify({
        "api_key": key,
        "email": email
    })


# ─────────────────────────────
# STRIPE (UNCHANGED LOGIC)
# ─────────────────────────────
def create_checkout(email, api_key):
    if not STRIPE_KEY:
        return None

    data = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][product_data][name]": "AI Firewall Pro",
        "line_items[0][price_data][unit_amount]": "4900",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1",
        "metadata[api_key]": api_key,
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=data,
        headers={
            "Authorization": "Bearer " + STRIPE_KEY,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["url"]


# ─────────────────────────────
# HTML (NO FILE DEPENDENCY FIX)
# ─────────────────────────────
HTML = """<!DOCTYPE html>
<html>
<head>
<title>AI Firewall</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:Arial;background:#fff;color:#111;padding:40px;text-align:center}
h1{color:#cc0000}
</style>
</head>
<body>
<h1>AI Firewall Active</h1>
<p>System running.</p>
</body>
</html>
"""


@app.route("/")
def home():
    return HTML


@app.route("/health")
def health():
    return {"status": "ok", "time": time.time()}


# ─────────────────────────────
# RUN (RAILWAY READY)
# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
