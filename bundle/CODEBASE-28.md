# Codebase — part 28 of 32

Contains:
- `reseller.html`
- `risk-policy.html`
- `robots.txt`


## `reseller.html`

812 lines, 66418 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Partner, White-Label &amp; Referral Programmes &mdash; sebbi.pro</title>
<meta name="description" content="Three ways to build a business on AILeash. Partner Programme: deploy it, sell it, keep the margin. White-Label: your brand, your product, our engine. Referral Programme: share your code, earn 10p per device per month forever.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--white:#fff;--green:#00ff88;--red:#cc0000;--cyan:#00d4ff;--purple:#b48cff;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--navy);color:var(--white);font-family:var(--sans);overflow-x:hidden}
html{scroll-behavior:smooth}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(10,15,30,0.97);backdrop-filter:blur(12px);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(201,168,76,0.15)}
.nav-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;text-decoration:none}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:16px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.4);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:9px 18px;font-weight:700!important;border-radius:4px}

/* HERO */
.hero{padding:120px 48px 80px;text-align:center;position:relative;overflow:hidden;border-bottom:4px solid var(--gold)}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 40%,rgba(201,168,76,0.07) 0%,transparent 65%)}
.hero-inner{max-width:900px;margin:0 auto;position:relative;z-index:1}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--gold);margin-bottom:20px;display:block}
h1{font-family:var(--display);font-size:clamp(32px,5vw,60px);line-height:1.05;font-weight:900;margin-bottom:20px}
h1 em{color:var(--gold);font-style:normal}
.hero-sub{font-size:17px;color:rgba(255,255,255,0.4);line-height:1.8;max-width:680px;margin:0 auto 40px}
.hero-sub strong{color:var(--white)}

/* THREE CARDS ON HERO */
.three-options{display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;background:rgba(255,255,255,0.06);max-width:900px;margin:0 auto;border-radius:6px;overflow:hidden}
.option-card{background:var(--navy);padding:32px 24px;text-align:left;text-decoration:none;transition:background .2s;display:block}
.option-card:hover{background:rgba(255,255,255,0.04)}
.option-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-bottom:12px;padding:4px 10px;border-radius:2px;display:inline-block}
.option-badge-gold{color:var(--gold);background:rgba(201,168,76,0.1);border:1px solid rgba(201,168,76,0.2)}
.option-badge-green{color:var(--green);background:rgba(0,255,136,0.06);border:1px solid rgba(0,255,136,0.2)}
.option-badge-purple{color:var(--purple);background:rgba(180,140,255,0.06);border:1px solid rgba(180,140,255,0.2)}
.option-card h3{font-family:var(--display);font-size:20px;font-weight:900;color:var(--white);margin-bottom:8px}
.option-card p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.65;margin-bottom:16px}
.option-earn{font-family:var(--display);font-size:32px;font-weight:900;line-height:1}
.option-earn-gold{color:var(--gold)}.option-earn-green{color:var(--green)}.option-earn-purple{color:var(--purple)}
.option-earn-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase;margin-top:4px}
.option-link{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);letter-spacing:1px;margin-top:12px;display:block}

/* SECTION DIVIDERS */
.sec-divider{height:4px;background:linear-gradient(90deg,var(--gold),rgba(255,255,255,0.05))}
.sec-divider-green{height:4px;background:linear-gradient(90deg,var(--green),rgba(255,255,255,0.05))}
.sec-divider-purple{height:4px;background:linear-gradient(90deg,var(--purple),rgba(255,255,255,0.05))}

/* GENERIC SECTION */
.sec{padding:80px 48px;border-bottom:1px solid rgba(255,255,255,0.05)}
.sec-inner{max-width:1100px;margin:0 auto}
.sec-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;margin-bottom:16px;display:block}
.eyebrow-gold{color:rgba(201,168,76,0.6)}
.eyebrow-green{color:rgba(0,255,136,0.6)}
.eyebrow-purple{color:rgba(180,140,255,0.6)}
h2{font-family:var(--display);font-size:clamp(26px,3.5vw,44px);font-weight:900;line-height:1.1;margin-bottom:16px}
h2 em{color:var(--gold);font-style:normal}
h2 em.green{color:var(--green)}
h2 em.purple{color:var(--purple)}
h3.block-title{font-family:var(--display);font-size:24px;font-weight:900;color:var(--white);margin:48px 0 20px}
.sec-sub{font-size:15px;color:rgba(255,255,255,0.35);line-height:1.8;max-width:640px;margin-bottom:48px}
.sec-sub strong{color:var(--white)}

/* BENEFITS */
.benefits-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px}
.benefit{background:rgba(255,255,255,0.03);border:1px solid rgba(201,168,76,0.1);border-radius:6px;padding:26px}
.benefit h4{font-family:var(--display);font-size:17px;font-weight:900;color:var(--gold);margin-bottom:10px}
.benefit p{font-size:13px;color:rgba(255,255,255,0.45);line-height:1.75}
.benefit p strong{color:var(--white)}

/* EXPLAIN CARDS */
.partner-explain{display:grid;grid-template-columns:1fr 1fr;gap:32px;margin-bottom:24px}
.explain-card{background:rgba(255,255,255,0.03);border:1px solid rgba(201,168,76,0.1);border-radius:6px;padding:28px}
.explain-card h3{font-family:var(--display);font-size:18px;font-weight:900;color:var(--white);margin-bottom:10px}
.explain-card p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.7}

/* PLAYBOOKS */
.playbook{background:rgba(255,255,255,0.03);border:1px solid rgba(201,168,76,0.1);border-radius:8px;padding:32px;margin-bottom:20px}
.playbook-head{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;flex-wrap:wrap;margin-bottom:16px}
.playbook h4{font-family:var(--display);font-size:20px;font-weight:900;color:var(--white)}
.playbook-earn{text-align:right}
.playbook-earn .num{font-family:var(--display);font-size:30px;color:var(--gold);font-weight:900;line-height:1}
.playbook-earn .lbl{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase;margin-top:4px}
.playbook p{font-size:13px;color:rgba(255,255,255,0.45);line-height:1.75;margin-bottom:12px}
.playbook p strong{color:var(--white)}
.playbook .maths{background:rgba(0,0,0,0.3);border:1px solid rgba(201,168,76,0.1);border-radius:4px;padding:16px 20px;font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.5);line-height:2}
.playbook .maths b{color:var(--green);font-weight:600}
.playbook .maths .dim{color:rgba(255,255,255,0.25)}

/* CALCULATOR */
.calc-wrap{background:rgba(255,255,255,0.03);border:2px solid rgba(201,168,76,0.2);border-radius:10px;padding:40px;margin-bottom:48px}
.calc-title{font-family:var(--display);font-size:24px;font-weight:900;color:var(--white);margin-bottom:8px}
.calc-sub{font-size:14px;color:rgba(255,255,255,0.35);margin-bottom:28px}
.calc-inputs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;margin-bottom:28px}
.calc-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}
.calc-input{background:rgba(255,255,255,0.06);border:2px solid rgba(201,168,76,0.2);color:var(--white);padding:12px;font-size:20px;font-family:var(--display);font-weight:700;width:120px;border-radius:6px;outline:none;text-align:center}
.calc-input:focus{border-color:var(--gold)}
.calc-select{background:rgba(255,255,255,0.06);border:2px solid rgba(255,255,255,0.08);color:var(--white);padding:12px 16px;font-size:14px;font-family:var(--sans);width:100%;border-radius:6px;outline:none}
.calc-select option{background:var(--navy)}
.calc-results{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:rgba(255,255,255,0.04);border-radius:6px;overflow:hidden;margin-bottom:20px}
.cr{background:rgba(0,0,0,0.3);padding:20px;text-align:center}
.cr-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}
.cr-amount{font-family:var(--display);font-size:28px;font-weight:900;line-height:1}
.cr-you{color:var(--green)}.cr-we{color:rgba(255,255,255,0.2)}.cr-client{color:var(--gold)}.cr-year{color:var(--cyan)}
.cr-sub{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.15);margin-top:4px}
.calc-pitch{background:rgba(201,168,76,0.04);border:1px solid rgba(201,168,76,0.12);border-radius:4px;padding:16px 20px;font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.45);line-height:1.8;margin-bottom:16px}
.calc-note{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.15);letter-spacing:1px}

/* STEPS */
.steps-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-bottom:48px}
.step{background:var(--navy);padding:28px 20px}
.step-n{font-family:var(--display);font-size:48px;font-weight:900;color:var(--gold);opacity:0.15;line-height:1;margin-bottom:10px}
.step h3{font-family:var(--display);font-size:16px;font-weight:900;color:var(--white);margin-bottom:8px}
.step p{font-size:13px;color:rgba(255,255,255,0.35);line-height:1.65}

