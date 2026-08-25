#!/usr/bin/env python3
"""
modules/binddesk.py  -  buttons for the signed lane

modules/bind.py is the engine. It answers POST requests with a key, which is
correct and completely unusable from a phone: a browser address bar can only
send GET, and nothing in it can attach an Authorization header.

So this is the page. Paste the key once, tap a button. Same routes underneath,
nothing new in the trust path.

Served at /bind-desk by the same runtime do_GET patch console.py uses. The
page holds nothing - the key is typed in, kept in the tab, and sent on each
request. Every route it calls checks that key itself.

PUBLIC is empty. Nothing here is reachable without a key except the page
itself, and the page is inert until one is pasted into it.
"""

import sys

VERSION = "1.0"

PUBLIC = set()

PAGE_PATHS = ("/bind-desk", "/bind-desk.html", "/binddesk")
_patched = [False]


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Bind desk</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0f1e;color:#e8ecf5;font-family:ui-monospace,Menlo,monospace;
 font-size:14px;line-height:1.55;padding:0 0 80px}
.w{max-width:620px;margin:0 auto;padding:22px 16px}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:#6b7894;font-size:12.5px;margin-bottom:22px}
h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#c9a84c;
 margin:0 0 12px}
label{display:block;font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#6b7894;margin:12px 0 6px}
input{width:100%;background:#131b2e;border:1px solid #223052;color:#e8ecf5;
 font-family:inherit;font-size:14px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:#c9a84c}
button{width:100%;background:#c9a84c;color:#0a0f1e;border:0;border-radius:4px;
 padding:14px;font-family:inherit;font-weight:700;font-size:14px;margin-top:12px;
 cursor:pointer}
button:active{opacity:.8}
button.q{background:transparent;color:#8f98ad;border:1px solid #223052;font-weight:400}
button.danger{background:transparent;color:#ff8a80;border:1px solid #4a2422;font-weight:400}
.card{background:#131b2e;border:1px solid #223052;border-radius:7px;
 padding:18px;margin:16px 0}
.note{color:#6b7894;font-size:11.5px;line-height:1.6;margin-top:10px}
.out{margin-top:12px;font-size:12px;white-space:pre-wrap;word-break:break-all;
 background:#080c16;border:1px solid #223052;border-radius:4px;padding:12px;
 max-height:320px;overflow:auto}
.ok{color:#7fe3b0}.bad{color:#ff8a80}.warn{color:#c9a84c}
.secret{background:#0f1c15;border:1px solid #2c5c44;border-radius:5px;
 padding:14px;margin-top:12px}
.secret .lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#7fe3b0;margin-bottom:6px}
.secret .val{font-size:13px;color:#7fe3b0;word-break:break-all;line-height:1.8}
.secret .warnline{color:#c9a84c;font-size:11.5px;margin-top:10px;line-height:1.6}
.step{display:inline-block;background:#223052;color:#8f98ad;border-radius:3px;
 padding:2px 8px;font-size:11px;margin-bottom:10px}
</style></head><body><div class="w">

<h1>Bind desk</h1>
<p class="sub">Names on the witness network. Your key stays in this tab.</p>

<div class="card">
  <label for="k">Your API key</label>
  <input id="k" type="password" placeholder="paste it here" autocomplete="off">
  <p class="note">Typed once, used by every button below. Nothing is stored.</p>
</div>

<div class="card">
  <span class="step">STEP 1</span>
  <h2>Claim a name</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">Puts a dated marker in
  the chain. Does not stop anyone else submitting — but theirs is provably
  later. Do this first if the name is exposed.</p>
  <label for="cn">Name</label>
  <input id="cn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="cc">Who is claiming it</label>
  <input id="cc" placeholder="Ishaan">
  <label for="cnote">Note (optional)</label>
  <input id="cnote" placeholder="pending credential">
  <button onclick="doClaim()">Seal the claim</button>
  <div id="o-claim"></div>
</div>

<div class="card">
  <span class="step">STEP 2</span>
  <h2>Issue a credential</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">This is the real fix.
  Once issued, only the holder of the secret can submit under that name.</p>
  <label for="in">Name</label>
  <input id="in" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="ito">Issued to</label>
  <input id="ito" placeholder="Ishaan">
  <button onclick="doIssue(false)">Issue it</button>
  <button class="q" onclick="doIssue(true)">Replace the existing one</button>
  <div id="o-issue"></div>
</div>

<div class="card">
  <h2>Check a name</h2>
  <label for="qn">Name</label>
  <input id="qn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <button class="q" onclick="doLook()">Look it up</button>
  <button class="q" onclick="doConflicts()">Show every contested name</button>
  <div id="o-look"></div>
</div>

<div class="card">
  <h2>Revoke a credential</h2>
  <label for="rk">Key id</label>
  <input id="rk" placeholder="bk_..." autocapitalize="off" autocorrect="off">
  <label for="rr">Reason</label>
  <input id="rr" placeholder="rotating">
  <button class="danger" onclick="doRevoke()">Revoke</button>
  <p class="note">Stops future submissions. Anything already bound stays bound.</p>
  <div id="o-revoke"></div>
</div>

</div>
<script>
var $=function(i){return document.getElementById(i)};
function key(){var k=$('k').value.trim();return k||null}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function show(id,cls,txt){$(id).innerHTML='<div class="out '+cls+'">'+esc(txt)+'</div>'}
function shown(id,html){$(id).innerHTML=html}

async function call(path,method,body){
  var k=key();
  if(!k){return {status:0,data:{error:'paste your key at the top first'}}}
  var o={method:method,headers:{'Authorization':'Bearer '+k}};
  if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  try{
    var r=await fetch(path,o);
    var d; try{d=await r.json()}catch(e){d={error:'unreadable response'}}
    return {status:r.status,data:d};
  }catch(e){return {status:0,data:{error:'could not reach the server'}}}
}

async function doClaim(){
  var n=$('cn').value.trim(), c=$('cc').value.trim();
  if(!n||!c){show('o-claim','bad','Fill in the name and who is claiming it.');return}
  show('o-claim','','Sealing...');
  var r=await call('/x/bind/claim','POST',{name:n,claimant:c,note:$('cnote').value.trim()});
  if(r.status!==200){show('o-claim','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-claim','ok','CLAIMED\\n\\nname     '+r.data.name
    +'\\nclaimant '+r.data.claimant
    +'\\nsealed   '+r.data.sealed_in_chain
    +'\\nblock    '+r.data.block_index
    +'\\n\\nThis is a dated marker, not a binding. Do step 2.');
}

async function doIssue(replace){
  var n=$('in').value.trim(), t=$('ito').value.trim();
  if(!n){show('o-issue','bad','Enter the name.');return}
  show('o-issue','','Issuing...');
  var r=await call('/x/bind/issue','POST',{name:n,issued_to:t,replace:!!replace});
  if(r.status===409){
    show('o-issue','warn','A credential already exists for '+n
      +'.\\n\\nUse "Replace the existing one" if you mean to revoke it and issue another.');
    return;
  }
  if(r.status!==200){show('o-issue','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  shown('o-issue','<div class="secret">'
    +'<div class="lbl">send both of these to them privately</div>'
    +'<div class="val">key_id&nbsp;&nbsp;'+esc(r.data.key_id)+'</div>'
    +'<div class="val">secret&nbsp;&nbsp;'+esc(r.data.secret)+'</div>'
    +'<div class="warnline">The secret is shown here once and is not stored '
    +'anywhere. Copy it now. If it is lost you have to revoke and reissue.</div>'
    +'<div class="warnline">Do not send it over LinkedIn or anywhere public.</div>'
    +'</div>'
    +'<div class="out ok">sealed  '+esc(r.data.sealed_in_chain)
    +'\\nblock   '+esc(r.data.block_index)+'</div>');
}

async function doLook(){
  var n=$('qn').value.trim();
  if(!n){show('o-look','bad','Enter a name.');return}
  show('o-look','','Looking...');
  var r=await call('/x/bind/name?name='+encodeURIComponent(n),'GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'not found');return}
  var d=r.data;
  var cls = d.state==='bound' ? 'ok' : 'warn';
  var t='STATE   '+d.state.toUpperCase()+'\\n\\n'+d.meaning+'\\n';
  if(d.credential){t+='\\nkey_id     '+d.credential.key_id
    +'\\nissued to  '+(d.credential.issued_to||'-')
    +'\\nissued at  '+d.credential.issued_at;}
  if(d.claims&&d.claims.length){t+='\\n\\nCLAIMS';
    d.claims.forEach(function(c){t+='\\n  '+c.claimant+'  '+c.claimed_at
      +'  block '+c.block_index;});}
  if(d.signed_submissions&&d.signed_submissions.length){
    t+='\\n\\nSIGNED SUBMISSIONS  '+d.signed_submissions.length;
    d.signed_submissions.slice(0,5).forEach(function(s){
      t+='\\n  '+s.at+'  block '+s.block_index;});}
  show('o-look',cls,t);
}

async function doConflicts(){
  show('o-look','','Checking...');
  var r=await call('/x/bind/conflicts','GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'failed');return}
  var d=r.data, t='';
  if(!d.contested_claims.length && !d.names_with_multiple_live_credentials.length){
    t='No contested names.';
  } else {
    d.contested_claims.forEach(function(c){t+='CONTESTED  '+c.name+'  ('+c.claimants+' claimants)\\n'});
    d.names_with_multiple_live_credentials.forEach(function(c){
      t+='MULTIPLE CREDENTIALS  '+c.name+'  ('+c.credentials+')\\n'});
  }
  show('o-look', t==='No contested names.'?'ok':'warn', t+'\\n\\n'+d.note);
}

async function doRevoke(){
  var k=$('rk').value.trim();
  if(!k){show('o-revoke','bad','Enter the key id.');return}
  show('o-revoke','','Revoking...');
  var r=await call('/x/bind/revoke','POST',{key_id:k,reason:$('rr').value.trim()});
  if(r.status!==200){show('o-revoke','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-revoke','ok','REVOKED\\n\\nname    '+r.data.name
    +'\\nkey_id  '+r.data.key_id
    +'\\nsealed  '+r.data.sealed_in_chain
    +'\\n\\n'+r.data.note);
}
</script></body></html>"""


def _install():
    if _patched[0]:
        return "already installed"
    m = sys.modules.get("__main__")
    srv = m if (m is not None and hasattr(m, "get_bearer")) else sys.modules.get("server")
    if srv is None:
        return "no server"
    H = getattr(srv, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_binddesk_patched", False):
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
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._binddesk_patched = True
    _patched[0] = True
    print("BINDDESK: /bind-desk installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    state = _install()
    action = (action or "").strip("/").lower()

    if not api_key:
        return {"error": "invalid_api_key",
                "note": "The page at /bind-desk is where you use this. Nothing "
                        "here answers without a key."}, 401

    if method == "GET" and action in ("", "status"):
        return {"binddesk_version": VERSION,
                "installed": bool(_patched[0]),
                "install_result": state,
                "page": "/bind-desk",
                "engine": "/x/bind/spec",
                "what_it_does": ("Buttons for the signed lane. Claim a name, "
                                 "issue a credential, look one up, revoke one. "
                                 "The page sends the same POST requests the "
                                 "engine already accepts."),
                "note": "The page is not public in any useful sense - it is "
                        "inert until a key is pasted into it, and every route "
                        "it calls checks that key."}, 200

    return {"error": "unknown_action", "GET": ["status"]}, 404
