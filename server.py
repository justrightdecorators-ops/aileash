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

# ============================================================================
# REFERRAL SYSTEM
# ============================================================================
import random,string

def gen_ref_code(name):
    prefix=(''.join(c for c in name.upper().split()[0] if c.isalpha())[:4]).ljust(4,'X')
    suffix=''.join(random.choices(string.digits,k=4))
    return f"REF-{prefix}-{suffix}"

def create_referral(key,email,name):
    code=gen_ref_code(name)
    with _db_lock:
        try:
            _conn.execute("CREATE TABLE IF NOT EXISTS referrals(code TEXT PRIMARY KEY,referrer_key TEXT,referrer_email TEXT,referrer_name TEXT,created REAL,devices_referred INTEGER DEFAULT 0,earnings_pence INTEGER DEFAULT 0)")
            _conn.execute("INSERT OR IGNORE INTO referrals(code,referrer_key,referrer_email,referrer_name,created) VALUES(?,?,?,?,?)",(code,key,email,name,time.time()))
            _conn.commit()
        except:pass
    return code

def get_referral(code):
    with _db_lock:
        try:return _conn.execute("SELECT referrer_key,referrer_email,referrer_name,devices_referred,earnings_pence FROM referrals WHERE code=?",(code,)).fetchone()
        except:return None

def credit_referral(code,devices=1):
    with _db_lock:
        try:
            _conn.execute("UPDATE referrals SET devices_referred=devices_referred+?,earnings_pence=earnings_pence+? WHERE code=?",(devices,devices*10,code))
            _conn.commit()
        except:pass

def send_referral_welcome(name,email,key,ref_code,product,monthly):
    pname={"guardian":"AILeash Guardian","sonicboom":"SonicBoom","sentinel":"AILeash Sentinel"}.get(product,"AILeash")
    html=f"""<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'>
<div style='max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'>
<div style='background:#0a0f1e;padding:32px;border-bottom:4px solid #c9a84c'>
<div style='font-size:22px;color:#fff;font-weight:900;font-family:Georgia,serif'>Monop <span style='color:#c9a84c'>Content</span></div>
</div>
<div style='padding:36px'>
<p style='font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:16px'>Welcome{', '+name.split()[0] if name.strip() else ''}.</p>
<p style='font-size:14px;color:#64748b;line-height:1.7'>Your {pname} API key is ready. 100 free decisions included. After that it is 50p per device per month via Stripe.</p>
<div style='background:#0a0f1e;border-radius:6px;padding:20px;margin:20px 0'>
<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your API Key</div>
<div style='font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all'>{key}</div>
</div>
<div style='background:#f8f5ee;border:2px solid #c9a84c;border-radius:6px;padding:20px;margin:20px 0'>
<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your Referral Code</div>
<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>{ref_code}</div>
<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Share this code with anyone who needs AI compliance or child safety. Every device they sign up earns you <strong>10p per month forever</strong>. Check your earnings at <a href='{HOST}/referrals?code={ref_code}' style='color:#c9a84c'>{HOST}/referrals</a></p>
</div>
<div style='background:#f0f9ff;border:1px solid #bae6fd;border-radius:6px;padding:16px;margin:20px 0'>
<p style='font-size:13px;color:#0369a1;line-height:1.6;margin:0'><strong>You will receive weekly compliance intelligence emails</strong> — real Ofcom updates, EU AI Act news and enforcement actions. Forward them to your team. They will think you are a genius.</p>
</div>
<p style='font-size:13px;color:#64748b'>Questions? Reply to this email or contact <a href='mailto:{OWNER_EMAIL}' style='color:#c9a84c'>{OWNER_EMAIL}</a> &middot; {OWNER_PHONE}</p>
</div>
</div></body></html>"""
    send_email(email,name,f"Your {pname} API Key + Referral Code",html)

def send_intelligence_email(email,name):
    html=f"""<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'>
<div style='max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'>
<div style='background:#0a0f1e;padding:28px;border-bottom:4px solid #c9a84c'>
<div style='font-size:18px;color:#fff;font-weight:900;font-family:Georgia,serif'>Monop Content <span style='color:#c9a84c'>Intelligence</span></div>
<div style='font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-top:4px'>Weekly Compliance Briefing</div>
</div>
<div style='padding:32px'>
<p style='font-size:16px;font-weight:700;color:#0a0f1e;margin-bottom:16px'>This week in AI compliance</p>
<div style='border-left:4px solid #cc0000;padding-left:16px;margin-bottom:20px'>
<p style='font-size:13px;color:#cc0000;font-weight:700;margin-bottom:4px;font-family:monospace;text-transform:uppercase;letter-spacing:1px'>EU AI Act — August 2026</p>
<p style='font-size:14px;color:#1a202c;line-height:1.7'>Enforcement is 10 weeks away. High-risk AI systems must have a tamper-evident audit chain, explainable decisions, continuous risk management and human oversight. Standard logs do not satisfy Article 12. You need a SHA-256 Merkle chain.</p>
</div>
<div style='border-left:4px solid #c9a84c;padding-left:16px;margin-bottom:20px'>
<p style='font-size:13px;color:#b45309;font-weight:700;margin-bottom:4px;font-family:monospace;text-transform:uppercase;letter-spacing:1px'>Online Safety Act — Already In Force</p>
<p style='font-size:14px;color:#1a202c;line-height:1.7'>Ofcom is actively investigating platforms right now. If children can access your platform you need documented, systematic, auditable risk assessment. A moderation team and a report button is not enough.</p>
</div>
<div style='border-left:4px solid #00875a;padding-left:16px;margin-bottom:24px'>
<p style='font-size:13px;color:#00875a;font-weight:700;margin-bottom:4px;font-family:monospace;text-transform:uppercase;letter-spacing:1px'>What Smart Platforms Are Doing</p>
<p style='font-size:14px;color:#1a202c;line-height:1.7'>Integrating AILeash before the deadline. Free API. 50p per device. SHA-256 audit chain from day one. The platforms that move now will have years of compliance history when regulators come knocking. The ones that wait will have nothing.</p>
</div>
<div style='background:#0a0f1e;border-radius:6px;padding:20px;text-align:center'>
<p style='color:rgba(255,255,255,0.6);font-size:13px;margin-bottom:12px'>Your referral code earns you 10p per device per month forever</p>
<a href='{HOST}/#signup' style='background:#c9a84c;color:#0a0f1e;padding:12px 24px;text-decoration:none;border-radius:4px;font-weight:700;font-size:14px'>Get AILeash Free</a>
</div>
<p style='font-size:11px;color:#94a3b8;margin-top:20px;text-align:center'>Monop Content &middot; Blyth, UK &middot; <a href='mailto:{OWNER_EMAIL}' style='color:#94a3b8'>{OWNER_EMAIL}</a></p>
</div>
</div></body></html>"""
    send_email(email,name,"Weekly AI Compliance Intelligence — Monop Content",html)

def send_contact_notification(visitor_name,visitor_email,visitor_msg):
    html=f"""<html><body style='font-family:Arial,sans-serif;padding:20px;color:#333'>
<h2 style='color:#0a0f1e'>New message via AILeash chat</h2>
<p><strong>From:</strong> {visitor_name}</p>
<p><strong>Email:</strong> {visitor_email}</p>
<p><strong>Message:</strong></p>
<div style='background:#f5f7fa;border-left:4px solid #c9a84c;padding:16px;border-radius:4px;font-size:14px;line-height:1.7'>{visitor_msg}</div>
<p style='margin-top:16px;font-size:12px;color:#64748b'>Sent from the AILeash on-site chat assistant</p>
</body></html>"""
    send_email(OWNER_EMAIL,OWNER_NAME,f"Chat message from {visitor_name}",html)


