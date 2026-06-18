import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

STRIPE_SECRET  = os.environ.get("STRIPE_SECRET", "")
BREVO_API_KEY  = os.environ.get("BREVO_API_KEY", "")
PORT           = int(os.environ.get("PORT", 8080))
DB             = "aileash.db"
VERSION        = "4.1.0"
HOST           = os.environ.get("HOST", "https://sebbi.pro")
SAFE_COUNTRIES = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS= {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA     = 100

RATE_LIMIT_PER_MIN  = 60
RATE_LIMIT_PER_HOUR = 1000
GLOBAL_RATE_PER_SEC = 200

OWNER_NAME  = "Justin Antony Dobson"
OWNER_TITLE = "Owner, Monop Content"
OWNER_EMAIL = "justin@monopcontent.com"
OWNER_PHONE = "07908 269428"

STRIPE_PRICE_ID_AILEASH  = ""
STRIPE_PRICE_ID_GUARDIAN = ""
_db_lock  = threading.Lock()
_load_lock= threading.Lock()
_req_times= deque()
_load_warn= False
_key_windows = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()

# ============================================================================
# DATABASE
# ============================================================================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT, org TEXT,
        org_type TEXT, product TEXT DEFAULT 'aileash', devices INTEGER DEFAULT 1,
        stripe_customer TEXT, stripe_sub TEXT, actions_used INTEGER DEFAULT 0,
        created REAL, active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 100, plan_type TEXT DEFAULT 'free')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS load_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, rps REAL, note TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS contact_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, name TEXT,
        email TEXT, phone TEXT, org TEXT, message TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key_email ON api_keys(email)")
    conn.commit()
    return conn

_conn = get_conn()

# ============================================================================
# LOAD TRACKING
# ============================================================================
def track_request():
    global _load_warn
    t = time.time()
    with _load_lock:
        _req_times.append(t)
        cutoff = t - 1.0
        while _req_times and _req_times[0] < cutoff:
            _req_times.popleft()
        rps = len(_req_times)
        if rps > GLOBAL_RATE_PER_SEC and not _load_warn:
            _load_warn = True
            try:
                _conn.execute("INSERT INTO load_log(ts,rps,note) VALUES(?,?,?)", (t,rps,"THROTTLE_ENGAGED"))
                _conn.commit()
            except Exception: pass
            print(f"LOAD WARNING: {rps} req/s", flush=True)
        elif rps < GLOBAL_RATE_PER_SEC * 0.7 and _load_warn:
            _load_warn = False
            print(f"LOAD CLEAR: {rps} req/s", flush=True)
        return rps

def is_overloaded():
    with _load_lock: return _load_warn

def get_rps():
    t = time.time()
    with _load_lock: return sum(1 for x in _req_times if x >= t - 1.0)

# ============================================================================
# RATE LIMITING
# ============================================================================
def check_rate_limit(key):
    t = time.time()
    with _key_lock:
        w = _key_windows[key]
        while w["min"]  and w["min"][0]  < t - 60:   w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600: w["hour"].popleft()
        if len(w["min"])  >= RATE_LIMIT_PER_MIN:
            return False, "rate_limit_minute", f"Max {RATE_LIMIT_PER_MIN} requests/minute."
        if len(w["hour"]) >= RATE_LIMIT_PER_HOUR:
            return False, "rate_limit_hour", f"Max {RATE_LIMIT_PER_HOUR} requests/hour."
        w["min"].append(t); w["hour"].append(t)
        return True, None, None

# ============================================================================
# EMAIL — BREVO
# ============================================================================
def send_email(to_email, to_name, subject, html_body):
    if not BREVO_API_KEY:
        print(f"EMAIL SKIP (no BREVO_API_KEY): to={to_email}", flush=True)
        return False
    payload = json.dumps({
        "sender":   {"name": "AILeash Platform", "email": "noreply@monopcontent.com"},
        "to":       [{"email": to_email, "name": to_name}],
        "subject":  subject,
        "htmlContent": html_body
    }).encode()
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key":      BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept":       "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"EMAIL SENT: {to_email}", flush=True)
            return True
    except Exception as e:
        print(f"EMAIL ERROR: {e}", flush=True)
        return False

