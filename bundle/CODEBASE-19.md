# Codebase — part 19 of 42

Contains:
- `modules/savings.py`
- `modules/sebbi_adapter.py`
- `modules/sebbi_engine.py`


## `modules/savings.py`

852 lines, 38047 bytes

```python
"""
modules/savings.py  -  the cost model at /savings

WHAT IT IS
----------
One page. Enter a device count, see what a traditional compliance architecture
costs against a proof-based one, and change every assumption behind it.

WHY THE ASSUMPTIONS ARE EDITABLE
--------------------------------
The saving rests on one number - what the traditional architecture costs per
device per year - and that number is ours, not theirs. Asserted, it is the
first thing a finance director dismisses. Broken into ingestion, storage,
monitoring, pipeline and engineering, with every line editable, the arithmetic
runs on their figures instead of ours. Harder to wave away, and honest.

The page will also say plainly when the saving goes negative on the numbers
somebody has typed. A calculator that can only ever produce a good answer is
not a calculator.

NO TRACKING, NO STORAGE
-----------------------
Everything happens in the browser. Nothing is submitted, nothing is recorded,
no figure anyone types reaches the server. A buyer modelling their own costs
should not have to wonder where those went.

v1.1 CHANGES
------------
1. The MEASURED column read /api/anchor-status and printed "live" or a
   calendar count under a heading promising figures read from the live chain.
   Anchoring is not a live property of the chain - it is a state each proof is
   in, and most are pending. It now reads /x/ots/status and prints the
   confirmed / pending split, which is the honest number and the one an
   auditor will look up themselves.
2. Block height is now labelled as mostly liveness beacon rather than usage.
   A five-minute beat is 288 blocks a day whether anyone is using the system
   or not, and quoting it as activity would be the same overstatement.
3. POST /x/savings/seal stays public - a visitor sealing their own model
   without an account is the point - but it is now throttled globally and
   deduplicated, so it cannot be used to write unlimited blocks into the
   chain. The page already handled a 429 that nothing was producing; now
   something does.
4. ctx["seal"] is wrapped. A failed seal returns 500 and stores nothing,
   instead of handing back a receipt for a block that was never written.

SAME PATCH AS network.py AND console.py
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime, adds one path, leaves
every other path alone. After each deploy one /x/ request must arrive before
/savings exists - opening /x/savings/status does it.
"""

import json
import sys
import time

VERSION = "1.1"

PUBLIC = {("GET", "status"), ("GET", "verify"), ("POST", "seal")}

PAGE_PATHS = ("/savings", "/savings.html", "/cost", "/proof-machine")

# Public write throttle. Generous enough that a real visitor never sees it,
# tight enough that the route cannot be used to flood the chain.
SEAL_PER_HOUR = 30

_patched = [False]
_ready = [False]
_seal_times = []


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS savings_model("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,devices INTEGER,"
            "assumptions TEXT,traditional_per REAL,proof_per REAL,"
            "annual_saving REAL,modelled REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_sav_hash ON savings_model(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The cost of proving it — AILeash</title>
<meta name="description" content="What AI governance costs at enterprise scale, and what a proof-based architecture changes. Put your own figures in.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0f1e; --ink2:#10182e; --paper:#f6f3ec; --line:#e3ddcf;
  --gold:#c9a84c; --mute:#6b6353; --mutei:rgba(255,255,255,.45);
  --save:#1a9e6e; --spend:#c8362b;
  --disp:Fraunces,Georgia,serif; --body:'Space Grotesk',system-ui,sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
body{background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.65}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}

header{background:var(--ink);color:#fff;padding:52px 0 44px;margin-bottom:38px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
h1{font-family:var(--disp);font-weight:900;font-size:clamp(32px,8vw,54px);
  line-height:1;letter-spacing:-.025em}
h1 i{font-style:italic;color:var(--gold)}
.stand{color:var(--mutei);margin-top:16px;max-width:52ch;font-size:15.5px}
.stand b{color:#fff}

h2{font-family:var(--disp);font-weight:900;font-size:clamp(22px,5vw,30px);
  letter-spacing:-.02em;margin-bottom:6px}
.note{color:var(--mute);font-size:14.5px;margin-bottom:22px;max-width:56ch}

section{margin-bottom:40px}

.devices{border:1px solid var(--line);border-left:3px solid var(--ink);
  background:#fff;padding:22px;margin-bottom:14px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--mute);margin-bottom:9px}
.count{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.count input[type=number]{flex:1;min-width:150px;background:var(--paper);
  border:1px solid var(--line);padding:13px 14px;border-radius:4px;
  font-family:var(--mono);font-size:20px;color:var(--ink);outline:none}
.count input:focus{border-color:var(--gold)}
input[type=range]{width:100%;-webkit-appearance:none;appearance:none;height:3px;
  background:var(--line);border-radius:2px;outline:none;margin-top:18px}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;
  border-radius:50%;background:var(--ink);border:4px solid var(--gold);cursor:pointer}
input[type=range]::-moz-range-thumb{width:22px;height:22px;border-radius:50%;
  background:var(--ink);border:4px solid var(--gold);cursor:pointer}
.presets{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
.presets button{background:transparent;border:1px solid var(--line);color:var(--mute);
  font-family:var(--mono);font-size:11.5px;padding:7px 11px;border-radius:3px;cursor:pointer}
.presets button:hover,.presets button.on{border-color:var(--ink);color:var(--ink)}

.headline{background:var(--ink);color:#fff;padding:30px 24px;margin-bottom:14px}
.hl-l{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.hl-v{font-family:var(--disp);font-weight:900;font-size:clamp(38px,12vw,68px);
  line-height:1;letter-spacing:-.03em;color:#7fe3b0}
.hl-s{color:var(--mutei);font-size:14px;margin-top:12px}

.compare{border:1px solid var(--line);background:#fff;padding:24px}
.row{margin-bottom:26px}
.row:last-child{margin-bottom:0}
.row-h{display:flex;justify-content:space-between;align-items:baseline;
  gap:12px;margin-bottom:10px}
.row-t{font-family:var(--disp);font-weight:600;font-size:18px}
.row-v{font-family:var(--mono);font-size:15px;font-weight:500}
.stack{display:flex;height:44px;border-radius:3px;overflow:hidden;background:var(--paper)}
.seg{position:relative;transition:width .4s ease;min-width:0}
.seg:not(:last-child){border-right:1px solid rgba(255,255,255,.35)}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;
  font-family:var(--mono);font-size:11px;color:var(--mute)}
.legend span{display:flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.gap-note{font-family:var(--mono);font-size:11.5px;color:var(--save);
  margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}

.assump{border:1px solid var(--line);background:#fff}
.a-row{display:grid;grid-template-columns:1fr 116px;gap:14px;align-items:center;
  padding:14px 18px;border-bottom:1px solid var(--line)}
.a-row:last-of-type{border-bottom:none}
.a-name{font-size:14.5px}
.a-name small{display:block;color:var(--mute);font-size:12px;margin-top:2px;line-height:1.45}
.a-in{display:flex;align-items:center;gap:5px}
.a-in span{font-family:var(--mono);font-size:13px;color:var(--mute)}
.a-in input{width:100%;background:var(--paper);border:1px solid var(--line);
  padding:9px 10px;border-radius:3px;font-family:var(--mono);font-size:14px;
  color:var(--ink);outline:none;text-align:right}
.a-in input:focus{border-color:var(--gold)}
.a-total{display:grid;grid-template-columns:1fr 116px;gap:14px;padding:15px 18px;
  background:var(--ink);color:#fff;align-items:center}
.a-total .a-name{font-family:var(--disp);font-weight:600;font-size:16px}
.a-total .v{font-family:var(--mono);font-size:15px;text-align:right;color:var(--gold)}
.reset{background:none;border:none;color:var(--mute);font-family:var(--mono);
  font-size:11.5px;text-decoration:underline;cursor:pointer;padding:12px 18px}

.years{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--line);border:1px solid var(--line);margin-top:14px}
.yr{background:#fff;padding:18px 14px;text-align:center}
.yr .l{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--mute);margin-bottom:8px}
.yr .v{font-family:var(--disp);font-weight:900;font-size:clamp(18px,5vw,26px);
  color:var(--save);line-height:1}

.split{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);
  border:1px solid var(--line);margin-bottom:16px}
.half{background:#fff;padding:20px}
.half.measured{border-top:3px solid var(--save)}
.half.modelled{border-top:3px solid var(--gold)}
.h-l{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--mute);margin-bottom:14px}
.measured .h-l{color:var(--save)}
.m-row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
  border-bottom:1px solid var(--line);font-size:13.5px;align-items:baseline}
.m-row:last-of-type{border-bottom:none}
.m-row b{font-family:var(--mono);font-size:13px;text-align:right}
.h-n{font-size:13px;color:var(--mute);line-height:1.65;margin-top:12px}
.sealbox{border:1px dashed var(--gold);background:rgba(201,168,76,.07);padding:22px}
.s-h{font-family:var(--disp);font-weight:900;font-size:19px;margin-bottom:8px}
.s-n{font-size:13.5px;color:var(--mute);line-height:1.65;margin-bottom:16px}
#sealbtn{background:var(--ink);color:#fff;border:none;border-radius:3px;padding:14px 22px;
  font-family:var(--body);font-weight:700;font-size:14px;cursor:pointer}
#sealbtn:hover:not(:disabled){background:#243156}
#sealbtn:disabled{opacity:.5;cursor:default}
#sealout{margin-top:14px;font-family:var(--mono);font-size:12px;line-height:1.9;
  color:var(--mute);word-break:break-all}
#sealout a{color:var(--ink)}
#sealout .ok{color:var(--save)}
#sealout .bad{color:var(--spend)}
@media(max-width:560px){.split{grid-template-columns:1fr}}
.straight{border-left:3px solid var(--gold);background:rgba(201,168,76,.07);
  padding:20px 22px;font-size:14.5px;line-height:1.7;color:var(--mute)}
.straight b{color:var(--ink)}
.straight p+p{margin-top:12px}

.cta{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}
.cta a{display:inline-block;padding:15px 26px;border-radius:3px;text-decoration:none;
  font-weight:700;font-size:14.5px}
.gold{background:var(--gold);color:var(--ink)}
.ghost{border:1px solid var(--line);color:var(--ink)}

footer{border-top:1px solid var(--line);margin-top:44px;padding:26px 0 60px;
  font-family:var(--mono);font-size:11px;color:var(--mute);line-height:1.9}
footer a{color:var(--ink)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(max-width:560px){
  .a-row,.a-total{grid-template-columns:1fr 96px;gap:10px;padding:13px 14px}
  .years{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>

<header>
  <div class="wrap">
    <p class="eyebrow">AILeash · what it costs to prove it</p>
    <h1>Everyone prices the model.<br><i>Nobody prices the proof.</i></h1>
    <p class="stand">At enterprise scale the model is rarely the expensive part. <b>Ingestion, log storage, monitoring, compliance pipelines and the engineering time to hold it all together</b> usually cost more — and none of it proves anything on its own.</p>
  </div>
</header>

<div class="wrap">

<section>
  <h2>Your deployment</h2>
  <p class="note">Everything below recalculates from this.</p>
  <div class="devices">
    <label for="dev">Devices under governance</label>
    <div class="count">
      <input id="dev" type="number" min="100" step="100" value="100000" inputmode="numeric">
    </div>
    <input id="devr" type="range" min="2" max="6" step="0.01" value="5">
    <div class="presets">
      <button data-n="10000">10k</button>
      <button data-n="25000">25k</button>
      <button data-n="50000">50k</button>
      <button data-n="100000" class="on">100k</button>
      <button data-n="250000">250k</button>
      <button data-n="500000">500k</button>
    </div>
  </div>
</section>

<section>
  <div class="headline">
    <p class="hl-l">Potential annual saving</p>
    <p class="hl-v" id="save">—</p>
    <p class="hl-s" id="save-sub">—</p>
  </div>

  <div class="compare">
    <div class="row">
      <div class="row-h">
        <span class="row-t">Traditional compliance architecture</span>
        <span class="row-v" id="trad-v">—</span>
      </div>
      <div class="stack" id="trad-stack"></div>
      <div class="legend" id="trad-legend"></div>
    </div>

    <div class="row">
      <div class="row-h">
        <span class="row-t">Proof-based, on AILeash</span>
        <span class="row-v" id="proof-v">—</span>
      </div>
      <div class="stack" id="proof-stack"></div>
      <div class="legend">
        <span><i class="sw" style="background:#c9a84c"></i>50p per device per month, flat</span>
      </div>
    </div>

    <p class="gap-note" id="gap">—</p>
  </div>

  <div class="years">
    <div class="yr"><div class="l">Year one</div><div class="v" id="y1">—</div></div>
    <div class="yr"><div class="l">Three years</div><div class="v" id="y3">—</div></div>
    <div class="yr"><div class="l">Per device, per year</div><div class="v" id="ypd">—</div></div>
  </div>
</section>

<section>
  <h2>Change any of these</h2>
  <p class="note">These are the figures the saving rests on. They are illustrative, and yours will differ — so put yours in. The arithmetic follows whatever you type.</p>
  <div class="assump" id="assump">
    <div class="a-row">
      <div class="a-name">Data ingestion
        <small>Getting decision data out of your systems and into somewhere it can be queried.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ingest" value="3.20" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Log storage
        <small>Retention at the volumes an audit trail implies, for as long as the regulation implies.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-store" value="2.80" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Monitoring platform
        <small>Licences and seats on whatever watches it.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-monitor" value="2.40" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Compliance pipeline
        <small>Turning raw logs into something a regulator will accept.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-pipeline" value="2.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Engineering time
        <small>Building it, and keeping it running once it exists.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-eng" value="1.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">AILeash
        <small>50p per device per month. Change it if you have been quoted something else.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ail" value="6.00" step="0.50" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-total">
      <div class="a-name">Traditional, per device per year</div>
      <div class="v" id="a-sum">—</div>
    </div>
  </div>
  <button class="reset" id="reset">Put the illustrative figures back</button>
</section>

<section>
  <h2>What is measured, and what is modelled</h2>
  <p class="note">The two halves of this page are not the same kind of number, and it matters which is which.</p>

  <div class="split">
    <div class="half measured">
      <div class="h-l">Measured — read from the live system just now</div>
      <div class="m-row"><span>Blocks in the chain</span><b id="m-height">…</b></div>
      <div class="m-row"><span>Bytes per seal</span><b>32</b></div>
      <div class="m-row"><span>Size of the record behind it</span><b>irrelevant</b></div>
      <div class="m-row"><span>Timestamp proofs confirmed</span><b id="m-anchor">…</b></div>
      <p class="h-n">A seal is a SHA-256 digest. Thirty-two bytes, whether the decision behind it is one line or a megabyte. That is not a claim about our architecture, it is what a hash is — and it is the whole reason the cost stops tracking the volume.</p>
      <p class="h-n">Two honest notes on the figures above. A liveness beat seals a block every five minutes, so most of that block count is heartbeat rather than customer decisions — it is not a usage number. And external timestamping is per proof: a proof is submitted first and confirmed later, so the split above is what is actually confirmed against what is still pending. Both are readable at <a href="/x/ots/status">/x/ots/status</a>.</p>
    </div>
    <div class="half modelled">
      <div class="h-l">Modelled — assumptions, including yours</div>
      <div class="m-row"><span>What you spend today</span><b>your figures</b></div>
      <div class="m-row"><span>What you would stop spending</span><b>an estimate</b></div>
      <p class="h-n">Nobody can prove what an organisation <i>would have</i> spent. That number does not exist anywhere to be measured, here or in any vendor's business case. What this page can do is make the assumptions visible and let you replace every one of them.</p>
    </div>
  </div>

  <div class="sealbox">
    <div class="s-h">Seal this calculation</div>
    <p class="s-n">Puts your inputs and the result into the audit chain, dated and tamper-evident, and hands you a receipt anyone can check. Then what was modelled, and on whose assumptions, is a matter of record rather than of memory — including ours.</p>
    <button id="sealbtn">Seal it and give me a receipt</button>
    <div id="sealout"></div>
  </div>
</section>

<section>
  <h2>Why a proof layer costs less</h2>
  <p class="note">It is not a discount on the same architecture. It is less architecture.</p>
  <div class="straight">
    <p><b>Most of that cost is moving and keeping data.</b> Sensitive records get shipped somewhere central, held for years, indexed so they can be searched, and watched so nothing goes missing — because the plan is to reconstruct what happened by reading it all back later.</p>
    <p><b>A proof-based layer answers the question at the moment the decision is made.</b> The decision is scored, sealed into a hash chain, submitted for external timestamping and recorded by independent platforms. What survives is a proof that the decision happened, under stated rules, and has not been altered since.</p>
    <p><b>So the volume stops being the problem.</b> A seal is the same size whether the record behind it is a line or a megabyte, and it does not have to leave your systems for the proof to hold. You keep your own data where it already is.</p>
    <p>It does not replace your logs, and it is not meant to. It replaces the machinery built to make logs trustworthy — which is the part that scales badly.</p>
  </div>
  <div class="cta">
    <a class="gold" href="/#signup">Get an API key · 90 days free</a>
    <a class="ghost" href="/whitepaper">Read the whitepaper</a>
    <a class="ghost" href="/api/verify-chain">Check the chain</a>
  </div>
</section>

<footer>
  Illustrative model. Real figures vary with cloud provider, data volume, retention policy, engineering rates and existing contracts — which is why every input above is yours to change. No saving is guaranteed and nothing here is a quotation.<br>
  <a href="https://sebbi.pro">sebbi.pro</a> · Monop Content, Blyth
</footer>

</div>

<script>
(function(){
  var DEFAULTS = { ingest:3.20, store:2.80, monitor:2.40, pipeline:2.60, eng:1.60, ail:6.00 };
  var SEGMENTS = [
    { id:'ingest',   label:'Data ingestion',      colour:'#0a0f1e' },
    { id:'store',    label:'Log storage',         colour:'#243156' },
    { id:'monitor',  label:'Monitoring',          colour:'#3d4f7d' },
    { id:'pipeline', label:'Compliance pipeline', colour:'#5b6e9e' },
    { id:'eng',      label:'Engineering time',    colour:'#8794b8' }
  ];

  var $ = function(id){ return document.getElementById(id); };
  var dev = $('dev'), devr = $('devr');

  function money(n){
    if(!isFinite(n)) return '—';
    if(Math.abs(n) >= 1000000) return '£' + (n/1000000).toFixed(2).replace(/\.00$/,'') + 'm';
    return '£' + Math.round(n).toLocaleString('en-GB');
  }
  function per(n){ return '£' + n.toFixed(2); }
  function val(id){
    var v = parseFloat($(id).value);
    return (isFinite(v) && v >= 0) ? v : 0;
  }
  function devices(){
    var v = parseInt(dev.value, 10);
    if(!isFinite(v) || v < 1) v = 1;
    return v;
  }

  function draw(){
    var n = devices();
    var parts = SEGMENTS.map(function(s){ return { s:s, v: val('a-' + s.id) }; });
    var tradPer = parts.reduce(function(a,p){ return a + p.v; }, 0);
    var ailPer = val('a-ail');

    var trad = tradPer * n, proof = ailPer * n, saved = trad - proof;

    $('a-sum').textContent = per(tradPer);
    $('trad-v').textContent = money(trad) + ' / year';
    $('proof-v').textContent = money(proof) + ' / year';

    $('save').textContent = saved > 0 ? money(saved) : money(0);
    $('save').style.color = saved > 0 ? '#7fe3b0' : '#ffb4ad';
    $('save-sub').textContent = n.toLocaleString('en-GB') + ' devices · ' +
      per(tradPer) + ' against ' + per(ailPer) + ' per device per year';

    var scale = Math.max(tradPer, ailPer) || 1;
    var tradHtml = '', legendHtml = '';
    parts.forEach(function(p){
      if(p.v <= 0) return;
      tradHtml += '<div class="seg" style="width:' + ((p.v/scale)*100) + '%;background:' +
        p.s.colour + '" title="' + p.s.label + ' · ' + per(p.v) + '"></div>';
      legendHtml += '<span><i class="sw" style="background:' + p.s.colour + '"></i>' +
        p.s.label + ' ' + per(p.v) + '</span>';
    });
    $('trad-stack').innerHTML = tradHtml;
    $('trad-legend').innerHTML = legendHtml;
    $('proof-stack').innerHTML = '<div class="seg" style="width:' +
      ((ailPer/scale)*100) + '%;background:#c9a84c"></div>';

    if(saved > 0){
      var pct = Math.round((saved / (tradPer * n)) * 100);
      $('gap').textContent = 'The gap is ' + money(saved) + ' a year — about ' + pct +
        '% of the traditional figure, on these inputs.';
      $('gap').style.color = '#1a9e6e';
    } else if(saved === 0){
      $('gap').textContent = 'On these inputs the two cost the same.';
      $('gap').style.color = '#6b6353';
    } else {
      $('gap').textContent = 'On these inputs the proof layer costs ' + money(-saved) +
        ' a year more. Worth knowing, and worth saying.';
      $('gap').style.color = '#c8362b';
    }

    $('y1').textContent = money(Math.max(0, saved));
    $('y3').textContent = money(Math.max(0, saved * 3));
    $('ypd').textContent = per(Math.max(0, tradPer - ailPer));

    document.querySelectorAll('.presets button').forEach(function(b){
      b.classList.toggle('on', parseInt(b.dataset.n,10) === n);
    });
  }

  function syncFromSlider(){
    dev.value = Math.round(Math.pow(10, parseFloat(devr.value)) / 100) * 100;
    draw();
  }
  function syncFromNumber(){
    var n = devices();
    devr.value = Math.min(6, Math.max(2, Math.log(n) / Math.LN10));
    draw();
  }

  devr.addEventListener('input', syncFromSlider);
  dev.addEventListener('input', syncFromNumber);
  document.querySelectorAll('.presets button').forEach(function(b){
    b.addEventListener('click', function(){
      dev.value = b.dataset.n; syncFromNumber();
    });
  });
  document.querySelectorAll('#assump input').forEach(function(i){
    i.addEventListener('input', draw);
  });
  $('reset').addEventListener('click', function(){
    Object.keys(DEFAULTS).forEach(function(k){ $('a-' + k).value = DEFAULTS[k].toFixed(2); });
    draw();
  });

  syncFromNumber();

  // ---- measured half: read the live system, state what is actually there
  (async function(){
    try{
      var r = await fetch('/x/witness/tip');
      if(r.ok){
        var d = await r.json();
        var h = d.height;
        $('m-height').textContent = (typeof h === 'number')
          ? h.toLocaleString('en-GB') : 'unavailable';
      } else { $('m-height').textContent = 'unavailable'; }
    }catch(e){ $('m-height').textContent = 'unavailable'; }

    try{
      var a = await fetch('/x/ots/status');
      if(a.ok){
        var ad = await a.json();
        var conf = ad.confirmed, pend = ad.pending;
        if(typeof conf === 'number' || typeof pend === 'number'){
          $('m-anchor').textContent = (conf || 0).toLocaleString('en-GB') +
            ' confirmed / ' + (pend || 0).toLocaleString('en-GB') + ' pending';
        } else {
          $('m-anchor').textContent = 'see /x/ots/status';
        }
      } else { $('m-anchor').textContent = 'unavailable'; }
    }catch(e){ $('m-anchor').textContent = 'unavailable'; }
  })();

  // ---- seal the calculation
  var sealbtn = $('sealbtn'), sealout = $('sealout');
  sealbtn.addEventListener('click', async function(){
    sealbtn.disabled = true;
    sealout.innerHTML = 'sealing…';
    var body = {
      devices: devices(),
      assumptions: {
        ingestion: val('a-ingest'), storage: val('a-store'),
        monitoring: val('a-monitor'), pipeline: val('a-pipeline'),
        engineering: val('a-eng'), aileash: val('a-ail')
      }
    };
    try{
      var r = await fetch('/x/savings/seal', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      var d = await r.json();
      if(r.status === 429){
        sealout.innerHTML = '<span class="bad">' +
          ((d && d.message) || 'Rate limited. Give it a few minutes.') + '</span>';
      } else if(r.status === 409 && d && d.receipt){
        sealout.innerHTML =
          '<span class="ok">This exact model is already sealed at block ' + d.block_index +
          '</span><br>receipt ' + d.receipt + '<br>' +
          '<a href="' + d.verify + '" target="_blank" rel="noopener">check it yourself →</a>';
      } else if(!r.ok || !d.receipt){
        sealout.innerHTML = '<span class="bad">' +
          ((d && (d.message || d.error)) || ('HTTP ' + r.status)) + '</span>';
      } else {
        sealout.innerHTML =
          '<span class="ok">Sealed at block ' + d.block_index + '</span><br>' +
          'receipt ' + d.receipt + '<br>' +
          '<a href="' + d.verify + '" target="_blank" rel="noopener">check it yourself →</a>';
      }
    }catch(e){
      sealout.innerHTML = '<span class="bad">Could not reach the server.</span>';
    }
    sealbtn.disabled = false;
  });
})();
</script>
</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_savings_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._savings_patched = True
    _patched[0] = True
    print("SAVINGS: /savings page installed at runtime", flush=True)
    return "installed"


def _throttle_ok():
    """Global cap on public writes. Prunes as it goes so the list cannot grow."""
    now = time.time()
    cutoff = now - 3600
    while _seal_times and _seal_times[0] < cutoff:
        _seal_times.pop(0)
    if len(_seal_times) >= SEAL_PER_HOUR:
        return False, int(3600 - (now - _seal_times[0])) + 1
    _seal_times.append(now)
    return True, 0


def _existing(ctx, devices, vals):
    """An identical model already sealed is returned rather than sealed again.
    Refreshing the page should not add a block."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT audit_hash,block_index FROM savings_model "
                "WHERE devices=? AND assumptions=? ORDER BY id DESC LIMIT 1",
                (devices, json.dumps(vals))).fetchone()
        if row and row[0]:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


def _seal(ctx, api_key, data):
    data = data or {}
    try:
        devices = int(data.get("devices", 0))
    except (TypeError, ValueError):
        devices = 0
    if devices < 1 or devices > 100000000:
        return {"error": "devices_required",
                "message": "Send a device count between 1 and 100,000,000."}, 400

    a = data.get("assumptions")
    if not isinstance(a, dict):
        return {"error": "assumptions_required"}, 400

    fields = ["ingestion", "storage", "monitoring", "pipeline", "engineering", "aileash"]
    vals = {}
    for f in fields:
        try:
            v = float(a.get(f, 0))
        except (TypeError, ValueError):
            v = 0.0
        if v < 0 or v > 100000:
            v = 0.0
        vals[f] = round(v, 2)

    # An identical model is not sealed twice.
    h_old, idx_old = _existing(ctx, devices, vals)
    if h_old:
        return {
            "sealed": False,
            "already_sealed": True,
            "receipt": h_old,
            "block_index": idx_old,
            "message": ("This exact model is already in the chain. It is not "
                        "sealed again, so refreshing the page does not add blocks."),
            "verify": "/x/savings/verify?receipt=" + h_old,
        }, 409

    ok, retry_after = _throttle_ok()
    if not ok:
        return {"error": "rate_limited",
                "retry_after_seconds": retry_after,
                "seals_per_hour": SEAL_PER_HOUR,
                "message": ("This route is open to anyone with no account, so it is "
                            "capped to stop the chain being flooded. Try again in a "
                            "few minutes.")}, 429

    traditional_per = round(sum(vals[f] for f in fields if f != "aileash"), 2)
    proof_per = vals["aileash"]
    traditional = round(traditional_per * devices, 2)
    proof = round(proof_per * devices, 2)
    saving = round(traditional - proof, 2)

    ts = time.time()
    detail = ("devices=" + str(devices) +
              ";" + ";".join("%s=%.2f" % (f, vals[f]) for f in fields) +
              ";traditional_per=%.2f;proof_per=%.2f;saving=%.2f"
              % (traditional_per, proof_per, saving))

    ev = {"user_id": "sav:" + str(devices), "action": "savings_modelled",
          "amount": 0, "country": "UK", "device_id": "savings",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SAVINGS_SEALED", "score": 0, "savings_version": VERSION,
           "devices": devices, "assumptions": vals,
           "traditional_per_device_year": traditional_per,
           "proof_per_device_year": proof_per,
           "annual_saving": saving, "timestamp": ts, "detail": detail}

    try:
        h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "message": ("Nothing was written and no receipt was issued. A receipt "
                            "for a block that does not exist is worse than an error.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash",
                "message": "Nothing was written and no receipt was issued."}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO savings_model(api_key,devices,assumptions,traditional_per,"
            "proof_per,annual_saving,modelled,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, devices, json.dumps(vals), traditional_per, proof_per,
             saving, ts, h, idx))
        ctx["conn"].commit()

    return {
        "sealed": True,
        "receipt": h,
        "block_index": idx,
        "receipt_seq": seq,
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "devices": devices,
        "assumptions": vals,
        "traditional_per_device_year": traditional_per,
        "proof_per_device_year": proof_per,
        "annual_saving": saving,
        "verify": "/x/savings/verify?receipt=" + h,
        "what_this_proves": ("That this calculation, on these assumptions, was run at "
                             "this time and has not been altered since. It does not "
                             "prove the assumptions are right - they are yours - and "
                             "no record can prove what an organisation would otherwise "
                             "have spent."),
    }, 200


def _verify(ctx, data):
    receipt = str((data or {}).get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT devices,assumptions,traditional_per,proof_per,annual_saving,"
            "modelled,block_index FROM savings_model WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No calculation with that receipt exists in this chain."}, 404
    try:
        assumptions = json.loads(row[1])
    except Exception:
        assumptions = {}
    return {
        "found": True, "receipt": receipt,
        "devices": row[0], "assumptions": assumptions,
        "traditional_per_device_year": row[2],
        "proof_per_device_year": row[3],
        "annual_saving": row[4],
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[5])),
        "block_index": row[6],
        "proof": ("This calculation is a block in a hash chain that is recorded by "
                  "independent platforms and submitted for external timestamping. "
                  "Altering or removing it breaks every block after it."),
        "chain_tip": "/x/witness/tip",
        "witnessed_by": "/x/roster/list",
        "timestamp_proofs": "/x/ots/status",
        "anchoring": ("Timestamping is per proof. A proof is submitted first and "
                      "confirmed later; submitted is not confirmed. Check the state "
                      "of the proof covering this block at /x/ots/status."),
    }, 200


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("SAVINGS: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "seal":
            _setup(ctx)
            return _seal(ctx, api_key or "public-savings", data)
        return {"error": "unknown_action", "action": action, "POST": ["seal"]}, 404

    if action in ("", "status"):
        return {
            "page": "/savings",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "public_seals_per_hour": SEAL_PER_HOUR,
            "note": ("The calculator runs in the browser. Nothing a visitor types is "
                     "submitted unless they choose to seal it."),
        }, 200
    if action == "verify":
        _setup(ctx)
        return _verify(ctx, data)
    return {"error": "unknown_action", "action": action,
            "GET": ["status", "verify"], "POST": ["seal"]}, 404

```


