import json,math,time,sqlite3,hashlib,threading,random,string,hmac,base64,zlib,re
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
def _pick_db_path():
    """Use a persistent volume if one is mounted, else fall back to the
    local file so the app never crashes on boot. Set DB_PATH in Railway
    (e.g. /data/aileash.db) once a volume is mounted at that folder, and
    the chain will survive redeploys instead of resetting each time."""
    p=os.environ.get("DB_PATH","").strip()
    if p:
        d=os.path.dirname(p) or "."
        try:
            os.makedirs(d,exist_ok=True)
            if os.access(d,os.W_OK):return p
        except Exception:pass
        print("DB_PATH set but "+p+" not writable - falling back to local aileash.db",flush=True)
    return "aileash.db"
DB=_pick_db_path()
VERSION="6.5.0"
OWNER_NAME="Justin Antony Dobson"
OWNER_EMAIL="justrightdecorators@gmail.com"
OWNER_PHONE="07908 269428"
SAFE={"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQ={"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA=100
TRIAL_DAYS=90
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
_trial_checkout_cache={}
_trial_lock=threading.Lock()

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
    c.execute("CREATE TABLE IF NOT EXISTS guardian_family(pair_code TEXT PRIMARY KEY,parent_key TEXT,child_name TEXT,created REAL,last_checkin REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS guardian_events(id INTEGER PRIMARY KEY AUTOINCREMENT,pair_code TEXT,ts REAL,kind TEXT,lat REAL,lon REAL,note TEXT,content_fp TEXT,audit_hash TEXT)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id)")
    try:c.execute("ALTER TABLE audit_log ADD COLUMN api_key TEXT")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE audit_log ADD COLUMN key_seq INTEGER")
    except sqlite3.OperationalError:pass
    try:c.execute("ALTER TABLE api_keys ADD COLUMN seq INTEGER DEFAULT 0")
    except sqlite3.OperationalError:pass
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit_key ON audit_log(api_key)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_keys_email ON api_keys(email)")
    c.execute("CREATE TABLE IF NOT EXISTS device_seen(api_key TEXT,device_id TEXT,first_seen REAL,PRIMARY KEY(api_key,device_id))")
    c.execute("CREATE TABLE IF NOT EXISTS identity_registry(fp TEXT PRIMARY KEY,ts REAL,seal TEXT,block_index INTEGER,public INTEGER DEFAULT 0,profile_json TEXT DEFAULT '')")
    c.execute("CREATE TABLE IF NOT EXISTS payment_registry(fp TEXT PRIMARY KEY,ts REAL,seal TEXT,block_index INTEGER,display_json TEXT DEFAULT '')")
    c.execute("CREATE TABLE IF NOT EXISTS post_registry(fp TEXT PRIMARY KEY,ts REAL,seal TEXT,block_index INTEGER)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_devseen_key ON device_seen(api_key)")
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
    with _trial_lock:
        old=[k for k,v in _trial_checkout_cache.items() if v[0]<t-3600]
        for k in old:del _trial_checkout_cache[k]

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
    pname={"sonicboom":"SonicBoom","sentinel":"AILeash Sentinel"}.get(product,"AILeash")
    safe_first=esc(name.split()[0]) if name.strip() else ""
    pricing_line="Your "+pname+" API key is ready. Everything is free for the first "+str(TRIAL_DAYS)+" days - full engine, unlimited decisions, no card. After the trial it is 50p per unique device per month via Stripe, metered on the real devices that used your key."
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
        +"<div style='background:#f8f5ee;border:2px solid #c9a84c;border-radius:6px;padding:20px;margin:20px 0'>"
        "<div style='font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px'>Your Referral Code</div>"
        "<div style='font-family:monospace;font-size:20px;color:#0a0f1e;font-weight:900'>"+esc(ref_code)+"</div>"
        "<p style='font-size:13px;color:#64748b;margin-top:8px;line-height:1.6'>Share this code. Every device signed up earns you <strong>10p per month forever</strong>.</p>"
        "</div>"
        +"<p style='font-size:13px;color:#64748b'>Your step-by-step installation guide is arriving in a separate email.</p>"
        "<p style='font-size:13px;color:#64748b'>Questions? <a href='mailto:"+OWNER_EMAIL+"' style='color:#c9a84c'>"+OWNER_EMAIL+"</a> &middot; "+OWNER_PHONE+"</p>"
        "</div></div></body></html>"
    )
    send_email(email,name,"Your "+pname+" API Key + Referral Code",html)

def _guide_shell(title,inner):
    return ("<html><body style='font-family:Arial,sans-serif;background:#f5f7fa;padding:20px'>"
        "<div style='max-width:640px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden'>"
        "<div style='background:#0a0f1e;padding:28px;border-bottom:4px solid #c9a84c'>"
        "<div style='font-size:20px;color:#fff;font-weight:900;font-family:Georgia,serif'>"+esc(title)+"</div>"
        "<div style='font-family:monospace;font-size:9px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-top:6px'>Installation guide &middot; Monop Content</div>"
        "</div><div style='padding:32px'>"+inner+
        "<hr style='border:none;border-top:1px solid #eee;margin:26px 0'>"
        "<p style='font-size:12px;color:#94a3b8;line-height:1.7'>Free for "+str(TRIAL_DAYS)+" days from signup. After that, 50p per unique device per month via Stripe - metered on the real devices that used your key, never a number you typed. When the trial ends you will be directed to a secure Stripe payment page; pay to continue exactly where you left off, or remove the integration - your choice, no lock-in.</p>"
        "<p style='font-size:12px;color:#94a3b8'>Help: <a href='mailto:"+OWNER_EMAIL+"' style='color:#c9a84c'>"+OWNER_EMAIL+"</a> &middot; "+OWNER_PHONE+" &middot; <a href='"+HOST+"/developers' style='color:#c9a84c'>"+HOST+"/developers</a></p>"
        "</div></div></body></html>")

def _code_block(code):
    return "<pre style='background:#0a0f1e;color:#7fe3b0;font-family:monospace;font-size:11px;padding:16px;border-radius:6px;overflow-x:auto;line-height:1.6'>"+esc(code)+"</pre>"

def _h(t):
    return "<p style='font-size:15px;font-weight:700;color:#0a0f1e;margin:22px 0 8px'>"+esc(t)+"</p>"

def _p(t):
    return "<p style='font-size:13px;color:#64748b;line-height:1.7;margin-bottom:8px'>"+t+"</p>"