def send_welcome_email(name, email, product, api_key, devices, monthly):
    product_name = "AILeash Guardian" if product == "guardian" else "AILeash"
    endpoint     = f"{HOST}/api/govern"
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>
body{{font-family:'DM Sans',Arial,sans-serif;background:#f5f7fa;margin:0;padding:0}}
.wrap{{max-width:580px;margin:40px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)}}
.hdr{{background:#0a0f1e;padding:32px 36px;border-bottom:4px solid #c9a84c}}
.hdr-logo{{font-size:22px;color:#fff;font-weight:900;letter-spacing:1px}}.hdr-logo span{{color:#c9a84c}}
.hdr-sub{{font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px;font-family:monospace;letter-spacing:2px;text-transform:uppercase}}
.body{{padding:36px}}
.greeting{{font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:8px}}
.intro{{font-size:14px;color:#64748b;line-height:1.7;margin-bottom:28px}}
.key-box{{background:#0a0f1e;border-radius:6px;padding:20px;margin-bottom:24px}}
.key-lbl{{font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}}
.key-val{{font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all;line-height:1.6}}
.billing{{background:#f5f7fa;border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:24px;font-size:13px;color:#64748b;line-height:1.7}}
.billing strong{{color:#0a0f1e}}
.code-box{{background:#0a0f1e;border-radius:6px;padding:20px;margin-bottom:24px}}
.code-lbl{{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}}
.code{{font-family:monospace;font-size:12px;color:#ccc;line-height:2}}
.code em{{color:#79b8ff;font-style:normal}}
.code .gr{{color:#00ff88}}
.footer-txt{{font-size:12px;color:#94a3b8;text-align:center;margin-top:28px;line-height:1.7}}
.footer-txt a{{color:#c9a84c;text-decoration:none}}
</style></head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-logo">AILeash <span>Platform</span></div>
    <div class="hdr-sub">{product_name} &mdash; Key Created</div>
  </div>
  <div class="body">
    <div class="greeting">Welcome{', ' + name.split()[0] if name.strip() else ''}.</div>
    <p class="intro">Your {product_name} API key is ready. You have 100 free decisions to start &mdash; no card required. After your trial, billing is &pound;{monthly:.2f}/month for {devices} device{'s' if devices != 1 else ''} via Stripe.</p>
    <div class="key-box">
      <div class="key-lbl">Your API Key &mdash; Save This Now</div>
      <div class="key-val">{api_key}</div>
    </div>
    <div class="billing">
      <strong>Billing summary</strong><br>
      Product: {product_name}<br>
      Devices: {devices}<br>
      Monthly total: &pound;{monthly:.2f}<br>
      Free decisions remaining: 100
    </div>
    <div class="code-box">
      <div class="code-lbl">Quick Start &mdash; curl</div>
      <div class="code">
        <em>POST</em> {endpoint}<br>
        Authorization: Bearer <em>{api_key[:20]}...</em><br>
        Content-Type: application/json<br><br>
        <span class="gr">Response: ALLOW / CHALLENGE / BLOCK</span><br>
        + SHA-256 audit hash on every decision
      </div>
    </div>
    <p class="intro" style="margin-bottom:8px">Questions? Reply to this email or contact us directly:</p>
    <p class="intro"><strong>{OWNER_NAME}</strong> &mdash; {OWNER_TITLE}<br>
    <a href="mailto:{OWNER_EMAIL}" style="color:#c9a84c">{OWNER_EMAIL}</a> &mdash; {OWNER_PHONE}</p>
  </div>
  <div class="footer-txt">
    &copy; 2026 Monop Content &middot; Blyth, UK<br>
    <a href="{HOST}">sebbi.pro</a> &mdash; EU AI Act &middot; Online Safety Act &middot; ICO Children's Code
  </div>
</div>
</body></html>"""
    send_email(email, name, f"Your {product_name} API Key", html)

def send_contact_notification(name, email, phone, org, message):
    html = f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;padding:20px;color:#333">
<h2 style="color:#0a0f1e">New Contact Form Submission</h2>
<p><strong>Name:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
<p><strong>Phone:</strong> {phone}</p>
<p><strong>Organisation:</strong> {org}</p>
<p><strong>Message:</strong><br>{message}</p>
<hr><p style="color:#999;font-size:12px">AILeash Platform &mdash; sebbi.pro</p>
</body></html>"""
    send_email(OWNER_EMAIL, OWNER_NAME, f"New Contact: {name}", html)

# ============================================================================
# STRIPE
# ============================================================================
def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET: return None
    url  = "https://api.stripe.com/v1" + endpoint
    hdrs = {"Authorization": "Bearer " + STRIPE_SECRET, "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read())
        except: return None
    except Exception as e:
        print(f"Stripe error: {e}", flush=True); return None

def _make_stripe_product(name, desc):
    p = stripe_call("POST", "/products", {"name": name, "description": desc})
    if not p or "id" not in p: return None
    pr = stripe_call("POST", "/prices", {"product": p["id"], "currency": "gbp", "unit_amount": 50, "recurring[interval]": "month"})
    return pr["id"] if pr and "id" in pr else None

def setup_stripe():
    global STRIPE_PRICE_ID_AILEASH, STRIPE_PRICE_ID_GUARDIAN
    if not STRIPE_SECRET:
        print("WARNING: No STRIPE_SECRET. Billing disabled.", flush=True); return
    with _db_lock:
        ra = _conn.execute("SELECT v FROM config WHERE k='stripe_price_aileash'").fetchone()
        rg = _conn.execute("SELECT v FROM config WHERE k='stripe_price_guardian'").fetchone()
    if ra and ra[0]:
        STRIPE_PRICE_ID_AILEASH = ra[0]
        print(f"Stripe AILeash: {STRIPE_PRICE_ID_AILEASH}", flush=True)
    else:
        pid = _make_stripe_product("AILeash", "AI governance. 50p per device per month.")
        if pid:
            STRIPE_PRICE_ID_AILEASH = pid
            with _db_lock:
                _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_aileash',?)", (pid,))
                _conn.commit()
            print(f"Stripe AILeash created: {pid}", flush=True)
    if rg and rg[0]:
        STRIPE_PRICE_ID_GUARDIAN = rg[0]
        print(f"Stripe Guardian: {STRIPE_PRICE_ID_GUARDIAN}", flush=True)
    else:
        pid = _make_stripe_product("AILeash Guardian", "Child safety governance. 50p per device per month.")
        if pid:
            STRIPE_PRICE_ID_GUARDIAN = pid
            with _db_lock:
                _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('stripe_price_guardian',?)", (pid,))
                _conn.commit()
            print(f"Stripe Guardian created: {pid}", flush=True)

# ============================================================================
# KEY MANAGEMENT
# ============================================================================
def create_api_key(email, phone="", name="", org="", org_type="", product="aileash", devices=1):
    email = str(email).strip().lower()
    if not email or "@" not in email: return None, "invalid_email"
    key = ("ag_live_" if product == "guardian" else "al_live_") + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("""INSERT INTO api_keys
                (key,email,phone,name,org,org_type,product,devices,stripe_customer,stripe_sub,
                 actions_used,created,active,is_paid,free_quota,plan_type)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key,email,phone,name,org,org_type,product,devices,"","",0,time.time(),1,0,FREE_QUOTA,"free"))
            _conn.commit()
        except sqlite3.IntegrityError:
            return None, "email_exists"
    return key, None

def get_key_info(key):
    with _db_lock:
        return _conn.execute(
            "SELECT email,actions_used,active,is_paid,free_quota,plan_type,product FROM api_keys WHERE key=?", (key,)
        ).fetchone()

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?", (key,))
        _conn.commit()

# ============================================================================
# VELOCITY / TRUST / ENGINE
# ============================================================================
WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now():  return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def prune(q,s):
    c=now()-s
    while q and q[0]<c: q.popleft()

def update_windows(uid):
    t=now()
    for q in [WINDOW_60S[uid],WINDOW_5M[uid],WINDOW_1H[uid]]: q.append(t)
    prune(WINDOW_60S[uid],60); prune(WINDOW_5M[uid],300); prune(WINDOW_1H[uid],3600)

def velocity(uid):
    return {"60s":len(WINDOW_60S[uid]),"5m":len(WINDOW_5M[uid]),"1h":len(WINDOW_1H[uid])}

def load_user(uid):
    with _db_lock:
        row=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?",(uid,)).fetchone()
    return {"trust":row[0],"last_country":row[1]} if row else {"trust":0.5,"last_country":None}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute("""INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country""",
            (uid,trust,country))
        _conn.commit()

def compute_score(s):
    score  = (1-s["trust"])*0.30
    score += min(s["v60"]/20,1)*0.15
    score += min(s["v5m"]/50,1)*0.10
    score += min(s["v1h"]/200,1)*0.10
    score += min(math.log1p(s["amount"])/math.log1p(10000),1)*0.15
    score += s["device_risk"]*0.10
    score += s["anomaly"]*0.10
    if s["country_shift"]:  score+=0.10
    if s["unsafe_country"]: score+=0.10
    return clamp(score)

def decide(score):
    if score<0.35: return "ALLOW"
    if score<0.70: return "CHALLENGE"
    return "BLOCK"

def update_trust(trust,decision):
    if decision=="ALLOW":       trust+=(1-trust)*0.01
    elif decision=="CHALLENGE": trust-=trust*0.02
    elif decision=="BLOCK":     trust-=trust*0.08
    return clamp(trust,0.05,1.0)

def explain(s):
    r=[]
    if s["trust"]<0.4:       r.append("low_trust")
    if s["v60"]>10:          r.append("velocity_spike")
    if s["amount"]>500:      r.append("high_amount")
    if s["device_risk"]>0.5: r.append("risky_device")
    if s["country_shift"]:   r.append("country_shift")
    if s["unsafe_country"]:  r.append("unsafe_country")
    if s["anomaly"]>0.5:     r.append("behaviour_anomaly")
    return r

def chain_tip():
    with _db_lock:
        row=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event,result,ts):
    prev=chain_tip()
    h=sha({"prev_hash":prev,"ts":ts,"event":event,"result":result})
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:
        rows=_conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows: return {"valid":True,"blocks":0,"message":"Empty chain"}
    prev="GENESIS"
    for i,row in enumerate(rows):
        payload={"prev_hash":row[2],"ts":row[4],"event":json.loads(row[0]),"result":json.loads(row[1])}
        if sha(payload)!=row[3] or row[2]!=prev:
            return {"valid":False,"broken_at_block":i,"message":f"Chain broken at block {i}"}
        prev=row[3]
    return {"valid":True,"blocks":len(rows),"message":"Chain intact"}

def govern(event,api_key=None):
    missing=REQUIRED_FIELDS-event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    if api_key:
        ok,ec,em=check_rate_limit(api_key)
        if not ok: return {"error":ec,"message":em},429
        ki=get_key_info(api_key)
        if not ki: return {"error":"invalid_api_key"},401
        email,actions_used,active,is_paid,free_quota,plan_type,product=ki
        if not active: return {"error":"account_inactive"},403
        if not is_paid and actions_used>=free_quota:
            return {"error":"quota_exceeded","message":f"Free quota of {free_quota} reached. Upgrade at {HOST}/#pricing"},429
    ts=now(); state=load_user(event["user_id"]); update_windows(event["user_id"]); v=velocity(event["user_id"])
    signals={"trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],
             "amount":float(event.get("amount",0)),"device_risk":float(event.get("device_risk",0)),
             "anomaly":float(event.get("anomaly",0)),
             "country_shift":state["last_country"] is not None and state["last_country"]!=event["country"],
             "unsafe_country":event["country"] not in SAFE_COUNTRIES}
    score=compute_score(signals); decision=decide(score); reasons=explain(signals)
    trust=update_trust(state["trust"],decision); save_user(event["user_id"],trust,event["country"])
    result={"decision":decision,"score":round(score,4),"trust":round(trust,4),
            "reasons":reasons,"version":VERSION,"timestamp":ts}
    result["audit_hash"]=append_audit(event,result,ts)
    if api_key: increment_usage(api_key)
    return result,200

# ============================================================================
# HTTP HELPERS
# ============================================================================
def send_json(h,data,status=200):
    body=json.dumps(data,indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.send_header("Content-Length",str(len(body)))
    h.send_header("Access-Control-Allow-Origin","*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h,html,status=200):
    body=html.encode()
    h.send_response(status)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Content-Length",str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    length=int(h.headers.get("Content-Length",0))
    if length:
        try:    return json.loads(h.rfile.read(length))
        except: return {}
    return {}

def get_api_key(h):
    auth=h.headers.get("Authorization","")
    if auth.startswith("Bearer "): return auth[7:]
    return h.headers.get("X-API-Key","").strip()

# ============================================================================
# PAGES
# ============================================================================
COMMON_CSS = "\n".join([
":root{--navy:#0a0f1e;--navy2:#111827;--gold:#c9a84c;--gold2:#e8c96a;--red:#cc0000;--green:#00875a;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--text:#1a202c;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}",
"*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}",
"body{background:var(--white);color:var(--text);font-family:var(--sans);overflow-x:hidden}",
"nav{position:fixed;top:0;left:0;right:0;z-index:100;background:var(--navy);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between}",
".nav-logo{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900}.nav-logo span{color:var(--gold)}",
".nav-links{display:flex;gap:24px;align-items:center}",
".nav-links a{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}",
".nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 20px;font-weight:700!important;border-radius:4px}",
"h2{font-family:var(--display);font-size:clamp(32px,3.5vw,50px);font-weight:900;margin-bottom:14px;line-height:1.1}",
"h2 em{color:var(--gold);font-style:normal}",
".slbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;opacity:.4}",
".sec-sub{font-size:15px;color:var(--muted);max-width:580px;line-height:1.7;margin-bottom:44px}",
".btn-gold{background:var(--gold);color:var(--navy);padding:15px 30px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}",
".btn-gold:hover{background:var(--gold2);transform:translateY(-2px)}",
".btn-red{background:var(--red);color:var(--white);padding:15px 30px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}",
".btn-red:hover{background:#aa0000;transform:translateY(-2px)}",
".btn-ghost{background:transparent;color:var(--white);padding:15px 30px;border:1px solid rgba(255,255,255,0.2);font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}",
".btn-ghost:hover{border-color:var(--gold);color:var(--gold)}",
".fg{margin-bottom:12px}",
".fg label{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}",
".fg input,.fg select,.fg textarea{width:100%;background:var(--off);border:2px solid var(--border);color:var(--text);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;transition:border-color .2s;border-radius:4px}",
".fg input:focus,.fg select:focus,.fg textarea:focus{border-color:var(--navy)}",
".fg input::placeholder,.fg textarea::placeholder{color:#bbb}",
".fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}",
".msg-err{display:none;color:var(--red);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}",
".msg-err.show{display:block}",
".msg-ok{display:none;color:var(--green);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#f0fff8;border-radius:4px;border:1px solid #bbf7d0}",
".msg-ok.show{display:block}",
"footer{background:var(--navy2);padding:52px 48px;border-top:1px solid rgba(255,255,255,0.04)}",
".foot-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;gap:40px}",
".foot-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;margin-bottom:4px}",
".foot-logo span{color:var(--gold)}",
".foot-tag{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.15);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}",
".foot-desc{font-size:12px;color:rgba(255,255,255,0.18);line-height:1.7}",
".foot-col h4{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);text-transform:uppercase;margin-bottom:10px}",
".foot-col a{display:block;color:rgba(255,255,255,0.18);text-decoration:none;font-size:12px;margin-bottom:6px;transition:color .2s}",
".foot-col a:hover{color:var(--white)}",
".foot-bottom{max-width:1200px;margin:32px auto 0;padding-top:18px;border-top:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;font-size:10px;color:rgba(255,255,255,0.12);font-family:var(--mono)}",
"@media(max-width:900px){nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}footer{padding:40px 20px}.foot-inner{grid-template-columns:1fr}.foot-bottom{flex-direction:column;gap:6px}}",
])

COMMON_FONTS = '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">'

COMMON_NAV = """<nav>
  <div class="nav-logo">AILeash <span>Platform</span></div>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/#governance">Governance</a>
    <a href="/#guardian">Guardian</a>
    <a href="/scan">AI Act Scanner</a>
    <a href="/contact">Contact</a>
    <a href="/#signup" class="nav-cta">Get Started</a>
  </div>
</nav>"""

COMMON_FOOTER = f"""<footer>
  <div class="foot-inner">
    <div>
      <div class="foot-logo">AILeash <span>Platform</span></div>
      <div class="foot-tag">Monop Content &middot; Blyth, UK</div>
      <p class="foot-desc">AI governance and child safety infrastructure. AILeash and AILeash Guardian. Same SHA-256 engine. 50p per device per month.</p>
    </div>
    <div class="foot-col"><h4>Products</h4><a href="/#governance">AILeash</a><a href="/#guardian">Guardian</a><a href="/scan">AI Act Scanner</a><a href="/#pricing">Pricing</a></div>
    <div class="foot-col"><h4>Company</h4><a href="/contact">Contact</a><a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a><a href="#">Privacy Policy</a><a href="#">Terms of Service</a></div>
    <div class="foot-col"><h4>Get In Touch</h4><a href="mailto:{OWNER_EMAIL}">{OWNER_EMAIL}</a><a href="tel:{OWNER_PHONE.replace(' ','')}">{OWNER_PHONE}</a><a href="/#signup">Get API Key</a></div>
  </div>
  <div class="foot-bottom">
    <span>&copy; 2026 Monop Content &middot; {OWNER_NAME} &middot; Blyth, UK &middot; v{VERSION}</span>
    <span>EU AI Act &middot; Online Safety Act &middot; ICO Children&apos;s Code &middot; DSA Compliant</span>
  </div>
</footer>"""

# ============================================================================
# MAIN LANDING PAGE
# ============================================================================
LANDING = "\n".join([
"<!DOCTYPE html>",
'<html lang="en"><head><meta charset="UTF-8">',
'<meta name="viewport" content="width=device-width,initial-scale=1.0">',
"<title>AILeash Platform &mdash; AI Governance &amp; Child Safety</title>",
'<meta name="description" content="AILeash: Enterprise AI governance. AILeash Guardian: Child safety. 50p per device per month. Built in Blyth, UK.">',
COMMON_FONTS,
"<style>",
COMMON_CSS,
".kdot{display:inline-block;width:7px;height:7px;background:var(--red);border-radius:50%;animation:blink 1.5s infinite;margin-right:8px;vertical-align:middle}",
"@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.4)}}",
".ktext{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;vertical-align:middle}",
".alert-bar{background:var(--red);padding:11px 48px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--white);letter-spacing:1px;text-transform:uppercase;margin-top:68px}",
".alert-bar strong{color:var(--gold2)}",
".hero{background:var(--navy);padding:80px 48px 100px;position:relative;overflow:hidden}",
".hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 15% 60%,rgba(201,168,76,0.06) 0%,transparent 55%)}",
".hero-inner{max-width:1200px;margin:0 auto;position:relative;z-index:1;text-align:center}",
"h1{font-family:var(--display);font-size:clamp(44px,5vw,72px);line-height:1.05;color:var(--white);font-weight:900;margin:16px 0 20px}",
"h1 em{color:var(--gold);font-style:normal}",
".hero-sub{font-size:18px;color:rgba(255,255,255,0.5);line-height:1.75;max-width:620px;margin:0 auto 40px}",
".product-cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:880px;margin:0 auto 48px}",
".pc{border-radius:8px;padding:28px;text-align:left;position:relative;overflow:hidden;cursor:pointer;transition:all .2s}",
".pc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}",
".pc-leash{background:rgba(201,168,76,0.07);border:1px solid rgba(201,168,76,0.2)}.pc-leash::before{background:var(--gold)}",
".pc-guardian{background:rgba(204,0,0,0.07);border:1px solid rgba(204,0,0,0.2)}.pc-guardian::before{background:var(--red)}",
".pc-leash:hover{border-color:rgba(201,168,76,0.5)}.pc-guardian:hover{border-color:rgba(204,0,0,0.5)}",
".pc-badge{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}",
".pc-leash .pc-badge{color:var(--gold)}.pc-guardian .pc-badge{color:#ff6b6b}",
".pc h3{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900;margin-bottom:6px}",
".pc p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.6;margin-bottom:12px}",
".pc-tags{display:flex;flex-wrap:wrap;gap:5px}",
".ptag{font-family:var(--mono);font-size:9px;padding:2px 8px;border-radius:2px}",
".pc-leash .ptag{background:rgba(201,168,76,0.1);color:var(--gold);border:1px solid rgba(201,168,76,0.2)}",
".pc-guardian .ptag{background:rgba(204,0,0,0.1);color:#ff6b6b;border:1px solid rgba(204,0,0,0.2)}",
".hero-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}",
".divider{height:4px;background:linear-gradient(90deg,var(--navy) 0%,var(--gold) 50%,var(--red) 100%)}",
".stats-strip{background:var(--navy)}",
".stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}",
".stat{padding:28px 20px;border-right:1px solid rgba(255,255,255,0.05);text-align:center}.stat:last-child{border:none}",
".stat-n{font-family:var(--display);font-size:36px;color:var(--gold);font-weight:900}",
".stat-l{font-size:10px;color:rgba(255,255,255,0.25);margin-top:4px;letter-spacing:1px;text-transform:uppercase}",
".sec{padding:80px 48px;border-bottom:1px solid var(--border)}",
".sec-inner{max-width:1200px;margin:0 auto}",
".two-col{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start}",
".feature-block{margin-bottom:36px}",
".fb-icon{font-size:24px;margin-bottom:8px}",
".fb-lbl{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:5px}",
".feature-block h3{font-family:var(--display);font-size:19px;font-weight:800;margin-bottom:6px;color:var(--navy)}",
".feature-block p{font-size:13px;color:var(--muted);line-height:1.65}",
".signal-list{display:flex;flex-direction:column;gap:8px}",
".sig{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--off);border:1px solid var(--border);border-radius:4px}",
".sig-bar-wrap{width:80px;height:4px;background:var(--border);border-radius:2px;flex-shrink:0}",
".sig-bar{height:100%;border-radius:2px;background:var(--gold)}",
".sig-name{font-size:12px;color:var(--text);flex:1}",
".sig-pct{font-family:var(--mono);font-size:11px;color:var(--gold);font-weight:600;flex-shrink:0}",
".dec-flow{display:flex;flex-direction:column;gap:8px;margin-top:20px}",
".df{padding:14px 16px;border-radius:4px}",
".df-allow{background:rgba(0,135,90,0.06);border:1px solid rgba(0,135,90,0.2)}",
".df-challenge{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2)}",
".df-block{background:rgba(204,0,0,0.06);border:1px solid rgba(204,0,0,0.2)}",
".df-v{font-family:var(--display);font-size:18px;font-weight:900;margin-bottom:3px}",
".df-allow .df-v{color:var(--green)}.df-challenge .df-v{color:#b45309}.df-block .df-v{color:var(--red)}",
".df-d{font-size:12px;color:var(--muted);line-height:1.5}",
".df-t{font-family:var(--mono);font-size:9px;margin-top:4px;color:var(--muted);opacity:.5}",
".guardian-sec{background:var(--navy2);padding:80px 48px;border-top:4px solid var(--red)}",
".guardian-inner{max-width:1200px;margin:0 auto}",
".threat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.03);margin-top:36px}",
".tc{background:var(--navy);padding:24px;position:relative}",
".tc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}",
".tc-r::before{background:var(--red)}.tc-g::before{background:var(--gold)}.tc-n::before{background:#3b82f6}",
".tc-gr::before{background:var(--green)}.tc-b::before{background:#7c3aed}.tc-p::before{background:#ec4899}",
".tc-icon{font-size:24px;margin-bottom:8px}",
".tc-lbl{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:5px}",
".tc h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:6px;color:var(--white)}",
".tc p{font-size:12px;color:rgba(255,255,255,0.35);line-height:1.6}",
".tc-tags{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px}",
".ttag{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);padding:2px 7px;font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);border-radius:2px}",
".compliance-sec{padding:80px 48px;background:var(--off)}",
".comp-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:36px}",
".comp-card{background:var(--white);border:1px solid var(--border);padding:24px;border-left:4px solid var(--navy)}",
".comp-act{font-family:var(--mono);font-size:9px;color:var(--navy);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;opacity:.4}",
".comp-card h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:6px;color:var(--navy)}",
".comp-card p{font-size:12px;color:var(--muted);line-height:1.65}",
".checks{margin-top:10px;display:flex;flex-direction:column;gap:4px}",
".chk{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--muted)}",
".chk::before{content:'OK';color:var(--green);font-weight:700;flex-shrink:0;font-family:var(--mono);font-size:9px}",
".fair-sec{padding:80px 48px;border-bottom:1px solid var(--border)}",
".fair-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:36px}",
".fair-card{border:1px solid var(--border);padding:24px;border-top:3px solid var(--navy)}",
".fair-card h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:8px;color:var(--navy)}",
".fair-card p{font-size:12px;color:var(--muted);line-height:1.65}",
".fair-limit{font-family:var(--mono);font-size:11px;color:var(--gold);margin-top:10px;padding:8px 10px;background:var(--off);border-radius:4px;line-height:1.8}",
".pricing-sec{padding:80px 48px;background:var(--navy);border-top:4px solid var(--gold)}",
".pricing-inner{max-width:880px;margin:0 auto;text-align:center}",
".price-cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:44px}",
".price-card{border-radius:8px;padding:36px 28px;text-align:center}",
".price-card.al{background:rgba(201,168,76,0.07);border:2px solid var(--gold)}",
".price-card.gu{background:rgba(204,0,0,0.07);border:2px solid var(--red)}",
".price-product{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}",
".al .price-product{color:var(--gold)}.gu .price-product{color:#ff6b6b}",
".price-big{font-family:var(--display);font-size:64px;font-weight:900;line-height:1;margin-bottom:4px}",
".al .price-big{color:var(--gold)}.gu .price-big{color:#ff6b6b}",
".price-big sup{font-size:28px;vertical-align:super}",
".price-per{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.35);margin-bottom:20px}",
".price-example{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.5);background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:4px;padding:10px;margin-bottom:20px;line-height:1.8;text-align:left}",
".price-example strong{color:var(--white)}",
".price-feats{text-align:left;margin-bottom:24px;display:flex;flex-direction:column;gap:8px}",
".pf{display:flex;align-items:center;gap:7px;font-size:12px;color:rgba(255,255,255,0.55);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}",
".pf::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;flex-shrink:0}",
".al .pf::before{color:var(--gold)}.gu .pf::before{color:#ff6b6b}",
".price-note{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.18);margin-top:12px;letter-spacing:1px}",
".signup-sec{padding:80px 48px;background:var(--white);border-top:4px solid var(--gold)}",
".signup-inner{max-width:580px;margin:0 auto}",
".product-tabs{display:flex;gap:0;margin-bottom:28px;border:2px solid var(--border);border-radius:6px;overflow:hidden}",
".stab{flex:1;padding:13px;text-align:center;cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:600;transition:all .2s;background:var(--white);color:var(--muted);border:none;outline:none}",
".stab.al-on{background:var(--navy);color:var(--gold)}",
".stab.gu-on{background:var(--red);color:var(--white)}",
".price-preview{background:var(--navy);border-radius:6px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between}",
".pp-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.35);letter-spacing:1px;text-transform:uppercase}",
".pp-amount{font-family:var(--display);font-size:32px;color:var(--gold);font-weight:900}",
".pp-amount.gu-col{color:#ff6b6b}",
".pp-sub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);margin-top:2px}",
".btn-full{width:100%;margin-top:8px;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}",
".key-box{display:none;margin-top:20px;background:var(--navy);border-radius:6px;padding:22px}",
".key-box.show{display:block}",
".key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);margin-bottom:8px;text-transform:uppercase}",
".key-val{font-family:var(--mono);font-size:11px;color:#00ff88;word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;border:1px solid rgba(255,255,255,0.05)}",
".key-copy{margin-top:8px;background:transparent;border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.3);padding:6px 14px;font-family:var(--mono);font-size:9px;cursor:pointer;transition:all .2s;letter-spacing:1px;text-transform:uppercase;border-radius:4px}",
".key-copy:hover{border-color:var(--gold);color:var(--gold)}",
".usage-box{margin-top:12px;font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);padding:12px;border-radius:4px;line-height:1.9}",
".usage-box em{color:#79b8ff;font-style:normal}",
"@media(max-width:900px){",
".alert-bar{padding:10px 20px;font-size:10px}",
".hero{padding:52px 20px 68px}",
".product-cards,.two-col,.comp-grid,.price-cards,.fg-row,.threat-grid,.fair-grid{grid-template-columns:1fr}",
".stats-inner{grid-template-columns:repeat(3,1fr)}",
".sec,.guardian-sec,.compliance-sec,.fair-sec,.pricing-sec,.signup-sec{padding:52px 20px}",
"}",
"</style></head><body>",
COMMON_NAV,
'<div class="alert-bar"><strong>EU AI Act enforcement: August 2026.</strong> &nbsp;UK Online Safety Act: now in force.&nbsp; <strong>50p per device. Both products. Total coverage.</strong></div>',
'<section class="hero"><div class="hero-inner">',
'<div><span class="kdot"></span><span class="ktext">Monop Content &middot; Blyth, UK &middot; Live Now</span></div>',
'<h1>AI Governance.<br><em>Child Safety.</em><br>One Platform.</h1>',
'<p class="hero-sub">Two products. One audit engine. 50p per device per month. Enter your details and you are covered. No technical knowledge required. Platforms, schools, parents, ISPs. Everyone.</p>',
'<div class="product-cards">',
'<div class="pc pc-leash" onclick="switchTab(\'leash\');document.getElementById(\'signup\').scrollIntoView({behavior:\'smooth\'})">',
'<div class="pc-badge">AILeash &mdash; AI Governance</div><h3>Enterprise AI Governance</h3>',
'<p>9-signal risk engine. SHA-256 audit chain. EU AI Act Art.9, 12, 13 compliant. Real-time ALLOW / CHALLENGE / BLOCK for every AI action.</p>',
'<div class="pc-tags"><span class="ptag">EU AI Act</span><span class="ptag">SHA-256 Chain</span><span class="ptag">9 Signals</span><span class="ptag">Real-Time</span></div></div>',
'<div class="pc pc-guardian" onclick="switchTab(\'guardian\');document.getElementById(\'signup\').scrollIntoView({behavior:\'smooth\'})">',
'<div class="pc-badge">AILeash Guardian &mdash; Child Safety</div><h3>Child Safety Layer</h3>',
'<p>Grooming detection. CSAM intervention. Cross-border risk. Online Safety Act 2023 and ICO Children\'s Code compliant. Every device.</p>',
'<div class="pc-tags"><span class="ptag">Online Safety Act</span><span class="ptag">Grooming Detection</span><span class="ptag">CSAM</span><span class="ptag">Ofcom Ready</span></div></div>',
'</div>',
'<div class="hero-btns">',
'<a href="#signup" class="btn-gold" onclick="switchTab(\'leash\')">Get AILeash &rarr;</a>',
'<a href="#signup" class="btn-red" onclick="switchTab(\'guardian\')">Get Guardian &rarr;</a>',
'<a href="/scan" class="btn-ghost">Free AI Act Scanner</a>',
'</div></div></section>',
'<div class="divider"></div>',
'<div class="stats-strip"><div class="stats-inner">',
'<div class="stat"><div class="stat-n">9</div><div class="stat-l">Risk Signals</div></div>',
'<div class="stat"><div class="stat-n">SHA256</div><div class="stat-l">Audit Chain</div></div>',
'<div class="stat"><div class="stat-n">&lt;12ms</div><div class="stat-l">Detection</div></div>',
'<div class="stat"><div class="stat-n">24/7</div><div class="stat-l">Always On</div></div>',
'<div class="stat"><div class="stat-n">50p</div><div class="stat-l">Per Device</div></div>',
'</div></div>',
'<section class="sec" id="governance"><div class="sec-inner">',
'<div class="slbl" style="color:var(--navy)">AILeash &mdash; AI Governance</div>',
'<h2>Nine-Signal <em>Risk Engine</em></h2>',
'<p class="sec-sub">Every AI action scored across nine concurrent signals. Explainable decisions. Tamper-evident audit chain. EU AI Act compliant from day one.</p>',
'<div class="two-col"><div>',
'<div class="feature-block"><div class="fb-icon">&#9889;</div><div class="fb-lbl">Signals 01&ndash;03</div><h3>Velocity Tracking</h3><p>Three concurrent time windows &mdash; 60 seconds, 5 minutes, 1 hour &mdash; detect spikes before they escalate.</p></div>',
'<div class="feature-block"><div class="fb-icon">&#128274;</div><div class="fb-lbl">Signal 04</div><h3>Adaptive Trust</h3><p>Per-agent trust scores decay on bad decisions and recover on good behaviour. Trust is earned, never assumed.</p></div>',
'<div class="feature-block"><div class="fb-icon">&#127758;</div><div class="fb-lbl">Signals 08&ndash;09</div><h3>Geographic Risk</h3><p>Country-shift detection and jurisdiction-based risk weighting. Sudden location changes trigger elevated scoring.</p></div>',
'</div><div>',
'<p style="font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:14px">Signal Weights</p>',
'<div class="signal-list">',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:90%"></div></div><span class="sig-name">Behavioural Trust</span><span class="sig-pct">30%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:75%"></div></div><span class="sig-name">Contact Velocity 60s</span><span class="sig-pct">15%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:75%"></div></div><span class="sig-name">Content / Amount Risk</span><span class="sig-pct">15%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:65%"></div></div><span class="sig-name">Velocity 5 Minutes</span><span class="sig-pct">10%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:65%"></div></div><span class="sig-name">Velocity 1 Hour</span><span class="sig-pct">10%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:50%"></div></div><span class="sig-name">Device Risk</span><span class="sig-pct">10%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:50%"></div></div><span class="sig-name">Behavioural Anomaly</span><span class="sig-pct">10%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:30%;background:#ff6b6b"></div></div><span class="sig-name">Geographic Risk</span><span class="sig-pct" style="color:#ff6b6b">+10%</span></div>',
'<div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:30%;background:#ff6b6b"></div></div><span class="sig-name">Cross-Border</span><span class="sig-pct" style="color:#ff6b6b">+10%</span></div>',
'</div>',
'<div class="dec-flow">',
'<div class="df df-allow"><div class="df-v">ALLOW</div><div class="df-d">Safe. Proceeds. SHA-256 audit record created.</div><div class="df-t">Score &lt; 0.35</div></div>',
'<div class="df df-challenge"><div class="df-v">CHALLENGE</div><div class="df-d">Elevated risk. Paused. Human review required.</div><div class="df-t">Score 0.35&ndash;0.70</div></div>',
'<div class="df df-block"><div class="df-v">BLOCK</div><div class="df-d">High risk. Halted. Evidence preserved. Referral activated.</div><div class="df-t">Score &gt; 0.70</div></div>',
'</div></div></div></div></section>',
'<section class="guardian-sec" id="guardian"><div class="guardian-inner">',
'<div class="slbl" style="color:rgba(255,255,255,0.25)">AILeash Guardian &mdash; Child Safety</div>',
'<h2 style="color:var(--white)">Every threat. <em>Detected. Stopped.</em></h2>',
'<p style="font-size:15px;color:rgba(255,255,255,0.35);max-width:580px;line-height:1.7;margin-bottom:0">Same SHA-256 engine, adapted for child safety. Six harm categories. All detected in real time. Every intervention recorded as legal evidence admissible in UK courts.</p>',
'<div class="threat-grid">',
'<div class="tc tc-r"><div class="tc-icon">&#127907;</div><div class="tc-lbl">Threat 01</div><h3>Grooming Detection</h3><p>Velocity, trust escalation, isolation attempts and geographic risk combined. Stopped before it starts.</p><div class="tc-tags"><span class="ttag">velocity_spike</span><span class="ttag">trust_escalation</span></div></div>',
'<div class="tc tc-g"><div class="tc-icon">&#128172;</div><div class="tc-lbl">Threat 02</div><h3>Harmful Content</h3><p>Anomaly detection flags content deviating from age-appropriate norms. Block triggered before a child sees it.</p><div class="tc-tags"><span class="ttag">content_anomaly</span><span class="ttag">age_mismatch</span></div></div>',
'<div class="tc tc-n"><div class="tc-icon">&#129302;</div><div class="tc-lbl">Threat 03</div><h3>Bot and Fake Accounts</h3><p>Automated accounts targeting children identified before first contact. Non-human actors exposed instantly.</p><div class="tc-tags"><span class="ttag">device_risk</span><span class="ttag">behaviour_anomaly</span></div></div>',
'<div class="tc tc-gr"><div class="tc-icon">&#129504;</div><div class="tc-lbl">Threat 04</div><h3>Psychological Manipulation</h3><p>Detects coercive control and manufactured dependency. Trust decay identifies dangerous relationships early.</p><div class="tc-tags"><span class="ttag">trust_decay</span><span class="ttag">sentiment_shift</span></div></div>',
'<div class="tc tc-b"><div class="tc-icon">&#127758;</div><div class="tc-lbl">Threat 05</div><h3>Cross-Border Risk</h3><p>Flags contact from high-risk jurisdictions. Country shift identifies when domestic contact suddenly operates abroad.</p><div class="tc-tags"><span class="ttag">unsafe_country</span><span class="ttag">country_shift</span></div></div>',
'<div class="tc tc-p"><div class="tc-icon">&#128247;</div><div class="tc-lbl">Threat 06</div><h3>CSAM and Image Abuse</h3><p>Integrates with image hash databases. Evidence automatically preserved for law enforcement referral.</p><div class="tc-tags"><span class="ttag">image_hash_match</span><span class="ttag">share_velocity</span></div></div>',
'</div></div></section>',
'<section class="compliance-sec" id="compliance"><div class="sec-inner">',
'<div class="slbl" style="color:var(--navy)">Legal Compliance</div>',
'<h2>Built for the law. <em>As it stands today.</em></h2>',
'<p class="sec-sub">Both products meet every current and upcoming UK and EU legal obligation. Deploy and tick every compliance box immediately.</p>',
'<div class="comp-grid">',
'<div class="comp-card"><div class="comp-act">EU AI Act 2024/1689</div><h3>High-Risk AI Compliance</h3><p>Enforced August 2026. AILeash satisfies Art.9 risk assessment, Art.12 audit chain, Art.13 explainability from day one.</p><div class="checks"><div class="chk">Article 9 &mdash; Continuous risk assessment</div><div class="chk">Article 12 &mdash; Tamper-evident audit chain</div><div class="chk">Article 13 &mdash; Explainable decisions</div><div class="chk">GDPR Art.22 &mdash; Human oversight pathway</div></div></div>',
'<div class="comp-card"><div class="comp-act">Online Safety Act 2023 &mdash; UK</div><h3>Duty of Care to Children</h3><p>Platforms must assess risk and demonstrate compliance to Ofcom. Guardian provides the complete technical infrastructure.</p><div class="checks"><div class="chk">Risk assessment infrastructure</div><div class="chk">Real-time content moderation</div><div class="chk">Age-appropriate design</div><div class="chk">Ofcom-ready audit trails</div></div></div>',
'<div class="comp-card"><div class="comp-act">ICO Children\'s Code &mdash; UK</div><h3>Age Appropriate Design</h3><p>Guardian ensures children are never subject to solely automated high-risk decisions without human oversight.</p><div class="checks"><div class="chk">Best interests of the child by default</div><div class="chk">Data minimisation for child users</div><div class="chk">Profiling restrictions enforced</div><div class="chk">Parental controls pathway</div></div></div>',
'<div class="comp-card"><div class="comp-act">Digital Services Act &mdash; EU 2022/2065</div><h3>Platform Accountability</h3><p>Continuous automated risk assessment with full audit documentation for regulatory submission under the DSA.</p><div class="checks"><div class="chk">Systemic risk assessment</div><div class="chk">Algorithmic transparency reports</div><div class="chk">Minor protection evidence packages</div><div class="chk">Regulator-ready submissions</div></div></div>',
'</div></div></section>',
'<section class="fair-sec"><div class="sec-inner">',
'<div class="slbl" style="color:var(--navy)">Fair Usage Policy</div>',
'<h2>Always fast. <em>Always fair.</em></h2>',
'<p class="sec-sub">Per-key rate limits keep the platform fast for everyone. When global load spikes, a second governance engine spins up automatically.</p>',
'<div class="fair-grid">',
'<div class="fair-card"><h3>Per-Key Rate Limits</h3><p>Every API key is governed by fair usage limits. Bursting above these triggers graceful throttling, not crashes. Your audit chain is always safe.</p><div class="fair-limit">60 requests / minute<br>1,000 requests / hour</div></div>',
'<div class="fair-card"><h3>Auto-Scale on Load</h3><p>When global request rate exceeds threshold, Railway spins up a second governance engine instance automatically. Capacity doubles in seconds.</p><div class="fair-limit">Threshold: 200 req / sec<br>Scale: automatic via Railway</div></div>',
'<div class="fair-card"><h3>Audit Chain Integrity</h3><p>Load events are logged. If we ever throttle your key, the event is recorded with a timestamp. Full transparency, always.</p><div class="fair-limit">Load events logged to chain<br>Verifiable via /api/verify-chain</div></div>',
'</div></div></section>',
'<section class="pricing-sec" id="pricing"><div class="pricing-inner">',
'<div class="slbl" style="color:rgba(255,255,255,0.25)">Pricing</div>',
'<h2 style="color:var(--white)">Simple. <em>Honest. 50p.</em></h2>',
'<p style="font-size:15px;color:rgba(255,255,255,0.35);line-height:1.7">50p per device per month. No tiers. No minimums. 10 devices is five pounds. 1,000 devices is five hundred.</p>',
'<div class="price-cards">',
'<div class="price-card al"><div class="price-product">AILeash &mdash; AI Governance</div><div class="price-big"><sup>&pound;</sup>0.50</div><div class="price-per">per device &middot; per month</div><div class="price-example">10 devices = <strong>&pound;5/mo</strong><br>100 devices = <strong>&pound;50/mo</strong><br>1,000 devices = <strong>&pound;500/mo</strong></div><div class="price-feats"><div class="pf">9-signal risk engine</div><div class="pf">SHA-256 and Merkle audit chain</div><div class="pf">ALLOW / CHALLENGE / BLOCK</div><div class="pf">EU AI Act Art.9 / 12 / 13</div><div class="pf">60/min and 1,000/hr fair use</div><div class="pf">100 free decisions to start</div></div><a href="#signup" class="btn-gold" style="display:block;text-align:center;text-decoration:none" onclick="switchTab(\'leash\')">Get AILeash &rarr;</a><p class="price-note">Free trial &middot; No card to start &middot; Stripe billing</p></div>',
'<div class="price-card gu"><div class="price-product">Guardian &mdash; Child Safety</div><div class="price-big"><sup>&pound;</sup>0.50</div><div class="price-per">per device &middot; per month</div><div class="price-example">10 devices = <strong>&pound;5/mo</strong><br>100 devices = <strong>&pound;50/mo</strong><br>1,000 devices = <strong>&pound;500/mo</strong></div><div class="price-feats"><div class="pf">Full Guardian engine</div><div class="pf">SHA-256 and Merkle audit chain</div><div class="pf">Real-time grooming detection</div><div class="pf">CSAM database integration</div><div class="pf">Ofcom and Online Safety Act</div><div class="pf">100 free decisions to start</div></div><a href="#signup" class="btn-red" style="display:block;text-align:center;text-decoration:none" onclick="switchTab(\'guardian\')">Get Guardian &rarr;</a><p class="price-note">Free trial &middot; No card to start &middot; Stripe billing</p></div>',
'</div></div></section>',
'<section class="signup-sec" id="signup"><div class="signup-inner">',
'<div class="slbl" style="color:var(--navy)">Get Started</div>',
'<h2>Covered in <em>60 seconds.</em></h2>',
'<p style="font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:24px">Name. Email. Phone. Organisation. Devices. That is it. Your key is created instantly then you go straight to Stripe. 100 free decisions included.</p>',
'<div class="product-tabs"><button class="stab al-on" id="tab-leash" onclick="switchTab(\'leash\')">AILeash &mdash; Governance</button><button class="stab" id="tab-guardian" onclick="switchTab(\'guardian\')">Guardian &mdash; Child Safety</button></div>',
'<div class="fg-row"><div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div><div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div></div>',
'<div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@organisation.com"></div>',
'<div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>',
'<div class="fg"><label>Organisation Name</label><input type="text" id="org" placeholder="e.g. St Mary\'s Academy / Meta UK / Ofcom"></div>',
'<div class="fg"><label>Organisation Type</label><select id="ot"><option value="">Select type</option><option value="platform">Social Media Platform</option><option value="school">School / Academy</option><option value="isp">ISP / Telecoms</option><option value="government">Government / Regulator</option><option value="enterprise">Enterprise</option><option value="charity">Charity / NGO</option><option value="parent">Parent / Individual</option><option value="other">Other</option></select></div>',
'<div class="fg"><label>Number of Devices</label><input type="number" id="dv" placeholder="e.g. 10" min="1" oninput="updatePrice()"></div>',
'<div class="price-preview"><div><div class="pp-label">Monthly Total</div><div class="pp-sub" id="pp-sub">Enter device count above</div></div><div class="pp-amount" id="pp-amt">&pound;0.00</div></div>',
'<button class="btn-full btn-gold" id="go-btn" onclick="doSignup()">Get Free API Key &rarr;</button>',
'<div class="msg-err" id="msg-err"></div>',
'<div class="msg-ok" id="msg-ok"></div>',
'<div class="key-box" id="key-box">',
'<div class="key-lbl">Your API Key &mdash; Save This Now</div>',
'<div class="key-val" id="key-val"></div>',
'<button class="key-copy" onclick="copyKey()">Copy Key</button>',
'<div class="usage-box"><div><em>POST</em> https://sebbi.pro/api/govern</div><div>Authorization: Bearer <em id="key-prev">YOUR_KEY</em></div><div>Content-Type: application/json</div><div style="margin-top:6px;color:rgba(255,255,255,0.12)">50p per device per month &middot; Billed via Stripe</div></div>',
'</div></div></section>',
COMMON_FOOTER,
"<script>",
"var AP='leash';",
"function switchTab(p){AP=p;document.getElementById('tab-leash').className='stab'+(p==='leash'?' al-on':'');document.getElementById('tab-guardian').className='stab'+(p==='guardian'?' gu-on':'');var btn=document.getElementById('go-btn');if(p==='guardian'){btn.textContent='Get Guardian API Key \u2192';btn.style.background='var(--red)';btn.style.color='var(--white)';}else{btn.textContent='Get AILeash API Key \u2192';btn.style.background='var(--gold)';btn.style.color='var(--navy)';}document.getElementById('pp-amt').className='pp-amount'+(p==='guardian'?' gu-col':'');updatePrice();}",
"function updatePrice(){var n=parseInt(document.getElementById('dv').value)||0;document.getElementById('pp-amt').textContent='\u00a3'+(n*0.5).toFixed(2);document.getElementById('pp-sub').textContent=n>0?(n+' device'+(n===1?'':'s')+' \u00d7 50p = \u00a3'+(n*0.5).toFixed(2)+'/mo'):'Enter device count above';}",
"async function doSignup(){var em=document.getElementById('em').value.trim();var ph=document.getElementById('ph').value.trim();var fn=document.getElementById('fn').value.trim();var ln=document.getElementById('ln').value.trim();var org=document.getElementById('org').value.trim();var ot=document.getElementById('ot').value;var dv=parseInt(document.getElementById('dv').value)||1;var err=document.getElementById('msg-err');var ok=document.getElementById('msg-ok');var kb=document.getElementById('key-box');var btn=document.getElementById('go-btn');err.classList.remove('show');ok.classList.remove('show');kb.classList.remove('show');if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}if(!ph){err.textContent='Please enter your phone number.';err.classList.add('show');return;}btn.textContent='Creating key\u2026';btn.disabled=true;try{var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:ot,product:AP,devices:dv})});var d=await r.json();if(d.api_key){document.getElementById('key-val').textContent=d.api_key;document.getElementById('key-prev').textContent=d.api_key.slice(0,24)+'...';kb.classList.add('show');ok.textContent='Key created. 100 free decisions included. Taking you to Stripe\u2026';ok.classList.add('show');btn.textContent='Key Created \u2713';setTimeout(function(){fetch('/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,product:AP,devices:dv})}).then(function(r2){return r2.json();}).then(function(d2){if(d2.checkout_url){window.location.href=d2.checkout_url;}else{ok.textContent='Key ready. Set up billing at '+window.location.origin+'/#pricing';}}).catch(function(){ok.textContent='Key ready. Billing setup at '+window.location.origin+'/#pricing';});},1400);}else{err.textContent='Error: '+(d.error||'Request failed. Email justin@monopcontent.com directly.');err.classList.add('show');btn.textContent=AP==='guardian'?'Get Guardian API Key \u2192':'Get AILeash API Key \u2192';btn.disabled=false;}}catch(e){err.textContent='Could not reach server. Email justin@monopcontent.com directly.';err.classList.add('show');btn.textContent=AP==='guardian'?'Get Guardian API Key \u2192':'Get AILeash API Key \u2192';btn.disabled=false;}}",
"function copyKey(){navigator.clipboard.writeText(document.getElementById('key-val').textContent).then(function(){var b=document.querySelector('.key-copy');b.textContent='Copied \u2713';setTimeout(function(){b.textContent='Copy Key';},2000);});}",
"</script></body></html>"
])

# ============================================================================
# SCAN PAGE
# ============================================================================
SCAN_PAGE = "\n".join([
"<!DOCTYPE html>",
'<html lang="en"><head><meta charset="UTF-8">',
'<meta name="viewport" content="width=device-width,initial-scale=1.0">',
"<title>EU AI Act Compliance Scanner &mdash; AILeash</title>",
'<meta name="description" content="Free EU AI Act compliance scanner. 8 questions. Instant score. See if your AI systems are ready for August 2026 enforcement.">',
COMMON_FONTS,
"<style>",
COMMON_CSS,
".scan-hero{background:var(--navy);padding:100px 48px 80px;text-align:center}",
".scan-hero h1{font-family:var(--display);font-size:clamp(36px,4vw,60px);color:var(--white);font-weight:900;margin-bottom:16px;line-height:1.1}",
".scan-hero h1 em{color:var(--gold);font-style:normal}",
".scan-hero p{font-size:17px;color:rgba(255,255,255,0.5);max-width:560px;margin:0 auto 32px;line-height:1.75}",
".scan-meta{display:flex;gap:24px;justify-content:center;flex-wrap:wrap;margin-bottom:0}",
".sm{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase;display:flex;align-items:center;gap:6px}",
".sm::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--gold);flex-shrink:0}",
".scan-wrap{max-width:720px;margin:0 auto;padding:60px 48px}",
".progress-bar{height:4px;background:var(--border);border-radius:2px;margin-bottom:40px;overflow:hidden}",
".progress-fill{height:100%;background:linear-gradient(90deg,var(--gold),var(--red));border-radius:2px;transition:width .4s ease}",
".question-card{display:none}",
".question-card.active{display:block}",
".q-num{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}",
".q-text{font-family:var(--display);font-size:clamp(20px,2.5vw,28px);font-weight:800;color:var(--navy);margin-bottom:8px;line-height:1.2}",
".q-sub{font-size:13px;color:var(--muted);margin-bottom:28px;line-height:1.6}",
".q-options{display:flex;flex-direction:column;gap:10px}",
".q-opt{padding:16px 20px;border:2px solid var(--border);border-radius:6px;cursor:pointer;font-size:14px;color:var(--text);transition:all .2s;background:var(--white);text-align:left;font-family:var(--sans)}",
".q-opt:hover{border-color:var(--gold);background:rgba(201,168,76,0.04)}",
".q-opt.selected{border-color:var(--navy);background:var(--navy);color:var(--white)}",
".q-opt.risk{border-color:var(--red)}.q-opt.risk.selected{background:var(--red)}",
".scan-nav{display:flex;justify-content:space-between;align-items:center;margin-top:28px}",
".scan-nav button{padding:12px 24px;border-radius:4px;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;transition:all .2s;border:none}",
".btn-back{background:var(--off);color:var(--muted)}.btn-back:hover{background:var(--border)}",
".btn-next{background:var(--gold);color:var(--navy)}.btn-next:hover{background:var(--gold2)}",
".result-card{display:none;text-align:center}",
".result-card.show{display:block}",
".result-score{font-family:var(--display);font-size:96px;font-weight:900;line-height:1;margin-bottom:8px}",
".score-high{color:var(--red)}.score-mid{color:#b45309}.score-low{color:var(--green)}",
".result-label{font-family:var(--mono);font-size:13px;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}",
".result-verdict{font-size:17px;color:var(--text);max-width:520px;margin:0 auto 32px;line-height:1.75}",
".result-issues{text-align:left;margin-bottom:32px}",
".ri{display:flex;gap:12px;padding:14px 16px;border-radius:4px;margin-bottom:8px;font-size:13px;line-height:1.5}",
".ri-red{background:#fff0f0;border:1px solid #ffcccc;color:#7f1d1d}",
".ri-gold{background:#fffbeb;border:1px solid #fde68a;color:#78350f}",
".ri-green{background:#f0fff8;border:1px solid #bbf7d0;color:#064e3b}",
".ri-icon{flex-shrink:0;font-weight:700;font-family:var(--mono);font-size:11px;padding-top:1px}",
".result-cta{background:var(--navy);border-radius:8px;padding:32px;text-align:center;margin-top:28px}",
".result-cta h3{font-family:var(--display);font-size:24px;color:var(--white);font-weight:900;margin-bottom:8px}",
".result-cta p{font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:20px;line-height:1.65}",
".result-cta-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}",
"@media(max-width:700px){.scan-wrap{padding:40px 20px}.scan-hero{padding:80px 20px 60px}}",
"</style></head><body>",
COMMON_NAV,
'<div class="scan-hero">',
'<h1>EU AI Act<br><em>Compliance Scanner</em></h1>',
'<p>8 questions. 60 seconds. Instant score. Find out if your AI systems are ready for the August 2026 enforcement deadline before Ofcom or the EU Commission finds out for you.</p>',
'<div class="scan-meta"><span class="sm">Free &mdash; No signup required</span><span class="sm">8 questions</span><span class="sm">Instant score</span><span class="sm">August 2026 deadline</span></div>',
'</div>',
'<div class="scan-wrap">',
'<div class="progress-bar"><div class="progress-fill" id="prog" style="width:0%"></div></div>',
'<div id="q-container">',
# Q1
'<div class="question-card active" id="q0">',
'<div class="q-num">Question 1 of 8</div>',
'<div class="q-text">Does your organisation use AI systems that make decisions affecting people?</div>',
'<div class="q-sub">This includes automated hiring, credit scoring, content moderation, access control, fraud detection, or any system where AI output influences a human outcome.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(0,0,false)">Yes &mdash; AI decisions directly affect people</button>',
'<button class="q-opt" onclick="answer(0,1,false)">Yes &mdash; AI assists humans who make final decisions</button>',
'<button class="q-opt" onclick="answer(0,2,false)">No &mdash; we use AI for internal tools only</button>',
'<button class="q-opt" onclick="answer(0,3,false)">We are evaluating AI but not deployed yet</button>',
'</div></div>',
# Q2
'<div class="question-card" id="q1">',
'<div class="q-num">Question 2 of 8</div>',
'<div class="q-text">Do you have a tamper-evident audit trail for every AI decision?</div>',
'<div class="q-sub">EU AI Act Article 12 requires high-risk AI systems to automatically log events in a way that cannot be altered after the fact. Logs must be retained and available to regulators.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(1,0,false)">Yes &mdash; cryptographic audit chain in place</button>',
'<button class="q-opt risk" onclick="answer(1,1,true)">We have standard logs but no tamper protection</button>',
'<button class="q-opt risk" onclick="answer(1,2,true)">No audit trail exists</button>',
'<button class="q-opt risk" onclick="answer(1,3,true)">We are not sure what we have</button>',
'</div></div>',
# Q3
'<div class="question-card" id="q2">',
'<div class="q-num">Question 3 of 8</div>',
'<div class="q-text">Can you explain every AI decision in plain language to a regulator?</div>',
'<div class="q-sub">Article 13 requires AI systems to be transparent. Every decision must include a human-readable explanation of which factors drove the outcome and why.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(2,0,false)">Yes &mdash; every decision includes a full explanation</button>',
'<button class="q-opt risk" onclick="answer(2,1,true)">We can explain some decisions but not all</button>',
'<button class="q-opt risk" onclick="answer(2,2,true)">No &mdash; our model is a black box</button>',
'<button class="q-opt risk" onclick="answer(2,3,true)">We have not considered this requirement</button>',
'</div></div>',
# Q4
'<div class="question-card" id="q3">',
'<div class="q-num">Question 4 of 8</div>',
'<div class="q-text">Is there a human oversight pathway for high-risk AI decisions?</div>',
'<div class="q-sub">Article 14 requires that humans can override, correct, or halt AI systems. High-risk decisions must not be fully automated without a mechanism for human intervention.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(3,0,false)">Yes &mdash; CHALLENGE decisions route to human review automatically</button>',
'<button class="q-opt" onclick="answer(3,1,false)">Humans can intervene but the process is manual</button>',
'<button class="q-opt risk" onclick="answer(3,2,true)">No human oversight pathway exists</button>',
'<button class="q-opt risk" onclick="answer(3,3,true)">All decisions are fully automated with no override</button>',
'</div></div>',
# Q5
'<div class="question-card" id="q4">',
'<div class="q-num">Question 5 of 8</div>',
'<div class="q-text">Have you conducted a formal risk assessment for your AI systems?</div>',
'<div class="q-sub">Article 9 requires a continuous risk management system covering identification, analysis, and mitigation of risks. This must be documented and updated throughout the AI lifecycle.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(4,0,false)">Yes &mdash; documented and updated regularly</button>',
'<button class="q-opt risk" onclick="answer(4,1,true)">We did one at launch but have not updated it</button>',
'<button class="q-opt risk" onclick="answer(4,2,true)">No formal risk assessment exists</button>',
'<button class="q-opt risk" onclick="answer(4,3,true)">We were not aware this was required</button>',
'</div></div>',
# Q6
'<div class="question-card" id="q5">',
'<div class="q-num">Question 6 of 8</div>',
'<div class="q-text">Does your AI system interact with or make decisions affecting children?</div>',
'<div class="q-sub">AI systems affecting minors are automatically classified as high-risk under the EU AI Act and are subject to additional obligations under the UK Online Safety Act 2023 and ICO Children\'s Code.</div>',
'<div class="q-options">',
'<button class="q-opt risk" onclick="answer(5,0,true)">Yes &mdash; children use or are affected by our AI systems</button>',
'<button class="q-opt" onclick="answer(5,1,false)">No &mdash; our systems explicitly exclude minors</button>',
'<button class="q-opt risk" onclick="answer(5,2,true)">We are not sure &mdash; our platform is open to the public</button>',
'<button class="q-opt" onclick="answer(5,3,false)">Not applicable to our use case</button>',
'</div></div>',
# Q7
'<div class="question-card" id="q6">',
'<div class="q-num">Question 7 of 8</div>',
'<div class="q-text">Are your AI systems registered with the EU AI Act database?</div>',
'<div class="q-sub">High-risk AI systems must be registered in the EU database before being placed on the market or put into service. This is a hard legal requirement from August 2026.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(6,0,false)">Yes &mdash; registered and compliant</button>',
'<button class="q-opt risk" onclick="answer(6,1,true)">No &mdash; not yet registered</button>',
'<button class="q-opt risk" onclick="answer(6,2,true)">We did not know registration was required</button>',
'<button class="q-opt" onclick="answer(6,3,false)">We have assessed and confirmed we are not high-risk</button>',
'</div></div>',
# Q8
'<div class="question-card" id="q7">',
'<div class="q-num">Question 8 of 8</div>',
'<div class="q-text">When is your organisation planning to be fully EU AI Act compliant?</div>',
'<div class="q-sub">Enforcement begins August 2026 for high-risk AI systems. Fines for non-compliance reach 3% of global annual turnover or 15 million euros, whichever is higher.</div>',
'<div class="q-options">',
'<button class="q-opt" onclick="answer(7,0,false)">We are already compliant</button>',
'<button class="q-opt" onclick="answer(7,1,false)">We have a programme in place and will be ready by August 2026</button>',
'<button class="q-opt risk" onclick="answer(7,2,true)">We are working on it but may not be ready in time</button>',
'<button class="q-opt risk" onclick="answer(7,3,true)">We have not started compliance work yet</button>',
'</div></div>',
'</div>',
# Result
'<div class="result-card" id="result">',
'<div class="result-score" id="res-score">0</div>',
'<div class="result-label" id="res-label">Calculating...</div>',
'<div class="result-verdict" id="res-verdict"></div>',
'<div class="result-issues" id="res-issues"></div>',
'<div class="result-cta">',
'<h3>AILeash fixes this. Today.</h3>',
'<p>SHA-256 audit chain. Explainable decisions. Human oversight pathway. EU AI Act Art.9, 12, 13 compliant. Guardian covers children. 50p per device per month. 100 free decisions to start.</p>',
'<div class="result-cta-btns">',
'<a href="/#signup" class="btn-gold" onclick="localStorage.setItem(\'scan_product\',\'leash\')">Get AILeash &rarr;</a>',
'<a href="/#signup" class="btn-red" onclick="localStorage.setItem(\'scan_product\',\'guardian\')">Get Guardian &rarr;</a>',
'</div>',
'<p style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);margin-top:16px;letter-spacing:1px">Free trial &middot; 100 decisions &middot; No card required</p>',
'</div>',
'<div style="margin-top:24px;text-align:center"><button onclick="restartScan()" style="background:none;border:none;color:var(--muted);font-family:var(--mono);font-size:11px;cursor:pointer;letter-spacing:1px;text-decoration:underline">Retake the scanner</button></div>',
'</div>',
'<div class="scan-nav" id="scan-nav">',
'<button class="btn-back" id="btn-back" onclick="prevQ()" style="display:none">Back</button>',
'<span style="font-family:var(--mono);font-size:11px;color:var(--muted)" id="q-counter">1 / 8</span>',
'<button class="btn-next" id="btn-next" onclick="nextQ()" disabled>Next &rarr;</button>',
'</div>',
'</div>',
COMMON_FOOTER,
"<script>",
"var cur=0,total=8,answers=[],risks=[];",
"var questions=[",
"'Does your organisation use AI systems that make decisions affecting people?',",
"'Do you have a tamper-evident audit trail for every AI decision?',",
"'Can you explain every AI decision in plain language to a regulator?',",
"'Is there a human oversight pathway for high-risk AI decisions?',",
"'Have you conducted a formal risk assessment for your AI systems?',",
"'Does your AI system interact with or make decisions affecting children?',",
"'Are your AI systems registered with the EU AI Act database?',",
"'When is your organisation planning to be fully EU AI Act compliant?'",
"];",
"var riskLabels=[",
"'No AI Act exposure identified','Standard audit logging insufficient for Art.12','Black-box AI violates Art.13 explainability','No human oversight violates Art.14','No risk management violates Art.9','Systems affecting children require Guardian + Online Safety Act compliance','High-risk AI must be registered in EU database before August 2026','Insufficient time to achieve compliance before enforcement'",
"];",
"function answer(q,opt,isRisk){",
"  answers[q]=opt; risks[q]=isRisk;",
"  document.querySelectorAll('#q'+q+' .q-opt').forEach(function(b){b.classList.remove('selected');});",
"  document.querySelectorAll('#q'+q+' .q-opt')[opt].classList.add('selected');",
"  document.getElementById('btn-next').disabled=false;",
"}",
"function updateProgress(){",
"  var pct=Math.round((cur/total)*100);",
"  document.getElementById('prog').style.width=pct+'%';",
"  document.getElementById('q-counter').textContent=(cur+1)+' / '+total;",
"  document.getElementById('btn-back').style.display=cur>0?'block':'none';",
"}",
"function nextQ(){",
"  if(answers[cur]===undefined) return;",
"  document.getElementById('q'+cur).classList.remove('active');",
"  cur++;",
"  if(cur>=total){showResult();return;}",
"  document.getElementById('q'+cur).classList.add('active');",
"  document.getElementById('btn-next').disabled=answers[cur]===undefined;",
"  updateProgress();",
"}",
"function prevQ(){",
"  if(cur===0) return;",
"  document.getElementById('q'+cur).classList.remove('active');",
"  cur--;",
"  document.getElementById('q'+cur).classList.add('active');",
"  document.getElementById('btn-next').disabled=false;",
"  updateProgress();",
"}",
"function showResult(){",
"  document.getElementById('scan-nav').style.display='none';",
"  document.getElementById('prog').style.width='100%';",
"  var riskCount=risks.filter(Boolean).length;",
"  var score=Math.round((riskCount/total)*100);",
"  var el=document.getElementById('res-score');",
"  el.textContent=score+'%';",
"  el.className='result-score '+(score>=60?'score-high':score>=30?'score-mid':'score-low');",
"  var label,verdict;",
"  if(score>=60){label='HIGH RISK &mdash; Immediate action required';verdict='Your AI systems have significant EU AI Act compliance gaps. At current enforcement fines, non-compliance could cost up to 3% of global annual turnover or \u20ac15M. AILeash can close these gaps today.';}",
"  else if(score>=30){label='MEDIUM RISK &mdash; Action needed before August 2026';verdict='You have made progress on compliance but critical gaps remain. With less than a year to enforcement, now is the time to close them. AILeash addresses every gap identified below.';}",
"  else{label='LOW RISK &mdash; Minor gaps to address';verdict='Your organisation appears largely prepared for the EU AI Act. A few areas need attention before August 2026. AILeash can provide the missing infrastructure.';}",
"  document.getElementById('res-label').innerHTML=label;",
"  document.getElementById('res-verdict').textContent=verdict;",
"  var issuesEl=document.getElementById('res-issues');",
"  issuesEl.innerHTML='';",
"  for(var i=0;i<total;i++){",
"    var cls=risks[i]?'ri-red':'ri-green';",
"    var icon=risks[i]?'FAIL':'PASS';",
"    issuesEl.innerHTML+='<div class=\"ri '+cls+'\"><span class=\"ri-icon\">'+icon+'</span><span>'+riskLabels[i]+'</span></div>';",
"  }",
"  document.getElementById('result').classList.add('show');",
"}",
"function restartScan(){cur=0;answers=[];risks=[];document.getElementById('result').classList.remove('show');document.getElementById('scan-nav').style.display='flex';document.querySelectorAll('.question-card').forEach(function(c){c.classList.remove('active');});document.getElementById('q0').classList.add('active');document.getElementById('btn-next').disabled=true;updateProgress();}",
"updateProgress();",
"</script></body></html>"
])

# ============================================================================
# CONTACT PAGE
# ============================================================================
CONTACT_PAGE = "\n".join([
"<!DOCTYPE html>",
'<html lang="en"><head><meta charset="UTF-8">',
'<meta name="viewport" content="width=device-width,initial-scale=1.0">',
f"<title>Contact &mdash; {OWNER_NAME} &mdash; AILeash Platform</title>",
COMMON_FONTS,
"<style>",
COMMON_CSS,
".contact-hero{background:var(--navy);padding:100px 48px 80px;text-align:center}",
".contact-hero h1{font-family:var(--display);font-size:clamp(36px,4vw,60px);color:var(--white);font-weight:900;margin-bottom:16px}",
".contact-hero h1 em{color:var(--gold);font-style:normal}",
".contact-hero p{font-size:17px;color:rgba(255,255,255,0.5);max-width:540px;margin:0 auto;line-height:1.75}",
".contact-wrap{max-width:1100px;margin:0 auto;padding:80px 48px;display:grid;grid-template-columns:1fr 1.4fr;gap:60px;align-items:start}",
".owner-card{background:var(--navy);border-radius:8px;padding:36px;position:sticky;top:88px}",
".owner-badge{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}",
".owner-name{font-family:var(--display);font-size:28px;color:var(--white);font-weight:900;margin-bottom:4px}",
".owner-title{font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:28px}",
".owner-contacts{display:flex;flex-direction:column;gap:14px}",
".oc{display:flex;align-items:center;gap:12px;padding:14px 16px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:6px;text-decoration:none;transition:border-color .2s}",
".oc:hover{border-color:rgba(201,168,76,0.4)}",
".oc-icon{font-size:18px;flex-shrink:0}",
".oc-label{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:2px}",
".oc-value{font-size:13px;color:var(--white)}",
".owner-note{margin-top:20px;font-size:12px;color:rgba(255,255,255,0.2);line-height:1.7;font-style:italic}",
".contact-form-wrap h2{font-family:var(--display);font-size:clamp(28px,3vw,40px);font-weight:900;margin-bottom:8px;color:var(--navy)}",
".contact-form-wrap h2 em{color:var(--gold);font-style:normal}",
".contact-form-wrap p{font-size:14px;color:var(--muted);margin-bottom:28px;line-height:1.7}",
".fg textarea{height:130px;resize:vertical}",
".btn-submit{background:var(--gold);color:var(--navy);padding:14px 32px;border:none;font-family:var(--sans);font-weight:700;font-size:15px;cursor:pointer;border-radius:4px;transition:all .2s;width:100%}",
".btn-submit:hover{background:var(--gold2)}",
"@media(max-width:900px){.contact-wrap{grid-template-columns:1fr;padding:52px 20px}.contact-hero{padding:80px 20px 60px}.owner-card{position:static}}",
"</style></head><body>",
COMMON_NAV,
'<div class="contact-hero">',
f'<h1>Talk to <em>{OWNER_NAME.split()[0]}.</em></h1>',
'<p>Whether you are a regulator, a platform, a school, or a parent &mdash; we want to hear from you. Responses within 24 hours.</p>',
'</div>',
'<div class="contact-wrap">',
'<div class="owner-card">',
'<div class="owner-badge">Direct Contact</div>',
f'<div class="owner-name">{OWNER_NAME}</div>',
f'<div class="owner-title">{OWNER_TITLE}</div>',
'<div class="owner-contacts">',
f'<a href="mailto:{OWNER_EMAIL}" class="oc"><span class="oc-icon">&#9993;</span><div><div class="oc-label">Email</div><div class="oc-value">{OWNER_EMAIL}</div></div></a>',
f'<a href="tel:{OWNER_PHONE.replace(" ","")}" class="oc"><span class="oc-icon">&#128222;</span><div><div class="oc-label">Phone</div><div class="oc-value">{OWNER_PHONE}</div></div></a>',
'<a href="https://github.com/justrightdecorators-ops/aileash" target="_blank" class="oc"><span class="oc-icon">&#128187;</span><div><div class="oc-label">GitHub</div><div class="oc-value">justrightdecorators-ops/aileash</div></div></a>',
'</div>',
'<p class="owner-note">Built in Blyth, UK. Available for meetings in London or remotely. Actively speaking with regulators, platforms, schools and ISPs.</p>',
'</div>',
'<div class="contact-form-wrap">',
'<h2>Send a <em>message.</em></h2>',
'<p>Use the form below or email directly. Tell us what you need &mdash; a demo, a pilot, a compliance briefing, or just a conversation about child safety or AI governance.</p>',
'<div class="fg-row"><div class="fg"><label>First Name</label><input type="text" id="cfn" placeholder="Justin"></div><div class="fg"><label>Last Name</label><input type="text" id="cln" placeholder="Smith"></div></div>',
'<div class="fg"><label>Email Address</label><input type="email" id="cem" placeholder="you@organisation.com"></div>',
'<div class="fg"><label>Phone (optional)</label><input type="tel" id="cph" placeholder="+44 7700 000000"></div>',
'<div class="fg"><label>Organisation</label><input type="text" id="corg" placeholder="e.g. Ofcom / Meta UK / St Mary\'s Academy"></div>',
'<div class="fg"><label>Message</label><textarea id="cmsg" placeholder="Tell us what you need..."></textarea></div>',
'<button class="btn-submit" id="contact-btn" onclick="sendContact()">Send Message &rarr;</button>',
'<div class="msg-err" id="contact-err"></div>',
'<div class="msg-ok" id="contact-ok"></div>',
'</div></div>',
COMMON_FOOTER,
"<script>",
"async function sendContact(){",
"  var fn=document.getElementById('cfn').value.trim();",
"  var ln=document.getElementById('cln').value.trim();",
"  var em=document.getElementById('cem').value.trim();",
"  var ph=document.getElementById('cph').value.trim();",
"  var org=document.getElementById('corg').value.trim();",
"  var msg=document.getElementById('cmsg').value.trim();",
"  var err=document.getElementById('contact-err');",
"  var ok=document.getElementById('contact-ok');",
"  var btn=document.getElementById('contact-btn');",
"  err.classList.remove('show');ok.classList.remove('show');",
"  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}",
"  if(!msg){err.textContent='Please enter a message.';err.classList.add('show');return;}",
"  btn.textContent='Sending\u2026';btn.disabled=true;",
"  try{",
"    var r=await fetch('/contact',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:fn+' '+ln,email:em,phone:ph,org:org,message:msg})});",
"    var d=await r.json();",
"    if(d.ok){ok.textContent='Message sent. Justin will respond within 24 hours.';ok.classList.add('show');btn.textContent='Sent \u2713';}",
"    else{err.textContent='Error sending. Email justin@monopcontent.com directly.';err.classList.add('show');btn.textContent='Send Message \u2192';btn.disabled=false;}",
"  }catch(e){err.textContent='Could not reach server. Email justin@monopcontent.com directly.';err.classList.add('show');btn.textContent='Send Message \u2192';btn.disabled=false;}",
"}",
"</script></body></html>"
])

# ============================================================================
# HTTP SERVER
# ============================================================================
class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type, Authorization, X-API-Key")
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path.rstrip("/")
        track_request()
        if path in ("","/"): send_html(self,LANDING)
        elif path=="/scan": send_html(self,SCAN_PAGE)
        elif path=="/contact": send_html(self,CONTACT_PAGE)
        elif path=="/api/health": send_json(self,{"status":"ok","version":VERSION,"rps":get_rps(),"throttle":is_overloaded()})
        elif path=="/api/verify-chain": send_json(self,verify_chain())
        elif path=="/api/stats":
            with _db_lock:
                keys=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                audits=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                loads=_conn.execute("SELECT COUNT(*) FROM load_log").fetchone()[0]
                contacts=_conn.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0]
            send_json(self,{"api_keys":keys,"audit_blocks":audits,"load_events":loads,"contacts":contacts,"rps":get_rps(),"throttle":is_overloaded(),"version":VERSION})
        elif path=="/robots.txt": send_html(self,"User-agent: *\nAllow: /\n")
        elif path=="/openapi.json": send_json(self,{"openapi":"3.0.0","info":{"title":"AILeash Platform","version":VERSION},"servers":[{"url":"https://sebbi.pro"}]})
        elif path in ("/ai-plugin.json","/.well-known/ai-plugin.json"):
            send_json(self,{"schema_version":"v1","name_for_human":"AILeash","name_for_model":"aileash","description_for_model":"AI governance and child safety API.","api":{"type":"openapi","url":"https://sebbi.pro/openapi.json"},"contact_email":OWNER_EMAIL})
        else: send_json(self,{"error":"not_found"},404)

    def do_POST(self):
        path=urlparse(self.path).path.rstrip("/")
        data=read_body(self)
        track_request()
        if is_overloaded() and path not in ("/api/govern","/govern"):
            send_json(self,{"error":"server_busy","message":"High load. Try again shortly.","rps":get_rps()},503)
            return

        if path in ("/api/govern","/govern"):
            api_key=get_api_key(self)
            try:
                result,status=govern(data,api_key if api_key else None)
                send_json(self,result,status)
            except ValueError as e: send_json(self,{"error":str(e)},400)
            except Exception as e:  send_json(self,{"error":"internal_error","detail":str(e)},500)

        elif path in ("/signup","/api/keys"):
            email   =str(data.get("email","")).strip().lower()
            phone   =str(data.get("phone","")).strip()
            name    =str(data.get("name","")).strip()
            org     =str(data.get("org","")).strip()
            org_type=str(data.get("org_type","")).strip()
            product =str(data.get("product","aileash")).strip().lower()
            devices =int(data.get("devices",1))
            if product not in ("aileash","guardian"): product="aileash"
            if devices<1: devices=1
            key,err=create_api_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email. Contact justin@monopcontent.com to retrieve it."}
                send_json(self,{"error":msgs.get(err,err)},400); return
            monthly=round(devices*0.50,2)
            threading.Thread(target=send_welcome_email,args=(name,email,product,key,devices,monthly),daemon=True).start()
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"plan":"free","quota":FREE_QUOTA,"endpoint":f"{HOST}/api/govern","message":f"100 free decisions included. After trial: \u00a3{monthly}/month for {devices} device(s) via Stripe."})

        elif path=="/contact":
            name =str(data.get("name","")).strip()
            email=str(data.get("email","")).strip().lower()
            phone=str(data.get("phone","")).strip()
            org  =str(data.get("org","")).strip()
            msg  =str(data.get("message","")).strip()
            if not email or "@" not in email:
                send_json(self,{"error":"invalid_email"},400); return
            if not msg:
                send_json(self,{"error":"no_message"},400); return
            with _db_lock:
                _conn.execute("INSERT INTO contact_log(ts,name,email,phone,org,message) VALUES(?,?,?,?,?,?)",
                    (time.time(),name,email,phone,org,msg))
                _conn.commit()
            threading.Thread(target=send_contact_notification,args=(name,email,phone,org,msg),daemon=True).start()
            send_json(self,{"ok":True})

        elif path=="/create-checkout":
            email  =str(data.get("email","")).strip().lower()
            product=str(data.get("product","aileash")).strip().lower()
            devices=int(data.get("devices",1))
            if devices<1: devices=1
            if not email or "@" not in email: send_json(self,{"error":"invalid_email"},400); return
            if not STRIPE_SECRET: send_json(self,{"error":"stripe_not_configured"},503); return
            price_id=STRIPE_PRICE_ID_GUARDIAN if product=="guardian" else STRIPE_PRICE_ID_AILEASH
            if not price_id:
                setup_stripe()
                price_id=STRIPE_PRICE_ID_GUARDIAN if product=="guardian" else STRIPE_PRICE_ID_AILEASH
            if not price_id: send_json(self,{"error":"stripe_setup_failed"},503); return
            session=stripe_call("POST","/checkout/sessions",{
                "mode":"subscription","customer_email":email,
                "success_url":f"{HOST}/?success=true","cancel_url":f"{HOST}/?cancel=true",
                "line_items[0][price]":price_id,"line_items[0][quantity]":str(devices)
            })
            if not session or "url" not in session:
                send_json(self,{"error":"checkout_failed","detail":str(session)},500); return
            send_json(self,{"checkout_url":session["url"]})

        else: send_json(self,{"error":"not_found"},404)

if __name__=="__main__":
    print(f"AILeash Platform v{VERSION} starting on port {PORT}",flush=True)
    setup_stripe()
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print(f"Ready. Fair use: {RATE_LIMIT_PER_MIN}/min {RATE_LIMIT_PER_HOUR}/hr per key. Global throttle: {GLOBAL_RATE_PER_SEC} req/s",flush=True)
    server.serve_forever()