## `modules/sebbi_adapter.py`

602 lines, 24915 bytes

```python
"""
sebbi_adapter.py  v1.0.0 - drop-in state anchoring for legacy applications.

Your application keeps its database, its logic and its infrastructure. This
file sits beside it: every state change you point it at is turned into a
SHA-256 fingerprint, queued locally, and sent in the background to the
sebbi.pro public proof log, which returns a receipt proving the fingerprint
is in an append-only RFC 6962 Merkle tree whose tree heads are sealed into the
sebbi.pro chain and timestamped in Bitcoin.

Only the fingerprint leaves your machine. The data itself never does.

TWO LINES
---------
    export SEBBI_API_KEY=your-key          (once, in the environment)

    from sebbi_adapter import anchor_state
    @anchor_state("orders.update")
    def update_order(order_id, status):
        ...                                 # unchanged
        return {"order_id": order_id, "status": status}

The return value is fingerprinted after the function succeeds. The call is
never slowed down by the network and never fails because of this file:
fingerprints go into a local append-only queue (sqlite) and a background
thread sends them. If sebbi.pro is unreachable they wait, and are sent when it
comes back, in order, with no duplicates.

OTHER WAYS IN
-------------
    from sebbi_adapter import record, AnchorLogHandler
    record({"account": 42, "balance": 1250})          # anywhere, returns the hash
    logging.getLogger("payments").addHandler(AnchorLogHandler())   # every log line

    @anchor_state("ledger.post", capture="args")      # fingerprint the inputs instead
    @anchor_state("user.save", extract=lambda result, args, kwargs: result.to_dict())

Async functions work the same way.

CHECKING
--------
    python sebbi_adapter.py status            queue and receipt counts
    python sebbi_adapter.py flush             send what is waiting, now
    python sebbi_adapter.py receipt <hash>    the receipt for one fingerprint
    python sebbi_adapter.py verify            re-check every stored receipt locally
    python sebbi_adapter.py hash '<json>'     fingerprint a JSON value exactly as the adapter would

Every receipt is checked on arrival with an RFC 6962 inclusion check, so the
server's answer is verified, not trusted. A receipt that fails the check is
kept (as evidence) and flagged.

FINGERPRINT RULE (so anyone can recompute it)
---------------------------------------------
SHA-256 over canonical JSON: keys sorted, separators "," and ":", UTF-8, no
extra whitespace. datetime/date -> ISO 8601 string, Decimal -> string,
bytes -> hex, set -> sorted list, UUID -> string, dataclass -> its fields,
objects with to_dict()/_asdict() -> that. Floats use Python's repr. Anything
else is refused (and logged) rather than guessed at - pass extract= for those.

SETTINGS (environment or Anchor(...) arguments)
-----------------------------------------------
    SEBBI_API_KEY        your key (without it, fingerprints queue and wait)
    SEBBI_ENDPOINT       default https://sebbi.pro
    SEBBI_DB             default ./sebbi_anchor.db
    SEBBI_DISABLED=1     record nothing (kill switch)

Standard library only. Python 3.8+.
"""

import asyncio
import atexit
import dataclasses
import datetime
import decimal
import functools
import hashlib
import inspect
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

__version__ = "1.0.0"
__all__ = ["anchor_state", "record", "Anchor", "AnchorLogHandler", "canonical_json", "state_hash",
           "verify_inclusion", "verify_consistency", "get_default"]

log = logging.getLogger("sebbi_adapter")


# ---------------------------------------------------------------- fingerprints

def _default(o):
    if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return str(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        return bytes(o).hex()
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=lambda x: canonical_json(x))
    if isinstance(o, uuid.UUID):
        return str(o)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    for attr in ("to_dict", "_asdict"):
        fn = getattr(o, attr, None)
        if callable(fn):
            return fn()
    raise TypeError("cannot fingerprint %s - pass extract= to choose what to record" % type(o).__name__)


def canonical_json(obj):
    """The exact bytes the fingerprint is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=_default).encode("utf-8")


def state_hash(obj):
    """SHA-256 of canonical JSON, as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()


# ---------------------------------------------------------------- RFC 6962 checks

def _h(b):
    return hashlib.sha256(b).digest()


def leaf_hash(entry_hex):
    return _h(b"\x00" + bytes.fromhex(entry_hex)).hex()


def verify_inclusion(entry_hex, index, tree_size, path, root):
    """RFC 9162 section 2.1.3.2: is entry at `index` in the tree of `tree_size` with `root`?"""
    try:
        index, tree_size = int(index), int(tree_size)
        if index < 0 or index >= tree_size:
            return False
        fn, sn = index, tree_size - 1
        r = _h(b"\x00" + bytes.fromhex(entry_hex))
        for p_hex in path:
            p = bytes.fromhex(p_hex)
            if sn == 0:
                return False
            if (fn & 1) or fn == sn:
                r = _h(b"\x01" + p + r)
                if not (fn & 1):
                    while not (fn & 1) and fn != 0:
                        fn >>= 1
                        sn >>= 1
            else:
                r = _h(b"\x01" + r + p)
            fn >>= 1
            sn >>= 1
        return sn == 0 and r == bytes.fromhex(root)
    except (ValueError, TypeError):
        return False


def verify_consistency(first, second, first_root, second_root, proof):
    """RFC 9162 section 2.1.4.2: is the tree of size `second` an append-only extension of `first`?"""
    try:
        first, second = int(first), int(second)
        fr_b, sr_b = bytes.fromhex(first_root), bytes.fromhex(second_root)
        path = [bytes.fromhex(p) for p in proof]
        if first == second:
            return not path and fr_b == sr_b
        if first < 1 or first > second or not path:
            return False
        if first & (first - 1) == 0:
            path = [fr_b] + path
        fn, sn = first - 1, second - 1
        while fn & 1:
            fn >>= 1
            sn >>= 1
        fr = sr = path[0]
        for c in path[1:]:
            if sn == 0:
                return False
            if (fn & 1) or fn == sn:
                fr = _h(b"\x01" + c + fr)
                sr = _h(b"\x01" + c + sr)
                if not (fn & 1):
                    while not (fn & 1) and fn != 0:
                        fn >>= 1
                        sn >>= 1
            else:
                sr = _h(b"\x01" + sr + c)
            fn >>= 1
            sn >>= 1
        return fr == fr_b and sr == sr_b and sn == 0
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- the sidecar

class Anchor(object):
    """Local append-only queue + background sender. Safe across threads, processes and forks."""

    def __init__(self, api_key=None, endpoint=None, db_path=None, batch_size=200,
                 flush_interval=2.0, timeout=10.0, check_chain=True, start=True):
        self.api_key = (api_key if api_key is not None else os.environ.get("SEBBI_API_KEY", "")).strip()
        self.endpoint = (endpoint or os.environ.get("SEBBI_ENDPOINT", "https://sebbi.pro")).rstrip("/")
        self.db_path = db_path or os.environ.get("SEBBI_DB", "sebbi_anchor.db")
        self.batch_size = max(1, min(500, int(batch_size)))
        self.flush_interval = float(flush_interval)
        self.timeout = float(timeout)
        self.check_chain = bool(check_chain)
        self.disabled = os.environ.get("SEBBI_DISABLED", "0") == "1"
        self._autostart = start
        self._warned_no_key = False
        if not self.endpoint.startswith("https://") and "127.0.0.1" not in self.endpoint \
                and "localhost" not in self.endpoint:
            log.warning("sebbi_adapter: endpoint %s is not https", self.endpoint)
        self._init_process()

    # -- process-local state (rebuilt after fork) --
    def _init_process(self):
        self._pid = os.getpid()
        self._wid = "%d-%s" % (self._pid, uuid.uuid4().hex[:8])
        self._lk = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._backoff = 0.0
        self._tried = {}
        self._db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS entries(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "cid TEXT UNIQUE NOT NULL,hash TEXT NOT NULL,label TEXT,created REAL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "cid TEXT NOT NULL,leaf_index INTEGER,receipt TEXT,verified INTEGER,"
                         "checkpointed INTEGER DEFAULT 0,in_chain INTEGER,received REAL)")
        self._db.execute("CREATE INDEX IF NOT EXISTS receipts_cid ON receipts(cid)")
        self._db.execute("CREATE INDEX IF NOT EXISTS entries_hash ON entries(hash)")
        self._db.execute("CREATE TABLE IF NOT EXISTS claims(cid TEXT PRIMARY KEY,worker TEXT,until REAL)")
        self._thread = None
        if self._autostart:
            self._start_thread()

    def _ensure_process(self):
        if os.getpid() != self._pid:
            self._init_process()

    def _start_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="sebbi-anchor", daemon=True)
        self._thread.start()

    # -- recording (host side: local only, never raises) --
    def record(self, payload, label=None):
        """Fingerprint `payload` and queue it. Returns the hash, or None if it could not be recorded."""
        if self.disabled:
            return None
        try:
            return self.record_hash(state_hash(payload), label=label)
        except Exception as e:
            log.warning("sebbi_adapter: not recorded (%s)", e)
            return None

    def record_hash(self, hash_hex, label=None):
        """Queue a fingerprint you computed yourself (64 hex characters)."""
        if self.disabled:
            return None
        try:
            h = str(hash_hex).strip().lower()
            if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
                raise ValueError("hash must be 64 hex characters")
            self._ensure_process()
            with self._lk:
                self._db.execute("INSERT INTO entries(cid,hash,label,created) VALUES(?,?,?,?)",
                                 (uuid.uuid4().hex, h, (str(label)[:120] if label else None), time.time()))
            self._wake.set()
            return h
        except Exception as e:
            log.warning("sebbi_adapter: not recorded (%s)", e)
            return None

    # -- lookups --
    def receipt(self, hash_hex):
        """Latest receipt for a fingerprint (the most recent entry with that hash), or None."""
        self._ensure_process()
        with self._lk:
            row = self._db.execute(
                "SELECT r.receipt,r.verified,r.checkpointed,r.in_chain,e.label,e.created FROM entries e "
                "JOIN receipts r ON r.cid=e.cid WHERE e.hash=? ORDER BY e.seq DESC, r.id DESC LIMIT 1",
                (str(hash_hex).lower(),)).fetchone()
        if not row:
            return None
        rec = json.loads(row[0])
        rec["verified_locally"] = bool(row[1])
        rec["checkpointed"] = bool(row[2])
        rec["tree_head_seen_in_chain"] = None if row[3] is None else bool(row[3])
        rec["label"] = row[4]
        return rec

    def counts(self):
        self._ensure_process()
        with self._lk:
            c = self._db
            total = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            sent = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts").fetchone()[0]
            cp = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts WHERE checkpointed=1").fetchone()[0]
            bad = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts WHERE verified=0").fetchone()[0]
        return {"recorded": total, "receipted": sent, "waiting": total - sent,
                "sealed_in_chain": cp, "failed_local_check": bad}

    def pending(self):
        return self.counts()["waiting"]

    # -- network --
    def _http(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.endpoint + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "sebbi-adapter/" + __version__)
        if self.api_key:
            req.add_header("X-Sebbi-Key", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8") or "{}")
            except Exception:
                return e.code, {}

    def _claim(self, n):
        now = time.time()
        with self._lk:
            c = self._db
            c.execute("BEGIN IMMEDIATE")
            try:
                rows = c.execute(
                    "SELECT e.cid,e.hash FROM entries e WHERE NOT EXISTS (SELECT 1 FROM receipts r WHERE r.cid=e.cid) "
                    "AND NOT EXISTS (SELECT 1 FROM claims k WHERE k.cid=e.cid AND k.until>? AND k.worker<>?) "
                    "ORDER BY e.seq LIMIT ?", (now, self._wid, n)).fetchall()
                for cid, _ in rows:
                    c.execute("INSERT OR REPLACE INTO claims(cid,worker,until) VALUES(?,?,?)",
                              (cid, self._wid, now + max(60.0, self.timeout * 3)))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return rows

    def _release(self, cids):
        with self._lk:
            self._db.executemany("DELETE FROM claims WHERE cid=? AND worker=?", [(c, self._wid) for c in cids])

    def _store(self, cid, rec, checkpointed=False, in_chain=None):
        ok = verify_inclusion(rec.get("entry_hash", ""), rec.get("leaf_index", -1), rec.get("tree_size", 0),
                              rec.get("audit_path", []), rec.get("root", ""))
        if checkpointed and ok and rec.get("checkpoint"):
            ok = rec["checkpoint"].get("root") == rec.get("root")
        if not ok:
            log.error("sebbi_adapter: receipt for leaf %s FAILED the local inclusion check - kept and flagged",
                      rec.get("leaf_index"))
        with self._lk:
            self._db.execute("INSERT INTO receipts(cid,leaf_index,receipt,verified,checkpointed,in_chain,received) "
                             "VALUES(?,?,?,?,?,?,?)",
                             (cid, rec.get("leaf_index"), json.dumps(rec, sort_keys=True), 1 if ok else 0,
                              1 if checkpointed else 0, in_chain, time.time()))
        return ok

    def _send_batch(self):
        """Send one batch. Returns number receipted; raises on network failure."""
        if not self.api_key:
            if not self._warned_no_key:
                log.warning("sebbi_adapter: SEBBI_API_KEY not set - fingerprints are queued locally and will "
                            "be sent once it is")
                self._warned_no_key = True
            return 0
        rows = self._claim(self.batch_size)
        if not rows:
            return 0
        wanted = {cid: h for cid, h in rows}
        try:
            code, out = self._http("POST", "/p/submit", {"items": [{"hash": h, "cid": cid} for cid, h in rows]})
        except Exception:
            self._release(list(wanted))
            raise
        if code != 200:
            self._release(list(wanted))
            raise IOError("sebbi.pro answered %s: %s" % (code, out.get("error") or out.get("message") or ""))
        done = 0
        for rec in out.get("receipts") or []:
            cid = rec.get("cid")
            if cid not in wanted:
                continue
            if rec.get("error"):
                log.error("sebbi_adapter: entry %s refused: %s", cid, rec["error"])
                continue
            if rec.get("entry_hash") != wanted[cid]:
                log.error("sebbi_adapter: server returned a different hash for %s - not stored", cid)
                continue
            self._store(cid, rec)
            done += 1
        self._release(list(wanted))
        return done

    def _upgrade(self, limit=50):
        """Fetch sealed receipts for leaves whose tree head should now be in the chain."""
        cutoff = time.time() - 30
        with self._lk:
            rows = self._db.execute(
                "SELECT r.cid,r.leaf_index FROM receipts r WHERE r.verified=1 AND r.received<? AND "
                "NOT EXISTS (SELECT 1 FROM receipts r2 WHERE r2.cid=r.cid AND r2.checkpointed=1) "
                "GROUP BY r.cid ORDER BY MIN(r.id) LIMIT ?", (cutoff, limit)).fetchall()
        blocks = {}
        now = time.time()
        for cid, idx in rows:
            if now - self._tried.get(cid, 0) < 30:
                continue
            self._tried[cid] = now
            code, rec = self._http("GET", "/p/receipt?leaf=%d" % idx)
            if code != 200 or not rec.get("checkpoint"):
                continue
            in_chain = None
            if self.check_chain:
                blk = rec["checkpoint"].get("block_index")
                if blk not in blocks:
                    try:
                        _, body = self._http("GET", "/x/walk/block?index=%s" % blk)
                        blocks[blk] = json.dumps(body)
                    except Exception:
                        blocks[blk] = None
                if blocks[blk] is not None:
                    in_chain = 1 if rec["checkpoint"].get("root", "~") in blocks[blk] else 0
                    if not in_chain:
                        log.error("sebbi_adapter: tree head for leaf %s not found in chain block %s", idx, blk)
            self._store(cid, rec, checkpointed=True, in_chain=in_chain)
            self._tried.pop(cid, None)

    def flush(self, timeout=30.0):
        """Send everything waiting, now. Returns how many were receipted. Never raises."""
        self._ensure_process()
        end, sent = time.time() + timeout, 0
        while time.time() < end:
            try:
                n = self._send_batch()
            except Exception as e:
                log.warning("sebbi_adapter: flush stopped (%s); entries stay queued", e)
                break
            sent += n
            if n == 0:
                break
        return sent

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait(self._backoff or self.flush_interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                while self._send_batch() >= self.batch_size:
                    pass
                self._upgrade()
                self._backoff = 0.0
            except Exception as e:
                self._backoff = min(300.0, max(2.0, self._backoff * 2))
                log.info("sebbi_adapter: sebbi.pro unreachable (%s); retrying in %ds", e, self._backoff)

    def close(self, flush_timeout=2.0):
        try:
            if flush_timeout:
                self.flush(timeout=flush_timeout)
        finally:
            self._stop.set()
            self._wake.set()


# ---------------------------------------------------------------- the default instance

_default_anchor = None
_default_lock = threading.Lock()


def get_default():
    global _default_anchor
    if _default_anchor is None:
        with _default_lock:
            if _default_anchor is None:
                _default_anchor = Anchor()
                atexit.register(_default_anchor.close)
    return _default_anchor


def record(payload, label=None, anchor=None):
    """Fingerprint and queue any JSON-able value. Returns the hash. Never raises."""
    try:
        return (anchor or get_default()).record(payload, label=label)
    except Exception as e:
        log.warning("sebbi_adapter: not recorded (%s)", e)
        return None


def anchor_state(label=None, capture="result", extract=None, anchor=None):
    """Decorator. After the wrapped function succeeds, fingerprint its state and queue it.

    capture:  "result" (default) - the return value
              "args"             - the arguments it was called with
              "both"             - {"args": ..., "kwargs": ..., "result": ...}
    extract:  f(result, args, kwargs) -> the value to fingerprint (overrides capture)
    The wrapped function's behaviour, return value and exceptions are unchanged.
    """
    if callable(label) and not isinstance(label, str):
        return anchor_state()(label)

    def deco(fn):
        name = label or getattr(fn, "__qualname__", getattr(fn, "__name__", "call"))

        def _state(args, kwargs, result):
            if extract is not None:
                return extract(result, args, kwargs)
            if capture == "args":
                return {"args": list(args), "kwargs": kwargs}
            if capture == "both":
                return {"args": list(args), "kwargs": kwargs, "result": result}
            return result

        def _anchor(args, kwargs, result):
            try:
                record(_state(args, kwargs, result), label=name, anchor=anchor)
            except Exception as e:
                log.warning("sebbi_adapter: %s not recorded (%s)", name, e)

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                _anchor(args, kwargs, result)
                return result
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            _anchor(args, kwargs, result)
            return result
        return wrapper
    return deco


class AnchorLogHandler(logging.Handler):
    """Fingerprints every log record it sees: logger, level, message and time."""

    def __init__(self, anchor=None, level=logging.INFO):
        logging.Handler.__init__(self, level)
        self._anchor = anchor

    def emit(self, rec):
        if rec.name.startswith("sebbi_adapter"):
            return
        try:
            record({"logger": rec.name, "level": rec.levelname, "message": rec.getMessage(),
                    "time": round(rec.created, 6)}, label="log:" + rec.name, anchor=self._anchor)
        except Exception:
            pass


# ---------------------------------------------------------------- command line

def _main(argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "hash" and len(argv) > 2:
        print(state_hash(json.loads(argv[2])))
        return 0
    a = Anchor(start=False)
    if cmd == "status":
        print(json.dumps(dict(a.counts(), endpoint=a.endpoint, db=a.db_path, key_set=bool(a.api_key)), indent=2))
    elif cmd == "flush":
        print("receipted %d" % a.flush(timeout=120))
        a._upgrade(limit=500)
        print(json.dumps(a.counts(), indent=2))
    elif cmd == "receipt" and len(argv) > 2:
        print(json.dumps(a.receipt(argv[2]), indent=2))
    elif cmd == "verify":
        with a._lk:
            rows = a._db.execute("SELECT receipt FROM receipts").fetchall()
        good = sum(1 for (r,) in rows if (lambda d: verify_inclusion(d.get("entry_hash", ""), d.get("leaf_index", -1),
                                                                      d.get("tree_size", 0), d.get("audit_path", []),
                                                                      d.get("root", "")))(json.loads(r)))
        print("%d of %d stored receipts pass the RFC 6962 inclusion check" % (good, len(rows)))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

```


