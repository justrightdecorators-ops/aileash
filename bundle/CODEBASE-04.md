# Codebase — part 4 of 19

Contains:
- `modules/console.py`
- `modules/counterfactual.py`
- `modules/declare.py`
- `modules/demo.py`
- `modules/dsr.py`


## `modules/console.py`

910 lines, 38938 bytes

```python
"""
modules/console.py  -  the operator console at /console

WHY IT EXISTS
-------------
Half the useful routes are keyed POSTs. A browser address bar can only issue
GETs without a header, so from a phone those routes are unreachable - which is
most of the time, for this operator.

This serves one page that can reach them. The key is typed in, held in a
variable for that tab, and never written to storage. Close the tab and it is
gone.

WHAT IT CAN DO
--------------
  continuity/issue       grant authority, and delegate it onward
  continuity/exercise    evaluate an action against the whole lineage
  reconcile/plan         fix the sample before any data is requested
  reconcile/submit       seal the comparison, mismatches included
  fingerprint/self       score the 28-vector battery on our own engine
  fingerprint/probe      fire it at somebody else's endpoint and compare
  fingerprint/history    past comparisons
  codebase/seal          hash the tree, seal the manifest with a declaration
  publish/seal           seal the exact bytes a live page is serving

SAME PATCH AS network.py
------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime, adds one path, and
leaves every other path alone. Idempotent, in memory, reverts on restart.

And the same catch: after every deploy, one /x/ request has to arrive before
/console exists. Opening /x/console/status does it.

NOT LINKED FROM ANYWHERE
------------------------
No link on the site, noindex on the page. It holds no secrets - every route it
calls checks the key itself - but there is no reason to advertise it either.
"""

import sys

VERSION = "1.1"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/console", "/console.html")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Console — AILeash</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0f1e; --panel:#131b2e; --panel2:#1a2338; --edge:rgba(201,168,76,.22);
  --gold:#c9a84c; --gold-dim:#8a7233;
  --text:#f2efe6; --mute:rgba(242,239,230,.42);
  --allow:#1a9e6e; --challenge:#c07a1d; --block:#c8362b; --ok:#7fe3b0;
  --disp:Fraunces,Georgia,serif; --body:'Space Grotesk',system-ui,sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
body{background:var(--ink);color:var(--text);font-family:var(--body);
  font-size:16px;line-height:1.6;padding:0 0 60px;
  background-image:repeating-linear-gradient(90deg,transparent 0 39px,rgba(201,168,76,.05) 39px 40px)}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}

header{padding:34px 0 22px;border-bottom:1px solid var(--edge);margin-bottom:26px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
h1{font-family:var(--disp);font-weight:900;font-size:clamp(30px,8vw,44px);
  line-height:1;letter-spacing:-.02em}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14.5px;margin-top:12px;max-width:44ch}

label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--mute);margin-bottom:7px}
input,textarea{width:100%;background:var(--panel);border:1px solid var(--edge);
  color:var(--text);font-family:var(--mono);font-size:13px;padding:12px 13px;
  border-radius:4px;outline:none}
input:focus,textarea:focus{border-color:var(--gold)}
textarea{resize:vertical;min-height:70px;font-family:var(--body);font-size:14px}

.keybar{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
  padding:16px;margin-bottom:26px}
.keynote{font-size:12px;color:var(--mute);margin-top:9px;line-height:1.55}

.op{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
  margin-bottom:14px;overflow:hidden}
.op-head{display:flex;align-items:baseline;gap:10px;padding:15px 16px;cursor:pointer;
  user-select:none}
.op-head:hover{background:var(--panel2)}
.op-n{font-family:var(--mono);font-size:10px;color:var(--gold-dim);letter-spacing:.1em}
.op-t{font-family:var(--disp);font-weight:600;font-size:18px;letter-spacing:-.01em}
.op-r{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--mute)}
.op-body{padding:0 16px 16px;display:none}
.op.open .op-body{display:block}
.op-why{font-size:13.5px;color:var(--mute);margin-bottom:14px;line-height:1.6}
.field{margin-bottom:12px}

button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;
  padding:14px;font-family:var(--body);font-weight:700;font-size:14.5px;cursor:pointer;
  transition:background .15s}
button:hover:not(:disabled){background:#dbbd63}
button:disabled{opacity:.45;cursor:default}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--edge)}
button.quiet:hover:not(:disabled){color:var(--text);border-color:var(--gold)}

/* ---- the readout: this is the thing worth building ---- */
#out{margin-top:26px}
.verdict{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
  overflow:hidden;margin-bottom:14px}
.v-head{padding:22px 18px;border-bottom:1px solid var(--edge)}
.v-word{font-family:var(--disp);font-weight:900;font-size:clamp(28px,9vw,42px);
  line-height:1;letter-spacing:-.02em}
.v-IDENTICAL,.v-err{color:var(--block)}
.v-DERIVED{color:var(--challenge)}
.v-SAME.SHAPE,.v-SIMILAR{color:var(--gold)}
.v-UNRELATED,.v-ok{color:var(--allow)}
.v-INCONCLUSIVE{color:var(--mute)}
.v-ALLOW{color:var(--allow)}
.v-CHALLENGE{color:var(--challenge)}
.v-BLOCK{color:var(--block)}
.lin{padding:16px 18px;border-bottom:1px solid var(--edge)}
.lin-hop{display:flex;gap:10px;align-items:baseline;padding:8px 0;
  border-bottom:1px solid rgba(201,168,76,.10)}
.lin-hop:last-child{border-bottom:none}
.lin-d{font-family:var(--mono);font-size:10px;color:var(--gold-dim);min-width:24px}
.lin-g{font-family:var(--mono);font-size:12px;color:var(--gold)}
.lin-s{font-size:12.5px;color:var(--mute)}
.lin-bad{color:var(--block)}
.v-stats{display:flex;flex-wrap:wrap;gap:18px;padding:14px 18px;
  border-bottom:1px solid var(--edge);font-family:var(--mono);font-size:11px}
.v-stats b{display:block;font-family:var(--disp);font-size:19px;color:var(--text);
  font-weight:600;margin-top:3px}
.v-stats span{color:var(--mute);letter-spacing:.1em;text-transform:uppercase}

/* paired bars: ours above, theirs below, one column per vector */
.strip{padding:18px}
.strip-l{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
.bars{display:flex;gap:2px;align-items:stretch;height:96px}
.bar{flex:1;display:flex;flex-direction:column;justify-content:center;gap:2px;min-width:0}
.bar i{display:block;border-radius:1px;transition:height .35s ease}
.bar .mine{background:var(--gold);align-self:flex-end;width:100%}
.bar .theirs{background:rgba(242,239,230,.35);width:100%}
.bar.match .theirs{background:var(--block)}
.bar-key{display:flex;gap:16px;margin-top:12px;font-family:var(--mono);font-size:10px;
  color:var(--mute);flex-wrap:wrap}
.dot{display:inline-block;width:8px;height:8px;border-radius:1px;margin-right:6px;
  vertical-align:middle}

pre{font-family:var(--mono);font-size:11.5px;line-height:1.65;background:#080c16;
  color:var(--ok);padding:15px;border-radius:5px;overflow-x:auto;
  border:1px solid var(--edge);max-height:340px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;border-radius:5px;
  border:1px solid var(--edge);color:var(--mute);margin-bottom:14px}
.msg.bad{color:#ffb4ad;border-color:rgba(200,54,43,.5);background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);background:rgba(26,158,110,.08)}
.working{font-family:var(--mono);font-size:12px;color:var(--gold)}
.working:after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
footer{margin-top:34px;padding-top:18px;border-top:1px solid var(--edge);
  font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash · operator console</p>
  <h1>Keyed <span>routes</span></h1>
  <p class="sub">The endpoints a browser cannot reach on its own. Your key stays in this tab and is never stored.</p>
</header>

<div class="keybar">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_…" autocomplete="off" spellcheck="false">
  <p class="keynote">Held in memory for this tab only. Close it and the key is gone — nothing is written to the device.</p>
</div>

<div class="op" id="op-self">
  <div class="op-head" onclick="toggle('op-self')">
    <span class="op-n">01</span><span class="op-t">Baseline</span>
    <span class="op-r">POST /x/fingerprint/self</span>
  </div>
  <div class="op-body">
    <p class="op-why">Runs the 28-vector battery through your own engine. Every probe is measured against this. Run it first — if it answers, the module can see your live scorer.</p>
    <button onclick="run('self')">Score the battery</button>
  </div>
</div>

<div class="op" id="op-probe">
  <div class="op-head" onclick="toggle('op-probe')">
    <span class="op-n">02</span><span class="op-t">Probe a target</span>
    <span class="op-r">POST /x/fingerprint/probe</span>
  </div>
  <div class="op-body">
    <p class="op-why">Fires the same battery at somebody else's scoring endpoint and compares the two sets of numbers. One request per vector with a gap between them.</p>
    <div class="field">
      <label for="t-url">Their scoring endpoint</label>
      <input id="t-url" type="url" placeholder="https://example.com/api/score" autocomplete="off">
    </div>
    <div class="field">
      <label for="t-fields">Field names, if theirs differ (optional)</label>
      <input id="t-fields" placeholder='{"amount":"value","trust":"history"}' autocomplete="off">
    </div>
    <div class="field">
      <label for="t-score">Where the score is in their reply (optional)</label>
      <input id="t-score" placeholder="risk_score" autocomplete="off">
    </div>
    <button onclick="run('probe')">Run the comparison</button>
  </div>
</div>

<div class="op" id="op-code">
  <div class="op-head" onclick="toggle('op-code')">
    <span class="op-n">03</span><span class="op-t">Seal the codebase</span>
    <span class="op-r">POST /x/codebase/seal</span>
  </div>
  <div class="op-body">
    <p class="op-why">Hashes every file, commits one manifest root, seals it with your declaration. Dated evidence of what you held and when.</p>
    <div class="field">
      <label for="c-author">Author</label>
      <input id="c-author" value="Justin Antony Dobson" autocomplete="off">
    </div>
    <div class="field">
      <label for="c-entity">Entity</label>
      <input id="c-entity" value="Monop Content" autocomplete="off">
    </div>
    <div class="field">
      <label for="c-stmt">Declaration</label>
      <textarea id="c-stmt">Scoring engine, weighting and trust decay authored solely by me.</textarea>
    </div>
    <button onclick="run('codebase')">Seal it</button>
  </div>
</div>

<div class="op" id="op-pub">
  <div class="op-head" onclick="toggle('op-pub')">
    <span class="op-n">04</span><span class="op-t">Seal a published page</span>
    <span class="op-r">POST /x/publish/seal</span>
  </div>
  <div class="op-body">
    <p class="op-why">Fetches a live page and seals the exact bytes served. Pins what the world could see on a given date, which is not the same as what was in the repo.</p>
    <div class="field">
      <label for="p-url">Page</label>
      <input id="p-url" type="url" value="https://sebbi.pro/" autocomplete="off">
    </div>
    <button onclick="run('publish')">Seal the page</button>
  </div>
</div>

<div class="op" id="op-hist">
  <div class="op-head" onclick="toggle('op-hist')">
    <span class="op-n">05</span><span class="op-t">Past probes</span>
    <span class="op-r">GET /x/fingerprint/history</span>
  </div>
  <div class="op-body">
    <p class="op-why">Every comparison you have run, with its verdict and receipt.</p>
    <button class="quiet" onclick="run('history')">Show them</button>
  </div>
</div>

<div class="op" id="op-spec">
  <div class="op-head" onclick="toggle('op-spec')">
    <span class="op-n">06</span><span class="op-t">Every command</span>
    <span class="op-r">GET /x/spec</span>
  </div>
  <div class="op-body">
    <p class="op-why">Walks every module on the router and reports what each one exposes, and which routes need a key. If you have forgotten what exists, this is the answer.</p>
    <button class="quiet" onclick="run('spec')">List them</button>
  </div>
</div>


<div class="op" id="op-auth">
  <div class="op-head" onclick="toggle('op-auth')">
    <span class="op-n">07</span><span class="op-t">Grant authority</span>
    <span class="op-r">POST /x/continuity/issue</span>
  </div>
  <div class="op-body">
    <p class="op-why">A root grant. It must be issued by a human, it must state a purpose, and it must expire. Whoever is named as accepting the risk is the person an incident lands on.</p>
    <div class="field">
      <label for="a-issuer">Issued by (human)</label>
      <input id="a-issuer" value="justin@monopcontent.com" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-subject">Granted to</label>
      <input id="a-subject" value="orchestrator" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-scope">Scope, comma separated</label>
      <input id="a-scope" value="payments.refund, payments.read" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-max">Maximum amount</label>
      <input id="a-max" value="5000" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-purpose">Purpose</label>
      <input id="a-purpose" value="resolve customer refund complaints" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-tags">Purpose tags, comma separated</label>
      <input id="a-tags" value="refunds, support" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-hours">Valid for (hours)</label>
      <input id="a-hours" value="24" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-deleg">Onward delegations allowed</label>
      <input id="a-deleg" value="2" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-risk">Risk accepted by (leave blank to use the issuer)</label>
      <input id="a-risk" placeholder="risk.officer@example.com" autocomplete="off">
    </div>
    <button onclick="run('issue')">Issue the grant</button>
  </div>
</div>

<div class="op" id="op-deleg">
  <div class="op-head" onclick="toggle('op-deleg')">
    <span class="op-n">08</span><span class="op-t">Delegate it onward</span>
    <span class="op-r">POST /x/continuity/issue</span>
  </div>
  <div class="op-body">
    <p class="op-why">A child can narrow, never widen. Try raising the amount above the parent's and watch it refuse. A child that can delegate again must name its own risk acceptor.</p>
    <div class="field">
      <label for="d-parent">Parent grant id</label>
      <input id="d-parent" placeholder="g_…" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-issuer">Issued by</label>
      <input id="d-issuer" value="orchestrator" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-subject">Granted to</label>
      <input id="d-subject" value="refund-agent" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-scope">Scope, comma separated</label>
      <input id="d-scope" value="payments.refund" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-max">Maximum amount</label>
      <input id="d-max" value="200" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-purpose">Purpose</label>
      <input id="d-purpose" value="issue small refunds" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-tags">Purpose tags</label>
      <input id="d-tags" value="refunds" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-hours">Valid for (hours, must fit inside the parent)</label>
      <input id="d-hours" value="6" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-deleg">Onward delegations allowed</label>
      <input id="d-deleg" value="0" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-risk">Risk accepted by (required if delegations above is not 0)</label>
      <input id="d-risk" placeholder="head.of.ops@example.com" autocomplete="off">
    </div>
    <button onclick="run('delegate')">Delegate</button>
  </div>
</div>

<div class="op" id="op-ex">
  <div class="op-head" onclick="toggle('op-ex')">
    <span class="op-n">09</span><span class="op-t">Exercise authority</span>
    <span class="op-r">POST /x/continuity/exercise</span>
  </div>
  <div class="op-body">
    <p class="op-why">The whole chain is re-derived at this moment, not trusted from when it was issued. Ask for more than the lineage allows and it names the grant and the invariant that broke.</p>
    <div class="field">
      <label for="e-grant">Grant id</label>
      <input id="e-grant" placeholder="g_…" autocomplete="off">
    </div>
    <div class="field">
      <label for="e-action">Action</label>
      <input id="e-action" value="payments.refund" autocomplete="off">
    </div>
    <div class="field">
      <label for="e-params">Parameters</label>
      <input id="e-params" value='{"amount": 150}' autocomplete="off">
    </div>
    <div class="field">
      <label for="e-tag">Declared purpose tag</label>
      <input id="e-tag" value="refunds" autocomplete="off">
    </div>
    <button onclick="run('exercise')">Evaluate it</button>
  </div>
</div>

<div class="op" id="op-plan">
  <div class="op-head" onclick="toggle('op-plan')">
    <span class="op-n">10</span><span class="op-t">Plan a reconciliation</span>
    <span class="op-r">POST /x/reconcile/plan</span>
  </div>
  <div class="op-body">
    <p class="op-why">Seals which records will be tested before any data is fetched. Once this runs you cannot choose a kinder sample, and an abandoned plan stays visible forever.</p>
    <div class="field">
      <label for="r-size">Sample size</label>
      <input id="r-size" value="10" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-field">Field to reconcile</label>
      <input id="r-field" value="decision" autocomplete="off">
    </div>
    <button onclick="run('plan')">Fix the sample</button>
  </div>
</div>

<div class="op" id="op-sub">
  <div class="op-head" onclick="toggle('op-sub')">
    <span class="op-n">11</span><span class="op-t">Submit the comparison</span>
    <span class="op-r">POST /x/reconcile/submit</span>
  </div>
  <div class="op-body">
    <p class="op-why">The values from your own live system, against the sample that was already sealed. Fill these honestly - a mismatch is sealed as permanently as a match, and that is the only reason any of it means anything.</p>
    <div class="field">
      <label for="s-run">Run id</label>
      <input id="s-run" placeholder="RUN-XXXXXXXX" autocomplete="off">
    </div>
    <div class="field">
      <label for="s-results">Results, block index to live value</label>
      <textarea id="s-results" placeholder='{"41": "ALLOW", "58": "BLOCK"}'></textarea>
    </div>
    <button onclick="run('submit')">Seal the comparison</button>
  </div>
</div>

<div id="out"></div>

<footer>
  Public routes need no key and are not listed here.<br>
  Chain: <a href="/api/verify-chain">/api/verify-chain</a> · Clock: <a href="/api/anchor-status">/api/anchor-status</a> · Network: <a href="/x/witness/peers">/x/witness/peers</a>
</footer>

</div>

<script>
(function(){
  var out = document.getElementById('out');
  var busy = false;

  window.toggle = function(id){
    var el = document.getElementById(id);
    el.classList.toggle('open');
  };
  document.getElementById('op-self').classList.add('open');

  function esc(s){
    return String(s==null?'':s).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
  }
  function msg(text, kind){
    out.innerHTML = '<div class="msg '+(kind||'')+'">'+esc(text)+'</div>';
  }
  function raw(obj){
    return '<pre>'+esc(JSON.stringify(obj,null,2))+'</pre>';
  }

  function key(){
    var k = document.getElementById('key').value.trim();
    if(!k){ msg('Paste your API key at the top first.','bad'); return null; }
    return k;
  }

  function parseJSONField(id){
    var v = document.getElementById(id).value.trim();
    if(!v) return null;
    try { return JSON.parse(v); }
    catch(e){ msg('That field-name map is not valid JSON. Example: {"amount":"value"}','bad'); return undefined; }
  }

  async function call(path, method, body){
    var k = key(); if(!k) return null;
    var opts = { method: method, headers: { 'Authorization':'Bearer '+k } };
    if(body){ opts.headers['Content-Type']='application/json'; opts.body=JSON.stringify(body); }
    var r = await fetch(path, opts);
    var d;
    try { d = await r.json(); } catch(e){ d = {error:'unreadable_response'}; }
    return { status: r.status, data: d };
  }

  function bars(perVector){
    var maxV = 0;
    perVector.forEach(function(p){
      maxV = Math.max(maxV, Math.abs(p.ours), Math.abs(p.theirs)); });
    if(maxV <= 0) maxV = 1;
    var html = '<div class="strip"><div class="strip-l">Every vector · yours above, theirs below</div><div class="bars">';
    perVector.forEach(function(p){
      var a = Math.max(2, Math.round((Math.abs(p.ours)/maxV)*44));
      var b = Math.max(2, Math.round((Math.abs(p.theirs)/maxV)*44));
      var match = Math.abs(p.delta) < 0.000001 ? ' match' : '';
      html += '<div class="bar'+match+'" title="'+esc(p.vector)+': '+p.ours+' vs '+p.theirs+'">'
           +  '<i class="mine" style="height:'+a+'px"></i>'
           +  '<i class="theirs" style="height:'+b+'px"></i></div>';
    });
    html += '</div><div class="bar-key">'
         +  '<span><i class="dot" style="background:var(--gold)"></i>yours</span>'
         +  '<span><i class="dot" style="background:var(--block)"></i>theirs, exact match</span>'
         +  '<span><i class="dot" style="background:rgba(242,239,230,.35)"></i>theirs, different</span>'
         +  '</div></div>';
    return html;
  }

  function csv(id){
    return document.getElementById(id).value.split(',')
      .map(function(x){ return x.trim(); }).filter(Boolean);
  }
  function num(id){
    var v = parseFloat(document.getElementById(id).value.trim());
    return isNaN(v) ? 0 : v;
  }
  function val(id){ return document.getElementById(id).value.trim(); }

  function renderGrant(d){
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">GRANTED</div>'
      + '<div class="v-why">Sealed at block ' + esc(d.block_index)
      + '. Depth ' + esc(d.depth) + '. Risk accepted by '
      + esc(d.risk_accepted_by || 'inherited from above') + '.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>grant</span><b style="font-family:var(--mono);font-size:12px">'
      + esc(d.grant) + '</b></div>'
      + '<div><span>expires</span><b style="font-size:13px">'
      + esc(String(d.not_after || '').slice(0,16)) + '</b></div>'
      + '</div></div>';
    // carry the id forward so the next step does not need copying by hand
    if(d.grant){
      var dp = document.getElementById('d-parent');
      var eg = document.getElementById('e-grant');
      if(dp && !dp.value) dp.value = d.grant;
      if(eg) eg.value = d.grant;
    }
    return html;
  }

  function renderExercise(d){
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-' + esc(d.verdict) + '">' + esc(d.verdict) + '</div>'
      + '<div class="v-why">' + esc(d.what_this_means || '') + '</div></div>'
      + '<div class="v-stats">'
      + '<div><span>authorised by</span><b style="font-size:13px">' + esc(d.authorised_by) + '</b></div>'
      + '<div><span>executed by</span><b style="font-size:13px">' + esc(d.executed_by) + '</b></div>'
      + '<div><span>risk accepted by</span><b style="font-size:13px">' + esc(d.risk_accepted_by) + '</b></div>'
      + '<div><span>hops</span><b>' + esc(d.delegation_depth) + '</b></div>'
      + '</div>';
    if(d.lineage && d.lineage.length){
      html += '<div class="lin"><div class="strip-l">Authority path, root first</div>';
      d.lineage.forEach(function(h){
        var bad = (h.integrity !== 'ok' || h.revoked) ? ' lin-bad' : '';
        html += '<div class="lin-hop"><span class="lin-d">' + esc(h.depth) + '</span>'
             +  '<span><span class="lin-g' + bad + '">' + esc(h.grant) + '</span>'
             +  '<div class="lin-s">' + esc(h.issuer) + ' &rarr; ' + esc(h.subject)
             +  ' · ' + esc((h.scope || []).join(', ')) + '</div></span></div>';
      });
      html += '</div>';
    }
    if(d.reasons && d.reasons.length){
      html += '<div class="lin"><div class="strip-l">'
           + (d.verdict === 'BLOCK' ? 'What broke' : 'What could not be settled')
           + '</div>';
      d.reasons.forEach(function(r){
        html += '<div class="lin-s" style="padding:5px 0">' + esc(r) + '</div>'; });
      if(d.broken_at){
        html += '<div class="lin-s" style="padding-top:8px;color:var(--block)">at grant '
             + esc(d.broken_at) + ' · ' + esc(d.broken_invariant) + '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderPlan(d){
    // prefill the submit form with the sealed sample so the next step is typing
    // values, not transcribing block numbers
    var skeleton = {};
    (d.sample || []).forEach(function(s){ skeleton[String(s.block_index)] = ''; });
    var sr = document.getElementById('s-run');
    var ss = document.getElementById('s-results');
    if(sr) sr.value = d.run_id;
    if(ss) ss.value = JSON.stringify(skeleton, null, 1);
    document.getElementById('op-sub').classList.add('open');
    return '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">SAMPLE FIXED</div>'
      + '<div class="v-why">' + esc(d.sample_size) + ' records selected from the chain tip and '
      + 'sealed at block ' + esc(d.block_index) + ', before any data was requested. '
      + 'The submit form below has been filled with the block indices.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>run</span><b style="font-family:var(--mono);font-size:12px">'
      + esc(d.run_id) + '</b></div>'
      + '<div><span>field</span><b style="font-size:13px">' + esc(d.field) + '</b></div>'
      + '</div></div>';
  }

  function renderSubmit(d){
    var clean = (d.mismatched === 0 && d.missing === 0);
    return '<div class="verdict"><div class="v-head">'
      + '<div class="v-word ' + (clean ? 'v-ok' : 'v-BLOCK') + '">'
      + esc(d.match_rate_pct) + '%</div>'
      + '<div class="v-why">Sealed at block ' + esc(d.block_index)
      + ' whichever way it went. It cannot be withdrawn.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>matched</span><b>' + esc(d.matched) + '</b></div>'
      + '<div><span>mismatched</span><b>' + esc(d.mismatched) + '</b></div>'
      + '<div><span>missing</span><b>' + esc(d.missing) + '</b></div>'
      + '</div></div>';
  }

  function renderProbe(d){
    var v = String(d.verdict||'').replace(/ /g,'.');
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-'+esc(v)+'">'+esc(d.verdict)+'</div>'
      + '<div class="v-why">'+esc(d.why||'')+'</div></div>'
      + '<div class="v-stats">'
      +   '<div><span>exact</span><b>'+esc(d.exact_matches)+'/'+esc(d.answered)+'</b></div>'
      +   '<div><span>correlation</span><b>'+esc(d.correlation==null?'—':d.correlation)+'</b></div>'
      +   '<div><span>same order</span><b>'+esc(d.rank_correlation==null?'—':d.rank_correlation)+'</b></div>'
      + '</div>';
    if(d.per_vector && d.per_vector.length) html += bars(d.per_vector);
    html += '</div>';
    if(d.sealed) html += '<div class="msg good">Sealed at block '+esc(d.sealed.block_index)
      + ' · receipt '+esc(String(d.sealed.receipt).slice(0,20))+'…</div>';
    if(d.failures) html += '<div class="msg bad">'+esc(d.failure_note||'Some vectors were rejected.')+'</div>';
    html += raw(d);
    out.innerHTML = html;
  }

  function renderSpec(d){
    // the shape varies by version, so find the module list wherever it is
    var mods = d.modules || d.spec || d;
    var names = [];
    if(Array.isArray(mods)){
      mods.forEach(function(m){
        names.push(typeof m === 'string' ? {name:m} : m); });
    } else if(mods && typeof mods === 'object'){
      Object.keys(mods).forEach(function(k){
        var v = mods[k];
        names.push({name:k, detail:(v && typeof v === 'object') ? v : null}); });
    }
    if(!names.length) return '<div class="msg">Nothing listed. The raw reply is below.</div>';

    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">' + names.length + ' modules</div>'
      + '<div class="v-why">Everything currently loaded on the router.</div></div>'
      + '<div class="strip">';
    names.forEach(function(m){
      var routes = '';
      if(m.detail){
        ['public','keyed','GET','POST','routes','actions'].forEach(function(k){
          var v = m.detail[k];
          if(Array.isArray(v) && v.length){
            routes += '<div style="color:var(--mute);font-size:11.5px;margin-top:3px">'
                   + esc(k) + ': ' + esc(v.join(', ')) + '</div>';
          }
        });
      }
      html += '<div style="padding:11px 0;border-bottom:1px solid var(--edge)">'
           +  '<span style="font-family:var(--mono);font-size:13px;color:var(--gold)">/x/'
           +  esc(m.name) + '/</span>' + routes + '</div>';
    });
    html += '</div></div>';
    return html;
  }

  window.run = async function(what){
    if(busy) return;
    var path, method='POST', body=null;

    if(what==='self'){ path='/x/fingerprint/self'; body={}; }

    else if(what==='probe'){
      var url = document.getElementById('t-url').value.trim();
      if(!url){ msg('Give the endpoint you want compared.','bad'); return; }
      var fields = parseJSONField('t-fields');
      if(fields === undefined) return;
      body = { url: url };
      if(fields) body.fields = fields;
      var sk = document.getElementById('t-score').value.trim();
      if(sk) body.score_key = sk;
      path='/x/fingerprint/probe';
    }

    else if(what==='codebase'){
      path='/x/codebase/seal';
      body = { author: document.getElementById('c-author').value.trim(),
               entity: document.getElementById('c-entity').value.trim(),
               statement: document.getElementById('c-stmt').value.trim() };
    }

    else if(what==='publish'){
      var pu = document.getElementById('p-url').value.trim();
      if(!pu){ msg('Give the page to seal.','bad'); return; }
      path='/x/publish/seal'; body={ url: pu };
    }

    else if(what==='issue' || what==='delegate'){
      var pre = (what === 'issue') ? 'a-' : 'd-';
      var hours = num(pre + 'hours') || 1;
      body = {
        issuer: val(pre + 'issuer'),
        issuer_kind: (what === 'issue') ? 'human' : 'agent',
        subject: val(pre + 'subject'),
        scope: csv(pre + 'scope'),
        constraints: { max_amount: num(pre + 'max') },
        purpose: val(pre + 'purpose'),
        purpose_tags: csv(pre + 'tags'),
        not_after: Math.floor(Date.now() / 1000) + Math.round(hours * 3600),
        delegations_left: Math.round(num(pre + 'deleg'))
      };
      var risk = val(pre + 'risk');
      if(risk) body.risk_accepted_by = risk;
      if(what === 'delegate'){
        var par = val('d-parent');
        if(!par){ msg('Give the parent grant id. Issue a root first if you have none.','bad'); return; }
        body.parent = par;
        // a child window must sit inside the parent's, so start it now
        body.not_before = Math.floor(Date.now() / 1000);
      }
      path = '/x/continuity/issue';
    }

    else if(what==='exercise'){
      var g = val('e-grant');
      if(!g){ msg('Give the grant id you are exercising.','bad'); return; }
      var params = {};
      var praw = val('e-params');
      if(praw){
        try { params = JSON.parse(praw); }
        catch(e){ msg('Parameters must be JSON. Example: {"amount": 150}','bad'); return; }
      }
      body = { grant: g, action: val('e-action'), params: params };
      var tag = val('e-tag');
      if(tag) body.purpose_tag = tag;
      path = '/x/continuity/exercise';
    }

    else if(what==='plan'){
      body = { sample_size: Math.round(num('r-size')) || 10, field: val('r-field') || 'decision' };
      path = '/x/reconcile/plan';
    }

    else if(what==='submit'){
      var rid = val('s-run');
      if(!rid){ msg('Give the run id from the plan step.','bad'); return; }
      var results;
      try { results = JSON.parse(val('s-results')); }
      catch(e){ msg('Results must be JSON: {"block index": "live value"}','bad'); return; }
      var empties = Object.keys(results).filter(function(k){
        return String(results[k]).trim() === ''; });
      if(empties.length){
        msg('Fill every value first — ' + empties.length + ' left blank. A blank is not a '
            + 'match, it is a missing record, and it will be sealed as one.','bad');
        return;
      }
      body = { run_id: rid, results: results };
      path = '/x/reconcile/submit';
    }

    else if(what==='history'){ path='/x/fingerprint/history'; method='GET'; }

    else if(what==='spec'){ path='/x/spec'; method='GET'; }

    else return;

    busy = true;
    out.innerHTML = '<div class="msg"><span class="working">'
      + (what==='probe' ? 'Firing 28 vectors, one at a time' : 'Working') + '</span></div>';

    try{
      var res = await call(path, method, body);
      if(!res){ busy=false; return; }

      if(res.status === 401){
        msg('That key was refused. Check it and try again.','bad');
      } else if(res.status === 404 && res.data && res.data.error === 'unknown_module'){
        msg('That module is not deployed yet.','bad');
      } else if(res.status === 429){
        msg('Rate limited. Give it a minute.','bad');
      } else if(res.status >= 400){
        out.innerHTML = '<div class="msg bad">'
          + esc((res.data && (res.data.message || res.data.error)) || ('HTTP '+res.status))
          + '</div>' + raw(res.data);
      } else if(what === 'probe' && res.data.verdict){
        renderProbe(res.data);
      } else if(what === 'self' && res.data.scores){
        out.innerHTML = '<div class="msg good">Baseline read from '
          + esc(res.data.source) + ' · ' + esc(res.data.vectors) + ' vectors</div>' + raw(res.data);
      } else if((what === 'issue' || what === 'delegate') && res.data.grant){
        out.innerHTML = renderGrant(res.data) + raw(res.data);
      } else if(what === 'exercise' && res.data.verdict){
        out.innerHTML = renderExercise(res.data) + raw(res.data);
      } else if(what === 'plan' && res.data.run_id){
        out.innerHTML = renderPlan(res.data) + raw(res.data);
      } else if(what === 'submit' && res.data.match_rate_pct !== undefined){
        out.innerHTML = renderSubmit(res.data) + raw(res.data);
      } else if(what === 'spec'){
        out.innerHTML = renderSpec(res.data) + raw(res.data);
      } else {
        out.innerHTML = '<div class="msg good">Done.</div>' + raw(res.data);
      }
    } catch(e){
      msg('Could not reach the server. That is a real failure, not a staged one.','bad');
    }
    busy = false;
  };
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
    if getattr(H, "_console_patched", False):
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
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._console_patched = True
    _patched[0] = True
    print("CONSOLE: /console page installed at runtime", flush=True)
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
            print("CONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/console",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "note": ("The page holds no credentials. Every route it calls checks "
                     "the key itself."),
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/counterfactual.py`

