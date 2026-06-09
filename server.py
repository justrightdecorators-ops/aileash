import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

STRIPE_SECRET = os.environ.get("STRIPE_SECRET", "")
PORT = int(os.environ.get("PORT", 8080))
DB = "aileash.db"
VERSION = "2.1.0"
HOST = os.environ.get("HOST", "https://sebbi.pro")
SAFE_COUNTRIES = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA = 100

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
    url = "https://stripe.com" + endpoint
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
WINDOW_5M = defaultdict(deque)
WINDOW_1H = defaultdict(deque)

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
        "5m": len(WINDOW_5M[uid]),
        "1h": len(WINDOW_1H[uid])
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