HOMEPAGE="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Monop Content &mdash; AI Compliance Made Simple</title>
<meta name="description" content="Four products. All free to integrate. You set the margin. We take 50p per device per month. EU AI Act. Child Safety. Speed. Fraud Detection.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--gold:#c9a84c;--red:#cc0000;--cyan:#00d4ff;--purple:#7c3aed;--green:#00875a;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--text:#1a202c;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--white);color:var(--text);font-family:var(--sans);overflow-x:hidden}
html{scroll-behavior:smooth}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:var(--navy);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between}
.nav-logo{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:16px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 18px;font-weight:700!important;border-radius:4px}
.alert-bar{background:var(--red);padding:10px 48px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--white);letter-spacing:1px;text-transform:uppercase;margin-top:68px}
.alert-bar strong{color:#ffd700}
.hero{background:var(--navy);padding:72px 48px 88px;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 20% 60%,rgba(201,168,76,0.06) 0%,transparent 55%)}
.hero-inner{max-width:1200px;margin:0 auto;position:relative;z-index:1;text-align:center}
h1{font-family:var(--display);font-size:clamp(40px,5vw,68px);line-height:1.05;color:var(--white);font-weight:900;margin-bottom:20px}
h1 em{color:var(--gold);font-style:normal}
h2{font-family:var(--display);font-size:clamp(28px,3vw,44px);font-weight:900;margin-bottom:14px;line-height:1.1}
h2 em{color:var(--gold);font-style:normal}
.hero-sub{font-size:18px;color:rgba(255,255,255,0.5);line-height:1.8;max-width:700px;margin:0 auto 40px}
.hero-sub strong{color:var(--white)}
.hero-btns{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.btn-gold{background:var(--gold);color:var(--navy);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-gold:hover{background:#e8c96a;transform:translateY(-2px)}
.btn-ghost{background:transparent;color:rgba(255,255,255,0.5);padding:14px 28px;border:1px solid rgba(255,255,255,0.15);font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-ghost:hover{color:var(--white);border-color:rgba(255,255,255,0.4)}
.divider{height:4px;background:linear-gradient(90deg,var(--gold) 0%,var(--red) 33%,var(--cyan) 66%,var(--purple) 100%)}
.stats-strip{background:var(--navy)}
.stats-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:repeat(5,1fr)}
.stat{padding:24px 16px;border-right:1px solid rgba(255,255,255,0.05);text-align:center}.stat:last-child{border:none}
.stat-n{font-family:var(--display);font-size:32px;color:var(--gold);font-weight:900}
.stat-l{font-size:10px;color:rgba(255,255,255,0.25);margin-top:4px;letter-spacing:1px;text-transform:uppercase}
.slbl{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px;color:rgba(0,0,0,0.25)}
.sec{padding:72px 48px;border-bottom:1px solid var(--border)}
.sec-inner{max-width:1200px;margin:0 auto}
.sec-sub{font-size:15px;color:var(--muted);max-width:600px;line-height:1.75;margin-bottom:44px}
.explain-sec{padding:72px 48px;background:var(--off);border-bottom:1px solid var(--border)}
.explain-inner{max-width:900px;margin:0 auto;text-align:center}
.explain-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:var(--border);margin-top:40px}
.es{background:var(--white);padding:32px 24px;text-align:center}
.es-n{font-family:var(--display);font-size:48px;color:var(--gold);font-weight:900;opacity:0.3;margin-bottom:8px}
.es h3{font-family:var(--display);font-size:20px;font-weight:900;color:var(--navy);margin-bottom:10px}
.es p{font-size:13px;color:var(--muted);line-height:1.7}
.products-sec{padding:72px 48px;border-bottom:1px solid var(--border)}
.products-inner{max-width:1200px;margin:0 auto}
.product-cards{display:grid;grid-template-columns:repeat(2,1fr);gap:2px;background:var(--border);margin-top:40px}
.pc{background:var(--white);padding:36px 28px;position:relative}
.pc::before{content:'';position:absolute;top:0;left:0;right:0;height:4px}
.pc-al::before{background:var(--gold)}.pc-gu::before{background:var(--red)}.pc-sb::before{background:var(--cyan)}.pc-se::before{background:var(--purple)}
.pc-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;display:inline-block;padding:3px 10px;border-radius:2px}
.pc-al .pc-badge{color:var(--gold);background:rgba(201,168,76,0.08);border:1px solid rgba(201,168,76,0.2)}
.pc-gu .pc-badge{color:var(--red);background:rgba(204,0,0,0.05);border:1px solid rgba(204,0,0,0.15)}
.pc-sb .pc-badge{color:var(--cyan);background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.2)}
.pc-se .pc-badge{color:var(--purple);background:rgba(124,58,237,0.05);border:1px solid rgba(124,58,237,0.2)}
.pc h3{font-family:var(--display);font-size:24px;font-weight:900;margin-bottom:10px;color:var(--navy)}
.pc-desc{font-size:14px;color:var(--muted);line-height:1.75;margin-bottom:20px}
.pc-features{display:flex;flex-direction:column;gap:6px;margin-bottom:24px}
.pcf{display:flex;align-items:flex-start;gap:8px;font-size:13px;color:var(--muted);padding:6px 0;border-bottom:1px solid var(--border)}
.pcf::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;flex-shrink:0;margin-top:2px}
.pc-al .pcf::before{color:var(--gold)}.pc-gu .pcf::before{color:var(--red)}.pc-sb .pcf::before{color:var(--cyan)}.pc-se .pcf::before{color:var(--purple)}
.pc-price{font-family:var(--display);font-size:44px;font-weight:900;line-height:1;margin-bottom:4px}
.pc-al .pc-price{color:var(--gold)}.pc-gu .pc-price{color:var(--red)}.pc-sb .pc-price{color:var(--cyan)}.pc-se .pc-price{color:var(--purple)}
.pc-price-label{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:20px;letter-spacing:1px}
.btn-block{display:block;text-align:center;padding:13px 20px;border-radius:4px;font-family:var(--sans);font-weight:700;font-size:14px;text-decoration:none;transition:all .2s;border:none;cursor:pointer;width:100%}
.btn-al{background:var(--gold);color:var(--navy)}.btn-al:hover{background:#e8c96a}
.btn-gu{background:var(--red);color:var(--white)}.btn-gu:hover{background:#aa0000}
.btn-sb{background:var(--cyan);color:var(--navy)}.btn-sb:hover{background:#33ddff}
.btn-se{background:var(--purple);color:var(--white)}.btn-se:hover{background:#6d28d9}
.pc-note{font-family:var(--mono);font-size:9px;color:var(--muted);text-align:center;margin-top:8px;letter-spacing:1px}
.calc-sec{padding:72px 48px;background:var(--navy);border-bottom:4px solid var(--gold)}
.calc-inner{max-width:700px;margin:0 auto;text-align:center}
.calc-wrap{background:rgba(255,255,255,0.04);border:2px solid rgba(201,168,76,0.3);border-radius:10px;padding:36px;margin-top:36px}
.calc-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;align-items:end}
.calc-label{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.calc-input-row{display:flex;align-items:center;gap:8px}
.pound{font-family:var(--display);font-size:28px;color:var(--gold);font-weight:900}
.calc-input{background:rgba(255,255,255,0.08);border:2px solid rgba(201,168,76,0.3);color:var(--white);padding:12px 16px;font-size:20px;font-family:var(--display);font-weight:700;width:120px;border-radius:6px;outline:none;text-align:center}
.calc-input:focus{border-color:var(--gold)}
.calc-devices{background:rgba(255,255,255,0.08);border:2px solid rgba(255,255,255,0.1);color:var(--white);padding:12px 16px;font-size:15px;font-family:var(--sans);width:100%;border-radius:6px;outline:none}
.calc-devices option{background:var(--navy)}
.calc-results{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.05);border-radius:6px;overflow:hidden;margin-top:0}
.cr{background:rgba(255,255,255,0.03);padding:20px;text-align:center}
.cr-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.cr-amount{font-family:var(--display);font-size:28px;font-weight:900;line-height:1}
.cr-you{color:#00ff88}.cr-we{color:rgba(255,255,255,0.2)}.cr-user{color:var(--gold)}
.cr-sub{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);margin-top:4px}
.referral-sec{padding:72px 48px;background:var(--off);border-bottom:1px solid var(--border)}
.referral-inner{max-width:900px;margin:0 auto;text-align:center}
.ref-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:var(--border);margin-top:36px}
.rs{background:var(--white);padding:28px;text-align:center}
.rs-icon{font-size:32px;margin-bottom:12px}
.rs h3{font-family:var(--display);font-size:18px;font-weight:900;color:var(--navy);margin-bottom:8px}
.rs p{font-size:13px;color:var(--muted);line-height:1.65}
.rs-earn{font-family:var(--display);font-size:36px;color:var(--gold);font-weight:900;margin-top:10px}
.rs-earn-label{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:1px;text-transform:uppercase}
.compliance-sec{padding:72px 48px;border-bottom:1px solid var(--border)}
.comp-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:36px}
.comp-card{background:var(--off);border:1px solid var(--border);padding:24px;border-left:4px solid var(--navy)}
.comp-act{font-family:var(--mono);font-size:9px;color:var(--navy);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;opacity:0.4}
.comp-card h3{font-family:var(--display);font-size:17px;font-weight:800;margin-bottom:8px;color:var(--navy)}
.comp-card .simple{font-size:15px;font-weight:700;color:var(--navy);margin-bottom:6px;line-height:1.4}
.comp-card p{font-size:13px;color:var(--muted);line-height:1.65}
.checks{margin-top:10px;display:flex;flex-direction:column;gap:4px}
.chk{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}
.chk::before{content:'OK';color:var(--green);font-weight:700;flex-shrink:0;font-family:var(--mono);font-size:9px}
.signup-sec{padding:72px 48px;background:var(--white);border-top:4px solid var(--gold)}
.signup-inner{max-width:560px;margin:0 auto}
.product-tabs{display:grid;grid-template-columns:repeat(4,1fr);gap:0;margin-bottom:24px;border:2px solid var(--border);border-radius:6px;overflow:hidden}
.stab{padding:10px 4px;text-align:center;cursor:pointer;font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;font-weight:600;transition:all .2s;background:var(--white);color:var(--muted);border:none;outline:none}
.stab-al-on{background:var(--navy);color:var(--gold)}
.stab-gu-on{background:var(--red);color:var(--white)}
.stab-sb-on{background:var(--navy);color:var(--cyan)}
.stab-se-on{background:var(--purple);color:var(--white)}
.fg{margin-bottom:12px}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:var(--off);border:2px solid var(--border);color:var(--text);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus{border-color:var(--navy)}
.fg input::placeholder{color:#bbb}
.fg select option{background:var(--white)}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.ref-field{background:var(--off);border:2px solid var(--border);border-radius:4px;padding:12px 14px;font-size:14px;font-family:var(--mono);color:var(--gold);font-weight:700;margin-bottom:12px;width:100%;outline:none;transition:border-color .2s}
.ref-field:focus{border-color:var(--gold)}
.ref-field::placeholder{color:#ccc;font-family:var(--sans);font-weight:400}
.btn-full{width:100%;margin-top:8px;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}
.key-box{display:none;margin-top:20px;background:var(--navy);border-radius:6px;padding:22px}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:#00ff88;word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px}
.ref-box{margin-top:12px;background:rgba(201,168,76,0.1);border:1px solid rgba(201,168,76,0.3);border-radius:4px;padding:12px}
.ref-box-label{font-family:var(--mono);font-size:9px;color:var(--gold);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.ref-box-code{font-family:var(--mono);font-size:18px;color:var(--gold);font-weight:700}
.ref-box-desc{font-size:12px;color:rgba(255,255,255,0.4);margin-top:6px;line-height:1.6}
.usage-box{margin-top:12px;font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);padding:12px;border-radius:4px;line-height:1.9}
.usage-box em{color:#79b8ff;font-style:normal}
.msg-err{display:none;color:var(--red);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}
.msg-err.show{display:block}
.msg-ok{display:none;color:var(--green);font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:#f0fff8;border-radius:4px;border:1px solid #bbf7d0}
.msg-ok.show{display:block}
.chat-bubble{position:fixed;bottom:24px;right:24px;z-index:999}
.chat-btn{background:var(--navy);color:var(--white);border:none;border-radius:50%;width:60px;height:60px;font-size:24px;cursor:pointer;box-shadow:0 4px 20px rgba(0,0,0,0.3);transition:all .2s;border:2px solid var(--gold)}
.chat-btn:hover{transform:scale(1.1);background:#111827}
.chat-window{display:none;position:fixed;bottom:100px;right:24px;width:380px;height:520px;background:var(--navy);border:1px solid rgba(255,255,255,0.1);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.5);flex-direction:column;overflow:hidden;z-index:999}
.chat-window.open{display:flex}
.chat-header{padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;align-items:center;justify-content:space-between;background:rgba(255,255,255,0.03)}
.chat-header-left h3{font-family:var(--display);font-size:16px;color:var(--white);font-weight:900}
.chat-header-left p{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.3);letter-spacing:1px;text-transform:uppercase;margin-top:2px}
.chat-close{background:none;border:none;color:rgba(255,255,255,0.3);font-size:20px;cursor:pointer;transition:color .2s}.chat-close:hover{color:var(--white)}
.chat-mode-tabs{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid rgba(255,255,255,0.08)}
.cmt{padding:8px;text-align:center;font-family:var(--mono);font-size:9px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;border:none;transition:all .2s;color:rgba(255,255,255,0.3);background:transparent}
.cmt.on{background:rgba(201,168,76,0.1);color:var(--gold);border-bottom:2px solid var(--gold)}
.chat-msgs{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.chat-msgs::-webkit-scrollbar{width:3px}
.chat-msgs::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:2px}
.cm{max-width:85%;padding:10px 14px;border-radius:8px;font-size:13px;line-height:1.5}
.cm-ai{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);color:rgba(255,255,255,0.8);align-self:flex-start;border-radius:4px 8px 8px 8px}
.cm-user{background:rgba(201,168,76,0.15);border:1px solid rgba(201,168,76,0.2);color:var(--white);align-self:flex-end;border-radius:8px 4px 8px 8px}
.cm-typing{display:flex;gap:4px;padding:10px 14px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.08);border-radius:4px 8px 8px 8px;align-self:flex-start;width:fit-content}
.cm-typing span{width:5px;height:5px;background:var(--gold);border-radius:50%;animation:bounce 1.2s infinite}
.cm-typing span:nth-child(2){animation-delay:.2s}.cm-typing span:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-5px)}}
.chat-email-form{padding:16px;display:none;flex-direction:column;gap:8px}
.chat-email-form.show{display:flex}
.cef input,.cef textarea{width:100%;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:var(--white);padding:10px 12px;font-size:13px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.cef input:focus,.cef textarea:focus{border-color:var(--gold)}
.cef input::placeholder,.cef textarea::placeholder{color:rgba(255,255,255,0.2)}
.cef textarea{resize:none;height:80px;line-height:1.5}
.chat-input-row{padding:12px 16px;border-top:1px solid rgba(255,255,255,0.08);display:flex;gap:8px;align-items:flex-end}
.chat-input{flex:1;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:var(--white);padding:10px 12px;font-size:13px;font-family:var(--sans);outline:none;border-radius:6px;resize:none;max-height:80px;line-height:1.4;transition:border-color .2s}
.chat-input:focus{border-color:rgba(201,168,76,0.4)}
.chat-input::placeholder{color:rgba(255,255,255,0.2)}
.chat-send{background:var(--gold);color:var(--navy);border:none;border-radius:6px;width:36px;height:36px;cursor:pointer;font-size:14px;flex-shrink:0;transition:background .2s}
.chat-send:hover{background:#e8c96a}.chat-send:disabled{opacity:0.4}
footer{background:#111827;padding:48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:2fr 1fr 1fr 1fr;gap:40px}
.foot-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;margin-bottom:4px}.foot-logo span{color:var(--gold)}
.foot-tag{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.15);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.foot-desc{font-size:12px;color:rgba(255,255,255,0.2);line-height:1.75}
.foot-col h4{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);text-transform:uppercase;margin-bottom:10px}
.foot-col a{display:block;color:rgba(255,255,255,0.2);text-decoration:none;font-size:12px;margin-bottom:6px;transition:color .2s}.foot-col a:hover{color:var(--white)}
.foot-bottom{max-width:1200px;margin:28px auto 0;padding-top:16px;border-top:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;font-size:10px;color:rgba(255,255,255,0.12);font-family:var(--mono)}
@media(max-width:900px){
nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
.hero,.sec,.explain-sec,.products-sec,.calc-sec,.referral-sec,.compliance-sec,.signup-sec{padding:48px 20px!important}
.stats-inner{grid-template-columns:repeat(3,1fr)!important}
.product-cards,.explain-steps,.ref-steps,.comp-grid{grid-template-columns:1fr!important}
.fg-row,.product-tabs,.calc-row,.calc-results{grid-template-columns:1fr!important}
.chat-window{width:calc(100vw - 32px);right:16px}
footer{padding:36px 20px}.foot-inner{grid-template-columns:1fr}.foot-bottom{flex-direction:column;gap:4px}}
</style>
</head>
<body>

<nav>
  <div class="nav-logo">Monop <span>Content</span></div>
  <div class="nav-links">
    <a href="#products">Products</a>
    <a href="#how">How It Works</a>
    <a href="#compliance">The Law</a>
    <a href="#referral">Earn 10p</a>
    <a href="/scan">Free Scanner</a>
    <a href="/contact">Contact</a>
    <a href="#signup" class="nav-cta">Get Free API Key</a>
  </div>
</nav>

<div class="alert-bar"><strong>EU AI Act: August 2026.</strong> &nbsp; UK Online Safety Act: now in force. &nbsp; <strong>Ignore it and the fine is 3% of your global turnover.</strong></div>

<section class="hero">
  <div class="hero-inner">
    <h1>AI compliance is complicated.<br><em>We made it simple.</em></h1>
    <p class="hero-sub">Four products. All free to integrate. <strong>Your users pay for protection.</strong> You set what they pay. We take 50p per device per month. You keep everything above that. Forever.</p>
    <div class="hero-btns">
      <a href="#how" class="btn-gold">Show Me How It Works &darr;</a>
      <a href="#signup" class="btn-ghost">Get Free API Key</a>
      <a href="/scan" class="btn-ghost">Free AI Act Scanner</a>
    </div>
  </div>
</section>

<div class="divider"></div>

<div class="stats-strip"><div class="stats-inner">
  <div class="stat"><div class="stat-n">4</div><div class="stat-l">Products</div></div>
  <div class="stat"><div class="stat-n">50p</div><div class="stat-l">We Take</div></div>
  <div class="stat"><div class="stat-n">&lt;30ms</div><div class="stat-l">Per Decision</div></div>
  <div class="stat"><div class="stat-n">SHA256</div><div class="stat-l">Audit Chain</div></div>
  <div class="stat"><div class="stat-n">10p</div><div class="stat-l">You Earn Per Referral</div></div>
</div></div>

<section class="explain-sec" id="how">
  <div class="explain-inner">
    <div class="slbl">How It Works</div>
    <h2>Three steps. <em>That is it.</em></h2>
    <p style="font-size:15px;color:var(--muted);line-height:1.75;max-width:580px;margin:0 auto">We built something that normally costs &pound;50,000 a year and made it 50p. Here is how the whole thing works in plain English.</p>
    <div class="explain-steps">
      <div class="es">
        <div class="es-n">01</div>
        <h3>You get a free API key</h3>
        <p>Sign up below. No card. No contract. You get an API key and 100 free decisions to test everything. Takes 60 seconds.</p>
      </div>
      <div class="es">
        <div class="es-n">02</div>
        <h3>Your platform calls our engine</h3>
        <p>Every time a user does something on your platform, you send us the details. We score it in under 30 milliseconds and tell you ALLOW, CHALLENGE or BLOCK.</p>
      </div>
      <div class="es">
        <div class="es-n">03</div>
        <h3>You charge your users. We take 50p.</h3>
        <p>Charge your users &pound;1.99 a month for a protected account. We take 50p. You keep &pound;1.49 per user per month. Forever. For doing nothing after setup.</p>
      </div>
    </div>
  </div>
</section>

<section class="products-sec" id="products">
  <div class="products-inner">
    <div class="slbl">Four Products</div>
    <h2>Pick what you need. <em>Or take all four.</em></h2>
    <p class="sec-sub">Every product uses the same engine. Every product is free to integrate. Every product takes 50p per device per month underneath whatever you charge.</p>
    <div class="product-cards">

      <div class="pc pc-al">
        <div class="pc-badge">AILeash &mdash; AI Governance</div>
        <h3>AILeash</h3>
        <p class="pc-desc">In simple terms: every time your AI makes a decision that affects a person, AILeash records it in a way that nobody can ever change or delete. This means if a regulator ever asks you to prove what your AI decided and why &mdash; you can. Without this, you have nothing.</p>
        <div class="pc-features">
          <div class="pcf">Every AI decision scored across 9 signals in real time &mdash; ALLOW, CHALLENGE or BLOCK</div>
          <div class="pcf">Every decision recorded in a tamper-proof chain &mdash; nobody can alter it, not even you</div>
          <div class="pcf">Every decision explained in plain language &mdash; regulators can read it instantly</div>
          <div class="pcf">EU AI Act Articles 9, 12 and 13 satisfied from day one &mdash; no extra work needed</div>
          <div class="pcf">Human review pathway for high-risk decisions &mdash; satisfies Article 14</div>
          <div class="pcf">100 free decisions included &mdash; no card required to start</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">we take per device per month &middot; you set user price</div>
        <a href="#signup" class="btn-block btn-al" onclick="setProduct('aileash')">Get Free AILeash API Key &rarr;</a>
        <p class="pc-note">Free trial &middot; No card &middot; Stripe billing after trial</p>
      </div>

      <div class="pc pc-gu">
        <div class="pc-badge">Guardian &mdash; Child Safety</div>
        <h3>AILeash Guardian</h3>
        <p class="pc-desc">In simple terms: if children use your platform, the law says you must protect them. Not with a policy document &mdash; with actual working technology that detects predators in real time and stops them before a child gets hurt. Guardian does exactly that.</p>
        <div class="pc-features">
          <div class="pcf">Detects grooming patterns before they escalate &mdash; blocked before the child sees it</div>
          <div class="pcf">CSAM triggers an automatic block regardless of any other score &mdash; mandatory, no exceptions</div>
          <div class="pcf">Detects love bombing, isolation attempts and psychological manipulation</div>
          <div class="pcf">Guardian App for parents &mdash; installs on any phone in 60 seconds, no app store</div>
          <div class="pcf">Every block generates a law enforcement evidence package for Action Fraud and CEOP</div>
          <div class="pcf">Online Safety Act 2023, ICO Children's Code and Ofcom compliant from day one</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">we take per device per month &middot; you set user price</div>
        <a href="#signup" class="btn-block btn-gu" onclick="setProduct('guardian')">Get Free Guardian API Key &rarr;</a>
        <p class="pc-note">Free trial &middot; No card &middot; Stripe billing after trial</p>
      </div>

      <div class="pc pc-sb">
        <div class="pc-badge">SonicBoom &mdash; Speed Plugin</div>
        <h3>SonicBoom</h3>
        <p class="pc-desc">In simple terms: if you already have AI running on AWS, Azure, Google Cloud or OpenAI, it is probably slow. SonicBoom is one line of code that makes it significantly faster and adds a full compliance audit chain automatically. Your system stays exactly as it is. You just add one line.</p>
        <div class="pc-features">
          <div class="pcf">One line of code around your existing AI calls &mdash; nothing else changes</div>
          <div class="pcf">Significantly faster than standard cloud AI infrastructure</div>
          <div class="pcf">Works with AWS, Azure, Google Cloud, OpenAI, Anthropic or any other API</div>
          <div class="pcf">SHA-256 audit chain added to every call automatically &mdash; Ofcom and EU AI Act compliant</div>
          <div class="pcf">Your data never leaves your network &mdash; sovereign architecture</div>
          <div class="pcf">100 free decisions included &mdash; no card required to start</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">we take per device per month &middot; you set user price</div>
        <a href="/sonicboom" class="btn-block btn-sb">Learn More About SonicBoom &rarr;</a>
        <p class="pc-note">Free plugin &middot; No card &middot; Stripe billing after trial</p>
      </div>

      <div class="pc pc-se">
        <div class="pc-badge">Sentinel &mdash; Fraud Detection</div>
        <h3>AILeash Sentinel</h3>
        <p class="pc-desc">In simple terms: Sentinel watches your platform 24 hours a day and sends you an alert the moment something unusual happens. A user suddenly sending 500 messages in a minute. Someone logging in from a different country. A pattern that looks like fraud. You find out immediately &mdash; not days later when the damage is done.</p>
        <div class="pc-features">
          <div class="pcf">Real-time fraud and anomaly monitoring across your entire platform</div>
          <div class="pcf">Instant alerts when unusual behaviour is detected &mdash; email and push notification</div>
          <div class="pcf">Velocity monitoring &mdash; catches burst attacks, account takeovers and bot activity</div>
          <div class="pcf">Trust decay scoring &mdash; identifies bad actors before they cause damage</div>
          <div class="pcf">Full SHA-256 audit trail of every alert &mdash; admissible as fraud evidence in court</div>
          <div class="pcf">Integrates with your existing system &mdash; one API call, same 50p model</div>
        </div>
        <div class="pc-price">50p</div>
        <div class="pc-price-label">we take per device per month &middot; you set user price</div>
        <a href="#signup" class="btn-block btn-se" onclick="setProduct('sentinel')">Get Free Sentinel API Key &rarr;</a>
        <p class="pc-note">Free trial &middot; No card &middot; Stripe billing after trial</p>
      </div>

    </div>
  </div>
</section>

<section class="calc-sec" id="margin">
  <div class="calc-inner">
    <div class="slbl" style="color:rgba(255,255,255,0.3)">Your Margin</div>
    <h2 style="color:var(--white)">Set your price. <em>See your profit.</em></h2>
    <p style="font-size:15px;color:rgba(255,255,255,0.4);line-height:1.75;margin-bottom:0">We take 50p. Everything above is yours. Every month. Forever.</p>
    <div class="calc-wrap">
      <div class="calc-row">
        <div>
          <div class="calc-label">You charge per device per month</div>
          <div class="calc-input-row"><span class="pound">&pound;</span><input class="calc-input" type="number" id="charge" value="1.99" min="0.51" step="0.01" oninput="calc()"></div>
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
        <div class="cr"><div class="cr-label">User Pays</div><div class="cr-amount cr-user" id="r-user">&pound;1.99</div><div class="cr-sub">per device per month</div></div>
        <div class="cr"><div class="cr-label">You Keep</div><div class="cr-amount cr-you" id="r-you">&pound;1,490</div><div class="cr-sub">per month profit</div></div>
        <div class="cr"><div class="cr-label">We Take</div><div class="cr-amount cr-we" id="r-we">&pound;500</div><div class="cr-sub">per month (50p per device)</div></div>
      </div>
    </div>
  </div>
</section>

<section class="referral-sec" id="referral">
  <div class="referral-inner">
    <div class="slbl">Referral Programme</div>
    <h2>Tell a friend. <em>Earn forever.</em></h2>
    <p style="font-size:15px;color:var(--muted);line-height:1.75;max-width:580px;margin:0 auto">When you sign up you get a referral code. Share it with anyone. Every device they sign up earns you 10p per month. Forever. No cap. No expiry.</p>
    <div class="ref-steps">
      <div class="rs">
        <div class="rs-icon">&#128272;</div>
        <h3>Sign up and get your code</h3>
        <p>When you sign up below you get a unique referral code instantly. It looks like REF-JOHN-1234. That code is yours forever.</p>
      </div>
      <div class="rs">
        <div class="rs-icon">&#128172;</div>
        <h3>Share it with anyone</h3>
        <p>Send it to a colleague, a tech mate, a call centre. Anyone who signs up using your code is linked to you permanently.</p>
        <div class="rs-earn">10p</div>
        <div class="rs-earn-label">per device per month forever</div>
      </div>
      <div class="rs">
        <div class="rs-icon">&#128176;</div>
        <h3>Earn every single month</h3>
        <p>10 referrals with 100 devices each means &pound;100 a month doing nothing. 10 referrals with 1,000 devices each means &pound;1,000 a month. Forever.</p>
      </div>
    </div>
  </div>
</section>

<section class="compliance-sec" id="compliance">
  <div class="sec-inner">
    <div class="slbl">The Law</div>
    <h2>What the law actually <em>requires.</em></h2>
    <p class="sec-sub">Most compliance officers will tell you what the law says. We will tell you what it means in practice and exactly what you need to have in place.</p>
    <div class="comp-grid">
      <div class="comp-card">
        <div class="comp-act">EU AI Act 2024/1689 &mdash; Enforcement August 2026</div>
        <div class="simple">In plain English: if your AI makes decisions that affect people, you need proof that every decision was fair, explainable and recorded permanently.</div>
        <p>The fine for getting this wrong is up to 3% of your global annual turnover or 15 million euros &mdash; whichever is higher. Per violation. Not per company. Per violation.</p>
        <div class="checks">
          <div class="chk">Article 9 &mdash; continuous risk management, not a one-time assessment</div>
          <div class="chk">Article 12 &mdash; tamper-evident audit chain that nobody can alter, not even you</div>
          <div class="chk">Article 13 &mdash; every decision explained in plain language automatically</div>
          <div class="chk">Article 14 &mdash; humans must be able to override high-risk decisions</div>
        </div>
      </div>
      <div class="comp-card">
        <div class="comp-act">Online Safety Act 2023 &mdash; UK &mdash; Already In Force</div>
        <div class="simple">In plain English: if users can talk to each other on your platform, especially children, you are legally responsible for protecting them. Right now. Not August 2026. Now.</div>
        <p>Ofcom is already investigating platforms. The ICO fined TikTok &pound;12.7 million for Children's Code violations. A moderation team and a report button is not enough.</p>
        <div class="checks">
          <div class="chk">Documented risk assessment that you can show Ofcom on demand</div>
          <div class="chk">Real-time content moderation with evidence trail</div>
          <div class="chk">Age-appropriate design for child users</div>
          <div class="chk">Ofcom-ready audit trails from every decision</div>
        </div>
      </div>
      <div class="comp-card">
        <div class="comp-act">ICO Children's Code &mdash; UK &mdash; Already In Force</div>
        <div class="simple">In plain English: if children under 18 can access your platform &mdash; even if you did not intend them to &mdash; the Children's Code applies to you. You must protect them by default, not as an afterthought.</div>
        <p>This is not optional. It is not a guideline. It is law. The ICO can and will fine you if children are exposed to harmful AI decisions on your platform without proper protection.</p>
        <div class="checks">
          <div class="chk">Best interests of the child applied by default</div>
          <div class="chk">Data minimisation for child users enforced automatically</div>
          <div class="chk">No profiling of children unless strictly necessary</div>
          <div class="chk">Human oversight of any automated decision affecting a child</div>
        </div>
      </div>
      <div class="comp-card">
        <div class="comp-act">Digital Services Act &mdash; EU 2022/2065</div>
        <div class="simple">In plain English: if you operate in Europe and have more than 45 million users, you are a Very Large Online Platform and the DSA applies to you in full. Even smaller platforms need to demonstrate systemic risk assessment.</div>
        <p>The DSA requires you to show exactly how your algorithmic systems work, prove you have assessed the risks they create, and demonstrate the steps you have taken to mitigate those risks.</p>
        <div class="checks">
          <div class="chk">Systemic risk assessment with documented evidence</div>
          <div class="chk">Algorithmic transparency reports for regulators</div>
          <div class="chk">Minor protection evidence packages</div>
          <div class="chk">Regulator-ready submissions at any time</div>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <div class="slbl" style="color:var(--navy)">Get Started</div>
    <h2>Free API key. <em>Right now.</em></h2>
    <p style="font-size:15px;color:var(--muted);line-height:1.7;margin-bottom:24px">Pick your product. Name and email. API key and referral code delivered instantly. 100 free decisions. No card required.</p>
    <div class="product-tabs">
      <button class="stab stab-al-on" id="tab-al" onclick="setProduct('aileash')">AILeash</button>
      <button class="stab" id="tab-gu" onclick="setProduct('guardian')">Guardian</button>
      <button class="stab" id="tab-sb" onclick="setProduct('sonicboom')">SonicBoom</button>
      <button class="stab" id="tab-se" onclick="setProduct('sentinel')">Sentinel</button>
    </div>
    <div class="fg-row">
      <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
      <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
    </div>
    <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
    <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
    <div class="fg"><label>Platform or Company Name</label><input type="text" id="org" placeholder="e.g. GameZone / Roblox / My Platform"></div>
    <div class="fg"><label>Estimated Devices</label>
      <select id="dv">
        <option value="100">Under 100</option>
        <option value="500">100 to 500</option>
        <option value="1000">500 to 1,000</option>
        <option value="5000">1,000 to 5,000</option>
        <option value="10000">5,000 to 10,000</option>
        <option value="50000">10,000 plus</option>
      </select>
    </div>
    <input class="ref-field" type="text" id="ref-code" placeholder="Referral code (optional) e.g. REF-JOHN-1234">
    <button class="btn-full" id="go-btn" style="background:var(--gold);color:var(--navy)" onclick="doSignup()">Get Free AILeash API Key &rarr;</button>
    <div class="msg-err" id="msg-err"></div>
    <div class="msg-ok" id="msg-ok"></div>
    <div class="key-box" id="key-box">
      <div class="key-lbl">Your API Key &mdash; Save This Now</div>
      <div class="key-val" id="key-val"></div>
      <div class="ref-box" id="ref-box">
        <div class="ref-box-label">Your Referral Code</div>
        <div class="ref-box-code" id="ref-code-display"></div>
        <div class="ref-box-desc">Share this with anyone. Every device they sign up earns you 10p per month forever. Check your earnings at <a href="/referrals" style="color:var(--gold)">sebbi.pro/referrals</a></div>
      </div>
      <div class="usage-box">
        <div><em>POST</em> https://sebbi.pro/api/govern</div>
        <div>Authorization: Bearer <em id="key-prev">YOUR_KEY</em></div>
        <div style="margin-top:6px;color:rgba(255,255,255,0.12)">100 free decisions &middot; 50p per device after trial &middot; Billed via Stripe</div>
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="foot-inner">
    <div>
      <div class="foot-logo">Monop <span>Content</span></div>
      <div class="foot-tag">Blyth, Northumberland, UK</div>
      <p class="foot-desc">Four AI compliance and safety products. Free to integrate. You set the margin. We take 50p per device per month. You keep the rest forever.</p>
    </div>
    <div class="foot-col"><h4>Products</h4>
      <a href="#products">AILeash</a>
      <a href="#products">Guardian</a>
      <a href="/sonicboom">SonicBoom</a>
      <a href="#products">Sentinel</a>
    </div>
    <div class="foot-col"><h4>Tools</h4>
      <a href="/scan">AI Act Scanner</a>
      <a href="/guardian-app">Guardian App</a>
      <a href="/reseller">Partner Programme</a>
      <a href="/report-threat">Report a Threat</a>
      <a href="/compliance-assistant">AI Assistant</a>
    </div>
    <div class="foot-col"><h4>Contact</h4>
      <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a>
      <a href="tel:07908269428">07908 269428</a>
      <a href="/contact">Send a Message</a>
      <a href="#signup">Get API Key</a>
      <a href="/referrals">My Referrals</a>
    </div>
  </div>
  <div class="foot-bottom">
    <span>&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK &middot; v6.0.0</span>
    <span>EU AI Act &middot; Online Safety Act &middot; ICO Children's Code &middot; DSA</span>
  </div>
</footer>

<!-- CHAT BUBBLE -->
<div class="chat-bubble">
  <button class="chat-btn" onclick="toggleChat()" title="Chat with us">&#128172;</button>
</div>
<div class="chat-window" id="chat-window">
  <div class="chat-header">
    <div class="chat-header-left">
      <h3>AILeash Assistant</h3>
      <p>Ask anything &middot; Or email Justin directly</p>
    </div>
    <button class="chat-close" onclick="toggleChat()">&times;</button>
  </div>
  <div class="chat-mode-tabs">
    <button class="cmt on" id="tab-ask" onclick="setMode('ask')">Ask a Question</button>
    <button class="cmt" id="tab-email" onclick="setMode('email')">Email Justin</button>
  </div>
  <div class="chat-msgs" id="chat-msgs">
    <div class="cm cm-ai">Hi. Ask me anything about AI compliance, child safety, the EU AI Act or any of our products. I will give you a straight answer.</div>
  </div>
  <div class="chat-email-form" id="chat-email-form">
    <div class="cef"><input type="text" id="ce-name" placeholder="Your name"></div>
    <div class="cef"><input type="email" id="ce-email" placeholder="Your email address"></div>
    <div class="cef"><textarea id="ce-msg" placeholder="Your message to Justin"></textarea></div>
    <button onclick="sendEmail()" style="background:var(--gold);color:var(--navy);border:none;padding:10px;border-radius:4px;font-weight:700;cursor:pointer;font-family:var(--sans);font-size:13px">Send to Justin &rarr;</button>
    <div id="ce-status" style="font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.4);margin-top:4px"></div>
  </div>
  <div class="chat-input-row" id="chat-input-row">
    <textarea class="chat-input" id="chat-input" placeholder="Ask anything..." rows="1" onkeydown="chatKey(event)" oninput="chatResize(this)"></textarea>
    <button class="chat-send" id="chat-send" onclick="chatSend()">&#8593;</button>
  </div>
</div>

<script>
var AP='aileash';
var chatMsgs=[];
var chatBusy=false;
var chatMode='ask';

var CHAT_SYS="You are the AILeash sales and compliance assistant on sebbi.pro, built by Justin Antony Dobson at Monop Content in Blyth UK. You know everything about the four products: AILeash (AI governance, EU AI Act Art 9/12/13/14), AILeash Guardian (child safety, grooming detection, CSAM block, Online Safety Act), SonicBoom (speed plugin for existing cloud AI), AILeash Sentinel (fraud and anomaly monitoring, real-time alerts). All products are free to integrate. We take 50p per device per month. Platforms set their own user price and keep the margin. Referral programme pays 10p per device per month. You are direct, helpful and knowledgeable. You explain compliance in plain English. You answer questions fully. You help people understand why they need these products and how to get started. When someone is ready, direct them to sign up at the form on this page. If they want to contact Justin directly, tell them to click the Email Justin tab above or email justin@monopcontent.com or call 07908 269428.";

function setProduct(p){
  AP=p;
  ['al','gu','sb','se'].forEach(function(t){document.getElementById('tab-'+t).className='stab';});
  document.getElementById('tab-'+{aileash:'al',guardian:'gu',sonicboom:'sb',sentinel:'se'}[p]).className='stab stab-'+{aileash:'al',guardian:'gu',sonicboom:'sb',sentinel:'se'}[p]+'-on';
  var btn=document.getElementById('go-btn');
  var labels={aileash:'Get Free AILeash API Key \u2192',guardian:'Get Free Guardian API Key \u2192',sonicboom:'Get Free SonicBoom Plugin \u2192',sentinel:'Get Free Sentinel API Key \u2192'};
  var colours={aileash:'var(--gold)',guardian:'var(--red)',sonicboom:'var(--cyan)',sentinel:'var(--purple)'};
  var textcols={aileash:'var(--navy)',guardian:'var(--white)',sonicboom:'var(--navy)',sentinel:'var(--white)'};
  btn.textContent=labels[p];btn.style.background=colours[p];btn.style.color=textcols[p];
}

function calc(){
  var charge=parseFloat(document.getElementById('charge').value)||0;
  var devices=parseInt(document.getElementById('devices').value)||0;
  document.getElementById('r-user').textContent='\u00a3'+charge.toFixed(2);
  document.getElementById('r-you').textContent='\u00a3'+Math.max(0,(charge-0.50)*devices).toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('r-we').textContent='\u00a3'+(0.50*devices).toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
}
calc();

async function doSignup(){
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var org=document.getElementById('org').value.trim();
  var dv=parseInt(document.getElementById('dv').value)||1;
  var rc=document.getElementById('ref-code').value.trim();
  var err=document.getElementById('msg-err');
  var ok=document.getElementById('msg-ok');
  var kb=document.getElementById('key-box');
  var btn=document.getElementById('go-btn');
  err.classList.remove('show');ok.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company name.';err.classList.add('show');return;}
  var orig=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('/signup',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:AP,product:AP==='guardian'?'guardian':'aileash',devices:dv,ref_code:rc})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      document.getElementById('key-prev').textContent=d.api_key.slice(0,20)+'...';
      if(d.ref_code){document.getElementById('ref-code-display').textContent=d.ref_code;document.getElementById('ref-box').style.display='block';}
      kb.classList.add('show');
      ok.textContent='Key created. 100 free decisions. Setting up billing\u2026';ok.classList.add('show');
      btn.textContent='Key Created \u2713';
      setTimeout(function(){
        fetch('/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({email:em,product:AP==='guardian'?'guardian':'aileash',devices:dv})
        }).then(function(r2){return r2.json();}).then(function(d2){
          if(d2.checkout_url){window.location.href=d2.checkout_url;}
          else{ok.textContent='Key ready. Justin will be in touch. justin@monopcontent.com';}
        }).catch(function(){ok.textContent='Key ready. Justin will be in touch. justin@monopcontent.com';});
      },2000);
    }else{err.textContent=d.error||'Something went wrong. Email justin@monopcontent.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
  }catch(e){err.textContent='Cannot reach server. Email justin@monopcontent.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
}

