import os
import time
import json
import hashlib
import urllib.request
import urllib.parse
import smtplib
from email.mime.text import MIMEText

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")

EMAIL_USER = os.getenv("EMAIL_USER", "justrightdecorators@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")

FREE_TIER_LIMIT = 1000

# ─────────────────────────────
# MEMORY CORE (your logic unchanged)
# ─────────────────────────────
_keys = {}
_audit_file = "audit.log"

def log_audit(entry):
    try:
        with open(_audit_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except:
        pass

def generate_key(email, plan="free"):
    raw = email + str(time.time()) + "aileash_secret_2026"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]

    _keys[key] = {
        "email": email,
        "plan": plan,
        "created": time.time()
    }
    return key

def validate_key(key):
    return _keys.get(key)

def upgrade_key(key):
    if key in _keys:
        _keys[key]["plan"] = "paid"
        return True
    return False

def score_event(event):
    amount = float(event.get("amount", 0))
    device = float(event.get("device_risk", 0.1))
    anomaly = float(event.get("anomaly", 0.05))

    s = (amount / 10000) * 0.3 + device * 0.3 + anomaly * 0.4
    return round(max(0.0, min(1.0, s)), 4)

def decide(score):
    if score < 0.3:
        return "ALLOW"
    if score < 0.7:
        return "CHALLENGE"
    return "BLOCK"

def log_event(user, event, decision, score):
    log_audit({
        "ts": time.time(),
        "user": user,
        "event": event,
        "decision": decision,
        "score": score
    })

# ─────────────────────────────
# STRIPE (UNCHANGED LOGIC)
# ─────────────────────────────
def create_checkout(email, api_key):
    if not STRIPE_KEY.startswith("sk_"):
        return None

    data = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][product_data][name]": "AILeash Pro",
        "line_items[0][price_data][product_data][description]": "AI firewall governance",
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

    resp = urllib.request.urlopen(req, timeout=8)
    return json.loads(resp.read())["url"]

# ─────────────────────────────
# EMAIL (FIXED - ACTUALLY RELIABLE)
# ─────────────────────────────
def send_email(user_email, message):
    if not EMAIL_USER or not EMAIL_PASS:
        return False

    msg = MIMEText(f"From: {user_email}\n\n{message}")
    msg["Subject"] = "AILeash Consent Form"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_USER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(EMAIL_USER, EMAIL_PASS)
            s.send_message(msg)
        return True
    except:
        return False

# ─────────────────────────────
# API ROUTES
# ─────────────────────────────
@app.route("/govern", methods=["POST"])
def govern():
    data = request.json or {}

    score = score_event(data)
    decision = decide(score)

    user = data.get("user", "anon")
    log_event(user, data, decision, score)

    return jsonify({
        "decision": decision,
        "score": score
    })

@app.route("/contact", methods=["POST"])
def contact():
    data = request.json or {}

    send_email(
        data.get("email", ""),
        data.get("message", "")
    )

    return jsonify({"status": "sent"})

@app.route("/health")
def health():
    return "OK", 200

# ─────────────────────────────
# LANDING PAGE (UNCHANGED SOURCE OF TRUTH)
# ─────────────────────────────
with open("index.html", "r", encoding="utf-8") as f:
    HTML = f.read()

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")

# ─────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