397 lines, 16121 bytes

```python
"""
Counterfactual explanation - /x/counterfactual/<action>

WHAT THIS IS
------------
Every governance vendor claims explainability. What they nearly all mean is
attribution: a list of which factors pushed the score up. That answers "why
did this happen" and leaves the only question anyone actually cares about
untouched - "what would have had to be different?"

That second question is the one a person contesting a decision needs, the
one Article 22 recourse turns on, and the one an ML-based system genuinely
cannot answer. A neural model is not invertible: you can attribute, you can
approximate with a sampling method, you cannot state the exact boundary.

This engine is arithmetic with published weights. Arithmetic runs backwards.
So for any sealed decision, the exact minimum change in every single factor
that would have produced a different verdict can be computed, stated, and
sealed - and anyone can re-derive it independently.

THE SCORING FUNCTION, RUN BACKWARDS
-----------------------------------
    score = (1 - trust)              x 0.30
          + min(v60/20, 1)           x 0.15
          + min(v5m/50, 1)           x 0.10
          + min(v1h/200, 1)          x 0.10
          + min(ln(1+amt)/ln(10001), 1) x 0.15
          + device_risk              x 0.10
          + anomaly                  x 0.10
          + 0.10 if country_shift
          + 0.10 if unsafe_country

    ALLOW < 0.35 <= CHALLENGE < 0.70 <= BLOCK

Each term is monotonic and independently invertible, so the required delta
for any single factor is exact rather than estimated.

WHAT YOU GET BACK
-----------------
  - the margin: how far the score sat from the nearest boundary. A BLOCK at
    0.701 and a BLOCK at 0.94 are not the same decision, and treating them
    the same is a failure of explanation.
  - per factor: the exact value that factor would have needed, alone, to
    reach the next verdict down - or a statement that this factor alone
    could not have done it, however far it moved.
  - the cheapest single change, where one exists.
  - a recourse statement in plain English, suitable for handing to the
    person the decision was about.

THE UNCOMFORTABLE PART, STATED UP FRONT
---------------------------------------
Perfect explainability and resistance to gaming are in direct tension, and
almost nobody in this field says so.

Telling a legitimate subject "your 60-second velocity needed to be under 11"
also tells a fraudster exactly where the wall is. This is not a flaw that
better engineering removes - it is what explanation IS. Publishing weights
means the boundary is derivable by anyone who reads the whitepaper anyway;
this module makes explicit what was already implicit.

The mitigations are honest rather than complete: these routes require a key
and are rate limited; every counterfactual request is itself sealed, so a
pattern of boundary probing is visible in the chain afterwards; and the
trust signal is history-dependent, so knowing the boundary does not let you
arrive at it instantly.

Operators handing counterfactuals to end users should treat that as a
deliberate choice with a cost, not a free feature.

    POST /x/counterfactual/explain    signals + verdict -> full analysis
    GET  /x/counterfactual/decision?block=N   explain a sealed decision
    GET  /x/counterfactual/probing    who has been mapping the boundary
"""

import json, math, time
from datetime import datetime, timezone

VERSION = "1.0"

ALLOW_MAX = 0.35
CHALLENGE_MAX = 0.70
LN_CAP = math.log1p(10000)

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS cf_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,ts REAL,block_index INTEGER,verdict TEXT,score REAL,target TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cf_key ON cf_requests(api_key,ts)")
        ctx["conn"].commit()
    _ready = True


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _verdict(sc):
    if sc < ALLOW_MAX:
        return "ALLOW"
    if sc < CHALLENGE_MAX:
        return "CHALLENGE"
    return "BLOCK"


def _normalise(data):
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, _f(data, "v60")),
        "v5m": max(0.0, _f(data, "v5m")),
        "v1h": max(0.0, _f(data, "v1h")),
        "amount": max(0.0, _f(data, "amount")),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": bool(data.get("unsafe_country")),
    }


# ---- per-factor contribution and inversion -------------------------------

def _contribs(s):
    return {
        "trust": (1 - s["trust"]) * 0.30,
        "v60": min(s["v60"] / 20.0, 1) * 0.15,
        "v5m": min(s["v5m"] / 50.0, 1) * 0.10,
        "v1h": min(s["v1h"] / 200.0, 1) * 0.10,
        "amount": min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15,
        "device_risk": s["device_risk"] * 0.10,
        "anomaly": s["anomaly"] * 0.10,
        "country_shift": 0.10 if s["country_shift"] else 0.0,
        "unsafe_country": 0.10 if s["unsafe_country"] else 0.0,
    }


def _invert(factor, target_contrib, s):
    """Value this factor would need for the stated contribution.
    Returns (value, human_string) or None where impossible."""
    t = target_contrib
    if factor == "trust":
        v = 1 - (t / 0.30)
        if v > 1.0:
            return None
        return round(_clamp(v), 4), "trust of " + str(round(_clamp(v), 3)) + " or higher (was " + str(round(s["trust"], 3)) + ")"
    if factor in ("v60", "v5m", "v1h"):
        cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[factor]
        v = (t / w) * cap
        if v < 0:
            return None
        label = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[factor]
        return round(v, 2), label + " velocity of " + str(int(v)) + " or fewer (was " + str(int(s[factor])) + ")"
    if factor == "amount":
        v = math.expm1((t / 0.15) * LN_CAP)
        if v < 0:
            return None
        return round(v, 2), "amount of " + str(round(v, 2)) + " or less (was " + str(round(s["amount"], 2)) + ")"
    if factor in ("device_risk", "anomaly"):
        v = t / 0.10
        if v < 0:
            return None
        nice = "device risk" if factor == "device_risk" else "behavioural anomaly"
        return round(_clamp(v), 4), nice + " of " + str(round(_clamp(v), 3)) + " or lower (was " + str(round(s[factor], 3)) + ")"
    if factor in ("country_shift", "unsafe_country"):
        if t >= 0.10:
            return None
        nice = "no country change from the previous event" if factor == "country_shift" else "an event from a jurisdiction on the safe list"
        return 0, nice
    return None


def _analyse(s, want=None):
    score = _score(s)
    verdict = _verdict(score)
    contribs = _contribs(s)

    if verdict == "BLOCK":
        target_v, ceiling = "CHALLENGE", CHALLENGE_MAX
    elif verdict == "CHALLENGE":
        target_v, ceiling = "ALLOW", ALLOW_MAX
    else:
        return {"score": score, "verdict": verdict,
                "margin_to_next_boundary": round(ALLOW_MAX - score, 4),
                "note": "Already the most permissive verdict. Nothing needed to change it."}, contribs, None

    if want in ("ALLOW", "CHALLENGE"):
        target_v = want
        ceiling = ALLOW_MAX if want == "ALLOW" else CHALLENGE_MAX

    # need score strictly below ceiling
    needed = round(score - ceiling, 6)
    factors = []
    cheapest = None

    for name, c in sorted(contribs.items(), key=lambda kv: -kv[1]):
        entry = {"factor": name,
                 "contributed": round(c, 4),
                 "share_of_score_pct": (round(100 * c / score, 1) if score else 0)}
        if c <= 0:
            entry["alone_sufficient"] = False
            entry["reason"] = "contributed nothing to this score"
            factors.append(entry)
            continue
        # contribution required so total lands just under the ceiling
        target_contrib = c - needed - 0.0001
        if target_contrib < 0:
            entry["alone_sufficient"] = False
            entry["reason"] = ("even at zero this factor only removes "
                               + str(round(c, 4)) + " of the "
                               + str(round(needed, 4)) + " required")
        else:
            inv = _invert(name, target_contrib, s)
            if inv is None:
                entry["alone_sufficient"] = False
                entry["reason"] = "no attainable value of this factor reaches the threshold"
            else:
                val, human = inv
                entry["alone_sufficient"] = True
                entry["required_value"] = val
                entry["statement"] = human
                if cheapest is None:
                    cheapest = {"factor": name, "required_value": val, "statement": human}
        factors.append(entry)

    summary = {
        "score": score,
        "verdict": verdict,
        "target_verdict": target_v,
        "threshold": ceiling,
        "margin": round(score - ceiling, 4),
        "score_reduction_required": max(0.0, needed),
        "factors": factors,
    }
    if cheapest:
        summary["single_change_that_would_have_sufficed"] = cheapest
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". The threshold for " + target_v + " is " + str(ceiling) +
            ". The decision would have been " + target_v + " with " +
            cheapest["statement"] + ", all else unchanged.")
    else:
        summary["single_change_that_would_have_sufficed"] = None
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". No single factor, changed alone, would have reached " + target_v +
            " - the score was driven by several factors together.")
    return summary, contribs, cheapest


def _log(ctx, api_key, block_index, verdict, score, target):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO cf_requests(api_key,ts,block_index,verdict,score,target) VALUES(?,?,?,?,?,?)",
                            (api_key, time.time(), block_index, verdict, score, target))
        ctx["conn"].commit()


def _seal(ctx, api_key, summary, block_index):
    ts = time.time()
    ev = {"user_id": "cf:" + str(block_index or "adhoc"), "action": "counterfactual",
          "amount": 0, "country": "UK", "device_id": "counterfactual",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "COUNTERFACTUAL_SEALED", "score": 0,
           "cf_version": VERSION, "timestamp": ts,
           "explained_verdict": summary.get("verdict"),
           "explained_score": summary.get("score"),
           "target_verdict": summary.get("target_verdict"),
           "detail": summary.get("recourse_statement")}
    return ctx["seal"](ev, res, ts, api_key)


def _explain(ctx, api_key, data):
    s = _normalise(data)
    want = str(data.get("target_verdict", "")).strip().upper() or None
    summary, _c, _ch = _analyse(s, want)
    h, idx, seq = _seal(ctx, api_key, summary, None)
    _log(ctx, api_key, None, summary.get("verdict"), summary.get("score"), want)
    summary["inputs_used"] = s
    summary["audit_hash"] = h
    summary["block_index"] = idx
    summary["receipt_seq"] = seq
    summary["reproduce"] = "Weights are published. Re-run the arithmetic yourself - this result is not an approximation."
    return summary, 200


def _decision(ctx, api_key, data):
    try:
        bid = int(data.get("block", 0))
    except (TypeError, ValueError):
        return {"error": "block_required", "message": "Pass ?block=<block_index> from a sealed decision."}, 400
    if bid <= 0:
        return {"error": "block_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT event_json,result_json,ts FROM audit_log WHERE id=? AND api_key=?", (bid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_block", "block": bid}, 404
    try:
        ev = json.loads(row[0])
        res = json.loads(row[1])
    except Exception:
        return {"error": "block_unreadable"}, 500
    if str(res.get("decision", "")).endswith("_SEALED"):
        return {"error": "not_a_decision",
                "message": "That block is a notary event, not an engine decision."}, 400

    sig = res.get("signals") or res.get("applied") or {}
    s = _normalise({
        "trust": sig.get("trust", res.get("trust", 0.5)),
        "v60": sig.get("v60", 0), "v5m": sig.get("v5m", 0), "v1h": sig.get("v1h", 0),
        "amount": ev.get("amount", 0),
        "device_risk": ev.get("device_risk", 0),
        "anomaly": ev.get("anomaly", 0),
        "country_shift": sig.get("country_shift", False),
        "unsafe_country": sig.get("unsafe_country", False),
    })
    summary, _c, _ch = _analyse(s)
    sealed_score = res.get("score")
    if sealed_score is not None and abs(float(sealed_score) - summary["score"]) > 0.0002:
        summary["reconstruction_warning"] = (
            "Recomputed score " + str(summary["score"]) + " does not match the sealed score "
            + str(sealed_score) + ". The sealed record does not carry every signal value, "
            "so this explanation is indicative rather than exact. Pass the signals directly "
            "to /explain for an exact result.")
    else:
        summary["reconstruction"] = "exact - recomputed score matches the sealed score"
    summary["explained_block"] = bid
    summary["sealed_at"] = _iso(row[2])
    h, idx, seq = _seal(ctx, api_key, summary, bid)
    _log(ctx, api_key, bid, summary.get("verdict"), summary.get("score"), None)
    summary["audit_hash"] = h
    summary["block_index"] = idx
    return summary, 200


def _probing(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT ts,verdict,score FROM cf_requests WHERE api_key=? AND ts>? ORDER BY ts DESC", (api_key, t - 86400)).fetchall()
    if not rows:
        return {"requests_24h": 0,
                "note": "No counterfactual requests in the last 24 hours."}, 200
    scores = [r[2] for r in rows if r[2] is not None]
    near = len([x for x in scores if abs(x - CHALLENGE_MAX) < 0.02 or abs(x - ALLOW_MAX) < 0.02])
    out = {"requests_24h": len(rows),
           "last_request": _iso(rows[0][0]),
           "near_boundary_requests": near,
           "note": "Every counterfactual request is sealed. Boundary probing leaves a trail whether or not anyone is watching at the time."}
    if len(rows) >= 50:
        out["flag"] = str(len(rows)) + " counterfactual requests in 24 hours - consistent with systematic boundary mapping"
    if near >= 10:
        out["boundary_flag"] = str(near) + " requests sat within 0.02 of a threshold"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "explain":
            return _explain(ctx, api_key, data)
    else:
        if action == "decision":
            return _decision(ctx, api_key, data)
        if action == "probing":
            return _probing(ctx, api_key)
    return {"error": "unknown_action", "action": action,
            "available": ["POST explain", "GET decision?block=", "GET probing"]}, 404

```


