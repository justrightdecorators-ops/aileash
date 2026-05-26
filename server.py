import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.0.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
STRIPE_PRICE_ID = ""
_db_lock        = threading.Lock()

RISK_PROFILES = {
    "default":{"base":0.0},
    "wire_transfer":{"base":0.18},
    "financial_transfer":{"base":0.18},
    "payment":{"base":0.12},
    "content_action":{"base":0.08},
    "tool_call":{"base":0.12},
    "data_export":{"base":0.15},
    "account_change":{"base":0.14},
}

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE, merkle_root TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS velocity_history (user_id TEXT, window_type TEXT, timestamps TEXT, PRIMARY KEY(user_id, window_type))")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()

def stripe_call(method, endpoint, data=None):
    url = "https://api.stripe.com/v1" + endpoint
    headers = {"Authorization": "Bearer " + STRIPE_SECRET, "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def setup_stripe():
    global STRIPE_PRICE_ID
    if not STRIPE_SECRET:
        print("  WARNING: No STRIPE_SECRET env var set.")
        return
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"  Stripe ready: {STRIPE_PRICE_ID}")
        return
    print("  Setting up Stripe...")
    product = stripe_call("POST", "/products", {"name": "AILeash Governance API", "description": "AI governance API — charged per action. EU AI Act compliant."})
    if "error" in product:
        print(f"  Stripe error: {product['error']}")
        return
    price = stripe_call("POST", "/prices", {"product": product["id"], "currency": "gbp", "billing_scheme": "per_unit", "unit_amount": 1, "recurring[interval]": "month", "recurring[usage_type]": "metered", "nickname": "Per Action"})
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute("INSERT INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()
    print(f"  Stripe done: {STRIPE_PRICE_ID}")

def create_api_key(email, stripe_customer):
    key = "al_live_" + secrets.token_hex(24)
    with _db_lock:
        _conn.execute("INSERT INTO api_keys(key,email,stripe_customer,created) VALUES(?,?,?,?)", (key, email, stripe_customer, time.time()))
        _conn.commit()
    return key

def validate_key(key):
    with _db_lock:
        row = _conn.execute("SELECT email,actions_used,active FROM api_keys WHERE key=?", (key,)).fetchone()
    if not row or not row[2]: return None
    return {"email": row[0], "actions_used": row[1]}

def increment_usage(key):
    with _db_lock:
        _conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?", (key,))
        _conn.commit()

def report_usage(key):
    with _db_lock:
        row = _conn.execute("SELECT stripe_customer FROM api_keys WHERE key=?", (key,)).fetchone()
    if not row: return
    subs = stripe_call("GET", f"/subscriptions?customer={row[0]}&status=active")
    if not subs.get("data"): return
    item_id = subs["data"][0]["items"]["data"][0]["id"]
    stripe_call("POST", f"/subscription_items/{item_id}/usage_records", {"quantity": 1, "timestamp": int(time.time()), "action": "increment"})

WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now(): return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def load_velocity(uid):
    with _db_lock:
        for wtype, q in [("60s",WINDOW_60S[uid]),("5m",WINDOW_5M[uid]),("1h",WINDOW_1H[uid])]:
            row = _conn.execute("SELECT timestamps FROM velocity_history WHERE user_id=? AND window_type=?", (uid,wtype)).fetchone()
            if row:
                q.clear()
                q.extend(json.loads(row[0]))

def save_velocity(uid):
    with _db_lock:
        for wtype, q in [("60s",WINDOW_60S[uid]),("5m",WINDOW_5M[uid]),("1h",WINDOW_1H[uid])]:
            _conn.execute("INSERT INTO velocity_history(user_id,window_type,timestamps) VALUES(?,?,?) ON CONFLICT(user_id,window_type) DO UPDATE SET timestamps=excluded.timestamps", (uid,wtype,json.dumps(list(q))))
        _conn.commit()

def prune(q,s):
    c=now()-s
    while q and q[0]<c: q.popleft()

def update_windows(uid):
    load_velocity(uid)
    t=now()
    for q in [WINDOW_60S[uid],WINDOW_5M[uid],WINDOW_1H[uid]]: q.append(t)
    prune(WINDOW_60S[uid],60); prune(WINDOW_5M[uid],300); prune(WINDOW_1H[uid],3600)
    save_velocity(uid)

def velocity(uid):
    return {"60s":len(WINDOW_60S[uid]),"5m":len(WINDOW_5M[uid]),"1h":len(WINDOW_1H[uid])}

def merkle_hash(data):
    return hashlib.sha256(data.encode()).hexdigest()

def build_merkle_root(leaves):
    if not leaves: return "GENESIS_ROOT"
    if len(leaves)==1: return leaves[0]
    tree=leaves[:]
    while len(tree)>1:
        new_level=[]
        for i in range(0,len(tree),2):
            a=tree[i]; b=tree[i+1] if i+1<len(tree) else a
            new_level.append(merkle_hash(a+b))
        tree=new_level
    return tree[0]

def get_merkle_root():
    with _db_lock:
        rows=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id ASC").fetchall()
    if not rows: return "GENESIS_ROOT"
    return build_merkle_root([r[0] for r in rows])

def load_user(uid):
    with _db_lock:
        row=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row: return {"trust":0.5,"last_country":None}
    return {"trust":row[0],"last_country":row[1]}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",(uid,trust,country))
        _conn.commit()

def compute_score(s,action_type="default"):
    score=0
    score+=(1-s["trust"])*0.30
    score+=min(s["v60"]/20,1)*0.15
    score+=min(s["v5m"]/50,1)*0.10
    score+=min(s["v1h"]/200,1)*0.10
    score+=min(math.log1p(s["amount"])/math.log1p(10000),1)*0.15
    score+=s["device_risk"]*0.10
    score+=s["anomaly"]*0.10
    if s["country_shift"]: score+=0.10
    if s["unsafe_country"]: score+=0.10
    profile=RISK_PROFILES.get(action_type,RISK_PROFILES["default"])
    score+=profile.get("base",0.0)
    return clamp(score)

def decide(score):
    if score<0.35: return "ALLOW"
    if score<0.70: return "CHALLENGE"
    return "BLOCK"

def update_trust(trust,decision):
    if decision=="ALLOW": trust+=(1-trust)*0.01
    elif decision=="CHALLENGE": trust-=trust*0.02
    elif decision=="BLOCK": trust-=trust*0.08
    return clamp(trust,0.05,1.0)

def explain(s):
    r=[]
    if s["trust"]<0.4: r.append("low_trust")
    if s["v60"]>10: r.append("velocity_spike")
    if s["amount"]>500: r.append("high_amount")
    if s["device_risk"]>0.5: r.append("risky_device")
    if s["country_shift"]: r.append("country_shift")
    if s["unsafe_country"]: r.append("unsafe_country")
    if s["anomaly"]>0.5: r.append("behaviour_anomaly")
    return r

def chain_tip():
    with _db_lock:
        row=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event,result,ts):
    prev=chain_tip()
    payload={"prev_hash":prev,"ts":ts,"event":event,"result":result}
    h=sha(payload)
    root=get_merkle_root()
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash,merkle_root) VALUES(?,?,?,?,?,?,?)",
            (ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h,root))
        _conn.commit()
    return h,root

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
    return {"valid":True,"blocks":len(rows),"merkle_root":get_merkle_root(),"message":"Chain intact — all hashes verified"}

