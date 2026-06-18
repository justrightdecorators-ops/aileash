# ==============================================================================
# AILEASH PLATFORM v5.0.0
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================

import json, math, time, sqlite3, hashlib, threading, hmac
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

PORT           = int(os.environ.get("PORT", 8080))
STRIPE_SECRET  = os.environ.get("STRIPE_SECRET", "")
BREVO_API_KEY  = os.environ.get("BREVO_API_KEY", "")
HOST           = os.environ.get("HOST", "https://sebbi.pro")
DB             = "aileash.db"
VERSION        = "5.0.0"
OWNER_NAME     = "Justin Antony Dobson"
OWNER_EMAIL    = "justin@monopcontent.com"
OWNER_PHONE    = "07908 269428"
SAFE_COUNTRIES = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS= {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA     = 100
RATE_PER_MIN   = 60
RATE_PER_HOUR  = 1000
GLOBAL_RPS     = 200

STRIPE_PRICE_AILEASH  = ""
STRIPE_PRICE_GUARDIAN = ""
_db_lock   = threading.Lock()
_load_lock = threading.Lock()
_req_times = deque()
_overloaded = False
_key_wins  = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock  = threading.Lock()

# ============================================================================
# DATABASE
# ============================================================================
def get_conn():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS api_keys(
        key TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT, org TEXT,
        org_type TEXT, product TEXT DEFAULT 'aileash', devices INTEGER DEFAULT 1,
        stripe_customer TEXT DEFAULT '', stripe_sub TEXT DEFAULT '',
        actions_used INTEGER DEFAULT 0, created REAL,
        active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 100, plan_type TEXT DEFAULT 'free')""")
    c.execute("""CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY, v TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS load_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, rps REAL, note TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS contact_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, name TEXT,
        email TEXT, phone TEXT, org TEXT, message TEXT)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.commit()
    return c

_conn = get_conn()

# ============================================================================
# LOAD TRACKING
# ============================================================================
def track_request():
    global _overloaded
    t = time.time()
    with _load_lock:
        _req_times.append(t)
        while _req_times and _req_times[0] < t - 1.0:
            _req_times.popleft()
        rps = len(_req_times)
        if rps > GLOBAL_RPS and not _overloaded:
            _overloaded = True
            try:
                _conn.execute("INSERT INTO load_log(ts,rps,note) VALUES(?,?,?)", (t,rps,"THROTTLE"))
                _conn.commit()
            except Exception: pass
        elif rps < GLOBAL_RPS * 0.7 and _overloaded:
            _overloaded = False

def is_overloaded():
    with _load_lock: return _overloaded

def get_rps():
    t = time.time()
    with _load_lock: return sum(1 for x in _req_times if x >= t - 1.0)

# ============================================================================
# RATE LIMITING
# ============================================================================
def check_rate(key):
    t = time.time()
    with _key_lock:
        w = _key_wins[key]
        while w["min"]  and w["min"][0]  < t - 60:   w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600: w["hour"].popleft()
        if len(w["min"])  >= RATE_PER_MIN:  return False, "rate_limit_minute"
        if len(w["hour"]) >= RATE_PER_HOUR: return False, "rate_limit_hour"
        w["min"].append(t); w["hour"].append(t)
        return True, None

