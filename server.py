# ==============================================================================
# AILEASH PLATFORM v5.0.0
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================

import json,math,time,sqlite3,hashlib,threading
import urllib.request,urllib.parse,os,secrets
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse

PORT=int(os.environ.get("PORT",8080))
STRIPE_SECRET=os.environ.get("STRIPE_SECRET","")
BREVO_API_KEY=os.environ.get("BREVO_API_KEY","")
HOST=os.environ.get("HOST","https://sebbi.pro")
DB="aileash.db"
VERSION="5.0.0"
OWNER_NAME="Justin Antony Dobson"
OWNER_EMAIL="justin@monopcontent.com"
OWNER_PHONE="07908 269428"
SAFE={"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ={"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA=100
STRIPE_PRICE_AL=""
STRIPE_PRICE_GU=""
_db_lock=threading.Lock()
_load_lock=threading.Lock()
_req_times=deque()
_overloaded=False
_key_wins=defaultdict(lambda:{"min":deque(),"hour":deque()})
_key_lock=threading.Lock()

def get_conn():
    c=sqlite3.connect(DB,check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY,trust REAL DEFAULT 0.5,last_country TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,user_id TEXT,event_json TEXT,result_json TEXT,prev_hash TEXT,audit_hash TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS api_keys(key TEXT PRIMARY KEY,email TEXT,phone TEXT,name TEXT,org TEXT,org_type TEXT,product TEXT DEFAULT 'aileash',devices INTEGER DEFAULT 1,stripe_customer TEXT DEFAULT '',stripe_sub TEXT DEFAULT '',actions_used INTEGER DEFAULT 0,created REAL,active INTEGER DEFAULT 1,is_paid INTEGER DEFAULT 0,free_quota INTEGER DEFAULT 100,plan_type TEXT DEFAULT 'free')")
    c.execute("CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS load_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,rps REAL,note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS contact_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,name TEXT,email TEXT,phone TEXT,org TEXT,message TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.commit()
    return c

_conn=get_conn()

def track_request():
    global _overloaded
    t=time.time()
    with _load_lock:
        _req_times.append(t)
        while _req_times and _req_times[0]<t-1.0:_req_times.popleft()
        rps=len(_req_times)
        if rps>200 and not _overloaded:
            _overloaded=True
            try:_conn.execute("INSERT INTO load_log(ts,rps,note) VALUES(?,?,?)",(t,rps,"THROTTLE"));_conn.commit()
            except:pass
        elif rps<140 and _overloaded:_overloaded=False

def is_over():
    with _load_lock:return _overloaded

def get_rps():
    t=time.time()
    with _load_lock:return sum(1 for x in _req_times if x>=t-1.0)

def check_rate(key):
    t=time.time()
    with _key_lock:
        w=_key_wins[key]
        while w["min"] and w["min"][0]<t-60:w["min"].popleft()
        while w["hour"] and w["hour"][0]<t-3600:w["hour"].popleft()
        if len(w["min"])>=60:return False,"rate_limit_minute"
        if len(w["hour"])>=1000:return False,"rate_limit_hour"
        w["min"].append(t);w["hour"].append(t)
        return True,None

def send_email(to_email,to_name,subject,html):
    if not BREVO_API_KEY:print(f"EMAIL SKIP:{to_email}",flush=True);return
    try:
        req=urllib.request.Request("https://api.brevo.com/v3/smtp/email",
            data=json.dumps({"sender":{"name":"AILeash","email":"noreply@monopcontent.com"},"to":[{"email":to_email,"name":to_name}],"subject":subject,"htmlContent":html}).encode(),
            headers={"api-key":BREVO_API_KEY,"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=10):pass
        print(f"EMAIL OK:{to_email}",flush=True)
    except Exception as e:print(f"EMAIL ERR:{e}",flush=True)

def welcome_email(name,email,product,key,devices,monthly):
    pn="AILeash Guardian" if product=="guardian" else "SonicBoom" if product=="sonicboom" else "AILeash"
    app_url=f"{HOST}/guardian-app" if product=="guardian" else f"{HOST}/sonicboom" if product=="sonicboom" else f"{HOST}/#signup"
    html=f"<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'><div style='max-width:580px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'><div style='background:#0a0f1e;padding:32px;border-bottom:4px solid #c9a84c'><div style='font-size:22px;color:#fff;font-weight:900'>Monop Content <span style='color:#c9a84c'>Platform</span></div></div><div style='padding:36px'><p style='font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:16px'>Welcome{', '+name.split()[0] if name.strip() else ''}.</p><p style='font-size:14px;color:#64748b;line-height:1.7'>Your {pn} API key is ready. 100 free decisions included. After trial: £{monthly:.2f}/month for {devices} device{'s' if devices!=1 else ''} via Stripe.</p><div style='background:#0a0f1e;border-radius:6px;padding:20px;margin:20px 0'><div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your API Key</div><div style='font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all'>{key}</div></div><p style='font-size:14px;color:#64748b;margin-bottom:16px'>Get started at <a href='{app_url}' style='color:#c9a84c'>{app_url}</a></p><p style='font-size:13px;color:#64748b'><strong>{OWNER_NAME}</strong><br><a href='mailto:{OWNER_EMAIL}' style='color:#c9a84c'>{OWNER_EMAIL}</a> &middot; {OWNER_PHONE}</p></div></div></body></html>"
    send_email(email,name,f"Your {pn} API Key",html)

def contact_email(name,email,phone,org,message):
    html=f"<html><body style='font-family:Arial,sans-serif;padding:20px;color:#333'><h2>New Contact: {name}</h2><p><b>Email:</b> {email}</p><p><b>Phone:</b> {phone}</p><p><b>Org:</b> {org}</p><p><b>Message:</b><br>{message}</p></body></html>"
    send_email(OWNER_EMAIL,OWNER_NAME,f"Contact: {name}",html)

def stripe_call(method,endpoint,data=None):
    if not STRIPE_SECRET:return None
    try:
        req=urllib.request.Request("https://api.stripe.com/v1"+endpoint,
            data=urllib.parse.urlencode(data).encode() if data else None,
            headers={"Authorization":"Bearer "+STRIPE_SECRET,"Content-Type":"application/x-www-form-urlencoded"},method=method)
        with urllib.request.urlopen(req,timeout=10) as r:return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:return json.loads(e.read())
        except:return None
    except Exception as e:print(f"Stripe:{e}",flush=True);return None

def make_price(name,desc):
    p=stripe_call("POST","/products",{"name":name,"description":desc})
    if not p or "id" not in p:return None
    pr=stripe_call("POST","/prices",{"product":p["id"],"currency":"gbp","unit_amount":50,"recurring[interval]":"month"})
    return pr["id"] if pr and "id" in pr else None

def setup_stripe():
    global STRIPE_PRICE_AL,STRIPE_PRICE_GU
    if not STRIPE_SECRET:print("No STRIPE_SECRET",flush=True);return
    with _db_lock:
        ra=_conn.execute("SELECT v FROM config WHERE k='price_al'").fetchone()
        rg=_conn.execute("SELECT v FROM config WHERE k='price_gu'").fetchone()
    if ra and ra[0]:STRIPE_PRICE_AL=ra[0]
    else:
        pid=make_price("AILeash","AI governance. 50p per device per month.")
        if pid:
            STRIPE_PRICE_AL=pid
            with _db_lock:_conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('price_al',?)",(pid,));_conn.commit()
    if rg and rg[0]:STRIPE_PRICE_GU=rg[0]
    else:
        pid=make_price("AILeash Guardian","Child safety. 50p per device per month.")
        if pid:
            STRIPE_PRICE_GU=pid
            with _db_lock:_conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('price_gu',?)",(pid,));_conn.commit()
    print(f"Stripe AL:{STRIPE_PRICE_AL[:12] if STRIPE_PRICE_AL else 'none'} GU:{STRIPE_PRICE_GU[:12] if STRIPE_PRICE_GU else 'none'}",flush=True)

def create_key(email,phone="",name="",org="",org_type="",product="aileash",devices=1):
    email=str(email).strip().lower()
    if not email or "@" not in email:return None,"invalid_email"
    key=("ag_live_" if product=="guardian" else "al_live_")+secrets.token_hex(24)
    with _db_lock:
        try:
            _conn.execute("INSERT INTO api_keys(key,email,phone,name,org,org_type,product,devices,stripe_customer,stripe_sub,actions_used,created,active,is_paid,free_quota,plan_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key,email,phone,name,org,org_type,product,devices,"","",0,time.time(),1,0,FREE_QUOTA,"free"))
            _conn.commit()
        except sqlite3.IntegrityError:return None,"email_exists"
    return key,None

def get_key(key):
    with _db_lock:
        return _conn.execute("SELECT email,actions_used,active,is_paid,free_quota,plan_type,product FROM api_keys WHERE key=?",(key,)).fetchone()

def inc_usage(key):
    with _db_lock:_conn.execute("UPDATE api_keys SET actions_used=actions_used+1 WHERE key=?",(key,));_conn.commit()

W60=defaultdict(deque);W5M=defaultdict(deque);W1H=defaultdict(deque)
def now():return time.time()
def clamp(x,a=0.0,b=1.0):return max(a,min(b,x))
def sha(p):return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()

def upd_vel(uid):
    t=now()
    for q in [W60[uid],W5M[uid],W1H[uid]]:q.append(t)
    c=now()
    W60[uid]=deque(x for x in W60[uid] if x>=c-60)
    W5M[uid]=deque(x for x in W5M[uid] if x>=c-300)
    W1H[uid]=deque(x for x in W1H[uid] if x>=c-3600)

def vel(uid):return{"60s":len(W60[uid]),"5m":len(W5M[uid]),"1h":len(W1H[uid])}

def load_user(uid):
    with _db_lock:r=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?",(uid,)).fetchone()
    return{"trust":r[0],"last_country":r[1]} if r else{"trust":0.5,"last_country":None}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",(uid,trust,country))
        _conn.commit()

def score_event(s):
    reasons=[]
    sc=(1-s["trust"])*0.30
    v60=s["v60"];sc+=min(v60/20,1)*0.15
    if v60>10:reasons.append("velocity_spike")
    sc+=min(s["v5m"]/50,1)*0.10+min(s["v1h"]/200,1)*0.10
    amt=float(s.get("amount",0));sc+=min(math.log1p(amt)/math.log1p(10000),1)*0.15
    if amt>500:reasons.append("high_amount")
    dr=float(s.get("device_risk",0));sc+=dr*0.10
    if dr>0.5:reasons.append("risky_device")
    an=float(s.get("anomaly",0));sc+=an*0.10
    if an>0.5:reasons.append("behaviour_anomaly")
    if s.get("country_shift"):sc+=0.10;reasons.append("country_shift")
    if s.get("unsafe_country"):sc+=0.10;reasons.append("unsafe_country")
    if s["trust"]<0.4:reasons.append("low_trust")
    return round(clamp(sc),4),reasons

def decide(sc):
    if sc<0.35:return"ALLOW"
    if sc<0.70:return"CHALLENGE"
    return"BLOCK"

def upd_trust(t,d):
    if d=="ALLOW":t+=(1-t)*0.01
    elif d=="CHALLENGE":t-=t*0.02
    elif d=="BLOCK":t-=t*0.08
    return clamp(t,0.05,1.0)

def chain_tip():
    with _db_lock:r=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return r[0] if r else"GENESIS"

def seal(event,result,ts):
    prev=chain_tip()
    h=sha({"prev_hash":prev,"ts":ts,"event":event,"result":result})
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",(ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h))
        _conn.commit()
    return h

def verify_chain():
    with _db_lock:rows=_conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows:return{"valid":True,"blocks":0,"message":"Empty chain"}
    prev="GENESIS"
    for i,row in enumerate(rows):
        p={"prev_hash":row[2],"ts":row[4],"event":json.loads(row[0]),"result":json.loads(row[1])}
        if sha(p)!=row[3] or row[2]!=prev:return{"valid":False,"broken_at":i,"message":f"Tampered at {i}"}
        prev=row[3]
    return{"valid":True,"blocks":len(rows),"tip":rows[-1][3],"message":"Chain intact"}

def govern(event,api_key=None):
    missing=REQ-event.keys()
    if missing:raise ValueError(f"Missing:{missing}")
    if api_key:
        ok,ec=check_rate(api_key)
        if not ok:return{"error":ec},429
        ki=get_key(api_key)
        if not ki:return{"error":"invalid_api_key"},401
        email,used,active,is_paid,quota,plan,product=ki
        if not active:return{"error":"account_inactive"},403
        if not is_paid and used>=quota:return{"error":"quota_exceeded","message":f"Upgrade at {HOST}/#pricing"},429
    ts=now();uid=event["user_id"]
    state=load_user(uid);upd_vel(uid);v=vel(uid)
    country=event["country"]
    signals={"trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],
        "amount":float(event.get("amount",0)),"device_risk":float(event.get("device_risk",0)),
        "anomaly":float(event.get("anomaly",0)),
        "country_shift":state["last_country"] is not None and state["last_country"]!=country,
        "unsafe_country":country not in SAFE}
    sc,reasons=score_event(signals)
    dec=decide(sc);trust=upd_trust(state["trust"],dec)
    save_user(uid,trust,country)
    result={"decision":dec,"score":sc,"trust":round(trust,4),"reasons":reasons,"version":VERSION,"timestamp":ts}
    result["audit_hash"]=seal(event,result,ts)
    if api_key:inc_usage(api_key)
    return result,200

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
        try:return json.loads(h.rfile.read(n))
        except:return{}
    return{}

def get_bearer(h):
    auth=h.headers.get("Authorization","")
    if auth.startswith("Bearer "):return auth[7:]
    return h.headers.get("X-API-Key","").strip()

def load_file(name):
    try:
        with open(name,"r",encoding="utf-8") as f:return f.read()
    except:return None

# ============================================================================
# HOMEPAGE — ALL THREE PRODUCTS
# ============================================================================
HOMEPAGE="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Monop Content &mdash; AILeash &middot; Guardian &middot; SonicBoom</title>
<meta name="description" content="Three AI compliance and safety products. Free API to platforms. Users pay for protection. You set the margin. We take 50p per device per month.">
<meta name="keywords" content="AI compliance software UK,EU AI Act compliance tool,Online Safety Act compliance platform,child safety API,grooming detection software,Ofcom compliance tool,AI governance platform UK">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--navy2:#111827;--gold:#c9a84c;--gold2:#e8c96a;--red:#cc0000;--green:#00875a;--cyan:#00d4ff;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--text:#1a202c;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--white);color:var(--text);font-family:var(--sans);overflow-x:hidden}
html{scroll-behavior:smooth}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:var(--navy);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between}
.nav-logo{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 20px;font-weight:700!important;border-radius:4px}
.alert-bar{background:var(--red);padding:11px 48px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--white);letter-spacing:1px;text-transform:uppercase;margin-top:68px}.alert-bar strong{color:#e8c96a}
.hero{background:var(--navy);padding:80px 48px 100px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 15% 60%,rgba(201,168,76,0.06) 0%,transparent 55%)}
.hero-inner{max-width:1200px;margin:0 auto;position:relative;z-index:1;text-align:center}
.kdot{display:inline-block;width:7px;height:7px;background:var(--red);border-radius:50%;animation:blink 1.5s infinite;margin-right:8px;vertical-align:middle}
@keyframes blink{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.4)}}
.ktext{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;vertical-align:middle}
h1{font-family:var(--display);font-size:clamp(44px,5vw,72px);line-height:1.05;color:var(--white);font-weight:900;margin:16px 0 20px}
h1 em{color:var(--gold);font-style:normal}
h2{font-family:var(--display);font-size:clamp(32px,3.5vw,50px);font-weight:900;margin-bottom:14px;line-height:1.1}
h2 em{color:var(--gold);font-style:normal}
.hero-sub{font-size:18px;color:rgba(255,255,255,0.5);line-height:1.75;max-width:680px;margin:0 auto 48px}
.hero-sub strong{color:var(--white)}
.hero-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.btn-gold{background:var(--gold);color:var(--navy);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-gold:hover{background:var(--gold2);transform:translateY(-2px)}
.btn-red{background:var(--red);color:var(--white);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-red:hover{background:#aa0000;transform:translateY(-2px)}
.btn-cyan{background:var(--cyan);color:var(--navy);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-cyan:hover{background:#33ddff;transform:translateY(-2px)}
.btn-ghost{background:transparent;color:var(--white);padding:14px 28px;border:1px solid rgba(255,255,255,0.2);font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-ghost:hover{border-color:var(--gold);color:var(--gold)}
.divider{height:4px;background:linear-gradient(90deg,var(--navy) 0%,var(--gold) 33%,var(--red) 66%,var(--cyan) 100%)}
.stats-strip{background:var(--navy)}
.stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}
.stat{padding:28px 20px;border-right:1px solid rgba(255,255,255,0.05);text-align:center}.stat:last-child{border:none}
.stat-n{font-family:var(--display);font-size:36px;color:var(--gold);font-weight:900}
.stat-l{font-size:10px;color:rgba(255,255,255,0.25);margin-top:4px;letter-spacing:1px;text-transform:uppercase}
.slbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;opacity:.4}
.sec-sub{font-size:15px;color:var(--muted);max-width:580px;line-height:1.7;margin-bottom:44px}
.sec{padding:80px 48px;border-bottom:1px solid var(--border)}
.sec-inner{max-width:1200px;margin:0 auto}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:start}
.products-sec{padding:80px 48px;background:var(--off);border-bottom:1px solid var(--border)}
.products-inner{max-width:1200px;margin:0 auto}
.product-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:var(--border);margin-top:40px}
.pc{background:var(--white);padding:36px 28px;position:relative;overflow:hidden}
.pc::before{content:'';position:absolute;top:0;left:0;right:0;height:4px}
.pc-al::before{background:var(--gold)}
.pc-gu::before{background:var(--red)}
.pc-sb::before{background:var(--cyan)}
.pc-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;display:inline-block;padding:3px 10px;border-radius:2px}
.pc-al .pc-badge{color:var(--gold);background:rgba(201,168,76,0.1);border:1px solid rgba(201,168,76,0.2)}
.pc-gu .pc-badge{color:var(--red);background:rgba(204,0,0,0.06);border:1px solid rgba(204,0,0,0.15)}
.pc-sb .pc-badge{color:var(--cyan);background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.2)}
.pc h3{font-family:var(--display);font-size:26px;font-weight:900;margin-bottom:10px;color:var(--navy)}
.pc-desc{font-size:13px;color:var(--muted);line-height:1.7;margin-bottom:20px}
.pc-features{display:flex;flex-direction:column;gap:6px;margin-bottom:24px}
.pcf{display:flex;align-items:flex-start;gap:8px;font-size:12px;color:var(--muted);padding:6px 0;border-bottom:1px solid var(--border)}
.pcf::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;flex-shrink:0;margin-top:1px}
.pc-al .pcf::before{color:var(--gold)}
.pc-gu .pcf::before{color:var(--red)}
.pc-sb .pcf::before{color:var(--cyan)}
.pc-price{font-family:var(--display);font-size:48px;font-weight:900;line-height:1;margin-bottom:4px}
.pc-al .pc-price{color:var(--gold)}
.pc-gu .pc-price{color:var(--red)}
.pc-sb .pc-price{color:var(--cyan)}
.pc-price sup{font-size:24px;vertical-align:super}
.pc-price-label{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:20px;letter-spacing:1px}
.btn-block{display:block;text-align:center;padding:14px 24px;border-radius:4px;font-family:var(--sans);font-weight:700;font-size:14px;text-decoration:none;transition:all .2s;border:none;cursor:pointer;width:100%}
.btn-block-al{background:var(--gold);color:var(--navy)}.btn-block-al:hover{background:var(--gold2)}
.btn-block-gu{background:var(--red);color:var(--white)}.btn-block-gu:hover{background:#aa0000}
.btn-block-sb{background:var(--cyan);color:var(--navy)}.btn-block-sb:hover{background:#33ddff}
.pc-note{font-family:var(--mono);font-size:9px;color:var(--muted);text-align:center;margin-top:10px;letter-spacing:1px}
.calc-wrap{background:var(--navy);border-radius:8px;padding:36px;margin-top:40px}
.calc-title{font-family:var(--mono);font-size:10px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}
.calc-row{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:20px;align-items:end}
.calc-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.35);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.calc-input-row{display:flex;align-items:center;gap:8px}
.pound{font-family:var(--display);font-size:28px;color:var(--gold);font-weight:900}
.calc-input{background:rgba(255,255,255,0.08);border:2px solid rgba(201,168,76,0.3);color:var(--white);padding:12px 16px;font-size:20px;font-family:var(--display);font-weight:700;width:120px;border-radius:6px;outline:none;text-align:center}
.calc-input:focus{border-color:var(--gold)}
.calc-devices{background:rgba(255,255,255,0.08);border:2px solid rgba(255,255,255,0.1);color:var(--white);padding:12px 16px;font-size:15px;font-family:var(--sans);width:100%;border-radius:6px;outline:none}
.calc-devices option{background:var(--navy)}
.calc-results{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.05);border-radius:6px;overflow:hidden}
.cr{background:rgba(255,255,255,0.03);padding:20px;text-align:center}
.cr-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.cr-amount{font-family:var(--display);font-size:28px;font-weight:900;line-height:1}
.cr-you{color:#00ff88}.cr-we{color:rgba(255,255,255,0.2)}.cr-user{color:var(--gold)}
.cr-sub{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);margin-top:4px}
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
.sonicboom-sec{padding:80px 48px;background:var(--navy);border-top:4px solid var(--cyan)}
.sb-inner{max-width:1200px;margin:0 auto}
.sb-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}
.sbg{background:rgba(0,212,255,0.04);border:1px solid rgba(0,212,255,0.1);border-radius:8px;padding:24px}
.sbg-icon{font-size:28px;margin-bottom:12px}
.sbg h3{font-family:var(--display);font-size:18px;color:var(--white);font-weight:800;margin-bottom:8px}
.sbg p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.65}
.sbg-stat{font-family:var(--display);font-size:36px;color:var(--cyan);font-weight:900;margin-top:12px}
.sbg-stat-label{font-family:var(--mono);font-size:9px;color:rgba(0,212,255,0.4);letter-spacing:1px;text-transform:uppercase}
.speed-compare{display:grid;grid-template-columns:1fr auto 1fr;gap:0;max-width:500px;margin:40px auto 0;align-items:center}
.sc-before{background:rgba(204,0,0,0.08);border:1px solid rgba(204,0,0,0.2);border-radius:8px 0 0 8px;padding:24px;text-align:center}
.sc-after{background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.3);border-radius:0 8px 8px 0;padding:24px;text-align:center}
.sc-arrow{background:rgba(255,255,255,0.02);border-top:1px solid rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.05);padding:24px 12px;text-align:center;font-size:20px;color:var(--cyan)}
.sc-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.sc-before .sc-label{color:rgba(255,107,107,0.6)}.sc-after .sc-label{color:var(--cyan)}
.sc-speed{font-family:var(--display);font-size:40px;font-weight:900;line-height:1}
.sc-before .sc-speed{color:#ff6b6b}.sc-after .sc-speed{color:var(--cyan)}
.sc-unit{font-family:var(--mono);font-size:10px;margin-top:4px}
.sc-before .sc-unit{color:rgba(255,107,107,0.4)}.sc-after .sc-unit{color:rgba(0,212,255,0.4)}
.engine-sec{padding:80px 48px;background:var(--navy);border-top:4px solid var(--gold)}
.engine-inner{max-width:1200px;margin:0 auto}
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
.pricing-inner{max-width:1200px;margin:0 auto;text-align:center}
.price-note{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.18);margin-top:12px;letter-spacing:1px}
.signup-sec{padding:80px 48px;background:var(--white);border-top:4px solid var(--gold)}
.signup-inner{max-width:580px;margin:0 auto}
.product-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-bottom:28px;border:2px solid var(--border);border-radius:6px;overflow:hidden}
.stab{padding:12px;text-align:center;cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:600;transition:all .2s;background:var(--white);color:var(--muted);border:none;outline:none}
.stab-al-on{background:var(--navy);color:var(--gold)}
.stab-gu-on{background:var(--red);color:var(--white)}
.stab-sb-on{background:var(--navy);color:var(--cyan)}
.price-preview{background:var(--navy);border-radius:6px;padding:16px 20px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between}
.pp-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.35);letter-spacing:1px;text-transform:uppercase}
.pp-amount{font-family:var(--display);font-size:32px;color:var(--gold);font-weight:900}
.pp-sub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);margin-top:2px}
.fg{margin-bottom:12px}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:var(--off);border:2px solid var(--border);color:var(--text);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;transition:border-color .2s;border-radius:4px}
.fg input:focus,.fg select:focus{border-color:var(--navy)}
.fg input::placeholder{color:#bbb}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn-full{width:100%;margin-top:8px;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}
.key-box{display:none;margin-top:20px;background:var(--navy);border-radius:6px;padding:22px}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:#00ff88;word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px}
.key-copy{margin-top:8px;background:transparent;border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.3);padding:6px 14px;font-family:var(--mono);font-size:9px;cursor:pointer;transition:all .2s;letter-spacing:1px;text-transform:uppercase;border-radius:4px}
.key-copy:hover{border-color:var(--gold);color:var(--gold)}
.usage-box{margin-top:12px;font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);padding:12px;border-radius:4px;line-height:1.9}
.usage-box em{color:#79b8ff;font-style:normal}
.msg-err{display:none;color:var(--red);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}
.msg-err.show{display:block}
.msg-ok{display:none;color:var(--green);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#f0fff8;border-radius:4px;border:1px solid #bbf7d0}
.msg-ok.show{display:block}
footer{background:var(--navy2);padding:52px 48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.5fr 1fr 1fr 1fr;gap:40px}
.foot-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;margin-bottom:4px}.foot-logo span{color:var(--gold)}
.foot-tag{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.15);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.foot-desc{font-size:12px;color:rgba(255,255,255,0.18);line-height:1.7}
.foot-col h4{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);text-transform:uppercase;margin-bottom:10px}
.foot-col a{display:block;color:rgba(255,255,255,0.18);text-decoration:none;font-size:12px;margin-bottom:6px;transition:color .2s}.foot-col a:hover{color:var(--white)}
.foot-bottom{max-width:1200px;margin:32px auto 0;padding-top:18px;border-top:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;font-size:10px;color:rgba(255,255,255,0.12);font-family:var(--mono)}
@media(max-width:900px){
nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
h1{font-size:clamp(36px,8vw,56px)}
.hero,.sec,.guardian-sec,.sonicboom-sec,.engine-sec,.compliance-sec,.fair-sec,.pricing-sec,.signup-sec,.products-sec{padding:52px 20px!important}
.two-col,.product-cards,.threat-grid,.engine-grid,.engine-compare,.comp-grid,.fair-grid,.sb-grid{grid-template-columns:1fr!important}
.stats-inner{grid-template-columns:repeat(3,1fr)!important}
.node-visual{grid-template-columns:repeat(2,1fr)!important}
.speed-compare{grid-template-columns:1fr auto 1fr}
footer{padding:40px 20px}.foot-inner{grid-template-columns:1fr}.foot-bottom{flex-direction:column;gap:6px}
.fg-row,.product-tabs,.calc-row,.calc-results{grid-template-columns:1fr!important}}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">Monop <span>Content</span></div>
  <div class="nav-links">
    <a href="#products">Products</a>
    <a href="#governance">AILeash</a>
    <a href="#guardian">Guardian</a>
    <a href="#sonicboom">SonicBoom</a>
    <a href="/scan">AI Act Scanner</a>
    <a href="/contact">Contact</a>
    <a href="#signup" class="nav-cta">Get Free API Key</a>
  </div>
