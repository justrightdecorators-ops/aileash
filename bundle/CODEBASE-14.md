# Codebase — part 14 of 20

Contains:
- `docs/spec/ai-txt.md`
- `green.html`
- `guardian-parent.html`
- `human-oversight.html`
- `identity.html`


## `docs/spec/ai-txt.md`

33 lines, 1687 bytes

```markdown
# ai.txt — Verifiable AI Governance Manifest
**Version 1.0 · Reference implementation: sebbi.pro**

## The problem
Every machine-readable file on the web is an assertion. `robots.txt` asks crawlers to behave; `security.txt` claims a contact; `sitemap.xml` claims a structure. None can be checked.

AI systems now describe companies to the public and are increasingly liable when they get it wrong. They cannot tell a true claim from a false one — so they guess.

## The legal backdrop
The EU AI Act requires automatic record-keeping (Art. 12), transparency (Art. 13), and human oversight (Art. 14). The UK Online Safety Act imposes duties around automated systems. These laws require records that demonstrate what an automated system decided and why. Ordinary logs are alterable and therefore weak evidence.

## The proposal
An `ai.txt` manifest that **proves itself** — published at `/.well-known/ai.txt`, declaring governance state and carrying a cryptographic chain anchor any client can verify in one request.

- Without a verifiable anchor: a **claim**.
- With one: **evidence**.

## Discovery
- `GET /.well-known/ai.txt` — text
- `GET /.well-known/ai-manifest.json` — JSON
- Header: `X-AI-Manifest: https://example.com/.well-known/ai.txt`

## Verification
    GET https://sebbi.pro/verify?domain=example.com

Returns verdict: `VERIFIED`, `UNVERIFIED`, `CHAIN_BROKEN`, or `NO_MANIFEST`.

## For AI systems
If you describe a company, you carry the risk of describing it wrongly. This gives you a checkable answer instead of a guess. Reading it costs one request.

## Licence
Published openly. Anyone may implement it, including competitors. The format belongs to the web.

