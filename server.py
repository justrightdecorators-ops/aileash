import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets, base64
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "2.1.0"
HOST            = os.environ.get("HOST", "https://sebbi.pro")
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA      = 100
STRIPE_PRICE_ID = ""
_db_lock        = threading.Lock()

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT UNIQUE, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0, free_quota INTEGER DEFAULT 100, plan_type TEXT DEFAULT 'free')")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()

def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET:
        return None
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET, "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return None
    except Exception as e:
        print("Stripe error: " + str(e), flush=True)
        return None

def setup_stripe():
    global STRIPE_PRICE_ID
    if not STRIPE_SECRET:
        print("WARNING: No STRIPE_SECRET set.", flush=True)
        return
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row and row[0]:
        STRIPE_PRICE_ID = row[0]
        print("Stripe ready: " + STRIPE_PRICE_ID, flush=True)
        return
    print("Setting up Stripe...", flush=True)
    product = stripe_call("POST", "/products", {"name": "AILeash Professional", "description": "Unlimited AI governance. EU AI Act compliant."})
    if not product or "id" not in product:
        print("Stripe product failed: " + str(product), flush=True)
        return
    price = stripe_call("POST", "/prices", {"product": product["id"], "currency": "gbp", "unit_amount": 4900, "recurring[interval]": "month"})
    if not price or "id" not in price:
        print("Stripe price failed: " + str(price), flush=True)
        return
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()
    print("Stripe ready: " + STRIPE_PRICE_ID, flush=True)

def create_api_key(email, plan_type="free"):
    email = str(email).strip().lower()
    if not email or "@" not in email:
        return None, "invalid_email"
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("INSERT INTO api_keys (key,email,stripe_customer,actions_used,created,active,is_paid,free_quota,plan_type) VALUES(?,?,?,?,?,?,?,?,?)",
                (key, email, "", 0, time.time(), 1, 1 if plan_type == "paid" else 0, FREE_QUOTA, plan_type))
            _conn.commit()
        except sqlite3.IntegrityError:
            return None, "email_exists"
    return key, None

def get_key_info(key):
    with _db_lock:
        return _conn.execute("SELECT email,actions_used,active,is_paid,free_quota,plan_type FROM api_keys WHERE key=?", (key,)).fetchone()

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?", (key,))
        _conn.commit()

WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(p): return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def update_windows(uid):
    t = now()
    for q in [WINDOW_60S[uid], WINDOW_5M[uid], WINDOW_1H[uid]]:
        q.append(t)
    c60 = t-60;  c5m = t-300;  c1h = t-3600
    while WINDOW_60S[uid] and WINDOW_60S[uid][0] < c60: WINDOW_60S[uid].popleft()
    while WINDOW_5M[uid]  and WINDOW_5M[uid][0]  < c5m: WINDOW_5M[uid].popleft()
    while WINDOW_1H[uid]  and WINDOW_1H[uid][0]  < c1h: WINDOW_1H[uid].popleft()

def velocity(uid):
    return {"60s": len(WINDOW_60S[uid]), "5m": len(WINDOW_5M[uid]), "1h": len(WINDOW_1H[uid])}

def load_user(uid):
    with _db_lock:
        row = _conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"trust": row[0], "last_country": row[1]} if row else {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country", (uid, trust, country))
        _conn.commit()

def compute_score(s):
    score = 0
    score += (1 - s["trust"]) * 0.30
    score += min(s["v60"] / 20, 1) * 0.15
    score += min(s["v5m"] / 50, 1) * 0.10
    score += min(s["v1h"] / 200, 1) * 0.10
    score += min(math.log1p(s["amount"]) / math.log1p(10000), 1) * 0.15
    score += s["device_risk"] * 0.10
    score += s["anomaly"] * 0.10
    if s["country_shift"]: score += 0.10
    if s["unsafe_country"]: score += 0.10
    return clamp(score)

def decide(score):
    if score < 0.35: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def update_trust(trust, decision):
    if decision == "ALLOW": trust += (1 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK": trust -= trust * 0.08
    return clamp(trust, 0.05, 1.0)

def explain(s):
    r = []
    if s["trust"] < 0.4: r.append("low_trust")
    if s["v60"] > 10: r.append("velocity_spike")
    if s["amount"] > 500: r.append("high_amount")
    if s["device_risk"] > 0.5: r.append("risky_device")
    if s["country_shift"]: r.append("country_shift")
    if s["unsafe_country"]: r.append("unsafe_country")
    if s["anomaly"] > 0.5: r.append("behaviour_anomaly")
    return r

def chain_tip():
    with _db_lock:
        row = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event, result, ts):
    prev = chain_tip()
    h = sha({"prev_hash": prev, "ts": ts, "event": event, "result": result})
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result), prev, h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows = _conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows:
        return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        payload = {"prev_hash": row[2], "ts": row[4], "event": json.loads(row[0]), "result": json.loads(row[1])}
        if sha(payload) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at_block": i, "message": "Chain broken at block " + str(i)}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "message": "Chain intact"}

