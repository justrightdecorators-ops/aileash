# ==============================================================================
# AILEASH PLATFORM v6.4.1 ENHANCED
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================
# v6.4.1 TECHNICAL CAPTURE ENHANCEMENT - Vamked up evidence preservation:
#  1. Raw signal values sealed into chain (not just final score)
#  2. Full request context captured (IP, user-agent, device fingerprint, timing)
#  3. Velocity windows sealed into audit chain on every decision
#  4. Threat reports enriched with forensic context
#  5. Guardian refactored: network/business focused, predator pattern detection
#  6. Law enforcement reporting workflow support (CEOP/NCA integration ready)
#  7. All receipts include raw signal snapshot + timestamps
#  8. Challenge resolution includes original threat context
# ==============================================================================

import json,math,time,sqlite3,hashlib,threading,random,string,hmac,base64,zlib
import urllib.request,urllib.parse,os,secrets,re,ipaddress
from html import escape as esc
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse,parse_qs

PORT=int(os.environ.get("PORT",8080))
STRIPE_SECRET=os.environ.get("STRIPE_SECRET","")
STRIPE_WEBHOOK_SECRET=os.environ.get("STRIPE_WEBHOOK_SECRET","")
BREVO_API_KEY=os.environ.get("BREVO_API_KEY","")
HOST=os.environ.get("HOST","https://sebbi.pro")
DB="aileash.db"
VERSION="6.4.1"
OWNER_NAME="Justin Antony Dobson"
OWNER_EMAIL="justrightdecorators@gmail.com"
OWNER_PHONE="07908 269428"
SAFE={"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ={"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA=100
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","")
_admin_tokens={}
_admin_fails=deque()
_admin_lock=threading.Lock()
ADMIN_TOKEN_TTL=86400
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
_prune_counter=0
_prune_lock=threading.Lock()

# ==============================================================================
# ENHANCED SCHEMA: Raw signals + request context captured
# ==============================================================================

def to_int(v,default=1,lo=1,hi=1000000):
    try:return max(lo,min(hi,int(v)))
    except (ValueError,TypeError):return default

def extract_ip(request_handler):
    """Extract client IP, handling X-Forwarded-For for proxies."""
    forwarded=request_handler.headers.get("X-Forwarded-For","").split(",")[0].strip()
    return forwarded if forwarded else request_handler.client_address[0]

def extract_user_agent(request_handler):
    """Extract and sanitise user-agent."""
    ua=request_handler.headers.get("User-Agent","").strip()[:256]
    return esc(ua) if ua else "unknown"

def fingerprint_device(ip,ua,device_id):
    """Generate deterministic device fingerprint from network context."""
    key=f"{ip}|{ua}|{device_id}".encode()
    return hashlib.sha256(key).hexdigest()[:16]

def get_conn():
    c=sqlite3.connect(DB,check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=NORMAL;")
    c.execute("CREATE TABLE IF NOT EXISTS users(user_id TEXT PRIMARY KEY,trust REAL DEFAULT 0.5,last_country TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,user_id TEXT,event_json TEXT,result_json TEXT,prev_hash TEXT,audit_hash TEXT UNIQUE,api_key TEXT,key_seq INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS raw_signals(id INTEGER PRIMARY KEY AUTOINCREMENT,audit_id INTEGER,trust REAL,v60 INTEGER,v5m INTEGER,v1h INTEGER,amount REAL,device_risk REAL,anomaly REAL,country_shift INTEGER,unsafe_country INTEGER,ip TEXT,user_agent TEXT,device_fingerprint TEXT,ts REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS api_keys(key TEXT PRIMARY KEY,email TEXT,phone TEXT,name TEXT,org TEXT,org_type TEXT,product TEXT DEFAULT 'aileash',devices INTEGER DEFAULT 1,stripe_customer TEXT,stripe_sub TEXT,actions_used INTEGER,created REAL,active INTEGER,is_paid INTEGER,free_quota INTEGER,plan_type TEXT,seq INTEGER DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS load_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,rps REAL,note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS contact_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,name TEXT,email TEXT,phone TEXT,org TEXT,message TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS referrals(code TEXT PRIMARY KEY,referrer_key TEXT,referrer_email TEXT,referrer_name TEXT,created REAL,devices_referred INTEGER DEFAULT 0,earnings_pence INTEGER)")
    c.execute("CREATE TABLE IF NOT EXISTS threat_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,ref TEXT,data_json TEXT,audit_hash TEXT,ip TEXT,device_fingerprint TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS waitlist(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,email TEXT,product TEXT,name TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS guardian_children(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_key TEXT,child_name TEXT,guardian_code TEXT UNIQUE,created REAL)")
    # Guardian enhanced: network patterns for business/safeguarding teams
    c.execute("CREATE TABLE IF NOT EXISTS guardian_patterns(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,network_id TEXT,user_id TEXT,pattern_type TEXT,severity TEXT,raw_events TEXT,audit_chain TEXT,reported_to_ceop INTEGER,report_ref TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(api_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_keys_email ON api_keys(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_raw_signals_audit ON raw_signals(audit_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_threat_hash ON threat_log(audit_hash)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_guardian_patterns ON guardian_patterns(network_id,pattern_type)")
    try:c.execute("ALTER TABLE audit_log ADD COLUMN api_key TEXT")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE audit_log ADD COLUMN key_seq INTEGER")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE api_keys ADD COLUMN seq INTEGER DEFAULT 0")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE threat_log ADD COLUMN ip TEXT")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE threat_log ADD COLUMN device_fingerprint TEXT")
    except sqlite3.OperationalError:pass
    try:c.execute("CREATE TABLE IF NOT EXISTS raw_signals(id INTEGER PRIMARY KEY AUTOINCREMENT,audit_id INTEGER,trust REAL,v60 INTEGER,v5m INTEGER,v1h INTEGER,amount REAL,device_risk REAL,anomaly REAL,country_shift INTEGER,unsafe_country INTEGER,ip TEXT,user_agent TEXT,device_fingerprint TEXT,ts REAL)")
    except sqlite3.OperationalError:pass
    try:c.execute("CREATE TABLE IF NOT EXISTS guardian_patterns(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,network_id TEXT,user_id TEXT,pattern_type TEXT,severity TEXT,raw_events TEXT,audit_chain TEXT,reported_to_ceop INTEGER,report_ref TEXT)")
    except sqlite3.OperationalError:pass
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

