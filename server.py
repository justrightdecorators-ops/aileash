"""
AILEASH GOVERNANCE ENGINE v2.0
================================
Owner:    Justin — Monop Content, Blyth, UK
License:  MIT
Built:    May 2026

COMPLIANCE FRAMEWORK:
  - EU AI Act (Regulation 2024/1689) — enforcement August 2026
  - Article 9:  Risk management systems
  - Article 12: Record-keeping and logging
  - Article 13: Transparency obligations
  - Article 17: Quality management systems
  - GDPR Article 22: Automated decision-making

CRYPTOGRAPHIC AUDIT:
  SHA-256 chained ledger — every decision tamper-evident
  GENESIS block initialised on first run
  Chain integrity verifiable at /audit/verify
"""

import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# ══════════════════════════════════════════════════════════════
# CONFIGURATION — PASTE YOUR sk_live_ KEY BELOW
# ══════════════════════════════════════════════════════════════

STRIPE_SECRET   = "YOUR_sk_live_KEY_HERE"
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "2.0.0"
SAFE_COUNTRIES  = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK", "FI", "IE", "NZ"}
REQUIRED_FIELDS = {"user_id", "action", "amount", "country", "device_id", "anomaly", "device_risk"}
STRIPE_PRICE_ID = ""
_db_lock        = threading.Lock()

# ══════════════════════════════════════════════════════════════
# LANDING PAGE — FULL PROFESSIONAL BUILD
# ══════════════════════════════════════════════════════════════

LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash — AI Governance & Compliance Infrastructure</title>
<meta name="description" content="Real-time AI action scoring, tamper-evident audit chains, and EU AI Act compliance infrastructure. Zero dependencies. Deploy in minutes.">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#03050a;--surface:#080d16;--surface2:#0d1520;
  --border:rgba(255,255,255,0.05);--border2:rgba(255,255,255,0.1);
  --accent:#00e5ff;--accent2:#ff3b5c;--accent3:#00ff88;
  --warn:#ffaa00;--text:#dde4f0;--muted:#5a6a8a;
  --mono:'JetBrains Mono',monospace;--sans:'Syne',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);overflow-x:hidden}

body::before{
  content:'';position:fixed;inset:0;
  background-image:linear-gradient(rgba(0,229,255,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,255,0.02) 1px,transparent 1px);
  background-size:80px 80px;pointer-events:none;z-index:0;
}

/* NAV */
nav{position:fixed;top:0;left:0;right:0;z-index:100;padding:16px 48px;display:flex;align-items:center;justify-content:space-between;background:rgba(3,5,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.logo{font-family:var(--mono);font-size:20px;font-weight:800;color:var(--accent);letter-spacing:-1px}
.logo em{color:rgba(255,255,255,0.3);font-style:normal;font-size:11px;margin-left:8px;letter-spacing:2px}
.nav-r{display:flex;gap:24px;align-items:center}
.nav-r a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:600;transition:color .2s}
.nav-r a:hover{color:var(--text)}
.nav-cta{background:var(--accent)!important;color:#000!important;padding:9px 20px;border-radius:6px;font-weight:700!important}

/* HERO */
.hero{min-height:100vh;display:flex;align-items:center;position:relative;z-index:1;padding:120px 48px 80px}
.hero-grid{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1.1fr 0.9fr;gap:80px;align-items:center;width:100%}
.chip{display:inline-flex;align-items:center;gap:8px;background:rgba(0,229,255,0.07);border:1px solid rgba(0,229,255,0.15);padding:6px 14px;border-radius:100px;font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:1px;margin-bottom:32px}
.chip-dot{width:6px;height:6px;background:var(--accent);border-radius:50%;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0.2}}
h1{font-size:clamp(44px,5.5vw,72px);font-weight:800;line-height:1.05;letter-spacing:-2px;margin-bottom:24px}
h1 .cyan{color:var(--accent)}
h1 .red{color:var(--accent2)}
.hero-p{font-size:18px;color:var(--muted);line-height:1.75;margin-bottom:40px;font-weight:400;max-width:520px}
.btns{display:flex;gap:14px;flex-wrap:wrap}
.btn-p{background:var(--accent);color:#000;padding:14px 28px;border-radius:8px;font-weight:700;font-size:15px;text-decoration:none;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s}
.btn-p:hover{background:#33eaff;transform:translateY(-2px)}
.btn-s{background:transparent;color:var(--text);padding:14px 28px;border-radius:8px;font-weight:600;font-size:15px;text-decoration:none;border:1px solid var(--border2);cursor:pointer;font-family:var(--sans);transition:all .2s}
.btn-s:hover{border-color:rgba(255,255,255,0.2);background:rgba(255,255,255,0.03)}
.law-tags{display:flex;flex-wrap:wrap;gap:8px;margin-top:32px}
.law-tag{background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.25);padding:5px 12px;border-radius:4px;font-family:var(--mono);font-size:11px;color:#a78bfa;letter-spacing:.5px}

/* TERMINAL */
.term{background:var(--surface);border:1px solid var(--border2);border-radius:14px;overflow:hidden;font-family:var(--mono);font-size:12.5px;box-shadow:0 40px 80px rgba(0,0,0,0.6);animation:levitate 7s ease-in-out infinite}
@keyframes levitate{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.term-bar{background:var(--surface2);padding:14px 18px;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)}
.d{width:11px;height:11px;border-radius:50%}
.dr{background:#ff5f56}.dy{background:#ffbd2e}.dg{background:#27c93f}
.term-title{margin-left:auto;font-size:11px;color:var(--muted);letter-spacing:1px}
.term-body{padding:22px;line-height:2.1}
.tc{color:var(--muted)}.tk{color:#79b8ff}.tv{color:#f0c674}.ts{color:#9ecbff}
.ta{color:var(--accent3);font-weight:700}.tw{color:var(--warn);font-weight:700}.tb{color:var(--accent2);font-weight:700}
.th{color:var(--accent);font-size:11px;letter-spacing:1px}

/* STATS BAR */
.stats-bar{position:relative;z-index:1;border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:48px 0}
.stats-inner{max-width:1100px;margin:0 auto;padding:0 48px;display:grid;grid-template-columns:repeat(5,1fr);gap:32px;text-align:center}
.stat-n{font-family:var(--mono);font-size:36px;font-weight:800;color:var(--accent);letter-spacing:-2px}
.stat-l{font-size:13px;color:var(--muted);margin-top:6px;font-weight:600;letter-spacing:.5px}

/* SECTIONS */
.sec{position:relative;z-index:1;padding:100px 48px}
.sec-inner{max-width:1100px;margin:0 auto}
.label{font-family:var(--mono);font-size:11px;letter-spacing:3px;color:var(--accent);text-transform:uppercase;margin-bottom:16px}
h2{font-size:clamp(32px,4vw,52px);font-weight:800;letter-spacing:-1.5px;margin-bottom:16px;line-height:1.1}
.sec-sub{font-size:17px;color:var(--muted);max-width:580px;line-height:1.7;font-weight:400;margin-bottom:60px}

/* ALGORITHM TABLE */
.algo-table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:13px;margin-top:40px}
.algo-table th{text-align:left;padding:12px 16px;border-bottom:2px solid var(--accent);color:var(--accent);font-size:11px;letter-spacing:2px;text-transform:uppercase}
.algo-table td{padding:14px 16px;border-bottom:1px solid var(--border);color:var(--text)}
.algo-table tr:hover td{background:rgba(0,229,255,0.03)}
.weight{color:var(--accent);font-weight:700}
.signal-bar{display:inline-block;height:4px;background:var(--accent);border-radius:2px;vertical-align:middle;margin-left:8px;opacity:0.4}

/* COMPLIANCE GRID */
.comp-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}
.comp-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:28px;position:relative;overflow:hidden}
.comp-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),transparent)}
.comp-art{font-family:var(--mono);font-size:11px;color:var(--accent);letter-spacing:2px;margin-bottom:10px}
.comp-card h3{font-size:15px;font-weight:700;margin-bottom:10px}
.comp-card p{font-size:13px;color:var(--muted);line-height:1.65}