def install_guide(product,key):
    k=esc(key)
    govern_curl=("curl -X POST "+HOST+"/api/govern \\\n"
        "  -H \"Authorization: Bearer "+key+"\" \\\n"
        "  -H \"Content-Type: application/json\" \\\n"
        "  -d '{\n"
        "    \"user_id\": \"user_123\",\n"
        "    \"action\": \"payment\",\n"
        "    \"amount\": 49.99,\n"
        "    \"country\": \"UK\",\n"
        "    \"device_id\": \"device_abc\",\n"
        "    \"anomaly\": 0.1,\n"
        "    \"device_risk\": 0.2\n"
        "  }'")
    govern_py=("import requests\n\n"
        "r = requests.post(\""+HOST+"/api/govern\",\n"
        "    headers={\"Authorization\": \"Bearer "+key+"\"},\n"
        "    json={\"user_id\": \"user_123\", \"action\": \"payment\",\n"
        "          \"amount\": 49.99, \"country\": \"UK\",\n"
        "          \"device_id\": \"device_abc\", \"anomaly\": 0.1, \"device_risk\": 0.2})\n"
        "d = r.json()\n"
        "print(d[\"decision\"], d[\"score\"], d[\"audit_hash\"])")
    govern_js=("const r = await fetch(\""+HOST+"/api/govern\", {\n"
        "  method: \"POST\",\n"
        "  headers: {\"Authorization\": \"Bearer "+key+"\",\n"
        "            \"Content-Type\": \"application/json\"},\n"
        "  body: JSON.stringify({user_id: \"user_123\", action: \"payment\",\n"
        "    amount: 49.99, country: \"UK\", device_id: \"device_abc\",\n"
        "    anomaly: 0.1, device_risk: 0.2})\n"
        "});\n"
        "const d = await r.json();\n"
        "console.log(d.decision, d.score, d.audit_hash);")
    eligible=_p("<b>Eligible systems:</b> anything that can send an HTTPS POST with JSON. That covers every modern backend - Python (Django, Flask, FastAPI), Node.js, PHP (Laravel, WordPress plugins), Java/Spring, .NET, Ruby on Rails, Go - plus no-code tools like Zapier and Make, and mobile apps calling through your own server. No SDK to install, no library dependency, nothing added to your stack.")
    if product=="sonicboom":
        inner=(
            _p("SonicBoom adds a sealed compliance record to every AI call you already make, without slowing anything down. It sits <b>alongside</b> your existing provider - AWS, Azure, Google Cloud, OpenAI, Anthropic - it never replaces it.")
            +_h("How it fits your current system")
            +_p("You already call your AI provider. Add one call to SonicBoom either just before (to gate the action) or just after (to seal the record). Median decision time is 28ms, so your users never notice it.")
            +_h("Step 1 - test your key (60 seconds)")
            +_code_block(govern_curl)
            +_h("Step 2 - wrap your existing AI call")
            +_p("Python example - two lines around what you already run:")
            +_code_block("verdict = requests.post(\""+HOST+"/api/govern\", headers=H, json=event).json()\nif verdict[\"decision\"] != \"BLOCK\":\n    result = openai_client.chat.completions.create(...)  # your existing call, unchanged")
            +_h("Step 3 - keep the receipt")
            +_p("Every response includes <b>audit_hash</b>, <b>block_index</b> and <b>receipt_seq</b>. Store them with your own logs - they are your regulator-ready proof. Anyone can verify them at "+HOST+"/api/verify-chain.")
            +eligible
            +_h("What the decision means")
            +_p("<b>ALLOW</b> - proceed. <b>CHALLENGE</b> - the response includes a hosted verification URL to show the user. <b>BLOCK</b> - stop the action; you get an email alert with the sealed evidence.")
        )
        return "SonicBoom installation guide - one line of code",_guide_shell("SonicBoom",inner)
    if product=="sentinel":
        inner=(
            _p("Sentinel watches every event on your platform and emails you the moment something looks like fraud - a burst of actions, a strange-country login, a risky device - with the sealed evidence attached.")
            +_h("How it fits your current system")
            +_p("Send Sentinel an event whenever money or accounts move: checkout, login, transfer, signup, message. One POST per event. Sentinel scores it in under 30ms and seals it. BLOCK verdicts trigger a real-time email alert (max one per hour so a burst attack can't flood your inbox).")
            +_h("Step 1 - test your key (60 seconds)")
            +_code_block(govern_curl)
            +_h("Step 2 - wire it into your event points")
            +_code_block(govern_py)
            +_h("Step 3 - act on the verdict")
            +_p("<b>ALLOW</b> - let it through. <b>CHALLENGE</b> - show the user the hosted verification link in the response. <b>BLOCK</b> - hold the action; the alert email is already on its way to you with the audit hash.")
            +_h("Live monitoring")
            +_p("Watch your last hour in real time: GET "+HOST+"/api/pulse with your key as the Bearer token. Device count and billing: GET "+HOST+"/api/usage.")
            +eligible
        )
        return "Sentinel installation guide - fraud alerts in 3 steps",_guide_shell("Sentinel",inner)
    if product=="guardian":
        inner=(
            _p("Guardian gives platforms with young users a safety layer that flags known grooming and manipulation patterns, gives every child one-tap access to CEOP, Childline and 999, and seals every safety event into a tamper-evident chain - the exact evidence Ofcom asks for under the Online Safety Act.")
            +_h("How it fits your current system")
            +_p("You build Guardian into <b>your own app</b> - your design, our engine underneath. Three endpoints do the work; message content is never stored, only a fingerprint.")
            +_h("Step 1 - pair a family")
            +_code_block("curl -X POST "+HOST+"/api/guardian/pair \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"parent_email\": \"parent@example.com\", \"child_name\": \"Sam\"}'")
            +_p("The response includes a <b>pair_code</b> and a ready-made child URL to open on the child's phone.")
            +_h("Step 2 - check a message")
            +_code_block("curl -X POST "+HOST+"/api/guardian/flag \\\n  -H \"Content-Type: application/json\" \\\n  -d '{\"code\": \"SAM-A1B2\", \"message\": \"<text the child wants checked>\"}'")
            +_p("Returns <b>FLAGGED</b> (with categories - the parent is emailed automatically) or <b>UNRECOGNISED</b>. Guardian never falsely tells a child a message is \"safe\".")
            +_h("Step 3 - check-ins and the Help button")
            +_code_block("POST "+HOST+"/api/guardian/checkin   {\"code\": \"SAM-A1B2\", \"lat\": 55.1, \"lon\": -1.5}\nPOST "+HOST+"/api/guardian/panic     {\"code\": \"SAM-A1B2\", \"lat\": 55.1, \"lon\": -1.5}")
            +_p("Panic seals the event and emails the parent instantly with a map link. The parent's full sealed timeline: GET "+HOST+"/api/guardian/report?email=parent@example.com&code=SAM-A1B2")
            +eligible
            +_p("<b>Families never pay.</b> Platforms pay 50p per device after the "+str(TRIAL_DAYS)+"-day trial.")
        )
        return "Guardian installation guide - child safety, sealed",_guide_shell("Guardian",inner)
    inner=(
        _p("AILeash scores every decision your AI makes - <b>ALLOW, CHALLENGE or BLOCK</b> in under 30ms - and seals each one into a SHA-256 chain nobody can quietly edit. When a regulator asks what your AI decided and why, you answer in one API call.")
        +_h("How it fits your current system")
        +_p("Wherever your AI acts on a user - approving a loan, pricing a policy, blocking a payment, banning an account - send AILeash the event first and act on the verdict. One POST per decision, nothing else in your stack changes.")
        +_h("Step 1 - test your key (60 seconds)")
        +_code_block(govern_curl)
        +_h("Step 2 - integrate (pick your language)")
        +_p("Python:")+_code_block(govern_py)
        +_p("JavaScript / Node:")+_code_block(govern_js)
        +_h("Step 3 - store the receipts")
        +_p("Every response includes <b>audit_hash</b>, <b>block_index</b> and a gapless <b>receipt_seq</b>. Store them with your own records - together they are your proof under EU AI Act Articles 9, 12, 13 and 14. Verify any time: "+HOST+"/api/verify-chain &middot; reconcile completeness: "+HOST+"/api/coverage.")
        +_h("The required fields")
        +_p("<b>user_id</b> (who), <b>action</b> (what), <b>amount</b> (0 if none), <b>country</b> (2-letter), <b>device_id</b> (device fingerprint - this is also the billing meter), <b>anomaly</b> and <b>device_risk</b> (0 to 1 - send 0 if you don't score these yet).")
        +eligible
        +_h("What the decision means")
        +_p("<b>ALLOW</b> - proceed. <b>CHALLENGE</b> - the response carries a hosted verification URL; show it to the user and poll the status URL. <b>BLOCK</b> - stop the action; a real-time alert email with sealed evidence is on its way to you.")
    )
    return "AILeash installation guide - live in 3 steps",_guide_shell("AILeash",inner)

