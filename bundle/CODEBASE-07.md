# Codebase — part 7 of 19

Contains:
- `modules/savings.py`
- `modules/selfcheck.py`
- `modules/spec.py`
- `modules/standard.py`
- `modules/stats.py`


## `modules/savings.py`

755 lines, 33108 bytes

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

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "verify"), ("POST", "seal")}

PAGE_PATHS = ("/savings", "/savings.html", "/cost", "/proof-machine")

_patched = [False]
_ready = [False]


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

/* device input */
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

/* the headline */
.headline{background:var(--ink);color:#fff;padding:30px 24px;margin-bottom:14px}
.hl-l{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.hl-v{font-family:var(--disp);font-weight:900;font-size:clamp(38px,12vw,68px);
  line-height:1;letter-spacing:-.03em;color:#7fe3b0}
.hl-s{color:var(--mutei);font-size:14px;margin-top:12px}

/* the stacked comparison - the signature */
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

/* assumptions */
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

/* three year */
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
.m-row b{font-family:var(--mono);font-size:13px}
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
      <div class="h-l">Measured — read from the live chain just now</div>
      <div class="m-row"><span>Blocks sealed</span><b id="m-height">…</b></div>
      <div class="m-row"><span>Bytes per seal</span><b>32</b></div>
      <div class="m-row"><span>Size of the record behind it</span><b>irrelevant</b></div>
      <div class="m-row"><span>External timestamp</span><b id="m-anchor">…</b></div>
      <p class="h-n">A seal is a SHA-256 digest. Thirty-two bytes, whether the decision behind it is one line or a megabyte. That is not a claim about our architecture, it is what a hash is — and it is the whole reason the cost stops tracking the volume.</p>
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
    <p><b>A proof-based layer answers the question at the moment the decision is made.</b> The decision is scored, sealed into a hash chain, externally timestamped and recorded by an independent platform. What survives is a proof that the decision happened, under stated rules, and has not been altered since.</p>
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

    // stacked bars, both scaled to the larger of the two
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

  // slider is logarithmic: 100 to 1,000,000
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

  // ---- measured half: read the live chain, do not assert it
  (async function(){
    try{
      var r = await fetch('/x/stats');
      if(r.ok){
        var d = await r.json();
        var h = (d.chain && d.chain.height);
        $('m-height').textContent = h ? h.toLocaleString('en-GB') : 'unavailable';
      } else { $('m-height').textContent = 'unavailable'; }
    }catch(e){ $('m-height').textContent = 'unavailable'; }
    try{
      var a = await fetch('/api/anchor-status');
      if(a.ok){
        var ad = await a.json();
        var cal = ad.calendars || ad.calendar_count;
        $('m-anchor').textContent = cal ? (cal + ' calendars') : 'live';
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
        sealout.innerHTML = '<span class="bad">Rate limited. Give it a minute.</span>';
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


def _seal(ctx, api_key, data):
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
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

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
    receipt = str(data.get("receipt", "")).strip().lower()
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
        "proof": ("This calculation is a block in a hash chain that is externally "
                  "timestamped and recorded by an independent platform. Altering or "
                  "removing it breaks every block after it."),
        "chain": "/api/verify-chain",
        "external_clock": "/api/anchor-status",
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
            "note": ("The calculator runs in the browser. Nothing a visitor types is "
                     "submitted unless they choose to seal it."),
        }, 200
    if action == "verify":
        _setup(ctx)
        return _verify(ctx, data)
    return {"error": "unknown_action", "action": action,
            "GET": ["status", "verify"], "POST": ["seal"]}, 404

```


## `modules/selfcheck.py`

1091 lines, 45976 bytes

```python
#!/usr/bin/env python3
"""
modules/selfcheck.py  -  the conformance runner, served as a page

WHY THIS IS A MODULE AND NOT A FILE IN ROOT
-------------------------------------------
A plain .html in the repo root does not get served on this deployment, so
the page ships inside the module and is served by the same runtime do_GET
patch that console.py uses for /console and network.py uses for /witness.
It also means the page cannot drift from the module that serves it.

WHAT THE PAGE DOES
------------------
Reads /.well-known/ordering-test.json, then runs every check the document
declares, in the order the document declares them. It discovers what it
needs as it goes: a committed period from /x/complete/periods, a tree size
from /x/consistency/root, a probe value that is not in the log.

It reports four outcomes and is deliberately mean about which is which:

  VERIFIED       the response was checked for what the claim requires -
                 consecutive leaf indices for absence, a proof path for
                 consistency, identical verdicts for reproducibility
  INCONCLUSIVE   the endpoint answered but the semantics were not checked,
                 or the route is POST-only, or the check is key-gated
  FAILED         published as publicly demonstrable and the endpoint is
                 not there. This is the number that matters
  NOT SUPPORTED  the document does not claim it

Reachable is not the same as verified, and this page never counts one as
the other. A runner that only ever passes has not been tested.

NOT A SHARED RUNNER
-------------------
It tests one side. The discovery document's runner field stays null until
the checks are jointly agreed with the other mirror, and publishing this as
though it were the agreed conformance test would claim something neither
operator has earned. Served unlinked and noindex for that reason.

    GET /self-check          the page
    GET /x/selfcheck/status  what is installed
"""

import sys

VERSION = "2.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/self-check", "/self-check.html")

_patched = [False]


PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Ordering test — self check</title>
<style>
  :root{
    --ink:#0a0f1e;
    --ink2:#10182e;
    --line:#1e2942;
    --gold:#c9a84c;
    --ok:#7fe3b0;
    --err:#ff8a80;
    --warn:#e8c06a;
    --mute:#6b7894;
    --text:#dbe3f4;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--ink);
    color:var(--text);
    font-family:var(--mono);
    font-size:14px;
    line-height:1.5;
    -webkit-text-size-adjust:100%;
  }
  .wrap{max-width:760px;margin:0 auto;padding:20px 16px 80px}

  header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:22px}
  .eyebrow{
    font-size:11px;letter-spacing:.18em;text-transform:uppercase;
    color:var(--gold);margin:0 0 8px
  }
  h1{font-size:22px;line-height:1.25;margin:0 0 10px;font-weight:600;letter-spacing:-.01em}
  .sub{color:var(--mute);font-size:13px;margin:0}
  .sub b{color:var(--text);font-weight:600}

  .bar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 0}
  button{
    font-family:var(--mono);font-size:13px;
    background:var(--gold);color:#10121a;border:0;border-radius:2px;
    padding:11px 18px;font-weight:700;letter-spacing:.02em;cursor:pointer;
  }
  button.ghost{background:transparent;color:var(--text);border:1px solid var(--line);font-weight:400}
  button:disabled{opacity:.4;cursor:default}
  button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}

  .tally{
    display:flex;gap:14px;flex-wrap:wrap;margin:20px 0 0;
    font-size:12px;color:var(--mute)
  }
  .tally b{font-size:20px;display:block;font-weight:600;letter-spacing:-.02em}
  .t-pass b{color:var(--ok)} .t-fail b{color:var(--err)}
  .t-inc b{color:var(--warn)} .t-ns b{color:var(--mute)}

  /* the spine: checks hold the order the document declares */
  ol.spine{list-style:none;margin:26px 0 0;padding:0;position:relative}
  ol.spine:before{
    content:"";position:absolute;left:19px;top:6px;bottom:6px;width:1px;
    background:var(--line)
  }
  li.check{position:relative;padding:0 0 2px 52px;margin:0 0 2px}
  .slot{
    position:absolute;left:0;top:12px;width:39px;height:22px;
    display:flex;align-items:center;justify-content:center;
    background:var(--ink);color:var(--mute);
    font-size:11px;letter-spacing:.08em;z-index:1
  }
  .row{
    border-bottom:1px solid var(--line);
    padding:12px 0 13px;
    display:flex;align-items:baseline;gap:10px;flex-wrap:wrap
  }
  .name{font-size:14px;font-weight:600;letter-spacing:-.01em}
  .verdict{
    font-size:10px;letter-spacing:.14em;text-transform:uppercase;
    padding:3px 7px;border:1px solid currentColor;border-radius:2px;white-space:nowrap
  }
  .v-pass{color:var(--ok)} .v-fail{color:var(--err)}
  .v-inc{color:var(--warn)} .v-ns{color:var(--mute)}
  .v-run{color:var(--gold)}
  .v-wait{color:var(--line)}
  .why{flex-basis:100%;color:var(--mute);font-size:12.5px;margin-top:2px}
  .why b{color:var(--text);font-weight:600}
  .ep{
    flex-basis:100%;font-size:11.5px;color:var(--mute);
    margin-top:5px;word-break:break-all
  }
  .ep a{color:var(--gold);text-decoration:none;border-bottom:1px solid rgba(201,168,76,.35)}
  details{flex-basis:100%;margin-top:8px}
  summary{
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--mute);cursor:pointer;list-style:none
  }
  summary::-webkit-details-marker{display:none}
  summary:before{content:"▸ ";}
  details[open] summary:before{content:"▾ ";}
  pre{
    background:var(--ink2);border:1px solid var(--line);border-radius:2px;
    margin:8px 0 0;padding:10px;font-size:11.5px;line-height:1.45;
    white-space:pre-wrap;word-break:break-word;max-height:280px;overflow:auto
  }
  li.check.done .slot{color:var(--text)}

  footer{
    margin-top:34px;border-top:1px solid var(--line);padding-top:16px;
    color:var(--mute);font-size:12px
  }
  footer p{margin:0 0 9px}
  .flash{
    border:1px solid var(--err);color:var(--err);
    padding:11px;border-radius:2px;margin:16px 0 0;font-size:12.5px
  }
  @media (prefers-reduced-motion: no-preference){
    li.check.done .row{animation:in .22s ease-out}
    @keyframes in{from{opacity:.35}to{opacity:1}}
  }
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">Ordering test · self check</p>
  <h1>Run every check this domain publishes about itself.</h1>
  <p class="sub">Reads <b>/.well-known/ordering-test.json</b>, then tests each check in the order the document declares it. Nothing here is a shared runner — it only tests this side.</p>
  <div class="bar">
    <button id="run">Run all checks</button>
    <button id="reload" class="ghost">Reload document</button>
  </div>
  <div class="tally" id="tally" hidden>
    <div class="t-pass"><b id="n-pass">0</b>verified</div>
    <div class="t-fail"><b id="n-fail">0</b>failed</div>
    <div class="t-inc"><b id="n-inc">0</b>inconclusive</div>
    <div class="t-ns"><b id="n-ns">0</b>not public</div>
  </div>
  <div id="flash"></div>
</header>

<ol class="spine" id="spine"></ol>

<footer>
  <p><b>Verified</b> means the response was checked for what the claim actually requires. <b>Reachable</b> means the endpoint answered but this runner did not confirm the semantics — reported as inconclusive, not as a pass.</p>
  <p>A check marked not publicly demonstrable is reported as such and never counted as a pass. This page cannot see behind a key and does not pretend to.</p>
</footer>

</div>

<script>
(function(){
  "use strict";

  var DOC = "/.well-known/ordering-test.json";
  var doc = null;
  var ctx = {};

  var el = function(id){ return document.getElementById(id); };
  var spine = el("spine");

  function flash(msg){
    el("flash").innerHTML = msg ? '<div class="flash">' + msg + '</div>' : '';
  }

  function pad(n){ return (n < 10 ? "0" : "") + n; }

  function jget(path){
    return fetch(path, {headers:{"Accept":"application/json"}}).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  function jpost(path, payload){
    return fetch(path, {
      method:"POST",
      headers:{"Content-Type":"application/json","Accept":"application/json"},
      body:JSON.stringify(payload)
    }).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  // SHA-256 in the visitor's own browser. The point of rule binding is that
  // the server hands back the exact string it hashed; if this page recomputes
  // the digest and it matches, nothing was taken on the server's word.
  function sha256hex(s){
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(s))
      .then(function(buf){
        var b = new Uint8Array(buf), out = "";
        for (var i = 0; i < b.length; i++){
          var h = b[i].toString(16);
          out += (h.length === 1 ? "0" : "") + h;
        }
        return out;
      });
  }

  var HEX64 = /^[0-9a-f]{64}$/;

  function walk(node, path, strings, hexes){
    if (typeof node === "string"){
      strings.push({path: path || "(root)", value: node});
      if (HEX64.test(node)) hexes[node] = path || "(root)";
      return;
    }
    if (Array.isArray(node)){
      for (var i = 0; i < node.length; i++) walk(node[i], path + "[" + i + "]", strings, hexes);
      return;
    }
    if (node && typeof node === "object"){
      for (var k in node){
        if (Object.prototype.hasOwnProperty.call(node, k)){
          walk(node[k], path ? path + "." + k : k, strings, hexes);
        }
      }
    }
  }

  // The payload these POST routes expect is not published, so this does two
  // things rather than guess: it tries the shapes they plausibly take, and
  // when a rejection names a missing field it adds that field and tries
  // again. A module that answers "'trust'" has told you what it wants.
  function defaultFor(name){
    if (/country/.test(name)) return "GB";
    if (/currency/.test(name)) return "GBP";
    if (/(^|_)id$|_id$|user|device|session/.test(name)) return "self-check";
    if (/trust|score|ratio|rate/.test(name)) return 0.5;
    return 0;
  }

  function missingField(body){
    var text = (body && typeof body === "object")
      ? (body.message || body.error || JSON.stringify(body))
      : String(body || "");
    // A bare quoted identifier is what a KeyError looks like once it reaches
    // the response. Also catch an explicit "missing x" phrasing.
    var m = text.match(/^['"]([A-Za-z_][A-Za-z0-9_]*)['"]$/) ||
            text.match(/missing[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i) ||
            text.match(/required[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i);
    return m ? m[1] : null;
  }

  function postShapes(url, inner){
    var learned = [];

    function round(probe, depth){
      var shapes = [{name:"flat", body:probe},
                    {name:"inputs", body:{inputs:probe}},
                    {name:"event", body:{event:probe}}];
      var rejected = {};

      function go(i){
        if (i >= shapes.length){
          // Every shape failed the same way? Learn the field and go again.
          var field = null;
          for (var k in rejected){
            if (Object.prototype.hasOwnProperty.call(rejected, k)){
              field = missingField(rejected[k]);
              if (field) break;
            }
          }
          if (field && depth < 6 && !(field in probe)){
            var next = {};
            for (var p in probe){
              if (Object.prototype.hasOwnProperty.call(probe, p)) next[p] = probe[p];
            }
            next[field] = defaultFor(field);
            learned.push(field);
            return round(next, depth + 1);
          }
          return Promise.resolve({ok:false, rejected:rejected, learned:learned, probe:probe});
        }
        return jpost(url, shapes[i].body).then(function(r){
          if (!r.ok){ rejected[shapes[i].name] = r.body; return go(i + 1); }
          return {ok:true, shape:shapes[i].name, body:r.body, sent:shapes[i].body,
                  rejected:rejected, learned:learned};
        }).catch(function(e){
          rejected[shapes[i].name] = e.message; return go(i + 1);
        });
      }
      return go(0);
    }

    return round(inner, 0);
  }

  function oneMessage(b){
    if (b && typeof b === "object" && (b.message || b.error)) return b.message || b.error;
    if (typeof b === "string") return b.slice(0, 200);
    return "no message";
  }

  // Every shape's rejection, not just the first. The first one is usually the
  // least informative, and the shape that nearly worked is the one that says
  // what is actually wrong.
  function firstMessage(rejected){
    var parts = [];
    for (var k in rejected){
      if (Object.prototype.hasOwnProperty.call(rejected, k)){
        parts.push("<b>" + k + "</b>: " + oneMessage(rejected[k]));
      }
    }
    return parts.length ? parts.join(" \u00b7 ") : "no message returned";
  }

  function learnedNote(res){
    return (res.learned && res.learned.length)
      ? " (after adding the fields it named: " + res.learned.join(", ") + ")"
      : "";
  }

  // The engine's real signal names. Guessing these from outside was the
  // thing that kept the reproducibility check amber.
  var PROBE = {action: "payment", amount: 4200, trust: 0.4,
               v60: 12, v5m: 20, v1h: 60,
               device_risk: 0.3, anomaly: 0.2, country: "UK",
               country_shift: false};

  function show(v){
    try { return JSON.stringify(v, null, 2); } catch(e){ return String(v); }
  }

  // ---- document ---------------------------------------------------------

  function loadDoc(){
    flash("");
    spine.innerHTML = "";
    el("tally").hidden = true;
    // The module that serves the discovery document installs its route on
    // first use, so after a deploy the document 404s until something touches
    // it. Touch it here rather than making a person remember to.
    return jget("/x/standard/status").catch(function(){}).then(function(){
      return jget(DOC);
    }).then(function(r){
      if (!r.ok || typeof r.body !== "object"){
        flash("Could not read " + DOC + " — status " + r.status +
              ". If this is a fresh deploy, open /x/standard/status once to install the route, then reload.");
        doc = null;
        return null;
      }
      doc = r.body;
      draw();
      return doc;
    }).catch(function(e){
      flash("Request failed: " + e.message + ". Serve this page from the same domain as the document.");
    });
  }

  function draw(){
    var names = Object.keys(doc.checks || {});
    spine.innerHTML = "";
    names.forEach(function(name, i){
      var c = doc.checks[name];
      var li = document.createElement("li");
      li.className = "check";
      li.id = "chk-" + name;
      li.innerHTML =
        '<span class="slot">' + pad(i+1) + '</span>' +
        '<div class="row">' +
          '<span class="name">' + name.replace(/_/g," ") + '</span>' +
          '<span class="verdict v-wait" data-v>waiting</span>' +
          '<div class="why" data-why>' +
            (c.supported ? "declared supported" : "declared not supported") +
            (c.demonstrable_publicly ? ", publicly demonstrable" : ", not publicly demonstrable") +
          '</div>' +
          (c.endpoint ? '<div class="ep">' + c.endpoint + '</div>' : '') +
        '</div>';
      spine.appendChild(li);
    });
    var t = doc.vendor ? doc.vendor : "this domain";
    document.querySelector(".sub").innerHTML =
      'Document loaded from <b>' + (doc.base_url || location.origin) + '</b> · vendor <b>' + t +
      '</b> · version <b>' + (doc.ordering_test_version || "?") + '</b> · ' +
      names.length + ' checks declared.';
  }

  function setResult(name, verdict, why, detail){
    var li = el("chk-" + name);
    if (!li) return;
    li.classList.add("done");
    var v = li.querySelector("[data-v]");
    var map = {PASS:"v-pass", FAIL:"v-fail", INCONCLUSIVE:"v-inc", "NOT SUPPORTED":"v-ns", RUNNING:"v-run"};
    v.className = "verdict " + (map[verdict] || "v-wait");
    v.textContent = verdict;
    li.querySelector("[data-why]").innerHTML = why;
    if (detail !== undefined){
      var old = li.querySelector("details");
      if (old) old.remove();
      var d = document.createElement("details");
      d.innerHTML = "<summary>response</summary><pre>" +
        show(detail).replace(/</g,"&lt;") + "</pre>";
      li.querySelector(".row").appendChild(d);
    }
  }

  function running(name){
    var li = el("chk-" + name);
    if (!li) return;
    var v = li.querySelector("[data-v]");
    v.className = "verdict v-run";
    v.textContent = "running";
  }

  // ---- context the checks need before they can run ----------------------

  function buildContext(){
    ctx = {};
    var jobs = [];

    jobs.push(jget("/x/complete/periods").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      var list = r.body.periods || r.body.committed || r.body;
      if (!Array.isArray(list)) return;
      for (var i = list.length - 1; i >= 0; i--){
        var p = list[i];
        var id = (typeof p === "string") ? p : (p.period || p.id);
        var committed = (typeof p === "string") ? true :
          (p.committed === undefined ? true : !!p.committed);
        if (id && committed){ ctx.period = id; break; }
      }
    }).catch(function(){}));

    jobs.push(jget("/x/consistency/root").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      ctx.size = r.body.size || r.body.tree_size || r.body.count;
      ctx.root = r.body.root;
    }).catch(function(){}));

    var hex = "0123456789abcdef";
    ctx.absent = "";
    for (var i = 0; i < 64; i++) ctx.absent += hex[Math.floor(Math.random() * 16)];

    return Promise.all(jobs);
  }

  function fill(endpoint){
    if (!endpoint) return null;
    return endpoint
      .replace("{period}", ctx.period || "")
      .replace("{value}", ctx.absent)
      .replace("{first}", "1")
      .replace("{second}", ctx.size ? String(ctx.size) : "");
  }

  // ---- the checks -------------------------------------------------------
  // Each returns {verdict, why, detail}.

  var runners = {

    authority_tokens: function(c){
      return jget(c.endpoint || "/x/continuity/decisions").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var list = b.decisions || [];
        if (!list.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no authority has been exercised " +
                      "yet \u2014 nothing to check, which is not the same as nothing failing",
                  detail:b};
        }
        // Pull one at random and confirm the listing agrees with the sealed
        // decision behind it. A summary that disagrees with its own record is
        // the failure worth catching here.
        var pick = list[Math.floor(Math.random() * list.length)];
        return jget("/x/continuity/decision?evaluation=" + encodeURIComponent(pick.evaluation))
          .then(function(d){
            if (!d.ok){
              return {verdict:"FAIL",
                      why:"the listing offers " + pick.evaluation + " but the decision behind " +
                          "it returned " + d.status,
                      detail:{listed:pick, fetched:d.body}};
            }
            var db = d.body || {};
            if (db.verdict !== pick.verdict){
              return {verdict:"FAIL",
                      why:"the public listing says <b>" + pick.verdict + "</b> and the sealed " +
                          "decision says <b>" + db.verdict + "</b>",
                      detail:{listed:pick, sealed:db}};
            }
            if (!db.lineage_digest || db.block_index === undefined){
              return {verdict:"INCONCLUSIVE",
                      why:"decision retrieved without a key, but it carries no lineage digest " +
                          "or block index to tie it to the chain",
                      detail:db};
            }
            return {verdict:"PASS",
                    why:"real sealed decisions readable without an account \u2014 <b>" +
                        (b.totals ? b.totals.allowed : "?") + " allowed, " +
                        (b.totals ? b.totals.challenged : "?") + " challenged, " +
                        (b.totals ? b.totals.blocked : "?") + " blocked</b>. Picked <b>" +
                        pick.evaluation + "</b> at random and the sealed record agrees with " +
                        "the listing, carrying its lineage digest and block index" +
                        (db.broken_invariant ? " and naming <b>" + db.broken_invariant +
                                               "</b> as what broke" : ""),
                    detail:{listing:b.totals, picked:pick, sealed:db}};
          });
      });
    },

    reconciliation: function(c){
      return jget(c.endpoint || "/x/reconcile/public").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var runs = b.recent || [];
        if (!runs.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no reconciliation run exists yet",
                  detail:b};
        }
        var done = runs.filter(function(x){ return x.status === "reconciled"; });
        var pick = (done.length ? done : runs)[0];
        return jget("/x/reconcile/proof?id=" + encodeURIComponent(pick.run_id)).then(function(p){
          if (!p.ok){
            return {verdict:"FAIL",
                    why:"the listing offers " + pick.run_id + " but its proof returned " + p.status,
                    detail:{listed:pick, fetched:p.body}};
          }
          var pb = p.body || {};
          if (pb.plan_block_index === null || pb.result_block_index === null){
            return {verdict:"INCONCLUSIVE",
                    why:"run <b>" + pick.run_id + "</b> was planned but never submitted, so " +
                        "there is no result block to order against. Published rather than " +
                        "hidden, which is the right behaviour, but it does not demonstrate " +
                        "the check",
                    detail:pb};
          }
          if (!(pb.plan_block_index < pb.result_block_index)){
            return {verdict:"FAIL",
                    why:"the selection was sealed at block " + pb.plan_block_index +
                        " and the result at " + pb.result_block_index +
                        " \u2014 the sample was not fixed before the data was requested",
                    detail:pb};
          }
          return {verdict:"PASS",
                  why:"the sample for <b>" + pb.run_id + "</b> was sealed at block <b>" +
                      pb.plan_block_index + "</b> and the result at <b>" +
                      pb.result_block_index + "</b> \u2014 fixed before any data was asked " +
                      "for, checkable without an account. Across the record: <b>" +
                      b.mismatched + " mismatches</b> and <b>" + b.abandoned +
                      " abandoned run" + (b.abandoned === 1 ? "" : "s") +
                      "</b> published rather than buried",
                  detail:{summary:{runs:b.runs, matched:b.matched, mismatched:b.mismatched,
                                   abandoned:b.abandoned}, proof:pb}};
        });
      });
    },

    rule_binding: function(c){
      return postShapes(c.endpoint || "/x/rulebind/prove", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected),
                  detail:res.rejected};
        }
        var strings = [], hexes = {};
        walk(res.body, "", strings, hexes);
        return Promise.all(strings.map(function(s){
          return sha256hex(s.value).then(function(h){ return {path:s.path, hash:h}; });
        })).then(function(hashed){
          for (var i = 0; i < hashed.length; i++){
            if (hexes[hashed[i].hash]){
              return {verdict:"PASS",
                      why:"the response returned the exact string that was hashed. SHA-256 of " +
                          "<b>" + hashed[i].path + "</b>, recomputed in this browser, equals " +
                          "<b>" + hexes[hashed[i].hash] + "</b> \u2014 the ruleset version is " +
                          "inside the digest, not a field beside it",
                      detail:res.body};
            }
          }
          return {verdict:"INCONCLUSIVE",
                  why:"accepted the <b>" + res.shape + "</b> payload" + learnedNote(res) +
                      ", but no string it returned " +
                      "hashes to any digest in the response, so the binding was not confirmed here",
                  detail:res.body};
        });
      });
    },

    commit_before_reveal: function(c){
      return jpost(c.endpoint || "/x/demo/review", PROBE).then(function(r){
        if (!r.ok){
          return {verdict:"INCONCLUSIVE", why:"POST returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var cid = b.case_id;
        if (!cid){
          return {verdict:"INCONCLUSIVE", why:"no case id came back to commit against", detail:b};
        }
        // The case must arrive with the verdict withheld. If it is in there,
        // nothing committed afterwards can have preceded a reveal that had
        // already happened.
        var text = JSON.stringify(b);
        if (/"(machine_verdict|verdict|decision)"\s*:\s*"(ALLOW|CHALLENGE|BLOCK)"/i.test(text)){
          return {verdict:"FAIL",
                  why:"the case arrived with the machine verdict already in it \u2014 the order " +
                      "cannot be fixed after the answer is known",
                  detail:b};
        }

        return jpost("/x/demo/commit", {case_id: cid, verdict: "challenge"}).then(function(k){
          if (!k.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"the case opened with the verdict withheld, but the commit returned " +
                        k.status,
                    detail:{case:b, commit:k.body}};
          }
          var kb = k.body || {};
          if (kb.block_index === undefined || !kb.machine_verdict){
            return {verdict:"INCONCLUSIVE",
                    why:"committed, but the response carries no block index or no revealed " +
                        "verdict to check the order against",
                    detail:{case:b, commit:kb}};
          }
          // A commitment you can redo is not a commitment.
          return jpost("/x/demo/commit", {case_id: cid, verdict: "allow"}).then(function(again){
            var refused = !again.ok ||
                          (again.body && again.body.error === "already_committed");
            if (!refused){
              return {verdict:"FAIL",
                      why:"the same case accepted a second, different verdict \u2014 a " +
                          "commitment that can be redone fixes nothing",
                      detail:{first:kb, second:again.body}};
            }
            return {verdict:"PASS",
                    why:"the case was issued with the verdict withheld, a human verdict was " +
                        "sealed at block <b>" + kb.block_index + "</b>, the machine verdict " +
                        "(<b>" + kb.machine_verdict + "</b>) was revealed only in that same " +
                        "response, dwell of <b>" + kb.dwell_seconds + "s</b> was recorded, and " +
                        "a second commit was refused \u2014 the order is fixed, not asserted",
                    detail:{case:b, commit:kb, second_attempt:again.body}};
          });
        });
      }).catch(function(e){
        return {verdict:"INCONCLUSIVE", why:"request failed: " + e.message};
      });
    },

    mutual_witnessing: function(c){
      return jget("/x/witness/peers").then(function(p){
        return jget("/x/witness/tip").then(function(t){
          if (!p.ok) return {verdict:"FAIL", why:"peers endpoint returned " + p.status, detail:p.body};
          if (!t.ok) return {verdict:"FAIL", why:"tip endpoint returned " + t.status, detail:t.body};
          var peers = p.body.peers || p.body;
          var n = Array.isArray(peers) ? peers.length : 0;
          if (n === 0){
            return {verdict:"FAIL", why:"no peer chains listed — witnessing claims an external party and there isn't one", detail:p.body};
          }
          return {verdict:"PASS",
                  why:"<b>" + n + " peer chain" + (n>1?"s":"") + "</b> listed and a current tip served, both without an account",
                  detail:{peers:p.body, tip:t.body}};
        });
      });
    },

    completeness_proof: function(c){
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no closed committed period found at /x/complete/periods, so there is nothing to ask for a root of"});
      }
      var url = fill(c.endpoint) || ("/x/complete/root?period=" + ctx.period);
      return jget(url).then(function(r){
        if (r.status === 409) return {verdict:"INCONCLUSIVE", why:"period " + ctx.period + " is still live — only closed periods commit", detail:r.body};
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var root = r.body.root || r.body.merkle_root;
        var count = r.body.count !== undefined ? r.body.count : r.body.leaf_count;
        if (!root || count === undefined){
          return {verdict:"INCONCLUSIVE", why:"reachable, but no root and exact leaf count in the response", detail:r.body};
        }
        return {verdict:"PASS",
                why:"root and an exact count of <b>" + count + "</b> leaves, committed for " + ctx.period + " before any export was asked for",
                detail:r.body};
      });
    },

    absence_proof: function(c){
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no committed period, so there is nothing to prove absence against"});
      }
      var url = fill(c.endpoint) ||
        ("/x/complete/prove?period=" + ctx.period + "&value=" + ctx.absent);
      return jget(url).then(function(r){
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var n = (r.body && r.body.neighbours) || (r.body && r.body.neighbors) || {};
        if (n.lower && n.upper &&
            n.lower.index !== undefined && n.upper.index !== undefined){
          if (n.upper.index - n.lower.index === 1){
            return {verdict:"PASS",
                    why:"neighbours at indices <b>" + n.lower.index + "</b> and <b>" +
                        n.upper.index + "</b> \u2014 consecutive, so nothing can sit between " +
                        "them. Absence proved, not asserted",
                    detail:r.body};
          }
          return {verdict:"FAIL",
                  why:"neighbour indices " + n.lower.index + " and " + n.upper.index +
                      " are not consecutive \u2014 that proves nothing",
                  detail:r.body};
        }
        if (n.lower || n.upper){
          return {verdict:"INCONCLUSIVE",
                  why:"boundary case \u2014 the probe sorted outside the whole set, so only one " +
                      "neighbour came back. Valid, but it does not exercise the adjacency argument",
                  detail:r.body};
        }
        return {verdict:"INCONCLUSIVE", why:"no neighbours in the response", detail:r.body};
      });
    },

    consistency_proof: function(c){
      if (!ctx.size){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"could not read a tree size from /x/consistency/root"});
      }
      var first = Math.max(1, Math.floor(ctx.size / 2));
      var url = "/x/consistency/proof?first=" + first + "&second=" + ctx.size;
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"returned " + r.status + " for first=" + first + " second=" + ctx.size,
                  detail:r.body};
        }
        var b = r.body || {};
        var path = b.consistency_proof || b.proof || b.path;
        if (!Array.isArray(path) || path.length === 0){
          return {verdict:"INCONCLUSIVE", why:"no proof path in the response", detail:b};
        }
        // The proof has to be against the same tip served at /x/consistency/root.
        // A proof against some other root proves something about some other log.
        if (ctx.root && b.second_root && b.second_root !== ctx.root){
          return {verdict:"FAIL",
                  why:"the proof is against a different root than /x/consistency/root serves \u2014 " +
                      "two views of the log, which is the split view this check exists to rule out",
                  detail:b};
        }
        return {verdict:"PASS",
                why:"RFC 6962 proof of <b>" + path.length + " nodes</b> that the log at " + first +
                    " is a prefix of the log at " + ctx.size +
                    ", against the same tip served separately \u2014 append-only shown, not claimed",
                detail:b};
      });
    },

    reproducibility: function(c){
      return postShapes(c.endpoint || "/x/replay/challenge", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected) +
                      ". This endpoint is published as publicly demonstrable, so the shape it " +
                      "wants belongs in the document",
                  detail:res.rejected};
        }
        return jpost(c.endpoint || "/x/replay/challenge", res.sent).then(function(b){
          return jget("/x/replay/fingerprint").then(function(f){
            var va = res.body && (res.body.verdict || res.body.decision);
            var vb = b.body && (b.body.verdict || b.body.decision);
            if (!va || !vb){
              return {verdict:"INCONCLUSIVE",
                      why:"both runs accepted under the <b>" + res.shape + "</b> shape, but no " +
                          "verdict field came back to compare",
                      detail:{first:res.body, second:b.body}};
            }
            if (va === vb){
              return {verdict:"PASS",
                      why:"identical inputs submitted twice both returned <b>" + va + "</b> " +
                          "under one code fingerprint" + learnedNote(res) +
                          " \u2014 determinism shown without disclosing any scoring logic",
                      detail:{shape:res.shape, fingerprint:f.body,
                              first:res.body, second:b.body}};
            }
            return {verdict:"FAIL",
                    why:"identical inputs gave <b>" + va + "</b> then <b>" + vb +
                        "</b> \u2014 not deterministic",
                    detail:{first:res.body, second:b.body}};
          });
        });
      });
    },

    external_anchoring: function(c){
      var url = c.endpoint || "/api/anchor-status";
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"<b>" + url + " returned " + r.status + "</b> \u2014 this check is " +
                      "published as publicly demonstrable and the endpoint under it is not there",
                  detail:r.body};
        }
        var b = r.body || {};
        var tip = b.tip || b.chain_tip || b.anchored_tip;
        if (!tip){
          return {verdict:"INCONCLUSIVE",
                  why:"the endpoint answers but names no anchored tip, so there is nothing to " +
                      "check it against",
                  detail:b};
        }

        // A browser cannot verify Bitcoin, and this page will not pretend to.
        // What it CAN settle is the question that actually decides the check:
        // is the tip that was submitted to the external authority a tip of
        // THIS log? An anchor over some other chain proves nothing about this
        // one, and that substitution is the only way this check fails
        // quietly.
        return jget("/x/consistency/ancestor?tip=" + encodeURIComponent(tip)).then(function(a){
          if (a.status === 409){
            return {verdict:"FAIL",
                    why:"the anchored tip is <b>not</b> on the log being served now \u2014 the " +
                        "external timestamp covers a different chain, which is the fork this " +
                        "check exists to catch",
                    detail:{anchor:b, ancestor:a.body}};
          }
          if (!a.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found, but /x/consistency/ancestor returned " + a.status +
                        " so it could not be placed on this log",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var text = JSON.stringify(a.body || {});
          var placed = /"(ancestor|is_ancestor|valid|ok|confirmed|on_chain)"\s*:\s*true/i.test(text) ||
                       /"(consistency_proof|proof|path)"\s*:\s*\[/.test(text);
          if (!placed){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found and the ancestor route answered, but this runner " +
                        "could not read a confirmation out of the response",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var stamped = (b.ots_ok === true) || /anchored/i.test(String(b.status || ""));
          return {verdict:"PASS",
                  why:"the tip submitted to the external authority is proved to be on <b>this</b> " +
                      "log, not a substituted one \u2014 checked against /x/consistency/ancestor" +
                      (stamped ? ", and the operator reports it stamped: " +
                                 String(b.status || "anchored")
                               : ", though the operator does not report it stamped yet") +
                      ". The attestation itself is the authority's to confirm, not this page's",
                  detail:{anchor:b, ancestor:a.body}};
        }).catch(function(e){
          return {verdict:"INCONCLUSIVE",
                  why:"anchored tip found but the ancestor check failed: " + e.message,
                  detail:b};
        });
      });
    }
  };

  // generic fallback: liveness only, reported honestly as inconclusive
  function genericRunner(name, c){
    var url = fill(c.endpoint);
    if (!url) return Promise.resolve({verdict:"INCONCLUSIVE", why:"declared publicly demonstrable but no endpoint given"});
    if (url.indexOf("{") !== -1){
      return Promise.resolve({verdict:"INCONCLUSIVE", why:"endpoint has a placeholder this runner could not fill: " + url});
    }
    return jget(url).then(function(r){
      var b = r.body || {};
      // This router answers a method mismatch with 404 unknown_action and
      // lists the methods it does accept. A POST-only route is present, not
      // missing, and calling it missing would be a false failure.
      var postOnly = (b.error === "unknown_action") && Array.isArray(b.POST) &&
                     (b.POST.indexOf(url.split("?")[0].split("/").pop()) !== -1 ||
                      (Array.isArray(b.GET) && b.GET.length === 0));
      if (r.status === 405 || r.status === 501 || postOnly){
        return {verdict:"INCONCLUSIVE",
                why:"POST-only endpoint \u2014 present and listed by the router, but it cannot " +
                    "be exercised from a plain page",
                detail:r.body};
      }
      if (b.error === "unknown_action"){
        return {verdict:"INCONCLUSIVE",
                why:"the route answered but does not accept GET. Reachable, semantics not checked",
                detail:r.body};
      }
      if (!r.ok){
        return {verdict:"FAIL", why:"<b>" + url + " returned " + r.status + "</b>", detail:r.body};
      }
      return {verdict:"INCONCLUSIVE", why:"reachable — semantics not checked by this runner", detail:r.body};
    });
  }

  // ---- run --------------------------------------------------------------

  function runAll(){
    if (!doc){ flash("No document loaded."); return; }
    el("run").disabled = true;
    var tally = {PASS:0, FAIL:0, INCONCLUSIVE:0, "NOT SUPPORTED":0};
    el("tally").hidden = false;

    buildContext().then(function(){
      var names = Object.keys(doc.checks);
      var chain = Promise.resolve();

      names.forEach(function(name){
        chain = chain.then(function(){
          var c = doc.checks[name];

          if (!c.supported){
            setResult(name, "NOT SUPPORTED", "the document does not claim this check");
            tally["NOT SUPPORTED"]++;
            return;
          }
          if (!c.demonstrable_publicly){
            setResult(name, "INCONCLUSIVE",
              "built and claimed, but key-gated — nothing here can confirm it, which is what the document says");
            tally.INCONCLUSIVE++;
            return;
          }

          running(name);
          var fn = runners[name] ? runners[name].bind(null, c) : genericRunner.bind(null, name, c);
          return fn().catch(function(e){
            return {verdict:"FAIL", why:"request threw: " + e.message};
          }).then(function(res){
            setResult(name, res.verdict, res.why, res.detail);
            tally[res.verdict] = (tally[res.verdict] || 0) + 1;
            el("n-pass").textContent = tally.PASS;
            el("n-fail").textContent = tally.FAIL;
            el("n-inc").textContent = tally.INCONCLUSIVE;
            el("n-ns").textContent = tally["NOT SUPPORTED"];
          });
        });
      });

      chain.then(function(){
        el("run").disabled = false;
        el("n-pass").textContent = tally.PASS;
        el("n-fail").textContent = tally.FAIL;
        el("n-inc").textContent = tally.INCONCLUSIVE;
        el("n-ns").textContent = tally["NOT SUPPORTED"];
        if (tally.FAIL > 0){
          flash(tally.FAIL + " check" + (tally.FAIL>1?"s":"") +
                " published as publicly demonstrable did not hold up. Fix the endpoint or change the document — the two have to agree.");
        }
      });
    });
  }

  el("run").addEventListener("click", runAll);
  el("reload").addEventListener("click", loadDoc);
  loadDoc();
})();
</script>
</body>
</html>
'''


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_selfcheck_patched", False):
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
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._selfcheck_patched = True
    _patched[0] = True
    print("SELFCHECK: /self-check installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("SELFCHECK: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"installed": bool(_patched[0]),
                "install_result": state,
                "module_version": VERSION,
                "serving": list(PAGE_PATHS),
                "page_bytes": len(PAGE),
                "note": "Runs against whichever host serves it. Same origin, so the browser "
                        "does not block the requests. Unlinked and noindex on purpose - it "
                        "tests one operator's own document and is not a joint runner."}, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/spec.py`

121 lines, 5086 bytes

```python
"""
Live API specification - /x/spec

/api/spec is a hardcoded constant. It describes the API as it was when
somebody last remembered to update it, which is a documentation problem
pretending to be a feature.

This discovers what is actually loaded, right now, by reading the modules
directory and each module's own docstring. Add a module and the spec
updates itself. Delete one and it disappears. There is no separate list to
maintain and therefore no list that can drift.

That matters here more than it would elsewhere: a platform whose pitch is
"check it, don't trust it" should not ship a self-description that is
quietly out of date.

    GET /x/spec           everything currently live
    GET /x/spec/modules   just the module list
"""

import importlib, os, pkgutil, re

VERSION = "1.0"

_EP = re.compile(r"^\s*(GET|POST|PUT|DELETE)\s+(/\S+)\s*(.*)$")


def _describe(name):
    """Pull a module's summary and endpoint list out of its own docstring."""
    try:
        m = importlib.import_module("modules." + name)
    except Exception as e:
        return {"module": name, "loaded": False, "error": str(e)}
    doc = (m.__doc__ or "").strip()
    lines = doc.splitlines()
    summary = ""
    for ln in lines:
        t = ln.strip()
        if t and not t.startswith("-") and not _EP.match(ln):
            summary = t
            break
    endpoints = []
    for ln in lines:
        mm = _EP.match(ln)
        if mm:
            endpoints.append({"method": mm.group(1),
                              "path": mm.group(2),
                              "takes": mm.group(3).strip() or None})
    out = {"module": name, "loaded": True, "summary": summary,
           "endpoints": endpoints,
           "version": getattr(m, "VERSION", None)}
    if not hasattr(m, "handle"):
        out["warning"] = "module has no handle() - it will not route"
    return out


def _modules():
    d = os.path.dirname(__file__)
    names = sorted(x.name for x in pkgutil.iter_modules([d])
                   if x.name not in ("router", "spec"))
    return [_describe(n) for n in names]


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404

    mods = _modules()

    if action == "modules":
        return {"count": len(mods), "modules": mods}, 200

    if action in ("", "all"):
        return {
            "spec_version": VERSION,
            "generated": "live - discovered at request time, not a stored list",
            "core": {
                "decision_engine": {
                    "path": "/api/govern",
                    "method": "POST",
                    "auth": "Bearer key",
                    "note": "deterministic scoring, verdict sealed before the response returns"
                },
                "notaries_public": [
                    {"method": "POST", "path": "/api/post/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/verify-post", "auth": "none"},
                    {"method": "POST", "path": "/api/identity/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/identity/check", "auth": "none"},
                    {"method": "POST", "path": "/api/payment/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/payment/check", "auth": "none"}
                ],
                "verification_public": [
                    {"method": "GET", "path": "/api/verify-chain",
                     "returns": "whole-chain integrity, recomputed"},
                    {"method": "GET", "path": "/api/inclusion",
                     "returns": "whether a given 64-char hash is sealed"},
                    {"method": "GET", "path": "/api/anchor-status",
                     "returns": "current tip, OpenTimestamps proof, calendar count"},
                    {"method": "GET", "path": "/api/regulation-map",
                     "returns": "engine features mapped to legal obligations"}
                ]
            },
            "modules": {
                "prefix": "/x/<module>/<action>",
                "auth": "Bearer key on every module route",
                "count": len(mods),
                "loaded": mods
            },
            "chain": {
                "algorithm": "SHA-256 hash chain",
                "scope": "one chain - every module seals into the same sequence as /api/govern",
                "anchoring": "chain tip submitted to OpenTimestamps, aggregated into a Merkle root, root committed to Bitcoin by several independent calendars",
                "receipts": "gapless per-key sequence issued in the same transaction as the chain write",
                "verify": "/api/verify-chain and /api/anchor-status, both without a key"
            },
            "honest_note": "This spec is generated by reading the modules directory at request time rather than from a stored list, so it cannot describe capabilities that are not actually loaded."
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["", "modules"]}, 404

```


## `modules/standard.py`

422 lines, 19423 bytes

```python
"""
modules/standard.py  -  the Ordering Test discovery document for this domain

WHAT IT SERVES
--------------
  GET /.well-known/ordering-test.json   this operator's discovery document
  GET /x/standard/hash                  sha256 of that document
  GET /x/standard/status                what is installed, and honest counts

SHAPE
-----
Deliberately identical to the shape Red Flag AI Pro published first:

    checks: { <name>: { supported, demonstrable_publicly, endpoint, note } }

Two fields, not one, and the second is the better idea. "We built it" and
"you can verify it without an account" are different claims, and most of this
market blurs them. Separating them lets a vendor be honest about having
something real that an outsider still has to take on trust.

WHAT THE HOST HEADER IS DOING HERE
----------------------------------
base_url is derived from the request rather than written into the file. An
earlier draft had the domain hardcoded, which meant any operator running it
would publish somebody else's domain as the source - the opposite of a mirror.
Deriving it means this file can be lifted to any domain and tells the truth
about wherever it is actually running.

EVERY PUBLISHED ENDPOINT MUST WORK AS WRITTEN
---------------------------------------------
An endpoint marked demonstrable_publicly is a promise that a stranger can copy
it out of this document and get an answer. If the route needs a parameter, the
document names that parameter. If a value has to be discovered first, the
document says where to discover it. An endpoint that errors when followed
literally is a failed check, not a documentation detail.

HONESTY RULES THIS FILE FOLLOWS
-------------------------------
  - A check we have not built says supported: false. It does not quietly go
    missing from the document.
  - A check that exists but needs an account says demonstrable_publicly:
    false, however much we would like the tick.
  - runner is null. A runner exists in draft, but the checks have not been
    jointly agreed with the other mirror, so publishing one as though it were
    a settled standard would claim something neither operator has earned yet.

None of that is modesty. A conformance document whose author scores full marks
on the day they publish it is a marketing page.
"""

import hashlib
import json
import sys

VERSION = "1.2"
ORDERING_TEST_VERSION = "0.1"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec"),
          ("GET", "document")}

# Several paths on purpose. /.well-known/ is where the standard says to look,
# but some platforms and static handlers reserve that prefix, so a plain root
# path is served as well. /x/standard/document goes through the normal router
# and cannot be intercepted by anything, which makes it the diagnostic.
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",
                   "/ordering-test.json",
                   "/well-known/ordering-test.json")

VENDOR = "AILeash"
FALLBACK_BASE = "https://sebbi.pro"

RUNNER = None
RUNNER_NOTE = (
    "No shared runner file is published here yet. The checks themselves have "
    "not been jointly agreed with the other mirrors as of this document's "
    "publication. This describes AILeash's own side only, not a settled "
    "cross-vendor standard.")

# Order follows the other mirror's document so the two read side by side.
CHECKS = {
    "rule_binding": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/rulebind/prove",
        "note": ("The ruleset version is a component of a digest sealed with the "
                 "decision, not a field beside it. POST any inputs without an "
                 "account and the response returns the exact string that was "
                 "hashed - SHA-256 it yourself and confirm it matches. Alter the "
                 "ruleset hash and the digest stops recomputing; alter the digest "
                 "and the chain breaks. Verify a past record at "
                 "/x/rulebind/verify?receipt=... and see ruleset history at "
                 "/x/rulebind/packs. No scoring logic is disclosed at any point - "
                 "inputs are published as a digest, never as values."),
    },
    "commit_before_reveal": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/demo/review",
        "note": ("The reviewer receives the case with the machine verdict "
                 "withheld. Their own call and dwell time are sealed first, "
                 "then the verdict is revealed, and the chain fixes that order "
                 "permanently. No account needed - open a case, commit a "
                 "verdict, and check the block indices yourself. Commit "
                 "endpoint is /x/demo/commit."),
    },
    "authority_tokens": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/continuity/decisions",
        "note": ("Authority is derived, not looked up. Every grant points at a "
                 "parent and terminates at a human principal; scope, limits, "
                 "purpose and validity must narrow at every hop; and the whole "
                 "chain is re-derived at the instant of execution rather than "
                 "trusted from the instant of issue. A decision beyond delegated "
                 "authority escalates rather than executes. Issuing and exercising "
                 "authority are keyed, but the record is not: /x/continuity/decisions "
                 "lists real sealed evaluations without an account, and any id from "
                 "it opens at /x/continuity/decision and /x/continuity/trace, which "
                 "returns the full authority path with the grant and invariant that "
                 "broke. Blocks are listed alongside allows, because a refusal with "
                 "no public record is indistinguishable from never having been asked. "
                 "An empty list means no authority has been exercised yet, not that "
                 "none failed. Derivation rules at /x/continuity/spec."),
    },
    "mutual_witnessing": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/witness/peers",
        "note": ("Live, running both directions with an external peer chain "
                 "hourly since 1 August 2026. No account needed, run it "
                 "yourself. Our current tip is at /x/witness/tip and any party "
                 "can submit theirs at /x/witness/observe without an account."),
    },
    "completeness_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/root?period={period}&kind=receipts",
        "note": ("Per-period sorted Merkle root and exact leaf count, committed "
                 "before any export is requested. An export can then be checked "
                 "against a number fixed before anyone knew it would be asked "
                 "for. Committed periods are listed at /x/complete/periods - "
                 "take a period identifier from there and substitute it. Only "
                 "closed periods can be committed, so the current period will "
                 "not appear until it ends. A period listed nowhere is a period "
                 "nobody committed, which is itself the finding."),
    },
    "absence_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/prove?period={period}&value={value}",
        "note": ("Two adjacent leaves with consecutive indices demonstrate that "
                 "nothing sits between them, so absence is proved rather than "
                 "asserted. Both parameters are required: take a period from "
                 "/x/complete/periods and supply any value you like. Try a "
                 "value that is not there."),
    },
    "reconciliation": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/reconcile/public",
        "note": ("The sample is derived from the chain tip and sealed BEFORE any "
                 "data is requested, so the operator cannot choose which records "
                 "get examined or prepare only the flattering ones. Planning and "
                 "submitting are keyed because they touch an operator's own "
                 "records, but the part that decides whether any of it means "
                 "anything is not: /x/reconcile/public gives run counts, match "
                 "rates and mismatches without an account, and "
                 "/x/reconcile/proof?id=RUN-XXXXXXXX shows the two sealed block "
                 "indices so anyone can confirm the selection block precedes the "
                 "result block. Abandoned runs are published too - a plan is "
                 "sealed when it is planned, so a test that came back badly and "
                 "was dropped stays visible forever as a plan with no result. "
                 "What this does not prove: that the records are true. Two "
                 "systems the operator controls agreeing with each other is "
                 "consistency, not truth."),
    },
    "reproducibility": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/replay/challenge",
        "note": ("Determinism proved by public challenge without disclosing any "
                 "scoring logic. Submit inputs, the run is sealed, resubmit the "
                 "same inputs later and the verdict must be identical under an "
                 "unchanged code fingerprint at /x/replay/fingerprint."),
    },
    "consistency_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/consistency/proof?first={first}&second={second}",
        "note": ("RFC 6962 consistency proofs, deliberately unmodified so "
                 "existing Certificate Transparency verifiers work against them "
                 "directly. first and second are tree sizes - read the current "
                 "size from /x/consistency/root and pick any earlier one. "
                 "Anyone holding any earlier tip we served can show it is a "
                 "prefix of the current log at /x/consistency/ancestor."),
    },

    # ---- proposed addition, flagged as a proposal rather than assumed ----
    "external_anchoring": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/api/anchor-status",
        "note": ("PROPOSED AS A SEPARATE CHECK, not settled. The other mirror "
                 "currently folds anchoring into consistency_proof, but they "
                 "answer different questions: consistency shows the log only "
                 "ever grew, anchoring shows the time was fixed somewhere the "
                 "operator cannot reach. A log can be perfectly append-only and "
                 "still have been built last week. Here the tip is submitted to "
                 "OpenTimestamps and committed into Bitcoin; the other mirror "
                 "uses an RFC 3161 timestamp. The spec should permit any "
                 "external authority the operator does not control and require "
                 "it to be named - not mandate one. Offered for the joint "
                 "session."),
    },
}

DOCUMENT_NOTE = (
    "Every endpoint marked demonstrable_publicly is unauthenticated by design - "
    "run it yourself without asking us. Where an endpoint carries a {parameter}, "
    "the note for that check says where to get a valid value; every published "
    "endpoint is meant to work when followed literally, and one that does not is "
    "a failed check on our side, not a quibble. Checks marked supported but not "
    "demonstrable_publicly are real and built, but currently need a key to see, "
    "and say so plainly rather than passing on the day this was published. "
    "Nothing here proves the records are true. It describes the order things "
    "were committed in, which is a narrower claim and the only one that holds.")

_patched = [False]


def _base_from(handler):
    """Derive our own base URL from the request. An operator running this file
    on their own domain publishes their domain, not whoever wrote it."""
    try:
        host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host")
        if not host:
            return FALLBACK_BASE
        host = host.split(",")[0].strip()[:200]
        proto = (handler.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return proto + "://" + host
    except Exception:
        return FALLBACK_BASE


def _base_from_ctx(ctx):
    """Same derivation for the routed /x/standard/document call.

    The router's ctx may or may not carry the request handler. If it does, the
    document served through the router names the same domain as the one served
    at /.well-known/ - which matters on a mirror, where hardcoding would make
    this file publish somebody else's domain again."""
    try:
        if isinstance(ctx, dict):
            for key in ("handler", "h", "request", "req", "self"):
                obj = ctx.get(key)
                if obj is not None and hasattr(obj, "headers"):
                    return _base_from(obj)
            headers = ctx.get("headers")
            if headers is not None:
                class _Shim(object):
                    pass
                shim = _Shim()
                shim.headers = headers
                return _base_from(shim)
        elif ctx is not None and hasattr(ctx, "headers"):
            return _base_from(ctx)
    except Exception:
        pass
    return FALLBACK_BASE


def _document(base):
    checks = {}
    for name, c in CHECKS.items():
        checks[name] = {
            "supported": c["supported"],
            "demonstrable_publicly": c["demonstrable_publicly"],
            "endpoint": c["endpoint"],
            "note": c["note"],
        }
    return {
        "ordering_test_version": ORDERING_TEST_VERSION,
        "vendor": VENDOR,
        "base_url": base,
        "runner": RUNNER,
        "runner_note": RUNNER_NOTE,
        "checks": checks,
        "witness_peers": base + "/x/witness/peers",
        "witness_tip": base + "/x/witness/tip",
        "committed_periods": base + "/x/complete/periods",
        "note": DOCUMENT_NOTE,
    }


def _digest(doc):
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in DISCOVERY_PATHS:
            body = json.dumps(_document(_base_from(self)), indent=2).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /.well-known/ordering-test.json installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    base = _base_from_ctx(ctx)
    doc = _document(base)

    if method == "GET" and action == "document":
        return doc, 200

    if method == "GET" and action == "hash":
        canonical = _document(FALLBACK_BASE)
        return {
            "sha256": _digest(canonical),
            "of": "this operator's discovery document",
            "canonicalisation": ("JSON, keys sorted, no whitespace, UTF-8, "
                                 "base_url fixed to " + FALLBACK_BASE +
                                 " so the digest does not move with the "
                                 "requesting host"),
            "what_this_is_for": (
                "Confirming our own document has not changed. It is NOT the "
                "cross-mirror check - two operators publish different documents "
                "by design, because they list different endpoints, so their "
                "digests should differ and a mismatch would prove nothing. The "
                "cross-mirror comparison only means something once every mirror "
                "serves a byte-identical runner file and hashes that instead. "
                "No runner is agreed yet."),
            "document": canonical,
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        supported = [k for k, c in CHECKS.items() if c["supported"]]
        public = [k for k, c in CHECKS.items() if c["demonstrable_publicly"]]
        parameterised = [k for k, c in CHECKS.items()
                         if c["endpoint"] and "{" in c["endpoint"]]
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "ordering_test_version": ORDERING_TEST_VERSION,
            "serving": list(DISCOVERY_PATHS),
            "always_available": "/x/standard/document",
            "checks_total": len(CHECKS),
            "checks_supported": len(supported),
            "checks_publicly_demonstrable": len(public),
            "publicly_demonstrable": public,
            "supported_but_not_public": [k for k in supported if k not in public],
            "endpoints_needing_a_parameter": parameterised,
            "runner": RUNNER,
            "note": ("base_url is derived from the Host header, so this file "
                     "publishes whichever domain is actually serving it. Checks "
                     "listed under endpoints_needing_a_parameter cannot be "
                     "demonstrated until a real value exists to substitute - "
                     "for the completeness and absence checks that means at "
                     "least one committed period at /x/complete/periods."),
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash", "document"]}, 404

```


## `modules/stats.py`

143 lines, 5540 bytes

```python
"""
Live figures for the Proving Ground - /x/stats

Charts on a compliance site are usually decoration. These are not, provided
they show something a visitor could otherwise only take on trust: that the
chain is genuinely growing, that decisions really are distributed across the
thresholds rather than hand-picked, and that people who click through a
review case behave exactly as the oversight argument predicts.

WHAT IS PUBLISHED, AND WHAT IS NOT
----------------------------------
Public and no key, because a figure nobody can see proves nothing.

Published: total chain height, hourly block counts, the verdict mix and score
distribution of PUBLIC DEMO decisions only, and dwell times from public review
cases.

Never published: anything scoped to a customer key. No customer verdict mix,
no customer volumes, no per-key anything. A visitor learns how the engine
behaves, not how any operator's business is going. That distinction is the
whole reason this endpoint can be open.

    GET /x/stats        everything below
    GET /x/stats/chain  chain height and hourly growth only
"""

import json, time
from datetime import datetime, timezone

VERSION = "1.0"
PUBLIC = {("GET", ""), ("GET", "stats"), ("GET", "chain")}

DEMO_KEY = "public_demo"


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _chain(ctx):
    t = time.time()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*),MIN(ts),MAX(ts) FROM audit_log").fetchone()
        recent = ctx["conn"].execute("SELECT ts FROM audit_log WHERE ts>? ORDER BY ts ASC", (t - 86400,)).fetchall()
    height = row[0] if row else 0
    buckets = [0] * 24
    for (ts,) in recent:
        h = int((t - ts) // 3600)
        if 0 <= h < 24:
            buckets[23 - h] += 1
    return {"height": height,
            "first_block": _iso(row[1] if row else None),
            "latest_block": _iso(row[2] if row else None),
            "last_24h": buckets,
            "blocks_last_24h": sum(buckets),
            "note": "Every block, from every source. The chain is one sequence."}


def _demo(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT result_json,ts FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (DEMO_KEY,)).fetchall()
    verdicts = {"ALLOW": 0, "CHALLENGE": 0, "BLOCK": 0}
    # ten buckets of 0.1 across the score range
    hist = [0] * 10
    scores = []
    for res, _ts in rows:
        try:
            r = json.loads(res)
        except Exception:
            continue
        d = r.get("decision")
        if d in verdicts:
            verdicts[d] += 1
            s = r.get("score")
            if isinstance(s, (int, float)):
                scores.append(s)
                b = min(int(float(s) * 10), 9)
                hist[b] += 1
    total = sum(verdicts.values())
    out = {"decisions": total, "verdicts": verdicts,
           "score_histogram": hist,
           "buckets": ["0.0-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5",
                       "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"],
           "thresholds": {"allow_below": 0.35, "block_at_or_above": 0.70}}
    if scores:
        scores.sort()
        out["median_score"] = round(scores[len(scores) // 2], 4)
    return out


def _oversight(ctx):
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT dwell,human_verdict,machine_verdict FROM demo_cases WHERE committed IS NOT NULL").fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"reviews": 0,
                "note": "Nobody has taken a review case yet."}
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    agreed = len([r for r in rows if (r[1] or "").upper() == (r[2] or "").upper()])
    # dwell buckets in seconds
    edges = [2, 5, 10, 20, 45, 90]
    labels = ["under 2s", "2-5s", "5-10s", "10-20s", "20-45s", "45-90s", "over 90s"]
    hist = [0] * 7
    for d in dwells:
        placed = False
        for i, e in enumerate(edges):
            if d < e:
                hist[i] += 1
                placed = True
                break
        if not placed:
            hist[6] += 1
    n = len(dwells)
    return {"reviews": len(rows),
            "agreed_with_engine": agreed,
            "agreement_rate_pct": round(100 * agreed / len(rows), 1),
            "median_dwell_seconds": (dwells[n // 2] if n else None),
            "under_2_seconds": hist[0],
            "under_2_seconds_pct": (round(100 * hist[0] / n, 1) if n else 0),
            "dwell_histogram": hist,
            "dwell_labels": labels,
            "note": "Visitors who committed in under two seconds did not read the case. That is the pattern the oversight record is designed to make visible."}


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404
    if action == "chain":
        return {"stats_version": VERSION, "chain": _chain(ctx)}, 200
    if action in ("", "stats"):
        return {"stats_version": VERSION,
                "generated": _iso(time.time()),
                "chain": _chain(ctx),
                "public_decisions": _demo(ctx),
                "public_reviews": _oversight(ctx),
                "scope": "Public demonstration activity and total chain height only. Nothing scoped to a customer key is published here."}, 200
    return {"error": "unknown_action", "action": action,
            "available": ["GET stats", "GET chain"]}, 404

```