# ============================================================================
# EMAIL
# ============================================================================
def send_email(to_email, to_name, subject, html):
    if not BREVO_API_KEY:
        print(f"EMAIL SKIP: {to_email}", flush=True); return
    try:
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps({"sender":{"name":"AILeash","email":"noreply@monopcontent.com"},
                "to":[{"email":to_email,"name":to_name}],"subject":subject,"htmlContent":html}).encode(),
            headers={"api-key":BREVO_API_KEY,"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req, timeout=10): pass
        print(f"EMAIL OK: {to_email}", flush=True)
    except Exception as e:
        print(f"EMAIL ERR: {e}", flush=True)

def welcome_email(name, email, product, key, devices, monthly):
    pn = "AILeash Guardian" if product == "guardian" else "AILeash"
    html = f"""<html><body style="font-family:Arial,sans-serif;background:#f5f7fa;padding:20px">
<div style="max-width:580px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden">
<div style="background:#0a0f1e;padding:32px;border-bottom:4px solid #c9a84c">
<div style="font-size:22px;color:#fff;font-weight:900">AILeash <span style="color:#c9a84c">Platform</span></div>
<div style="font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px;font-family:monospace;letter-spacing:2px;text-transform:uppercase">{pn} — Key Created</div>
</div>
<div style="padding:36px">
<div style="font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:16px">Welcome{", " + name.split()[0] if name.strip() else ""}.</div>
<p style="font-size:14px;color:#64748b;line-height:1.7">Your {pn} API key is ready. 100 free decisions included. After trial: £{monthly:.2f}/month for {devices} device{"s" if devices!=1 else ""} via Stripe.</p>
<div style="background:#0a0f1e;border-radius:6px;padding:20px;margin:20px 0">
<div style="font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">Your API Key — Save This Now</div>
<div style="font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all">{key}</div>
</div>
<div style="background:#f5f7fa;border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:20px;font-size:13px;color:#64748b;line-height:1.7">
<strong style="color:#0a0f1e">Billing:</strong> {pn} · {devices} device{"s" if devices!=1 else ""} · £{monthly:.2f}/month
</div>
<div style="background:#0a0f1e;border-radius:6px;padding:20px;margin-bottom:20px">
<div style="font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px">Quick Start</div>
<div style="font-family:monospace;font-size:12px;color:#ccc;line-height:2">
POST {HOST}/api/govern<br>
Authorization: Bearer {key[:20]}...<br>
Content-Type: application/json<br><br>
<span style="color:#00ff88">Response: ALLOW / CHALLENGE / BLOCK + SHA-256 audit hash</span>
</div>
</div>
<p style="font-size:13px;color:#64748b"><strong>{OWNER_NAME}</strong><br>
<a href="mailto:{OWNER_EMAIL}" style="color:#c9a84c">{OWNER_EMAIL}</a> · {OWNER_PHONE}</p>
</div>
<div style="text-align:center;padding:20px;font-size:12px;color:#94a3b8">
© 2026 Monop Content · Blyth, UK · <a href="{HOST}" style="color:#c9a84c">sebbi.pro</a>
</div>
</div></body></html>"""
    send_email(email, name, f"Your {pn} API Key", html)

def contact_email(name, email, phone, org, message):
    html = f"""<html><body style="font-family:Arial,sans-serif;padding:20px;color:#333">
<h2 style="color:#0a0f1e">New Contact: {name}</h2>
<p><strong>Email:</strong> {email}</p>
<p><strong>Phone:</strong> {phone}</p>
<p><strong>Organisation:</strong> {org}</p>
<p><strong>Message:</strong><br>{message}</p>
</body></html>"""
    send_email(OWNER_EMAIL, OWNER_NAME, f"Contact: {name}", html)

# ============================================================================
# STRIPE
# ============================================================================
def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET: return None
    try:
        req = urllib.request.Request(
            "https://api.stripe.com/v1" + endpoint,
            data=urllib.parse.urlencode(data).encode() if data else None,
            headers={"Authorization":"Bearer "+STRIPE_SECRET,"Content-Type":"application/x-www-form-urlencoded"},
            method=method)
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except: return None
    except Exception as e:
        print(f"Stripe: {e}", flush=True); return None

def make_price(name, desc):
    p = stripe_call("POST","/products",{"name":name,"description":desc})
    if not p or "id" not in p: return None
    pr = stripe_call("POST","/prices",{"product":p["id"],"currency":"gbp","unit_amount":50,"recurring[interval]":"month"})
    return pr["id"] if pr and "id" in pr else None

def setup_stripe():
    global STRIPE_PRICE_AILEASH, STRIPE_PRICE_GUARDIAN
    if not STRIPE_SECRET: print("No STRIPE_SECRET",flush=True); return
    with _db_lock:
        ra = _conn.execute("SELECT v FROM config WHERE k='price_aileash'").fetchone()
        rg = _conn.execute("SELECT v FROM config WHERE k='price_guardian'").fetchone()
    if ra and ra[0]: STRIPE_PRICE_AILEASH = ra[0]
    else:
        pid = make_price("AILeash","AI governance. 50p per device per month.")
        if pid:
            STRIPE_PRICE_AILEASH = pid
            with _db_lock:
                _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('price_aileash',?)",(pid,))
                _conn.commit()
    if rg and rg[0]: STRIPE_PRICE_GUARDIAN = rg[0]
    else:
        pid = make_price("AILeash Guardian","Child safety. 50p per device per month.")
        if pid:
            STRIPE_PRICE_GUARDIAN = pid
            with _db_lock:
                _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('price_guardian',?)",(pid,))
                _conn.commit()
    print(f"Stripe ready. AILeash:{STRIPE_PRICE_AILEASH[:12] if STRIPE_PRICE_AILEASH else 'none'} Guardian:{STRIPE_PRICE_GUARDIAN[:12] if STRIPE_PRICE_GUARDIAN else 'none'}",flush=True)

# ============================================================================
# KEY MANAGEMENT
# ============================================================================
def create_key(email, phone="", name="", org="", org_type="", product="aileash", devices=1):
    email = str(email).strip().lower()
    if not email or "@" not in email: return None, "invalid_email"
    key = ("ag_live_" if product=="guardian" else "al_live_") + secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("""INSERT INTO api_keys(key,email,phone,name,org,org_type,product,
                devices,stripe_customer,stripe_sub,actions_used,created,active,is_paid,free_quota,plan_type)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key,email,phone,name,org,org_type,product,devices,"","",0,time.time(),1,0,FREE_QUOTA,"free"))
            _conn.commit()
        except sqlite3.IntegrityError: return None, "email_exists"
    return key, None

def get_key(key):
    with _db_lock:
        return _conn.execute(
            "SELECT email,actions_used,active,is_paid,free_quota,plan_type,product FROM api_keys WHERE key=?",
            (key,)).fetchone()

def inc_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?",(key,))
        _conn.commit()

# ============================================================================
# RISK ENGINE
# ============================================================================
W60S=defaultdict(deque); W5M=defaultdict(deque); W1H=defaultdict(deque)

def now(): return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def upd_vel(uid):
    t=now()
    for q in [W60S[uid],W5M[uid],W1H[uid]]: q.append(t)
    c=now()
    while W60S[uid] and W60S[uid][0]<c-60: W60S[uid].popleft()
    while W5M[uid]  and W5M[uid][0] <c-300: W5M[uid].popleft()
    while W1H[uid]  and W1H[uid][0] <c-3600: W1H[uid].popleft()

def vel(uid): return {"60s":len(W60S[uid]),"5m":len(W5M[uid]),"1h":len(W1H[uid])}

def load_user(uid):
    with _db_lock:
        r=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?",(uid,)).fetchone()
    return {"trust":r[0],"last_country":r[1]} if r else {"trust":0.5,"last_country":None}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute("""INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country""",
            (uid,trust,country))
        _conn.commit()

def score_event(s):
    reasons=[]
    sc  = (1-s["trust"])*0.30
    v60 = s["v60"]
    sc += min(v60/20,1)*0.15
    if v60>10: reasons.append("velocity_spike")
    sc += min(s["v5m"]/50,1)*0.10
    sc += min(s["v1h"]/200,1)*0.10
    amt = float(s.get("amount",0))
    sc += min(math.log1p(amt)/math.log1p(10000),1)*0.15
    if amt>500: reasons.append("high_amount")
    dr = float(s.get("device_risk",0))
    sc += dr*0.10
    if dr>0.5: reasons.append("risky_device")
    an = float(s.get("anomaly",0))
    sc += an*0.10
    if an>0.5: reasons.append("behaviour_anomaly")
    if s.get("country_shift"):  sc+=0.10; reasons.append("country_shift")
    if s.get("unsafe_country"): sc+=0.10; reasons.append("unsafe_country")
    if s["trust"]<0.4: reasons.append("low_trust")
    return round(clamp(sc),4), reasons

def decide(sc):
    if sc<0.35: return "ALLOW"
    if sc<0.70: return "CHALLENGE"
    return "BLOCK"

def upd_trust(t,d):
    if d=="ALLOW":     t+=(1-t)*0.01
    elif d=="CHALLENGE": t-=t*0.02
    elif d=="BLOCK":   t-=t*0.08
    return clamp(t,0.05,1.0)

def chain_tip():
    with _db_lock:
        r=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else "GENESIS"

def seal(event,result,ts):
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
        p={"prev_hash":row[2],"ts":row[4],"event":json.loads(row[0]),"result":json.loads(row[1])}
        if sha(p)!=row[3] or row[2]!=prev:
            return {"valid":False,"broken_at":i,"message":f"Tampered at block {i}"}
        prev=row[3]
    return {"valid":True,"blocks":len(rows),"tip":rows[-1][3],"message":"Chain intact"}

def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - event.keys()
    if missing: raise ValueError(f"Missing: {missing}")
    if api_key:
        ok,ec = check_rate(api_key)
        if not ok: return {"error":ec},429
        ki = get_key(api_key)
        if not ki: return {"error":"invalid_api_key"},401
        email,used,active,is_paid,quota,plan,product = ki
        if not active: return {"error":"account_inactive"},403
        if not is_paid and used>=quota:
            return {"error":"quota_exceeded","message":f"Upgrade at {HOST}/#pricing"},429
    ts=now(); uid=event["user_id"]
    state=load_user(uid); upd_vel(uid); v=vel(uid)
    country=event["country"]
    signals={
        "trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],
        "amount":float(event.get("amount",0)),"device_risk":float(event.get("device_risk",0)),
        "anomaly":float(event.get("anomaly",0)),
        "country_shift":state["last_country"] is not None and state["last_country"]!=country,
        "unsafe_country":country not in SAFE_COUNTRIES
    }
    sc,reasons=score_event(signals)
    dec=decide(sc)
    trust=upd_trust(state["trust"],dec)
    save_user(uid,trust,country)
    result={"decision":dec,"score":sc,"trust":round(trust,4),"reasons":reasons,"version":VERSION,"timestamp":ts}
    result["audit_hash"]=seal(event,result,ts)
    if api_key: inc_usage(api_key)
    return result,200

# ============================================================================
# HTTP
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
    body=html.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Content-Length",str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def read_body(h):
    n=int(h.headers.get("Content-Length",0))
    if n:
        try: return json.loads(h.rfile.read(n))
        except: return {}
    return {}

def get_bearer(h):
    auth=h.headers.get("Authorization","")
    if auth.startswith("Bearer "): return auth[7:]
    return h.headers.get("X-API-Key","").strip()

# ============================================================================
# PAGES — FONTS + CSS
# ============================================================================
FONTS = '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">'

CSS_VARS = """
:root{--navy:#0a0f1e;--navy2:#111827;--gold:#c9a84c;--gold2:#e8c96a;--red:#cc0000;
--green:#00875a;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--text:#1a202c;
--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{background:var(--white);color:var(--text);font-family:var(--sans);overflow-x:hidden}
"""

CSS_NAV = """
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:var(--navy);
padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between}
.nav-logo{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900}
.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}
.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 20px;font-weight:700!important;border-radius:4px}
"""

CSS_BTNS = """
.btn-gold{background:var(--gold);color:var(--navy);padding:14px 28px;border:none;font-family:var(--sans);
font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}
.btn-gold:hover{background:var(--gold2);transform:translateY(-2px)}
.btn-red{background:var(--red);color:var(--white);padding:14px 28px;border:none;font-family:var(--sans);
font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}
.btn-red:hover{background:#aa0000;transform:translateY(-2px)}
.btn-ghost{background:transparent;color:var(--white);padding:14px 28px;border:1px solid rgba(255,255,255,0.2);
font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;text-decoration:none;
border-radius:4px;display:inline-block;transition:all .2s}
.btn-ghost:hover{border-color:var(--gold);color:var(--gold)}
"""

CSS_FORMS = """
.fg{margin-bottom:12px}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);
letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select,.fg textarea{width:100%;background:var(--off);border:2px solid var(--border);
color:var(--text);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;
transition:border-color .2s;border-radius:4px}
.fg input:focus,.fg select:focus,.fg textarea:focus{border-color:var(--navy)}
.fg input::placeholder,.fg textarea::placeholder{color:#bbb}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.msg-err{display:none;color:var(--red);font-family:var(--mono);font-size:11px;margin-top:10px;
padding:10px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}
.msg-err.show{display:block}
.msg-ok{display:none;color:var(--green);font-family:var(--mono);font-size:11px;margin-top:10px;
padding:10px;background:#f0fff8;border-radius:4px;border:1px solid #bbf7d0}
.msg-ok.show{display:block}
"""

CSS_FOOTER = """
footer{background:var(--navy2);padding:52px 48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;gap:40px}
.foot-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;margin-bottom:4px}
.foot-logo span{color:var(--gold)}
.foot-tag{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.15);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.foot-desc{font-size:12px;color:rgba(255,255,255,0.18);line-height:1.7}
.foot-col h4{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);text-transform:uppercase;margin-bottom:10px}
.foot-col a{display:block;color:rgba(255,255,255,0.18);text-decoration:none;font-size:12px;margin-bottom:6px;transition:color .2s}
.foot-col a:hover{color:var(--white)}
.foot-bottom{max-width:1200px;margin:32px auto 0;padding-top:18px;border-top:1px solid rgba(255,255,255,0.04);
display:flex;justify-content:space-between;font-size:10px;color:rgba(255,255,255,0.12);font-family:var(--mono)}
"""

CSS_MISC = """
h1{font-family:var(--display);font-size:clamp(44px,5vw,72px);line-height:1.05;color:var(--white);font-weight:900;margin:16px 0 20px}
h1 em{color:var(--gold);font-style:normal}
h2{font-family:var(--display);font-size:clamp(32px,3.5vw,50px);font-weight:900;margin-bottom:14px;line-height:1.1}
h2 em{color:var(--gold);font-style:normal}
.slbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;opacity:.4}
.sec-sub{font-size:15px;color:var(--muted);max-width:580px;line-height:1.7;margin-bottom:44px}
.sec{padding:80px 48px;border-bottom:1px solid var(--border)}
.sec-inner{max-width:1200px;margin:0 auto}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.4)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
"""

CSS_RESPONSIVE = """
@media(max-width:900px){
nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
h1{font-size:clamp(36px,8vw,56px)}
.hero{padding:52px 20px 68px!important}
.two-col,.fg-row,.product-cards,.price-cards,.comp-grid,.threat-grid,.fair-grid,.engine-grid,.engine-compare{grid-template-columns:1fr!important}
.stats-inner{grid-template-columns:repeat(3,1fr)!important}
.sec,.guardian-sec,.compliance-sec,.fair-sec,.pricing-sec,.signup-sec,.engine-sec,.contact-sec{padding:52px 20px!important}
footer{padding:40px 20px}.foot-inner{grid-template-columns:1fr}.foot-bottom{flex-direction:column;gap:6px}
.node-visual{grid-template-columns:repeat(2,1fr)!important}
.contact-wrap{grid-template-columns:1fr!important;padding:52px 20px!important}
.owner-card{position:static!important}
}
"""

NAV_HTML = """<nav>
  <div class="nav-logo">AILeash <span>Platform</span></div>
  <div class="nav-links">
    <a href="/">Home</a>
    <a href="/#governance">Governance</a>
    <a href="/#guardian">Guardian</a>
    <a href="/#engine">The Engine</a>
    <a href="/scan">AI Act Scanner</a>
    <a href="/contact">Contact</a>
    <a href="/#signup" class="nav-cta">Get Started</a>
  </div>
</nav>"""

FOOTER_HTML = """<footer>
  <div class="foot-inner">
    <div>
      <div class="foot-logo">AILeash <span>Platform</span></div>
      <div class="foot-tag">Monop Content &middot; Blyth, UK</div>
      <p class="foot-desc">AI governance and child safety. Two products. One engine. 50p per device per month.</p>
    </div>
    <div class="foot-col"><h4>Products</h4>
      <a href="/#governance">AILeash</a><a href="/#guardian">Guardian</a>
      <a href="/#engine">The Engine</a><a href="/scan">AI Act Scanner</a><a href="/#pricing">Pricing</a>
    </div>
    <div class="foot-col"><h4>Company</h4>
      <a href="/contact">Contact</a>
      <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a>
      <a href="#">Privacy Policy</a><a href="#">Terms of Service</a>
    </div>
    <div class="foot-col"><h4>Get In Touch</h4>
      <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a>
      <a href="tel:07908269428">07908 269428</a>
      <a href="/#signup">Get API Key</a>
    </div>
  </div>
  <div class="foot-bottom">
    <span>&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK &middot; v5.0.0</span>
    <span>EU AI Act &middot; Online Safety Act &middot; ICO Children's Code &middot; DSA</span>
  </div>
</footer>"""

def page_shell(title, desc, body_css, body_html):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
{FONTS}
<style>
{CSS_VARS}{CSS_NAV}{CSS_BTNS}{CSS_FORMS}{CSS_FOOTER}{CSS_MISC}
{body_css}
{CSS_RESPONSIVE}
</style>
</head>
<body>
{NAV_HTML}
{body_html}
{FOOTER_HTML}
</body>
</html>"""

