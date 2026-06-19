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
<meta name="description" content="Three AI compliance and safety products. Free API. You set the margin. We take 50p per device.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--gold:#c9a84c;--red:#cc0000;--green:#00875a;--cyan:#00d4ff;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--navy);color:var(--white);font-family:var(--sans);overflow-x:hidden}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(10,15,30,0.97);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.05)}
.nav-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.4);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 20px;font-weight:700!important;border-radius:4px}
.hero{padding:120px 48px 80px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.05)}
.hero-inner{max-width:900px;margin:0 auto}
.mono-badge{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.25);letter-spacing:3px;text-transform:uppercase;margin-bottom:16px}
.hero h1{font-family:var(--display);font-size:clamp(44px,5.5vw,72px);color:var(--white);font-weight:900;line-height:1.05;margin-bottom:20px}
.hero h1 em{color:var(--gold);font-style:normal}
.hero p{font-size:18px;color:rgba(255,255,255,0.45);line-height:1.75;max-width:640px;margin:0 auto 48px}
.hero p strong{color:var(--white)}
.alert-strip{display:inline-block;background:rgba(204,0,0,0.15);border:1px solid rgba(204,0,0,0.3);color:#ff6b6b;font-family:var(--mono);font-size:11px;letter-spacing:1px;text-transform:uppercase;padding:8px 20px;border-radius:4px;margin-bottom:28px}
.products{padding:80px 48px}
.products-inner{max-width:1100px;margin:0 auto}
.sec-label{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,0.25);margin-bottom:16px;text-align:center}
.sec-title{font-family:var(--display);font-size:clamp(32px,3.5vw,48px);font-weight:900;text-align:center;margin-bottom:12px;color:var(--white)}
.sec-title em{color:var(--gold);font-style:normal}
.sec-sub{font-size:15px;color:rgba(255,255,255,0.35);text-align:center;max-width:580px;margin:0 auto 56px;line-height:1.7}
.product-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.04)}
.pc{background:var(--navy);padding:40px 32px;position:relative;overflow:hidden;transition:background .2s}
.pc:hover{background:#0d1425}
.pc::before{content:'';position:absolute;top:0;left:0;right:0;height:4px}
.pc-al::before{background:var(--gold)}
.pc-gu::before{background:var(--red)}
.pc-sb::before{background:var(--cyan)}
.pc-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:16px;display:inline-block;padding:4px 10px;border-radius:2px}
.pc-al .pc-badge{color:var(--gold);background:rgba(201,168,76,0.1);border:1px solid rgba(201,168,76,0.2)}
.pc-gu .pc-badge{color:#ff6b6b;background:rgba(204,0,0,0.1);border:1px solid rgba(204,0,0,0.2)}
.pc-sb .pc-badge{color:var(--cyan);background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2)}
.pc h2{font-family:var(--display);font-size:28px;color:var(--white);font-weight:900;margin-bottom:12px;line-height:1.1}
.pc-desc{font-size:14px;color:rgba(255,255,255,0.35);line-height:1.7;margin-bottom:24px}
.pc-features{display:flex;flex-direction:column;gap:8px;margin-bottom:28px}
.pcf{display:flex;align-items:center;gap:8px;font-size:13px;color:rgba(255,255,255,0.45);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.pcf::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;flex-shrink:0}
.pc-al .pcf::before{color:var(--gold)}
.pc-gu .pcf::before{color:#ff6b6b}
.pc-sb .pcf::before{color:var(--cyan)}
.pc-price{font-family:var(--display);font-size:44px;font-weight:900;line-height:1;margin-bottom:4px}
.pc-al .pc-price{color:var(--gold)}
.pc-gu .pc-price{color:#ff6b6b}
.pc-sb .pc-price{color:var(--cyan)}
.pc-price-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);margin-bottom:24px;letter-spacing:1px}
.btn{display:block;text-align:center;padding:14px 24px;border-radius:6px;font-family:var(--sans);font-weight:700;font-size:14px;text-decoration:none;transition:all .2s;border:none;cursor:pointer;width:100%}
.btn-al{background:var(--gold);color:var(--navy)}.btn-al:hover{background:#e8c96a}
.btn-gu{background:var(--red);color:var(--white)}.btn-gu:hover{background:#aa0000}
.btn-sb{background:var(--cyan);color:var(--navy)}.btn-sb:hover{background:#33ddff}
.model-sec{padding:80px 48px;border-top:1px solid rgba(255,255,255,0.05)}
.model-inner{max-width:1100px;margin:0 auto}
.model-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-top:40px}
.mg{background:var(--navy);padding:32px;text-align:center}
.mg-icon{font-size:40px;margin-bottom:16px}
.mg-n{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.mg h3{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900;margin-bottom:8px}
.mg p{font-size:13px;color:rgba(255,255,255,0.35);line-height:1.65;margin-bottom:16px}
.mg-price{font-family:var(--display);font-size:36px;font-weight:900;color:var(--gold)}
.mg-price-sub{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);margin-top:4px}
.calc-sec{padding:80px 48px;border-top:1px solid rgba(255,255,255,0.05)}
.calc-inner{max-width:700px;margin:0 auto}
.calc-wrap{background:rgba(201,168,76,0.05);border:2px solid rgba(201,168,76,0.2);border-radius:12px;padding:40px;margin-top:40px}
.calc-row{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px}
.calc-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.calc-input-row{display:flex;align-items:center;gap:8px}
.pound{font-family:var(--display);font-size:28px;color:var(--gold);font-weight:900}
.calc-input{background:rgba(255,255,255,0.06);border:2px solid rgba(201,168,76,0.2);color:var(--white);padding:12px 16px;font-size:20px;font-family:var(--display);font-weight:700;width:120px;border-radius:6px;outline:none;text-align:center}
.calc-input:focus{border-color:var(--gold)}
.calc-devices{background:rgba(255,255,255,0.06);border:2px solid rgba(255,255,255,0.08);color:var(--white);padding:12px 16px;font-size:15px;font-family:var(--sans);width:100%;border-radius:6px;outline:none}
.calc-devices option{background:var(--navy)}
.calc-results{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.04);border-radius:8px;overflow:hidden}
.cr{background:rgba(255,255,255,0.03);padding:20px;text-align:center}
.cr-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.cr-amount{font-family:var(--display);font-size:28px;font-weight:900;line-height:1}
.cr-you{color:#00ff88}.cr-we{color:rgba(255,255,255,0.2)}.cr-user{color:var(--gold)}
.cr-sub{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);margin-top:4px}
.signup-sec{padding:80px 48px;border-top:1px solid rgba(255,255,255,0.05)}
.signup-inner{max-width:580px;margin:0 auto}
.form-wrap{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:32px;margin-top:32px}
.fg{margin-bottom:14px}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:var(--white);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus{border-color:var(--gold)}
.fg input::placeholder{color:rgba(255,255,255,0.2)}
.fg select option{background:var(--navy)}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.product-tabs{display:grid;grid-template-columns:repeat(3,1fr);gap:0;border:1px solid rgba(255,255,255,0.1);border-radius:6px;overflow:hidden;margin-bottom:20px}
.ptab{padding:12px;text-align:center;cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;font-weight:600;transition:all .2s;background:rgba(255,255,255,0.02);color:rgba(255,255,255,0.3);border:none;outline:none}
.ptab-al-on{background:var(--navy);color:var(--gold);border-bottom:2px solid var(--gold)}
.ptab-gu-on{background:rgba(204,0,0,0.2);color:#ff6b6b;border-bottom:2px solid var(--red)}
.ptab-sb-on{background:rgba(0,212,255,0.1);color:var(--cyan);border-bottom:2px solid var(--cyan)}
.btn-full{width:100%;padding:16px;font-family:var(--sans);font-weight:700;font-size:16px;cursor:pointer;border-radius:4px;border:none;transition:all .2s;margin-top:8px}
.btn-full-al{background:var(--gold);color:var(--navy)}
.btn-full-gu{background:var(--red);color:var(--white)}
.btn-full-sb{background:var(--cyan);color:var(--navy)}
.msg{display:none;padding:12px;border-radius:4px;font-family:var(--mono);font-size:11px;margin-top:12px;line-height:1.6}
.msg.show{display:block}
.msg-ok{background:rgba(0,135,90,0.15);border:1px solid rgba(0,135,90,0.3);color:#00ff88}
.msg-err{background:rgba(204,0,0,0.15);border:1px solid rgba(204,0,0,0.3);color:#ff6b6b}
.key-box{display:none;background:rgba(0,0,0,0.4);border:1px solid rgba(201,168,76,0.2);border-radius:8px;padding:24px;margin-top:16px}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.key-val{font-family:var(--mono);font-size:12px;color:#00ff88;word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px}
.key-next{margin-top:12px;font-size:13px;color:rgba(255,255,255,0.4);line-height:1.75}
footer{padding:40px 48px;border-top:1px solid rgba(255,255,255,0.05);text-align:center}
.foot-links{display:flex;gap:24px;justify-content:center;flex-wrap:wrap;margin-bottom:16px}
.foot-links a{color:rgba(255,255,255,0.25);text-decoration:none;font-size:13px;transition:color .2s}.foot-links a:hover{color:var(--white)}
.foot-copy{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.12)}
@media(max-width:900px){
nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
.hero,.products,.model-sec,.calc-sec,.signup-sec{padding:52px 20px}
.product-cards,.model-grid,.calc-row,.calc-results{grid-template-columns:1fr!important}
.fg-row,.product-tabs{grid-template-columns:1fr!important}}
</style>
</head>
<body>
<nav>
  <div class="nav-logo">Monop <span>Content</span></div>
  <div class="nav-links">
    <a href="#products">Products</a>
    <a href="#model">The Model</a>
    <a href="#margin">Your Margin</a>
    <a href="/scan">AI Act Scanner</a>
    <a href="/contact">Contact</a>
    <a href="#signup" class="nav-cta">Get Free API Key</a>
  </div>
</nav>

<section class="hero">
  <div class="hero-inner">
    <div class="alert-strip">EU AI Act Enforcement: August 2026 &mdash; Ofcom: Now In Force</div>
    <div class="mono-badge">Monop Content &middot; Blyth, UK &middot; Three Products &middot; One Model</div>
    <h1>Free API.<br><em>You set the margin.</em><br>We take 50p.</h1>
    <p>Three products. All free to integrate. <strong>Your users pay for protection.</strong> You set what they pay. We take 50p per device per month. You keep everything above that. Forever.</p>
  </div>
</section>

<section class="products" id="products">
  <div class="products-inner">
    <div class="sec-label">Three Products</div>
    <div class="sec-title">Pick your <em>product.</em></div>
    <p class="sec-sub">All three integrate free. All three use the same 50p model. All three are live now at sebbi.pro.</p>
    <div class="product-cards">

      <div class="pc pc-al">
        <div class="pc-badge">AILeash &mdash; AI Governance</div>
        <h2>AILeash</h2>
        <p class="pc-desc">Enterprise AI governance. Nine-signal risk engine. SHA-256 audit chain. EU AI Act compliant from day one. Every AI decision scored, explained, and sealed to a court-admissible record.</p>
        <div class="pc-features">
          <div class="pcf">9-signal risk engine — ALLOW / CHALLENGE / BLOCK</div>
          <div class="pcf">SHA-256 Merkle audit chain — court admissible</div>
          <div class="pcf">EU AI Act Art.9, 12, 13 satisfied instantly</div>
          <div class="pcf">Sovereign local engine — data never leaves your network</div>
          <div class="pcf">Ofcom audit trail ready</div>
          <div class="pcf">100 free decisions — no card required</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">per device &middot; per month &middot; you set user price</div>
        <a href="#signup" class="btn btn-al" onclick="setProduct('aileash')">Get Free AILeash API Key &rarr;</a>
      </div>

      <div class="pc pc-gu">
        <div class="pc-badge">Guardian &mdash; Child Safety</div>
        <h2>AILeash Guardian</h2>
        <p class="pc-desc">Child safety layer. Grooming detection. CSAM mandatory block. Psychological manipulation signals. Online Safety Act 2023 and ICO Children's Code compliant. Includes Guardian App for parents.</p>
        <div class="pc-features">
          <div class="pcf">Real-time grooming pattern detection</div>
          <div class="pcf">CSAM mandatory block regardless of score</div>
          <div class="pcf">Parent Guardian App — installs in 60 seconds</div>
          <div class="pcf">Law enforcement evidence package — Action Fraud ready</div>
          <div class="pcf">Online Safety Act 2023 &amp; Ofcom compliant</div>
          <div class="pcf">100 free decisions — no card required</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">per device &middot; per month &middot; you set user price</div>
        <a href="#signup" class="btn btn-gu" onclick="setProduct('guardian')">Get Free Guardian API Key &rarr;</a>
      </div>

      <div class="pc pc-sb">
        <div class="pc-badge">SonicBoom &mdash; Speed Plugin</div>
        <h2>SonicBoom</h2>
        <p class="pc-desc">One-line plugin for any existing cloud AI infrastructure. Your system stays exactly as it is. Every decision goes from 200ms to 6ms. Full SHA-256 audit chain added automatically. Compliant instantly.</p>
        <div class="pc-features">
          <div class="pcf">6ms decisions — down from 200ms</div>
          <div class="pcf">One line to integrate — nothing else changes</div>
          <div class="pcf">Works with AWS, Azure, GCP, OpenAI, any API</div>
          <div class="pcf">SHA-256 audit chain added automatically</div>
          <div class="pcf">EU AI Act and Ofcom compliant instantly</div>
          <div class="pcf">100 free decisions — no card required</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">per device &middot; per month &middot; you set user price</div>
        <a href="#signup" class="btn btn-sb" onclick="setProduct('sonicboom')">Get Free SonicBoom Plugin &rarr;</a>
      </div>

    </div>
  </div>
</section>

<section class="model-sec" id="model">
  <div class="model-inner">
    <div class="sec-label">The Model</div>
    <div class="sec-title">Free to platforms. <em>Paid by users.</em></div>
    <p class="sec-sub">This is why nobody can compete. Platforms pay nothing. Users pay for protection. You keep the margin. We take 50p.</p>
    <div class="model-grid">
      <div class="mg">
        <div class="mg-icon">&#127970;</div>
        <div class="mg-n">Platform</div>
        <h3>Pays Nothing</h3>
        <p>Free API integration. Full compliance. Full child safety or speed boost. Zero cost to the platform. No excuse not to integrate.</p>
        <div class="mg-price">&pound;0</div>
        <div class="mg-price-sub">to integrate</div>
      </div>
      <div class="mg">
        <div class="mg-icon">&#128241;</div>
        <div class="mg-n">User</div>
        <h3>Pays You</h3>
        <p>Users pay whatever you charge for a protected or faster account. &pound;1, &pound;2.99, &pound;9.99 per device. You decide. You keep the margin.</p>
        <div class="mg-price">Your Price</div>
        <div class="mg-price-sub">you set it</div>
      </div>
      <div class="mg">
        <div class="mg-icon">&#9881;</div>
        <div class="mg-n">AILeash / SonicBoom</div>
        <h3>Takes 50p</h3>
        <p>We take 50p per device per month from your revenue. Everything above that is yours. No caps. No contracts. Forever.</p>
        <div class="mg-price">50p</div>
        <div class="mg-price-sub">per device we take</div>
      </div>
    </div>
  </div>
</section>

<section class="calc-sec" id="margin">
  <div class="calc-inner">
    <div class="sec-label" style="text-align:center">Your Margin</div>
    <div class="sec-title">Set your price. <em>See your profit.</em></div>
    <p class="sec-sub" style="text-align:center;margin:0 auto 0">We take 50p. Everything above is yours.</p>
    <div class="calc-wrap">
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

<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <div class="sec-label" style="text-align:center">Get Started</div>
    <div class="sec-title" style="text-align:center;color:var(--white)">Free API key. <em>Right now.</em></div>
    <p style="font-size:15px;color:rgba(255,255,255,0.35);text-align:center;line-height:1.7;margin-top:12px">Name and email. API key delivered instantly. 100 free decisions. No card required.</p>
    <div class="form-wrap">
      <div class="product-tabs">
        <button class="ptab ptab-al-on" id="tab-al" onclick="setProduct('aileash')">AILeash</button>
        <button class="ptab" id="tab-gu" onclick="setProduct('guardian')">Guardian</button>
        <button class="ptab" id="tab-sb" onclick="setProduct('sonicboom')">SonicBoom</button>
      </div>
      <div class="fg-row">
        <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
        <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
      </div>
      <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
      <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
      <div class="fg"><label>Company / Platform Name</label><input type="text" id="org" placeholder="e.g. Roblox / GameZone / My Platform"></div>
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
      <button class="btn-full btn-full-al" id="go-btn" onclick="doSignup()">Get Free AILeash API Key &rarr;</button>
      <div class="msg msg-ok" id="msg-ok"></div>
      <div class="msg msg-err" id="msg-err"></div>
      <div class="key-box" id="key-box">
        <div class="key-lbl">Your API Key &mdash; Save This Now</div>
        <div class="key-val" id="key-val"></div>
        <div class="key-next">100 free decisions included. Justin will be in touch within 24 hours.<br><br>justin@monopcontent.com &middot; 07908 269428 &middot; sebbi.pro</div>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="foot-links">
    <a href="#products">AILeash</a>
    <a href="#products">Guardian</a>
    <a href="#products">SonicBoom</a>
    <a href="/reseller">Partner Programme</a>
    <a href="/scan">AI Act Scanner</a>
    <a href="/guardian-app">Guardian App</a>
    <a href="/sonicboom">SonicBoom</a>
    <a href="/contact">Contact</a>
  </div>
  <div class="foot-copy">&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK &middot; justin@monopcontent.com &middot; 07908 269428 &middot; sebbi.pro</div>
</footer>

<script>
var AP='aileash';
function setProduct(p){
  AP=p;
  document.getElementById('tab-al').className='ptab'+(p==='aileash'?' ptab-al-on':'');
  document.getElementById('tab-gu').className='ptab'+(p==='guardian'?' ptab-gu-on':'');
  document.getElementById('tab-sb').className='ptab'+(p==='sonicboom'?' ptab-sb-on':'');
  var btn=document.getElementById('go-btn');
  if(p==='aileash'){btn.textContent='Get Free AILeash API Key \u2192';btn.className='btn-full btn-full-al';}
  else if(p==='guardian'){btn.textContent='Get Free Guardian API Key \u2192';btn.className='btn-full btn-full-gu';}
  else{btn.textContent='Get Free SonicBoom Plugin \u2192';btn.className='btn-full btn-full-sb';}
}
function calc(){
  var charge=parseFloat(document.getElementById('charge').value)||0;
  var devices=parseInt(document.getElementById('devices').value)||0;
  var youKeep=Math.max(0,charge-0.50)*devices;
  var weGet=0.50*devices;
  document.getElementById('r-user').textContent='\u00a3'+charge.toFixed(2);
  document.getElementById('r-you').textContent='\u00a3'+youKeep.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('r-we').textContent='\u00a3'+weGet.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
}
calc();
async function doSignup(){
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var org=document.getElementById('org').value.trim();
  var dv=parseInt(document.getElementById('dv').value)||1;
  var ok=document.getElementById('msg-ok');
  var err=document.getElementById('msg-err');
  var kb=document.getElementById('key-box');
  var btn=document.getElementById('go-btn');
  ok.classList.remove('show');err.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company name.';err.classList.add('show');return;}
  var origText=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:AP,product:AP==='guardian'?'guardian':'aileash',devices:dv})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      kb.classList.add('show');
      ok.textContent='Key created. 100 free decisions. Setting up billing\u2026';ok.classList.add('show');
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
</script>
</body>
</html>"""

# ============================================================================
# HTTP SERVER
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
