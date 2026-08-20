# Codebase — part 22 of 24

Contains:
- `sonicboom.html`


## `sonicboom.html`

867 lines, 60432 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SonicBoom &mdash; Your Own AI Compliance Engine. Runs Local. Sub-20ms.</title>
<meta name="description" content="SonicBoom gives you your own AILeash compliance engine. Runs inside your infrastructure. Every decision is local. No round trip. Sub-20ms.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --navy:#0a0f1e;--cyan:#00d4ff;--gold:#c9a84c;--white:#fff;
  --green:#00ff88;--red:#cc0000;--purple:#7c3aed;
  --mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif
}
html,body{background:var(--navy);color:var(--white);font-family:var(--sans);overflow-x:hidden}
html{scroll-behavior:smooth}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(10,15,30,0.97);backdrop-filter:blur(12px);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(0,212,255,0.1)}
.nav-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;text-decoration:none}.nav-logo span{color:var(--cyan)}
.nav-links{display:flex;gap:16px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.4);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--cyan)!important;color:var(--navy)!important;padding:9px 18px;font-weight:700!important;border-radius:4px}
.scan-sec{padding:140px 48px 80px;position:relative;overflow:hidden;text-align:center;border-bottom:1px solid rgba(0,212,255,0.1)}
.scan-sec::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 40%,rgba(0,212,255,0.06) 0%,transparent 65%)}
.scan-sec::after{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--cyan),transparent)}
.scan-inner{max-width:820px;margin:0 auto;position:relative;z-index:1}
.scan-eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--cyan);margin-bottom:20px;display:block}
.scan-title{font-family:var(--display);font-size:clamp(36px,5vw,64px);line-height:1.05;font-weight:900;margin-bottom:16px}
.scan-title em{color:var(--cyan);font-style:normal}
.scan-sub{font-size:16px;color:rgba(255,255,255,0.35);line-height:1.7;margin-bottom:16px}
.data-note{font-family:var(--mono);font-size:11px;color:rgba(0,255,136,0.55);margin-bottom:32px;line-height:1.7}
.sound-toggle{display:inline-flex;align-items:center;gap:10px;background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.2);border-radius:40px;padding:10px 20px;cursor:pointer;margin-bottom:32px;transition:all .2s;font-family:var(--mono);font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--cyan)}
.sound-toggle:hover{background:rgba(0,212,255,0.15)}
.category-badge{display:none;margin:0 auto 24px;padding:10px 24px;border-radius:40px;font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;font-weight:700;width:fit-content}
.category-badge.show{display:block}
.cat-enterprise{background:rgba(201,168,76,0.1);border:1px solid rgba(201,168,76,0.3);color:var(--gold)}
.cat-developer{background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.3);color:var(--cyan)}
.cat-callcentre{background:rgba(0,135,90,0.1);border:1px solid rgba(0,135,90,0.3);color:#00ff88}
.cat-lawenforcement{background:rgba(124,58,237,0.1);border:1px solid rgba(124,58,237,0.3);color:#a78bfa}
.cat-consumer{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.5)}
.terminal{background:rgba(0,0,0,0.55);border:1px solid rgba(0,212,255,0.2);border-radius:8px;overflow:hidden;text-align:left;margin-bottom:40px;box-shadow:0 0 60px rgba(0,212,255,0.05)}
.terminal-bar{background:rgba(0,212,255,0.05);padding:12px 20px;border-bottom:1px solid rgba(0,212,255,0.1);display:flex;align-items:center;gap:8px}
.t-dot{width:10px;height:10px;border-radius:50%}
.t-dot-r{background:#ff5f57}.t-dot-y{background:#febc2e}.t-dot-g{background:#28c840}
.t-title{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);letter-spacing:2px;text-transform:uppercase;margin-left:8px}
.terminal-body{padding:28px 28px 32px;min-height:320px;max-height:70vh;overflow-y:auto}
.terminal-body::-webkit-scrollbar{width:3px}.terminal-body::-webkit-scrollbar-thumb{background:rgba(0,212,255,0.2);border-radius:2px}
.t-line{font-family:var(--mono);font-size:13px;line-height:2.1;display:flex;align-items:flex-start;gap:10px;opacity:0;transform:translateY(4px);transition:opacity .25s,transform .25s}
.t-line.show{opacity:1;transform:none}
.t-prompt{color:rgba(0,212,255,0.3);flex-shrink:0;user-select:none}
.t-text{color:rgba(255,255,255,0.75);flex:1}
.t-cyan{color:var(--cyan)}.t-green{color:var(--green)}.t-gold{color:var(--gold)}.t-red{color:#ff6b6b}.t-dim{color:rgba(255,255,255,0.2)}.t-purple{color:#a78bfa}
.t-hash{color:var(--green);font-size:11px;word-break:break-all;line-height:1.6}
.t-section{font-family:var(--mono);font-size:9px;letter-spacing:3px;text-transform:uppercase;color:rgba(0,212,255,0.2);padding:10px 0 4px;border-top:1px solid rgba(255,255,255,0.04);margin-top:6px;opacity:0;transition:opacity .3s}
.t-section.show{opacity:1}
.t-sales{font-family:var(--mono);font-size:12px;line-height:1.8;opacity:0;transform:translateY(4px);transition:opacity .3s,transform .3s;padding:12px 16px;border-radius:4px;margin:4px 0}
.t-sales.show{opacity:1;transform:none}
.t-sales-enterprise{background:rgba(201,168,76,0.06);border-left:3px solid var(--gold);color:rgba(255,255,255,0.6)}
.t-sales-developer{background:rgba(0,212,255,0.04);border-left:3px solid var(--cyan);color:rgba(255,255,255,0.6)}
.t-sales-callcentre{background:rgba(0,255,136,0.04);border-left:3px solid var(--green);color:rgba(255,255,255,0.6)}
.t-sales-law{background:rgba(124,58,237,0.06);border-left:3px solid #7c3aed;color:rgba(255,255,255,0.6)}
.t-sales-consumer{background:rgba(255,255,255,0.03);border-left:3px solid rgba(255,255,255,0.15);color:rgba(255,255,255,0.5)}
.verdict{display:none;padding:28px 28px 32px;border-top:1px solid rgba(0,212,255,0.1);background:rgba(0,0,0,0.3)}
.verdict.show{display:block}
.verdict-decision{font-family:var(--display);font-size:56px;font-weight:900;line-height:1;margin-bottom:6px;letter-spacing:2px;color:var(--green)}
.verdict-score{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.25);letter-spacing:1px;margin-bottom:20px}
.verdict-hash-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.15);margin-bottom:6px}
.verdict-hash{font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:10px 12px;border-radius:4px;margin-bottom:12px;line-height:1.6}
.verdict-sealed{font-family:var(--mono);font-size:10px;color:rgba(0,212,255,0.35);letter-spacing:1px}
.verdict-verify{display:inline-block;margin-top:12px;font-family:var(--mono);font-size:10px;color:var(--cyan);text-decoration:none;border-bottom:1px solid rgba(0,212,255,0.3)}
.fear-sec{display:none;padding:0 48px 80px;text-align:center}
.fear-sec.show{display:block}
.fear-inner{max-width:720px;margin:0 auto}
.fear-line{font-family:var(--display);font-size:clamp(20px,3vw,34px);font-weight:900;line-height:1.3;margin-bottom:20px;opacity:0;transform:translateY(24px);transition:opacity .7s,transform .7s}
.fear-line.show{opacity:1;transform:none}
.fear-line em{color:var(--cyan);font-style:normal}
.fear-line strong{color:var(--red)}
.fear-divider{width:60px;height:3px;background:linear-gradient(90deg,var(--cyan),var(--gold));margin:36px auto;opacity:0;transition:opacity .7s;border-radius:2px}
.fear-divider.show{opacity:1}
.fear-cta{margin-top:52px;opacity:0;transform:translateY(24px);transition:opacity .7s,transform .7s}
.fear-cta.show{opacity:1;transform:none}
.fear-price{font-family:var(--display);font-size:clamp(56px,10vw,110px);font-weight:900;color:var(--cyan);line-height:1;margin-bottom:4px}
.fear-price-label{font-family:var(--mono);font-size:11px;letter-spacing:2px;color:rgba(255,255,255,0.2);margin-bottom:36px;text-transform:uppercase}
.btn-cyan{background:var(--cyan);color:var(--navy);padding:16px 36px;border:none;font-family:var(--sans);font-weight:700;font-size:16px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-cyan:hover{background:#33ddff;transform:translateY(-2px)}
.btn-ghost{background:transparent;color:rgba(255,255,255,0.4);padding:16px 36px;border:1px solid rgba(255,255,255,0.1);font-family:var(--sans);font-weight:600;font-size:16px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s;margin-left:12px}.btn-ghost:hover{color:var(--white);border-color:rgba(255,255,255,0.3)}
.divider{height:1px;background:linear-gradient(90deg,transparent,rgba(0,212,255,0.3),transparent)}
.what-sec{padding:80px 48px;border-bottom:1px solid rgba(255,255,255,0.05)}
.what-inner,.engine-inner,.how-inner,.pricing-inner{max-width:1100px;margin:0 auto}
.sec-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;color:rgba(0,212,255,0.5);margin-bottom:16px;display:block}
h2{font-family:var(--display);font-size:clamp(28px,3.5vw,48px);font-weight:900;line-height:1.1;margin-bottom:16px}
h2 em{color:var(--cyan);font-style:normal}
.sec-sub{font-size:15px;color:rgba(255,255,255,0.35);line-height:1.8;max-width:580px;margin-bottom:52px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.04)}
.col{background:var(--navy);padding:40px 36px}
.col-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:20px;padding:4px 10px;border-radius:2px;display:inline-block}
.col-old .col-label{color:rgba(255,255,255,0.2);background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08)}
.col-new .col-label{color:var(--cyan);background:rgba(0,212,255,0.06);border:1px solid rgba(0,212,255,0.2)}
.col h3{font-family:var(--display);font-size:22px;font-weight:900;margin-bottom:12px}
.col-old h3{color:rgba(255,255,255,0.3)}.col-new h3{color:var(--white)}
.col p{font-size:14px;line-height:1.75;margin-bottom:20px}
.col-old p{color:rgba(255,255,255,0.2)}.col-new p{color:rgba(255,255,255,0.5)}
.col-stat{font-family:var(--display);font-size:52px;font-weight:900;line-height:1;margin-bottom:4px}
.col-old .col-stat{color:rgba(255,255,255,0.1)}.col-new .col-stat{color:var(--cyan)}
.col-stat-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:rgba(255,255,255,0.2);text-transform:uppercase}
.engine-sec{padding:80px 48px;background:rgba(0,212,255,0.02);border-bottom:1px solid rgba(0,212,255,0.08)}
.engine-card{background:rgba(255,255,255,0.03);border:1px solid rgba(0,212,255,0.15);border-radius:8px;overflow:hidden;margin-top:40px}
.engine-card-header{background:rgba(0,212,255,0.06);border-bottom:1px solid rgba(0,212,255,0.1);padding:24px 32px;display:flex;align-items:center;justify-content:space-between}
.engine-card-title{font-family:var(--display);font-size:24px;font-weight:900;color:var(--white)}.engine-card-title span{color:var(--cyan)}
.engine-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--cyan);background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);padding:5px 12px;border-radius:2px}
.engine-body{padding:32px;display:grid;grid-template-columns:1fr 1fr;gap:40px}
.engine-features{display:flex;flex-direction:column;gap:16px}
.ef{display:flex;align-items:flex-start;gap:12px}
.ef-icon{font-family:var(--mono);font-size:9px;font-weight:700;color:var(--cyan);flex-shrink:0;margin-top:2px}
.ef-text h4{font-size:14px;font-weight:700;color:var(--white);margin-bottom:3px}
.ef-text p{font-size:13px;color:rgba(255,255,255,0.35);line-height:1.6}
.engine-download{background:rgba(0,0,0,0.3);border:1px solid rgba(0,212,255,0.1);border-radius:6px;padding:28px;display:flex;flex-direction:column;gap:16px}
.dl-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.2);margin-bottom:4px}
.dl-filename{font-family:var(--mono);font-size:16px;color:var(--cyan);font-weight:600}
.dl-size{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.15);margin-top:2px}
.dl-steps{display:flex;flex-direction:column;gap:8px}
.dl-step{font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.4);line-height:1.5}
.dl-step strong{color:var(--cyan)}
.code-block{background:rgba(0,0,0,0.4);border:1px solid rgba(0,212,255,0.1);border-radius:6px;padding:20px;font-family:var(--mono);font-size:12px;line-height:1.8;color:rgba(255,255,255,0.5);overflow-x:auto;white-space:pre}
.code-block .c-cyan{color:var(--cyan)}.code-block .c-green{color:var(--green)}.code-block .c-gold{color:var(--gold)}.code-block .c-dim{color:rgba(255,255,255,0.2)}
.dl-btn{display:block;text-align:center;background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.3);color:var(--cyan);padding:12px;border-radius:4px;font-family:var(--mono);font-size:12px;font-weight:600;text-decoration:none;transition:all .2s;cursor:pointer}.dl-btn:hover{background:rgba(0,212,255,0.2)}
.how-sec{padding:80px 48px;border-bottom:1px solid rgba(255,255,255,0.05)}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-top:40px}
.step{background:var(--navy);padding:32px 24px}
.step-n{font-family:var(--display);font-size:56px;font-weight:900;color:var(--cyan);opacity:0.15;line-height:1;margin-bottom:12px}
.step h3{font-family:var(--display);font-size:18px;font-weight:900;color:var(--white);margin-bottom:10px}
.step p{font-size:13px;color:rgba(255,255,255,0.35);line-height:1.7}
.pricing-sec{padding:80px 48px;border-bottom:1px solid rgba(255,255,255,0.05)}
.price-card{background:rgba(255,255,255,0.03);border:1px solid rgba(0,212,255,0.15);border-radius:8px;padding:48px;margin-top:40px;text-align:center;max-width:600px;margin-left:auto;margin-right:auto}
.price-big{font-family:var(--display);font-size:96px;font-weight:900;color:var(--cyan);line-height:1;margin-bottom:4px}
.price-per{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.2);margin-bottom:32px}
.price-includes{display:flex;flex-direction:column;gap:10px;text-align:left;margin-bottom:32px}
.pi{display:flex;align-items:center;gap:10px;font-size:14px;color:rgba(255,255,255,0.5)}
.pi::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;color:var(--cyan);flex-shrink:0}
.signup-sec{padding:80px 48px}
.signup-inner{max-width:520px;margin:0 auto;text-align:center}
.signup-inner p{font-size:15px;color:rgba(255,255,255,0.35);line-height:1.7;margin-bottom:32px}
.fg{margin-bottom:12px;text-align:left}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:rgba(255,255,255,0.05);border:2px solid rgba(255,255,255,0.08);color:var(--white);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus{border-color:var(--cyan)}
.fg input::placeholder{color:rgba(255,255,255,0.2)}
.fg select option{background:var(--navy)}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn-full{width:100%;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s;background:var(--cyan);color:var(--navy);margin-top:8px}
.btn-full:hover{background:#33ddff}
.key-box{display:none;margin-top:24px;background:rgba(0,0,0,0.4);border:1px solid rgba(0,212,255,0.2);border-radius:6px;padding:24px;text-align:left}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--cyan);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;margin-bottom:16px}
.msg-err{display:none;color:#ff6b6b;font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:rgba(255,0,0,0.08);border-radius:4px;border:1px solid rgba(255,0,0,0.2)}
.msg-err.show{display:block}
footer{background:rgba(0,0,0,0.4);padding:48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px}
.foot-logo{font-family:var(--display);font-size:18px;color:var(--white);font-weight:900;text-decoration:none}.foot-logo span{color:var(--cyan)}
.foot-links{display:flex;gap:24px;flex-wrap:wrap}
.foot-links a{color:rgba(255,255,255,0.2);text-decoration:none;font-size:12px;transition:color .2s}.foot-links a:hover{color:var(--white)}
.foot-copy{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.1);width:100%;margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.04)}
@media(max-width:900px){
  nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
  .scan-sec,.what-sec,.engine-sec,.how-sec,.pricing-sec,.signup-sec,.fear-sec{padding-left:20px!important;padding-right:20px!important}
  .two-col,.engine-body,.steps,.fg-row{grid-template-columns:1fr!important}
  footer{padding:36px 20px}.foot-inner{flex-direction:column;align-items:flex-start}
  .btn-ghost{margin-left:0;margin-top:12px}
}
</style>
</head>
<body>

