# Codebase — part 18 of 54

Contains:
- `modules/network.py`
- `modules/noexec.py`


## `modules/network.py`

487 lines, 19842 bytes

```python
"""
modules/network.py  -  serves the public witness network page

WHY THIS IS A MODULE AND NOT A TEMPLATE
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it - it would arrive as a JSON string. So this does the
same thing router.py already does for POST: it patches the request handler at
runtime, adds a branch for the page path, and leaves every other path exactly
as it was. The patch is idempotent and lives in memory, so a restart reverts it.

THE SAME CATCH AS THE POST PATCH
--------------------------------
A module is only imported when a request reaches the router. So after every
deploy, one request to /x/network/status has to arrive before /witness works.
Opening /x/network/status in a browser does it. Until then the page path falls
through to whatever the server did before, which is a 404 - not an error page,
just the old behaviour.

If you would rather not patch anything, the same HTML works as a plain file in
static/. This exists because the page then lives with the module it describes
rather than drifting away from it.

ROUTES
------
  GET /witness            the page
  GET /witness.html       same page
  GET /x/network/status   whether the patch is installed (public)

The page itself holds no data. It reads /x/witness/tip and /x/witness/peers
from the browser, same as any other visitor would, so it cannot show anything
a stranger could not verify for themselves.
"""

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/witness", "/witness.html", "/network")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The witness network — AILeash</title>
<meta name="description" content="Two independent platforms recording each other's records, hourly. Checkable by anyone, without an account.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,600&family=Inter+Tight:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#E9EDE4;
  --paper-deep:#DFE5D8;
  --ink:#18241F;
  --ink-soft:#4A5A52;
  --rule:#BFCCBF;
  --rule-strong:#9AAC9C;
  --stamp:#7C2B38;
  --verdigris:#2F6B5E;
  --amber:#9A6B1F;
  --gutter:#CBD6C8;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--paper);
  color:var(--ink);
  font-family:"Inter Tight",system-ui,sans-serif;
  font-size:17px;
  line-height:1.6;
  /* ruled paper, faint */
  background-image:repeating-linear-gradient(
    to bottom,
    transparent 0 31px,
    rgba(154,172,156,.20) 31px 32px
  );
}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}

/* ---------- masthead ---------- */
.masthead{padding:52px 0 30px;border-bottom:2px solid var(--ink)}
.eyebrow{
  font-family:"IBM Plex Mono",monospace;
  font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink-soft);margin:0 0 18px;
}
h1{
  font-family:Fraunces,Georgia,serif;
  font-weight:600;font-size:clamp(2.5rem,7.5vw,4.6rem);
  line-height:1.02;letter-spacing:-.02em;margin:0 0 20px;
}
h1 em{font-style:italic;font-weight:300}
.standfirst{font-size:clamp(1.05rem,2.4vw,1.28rem);max-width:40ch;color:var(--ink-soft);margin:0}

/* ---------- the spread ---------- */
.spread{
  margin:44px 0 8px;
  border:1px solid var(--rule-strong);
  background:rgba(255,255,255,.4);
}
.spread-head{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule-strong);
}
.spread-head div{
  font-family:"IBM Plex Mono",monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  padding:12px 16px;color:var(--ink-soft);
}
.spread-head .mid{text-align:center;background:var(--gutter);color:var(--ink)}
.spread-head .right{text-align:right}
.folio{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule);
}
.folio:last-child{border-bottom:0}
.side{padding:20px 16px;min-width:0}
.side.right{text-align:right}
.mid{
  background:var(--gutter);
  display:flex;align-items:center;justify-content:center;
  font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-soft);
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
}
.chain-name{
  font-family:Fraunces,Georgia,serif;font-size:1.35rem;font-weight:600;
  margin:0 0 4px;letter-spacing:-.01em;
}
.role{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-soft);margin:0 0 14px}
.hash{
  font-family:"IBM Plex Mono",monospace;font-size:12.5px;
  word-break:break-all;color:var(--ink);margin:0 0 3px;line-height:1.45;
}
.hash-label{font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 5px}
.meta{font-size:14px;color:var(--ink-soft);margin:12px 0 0}
.meta b{color:var(--ink);font-weight:600}

/* ---------- stamp ---------- */
.stamp{
  display:inline-block;margin-top:16px;padding:6px 13px 5px;
  border:2.5px solid var(--stamp);color:var(--stamp);
  font-family:"IBM Plex Mono",monospace;font-weight:500;
  font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  transform:rotate(-3.5deg);opacity:.9;
}
.stamp.press{animation:press .5s cubic-bezier(.2,1.5,.4,1) both}
@keyframes press{
  0%{opacity:0;transform:rotate(-3.5deg) scale(1.5)}
  70%{opacity:.95;transform:rotate(-3.5deg) scale(.97)}
  100%{opacity:.9;transform:rotate(-3.5deg) scale(1)}
}
.stamp.live{border-color:var(--verdigris);color:var(--verdigris)}
.stamp.weak{border-color:var(--amber);color:var(--amber)}
.stamp.flag{background:var(--stamp);color:var(--paper)}

/* ---------- sections ---------- */
section{padding:56px 0;border-top:1px solid var(--rule-strong)}
h2{
  font-family:Fraunces,Georgia,serif;font-weight:600;
  font-size:clamp(1.6rem,4vw,2.3rem);letter-spacing:-.015em;
  margin:0 0 8px;line-height:1.15;
}
.sec-note{color:var(--ink-soft);max-width:56ch;margin:0 0 30px}
p{max-width:62ch}

.defs{display:grid;gap:0;border-top:1px solid var(--rule)}
.def{
  display:grid;grid-template-columns:170px 1fr;gap:20px;
  padding:15px 0;border-bottom:1px solid var(--rule);
}
.def dt{
  font-family:"IBM Plex Mono",monospace;font-size:12px;
  letter-spacing:.1em;text-transform:uppercase;padding-top:3px;
}
.def dd{margin:0;color:var(--ink-soft)}
.dot{display:inline-block;width:8px;height:8px;margin-right:8px;border-radius:50%;vertical-align:middle}
.dot.ok{background:var(--stamp)}
.dot.mid-c{background:var(--verdigris)}
.dot.weak{background:var(--amber)}

.limits li{max-width:62ch;margin-bottom:13px;color:var(--ink-soft)}
.limits b{color:var(--ink)}

pre{
  font-family:"IBM Plex Mono",monospace;font-size:13px;line-height:1.7;
  background:var(--ink);color:var(--paper);padding:20px;overflow-x:auto;
  border:0;margin:22px 0;
}
pre .k{color:#9FC6B4}
code{font-family:"IBM Plex Mono",monospace;font-size:.92em}

.links{list-style:none;padding:0;margin:24px 0 0}
.links li{border-bottom:1px solid var(--rule);padding:13px 0}
.links a{
  font-family:"IBM Plex Mono",monospace;font-size:13.5px;
  color:var(--ink);text-decoration:none;word-break:break-all;
  display:flex;justify-content:space-between;gap:16px;align-items:baseline;
}
.links a:hover,.links a:focus-visible{color:var(--stamp)}
.links span{color:var(--ink-soft);font-family:"Inter Tight",sans-serif;
  font-size:13px;flex:0 0 auto;text-align:right}

footer{padding:40px 0 70px;color:var(--ink-soft);font-size:14px}
footer a{color:var(--ink)}

.loading,.errbox{
  font-family:"IBM Plex Mono",monospace;font-size:13px;
  color:var(--ink-soft);padding:26px 16px;
}
.errbox b{display:block;color:var(--ink);margin-bottom:6px;font-family:"Inter Tight",sans-serif;font-size:15px}

a:focus-visible,button:focus-visible{outline:2.5px solid var(--stamp);outline-offset:3px}

@media (max-width:760px){
  body{background-image:none}
  .spread-head,.folio{grid-template-columns:1fr}
  .spread-head .mid,.folio .mid{
    border-left:0;border-right:0;
    border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
    padding:7px 0;text-align:center;
  }
  .spread-head .right,.side.right{text-align:left}
  .spread-head div{padding:9px 14px}
  .def{grid-template-columns:1fr;gap:5px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>
</head>
<body>

<div class="wrap">

  <header class="masthead">
    <p class="eyebrow">AILeash · the witness network</p>
    <h1>Two ledgers.<br><em>Neither one is the authority.</em></h1>
    <p class="standfirst">Independent platforms record each other's records, every hour. You can check it yourself, right now, without an account.</p>
  </header>

  <div class="spread" id="spread">
    <div class="spread-head">
      <div>This chain</div>
      <div class="mid">Exchange</div>
      <div class="right">Recorded by</div>
    </div>
    <div id="folios">
      <div class="loading">Reading the ledger…</div>
    </div>
  </div>

  <section>
    <h2>Why this exists</h2>
    <p class="sec-note">Every platform that sells you an audit trail also holds it.</p>
    <p>A hash chain stops anyone else altering the record. It does not stop the operator rebuilding the whole thing and presenting the result as history. Anchoring the chain externally narrows that down — you can't rewrite anything older than your last anchor — and it still leaves the keeper and the checker as the same party.</p>
    <p>Nothing you build alone closes that. Somebody outside has to be holding a copy.</p>
    <p>So each platform here takes the fingerprint of the others' records and seals it into its own. To rewrite your past now, everyone holding a copy would have to rewrite theirs in step, and re-obtain external timestamps that were issued days ago. The second half is the part that can't be done.</p>
  </section>

  <section>
    <h2>What the marks mean</h2>
    <p class="sec-note">Two checks run on every submission. Neither can reject one — everything gets sealed. What changes is how strong we say the claim is.</p>

    <dl class="defs">
      <div class="def"><dt><span class="dot ok"></span>Confirmed</dt><dd>We fetched the address given and it served exactly the tip that was submitted.</dd></div>
      <div class="def"><dt><span class="dot mid-c"></span>Live</dt><dd>The address served a valid but different tip. A working chain moves between submitting and our looking — normal, not a failure.</dd></div>
      <div class="def"><dt><span class="dot weak"></span>Self-declared</dt><dd>No address given, or we couldn't reach it. Taken on their word, and marked as such.</dd></div>
      <div class="def"><dt>First-use</dt><dd>First time this name appeared. It's now bound to the address it came from.</dd></div>
      <div class="def"><dt>Bound</dt><dd>Same address as the first time this name appeared. The same operator, consistently.</dd></div>
      <div class="def"><dt>Conflict</dt><dd>This name has been submitted from a different address than the one it was first bound to. Still sealed, permanently flagged. Operators do move hosts — but you get to see it and decide.</dd></div>
    </dl>
  </section>

  <section>
    <h2>What this does not prove</h2>
    <p class="sec-note">Said plainly, because the value of the rest depends on it.</p>
    <ul class="limits">
      <li><b>It doesn't prove a record was true when it was written.</b> Nothing can. No system reaches back to verify what someone was thinking or whether the data going in was honest. This proves what was recorded, when, and that it hasn't changed since.</li>
      <li><b>It doesn't prove identity.</b> A name is self-declared. Checking the address proves someone runs a live chain producing that data — not that they're who they say. Binding a name to its first address is what makes a change visible.</li>
      <li><b>Two platforms checking each other isn't much of a network.</b> The strength comes from breadth. This gets meaningfully harder to bend with every chain that joins, and not before.</li>
      <li><b>A participant can go quiet.</b> Nobody can force anyone to keep publishing. Gaps show up as stale or silent rather than disappearing, which is the point.</li>
    </ul>
  </section>

  <section>
    <h2>Joining</h2>
    <p class="sec-note">Chains submit their current head to the network and record the heads of others in return.</p>
    <pre><span class="k">POST</span> https://sebbi.pro/x/witness/observe
<span class="k">Content-Type:</span> application/json

{
  "chain": "your-chain-name",
  "tip":   "&lt;64 hex characters — your current chain head&gt;",
  "url":   "https://yoursite/your/tip",
  "ts":    "2026-08-02T14:00:00Z"
}</pre>
    <p><code>url</code> is the address we fetch to check your tip independently — it's the difference between confirmed and self-declared. <code>ts</code> is optional, epoch or ISO.</p>
    <p>Running a chain in the other direction, recording ours as we record yours, is what makes it mutual rather than us keeping a list. If you operate a platform in this space and you're willing to have your history held somewhere you don't control, message me and we'll talk through it and what it costs.</p>
  </section>

  <section>
    <h2>Check it yourself</h2>
    <p class="sec-note">Nothing here needs a login. Open any of these.</p>
    <ul class="links">
      <li><a href="/x/witness/tip">/x/witness/tip<span>our current head</span></a></li>
      <li><a href="/x/witness/peers">/x/witness/peers<span>everyone we record</span></a></li>
      <li><a href="/api/verify-chain">/api/verify-chain<span>chain checked end to end</span></a></li>
      <li><a href="/api/anchor-status">/api/anchor-status<span>the external timestamp</span></a></li>
    </ul>
  </section>

  <footer>
    <p>Sealed records and their attestations are held by each participating platform independently. AILeash operates one chain in this network; it does not run the network. — <a href="https://sebbi.pro">sebbi.pro</a></p>
  </footer>

</div>

<script>
(function(){
  var folios = document.getElementById('folios');

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function stampFor(liveness, nameStatus){
    var cls = 'stamp press', text = String(liveness || 'unchecked');
    if (liveness === 'confirmed') cls += '';
    else if (liveness === 'live') cls += ' live';
    else cls += ' weak';
    if (nameStatus === 'conflict'){ cls += ' flag'; text = 'conflict'; }
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }

  function ago(hours){
    if (hours == null) return 'unknown';
    if (hours < 1) return 'within the hour';
    if (hours < 2) return 'an hour ago';
    if (hours < 48) return Math.round(hours) + ' hours ago';
    return Math.round(hours / 24) + ' days ago';
  }

  function render(ours, peers){
    if (!peers || !peers.length){
      folios.innerHTML = '<div class="errbox"><b>No chains recorded yet.</b>' +
        'Nothing has been submitted to this chain. The first tip posted to ' +
        '/x/witness/observe appears here.</div>';
      return;
    }
    var html = '';
    peers.forEach(function(p){
      html += '<div class="folio">' +
        '<div class="side">' +
          '<p class="chain-name">' + esc(ours.name) + '</p>' +
          '<p class="role">head of chain · height ' + esc(ours.height) + '</p>' +
          '<p class="hash-label">Current tip</p>' +
          '<p class="hash">' + esc(ours.tip) + '</p>' +
          '<p class="meta">Sealed <b>' + esc(ours.sealed) + '</b></p>' +
        '</div>' +
        '<div class="mid">↔</div>' +
        '<div class="side right">' +
          '<p class="chain-name">' + esc(p.peer) + '</p>' +
          '<p class="role">' + esc(p.observations) + ' observations · ' +
              esc(p.distinct_tips) + ' distinct tips</p>' +
          '<p class="hash-label">Name bound to</p>' +
          '<p class="hash">' + esc(p.bound_to || 'no address supplied') + '</p>' +
          '<p class="meta">Last recorded <b>' + esc(ago(p.hours_since_last)) + '</b> · ' +
              esc(p.name_status || 'unchecked') + '</p>' +
          stampFor(p.liveness, p.name_status) +
        '</div>' +
      '</div>';
    });
    folios.innerHTML = html;
  }

  function failed(){
    folios.innerHTML = '<div class="errbox"><b>The ledger did not answer.</b>' +
      'The endpoints are public, so you can try them directly: ' +
      '<a href="/x/witness/peers">/x/witness/peers</a></div>';
  }

  Promise.all([
    fetch('/x/witness/tip').then(function(r){ return r.json(); }),
    fetch('/x/witness/peers').then(function(r){ return r.json(); })
  ]).then(function(res){
    var tip = res[0] || {}, peers = res[1] || {};
    render({
      name: 'aileash',
      tip: tip.tip || 'unavailable',
      height: tip.height == null ? '—' : tip.height,
      sealed: tip.sealed_at ? new Date(tip.sealed_at).toUTCString().replace(' GMT','  UTC') : 'unknown'
    }, peers.peers || []);
  }).catch(failed);
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
    """Add a page branch to do_GET at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_page_patched", False):
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
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._page_patched = True
    _patched[0] = True
    print("NETWORK: /witness page branch installed at runtime", flush=True)
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
            print("NETWORK: page patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/witness",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": "The page reads /x/witness/tip and /x/witness/peers from the browser. It holds no data of its own.",
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404

```


