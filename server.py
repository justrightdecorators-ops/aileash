from flask import Flask, request, jsonify, redirect

import auth
import engine
import memory
import billing
from config import PORT, VERSION, PRODUCT, FREE_TIER_LIMIT

app = Flask(__name__)

@app.route("/")
def index():
    try:
        with open("static/index.html") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except:
        return "AILeash running", 200

@app.route("/health")
def health():
    return jsonify({"status": "ok", "product": PRODUCT, "version": VERSION})

@app.route("/govern", methods=["POST"])
def govern():
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        return jsonify({"error": "missing_key"}), 401

    user = auth.validate_key(api_key)
    if not user:
        return jsonify({"error": "invalid_key"}), 401

    plan = user.get("plan", "free")
    usage = memory.count_for_user(api_key)

    if plan == "free" and usage >= FREE_TIER_LIMIT:
        return jsonify({
            "error": "limit_reached",
            "upgrade_url": "/checkout?key=" + api_key
        }), 402

    event = request.get_json(silent=True) or {}

    risk_score = engine.score(event)
    decision = engine.decide(risk_score)

    memory.log(api_key, event, decision, risk_score)

    return jsonify({
        "decision": decision,
        "score": risk_score,
        "usage": usage + 1,
        "plan": plan
    })

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()

    if not email or "@" not in email:
        return jsonify({"error": "invalid_email"}), 400

    key = auth.generate_key(email)

    return jsonify({
        "api_key": key,
        "plan": "free"
    })

@app.route("/checkout")
def checkout():
    api_key = request.args.get("key", "")
    email = request.args.get("email", "")

    user = auth.validate_key(api_key) if api_key else None
    if user:
        email = user.get("email", email)

    if not email:
        return jsonify({"error": "missing_email"}), 400

    if not api_key:
        api_key = auth.generate_key(email)

    url = billing.create_checkout(email, api_key)

    if not url:
        return jsonify({"error": "billing_not_configured"}), 500

    return redirect(url)

@app.route("/webhook", methods=["POST"])
def webhook():
    import json
    try:
        event = json.loads(request.data)

        if event.get("type") == "checkout.session.completed":
            session = event["data"]["object"]
            api_key = session.get("metadata", {}).get("api_key")

            if api_key:
                auth.upgrade_key(api_key)

        return jsonify({"received": True})

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/audit")
def audit():
    api_key = request.headers.get("x-api-key", "")
    if not auth.validate_key(api_key):
        return jsonify({"error": "invalid_key"}), 401

    return jsonify(memory.recent(50))


if __name__ == "__main__":
    print("Starting AILeash...")
    app.run(host="0.0.0.0", port=PORT)
