"""
AILeash Unified Server
Ravishing + SebbiPro + Billing + Landing
Railway-safe production build
"""

import json, os, urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------- CONFIG ----------------

PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")

# ---------------- LANDING ----------------

def load_landing():
    try:
        with open("static/landing.html", "r", encoding="utf-8") as f:
            return f.read()
    except:
        return "<h1>Landing Missing</h1>"

LANDING = load_landing()

# ---------------- STRIPE (SAFE LAYER) ----------------

def stripe_call(method, endpoint, data=None):
    if not STRIPE_KEY:
        return {"error": "missing_stripe_key"}

    url = "https://api.stripe.com/v1" + endpoint
    body = urllib.parse.urlencode(data).encode() if data else None

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": "Bearer " + STRIPE_KEY},
        method=method
    )

    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

# ---------------- ENGINE LAYERS ----------------

def ravishing_engine(payload):
    return {
        "engine": "ravishing",
        "status": "ok",
        "input": payload
    }

def sebbipro_engine(payload):
    return {
        "engine": "sebbipro",
        "status": "ok",
        "input": payload
    }

# ---------------- BILLING LAYER (SAFE INIT) ----------------

def create_product_safe():
    product = stripe_call("POST", "/products", {
        "name": "AILeash Unified API"
    })

    if "id" not in product:
        return product

    price = stripe_call("POST", "/prices", {
        "product": product["id"],
        "currency": "gbp",
        "unit_amount": 1,
        "recurring[interval]": "month"
    })

    if "id" not in price:
        return price

    return {"product": product["id"], "price": price["id"]}

# ---------------- RESPONSE HELPERS ----------------

def send_json(h, data, status=200):
    body = json.dumps(data).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.end_headers()
    h.wfile.write(body)

def send_html(h, html):
    body = html.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.end_headers()
    h.wfile.write(body)

# ---------------- ROUTER ----------------

def route_engine(path, body):
    if path.startswith("/ravishing"):
        return ravishing_engine(body)
    if path.startswith("/sebbipro"):
        return sebbipro_engine(body)
    return {"error": "invalid_engine"}

# ---------------- SERVER ----------------

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        # Landing page (frontend)
        if self.path == "/":
            return send_html(self, LANDING)

        # health check
        if self.path == "/health":
            return send_json(self, {"ok": True})

        # optional debug billing setup
        if self.path == "/setup":
            result = create_product_safe()
            return send_json(self, result)

        return send_json(self, {"error": "not_found"}, 404)

    def do_POST(self):

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            body = json.loads(raw) if raw else {}
        except:
            return send_json(self, {"error": "invalid_json"}, 400)

        result = route_engine(self.path, body)
        return send_json(self, result)

# ---------------- BOOT ----------------

if __name__ == "__main__":
    print("=== AILeash Unified System Starting ===")
    print("PORT:", PORT)
    print("Stripe enabled:", bool(STRIPE_KEY))

    # IMPORTANT: never block startup
    try:
        if STRIPE_KEY:
            print("Stripe mode: active")
        else:
            print("Stripe mode: disabled")
    except Exception as e:
        print("Stripe warning:", e)

    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