## `modules/declare.py`

345 lines, 13493 bytes

```python
"""
Declaration notary - /x/declare/<action>

THE IDEA
--------
An operator uploads their own file saying what must always be true of their
decisions. It is sealed, versioned, and published. Every record is then tested
against it, and every violation is sealed.

WHY THIS ISN'T CIRCULAR
-----------------------
The obvious objection: if they write their own rules AND supply their own
data, checking one against the other proves nothing. They could declare
nothing and pass.

Two things stop that.

1. THE RULES COME FIRST. A declaration is sealed before the records it judges.
   You cannot write the rule after seeing the outcome, because the chain shows
   which came first. Retrofitting a standard to a result is exactly what this
   makes impossible.

2. YOU CANNOT QUIETLY WEAKEN IT. Every version is kept and sealed. If you
   published a strict rule in March and a loose one in September, both are
   permanent and the change is dated. Nobody can pretend the strict one never
   existed. Weakening your own standard becomes a visible act.

So the file does not prove you are honest. It converts your claims into
something that can be tested, and takes away your ability to move the goalposts
afterwards. An auditor reads the declaration, reads the violations, and reads
the version history. All three are sealed.

RULE FORMAT
-----------
    {"rules": [
      {"id": "no-silent-high-value",
       "describe": "Payments over 10000 are never auto-allowed",
       "when":    {"field": "amount",   "op": ">",  "value": 10000},
       "require": {"field": "decision", "op": "in", "value": ["CHALLENGE","BLOCK"]}}
    ]}

    ops: == != > >= < <= in not_in exists

HONEST LIMITS
-------------
- Weak rules prove weak things. A declaration that requires nothing passes
  everything. Publish it and let people judge the rules themselves.
- This tests what was sealed. A decision never recorded cannot violate a rule
  - gapless receipts are what cover that gap, not this.
- The operator still supplies the data. This is not an external audit. It is a
  published standard, sealed before the evidence, that they can be held to.

    POST /x/declare/publish     declaration file - sealed and versioned
    GET  /x/declare/current     the live declaration
    GET  /x/declare/history     every version ever published
    POST /x/declare/check       test sealed records against it, seal the result
    GET  /x/declare/violations  what failed, and when
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.0"
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "exists"}
MAX_RULES = 100

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declarations(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,version INTEGER,body TEXT,sha256 TEXT,published REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declare_checks(check_id TEXT PRIMARY KEY,api_key TEXT,decl_version INTEGER,ran REAL,tested INTEGER,passed INTEGER,violated INTEGER,detail TEXT,audit_hash TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dec_key ON declarations(api_key,version)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, ref, action, detail):
    ts = time.time()
    ev = {"user_id": "dec:" + ref, "action": "declare_" + action, "amount": 0,
          "country": "UK", "device_id": "declare", "anomaly": 0, "device_risk": 0}
    res = {"decision": "DECLARATION_SEALED", "score": 0, "declare_action": action,
           "declare_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _validate(body):
    if not isinstance(body, dict):
        return "declaration must be an object"
    rules = body.get("rules")
    if not isinstance(rules, list) or not rules:
        return "declaration needs a non-empty rules list"
    if len(rules) > MAX_RULES:
        return "too many rules (max " + str(MAX_RULES) + ")"
    seen = set()
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            return "rule " + str(i) + " is not an object"
        rid = str(r.get("id", "")).strip()
        if not rid:
            return "rule " + str(i) + " has no id"
        if rid in seen:
            return "duplicate rule id: " + rid
        seen.add(rid)
        req = r.get("require")
        if not isinstance(req, dict) or not req.get("field"):
            return "rule " + rid + " has no require.field"
        for part in ("when", "require"):
            c = r.get(part)
            if c is None:
                continue
            if not isinstance(c, dict):
                return "rule " + rid + ": " + part + " must be an object"
            if c.get("op", "==") not in OPS:
                return "rule " + rid + ": unknown op " + str(c.get("op"))
    return None


def _get(record, field):
    cur = record
    for part in str(field).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _test(cond, record):
    if not cond:
        return True
    val = _get(record, cond["field"])
    op = cond.get("op", "==")
    want = cond.get("value")
    if op == "exists":
        return (val is not None) == bool(want if want is not None else True)
    if val is None:
        return False
    try:
        if op == "==":
            return str(val).strip().lower() == str(want).strip().lower()
        if op == "!=":
            return str(val).strip().lower() != str(want).strip().lower()
        if op == "in":
            return str(val).strip().lower() in [str(x).strip().lower() for x in want]
        if op == "not_in":
            return str(val).strip().lower() not in [str(x).strip().lower() for x in want]
        v, w = float(val), float(want)
        if op == ">":
            return v > w
        if op == ">=":
            return v >= w
        if op == "<":
            return v < w
        if op == "<=":
            return v <= w
    except Exception:
        return False
    return False


def _current(ctx, api_key):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT version,body,sha256,published,audit_hash FROM declarations WHERE api_key=? ORDER BY version DESC LIMIT 1", (api_key,)).fetchone()


def _publish(ctx, api_key, data):
    body = data.get("declaration")
    if body is None:
        body = {k: v for k, v in data.items() if k != "declaration"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"error": "declaration_not_json"}, 400
    err = _validate(body)
    if err:
        return {"error": "invalid_declaration", "detail": err}, 400

    prev = _current(ctx, api_key)
    ver = (prev[0] + 1) if prev else 1
    sha = _sha(body)
    if prev and prev[2] == sha:
        return {"error": "unchanged",
                "message": "Identical to version " + str(prev[0]) + ". Nothing to publish."}, 400

    ref = "V" + str(ver)
    ids = [str(r.get("id")) for r in body["rules"]]
    detail = ("version=" + str(ver) + ";sha256=" + sha + ";rules=" + str(len(ids)) +
              ";ids=" + ",".join(ids[:40]) +
              (";replaces=" + prev[2] if prev else ";first_declaration=true"))
    h, idx, seq, ts = _seal_event(ctx, api_key, ref, "published", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO declarations(api_key,version,body,sha256,published,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
                            (api_key, ver, json.dumps(body), sha, ts, h, idx))
        ctx["conn"].commit()

    out = {"version": ver, "sha256": sha, "rules": len(ids), "rule_ids": ids,
           "published": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "Sealed. Every record from this point is judged against it, and this version cannot be removed."}
    if prev:
        out["replaces_version"] = prev[0]
        out["warning"] = "Version " + str(prev[0]) + " remains sealed and readable. Changes to your own standard are permanent and dated."
    return out, 200


def _current_view(ctx, api_key):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration",
                "message": "Nothing published yet."}, 404
    return {"version": row[0], "declaration": json.loads(row[1]),
            "sha256": row[2], "published": _iso(row[3]),
            "sealed": row[4]}, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT version,sha256,published,audit_hash,body FROM declarations WHERE api_key=? ORDER BY version ASC", (api_key,)).fetchall()
    if not rows:
        return {"count": 0, "versions": []}, 200
    out = []
    for v, sha, ts, ah, body in rows:
        try:
            n = len(json.loads(body).get("rules", []))
        except Exception:
            n = None
        out.append({"version": v, "sha256": sha, "published": _iso(ts),
                    "sealed": ah, "rules": n})
    return {"count": len(out), "versions": out,
            "note": "Every version ever published. Loosening a standard is visible here permanently."}, 200


def _check(ctx, api_key, data):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration"}, 404
    ver, body = row[0], json.loads(row[1])
    rules = body["rules"]

    try:
        limit = min(int(data.get("limit", 500)), 5000)
    except Exception:
        limit = 500

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT id,user_id,event_json,result_json,ts FROM audit_log WHERE api_key=? AND ts>=? ORDER BY id DESC LIMIT ?", (api_key, row[3], limit)).fetchall()

    violations = []
    tested = 0
    for bid, uid, ev_json, res_json, bts in recs:
        try:
            rec = {}
            rec.update(json.loads(ev_json))
            rec.update(json.loads(res_json))
        except Exception:
            continue
        if rec.get("decision", "").endswith("_SEALED"):
            continue
        tested += 1
        for r in rules:
            if not _test(r.get("when"), rec):
                continue
            if not _test(r.get("require"), rec):
                violations.append({"block_index": bid, "record_id": uid,
                                   "rule": r.get("id"),
                                   "describe": r.get("describe"),
                                   "at": _iso(bts)})

    ts = time.time()
    cid = "CHK-" + _sha(str(ts) + api_key)[:8].upper()
    detail = ("decl_version=" + str(ver) + ";tested=" + str(tested) +
              ";violated=" + str(len(violations)) +
              ";rules=" + ",".join(sorted({v["rule"] for v in violations})[:20]))
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "checked", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO declare_checks(check_id,api_key,decl_version,ran,tested,passed,violated,detail,audit_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                            (cid, api_key, ver, ts, tested, tested - len({v["block_index"] for v in violations}), len(violations), json.dumps(violations[:200]), h))
        ctx["conn"].commit()

    out = {"check_id": cid, "declaration_version": ver, "records_tested": tested,
           "violations": len(violations), "ran_at": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "note": "Result sealed whichever way it went."}
    if violations:
        out["failed_rules"] = sorted({v["rule"] for v in violations})
        out["detail"] = violations[:20]
        out["flag"] = str(len(violations)) + " record(s) violate your own published rules"
    return out, 200


def _violations(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT check_id,decl_version,ran,tested,violated,detail FROM declare_checks WHERE api_key=? ORDER BY ran DESC LIMIT 50", (api_key,)).fetchall()
    if not rows:
        return {"checks": 0, "note": "No checks run yet."}, 200
    latest = rows[0]
    try:
        detail = json.loads(latest[5])
    except Exception:
        detail = []
    return {"checks": len(rows),
            "latest": {"check_id": latest[0], "declaration_version": latest[1],
                       "ran": _iso(latest[2]), "tested": latest[3],
                       "violations": latest[4], "detail": detail[:50]},
            "history": [{"check_id": r[0], "ran": _iso(r[2]), "tested": r[3],
                         "violations": r[4]} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "publish":
            return _publish(ctx, api_key, data)
        if action == "check":
            return _check(ctx, api_key, data)
    else:
        if action == "current":
            return _current_view(ctx, api_key)
        if action == "history":
            return _history(ctx, api_key)
        if action == "violations":
            return _violations(ctx, api_key)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/demo.py`

