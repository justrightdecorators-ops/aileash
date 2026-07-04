# ==============================================================================
# AILEASH PLATFORM v6.1.0
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================
# v6.1.0 SECURITY RELEASE - fixes:
#  1. Stripe webhook signature verification (requires STRIPE_WEBHOOK_SECRET)
#  2. Admin auth: empty password rejected, constant-time compare, rate limited,
#     tokens expire after 24h
#  3. /api/govern now requires a valid API key (no more anonymous access)
#  4. Audit chain race condition fixed (tip read + insert under one lock)
#  5. One key per email per product enforced
#  6. HTML escaping on all user-supplied text (XSS fix)
#  7. Badges are now read-only (no longer write to the audit chain)
#  8. Velocity / rate-limit memory now pruned (no unbounded growth)
#  9. Safe integer parsing on signup/checkout (no 500 on bad input)
# 10. Internal errors no longer leak exception detail to callers
# ==============================================================================

import json,math,time,sqlite3,hashlib,threading,random,string,hmac,base64,zlib
import urllib.request,urllib.parse,os,secrets
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
VERSION="6.4.0"
OWNER_NAME="Justin Antony Dobson"
OWNER_EMAIL="justrightdecorators@gmail.com"
OWNER_PHONE="07908 269428"
SAFE={"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ={"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA=100
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","")
_admin_tokens={}          # token -> expiry timestamp
_admin_fails=deque()      # timestamps of failed admin logins
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

def to_int(v,default=1,lo=1,hi=1000000):
    try:return max(lo,min(hi,int(v)))
    except (ValueError,TypeError):return default

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
    c.execute("CREATE TABLE IF NOT EXISTS guardian_children(id INTEGER PRIMARY KEY AUTOINCREMENT,parent_key TEXT,child_name TEXT,guardian_code TEXT UNIQUE,created REAL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    try:c.execute("ALTER TABLE audit_log ADD COLUMN api_key TEXT")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE audit_log ADD COLUMN key_seq INTEGER")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE api_keys ADD COLUMN seq INTEGER DEFAULT 0")
    except sqlite3.OperationalError:pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(api_key)")
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

def prune_memory():
    """Evict stale entries from in-memory velocity/rate-limit stores.
    Called every 1000 requests. Fix for unbounded memory growth."""
    t=time.time()
    with _key_lock:
        dead=[k for k,w in _key_wins.items() if (not w["hour"]) or w["hour"][-1]<t-3600]
        for k in dead:del _key_wins[k]
    for store,age in ((W60,60),(W5M,300),(W1H,3600)):
        dead=[u for u,q in store.items() if (not q) or q[-1]<t-age]
        for u in dead:del store[u]
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
        pricing_line="Guardian is completely free for your family &mdash; every child, always. No card, no trial, no charge, ever."
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
        "<div style='font-family:monospace;font-size:10px;color:#00875a;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your Guardian Code</div>"
        "<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>"+esc(ref_code)+"</div>"
        "<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Share Guardian with other parents &mdash; it's free for them too.</p>"
        "</div>"
        )
        +"<p style='font-size:13px;color:#64748b'>Questions? <a href='mailto:"+OWNER_EMAIL+"' style='color:#c9a84c'>"+OWNER_EMAIL+"</a> &middot; "+OWNER_PHONE+"</p>"
        "</div></div></body></html>"
    )
    send_email(email,name,"Your "+pname+" API Key + Referral Code",html)

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
    """Verify Stripe webhook signature. Fix for unauthenticated webhook.
    Stripe-Signature header format: t=timestamp,v1=hexsig[,v1=...]"""
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
        ("price_gu","AILeash Guardian","Child safety. Free for families."),
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
    if not STRIPE_WEBHOOK_SECRET:print("WARNING: STRIPE_WEBHOOK_SECRET not set - webhook will reject all events. Set it in Railway variables (Stripe dashboard > Webhooks > Signing secret).",flush=True)