# ============================================================================
# LANDING PAGE
# ============================================================================
LANDING_CSS = """
.alert-bar{background:var(--red);padding:11px 48px;text-align:center;font-family:var(--mono);
font-size:11px;color:var(--white);letter-spacing:1px;text-transform:uppercase;margin-top:68px}
.alert-bar strong{color:#e8c96a}
.hero{background:var(--navy);padding:80px 48px 100px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 15% 60%,rgba(201,168,76,0.06) 0%,transparent 55%)}
.hero-inner{max-width:1200px;margin:0 auto;position:relative;z-index:1;text-align:center}
.kdot{display:inline-block;width:7px;height:7px;background:var(--red);border-radius:50%;animation:blink 1.5s infinite;margin-right:8px;vertical-align:middle}
.ktext{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;vertical-align:middle}
.hero-sub{font-size:18px;color:rgba(255,255,255,0.5);line-height:1.75;max-width:620px;margin:0 auto 40px}
.product-cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;max-width:880px;margin:0 auto 48px}
.pc{border-radius:8px;padding:28px;text-align:left;position:relative;overflow:hidden;cursor:pointer;transition:all .2s}
.pc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.pc-leash{background:rgba(201,168,76,0.07);border:1px solid rgba(201,168,76,0.2)}.pc-leash::before{background:var(--gold)}
.pc-guardian{background:rgba(204,0,0,0.07);border:1px solid rgba(204,0,0,0.2)}.pc-guardian::before{background:var(--red)}
.pc-leash:hover{border-color:rgba(201,168,76,0.5)}.pc-guardian:hover{border-color:rgba(204,0,0,0.5)}
.pc-badge{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.pc-leash .pc-badge{color:var(--gold)}.pc-guardian .pc-badge{color:#ff6b6b}
.pc h3{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900;margin-bottom:6px}
.pc p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.6;margin-bottom:12px}
.pc-tags{display:flex;flex-wrap:wrap;gap:5px}
.ptag{font-family:var(--mono);font-size:9px;padding:2px 8px;border-radius:2px}
.pc-leash .ptag{background:rgba(201,168,76,0.1);color:var(--gold);border:1px solid rgba(201,168,76,0.2)}
.pc-guardian .ptag{background:rgba(204,0,0,0.1);color:#ff6b6b;border:1px solid rgba(204,0,0,0.2)}
.hero-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.divider{height:4px;background:linear-gradient(90deg,var(--navy) 0%,var(--gold) 50%,var(--red) 100%)}
.stats-strip{background:var(--navy)}
.stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}
.stat{padding:28px 20px;border-right:1px solid rgba(255,255,255,0.05);text-align:center}.stat:last-child{border:none}
.stat-n{font-family:var(--display);font-size:36px;color:var(--gold);font-weight:900}
.stat-l{font-size:10px;color:rgba(255,255,255,0.25);margin-top:4px;letter-spacing:1px;text-transform:uppercase}
.feature-block{margin-bottom:36px}
.fb-icon{font-size:24px;margin-bottom:8px}
.fb-lbl{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:5px}
.feature-block h3{font-family:var(--display);font-size:19px;font-weight:800;margin-bottom:6px;color:var(--navy)}
.feature-block p{font-size:13px;color:var(--muted);line-height:1.65}
.signal-list{display:flex;flex-direction:column;gap:8px}
.sig{display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--off);border:1px solid var(--border);border-radius:4px}
.sig-bar-wrap{width:80px;height:4px;background:var(--border);border-radius:2px;flex-shrink:0}
.sig-bar{height:100%;border-radius:2px;background:var(--gold)}
.sig-name{font-size:12px;color:var(--text);flex:1}
.sig-pct{font-family:var(--mono);font-size:11px;color:var(--gold);font-weight:600;flex-shrink:0}
.dec-flow{display:flex;flex-direction:column;gap:8px;margin-top:20px}
.df{padding:14px 16px;border-radius:4px}
.df-allow{background:rgba(0,135,90,0.06);border:1px solid rgba(0,135,90,0.2)}
.df-challenge{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2)}
.df-block{background:rgba(204,0,0,0.06);border:1px solid rgba(204,0,0,0.2)}
.df-v{font-family:var(--display);font-size:18px;font-weight:900;margin-bottom:3px}
.df-allow .df-v{color:var(--green)}.df-challenge .df-v{color:#b45309}.df-block .df-v{color:var(--red)}
.df-d{font-size:12px;color:var(--muted);line-height:1.5}
.df-t{font-family:var(--mono);font-size:9px;margin-top:4px;color:var(--muted);opacity:.5}
.guardian-sec{background:var(--navy2);padding:80px 48px;border-top:4px solid var(--red)}
.guardian-inner{max-width:1200px;margin:0 auto}
.threat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.03);margin-top:36px}
.tc{background:var(--navy);padding:24px;position:relative}
.tc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.tc-r::before{background:var(--red)}.tc-g::before{background:var(--gold)}.tc-n::before{background:#3b82f6}
.tc-gr::before{background:var(--green)}.tc-b::before{background:#7c3aed}.tc-p::before{background:#ec4899}
.tc-icon{font-size:24px;margin-bottom:8px}
.tc-lbl{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:5px}
.tc h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:6px;color:var(--white)}
.tc p{font-size:12px;color:rgba(255,255,255,0.35);line-height:1.6}
.tc-tags{margin-top:8px;display:flex;flex-wrap:wrap;gap:4px}
.ttag{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);padding:2px 7px;font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);border-radius:2px}
.engine-sec{padding:80px 48px;background:var(--navy);border-top:4px solid var(--gold)}
.engine-inner{max-width:1200px;margin:0 auto}
.engine-hero{text-align:center;margin-bottom:56px}
.engine-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-bottom:40px}
.eg{background:var(--navy2);padding:28px;position:relative}
.eg::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--gold)}
.eg-num{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.eg h3{font-family:var(--display);font-size:19px;color:var(--white);font-weight:900;margin-bottom:8px}
.eg p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.65}
.engine-compare{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:40px}
.ec{border-radius:8px;padding:28px}
.ec-old{background:rgba(204,0,0,0.07);border:1px solid rgba(204,0,0,0.2)}
.ec-new{background:rgba(201,168,76,0.07);border:1px solid rgba(201,168,76,0.3)}
.ec-label{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
.ec-old .ec-label{color:#ff6b6b}.ec-new .ec-label{color:var(--gold)}
.ec h3{font-family:var(--display);font-size:19px;font-weight:900;margin-bottom:14px}
.ec-old h3{color:#ff6b6b}.ec-new h3{color:var(--gold)}
.ec-list{display:flex;flex-direction:column;gap:6px}
.ec-item{display:flex;align-items:flex-start;gap:10px;font-size:13px;color:rgba(255,255,255,0.5);padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.ec-old .ec-item::before{content:'X';color:#ff6b6b;font-family:var(--mono);font-size:10px;font-weight:700;flex-shrink:0;margin-top:1px}
.ec-new .ec-item::before{content:'OK';color:var(--gold);font-family:var(--mono);font-size:10px;font-weight:700;flex-shrink:0;margin-top:1px}
.node-visual{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:28px 0}
.node{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.15);border-radius:6px;padding:14px 8px;text-align:center}
.node-icon{font-size:20px;margin-bottom:6px}
.node-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase}
.node-status{font-family:var(--mono);font-size:9px;color:var(--gold);margin-top:4px}
.engine-download{background:rgba(201,168,76,0.08);border:2px solid var(--gold);border-radius:8px;padding:36px;text-align:center}
.ed-title{font-family:var(--display);font-size:30px;color:var(--white);font-weight:900;margin-bottom:10px}
.ed-sub{font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:20px;line-height:1.7;max-width:520px;margin-left:auto;margin-right:auto}
.ed-code{font-family:var(--mono);font-size:12px;color:#00ff88;background:rgba(0,0,0,0.4);padding:12px 20px;border-radius:4px;margin-bottom:20px;display:inline-block;border:1px solid rgba(0,255,136,0.15)}
.ed-btns{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}
.compliance-sec{padding:80px 48px;background:var(--off)}
.comp-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:36px}
.comp-card{background:var(--white);border:1px solid var(--border);padding:24px;border-left:4px solid var(--navy)}
.comp-act{font-family:var(--mono);font-size:9px;color:var(--navy);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;opacity:.4}
.comp-card h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:6px;color:var(--navy)}
.comp-card p{font-size:12px;color:var(--muted);line-height:1.65}
.checks{margin-top:10px;display:flex;flex-direction:column;gap:4px}
.chk{display:flex;align-items:center;gap:7px;font-size:11px;color:var(--muted)}
.chk::before{content:'OK';color:var(--green);font-weight:700;flex-shrink:0;font-family:var(--mono);font-size:9px}
.fair-sec{padding:80px 48px;border-bottom:1px solid var(--border)}
.fair-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:36px}
.fair-card{border:1px solid var(--border);padding:24px;border-top:3px solid var(--navy)}
.fair-card h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:8px;color:var(--navy)}
.fair-card p{font-size:12px;color:var(--muted);line-height:1.65}
.fair-limit{font-family:var(--mono);font-size:11px;color:var(--gold);margin-top:10px;padding:8px 10px;background:var(--off);border-radius:4px;line-height:1.8}
.pricing-sec{padding:80px 48px;background:var(--navy);border-top:4px solid var(--gold)}
.pricing-inner{max-width:880px;margin:0 auto;text-align:center}
.price-cards{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:44px}
.price-card{border-radius:8px;padding:36px 28px;text-align:center}
.price-card.al{background:rgba(201,168,76,0.07);border:2px solid var(--gold)}
.price-card.gu{background:rgba(204,0,0,0.07);border:2px solid var(--red)}
.price-product{font-family:var(--mono);font-size:10px;letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.al .price-product{color:var(--gold)}.gu .price-product{color:#ff6b6b}
.price-big{font-family:var(--display);font-size:64px;font-weight:900;line-height:1;margin-bottom:4px}
.al .price-big{color:var(--gold)}.gu .price-big{color:#ff6b6b}
.price-big sup{font-size:28px;vertical-align:super}
.price-per{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.35);margin-bottom:20px}
.price-example{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.5);background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:4px;padding:10px;margin-bottom:20px;line-height:1.8;text-align:left}
.price-example strong{color:var(--white)}
.price-feats{text-align:left;margin-bottom:24px;display:flex;flex-direction:column;gap:8px}
.pf{display:flex;align-items:center;gap:7px;font-size:12px;color:rgba(255,255,255,0.55);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.pf::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;flex-shrink:0}
.al .pf::before{color:var(--gold)}.gu .pf::before{color:#ff6b6b}
.price-note{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.18);margin-top:12px;letter-spacing:1px}
.signup-sec{padding:80px 48px;background:var(--white);border-top:4px solid var(--gold)}
.signup-inner{max-width:580px;margin:0 auto}
.product-tabs{display:flex;gap:0;margin-bottom:28px;border:2px solid var(--border);border-radius:6px;overflow:hidden}
.stab{flex:1;padding:13px;text-align:center;cursor:pointer;font-family:var(--mono);font-size:10px;
letter-spacing:1px;text-transform:uppercase;font-weight:600;transition:all .2s;
background:var(--white);color:var(--muted);border:none;outline:none}
.stab.al-on{background:var(--navy);color:var(--gold)}
.stab.gu-on{background:var(--red);color:var(--white)}
.price-preview{background:var(--navy);border-radius:6px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between}
.pp-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.35);letter-spacing:1px;text-transform:uppercase}
.pp-amount{font-family:var(--display);font-size:32px;color:var(--gold);font-weight:900}
.pp-amount.gu-col{color:#ff6b6b}
.pp-sub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);margin-top:2px}
.btn-full{width:100%;margin-top:8px;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}
.key-box{display:none;margin-top:20px;background:var(--navy);border-radius:6px;padding:22px}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:#00ff88;word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;border:1px solid rgba(255,255,255,0.05)}
.key-copy{margin-top:8px;background:transparent;border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.3);padding:6px 14px;font-family:var(--mono);font-size:9px;cursor:pointer;transition:all .2s;letter-spacing:1px;text-transform:uppercase;border-radius:4px}
.key-copy:hover{border-color:var(--gold);color:var(--gold)}
.usage-box{margin-top:12px;font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);padding:12px;border-radius:4px;line-height:1.9}
.usage-box em{color:#79b8ff;font-style:normal}
"""

