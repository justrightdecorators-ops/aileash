import json
import sqlite3
import hashlib
import time
import hmac
import os
from datetime import datetime
from collections import defaultdict
from collections import deque
from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

STRIPE_SECRET = os.environ.get("STRIPE_SECRET", "")
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = int(os.environ.get("PORT", 8080))
BASE_URL = os.environ.get("BASE_URL", "https://sebbi.pro")
SAFE = {"UK","US","DE","FR","CA","AU"}
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

def now(): return time.time()
def clamp(x): return max(0.0, min(1.0, x))
def sha(p): return hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
def make_key(email): return hmac.new(LICENCE_SECRET.encode(),(email+LICENCE_SECRET).encode(),hashlib.sha256).hexdigest()

gc = sqlite3.connect("aileash.db",check_same_thread=False)
gc.row_factory = sqlite3.Row
gc.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY,trust REAL DEFAULT 0.5,last_country TEXT)")
gc.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,user_id TEXT,event_json TEXT,result_json TEXT,prev_hash TEXT,audit_hash TEXT UNIQUE)")
gc.execute("CREATE TABLE IF NOT EXISTS system_log (id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,event_type TEXT,detail TEXT)")
gc.commit()

lc = sqlite3.connect("licences.db",check_same_thread=False)
lc.row_factory = sqlite3.Row
lc.execute("CREATE TABLE IF NOT EXISTS licences (id INTEGER PRIMARY KEY AUTOINCREMENT,email TEXT UNIQUE,company TEXT,licence_key TEXT,stripe_sub TEXT,status TEXT DEFAULT 'ACTIVE',created_ts REAL,expires_ts REAL)")
lc.commit()

def syslog(t,d=""): gc.execute("INSERT INTO system_log(ts,event_type,detail) VALUES(?,?,?)",(now(),t,d)); gc.commit()

def load_user(uid):
row = gc.execute("SELECT trust,last_country FROM users WHERE user_id=?",(uid,)).fetchone()
return {"trust":row[0],"last_country":row[1]} if row else {"trust":0.5,"last_country":None}

def save_user(uid,trust,country):
gc.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",(uid,trust,country))
gc.commit()

def prune(q,s):
c=now()-s
while q and q[0]<c: q.popleft()

def update_windows(uid):
t=now()
for q in [W60[uid],W5M[uid],W1H[uid]]: q.append(t)
prune(W60[uid],60); prune(W5M[uid],300); prune(W1H[uid],3600)

def chain_tip():
row=gc.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
return row[0] if row else "GENESIS"

def do_audit(event,result):
prev=chain_tip()
h=sha({"prev_hash":prev,"ts":now(),"event":event,"result":result})
gc.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",(now(),event["user_id"],json.dumps(event),json.dumps(result),prev,h))
gc.commit()
return h

def govern(event):
state=load_user(event["user_id"])
update_windows(event["user_id"])
v60=len(W60[event["user_id"]]); v5m=len(W5M[event["user_id"]]); v1h=len(W1H[event["user_id"]])
country=event.get("country","UK"); amount=event.get("amount",0)
device_risk=event.get("device_risk",0.1); anomaly=event.get("anomaly",0.05)
s=0.0
s+=(1.0-state["trust"])*0.30
s+=min(v60/20.0,1.0)*0.15
s+=min(v5m/50.0,1.0)0.10
s+=min(v1h/200.0,1.0)0.10
s+=min(amount/1000.0,1.0)0.15
s+=device_risk0.10
s+=anomaly0.10
if state["last_country"] and state["last_country"]!=country: s+=0.10
if country not in SAFE: s+=0.10
s=clamp(s)
decision="ALLOW" if s<0.35 else "CHALLENGE" if s<0.70 else "BLOCK"
reasons=[]
if state["trust"]<0.4: reasons.append("low_trust")
if v60>10: reasons.append("velocity_spike")
if amount>500: reasons.append("high_amount")
if device_risk>0.5: reasons.append("risky_device")
if state["last_country"] and state["last_country"]!=country: reasons.append("country_shift")
if country not in SAFE: reasons.append("unsafe_country")
if anomaly>0.5: reasons.append("behaviour_anomaly")
trust=state["trust"]
if decision=="ALLOW": trust+=(1.0-trust)0.01
elif decision=="CHALLENGE": trust-=trust0.02
elif decision=="BLOCK": trust-=trust0.08; syslog("BLOCK",json.dumps({"user":event["user_id"],"score":round(s,4),"reasons":reasons}))
trust=max(0.05,clamp(trust))
save_user(event["user_id"],trust,country)
result={"decision":decision,"score":round(s,4),"trust":round(trust,4),"reasons":reasons,"velocity":{"60s":v60,"5m":v5m,"1h":v1h},"explanation":{"trust_factor":round((1.0-state["trust"])*0.30,4),"amount_factor":round(min(amount/1000.0,1.0)0.15,4),"anomaly_factor":round(anomaly0.10,4),"country_shift":state["last_country"] is not None and state["last_country"]!=country,"unsafe_country":country not in SAFE},"human_oversight":{"required":decision!="ALLOW","urgency":"HIGH" if decision=="BLOCK" else "MEDIUM" if decision=="CHALLENGE" else "NONE"},"compliance":{"standard":"EU AI Act Articles 9 12 13 14","audit_chain":"SHA-256 chained ledger"}}
result["audit_hash"]=do_audit(event,result)
return result

