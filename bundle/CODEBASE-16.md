# Codebase — part 16 of 41

Contains:
- `modules/peerconsole.py`
- `modules/praxis.py`
- `modules/prove.py`
- `modules/publish.py`


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


## `modules/prove.py`

352 lines, 30070 bytes

```python
"""
modules/prove.py  v1.0.0
"Prove it all" - every public address that proves something about sebbi.pro,
on one page at /prove, and as a machine-readable index at /prove.json.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/prove/status or /x/armall/status after each deploy.
The page checks every JSON route live from the visitor's browser, one at a
time, and shows green (answered), amber (rate-limited) or red (failed).
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIiPgo8"
    "dGl0bGU+UHJvdmUgaXQgYWxsIOKAlCBzZWJiaS5wcm8sIG1hY2hpbmUgcmVhZGFibGU8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNj"
    "cmlwdGlvbiIgY29udGVudD0iRXZlcnkgcHVibGljIHJvdXRlIHRoYXQgcHJvdmVzIHNvbWV0aGluZyBhYm91dCBzZWJiaS5wcm8s"
    "IGluIG9uZSBwbGFjZSwgY2hlY2tlZCBsaXZlLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3Nz"
    "Mj9mYW1pbHk9TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmZhbWlseT1JQk0rUGxleCtTYW5zOndnaHRANDAwOzUwMDs2"
    "MDAmZmFtaWx5PUlCTStQbGV4K01vbm86d2dodEA0MDA7NTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxl"
    "Pgo6cm9vdHstLWluazojMGEwZjFlOy0taW5rMjojMTAxODJlOy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLWVycjojZmY4"
    "YTgwOy0tYW1iOiNmMGM2NzQ7LS1tdXQ6cmdiYSgyNTUsMjU1LDI1NSwuNjIpOy0tbGluZTpyZ2JhKDIwMSwxNjgsNzYsLjE4KTsK"
    "LS1zYW5zOidJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidOZXdzcmVhZGVyJyxHZW9yZ2lhLHNl"
    "cmlmOy0tbW9ubzonSUJNIFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZX0KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7"
    "bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZmZmO2ZvbnQtZmFtaWx5OnZhcigt"
    "LXNhbnMpO2xpbmUtaGVpZ2h0OjEuNTU7LXdlYmtpdC1mb250LXNtb290aGluZzphbnRpYWxpYXNlZDtwYWRkaW5nLWJvdHRvbTpl"
    "bnYoc2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwKX0KLndyYXB7bWF4LXdpZHRoOjg2MHB4O21hcmdpbjowIGF1dG87cGFkZGluZzow"
    "IDIwcHh9Ci50b3B7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxNXB4IDB9LnRvcCAud3JhcHtk"
    "aXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6YmFzZWxpbmU7ZmxleC13cmFwOndy"
    "YXA7Z2FwOjEwcHh9Ci5icmFuZHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTNweH0uYnJhbmQgYntjb2xvcjp2"
    "YXIoLS1nb2xkKTtmb250LXdlaWdodDo1MDB9Ci50b3AgYXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4"
    "O2NvbG9yOnZhcigtLW11dCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2luLWxlZnQ6MTRweH0KLmhlcm97cGFkZGluZzo0NnB4"
    "IDAgMjJweH0ua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0"
    "ZXItc3BhY2luZzouMDdlbTttYXJnaW4tYm90dG9tOjEycHh9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdo"
    "dDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNnZ3LDU0cHgpO2xpbmUtaGVpZ2h0OjEuMDU7bWFyZ2luLWJvdHRvbToxNHB4fQou"
    "aGVybyBwe2NvbG9yOnZhcigtLW11dCk7bWF4LXdpZHRoOjU4Y2g7Zm9udC1zaXplOjE2LjVweH0KLmJhcntwb3NpdGlvbjpzdGlj"
    "a3k7dG9wOjA7ei1pbmRleDo1O2JhY2tncm91bmQ6cmdiYSgxMCwxNSwzMCwuOTQpO2JhY2tkcm9wLWZpbHRlcjpibHVyKDZweCk7"
    "Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxMnB4IDA7bWFyZ2luLXRvcDoyMnB4fQouYmFyIC53"
    "cmFwe2Rpc3BsYXk6ZmxleDtnYXA6MTRweDthbGlnbi1pdGVtczpjZW50ZXI7ZmxleC13cmFwOndyYXB9Ci5idG57YmFja2dyb3Vu"
    "ZDp2YXIoLS1nb2xkKTtjb2xvcjp2YXIoLS1pbmspO2JvcmRlcjowO2JvcmRlci1yYWRpdXM6NXB4O3BhZGRpbmc6MTBweCAxNnB4"
    "O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2ZvbnQtd2VpZ2h0OjUwMDtjdXJzb3I6cG9pbnRlcn0KLmJ0"
    "bltkaXNhYmxlZF17b3BhY2l0eTouNn0KLnRhbGx5e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMi41cHg7Y29s"
    "b3I6dmFyKC0tbXV0KX0udGFsbHkgYntmb250LXdlaWdodDo1MDB9Ci5ne3BhZGRpbmc6MjZweCAwIDZweH0uZyBoMntmb250LWZh"
    "bWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyNHB4O21hcmdpbi1ib3R0b206M3B4fQouZyAuYWJv"
    "dXR7Y29sb3I6dmFyKC0tbXV0KTtmb250LXNpemU6MTRweDttYXJnaW4tYm90dG9tOjEycHh9Ci5se2Rpc3BsYXk6ZmxleDtnYXA6"
    "MTJweDthbGlnbi1pdGVtczpjZW50ZXI7YmFja2dyb3VuZDp2YXIoLS1pbmsyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "O2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxM3B4O21hcmdpbi1ib3R0b206OHB4fQouZG90e3dpZHRoOjEwcHg7aGVp"
    "Z2h0OjEwcHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4xOCk7ZmxleDpub25lfQouZG90"
    "Lm9re2JhY2tncm91bmQ6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDhweCByZ2JhKDEyNywyMjcsMTc2LC42KX0uZG90LmVycnti"
    "YWNrZ3JvdW5kOnZhcigtLWVycil9LmRvdC5hbWJ7YmFja2dyb3VuZDp2YXIoLS1hbWIpfS5kb3QucnVue2JhY2tncm91bmQ6dmFy"
    "KC0tZ29sZCk7YW5pbWF0aW9uOnAgMC44cyBpbmZpbml0ZSBhbHRlcm5hdGV9CkBrZXlmcmFtZXMgcHt0b3tvcGFjaXR5Oi4zfX0K"
    "LmwgLnR7ZmxleDoxO21pbi13aWR0aDowfS5sIC5ue2ZvbnQtc2l6ZToxNC41cHh9Ci5sIGF7Zm9udC1mYW1pbHk6dmFyKC0tbW9u"
    "byk7Zm9udC1zaXplOjExLjVweDtjb2xvcjp2YXIoLS1nb2xkKTt3b3JkLWJyZWFrOmJyZWFrLWFsbDt0ZXh0LWRlY29yYXRpb246"
    "bm9uZX0KLmwgLnN7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0KTtmbGV4Om5v"
    "bmU7dGV4dC1hbGlnbjpyaWdodDttaW4td2lkdGg6NTZweH0KZm9vdGVye2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "O21hcmdpbi10b3A6MzRweDtwYWRkaW5nOjIycHggMCA0NnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41"
    "cHg7Y29sb3I6dmFyKC0tbXV0KX0KQG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246cmVkdWNlKXsuZG90LnJ1bnthbmltYXRp"
    "b246bm9uZX19Cjwvc3R5bGU+PC9oZWFkPjxib2R5Pgo8aGVhZGVyIGNsYXNzPSJ0b3AiPjxkaXYgY2xhc3M9IndyYXAiPjxkaXYg"
    "Y2xhc3M9ImJyYW5kIj5zZWJiaTxiPi5wcm88L2I+PC9kaXY+PG5hdj48YSBocmVmPSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9wYXNz"
    "cG9ydCI+UGFzc3BvcnQ8L2E+PGEgaHJlZj0iL3Byb3ZlLmpzb24iPkpTT048L2E+PC9uYXY+PC9kaXY+PC9oZWFkZXI+CjxkaXYg"
    "Y2xhc3M9IndyYXAiPjxkaXYgY2xhc3M9Imhlcm8iPjxkaXYgY2xhc3M9ImtpY2siPk1BQ0hJTkUgUkVBREFCTEUgwrcgUFJPVkUg"
    "SVQgQUxMPC9kaXY+CjxoMT5Eb24ndCB0cnVzdCB1cy4gQ2hlY2sgZXZlcnl0aGluZy48L2gxPgo8cD5FdmVyeSBwdWJsaWMgYWRk"
    "cmVzcyB0aGF0IHByb3ZlcyBzb21ldGhpbmcgYWJvdXQgc2ViYmkucHJvLCBpbiBvbmUgcGxhY2UuIE5vIGFjY291bnQsIG5vIGxv"
    "Z2luLCBub3RoaW5nIHRvIGluc3RhbGwuIFRhcCBhbnkgbGluayB0byByZWFkIHRoZSByYXcgcHJvb2YsIG9yIGNoZWNrIHRoZW0g"
    "YWxsIGxpdmUgcmlnaHQgbm93LjwvcD48L2Rpdj48L2Rpdj4KPGRpdiBjbGFzcz0iYmFyIj48ZGl2IGNsYXNzPSJ3cmFwIj48YnV0"
    "dG9uIGNsYXNzPSJidG4iIGlkPSJnbyIgb25jbGljaz0iY2hlY2tBbGwoKSI+Q2hlY2sgZXZlcnl0aGluZyBsaXZlPC9idXR0b24+"
    "CjxzcGFuIGNsYXNzPSJ0YWxseSIgaWQ9InRhbGx5Ij5SZWFkeTwvc3Bhbj48L2Rpdj48L2Rpdj4KPGRpdiBjbGFzcz0id3JhcCIg"
    "aWQ9Imxpc3QiPjwvZGl2Pgo8ZGl2IGNsYXNzPSJ3cmFwIj48Zm9vdGVyPnNlYmJpLnBybyDCtyBNb25vcCBDb250ZW50IMK3IEJs"
    "eXRoLCBOb3J0aHVtYmVybGFuZCwgVUs8YnI+TWFjaGluZXMgY2FuIHJlYWQgdGhpcyB3aG9sZSBpbmRleCBhdCBodHRwczovL3Nl"
    "YmJpLnByby9wcm92ZS5qc29uPC9mb290ZXI+PC9kaXY+CjxzY3JpcHQ+CnZhciBEQVRBPXsiaXNzdWVyIjogInNlYmJpLnBybyIs"
    "ICJ3aGF0IjogImV2ZXJ5IHB1YmxpYyByb3V0ZSB0aGF0IHByb3ZlcyBzb21ldGhpbmcsIGdyb3VwZWQiLCAiaG93IjogImVhY2gg"
    "dXJsIGFuc3dlcnMgd2l0aG91dCBhbiBhY2NvdW50OyBqc29uIHJvdXRlcyBjYW4gYmUgY2hlY2tlZCBieSBtYWNoaW5lIiwgImdy"
    "b3VwcyI6IFt7Imdyb3VwIjogIlRoZSBjaGFpbiBpdHNlbGYiLCAiYWJvdXQiOiAiRXZlcnkgcmVjb3JkIGhhc2hlZCBpbnRvIG9u"
    "ZSBjaGFpbi4gQ2hhbmdlIG9uZSBhbmQgZXZlcnl0aGluZyBhZnRlciBpdCBicmVha3MuIiwgImxpbmtzIjogW3sibmFtZSI6ICJW"
    "ZXJpZnkgdGhlIHdob2xlIGNoYWluIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby9hcGkvdmVyaWZ5LWNoYWluIiwgIm1hY2hp"
    "bmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkN1cnJlbnQgdGlwLCBhcyBzZXJ2ZWQgdG8gd2l0bmVzc2VzIiwgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L3dpdG5lc3MvdGlwIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkFwcGVuZC1v"
    "bmx5IHByb29mIChSRkMgNjk2MiB0cmVlIHJvb3QpIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2NvbnNpc3RlbmN5L3Jv"
    "b3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ29tcGxldGVuZXNzIHBlcmlvZHMgKHByb3ZlIHdoYXQgaXMg"
    "bWlzc2luZykiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUvcGVyaW9kcyIsICJtYWNoaW5lX2NoZWNrIjog"
    "dHJ1ZX0sIHsibmFtZSI6ICJDb21wbGV0ZW5lc3MgcnVsZXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUv"
    "c3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJUaW1lLCBhbmNob3JlZCB0byBCaXRjb2luIiwgImFi"
    "b3V0IjogIlRpbWVzdGFtcHMgbm9ib2R5IGludm9sdmVkIGNhbiBtb3ZlLiIsICJsaW5rcyI6IFt7Im5hbWUiOiAiQW5jaG9yIHBy"
    "b29mcyBzdGF0dXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvb3RzL3N0YXR1cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1"
    "ZX0sIHsibmFtZSI6ICJMYXRlc3QgcHJvb2YgY29uZmlybWVkIGluIEJpdGNvaW4iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJv"
    "L3gvb3RzL2xhdGVzdF9jb25maXJtZWQiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ2hlY2sgdGhlIGFuY2hv"
    "ciBhZ2FpbnN0IHR3byBwdWJsaWMgZXhwbG9yZXJzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L21hY2hpbmUvYXNrP3E9"
    "Yml0Y29pbiIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbmRlcGVuZGVudCB3aXRuZXNzZXMiLCAiYWJv"
    "dXQiOiAiT3RoZXIgb3JnYW5pc2F0aW9ucyBob2xkIG91ciB0aXAuIFdlIGNhbm5vdCByZXdyaXRlIHdoYXQgdGhleSBob2xkLiIs"
    "ICJsaW5rcyI6IFt7Im5hbWUiOiAiV2l0bmVzcyByb3N0ZXIiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcm9zdGVyL2xp"
    "c3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiUGVlcnMgd2UgZXhjaGFuZ2Ugd2l0aCIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8veC9tdXR1YWwvcGVlcnMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiTXV0dWFsIHdp"
    "dG5lc3Npbmcgc3RhdHVzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L211dHVhbC9zdGF0dXMiLCAibWFjaGluZV9jaGVj"
    "ayI6IHRydWV9LCB7Im5hbWUiOiAiV2l0bmVzcyBwZWVycyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3Bl"
    "ZXJzIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfV19LCB7Imdyb3VwIjogIkN1c3RvZHksIG91dHNpZGUgb3VyIGNvbnRyb2wiLCAi"
    "YWJvdXQiOiAiQSBzZWxmLXByb3ZpbmcgZmlsZSBhIGRheSwgYW5kIGEgc2VhbGVkIGNvdW50IG9mIHdobyBob2xkcyBhIGNvcHku"
    "IiwgImxpbmtzIjogW3sibmFtZSI6ICJEYWlseSBzZWxmLXByb3ZpbmcgYXJjaGl2ZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5w"
    "cm8veC9hcmNoaXZlL21hbmlmZXN0IiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkluZGVwZW5kZW50IGhvbGRl"
    "cnMsIGNvdW50ZWQgYW5kIHNlYWxlZCIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jdXN0b2R5L3N0YXR1cyIsICJtYWNo"
    "aW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbnRlZ3JpdHkgcmF0aW5nIiwgImFib3V0IjogIlRoZSBvcGVuIEwwLUw0"
    "IHN0YW5kYXJkLCBjaGVja2VkIGJ5IG1hY2hpbmUuIiwgImxpbmtzIjogW3sibmFtZSI6ICJPdXIgb3duIGRlY2xhcmF0aW9uIiwg"
    "InVybCI6ICJodHRwczovL3NlYmJpLnByby94L2ludGVncml0eS9zZWxmIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1l"
    "IjogIlRoZSBwdWJsaWMgcmVnaXN0ZXIgb2YgdmVyZGljdHMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvaW50ZWdyaXR5"
    "L3JlZ2lzdGVyIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkNoZWNrZXIgc3RhdHVzIiwgInVybCI6ICJodHRw"
    "czovL3NlYmJpLnByby94L2ludGVncml0eS9zdGF0dXMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9XX0sIHsiZ3JvdXAiOiAiQXV0"
    "aG9yaXR5IGF0IHRoZSBtb21lbnQgb2YgYWN0aW9uIiwgImFib3V0IjogIldobyBhdXRob3Jpc2VkIGl0LCB3aGV0aGVyIGl0IHN0"
    "aWxsIHN0b29kLCBzaWduZWQuIiwgImxpbmtzIjogW3sibmFtZSI6ICJUaGUgZGVyaXZhdGlvbiBydWxlcyIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3NwZWMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiRXZlcnkg"
    "c2VhbGVkIGF1dGhvcml0eSBkZWNpc2lvbiIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L2RlY2lzaW9u"
    "cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJMYXRlc3Qgc2lnbmVkIHByb29mIGJ1bmRsZSIsICJ1cmwiOiAi"
    "aHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3Byb29mIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIlRo"
    "ZSBzaWduaW5nIGtleSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3B1YmtleSIsICJtYWNoaW5lX2No"
    "ZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbmRlcGVuZGVudCB0ZXN0OiBUZW1wb3JhbCBTdGFuZGluZyIsICJhYm91dCI6ICJD"
    "bGFpbSBmcm96ZW4gYmVmb3JlIHRoZSBydW4uIFJlc3VsdCBwdWJsaXNoZWQgYXMgb2JzZXJ2ZWQuIiwgImxpbmtzIjogW3sibmFt"
    "ZSI6ICJUaGUgc2VhbGVkIHByZS1yZWdpc3RyYXRpb24iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvZnJl"
    "ZXplIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkV2ZXJ5IHJ1biwgZmFpbHVyZXMgaW5jbHVkZWQiLCAidXJs"
    "IjogImh0dHBzOi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvcnVucyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJM"
    "YXRlc3QgZXZpZGVuY2UgcGFja2FnZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9zdGFuZGluZy9ldmlkZW5jZSIsICJt"
    "YWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJBZ2VudCBQYXNzcG9ydCIsICJhYm91dCI6ICJTaWduZWQsIHNpbmds"
    "ZS11c2UgcGVybWlzc2lvbiBmb3IgQUkgYWN0aW9ucy4iLCAibGlua3MiOiBbeyJuYW1lIjogIlBhc3Nwb3J0IHN0YXR1cyBhbmQg"
    "Y291bnRzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3Bhc3Nwb3J0L3N0YXR1cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1"
    "ZX0sIHsibmFtZSI6ICJUb2tlbiBmb3JtYXQgYW5kIG9mZmxpbmUgcnVsZXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gv"
    "cGFzc3BvcnQvc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJTaXRlIGRpc2NvdmVyeSBmaWxlIGdlbmVy"
    "YXRvciIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9zaXRlZmlsZT9kb21haW49eW91ci5zaXRlJnJlcXVp"
    "cmU9cGF5bWVudHMuKiIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJNQ1AgZW5kcG9pbnQgZm9yIGFnZW50cyIs"
    "ICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9tY3AiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUi"
    "OiAiUnVuIHRoZSB0ZW4tc3RlcCBsaXZlIGRlbW8iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvZGVtbyIs"
    "ICJtYWNoaW5lX2NoZWNrIjogZmFsc2V9XX0sIHsiZ3JvdXAiOiAiRGV0ZXJtaW5pc20gYW5kIHRoZSBkZWNpc2lvbiBmdW5jdGlv"
    "biIsICJhYm91dCI6ICJTYW1lIGlucHV0cywgc2FtZSB2ZXJkaWN0LCB1bmRlciBhIHB1Ymxpc2hlZCBmaW5nZXJwcmludC4iLCAi"
    "bGlua3MiOiBbeyJuYW1lIjogIkNvZGUgZmluZ2VycHJpbnQiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcmVwbGF5L2Zp"
    "bmdlcnByaW50IiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIlJlcGxheSBydWxlcyIsICJ1cmwiOiAiaHR0cHM6"
    "Ly9zZWJiaS5wcm8veC9yZXBsYXkvc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJFdmlkZW5jZSB5"
    "b3UgY2FuIHRha2UgYXdheSIsICJhYm91dCI6ICJQYWNrcywgbGluZWFnZSwgcHVibGljYXRpb25zIGFuZCBhdXRob3JzaGlwLCBh"
    "bGwgc2VhbGVkLiIsICJsaW5rcyI6IFt7Im5hbWUiOiAiUXVhcnRlcmx5IGV2aWRlbmNlIHBhY2sgZm9ybWF0IiwgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L3BhY2svc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJDcm9zcy1vcmdh"
    "bmlzYXRpb24gbGluZWFnZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9saW5lYWdlL3NwZWMiLCAibWFjaGluZV9jaGVj"
    "ayI6IHRydWV9LCB7Im5hbWUiOiAiU2VhbGVkIHB1YmxpY2F0aW9ucyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wdWJs"
    "aXNoL2xpc3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ29kZWJhc2UgYXV0aG9yc2hpcCByb290IiwgInVy"
    "bCI6ICJodHRwczovL3NlYmJpLnByby94L2NvZGViYXNlL3Jvb3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAi"
    "TWV0ZXJpbmcgZ2F0ZSBydWxlcyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93YWxsZXQvc3BlYyIsICJtYWNoaW5lX2No"
    "ZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJTaWduYWwgUGFja3MiLCAiYWJvdXQiOiAiVGhlIG9wZW4gbGlicmFyeSBvZiBkZWNp"
    "c2lvbiBwYWNrcy4iLCAibGlua3MiOiBbeyJuYW1lIjogIkJyb3dzZSB0aGUgcGFja3MiLCAidXJsIjogImh0dHBzOi8vc2ViYmku"
    "cHJvL3BhY2tzIiwgIm1hY2hpbmVfY2hlY2siOiBmYWxzZX1dfSwgeyJncm91cCI6ICJGb3IgbWFjaGluZXMiLCAiYWJvdXQiOiAi"
    "UGxhaW4gZmlsZXMgYW55IHN5c3RlbSBjYW4gcmVhZC4iLCAibGlua3MiOiBbeyJuYW1lIjogImFpLnR4dCIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8vLndlbGwta25vd24vYWkudHh0IiwgIm1hY2hpbmVfY2hlY2siOiBmYWxzZX0sIHsibmFtZSI6ICJjb21w"
    "bHkudHh0IiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9jb21wbHkudHh0IiwgIm1hY2hpbmVfY2hlY2si"
    "OiBmYWxzZX0sIHsibmFtZSI6ICJUaGlzIHdob2xlIGluZGV4IGFzIEpTT04iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3By"
    "b3ZlLmpzb24iLCAibWFjaGluZV9jaGVjayI6IGZhbHNlfV19XX07CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJl"
    "cGxhY2UoL1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybnsnJic6JyZhbXA7JywnPCc6JyZsdDsnLCc+JzonJmd0OycsJyInOicm"
    "cXVvdDsnfVtjXX0pfQp2YXIgcm93cz1bXSxMPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaXN0Jyk7CkRBVEEuZ3JvdXBzLmZv"
    "ckVhY2goZnVuY3Rpb24oZyl7dmFyIGQ9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7ZC5jbGFzc05hbWU9J2cnOwogdmFy"
    "IGg9JzxoMj4nK2VzYyhnLmdyb3VwKSsnPC9oMj48ZGl2IGNsYXNzPSJhYm91dCI+Jytlc2MoZy5hYm91dCkrJzwvZGl2Pic7CiBn"
    "LmxpbmtzLmZvckVhY2goZnVuY3Rpb24obCxpKXt2YXIgaWQ9J3InK3Jvd3MubGVuZ3RoO3Jvd3MucHVzaCh7aWQ6aWQsdXJsOmwu"
    "dXJsLGNoZWNrOmwubWFjaGluZV9jaGVja30pOwogIGgrPSc8ZGl2IGNsYXNzPSJsIj48c3BhbiBjbGFzcz0iZG90IiBpZD0iJytp"
    "ZCsnZCI+PC9zcGFuPjxkaXYgY2xhc3M9InQiPjxkaXYgY2xhc3M9Im4iPicrZXNjKGwubmFtZSkrJzwvZGl2PjxhIGhyZWY9Iicr"
    "ZXNjKGwudXJsKSsnIiB0YXJnZXQ9Il9ibGFuayIgcmVsPSJub29wZW5lciI+Jytlc2MobC51cmwucmVwbGFjZSgnaHR0cHM6Ly8n"
    "LCcnKSkrJzwvYT48L2Rpdj48c3BhbiBjbGFzcz0icyIgaWQ9IicraWQrJ3MiPicrKGwubWFjaGluZV9jaGVjaz8nJzonb3Blbicp"
    "Kyc8L3NwYW4+PC9kaXY+J30pOwogZC5pbm5lckhUTUw9aDtMLmFwcGVuZENoaWxkKGQpfSk7CmZ1bmN0aW9uIHNldChyLGMsdCl7"
    "ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoci5pZCsnZCcpLmNsYXNzTmFtZT0nZG90ICcrYztkb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZChyLmlkKydzJykudGV4dENvbnRlbnQ9dH0KZnVuY3Rpb24gY2hlY2tBbGwoKXt2YXIgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZCgnZ28nKSxUPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWxseScpO2IuZGlzYWJsZWQ9dHJ1ZTsKIHZhciBxPXJvd3MuZmls"
    "dGVyKGZ1bmN0aW9uKHIpe3JldHVybiByLmNoZWNrfSksb2s9MCxiYWQ9MCxidXN5PTAsaT0wLEdBUD02NTA7CiBxLmZvckVhY2go"
    "ZnVuY3Rpb24ocil7c2V0KHIsJycsJ3F1ZXVlZCcpfSk7CiBmdW5jdGlvbiBkb25lKCl7VC5pbm5lckhUTUw9JzxiIHN0eWxlPSJj"
    "b2xvcjojN2ZlM2IwIj4nK29rKycgYW5zd2VyZWQ8L2I+JysoYmFkPycgwrcgPGIgc3R5bGU9ImNvbG9yOiNmZjhhODAiPicrYmFk"
    "KycgZmFpbGVkPC9iPic6JycpKyhidXN5PycgwrcgJytidXN5Kycgc3RpbGwgYnVzeSc6JycpKycgwrcgY2hlY2tlZCAnK25ldyBE"
    "YXRlKCkudG9Mb2NhbGVUaW1lU3RyaW5nKCk7Yi5kaXNhYmxlZD1mYWxzZX0KIGZ1bmN0aW9uIG9uZShyLHRyaWVzKXt2YXIgdDA9"
    "cGVyZm9ybWFuY2Uubm93KCk7c2V0KHIsJ3J1bicsdHJpZXM/J3JldHJ5ICcrdHJpZXM6J+KApicpOwogIGZldGNoKHIudXJsLnJl"
    "cGxhY2UoJ2h0dHBzOi8vc2ViYmkucHJvJywnJykse2NhY2hlOiduby1zdG9yZSd9KS50aGVuKGZ1bmN0aW9uKHgpe3ZhciBtcz1N"
    "YXRoLnJvdW5kKHBlcmZvcm1hbmNlLm5vdygpLXQwKTsKICAgaWYoeC5vayl7b2srKztzZXQociwnb2snLG1zKycgbXMnKTtzZXRU"
    "aW1lb3V0KG5leHQsR0FQKX0KICAgZWxzZSBpZih4LnN0YXR1cz09PTQyOSYmdHJpZXM8Myl7c2V0KHIsJ2FtYicsJ3dhaXRpbmcn"
    "KTtzZXRUaW1lb3V0KGZ1bmN0aW9uKCl7b25lKHIsdHJpZXMrMSl9LDMwMDAqKHRyaWVzKzEpKX0KICAgZWxzZSBpZih4LnN0YXR1"
    "cz09PTQyOSl7YnVzeSsrO3NldChyLCdhbWInLCdidXN5Jyk7c2V0VGltZW91dChuZXh0LEdBUCl9CiAgIGVsc2V7YmFkKys7c2V0"
    "KHIsJ2VycicsU3RyaW5nKHguc3RhdHVzKSk7c2V0VGltZW91dChuZXh0LEdBUCl9CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtiYWQr"
    "KztzZXQociwnZXJyJywnZXJyb3InKTtzZXRUaW1lb3V0KG5leHQsR0FQKX0pfQogZnVuY3Rpb24gbmV4dCgpe2lmKGk+PXEubGVu"
    "Z3RoKXtkb25lKCk7cmV0dXJufXZhciByPXFbaSsrXTtULnRleHRDb250ZW50PSdDaGVja2luZyAnK2krJyBvZiAnK3EubGVuZ3Ro"
    "O29uZShyLDApfQogbmV4dCgpfQo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="
)

_JSON_B64 = (
    "ewogImlzc3VlciI6ICJzZWJiaS5wcm8iLAogIndoYXQiOiAiZXZlcnkgcHVibGljIHJvdXRlIHRoYXQgcHJvdmVzIHNvbWV0aGlu"
    "ZywgZ3JvdXBlZCIsCiAiaG93IjogImVhY2ggdXJsIGFuc3dlcnMgd2l0aG91dCBhbiBhY2NvdW50OyBqc29uIHJvdXRlcyBjYW4g"
    "YmUgY2hlY2tlZCBieSBtYWNoaW5lIiwKICJncm91cHMiOiBbCiAgewogICAiZ3JvdXAiOiAiVGhlIGNoYWluIGl0c2VsZiIsCiAg"
    "ICJhYm91dCI6ICJFdmVyeSByZWNvcmQgaGFzaGVkIGludG8gb25lIGNoYWluLiBDaGFuZ2Ugb25lIGFuZCBldmVyeXRoaW5nIGFm"
    "dGVyIGl0IGJyZWFrcy4iLAogICAibGlua3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiVmVyaWZ5IHRoZSB3aG9sZSBjaGFpbiIs"
    "CiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby9hcGkvdmVyaWZ5LWNoYWluIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRy"
    "dWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiQ3VycmVudCB0aXAsIGFzIHNlcnZlZCB0byB3aXRuZXNzZXMiLAogICAgICJ1"
    "cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3RpcCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAog"
    "ICAgewogICAgICJuYW1lIjogIkFwcGVuZC1vbmx5IHByb29mIChSRkMgNjk2MiB0cmVlIHJvb3QpIiwKICAgICAidXJsIjogImh0"
    "dHBzOi8vc2ViYmkucHJvL3gvY29uc2lzdGVuY3kvcm9vdCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAg"
    "ewogICAgICJuYW1lIjogIkNvbXBsZXRlbmVzcyBwZXJpb2RzIChwcm92ZSB3aGF0IGlzIG1pc3NpbmcpIiwKICAgICAidXJsIjog"
    "Imh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUvcGVyaW9kcyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAog"
    "ICAgewogICAgICJuYW1lIjogIkNvbXBsZXRlbmVzcyBydWxlcyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2Nv"
    "bXBsZXRlL3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJU"
    "aW1lLCBhbmNob3JlZCB0byBCaXRjb2luIiwKICAgImFib3V0IjogIlRpbWVzdGFtcHMgbm9ib2R5IGludm9sdmVkIGNhbiBtb3Zl"
    "LiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJBbmNob3IgcHJvb2ZzIHN0YXR1cyIsCiAgICAgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L290cy9zdGF0dXMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAg"
    "ICAibmFtZSI6ICJMYXRlc3QgcHJvb2YgY29uZmlybWVkIGluIEJpdGNvaW4iLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5w"
    "cm8veC9vdHMvbGF0ZXN0X2NvbmZpcm1lZCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJu"
    "YW1lIjogIkNoZWNrIHRoZSBhbmNob3IgYWdhaW5zdCB0d28gcHVibGljIGV4cGxvcmVycyIsCiAgICAgInVybCI6ICJodHRwczov"
    "L3NlYmJpLnByby94L21hY2hpbmUvYXNrP3E9Yml0Y29pbiIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9CiAgIF0K"
    "ICB9LAogIHsKICAgImdyb3VwIjogIkluZGVwZW5kZW50IHdpdG5lc3NlcyIsCiAgICJhYm91dCI6ICJPdGhlciBvcmdhbmlzYXRp"
    "b25zIGhvbGQgb3VyIHRpcC4gV2UgY2Fubm90IHJld3JpdGUgd2hhdCB0aGV5IGhvbGQuIiwKICAgImxpbmtzIjogWwogICAgewog"
    "ICAgICJuYW1lIjogIldpdG5lc3Mgcm9zdGVyIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcm9zdGVyL2xpc3Qi"
    "LAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJQZWVycyB3ZSBleGNoYW5nZSB3"
    "aXRoIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvbXV0dWFsL3BlZXJzIiwKICAgICAibWFjaGluZV9jaGVjayI6"
    "IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiTXV0dWFsIHdpdG5lc3Npbmcgc3RhdHVzIiwKICAgICAidXJsIjogImh0"
    "dHBzOi8vc2ViYmkucHJvL3gvbXV0dWFsL3N0YXR1cyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewog"
    "ICAgICJuYW1lIjogIldpdG5lc3MgcGVlcnMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3BlZXJz"
    "IiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiQ3VzdG9keSwgb3V0"
    "c2lkZSBvdXIgY29udHJvbCIsCiAgICJhYm91dCI6ICJBIHNlbGYtcHJvdmluZyBmaWxlIGEgZGF5LCBhbmQgYSBzZWFsZWQgY291"
    "bnQgb2Ygd2hvIGhvbGRzIGEgY29weS4iLAogICAibGlua3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiRGFpbHkgc2VsZi1wcm92"
    "aW5nIGFyY2hpdmUiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9hcmNoaXZlL21hbmlmZXN0IiwKICAgICAibWFj"
    "aGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiSW5kZXBlbmRlbnQgaG9sZGVycywgY291bnRlZCBh"
    "bmQgc2VhbGVkIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY3VzdG9keS9zdGF0dXMiLAogICAgICJtYWNoaW5l"
    "X2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJJbnRlZ3JpdHkgcmF0aW5nIiwKICAgImFib3V0"
    "IjogIlRoZSBvcGVuIEwwLUw0IHN0YW5kYXJkLCBjaGVja2VkIGJ5IG1hY2hpbmUuIiwKICAgImxpbmtzIjogWwogICAgewogICAg"
    "ICJuYW1lIjogIk91ciBvd24gZGVjbGFyYXRpb24iLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9pbnRlZ3JpdHkv"
    "c2VsZiIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlRoZSBwdWJsaWMgcmVn"
    "aXN0ZXIgb2YgdmVyZGljdHMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9pbnRlZ3JpdHkvcmVnaXN0ZXIiLAog"
    "ICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJDaGVja2VyIHN0YXR1cyIsCiAgICAg"
    "InVybCI6ICJodHRwczovL3NlYmJpLnByby94L2ludGVncml0eS9zdGF0dXMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQog"
    "ICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJBdXRob3JpdHkgYXQgdGhlIG1vbWVudCBvZiBhY3Rpb24iLAogICAiYWJv"
    "dXQiOiAiV2hvIGF1dGhvcmlzZWQgaXQsIHdoZXRoZXIgaXQgc3RpbGwgc3Rvb2QsIHNpZ25lZC4iLAogICAibGlua3MiOiBbCiAg"
    "ICB7CiAgICAgIm5hbWUiOiAiVGhlIGRlcml2YXRpb24gcnVsZXMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9j"
    "b250aW51aXR5L3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJFdmVy"
    "eSBzZWFsZWQgYXV0aG9yaXR5IGRlY2lzaW9uIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29udGludWl0eS9k"
    "ZWNpc2lvbnMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJMYXRlc3Qgc2ln"
    "bmVkIHByb29mIGJ1bmRsZSIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2NvbnRpbnVpdHkvcHJvb2YiLAogICAg"
    "ICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJUaGUgc2lnbmluZyBrZXkiLAogICAgICJ1"
    "cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3B1YmtleSIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAg"
    "ICB9CiAgIF0KICB9LAogIHsKICAgImdyb3VwIjogIkluZGVwZW5kZW50IHRlc3Q6IFRlbXBvcmFsIFN0YW5kaW5nIiwKICAgImFi"
    "b3V0IjogIkNsYWltIGZyb3plbiBiZWZvcmUgdGhlIHJ1bi4gUmVzdWx0IHB1Ymxpc2hlZCBhcyBvYnNlcnZlZC4iLAogICAibGlu"
    "a3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiVGhlIHNlYWxlZCBwcmUtcmVnaXN0cmF0aW9uIiwKICAgICAidXJsIjogImh0dHBz"
    "Oi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvZnJlZXplIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAg"
    "ICAgIm5hbWUiOiAiRXZlcnkgcnVuLCBmYWlsdXJlcyBpbmNsdWRlZCIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94"
    "L3N0YW5kaW5nL3J1bnMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJMYXRl"
    "c3QgZXZpZGVuY2UgcGFja2FnZSIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3N0YW5kaW5nL2V2aWRlbmNlIiwK"
    "ICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiQWdlbnQgUGFzc3BvcnQi"
    "LAogICAiYWJvdXQiOiAiU2lnbmVkLCBzaW5nbGUtdXNlIHBlcm1pc3Npb24gZm9yIEFJIGFjdGlvbnMuIiwKICAgImxpbmtzIjog"
    "WwogICAgewogICAgICJuYW1lIjogIlBhc3Nwb3J0IHN0YXR1cyBhbmQgY291bnRzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2Vi"
    "YmkucHJvL3gvcGFzc3BvcnQvc3RhdHVzIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5h"
    "bWUiOiAiVG9rZW4gZm9ybWF0IGFuZCBvZmZsaW5lIHJ1bGVzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFz"
    "c3BvcnQvc3BlYyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlNpdGUgZGlz"
    "Y292ZXJ5IGZpbGUgZ2VuZXJhdG9yIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvc2l0ZWZpbGU/"
    "ZG9tYWluPXlvdXIuc2l0ZSZyZXF1aXJlPXBheW1lbnRzLioiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAg"
    "IHsKICAgICAibmFtZSI6ICJNQ1AgZW5kcG9pbnQgZm9yIGFnZW50cyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94"
    "L3Bhc3Nwb3J0L21jcCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlJ1biB0"
    "aGUgdGVuLXN0ZXAgbGl2ZSBkZW1vIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvZGVtbyIsCiAg"
    "ICAgIm1hY2hpbmVfY2hlY2siOiBmYWxzZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJEZXRlcm1pbmlzbSBhbmQg"
    "dGhlIGRlY2lzaW9uIGZ1bmN0aW9uIiwKICAgImFib3V0IjogIlNhbWUgaW5wdXRzLCBzYW1lIHZlcmRpY3QsIHVuZGVyIGEgcHVi"
    "bGlzaGVkIGZpbmdlcnByaW50LiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJDb2RlIGZpbmdlcnByaW50IiwK"
    "ICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcmVwbGF5L2ZpbmdlcnByaW50IiwKICAgICAibWFjaGluZV9jaGVjayI6"
    "IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiUmVwbGF5IHJ1bGVzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmku"
    "cHJvL3gvcmVwbGF5L3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91"
    "cCI6ICJFdmlkZW5jZSB5b3UgY2FuIHRha2UgYXdheSIsCiAgICJhYm91dCI6ICJQYWNrcywgbGluZWFnZSwgcHVibGljYXRpb25z"
    "IGFuZCBhdXRob3JzaGlwLCBhbGwgc2VhbGVkLiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJRdWFydGVybHkg"
    "ZXZpZGVuY2UgcGFjayBmb3JtYXQiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYWNrL3NwZWMiLAogICAgICJt"
    "YWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJDcm9zcy1vcmdhbmlzYXRpb24gbGluZWFnZSIs"
    "CiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2xpbmVhZ2Uvc3BlYyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVl"
    "CiAgICB9LAogICAgewogICAgICJuYW1lIjogIlNlYWxlZCBwdWJsaWNhdGlvbnMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJi"
    "aS5wcm8veC9wdWJsaXNoL2xpc3QiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6"
    "ICJDb2RlYmFzZSBhdXRob3JzaGlwIHJvb3QiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb2RlYmFzZS9yb290"
    "IiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiTWV0ZXJpbmcgZ2F0ZSBydWxl"
    "cyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3dhbGxldC9zcGVjIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRy"
    "dWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiU2lnbmFsIFBhY2tzIiwKICAgImFib3V0IjogIlRoZSBvcGVuIGxp"
    "YnJhcnkgb2YgZGVjaXNpb24gcGFja3MuIiwKICAgImxpbmtzIjogWwogICAgewogICAgICJuYW1lIjogIkJyb3dzZSB0aGUgcGFj"
    "a3MiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8vcGFja3MiLAogICAgICJtYWNoaW5lX2NoZWNrIjogZmFsc2UKICAg"
    "IH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiRm9yIG1hY2hpbmVzIiwKICAgImFib3V0IjogIlBsYWluIGZpbGVzIGFueSBz"
    "eXN0ZW0gY2FuIHJlYWQuIiwKICAgImxpbmtzIjogWwogICAgewogICAgICJuYW1lIjogImFpLnR4dCIsCiAgICAgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9haS50eHQiLAogICAgICJtYWNoaW5lX2NoZWNrIjogZmFsc2UKICAgIH0sCiAg"
    "ICB7CiAgICAgIm5hbWUiOiAiY29tcGx5LnR4dCIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9j"
    "b21wbHkudHh0IiwKICAgICAibWFjaGluZV9jaGVjayI6IGZhbHNlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlRoaXMgd2hv"
    "bGUgaW5kZXggYXMgSlNPTiIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby9wcm92ZS5qc29uIiwKICAgICAibWFjaGlu"
    "ZV9jaGVjayI6IGZhbHNlCiAgICB9CiAgIF0KICB9CiBdCn0="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/prove": (_d(_HTML_B64), "text/html; charset=utf-8"),
    "/prove.json": (_d(_JSON_B64), "application/json; charset=utf-8"),
}
_patched = False


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


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_prove_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._prove_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "prove", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/publish.py`

