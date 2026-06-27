# ==============================================================================
# AILEASH PLATFORM v6.0.0
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================

import json,math,time,sqlite3,hashlib,threading,random,string
import urllib.request,urllib.parse,os,secrets
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse,parse_qs

PORT=int(os.environ.get("PORT",8080))
STRIPE_SECRET=os.environ.get("STRIPE_SECRET","")
BREVO_API_KEY=os.environ.get("BREVO_API_KEY","")
HOST=os.environ.get("HOST","https://sebbi.pro")
DB="aileash.db"
VERSION="6.0.0"
OWNER_NAME="Justin Antony Dobson"
OWNER_EMAIL="justrightdecorators@gmail.com"
OWNER_PHONE="07908 269428"
SAFE={"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ={"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA=100
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","Racecar198066")
_admin_tokens=set()
STRIPE_PRICE_AL=""
STRIPE_PRICE_GU=""
STRIPE_PRICE_SB=""
STRIPE_PRICE_SE=""
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
    c.execute("CREATE TABLE IF NOT EXISTS referrals(code TEXT PRIMARY KEY,referrer_key TEXT,referrer_email TEXT,referrer_name TEXT,created REAL,devices_referred INTEGER DEFAULT 0,earnings_pence INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS threat_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,ref TEXT,data_json TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS waitlist(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,email TEXT,product TEXT,name TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_keys_email ON api_keys(email)")
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
    BREVO_KEY=os.environ.get("BREVO_API_KEY","").strip()
    if not BREVO_KEY:print("EMAIL SKIP:"+to_email,flush=True);return
    try:
        payload=json.dumps({"sender":{"name":"AILeash","email":"justrightdecorators@gmail.com"},"to":[{"email":to_email,"name":to_name}],"subject":subject,"htmlContent":html})
        req=urllib.request.Request("https://api.brevo.com/v3/smtp/email",
            data=payload.encode("utf-8"),
            headers={"api-key":str(BREVO_KEY),"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=15):pass
        print("EMAIL OK:"+to_email,flush=True)
    except Exception as e:print("EMAIL ERR:"+str(e),flush=True)

def send_referral_welcome(name,email,key,ref_code,product,monthly):
    pname={"guardian":"AILeash Guardian","sonicboom":"SonicBoom","sentinel":"AILeash Sentinel"}.get(product,"AILeash")
    html=(
        "<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'>"
        "<div style='max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'>"
        "<div style='background:#0a0f1e;padding:32px;border-bottom:4px solid #c9a84c'>"
        "<div style='font-size:22px;color:#fff;font-weight:900;font-family:Georgia,serif'>Monop <span style='color:#c9a84c'>Content</span></div>"
        "</div><div style='padding:36px'>"
        "<p style='font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:16px'>Welcome"+(", "+name.split()[0] if name.strip() else "")+".</p>"
        "<p style='font-size:14px;color:#64748b;line-height:1.7'>Your "+pname+" API key is ready. 100 free decisions included. After that it is 50p per device per month via Stripe.</p>"
        "<div style='background:#0a0f1e;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your API Key</div>"
        "<div style='font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all'>"+key+"</div>"
        "</div>"
        "<div style='background:#f8f5ee;border:2px solid #c9a84c;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your Referral Code</div>"
        "<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>"+ref_code+"</div>"
        "<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Share this code. Every device signed up earns you <strong>10p per month forever</strong>.</p>"
        "</div>"
        "<p style='font-size:13px;color:#64748b'>Questions? <a href='mailto:"+OWNER_EMAIL+"' style='color:#c9a84c'>"+OWNER_EMAIL+"</a> &middot; "+OWNER_PHONE+"</p>"
        "</div></div></body></html>"
    )
    send_email(email,name,"Your "+pname+" API Key + Referral Code",html)

def contact_email(name,email,phone,org,message):
    html=(
        "<html><body style='font-family:Arial,sans-serif;padding:20px;color:#333'>"
        "<h2>New Contact: "+name+"</h2>"
        "<p><b>Email:</b> "+email+"</p><p><b>Phone:</b> "+phone+"</p>"
        "<p><b>Org:</b> "+org+"</p><p><b>Message:</b><br>"+message+"</p>"
        "</body></html>"
    )
    send_email(OWNER_EMAIL,OWNER_NAME,"Contact: "+name,html)

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
    except Exception as e:print("Stripe:"+str(e),flush=True);return None

def make_price(name,desc):
    p=stripe_call("POST","/products",{"name":name,"description":desc})
    if not p or "id" not in p:return None
    pr=stripe_call("POST","/prices",{"product":p["id"],"currency":"gbp","unit_amount":50,"recurring[interval]":"month"})
    return pr["id"] if pr and "id" in pr else None

def setup_stripe():
    global STRIPE_PRICE_AL,STRIPE_PRICE_GU,STRIPE_PRICE_SB,STRIPE_PRICE_SE
    if not STRIPE_SECRET:print("No STRIPE_SECRET",flush=True);return
    products=[
        ("price_al","AILeash","AI governance. 50p per device per month."),
        ("price_gu","AILeash Guardian","Child safety. 50p per device per month."),
        ("price_sb","SonicBoom","Speed plugin. 50p per device per month."),
        ("price_se","AILeash Sentinel","Fraud detection. 50p per device per month."),
    ]
    for k,name,desc in products:
        with _db_lock:
            r=_conn.execute("SELECT v FROM config WHERE k=?",(k,)).fetchone()
        if r and r[0]:
            if k=="price_al":STRIPE_PRICE_AL=r[0]
            elif k=="price_gu":STRIPE_PRICE_GU=r[0]
            elif k=="price_sb":STRIPE_PRICE_SB=r[0]
            elif k=="price_se":STRIPE_PRICE_SE=r[0]
        else:
            pid=make_price(name,desc)
            if pid:
                with _db_lock:_conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES(?,?)",(k,pid));_conn.commit()
                if k=="price_al":STRIPE_PRICE_AL=pid
                elif k=="price_gu":STRIPE_PRICE_GU=pid
                elif k=="price_sb":STRIPE_PRICE_SB=pid
                elif k=="price_se":STRIPE_PRICE_SE=pid
    print("Stripe AL:"+str(STRIPE_PRICE_AL)[:12]+" GU:"+str(STRIPE_PRICE_GU)[:12]+" SB:"+str(STRIPE_PRICE_SB)[:12]+" SE:"+str(STRIPE_PRICE_SE)[:12],flush=True)

def get_stripe_price(product):
    return{"aileash":STRIPE_PRICE_AL,"guardian":STRIPE_PRICE_GU,"sonicboom":STRIPE_PRICE_SB,"sentinel":STRIPE_PRICE_SE}.get(product,STRIPE_PRICE_AL)

def create_key(email,phone="",name="",org="",org_type="",product="aileash",devices=1):
    email=str(email).strip().lower()
    if not email or "@" not in email:return None,"invalid_email"
    prefix={"guardian":"ag_live_","sonicboom":"sb_live_","sentinel":"se_live_"}.get(product,"al_live_")
    key=prefix+secrets.token_hex(24)
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

def gen_ref_code(name):
    prefix=("".join(c for c in name.upper().split()[0] if c.isalpha())[:4]).ljust(4,"X")
    suffix="".join(random.choices(string.digits,k=4))
    return "REF-"+prefix+"-"+suffix

def create_referral(key,email,name):
    code=gen_ref_code(name)
    with _db_lock:
        try:
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
        if sha(p)!=row[3] or row[2]!=prev:return{"valid":False,"broken_at":i,"message":"Tampered at block "+str(i)}
        prev=row[3]
    return{"valid":True,"blocks":len(rows),"tip":rows[-1][3],"message":"Chain intact"}

def govern(event,api_key=None):
    missing=REQ-event.keys()
    if missing:raise ValueError("Missing fields: "+str(missing))
    if api_key:
        ok,ec=check_rate(api_key)
        if not ok:return{"error":ec},429
        ki=get_key(api_key)
        if not ki:return{"error":"invalid_api_key"},401
        email,used,active,is_paid,quota,plan,product=ki
        if not active:return{"error":"account_inactive"},403
        if not is_paid and used>=quota:return{"error":"quota_exceeded","message":"Upgrade at "+HOST+"/#pricing"},429
    ts=now();uid=event["user_id"]
    state=load_user(uid);upd_vel(uid);v=vel(uid)
    country=event["country"]
    signals={
        "trust":state["trust"],"v60":v["60s"],"v5m":v["5m"],"v1h":v["1h"],
        "amount":float(event.get("amount",0)),"device_risk":float(event.get("device_risk",0)),
        "anomaly":float(event.get("anomaly",0)),
        "country_shift":state["last_country"] is not None and state["last_country"]!=country,
        "unsafe_country":country not in SAFE
    }
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
    h.send_header("X-Content-Type-Options","nosniff")
    h.end_headers()
    h.wfile.write(body)

def send_html(h,html,status=200):
    body=html.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type","text/html; charset=utf-8")
    h.send_header("Content-Length",str(len(body)))
    h.send_header("X-Frame-Options","SAMEORIGIN")
    h.end_headers()
    h.wfile.write(body)

def send_text(h,text,content_type="text/plain",status=200):
    body=text.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type",content_type)
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

def page_404():
    return (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'><title>Not Found</title>"
        "<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;"
        "align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center}"
        "h1{color:#c9a84c;font-size:48px;margin-bottom:8px}"
        "p{color:rgba(255,255,255,0.4);font-size:14px}"
        "a{color:#c9a84c;text-decoration:none}</style></head>"
        "<body><div><h1>404</h1><p>Page not found.</p>"
        "<p style='margin-top:16px'><a href='/'>Back to AILeash &rarr;</a></p>"
        "</div></body></html>"
    )

def badge_svg(label,value,colour):
    lw=len(label)*7+16
    vw=len(value)*7+16
    total=lw+vw
    body=(
        "<svg xmlns='http://www.w3.org/2000/svg' width='"+str(total)+"' height='20'>"
        "<linearGradient id='s' x2='0' y2='100%'><stop offset='0' stop-color='#bbb' stop-opacity='.1'/><stop offset='1' stop-opacity='.1'/></linearGradient>"
        "<rect rx='3' width='"+str(total)+"' height='20' fill='#555'/>"
        "<rect rx='3' x='"+str(lw)+"' width='"+str(vw)+"' height='20' fill='"+colour+"'/>"
        "<rect rx='3' width='"+str(total)+"' height='20' fill='url(#s)'/>"
        "<g fill='#fff' text-anchor='middle' font-family='DejaVu Sans,Verdana,Geneva,sans-serif' font-size='11'>"
        "<text x='"+str(lw//2)+"' y='15' fill='#010101' fill-opacity='.3'>"+label+"</text>"
        "<text x='"+str(lw//2)+"' y='14'>"+label+"</text>"
        "<text x='"+str(lw+vw//2)+"' y='15' fill='#010101' fill-opacity='.3'>"+value+"</text>"
        "<text x='"+str(lw+vw//2)+"' y='14'>"+value+"</text>"
        "</g></svg>"
    )
    return body

def send_svg(h,svg):
    body=svg.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type","image/svg+xml")
    h.send_header("Content-Length",str(len(body)))
    h.send_header("Cache-Control","no-cache, no-store, must-revalidate")
    h.send_header("Access-Control-Allow-Origin","*")
    h.end_headers()
    h.wfile.write(body)

def referrals_page(code):
    ref=get_referral(code) if code else None
    if ref:
        _,email,name,devices,earnings=ref
        first=name.split()[0] if name else "there"
        return (
            "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
            "<title>Your Referrals</title>"
            "<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;"
            "align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px}"
            ".box{max-width:480px;width:100%;background:rgba(255,255,255,0.04);"
            "border:1px solid rgba(255,255,255,0.08);border-radius:12px;padding:36px;text-align:center}"
            "h1{font-family:Georgia,serif;font-size:28px;color:#c9a84c;margin-bottom:8px}"
            ".stat{font-size:48px;font-weight:900;color:#00ff88;margin:20px 0 4px;font-family:Georgia,serif}"
            ".lbl{font-size:11px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:20px}"
            ".earn{font-size:36px;font-weight:900;color:#c9a84c;font-family:Georgia,serif}"
            "p{font-size:14px;color:rgba(255,255,255,0.4);line-height:1.7;margin-top:12px}"
            "a{color:#c9a84c;text-decoration:none}</style></head>"
            "<body><div class='box'>"
            "<h1>Your Referrals</h1><p>Welcome back, "+first+".</p>"
            "<div class='stat'>"+str(devices)+"</div><div class='lbl'>Devices Referred</div>"
            "<div class='earn'>&pound;"+"{:.2f}".format(earnings/100)+"</div>"
            "<div class='lbl'>Earned This Month</div>"
            "<p>10p per device per month. Keep sharing.<br><br>"
            "Questions? <a href='mailto:"+OWNER_EMAIL+"'>"+OWNER_EMAIL+"</a></p>"
            "</div></body></html>"
        )
    return (
        "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        "<title>Referrals</title>"
        "<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;"
        "align-items:center;justify-content:center;min-height:100vh;margin:0;text-align:center;padding:20px}"
        "h1{font-size:28px;color:#c9a84c;margin-bottom:12px}"
        "p{color:rgba(255,255,255,0.4);font-size:14px;line-height:1.7}"
        "a{color:#c9a84c;text-decoration:none}</style></head><body>"
        "<div><h1>Check Your Referral Earnings</h1>"
        "<p>Sign up at <a href='https://sebbi.pro/#signup'>sebbi.pro</a> to get your referral code.<br>"
        "Then return here: <a href='/referrals?code=YOUR-CODE'>sebbi.pro/referrals?code=YOUR-CODE</a><br><br>"
        "Questions? <a href='mailto:"+OWNER_EMAIL+"'>"+OWNER_EMAIL+"</a></p>"
        "</div></body></html>"
    )

HOMEPAGE=load_file("index.html") or ""

class ThreadedServer(__import__('socketserver').ThreadingMixIn,__import__('http.server',fromlist=['HTTPServer']).HTTPServer):
    allow_reuse_address=True
    daemon_threads=True

class Handler(__import__('http.server',fromlist=['BaseHTTPRequestHandler']).BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type,Authorization,X-API-Key")
        self.end_headers()

    def do_GET(self):
        parsed=urlparse(self.path)
        path=parsed.path
        if path.endswith("/") and path!="/":path=path.rstrip("/")
        qs=parse_qs(parsed.query)
        track_request()

        if path=="/mM_hYELAWL0vrzIvAnKRBlUnN1kM-H656cmjMrFT-3U.html":
            send_text(self,"google-site-verification: mM_hYELAWL0vrzIvAnKRBlUnN1kM-H656cmjMrFT-3U","text/html")
            return

        if path=="/":
            send_html(self,HOMEPAGE)
        elif path=="/scan":
            c=load_file("scan.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/contact":
            c=load_file("contact.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-app":
            c=load_file("guardian-app.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-parent":
            c=load_file("guardian-parent.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-child":
            c=load_file("guardian-child.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/sonicboom":
            c=load_file("sonicboom.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path in("/reseller","/partners"):
            c=load_file("reseller.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/report-threat":
            c=load_file("report-threat.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/compliance-assistant":
            c=load_file("compliance-assistant.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/sentinel":
            c=load_file("sentinel.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/whitepaper":
            c=load_file("whitepaper.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/developers":
            c=load_file("developers.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/ai-standard":
            c=load_file("ai-standard.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/ai.txt":
            c=load_file("ai.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/certificate":
            c=load_file("certificate.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/registry":
            c=load_file("registry.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/aileash-compliance.zip":
            try:
                with open("aileash-compliance.zip","rb") as f:body=f.read()
                self.send_response(200)
                self.send_header("Content-Type","application/zip")
                self.send_header("Content-Disposition",'attachment; filename="aileash-compliance.zip"')
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except:send_json(self,{"error":"not found"},404)
        elif path=="/admin":
            c=load_file("admin.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/referrals":
            code=qs.get("code",[""])[0].strip().upper()
            send_html(self,referrals_page(code))
        elif path in("/dashboard","/pricing","/docs","/blog","/status","/about","/legal","/privacy","/terms"):
            name=path.lstrip("/")+".html"
            c=load_file(name)
            if c:send_html(self,c)
            else:send_json(self,{"status":"coming_soon","route":path},200)
        elif path=="/download/engine":
            api_key=get_bearer(self)
            ki=get_key(api_key) if api_key else None
            if not ki:
                send_html(self,"<html><body style='font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;justify-content:center;min-height:100vh'><div style='text-align:center;padding:40px'><h1 style='color:#c9a84c;margin-bottom:16px'>Engine Download</h1><p style='color:rgba(255,255,255,0.5);margin-bottom:24px'>Valid API key required.</p><a href='https://sebbi.pro/#signup' style='background:#c9a84c;color:#0a0f1e;padding:14px 28px;text-decoration:none;border-radius:4px;font-weight:700'>Get API Key</a></div></body></html>",401)
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
        elif path=="/api/health":
            send_json(self,{"status":"ok","version":VERSION,"rps":get_rps()})
        elif path=="/api/verify-chain":
            send_json(self,verify_chain())
        elif path=="/api/stats":
            with _db_lock:
                keys=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                paid=_conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_paid=1").fetchone()[0]
                audits=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_json(self,{"api_keys":keys,"paid_keys":paid,"audit_blocks":audits,"rps":get_rps(),"version":VERSION})
        elif path=="/api/validate-engine":
            send_json(self,{"error":"method_not_allowed"},405)
        elif path=="/api/badge/status":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_svg(self,badge_svg("AILeash","LIVE "+str(blocks)+" blocks","#00875a"))
        elif path=="/api/badge/decision":
            test={"user_id":"github_visitor","action":"readme_view","amount":0,"country":"UK","device_id":"github","anomaly":0.05,"device_risk":0.05}
            try:
                result,_=govern(test)
                dec=result.get("decision","ALLOW")
                sc=result.get("score",0)
                colours={"ALLOW":"#00875a","CHALLENGE":"#b45309","BLOCK":"#cc0000"}
                send_svg(self,badge_svg("Live Decision",dec+" "+str(round(sc,2)),colours.get(dec,"#555")))
            except:
                send_svg(self,badge_svg("Live Decision","ALLOW 0.18","#00875a"))
        elif path=="/api/badge/chain":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_svg(self,badge_svg("SHA-256",str(blocks)+" blocks","#0a0f1e"))
        elif path=="/robots.txt":
            c=load_file("robots.txt");send_text(self,c) if c else send_text(self,"User-agent: *\nAllow: /\nSitemap: https://sebbi.pro/sitemap.xml\n")
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
            send_html(self,page_404(),404)

    def do_POST(self):
        parsed=urlparse(self.path)
        path=parsed.path.rstrip("/")
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
            if product not in("aileash","guardian","sonicboom","sentinel"):product="aileash"
            key,err=create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email."}
                send_json(self,{"error":msgs.get(err,err)},400);return
            monthly=round(devices*0.50,2)
            if ref_code_used:
                threading.Thread(target=credit_referral,args=(ref_code_used,devices),daemon=True).start()
            new_ref_code=create_referral(key,email,name)
            threading.Thread(target=send_referral_welcome,args=(name,email,key,new_ref_code,product,monthly),daemon=True).start()
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"quota":FREE_QUOTA,"ref_code":new_ref_code,"endpoint":HOST+"/api/govern","message":"100 free decisions. After trial: \u00a3"+str(monthly)+"/month via Stripe."})
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
        elif path=="/create-checkout":
            email=str(data.get("email","")).strip().lower()
            product=str(data.get("product","aileash")).strip().lower()
            devices=max(1,int(data.get("devices",1)))
            if not email or "@" not in email:send_json(self,{"error":"invalid_email"},400);return
            if not STRIPE_SECRET:send_json(self,{"error":"stripe_not_configured"},503);return
            pid=get_stripe_price(product)
            if not pid:setup_stripe();pid=get_stripe_price(product)
            if not pid:send_json(self,{"error":"stripe_setup_failed"},503);return
            session=stripe_call("POST","/checkout/sessions",{
                "mode":"subscription",
                "customer_email":email,
                "success_url":HOST+"/?success=true",
                "cancel_url":HOST+"/?cancel=true",
                "line_items[0][price]":pid,
                "line_items[0][quantity]":str(devices)
            })
            if not session or "url" not in session:send_json(self,{"error":"checkout_failed"},500);return
            send_json(self,{"checkout_url":session["url"]})
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
                        print("PAID:"+email,flush=True)
                elif etype in("customer.subscription.deleted","invoice.payment_failed"):
                    email=obj.get("customer_email","")
                    if email:
                        email=email.strip().lower()
                        with _db_lock:_conn.execute("UPDATE api_keys SET is_paid=0,plan_type='free' WHERE email=?",(email,));_conn.commit()
                        print("UNPAID:"+email,flush=True)
                send_json(self,{"ok":True})
            except Exception as e:print("Webhook:"+str(e),flush=True);send_json(self,{"ok":True})
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
        elif path=="/report-threat":
            ref="AIDX-"+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:12].upper()
            with _db_lock:
                _conn.execute("INSERT INTO threat_log(ts,ref,data_json) VALUES(?,?,?)",(time.time(),ref,json.dumps(data)))
                _conn.commit()
            html="<html><body style='font-family:Arial,sans-serif;padding:20px'><h2 style='color:#cc0000'>THREAT REPORT: "+ref+"</h2><pre style='background:#f5f5f5;padding:16px;border-radius:4px'>"+json.dumps(data,indent=2)+"</pre></body></html>"
            threading.Thread(target=send_email,args=(OWNER_EMAIL,OWNER_NAME,"THREAT REPORT: "+ref,html),daemon=True).start()
            send_json(self,{"ok":True,"reference":ref})
        elif path=="/waitlist":
            email=str(data.get("email","")).strip().lower()
            product=str(data.get("product","")).strip()
            name=str(data.get("name","")).strip()
            if not email or "@" not in email:send_json(self,{"error":"invalid_email"},400);return
            with _db_lock:
                _conn.execute("INSERT INTO waitlist(ts,email,product,name) VALUES(?,?,?,?)",(time.time(),email,product,name))
                _conn.commit()
            send_json(self,{"ok":True,"message":"You are on the waitlist. We will be in touch."})
        elif path=="/admin/auth":
            pw=str(data.get("password","")).strip()
            if pw==ADMIN_PASSWORD:
                tok=secrets.token_hex(32)
                _admin_tokens.add(tok)
                send_json(self,{"token":tok})
            else:
                send_json(self,{"error":"invalid_password"},401)
        elif path=="/admin/forgot":
            email=str(data.get("email","")).strip().lower()
            if email==OWNER_EMAIL.lower():
                html=("<html><body style='font-family:Arial,sans-serif;padding:20px'>"
                    "<h2 style='color:#c9a84c'>AILeash Admin Password Reset</h2>"
                    "<p>Your admin password is set via the ADMIN_PASSWORD environment variable on Railway.</p>"
                    "<p>To reset: Railway dashboard &rarr; Variables &rarr; update ADMIN_PASSWORD.</p>"
                    "</body></html>")
                threading.Thread(target=send_email,args=(OWNER_EMAIL,OWNER_NAME,"AILeash Admin Password Reset",html),daemon=True).start()
            send_json(self,{"ok":True})
        elif path=="/admin/stats":
            auth=get_bearer(self)
            if auth not in _admin_tokens:send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                total=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                paid=_conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_paid=1").fetchone()[0]
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            chain=verify_chain()
            send_json(self,{"total_keys":total,"paid_keys":paid,"audit_blocks":blocks,"chain_valid":chain["valid"]})
        elif path=="/admin/keys":
            auth=get_bearer(self)
            if auth not in _admin_tokens:send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT key,email,name,org,product,devices,actions_used,free_quota,is_paid,plan_type,created FROM api_keys ORDER BY created DESC").fetchall()
            keys=[{"key":r[0],"email":r[1],"name":r[2],"org":r[3],"product":r[4],"devices":r[5],"actions_used":r[6],"free_quota":r[7],"is_paid":r[8],"plan_type":r[9],"created":r[10]} for r in rows]
            send_json(self,{"keys":keys})
        elif path=="/admin/referrals":
            auth=get_bearer(self)
            if auth not in _admin_tokens:send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT code,referrer_email,referrer_name,devices_referred,earnings_pence,created FROM referrals ORDER BY created DESC").fetchall()
            refs=[{"code":r[0],"referrer_email":r[1],"referrer_name":r[2],"devices_referred":r[3],"earnings_pence":r[4],"created":r[5]} for r in rows]
            send_json(self,{"referrals":refs})
        elif path=="/admin/contacts":
            auth=get_bearer(self)
            if auth not in _admin_tokens:send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT ts,name,email,phone,org,message FROM contact_log ORDER BY ts DESC").fetchall()
            contacts=[{"ts":r[0],"name":r[1],"email":r[2],"phone":r[3],"org":r[4],"message":r[5]} for r in rows]
            send_json(self,{"contacts":contacts})
        else:
            send_json(self,{"error":"not_found"},404)

if __name__=="__main__":
    print("AILeash Platform v"+VERSION+" starting on :"+str(PORT),flush=True)
    setup_stripe()
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print("Ready.",flush=True)
    server.serve_forever()
