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
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"  Stripe: {STRIPE_PRICE_ID}")
        return
    print("  Setting up Stripe...")
    product = stripe_call("POST", "/products", {"name": "AILeash Governance API", "description": "AI governance API — charged per action. EU AI Act compliant."})
    price = stripe_call("POST", "/prices", {"product": product["id"], "currency": "gbp", "billing_scheme": "per_unit", "unit_amount": 1, "recurring[interval]": "month", "recurring[usage_type]": "metered", "nickname": "Per Action"})
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute("INSERT INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()
    print(f"  Stripe ready: {STRIPE_PRICE_ID}")

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

def load_user(uid):
    with _db_lock:
        row = _conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row: return {"trust":0.5,"last_country":None}
    return {"trust":row[0],"last_country":row[1]}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",(uid,trust,country))
        _conn.commit()

def prune(q,s):
    c=now()-s
    while q and q[0]<c: q.popleft()

def update_windows(uid):
    t=now()
    for q in [WINDOW_60S[uid],WINDOW_5M[uid],WINDOW_1H[uid]]: q.append(t)
    prune(WINDOW_60S[uid],60); prune(WINDOW_5M[uid],300); prune(WINDOW_1H[uid],3600)

def velocity(uid):
    return {"60s":len(WINDOW_60S[uid]),"5m":len(WINDOW_5M[uid]),"1h":len(WINDOW_1H[uid])}

def compute_score(s):
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
    return {"valid":True,"blocks":len(rows),"message":"Chain intact — all hashes verified"}

def govern(event,api_key=None):
    missing=REQUIRED_FIELDS-event.keys()
    if missing: raise ValueError(f"Missing: {missing}")
    ts=now()
    state=load_user(event["user_id"])
    update_windows(event["user_id"])
    v=velocity(event["user_id"])
    signals={"trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],"amount":event["amount"],"device_risk":event["device_risk"],"anomaly":event["anomaly"],"country_shift":state["last_country"] is not None and state["last_country"]!=event["country"],"unsafe_country":event["country"] not in SAFE_COUNTRIES}
    score=compute_score(signals)
    decision=decide(score)
    reasons=explain(signals)
    trust=update_trust(state["trust"],decision)
    save_user(event["user_id"],trust,event["country"])
    result={"decision":decision,"score":round(score,4),"trust":round(trust,4),"reasons":reasons}
    result["audit_hash"]=append_audit(event,result,ts)
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
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#03050a;--surface:#080d16;--surface2:#0d1520;--border:rgba(255,255,255,0.05);--border2:rgba(255,255,255,0.1);--accent:#00e5ff;--accent2:#ff3b5c;--accent3:#00ff88;--warn:#ffaa00;--text:#dde4f0;--muted:#5a6a8a;--mono:'JetBrains Mono',monospace;--sans:'Syne',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(0,229,255,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,0.02) 1px,transparent 1px);background-size:80px 80px;pointer-events:none;z-index:0}
nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:16px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(3,5,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.logo{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--accent);letter-spacing:-1px}
.logo em{color:rgba(255,255,255,0.3);font-style:normal;font-size:11px;margin-left:8px;letter-spacing:2px}
.nav-r{display:flex;gap:24px;align-items:center}
.nav-r a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:600;transition:color .2s}
.nav-r a:hover{color:var(--text)}
.nav-cta{background:var(--accent)!important;color:#000!important;padding:9px 20px;border-radius:6px;font-weight:700!important}
.hero{min-height:100vh;display:flex;align-items:center;position:relative;z-index:1;padding:120px 48px 80px}
.hero-grid{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.1fr 0.9fr;gap:80px;align-items:center;width:100%}
.chip{display:inline-flex;align-items:center;gap:8px;background:rgba(0,229,255,0.07);border:1px solid rgba(0,229,255,0.15);padding:6px 14px;border-radius:100px;font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:1px;margin-bottom:32px}
.chip-dot{width:6px;height:6px;background:var(--accent);border-radius:50%;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
h1{font-size:clamp(44px,5.5vw,72px);font-weight:800;line-height:1.05;letter-spacing:-2px;margin-bottom:24px}
h1 .cy{color:var(--accent)}h1 .re{color:var(--accent2)}
.hero-p{font-size:18px;color:var(--muted);line-height:1.75;margin-bottom:40px;max-width:520px}
.btns{display:flex;gap:14px;flex-wrap:wrap}
.btn-p{background:var(--accent);color:#000;padding:14px 28px;border-radius:8px;font-weight:700;font-size:15px;text-decoration:none;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}
.btn-p:hover{background:#33eaff;transform:translateY(-2px)}
.btn-s{background:transparent;color:var(--text);padding:14px 28px;border-radius:8px;font-weight:600;font-size:15px;text-decoration:none;border:1px solid var(--border2);cursor:pointer;font-family:var(--sans);transition:all .2s}
.law-tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:32px}
.law-tag{background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.25);padding:5px 12px;border-radius:4px;font-family:var(--mono);font-size:11px;color:#a78bfa;letter-spacing:.5px}
.term{background:var(--surface);border:1px solid var(--border2);border-radius:14px;overflow:hidden;font-family:var(--mono);font-size:12.5px;box-shadow:0 40px 80px rgba(0,0,0,.6);animation:lev 7s ease-in-out infinite}
@keyframes lev{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.term-bar{background:var(--surface2);padding:14px 18px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)}
.d{width:11px;height:11px;border-radius:50%}.dr{background:#ff5f56}.dy{background:#ffbd2e}.dg{background:#27c93f}
.term-title{margin-left:auto;font-size:11px;color:var(--muted);letter-spacing:1px}
.term-body{padding:22px;line-height:2.1}
.tc{color:var(--muted)}.tk{color:#79b8ff}.tv{color:#f0c674}.ts{color:#9ecbff}
.ta{color:var(--accent3);font-weight:700}.tw{color:var(--warn);font-weight:700}.tb{color:var(--accent2);font-weight:700}
.stats-bar{position:relative;z-index:1;border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:48px 0}
.stats-inner{max-width:1100px;margin:0 auto;padding:0 48px;display:grid;grid-template-columns:repeat(5,1fr);gap:32px;text-align:center}
.stat-n{font-family:var(--mono);font-size:36px;font-weight:800;color:var(--accent);letter-spacing:-2px}
.stat-l{font-size:13px;color:var(--muted);margin-top:6px;font-weight:600}
.sec{position:relative;z-index:1;padding:100px 48px}
.sec-inner{max-width:1100px;margin:0 auto}
.lbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;color:var(--accent);text-transform:uppercase;margin-bottom:16px}
h2{font-size:clamp(32px,4vw,52px);font-weight:800;letter-spacing:-1.5px;margin-bottom:16px;line-height:1.1}
.sec-sub{font-size:17px;color:var(--muted);max-width:580px;line-height:1.7;margin-bottom:60px}
.algo-table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:13px;margin-top:40px}
.algo-table th{text-align:left;padding:12px 16px;border-bottom:2px solid var(--accent);color:var(--accent);font-size:11px;letter-spacing:2px;text-transform:uppercase}
.algo-table td{padding:14px 16px;border-bottom:1px solid var(--border);color:var(--text)}
.algo-table tr:hover td{background:rgba(0,229,255,0.03)}
.wt{color:var(--accent);font-weight:700}
.comp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}
.comp-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:28px;position:relative;overflow:hidden}
.comp-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}
.comp-art{font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:2px;margin-bottom:10px}
.comp-card h3{font-size:15px;font-weight:700;margin-bottom:10px}
.comp-card p{font-size:13px;color:var(--muted);line-height:1.65}
.dec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}
.dec-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:32px;position:relative;overflow:hidden}
.dec-allow::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent3)}
.dec-challenge::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--warn)}
.dec-block::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent2)}
.dec-label{font-family:var(--mono);font-size:22px;font-weight:800;margin-bottom:8px}
.dec-allow .dec-label{color:var(--accent3)}.dec-challenge .dec-label{color:var(--warn)}.dec-block .dec-label{color:var(--accent2)}
.dec-thresh{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:16px}
.dec-desc{font-size:14px;color:var(--muted);line-height:1.65}
.chain-viz{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px;margin-top:40px;font-family:var(--mono);font-size:12px}
.chain-row{display:flex;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--border)}
.chain-row:last-child{border:none}
.chain-block{background:rgba(0,229,255,0.07);border:1px solid rgba(0,229,255,0.15);padding:8px 14px;border-radius:6px;color:var(--accent);font-size:11px;white-space:nowrap}
.chain-arrow{color:var(--muted);font-size:16px}
.chain-hash{color:var(--muted);font-size:11px;word-break:break-all;flex:1}
.cda{color:var(--accent3)}.cdc{color:var(--warn)}.cdb{color:var(--accent2)}
.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:40px}
.price-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:36px;position:relative}
.price-card.featured{border-color:var(--accent);background:linear-gradient(135deg,rgba(0,229,255,0.04) 0%,var(--surface) 60%)}
.price-badge{position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:var(--accent);color:#000;font-family:var(--mono);font-size:10px;font-weight:700;padding:4px 14px;border-radius:100px;letter-spacing:1px;white-space:nowrap}
.price-tier{font-family:var(--mono);font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}
.price-num{font-family:var(--mono);font-size:44px;font-weight:800;letter-spacing:-2px;margin-bottom:4px}
.price-unit{font-size:13px;color:var(--muted);margin-bottom:28px}
.price-features{list-style:none;margin-bottom:32px}
.price-features li{font-size:14px;color:var(--muted);padding:9px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.price-features li::before{content:'✓';color:var(--accent);font-family:var(--mono);font-size:12px;flex-shrink:0}
.signup-sec{padding:100px 48px;background:var(--surface);border-top:1px solid var(--border);position:relative;z-index:1}
.signup-inner{max-width:580px;margin:0 auto;text-align:center}
.form-wrap{margin-top:40px;text-align:left}
.fg{margin-bottom:16px}
.fg label{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.fg input{width:100%;background:var(--bg);border:1px solid var(--border2);color:var(--text);padding:14px 16px;border-radius:8px;font-size:15px;font-family:var(--sans);outline:none;transition:border-color .2s}
.fg input:focus{border-color:var(--accent)}
.fg input::placeholder{color:var(--muted)}
.btn-full{width:100%;margin-top:8px;padding:16px;font-size:16px;font-weight:700}
.key-result{display:none;margin-top:24px;background:var(--bg);border:1px solid rgba(0,229,255,0.25);border-radius:10px;padding:24px}
.key-result.show{display:block}
.key-label{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--accent);margin-bottom:10px}
.key-val{font-family:var(--mono);font-size:13px;color:var(--accent3);word-break:break-all;background:rgba(0,255,136,0.05);padding:14px;border-radius:6px;border:1px solid rgba(0,255,136,0.1)}
.key-copy{margin-top:12px;background:transparent;border:1px solid var(--border2);color:var(--muted);padding:8px 18px;border-radius:6px;font-family:var(--mono);font-size:11px;cursor:pointer;transition:all .2s}
.key-copy:hover{border-