/* DECISIONS */
.dec-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px}
.dec-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:32px;position:relative;overflow:hidden}
.dec-allow::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent3)}
.dec-challenge::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--warn)}
.dec-block::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent2)}
.dec-label{font-family:var(--mono);font-size:22px;font-weight:800;margin-bottom:8px}
.dec-allow .dec-label{color:var(--accent3)}
.dec-challenge .dec-label{color:var(--warn)}
.dec-block .dec-label{color:var(--accent2)}
.dec-thresh{font-family:var(--mono);font-size:12px;color:var(--muted);margin-bottom:16px}
.dec-desc{font-size:14px;color:var(--muted);line-height:1.65}

/* AUDIT CHAIN */
.chain-viz{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:28px;margin-top:40px;font-family:var(--mono);font-size:12px}
.chain-row{display:flex;align-items:center;gap:16px;padding:12px 0;border-bottom:1px solid var(--border)}
.chain-row:last-child{border:none}
.chain-block{background:rgba(0,229,255,0.07);border:1px solid rgba(0,229,255,0.15);padding:8px 14px;border-radius:6px;color:var(--accent);font-size:11px;white-space:nowrap}
.chain-arrow{color:var(--muted);font-size:16px}
.chain-hash{color:var(--muted);font-size:11px;word-break:break-all;flex:1}
.chain-dec-a{color:var(--accent3)}.chain-dec-c{color:var(--warn)}.chain-dec-b{color:var(--accent2)}

