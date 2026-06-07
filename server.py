import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
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
_db_lock = threading.Lock()

# ============================================================================
# DATABASE
# ============================================================================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        trust REAL DEFAULT 0.5,
        last_country TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        user_id TEXT,
        event_json TEXT,
        result_json TEXT,
        prev_hash TEXT,
        audit_hash TEXT UNIQUE
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY,
        email TEXT UNIQUE,
        stripe_customer TEXT,
        actions_used INTEGER DEFAULT 0,
        created REAL,
        active INTEGER DEFAULT 1,
        is_paid INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 100,
        plan_type TEXT DEFAULT 'free'
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS config (
        k TEXT PRIMARY KEY,
        v TEXT
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()

# ============================================================================
# STRIPE - AUTO SETUP (no Price ID needed)
# ============================================================================
def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET:
        return None
    url = "https://api.stripe.com/v1" + endpoint
    headers = {
        "Authorization": "Bearer " + STRIPE_SECRET,
        "Content-Type": "application/x-www-form-urlencoded"
    }
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
        print(f"Stripe error: {e}", flush=True)
        return None

def setup_stripe():
    global STRIPE_PRICE_ID
    if not STRIPE_SECRET:
        print("WARNING: No STRIPE_SECRET set. Billing disabled.", flush=True)
        return
    # Check if we already have a price ID stored
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row and row[0]:
        STRIPE_PRICE_ID = row[0]
        print(f"Stripe ready: {STRIPE_PRICE_ID}", flush=True)
        return
    # Auto-create product and price
    print("Setting up Stripe product...", flush=True)
    product = stripe_call("POST", "/products", {
        "name": "AILeash Professional",
        "description": "Unlimited AI governance decisions. EU AI Act compliant."
    })
    if not product or "id" not in product:
        print(f"Stripe product creation failed: {product}", flush=True)
        return
    price = stripe_call("POST", "/prices", {
        "product": product["id"],
        "currency": "gbp",
        "unit_amount": 4900,
        "recurring[interval]": "month"
    })
    if not price or "id" not in price:
        print(f"Stripe price creation failed: {price}", flush=True)
        return
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute(
            "INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_id',?)",
            (STRIPE_PRICE_ID,)
        )
        _conn.commit()
    print(f"Stripe ready: {STRIPE_PRICE_ID}", flush=True)

# ============================================================================
# KEY MANAGEMENT
# ============================================================================
def create_api_key(email, plan_type="free"):
    email = str(email).strip().lower()
    if not email or "@" not in email:
        return None, "invalid_email"
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("""INSERT INTO api_keys
                (key,email,stripe_customer,actions_used,created,active,is_paid,free_quota,plan_type)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (key, email, "", 0, time.time(), 1,
                 1 if plan_type == "paid" else 0,
                 FREE_QUOTA, plan_type))
            _conn.commit()
        except sqlite3.IntegrityError:
            return None, "email_exists"
    return key, None

def get_key_info(key):
    with _db_lock:
        row = _conn.execute(
            "SELECT email,actions_used,active,is_paid,free_quota,plan_type FROM api_keys WHERE key=?",
            (key,)
        ).fetchone()
    return row

def increment_usage(key):
    with _db_lock:
        _conn.execute(
            "UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?",
            (key,)
        )
        _conn.commit()

# ============================================================================
# VELOCITY TRACKING
# ============================================================================
WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(p): return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def prune(q, s):
    c = now() - s
    while q and q[0] < c:
        q.popleft()

def update_windows(uid):
    t = now()
    for q in [WINDOW_60S[uid], WINDOW_5M[uid], WINDOW_1H[uid]]:
        q.append(t)
    prune(WINDOW_60S[uid], 60)
    prune(WINDOW_5M[uid], 300)
    prune(WINDOW_1H[uid], 3600)

def velocity(uid):
    return {
        "60s": len(WINDOW_60S[uid]),
        "5m":  len(WINDOW_5M[uid]),
        "1h":  len(WINDOW_1H[uid])
    }

# ============================================================================
# USER TRUST
# ============================================================================
def load_user(uid):
    with _db_lock:
        row = _conn.execute(
            "SELECT trust,last_country FROM users WHERE user_id=?", (uid,)
        ).fetchone()
    if not row:
        return {"trust": 0.5, "last_country": None}
    return {"trust": row[0], "last_country": row[1]}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute("""INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
            trust=excluded.trust,
            last_country=excluded.last_country""",
            (uid, trust, country))
        _conn.commit()

# ============================================================================
# RISK ENGINE
# ============================================================================
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
    if decision == "ALLOW":     trust += (1 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK":   trust -= trust * 0.08
    return clamp(trust, 0.05, 1.0)

def explain(s):
    r = []
    if s["trust"] < 0.4:       r.append("low_trust")
    if s["v60"] > 10:          r.append("velocity_spike")
    if s["amount"] > 500:      r.append("high_amount")
    if s["device_risk"] > 0.5: r.append("risky_device")
    if s["country_shift"]:     r.append("country_shift")
    if s["unsafe_country"]:    r.append("unsafe_country")
    if s["anomaly"] > 0.5:     r.append("behaviour_anomaly")
    return r

# ============================================================================
# AUDIT CHAIN
# ============================================================================
def chain_tip():
    with _db_lock:
        row = _conn.execute(
            "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event, result, ts):
    prev = chain_tip()
    payload = {"prev_hash": prev, "ts": ts, "event": event, "result": result}
    h = sha(payload)
    with _db_lock:
        _conn.execute("""INSERT INTO audit_log
            (ts,user_id,event_json,result_json,prev_hash,audit_hash)
            VALUES(?,?,?,?,?,?)""",
            (ts, event["user_id"], json.dumps(event),
             json.dumps(result), prev, h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows = _conn.execute(
            "SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC"
        ).fetchall()
    if not rows:
        return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        payload = {
            "prev_hash": row[2], "ts": row[4],
            "event": json.loads(row[0]), "result": json.loads(row[1])
        }
        if sha(payload) != row[3] or row[2] != prev:
            return {"valid": False, "broken_at_block": i,
                    "message": f"Chain broken at block {i}"}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "message": "Chain intact"}

# ============================================================================
# GOVERN
# ============================================================================
def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - event.keys()
    if missing:
        raise ValueError(f"Missing fields: {missing}")

    # Key validation
    if api_key:
        key_info = get_key_info(api_key)
        if not key_info:
            return {"error": "invalid_api_key"}, 401
        email, actions_used, active, is_paid, free_quota, plan_type = key_info
        if not active:
            return {"error": "account_inactive"}, 403
        if not is_paid and actions_used >= free_quota:
            return {
                "error": "quota_exceeded",
                "message": f"Free quota of {free_quota} actions reached. Upgrade at {HOST}/pricing"
            }, 429

    ts = now()
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v = velocity(event["user_id"])

    signals = {
        "trust":        state["trust"],
        "v60":          v["60s"],
        "v5m":          v["5m"],
        "v1h":          v["1h"],
        "amount":       float(event.get("amount", 0)),
        "device_risk":  float(event.get("device_risk", 0)),
        "anomaly":      float(event.get("anomaly", 0)),
        "country_shift": (
            state["last_country"] is not None and
            state["last_country"] != event["country"]
        ),
        "unsafe_country": event["country"] not in SAFE_COUNTRIES
    }

    score    = compute_score(signals)
    decision = decide(score)
    reasons  = explain(signals)
    trust    = update_trust(state["trust"], decision)

    save_user(event["user_id"], trust, event["country"])

    result = {
        "decision":    decision,
        "score":       round(score, 4),
        "trust":       round(trust, 4),
        "reasons":     reasons,
        "version":     VERSION,
        "timestamp":   ts
    }
    result["audit_hash"] = append_audit(event, result, ts)

    if api_key:
        increment_usage(api_key)

    return result, 200

# ============================================================================
# HTTP HELPERS
# ============================================================================
def send_json(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h, html, status=200):
    body = html.encode()
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

# ============================================================================
# LANDING PAGE
# ============================================================================
LANDING = (
    '<!DOCTYPE html>\n'
    '<html lang="en">\n'
    '<head>\n'
    '<meta charset="UTF-8">\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
    '<title>AILeash - Enterprise AI Governance Platform</title>\n'
    '<meta name="description" content="Real-time AI governance, trust scoring, SHA-256 audit chains and EU AI Act compliance. Deploy in minutes.">\n'
    '<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">\n'
    '<style>\n'
    ':root{--red:#cc0000;--red2:#990000;--black:#0a0a0a;--white:#fff;--off:#f8f8f8;--border:#e0e0e0;--muted:#666;--mono:\'JetBrains Mono\',monospace;--sans:\'DM Sans\',sans-serif;--display:\'Bebas Neue\',sans-serif}\n'
    '*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}\n'
    'body{background:#fff;color:#0a0a0a;font-family:var(--sans);overflow-x:hidden}\n'
    'nav{position:fixed;top:0;left:0;right:0;z-index:100;background:#fff;border-bottom:3px solid var(--red);padding:0 40px;height:64px;display:flex;align-items:center;justify-content:space-between}\n'
    '.logo{font-family:var(--display);font-size:28px;letter-spacing:2px}.logo span{color:var(--red)}\n'
    '.nav-links{display:flex;gap:28px;align-items:center}\n'
    '.nav-links a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--red)}\n'
    '.nav-cta{background:var(--red)!important;color:#fff!important;padding:10px 20px;border-radius:4px;font-weight:700!important}\n'
    '.hero{padding:120px 40px 80px;border-bottom:1px solid var(--border)}\n'
    '.hero-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:80px;align-items:center}\n'
    '.eyebrow{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#fff;padding:6px 14px;font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-bottom:24px}\n'
    '.eyebrow::before{content:\'\';width:6px;height:6px;background:#fff;border-radius:50%;animation:pulse 2s infinite}\n'
    '@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}\n'
    'h1{font-family:var(--display);font-size:clamp(52px,5.5vw,84px);line-height:.95;letter-spacing:2px;margin-bottom:24px;text-transform:uppercase}\n'
    'h1 .red{color:var(--red)}\n'
    '.hero-p{font-size:17px;color:var(--muted);line-height:1.75;margin-bottom:36px;max-width:500px}\n'
    '.btns{display:flex;gap:12px;flex-wrap:wrap}\n'
    '.btn-p{background:var(--red);color:#fff;padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:background .2s;border-radius:4px;display:inline-block}\n'
    '.btn-p:hover{background:var(--red2)}\n'
    '.btn-o{background:transparent;color:var(--black);padding:14px 28px;border:2px solid var(--black);font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:all .2s;border-radius:4px;display:inline-block}\n'
    '.btn-o:hover{background:var(--black);color:#fff}\n'
    '.pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:28px}\n'
    '.pill{border:1px solid var(--red);color:var(--red);padding:4px 12px;font-family:var(--mono);font-size:11px;border-radius:2px}\n'
    '.terminal{background:#0a0a0a;border-radius:8px;overflow:hidden;font-family:var(--mono);font-size:13px;box-shadow:8px 8px 0 var(--red)}\n'
    '.term-bar{background:#1a1a1a;padding:12px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333}\n'
    '.dot{width:10px;height:10px;border-radius:50%}.dr{background:#ff5f56}.dy{background:#ffbd2e}.dg{background:#27c93f}\n'
    '.tlbl{margin-left:auto;font-size:10px;color:#666;letter-spacing:2px;text-transform:uppercase}\n'
    '.term-body{padding:24px;line-height:2.2;color:#ccc}\n'
    '.tc{color:#555}.tk{color:#79b8ff}.tv{color:#f0c674}.ts{color:#9ecbff}\n'
    '.ta{color:#00ff88;font-weight:700}.tw{color:#ffaa00;font-weight:700}.tb{color:#ff3b5c;font-weight:700}\n'
    '.stats{background:#0a0a0a;padding:48px}\n'
    '.stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}\n'
    '.stat{padding:24px;border-right:1px solid #222;text-align:center}.stat:last-child{border:none}\n'
    '.stat-n{font-family:var(--display);font-size:44px;color:var(--red);letter-spacing:2px}\n'
    '.stat-l{font-size:12px;color:#666;margin-top:4px;letter-spacing:1px;text-transform:uppercase}\n'
    '.sec{padding:80px 40px;border-bottom:1px solid var(--border)}\n'
    '.sec-inner{max-width:1200px;margin:0 auto}\n'
    '.sec-lbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;color:var(--red);text-transform:uppercase;margin-bottom:12px}\n'
    'h2{font-family:var(--display);font-size:clamp(36px,4vw,56px);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}\n'
    'h2 span{color:var(--red)}\n'
    '.sec-sub{font-size:17px;color:var(--muted);max-width:600px;line-height:1.7;margin-bottom:48px}\n'
    '.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border:1px solid var(--border);margin-top:40px}\n'
    '.gcard{background:#fff;padding:32px;position:relative}\n'
    '.gcard::before{content:\'\';position:absolute;top:0;left:0;right:0;height:3px;background:var(--red)}\n'
    '.gcard-ref{font-family:var(--mono);font-size:10px;color:var(--red);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}\n'
    '.gcard h3{font-family:var(--display);font-size:20px;letter-spacing:1px;margin-bottom:10px;text-transform:uppercase}\n'
    '.gcard p{font-size:14px;color:var(--muted);line-height:1.65}\n'
    '.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:40px}\n'
    '.price-card{border:1px solid var(--border);padding:36px;position:relative}\n'
    '.price-card.featured{border:2px solid var(--red);background:var(--off)}\n'
    '.price-badge{position:absolute;top:-14px;left:50%;transform:translateX(-50%);background:var(--red);color:#fff;font-family:var(--mono);font-size:10px;font-weight:700;padding:4px 16px;letter-spacing:2px;text-transform:uppercase;white-space:nowrap}\n'
    '.price-tier{font-family:var(--mono);font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}\n'
    '.price-num{font-family:var(--display);font-size:56px;letter-spacing:-1px;color:var(--black);margin-bottom:4px}\n'
    '.price-num sup{font-size:24px;vertical-align:super;color:var(--red)}\n'
    '.price-unit{font-size:13px;color:var(--muted);margin-bottom:28px;font-family:var(--mono)}\n'
    '.price-features{list-style:none;margin-bottom:32px}\n'
    '.price-features li{font-size:14px;color:var(--muted);padding:10px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}\n'
    '.price-features li::before{content:\'✓\';color:var(--red);font-weight:700}\n'
    '.signup-sec{padding:80px 40px;background:var(--off);border-bottom:1px solid var(--border)}\n'
    '.signup-inner{max-width:640px;margin:0 auto}\n'
    '.fg{margin-bottom:16px}\n'
    '.fg label{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}\n'
    '.fg input{width:100%;background:#fff;border:2px solid var(--border);color:var(--black);padding:14px 16px;font-size:15px;font-family:var(--sans);outline:none;transition:border-color .2s;border-radius:4px}\n'
    '.fg input:focus{border-color:var(--red)}\n'
    '.fg input::placeholder{color:#bbb}\n'
    '.btn-full{width:100%;margin-top:8px;padding:16px;font-size:15px}\n'
    '.key-result{display:none;margin-top:20px;background:#0a0a0a;border-radius:6px;padding:20px;font-family:var(--mono);font-size:13px;color:#00ff88;word-break:break-all}\n'
    '.key-result.visible{display:block}\n'
    '.error-box{display:none;margin-top:16px;padding:14px 16px;background:#fff5f5;border:1px solid #ffcccc;border-radius:4px;font-size:14px;color:var(--red)}\n'
    '.error-box.visible{display:block}\n'
    '.stripe-notice{display:none;margin-top:16px;padding:14px 16px;background:#fffbeb;border:1px solid #f59e0b;border-radius:4px;font-size:14px;color:#92400e}\n'
    '.stripe-notice.visible{display:block}\n'
    'footer{background:#0a0a0a;color:#444;text-align:center;padding:40px;font-family:var(--mono);font-size:12px;letter-spacing:1px}\n'
    'footer span{color:var(--red)}\n'
    '@media(max-width:900px){\n'
    '  .hero-inner{grid-template-columns:1fr}\n'
    '  .grid3{grid-template-columns:1fr}\n'
    '  .price-grid{grid-template-columns:1fr}\n'
    '  .stats-inner{grid-template-columns:repeat(2,1fr)}\n'
    '  .nav-links{display:none}\n'
    '}\n'
    '@keyframes spin{to{transform:rotate(360deg)}}\n'
    '.spin{display:inline-block;width:12px;height:12px;border:2px solid transparent;border-top-color:currentColor;border-radius:50%;animation:spin .7s linear infinite}\n'
    '</style>\n'
    '</head>\n'
    '<body>\n'
    '\n'
    '<nav>\n'
    '  <div class="logo">AI<span>LEASH</span></div>\n'
    '  <div class="nav-links">\n'
    '    <a href="#governance">Governance</a>\n'
    '    <a href="#compliance">Compliance</a>\n'
    '    <a href="#pricing">Pricing</a>\n'
    '    <a href="#api">API</a>\n'
    '    <a href="#signup" class="nav-cta">Get Free Key</a>\n'
    '  </div>\n'
    '</nav>\n'
    '\n'
    '<section class="hero">\n'
    '  <div class="hero-inner">\n'
    '    <div>\n'
    '      <div class="eyebrow">Live Governance Engine</div>\n'
    '      <h1>AI <span class="red">Governance</span><br>Infrastructure</h1>\n'
    '      <p class="hero-p">Real-time AI action scoring, SHA-256 tamper-evident audit chains, and EU AI Act compliant enforcement. Built for regulated enterprises, financial systems, and autonomous AI agents.</p>\n'
    '      <div class="btns">\n'
    '        <a href="#signup" class="btn-p">Get Free API Key</a>\n'
    '        <button class="btn-o" onclick="upgradeNow()">Upgrade — £49/mo</button>\n'
    '      </div>\n'
    '      <div class="pills">\n'
    '        <span class="pill">EU AI Act Art.13</span>\n'
    '        <span class="pill">SHA-256 Chain</span>\n'
    '        <span class="pill">9-Signal Engine</span>\n'
    '        <span class="pill">Real-Time</span>\n'
    '        <span class="pill">Zero Dependencies</span>\n'
    '      </div>\n'
    '    </div>\n'
    '    <div>\n'
    '      <div class="terminal">\n'
    '        <div class="term-bar">\n'
    '          <div class="dot dr"></div><div class="dot dy"></div><div class="dot dg"></div>\n'
    '          <span class="tlbl">AILeash Live Response</span>\n'
    '        </div>\n'
    '        <div class="term-body">\n'
    '          <span class="tc">// POST /api/govern</span><br>\n'
    '          <span class="tk">"decision"</span>: <span class="ta">"ALLOW"</span>,<br>\n'
    '          <span class="tk">"score"</span>: <span class="tv">0.2841</span>,<br>\n'
    '          <span class="tk">"trust"</span>: <span class="tv">0.8120</span>,<br>\n'
    '          <span class="tk">"reasons"</span>: <span class="ts">[]</span>,<br>\n'
    '          <span class="tk">"audit_hash"</span>: <span class="ts">"a3f9c2..."</span><br>\n'
    '          <br>\n'
    '          <span class="tc">// CHALLENGE example</span><br>\n'
    '          <span class="tk">"decision"</span>: <span class="tw">"CHALLENGE"</span>,<br>\n'
    '          <span class="tk">"score"</span>: <span class="tv">0.6103</span>,<br>\n'
    '          <span class="tk">"reasons"</span>: <span class="ts">["velocity_spike","country_shift"]</span><br>\n'
    '          <br>\n'
    '          <span class="tc">// BLOCK example</span><br>\n'
    '          <span class="tk">"decision"</span>: <span class="tb">"BLOCK"</span>,<br>\n'
    '          <span class="tk">"score"</span>: <span class="tv">0.8947</span>,<br>\n'
    '          <span class="tk">"reasons"</span>: <span class="ts">["low_trust","velocity_spike","unsafe_country"]</span>\n'
    '        </div>\n'
    '      </div>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<div class="stats">\n'
    '  <div class="stats-inner">\n'
    '    <div class="stat"><div class="stat-n">9</div><div class="stat-l">Risk Signals</div></div>\n'
    '    <div class="stat"><div class="stat-n">3</div><div class="stat-l">Decision Tiers</div></div>\n'
    '    <div class="stat"><div class="stat-n">SHA256</div><div class="stat-l">Audit Chain</div></div>\n'
    '    <div class="stat"><div class="stat-n">0ms</div><div class="stat-l">Extra Latency</div></div>\n'
    '    <div class="stat"><div class="stat-n">100%</div><div class="stat-l">Deterministic</div></div>\n'
    '  </div>\n'
    '</div>\n'
    '\n'
    '<section class="sec" id="governance">\n'
    '  <div class="sec-inner">\n'
    '    <div class="sec-lbl">Risk Engine</div>\n'
    '    <h2>Nine-Signal <span>Governance</span></h2>\n'
    '    <p class="sec-sub">Every AI action is evaluated across nine concurrent risk signals producing an explainable ALLOW, CHALLENGE, or BLOCK decision in real time.</p>\n'
    '    <div class="grid3">\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 01-03</div>\n'
    '        <h3>Velocity Tracking</h3>\n'
    '        <p>Three concurrent time windows — 60 seconds, 5 minutes, 1 hour — detect velocity spikes and unusual action bursts before they escalate.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 04</div>\n'
    '        <h3>Adaptive Trust</h3>\n'
    '        <p>Per-user trust scores decay on bad decisions and recover on good behaviour. Trust is earned, not assumed.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 05</div>\n'
    '        <h3>Amount Scoring</h3>\n'
    '        <p>Logarithmic financial weighting scales risk proportionally across transaction sizes from micro-payments to large transfers.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 06</div>\n'
    '        <h3>Device Risk</h3>\n'
    '        <p>Device-level risk signals from your existing stack feed directly into the scoring model with configurable weighting.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 07</div>\n'
    '        <h3>Behavioural Anomaly</h3>\n'
    '        <p>Anomaly scores from your ML pipeline are ingested and weighted alongside deterministic signals for hybrid scoring.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Signal 08-09</div>\n'
    '        <h3>Geographic Risk</h3>\n'
    '        <p>Country-shift detection and jurisdiction-based risk weighting across 150+ regions with a curated safe-country allowlist.</p>\n'
    '      </div>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<section class="sec" id="compliance">\n'
    '  <div class="sec-inner">\n'
    '    <div class="sec-lbl">EU AI Act</div>\n'
    '    <h2>Compliance <span>Built In</span></h2>\n'
    '    <p class="sec-sub">AILeash is designed around EU AI Act 2024/1689 operational requirements. August 2026 enforcement deadline. Are you ready?</p>\n'
    '    <div class="grid3">\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Art. 13</div>\n'
    '        <h3>Transparency</h3>\n'
    '        <p>Every decision includes a full signal breakdown and regulatory basis. Explainability is not optional — it is built into every API response.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Art. 14</div>\n'
    '        <h3>Human Oversight</h3>\n'
    '        <p>CHALLENGE decisions automatically route to human review. The system enforces oversight — it cannot be bypassed.</p>\n'
    '      </div>\n'
    '      <div class="gcard">\n'
    '        <div class="gcard-ref">Art. 9 + 12</div>\n'
    '        <h3>Audit Integrity</h3>\n'
    '        <p>SHA-256 chained audit trail. Every block links to the previous. Tampering breaks the chain instantly. Forensic-grade evidence retention.</p>\n'
    '      </div>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<section class="sec" id="pricing">\n'
    '  <div class="sec-inner">\n'
    '    <div class="sec-lbl">Pricing</div>\n'
    '    <h2>Simple <span>Pricing</span></h2>\n'
    '    <p class="sec-sub">Start free. Scale as you grow. Same production engine on every plan.</p>\n'
    '    <div class="price-grid">\n'
    '      <div class="price-card">\n'
    '        <div class="price-tier">Free</div>\n'
    '        <div class="price-num">£0</div>\n'
    '        <div class="price-unit">100 governance decisions</div>\n'
    '        <ul class="price-features">\n'
    '          <li>100 API calls</li>\n'
    '          <li>9-signal risk engine</li>\n'
    '          <li>ALLOW / CHALLENGE / BLOCK</li>\n'
    '          <li>Audit trail responses</li>\n'
    '          <li>No credit card required</li>\n'
    '        </ul>\n'
    '        <a href="#signup" class="btn-o" style="display:block;text-align:center">Get Free Key</a>\n'
    '      </div>\n'
    '      <div class="price-card featured">\n'
    '        <div class="price-badge">Most Popular</div>\n'
    '        <div class="price-tier">Professional</div>\n'
    '        <div class="price-num"><sup>£</sup>49</div>\n'
    '        <div class="price-unit">per month — unlimited decisions</div>\n'
    '        <ul class="price-features">\n'
    '          <li>Unlimited API calls</li>\n'
    '          <li>9-signal risk engine</li>\n'
    '          <li>Full audit chain access</li>\n'
    '          <li>Priority throughput</li>\n'
    '          <li>Email support</li>\n'
    '        </ul>\n'
    '        <button class="btn-p" style="width:100%" onclick="upgradeNow()">Upgrade Now</button>\n'
    '      </div>\n'
    '      <div class="price-card">\n'
    '        <div class="price-tier">Enterprise</div>\n'
    '        <div class="price-num">Custom</div>\n'
    '        <div class="price-unit">on-premise + SLA</div>\n'
    '        <ul class="price-features">\n'
    '          <li>Everything in Pro</li>\n'
    '          <li>On-premise deployment</li>\n'
    '          <li>Custom SLA</li>\n'
    '          <li>Multi-tenant isolation</li>\n'
    '          <li>Engineering support</li>\n'
    '        </ul>\n'
    '        <a href="mailto:hello@monop.ai" class="btn-o" style="display:block;text-align:center">Contact Sales</a>\n'
    '      </div>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<section class="sec" id="api">\n'
    '  <div class="sec-inner">\n'
    '    <div class="sec-lbl">API Reference</div>\n'
    '    <h2>One Endpoint. <span>Full Governance.</span></h2>\n'
    '    <p class="sec-sub">POST an event. Receive a decision. Integrates into any stack in under five minutes.</p>\n'
    '    <div style="background:#0a0a0a;border-radius:8px;overflow:hidden;margin-top:24px">\n'
    '      <div style="background:#1a1a1a;padding:12px 24px;font-family:var(--mono);font-size:11px;color:#666;letter-spacing:2px;text-transform:uppercase;border-bottom:1px solid #222">POST /api/govern — Request</div>\n'
    '      <pre style="padding:24px;font-family:var(--mono);font-size:13px;color:#ccc;line-height:2;overflow-x:auto">curl -X POST https://sebbi.pro/api/govern \\\n'
    '  -H "Authorization: Bearer al_live_..." \\\n'
    '  -H "Content-Type: application/json" \\\n'
    '  -d \'{\n'
    '    "user_id":    "user_001",\n'
    '    "action":     "wire_transfer",\n'
    '    "amount":     2500,\n'
    '    "country":    "UK",\n'
    '    "device_id":  "mobile_chrome",\n'
    '    "device_risk": 0.2,\n'
    '    "anomaly":    0.1\n'
    '  }\'</pre>\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<section class="signup-sec" id="signup">\n'
    '  <div class="signup-inner">\n'
    '    <div class="sec-lbl">Get Started</div>\n'
    '    <h2 style="font-size:clamp(32px,4vw,48px)">Free API <span>Key</span></h2>\n'
    '    <p style="color:var(--muted);margin-bottom:32px;font-size:16px;line-height:1.7">100 free governance decisions. No card required. Same engine as paid plans.</p>\n'
    '    <div class="fg">\n'
    '      <label>Email Address</label>\n'
    '      <input type="email" id="signup-email" placeholder="you@company.com">\n'
    '    </div>\n'
    '    <button class="btn-p btn-full" id="signup-btn" onclick="getKey()">Generate Free API Key</button>\n'
    '    <div class="key-result" id="key-result"></div>\n'
    '    <div class="error-box" id="error-box"></div>\n'
    '    <div class="stripe-notice" id="stripe-notice">\n'
    '      Stripe billing is not yet configured on this deployment.\n'
    '      Set <code>STRIPE_SECRET</code> in your Railway environment variables to enable paid plans.\n'
    '    </div>\n'
    '  </div>\n'
    '</section>\n'
    '\n'
    '<footer>\n'
    '  AILeash <span>v\n'
) + VERSION + """</span> — Enterprise AI Governance — Built by Monop, Blyth UK
</footer>

<script>
async function getKey() {
  const email = document.getElementById('signup-email').value.trim();
  const btn   = document.getElementById('signup-btn');
  const result = document.getElementById('key-result');
  const errBox = document.getElementById('error-box');

  result.classList.remove('visible');
  errBox.classList.remove('visible');

  if (!email || !email.includes('@')) {
    errBox.textContent = 'Please enter a valid email address.';
    errBox.classList.add('visible');
    return;
  }

  btn.innerHTML = '<span class="spin"></span> Generating...';
  btn.disabled = true;

  try {
    const r = await fetch('/api/keys', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email})
    });
    const d = await r.json();
    if (d.key) {
      result.innerHTML = '&#10003; KEY CREATED<br><br>' + d.key + '<br><br>100 free governance decisions included.<br>Use header: Authorization: Bearer ' + d.key;
      result.classList.add('visible');
    } else {
      errBox.textContent = d.error || 'Key generation failed.';
      errBox.classList.add('visible');
    }
  } catch(e) {
    errBox.textContent = 'Cannot reach server.';
    errBox.classList.add('visible');
  }

  btn.innerHTML = 'Generate Free API Key';
  btn.disabled = false;
}

