import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.0.0"
SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}
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
    if STRIPE_PRICE_ID:
        print(f"  Stripe ready: {STRIPE_PRICE_ID}")
        return
    if not STRIPE_SECRET:
        print("  WARNING: No STRIPE_SECRET set.")
        return
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"  Stripe ready: {STRIPE_PRICE_ID}")
        return
    print("  No STRIPE_PRICE_ID set. Add it in Railway Variables.")

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
.key-r