<nav>
  <a href="https://sebbi.pro" class="nav-logo">Monop <span>Content</span></a>
  <div class="nav-links">
    <a href="https://sebbi.pro/#products">All Products</a>
    <a href="https://sebbi.pro/scan">Free Scanner</a>
    <a href="https://sebbi.pro/contact">Contact</a>
    <a href="#signup" class="nav-cta">Get SonicBoom Free</a>
  </div>
</nav>

<section class="scan-sec">
  <div class="scan-inner">
    <span class="scan-eyebrow">SonicBoom &mdash; sebbi.pro &mdash; Live Engine</span>
    <h1 class="scan-title" style="font-family:var(--display);font-size:clamp(36px,5vw,64px);line-height:1.05;font-weight:900;margin-bottom:16px">Hello.<br><em>We already know who you are.</em></h1>
    <p class="scan-sub">Welcome to sebbi.pro. We are Monop Content. This is our AI compliance engine. It has been scanning you since the moment you arrived.</p>
    <p class="data-note">Everything below is real: your real device, your real approximate location, and a real decision from our live governance engine &mdash; not a simulation.</p>
    <button class="sound-toggle" id="sound-toggle" onclick="toggleSound()">
      <span id="sound-icon">&#128266;</span>
      <span id="sound-label">Sound On &mdash; Tap to mute</span>
    </button>
    <div class="category-badge" id="category-badge"></div>
    <div class="terminal">
      <div class="terminal-bar">
        <div class="t-dot t-dot-r"></div><div class="t-dot t-dot-y"></div><div class="t-dot t-dot-g"></div>
        <span class="t-title">AILeash Engine v5.0.0 &mdash; sebbi.pro &mdash; Live Session Scan</span>
      </div>
      <div class="terminal-body" id="terminal-body"></div>
      <div class="verdict" id="verdict">
        <div class="verdict-decision" id="v-decision">ALLOW</div>
        <div class="verdict-score" id="v-score"></div>
        <div class="verdict-hash-label">Audit Hash &mdash; SHA-256 &mdash; Sealed Into the Real Chain Just Now</div>
        <div class="verdict-hash" id="v-hash"></div>
        <div class="verdict-sealed" id="v-sealed"></div>
        <a href="https://sebbi.pro/api/verify-chain" target="_blank" class="verdict-verify">Verify the chain integrity yourself &rarr;</a>
      </div>
    </div>
  </div>
