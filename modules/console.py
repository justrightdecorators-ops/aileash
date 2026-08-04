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

VERSION = "1.0"

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
.v-why{font-size:14px;color:var(--mute);margin-top:11px;line-height:1.6}
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