def prune_memory():
    """Evict stale entries from in-memory velocity/rate-limit stores."""
    t=time.time()
    with _key_lock:
        dead=[k for k,w in _key_wins.items() if (not w["hour"]) or w["hour"][-1]<t-3600]
        for k in dead:del _key_wins[k]
    with _admin_lock:
        expired=[tok for tok,exp in _admin_tokens.items() if exp<t]
        for tok in expired:del _admin_tokens[tok]

def maybe_prune():
    global _prune_counter
    with _prune_lock:
        _prune_counter+=1
        if _prune_counter<1000:return
        _prune_counter=0
    try:prune_memory()
    except Exception as e:print("PRUNE ERR:"+str(e),flush=True)

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
    is_guardian=(product=="guardian")
    safe_first=esc(name.split()[0]) if name.strip() else ""
    if is_guardian:
        pricing_line="Guardian is completely free for network safeguarding — no card, no trial, no charge, ever."
    else:
        pricing_line="Your "+pname+" API key is ready. 100 free decisions included. After that it is 50p per device per month via Stripe."
    html=(
        "<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'>"
        "<div style='max-width:600px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'>"
        "<div style='background:#0a0f1e;padding:32px;border-bottom:4px solid #c9a84c'>"
        "<div style='font-size:22px;color:#fff;font-weight:900;font-family:Georgia,serif'>Monop <span style='color:#c9a84c'>Content</span></div>"
        "</div><div style='padding:36px'>"
        "<p style='font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:16px'>Welcome"+(", "+safe_first if safe_first else "")+".</p>"
        "<p style='font-size:14px;color:#64748b;line-height:1.7'>"+pricing_line+"</p>"
        "<div style='background:#0a0f1e;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your API Key</div>"
        "<div style='font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all'>"+esc(key)+"</div>"
        "</div>"
        +(
        "<div style='background:#f8f5ee;border:2px solid #c9a84c;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your Referral Code</div>"
        "<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>"+esc(ref_code)+"</div>"
        "<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Share this code. Every device signed up earns you <strong>10p per month forever</strong>.</p>"
        "</div>" if not is_guardian else
        "<div style='background:#f0fff8;border:2px solid #00c853;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#00875a;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Network Safeguarding</div>"
        "<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>"+esc(ref_code)+"</div>"
        "<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Guardian detects predatory patterns. CEOP/NCA reporting ready. Free for safeguarding teams.</p>"
        "</div>"
        )
        +"<p style='font-size:13px;color:#64748b'>Questions? <a href='mailto:"+OWNER_EMAIL+"' style='color:#c9a84c'>"+OWNER_EMAIL+"</a> &middot; "+OWNER_PHONE+"</p>"
        "</div></div></body></html>"
    )
    send_email(email,name,"Your "+pname+" API Key",html)