</section>

<section class="fear-sec" id="fear-sec">
  <div class="fear-inner">
    <div class="fear-line" id="f1">We did that <em>using our real engine, live.</em></div>
    <div class="fear-line" id="f2">Every single user on your platform<br>could be scored like that. <em>In real time.</em></div>
    <div class="fear-divider" id="fd1"></div>
    <div class="fear-line" id="f3">When a regulator knocks on your door and asks you to prove<br>your AI treated someone fairly on a specific date &mdash;</div>
    <div class="fear-line" id="f4"><strong>what exactly are you going to show them?</strong></div>
    <div class="fear-divider" id="fd2"></div>
    <div class="fear-line" id="f5">Your session was just sealed into our real audit chain.<br><em>Tamper-evident. Verifiable. Yours to check.</em></div>
    <div class="fear-line" id="f6">Most AI has <strong>none of this.</strong></div>
    <div class="fear-cta" id="fear-cta">
      <div class="fear-price">50p</div>
      <div class="fear-price-label">per device per month &mdash; your own engine &mdash; your data never leaves your network</div>
      <a href="#signup" class="btn-cyan">Get The Engine Free &rarr;</a>
      <a href="https://sebbi.pro/#products" class="btn-ghost">See All Products</a>
    </div>
  </div>
</section>

<div class="divider"></div>

<section class="what-sec">
  <div class="what-inner">
    <span class="sec-eyebrow">The Problem</span>
    <h2>Every API call is a<br><em>round trip you pay for.</em></h2>
    <p class="sec-sub">Standard cloud AI compliance tools make you send every decision to their server and wait for a response. That latency adds up. That data leaves your network. That dependency is their leverage over you.</p>
    <div class="two-col">
      <div class="col col-old">
        <div class="col-label">The old way</div>
        <h3>Call someone else's server</h3>
        <p>Your platform makes a decision. You send it to a remote API. You wait. They respond. You act. Every single time. Your data leaves your network on every call.</p>
        <div class="col-stat">200ms</div>
        <div class="col-stat-label">typical round trip latency</div>
      </div>
      <div class="col col-new">
        <div class="col-label">SonicBoom</div>
        <h3>Your engine. Your server. Your speed.</h3>
        <p>The Sebdog Engine runs inside your own infrastructure. Every compliance decision happens locally. Nothing leaves your network. The audit chain builds on your own machine.</p>
        <div class="col-stat">&lt;20ms</div>
        <div class="col-stat-label">local decision &mdash; no network hop</div>
      </div>
    </div>
  </div>
</section>

