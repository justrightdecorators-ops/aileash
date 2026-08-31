# Codebase — part 20 of 29

Contains:
- `compliance-assistant.html`
- `console.html`
- `contact.html`
- `copyright.txt`
- `data-protection.html`


## `compliance-assistant.html`

533 lines, 39836 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Own the thing everyone needs. 50p in, your price out. &middot; sebbi.pro</title>
<meta name="description" content="Buy the child-safety and fraud package at 50p per phone per month. Sell it at your price. No stock, no fees, no boss. Recurring income that pays you again every month.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#070b16;--surface:#111a30;--surface2:#0c1322;--border:#1e2a45;--gold:#c9a84c;--gold2:#f0d78a;--green:#7fe3b0;--green2:#2ee68a;--cyan:#00d4ff;--red:#ff6b6b;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif;--muted:#8a90a6}
html{scroll-behavior:smooth}
body{background:var(--navy);color:#fff;font-family:var(--sans);line-height:1.7;-webkit-font-smoothing:antialiased;overflow-x:hidden}

nav{position:sticky;top:0;z-index:100;background:rgba(7,11,22,0.96);backdrop-filter:blur(14px);padding:0 20px;height:58px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(201,168,76,0.15)}
.nav-logo{font-family:var(--display);font-size:17px;color:#fff;font-weight:900;text-decoration:none}.nav-logo span{color:var(--gold)}
.nav-links{display:flex;gap:14px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.45);text-decoration:none;font-size:13px}.nav-links a:hover{color:#fff}
.nav-cta{background:var(--gold)!important;color:var(--navy)!important;padding:8px 15px;font-weight:800!important;border-radius:6px}

.hero{padding:52px 20px 44px;text-align:center;position:relative;overflow:hidden}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% -10%,rgba(201,168,76,0.14),transparent 58%)}
.hero::after{content:'';position:absolute;left:0;right:0;bottom:0;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,0.4),transparent)}
.hero-in{max-width:820px;margin:0 auto;position:relative}
.kick{display:inline-block;font-family:var(--mono);font-size:10px;letter-spacing:2.5px;text-transform:uppercase;color:var(--gold);border:1px solid rgba(201,168,76,0.35);background:rgba(201,168,76,0.07);padding:6px 14px;border-radius:100px;margin-bottom:22px}
h1{font-family:var(--display);font-size:clamp(34px,8vw,66px);line-height:1.02;font-weight:900;margin-bottom:20px;letter-spacing:-0.5px}
h1 em{font-style:normal;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.hero-sub{font-size:17.5px;color:rgba(255,255,255,0.58);line-height:1.72;max-width:600px;margin:0 auto}
.hero-sub b{color:#fff;font-weight:700}

.flow{display:flex;gap:6px;max-width:560px;margin:32px auto 0}
.flow-b{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:11px;padding:16px 10px}
.flow-b.hot{border-color:rgba(127,227,176,0.45);background:rgba(127,227,176,0.06)}
.flow-b .k{font-family:var(--mono);font-size:8.5px;letter-spacing:1.8px;text-transform:uppercase;color:rgba(255,255,255,0.3);margin-bottom:7px}
.flow-b .v{font-family:var(--display);font-size:clamp(19px,4.6vw,27px);font-weight:900;line-height:1.05}
.c-dim{color:rgba(255,255,255,0.45)}.c-gold{color:var(--gold)}.c-green{color:var(--green)}

section.sec{max-width:880px;margin:0 auto;padding:60px 20px 0}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:2.8px;text-transform:uppercase;color:rgba(201,168,76,0.7);margin-bottom:13px;display:block}
h2{font-family:var(--display);font-size:clamp(28px,5.6vw,44px);font-weight:900;line-height:1.06;margin-bottom:15px;letter-spacing:-0.3px}
h2 em{font-style:normal;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
h2 em.g{background:linear-gradient(100deg,var(--green),var(--green2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:15.5px;color:rgba(255,255,255,0.52);line-height:1.8;max-width:640px;margin-bottom:30px}
.sub b{color:#fff}

.clock{background:linear-gradient(160deg,rgba(201,168,76,0.09),rgba(127,227,176,0.05));border:2px solid rgba(201,168,76,0.3);border-radius:18px;padding:26px 20px;margin-bottom:18px;text-align:center}
.clock-k{font-family:var(--mono);font-size:9.5px;letter-spacing:2.5px;text-transform:uppercase;color:rgba(255,255,255,0.4);margin-bottom:12px}
.clock-big{font-family:var(--display);font-size:clamp(52px,15vw,104px);font-weight:900;line-height:0.95;background:linear-gradient(100deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.clock-unit{font-family:var(--display);font-size:clamp(18px,4vw,26px);font-weight:900;color:rgba(255,255,255,0.5);margin-top:2px}
.clock-date{font-family:var(--mono);font-size:12px;color:var(--green);letter-spacing:1.5px;margin-top:14px}
.clock-sm{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);margin-top:8px;line-height:1.7;max-width:430px;margin-left:auto;margin-right:auto}

.panel{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:24px 20px;margin-bottom:18px}
.ctrl{margin-bottom:22px}
.ctrl:last-child{margin-bottom:0}
.ctrl-top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px;gap:12px}
.ctrl-lbl{font-family:var(--mono);font-size:9.5px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
.ctrl-val{font-family:var(--display);font-size:25px;font-weight:900;color:var(--gold);line-height:1;white-space:nowrap}
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:7px;border-radius:4px;background:rgba(255,255,255,0.09);outline:none}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:30px;height:30px;border-radius:50%;background:linear-gradient(160deg,var(--gold2),var(--gold));cursor:pointer;border:4px solid var(--navy);box-shadow:0 0 0 1px rgba(201,168,76,0.6),0 0 18px rgba(201,168,76,0.35)}
input[type=range]::-moz-range-thumb{width:30px;height:30px;border-radius:50%;background:var(--gold);cursor:pointer;border:4px solid var(--navy)}
.hint{font-family:var(--mono);font-size:9.5px;color:rgba(255,255,255,0.26);margin-top:8px;line-height:1.7}

.figs{display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden;margin-bottom:16px}
.fig{background:var(--surface2);padding:17px 10px;text-align:center}
.fig .k{font-family:var(--mono);font-size:8.5px;letter-spacing:1.6px;text-transform:uppercase;color:rgba(255,255,255,0.28);margin-bottom:7px}
.fig .v{font-family:var(--display);font-size:clamp(20px,5vw,30px);font-weight:900;line-height:1}
.fig .s{font-family:var(--mono);font-size:8.5px;color:rgba(255,255,255,0.22);margin-top:5px}

.rung{display:flex;align-items:center;gap:14px;background:var(--surface2);border:1px solid var(--border);border-radius:11px;padding:14px 16px;margin-bottom:8px;transition:all .25s}
.rung.hit{border-color:rgba(127,227,176,0.45);background:rgba(127,227,176,0.055)}
.rung.now{border-color:var(--gold);background:rgba(201,168,76,0.09);box-shadow:0 0 24px rgba(201,168,76,0.12)}
.rung-n{font-family:var(--display);font-size:20px;font-weight:900;color:rgba(255,255,255,0.35);min-width:66px;line-height:1.1}
.rung.hit .rung-n{color:var(--green)}
.rung.now .rung-n{color:var(--gold)}
.rung-n small{display:block;font-family:var(--mono);font-size:8px;letter-spacing:1.4px;text-transform:uppercase;color:rgba(255,255,255,0.25);font-weight:400;margin-top:3px}
.rung-mid{flex:1;min-width:0}
.rung-mid .t{font-size:14.5px;font-weight:700;color:#fff;line-height:1.35}
.rung-mid .d{font-size:12.5px;color:rgba(255,255,255,0.42);line-height:1.5;margin-top:2px}
.rung-amt{font-family:var(--display);font-size:19px;font-weight:900;color:var(--green);text-align:right;white-space:nowrap}
.rung-amt small{display:block;font-family:var(--mono);font-size:8px;color:rgba(255,255,255,0.25);font-weight:400;letter-spacing:1px;margin-top:3px}

.vs{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden}
.vs-col{background:var(--surface2);padding:24px 20px}
.vs-col.bad h3{color:rgba(255,255,255,0.4)}
.vs-col.good h3{background:linear-gradient(100deg,var(--green),var(--green2));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.vs-col h3{font-family:var(--display);font-size:20px;font-weight:900;margin-bottom:15px}
.vs-col li{list-style:none;font-size:13.5px;line-height:1.6;padding:9px 0 9px 20px;position:relative;color:rgba(255,255,255,0.5);border-bottom:1px solid rgba(255,255,255,0.04)}
.vs-col li:last-child{border-bottom:none}
.vs-col li b{color:#fff}
.vs-col.bad li::before{content:'\2715';position:absolute;left:0;color:var(--red);opacity:.7}
.vs-col.good li::before{content:'\2713';position:absolute;left:0;color:var(--green)}

.packs{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.pk{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:20px}
.pk .tag{font-family:var(--mono);font-size:8.5px;letter-spacing:1.6px;text-transform:uppercase;padding:3px 9px;border-radius:4px;display:inline-block;margin-bottom:11px}
.tg-red{color:var(--red);background:rgba(255,107,107,0.09);border:1px solid rgba(255,107,107,0.3)}
.tg-cyan{color:var(--cyan);background:rgba(0,212,255,0.08);border:1px solid rgba(0,212,255,0.3)}
.tg-green{color:var(--green);background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.3)}
.tg-gold{color:var(--gold);background:rgba(201,168,76,0.09);border:1px solid rgba(201,168,76,0.32)}
.pk h3{font-family:var(--display);font-size:20px;font-weight:900;margin-bottom:6px}
.pk .one{font-size:14px;color:rgba(255,255,255,0.72);font-weight:600;margin-bottom:10px}
.pk p{font-size:13.5px;color:rgba(255,255,255,0.47);line-height:1.7}
.pk p b{color:rgba(255,255,255,0.82)}
.say{background:rgba(201,168,76,0.06);border-left:3px solid var(--gold);padding:11px 14px;margin-top:13px;border-radius:0 6px 6px 0}
.say .k{font-family:var(--mono);font-size:8px;letter-spacing:1.6px;text-transform:uppercase;color:var(--gold);margin-bottom:5px}
.say p{font-size:13px;color:rgba(255,255,255,0.65);font-style:italic;margin:0}

.script{background:var(--surface);border:1px solid var(--border);border-radius:13px;padding:20px;margin-bottom:11px}
.script-h{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:12px;flex-wrap:wrap}
.script-h h4{font-family:var(--display);font-size:19px;font-weight:900}
.script-h .who{font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--cyan)}
.words{background:rgba(0,0,0,0.35);border:1px solid rgba(0,212,255,0.14);border-radius:8px;padding:15px 17px;font-size:14px;color:rgba(255,255,255,0.75);line-height:1.75;font-style:italic}
.words b{color:var(--gold);font-style:normal}
.script .after{font-size:13px;color:rgba(255,255,255,0.42);line-height:1.65;margin-top:11px}
.script .after b{color:#fff}

.claims{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:rgba(255,255,255,0.05);border-radius:12px;overflow:hidden}
.cl{background:var(--surface2);padding:22px 19px}
.cl h4{font-family:var(--display);font-size:18px;font-weight:900;margin-bottom:13px}
.cl.y h4{color:var(--green)}.cl.n h4{color:var(--red)}
.cl li{list-style:none;font-size:13.5px;line-height:1.6;padding:8px 0 8px 21px;position:relative;color:rgba(255,255,255,0.52);border-bottom:1px solid rgba(255,255,255,0.04)}
.cl li:last-child{border-bottom:none}
.cl.y li::before{content:'\2713';position:absolute;left:0;color:var(--green);font-weight:700}
.cl.n li::before{content:'\2715';position:absolute;left:0;color:var(--red);font-weight:700}

.note{border-radius:10px;padding:15px 19px;font-size:13.5px;line-height:1.75;margin-top:15px}
.note-cyan{background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.22);color:rgba(255,255,255,0.58)}
.note-cyan b{color:var(--cyan)}
.note-red{background:rgba(255,107,107,0.05);border:1px solid rgba(255,107,107,0.24);color:rgba(255,255,255,0.58)}
.note-red b{color:var(--red)}
.note-gold{background:rgba(201,168,76,0.05);border:1px solid rgba(201,168,76,0.28);color:rgba(255,255,255,0.58)}
.note-gold b{color:var(--gold)}

.faq{background:var(--surface);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;overflow:hidden}
.faq-q{padding:15px 19px;font-size:14.5px;font-weight:600;cursor:pointer;display:flex;justify-content:space-between;gap:14px;align-items:center}
.faq-q::after{content:'+';font-family:var(--mono);color:var(--gold);font-size:18px;flex-shrink:0}
.faq.open .faq-q::after{content:'\2013'}
.faq-a{display:none;padding:0 19px 17px;font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.75}
.faq.open .faq-a{display:block}
.faq-a b{color:#fff}

.cta{max-width:880px;margin:0 auto;padding:64px 20px 34px;text-align:center}
.cta p{color:rgba(255,255,255,0.52);font-size:15.5px;margin-bottom:26px;max-width:540px;margin-left:auto;margin-right:auto}
.btn{background:linear-gradient(140deg,var(--gold2),var(--gold));color:var(--navy);padding:17px 34px;border:none;font-family:var(--sans);font-weight:800;font-size:16px;cursor:pointer;text-decoration:none;border-radius:8px;display:inline-block;transition:all .2s;box-shadow:0 6px 26px rgba(201,168,76,0.24)}
.btn:hover{transform:translateY(-2px)}
.btn2{background:transparent;color:rgba(255,255,255,0.55);padding:17px 30px;border:1px solid rgba(255,255,255,0.16);font-weight:600;font-size:15px;text-decoration:none;border-radius:8px;display:inline-block;margin-left:8px}
.btn2:hover{color:#fff;border-color:rgba(255,255,255,0.4)}

.honest{max-width:880px;margin:0 auto;padding:0 20px 54px}
.honest-box{border:1px solid rgba(201,168,76,0.28);background:rgba(201,168,76,0.04);border-radius:11px;padding:19px 22px;font-size:13.5px;color:var(--muted);line-height:1.8}
.honest-box b{color:var(--gold)}

footer{background:rgba(0,0,0,0.45);padding:32px 20px;border-top:1px solid rgba(255,255,255,0.05);text-align:center}
.fl{display:flex;gap:18px;flex-wrap:wrap;justify-content:center;margin-bottom:13px}
.fl a{color:rgba(255,255,255,0.35);text-decoration:none;font-size:12.5px}.fl a:hover{color:#fff}
.fc{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.22);line-height:1.85;max-width:620px;margin:0 auto}

@media(max-width:740px){
  .nav-links a:not(.nav-cta){display:none}
  .packs,.vs,.claims{grid-template-columns:1fr}
  .figs{grid-template-columns:1fr 1fr}
  .btn2{margin-left:0;margin-top:10px;display:block}
  .rung{padding:12px 13px;gap:10px}
  .rung-n{min-width:54px;font-size:17px}
  .rung-amt{font-size:16px}
  .rung-mid .t{font-size:13.5px}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">Monop <span>Content</span></a>
  <div class="nav-links">
    <a href="#clock">The numbers</a>
    <a href="#package">What you sell</a>
    <a href="#scripts">The words</a>
    <a href="#start" class="nav-cta">Start free</a>
  </div>
</nav>

<section class="hero">
  <div class="hero-in">
    <span class="kick">No stock &middot; no fees &middot; no boss &middot; start today</span>
    <h1>Everyone's flogging<br>somebody else's tat.<br><em>Sell something that matters.</em></h1>
    <p class="hero-sub">You buy a child-safety and fraud package for <b>50p per phone per month</b>. You sell it for whatever you like. The difference is yours, and it lands again next month whether you worked that month or not. <b>No stock. No shipping. Nothing up front.</b> One phone or a hundred thousand.</p>

    <div class="flow">
      <div class="flow-b"><div class="k">You pay</div><div class="v c-dim">50p</div></div>
      <div class="flow-b"><div class="k">You charge</div><div class="v c-gold">&pound;4.50</div></div>
      <div class="flow-b hot"><div class="k">You keep</div><div class="v c-green">&pound;4.00</div></div>
    </div>
  </div>
</section>

<section class="sec" id="clock">
  <span class="eyebrow">01 &middot; Your number</span>
  <h2>How long until you've<br>earned <em>a million?</em></h2>
  <p class="sub">Set your price. Set how many phones you get it onto. The clock does the rest. <b>It's arithmetic, not a promise</b> &mdash; nobody's handing you the phones, you go and get them. But this is what the maths says when you do.</p>

  <div class="clock">
    <div class="clock-k">You pass &pound;1,000,000 earned in</div>
    <div class="clock-big" id="c-num">25</div>
    <div class="clock-unit" id="c-unit">months</div>
    <div class="clock-date" id="c-date">&nbsp;</div>
    <div class="clock-sm">Total earned over time, before tax and your own costs. Not a lump sum and not net worth &mdash; anyone telling you different is selling you something.</div>
  </div>

  <div class="panel">
    <div class="ctrl">
      <div class="ctrl-top"><span class="ctrl-lbl">Phones you get it onto</span><span class="ctrl-val" id="v-dev">10,000</span></div>
      <input type="range" id="s-dev" min="0" max="100" value="76" oninput="draw()">
      <div class="hint">Start where you actually are. Ten is a real number. So is fifty.</div>
    </div>
    <div class="ctrl">
      <div class="ctrl-top"><span class="ctrl-lbl">What you charge per phone, per month</span><span class="ctrl-val" id="v-price">&pound;4.50</span></div>
      <input type="range" id="s-price" min="60" max="2000" value="450" step="10" oninput="draw()">
      <div class="hint">Your market, your price, your currency. Parents pay this for one coffee a month.</div>
    </div>
  </div>

  <div class="figs">
    <div class="fig"><div class="k">You keep</div><div class="v c-green" id="f-mo">&pound;40,000</div><div class="s">every month</div></div>
    <div class="fig"><div class="k">Over a year</div><div class="v" style="color:var(--cyan)" id="f-yr">&pound;480,000</div><div class="s">recurring</div></div>
    <div class="fig"><div class="k">We take</div><div class="v c-dim" id="f-us">&pound;5,000</div><div class="s">50p a phone</div></div>
  </div>

  <div class="note note-cyan" id="reality">&nbsp;</div>
</section>

<section class="sec">
  <span class="eyebrow">02 &middot; The climb</span>
  <h2>It doesn't start at a million.<br>It starts at <em class="g">ten phones.</em></h2>
  <p class="sub">Every rung, at the price you just set. The first one takes an afternoon. Every one after is the same conversation again. <b>Nothing resets &mdash; last month's phones still pay you this month.</b></p>

  <div id="ladder"></div>

  <div class="note note-gold"><b>The bit people miss:</b> this is the opposite of a job. A job pays you once for the hour you worked. Every phone you sign up pays you again next month, and the month after, while you're asleep or out signing up the next one. <b>Ten new customers a month isn't ten customers &mdash; by December it's a hundred and twenty, all still paying.</b></div>
</section>

<section class="sec">
  <span class="eyebrow">03 &middot; Why this and not the other stuff</span>
  <h2>You've seen the<br>dropshipping <em>adverts.</em></h2>
  <p class="sub">The honest comparison, including the bit that's harder here. If you want easy, this isn't easy. If you want something still paying you in two years, read on.</p>

  <div class="vs">
    <div class="vs-col bad">
      <h3>Flipping products</h3>
      <li>You get paid <b>once</b>. Then back to zero.</li>
      <li>Someone always undercuts you. Margins die.</li>
      <li>Money up front on stock or ads before you earn a penny.</li>
      <li>Returns, shipping, angry customers, customs.</li>
      <li>Anyone can copy your shop in a weekend.</li>
      <li>Nobody's life is better because you sold it.</li>
    </div>
    <div class="vs-col good">
      <h3>This</h3>
      <li>You get paid <b>every month</b>, as long as they keep it.</li>
      <li>Your cost is fixed at 50p. It doesn't rise when you grow.</li>
      <li><b>Nothing up front.</b> No stock, no fee, no minimum.</li>
      <li>No shipping, no returns, no warehouse. It's software.</li>
      <li>Harder to sell than a phone case &mdash; you have to explain it.</li>
      <li>A parent finds out early. That's the product.</li>
    </div>
  </div>
</section>

<section class="sec" id="package">
  <span class="eyebrow">04 &middot; What they actually get</span>
  <h2>Four things.<br>One price. <em>One install.</em></h2>
  <p class="sub">What's on the phone after they say yes. Each one has the exact sentence to use &mdash; nick them word for word, they're written to be said out loud.</p>

  <div class="packs">
    <div class="pk">
      <span class="tag tg-red">Guardian</span>
      <h3>Child protection</h3>
      <p class="one">Spots the patterns that come before harm.</p>
      <p>Watches for the known warning signs of grooming &mdash; pushing for secrecy, isolating a child, moving them to a private chat &mdash; and tells the parent. <b>The messages are never stored</b>, only a fingerprint. What is kept is sealed, so it can't be edited later and it means something to a school or the police.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;Your kid's phone tells you when something starts going wrong &mdash; without you having to read their messages.&rdquo;</p></div>
    </div>

    <div class="pk">
      <span class="tag tg-cyan">Sentinel</span>
      <h3>Fraud alarm</h3>
      <p class="one">Catches it during, not on the statement.</p>
      <p>Watches speed and pattern &mdash; a run of login attempts, a burst of payments, the account popping up in another country minutes after the last one. Classic takeover signals. Flags them live and <b>seals the evidence</b>, so there's something real to show the bank.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;When someone tries to get into your account, you find out while it's happening.&rdquo;</p></div>
    </div>

    <div class="pk">
      <span class="tag tg-green">Sebdog</span>
      <h3>It runs on the phone</h3>
      <p class="one">Not on our computers. Theirs.</p>
      <p>The engine sits on the device itself, so their data doesn't have to leave it to be protected. <b>No round trip, nobody in the middle.</b> Companies pay serious money for this as an on-site product. Here it's just part of the package.</p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;It protects you without sending your life to somebody else's computer.&rdquo;</p></div>
    </div>

    <div class="pk">
      <span class="tag tg-gold">Signal Packs</span>
      <h3>Their rules, not ours</h3>
      <p class="one">They build it. That's why they keep it.</p>
      <p>A Signal Pack is a set of rules the parent writes themselves: which numbers get through, which sites are allowed, what counts as odd for this particular kid. <b>They've put work into it, so they don't cancel it.</b></p>
      <div class="say"><div class="k">Say this</div><p>&ldquo;You set the rules. It's your phone and your family.&rdquo;</p></div>
    </div>
  </div>

  <div class="note note-gold"><b>Underneath all four:</b> everything is written into a chain where each record is locked to the one before, so nothing can be quietly changed afterwards &mdash; not by us either. That's what turns an alert into evidence instead of a screenshot.</div>
</section>

<section class="sec" id="scripts">
  <span class="eyebrow">05 &middot; Your first ten customers</span>
  <h2>You already know<br>every one of <em>them.</em></h2>
  <p class="sub">You don't need adverts or a website to start. You need ten people who trust you and have kids with phones. <b>Here are the actual words.</b> Change them to sound like you, then use them ten times.</p>

  <div class="script">
    <div class="script-h"><h4>The school gate</h4><span class="who">In person &middot; 30 seconds</span></div>
    <div class="words">&ldquo;Can I ask you something daft &mdash; has your lad got a phone yet? Right. So I've started doing something that puts a thing on it that watches for the grooming stuff. It doesn't read his messages, it just tells you if someone starts asking him to keep secrets or move to a private chat. <b>It's a fiver a month.</b> Want me to put it on for you?&rdquo;</div>
    <div class="after"><b>Why it works:</b> you named the fear, you killed the objection they were about to make (reading his messages), and you gave the price before they had to ask. <b>Say the price.</b> People who hide the price never sell anything.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The group chat</h4><span class="who">WhatsApp &middot; paste it</span></div>
    <div class="words">&ldquo;Bit random. I've started doing a thing for kids' phones &mdash; it watches for the grooming warning signs and tells the parent, without reading their messages. Also catches someone trying to get into your bank. <b>&pound;4.50 a month, cancel whenever.</b> If anyone wants it on their kid's phone give me a shout and I'll sort it.&rdquo;</div>
    <div class="after"><b>Why it works:</b> low pressure, no link, no sales voice. In a group of forty parents you'll get three. <b>Three is £13.50 a month, forever, from one message</b> &mdash; and those three tell other parents, because this is the thing parents actually talk about.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The shop counter</h4><span class="who">If you sell phones</span></div>
    <div class="words">&ldquo;Is this one for yourself or for one of the kids? For your daughter &mdash; right. Do you want me to put the safety package on before you go? It watches for grooming and tells you, and it flags anyone trying to get into her accounts. <b>It's five pound a month and I can set it up now while you're stood here.</b>&rdquo;</div>
    <div class="after"><b>Why it works:</b> they're already spending and already thinking about their kid. <b>Every handset becomes a monthly income you keep for years</b> instead of a one-off margin you spend that week.</div>
  </div>

  <div class="script">
    <div class="script-h"><h4>The business one</h4><span class="who">Phone &middot; clubs, schools, firms</span></div>
    <div class="words">&ldquo;I supply a safety package that goes on phones &mdash; it flags the grooming warning signs to a parent and keeps a sealed record you could hand to the police if it ever came to it. I'm offering it to your families at <b>&pound;4 a month.</b> Could I show you what a parent actually sees? Takes five minutes.&rdquo;</div>
    <div class="after"><b>Why it works:</b> one club or one school is a hundred families in a single conversation. <b>That's £350 a month from one phone call.</b> Ask for the five minutes, not the sale.</div>
  </div>

  <div class="note note-cyan"><b>The only rule:</b> ask for the money. Nine out of ten people who fail at this never say a price out loud. Say it plainly, then stop talking and let them answer.</div>
</section>

<section class="sec">
  <span class="eyebrow">06 &middot; How the good ones sell it</span>
  <h2>Never oversell<br>this <em>one thing.</em></h2>
  <p class="sub">Everything on the left is true and provable. Everything on the right is a promise nobody on earth can keep, including us. <b>The left-hand column closes better anyway</b> &mdash; parents can smell a salesman, and they trust the person who tells them what it can't do.</p>

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

  <div class="note note-red"><b>Why we're hard on this:</b> it catches known patterns. It cannot catch every clever rewording, and no honest product claims otherwise. What it guarantees is the <b>record</b>. Sell the early warning and the proof. <b>A parent promised a wall who got a smoke alarm cancels, tells forty other parents, and takes your income with them.</b> Sell it straight and they stay for years. Overclaim on child safety and your code gets pulled.</div>
</section>

<section class="sec">
  <span class="eyebrow">07 &middot; The deal, plainly</span>
  <h2>You get rich,<br>we get <em class="g">busy.</em></h2>
  <p class="sub">No catch, and here's exactly where our money comes from so you're not left wondering.</p>

  <div class="vs">
    <div class="vs-col good">
      <h3>What you get</h3>
      <li>Everything above 50p. <b>We never see your price.</b></li>
      <li>Your own brand on it if you want one.</li>
      <li>Your customers, your invoices, your relationship.</li>
      <li>Phones locked to your code <b>permanently</b> &mdash; they grow, you grow.</li>
      <li>No joining fee, no minimum, no exclusivity, no quota.</li>
      <li>Sell nothing, owe nothing.</li>
    </div>
    <div class="vs-col good">
      <h3>What we get</h3>
      <li>50p per active phone. <b>That's the entire deal.</b></li>
      <li>We'd rather have 50p from a million phones than &pound;50 from a thousand.</li>
      <li>You sell in places we'd never reach.</li>
      <li>Every phone makes the network stronger for everyone on it.</li>
      <li>We only earn when you earn. <b>You sell nothing, we get nothing.</b></li>
      <li>Which is why the 50p doesn't move when you scale.</li>
    </div>
  </div>

  <div class="note note-gold"><b>Say it to your customers if you like</b> &mdash; there's no shame in the model. You're the one out there doing the work, having the conversations, taking the knock-backs. <b>You should keep the lion's share, and you do.</b></div>
</section>

<section class="sec">
  <span class="eyebrow">08 &middot; Straight answers</span>
  <h2>What everyone<br><em>asks first.</em></h2>
  <div style="margin-top:24px">
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need money to start?</div><div class="faq-a">No. Not a penny. No joining fee, no stock, no minimum, no ads. You pay us 50p only for phones that are actually live &mdash; and by then your customer has already paid you.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need to be technical?</div><div class="faq-a">No. You get a code, they install it, that's it. If you can set up a phone for somebody, you can do this.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Do I need a company?</div><div class="faq-a">Not to start. But once money's coming in, <b>tell HMRC</b> &mdash; income from this is taxable like any other, and registering as a sole trader is free and takes ten minutes online. Don't skip it, and don't let anyone tell you it doesn't count.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Is this one of them pyramid things?</div><div class="faq-a"><b>No, and here's how you check.</b> You don't recruit anybody. You don't earn from other sellers. You don't buy in, and there's nothing to buy. You sell a real product to real people who use it, and you pay 50p per phone. If a scheme's money comes from recruiting rather than selling, walk away &mdash; that's the test, and this one passes it.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Can I sell it outside the UK?</div><div class="faq-a">Yes, anywhere. Your currency, your price, your language. The 50p stays in sterling, so in plenty of markets the margin is <b>better</b>, not worse.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">What if someone cancels?</div><div class="faq-a">Billing stops for that phone &mdash; your bit and our bit. No penalty, no clawback, no notice period. Your other customers aren't affected.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">Will you go behind my back to my customers?</div><div class="faq-a">No. You invoice them, you hold the relationship, and their phones are tied to your code permanently. If your ten become ten thousand, that's yours.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">How do I know any of this is real?</div><div class="faq-a">Don't take our word for it. The chain is public, the checking routes need no account, and the verifier runs on your own machine with the internet off. <b>You're meant to check rather than trust.</b> Start at <a href="/whitepaper" style="color:var(--gold)">the whitepaper</a>.</div></div>
    <div class="faq"><div class="faq-q" onclick="tf(this)">How much can I really make in month one?</div><div class="faq-a">Realistically? Ten to thirty phones if you actually ask everyone you know. At &pound;4.50 that's <b>&pound;40 to &pound;120 a month</b> &mdash; and it's still arriving next January. Anyone promising you thousands in week one is lying to you.</div></div>
  </div>
</section>

<div class="cta" id="start">
  <h2>Ten phones by <em>Friday.</em></h2>
  <p>Get your code, set your price, ask the first ten people you know. It costs you nothing to find out whether you're any good at this.</p>
  <a href="/#signup" class="btn">Get my code &mdash; free &rarr;</a>
  <a href="/contact" class="btn2">Talk to Justin first</a>
</div>

<div class="honest">
  <div class="honest-box"><b>About the numbers on this page:</b> every figure comes from sliders you set yourself. It's arithmetic, not a forecast, and nobody is promising you customers or income. The million is <b>total earned over time, before tax and your own costs</b> &mdash; not a lump sum, not net worth. What we promise is the price: <b>50p per active phone per month and nothing else.</b> Whether anyone buys is down to you, which is exactly why the margin is yours.<br><br><b>About the product:</b> sealing proves something happened in a particular form at a particular time and hasn't changed since. It does not prove the contents are true and it does not discharge anybody's legal duties. <b>Guardian is a safeguarding aid and an evidence layer. It supports a parent. It never replaces one.</b></div>
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
var DEV=[5,10,20,35,50,75,100,150,250,400,600,1000,1600,2500,4000,6500,10000,16000,25000,40000,65000,100000];
var COST=0.50;
var MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];
var RUNGS=[
  {n:10,    t:'Your phone bill',       d:'One afternoon. Family and the neighbours.'},
  {n:50,    t:'The weekly shop',       d:'Your street, your group chat, the school gate.'},
  {n:100,   t:'The car payment',       d:'One club, one class, one small school.'},
  {n:250,   t:'Rent money',            d:'Word of mouth has started doing it for you.'},
  {n:500,   t:'A full-time wage',      d:'You could pack the day job in around here.'},
  {n:2000,  t:"You're an employer",    d:'Somebody else is making the calls for you now.'},
  {n:10000, t:'You run a company',     d:'A shop chain, an operator, a proper region.'},
  {n:25000, t:'Millionaire territory', d:'Cumulative, over time. Still just phones.'}
];

function money(n){
  if(n>=1000000) return '\u00a3'+(n/1000000).toFixed(n>=10000000?0:2)+'m';
  if(n>=100000)  return '\u00a3'+Math.round(n/1000)+'k';
  return '\u00a3'+Math.round(n).toLocaleString('en-GB');
}
function num(n){
  if(n>=1000000) return (n/1000000).toFixed(n>=10000000?0:1)+'m';
  if(n>=10000)   return Math.round(n/1000)+'k';
  return Math.round(n).toLocaleString('en-GB');
}
function devFrom(v){
  var i=Math.round(v/100*(DEV.length-1));
  return DEV[Math.max(0,Math.min(DEV.length-1,i))];
}
function futureDate(m){
  var d=new Date(); d.setMonth(d.getMonth()+m);
  return MONTHS[d.getMonth()]+' '+d.getFullYear();
}

function draw(){
  var dev=devFrom(+document.getElementById('s-dev').value);
  var price=(+document.getElementById('s-price').value)/100;
  var per=Math.max(0,price-COST);
  var mo=per*dev;

  document.getElementById('v-dev').textContent=num(dev);
  document.getElementById('v-price').textContent='\u00a3'+price.toFixed(2);
  document.getElementById('f-mo').textContent=money(mo);
  document.getElementById('f-yr').textContent=money(mo*12);
  document.getElementById('f-us').textContent=money(COST*dev);

  var cn=document.getElementById('c-num'),cu=document.getElementById('c-unit'),cd=document.getElementById('c-date');
  if(mo<=0){
    cn.textContent='\u2014'; cu.textContent='never at this price';
    cd.textContent='you\u2019re charging 50p or less \u2014 push the price up';
  } else {
    var months=Math.ceil(1000000/mo);
    if(months<=120){
      cn.textContent=months; cu.textContent=(months===1?'month':'months');
      cd.textContent='around '+futureDate(months);
    } else {
      var yrs=Math.round(months/12);
      cn.textContent=yrs; cu.textContent='years';
      cd.textContent=(yrs>60?'a long way off \u2014 add phones or raise your price':'around '+futureDate(months));
    }
  }

  var rl=document.getElementById('reality');
  if(price<=COST){
    rl.className='note note-red';
    rl.innerHTML='<b>You\u2019d be working for nothing.</b> At \u00a3'+price.toFixed(2)+' you\u2019re at or below the 50p we charge. Even \u00a31.50 leaves you a pound a month per phone \u2014 push it up.';
  } else if(dev>=25000){
    rl.className='note note-cyan';
    rl.innerHTML='<b>That\u2019s operator scale.</b> '+num(dev)+' phones is a network deal or a shop chain, not a school gate. Real, but it\u2019s a boardroom, not an afternoon. Drag it back to 50 and look at where you\u2019d actually start.';
  } else {
    rl.className='note note-cyan';
    rl.innerHTML='<b>Straight up:</b> the clock assumes you hold '+num(dev)+' phones the whole way. Real life is a climb \u2014 you\u2019ll be at 20 before you\u2019re at 200. Which is why the ladder below matters more than the big number.';
  }

  var out='',marked=false;
  for(var i=RUNGS.length-1;i>=0;i--){
    RUNGS[i]._cls = (RUNGS[i].n<=dev && !marked) ? 'rung now' : (RUNGS[i].n<=dev ? 'rung hit' : 'rung');
    if(RUNGS[i].n<=dev) marked=true;
  }
  RUNGS.forEach(function(r){
    out+='<div class="'+r._cls+'">'+
      '<div class="rung-n">'+num(r.n)+'<small>phones</small></div>'+
      '<div class="rung-mid"><div class="t">'+r.t+'</div><div class="d">'+r.d+'</div></div>'+
      '<div class="rung-amt">'+money(per*r.n)+'<small>a month</small></div>'+
    '</div>';
  });
  document.getElementById('ladder').innerHTML=out;
}

function tf(el){el.parentElement.classList.toggle('open');}
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