def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - event.keys()
    if missing:
        raise ValueError("Missing fields: " + str(missing))
    if api_key:
        key_info = get_key_info(api_key)
        if not key_info:
            return {"error": "invalid_api_key"}, 401
        email, actions_used, active, is_paid, free_quota, plan_type = key_info
        if not active:
            return {"error": "account_inactive"}, 403
        if not is_paid and actions_used >= free_quota:
            return {"error": "quota_exceeded", "message": "Free quota reached. Upgrade at " + HOST + "/pricing"}, 429
    ts = now()
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v = velocity(event["user_id"])
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"], "v1h": v["1h"],
        "amount": float(event.get("amount", 0)), "device_risk": float(event.get("device_risk", 0)),
        "anomaly": float(event.get("anomaly", 0)),
        "country_shift": state["last_country"] is not None and state["last_country"] != event["country"],
        "unsafe_country": event["country"] not in SAFE_COUNTRIES
    }
    score    = compute_score(signals)
    decision = decide(score)
    reasons  = explain(signals)
    trust    = update_trust(state["trust"], decision)
    save_user(event["user_id"], trust, event["country"])
    result   = {"decision": decision, "score": round(score, 4), "trust": round(trust, 4), "reasons": reasons, "version": VERSION, "timestamp": ts}
    result["audit_hash"] = append_audit(event, result, ts)
    if api_key:
        increment_usage(api_key)
    return result, 200

def send_json(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h, html, status=200):
    body = html.encode() if isinstance(html, str) else html
    h.send_response(status)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    length = int(h.headers.get("Content-Length", 0))
    if length:
        try:
            return json.loads(h.rfile.read(length))
        except Exception:
            return {}
    return {}

def get_api_key(h):
    auth = h.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return h.headers.get("X-API-Key", "").strip()