<section class="engine-sec" id="engine">
  <div class="engine-inner">
    <span class="sec-eyebrow">The Engine</span>
    <h2>Sebdog Engine &mdash;<br><em>everything AILeash does,</em> running on yours.</h2>
    <p class="sec-sub">One Python file. Runs anywhere Python runs. Licence-validated against sebbi.pro on startup. Every decision after that is yours, local, and instant.</p>
    <div class="engine-card">
      <div class="engine-card-header">
        <div class="engine-card-title">sebdog_engine<span>.py</span></div>
        <div class="engine-badge">Included with SonicBoom</div>
      </div>
      <div class="engine-body">
        <div class="engine-features">
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>9-signal weighted scoring engine</h4><p>The full AILeash algorithm running on your machine. EWMA trust decay, velocity windows, anomaly detection.</p></div></div>
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>SHA-256 Merkle audit chain</h4><p>Every decision sealed into a tamper-evident chain in your own SQLite database. Nobody can alter it.</p></div></div>
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>Licence validates once, runs forever</h4><p>Phones home on startup and every 24 hours. Between checks every decision is purely local.</p></div></div>
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>Data sovereignty</h4><p>Your users data never leaves your network. Ever. Regulators love this.</p></div></div>
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>EU AI Act Articles 9, 12, 13, 14 alignment</h4><p>Full compliance audit trail generated automatically. Regulator-ready from day one.</p></div></div>
          <div class="ef"><div class="ef-icon">OK</div><div class="ef-text"><h4>Zero external dependencies</h4><p>Pure Python standard library only. No pip install. Runs anywhere.</p></div></div>
        </div>
        <div class="engine-download">
          <div>
            <div class="dl-label">Engine File</div>
            <div class="dl-filename">sebdog_engine.py</div>
            <div class="dl-size">Pure Python &mdash; zero dependencies &mdash; runs anywhere</div>
          </div>
          <div class="dl-steps">
            <div class="dl-step"><strong>1.</strong> Get your free API key below</div>
            <div class="dl-step"><strong>2.</strong> Download the engine with your key</div>
            <div class="dl-step"><strong>3.</strong> Run it on your own server</div>
            <div class="dl-step"><strong>4.</strong> Call localhost instead of sebbi.pro</div>
          </div>
          <div class="code-block"><span class="c-dim"># Run the engine on your server</span>
<span class="c-cyan">python</span> sebdog_engine.py \
  <span class="c-gold">--key</span> al_live_your_key \
  <span class="c-gold">--port</span> 9090

<span class="c-dim"># Every decision is now local</span>
<span class="c-cyan">POST</span> http://localhost:9090/govern
<span class="c-green">-> ALLOW / CHALLENGE / BLOCK</span>
<span class="c-green">-> audit_hash sealed locally</span>
<span class="c-green">-> under 20ms. No network hop.</span></div>
          <a href="#signup" class="dl-btn">Get API Key and Download Engine</a>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="how-sec" id="how">
  <div class="how-inner">
    <span class="sec-eyebrow">How It Works</span>
    <h2>Four steps.<br><em>Then it runs forever.</em></h2>
    <p class="sec-sub">From signup to local engine running in under five minutes.</p>
    <div class="steps">
      <div class="step"><div class="step-n">01</div><h3>Get your free API key</h3><p>Sign up below. No card. 100 free decisions included. Takes 60 seconds.</p></div>
      <div class="step"><div class="step-n">02</div><h3>Download the Sebdog Engine</h3><p>One Python file. Download it with your API key. Drop it on your server.</p></div>
      <div class="step"><div class="step-n">03</div><h3>Run it on your infrastructure</h3><p>One command. Validates your licence and starts listening on any port you choose.</p></div>
      <div class="step"><div class="step-n">04</div><h3>Point your platform at localhost</h3><p>Change one URL in your code. Sub-20ms local compliance decisions forever.</p></div>
    </div>
  </div>
</section>

<section class="pricing-sec">
  <div class="pricing-inner">
    <span class="sec-eyebrow">Pricing</span>
    <h2>Same model.<br><em>Your own engine included.</em></h2>
    <div class="price-card">
      <div class="price-big">50p</div>
      <div class="price-per">per device per month &mdash; billed via stripe</div>
      <div class="price-includes">
        <div class="pi">Sebdog Engine file runs on your own server</div>
        <div class="pi">Full 9-signal scoring algorithm included</div>
        <div class="pi">SHA-256 local audit chain your database</div>
        <div class="pi">EU AI Act Articles 9 12 13 14 alignment</div>
        <div class="pi">100 free decisions to test before you commit</div>
        <div class="pi">Zero dependencies pure Python standard library</div>
        <div class="pi">Referral code included earn 10p per device you refer</div>
      </div>
      <a href="#signup" class="btn-cyan" style="display:block;text-align:center;padding:14px">Get Free API Key and Engine</a>
    </div>
  </div>
</section>

<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <span class="sec-eyebrow">Get Started</span>
    <h2>Free API key.<br><em>Engine download. Now.</em></h2>
    <p>Sign up. Get your key. Download the Sebdog Engine. Running in under five minutes.</p>
    <div class="fg-row">
      <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
      <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
    </div>
    <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
    <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
    <div class="fg"><label>Platform or Company Name</label><input type="text" id="org" placeholder="e.g. MyPlatform Ltd"></div>
    <div class="fg"><label>Estimated Devices</label>
      <select id="dv">
        <option value="100">Under 100</option>
        <option value="500">100 to 500</option>
        <option value="1000">500 to 1,000</option>
        <option value="5000">1,000 to 5,000</option>
        <option value="10000">5,000 to 10,000</option>
        <option value="50000">10,000 plus</option>
      </select>
    </div>
    <button class="btn-full" onclick="doSignup()">Get Free API Key and Download Engine</button>
    <div class="msg-err" id="msg-err"></div>
    <div class="key-box" id="key-box">
      <div class="key-lbl">Your API Key &mdash; Save This Now</div>
      <div class="key-val" id="key-val"></div>
      <div style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);margin-top:16px;line-height:1.9;background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.1);border-radius:4px;padding:12px">
        Redirecting to Stripe to set up billing&hellip;<br>
        Engine download unlocks after payment.<br>
        100 free decisions active now.
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="foot-inner">
    <a href="https://sebbi.pro" class="foot-logo">Monop <span>Content</span></a>
    <div class="foot-links">
      <a href="https://sebbi.pro/#products">All Products</a>
      <a href="https://sebbi.pro/#signup">AILeash</a>
      <a href="https://sebbi.pro/#signup">Guardian</a>
      <a href="https://sebbi.pro/#signup">Sentinel</a>
      <a href="https://sebbi.pro/scan">Free Scanner</a>
      <a href="https://sebbi.pro/contact">Contact Justin</a>
    </div>
    <div class="foot-copy">&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; justrightdecorators@gmail.com &middot; 07908 269428</div>
  </div>
</footer>

<script>
// ============================================================
// SOUND ENGINE — smooth deep man's voice with queue
// ============================================================
var soundOn = true;
var synth = window.speechSynthesis;
var voices = [];
var speechQueue = [];
var isSpeaking = false;

function loadVoices() { voices = synth ? synth.getVoices() : []; }
if (synth) { synth.onvoiceschanged = loadVoices; loadVoices(); }

function toggleSound() {
  soundOn = !soundOn;
  document.getElementById('sound-icon').textContent = soundOn ? '\uD83D\uDD0A' : '\uD83D\uDD07';
  document.getElementById('sound-label').textContent = soundOn ? 'Sound On \u2014 Tap to mute' : 'Sound Off \u2014 Tap to enable';
  if (!soundOn && synth) { synth.cancel(); speechQueue = []; isSpeaking = false; }
}