function toggleChat(){
  var w=document.getElementById('chat-window');
  w.classList.toggle('open');
}

function setMode(m){
  chatMode=m;
  document.getElementById('tab-ask').className='cmt'+(m==='ask'?' on':'');
  document.getElementById('tab-email').className='cmt'+(m==='email'?' on':'');
  document.getElementById('chat-msgs').style.display=m==='ask'?'flex':'none';
  document.getElementById('chat-input-row').style.display=m==='ask'?'flex':'none';
  document.getElementById('chat-email-form').className='chat-email-form'+(m==='email'?' show':'');
}

function chatResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,80)+'px';}

function chatKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();chatSend();}}

function addChatMsg(role,text){
  var msgs=document.getElementById('chat-msgs');
  var d=document.createElement('div');
  d.className='cm cm-'+role;
  d.textContent=text;
  msgs.appendChild(d);
  msgs.scrollTop=msgs.scrollHeight;
}

function showTyping(){
  var msgs=document.getElementById('chat-msgs');
  var d=document.createElement('div');
  d.id='chat-typing';d.className='cm-typing';
  d.innerHTML='<span></span><span></span><span></span>';
  msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;
}

function hideTyping(){var t=document.getElementById('chat-typing');if(t)t.remove();}

async function chatSend(){
  if(chatBusy)return;
  var inp=document.getElementById('chat-input');
  var q=inp.value.trim();
  if(!q)return;
  inp.value='';inp.style.height='auto';
  chatBusy=true;document.getElementById('chat-send').disabled=true;
  addChatMsg('user',q);
  chatMsgs.push({role:'user',content:q});
  showTyping();
  try{
    var r=await fetch('https://api.anthropic.com/v1/messages',{
      method:'POST',
      headers:{'Content-Type':'application/json','anthropic-version':'2023-06-01','anthropic-dangerous-direct-browser-access':'true'},
      body:JSON.stringify({model:'claude-sonnet-4-6',max_tokens:600,system:CHAT_SYS,messages:chatMsgs})
    });
    var data=await r.json();
    var reply=data.content&&data.content[0]?data.content[0].text:'Sorry I could not get a response. Email justin@monopcontent.com directly.';
    hideTyping();
    chatMsgs.push({role:'assistant',content:reply});
    addChatMsg('ai',reply);
  }catch(e){
    hideTyping();
    addChatMsg('ai','Having trouble connecting. Email justin@monopcontent.com or call 07908 269428.');
  }
  chatBusy=false;document.getElementById('chat-send').disabled=false;
}