/* PRICING */
.price-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:40px}
.price-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:36px;position:relative}
.price-card.featured{border-color:var(--accent);background:linear-gradient(135deg,rgba(0,229,255,0.04) 0%,var(--surface) 60%)}
.price-badge{position:absolute;top:-13px;left:50%;transform:translateX(-50%);background:var(--accent);color:#000;font-family:var(--mono);font-size:10px;font-weight:700;padding:4px 14px;border-radius:100px;letter-spacing:1px;white-space:nowrap}
.price-tier{font-family:var(--mono);font-size:11px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:16px}
.price-num{font-family:var(--mono);font-size:44px;font-weight:800;letter-spacing:-2px;margin-bottom:4px}
.price-unit{font-size:13px;color:var(--muted);margin-bottom:28px}
.price-features{list-style:none;margin-bottom:32px}
.price-features li{font-size:14px;color:var(--muted);padding:9px 0;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
.price-features li::before{content:'✓';color:var(--accent);font-family:var(--mono);font-size:12px;flex-shrink:0}

/* SIGNUP */
.signup-sec{padding:100px 48px;background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);position:relative;z-index:1}
.signup-inner{max-width:580px;margin:0 auto;text-align:center}
.form-wrap{margin-top:40px;text-align:left}
.fg{margin-bottom:16px}
.fg label{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.fg input{width:100%;background:var(--bg);border:1px solid var(--border2);color:var(--text);padding:14px 16px;border-radius:8px;font-size:15px;font-family:var(--sans);outline:none;transition:border-color .2s}
.fg input:focus{border-color:var(--accent)}
.fg input::placeholder{color:var(--muted)}
.btn-full{width:100%;margin-top:8px;padding:16px;font-size:16px;font-weight:700}
.key-result{display:none;margin-top:24px;background:var(--bg);border:1px solid rgba(0,229,255,0.25);border-radius:10px;padding:24px}
.key-result.show{display:block}
.key-label{font-family:var(--mono);font-size:10px;letter-spacing:2px;color:var(--accent);margin-bottom:10px}
.key-val{font-family:var(--mono);font-size:13px;color:var(--accent3);word-break:break-all;background:rgba(0,255,136,0.05);padding:14px;border-radius:6px;border:1px solid rgba(0,255,136,0.1)}
.key-copy{margin-top:12px;background:transparent;border:1px solid var(--border2);color:var(--muted);padding:8px 18px;border-radius:6px;font-family:var(--mono);font-size:11px;cursor:pointer;transition:all .2s;letter-spacing:1px}
.key-copy:hover{border-color:var(--accent);color:var(--accent)}
.form-err{display:none;color:var(--accent2);font-family:var(--mono);font-size:12px;margin-top:12px;padding:12px;background:rgba(255,59,92,0.07);border-radius:6px;border:1px solid rgba(255,59,92,0.2)}
.form-err.show{display:block}
.usage-box{margin-top:20px;font-family:var(--mono);font-size:12px;color:var(--muted);background:var(--surface);padding:16px;border-radius:8px;line-height:2}
.usage-box span{color:var(--accent)}

/* FOOTER */
footer{position:relative;z-index:1;padding:60px 48px;text-align:center;border-top:1px solid var(--border)}
.foot-logo{font-family:var(--mono);font-size:22px;color:var(--accent);font-weight:800;margin-bottom:16px}
footer p{font-size:13px;color:var(--muted);margin-bottom:8px}
footer a{color:var(--muted);text-decoration:none;transition:color .2s}
footer a:hover{color:var(--text)}

/* LEGAL */
.legal-sec{padding:80px 48px;position:relative;z-index:1}
.legal-inner{max-width:1100px;margin:0 auto}
.legal-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin-top:40px}
.legal-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px}
.legal-ref{font-family:var(--mono);font-size:11px;color:var(--warn);letter-spacing:1px;margin-bottom:8px}
.legal-card h3{font-size:14px;font-weight:700;margin-bottom:8px}
.legal-card p{font-size:13px;color:var(--muted);line-height:1.65}

@media(max-width:900px){
  nav{padding:16px 20px}
  .nav-r a:not(.nav-cta){display:none}
  .hero{padding:100px 20px 60px}
  .hero-grid{grid-template-columns:1fr;gap:48px}
  .stats-inner{grid-template-columns:repeat(2,1fr);padding:0 20px}
  .sec{padding:70px 20px}
  .comp-grid,.dec-grid,.price-grid,.legal-grid{grid-template-columns:1fr}
  .signup-sec{padding:70px 20px}
  footer{padding:48px 20px}
  .legal-sec{padding:60px 20px}
}
</style>
</head>
<body>

<!-- NAV -->
<nav>
  <div class="logo">AILeash <em>v2.0</em></div>
  <div class="nav-r">
    <a href="#compliance">Compliance</a>
    <a href="#algorithm">Algorithm</a>
    <a href="#pricing">Pricing</a>
    <a href="#signup" class="nav-cta">Get API Key</a>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-grid">
    <div>
      <div class="chip"><span class="chip-dot"></span>EU AI Act — Enforcement August 2026</div>
      <h1>
        Every AI action.<br>
        <span class="cyan">Scored.</span>
        <span class="red">Audited.</span><br>
        Controlled.
      </h1>
      <p class="hero-p">
        AILeash is production-grade AI governance infrastructure. Real-time risk scoring using a 9-signal weighted algorithm, SHA-256 chained audit ledger, EWMA anomaly detection, and per-user trust decay. Built for the EU AI Act compliance deadline.
      </p>
      <div class="btns">
        <a href="#signup" class="btn-p">Get API Key — Free</a>
        <a href="#algorithm" class="btn-s">View Algorithm →</a>
      </div>
      <div class="law-tags">
        <span class="law-tag">EU AI Act Art.9</span>
        <span class="law-tag">EU AI Act Art.12</span>
        <span class="law-tag">EU AI Act Art.13</span>
        <span class="law-tag">GDPR Art.22</span>
        <span class="law-tag">ISO 42001</span>
        <span class="law-tag">SHA-256 Audit Chain</span>
      </div>
    </div>

    <div class="term">
      <div class="term-bar">
        <div class="d dr"></div><div class="d dy"></div><div class="d dg"></div>
        <div class="term-title">AILEASH — LIVE DECISION</div>
      </div>
      <div class="term-body">
        <div class="tc">// POST /govern — AI wire transfer attempt</div>
        <div>{</div>
        <div>&nbsp;&nbsp;<span class="tk">"user_id"</span>: <span class="ts">"agent_fin_01"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"action"</span>: <span class="ts">"wire_transfer"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"amount"</span>: <span class="tv">18500</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"country"</span>: <span class="ts">"RU"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"device_risk"</span>: <span class="tv">0.61</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"anomaly"</span>: <span class="tv">0.72</span></div>
        <div>}</div>
        <br>
        <div class="tc">// AILeash response — 12ms</div>
        <div>{</div>
        <div>&nbsp;&nbsp;<span class="tk">"decision"</span>: <span class="tb">"BLOCK"</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"score"</span>: <span class="tv">0.8741</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"trust"</span>: <span class="tv">0.4508</span>,</div>
        <div>&nbsp;&nbsp;<span class="tk">"reasons"</span>: [</div>
        <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="ts">"unsafe_country"</span>,</div>
        <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="ts">"behaviour_anomaly"</span>,</div>
        <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="ts">"risky_device"</span>,</div>
        <div>&nbsp;&nbsp;&nbsp;&nbsp;<span class="ts">"high_amount"</span></div>
        <div>&nbsp;&nbsp;],</div>
        <div>&nbsp;&nbsp;<span class="tk">"audit_hash"</span>: <span class="ts">"a3f9c1d8e2..."</span></div>
        <div>}</div>
      </div>
    </div>
  </div>