</nav>

<div class="alert-bar"><strong>EU AI Act enforcement: August 2026.</strong> &nbsp;UK Online Safety Act: now in force.&nbsp; <strong>Free API. You set the margin. We take 50p.</strong></div>

<section class="hero">
<div class="hero-inner">
  <div><span class="kdot"></span><span class="ktext">Monop Content &middot; Blyth, UK &middot; Three Products &middot; Live Now</span></div>
  <h1>AI Compliance.<br><em>Child Safety.</em><br>Instant Speed.</h1>
  <p class="hero-sub">Three products. All free to integrate. <strong>Your users pay for protection.</strong> You set what they pay. We take 50p per device per month underneath. You keep everything above that. Forever.</p>
  <div class="hero-btns">
    <a href="#products" class="btn-gold">See All Three Products &darr;</a>
    <a href="#signup" class="btn-ghost">Get Free API Key</a>
    <a href="/scan" class="btn-ghost">Free AI Act Scanner</a>
  </div>
</div>
</section>

<div class="divider"></div>

<div class="stats-strip"><div class="stats-inner">
  <div class="stat"><div class="stat-n">3</div><div class="stat-l">Products</div></div>
  <div class="stat"><div class="stat-n">50p</div><div class="stat-l">We Take</div></div>
  <div class="stat"><div class="stat-n">&lt;12ms</div><div class="stat-l">Detection</div></div>
  <div class="stat"><div class="stat-n">SHA256</div><div class="stat-l">Audit Chain</div></div>
  <div class="stat"><div class="stat-n">24/7</div><div class="stat-l">Always On</div></div>
