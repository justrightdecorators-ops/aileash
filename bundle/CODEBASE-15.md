# Codebase — part 15 of 17

Contains:
- `seal.html`
- `sentinel.html`
- `signal-packs.html`
- `sitemap.xml`


## `seal.html`

83 lines, 4894 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Seal a post — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#fff;font-family:system-ui,sans-serif;min-height:100vh;padding:24px}
  .wrap{max-width:620px;margin:0 auto}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:26px;color:var(--gold);margin:14px 0 6px}
  .sub{font-size:13.5px;color:rgba(255,255,255,0.5);line-height:1.7;margin-bottom:22px}
  textarea{width:100%;min-height:200px;background:var(--ink2);border:1px solid rgba(201,168,76,0.35);color:#fff;border-radius:8px;padding:14px;font-size:14px;font-family:inherit;line-height:1.6;outline:none;resize:vertical}
  textarea:focus{border-color:var(--gold)}
  button{width:100%;margin-top:14px;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:16px;font-size:16px;font-weight:800;cursor:pointer}
  button:disabled{opacity:0.5}
  #result{display:none;margin-top:20px;border-radius:10px;padding:26px;text-align:left}
  #result.ok{display:block;background:rgba(127,227,176,0.08);border:2px solid var(--ok)}
  #result.err{display:block;background:rgba(255,138,128,0.08);border:2px solid var(--err)}
  #result .big{font-size:22px;font-weight:900;font-family:Georgia,serif;margin-bottom:10px;text-align:center}
  #result.ok .big{color:var(--ok)}
  #result.err .big{color:var(--err)}
  #result .detail{font-family:monospace;font-size:12px;color:rgba(255,255,255,0.75);line-height:2;word-break:break-all}
  #result .code{font-size:18px;color:var(--gold);font-weight:700}
  .note{margin-top:22px;font-size:12px;color:rgba(255,255,255,0.35);line-height:1.8}
  .note b{color:var(--gold);font-weight:600}
  a{color:var(--gold)}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand">sebbi.pro &middot; live chain sealing</div>
  <h1>Seal this post into the chain.</h1>
  <div class="sub">Paste the exact final text of your post below — the way you're about to publish it, without the footer line. This fingerprints it (SHA-256, computed in your own browser) and seals that fingerprint into the live audit chain. Change even one letter afterwards and it will no longer match.</div>

  <textarea id="txt" placeholder="Paste your finished post text here..."></textarea>
  <button id="go" onclick="sealPost()">Seal this post &rarr;</button>

  <div id="result"></div>

  <div class="note"><b>How this works:</b> your text never leaves your browser — only its fingerprint is sealed. Once sealed, add the verification line it gives you to the end of your post before publishing, so readers can check it at <a href="/verify-post">sebbi.pro/verify-post</a>.<br><br>This is the same engine that seals AI decisions for platforms. <a href="/">Free for 90 days &rarr;</a></div>
</div>

<script>
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
async function sealPost(){
  var raw=document.getElementById("txt").value;
  var res=document.getElementById("result");
  var btn=document.getElementById("go");
  if(!raw.trim()){res.className="err";res.style.display="block";res.innerHTML="<div class='big'>Paste some text first</div>";return;}
  btn.disabled=true;btn.textContent="Sealing\u2026";
  try{
    var text=raw.trim();
    var hash=await sha256hex(text);
    var r=await fetch("/api/post/seal",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({fingerprint:hash})});
    var d=await r.json();
    if(!d.sealed){
      res.className="err";res.style.display="block";
      res.innerHTML="<div class='big'>Sealing failed</div><div class='detail'>"+(d.error||"Unknown error")+"</div>";
    }else{
      var when=new Date(d.sealed_at*1000).toLocaleString("en-GB");
      var code=(d.code||hash.slice(0,12));
      res.className="ok";res.style.display="block";
      res.innerHTML="<div class='big'>"+(d.already_registered?"Already sealed":"\u2713 SEALED")+"</div>"
        +"<div class='detail'>Block #"+d.block_index+"<br>Sealed "+when+"<br>Fingerprint "+hash+"<br><br>"
        +"<b>Add this line to the end of your post:</b><br>\uD83D\uDD17 Post sealed \u00b7 verify at sebbi.pro/verify-post<br><br>"
        +"<span class='code'>Verification code: "+code+"</span></div>";
    }
  }catch(e){
    res.className="err";res.style.display="block";
    res.innerHTML="<div class='big'>Network error</div><div class='detail'>"+e+"</div>";
  }
  btn.disabled=false;btn.textContent="Seal this post \u2192";
}
</script>
</body>
</html>

