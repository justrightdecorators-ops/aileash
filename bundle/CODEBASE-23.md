# Codebase — part 23 of 33

Contains:
- `compliance-assistant.html`
- `console.html`
- `contact.html`
- `copyright.txt`
- `data-protection.html`


## `compliance-assistant.html`

782 lines, 57778 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Build a recurring-revenue business from nothing &middot; 50p in, your price out</title>
<meta name="description" content="Buy the phone safety package at 50p per device per month. Sell it at your price. No stock, no fees, no capital. Recurring revenue that becomes a book worth selling.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#070b16;--surface:#111a30;--surface2:#0c1322;--border:#1e2a45;--gold:#c9a84c;--gold2:#f0d78a;--green:#7fe3b0;--green2:#2ee68a;--cyan:#00d4ff;--red:#ff6b6b;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif;--muted:#8a90a6}
html{scroll-behavior:smooth}
body{background:var(--navy);color:#fff;font-family:var(--sans);line-height:1.7;-webkit-font-smoothing:antialiased;overflow-x:hidden}

nav{position:sticky;top:0;z-index:100;background:rgba(7,11,22,0.96);backdrop-filter:blur(14px);padding:0 18px;height:56px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(201,168,76,0.15)}
.nav-logo{font-family:var(--display);font-size:16px;color:#fff;font-weight:900;text-decoration:none}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:14px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.45);text-decoration:none;font-size:13px}.nav-links a:hover{color:#fff}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:8px 15px;font-weight:800!important;border-radius:6px}

.hero{padding:50px 20px 42px;text-align:center;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% -10%,rgba(201,168,76,0.14),transparent 58%)}
.hero::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,0.4),transparent)}
.hero-in{max-width:800px;margin:0 auto;position:relative}
.kick{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:2.4px;text-transform:uppercase;color:var(--gold);border:1px solid rgba(201,168,76,0.35);background:rgba(201,168,76,0.07);padding:6px 14px;border-radius:100px;margin-bottom:20px}
h1{font-family:var(--display);font-size:clamp(33px,7.6vw,62px);line-height:1.03;font-weight:900;margin-bottom:18px;letter-spacing:-0.5px}
h1 em{font-style:normal;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero-sub{font-size:17px;color:rgba(255,255,255,0.58);line-height:1.72;max-width:590px;margin:0 auto}
.hero-sub b{color:#fff;font-weight:700}
.flow{display:flex;gap:6px;max-width:540px;margin:30px auto 0}
.flow-b{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:11px;padding:15px 8px}
.flow-b.hot{border-color:rgba(127,227,176,0.45);background:rgba(127,227,176,0.06)}
.flow-b .k{font-family:var(--mono);font-size:8px;letter-spacing:1.6px;text-transform:uppercase;color:rgba(255,255,255,0.3);margin-bottom:6px}
.flow-b .v{font-family:var(--display);font-size:clamp(18px,4.4vw,26px);font-weight:900;line-height:1.05}
.c-dim{color:rgba(255,255,255,0.45)}.c-gold{color:var(--gold)}.c-green{color:var(--green)}

section.sec{max-width:880px;margin:0 auto;padding:58px 20px 0}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:2.6px;text-transform:uppercase;color:rgba(201,168,76,0.7);margin-bottom:12px;display:block}
h2{font-family:var(--display);font-size:clamp(27px,5.4vw,42px);font-weight:900;line-height:1.07;margin-bottom:14px;letter-spacing:-0.3px}
h2 em{font-style:normal;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
h2 em.g{background:linear-gradient(100deg,var(--green),var(--green2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:15.5px;color:rgba(255,255,255,0.52);line-height:1.8;max-width:640px;margin-bottom:28px}
.sub b{color:#fff}

.panel{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:22px 19px;margin-bottom:16px}
.ctrl{margin-bottom:20px}.ctrl:last-child{margin-bottom:0}
.ctrl-top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px;gap:12px}
.ctrl-lbl{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
.ctrl-val{font-family:var(--display);font-size:24px;font-weight:900;color:var(--gold);line-height:1;white-space:nowrap}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:7px;border-radius:4px;background:rgba(255,255,255,0.09);outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:30px;height:30px;border-radius:50%;background:linear-gradient(160deg,var(--gold2),var(--gold));cursor:pointer;border:4px solid var(--navy);box-shadow:0 0 0 1px rgba(201,168,76,0.6),0 0 18px rgba(201,168,76,0.3)}
input[type=range]::-moz-range-thumb{width:30px;height:30px;border-radius:50%;background:var(--gold);cursor:pointer;border:4px solid var(--navy)}
.hint{font-family:var(--mono);font-size:9.5px;color:rgba(255,255,255,0.26);margin-top:8px;line-height:1.7}

.graph{background:var(--surface2);border:1px solid var(--border);border-radius:13px;padding:18px 12px 8px;margin-bottom:16px}
.graph-t{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.32);padding-left:4px}
.graph-s{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.22);padding-left:4px;margin-bottom:12px}
svg.chart{width:100%;height:auto;display:block;overflow:visible}
.legend{display:flex;gap:15px;flex-wrap:wrap;padding:11px 4px 3px;font-family:var(--mono);font-size:9px;letter-spacing:1px;color:rgba(255,255,255,0.33)}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px}

.figs{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden;margin-bottom:14px}
.fig{background:var(--surface2);padding:16px 12px;text-align:center}
.fig .k{font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;text-transform:uppercase;color:rgba(255,255,255,0.28);margin-bottom:6px}
.fig .v{font-family:var(--display);font-size:clamp(21px,5.2vw,31px);font-weight:900;line-height:1}
.fig .s{font-family:var(--mono);font-size:8.5px;color:rgba(255,255,255,0.22);margin-top:5px}

.asset{background:linear-gradient(160deg,rgba(201,168,76,0.1),rgba(127,227,176,0.05));border:2px solid rgba(201,168,76,0.3);border-radius:16px;padding:24px 20px;text-align:center;margin-bottom:14px}
.asset .k{font-family:var(--mono);font-size:9.5px;letter-spacing:2.4px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-bottom:10px}
.asset .v{font-family:var(--display);font-size:clamp(38px,10vw,66px);font-weight:900;line-height:1;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.asset .s{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.32);margin-top:11px;line-height:1.7;max-width:430px;margin-left:auto;margin-right:auto}

.rung{display:flex;align-items:center;gap:13px;background:var(--surface2);border:1px solid var(--border);border-radius:11px;padding:13px 15px;margin-bottom:7px}
.rung.hit{border-color:rgba(127,227,176,0.42);background:rgba(127,227,176,0.05)}
.rung.now{border-color:var(--gold);background:rgba(201,168,76,0.09)}
.rung-n{font-family:var(--display);font-size:19px;font-weight:900;color:rgba(255,255,255,0.35);min-width:62px;line-height:1.1}
.rung.hit .rung-n{color:var(--green)}.rung.now .rung-n{color:var(--gold)}
.rung-n small{display:block;font-family:var(--mono);font-size:7.5px;letter-spacing:1.3px;text-transform:uppercase;color:rgba(255,255,255,0.25);font-weight:400;margin-top:3px}
.rung-mid{flex:1;min-width:0}
.rung-mid .t{font-size:14px;font-weight:700;line-height:1.35}
.rung-mid .d{font-size:12.5px;color:rgba(255,255,255,0.42);line-height:1.5;margin-top:2px}
.rung-amt{font-family:var(--display);font-size:18px;font-weight:900;color:var(--green);text-align:right;white-space:nowrap}
.rung-amt small{display:block;font-family:var(--mono);font-size:7.5px;color:rgba(255,255,255,0.25);font-weight:400;letter-spacing:1px;margin-top:3px}

.vs{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden}
.vs-col{background:var(--surface2);padding:23px 19px}
.vs-col.bad h3{color:rgba(255,255,255,0.4)}
.vs-col.good h3{background:linear-gradient(100deg,var(--green),var(--green2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.vs-col h3{font-family:var(--display);font-size:19px;font-weight:900;margin-bottom:14px}
.vs-col li{list-style:none;font-size:13.5px;line-height:1.6;padding:9px 0 9px 20px;position:relative;color:rgba(255,255,255,0.5);border-bottom:1px solid rgba(255,255,255,0.04)}
.vs-col li:last-child{border-bottom:none}
.vs-col li b{color:#fff}
.vs-col.bad li::before{content:'\2715';position:absolute;left:0;color:var(--red);opacity:.7}
.vs-col.good li::before{content:'\2713';position:absolute;left:0;color:var(--green)}

.packs{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.pk{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:19px}
.pk .tag{font-family:var(--mono);font-size:8.5px;letter-spacing:1.5px;text-transform:uppercase;padding:3px 9px;border-radius:4px;display:inline-block;margin-bottom:10px}
.tg-red{color:var(--red);background:rgba(255,107,107,0.09);border:1px solid rgba(255,107,107,0.3)}
.tg-cyan{color:var(--cyan);background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.3)}
.tg-green{color:var(--green);background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.3)}
.pk h3{font-family:var(--display);font-size:19px;font-weight:900;margin-bottom:6px}
.pk .one{font-size:14px;color:rgba(255,255,255,0.72);font-weight:600;margin-bottom:9px}
.pk p{font-size:13.5px;color:rgba(255,255,255,0.47);line-height:1.7}
.pk p b{color:rgba(255,255,255,0.82)}
.say{background:rgba(201,168,76,0.06);border-left:3px solid var(--gold);padding:10px 13px;margin-top:12px;border-radius:0 6px 6px 0}
.say .k{font-family:var(--mono);font-size:8px;letter-spacing:1.5px;text-transform:uppercase;color:var(--gold);margin-bottom:4px}
.say p{font-size:13px;color:rgba(255,255,255,0.65);font-style:italic;margin:0}

.spotlight{background:linear-gradient(150deg,rgba(201,168,76,0.09),rgba(0,212,255,0.04));border:2px solid rgba(201,168,76,0.28);border-radius:16px;padding:26px 22px}
.spotlight h3{font-family:var(--display);font-size:clamp(24px,5vw,34px);font-weight:900;margin-bottom:10px;line-height:1.1}
.spotlight h3 em{font-style:normal;color:var(--gold)}
.spotlight>p{font-size:15px;color:rgba(255,255,255,0.58);line-height:1.75;margin-bottom:18px}
.spotlight>p b{color:#fff}
.sp-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px}
.sp{background:rgba(0,0,0,0.28);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:15px 17px}
.sp .t{font-size:14px;font-weight:700;color:var(--gold);margin-bottom:5px}
.sp p{font-size:13px;color:rgba(255,255,255,0.5);line-height:1.65;margin:0}

.script{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:19px;margin-bottom:10px}
.script-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:11px;flex-wrap:wrap}
.script-h h4{font-family:var(--display);font-size:18px;font-weight:900}
.script-h .who{font-family:var(--mono);font-size:9px;letter-spacing:1.4px;text-transform:uppercase;color:var(--cyan)}
.words{background:rgba(0,0,0,0.35);border:1px solid rgba(0,212,255,0.14);border-radius:8px;padding:14px 16px;font-size:14px;color:rgba(255,255,255,0.75);line-height:1.75;font-style:italic}
.words b{color:var(--gold);font-style:normal}
.script .after{font-size:13px;color:rgba(255,255,255,0.42);line-height:1.65;margin-top:10px}
.script .after b{color:#fff}

.claims{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden}
.cl{background:var(--surface2);padding:21px 18px}
.cl h4{font-family:var(--display);font-size:17px;font-weight:900;margin-bottom:12px}
.cl.y h4{color:var(--green)}.cl.n h4{color:var(--red)}
.cl li{list-style:none;font-size:13.5px;line-height:1.6;padding:8px 0 8px 21px;position:relative;color:rgba(255,255,255,0.52);border-bottom:1px solid rgba(255,255,255,0.04)}
.cl li:last-child{border-bottom:none}
.cl.y li::before{content:'\2713';position:absolute;left:0;color:var(--green);font-weight:700}
.cl.n li::before{content:'\2715';position:absolute;left:0;color:var(--red);font-weight:700}

.note{border-radius:10px;padding:14px 18px;font-size:13.5px;line-height:1.75;margin-top:14px}
.note-cyan{background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.22);color:rgba(255,255,255,0.58)}
.note-cyan b{color:var(--cyan)}
.note-red{background:rgba(255,107,107,0.05);border:1px solid rgba(255,107,107,0.24);color:rgba(255,255,255,0.58)}
.note-red b{color:var(--red)}
.note-gold{background:rgba(201,168,76,0.05);border:1px solid rgba(201,168,76,0.28);color:rgba(255,255,255,0.58)}
.note-gold b{color:var(--gold)}

/* SIGNUP */
.signup{background:linear-gradient(160deg,rgba(201,168,76,0.08),rgba(127,227,176,0.04));border:2px solid rgba(201,168,76,0.3);border-radius:16px;padding:28px 22px}
.signup h3{font-family:var(--display);font-size:clamp(25px,5.4vw,36px);font-weight:900;margin-bottom:8px;line-height:1.1}
.signup>p{font-size:14.5px;color:rgba(255,255,255,0.52);line-height:1.7;margin-bottom:22px}
.fg{margin-bottom:11px}
.fg label{display:block;font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.3);letter-spacing:1.8px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:rgba(255,255,255,0.05);border:2px solid rgba(255,255,255,0.09);color:#fff;padding:13px 14px;font-size:15px;font-family:var(--sans);outline:none;border-radius:7px}
.fg input:focus,.fg select:focus{border-color:var(--gold)}
.fg input::placeholder{color:rgba(255,255,255,0.2)}
.fg select option{background:var(--navy)}
.fg2{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.btn-full{width:100%;padding:16px;font-size:16px;font-weight:800;border-radius:8px;border:none;cursor:pointer;font-family:var(--sans);background:linear-gradient(140deg,var(--gold2),var(--gold));color:var(--navy);margin-top:8px;transition:all .2s}
.btn-full:hover{transform:translateY(-2px)}
.btn-full:disabled{opacity:.5;transform:none}
.err{display:none;color:var(--red);font-family:var(--mono);font-size:11.5px;margin-top:11px;padding:11px 13px;background:rgba(255,107,107,0.08);border-radius:7px;border:1px solid rgba(255,107,107,0.22);line-height:1.6}
.err.show{display:block}
.got{display:none;margin-top:20px;background:rgba(0,0,0,0.35);border:1px solid rgba(201,168,76,0.25);border-radius:12px;padding:20px}
.got.show{display:block}
.got-k{font-family:var(--mono);font-size:8.5px;letter-spacing:1.8px;color:var(--gold);text-transform:uppercase;margin-bottom:7px}
.got-v{font-family:var(--mono);font-size:12px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.4);padding:11px 13px;border-radius:6px;margin-bottom:16px;line-height:1.6}
.got-code{font-family:var(--display);font-size:clamp(26px,7vw,38px);font-weight:900;color:var(--green);letter-spacing:2px;margin:4px 0 8px;word-break:break-all}
.cpy{background:rgba(0,212,255,0.09);border:1px solid rgba(0,212,255,0.25);color:var(--cyan);padding:10px 18px;border-radius:6px;font-family:var(--mono);font-size:10px;cursor:pointer;letter-spacing:1.4px;text-transform:uppercase;margin-top:6px}
.next{margin-top:18px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.08);font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.75}
.next b{color:#fff}

.faq{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;overflow:hidden}
.faq-q{padding:15px 18px;font-size:14.5px;font-weight:600;cursor:pointer;display:flex;justify-content:space-between;gap:14px;align-items:center}
.faq-q::after{content:'+';font-family:var(--mono);color:var(--gold);font-size:18px;flex-shrink:0}
.faq.open .faq-q::after{content:'\2013'}
.faq-a{display:none;padding:0 18px 16px;font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.75}
.faq.open .faq-a{display:block}
.faq-a b{color:#fff}

.honest{max-width:880px;margin:0 auto;padding:44px 20px 50px}
.honest-box{border:1px solid rgba(201,168,76,0.28);background:rgba(201,168,76,0.04);border-radius:11px;padding:19px 21px;font-size:13.5px;color:var(--muted);line-height:1.8}
.honest-box b{color:var(--gold)}

footer{background:rgba(0,0,0,0.45);padding:30px 20px;border-top:1px solid rgba(255,255,255,0.05);text-align:center}
.fl{display:flex;gap:17px;flex-wrap:wrap;justify-content:center;margin-bottom:12px}
.fl a{color:rgba(255,255,255,0.35);text-decoration:none;font-size:12.5px}.fl a:hover{color:#fff}
.fc{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.22);line-height:1.85;max-width:620px;margin:0 auto}

@media(max-width:740px){
  .nav-links a:not(.nav-cta){display:none}
  .packs,.vs,.claims,.sp-grid,.fg2{grid-template-columns:1fr}
  .rung{padding:11px 12px;gap:9px}
  .rung-n{min-width:52px;font-size:16px}
  .rung-amt{font-size:15px}
  .rung-mid .t{font-size:13px}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">Monop <span>Content</span></a>
  <div class="nav-links">
    <a href="#numbers">The numbers</a>
    <a href="#product">The product</a>
    <a href="#words">The words</a>
    <a href="#signup" class="nav-cta">Start free</a>
  </div>
</nav>

<section class="hero">
  <div class="hero-in">
    <span class="kick">No capital &middot; no stock &middot; no fees &middot; start today</span>
    <h1>Don't resell a product.<br><em>Build your own.</em></h1>
    <p class="hero-sub">You buy the engine at <b>50p per device per month</b>. Then you decide what it is. Child safety for parents. Endpoint monitoring for a call centre. Driver checks for a haulage firm. <b>You write the rules, you name the product, you set the price</b> &mdash; and every customer pays you again next month whether you worked or not.</p>
    <div class="flow">
      <div class="flow-b"><div class="k">Your cost</div><div class="v c-dim">50p</div></div>
      <div class="flow-b"><div class="k">Your price</div><div class="v c-gold">&pound;4.50</div></div>
      <div class="flow-b hot"><div class="k">Your margin</div><div class="v c-green">&pound;4.00</div></div>
    </div>
  </div>
</section>

<!-- ========== NUMBERS ========== -->
<section class="sec" id="numbers">
  <span class="eyebrow">01 &middot; Run it like a business</span>
  <h2>Not a wage.<br>A <em>book of revenue.</em></h2>
  <p class="sub">Forget how much you make this month. The question a businessman asks is what the whole thing is worth in three years. Set how many customers you can add each month and what you charge them &mdash; <b>the graph stacks it up, because last month's customers are still paying.</b></p>

  <div class="panel">
    <div class="ctrl">
      <div class="ctrl-top"><span class="ctrl-lbl">New devices you add each month</span><span class="ctrl-val" id="v-add">25</span></div>
      <input type="range" id="s-add" min="0" max="100" value="42" oninput="draw()">
      <div class="hint">Not total &mdash; new ones per month. Five is a slow start. Fifty means you're working at it.</div>
    </div>
    <div class="ctrl">
      <div class="ctrl-top"><span class="ctrl-lbl">Your price per device, per month</span><span class="ctrl-val" id="v-price">&pound;4.50</span></div>
      <input type="range" id="s-price" min="60" max="2000" value="450" step="10" oninput="draw()">
      <div class="hint">Your market, your price, your currency. We take 50p of it and nothing else.</div>
    </div>
    <div class="ctrl">
      <div class="ctrl-top"><span class="ctrl-lbl">Customers who stay each month</span><span class="ctrl-val" id="v-keep">97%</span></div>
      <input type="range" id="s-keep" min="85" max="100" value="97" oninput="draw()">
      <div class="hint">Nobody keeps everyone. 97% means three in every hundred leave each month &mdash; normal for a consumer subscription, and the number your buyer will ask for.</div>
    </div>
  </div>

  <div class="graph">
    <div class="graph-t">Monthly margin, three years out</div>
    <div class="graph-s" id="g-sub">&nbsp;</div>
    <svg class="chart" id="chart" viewBox="0 0 340 170" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monthly margin growing over 36 months"></svg>
    <div class="legend">
      <span><i style="background:var(--green)"></i>Your margin</span>
      <span><i style="background:#2a3550"></i>Our 50p</span>
    </div>
  </div>

  <div class="figs">
    <div class="fig"><div class="k">Month 12 margin</div><div class="v c-green" id="f-12">&pound;0</div><div class="s">per month</div></div>
    <div class="fig"><div class="k">Month 36 margin</div><div class="v c-green" id="f-36">&pound;0</div><div class="s">per month</div></div>
    <div class="fig"><div class="k">Devices by month 36</div><div class="v c-dim" id="f-dev">0</div><div class="s">all still paying</div></div>
    <div class="fig"><div class="k">Earned over 3 years</div><div class="v" style="color:var(--cyan)" id="f-tot">&pound;0</div><div class="s">cumulative</div></div>
  </div>

  <div class="asset">
    <div class="k">What the book itself is worth by year three</div>
    <div class="v" id="f-val">&pound;0</div>
    <div class="s">Recurring-revenue businesses typically change hands at somewhere around 2&ndash;4&times; annual revenue, depending on churn and how much of it depends on you personally. This is the middle of that range on your own numbers &mdash; an illustration, not a valuation.</div>
  </div>

  <div class="note note-cyan" id="reality">&nbsp;</div>
</section>

<!-- ========== LADDER ========== -->
<section class="sec">
  <span class="eyebrow">02 &middot; The climb</span>
  <h2>It starts at <em class="g">ten devices.</em></h2>
  <p class="sub">Every rung at the price you just set. The first takes an afternoon. Every one after is the same conversation again.</p>
  <div id="ladder"></div>
  <div class="note note-gold"><b>The bit people miss:</b> a job pays you once for the hour you worked. Every device you sign up pays you again next month, and the month after, while you're asleep or out signing up the next one. <b>Ten new customers a month isn't ten customers &mdash; by December it's a hundred and twenty, all still paying.</b></div>
</section>

<!-- ========== VS ========== -->
<section class="sec">
  <span class="eyebrow">03 &middot; Why this and not the other stuff</span>
  <h2>You've seen the<br>dropshipping <em>adverts.</em></h2>
  <p class="sub">The honest comparison, including the part that's harder here.</p>
  <div class="vs">
    <div class="vs-col bad">
      <h3>Flipping products</h3>
      <li>Paid <b>once</b>. Then back to zero next month.</li>
      <li>Someone always undercuts you. Margins die.</li>
      <li>Capital up front on stock or ads before a penny comes back.</li>
      <li>Returns, shipping, customs, angry customers.</li>
      <li>You can't sell the business. There isn't one.</li>
      <li>Nobody's life is better because you sold it.</li>
    </div>
    <div class="vs-col good">
      <h3>This</h3>
      <li>Paid <b>every month</b>, for as long as they keep it.</li>
      <li>Your cost is fixed at 50p and doesn't rise as you grow.</li>
      <li><b>No capital.</b> No stock, no fee, no minimum.</li>
      <li>No shipping, no returns, no warehouse. It's software.</li>
      <li><b>A book of subscriptions is an asset you can sell.</b></li>
      <li>Harder to sell than a phone case &mdash; you have to explain it.</li>
    </div>
  </div>
</section>

<!-- ========== PRODUCT ========== -->
<section class="sec" id="product">
  <span class="eyebrow">04 &middot; What they get for the money</span>
  <h2>Three things<br>on the <em>phone itself.</em></h2>
  <p class="sub">Each has the exact sentence to use. Nick them word for word &mdash; they're written to be said out loud.</p>

  <div class="packs">
    <div class="pk">
      <span class="tag tg-red">Guardian</span>
      <h3>Child protection</h3>
      <p class="one">Spots the patterns that come before harm.</p>
      <p>Watches for known warning signs of grooming &mdash; pushing for secrecy, isolating a child, moving them to a private chat &mdash; and tells the parent. <b>The messages are never stored</b>, only a fingerprint. What is kept is sealed, so it can't be edited later and it means something to a school or the police.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;Your kid's phone tells you when something starts going wrong &mdash; without you having to read their messages.&rdquo;</p></div>
    </div>
    <div class="pk">
      <span class="tag tg-cyan">Sentinel</span>
      <h3>Fraud alarm</h3>
      <p class="one">Catches it during, not on the statement.</p>
      <p>Watches speed and pattern &mdash; a run of login attempts, a burst of payments, the account surfacing in another country minutes after the last one. Classic takeover signals. Flags them live and <b>seals the evidence</b>, so there's something real to show the bank.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;When someone tries to get into your account, you find out while it's happening.&rdquo;</p></div>
    </div>
    <div class="pk">
      <span class="tag tg-green">Sebdog</span>
      <h3>It runs on the phone</h3>
      <p class="one">Not on our computers. Theirs.</p>
      <p>The engine sits on the device itself, so their data doesn't have to leave it to be protected. <b>No round trip, nobody in the middle.</b> Businesses pay serious money for this as an on-site product. Here it's part of the package.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;It protects you without sending your life to somebody else's computer.&rdquo;</p></div>
    </div>
    <div class="pk">
      <span class="tag tg-green">The proof layer</span>
      <h3>All of it, sealed</h3>
      <p class="one">A record nobody can rewrite &mdash; us included.</p>
      <p>Every alert is written into a chain where each record is locked to the one before, so altering anything past visibly breaks it. <b>That's what turns an alert into evidence</b> rather than a screenshot somebody could have faked.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;If it happened, you can prove it happened.&rdquo;</p></div>
    </div>
  </div>
</section>

<!-- ========== SIGNAL PACKS ========== -->
<section class="sec">
  <span class="eyebrow">05 &middot; The part that makes you a company</span>
  <div class="spotlight">
    <h3>Signal Packs &mdash;<br>your product, <em>not ours.</em></h3>
    <p>Here's what you're really buying, and it isn't a child-safety app. The engine watches events on a device, scores them against <b>a set of rules somebody wrote</b>, and seals the result so it can't be altered afterwards. Guardian is just one set of rules. <b>A Signal Pack is you writing your own set</b> &mdash; and the moment you do, it stops being our product and starts being yours.</p>
    <div class="sp-grid">
      <div class="sp"><div class="t">You define what's risky</div><p>Not us. You decide what the engine watches for and what it does about it. Same engine, completely different product.</p></div>
      <div class="sp"><div class="t">You name it and brand it</div><p>Your product name, your logo, your pricing page. Your customers never need to hear of us.</p></div>
      <div class="sp"><div class="t">One pack, sold a thousand times</div><p>Write it once for a market you understand, then sell that same pack to every firm in that market. <b>That's a product line, not a side hustle.</b></p></div>
      <div class="sp"><div class="t">Different packs, different prices</div><p>A parent pays &pound;4. A call centre pays &pound;12 a seat for the same engine with different rules and a sealed audit trail.</p></div>
    </div>
    <div class="note note-gold" style="margin-top:16px"><b>And the churn angle:</b> a customer who has helped shape their own pack does not cancel in month three. Churn is the single number that decides what your book is worth &mdash; <b>every point of it you avoid raises the sale price of the whole business.</b></div>
  </div>

  <div class="note note-cyan"><b>Be straight about the boundary:</b> the engine works on the signals it can actually see on a device &mdash; patterns, timing, addresses, activity. A Signal Pack decides what to do with those signals. <b>It is a rules-and-evidence layer, not magic</b>, and you'll sell far more of it by telling a buyer exactly what it watches than by implying it watches everything.</div>

  <div class="spotlight" style="margin-top:18px">
    <h3>Twenty packs are <em>already written.</em></h3>
    <p>You don't have to start from a blank page. There is an open library of packs at <b>sebbi.pro/packs.html</b> &mdash; legal review, clinical summarisation, support triage, coding agents, security operations, public sector correspondence. Open any of them, read every rule and the reason it exists, and <b>fork it into your own name in one tap.</b></p>
    <div class="sp-grid">
      <div class="sp"><div class="t">Free to read, free to publish</div><p>No account, no key, no card. Writing a pack and putting it in the library costs nothing and never will.</p></div>
      <div class="sp"><div class="t">Publishing proves it's yours</div><p>The moment you publish, the pack's fingerprint is sealed into the chain with the date. If somebody copies your work later, <b>the record already says who wrote it first</b> &mdash; including against us.</p></div>
      <div class="sp"><div class="t">Fork the closest one</div><p>Find the pack nearest to your market, disagree with its thresholds, change them, publish yours. The parent is recorded, so the lineage is visible rather than argued about.</p></div>
      <div class="sp"><div class="t">Running it needs the engine</div><p>This is the bit that pays you. A pack on its own is a text file &mdash; it decides nothing and produces no evidence. <b>Every person who wants to actually run your pack needs a device on the engine</b>, and that's your 50p.</p></div>
    </div>
    <div class="note note-gold" style="margin-top:16px"><b>Why this matters to your book:</b> a pack you wrote and published, with your name sealed on it, is an asset you own outright. <b>Write one for a market you understand and it can be sold to every firm in that market</b> &mdash; and every one of them arrives at the engine to run it.</div>
  </div>

  <p class="sub" style="margin-top:18px"><a href="/packs.html" style="color:#c9a84c">Open the library &rarr;</a></p>
</section>

<!-- ========== MARKETS ========== -->
<section class="sec">
  <span class="eyebrow">06 &middot; Pick your market</span>
  <h2>Same 50p.<br>Seven different <em>businesses.</em></h2>
  <p class="sub">Every one of these is the same engine at the same cost to you. The only thing that changes is the pack you write and the price you charge. <b>Pick the market you already understand</b> &mdash; the one where you know how people talk.</p>

  <div class="packs">
    <div class="pk">
      <span class="tag tg-red">Consumer</span>
      <h3>Parents</h3>
      <p class="one">The easiest first sale you'll ever make.</p>
      <p>Grooming warning signs, sealed alerts, rules the parent sets. <b>Sell it at &pound;4&ndash;&pound;6 a month.</b> Low price, huge market, and the referrals do the work &mdash; parents talk to other parents about exactly this.</p>
    </div>
    <div class="pk">
      <span class="tag tg-cyan">Business</span>
      <h3>Call centres</h3>
      <p class="one">Hundreds of seats in one signature.</p>
      <p>Every agent's endpoint monitored against your pack, every flag sealed into a record a compliance manager can produce later. <b>&pound;8&ndash;&pound;15 a seat.</b> One five-hundred-seat floor is more revenue than two hundred parents, from one meeting.</p>
    </div>
    <div class="pk">
      <span class="tag tg-cyan">Business</span>
      <h3>Any firm with endpoints</h3>
      <p class="one">Laptops, tablets, handsets, kiosks.</p>
      <p>Write a pack for their policy &mdash; what's normal on a company device and what isn't &mdash; and sell it as monitored-with-evidence. <b>&pound;5&ndash;&pound;12 a device.</b> Two hundred devices is a real contract with one invoice.</p>
    </div>
    <div class="pk">
      <span class="tag tg-green">Vertical</span>
      <h3>Care &amp; support agencies</h3>
      <p class="one">Lone workers, vulnerable clients.</p>
      <p>A pack built around visits, hours and unusual activity, with a sealed trail for safeguarding. <b>&pound;8&ndash;&pound;20 a device.</b> They already have the duty; nobody's sold them the evidence layer for it.</p>
    </div>
    <div class="pk">
      <span class="tag tg-green">Vertical</span>
      <h3>Haulage, taxi, delivery</h3>
      <p class="one">Drivers, handsets, disputes.</p>
      <p>Your pack, their fleet, and a record that settles an argument about what happened and when. <b>&pound;5&ndash;&pound;10 a driver.</b> One firm with sixty drivers is &pound;400 a month from a single phone call.</p>
    </div>
    <div class="pk">
      <span class="tag tg-green">Vertical</span>
      <h3>Schools &amp; youth clubs</h3>
      <p class="one">One conversation, a hundred families.</p>
      <p>Sell to the institution, deploy across the families. <b>&pound;3&ndash;&pound;5 a device</b> at volume, one invoice, one relationship to maintain, and a safeguarding lead who wants the evidence trail anyway.</p>
    </div>
  </div>

  <div class="note note-gold"><b>The move nobody makes:</b> don't sell all seven. <b>Pick one, write one really good pack, and go and own that market.</b> The firm that becomes "the endpoint evidence people for care agencies" charges four times what a generalist charges, and sells the business for more at the end because the book is concentrated and defensible.</div>
</section>

<!-- ========== SALES FORCE ========== -->
<section class="sec">
  <span class="eyebrow">07 &middot; Scale past yourself</span>
  <h2>Your book.<br>Your <em>sales force.</em></h2>
  <p class="sub">There's a ceiling on what one person can sell, and it's about five hundred devices. Past that you stop selling and start running something.</p>

  <div class="vs">
    <div class="vs-col good">
      <h3>Put people on it</h3>
      <li>Your cost stays at 50p <b>no matter who made the sale.</b></li>
      <li>Pay a seller commission out of your margin &mdash; at &pound;4.50 there's room for both of you.</li>
      <li>Give them the scripts on this page. They're written to be read out.</li>
      <li>A pack you already wrote means <b>a new seller needs no product knowledge</b>, just the conversation.</li>
      <li>Recurring revenue means their sale keeps paying you long after their commission is spent.</li>
    </div>
    <div class="vs-col good">
      <h3>Or put a machine on it</h3>
      <li>An existing call centre can sell this <b>tomorrow</b>, off a script, into their existing list.</li>
      <li>A phone shop chain adds it at the counter across every branch.</li>
      <li>An IT firm adds one line to invoices clients already pay monthly.</li>
      <li>Any business with a customer list already owns the expensive part &mdash; <b>the customers.</b></li>
      <li>You keep every penny above 50p on all of it.</li>
    </div>
  </div>

  <div class="note note-cyan"><b>The honest maths on hiring:</b> at &pound;4.50 you keep &pound;4. Give a seller &pound;1 per device per month and you still hold &pound;3, on a sale you didn't make. <b>Ten sellers doing twenty a month each is 200 devices a month landing on a book you own.</b> That's the difference between a wage and a company.</div>
</section>

<!-- ========== WORDS ========== -->
<section class="sec" id="words">
  <span class="eyebrow">08 &middot; Your first ten customers</span>
  <h2>You already know<br>every one of <em>them.</em></h2>
  <p class="sub">No adverts, no website, no capital. Ten people who trust you and have kids with phones. <b>Here are the words.</b></p>

  <div class="script">
    <div class="script-h"><h4>The school gate</h4><span class="who">In person &middot; 30 seconds</span></div>
    <div class="words">&ldquo;Can I ask you something daft &mdash; has your lad got a phone yet? Right. So I've started doing something that puts a thing on it that watches for the grooming stuff. It doesn't read his messages, it just tells you if someone starts asking him to keep secrets or move to a private chat. <b>It's a fiver a month.</b> Want me to put it on for you?&rdquo;</div>
    <div class="after"><b>Why it works:</b> you named the fear, killed the objection they were about to make, and gave the price before they had to ask. <b>Say the price.</b> People who hide the price never sell anything.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The group chat</h4><span class="who">WhatsApp &middot; paste it</span></div>
    <div class="words">&ldquo;Bit random. I've started doing a thing for kids' phones &mdash; it watches for the grooming warning signs and tells the parent, without reading their messages. Also catches someone trying to get into your bank. <b>&pound;4.50 a month, cancel whenever.</b> If anyone wants it on their kid's phone give me a shout.&rdquo;</div>
    <div class="after"><b>Why it works:</b> no link, no sales voice, no pressure. In a group of forty parents you'll get three &mdash; and <b>those three tell other parents</b>, because this is the thing parents actually talk about.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The counter</h4><span class="who">If you sell or fix phones</span></div>
    <div class="words">&ldquo;Is this one for yourself or one of the kids? For your daughter &mdash; right. Do you want me to put the safety package on before you go? It watches for grooming and tells you, and flags anyone trying to get into her accounts. <b>Five pound a month and I'll set it up now while you're stood here.</b>&rdquo;</div>
    <div class="after"><b>Why it works:</b> they're already spending and already thinking about their kid. <b>Every handset becomes years of monthly revenue</b> instead of one margin you spend that week.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The business call</h4><span class="who">Clubs &middot; schools &middot; employers</span></div>
    <div class="words">&ldquo;I supply a safety package for phones &mdash; it flags grooming warning signs to a parent and keeps a sealed record you could hand to the police if it came to it. I'm offering it to your families at <b>&pound;4 a month.</b> Could I show you what a parent actually sees? Five minutes.&rdquo;</div>
    <div class="after"><b>Why it works:</b> one club is a hundred families in one conversation. <b>That's £350 a month from a single phone call.</b> Ask for the five minutes, not the sale.</div>
  </div>

  <div class="note note-cyan"><b>The only rule:</b> ask for the money. Nine out of ten people who fail at this never say a price out loud. Say it plainly, then stop talking and let them answer.</div>
</section>

<!-- ========== CLAIMS ========== -->
<section class="sec">
  <span class="eyebrow">09 &middot; How the good ones sell it</span>
  <h2>Never oversell<br>this <em>one thing.</em></h2>
  <p class="sub">Left column is true and provable. Right column is a promise nobody on earth can keep, us included. <b>The left closes better anyway</b> &mdash; people trust the seller who tells them what it can't do.</p>
  <div class="claims">
    <div class="cl y">
      <h4>True. Say it freely.</h4>
      <li>Flags known warning signs of grooming and alerts the parent</li>
      <li>Never stores the messages &mdash; only a fingerprint</li>
      <li>Keeps a sealed record nobody can quietly change later</li>
      <li>Catches fraud patterns as they happen</li>
      <li>Runs on the phone, so their data stays on it</li>
      <li>Something real to hand to a school or the police</li>
    </div>
    <div class="cl n">
      <h4>Never. Not once.</h4>
      <li>&ldquo;Stops grooming&rdquo; or &ldquo;keeps your child safe&rdquo;</li>
      <li>&ldquo;Catches every predator&rdquo; &middot; &ldquo;100% detection&rdquo;</li>
      <li>&ldquo;Unhackable&rdquo; or &ldquo;impossible to get round&rdquo;</li>
      <li>&ldquo;Police approved&rdquo; &middot; &ldquo;certified&rdquo; &middot; &ldquo;government backed&rdquo;</li>
      <li>&ldquo;Makes you compliant&rdquo; with any law</li>
      <li>Anything hinting a parent can stop paying attention</li>
    </div>
  </div>
  <div class="note note-red"><b>Why we're hard on this:</b> it catches known patterns. It cannot catch every clever rewording and no honest product claims otherwise. What it guarantees is the <b>record</b>. <b>A parent promised a wall who got a smoke alarm cancels, tells forty other parents, and takes your book with them.</b> Sell it straight and they stay for years. Overclaim on child safety and your code gets pulled.</div>
</section>

<!-- ========== SIGNUP ========== -->
<section class="sec" id="signup">
  <span class="eyebrow">10 &middot; Start</span>
  <div class="signup">
    <h3>Get your reseller code</h3>
    <p>Free. No fee, no minimum, no contract, no card. You get your code and your key on this page in about ten seconds &mdash; then go and ask the first ten people you know.</p>

    <div class="fg2">
      <div class="fg"><label>First name</label><input type="text" id="i-fn" placeholder="Jane" autocomplete="given-name"></div>
      <div class="fg"><label>Last name</label><input type="text" id="i-ln" placeholder="Smith" autocomplete="family-name"></div>
    </div>
    <div class="fg"><label>Email</label><input type="email" id="i-em" placeholder="you@email.com" autocomplete="email"></div>
    <div class="fg"><label>Phone (optional)</label><input type="tel" id="i-ph" placeholder="07700 000000" autocomplete="tel"></div>
    <div class="fg"><label>Trading name &mdash; or just your own</label><input type="text" id="i-org" placeholder="Jane Smith" autocomplete="organization"></div>
    <div class="fg"><label>Where will you sell it?</label>
      <select id="i-type">
        <option value="personal">People I know &mdash; starting from scratch</option>
        <option value="phoneshop">Phone shop or repair shop</option>
        <option value="school">School, club or parent group</option>
        <option value="it">IT firm or consultancy</option>
        <option value="operator">Network, MVNO or large rollout</option>
        <option value="overseas">Outside the UK</option>
        <option value="other">Something else</option>
      </select>
    </div>
    <div class="fg"><label>What you plan to charge (you can change it any time)</label>
      <select id="i-price">
        <option value="1.50">&pound;1.50 per device</option>
        <option value="2.99">&pound;2.99 per device</option>
        <option value="4.50" selected>&pound;4.50 per device</option>
        <option value="7.00">&pound;7.00 per device</option>
        <option value="10.00">&pound;10.00 per device</option>
        <option value="0">Not decided yet</option>
      </select>
    </div>

    <button class="btn-full" id="btn-go" onclick="signup()">Get my reseller code &rarr;</button>
    <div class="err" id="err"></div>

    <div class="got" id="got">
      <div class="got-k">Your reseller code &mdash; every device signed up with this is yours</div>
      <div class="got-code" id="out-code">&mdash;</div>
      <button class="cpy" onclick="copyIt('out-code')">Copy code</button>
      <div style="height:18px"></div>
      <div class="got-k">Your API key &mdash; save this somewhere safe</div>
      <div class="got-v" id="out-key">&mdash;</div>
      <button class="cpy" onclick="copyIt('out-key')">Copy key</button>
      <div class="next">
        <b>Next three things, in order:</b><br>
        1. Save that key somewhere you won't lose it.<br>
        2. Decide your price and stick to it for the first month.<br>
        3. Use the school gate script on five people today. <b>Not tomorrow.</b>
      </div>
    </div>
  </div>
</section>

<!-- ========== FAQ ========== -->
<section class="sec">
  <span class="eyebrow">11 &middot; Straight answers</span>
  <h2>What everyone<br><em>asks first.</em></h2>
  <div style="margin-top:22px">
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need money to start?</div><div class="faq-a">No. Not a penny. No joining fee, no stock, no minimum, no card. You pay 50p only for devices that are actually live &mdash; and by then your customer has already paid you.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need to be technical?</div><div class="faq-a">No. You get a code, they install it, that's it. If you can set up a phone for somebody, you can do this.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need a company?</div><div class="faq-a">Not to start. But once money's coming in, <b>tell HMRC</b> &mdash; this income is taxable like any other, and registering as a sole trader is free and takes ten minutes online. Don't skip it.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Is this one of them pyramid things?</div><div class="faq-a"><b>No, and here's the test.</b> You don't recruit anybody. You don't earn from other sellers. You don't buy in and there's nothing to buy. You sell a real product to real people who use it, and you pay 50p per device. If a scheme's money comes from recruiting rather than selling, walk away &mdash; this one passes that test.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Can I really sell the business later?</div><div class="faq-a">A book of live subscriptions is a real asset and people do buy them. What it fetches depends on churn, how many customers depend on you personally, and whether your records are clean. <b>Nobody can promise you a buyer</b> &mdash; but unlike flipping products, there's something there to sell.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Can I sell outside the UK?</div><div class="faq-a">Yes, anywhere. Your currency, your price, your language. The 50p stays in sterling, so in plenty of markets the margin is <b>better</b>, not worse.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">What if a customer cancels?</div><div class="faq-a">Billing stops for that device &mdash; your bit and our bit. No penalty, no clawback, no notice period. Your other customers are untouched.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Will you go behind my back to my customers?</div><div class="faq-a">No. You invoice them, you hold the relationship, and their devices are tied to your code permanently. If your ten become ten thousand, that's yours.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">How do I know any of this is real?</div><div class="faq-a">Don't take our word for it. The chain is public, the checking routes need no account, and the verifier runs on your own machine with the internet off. <b>You're meant to check rather than trust.</b> Start at <a href="/whitepaper" style="color:var(--gold)">the whitepaper</a>.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Honestly &mdash; month one?</div><div class="faq-a">Ten to thirty devices if you actually ask everyone you know. At &pound;4.50 that's <b>&pound;40 to &pound;120 a month</b> &mdash; still arriving next January, and the January after. Anyone promising you thousands in week one is lying to you.</div></div>
  </div>
</section>

<div class="honest">
  <div class="honest-box"><b>About the numbers:</b> every figure comes from sliders you set yourself. It's arithmetic, not a forecast, and nobody is promising you customers or income. The valuation figure is an illustration using a common market range for recurring-revenue businesses &mdash; <b>it is not an offer, an appraisal, or a guarantee that anyone will buy your book.</b> What we promise is the price: 50p per active device per month and nothing else.<br><br><b>About the product:</b> sealing proves something happened in a particular form at a particular time and hasn't changed since. It does not prove the contents are true and it does not discharge anybody's legal duties. <b>Guardian is a safeguarding aid and an evidence layer. It supports a parent. It never replaces one.</b></div>
</div>

<footer>
  <div class="fl">
    <a href="/">Home</a>
    <a href="/whitepaper">Whitepaper</a>
    <a href="/developers">Developers</a>
    <a href="/verify">Verify</a>
    <a href="/contact">Contact</a>
  </div>
  <div class="fc">&copy; 2026 Monop Content &middot; Blyth, Northumberland, UK &middot; sebbi.pro<br>Figures are arithmetic on values you enter. Not projections, not guarantees of earnings.</div>
</footer>

<script>
var ADD=[1,2,3,5,8,10,15,20,25,35,50,75,100,150,250,400,650,1000,1600,2500,4000];
var COST=0.50, VAL_MULT=3, HORIZON=36;
var RUNGS=[
  {n:10,    t:'Your phone bill',       d:'One afternoon. Family and neighbours.'},
  {n:50,    t:'The weekly shop',       d:'Your street, your group chat, the school gate.'},
  {n:100,   t:'The car payment',       d:'One club, one class, one small school.'},
  {n:250,   t:'Rent money',            d:'Word of mouth is doing some of it for you.'},
  {n:500,   t:'A full-time wage',      d:'You could pack the day job in around here.'},
  {n:2000,  t:"You're an employer",    d:'Somebody else is making the calls now.'},
  {n:10000, t:'You run a company',     d:'A shop chain, an operator, a region.'}
];

function money(n){
  if(n>=1000000) return '\u00a3'+(n/1000000).toFixed(n>=10000000?1:2)+'m';
  if(n>=100000)  return '\u00a3'+Math.round(n/1000)+'k';
  return '\u00a3'+Math.round(n).toLocaleString('en-GB');
}
function num(n){
  if(n>=1000000) return (n/1000000).toFixed(1)+'m';
  if(n>=10000)   return Math.round(n/1000)+'k';
  return Math.round(n).toLocaleString('en-GB');
}
function addFrom(v){
  var i=Math.round(v/100*(ADD.length-1));
  return ADD[Math.max(0,Math.min(ADD.length-1,i))];
}

function series(add,keep){
  var live=0,out=[];
  for(var m=1;m<=HORIZON;m++){ live=live*keep+add; out.push(live); }
  return out;
}

function draw(){
  var add=addFrom(+document.getElementById('s-add').value);
  var price=(+document.getElementById('s-price').value)/100;
  var keepPct=+document.getElementById('s-keep').value;
  var keep=keepPct/100;
  var per=Math.max(0,price-COST);

  document.getElementById('v-add').textContent=num(add);
  document.getElementById('v-price').textContent='\u00a3'+price.toFixed(2);
  document.getElementById('v-keep').textContent=keepPct+'%';

  var s=series(add,keep);
  var d12=s[11], d36=s[35];
  var total=0; for(var i=0;i<s.length;i++) total+=s[i]*per;
  var annual36=d36*per*12;

  document.getElementById('f-12').textContent=money(d12*per);
  document.getElementById('f-36').textContent=money(d36*per);
  document.getElementById('f-dev').textContent=num(d36);
  document.getElementById('f-tot').textContent=money(total);
  document.getElementById('f-val').textContent=money(annual36*VAL_MULT);
  document.getElementById('g-sub').textContent=num(add)+' new a month \u00b7 '+keepPct+'% stay \u00b7 \u00a3'+price.toFixed(2)+' each';

  var rl=document.getElementById('reality');
  if(per<=0){
    rl.className='note note-red';
    rl.innerHTML='<b>You\u2019d be working for nothing.</b> At \u00a3'+price.toFixed(2)+' you\u2019re at or below the 50p we charge. Even \u00a31.50 leaves you a pound per device per month.';
  } else if(keepPct<=90){
    rl.className='note note-red';
    rl.innerHTML='<b>Churn is eating you alive.</b> At '+keepPct+'% you lose '+(100-keepPct)+' customers in every hundred, every month \u2014 you\u2019d be running to stand still, and no buyer touches a book like that. <b>Get every customer building a Signal Pack in week one</b> and this number is the one that moves.';
  } else {
    rl.className='note note-cyan';
    rl.innerHTML='<b>What this actually says:</b> add '+num(add)+' a month and keep '+keepPct+'% of them, and by month 36 you hold '+num(d36)+' paying devices without ever having a bigger month than your first. <b>The stack does the work, not the heroics.</b>';
  }

  chart(s,per,keep);
  ladder(d36,per);
}

function chart(s,per,keep){
  var W=340,H=170,padL=6,padR=6,padT=14,padB=22;
  var n=s.length, plotH=H-padT-padB, plotW=W-padL-padR;
  var maxTot=s[n-1]*(per+COST); if(maxTot<=0) maxTot=1;
  var bw=plotW/n, gap=bw*0.22;
  var o='';
  o+='<line x1="'+padL+'" y1="'+(H-padB)+'" x2="'+(W-padR)+'" y2="'+(H-padB)+'" stroke="#1e2a45" stroke-width="1"/>';
  for(var i=0;i<n;i++){
    var live=s[i], tot=live*(per+COST);
    var totH=plotH*(tot/maxTot);
    var costH=totH*(COST/(per+COST));
    var keepH=totH-costH;
    var x=padL+i*bw;
    o+='<rect x="'+x.toFixed(1)+'" y="'+(H-padB-costH).toFixed(1)+'" width="'+(bw-gap).toFixed(1)+'" height="'+Math.max(0,costH).toFixed(1)+'" fill="#2a3550"/>';
    o+='<rect x="'+x.toFixed(1)+'" y="'+(H-padB-totH).toFixed(1)+'" width="'+(bw-gap).toFixed(1)+'" height="'+Math.max(0,keepH).toFixed(1)+'" fill="'+(i===11||i===35?'#7fe3b0':'rgba(127,227,176,0.4)')+'"/>';
    if(i===11||i===35){
      o+='<text x="'+(x+(bw-gap)/2).toFixed(1)+'" y="'+(H-padB-totH-4).toFixed(1)+'" text-anchor="middle" font-family="DM Sans,sans-serif" font-size="8.5" font-weight="700" fill="#7fe3b0">'+money(live*per)+'</text>';
    }
  }
  ['1','12','24','36'].forEach(function(m){
    var i=(+m)-1, x=padL+i*bw+(bw-gap)/2;
    o+='<text x="'+x.toFixed(1)+'" y="'+(H-padB+13)+'" text-anchor="middle" font-family="JetBrains Mono,monospace" font-size="8" fill="rgba(255,255,255,0.3)">m'+m+'</text>';
  });
  document.getElementById('chart').innerHTML=o;
}

function ladder(dev,per){
  var marked=false, cls={};
  for(var i=RUNGS.length-1;i>=0;i--){
    var n=RUNGS[i].n;
    cls[n]=(n<=dev&&!marked)?'rung now':(n<=dev?'rung hit':'rung');
    if(n<=dev) marked=true;
  }
  var o='';
  RUNGS.forEach(function(r){
    o+='<div class="'+cls[r.n]+'">'+
      '<div class="rung-n">'+num(r.n)+'<small>devices</small></div>'+
      '<div class="rung-mid"><div class="t">'+r.t+'</div><div class="d">'+r.d+'</div></div>'+
      '<div class="rung-amt">'+money(per*r.n)+'<small>a month</small></div>'+
    '</div>';
  });
  document.getElementById('ladder').innerHTML=o;
}

function tf(el){el.parentElement.classList.toggle('open');}

function copyIt(id){
  var t=document.getElementById(id).textContent.trim();
  if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){alert('Copied');},function(){});}
}

function clean(s){
  // strip anything a phone keyboard may have smuggled in
  return (s||'').replace(/[\u2018\u2019\u201c\u201d]/g,"'").replace(/[^\x20-\x7E]/g,'').trim();
}

async function signup(){
  var fn=clean(document.getElementById('i-fn').value);
  var ln=clean(document.getElementById('i-ln').value);
  var em=clean(document.getElementById('i-em').value);
  var ph=clean(document.getElementById('i-ph').value);
  var org=clean(document.getElementById('i-org').value);
  var type=document.getElementById('i-type').value;
  var price=document.getElementById('i-price').value;
  var err=document.getElementById('err'), got=document.getElementById('got'), btn=document.getElementById('btn-go');
  err.classList.remove('show'); got.classList.remove('show');

  if(!em||em.indexOf('@')<1){err.textContent='Enter a valid email address.';err.classList.add('show');return;}
  if(!fn&&!org){err.textContent='Enter your name or a trading name.';err.classList.add('show');return;}

  var label=org||((fn+' '+ln).trim());
  btn.disabled=true; btn.textContent='Setting you up\u2026';
  try{
    var r=await fetch('/signup',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        email:em, phone:ph, name:(fn+' '+ln).trim(), org:label,
        org_type:'reseller_'+type, product:'guardian-package',
        intended_price:price, devices:1
      })
    });
    var d=await r.json();
    if(d && d.api_key){
      document.getElementById('out-key').textContent=d.api_key;
      document.getElementById('out-code').textContent=d.ref_code||d.referral_code||'(check your email)';
      got.classList.add('show');
      btn.textContent='You\u2019re in \u2713';
      got.scrollIntoView({behavior:'smooth',block:'center'});
    } else {
      err.textContent=(d&&d.error)?d.error:'Something went wrong. Email justrightdecorators@gmail.com and we will set you up by hand.';
      err.classList.add('show'); btn.disabled=false; btn.textContent='Get my reseller code \u2192';
    }
  }catch(e){
    err.textContent='Could not reach the server. Email justrightdecorators@gmail.com and we will set you up by hand.';
    err.classList.add('show'); btn.disabled=false; btn.textContent='Get my reseller code \u2192';
  }
}