</div></div>

<section class="products-sec" id="products">
<div class="products-inner">
  <div class="slbl" style="color:var(--navy)">Three Products &mdash; One Model</div>
  <h2>Pick your product. <em>Set your price.</em></h2>
  <p class="sec-sub">All three integrate free. All three use the same model &mdash; you set what your users pay, we take 50p, you keep the rest.</p>

  <div class="product-cards">
    <div class="pc pc-al">
      <div class="pc-badge">AILeash &mdash; AI Governance</div>
      <h3>AILeash</h3>
      <p class="pc-desc">Enterprise AI governance. Nine-signal risk engine. SHA-256 audit chain. EU AI Act compliant from day one. Every AI decision scored, explained, and sealed to a court-admissible Merkle chain automatically.</p>
      <div class="pc-features">
        <div class="pcf">9-signal risk engine &mdash; ALLOW / CHALLENGE / BLOCK in &lt;12ms</div>
        <div class="pcf">SHA-256 Merkle audit chain &mdash; tamper-evident, court admissible</div>
        <div class="pcf">EU AI Act Art.9, 12, 13 satisfied from day one</div>
        <div class="pcf">Sovereign local engine &mdash; data never leaves your network</div>
        <div class="pcf">Asymmetric trust decay &mdash; trust harder to build than lose</div>
        <div class="pcf">100 free decisions &mdash; no card required to start</div>
      </div>
      <div class="pc-price"><sup>&pound;</sup>0.50</div>
      <div class="pc-price-label">we take per device per month &middot; you set user price</div>
      <a href="#signup" class="btn-block btn-block-al" onclick="setProduct('aileash')">Get Free AILeash API Key &rarr;</a>
      <p class="pc-note">Free trial &middot; No card &middot; Stripe billing after trial</p>
    </div>

    <div class="pc pc-gu">
      <div class="pc-badge">Guardian &mdash; Child Safety</div>
      <h3>AILeash Guardian</h3>
      <p class="pc-desc">Child safety layer. Grooming detection. CSAM mandatory block. Psychological manipulation signals. Online Safety Act 2023 and ICO Children's Code compliant. Parent Guardian App included &mdash; installs in 60 seconds.</p>
      <div class="pc-features">
        <div class="pcf">Real-time grooming pattern detection &mdash; blocked before child sees it</div>
        <div class="pcf">CSAM mandatory block regardless of score</div>
        <div class="pcf">Psychological manipulation &amp; love bombing detection</div>
        <div class="pcf">Guardian App for parents &mdash; push notification on block</div>
        <div class="pcf">Law enforcement evidence package &mdash; Action Fraud / CEOP ready</div>
        <div class="pcf">Online Safety Act 2023, ICO Children's Code, Ofcom compliant</div>
      </div>
      <div class="pc-price"><sup>&pound;</sup>0.50</div>
      <div class="pc-price-label">we take per device per month &middot; you set user price</div>
      <a href="#signup" class="btn-block btn-block-gu" onclick="setProduct('guardian')">Get Free Guardian API Key &rarr;</a>
      <p class="pc-note">Free trial &middot; No card &middot; Stripe billing after trial</p>
    </div>

    <div class="pc pc-sb">
      <div class="pc-badge">SonicBoom &mdash; Speed Plugin</div>
      <h3>SonicBoom</h3>
      <p class="pc-desc">One-line plugin for any existing cloud AI infrastructure. AWS, Azure, GCP, OpenAI &mdash; it does not matter. Your system stays exactly as it is. Every decision is significantly faster. Full audit chain added automatically.</p>
      <div class="pc-features">
        <div class="pcf">Sub-20ms decisions &mdash; significantly faster than standard cloud AI</div>
        <div class="pcf">Works with any cloud AI &mdash; AWS, Azure, GCP, OpenAI, any API</div>
        <div class="pcf">SHA-256 audit chain added automatically to every call</div>
        <div class="pcf">EU AI Act and Ofcom compliant from first integration</div>
        <div class="pcf">Nothing changes in your existing system &mdash; zero disruption</div>
        <div class="pcf">100 free decisions &mdash; no card required to start</div>
      </div>
      <div class="pc-price"><sup>&pound;</sup>0.50</div>
      <div class="pc-price-label">we take per device per month &middot; you set user price</div>
      <a href="/sonicboom" class="btn-block btn-block-sb">Learn More &amp; Get SonicBoom &rarr;</a>
      <p class="pc-note">Free plugin &middot; No card &middot; Stripe billing after trial</p>
    </div>
  </div>

  <div class="calc-wrap">
    <div class="calc-title">&#9998; Set your margin &mdash; see your profit instantly</div>
    <div class="calc-row">
      <div>
        <div class="calc-label">You charge per device per month</div>
        <div class="calc-input-row">
          <span class="pound">&pound;</span>
          <input class="calc-input" type="number" id="charge" value="1.99" min="0.51" step="0.01" oninput="calc()">
        </div>
      </div>
      <div>
        <div class="calc-label">Number of devices</div>
        <select class="calc-devices" id="devices" onchange="calc()">
          <option value="100">100 devices</option>
          <option value="500">500 devices</option>
          <option value="1000" selected>1,000 devices</option>
          <option value="5000">5,000 devices</option>
          <option value="10000">10,000 devices</option>
          <option value="50000">50,000 devices</option>
          <option value="100000">100,000 devices</option>
        </select>
      </div>
    </div>
    <div class="calc-results">
      <div class="cr"><div class="cr-label">User Pays</div><div class="cr-amount cr-user" id="r-user">&pound;1.99</div><div class="cr-sub">per device / month</div></div>
      <div class="cr"><div class="cr-label">You Keep</div><div class="cr-amount cr-you" id="r-you">&pound;1,490</div><div class="cr-sub">per month profit</div></div>
      <div class="cr"><div class="cr-label">We Take</div><div class="cr-amount cr-we" id="r-we">&pound;500</div><div class="cr-sub">per month (50p/device)</div></div>
    </div>
  </div>