LANDING_JS = """
var AP='leash';
function switchTab(p){
  AP=p;
  document.getElementById('tab-leash').className='stab'+(p==='leash'?' al-on':'');
  document.getElementById('tab-guardian').className='stab'+(p==='guardian'?' gu-on':'');
  var btn=document.getElementById('go-btn');
  if(p==='guardian'){btn.textContent='Get Guardian API Key \u2192';btn.style.background='var(--red)';btn.style.color='var(--white)';}
  else{btn.textContent='Get AILeash API Key \u2192';btn.style.background='var(--gold)';btn.style.color='var(--navy)';}
  document.getElementById('pp-amt').className='pp-amount'+(p==='guardian'?' gu-col':'');
  updatePrice();
}
function updatePrice(){
  var n=parseInt(document.getElementById('dv').value)||0;
  document.getElementById('pp-amt').textContent='\u00a3'+(n*0.5).toFixed(2);
  document.getElementById('pp-sub').textContent=n>0?(n+' device'+(n===1?'':'s')+' \u00d7 50p = \u00a3'+(n*0.5).toFixed(2)+'/mo'):'Enter device count above';
}
async function doSignup(){
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var org=document.getElementById('org').value.trim();
  var ot=document.getElementById('ot').value;
  var dv=parseInt(document.getElementById('dv').value)||1;
  var err=document.getElementById('msg-err');
  var ok=document.getElementById('msg-ok');
  var kb=document.getElementById('key-box');
  var btn=document.getElementById('go-btn');
  err.classList.remove('show');ok.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!ph){err.textContent='Please enter your phone number.';err.classList.add('show');return;}
  btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:ot,product:AP,devices:dv})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      document.getElementById('key-prev').textContent=d.api_key.slice(0,24)+'...';
      kb.classList.add('show');
      ok.textContent='Key created. 100 free decisions included. Taking you to Stripe\u2026';
      ok.classList.add('show');btn.textContent='Key Created \u2713';
      setTimeout(function(){
        fetch('/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({email:em,product:AP,devices:dv})}).then(function(r2){return r2.json();}).then(function(d2){
          if(d2.checkout_url){window.location.href=d2.checkout_url;}
          else{ok.textContent='Key ready. Set up billing at '+window.location.origin+'/#pricing';}
        }).catch(function(){ok.textContent='Key ready. Billing at '+window.location.origin+'/#pricing';});
      },1400);
    }else{
      err.textContent='Error: '+(d.error||'Failed. Email justin@monopcontent.com directly.');
      err.classList.add('show');
      btn.textContent=AP==='guardian'?'Get Guardian API Key \u2192':'Get AILeash API Key \u2192';btn.disabled=false;
    }
  }catch(e){
    err.textContent='Cannot reach server. Email justin@monopcontent.com directly.';
    err.classList.add('show');
    btn.textContent=AP==='guardian'?'Get Guardian API Key \u2192':'Get AILeash API Key \u2192';btn.disabled=false;
  }
}
function copyKey(){
  navigator.clipboard.writeText(document.getElementById('key-val').textContent).then(function(){
    var b=document.querySelector('.key-copy');b.textContent='Copied \u2713';
    setTimeout(function(){b.textContent='Copy Key';},2000);
  });
}
"""

