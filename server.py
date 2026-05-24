
import os
import time
import json
import hashlib
import urllib.request
import urllib.parse

from flask import Flask, request, jsonify, redirect

app = Flask(__name__)

PORT = int(os.getenv("PORT", 8080))
STRIPE_KEY = os.getenv("STRIPE_KEY", "")
BASE_URL = os.getenv("BASE_URL", "https://sebbi.pro")
FREE_TIER_LIMIT = 1000

_keys = {}
_audit = []

def generate_key(email, plan="free"):
    raw = email + str(time.time()) + "aileash_secret_2026"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    _keys[key] = {"email": email, "plan": plan, "created": time.time()}
    return key

def validate_key(key):
    return _keys.get(key)

def upgrade_key(key):
    if key in _keys:
        _keys[key]["plan"] = "paid"
        return True
    return False

def log_event(user, event, decision, score):
    _audit.append({"ts": time.time(), "user": user, "event": event, "decision": decision, "score": score})

def count_for_user(user):
    return sum(1 for x in _audit if x["user"] == user)

def score_event(event):
    amount = float(event.get("amount", 0))
    device = float(event.get("device_risk", 0.1))
    anomaly = float(event.get("anomaly", 0.05))
    s = (amount / 10000) * 0.3 + device * 0.3 + anomaly * 0.4
    return round(max(0.0, min(1.0, s)), 4)

def decide(s):
    if s < 0.3: return "ALLOW"
    if s < 0.7: return "CHALLENGE"
    return "BLOCK"