/* WHITE LABEL */
.wl-sec{padding:80px 48px;background:rgba(180,140,255,0.02);border-bottom:1px solid rgba(180,140,255,0.08)}
.wl-compare{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.04);border-radius:6px;overflow:hidden;margin-bottom:48px}
.wl-col{background:var(--navy);padding:32px 28px}
.wl-col h4{font-family:var(--display);font-size:18px;font-weight:900;margin-bottom:16px}
.wl-col.theirs h4{color:rgba(255,255,255,0.35)}
.wl-col.yours h4{color:var(--purple)}
.wl-col ul{list-style:none}
.wl-col li{font-size:13px;color:rgba(255,255,255,0.45);line-height:1.7;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.wl-col li:last-child{border-bottom:none}
.wl-col li b{color:var(--white)}
.wl-tiers{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:48px}
.wl-tier{background:rgba(255,255,255,0.03);border:1px solid rgba(180,140,255,0.12);border-radius:8px;padding:28px}
.wl-tier.featured{border:2px solid rgba(180,140,255,0.4);background:rgba(180,140,255,0.04)}
.wl-tier h4{font-family:var(--display);font-size:19px;font-weight:900;color:var(--white);margin-bottom:4px}
.wl-tier .price{font-family:var(--display);font-size:30px;font-weight:900;color:var(--purple);margin:8px 0 2px}
.wl-tier .price-sub{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase;margin-bottom:16px}
.wl-tier ul{list-style:none}
.wl-tier li{font-size:12.5px;color:rgba(255,255,255,0.45);line-height:1.6;padding:6px 0 6px 18px;position:relative}
.wl-tier li::before{content:'\2713';position:absolute;left:0;color:var(--purple);font-weight:700}
.wl-steps{display:grid;grid-template-columns:repeat(4,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-bottom:24px}
.wl-steps .step-n{color:var(--purple)}

/* REFERRAL */
.referral-sec{padding:80px 48px;background:rgba(0,255,136,0.02);border-bottom:1px solid rgba(0,255,136,0.08)}
.referral-inner{max-width:900px;margin:0 auto;text-align:center}
.ref-three{display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;background:rgba(255,255,255,0.04);margin:40px 0}
.ref-card{background:var(--navy);padding:32px 24px;text-align:center}
.ref-icon{font-size:32px;margin-bottom:12px}
.ref-card h3{font-family:var(--display);font-size:18px;font-weight:900;color:var(--white);margin-bottom:8px}
.ref-card p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.65}
.ref-earn{font-family:var(--display);font-size:40px;color:var(--green);font-weight:900;margin-top:12px}
.ref-earn-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase}
.ref-code-sec{background:rgba(255,255,255,0.03);border:2px solid rgba(0,255,136,0.15);border-radius:10px;padding:40px;max-width:700px;margin:0 auto;text-align:center}
.ref-code-title{font-family:var(--display);font-size:24px;font-weight:900;color:var(--white);margin-bottom:8px}
.ref-code-sub{font-size:14px;color:rgba(255,255,255,0.35);margin-bottom:28px;line-height:1.65}
.ref-code-display{font-family:var(--display);font-size:48px;font-weight:900;color:var(--green);letter-spacing:4px;margin-bottom:8px}
.ref-code-hint{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);letter-spacing:1px;margin-bottom:24px}
.ref-share-text{background:rgba(0,255,136,0.04);border:1px solid rgba(0,255,136,0.12);border-radius:6px;padding:20px;font-family:var(--mono);font-size:12px;color:rgba(255,255,255,0.5);line-height:1.9;text-align:left;margin-bottom:20px}
.ref-share-text strong{color:var(--green)}
.ref-link{font-family:var(--mono);font-size:12px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:12px 16px;border-radius:4px;margin-bottom:20px;display:block;text-align:left}
.ref-earnings{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:20px}
.ref-earn-card{background:rgba(0,0,0,0.3);border-radius:4px;padding:16px;text-align:center}
.ref-earn-num{font-family:var(--display);font-size:24px;font-weight:900;color:var(--green)}
.ref-earn-desc{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase;margin-top:4px}

/* FAQ */
.faq{margin-bottom:24px}
.faq-item{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:6px;margin-bottom:10px;overflow:hidden}
.faq-q{padding:18px 22px;font-size:14px;font-weight:600;color:var(--white);cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:16px}
.faq-q::after{content:'+';font-family:var(--mono);color:var(--gold);font-size:18px;flex-shrink:0}
.faq-item.open .faq-q::after{content:'\2013'}
.faq-a{display:none;padding:0 22px 20px;font-size:13px;color:rgba(255,255,255,0.45);line-height:1.75}
.faq-item.open .faq-a{display:block}
.faq-a strong{color:var(--white)}

/* SIGNUP FORM */
.partner-signup{background:rgba(255,255,255,0.03);border:1px solid rgba(201,168,76,0.15);border-radius:8px;padding:40px}
.partner-signup h3{font-family:var(--display);font-size:28px;font-weight:900;color:var(--white);margin-bottom:8px}
.partner-signup p{font-size:14px;color:rgba(255,255,255,0.35);line-height:1.7;margin-bottom:24px}
.fg{margin-bottom:12px;text-align:left}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:rgba(255,255,255,0.05);border:2px solid rgba(255,255,255,0.08);color:var(--white);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus{border-color:var(--gold)}
.fg input::placeholder{color:rgba(255,255,255,0.2)}
.fg select option{background:var(--navy)}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn-gold{background:var(--gold);color:var(--navy);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-gold:hover{background:#e8c96a;transform:translateY(-2px)}
.btn-full-gold{width:100%;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s;background:var(--gold);color:var(--navy);margin-top:8px}
.btn-full-gold:hover{background:#e8c96a}
.key-box{display:none;margin-top:24px;background:rgba(0,0,0,0.4);border:1px solid rgba(201,168,76,0.2);border-radius:6px;padding:24px;text-align:left}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--gold);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;margin-bottom:12px}
.ref-box-inner{background:rgba(0,255,136,0.06);border:1px solid rgba(0,255,136,0.2);border-radius:4px;padding:16px;margin-bottom:12px}
.ref-code-big{font-family:var(--display);font-size:32px;color:var(--green);font-weight:900;margin:6px 0;letter-spacing:3px}
.demo-link-box{background:rgba(0,212,255,0.04);border:1px solid rgba(0,212,255,0.15);border-radius:4px;padding:16px}
.demo-link-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--cyan);text-transform:uppercase;margin-bottom:6px}
.demo-link-url{font-family:var(--mono);font-size:12px;color:var(--cyan);word-break:break-all;margin-bottom:10px}
.msg-err{display:none;color:#ff6b6b;font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:rgba(255,0,0,0.08);border-radius:4px;border:1px solid rgba(255,0,0,0.2)}
.msg-err.show{display:block}

footer{background:rgba(0,0,0,0.4);padding:48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px}
.foot-logo{font-family:var(--display);font-size:18px;color:var(--white);font-weight:900;text-decoration:none}.foot-logo span{color:var(--gold)}
.foot-links{display:flex;gap:24px;flex-wrap:wrap}
.foot-links a{color:rgba(255,255,255,0.2);text-decoration:none;font-size:12px;transition:color .2s}.foot-links a:hover{color:var(--white)}
.foot-copy{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.1);width:100%;margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.04)}

@media(max-width:900px){
  nav{padding:0 20px}.nav-links a:not(.nav-cta){display:none}
  .hero,.sec,.wl-sec,.referral-sec{padding-left:20px!important;padding-right:20px!important}
  .three-options,.partner-explain,.benefits-grid,.calc-inputs,.calc-results,.steps-grid,.wl-compare,.wl-tiers,.wl-steps,.ref-three,.ref-earnings,.fg-row{grid-template-columns:1fr!important}
  .playbook-head{flex-direction:column}
  .playbook-earn{text-align:left}
  footer{padding:36px 20px}.foot-inner{flex-direction:column;align-items:flex-start}
}
</style>
</head>
<body>

<nav>
  <a href="https://sebbi.pro" class="nav-logo">Monop <span>Content</span></a>
  <div class="nav-links">
    <a href="https://sebbi.pro/#products">Products</a>
    <a href="https://sebbi.pro/sonicboom">SonicBoom</a>
    <a href="https://sebbi.pro/contact">Contact</a>
    <a href="#partner-signup" class="nav-cta">Become a Partner</a>
  </div>
</nav>