async function upgradeNow() {
  const email = document.getElementById('signup-email').value.trim() || prompt('Enter your email to upgrade:');
  if (!email) return;

  try {
    const r = await fetch('/create-checkout', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email})
    });
    const d = await r.json();
    if (d.checkout_url) {
      window.location.href = d.checkout_url;
    } else {
      document.getElementById('stripe-notice').classList.add('visible');
      document.getElementById('stripe-notice').scrollIntoView({behavior:'smooth',block:'center'});
    }
  } catch(e) {
    document.getElementById('stripe-notice').classList.add('visible');
  }
}
</script>
</body>
</html>"""

# ============================================================================
# HTTP SERVER
# ============================================================================
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
                keys  = _conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                audits = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_json(self, {"api_keys": keys, "audit_blocks": audits, "version": VERSION})

        else:
            send_json(self, {"error": "not_found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)

        # GOVERN
        if path == "/api/govern":
            api_key = get_api_key(self)
            try:
                result, status = govern(data, api_key if api_key else None)
                send_json(self, result, status)
            except ValueError as e:
                send_json(self, {"error": str(e)}, 400)
            except Exception as e:
                send_json(self, {"error": "internal_error", "detail": str(e)}, 500)

        # KEY GENERATION
        elif path == "/api/keys":
            email = str(data.get("email", "")).strip().lower()
            key, err = create_api_key(email)
            if err:
                msgs = {
                    "invalid_email": "Please enter a valid email address.",
                    "email_exists":  "A key already exists for this email address."
                }
                send_json(self, {"error": msgs.get(err, err)}, 400)
                return
            send_json(self, {
                "key":     key,
                "email":   email,
                "plan":    "free",
                "quota":   FREE_QUOTA,
                "message": f"{FREE_QUOTA} free governance decisions included."
            })

        # STRIPE CHECKOUT
        elif path == "/create-checkout":
            email = str(data.get("email", "")).strip().lower()
            if not email or "@" not in email:
                send_json(self, {"error": "invalid_email"}, 400)
                return

            if not STRIPE_SECRET:
                send_json(self, {
                    "error": "stripe_not_configured",
                    "message": "Set STRIPE_SECRET in Railway environment variables."
                }, 503)
                return

            # Auto-setup if price not ready
            if not STRIPE_PRICE_ID:
                setup_stripe()

            if not STRIPE_PRICE_ID:
                send_json(self, {
                    "error": "stripe_setup_failed",
                    "message": "Stripe could not auto-configure. Check STRIPE_SECRET is valid."
                }, 503)
                return

            session = stripe_call("POST", "/checkout/sessions", {
                "mode": "subscription",
                "customer_email": email,
                "success_url": f"{HOST}/?success=true",
                "cancel_url":  f"{HOST}/?cancel=true",
                "line_items[0][price]":    STRIPE_PRICE_ID,
                "line_items[0][quantity]": "1"
            })

            if not session or "url" not in session:
                send_json(self, {
                    "error": "checkout_failed",
                    "detail": str(session)
                }, 500)
                return

            send_json(self, {"checkout_url": session["url"]})

        else:
            send_json(self, {"error": "not_found"}, 404)

# ============================================================================
# MAIN
# ============================================================================
if __name__ == "__main__":
    print(f"AILeash v{VERSION} starting on port {PORT}", flush=True)
    setup_stripe()
    server = ThreadedServer(("0.0.0.0", PORT), Handler)
    print(f"Ready.", flush=True)
    server.serve_forever()