def govern(event,api_key=None):
    missing=REQUIRED_FIELDS-event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    ts=now()
    state=load_user(event["user_id"])
    update_windows(event["user_id"])
    v=velocity(event["user_id"])
    signals={"trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],"amount":event["amount"],"device_risk":event["device_risk"],"anomaly":event["anomaly"],"country_shift":state["last_country"] is not None and state["last_country"]!=event["country"],"unsafe_country":event["country"] not in SAFE_COUNTRIES}
    action_type=event.get("action","default")
    score=compute_score(signals,action_type)
    decision=decide(score)
    reasons=explain(signals)
    trust=update_trust(state["trust"],decision)
    save_user(event["user_id"],trust,event["country"])
    result={"decision":decision,"score":round(score,4),"trust":round(trust,4),"reasons":reasons,"version":VERSION}
    audit_hash,merkle_root=append_audit(event,result,ts)
    result["audit_hash"]=audit_hash
    result["merkle_root"]=merkle_root
    if api_key:
        increment_usage(api_key)
        threading.Thread(target=report_usage,args=(api_key,),daemon=True).start()
    return result

def send(h,data,status=200):
    body=json.dumps(data,indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json")
    h.send_header("Content-Length",str(len(body)))
    h.send_header("Access-Control-Allow-Origin","*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h,html):
    body=html.encode()
    h.send_response(200)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Content-Length",str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def err(h,msg,status=400): send(h,{"error":msg},status)

def get_key(h):
    auth=h.headers.get("Authorization","")
    return auth[7:] if auth.startswith("Bearer ") else None

LANDING="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash — AI Governance & Compliance Infrastructure</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--red:#cc0000;--red2:#990000;--black:#0a0a0a;--white:#fff;--off:#f8f8f8;--border:#e0e0e0;--muted:#666;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Bebas Neue',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{background:#fff;color:#0a0a0a;font-family:var(--sans);overflow-x:hidden}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:#fff;border-bottom:3px solid var(--red);padding:0 48px;height:64px;display:flex;align-items:center;justify-content:space-between}
.logo{font-family:var(--display);font-size:28px;letter-spacing:2px}.logo span{color:var(--red)}
.nav-links{display:flex;gap:32px;align-items:center}
.nav-links a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--red)}
.nav-cta{background:var(--red)!important;color:#fff!important;padding:10px 22px;border-radius:4px;font-weight:700!important;letter-spacing:1px!important;text-transform:uppercase;font-size:13px!important}
.hero{padding:120px 48px 80px;border-bottom:1px solid var(--border)}
.hero-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:80px;align-items:center}
.eyebrow{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#fff;padding:6px 14px;font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-bottom:24px}
.eyebrow::before{content:'';width:6px;height:6px;background:#fff;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
h1{font-family:var(--display);font-size:clamp(56px,6vw,88px);line-height:.95;letter-spacing:2px;margin-bottom:24px;text-transform:uppercase}
h1 .red{color:var(--red)}
.hero-p{font-size:17px;color:var(--muted);line-height:1.75;margin-bottom:36px;max-width:520px}
.btns{display:flex;gap:14px;flex-wrap:wrap}
.btn-p{background:var(--red);color:#fff;padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:all .2s;border-radius:4px;display:inline-block}
.btn-p:hover{background:var(--red2)}
.btn-o{background:transparent;color:var(--black);padding:14px 28px;border:2px solid var(--black);font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:all .2s;border-radius:4px;display:inline-block}
.btn-o:hover{background:var(--black);color:#fff}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:28px}
.pill{border:1px solid var(--red);color:var(--red);padding:4px 12px;font-family:var(--mono);font-size:11px;border-radius:2px}
.terminal{background:#0a0a0a;border-radius:8px;overflow:hidden;font-family:var(--mono);font-size:13px;box-shadow:8px 8px 0 var(--red)}
.term-bar{background:#1a1a1a;padding:12px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333}
.dot{width:10px;height:10px;border-radius:50%}.dr{background:#ff5f56}.dy{background:#ffbd2e}.dg{background:#27c93f}
.tlbl{margin-left:auto;font-size:10px;color:#666;letter-spacing:2px;text-transform:uppercase}
.term-body{padding:24px;line-height:2.2;color:#ccc}
.tc{color:#555}.tk{color:#79b8ff}.tv{color:#f0c674}.ts{color:#9ecbff}.tb{color:#ff3b5c;font-weight:700}
.stats{background:#0a0a0a;padding:48px}
.stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}
.stat{padding:24px;border-right:1px solid #222;text-align:center}.stat:last-child{border:none}
.stat-n{font-family:var(--display);font-size:44px;color:var(--red);letter-spacing:2px}
.stat-l{font-size:12px;color:#666;margin-top:4px;letter-spacing:1px;text-transform:uppercase}
.sec{padding:80px 48px;border-bottom:1px solid var(--border)}
.sec-inner{max-width:1200px;margin:0 auto}
.sec-lbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;color:var(--red);text-transform:uppercase;margin-bottom:12px}
h2{font-family:var(--display);font-size:clamp(36px,4vw,56px);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}
h2 span{color:var(--red)}
.sec-sub{font-size:17px;color:var(--muted);max-width:640px;line-height:1.7;margin-bottom:48px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--border);border:1px solid var(--border)}
.card{background:#fff;padding:32px;position:relative}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--red)}
.card-ref{font-family:var(--mono);font-size:10px;color:var(--red);letter-spacing:2px;text-transform:uppercase;margin-bottom:12px}
.card h3{font-family:var(--display);font-size:20px;letter-spacing:1px;margin-bottom:10px;text-transform:uppercase}
.card p{font-size:14px;color:var(--muted);line-height:1.65}
.how-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:40px}
.how-card{border:1px solid var(--border);padding:32px;position:relative}
.how-card::after{content:'';position:absolute;bottom:0;left:0;right:0;height:4px;background:var(--red)}
.how-num{font-family:var(--display);font-size:64px;color:#f0f0f0;line-height:1;margin-bottom:16px}
.how-card h3{font-family:var(--display);font-size:22px;letter-spacing:1px;margin-bottom:10px;text-transform:uppercase}
.how-card p{font-size:14px;color:var(--muted);line-height:1.65}
.dec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid var(--border);margin-top:40px}
.dec-card{padding:36px;border-right:1px solid var(--border);position:relative}
.dec-card:last-child{border:none}
.dec-card::after{content:'';position:absolute;bottom:0;left:0;right:0;height:4px}
.dec-a::after{background:#00cc66}.dec-c::after{background:#ff9900}.dec-b::after{background:var(--red)}
.dec-v{font-family:var(--display);font-size:48px;letter-spacing:3px;margin-bottom:8px}
.dec-a .dec-v{color:#00cc66}.dec-c .dec-v{color:#ff9900}.dec-b .dec-v{color:var(--red)}
.dec-r{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:16px}
.dec-d{font-size:14px;color:var(--muted);line-height:1.65}
.legal-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:24px;margin-top:40px}
.legal-card{border:1px solid var(--border);padding:28px;border-left:4px solid var(--red)}
.legal-act{font-family:var(--mono);font-size:10px;color:var(--red);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.legal-card h3{font-family:var(--display);font-size:20px;letter-spacing:1px;margin-bottom:10px;text-transform:uppercase}
.legal-card p{font-size:14px;color:var(--muted);line-height:1.7}
.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:40px}
.price-card{border:1px solid var(--border);padding:36px;position:relative}
.price-card.featured{border:2px solid var(--red);background:#f8f8f8}
.price-badge{position:absolute;top:-14px;left:50%;transform:translateX(-50%);background:var(--red);color:#fff;font-family:var(--mono);font-size:10px;font-weight:700;padding:4px 16px;letter-spacing:2px;text-transform:uppercase;white-space:nowrap}
.price-tier{font-family:var(--mono);font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}
.price-num{font-family:var(--display);font-size:56px;letter-spacing:-1px;margin-bottom:4px}
.price-num sup{font-size:24px;vertical-align:super;color:var(--red)}
.price-unit{font-size:13px;color:var(--muted);margin-bottom:28px;font-family:var(--mono)}
.price-features{list-style:none;margin-bottom:32px}
.price-features li{font-size:14px;color:var(--muted);padding:10px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.price-features li::before{content:'✓';color:var(--red);font-weight:700}
.signup-sec{padding:80px 48px;background:#f8f8f8;border-bottom:1px solid var(--border)}
.signup-inner{max-width:680px;margin:0 auto}
.fg{margin-bottom:16px}
.fg label{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.fg input{width:100%;background:#fff;border:2px solid var(--border);color:#0a0a0a;padding:14px 16px;font-size:15px;font-family:var(--sans);outline:none;transition:border-color .2s;border-radius:4px}
.fg input:focus{border-color:var(--red)}.fg input::placeholder{color:#bbb}
.btn-full{width:100%;margin-top:8px;padding:16px;font-size:15px}
.key-result{display:none;margin-top:24px;background:#0a0a0a;border-radius:8px;padding:24px}
.key-result.show{display:block}
.key-lbl{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--red);margin-bottom:10px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:13px;color:#00ff88;word-break:break-all;background:#0d0d0d;padding:14px;border-radius:4px;border:1px solid #222}
.key-copy{margin-top:12px;background:transparent;border:1px solid #333;color:#666;padding:8px 18px;font-family:var(--mono);font-size:11px;cursor:pointer;transition:all .2s;letter-spacing:1px;text-transform:uppercase;border-radius:4px}
.key-copy:hover{border-color:var(--red);color:var(--red)}
.usage-box{margin-top:16px;font-family:var(--mono);font-size:12px;color:#555;background:#0d0d0d;padding:16px;border-radius:4px;line-height:2.2}
.usage-box em{color:#79b8ff;font-style:normal}
.form-err{display:none;color:var(--red);font-family:var(--mono);font-size:12px;margin-top:12px;padding:12px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}
.form-err.show{display:block}
footer{background:#0a0a0a;padding:60px 48px;color:#666}
.foot-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr 1fr;gap:40px}
.foot-logo{font-family:var(--display);font-size:32px;color:#fff;letter-spacing:2px;margin-bottom:12px}
.foot-logo span{color:var(--red)}
.foot-desc{font-size:13px;line-height:1.65;color:#555}
.foot-col h4{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--red);text-transform:uppercase;margin-bottom:16px}
.foot-col a{display:block;color:#555;text-decoration:none;font-size:13px;margin-bottom:8px;transition:color .2s}
.foot-col a:hover{color:#fff}
.foot-bottom{max-width:1200px;margin:40px auto 0;padding-top:24px;border-top:1px solid #111;display:flex;justify-content:space-between;font-size:12px;color:#333;font-family:var(--mono)}
@media(max-width:900px){
nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
.hero{padding:90px 20px 60px}.hero-inner{grid-template-columns:1fr;gap:40px}
.stats-inner{grid-template-columns:repeat(2,1fr)}.stat{border-right:none;border-bottom:1px solid #222}
.sec{padding:60px 20px}.grid3,.dec-grid,.how-grid,.price-grid,.legal-grid{grid-template-columns:1fr}
.dec-card{border-right:none;border-bottom:1px solid var(--border)}
.signup-sec{padding:60px 20px}footer{padding:48px 20px}
.foot-inner{grid-template-columns:1fr}.foot-bottom{flex-direction:column;gap:12px;text-align:center}}
</style>
</head>
<body>
<nav>
  <div class="logo">AI<span>Leash</span></div>
  <div class="nav-links">
    <a href="#compliance">Compliance</a>
    <a href="#how">How It Works</a>
    <a href="#legal">Legal</a>
    <a href="#pricing">Pricing</a>
    <a href="#signup" class="nav-cta">Get API Key</a>
  </div>
</nav>
<section class="hero">
  <div class="hero-inner">
    <div>
      <div class="eyebrow">EU AI Act — Enforcement August 2026</div>
      <h1>AI Governance<br><span class="red">Infrastructure</span></h1>
      <p class="hero-p">AILeash is a real-time AI action governance engine. Every AI decision scored, audited, and controlled before it executes. Cryptographic audit chain. Built for EU AI Act compliance.</p>
      <div class="btns">
        <a href="#signup" class="btn-p">Get API Key — Free</a>
        <a href="#how" class="btn-o">How It Works</a>
      </div>
      <div class="pills">
        <span class="pill">EU AI Act Art.9</span>
        <span class="pill">EU AI Act Art.12</span>
        <span class="pill">EU AI Act Art.13</span>
        <span class="pill">GDPR Art.22</span>
        <span class="pill">ISO 42001</span>
        <span class="pill">SHA-256 Chain</span>
        <span class="pill">Merkle Proof</span>
      </div>
    </div>
    <div class="terminal">
      <div class="term-bar">
        <div class="dot dr"></div><div class="dot dy"></div><div class="dot dg"></div>
        <div class="tlbl">AILeash v3.0 — Live</div>
      </div>
      <div class="term-body">
        <div class="tc">// AI agent attempts wire transfer</div>
        <div>{</div>
        <div>&nbsp;&nbsp;<span class="tk">"user_id"</span>: <span class="ts">"agent_fin_01"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"action"</span>: <span class="ts">"wire_transfer"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"amount"</span>: <span class="tv">18500</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"country"</span>: <span class="ts">"RU"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"device_risk"</span>: <span class="tv">0.61</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"anomaly"</span>: <span class="tv">0.72</span></div>
        <div>}</div><br>
        <div class="tc">// AILeash responds — 12ms</div>
        <div>{</div>
        <div>&nbsp;&nbsp;<span class="tk">"decision"</span>: <span class="tb">"BLOCK"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"score"</span>: <span class="tv">0.9141</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"reasons"</span>: [<span class="ts">"unsafe_country"</span>, <span class="ts">"behaviour_anomaly"</span>],</div>
        <div>&nbsp;&nbsp;<span class="tk">"audit_hash"</span>: <span class="ts">"a3f9c1d8..."</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"merkle_root"</span>: <span class="ts">"7e2b4f91..."</span></div>
        <div>}</div>
      </div>
    </div>
  </div>
</section>
<section class="stats">
  <div class="stats-inner">
    <div class="stat"><div class="stat-n">0</div><div class="stat-l">Dependencies</div></div>
    <div class="stat"><div class="stat-n">&lt;15ms</div><div class="stat-l">Decision Time</div></div>
    <div class="stat"><div class="stat-n">SHA-256</div><div class="stat-l">Audit Chain</div></div>
    <div class="stat"><div class="stat-n">9+</div><div class="stat-l">Risk Signals</div></div>
    <div class="stat"><div class="stat-n">Aug 26</div><div class="stat-l">EU AI Act</div></div>
  </div>
</section>
<section class="sec" id="compliance">
  <div class="sec-inner">
    <div class="sec-lbl">Regulatory Compliance</div>
    <h2>Built for the <span>EU AI Act</span></h2>
    <p class="sec-sub">Regulation 2024/1689 enforcement begins August 2026. High-risk AI systems must implement risk management, audit trails, transparency, and human oversight. AILeash delivers every mandatory layer.</p>
    <div class="grid3">
      <div class="card"><div class="card-ref">Art. 9 — Risk Management</div><h3>Continuous Assessment</h3><p>Every AI action assessed in real time using a proprietary multi-signal risk engine. Risk accumulates across sessions. No action escapes governance.</p></div>
      <div class="card"><div class="card-ref">Art. 12 — Record Keeping</div><h3>Tamper-Evident Chain</h3><p>SHA-256 chained ledger with Merkle proof verification. Every decision cryptographically linked. Chain integrity verifiable at any time.</p></div>
      <div class="card"><div class="card-ref">Art. 13 — Transparency</div><h3>Explainable Decisions</h3><p>Every ALLOW, CHALLENGE, or BLOCK returns human-readable reasons. No black boxes. Every factor surfaced for regulatory review.</p></div>
      <div class="card"><div class="card-ref">Art. 17 — Quality Management</div><h3>Deterministic Scoring</h3><p>Same inputs always produce the same output. Version-locked scoring logic. Full reproducibility for regulatory audit.</p></div>
      <div class="card"><div class="card-ref">GDPR Art. 22</div><h3>Human Oversight</h3><p>CHALLENGE decisions create a mandatory human review pathway. No fully automated high-risk decisions without oversight capability.</p></div>
      <div class="card"><div class="card-ref">ISO 42001</div><h3>AI Management System</h3><p>Aligned with ISO 42001. Risk identification, treatment, monitoring baked into the core. Persistent audit trail survives restarts.</p></div>
    </div>
  </div>
</section>
<section class="sec" id="how">
  <div class="sec-inner">
    <div class="sec-lbl">How It Works</div>
    <h2>Three Steps. <span>One Decision.</span></h2>
    <p class="sec-sub">Every AI action passes through AILeash before it executes. Real-time. Automatic. Fully audited.</p>
    <div class="how-grid">
      <div class="how-card"><div class="how-num">01</div><h3>Send The Action</h3><p>Your AI agent sends the proposed action to AILeash via a single API call before executing. Amount, location, device context, and behavioural signals included.</p></div>
      <div class="how-card"><div class="how-num">02</div><h3>Proprietary Scoring</h3><p>AILeash runs the action through a proprietary multi-signal risk engine with action-type profiles. Behavioural patterns, velocity, geography, and trust history analysed.</p></div>
      <div class="how-card"><div class="how-num">03</div><h3>Decision & Audit</h3><p>A decision returned in under 15ms with reasons and a Merkle-proofed SHA-256 audit record written to the tamper-evident chain.</p></div>
    </div>
    <div class="dec-grid">
      <div class="dec-card dec-a"><div class="dec-v">ALLOW</div><div class="dec-r">LOW RISK — ACTION PROCEEDS</div><div class="dec-d">Action within acceptable risk parameters. Trust maintained. SHA-256 + Merkle audit record written.</div></div>
      <div class="dec-card dec-c"><div class="dec-v">CHALLENGE</div><div class="dec-r">ELEVATED RISK — HUMAN REVIEW</div><div class="dec-d">Action flagged. GDPR Art.22 oversight pathway triggered. Full signal breakdown returned.</div></div>
      <div class="dec-card dec-b"><div class="dec-v">BLOCK</div><div class="dec-r">HIGH RISK — ACTION HALTED</div><div class="dec-d">Action stopped immediately. Trust decays. Full explainability reasons returned. Audit record written.</div></div>
    </div>
  </div>
</section>
<section class="sec" id="legal" style="background:#f8f8f8">
  <div class="sec-inner">
    <div class="sec-lbl">Legal Framework</div>
    <h2>Regulation <span>References</span></h2>
    <p class="sec-sub">The specific articles of EU law AILeash addresses.</p>
    <div class="legal-grid">
      <div class="legal-card"><div class="legal-act">EU AI Act — Reg. 2024/1689 — Art. 6</div><h3>High-Risk Classification</h3><p>Article 6 classifies AI systems used in critical infrastructure, employment, education, essential services, and financial services as high-risk. Must comply before August 2026. Fines up to €30M or 6% of global annual turnover.</p></div>
      <div class="legal-card"><div class="legal-act">EU AI Act — Reg. 2024/1689 — Art. 9</div><h3>Risk Management System</h3><p>Requires continuous, iterative risk management throughout the entire AI system lifecycle. Must identify known and foreseeable risks, estimate and evaluate them, and adopt appropriate measures.</p></div>
      <div class="legal-card"><div class="legal-act">EU AI Act — Reg. 2024/1689 — Art. 12</div><h3>Record Keeping & Logging</h3><p>High-risk AI systems must have automatic logging capabilities ensuring traceability. AILeash's SHA-256 chained ledger with Merkle proofs provides mathematically verifiable integrity.</p></div>
      <div class="legal-card"><div class="legal-act">EU AI Act — Reg. 2024/1689 — Art. 13</div><h3>Transparency & Information</h3><p>Systems must be sufficiently transparent to enable deployers to interpret outputs. Every AILeash decision includes human-readable explainability reasons available for regulatory review.</p></div>
      <div class="legal-card"><div class="legal-act">GDPR — Reg. 2016/679 — Art. 22</div><h3>Automated Decision-Making</h3><p>Data subjects have the right not to be subject to decisions based solely on automated processing. AILeash's CHALLENGE class triggers mandatory human review — a legally defensible oversight pathway.</p></div>
      <div class="legal-card"><div class="legal-act">ISO/IEC 42001:2023</div><h3>AI Management Systems</h3><p>Specifies requirements for establishing and improving an AI management system. AILeash's continuous risk assessment, persistent audit trail, and explainable decisions align with core requirements.</p></div>
    </div>
  </div>
</section>
<section class="sec" id="pricing">
  <div class="sec-inner">
    <div class="sec-lbl">Pricing</div>
    <h2>Pay Per Action. <span>Nothing Else.</span></h2>
    <p class="sec-sub">No seats. No minimums on free tier. Billed monthly via Stripe.</p>
    <div class="price-grid">
      <div class="price-card">
        <div class="price-tier">Free Tier</div><div class="price-num">£0</div>
        <div class="price-unit">1,000 actions/month</div>
        <ul class="price-features">
          <li>Full governance engine</li><li>SHA-256 + Merkle audit chain</li>
          <li>ALLOW / CHALLENGE / BLOCK</li><li>Explainable decision reasons</li>
          <li>Persistent velocity tracking</li><li>Chain integrity verification</li>
        </ul>
        <a href="#signup" class="btn-o" style="display:block;text-align:center;text-decoration:none">Start Free</a>
      </div>
      <div class="price-card featured">
        <div class="price-badge">Recommended</div>
        <div class="price-tier">Pay As You Go</div>
        <div class="price-num"><sup>£</sup>0.001</div>
        <div class="price-unit">per action · billed monthly</div>
        <ul class="price-features">
          <li>Everything in Free</li><li>Unlimited actions</li>
          <li>Stripe metered billing</li><li>Action-type risk profiles</li>
          <li>Email support</li><li>EU AI Act compliance docs</li>
        </ul>
        <a href="#signup" class="btn-p" style="display:block;text-align:center;text-decoration:none">Get API Key</a>
      </div>
      <div class="price-card">
        <div class="price-tier">Enterprise</div><div class="price-num">Custom</div>
        <div class="price-unit">flat rate · white-label · on-premise</div>
        <ul class="price-features">
          <li>Everything in Pay As You Go</li><li>On-premise deployment</li>
          <li>White-label SDK</li><li>SLA + dedicated support</li>
          <li>Compliance documentation pack</li><li>Custom risk configuration</li>
        </ul>
        <a href="mailto:justin@monopcontent.com" class="btn-o" style="display:block;text-align:center;text-decoration:none">Contact Us</a>
      </div>
    </div>
  </div>
</section>
<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <div class="sec-lbl">Get Access</div>
    <h2 style="font-family:var(--display);font-size:clamp(36px,4vw,56px);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px">API Key in <span style="color:var(--red)">10 Seconds.</span></h2>
    <p style="font-size:17px;color:var(--muted);line-height:1.7;margin-bottom:40px">Enter your work email. Get an API key instantly. Start governing your AI actions today.</p>
    <div class="fg"><label>Work Email Address</label><input type="email" id="emailInput" placeholder="you@company.com"></div>
    <button class="btn-p btn-full" id="signupBtn" onclick="doSignup()">Get My API Key →</button>
    <div class="form-err" id="formErr"></div>
    <div class="key-result" id="keyResult">
      <div class="key-lbl">Your API Key — Save This Immediately</div>
      <div class="key-val" id="keyVal"></div>
      <button class="key-copy" onclick="copyKey()">Copy Key</button>
      <div class="usage-box">
        <div><em>POST</em> https://aileash.onrender.com/govern</div>
        <div>Authorization: Bearer <em id="keyPreview">YOUR_KEY</em></div>
        <div>Content-Type: application/json</div>
      </div>
    </div>
  </div>
</section>
<footer>
  <div class="foot-inner">
    <div>
      <div class="foot-logo">AI<span>Leash</span></div>
      <p class="foot-desc">Production-grade AI governance and compliance infrastructure. Built for EU AI Act enforcement. SHA-256 + Merkle tamper-evident audit chain. Zero dependencies.</p>
    </div>
    <div class="foot-col">
      <h4>Product</h4>
      <a href="#compliance">Compliance</a><a href="#how">How It Works</a>
      <a href="#legal">Legal Framework</a><a href="#pricing">Pricing</a>
      <a href="https://aileash.onrender.com/" target="_blank">Live API</a>
    </div>
    <div class="foot-col">
      <h4>Company</h4>
      <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a>
      <a href="mailto:justin@monopcontent.com">Contact</a>
      <a href="#">Monop Content · Blyth, UK</a>
    </div>
  </div>
  <div class="foot-bottom">
    <span>© 2026 Monop Content · MIT License</span>
    <span>EU AI Act Art.9 / Art.12 / Art.13 · SHA-256 + Merkle Audit Chain</span>
  </div>
</footer>
<script>
const API='https://aileash.onrender.com';
async function doSignup(){
  const email=document.getElementById('emailInput').value.trim();
  const errEl=document.getElementById('formErr');
  const resEl=document.getElementById('keyResult');
  const btn=document.getElementById('signupBtn');
  errEl.classList.remove('show');resEl.classList.remove('show');
  if(!email||!email.includes('@')){errEl.textContent='ERROR: Please enter a valid email address.';errEl.classList.add('show');return}
  btn.textContent='Creating your key...';btn.disabled=true;
  try{
    const r=await fetch(API+'/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})});
    const d=await r.json();
    if(d.api_key){
      document.getElementById('keyVal').textContent=d.api_key;
      document.getElementById('keyPreview').textContent=d.api_key.slice(0,24)+'...';
      resEl.classList.add('show');btn.textContent='Key Created ✓';
    }else{errEl.textContent='ERROR: '+(d.error||'Signup failed.');errEl.classList.add('show');btn.textContent='Get My API Key →';btn.disabled=false}
  }catch(e){errEl.textContent='ERROR: Could not reach API.';errEl.classList.add('show');btn.textContent='Get My API Key →';btn.disabled=false}
}
function copyKey(){
  navigator.clipboard.writeText(document.getElementById('keyVal').textContent).then(()=>{
    const b=document.querySelector('.key-copy');b.textContent='Copied ✓';setTimeout(()=>b.textContent='Copy Key',2000)
  })
}
document.getElementById('emailInput').addEventListener('keydown',e=>{if(e.key==='Enter')doSignup()});
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): print(f"  [{self.address_string()}] {fmt%args}")
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization")
        self.end_headers()
    def do_GET(self):
        path=urlparse(self.path).path.rstrip("/")
        if path in ("","/"): send_html(self,LANDING)
        elif path=="/health": send(self,{"status":"ok","service":"AILeash","version":VERSION,"chain_tip":chain_tip()[:16]+"...","merkle_root":get_merkle_root()[:16]+"..."})
        elif path=="/audit":
            key=get_key(self)
            if not key or not validate_key(key): err(self,"API key required",401); return
            with _db_lock:
                rows=_conn.execute("SELECT ts,user_id,event_json,result_json,prev_hash,audit_hash,merkle_root FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()
            send(self,{"count":len(rows),"records":[{"ts":r[0],"user_id":r[1],"event":json.loads(r[2]),"result":json.loads(r[3]),"prev_hash":r[4],"audit_hash":r[5],"merkle_root":r[6]} for r in rows]})
        elif path=="/audit/verify":
            key=get_key(self)
            if not key or not validate_key(key): err(self,"API key required",401); return
            send(self,verify_chain())
        elif path=="/audit/root":
            key=get_key(self)
            if not key or not validate_key(key): err(self,"API key required",401); return
            send(self,{"merkle_root":get_merkle_root()})
        elif path.startswith("/user/"):
            key=get_key(self)
            if not key or not validate_key(key): err(self,"API key required",401); return
            send(self,{"user_id":path[6:],**load_user(path[6:])})
        else: err(self,"Not found",404)
    def do_POST(self):
        path=urlparse(self.path).path.rstrip("/")
        length=int(self.headers.get("Content-Length",0))
        try: body=json.loads(self.rfile.read(length)) if length else {}
        except: err(self,"Invalid JSON"); return
        if path=="/signup":
            email=body.get("email")
            if not email: err(self,"Email required"); return
            if not STRIPE_SECRET: err(self,"Stripe not configured. Add STRIPE_SECRET in Railway Variables."); return
            if not STRIPE_PRICE_ID: err(self,"Stripe not ready. Contact support."); return
            customer=stripe_call("POST","/customers",{"email":email,"description":"AILeash API customer"})
            cid=customer.get("id")
            if not cid: err(self,"Stripe error: "+customer.get("error",{}).get("message","unknown")); return
            stripe_call("POST","/subscriptions",{"customer":cid,"items[0][price]":STRIPE_PRICE_ID})
            key=create_api_key(email,cid)
            send(self,{"message":"Welcome to AILeash","api_key":key,"email":email,"pricing":"£0.001 per action","usage":"Authorization: Bearer "+key,"version":VERSION})
            return
        if path=="/govern":
            key=get_key(self)
            if not key: err(self,"API key required. POST email to /signup",401); return
            if not validate_key(key): err(self,"Invalid API key",401); return
            try: send(self,govern(body,api_key=key))
            except ValueError as e: err(self,str(e))
            except Exception as e: err(self,f"Internal error: {e}",500)
            return
        err(self,"Not found",404)

if __name__=="__main__":
    print("="*52)
    print("  AILEASH GOVERNANCE ENGINE v3.0")
    print("  Monop Content · Blyth, UK")
    print("  EU AI Act Art.9 / Art.12 / Art.13")
    print("="*52)
    setup_stripe()
    server=HTTPServer(("0.0.0.0",PORT),Handler)
    print(f"\n  Port {PORT} — Ready.\n")
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