def create_checkout(email, api_key):
    if not STRIPE_KEY or not STRIPE_KEY.startswith("sk_"):
        return None
    data = urllib.parse.urlencode({
        "success_url": BASE_URL + "/success?key=" + api_key,
        "cancel_url": BASE_URL,
        "mode": "subscription",
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][product_data][name]": "AILeash Pro",
        "line_items[0][price_data][product_data][description]": "Unlimited AI governance. EU AI Act compliant.",
        "line_items[0][price_data][unit_amount]": "4900",
        "line_items[0][price_data][recurring][interval]": "month",
        "line_items[0][quantity]": "1",
        "metadata[api_key]": api_key,
    }).encode()
    req = urllib.request.Request(
        "https://api.stripe.com/v1/checkout/sessions",
        data=data,
        headers={
            "Authorization": "Bearer " + STRIPE_KEY,
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read())["url"]

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash - AI Compliance Infrastructure</title>
<meta name="description" content="AILeash governs every AI decision in real time. EU AI Act compliant. Free tier available. Pro from £49/month.">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{background:#ffffff;color:#1a1a1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;line-height:1.6}
a{text-decoration:none;color:inherit}

nav{background:#fff;border-bottom:3px solid #cc0000;padding:1rem 2rem;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.logo{font-size:1.4rem;font-weight:900;color:#cc0000;letter-spacing:-1px}
.logo span{color:#1a1a1a}
.nav-links{display:flex;gap:1.5rem;align-items:center}
.nav-links a{color:#555;font-size:.88rem;font-weight:500}
.nav-links a:hover{color:#cc0000}
.nav-btn{background:#cc0000;color:#fff!important;padding:.4rem 1.2rem;border-radius:4px;font-weight:700}
.nav-btn:hover{background:#aa0000!important}

.alert-bar{background:#cc0000;color:#fff;text-align:center;padding:.6rem 1rem;font-size:.82rem;font-weight:600;letter-spacing:.5px}

.hero{max-width:1000px;margin:0 auto;padding:5rem 2rem 4rem;text-align:center}
.hero-badge{display:inline-block;background:#fff0f0;color:#cc0000;border:1px solid #ffcccc;padding:.3rem 1rem;border-radius:20px;font-size:.78rem;font-weight:700;letter-spacing:1px;margin-bottom:1.5rem}
h1{font-size:clamp(2rem,5vw,3.8rem);line-height:1.1;margin-bottom:1.2rem;font-weight:900;letter-spacing:-2px;color:#1a1a1a}
h1 span{color:#cc0000}
.hero-sub{font-size:1.1rem;color:#555;max-width:620px;margin:0 auto 1rem}
.hero-sub2{font-size:.9rem;color:#888;max-width:540px;margin:0 auto 2.5rem}
.hero-btns{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin-bottom:.8rem}
.btn-red{background:#cc0000;color:#fff;padding:.9rem 2.5rem;border-radius:6px;font-size:1rem;font-weight:700;border:none;cursor:pointer;display:inline-block;transition:background .2s}
.btn-red:hover{background:#aa0000}
.btn-white{background:#fff;color:#cc0000;padding:.9rem 2.5rem;border-radius:6px;font-size:.95rem;font-weight:600;border:2px solid #cc0000;display:inline-block;transition:all .2s}
.btn-white:hover{background:#cc0000;color:#fff}
.free-note{color:#888;font-size:.8rem}

.stats{display:grid;grid-template-columns:repeat(4,1fr);background:#1a1a1a;margin:0 0 4rem}
.stat{padding:2rem 1rem;text-align:center;border-right:1px solid #333}
.stat:last-child{border-right:none}
.stat-n{font-size:2rem;color:#cc0000;font-weight:900;display:block}
.stat-l{font-size:.72rem;color:#888;letter-spacing:2px;margin-top:.2rem}

.sec{max-width:1000px;margin:0 auto;padding:4rem 2rem}
.sec-badge{display:inline-block;background:#fff0f0;color:#cc0000;border:1px solid #ffcccc;padding:.2rem .8rem;border-radius:20px;font-size:.72rem;font-weight:700;letter-spacing:1px;margin-bottom:1rem}
h2{font-size:2rem;font-weight:900;margin-bottom:.6rem;letter-spacing:-1px;color:#1a1a1a}
.sec-sub{color:#666;font-size:.95rem;max-width:580px;margin-bottom:2.5rem;line-height:1.7}

.decision-row{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem;margin:2rem 0}
.d-card{border-radius:8px;padding:1.8rem;text-align:center}
.d-allow{background:#f0fff4;border:2px solid #00cc66}
.d-challenge{background:#fffbf0;border:2px solid #ff9900}
.d-block{background:#fff0f0;border:2px solid #cc0000}
.d-score{font-size:1rem;font-weight:700;margin-bottom:.3rem}
.d-label{font-size:1.2rem;font-weight:900;margin-bottom:.4rem}
.d-desc{font-size:.83rem;color:#666;line-height:1.5}
.score-allow{color:#00aa44}
.score-challenge{color:#cc7700}
.score-block{color:#cc0000}

.code-box{background:#1a1a1a;border-radius:8px;overflow:hidden;margin:1.5rem 0}
.code-top{background:#111;padding:.6rem 1.2rem;font-size:.75rem;color:#888;display:flex;justify-content:space-between}
.code-top span{color:#cc0000;font-weight:700}
pre{padding:1.4rem;overflow-x:auto;font-size:.85rem;line-height:1.9;color:#e0e0e0;font-family:'Courier New',monospace}
.c-red{color:#ff6666}
.c-green{color:#66ff99}
.c-grey{color:#666}

.terminal{background:#1a1a1a;border-radius:8px;padding:1.5rem;margin:1.5rem 0;font-family:'Courier New',monospace;font-size:.82rem;line-height:2.1}
.t-ok{color:#00ff66}
.t-warn{color:#ffaa00}
.t-block{color:#ff4444}
.t-dim{color:#444}
.cursor{display:inline-block;width:8px;height:14px;background:#cc0000;animation:blink 1s infinite;vertical-align:middle}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}

.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1.2rem}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.2rem}

.card{background:#fff;border:1px solid #e8e8e8;border-radius:8px;padding:1.6rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.card:hover{border-color:#cc0000;box-shadow:0 4px 16px rgba(204,0,0,.08)}
.card-tag{font-size:.7rem;font-weight:700;letter-spacing:2px;margin-bottom:.6rem;color:#cc0000}
.card h3{font-size:1rem;font-weight:700;margin-bottom:.4rem;color:#1a1a1a}
.card p{font-size:.85rem;color:#666;line-height:1.7}

.fine-box{background:#fff0f0;border:2px solid #cc0000;border-radius:8px;padding:2rem;margin:2rem 0}
.fine-box h3{color:#cc0000;font-size:.82rem;font-weight:700;letter-spacing:2px;margin-bottom:1.2rem}
.fine-row{display:flex;justify-content:space-between;align-items:center;padding:.7rem 0;border-bottom:1px solid #ffcccc;flex-wrap:wrap;gap:.5rem}
.fine-row:last-child{border-bottom:none}
.fine-l{color:#555;font-size:.88rem}
.fine-v{color:#cc0000;font-weight:700;font-size:.95rem;white-space:nowrap}

.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1.2rem;margin:2rem 0}
.step{background:#fff;border:1px solid #e8e8e8;border-radius:8px;padding:1.5rem;position:relative;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.step-n{font-size:2.5rem;font-weight:900;color:#ffcccc;position:absolute;top:.5rem;right:1rem}
.step h3{color:#cc0000;font-size:.85rem;font-weight:700;letter-spacing:1px;margin-bottom:.4rem;position:relative}
.step p{font-size:.83rem;color:#666;line-height:1.7;position:relative}

.comp-card{background:#fff;border:1px solid #e8e8e8;border-top:3px solid #cc0000;border-radius:8px;padding:1.6rem;margin-bottom:1rem;box-shadow:0 2px 8px rgba(0,0,0,.04)}
.comp-card h3{color:#cc0000;font-size:.78rem;font-weight:700;letter-spacing:2px;margin-bottom:.8rem}
.comp-card ul{list-style:none}
.comp-card ul li{font-size:.83rem;color:#555;padding:.3rem 0;border-bottom:1px solid #f0f0f0}
.comp-card ul li:before{content:"✓ ";color:#00aa44;font-weight:700}
.comp-card ul li:last-child{border-bottom:none}

.pricing-wrap{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;max-width:800px;margin:2rem auto}
.price-card{background:#fff;border:2px solid #e8e8e8;border-radius:12px;padding:2rem;box-shadow:0 4px 16px rgba(0,0,0,.06)}
.price-card.featured{border-color:#cc0000;box-shadow:0 8px 32px rgba(204,0,0,.12)}
.price-label{font-size:.72rem;font-weight:700;letter-spacing:2px;color:#cc0000;margin-bottom:.8rem}
.price-n{font-size:3rem;font-weight:900;color:#1a1a1a;line-height:1}
.price-per{color:#888;font-size:.85rem;margin:.2rem 0 1.2rem}
.feat-list{list-style:none;margin:1rem 0 1.5rem}
.feat-list li{padding:.45rem 0;border-bottom:1px solid #f0f0f0;font-size:.85rem;color:#555}
.feat-list li:before{content:"✓ ";color:#00aa44;font-weight:700}
.feat-list li:last-child{border-bottom:none}

.form-section{background:#f8f8f8;border-radius:12px;padding:2rem;max-width:480px;margin:0 auto}
.field{margin:.7rem 0}
.field label{display:block;font-size:.75rem;font-weight:700;color:#444;letter-spacing:1px;margin-bottom:.3rem;text-transform:uppercase}
.field input,.field textarea{width:100%;background:#fff;border:1px solid #ddd;border-radius:6px;color:#1a1a1a;padding:.7rem 1rem;font-family:inherit;font-size:.9rem;outline:none;transition:border .2s}
.field input:focus,.field textarea:focus{border-color:#cc0000;box-shadow:0 0 0 3px rgba(204,0,0,.08)}
.field textarea{resize:vertical}
.submit-btn{display:block;width:100%;background:#cc0000;color:#fff;padding:1rem;border-radius:6px;font-family:inherit;font-size:1rem;font-weight:700;border:none;cursor:pointer;margin-top:1rem;transition:background .2s}
.submit-btn:hover{background:#aa0000}
.submit-btn:disabled{background:#ccc;cursor:not-allowed}
.msg{padding:.8rem 1rem;margin-top:.8rem;border-radius:6px;font-size:.85rem;display:none}
.msg-ok{background:#f0fff4;color:#00aa44;border:1px solid #ccffdd}
.msg-err{background:#fff0f0;color:#cc0000;border:1px solid #ffcccc}
.key-box{background:#1a1a1a;border-radius:8px;padding:1.2rem;margin-top:1rem;display:none}
.key-box h4{color:#cc0000;font-size:.72rem;font-weight:700;letter-spacing:2px;margin-bottom:.5rem}
.key-box code{color:#00ff88;font-family:'Courier New',monospace;font-size:.85rem;word-break:break-all;display:block}
.key-box p{color:#888;font-size:.78rem;margin-top:.6rem}
.key-box a{color:#cc0000}

.faq-item{border-bottom:1px solid #f0f0f0;padding:1.3rem 0}
.faq-item h3{font-size:.95rem;font-weight:700;color:#1a1a1a;margin-bottom:.4rem}
.faq-item p{font-size:.88rem;color:#666;line-height:1.75}

.cta-section{background:#cc0000;color:#fff;text-align:center;padding:5rem 2rem}
.cta-section h2{color:#fff;font-size:2.2rem;margin-bottom:.8rem}
.cta-section p{color:rgba(255,255,255,.8);margin-bottom:2rem;font-size:1rem}
.btn-white-cta{background:#fff;color:#cc0000;padding:1rem 2.5rem;border-radius:6px;font-size:1rem;font-weight:700;display:inline-block;transition:all .2s}
.btn-white-cta:hover{background:#f0f0f0}

footer{background:#1a1a1a;color:#888;padding:2.5rem 2rem;text-align:center;font-size:.82rem}
footer a{color:#aaa;text-decoration:none}
footer a:hover{color:#cc0000}
.footer-links{display:flex;gap:2rem;justify-content:center;margin-bottom:.8rem;flex-wrap:wrap}

@media(max-width:700px){
.stats{grid-template-columns:1fr 1fr}
.stat:nth-child(2){border-right:none}
.stat:nth-child(3){border-top:1px solid #333}
.grid2,.grid3,.pricing-wrap,.decision-row{grid-template-columns:1fr}
.nav-links a:not(.nav-btn){display:none}
h1{letter-spacing:-.5px}
h2{font-size:1.6rem}
}
</style>
</head>
<body>

<nav>
  <div class="logo">AI<span>Leash</span></div>
  <div class="nav-links">
    <a href="#what">How it works</a>
    <a href="#why">Why now</a>
    <a href="#pricing">Pricing</a>
    <a href="#contact">Contact</a>
    <a href="#free" class="nav-btn">Start free</a>
  </div>
</nav>

<div class="alert-bar">
  EU AI ACT FULL ENFORCEMENT: 2 AUGUST 2026 &nbsp;&mdash;&nbsp; FINES UP TO 35 MILLION EUROS OR 7% GLOBAL TURNOVER
</div>

<div class="hero">
  <div class="hero-badge">AI COMPLIANCE INFRASTRUCTURE</div>
  <h1>Your AI is making decisions.<br><span>Is it compliant?</span></h1>
  <p class="hero-sub">AILeash governs every decision your AI system makes in real time. Risk scored. Dangerous actions blocked. Every outcome audited automatically.</p>
  <p class="hero-sub2">EU AI Act compliant. Deploys in 2 minutes. Free tier included. No infrastructure changes required.</p>
  <div class="hero-btns">
    <a href="#free" class="btn-red">Start free &mdash; 1,000 requests</a>
    <a href="#what" class="btn-white">See how it works</a>
  </div>
  <p class="free-note">Free tier included. No card required. Pro from &pound;49/month.</p>
</div>

<div class="stats">
  <div class="stat"><span class="stat-n">0</span><span class="stat-l">DEPENDENCIES</span></div>
  <div class="stat"><span class="stat-n">2 min</span><span class="stat-l">TO DEPLOY</span></div>
  <div class="stat"><span class="stat-n">1,000</span><span class="stat-l">FREE REQUESTS</span></div>
  <div class="stat"><span class="stat-n">35M</span><span class="stat-l">MAX EU FINE &euro;</span></div>
</div>

<section class="sec" id="what">
  <div class="sec-badge">HOW IT WORKS</div>
  <h2>A firewall for your AI system.</h2>
  <p class="sec-sub">Every AI action passes through AILeash before execution. The engine evaluates the risk and returns one of three decisions in milliseconds. High-risk actions are blocked before they happen.</p>

  <div class="decision-row">
    <div class="d-card d-allow">
      <div class="d-score score-allow">0.00 &mdash; 0.29</div>
      <div class="d-label score-allow">ALLOW</div>
      <div class="d-desc">Risk is low. Action passes through instantly. Logged in tamper-evident audit chain.</div>
    </div>
    <div class="d-card d-challenge">
      <div class="d-score score-challenge">0.30 &mdash; 0.69</div>
      <div class="d-label score-challenge">CHALLENGE</div>
      <div class="d-desc">Risk is elevated. Action flagged for human review. Full explanation included.</div>
    </div>
    <div class="d-card d-block">
      <div class="d-score score-block">0.70 &mdash; 1.00</div>
      <div class="d-label score-block">BLOCK</div>
      <div class="d-desc">Risk is too high. Action stopped before execution. Incident logged automatically.</div>
    </div>
  </div>

  <div class="code-box">
    <div class="code-top"><span>API Request</span><span>responds in milliseconds</span></div>
    <pre>POST https://sebbi.pro/govern
x-api-key: your_key

{
  <span class="c-red">"action"</span>: <span class="c-red">"transfer"</span>,
  <span class="c-red">"amount"</span>: 5000,
  <span class="c-red">"device_risk"</span>: 0.2,
  <span class="c-red">"anomaly"</span>: 0.1,
  <span class="c-red">"country"</span>: <span class="c-red">"US"</span>
}

<span class="c-grey">Response:</span>
{
  <span class="c-red">"decision"</span>: <span class="c-green">"ALLOW"</span>,
  <span class="c-red">"score"</span>: 0.23,
  <span class="c-red">"usage"</span>: 1,
  <span class="c-red">"plan"</span>: <span class="c-green">"free"</span>
}</pre>
  </div>

  <div class="terminal">
    <div style="color:#cc0000;font-weight:bold;margin-bottom:.5rem">&gt; AILeash Live</div>
    <div><span class="t-ok">&gt;</span> transfer | &pound;450 | UK | anomaly=0.05</div>
    <div><span class="t-ok">[ALLOW]</span> score=0.18 &mdash; logged in audit chain</div>
    <div>&nbsp;</div>
    <div><span class="t-ok">&gt;</span> wire_transfer | &pound;18,500 | Russia | anomaly=0.72</div>
    <div><span class="t-block">[BLOCK]</span> score=0.84 &mdash; stopped before execution</div>
    <div>&nbsp;</div>
    <div><span class="t-ok">&gt;</span> payment | &pound;2,000 | Germany | anomaly=0.31</div>
    <div><span class="t-warn">[CHALLENGE]</span> score=0.51 &mdash; flagged for review</div>
    <div>&nbsp;</div>
    <div class="t-dim">Audit chain: 3 entries. SHA-256. Tamper-evident. 0 errors.</div>
    <div><span style="color:#cc0000">&gt;</span> <span class="cursor"></span></div>
  </div>

  <div class="grid4" style="margin-top:2.5rem">
    <div class="card"><div class="card-tag">RISK SCORING</div><h3>Every action evaluated</h3><p>Trust score, velocity, transaction size, device risk, geographic signals, and anomaly combined into a single deterministic score.</p></div>
    <div class="card"><div class="card-tag">AUDIT CHAIN</div><h3>SHA-256 chained log</h3><p>Every decision mathematically linked from your first request. Any tampering is immediately detectable by anyone independently verifying the chain.</p></div>
    <div class="card"><div class="card-tag">TRUST ENGINE</div><h3>Learns over time</h3><p>Per-agent trust scores that evolve with every decision. Good actors earn trust. Bad actors lose it permanently. Your system gets smarter every day.</p></div>
    <div class="card"><div class="card-tag">VELOCITY DETECTION</div><h3>Three time windows</h3><p>60 seconds, 5 minutes, 1 hour running simultaneously. Burst attacks and unusual patterns caught before they cause damage.</p></div>
  </div>
</section>

<section class="sec" id="why" style="background:#fafafa;max-width:100%;padding:4rem 2rem">
  <div style="max-width:1000px;margin:0 auto">
  <div class="sec-badge">WHY YOU NEED THIS NOW</div>
  <h2>The deadline is real. The fines are real.</h2>
  <p class="sec-sub">The EU AI Act came into force in 2024. Full enforcement of high-risk AI system requirements begins 2 August 2026. Companies deploying AI without proper governance infrastructure face fines that will end businesses.</p>

  <div class="fine-box">
    <h3>WHAT NON-COMPLIANCE COSTS</h3>
    <div class="fine-row"><span class="fine-l">Prohibited AI practices (Article 5)</span><span class="fine-v">35M EUR or 7% global turnover</span></div>
    <div class="fine-row"><span class="fine-l">High-risk system violations (Articles 9&ndash;15)</span><span class="fine-v">15M EUR or 3% global turnover</span></div>
    <div class="fine-row"><span class="fine-l">Incorrect information to authorities</span><span class="fine-v">7.5M EUR or 1.5% global turnover</span></div>
    <div class="fine-row"><span class="fine-l">GDPR + AI Act dual exposure (healthtech, fintech)</span><span class="fine-v">Combined penalties apply</span></div>
  </div>

  <div class="grid2" style="margin-top:1.5rem">
    <div class="card"><div class="card-tag" style="color:#cc0000">THE AUDIT PROBLEM</div><h3>You cannot prove what your AI decided.</h3><p>Without a tamper-evident audit log, you have no record that regulators will accept. Standard application logs are not enough and are easily altered.</p></div>
    <div class="card"><div class="card-tag" style="color:#cc