<!-- HERO -->
<section class="hero">
  <div class="hero-inner">
    <span class="eyebrow">sebbi.pro &mdash; Build a Business On This Platform</span>
    <h1>Three ways in.<br><em>One engine underneath.</em></h1>
    <p class="hero-sub">AILeash is the compliance engine &mdash; decision governance, a tamper-evident chain, and now proof that an autonomous agent was entitled to act at all. You are the business on top of it. <strong>Sell it under our name, sell it under yours, or just share a code.</strong> Here is exactly what each route means, what it pays, and how to build a real recurring-revenue business from it &mdash; whether you're an IT consultancy, a call centre supplier, a web developer, or someone starting from zero.</p>

    <div class="three-options">
      <a href="#partner" class="option-card">
        <div class="option-badge option-badge-gold">Partner Programme</div>
        <h3>You sell it</h3>
        <p>Deploy AILeash inside your clients. Set your own price. Keep everything above 50p per device.</p>
        <div class="option-earn option-earn-gold">&pound;12,450</div>
        <div class="option-earn-label">example: 5 clients, 1,000 devices, &pound;2.99</div>
        <span class="option-link">Jump to Partner Programme &darr;</span>
      </a>
      <a href="#whitelabel" class="option-card">
        <div class="option-badge option-badge-purple">White-Label</div>
        <h3>Your brand on it</h3>
        <p>Your logo, your domain, your product name. Our engine underneath. Your clients never see us.</p>
        <div class="option-earn option-earn-purple">Free</div>
        <div class="option-earn-label">to join &mdash; 50p per device &mdash; your brand on top</div>
        <span class="option-link">Jump to White-Label &darr;</span>
      </a>
      <a href="#referral" class="option-card">
        <div class="option-badge option-badge-green">Referral Programme</div>
        <h3>You share a code</h3>
        <p>Give someone your code. They sign up. You earn 10p per device per month, forever. Zero work after sharing.</p>
        <div class="option-earn option-earn-green">10p</div>
        <div class="option-earn-label">per device per month &mdash; no cap &mdash; no expiry</div>
        <span class="option-link">Jump to Referral Programme &darr;</span>
      </a>
    </div>
  </div>
</section>