def send_install_guide(name,email,key,product):
    try:
        subject,html=install_guide(product,key)
        send_email(email,name,subject,html)
    except Exception as e:print("GUIDE ERR:"+str(e),flush=True)

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
    return{"aileash":STRIPE_PRICE_AL,"sonicboom":STRIPE_PRICE_SB,"sentinel":STRIPE_PRICE_SE}.get(product,STRIPE_PRICE_AL)

def trial_checkout(key,email,product):
    """Payment gate at trial end. Builds a Stripe checkout session whose
    quantity is the REAL unique device count seen on this key - a show of
    good faith both ways: they had 90 days free, the bill reflects exactly
    what they used. Cached one hour per key so expired-trial traffic
    doesn't hammer Stripe."""
    t=time.time()
    with _trial_lock:
        c=_trial_checkout_cache.get(key)
        if c and t-c[0]<3600:return c[1]
    n=device_count(key) or 1
    url=HOST+"/#signup"
    if STRIPE_SECRET:
        pid=get_stripe_price(product)
        if not pid:setup_stripe();pid=get_stripe_price(product)
        if pid:
            session=stripe_call("POST","/checkout/sessions",{
                "mode":"subscription",
                "customer_email":email,
                "success_url":HOST+"/?success=true",
                "cancel_url":HOST+"/?cancel=true",
                "line_items[0][price]":pid,
                "line_items[0][quantity]":str(n)})
            if session and "url" in session:url=session["url"]
    with _trial_lock:_trial_checkout_cache[key]=(t,url)
    return url

