# Codebase — part 35 of 45

Contains:
- `console.html`
- `contact.html`
- `copyright.txt`
- `data-protection.html`


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

125 lines, 13231 bytes

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
      <tr><td>Request records</td><td>For each request that seals a record: the calling IP address and forwarded chain, user agent, origin, referer, language and request id. Optionally, end-user context the customer attaches (IP, user agent, session id, actor). Held <b>off the chain</b>; only a SHA-256 fingerprint of each is sealed</td><td>Security, fraud prevention and the machine-proof decision report customers request for their own records · legitimate interest; customers' legitimate interest in complete evidence</td></tr>
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
  <p>Request records (§2) are kept for two years, then the raw details — IP address, user agent and headers — are deleted automatically. The sealed fingerprint remains, so the chain stays intact and a report for that block states plainly that the details have expired. Because these details were never written into the chain, an erasure request can be honoured for them in full.</p>
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
