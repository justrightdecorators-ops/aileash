import os
import time
import json
import hashlib
import threading
import queue
from flask import Flask, request, jsonify

app = Flask(__name__)

PORT = int(os.getenv("PORT", 8080))

# ─────────────────────────────────────────────
# CORE BRAIN (YOUR LOGIC - UNCHANGED)
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# FAST STATE (IN MEMORY)
# ─────────────────────────────────────────────

_keys = {}
event_queue = queue.Queue()

def generate_key(email, plan="free"):
    raw = email + str(time.time()) + "ai_firewall_core"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]

    _keys[key] = {
        "email": email,
        "plan": plan,
        "created": time.time()
    }

    return key


def validate_key(key):
    return _keys.get(key)


# ─────────────────────────────────────────────
# BACKGROUND WORKER (ACTIONS OFF MAIN THREAD)
# ─────────────────────────────────────────────

def worker():
    with open("audit.log", "a") as f:
        while True:
            item = event_queue.get()
            try:
                f.write(json.dumps(item) + "\n")
                f.flush()
            except:
                pass


threading.Thread(target=worker, daemon=True).start()


# ─────────────────────────────────────────────
# ULTRA FAST API PATH
# ─────────────────────────────────────────────

@app.route("/govern", methods=["POST"])
def govern():
    start = time.time()

    event = request.json or {}
    key = request.headers.get("x-api-key", "")

    user = validate_key(key)
    if not user:
        return jsonify({"error": "invalid key"}), 403

    # YOUR CORE BRAIN
    score = score_event(event)
    decision = decide(score)

    # FIRE AND FORGET AUDIT (NON-BLOCKING)
    event_queue.put({
        "ts": time.time(),
        "user": user["email"],
        "event": event,
        "score": score,
        "decision": decision
    })

    return jsonify({
        "decision": decision,
        "score": score,
        "latency_ms": round((time.time() - start) * 1000, 2)
    })


@app.route("/key", methods=["POST"])
def key_route():
    data = request.json or {}
    email = data.get("email", "")

    key = generate_key(email)

    return jsonify({
        "key": key
    })


@app.route("/")
def home():
    return "AI FIREWALL ACTIVE"


# ─────────────────────────────────────────────
# START
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