def trial_state(created,is_paid):
    """Returns (in_trial, days_left). Paid accounts are never gated."""
    if is_paid:return True,None
    age=time.time()-(created or 0)
    left=TRIAL_DAYS-int(age//86400)
    return age<=TRIAL_DAYS*86400,max(0,left)

def create_key(email,phone="",name="",org="",org_type="",product="aileash",devices=1):
    email=str(email).strip().lower()
    if not email or "@" not in email:return None,"invalid_email"
    prefix={"sonicboom":"sb_live_","sentinel":"se_live_"}.get(product,"al_live_")
    key=prefix+secrets.token_hex(24)
    with _db_lock:
        r=_conn.execute("SELECT 1 FROM api_keys WHERE email=? AND product=?",(email,product)).fetchone()
        if r:return None,"email_exists"
        try:
            _conn.execute("INSERT INTO api_keys(key,email,phone,name,org,org_type,product,devices,stripe_customer,stripe_sub,actions_used,created,active,is_paid,free_quota,plan_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key,email,phone,name,org,org_type,product,devices,"","",0,time.time(),1,0,FREE_QUOTA,"trial"))
            _conn.commit()
        except sqlite3.IntegrityError:return None,"email_exists"
    return key,None

def get_key(key):
    with _db_lock:
        return _conn.execute("SELECT email,actions_used,active,is_paid,free_quota,plan_type,product,created FROM api_keys WHERE key=?",(key,)).fetchone()

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

GUARDIAN_PATTERNS=[
    (re.compile(r"\b(don'?t|do not)\s+tell\s+(your\s+)?(mum|mom|dad|parents|anyone)\b",re.I),"secrecy"),
    (re.compile(r"\b(keep\s+(this|it)\s+(a\s+)?secret|between\s+us|our\s+little\s+secret)\b",re.I),"secrecy"),
    (re.compile(r"\b(send|share|post)\s+(me\s+)?(a\s+)?(pic|pics|picture|photo|photos|image|nude|nudes)\b",re.I),"image_request"),
    (re.compile(r"\b(meet\s+(up|me)|come\s+over|where\s+do\s+you\s+live|what'?s\s+your\s+address)\b",re.I),"meeting"),
    (re.compile(r"\b(you'?re\s+so\s+mature|mature\s+for\s+your\s+age|our\s+age\s+gap\s+doesn'?t\s+matter)\b",re.I),"grooming_flattery"),
    (re.compile(r"\b(sex|sexy|horny|naked|touch\s+yourself)\b",re.I),"sexual"),
    (re.compile(r"\b(delete\s+(this|our)\s+(chat|messages|conversation)|clear\s+your\s+history)\b",re.I),"evidence_hiding"),
]
def guardian_check(text):
    """Returns FLAGGED (with categories) or UNRECOGNISED. Never 'safe'."""
    cats=sorted({c for pat,c in GUARDIAN_PATTERNS if pat.search(text or "")})
    if cats:
        return {"result":"FLAGGED","categories":cats,
                "advice":"This message matches patterns used to groom or manipulate. Do not reply. Show a trusted adult now. CEOP, Childline and 999 are one tap away."}
    return {"result":"UNRECOGNISED",
            "advice":"Guardian cannot judge this message. That does not mean it is safe. If anything feels wrong, trust that feeling and show an adult you trust."}
def gen_pair_code(name):
    base=re.sub(r"[^a-z0-9]","",(name or "child").lower())[:6] or "child"
    return base.upper()+"-"+secrets.token_hex(2).upper()
def guardian_seal(pair_code,kind,lat,lon,note,content_fp):
    """Seal a guardian event into the MAIN audit chain, then store the row."""
    ts=now()
    ev={"user_id":"guardian:"+pair_code,"action":"guardian_"+kind}
    res={"decision":"GUARDIAN","kind":kind,"version":VERSION,"timestamp":ts}
    h,idx,seq=seal(ev,res,ts,None)
    with _db_lock:
        _conn.execute("INSERT INTO guardian_events(pair_code,ts,kind,lat,lon,note,content_fp,audit_hash) VALUES(?,?,?,?,?,?,?,?)",
            (pair_code,ts,kind,lat,lon,note,content_fp,h))
        if kind=="checkin":
            _conn.execute("UPDATE guardian_family SET last_checkin=? WHERE pair_code=?",(ts,pair_code))
        _conn.commit()
    return h
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

def record_device(api_key,device_id):
    """Log each unique device_id that uses this key. Returns live unique device count.
    This is the real meter: you are billed for every distinct device you send the key to."""
    if not api_key or not device_id:return None
    with _db_lock:
        try:
            _conn.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",(api_key,device_id,time.time()))
            _conn.commit()
            n=_conn.execute("SELECT COUNT(*) FROM device_seen WHERE api_key=?",(api_key,)).fetchone()[0]
        except Exception as e:
            print("record_device err:"+str(e),flush=True);return None
    return n

def device_count(api_key):
    with _db_lock:
        try:return _conn.execute("SELECT COUNT(*) FROM device_seen WHERE api_key=?",(api_key,)).fetchone()[0]
        except:return 0

def govern(event,api_key=None):
    missing=REQ-event.keys()
    if missing:raise ValueError("Missing fields: "+str(missing))
    if api_key:
        ok,ec=check_rate(api_key)
        if not ok:return{"error":ec},429
        ki=get_key(api_key)
        if not ki:return{"error":"invalid_api_key"},401
        email,used,active,is_paid,quota,plan,product,created=ki
        if not active:return{"error":"account_inactive"},403
        in_trial,days_left=trial_state(created,is_paid)
        if not in_trial:
            return{"error":"trial_expired",
                "message":"Your "+str(TRIAL_DAYS)+"-day free trial has ended. Your keys, chain and devices are untouched - pay to continue exactly where you left off, or remove the integration. The bill reflects only the real devices that used your key.",
                "billable_devices":device_count(api_key),
                "rate_per_device_gbp":0.50,
                "checkout_url":trial_checkout(api_key,email,product)},402
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
        dcount=record_device(api_key,str(event.get("device_id","")))
        if dcount is not None:
            result["billable_devices"]=dcount
            result["monthly_charge_gbp"]=round(dcount*0.50,2)
        if not is_paid and days_left is not None:
            result["trial_days_left"]=days_left
        if dec=="BLOCK":
            threading.Thread(target=send_block_alert,args=(api_key,event,result),daemon=True).start()
    return result,200

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
  "ico_childrens_code":{"status":"in force","support":"deterministic scoring; no profiling of children; full audit trail"},
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
        rows=_conn.execute("SELECT key,org,active,is_paid,actions_used,free_quota,created FROM api_keys").fetchall()
    for k,org,active,is_paid,used,quota,created in rows:
        if badge_id_for_key(k)==badge_id:
            in_trial,_=trial_state(created,is_paid)
            ok=bool(active) and (bool(is_paid) or in_trial)
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
            if c:send_html(self,c)
            else:send_html(self,page_404(),404)
        elif path=="/reseller":
            c=load_file("reseller.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/scan":
            c=load_file("scan.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/contact":
            c=load_file("contact.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/sonicboom":
            c=load_file("sonicboom.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/seal":
            c=load_file("seal.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
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
        elif path=="/.well-known/ai.txt":
            c=load_file("static/.well-known/ai.txt")
            send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/.well-known/ai-manifest.json":
            c=load_file("static/.well-known/ai-manifest.json")
            send_text(self,c,"application/json") if c else send_json(self,{"error":"not found"},404)
        elif path=="/.well-known/ai-safety.txt":
            c=load_file("static/.well-known/ai-safety.txt")
            send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/.well-known/security.txt":
            c=load_file("static/.well-known/security.txt")
            send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/.well-known/comply.txt":
            c=load_file("static/.well-known/comply.txt")
            send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/spec/ai-txt":
            c=load_file("docs/spec/ai-txt.md")
            send_text(self,c,"text/markdown") if c else send_json(self,{"error":"not found"},404)
        elif path=="/api/verify-manifest":
            dom=qs.get("domain",[""])[0].strip().lower().replace("https://","").replace("http://","").strip("/")
            chain=verify_chain()
            with _db_lock:
                tip=_conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            if dom and dom!="sebbi.pro":
                send_json(self,{"domain":dom,"manifest_found":False,"verdict":"NO_MANIFEST",
                    "message":"No verifiable manifest registered for this domain. Publish one: "+HOST+"/spec/ai-txt",
                    "checked_at":time.time()})
            else:
                send_json(self,{"domain":"sebbi.pro","manifest_found":True,
                    "chain_valid":chain.get("valid"),"sealed_count":chain.get("blocks"),
                    "chain_tip":(tip[0] if tip else "GENESIS"),
                    "verdict":"VERIFIED" if chain.get("valid") else "CHAIN_BROKEN",
                    "verified_by":"AILeash - sebbi.pro","checked_at":time.time()})
        elif path=="/ai.txt":
            c=load_file("ai.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/brain.py":
            c=load_file("brain.py")
            if c:
                self.send_response(200);self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition","attachment; filename=\"brain.py\"")
                b=c.encode();self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/sebdog_engine.py":
            c=load_file("sebdog_engine.py")
            if c:
                self.send_response(200);self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition","attachment; filename=\"sebdog_engine.py\"")
                b=c.encode();self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/sebdog_licence.py":
            c=load_file("sebdog_licence.py")
            if c:
                self.send_response(200);self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition","attachment; filename=\"sebdog_licence.py\"")
                b=c.encode();self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/sebdog_reporter.py":
            c=load_file("sebdog_reporter.py")
            if c:
                self.send_response(200);self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition","attachment; filename=\"sebdog_reporter.py\"")
                b=c.encode();self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/aileash_reporter.py":
            c=load_file("aileash_reporter.py")
            if c:
                self.send_response(200);self.send_header("Content-Type","text/x-python")
                self.send_header("Content-Disposition","attachment; filename=\"aileash_reporter.py\"")
                b=c.encode();self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/aileash-compliance.zip":
            import os
            fp=os.path.join(os.path.dirname(os.path.abspath(__file__)),"aileash-compliance.zip")
            if os.path.exists(fp):
                with open(fp,"rb") as zf:data=zf.read()
                self.send_response(200);self.send_header("Content-Type","application/zip")
                self.send_header("Content-Disposition","attachment; filename=\"aileash-compliance.zip\"")
                self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
            else:send_json(self,{"error":"not found"},404)
        elif path=="/api-routes.md" or path=="/api-routes":
            c=load_file("api-routes.md")
            if c:send_text(self,c,"text/markdown")
            else:send_json(self,{"error":"not found"},404)
        elif path=="/comply.txt":
            c=load_file("comply.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-child":
            c=load_file("guardian-child.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian":
            c=load_file("guardian.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/guardian-parent":
            c=load_file("guardian-parent.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/certificate":
            c=load_file("certificate.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/registry":
            c=load_file("registry.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/admin":
            c=load_file("admin.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/brain":
            c=load_file("brain.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/green":
            c=load_file("green.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/dis.txt":
            c=load_file("dis.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/legal.txt":
            c=load_file("legal.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/liability.txt":
            c=load_file("liability.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/copyright.txt":
            c=load_file("copyright.txt");send_text(self,c,"text/plain") if c else send_json(self,{"error":"not found"},404)
        elif path=="/ai-txt-kit" or path=="/kit":
            c=load_file("ai-txt-kit.html");send_html(self,c) if c else send_json(self,{"error":"not found"},404)
        elif path=="/ai-txt-template.txt":
            c=load_file("ai-txt-template.txt")
            if c:
                self.send_response(200)
                self.send_header("Content-Type","text/plain; charset=utf-8")
                self.send_header("Content-Disposition","attachment; filename=\"ai.txt\"")
                self.end_headers();self.wfile.write(c.encode())
            else:send_json(self,{"error":"not found"},404)
        elif path=="/referrals":
            code=qs.get("code",[""])[0].strip().upper()
            send_html(self,referrals_page(code))
        elif path in("/verify","/identity","/notary","/pay-check","/dashboard","/pricing","/docs","/blog","/status","/about","/legal","/privacy","/terms"):
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
        elif path=="/api/payment/check":
            code=qs.get("code",[""])[0].strip().lower()
            fpq=qs.get("fp",[""])[0].strip().lower()
            if not code or len(code)<12:send_json(self,{"found":False,"error":"provide the 12-character code"},400);return
            with _db_lock:
                if len(code)==64:
                    r=_conn.execute("SELECT fp,ts,seal,block_index,display_json FROM payment_registry WHERE fp=?",(code,)).fetchone()
                else:
                    r=_conn.execute("SELECT fp,ts,seal,block_index,display_json FROM payment_registry WHERE fp LIKE ?",(code+"%",)).fetchone()
            if not r:
                ts=time.time()
                ev={"user_id":"payment_verifier","action":"payment_verification","amount":0,"country":"UK","device_id":"paycheck_"+code[:12],"anomaly":0,"device_risk":0,"checked_code":code[:12],"result":"NO_SEAL"}
                res={"decision":"VERIFICATION","score":0,"version":VERSION,"timestamp":ts,"result":"NO_SEAL"}
                h2,idx2,_=seal(ev,res,ts)
                send_json(self,{"found":False,"receipt":{"seal":h2,"block_index":idx2,"checked_at":ts,"result":"NO_SEAL"}});return
            out={"found":True,"registered_at":r[1],"seal":r[2],"block_index":r[3]}
            if r[4]:
                try:out["display"]=json.loads(r[4])
                except:pass
            result="FOUND"
            if fpq and len(fpq)==64:
                out["match"]=(fpq==r[0])
                result="MATCH" if out["match"] else "MISMATCH"
            ts=time.time()
            ev={"user_id":"payment_verifier","action":"payment_verification","amount":0,"country":"UK","device_id":"paycheck_"+code[:12],"anomaly":0,"device_risk":0,"checked_code":code[:12],"checked_fp":fpq or "","result":result}
            res={"decision":"VERIFICATION","score":0,"version":VERSION,"timestamp":ts,"result":result,"note":"payer verification sealed - proof of care under PSR mandatory reimbursement rules"}
            h2,idx2,_=seal(ev,res,ts)
            out["receipt"]={"seal":h2,"block_index":idx2,"checked_at":ts,"result":result}
            send_json(self,out)
        elif path=="/api/identity/check":
            q=qs.get("code",[""])[0].strip().lower()
            if not q or len(q)<12:send_json(self,{"found":False,"error":"provide at least 12 characters"},400);return
            with _db_lock:
                if len(q)==64:
                    r=_conn.execute("SELECT fp,ts,seal,block_index,public,profile_json FROM identity_registry WHERE fp=?",(q,)).fetchone()
                else:
                    r=_conn.execute("SELECT fp,ts,seal,block_index,public,profile_json FROM identity_registry WHERE fp LIKE ?",(q+"%",)).fetchone()
            if not r:send_json(self,{"found":False});return
            out={"found":True,"fingerprint":r[0],"registered_at":r[1],"seal":r[2],"block_index":r[3]}
            if r[4] and r[5]:
                try:out["profile"]=json.loads(r[5])
                except:pass
            send_json(self,out)
        elif path=="/api/verify-post":
            ch=qs.get("content",[""])[0].strip().lower()
            if not ch or len(ch)!=64:send_json(self,{"verified":False,"error":"provide a 64-char sha-256"},400);return
            with _db_lock:
                r=_conn.execute("SELECT ts,seal,block_index FROM post_registry WHERE fp=?",(ch,)).fetchone()
            if r:send_json(self,{"verified":True,"block_index":r[2],"sealed_at":r[0],"seal":r[1]})
            else:send_json(self,{"verified":False})
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
        elif path=="/api/guardian/report":
            email=qs.get("email",[""])[0].strip().lower()
            if not email:send_json(self,{"error":"email required"},400);return
            pc=qs.get("code",[""])[0].strip()
            with _db_lock:
                fam=_conn.execute("SELECT child_name,created,last_checkin FROM guardian_family WHERE pair_code=? AND parent_key=?",(pc,email)).fetchone()
                rows=_conn.execute("SELECT ts,kind,lat,lon,note,audit_hash FROM guardian_events WHERE pair_code=? ORDER BY ts DESC LIMIT 200",(pc,)).fetchall()
            if not fam:send_json(self,{"error":"not_found_or_not_yours"},404);return
            events=[{"ts":r[0],"kind":r[1],"lat":r[2],"lon":r[3],"note":r[4],"sealed":r[5][:16]} for r in rows]
            send_json(self,{"child":fam[0],"paired":fam[1],"last_checkin":fam[2],
                "events":events,
                "note":"Every event is sealed in the audit chain. Message content is never stored - only a fingerprint. This timeline is tamper-evident and can be independently verified."})
        elif path=="/api/guardian/children":
            email=qs.get("email",[""])[0].strip().lower()
            if not email:send_json(self,{"error":"email required"},400);return
            with _db_lock:
                rows=_conn.execute("SELECT pair_code,child_name,last_checkin FROM guardian_family WHERE parent_key=? ORDER BY created ASC",(email,)).fetchall()
            send_json(self,{"children":[{"code":r[0],"name":r[1],"last_checkin":r[2]} for r in rows]})
        elif path=="/api/usage":
            auth=get_bearer(self)
            if not auth:send_json(self,{"error":"api_key_required"},401);return
            n=device_count(auth)
            ki=get_key(auth)
            trial_note=""
            days_left=None
            if ki:
                _,_,_,is_paid,_,_,_,created=ki
                in_trial,days_left=trial_state(created,is_paid)
                if is_paid:trial_note="Paid account."
                elif in_trial:trial_note="Free trial: "+str(days_left)+" day(s) remaining. Billing begins only after the trial."
                else:trial_note="Trial ended. Pay to continue - the charge below reflects the real devices seen on this key."
            send_json(self,{"billable_devices":n,"rate_per_device_gbp":0.50,"monthly_charge_gbp":round(n*0.50,2),
                "trial_days_left":days_left,"trial_status":trial_note,
                "note":"You are billed 50p for every unique device that uses this key. This count is the real number of distinct devices seen, not a figure you set. Send the key to 20 million devices and the bill is for 20 million devices."})
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
                    sub_id=str(obj.get("subscription") or "")
                    cust_id=str(obj.get("customer") or "")
                    if email:
                        email=email.strip().lower()
                        with _db_lock:
                            _conn.execute("UPDATE api_keys SET is_paid=1,plan_type='paid' WHERE email=?",(email,))
                            if sub_id:_conn.execute("UPDATE api_keys SET stripe_sub=? WHERE email=? AND stripe_sub=''",(sub_id,email))
                            if cust_id:_conn.execute("UPDATE api_keys SET stripe_customer=? WHERE email=? AND stripe_customer=''",(cust_id,email))
                            _conn.commit()
                        print("PAID:"+email+(" sub:"+sub_id[:14] if sub_id else ""),flush=True)
                elif etype in("customer.subscription.deleted","invoice.payment_failed"):
                    email=(obj.get("customer_email") or "").strip().lower()
                    sub_id=str(obj.get("id") if etype=="customer.subscription.deleted" else obj.get("subscription") or "")
                    with _db_lock:
                        if email:
                            _conn.execute("UPDATE api_keys SET is_paid=0,plan_type='free' WHERE email=?",(email,))
                        elif sub_id:
                            _conn.execute("UPDATE api_keys SET is_paid=0,plan_type='free' WHERE stripe_sub=?",(sub_id,))
                        _conn.commit()
                    print("UNPAID:"+(email or sub_id),flush=True)
                send_json(self,{"ok":True})
            except Exception as e:print("Webhook:"+str(e),flush=True);send_json(self,{"ok":True})
            return

        data=read_body(self)

        if path in("/api/govern","/govern"):
            api_key=get_bearer(self)
            if not api_key:
                send_json(self,{"error":"api_key_required","message":"Get a free key at "+HOST+"/#signup"},401);return
            try:
                result,status=govern(data,api_key)
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
            if product not in("aileash","sonicboom","sentinel","guardian"):product="aileash"
            guide_product=product
            if product=="guardian":product="aileash"
            key,err=create_key(email,phone,name,org,org_type,product,devices)
            if err:
                msgs={"invalid_email":"Please enter a valid email address.","email_exists":"A key already exists for this email."}
                send_json(self,{"error":msgs.get(err,err)},400);return
            monthly=round(devices*0.50,2)
            if ref_code_used:
                threading.Thread(target=credit_referral,args=(ref_code_used,devices),daemon=True).start()
            new_ref_code=create_referral(key,email,name)
            threading.Thread(target=send_referral_welcome,args=(name,email,key,new_ref_code,product,monthly),daemon=True).start()
            threading.Thread(target=send_install_guide,args=(name,email,key,guide_product),daemon=True).start()
            signup_msg="Free for "+str(TRIAL_DAYS)+" days - full engine, no card. After the trial: 50p per unique device per month via Stripe, metered on real usage. Your installation guide is on its way to your inbox."
            bid=badge_id_for_key(key)
            send_json(self,{"api_key":key,"email":email,"product":product,"devices":devices,"monthly":monthly,"trial_days":TRIAL_DAYS,"ref_code":new_ref_code,"badge_id":bid,"badge_url":HOST+"/api/badge/shield?badge="+bid,"endpoint":HOST+"/api/govern","message":signup_msg})
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
            email,used,active,is_paid,quota,plan,product,created=ki
            if not active:send_json(self,{"valid":False,"error":"account_inactive"},403);return
            in_trial,days_left=trial_state(created,is_paid)
            if not in_trial:
                send_json(self,{"valid":False,"error":"trial_expired",
                    "message":"Your "+str(TRIAL_DAYS)+"-day free trial has ended. Pay to continue exactly where you left off.",
                    "billable_devices":device_count(api_key),
                    "checkout_url":trial_checkout(api_key,email,product)},402);return
            with _db_lock:devices=_conn.execute("SELECT devices FROM api_keys WHERE key=?",(api_key,)).fetchone()
            send_json(self,{"valid":True,"plan":plan,"product":product,"devices":devices[0] if devices else 1,"email":email,"trial_days_left":days_left})
        elif path=="/api/payment/seal":
            fp=str(data.get("fingerprint","")).strip().lower()
            if len(fp)!=64 or not all(c in "0123456789abcdef" for c in fp):
                send_json(self,{"sealed":False,"error":"valid sha-256 fingerprint required"},400);return
            with _db_lock:
                dup=_conn.execute("SELECT ts,seal,block_index FROM payment_registry WHERE fp=?",(fp,)).fetchone()
            if dup:
                send_json(self,{"sealed":True,"seal":dup[1],"block_index":dup[2],"sealed_at":dup[0],"code":fp[:12],"already_registered":True});return
            p=data.get("display",{})
            display=""
            if isinstance(p,dict):
                safe={k:str(p.get(k,""))[:120] for k in ("business","sort_masked","account_masked") if p.get(k)}
                display=json.dumps(safe)
            ts=time.time()
            ev={"user_id":"payment_notary","action":"payment_details_sealed","amount":0,"country":"UK","device_id":"paynotary_"+fp[:12],"anomaly":0,"device_risk":0,"payment_fp":fp}
            res={"decision":"NOTARISED","score":0,"version":VERSION,"timestamp":ts,"note":"payment details fingerprint sealed; full details never stored - only masked display fields"}
            h,idx,_=seal(ev,res,ts)
            with _db_lock:
                _conn.execute("INSERT OR IGNORE INTO payment_registry(fp,ts,seal,block_index,display_json) VALUES(?,?,?,?,?)",(fp,ts,h,idx,display))
                _conn.commit()
            send_json(self,{"sealed":True,"seal":h,"block_index":idx,"sealed_at":ts,"code":fp[:12]})
        elif path=="/api/identity/seal":
            fp=str(data.get("fingerprint","")).strip().lower()
            if len(fp)!=64 or not all(c in "0123456789abcdef" for c in fp):
                send_json(self,{"sealed":False,"error":"valid sha-256 fingerprint required"},400);return
            with _db_lock:
                dup=_conn.execute("SELECT ts,seal,block_index FROM identity_registry WHERE fp=?",(fp,)).fetchone()
            if dup:
                send_json(self,{"sealed":True,"seal":dup[1],"block_index":dup[2],"sealed_at":dup[0],"already_registered":True});return
            is_public=1 if data.get("public") else 0
            profile=""
            if is_public:
                p=data.get("profile",{})
                if isinstance(p,dict):
                    safe={k:str(p.get(k,""))[:300] for k in ("name","title","bio","linkedin","facebook","org") if p.get(k)}
                    profile=json.dumps(safe)
            ts=time.time()
            ev={"user_id":"identity_notary","action":"identity_sealed","amount":0,"country":"UK","device_id":"identity_"+fp[:12],"anomaly":0,"device_risk":0,"identity_fp":fp}
            res={"decision":"NOTARISED","score":0,"version":VERSION,"timestamp":ts,"note":"identity fingerprint sealed; raw identity stored only if user opted to publish"}
            h,idx,_=seal(ev,res,ts)
            with _db_lock:
                _conn.execute("INSERT OR IGNORE INTO identity_registry(fp,ts,seal,block_index,public,profile_json) VALUES(?,?,?,?,?,?)",(fp,ts,h,idx,is_public,profile))
                _conn.commit()
            send_json(self,{"sealed":True,"seal":h,"block_index":idx,"sealed_at":ts,"code":fp[:12]})
        elif path=="/api/post/seal":
            fp=str(data.get("fingerprint","")).strip().lower()
            if len(fp)!=64 or not all(c in "0123456789abcdef" for c in fp):
                send_json(self,{"sealed":False,"error":"valid sha-256 fingerprint required"},400);return
            with _db_lock:
                dup=_conn.execute("SELECT ts,seal,block_index FROM post_registry WHERE fp=?",(fp,)).fetchone()
            if dup:
                send_json(self,{"sealed":True,"seal":dup[1],"block_index":dup[2],"sealed_at":dup[0],"code":fp[:12],"already_registered":True});return
            ts=time.time()
            ev={"user_id":"post_notary","action":"post_sealed","amount":0,"country":"UK","device_id":"post_"+fp[:12],"anomaly":0,"device_risk":0,"post_fp":fp}
            res={"decision":"NOTARISED","score":0,"version":VERSION,"timestamp":ts,"note":"post content fingerprint sealed; content itself never stored"}
            h,idx,_=seal(ev,res,ts)
            with _db_lock:
                _conn.execute("INSERT OR IGNORE INTO post_registry(fp,ts,seal,block_index) VALUES(?,?,?,?)",(fp,ts,h,idx))
                _conn.commit()
            send_json(self,{"sealed":True,"seal":h,"block_index":idx,"sealed_at":ts,"code":fp[:12]})
        elif path=="/report-threat":
            ref="AIDX-"+hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:12].upper()
            with _db_lock:
                _conn.execute("INSERT INTO threat_log(ts,ref,data_json) VALUES(?,?,?)",(time.time(),ref,json.dumps(data)))
                _conn.commit()
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
        elif path=="/api/guardian/pair":
            email=str(data.get("parent_email","")).strip().lower()[:120]
            if not email or "@" not in email:send_json(self,{"error":"parent_email required"},400);return
            nm=str(data.get("child_name","")).strip()[:40]
            if not nm:send_json(self,{"error":"child_name required"},400);return
            with _db_lock:
                n=_conn.execute("SELECT COUNT(*) FROM guardian_family WHERE parent_key=?",(email,)).fetchone()[0]
            if n>=10:send_json(self,{"error":"max 10 children per account"},400);return
            pc=gen_pair_code(nm)
            with _db_lock:
                _conn.execute("INSERT INTO guardian_family(pair_code,parent_key,child_name,created,last_checkin) VALUES(?,?,?,?,0)",(pc,email,nm,now()))
                _conn.commit()
            send_json(self,{"ok":True,"pair_code":pc,"child_name":nm,
                "child_url":HOST+"/guardian-child?code="+pc,
                "note":"Open the child link on the child's phone and add it to their home screen. Everything the child shares or flags will appear in your report, sealed and provable."})
        elif path=="/api/guardian/checkin":
            pc=str(data.get("code","")).strip()
            with _db_lock:
                fam=_conn.execute("SELECT child_name FROM guardian_family WHERE pair_code=?",(pc,)).fetchone()
            if not fam:send_json(self,{"error":"unknown_code"},404);return
            lat=data.get("lat");lon=data.get("lon")
            try:lat=float(lat) if lat is not None else None
            except:lat=None
            try:lon=float(lon) if lon is not None else None
            except:lon=None
            h=guardian_seal(pc,"checkin",lat,lon,"",None)
            send_json(self,{"ok":True,"sealed":h[:16]})
        elif path=="/api/guardian/panic":
            pc=str(data.get("code","")).strip()
            with _db_lock:
                fam=_conn.execute("SELECT parent_key,child_name FROM guardian_family WHERE pair_code=?",(pc,)).fetchone()
            if not fam:send_json(self,{"error":"unknown_code"},404);return
            lat=data.get("lat");lon=data.get("lon")
            try:lat=float(lat) if lat is not None else None
            except:lat=None
            try:lon=float(lon) if lon is not None else None
            except:lon=None
            h=guardian_seal(pc,"panic",lat,lon,"child requested help",None)
            pk=get_key(fam[0])
            if pk:
                try:send_email(pk[0],pk[2] if len(pk)>2 else "",
                    "GUARDIAN ALERT: "+fam[1]+" tapped Help",
                    "<p><b>"+esc(fam[1])+"</b> tapped the Help button in Guardian at "+time.strftime("%H:%M on %d %b")+".</p>"+
                    ("<p>Location shared: <a href='https://maps.google.com/?q="+str(lat)+","+str(lon)+"'>view on map</a></p>" if lat and lon else "<p>No location was shared.</p>")+
                    "<p>This event is sealed in the audit chain ("+h[:16]+").</p><p>Check on them now. In an emergency call 999.</p>")
                except Exception as e:print("GUARDIAN EMAIL ERR:"+str(e),flush=True)
            send_json(self,{"ok":True,"sealed":h[:16],"help":{"childline":"0800 1111","emergency":"999","ceop":"https://www.ceop.police.uk/safety-centre/"}})
        elif path=="/api/guardian/flag":
            pc=str(data.get("code","")).strip()
            msg=str(data.get("message",""))[:2000]
            with _db_lock:
                fam=_conn.execute("SELECT parent_key,child_name FROM guardian_family WHERE pair_code=?",(pc,)).fetchone()
            if not fam:send_json(self,{"error":"unknown_code"},404);return
            verdict=guardian_check(msg)
            fp=hashlib.sha256(msg.encode()).hexdigest()[:16] if msg else None
            note=verdict["result"]+((":"+",".join(verdict["categories"])) if verdict.get("categories") else "")
            h=guardian_seal(pc,"flag",None,None,note,fp)
            if verdict["result"]=="FLAGGED":
                pk=get_key(fam[0])
                if pk:
                    try:send_email(pk[0],pk[2] if len(pk)>2 else "",
                        "Guardian flagged a message for "+fam[1],
                        "<p>Guardian flagged a message "+esc(fam[1])+" checked, matching: <b>"+esc(", ".join(verdict["categories"]))+"</b>.</p>"+
                        "<p>The message text is not stored - only a fingerprint. Talk to your child. CEOP and Childline can help.</p>"+
                        "<p>Sealed in the audit chain ("+h[:16]+").</p>")
                    except Exception as e:print("GUARDIAN EMAIL ERR:"+str(e),flush=True)
            send_json(self,{"result":verdict["result"],"categories":verdict.get("categories",[]),"advice":verdict["advice"],"sealed":h[:16],
                "help":{"childline":"0800 1111","emergency":"999","ceop":"https://www.ceop.police.uk/safety-centre/"}})
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
        elif path=="/api/generate-airgap-token":
            auth=get_bearer(self)
            ki=get_key(auth) if auth else None
            if not ki:send_json(self,{"error":"invalid_api_key"},401);return
            email,used,active,is_paid,quota,plan,product,created=ki
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
            want=["key","email","name","org","product","devices","actions_used","free_quota","is_paid","plan_type","created"]
            with _db_lock:
                have=set(row[1] for row in _conn.execute("PRAGMA table_info(api_keys)").fetchall())
                cols=[c for c in want if c in have]
                rows=_conn.execute("SELECT "+",".join(cols)+" FROM api_keys ORDER BY created DESC").fetchall()
            keys=[dict(zip(cols,r)) for r in rows]
            send_json(self,{"keys":keys})
        elif path=="/admin/referrals":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT code,referrer_email,referrer_name,devices_referred,earnings_pence,created FROM referrals ORDER BY created DESC").fetchall()
            refs=[{"code":r[0],"referrer_email":r[1],"referrer_name":r[2],"devices_referred":r[3],"earnings_pence":r[4],"created":r[5]} for r in rows]
            send_json(self,{"referrals":refs})
        elif path=="/admin/audit":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            limit=int(data.get("limit",200)) if isinstance(data,dict) else 200
            if limit>1000:limit=1000
            filt_key=str(data.get("api_key","")).strip() if isinstance(data,dict) else ""
            with _db_lock:
                cols=set(r[1] for r in _conn.execute("PRAGMA table_info(audit_log)").fetchall())
                has_key="api_key" in cols
                if filt_key and has_key:
                    rows=_conn.execute("SELECT id,ts,user_id,event_json,result_json,prev_hash,audit_hash FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT ?",(filt_key,limit)).fetchall()
                else:
                    rows=_conn.execute("SELECT id,ts,user_id,event_json,result_json,prev_hash,audit_hash FROM audit_log ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
            recs=[]
            for r in rows:
                try:res=json.loads(r[4]) if r[4] else {}
                except:res={}
                recs.append({"seq":r[0],"ts":r[1],"user_id":r[2],
                    "decision":res.get("decision",res.get("result","")),
                    "score":res.get("score",""),
                    "reasons":res.get("reasons",[]),
                    "prev_hash":r[5],"audit_hash":r[6]})
            chain=verify_chain()
            send_json(self,{"records":recs,"count":len(recs),"chain_valid":chain.get("valid"),"chain_blocks":chain.get("blocks"),"chain_tip":chain.get("tip")})
        elif path=="/admin/contacts":
            if not check_admin(self):send_json(self,{"error":"unauthorized"},401);return
            with _db_lock:
                rows=_conn.execute("SELECT ts,name,email,phone,org,message FROM contact_log ORDER BY ts DESC").fetchall()
            contacts=[{"ts":r[0],"name":r[1],"email":r[2],"phone":r[3],"org":r[4],"message":r[5]} for r in rows]
            send_json(self,{"contacts":contacts})
        else:
            send_json(self,{"error":"not_found"},404)

# ============================================================
# STRIPE QUANTITY SYNC - keeps billing matched to real devices
# Every 6 hours: for each paid key, compare live unique device
# count to the Stripe subscription quantity. If devices grew,
# raise the quantity so billing follows the meter. Never lowers
# quantity automatically - lower it manually in Stripe if a
# client genuinely shrinks.
# ============================================================
SYNC_INTERVAL=6*3600

def sync_stripe_quantities():
    if not STRIPE_SECRET:
        print("QSYNC skip: no STRIPE_SECRET",flush=True);return
    with _db_lock:
        rows=_conn.execute("SELECT key,email,stripe_sub FROM api_keys WHERE is_paid=1 AND active=1 AND stripe_sub!=''").fetchall()
    for key,email,sub_id in rows:
        try:
            n=device_count(key)
            if not n:continue
            sub=stripe_call("GET","/subscriptions/"+sub_id)
            if not sub or "items" not in sub:
                print("QSYNC no sub for "+email,flush=True);continue
            items=sub["items"].get("data",[])
            if not items:continue
            item=items[0]
            current=int(item.get("quantity",0) or 0)
            if n>current:
                r=stripe_call("POST","/subscription_items/"+item["id"],
                    {"quantity":str(n),"proration_behavior":"none"})
                if r and "id" in r:
                    print("QSYNC "+email+": "+str(current)+" -> "+str(n)+" devices",flush=True)
                else:
                    print("QSYNC FAIL "+email,flush=True)
        except Exception as e:
            print("QSYNC ERR "+email+": "+str(e),flush=True)

def _qsync_loop():
    time.sleep(120)
    while True:
        try:sync_stripe_quantities()
        except Exception as e:print("QSYNC LOOP ERR:"+str(e),flush=True)
        time.sleep(SYNC_INTERVAL)

if __name__=="__main__":
    print("AILeash Platform v"+VERSION+" starting on :"+str(PORT),flush=True)
    seal_regmap_if_changed()
    setup_stripe()
    threading.Thread(target=_qsync_loop,daemon=True).start()
    print("QSYNC thread started - device/billing sync every 6h",flush=True)
    server=ThreadedServer(("0.0.0.0",PORT),Handler)
    print("Ready.",flush=True)
    server.serve_forever()
