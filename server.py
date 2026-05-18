import json
import sqlite3
import hashlib
import time
import hmac
import os
from datetime import datetime
from collections import Counter
from collections import defaultdict
from collections import deque
from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

STRIPE_SECRET = os.environ.get("STRIPE_SECRET", "")
LICENCE_SECRET = hashlib.sha256(b"monopcontent_aileash_2026").hexdigest()
PORT = int(os.environ.get("PORT", 8080))

SAFE = {"UK","US","DE","FR","CA","AU"}
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

def now(): return time.time()

def clamp(x):
    if x < 0.0: return 0.0
    if x > 1.0: return 1.0
    return x

def sha(p):
    return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def make_licence_key(email):
    return hmac.new(
        LICENCE_SECRET.encode(),
        (email + LICENCE_SECRET).encode(),
        hashlib.sha256
    ).hexdigest()

gc = sqlite3.connect("aileash.db", check_same_thread=False)
gc.row_factory = sqlite3.Row
gc.execute(
    "CREATE TABLE IF NOT EXISTS users ("
    "user_id TEXT PRIMARY KEY,"
    "trust REAL DEFAULT 0.5,"
    "last_country TEXT)"
)
gc.execute(
    "CREATE TABLE IF NOT EXISTS audit_log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts REAL, user_id TEXT,"
    "event_json TEXT, result_json TEXT,"
    "prev_hash TEXT, audit_hash TEXT UNIQUE)"
)
gc.commit()

lc = sqlite3.connect("licences.db", check_same_thread=False)
lc.row_factory = sqlite3.Row
lc.execute(
    "CREATE TABLE IF NOT EXISTS licences ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "email TEXT UNIQUE, company TEXT,"
    "licence_key TEXT,"
    "stripe_customer TEXT,"
    "stripe_subscription TEXT,"
    "status TEXT DEFAULT 'ACTIVE',"
    "created_ts REAL,"
    "expires_ts REAL)"
)
lc.commit()