LANDING_BODY = """
<div class="alert-bar"><strong>EU AI Act enforcement: August 2026.</strong> &nbsp;UK Online Safety Act: now in force.&nbsp; <strong>50p per device. Both products. Total coverage.</strong></div>

<section class="hero">
<div class="hero-inner">
  <div><span class="kdot"></span><span class="ktext">Monop Content &middot; Blyth, UK &middot; Live Now</span></div>
  <h1>AI Governance.<br><em>Child Safety.</em><br>One Platform.</h1>
  <p class="hero-sub">Two products. One audit engine. 50p per device per month. Enter your details and you are covered. No technical knowledge required. Platforms, schools, parents, ISPs. Everyone.</p>
  <div class="product-cards">
    <div class="pc pc-leash" onclick="switchTab('leash');document.getElementById('signup').scrollIntoView({behavior:'smooth'})">
      <div class="pc-badge">AILeash &mdash; AI Governance</div>
      <h3>Enterprise AI Governance</h3>
      <p>9-signal risk engine. SHA-256 audit chain. EU AI Act Art.9, 12, 13 compliant. Real-time ALLOW / CHALLENGE / BLOCK.</p>
      <div class="pc-tags"><span class="ptag">EU AI Act</span><span class="ptag">SHA-256 Chain</span><span class="ptag">9 Signals</span><span class="ptag">Real-Time</span></div>
    </div>
    <div class="pc pc-guardian" onclick="switchTab('guardian');document.getElementById('signup').scrollIntoView({behavior:'smooth'})">
      <div class="pc-badge">AILeash Guardian &mdash; Child Safety</div>
      <h3>Child Safety Layer</h3>
      <p>Grooming detection. CSAM intervention. Cross-border risk. Online Safety Act 2023 and ICO Children's Code compliant.</p>
      <div class="pc-tags"><span class="ptag">Online Safety Act</span><span class="ptag">Grooming Detection</span><span class="ptag">CSAM</span><span class="ptag">Ofcom Ready</span></div>
    </div>
  </div>
  <div class="hero-btns">
    <a href="#signup" class="btn-gold" onclick="switchTab('leash')">Get AILeash &rarr;</a>
    <a href="#signup" class="btn-red" onclick="switchTab('guardian')">Get Guardian &rarr;</a>
    <a href="/scan" class="btn-ghost">Free AI Act Scanner</a>
  </div>
</div>
</section>

<div class="divider"></div>

<div class="stats-strip"><div class="stats-inner">
  <div class="stat"><div class="stat-n">9</div><div class="stat-l">Risk Signals</div></div>
  <div class="stat"><div class="stat-n">SHA256</div><div class="stat-l">Audit Chain</div></div>
  <div class="stat"><div class="stat-n">&lt;12ms</div><div class="stat-l">Detection</div></div>
  <div class="stat"><div class="stat-n">24/7</div><div class="stat-l">Always On</div></div>
  <div class="stat"><div class="stat-n">50p</div><div class="stat-l">Per Device</div></div>
</div></div>

<section class="sec" id="governance"><div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">AILeash &mdash; AI Governance</div>
  <h2>Nine-Signal <em>Risk Engine</em></h2>
  <p class="sec-sub">Every AI action scored across nine concurrent signals. Explainable decisions. Tamper-evident audit chain. EU AI Act compliant from day one.</p>
  <div class="two-col"><div>
    <div class="feature-block"><div class="fb-icon">&#9889;</div><div class="fb-lbl">Signals 01&ndash;03</div><h3>Velocity Tracking</h3><p>Three concurrent time windows &mdash; 60 seconds, 5 minutes, 1 hour &mdash; detect spikes before they escalate into real damage.</p></div>
    <div class="feature-block"><div class="fb-icon">&#128274;</div><div class="fb-lbl">Signal 04</div><h3>Adaptive Trust</h3><p>Per-agent trust scores decay on bad decisions and recover on good behaviour. Trust is earned, never assumed.</p></div>
    <div class="feature-block"><div class="fb-icon">&#127758;</div><div class="fb-lbl">Signals 08&ndash;09</div><h3>Geographic Risk</h3><p>Country-shift detection and jurisdiction-based risk weighting. Sudden location changes trigger automatic elevated scoring.</p></div>
  </div><div>
    <p style="font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:14px">Signal Weights</p>
    <div class="signal-list">
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:90%"></div></div><span class="sig-name">Behavioural Trust</span><span class="sig-pct">30%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:75%"></div></div><span class="sig-name">Contact Velocity 60s</span><span class="sig-pct">15%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:75%"></div></div><span class="sig-name">Content / Amount Risk</span><span class="sig-pct">15%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:65%"></div></div><span class="sig-name">Velocity 5 Minutes</span><span class="sig-pct">10%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:65%"></div></div><span class="sig-name">Velocity 1 Hour</span><span class="sig-pct">10%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:50%"></div></div><span class="sig-name">Device Risk</span><span class="sig-pct">10%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:50%"></div></div><span class="sig-name">Behavioural Anomaly</span><span class="sig-pct">10%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:30%;background:#ff6b6b"></div></div><span class="sig-name">Geographic Risk</span><span class="sig-pct" style="color:#ff6b6b">+10%</span></div>
      <div class="sig"><div class="sig-bar-wrap"><div class="sig-bar" style="width:30%;background:#ff6b6b"></div></div><span class="sig-name">Cross-Border</span><span class="sig-pct" style="color:#ff6b6b">+10%</span></div>
    </div>
    <div class="dec-flow">
      <div class="df df-allow"><div class="df-v">ALLOW</div><div class="df-d">Safe. Proceeds. SHA-256 audit record created.</div><div class="df-t">Score &lt; 0.35</div></div>
      <div class="df df-challenge"><div class="df-v">CHALLENGE</div><div class="df-d">Elevated risk. Paused. Human review required.</div><div class="df-t">Score 0.35&ndash;0.70</div></div>
      <div class="df df-block"><div class="df-v">BLOCK</div><div class="df-d">High risk. Halted. Evidence preserved. Referral activated.</div><div class="df-t">Score &gt; 0.70</div></div>
    </div>
  </div></div>
</div></section>

<section class="guardian-sec" id="guardian"><div class="guardian-inner">
  <div class="slbl" style="color:rgba(255,255,255,0.25)">AILeash Guardian &mdash; Child Safety</div>
  <h2 style="color:var(--white)">Every threat. <em>Detected. Stopped.</em></h2>
  <p style="font-size:15px;color:rgba(255,255,255,0.35);max-width:580px;line-height:1.7;margin-bottom:0">Same SHA-256 engine, adapted for child safety. Six harm categories. All detected in real time. Every intervention recorded as legal evidence admissible in UK courts.</p>
  <div class="threat-grid">
    <div class="tc tc-r"><div class="tc-icon">&#127907;</div><div class="tc-lbl">Threat 01</div><h3>Grooming Detection</h3><p>Velocity, trust escalation, isolation attempts and geographic risk combined. Stopped before it starts.</p><div class="tc-tags"><span class="ttag">velocity_spike</span><span class="ttag">trust_escalation</span></div></div>
    <div class="tc tc-g"><div class="tc-icon">&#128172;</div><div class="tc-lbl">Threat 02</div><h3>Harmful Content</h3><p>Anomaly detection flags content deviating from age-appropriate norms. Block triggered before a child sees it.</p><div class="tc-tags"><span class="ttag">content_anomaly</span><span class="ttag">age_mismatch</span></div></div>
    <div class="tc tc-n"><div class="tc-icon">&#129302;</div><div class="tc-lbl">Threat 03</div><h3>Bot and Fake Accounts</h3><p>Automated accounts targeting children identified before first contact. Non-human actors exposed instantly.</p><div class="tc-tags"><span class="ttag">device_risk</span><span class="ttag">behaviour_anomaly</span></div></div>
    <div class="tc tc-gr"><div class="tc-icon">&#129504;</div><div class="tc-lbl">Threat 04</div><h3>Psychological Manipulation</h3><p>Detects coercive control and manufactured dependency. Trust decay identifies dangerous relationships early.</p><div class="tc-tags"><span class="ttag">trust_decay</span><span class="ttag">sentiment_shift</span></div></div>
    <div class="tc tc-b"><div class="tc-icon">&#127758;</div><div class="tc-lbl">Threat 05</div><h3>Cross-Border Risk</h3><p>Flags contact from high-risk jurisdictions. Country shift identifies when domestic contact suddenly operates abroad.</p><div class="tc-tags"><span class="ttag">unsafe_country</span><span class="ttag">country_shift</span></div></div>
    <div class="tc tc-p"><div class="tc-icon">&#128247;</div><div class="tc-lbl">Threat 06</div><h3>CSAM and Image Abuse</h3><p>Integrates with image hash databases. Evidence automatically preserved for law enforcement referral.</p><div class="tc-tags"><span class="ttag">image_hash_match</span><span class="ttag">share_velocity</span></div></div>
  </div>
</div></section>

<section class="engine-sec" id="engine"><div class="engine-inner">
  <div class="engine-hero">
    <div class="slbl" style="color:rgba(255,255,255,0.3)">The Architecture</div>
    <h2 style="color:var(--white)">You don't connect to us.<br><em>You become us.</em></h2>
    <p style="font-size:17px;color:rgba(255,255,255,0.45);max-width:640px;margin:0 auto;line-height:1.75">Every customer gets their own sovereign governance engine. It runs on your hardware. Your data never leaves your network. No central server. No single point of failure. No infrastructure bottleneck. Just your engine, your chain, your compliance &mdash; forever.</p>
  </div>
  <div class="engine-grid">
    <div class="eg"><div class="eg-num">What you get</div><h3>Your Own Engine</h3><p>When you sign up you download a single Python file. That file IS the governance engine. Nine-signal risk scoring, SHA-256 Merkle audit chain, EU AI Act compliance mapping &mdash; all running locally on your hardware.</p></div>
    <div class="eg"><div class="eg-num">Your data</div><h3>Stays With You</h3><p>Every audit record, every decision, every piece of evidence is sealed to a cryptographic chain that lives on your machine. Not our cloud. Not our servers. Yours. We cannot read it, alter it, or lose it.</p></div>
    <div class="eg"><div class="eg-num">How it scales</div><h3>Replicates Itself</h3><p>Need to protect 2,000 devices across 50 locations? The engine clones itself to each node with a single cryptographic handshake. No deployment team. No central installation server. Automatic.</p></div>
    <div class="eg"><div class="eg-num">Your cost</div><h3>50p Per Device</h3><p>Because we have near-zero infrastructure costs at your scale, we pass that directly to you. Enterprise vendors charge £50,000 a year for a fraction of this. We charge 50p because the architecture makes it possible.</p></div>
    <div class="eg"><div class="eg-num">The audit chain</div><h3>Court-Admissible</h3><p>Every decision is cryptographically sealed &mdash; timestamp, email, IP, decision &mdash; hashed with SHA-256 into a Merkle chain where tampering breaks every subsequent block. Admissible in UK courts. Verifiable by Ofcom.</p></div>
    <div class="eg"><div class="eg-num">Child safety</div><h3>Guardian Built In</h3><p>Guardian extends the same architecture with child-specific detection &mdash; grooming, CSAM, manipulation, cross-border risk. BLOCK threshold 0.60. CSAM triggers mandatory BLOCK. Evidence preserved instantly for law enforcement.</p></div>
  </div>
  <div class="engine-compare">
    <div class="ec ec-old">
      <div class="ec-label">Every other vendor</div>
      <h3>Centralised. Expensive. Fragile.</h3>
      <div class="ec-list">
        <div class="ec-item">Your data sent to their cloud on every decision</div>
        <div class="ec-item">Single point of failure &mdash; their outage is your breach</div>
        <div class="ec-item">&pound;50,000+ per year enterprise contracts</div>
        <div class="ec-item">Months to deploy &mdash; integration teams required</div>
        <div class="ec-item">You depend on them forever &mdash; lock-in by design</div>
        <div class="ec-item">Audit chain they control &mdash; not you</div>
      </div>
    </div>
    <div class="ec ec-new">
      <div class="ec-label">AILeash</div>
      <h3>Sovereign. Affordable. Unstoppable.</h3>
      <div class="ec-list">
        <div class="ec-item">Your data never leaves your hardware</div>
        <div class="ec-item">No central server &mdash; runs offline if needed</div>
        <div class="ec-item">50p per device per month &mdash; no contracts</div>
        <div class="ec-item">60 seconds to deploy &mdash; one file, one API key</div>
        <div class="ec-item">You own the engine &mdash; we cannot take it away</div>
        <div class="ec-item">Your audit chain &mdash; cryptographically yours</div>
      </div>
    </div>
  </div>
  <div class="node-visual">
    <div class="node"><div class="node-icon">&#127968;</div><div class="node-label">Your HQ</div><div class="node-status">Node 001 Active</div></div>
    <div class="node"><div class="node-icon">&#127982;</div><div class="node-label">Branch Office</div><div class="node-status">Node 002 Replicated</div></div>
    <div class="node"><div class="node-icon">&#127979;</div><div class="node-label">School</div><div class="node-status">Node 003 Replicated</div></div>
    <div class="node"><div class="node-icon">&#128241;</div><div class="node-label">Mobile Fleet</div><div class="node-status">Node 004 Replicated</div></div>
    <div class="node"><div class="node-icon">&#127760;</div><div class="node-label">Remote Site</div><div class="node-status">Node 005 Replicated</div></div>
  </div>
  <div class="engine-download">
    <div class="ed-title">Get the engine. Own it forever.</div>
    <p class="ed-sub">One Python file. Zero external dependencies. Runs on any device with Python installed. Your governance engine, your audit chain, your compliance &mdash; sovereign and permanent.</p>
    <div class="ed-code">python engine.py &nbsp;&mdash;&nbsp; All systems operational</div>
    <div class="ed-btns">
      <a href="/download/engine" class="btn-gold">Download engine.py &rarr;</a>
      <a href="#signup" class="btn-ghost">Get API Key First</a>
    </div>
  </div>
</div></section>

<section class="compliance-sec" id="compliance"><div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">Legal Compliance</div>
  <h2>Built for the law. <em>As it stands today.</em></h2>
  <p class="sec-sub">Both products meet every current and upcoming UK and EU legal obligation. Deploy and tick every compliance box immediately.</p>
  <div class="comp-grid">
    <div class="comp-card"><div class="comp-act">EU AI Act 2024/1689</div><h3>High-Risk AI Compliance</h3><p>Enforced August 2026. AILeash satisfies Art.9 risk assessment, Art.12 audit chain, Art.13 explainability from day one.</p><div class="checks"><div class="chk">Article 9 &mdash; Continuous risk assessment</div><div class="chk">Article 12 &mdash; Tamper-evident audit chain</div><div class="chk">Article 13 &mdash; Explainable decisions</div><div class="chk">GDPR Art.22 &mdash; Human oversight pathway</div></div></div>
    <div class="comp-card"><div class="comp-act">Online Safety Act 2023 &mdash; UK</div><h3>Duty of Care to Children</h3><p>Platforms must assess risk and demonstrate compliance to Ofcom. Guardian provides the complete technical infrastructure.</p><div class="checks"><div class="chk">Risk assessment infrastructure</div><div class="chk">Real-time content moderation</div><div class="chk">Age-appropriate design</div><div class="chk">Ofcom-ready audit trails</div></div></div>
    <div class="comp-card"><div class="comp-act">ICO Children's Code &mdash; UK</div><h3>Age Appropriate Design</h3><p>Guardian ensures children are never subject to solely automated high-risk decisions without human oversight.</p><div class="checks"><div class="chk">Best interests of the child by default</div><div class="chk">Data minimisation for child users</div><div class="chk">Profiling restrictions enforced</div><div class="chk">Parental controls pathway</div></div></div>
    <div class="comp-card"><div class="comp-act">Digital Services Act &mdash; EU 2022/2065</div><h3>Platform Accountability</h3><p>Continuous automated risk assessment with full audit documentation for regulatory submission under the DSA.</p><div class="checks"><div class="chk">Systemic risk assessment</div><div class="chk">Algorithmic transparency reports</div><div class="chk">Minor protection evidence packages</div><div class="chk">Regulator-ready submissions</div></div></div>
  </div>
</div></section>

<section class="fair-sec"><div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">Fair Usage Policy</div>
  <h2>Always fast. <em>Always fair.</em></h2>
  <p class="sec-sub">Per-key rate limits keep the platform fast for everyone. When global load spikes, a second governance engine spins up automatically.</p>
  <div class="fair-grid">
    <div class="fair-card"><h3>Per-Key Rate Limits</h3><p>Every API key is governed by fair usage limits. Bursting above these triggers graceful throttling, not crashes. Your audit chain is always safe.</p><div class="fair-limit">60 requests / minute<br>1,000 requests / hour</div></div>
    <div class="fair-card"><h3>Auto-Scale on Load</h3><p>When global request rate exceeds threshold, Railway spins up a second governance engine instance automatically. Capacity doubles in seconds.</p><div class="fair-limit">Threshold: 200 req / sec<br>Scale: automatic via Railway</div></div>
    <div class="fair-card"><h3>Audit Chain Integrity</h3><p>Load events are logged. If we ever throttle your key, the event is recorded with a timestamp. Full transparency, always.</p><div class="fair-limit">Load events logged to chain<br>Verifiable via /api/verify-chain</div></div>
  </div>
</div></section>

<section class="pricing-sec" id="pricing"><div class="pricing-inner">
  <div class="slbl" style="color:rgba(255,255,255,0.25)">Pricing</div>
  <h2 style="color:var(--white)">Simple. <em>Honest. 50p.</em></h2>
  <p style="font-size:15px;color:rgba(255,255,255,0.35);line-height:1.7">50p per device per month. No tiers. No minimums. 10 devices is five pounds. 1,000 devices is five hundred.</p>
  <div class="price-cards">
    <div class="price-card al">
      <div class="price-product">AILeash &mdash; AI Governance</div>
      <div class="price-big"><sup>&pound;</sup>0.50</div>
      <div class="price-per">per device &middot; per month</div>
      <div class="price-example">10 devices = <strong>&pound;5/mo</strong><br>100 devices = <strong>&pound;50/mo</strong><br>1,000 devices = <strong>&pound;500/mo</strong></div>
      <div class="price-feats"><div class="pf">9-signal risk engine</div><div class="pf">SHA-256 and Merkle audit chain</div><div class="pf">ALLOW / CHALLENGE / BLOCK</div><div class="pf">EU AI Act Art.9 / 12 / 13</div><div class="pf">Sovereign local engine included</div><div class="pf">100 free decisions to start</div></div>
      <a href="#signup" class="btn-gold" style="display:block;text-align:center;text-decoration:none" onclick="switchTab('leash')">Get AILeash &rarr;</a>
      <p class="price-note">Free trial &middot; No card to start &middot; Stripe billing</p>
    </div>
    <div class="price-card gu">
      <div class="price-product">Guardian &mdash; Child Safety</div>
      <div class="price-big"><sup>&pound;</sup>0.50</div>
      <div class="price-per">per device &middot; per month</div>
      <div class="price-example">10 devices = <strong>&pound;5/mo</strong><br>100 devices = <strong>&pound;50/mo</strong><br>1,000 devices = <strong>&pound;500/mo</strong></div>
      <div class="price-feats"><div class="pf">Full Guardian engine</div><div class="pf">SHA-256 and Merkle audit chain</div><div class="pf">Real-time grooming detection</div><div class="pf">CSAM database integration</div><div class="pf">Ofcom and Online Safety Act</div><div class="pf">100 free decisions to start</div></div>
      <a href="#signup" class="btn-red" style="display:block;text-align:center;text-decoration:none" onclick="switchTab('guardian')">Get Guardian &rarr;</a>
      <p class="price-note">Free trial &middot; No card to start &middot; Stripe billing</p>
    </div>
  </div>
</div></section>

<section class="signup-sec" id="signup"><div class="signup-inner">
  <div class="slbl" style="color:var(--navy)">Get Started</div>
  <h2>Covered in <em>60 seconds.</em></h2>
  <p style="font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:24px">Name. Email. Phone. Organisation. Devices. That is it. Key created instantly. Straight to Stripe. 100 free decisions included.</p>
  <div class="product-tabs">
    <button class="stab al-on" id="tab-leash" onclick="switchTab('leash')">AILeash &mdash; Governance</button>
    <button class="stab" id="tab-guardian" onclick="switchTab('guardian')">Guardian &mdash; Child Safety</button>
  </div>
  <div class="fg-row">
    <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
    <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
  </div>
  <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@organisation.com"></div>
  <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
  <div class="fg"><label>Organisation Name</label><input type="text" id="org" placeholder="e.g. St Mary's Academy / Meta UK / Ofcom"></div>
  <div class="fg"><label>Organisation Type</label>
    <select id="ot"><option value="">Select type</option>
      <option value="platform">Social Media Platform</option><option value="school">School / Academy</option>
      <option value="isp">ISP / Telecoms</option><option value="government">Government / Regulator</option>
      <option value="enterprise">Enterprise</option><option value="charity">Charity / NGO</option>
      <option value="parent">Parent / Individual</option><option value="other">Other</option>
    </select>
  </div>
  <div class="fg"><label>Number of Devices</label><input type="number" id="dv" placeholder="e.g. 10" min="1" oninput="updatePrice()"></div>
  <div class="price-preview">
    <div><div class="pp-label">Monthly Total</div><div class="pp-sub" id="pp-sub">Enter device count above</div></div>
    <div class="pp-amount" id="pp-amt">&pound;0.00</div>
  </div>
  <button class="btn-full btn-gold" id="go-btn" onclick="doSignup()">Get Free API Key &rarr;</button>
  <div class="msg-err" id="msg-err"></div>
  <div class="msg-ok" id="msg-ok"></div>
  <div class="key-box" id="key-box">
    <div class="key-lbl">Your API Key &mdash; Save This Now</div>
    <div class="key-val" id="key-val"></div>
    <button class="key-copy" onclick="copyKey()">Copy Key</button>
    <div class="usage-box">
      <div><em>POST</em> https://sebbi.pro/api/govern</div>
      <div>Authorization: Bearer <em id="key-prev">YOUR_KEY</em></div>
      <div>Content-Type: application/json</div>
      <div style="margin-top:6px;color:rgba(255,255,255,0.12)">50p per device per month &middot; Billed via Stripe</div>
    </div>
  </div>
</div></section>

<script>""" + LANDING_JS + """</script>
"""