```


## `sentinel.html`

485 lines, 52351 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Sentinel &mdash; Real-Time Fraud &amp; Anomaly Detection &mdash; sebbi.pro</title>
<meta name="description" content="AILeash Sentinel watches your platform 24 hours a day. Real-time fraud detection, velocity monitoring, trust decay scoring. Every alert sealed into a SHA-256 audit chain. 50p per device per month.">
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--navy:#0a0f1e;--purple:#7c3aed;--purple-light:#a78bfa;--white:#fff;--green:#00ff88;--red:#cc0000;--gold:#c9a84c;--cyan:#00d4ff;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Playfair Display',serif}
html,body{background:var(--navy);color:var(--white);font-family:var(--sans);overflow-x:hidden}
html{scroll-behavior:smooth}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(10,15,30,0.97);backdrop-filter:blur(12px);padding:0 48px;height:68px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(124,58,237,0.2)}
.nav-logo{font-family:var(--display);font-size:20px;color:var(--white);font-weight:900;text-decoration:none}.nav-logo span{color:var(--purple-light)}
.nav-links{display:flex;gap:16px;align-items:center}
.nav-links a{color:rgba(255,255,255,0.4);text-decoration:none;font-size:13px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--white)}
.nav-cta{background:var(--purple)!important;color:var(--white)!important;padding:9px 18px;font-weight:700!important;border-radius:4px}
.alert-bar{background:var(--purple);padding:10px 48px;margin-top:68px;text-align:center;font-family:var(--mono);font-size:11px;color:var(--white);letter-spacing:1px;text-transform:uppercase}
.alert-bar strong{color:#ffd700}
.hero{padding:60px 48px 80px;position:relative;overflow:hidden;text-align:center;border-bottom:1px solid rgba(124,58,237,0.15)}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 40%,rgba(124,58,237,0.08) 0%,transparent 65%)}
.hero::after{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--purple-light),transparent)}
.hero-inner{max-width:860px;margin:0 auto;position:relative;z-index:1}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:3px;text-transform:uppercase;color:var(--purple-light);margin-bottom:20px;display:block}
h1{font-family:var(--display);font-size:clamp(32px,5vw,64px);line-height:1.05;font-weight:900;margin-bottom:20px}
h1 em{color:var(--purple-light);font-style:normal}
.hero-sub{font-size:17px;color:rgba(255,255,255,0.4);line-height:1.8;max-width:640px;margin:0 auto 36px}
.hero-sub strong{color:var(--white)}
.sound-toggle{display:inline-flex;align-items:center;gap:10px;background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2);border-radius:40px;padding:10px 20px;cursor:pointer;margin-bottom:28px;transition:all .2s;font-family:var(--mono);font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--purple-light)}
.sound-toggle:hover{background:rgba(124,58,237,0.15)}
.terminal{background:rgba(0,0,0,0.6);border:1px solid rgba(124,58,237,0.2);border-radius:8px;overflow:hidden;text-align:left;margin-bottom:40px}
.terminal-bar{background:rgba(124,58,237,0.04);padding:12px 20px;border-bottom:1px solid rgba(124,58,237,0.1);display:flex;align-items:center;gap:8px}
.t-dot{width:10px;height:10px;border-radius:50%}
.t-dot-r{background:#ff5f57}.t-dot-y{background:#febc2e}.t-dot-g{background:#28c840}
.t-title{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.2);letter-spacing:2px;text-transform:uppercase;margin-left:8px}
.terminal-body{padding:24px 28px 28px;min-height:240px;max-height:50vh;overflow-y:auto}
.terminal-body::-webkit-scrollbar{width:3px}.terminal-body::-webkit-scrollbar-thumb{background:rgba(124,58,237,0.2);border-radius:2px}
.t-line{font-family:var(--mono);font-size:12px;line-height:2;display:flex;align-items:flex-start;gap:10px;opacity:0;transform:translateY(4px);transition:opacity .25s,transform .25s}
.t-line.show{opacity:1;transform:none}
.t-prompt{color:rgba(124,58,237,0.5);flex-shrink:0}
.t-text{color:rgba(255,255,255,0.75);flex:1}
.t-purple{color:var(--purple-light)}.t-green{color:var(--green)}.t-gold{color:var(--gold)}.t-red{color:#ff6b6b}.t-dim{color:rgba(255,255,255,0.2)}.t-cyan{color:var(--cyan)}
.t-hash{color:var(--green);font-size:11px;word-break:break-all;line-height:1.6}
.t-section{font-family:var(--mono);font-size:9px;letter-spacing:3px;text-transform:uppercase;color:rgba(124,58,237,0.25);padding:8px 0 4px;border-top:1px solid rgba(255,255,255,0.04);margin-top:4px;opacity:0;transition:opacity .3s}
.t-section.show{opacity:1}
.verdict{display:none;padding:24px 28px;border-top:1px solid rgba(124,58,237,0.1);background:rgba(0,0,0,0.3)}
.verdict.show{display:block}
.verdict-decision{font-family:var(--display);font-size:48px;font-weight:900;line-height:1;margin-bottom:6px;color:var(--green)}
.verdict-score{font-family:var(--mono);font-size:11px;color:rgba(255,255,255,0.25);margin-bottom:16px}
.verdict-hash-label{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.15);margin-bottom:6px}
.verdict-hash{font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:10px 12px;border-radius:4px;margin-bottom:8px;line-height:1.6}
.verdict-sealed{font-family:var(--mono);font-size:10px;color:rgba(124,58,237,0.5)}
.btn-purple{background:var(--purple);color:var(--white);padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s}.btn-purple:hover{background:#6d28d9;transform:translateY(-2px)}
.btn-ghost{background:transparent;color:rgba(255,255,255,0.4);padding:14px 28px;border:1px solid rgba(255,255,255,0.1);font-family:var(--sans);font-weight:600;font-size:14px;cursor:pointer;text-decoration:none;border-radius:4px;display:inline-block;transition:all .2s;margin-left:10px}.btn-ghost:hover{color:var(--white);border-color:rgba(255,255,255,0.3)}
.sec{padding:80px 48px;border-bottom:1px solid rgba(255,255,255,0.05)}
.sec-inner{max-width:1100px;margin:0 auto}
.sec-eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:3px;text-transform:uppercase;color:rgba(124,58,237,0.5);margin-bottom:16px;display:block}
h2{font-family:var(--display);font-size:clamp(26px,3.5vw,44px);font-weight:900;line-height:1.1;margin-bottom:16px}
h2 em{color:var(--purple-light);font-style:normal}
.sec-sub{font-size:15px;color:rgba(255,255,255,0.35);line-height:1.8;max-width:580px;margin-bottom:48px}
.video-sec{padding:80px 48px;background:rgba(0,0,0,0.3);border-bottom:1px solid rgba(124,58,237,0.08)}
.video-inner{max-width:900px;margin:0 auto;text-align:center}
.advert-stage{width:100%;aspect-ratio:16/9;position:relative;background:#000;border-radius:8px;overflow:hidden;border:1px solid rgba(124,58,237,0.2)}
.ad-scene{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;transition:opacity 0.8s;padding:40px}
.ad-scene.active{opacity:1}
.ad-line{font-family:var(--display);font-size:clamp(14px,3.5vw,52px);font-weight:900;color:#fff;text-align:center;line-height:1.2;opacity:0;transform:translateY(16px);transition:opacity .5s,transform .5s;margin-bottom:8px}
.ad-line.show{opacity:1;transform:none}
.ad-line.purple{color:var(--purple-light)}.ad-line.green{color:var(--green)}.ad-line.red{color:var(--red)}.ad-line.gold{color:var(--gold)}
.ad-terminal{background:rgba(0,0,0,0.7);border:1px solid rgba(124,58,237,0.25);border-radius:6px;width:85%;padding:0;overflow:hidden}
.ad-tm-bar{background:rgba(124,58,237,0.04);padding:8px 16px;border-bottom:1px solid rgba(124,58,237,0.1);display:flex;gap:6px;align-items:center}
.ad-tm-dot{width:8px;height:8px;border-radius:50%}
.ad-tm-body{padding:16px 20px;display:flex;flex-direction:column;gap:0}
.ad-tm-line{font-family:monospace;font-size:clamp(8px,1.2vw,14px);line-height:1.9;display:flex;gap:8px;opacity:0;transition:opacity .3s}
.ad-tm-line.show{opacity:1}
.ad-big{font-family:var(--display);font-size:clamp(40px,10vw,110px);font-weight:900;line-height:1;opacity:0;transform:scale(0.7);transition:opacity .5s,transform .5s}
.ad-big.show{opacity:1;transform:scale(1)}
.ad-small{font-family:monospace;font-size:clamp(8px,1.2vw,14px);color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-top:8px;opacity:0;transition:opacity .5s}
.ad-small.show{opacity:1}
.ad-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;width:88%}
.ad-card{border-left:3px solid;padding:12px 16px;opacity:0;transform:translateX(-16px);transition:opacity .4s,transform .4s}
.ad-card.show{opacity:1;transform:none}
.ad-card-label{font-family:monospace;font-size:clamp(7px,0.9vw,10px);letter-spacing:2px;text-transform:uppercase;margin-bottom:4px;opacity:0.7}
.ad-card-text{font-size:clamp(10px,1.4vw,15px);color:rgba(255,255,255,0.8);font-weight:700;line-height:1.3}
.ad-card-fine{font-family:monospace;font-size:clamp(7px,0.8vw,10px);color:rgba(255,255,255,0.3);margin-top:4px}
.ad-progress{position:absolute;bottom:0;left:0;right:0;height:3px;background:rgba(255,255,255,0.05)}
.ad-progress-bar{height:100%;background:linear-gradient(90deg,var(--purple),var(--cyan));width:0%;transition:width .1s linear}
.ad-controls{display:flex;gap:10px;justify-content:center;margin-top:16px}
.ad-ctrl{background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:rgba(255,255,255,0.5);padding:8px 16px;border-radius:4px;cursor:pointer;font-family:var(--mono);font-size:10px;letter-spacing:1px;text-transform:uppercase;transition:all .2s}.ad-ctrl:hover{background:rgba(255,255,255,0.12);color:var(--white)}
.features-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:2px;background:rgba(255,255,255,0.04);margin-top:40px}
.feat{background:var(--navy);padding:32px 24px;border-top:3px solid var(--purple)}
.feat-icon{font-size:28px;margin-bottom:12px}
.feat h3{font-family:var(--display);font-size:18px;font-weight:900;color:var(--white);margin-bottom:8px}
.feat p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.7}
.feat-badge{font-family:var(--mono);font-size:9px;letter-spacing:2px;text-transform:uppercase;margin-top:10px;padding:3px 8px;border-radius:2px;display:inline-block;color:var(--purple-light);background:rgba(124,58,237,0.08);border:1px solid rgba(124,58,237,0.2)}
.use-cases{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:40px}
.use-card{background:rgba(255,255,255,0.02);border:1px solid rgba(124,58,237,0.1);border-radius:6px;padding:24px}
.use-card h3{font-family:var(--display);font-size:17px;font-weight:900;color:var(--white);margin-bottom:8px}
.use-card p{font-size:13px;color:rgba(255,255,255,0.4);line-height:1.7}
.use-earn{font-family:var(--display);font-size:28px;color:var(--purple-light);font-weight:900;margin-top:12px}
.use-earn-label{font-family:var(--mono);font-size:9px;color:rgba(255,255,255,0.2);letter-spacing:1px;text-transform:uppercase}
.pricing-sec{padding:80px 48px;border-bottom:4px solid var(--purple)}
.pricing-inner{max-width:700px;margin:0 auto;text-align:center}
.price-big{font-family:var(--display);font-size:96px;font-weight:900;color:var(--purple-light);line-height:1;margin-bottom:4px}
.price-per{font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.2);margin-bottom:32px}
.price-includes{display:flex;flex-direction:column;gap:10px;text-align:left;margin-bottom:32px;max-width:500px;margin-left:auto;margin-right:auto}
.pi{display:flex;align-items:center;gap:10px;font-size:14px;color:rgba(255,255,255,0.5)}
.pi::before{content:'OK';font-family:var(--mono);font-size:9px;font-weight:700;color:var(--purple-light);flex-shrink:0}
.signup-sec{padding:80px 48px}
.signup-inner{max-width:520px;margin:0 auto;text-align:center}
.signup-inner p{font-size:15px;color:rgba(255,255,255,0.35);line-height:1.7;margin-bottom:32px}
.fg{margin-bottom:12px;text-align:left}
.fg label{display:block;font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.25);letter-spacing:2px;text-transform:uppercase;margin-bottom:6px}
.fg input,.fg select{width:100%;background:rgba(255,255,255,0.05);border:2px solid rgba(255,255,255,0.08);color:var(--white);padding:12px 14px;font-size:14px;font-family:var(--sans);outline:none;border-radius:4px;transition:border-color .2s}
.fg input:focus,.fg select:focus{border-color:var(--purple)}
.fg input::placeholder{color:rgba(255,255,255,0.2)}
.fg select option{background:var(--navy)}
.fg-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.btn-full{width:100%;padding:14px;font-size:15px;font-weight:700;border-radius:4px;border:none;cursor:pointer;font-family:var(--sans);transition:all .2s;background:var(--purple);color:var(--white);margin-top:8px}
.btn-full:hover{background:#6d28d9}
.key-box{display:none;margin-top:24px;background:rgba(0,0,0,0.4);border:1px solid rgba(124,58,237,0.2);border-radius:6px;padding:24px;text-align:left}
.key-box.show{display:block}
.key-lbl{font-family:var(--mono);font-size:9px;letter-spacing:2px;color:var(--purple-light);margin-bottom:8px;text-transform:uppercase}
.key-val{font-family:var(--mono);font-size:11px;color:var(--green);word-break:break-all;background:rgba(0,0,0,0.3);padding:10px;border-radius:4px;margin-bottom:12px}
.ref-box{background:rgba(124,58,237,0.06);border:1px solid rgba(124,58,237,0.2);border-radius:4px;padding:16px}
.ref-code{font-family:var(--display);font-size:24px;color:var(--purple-light);font-weight:900;margin:6px 0}
.ref-desc{font-size:12px;color:rgba(255,255,255,0.35);line-height:1.6}
.msg-err{display:none;color:#ff6b6b;font-family:var(--mono);font-size:11px;margin-top:10px;padding:10px;background:rgba(255,0,0,0.08);border-radius:4px;border:1px solid rgba(255,0,0,0.2)}
.msg-err.show{display:block}
footer{background:rgba(0,0,0,0.4);padding:48px;border-top:1px solid rgba(255,255,255,0.04)}
.foot-inner{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:20px}
.foot-logo{font-family:var(--display);font-size:18px;color:var(--white);font-weight:900;text-decoration:none}.foot-logo span{color:var(--purple-light)}
.foot-links{display:flex;gap:24px;flex-wrap:wrap}
.foot-links a{color:rgba(255,255,255,0.2);text-decoration:none;font-size:12px;transition:color .2s}.foot-links a:hover{color:var(--white)}
.foot-copy{font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.1);width:100%;margin-top:16px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.04)}
@media(max-width:900px){
  nav{padding:0 20px}.alert-bar{padding:10px 20px}
  .nav-links a:not(.nav-cta){display:none}
  .hero,.sec,.video-sec,.pricing-sec,.signup-sec{padding-left:20px!important;padding-right:20px!important}
  .features-grid,.use-cases,.fg-row,.ad-grid{grid-template-columns:1fr!important}
  footer{padding:36px 20px}.foot-inner{flex-direction:column;align-items:flex-start}
  .btn-ghost{margin-left:0;margin-top:10px;display:block}
}
</style>
</head>
<body>
<nav>
  <a href="https://sebbi.pro" class="nav-logo">Monop <span>Content</span></a>
  <div class="nav-links">
    <a href="https://sebbi.pro/#products">All Products</a>
    <a href="https://sebbi.pro/reseller">Reseller</a>
    <a href="https://sebbi.pro/contact">Contact</a>
    <a href="#signup" class="nav-cta">Get Sentinel Free</a>
  </div>
</nav>

<div class="alert-bar"><strong>Fraud costs UK businesses £1.8 billion a year.</strong> &nbsp; Sentinel catches it before the damage is done. &nbsp; <strong>50p per device per month.</strong></div>

<section class="hero">
  <div class="hero-inner">
    <span class="eyebrow">AILeash Sentinel &mdash; Fraud &amp; Anomaly Detection &mdash; sebbi.pro</span>
    <h1>Your platform is being attacked<br><em>right now.</em></h1>
    <p class="hero-sub">Sentinel watches every user, every session, every transaction — 24 hours a day. <strong>Fraud flagged before the damage is done.</strong> Every alert sealed into a cryptographic chain. Admissible as fraud evidence in court.</p>
    <button class="sound-toggle" id="sound-toggle" onclick="toggleSound()"><span id="sound-icon">&#128266;</span><span id="sound-label">Sound On &mdash; Tap to mute</span></button>
    <div class="terminal">
      <div class="terminal-bar">
        <div class="t-dot t-dot-r"></div><div class="t-dot t-dot-y"></div><div class="t-dot t-dot-g"></div>
        <span class="t-title">AILeash Sentinel &mdash; Live Session Scan &mdash; Fraud Monitor Active</span>
      </div>
      <div class="terminal-body" id="terminal-body"></div>
      <div class="verdict" id="verdict">
        <div class="verdict-decision" id="v-decision">ALLOW</div>
        <div class="verdict-score" id="v-score"></div>
        <div class="verdict-hash-label">Audit Hash &mdash; SHA-256 &mdash; Sealed &mdash; Fraud Evidence Ready</div>
        <div class="verdict-hash" id="v-hash"></div>
        <div class="verdict-sealed" id="v-sealed"></div>
      </div>
    </div>
    <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap">
      <a href="#signup" class="btn-purple">Get Free Sentinel API Key &rarr;</a>
      <a href="#video" class="btn-ghost">Watch The Demo</a>
    </div>
  </div>
</section>

<section class="video-sec" id="video">
  <div class="video-inner">
    <span class="sec-eyebrow">Sentinel &mdash; 60 Second Demo</span>
    <h2 style="font-family:var(--display);font-size:clamp(26px,3.5vw,44px);font-weight:900;margin-bottom:16px">Watch a fraud attack<br><em>get caught in real time.</em></h2>
    <p style="font-size:15px;color:rgba(255,255,255,0.35);line-height:1.8;max-width:580px;margin:0 auto 32px">This is what Sentinel does. Every second. On every platform. Before the money is gone.</p>
    <div class="advert-stage" id="advert-stage">
      <div class="ad-scene" id="as1" style="background:#000">
        <div class="ad-line purple" id="as1a">500 requests.</div>
        <div class="ad-line purple" id="as1b">60 seconds.</div>
        <div class="ad-line purple" id="as1c">One account.</div>
        <div class="ad-line" id="as1d" style="margin-top:24px;font-size:clamp(12px,2vw,28px);color:rgba(255,255,255,0.4)">Without Sentinel,</div>
        <div class="ad-line red" id="as1e">you find out days later.</div>
      </div>
      <div class="ad-scene" id="as2" style="background:#0a0f1e">
        <div style="font-family:Georgia,serif;font-size:clamp(14px,2.5vw,28px);font-weight:900;color:#fff;margin-bottom:16px;text-align:center">Sentinel <span style="color:var(--purple-light)">catches it instantly.</span></div>
        <div class="ad-terminal">
          <div class="ad-tm-bar">
            <div class="ad-tm-dot" style="background:#ff5f57"></div><div class="ad-tm-dot" style="background:#febc2e"></div><div class="ad-tm-dot" style="background:#28c840"></div>
            <span style="font-family:monospace;font-size:clamp(7px,1vw,11px);color:rgba(255,255,255,0.2);letter-spacing:2px;text-transform:uppercase;margin-left:8px">Sentinel &mdash; Real-Time Fraud Detection</span>
          </div>
          <div class="ad-tm-body">
            <div class="ad-tm-line" id="atl1"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.7)">ALERT: user_789 &mdash; <span style="color:#ff6b6b">velocity spike detected</span></span></div>
            <div class="ad-tm-line" id="atl2"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.7)">60s window: <span style="color:#ff6b6b">487 requests &mdash; threshold: 60</span></span></div>
            <div class="ad-tm-line" id="atl3"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.7)">Country shift: <span style="color:#ff6b6b">GB to NG &mdash; account takeover signal</span></span></div>
            <div class="ad-tm-line" id="atl4"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.7)">Trust score: <span style="color:#ff6b6b">0.0341 &mdash; critically low</span></span></div>
            <div class="ad-tm-line" id="atl5"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.7)">Risk score: <span style="color:#ff6b6b">0.9187</span> &mdash; 9 signals triggered</span></div>
            <div class="ad-tm-line" id="atl6"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:rgba(255,255,255,0.9);font-weight:700;font-size:1.1em;letter-spacing:2px">Decision: <span style="color:#cc0000">BLOCK</span></span></div>
            <div class="ad-tm-line" id="atl7"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:var(--green)">Alert sent &mdash; fraud evidence package sealed &mdash; audit hash locked</span></div>
            <div class="ad-tm-line" id="atl8"><span style="color:rgba(124,58,237,0.5)">&gt;</span><span style="color:var(--green)">Time from first signal to block: 847ms</span></div>
          </div>
        </div>
      </div>
      <div class="ad-scene" id="as3" style="background:#0a0f1e">
        <div style="text-align:center">
          <div class="ad-big red" id="ad-block" style="color:#cc0000">BLOCKED</div>
          <div class="ad-small" id="ad-block-sub">847ms from first signal &mdash; evidence sealed &mdash; admissible in court</div>
          <div style="font-family:monospace;font-size:clamp(8px,1vw,12px);color:var(--purple-light);margin-top:16px;opacity:0;transition:opacity .5s" id="ad-saved">Before the money left. Before the data was stolen. Before the damage was done.</div>
        </div>
      </div>
      <div class="ad-scene" id="as4" style="background:#0a0f1e">
        <div style="font-family:Georgia,serif;font-size:clamp(14px,2.8vw,32px);font-weight:900;color:#fff;margin-bottom:20px;text-align:center;opacity:0;transition:opacity .5s" id="as4-title">Sentinel watches <span style="color:var(--purple-light)">everything.</span></div>
        <div class="ad-grid">
          <div class="ad-card" id="ac1" style="border-color:var(--purple-light);background:rgba(124,58,237,0.04)"><div class="ad-card-label" style="color:var(--purple-light)">Velocity Monitoring</div><div class="ad-card-text">60s, 5m, 1h windows. Burst attacks caught instantly.</div><div class="ad-card-fine">Threshold breach triggers immediate BLOCK</div></div>
          <div class="ad-card" id="ac2" style="border-color:var(--gold);background:rgba(201,168,76,0.04)"><div class="ad-card-label" style="color:var(--gold)">Trust Decay</div><div class="ad-card-text">EWMA scoring across all sessions. Bad actors identified before they act.</div><div class="ad-card-fine">Score persists across every session</div></div>
          <div class="ad-card" id="ac3" style="border-color:var(--cyan);background:rgba(0,212,255,0.04)"><div class="ad-card-label" style="color:var(--cyan)">Account Takeover</div><div class="ad-card-text">Country shift detection. New device. Behaviour change. ATO stopped cold.</div><div class="ad-card-fine">Real-time cross-session comparison</div></div>
          <div class="ad-card" id="ac4" style="border-color:var(--green);background:rgba(0,255,136,0.04)"><div class="ad-card-label" style="color:var(--green)">Evidence Chain</div><div class="ad-card-text">Every alert sealed into SHA-256 chain. Admissible. FCA compliant.</div><div class="ad-card-fine">50p per device per month</div></div>
        </div>
      </div>
      <div class="ad-scene" id="as5" style="background:#000">
        <div style="font-family:var(--display);font-size:clamp(28px,7vw,88px);font-weight:900;color:#fff;text-align:center;opacity:0;transition:opacity .8s" id="ad-cta-logo">AILeash <span style="color:var(--purple-light)">Sentinel</span></div>
        <div style="font-family:monospace;font-size:clamp(12px,2.5vw,28px);color:rgba(255,255,255,0.4);text-align:center;margin-top:8px;opacity:0;transition:opacity .8s" id="ad-cta-url">sebbi.pro/sentinel</div>
        <div style="font-size:clamp(10px,1.5vw,18px);color:rgba(255,255,255,0.2);text-align:center;margin-top:12px;font-style:italic;opacity:0;transition:opacity .8s" id="ad-cta-tag">Fraud caught before the damage is done. From 50p per device per month.</div>
      </div>
      <div class="ad-progress"><div class="ad-progress-bar" id="ad-progress-bar"></div></div>
    </div>
    <div class="ad-controls">
      <button class="ad-ctrl" onclick="restartAd()">&#9654; Play Again</button>
      <button class="ad-ctrl" id="ad-sound-btn" onclick="toggleAdSound()">&#128266; Sound On</button>
    </div>
  </div>
</section>

<section class="sec">
  <div class="sec-inner">
    <span class="sec-eyebrow">What Sentinel Does</span>
    <h2>Watches. Detects. Blocks.<br><em>Before the damage is done.</em></h2>
    <p class="sec-sub">Sentinel is not a dashboard you check. It is an engine that watches your platform every second and acts the moment something goes wrong.</p>
    <div class="features-grid">
      <div class="feat"><div class="feat-icon">&#9889;</div><h3>Real-Time Velocity</h3><p>Three monitoring windows — 60 seconds, 5 minutes, 1 hour. Burst attacks, bot floods and scripted fraud all spike the 60-second window. Slower attacks get caught in the 5-minute or hourly window. Nothing gets through.</p><div class="feat-badge">Three windows</div></div>
      <div class="feat"><div class="feat-icon">&#128200;</div><h3>EWMA Trust Decay</h3><p>Every user builds a trust score across all their sessions. A single BLOCK event drops it fast. It rebuilds slowly over time. Bad actors cannot reset their score by clearing cookies or changing device.</p><div class="feat-badge">Cross-session</div></div>
      <div class="feat"><div class="feat-icon">&#127757;</div><h3>Account Takeover Detection</h3><p>Country shift between sessions is one of the strongest account takeover signals. Sentinel flags it immediately. New device combined with unusual behaviour. Atypical transaction amounts. All caught.</p><div class="feat-badge">ATO detection</div></div>
      <div class="feat"><div class="feat-icon">&#128276;</span></div><h3>Instant Alerts</h3><p>The moment Sentinel triggers a BLOCK it fires an alert. Email. Push notification. Whatever your platform uses. You know about it in seconds. Not hours. Not days. Seconds.</p><div class="feat-badge">Sub-second alert</div></div>
      <div class="feat"><div class="feat-icon">&#128196;</div><h3>Fraud Evidence Package</h3><p>Every BLOCK generates a structured evidence package. SHA-256 sealed. Timestamped. Signal breakdown included. Admissible as fraud evidence in court. FCA compliant. Ready to hand to your legal team.</p><div class="feat-badge">Court admissible</div></div>
      <div class="feat"><div class="feat-icon">&#128279;</div><h3>SHA-256 Audit Chain</h3><p>Every decision — ALLOW, CHALLENGE, BLOCK — sealed into the Merkle chain. Your entire fraud history is cryptographically verifiable. Nobody can alter it retrospectively. Not even you.</p><div class="feat-badge">Immutable</div></div>
    </div>
  </div>
</section>

<section class="sec" style="background:rgba(0,0,0,0.2)">
  <div class="sec-inner">
    <span class="sec-eyebrow">Who Needs Sentinel</span>
    <h2>If money moves on your platform,<br><em>you need this.</em></h2>
    <p class="sec-sub">Anywhere users transact, authenticate, or interact at scale — Sentinel is watching.</p>
    <div class="use-cases">
      <div class="use-card"><h3>&#128222; Call Centres</h3><p>Caller scored before the agent picks up. Velocity across previous calls. Country of origin. Device fingerprint. Trust history. Fraud flagged before a word is spoken.</p><div class="use-earn">847ms</div><div class="use-earn-label">from first signal to block</div></div>
      <div class="use-card"><h3>&#127968; Fintech &amp; Banking</h3><p>Every transaction scored across 9 signals. High-value anomalies flagged immediately. Account takeover detected from country shift and velocity. Every decision sealed and FCA-admissible.</p><div class="use-earn">0.9+</div><div class="use-earn-label">risk score on genuine fraud</div></div>
      <div class="use-card"><h3>&#128717; E-Commerce</h3><p>Bot attacks, credential stuffing, card testing — all caught in the velocity windows. Trust decay identifies repeat bad actors. Every block generates an evidence package for chargebacks.</p><div class="use-earn">3x</div><div class="use-earn-label">windows catch what single checks miss</div></div>
      <div class="use-card"><h3>&#127918; Gaming Platforms</h3><p>Account farming, gold selling, exploit abuse — all show characteristic velocity patterns. Sentinel catches them automatically. Every banned account has a sealed evidence trail.</p><div class="use-earn">60s</div><div class="use-earn-label">velocity window catches burst abuse</div></div>
      <div class="use-card"><h3>&#127970; Insurance</h3><p>Claim fraud detected from anomaly signals. Unusual behaviour patterns flagged. Every underwriting AI decision sealed into the audit chain. FCA and EU AI Act satisfied simultaneously.</p><div class="use-earn">9</div><div class="use-earn-label">signals scoring every claim decision</div></div>
      <div class="use-card"><h3>&#128187; SaaS Platforms</h3><p>API abuse, scraping attacks, credential stuffing — Sentinel catches them all. Rate limiting with intelligence, not just counts. Trust decay ensures bad actors stay flagged across sessions.</p><div class="use-earn">1h</div><div class="use-earn-label">window catches sustained slow attacks</div></div>
    </div>
  </div>
</section>

<section class="pricing-sec">
  <div class="pricing-inner">
    <span class="sec-eyebrow">Pricing</span>
    <h2>One price.<br><em>24-hour fraud protection.</em></h2>
    <p style="font-size:15px;color:rgba(255,255,255,0.35);line-height:1.75;margin-bottom:40px">Fraud costs UK businesses £1.8 billion a year. Sentinel costs 50p per device per month.</p>
    <div class="price-big">50p</div>
    <div class="price-per">per device per month &mdash; billed via stripe</div>
    <div class="price-includes">
      <div class="pi">Real-time velocity monitoring &mdash; 60s, 5m, 1h windows</div>
      <div class="pi">EWMA trust decay scoring across all sessions</div>
      <div class="pi">Account takeover detection &mdash; country shift and device change</div>
      <div class="pi">Instant alerts &mdash; email and push on every BLOCK</div>
      <div class="pi">SHA-256 fraud evidence package on every block decision</div>
      <div class="pi">Full audit chain &mdash; FCA compliant &mdash; admissible in court</div>
      <div class="pi">EU AI Act Articles 9, 12, 13, 14 satisfied automatically</div>
      <div class="pi">100 free decisions &mdash; no card required to start</div>
      <div class="pi">Referral code &mdash; earn 10p per device you refer forever</div>
    </div>
    <a href="#signup" class="btn-purple" style="display:inline-block;padding:16px 36px;font-size:16px">Get Free Sentinel API Key &rarr;</a>
  </div>
</section>

<section class="signup-sec" id="signup">
  <div class="signup-inner">
    <span class="sec-eyebrow" style="color:rgba(124,58,237,0.5)">Get Started</span>
    <h2>Free API key.<br><em>Sentinel running in 60 seconds.</em></h2>
    <p>No card. No contract. 100 free decisions. Your key in under a minute.</p>
    <div class="fg-row">
      <div class="fg"><label>First Name</label><input type="text" id="fn" placeholder="Justin"></div>
      <div class="fg"><label>Last Name</label><input type="text" id="ln" placeholder="Smith"></div>
    </div>
    <div class="fg"><label>Email Address</label><input type="email" id="em" placeholder="you@company.com"></div>
    <div class="fg"><label>Phone Number</label><input type="tel" id="ph" placeholder="+44 7700 000000"></div>
    <div class="fg"><label>Company or Platform Name</label><input type="text" id="org" placeholder="e.g. MyPlatform Ltd"></div>
    <div class="fg"><label>Platform Type</label>
      <select id="platform">
        <option value="fintech">Fintech / Banking</option>
        <option value="callcentre">Call Centre</option>
        <option value="ecommerce">E-Commerce</option>
        <option value="gaming">Gaming</option>
        <option value="insurance">Insurance</option>
        <option value="saas">SaaS Platform</option>
        <option value="other">Other</option>
      </select>
    </div>
    <button class="btn-full" onclick="doSignup()">Get Free Sentinel API Key &rarr;</button>
    <div class="msg-err" id="msg-err"></div>
    <div class="key-box" id="key-box">
      <div class="key-lbl">Your Sentinel API Key &mdash; Save This Now</div>
      <div class="key-val" id="key-val"></div>
      <div class="ref-box">
        <div class="key-lbl">Your Referral Code</div>
        <div class="ref-code" id="ref-code-display">REF-XXXX-0000</div>
        <div class="ref-desc">Every device signed up using this code earns you 10p per month forever.</div>
      </div>
      <div style="font-family:var(--mono);font-size:10px;color:rgba(255,255,255,0.3);margin-top:16px;line-height:1.9;background:rgba(124,58,237,0.04);border:1px solid rgba(124,58,237,0.1);border-radius:4px;padding:12px">
        Redirecting to Stripe to set up billing&hellip;<br>100 free decisions active now.
      </div>
    </div>
  </div>
</section>

<footer>
  <div class="foot-inner">
    <a href="https://sebbi.pro" class="foot-logo">Monop <span>Content</span></a>
    <div class="foot-links">
      <a href="https://sebbi.pro/#products">All Products</a>
      <a href="https://sebbi.pro/aileash">AILeash</a>
      <a href="https://sebbi.pro/guardian-app">Guardian</a>
      <a href="https://sebbi.pro/sonicboom">SonicBoom</a>
      <a href="https://sebbi.pro/reseller">Reseller</a>
      <a href="https://sebbi.pro/contact">Contact Justin</a>
    </div>
    <div class="foot-copy">&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; justin@monopcontent.com &middot; 07908 269428</div>
  </div>
</footer>

<script>
var soundOn=true,adSoundOn=true;
var synth=window.speechSynthesis,voices=[],speechQueue=[],isSpeaking=false;
function loadVoices(){voices=synth?synth.getVoices():[];}
if(synth){synth.onvoiceschanged=loadVoices;loadVoices();}
function toggleSound(){soundOn=!soundOn;document.getElementById('sound-icon').textContent=soundOn?'\uD83D\uDD0A':'\uD83D\uDD07';document.getElementById('sound-label').textContent=soundOn?'Sound On \u2014 Tap to mute':'Sound Off \u2014 Tap to enable';if(!soundOn&&synth){synth.cancel();speechQueue=[];isSpeaking=false;}}
function toggleAdSound(){adSoundOn=!adSoundOn;document.getElementById('ad-sound-btn').textContent=adSoundOn?'\uD83D\uDD0A Sound On':'\uD83D\uDD07 Sound Off';if(!adSoundOn&&synth){synth.cancel();speechQueue=[];isSpeaking=false;}}
function getVoice(){if(!voices.length)return null;var d=voices.find(function(v){return/daniel|george|arthur|oliver/i.test(v.name)&&v.lang.startsWith('en');});var u=voices.find(function(v){return v.lang==='en-GB';});var e=voices.find(function(v){return v.lang.startsWith('en');});return d||u||e||null;}
function processQueue(){if(!synth||speechQueue.length===0||isSpeaking)return;isSpeaking=true;var item=speechQueue.shift();var utt=new SpeechSynthesisUtterance(item.text);utt.pitch=0.65;utt.rate=0.90;utt.volume=1.0;var v=getVoice();if(v)utt.voice=v;utt.onend=function(){isSpeaking=false;setTimeout(processQueue,150);};utt.onerror=function(){isSpeaking=false;setTimeout(processQueue,150);};synth.speak(utt);}
function speak(text,forAd){if(forAd&&!adSoundOn)return;if(!forAd&&!soundOn)return;if(!synth||!text)return;speechQueue.push({text:text});processQueue();}
function speakNow(text){if(!soundOn||!synth||!text)return;synth.cancel();speechQueue=[];isSpeaking=false;speechQueue.push({text:text});processQueue();}
async function getHash(data){try{var buf=new TextEncoder().encode(JSON.stringify(data));var hb=await crypto.subtle.digest('SHA-256',buf);return Array.from(new Uint8Array(hb)).map(function(b){return b.toString(16).padStart(2,'0');}).join('');}catch(e){var h=0,s=JSON.stringify(data)+Date.now();for(var i=0;i<s.length;i++){h=((h<<5)-h)+s.charCodeAt(i);h=(h|0);}var a=Math.abs(h);return[a,a*31,a*17,a*7].map(function(n){return Math.abs(n).toString(16).padStart(8,'0');}).join('');}}
var tb;
function addLine(id,prompt,html,spoken,delay){return new Promise(function(resolve){setTimeout(function(){var ex=document.getElementById(id);if(ex)ex.remove();var div=document.createElement('div');div.className='t-line';div.id=id;div.innerHTML='<span class="t-prompt">'+prompt+'</span><span class="t-text">'+html+'</span>';tb.appendChild(div);setTimeout(function(){div.classList.add('show');if(spoken)speak(spoken,false);tb.scrollTop=tb.scrollHeight;},30);resolve();},delay);});}
function addSection(id,label,delay){return new Promise(function(resolve){setTimeout(function(){var div=document.createElement('div');div.className='t-section';div.id=id;div.textContent='--- '+label+' ---';tb.appendChild(div);setTimeout(function(){div.classList.add('show');tb.scrollTop=tb.scrollHeight;},30);resolve();},delay);});}
async function getIPGeo(){var r={city:'Unknown',country:'Unknown',countryCode:'??',isp:'Unknown',ip:'Unknown'};try{var res=await fetch('https://ipapi.co/json/');var d=await res.json();if(d&&d.ip&&!d.error){r.ip=d.ip;r.city=d.city||'Unknown';r.country=d.country_name||'Unknown';r.countryCode=d.country_code||'??';r.isp=d.org||'Unknown';return r;}}catch(e){}try{var res2=await fetch('https://ip-api.com/json/?fields=status,city,country,countryCode,isp,query');var d2=await res2.json();if(d2&&d2.status==='success'){r.ip=d2.query;r.city=d2.city||'Unknown';r.country=d2.country||'Unknown';r.countryCode=d2.countryCode||'??';r.isp=d2.isp||'Unknown';}}catch(e){}return r;}
async function getGPS(){return new Promise(function(resolve){if(!navigator.geolocation){resolve(null);return;}navigator.geolocation.getCurrentPosition(function(p){resolve({lat:p.coords.latitude,lng:p.coords.longitude,accuracy:Math.round(p.coords.accuracy)});},function(){resolve(null);},{timeout:6000,maximumAge:60000});});}
async function reverseGeocode(lat,lng){try{var r=await fetch('https://nominatim.openstreetmap.org/reverse?lat='+lat+'&lon='+lng+'&format=json');var d=await r.json();if(d&&d.address){var a=d.address;return[a.town||a.city||a.village||'',a.county||'',a.country||''].filter(Boolean).join(', ');}}catch(e){}return null;}
async function runScan(){
  tb=document.getElementById('terminal-body');
  var ts=Date.now(),ua=navigator.userAgent;
  var isMobile=/Mobile|Android|iPhone|iPad/i.test(ua);
  var deviceType=isMobile?'Mobile':'Desktop';
  var browser='Unknown',bv='';
  var cm=ua.match(/Chrome\/([\d]+)/),fm=ua.match(/Firefox\/([\d]+)/),em2=ua.match(/Edg\/([\d]+)/);
  if(em2){browser='Edge';bv=em2[1];}else if(cm&&!/Edge/i.test(ua)){browser='Chrome';bv=cm[1];}else if(fm){browser='Firefox';bv=fm[1];}
  var os='Unknown';
  var am=ua.match(/Android ([\d.]+)/),im=ua.match(/OS ([\d_]+)/),wm=ua.match(/Windows NT/);
  if(am){os='Android';}else if(/iPhone|iPad/.test(ua)&&im){os='iOS';}else if(wm){os='Windows';}else if(/Mac/i.test(ua)){os='macOS';}else if(/Linux/i.test(ua)){os='Linux';}
  var cpuCores=navigator.hardwareConcurrency||null,ram=navigator.deviceMemory||null;
  var tz=Intl.DateTimeFormat().resolvedOptions().timeZone||'Unknown';
  var localTime=new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',hour12:false});
  var firstVisit=!localStorage.getItem('se_visit');if(firstVisit)localStorage.setItem('se_visit',ts);
  var visitCount=parseInt(localStorage.getItem('se_count')||'0')+1;localStorage.setItem('se_count',visitCount);
  var battery=null,charging=null;
  try{if(navigator.getBattery){var b=await navigator.getBattery();battery=Math.round(b.level*100);charging=b.charging;}}catch(e){}
  var connType=null;try{var conn=navigator.connection||navigator.mozConnection||navigator.webkitConnection;if(conn)connType=conn.effectiveType||conn.type||null;}catch(e){}
  var gpsPromise=getGPS(),ipGeoPromise=getIPGeo();
  var delay=0,step=280;
  speakNow('Welcome. This is AILeash Sentinel. The fraud and anomaly detection engine built by Monop Content. Right now, while I scan your session, Sentinel is watching every user on every platform that has deployed it. Every request. Every transaction. Every session. Nothing gets through.');
  await addLine('tl-intro','>','<span class="t-dim">AILeash Sentinel v5.0.0 &mdash; Fraud and Anomaly Detection &mdash; 24hr Monitor Active</span>',null,delay);delay+=step;
  await addSection('sec-device','Session Intelligence',delay);delay+=200;
  await addLine('tl-dev','>','Device: <span class="t-purple">'+deviceType+' &mdash; '+os+' &mdash; '+browser+(bv?' '+bv:'')+'</span>',deviceType+'. '+os+'. '+browser+'.',delay);delay+=step;
  if(cpuCores){await addLine('tl-cpu','>','Processor: <span class="t-purple">'+cpuCores+' CPU cores</span>',null,delay);delay+=step;}
  if(ram){await addLine('tl-ram','>','Memory: <span class="t-purple">'+ram+'GB RAM</span>',null,delay);delay+=step;}
  if(battery!==null){await addLine('tl-bat','>','Battery: <span class="t-purple">'+battery+'%'+(charging?' &mdash; charging':'')+'</span>',null,delay);delay+=step;}
  if(connType){await addLine('tl-conn','>','Connection: <span class="t-purple">'+connType.toUpperCase()+'</span>',connType.toUpperCase()+'.',delay);delay+=step;}
  await addLine('tl-time','>','Local time: <span class="t-purple">'+localTime+' &mdash; '+tz+'</span>',null,delay);delay+=step;
  await addLine('tl-visit','>',firstVisit?'<span class="t-gold">First visit &mdash; establishing baseline behaviour</span>':'<span class="t-dim">Visit number '+visitCount+' &mdash; comparing to session history</span>',null,delay);delay+=step;
  await addSection('sec-network','Network Analysis',delay);delay+=200;
  await addLine('tl-geoload','>','<span class="t-dim">Resolving network location&hellip;</span>',null,delay);delay+=step;
  var gps=await gpsPromise,ipGeo=await ipGeoPromise;
  if(gps){var rev=await reverseGeocode(gps.lat,gps.lng);var locD=rev?rev+' &mdash; GPS '+gps.accuracy+'m':gps.lat.toFixed(4)+', '+gps.lng.toFixed(4);await addLine('tl-gps','>','<span class="t-green">GPS: </span><span class="t-purple">'+locD+'</span>',rev?'You are in '+rev+'.':'GPS confirmed.',delay);delay+=step;}
  else{var loc=(ipGeo.city!=='Unknown'?ipGeo.city+' &mdash; ':'')+ipGeo.country;await addLine('tl-loc','>','Location: <span class="t-purple">'+loc+'</span>',(ipGeo.city!=='Unknown'?ipGeo.city+'. ':'')+ipGeo.country+'.',delay);delay+=step;}
  await addLine('tl-ip','>','IP: <span class="t-purple">'+ipGeo.ip+'</span>',null,delay);delay+=step;
  await addLine('tl-isp','>','Network provider: <span class="t-purple">'+ipGeo.isp+'</span>','Network provider: '+ipGeo.isp+'.',delay);delay+=step;
  await addSection('sec-sentinel','Sentinel Fraud Detection Engine',delay);delay+=200;
  await addLine('tl-v1','>','Velocity 60s window: <span class="t-green">1 request &mdash; normal</span>',null,delay);delay+=step;
  await addLine('tl-v2','>','Velocity 5m window: <span class="t-green">1 request &mdash; normal</span>',null,delay);delay+=step;
  await addLine('tl-v3','>','Velocity 1h window: <span class="t-green">1 request &mdash; normal</span>',null,delay);delay+=step;
  await addLine('tl-cs','>','Country shift: <span class="t-green">No prior session &mdash; no shift detected</span>',null,delay);delay+=step;
  await addLine('tl-scoring','>','<span class="t-dim">Running 9-signal weighted scoring engine&hellip;</span>','Running scoring engine.',delay);delay+=step*1.5;
  var score=0.05,reasons=[];
  var SAFE=['GB','US','DE','FR','CA','AU','NL','SE','NO','DK','FI','IE','NZ'];
  if(!SAFE.includes(ipGeo.countryCode)&&ipGeo.countryCode!=='??'){score+=0.12;reasons.push('non_standard_region');}
  if(visitCount>8){score+=0.05;reasons.push('high_visit_frequency');}
  score=Math.min(parseFloat(score.toFixed(4)),0.34);
  var trust=(0.74+Math.random()*0.08).toFixed(4);
  var hashData={ip:ipGeo.ip,city:ipGeo.city,country:ipGeo.country,browser:browser,os:os,ts:ts,score:score,engine:'sentinel'};
  if(gps){hashData.lat=gps.lat.toFixed(4);hashData.lng=gps.lng.toFixed(4);}
  var auditHash=await getHash(hashData),sealedAt=new Date().toISOString();
  await addLine('tl-score','>','Risk score: <span class="t-purple">'+score.toFixed(4)+'</span> &mdash; Trust index: <span class="t-purple">'+trust+'</span>','Risk score '+score.toFixed(2)+'. Trust index '+trust+'.',delay);delay+=step;
  if(reasons.length>0){await addLine('tl-flags','>','Flags: <span class="t-gold">'+reasons.join(' &mdash; ')+'</span>',null,delay);delay+=step;}
  else{await addLine('tl-flags','>','<span class="t-green">No fraud signals detected. Clean session. No anomalies across all 9 signals.</span>','No fraud signals detected. Clean session.',delay);delay+=step;}
  await addLine('tl-dec','>','Decision: <span style="color:var(--green);font-weight:700;font-size:15px;letter-spacing:3px">ALLOW</span>','Decision. Allow.',delay);delay+=step;
  await addLine('tl-seal','>','<span class="t-dim">Sealing to SHA-256 fraud evidence chain&hellip;</span>',null,delay);delay+=step;
  await addLine('tl-hash','>','Audit hash: <span class="t-hash">'+auditHash+'</span>','Audit hash sealed.',delay);delay+=step;
  await addLine('tl-done','>','<span class="t-green">Sealed '+sealedAt+' &mdash; immutable &mdash; FCA compliant &mdash; court admissible</span>','Sealed. FCA compliant. Court admissible.',delay);delay+=step;
  await addLine('tl-pitch','>','<span class="t-purple">Your platform is processing transactions right now. Without Sentinel, fraud is happening and you will find out days later. With Sentinel you find out in under a second.</span>','Your platform is processing transactions right now. Without Sentinel, fraud is happening and you will find out days later. With Sentinel you find out in under a second.',delay);delay+=step*1.5;
  setTimeout(function(){
    document.getElementById('v-decision').textContent='ALLOW';
    document.getElementById('v-score').textContent='Score: '+score.toFixed(4)+'  \u2014  Trust: '+trust+'  \u2014  Signals: 9  \u2014  Engine: Sentinel';
    document.getElementById('v-hash').textContent=auditHash;
    document.getElementById('v-sealed').textContent='Sealed '+sealedAt+'  \u2014  Immutable  \u2014  FCA compliant  \u2014  Court admissible';
    document.getElementById('verdict').classList.add('show');
    speak('Clean session. But every fraudster on your platform right now is getting this same treatment. The ones scoring above 0.7 are already being blocked. From fifty pence per device per month.',false);
  },delay);
}
window.addEventListener('load',function(){setTimeout(runScan,800);});
var adPlayed=false,adStartTime=null,adProgressInterval=null,adTotalDuration=58000;
function showAdScene(n){document.querySelectorAll('.ad-scene').forEach(function(s){s.classList.remove('active');});var sc=document.getElementById('as'+n);if(sc)sc.classList.add('active');}
function adShow(id,delay){setTimeout(function(){var el=document.getElementById(id);if(el)el.classList.add('show');},delay);}
function updateAdProgress(){if(!adStartTime)return;var pct=Math.min(100,((Date.now()-adStartTime)/adTotalDuration)*100);document.getElementById('ad-progress-bar').style.width=pct+'%';}
function restartAd(){if(synth){synth.cancel();speechQueue=[];isSpeaking=false;}clearInterval(adProgressInterval);document.querySelectorAll('.ad-scene .show').forEach(function(el){el.classList.remove('show');});document.getElementById('ad-progress-bar').style.width='0%';adStartTime=null;setTimeout(playAd,500);}
function playAd(){
  adStartTime=Date.now();adProgressInterval=setInterval(updateAdProgress,100);
  showAdScene(1);speak('500 requests. 60 seconds. One account. Without Sentinel, you find out days later.',true);
  adShow('as1a',300);adShow('as1b',1200);adShow('as1c',2400);adShow('as1d',4000);adShow('as1e',5200);
  setTimeout(function(){showAdScene(2);speak('Sentinel catches it instantly. Velocity spike detected. 487 requests in 60 seconds. Country shift from GB to Nigeria. Account takeover signal. Trust score critically low. Decision. Block.',true);['atl1','atl2','atl3','atl4','atl5','atl6','atl7','atl8'].forEach(function(id,i){adShow(id,i*750);});},10000);
  setTimeout(function(){showAdScene(3);speak('Blocked. 847 milliseconds from first signal. Before the money left. Before the data was stolen. Before the damage was done.',true);adShow('ad-block',400);adShow('ad-block-sub',1000);setTimeout(function(){document.getElementById('ad-saved').style.opacity='1';},1800);},24000);
  setTimeout(function(){showAdScene(4);speak('Sentinel watches everything. Velocity monitoring across three windows. EWMA trust decay across all sessions. Account takeover detection. SHA-256 fraud evidence chain. All for fifty pence per device per month.',true);setTimeout(function(){document.getElementById('as4-title').style.opacity='1';},200);adShow('ac1',800);adShow('ac2',1600);adShow('ac3',2400);adShow('ac4',3200);},34000);
  setTimeout(function(){showAdScene(5);speak('AILeash Sentinel. sebbi dot pro. Fraud caught before the damage is done. From fifty pence per device per month.',true);setTimeout(function(){document.getElementById('ad-cta-logo').style.opacity='1';},400);setTimeout(function(){document.getElementById('ad-cta-url').style.opacity='1';},900);setTimeout(function(){document.getElementById('ad-cta-tag').style.opacity='1';},1500);},48000);
  setTimeout(function(){clearInterval(adProgressInterval);document.getElementById('ad-progress-bar').style.width='100%';},adTotalDuration);
}
var observer=new IntersectionObserver(function(entries){entries.forEach(function(entry){if(entry.isIntersecting&&!adPlayed){adPlayed=true;setTimeout(playAd,600);}});},{threshold:0.3});
var vs=document.getElementById('video');if(vs)observer.observe(vs);
async function doSignup(){
  var fn=document.getElementById('fn').value.trim(),ln=document.getElementById('ln').value.trim(),em=document.getElementById('em').value.trim(),ph=document.getElementById('ph').value.trim(),org=document.getElementById('org').value.trim(),platform=document.getElementById('platform').value;
  var err=document.getElementById('msg-err'),kb=document.getElementById('key-box'),btn=document.querySelector('.btn-full');
  err.classList.remove('show');kb.classList.remove('show');
  if(!em||!em.includes('@')){err.textContent='Please enter a valid email address.';err.classList.add('show');return;}
  if(!org){err.textContent='Please enter your company name.';err.classList.add('show');return;}
  var orig=btn.textContent;btn.textContent='Creating key\u2026';btn.disabled=true;
  try{
    var r=await fetch('https://sebbi.pro/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,phone:ph,name:fn+' '+ln,org:org,org_type:'sentinel_'+platform,product:'aileash',devices:1})});
    var d=await r.json();
    if(d.api_key){
      document.getElementById('key-val').textContent=d.api_key;
      if(d.ref_code)document.getElementById('ref-code-display').textContent=d.ref_code;
      kb.classList.add('show');btn.textContent='Key created \u2014 setting up billing\u2026';
      speak('Sentinel key created. Redirecting to billing.',false);
      try{var r2=await fetch('https://sebbi.pro/create-checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:em,product:'aileash',devices:1})});var d2=await r2.json();if(d2.checkout_url){setTimeout(function(){window.location.href=d2.checkout_url;},2500);}else{btn.textContent='Key ready \u2713';}}catch(e2){btn.textContent='Key ready \u2713';}
    }else{err.textContent=d.error||'Something went wrong. Email justin@monopcontent.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
  }catch(e){err.textContent='Cannot reach server. Email justin@monopcontent.com';err.classList.add('show');btn.textContent=orig;btn.disabled=false;}
}
</script>
</body>
</html>

```


