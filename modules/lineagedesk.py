"""
Lineage desk - a keyed page at /lineage-desk.

Exists because lineage declare is POST-with-a-key, and a phone browser address
bar can send neither. Own _lineagedesk_patched attribute so it composes with
console.py, packconsole.py, peerconsole.py and binddesk.py.

Arm after every deploy by hitting /x/lineagedesk/status.
"""

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "health"), ("GET", "spec")}

_patched = [False]

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lineage desk</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f5f5f5;color:#111}
h1{font-size:20px;margin:0 0 4px}
p.sub{margin:0 0 16px;color:#555;font-size:14px}
label{display:block;margin:12px 0 4px;font-size:14px;font-weight:500}
input,textarea,select{width:100%;padding:10px;font-size:15px;border:1px solid #ccc;
border-radius:6px;box-sizing:border-box;font-family:inherit}
textarea{min-height:90px;font-family:ui-monospace,monospace;font-size:13px}
button{width:100%;padding:12px;margin-top:12px;font-size:15px;font-weight:500;
border:0;border-radius:6px;background:#1a1a1a;color:#fff}
button.alt{background:#fff;color:#1a1a1a;border:1px solid #ccc}
.row{display:flex;gap:8px}
.row button{flex:1}
pre{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;
white-space:pre-wrap;word-break:break-all;font-size:12px;margin-top:16px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:16px}
small{color:#666;font-size:12px}
</style>
</head>
<body>
<h1>Lineage desk</h1>
<p class="sub">Declare what fed a decision, and read it back.</p>

<div class="card">
<label>API key</label>
<input id="key" type="password" placeholder="paste your key" autocomplete="off">
<small>Kept in this page only. Never sent anywhere but sebbi.pro.</small>
</div>

<div class="card">
<label>Decision receipt (the child, 64 hex)</label>
<input id="child" placeholder="audit hash of the decision" autocomplete="off">

<label>Input chain</label>
<input id="pchain" placeholder="aileash, mir, supplier-name" value="aileash" autocomplete="off">

<label>Input receipt (the parent, 64 hex)</label>
<input id="parent" placeholder="audit hash of what fed it" autocomplete="off">

<label>Role</label>
<select id="role">
<option>input</option><option>model</option><option>data</option>
<option>policy</option><option>document</option><option>upstream-decision</option>
<option>supplier</option><option>other</option>
</select>

<label>Their base address (optional)</label>
<input id="pbase" placeholder="https://supplier.example" autocomplete="off">

<label>Note (optional)</label>
<input id="note" placeholder="200 characters" autocomplete="off">

<button onclick="declareOne()">Declare this input</button>
</div>

<div class="card">
<label>Or paste a full declaration body</label>
<textarea id="raw" placeholder='{"receipt":"...","inputs":[{"chain":"mir","receipt":"..."}]}'></textarea>
<button class="alt" onclick="declareRaw()">Declare from JSON</button>
</div>

<div class="card">
<label>Read it back</label>
<div class="row">
<button class="alt" onclick="read('trace')">Trace up</button>
<button class="alt" onclick="read('impact')">Impact down</button>
</div>
<button class="alt" onclick="read('receipt')">Portable receipt</button>
<button class="alt" onclick="status()">Module status</button>
</div>

<pre id="out">Ready.</pre>

<script>
function val(id){return document.getElementById(id).value.trim();}
function show(o){document.getElementById('out').textContent =
  typeof o === 'string' ? o : JSON.stringify(o, null, 2);}

function post(body){
  var k = val('key');
  if(!k){show('Paste your API key first.');return;}
  show('Sending...');
  fetch('/x/lineage/declare', {
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},
    body:JSON.stringify(body)
  }).then(function(r){return r.json().then(function(j){
      return {http:r.status, response:j};});})
    .then(show).catch(function(e){show('Failed: '+e);});
}

function declareOne(){
  var child = val('child'), parent = val('parent');
  if(child.length !== 64){show('The decision receipt must be 64 hex characters.');return;}
  if(parent.length !== 64){show('The input receipt must be 64 hex characters.');return;}
  var item = {chain: val('pchain') || 'aileash', receipt: parent, role: val('role')};
  if(val('pbase')) item.base = val('pbase');
  if(val('note')) item.note = val('note');
  post({receipt: child, inputs: [item]});
}

function declareRaw(){
  var t = val('raw');
  if(!t){show('Nothing to send.');return;}
  var body;
  try{body = JSON.parse(t);}catch(e){show('That is not valid JSON: '+e);return;}
  post(body);
}

function read(action){
  var r = val('child');
  if(r.length !== 64){show('Put a 64 hex receipt in the decision receipt box.');return;}
  show('Reading...');
  fetch('/x/lineage/'+action+'?receipt='+encodeURIComponent(r))
    .then(function(x){return x.json();}).then(show)
    .catch(function(e){show('Failed: '+e);});
}

function status(){
  show('Reading...');
  fetch('/x/lineage/status').then(function(x){return x.json();})
    .then(show).catch(function(e){show('Failed: '+e);});
}
</script>
</body>
</html>"""


def _install_page(ctx):
    if _patched[0]:
        return "already installed"
    import sys
    s = sys.modules.get("__main__")
    if s is None or not hasattr(s, "get_bearer"):
        s = sys.modules.get("server")
    if s is None:
        return "server not found"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_lineagedesk_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.rstrip("/") == "/lineage-desk":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original(self)

    H.do_GET = do_GET
    H._lineagedesk_patched = True
    _patched[0] = True
    print("LINEAGEDESK: /lineage-desk installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    action = str(action or "status").strip().lower().strip("/")
    result = _install_page(ctx)

    if action in ("", "status", "health", "index"):
        return {"module": "lineagedesk", "version": VERSION, "ok": True,
                "page_install": result,
                "page": "https://sebbi.pro/lineage-desk",
                "note": "Hit this route after every deploy to arm the page."}, 200

    if action == "spec":
        return {"module": "lineagedesk", "version": VERSION,
                "what_it_does": "Serves a keyed page at /lineage-desk so lineage declarations "
                                "can be made from a phone, where a browser address bar cannot "
                                "send a POST or an Authorization header.",
                "page": "https://sebbi.pro/lineage-desk",
                "arm": "https://sebbi.pro/x/lineagedesk/status",
                "calls": ["POST /x/lineage/declare",
                          "GET /x/lineage/trace", "GET /x/lineage/impact",
                          "GET /x/lineage/receipt", "GET /x/lineage/status"]}, 200

    return {"error": "unknown_action", "action": action,
            "known_actions": ["status", "spec"]}, 404
