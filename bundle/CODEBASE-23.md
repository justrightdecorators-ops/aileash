# Codebase — part 23 of 28

Contains:
- `pack.html`
- `pay-check.html`
- `registry.html`
- `report-threat.html`
- `requirements.txt`


## `pack.html`

720 lines, 28330 bytes

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Evidence pack — sebbi.pro</title>
<meta name="description" content="The document you hand an auditor. It does not summarise your chain, it re-verifies it: every block in the period rehashed and compared to the hash sealed at the time.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#EEF1F0;
  --paper-2:#E3E8E7;
  --ink:#16232B;
  --ink-soft:#5A6E77;
  --rule:#CBD5D3;
  --slate:#2E6B72;
  --ochre:#B4700F;
  --stop:#8C2F1E;
  --good:#1E6B4A;
  --sans:"IBM Plex Sans",system-ui,-apple-system,sans-serif;
  --cond:"IBM Plex Sans Condensed","IBM Plex Sans",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--paper);color:var(--ink);
  font:16px/1.6 var(--sans);
  font-variant-numeric:tabular-nums;
}
.wrap{max-width:860px;margin:0 auto;padding:0 22px}
a{color:var(--slate)}
:focus-visible{outline:2px solid var(--ochre);outline-offset:3px}
code{font:500 13.5px var(--mono);background:#fff;border:1px solid var(--rule);
  padding:1px 5px;word-break:break-all}

/* ---- masthead ---- */
.top{border-bottom:1px solid var(--rule);padding:18px 0}
.top .wrap{display:flex;align-items:baseline;justify-content:space-between;gap:16px}
.brand{font:600 15px/1 var(--cond);letter-spacing:.14em;text-transform:uppercase;
  text-decoration:none;color:var(--ink)}
.brand span{color:var(--ochre)}
.top nav{font-size:13.5px;color:var(--ink-soft)}
.top nav a{margin-left:16px;text-decoration:none}
.top nav a:hover{text-decoration:underline}

/* ---- hero ---- */
.hero{padding:56px 0 44px;border-bottom:1px solid var(--rule)}
.eyebrow{
  font:600 12px/1 var(--cond);letter-spacing:.2em;text-transform:uppercase;
  color:var(--slate);margin-bottom:18px;
}
h1{
  font:700 clamp(34px,7.2vw,60px)/1.02 var(--cond);
  letter-spacing:-.015em;margin:0 0 18px;max-width:16ch;
}
.lede{font-size:18.5px;line-height:1.55;max-width:56ch;color:var(--ink);margin:0 0 28px}
.lede b{font-weight:600}

/* the claim/check contrast: the signature line of the product */
.contrast{
  background:#fff;border:1px solid var(--rule);margin:0 0 26px;
  display:grid;grid-template-columns:1fr 1fr;
}
@media (max-width:640px){.contrast{grid-template-columns:1fr}}
.contrast div{padding:16px 18px}
.contrast div+div{border-left:1px solid var(--rule)}
@media (max-width:640px){.contrast div+div{border-left:0;border-top:1px solid var(--rule)}}
.contrast .tag{
  font:600 10.5px/1 var(--cond);letter-spacing:.16em;text-transform:uppercase;
  display:block;margin-bottom:7px;
}
.contrast .a .tag{color:var(--stop)}
.contrast .b .tag{color:var(--good)}
.contrast p{margin:0;font-size:15px;line-height:1.5}
.contrast .a p{color:var(--ink-soft)}