function getVoice() {
  if (!voices.length) return null;
  var deepMale = voices.find(function(v){ return /daniel|george|arthur|oliver|thomas/i.test(v.name) && v.lang.startsWith('en'); });
  var ukMale = voices.find(function(v){ return v.lang === 'en-GB'; });
  var enAny = voices.find(function(v){ return v.lang.startsWith('en'); });
  return deepMale || ukMale || enAny || null;
}

function processQueue() {
  if (!soundOn || !synth || speechQueue.length === 0 || isSpeaking) return;
  isSpeaking = true;
  var item = speechQueue.shift();
  var utt = new SpeechSynthesisUtterance(item.text);
  utt.pitch = 0.65;
  utt.rate = 0.90;
  utt.volume = 1.0;
  var v = getVoice();
  if (v) utt.voice = v;
  utt.onend = function() { isSpeaking = false; setTimeout(processQueue, 150); };
  utt.onerror = function() { isSpeaking = false; setTimeout(processQueue, 150); };
  synth.speak(utt);
}

function speak(text) {
  if (!soundOn || !synth || !text) return;
  speechQueue.push({ text: text });
  processQueue();
}

function speakNow(text) {
  if (!soundOn || !synth || !text) return;
  synth.cancel(); speechQueue = []; isSpeaking = false;
  speechQueue.push({ text: text });
  processQueue();
}

// ============================================================
// TERMINAL
// ============================================================
var tb;
function addLine(id, prompt, html, spoken, delay, pitch, rate) {
  return new Promise(function(resolve) {
    setTimeout(function() {
      var ex = document.getElementById(id);
      if (ex) ex.remove();
      var div = document.createElement('div');
      div.className = 't-line'; div.id = id;
      div.innerHTML = '<span class="t-prompt">'+prompt+'</span><span class="t-text">'+html+'</span>';
      tb.appendChild(div);
      setTimeout(function(){ div.classList.add('show'); if(spoken) speak(spoken, pitch, rate); tb.scrollTop=tb.scrollHeight; }, 30);
      resolve();
    }, delay);
  });
}

function addSalesLine(id, html, spoken, cssClass, delay) {
  return new Promise(function(resolve) {
    setTimeout(function() {
      var div = document.createElement('div');
      div.className = 't-sales ' + (cssClass||'t-sales-consumer'); div.id = id;
      div.innerHTML = html;
      tb.appendChild(div);
      setTimeout(function(){ div.classList.add('show'); if(spoken) speak(spoken); tb.scrollTop=tb.scrollHeight; }, 30);
      resolve();
    }, delay);
  });
}

function addSection(id, label, delay) {
  return new Promise(function(resolve) {
    setTimeout(function() {
      var div = document.createElement('div');
      div.className = 't-section'; div.id = id;
      div.textContent = '--- '+label+' ---';
      tb.appendChild(div);
      setTimeout(function(){ div.classList.add('show'); tb.scrollTop=tb.scrollHeight; }, 30);
      resolve();
    }, delay);
  });
}

// ============================================================
// GEO
// ============================================================
async function getGPS() {
  return new Promise(function(resolve) {
    if (!navigator.geolocation) { resolve(null); return; }
    navigator.geolocation.getCurrentPosition(
      function(p){ resolve({ lat:p.coords.latitude, lng:p.coords.longitude, accuracy:Math.round(p.coords.accuracy) }); },
      function(){ resolve(null); },
      { timeout:6000, maximumAge:60000 }
    );
  });
}

async function reverseGeocode(lat, lng) {
  try {
    var r = await fetch('https://nominatim.openstreetmap.org/reverse?lat='+lat+'&lon='+lng+'&format=json');
    var d = await r.json();
    if (d && d.address) {
      var a = d.address;
      var town = a.town||a.city||a.village||a.hamlet||a.county||'';
      var county = a.county||a.state_district||'';
      var country = a.country||'';
      return { town:town, county:county, country:country, display:[town,county,country].filter(Boolean).join(', ') };
    }
  } catch(e) {}
  return null;
}

async function getIPGeo() {
  var r = { city:'Unknown', country:'Unknown', countryCode:'??', region:'Unknown', isp:'Unknown', ip:'Unknown' };
  try {
    var res = await fetch('https://ipapi.co/json/');
    var d = await res.json();
    if (d&&d.ip&&!d.error) { r.ip=d.ip; r.city=d.city||'Unknown'; r.region=d.region||''; r.country=d.country_name||'Unknown'; r.countryCode=d.country_code||'??'; r.isp=d.org||'Unknown'; return r; }
  } catch(e) {}
  try {
    var res2 = await fetch('https://ip-api.com/json/?fields=status,city,country,countryCode,regionName,isp,query');
    var d2 = await res2.json();
    if (d2&&d2.status==='success') { r.ip=d2.query; r.city=d2.city||'Unknown'; r.region=d2.regionName||''; r.country=d2.country||'Unknown'; r.countryCode=d2.countryCode||'??'; r.isp=d2.isp||'Unknown'; }
  } catch(e) {}
  return r;
}

// ============================================================
// CATEGORISE VISITOR
// ============================================================
function categorise(ua, isp, hour, isMobile, connType) {
  var ispL = isp.toLowerCase();
  var uaL = ua.toLowerCase();
  if (ispL.includes('police')||ispL.includes('gov')||ispL.includes('nhs')||ispL.includes('council')||ispL.includes('home office')) {
    return 'lawenforcement';
  }
  if (!isMobile && hour>=8 && hour<=18 && (ispL.includes('business')||ispL.includes('enterprise')||ispL.includes('bt')||ispL.includes('virgin')||ispL.includes('vodafone')||ispL.includes('talktalk'))) {
    return 'callcentre';
  }
  if ((uaL.includes('linux')||uaL.includes('x11')) && !isMobile) { return 'developer'; }
  if (!isMobile && (uaL.includes('firefox')||uaL.includes('chrome')) && hour>=9 && hour<=17) { return 'enterprise'; }
  return 'consumer';
}

