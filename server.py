import os
import time
import json
import hashlib
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------
# CONFIG
# -------------------------
PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

# -------------------------
# MEMORY STORE (SIMPLE)
# -------------------------
_keys = {}
_audit = []

# -------------------------
# CORE AI FIREWALL LOGIC
# -------------------------
def generate_key(email):
    raw = email + str(time.time())
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    _keys[key] = {"email": email, "plan": "free", "ts": time.time()}
    return key


def validate_key(key):
    return _keys.get(key)


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


def log_event(key, event, decision, score):
    _audit.append({
        "ts": time.time(),
        "key": key,
        "event": event,
        "decision": decision,
        "score": score
    })


# -------------------------
# API
# -------------------------
@app.route("/govern", methods=["POST"])
def govern():
    key = request.headers.get("x-api-key")
    user = validate_key(key)

    if not user:
        return jsonify({"error": "invalid key"}), 403

    data = request.json or {}
    score = score_event(data)
    decision = decide(score)

    log_event(key, data, decision, score)

    return jsonify({
        "decision": decision,
        "score": score,
        "usage": len(_audit)
    })


@app.route("/audit")
def audit():
    return jsonify(_audit)


@app.route("/contact", methods=["POST"])
def contact():
    data = request.json or {}
    print("CONTACT:", data)
    return jsonify({"status": "received"})


# -------------------------
# FULL LANDING PAGE (COMPLETE)
# -------------------------
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Firewall</title>
<style>
body{margin:0;font-family:Arial;background:#fff;color:#111}
header{padding:20px;border-bottom:3px solid red;display:flex;justify-content:space-between}
.hero{text-align:center;padding:80px}
.hero h1{font-size:44px}
.red{color:red}
.btn{padding:12px 20px;background:red;color:#fff;border:none;cursor:pointer}
section{max-width:900px;margin:auto;padding:40px}
.card{border:1px solid #ddd;padding:15px;margin:10px 0}
footer{background:#111;color:#aaa;text-align:center;padding:30px}
</style>
</head>

<body>

<header>
<b>AI <span class="red">Firewall</span></b>
<div>Home | API | Contact</div>
</header>

<div class="hero">
<h1>AI decisions <span class="red">controlled in real time</span></h1>
<p>Fast AI governance layer for modern systems</p>
<button class="btn">Start Free</button>
</div>

<section>
<h2>What it does</h2>
<div class="card">Scores every AI decision instantly</div>
<div class="card">Blocks high-risk actions in real time</div>
<div class="card">Creates immutable audit trail</div>
</section>

<section>
<h2>Contact</h2>
<form onsubmit="send(event)">
<input id="name" placeholder="Name"><br><br>
<input id="email" placeholder="Email"><br><br>
<textarea id="msg" placeholder="Message"></textarea><br><br>
<button class="btn">Send</button>
</form>
</section>

<footer>
AI Firewall System © 2026
</footer>

<script>
function send(e){
e.preventDefault();
fetch('/contact',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
name:document.getElementById('name').value,
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


@app.route("/")
def home():
    return HTML


# -------------------------
# START
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