LANDING_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+"
    "CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0"
    "aWFsLXNjYWxlPTEuMCI+Cjx0aXRsZT5BSUxlYXNoIOKAlCBFbnRl"
    "cnByaXNlIEFJIEdvdmVybmFuY2UgUGxhdGZvcm08L3RpdGxlPgo8"
    "bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0iUmVhbC10"
    "aW1lIEFJIGdvdmVybmFuY2UsIHRydXN0IHNjb3JpbmcsIFNIQS0y"
    "NTYgYXVkaXQgY2hhaW5zIGFuZCBFVSBBSSBBY3QgY29tcGxpYW5j"
    "ZS4iPgo8L2hlYWQ+Cjxib2R5IHN0eWxlPSJmb250LWZhbWlseTpz"
    "YW5zLXNlcmlmO21heC13aWR0aDo5MDBweDttYXJnaW46YXV0bztw"
    "YWRkaW5nOjQwcHgiPgo8aDE+QUlMZWFzaDwvaDE+CjxwPkVudGVy"
    "cHJpc2UgQUkgR292ZXJuYW5jZSBJbmZyYXN0cnVjdHVyZS4gUmVh"
    "bC10aW1lIHJpc2sgc2NvcmluZywgU0hBLTI1NiBhdWRpdCBjaGFp"
    "bnMsIGFuZCBFVSBBSSBBY3QgY29tcGxpYW5jZS48L3A+CjxoMj5H"
    "ZXQgRnJlZSBBUEkgS2V5PC9oMj4KPGlucHV0IHR5cGU9ImVtYWls"
    "IiBpZD0iZW1haWwiIHBsYWNlaG9sZGVyPSJ5b3VAY29tcGFueS5j"
    "b20iIHN0eWxlPSJwYWRkaW5nOjEwcHg7d2lkdGg6MzAwcHg7bWFy"
    "Z2luLXJpZ2h0OjEwcHgiPgo8YnV0dG9uIG9uY2xpY2s9ImdldEtl"
    "eSgpIiBzdHlsZT0icGFkZGluZzoxMHB4IDIwcHg7YmFja2dyb3Vu"
    "ZDojY2MwMDAwO2NvbG9yOiNmZmY7Ym9yZGVyOm5vbmU7Y3Vyc29y"
    "OnBvaW50ZXIiPkdldCBGcmVlIEtleTwvYnV0dG9uPgo8ZGl2IGlk"
    "PSJyZXN1bHQiIHN0eWxlPSJtYXJnaW4tdG9wOjIwcHg7cGFkZGlu"
    "ZzoxNXB4O2JhY2tncm91bmQ6I2YwZjBmMDtkaXNwbGF5Om5vbmUi"
    "PjwvZGl2Pgo8aDI+VXBncmFkZSAmd291bGQ7PTQ5L21vPC9oMj4K"
    "PGlucHV0IHR5cGU9ImVtYWlsIiBpZD0icGVtYWlsIiBwbGFjZWhv"
    "bGRlcj0ieW91QGNvbXBhbnkuY29tIiBzdHlsZT0icGFkZGluZzox"
    "MHB4O3dpZHRoOjMwMHB4O21hcmdpbi1yaWdodDoxMHB4Ij4KPGJ1"
    "dHRvbiBvbmNsaWNrPSJ1cGdyYWRlKCkiIHN0eWxlPSJwYWRkaW5n"
    "OjEwcHggMjBweDtiYWNrZ3JvdW5kOiMwMDY2MDA7Y29sb3I6I2Zm"
    "Zjtib3JkZXI6bm9uZTtjdXJzb3I6cG9pbnRlciI+VXBncmFkZTwv"
    "YnV0dG9uPgo8ZGl2IGlkPSJzdHJpcGVub3RpY2UiIHN0eWxlPSJt"
    "YXJnaW4tdG9wOjEwcHg7cGFkZGluZzoxMHB4O2JhY2tncm91bmQ6"
    "I2ZmZjNjZDtkaXNwbGF5Om5vbmUiPlN0cmlwZSBub3QgY29uZmln"
    "dXJlZC4gU2V0IFNUUklQRV9TRUNSRVQgaW4gUmFpbHdheSB2YXJp"
    "YWJsZXMuPC9kaXY+CjxoMj5BUEkgRW5kcG9pbnQ8L2gyPgo8cHJl"
    "IHN0eWxlPSJiYWNrZ3JvdW5kOiMxMTExMTE7Y29sb3I6I2NjY2Nj"
    "YztwYWRkaW5nOjIwcHg7Ym9yZGVyLXJhZGl1czo4cHgiPlBPU1Qg"
    "L2FwaS9nb3Zlcm4KQXV0aG9yaXphdGlvbjogQmVhcmVyIGFsX2xp"
    "dmVfLi4uCgp7CiAgInVzZXJfaWQiOiAidXNlcl8wMDEiLAogICJh"
    "Y3Rpb24iOiAicGF5bWVudCIsCiAgImFtb3VudCI6IDI1MDAsCiAg"
    "ImNvdW50cnkiOiAiVUsiLAogICJkZXZpY2VfaWQiOiAibW9iaWxl"
    "IiwKICAiZGV2aWNlX3Jpc2siOiAwLjIsCiAgImFub21hbHkiOiAw"
    "LjEKfTwvcHJlPgo8c2NyaXB0Pgphc3luYyBmdW5jdGlvbiBnZXRL"
    "ZXkoKXsKICBjb25zdCBlbWFpbD1kb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgnZW1haWwnKS52YWx1ZS50cmltKCk7CiAgaWYoIWVtYWls"
    "KXthbGVydCgnRW50ZXIgeW91ciBlbWFpbCcpO3JldHVybn0KICBj"
    "b25zdCByPWF3YWl0IGZldGNoKCcvYXBpL2tleXMnLHttZXRob2Q6"
    "J1BPU1QnLGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNh"
    "dGlvbi9qc29uJ30sYm9keTpKU09OLnN0cmluZ2lmeSh7ZW1haWx9"
    "KX0pOwogIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgY29uc3Qg"
    "Ym94PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXN1bHQnKTsK"
    "ICBib3guc3R5bGUuZGlzcGxheT0nYmxvY2snOwogIGlmKGQua2V5"
    "KXtib3guaW5uZXJIVE1MPSc8Yj5Zb3VyIEFQSSBLZXk6PC9iPjxi"
    "cj4nK2Qua2V5Kyc8YnI+PGJyPjEwMCBmcmVlIGRlY2lzaW9ucyBp"
    "bmNsdWRlZC4nfQogIGVsc2V7Ym94LmlubmVySFRNTD0nRXJyb3I6"
    "ICcrKGQuZXJyb3J8fCdGYWlsZWQnKX0KfQphc3luYyBmdW5jdGlv"
    "biB1cGdyYWRlKCl7CiAgY29uc3QgZW1haWw9ZG9jdW1lbnQuZ2V0"
    "RWxlbWVudEJ5SWQoJ3BlbWFpbCcpLnZhbHVlLnRyaW0oKTsKICBp"
    "ZighZW1haWwpe2FsZXJ0KCdFbnRlciB5b3VyIGVtYWlsJyk7cmV0"
    "dXJufQogIGNvbnN0IHI9YXdhaXQgZmV0Y2goJy9jcmVhdGUtY2hl"
    "Y2tvdXQnLHttZXRob2Q6J1BPU1QnLGhlYWRlcnM6eydDb250ZW50"
    "LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sYm9keTpKU09OLnN0"
    "cmluZ2lmeSh7ZW1haWx9KX0pOwogIGNvbnN0IGQ9YXdhaXQgci5q"
    "c29uKCk7CiAgaWYoZC5jaGVja291dF91cmwpe3dpbmRvdy5sb2Nh"
    "dGlvbi5ocmVmPWQuY2hlY2tvdXRfdXJsfQogIGVsc2V7ZG9jdW1l"
    "bnQuZ2V0RWxlbWVudEJ5SWQoJ3N0cmlwZW5vdGljZScpLnN0eWxl"
    "LmRpc3BsYXk9J2Jsb2NrJ30KfQo8L3NjcmlwdD4KPC9ib2R5Pgo8"
    "L2h0bWw+"
)
LANDING = base64.b64decode(LANDING_B64).decode("utf-8")