</div>
</section>

<section class="sec" id="governance">
<div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">AILeash &mdash; AI Governance</div>
  <h2>Nine-Signal <em>Risk Engine</em></h2>
  <p class="sec-sub">Every AI action scored across nine concurrent signals. Explainable decisions. Tamper-evident audit chain. EU AI Act compliant from day one.</p>
  <div class="two-col"><div>
    <div class="feature-block"><div class="fb-icon">&#9889;</div><div class="fb-lbl">Signals 01&ndash;03</div><h3>Velocity Tracking</h3><p>Three concurrent time windows &mdash; 60 seconds, 5 minutes, 1 hour &mdash; detect spikes before they escalate. Catches burst attacks and patient low-and-slow adversaries that single windows miss.</p></div>
    <div class="feature-block"><div class="fb-icon">&#128274;</div><div class="fb-lbl">Signal 04</div><h3>Asymmetric Trust Decay</h3><p>Per-agent trust scores decay asymmetrically. BLOCK drops trust by 8%. CHALLENGE by 2%. ALLOW recovers by 1%. Trust is harder to build than to lose &mdash; exactly like real human trust. Nobody else builds it this way.</p></div>
    <div class="feature-block"><div class="fb-icon">&#127758;</div><div class="fb-lbl">Signals 08&ndash;09</div><h3>Geographic Risk</h3><p>Country-shift detection and jurisdiction-based risk weighting. Sudden location changes trigger automatic elevated scoring &mdash; a classic account takeover signal caught before damage is done.</p></div>
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
      <div class="df df-allow"><div class="df-v">ALLOW</div><div class="df-d">Safe. Proceeds. SHA-256 audit record created and sealed to chain.</div><div class="df-t">Score &lt; 0.35</div></div>
      <div class="df df-challenge"><div class="df-v">CHALLENGE</div><div class="df-d">Elevated risk. Paused. Human review required before proceeding.</div><div class="df-t">Score 0.35&ndash;0.70</div></div>
      <div class="df df-block"><div class="df-v">BLOCK</div><div class="df-d">High risk. Halted. Evidence preserved. Referral pathway activated.</div><div class="df-t">Score &gt; 0.70</div></div>
    </div>
  </div></div>