def get_stripe_price(product):
    return{"aileash":STRIPE_PRICE_AL,"guardian":STRIPE_PRICE_GU,"sonicboom":STRIPE_PRICE_SB,"sentinel":STRIPE_PRICE_SE}.get(product,STRIPE_PRICE_AL)

def create_key(email,phone="",name="",org="",org_type="",product="aileash",devices=1):
    email=str(email).strip().lower()
    if not email or "@" not in email:return None,"invalid_email"
    prefix={"guardian":"ag_live_","sonicboom":"sb_live_","sentinel":"se_live_"}.get(product,"al_live_")
    key=prefix+secrets.token_hex(24)
    with _db_lock:
        # Fix: enforce one key per email per product (email_exists was dead code)
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
    # Fix: crashed with IndexError on empty/whitespace name
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

def gen_guardian_code(name):
    letters="".join(c for c in name.upper() if c.isalpha())[:4].ljust(4,"X")
    suffix="".join(random.choices(string.digits,k=4))
    return "GRD-"+letters+"-"+suffix

def add_guardian_child(parent_key,name):
    for _ in range(5):
        code=gen_guardian_code(name)
        with _db_lock:
            try:
                _conn.execute("INSERT INTO guardian_children(parent_key,child_name,guardian_code,created) VALUES(?,?,?,?)",(parent_key,name,code,time.time()))
                _conn.commit()
                return code
            except sqlite3.IntegrityError:
                continue
    return None

def get_guardian_children(parent_key):
    with _db_lock:
        return _conn.execute("SELECT child_name,guardian_code,created FROM guardian_children WHERE parent_key=? ORDER BY created ASC",(parent_key,)).fetchall()

def get_guardian_alerts(code,limit=30):
    uid="guardian_child_"+code
    with _db_lock:
        rows=_conn.execute("SELECT ts,event_json,result_json FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT ?",(uid,limit)).fetchall()
    alerts=[]
    for ts,ev,res in rows:
        try:
            e=json.loads(ev);r=json.loads(res)
            alerts.append({"ts":ts,"threat_type":e.get("threat_type","SAFE"),"decision":r.get("decision"),"score":r.get("score")})
        except:pass
    return alerts

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

def seal(event,result,ts,api_key=None):
    """Tip read + hash + insert inside ONE lock hold (race fix).
    Completeness receipts: every sealed decision gets the chain position
    (block_index) and a per-key monotonic sequence number (key_seq) issued
    inside the same lock. Sequence numbers have no gaps by construction -
    a caller holding receipts N and N+2 can PROVE N+1 is missing.
    Both live alongside the block, never inside the hash payload, so all
    existing chain blocks remain valid."""
    with _db_lock:
        r=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev=r[0] if r else "GENESIS"
        h=sha({"prev_hash":prev,"ts":ts,"event":event,"result":result})
        seq=None
        if api_key:
            _conn.execute("UPDATE api_keys SET seq=COALESCE(seq,0)+1 WHERE key=?",(api_key,))
            sr=_conn.execute("SELECT seq FROM api_keys WHERE key=?",(api_key,)).fetchone()
            seq=sr[0] if sr else None
        cur=_conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash,api_key,key_seq) VALUES(?,?,?,?,?,?,?,?)",(ts,event["user_id"],json.dumps(event),json.dumps(result),prev,h,api_key or "",seq))
        idx=cur.lastrowid
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
    """Read-only: fetch the most recent decision for badge display.
    Fix: badges no longer write to the audit chain."""
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

# --- v6.4: hosted CHALLENGE resolution -------------------------------------
# When the engine returns CHALLENGE, the response now carries a signed,
# time-limited verification link. We host the page, seal the resolution
# into the chain, and expose a one-call status check. The client's
# "complex exception workflow" becomes: show the link, poll the status.
CHALLENGE_TTL=900  # 15 minutes
def _challenge_secret():
    s=os.environ.get("LICENCE_SECRET","")
    return s.encode() if s else _EPHEMERAL_SECRET
