import os
import time
import json
import hashlib
import smtplib
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify, Response

app = Flask(__name__)

# ---------------- ENV ----------------
PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")

CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "justrightdecorators@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# ---------------- STORAGE ----------------
_keys = {}
_audit = []

# ---------------- AUDIT HASH CHAIN ----------------
def hash_event(prev_hash, event):
    raw = json.dumps(event, sort_keys=True) + prev_hash
    return hashlib.sha256(raw.encode()).hexdigest()


def log_event(user, event, decision, score):
    prev_hash = _audit[-1]["hash"] if _audit else "genesis"

    entry = {
        "ts": time.time(),
        "user": user,
        "event": event,
        "decision": decision,
        "score": score,
    }

    entry["hash"] = hash_event(prev_hash, entry)
    _audit.append(entry)


# ---------------- CORE LOGIC ----------------
def score_event(event):
    amount = float(event.get("amount", 0))
    device = float(event.get("device_risk", 0.1))
    anomaly = float(event.get("anomaly", 0.05))

    score = (amount / 10000) * 0.3 + device * 0.3 + anomaly * 0.4
    return round(max(0.0, min(1.0, score)), 4)


def decide(score):
    if score < 0.3:
        return "ALLOW"
    if score < 0.7:
        return "CHALLENGE"
    return "BLOCK"


# ---------------- EMAIL ----------------
def send_email(sender_email, message):
    if not GMAIL_APP_PASSWORD:
        return False

    try:
        smtp = smtplib.SMTP("smtp.gmail.com", 587)
        smtp.starttls()
        smtp.login(CONTACT_EMAIL, GMAIL_APP_PASSWORD)

        body = f"From: {sender_email}\n\n{message}"

        smtp.sendmail(CONTACT_EMAIL, CONTACT_EMAIL, body)
        smtp.quit()
        return True
    except Exception as e:
        print("EMAIL_ERROR:", e)
        return False


# ---------------- STRIPE ----------------
def create_checkout(email, api_key):
    if not STRIPE_KEY:
        return None

    payload = urllib.parse.urlencode({
        "mode": "subscription",
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][product_data][name]": "AI Firewall Pro",
        "line_items[0][price_data][unit_amount]": "4900",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1"
    }).encode()

    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=payload,
        headers={
            "Authorization": "Bearer " + STRIPE_KEY,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )

    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read())["url"]


# ---------------- ROUTES ----------------
@app.route("/govern", methods=["POST"])
def govern():
    data = request.json or {}

    score = score_event(data)
    decision = decide(score)

    log_event("api_user", data, decision, score)

    return jsonify({
        "decision": decision,
        "score": score
    })


@app.route("/audit", methods=["GET"])
def audit():
    return jsonify(_audit[-1000:])


@app.route("/contact", methods=["POST"])
def contact():
    data = request.json or {}

    ok = send_email(
        data.get("email", ""),
        data.get("message", "")
    )

    return jsonify({"sent": ok})


@app.route("/")
def home():
    return Response(HTML, mimetype="text/html")


# ---------------- LANDING PAGE (UNCHANGED PLACEHOLDER) ----------------
HTML = """<!DOCTYPE html>
<html>
<head>
<title>AI Firewall</title>
<style>
body{font-family:Arial;background:#fff;color:#111}
nav{border-bottom:3px solid #cc0000;padding:20px}
</style>
</head>
<body>

<nav>AI Firewall</nav>

<h1>AI Firewall System</h1>
<p>Govern AI decisions in real time.</p>

</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