.buyrow{display:flex;flex-wrap:wrap;align-items:center;gap:16px}
.dl{
  display:inline-block;background:var(--ink);color:var(--paper);
  font:600 15px/1 var(--sans);letter-spacing:.01em;
  padding:15px 24px;border:1px solid var(--ink);border-radius:2px;
  text-decoration:none;cursor:pointer;
  transition:background .12s ease,color .12s ease;
}
.dl:hover{background:var(--ochre);border-color:var(--ochre);color:#fff}
.dl:disabled{opacity:.45;cursor:default}
.price{font-size:14.5px;color:var(--ink-soft)}
.price b{color:var(--ink);font-weight:600}

/* ---- generic section ---- */
section{padding:46px 0;border-bottom:1px solid var(--rule)}
h2{
  font:700 clamp(22px,3.6vw,30px)/1.15 var(--cond);
  letter-spacing:-.01em;margin:0 0 8px;
}
.sub{color:var(--ink-soft);font-size:15px;margin:0 0 26px;max-width:60ch}

/* ---- the four checks ---- */
.checks{border-top:1px solid var(--rule)}
.chk{
  display:grid;grid-template-columns:auto 1fr;gap:0 20px;
  padding:18px 0;border-bottom:1px solid var(--rule);align-items:start;
}
.chk .mark{
  font:600 11px/1.6 var(--cond);letter-spacing:.16em;text-transform:uppercase;
  color:#fff;background:var(--slate);padding:2px 8px;border-radius:2px;
  white-space:nowrap;margin-top:3px;
}
.chk h3{font:600 17px/1.4 var(--sans);margin:0 0 4px}
.chk p{margin:0;font-size:15px;color:var(--ink-soft)}

/* ---- build your pack ---- */
.build{background:var(--paper-2)}
.form{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 6px}
.form input,.form select{
  flex:1 1 200px;min-width:0;background:#fff;border:1px solid var(--rule);
  padding:14px;font:400 15px var(--sans);color:var(--ink);border-radius:2px;
}
.form select{font:500 15px var(--mono)}
.form input:focus,.form select:focus{outline:none;box-shadow:inset 0 0 0 2px var(--ochre)}
.form button{
  flex:0 0 auto;background:var(--ink);color:var(--paper);border:1px solid var(--ink);
  padding:14px 22px;font:600 15px var(--sans);border-radius:2px;cursor:pointer;
}
.form button:hover{background:var(--ochre);border-color:var(--ochre);color:#fff}
.form button:disabled{opacity:.45;cursor:default}
.scoperow{display:flex;gap:18px;flex-wrap:wrap;font-size:14px;color:var(--ink-soft);
  margin:2px 0 16px}
.scoperow label{display:flex;align-items:center;gap:7px;cursor:pointer}
.msg{font-size:14.5px;min-height:22px;margin:0 0 14px}
.msg .yes{color:var(--good);font-weight:600}
.msg .no{color:var(--stop);font-weight:600}

.result{background:#fff;border:1px solid var(--rule);display:none}
.result.on{display:block}
.result .hd{
  font:600 11px/1 var(--cond);letter-spacing:.16em;text-transform:uppercase;
  padding:12px 14px;border-bottom:1px solid var(--rule);color:var(--ink-soft);
  display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
}
.result .hd .acts{display:flex;gap:8px}
.result .hd button{
  background:transparent;border:1px solid var(--rule);color:var(--ink);
  font:600 10.5px/1 var(--cond);letter-spacing:.14em;text-transform:uppercase;
  padding:7px 10px;border-radius:2px;cursor:pointer;
}
.result .hd button:hover{border-color:var(--ochre);color:var(--ochre)}
.result iframe{display:block;width:100%;height:640px;border:0;background:#0a0f1e}
.jsonbox{padding:14px;font:400 12.5px/1.7 var(--mono);white-space:pre-wrap;
  word-break:break-all;max-height:520px;overflow:auto;display:none}
.jsonbox.on{display:block}

/* ---- headline read ---- */
.figs{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--rule);
  border:1px solid var(--rule);margin:0 0 18px}
@media (max-width:640px){.figs{grid-template-columns:1fr}}
.figs div{background:#fff;padding:14px 16px}
.figs .n{font:700 26px/1.1 var(--cond);letter-spacing:-.01em}
.figs .n.ok{color:var(--good)} .figs .n.bad{color:var(--stop)}
.figs .l{font-size:12.5px;color:var(--ink-soft);margin-top:4px}

/* ---- routes ---- */
table.rt{width:100%;border-collapse:collapse;font-size:14px;margin-top:4px}
table.rt th,table.rt td{text-align:left;padding:10px 12px 10px 0;
  border-bottom:1px solid var(--rule);vertical-align:top}
table.rt th{font:600 10.5px/1.6 var(--cond);letter-spacing:.16em;
  text-transform:uppercase;color:var(--ink-soft)}
table.rt td.r{font:500 13px var(--mono);white-space:nowrap;padding-right:16px}
table.rt td.a{color:var(--ink-soft);white-space:nowrap;font-size:13px}

/* ---- limits ---- */
ul.limits{margin:0;padding:0;list-style:none}
ul.limits li{
  padding:14px 0 14px 22px;border-bottom:1px solid var(--rule);
  font-size:15px;color:var(--ink-soft);position:relative;
}
ul.limits li::before{content:"—";position:absolute;left:0;color:var(--stop)}
ul.limits li:first-child{border-top:1px solid var(--rule)}

/* ---- key ---- */
.key{background:var(--paper-2)}
.terms{font-size:13.5px;color:var(--ink-soft);margin:16px 0 0;max-width:62ch}

/* ---- steps ---- */
.steps{counter-reset:s;margin:0;padding:0;list-style:none}
.steps li{margin:0 0 22px}
.steps li h3{
  font:600 15px/1.4 var(--sans);margin:0 0 8px;
  display:flex;align-items:baseline;gap:10px;
}
.steps li h3::before{
  counter-increment:s;content:counter(s);
  font:600 11px/1 var(--cond);letter-spacing:.1em;
  color:#fff;background:var(--ink);padding:4px 7px;border-radius:2px;
}
pre.cmd{
  background:#fff;border:1px solid var(--rule);padding:14px 16px;margin:0 0 10px;
  font:500 13.5px/1.75 var(--mono);overflow-x:auto;
}
pre.cmd .c{color:var(--ink-soft)}

/* ---- footer ---- */
.foot{padding:30px 0 44px;font-size:13.5px;color:var(--ink-soft)}
</style>
</head>
<body>

<header class="top">
  <div class="wrap">
    <a class="brand" href="/">sebbi<span>.pro</span></a>
    <nav>
      <a href="/x/pack/spec">Read the spec</a>
      <a href="#build">Build one</a>
      <a href="#key">Get a key</a>
    </nav>
  </div>
</header>

<div class="hero">
  <div class="wrap">
    <div class="eyebrow">Evidence pack</div>
    <h1>The document you hand the auditor.</h1>
    <p class="lede">Everything else on this platform produces evidence. This produces
    the paperwork. Pick a period and it does not summarise your chain — it
    <b>re-verifies</b> it. Every block in the range is rehashed from its stored
    contents using the same function that sealed it, and compared to the hash
    recorded at the time.</p>

    <div class="contrast">
      <div class="a">
        <span class="tag">A summary</span>
        <p>A number your own system printed about itself. The auditor has to take
        your word for it, and so do you.</p>
      </div>
      <div class="b">
        <span class="tag">A re-verification</span>
        <p>Every block recomputed and compared. A check anyone can repeat, on
        their own machine, without asking you.</p>
      </div>
    </div>

    <div class="buyrow">
      <a class="dl" href="#build">Build a pack</a>
      <span class="price">Included with any <b>sebbi.pro</b> key &middot; free for 90 days</span>
    </div>
  </div>
</div>

<section>
  <div class="wrap">
    <h2>What it actually checks</h2>
    <p class="sub">Four separate checks. Each one can fail on its own, and the pack
    says so plainly rather than quietly rounding it away.</p>

    <div class="checks">
      <div class="chk">
        <span class="mark">Hash</span>
        <div>
          <h3>Every block rehashed</h3>
          <p>SHA-256 over the stored prev_hash, timestamp, event and result —
          recomputed row by row and compared to the hash sealed at the time. If a
          single character of a record was edited after the fact, its hash no
          longer matches and the block is named.</p>
        </div>
      </div>
      <div class="chk">
        <span class="mark">Links</span>
        <div>
          <h3>The links walked end to end</h3>
          <p>Each block records the hash of the one before it. The pack walks that
          line through the whole period. A block removed from the middle breaks the
          link on either side of the hole, and the break is reported with its
          number.</p>
        </div>
      </div>
      <div class="chk">
        <span class="mark">Entry</span>
        <div>
          <h3>The link into the period</h3>
          <p>The first block in your period is checked against the last block
          before it — so a pack cannot be made clean by choosing a start date that
          skips over the problem. Where the chain starts at the beginning, it says
          so: intact from genesis.</p>
        </div>
      </div>
      <div class="chk">
        <span class="mark">Receipts</span>
        <div>
          <h3>Gapless receipt numbers</h3>
          <p>For a single key, receipts are numbered with no gaps by construction.
          The pack checks the sequence from first to last. A missing number is not
          a lost record — it is a record that left this chain, and it is listed.</p>
        </div>
      </div>
    </div>
  </div>
</section>

<section class="build" id="build">
  <div class="wrap">
    <h2>Build your pack</h2>
    <p class="sub">Runs against your own chain, right here in the browser. Nothing
    is sealed and nothing is charged until you press Seal it — preview as many
    times as you like.</p>

    <div class="form">
      <input id="key" type="text" autocomplete="off" spellcheck="false"
             placeholder="Your sebbi.pro key" aria-label="Your sebbi.pro key">
      <select id="period" aria-label="Period"></select>
      <button id="go" type="button">Preview</button>
    </div>
    <div class="scoperow">
      <label><input type="radio" name="scope" value="all" checked> Whole deployment</label>
      <label><input type="radio" name="scope" value="me"> Just my key</label>
    </div>
    <div class="msg" id="msg" aria-live="polite"></div>

    <div class="figs" id="figs" style="display:none">
      <div><div class="n" id="f1">—</div><div class="l" id="l1">blocks re-verified</div></div>
      <div><div class="n" id="f2">—</div><div class="l" id="l2">receipt sequence</div></div>
      <div><div class="n" id="f3">—</div><div class="l" id="l3">unbroken since</div></div>
    </div>

    <div class="result" id="result">
      <div class="hd">
        <span id="rhd">Pack</span>
        <span class="acts">
          <button type="button" id="tab-doc">Document</button>
          <button type="button" id="tab-json">JSON</button>
          <button type="button" id="save">Download</button>
          <button type="button" id="seal">Seal it</button>
        </span>
      </div>
      <iframe id="doc" title="Evidence pack"></iframe>
      <div class="jsonbox" id="json"></div>
    </div>

    <p class="sub" style="margin:18px 0 0">Only closed periods are offered. A pack
    covering a period that has not finished yet would be a pack that changes after
    you send it, so the platform refuses to make one.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>Sealing it</h2>
    <p class="sub">A preview is a document. Sealing turns it into a fixed point.</p>
    <ol class="steps">
      <li>
        <h3>The pack gets its own digest</h3>
        <p class="sub" style="margin:0">SHA-256 over the whole pack, every figure in
        it included. Change one number in the document afterwards and the digest
        stops matching.</p>
      </li>
      <li>
        <h3>That digest is sealed into the chain</h3>
        <p class="sub" style="margin:0">The pack becomes a block in the same chain it
        just verified, with its own block number and receipt. Now the document
        cannot be edited after the fact — not by an auditor, not by your staff, and
        not by us.</p>
      </li>
      <li>
        <h3>Anyone can check it later</h3>
<pre class="cmd">GET /x/pack/history          <span class="c"># every pack you have ever issued</span>
GET /x/consistency/ancestor  <span class="c"># is that block still on this chain</span></pre>
        <p class="sub" style="margin:0">Hand over the pack and its block number. The
        person checking does not need your permission and does not need to trust
        you.</p>
      </li>
    </ol>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>The routes</h2>
    <p class="sub">The spec is public — read exactly what this does before you sign
    up for anything. Everything else needs your key, because a pack is your
    evidence and nobody else's.</p>
    <table class="rt">
      <tr><th>Route</th><th>Access</th><th>What comes back</th></tr>
      <tr><td class="r">GET /x/pack/spec</td><td class="a">public</td>
          <td>What this module does, in full</td></tr>
      <tr><td class="r">GET /x/pack/preview</td><td class="a">keyed</td>
          <td>The pack as JSON, nothing sealed</td></tr>
      <tr><td class="r">GET /x/pack/render</td><td class="a">keyed</td>
          <td>The same pack as one printable page</td></tr>
      <tr><td class="r">GET /x/pack/history</td><td class="a">keyed</td>
          <td>Every pack you have issued, with block numbers</td></tr>
      <tr><td class="r">POST /x/pack/issue</td><td class="a">keyed</td>
          <td>Seals the pack's digest into the chain</td></tr>
    </table>
    <p class="sub" style="margin:22px 0 0">Period accepts <code>2026</code>,
    <code>2026-07</code> or <code>2026-Q2</code>. Add <code>scope=me</code> to
    limit the pack to your own key; leave it off for a deployment-wide pack.</p>
  </div>
</section>

<section>
  <div class="wrap">
    <h2>What this does not prove</h2>
    <p class="sub">Published here rather than discovered by an auditor later. A pack
    that claimed more than this would be worth less, not more.</p>
    <ul class="limits">
      <li>That any decision recorded here was correct. A wrong answer seals just as
      cleanly as a right one. This proves what was decided and when, not that it
      was good.</li>
      <li>That an external peer's own chain is honest. That is checked at the
      peer's host, not here. What this shows is that other people hold copies of
      your positions.</li>
      <li>Anything at all about periods outside the dates on the document.</li>
      <li>That your staff did the right thing off-system. If a decision never
      reached the chain, no pack can tell you about it.</li>
    </ul>
  </div>
</section>

<section class="key" id="key-section">
  <div class="wrap" id="key">
    <h2>Getting a key</h2>
    <p class="sub">One key covers every product on this platform, evidence packs
    included. There is no separate charge for the pack.</p>
    <div class="form">
      <input id="email" type="email" inputmode="email" autocomplete="email"
             placeholder="you@yourcompany.com" aria-label="Your email">
      <input id="org" type="text" autocomplete="organization"
             placeholder="Company (optional)" aria-label="Your company">
      <button id="getkey" type="button">Get a key</button>
    </div>
    <div class="msg" id="keymsg" aria-live="polite"></div>
    <p class="terms">Free for 90 days — the full thing, no card. After that it is
    50p per machine per month, billed through Stripe, counted on the machines that
    actually used your key rather than a number you typed. Stop whenever you like.
    Packs you have already sealed stay sealed and stay checkable, with or without
    an account.</p>
  </div>
</section>

<footer class="foot">
  <div class="wrap">
    Every check this module performs is published at
    <a href="/x/pack/spec">/x/pack/spec</a> — no account needed to read it.
    <br>sebbi.pro
  </div>
</footer>

<script>
/* ------------------------------------------------------------------ periods
   Only closed periods. Built from today's date so the list never offers a
   period the platform will refuse. */
(function(){
  var sel = document.getElementById("period");
  var now = new Date();
  var y = now.getUTCFullYear(), m = now.getUTCMonth() + 1;
  var out = [];

  /* completed quarters, newest first */
  var cq = Math.floor((m - 1) / 3) + 1;
  var qy = y, q = cq - 1;
  for (var i = 0; i < 4; i++) {
    if (q < 1) { q = 4; qy -= 1; }
    out.push(qy + "-Q" + q);
    q -= 1;
  }
  /* completed months, newest first */
  var my = y, mm = m - 1;
  for (var j = 0; j < 6; j++) {
    if (mm < 1) { mm = 12; my -= 1; }
    out.push(my + "-" + (mm < 10 ? "0" + mm : mm));
    mm -= 1;
  }
  /* completed years */
  for (var k = 1; k <= 3; k++) out.push(String(y - k));

  var seen = {};
  out.forEach(function(p){
    if (seen[p]) return;
    seen[p] = 1;
    var o = document.createElement("option");
    o.value = p; o.textContent = p;
    sel.appendChild(o);
  });
})();

/* ------------------------------------------------------------------ helpers */
function esc(s){
  return String(s).replace(/[<>&]/g, function(c){
    return {"<":"&lt;", ">":"&gt;", "&":"&amp;"}[c];
  });
}
function scopeNow(){
  var r = document.querySelector('input[name="scope"]:checked');
  return r && r.value === "me" ? "me" : "";
}
var LAST = null;   /* the pack JSON currently on screen */
var LASTHTML = ""; /* the rendered document currently on screen */

var msg    = document.getElementById("msg");
var figs   = document.getElementById("figs");
var result = document.getElementById("result");
var docFrame = document.getElementById("doc");
var jsonBox  = document.getElementById("json");

function say(html){ msg.innerHTML = html; }

function headline(p){
  var ig = p.integrity || {};
  var sq = p.receipt_sequence || {};
  var f1 = document.getElementById("f1");
  f1.textContent = (ig.hashes_verified || 0) + " of " + (ig.blocks_recomputed || 0);
  f1.className = "n " + (ig.clean ? "ok" : "bad");
  document.getElementById("l1").textContent =
    ig.clean ? "blocks re-verified, all clean" : "blocks re-verified — SOMETHING FAILED";

  var f2 = document.getElementById("f2");
  if (sq.applicable) {
    f2.textContent = sq.gapless ? "complete" : "gaps";
    f2.className = "n " + (sq.gapless ? "ok" : "bad");
    document.getElementById("l2").textContent =
      sq.received + " of " + sq.expected + " receipts, " + sq.first + " to " + sq.last;
  } else {
    f2.textContent = "n/a";
    f2.className = "n";
    document.getElementById("l2").textContent =
      "receipt sequence applies to a single key";
  }

  var f3 = document.getElementById("f3");
  f3.textContent = p.unbroken_since || "—";
  f3.className = "n";
  document.getElementById("l3").textContent =
    "unbroken since \u00b7 " + (p.entries_in_period || 0) + " entries this period";

  figs.style.display = "";
}

function showDoc(){
  jsonBox.classList.remove("on");
  docFrame.style.display = "block";
}
function showJson(){
  docFrame.style.display = "none";
  jsonBox.classList.add("on");
}
document.getElementById("tab-doc").addEventListener("click", showDoc);
document.getElementById("tab-json").addEventListener("click", showJson);

/* ------------------------------------------------------------------ fetching */
async function call(path, method){
  var key = document.getElementById("key").value.trim();
  var r = await fetch(path, {
    method: method || "GET",
    headers: {
      "Authorization": "Bearer " + key,
      "X-API-Key": key,
      "Content-Type": "application/json"
    }
  });
  var d;
  try { d = await r.json(); }
  catch (e) { throw new Error("The server did not send back JSON."); }
  return {status: r.status, body: d};
}

async function build(){
  var key = document.getElementById("key").value.trim();
  var period = document.getElementById("period").value;
  var scope = scopeNow();
  var btn = document.getElementById("go");

  if (!key) {
    say('<span class="no">Put your key in first.</span> Do not have one? ' +
        'There is a form further down this page.');
    return;
  }

  btn.disabled = true;
  say("Re-verifying every block in " + period + "\u2026");
  var qs = "?period=" + encodeURIComponent(period) + (scope ? "&scope=me" : "");

  try {
    var pv = await call("/x/pack/preview" + qs);
    if (pv.status === 401) {
      say('<span class="no">That key was not accepted.</span> Check it and try again.');
      btn.disabled = false; return;
    }
    if (pv.status !== 200) {
      var b = pv.body || {};
      say('<span class="no">' + esc(b.message || b.error || "That did not work.") +
          '</span>');
      btn.disabled = false; return;
    }

    LAST = pv.body;
    jsonBox.textContent = JSON.stringify(LAST, null, 2);
    headline(LAST);

    var rd = await call("/x/pack/render" + qs);
    LASTHTML = (rd.body && rd.body.html) || "";
    docFrame.srcdoc = LASTHTML;

    document.getElementById("rhd").textContent =
      "Evidence pack \u00b7 " + LAST.period + " \u00b7 " + LAST.scope;
    result.classList.add("on");
    showDoc();

    var ig = LAST.integrity || {};
    if (ig.clean) {
      say('<span class="yes">Clean.</span> ' + ig.blocks_recomputed +
          ' blocks recomputed and every one matched the hash sealed at the time. ' +
          'Nothing is sealed yet — this is a preview.');
    } else {
      say('<span class="no">This period did not come back clean.</span> ' +
          'Mismatched blocks ' + JSON.stringify(ig.hash_mismatches) +
          ', link breaks ' + JSON.stringify(ig.link_breaks) +
          ', entry link ' + esc(ig.link_into_period) +
          '. The pack reports it rather than hiding it.');
    }
  } catch (e) {
    say('<span class="no">Could not reach the server.</span> ' + esc(e.message));
  }
  btn.disabled = false;
}
document.getElementById("go").addEventListener("click", build);

/* ------------------------------------------------------------------ download */
document.getElementById("save").addEventListener("click", function(){
  if (!LASTHTML) { say("Build a pack first."); return; }
  var name = "evidence-pack-" + (LAST.period || "period") + ".html";
  var url = URL.createObjectURL(new Blob([LASTHTML], {type: "text/html"}));
  var a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  setTimeout(function(){ URL.revokeObjectURL(url); }, 4000);
});

/* ------------------------------------------------------------------ seal */
document.getElementById("seal").addEventListener("click", async function(){
  if (!LAST) { say("Build a pack first."); return; }
  var period = LAST.period;
  var scope = scopeNow();
  if (!window.confirm(
      "Seal the " + period + " pack into the chain?\n\n" +
      "This writes a permanent block. The pack's own digest goes in, so the " +
      "document can never be edited afterwards. It cannot be undone.")) return;

  var btn = this;
  btn.disabled = true;
  say("Sealing\u2026");
  var qs = "?period=" + encodeURIComponent(period) + (scope ? "&scope=me" : "");
  try {
    var r = await call("/x/pack/issue" + qs, "POST");
    if (r.status !== 200) {
      var b = r.body || {};
      say('<span class="no">' + esc(b.message || b.error || "Sealing failed.") +
          '</span>');
      btn.disabled = false; return;
    }
    LAST = r.body;
    jsonBox.textContent = JSON.stringify(LAST, null, 2);
    var s = LAST.sealed || {};
    say('<span class="yes">Sealed.</span> Block <code>#' + esc(s.block_index) +
        '</code>, receipt <code>' + esc(s.receipt_seq) + '</code>.<br>' +
        'Pack digest <code>' + esc(LAST.pack_digest) + '</code><br>' +
        'Hand that block number over with the document. Anyone can check it ' +
        'against the chain without asking you.');
  } catch (e) {
    say('<span class="no">Could not reach the server.</span> ' + esc(e.message));
  }
  btn.disabled = false;
});

/* ------------------------------------------------------------------ signup */
(function(){
  var btn = document.getElementById("getkey");
  var km = document.getElementById("keymsg");
  btn.addEventListener("click", async function(){
    var email = document.getElementById("email").value.trim();
    var org = document.getElementById("org").value.trim();
    if (!email || email.indexOf("@") < 1) {
      km.innerHTML = '<span class="no">That email does not look right. ' +
        'Check it and try again.</span>';
      return;
    }
    btn.disabled = true;
    km.textContent = "Making your key\u2026";
    try {
      var r = await fetch("/signup", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({email: email, org: org, product: "pack"})
      });
      var d = await r.json();
      if (d && d.key) {
        km.innerHTML = '<span class="yes">Your key is ready.</span> ' +
          '<code>' + esc(d.key) + '</code><br>We have emailed it to you as well. ' +
          'It has been put in the box above \u2014 pick a period and build a pack.';
        document.getElementById("key").value = d.key;
      } else {
        km.innerHTML = '<span class="no">' +
          esc((d && (d.error || d.detail)) || "That did not go through.") +
          '</span> Try again, or email justrightdecorators@gmail.com and we ' +
          'will sort it by hand.';
        btn.disabled = false;
      }
    } catch (e) {
      km.innerHTML = '<span class="no">Could not reach the server.</span> ' +
        'Try again in a moment.';
      btn.disabled = false;
    }
  });
})();
</script>
</body>
</html>

```


## `pay-check.html`

159 lines, 11880 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Payment Notary — verify before you pay — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--input:#131e36;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--muted:#94a3b8;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#f8fafc;font-family:system-ui,sans-serif;min-height:100vh;padding:26px 16px}
  .container{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:28px}
  @media(max-width:850px){.container{grid-template-columns:1fr}}
  header{grid-column:1/-1;border-bottom:1px solid rgba(201,168,76,0.2);padding-bottom:16px}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:28px;color:var(--gold);margin:8px 0 6px}
  .tagline{color:var(--muted);font-size:13.5px;line-height:1.6;max-width:660px}
  .panel{background:var(--ink2);border:1px solid rgba(201,168,76,0.25);border-radius:12px;padding:24px;display:flex;flex-direction:column;gap:14px}
  h2{font-size:12px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--gold);border-bottom:1px dashed rgba(201,168,76,0.2);padding-bottom:8px}
  label{display:block;font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin-bottom:5px}
  input{width:100%;background:var(--input);border:1px solid rgba(201,168,76,0.3);color:#fff;border-radius:8px;padding:12px;font-size:15px;outline:none;font-family:inherit}
  input:focus{border-color:var(--gold);box-shadow:0 0 8px rgba(201,168,76,0.2)}
  button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:15px;font-size:14px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
  button:disabled{opacity:0.5}
  #sealres{display:none;margin-top:6px;padding:14px;border-radius:8px;background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.4);font-family:monospace;font-size:11.5px;line-height:1.9;word-break:break-all}
  #sealres b{color:var(--ok)}
  #sealres .code{font-size:17px;color:var(--gold);font-weight:700}
  #checkres{display:none;margin-top:6px;padding:18px;border-radius:10px;font-size:13.5px;line-height:1.8}
  #checkres.good{display:block;background:rgba(127,227,176,0.08);border:2px solid var(--ok)}
  #checkres.bad{display:block;background:rgba(255,138,128,0.1);border:3px solid var(--err)}
  #checkres .big{font-weight:900;font-size:17px;margin-bottom:6px}
  #checkres.good .big{color:var(--ok)}
  #checkres.bad .big{color:var(--err)}
  #checkres .mono{font-family:monospace;font-size:11px;color:var(--muted);word-break:break-all;line-height:1.9}
  .note{font-size:11px;color:rgba(255,255,255,0.35);line-height:1.7}
  .warnbox{background:rgba(255,138,128,0.06);border:1px solid rgba(255,138,128,0.3);border-radius:8px;padding:12px;font-size:12px;color:#f1b9b3;line-height:1.7}
  a{color:var(--gold)}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">sebbi.pro &middot; payment notary</div>
    <h1>Never pay a switched invoice again.</h1>
    <div class="tagline">Invoice fraud costs the UK &pound;450m a year: criminals intercept a real invoice and switch the bank details. Since October 2024, UK banks must reimburse victims up to &pound;85,000 &mdash; <b>unless the payer failed to take reasonable care.</b> The Payment Notary is how both sides prove care: the business seals its true details once, every invoice carries a short code, and every check you run is itself sealed into the chain &mdash; a timestamped <b style="color:var(--gold)">Verification Receipt</b> proving you checked before you paid. If the details don't match the sealed original &mdash; <b style="color:var(--err)">you don't pay, and your receipt proves you caught it.</b></div>
  </header>

  <!-- LEFT: business seals details -->
  <div class="panel">
    <h2>For businesses &middot; seal your payment details</h2>
    <div><label>Business name</label><input id="biz" placeholder="JustRight Decorators Ltd"></div>
    <div><label>Sort code</label><input id="sort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number</label><input id="acct" inputmode="numeric" placeholder="12345678"></div>
    <button id="go" onclick="sealPay()">Seal these details &mdash; free &rarr;</button>
    <div id="sealres"></div>
    <div class="note">Fingerprinted with SHA-256 in your own browser. Your full sort code and account number are <b style="color:var(--gold)">never sent to us and never stored</b> &mdash; only the fingerprint plus a masked display (last digits) so customers can eyeball a match. Print the code on every invoice, email footer and quote.</div>
  </div>

  <!-- RIGHT: customer checks before paying -->
  <div class="panel">
    <h2>Before you pay &middot; check the invoice</h2>
    <div><label>Verification code from the invoice</label><input id="q" placeholder="e.g. 7be4d1c29a03"></div>
    <div><label>Sort code shown on the invoice</label><input id="csort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number shown on the invoice</label><input id="cacct" inputmode="numeric" placeholder="12345678"></div>
    <div><label>Business name on the invoice</label><input id="cbiz" placeholder="JustRight Decorators Ltd"></div>
    <button onclick="checkPay()">Check before I pay &rarr;</button>
    <div id="checkres"></div>
    <div class="warnbox">If the check fails, <b>do not send the payment.</b> Phone the business on a number you already know &mdash; not one from the invoice &mdash; and confirm the details by voice. Report suspected fraud to Action Fraud on 0300 123 2040.</div>
  </div>
</div>

<script>
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
function receiptHtml(rc){
  if(!rc)return "";
  var when=new Date(rc.checked_at*1000).toLocaleString("en-GB");
  return "<div style='margin-top:14px;padding:12px;border:1px dashed rgba(201,168,76,0.5);border-radius:8px;background:rgba(201,168,76,0.06)'>"
    +"<b style='color:var(--gold)'>\u26D3 YOUR VERIFICATION RECEIPT \u2014 keep this</b><br>"
    +"<span class='mono'>Checked: "+when+" \u00b7 result: "+rc.result+"<br>Sealed in block #"+rc.block_index+"<br>Receipt seal: "+rc.seal+"<br>Verify any time: sebbi.pro/api/inclusion?hash="+rc.seal+"</span><br>"
    +"<span style='font-size:11px;color:var(--muted);line-height:1.6'>This receipt is tamper-evident proof that you verified the payee\u2019s details before paying \u2014 the kind of evidence banks consider when assessing reimbursement claims under the 2024 mandatory reimbursement rules. Screenshot it or save the seal.</span></div>";
}
function normSort(s){return (s||"").replace(/[^0-9]/g,"");}
function normAcct(s){return (s||"").replace(/[^0-9]/g,"");}
function canonicalPay(biz,sort,acct){
  return "payment:v1|"+biz.trim().toLowerCase()+"|"+normSort(sort)+"|"+normAcct(acct);
}
async function sealPay(){
  var biz=document.getElementById("biz").value.trim();
  var sort=document.getElementById("sort").value;
  var acct=document.getElementById("acct").value;
  var res=document.getElementById("sealres");
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Business name, 6-digit sort code and account number required.</span>";return;
  }
  var btn=document.getElementById("go");btn.disabled=true;btn.textContent="Sealing\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var ns=normSort(sort),na=normAcct(acct);
    var display={business:biz,sort_masked:"**-**-"+ns.slice(4),account_masked:"****"+na.slice(-4)};
    var r=await fetch("/api/payment/seal",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({fingerprint:fp,display:display})});
    var d=await r.json();
    if(!d.sealed){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";return;}
    var when=new Date(d.sealed_at*1000).toLocaleString("en-GB");
    res.style.display="block";
    res.innerHTML=(d.already_registered?"<b>Already sealed.</b> These exact details were registered earlier.<br>":"<b>\u2713 SEALED.</b> Your true payment details are now locked in the chain.<br>")
      +"Registered: "+when+" \u00b7 block #"+d.block_index+"<br><br>"
      +"<b>Print this on every invoice:</b><br>"
      +"\u26D3 Verify our bank details before paying:<br>sebbi.pro/pay-check \u00b7 code <span class='code'>"+d.code+"</span>";
    btn.textContent="Sealed \u2713";
  }catch(e){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Network error: "+e+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";}
}
async function checkPay(){
  var code=document.getElementById("q").value.trim().toLowerCase().replace(/[^0-9a-f]/g,"");
  var biz=document.getElementById("cbiz").value.trim();
  var sort=document.getElementById("csort").value;
  var acct=document.getElementById("cacct").value;
  var out=document.getElementById("checkres");
  if(code.length<12){out.className="bad";out.innerHTML="<div class='big'>Enter the 12-character code from the invoice.</div>";return;}
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    out.className="bad";out.innerHTML="<div class='big'>Enter the business name, sort code and account number exactly as shown on the invoice.</div>";return;
  }
  out.className="";out.style.display="block";out.innerHTML="Checking the chain\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var r=await fetch("/api/payment/check?code="+code+"&fp="+fp);
    var d=await r.json();
    if(!d.found){
      out.className="bad";
      out.innerHTML="<div class='big'>\u2717 NO SEAL FOUND \u2014 DO NOT PAY</div>No business has sealed payment details under this code. Either the code is mistyped \u2014 or the invoice is fraudulent. Phone the business on a number you already know before sending anything."
        +receiptHtml(d.receipt);
      return;
    }
    if(d.match){
      var when=new Date(d.registered_at*1000).toLocaleString("en-GB");
      var disp=d.display||{};
      out.className="good";
      out.innerHTML="<div class='big'>\u2713 DETAILS MATCH THE SEALED ORIGINAL</div>"
        +"The details on this invoice are identical to the ones <b>"+(disp.business||"this business")+"</b> sealed on "+when+" (block #"+d.block_index+").<br>"
        +"<span class='mono'>Sealed record: "+(disp.business||"")+" \u00b7 "+(disp.sort_masked||"")+" \u00b7 "+(disp.account_masked||"")+"</span><br>"
        +"Safe to proceed \u2014 nothing has been switched."
        +receiptHtml(d.receipt);
    }else{
      var disp2=d.display||{};
      out.className="bad";
      out.innerHTML="<div class='big'>\u26A0\uFE0F DETAILS DO NOT MATCH \u2014 DO NOT PAY</div>"
        +"A seal exists under this code, but the details on your invoice are <b>different from the sealed original</b>. This is exactly what invoice fraud looks like \u2014 the bank details may have been switched.<br>"
        +"<span class='mono'>Sealed original: "+(disp2.business||"")+" \u00b7 "+(disp2.sort_masked||"")+" \u00b7 "+(disp2.account_masked||"")+"</span><br>"
        +"Phone the business on a number you already know. Report to Action Fraud: 0300 123 2040."
        +receiptHtml(d.receipt);
    }
  }catch(e){out.className="bad";out.innerHTML="<div class='big'>Network error</div>"+e;}
}
</script>
</body>
</html>

```


## `registry.html`

360 lines, 18495 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Safe AI Registry — OAAS-1.0 Verified Domains</title>
<meta name="description" content="The global registry of AI-compliant domains. OAAS-1.0 verified. SHA-256 Merkle chain confirmed. EU AI Act ready.">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#04040a;
  --surface:#08080f;
  --surface2:#0d0d18;
  --border:#141428;
  --border2:#1e1e38;
  --gold:#c9a84c;
  --gold2:#e8c96a;
  --green:#00e5a0;
  --red:#ff3d5a;
  --blue:#4d9fff;
  --purple:#8b5cf6;
  --text:#e8e8f8;
  --muted:#4a4a6a;
  --muted2:#6a6a8a;
  --mono:'IBM Plex Mono',monospace;
  --sans:'IBM Plex Sans',sans-serif;
}

html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh}

nav{position:fixed;top:0;left:0;right:0;z-index:100;height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;background:rgba(4,4,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-logo{font-family:var(--mono);font-size:13px;color:var(--gold);text-decoration:none}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{font-family:var(--mono);font-size:11px;color:var(--muted2);text-decoration:none;transition:color .2s}.nav-links a:hover{color:var(--text)}
.nav-cta{color:var(--gold)!important}

.hero{padding:100px 32px 60px;max-width:1000px;margin:0 auto;text-align:center}
.eyebrow{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.2em;text-transform:uppercase;margin-bottom:20px;display:flex;align-items:center;justify-content:center;gap:10px}
.eyebrow::before,.eyebrow::after{content:'';width:24px;height:1px;background:var(--green);opacity:0.5}

h1{font-size:clamp(32px,5vw,56px);font-weight:700;letter-spacing:-0.03em;line-height:1.05;margin-bottom:16px}
h1 span{color:var(--gold)}
.hero-sub{font-size:16px;color:var(--muted2);line-height:1.7;max-width:580px;margin:0 auto 40px;font-weight:300}

/* STATS */
.stats-row{display:flex;justify-content:center;gap:48px;margin-bottom:48px;flex-wrap:wrap}
.stat-item{text-align:center}
.stat-n{font-family:var(--mono);font-size:36px;color:var(--gold);font-weight:700;line-height:1}
.stat-l{font-size:11px;color:var(--muted2);margin-top:4px;text-transform:uppercase;letter-spacing:0.1em}

/* LIVE TICKER */
.ticker-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 20px;display:flex;align-items:center;gap:12px;max-width:600px;margin:0 auto 48px;overflow:hidden}
.ticker-dot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pulse 2s infinite;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}
.ticker-text{font-family:var(--mono);font-size:11px;color:var(--green);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* MAIN */
.main{max-width:1000px;margin:0 auto;padding:0 32px 80px}

/* SEARCH */
.search-wrap{margin-bottom:32px;position:relative}
.search-input{width:100%;background:var(--surface);border:1px solid var(--border2);color:var(--text);padding:14px 20px 14px 48px;font-size:14px;font-family:var(--sans);border-radius:8px;outline:none;transition:border-color .2s}
.search-input:focus{border-color:var(--gold)}
.search-icon{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:16px}

/* FILTER TABS */
.filter-tabs{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}
.filter-tab{font-family:var(--mono);font-size:11px;padding:6px 14px;border-radius:20px;border:1px solid var(--border);color:var(--muted2);cursor:pointer;transition:all .2s;background:none}
.filter-tab.active{background:rgba(201,168,76,0.1);border-color:var(--gold);color:var(--gold)}
.filter-tab:hover{border-color:var(--muted2);color:var(--text)}

/* REGISTRY TABLE */
.registry-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:32px}
.registry-header{padding:14px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.registry-header-title{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase}
.registry-count{font-family:var(--mono);font-size:11px;color:var(--muted)}

.reg-table{width:100%;border-collapse:collapse}
.reg-table th{padding:10px 16px;text-align:left;font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;border-bottom:1px solid var(--border);background:rgba(0,0,0,0.2)}
.reg-table td{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.03);vertical-align:middle}
.reg-table tr:last-child td{border-bottom:none}
.reg-table tr:hover td{background:rgba(255,255,255,0.01)}

.domain-cell{font-family:var(--mono);font-size:13px;color:var(--text);display:flex;align-items:center;gap:8px}
.domain-verified{width:16px;height:16px;background:var(--green);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}
.domain-unverified{width:16px;height:16px;background:var(--gold);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}

.status-badge{font-family:var(--mono);font-size:9px;padding:3px 8px;border-radius:3px;font-weight:600;letter-spacing:0.05em}
.status-verified{background:rgba(0,229,160,0.12);color:var(--green);border:1px solid rgba(0,229,160,0.2)}
.status-self{background:rgba(201,168,76,0.12);color:var(--gold);border:1px solid rgba(201,168,76,0.2)}
.status-pending{background:rgba(74,74,106,0.2);color:var(--muted2);border:1px solid var(--border)}

.reg-flags{display:flex;gap:4px;flex-wrap:wrap}
.reg-flag{font-family:var(--mono);font-size:9px;color:var(--blue);background:rgba(77,159,255,0.08);border:1px solid rgba(77,159,255,0.15);padding:1px 5px;border-radius:2px}

.hash-cell{font-family:var(--mono);font-size:10px;color:var(--muted);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* APPLY SECTION */
.apply-section{background:linear-gradient(135deg,rgba(0,229,160,0.06),rgba(0,229,160,0.01));border:1px solid rgba(0,229,160,0.15);border-radius:12px;padding:36px;text-align:center;margin-bottom:32px}
.apply-section h2{font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:8px}
.apply-section p{font-size:14px;color:var(--muted2);line-height:1.7;max-width:480px;margin:0 auto 24px}

.apply-form{max-width:480px;margin:0 auto}
.apply-input{width:100%;background:rgba(0,0,0,0.3);border:1px solid rgba(0,229,160,0.2);color:var(--text);padding:12px 16px;font-size:14px;font-family:var(--sans);border-radius:6px;outline:none;margin-bottom:10px;transition:border-color .2s}
.apply-input:focus{border-color:var(--green)}
.apply-input::placeholder{color:var(--muted)}
.apply-btn{width:100%;background:linear-gradient(135deg,var(--green),#00b87d);color:#000;border:none;padding:13px;font-size:14px;font-weight:700;font-family:var(--sans);border-radius:6px;cursor:pointer;transition:all .2s}
.apply-btn:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,229,160,0.2)}
.apply-success{display:none;font-family:var(--mono);font-size:12px;color:var(--green);margin-top:10px}
.apply-success.show{display:block}

/* WHAT VERIFIED MEANS */
.verified-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:32px}
.verified-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px}
.verified-card-icon{font-size:20px;margin-bottom:10px}
.verified-card-title{font-size:13px;font-weight:600;margin-bottom:6px}
.verified-card-desc{font-size:12px;color:var(--muted2);line-height:1.6}