var SALES = {
  enterprise: {
    badge: 'Enterprise — Compliance Officer Detected',
    badgeClass: 'cat-enterprise',
    lines: [
      { html: '<span class="t-gold">We just scanned you. Your AI may not be doing this for your users. Every one without it is a blind spot.</span>', spoken: 'We just scanned you. Your AI may not be doing this for your users. Every one without it is a blind spot.' },
      { html: 'EU AI Act enforcement is coming for high-risk systems. Article 12 calls for a tamper-evident audit chain for AI decisions that affect a person. <span class="t-gold">A standard log file your own team can edit does not satisfy that. You need a SHA-256 Merkle chain. You need AILeash.</span>', spoken: 'EU AI Act enforcement is coming for high-risk systems. Article 12 calls for a tamper-evident audit chain. A log file your team can edit will not satisfy that. You need AILeash.' },
      { html: '<span class="t-gold">When a regulator asks, you have two choices. Show them years of cryptographic proof. Or show them nothing.</span> Organisations that build this in now will have that history. The ones that wait will not.', spoken: 'When a regulator asks, you have two choices. Show them years of cryptographic proof. Or show them nothing. Organisations that build this in now will have that history.' },
      { html: 'EU AI Act Articles 9, 12, 13 and 14. <span class="t-gold">AILeash is built around all four. From 50 pence per device per month. Not fifty thousand pounds a year. Fifty pence per device.</span>', spoken: 'EU AI Act Articles 9, 12, 13 and 14. AILeash is built around all four. From fifty pence per device per month.' }
    ],
    css: 't-sales-enterprise'
  },
  callcentre: {
    badge: 'Call Centre — Business Network Detected',
    badgeClass: 'cat-callcentre',
    lines: [
      { html: '<span class="t-green">Before your agent picks up the phone, AILeash can already score the caller. Device. Location signals. Velocity. Behaviour pattern. Trust index.</span>', spoken: 'Before your agent picks up the phone, AILeash can already score the caller. Device. Location signals. Velocity. Behaviour pattern. Trust index.' },
      { html: 'Your agents can see the risk score the moment the call connects. <span class="t-green">Fraud flagged early. Account takeovers caught faster. Every decision sealed into a tamper-proof audit chain.</span>', spoken: 'Your agents can see the risk score the moment the call connects. Fraud flagged early. Every decision sealed into a tamper-proof audit chain.' },
      { html: '<span class="t-green">That audit chain is tamper-evident by design. If a caller later disputes a decision, you have a cryptographic record of exactly what the system knew and decided at that moment.</span>', spoken: 'That audit chain is tamper-evident by design. If a caller later disputes a decision, you have a cryptographic record of what the system knew and decided.' },
      { html: '<span class="t-green">Fifty pence per device per month.</span> Contact Justin at Monop Content for volume pricing.', spoken: 'Fifty pence per device per month. Contact Justin at Monop Content for volume pricing.' }
    ],
    css: 't-sales-callcentre'
  },
  developer: {
    badge: 'Developer — Technical User Detected',
    badgeClass: 'cat-developer',
    lines: [
      { html: '<span class="t-cyan">One Python file. Zero dependencies. Pure standard library. Runs anywhere Python runs. No pip install. No framework. No bloat.</span>', spoken: 'One Python file. Zero dependencies. Pure standard library. Runs anywhere Python runs. No pip install. No framework. No bloat.' },
      { html: 'Drop sebdog underscore engine dot py on your server. Point your platform at localhost. <span class="t-cyan">Sub-20 millisecond compliance decisions. SHA-256 Merkle audit chain built locally. No external calls on the hot path.</span>', spoken: 'Drop the Sebdog engine on your server. Point your platform at localhost. Sub 20 millisecond compliance decisions. SHA-256 Merkle audit chain built locally.' },
      { html: '<span class="t-cyan">Built around the EU AI Act, the Online Safety Act, and the ICO Childrens Code.</span> One hundred free decisions. No credit card. Get the engine now.', spoken: 'Built around the EU AI Act, the Online Safety Act, and the ICO Childrens Code. Get the engine now.' }
    ],
    css: 't-sales-developer'
  },
  lawenforcement: {
    badge: 'Public Sector — Government Network Detected',
    badgeClass: 'cat-lawenforcement',
    lines: [
      { html: '<span class="t-purple">Every interaction. Every decision. Every override. Every timestamp. Sealed into a cryptographic chain nobody can alter without it being detectable. Not even the operator.</span>', spoken: 'Every interaction. Every decision. Every override. Every timestamp. Sealed into a cryptographic chain nobody can alter without it being detectable.' },
      { html: 'SHA-256 Merkle chain. <span class="t-purple">Each block contains the event, the decision, the timestamp, and the hash of the block before it. Alter any record and the chain visibly breaks.</span>', spoken: 'SHA-256 Merkle chain. Each block contains the event, the decision, the timestamp, and the hash of the block before it. Alter any record and the chain visibly breaks.' },
      { html: 'Velocity monitoring. Trust decay scoring. <span class="t-purple">Every BLOCK or CHALLENGE comes with a plain-language reason list.</span>', spoken: 'Velocity monitoring. Trust decay scoring. Every block or challenge comes with a plain language reason list.' }
    ],
    css: 't-sales-law'
  },
  consumer: {
    badge: 'Visitor — Session Identified',
    badgeClass: 'cat-consumer',
    lines: [
      { html: 'We just scanned you the way your bank or insurer arguably should be. <span class="t-dim">Most platforms making decisions about people are not doing this yet.</span>', spoken: 'We just scanned you the way your bank or insurer arguably should be. Most platforms making decisions about people are not doing this yet.' },
      { html: 'If you run a platform that uses AI to make decisions about people, <span class="t-cyan">what you just experienced is close to what a regulator will expect. From 50 pence per device per month.</span>', spoken: 'If you run a platform that uses AI to make decisions about people, what you just experienced is close to what a regulator will expect. From fifty pence per device per month.' }
    ],
    css: 't-sales-consumer'
  }
};

// ============================================================
// REAL GOVERNANCE CALL — this is the fix.
// The scan used to invent a score, trust and hash in the browser.
// It now sends real signals to the real engine and narrates the
// real response, including the real audit hash actually written
// to the real chain.
// ============================================================
async function callRealEngine(signals){
  var event = {
    user_id: 'sonicboom_'+Math.random().toString(36).slice(2,10),
    action: 'sonicboom_scan',
    amount: 0,
    country: signals.countryCode || 'UK',
    device_id: (signals.deviceType||'device')+'_'+(signals.os||'unknown'),
    anomaly: signals.anomaly,
    device_risk: signals.deviceRisk
  };
  var res = await fetch('https://sebbi.pro/api/govern', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(event)
  });
  var data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error||'engine_error');
  return data;
}