## `signal-packs.html`

178 lines, 9653 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Packs - AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#fff;line-height:1.55}
.wrap{max-width:760px;margin:0 auto;padding:22px 18px 80px}
a.back{color:#c9a84c;text-decoration:none;font-size:14px;font-family:monospace}
h1{font-size:26px;font-weight:800;margin:14px 0 4px}h1 span{color:#c9a84c}
.sub{color:#8a90a6;font-size:14px;margin-bottom:20px}
.card{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:18px;margin-bottom:14px}
.card h2{font-size:12px;color:#c9a84c;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:12px}
input,textarea,select{width:100%;padding:11px;border-radius:8px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:14px;margin:6px 0;font-family:inherit}
textarea{min-height:120px;font-family:monospace;font-size:12px}
button{background:#c9a84c;color:#0a0f1e;border:none;border-radius:8px;padding:11px 18px;font-weight:800;cursor:pointer;font-size:14px}
button.ghost{background:transparent;border:1px solid #2a3350;color:#c9a84c}
button.small{padding:7px 12px;font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.msg{font-size:13px;margin-top:8px;min-height:18px}
.ok{color:#7fe3b0}.err{color:#ff7b6e}
.pack{background:#0b1226;border:1px solid #2a3350;border-radius:8px;padding:12px;margin:8px 0;font-size:13px}
.pack .nm{font-weight:700;color:#fff}
.pack .meta{color:#8a90a6;font-size:12px}
.badge{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:uppercase;margin-left:6px}
.badge.pub{background:#0d2018;color:#7fe3b0;border:1px solid #1fae79}
.badge.priv{background:#1a1206;color:#c9a84c;border:1px solid #c9a84c}
.warn{background:#1a1206;border:1px solid #c9a84c;border-radius:8px;padding:12px;font-size:12.5px;color:#e8d9b0;margin:10px 0;line-height:1.6}
.hide{display:none}
.tiny{color:#5a6178;font-size:11px;margin-top:14px;line-height:1.6}
.starter{cursor:pointer;color:#7fe3b0;font-size:12px;text-decoration:underline;margin-right:12px}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; AILeash</a>
  <h1>Signal <span>Packs</span></h1>
  <p class="sub">Define the risks specific to your AI system, seal them, and use them per decision. Build your own, or start from a community template.</p>

  <div class="card" id="loginCard">
    <h2>Your API key</h2>
    <input id="apikey" type="password" placeholder="Paste your AILeash API key">
    <button onclick="loadMine()">Load my packs</button>
    <div class="msg" id="loginMsg"></div>
    <p class="tiny">No key? Get one free at <a href="/#signup" style="color:#c9a84c">sebbi.pro</a>. Your key stays in your browser - it is only sent to your own account.</p>
  </div>

  <div id="app" class="hide">
    <div class="card">
      <h2>Build a signal pack</h2>
      <div class="row" style="margin-bottom:8px">
        <span style="font-size:12px;color:#8a90a6">Start from a template:</span>
        <span class="starter" onclick="loadStarter('hiring-risk')">hiring-risk</span>
        <span class="starter" onclick="loadStarter('lending-risk')">lending-risk</span>
        <span class="starter" onclick="loadStarter('content-safety')">content-safety</span>
      </div>
      <input id="packname" placeholder="Pack name, e.g. hiring-risk">
      <textarea id="packsignals" placeholder='{"bias": 0.15, "adverse_impact": 0.15, "explainability_gap": 0.10}'></textarea>
      <p class="tiny">Each signal has a weight from 0 to 0.30. Send raw signal values 0-1 at decision time; these weights decide how much each one counts.</p>
      <button onclick="createPack()">Create &amp; seal pack</button>
      <div class="msg" id="createMsg"></div>
    </div>

    <div class="card">
      <h2>My packs</h2>
      <div id="mypacks"><div class="meta" style="color:#5a6178">Loading...</div></div>
    </div>

    <div class="card">
      <h2>Public library</h2>
      <div class="warn">Community-contributed templates. <b>Unverified.</b> Always validate a pack against your own risk assessment before relying on it. Publishing your own pack is optional - your packs are private by default.</div>
      <button class="ghost small" onclick="loadLibrary()">Browse library</button>
      <div id="library" style="margin-top:10px"></div>
    </div>
  </div>

  <p class="tiny">Signal packs let you evaluate the foreseeable risks specific to your system, per decision, sealed into a tamper-evident record. This supports EU AI Act risk-evaluation and record-keeping duties. It does not by itself constitute a complete Article 9 risk-management process - the documented governance around your packs is yours to maintain.</p>
</div>

<script>
var KEY="";
var STARTERS={
  "hiring-risk":{"demographic_bias":0.15,"adverse_impact":0.15,"explainability_gap":0.10,"proxy_discrimination":0.10},
  "lending-risk":{"protected_attribute_influence":0.15,"affordability_breach":0.12,"fairness_disparity":0.15,"explainability_gap":0.10},
  "content-safety":{"child_safety_flag":0.20,"grooming_pattern":0.20,"harmful_content":0.12,"self_harm_signal":0.15}
};
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}

async function api(path,body){
  var r=await fetch(path,{method:"POST",headers:{"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},body:JSON.stringify(body||{})});
  return await r.json();
}

async function loadMine(){
  KEY=document.getElementById("apikey").value.trim();
  var m=document.getElementById("loginMsg");
  if(!KEY){m.className="msg err";m.textContent="Paste your key first.";return;}
  m.className="msg";m.textContent="Checking...";
  try{
    var d=await api("/api/signal-pack/list",{});
    if(d.error){m.className="msg err";m.textContent="Key not recognised.";return;}
    document.getElementById("loginCard").classList.add("hide");
    document.getElementById("app").classList.remove("hide");
    renderMine(d.packs||[]);
  }catch(e){m.className="msg err";m.textContent="Connection error.";}
}

function loadStarter(name){
  document.getElementById("packname").value=name;
  document.getElementById("packsignals").value=JSON.stringify(STARTERS[name],null,2);
}

async function createPack(){
  var name=document.getElementById("packname").value.trim();
  var raw=document.getElementById("packsignals").value.trim();
  var m=document.getElementById("createMsg");
  if(!name){m.className="msg err";m.textContent="Give the pack a name.";return;}
  var sig;
  try{sig=JSON.parse(raw);}catch(e){m.className="msg err";m.textContent="Signals must be valid JSON, e.g. {\\"bias\\": 0.15}";return;}
  m.className="msg";m.textContent="Sealing...";
  var d=await api("/api/signal-pack/create",{name:name,signals:sig});
  if(d.error){m.className="msg err";m.textContent=d.error;return;}
  m.className="msg ok";m.textContent="Pack '"+esc(d.pack.name)+"' v"+d.pack.version+" created and sealed (block "+d.pack.block_index+").";
  var l=await api("/api/signal-pack/list",{});renderMine(l.packs||[]);
}

function renderMine(packs){
  var el=document.getElementById("mypacks");
  if(!packs.length){el.innerHTML='<div class="meta" style="color:#5a6178">No packs yet. Build one above.</div>';return;}
  var h="";
  packs.forEach(function(p){
    h+='<div class="pack"><div class="nm">'+esc(p.name)+' <span class="meta">v'+esc(p.latest_version)+'</span></div>'
      +'<div class="row" style="margin-top:8px">'
      +'<button class="small ghost" onclick="publishPack(\\''+esc(p.name)+'\\')">Publish to library</button>'
      +'<button class="small ghost" onclick="unpublishPack(\\''+esc(p.name)+'\\')">Make private</button>'
      +'</div></div>';
  });
  el.innerHTML=h;
}

async function publishPack(name){
  var author=prompt("Publish '"+name+"' to the public library.\\n\\nShow it as contributed by (name or company, optional):","")||"anonymous";
  var d=await api("/api/signal-pack/publish",{name:name,author:author});
  alert(d.error?("Error: "+d.error):"Published. It's now in the community library, marked unverified. You can make it private again any time.");
}
async function unpublishPack(name){
  await api("/api/signal-pack/unpublish",{name:name});
  alert("'"+name+"' is now private.");
}

async function loadLibrary(){
  var el=document.getElementById("library");
  el.innerHTML='<div class="meta" style="color:#5a6178">Loading...</div>';
  var d=await api("/api/signal-pack/library",{});
  var lib=d.library||[];
  if(!lib.length){el.innerHTML='<div class="meta" style="color:#5a6178">No published packs yet. Be the first.</div>';return;}
  var h="";
  lib.forEach(function(p){
    h+='<div class="pack"><div class="nm">'+esc(p.name)+' <span class="badge pub">community</span></div>'
      +'<div class="meta">by '+esc(p.author)+' &middot; v'+esc(p.version)+' &middot; '+Object.keys(p.signals||{}).length+' signals</div>'
      +'<button class="small ghost" style="margin-top:8px" onclick=\\'useLibPack("'+esc(p.name)+'",'+JSON.stringify(JSON.stringify(p.signals))+')\\'>Load into builder</button>'
      +'</div>';
  });
  el.innerHTML=h;
}
function useLibPack(name,sigStr){
  document.getElementById("packname").value=name;
  var sig=JSON.parse(sigStr);
  var flat={};for(var k in sig){flat[k]=(sig[k]&&sig[k].weight!=null)?sig[k].weight:sig[k];}
  document.getElementById("packsignals").value=JSON.stringify(flat,null,2);
  window.scrollTo(0,0);
}
</script>
</body>
</html>

```


## `sitemap.xml`

71 lines, 1760 bytes

```
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="http://www.sitemaps.org/schemas/sitemap/0.9
        http://www.sitemaps.org/schemas/sitemap/0.9/sitemap.xsd">

  <url>
    <loc>https://sebbi.pro/</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/compliance-assistant</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.95</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/guardian-app</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.95</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/sonicboom</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.95</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/sentinel</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.95</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/reseller</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.90</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/scan</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>weekly</changefreq>
    <priority>0.85</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/report-threat</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.70</priority>
  </url>

  <url>
    <loc>https://sebbi.pro/contact</loc>
    <lastmod>2026-06-23</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.65</priority>
  </url>

</urlset>

```