358 lines, 15159 bytes

```python
"""
Public proving ground - /x/demo/<action>

WHY THIS EXISTS
---------------
Every page on this platform says "check it, don't trust it" and then asks for
an email address before anyone can check anything. That is the same bargain
every other vendor offers, dressed in better language.

This removes the bargain. No key, no account, no email. A visitor sends a
scenario, gets a real verdict from the live engine, and it is sealed into the
production chain - the same chain, the same sequence, covered by the same
external anchor. They get the block index back and can verify it themselves at
a public endpoint that has never heard of them.

The demonstration is not a simulation of the product. It IS the product, run
once, by a stranger, for free.

WHAT IS DELIBERATELY REAL
-------------------------
  - the scoring is the engine's own arithmetic, not a mock
  - the seal is a genuine block in the live chain
  - the counterfactual is computed by inverting the real function
  - the review flow really does withhold the verdict until commitment
  - the dwell time is really measured and really sealed

WHAT IS DELIBERATELY NOT REAL
-----------------------------
  - demo events do not touch any customer's trust history; user ids are
    namespaced to demo: and scored from a neutral starting trust
  - nothing about a visitor is recorded beyond what they typed

ABUSE
-----
Public routes are rate limited per client by the router. A visitor cannot
flood the chain, and the cost of a demo block is a few hundred bytes.

    POST /x/demo/govern   scenario -> verdict, seal, counterfactual
    POST /x/demo/review   open a review case, verdict withheld
    POST /x/demo/commit   commit a verdict, then see what the machine said
    GET  /x/demo/stats    how many people have tried it
"""

import json, math, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"

# No key required for any of these - that is the entire point.
PUBLIC = {("POST", "govern"), ("POST", "review"), ("POST", "commit"),
          ("GET", "stats"), ("GET", "")}

DEMO_KEY = "public_demo"
LN_CAP = math.log1p(10000)
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK", "FI", "IE", "NZ"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_cases(case_id TEXT PRIMARY KEY,opened REAL,material TEXT,machine_verdict TEXT,score REAL,committed REAL,human_verdict TEXT,dwell REAL)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_stats(k TEXT PRIMARY KEY,v INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _bump(ctx, k):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_stats(k,v) VALUES(?,1) ON CONFLICT(k) DO UPDATE SET v=v+1", (k,))
        ctx["conn"].commit()


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _signals(data):
    country = str(data.get("country", "UK")).strip().upper()[:4] or "UK"
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, min(_f(data, "v60"), 10000)),
        "v5m": max(0.0, min(_f(data, "v5m"), 10000)),
        "v1h": max(0.0, min(_f(data, "v1h"), 100000)),
        "amount": max(0.0, min(_f(data, "amount"), 10000000)),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country": country,
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": country not in SAFE,
    }


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _reasons(s):
    r = []
    if s["trust"] < 0.4:
        r.append("low_trust")
    if s["v60"] > 10:
        r.append("velocity_spike")
    if s["amount"] > 500:
        r.append("high_amount")
    if s["device_risk"] > 0.5:
        r.append("risky_device")
    if s["anomaly"] > 0.5:
        r.append("behaviour_anomaly")
    if s["country_shift"]:
        r.append("country_shift")
    if s["unsafe_country"]:
        r.append("unsafe_country")
    return r


def _verdict(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def _counterfactual(s, score, verdict):
    """Exact inversion. Returns the cheapest single change, or None."""
    if verdict == "ALLOW":
        return None, "Already the most permissive verdict."
    ceiling = 0.70 if verdict == "BLOCK" else 0.35
    target = "CHALLENGE" if verdict == "BLOCK" else "ALLOW"
    needed = score - ceiling + 0.0001

    contribs = [
        ("trust", (1 - s["trust"]) * 0.30),
        ("amount", min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15),
        ("v60", min(s["v60"] / 20.0, 1) * 0.15),
        ("v5m", min(s["v5m"] / 50.0, 1) * 0.10),
        ("v1h", min(s["v1h"] / 200.0, 1) * 0.10),
        ("device_risk", s["device_risk"] * 0.10),
        ("anomaly", s["anomaly"] * 0.10),
        ("country_shift", 0.10 if s["country_shift"] else 0.0),
        ("unsafe_country", 0.10 if s["unsafe_country"] else 0.0),
    ]
    contribs.sort(key=lambda kv: -kv[1])

    for name, c in contribs:
        if c <= 0 or c < needed:
            continue
        t = c - needed
        if name == "trust":
            v = 1 - (t / 0.30)
            if v <= 1.0:
                return {"factor": "trust", "required": round(_clamp(v), 3),
                        "was": round(s["trust"], 3)}, ("a trust score of "
                        + str(round(_clamp(v), 3)) + " instead of "
                        + str(round(s["trust"], 3)) + " would have made this "
                        + target)
        if name == "amount":
            v = math.expm1((t / 0.15) * LN_CAP)
            return {"factor": "amount", "required": round(v, 2),
                    "was": round(s["amount"], 2)}, ("an amount of "
                    + str(round(v, 2)) + " instead of " + str(round(s["amount"], 2))
                    + " would have made this " + target)
        if name in ("v60", "v5m", "v1h"):
            cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[name]
            v = (t / w) * cap
            lbl = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[name]
            return {"factor": name, "required": int(v), "was": int(s[name])}, (
                "a " + lbl + " velocity of " + str(int(v)) + " instead of "
                + str(int(s[name])) + " would have made this " + target)
        if name in ("device_risk", "anomaly"):
            v = t / 0.10
            lbl = "device risk" if name == "device_risk" else "behavioural anomaly"
            return {"factor": name, "required": round(_clamp(v), 3), "was": round(s[name], 3)}, (
                "a " + lbl + " of " + str(round(_clamp(v), 3)) + " instead of "
                + str(round(s[name], 3)) + " would have made this " + target)
        if name in ("country_shift", "unsafe_country"):
            lbl = ("no country change from the previous event" if name == "country_shift"
                   else "an event from a jurisdiction on the safe list")
            return {"factor": name, "required": 0, "was": 1}, (
                lbl + " would have made this " + target)
    return None, ("no single factor, changed alone, would have reached "
                  + target + " - several drove this together")


def _govern(ctx, data):
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    reasons = _reasons(s)
    cf, cf_text = _counterfactual(s, score, verdict)

    ts = time.time()
    uid = "demo:" + secrets.token_hex(3)
    ev = {"user_id": uid, "action": str(data.get("action", "payment"))[:40],
          "amount": s["amount"], "country": s["country"],
          "device_id": "demo", "anomaly": s["anomaly"],
          "device_risk": s["device_risk"]}
    res = {"decision": verdict, "score": score, "reasons": reasons,
           "demo": True, "demo_version": VERSION, "timestamp": ts,
           "signals": {k: s[k] for k in ("trust", "v60", "v5m", "v1h",
                                          "country_shift", "unsafe_country")},
           "note": "public demonstration - sealed into the live chain like any other decision"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)
    _bump(ctx, "govern")

    return {"decision": verdict, "score": score, "reasons": reasons,
            "sealed_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "counterfactual": cf,
            "counterfactual_statement": cf_text,
            "verify": {
                "this_block": "/api/inclusion?hash=" + h,
                "whole_chain": "/api/verify-chain",
                "external_anchor": "/api/anchor-status"},
            "what_just_happened": [
                "Your scenario was scored by the live engine, not a simulation.",
                "The verdict was sealed into the production chain as block " + str(idx) + ".",
                "That block is now covered by the next external timestamp.",
                "Nothing about you was recorded. No account, no email, no key.",
                "Verify any of it at the links above - they have never heard of you."]}, 200


def _review(ctx, data):
    """Open a review case. The verdict is computed and sealed - and withheld."""
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    cid = "DEMO-" + secrets.token_hex(4).upper()
    ts = time.time()
    material = {"action": str(data.get("action", "payment"))[:40],
                "amount": s["amount"], "country": s["country"],
                "60_second_velocity": int(s["v60"]),
                "5_minute_velocity": int(s["v5m"]),
                "device_risk": s["device_risk"],
                "behavioural_anomaly": s["anomaly"],
                "country_changed": s["country_shift"],
                "trust_history": round(s["trust"], 3)}
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_cases(case_id,opened,material,machine_verdict,score,committed,human_verdict,dwell) VALUES(?,?,?,?,?,NULL,NULL,NULL)",
                            (cid, ts, json.dumps(material), verdict, score))
        ctx["conn"].commit()
    _bump(ctx, "review_opened")
    return {"case_id": cid, "opened": _iso(ts), "material": material,
            "machine_verdict": "withheld until you commit",
            "your_options": ["allow", "challenge", "block"],
            "instruction": "Decide for yourself, then POST your verdict to /x/demo/commit with this case_id. The clock is running and your answer is sealed before ours is shown."}, 200


def _commit(ctx, data):
    cid = str(data.get("case_id", "")).strip().upper()
    hv = str(data.get("verdict", "")).strip().upper()
    if hv not in ("ALLOW", "CHALLENGE", "BLOCK"):
        return {"error": "verdict_required", "allowed": ["allow", "challenge", "block"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT opened,material,machine_verdict,score,committed FROM demo_cases WHERE case_id=?", (cid,)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_committed",
                "message": "You commit once. That is the point of it."}, 400

    ts = time.time()
    dwell = round(ts - row[0], 2)
    agreed = (hv == row[2])

    ev = {"user_id": "demo:" + cid, "action": "demo_oversight_commit",
          "amount": 0, "country": "UK", "device_id": "demo",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "DEMO_OVERSIGHT_SEALED", "score": 0, "demo": True,
           "timestamp": ts, "human_verdict": hv, "dwell_seconds": dwell,
           "detail": "human verdict sealed before the machine verdict was revealed"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE demo_cases SET committed=?,human_verdict=?,dwell=? WHERE case_id=?",
                            (ts, hv, dwell, cid))
        ctx["conn"].commit()
    _bump(ctx, "review_committed")

    out = {"case_id": cid, "your_verdict": hv,
           "machine_verdict": row[2], "machine_score": row[3],
           "agreed": agreed, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "what_just_happened": [
               "Your verdict was sealed as block " + str(idx) + " BEFORE this response revealed ours.",
               "The chain fixes that order permanently and it cannot be reversed.",
               "Your dwell time of " + str(dwell) + "s is part of the record.",
               "That is the difference between a reviewer who decided and one who agreed."]}
    if dwell < 2:
        out["flag"] = ("committed in " + str(dwell) + " seconds - on a real system that would sit "
                       "in your record permanently, and a pattern of it would be visible to an auditor")
    if agreed:
        out["note"] = "You agreed with the engine - but the chain shows you did so without having seen it."
    else:
        out["note"] = "You diverged from the engine. On a real system that is evidence of independent judgement."
    return out, 200


def _stats(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT k,v FROM demo_stats").fetchall()
        cases = ctx["conn"].execute("SELECT COUNT(*),AVG(dwell) FROM demo_cases WHERE committed IS NOT NULL").fetchone()
        fast = ctx["conn"].execute("SELECT COUNT(*) FROM demo_cases WHERE dwell IS NOT NULL AND dwell<2").fetchone()
    d = {k: v for k, v in rows}
    out = {"decisions_run": d.get("govern", 0),
           "review_cases_opened": d.get("review_opened", 0),
           "review_cases_committed": d.get("review_committed", 0)}
    if cases and cases[0]:
        out["median_dwell_seconds"] = round(cases[1] or 0, 2)
        out["committed_under_2_seconds"] = fast[0] if fast else 0
        out["note"] = ("Visitors who committed in under two seconds did not read the case. "
                       "On a real deployment that is exactly what the record would show.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "govern":
            return _govern(ctx, data)
        if action == "review":
            return _review(ctx, data)
        if action == "commit":
            return _commit(ctx, data)
    else:
        if action in ("", "stats"):
            return _stats(ctx)
    return {"error": "unknown_action", "action": action,
            "available": ["POST govern", "POST review", "POST commit", "GET stats"]}, 404

```


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```