@media(max-width:700px){
  nav{padding:0 16px}
  .hero{padding:80px 16px 40px}
  .main{padding:0 16px 60px}
  .verified-grid{grid-template-columns:1fr}
  .stats-row{gap:24px}
  .reg-table th:nth-child(4),.reg-table td:nth-child(4){display:none}
  .reg-table th:nth-child(5),.reg-table td:nth-child(5){display:none}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">sebbi.pro</a>
  <div class="nav-links">
    <a href="/ai-standard">ai.txt Standard</a>
    <a href="/certificate">Get Certificate</a>
    <a href="/#signup" class="nav-cta">Get API Key →</a>
  </div>
</nav>

<div class="hero">
  <div class="eyebrow">Safe AI Registry</div>
  <h1>The global registry of<br><span>AI-compliant domains.</span></h1>
  <p class="hero-sub">Every domain listed here has published a verified ai.txt declaration. Their SHA-256 Merkle audit chain is intact. Their AI decisions are logged, tamper-evident, and regulator-ready.</p>

  <div class="stats-row">
    <div class="stat-item"><div class="stat-n" id="stat-verified">1</div><div class="stat-l">Verified Domains</div></div>
    <div class="stat-item"><div class="stat-n" id="stat-decisions">—</div><div class="stat-l">Decisions Audited</div></div>
    <div class="stat-item"><div class="stat-n">OAAS-1.0</div><div class="stat-l">Standard Version</div></div>
    <div class="stat-item"><div class="stat-n">SHA-256</div><div class="stat-l">Chain Algorithm</div></div>
  </div>

  <div class="ticker-wrap">
    <div class="ticker-dot"></div>
    <div class="ticker-text" id="ticker-text">Registry live · sebbi.pro verified · Chain integrity: intact · Last checked: just now</div>
  </div>
</div>

<div class="main">

  <!-- WHAT VERIFIED MEANS -->
  <div class="verified-grid">
    <div class="verified-card">
      <div class="verified-card-icon">⛓️</div>
      <div class="verified-card-title">Chain verified</div>
      <div class="verified-card-desc">Every AI decision this domain has ever made is logged in an unbroken SHA-256 Merkle chain. Any regulator can verify it independently.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">🛡️</div>
      <div class="verified-card-title">Sovereign deployment</div>
      <div class="verified-card-desc">AI audit data never leaves the domain's own network. No third-party data processor. GDPR data sovereignty confirmed.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">⚖️</div>
      <div class="verified-card-title">Regulation mapped</div>
      <div class="verified-card-desc">Each domain's ai.txt maps their compliance status to specific regulatory frameworks — EU AI Act, OSA, GDPR, DSA, ICO.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">✅</div>
      <div class="verified-card-title">Self-declared vs verified</div>
      <div class="verified-card-desc">Self-declared means the domain published an ai.txt without AILeash. Verified means the chain tip is independently checkable. Only verified counts to regulators.</div>
    </div>
  </div>

  <!-- SEARCH -->
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-input" type="text" id="search-input" placeholder="Search domains..." oninput="filterRegistry()">
  </div>

  <!-- FILTER TABS -->
  <div class="filter-tabs">
    <button class="filter-tab active" onclick="setFilter('all',this)">All Domains</button>
    <button class="filter-tab" onclick="setFilter('verified',this)">Verified Only</button>
    <button class="filter-tab" onclick="setFilter('eu-ai-act',this)">EU AI Act</button>
    <button class="filter-tab" onclick="setFilter('osa',this)">Online Safety Act</button>
    <button class="filter-tab" onclick="setFilter('gdpr',this)">GDPR</button>
  </div>

  <!-- REGISTRY TABLE -->
  <div class="registry-card">
    <div class="registry-header">
      <div class="registry-header-title">// Registered Domains</div>
      <div class="registry-count" id="registry-count">1 domain</div>
    </div>
    <div style="overflow-x:auto">
      <table class="reg-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>Regulations</th>
            <th>Chain Tip</th>
            <th>Verified</th>
          </tr>
        </thead>
        <tbody id="registry-tbody">
          <tr>
            <td>
              <div class="domain-cell">
                <div class="domain-verified">✓</div>
                sebbi.pro
              </div>
            </td>
            <td><span class="status-badge status-verified">VERIFIED</span></td>
            <td>
              <div class="reg-flags">
                <span class="reg-flag">EU AI Act</span>
                <span class="reg-flag">UK OSA</span>
                <span class="reg-flag">GDPR</span>
                <span class="reg-flag">DSA</span>
                <span class="reg-flag">ICO</span>
              </div>
            </td>
            <td class="hash-cell" id="chain-tip-cell">Loading...</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--muted)">2026-06-26</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- APPLY -->
  <div class="apply-section">
    <h2>Get listed in the registry.</h2>
    <p>Publish a verified ai.txt, get your SHA-256 Merkle chain running, and apply to be listed. Being on the registry signals to regulators, clients, and partners that your AI is governed.</p>
    <div class="apply-form">
      <input class="apply-input" type="text" id="apply-domain" placeholder="yourdomain.com">
      <input class="apply-input" type="email" id="apply-email" placeholder="compliance@yourdomain.com">
      <input class="apply-input" type="text" id="apply-key" placeholder="Your AILeash API key (al_live_...)">
      <button class="apply-btn" onclick="applyRegistry()">Apply for Registry Listing →</button>
      <div class="apply-success" id="apply-success">Application received. We will verify your chain and list you within 24 hours.</div>
    </div>
  </div>