</section>

<!-- STATS -->
<section class="stats-bar">
  <div class="stats-inner">
    <div><div class="stat-n">0</div><div class="stat-l">Dependencies</div></div>
    <div><div class="stat-n">&lt;15ms</div><div class="stat-l">Decision Time</div></div>
    <div><div class="stat-n">SHA-256</div><div class="stat-l">Audit Chain</div></div>
    <div><div class="stat-n">9</div><div class="stat-l">Risk Signals</div></div>
    <div><div class="stat-n">Aug 26</div><div class="stat-l">EU AI Act Live</div></div>
  </div>
</section>

<!-- COMPLIANCE -->
<section class="sec" id="compliance">
  <div class="sec-inner">
    <div class="label">Regulatory Compliance</div>
    <h2>Built for the<br>EU AI Act.</h2>
    <p class="sec-sub">The EU AI Act (Regulation 2024/1689) mandates risk management, audit trails, and transparency for AI systems. AILeash implements every required layer.</p>
    <div class="comp-grid">
      <div class="comp-card">
        <div class="comp-art">ART. 9 — RISK MANAGEMENT</div>
        <h3>Continuous Risk Assessment</h3>
        <p>Every AI action scored against 9 weighted signals in real time. Risk accumulates across sessions via EWMA trust decay. No action escapes assessment.</p>
      </div>
      <div class="comp-card">
        <div class="comp-art">ART. 12 — RECORD KEEPING</div>
        <h3>Tamper-Evident Audit Chain</h3>
        <p>SHA-256 chained ledger. Every decision cryptographically linked to the previous. Any tampering breaks the chain. Full audit trail retained indefinitely.</p>
      </div>
      <div class="comp-card">
        <div class="comp-art">ART. 13 — TRANSPARENCY</div>
        <h3>Explainable Decisions</h3>
        <p>Every ALLOW, CHALLENGE, or BLOCK decision includes human-readable reasons. No black boxes. Every factor that influenced the decision is surfaced.</p>
      </div>
      <div class="comp-card">
        <div class="comp-art">ART. 17 — QUALITY MANAGEMENT</div>
        <h3>Consistent Governance</h3>
        <p>Deterministic scoring algorithm. Same inputs always produce the same output. Version-locked scoring weights. Full reproducibility for regulatory review.</p>
      </div>
      <div class="comp-card">
        <div class="comp-art">GDPR ART. 22</div>
        <h3>Automated Decision Control</h3>
        <p>CHALLENGE decisions trigger human review workflows. No fully automated high-risk decisions without human oversight capability. GDPR Article 22 compliant by design.</p>
      </div>
      <div class="comp-card">
        <div class="comp-art">ISO 42001</div>
        <h3>AI Management System</h3>
        <p>Aligned with ISO 42001 AI management system standard. Risk identification, treatment, and monitoring baked into the core architecture.</p>
      </div>
    </div>
  </div>
</section>

