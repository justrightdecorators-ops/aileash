import os
import time
import json
import hashlib
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify

app = Flask(__name__)

PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

FREE_TIER_LIMIT = 1000

_keys = {}
_audit = []

# ─────────────────────────────────────────────
# DO NOT TOUCH YOUR LANDING PAGE HTML
# paste your existing HTML EXACTLY below this line
# ─────────────────────────────────────────────

HTML = """PASTE YOUR EXISTING HTML HERE EXACTLY AS YOU HAVE IT"""

# ─────────────────────────────────────────────

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


def log_event(user, event, decision, score):
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

    score = (amount / 10000) * 0.3 + device * 0.3 + anomaly * 0.4
    return round(max(0.0, min(1.0, score)), 4)


def decide(score):
    if score < 0.3:
        return "ALLOW"
    elif score < 0.7:
        return "CHALLENGE"
    return "BLOCK"


def create_checkout(email, api_key):
    if not STRIPE_KEY:
        return None

    data = urllib.parse.urlencode({
        "success_url": f"{BASE_URL}/success?key={api_key}",
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][product_data][name]": "AILeash Pro",
        "line_items[0][price_data][product_data][description]": "AI governance layer",
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

    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode())["url"]
    except Exception as e:
        print("Stripe error:", e)
        return None


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/")
def home():
    return HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/generate-key", methods=["POST"])
def generate():
    data = request.json or {}
    email = data.get("email")

    if not email:
        return jsonify({"error": "email required"}), 400

    key = generate_key(email)
    return jsonify({"api_key": key})


@app.route("/govern", methods=["POST"])
def govern():
    api_key = request.headers.get("x-api-key")
    user = validate_key(api_key)

    if not user:
        return jsonify({"error": "invalid api key"}), 403

    data = request.json or {}

    score = score_event(data)
    decision = decide(score)

    log_event(user["email"], data, decision, score)

    return jsonify({
        "decision": decision,
        "score": score,
        "usage": count_for_user(user["email"]),
        "plan": user["plan"]
    })


@app.route("/checkout", methods=["POST"])
def checkout():
    data = request.json or {}
    email = data.get("email")

    if not email:
        return jsonify({"error": "email required"}), 400

    api_key = generate_key(email)
    url = create_checkout(email, api_key)

    if not url:
        return jsonify({"error": "stripe not configured"}), 500

    return jsonify({
        "checkout_url": url,
        "api_key": api_key
    })


@app.route("/success")
def success():
    key = request.args.get("key")
    if key:
        upgrade_key(key)

    return "Payment successful. You can return to the app."


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "keys": len(_keys),
        "events": len(_audit)
    })


# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