</div>
</section>

<section class="guardian-sec" id="guardian">
<div class="guardian-inner">
  <div class="slbl" style="color:rgba(255,255,255,0.25)">AILeash Guardian &mdash; Child Safety</div>
  <h2 style="color:var(--white)">Every threat. <em>Detected. Stopped.</em></h2>
  <p style="font-size:15px;color:rgba(255,255,255,0.35);max-width:620px;line-height:1.7;margin-bottom:36px">Same SHA-256 engine adapted for child safety. Block threshold drops from 0.70 to 0.60. Six harm categories. All detected in real time. Every intervention recorded as legal evidence admissible in UK courts. Parent Guardian App included &mdash; installs on any phone in 60 seconds, no app store required.</p>
  <div class="threat-grid">
    <div class="tc tc-r"><div class="tc-icon">&#127907;</div><div class="tc-lbl">Threat 01</div><h3>Grooming Detection</h3><p>Velocity, trust escalation, isolation attempts and geographic risk combined. Stopped before it starts. Evidence sealed automatically.</p><div class="tc-tags"><span class="ttag">velocity_spike</span><span class="ttag">trust_escalation</span><span class="ttag">isolation_attempt</span></div></div>
    <div class="tc tc-g"><div class="tc-icon">&#128172;</div><div class="tc-lbl">Threat 02</div><h3>Harmful Content</h3><p>Anomaly detection flags content deviating from age-appropriate norms. Block triggered before a child sees it. Age mismatch adds 12% to risk score.</p><div class="tc-tags"><span class="ttag">content_anomaly</span><span class="ttag">age_mismatch</span></div></div>
    <div class="tc tc-n"><div class="tc-icon">&#129302;</div><div class="tc-lbl">Threat 03</div><h3>Bot and Fake Accounts</h3><p>Automated accounts targeting children identified before first contact. Non-human actors exposed via device risk and behavioural anomaly signals.</p><div class="tc-tags"><span class="ttag">device_risk</span><span class="ttag">behaviour_anomaly</span></div></div>
    <div class="tc tc-gr"><div class="tc-icon">&#129504;</div><div class="tc-lbl">Threat 04</div><h3>Psychological Manipulation</h3><p>Detects coercive control, manufactured dependency and love bombing. Trust decay identifies dangerous relationship patterns early before escalation.</p><div class="tc-tags"><span class="ttag">trust_decay</span><span class="ttag">love_bombing</span><span class="ttag">sentiment_shift</span></div></div>
    <div class="tc tc-b"><div class="tc-icon">&#127758;</div><div class="tc-lbl">Threat 05</div><h3>Cross-Border Risk</h3><p>Flags contact from high-risk jurisdictions. Country shift detects when domestic contact suddenly operates from abroad &mdash; a classic predator evasion tactic.</p><div class="tc-tags"><span class="ttag">unsafe_country</span><span class="ttag">country_shift</span></div></div>
    <div class="tc tc-p"><div class="tc-icon">&#128247;</div><div class="tc-lbl">Threat 06</div><h3>CSAM &amp; Image Abuse</h3><p>Mandatory block on any CSAM detection regardless of overall risk score. Evidence automatically preserved and formatted for law enforcement referral.</p><div class="tc-tags"><span class="ttag">csam_mandatory_block</span><span class="ttag">evidence_preserved</span></div></div>
  </div>
  <div style="text-align:center;margin-top:32px">
    <a href="/guardian-app" class="btn-red" style="display:inline-block;text-decoration:none;font-size:16px;padding:16px 36px">Open Guardian App &rarr;</a>
    <p style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);margin-top:12px;letter-spacing:1px">Works on any phone &middot; No app store &middot; API key required &middot; Push notifications on block</p>
  </div>
</div>
</section>