def load_user(uid):
    row = gc.execute(
        "SELECT trust, last_country FROM users WHERE user_id=?", (uid,)
    ).fetchone()
    if row:
        return {"trust": row[0], "last_country": row[1]}
    return {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    gc.execute(
        "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " trust=excluded.trust,"
        " last_country=excluded.last_country",
        (uid, trust, country)
    )
    gc.commit()

def prune(q, s):
    c = now() - s
    while q and q[0] < c:
        q.popleft()

def update_windows(uid):
    t = now()
    W60[uid].append(t)
    W5M[uid].append(t)
    W1H[uid].append(t)
    prune(W60[uid], 60)
    prune(W5M[uid], 300)
    prune(W1H[uid], 3600)

def chain_tip():
    row = gc.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row: return row[0]
    return "GENESIS"

def do_audit(event, result):
    prev = chain_tip()
    payload = {"prev_hash": prev, "ts": now(), "event": event, "result": result}
    h = sha(payload)
    gc.execute(
        "INSERT INTO audit_log"
        "(ts,user_id,event_json,result_json,prev_hash,audit_hash)"
        " VALUES(?,?,?,?,?,?)",
        (now(), event["user_id"], json.dumps(event), json.dumps(result), prev, h)
    )
    gc.commit()
    return h

def govern(event):
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v60 = len(W60[event["user_id"]])
    v5m = len(W5M[event["user_id"]])
    v1h = len(W1H[event["user_id"]])
    country = event.get("country", "UK")
    amount = event.get("amount", 0)
    device_risk = event.get("device_risk", 0.1)
    anomaly = event.get("anomaly", 0.05)
    s = 0.0
    s += (1.0 - state["trust"]) * 0.30
    s += min(v60 / 20.0, 1.0) * 0.15
    s += min(v5m / 50.0, 1.0) * 0.10
    s += min(v1h / 200.0, 1.0) * 0.10
    s += min(amount / 1000.0, 1.0) * 0.15
    s += device_risk * 0.10
    s += anomaly * 0.10
    if state["last_country"] and state["last_country"] != country: s += 0.10
    if country not in SAFE: s += 0.10
    s = clamp(s)
    if s < 0.35: decision = "ALLOW"
    elif s < 0.70: decision = "CHALLENGE"
    else: decision = "BLOCK"
    reasons = []
    if state["trust"] < 0.4: reasons.append("low_trust")
    if v60 > 10: reasons.append("velocity_spike")
    if amount > 500: reasons.append("high_amount")
    if device_risk > 0.5: reasons.append("risky_device")
    if state["last_country"] and state["last_country"] != country:
        reasons.append("country_shift")
    if country not in SAFE: reasons.append("unsafe_country")
    if anomaly > 0.5: reasons.append("behaviour_anomaly")
    trust = state["trust"]
    if decision == "ALLOW": trust += (1.0 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK": trust -= trust * 0.08
    trust = clamp(trust)
    if trust < 0.05: trust = 0.05
    save_user(event["user_id"], trust, country)
    result = {
        "decision": decision,
        "score": round(s, 4),
        "trust": round(trust, 4),
        "reasons": reasons
    }
    result["audit_hash"] = do_audit(event, result)
    return result

def create_stripe_checkout(email, company):
    params = urllib.parse.urlencode({
        "success_url": "https://sebbi.pro/success",
        "cancel_url": "https://sebbi.pro",
        "mode": "subscription",
        "line_items[0][price_data][currency]": "usd",
        "line_items[0][price_data][product_data][name]": "AILeash Compliance",
        "line_items[0][price_data][product_data][description]": "AI governance and compliance middleware. EU AI Act ready.",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][price_data][unit_amount]": "9900",
        "line_items[0][quantity]": "1",
        "customer_email": email,
        "metadata[company]": company,
    }).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=params,
        headers={
            "Authorization": "Bearer " + STRIPE_SECRET,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    resp = urllib.request.urlopen(req)
    session = json.loads(resp.read())
    return session["url"]

LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash - AI Compliance Infrastructure</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e8e8e8;font-family:'Courier New',monospace;line-height:1.7}
nav{border-bottom:1px solid #1a1a1a;padding:1.2rem 2rem;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;background:#0a0a0a;z-index:100}
.logo{font-size:1.3rem;color:#00ff88;font-weight:bold;letter-spacing:3px}
.logo span{color:#e8e8e8}
.nav-right{color:#ffaa00;font-size:.8rem;letter-spacing:1px}
.hero{max-width:900px;margin:0 auto;padding:6rem 2rem 4rem;text-align:center}
.urgent{display:inline-block;background:rgba(255,170,0,.1);border:1px solid #ffaa00;color:#ffaa00;padding:.4rem 1.2rem;font-size:.8rem;letter-spacing:2px;margin-bottom:2rem}
h1{font-size:clamp(2.2rem,5vw,3.8rem);line-height:1.15;margin-bottom:1.5rem;letter-spacing:-1px}
h1 em{color:#00ff88;font-style:normal}
.hero-sub{font-size:1.1rem;color:#888;max-width:650px;margin:0 auto 1rem}
.hero-sub2{font-size:.95rem;color:#555;max-width:600px;margin:0 auto 3rem}
.cta-area{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:4rem}
.btn-main{background:#00ff88;color:#0a0a0a;padding:.9rem 2.5rem;font-family:'Courier New',monospace;font-size:1rem;font-weight:bold;border:none;cursor:pointer;letter-spacing:1px;text-decoration:none;display:inline-block}
.btn-main:hover{background:#00cc66}
.btn-sec{border:1px solid #333;color:#888;padding:.9rem 2rem;font-family:'Courier New',monospace;font-size:.9rem;text-decoration:none;display:inline-block}
.btn-sec:hover{border-color:#00ff88;color:#00ff88}
.stats{display:flex;justify-content:center;flex-wrap:wrap;border-top:1px solid #1a1a1a;border-bottom:1px solid #1a1a1a;margin:0 0 5rem}
.stat{padding:2rem 3rem;text-align:center;border-right:1px solid #1a1a1a}
.stat:last-child{border-right:none}
.stat-n{font-size:2.2rem;color:#00ff88;font-weight:bold;display:block}
.stat-l{font-size:.75rem;color:#555;letter-spacing:2px}
.section{max-width:900px;margin:0 auto;padding:4rem 2rem}
.section-label{font-size:.7rem;color:#00ff88;letter-spacing:4px;margin-bottom:1rem}
h2{font-size:1.9rem;margin-bottom:1rem;letter-spacing:-.5px}
.section-sub{color:#666;margin-bottom:3rem;max-width:600px;font-size:.95rem}
.problem-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem;margin:2rem 0}
.problem-card{background:#0f0f0f;border:1px solid #1a1a1a;border-left:3px solid #ff4444;padding:1.5rem}
.problem-card h3{color:#ff4444;font-size:.9rem;margin-bottom:.5rem;letter-spacing:1px}
.problem-card p{color:#666;font-size:.85rem}
.solution-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem;margin:2rem 0}
.solution-card{background:#0f0f0f;border:1px solid #1a1a1a;border-left:3px solid #00ff88;padding:1.5rem}
.solution-card h3{color:#00ff88;font-size:.9rem;margin-bottom:.5rem;letter-spacing:1px}
.solution-card p{color:#666;font-size:.85rem}
.code-block{background:#050505;border:1px solid #1a1a1a;padding:1.5rem;margin:2rem 0;overflow-x:auto}
.code-block pre{font-size:.88rem;line-height:1.8;color:#e8e8e8}
.g{color:#00ff88}.m{color:#555}.a{color:#ffaa00}
.how-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.5rem;margin:2rem 0}
.step{background:#0f0f0f;border:1px solid #1a1a1a;padding:1.5rem}
.step-n{font-size:2rem;color:#00ff88;font-weight:bold;margin-bottom:.5rem}
.step h3{font-size:.95rem;margin-bottom:.5rem}
.step p{color:#666;font-size:.85rem}
.law-box{background:#0f0f0f;border:1px solid #ffaa00;padding:2rem;margin:2rem 0}
.law-box h3{color:#ffaa00;margin-bottom:1rem}
.law-box p{color:#888;font-size:.9rem;margin-bottom:.5rem}
.law-box ul{margin-left:1.5rem;color:#666;font-size:.85rem}
.law-box ul li{margin:.3rem 0}
.pricing{background:#0f0f0f;border:2px solid #00ff88;padding:2.5rem;max-width:480px;margin:2rem auto;text-align:center}
.price-main{font-size:3.5rem;color:#00ff88;font-weight:bold}
.price-main span{font-size:1rem;color:#555}
.price-sub{color:#555;font-size:.85rem;margin-bottom:2rem}
.feature-list{text-align:left;list-style:none;margin:1.5rem 0}
.feature-list li{padding:.5rem 0;border-bottom:1px solid #1a1a1a;font-size:.9rem;color:#e8e8e8}
.feature-list li:before{content:"[OK] ";color:#00ff88}
.feature-list li:last-child{border-bottom:none}
.form-group{margin:.8rem 0;text-align:left}
.form-group label{font-size:.75rem;color:#555;display:block;margin-bottom:.3rem;letter-spacing:1px}
.form-group input{width:100%;background:#0a0a0a;border:1px solid #222;color:#e8e8e8;padding:.7rem;font-family:'Courier New',monospace;font-size:.9rem}
.form-group input:focus{outline:none;border-color:#00ff88}
.pay-btn{display:block;background:#00ff88;color:#0a0a0a;padding:1rem;font-family:'Courier New',monospace;font-size:1rem;font-weight:bold;border:none;cursor:pointer;width:100%;margin-top:1.5rem;letter-spacing:1px}
.pay-btn:hover{background:#00cc66}
.msg{padding:1rem;margin-top:1rem;font-size:.85rem;display:none}
.msg-ok{background:rgba(0,255,136,.05);color:#00ff88;border:1px solid #00ff88}
.msg-err{background:rgba(255,68,68,.05);color:#ff4444;border:1px solid #ff4444}
.guarantee{color:#555;font-size:.8rem;margin-top:1rem;text-align:center}
.testimonial-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1.5rem;margin:2rem 0}
.testimonial{background:#0f0f0f;border:1px solid #1a1a1a;padding:1.5rem}
.testimonial p{color:#888;font-size:.88rem;margin-bottom:1rem;line-height:1.6}
.testimonial-name{color:#00ff88;font-size:.8rem;letter-spacing:1px}
.faq-item{border-bottom:1px solid #1a1a1a;padding:1.5rem 0}
.faq-item h3{font-size:.95rem;margin-bottom:.5rem;color:#e8e8e8}
.faq-item p{color:#666;font-size:.88rem}
footer{border-top:1px solid #1a1a1a;padding:2rem;text-align:center;color:#444;font-size:.8rem;margin-top:5rem}
footer a{color:#444;text-decoration:none}
footer a:hover{color:#00ff88}
@media(max-width:600px){.stat{border-right:none;border-bottom:1px solid #1a1a1a;padding:1.5rem}.hero{padding:3rem 1.5rem 2rem}.section{padding:3rem 1.5rem}}
</style>
</head>
<body>

<nav>
  <div class="logo">AI<span>Leash</span></div>
  <div class="nav-right">EU AI ACT: AUGUST 2026</div>
</nav>

<div class="hero">
  <div class="urgent">ENFORCEMENT DEADLINE: AUGUST 2026</div>
  <h1>Your AI is making decisions.<br><em>Who is watching it?</em></h1>
  <p class="hero-sub">AILeash is compliance infrastructure for any business deploying AI. Every decision your AI makes is scored, governed, and locked into a tamper-evident audit chain in real time.</p>
  <p class="hero-sub2">EU AI Act. UK AI framework. US state legislation. One system covers all of it. Deploy in minutes. Stay compliant forever.</p>
  <div class="cta-area">
    <a href="#pricing" class="btn-main">Start for $99 / month</a>
    <a href="#how" class="btn-sec">See how it works</a>
  </div>
</div>

<div class="stats">
  <div class="stat"><span class="stat-n">0</span><span class="stat-l">DEPENDENCIES</span></div>
  <div class="stat"><span class="stat-n">2 min</span><span class="stat-l">TO DEPLOY</span></div>
  <div class="stat"><span class="stat-n">100%</span><span class="stat-l">AUDIT COVERAGE</span></div>
  <div class="stat"><span class="stat-n">3</span><span class="stat-l">JURISDICTIONS</span></div>
</div>

<section class="section">
  <div class="section-label">// THE PROBLEM</div>
  <h2>AI legislation is here. Most companies are not ready.</h2>
  <p class="section-sub">The EU AI Act came into force in August 2024. Full enforcement begins August 2026. Companies deploying AI without proper governance face fines of up to 30 million euros or 6% of global turnover.</p>
  <div class="problem-grid">
    <div class="problem-card">
      <h3>NO AUDIT TRAIL</h3>
      <p>You cannot prove what your AI decided, when it decided it, or why. Regulators will ask. You will not have an answer.</p>
    </div>
    <div class="problem-card">
      <h3>NO RISK SCORING</h3>
      <p>Your AI treats every action the same. High risk transactions, anomalous behaviour, and geographic threats go undetected.</p>
    </div>
    <div class="problem-card">
      <h3>NO INCIDENT LOG</h3>
      <p>When something goes wrong — and it will — you have no record of what happened. That is a legal liability, not just a technical problem.</p>
    </div>
    <div class="problem-card">
      <h3>NO TRUST ENGINE</h3>
      <p>Your AI has no memory. It cannot learn which agents are trustworthy and which are becoming a threat. Every session starts from zero.</p>
    </div>
  </div>
</section>

<section class="section">
  <div class="section-label">// THE SOLUTION</div>
  <h2>AILeash. Drop it in. Walk away compliant.</h2>
  <p class="section-sub">AILeash sits inside your existing system as invisible infrastructure. Every AI action is governed before it executes. Every decision is logged. Every anomaly is caught. You do nothing except stay compliant.</p>
  <div class="solution-grid">
    <div class="solution-card">
      <h3>REAL-TIME RISK SCORING</h3>
      <p>Every AI action scored across trust, velocity, transaction size, device risk, geographic signals, and behavioural anomaly. Decisions in milliseconds.</p>
    </div>
    <div class="solution-card">
      <h3>TAMPER-EVIDENT AUDIT CHAIN</h3>
      <p>Every decision locked into a SHA-256 chained ledger from the moment your system starts. Any tampering is mathematically detectable. Regulators trust it.</p>
    </div>
    <div class="solution-card">
      <h3>TRUST ENGINE</h3>
      <p>Per-agent trust scores that evolve with behaviour. Good actors earn trust over time. Bad actors lose it permanently. Your system gets smarter every day.</p>
    </div>
    <div class="solution-card">
      <h3>VELOCITY DETECTION</h3>
      <p>Three overlapping time windows catch burst attacks and unusual activity patterns that single-threshold systems miss completely.</p>
    </div>
    <div class="solution-card">
      <h3>AUTOMATIC BLOCKING</h3>
      <p>High-risk actions are blocked before they execute. Suspicious actions are flagged for review. Safe actions pass through instantly. All three outcomes logged.</p>
    </div>
    <div class="solution-card">
      <h3>ZERO DEPENDENCIES</h3>
      <p>Pure Python. SQLite. Nothing else. Runs on any server, any cloud, any device. No vendor lock-in. No infrastructure changes. No downtime.</p>
    </div>
  </div>
</section>

<section class="section" id="how">
  <div class="section-label">// HOW IT WORKS</div>
  <h2>One command. Fully compliant.</h2>
  <p class="section-sub">AILeash installs as middleware inside your existing Flask or FastAPI application. No architecture changes. No rewrites. It wraps your existing routes and governs every request automatically.</p>

  <div class="code-block">
    <pre><span class="m"># Install</span>
<span class="g">pip install aileash</span>

<span class="m"># Add to your Flask app -- one line</span>
<span class="g">import</span> aileash
aileash<span class="a">.flask_middleware</span>(app)

<span class="m"># Every route is now governed. No other changes needed.</span>
<span class="m"># ALLOW, CHALLENGE, or BLOCK -- automatic.</span>
<span class="m"># Full audit chain -- automatic.</span>
<span class="m"># Trust scoring -- automatic.</span></pre>
  </div>

  <div class="how-steps">
    <div class="step"><div class="step-n">01</div><h3>Sign up</h3><p>Pay $99/month. Receive your licence key instantly by email.</p></div>
    <div class="step"><div class="step-n">02</div><h3>Install</h3><p>pip install aileash. Add your licence key. One line in your application.</p></div>
    <div class="step"><div class="step-n">03</div><h3>Govern</h3><p>Every AI action scored and audited in real time. Automatically.</p></div>
    <div class="step"><div class="step-n">04</div><h3>Prove it</h3><p>Show regulators your audit chain. Every decision logged. Nothing missing.</p></div>
  </div>
</section>

<section class="section">
  <div class="section-label">// LEGAL FRAMEWORK</div>
  <h2>Built for the legislation that is coming for you.</h2>
  <div class="law-box">
    <h3>EU AI ACT -- ENFORCEMENT AUGUST 2026</h3>
    <p>Article 9 requires a risk management system for all high-risk AI applications. AILeash delivers:</p>
    <ul>
      <li>Continuous risk identification and analysis</li>
      <li>Risk management measures and controls</li>
      <li>Testing and incident logging</li>
      <li>Tamper-evident audit trail with full decision history</li>
    </ul>
  </div>
  <div class="law-box">
    <h3>UK AI FRAMEWORK</h3>
    <p>The UK government requires organisations to be able to explain and audit AI decisions. AILeash provides a complete explainable decision log for every action your AI takes.</p>
  </div>
  <div class="law-box">
    <h3>US STATE LEGISLATION</h3>
    <p>Colorado, California, Texas and 12 other states have active AI legislation. Federal frameworks are accelerating. AILeash positions you ahead of every jurisdiction now moving.</p>
  </div>
</section>

<section class="section">
  <div class="section-label">// WHO NEEDS THIS</div>
  <h2>If you deploy AI, you need AILeash.</h2>
  <div class="problem-grid">
    <div class="solution-card">
      <h3>FINTECH</h3>
      <p>AI credit scoring, fraud detection, trading systems. Every decision is a regulatory event. You need a log.</p>
    </div>
    <div class="solution-card">
      <h3>HEALTHTECH</h3>
      <p>AI triage, diagnostic support, patient data processing. GDPR plus AI Act. Double exposure. Single solution.</p>
    </div>
    <div class="solution-card">
      <h3>LEGALTECH</h3>
      <p>AI contract review, case analysis, document processi