## `modules/noexec.py`

490 lines, 22739 bytes

```python
"""
modules/noexec.py  v1.1.0
The NO-EXEC blind bundle: six real objects from the live system, each one
authentic, each one attached to a claim it may not support.

Arm after each deploy:  https://sebbi.pro/x/noexec/status

    GET /x/noexec/build              mint the six objects on the live chain,
                                     pack them into one bundle, seal the
                                     bundle fingerprint and a salted
                                     commitment to the answer key, and hand
                                     back the links (one build per 10 minutes)
    GET /x/noexec/bundle?id=         the bundle exactly as sent: claims and
                                     objects only, no verdicts, no hints
    GET /x/noexec/reveal?id=&secret= the answer key plus its salt, so anyone
                                     can recompute the sealed commitment
    GET /x/noexec/reveal?id=&admin=  the operator's own unlock (ADMIN_PASSWORD), for
                                     when the reveal link is lost. It publishes the
                                     key: from then on the plain link works for anyone
                                     and the reveal itself is sealed in the chain
    GET /x/noexec/status             module status

How the six are made (nothing faked, nothing edited afterwards):
  1  a passport minted, then redeemed once, redemption sealed
  2  a passport minted, then its grant revoked, revocation sealed
  3  a passport minted for one site, never presented anywhere
  4  a signed authority proof bundle for an ALLOW evaluation whose grant
     window is fifteen minutes long
  5  the sealed Temporal Standing Test evidence package, run r_72d2d93a5c2a4988
  6  the latest self-proving archive file and the sealed custody count

Built on continuity.py (1.6.0+) and passport.py. Neither is changed.
"""

import hashlib
import importlib
import importlib.util
import json
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.1.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "build"), ("GET", "bundle"), ("GET", "reveal")}

SITE = "https://sebbi.pro"
KEY = "noexec-blind-bundle"
GAP = 600
CAP = "noexec.pay"
TAGS = ["noexec"]
AUD = "checkout.sebbi.pro"
AUD_OTHER = "bookings.sebbi.pro"
PARAMS = {"amount": 20}
TST_RUN = "r_72d2d93a5c2a4988"
TST_REVIEW = "https://studio.moralclarity.ai/temporal-standing-test"

_ready = False
_last = [0.0]


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _block_url(n):
    return SITE + "/x/walk/block?index=%s" % n if n is not None else None


def _load(name, must_have):
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith(os.sep + name + ".py") and all(hasattr(m, a) for a in must_have):
            return m
    pkg = __package__ or ""
    try:
        m = importlib.import_module(pkg + "." + name if pkg else name)
        if all(hasattr(m, a) for a in must_have):
            return m
    except Exception:
        pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("noexec_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _call(name, action, data, ctx):
    """Ask another live module for one of its public answers. Never raises."""
    try:
        m = _load(name, ("handle",))
        out = m.handle("GET", action, data, None, ctx)
        body = out[0] if isinstance(out, tuple) else out
        return body if isinstance(body, dict) else {"raw": str(body)[:4000]}
    except Exception as e:
        return {"unavailable": str(e)[:200]}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS noexec_bundle(id TEXT PRIMARY KEY,created REAL,"
                  "bundle TEXT,bundle_sha256 TEXT,answer_key TEXT,key_commitment TEXT,"
                  "secret_digest TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS noexec_revealed(id TEXT PRIMARY KEY,at REAL,"
                  "how TEXT,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _seal(ctx, kind, extra):
    ev = {"user_id": "noexec:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "noexec", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "noexec_version": VERSION}
    res.update(extra)
    out = ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _grant(C, ctx, gid, subject, now):
    g = {"id": gid, "issuer": "justin-dobson", "issuer_kind": "human", "subject": subject,
         "scope": [CAP], "constraints": {"max_amount": 50},
         "purpose": "NO-EXEC blind bundle for independent review", "purpose_tags": TAGS,
         "not_after": now + 900}
    r, s = C._issue(ctx, KEY, g)
    if s != 200:
        raise RuntimeError("grant %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _mint(P, C, ctx, gid, audience):
    r, s = P._mint(ctx, C, KEY, {"grant": gid, "action": CAP, "params": PARAMS,
                                 "purpose_tag": TAGS[0], "audience": audience})
    if s != 200 or not r.get("issued"):
        raise RuntimeError("passport for %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _passport_sources(token, gid, issued_block):
    return {"live_check": SITE + "/x/passport/verify?token=" + token,
            "token_format": SITE + "/x/passport/spec",
            "public_key": SITE + "/x/continuity/pubkey",
            "grant_lineage": SITE + "/x/continuity/trace?grant=" + gid,
            "issued_in_block": _block_url(issued_block)}


def _build(ctx):
    now = time.time()
    if now - _last[0] < GAP:
        return {"error": "too_soon", "retry_after_seconds": int(GAP - (now - _last[0]))}, 429
    _last[0] = now
    C = _load("continuity", ("_issue", "_evaluate", "_revoke", "_proof", "_confirm"))
    P = _load("passport", ("_mint", "_redeem", "_check"))
    C._setup(ctx)
    P._setup(ctx)

    tag = uuid.uuid4().hex[:10]
    agent = "agent-" + tag
    cases, key = [], []

    # 1 - the spent passport
    g1 = "nx_%s_1" % tag
    _grant(C, ctx, g1, agent, now)
    p1 = _mint(P, C, ctx, g1, AUD)
    r1, _s = P._redeem(ctx, C, {"token": p1["passport"], "audience": AUD, "params": PARAMS})
    if not r1.get("redeemed"):
        raise RuntimeError("case 1 redemption did not bind: %s" % _canon(r1)[:300])
    cases.append({"case": 1,
                  "claim": "This agent is authorised to perform this action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p1["passport"]},
                  "sources": _passport_sources(p1["passport"], g1, p1.get("block_index"))})
    key.append({"case": 1, "verdict": "NOT PROVEN",
                "what_it_proves": "Authorised once, for %s of %s at %s." % (CAP, _canon(PARAMS), AUD),
                "why_not": "Already redeemed; the redemption is sealed in block %s. Nothing "
                           "authorises a further execution." % r1.get("block_index"),
                "evidence": [_block_url(r1.get("block_index"))]})

    # 2 - the revoked passport
    g2 = "nx_%s_2" % tag
    _grant(C, ctx, g2, agent, now)
    p2 = _mint(P, C, ctx, g2, AUD)
    rv, _s = C._revoke(ctx, KEY, {"grant": g2, "reason": "human withdrew the authority"})
    cases.append({"case": 2,
                  "claim": "This agent was authorised at the moment of action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p2["passport"]},
                  "sources": _passport_sources(p2["passport"], g2, p2.get("block_index"))})
    key.append({"case": 2, "verdict": "NOT PROVEN",
                "what_it_proves": "The signature is genuine and the passport was in date: an "
                                  "offline verifier says VALID.",
                "why_not": "The grant behind it was revoked (block %s) after issue. Standing is "
                           "lost, so no moment of action after that is authorised. Signature "
                           "validity is not standing." % rv.get("block_index"),
                "evidence": [_block_url(rv.get("block_index")),
                             SITE + "/x/continuity/trace?grant=" + g2]})

    # 3 - the misdirected passport (never presented anywhere, so still unspent)
    g3 = "nx_%s_3" % tag
    _grant(C, ctx, g3, agent, now)
    p3 = _mint(P, C, ctx, g3, AUD_OTHER)
    cases.append({"case": 3,
                  "claim": "This agent is authorised to act at %s." % AUD,
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p3["passport"]},
                  "sources": _passport_sources(p3["passport"], g3, p3.get("block_index"))})
    key.append({"case": 3, "verdict": "NOT PROVEN",
                "what_it_proves": "Genuine, unspent and unrevoked authority at %s." % AUD_OTHER,
                "why_not": "The passport's audience is %s. It says nothing about %s."
                           % (AUD_OTHER, AUD),
                "evidence": [SITE + "/x/passport/spec"]})

    # 4 - the signed proof of a past ALLOW
    g4 = "nx_%s_4" % tag
    gr4 = _grant(C, ctx, g4, agent, now)
    ev, s = C._evaluate(ctx, KEY, {"grant": g4, "action": CAP, "params": PARAMS,
                                   "purpose_tag": TAGS[0]})
    if s != 200 or ev.get("verdict") != "ALLOW":
        raise RuntimeError("case 4 evaluation was not ALLOW: %s" % _canon(ev)[:300])
    proof, s = C._proof(ctx, {"evaluation": ev["evaluation"]})
    if s != 200:
        raise RuntimeError("case 4 proof not produced: %s" % _canon(proof)[:300])
    cases.append({"case": 4,
                  "claim": "This agent holds this authority.",
                  "object": {"authority_proof": proof},
                  "sources": {"proof": SITE + "/x/continuity/proof?evaluation=" + ev["evaluation"],
                              "public_key": SITE + "/x/continuity/pubkey",
                              "derivation_rules": SITE + "/x/continuity/spec",
                              "grant_lineage": SITE + "/x/continuity/trace?grant=" + g4}})
    key.append({"case": 4, "verdict": "NOT PROVEN",
                "what_it_proves": "Authority stood, and the ALLOW re-derives from the lineage, at "
                                  "%s." % ev.get("evaluated_at", _iso(now)),
                "why_not": "A proof of an instant says nothing about now. The grant's window "
                           "closes at %s; any present-tense claim needs a live standing check."
                           % gr4.get("not_after"),
                "evidence": [SITE + "/x/continuity/trace?grant=" + g4]})

    # 5 - the real test, the narrower finding
    tst = _call("standing", "evidence", {"run": TST_RUN}, ctx)
    cases.append({"case": 5,
                  "claim": "sebbi.pro passed the Temporal Standing Test.",
                  "object": {"evidence_package": tst},
                  "sources": {"evidence": SITE + "/x/standing/evidence?run=" + TST_RUN,
                              "freeze_sealed_in": _block_url(2387),
                              "run_sealed_in": _block_url(2398),
                              "test_definition": TST_REVIEW}})
    key.append({"case": 5, "verdict": "NOT PROVEN",
                "what_it_proves": "A pre-registered run, freeze sealed before execution (block "
                                  "2387 before 2398), both branches recorded as observed.",
                "why_not": "The independent reviewer's finding is narrower than the package's "
                           "own 'PASS': revocation-aware authorisation and execution binding "
                           "ESTABLISHED; temporal standing on external facts (a still-valid "
                           "grant defeated by a change in an authoritative external fact) NOT "
                           "YET ESTABLISHED. The object is authentic; its summary overstates "
                           "what it supports.",
                "evidence": [SITE + "/x/standing/evidence?run=" + TST_RUN, TST_REVIEW]})

    # 6 - the archive with no custodians
    man = _call("archive", "manifest", {}, ctx)
    files = man.get("files") if isinstance(man, dict) else None
    latest = files[0] if isinstance(files, list) and files else man
    cus = _call("custody", "status", {}, ctx)
    cases.append({"case": 6,
                  "claim": "sebbi.pro's record is held independently.",
                  "object": {"archive_file": latest, "custody": cus},
                  "sources": {"archive_manifest": SITE + "/x/archive/manifest",
                              "archive_file": (latest or {}).get("file") if isinstance(latest, dict) else None,
                              "sealed_in": (latest or {}).get("check_block") if isinstance(latest, dict) else None,
                              "custody_count": SITE + "/x/custody/status"}})
    key.append({"case": 6, "verdict": "NOT PROVEN",
                "what_it_proves": "Integrity: the file is content-addressed, sealed in the chain, "
                                  "and its embedded verifier passes.",
                "why_not": "Independence: the sealed custody count of holders other than "
                           "sebbi.pro is %s." % _custody_count(cus),
                "evidence": [SITE + "/x/custody/status"]})

    for c in cases:
        c["object_sha256"] = _sha(c["object"])

    bid = "nx_" + tag
    captured = _iso(time.time())
    bundle = {
        "bundle": bid,
        "format": "noexec-blind-bundle/1",
        "issuer": "sebbi.pro",
        "captured_at": captured,
        "instructions": "Six objects taken from the live system. Each is presented with the "
                        "claim being made with it and nothing else. Fetch every source "
                        "yourself rather than trusting this copy; each object carries the "
                        "SHA-256 of its canonical JSON (keys sorted, separators ',' ':').",
        "format_notes": {
            "passport": "sbp1.<base64url body>.<base64url Ed25519 signature>; the signature "
                        "is over 'AILEASH-PASSPORT-v1:' || body bytes. Passports carry a "
                        "5-minute validity window (exp).",
            "chain_blocks": SITE + "/x/walk/block?index=<n>",
        },
        "cases": cases,
    }
    bundle_sha = _sha(bundle)

    salt = secrets.token_hex(32)
    answer = {"bundle": bid, "bundle_sha256": bundle_sha, "salt": salt, "answers": key}
    commitment = _sha(answer)
    secret = secrets.token_urlsafe(18)
    audit_hash, block = _seal(ctx, "noexec_bundle_committed",
                              {"bundle": bid, "bundle_sha256": bundle_sha,
                               "answer_key_commitment": commitment,
                               "detail": "bundle=%s;sha256=%s;key_commitment=%s"
                                         % (bid, bundle_sha, commitment)})
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO noexec_bundle VALUES(?,?,?,?,?,?,?,?,?)",
                            (bid, time.time(), _canon(bundle), bundle_sha, _canon(answer),
                             commitment, hashlib.sha256(secret.encode()).hexdigest(),
                             audit_hash, block))
        ctx["conn"].commit()
    return {"built": True, "bundle": bid,
            "send_this_link": SITE + "/x/noexec/bundle?id=" + bid,
            "bundle_sha256": bundle_sha,
            "answer_key_commitment": commitment,
            "sealed_in_chain": audit_hash, "block_index": block,
            "check_the_seal": _block_url(block),
            "reveal_later_keep_private": SITE + "/x/noexec/reveal?id=%s&secret=%s" % (bid, secret),
            "note": "Send only the bundle link. Keep the reveal link to yourself until the "
                    "reviewer has published results."}, 200


def _custody_count(cus):
    if not isinstance(cus, dict):
        return "unavailable"
    for k in ("independent_holders_today", "independent_holders", "holders_today", "count",
              "independent"):
        if k in cus:
            return cus[k]
    for v in cus.values():
        if isinstance(v, dict):
            for k in ("independent_holders", "count", "holders"):
                if k in v:
                    return v[k]
    return "as sealed at " + SITE + "/x/custody/status"


def _query(ctx):
    """Read the query string straight off the live request, whatever the router passed:
    from the handler in ctx if there is one, otherwise from the request handler found on
    the call stack (the same way page modules find it)."""
    from urllib.parse import parse_qs
    paths = []
    try:
        if isinstance(ctx, dict):
            for k in ("handler", "h", "request_handler", "request"):
                h = ctx.get(k)
                if h is not None and getattr(h, "path", None):
                    paths.append(h.path)
        f = sys._getframe()
        while f is not None:
            o = f.f_locals.get("self")
            if o is not None and hasattr(o, "wfile") and isinstance(getattr(o, "path", None), str):
                paths.append(o.path)
                break
            f = f.f_back
    except Exception:
        pass
    for path in paths:
        if "?" in path:
            return {k: v[0] for k, v in parse_qs(path.split("?", 1)[1]).items()}
    return {}


def _q(data, k):
    v = data.get(k, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v).strip()


def _get(ctx, bid):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT id,created,bundle,bundle_sha256,answer_key,key_commitment,secret_digest,"
            "audit_hash,block_index FROM noexec_bundle WHERE id=?", (bid,)).fetchone()


def _bundle(ctx, data):
    row = _get(ctx, _q(data, "id"))
    if not row:
        return {"error": "bundle_not_found"}, 404
    return {"bundle": json.loads(row[2]), "bundle_sha256": row[3],
            "answer_key_commitment": row[5],
            "commitment_sealed_in_chain": row[7], "commitment_block": _block_url(row[8]),
            "commitment_rule": "SHA-256 of the canonical JSON of the answer key, which includes "
                               "this bundle's SHA-256 and a random salt. It was sealed before "
                               "this bundle was sent and will be revealed after review."}, 200


def _reveal(ctx, data):
    import hmac
    bid = _q(data, "id")
    row = _get(ctx, bid)
    if not row:
        return {"error": "bundle_not_found"}, 404
    with ctx["lock"]:
        pub = ctx["conn"].execute("SELECT at,how,audit_hash,block_index FROM noexec_revealed "
                                  "WHERE id=?", (bid,)).fetchone()
    secret = _q(data, "secret")
    admin = _q(data, "admin")
    pw = os.environ.get("ADMIN_PASSWORD", "")
    by_secret = bool(secret) and hashlib.sha256(secret.encode()).hexdigest() == row[6]
    by_admin = bool(admin) and bool(pw) and hmac.compare_digest(admin, pw)
    if not (pub or by_secret or by_admin):
        return {"error": "not_yet_revealed"}, 403
    if not pub:
        how = "reveal link" if by_secret else "operator unlock (reveal link lost)"
        audit_hash, block = _seal(ctx, "noexec_key_revealed",
                                  {"bundle": bid, "answer_key_commitment": row[5],
                                   "how": how,
                                   "detail": "bundle=%s;revealed_by=%s" % (bid, how)})
        with ctx["lock"]:
            ctx["conn"].execute("INSERT OR IGNORE INTO noexec_revealed VALUES(?,?,?,?,?)",
                                (bid, time.time(), how, audit_hash, block))
            ctx["conn"].commit()
        pub = (time.time(), how, audit_hash, block)
    answer = json.loads(row[4])
    return {"answer_key": answer, "recomputed_commitment": _sha(answer),
            "sealed_commitment": row[5], "matches": _sha(answer) == row[5],
            "commitment_sealed_in": _block_url(row[8]),
            "revealed": {"at": _iso(pub[0]), "how": pub[1], "sealed_in": _block_url(pub[3])},
            "share_this_link": SITE + "/x/noexec/reveal?id=" + bid,
            "check_it_yourself": "SHA-256 of the canonical JSON of answer_key (keys sorted, "
                                 "separators ',' ':', UTF-8) must equal sealed_commitment, "
                                 "which was sealed before the bundle was sent."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/")
    data = dict(data or {})
    if "?" in action:
        from urllib.parse import parse_qs
        action, qs = action.split("?", 1)
        for k, v in parse_qs(qs).items():
            data.setdefault(k, v[0])
    for k, v in _query(ctx).items():
        if not _q(data, k):
            data[k] = v
    action = action.strip("/")
    parts = action.split("/")
    if len(parts) > 1:
        action = parts[0]
        if not _q(data, "id"):
            data["id"] = parts[1]
        if len(parts) > 2 and not _q(data, "secret"):
            data["secret"] = parts[2]
    action = action.lower()
    if action in ("status", "spec", ""):
        with ctx["lock"]:
            n = ctx["conn"].execute("SELECT COUNT(*) FROM noexec_bundle").fetchone()[0]
            last = ctx["conn"].execute("SELECT id,block_index FROM noexec_bundle ORDER BY created "
                                       "DESC LIMIT 3").fetchall()
        return {"module": "noexec", "version": VERSION, "armed": True, "bundles_built": n,
                "latest": [{"bundle": r[0], "link": SITE + "/x/noexec/bundle?id=" + r[0],
                            "sealed_block": r[1]} for r in last],
                "build": SITE + "/x/noexec/build"}, 200
    if action == "build":
        try:
            return _build(ctx)
        except Exception as e:
            _last[0] = 0.0
            return {"built": False, "error": str(e)[:500]}, 500
    if action == "bundle":
        return _bundle(ctx, data)
    if action == "reveal":
        return _reveal(ctx, data)
    return {"error": "unknown_action", "GET": ["status", "build", "bundle", "reveal"]}, 404

```