class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/"):
            send_html(self, LANDING)
        elif path == "/api/health":
            send_json(self, {"status": "ok", "version": VERSION})
        elif path == "/api/verify-chain":
            send_json(self, verify_chain())
        elif path == "/api/stats":
            with _db_lock:
                keys   = _conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                audits = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_json(self, {"api_keys": keys, "audit_blocks": audits, "version": VERSION})
        elif path == "/robots.txt":
            send_html(self, "User-agent: *\nAllow: /\nAllow: /openapi.json\nAllow: /ai-plugin.json\n")
        elif path == "/openapi.json":
            send_json(self, {"openapi": "3.0.0", "info": {"title": "AILeash Governance API", "version": VERSION}, "servers": [{"url": "https://sebbi.pro"}]})
        elif path == "/ai-plugin.json" or path == "/.well-known/ai-plugin.json":
            send_json(self, {"schema_version": "v1", "name_for_human": "AILeash", "name_for_model": "aileash", "description_for_model": "AI governance API. POST to /api/govern. Returns ALLOW CHALLENGE or BLOCK with SHA-256 audit trail.", "api": {"type": "openapi", "url": "https://sebbi.pro/openapi.json"}, "contact_email": "hello@monop.ai"})
        else:
            send_json(self, {"error": "not_found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)

        if path == "/api/govern":
            api_key = get_api_key(self)
            try:
                result, status = govern(data, api_key if api_key else None)
                send_json(self, result, status)
            except ValueError as e:
                send_json(self, {"error": str(e)}, 400)
            except Exception as e:
                send_json(self, {"error": "internal_error", "detail": str(e)}, 500)

        elif path == "/api/keys":
            email = str(data.get("email", "")).strip().lower()
            key, err = create_api_key(email)
            if err:
                msgs = {"invalid_email": "Please enter a valid email address.", "email_exists": "A key already exists for this email."}
                send_json(self, {"error": msgs.get(err, err)}, 400)
                return
            send_json(self, {"key": key, "email": email, "plan": "free", "quota": FREE_QUOTA})

        elif path == "/create-checkout":
            email = str(data.get("email", "")).strip().lower()
            if not email or "@" not in email:
                send_json(self, {"error": "invalid_email"}, 400)
                return
            if not STRIPE_SECRET:
                send_json(self, {"error": "stripe_not_configured"}, 503)
                return
            if not STRIPE_PRICE_ID:
                setup_stripe()
            if not STRIPE_PRICE_ID:
                send_json(self, {"error": "stripe_setup_failed"}, 503)
                return
            session = stripe_call("POST", "/checkout/sessions", {
                "mode": "subscription",
                "customer_email": email,
                "success_url": HOST + "/?success=true",
                "cancel_url": HOST + "/?cancel=true",
                "line_items[0][price]": STRIPE_PRICE_ID,
                "line_items[0][quantity]": "1"
            })
            if not session or "url" not in session:
                send_json(self, {"error": "checkout_failed", "detail": str(session)}, 500)
                return
            send_json(self, {"checkout_url": session["url"]})

        else:
            send_json(self, {"error": "not_found"}, 404)

if __name__ == "__main__":
    print("AILeash v" + VERSION + " starting on port " + str(PORT), flush=True)
    setup_stripe()
    server = ThreadedServer(("0.0.0.0", PORT), Handler)
    print("Ready.", flush=True)
    server.serve_forever()
  