LANDING = page_shell(
    "AILeash Platform &mdash; AI Governance &amp; Child Safety",
    "AILeash: Enterprise AI governance. AILeash Guardian: Child safety. 50p per device per month.",
    LANDING_CSS,
    LANDING_BODY
)

# ============================================================================
# SCAN PAGE
# ============================================================================
SCAN_CSS = """
.scan-hero{background:var(--navy);padding:100px 48px 80px;text-align:center;margin-top:68px}
.scan-hero h1{font-family:var(--display);font-size:clamp(36px,4vw,60px);color:var(--white);font-weight:900;margin-bottom:16px;line-height:1.1}
.scan-hero h1 em{color:var(--gold);font-style:normal}
.scan-hero p{font-size:17px;color:rgba(255,255,255,0.5);max-width:560px;margin:0 auto 32px;line-height:1.75}
.scan-meta{display:flex;gap:24px;justify-content:center;flex-wrap:wrap}
.sm{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase;display:flex;align-items:center;gap:6px}
.sm::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--gold);flex-shrink:0}
.scan-wrap{max-width:720px;margin:0 auto;padding:60px 48px}
.progress-bar{height:4px;background:var(--border);border-radius:2px;margin-bottom:40px;overflow:hidden}
.progress-fill{height:100%;background:linear-gradient(90deg,var(--gold),var(--red));border-radius:2px;transition:width .4s ease}
.question-card{display:none}.question-card.active{display:block}
.q-num{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.q-text{font-family:var(--display);font-size:clamp(20px,2.5vw,28px);font-weight:800;color:var(--navy);margin-bottom:8px;line-height:1.2}
.q-sub{font-size:13px;color:var(--muted);margin-bottom:28px;line-height:1.6}
.q-options{display:flex;flex-direction:column;gap:10px}
.q-opt{padding:16px 20px;border:2px solid var(--border);border-radius:6px;cursor:pointer;font-size:14px;color:var(--text);transition:all .2s;background:var(--white);text-align:left;font-family:var(--sans)}
.q-opt:hover{border-color:var(--gold);background:rgba(201,168,76,0.04)}
.q-opt.selected{border-color:var(--navy);background:var(--navy);color:var(--white)}
.q-opt.risk{border-color:var(--red)}.q-opt.risk.selected{background:var(--red);color:var(--white)}
.scan-nav{display:flex;justify-content:space-between;align-items:center;margin-top:28px}
.scan-nav button{padding:12px 24px;border-radius:4px;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;transition:all .2s;border:none}
.btn-back{background:var(--off);color:var(--muted)}.btn-next{background:var(--gold);color:var(--navy)}
.result-card{display:none;text-align:center}.result-card.show{display:block}
.result-score{font-family:var(--display);font-size:96px;font-weight:900;line-height:1;margin-bottom:8px}
.score-high{color:var(--red)}.score-mid{color:#b45309}.score-low{color:var(--green)}
.result-label{font-family:var(--mono);font-size:13px;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}
.result-verdict{font-size:17px;color:var(--text);max-width:520px;margin:0 auto 32px;line-height:1.75}
.result-issues{text-align:left;margin-bottom:32px}
.ri{display:flex;gap:12px;padding:14px 16px;border-radius:4px;margin-bottom:8px;font-size:13px;line-height:1.5}
.ri-red{background:#fff0f0;border:1px solid #ffcccc;color:#7f1d1d}
.ri-green{background:#f0fff8;border:1px solid #bbf7d0;color:#064e3b}
.ri-icon{flex-shrink:0;font-weight:700;font-family:var(--mono);font-size:11px;padding-top:1px}
.result-cta{background:var(--navy);border-radius:8px;padding:32px;text-align:center;margin-top:28px}
.result-cta h3{font-family:var(--display);font-size:24px;color:var(--white);font-weight:900;margin-bottom:8px}
.result-cta p{font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:20px;line-height:1.65}
.result-cta-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
"""