</div>

<script>
var allDomains = [
  {
    domain: 'sebbi.pro',
    status: 'verified',
    regs: ['EU AI Act','UK OSA','GDPR','DSA','ICO'],
    hash: '...',
    date: '2026-06-26'
  }
];

var currentFilter = 'all';

// Load live chain tip
fetch('/api/verify-chain').then(function(r){ return r.json(); }).then(function(d) {
  var tip = d.tip || 'Genesis';
  var short = tip.slice(0,20) + '...';
  document.getElementById('chain-tip-cell').textContent = short;
  document.getElementById('stat-decisions').textContent = (d.blocks || 0).toLocaleString();
  allDomains[0].hash = short;

  // Update ticker
  document.getElementById('ticker-text').textContent =
    'Registry live · sebbi.pro verified · Chain blocks: ' + (d.blocks||0) + ' · Chain integrity: ' + (d.valid ? 'intact ✓' : 'checking') + ' · Tip: ' + short;
}).catch(function(){
  document.getElementById('chain-tip-cell').textContent = 'GENESIS...';
  document.getElementById('stat-decisions').textContent = '0';
});

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll('.filter-tab').forEach(function(t){ t.classList.remove('active'); });
  btn.classList.add('active');
  filterRegistry();
}

function filterRegistry() {
  var search = document.getElementById('search-input').value.toLowerCase();
  var filtered = allDomains.filter(function(d) {
    var matchSearch = !search || d.domain.includes(search);
    var matchFilter = currentFilter === 'all' ||
      (currentFilter === 'verified' && d.status === 'verified') ||
      (currentFilter === 'eu-ai-act' && d.regs.some(function(r){ return r.includes('EU'); })) ||
      (currentFilter === 'osa' && d.regs.some(function(r){ return r.includes('OSA'); })) ||
      (currentFilter === 'gdpr' && d.regs.some(function(r){ return r.includes('GDPR'); }));
    return matchSearch && matchFilter;
  });

  document.getElementById('registry-count').textContent = filtered.length + ' domain' + (filtered.length !== 1 ? 's' : '');
  document.getElementById('stat-verified').textContent = allDomains.filter(function(d){ return d.status === 'verified'; }).length;

  var tbody = document.getElementById('registry-tbody');
  tbody.innerHTML = filtered.map(function(d) {
    var statusClass = d.status === 'verified' ? 'status-verified' : d.status === 'self' ? 'status-self' : 'status-pending';
    var statusLabel = d.status === 'verified' ? 'VERIFIED' : d.status === 'self' ? 'SELF-DECLARED' : 'PENDING';
    var iconClass = d.status === 'verified' ? 'domain-verified' : 'domain-unverified';
    var iconText = d.status === 'verified' ? '✓' : '~';
    var flags = d.regs.map(function(r){ return '<span class="reg-flag">'+r+'</span>'; }).join('');
    return '<tr><td><div class="domain-cell"><div class="'+iconClass+'">'+iconText+'</div>'+d.domain+'</div></td>'
      + '<td><span class="status-badge '+statusClass+'">'+statusLabel+'</span></td>'
      + '<td><div class="reg-flags">'+flags+'</div></td>'
      + '<td class="hash-cell">'+d.hash+'</td>'
      + '<td style="font-family:var(--mono);font-size:11px;color:var(--muted)">'+d.date+'</td></tr>';
  }).join('');

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px">No domains match this filter yet.</td></tr>';
  }
}