_EPHEMERAL_SECRET=secrets.token_bytes(32)  # fallback: pending links die on restart

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
    # derived from verified payload (user + block + issue-time), never the raw token string,
    # so a mutated/replayed token cannot collide onto a resolved challenge's marker
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
 "Confirm it was you and you'll be on your way \u2014 the confirmation is sealed into a tamper-evident record.</p>"
 "<button onclick='go()'>Yes, it was me</button><div id='out'></div>"
 "<script>async function go(){var t=new URLSearchParams(location.search).get('token');"
 "var o=document.getElementById('out');o.textContent='Sealing\u2026';"
 "try{var r=await fetch('/api/challenge/resolve',{method:'POST',headers:{'Content-Type':'application/json'},"
 "body:JSON.stringify({token:t})});var d=await r.json();"
 "if(d.resolved){o.className='ok';o.textContent='Verified and sealed: '+d.sealed.slice(0,20)+'\u2026 You can close this page.';}"
 "else{o.className='err';o.textContent=d.error||'Could not verify.';}}"
 "catch(e){o.className='err';o.textContent='Network error - try again.';}}</script>"
 "</div></body></html>")

def send_block_alert(api_key,event,result):
    """The moment the engine BLOCKS something on a customer's traffic,
    tell them - with the sealed evidence attached. Max one email per hour
    per key so a burst attack doesn't also flood their inbox."""
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
    h,idx,seq=seal(event,result,ts,api_key)
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

# --- v6.4: versioned regulation map, changes sealed into the chain ---------
REG_MAP_VERSION="2026.07"
REG_MAP={
  "version":REG_MAP_VERSION,
  "note":"Design mapping of engine capabilities to regulatory obligations. Design intent, not certification.",
  "eu_ai_act_2024_1689":{
    "art_9_risk_management":"continuous per-event scoring, 9 signals, deterministic",
    "art_12_record_keeping":"per-decision SHA-256 chain, gapless receipts, public verification",
    "art_13_transparency":"plain-language reasons on every decision",
    "art_14_human_oversight":"CHALLENGE verdict + hosted human verification pathway",
    "timeline":"general application Aug 2026; high-risk (Annex III) proposed deferral to Dec 2027, pending formal adoption"},
  "uk_online_safety_act_2023":{"status":"in force","support":"real-time moderation evidence trail, sealed"},
  "ico_childrens_code":{"status":"in force","support":"Guardian message checks; no profiling of children"},
  "eu_dsa_2022_2065":{"support":"algorithmic decision evidence for systemic risk assessment"}}

def seal_regmap_if_changed():
    """Every change to the regulation map is itself sealed into the chain -
    regulatory updates become auditable events, not silent edits."""
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

# --- v6.4: the engine is self-describing - full spec, public ---------------
ENGINE_SPEC={
  "engine":"AILeash deterministic scoring","version":VERSION,
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
    "concurrency":"tip read + hash + insert in one lock hold","receipts":"gapless per-key sequence, same transaction"},
  "principle":"deterministic and fully specified: identical inputs give identical outputs, forever; any competent engineer can maintain or reimplement this engine from this spec"}

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
    """Fix: tokens now expire after 24h and are checked under a lock."""
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
    """Fix: rate limit admin login attempts - max 10 per minute globally."""
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
    """Find the org for a public badge id. Returns (org, active_and_ok) or None."""
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
        "<g transform='translate(79,44)'><circle cx='16' cy='16' r='13.5' fill='none' stroke='"+edge+"' stroke-width='2.6' stroke-dasharray='66 20' stroke-linecap='round' transform='rotate(-50 16 16)'/><circle cx='26.5' cy='7' r='3.1' fill='"+edge+"'/><circle cx='16' cy='16' r='3.4' fill='"+fill1+"'/></g>"
        "<text x='95' y='102' text-anchor='middle' font-family='Georgia,serif' font-weight='900' font-size='19' fill='#ffffff'>AI<tspan fill='"+txt+"'>Leash</tspan></text>"
        "<text x='95' y='119' text-anchor='middle' font-family='monospace' font-size='7.5' letter-spacing='2' fill='"+txt+"'>AI GOVERNANCE</text>"
        "<rect x='30' y='130' width='130' height='22' rx='3' fill='"+band+"'/>"
        "<text x='95' y='145' text-anchor='middle' font-family='monospace' font-weight='700' font-size='9' letter-spacing='1' fill='"+st_fill+"'>"+status+"</text>"
        "<text x='95' y='168' text-anchor='middle' font-family='Verdana,sans-serif' font-size='9.5' font-weight='700' fill='#ffffff'>"+org+"</text>"
        "<text x='95' y='183' text-anchor='middle' font-family='monospace' font-size='7' letter-spacing='1' fill='"+txt+"'>"+("SHA-256 AUDIT CHAIN \u2713" if ok else "NO VALID ACCOUNT")+"</text>"
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