draw();
</script>
</body>
</html>

```


## `console.html`

391 lines, 17987 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>Console — sebbi.pro</title>
<style>
  :root{
    --ink:#0a0f1e; --ink2:#10182e; --gold:#c9a84c;
    --ok:#7fe3b0; --err:#ff8a80;
    --line:rgba(201,168,76,0.22);
    --mute:rgba(255,255,255,0.45);
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#fff;font-family:system-ui,-apple-system,sans-serif;
       min-height:100vh;padding:18px 16px 60px;-webkit-text-size-adjust:100%}
  .wrap{max-width:640px;margin:0 auto}

  .brand{font-family:ui-monospace,monospace;font-size:10px;letter-spacing:2.5px;
         text-transform:uppercase;color:rgba(255,255,255,0.32)}
  h1{font-family:Georgia,serif;font-size:25px;color:var(--gold);margin:12px 0 4px}
  .sub{font-size:13px;color:var(--mute);line-height:1.65;margin-bottom:20px}

  .keybar{background:var(--ink2);border:1px solid var(--line);border-radius:10px;
          padding:14px;margin-bottom:18px}
  .keybar label{display:block;font-size:11px;letter-spacing:1.2px;text-transform:uppercase;
                color:var(--mute);margin-bottom:7px}
  .keystate{margin-top:9px;font-family:ui-monospace,monospace;font-size:11px;color:var(--mute)}
  .keystate b{color:var(--gold);font-weight:600}

  input,select,textarea{width:100%;background:#0c1424;border:1px solid var(--line);
    color:#fff;border-radius:7px;padding:11px 12px;font-size:15px;font-family:inherit;outline:none}
  input:focus,select,textarea:focus{border-color:var(--gold)}
  textarea{font-family:ui-monospace,monospace;font-size:13px;line-height:1.55;min-height:74px;resize:vertical}
  select{appearance:none;background-image:linear-gradient(45deg,transparent 50%,var(--gold) 50%),
         linear-gradient(135deg,var(--gold) 50%,transparent 50%);
         background-position:calc(100% - 18px) 20px,calc(100% - 13px) 20px;
         background-size:5px 5px,5px 5px;background-repeat:no-repeat}

  section{border:1px solid var(--line);border-radius:10px;margin-bottom:14px;overflow:hidden}
  section > h2{font-family:Georgia,serif;font-size:16px;color:var(--gold);
    padding:14px 15px;background:var(--ink2);cursor:pointer;display:flex;
    justify-content:space-between;align-items:center;font-weight:400}
  section > h2 .chev{font-size:12px;color:var(--mute)}
  .body{padding:15px;display:none;border-top:1px solid var(--line)}
  section.open .body{display:block}
  section.open > h2 .chev{transform:rotate(180deg)}

  .op{padding:13px 0;border-bottom:1px solid rgba(255,255,255,0.06)}
  .op:last-child{border-bottom:none;padding-bottom:0}
  .op:first-child{padding-top:0}
  .op .name{font-family:ui-monospace,monospace;font-size:12.5px;color:#fff;margin-bottom:3px}
  .op .name span{color:var(--mute)}
  .op .why{font-size:12px;color:var(--mute);line-height:1.6;margin-bottom:9px}
  .row{display:flex;gap:8px;margin-bottom:8px}
  .row > *{flex:1;min-width:0}

  button{background:var(--gold);color:var(--ink);border:none;border-radius:7px;
    padding:12px 14px;font-size:14px;font-weight:800;cursor:pointer;width:100%;
    font-family:inherit;letter-spacing:0.2px}
  button:active{opacity:0.8}
  button:disabled{opacity:0.45}
  button.quiet{background:transparent;color:var(--gold);border:1px solid var(--line);font-weight:600}
  button.danger{background:transparent;color:var(--err);border:1px solid rgba(255,138,128,0.4);font-weight:600}

  #out{position:sticky;bottom:0;margin-top:18px;background:#070c18;
       border:1px solid var(--line);border-radius:10px;overflow:hidden}
  #out .head{display:flex;justify-content:space-between;align-items:center;
    padding:10px 13px;background:var(--ink2);font-family:ui-monospace,monospace;font-size:11px}
  #out .code{font-weight:700;letter-spacing:1px}
  #out .code.g{color:var(--ok)} #out .code.r{color:var(--err)} #out .code.n{color:var(--mute)}
  #out .route{color:var(--mute);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    max-width:62%;text-align:right}
  #out pre{padding:13px;font-family:ui-monospace,monospace;font-size:11.5px;line-height:1.65;
    color:rgba(255,255,255,0.85);white-space:pre-wrap;word-break:break-word;
    max-height:44vh;overflow:auto}
  .foot{margin-top:22px;font-size:11.5px;color:rgba(255,255,255,0.3);line-height:1.8}
  .foot b{color:var(--gold);font-weight:600}
</style>
</head>
<body>
<div class="wrap">

  <div class="brand">sebbi.pro &middot; operator console</div>
  <h1>Console</h1>
  <div class="sub">Keyed routes, run from a phone. The key stays in this tab and is never written to storage — closing the tab forgets it.</div>

  <div class="keybar">
    <label for="key">API key</label>
    <input id="key" type="password" autocomplete="off" autocapitalize="off"
           spellcheck="false" placeholder="Paste your key" oninput="keyState()">
    <div class="keystate" id="keystate">No key set. Every route below will answer <b>401</b>.</div>
  </div>

  <!-- ================= WALLET ================= -->
  <section id="s-wallet" class="open">
    <h2 onclick="toggle('s-wallet')">Wallet <span class="chev">&#9660;</span></h2>
    <div class="body">

      <div class="op">
        <div class="name">GET status <span>· quote · devices · review</span></div>
        <div class="why">Balance, free window, live devices and any open halt.</div>
        <div class="row">
          <button class="quiet" onclick="go('GET','wallet','status')">Status</button>
          <button class="quiet" onclick="go('GET','wallet','quote')">Prices</button>
        </div>
        <div class="row">
          <button class="quiet" onclick="go('GET','wallet','devices')">Devices</button>
          <button class="quiet" onclick="go('GET','wallet','review')">Open halts</button>
        </div>
      </div>

      <div class="op">
        <div class="name">POST charge <span>· the gate</span></div>
        <div class="why">Simulate spends nothing and seals nothing. Charge does both. Send the same receipt twice and the key halts on purpose.</div>
        <input id="w-device" placeholder="device_id, e.g. test-device-01" value="test-device-01">
        <div style="height:8px"></div>
        <input id="w-receipt" placeholder="receipt — 64 hex" autocapitalize="off" spellcheck="false">
        <div style="height:8px"></div>
        <div class="row">
          <button class="quiet" onclick="newReceipt()">New receipt</button>
          <button class="quiet" onclick="chargeCall('simulate')">Simulate</button>
        </div>
        <button onclick="chargeCall('charge')">Charge</button>
      </div>

      <div class="op">
        <div class="name">POST subscribe</div>
        <div class="why">Puts one device on the 30-day plan and takes it off the balance. Renewing early extends the existing expiry.</div>
        <input id="w-subdev" placeholder="device_id" value="test-device-01">
        <div style="height:8px"></div>
        <button onclick="go('POST','wallet','subscribe',{device_id:val('w-subdev')})">Subscribe device</button>
      </div>

      <div class="op">
        <div class="name">POST topup <span>· after a payment clears</span></div>
        <div class="why">1000 millipence = 1 penny, so 50p is 50000. The note is required — put the Stripe payment reference in it so the ledger reconciles.</div>
        <div class="row">
          <input id="w-amount" inputmode="numeric" placeholder="millipence" value="50000">
          <input id="w-note" placeholder="Stripe ref / who authorised">
        </div>
        <button onclick="go('POST','wallet','topup',{millipence:num('w-amount'),note:val('w-note')})">Credit balance</button>
      </div>

      <div class="op">
        <div class="name">GET ledger</div>
        <div class="why">Every charge, topup and subscription, newest first.</div>
        <div class="row">
          <input id="w-limit" inputmode="numeric" placeholder="limit" value="25">
          <button class="quiet" onclick="go('GET','wallet','ledger',{limit:num('w-limit')})">Show ledger</button>
        </div>
      </div>

      <div class="op">
        <div class="name">POST clear <span>· human decision</span></div>
        <div class="why">Releases a halted key. Your name and the reason are sealed into the chain with it.</div>
        <div class="row">
          <input id="w-halt" inputmode="numeric" placeholder="halt_id">
          <input id="w-by" placeholder="cleared_by">
        </div>
        <input id="w-cnote" placeholder="Why this halt is safe to clear">
        <div style="height:8px"></div>
        <button class="danger" onclick="go('POST','wallet','clear',{halt_id:num('w-halt'),cleared_by:val('w-by'),note:val('w-cnote')})">Clear halt</button>
      </div>

    </div>
  </section>

  <!-- ================= ANCHORING ================= -->
  <section id="s-ots">
    <h2 onclick="toggle('s-ots')">Anchoring <span class="chev">&#9660;</span></h2>
    <div class="body">
      <div class="op">
        <div class="name">GET ots/status</div>
        <div class="why">Proof count on disk against stamps recorded. Warns if a volume was lost.</div>
        <button class="quiet" onclick="go('GET','ots','status')">Anchor status</button>
      </div>
      <div class="op">
        <div class="name">POST ots/upgrade</div>
        <div class="why">Fetches each pending proof again from the calendars. Anything stamped more than a few hours ago should come back confirmed with a Bitcoin block height. Until this runs, pending is all you have.</div>
        <button onclick="go('POST','ots','upgrade',{})">Upgrade proofs</button>
      </div>
    </div>
  </section>

  <!-- ================= NETWORK ================= -->
  <section id="s-net">
    <h2 onclick="toggle('s-net')">Network <span class="chev">&#9660;</span></h2>
    <div class="body">
      <div class="op">
        <div class="name">Witness exchange</div>
        <div class="why">Peers, last sync result, and the published roster.</div>
        <div class="row">
          <button class="quiet" onclick="go('GET','mutual','peers')">Peers</button>
          <button class="quiet" onclick="go('GET','mutual','status')">Sync status</button>
        </div>
        <button class="quiet" onclick="go('GET','roster','list')">Roster</button>
      </div>
      <div class="op">
        <div class="name">POST mutual/sync</div>
        <div class="why">Runs a cycle now instead of waiting for the hourly timer.</div>
        <button onclick="go('POST','mutual','sync',{})">Sync now</button>
      </div>
    </div>
  </section>

  <!-- ================= EVIDENCE ================= -->
  <section id="s-ev">
    <h2 onclick="toggle('s-ev')">Evidence <span class="chev">&#9660;</span></h2>
    <div class="body">
      <div class="op">
        <div class="name">POST codebase/seal</div>
        <div class="why">Hashes the deployed source tree into one manifest root and seals it with an authorship declaration. Dated evidence of what you held and when — not proof of ownership.</div>
        <div class="row">
          <input id="c-author" placeholder="author">
          <input id="c-entity" placeholder="entity">
        </div>
        <input id="c-stmt" placeholder="statement">
        <div style="height:8px"></div>
        <button onclick="go('POST','codebase','seal',{author:val('c-author'),entity:val('c-entity'),statement:val('c-stmt')})">Seal codebase</button>
      </div>
      <div class="op">
        <div class="name">POST publish/seal</div>
        <div class="why">Fetches a URL, hashes the exact bytes served, and seals it. Re-sealing builds a revision history.</div>
        <input id="p-url" placeholder="https://sebbi.pro/..." autocapitalize="off" spellcheck="false">
        <div style="height:8px"></div>
        <button onclick="go('POST','publish','seal',{url:val('p-url')})">Seal page</button>
      </div>
      <div class="op">
        <div class="name">Evidence pack</div>
        <div class="why">Preview re-verifies a period without issuing. Issue seals the pack's own digest so the document cannot be edited afterwards.</div>
        <input id="k-period" placeholder="period — 2026-Q3, 2026-08, 2026-08-23" value="2026-08">
        <div style="height:8px"></div>
        <div class="row">
          <button class="quiet" onclick="go('POST','pack','preview',{period:val('k-period')})">Preview</button>
          <button onclick="go('POST','pack','issue',{period:val('k-period')})">Issue</button>
        </div>
      </div>
    </div>
  </section>

  <!-- ================= ANY ROUTE ================= -->
  <section id="s-raw">
    <h2 onclick="toggle('s-raw')">Any route <span class="chev">&#9660;</span></h2>
    <div class="body">
      <div class="op">
        <div class="why">Every module is reachable here without waiting for a form to be built for it. GET sends the JSON as query parameters; POST sends it as the body.</div>
        <div class="row">
          <select id="r-method"><option>GET</option><option>POST</option></select>
          <input id="r-module" placeholder="module" autocapitalize="off" spellcheck="false">
          <input id="r-action" placeholder="action" autocapitalize="off" spellcheck="false">
        </div>
        <textarea id="r-body" placeholder='{}' spellcheck="false">{}</textarea>
        <div style="height:8px"></div>
        <button onclick="raw()">Send</button>
      </div>
    </div>
  </section>

  <div id="out">
    <div class="head">
      <span class="code n" id="out-code">READY</span>
      <span class="route" id="out-route">Nothing sent yet</span>
    </div>
    <pre id="out-body">Set a key, then run a route. Start with Wallet → Status.</pre>
  </div>

  <div class="foot">
    <b>Notes.</b> The key is held in a variable in this tab only — not in localStorage, not in the URL, not in a cookie.<br>
    A 401 means no key or the wrong key. A 404 usually means the router has not been armed since the last deploy — send anything once and try again. A 423 means the wallet has halted the key and a person needs to clear it.
  </div>

</div>

<script>
var apiKey = "";

function val(id){ return document.getElementById(id).value.trim(); }
function num(id){ var n = parseInt(val(id), 10); return isNaN(n) ? null : n; }

function keyState(){
  apiKey = document.getElementById("key").value.trim();
  var el = document.getElementById("keystate");
  if(!apiKey){
    el.innerHTML = "No key set. Every route below will answer <b>401</b>.";
  } else {
    el.innerHTML = "Key set — <b>" + apiKey.length + "</b> characters, ending <b>"
                 + apiKey.slice(-4) + "</b>. Held in this tab only.";
  }
}

function toggle(id){ document.getElementById(id).classList.toggle("open"); }

function newReceipt(){
  var b = new Uint8Array(32);
  crypto.getRandomValues(b);
  var hex = Array.from(b).map(function(x){return x.toString(16).padStart(2,"0");}).join("");
  document.getElementById("w-receipt").value = hex;
  show("n", "receipt generated",
       "A fresh 64-hex value.\n\nCharge it once and it is accepted.\nCharge the same one again and the key halts — that is the replay rule working, not a fault.");
}

function chargeCall(action){
  var r = val("w-receipt");
  if(!r){ newReceipt(); r = val("w-receipt"); }
  go("POST", "wallet", action, { device_id: val("w-device"), receipt: r });
}

function show(cls, route, text){
  document.getElementById("out-code").className = "code " + cls;
  document.getElementById("out-code").textContent =
    (cls === "n" ? "NOTE" : document.getElementById("out-code").textContent);
  document.getElementById("out-route").textContent = route;
  document.getElementById("out-body").textContent = text;
}

function raw(){
  var body = {};
  var txt = val("r-body");
  if(txt){
    try { body = JSON.parse(txt); }
    catch(e){
      document.getElementById("out-code").className = "code r";
      document.getElementById("out-code").textContent = "BAD JSON";
      document.getElementById("out-route").textContent = "not sent";
      document.getElementById("out-body").textContent =
        "The body is not valid JSON, so nothing was sent.\n\n" + e;
      return;
    }
  }
  go(val("r-method"), val("r-module"), val("r-action"), body);
}

async function go(method, module, action, body){
  if(!module || !action) return;
  keyState();

  var path = "/x/" + module + "/" + action;
  var opts = { method: method, headers: {} };

  if(apiKey){
    opts.headers["Authorization"] = "Bearer " + apiKey;
    opts.headers["X-API-Key"] = apiKey;
  }

  if(method === "GET"){
    var qs = [];
    for(var k in (body || {})){
      if(body[k] === null || body[k] === undefined || body[k] === "") continue;
      qs.push(encodeURIComponent(k) + "=" + encodeURIComponent(body[k]));
    }
    if(qs.length) path += "?" + qs.join("&");
  } else {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body || {});
  }

  var codeEl = document.getElementById("out-code");
  codeEl.className = "code n";
  codeEl.textContent = "···";
  document.getElementById("out-route").textContent = method + " " + path;
  document.getElementById("out-body").textContent = "Sending…";

  try {
    var res = await fetch(path, opts);
    var text = await res.text();
    var pretty = text;
    try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch(e){}

    codeEl.className = "code " + (res.ok ? "g" : "r");
    codeEl.textContent = res.status + (res.ok ? " OK" : "");
    document.getElementById("out-body").textContent = pretty;

    if(res.status === 404){
      document.getElementById("out-body").textContent =
        pretty + "\n\n— The router may not have been armed since the last deploy. Send this again.";
    }
  } catch(e){
    codeEl.className = "code r";
    codeEl.textContent = "NO REPLY";
    document.getElementById("out-body").textContent =
      "The request never reached the server.\n\n" + e;
  }
}

keyState();
</script>
</body>
</html>

```