<!-- ============ PARTNER PROGRAMME ============ -->
<div class="sec-divider" id="partner"></div>
<section class="sec">
  <div class="sec-inner">
    <span class="sec-eyebrow eyebrow-gold">Partner Programme</span>
    <h2>You deploy it.<br>You sell it.<br><em>You keep the margin. Forever.</em></h2>
    <p class="sec-sub">You have clients &mdash; or you can find them. They need AI compliance, because from <strong>August 2026 the EU AI Act's obligations start biting</strong> and most companies have nothing in place. You sell AILeash at whatever price you choose. We take 50p per device per month. Everything above that is yours, every month, for as long as those devices stay live.</p>

    <!-- WHY JOIN: THE FULL BENEFITS -->
    <h3 class="block-title">Why partners join &mdash; the full picture</h3>
    <div class="benefits-grid">
      <div class="benefit">
        <h4>Recurring revenue, not one-off fees</h4>
        <p>Most consultancy work is paid once: you do the job, invoice, and start again from zero next month. Partner revenue is different &mdash; <strong>every device billed this month bills again next month</strong>. Land one 1,000-device client at &pound;2.99 and you've created &pound;2,490 of monthly margin that repeats without new work. Your income compounds as you add clients instead of resetting.</p>
      </div>
      <div class="benefit">
        <h4>You set the price &mdash; and keep the margin</h4>
        <p>We don't dictate your pricing. Charge &pound;1.99, &pound;2.99, &pound;5, &pound;10 per device &mdash; whatever your market bears. <strong>Our cut is a flat 50p per device regardless of your price</strong>, so every penny you negotiate above that is pure margin. Sell on value, bundle it into bigger contracts, or undercut competitors: the pricing strategy is entirely yours.</p>
      </div>
      <div class="benefit">
        <h4>Your client relationship stays yours</h4>
        <p>You invoice the client. You hold the relationship. We never contact your clients, never upsell them, never go around you. <strong>Their devices are locked to your partner code permanently</strong> &mdash; if they grow from 500 devices to 5,000, that growth is your growth.</p>
      </div>
      <div class="benefit">
        <h4>Zero cost, zero stock, zero risk</h4>
        <p>Joining is free. There's no minimum sales quota, no annual commitment, no certification fee, no stock to hold. <strong>If you sell nothing, you owe nothing.</strong> The only investment is the time you spend talking to prospects &mdash; and the demo link does the technical pitch for you.</p>
      </div>
      <div class="benefit">
        <h4>The demo sells itself</h4>
        <p>You get a personalised demo link. Your prospect clicks it and <strong>the engine scans them live</strong> &mdash; showing their own compliance gaps against the EU AI Act, in their own data, in real time. You're not pitching slides; you're showing them a problem they can see, with the fix attached. Your job is the follow-up call.</p>
      </div>
      <div class="benefit">
        <h4>A regulatory deadline does your urgency for you</h4>
        <p>Selling is easiest when the customer has a deadline. <strong>The EU AI Act's next wave of obligations lands August 2026</strong>, the UK Online Safety Act is live, and the 2024 Payment Services reimbursement rules already apply. You're not creating demand &mdash; you're arriving with the answer while the clock runs.</p>
      </div>
      <div class="benefit">
        <h4>A full product suite to sell, not one tool</h4>
        <p>One partnership covers the whole stack: <strong>AILeash</strong> (decision governance and audit chain), <strong>Guardian</strong> (child-safety suite for the Online Safety Act), <strong>Payment Notary</strong> (payment dispute evidence), <strong>Sentinel</strong>, <strong>Brain</strong> (instruction governance), <strong>authority continuity</strong> (proof an agent was entitled to act, exportable and checkable off our machines), and the free compliance scanner as your lead-generation hook. Different clients, different entry points, same partner code.</p>
      </div>
      <div class="benefit">
        <h4>Proof your client can hand to their own auditor</h4>
        <p>Most compliance tools produce a dashboard the client has to be trusted about. This produces evidence that leaves the building: any governed decision exports as a <strong>signed proof bundle</strong>, and their auditor checks it on their own machine with a one-file script that has no dependencies, makes no network calls and never contacts us. <strong>When authority could not be derived, the refusal is provable too</strong> &mdash; which grant, which rule, which hop. That is a demo that closes rooms, and no competitor in this space can run it.</p>
      </div>
      <div class="benefit">
        <h4>On-premise option for security-conscious clients</h4>
        <p>Some clients won't let data leave their network. The <strong>Sebdog Engine deploys inside their infrastructure</strong> &mdash; their data stays on their metal, you still bill per device. That single fact wins deals in finance, legal, and healthcare that cloud-only competitors can't touch.</p>
      </div>
    </div>

    <div class="partner-explain">
      <div class="explain-card">
        <h3>What you actually do</h3>
        <p>Sign up free below. You get your API key, your partner code, and your personalised demo link within sixty seconds. Send the demo link to a prospect. The engine scans them live and delivers a targeted pitch showing their gaps. You follow up and close. They sign up with your code, their devices link to your account permanently, and your margin lands every month from then on.</p>
      </div>
      <div class="explain-card">
        <h3>What you charge your client</h3>
        <p>Whatever you want. &pound;1.99 per device. &pound;5 per device. &pound;10 per device. Your price, your relationship, your invoice. We take 50p per device per month from whatever they pay. You keep everything above that. No minimum. No contract. No cap.</p>
      </div>
    </div>

    <!-- MARGIN CALCULATOR -->
    <div class="calc-wrap">
      <div class="calc-title">Your Margin Calculator</div>
      <div class="calc-sub">Set your price. See what you keep. We take 50p. You keep everything above that.</div>
      <div class="calc-inputs">
        <div>
          <div class="calc-label">You charge per device</div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-family:var(--display);font-size:28px;color:var(--gold);font-weight:900">&pound;</span>
            <input class="calc-input" type="number" id="p-charge" value="2.99" min="0.51" step="0.01" oninput="pCalc()">
          </div>
        </div>
        <div>
          <div class="calc-label">Devices per client</div>
          <select class="calc-select" id="p-devices" onchange="pCalc()">
            <option value="100">100 devices</option>
            <option value="500">500 devices</option>
            <option value="1000" selected>1,000 devices</option>
            <option value="5000">5,000 devices</option>
            <option value="10000">10,000 devices</option>
            <option value="50000">50,000 devices</option>
          </select>
        </div>
        <div>
          <div class="calc-label">Number of clients</div>
          <select class="calc-select" id="p-clients" onchange="pCalc()">
            <option value="1">1 client</option>
            <option value="3">3 clients</option>
            <option value="5" selected>5 clients</option>
            <option value="10">10 clients</option>
            <option value="20">20 clients</option>
            <option value="50">50 clients</option>
          </select>
        </div>
      </div>
      <div class="calc-results">
        <div class="cr"><div class="cr-label">Client Pays</div><div class="cr-amount cr-client" id="p-r-client">&pound;2.99</div><div class="cr-sub">per device per month</div></div>
        <div class="cr"><div class="cr-label">You Keep</div><div class="cr-amount cr-you" id="p-r-profit">&pound;12,450</div><div class="cr-sub">per month margin</div></div>
        <div class="cr"><div class="cr-label">We Take</div><div class="cr-amount cr-we" id="p-r-we">&pound;2,500</div><div class="cr-sub">50p per device</div></div>
        <div class="cr"><div class="cr-label">Per Year</div><div class="cr-amount cr-year" id="p-r-year">&pound;149,400</div><div class="cr-sub">annual margin</div></div>
      </div>
      <div class="calc-pitch" id="p-pitch">Your clients pay &pound;2.99 per device. You keep &pound;12,450 a month across 5 clients. We take &pound;2,500. Everyone wins.</div>
      <p class="calc-note">Illustrative figures based on the inputs above. Your partner code links every device to your account permanently &mdash; you earn your margin every month those devices stay live.</p>
    </div>

    <!-- INDUSTRY PLAYBOOKS -->
    <h3 class="block-title">The playbooks &mdash; how each business actually makes money from this</h3>
    <p class="sec-sub" style="margin-bottom:28px">Not theory. Each of these is a concrete route from where you are today to monthly recurring revenue, with the maths shown. Every figure is an example based on the pricing shown &mdash; your prices and client sizes will set your real numbers.</p>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#127963;&#65039; IT Consultancies &amp; MSPs</h4>
        <div class="playbook-earn"><div class="num">&pound;12,450</div><div class="lbl">example monthly margin</div></div>
      </div>
      <p><strong>Your position:</strong> you already manage your clients' devices, networks, and software estate. They trust you to tell them what they need next. AI compliance is the next thing they need &mdash; and right now, almost none of them have it.</p>
      <p><strong>The play:</strong> add "AI Compliance &mdash; managed" as a line on your existing service catalogue. Run the free scanner (sebbi.pro/scan) against each client as part of your next quarterly review &mdash; it produces a gap report you can put in front of them the same day. Every gap in that report is a reason to switch on AILeash. Because you already bill them monthly, this is one extra line on an invoice they already pay.</p>
      <p><strong>For clients who won't allow external data flows</strong> &mdash; deploy the Sebdog Engine inside their network. Their data never leaves. You still bill per device.</p>
      <div class="maths">
        5 clients &times; 1,000 devices &times; &pound;2.99 <span class="dim">= &pound;14,950 billed</span><br>
        minus 50p &times; 5,000 devices <span class="dim">= &pound;2,500 to us</span><br>
        <b>= &pound;12,450/month margin &middot; &pound;149,400/year</b> <span class="dim">&mdash; on top of your existing contracts</span>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#128222; Call Centres &amp; Contact-Platform Suppliers</h4>
        <div class="playbook-earn"><div class="num">&pound;1,490</div><div class="lbl">example: one 1,000-seat floor</div></div>
      </div>
      <p><strong>Your position:</strong> you supply or run contact-centre technology. Your clients' agents make thousands of AI-assisted decisions a day &mdash; call routing, fraud flags, identity checks &mdash; and none of it is provable after the fact.</p>
      <p><strong>The play:</strong> sell AILeash per seat as the audit layer under the AI tools the floor already uses. Before an agent picks up, the engine has scored the interaction &mdash; device, location, risk; fraud flagged before a word is spoken. Every ALLOW/CHALLENGE/BLOCK decision lands in the hash chain, so when a customer disputes what happened on a call, there's a sealed record. Pitch it to the operations director as dispute-protection: one avoided regulatory complaint pays for the year.</p>
      <p><strong>Scale maths:</strong> contact centres are dense &mdash; one client is hundreds or thousands of seats. Three mid-size floors can match what ten small IT clients pay.</p>
      <div class="maths">
        1,000 seats &times; &pound;1.99 <span class="dim">= &pound;1,990 billed</span> &middot; minus &pound;500 <span class="dim">to us</span> = <b>&pound;1,490/month per floor</b><br>
        5 floors = <b>&pound;7,450/month &middot; &pound;89,400/year</b>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#128187; Web Developers &amp; Agencies</h4>
        <div class="playbook-earn"><div class="num">&pound;3,735</div><div class="lbl">example: 15 client sites</div></div>
      </div>
      <p><strong>Your position:</strong> you build and maintain websites and apps for small and mid-size businesses. More and more of those builds now include AI features &mdash; chatbots, recommendation engines, automated decisions &mdash; and your clients have no idea those features carry compliance obligations.</p>
      <p><strong>The play:</strong> make compliance part of every AI feature you ship. When you build a client a chatbot, wire AILeash in as the governance layer and bill it as a monthly "AI compliance &amp; monitoring" line alongside your existing hosting/maintenance retainer. Your clients already pay you monthly for hosting &mdash; this is the same motion. For new business, run the free scanner against a prospect's site before the pitch meeting and open with their gap report. It turns "do you need a new website?" into "your current site has compliance exposure &mdash; here's the fix, and we build it in."</p>
      <p><strong>Why it sticks:</strong> a client can move hosting anywhere. Moving a compliance audit chain mid-stream is much harder &mdash; this line item makes your whole retainer stickier.</p>
      <div class="maths">
        15 client sites &times; avg 100 devices &times; &pound;2.99 <span class="dim">= &pound;4,485 billed</span><br>
        minus 50p &times; 1,500 <span class="dim">= &pound;750 to us</span> = <b>&pound;3,735/month &middot; &pound;44,820/year</b> <span class="dim">&mdash; on top of hosting retainers</span>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#128203; Legal &amp; Compliance Firms</h4>
        <div class="playbook-earn"><div class="num">&pound;7,500</div><div class="lbl">example: 10 audit clients</div></div>
      </div>
      <p><strong>Your position:</strong> clients pay you to tell them whether they're compliant. Under the EU AI Act, the honest answer for most of them is no &mdash; and an audit report that ends "you have gaps" invites the question "so what do we do?"</p>
      <p><strong>The play:</strong> AILeash is your answer to that question. Your engagement becomes: audit (your fees) &rarr; remediation (deploy AILeash, your margin) &rarr; ongoing monitoring (recurring revenue). Instead of handing clients a PDF and leaving, you hand them a running system with your firm attached to it every month. The audit chain also strengthens your own advice: you can show a regulator the client's decisions are sealed and verifiable, not just described in a policy document.</p>
      <div class="maths">
        10 clients &times; 500 devices &times; &pound;2.00 <span class="dim">= &pound;10,000 billed</span><br>
        minus 50p &times; 5,000 <span class="dim">= &pound;2,500 to us</span> = <b>&pound;7,500/month &middot; &pound;90,000/year</b> <span class="dim">&mdash; on top of audit fees</span>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#127918; Gaming &amp; Consumer Platforms</h4>
        <div class="playbook-earn"><div class="num">&pound;2,490</div><div class="lbl">example: 3,000 devices</div></div>
      </div>
      <p><strong>Your position:</strong> you supply platforms with child or teenage users &mdash; games, communities, education apps. The Online Safety Act puts hard duties on them, with real penalties.</p>
      <p><strong>The play:</strong> sell Guardian &mdash; the child-safety suite built under the Online Safety Act framing &mdash; as a managed service. The parent/child PWA pair gives platforms something concrete to show Ofcom-facing due diligence: monitored decisions, sealed logs, parental controls. For platforms, "we deployed a dedicated safety layer" is a much stronger regulatory position than "we have a policy."</p>
      <div class="maths">
        3,000 devices &times; &pound;1.33 <span class="dim">= &pound;3,990 billed</span> &middot; minus &pound;1,500 <span class="dim">to us</span> = <b>&pound;2,490/month &middot; &pound;29,880/year</b>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#127974; Financial Services Suppliers</h4>
        <div class="playbook-earn"><div class="num">&pound;22,500</div><div class="lbl">example: 5,000 devices</div></div>
      </div>
      <p><strong>Your position:</strong> you serve banks, lenders, insurers, or payment firms. Every AI decision they make &mdash; credit scoring, fraud flags, payment holds &mdash; needs to be explainable and provable, and the 2024 Payment Services reimbursement rules put money directly on the line for disputed payments.</p>
      <p><strong>The play:</strong> sell the audit chain plus Payment Notary as dispute-evidence infrastructure. When a customer claims "I never authorised that payment," a sealed cryptographic record of what the system decided and when is the difference between paying out and defending the decision. Financial clients pay the highest per-device prices in this list because the cost of not having it is measured in reimbursements &mdash; which is why the worked example uses &pound;5/device.</p>
      <div class="maths">
        5,000 devices &times; &pound;5.00 <span class="dim">= &pound;25,000 billed</span> &middot; minus &pound;2,500 <span class="dim">to us</span> = <b>&pound;22,500/month &middot; &pound;270,000/year</b>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#129302; AI Agent Builders &amp; Automation Platforms</h4>
        <div class="playbook-earn"><div class="num">&pound;9,960</div><div class="lbl">example: 4 platforms, 1,000 seats</div></div>
      </div>
      <p><strong>Your position:</strong> you build or supply autonomous agents &mdash; anything where software takes an action on a person's behalf rather than suggesting one. Your clients' boards are now asking the question nobody in this category can answer: <em>who authorised the agent to do that?</em></p>
      <p><strong>The play:</strong> sell authority continuity as the layer underneath the agents. Every grant traces back to the human who issued it, narrows at every hop, and is re-derived at the instant the agent acts &mdash; so a permission revoked three delegations up kills the action immediately rather than at the next token refresh. Each lineage also names <strong>who accepted the risk of that capability existing</strong>, separately from who granted it and who ran it, which is the name their incident process actually needs and currently does not have.</p>
      <p><strong>Why it closes:</strong> you do not have to argue the value. Export one decision as a signed proof, hand it to their security lead, and let them verify it on their own laptop with the network off. Then export a <em>refused</em> one and show it naming the exact grant and rule that broke. Nobody else in this market can put that on the table.</p>
      <div class="maths">
        4 platforms &times; 1,000 seats &times; &pound;3.00 <span class="dim">= &pound;12,000 billed</span><br>
        minus 50p &times; 4,000 <span class="dim">= &pound;2,000 to us</span> = <b>&pound;9,960/month &middot; &pound;119,520/year</b>
      </div>
    </div>

    <div class="playbook">
      <div class="playbook-head">
        <h4>&#128640; Starting From Zero &mdash; no clients yet</h4>
        <div class="playbook-earn"><div class="num">&pound;747</div><div class="lbl">example: first 3 small clients</div></div>
      </div>
      <p><strong>Your position:</strong> no agency, no client base &mdash; just willingness to work. This programme can be the whole business, because the two expensive parts of starting a software company (building the product, running the infrastructure) are already done.</p>
      <p><strong>The play, step by step:</strong> pick one niche you can talk to &mdash; local accountancy firms, dental chains, recruitment agencies, letting agents. Run the free scanner against ten of them; it costs nothing and produces a personalised gap report for each. Email or call with the report: "I ran a compliance scan against your site &mdash; three of the gaps are the kind regulators are focusing on from August. Fifteen minutes to walk you through it?" Send your demo link before the call so the engine has already made the technical case. Close at a modest price &mdash; &pound;2.49/device on small device counts &mdash; because your first three clients are your references. Then ask each one for an introduction, and repeat.</p>
      <p><strong>What it costs you:</strong> &pound;0. No stock, no licence fee, no quota. Your only spend is time &mdash; and every client you land pays you again next month whether you work that month or not.</p>
      <div class="maths">
        3 clients &times; 125 devices &times; &pound;2.49 <span class="dim">= &pound;933 billed</span> &middot; minus &pound;187 <span class="dim">to us</span> = <b>&pound;747/month from a standing start</b><br>
        <span class="dim">Land one client a month for a year at that size:</span> <b>&pound;2,988/month by month 12 &middot; growing</b>
      </div>
    </div>

    <!-- HOW IT WORKS -->
    <h3 class="block-title">How it works</h3>
    <div class="steps-grid">
      <div class="step"><div class="step-n">01</div><h3>Sign up free</h3><p>Get your API key, your partner code, and your personalised demo link. Takes 60 seconds. No cost.</p></div>
      <div class="step"><div class="step-n">02</div><h3>Send the demo link</h3><p>One URL. Your prospect clicks it. The engine scans them live and delivers your pitch. You follow up.</p></div>
      <div class="step"><div class="step-n">03</div><h3>They sign up</h3><p>Their devices are permanently linked to your partner code. Every device. Every month.</p></div>
      <div class="step"><div class="step-n">04</div><h3>You earn your margin</h3><p>They pay you. We take 50p per device. You keep everything above it. Every month those devices stay live.</p></div>
    </div>

    <!-- PARTNER FAQ -->
    <h3 class="block-title">Partner questions, answered straight</h3>
    <div class="faq" id="partner-faq">
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">What does "per device" actually mean?</div><div class="faq-a">A device is any endpoint running under AILeash governance for your client &mdash; a workstation, an agent seat, a server instance making AI decisions. You bill your client per device at your price; we count the same devices and take 50p each per month.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">When and how do I get paid?</div><div class="faq-a"><strong>You invoice your client directly at your price</strong> &mdash; the money comes to you first, on your payment terms. We bill you 50p per active device monthly. You are never waiting on us to pay you out.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">What if my client cancels?</div><div class="faq-a">Billing stops for those devices &mdash; both your margin and our 50p. No penalty, no clawback, no minimum term. Your other clients are unaffected.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Do I need technical skills to deploy it?</div><div class="faq-a">For cloud deployment, no &mdash; signup, code, and demo link are self-serve, and clients onboard through the same flow. On-premise Sebdog Engine deployments need basic server access at the client side; if that's beyond you, email justin@monopcontent.com and we'll support the install.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Can I be a partner and a referrer at the same time?</div><div class="faq-a">Yes &mdash; the same code does both. Clients you actively sell and deploy earn you your full margin; people you simply refer who sign themselves up earn you 10p per device per month.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">What can I actually show a prospect in a first meeting?</div><div class="faq-a">Three links, no slides. <strong>sebbi.pro/self-check</strong> runs every claim the platform publishes about itself and grades them in front of your prospect &mdash; including the two still marked amber. <strong>sebbi.pro/x/continuity/proof</strong> returns a signed proof of a real authority decision. And <strong>sebbi.pro/verify-authority.py</strong> is the one-file checker their own engineer runs, with no dependencies and no network. Handing someone the tool to check you is a stronger opening than any deck.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Is there a contract or exclusivity?</div><div class="faq-a">No exclusivity either way &mdash; you can sell other products, and other partners can operate in your market. No lock-in for you: stop selling any time and you keep earning on devices already linked to your code while they stay live.</div></div>
    </div>

    <!-- PARTNER SIGNUP FORM -->
    <div class="partner-signup" id="partner-signup">
      <h3>Become a Partner</h3>
      <p>Free to join. Get your partner code, your demo link, and your API key. Start sending prospects today.</p>
      <div class="fg-row">
        <div class="fg"><label>First Name</label><input type="text" id="p-fn" placeholder="Justin"></div>
        <div class="fg"><label>Last Name</label><input type="text" id="p-ln" placeholder="Smith"></div>
      </div>
      <div class="fg"><label>Email Address</label><input type="email" id="p-em" placeholder="you@company.com"></div>
      <div class="fg"><label>Phone Number</label><input type="tel" id="p-ph" placeholder="+44 7700 000000"></div>
      <div class="fg"><label>Company Name</label><input type="text" id="p-org" placeholder="e.g. ACME IT Solutions"></div>
      <div class="fg"><label>Your Industry</label>
        <select id="p-industry">
          <option value="it">IT Consultancy / MSP</option>
          <option value="web">Web Developer / Agency</option>
          <option value="callcentre">Call Centre / Contact Platform</option>
          <option value="legal">Legal / Compliance Firm</option>
          <option value="finance">Financial Services</option>
          <option value="gaming">Gaming / Consumer Platform</option>
          <option value="startup">Starting From Zero</option>
          <option value="other">Other</option>
        </select>
      </div>
      <button class="btn-full-gold" onclick="doPartnerSignup()">Get My Partner Code &amp; Demo Link &rarr;</button>
      <div class="msg-err" id="p-msg-err"></div>
      <div class="key-box" id="p-key-box">
        <div class="key-lbl">Your API Key &mdash; Save This</div>
        <div class="key-val" id="p-key-val"></div>
        <div class="ref-box-inner">
          <div class="key-lbl">Your Partner Code &mdash; Links Every Client To You</div>
          <div class="ref-code-big" id="p-ref-code">REF-XXXX-0000</div>
          <div style="font-size:12px;color:rgba(255,255,255,0.35);line-height:1.6">Every device that signs up using this code earns you your margin every month it stays live.</div>
        </div>
        <div class="demo-link-box">
          <div class="demo-link-label">Your Personalised Demo Link &mdash; Send This To Prospects</div>
          <div class="demo-link-url" id="p-demo-link">https://sebbi.pro/reseller?ref=REF-XXXX-0000</div>
          <button onclick="copyPartnerLink()" style="background:rgba(0,212,255,0.1);border:1px solid rgba(0,212,255,0.2);color:var(--cyan);padding:8px 16px;border-radius:4px;font-family:var(--mono);font-size:10px;cursor:pointer;letter-spacing:1px;text-transform:uppercase">Copy Demo Link</button>
        </div>
      </div>
    </div>

  </div>