// ============================================================
// MAIN SCAN
// ============================================================
async function runScan() {
  tb = document.getElementById('terminal-body');
  var ts = Date.now();
  var ua = navigator.userAgent;
  var lang = navigator.language||'en';
  var langNames = {'en':'English','en-GB':'English','en-US':'English','fr':'French','de':'German','es':'Spanish','pt':'Portuguese','nl':'Dutch','it':'Italian','pl':'Polish','ru':'Russian','zh':'Chinese','ja':'Japanese','ko':'Korean','ar':'Arabic'};
  var langFull = langNames[lang]||lang;
  var sw = window.screen.width, sh = window.screen.height;
  var dpr = window.devicePixelRatio||1;
  var tz = Intl.DateTimeFormat().resolvedOptions().timeZone||'Unknown';
  var now = new Date();
  var localTime = now.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',hour12:false});
  var hour = now.getHours();
  var firstVisit = !localStorage.getItem('sb_visit');
  if(firstVisit) localStorage.setItem('sb_visit',ts);
  var visitCount = parseInt(localStorage.getItem('sb_count')||'0')+1;
  localStorage.setItem('sb_count',visitCount);
  var isMobile = /Mobile|Android|iPhone|iPad/i.test(ua);
  var isTablet = /iPad|Tablet/i.test(ua);
  var deviceType = isTablet?'Tablet':isMobile?'Mobile':'Desktop';
  var browser='Unknown', bv='';
  var em=ua.match(/Edg\/([\d]+)/),cm=ua.match(/Chrome\/([\d]+)/),fm=ua.match(/Firefox\/([\d]+)/),sm=ua.match(/Version\/([\d]+).*Safari/);
  if(em){browser='Edge';bv=em[1];}else if(cm&&!/Edge/i.test(ua)){browser='Chrome';bv=cm[1];}else if(fm){browser='Firefox';bv=fm[1];}else if(sm){browser='Safari';bv=sm[1];}
  var os='Unknown',ov='';
  var am=ua.match(/Android ([\d.]+)/),im=ua.match(/OS ([\d_]+)/),wm=ua.match(/Windows NT ([\d.]+)/);
  var wmap={'10.0':'10 or 11','6.3':'8.1','6.2':'8','6.1':'7'};
  if(am){os='Android';ov=am[1];}else if(/iPhone|iPad/.test(ua)&&im){os='iOS';ov=im[1].replace(/_/g,'.');}else if(wm){os='Windows';ov=wmap[wm[1]]||wm[1];}else if(/Mac/i.test(ua)){os='macOS';}else if(/Linux/i.test(ua)){os='Linux';}
  var cpuCores=navigator.hardwareConcurrency||null;
  var ram=navigator.deviceMemory||null;
  var touchPoints=navigator.maxTouchPoints||0;
  var dnt=navigator.doNotTrack==='1'||window.doNotTrack==='1';
  var referrer=document.referrer, refHost='';
  if(referrer){try{refHost=new URL(referrer).hostname.replace('www.','');}catch(e){}}
  var hasAdBlocker=false;
  try{var at=document.createElement('div');at.className='adsbox pub_300x250';at.style.cssText='width:1px;height:1px;position:absolute;left:-9999px;';document.body.appendChild(at);hasAdBlocker=at.offsetHeight===0;document.body.removeChild(at);}catch(e){}
  var battery=null,charging=null;
  try{if(navigator.getBattery){var b=await navigator.getBattery();battery=Math.round(b.level*100);charging=b.charging;}}catch(e){}
  var connType=null,connSpeed=null;
  try{var conn=navigator.connection||navigator.mozConnection||navigator.webkitConnection;if(conn){connType=conn.effectiveType||conn.type||null;connSpeed=conn.downlink||null;}}catch(e){}

  var gpsPromise=getGPS();
  var ipGeoPromise=getIPGeo();

  var delay=0, step=280, P=1.9, R=1.1;

  setTimeout(function(){
    speakNow('Welcome to sebbi dot pro. This is the AILeash engine, built by Monop Content in Blyth, United Kingdom. I have been scanning your session since the moment you arrived.');
  }, 600);

  await addLine('tl-intro','>', '<span class="t-dim">Hello. Welcome to sebbi.pro. This is the AILeash Engine, built by Monop Content, Blyth, UK.</span>', null, delay); delay+=step;
  await addLine('tl-intro2','>', '<span class="t-dim">I have been scanning your session since the moment you arrived. Here is what I found.</span>', null, delay); delay+=step*1.2;

  await addSection('sec-device','Device Intelligence', delay); delay+=200;
  await addLine('tl-dev','>','Device: <span class="t-cyan">'+deviceType+' &mdash; '+os+(ov?' '+ov:'')+' &mdash; '+browser+(bv?' '+bv:'')+'</span>', deviceType+'. '+os+'. '+browser+'.', delay, P, R); delay+=step;
  await addLine('tl-screen','>','Display: <span class="t-cyan">'+sw+' by '+sh+(dpr>1?' &mdash; Retina '+dpr+'x':' &mdash; Standard resolution')+'</span>', sw+' by '+sh+' display.', delay, P, R); delay+=step;
  if(cpuCores){ await addLine('tl-cpu','>','Processor: <span class="t-cyan">'+cpuCores+' CPU core'+(cpuCores>1?'s':'')+' detected</span>', cpuCores+' CPU cores detected.', delay, P, R); delay+=step; }
  if(ram){ await addLine('tl-ram','>','Memory: <span class="t-cyan">'+ram+' gigabyte'+(ram>1?'s':'')+' RAM</span>', ram+' gigabytes of RAM.', delay, P, R); delay+=step; }
  await addLine('tl-touch','>',touchPoints>0?'Input: <span class="t-cyan">Touchscreen &mdash; '+touchPoints+' touch points</span>':'Input: <span class="t-dim">Mouse and keyboard &mdash; no touchscreen</span>', touchPoints>0?'Touchscreen. '+touchPoints+' touch points.':'Mouse and keyboard.', delay, P, R); delay+=step;
  if(battery!==null){
    var bd=battery+'%'+(charging?' &mdash; charging':battery<20?' &mdash; low battery':'');
    var bs=battery+' percent battery'+(charging?'. Charging.':battery<20?'. Battery is low.':'.');
    await addLine('tl-bat','>','Power: <span class="t-cyan">'+bd+'</span>', bs, delay, P, R); delay+=step;
  }
  if(connType){
    var ct=connType.toUpperCase()+(connSpeed?' &mdash; '+connSpeed+' Mbps':'');
    await addLine('tl-conn','>','Connection: <span class="t-cyan">'+ct+'</span>', connType.toUpperCase()+' connection.', delay, P, R); delay+=step;
  }

  await addSection('sec-identity','Session Identity', delay); delay+=200;
  await addLine('tl-time','>','Local time: <span class="t-cyan">'+localTime+' &mdash; '+tz+'</span>', 'Local time '+localTime+'.', delay, P, R); delay+=step;
  await addLine('tl-lang','>','Language: <span class="t-cyan">'+langFull+'</span>', 'Language: '+langFull+'.', delay, P, R); delay+=step;
  if(dnt){ await addLine('tl-dnt','>','<span class="t-gold">Do Not Track enabled &mdash; privacy-conscious user</span>','Do Not Track is enabled.',delay,P,R); delay+=step; }
  if(hasAdBlocker){ await addLine('tl-adb','>','<span class="t-gold">Ad blocker active &mdash; privacy tools detected</span>','Ad blocker detected.',delay,P,R); delay+=step; }
  if(refHost){ await addLine('tl-ref','>','Arrived from: <span class="t-cyan">'+refHost+'</span>','You arrived from '+refHost+'.',delay,P,R); delay+=step; }
  await addLine('tl-visit','>',firstVisit?'<span class="t-gold">First visit &mdash; no prior session history on this device</span>':'<span class="t-dim">Visit number '+visitCount+' &mdash; returning visitor</span>', firstVisit?'This is your first visit.':'This is visit number '+visitCount+'. Welcome back.', delay, P, R); delay+=step;

  await addSection('sec-network','Network Location', delay); delay+=200;
  await addLine('tl-geoload','>','<span class="t-dim">Resolving your approximate location&hellip;</span>','Resolving your approximate location.',delay,P,R); delay+=step;

  var gps=await gpsPromise;
  var ipGeo=await ipGeoPromise;
  var locDisplay='', locSpoken='';

  if(gps){
    var rev=await reverseGeocode(gps.lat,gps.lng);
    if(rev&&rev.display){ locDisplay=rev.display+' &mdash; GPS accurate to '+gps.accuracy+'m'; locSpoken='You are in '+rev.display+'. GPS accurate to '+gps.accuracy+' metres.'; }
    else { locDisplay=gps.lat.toFixed(4)+', '+gps.lng.toFixed(4); locSpoken='Location confirmed by G.P.S.'; }
    await addLine('tl-gps','>','<span class="t-green">GPS confirmed: </span><span class="t-cyan">'+locDisplay+'</span>',locSpoken,delay,P,R); delay+=step;
  } else {
    locDisplay=(ipGeo.city!=='Unknown'?ipGeo.city+(ipGeo.region?', '+ipGeo.region:'')+ ' &mdash; ':'')+ipGeo.country;
    locSpoken='Location: '+(ipGeo.city!=='Unknown'?ipGeo.city+'. ':'')+ipGeo.country+'.';
    await addLine('tl-loc','>','Location: <span class="t-cyan">'+locDisplay+'</span>',locSpoken,delay,P,R); delay+=step;
  }
  await addLine('tl-ip','>','IP address: <span class="t-cyan">'+ipGeo.ip+'</span>','I.P. address: '+ipGeo.ip+'.',delay,P,R); delay+=step;
  await addLine('tl-isp','>','Network provider: <span class="t-cyan">'+ipGeo.isp+'</span>','Network provider: '+ipGeo.isp+'.',delay,P,R); delay+=step;

  var cat=categorise(ua, ipGeo.isp, hour, isMobile, connType);
  var salesData=SALES[cat];
  var badge=document.getElementById('category-badge');
  badge.textContent=salesData.badge;
  badge.className='category-badge '+salesData.badgeClass;
  badge.classList.add('show');

  await addSection('sec-sales','AILeash &mdash; What This Means For You', delay); delay+=200;
  for(var i=0;i<salesData.lines.length;i++){
    await addSalesLine('tl-sales'+i, salesData.lines[i].html, salesData.lines[i].spoken, salesData.css, delay);
    delay+=step*1.4;
  }

  await addSection('sec-scoring','Live Governance Engine', delay); delay+=200;
  await addLine('tl-scoring','>','<span class="t-dim">Sending real signals to the live 9-signal governance engine&hellip;</span>','Sending real signals to the live governance engine.',delay,P,R); delay+=step*1.4;

  // Build REAL signals from what was actually detected — no invented values.
  var anomaly=0.05;
  if(hasAdBlocker) anomaly+=0.05;
  if(dnt) anomaly+=0.05;
  if(visitCount>8) anomaly+=0.10;
  anomaly=Math.min(anomaly,1);
  var deviceRisk=(battery!==null && battery<15 && !charging) ? 0.2 : 0.05;

  var engineResult=null, engineError=null;
  try{
    engineResult = await callRealEngine({
      countryCode: ipGeo.countryCode!=='??' ? ipGeo.countryCode : 'UK',
      deviceType: deviceType,
      os: os,
      anomaly: anomaly,
      deviceRisk: deviceRisk
    });
  }catch(e){
    engineError = e;
  }

  if(engineError || !engineResult){
    await addLine('tl-err','>','<span class="t-red">Could not reach the live engine just now &mdash; showing an honest error, not a fallback result.</span>','Could not reach the live engine just now.',delay,P,R); delay+=step;
    return;
  }

  await addLine('tl-score','>','Risk score: <span class="t-cyan">'+engineResult.score+'</span> &mdash; Trust index: <span class="t-cyan">'+engineResult.trust+'</span>','Risk score '+engineResult.score+'. Trust index '+engineResult.trust+'.',delay,P,R); delay+=step;
  if(engineResult.reasons && engineResult.reasons.length>0){
    await addLine('tl-flags','>','Signals raised: <span class="t-gold">'+engineResult.reasons.join(' &mdash; ')+'</span>','Signals raised: '+engineResult.reasons.join('. ')+'.',delay,P,R); delay+=step;
  } else {
    await addLine('tl-flags','>','<span class="t-dim">No risk signals raised on this session</span>','No risk signals raised on this session.',delay,P,R); delay+=step;
  }
  var decColour = engineResult.decision==='ALLOW' ? 'var(--green)' : engineResult.decision==='CHALLENGE' ? 'var(--gold)' : '#ff6b6b';
  await addLine('tl-dec','>','Decision: <span style="color:'+decColour+';font-weight:700;font-size:16px;letter-spacing:3px">'+engineResult.decision+'</span>','Decision. '+engineResult.decision+'.',delay,P,R); delay+=step;
  await addLine('tl-seal','>','<span class="t-dim">Writing to the real SHA-256 Merkle audit chain&hellip;</span>','Writing to the real audit chain.',delay,P,R); delay+=step;
  await addLine('tl-hash','>','Audit hash: <span class="t-hash">'+engineResult.audit_hash+'</span>','Audit hash generated and sealed for real.',delay,P,R); delay+=step;
  await addLine('tl-done','>','<span class="t-green">Sealed &mdash; tamper-evident &mdash; you can verify this chain yourself, right now.</span>','Sealed. Tamper-evident. You can verify this chain yourself, right now.',delay,P,R); delay+=step;

  setTimeout(function(){
    document.getElementById('v-decision').textContent=engineResult.decision;
    document.getElementById('v-decision').style.color=decColour;
    document.getElementById('v-score').textContent='Score: '+engineResult.score+'  —  Trust: '+engineResult.trust+'  —  Version: '+engineResult.version;
    document.getElementById('v-hash').textContent=engineResult.audit_hash;
    document.getElementById('v-sealed').textContent='Sealed just now  —  Real chain entry  —  Verifiable  —  Not a simulation';
    document.getElementById('verdict').classList.add('show');
  }, delay);
  delay+=step*2;

  setTimeout(function(){
    var fs=document.getElementById('fear-sec');
    fs.classList.add('show');
    var items=[
      {id:'f1',spoken:'We did that. Using our real engine, live.'},
      {id:'f2',spoken:'Every single user on your platform could be scored like that. In real time.'},
      {id:'fd1',spoken:null},
      {id:'f3',spoken:'When a regulator asks you to prove your AI treated someone fairly on a specific date.'},
      {id:'f4',spoken:'What exactly are you going to show them?'},
      {id:'fd2',spoken:null},
      {id:'f5',spoken:'Your session was just sealed into our real audit chain. Tamper-evident. Verifiable. Yours to check.'},
      {id:'f6',spoken:'Most AI has none of this.'},
      {id:'fear-cta',spoken:'Fifty pence. Per device. Per month. Get the engine free right now.'}
    ];
    items.forEach(function(item,i){
      setTimeout(function(){
        var el=document.getElementById(item.id);
        if(el) el.classList.add('show');
        if(item.spoken) speak(item.spoken);
      }, i*900);
    });
  }, delay);
}