## `contact.html`

134 lines, 7574 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Contact &mdash; Monop Content</title>
<meta name="description" content="Get in touch with Monop Content about AILeash, Guardian, SonicBoom or Sentinel.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--gold:#c9a84c;--green:#00875a;--red:#cc0000;--white:#fff;--off:#f5f7fa;--border:#e2e8f0;--muted:#64748b;--text:#1a202c;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--off);color:var(--text);font-family:var(--sans);min-height:100vh}
nav{background:var(--navy);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between}
.nav-logo{font-family:var(--display);font-size:22px;color:var(--white);font-weight:900;text-decoration:none}.nav-logo span{color:var(--gold)}
.nav-back{color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;font-weight:500}
.nav-back:hover{color:var(--white)}
.page{max-width:600px;margin:0 auto;padding:60px 24px}
.page-label{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;color:var(--gold);margin-bottom:12px}
h1{font-family:var(--display);font-size:clamp(32px,4vw,48px);font-weight:900;color:var(--navy);margin-bottom:12px;line-height:1.1}
h1 em{color:var(--gold);font-style:normal}
.page-sub{font-size:15px;color:var(--muted);line-height:1.75;margin-bottom:40px}
.form-card{background:var(--white);border:1px solid var(--border);border-radius:8px;padding:36px}
.fg{margin-bottom:16px}
.fg label{display:block;font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select,.fg textarea{width:100%;background:var(--off);border:2px solid var(--border);color:var(--text);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus,.fg textarea:focus{border-color:var(--navy)}
.fg input::placeholder,.fg textarea::placeholder{color:#bbb}
.fg textarea{resize:vertical;min-height:120px;line-height:1.6}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.submit-btn{width:100%;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);background:var(--gold);color:var(--navy);margin-top:8px;transition:background .2s}
.submit-btn:hover{background:#e8c96a}
.submit-btn:disabled{opacity:0.5;cursor:not-allowed}
.msg-ok{display:none;color:var(--green);font-family:var(--mono);font-size:11px;margin-top:12px;padding:12px;background:#f0fff8;border-radius:4px;border:1px solid #bbf7d0}
.msg-ok.show{display:block}
.msg-err{display:none;color:var(--red);font-family:var(--mono);font-size:11px;margin-top:12px;padding:12px;background:#fff0f0;border-radius:4px;border:1px solid #ffcccc}
.msg-err.show{display:block}
.direct{margin-top:32px;background:var(--navy);border-radius:8px;padding:28px}
.direct-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:16px}
.direct-item{display:flex;align-items:center;gap:12px;margin-bottom:12px}
.direct-item:last-child{margin:0}
.di-icon{font-size:18px;flex-shrink:0}
.di-text{font-size:14px;color:rgba(255,255,255,0.6)}
.di-text a{color:var(--gold);text-decoration:none}
@media(max-width:600px){
  nav{padding:0 20px}
  .page{padding:40px 16px}
  .form-card{padding:24px}
  .fg-row{grid-template-columns:1fr}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">Monop <span>Content</span></a>
  <a href="/" class="nav-back">&larr; Back to Platform</a>
</nav>

<div class="page">
  <div class="page-label">Get In Touch</div>
  <h1>Send us a <em>message.</em></h1>
  <p class="page-sub">Questions about AILeash, Guardian, SonicBoom or Sentinel. Partnership enquiries. Press. Anything. We reply within 24 hours.</p>

  <div class="form-card">
    <div class="fg-row">
      <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Jane"></div>
      <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
    </div>
    <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
    <div class="fg"><label>Phone (optional)</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
    <div class="fg"><label>Organisation</label><input type="text" id="org" placeholder="Company or platform name"></div>
    <div class="fg"><label>Message</label><textarea id="msg" placeholder="Tell us what you need..."></textarea></div>
    <button class="submit-btn" id="submit-btn" onclick="doSubmit()">Send Message &rarr;</button>
    <div class="msg-ok" id="msg-ok">Message sent. We will reply within 24 hours.</div>
    <div class="msg-err" id="msg-err">Something went wrong. Email justin@monopcontent.com directly.</div>
  </div>

  <div class="direct">
    <div class="direct-label">Or contact directly</div>
    <div class="direct-item">
      <div class="di-icon">&#9993;</div>
      <div class="di-text"><a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a></div>
    </div>
    <div class="direct-item">
      <div class="di-icon">&#128222;</div>
      <div class="di-text"><a href="tel:07908269428">07908 269428</a></div>
    </div>
    <div class="direct-item">
      <div class="di-icon">&#127968;</div>
      <div class="di-text" style="color:rgba(255,255,255,0.4)">Monop Content &middot; Blyth, Northumberland, UK</div>
    </div>
  </div>
</div>

<script>
async function doSubmit(){
  var fn=document.getElementById('fn').value.trim();
  var ln=document.getElementById('ln').value.trim();
  var em=document.getElementById('em').value.trim();
  var ph=document.getElementById('ph').value.trim();
  var org=document.getElementById('org').value.trim();
  var msg=document.getElementById('msg').value.trim();
  var ok=document.getElementById('msg-ok');
  var err=document.getElementById('msg-err');
  var btn=document.getElementById('submit-btn');
  ok.classList.remove('show');err.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!msg){err.textContent='Please enter a message.';err.classList.add('show');return;}
  btn.disabled=true;btn.textContent='Sending...';
  try{
    var r=await fetch('/contact',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name:fn+' '+ln,email:em,phone:ph,org:org,message:msg})});
    var d=await r.json();
    if(d.ok){
      ok.classList.add('show');
      btn.textContent='Sent';
      document.getElementById('fn').value='';
      document.getElementById('ln').value='';
      document.getElementById('em').value='';
      document.getElementById('ph').value='';
      document.getElementById('org').value='';
      document.getElementById('msg').value='';
    }else{
      err.textContent=d.error||'Something went wrong. Email justin@monopcontent.com directly.';
      err.classList.add('show');btn.disabled=false;btn.textContent='Send Message \u2192';
    }
  }catch(e){
    err.classList.add('show');btn.disabled=false;btn.textContent='Send Message \u2192';
  }
}
</script>
</body>
</html>

```


## `copyright.txt`

76 lines, 4491 bytes

```text
# COPYRIGHT.TXT — Copyright and Originality Declaration
# sebbi.pro | Monop Content | Justin Antony Dobson
# Published: June 2026
# Linked to: sebbi.pro/ai.txt | sebbi.pro/dis.txt | sebbi.pro/legal.txt
# Verification: sebbi.pro/api/verify-chain

## Automatic Copyright Notice

Under the Copyright, Designs and Patents Act 1988, copyright in an original work arises automatically upon creation. No registration is required. The following original works are the intellectual property of Justin Antony Dobson, trading as Monop Content, from the date of their creation.

## Original Works Declared

COPYRIGHT-001: OAAS-1.0 — Open AI Audit Standard
The concept, structure, format, and specific wording of the Open AI Audit Standard, including the ai.txt declaration format, is an original work created by Justin Antony Dobson in June 2026. First published at sebbi.pro/ai.txt.

COPYRIGHT-002: dis.txt — Disinformation Protection Standard
The concept, structure, and format of a machine-readable disinformation protection declaration file linked to a cryptographic audit chain is an original work created by Justin Antony Dobson in June 2026. First published at sebbi.pro/dis.txt.

COPYRIGHT-003: legal.txt — Legal Declaration Standard
The concept, structure, and format of a machine-readable legal declaration file linked to a cryptographic audit chain is an original work created by Justin Antony Dobson in June 2026. First published at sebbi.pro/legal.txt.

COPYRIGHT-004: copyright.txt — Copyright Declaration Standard
The concept, structure, and format of this file is an original work created by Justin Antony Dobson in June 2026. First published at sebbi.pro/copyright.txt.

COPYRIGHT-005: AILeash Platform
The AILeash platform including its governance engine, 9-signal weighted scoring system, SHA-256 Merkle audit chain implementation, trust decay model, velocity tracking system, and sovereign deployment architecture is an original work created by Justin Antony Dobson between 2021 and 2026.

COPYRIGHT-006: AILeash Guardian
The AILeash Guardian child safety platform including its grooming detection methodology, parent PWA dashboard, and evidence chain implementation is an original work created by Justin Antony Dobson.

COPYRIGHT-007: SonicBoom
The SonicBoom speed and compliance layer concept and implementation is an original work created by Justin Antony Dobson.

COPYRIGHT-008: AILeash Sentinel
The AILeash Sentinel fraud and anomaly detection platform is an original work created by Justin Antony Dobson.

## What Is Protected

The following are protected by copyright and may not be reproduced, copied, or distributed without permission:

- The specific wording, format, and structure of ai.txt, dis.txt, legal.txt, and copyright.txt
- The source code of server.py, engine.py, and all associated platform files
- The specific implementation of the SHA-256 Merkle chain audit system as built by Justin Antony Dobson
- All HTML, CSS, and JavaScript files published at sebbi.pro
- The OAAS-1.0 standard document published at sebbi.pro/ai-standard

## What Is Not Restricted

Others may:
- Build their own AI compliance products using different code and different approaches
- Implement the general concept of AI audit chains using their own implementations
- Reference OAAS-1.0 provided they attribute authorship to Justin Antony Dobson

Others may not:
- Copy the specific format of these declaration files and present them as their own
- Reproduce the source code of the AILeash platform without permission
- Claim authorship or co-authorship of OAAS-1.0 or any of the above works

## Prior Art Declaration

This file, combined with the SHA-256 Merkle chain at sebbi.pro/api/verify-chain, constitutes a timestamped prior art declaration. The chain provides cryptographic proof of the date and content of all original works listed above.

If any third party seeks to patent, trademark, or claim ownership of concepts substantially similar to those listed above after the publication date of this file, this declaration and the associated Merkle chain evidence will be submitted as prior art.

## Linked Files

ai.txt: https://sebbi.pro/ai.txt
dis.txt: https://sebbi.pro/dis.txt
legal.txt: https://sebbi.pro/legal.txt
copyright.txt: https://sebbi.pro/copyright.txt
Verification: https://sebbi.pro/api/verify-chain

© 2026 Justin Antony Dobson / Monop Content
Blyth, Northumberland, United Kingdom
All rights reserved under the Copyright, Designs and Patents Act 1988.

```


## `data-protection.html`

123 lines, 12310 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data Protection &amp; Sovereignty Statement — Monop Content / AILeash</title>
<meta name="description" content="What data the AILeash platform processes, what it deliberately never holds, where data lives, how long it is kept, and how data subject rights are handled.">
<style>
  :root{--ink:#0a0f1e;--ink2:#111a30;--line:#232d4a;--gold:#c9a84c;--gold-dim:#8a7838;--ok:#7fe3b0;--text:#e8e8f0;--muted:#c2c8dc;--faint:#5a6178}
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
  .green{border:1px solid rgba(127,227,176,.3);background:rgba(127,227,176,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .green b{color:var(--ok)}
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
  <h1>Data Protection &amp;<br><span>Sovereignty Statement</span></h1>
  <div class="meta">
    Document: MC-POL-002 · Version 1.0 · Effective 20 July 2026<br>
    Owner: Justin Dobson, Founder, Monop Content · Review cycle: quarterly, and on any material change to data handling<br>
    Alignment: UK GDPR / EU GDPR · published at sebbi.pro/data-protection
  </div>

  <h2><span class="n">1.</span>The design principle: the safest data is the data we never hold</h2>
  <p>AILeash is built on aggressive data minimisation. Wherever the platform can do its job with a cryptographic fingerprint instead of content, it holds only the fingerprint. This is not a bolted-on privacy feature — it is the architecture:</p>
  <ul>
    <li><b>The notaries</b> fingerprint content in the user's own browser. The document, post or bank details <b>never leave the user's device</b>; only the 64-character SHA-256 hash is transmitted and sealed. A hash cannot be reversed into the content it fingerprints.</li>
    <li><b>KYC sealing</b> stores only the SHA-256 of the verification provider's reference — never the identity document, never the raw reference number, never the personal data the provider examined.</li>
    <li><b>Guardian</b> never stores message content — only fingerprints of flagged exchanges, sufficient to prove later that a specific exchange existed in a specific form.</li>
    <li><b>The decision engine</b> receives only the seven event fields the customer chooses to send. Customers are instructed (in the developer documentation and below) to send pseudonymous identifiers, not names or contact details.</li>
  </ul>

  <h2><span class="n">2.</span>What we process, and why</h2>
  <table>
    <thead><tr><th>Data</th><th>Content</th><th>Purpose · lawful basis</th></tr></thead>
    <tbody>
      <tr><td>Governed events</td><td>user_id (customer-supplied identifier), action label, amount, country code, device_id, two 0–1 risk signals, optional authority token</td><td>Delivering the contracted decision and evidence service · performance of contract</td></tr>
      <tr><td>Sealed chain records</td><td>Event, verdict, reasons, jurisdiction tag, timestamp, hashes</td><td>The tamper-evident evidence record that is the product itself · performance of contract; customers' legitimate interest in verifiable records</td></tr>
      <tr><td>Account data</td><td>E-mail address, hashed API key, plan status, device counts</td><td>Account operation, alerts, billing · performance of contract</td></tr>
      <tr><td>Billing data</td><td>Handled by Stripe; we hold no card numbers</td><td>Payment collection · performance of contract</td></tr>
      <tr><td>Notary seals</td><td>SHA-256 fingerprints; for identity seals marked public, the limited display fields the user chooses to include; masked payment display fields</td><td>The public notarisation service · consent (the user submits the seal)</td></tr>
      <tr><td>Contact messages</td><td>What the sender chooses to write</td><td>Responding · legitimate interest</td></tr>
    </tbody>
  </table>
  <div class="honest"><b>Pseudonymisation is a shared responsibility, stated plainly:</b> the <code style="color:#7fe3b0">user_id</code> and <code style="color:#7fe3b0">device_id</code> fields are supplied by the customer. Our documentation instructs customers to send pseudonymous identifiers (e.g. <i>user_4471</i>), never names, e-mail addresses or other direct identifiers. Where a customer follows this, chain records contain no directly identifying personal data. Customers acting as controllers remain responsible for what they choose to transmit; Monop Content acts as processor for event data processed on customers' instructions.</div>

  <h2><span class="n">3.</span>What we deliberately do not hold</h2>
  <ul>
    <li>No notarised content — documents, posts, messages and bank details are fingerprinted client-side and never transmitted.</li>
    <li>No identity documents and no raw KYC references — hashes only.</li>
    <li>No message content in Guardian — fingerprints only.</li>
    <li>No card or bank account numbers — payments are processed by Stripe; the Payment Notary stores only user-chosen masked display fields.</li>
    <li>No behavioural profiles beyond the per-user trust score the customer's own events generate, held against the customer's pseudonymous identifier.</li>
    <li>No advertising, no analytics resale, no third-party data sharing of any kind. The business model is the platform fee; the data is not the product.</li>
  </ul>

  <h2><span class="n">4.</span>Where data lives, and the sovereign option</h2>
  <p>The hosted platform runs on Railway cloud infrastructure with the database on a persistent encrypted volume; connections are TLS-encrypted in transit; backups are taken daily. Sub-processors are listed in §7. Hosting region details and current sub-processor terms are available on request at justin@monopcontent.com.</p>
  <div class="green"><b>Full data sovereignty is a product option, not a promise:</b> organisations whose data cannot leave their own network can run the sovereign engine entirely on their own hardware — decisions, chain and database inside their building, licence validation fully offline, no phone-home. Under sovereign deployment, Monop Content processes nothing at all.</div>

  <h2><span class="n">5.</span>Retention — and the honest tension with an append-only chain</h2>
  <p>Account and billing data are retained for the life of the account plus the period required by tax and accounting law. Contact messages are retained only as long as needed to respond.</p>
  <p>Chain records require an honest explanation rather than a boilerplate one. The chain is append-only by design — its evidential value exists precisely because records cannot be deleted or altered. This is why the platform is architected so that chain records should contain <b>no directly identifying personal data</b>: fingerprints, pseudonymous identifiers and hashes are sealed; content and identities are not. Where a valid erasure request nonetheless touches sealed data (for example, display fields a user chose to make public on an identity seal), we honour it by erasing the stored display data while the cryptographic fingerprint — which identifies no one — remains in the chain. This preserves both the data subject's rights and the integrity of the record for everyone else.</p>

  <h2><span class="n">6.</span>Data subject rights</h2>
  <p>Requests for access, rectification, erasure, restriction or portability go to <b>justin@monopcontent.com</b> and are answered within one calendar month. For event data processed on a customer's behalf, requests are handled with, and routed via, the customer as controller. UK data subjects may complain to the ICO; EU data subjects to their national supervisory authority.</p>

  <h2><span class="n">7.</span>Sub-processors</h2>
  <table>
    <thead><tr><th>Provider</th><th>Purpose</th><th>Data touched</th></tr></thead>
    <tbody>
      <tr><td>Railway</td><td>Application hosting and database volume</td><td>All hosted-platform data at rest and in transit</td></tr>
      <tr><td>Stripe</td><td>Billing and payment processing</td><td>Billing identity and payment card data (held by Stripe, not by us)</td></tr>
      <tr><td>Brevo</td><td>Transactional e-mail (alerts, receipts, contact)</td><td>E-mail addresses and message content of e-mails sent</td></tr>
    </tbody>
  </table>
  <p>Sub-processors will not be added or changed without this document being updated — and each revision of this document is fingerprinted and sealed into the chain, so its history is tamper-evident.</p>

  <h2><span class="n">8.</span>Security measures, summarised</h2>
  <ul>
    <li>TLS for all connections; secrets held in environment variables, never in code or the repository.</li>
    <li>Bearer-key authentication with per-key rate limits; HMAC-SHA256 signed tokens for challenges, authority and licences.</li>
    <li>Single-lock, write-ahead-journaled database writes; the sealed chain makes any tampering — including by the operator — externally detectable.</li>
    <li>Daily automated backups; deployment exclusively through version-controlled pipeline, so every production state is attributable.</li>
  </ul>

  <div class="honest"><b>Honest maturity statement:</b> Monop Content is an early-stage, single-operator company. This statement describes practices genuinely in operation today. We do not hold ISO 27001 or SOC 2 certification at this stage and will not imply otherwise; what we offer instead, unusually, is a platform whose core integrity claims any prospect can verify from outside before trusting us with anything.</div>

  <hr>
  <footer>
    <p style="margin-top:20px"><a href="/">sebbi.pro</a> · <a href="/risk-policy">Risk Management Policy</a> · <a href="/human-oversight">Human Oversight Policy</a> · <a href="/whitepaper">Whitepaper</a> · <a href="/contact">Contact</a></p>
    <p style="margin-top:8px;color:var(--faint)">Monop Content · Blyth, Northumberland, UK · justin@monopcontent.com</p>
  </footer>
</div>
</body>
</html>

```