## `modules/sebbi_engine.py`

229 lines, 8776 bytes

```python
# modules/sebbi_engine.py
"""
Live chain-state endpoint  -  GET /x/sebbi_engine/state

WHAT CHANGED IN v1.1, AND WHY
-----------------------------
v1.0 served this at /verify and returned "status": "sealed". It performed no
verification: no rehash, no chain walk, no proof check. It read the last row of
audit_log and reported that a row existed. A route called verify that returns
sealed, having checked neither, is a word one step past what the check does -
the same fault that has been raised against this codebase before, and the word
an auditor will quote back.

So v1.1 does the same honest job under honest names:

  * action renamed  verify -> state
  * status is now  live / unavailable, never "sealed"
  * tip_digest removed - it was a hash of a hash, proving nothing
  * token_budget removed - unrelated to chain state, it did not belong here
  * every response names the routes that DO verify, and says plainly that
    this one does not

WHAT THIS ROUTE IS
------------------
The current tip and height, read from the database at request time. Nothing
cached, nothing hardcoded. If the chain cannot be read it says so rather than
reporting a reassuring value it cannot stand behind.

WHAT IT IS NOT
--------------
It is not verification. Reading the last row proves a row exists. Verifying
the chain means rewalking it, and confirming the tip was recorded by operators
we do not control. Those are separate routes, listed in every response.

Dual-signature handle(...) so it works with the router
    handle(method, action, data, api_key, ctx) -> (payload, status)
and with older direct-write callers
    handle(handler, path, query_params=None) -> writes the response, returns True

Import-safe: nothing here can crash the server on import.
"""

import os
import json
import time

VERSION = "1.1"
MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")

# GET /state is public by design - anyone can read live state without an
# account. The old ("GET", "verify") pair is kept so existing callers get the
# renamed answer rather than a bare 404.
PUBLIC = {("GET", "state"), ("GET", "verify"), ("GET", "spec"), ("GET", "")}

VERIFY_ELSEWHERE = {
    "chain_tip": "https://sebbi.pro/x/witness/tip",
    "append_only_proof": "https://sebbi.pro/x/consistency/proof",
    "is_my_tip_still_on_this_chain": "https://sebbi.pro/x/consistency/ancestor",
    "who_recorded_our_tip": "https://sebbi.pro/x/roster/list",
    "timestamp_proof_state": "https://sebbi.pro/x/ots/status",
}

NOT_VERIFICATION = (
    "This route reads the current tip and height. It does not verify anything: "
    "it does not rewalk the chain, recompute any hash, or check any external "
    "record. Reading the last row proves a row exists and nothing more. The "
    "routes above are the ones that verify, and you run them yourself."
)

try:
    print("modules.sebbi_engine: loaded (v%s, live-state mode)" % VERSION, flush=True)
except Exception:
    pass


def _read_live_chain(ctx):
    """
    Read the real current chain tip and height from the live database via ctx.

    Returns what was actually found, or a record of why it could not be read.
    It never invents a value.
    """
    if not isinstance(ctx, dict):
        return {"live": False, "reason": "no_context"}

    conn = ctx.get("conn") or ctx.get("db") or ctx.get("connection")
    lock = ctx.get("lock")
    if conn is None:
        return {"live": False, "reason": "no_db_handle"}

    # Matched to modules/witness.py _our_tip(): the chain lives in audit_log,
    # the sealed hash is audit_hash, the height is id.
    query = ("SELECT audit_hash AS seal, id AS height FROM audit_log "
             "ORDER BY id DESC LIMIT 1")

    def _run():
        try:
            row = conn.execute(query).fetchone()
        except Exception:
            return {"live": False, "reason": "query_failed"}
        if not row:
            return {"live": False, "reason": "no_chain_rows"}
        seal = row[0]
        height = row[1]
        if seal is None:
            return {"live": False, "reason": "null_tip"}
        return {"live": True, "tip": str(seal),
                "height": int(height) if height is not None else None}

    try:
        if lock is not None:
            with lock:
                return _run()
        return _run()
    except Exception as e:  # noqa: BLE001
        return {"live": False, "reason": "read_error:" + e.__class__.__name__}


def _build_payload(ctx):
    now = int(time.time())
    chain = _read_live_chain(ctx)

    payload = {
        "module": MODULE_NAME,
        "version": VERSION,
        "read_at": now,
        "read_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }

    if chain.get("live"):
        payload["status"] = "live"
        payload["chain_tip"] = chain["tip"]
        payload["chain_height"] = chain["height"]
        payload["note"] = (
            "Live chain state, read at request time. It changes as the chain "
            "grows, so two reads a minute apart are expected to differ.")
    else:
        payload["status"] = "unavailable"
        payload["chain_tip"] = None
        payload["chain_height"] = None
        payload["reason"] = chain.get("reason", "unknown")
        payload["note"] = (
            "The live chain could not be read for this request, so no state is "
            "reported. This endpoint never returns a placeholder in place of "
            "real state.")

    payload["height_is_not_activity"] = (
        "A liveness beacon seals a block every five minutes, so most of the "
        "height is heartbeat rather than customer decisions. Do not read this "
        "number as usage.")
    payload["this_is_not_verification"] = NOT_VERIFICATION
    payload["verify_it_yourself"] = VERIFY_ELSEWHERE
    return payload


def _spec():
    return {
        "module": MODULE_NAME,
        "version": VERSION,
        "route": "GET /x/sebbi_engine/state",
        "what_it_returns": "The current chain tip and height, read at request time.",
        "what_it_does_not_do": NOT_VERIFICATION,
        "renamed_in_v1_1": (
            "The action was called verify and returned status sealed. It "
            "verified nothing, so both names were wrong. verify still answers, "
            "and returns this same state payload under the honest names."),
        "verify_it_yourself": VERIFY_ELSEWHERE,
        "cost": "Free. No account, no key.",
    }, 200


def handle(*args, **kwargs):
    """Dual-signature handler; autodetects call style from the first argument."""

    # Legacy direct-write style: first arg is an HTTP handler
    if args and hasattr(args[0], "send_response") and hasattr(args[0], "wfile"):
        handler = args[0]
        ctx = getattr(handler, "ctx", None)
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        body = json.dumps(payload, indent=2).encode("utf-8")
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            try:
                handler.send_response(500)
                handler.send_header("Content-Type", "text/plain")
                handler.end_headers()
                handler.wfile.write(b"sebbi_engine: response failed\n")
            except Exception:
                pass
        return True

    # Router style: handle(method, action, data, api_key, ctx)
    method = args[0] if len(args) > 0 else kwargs.get("method")
    action = args[1] if len(args) > 1 else kwargs.get("action", "")
    ctx = args[4] if len(args) > 4 else kwargs.get("ctx")

    # Tolerate action arriving as a full path
    if isinstance(action, str) and action.startswith("/"):
        parts = [x for x in action.strip("/").split("/") if x]
        if len(parts) >= 3 and parts[1] == "sebbi_engine":
            action = parts[2]

    action = (action or "").strip("/").lower()

    if method != "GET":
        return {"error": "method_not_allowed", "GET": ["state", "spec"]}, 405

    if action == "spec":
        return _spec()

    if action in ("state", ""):
        return _build_payload(ctx if isinstance(ctx, dict) else None), 200

    if action == "verify":
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        payload["renamed"] = (
            "This action is now /x/sebbi_engine/state. It was called verify and "
            "returned status sealed, while verifying nothing. Same data, honest "
            "names. Update your caller when convenient.")
        return payload, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["state", "spec"]}, 404

```
