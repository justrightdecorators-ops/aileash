# Codebase — part 16 of 44

Contains:
- `modules/peerconsole.py`
- `modules/plugin.py`
- `modules/praxis.py`


## `modules/peerconsole.py`

376 lines, 15478 bytes

```python
"""
modules/peerconsole.py  v1.0  -  the peer credential page at /peers

Register a peer, rotate their secret, suspend them, see who is on.
Keyed POSTs a browser address bar cannot reach.

Own patch attribute so it composes with console.py and packconsole.py.
After a deploy, one /x/ request arms it: /x/peerconsole/status
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0"
PUBLIC = {("GET", "status")}
PAGE_PATHS = ("/peers", "/peers.html", "/peer-console")

_patched = [False]

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Peers — AILeash</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--ink:#0a0f1e;--panel:#131b2e;--panel2:#1a2338;--edge:rgba(201,168,76,.22);
--gold:#c9a84c;--text:#f2efe6;--mute:rgba(242,239,230,.42);--ok:#7fe3b0;--err:#ff8a80;
--mono:'IBM Plex Mono',ui-monospace,monospace;--body:system-ui,-apple-system,sans-serif}
body{background:var(--ink);color:var(--text);font-family:var(--body);font-size:16px;
line-height:1.6;padding:0 0 60px}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}
header{padding:30px 0 20px;border-bottom:1px solid var(--edge);margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
text-transform:uppercase;color:var(--gold);margin-bottom:8px}
h1{font-size:34px;line-height:1;font-weight:800;letter-spacing:-.02em}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14px;margin-top:10px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--mute);margin-bottom:6px}
input{width:100%;background:var(--panel);border:1px solid var(--edge);color:var(--text);
font-family:var(--mono);font-size:13px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:var(--gold)}
.keybar{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
padding:16px;margin-bottom:24px}
.keynote{font-size:12px;color:var(--mute);margin-top:8px}
.op{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
margin-bottom:12px;overflow:hidden}
.op-head{display:flex;align-items:baseline;gap:10px;padding:15px 16px;cursor:pointer}
.op-head:hover{background:var(--panel2)}
.op-n{font-family:var(--mono);font-size:10px;color:var(--gold);opacity:.6}
.op-t{font-size:17px;font-weight:700}
.op-r{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--mute)}
.op-body{padding:0 16px 16px;display:none}
.op.open .op-body{display:block}
.op-why{font-size:13.5px;color:var(--mute);margin-bottom:14px}
.field{margin-bottom:12px}
button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;
padding:14px;font-weight:700;font-size:14.5px;cursor:pointer}
button:hover:not(:disabled){background:#dbbd63}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--edge)}
.two{display:flex;gap:10px}
.two button{flex:1}
#out{margin-top:24px}
pre{font-family:var(--mono);font-size:11.5px;line-height:1.6;background:#080c16;
color:var(--ok);padding:14px;border-radius:5px;overflow-x:auto;
border:1px solid var(--edge);max-height:320px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;border-radius:5px;
border:1px solid var(--edge);color:var(--mute);margin-bottom:12px}
.msg.bad{color:var(--err);border-color:rgba(200,54,43,.5);background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);background:rgba(26,158,110,.08)}
.secret{background:#080c16;border:2px solid var(--gold);border-radius:6px;padding:18px;
margin-bottom:14px}
.secret .lbl{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.secret .val{font-family:var(--mono);font-size:13px;color:var(--text);word-break:break-all;
line-height:1.7;background:var(--panel);padding:12px;border-radius:4px}
.secret .warn{color:var(--err);font-size:13px;margin-top:12px}
.peer{padding:12px 0;border-bottom:1px solid var(--edge)}
.peer:last-child{border-bottom:none}
.peer .id{font-family:var(--mono);font-size:13.5px;color:var(--gold)}
.peer .meta{font-size:12.5px;color:var(--mute);margin-top:3px}
.pill{display:inline-block;font-family:var(--mono);font-size:10px;padding:2px 7px;
border-radius:3px;letter-spacing:.1em;text-transform:uppercase}
.pill.active{background:rgba(26,158,110,.18);color:var(--ok)}
.pill.suspended{background:rgba(200,54,43,.15);color:var(--err)}
footer{margin-top:30px;padding-top:16px;border-top:1px solid var(--edge);
font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash · peer credentials</p>
  <h1>Signed <span>peers</span></h1>
  <p class="sub">The open endpoint stays open. This issues credentials to peers who need a guarantee that only they can submit as their chain.</p>
</header>

<div class="keybar">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_…" autocomplete="off" spellcheck="false">
  <p class="keynote">Held in this tab only. Close it and the key is gone.</p>
</div>

<div class="op open" id="op-reg">
  <div class="op-head" onclick="tog('op-reg')">
    <span class="op-n">01</span><span class="op-t">Register a peer</span>
    <span class="op-r">POST /x/peer/register</span>
  </div>
  <div class="op-body">
    <p class="op-why">Issues their secret. It is shown once here and never again — send it to them over a channel you trust, not the same email as everything else.</p>
    <div class="field">
      <label for="r-id">Peer id (lowercase, no spaces)</label>
      <input id="r-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-name">Chain name</label>
      <input id="r-name" placeholder="PRAXIS" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-url">Their public tip URL</label>
      <input id="r-url" placeholder="https://example.com/api/tip" autocomplete="off">
    </div>
    <button onclick="run('register')">Issue the credential</button>
  </div>
</div>

<div class="op" id="op-rot">
  <div class="op-head" onclick="tog('op-rot')">
    <span class="op-n">02</span><span class="op-t">Rotate a secret</span>
    <span class="op-r">POST /x/peer/rotate</span>
  </div>
  <div class="op-body">
    <p class="op-why">New secret now, old one keeps working for 24 hours so they can roll over without downtime.</p>
    <div class="field">
      <label for="o-id">Peer id</label>
      <input id="o-id" placeholder="praesidium" autocomplete="off">
    </div>
    <button onclick="run('rotate')">Rotate</button>
  </div>
</div>

<div class="op" id="op-sus">
  <div class="op-head" onclick="tog('op-sus')">
    <span class="op-n">03</span><span class="op-t">Suspend or resume</span>
    <span class="op-r">POST /x/peer/suspend</span>
  </div>
  <div class="op-body">
    <p class="op-why">Suspending refuses new submissions. Nothing is deleted and their sealed history stands.</p>
    <div class="field">
      <label for="s-id">Peer id</label>
      <input id="s-id" placeholder="praesidium" autocomplete="off">
    </div>
    <div class="two">
      <button onclick="run('suspend')">Suspend</button>
      <button class="quiet" onclick="run('resume')">Resume</button>
    </div>
  </div>
</div>

<div class="op" id="op-list">
  <div class="op-head" onclick="tog('op-list')">
    <span class="op-n">04</span><span class="op-t">Who is registered</span>
    <span class="op-r">GET /x/peer/peers</span>
  </div>
  <div class="op-body">
    <p class="op-why">Public route. Secrets are never returned by anything.</p>
    <button class="quiet" onclick="run('peers')">List them</button>
  </div>
</div>

<div class="op" id="op-hist">
  <div class="op-head" onclick="tog('op-hist')">
    <span class="op-n">05</span><span class="op-t">Submissions</span>
    <span class="op-r">GET /x/peer/history</span>
  </div>
  <div class="op-body">
    <p class="op-why">What has come in, with the receipt for each. Leave the id blank for everything.</p>
    <div class="field">
      <label for="h-id">Peer id (optional)</label>
      <input id="h-id" placeholder="leave blank for all" autocomplete="off">
    </div>
    <button class="quiet" onclick="run('history')">Show them</button>
  </div>
</div>

<div id="out"></div>

<footer>
  Spec for peers to implement: <a href="/x/peer/spec">/x/peer/spec</a><br>
  Open endpoint, unchanged: <a href="/x/witness/peers">/x/witness/peers</a><br>
  Other consoles: <a href="/console">/console</a> · <a href="/pack">/pack</a>
</footer>

</div>

<script>
(function(){
  var out=document.getElementById('out'), busy=false;
  window.tog=function(id){document.getElementById(id).classList.toggle('open');};
  function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function msg(t,k){out.innerHTML='<div class="msg '+(k||'')+'">'+esc(t)+'</div>';}
  function raw(o){return '<pre>'+esc(JSON.stringify(o,null,2))+'</pre>';}
  function val(id){return document.getElementById(id).value.trim();}
  function key(){var k=val('key');if(!k){msg('Paste your API key at the top first.','bad');return null;}return k;}

  async function call(path,method,body){
    var k=key(); if(!k) return null;
    var o={method:method,headers:{'Authorization':'Bearer '+k}};
    if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body);}
    var r=await fetch(path,o); var d;
    try{d=await r.json();}catch(e){d={error:'unreadable_response'};}
    return {status:r.status,data:d};
  }

  function showSecret(d,title,extra){
    return '<div class="secret"><div class="lbl">'+esc(title)+' — '+esc(d.peer_id)+'</div>'
      +'<div class="val">'+esc(d.secret)+'</div>'
      +'<div class="warn">Shown once. Not recoverable. Copy it now and send it to them '
      +'separately from anything else.</div>'
      +(extra?'<div class="warn" style="color:var(--mute)">'+esc(extra)+'</div>':'')
      +'</div>';
  }

  function showPeers(d){
    if(!d.peers||!d.peers.length) return '<div class="msg">No peers registered yet.</div>';
    var h='<div class="msg good">'+d.count+' registered</div><div class="op open"><div class="op-body" style="padding:16px">';
    d.peers.forEach(function(p){
      h+='<div class="peer"><span class="id">'+esc(p.peer_id)+'</span> '
        +'<span class="pill '+esc(p.status)+'">'+esc(p.status)+'</span>'
        +'<div class="meta">'+esc(p.chain_name||'')
        +' · '+esc(p.submissions)+' submissions'
        +(p.last_seen?' · last '+esc(p.last_seen):' · never submitted')
        +(p.rotation_overlap_active?' · rotating':'')
        +'</div>'
        +(p.url?'<div class="meta">'+esc(p.url)+'</div>':'')
        +'</div>';
    });
    return h+'</div></div>';
  }

  window.run=async function(what){
    if(busy) return;
    var path,method='POST',body=null;

    if(what==='register'){
      var id=val('r-id');
      if(!id){msg('Give the peer an id.','bad');return;}
      path='/x/peer/register';
      body={peer_id:id.toLowerCase(),chain_name:val('r-name')||id,url:val('r-url')};
    }
    else if(what==='rotate'){
      var oid=val('o-id');
      if(!oid){msg('Which peer?','bad');return;}
      path='/x/peer/rotate'; body={peer_id:oid.toLowerCase()};
    }
    else if(what==='suspend'||what==='resume'){
      var sid=val('s-id');
      if(!sid){msg('Which peer?','bad');return;}
      path='/x/peer/'+what; body={peer_id:sid.toLowerCase()};
    }
    else if(what==='peers'){path='/x/peer/peers';method='GET';}
    else if(what==='history'){
      var hid=val('h-id');
      path='/x/peer/history'+(hid?'?peer_id='+encodeURIComponent(hid.toLowerCase()):'');
      method='GET';
    }
    else return;

    busy=true;
    out.innerHTML='<div class="msg">Working…</div>';
    try{
      var res=await call(path,method,body);
      if(!res){busy=false;return;}
      var d=res.data;
      if(res.status===401){msg('That key was refused.','bad');}
      else if(res.status===404&&d&&d.error==='unknown_module'){
        msg('modules/peer.py is not deployed yet.','bad');}
      else if(res.status>=400){
        out.innerHTML='<div class="msg bad">'+esc((d&&(d.detail||d.error))||('HTTP '+res.status))+'</div>'+raw(d);}
      else if(what==='register'&&d.secret){
        out.innerHTML=showSecret(d,'Peer secret')
          +'<div class="msg good">Registered. Send them /x/peer/spec so they can implement the signing.</div>'+raw(d);}
      else if(what==='rotate'&&d.secret){
        out.innerHTML=showSecret(d,'New secret','Previous secret valid until '+(d.previous_valid_until||''))+raw(d);}
      else if(what==='peers'){out.innerHTML=showPeers(d)+raw(d);}
      else{out.innerHTML='<div class="msg good">Done.</div>'+raw(d);}
    }catch(e){msg('Could not reach the server.','bad');}
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
    if getattr(H, "_peerconsole_patched", False):
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
    H._peerconsole_patched = True
    _patched[0] = True
    print("PEERCONSOLE: /peers page installed at runtime", flush=True)
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
            print("PEERCONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/peers",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "paths": list(PAGE_PATHS),
            "note": "The page holds no credentials. Every route it calls "
                    "checks the key itself.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/plugin.py`