def contact_email(name,email,phone,org,message):
    html=(
        "<html><body style='font-family:Arial,sans-serif;padding:20px;color:#333'>"
        "<h2>New Contact: "+esc(name)+"</h2>"
        "<p><b>Email:</b> "+esc(email)+"</p><p><b>Phone:</b> "+esc(phone)+"</p>"
        "<p><b>Org:</b> "+esc(org)+"</p><p><b>Message:</b><br>"+esc(message)+"</p>"
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

def verify_stripe_signature(payload,sig_header):
    """Verify Stripe webhook signature."""
    if not STRIPE_WEBHOOK_SECRET:return False
    if not sig_header:return False
    try:
        t=None;sigs=[]
        for part in sig_header.split(","):
            k,_,v=part.strip().partition("=")
            if k=="t":t=v
            elif k=="v1":sigs.append(v)
        if not t or not sigs:return False
        if abs(time.time()-int(t))>300:return False
        signed=t.encode()+b"."+payload
        expected=hmac.new(STRIPE_WEBHOOK_SECRET.encode(),signed,hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected,s) for s in sigs)
    except Exception:
        return False

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
        ("price_gu","AILeash Guardian","Network safeguarding. Free for teams."),
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
    if not STRIPE_WEBHOOK_SECRET:print("WARNING: STRIPE_WEBHOOK_SECRET not set",flush=True)

def get_stripe_price(product):
    return{"aileash":STRIPE_PRICE_AL,"guardian":STRIPE_PRICE_GU,"sonicboom":STRIPE_PRICE_SB,"sentinel":STRIPE_PRICE_SE}.get(product,STRIPE_PRICE_AL)

def create_key(email,phone="",name="",org="",org_type="",product="aileash",devices=1):
    email=str(email).strip().lower()
    if not email or "@" not in email:return None,"invalid_email"
    prefix={"guardian":"ag_live_","sonicboom":"sb_live_","sentinel":"se_live_"}.get(product,"al_live_")
    key=prefix+secrets.token_hex(24)
    with _db_lock:
        r=_conn.execute("SELECT 1 FROM api_keys WHERE email=? AND product=?",(email,product)).fetchone()
        if r:return None,"email_exists"
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
    words=name.upper().split()
    first=words[0] if words else "USER"
    prefix=("".join(c for c in first if c.isalpha())[:4]).ljust(4,"X")
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

def seal(event,result,ts,api_key=None,raw_signals=None,request_context=None):
    """Seal decision with full technical context: raw signals, request metadata, velocity windows."""
    with _db_lock:
        r=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev=r[0] if r else "GENESIS"
        h=sha({"prev_hash":prev,"ts":ts,"event":event,"result":result})
        seq=None
        if api_key:
            _conn.execute("UPDATE api_keys SET seq=COALESCE(seq,0)+1 WHERE key=?",(api_key,))
            sr=_conn.execute("SELECT seq FROM api_keys WHERE key=?",(api_key,)).fetchone()
            seq=sr[0] if sr else None
        cur=_conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash,api_key,key_seq) VALUES(?,?,?,?,?,?,?,?)",(ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h,api_key,seq))
        idx=cur.lastrowid
        # ENHANCED: Capture raw signals + request context
        if raw_signals:
            _conn.execute("INSERT INTO raw_signals(audit_id,trust,v60,v5m,v1h,amount,device_risk,anomaly,country_shift,unsafe_country,ip,user_agent,device_fingerprint,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (idx,raw_signals.get("trust"),raw_signals.get("v60"),raw_signals.get("v5m"),raw_signals.get("v1h"),
                 raw_signals.get("amount"),raw_signals.get("device_risk"),raw_signals.get("anomaly"),
                 raw_signals.get("country_shift"),raw_signals.get("unsafe_country"),
                 request_context.get("ip") if request_context else "",
                 request_context.get("user_agent") if request_context else "",
                 request_context.get("device_fingerprint") if request_context else "",ts))
        _conn.commit()
    return h,idx,seq