<section class="sonicboom-sec" id="sonicboom">
<div class="sb-inner">
  <div class="slbl" style="color:rgba(0,212,255,0.4)">SonicBoom &mdash; Speed Plugin</div>
  <h2 style="color:var(--white)">Your AI is slow. <em>SonicBoom makes it faster.</em></h2>
  <p style="font-size:15px;color:rgba(255,255,255,0.4);max-width:620px;line-height:1.75;margin-bottom:40px">One line of code around your existing AI calls. Nothing changes in your system. Every decision is significantly faster. Full SHA-256 audit chain added automatically. EU AI Act and Ofcom compliant from the moment you integrate. Works with any cloud infrastructure.</p>
  <div class="speed-compare">
    <div class="sc-before"><div class="sc-label">Typical Cloud AI</div><div class="sc-speed">200+</div><div class="sc-unit">milliseconds</div></div>
    <div class="sc-arrow">&#8594;</div>
    <div class="sc-after"><div class="sc-label">After SonicBoom</div><div class="sc-speed"><div class="sc-after"><div class="sc-label">After SonicBoom</div><div class="sc-speed">6</div>lt;20</div><div class="sc-unit">milliseconds</div></div>
  </div>
  <div class="sb-grid" style="margin-top:40px">
    <div class="sbg"><div class="sbg-icon">&#9889;</div><h3>One Line to Integrate</h3><p>Wrap your existing AI call with one line of code. Your system stays exactly as it is. SonicBoom sits in front of it and makes it faster.</p><div class="sbg-stat">1</div><div class="sbg-stat-label">line of code</div></div>
    <div class="sbg"><div class="sbg-icon">&#128274;</div><h3>Audit Chain Automatic</h3><p>Every call through SonicBoom gets a SHA-256 audit record sealed to a Merkle chain automatically. No extra work. Ofcom and EU AI Act compliant instantly.</p><div class="sbg-stat">100%</div><div class="sbg-stat-label">decisions audited</div></div>
    <div class="sbg"><div class="sbg-icon">&#127760;</div><h3>Any Cloud Infrastructure</h3><p>AWS, Azure, Google Cloud, OpenAI, Anthropic, custom APIs &mdash; it does not matter. SonicBoom wraps any AI call and makes it faster and compliant.</p><div class="sbg-stat">Any</div><div class="sbg-stat-label">cloud provider</div></div>
  </div>
  <div style="text-align:center;margin-top:32px">
    <a href="/sonicboom" class="btn-cyan" style="display:inline-block;text-decoration:none;font-size:16px;padding:16px 36px">Learn More About SonicBoom &rarr;</a>
  </div>
</div>
</section>

<section class="engine-sec" id="engine">
<div class="engine-inner">
  <div style="text-align:center;margin-bottom:56px">
    <div class="slbl" style="color:rgba(255,255,255,0.3)">The Architecture</div>
    <h2 style="color:var(--white)">You don&rsquo;t connect to us.<br><em>You become us.</em></h2>
    <p style="font-size:17px;color:rgba(255,255,255,0.45);max-width:640px;margin:0 auto;line-height:1.75">Every customer gets their own sovereign governance engine. It runs on your hardware. Your data never leaves your network. No central server. No single point of failure. Just your engine, your chain, your compliance &mdash; forever.</p>
  </div>
  <div class="engine-grid">
    <div class="eg"><div class="eg-num">What you get</div><h3>Your Own Engine</h3><p>When you sign up you download a single Python file. Nine-signal risk scoring, SHA-256 Merkle audit chain, EU AI Act compliance mapping &mdash; all running locally on your hardware.</p></div>
    <div class="eg"><div class="eg-num">Your data</div><h3>Stays With You</h3><p>Every audit record, every decision, every piece of evidence is sealed to a cryptographic chain on your machine. Not our cloud. Yours. We cannot read it, alter it, or lose it.</p></div>
    <div class="eg"><div class="eg-num">How it scales</div><h3>Replicates Itself</h3><p>Need to protect 2,000 devices across 50 locations? The engine clones itself to each node with a single cryptographic handshake. No deployment team. Automatic.</p></div>
    <div class="eg"><div class="eg-num">Your cost</div><h3>50p Per Device</h3><p>Because we have near-zero infrastructure costs at your scale, we pass that directly to you. Enterprise vendors charge &pound;50,000 a year. We charge 50p because the architecture makes it possible.</p></div>
    <div class="eg"><div class="eg-num">The audit chain</div><h3>Court-Admissible</h3><p>Every decision cryptographically sealed &mdash; timestamp, decision, reasons, hash of previous block. Tamper with any record and every subsequent block breaks. Admissible in UK courts.</p></div>
    <div class="eg"><div class="eg-num">Cancel anytime</div><h3>Your Chain Stays</h3><p>Cancel your subscription and the engine locks. But every audit record &mdash; years of compliance history &mdash; stays with you permanently. Your regulator can still verify it.</p></div>
  </div>
  <div class="engine-compare">
    <div class="ec ec-old"><div class="ec-label">Every other vendor</div><h3>Centralised. Expensive. Fragile.</h3><div class="ec-list">
      <div class="ec-item">Your data sent to their cloud on every decision</div>
      <div class="ec-item">Single point of failure &mdash; their outage is your breach</div>
      <div class="ec-item">&pound;50,000+ per year enterprise contracts</div>
      <div class="ec-item">Months to deploy &mdash; integration teams required</div>
      <div class="ec-item">You depend on them forever &mdash; lock-in by design</div>
      <div class="ec-item">Audit chain they control &mdash; not you</div>
    </div></div>
    <div class="ec ec-new"><div class="ec-label">AILeash / SonicBoom</div><h3>Sovereign. Affordable. Unstoppable.</h3><div class="ec-list">
      <div class="ec-item">Your data never leaves your hardware</div>
      <div class="ec-item">No central server &mdash; runs offline if needed</div>
      <div class="ec-item">50p per device per month &mdash; no contracts</div>
      <div class="ec-item">60 seconds to integrate &mdash; one file or one line</div>
      <div class="ec-item">You own the engine &mdash; we cannot take it away</div>
      <div class="ec-item">Your audit chain &mdash; cryptographically yours forever</div>
    </div></div>
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
    <div class="ed-btns"><a href="/download/engine" class="btn-gold">Download engine.py &rarr;</a><a href="#signup" class="btn-ghost">Get API Key First</a></div>
  </div>
</div>
</section>

<section class="compliance-sec" id="compliance">
<div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">Legal Compliance</div>
  <h2>Built for the law. <em>As it stands today.</em></h2>
  <p class="sec-sub">All three products meet every current and upcoming UK and EU legal obligation. Deploy and tick every compliance box immediately.</p>
  <div class="comp-grid">
    <div class="comp-card"><div class="comp-act">EU AI Act 2024/1689</div><h3>High-Risk AI Compliance</h3><p>Enforced August 2026. AILeash and SonicBoom satisfy Art.9 risk assessment, Art.12 audit chain, Art.13 explainability from day one.</p><div class="checks"><div class="chk">Article 9 &mdash; Continuous risk assessment</div><div class="chk">Article 12 &mdash; Tamper-evident audit chain</div><div class="chk">Article 13 &mdash; Explainable decisions</div><div class="chk">GDPR Art.22 &mdash; Human oversight pathway</div></div></div>
    <div class="comp-card"><div class="comp-act">Online Safety Act 2023 &mdash; UK</div><h3>Duty of Care to Children</h3><p>Platforms must assess risk and demonstrate compliance to Ofcom. Guardian provides the complete technical infrastructure. Ofcom audit trail ready on day one.</p><div class="checks"><div class="chk">Risk assessment infrastructure</div><div class="chk">Real-time content moderation</div><div class="chk">Age-appropriate design</div><div class="chk">Ofcom-ready audit trails</div></div></div>
    <div class="comp-card"><div class="comp-act">ICO Children&rsquo;s Code &mdash; UK</div><h3>Age Appropriate Design</h3><p>Guardian ensures children are never subject to solely automated high-risk decisions without human oversight. Best interests of the child built in by design.</p><div class="checks"><div class="chk">Best interests of the child by default</div><div class="chk">Data minimisation for child users</div><div class="chk">Profiling restrictions enforced</div><div class="chk">Parental controls pathway</div></div></div>
    <div class="comp-card"><div class="comp-act">Digital Services Act &mdash; EU 2022/2065</div><h3>Platform Accountability</h3><p>Continuous automated risk assessment with full audit documentation for regulatory submission. Systemic risk assessment infrastructure built in.</p><div class="checks"><div class="chk">Systemic risk assessment</div><div class="chk">Algorithmic transparency reports</div><div class="chk">Minor protection evidence packages</div><div class="chk">Regulator-ready submissions</div></div></div>
  </div>
</div>
</section>

