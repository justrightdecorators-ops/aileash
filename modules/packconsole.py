"""
modules/packconsole.py  -  the evidence pack page at /pack

WHY IT EXISTS
-------------
/x/pack/preview, render, issue and history are all keyed. A browser address
bar cannot send an Authorization header, so from a phone they are unreachable.
This serves one page that can.

It is deliberately NOT part of console.py. That file is large and editing it
on a phone risks the whole thing. This adds a second page and touches nothing
that already works.

SAME PATCH AS console.py / network.py
-------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime under its own
attribute name, adds two paths, and passes everything else straight through
to whatever was there before - including console.py's patch, whichever
installs first.

And the same catch: after every deploy one /x/ request must arrive before
/pack exists. Opening /x/packconsole/status does it, and Railway's
healthcheck on /x/console/status will arm this too once it is listed in
console.py's SIBLINGS.

THE KEY
-------
Typed in, held in a variable for that tab, never written to storage. Close
the tab and it is gone.
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/pack", "/pack.html", "/pack-console")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Evidence pack - AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0f1e;--panel:#131b2e;--panel2:#1a2338;
 --edge:rgba(201,168,76,.22);--gold:#c9a84c;--gold-dim:#8a7233;
 --text:#f2efe6;--mute:rgba(242,239,230,.42);--ok:#7fe3b0;--bad:#c8362b;
 --mono:ui-monospace,'IBM Plex Mono',monospace}
body{background:var(--ink);color:var(--text);font:16px/1.6 system-ui,
 -apple-system,sans-serif;padding:0 0 60px}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}
header{padding:32px 0 20px;border-bottom:1px solid var(--edge);
 margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
 text-transform:uppercase;color:var(--gold);margin-bottom:10px}
h1{font-size:34px;line-height:1;letter-spacing:-.02em;font-weight:800}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14.5px;margin-top:12px;max-width:46ch}
label{display:block;font-family:var(--mono);font-size:10px;
 letter-spacing:.16em;text-transform:uppercase;color:var(--mute);
 margin-bottom:7px}
input{width:100%;background:var(--panel);border:1px solid var(--edge);
 color:var(--text);font-family:var(--mono);font-size:13px;padding:12px 13px;
 border-radius:4px;outline:none}
input:focus{border-color:var(--gold)}
.box{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
 padding:16px;margin-bottom:16px}
.note{font-size:12px;color:var(--mute);margin-top:9px;line-height:1.55}
.field{margin-bottom:12px}
.seg{display:flex;gap:8px}
.seg button{flex:1}
button{width:100%;background:var(--gold);color:var(--ink);border:none;
 border-radius:4px;padding:13px;font-weight:700;font-size:14.5px;
 cursor:pointer;font-family:inherit}
button:hover:not(:disabled){background:#dbbd63}
button:disabled{opacity:.45;cursor:default}
button.quiet{background:transparent;color:var(--mute);
 border:1px solid var(--edge)}
button.quiet.on{color:var(--ink);background:var(--gold);border-color:var(--gold)}
button.quiet:hover:not(:disabled):not(.on){color:var(--text);
 border-color:var(--gold)}
.row{display:flex;gap:8px;margin-top:10px}
.row button{flex:1}
#out{margin-top:24px}
.verdict{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
 overflow:hidden;margin-bottom:14px}
.v-head{padding:22px 18px;border-bottom:1px solid var(--edge)}
.v-word{font-size:38px;line-height:1;letter-spacing:-.02em;font-weight:800}
.v-ok{color:var(--ok)}.v-bad{color:var(--bad)}.v-mute{color:var(--mute)}
.v-why{color:var(--mute);font-size:13.5px;margin-top:10px;line-height:1.6}
.v-stats{display:flex;flex-wrap:wrap;gap:18px;padding:14px 18px;
 border-bottom:1px solid var(--edge);font-family:var(--mono);font-size:11px}
.v-stats b{display:block;font-size:19px;color:var(--text);font-weight:700;
 margin-top:3px;font-family:inherit}
.v-stats span{color:var(--mute);letter-spacing:.1em;text-transform:uppercase}
.lin{padding:14px 18px;border-bottom:1px solid var(--edge)}
.lin:last-child{border-bottom:none}
.strip-l{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
 text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.kv{display:flex;justify-content:space-between;gap:14px;padding:6px 0;
 border-bottom:1px solid rgba(201,168,76,.10);font-size:13.5px}
.kv:last-child{border-bottom:none}
.kv b{color:var(--gold);font-family:var(--mono);font-size:12.5px}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.65;
 background:#080c16;color:var(--ok);padding:15px;border-radius:5px;
 overflow-x:auto;border:1px solid var(--edge);max-height:320px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;
 border-radius:5px;border:1px solid var(--edge);color:var(--mute);
 margin-bottom:14px}
.msg.bad{color:#ffb4ad;border-color:rgba(200,54,43,.5);
 background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);
 background:rgba(26,158,110,.08)}
.working:after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}
 75%{content:'...'}}
iframe{width:100%;height:70vh;border:1px solid var(--edge);border-radius:6px;
 background:#0a0f1e;margin-top:12px}
code{font-family:var(--mono);font-size:12px;color:#9fb3d9;
 word-break:break-all}
footer{margin-top:32px;padding-top:18px;border-top:1px solid var(--edge);
 font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash &middot; evidence pack</p>
  <h1>The <span>document</span></h1>
  <p class="sub">Re-verifies every block in a period against the hash sealed
  at the time. Not a summary of the chain &mdash; a check of it.</p>
</header>

<div class="box">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_&hellip;"
   autocomplete="off" spellcheck="false">
  <p class="note">Held in memory for this tab only. Nothing is written to
  the device.</p>
</div>

<div class="box">
  <div class="field">
    <label for="period">Period</label>
    <input id="period" value="2026-Q2" autocomplete="off"
     placeholder="2026-Q2, 2026-07 or 2026">
  </div>
  <label>Scope</label>
  <div class="seg">
    <button class="quiet on" id="sc-me" onclick="setScope('me')">My key</button>
    <button class="quiet" id="sc-all" onclick="setScope('')">Whole deployment</button>
  </div>
  <p class="note">Receipt-sequence checking only applies to a single key.
  A deployment-wide pack still re-verifies every hash.</p>
  <div class="row">
    <button onclick="go('preview')">Preview</button>
    <button onclick="go('render')">View page</button>
  </div>
  <div class="row">
    <button class="quiet" onclick="go('history')">Past packs</button>
    <button class="quiet" onclick="go('issue')">Issue &amp; seal</button>
  </div>
  <p class="note">Issuing seals the pack's own digest into the chain, so the
  document cannot be edited afterwards. It cannot be withdrawn.</p>
</div>

<div id="out"></div>

<footer>
  Spec: <a href="/x/pack/spec">/x/pack/spec</a> &middot;
  Chain: <a href="/api/verify-chain">/api/verify-chain</a> &middot;
  Console: <a href="/console">/console</a>
</footer>

</div>

<script>
(function(){
  var out=document.getElementById('out'), busy=false, scope='me';

  window.setScope=function(v){
    scope=v;
    document.getElementById('sc-me').classList.toggle('on',v==='me');
    document.getElementById('sc-all').classList.toggle('on',v==='');
  };

  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function msg(t,k){out.innerHTML='<div class="msg '+(k||'')+'">'+esc(t)+'</div>';}
  function raw(o){return '<pre>'+esc(JSON.stringify(o,null,2))+'</pre>';}
  function key(){var k=document.getElementById('key').value.trim();
    if(!k){msg('Paste your API key at the top first.','bad');return null;}return k;}

  async function call(path,method,body){
    var k=key(); if(!k) return null;
    var o={method:method,headers:{'Authorization':'Bearer '+k}};
    if(body){o.headers['Content-Type']='application/json';
      o.body=JSON.stringify(body);}
    var r=await fetch(path,o), d;
    try{d=await r.json();}catch(e){d={error:'unreadable_response'};}
    return {status:r.status,data:d};
  }

  function qs(){
    var p=encodeURIComponent(document.getElementById('period').value.trim());
    return '?period='+p+(scope?'&scope='+scope:'');
  }

  function renderPack(d){
    var ig=d.integrity||{}, sq=d.receipt_sequence||{};
    var clean=!!ig.clean;
    var h='<div class="verdict"><div class="v-head">'
      +'<div class="v-word '+(clean?'v-ok':'v-bad')+'">'
      +esc(ig.hashes_verified)+' of '+esc(ig.blocks_recomputed)
      +'</div><div class="v-why">blocks re-verified &mdash; '
      +esc(ig.method||'')+'</div></div>'
      +'<div class="v-stats">'
      +'<div><span>period</span><b>'+esc(d.period)+'</b></div>'
      +'<div><span>entries</span><b>'+esc(d.entries_in_period)+'</b></div>'
      +'<div><span>unbroken since</span><b style="font-size:14px">'
      +esc(d.unbroken_since)+'</b></div>'
      +'<div><span>devices</span><b>'
      +esc((d.devices||{}).total_ever)+'</b></div></div>';

    if(!clean){
      h+='<div class="lin"><div class="strip-l">Problems found</div>'
        +'<div class="kv"><span>mismatched blocks</span><b>'
        +esc(JSON.stringify(ig.hash_mismatches||[]))+'</b></div>'
        +'<div class="kv"><span>link breaks</span><b>'
        +esc(JSON.stringify(ig.link_breaks||[]))+'</b></div>'
        +'<div class="kv"><span>link into period</span><b>'
        +esc(ig.link_into_period)+'</b></div></div>';
    }

    h+='<div class="lin"><div class="strip-l">Receipt sequence</div>';
    if(sq.applicable){
      h+='<div class="kv"><span>'+(sq.gapless?'Complete, no gaps'
         :'GAPS FOUND')+'</span><b>'+esc(sq.received)+' of '
         +esc(sq.expected)+'</b></div>';
      if(!sq.gapless){h+='<div class="kv"><span>missing</span><b>'
         +esc(JSON.stringify(sq.missing))+'</b></div>';}
    } else {
      h+='<div class="kv"><span>Not applicable to a deployment-wide pack'
         +'</span><b>&mdash;</b></div>';
    }
    h+='</div>';

    var vs=d.verdicts||{};
    if(Object.keys(vs).length){
      h+='<div class="lin"><div class="strip-l">Verdicts in period</div>';
      Object.keys(vs).sort().forEach(function(k){
        h+='<div class="kv"><span>'+esc(k)+'</span><b>'+esc(vs[k])
          +'</b></div>';});
      h+='</div>';
    }

    h+='<div class="lin"><div class="strip-l">Chain range</div>'
      +'<div class="kv"><span>first</span><b>#'+esc(d.first_block)
      +'</b></div><div class="kv"><span>last</span><b>#'+esc(d.last_block)
      +'</b></div><div class="kv"><span>pack digest</span></div>'
      +'<code>'+esc(d.pack_digest)+'</code></div>';

    if(d.sealed){
      h+='<div class="lin"><div class="strip-l">Sealed into the chain</div>'
        +'<div class="kv"><span>block</span><b>'+esc(d.sealed.block_index)
        +'</b></div><code>'+esc(d.sealed.audit_hash)+'</code></div>';
    }
    h+='</div>';
    return h;
  }

  function renderHistory(d){
    if(!d.count) return '<div class="msg">No packs issued yet.</div>';
    var h='<div class="verdict"><div class="v-head">'
      +'<div class="v-word v-ok">'+esc(d.count)+'</div>'
      +'<div class="v-why">packs issued and sealed</div></div><div class="lin">';
    (d.packs||[]).forEach(function(p){
      h+='<div class="kv"><span>'+esc(p.period)+' &middot; '+esc(p.issued)
        +'</span><b>'+esc(p.hashes_verified)+' verified'
        +(p.mismatches?' / '+esc(p.mismatches)+' bad':'')+'</b></div>';});
    h+='</div></div>';
    return h;
  }

  window.go=async function(what){
    if(busy) return;
    var period=document.getElementById('period').value.trim();
    if(what!=='history' && !period){
      msg('Give a period: 2026-Q2, 2026-07 or 2026.','bad'); return; }
    busy=true;
    out.innerHTML='<div class="msg"><span class="working">Re-verifying every '
      +'block in the period</span></div>';
    try{
      var res;
      if(what==='preview') res=await call('/x/pack/preview'+qs(),'GET');
      else if(what==='render') res=await call('/x/pack/render'+qs(),'GET');
      else if(what==='history') res=await call('/x/pack/history','GET');
      else res=await call('/x/pack/issue','POST',
        {period:period,scope:scope||undefined});
      if(!res){busy=false;return;}

      if(res.status===401){
        msg('That key was refused. Check it and try again.','bad');
      } else if(res.status===404 && res.data
                && res.data.error==='unknown_module'){
        msg('The pack module is not deployed. Open /x/pack/spec first.','bad');
      } else if(res.status>=400){
        out.innerHTML='<div class="msg bad">'
          +esc((res.data&&(res.data.message||res.data.error))
               ||('HTTP '+res.status))+'</div>'+raw(res.data);
      } else if(what==='render' && res.data.html){
        var f=document.createElement('iframe');
        f.setAttribute('sandbox','');
        f.srcdoc=res.data.html;
        out.innerHTML='<div class="msg good">The pack as one page. Long-press '
          +'to save, or screenshot it.</div>';
        out.appendChild(f);
      } else if(what==='history'){
        out.innerHTML=renderHistory(res.data)+raw(res.data);
      } else if(res.data.integrity){
        var pre = (what==='issue')
          ? '<div class="msg good">Issued and sealed. This cannot be '
            +'withdrawn.</div>' : '';
        out.innerHTML=pre+renderPack(res.data)+raw(res.data);
      } else {
        out.innerHTML='<div class="msg good">Done.</div>'+raw(res.data);
      }
    }catch(e){
      msg('Could not reach the server.','bad');
    }
    busy=false;
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
    if getattr(H, "_packconsole_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
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
    H._packconsole_patched = True
    _patched[0] = True
    print("PACKCONSOLE: /pack page installed at runtime", flush=True)
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
            print("PACKCONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {"page": "/pack",
                "installed": bool(_patched[0]),
                "install_result": state,
                "version": VERSION,
                "calls": ["/x/pack/preview", "/x/pack/render",
                          "/x/pack/issue", "/x/pack/history"],
                "note": ("The page holds no credentials. Every route it "
                         "calls checks the key itself.")}, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404