async function sendEmail(){
  var name=document.getElementById('ce-name').value.trim();
  var email=document.getElementById('ce-email').value.trim();
  var msg=document.getElementById('ce-msg').value.trim();
  var status=document.getElementById('ce-status');
  if(!email||!email.includes('@')){status.textContent='Please enter your email.';return;}
  if(!msg){status.textContent='Please enter a message.';return;}
  status.textContent='Sending\u2026';
  try{
    var r=await fetch('/contact',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:name,email:email,message:msg,org:'Chat widget'})});
    var d=await r.json();
    if(d.ok){
      status.textContent='Sent. Justin will reply within 24 hours.';
      document.getElementById('ce-name').value='';
      document.getElementById('ce-email').value='';
      document.getElementById('ce-msg').value='';
    }else{status.textContent='Something went wrong. Email justin@monopcontent.com directly.';}
  }catch(e){status.textContent='Cannot reach server. Email justin@monopcontent.com directly.';}
}
</script>
</body>
</html>"""
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
        elif path=="/api/badge/status":
            # Live SVG badge — shows engine status
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                keys=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
            svg=f"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="20">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="200" height="20" fill="#555"/>
<rect rx="3" x="90" width="110" height="20" fill="#00875a"/>
<rect rx="3" width="200" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
<text x="45" y="15" fill="#010101" fill-opacity=".3">AILeash</text>
<text x="45" y="14">AILeash</text>
<text x="144" y="15" fill="#010101" fill-opacity=".3">LIVE {blocks} blocks</text>
<text x="144" y="14">LIVE {blocks} blocks</text>
</g></svg>"""
            body=svg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","image/svg+xml")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(body)

        elif path=="/api/badge/decision":
            # Live demo — scores a test event and returns SVG badge with real decision
            test_event={"user_id":"github_visitor","action":"readme_view","amount":0,"country":"UK","device_id":"github","anomaly":0.05,"device_risk":0.05}
            try:
                result,_=govern(test_event)
                dec=result.get("decision","ALLOW")
                score=result.get("score",0)
                colours={"ALLOW":"#00875a","CHALLENGE":"#b45309","BLOCK":"#cc0000"}
                colour=colours.get(dec,"#555")
                label=f"{dec} {score:.2f}"
            except:
                dec="ALLOW";colour="#00875a";label="ALLOW 0.18"
            svg=f"""<svg xmlns="http://www.w3.org/2000/svg" width="220" height="20">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="220" height="20" fill="#555"/>
<rect rx="3" x="100" width="120" height="20" fill="{colour}"/>
<rect rx="3" width="220" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
<text x="50" y="15" fill="#010101" fill-opacity=".3">Live Decision</text>
<text x="50" y="14">Live Decision</text>
<text x="159" y="15" fill="#010101" fill-opacity=".3">{label}</text>
<text x="159" y="14">{label}</text>
</g></svg>"""
            body=svg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","image/svg+xml")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(body)

        elif path=="/api/badge/chain":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            svg=f"""<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">
<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
<rect rx="3" width="180" height="20" fill="#555"/>
<rect rx="3" x="80" width="100" height="20" fill="#0a0f1e"/>
<rect rx="3" width="180" height="20" fill="url(#s)"/>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
<text x="40" y="15" fill="#010101" fill-opacity=".3">SHA-256</text>
<text x="40" y="14">SHA-256</text>
<text x="129" y="15" fill="#010101" fill-opacity=".3">{blocks} blocks</text>
<text x="129" y="14">{blocks} blocks</text>
</g></svg>"""
            body=svg.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","image/svg+xml")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-cache, no-store, must-revalidate")
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(body)

        elif path=="/compliance-assistant":
            c=load_file("compliance-assistant.html")
            send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/sentinel":
            c=load_file("sentinel.html")
            send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/referrals":
            code=urlparse(self.path).query.replace("code=","").strip()
            ref=get_referral(code) if code else None
            if ref:
                _,email,name,devices,earnings=ref
                html=f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Your Referrals</title>