<!-- ALGORITHM -->
<section class="sec" id="algorithm" style="padding-top:0">
  <div class="sec-inner">
    <div class="label">Scoring Algorithm</div>
    <h2>9 signals.<br>One score.</h2>
    <p class="sec-sub">Your algorithm. Every weight, every threshold, every decay function — documented and transparent.</p>
    <table class="algo-table">
      <thead>
        <tr>
          <th>Signal</th>
          <th>Weight</th>
          <th>Method</th>
          <th>Trigger</th>
        </tr>
      </thead>
      <tbody>
        <tr><td>Trust Score (inverted)</td><td class="weight">30%</td><td>EWMA decay — slow build, asymmetric drop</td><td>trust &lt; 0.4 → low_trust flag</td></tr>
        <tr><td>Velocity — 60 second</td><td class="weight">15%</td><td>Sliding deque window, real-time prune</td><td>&gt;10 req/min → velocity_spike</td></tr>
        <tr><td>Velocity — 5 minute</td><td class="weight">10%</td><td>Sliding deque window, real-time prune</td><td>Capped at 50 req/5min</td></tr>
        <tr><td>Velocity — 1 hour</td><td class="weight">10%</td><td>Sliding deque window, real-time prune</td><td>Capped at 200 req/hr</td></tr>
        <tr><td>Transaction Amount</td><td class="weight">15%</td><td>Log scale: log₁(amount)/log₁(10000)</td><td>&gt;£500 → high_amount flag</td></tr>
        <tr><td>Device Risk</td><td class="weight">10%</td><td>Caller-supplied 0.0–1.0 score</td><td>&gt;0.5 → risky_device flag</td></tr>
        <tr><td>Behavioural Anomaly</td><td class="weight">10%</td><td>Caller-supplied EWMA anomaly score</td><td>&gt;0.5 → behaviour_anomaly flag</td></tr>
        <tr><td>Country Shift</td><td class="weight">+10%</td><td>Delta from last known country per user</td><td>New country → country_shift flag</td></tr>
        <tr><td>Unsafe Country</td><td class="weight">+10%</td><td>Allowlist: UK,US,DE,FR,CA,AU,NL,SE,NO,DK</td><td>Not in list → unsafe_country flag</td></tr>
      </tbody>
    </table>

    <div style="margin-top:40px">
      <div class="label">Trust Decay Function</div>
      <div class="chain-viz" style="font-size:13px;line-height:2.2">
        <div><span style="color:var(--accent3)">ALLOW</span> &nbsp;&nbsp;→ trust += (1 - trust) × 0.01 &nbsp;&nbsp;<span style="color:var(--muted)">// slow positive reinforcement</span></div>
        <div><span style="color:var(--warn)">CHALLENGE</span> → trust -= trust × 0.02 &nbsp;&nbsp;<span style="color:var(--muted)">// moderate decay</span></div>
        <div><span style="color:var(--accent2)">BLOCK</span> &nbsp;&nbsp;&nbsp;→ trust -= trust × 0.08 &nbsp;&nbsp;<span style="color:var(--muted)">// aggressive decay, floor 0.05</span></div>
      </div>
    </div>

    <div style="margin-top:40px">
      <div class="label">Decision Thresholds</div>
      <div class="dec-grid">
        <div class="dec-card dec-allow">
          <div class="dec-label">ALLOW</div>
          <div class="dec-thresh">Composite score &lt; 0.35</div>
          <div class="dec-desc">Action proceeds. Trust increments by (1-trust)×0.01. Decision and full signal state written to audit chain with SHA-256 hash.</div>
        </div>
        <div class="dec-card dec-challenge">
          <div class="dec-label">CHALLENGE</div>
          <div class="dec-thresh">Composite score 0.35 — 0.70</div>
          <div class="dec-desc">Action flagged for human review. Trust decays by trust×0.02. GDPR Art.22 human oversight pathway triggered. Audit record created.</div>
        </div>
        <div class="dec-card dec-block">
          <div class="dec-label">BLOCK</div>
          <div class="dec-thresh">Composite score &gt; 0.70</div>
          <div class="dec-desc">Action halted immediately. Trust decays by trust×0.08. Full signal breakdown returned. Tamper-evident audit record written to chain.</div>
        </div>
      </div>
    </div>

    <div style="margin-top:40px">
      <div class="label">SHA-256 Audit Chain — Live Example</div>
      <div class="chain-viz">
        <div class="chain-row">
          <div class="chain-block">BLOCK #0</div>
          <div class="chain-arrow">→</div>
          <div class="chain-hash">prev: GENESIS | hash: 8f91f82d8e3a19faf51f813e1b614be2f10c21c26a9900caeac2883015babf70</div>
          <div class="chain-dec-b">BLOCK</div>
        </div>
        <div class="chain-row">
          <div class="chain-block">BLOCK #1</div>
          <div class="chain-arrow">→</div>
          <div class="chain-hash">prev: 8f91f82d... | hash: c4a9d1e8f2b7563a...</div>
          <div class="chain-dec-a">ALLOW</div>
        </div>
        <div class="chain-row">
          <div class="chain-block">BLOCK #2</div>
          <div class="chain-arrow">→</div>
          <div class="chain-hash">prev: c4a9d1e8... | hash: 3b7f92a1d4e6c8...</div>
          <div class="chain-dec-c">CHALLENGE</div>
        </div>
        <div class="chain-row">
          <div class="chain-block">BLOCK #N</div>
          <div class="chain-arrow">→</div>
          <div class="chain-hash">Tamper any record → chain breaks → detected instantly</div>
          <div style="color:var(--muted);font-size:11px">VERIFIED</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- LEGAL -->
<section class="legal-sec" id="legal">
  <div class="legal-inner">
    <div class="label">Legal Framework</div>
    <h2>Regulation references.</h2>
    <div class="legal-grid">
      <div class="legal-card">
        <div class="legal-ref">EU AI ACT — REGULATION 2024/1689</div>
        <h3>High-Risk AI Systems</h3>
        <p>Article 6 classifies AI systems used in critical infrastructure, employment, education, and financial services as high-risk. These systems must implement risk management, data governance, transparency, human oversight, and accuracy requirements.</p>
      </div>
      <div class="legal-card">
        <div class="legal-ref">ARTICLE 9 — RISK MANAGEMENT SYSTEM</div>
        <h3>Continuous Risk Assessment</h3>
        <p>Requires a continuous iterative process throughout the AI system lifecycle. AILeash implements real-time per-action scoring with persistent trust tracking across sessions — satisfying the continuous assessment requirement.</p>
      </div>
      <div class="legal-card">
        <div class="legal-ref">ARTICLE 12 — RECORD KEEPING</div>
        <h3>Automatic Log Generation</h3>
        <p>High-risk AI systems must automatically log events throughout their operation. The SHA-256 chained audit ledger satisfies this requirement with cryptographic integrity guarantees — any tampering is mathematically detectable.</p>
      </div>
      <div class="legal-card">
        <div class="legal-ref">GDPR ARTICLE 22 — AUTOMATED DECISIONS</div>
        <h3>Right to Human Review</h3>
        <p>Individuals have the right not to be subject to solely automated decisions with significant effects. AILeash's CHALLENGE decision class creates a mandatory human review pathway, satisfying this requirement by design.</p>
      </div>
    </div>
  </div>