<section class="fair-sec">
<div class="sec-inner">
  <div class="slbl" style="color:var(--navy)">Fair Usage</div>
  <h2>Always fast. <em>Always fair.</em></h2>
  <p class="sec-sub">Per-key rate limits keep the platform fast for everyone. Global throttling kicks in automatically if load spikes.</p>
  <div class="fair-grid">
    <div class="fair-card"><h3>Per-Key Rate Limits</h3><p>Every API key governed by fair usage limits. Bursting above these triggers graceful throttling. Your audit chain is always safe.</p><div class="fair-limit">60 requests / minute<br>1,000 requests / hour</div></div>
    <div class="fair-card"><h3>Global Throttle</h3><p>When global request rate exceeds threshold, non-critical requests are throttled. Govern calls always pass. Load events logged to chain.</p><div class="fair-limit">Threshold: 200 req / sec<br>Govern always prioritised</div></div>
    <div class="fair-card"><h3>Audit Chain Integrity</h3><p>Every load event logged with timestamp. Full transparency. Verify your entire chain at any time via the public endpoint.</p><div class="fair-limit">All events logged<br>sebbi.pro/api/verify-chain</div></div>
  </div>
</div>
</section>

<section class="signup-sec" id="signup">
<div class="signup-inner">
  <div class="slbl" style="color:var(--navy)">Get Started</div>
  <h2>Free API key. <em>Right now.</em></h2>
  <p style="font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:24px">Pick your product. Name and email. API key delivered instantly. 100 free decisions. No card required to start.</p>
  <div class="product-tabs">
    <button class="stab stab-al-on" id="tab-al" onclick="setProduct('aileash')">AILeash</button>
    <button class="stab" id="tab-gu" onclick="setProduct('guardian')">Guardian</button>
    <button class="stab" id="tab-sb" onclick="setProduct('sonicboom')">SonicBoom</button>
  </div>
  <div class="fg-row">
    <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
    <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
  </div>
  <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
  <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
  <div class="fg"><label>Platform / Company Name</label><input type="text" id="org" placeholder="e.g. Roblox / GameZone / My Platform"></div>
  <div class="fg"><label>Estimated Devices</label>
    <select id="dv">
      <option value="100">Under 100</option>
      <option value="500">100 to 500</option>
      <option value="1000">500 to 1,000</option>
      <option value="5000">1,000 to 5,000</option>
      <option value="10000">5,000 to 10,000</option>
      <option value="50000">10,000+</option>
    </select>
  </div>
  <div class="price-preview">
    <div><div class="pp-label">Monthly Total</div><div class="pp-sub" id="pp-sub">Enter device count above</div></div>
    <div class="pp-amount" id="pp-amt">&pound;0.00</div>
  </div>
  <button class="btn-full" id="go-btn" style="background:var(--gold);color:var(--navy)" onclick="doSignup()">Get Free AILeash API Key &rarr;</button>
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
</div>
</section>

<footer>
<div class="foot-inner">
  <div>
    <div class="foot-logo">Monop <span>Content</span></div>
    <div class="foot-tag">Blyth, Northumberland, UK</div>
    <p class="foot-desc">Three AI compliance and safety products. Free to integrate. You set the margin. We take 50p per device per month.</p>
  </div>
  <div class="foot-col"><h4>Products</h4>
    <a href="#governance">AILeash</a>
    <a href="#guardian">Guardian</a>
    <a href="/sonicboom">SonicBoom</a>
    <a href="/reseller">Partner Programme</a>
    <a href="/scan">AI Act Scanner</a>
  </div>
  <div class="foot-col"><h4>Tools</h4>
    <a href="/guardian-app">Guardian App</a>
    <a href="/report-threat">Report a Threat</a>
    <a href="/api/health">API Health</a>
    <a href="/api/verify-chain">Verify Chain</a>
    <a href="/download/engine">Download Engine</a>
  </div>
  <div class="foot-col"><h4>Contact</h4>
    <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a>
    <a href="tel:07908269428">07908 269428</a>
    <a href="/contact">Send a Message</a>
    <a href="#signup">Get API Key</a>
  </div>
</div>
<div class="foot-bottom">
  <span>&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK &middot; v5.0.0</span>
  <span>EU AI Act &middot; Online Safety Act &middot; ICO Children&rsquo;s Code &middot; DSA</span>
</div>
</footer>

