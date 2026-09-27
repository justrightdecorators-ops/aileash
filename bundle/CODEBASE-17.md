# Codebase — part 17 of 45

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

1270 lines, 67505 bytes

```python
"""
modules/plugin.py  v3.0.0
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
    POST /p/decide            (3.0.0) permission before acting: the sebbi.pro engine
                              decides ALLOW / CHALLENGE / BLOCK, sealed in the chain

Permission before, proof after (3.0.0): /p/decide runs the engine's own govern()
- trust, velocity, amount, country shift, device risk - and seals every decision
in the chain. Limits per key: 60 decisions a minute on trial, 1,200 a minute on
a paid key (PLUGIN_DECIDE_TRIAL_PER_MIN / PLUGIN_DECIDE_PAID_PER_MIN). The device
is metered with the same id the log uses, so a device that is both governed and
recorded counts once. Customer ids arrive already one-way hashed.

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

VERSION = "3.0.0"
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
    "6lTp/FD9BZtD/h8C7P0fi7Sq8Q=="
)
_ADAPTER_B64 = (
    "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"
    "RvGSqDrq/X9IKHBi"
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
            "records_logged": rows[0][0] if rows else 0,
            "decisions_today": _decisions.get((client, time.strftime("%Y-%m-%d", time.gmtime())), 0),
            "active": bool(active)}, 200


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


_rate = {}
_rate_lock = threading.Lock()
DECIDE_TRIAL = int(os.environ.get("PLUGIN_DECIDE_TRIAL_PER_MIN", "60") or 60)
DECIDE_PAID = int(os.environ.get("PLUGIN_DECIDE_PAID_PER_MIN", "1200") or 1200)
_decisions = {}


def _rate_ok(key, paid):
    limit = DECIDE_PAID if paid else DECIDE_TRIAL
    now = time.time()
    with _rate_lock:
        q = [t for t in _rate.get(key, []) if now - t < 60]
        if len(q) >= limit:
            _rate[key] = q
            return False, limit
        q.append(now)
        _rate[key] = q
    return True, limit


def _f01(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def c_decide(q, body, key):
    key = str(key or "").strip()
    client = _client_for(key)
    if not client or client == "open":
        return {"error": "api_key_required", "message": "Send your sebbi.pro key in the X-Sebbi-Key header."}, 401
    gate = _trial_gate(key)
    if gate:
        return gate, 402
    row = _key_row(key)
    ok, limit = _rate_ok(key, bool(row and row[1]))
    if not ok:
        return {"error": "rate_limited", "limit_per_minute": limit,
                "message": "Decision limit reached for this minute (%d). Paid keys allow more." % limit}, 429
    govern = _server_fn("govern")
    if not govern:
        return {"error": "unavailable", "message": "The decision engine isn't available just now."}, 503
    action = re.sub(r"[^A-Za-z0-9 ._:/-]", "", str(body.get("action") or "action"))[:80] or "action"
    user = str(body.get("user") or "").strip()
    dev = str(body.get("device") or "").strip()
    if user and not CID_RE.match(user):
        return {"error": "bad_user", "message": "user must be 1-80 letters, numbers, _ . : -"}, 400
    if dev and not CID_RE.match(dev):
        return {"error": "bad_device", "message": "device must be 1-80 letters, numbers, _ . : -"}, 400
    try:
        amount = max(0.0, float(body.get("amount") or 0))
    except (TypeError, ValueError):
        amount = 0.0
    country = re.sub(r"[^A-Za-z]", "", str(body.get("country") or "UK"))[:2].upper() or "UK"
    if country == "GB":
        country = "UK"
    event = {"user_id": "plugin:" + (user or dev or client), "action": action, "amount": amount,
             "country": country, "device_id": "adapter:" + (dev or client),
             "anomaly": _f01(body.get("anomaly")), "device_risk": _f01(body.get("device_risk"))}
    try:
        result, status = govern(event, None)
    except Exception as e:
        return {"error": "engine_error", "message": "The engine couldn't decide: " + str(e)[:120]}, 500
    if status != 200 or not isinstance(result, dict):
        return {"error": "engine_error", "detail": result}, 502
    _meter(key, [dev or client.replace("k_", "key_")])
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with _rate_lock:
        _decisions[(client, day)] = _decisions.get((client, day), 0) + 1
    out = {"decision": result.get("decision"), "action": action, "score": result.get("score"),
           "reasons": result.get("reasons") or [], "audit_hash": result.get("audit_hash"),
           "block_index": result.get("block_index"),
           "verify": SITE + "/x/walk/block?index=%s" % result.get("block_index"),
           "timestamp": result.get("timestamp")}
    for k in ("challenge_url", "challenge_status_url", "challenge_expires_in"):
        if k in result:
            out[k] = result[k]
    return out, 200


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
POSTS = {"submit": c_submit, "signup": c_signup, "account": c_account, "pay": c_pay, "decide": c_decide}


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
