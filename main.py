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

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/": self.landing()
        elif path=="/api/govern": self.govern_get()
        elif path=="/api/verify": self.verify_get()
        elif path=="/health": self.health()
        else: err(self,"Not found",404)
    
    def do_POST(self):
        path=urlparse(self.path).path
        length=int(self.headers.get("Content-Length",0))
        body=self.rfile.read(length).decode()
        try: data=json.loads(body) if body else {}
        except: return err(self,"Invalid JSON",400)
        
        if path=="/api/govern": self.govern_post(data)
        elif path=="/api/keys": self.create_key(data)
        else: err(self,"Not found",404)
    
    def landing(self):
        with open("landing.html","r") as f:
            send_html(self,f.read())
    
    def govern_get(self):
        err(self,"POST required",405)
    
    def govern_post(self,data):
        try:
            result=govern(data,get_key(self))
            send(self,result)
        except ValueError as e:
            err(self,str(e),400)
        except Exception as e:
            err(self,str(e),500)
    
    def verify_get(self):
        result=verify_chain()
        send(self,result)
    
    def health(self):
        send(self,{"status":"ok","version":VERSION})
    
    def create_key(self,data):
        email=data.get("email")
        stripe_customer=data.get("stripe_customer","")
        if not email: return err(self,"email required",400)
        key=create_api_key(email,stripe_customer)
        send(self,{"key":key,"email":email},201)
    
    def log_message(self,format,*args): pass

def main():
    setup_stripe()
    server=HTTPServer(("0.0.0.0",PORT),RequestHandler)
    print(f"AILeash v{VERSION} running on port {PORT}")
    server.serve_forever()

if __name__=="__main__":
    main()
