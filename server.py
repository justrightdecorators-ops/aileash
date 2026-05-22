from flask import Flask, request, jsonify, redirect
import engine
import memory
import auth
import billing
from config import PORT, VERSION, PRODUCT, FREE_TIER_LIMIT

app = Flask(__name__)

# ── LANDING PAGE ───────────────────────────────────────

@app.route("/")
def index():
    with open("static/index.html") as f:
        return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}

# ── HEALTH ─────────────────────────────────────────────

@app.route("/health")
def health():
    return jsonify({"status": "ok", "product": PRODUCT, "version": VERSION})

# ── GOVERN ─────────────────────────────────────────────

@app.route("/govern", methods=["POST"])
def govern():
    api_key = request.headers.get("x-api-key", "")
    if not api_key:
        return jsonify({"error": "missing_key", "message": "Include your API key in the x-api-key header."}), 401
    user = auth.validate_key(api_key)
    if not user:
        return jsonify({"error": "invalid_key", "message": "Invalid API key."}), 401
    plan = user.get("plan", "free")
    usage = memory.count_for_user(api_key)
    if plan == "free" and usage >= FREE_TIER_LIMIT:
        return jsonify({
            "error": "limit_reached",
            "message": "Upgrade to continue using AILeash",
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
        "limit": FREE_TIER_LIMIT if plan == "free" else "unlimited",
        "plan": plan
    })

# ── REGISTER ───────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    name = data.get("name", "").strip()
    if not email or "@" not in email:
        return jsonify({"error": "Please provide a valid email address."}), 400
    key = auth.generate_key(email)
    return jsonify({
        "api_key": key,
        "plan": "free",
        "limit": FREE_TIER_LIMIT,
        "email": email,
        "message": "Your free API key. Add x-api-key: " + key + " to your requests."
    })

# ── CONTACT ────────────────────────────────────────────

@app.route("/contact", methods=["POST"])
def contact():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    message = data.get("message", "").strip()
    if not name or not email:
        return jsonify({"error": "Please provide your name and email."}), 400
    print("CONTACT: " + name + " | " + email + " | " + phone + " | " + message)
    return jsonify({"success": True, "message": "Thanks " + name + ". We will be in touch shortly."})

# ── CHECKOUT ───────────────────────────────────────────

@app.route("/checkout")
def checkout():
    api_key = request.args.get("key", "")
    email = request.args.get("email", "")
    user = auth.validate_key(api_key) if api_key else None
    if user:
        email = user.get("email", email)
    if not email or "@" not in email:
        return jsonify({"error": "Provide email as ?email=you@example.com"}), 400
    if not api_key:
        api_key = auth.generate_key(email)
    url = billing.create_checkout(email, api_key)
    if not url:
        return jsonify({
            "error": "Payment not configured.",
            "message": "Contact hello@monopcontent.com"
        }), 500
    return redirect(url)

# ── WEBHOOK ────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    import json
    try:
        event = json.loads(request.data)
        etype = event.get("type", "")
        if etype == "checkout.session.completed":
            session = event["data"]["object"]
            api_key = session.get("metadata", {}).get("api_key", "")
            if api_key:
                auth.upgrade_key(api_key)
                print("UPGRADED: " + api_key)
        return jsonify({"received": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ── SUCCESS ────────────────────────────────────────────

@app.route("/success")
def success():
    key = request.args.get("key", "")
    auth.upgrade_key(key)
    return """<!DOCTYPE html>
<html><head><meta charset=UTF-8><title>Welcome to AILeash Pro</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#080808;color:#ccc;font-family:'Courier New',monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:2rem;text-align:center}
.box{max-width:560px}
.logo{color:#00ff88;font-size:1.3rem;font-weight:bold;letter-spacing:3px;margin-bottom:2rem}
.logo span{color:#ccc}
h1{font-size:1.8rem;color:#fff;margin-bottom:1rem}
p{color:#444;margin-bottom:1rem;line-height:1.8;font-size:.9rem}
.key{background:#0c0c0c;border:1px solid #00ff88;padding:1rem;margin:1.5rem 0;color:#00ff88;font-size:.85rem;word-break:break-all}
.steps{text-align:left;list-style:none;margin:1.5rem 0}
.steps li{padding:.6rem 0;border-bottom:1px solid #111;color:#444;font-size:.85rem}
.steps li:before{content:">> ";color:#00ff88}
.steps li:last-child{border-bottom:none}
a{color:#00ff88;text-decoration:none}
.btn{display:inline-block;background:#00ff88;color:#080808;padding:.8rem 2rem;font-family:'Courier New',monospace;font-weight:bold;margin-top:1rem;text-decoration:none}
</style>
</head><body><div class="box">
<div class="logo">AI<span>Leash</span></div>
<h1>Welcome to Pro.</h1>
<p>Payment successful. Your API key has been upgraded to unlimited requests.</p>
<div class="key">x-api-key: """ + key + """</div>
<ul class="steps">
<li>Save your API key above</li>
<li>pip install requests</li>
<li>Add x-api-key header to all requests</li>
<li>POST to https://sebbi.pro/govern</li>
<li>Every AI decision governed and audited</li>
</ul>
<a href="/" class="btn">Back to AILeash</a>
<p style="margin-top:1.5rem;color:#252525;font-size:.78rem">
Questions? <a href="mailto:hello@monopcontent.com">hello@monopcontent.com</a>
</p>
</div></body></html>"""

# ── AUDIT ──────────────────────────────────────────────

@app.route("/audit")
def audit():
    api_key = request.headers.get("x-api-key", "")
    if not auth.validate_key(api_key):
        return jsonify({"error": "invalid_key"}), 401
    return jsonify(memory.recent(50))

# ── RUN ────────────────────────────────────────────────

if __name__ == "__main__":
    print("AILeash v" + VERSION + " starting on port " + str(PORT))
    app.run(host="0.0.0.0", port=PORT)