<style>body{{font-family:'DM Sans',sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{max-width:480px;width:100%;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:36px;text-align:center}}
h1{{font-family:Georgia,serif;font-size:28px;color:#c9a84c;margin-bottom:8px}}
.stat{{font-size:48px;font-weight:900;color:#00ff88;margin:20px 0 4px;font-family:Georgia,serif}}
.stat-label{{font-size:11px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}}
.earn{{font-size:36px;font-weight:900;color:#c9a84c;font-family:Georgia,serif}}
p{{font-size:14px;color:rgba(255,255,255,0.4);line-height:1.7;margin-top:12px}}
</style></head><body><div class="box">
<h1>Your Referrals</h1>
<p>Welcome back, {name.split()[0] if name else 'there'}.</p>
<div class="stat">{devices}</div><div class="stat-label">Devices Referred</div>
<div class="earn">&pound;{earnings/100:.2f}</div><div class="stat-label">Earned This Month</div>
<p>You earn 10p per device per month. Keep sharing your code and watch it grow.<br><br>Questions? <a href="mailto:justin@monopcontent.com" style="color:#c9a84c">justin@monopcontent.com</a></p>
</div></body></html>"""
                send_html(self,html)
            else:
                send_html(self,"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Referrals</title>
<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;padding:20px}
h1{font-size:28px;color:#c9a84c;margin-bottom:12px}p{color:rgba(255,255,255,0.4);font-size:14px;line-height:1.7}
a{color:#c9a84c;text-decoration:none}</style></head><body>
<div><h1>Check Your Referral Earnings</h1>
<p>Sign up at <a href="https://sebbi.pro/#signup">sebbi.pro</a> to get your referral code.<br>
Then come back here with your code: <a href="/referrals?code=YOUR-CODE">sebbi.pro/referrals?code=YOUR-CODE</a><br><br>
Questions? <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a></p></div></body></html>""")
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
            ref_code_used=str(data.get("ref_code","")).strip().upper()
            if product not in("aileash","guardian"):product="aileash"
            key,err=create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email."}
                send_json(self,{"error":msgs.get(err,err)},400);return
            monthly=round(devices*0.50,2)
            if ref_code_used:
                threading.Thread(target=credit_referral,args=(ref_code_used,devices),daemon=True).start()
            new_ref_code=create_referral(key,email,name)
            threading.Thread(target=referral_welcome_email,args=(name,email,key,new_ref_code,product,monthly),daemon=True).start()
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"quota":FREE_QUOTA,"ref_code":new_ref_code,"endpoint":f"{HOST}/api/govern","message":f"100 free decisions. After trial: £{monthly}/month via Stripe."})

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