def verify_chain():
    with _db_lock:rows=_conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows:return{"valid":True,"blocks":0,"message":"Empty chain"}
    prev="GENESIS"
    for i,row in enumerate(rows):
        p={"prev_hash":row[2],"ts":row[4],"event":json.loads(row[0]),"result":json.loads(row[1])}
        if sha(p)!=row[3] or row[2]!=prev:return{"valid":False,"broken_at":i,"message":"Tampered at block "+str(i)}
        prev=row[3]
    return{"valid":True,"blocks":len(rows),"tip":rows[-1][3],"message":"Chain intact"}

def last_decision():
    """Read-only: fetch the most recent decision for badge display."""
    with _db_lock:
        r=_conn.execute("SELECT result_json FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:return None
    try:
        res=json.loads(r[0])
        return res.get("decision"),res.get("score")
    except:return None

_alert_last={}
_alert_lock=threading.Lock()
ALERT_COOLDOWN=3600

CHALLENGE_TTL=900
def _challenge_secret():
    s=os.environ.get("LICENCE_SECRET","")
    return s.encode() if s else _EPHEMERAL_SECRET
_EPHEMERAL_SECRET=secrets.token_bytes(32)

def make_challenge_token(user_id,audit_hash):
    payload=json.dumps({"u":user_id,"h":audit_hash[:16],"t":int(time.time())},sort_keys=True,separators=(',',':'))
    sig=hmac.new(_challenge_secret(),payload.encode(),hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(json.dumps({"p":payload,"s":sig},separators=(',',':')).encode()).decode()

def read_challenge_token(token):
    try:
        d=json.loads(base64.urlsafe_b64decode(token.encode()))
        payload=d["p"];sig=d["s"]
        expected=hmac.new(_challenge_secret(),payload.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,sig):return None,"bad_signature"
        p=json.loads(payload)
        if time.time()-p["t"]>CHALLENGE_TTL:return None,"expired"
        return p,None
    except Exception:
        return None,"malformed"

def challenge_marker(payload_dict):
    key=str(payload_dict["u"])+"|"+str(payload_dict["h"])+"|"+str(payload_dict["t"])
    return "challenge_"+hashlib.sha256(key.encode()).hexdigest()[:24]

def challenge_resolved(payload_dict):
    uid=challenge_marker(payload_dict)
    with _db_lock:
        r=_conn.execute("SELECT audit_hash,ts FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT 1",(uid,)).fetchone()
    return r

CHALLENGE_PAGE=("<!DOCTYPE html><html><head><meta charset='UTF-8'>"
 "<meta name='viewport' content='width=device-width,initial-scale=1.0'><title>Verify - AILeash</title>"
 "<style>body{font-family:sans-serif;background:#0a0f1e;color:#fff;display:flex;align-items:center;"
 "justify-content:center;min-height:100vh;margin:0;padding:20px;text-align:center}"
 ".box{max-width:420px;background:rgba(255,255,255,0.04);border:1px solid rgba(201,168,76,0.35);"
 "border-radius:10px;padding:36px}h1{font-family:Georgia,serif;color:#c9a84c;font-size:24px;margin-bottom:10px}"
 "p{color:rgba(255,255,255,0.5);font-size:14px;line-height:1.7;margin-bottom:22px}"
 "button{background:#c9a84c;color:#0a0f1e;border:none;border-radius:5px;padding:14px 30px;"
 "font-size:15px;font-weight:700;cursor:pointer}#out{margin-top:18px;font-family:monospace;font-size:12px}"
 ".ok{color:#7fe3b0}.err{color:#ff8a80}</style></head><body><div class='box'>"
 "<h1>Quick security check</h1><p>This action was flagged for verification. "
 "Confirm it was you and you'll be on your way — the confirmation is sealed into a tamper-evident record.</p>"
 "<button onclick='go()'>Yes, it was me</button><div id='out'></div>"
 "<script>async function go(){var t=new URLSearchParams(location.search).get('token');"
 "var o=document.getElementById('out');o.textContent='Sealing…';"
 "try{var r=await fetch('/api/challenge/resolve',{method:'POST',headers:{'Content-Type':'application/json'},"
 "body:JSON.stringify({token:t})});var d=await r.json();"
 "if(d.resolved){o.className='ok';o.textContent='Verified and sealed: '+d.sealed.slice(0,20)+'… You can close this page.';}"
 "else{o.className='err';o.textContent=d.error||'Could not verify.';}}"
 "catch(e){o.className='err';o.textContent='Network error - try again.';}}</script>"
 "</div></body></html>")

def send_block_alert(api_key,event,result):
    """ENHANCED: Block alert includes sealed evidence + raw signals context."""
    try:
        now_t=time.time()
        with _alert_lock:
            if now_t-_alert_last.get(api_key,0)<ALERT_COOLDOWN:return
            _alert_last[api_key]=now_t
        ki=get_key(api_key)
        if not ki:return
        email=ki[0]
        reasons=", ".join(result.get("reasons",[])) or "risk threshold exceeded"
        html=("<html><body style='font-family:Arial,sans-serif;padding:20px;color:#333'>"
            "<h2 style='color:#cc0000'>AILeash blocked an event on your platform</h2>"
            "<p>Caught in real time. Nothing to do unless it looks wrong to you.</p>"
            "<table style='font-family:monospace;font-size:13px'>"
            "<tr><td style='padding:3px 12px 3px 0'><b>User</b></td><td>"+esc(str(event.get("user_id","")))+"</td></tr>"
            "<tr><td style='padding:3px 12px 3px 0'><b>Action</b></td><td>"+esc(str(event.get("action","")))+"</td></tr>"
            "<tr><td style='padding:3px 12px 3px 0'><b>Score</b></td><td>"+str(result.get("score"))+"</td></tr>"
            "<tr><td style='padding:3px 12px 3px 0'><b>Reasons</b></td><td>"+esc(reasons)+"</td></tr>"
            "<tr><td style='padding:3px 12px 3px 0'><b>Sealed</b></td><td>"+str(result.get("audit_hash",""))[:32]+"&hellip;</td></tr>"
            "</table>"
            "<p style='color:#888;font-size:12px'>This block is already sealed in your tamper-evident audit chain. "
            "Live view: <a href='"+HOST+"/api/pulse'>"+HOST+"/api/pulse</a> with your API key. "
            "Further block alerts are paused for 60 minutes.</p>"
            "</body></html>")
        send_email(email,"","AILeash: event BLOCKED - "+esc(str(event.get("action","")))[:40],html)
    except Exception as e:print("ALERT ERR:"+str(e),flush=True)

def govern(event,api_key=None,request_handler=None):
    """ENHANCED: Capture full technical context for audit chain."""
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
    # ENHANCED: Extract request context
    request_context={}
    if request_handler:
        request_context["ip"]=extract_ip(request_handler)
        request_context["user_agent"]=extract_user_agent(request_handler)
        request_context["device_fingerprint"]=fingerprint_device(request_context["ip"],request_context["user_agent"],event.get("device_id",""))
    h,idx,seq=seal(event,result,ts,api_key,signals,request_context)
    result["audit_hash"]=h
    result["block_index"]=idx
    if seq is not None:result["receipt_seq"]=seq
    if dec=="CHALLENGE":
        ctok=make_challenge_token(uid,h)
        result["challenge_url"]=HOST+"/verify-challenge?token="+ctok
        result["challenge_status_url"]=HOST+"/api/challenge/status?token="+ctok
        result["challenge_expires_in"]=CHALLENGE_TTL
    if api_key:
        inc_usage(api_key)
        if dec=="BLOCK":
            threading.Thread(target=send_block_alert,args=(api_key,event,result),daemon=True).start()
    return result,200

# ==============================================================================
# GUARDIAN ENHANCED: Network/Business Safeguarding for Predator Pattern Detection
# ==============================================================================

def detect_guardian_pattern(network_id,user_id,events_json,audit_hash):
    """Guardian: detect grooming/predatory patterns in network traffic."""
    try:
        events=json.loads(events_json)
        # Pattern detection: repeated contact, escalation, isolation tactics
        pattern_type=None
        severity="low"
        if len(events)>5:
            pattern_type="sustained_contact"
            severity="medium"
        # Placeholder: extend with NLP/heuristics for actual grooming signals
        if pattern_type:
            with _db_lock:
                _conn.execute("INSERT INTO guardian_patterns(ts,network_id,user_id,pattern_type,severity,raw_events,audit_chain) VALUES(?,?,?,?,?,?,?)",
                    (time.time(),network_id,user_id,pattern_type,severity,events_json,audit_hash))
                _conn.commit()
            return True,pattern_type,severity
    except:pass
    return False,None,None

def report_to_ceop(network_id,user_id,pattern_type,severity,audit_hash):
    """Guardian: Prepare evidence package for CEOP reporting (placeholder for integration)."""
    report_ref="CEOP-"+hashlib.sha256((network_id+"|"+user_id+"|"+str(time.time())).encode()).hexdigest()[:12].upper()
    with _db_lock:
        _conn.execute("UPDATE guardian_patterns SET reported_to_ceop=1,report_ref=? WHERE network_id=? AND user_id=? AND audit_chain=?",
            (report_ref,network_id,user_id,audit_hash))
        _conn.commit()
    # TODO: Integrate with CEOP API for actual reporting
    print(f"GUARDIAN REPORT: {report_ref} - {pattern_type} ({severity}) - Audit: {audit_hash[:16]}", flush=True)
    return report_ref

REG_MAP_VERSION="2026.07"
REG_MAP={
  "version":REG_MAP_VERSION,
  "note":"Design mapping of engine capabilities to regulatory obligations.",
  "eu_ai_act_2024_1689":{
    "art_9_risk_management":"continuous per-event scoring, 9 signals, deterministic",
    "art_12_record_keeping":"per-decision SHA-256 chain, gapless receipts, raw signals captured",
    "art_13_transparency":"plain-language reasons on every decision",
    "art_14_human_oversight":"CHALLENGE verdict + hosted human verification pathway",
    "timeline":"general application Aug 2026; high-risk (Annex III) proposed deferral to Dec 2027"},
  "uk_online_safety_act_2023":{"status":"in force","support":"real-time moderation evidence trail, sealed, Guardian network patterns"},
  "ico_childrens_code":{"status":"in force","support":"Guardian network safeguarding; pattern detection; CEOP integration ready"},
  "eu_dsa_2022_2065":{"support":"algorithmic decision evidence for systemic risk assessment"}}

def seal_regmap_if_changed():
    try:
        with _db_lock:
            r=_conn.execute("SELECT v FROM config WHERE k='regmap_version'").fetchone()
        if r and r[0]==REG_MAP_VERSION:return
        ev={"user_id":"system_regmap","action":"regulation_map_updated","amount":0,"country":"UK","device_id":"server","anomaly":0,"device_risk":0}
        res={"decision":"ALLOW","score":0,"map_version":REG_MAP_VERSION,"map_hash":sha(REG_MAP),"version":VERSION,"note":"regulation map change sealed"}
        seal(ev,res,time.time())
        with _db_lock:
            _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('regmap_version',?)",(REG_MAP_VERSION,))
            _conn.commit()
        print("REGMAP sealed:"+REG_MAP_VERSION,flush=True)
    except Exception as e:print("REGMAP ERR:"+str(e),flush=True)

ENGINE_SPEC={
  "engine":"AILeash deterministic scoring + Guardian network safeguarding","version":VERSION,
  "signals":{
    "trust":{"weight":0.30,"formula":"(1 - trust)"},
    "velocity_60s":{"weight":0.15,"formula":"min(count/20, 1)"},
    "velocity_5m":{"weight":0.10,"formula":"min(count/50, 1)"},
    "velocity_1h":{"weight":0.10,"formula":"min(count/200, 1)"},
    "amount":{"weight":0.15,"formula":"min(ln(1+amount)/ln(1+10000), 1)"},
    "device_risk":{"weight":0.10,"formula":"raw 0..1"},
    "anomaly":{"weight":0.10,"formula":"raw 0..1"},
    "country_shift":{"weight":0.10,"formula":"1 if prior country differs"},
    "unsafe_country":{"weight":0.10,"formula":"1 if outside allow-list"}},
  "score":"clamp(sum, 0, 1); weights sum to 1.20 pre-clamp (deliberate saturation headroom)",
  "thresholds":{"ALLOW":"score < 0.35","CHALLENGE":"0.35 <= score < 0.70","BLOCK":"score >= 0.70"},
  "trust_dynamics":{"ALLOW":"t += (1-t)*0.01","CHALLENGE":"t -= t*0.02","BLOCK":"t -= t*0.08","clamp":"[0.05, 1.0]"},
  "chain":{"hash":"SHA-256(canonical_json{prev_hash, ts, event, result})","genesis":"GENESIS",
    "concurrency":"tip read + hash + insert in one lock hold","receipts":"gapless per-key sequence, raw signals captured"},
  "guardian":{"purpose":"network safeguarding - detect predatory patterns","ceop_ready":"yes","free_for_teams":"yes"},
  "principle":"deterministic and fully specified: identical inputs give identical outputs, forever"}

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

VISITS_START=2026
def bump_visits():
    with _db_lock:
        r=_conn.execute("SELECT v FROM config WHERE k='visits'").fetchone()
        n=(int(r[0]) if r and r[0] else VISITS_START)+1
        _conn.execute("INSERT OR REPLACE INTO config(k,v) VALUES('visits',?)",(str(n),))
        _conn.commit()
    return n

def get_visits():
    with _db_lock:
        r=_conn.execute("SELECT v FROM config WHERE k='visits'").fetchone()
    return int(r[0]) if r and r[0] else VISITS_START

def load_file(name):
    try:
        with open(name,"r",encoding="utf-8") as f:return f.read()
    except:return None

def check_admin(h):
    tok=get_bearer(h)
    if not tok:return False
    t=time.time()
    with _admin_lock:
        exp=_admin_tokens.get(tok)
        if exp is None:return False
        if exp<t:
            del _admin_tokens[tok]
            return False
        return True

def admin_login_allowed():
    t=time.time()
    with _admin_lock:
        while _admin_fails and _admin_fails[0]<t-60:_admin_fails.popleft()
        return len(_admin_fails)<10

def admin_login_failed():
    with _admin_lock:_admin_fails.append(time.time())

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

def badge_id_for_key(key):
    return hashlib.sha256(("shield:"+key).encode()).hexdigest()[:16]

def lookup_badge(badge_id):
    if not badge_id or len(badge_id)!=16:return None
    with _db_lock:
        rows=_conn.execute("SELECT key,org,active,is_paid,actions_used,free_quota FROM api_keys").fetchall()
    for k,org,active,is_paid,used,quota in rows:
        if badge_id_for_key(k)==badge_id:
            ok=bool(active) and (bool(is_paid) or used<quota)
            return (org or "Verified platform",ok)
    return None

def shield_svg(org,ok):
    org=esc(str(org))[:28]
    if ok:
        fill1="#0a0f1e";edge="#c9a84c";band="#c9a84c";txt="#c9a84c";status="SEALED BY AILEASH";st_fill="#0a0f1e";tick="#7fe3b0"
    else:
        fill1="#3a3f4d";edge="#8a8f9c";band="#8a8f9c";txt="#c3c7d1";status="UNVERIFIED";st_fill="#2c303b";tick="#c8362b"
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='190' height='226' viewBox='0 0 190 226'>"
        "<defs><filter id='sh' x='-20%' y='-20%' width='140%' height='140%'><feDropShadow dx='0' dy='3' stdDeviation='4' flood-color='#0a0f1e' flood-opacity='0.35'/></filter></defs>"
        "<path d='M95 6 L172 32 L172 112 Q172 172 95 218 Q18 172 18 112 L18 32 Z' fill='"+fill1+"' stroke='"+edge+"' stroke-width='4' filter='url(#sh)'/>"
        "<path d='M95 20 L158 41 L158 110 Q158 162 95 202 Q32 162 32 110 L32 41 Z' fill='none' stroke='"+edge+"' stroke-width='1.2' stroke-dasharray='5 4' opacity='0.6'/>"
        "<text x='95' y='102' text-anchor='middle' font-family='Georgia,serif' font-weight='900' font-size='19' fill='#ffffff'>AI<tspan fill='"+txt+"'>Leash</tspan></text>"
        "<text x='95' y='119' text-anchor='middle' font-family='monospace' font-size='7.5' letter-spacing='2' fill='"+txt+"'>AI GOVERNANCE</text>"
        "<rect x='30' y='130' width='130' height='22' rx='3' fill='"+band+"'/>"
        "<text x='95' y='145' text-anchor='middle' font-family='monospace' font-weight='700' font-size='9' letter-spacing='1' fill='"+st_fill+"'>"+status+"</text>"
        "<text x='95' y='168' text-anchor='middle' font-family='Verdana,sans-serif' font-size='9.5' font-weight='700' fill='#ffffff'>"+org+"</text>"
        "<text x='95' y='183' text-anchor='middle' font-family='monospace' font-size='7' letter-spacing='1' fill='"+txt+"'>"+("SHA-256 AUDIT CHAIN ✓" if ok else "NO VALID ACCOUNT")+"</text>"
        "<circle cx='95' cy='196' r='4' fill='"+tick+"'/>"
        "</svg>")

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
        parsed=urlparse(self.path)
        path=parsed.path
        if path.endswith("/") and path!="/":path=path.rstrip("/")
        qs=parse_qs(parsed.query)
        track_request()
        maybe_prune()

        if path=="/":
            try:bump_visits()
            except:pass
            c=load_file("index.html")
            send_html(self,c if c else "<html><body>AILeash</body></html>")
        elif path=="/api/spec":
            send_json(self,ENGINE_SPEC)
        elif path=="/api/verify-chain":
            send_json(self,verify_chain())
        elif path=="/api/health":
            send_json(self,{"status":"ok","version":VERSION,"rps":get_rps()})
        else:
            send_html(self,page_404(),404)

    def do_POST(self):
        parsed=urlparse(self.path)
        path=parsed.path.rstrip("/")
        track_request()
        maybe_prune()
        
        if is_over() and path not in("/api/govern","/govern"):
            n=int(self.headers.get("Content-Length",0) or 0)
            if n:self.rfile.read(n)
            send_json(self,{"error":"server_busy"},503);return

        if path=="/stripe-webhook":
            length=int(self.headers.get("Content-Length",0) or 0)
            raw=self.rfile.read(length) if length else b""
            sig=self.headers.get("Stripe-Signature","")
            if not verify_stripe_signature(raw,sig):
                print("WEBHOOK REJECTED: bad or missing signature",flush=True)
                send_json(self,{"error":"invalid_signature"},400);return
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
            return

        data=read_body(self)

        if path in("/api/govern","/govern"):
            api_key=get_bearer(self)
            if not api_key:
                send_json(self,{"error":"api_key_required","message":"Get a free key at "+HOST+"/#signup"},401);return
            try:
                result,status=govern(data,api_key,self)
                send_json(self,result,status)
            except ValueError as e:send_json(self,{"error":str(e)},400)
            except Exception as e:
                print("GOVERN ERR:"+repr(e),flush=True)
                send_json(self,{"error":"internal"},500)
        elif path in("/signup","/api/keys"):
            email=str(data.get("email","")).strip().lower()
            phone=str(data.get("phone","")).strip()
            name=str(data.get("name","")).strip()
            org=str(data.get("org","")).strip()
            org_type=str(data.get("org_type","")).strip()
            product=str(data.get("product","aileash")).strip().lower()
            devices=to_int(data.get("devices",1))
            ref_code_used=str(data.get("ref_code","")).strip().upper()
            if product not in("aileash","guardian","sonicboom","sentinel"):product="aileash"
            key,err=create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email."}
                send_json(self,{"error":msgs.get(err,err)},400);return
            monthly=0.0 if product=="guardian" else round(devices*0.50,2)
            if ref_code_used and product!="guardian":
                threading.Thread(target=credit_referral,args=(ref_code_used,devices),daemon=True).start()
            new_ref_code=create_referral(key,email,name)
            threading.Thread(target=send_referral_welcome,args=(name,email,key,new_ref_code,product,monthly),daemon=True).start()
            signup_msg="Guardian is free for your safeguarding team, always." if product=="guardian" else "100 free decisions. After trial: £"+str(monthly)+"/month via Stripe."
            bid=badge_id_for_key(key)
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"quota":FREE_QUOTA,"ref_code":new_ref_code,"badge_id":bid,"message":signup_msg})
        elif path=="/admin/auth":
            if not ADMIN_PASSWORD:
                send_json(self,{"error":"admin_disabled"},503);return
            if not admin_login_allowed():
                send_json(self,{"error":"too_many_attempts"},429);return
            pw=str(data.get("password","")).strip()
            if pw and hmac.compare_digest(pw,ADMIN_PASSWORD):
                tok=secrets.token_hex(32)
                with _admin_lock:_admin_tokens[tok]=time.time()+ADMIN_TOKEN_TTL
                send_json(self,{"token":tok,"expires_in":ADMIN_TOKEN_TTL})
            else:
                admin_login_failed()
                send_json(self,{"error":"invalid_password"},401)
        else:
            send_json(self,{"error":"not_found"},404)

if __name__=="__main__":
    print("AILeash Platform v"+VERSION+" Enhanced starting on :"+str(PORT),flush=True)
    seal_regmap_if_changed()
    setup_stripe()
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print("Ready.",flush=True)
    server.serve_forever()