491 lines, 21976 bytes

```python
#!/usr/bin/env python3
"""
modules/publish.py  -  sealing what you published, at the moment you publish it
===============================================================================

THE PROBLEM THIS EXISTS TO NEVER HAVE AGAIN
-------------------------------------------
Somebody asks when a page was published. You answer from git history. They
point out - correctly - that git commit dates are fields in the commit
object which anyone can set to anything with an environment variable before
committing. Your strongest evidence turns out to be the weakest thing in
the room, and it drags the credible parts down with it.

The fix is not a better argument. It is sealing the page the moment it goes
live, so the question never depends on anybody's word again.

WHAT THIS DOES
--------------
    POST /x/publish/seal {"url": "https://example.com/spec"}

We fetch the URL ourselves, hash exactly what was served, and seal the hash,
the URL and the fetch time into the chain - where it is anchored externally
and handed to peer chains like every other block.

From then on:

  - "this exact content was served at this address no later than T" is
    arithmetic rather than a claim;
  - re-sealing the same URL later builds a permanent revision history that
    the publisher cannot edit, because each version is its own block;
  - and anyone can check it without an account.

Seal at publication and you never argue about a publication date again. That
is the entire point, and it takes one call.

WHAT IT HONESTLY CANNOT DO
--------------------------
It cannot reach backwards. A seal made today proves the content existed
today, not that it existed last week. Nothing can prove that - not this, not
Bitcoin, not a notary. Timestamps are one-directional by nature.

So for anything already published before it was sealed, the module records
EXTERNAL REFERENCES alongside: a GitHub push event, a Wayback Machine
snapshot, a DigiCert or OpenTimestamps proof. Those are stored and sealed as
supplied. We do not verify them and we do not present them as ours - they
are somebody else's record, named so a third party can check it at source.
That distinction is stated in every response rather than left to be
discovered.

Two references are worth knowing about, because they are the ones that
actually carry an earlier date:

  GitHub push events   api.github.com/repos/<owner>/<repo>/events
                       The push timestamp is recorded server-side by GitHub
                       and cannot be set by the pusher, unlike commit dates.
                       Retained roughly 90 days - so it must be captured
                       while it still exists.

  Wayback Machine      archive.org/wayback/available?url=...&timestamp=...
                       An independent party with no stake in the dispute.
                       If it caught the page, that settles it outright.

FETCHING SAFELY
---------------
This module makes the server fetch a URL. Done naively that is a hole worse
than the one it closes. So the fetcher speaks only http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that
is private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a cap. Sealing is keyed,
so this is not an anonymous capability either.

    POST /x/publish/seal      fetch, hash and seal a live URL     (keyed)
    GET  /x/publish/history   every version ever sealed of a URL  (public)
    GET  /x/publish/verify    was this exact content served, when (public)
    GET  /x/publish/list      everything sealed                   (public)
    GET  /x/publish/spec      how to check any of it              (public)
"""

import hashlib
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Reading is open. A publication record only settles an argument if the
# other side can check it without going through the publisher.
PUBLIC = {("GET", "history"), ("GET", "verify"), ("GET", "list"),
          ("GET", "spec")}

CONTENT_PREFIX = b"AILEASH-PUBLISH-v1:"

FETCH_TIMEOUT = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
MAX_EXTERNAL = 8

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS publish_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,url TEXT,"
                  "content_hash TEXT,byte_length INTEGER,http_status INTEGER,"
                  "content_type TEXT,note TEXT,external TEXT,"
                  "fetched REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_url ON publish_seal(url,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_hash ON publish_seal(content_hash)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# fetching - read the SSRF note above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction to fetch a second URL we never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    if not parts.hostname:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(parts.hostname, port)


def _fetch(url):
    """Returns (body_bytes, status, content_type, error)."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, None, None, why
    request = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "aileash-publish/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, exc.code, None, "url answered %s" % exc.code
    except Exception as exc:
        return None, None, None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, status, content_type, "response larger than the %d byte cap" % MAX_FETCH_BYTES
    return body, status, content_type, None


def _content_hash(body):
    """Hash exactly the bytes served. No normalisation, no cleverness -
    a whitespace-tolerant hash would be a hash of our opinion of the page
    rather than of the page."""
    return hashlib.sha256(CONTENT_PREFIX + body).hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _clean_external(value):
    """External references are recorded verbatim and never verified."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_EXTERNAL]:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()[:60]
            reference = str(item.get("reference", item.get("url", ""))).strip()[:400]
            claimed = str(item.get("claimed_time", "")).strip()[:60]
            if source and reference:
                out.append({"source": source, "reference": reference,
                            "claimed_time": claimed or None})
        elif isinstance(item, str) and item.strip():
            out.append({"source": "unnamed", "reference": item.strip()[:400],
                        "claimed_time": None})
    return out


def _seal(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required",
                "message": "The address of the page you have just published."}, 400

    note = str(data.get("note", "") or "").strip()[:300]
    external = _clean_external(data.get("external"))

    body, status, content_type, why = _fetch(url)
    if why:
        return {"error": "fetch_failed", "url": url, "message": why,
                "note": "Nothing was sealed. A record of a page we could not read would be "
                        "worse than no record."}, 502

    digest = _content_hash(body)
    now = time.time()

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT content_hash,fetched,audit_hash FROM publish_seal "
            "WHERE url=? ORDER BY id ASC", (url,)).fetchall()

    unchanged = bool(prior) and prior[-1][0] == digest
    first_of_this_version = None
    for row in prior:
        if row[0] == digest:
            first_of_this_version = row[1]
            break

    external_summary = ";".join("%s=%s" % (e["source"], e["reference"][:60]) for e in external)
    ev = {"user_id": "pub:" + digest[:16], "action": "publication_sealed", "amount": 0,
          "country": "UK", "device_id": "publish", "anomaly": 0, "device_risk": 0}
    res = {"decision": "PUBLICATION_SEALED", "score": 0, "publish_version": VERSION,
           "url": url, "content_hash": digest, "bytes": len(body),
           "http_status": status,
           "detail": "url=%s;sha256=%s;bytes=%d%s"
                     % (url, digest, len(body),
                        ";external=" + external_summary if external_summary else "")}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO publish_seal(api_key,url,content_hash,byte_length,http_status,"
            "content_type,note,external,fetched,audit_hash,block_index) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, digest, len(body), status, content_type or None,
             note or None,
             "|".join("%s %s %s" % (e["source"], e["reference"], e["claimed_time"] or "")
                      for e in external) or None,
             now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "url": url, "content_hash": digest, "bytes": len(body),
        "http_status": status, "content_type": content_type,
        "sealed_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "version_number": len(prior) + 1,
        "publish_version": VERSION,
        "what_this_proves": "This exact content was served at this address when we fetched it, "
                            "and the record of that cannot be altered afterwards.",
        "what_it_does_not": "It does not prove the page existed earlier than this moment. "
                            "Nothing can prove that after the fact - timestamps only run "
                            "forwards. Seal at publication and the question never arises.",
        "history": "/x/publish/history?url=" + url,
        "verify_this_block": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if unchanged:
        out["unchanged"] = True
        out["first_sealed_in_this_form"] = _iso(first_of_this_version)
        out["message"] = ("Identical to the last sealed version. The page has not changed since "
                          "%s and now has an additional dated witness." % _iso(first_of_this_version))
    elif prior:
        out["changed"] = True
        out["previous_hash"] = prior[-1][0]
        out["previous_sealed_at"] = _iso(prior[-1][1])
        out["message"] = ("The content has changed since the last seal. Both versions remain in "
                          "the chain - a revision history the publisher cannot edit.")
    else:
        out["message"] = ("First seal for this address. Every later seal builds a permanent, "
                          "dated revision history from here.")

    if external:
        out["external_references"] = external
        out["external_caveat"] = ("Recorded exactly as supplied and sealed with the block. We do "
                                  "not verify them and they are not our evidence - they are "
                                  "somebody else's record, named so you can check them at "
                                  "source.")
    else:
        out["advice"] = ("If this page was published before today, add external references - a "
                         "GitHub push event, a Wayback snapshot - and they will be sealed "
                         "alongside. Those carry an earlier date; a seal made now cannot.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _parse_external(blob):
    if not blob:
        return []
    out = []
    for line in blob.split("|"):
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append({"source": parts[0], "reference": parts[1],
                        "claimed_time": parts[2] if len(parts) > 2 and parts[2] else None})
    return out


def _history(ctx, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT content_hash,byte_length,fetched,audit_hash,block_index,note,external "
            "FROM publish_seal WHERE url=? ORDER BY id ASC LIMIT 500", (url,)).fetchall()
    if not rows:
        return {"error": "never_sealed", "url": url,
                "message": "No seal recorded for that address."}, 404

    versions, last_hash = [], None
    for content_hash, length, fetched, audit_hash, block_index, note, external in rows:
        versions.append({
            "content_hash": content_hash, "bytes": length,
            "sealed_at": _iso(fetched), "sealed_in_chain": audit_hash,
            "block_index": block_index, "note": note,
            "changed_from_previous": last_hash is not None and content_hash != last_hash,
            "external_references": _parse_external(external),
        })
        last_hash = content_hash

    distinct = len({v["content_hash"] for v in versions})
    return {"url": url, "seals": len(versions), "distinct_versions": distinct,
            "first_sealed": versions[0]["sealed_at"], "latest_sealed": versions[-1]["sealed_at"],
            "current_hash": versions[-1]["content_hash"],
            "versions": versions,
            "publish_version": VERSION,
            "what_this_is": "A dated revision history the publisher cannot edit. Each version is "
                            "its own block; altering or removing one breaks every block after it.",
            "limit": "The first seal fixes an upper bound, not a lower one. Anything published "
                     "before its first seal rests on external evidence, which is recorded here "
                     "but not verified by us."}, 200


def _verify(ctx, data):
    url = str(data.get("url", "")).strip()
    digest = str(data.get("hash", data.get("content_hash", ""))).strip().lower()
    if not digest or not HEX64.match(digest):
        return {"error": "hash_required",
                "message": "sha256 of AILEASH-PUBLISH-v1: followed by the exact bytes served"}, 400

    with ctx["lock"]:
        if url:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE url=? AND content_hash=? ORDER BY id ASC", (url, digest)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE content_hash=? ORDER BY id ASC", (digest,)).fetchall()

    if not rows:
        return {"sealed": False, "content_hash": digest, "url": url or None,
                "message": "We hold no seal for that exact content. Either it was never sealed, "
                           "or the content differs from what was - a single byte is enough."}, 404

    return {"sealed": True, "content_hash": digest,
            "url": rows[0][0], "times_sealed": len(rows),
            "first_sealed": _iso(rows[0][1]),
            "latest_sealed": _iso(rows[-1][1]),
            "sealed_in_chain": rows[0][2], "block_index": rows[0][3],
            "publish_version": VERSION,
            "what_this_proves": "Content with exactly this fingerprint was served at that "
                                "address no later than the first sealing time, and the record "
                                "of it has not been altered since.",
            "verify_the_block": "/x/consistency/ancestor?tip=" + rows[0][2]}, 200


def _list(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT url,COUNT(*),MIN(fetched),MAX(fetched),COUNT(DISTINCT content_hash) "
            "FROM publish_seal GROUP BY url ORDER BY MAX(fetched) DESC LIMIT 500").fetchall()
    return {"count": len(rows),
            "pages": [{"url": r[0], "seals": r[1], "first_sealed": _iso(r[2]),
                       "latest_sealed": _iso(r[3]), "distinct_versions": r[4],
                       "history": "/x/publish/history?url=" + r[0]} for r in rows],
            "publish_version": VERSION,
            "note": "Everything this platform has sealed about its own published pages. Ours is "
                    "in here too - a publisher who seals everyone's pages but not their own is "
                    "telling you something."}, 200


def _spec():
    return {
        "publish_version": VERSION,
        "content_hash": "sha256('AILEASH-PUBLISH-v1:' || exact_bytes_served) as lowercase hex",
        "no_normalisation": "The bytes are hashed exactly as served. Nothing is trimmed, "
                            "reordered or cleaned up first - a whitespace-tolerant hash would "
                            "be a hash of our opinion of the page rather than of the page.",
        "reproduce_it": "curl the URL, pipe the raw bytes through sha256 with that prefix, and "
                        "compare with what we sealed. If your bytes differ, the page changed.",
        "what_a_seal_proves": "That content with this exact fingerprint was served at this "
                              "address no later than the sealing time, and that the record has "
                              "not been altered since - it is a chain block like any other, "
                              "anchored externally and witnessed by peers.",
        "what_it_cannot_prove": "That the page existed before the seal. Timestamps run forwards "
                                "only. Any product implying otherwise is misdescribing what a "
                                "timestamp is.",
        "for_earlier_dates": {
            "github_push": "api.github.com/repos/<owner>/<repo>/events - the push timestamp is "
                           "recorded by GitHub, not the pusher, unlike commit author and "
                           "committer dates which are settable fields. Retained around 90 days, "
                           "so capture it while it exists.",
            "wayback": "archive.org/wayback/available - an independent party with no stake in "
                       "the dispute.",
            "status": "Both are recorded and sealed as supplied, and neither is verified by us. "
                      "They are somebody else's evidence, named so you can check them at source.",
        },
        "the_discipline": "Seal at publication. One call at the moment a page goes live means "
                          "the publication date never rests on anyone's word, anyone's git "
                          "history, or anyone's memory again.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "history":
            return _history(ctx, data)
        if action == "verify":
            return _verify(ctx, data)
        if action == "list":
            return _list(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "verify", "list"],
            "POST": ["seal (keyed)"]}, 404

```
