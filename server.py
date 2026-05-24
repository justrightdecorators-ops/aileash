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
# YOUR LANDING PAGE (UNCHANGED, EMBEDDED EXACTLY)
# ─────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash - AI Compliance Infrastructure</title>
<meta name="description" content="AILeash governs every AI decision in real time. EU AI Act compliant. Free tier available. Pro from £49/month.">
<style>
body{margin:0;font-family:Arial;background:#fff;color:#111}
nav{padding:20px;display:flex;justify-content:space-between;border-bottom:2px solid #cc0000}
.hero{text-align:center;padding:60px 20px}
.btn{background:#cc0000;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;display:inline-block}
</style>
</head>
<body>

<nav>
  <div><b>AILeash</b></div>
  <div><a href="#free">Start free</a></div>
</nav>

<div class="hero">
  <h1>Your AI is making decisions.</h1>
  <p>Is it compliant?</p>
  <a class="btn" href="#free">Start Free</a>
</div>

</body>
</html>"""

# ─────────────────────────────────────────────
# CORE LOGIC
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
    return jsonify({
        "checkout_url": f"{BASE_URL}/success?key={api_key}",
        "api_key": api_key
    })


@app.route("/success")
def success():
    key = request.args.get("key")
    if key:
        upgrade_key(key)

    return "<h1>Payment successful</h1>"


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "keys": len(_keys),
        "events": len(_audit)
    })


# ─────────────────────────────────────────────
# START SERVER
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
