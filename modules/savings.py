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

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/savings", "/savings.html", "/cost", "/proof-machine")

_patched = [False]


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

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/savings",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": ("Runs entirely in the browser. Nothing a visitor types is "
                     "submitted or recorded."),
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404