1141 lines, 59388 bytes

```python
"""
modules/plugin.py  v2.0.2
The public proof log: legacy systems send sebbi.pro the SHA-256 of a state
change, and get back a receipt proving that hash is in an append-only log.

  * An RFC 6962 Merkle tree (the Certificate Transparency construction):
        leaf hash  = SHA-256(0x00 || entry)      entry = the 32-byte state hash
        node hash  = SHA-256(0x01 || left || right)
    so any receipt can be checked by anyone, with any RFC 6962 verifier,
    without trusting this server.
  * Receipts come back straight away: leaf index, tree size, root and the
    inclusion (audit) path.
  * Tree heads are sealed into the sebbi.pro chain on a schedule (every 60s or
    every 1,000 leaves, whichever comes first). That chain is walkable at
    /x/walk and its tip is timestamped in Bitcoin with OpenTimestamps by the
    existing anchor, so a leaf becomes Bitcoin-anchored once a confirmed
    anchored tip is at or after the block that sealed its tree head.
  * Hash-only. No payloads, labels or customer data are sent or stored.
  * Idempotent: the client sends its own id with each hash, so a retry after a
    lost response returns the original leaf instead of adding a duplicate.

Routes (clean /p/ prefix, armed by /x/plugin/status):

    POST /p/submit        {"items":[{"hash":"<64 hex>","cid":"<client id>"}]}
                          or {"hash":"<64 hex>"}      needs an API key
    GET  /p/receipt?leaf=N        receipt against the sealed tree head
    GET  /p/proof?leaf=N&size=M   inclusion path at tree size M
    GET  /p/consistency?first=M&second=N   RFC 6962 consistency proof
    GET  /p/sth                   latest sealed tree head + current size
    GET  /p/find?hash=<64 hex>    leaf indexes holding that entry hash
    GET  /p/                      what this log is and how to check it

The customer journey (2.0.0), reached from the "plug in" bubble on the homepage:

    GET  /plugin              the product page: price, sign-up, set-up for Python,
                              JavaScript or any language, account, pricing,
                              receipt checker
    POST /p/signup            {name,email,org} -> a new key on the page and by email
                              (free 90 days; an existing email gets its key re-sent
                              to that inbox only)
    POST /p/account           {key} -> devices this month, bill, trial days, records
    POST /p/pay               {key} -> Stripe checkout for the real device count, or
                              the Stripe billing page for customers already paying
    GET  /p/sebbi_adapter.py  the Python adapter download

Keys are ordinary sebbi.pro keys (server.py's create_key, product "aileash"), so
the trial, the 50p device meter, the Stripe webhook and the 6-hourly quantity
sync all apply exactly as for the engine.

Billing (1.4.0): the same meter as the engine - 50p per device per month.
Each fingerprint can say which device it is about (a phone, terminal, till,
car...), sent as a one-way hash. Every distinct device seen on the key in a
calendar month counts once, through server.py's own record_device(), so a
customer running one central server for 20 million phones is billed for 20
million devices. Fingerprints with no device named count the installation
that sent them. Free for the key's 90-day trial. When a key's trial ends unpaid, /p/submit
answers 402 with the same Stripe checkout the engine gives (server.py's own
trial_checkout, quantity = real devices). Receipts, proofs and every GET route
stay free for good; the client keeps queuing and sends once paid.

The API key goes in the X-Sebbi-Key header (or "key" in the body). Set
ADAPTER_OPEN=1 in Railway to accept submissions without a key (not advised).

Size: kept well under 100,000 characters (the page and the adapter download are
stored compressed), because longer files get cut off when pasted into GitHub.

Loading: the live server loads modules through modules/router.py and calls
handle(). ALIASES and register(MODULE_MAP) are also provided so a loader that
maps modules by name (e.g. brain.py) can pick it up under "adapter",
"sidecar" or "anchor".

Assumes one server process (as on Railway today). If a second process ever
writes the same database, appends detect it and reload before continuing.
"""

import base64
import hashlib
import zlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse

VERSION = "2.0.2"
ALIASES = ["adapter", "sidecar", "anchor"]
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "sth"), ("GET", "proof"),
          ("GET", "receipt"), ("GET", "consistency"), ("GET", "find")}

KEY = "public-proof-adapter"
SITE = "https://sebbi.pro"
MAX_ITEMS = 500
MAX_BODY = 262144
CHECKPOINT_SECONDS = max(10, int(os.environ.get("ADAPTER_CHECKPOINT_SECONDS", "60") or 60))
CHECKPOINT_EVERY = max(1, int(os.environ.get("ADAPTER_CHECKPOINT_EVERY", "1000") or 1000))
OPEN = os.environ.get("ADAPTER_OPEN", "0") == "1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SPEC = ("RFC 6962 Merkle tree, SHA-256. leaf_hash = SHA256(0x00 || entry); "
        "node = SHA256(0x01 || left || right); entry = the 32 raw bytes of the submitted hash.")

_PAGE_B64 = (
    "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"
)
_ADAPTER_B64 = (
    "eNrVPWt327ix3/UrcNmTLrmhGcl5dFeNkjq2knXXj9RWurvH9WEoErJYU6RCUnbUnNzffmcGAAmQlOw8zr3nul2bD3AAzHsGA8Sy"
    "rF7Bp9PYD6JgWfLcW64Zuxl4A6/PdliUZ8udOGVFGZScBWk4z/I4vWKzLGcJvwrCNQuWyyQOgzLO0sLr9f7IVrn+jF1zvixYXBYs"
    "CspgGhTcpbsku4pDABnRXZzO8qAo81VYrnLusck8LnqzOOGswNdTXsQRh5ZDxm94vpYDCudBesXZOluxZRanJTRgAfwuGEBJOYBO"
    "y4wFvfNf9nZ2nz5jMxg7z5cwhdJlH1Z8BU2SLAySZO3SUAqOQFJWzjmbBuH1VZ6t4DEAgScCUd4yz9hyNYUJMrjMZjgTl93O43DO"
    "co4dFyyAq5DHyxKb3CDGEKLWfS/GOUOfiCueRjtZmqzZ2et99uznZ7vsmOfXMPcy5xwgZ4W8nPMgAuA5YIUHiZqfOTTACQGGUccL"
    "DnhaLKkhexWXISAJaHSKfTUGBOQMbniBuMzZIgjncUpk4EQ2pBFPZixF7LMo40jqyW+n7OjwZHze21E/PQY//OMyy0t2Pn716tDf"
    "e3vo/zr+Y4Rwd675mlU/dpaGyAsC2zy9ifMsXQABnB6BmeXZghm8yeIFQRZ86BMPUNO/6U9sK8sjnhfeaglD55ZDTSI+Y+KBT69t"
    "+u3HkUu8tCqcYU+NzPM8dtfPn9gqFewXVd8J6rNPloJtDVndjSX6gWfi4nOvdxIsOM0+4jdxCEgAvCumBgYJptmqZHbAlvMsBVSV"
    "cZLAb54v4jSAqzDIHSlB0Ly34PAKaL1EEhFAl4AX2EtQiOuKT3h6BSQe9roQiBJReMD7gD5XwhpZMK6o4CXOyxEoCICDeBIpGua8"
    "WCVlF8BlVngFcGwNLQkW0yiQn4Dw5VeFy65v8e9QPr2wcMLWpSAgCBTg0v5kBWEIQlkCHp/sAlanQQJ9cbgd7D7tf66He3g8Ptx5"
    "/BSICSzQOxAYTgEXQoIAozu3wZrNg2IOSANNpbM+aBzQcUSctRS4tESep2kSmW+CZEVk0qQIAAUz5FSSLuAQUoHFKgw5jwohT4hc"
    "JJeQpSLJbuGrKLtN2VRIZcrL2yy/JsqKRrMgTlAJhsEKVAGonHJO/SZAP633gl1lUuUJtWYoF9J3zC4+JHHJBd8EmpLrlfMc1AtO"
    "NCJeWXjscKYxDPS4SnNk0WCaSMzcBnEpNKfCEagrngJD9sIMMY3wScZJDkBNxuWcpRmLVsJCkCI5nfwyPmO/7f1xzg5PamVSKZTN"
    "mkAwhcv2iNuOsqtfYCwJz7+EYxxdqIN0DRPIQXKUKkeKII8QSFD1IDVX3hUvoTPAO7B2sEalVViOF0SR7N9uDsh2HIIvrBeAYQlw"
    "WafwgV6/QjucFaWFMr5EiziyUDIsR41T19w4wjhdrsiMFiUQsQsscE4OMniDMsg/lnkQlvcRQq/M/CgOS5hAr7dXrNOw4uuCEZtW"
    "KgakCYi5/8t4/9fDkzc9g4TLdTlHSWi6GkIV6opVsCmylDKhRLxiK5hZsirmhn5GNgZeFN4AsikgzAXOu90KR3X5HCn+AlsKvSae"
    "otcDasOw49ugAa3j2VofVc53wjkPrysvJkOFreBLV2QrTBwY++H5v4ssffEDwdRZIWB/Pz89kaqJfwQag+BL1a9E5zZbJVGvN6YR"
    "qK4BSTQwoQmDPI8BhpBW8FEqvyROQ8A06jRqDbZTuR85gPsBNGta3KJ4FmLyMY8Q6cCj+Qo4M/LYXtVlicQRmg2HJ/ACevGaL9Ho"
    "FYAj8PlAUIWumiUBCFwEHPYauGt89vbs8GTCzt4djUGnZSi4SJoQRotyvwBxQH/RMdXJXT+Vp5ih2gVgWRqjHkWsDsGVXRcw47zE"
    "WRV8GeQBELBglmvREK0hyNa7yeudn3DSPZIydAxByy2DENwpdD/QK3uEF2znBTs8P2U/PesPgBNyYtADHsYL6BDeyUe96Rq+xwdz"
    "/hG7LekljQKUSAFy++7d4YH2BXlsYRIU9BW6z2SlC7eXTf/NQ7gnulaC/cgPCnGF7ZEsHnudZAE0RHPzljgRaJvzZQ4ETOEeuunx"
    "pCDzl/MZNIuAZGlECpJHDgPMzMkMAj2uVrzABkDuHbbEYSn9QxJVon8LZAWC7o8FuXqv0dvFlz/3YTaAdWRKMIa3mj0CapB/k7Kn"
    "/aXm9NDlIkvL+bAnxCwCLAHnlqoBGXphHYQvQI6WKxQNSUDIyTtHWw16JMh7BI/NwVYjYyyA26SfhqEN3F+DIWNnEmRl5GqfIxLA"
    "SViUi5Gv0lSEBtKYAxLOx5MJsPc5szWHGIyntHA2eDMO6ukV2Zwv5G6piw3HXGkmwgn65zaOHv1OtOyGc1FrZtSnjgZrfHLw9hTF"
    "UfyArx2A6WDzslwWw0ePKpppnxy8MtS1+sR7JDUeTdeLpvon438Ch/jA6/STCucZcKcQinOgMMWW4IbwKuKCnjhuUi1AWDUEfQ4H"
    "h+d7r47GB6MBq50H1F3I7My+BleUFYCbcA6G8LwMkC1QAKd5ACyGHpYnRYU99n566PUsCK17KmJBwxln1W3JP4KLJO8qceWF9ogU"
    "RXUv1IK6JQucZUnVHq0CDEXdghuwBEFXt2gs1LX0YNRtVoEQfuHj6nZdvRGOofaRPrJVnkDHHs/zLG88yzlwTFGNYrWKwez4PggQ"
    "WhDfZyNmUaLBgqdg+OjJhaW7LaBPLUEJvBIyUF/V7hU+q7S1j/O1ZMDFfcSN5fY0ZrOEYfYra4aN5bMQ/BpQF2B31vgUHD1fMpN1"
    "2euh4zbq8gINO43xRu9PbOcbfwzp6/UwglVjsTMZrsYzUMHo9aFHa2cusL5kHU9duMx4pN3iL0eLe2Vgk3lxkYHyXQRgErp7kfzo"
    "SXPVhgGmCMa4YYhk0VyGf8DTCECNL/giy9c3Mb/tGA81B2geGMBNA7LBLroYKPyHp3DZAUVYTGwLWk55vh+HzGQb+6OzoQdkXw8t"
    "7V2T1cQZEOlXt9BEhHRZ2QBdrpe8DVWHIw207AQNY1CWOaoy25J2HLlVGnJLAzZLgWGBUbE99oV/XXYCvpJTtYFBo+OJYZ09S7WP"
    "tdHMUon6PIjB7k9gyGOUeUwWpDgl3Q19ULQsfYmZqQwzWeSUw62Ua/aA5o/09X3U6b6P4oPc3iANeC9ybKBaMZImB1ewRyudhTlA"
    "sMopeXIe6mJtMgjOi1aLZYFAXeINH7270SRfcd23G9ng3Lno2TkQNqUFhGKA5DCOR68D8H8MtaL9ADazW5hNKpsp+zZSAux4oGGy"
    "COOycrbzk6WmXKssc7qVXzpreKUuuvfPnjBMI+RhUGCS8CP6Joh2zII1pi4thVfMA4Bnd6CY5CyKwbVB8f8uiqyKH8jJV7psbk/l"
    "BLvHNnU8bRj4ScKDmUAOeD/52oeBmhAQpvWvj/2+xR4KxvAweYCKo/5CKRIBs2kL6oaYt4jwD+Ze/SL+D9BxCX6ty/IsK2va4Ox+"
    "HsDsCi7yPbtg1B57u0NkQoKGru97AvZe5coonwvUfF8Bfy/8xvcI/P1LRTb4upbH5nhAtIHXbXrsuHRdvTPEm1qw56yPrqS4eTGq"
    "4XRKPHGupkdALFLqsDGGHTaoVRc0uB8NasAwoiU+Q8wges3BLAGiCYQaO0YjmCGObcT6w5ZAds5GfgTajv2ZDRzEyowAFGkHBG1S"
    "A5zUEv7LnVY7AIiKUAEdduoGCAcTbrQT0W3K/qtz+JoefwEkG2xsUHQ1wBjtHhPKcVLmhDr7a/WhDKBAvsja4KVJMRIXuTQQUnT/"
    "T0xQkP1wa1PSNoGCaIacav6ZPYtzDH9B7LI0wmAFbn3sTD2TN7RMc4e8PpHyqssmsfd7Aep9c60GLBvYA/wcpZj63iC1xjClyNIz"
    "KbLihSYRuT+F5vC7xfv1FB238UqbcQ0K5Qmd6oYEOULqSOIQN5e6rqA+SBYIYqduQP4l2MS7NNIRjbgN6DkbkHjRzQuFBXiiYNxD"
    "+VTA/swEClDpOB0Cr+aLQ7pEpob7tgqrQFRE0XWYkFAhnMOvkIkZileBv7D3i/6loepCpeYuBsPL4f+iFpu1pD6E/2YdeqzobFn8"
    "f9Z47SkVqPPCb9B5M1J0xPu0cpwrERC3gpDfqvREBskvM/BkbXFT67FTuYKlpZnEEgzyGS0Ggj88rPPzsl2Q3GJG7Sq+kW4zvaQu"
    "KmcxVl2jSsRgAXlLPoF5WVZr1NhI98SsyEc0N1w6GSjvCFBDIgTEJXJmLafYcEUvho93L7+PP0qzjiGIDfJeT2RKZX5NZEhrHB9t"
    "WEZ7qJcH4FoDBBnsPJgBesM8KwqZNCnI+ISY/ywE12f5tfDJq1VpH3zPuPR9G1NX4M4vYwxFRie05AuQqbJB3kZTH3WHvJsGZTgn"
    "J2y02+93xCK0LOLjumR+EySjXa/vUvImW5WjQR/vyCH3qWZAxT5lkJd0rbEmDs2TIwNJstUl8El1WZCME7NQajgrPJnDxESJbRlp"
    "R4ypkL6Ysl7ajtmRmjT2VF3j2ksnRJV8RJCtjCP2kYtOrEdWox+JTehGXW3s5OAVJZTM3GQTXk0PALkIPtpgYBZxaj8F4pClrxs4"
    "TuNbk1RopDADb5uPG99IUlaN5X2jlUZi9CeyLLG1R02UxAWmAdBN2YAImSZFdPQtssHWwDKB+MGqzIiP0BLi38b72wCrc/w0k/zU"
    "svbISQYreAQG869zu6KyJSyJNdj9iwfc7IFip+RK2mCjf7Ukgz6j5bY5LrN2fmZakSS78nDYoFIb2b5hJaSY95BiQEO0XBNiA9dC"
    "7qV+sGXVC2o3pTN2xCK+qHWycz5dxUkpCwxQkThMZvRJjRjQsIOm/PrLWNIV6AnXTbHzb+m99SDaeVBgXsauPpPpL/z1xCatfDH8"
    "6bL5fXINn1fZYg9053W7j+CaG63GN2CyWs2KMlveoxkq4Ww2g5ZA/8Y7EHri40+fGy8i9KtlutsD9y8FjW/rCqFWko9RcIssoVI2"
    "P+E3PJG6V4gQmk5fDFJkepxWXx7/yMMVrsC/Pdt7c7zH/p2BfQwSfwGWbvTb3pF1j29w+WAOkpititHJ6dnxHV/tn433JmM2QUll"
    "h6/ZyemEjX8/PJ+cUz4i5sggHxgozfGb8Rl7e3Z4vHf2B8PloL13E1CmAOB4fDJxrY3OF7NC4JbJ+PcJe3dy+I93Y+rk5N3RkUtL"
    "1PSmepQEU57QMzcEZOEiGwzxyPnaWcg15MKGMXynWdRjxSSTyJFI0K5asqYJqIXt6u1W8MgmJPz1B+xg/Hrv3dGE9d04lYrZ6Onm"
    "S9BzeHIw/n0Denyc3elJjS64/2qgknMo/4ZAFSfh/VcTEpyveEHjElTQiOhidQloOkL6Ki3j5Nt4BjziwL5ud3NDj3SwRvTe3c/e"
    "0QQIKbqRiGB7Bwds//To3fGJcpURsAZXBgJK9ZwueU6KJUgoFGiGskWxZaKHJ+fjswk7PWOHb0AjIMkmp3KO7o3D/rl39G58bv8g"
    "RvKD+9IBa2RbcEt+eVud7/Yv3aZTojx+Zm9wBtSKrHDnlDd3MXzWvwRfapNctGdzPj4a70/YDXt9dnpMs2C//TKGWV2P1AwA/IyD"
    "+wTaF3rot4yPLF8b1ZGIiqlNl6SLsvRCQlCGmGyqzPhvsKoAXDOmGM5WBrOrly5zT70Y3bf7MOYnqpTrB7jEFCSgMuzOdZtNSKoN"
    "60R0C0OAiYxEs3yVuhRPjmS8FqiV1yjgi0yECt0EEI6a4c2IhR5aRUdviyKvoSxQxJDKlVWOtLJUGE6NLOETkdEyWIObC74IWRMV"
    "EYlqT1rQqhEAAdZrbTHovfz0PaFPRHBx6bH34uv3sixUlIuVWumtVniLlRde1cFZozrQxdCBYh/MtlPNWiKW+qZczoJHVXitE1Z5"
    "3J1pMIOXW2pJZV8RjOhDLI5oi0hy4o5CGv2usCbj7qaCGtMfTG1iFdb9/WCcrporsx8UqHK4s3FeDSrLsROp8VIswdyL1v8QlSnG"
    "AiBuCpB1YJFWGfLsSWOBzPneVJlT0JPbag6VWvRojc5uLV0kPLXnpD5gcLi0m64hQlMxidUf7D5+8vTZX376OZiGgC5L5BHn+HLe"
    "kXMTC7R1sgniJbTYi1VBzNhCgOV06KqG4jOb0DqVcvk7km2bjBWZKOU2gMknT1H4hsotdCVLKvv10pX/cyy3d2dRvt00a8BJWBsA"
    "1KBewDINwM4R0skjpUQF8ZPw+Smktp17dNWZmnO6UIkRj1fw0u6UhPn/pfCRek6y7Hq1LBpqF/3FhjCaMneExdulURtrCqCNunGR"
    "yTbwQCyFitpD1LTkOFaK0xDDO5hwCwPm2S0btVmwRVDlcuSenIGbe1XJau7pfjvcKj/d5Z5gV+6pOIY8FuUCctYOBqy/QyhSueAs"
    "J4fcA/YfcfwtHR3uITpGL8GjOwDP8tUfDJnmA8QK5/sutIeGeMmODo8PJ2zQIQ22qXSksgGfTvObmjkWwNbdGg6GDiilmgm0JYUN"
    "XxkOGDS4sBTyfFnFbF2qbBM2HzSb6wg2m+42m9JSM2598gvOU1/Rgr5SJhc/fHxZZatJriuIj5sQiYb0Pb5+ctlMZkOj2jqJ8vPu"
    "jMrXcGio8afxosxKyvyFLb94//TdycT+0TGYrekQN1QPpU83gTqAiAji4wnDgFBAVQy6FWy4/Dqgksl1oo8GW3uakpv69V0pdhz1"
    "N3ZTbddSatMaChqIokOERs8Ql/BIbiJQjdiOeNGWd7E3r+bTIaANvsdSdyUePmEC3sA0P9eshqsMqNsbvKb7eZIbnYtqPJeaLldb"
    "h/S8IKYipSaHwGqeRaqKZZpF66YzRZv9RnqBFLZqLcygyOGLdta/oTk+ADCzHNQ7E39tM0f7UA4KBzDCX2q0I/FHl+APuNOGNAKW"
    "Xu5nwE5puYNLahiHaptPH1El6OZP3xU839m7gq+r7P6ONKiPMErWilWdlosoFz6a+tPs4fedc4L6K1+rbLD8bku6gZRHA2twmwF7"
    "2HBfpyf1VQAH/YV848px7omtNq6hyD0R8UKgb5IXbLL16XM7daFX+3q/TCZvycPs8FRac9KGAmYPOjMGwu89kC5P6c6ePmky5lPK"
    "SQqEXuyYkuegeYHfpMw1zfVq/AYcgMPj4/HB4d5k3JhMN6ay28JQf50OqdKJ5Ee4woOAPzJr03BMhFrU8mG2/HrQ0J+5bKr5KA7r"
    "znFaeycHW0CK5B67VrkczenBD689yuq9eCnvRL7v+YuXG7tr+EbCF3qJiS0gnluvYiBhpdYHV8RuFy5QBIXtfPg/BlKI8O5ShLAr"
    "53Y2fnu0ty+TbnUOU6YsRbbSjGHujl8IgDEHYMiHtI74jNZqjTW/H9njZrjRGO3+6TGg54tFR4Nwdnp09Gpv/1fL6Q4yW24TIFET"
    "tJwnPCi4FDWYnb7HeotMNZ133G1jWwfAWpOxwVjSqQCmEiwksD9ChriwQw2XTl16g8O4NJNvWa6NETd+hq7pqcgaXmXQmzYzw2Wv"
    "VhkpgBGpUln0SLsQMEtKPYhX9VIDvNoZ6K+q+kp4078zIK0+C1YRJhnBlCISLnWIWBkml92Nym99hQLTY9m12n0pvqsbWI1sA028"
    "4c1bl1pvtDxsDqAVgmTX7RiXi7xFI8LVQ03EHC63vt47PBofUBpOJBQbOxTBS6NNP9oOwo2C2EUWx/kajjUzHvrqi7a6pFaVqgUl"
    "1wg6q5BTLQlt0oq1emzmTO6ld2zF9O25u7ofSGJhFspDgwElwa+F79e/i00HLYaT31WyZaRhHKe1NeVal1xwHn0qqWg6zFgwj/t/"
    "0SulBl6VsE1XiynPWeXf/1WmnXGHofKe0VPHU0gaicGqKKHT89MbmAUObR27LY9j7s4TILFY0diKh5sWzfNLxL483KS2nUusqSwS"
    "E5scMdndod67yzSQ5l3ZgnrlXfot4vPa0dIqY7pSEMVwO9TbgHhlxD4Brw7ZvDbfc81818v8MdgMHMZFo/RSfgH+UbfJjzFk/kTp"
    "UgjN5i6tDmP4Fkefm7QGIG26xuWFJbwvSi7AZQM+jMsTxWR2XG6JAITbKmp7BDIpirPenp5TndOj5aNiNV3EqNA/qS6H+qIdNKLu"
    "4Cn9/bw5y9+ly5Ttxg3GtsB/w9swPQCUaxgzJrF3+/2vg6hggM140t/9Mqmh7aszrNsGfxfMwBxDkhRToZslpwhm/AsEpxAaJRQn"
    "tsiSt2WAHPkAS32AWprBhDsfoqXOorRHtEZmdSGUHZ6ONeNHG53FnnoY8IOCusLKnIpBpI+B34hwqXq24EURXHEZROm9RagXR5qA"
    "oXRglg/P6VCf1/kg/P6iUascUqlQ7SPgmTAtYsaRWsQQ9O5wNiF2j9NVq6S5dp7ExLqZodtNEGnmB9XGdEkeZeYuJMxL5ytGU7ty"
    "tF4jpnUBoC+/ZITitASp59DrYlE8mwGJU5EUJ3rQHjpS/3RIhJjBPcdc1VCBZ6vmbX5KLPBQL2u+j5SqnYnG6p2/Wl7lQaR86CQG"
    "tTR62m+sxmIspk6tqkJN6cnd0NqrccoVK+ZyBfUWF63kpilyEQyzDN6WqP/S3AbA2+P+PdcKii9cLEBs5p5WIrQpdq7yjwMKTeQy"
    "A7hxz0Ws0rFOcJ/YfFd1sEvBdF4F0/jAyK52uYvWm7PTd28xgBYfVvH08eGJjWsMjh5TC9xKinbH01PwPq4Ls8hucx6lMsJx9HGD"
    "BZ7R5zt6CR+JHn3Wd9hzIO3wS4SAQJCEwqDU8S+mmRXrG7qZfTNWVlZi/iVSfPSAdqvC4LvtlrB9amvLPeKnzTonrep1jXyqnn7U"
    "anjbUKfJltCMiKZ8/K49Hfi1VNyCwN2Zkc7MlfrxRX55A2I/ProNkutHBP0ljWQkDBt07WyEKQZzAW0uO3LUnZ/dne/oBt5Ce4Wa"
    "upWW++4Gq5FxIO3IxlAZsPLfmFdPjS5EeNQNfCZptIkH7rZDtbbVQ2razE37GjBdQuOnIQkzCtzvtqnUZXAaSRSxu6DKoagLZ5PM"
    "estsKWCJzeqVvaGSeGls6jpdr98R/9HxL+IAD/0IqDoanIOyocNc0MGqg0KPnWgVSV+yMs1TyuHR4ptukh6qobp6XEM7o/RmzxHA"
    "PTLpaSVXWhC8PdPXkaS/y6kWp2phKfZS1hT8tUoogwsr98JE7UIDkqecB9ftNUnwOdKWyt+w6c0EUa2CpaWeZFylzei/3nBW15Jj"
    "mRzVYAw3VWggg9hmVTkIRcfejI01HiFIUEd5z52D6MZWJ93F1NqUx93cjUC7WyEYVaXmHJQbtykb0F1r/wWs1gSDW2Me9ym1jUnu"
    "3SrHXbX5ke125LiRZeN0lnX41Spk0g8qFHwL3JOvURGAOnsQoSbjjd40FRMmWZW3FsRXimbX0DMtGsUzs/0GJAgVpmAaX2jeEh7y"
    "may761WBmdolRa16o++2WU4dz6ROLen11EEWcjeUMpnVY7IYHbtBxL5G7VgdJQ1XSTaFwL0BV+1GbHYnCz0a6wlG7y3K3Amj8l1a"
    "c5O7A9u8KE5yAuf+Cjel53bjU484yTGOqGhMUCBEFrp2lriKhhtrIBu1rnWFK9o1PCJkh8SAzgT0WoWrG0ydwdly5LZEB/zfoJ/j"
    "dY9+c63pHQrjG8rcjBI3wqxxCqaO1upkTXHQpXYs5n3RfoDjwGNiPLZXnfp6mwdkLlunv7rm+TRlUZ2qrZUkCx0khzZkTA2uOtIM"
    "o9uycQhtgyvFUaHGI/FNdW4cZjpvAeeYOeYRyU4TxjQr500YnwTkIR6QDP6qOCi0upUjpdvPksyET5jGzO46Y1SeNyh5E88EMuoH"
    "8eSePI54ofChTnKmvcNkDYNS5QX0I5Ndea4gHQUo9xqLDdHD6shi2i3dPrdYP54aCxqv+foWz4FTqBP1ilumo23GJoCTDpb4Ac/y"
    "nQc3cbbKXfM4YWQGrsRCZCurc6Y9xXe95qFNori163QpKYNF2bHR3JAMRwKpjSCWYpjHQRHORrJ0VmgBOlYKD1awfP/DKkjEAU4g"
    "S4131XM6WxqTkT3t6D8mB6Fj05VkcVp6XLLV9vhLVYCItt30akXxgs1oT6tg7U1gK0mgPBkB0wVCXHzeBp/k69vg6zInLj53raNI"
    "7jbxLdj0ngg3jwLYOOiuVEXFosbhBR0fywHdi04af6v2eOyZEAA1WDXxzRVR4pBx0f5y05xTdR7yJjDidScY2UKJQjVWuUCjxbUV"
    "XYRM3ocunfHBxpQMrnmNtpO993W5EwG5M18i3YJtwq18BdQPlckVf3TP4buHtjLP0fQkxDB0qtDhWXSaJkRv0BjMS5xypcnbx+X9"
    "rTqb00O1X2ALowEdBUrEDoRdyO0fBUp+/FHyexevIbYAzwGGqXgYX/ObthO7jZW2y0QXE6vB1pjZOlOc3/2mV03trkndf0Ldk5FP"
    "1TwM3RNmPfMgEO3kdnXap7zv9LoL7WB3eXJsjOkHXgzFkcjAzbR7HKtaaVmu+hc6th8GovugYvu5Gs7hyetTx/CZ9VF6DUD0bXPH"
    "XhXeqFBEjYIvYrX5A1eOjN2ImNdGMTFOZGgcf7p1J2LHNjZ5Tr/AFFkz0QdYOBq4fETX8rla3RyqRPuxeLBp846FuMbWmNmk4iy1"
    "44g9cz4rNYRDoFNp6hFIEugYu+9SOiVbvksMHmaLBR2vTf9oADHKIohTlIUbiW3FANOgiMP9LJ3FV3abY8g1XgTlyHpgSxQ6qgAk"
    "XOCaLoK8GFyqjWnUA3vBBiIXrf4Rk8oFxW/AnaE1UeJp/SNtEZ/ERN+ZqFX/Upe7lx31PiLPFNQRuDidRjtqQRuD+vdVGn1q6wR0"
    "iGpQ1dBrx+sEVSU6HrIDt9VRENIIBaqu4o4SJwgYMMc3os0nQVXs7YjDJKEnldHiiTZ0SgG1Rl7vQmBi6SloZI4Gu30NZ0Gdw1OL"
    "sH1nMzJ0PGwbmxzEPahrAFd7yBRxt3ciyietRj4n2LhmG3TuH1cVgp0bWsyVy6ssQ24vVgt7QOGinbuOWpSkU9XkEcHRsF3bGW2q"
    "7Iw21HXeYz/hfX6iztpQ9bhV+/l9e9XqRx1denNdbiXjPojwVET4bf4LF4U4FBhj7k3/pARVtyBxXOI1pIZTMYx+tJvoyfejLFS7"
    "Myql0ethuk8GncRfPulLiEAFgGJdeJi4s4UaxVviaqf3PxnpuLc="
)


def _d(b):
    return zlib.decompress(base64.b64decode("".join(b.split())))


_FILES = {
    "/plugin": (_d(_PAGE_B64), "text/html; charset=utf-8", None),
    "/p/sebbi_adapter.py": (_d(_ADAPTER_B64), "text/x-python; charset=utf-8", "sebbi_adapter.py"),
}

_ctx = {}
_ready = False
_patched = False
_loaded = False
_leaves = []            # leaf hashes (bytes), index = leaf index
_cache = {}             # (start, size) -> hash, for complete power-of-two subtrees
_tree_lock = threading.Lock()
_cp_lock = threading.Lock()
_loop_started = False


# ---------------------------------------------------------------- RFC 6962

def _h(b):
    return hashlib.sha256(b).digest()


def _leaf_hash(entry):
    return _h(b"\x00" + entry)


def _node(left, right):
    return _h(b"\x01" + left + right)


def _split(n):
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(start, n):
    """Merkle Tree Hash of leaves[start:start+n]."""
    if n == 0:
        return _h(b"")
    if n == 1:
        return _leaves[start]
    full = n >= 16 and (n & (n - 1)) == 0
    if full:
        hit = _cache.get((start, n))
        if hit is not None:
            return hit
    k = _split(n)
    out = _node(_mth(start, k), _mth(start + k, n - k))
    if full:
        _cache[(start, n)] = out
    return out


def _path(m, start, n):
    """Audit path for leaf m within leaves[start:start+n]."""
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, start, k) + [_mth(start + k, n - k)]
    return _path(m - k, start + k, n - k) + [_mth(start, k)]


def _subproof(m, start, n, b):
    if m == n:
        return [] if b else [_mth(start, n)]
    k = _split(n)
    if m <= k:
        return _subproof(m, start, k, b) + [_mth(start + k, n - k)]
    return _subproof(m - k, start + k, n - k, False) + [_mth(start, k)]


def _consistency(m, n):
    if m <= 0 or m >= n:
        return []
    return _subproof(m, 0, n, True)


# ---------------------------------------------------------------- storage

def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS ppa_leaf(idx INTEGER PRIMARY KEY,entry_hash TEXT NOT NULL,"
                  "leaf_hash TEXT NOT NULL,client TEXT,cid TEXT,ts REAL,UNIQUE(client,cid))")
        c.execute("CREATE INDEX IF NOT EXISTS ppa_leaf_entry ON ppa_leaf(entry_hash)")
        c.execute("CREATE TABLE IF NOT EXISTS ppa_sth(tree_size INTEGER PRIMARY KEY,root TEXT NOT NULL,"
                  "ts REAL,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _reload_locked(c):
    """Rebuild the in-memory tree from the database. Caller holds _ctx['lock']."""
    rows = c.execute("SELECT idx,leaf_hash FROM ppa_leaf ORDER BY idx").fetchall()
    fresh = []
    for i, (idx, lh) in enumerate(rows):
        if idx != i:
            raise RuntimeError("leaf index gap at %d" % i)
        fresh.append(bytes.fromhex(lh))
    _cache.clear()
    _leaves[:] = fresh


def _load():
    global _loaded
    if _loaded:
        return
    with _tree_lock:
        if _loaded:
            return
        with _ctx["lock"]:
            _reload_locked(_ctx["conn"])
        _loaded = True


def _seal(kind, detail, extra):
    ev = {"user_id": "ppa:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "public-proof-adapter", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "adapter_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _sth_rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _latest_sth():
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth ORDER BY tree_size DESC LIMIT 1")
    return _sth_dict(r[0]) if r else None


def _covering_sth(idx):
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth WHERE tree_size>? "
                  "ORDER BY tree_size ASC LIMIT 1", (idx,))
    return _sth_dict(r[0]) if r else None


def _sth_dict(r):
    return {"tree_size": r[0], "root": r[1],
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2] or 0)),
            "audit_hash": r[3], "block_index": r[4],
            "walk": SITE + "/x/walk/block?index=%s" % r[4] if r[4] is not None else None,
            "ts": r[2] or 0}


# ---------------------------------------------------------------- appends and checkpoints

def _append(client, items):
    """items: list of (entry_hex, cid or None). Returns list of (idx, entry_hex, replayed, error)."""
    for attempt in range(3):
        out = []
        with _ctx["lock"]:
            c = _ctx["conn"]
            top = c.execute("SELECT COALESCE(MAX(idx),-1) FROM ppa_leaf").fetchone()[0]
            if top + 1 != len(_leaves):
                _reload_locked(c)
            start_len = len(_leaves)
            try:
                for eh, cid in items:
                    if cid:
                        row = c.execute("SELECT idx,entry_hash FROM ppa_leaf WHERE client=? AND cid=?",
                                        (client, cid)).fetchone()
                        if row:
                            if row[1] != eh:
                                out.append((None, eh, False, "cid_reused_for_a_different_hash"))
                            else:
                                out.append((row[0], eh, True, None))
                            continue
                    idx = len(_leaves)
                    lh = _leaf_hash(bytes.fromhex(eh))
                    c.execute("INSERT INTO ppa_leaf(idx,entry_hash,leaf_hash,client,cid,ts) VALUES(?,?,?,?,?,?)",
                              (idx, eh, lh.hex(), client, cid or None, time.time()))
                    _leaves.append(lh)
                    out.append((idx, eh, False, None))
                c.commit()
                return out
            except sqlite3.IntegrityError:
                c.rollback()
                del _leaves[start_len:]
                _reload_locked(c)
            except Exception:
                c.rollback()
                del _leaves[start_len:]
                raise
    raise RuntimeError("could not append after retries")


def _checkpoint(force=False):
    """Seal the current tree head into the chain if it is due. Never runs twice at once."""
    if "conn" not in _ctx or not _cp_lock.acquire(blocking=False):
        return None
    try:
        _load()
        n = len(_leaves)
        last = _latest_sth()
        last_size = last["tree_size"] if last else 0
        if n == 0 or n == last_size:
            return last
        due = force or (n - last_size) >= CHECKPOINT_EVERY or \
            (time.time() - (last["ts"] if last else 0)) >= CHECKPOINT_SECONDS
        if not due:
            return last
        root = _mth(0, n).hex()
        ah, blk = _seal("tree_head", "size=%d;root=%s" % (n, root),
                        {"tree_size": n, "root": root, "prev_tree_size": last_size,
                         "log": "sebbi public proof log", "spec": "RFC6962-SHA256"})
        with _ctx["lock"]:
            _ctx["conn"].execute("INSERT OR IGNORE INTO ppa_sth(tree_size,root,ts,audit_hash,block_index) "
                                 "VALUES(?,?,?,?,?)", (n, root, time.time(), ah, blk))
            _ctx["conn"].commit()
        return _latest_sth()
    finally:
        _cp_lock.release()


def _loop():
    while True:
        time.sleep(10)
        try:
            _checkpoint()
        except Exception as e:
            print("plugin checkpoint: " + str(e)[:160], flush=True)


def _start_loop():
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, name="ppa-checkpoint", daemon=True).start()


# ---------------------------------------------------------------- receipts

def _anchoring_note(cp):
    if not cp:
        return ("pending: this leaf is covered by the next tree head, sealed into the chain within about "
                "%d seconds. Fetch /p/receipt?leaf=N again after that." % CHECKPOINT_SECONDS)
    return ("tree head sealed in chain block %s. The chain tip is timestamped in Bitcoin via OpenTimestamps; "
            "once a confirmed anchored tip is at or after that block, this leaf is Bitcoin-anchored. "
            "Check: %s/x/ots/latest_confirmed" % (cp["block_index"], SITE))


def _receipt(idx, size=None):
    _load()
    n = len(_leaves)
    if idx < 0 or idx >= n:
        return None
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT entry_hash FROM ppa_leaf WHERE idx=?", (idx,)).fetchone()
    cp = _covering_sth(idx) if size is None else None
    tsize = size if size is not None else (cp["tree_size"] if cp else n)
    tsize = max(idx + 1, min(tsize, n))
    root = _mth(0, tsize).hex()
    rec = {"log": "sebbi.pro public proof log", "spec": SPEC,
           "entry_hash": row[0] if row else None, "leaf_index": idx,
           "leaf_hash": _leaves[idx].hex(), "tree_size": tsize, "root": root,
           "audit_path": [p.hex() for p in _path(idx, 0, tsize)],
           "checkpoint": None, "anchoring": _anchoring_note(cp)}
    if cp:
        c2 = dict(cp)
        c2.pop("ts", None)
        c2["root_matches"] = (cp["root"] == root)
        rec["checkpoint"] = c2
    return rec


# ---------------------------------------------------------------- commands

def _meter(key, devices):
    """Count each distinct device on the key's monthly meter - the engine's own record_device()."""
    key = str(key or "").strip()
    devices = [d for d in dict.fromkeys(devices) if d and CID_RE.match(d)]
    if not key or not devices:
        return None
    rd = _server_fn("record_device")
    n = None
    for d in devices:
        dev_id = "adapter:" + d
        if rd:
            try:
                n = rd(key, dev_id)
                continue
            except Exception:
                pass
        try:
            with _ctx["lock"]:
                c = _ctx["conn"]
                c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                          (key, dev_id, time.time()))
                c.commit()
                n = c.execute("SELECT COUNT(*) FROM device_seen WHERE api_key=?", (key,)).fetchone()[0]
        except Exception:
            try:
                _ctx["conn"].rollback()
            except Exception:
                pass
    return n


TRIAL_DAYS = 90


def _server_fn(name):
    """Borrow a function from the running server (server.py) if it is there."""
    for modname in ("__main__", "server"):
        m = sys.modules.get(modname)
        fn = getattr(m, name, None) if m else None
        if callable(fn):
            return fn
    return None


def _trial_gate(key):
    """None if the key may submit; otherwise the same 402 answer the engine gives at trial end."""
    try:
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT email,is_paid,created,product FROM api_keys WHERE key=?",
                                       (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    email, is_paid, created, product = row
    ts = _server_fn("trial_state")
    in_trial = ts(created, is_paid)[0] if ts else (bool(is_paid) or time.time() - (created or 0) <= TRIAL_DAYS * 86400)
    if in_trial:
        return None
    dc = _server_fn("device_count")
    tc = _server_fn("trial_checkout")
    try:
        devices = dc(key) if dc else None
    except Exception:
        devices = None
    try:
        url = tc(key, email, product or "aileash") if tc else SITE + "/#signup"
    except Exception:
        url = SITE + "/#signup"
    return {"error": "trial_expired",
            "message": "Your 90-day free trial has ended. Your receipts, proofs and queued fingerprints are "
                       "untouched - pay to continue exactly where you left off. The bill is 50p for each real "
                       "device that used your key.",
            "billable_devices": devices, "rate_per_device_gbp": 0.50, "checkout_url": url}


def _client_for(key):
    key = str(key or "").strip()
    if key:
        try:
            with _ctx["lock"]:
                row = _ctx["conn"].execute("SELECT active FROM api_keys WHERE key=?", (key,)).fetchone()
        except Exception:
            row = None
        if row and row[0] in (1, None):
            return "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "open" if OPEN else None


# ---------------------------------------------------------------- sign-up, account, payment

_signups = {}
_signup_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _welcome_html(name, key, trial_ends):
    k = _esc(key)
    return ("<div style='font-family:Arial,sans-serif;max-width:560px;color:#1f2937'>"
            "<h2 style='color:#0b1220'>Your sebbi.pro plug-in key</h2>"
            "<p>Hi " + _esc(name or "there") + ", your key is below. Keep it private.</p>"
            "<p style='font-family:monospace;font-size:15px;background:#f1f5f9;padding:12px;border-radius:8px;"
            "word-break:break-all'>" + k + "</p>"
            "<h3>Plug it in</h3><ol>"
            "<li>Download the adapter: <a href='" + SITE + "/p/sebbi_adapter.py'>" + SITE + "/p/sebbi_adapter.py</a></li>"
            "<li>Set <code>SEBBI_API_KEY=" + k + "</code></li>"
            "<li>Add <code>@anchor_state(\"orders.update\", device=\"handset\")</code> above any function "
            "that changes something important.</li></ol>"
            "<p>Other languages, your account and your bill: <a href='" + SITE + "/plugin'>" + SITE + "/plugin</a></p>"
            "<p><b>Free until " + _esc(trial_ends) + "</b>, then 50p per device per month - every phone, till "
            "or machine you record for, counted once a month.</p>"
            "<p style='color:#64748b;font-size:13px'>Questions: justrightdecorators@gmail.com</p></div>")


def _send_mail(to, name, subject, html):
    fn = _server_fn("send_email")
    if fn:
        threading.Thread(target=fn, args=(to, name or "", subject, html), daemon=True).start()
        return True
    return False


def _trial_end(created):
    return time.strftime("%d %B %Y", time.gmtime((created or time.time()) + TRIAL_DAYS * 86400))


def c_signup(q, body, key, ip=""):
    email = str(body.get("email") or "").strip().lower()
    name = str(body.get("name") or "").strip()[:80]
    org = str(body.get("org") or "").strip()[:120]
    if not EMAIL_RE.match(email):
        return {"error": "invalid_email", "message": "Please enter a valid email address."}, 400
    now = time.time()
    with _signup_lock:
        hits = [t for t in _signups.get(ip, []) if now - t < 3600]
        if len(hits) >= 5:
            return {"error": "slow_down", "message": "Too many sign-ups from here. Try again in an hour."}, 429
        hits.append(now)
        _signups[ip] = hits
    create = _server_fn("create_key")
    if not create:
        return {"error": "unavailable", "message": "Sign-up isn't available just now."}, 503
    new_key, err = create(email, "", name, org, "plugin", "aileash", 1)
    if err == "email_exists":
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT key,name,created FROM api_keys WHERE email=? AND product='aileash'",
                                       (email,)).fetchone()
        if row:
            _send_mail(email, row[1] or name, "Your sebbi.pro key", _welcome_html(row[1] or name, row[0], _trial_end(row[2])))
        return {"error": "email_exists",
                "message": "That email already has a sebbi.pro key. We've emailed it to you - the same key works here."}, 409
    if err or not new_key:
        return {"error": err or "failed", "message": "Couldn't create a key just now."}, 400
    ends = _trial_end(now)
    _send_mail(email, name, "Your sebbi.pro plug-in key", _welcome_html(name, new_key, ends))
    _send_mail("justrightdecorators@gmail.com", "sebbi.pro", "New plug-in sign-up: " + (org or email),
               "<p>New plug-in customer: " + _esc(name) + " &middot; " + _esc(email) + " &middot; " + _esc(org) + "</p>")
    return {"key": new_key, "trial_ends": ends, "rate_per_device_gbp": 0.50}, 200


def _key_row(key):
    key = str(key or "").strip()
    if not key:
        return None
    try:
        with _ctx["lock"]:
            return _ctx["conn"].execute("SELECT email,is_paid,created,product,stripe_customer,active FROM api_keys "
                                        "WHERE key=?", (key,)).fetchone()
    except Exception:
        return None


def _devices_this_month(key):
    m = sys.modules.get("modules.meter") or sys.modules.get("meter")
    if m is not None and hasattr(m, "month_count"):
        try:
            return m.month_count(key)
        except Exception:
            pass
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else 0
    except Exception:
        return 0


def _billable(key):
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else _devices_this_month(key)
    except Exception:
        return _devices_this_month(key)


def c_account(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    ts = _server_fn("trial_state")
    in_trial, left = ts(created, is_paid) if ts else (time.time() - (created or 0) <= TRIAL_DAYS * 86400,
                                                       max(0, TRIAL_DAYS - int((time.time() - (created or 0)) // 86400)))
    billable = _billable(key)
    client = "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    rows = _sth_rows("SELECT COUNT(*) FROM ppa_leaf WHERE client=?", (client,))
    return {"email_hint": (email[:2] + "***" + email[email.find("@"):]) if email and "@" in email else "",
            "paid": bool(is_paid), "in_trial": bool(in_trial) and not is_paid,
            "trial_days_left": None if is_paid else left, "trial_ends": _trial_end(created),
            "devices_this_month": _devices_this_month(key), "billable_devices": billable,
            "monthly_bill_gbp": round(billable * 0.50, 2), "rate_per_device_gbp": 0.50,
            "records_logged": rows[0][0] if rows else 0, "active": bool(active)}, 200


def c_pay(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    if is_paid and cust:
        call = _server_fn("stripe_call")
        r = call("POST", "/billing_portal/sessions", {"customer": cust, "return_url": SITE + "/plugin#account"}) if call else None
        if r and r.get("url"):
            return {"url": r["url"]}, 200
        return {"error": "portal_unavailable", "message": "Your account is paid. To change billing, email "
                                                         "justrightdecorators@gmail.com."}, 200
    tc = _server_fn("trial_checkout")
    if not tc:
        return {"error": "unavailable", "message": "Payments aren't available just now."}, 503
    try:
        url = tc(key, email, product or "aileash")
    except Exception:
        url = None
    if not url or "stripe.com" not in url:
        return {"error": "unavailable", "message": "Payments aren't available just now - try again shortly."}, 503
    return {"url": url}, 200


def c_submit(q, body, key):
    client = _client_for(key)
    if not client:
        return {"error": "api_key_required",
                "message": "Send your sebbi.pro API key in the X-Sebbi-Key header."}, 401
    if client != "open":
        gate = _trial_gate(str(key).strip())
        if gate:
            return gate, 402
    raw = body.get("items")
    if raw is None and body.get("hashes") is not None:
        raw = [{"hash": h} for h in body.get("hashes") or []]
    if raw is None and body.get("hash") is not None:
        raw = [{"hash": body.get("hash"), "cid": body.get("cid")}]
    if not isinstance(raw, list) or not raw:
        return {"error": "nothing_to_submit", "message": 'Send {"items":[{"hash":"<64 hex>","cid":"..."}]}'}, 400
    if len(raw) > MAX_ITEMS:
        return {"error": "too_many", "max_items": MAX_ITEMS}, 413
    items, bad, devs = [], [], []
    install = str(body.get("device") or "").strip()
    for i, it in enumerate(raw):
        it = it if isinstance(it, dict) else {"hash": it}
        h = str(it.get("hash") or "").strip().lower()
        cid = str(it.get("cid") or "").strip() or None
        dev = str(it.get("device") or "").strip() or install
        if not HEX64.match(h):
            bad.append({"position": i, "error": "hash must be 64 hex characters (SHA-256)"})
        elif cid and not CID_RE.match(cid):
            bad.append({"position": i, "error": "cid must be 1-80 letters, numbers, _ . : -"})
        elif dev and not CID_RE.match(dev):
            bad.append({"position": i, "error": "device must be 1-80 letters, numbers, _ . : -"})
        else:
            items.append((h, cid))
            devs.append(dev)
    if bad:
        return {"error": "bad_items", "items": bad}, 400
    _load()
    devices = _meter(key, devs) if client != "open" else None
    placed = _append(client, items)
    n = len(_leaves)
    last = _latest_sth()
    if n - (last["tree_size"] if last else 0) >= CHECKPOINT_EVERY:
        threading.Thread(target=_checkpoint, daemon=True).start()
    receipts = []
    for (idx, eh, replayed, err), (_, cid) in zip(placed, items):
        if err:
            receipts.append({"cid": cid, "entry_hash": eh, "error": err})
            continue
        r = _receipt(idx, size=n)
        r["cid"] = cid
        r["replayed"] = replayed
        r["anchoring"] = _anchoring_note(None)
        receipts.append(r)
    return {"accepted": sum(1 for r in receipts if "error" not in r), "tree_size": n,
            "devices_this_month": devices,
            "root": _mth(0, n).hex(), "receipts": receipts}, 200


def _int(q, name, default=None):
    try:
        return int(str(q.get(name, default)))
    except (TypeError, ValueError):
        return None


def c_receipt(q, body, key):
    idx = _int(q, "leaf")
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx)
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_proof(q, body, key):
    idx, size = _int(q, "leaf"), _int(q, "size", 0)
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx, size=size or len(_leaves))
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_consistency(q, body, key):
    _load()
    m, n = _int(q, "first"), _int(q, "second", len(_leaves))
    if m is None or n is None or m < 1 or m > n or n > len(_leaves):
        return {"error": "need 1 <= first <= second <= tree size", "tree_size": len(_leaves)}, 400
    return {"first": m, "second": n, "first_root": _mth(0, m).hex(), "second_root": _mth(0, n).hex(),
            "proof": [p.hex() for p in _consistency(m, n)], "spec": SPEC}, 200


def c_sth(q, body, key):
    _load()
    last = _latest_sth()
    if last:
        last.pop("ts", None)
    return {"tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "spec": SPEC}, 200


def c_find(q, body, key):
    h = str(q.get("hash") or "").strip().lower()
    if not HEX64.match(h):
        return {"error": "hash must be 64 hex characters"}, 400
    rows = _sth_rows("SELECT idx FROM ppa_leaf WHERE entry_hash=? ORDER BY idx LIMIT 50", (h,))
    return {"entry_hash": h, "leaf_indexes": [r[0] for r in rows]}, 200


def c_index(q, body, key):
    return {"log": "sebbi.pro public proof log", "version": VERSION, "spec": SPEC,
            "submit": "POST " + SITE + "/p/submit with X-Sebbi-Key",
            "check": ["GET " + SITE + "/p/receipt?leaf=N", "GET " + SITE + "/p/consistency?first=M&second=N",
                      "GET " + SITE + "/p/sth"],
            "hash_only": True}, 200


GETS = {"receipt": c_receipt, "proof": c_proof, "consistency": c_consistency, "sth": c_sth,
        "find": c_find, "": c_index}
POSTS = {"submit": c_submit, "signup": c_signup, "account": c_account, "pay": c_pay}


# ---------------------------------------------------------------- transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _run(h, method):
    u = urllib.parse.urlparse(h.path)
    name = u.path[3:].strip("/").lower()
    table = GETS if method == "GET" else POSTS
    if name not in table:
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/plugin/status once"}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            _send(h, {"error": "body_too_large", "max_bytes": MAX_BODY}, 413)
            return True
        try:
            body = json.loads(h.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if not isinstance(body, dict):
                body = {}
        except Exception:
            _send(h, {"error": "bad_json"}, 400)
            return True
    key = h.headers.get("X-Sebbi-Key") or body.get("key") or q.get("key")
    try:
        if name == "signup":
            ip = (h.headers.get("X-Forwarded-For") or h.client_address[0] or "").split(",")[0].strip()
            out, code = c_signup(q, body, key, ip)
        else:
            out, code = table[name](q, body, key)
    except Exception as e:
        out, code = {"error": "failed", "detail": str(e)[:160]}, 500
    _send(h, out, code)
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
        _setup()
        _load()
        _start_loop()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_ppa_patched", False):
        _patched = True
        return True
    og, op, oo = cls.do_GET, getattr(cls, "do_POST", None), getattr(cls, "do_OPTIONS", None)

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype, fname = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if fname:
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return
        if (self.path == "/p" or self.path.startswith("/p/")) and _run(self, "GET"):
            return
        return og(self)

    def do_POST(self):
        if self.path.startswith("/p/") and _run(self, "POST"):
            return
        return op(self) if op else None

    def do_OPTIONS(self):
        if self.path.startswith("/p/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return oo(self) if oo else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls.do_OPTIONS = do_OPTIONS
    cls._ppa_patched = True
    _patched = True
    return True


def _flat(d):
    if not isinstance(d, dict):
        return {}
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in d.items()}


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    action = (action or "status").strip("/").lower()
    data = _flat(data)
    if "conn" in _ctx and action in POSTS and method == "POST":
        return POSTS[action](data, data, api_key or data.get("key"))
    if "conn" in _ctx and action in GETS and action not in ("",):
        return GETS[action](data, data, api_key)
    last = _latest_sth() if "conn" in _ctx else None
    if last:
        last.pop("ts", None)
    return {"module": "plugin", "version": VERSION, "armed": armed,
            "aliases": ALIASES, "tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "checkpoint_every_leaves": CHECKPOINT_EVERY,
            "open_submissions": OPEN, "spec": SPEC,
            "pages": sorted(_FILES.keys()),
            "endpoints": ["POST /p/submit", "/p/receipt", "/p/proof", "/p/consistency", "/p/sth", "/p/find"]}, 200


def register(MODULE_MAP):
    """For name-based loaders: map this module under its own name and its aliases."""
    mod = sys.modules[__name__]
    for name in ["plugin"] + ALIASES:
        MODULE_MAP.setdefault(name, mod)
    return MODULE_MAP

```