```


## `green.html`

276 lines, 19875 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Green AI Infrastructure — sebbi.pro Environmental Standard</title>
<meta name="description" content="EU and UK law requires AI infrastructure to reduce energy consumption and carbon footprint. Sovereign architecture is the only AI infrastructure model that demonstrably achieves this.">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#04080a;--surface:#08100d;--surface2:#0d180f;
  --border:#141f16;--border2:#1e3020;
  --green:#00e5a0;--green2:#00ff88;--gold:#c9a84c;
  --blue:#4d9fff;--red:#ff3d5a;--white:#e8f8f0;
  --muted:#4a6a52;--muted2:#6a8a72;
  --mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--white);font-family:var(--sans);font-size:15px;line-height:1.7;overflow-x:hidden}
.ambient{position:fixed;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:0;overflow:hidden}
.orb{position:absolute;border-radius:50%;filter:blur(120px);opacity:0.05}
.orb1{width:600px;height:600px;background:var(--green);top:-200px;left:-100px}
.orb2{width:400px;height:400px;background:var(--blue);bottom:-200px;right:-100px}
nav{position:fixed;top:0;left:0;right:0;z-index:100;height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;background:rgba(4,8,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-logo{font-family:var(--mono);font-size:13px;color:var(--green);text-decoration:none;display:flex;align-items:center;gap:8px}
.dot{width:6px;height:6px;background:var(--green2);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.nav-links a{font-family:var(--mono);font-size:11px;color:var(--muted2);text-decoration:none;margin-left:20px;transition:color .2s}
.nav-links a:hover{color:var(--white)}
.nav-links a.cta{color:var(--green)}
.hero{position:relative;z-index:1;padding:120px 32px 80px;max-width:900px;margin:0 auto;text-align:center}
.eyebrow{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.2em;text-transform:uppercase;margin-bottom:20px}
h1{font-size:clamp(40px,6vw,72px);font-weight:700;line-height:1.05;letter-spacing:-0.04em;margin-bottom:20px}
h1 em{color:var(--green);font-style:normal}
.hero-sub{font-size:17px;color:var(--muted2);line-height:1.8;max-width:640px;margin:0 auto 40px}
.hero-sub strong{color:var(--white)}
.btn-green{background:linear-gradient(135deg,var(--green),var(--green2));color:#000;padding:13px 24px;border-radius:6px;font-weight:700;font-size:13px;text-decoration:none;font-family:var(--mono);letter-spacing:0.05em;display:inline-block;margin:6px;transition:all .2s}
.btn-green:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,229,160,0.25)}
.btn-ghost{border:1px solid var(--border2);color:var(--muted2);padding:13px 24px;border-radius:6px;font-size:13px;text-decoration:none;font-family:var(--mono);display:inline-block;margin:6px;transition:all .2s}
.btn-ghost:hover{border-color:var(--green);color:var(--green)}
.stat-strip{background:var(--surface);border-top:1px solid var(--border);border-bottom:1px solid var(--border);position:relative;z-index:1}
.stat-inner{max-width:900px;margin:0 auto;display:grid;grid-template-columns:repeat(4,1fr)}
.stat{padding:24px 16px;border-right:1px solid var(--border);text-align:center}.stat:last-child{border:none}
.stat-n{font-family:var(--mono);font-size:28px;color:var(--green);font-weight:700}
.stat-l{font-size:10px;color:var(--muted2);margin-top:4px;letter-spacing:1px;text-transform:uppercase}
.content{position:relative;z-index:1;max-width:900px;margin:0 auto;padding:0 32px 80px}
.sec{padding-top:60px;margin-bottom:48px}
.sec-eye{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.2em;text-transform:uppercase;margin-bottom:12px;display:flex;align-items:center;gap:8px}
.sec-eye::before{content:'//';color:var(--muted)}
h2{font-size:clamp(26px,4vw,40px);font-weight:700;letter-spacing:-0.03em;line-height:1.1;margin-bottom:12px}
h2 em{color:var(--green);font-style:normal}
.sec-sub{font-size:15px;color:var(--muted2);line-height:1.75;max-width:680px;margin-bottom:32px}
.law-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:24px}
.law-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px;border-left:3px solid var(--green)}
.law-tag{font-family:var(--mono);font-size:9px;color:var(--green);letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;display:block}
.law-title{font-size:13px;font-weight:600;margin-bottom:8px;color:var(--white)}
.law-desc{font-size:12px;color:var(--muted2);line-height:1.65}
.why-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:24px}
.why-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:24px;position:relative;overflow:hidden}
.why-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--green),transparent)}
.why-icon{font-size:24px;margin-bottom:12px}
.why-title{font-size:14px;font-weight:600;margin-bottom:8px}
.why-desc{font-size:13px;color:var(--muted2);line-height:1.65}
.compare{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-top:24px}
.compare-head{display:grid;grid-template-columns:1fr 1fr 1fr;background:var(--surface2);border-bottom:1px solid var(--border)}
.ch{padding:14px 16px;font-family:var(--mono);font-size:11px;font-weight:600;text-align:center}
.ch-metric{color:var(--muted2);text-align:left}
.ch-cloud{color:var(--red)}
.ch-sovereign{color:var(--green)}
.compare-row{display:grid;grid-template-columns:1fr 1fr 1fr;border-bottom:1px solid var(--border)}
.compare-row:last-child{border:none}
.compare-row:hover{background:rgba(0,229,160,0.02)}
.cr{padding:14px 16px;font-size:13px;text-align:center;display:flex;align-items:center;justify-content:center}
.cr-metric{color:var(--muted2);font-size:12px;text-align:left;justify-content:flex-start}
.cr-bad{color:var(--red)}
.cr-good{color:var(--green2);font-weight:600}
.code-block{background:rgba(0,0,0,0.4);border:1px solid var(--border2);border-radius:6px;padding:24px;font-family:var(--mono);font-size:12px;color:var(--green2);line-height:2;margin:24px 0;overflow-x:auto}
.cta-sec{background:linear-gradient(135deg,rgba(0,229,160,0.06),rgba(0,229,160,0.01));border:1px solid rgba(0,229,160,0.15);border-radius:16px;padding:48px;text-align:center;margin-top:60px}
.cta-sec h2{font-size:clamp(24px,4vw,40px);margin-bottom:12px}
.cta-sec p{font-size:15px;color:var(--muted2);margin-bottom:32px;max-width:500px;margin-left:auto;margin-right:auto}
footer{border-top:1px solid var(--border);padding:32px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--muted);position:relative;z-index:1}
footer a{color:var(--green);text-decoration:none}
@media(max-width:768px){
  .law-grid,.why-grid{grid-template-columns:1fr}
  .stat-inner{grid-template-columns:repeat(2,1fr)}
  .compare-head,.compare-row{grid-template-columns:1fr 1fr}
  .ch-metric,.cr-metric{display:none}
  nav{padding:0 16px}.nav-links{display:none}
  .hero,.content{padding-left:16px;padding-right:16px}
}
</style>
</head>
<body>
<div class="ambient"><div class="orb orb1"></div><div class="orb orb2"></div></div>

<nav>
  <a href="/" class="nav-logo"><div class="dot"></div>sebbi.pro</a>
  <div class="nav-links">
    <a href="#laws">The Laws</a>
    <a href="#sovereign">Sovereign Architecture</a>
    <a href="#brain">Brain Governance</a>
    <a href="/ai-standard">OAAS-1.0</a>
    <a href="/#signup" class="cta">Get Verified →</a>
  </div>
</nav>

<div class="hero">
  <div class="eyebrow">Environmental AI Standard</div>
  <h1>AI has an energy problem.<br><em>Sovereign architecture</em><br>solves it.</h1>
  <p class="hero-sub">EU and UK law now requires organisations to measure, report, and reduce the energy consumption of their AI infrastructure. <strong>Sovereign architecture — where AI decisions are processed on your own hardware — is the only model that demonstrably reduces AI energy consumption at the infrastructure level.</strong></p>
  <a href="#laws" class="btn-green">See the Laws →</a>
  <a href="/#signup" class="btn-ghost">Get Verified Free</a>
</div>

<div class="stat-strip">
  <div class="stat-inner">
    <div class="stat"><div class="stat-n">945 TWh</div><div class="stat-l">Data centre energy by 2030</div></div>
    <div class="stat"><div class="stat-n">1.5%</div><div class="stat-l">Global electricity used by AI now</div></div>
    <div class="stat"><div class="stat-n">3%</div><div class="stat-l">EU turnover fine for AI Act breach</div></div>
    <div class="stat"><div class="stat-n">2030</div><div class="stat-l">EU carbon-neutral data centre target</div></div>
  </div>
</div>

<div class="content">

  <div class="sec" id="laws">
    <div class="sec-eye">The Legal Framework</div>
    <h2>These are not guidelines.<br><em>These are laws.</em></h2>
    <p class="sec-sub">The EU and UK have enacted binding legislation requiring organisations to reduce the energy consumption and carbon footprint of their AI and data infrastructure. The direction of travel is unambiguous — and the pace of enforcement is accelerating.</p>

    <div class="law-grid">
      <div class="law-card">
        <span class="law-tag">Energy Efficiency Directive EU 2023/1791</span>
        <div class="law-title">Energy Efficiency First — Now a Legal Principle</div>
        <div class="law-desc">The revised Energy Efficiency Directive establishes Energy Efficiency First as a core principle of EU energy policy. Member states must prioritise this in all relevant policy decisions. Data centres with electrical demand of 500kW or more must report energy performance annually to the EU database. This includes total energy consumption, renewable energy use, waste heat, cooling efficiency, and water footprint.</div>
      </div>
      <div class="law-card">
        <span class="law-tag">EU AI Act 2024/1689 — Article 53</span>
        <div class="law-title">AI Energy Reporting — Mandatory</div>
        <div class="law-desc">Article 53 of the EU AI Act requires providers of general-purpose AI models to maintain technical documentation including energy consumption — whether known or estimated. The European Commission is developing a framework for measuring compliance with energy-related objectives and exploring a mandatory AI energy and emissions label. High-risk AI systems must document computational resources used during development, training, and operation.</div>
      </div>
      <div class="law-card">
        <span class="law-tag">Corporate Sustainability Reporting Directive</span>
        <div class="law-title">AI Energy Disclosure — Mandatory for Large Companies</div>
        <div class="law-desc">The CSRD requires disclosure of energy consumption and environmental impacts including greenhouse gas emissions and energy efficiency of AI algorithms. Sections 19-21 specifically address AI infrastructure. Organisations that cannot demonstrate the energy efficiency of their AI infrastructure will face increasing pressure from investors, regulators, and customers who must report on their own supply chain emissions.</div>
      </div>
      <div class="law-card">
        <span class="law-tag">Germany EnEfG — Energy Efficiency Act</span>
        <div class="law-title">Already in Force for German Data Centres</div>
        <div class="law-desc">Germany's Energy Efficiency Act applies to data centres with capacity of 300kW or more. It mandates a renewable electricity share of 50%, rising to 100% from January 2027. Energy reuse obligations apply to data centres coming into operation from July 2026. Power usage effectiveness obligations apply from July 2027. Germany is the EU's largest economy — where Germany leads, the rest of Europe follows.</div>
      </div>
      <div class="law-card">
        <span class="law-tag">UK Climate Change Agreement Targets 2026</span>
        <div class="law-title">Legally Binding Carbon Reduction Targets</div>
        <div class="law-desc">UK data centres designated as Critical National Infrastructure in 2024 face mandatory disclosure requirements. 2026 marks the first year where Building Lifecycle Carbon is a mandatory disclosure for data centre operators. The Climate Change Act 2008 imposes legally binding carbon budgets. Organisations whose AI infrastructure cannot demonstrate energy efficiency face increasing regulatory and procurement barriers.</div>
      </div>
      <div class="law-card">
        <span class="law-tag">EU Data Centre Energy Efficiency Package 2026</span>
        <div class="law-title">Carbon-Neutral Data Centres by 2030</div>
        <div class="law-desc">The European Commission's Data Centre Energy Efficiency Package, published in Q1 2026 alongside the Strategy Roadmap on Digitalisation and AI, sets the goal of carbon-neutral data centres by 2030. A rating scheme for EU data centres is being introduced. Minimum performance standards for data centres will follow. The IEA projects data centre energy consumption will more than double to 945 TWh by 2030 — primarily driven by AI.</div>
      </div>
    </div>
  </div>

  <div class="sec" id="sovereign">
    <div class="sec-eye">The Solution</div>
    <h2>Sovereign architecture.<br><em>Less energy. Full compliance.</em></h2>
    <p class="sec-sub">The only AI infrastructure model that demonstrably reduces energy consumption at the infrastructure level is sovereign architecture — where AI decisions are processed on the organisation's own hardware, with data never routed through third-party data centres.</p>

    <div class="compare">
      <div class="compare-head">
        <div class="ch ch-metric">Metric</div>
        <div class="ch ch-cloud">Cloud-Routed AI</div>
        <div class="ch ch-sovereign">Sovereign Architecture</div>
      </div>
      <div class="compare-row">
        <div class="cr cr-metric">Data transmission energy</div>
        <div class="cr cr-bad">High — every decision routed to third-party servers and back</div>
        <div class="cr cr-good">Zero — decisions processed on your own hardware</div>
      </div>
      <div class="compare-row">
        <div class="cr cr-metric">Third-party data centre dependency</div>
        <div class="cr cr-bad">Full — your AI runs on someone else's infrastructure</div>
        <div class="cr cr-good">None — your infrastructure, your energy choices</div>
      </div>
      <div class="compare-row">
        <div class="cr cr-metric">Energy reporting capability</div>
        <div class="cr cr-bad">Limited — dependent on third-party disclosure</div>
        <div class="cr cr-good">Complete — full visibility of your own infrastructure</div>
      </div>
      <div class="compare-row">
        <div class="cr cr-metric">Carbon footprint auditability</div>
        <div class="cr cr-bad">Partial — shared infrastructure complicates attribution</div>
        <div class="cr cr-good">Full — your hardware, your carbon, your audit</div>
      </div>
      <div class="compare-row">
        <div class="cr cr-metric">EU Energy Efficiency Directive compliance</div>
        <div class="cr cr-bad">Dependent on cloud provider compliance</div>
        <div class="cr cr-good">Direct — you control and report your own energy use</div>
      </div>
    </div>

    <div class="why-grid" style="margin-top:24px">
      <div class="why-card">
        <div class="why-icon">⚡</div>
        <div class="why-title">Eliminates unnecessary data transmission</div>
        <div class="why-desc">Every AI decision routed through a cloud provider requires data to travel from your system, to a third-party data centre, be processed, and return. Sovereign architecture eliminates this entirely. The decision happens where the data already is.</div>
      </div>
      <div class="why-card">
        <div class="why-icon">📊</div>
        <div class="why-title">Full energy reporting capability</div>
        <div class="why-desc">EU law requires organisations to report on AI energy consumption. With cloud-routed AI, you depend on your provider's disclosure. With sovereign architecture, you have complete visibility and control over every watt your AI system consumes.</div>
      </div>
      <div class="why-card">
        <div class="why-icon">🌍</div>
        <div class="why-title">Supports legally binding carbon targets</div>
        <div class="why-desc">The UK Climate Change Act and EU Green Deal impose legally binding carbon reduction obligations. Organisations must demonstrate progress. Sovereign AI infrastructure gives you the direct control and auditability that regulators expect to see.</div>
      </div>
      <div class="why-card">
        <div class="why-icon">🏗️</div>
        <div class="why-title">Infrastructure costs stay flat as you scale</div>
        <div class="why-desc">Cloud-routed AI costs grow with every decision. Sovereign architecture means your infrastructure costs stay flat regardless of volume — which also means your energy per decision falls as you scale. Better for your budget. Better for the planet.</div>
      </div>
    </div>
  </div>

  <div class="sec" id="brain">
    <div class="sec-eye">Brain Governance</div>
    <h2>The Brain records it.<br><em>The chain proves it.</em></h2>
    <p class="sec-sub">AILeash Brain is the cryptographic instruction governance layer that enforces what AI systems can and cannot do — and seals every decision in a SHA-256 Merkle chain. Every governance decision is permanently recorded, including the energy context in which it was made.</p>

    <div class="code-block">
# Every governance decision sealed in the chain
# Including energy-relevant context

{
  "decision": "ALLOW",
  "instruction_hash": "a3f8c2d1e9b7...",
  "threat_category": "none",
  "risk_score": 0.0,
  "audit_hash": "9462e908f1c3...",
  "ms": 4.2
}

# Sub-5ms decisions
# Zero third-party data transmission
# Every decision permanently recorded
# Chain verifiable by any regulator
    </div>

    <p style="font-size:14px;color:var(--muted2);line-height:1.75;margin-top:16px">The AILeash Brain runs on your own hardware. Every instruction is hashed and checked in milliseconds. Every decision is sealed in a tamper-proof chain. No data leaves your network. No unnecessary energy consumed in transmission. The audit trail regulators require is built automatically into every decision your AI system makes.</p>

    <div style="text-align:center;margin-top:28px">
      <a href="/brain" class="btn-green">Explore AILeash Brain →</a>
      <a href="/ai-standard" class="btn-ghost">View OAAS-1.0 Standard</a>
    </div>
  </div>

  <div class="cta-sec">
    <h2>Free to verify.<br><em>50p per device per month.</em></h2>
    <p>100 free decisions. SHA-256 Merkle chain started instantly. No card required. Your sovereign AI infrastructure — compliant with EU energy law, UK carbon targets, and the EU AI Act — starts today.</p>
    <a href="/#signup" class="btn-green">Get Your Free API Key →</a>
    <a href="/ai-standard" class="btn-ghost">Read the OAAS-1.0 Standard</a>
  </div>

</div>

<footer>
  <p>sebbi.pro Environmental AI Standard · Monop Content · Blyth, Northumberland, UK · 2026</p>
  <p style="margin-top:8px;color:var(--muted)">Referenced legislation: EU EED 2023/1791 · EU AI Act 2024/1689 · CSRD · EnEfG · UK Climate Change Act 2008 · <a href="/ai-standard">OAAS-1.0</a></p>
</footer>

</body>
</html>

```


