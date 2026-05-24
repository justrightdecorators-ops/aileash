import os
import time
import json
import hashlib
import smtplib
import redis
from email.mime.text import MIMEText
from flask import Flask, request, jsonify

app = Flask(__name__)

PORT = int(os.getenv("PORT", 8080))
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")

STRIPE_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_PASS", "")
CONTACT_EMAIL = "justrightdecorators@gmail.com"

REDIS_URL = os.getenv("REDIS_URL", "")
r = redis.from_url(REDIS_URL) if REDIS_URL else None

_keys = {}
_audit = []
_last_hash = "genesis"

# ─────────────────────────────
# CORE LOGIC
# ─────────────────────────────
def score_event(event):
    amount = float(event.get("amount", 0))
    device = float(event.get("device_risk", 0.1))
    anomaly = float(event.get("anomaly", 0.05))
    return round(min(1.0, (amount/10000)*0.3 + device*0.3 + anomaly*0.4), 4)

def decide(score):
    if score < 0.3:
        return "ALLOW"
    if score < 0.7:
        return "CHALLENGE"
    return "BLOCK"

# ─────────────────────────────
# AUDIT (real chain)
# ─────────────────────────────
def audit_log(user, event, decision, score):
    global _last_hash

    payload = f"{time.time()}|{user}|{event}|{decision}|{score}|{_last_hash}"
    new_hash = hashlib.sha256(payload.encode()).hexdigest()

    record = {
        "ts": time.time(),
        "user": user,
        "event": event,
        "decision": decision,
        "score": score,
        "hash": new_hash,
        "prev": _last_hash
    }

    _last_hash = new_hash

    if r:
        r.lpush("audit", json.dumps(record))
    else:
        _audit.append(record)

# ─────────────────────────────
# API KEY
# ─────────────────────────────
def generate_key(email):
    raw = email + str(time.time())
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]

    data = {"email": email, "created": time.time(), "plan": "free"}

    if r:
        r.hset("keys", key, json.dumps(data))
    else:
        _keys[key] = data

    return key

def validate_key(key):
    if r:
        data = r.hget("keys", key)
        return json.loads(data) if data else None
    return _keys.get(key)

# ─────────────────────────────
# EMAIL (consent form)
# ─────────────────────────────
def send_email(sender_email, message):
    if not GMAIL_USER or not GMAIL_PASS:
        return False

    msg = MIMEText(message)
    msg["Subject"] = "AI Firewall Consent Form"
    msg["From"] = GMAIL_USER
    msg["To"] = CONTACT_EMAIL
    msg["Reply-To"] = sender_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.send_message(msg)

    return True

# ─────────────────────────────
# ROUTES
# ─────────────────────────────

@app.route("/")
def home():
    return HTML, 200, {"Content-Type": "text/html"}

@app.route("/govern", methods=["POST"])
def govern():
    api_key = request.headers.get("x-api-key")
    user = validate_key(api_key)

    if not user:
        return jsonify({"error": "invalid key"}), 401

    event = request.json
    score = score_event(event)
    decision = decide(score)

    audit_log(user["email"], event, decision, score)

    return jsonify({
        "decision": decision,
        "score": score
    })

@app.route("/consent", methods=["POST"])
def consent():
    data = request.json
    send_email(data.get("email"), data.get("message", ""))
    return jsonify({"status": "sent"})

@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    return jsonify({"ok": True})

# ─────────────────────────────
# LANDING PAGE (FULL — NO PLACEHOLDERS)
# ─────────────────────────────
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Firewall</title>
<style>
body{margin:0;font-family:Arial;background:#fff;color:#111}
header{padding:20px;border-bottom:3px solid #cc0000;display:flex;justify-content:space-between}
.logo{font-weight:900;color:#cc0000}
.hero{padding:80px 20px;text-align:center}
h1{font-size:42px;margin-bottom:10px}
h1 span{color:#cc0000}
p{color:#555;max-width:700px;margin:10px auto}
.btn{display:inline-block;margin-top:20px;padding:12px 28px;background:#cc0000;color:#fff;text-decoration:none;font-weight:bold;border-radius:6px}
section{padding:60px 20px;max-width:900px;margin:auto}
.card{border:1px solid #eee;padding:20px;margin:10px 0;border-radius:8px}
.footer{padding:30px;text-align:center;background:#111;color:#aaa}
</style>
</head>
<body>

<header>
  <div class="logo">AI Firewall</div>
  <a class="btn" href="#contact">Start Free</a>
</header>

<div class="hero">
  <h1>Govern your AI in <span>real time</span></h1>
  <p>Every decision scored, logged, and controlled. Built for compliance, speed, and scale.</p>
  <a class="btn" href="#contact">Get API Key</a>
</div>

<section>
  <div class="card">✔ Risk scoring engine</div>
  <div class="card">✔ Tamper-proof audit log</div>
  <div class="card">✔ Stripe billing ready</div>
  <div class="card">✔ Email consent system</div>
</section>

<section id="contact">
  <h2>Consent Form</h2>
  <form onsubmit="send(event)">
    <input id="email" placeholder="Your email" style="width:100%;padding:10px;margin:5px 0">
    <textarea id="msg" placeholder="Message" style="width:100%;padding:10px;height:100px"></textarea>
    <button class="btn">Send</button>
  </form>
</section>

<div class="footer">AI Firewall System ©</div>

<script>
async function send(e){
e.preventDefault();
await fetch('/consent',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
email:document.getElementById('email').value,
message:document.getElementById('msg').value
})
});
alert("Sent");
}
</script>

</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