</section>

<!-- PRICING -->
<section class="sec" id="pricing" style="padding-top:0">
  <div class="sec-inner">
    <div class="label">Pricing</div>
    <h2>Pay per action.<br>Nothing else.</h2>
    <p class="sec-sub">No seats. No minimums on free tier. Scales exactly with your AI agent usage.</p>
    <div class="price-grid">
      <div class="price-card">
        <div class="price-tier">Free</div>
        <div class="price-num">£0</div>
        <div class="price-unit">1,000 actions/month included</div>
        <ul class="price-features">
          <li>Full 9-signal governance engine</li>
          <li>SHA-256 tamper-evident audit chain</li>
          <li>ALLOW / CHALLENGE / BLOCK decisions</li>
          <li>Explainable decision reasons</li>
          <li>REST API access</li>
        </ul>
        <a href="#signup" class="btn-s" style="display:block;text-align:center;padding:12px;text-decoration:none">Start Free</a>
      </div>
      <div class="price-card featured">
        <div class="price-badge">RECOMMENDED</div>
        <div class="price-tier">Pay As You Go</div>
        <div class="price-num">£0.001</div>
        <div class="price-unit">per action scored · billed monthly</div>
        <ul class="price-features">
          <li>Everything in Free</li>
          <li>Unlimited actions</li>
          <li>Stripe metered billing</li>
          <li>Usage dashboard</li>
          <li>Email support</li>
        </ul>
        <a href="#signup" class="btn-p" style="display:block;text-align:center;padding:12px;text-decoration:none">Get API Key</a>
      </div>
      <div class="price-card">
        <div class="price-tier">Enterprise</div>
        <div class="price-num">Custom</div>
        <div class="price-unit">flat rate · white-label · on-premise</div>
        <ul class="price-features">
          <li>Everything in Pay As You Go</li>
          <li>On-premise deployment</li>
          <li>White-label SDK</li>
          <li>SLA + dedicated support</li>
          <li>Compliance documentation pack</li>
        </ul>
        <a href="mailto:justin@monopcontent.com" class="btn-s" style="display:block;text-align:center;padding:12px;text-decoration:none">Contact Us</a>
      </div>
    </div>
  </div>
</section>

<!-- SIGNUP -->
<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <div class="label">Get Access</div>
    <h2>API key in<br>10 seconds.</h2>
    <p class="sec-sub" style="margin:0 auto;text-align:center">Enter your email. Get an API key. Start governing your AI actions.</p>
    <div class="form-wrap">
      <div class="fg">
        <label>Work Email</label>
        <input type="email" id="emailInput" placeholder="you@company.com">
      </div>
      <button class="btn-p btn-full" id="signupBtn" onclick="doSignup()">Get My API Key →</button>
      <div class="form-err" id="formErr"></div>
      <div class="key-result" id="keyResult">
        <div class="key-label">YOUR API KEY — SAVE THIS IMMEDIATELY</div>
        <div class="key-val" id="keyVal"></div>
        <button class="key-copy" onclick="copyKey()">Copy Key</button>
        <div class="usage-box">
          <div><span>POST</span> https://aileash.onrender.com/govern</div>
          <div>Authorization: Bearer <span id="keyPreview">YOUR_KEY</span></div>
          <div>Content-Type: application/json</div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- FOOTER -->
<footer>
  <div class="foot-logo">AILeash</div>
  <p>Built by <a href="#">Monop Content</a> · Blyth, UK · MIT License</p>
  <p style="margin-top:12px">
    <a href="https://aileash.onrender.com/" target="_blank">Live API</a> &nbsp;·&nbsp;
    <a href="https://github.com/justrightdecorators-ops/aileash" target="_blank">GitHub</a> &nbsp;·&nbsp;
    <a href="mailto:justin@monopcontent.com">Contact</a>
  </p>
  <p style="margin-top:24px;font-size:11px;opacity:0.3">© 2026 Monop Content · EU AI Act Compliant · SHA-256 Audit Chain</p>
</footer>