</section>

<!-- ============ WHITE LABEL ============ -->
<div class="sec-divider-purple" id="whitelabel"></div>
<section class="wl-sec">
  <div class="sec-inner">
    <span class="sec-eyebrow eyebrow-purple">White-Label Programme</span>
    <h2>Your brand.<br>Your product.<br><em class="purple">Our engine underneath.</em></h2>
    <p class="sec-sub">The Partner Programme sells <strong>AILeash by sebbi.pro</strong>. White-label removes our name entirely: your logo, your domain, your product name, your pricing page &mdash; running on our engine. Your clients sign up to <strong>you</strong>. They never see sebbi.pro. For agencies and consultancies who want to own a product, not resell one.</p>

    <h3 class="block-title" style="margin-top:0">What white-label changes</h3>
    <div class="wl-compare">
      <div class="wl-col theirs">
        <h4>Standard Partner</h4>
        <ul>
          <li>You sell <b>AILeash</b> &mdash; sebbi.pro branding visible</li>
          <li>Demo link and dashboards carry our name</li>
          <li>Client signup happens on sebbi.pro</li>
          <li>Free to join &mdash; margin above 50p/device</li>
          <li>Fastest route to first revenue</li>
        </ul>
      </div>
      <div class="wl-col yours">
        <h4>White-Label Partner</h4>
        <ul>
          <li>You sell <b>your product name</b> &mdash; our name nowhere</li>
          <li>Your logo, colours, and domain on every screen</li>
          <li>Client signup happens on <b>your</b> site</li>
          <li>Free to join &mdash; same 50p/device, your brand on top</li>
          <li>You're building a <b>brand asset you own</b> &mdash; a product line with your name on it that adds real value to your company</li>
        </ul>
      </div>
    </div>

    <h3 class="block-title">What you get</h3>
    <div class="benefits-grid">
      <div class="benefit" style="border-color:rgba(180,140,255,0.12)">
        <h4 style="color:var(--purple)">The full engine, rebadged</h4>
        <p>Everything under the hood is the production AILeash stack: the 9-signal scoring engine, the SHA-256 hash-chained audit trail, ALLOW/CHALLENGE/BLOCK decisioning, the compliance scanner, and the verification suite. <strong>Your clients get the real thing &mdash; wearing your badge.</strong></p>
      </div>
      <div class="benefit" style="border-color:rgba(180,140,255,0.12)">
        <h4 style="color:var(--purple)">Your domain, your signup flow</h4>
        <p>The platform runs at your domain (e.g. <strong>compliance.youragency.com</strong>) with your logo and colour scheme. Clients register, log in, and see reports under your brand. Invoices come from you. Support email is yours.</p>
      </div>
      <div class="benefit" style="border-color:rgba(180,140,255,0.12)">
        <h4 style="color:var(--purple)">Your own lead machine</h4>
        <p>The free compliance scanner is rebadged too &mdash; put it on your own site as <strong>your</strong> free tool. Every business that scans itself becomes your lead, sees your brand on the gap report, and gets your upgrade pitch.</p>
      </div>
      <div class="benefit" style="border-color:rgba(180,140,255,0.12)">
        <h4 style="color:var(--purple)">Updates without the engineering bill</h4>
        <p>When regulations shift and the engine updates, <strong>your product updates with it</strong> &mdash; no dev team on your payroll. You get the roadmap of a full product company for nothing but the 50p per device you already pay.</p>
      </div>
    </div>

    <h3 class="block-title">White-label tiers</h3>
    <div class="wl-tiers">
      <div class="wl-tier">
        <h4>Badged</h4>
        <div class="price">Free</div>
        <div class="price-sub">50p per device per month &mdash; same as Partner</div>
        <ul>
          <li>Your logo and colours on the client dashboard</li>
          <li>Runs on a subdomain we host (yourname.sebbi.pro)</li>
          <li>Rebadged gap reports and demo link</li>
          <li>You keep 100% of your client pricing</li>
          <li>Cancel monthly &mdash; fall back to standard Partner</li>
        </ul>
      </div>
      <div class="wl-tier featured">
        <h4>Full White-Label</h4>
        <div class="price">Free</div>
        <div class="price-sub">50p per device per month &mdash; we only earn when you do</div>
        <ul>
          <li>Your own domain &mdash; our name appears nowhere</li>
          <li>Your product name across every screen, report, and email</li>
          <li>Rebadged scanner on your site as your lead tool</li>
          <li>Client signup and billing flows under your brand</li>
          <li>Priority support and deployment help</li>
        </ul>
      </div>
      <div class="wl-tier">
        <h4>Sovereign</h4>
        <div class="price">Custom</div>
        <div class="price-sub">annual licence &mdash; talk to Justin</div>
        <ul>
          <li>Sebdog Engine deployed inside your own infrastructure</li>
          <li>Air-gapped licence tokens &mdash; runs without calling home</li>
          <li>Your data plane end to end &mdash; nothing transits sebbi.pro</li>
          <li>For firms selling into finance, defence, and government</li>
        </ul>
      </div>
    </div>

    <div class="calc-pitch" style="border-color:rgba(180,140,255,0.15);background:rgba(180,140,255,0.04);margin-bottom:48px">
      <b style="color:var(--purple)">White-label worked example:</b> Full White-Label, free to join. 4 clients &times; 1,000 devices at your price of &pound;3.50 = &pound;14,000 billed by you under your own brand. We take 50p &times; 4,000 devices = &pound;2,000. <b style="color:#00ff88">Your margin: &pound;12,000/month &mdash; under your own product name, with no platform fee.</b>
    </div>

    <h3 class="block-title">How white-label onboarding works</h3>
    <div class="steps-grid wl-steps">
      <div class="step"><div class="step-n">01</div><h3>Apply</h3><p>Sign up as a partner below, pick your industry, then email justin@monopcontent.com with "white-label" and your product name.</p></div>
      <div class="step"><div class="step-n">02</div><h3>Brand it</h3><p>Send your logo, colours, domain, and product name. Badged tier is live in days; full white-label as soon as your domain is pointed.</p></div>
      <div class="step"><div class="step-n">03</div><h3>Launch</h3><p>Your scanner goes on your site, your demo link goes to prospects, your signup flow goes live under your brand.</p></div>
      <div class="step"><div class="step-n">04</div><h3>Own it</h3><p>Clients sign to you, pay you, and renew with you. You've launched a product line &mdash; without building the product.</p></div>
    </div>

    <div class="faq">
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Who owns the client relationship under white-label?</div><div class="faq-a"><strong>You do, completely.</strong> Clients contract with you, pay you, and know only your brand. We provide the engine to you under the white-label agreement &mdash; we have no relationship with your clients.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">What does white-label cost me?</div><div class="faq-a"><strong>Nothing to join</strong> &mdash; same deal as the Partner Programme: 50p per active device per month, and that's it. We only earn when your clients' devices are live, so we make money when you do.</div></div>
      <div class="faq-item"><div class="faq-q" onclick="toggleFaq(this)">Can I white-label just one product, like Guardian?</div><div class="faq-a">Yes &mdash; scope it in your application email. Some partners white-label only Guardian for the child-safety market, or only the scanner as a branded lead tool.</div></div>
    </div>

  </div>