## `modules/praxis.py`

697 lines, 24699 bytes

```python
"""
modules/praxis.py  v1.0.2

Outbound submitter for the PRAXIS external-witness observe endpoint (chain 4).

Contract implemented against the SERVED schema route, not prose:
    GET  https://chain4.thepraesidium.ai/api/external-witness/observe/schema
    POST https://chain4.thepraesidium.ai/api/external-witness/observe

Signing:
    preimage  = b"PRAXIS-OBSERVE-v1\\n" + canonical JSON of the envelope
                with the "signature" field REMOVED
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    signature = lowercase hex HMAC-SHA256, carried in the body

Secret:
    environment variable PRAXIS_OBSERVE_SECRET
    (never written to a file, never returned by any route)

Routes
    GET  /x/praxis/spec      public   what this module does and how it signs
    GET  /x/praxis/status    public   config check + arms the /praxis page
    GET  /x/praxis/schema    public   fetches THEIR live contract, reports version
    GET  /x/praxis/history   keyed    past attempts from our own chain
    POST /x/praxis/canonical keyed    dry run: envelope, preimage, signature, NO send
    POST /x/praxis/submit    keyed    signs and sends ONE bounded submission

v1.0.1 fixes a real fault found on 7 Sep 2026. _seal called the host seal()
with one argument when it requires three, so every submit reported
sealed:false while the response still said ok:true. A remote call was being
recorded by the peer with no matching entry in our own chain. A failed seal
now makes the whole response ok:false and says so at the top level.

v1.0.2 fixes the follow-on. The host seal() returns a tuple
(audit_hash, block_index, key_seq); v1.0.1 only read dicts and strings and
so reported a successful seal as "seal returned no hash".
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

VERSION = "1.0.2"

# ---------------------------------------------------------------- constants

BASE = "https://chain4.thepraesidium.ai"
OBSERVE_URL = BASE + "/api/external-witness/observe"
SCHEMA_URL = BASE + "/api/external-witness/observe/schema"

DOMAIN = b"PRAXIS-OBSERVE-v1\n"
ENVELOPE_SCHEMA = "praxis_external_observe_request_v1"

OUR_PEER_ID = "aileash"
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"

SECRET_ENV = "PRAXIS_OBSERVE_SECRET"

TIMEOUT = 20
MAX_RESPONSE_BYTES = 262144

PUBLIC = {
    ("GET", "spec"),
    ("GET", "status"),
    ("GET", "schema"),
}


# ---------------------------------------------------------------- helpers

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def _secret():
    s = os.environ.get(SECRET_ENV, "")
    return s.strip()


def _fresh_nonce():
    # matches ^[A-Za-z0-9_.:-]{12,128}$
    return secrets.token_hex(20)


def _fresh_idem():
    # matches ^[0-9a-f]{64}(\.attempt-N)?$
    return secrets.token_hex(32)


def _http(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "AILeash-praxis/" + VERSION)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_RESPONSE_BYTES)
            return r.status, dict(r.headers), raw, None
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read(MAX_RESPONSE_BYTES)
        except Exception:
            pass
        return e.code, dict(getattr(e, "headers", {}) or {}), raw, None
    except Exception as e:
        return 0, {}, b"", "%s: %s" % (type(e).__name__, e)


def _parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _build_envelope(tip_digest, witnessed_peer_id, source_url,
                    receipt_digest=None, attempt=None, observed_at=None):
    payload = {
        "witnessed_peer_id": witnessed_peer_id,
        "data_class": "HASH_ONLY",
        "tip_digest": tip_digest,
        "source_url": source_url,
        "observed_at": observed_at or _now_iso(),
    }
    # receipt_digest is OPTIONAL in contract v1_1 and is omitted for a pure
    # chain-tip observation. Never duplicate tip_digest into it.
    if receipt_digest:
        payload["receipt_digest"] = receipt_digest

    key = _fresh_idem()
    if attempt:
        key = "%s.attempt-%s" % (key, attempt)

    return {
        "schema_version": ENVELOPE_SCHEMA,
        "peer_id": OUR_PEER_ID,
        "ts": _now_iso(),
        "nonce": _fresh_nonce(),
        "idempotency_key": key,
        "payload": payload,
    }


def _sign(envelope, secret):
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    canonical = _canonical(unsigned)
    preimage = DOMAIN + canonical
    sig = hmac.new(secret.encode("utf-8"), preimage, hashlib.sha256).hexdigest()
    return canonical, preimage, sig


def _validate(tip_digest, witnessed_peer_id, source_url, receipt_digest):
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", tip_digest or ""):
        return "tip_digest must be 64 lowercase hex characters"
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{2,63}", witnessed_peer_id or ""):
        return "witnessed_peer_id must match ^[a-z][a-z0-9_.:-]{2,63}$"
    if not (source_url or "").startswith("https://") or (source_url or "").count("/") < 3:
        return "source_url must be an https URL with a path"
    if len(source_url) > 512:
        return "source_url exceeds 512 characters"
    if receipt_digest and not re.fullmatch(r"[0-9a-f]{64}", receipt_digest):
        return "receipt_digest, if supplied, must be 64 lowercase hex characters"
    if receipt_digest and receipt_digest == tip_digest:
        return "receipt_digest must not duplicate tip_digest"
    return None


def _record_seal_result(out, res):
    """Read whatever the host seal() handed back.

    This deployment's seal() returns a TUPLE: (audit_hash, block_index,
    key_seq). v1.0.1 only understood dicts and strings, so a successful seal
    was reported as "seal returned no hash". Tuples are handled first.
    """
    if isinstance(res, (tuple, list)):
        if len(res) > 0:
            out["audit_hash"] = res[0]
        if len(res) > 1:
            out["block_index"] = res[1]
        if len(res) > 2:
            out["key_seq"] = res[2]
    elif isinstance(res, dict):
        out["audit_hash"] = (res.get("audit_hash") or res.get("hash")
                             or res.get("seal") or res.get("block_hash"))
        out["block_index"] = res.get("block_index") or res.get("index")
        out["key_seq"] = res.get("key_seq") or res.get("seq")
    elif isinstance(res, str):
        out["audit_hash"] = res
    out["sealed"] = bool(out["audit_hash"])
    return out


def _seal(ctx, event):
    """Seal into our own chain.

    The host seal() takes three positional arguments (event, result, ts).
    v1.0.0 called it with one and every submit failed silently. We try the
    three-argument form first and fall back only if the host is older, and
    we record which call shape worked so this is never guesswork again.
    """
    out = {"sealed": False, "audit_hash": None, "error": None,
           "call_shape": None}
    sealer = ctx.get("seal")
    if not sealer:
        out["error"] = "no seal function in ctx"
        return out

    result_value = event.get("result") or "sent"
    ts_value = event.get("ts") or _now_iso()

    attempts = [
        ("seal(event, result, ts)", lambda: sealer(event, result_value, ts_value)),
        ("seal(event, result)", lambda: sealer(event, result_value)),
        ("seal(event)", lambda: sealer(event)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            res = call()
        except TypeError as e:
            errors.append("%s -> TypeError: %s" % (shape, e))
            continue
        except Exception as e:
            out["error"] = "%s -> %s: %s" % (shape, type(e).__name__, e)
            out["call_shape"] = shape
            return out
        out["call_shape"] = shape
        _record_seal_result(out, res)
        if not out["sealed"]:
            out["error"] = "seal returned no hash"
        return out

    out["error"] = "no accepted call shape; " + " | ".join(errors)
    return out


# ---------------------------------------------------------------- page

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>PRAXIS submit</title>
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--ink);color:#e8ecf5;
     font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1{font-size:18px;margin:0 0 4px;color:var(--gold)}
p.sub{margin:0 0 18px;color:#8b96ad;font-size:13px}
label{display:block;margin:12px 0 4px;font-size:12px;color:#8b96ad;
      text-transform:uppercase;letter-spacing:.06em}
input{width:100%;padding:11px;background:var(--ink2);border:1px solid #24304e;
      border-radius:8px;color:#e8ecf5;font:14px monospace}
input:focus{outline:none;border-color:var(--gold)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
button{flex:1;min-width:120px;padding:13px;border:0;border-radius:8px;
       background:var(--gold);color:#0a0f1e;font-weight:600;font-size:15px}
button.alt{background:var(--ink2);color:#e8ecf5;border:1px solid #24304e}
button:disabled{opacity:.45}
pre{margin-top:16px;padding:12px;background:var(--ink2);border:1px solid #24304e;
    border-radius:8px;white-space:pre-wrap;word-break:break-all;
    font:12px/1.45 monospace;max-height:60vh;overflow:auto}
.ok{color:var(--ok)}.err{color:var(--err)}
</style></head><body>

<h1>PRAXIS observe &mdash; chain 4</h1>
<p class="sub">Signs one bounded submission and sends it. Fresh ts, nonce and
idempotency key every press.</p>

<label>API key</label>
<input id="key" type="password" placeholder="AILeash API key" autocomplete="off">

<label>Tip digest (64 hex)</label>
<input id="tip" placeholder="press Load tip">

<label>Witnessed peer id</label>
<input id="wpid" value="aileash">

<label>Source URL</label>
<input id="src" value="https://sebbi.pro/x/witness/tip">

<label>Attempt marker (optional)</label>
<input id="att" placeholder="leave blank for a first attempt">

<div class="row">
  <button class="alt" onclick="loadTip()">Load tip</button>
  <button class="alt" onclick="theirSchema()">Their schema</button>
</div>
<div class="row">
  <button class="alt" onclick="go('canonical')">Dry run</button>
  <button onclick="send()">Send</button>
</div>

<pre id="out">Ready.</pre>

<script>
var out = document.getElementById('out');
function show(t, cls){ out.className = cls || ''; out.textContent = t; }
function val(id){ return document.getElementById(id).value.trim(); }

function loadTip(){
  show('Loading our tip...');
  fetch('/x/witness/tip').then(function(r){ return r.json(); }).then(function(j){
    var t = j.tip || j.hash || j.head || j.chain_tip || j.latest || '';
    document.getElementById('tip').value = t;
    show('Tip loaded.\\n\\n' + JSON.stringify(j, null, 2), 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function theirSchema(){
  show('Fetching their live contract...');
  fetch('/x/praxis/schema').then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.receipt_digest_required ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function body(){
  return {
    tip_digest: val('tip'),
    witnessed_peer_id: val('wpid'),
    source_url: val('src'),
    attempt: val('att') || null
  };
}

function go(action){
  var k = val('key');
  if(!k){ show('API key required.', 'err'); return; }
  show('Working...');
  fetch('/x/praxis/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + k },
    body: JSON.stringify(body())
  }).then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.ok === false ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function send(){
  if(!confirm('Send one bounded submission to chain 4 now?')) return;
  go('submit');
}
</script>
</body></html>"""


def _install_page():
    """Serve /praxis by wrapping the running handler's do_GET, once."""
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            names = dir(mod)
        except Exception:
            continue
        for name in names:
            try:
                obj = getattr(mod, name, None)
            except Exception:
                continue
            if not isinstance(obj, type):
                continue
            if not (hasattr(obj, "do_GET") and hasattr(obj, "do_POST")):
                continue
            if getattr(obj, "_praxis_patched", False):
                return True
            original = obj.do_GET

            def patched(self, _original=original):
                try:
                    path = self.path.split("?")[0].rstrip("/")
                except Exception:
                    path = ""
                if path == "/praxis":
                    data = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Robots-Tag", "noindex")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return _original(self)

            obj.do_GET = patched
            obj._praxis_patched = True
            return True
    return False


# ---------------------------------------------------------------- actions

def _spec():
    return {
        "module": "praxis",
        "version": VERSION,
        "what_this_is": (
            "Outbound submitter for the PRAXIS external-witness observe "
            "endpoint. One bounded submission per press. This module sends; "
            "it does not receive."
        ),
        "target": {"observe": OBSERVE_URL, "schema": SCHEMA_URL},
        "signing": {
            "algorithm": "hmac-sha256",
            "domain": "PRAXIS-OBSERVE-v1\\n",
            "canonicalization": "sort_keys=true, separators=(',',':'), ensure_ascii=true, utf-8",
            "preimage": "domain bytes + canonical JSON of the envelope with 'signature' removed",
            "signature_encoding": "lowercase hex",
            "auth_transport": "body, not headers",
        },
        "payload_policy": (
            "receipt_digest is optional under their contract v1_1 and is "
            "omitted for a pure chain-tip observation. It is never filled "
            "with a duplicate of tip_digest or a placeholder."
        ),
        "freshness": "fresh ts, fresh nonce and a fresh idempotency key on every submit",
        "seal_policy": (
            "a submit that reaches the peer but fails to seal into our own "
            "chain returns ok:false with seal_failed true. The send is still "
            "reported in full, because it happened and the peer may hold a "
            "durable record of it."
        ),
        "not_claimed": [
            "this lane is one-directional and does not establish mutual witnessing",
            "their acceptance is a transport and signature outcome, not verification "
            "of anything in our chain",
        ],
        "routes": {
            "public": ["GET spec", "GET status", "GET schema"],
            "keyed": ["GET history", "POST canonical", "POST submit"],
        },
    }


def _status():
    installed = _install_page()
    s = _secret()
    return {
        "module": "praxis",
        "version": VERSION,
        "page": "/praxis",
        "page_installed": installed,
        "peer_id": OUR_PEER_ID,
        "secret_configured": bool(s),
        "secret_env": SECRET_ENV,
        "secret_length": len(s) if s else 0,
        "target": OBSERVE_URL,
        "note": (
            "secret_configured false means the environment variable is not set "
            "on this replica; the secret itself is never returned by any route"
        ),
    }


def _their_schema():
    code, headers, raw, err = _http("GET", SCHEMA_URL)
    if err:
        return {"ok": False, "error": "fetch_failed", "detail": err}, 502
    doc = _parse_json(raw)
    if doc is None:
        return {"ok": False, "error": "unparseable", "status": code}, 502

    req = (((doc.get("request_schema") or {}).get("properties") or {})
           .get("payload") or {})
    required = req.get("required") or []
    hdr = {}
    for k, v in (headers or {}).items():
        if k.lower().startswith("x-praxis") or k.lower() == "cache-control":
            hdr[k.lower()] = v

    return {
        "ok": True,
        "fetched_at": _now_iso(),
        "http_status": code,
        "contract_version": doc.get("schema_version"),
        "payload_required": required,
        "receipt_digest_required": "receipt_digest" in required,
        "canonicalization": ((doc.get("signing") or {}).get("canonicalization")),
        "domain": ((doc.get("signing") or {}).get("domain")),
        "clock_skew_seconds": ((doc.get("freshness") or {}).get("clock_skew_seconds")),
        "headers": hdr,
        "body_sha256": _sha256_hex(raw),
    }, 200


def _canonical_action(data):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig

    return {
        "ok": True,
        "dry_run": True,
        "sent": False,
        "envelope": signed,
        "canonical_json": canonical.decode("utf-8"),
        "canonical_sha256": _sha256_hex(canonical),
        "preimage_sha256": _sha256_hex(preimage),
        "signature": sig,
        "note": "nothing was sent; ts, nonce and idempotency_key here are "
                "single-use and will be regenerated on an actual submit",
    }, 200


def _submit(data, ctx):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig
    wire = _canonical(signed)

    started = time.time()
    code, headers, raw, err = _http("POST", OBSERVE_URL, wire)
    took = round(time.time() - started, 3)

    parsed = _parse_json(raw)
    transport_ok = err is None and code in (200, 202)
    result = {
        "ok": transport_ok,
        "sent": err is None,
        "took_seconds": took,
        "http_status": code,
        "transport_error": err,
        "request": {
            "idempotency_key": env["idempotency_key"],
            "nonce": env["nonce"],
            "ts": env["ts"],
            "peer_id": env["peer_id"],
            "payload": env["payload"],
            "signature": sig,
            "canonical_sha256": _sha256_hex(canonical),
            "wire_sha256": _sha256_hex(wire),
            "wire_bytes": len(wire),
        },
        "response": {
            "body": parsed,
            "raw_sha256": _sha256_hex(raw) if raw else None,
            "raw_bytes": len(raw),
            "raw_text": (raw.decode("utf-8", "replace")[:4000] if raw else None),
        },
    }

    if isinstance(parsed, dict):
        result["their_error"] = parsed.get("error")
        result["their_accepted"] = parsed.get("accepted")
        result["their_replayed"] = parsed.get("replayed")
        result["their_request_digest"] = parsed.get("request_digest")
        result["their_durable_event_recorded"] = parsed.get("durable_event_recorded")
        result["their_accepted_decision_recorded"] = parsed.get(
            "accepted_decision_recorded")

    event = {
        "user_id": "praxis:" + OUR_PEER_ID,
        "event": "praxis_observe_submit",
        "kind": "praxis_observe_submit",
        "ts": _now_iso(),
        "target": OBSERVE_URL,
        "idempotency_key": env["idempotency_key"],
        "request_wire_sha256": result["request"]["wire_sha256"],
        "http_status": code,
        "response_sha256": result["response"]["raw_sha256"],
        "their_error": result.get("their_error"),
        "their_accepted": result.get("their_accepted"),
        "result": "sent" if err is None else "transport_error",
    }
    result["our_seal"] = _seal(ctx, event)

    # A send that the peer accepted but our own chain has no entry for is a
    # failure of this deployment, not a success. Say so at the top level.
    if not result["our_seal"].get("sealed"):
        result["ok"] = False
        result["seal_failed"] = True
        result["seal_failed_note"] = (
            "the submission reached the peer but was NOT sealed into our "
            "chain. The peer may hold a durable record with no counterpart "
            "here. Do not treat this submission as evidenced on our side."
        )

    if not transport_ok:
        status = 502 if err else 200
    elif not result["our_seal"].get("sealed"):
        status = 500
    else:
        status = 200
    return result, status


def _history(ctx, data):
    limit = 20
    try:
        limit = max(1, min(100, int(data.get("limit") or 20)))
    except Exception:
        pass
    rows = []
    try:
        conn = ctx.get("conn")
        lock = ctx.get("lock")
        sql = ("SELECT rowid, * FROM audit_log "
               "WHERE user_id = ? ORDER BY rowid DESC LIMIT ?")
        if lock:
            with lock:
                cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return {"ok": False, "error": "query_failed",
                "detail": "%s: %s" % (type(e).__name__, e)}, 500
    return {"ok": True, "count": len(rows), "rows": rows}, 200


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "status":
        return _status(), 200

    if method == "GET" and action == "schema":
        return _their_schema()

    if method == "GET" and action == "history":
        return _history(ctx, data)

    if method == "POST" and action == "canonical":
        return _canonical_action(data)

    if method == "POST" and action == "submit":
        return _submit(data, ctx)

    return {"ok": False, "error": "unknown_action", "action": action,
            "available": ["spec", "status", "schema", "history",
                          "canonical", "submit"]}, 404

```