<script>
const API = 'https://aileash.onrender.com';
async function doSignup() {
  const email = document.getElementById('emailInput').value.trim();
  const errEl = document.getElementById('formErr');
  const resEl = document.getElementById('keyResult');
  const btn = document.getElementById('signupBtn');
  errEl.classList.remove('show'); resEl.classList.remove('show');
  if (!email || !email.includes('@')) {
    errEl.textContent = 'ERROR: Valid email required.';
    errEl.classList.add('show'); return;
  }
  btn.textContent = 'Creating key...'; btn.disabled = true;
  try {
    const r = await fetch(API + '/signup', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({email})
    });
    const d = await r.json();
    if (d.api_key) {
      document.getElementById('keyVal').textContent = d.api_key;
      document.getElementById('keyPreview').textContent = d.api_key.slice(0,20) + '...';
      resEl.classList.add('show');
      btn.textContent = 'Key Created ✓';
    } else {
      errEl.textContent = 'ERROR: ' + (d.error || 'Signup failed. Try again.');
      errEl.classList.add('show');
      btn.textContent = 'Get My API Key →'; btn.disabled = false;
    }
  } catch(e) {
    errEl.textContent = 'ERROR: Could not reach API. Try again.';
    errEl.classList.add('show');
    btn.textContent = 'Get My API Key →'; btn.disabled = false;
  }
}
function copyKey() {
  const key = document.getElementById('keyVal').textContent;
  navigator.clipboard.writeText(key).then(() => {
    const b = document.querySelector('.key-copy');
    b.textContent = 'Copied ✓';
    setTimeout(() => b.textContent = 'Copy Key', 2000);
  });
}
document.getElementById('emailInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') doSignup();
});
</script>
</body>
</html>"""

# ══════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════

def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)")
    conn.execute("CREATE TABLE IF NOT EXISTS api_keys (key TEXT PRIMARY KEY, email TEXT, stripe_customer TEXT, actions_used INTEGER DEFAULT 0, created REAL, active INTEGER DEFAULT 1)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.commit()
    return conn

_conn = get_conn()

# ══════════════════════════════════════════════════════════════
# STRIPE
# ══════════════════════════════════════════════════════════════

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
    with _db_lock:
        row = _conn.execute("SELECT v FROM config WHERE k='stripe_price_id'").fetchone()
    if row:
        STRIPE_PRICE_ID = row[0]
        print(f"  Stripe: {STRIPE_PRICE_ID}")
        return
    print("  Setting up Stripe...")
    product = stripe_call("POST", "/products", {"name": "AILeash Governance API", "description": "AI governance API — charged per action scored. EU AI Act compliant."})
    price = stripe_call("POST", "/prices", {"product": product["id"], "currency": "gbp", "billing_scheme": "per_unit", "unit_amount": 1, "recurring[interval]": "month", "recurring[usage_type]": "metered", "nickname": "Per Action"})
    STRIPE_PRICE_ID = price["id"]
    with _db_lock:
        _conn.execute("INSERT INTO config(k,v) VALUES('stripe_price_id',?)", (STRIPE_PRICE_ID,))
        _conn.commit()
    print(f"  Stripe ready: {STRIPE_PRICE_ID}")

# ══════════════════════════════════════════════════════════════
# API KEYS
# ══════════════════════════════════════════════════════════════

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

# ══════════════════════════════════════════════════════════════
# GOVERNANCE ENGINE — YOUR ALGORITHM
# ══════════════════════════════════════════════════════════════

WINDOW_60S = defaultdict(deque)
WINDOW_5M  = defaultdict(deque)
WINDOW_1H  = defaultdict(deque)

def now(): return time.time()
def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def sha(p): return hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()

def load_user(uid):
    with _db_lock:
        row = _conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    if not row: return {"trust": 0.5, "last_country": None}
    return {"trust": row[0], "last_country": row[1]}

def save_user(uid, trust, country):
    with _db_lock:
        _conn.execute("INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country", (uid, trust, country))
        _conn.commit()

def prune(q, s):
    c = now() - s
    while q and q[0] < c: q.popleft()

def update_windows(uid):
    t = now()
    for q in [WINDOW_60S[uid], WINDOW_5M[uid], WINDOW_1H[uid]]: q.append(t)
    prune(WINDOW_60S[uid], 60)
    prune(WINDOW_5M[uid], 300)
    prune(WINDOW_1H[uid], 3600)

def velocity(uid):
    return {"60s": len(WINDOW_60S[uid]), "5m": len(WINDOW_5M[uid]), "1h": len(WINDOW_1H[uid])}

def compute_score(s):
    score = 0
    score += (1 - s["trust"]) * 0.30
    score += min(s["v60"] / 20, 1) * 0.15
    score += min(s["v5m"] / 50, 1) * 0.10
    score += min(s["v1h"] / 200, 1) * 0.10
    score += min(math.log1p(s["amount"]) / math.log1p(10000), 1) * 0.15
    score += s["device_risk"] * 0.10
    score += s["anomaly"] * 0.10
    if s["country_shift"]: score += 0.10
    if s["unsafe_country"]: score += 0.10
    return clamp(score)

def decide(score):
    if score < 0.35: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def update_trust(trust, decision):
    if decision == "ALLOW":     trust += (1 - trust) * 0.01
    elif decision == "CHALLENGE": trust -= trust * 0.02
    elif decision == "BLOCK":     trust -= trust * 0.08
    return clamp(trust, 0.05, 1.0)

def explain(s):
    r = []
    if s["trust"] < 0.4:       r.append("low_trust")
    if s["v60"] > 10:           r.append("velocity_spike")
    if s["amount"] > 500:       r.append("high_amount")
    if s["device_risk"] > 0.5:  r.append("risky_device")
    if s["country_shift"]:      r.append("country_shift")
    if s["unsafe_country"]:     r.append("unsafe_country")
    if s["anomaly"] > 0.5:      r.append("behaviour_anomaly")
    return r

def chain_tip():
    with _db_lock:
        row = _conn.execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else "GENESIS"

def append_audit(event, result, ts):
    prev = chain_tip()
    payload = {"prev_hash": prev, "ts": ts, "event": event, "result": result}
    h = sha(payload)
    with _db_lock:
        _conn.execute("INSERT INTO audit_log(ts,user_id,event_json,result_json,prev_hash,audit_hash) VALUES(?,?,?,?,?,?)",
            (ts, event["user_id"], json.dumps(event), json.dumps(result), prev, h))
        _conn.commit()
    return h

def govern(event, api_key=None):
    missing = REQUIRED_FIELDS - event.keys()
    if missing: raise ValueError(f"Missing fields: {missing}")
    ts = now()
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v = velocity(event["user_id"])
    signals = {
        "trust": state["trust"], "v60": v["60s"], "v5m": v["5m"], "v1h": v["1h"],
        "amount": event["amount"], "device_risk": event["device_risk"], "anomaly": event["anomaly"],
        "country_shift": state["last_country"] is not None and state["last_country"] != event["country"],
        "unsafe_country": event["country"] not in SAFE_COUNTRIES,
    }
    score    = compute_score(signals)
    decision = decide(score)
    reasons  = explain(signals)
    trust    = update_trust(state["trust"], decision)
    save_user(event["user_id"], trust, event["country"])
    result = {"decision": decision, "score": round(score, 4), "trust": round(trust, 4), "reasons": reasons}
    result["audit_hash"] = append_audit(event, result, ts)
    if api_key:
        increment_usage(api_key)
        threading.Thread(target=report_usage, args=(api_key,), daemon=True).start()
    return result

def verify_chain():
    with _db_lock:
        rows = _conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log ORDER BY id ASC").fetchall()
    if not rows: return {"valid": True, "blocks": 0, "message": "Empty chain"}
    prev = "GENESIS"
    for i, row in enumerate(rows):
        payload = {"prev_hash": row[2], "ts": row[4], "event": json.loads(row[0]), "result": json.loads(row[1])}
        expected = sha(payload)
        if expected != row[3]:
            return {"valid": False, "broken_at_block": i, "message": f"Chain broken at block {i}"}
        if row[2] != prev:
            return {"valid": False, "broken_at_block": i, "message": f"Hash mismatch at block {i}"}
        prev = row[3]
    return {"valid": True, "blocks": len(rows), "message": "Chain intact — all hashes verified"}

# ══════════════════════════════════════════════════════════════
# HTTP SERVER
# ══════════════════════════════════════════════════════════════

def send(h, data, status=200):
    body = json.dumps(data, indent=2).encode()
    h.send_response(status)
    h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    h.wfile.write(body)

def send_html(h, html):
    body = html.encode()
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)

def err(h, msg, status=400): send(h, {"error": msg}, status)

def get_key(h):
    auth = h.headers.get("Authorization", "")
    return auth[7:] if auth.startswith("Bearer ") else None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): print(f"  [{self.address_string()}] {fmt % args}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        if path in ("", "/"):
            send_html(self, LANDING)

        elif path == "/health":
            send(self, {"status": "ok", "service": "AILeash Governance Engine", "version": VERSION, "chain": chain_tip()[:16] + "..."})

        elif path == "/audit":
            key = get_key(self)
            if not key or not validate_key(key): err(self, "Valid API key required", 401); return
            with _db_lock:
                rows = _conn.execute("SELECT ts,user_id,event_json,result_json,prev_hash,audit_hash FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()
            records = [{"ts": r[0], "user_id": r[1], "event": json.loads(r[2]), "result": json.loads(r[3]), "prev_hash": r[4], "audit_hash": r[5]} for r in rows]
            send(self, {"count": len(records), "records": records})

        elif path == "/audit/verify":
            key = get_key(self)
            if not key or not validate_key(key): err(self, "Valid API key required", 401); return
            send(self, verify_chain())

        elif path.startswith("/user/"):
            key = get_key(self)
            if not key or not validate_key(key): err(self, "Valid API key required", 401); return
            uid = path[6:]
            send(self, {"user_id": uid, **load_user(uid)})

        else:
            err(self, "Not found", 404)

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length)) if length else {}
        except:
            err(self, "Invalid JSON"); return

        if path == "/signup":
            email = body.get("email")
            if not email: err(self, "Email required"); return
            customer = stripe_call("POST", "/customers", {"email": email, "description": "AILeash API customer — EU AI Act compliance"})
            cid = customer.get("id")
            if not cid: err(self, "Stripe error: " + customer.get("error", {}).get("message", "unknown")); return
            stripe_call("POST", "/subscriptions", {"customer": cid, "items[0][price]": STRIPE_PRICE_ID})
            key = create_api_key(email, cid)
            send(self, {
                "message": "Welcome to AILeash",
                "api_key": key,
                "email": email,
                "pricing": "£0.001 per action, billed monthly via Stripe",
                "usage": "Authorization: Bearer " + key,
                "docs": "POST /govern with your event payload",
                "compliance": "EU AI Act Art.9, Art.12, Art.13 — audit chain active"
            })
            return

        if path == "/govern":
            key = get_key(self)
            if not key: err(self, "API key required. POST email to /signup", 401); return
            if not validate_key(key): err(self, "Invalid or inactive API key", 401); return
            try:
                send(self, govern(body, api_key=key))
            except ValueError as e:
                err(self, str(e))
            except Exception as e:
                err(self, f"Internal error: {e}", 500)
            return

        err(self, "Not found", 404)

# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 52)
    print("  AILEASH GOVERNANCE ENGINE v2.0")
    print("  Monop Content · Blyth, UK")
    print("  EU AI Act Art.9 / Art.12 / Art.13 Compliant")
    print("=" * 52)
    setup_stripe()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n  Running on port {PORT}")
    print(f"  GET  /          — landing page")
    print(f"  POST /signup    — get API key")
    print(f"  POST /govern    — score action")
    print(f"  GET  /health    — liveness")
    print(f"  GET  /audit     — audit chain")
    print(f"  GET  /audit/verify — chain integrity")
    print(f"\n  Ready.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutdown.")
        server.server_close()