</section>

<!-- ============ REFERRAL PROGRAMME ============ -->
<div class="sec-divider-green" id="referral"></div>
<section class="referral-sec">
  <div class="referral-inner">
    <span class="sec-eyebrow eyebrow-green">Referral Programme</span>
    <h2 style="font-family:var(--display);font-size:clamp(26px,3.5vw,44px);font-weight:900;margin-bottom:16px">Tell a friend.<br><em class="green" style="font-style:normal;color:var(--green)">Earn forever.</em></h2>
    <p style="font-size:15px;color:rgba(255,255,255,0.35);line-height:1.8;max-width:580px;margin:0 auto 0">This is the simple one. You get a referral code when you sign up. You share it with anyone &mdash; a colleague, a friend, a business contact. Every device they sign up earns you 10p per device per month. Forever. No cap. No expiry. No work required after sharing the code.</p>

    <div class="ref-three">
      <div class="ref-card">
        <div class="ref-icon">&#128272;</div>
        <h3>You get a code</h3>
        <p>When you sign up you get a unique referral code. It looks like REF-JOHN-1234. That code is yours forever.</p>
      </div>
      <div class="ref-card">
        <div class="ref-icon">&#128172;</div>
        <h3>You share it</h3>
        <p>Send it to anyone. A colleague, a tech mate, a call centre manager. Anyone who signs up using your code is linked to you permanently.</p>
        <div class="ref-earn">10p</div>
        <div class="ref-earn-label">per device per month forever</div>
      </div>
      <div class="ref-card">
        <div class="ref-icon">&#128176;</div>
        <h3>You earn forever</h3>
        <p>10 referrals with 100 devices each &mdash; &pound;100 a month doing nothing. 10 referrals with 1,000 devices each &mdash; &pound;1,000 a month.</p>
      </div>
    </div>

    <div class="ref-code-sec">
      <div class="ref-code-title">Your referral code</div>
      <div class="ref-code-sub">Sign up as a partner above and your referral code appears here automatically. Or sign up on the main homepage to get just the referral code without the partner programme.</div>
      <div class="ref-code-display" id="r-code-display">REF-XXXX-0000</div>
      <div class="ref-code-hint">Your unique code &mdash; share this with anyone</div>

      <div class="ref-share-text">
        &ldquo;I use AILeash for AI compliance &mdash; it seals every AI decision into a cryptographic chain so you can prove what your system decided. Free to start. Use my code <strong id="r-code-inline">REF-XXXX-0000</strong> when you sign up at sebbi.pro&rdquo;
      </div>

      <div class="ref-link" id="r-link-display">https://sebbi.pro/#signup</div>

      <button onclick="copyRefCode()" style="background:rgba(0,255,136,0.1);border:1px solid rgba(0,255,136,0.2);color:var(--green);padding:10px 20px;border-radius:4px;font-family:var(--mono);font-size:11px;cursor:pointer;letter-spacing:1px;text-transform:uppercase;margin-bottom:20px">Copy Referral Code</button>

      <div class="ref-earnings">
        <div class="ref-earn-card">
          <div class="ref-earn-num">&pound;100</div>
          <div class="ref-earn-desc">10 referrals &mdash; 100 devices each</div>
        </div>
        <div class="ref-earn-card">
          <div class="ref-earn-num">&pound;1,000</div>
          <div class="ref-earn-desc">10 referrals &mdash; 1,000 devices each</div>
        </div>
        <div class="ref-earn-card">
          <div class="ref-earn-num">&pound;5,000</div>
          <div class="ref-earn-desc">10 referrals &mdash; 5,000 devices each</div>
        </div>
      </div>

      <p style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);margin-top:16px;letter-spacing:1px">Check your referral earnings at <a href="https://sebbi.pro/referrals" style="color:var(--green)">sebbi.pro/referrals?code=YOUR-CODE</a></p>
    </div>
  </div>