def stripe_checkout(email,company):
params=urllib.parse.urlencode({"success_url":BASE_URL+"/success","cancel_url":BASE_URL,"mode":"subscription","line_items[0][price_data][currency]":"usd","line_items[0][price_data][product_data][name]":"AILeash Compliance","line_items[0][price_data][product_data][description]":"AI governance middleware. EU AI Act Article 9 compliant.","line_items[0][price_data][recurring][interval]":"month","line_items[0][price_data][unit_amount]":"9900","line_items[0][quantity]":"1","customer_email":email,"metadata[company]":company}).encode()
req=urllib.request.Request("https://api.stripe.com/v1/checkout/sessions",data=params,headers={"Authorization":"Bearer "+STRIPE_SECRET,"Content-Type":"application/x-www-form-urlencoded"})
return json.loads(urllib.request.urlopen(req,timeout=10).read())["url"]

PAGE = """<!DOCTYPE html>

<html lang="en">  
<head>  
<meta charset="UTF-8">  
<meta name="viewport" content="width=device-width,initial-scale=1.0">  
<title>AILeash - AI Governance and Compliance</title>  
<meta name="description" content="AI governance middleware. EU AI Act compliant. Real-time risk scoring, tamper-evident audit chain. $99/month. Deploy in 2 minutes.">  
<style>  
*{margin:0;padding:0;box-sizing:border-box}  
html{scroll-behavior:smooth}  
body{background:#080808;color:#ccc;font-family:'Courier New',monospace;line-height:1.7}  
nav{border-bottom:1px solid #141414;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:#080808;z-index:100}  
.logo{color:#00ff88;font-weight:bold;letter-spacing:3px;font-size:1.1rem}  
.logo span{color:#ccc}  
.nav-links a{color:#444;font-size:.78rem;text-decoration:none;margin-left:1.5rem}  
.nav-links a:hover{color:#00ff88}  
.nav-cta{background:#00ff88;color:#080808!important;padding:.3rem 1rem;font-weight:bold}  
.alert{background:rgba(255,160,0,.06);border-bottom:1px solid rgba(255,160,0,.15);padding:.5rem;text-align:center;font-size:.75rem;color:#ffa000;letter-spacing:2px}  
.hero{max-width:920px;margin:0 auto;padding:7rem 2rem 4rem;text-align:center}  
.eyebrow{display:inline-block;border:1px solid #1a1a1a;color:#444;padding:.25rem .8rem;font-size:.7rem;letter-spacing:3px;margin-bottom:2rem}  
h1{font-size:clamp(2rem,5vw,3.8rem);line-height:1.1;margin-bottom:1.5rem;color:#fff;letter-spacing:-2px}  
h1 em{color:#00ff88;font-style:normal}  
.hero-p{color:#555;max-width:620px;margin:0 auto 1rem;font-size:1rem}  
.hero-p2{color:#333;max-width:560px;margin:0 auto 3rem;font-size:.88rem}  
.btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:2.5rem}  
.btn{background:#00ff88;color:#080808;padding:.9rem 2.5rem;font-family:'Courier New',monospace;font-size:.95rem;font-weight:bold;border:none;cursor:pointer;text-decoration:none;display:inline-block;letter-spacing:1px}  
.btn:hover{background:#00dd77}  
.btn2{border:1px solid #1e1e1e;color:#555;padding:.9rem 2rem;font-family:'Courier New',monospace;font-size:.88rem;text-decoration:none;display:inline-block}  
.btn2:hover{border-color:#00ff88;color:#00ff88}  
.cmd{background:#0c0c0c;border:1px solid #161616;display:inline-block;padding:.6rem 1.5rem;color:#00ff88;font-size:.88rem;margin-bottom:.5rem}  
.metrics{display:flex;justify-content:center;flex-wrap:wrap;border-top:1px solid #0f0f0f;border-bottom:1px solid #0f0f0f;margin-bottom:6rem}  
.metric{padding:2rem 3rem;text-align:center;border-right:1px solid #0f0f0f}  
.metric:last-child{border-right:none}  
.mn{font-size:2rem;color:#00ff88;font-weight:bold;display:block}  
.ml{font-size:.68rem;color:#333;letter-spacing:2px}  
.sec{max-width:920px;margin:0 auto;padding:4rem 2rem}  
.sec-eye{font-size:.68rem;color:#00ff88;letter-spacing:4px;margin-bottom:.8rem}  
h2{font-size:1.7rem;color:#fff;margin-bottom:.7rem;letter-spacing:-.5px}  
.sec-p{color:#444;font-size:.9rem;max-width:580px;margin-bottom:3rem;line-height:1.8}  
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem}  
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem}  
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:1.2rem}  
.card{background:#0c0c0c;border:1px solid #161616;padding:1.6rem}  
.card-r{border-left:3px solid #ff3333}  
.card-g{border-left:3px solid #00ff88}  
.card-a{border-top:2px solid #ffa000}  
.ct{font-size:.68rem;letter-spacing:2px;margin-bottom:.6rem}  
.red{color:#ff3333}.green{color:#00ff88}.amber{color:#ffa000}  
.card h3{font-size:.9rem;color:#bbb;margin-bottom:.4rem}  
.card p{color:#383838;font-size:.83rem;line-height:1.7}  
.card ul{list-style:none;margin-top:.8rem}  
.card ul li{color:#383838;font-size:.82rem;padding:.25rem 0;border-bottom:1px solid #111}  
.card ul li:before{content:"-- ";color:#00ff88}  
.card ul li:last-child{border-bottom:none}  
.fine-box{background:#0c0c0c;border:1px solid #161616;border-left:4px solid #ff3333;padding:2rem;margin:2rem 0}  
.fine-box h3{color:#ff3333;font-size:.8rem;letter-spacing:2px;margin-bottom:1rem}  
.fine-row{display:flex;justify-content:space-between;align-items:center;padding:.6rem 0;border-bottom:1px solid #0f0f0f;flex-wrap:wrap;gap:.5rem}  
.fine-row:last-child{border-bottom:none}  
.fine-l{color:#555;font-size:.83rem}  
.fine-v{color:#ff3333;font-weight:bold;font-size:.95rem}  
.code-box{background:#030303;border:1px solid #141414;margin:2rem 0;overflow:hidden}  
.code-top{background:#0c0c0c;border-bottom:1px solid #141414;padding:.5rem 1rem;font-size:.72rem;color:#333;display:flex;justify-content:space-between}  
.code-top em{color:#00ff88;font-style:normal}  
pre{padding:1.2rem;overflow-x:auto;font-size:.83rem;line-height:1.9;color:#bbb}  
.g{color:#00ff88}.d{color:#333}.a{color:#ffa000}.w{color:#fff}  
.terminal{background:#020202;border:1px solid #00ff88;padding:1.5rem;margin:2rem 0;font-size:.8rem;line-height:2}  
.tok{color:#00ff88}.twarn{color:#ffa000}.tblock{color:#ff3333}.tdim{color:#1e1e1e}  
.cursor{display:inline-block;width:7px;height:12px;background:#00ff88;animation:blink 1s infinite;vertical-align:middle}  
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}  
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:1.2rem;margin:2rem 0}  
.step{background:#0c0c0c;border:1px solid #161616;padding:1.4rem;position:relative;overflow:hidden}  
.step-bg{position:absolute;top:-.8rem;right:.5rem;font-size:4rem;color:#0e0e0e;font-weight:bold;pointer-events:none}  
.step h3{color:#00ff88;font-size:.82rem;letter-spacing:1px;margin-bottom:.4rem;position:relative}  
.step p{color:#383838;font-size:.8rem;line-height:1.7;position:relative}  
.comp-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:1.2rem;margin:2rem 0}  
.comp-card{background:#0c0c0c;border:1px solid #161616;border-top:2px solid #ffa000;padding:1.6rem}  
.comp-card h3{color:#ffa000;font-size:.78rem;letter-spacing:2px;margin-bottom:.8rem}  
.comp-card p{color:#383838;font-size:.82rem;line-height:1.75;margin-bottom:.7rem}  
.comp-card ul{list-style:none}  
.comp-card ul li{color:#383838;font-size:.8rem;padding:.28rem 0;border-bottom:1px solid #0f0f0f}  
.comp-card ul li:before{content:"[OK] ";color:#00ff88}  
.comp-card ul li:last-child{border-bottom:none}  
.cmp-table{width:100%;border-collapse:collapse;margin:2rem 0;font-size:.82rem}  
.cmp-table th{text-align:left;padding:.7rem .8rem;border-bottom:1px solid #131313;color:#333;font-weight:normal;font-size:.7rem;letter-spacing:1px}  
.cmp-table td{padding:.7rem .8rem;border-bottom:1px solid #0d0d0d;color:#444}  
.cmp-table td:first-child{color:#666}  
.cmp-table tr:last-child td{border-bottom:none}  
.tok{color:#00ff88}.tag-no{color:#ff3333}.tag-part{color:#ffa000}  
.pricing-box{background:#0c0c0c;border:2px solid #00ff88;padding:2.5rem;max-width:500px;margin:0 auto}  
.price-n{font-size:3.5rem;color:#00ff88;font-weight:bold;line-height:1;text-align:center}  
.price-per{color:#333;font-size:.88rem;text-align:center;margin:.3rem 0 .5rem}  
.price-note{color:#252525;font-size:.75rem;text-align:center;margin-bottom:2rem}  
.feat-list{list-style:none;margin:1.2rem 0 1.8rem}  
.feat-list li{padding:.5rem 0;border-bottom:1px solid #111;font-size:.86rem;color:#777;display:flex;align-items:center;gap:.5rem}  
.feat-list li:before{content:"[OK]";color:#00ff88;font-size:.75rem;white-space:nowrap}  
.feat-list li:last-child{border-bottom:none}  
.field{margin:.65rem 0}  
.field label{display:block;font-size:.7rem;color:#333;letter-spacing:2px;margin-bottom:.25rem}  
.field input{width:100%;background:#070707;border:1px solid #1a1a1a;color:#ccc;padding:.65rem .8rem;font-family:'Courier New',monospace;font-size:.86rem;outline:none}  
.field input:focus{border-color:#00ff88}  
.pay-btn{display:block;width:100%;background:#00ff88;color:#080808;padding:1rem;font-family:'Courier New',monospace;font-size:.95rem;font-weight:bold;border:none;cursor:pointer;letter-spacing:1px;margin-top:1.2rem}  
.pay-btn:hover{background:#00dd77}  
.pay-btn:disabled{background:#1a1a1a;color:#333;cursor:not-allowed}  
.msg{padding:.7rem .9rem;margin-top:.7rem;font-size:.8rem;display:none}  
.msg-ok{background:rgba(0,255,136,.04);color:#00ff88;border:1px solid #00ff4422}  
.msg-err{background:rgba(255,51,51,.04);color:#ff3333;border:1px solid #ff333322}  
.guar{color:#252525;font-size:.73rem;text-align:center;margin-top:.8rem;line-height:1.6}  
.faq-item{border-bottom:1px solid #0d0d0d;padding:1.3rem 0}  
.faq-item h3{font-size:.88rem;color:#bbb;margin-bottom:.4rem}  
.faq-item p{color:#383838;font-size:.82rem;line-height:1.75}  
.sector-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.2rem;margin:2rem 0}  
.sector-card{background:#0c0c0c;border:1px solid #161616;border-top:2px solid #00ff88;padding:1.4rem}  
.sector-card h3{color:#00ff88;font-size:.82rem;letter-spacing:1px;margin-bottom:.4rem}  
.sector-card p{color:#383838;font-size:.8rem;line-height:1.7}  
footer{border-top:1px solid #0d0d0d;padding:2rem;text-align:center;color:#252525;font-size:.76rem;margin-top:5rem}  
footer a{color:#252525;text-decoration:none}  
footer a:hover{color:#00ff88}  
@media(max-width:700px){  
.grid2,.grid3{grid-template-columns:1fr}  
.metric{border-right:none;border-bottom:1px solid #0f0f0f;padding:1.5rem}  
.metric:last-child{border-bottom:none}  
.nav-links a:not(.nav-cta){display:none}  
h1{letter-spacing:-1px}  
}  
</style>  
</head>  
<body>  <nav>  
  <div class="logo">AI<span>Leash</span></div>  
  <div class="nav-links">  
    <a href="#problem">Why you need it</a>  
    <a href="#how">How it works</a>  
    <a href="#compliance">Compliance</a>  
    <a href="#pricing" class="nav-cta">Start now</a>  
  </div>  
</nav>  <div class="alert">EU AI ACT FULL ENFORCEMENT: 2 AUGUST 2026 &nbsp;|&nbsp; FINES UP TO 35 MILLION EUROS OR 7% GLOBAL TURNOVER</div>  <div class="hero">  
  <div class="eyebrow">AI GOVERNANCE INFRASTRUCTURE</div>  
  <h1>Your AI is making decisions.<br><em>Who is watching it?</em></h1>  
  <p class="hero-p">Every AI action your system takes creates legal liability. AILeash sits inside your application and governs every single decision in real time. Risk scored. Audited. Compliant. Automatically.</p>  
  <p class="hero-p2">Used by fintech, healthtech, legaltech, and any company deploying AI in the EU, UK, or US. If your AI makes decisions that affect people, you need this.</p>  
  <div class="btns">  
    <a href="#pricing" class="btn">Get compliant now -- $99/month</a>  
    <a href="#how" class="btn2">See how it works</a>  
  </div>  
  <div class="cmd">$ pip install aileash</div>  
  <div style="color:#1e1e1e;font-size:.73rem;margin-top:.4rem">Zero dependencies. Pure Python. Runs anywhere.</div>  
</div>  <div class="metrics">  
  <div class="metric"><span class="mn">0</span><span class="ml">DEPENDENCIES</span></div>  
  <div class="metric"><span class="mn">2 min</span><span class="ml">TO DEPLOY</span></div>  
  <div class="metric"><span class="mn">100%</span><span class="ml">AUDIT COVERAGE</span></div>  
  <div class="metric"><span class="mn">3</span><span class="ml">JURISDICTIONS</span></div>  
  <div class="metric"><span class="mn">35M</span><span class="ml">MAX FINE EUROS</span></div>  
</div>  <section class="sec" id="problem">  
  <div class="sec-eye">// THE PROBLEM</div>  
  <h2>The law has changed. Most companies have not.</h2>  
  <p class="sec-p">The EU AI Act is not coming. It is here. Prohibited AI practices have been enforceable since February 2025. Full high-risk enforcement hits on 2 August 2026. If you are deploying AI without governance infrastructure, you are already behind.</p>    <div class="fine-box">  
    <h3>WHAT NON-COMPLIANCE COSTS YOU</h3>  
    <div class="fine-row"><span class="fine-l">Prohibited AI practices (Article 5)</span><span class="fine-v">35M EUR or 7% global turnover</span></div>  
    <div class="fine-row"><span class="fine-l">High-risk system violations (Articles 9-15)</span><span class="fine-v">15M EUR or 3% global turnover</span></div>  
    <div class="fine-row"><span class="fine-l">Incorrect information to authorities</span><span class="fine-v">7.5M EUR or 1.5% global turnover</span></div>  
    <div class="fine-row"><span class="fine-l">GDPR + AI Act dual exposure (healthtech, fintech)</span><span class="fine-v">Combined penalties apply</span></div>  
  </div>    <div class="grid2" style="margin-top:2rem">  
    <div class="card card-r">  
      <div class="ct red">WHAT REGULATORS WILL ASK</div>  
      <h3>Can you prove what your AI decided?</h3>  
      <p>Every AI decision is a regulatory event. You need to show exactly what it decided, why, and what happened. If you cannot, you are exposed.</p>  
    </div>  
    <div class="card card-r">  
      <div class="ct red">THE MOST COMMON FAILURE</div>  
      <h3>Paper compliance does not survive scrutiny.</h3>  
      <p>A risk assessment document without engineering changes will be rejected. The EU AI Act requires technical and operational compliance, not just paperwork.</p>  
    </div>  
    <div class="card card-r">  
      <div class="ct red">THE HIDDEN EXPOSURE</div>  
      <h3>Third-party AI is your liability too.</h3>  
      <p>If you deploy AI built by someone else, you are still the responsible party. The vendor being compliant does not make you compliant.</p>  
    </div>  
    <div class="card card-r">  
      <div class="ct red">THE TIMING PROBLEM</div>  
      <h3>You cannot build this at the last minute.</h3>  
      <p>Audit chains need to exist from the moment your system goes live. Historical gaps in your log are evidence of non-compliance, not just missing data.</p>  
    </div>  
  </div>  
</section>  <section class="sec">  
  <div class="sec-eye">// WHO NEEDS THIS</div>  
  <h2>If your AI makes decisions, you are in scope.</h2>  
  <p class="sec-p">The EU AI Act applies to any organisation that provides or deploys A