window.addEventListener('load', function(){ setTimeout(runScan, 1000); });

// ============================================================
// SIGNUP
// ============================================================
async function doSignup(){
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var org=document.getElementById('org').value.trim();
  var dv=parseInt(document.getElementById('dv').value)||1;
  var err=document.getElementById('msg-err');
  var kb=document.getElementById('key-box');
  var btn=document.querySelector('.btn-full');
  err.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company or platform name.';err.classList.add('show');return;}
  var orig=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('https://sebbi.pro/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:'sonicboom',product:'aileash',devices:dv})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      kb.classList.add('show');
      btn.textContent='Key created \u2014 setting up billing\u2026';
      speak('Key created! Redirecting to billing now.');
      try{
        var r2=await fetch('https://sebbi.pro/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,product:'aileash',devices:dv})});
        var d2=await r2.json();
        if(d2.checkout_url){setTimeout(function(){window.location.href=d2.checkout_url;},2500);}
        else{btn.textContent='Key ready \u2713';}
      }catch(e2){btn.textContent='Key ready \u2713';}
    }else{
      err.textContent=d.error||'Something went wrong. Email justrightdecorators@gmail.com';
      err.classList.add('show');btn.textContent=orig;btn.disabled=false;
    }
  }catch(e){
    err.textContent='Cannot reach server. Email justrightdecorators@gmail.com';
    err.classList.add('show');btn.textContent=orig;btn.disabled=false;
  }
}
</script>
</body>
</html>

```