def referrals_page(code):
    ref=get_referral(code) if code else None
    if ref:
        _,email,name,devices,earnings=ref
        # Fix: name is user-supplied - escape it (stored XSS)
        first=esc(name.split()[0]) if name and name.split() else "there"
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

# Fallback homepage (served only if index.html is missing). Stored zlib+base64
# so the file survives phone clipboards and PyramIDE. Decoded once at startup -
# byte-identical to the original HTML.
_HOMEPAGE_B64="".join([
"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"
])
HOMEPAGE=zlib.decompress(base64.b64decode(_HOMEPAGE_B64)).decode("utf-8")

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

        if path=="/mM_hYELAWL0vrzIvAnKRBlUnN1kM-H656cmjMrFT-3U.html":
            send_text(self,"google-site-verification: mM_hYELAWL0vrzIvAnKRBlUnN1kM-H656cmjMrFT-3U","text/html")
            return

        if path=="/":
            try:bump_visits()
            except:pass
            c=load_file("index.html")
            send_html(self,c if c else HOMEPAGE)
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
        elif path=="/child-safety-guide":
            c=load_file("child-safety-guide.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/compliance-assistant":
            c=load_file("compliance-assistant.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/investors":
            c=load_file("investor-prospectus.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
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
        elif path=="/admin":
            c=load_file("admin.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/brain":
            c=load_file("brain.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/referrals":
            code=qs.get("code",[""])[0].strip().upper()
            send_html(self,referrals_page(code))
        elif path=="/api/guardian/children":
            auth=get_bearer(self)
            if not auth:send_json(self,{"error":"no_key"},401);return
            rows=get_guardian_children(auth)
            children=[{"name":r[0],"code":r[1],"created":r[2]} for r in rows]
            send_json(self,{"children":children})
        elif path=="/api/guardian/alerts":
            code=qs.get("code",[""])[0].strip().upper()
            if not code:send_json(self,{"error":"no_code"},400);return
            send_json(self,{"alerts":get_guardian_alerts(code)})
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
        elif path=="/verify-challenge":
            send_html(self,CHALLENGE_PAGE)
        elif path=="/api/challenge/status":
            tok=qs.get("token",[""])[0].strip()
            p,err=read_challenge_token(tok)
            if not p:send_json(self,{"resolved":False,"error":err or "invalid_token"},400);return
            r=challenge_resolved(p)
            if r:send_json(self,{"resolved":True,"sealed":r[0],"at":r[1]})
            else:send_json(self,{"resolved":False,"expired":err=="expired"})
        elif path=="/api/regulation-map":
            send_json(self,{"map":REG_MAP,"map_hash":sha(REG_MAP),"changes_sealed":"every version change is sealed into the audit chain as a block"})
        elif path=="/api/partner/status":
            bid=qs.get("badge",[""])[0].strip().lower()
            hit=lookup_badge(bid)
            with _db_lock:
                tip=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            ct=(tip[0][:16] if tip else "GENESIS")
            if hit:
                send_json(self,{"partner":hit[0],"account_standing":"active" if hit[1] else "lapsed","infrastructure":"operational","chain_tip":ct,"note":"account_standing is the partner's status; infrastructure is the AILeash platform status - independently attributable"})
            else:
                send_json(self,{"partner":None,"account_standing":"not_found","infrastructure":"operational","chain_tip":ct})
        elif path=="/api/spec":
            send_json(self,ENGINE_SPEC)
        elif path=="/api/inclusion":
            h_q=qs.get("hash",[""])[0].strip().lower()
            if not h_q or len(h_q)!=64:send_json(self,{"included":False,"error":"provide full 64-char audit hash"},400);return
            with _db_lock:
                r=_conn.execute("SELECT id,ts,key_seq FROM audit_log WHERE audit_hash=?",(h_q,)).fetchone()
            if not r:send_json(self,{"included":False,"hash":h_q});return
            send_json(self,{"included":True,"hash":h_q,"block_index":r[0],"sealed_at":r[1],"receipt_seq":r[2]})
        elif path=="/api/coverage":
            auth=get_bearer(self)
            if not auth:send_json(self,{"error":"api_key_required"},401);return
            ki=get_key(auth)
            if not ki:send_json(self,{"error":"invalid_api_key"},401);return
            with _db_lock:
                sr=_conn.execute("SELECT COALESCE(seq,0) FROM api_keys WHERE key=?",(auth,)).fetchone()
                cnt=_conn.execute("SELECT COUNT(*),MIN(key_seq),MAX(key_seq),MIN(ts),MAX(ts) FROM audit_log WHERE api_key=?",(auth,)).fetchone()
                gaps=_conn.execute("SELECT COUNT(*) FROM audit_log WHERE api_key=? AND key_seq IS NOT NULL",(auth,)).fetchone()
            issued=sr[0] if sr else 0
            sealed=gaps[0]
            send_json(self,{
                "receipts_issued":issued,
                "receipts_sealed":sealed,
                "complete":issued==sealed,
                "seq_range":[cnt[1],cnt[2]],
                "period":[cnt[3],cnt[4]],
                "how_to_reconcile":"Every /api/govern response carries receipt_seq. Sequences are gapless by construction. Compare your stored receipts against seq_range - any number you hold that this chain lacks, or any gap in your own receipt series, is a provable omission."})
        elif path=="/api/pulse":
            auth=get_bearer(self)
            if not auth:send_json(self,{"error":"api_key_required"},401);return
            ki=get_key(auth)
            if not ki:send_json(self,{"error":"invalid_api_key"},401);return
            cutoff=time.time()-3600
            with _db_lock:
                counts=dict(_conn.execute("SELECT json_extract(result_json,'$.decision'),COUNT(*) FROM audit_log WHERE api_key=? AND ts>? GROUP BY 1",(auth,cutoff)).fetchall())
                recent=_conn.execute("SELECT ts,event_json,result_json,audit_hash FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 10",(auth,)).fetchall()
                tip=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            events=[]
            for ts_,ev,res,ah in recent:
                try:
                    e=json.loads(ev);r=json.loads(res)
                    events.append({"ts":ts_,"action":e.get("action"),"decision":r.get("decision"),"score":r.get("score"),"reasons":r.get("reasons",[]),"sealed":ah[:16]})
                except:pass
            send_json(self,{
                "last_hour":{"ALLOW":counts.get("ALLOW",0),"CHALLENGE":counts.get("CHALLENGE",0),"BLOCK":counts.get("BLOCK",0)},
                "recent":events,
                "chain_tip":(tip[0][:16] if tip else "GENESIS"),
                "alerting":"BLOCK events email you in real time (max 1/hour)"})
        elif path=="/api/visits":
            send_json(self,{"visits":get_visits()})
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
        elif path=="/api/badge/shield":
            bid=qs.get("badge",[""])[0].strip().lower()
            hit=lookup_badge(bid)
            if hit:send_svg(self,shield_svg(hit[0],hit[1]))
            else:send_svg(self,shield_svg("No account found",False))
        elif path=="/api/badge/status":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_svg(self,badge_svg("AILeash","LIVE "+str(blocks)+" blocks","#00875a"))
        elif path=="/api/badge/decision":
            # Fix: read-only - no longer writes a block to the audit chain per view
            ld=last_decision()
            if ld and ld[0]:
                dec,sc=ld
                colours={"ALLOW":"#00875a","CHALLENGE":"#b45309","BLOCK":"#cc0000"}
                send_svg(self,badge_svg("Live Decision",str(dec)+" "+str(round(sc or 0,2)),colours.get(dec,"#555")))
            else:
                send_svg(self,badge_svg("Live Decision","READY","#00875a"))
        elif path=="/api/badge/chain":
            with _db_lock:
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            send_svg(self,badge_svg("SHA-256",str(blocks)+" blocks","#0a0f1e"))
        elif path=="/robots.txt":
            send_text(self,"User-agent: *\nAllow: /\nSitemap: https://sebbi.pro/sitemap.xml\n")
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
        track_request()
        maybe_prune()
        if is_over() and path not in("/api/govern","/govern"):
            # drain body before replying so the connection stays clean
            n=int(self.headers.get("Content-Length",0) or 0)
            if n:self.rfile.read(n)
            send_json(self,{"error":"server_busy"},503);return

        # Webhook needs the RAW bytes for signature verification - handle before read_body
        if path=="/stripe-webhook":
            length=int(self.headers.get("Content-Length",0) or 0)
            raw=self.rfile.read(length) if length else b""
            # Fix: verify Stripe signature - previously anyone could POST a fake
            # checkout.session.completed and mark themselves paid for free
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
            # Fix: API key now REQUIRED - previously no key meant no quota,
            # no rate limit, no billing, and anonymous audit chain writes
            if not api_key:
                send_json(self,{"error":"api_key_required","message":"Get a free key at "+HOST+"/#signup"},401);return
            try:
                result,status=govern(data,api_key)
                send_json(self,result,status)
            except ValueError as e:send_json(self,{"error":str(e)},400)
            except Exception as e:
                # Fix: log detail server-side, do not leak it to the caller
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
            signup_msg="Guardian is free for your family, always." if product=="guardian" else "100 free decisions. After trial: \u00a3"+str(monthly)+"/month via Stripe."
            bid=badge_id_for_key(key)
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"quota":FREE_QUOTA,"ref_code":new_ref_code,"badge_id":bid,"badge_url":HOST+"/api/badge/shield?badge="+bid,"endpoint":HOST+"/api/govern","message":signup_msg})
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
            devices=to_int(data.get("devices",1))
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
            # Fix: escape user-supplied JSON before embedding in the email HTML
            html="<html><body style='font-family:Arial,sans-serif;padding:20px'><h2 style='color:#cc0000'>THREAT REPORT: "+ref+"</h2><pre style='background:#f5f5f5;padding:16px;border-radius:4px'>"+esc(json.dumps(data,indent=2))+"</pre></body></html>"
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
        elif path=="/api/challenge/resolve":
            tok=str(data.get("token","")).strip()
            p,err=read_challenge_token(tok)
            if not p:send_json(self,{"resolved":False,"error":err or "invalid_token"},400);return
            prior=challenge_resolved(p)
            if prior:send_json(self,{"resolved":True,"sealed":prior[0],"note":"already resolved"});return
            uid=challenge_marker(p)
            ev={"user_id":uid,"action":"challenge_resolved","amount":0,"country":"UK","device_id":"hosted_verify","anomaly":0,"device_risk":0,"original_user":p["u"],"original_block":p["h"]}
            res={"decision":"ALLOW","score":0,"reasons":["human_verified"],"version":VERSION,"timestamp":time.time()}
            h2,_,_=seal(ev,res,res["timestamp"])
            st=load_user(p["u"])
            save_user(p["u"],clamp(st["trust"]+(1-st["trust"])*0.05,0.05,1.0),st["last_country"])
            send_json(self,{"resolved":True,"sealed":h2})
        elif path=="/api/guardian/add-child":
            auth=get_bearer(self)
            if not auth:send_json(self,{"error":"no_key"},401);return
            ki=get_key(auth)
            if not ki:send_json(self,{"error":"invalid_api_key"},401);return
            name=str(data.get("name","")).strip()
            if not name:send_json(self,{"error":"no_name"},400);return
            code=add_guardian_child(auth,name)
            if not code:send_json(self,{"error":"could_not_create_code"},500);return
            send_json(self,{"ok":True,"name":name,"code":code})
        elif path=="/admin/auth":
            # Fixes: empty password rejected, constant-time compare, rate limited
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
        elif path=="/api/generate-airgap-token":
            auth=get_bearer(self)
            ki=get_key(auth) if auth else None
            if not ki:send_json(self,{"error":"invalid_api_key"},401);return
            email,used,active,is_paid,quota,plan,product=ki
            if not is_paid:send_json(self,{"error":"paid_plan_required"},403);return
            with _db_lock:
                devices=_conn.execute("SELECT devices FROM api_keys WHERE key=?",(auth,)).fetchone()
            secret=os.environ.get("LICENCE_SECRET","").encode()
            if not secret:send_json(self,{"error":"licence_secret_not_configured"},503);return
            issued=int(time.time())
            expires=issued+(365*86400)
            payload=json.dumps({"v":"1","key":auth,"devices":devices[0] if devices else 1,"plan":plan,"email":email,"issued":issued,"expires":expires},sort_keys=True,separators=(',',':'))
            sig=hmac.new(secret,payload.encode(),hashlib.sha256).hexdigest()
            token_data=json.dumps({"payload":payload,"sig":sig},separators=(',',':'))
            token=base64.urlsafe_b64encode(token_data.encode()).decode()
            send_json(self,{"token":token,"expires":expires,"days":365})
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
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                total=_conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
                paid=_conn.execute("SELECT COUNT(*) FROM api_keys WHERE is_paid=1").fetchone()[0]
                blocks=_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            chain=verify_chain()
            send_json(self,{"total_keys":total,"paid_keys":paid,"audit_blocks":blocks,"chain_valid":chain["valid"]})
        elif path=="/admin/keys":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT key,email,name,org,product,devices,actions_used,free_quota,is_paid,plan_type,created FROM api_keys ORDER BY created DESC").fetchall()
            keys=[{"key":r[0],"email":r[1],"name":r[2],"org":r[3],"product":r[4],"devices":r[5],"actions_used":r[6],"free_quota":r[7],"is_paid":r[8],"plan_type":r[9],"created":r[10]} for r in rows]
            send_json(self,{"keys":keys})
        elif path=="/admin/referrals":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT code,referrer_email,referrer_name,devices_referred,earnings_pence,created FROM referrals ORDER BY created DESC").fetchall()
            refs=[{"code":r[0],"referrer_email":r[1],"referrer_name":r[2],"devices_referred":r[3],"earnings_pence":r[4],"created":r[5]} for r in rows]
            send_json(self,{"referrals":refs})
        elif path=="/admin/contacts":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT ts,name,email,phone,org,message FROM contact_log ORDER BY ts DESC").fetchall()
            contacts=[{"ts":r[0],"name":r[1],"email":r[2],"phone":r[3],"org":r[4],"message":r[5]} for r in rows]
            send_json(self,{"contacts":contacts})
        else:
            send_json(self,{"error":"not_found"},404)

if __name__=="__main__":
    print("AILeash Platform v"+VERSION+" starting on :"+str(PORT),flush=True)
    seal_regmap_if_changed()
    setup_stripe()
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print("Ready.",flush=True)
    server.serve_forever()