</section>

<footer>
  <div class="foot-inner">
    <a href="https://sebbi.pro" class="foot-logo">Monop <span>Content</span></a>
    <div class="foot-links">
      <a href="https://sebbi.pro/#products">All Products</a>
      <a href="https://sebbi.pro/sonicboom">SonicBoom</a>
      <a href="https://sebbi.pro/compliance-assistant">AILeash</a>
      <a href="https://sebbi.pro/sentinel">Sentinel</a>
      <a href="https://sebbi.pro/scan">Free Scanner</a>
      <a href="https://sebbi.pro/contact">Contact Justin</a>
    </div>
    <div class="foot-copy">&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; justin@monopcontent.com &middot; 07908 269428 &middot; Earnings figures on this page are illustrative examples based on the stated pricing and device counts &mdash; actual results depend on your prices and clients.</div>
  </div>
</footer>

<script>
// CALCULATOR
function pCalc(){
  var charge=parseFloat(document.getElementById('p-charge').value)||0;
  var devices=parseInt(document.getElementById('p-devices').value)||0;
  var clients=parseInt(document.getElementById('p-clients').value)||1;
  var total=devices*clients;
  var profit=Math.max(0,charge-0.50)*total;
  var we=0.50*total;
  var annual=profit*12;
  document.getElementById('p-r-client').textContent='\u00a3'+charge.toFixed(2);
  document.getElementById('p-r-profit').textContent='\u00a3'+profit.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('p-r-we').textContent='\u00a3'+we.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('p-r-year').textContent='\u00a3'+annual.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  document.getElementById('p-pitch').textContent='Your clients pay \u00a3'+charge.toFixed(2)+' per device. You keep \u00a3'+profit.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0})+' a month across '+clients+' client'+(clients>1?'s':'')+'. We take \u00a3'+we.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0})+'. Everyone wins.';
}
pCalc();

// FAQ
function toggleFaq(el){
  el.parentElement.classList.toggle('open');
}

function copyPartnerLink(){
  var url=document.getElementById('p-demo-link').textContent;
  navigator.clipboard.writeText(url).then(function(){alert('Demo link copied!');}).catch(function(){});
}

function copyRefCode(){
  var code=document.getElementById('r-code-display').textContent;
  navigator.clipboard.writeText(code).then(function(){alert('Referral code copied!');}).catch(function(){});
}

function updateRefDisplay(code){
  document.getElementById('r-code-display').textContent=code;
  document.getElementById('r-code-inline').textContent=code;
  document.getElementById('r-link-display').textContent='https://sebbi.pro/#signup?ref='+code;
}

// PARTNER SIGNUP
async function doPartnerSignup(){
  var fn=document.getElementById('p-fn').value.trim();
  var ln=document.getElementById('p-ln').value.trim();
  var em=document.getElementById('p-em').value.trim();
  var ph=document.getElementById('p-ph').value.trim();
  var org=document.getElementById('p-org').value.trim();
  var industry=document.getElementById('p-industry').value;
  var err=document.getElementById('p-msg-err');
  var kb=document.getElementById('p-key-box');
  var btn=document.querySelector('.btn-full-gold');
  err.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company name.';err.classList.add('show');return;}
  var orig=btn.textContent;btn.textContent='Creating account\u2026';btn.disabled=true;
  try{
    var r=await fetch('https://sebbi.pro/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:'partner_'+industry,product:'aileash',devices:1})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('p-key-val').textContent=d.api_key;
      var code=d.ref_code||'REF-XXXX-0000';
      document.getElementById('p-ref-code').textContent=code;
      document.getElementById('p-demo-link').textContent='https://sebbi.pro/reseller?ref='+code;
      updateRefDisplay(code);
      kb.classList.add('show');
      btn.textContent='Account created \u2713';
    }else{
      err.textContent=d.error||'Something went wrong. Email justin@monopcontent.com';
      err.classList.add('show');btn.textContent=orig;btn.disabled=false;
    }
  }catch(e){
    err.textContent='Cannot reach server. Email justin@monopcontent.com';
    err.classList.add('show');btn.textContent=orig;btn.disabled=false;
  }
}
</script>
</body>
</html>