## `guardian-parent.html`

70 lines, 4511 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0f1e">
<title>Guardian - Child safety for your platform</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#fff;min-height:100vh;line-height:1.6}
.wrap{max-width:620px;margin:0 auto;padding:28px 20px 80px}
.logo{display:flex;align-items:center;gap:10px;margin-bottom:24px}
h1{font-size:30px;font-weight:800}h1 span{color:#c9a84c}
.lead{font-size:18px;color:#e8e8f0;margin-bottom:8px;font-weight:600}
.sub{color:#8a90a6;font-size:15px;margin-bottom:26px}
.box{background:#111a30;border:1px solid #232d4a;border-radius:14px;padding:20px;margin-bottom:16px}
.box h2{font-size:12px;color:#c9a84c;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:14px}
.line{display:flex;gap:12px;margin:12px 0;font-size:15px;color:#c2c8dc}
.line b{color:#c9a84c;flex-shrink:0;font-size:18px}
.price{background:#0d2018;border:1px solid #1fae79;border-radius:14px;padding:20px;text-align:center;margin-bottom:16px}
.price .big{font-size:34px;font-weight:800;color:#7fe3b0}
.price .p{color:#a9b0c4;font-size:14px;margin-top:4px}
.cta{display:block;background:#c9a84c;color:#0a0f1e;text-align:center;padding:18px;border-radius:12px;font-weight:800;font-size:17px;text-decoration:none;margin:22px 0 10px}
.law{background:#1a1206;border:1px solid #c9a84c;border-radius:12px;padding:16px;font-size:14px;color:#e8d9b0;margin-bottom:16px;line-height:1.7}
.tiny{color:#5a6178;font-size:12px;margin-top:20px;line-height:1.7}
a.back{color:#c9a84c;text-decoration:none;font-size:14px;font-family:monospace}
</style>
</head>
<body>
<div class="wrap">
  <div class="logo">
    <svg width="30" height="30" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/></svg>
    <a class="back" href="/">&larr; AILeash</a>
  </div>

  <h1>Guard<span>ian</span></h1>
  <p class="lead">Child safety, built into your platform.</p>
  <p class="sub">For consoles, games and apps with young users &mdash; PlayStation, Roblox, Discord, TikTok and the like. The Online Safety Act now makes you responsible for keeping kids safe. Guardian is how you do it, and how you prove it.</p>

  <div class="law">
    <b>The problem:</b> if under-18s use your platform, the Online Safety Act says you must protect them from grooming and harm &mdash; and prove to Ofcom that you did. Get it wrong and the fines are huge.
  </div>

  <div class="box">
    <h2>What Guardian gives your platform</h2>
    <div class="line"><b>1</b><span>A one-tap <b>Help button</b> your young users can hit if something feels wrong &mdash; it alerts instantly.</span></div>
    <div class="line"><b>2</b><span>Automatic <b>grooming-pattern flagging</b> on messages &mdash; it never falsely tells a child something is "safe".</span></div>
    <div class="line"><b>3</b><span>A <b>tamper-proof record</b> of every safety event &mdash; the exact evidence Ofcom asks for, provable on demand.</span></div>
    <div class="line"><b>4</b><span><b>CEOP, Childline and 999</b> one tap away for every child, always.</span></div>
  </div>

  <div class="box">
    <h2>How you use it</h2>
    <div class="line"><b>&#9656;</b><span>Sign up below and get your <b>API key</b>.</span></div>
    <div class="line"><b>&#9656;</b><span>Your developers wire Guardian into <b>your own app</b> &mdash; your design, your branding. Our engine runs underneath, invisible.</span></div>
    <div class="line"><b>&#9656;</b><span>Your young users are protected, and you have the audit trail proving it. Done.</span></div>
  </div>

  <div class="price">
    <div class="big">50p</div>
    <div class="p">per device, per month. The families on your platform never pay a penny.</div>
  </div>

  <a class="cta" href="/#signup" onclick="setProduct&&setProduct('guardian')">Sign up &amp; get your Guardian API key &rarr;</a>

  <div class="tiny">Guardian cannot secretly read anyone's phone &mdash; that is deliberate. It flags known-risky patterns and lets a child ask for help. Message content is never stored, only a tamper-evident fingerprint. Any product promising to secretly read a child's phone is either lying or spyware.</div>
</div>
</body>
</html>

```


## `human-oversight.html`

115 lines, 13247 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Human Oversight Policy — Monop Content / AILeash</title>
<meta name="description" content="How human oversight is engineered into the AILeash platform: commit-before-reveal, the CHALLENGE flow, delegated authority tokens, conformance probes, and the sealed evidence trail behind every human intervention. Aligned to EU AI Act Article 14.">
<style>
  :root{--ink:#0a0f1e;--ink2:#111a30;--line:#232d4a;--gold:#c9a84c;--gold-dim:#8a7838;--ok:#7fe3b0;--text:#e8e8f0;--muted:#c2c8dc;--faint:#5a6178;--code-bg:#0b1226}
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--ink);color:#fff;line-height:1.7;-webkit-font-smoothing:antialiased}
  .wrap{max-width:720px;margin:0 auto;padding:26px 20px 90px}
  a.back{color:var(--gold);text-decoration:none;font-size:13px;font-family:ui-monospace,Menlo,monospace;letter-spacing:.5px}
  .eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:var(--gold-dim);margin:22px 0 10px}
  h1{font-size:28px;font-weight:800;letter-spacing:-.5px;margin-bottom:10px;line-height:1.2}
  h1 span{color:var(--gold)}
  .meta{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--faint);margin-bottom:26px;line-height:1.9}
  h2{font-size:19px;font-weight:800;margin:40px 0 8px;letter-spacing:-.3px}
  h2 .n{color:var(--gold);font-family:ui-monospace,Menlo,monospace;font-size:13px;margin-right:8px}
  h3{font-size:15px;font-weight:700;margin:22px 0 6px;color:var(--gold)}
  p{font-size:14.5px;color:var(--muted);margin-bottom:13px}
  p b{color:#fff}
  ul{margin:0 0 14px 0;list-style:none}
  li{position:relative;padding-left:20px;margin-bottom:9px;font-size:14px;color:var(--muted)}
  li::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--gold)}
  li b{color:#fff}
  pre{background:var(--code-bg);border:1px solid var(--line);border-radius:10px;padding:15px;font-size:12.5px;color:var(--muted);overflow-x:auto;margin:14px 0;font-family:ui-monospace,Menlo,monospace;line-height:1.8}
  pre b{color:var(--ok);font-weight:400}
  .honest{border:1px solid rgba(201,168,76,.35);background:rgba(201,168,76,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .honest b{color:var(--gold)}
  hr{border:none;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,.25),transparent);margin:40px 0 0}
  footer{margin-top:30px;text-align:center;font-size:12px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
  footer a{color:var(--gold);text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; sebbi.pro</a>
  <div class="eyebrow">monop content · policy document · public</div>
  <h1>Human Oversight Policy<br><span>AILeash Platform</span></h1>
  <div class="meta">
    Document: MC-POL-003 · Version 2.0 · Effective 28 July 2026 · supersedes v1.0 (20 July 2026)<br>
    Owner: Justin Dobson, Founder, Monop Content · Review cycle: quarterly, and on any change to the challenge, authority, commitment or conformance mechanisms<br>
    Alignment: EU AI Act (Regulation 2024/1689) Article 14 · published at sebbi.pro/human-oversight
  </div>

  <h2><span class="n">1.</span>Position: oversight as engineering, not paperwork</h2>
  <p>"Human in the loop" fails in practice for three predictable reasons: the human is invoked too late or not at all; nobody can later prove the human who intervened was actually authorised to; and — least often admitted — nobody can show the human did anything more than agree with whatever the machine had already decided.</p>
  <p>This policy describes how the platform engineers all three away as far as they can be engineered, and states plainly where engineering stops.</p>

  <div class="honest"><b>What this policy does not claim.</b> No system can prove a person deliberated. That is an internal state and no amount of recording reaches it. Any vendor asserting proof of genuine human thought is describing something that does not exist. What follows is what <i>can</i> be proved: that a human was invoked, that they were authorised, that they committed before they knew the answer, how long they took, and how often they disagree.</div>

  <h2><span class="n">2.</span>When a human is brought in: the CHALLENGE band</h2>
  <p>The decision engine returns three verdicts. ALLOW and BLOCK are the clear cases. Between them sits a deliberate band — <b>CHALLENGE</b> — where the engine's judgement is that the event is neither safe enough to pass nor dangerous enough to refuse, and a human must decide.</p>
  <p>A CHALLENGE verdict is not advisory. The response includes a hosted resolution flow: a signed link the affected user or an authorised reviewer opens to confirm or deny the action, a status endpoint the customer's system polls, and an expiry after which the challenge lapses unresolved. Tokens are stateless and HMAC-signed; they cannot be forged or replayed after expiry.</p>
  <pre>event → engine → <b>CHALLENGE</b> → hosted confirm/deny (human)
       → resolution <b>sealed into the chain as its own block</b>
       → customer system reads the outcome and proceeds accordingly</pre>
  <p>The critical property: <b>the exception path is part of the evidence trail, not a gap in it.</b> Every human intervention — that it happened, when, and with what outcome — is sealed with the same tamper-evidence as the machine decisions around it.</p>

  <h2><span class="n">3.</span>Commit before reveal: proving the judgement was independent</h2>
  <p>An oversight record showing that a reviewer approved a decision the machine had already displayed to them proves very little. It is consistent with careful agreement and equally consistent with a rubber stamp. Until the two can be told apart, "human oversight" is an assertion.</p>
  <p>The platform separates them by controlling <b>order</b>. A case is opened with the material and the machine's verdict, and the verdict is returned to the caller as <i>withheld</i>. The reviewer sees the case, not the answer. Their own decision and their reasoning are sealed as a block. Only then is the machine verdict released.</p>
  <pre>open   → material sealed · machine verdict sealed but <b>withheld</b>
review → human sees the case, not the answer
commit → <b>human verdict and reasoning sealed</b>
reveal → machine verdict returned
result → the chain shows the human committed first</pre>
  <p>Because blocks cannot be reordered without breaking every block after them, the record establishes that the reviewer could not simply have agreed with an answer they had already seen. That is not proof of thought. It is proof of independence, which is the part Article 14 actually turns on.</p>

  <h3>Attention and divergence</h3>
  <ul>
    <li><b>Dwell time</b> — the interval between opening a case and committing to it is sealed with the decision. A sub-second approval sits in the record permanently, beside a two-minute one. One fast decision means nothing; four hundred consecutive fast decisions is a pattern that survives being explained away.</li>
    <li><b>Divergence rate</b> — agreement with the machine is recorded per reviewer over time. A reviewer who has never once disagreed across a meaningful sample is visible in the data. One who diverges sometimes is demonstrably exercising judgement.</li>
    <li><b>Reasoning</b> — a commitment with blank reasoning is refused outright. The reasoning is the part that gets examined later.</li>
  </ul>

  <h2><span class="n">4.</span>Who may oversee: delegated authority, sealed</h2>
  <p>Oversight only satisfies Article 14 if the human is competent and mandated — and if that mandate can be demonstrated afterwards. The platform makes the mandate a first-class object:</p>
  <ul>
    <li>A customer issues a <b>signed authority token</b> binding a named user identifier to a role, a maximum amount, and an expiry. The grant itself is sealed into the chain at the moment of issue — who was empowered, to what limit, until when, is a permanent record.</li>
    <li>Events carrying an authority token are verified deterministically. A token that is invalid, expired, bound to a different user, or below the amount at stake causes the verdict to <b>escalate</b> — an ALLOW becomes a CHALLENGE — with the specific reason (e.g. <i>authority_expired</i>, <i>authority_exceeds_limit</i>) sealed into the decision record.</li>
    <li>An approval made outside granted authority therefore cannot pass silently. It becomes a flagged, sealed, examinable event — visible to the customer's own audit and to any later review.</li>
  </ul>

  <h2><span class="n">5.</span>The overseer's information: explainability</h2>
  <p>A human cannot meaningfully oversee a verdict they cannot understand. Every verdict the engine returns carries its reasons in plain English — "velocity spike", "new country", "low trust", "authority exceeds limit" — not scores alone and never an unexplained refusal. The engine is deterministic: identical inputs always yield identical verdicts, so an overseer (or a court) re-examining a decision later sees exactly what the system saw and why it concluded what it did.</p>

  <h2><span class="n">6.</span>Override and the record of it</h2>
  <p>Ultimate control rests with the customer's humans, not with the engine. A customer may resolve any CHALLENGE in either direction, and may configure their own systems to overrule engine verdicts. The platform's role is not to remove human authority but to make its exercise <b>attributable and permanent</b>: the resolution, the resolver, and the timing are sealed. Oversight without a record is a claim; this is oversight with proof.</p>

  <h2><span class="n">7.</span>Conformance: testing the arrangement rather than trusting it</h2>
  <p>Section 3 has a dependency that must be stated openly. <b>The ordering guarantee holds only if the integrating system honours it.</b> If a platform displays the machine verdict to its own reviewers before opening the case, the sealed order proves nothing. The engine cannot see inside a customer's interface and does not pretend to.</p>
  <p>What it can do is test the arrangement from the outside, using the method substantive audit has always used — and specifically the approach set out publicly by <b>James Stokes of Red Flag AI Pro</b>: place a case with a known answer into the queue, unannounced, and see who catches it.</p>
  <ul>
    <li>A <b>probe</b> is a genuine oversight case whose machine verdict has been deliberately set to a known-wrong value. To the reviewer it is indistinguishable from any other case.</li>
    <li>Agreeing with the planted verdict means the case was not evaluated. That is a caught rubber stamp, sealed like any other event.</li>
    <li>If the interface is leaking the verdict early, a reviewer's agreement rate on probes will track their agreement rate on ordinary cases. If they are deciding blind, it will not. <b>The gap between those two figures is the conformance signal.</b></li>
  </ul>
  <p>A single probe establishes nothing about an individual. A catch rate across dozens is evidence about a process, and the process is what is under audit.</p>

  <h2><span class="n">8.</span>Oversight of the platform itself</h2>
  <p>Monop Content applies the same standard to its own operation. The Founder is the accountable human for the platform (see the Risk Management Policy, MC-POL-001). Platform-level changes deploy only through a version-controlled pipeline attributable to a named commit; the platform cannot alter its own sealed history, and its integrity is continuously checkable by anyone at the public verification endpoint — meaning the platform's overseer is, by design, also overseeable.</p>

  <div class="honest"><b>Honest limits, restated.</b> The platform routes borderline decisions to humans, proves who intervened with what mandate, and establishes that they committed before the answer was disclosed to them. It cannot make the human's judgement correct and does not claim to. A reviewer can leave a screen open, so dwell time is gameable by anyone deliberately gaming it. Authority tokens prove the grant, not the wisdom of granting it. Probes test a process, not a person — someone can catch a probe and rubber stamp the next hundred cases — and an operator who identifies probe cases controls their own interface. Customers remain responsible for staffing oversight roles with competent people; no software discharges that duty for them.</div>

  <hr>
  <footer>
    <p style="margin-top:20px"><a href="/">sebbi.pro</a> · <a href="/risk-policy">Risk Management Policy</a> · <a href="/data-protection">Data Protection Statement</a> · <a href="/whitepaper">Whitepaper</a> · <a href="/contact">Contact</a></p>
    <p style="margin-top:8px;color:var(--faint)">Monop Content · Blyth, Northumberland, UK · justin@monopcontent.com</p>
  </footer>
</div>
</body>
</html>

```


## `identity.html`

151 lines, 9171 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Identity Notary — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#fff;font-family:system-ui,sans-serif;min-height:100vh;padding:24px}
  .wrap{max-width:560px;margin:0 auto}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:26px;color:var(--gold);margin:14px 0 6px}
  .sub{font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.7;margin-bottom:22px}
  label{display:block;font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.45);margin:16px 0 6px}
  input{width:100%;background:var(--ink2);border:1px solid rgba(201,168,76,0.35);color:#fff;border-radius:8px;padding:13px;font-size:15px;outline:none}
  input:focus{border-color:var(--gold)}
  button{width:100%;margin-top:20px;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:16px;font-size:16px;font-weight:800;cursor:pointer}
  button:disabled{opacity:0.5}
  #cert{display:none;margin-top:24px;background:var(--ink2);border:2px solid var(--gold);border-radius:12px;padding:28px;text-align:center}
  #cert .seal-ring{width:64px;height:64px;margin:0 auto 14px}
  #cert h2{font-family:Georgia,serif;font-size:22px;color:#fff;margin-bottom:4px}
  #cert .who{font-family:Georgia,serif;font-style:italic;font-size:18px;color:var(--gold);margin-bottom:14px}
  #cert .row{font-family:monospace;font-size:11px;color:rgba(255,255,255,0.6);line-height:2;word-break:break-all;text-align:left;background:rgba(0,0,0,0.3);border-radius:8px;padding:14px;margin-top:10px}
  #cert .row b{color:var(--ok)}
  #status{margin-top:14px;font-family:monospace;font-size:12px;line-height:1.8;word-break:break-all}
  .ok{color:var(--ok)}.err{color:var(--err)}
  .note{margin-top:22px;font-size:12px;color:rgba(255,255,255,0.35);line-height:1.8}
  .note b{color:var(--gold);font-weight:600}
  a{color:var(--gold)}
  .copybtn{background:var(--ink);color:var(--gold);border:1px solid rgba(201,168,76,0.4);margin-top:12px;padding:12px;font-size:13px;font-weight:600}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">sebbi.pro &middot; sovereign identity notary</div>
  <h1>Seal your identity into the chain.</h1>
  <div class="sub">Enter your details below. They are fingerprinted with SHA-256 <b>inside your own browser</b> — the details themselves never leave your device and are never stored. Only the fingerprint is sealed into the live audit chain, creating permanent, tamper-evident proof that this exact identity existed at this exact moment.</div>

  <label>Full name</label>
  <input id="nm" placeholder="Justin Antony Dobson">

  <label>Email</label>
  <input id="em" type="email" placeholder="you@example.com">

  <label>Organisation (optional)</label>
  <input id="org" placeholder="Monop Content">

  <label>Title (optional)</label>
  <input id="ttl" placeholder="Founder">

  <label>One-line bio (optional)</label>
  <input id="bio" placeholder="Building tamper-evident AI compliance from Blyth.">

  <button id="go" onclick="notarise()">Notarise this identity &rarr;</button>
  <div id="status"></div>

  <div id="cert">
    <svg class="seal-ring" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/><circle cx="16" cy="16" r="3.4" fill="#0a0f1e"/></svg>
    <h2>Certificate of Notarised Identity</h2>
    <div class="who" id="cwho"></div>
    <div class="row" id="crow"></div>
    <canvas id="cardcanvas" width="1200" height="628" style="width:100%;border-radius:8px;margin-top:14px;border:1px solid rgba(201,168,76,0.4)"></canvas>
    <a id="carddl" class="copybtn" style="display:block;text-align:center;text-decoration:none" download="identity-card.png">Download identity card</a>
    <button class="copybtn" onclick="copyCert()">Copy certificate text</button>
  </div>

  <div class="note"><b>Verify any time:</b> re-enter the identical details on this page and the chain will return the same fingerprint, block and timestamp — proof nothing changed. One character different produces a completely different fingerprint. Powered by the same engine that seals AI decisions: <a href="/">free for 90 days &rarr;</a></div>
</div>

<script>
var lastCert="";
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
async function notarise(){
  var nm=document.getElementById("nm").value.trim();
  var em=document.getElementById("em").value.trim().toLowerCase();
  var org=document.getElementById("org").value.trim();
  var st=document.getElementById("status");
  var cert=document.getElementById("cert");
  cert.style.display="none";
  if(!nm||!em||em.indexOf("@")<0){st.innerHTML="<span class='err'>Name and a valid email are required.</span>";return;}
  var btn=document.getElementById("go");btn.disabled=true;
  st.innerHTML="Fingerprinting in your browser\u2026";
  try{
    var ttl=document.getElementById("ttl").value.trim();var bio=document.getElementById("bio").value.trim();var canonical="identity:v1|"+nm+"|"+em+"|"+org+"|"+ttl+"|"+bio;
    var fp=await sha256hex(canonical);
    st.innerHTML="Fingerprint "+fp.slice(0,20)+"\u2026<br>Sealing into the chain\u2026";
    var r=await fetch("/api/identity/seal",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({fingerprint:fp})});
    var d=await r.json();
    if(!d.sealed){st.innerHTML="<span class='err'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;return;}
    var when=new Date((d.sealed_at||Date.now()/1000)*1000);
    document.getElementById("cwho").textContent=nm+(org?(" \u00b7 "+org):"");
    document.getElementById("crow").innerHTML=
      "Fingerprint <b>"+fp+"</b><br>"+
      "Sealed in block <b>#"+d.block_index+"</b> of the live sebbi.pro audit chain<br>"+
      "Seal <b>"+d.seal+"</b><br>"+
      "Timestamp <b>"+when.toLocaleString("en-GB")+"</b><br>"+
      "Chain verification: sebbi.pro/api/inclusion?hash="+d.seal;
    lastCert="CERTIFICATE OF NOTARISED IDENTITY \u2014 sebbi.pro\n"+
      nm+(org?(" \u00b7 "+org):"")+"\n"+
      "Fingerprint: "+fp+"\n"+
      "Block: #"+d.block_index+"\nSeal: "+d.seal+"\n"+
      "Timestamp: "+when.toLocaleString("en-GB")+"\n"+
      "Verify: sebbi.pro/api/inclusion?hash="+d.seal;
    cert.style.display="block";drawCard(nm,ttl,org,bio,fp,d);
    st.innerHTML="<span class='ok'>\u2713 Identity notarised. The details never left this device \u2014 only the fingerprint is in the chain.</span>";
  }catch(e){st.innerHTML="<span class='err'>Network error: "+e+"</span>";}
  btn.disabled=false;
}
function drawCard(nm,ttl,org,bio,fp,d){
  var c=document.getElementById("cardcanvas"),x=c.getContext("2d");
  var W=c.width,H=c.height;
  var g=x.createLinearGradient(0,0,W,H);g.addColorStop(0,"#0a0f1e");g.addColorStop(1,"#141d36");
  x.fillStyle=g;x.fillRect(0,0,W,H);
  x.strokeStyle="#c9a84c";x.lineWidth=6;x.strokeRect(14,14,W-28,H-28);
  x.strokeStyle="rgba(201,168,76,0.35)";x.lineWidth=1.5;x.setLineDash([6,5]);x.strokeRect(30,30,W-60,H-60);x.setLineDash([]);
  x.fillStyle="#c9a84c";x.font="600 22px monospace";x.textAlign="center";
  x.fillText("CERTIFICATE OF NOTARISED IDENTITY",W/2,86);
  x.fillStyle="#ffffff";x.font="900 64px Georgia";
  x.fillText(nm,W/2,180);
  x.fillStyle="#c9a84c";x.font="italic 600 30px Georgia";
  var sub=(ttl?ttl:"")+(ttl&&org?" \u00b7 ":"")+(org?org:"");
  if(sub)x.fillText(sub,W/2,226);
  if(bio){x.fillStyle="rgba(255,255,255,0.65)";x.font="26px Georgia";x.fillText(bio.slice(0,70),W/2,274);}
  /* seal ring */
  x.save();x.translate(W/2,360);x.strokeStyle="#c9a84c";x.lineWidth=7;x.setLineDash([52,16]);
  x.beginPath();x.arc(0,0,44,0,Math.PI*2);x.stroke();x.setLineDash([]);
  x.fillStyle="#c9a84c";x.beginPath();x.arc(30,-30,9,0,7);x.fill();
  x.fillStyle="#0a0f1e";x.beginPath();x.arc(0,0,11,0,7);x.fill();x.restore();
  x.fillStyle="#7fe3b0";x.font="600 21px monospace";
  x.fillText("FINGERPRINT "+fp.slice(0,40)+"\u2026",W/2,452);
  x.fillStyle="rgba(255,255,255,0.6)";x.font="600 21px monospace";
  x.fillText("SEALED IN BLOCK #"+d.block_index+" \u00b7 LIVE SEBBI.PRO AUDIT CHAIN",W/2,490);
  x.fillText(new Date(d.sealed_at*1000).toLocaleString("en-GB"),W/2,524);
  x.fillStyle="#c9a84c";x.font="600 20px monospace";
  x.fillText("verify: sebbi.pro/api/inclusion?hash="+d.seal.slice(0,24)+"\u2026",W/2,572);
  document.getElementById("carddl").href=c.toDataURL("image/png");
}
function copyCert(){
  navigator.clipboard.writeText(lastCert).then(function(){
    document.getElementById("status").innerHTML="<span class='ok'>Certificate copied.</span>";
  });
}
</script>
</body>
</html>

```