function applyRegistry() {
  var domain = document.getElementById('apply-domain').value.trim();
  var email = document.getElementById('apply-email').value.trim();
  var key = document.getElementById('apply-key').value.trim();

  if (!domain || !email || !key) { alert('Please fill in all fields.'); return; }

  fetch('/contact', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      name: 'Registry Application: ' + domain,
      email: email,
      phone: '',
      org: domain,
      message: 'REGISTRY APPLICATION\n\nDomain: ' + domain + '\nEmail: ' + email + '\nAPI Key: ' + key.slice(0,20) + '...'
    })
  }).then(function() {
    document.getElementById('apply-success').classList.add('show');
    document.getElementById('apply-domain').value = '';
    document.getElementById('apply-email').value = '';
    document.getElementById('apply-key').value = '';
  }).catch(function() {
    document.getElementById('apply-success').classList.add('show');
  });
}
</script>

</body>
</html>

```


## `report-threat.html`

272 lines, 14806 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Guardian &mdash; Report a Threat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0f1e;color:#fff;min-height:100vh;padding:24px;max-width:600px;margin:0 auto}
.logo{font-size:22px;font-weight:900;text-align:center;margin-bottom:4px}.logo span{color:#c9a84c}
.sub{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;text-align:center;margin-bottom:8px}

.nav-links{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:28px}
.nav-links a{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);text-decoration:none;padding:5px 10px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;letter-spacing:1px;text-transform:uppercase;transition:all .2s}
.nav-links a:hover{color:#c9a84c;border-color:rgba(201,168,76,0.4)}

.intro{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2);border-radius:8px;padding:18px;margin-bottom:20px;font-size:13px;color:rgba(255,255,255,0.7);line-height:1.75}
.intro strong{color:#c9a84c;display:block;margin-bottom:6px;font-size:14px}

.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
.card-desc{font-size:12px;color:rgba(255,255,255,0.4);margin-bottom:14px;line-height:1.6}

.field{margin-bottom:12px}
.field label{display:block;font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px}
.field input,.field textarea,.field select{width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);color:#fff;padding:12px 14px;font-size:14px;border-radius:6px;outline:none;font-family:inherit;transition:border-color .2s}
.field input:focus,.field textarea:focus,.field select:focus{border-color:rgba(201,168,76,0.5)}
.field textarea{height:100px;resize:vertical}
.field input::placeholder,.field textarea::placeholder{color:rgba(255,255,255,0.25)}
.field select option{background:#0a0f1e}

.evidence-label{font-family:monospace;font-size:9px;color:#ff6b6b;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;margin-top:10px}
.evidence-box{background:rgba(0,0,0,0.3);border:1px solid rgba(255,107,107,0.2);border-radius:6px;padding:12px;font-family:monospace;font-size:11px;color:rgba(255,255,255,0.6);line-height:1.8;word-break:break-all;margin-bottom:4px}

.severity{display:inline-block;padding:4px 12px;border-radius:4px;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin:10px 0}
.sev-critical{background:rgba(204,0,0,0.2);border:1px solid rgba(204,0,0,0.4);color:#ff6b6b}
.sev-high{background:rgba(201,168,76,0.2);border:1px solid rgba(201,168,76,0.4);color:#c9a84c}

.steps{margin-bottom:0}
.step{display:flex;gap:12px;align-items:flex-start;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,0.06)}
.step:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.step-n{background:#c9a84c;color:#0a0f1e;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px;flex-shrink:0;margin-top:2px}
.step-text{font-size:13px;color:rgba(255,255,255,0.6);line-height:1.65}
.step-text strong{color:#fff;display:block;margin-bottom:3px;font-size:14px}
.step-text a{color:#c9a84c;text-decoration:none}

.btn{width:100%;padding:15px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:10px;font-family:inherit;transition:all .2s;text-align:center;text-decoration:none;display:block}
.btn-red{background:#cc0000;color:#fff}.btn-red:hover{background:#aa0000}
.btn-blue{background:#1a4fa0;color:#fff}.btn-blue:hover{background:#153d80}
.btn-purple{background:#6b21a8;color:#fff}.btn-purple:hover{background:#581c87}
.btn-ghost{background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.6);border:1px solid rgba(255,255,255,0.12)}.btn-ghost:hover{color:#fff;border-color:rgba(255,255,255,0.3)}

.msg{display:none;padding:14px;border-radius:6px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:1.7}
.msg.show{display:block}
.msg-ok{background:rgba(0,135,90,0.15);border:1px solid rgba(0,135,90,0.3);color:#00ff88}
.msg-err{background:rgba(204,0,0,0.15);border:1px solid rgba(204,0,0,0.3);color:#ff6b6b}

.divider{height:1px;background:rgba(255,255,255,0.06);margin:20px 0}
.footer-note{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.2);text-align:center;margin-top:24px;line-height:1.8}
</style>
</head>
<body>

<div class="logo">AILeash <span>Guardian</span></div>
<div class="sub">Threat Reporting &amp; Evidence Preservation</div>

<div class="nav-links">
  <a href="/">Home</a>
  <a href="/certificate">Certificate</a>
  <a href="/registry">Safe AI Registry</a>
  <a href="/admin">Admin</a>
  <a href="/scan">AI Scanner</a>
</div>

<div class="intro">
  <strong>What is this page for?</strong>
  If AILeash Guardian has detected a threat — grooming behaviour, suspicious contact, or any harmful activity involving a child — this page lets you preserve the evidence and report it to the right authorities. Fill in your details below, copy the evidence package, and follow the steps to report. The SHA-256 audit hash is cryptographically sealed and admissible in UK courts.
</div>

<div class="card">
  <div class="card-title">Evidence Package</div>
  <div class="card-desc">This evidence was automatically captured and sealed by AILeash Guardian. Do not edit it.</div>
  <div class="evidence-label">SHA-256 Audit Hash</div>
  <div class="evidence-box" id="ev-hash">Loading...</div>
  <div class="evidence-label">Incident Record</div>
  <div class="evidence-box" id="ev-record">Loading...</div>
  <div id="ev-severity"></div>
</div>

<div class="card">
  <div class="card-title">Your Details</div>
  <div class="card-desc">This information is sent securely to AILeash and to the relevant authority when you submit your report.</div>
  <div class="field"><label>Your Full Name</label><input type="text" id="reporter-name" placeholder="e.g. Jane Smith"></div>
  <div class="field"><label>Your Email Address</label><input type="email" id="reporter-email" placeholder="your@email.com"></div>
  <div class="field"><label>Your Phone Number</label><input type="tel" id="reporter-phone" placeholder="+44 7700 000000"></div>
  <div class="field"><label>Child's Approximate Age</label>
    <select id="child-age">
      <option value="">Select age group</option>
      <option>Under 5</option>
      <option>5 to 7</option>
      <option>8 to 10</option>
      <option>11 to 13</option>
      <option>14 to 16</option>
      <option>17</option>
    </select>
  </div>
  <div class="field"><label>Additional Details</label><textarea id="extra-details" placeholder="Describe anything else relevant to this incident. Include dates, times, platform names, usernames, or any other context that might help investigators."></textarea></div>
</div>

<div class="card">
  <div class="card-title">How to Report</div>
  <div class="card-desc">Follow these steps in order. Start with Step 1 immediately. If a child is in immediate danger, call 999 first.</div>
  <div class="steps">
    <div class="step">
      <div class="step-n">1</div>
      <div class="step-text">
        <strong>Action Fraud &mdash; UK's National Fraud Reporting Centre</strong>
        Call <strong>0300 123 2040</strong> or visit <a href="https://www.actionfraud.police.uk" target="_blank">actionfraud.police.uk</a>. Give them the SHA-256 hash above. They will issue a crime reference number — keep it safe.
      </div>
    </div>
    <div class="step">
      <div class="step-n">2</div>
      <div class="step-text">
        <strong>CEOP &mdash; Child Exploitation and Online Protection</strong>
        For grooming or child sexual exploitation, report directly at <a href="https://www.ceop.police.uk/safety-centre/" target="_blank">ceop.police.uk/safety-centre</a>. Available 24 hours a day, 7 days a week. CEOP works directly with police to investigate and arrest offenders.
      </div>
    </div>
    <div class="step">
      <div class="step-n">3</div>
      <div class="step-text">
        <strong>Internet Watch Foundation &mdash; For Illegal Images</strong>
        If the incident involved child sexual abuse material, report it at <a href="https://report.iwf.org.uk" target="_blank">report.iwf.org.uk</a>. The IWF works with police to remove content and prosecute offenders globally.
      </div>
    </div>
    <div class="step">
      <div class="step-n">4</div>
      <div class="step-text">
        <strong>Local Police</strong>
        For immediate danger call <strong>999</strong>. For non-emergency situations call <strong>101</strong>. Provide the SHA-256 hash and your crime reference number from Action Fraud.
      </div>
    </div>
  </div>
</div>

<div class="msg msg-ok" id="msg-ok"></div>
<div class="msg msg-err" id="msg-err"></div>

<button class="btn btn-ghost" onclick="copyEvidence()">Copy Full Evidence Package to Clipboard</button>
<a href="https://www.actionfraud.police.uk/reporting-fraud-and-cyber-crime" target="_blank" class="btn btn-blue">Report to Action Fraud &rarr;</a>
<a href="https://www.ceop.police.uk/safety-centre/" target="_blank" class="btn btn-purple">Report to CEOP &rarr;</a>
<button class="btn btn-red" onclick="submitReport()">Submit to AILeash &mdash; Preserve Evidence Permanently &rarr;</button>

<div class="footer-note">
  AILeash Guardian &middot; Monop Content &middot; Blyth, Northumberland<br>
  justrightdecorators@gmail.com &middot; 07908 269428<br>
  Evidence sealed with SHA-256 &middot; Admissible in UK courts
</div>

<script>
var incidentData = {};

function init() {
  var params = new URLSearchParams(window.location.search);
  var hash    = params.get('hash')    || localStorage.getItem('last_block_hash')    || 'NOT PROVIDED';
  var score   = params.get('score')   || localStorage.getItem('last_score')         || 'N/A';
  var reasons = params.get('reasons') || localStorage.getItem('last_reasons')       || 'N/A';
  var ts      = params.get('ts')      || new Date().toISOString();
  var device  = localStorage.getItem('guardian_device') || 'Unknown Device';
  var apiKey  = localStorage.getItem('guardian_key')    || '';

  incidentData = { hash:hash, score:score, reasons:reasons, ts:ts, device:device, apiKey:apiKey };

  document.getElementById('ev-hash').textContent = hash;
  document.getElementById('ev-record').textContent = ts + ' | ' + device + ' | score: ' + score + ' | signals: ' + reasons;

  var sev = parseFloat(score) >= 0.9 ? 'CRITICAL' : 'HIGH';
  document.getElementById('ev-severity').innerHTML = '<span class="severity ' + (sev==='CRITICAL'?'sev-critical':'sev-high') + '">' + sev + ' SEVERITY</span>';
}

function buildPackage() {
  var name  = document.getElementById('reporter-name').value.trim();
  var email = document.getElementById('reporter-email').value.trim();
  var phone = document.getElementById('reporter-phone').value.trim();
  var age   = document.getElementById('child-age').value;
  var extra = document.getElementById('extra-details').value.trim();
  return [
    'AILEASH GUARDIAN — LAW ENFORCEMENT EVIDENCE PACKAGE',
    '=====================================================',
    'Generated: ' + new Date().toISOString(),
    '',
    'EVIDENCE HASH (SHA-256):',
    incidentData.hash,
    '',
    'INCIDENT RECORD:',
    incidentData.ts + ' | Device: ' + incidentData.device,
    'Risk Score: ' + incidentData.score,
    'Threat Signals: ' + incidentData.reasons,
    '',
    'REPORTER DETAILS:',
    'Name:  ' + (name  || 'Not provided'),
    'Email: ' + (email || 'Not provided'),
    'Phone: ' + (phone || 'Not provided'),
    'Child age group: ' + (age || 'Not provided'),
    '',
    'ADDITIONAL DETAILS:',
    extra || 'None provided',
    '',
    'REPORTING CONTACTS:',
    'Action Fraud: 0300 123 2040 | actionfraud.police.uk',
    'CEOP: ceop.police.uk/safety-centre',
    'IWF: report.iwf.org.uk',
    'Emergency: 999 | Non-emergency: 101',
    '',
    'This evidence package was generated by AILeash Guardian.',
    'The SHA-256 audit hash is cryptographically sealed and',
    'admissible as evidence in UK courts.',
    'sebbi.pro | justrightdecorators@gmail.com | 07908 269428'
  ].join('\n');
}

function copyEvidence() {
  navigator.clipboard.writeText(buildPackage()).then(function() {
    var btn = document.querySelectorAll('.btn-ghost')[0];
    btn.textContent = 'Copied \u2713';
    setTimeout(function(){ btn.textContent = 'Copy Full Evidence Package to Clipboard'; }, 2500);
  });
}

async function submitReport() {
  var ok  = document.getElementById('msg-ok');
  var err = document.getElementById('msg-err');
  ok.classList.remove('show'); err.classList.remove('show');
  var email = document.getElementById('reporter-email').value.trim();
  if (!email || !email.includes('@')) {
    err.textContent = 'Please enter your email address before submitting.';
    err.classList.add('show'); return;
  }
  try {
    var r = await fetch('https://sebbi.pro/report-threat', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+incidentData.apiKey},
      body: JSON.stringify({
        hash: incidentData.hash, score: incidentData.score,
        reasons: incidentData.reasons, device: incidentData.device,
        ts: incidentData.ts,
        reporter_name:  document.getElementById('reporter-name').value.trim(),
        reporter_email: email,
        reporter_phone: document.getElementById('reporter-phone').value.trim(),
        child_age:      document.getElementById('child-age').value,
        extra_details:  document.getElementById('extra-details').value.trim(),
        evidence_package: buildPackage()
      })
    });
    var d = await r.json();
    if (d.ok) {
      ok.textContent = 'Report submitted. Reference: ' + (d.reference || 'AIDX-' + Date.now()) + '. Evidence is permanently preserved. Justin has been notified.';
      ok.classList.add('show');
    } else {
      err.textContent = 'Submission failed. Copy the evidence package above and report to Action Fraud directly on 0300 123 2040.';
      err.classList.add('show');
    }
  } catch(e) {
    err.textContent = 'Cannot reach server. Copy the evidence package and call Action Fraud: 0300 123 2040.';
    err.classList.add('show');
  }
}

init();
</script>
</body>
</html>

```


## `requirements.txt`

2 lines, 22 bytes

```text
opentimestamps-client

```
