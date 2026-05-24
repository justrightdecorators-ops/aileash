"""
AILEASH GOVERNANCE ENGINE v2.0
================================
Owner:    Justin — Monop Content, Blyth, UK
License:  MIT
Built:    May 2026
"""

import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_KEY = os.getenv("STRIPE_KEY", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "2.0.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
STRIPE_PRICE_ID = ""
_db_lock        = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn


_conn = get_conn()


def stripe_call(method, endpoint, data=None):
    url = "https://api.stripe.com/v1" + endpoint
    headers = {
        "Authorization": "Bearer " + STRIPE_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except:
            return {"error": "stripe_http_error"}


# ✅ LANDING IS NOW EXTERNAL FILE
def get_landing():
    with open("static/landing.html", "r", encoding="utf-8") as f:
        return f.read()


def setup_stripe():
    global STRIPE_PRICE_ID

    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()

    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"Stripe: {STRIPE_PRICE_ID}")
        return

    print("Setting up Stripe...")

    product = stripe_call(
        "POST",
        "/products",
        {
            "name": "AILeash Governance API",
            "description": "AI governance API — charged per action."
        }
    )

    if not isinstance(product, dict) or "id" not in product:
        raise RuntimeError(f"Stripe product creation failed: {product}")

    price = stripe_call(
        "POST",
        "/prices",
        {
            "product": product["id"],
            "currency": "gbp",
            "billing_scheme": "per_unit",
            "unit_amount": 1,
            "recurring[interval]": "month",
            "recurring[usage_type]": "metered",
            "nickname": "Per Action"
        }
    )

    if not isinstance(price, dict) or "id" not in price:
        raise RuntimeError(f"Stripe price creation failed: {price}")

    STRIPE_PRICE_ID = price["id"]

    with _db_lock:
        _conn.execute(
            "INSERT INTO config(k,v) VALUES('stripe_price_id',?)",
            (STRIPE_PRICE_ID,)
        )
        _conn.commit()

    print(f"Stripe ready: {STRIPE_PRICE_ID}")


def send(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)


def send_html(h, html):
    body = html.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def err(h, msg, status=400):
    send(h, {"error": msg}, status)


def get_key(h):
    auth = h.headers.get("Authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else None


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            send_html(self, get_landing())
        else:
            err(self, "Not found", 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)

        try:
            data = json.loads(raw)
        except:
            return err(self, "Invalid JSON")

        send(self, {"ok": True, "received": data})


if __name__ == "__main__":
    print(f"Starting AILeash v{VERSION} on port {PORT}")
    setup_stripe()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