SCAN_BODY = """
<div class="scan-hero">
  <h1>EU AI Act<br><em>Compliance Scanner</em></h1>
  <p>8 questions. 60 seconds. Instant score. Find out if your AI systems are ready for the August 2026 enforcement deadline.</p>
  <div class="scan-meta"><span class="sm">Free &mdash; No signup</span><span class="sm">8 questions</span><span class="sm">Instant score</span><span class="sm">August 2026 deadline</span></div>
</div>
<div class="scan-wrap">
  <div class="progress-bar"><div class="progress-fill" id="prog" style="width:0%"></div></div>
  <div id="q-container">
    <div class="question-card active" id="q0"><div class="q-num">Question 1 of 8</div><div class="q-text">Does your organisation use AI systems that make decisions affecting people?</div><div class="q-sub">This includes automated hiring, credit scoring, content moderation, access control, fraud detection, or any system where AI output influences a human outcome.</div><div class="q-options"><button class="q-opt" onclick="answer(0,0,false)">Yes &mdash; AI decisions directly affect people</button><button class="q-opt" onclick="answer(0,1,false)">Yes &mdash; AI assists humans who make final decisions</button><button class="q-opt" onclick="answer(0,2,false)">No &mdash; we use AI for internal tools only</button><button class="q-opt" onclick="answer(0,3,false)">We are evaluating AI but not deployed yet</button></div></div>
    <div class="question-card" id="q1"><div class="q-num">Question 2 of 8</div><div class="q-text">Do you have a tamper-evident audit trail for every AI decision?</div><div class="q-sub">EU AI Act Article 12 requires high-risk AI systems to automatically log events in a way that cannot be altered. Logs must be retained and available to regulators.</div><div class="q-options"><button class="q-opt" onclick="answer(1,0,false)">Yes &mdash; cryptographic audit chain in place</button><button class="q-opt risk" onclick="answer(1,1,true)">We have standard logs but no tamper protection</button><button class="q-opt risk" onclick="answer(1,2,true)">No audit trail exists</button><button class="q-opt risk" onclick="answer(1,3,true)">We are not sure what we have</button></div></div>
    <div class="question-card" id="q2"><div class="q-num">Question 3 of 8</div><div class="q-text">Can you explain every AI decision in plain language to a regulator?</div><div class="q-sub">Article 13 requires AI systems to be transparent. Every decision must include a human-readable explanation of which factors drove the outcome.</div><div class="q-options"><button class="q-opt" onclick="answer(2,0,false)">Yes &mdash; every decision includes a full explanation</button><button class="q-opt risk" onclick="answer(2,1,true)">We can explain some decisions but not all</button><button class="q-opt risk" onclick="answer(2,2,true)">No &mdash; our model is a black box</button><button class="q-opt risk" onclick="answer(2,3,true)">We have not considered this requirement</button></div></div>
    <div class="question-card" id="q3"><div class="q-num">Question 4 of 8</div><div class="q-text">Is there a human oversight pathway for high-risk AI decisions?</div><div class="q-sub">Article 14 requires that humans can override, correct, or halt AI systems. High-risk decisions must not be fully automated without human intervention.</div><div class="q-options"><button class="q-opt" onclick="answer(3,0,false)">Yes &mdash; CHALLENGE decisions route to human review automatically</button><button class="q-opt" onclick="answer(3,1,false)">Humans can intervene but the process is manual</button><button class="q-opt risk" onclick="answer(3,2,true)">No human oversight pathway exists</button><button class="q-opt risk" onclick="answer(3,3,true)">All decisions are fully automated with no override</button></div></div>
    <div class="question-card" id="q4"><div class="q-num">Question 5 of 8</div><div class="q-text">Have you conducted a formal risk assessment for your AI systems?</div><div class="q-sub">Article 9 requires a continuous risk management system covering identification, analysis, and mitigation of risks. This must be documented and updated throughout the AI lifecycle.</div><div class="q-options"><button class="q-opt" onclick="answer(4,0,false)">Yes &mdash; documented and updated regularly</button><button class="q-opt risk" onclick="answer(4,1,true)">We did one at launch but have not updated it</button><button class="q-opt risk" onclick="answer(4,2,true)">No formal risk assessment exists</button><button class="q-opt risk" onclick="answer(4,3,true)">We were not aware this was required</button></div></div>
    <div class="question-card" id="q5"><div class="q-num">Question 6 of 8</div><div class="q-text">Does your AI system interact with or make decisions affecting children?</div><div class="q-sub">AI systems affecting minors are automatically classified as high-risk and are subject to additional obligations under the UK Online Safety Act 2023 and ICO Children's Code.</div><div class="q-options"><button class="q-opt risk" onclick="answer(5,0,true)">Yes &mdash; children use or are affected by our AI systems</button><button class="q-opt" onclick="answer(5,1,false)">No &mdash; our systems explicitly exclude minors</button><button class="q-opt risk" onclick="answer(5,2,true)">We are not sure &mdash; our platform is open to the public</button><button class="q-opt" onclick="answer(5,3,false)">Not applicable to our use case</button></div></div>
    <div class="question-card" id="q6"><div class="q-num">Question 7 of 8</div><div class="q-text">Are your AI systems registered with the EU AI Act database?</div><div class="q-sub">High-risk AI systems must be registered in the EU database before being placed on the market. This is a hard legal requirement from August 2026.</div><div class="q-options"><button class="q-opt" onclick="answer(6,0,false)">Yes &mdash; registered and compliant</button><button class="q-opt risk" onclick="answer(6,1,true)">No &mdash; not yet registered</button><button class="q-opt risk" onclick="answer(6,2,true)">We did not know registration was required</button><button class="q-opt" onclick="answer(6,3,false)">We have assessed and confirmed we are not high-risk</button></div></div>
    <div class="question-card" id="q7"><div class="q-num">Question 8 of 8</div><div class="q-text">When is your organisation planning to be fully EU AI Act compliant?</div><div class="q-sub">Enforcement begins August 2026. Fines reach 3% of global annual turnover or 15 million euros, whichever is higher.</div><div class="q-options"><button class="q-opt" onclick="answer(7,0,false)">We are already compliant</button><button class="q-opt" onclick="answer(7,1,false)">We have a programme in place and will be ready by August 2026</button><button class="q-opt risk" onclick="answer(7,2,true)">We are working on it but may not be ready in time</button><button class="q-opt risk" onclick="answer(7,3,true)">We have not started compliance work yet</button></div></div>
  </div>
  <div class="result-card" id="result">
    <div class="result-score" id="res-score">0</div>
    <div class="result-label" id="res-label"></div>
    <div class="result-verdict" id="res-verdict"></div>
    <div class="result-issues" id="res-issues"></div>
    <div class="result-cta">
      <h3>AILeash fixes this. Today.</h3>
      <p>SHA-256 audit chain. Explainable decisions. Human oversight. EU AI Act Art.9, 12, 13. Guardian covers children. 50p per device per month. 100 free decisions to start.</p>
      <div class="result-cta-btns">
        <a href="/#signup" class="btn-gold">Get AILeash &rarr;</a>
        <a href="/#signup" class="btn-red">Get Guardian &rarr;</a>
      </div>
      <p style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);margin-top:16px">Free trial &middot; 100 decisions &middot; No card required</p>
    </div>
    <div style="margin-top:24px;text-align:center"><button onclick="restartScan()" style="background:none;border:none;color:var(--muted);font-family:var(--mono);font-size:11px;cursor:pointer;text-decoration:underline">Retake the scanner</button></div>
  </div>
  <div class="scan-nav" id="scan-nav">
    <button class="btn-back" id="btn-back" onclick="prevQ()" style="display:none">Back</button>
    <span style="font-family:var(--mono);font-size:11px;color:var(--muted)" id="q-counter">1 / 8</span>
    <button class="btn-next" id="btn-next" onclick="nextQ()" disabled>Next &rarr;</button>
  </div>
</div>
<script>
var cur=0,total=8,answers=[],risks=[];
var riskLabels=['No AI Act exposure identified','Standard audit logging insufficient for Art.12','Black-box AI violates Art.13 explainability','No human oversight violates Art.14','No risk management violates Art.9','Systems affecting children require Guardian + Online Safety Act compliance','High-risk AI must be registered in EU database before August 2026','Insufficient time to achieve compliance before enforcement'];
function answer(q,opt,isRisk){answers[q]=opt;risks[q]=isRisk;document.querySelectorAll('#q'+q+' .q-opt').forEach(function(b){b.classList.remove('selected');});document.querySelectorAll('#q'+q+' .q-opt')[opt].classList.add('selected');document.getElementById('btn-next').disabled=false;}
function updateProgress(){var pct=Math.round((cur/total)*100);document.getElementById('prog').style.width=pct+'%';document.getElementById('q-counter').textContent=(cur+1)+' / '+total;document.getElementById('btn-back').style.display=cur>0?'block':'none';}
function nextQ(){if(answers[cur]===undefined)return;document.getElementById('q'+cur).classList.remove('active');cur++;if(cur>=total){showResult();return;}document.getElementById('q'+cur).classList.add('active');document.getElementById('btn-next').disabled=answers[cur]===undefined;updateProgress();}
function prevQ(){if(cur===0)return;document.getElementById('q'+cur).classList.remove('active');cur--;document.getElementById('q'+cur).classList.add('active');document.getElementById('btn-next').disabled=false;updateProgress();}
function showResult(){document.getElementById('scan-nav').style.display='none';document.getElementById('prog').style.width='100%';var rc=risks.filter(Boolean).length;var score=Math.round((rc/total)*100);var el=document.getElementById('res-score');el.textContent=score+'%';el.className='result-score '+(score>=60?'score-high':score>=30?'score-mid':'score-low');var label,verdict;if(score>=60){label='HIGH RISK &mdash; Immediate action required';verdict='Your AI systems have significant EU AI Act compliance gaps. At current enforcement fines, non-compliance could cost up to 3% of global annual turnover or \u20ac15M.';}else if(score>=30){label='MEDIUM RISK &mdash; Action needed before August 2026';verdict='You have made progress on compliance but critical gaps remain. With enforcement approaching, now is the time to close them.';}else{label='LOW RISK &mdash; Minor gaps to address';verdict='Your organisation appears largely prepared for the EU AI Act. A few areas need attention before August 2026.';}document.getElementById('res-label').innerHTML=label;document.getElementById('res-verdict').textContent=verdict;var el2=document.getElementById('res-issues');el2.innerHTML='';for(var i=0;i<total;i++){var cls=risks[i]?'ri-red':'ri-green';var icon=risks[i]?'FAIL':'PASS';el2.innerHTML+='<div class="ri '+cls+'"><span class="ri-icon">'+icon+'</span><span>'+riskLabels[i]+'</span></div>';}document.getElementById('result').classList.add('show');}
function restartScan(){cur=0;answers=[];risks=[];document.getElementById('result').classList.remove('show');document.getElementById('scan-nav').style.display='flex';document.querySelectorAll('.question-card').forEach(function(c){c.classList.remove('active');});document.getElementById('q0').classList.add('active');document.getElementById('btn-next').disabled=true;updateProgress();}
updateProgress();
</script>
"""

SCAN = page_shell(
    "EU AI Act Compliance Scanner &mdash; AILeash",
    "Free EU AI Act compliance scanner. 8 questions. Instant score. August 2026 deadline.",
    SCAN_CSS,
    SCAN_BODY
)

# ============================================================================
# CONTACT PAGE
# ============================================================================
CONTACT_CSS = """
.contact-hero{background:var(--navy);padding:100px 48px 80px;text-align:center;margin-top:68px}
.contact-hero h1{font-family:var(--display);font-size:clamp(36px,4vw,60px);color:var(--white);font-weight:900;margin-bottom:16px}
.contact-hero h1 em{color:var(--gold);font-style:normal}
.contact-hero p{font-size:17px;color:rgba(255,255,255,0.5);max-width:540px;margin:0 auto;line-height:1.75}
.contact-wrap{max-width:1100px;margin:0 auto;padding:80px 48px;display:grid;grid-template-columns:1fr 1.4fr;gap:60px;align-items:start}
.owner-card{background:var(--navy);border-radius:8px;padding:36px;position:sticky;top:88px}
.owner-badge{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}
.owner-name{font-family:var(--display);font-size:28px;color:var(--white);font-weight:900;margin-bottom:4px}
.owner-title{font-size:14px;color:rgba(255,255,255,0.4);margin-bottom:28px}
.owner-contacts{display:flex;flex-direction:column;gap:14px}
.oc{display:flex;align-items:center;gap:12px;padding:14px 16px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:6px;text-decoration:none;transition:border-color .2s}
.oc:hover{border-color:rgba(201,168,76,0.4)}
.oc-icon{font-size:18px;flex-shrink:0}
.oc-label{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:2px}
.oc-value{font-size:13px;color:var(--white)}
.owner-note{margin-top:20px;font-size:12px;color:rgba(255,255,255,0.2);line-height:1.7;font-style:italic}
.contact-form-wrap h2{font-family:var(--display);font-size:clamp(28px,3vw,40px);font-weight:900;margin-bottom:8px;color:var(--navy)}
.contact-form-wrap h2 em{color:var(--gold);font-style:normal}
.contact-form-wrap p{font-size:14px;color:var(--muted);margin-bottom:28px;line-height:1.7}
.fg textarea{height:130px;resize:vertical}
.btn-submit{background:var(--gold);color:var(--navy);padding:14px 32px;border:none;font-family:var(--sans);font-weight:700;font-size:15px;cursor:pointer;border-radius:4px;transition:all .2s;width:100%}
.btn-submit:hover{background:var(--gold2)}
"""