<script>
var AP='aileash';
function setProduct(p){
  AP=p;
  document.getElementById('tab-al').className='stab'+(p==='aileash'?' stab-al-on':'');
  document.getElementById('tab-gu').className='stab'+(p==='guardian'?' stab-gu-on':'');
  document.getElementById('tab-sb').className='stab'+(p==='sonicboom'?' stab-sb-on':'');
  var btn=document.getElementById('go-btn');
  if(p==='aileash'){btn.textContent='Get Free AILeash API Key \u2192';btn.style.background='var(--gold)';btn.style.color='var(--navy)';}
  else if(p==='guardian'){btn.textContent='Get Free Guardian API Key \u2192';btn.style.background='var(--red)';btn.style.color='var(--white)';}
  else{btn.textContent='Get Free SonicBoom Plugin \u2192';btn.style.background='var(--cyan)';btn.style.color='var(--navy)';}
}
function calc(){
  var n=parseInt(document.getElementById('dv').value)||0;
  document.getElementById('pp-amt').textContent='\u00a3'+(n*0.5).toFixed(2);
  document.getElementById('pp-sub').textContent=n>0?(n+' device'+(n===1?'':'s')+' \u00d7 50p = \u00a3'+(n*0.5).toFixed(2)+'/mo'):'Enter device count above';
}
function calcMargin(){
  var charge=parseFloat(document.getElementById('charge').value)||0;
  var devices=parseInt(document.getElementById('devices').value)||0;
  var youKeep=Math.max(0,charge-0.50)*devices;
  var weGet=0.50*devices;
  document.getElementById('r-user').textContent='\u00a3'+charge.toFixed(2);
  document.getElementById('r-you').textContent='\u00a3'+youKeep.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('r-we').textContent='\u00a3'+weGet.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
}
calcMargin();
async function doSignup(){
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var org=document.getElementById('org').value.trim();
  var dv=parseInt(document.getElementById('dv').value)||1;
  var err=document.getElementById('msg-err');
  var ok=document.getElementById('msg-ok');
  var kb=document.getElementById('key-box');
  var btn=document.getElementById('go-btn');
  err.classList.remove('show');ok.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company name.';err.classList.add('show');return;}
  var origText=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:AP,product:AP==='guardian'?'guardian':'aileash',devices:dv})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      document.getElementById('key-prev').textContent=d.api_key.slice(0,24)+'...';
      kb.classList.add('show');
      ok.textContent='Key created. 100 free decisions included. Setting up billing\u2026';ok.classList.add('show');
      btn.textContent='Key Created \u2713';
      setTimeout(function(){
        fetch('/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({email:em,product:AP==='guardian'?'guardian':'aileash',devices:dv})
        }).then(function(r2){return r2.json();}).then(function(d2){
          if(d2.checkout_url){window.location.href=d2.checkout_url;}
          else{ok.textContent='Key ready. Contact justin@monopcontent.com for billing.';}
        }).catch(function(){ok.textContent='Key ready. Contact justin@monopcontent.com for billing.';});
      },1500);
    }else{
      err.textContent=d.error||'Something went wrong. Email justin@monopcontent.com directly.';
      err.classList.add('show');btn.textContent=origText;btn.disabled=false;
    }
  }catch(e){
    err.textContent='Cannot reach server. Email justin@monopcontent.com directly.';
    err.classList.add('show');btn.textContent=origText;btn.disabled=false;
  }
}
function copyKey(){
  navigator.clipboard.writeText(document.getElementById('key-val').textContent).then(function(){
    var b=document.querySelector('.key-copy');b.textContent='Copied \u2713';
    setTimeout(function(){b.textContent='Copy Key';},2000);
  });
}
</script>
</body>
</html>"""# HTTP SERVER
# ============================================================================
class ThreadedServer(ThreadingMixIn,HTTPServer):
    allow_reuse_address=True
    daemon_threads=True

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path
        if path.endswith("/") and path!="/":path=path.rstrip("/")
        track_request()

        if path=="/":
            send_html(self,HOMEPAGE)
        elif path=="/scan":
            c=load_file("scan.html")
            send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/contact":
            c=load_file("contact.html")
            send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-app":
            c=load_file("guardian-app.html")
            send_html(self,c) if c else send_json(self,{"error":"guardian-app.html not in repo"},404)
        elif path=="/sonicboom":
            c=load_file("sonicboom.html")
            send_html(self,c) if c else send_json(self,{"error":"sonicboom.html not in repo"},404)
        elif path=="/reseller" or path=="/partners":
            c=load_file("reseller.html")
            send_html(self,c) if c else send_json(self,{"error":"reseller.html not in repo"},404)
        elif path=="/report-threat":
            c=load_file("report-threat.html")
            send_html(self,c) if c else send_json(self,{"error":"report-threat.html not in repo"},404)
        elif path=="/api/health":
            send_json(self,{"status":"ok","version":VERSION,"rps":get_rps()})
        elif path=="/api/verify-chain":
            send_json(self,verify_chain())
        elif path=="/api/stats":
            with _db_lock:
                keys=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                audits=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_json(self,{"api_keys":keys,"audit_blocks":audits,"rps":get_rps(),"version":VERSION})
        elif path=="/api/validate-engine":
            send_json(self,{"error":"method_not_allowed"},405)
        elif path=="/download/engine":
            api_key=get_bearer(self)
            ki=get_key(api_key) if api_key else None
            if not ki:
                send_html(self,"<html><body style='font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh'><div style='text-align:center;padding:40px'><h1 style='color:#c9a84c;margin-bottom:16px'>Engine Download</h1><p style='color:rgba(255,255,255,0.5);margin-bottom:24px'>Valid API key required.<br>Get yours at sebbi.pro</p><a href='https://sebbi.pro/#signup' style='background:#c9a84c;color:#0a0f1e;padding:14px 28px;text-decoration:none;border-radius:4px;font-weight:700'>Get API Key</a></div></body></html>",401)
                return
            try:
                with open("engine.py","rb") as f:body=f.read()
                self.send_response(200)
                self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition",'attachment; filename="engine.py"')
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except:send_json(self,{"error":"engine_not_found"},404)
        elif path=="/robots.txt":
            send_html(self,"User-agent: *\nAllow: /\nSitemap: https://sebbi.pro/sitemap.xml\n")
        elif path=="/sitemap.xml":
            c=load_file("sitemap.xml")
            if c:
                body=c.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type","application/xml")
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:send_json(self,{"error":"not found"},404)
        else:
            send_json(self,{"error":"not_found"},404)

    def do_POST(self):
        path=urlparse(self.path).path.rstrip("/")
        data=read_body(self)
        track_request()
        if is_over() and path not in("/api/govern","/govern"):
            send_json(self,{"error":"server_busy"},503);return

        if path in("/api/govern","/govern"):
            api_key=get_bearer(self)
            try:
                result,status=govern(data,api_key or None)
                send_json(self,result,status)
            except ValueError as e:send_json(self,{"error":str(e)},400)
            except Exception as e:send_json(self,{"error":"internal","detail":str(e)},500)

        elif path in("/signup","/api/keys"):
            email=str(data.get("email","")).strip().lower()
            phone=str(data.get("phone","")).strip()
            name=str(data.get("name","")).strip()
            org=str(data.get("org","")).strip()
            org_type=str(data.get("org_type","")).strip()
            product=str(data.get("product","aileash")).strip().lower()
            devices=max(1,int(data.get("devices",1)))
            if product not in("aileash","guardian"):product="aileash"
            key,err=create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email."}
                send_json(self,{"error":msgs.get(err,err)},400);return
            monthly=round(devices*0.50,2)
            threading.Thread(target=welcome_email,args=(name,email,product,key,devices,monthly),daemon=True).start()
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"quota":FREE_QUOTA,"endpoint":f"{HOST}/api/govern","message":f"100 free decisions. After trial: £{monthly}/month via Stripe."})

        elif path=="/contact":
            name=str(data.get("name","")).strip()
            email=str(data.get("email","")).strip().lower()
            phone=str(data.get("phone","")).strip()
            org=str(data.get("org","")).strip()
            msg=str(data.get("message","")).strip()
            if not email or "@" not in email:send_json(self,{"error":"invalid_email"},400);return
            if not msg:send_json(self,{"error":"no_message"},400);return
            with _db_lock:
                _conn.execute("INSERT INTO contact_log(ts,name,email,phone,org,message) VALUES(?,?,?,?,?,?)",(time.time(),name,email,phone,org,msg))
                _conn.commit()
            threading.Thread(target=contact_email,args=(name,email,phone,org,msg),daemon=True).start()
            send_json(self,{"ok":True})

        elif path=="/api/validate-engine":
            api_key=get_bearer(self)
            if not api_key:send_json(self,{"valid":False,"error":"no_key"},401);return
            ki=get_key(api_key)
            if not ki:send_json(self,{"valid":False,"error":"invalid_api_key"},401);return
            email,used,active,is_paid,quota,plan,product=ki
            if not active:send_json(self,{"valid":False,"error":"account_inactive"},403);return
            if not is_paid and used>=quota:send_json(self,{"valid":False,"error":"quota_exceeded","message":"Renew at https://sebbi.pro/#pricing"},402);return
            with _db_lock:devices=_conn.execute("SELECT devices FROM api_keys WHERE key=?",(api_key,)).fetchone()
            send_json(self,{"valid":True,"plan":plan,"product":product,"devices":devices[0] if devices else 1,"email":email})

        elif path=="/stripe-webhook":
            length=int(self.headers.get("Content-Length",0))
            raw=self.rfile.read(length) if length else b""
            try:
                event=json.loads(raw)
                etype=event.get("type","")
                obj=event.get("data",{}).get("object",{})
                if etype in("checkout.session.completed","invoice.paid"):
                    email=obj.get("customer_email") or obj.get("customer_details",{}).get("email","")
                    if email:
                        email=email.strip().lower()
                        with _db_lock:_conn.execute("UPDATE api_keys SET is_paid=1,plan_type='paid' WHERE email=?",(email,));_conn.commit()
                        print(f"PAID:{email}",flush=True)
                elif etype in("customer.subscription.deleted","invoice.payment_failed"):
                    email=obj.get("customer_email","")
                    if email:
                        email=email.strip().lower()
                        with _db_lock:_conn.execute("UPDATE api_keys SET is_paid=0,plan_type='free' WHERE email=?",(email,));_conn.commit()
                        print(f"UNPAID:{email}",flush=True)
                send_json(self,{"ok":True})
            except Exception as e:print(f"Webhook:{e}",flush=True);send_json(self,{"ok":True})

        elif path=="/create-checkout":
            email=str(data.get("email","")).strip().lower()
            product=str(data.get("product","aileash")).strip().lower()
            devices=max(1,int(data.get("devices",1)))
            if not email or "@" not in email:send_json(self,{"error":"invalid_email"},400);return
            if not STRIPE_SECRET:send_json(self,{"error":"stripe_not_configured"},503);return
            pid=STRIPE_PRICE_GU if product=="guardian" else STRIPE_PRICE_AL
            if not pid:setup_stripe();pid=STRIPE_PRICE_GU if product=="guardian" else STRIPE_PRICE_AL
            if not pid:send_json(self,{"error":"stripe_setup_failed"},503);return
            session=stripe_call("POST","/checkout/sessions",{"mode":"subscription","customer_email":email,"success_url":f"{HOST}/?success=true","cancel_url":f"{HOST}/?cancel=true","line_items[0][price]":pid,"line_items[0][quantity]":str(devices)})
            if not session or "url" not in session:send_json(self,{"error":"checkout_failed"},500);return
            send_json(self,{"checkout_url":session["url"]})

        elif path=="/report-threat":
            ref="AIDX-"+hashlib.sha256(json.dumps(data).encode()).hexdigest()[:12].upper()
            with _db_lock:
                _conn.execute("INSERT INTO contact_log(ts,name,email,phone,org,message) VALUES(?,?,?,?,?,?)",
                    (time.time(),data.get("reporter_name",""),data.get("reporter_email",""),"","THREAT_REPORT",json.dumps(data)))
                _conn.commit()
            html=f"<html><body style='font-family:Arial,sans-serif;padding:20px'><h2 style='color:#cc0000'>THREAT REPORT: {ref}</h2><pre style='background:#f5f5f5;padding:16px;border-radius:4px'>{json.dumps(data,indent=2)}</pre></body></html>"
            threading.Thread(target=send_email,args=(OWNER_EMAIL,OWNER_NAME,f"THREAT REPORT: {ref}",html),daemon=True).start()
            send_json(self,{"ok":True,"reference":ref})

        else:
            send_json(self,{"error":"not_found"},404)

if __name__=="__main__":
    print(f"AILeash Platform v{VERSION} starting on :{PORT}",flush=True)
    setup_stripe()
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print("Ready.",flush=True)
    server.serve_forever()