```


## `risk-policy.html`

106 lines, 12508 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Risk Management Policy — Monop Content / AILeash</title>
<meta name="description" content="The AI risk management policy for the AILeash platform, aligned to EU AI Act Article 9: how risks are identified, mitigated, tested, monitored and reviewed.">
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
  p{font-size:14.5px;color:var(--muted);margin-bottom:13px}
  p b{color:#fff}
  ul{margin:0 0 14px 0;list-style:none}
  li{position:relative;padding-left:20px;margin-bottom:9px;font-size:14px;color:var(--muted)}
  li::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--gold)}
  li b{color:#fff}
  .honest{border:1px solid rgba(201,168,76,.35);background:rgba(201,168,76,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .honest b{color:var(--gold)}
  table{width:100%;border-collapse:collapse;font-size:13px;margin:14px 0}
  th{padding:9px 10px;text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.08em;color:var(--faint);border-bottom:2px solid var(--line)}
  td{padding:10px;border-bottom:1px solid var(--line);vertical-align:top;color:var(--muted)}
  td:first-child{color:#fff;font-weight:600}
  hr{border:none;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,.25),transparent);margin:40px 0 0}
  footer{margin-top:30px;text-align:center;font-size:12px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
  footer a{color:var(--gold);text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; sebbi.pro</a>
  <div class="eyebrow">monop content · policy document · public</div>
  <h1>AI Risk Management Policy<br><span>AILeash Platform</span></h1>
  <div class="meta">
    Document: MC-POL-001 · Version 1.0 · Effective 20 July 2026<br>
    Owner: Justin Dobson, Founder, Monop Content · Review cycle: quarterly, and on any material platform change<br>
    Alignment: EU AI Act (Regulation 2024/1689) Article 9 · published at sebbi.pro/risk-policy
  </div>

  <h2><span class="n">1.</span>Purpose and scope</h2>
  <p>This policy describes how Monop Content identifies, analyses, mitigates, tests and monitors risk across the lifecycle of the AILeash platform — the decision engine, the tamper-evident audit chain, the delegation layer (authority, KYC sealing, jurisdiction tagging), the public notaries, Brain, and the hosted infrastructure they run on.</p>
  <p>It applies to all platform components, all releases, and all environments (the hosted cloud service and the sovereign on-premise engine). It is written to align with the risk-management system expectations of Article 9 of the EU AI Act, and it is published because a governance vendor's own risk posture should be inspectable.</p>
  <div class="honest"><b>Classification, stated honestly:</b> AILeash is a governance and evidence tool that sits alongside customers' AI systems; it is not itself a high-risk AI system under Annex III of the Act, and it makes no automated decisions about natural persons' rights. We maintain this policy to the Article 9 standard anyway — because our customers' compliance rests partly on our reliability, and because we should be held to the standard we help others evidence.</div>

  <h2><span class="n">2.</span>Roles and responsibility</h2>
  <p>Monop Content is at present a single-operator company. Accountability is therefore simple and total: <b>the Founder is the risk owner</b> for every item in this policy — identification, mitigation, testing, monitoring, incident response and review. There is no diffusion of responsibility. As the company grows, this section will be revised to assign named owners per risk area, and that revision will be sealed (see §8).</p>

  <h2><span class="n">3.</span>Risk identification and analysis</h2>
  <p>Risks are identified continuously through four channels: design review before any change ships; automated verification of the chain after every deployment; monitoring of live traffic, error rates and blocked-event patterns; and external input (customer reports, security disclosures to justin@monopcontent.com, and the public verifiability of the chain itself — anyone can attempt to falsify our records at any time).</p>
  <p>The principal risk register:</p>
  <table>
    <thead><tr><th>Risk</th><th>Potential impact</th><th>Mitigation (see §4)</th></tr></thead>
    <tbody>
      <tr><td>Chain integrity failure</td><td>Evidence loses probative value</td><td>Single-lock sealed writes; WAL journaling; anchored tip; public verification endpoint; daily backups</td></tr>
      <tr><td>Incorrect verdicts (false ALLOW / false BLOCK)</td><td>Customer harm; missed threats or blocked legitimate activity</td><td>Deterministic scoring; plain-English reasons on every verdict; CHALLENGE band for borderline cases; human-oversight flow</td></tr>
      <tr><td>Availability loss</td><td>Customers cannot govern events</td><td>Stateless integration pattern; automatic restart; daily database backups; customer-side fail-safe guidance in developer docs</td></tr>
      <tr><td>Unauthorised access / key compromise</td><td>Records written under a stolen key</td><td>Bearer-key auth; per-key rate limits; HMAC-signed tokens; no key material in the chain; secrets held in environment, never in code</td></tr>
      <tr><td>Data protection failure</td><td>Personal data exposure</td><td>Data-minimising design throughout — fingerprints not content, hashes not references; see the Data Protection Statement (MC-POL-002)</td></tr>
      <tr><td>Overclaim / misdescription of capability</td><td>Customers rely on protections that do not exist</td><td>Honest-limits statements on every product page, in the whitepaper, and sealed into our own chain; deliberate refusal to claim correctness-proving or compliance-conferring capability</td></tr>
      <tr><td>Single-operator continuity</td><td>Maintenance interruption</td><td>Self-contained stdlib architecture; sovereign engine option gives customers independence; documented codebase; daily backups; see §7</td></tr>
    </tbody>
  </table>

  <h2><span class="n">4.</span>Risk mitigation by design</h2>
  <p>The platform's primary risk controls are architectural rather than procedural — chosen so that safety does not depend on anyone remembering to follow a process:</p>
  <ul>
    <li><b>Determinism.</b> The scoring engine contains no model-layer randomness: identical inputs produce identical verdicts, always. Behaviour is therefore testable, reproducible and explainable — the precondition for every other control.</li>
    <li><b>Tamper-evidence over trust.</b> Every decision, grant and verification is sealed into an append-only SHA-256 chain whose integrity anyone can verify externally. The operator (including the Founder) cannot rewrite history undetected. Risk of internal falsification is engineered out rather than policied away.</li>
    <li><b>Gapless receipts.</b> Sequence numbers issued in the same transaction as each seal make record omission detectable — closing the gap that tamper-evidence alone leaves open.</li>
    <li><b>Human oversight built in.</b> Borderline verdicts return CHALLENGE with a hosted resolution flow; delegated-authority tokens make the overseeing human's mandate itself a sealed, checkable record (Article 14 alignment).</li>
    <li><b>Data minimisation.</b> Content is fingerprinted client-side; KYC references are stored only as hashes; Guardian never stores message content. The lowest-risk data is the data never held.</li>
    <li><b>Stated limits.</b> Every capability is published alongside what it does not do. Overclaim is treated as a platform risk equal in severity to a technical failure, because customers make decisions based on our descriptions.</li>
  </ul>

  <h2><span class="n">5.</span>Testing and release management</h2>
  <p>Every release passes, in order: compilation and unit checks on changed components (including, for the delegation layer, explicit negative tests — expired, tampered, wrong-user and over-limit tokens must all escalate correctly); deployment to the production environment via version-controlled GitHub-to-Railway pipeline, so every deployed state is attributable to a commit; and post-deployment verification, including chain-integrity confirmation via the public endpoint and a live governed event to confirm end-to-end behaviour. A release is not considered complete until the chain verifies green after it.</p>

  <h2><span class="n">6.</span>Monitoring and incident response</h2>
  <p>Live monitoring includes platform-level request/error metrics (hosting dashboard), per-customer visibility via the authenticated pulse and coverage endpoints, and automatic e-mail alerts to account holders when the engine blocks on their traffic. The public verification endpoint acts as a standing, continuous integrity test that anyone may run.</p>
  <p>On any suspected integrity, security or availability incident: the affected component is isolated or the platform paused; the chain is verified to establish the exact boundary of any impact (tampering localises to a block index by design); affected customers are informed with the sealed evidence of what occurred; the fix is deployed through the standard release path; and the incident and remedy are recorded. The chain itself makes honest incident disclosure enforceable — we could not quietly rewrite an incident out of history even if we wished to.</p>

  <h2><span class="n">7.</span>Continuity</h2>
  <p>The platform is deliberately built as a self-contained, dependency-light system (Python standard library, single-file server) to minimise supply-chain and bus-factor risk. Databases are backed up daily. Customers requiring full independence from Monop Content's continuity can deploy the sovereign engine inside their own network with offline licence validation — their governance does not stop if we do.</p>

  <h2><span class="n">8.</span>Review and change control</h2>
  <p>This policy is reviewed quarterly, and immediately upon any material change to the platform's architecture, data handling or product claims. Each revision is fingerprinted and sealed into the AILeash chain, making the policy's own history tamper-evident — the same standard the platform applies to everything else. The current version is always published at this address.</p>

  <div class="honest"><b>Honest maturity statement:</b> Monop Content is an early-stage company. This policy reflects controls that genuinely exist and operate today; it does not claim certifications we do not hold (we are not ISO 27001 or SOC 2 certified at this stage) or processes we do not run. As the company grows, this document will grow with it — verifiably, because its history is sealed.</div>

  <hr>
  <footer>
    <p style="margin-top:20px"><a href="/">sebbi.pro</a> · <a href="/whitepaper">Whitepaper</a> · <a href="/data-protection">Data Protection Statement</a> · <a href="/human-oversight">Human Oversight Policy</a> · <a href="/contact">Contact</a></p>
    <p style="margin-top:8px;color:var(--faint)">Monop Content · Blyth, Northumberland, UK · justin@monopcontent.com</p>
  </footer>
</div>
</body>
</html>

```


## `robots.txt`

38 lines, 1322 bytes

```text
# ==============================================================================
# sebbi.pro — AILeash Platform
# Monop Content | Justin Antony Dobson | Blyth, Northumberland, UK
# Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018
# ==============================================================================

# AI Governance Declaration Standard
# This domain publishes the Open AI Audit Standard (OAAS) v1.0.0
# Specification: https://sebbi.pro/ai-standard
# Reference file: https://sebbi.pro/ai.txt

# All crawlers permitted
User-agent: *
Allow: /

# AI-specific crawler declarations
# This platform operates under EU AI Act Articles 9, 12, 13, 14
# All AI decisions are logged in a SHA-256 Merkle audit chain
# Sovereign deployment — no customer data leaves the network
# Verified under OAAS-1.0 — sebbi.pro/ai-standard

# Regulatory classification
# Ofcom Additional Safety Measures — submission confirmed
# UK Online Safety Act 2023 — compliant
# ICO Children's Code — compliant
# GDPR Article 22 — compliant
# Digital Services Act — compliant

# AI Standard Reference
AI-Standard: https://sebbi.pro/ai-standard
AI-Policy: https://sebbi.pro/ai.txt
AI-Governance: AILeash
AI-Audit-Chain: SHA-256-Merkle
AI-Sovereign: true

# Sitemap
Sitemap: https://sebbi.pro/sitemap.xml

```