CONTACT_BODY = f"""
<div class="contact-hero">
  <h1>Talk to <em>Justin.</em></h1>
  <p>Whether you are a regulator, a platform, a school, or a parent &mdash; we want to hear from you. Responses within 24 hours.</p>
</div>
<div class="contact-wrap">
  <div class="owner-card">
    <div class="owner-badge">Direct Contact</div>
    <div class="owner-name">{OWNER_NAME}</div>
    <div class="owner-title">Owner, Monop Content</div>
    <div class="owner-contacts">
      <a href="mailto:{OWNER_EMAIL}" class="oc"><span class="oc-icon">&#9993;</span><div><div class="oc-label">Email</div><div class="oc-value">{OWNER_EMAIL}</div></div></a>
      <a href="tel:07908269428" class="oc"><span class="oc-icon">&#128222;</span><div><div class="oc-label">Phone</div><div class="oc-value">{OWNER_PHONE}</div></div></a>
      <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank" class="oc"><span class="oc-icon">&#128187;</span><div><div class="oc-label">GitHub</div><div class="oc-value">justrightdecorators-ops/aileash</div></div></a>
    </div>
    <p class="owner-note">Built in Blyth, UK. Available for meetings in London or remotely. Actively speaking with regulators, platforms, schools and ISPs.</p>
  </div>
  <div class="contact-form-wrap">
    <h2>Send a <em>message.</em></h2>
    <p>Use the form below or email directly. Tell us what you need &mdash; a demo, a pilot, a compliance briefing, or just a conversation.</p>
    <div class="fg-row"><div class="fg"><label>First Name</label><input type="text" id="cfn" placeholder="Justin"></div><div class="fg"><label>Last Name</label><input type="text" id="cln" placeholder="Smith"></div></div>
    <div class="fg"><label>Email Address</label><input type="email" id="cem" placeholder="you@organisation.com"></div>
    <div class="fg"><label>Phone (optional)</label><input type="tel" id="cph" placeholder="+44 7700 000000"></div>
    <div class="fg"><label>Organisation</label><input type="text" id="corg" placeholder="e.g. Ofcom / Meta UK / St Mary's Academy"></div>
    <div class="fg"><label>Message</label><textarea id="cmsg" placeholder="Tell us what you need..."></textarea></div>
    <button class="btn-submit" id="contact-btn" onclick="sendContact()">Send Message &rarr;</button>
    <div class="msg-err" id="contact-err"></div>
    <div class="msg-ok" id="contact-ok"></div>
  </div>
</div>
<script>
async function sendContact(){{
  var fn=document.getElementById('cfn').value.trim();var ln=document.getElementById('cln').value.trim();
  var em=document.getElementById('cem').value.trim();var ph=document.getElementById('cph').value.trim();
  var org=document.getElementById('corg').value.trim();var msg=document.getElementById('cmsg').value.trim();
  var err=document.getElementById('contact-err');var ok=document.getElementById('contact-ok');
  var btn=document.getElementById('contact-btn');
  err.classList.remove('show');ok.classList.remove('show');
  if(!em||!em.includes('@')){{err.textContent='Please enter a valid email address.';err.classList.add('show');return;}}
  if(!msg){{err.textContent='Please enter a message.';err.classList.add('show');return;}}
  btn.textContent='Sending\u2026';btn.disabled=true;
  try{{
    var r=await fetch('/contact',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{name:fn+' '+ln,email:em,phone:ph,org:org,message:msg}})}});
    var d=await r.json();
    if(d.ok){{ok.textContent='Message sent. Justin will respond within 24 hours.';ok.classList.add('show');btn.textContent='Sent \u2713';}}
    else{{err.textContent='Error. Email justin@monopcontent.com directly.';err.classList.add('show');btn.textContent='Send Message \u2192';btn.disabled=false;}}
  }}catch(e){{err.textContent='Cannot reach server. Email justin@monopcontent.com directly.';err.classList.add('show');btn.textContent='Send Message \u2192';btn.disabled=false;}}
}}
</script>
"""

CONTACT = page_shell(
    f"Contact &mdash; {OWNER_NAME} &mdash; AILeash Platform",
    "Contact Justin Antony Dobson, Owner of Monop Content and AILeash Platform.",
    CONTACT_CSS,
    CONTACT_BODY
)

# ============================================================================
# HTTP SERVER
# ============================================================================
class ThreadedServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        track_request()

        if path == "/":
            send_html(self, LANDING)
        elif path == "/scan":
            send_html(self, SCAN)
        elif path == "/contact":
            send_html(self, CONTACT)
        elif path == "/api/health":
            send_json(self, {"status":"ok","version":VERSION,"rps":get_rps()})
        elif path == "/api/verify-chain":
            send_json(self, verify_chain())
        elif path == "/api/stats":
            with _db_lock:
                keys    = _conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                audits  = _conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                contacts= _conn.execute("SELECT COUNT(*) FROM contact_log").fetchone()[0]
            send_json(self, {"api_keys":keys,"audit_blocks":audits,"contacts":contacts,"rps":get_rps(),"version":VERSION})
        elif path == "/api/validate-engine":
            send_json(self, {"error": "method_not_allowed"}, 405)

        elif path == "/download/engine":
            api_key = get_bearer(self)
            if not api_key:
                # No key — serve a page telling them to sign up
                send_html(self, """<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>AILeash Engine Download</title>
<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{text-align:center;max-width:480px;padding:40px}
h1{font-size:28px;margin-bottom:16px;color:#c9a84c}p{color:rgba(255,255,255,0.5);margin-bottom:24px;line-height:1.7}
a{background:#c9a84c;color:#0a0f1e;padding:14px 28px;text-decoration:none;border-radius:4px;font-weight:700;display:inline-block}</style></head>
<body><div class="box"><h1>Engine Download</h1>
<p>A valid AILeash API key is required to download the engine.<br>Get your key at sebbi.pro &mdash; 100 free decisions, no card required.</p>
<a href="https://sebbi.pro/#signup">Get API Key &rarr;</a></div></body></html>""", 401)
                return
            ki = get_key(api_key)
            if not ki or not ki[2]:
                send_html(self, """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Invalid Key</title>
<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{text-align:center;padding:40px}h1{color:#cc0000}p{color:rgba(255,255,255,0.5)}</style></head>
<body><div class="box"><h1>Invalid API Key</h1><p>Contact justin@monopcontent.com</p></div></body></html>""", 401)
                return
            try:
                with open("engine.py", "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/x-python")
                self.send_header("Content-Disposition", 'attachment; filename="engine.py"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                send_json(self, {"error": "engine_not_found"}, 404)
        elif path == "/robots.txt":
            send_html(self,"User-agent: *\nAllow: /\n")
        elif path == "/openapi.json":
            send_json(self,{"openapi":"3.0.0","info":{"title":"AILeash","version":VERSION},"servers":[{"url":"https://sebbi.pro"}]})
        else:
            send_json(self,{"error":"not_found"},404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        data = read_body(self)
        track_request()

        if is_overloaded() and path not in ("/api/govern","/govern"):
            send_json(self,{"error":"server_busy","rps":get_rps()},503)
            return

        if path in ("/api/govern","/govern"):
            api_key = get_bearer(self)
            try:
                result,status = govern(data, api_key or None)
                send_json(self,result,status)
            except ValueError as e: send_json(self,{"error":str(e)},400)
            except Exception as e:  send_json(self,{"error":"internal","detail":str(e)},500)

        elif path in ("/signup","/api/keys"):
            email    = str(data.get("email","")).strip().lower()
            phone    = str(data.get("phone","")).strip()
            name     = str(data.get("name","")).strip()
            org      = str(data.get("org","")).strip()
            org_type = str(data.get("org_type","")).strip()
            product  = str(data.get("product","aileash")).strip().lower()
            devices  = max(1,int(data.get("devices",1)))
            if product not in ("aileash","guardian"): product = "aileash"
            key,err = create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs = {"invalid_email":"Please enter a valid email address.",
                        "email_exists":"A key already exists for this email. Contact justin@monopcontent.com."}
                send_json(self,{"error":msgs.get(err,err)},400); return
            monthly = round(devices*0.50,2)
            threading.Thread(target=welcome_email,args=(name,email,product,key,devices,monthly),daemon=True).start()
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,
                "monthly":monthly,"quota":FREE_QUOTA,"endpoint":f"{HOST}/api/govern",
                "message":f"100 free decisions. After trial: £{monthly}/month via Stripe."})

        elif path == "/contact":
            name  = str(data.get("name","")).strip()
            email = str(data.get("email","")).strip().lower()
            phone = str(data.get("phone","")).strip()
            org   = str(data.get("org","")).strip()
            msg   = str(data.get("message","")).strip()
            if not email or "@" not in email: send_json(self,{"error":"invalid_email"},400); return
            if not msg: send_json(self,{"error":"no_message"},400); return
            with _db_lock:
                _conn.execute("INSERT INTO contact_log(ts,name,email,phone,org,message) VALUES(?,?,?,?,?,?)",
                    (time.time(),name,email,phone,org,msg))
                _conn.commit()
            threading.Thread(target=contact_email,args=(name,email,phone,org,msg),daemon=True).start()
            send_json(self,{"ok":True})

        elif path == "/api/validate-engine":
            api_key = get_bearer(self)
            if not api_key:
                send_json(self, {"valid": False, "error": "no_key"}, 401); return
            ki = get_key(api_key)
            if not ki:
                send_json(self, {"valid": False, "error": "invalid_api_key"}, 401); return
            email, used, active, is_paid, quota, plan, product = ki
            if not active:
                send_json(self, {"valid": False, "error": "account_inactive"}, 403); return
            if not is_paid and used >= quota:
                send_json(self, {"valid": False, "error": "quota_exceeded",
                    "message": "Free trial ended. Renew at https://sebbi.pro/#pricing"}, 402); return
            with _db_lock:
                devices = _conn.execute("SELECT devices FROM api_keys WHERE key=?", (api_key,)).fetchone()
            send_json(self, {
                "valid":   True,
                "plan":    plan,
                "product": product,
                "devices": devices[0] if devices else 1,
                "email":   email,
            })

        elif path == "/stripe-webhook":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b""
            try:
                event = json.loads(raw)
                etype = event.get("type", "")
                obj   = event.get("data", {}).get("object", {})
                if etype in ("checkout.session.completed", "invoice.paid"):
                    email = obj.get("customer_email") or obj.get("customer_details", {}).get("email", "")
                    if email:
                        email = email.strip().lower()
                        with _db_lock:
                            _conn.execute("UPDATE api_keys SET is_paid=1, plan_type='paid' WHERE email=?", (email,))
                            _conn.commit()
                        print(f"PAID: {email}", flush=True)
                elif etype in ("customer
