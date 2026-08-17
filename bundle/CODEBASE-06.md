# Codebase — part 6 of 20

Contains:
- `modules/network.py`
- `modules/oversight.py`
- `modules/pack.py`
- `modules/packconsole.py`
- `modules/peer.py`
- `modules/peerconsole.py`


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


## `modules/oversight.py`

249 lines, 11339 bytes

```python
"""
Human oversight notary - /x/oversight/<action>

THE PROBLEM
-----------
Nobody can prove a person thought about a decision. That is an internal state
and no amount of logging reaches it. Any vendor claiming to prove genuine
human oversight is overselling.

But rubber stamping is not an internal state. It is a pattern, and patterns
leave marks - if you record the right things, in the right order, at the time.

WHAT THIS DOES
--------------
Three things, none of which claim to read minds.

1. ORDER. The reviewer's own call is sealed BEFORE the machine's verdict is
   revealed to them. Two blocks, in that order, in a chain that cannot be
   reordered afterwards. So a reviewer cannot have simply agreed with an
   answer they had already seen - the chain shows they committed while it was
   still hidden.

2. ATTENTION. The gap between opening the case and committing is recorded.
   A 0.8 second approval sits in the record permanently, next to a two minute
   one. Not proof of thought - but a 400-case history of sub-second calls is
   not something anyone can explain away.

3. INDEPENDENCE. Agreement rate over time. A reviewer who has never once
   diverged from the machine is visible in the data. One who diverges
   sometimes is demonstrably exercising judgement.

WHAT IT DOES NOT DO
-------------------
- It cannot prove the reviewer read the material. They can leave a screen open.
- Dwell time is measurable but gameable by anyone deliberately gaming it.
- It does not stop a reviewer being wrong. It records that they decided.
- If the integrating system shows its user the machine verdict before calling
  /open, this proves nothing. The ordering guarantee is only as good as the
  integration honouring it. That is a documented limit, not a hidden one.

WHAT IT IS FOR
--------------
Turning "we have human oversight" from an assertion into a dataset that an
auditor can test - and that a rubber stamper cannot hide inside.

    POST /x/oversight/open      case_ref, material, machine_verdict, reviewer
    POST /x/oversight/commit    case_id, reviewer_verdict, reasoning
    GET  /x/oversight/case?id=OVS-XXXXXXXX
    GET  /x/oversight/reviewer?id=<reviewer id>
    GET  /x/oversight/list
"""

import hashlib, json, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS oversight_cases(case_id TEXT PRIMARY KEY,api_key TEXT,case_ref TEXT,reviewer TEXT,material_hash TEXT,machine_verdict TEXT,opened REAL,committed REAL,reviewer_verdict TEXT,agreed INTEGER,dwell REAL,status TEXT DEFAULT 'open')")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_ovs_key ON oversight_cases(api_key)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_ovs_rev ON oversight_cases(api_key,reviewer)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _hash(x):
    if not isinstance(x, str):
        x = json.dumps(x, sort_keys=True)
    return hashlib.sha256(x.encode()).hexdigest()


def _seal_event(ctx, api_key, cid, action, detail):
    ts = time.time()
    ev = {"user_id": "ovs:" + cid, "action": "oversight_" + action, "amount": 0,
          "country": "UK", "device_id": "oversight", "anomaly": 0, "device_risk": 0}
    res = {"decision": "OVERSIGHT_SEALED", "score": 0, "oversight_action": action,
           "oversight_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _open(ctx, api_key, data):
    ref = str(data.get("case_ref", "")).strip()
    if not ref:
        return {"error": "case_ref_required"}, 400
    reviewer = str(data.get("reviewer", "")).strip()
    if not reviewer:
        return {"error": "reviewer_required",
                "message": "Oversight without a named reviewer is not oversight."}, 400
    material = data.get("material")
    if material is None:
        return {"error": "material_required",
                "message": "Send exactly what the reviewer will see. Only its hash is stored."}, 400
    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    cid = "OVS-" + secrets.token_hex(4).upper()
    mh = _hash(material)
    detail = ("ref=" + ref[:80] + ";reviewer=" + reviewer[:60] +
              ";material_sha256=" + mh + ";machine_verdict_sealed=" + (mv or "none"))
    h, idx, seq, ts = _seal_event(ctx, api_key, cid, "opened", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO oversight_cases(case_id,api_key,case_ref,reviewer,material_hash,machine_verdict,opened,committed,reviewer_verdict,agreed,dwell,status) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,'open')",
                            (cid, api_key, ref, reviewer, mh, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts), "material_sha256": mh,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until commit",
            "message": "Clock running. Show the reviewer the material, not the verdict."}, 200


def _commit(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT reviewer,material_hash,machine_verdict,opened,status FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4] != "open":
        return {"error": "already_committed",
                "message": "A reviewer commits once. That is the point."}, 400

    rv = str(data.get("reviewer_verdict", "")).strip().lower()
    if rv not in VERDICTS:
        return {"error": "invalid_reviewer_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required",
                "message": "Sealed at commit, before the machine verdict is revealed. Blank is not permitted."}, 400

    ts = time.time()
    dwell = round(ts - row[3], 3)
    agreed = None if not row[2] else (1 if rv == row[2] else 0)
    detail = ("reviewer_verdict=" + rv + ";dwell_seconds=" + str(dwell) +
              ";reasoning=" + reasoning[:600])
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "committed", detail)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE oversight_cases SET committed=?,reviewer_verdict=?,agreed=?,dwell=?,status='committed' WHERE case_id=? AND api_key=?",
                            (ts, rv, agreed, dwell, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "reviewer_verdict": rv, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "machine_verdict": row[2],
           "note": "Your call was sealed before this line was returned. The chain shows the order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "committed in under 2 seconds - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT case_ref,reviewer,material_hash,machine_verdict,opened,committed,reviewer_verdict,agreed,dwell,status FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("ovs:" + cid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("oversight_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"case_id": cid, "case_ref": row[0], "reviewer": row[1],
            "material_sha256": row[2], "machine_verdict": row[3],
            "opened": _iso(row[4]), "committed": _iso(row[5]),
            "reviewer_verdict": row[6],
            "agreed": (None if row[7] is None else bool(row[7])),
            "dwell_seconds": row[8], "status": row[9], "events": events,
            "ordering_proof": "The opened block precedes the committed block in the chain. Neither can be reordered or altered without breaking every block after it."}, 200


def _reviewer(ctx, api_key, rid):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM oversight_cases WHERE api_key=? AND reviewer=? AND status='committed'", (api_key, rid)).fetchall()
    if not rows:
        return {"reviewer": rid, "cases": 0,
                "note": "No committed cases on record for this reviewer."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    median = dwells[n // 2] if n else None
    under2 = len([d for d in dwells if d < 2])
    out = {"reviewer": rid, "cases": len(rows),
           "median_dwell_seconds": median,
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " cases"
    return out, 200


def _list(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT case_id,case_ref,reviewer,opened,status,reviewer_verdict,dwell,agreed FROM oversight_cases WHERE api_key=? ORDER BY opened DESC LIMIT 200", (api_key,)).fetchall()
    return {"count": len(rows),
            "cases": [{"case_id": r[0], "case_ref": r[1], "reviewer": r[2],
                       "opened": _iso(r[3]), "status": r[4],
                       "reviewer_verdict": r[5], "dwell_seconds": r[6],
                       "agreed": (None if r[7] is None else bool(r[7]))} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "open":
            return _open(ctx, api_key, data)
        if action == "commit":
            return _commit(ctx, api_key, data)
    else:
        if action == "list":
            return _list(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
        if action == "reviewer":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _reviewer(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/pack.py`

501 lines, 20695 bytes

```python
"""
Evidence pack - /x/pack/<action>

WHAT THIS IS
------------
The sellable artifact. Everything else in this platform produces evidence;
this produces the document someone hands an auditor.

For a chosen period it does not summarise the chain, it RE-VERIFIES it:
every block in the range is rehashed from its stored contents using the
same function that sealed it, and compared to the hash recorded at the
time. Then the links between blocks are walked, and for a single key the
gapless receipt sequence is checked end to end.

A summary is a claim. A re-verification is a check anyone can repeat.

WHAT IT DOES NOT PROVE
----------------------
- That any decision recorded here was correct. Wrong answers seal just as
  cleanly as right ones.
- That an external peer's own chain is honest. That is checked at the
  peer's host, not here.
- Anything about periods outside the range requested.

    GET  /x/pack/spec                        public - what this does
    GET  /x/pack/preview?period=2026-Q2      keyed  - the pack as JSON
    GET  /x/pack/render?period=2026-Q2       keyed  - the pack as one page
    GET  /x/pack/history                     keyed  - packs issued
    POST /x/pack/issue                       keyed  - seal it into the chain

period accepts YYYY, YYYY-MM, YYYY-Qn. Add scope=me to limit the pack to
your own key; omit scope for a deployment-wide pack.
"""

import calendar
import datetime
import hashlib
import json
import time

VERSION = "1.0"

# (METHOD, action). Only the spec is open - a pack is customer evidence.
PUBLIC = {("GET", "spec")}

MAX_ROWS = 200000

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS pack_issued("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
            "period TEXT,scope TEXT,digest TEXT,issued REAL,"
            "entries INTEGER,verified INTEGER,mismatches INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_pack_key "
            "ON pack_issued(api_key)")
        ctx["conn"].commit()
    _ready = True


def _sha(p):
    """Identical to the engine's own sha(). Written out here rather than
    imported so this module depends on no other module's internals."""
    return hashlib.sha256(
        json.dumps(p, sort_keys=True).encode()).hexdigest()


def _iso(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%d")


def _epoch(y, m, d):
    return float(calendar.timegm((y, m, d, 0, 0, 0, 0, 0, 0)))


def _bounds(period):
    """YYYY | YYYY-MM | YYYY-Qn -> (start, end, label)."""
    p = str(period or "").strip().upper()
    try:
        if len(p) == 4:
            y = int(p)
            return _epoch(y, 1, 1), _epoch(y + 1, 1, 1), p
        if len(p) == 7 and p[4] == "-" and p[5] == "Q":
            y, q = int(p[:4]), int(p[6])
            if q < 1 or q > 4:
                return None
            m = (q - 1) * 3 + 1
            em, ey = m + 3, y
            if em > 12:
                em, ey = em - 12, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
        if len(p) == 7 and p[4] == "-":
            y, m = int(p[:4]), int(p[5:])
            em, ey = m + 1, y
            if em > 12:
                em, ey = 1, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
    except (ValueError, IndexError):
        return None
    return None


# ----------------------------------------------------------------------
# assembly - the actual re-verification
# ----------------------------------------------------------------------

def _assemble(ctx, start, end, label, scope):
    c = ctx["conn"]
    cols = ("id,ts,event_json,result_json,prev_hash,audit_hash,"
            "api_key,key_seq")

    with ctx["lock"]:
        if scope:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "AND api_key=? ORDER BY id ASC LIMIT ?",
                (start, end, scope, MAX_ROWS)).fetchall()
            began = c.execute(
                "SELECT MIN(ts) FROM audit_log WHERE api_key=?",
                (scope,)).fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=?",
                (scope,)).fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=? "
                "AND first_seen>=? AND first_seen<?",
                (scope, start, end)).fetchone()
        else:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "ORDER BY id ASC LIMIT ?",
                (start, end, MAX_ROWS)).fetchall()
            began = c.execute("SELECT MIN(ts) FROM audit_log").fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen").fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen "
                "WHERE first_seen>=? AND first_seen<?",
                (start, end)).fetchone()
        chain_total = c.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]

    verdicts = {}
    actions = {}
    seqs = []
    verified = 0
    mismatched = []
    link_breaks = []
    expect_prev = None
    per_day = {}

    for rid, ts, ev_j, res_j, prev, ah, akey, kseq in rows:
        try:
            ev = json.loads(ev_j)
            res = json.loads(res_j)
        except Exception:
            mismatched.append(rid)
            expect_prev = ah
            continue

        if _sha({"prev_hash": prev, "ts": ts,
                 "event": ev, "result": res}) == ah:
            verified += 1
        else:
            mismatched.append(rid)

        if expect_prev is not None and prev != expect_prev:
            link_breaks.append(rid)
        expect_prev = ah

        d = str(res.get("decision", "UNRECORDED"))
        verdicts[d] = verdicts.get(d, 0) + 1
        a = str(ev.get("action", "unrecorded"))
        actions[a] = actions.get(a, 0) + 1
        if kseq is not None:
            try:
                seqs.append(int(kseq))
            except (TypeError, ValueError):
                pass
        k = _day(ts)
        per_day[k] = per_day.get(k, 0) + 1

    # does the first block in the period chain to the one before it
    entry_link = "no_entries_in_period"
    if rows:
        with ctx["lock"]:
            before = c.execute(
                "SELECT audit_hash FROM audit_log WHERE id<? "
                "ORDER BY id DESC LIMIT 1", (rows[0][0],)).fetchone()
        if before is None:
            entry_link = ("intact_from_genesis"
                          if rows[0][4] == "GENESIS" else "broken")
        else:
            entry_link = "intact" if rows[0][4] == before[0] else "broken"

    seq = {"applicable": bool(scope and seqs)}
    if seq["applicable"]:
        lo, hi = min(seqs), max(seqs)
        have = set(seqs)
        missing = [n for n in range(lo, hi + 1) if n not in have]
        seq.update({"first": lo, "last": hi, "received": len(seqs),
                    "expected": hi - lo + 1,
                    "missing": missing[:200],
                    "gapless": not missing,
                    "note": "Receipt numbers are issued with no gaps by "
                            "construction. A missing number is a record "
                            "that left this chain."})

    clean = (not mismatched and not link_breaks
             and entry_link in ("intact", "intact_from_genesis"))

    p = {
        "pack_version": VERSION,
        "period": label,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "generated_at": _iso(time.time()),
        "scope": ("key " + str(scope)[:12] + "\u2026") if scope
                 else "deployment-wide",
        "unbroken_since": _day(began[0] if began else None),
        "entries_in_period": len(rows),
        "chain_total_entries": chain_total,
        "first_block": rows[0][0] if rows else None,
        "first_hash": rows[0][5] if rows else None,
        "last_block": rows[-1][0] if rows else None,
        "last_hash": rows[-1][5] if rows else None,
        "integrity": {
            "clean": clean,
            "blocks_recomputed": len(rows),
            "hashes_verified": verified,
            "hash_mismatches": mismatched[:50],
            "link_breaks": link_breaks[:50],
            "link_into_period": entry_link,
            "method": "SHA-256 over {prev_hash, ts, event, result}, "
                      "recomputed from the stored row and compared to "
                      "the hash sealed at the time",
        },
        "receipt_sequence": seq,
        "verdicts": verdicts,
        "actions": dict(sorted(actions.items(), key=lambda x: -x[1])[:20]),
        "devices": {"total_ever": dev_all[0] if dev_all else 0,
                    "first_seen_in_period": dev_new[0] if dev_new else 0},
        "busiest_days": [{"day": d, "entries": n} for d, n in
                         sorted(per_day.items(), key=lambda x: -x[1])[:5]],
        "check_this_yourself": {
            "offline": "aileash_verify.py - stdlib only, no network",
            "still_on_this_chain": "/x/consistency/ancestor?tip=<last_hash>",
            "append_only": "/x/consistency/proof?first=&second=",
            "record_included": "/x/complete/prove",
            "who_witnessed_us": "/x/witness/peers",
        },
        "this_does_not_prove": [
            "That any decision recorded here was correct.",
            "That an external peer's own chain is honest - that is "
            "checked at the peer's host, not here.",
            "Anything about periods outside the dates above.",
        ],
    }
    p["pack_digest"] = hashlib.sha256(
        b"AILEASH-PACK-v1\x00" + json.dumps(
            p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return p


# ----------------------------------------------------------------------
# one page, self contained
# ----------------------------------------------------------------------

def _html(p):
    ig = p["integrity"]
    sq = p["receipt_sequence"]
    good = "#7fe3b0"
    bad = "#ff8a80"

    def card(inner):
        return ("<div style='background:#10182e;border:1px solid #223055;"
                "border-radius:12px;padding:16px;margin-bottom:14px'>"
                + inner + "</div>")

    def row(k, v):
        return ("<tr><td style='padding:7px 0;border-bottom:1px solid "
                "#1d2a4a'>" + str(k) + "</td><td style='padding:7px 0;"
                "border-bottom:1px solid #1d2a4a;text-align:right;"
                "color:#c9a84c;font-weight:600'>" + str(v) + "</td></tr>")

    def mono(v):
        return ("<code style='font:12px ui-monospace,monospace;"
                "color:#9fb3d9;word-break:break-all'>" + str(v)
                + "</code>")

    integ = ("<div style='font-size:26px;font-weight:600;color:"
             + (good if ig["clean"] else bad) + "'>"
             + str(ig["hashes_verified"]) + " of "
             + str(ig["blocks_recomputed"]) + " blocks re-verified</div>"
             "<div style='color:#93a0bd;font-size:13px;margin-top:6px'>"
             + ig["method"] + "</div>")
    if not ig["clean"]:
        integ += ("<div style='color:" + bad + ";font-size:13px;"
                  "margin-top:8px'>mismatched blocks "
                  + str(ig["hash_mismatches"]) + " &middot; link breaks "
                  + str(ig["link_breaks"]) + " &middot; entry link "
                  + ig["link_into_period"] + "</div>")

    if sq.get("applicable"):
        seqbox = ("<div style='font-size:20px;font-weight:600;color:"
                  + (good if sq["gapless"] else bad) + "'>"
                  + ("Receipt sequence complete" if sq["gapless"]
                     else "GAPS IN RECEIPT SEQUENCE") + "</div>"
                  "<div style='color:#93a0bd;font-size:13px'>"
                  + str(sq["received"]) + " of " + str(sq["expected"])
                  + " received, numbers " + str(sq["first"]) + " to "
                  + str(sq["last"]) + "</div>")
        if not sq["gapless"]:
            seqbox += ("<div style='color:" + bad + ";font:12px "
                       "ui-monospace,monospace;margin-top:6px'>missing "
                       + str(sq["missing"]) + "</div>")
    else:
        seqbox = ("<div style='color:#93a0bd;font-size:13px'>Receipt "
                  "sequence applies to a single key. This pack is "
                  "deployment-wide.</div>")

    checks = "".join("<li><b>" + k.replace("_", " ") + "</b> " + mono(v)
                     + "</li>" for k, v in
                     p["check_this_yourself"].items())
    nots = "".join("<li>" + x + "</li>" for x in p["this_does_not_prove"])

    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Evidence Pack " + p["period"] + " - AILeash</title>"
        "<body style='background:#0a0f1e;color:#e8ecf5;margin:0;"
        "padding:22px;font:15px/1.55 -apple-system,system-ui,sans-serif'>"
        "<div style='max-width:760px;margin:0 auto'>"
        "<h1 style='font-size:21px;margin:0 0 4px;color:#c9a84c'>"
        "Evidence Pack &mdash; " + p["period"] + "</h1>"
        "<div style='color:#93a0bd;font-size:13px;margin-bottom:20px'>"
        + p["scope"] + " &middot; " + str(p["period_start"]) + " to "
        + str(p["period_end"]) + " &middot; generated "
        + str(p["generated_at"]) + "</div>"
        + card("<div style='color:#93a0bd;font-size:13px'>Unbroken since"
               "</div><div style='font-size:26px;color:" + good
               + ";font-weight:600'>" + str(p["unbroken_since"])
               + "</div>")
        + card(integ)
        + card(seqbox)
        + card("<table style='width:100%;border-collapse:collapse;"
               "font-size:14px'>"
               + row("Entries in period", p["entries_in_period"])
               + row("Chain total entries", p["chain_total_entries"])
               + row("Devices, total ever", p["devices"]["total_ever"])
               + row("Devices first seen this period",
                     p["devices"]["first_seen_in_period"])
               + "".join(row(k, v) for k, v in sorted(
                   p["verdicts"].items()))
               + "".join(row(k, v) for k, v in p["actions"].items())
               + "</table>")
        + card("<div style='color:#93a0bd;font-size:13px'>First block</div>"
               + mono("#" + str(p["first_block"]) + " "
                      + str(p["first_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Last block</div>"
               + mono("#" + str(p["last_block"]) + " "
                      + str(p["last_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Pack digest</div>" + mono(p["pack_digest"]))
        + card("<div style='color:#93a0bd;font-size:13px'>Check every "
               "figure above yourself:</div><ul style='margin:6px 0 0 18px;"
               "padding:0;font-size:13px'>" + checks + "</ul>"
               "<div style='color:#93a0bd;font-size:13px;margin-top:14px'>"
               "What this pack does not prove:</div>"
               "<ul style='margin:6px 0 0 18px;padding:0;color:#93a0bd;"
               "font-size:13px'>" + nots + "</ul>")
        + "<div style='color:#6d7b99;font-size:12px;margin-top:18px'>"
          "AILeash &middot; sebbi.pro</div></div>")


# ----------------------------------------------------------------------

def _resolve(data, api_key):
    b = _bounds(data.get("period"))
    if not b:
        return None, ({"error": "period_required",
                       "accepts": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                       "example": "/x/pack/preview?period=2026-Q2"}, 400)
    start, end, label = b
    if end > time.time():
        return None, ({"error": "period_not_closed", "period": label,
                       "message": "A pack can only cover a period that "
                                  "has finished."}, 409)
    scope = data.get("scope")
    if scope == "me":
        scope = api_key
    return (start, end, label, scope or None), None


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return {"module": "pack", "version": VERSION,
                "purpose": "Re-verifies every block in a period against "
                           "the hash sealed at the time, and checks the "
                           "gapless receipt sequence for a single key.",
                "periods": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                "routes": {"GET /x/pack/spec": "public",
                           "GET /x/pack/preview?period=": "keyed, json",
                           "GET /x/pack/render?period=": "keyed, one page",
                           "GET /x/pack/history": "keyed",
                           "POST /x/pack/issue": "keyed, seals the pack"},
                "scope": "add scope=me for your key only; omit for "
                         "deployment-wide",
                "does_not_prove": [
                    "That any decision recorded here was correct.",
                    "That an external peer's chain is honest.",
                ]}, 200

    if not api_key:
        return {"error": "invalid_api_key"}, 401

    _setup(ctx)

    if method == "GET":
        if action == "history":
            with ctx["lock"]:
                rows = ctx["conn"].execute(
                    "SELECT period,scope,digest,issued,entries,verified,"
                    "mismatches,audit_hash,block_index FROM pack_issued "
                    "WHERE api_key=? ORDER BY id DESC LIMIT 200",
                    (api_key,)).fetchall()
            return {"count": len(rows), "packs": [
                {"period": r[0], "scope": r[1], "digest": r[2],
                 "issued": _iso(r[3]), "entries": r[4],
                 "hashes_verified": r[5], "mismatches": r[6],
                 "sealed_in_chain": r[7], "block_index": r[8]}
                for r in rows]}, 200

        if action in ("preview", "render"):
            got, err = _resolve(data, api_key)
            if err:
                return err
            start, end, label, scope = got
            p = _assemble(ctx, start, end, label, scope)
            if action == "preview":
                return p, 200
            return {"period": label, "content_type": "text/html",
                    "html": _html(p)}, 200

    if method == "POST" and action == "issue":
        got, err = _resolve(data, api_key)
        if err:
            return err
        start, end, label, scope = got
        p = _assemble(ctx, start, end, label, scope)
        ig = p["integrity"]
        ts = time.time()
        ev = {"user_id": "pack:" + label, "action": "evidence_pack_issued",
              "amount": 0, "country": "UK", "device_id": "pack",
              "anomaly": 0, "device_risk": 0}
        res = {"decision": "PACK_ISSUED", "score": 0, "pack_version": VERSION,
               "timestamp": ts, "period": label, "scope": p["scope"],
               "entries": p["entries_in_period"],
               "blocks_recomputed": ig["blocks_recomputed"],
               "hashes_verified": ig["hashes_verified"],
               "clean": ig["clean"], "pack_digest": p["pack_digest"],
               "note": "evidence pack issued; the pack's own digest is "
                       "now sealed, so the document cannot be edited "
                       "after the fact"}
        h, idx, seq = ctx["seal"](ev, res, ts, api_key)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO pack_issued(api_key,period,scope,digest,"
                "issued,entries,verified,mismatches,audit_hash,"
                "block_index) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (api_key, label, p["scope"], p["pack_digest"], ts,
                 p["entries_in_period"], ig["hashes_verified"],
                 len(ig["hash_mismatches"]), h, idx))
            ctx["conn"].commit()
        p["sealed"] = {"audit_hash": h, "block_index": idx,
                       "receipt_seq": seq}
        return p, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "preview", "render", "history"],
            "POST": ["issue"]}, 404

```


## `modules/packconsole.py`

426 lines, 16973 bytes

```python
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

```


## `modules/peer.py`

664 lines, 25236 bytes

```python
"""
modules/peer.py  v1.0  --  signed peer submission

WHY THIS EXISTS
    /x/witness/observe is unauthenticated on purpose. Anyone can submit a
    tip without an account, and that openness is what answers the
    collusion objection -- nobody has to trust us to audit the network.

    The cost of that openness is that anyone can submit a tip under any
    name. Name binding catches most of it; it does not prevent it.

    A named peer exchanging period roots wants a stronger guarantee: that
    only they can submit as their chain. This module gives them that
    WITHOUT changing the open endpoint. Both run side by side. A peer
    picks whichever suits their risk posture.

WHAT IT COVERS
    canonicalization, HMAC-SHA256 signing, nonce, replay window, clock
    skew, idempotency, retry semantics, suspension, key rotation with
    overlap.

AUTH LIVES IN THE BODY, NOT IN HEADERS
    The module router hands modules a parsed body, not the raw headers,
    so every authentication field travels in the JSON body. This also
    makes the scheme trivial to implement from any language and easy to
    replay in a test.

THE SCHEME, IN FULL
    Envelope:
        {
          "peer_id":         "prae-001",
          "ts":              1755432000,          integer unix seconds
          "nonce":           "<>=16 chars, unique per peer>",
          "idempotency_key": "<optional, <=128 chars>",
          "payload":         { ... the thing being submitted ... },
          "signature":       "<hex hmac-sha256>"
        }

    String to sign:
        "AILEASH-PEER-v1\\n" + canonical(envelope_without_signature)

    canonical() is exactly:
        json.dumps(obj, sort_keys=True, separators=(",",":"),
                   ensure_ascii=True)

    signature = hmac_sha256(secret, string_to_sign).hexdigest()

    POST /x/peer/canonical returns the exact string to sign for a given
    envelope, so an implementer can debug canonicalization without
    holding or revealing a secret.

RULES
    clock skew      +/- 300s. Outside that: 401 clock_skew.
    nonce           unique per peer for 900s. Reused: 409 replay.
    idempotency     same key + same payload digest returns the FIRST
                    response verbatim, sealed once. Same key + different
                    payload: 409 idempotency_conflict.
    retry           safe. Retry the identical envelope; idempotency makes
                    it a no-op that returns the original receipt.
    suspension      403 peer_suspended. Submissions refused, nothing
                    deleted, the peer's history stands.
    rotation        two secrets live at once. A new secret is issued and
                    the previous one stays valid for ROTATION_OVERLAP
                    (default 24h) so a peer can roll without downtime.

ROUTES
    GET  spec       public   full implementation guide
    POST canonical  public   the exact string to sign. no secret needed.
    GET  peers      public   peer ids, status, rotation state. no secrets.
    POST submit     public route, SIGNATURE authenticated
    POST register   keyed    operator issues a peer credential
    POST rotate     keyed    issue a new secret, overlap the old
    POST suspend    keyed
    POST resume     keyed
    GET  history    keyed    submissions by peer

TABLES OWNED
    peer_registry, peer_nonce, peer_submission
"""

import hashlib
import hmac
import json
import os
import re
import time

VERSION = "1.0"

PUBLIC = {
    ("GET", "spec"),
    ("POST", "canonical"),
    ("GET", "peers"),
    ("POST", "submit"),
}

SIGN_PREFIX = "AILEASH-PEER-v1\n"

CLOCK_SKEW_SECONDS = 300
NONCE_TTL_SECONDS = 900
NONCE_MIN_LENGTH = 16
ROTATION_OVERLAP_SECONDS = 86400
MAX_PAYLOAD_BYTES = 65536
MAX_IDEMPOTENCY_KEY = 128

_PEER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")

_ready = False


# ---------------------------------------------------------------- storage

def _setup(ctx):
    global _ready
    if _ready:
        return
    conn = ctx["conn"]
    with ctx["lock"]:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_registry (
                peer_id          TEXT PRIMARY KEY,
                chain_name       TEXT,
                url              TEXT,
                secret_current   TEXT,
                secret_previous  TEXT,
                rotated_at       REAL,
                status           TEXT DEFAULT 'active',
                created          REAL,
                submissions      INTEGER DEFAULT 0,
                last_seen        REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_nonce (
                peer_id   TEXT,
                nonce     TEXT,
                seen_at   REAL,
                PRIMARY KEY (peer_id, nonce)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS peer_submission (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                peer_id          TEXT,
                ts               REAL,
                idempotency_key  TEXT,
                payload_digest   TEXT,
                response_json    TEXT,
                audit_hash       TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_sub_idem "
            "ON peer_submission(peer_id, idempotency_key)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_peer_nonce_time "
            "ON peer_nonce(seen_at)")
        conn.commit()
    _ready = True


# ------------------------------------------------------------ primitives

def canonical(obj):
    """
    THE canonicalization. Any implementation in any language must produce
    this byte-for-byte. Sorted keys, no whitespace, ASCII-escaped.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True)


def string_to_sign(envelope):
    """Envelope WITHOUT the signature field, prefixed and canonicalized."""
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    return SIGN_PREFIX + canonical(unsigned)


def sign(secret, envelope):
    return hmac.new(secret.encode("utf-8"),
                    string_to_sign(envelope).encode("utf-8"),
                    hashlib.sha256).hexdigest()


def _digest(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def _new_secret():
    return os.urandom(32).hex()


def _now():
    return time.time()


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _sweep_nonces(ctx):
    cutoff = _now() - NONCE_TTL_SECONDS
    with ctx["lock"]:
        ctx["conn"].execute("DELETE FROM peer_nonce WHERE seen_at < ?",
                            (cutoff,))
        ctx["conn"].commit()


# ------------------------------------------------------------ the submit

def _submit(ctx, data):
    """
    Signature-authenticated. No API key. Every rule on the list is
    enforced here, in a fixed order, and each failure names itself.
    """
    _setup(ctx)

    # ---- shape
    peer_id = (data.get("peer_id") or "").strip()
    signature = (data.get("signature") or "").strip()
    nonce = (data.get("nonce") or "").strip()
    payload = data.get("payload")
    idem = (data.get("idempotency_key") or "").strip()[:MAX_IDEMPOTENCY_KEY]

    if not peer_id or not signature or not nonce or payload is None:
        return {"ok": False, "error": "malformed_envelope",
                "required": ["peer_id", "ts", "nonce", "payload",
                             "signature"]}, 400

    try:
        ts = int(data.get("ts"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "malformed_ts",
                "detail": "ts must be an integer of unix seconds"}, 400

    if len(nonce) < NONCE_MIN_LENGTH:
        return {"ok": False, "error": "nonce_too_short",
                "minimum": NONCE_MIN_LENGTH}, 400

    if len(canonical(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return {"ok": False, "error": "payload_too_large",
                "max_bytes": MAX_PAYLOAD_BYTES}, 413

    # ---- peer known and active
    row = ctx["conn"].execute(
        "SELECT peer_id, chain_name, secret_current, secret_previous, "
        "rotated_at, status FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer", "peer_id": peer_id}, 401
    if row[5] == "suspended":
        return {"ok": False, "error": "peer_suspended",
                "detail": "Submissions refused. Existing history stands "
                          "and nothing has been removed."}, 403

    # ---- clock skew, before any expensive work
    skew = abs(_now() - ts)
    if skew > CLOCK_SKEW_SECONDS:
        return {"ok": False, "error": "clock_skew",
                "detail": "Timestamp is %.0fs from server time; the window "
                          "is +/-%ds." % (skew, CLOCK_SKEW_SECONDS),
                "server_time": int(_now())}, 401

    # ---- signature, against current then previous secret
    envelope = {"peer_id": peer_id, "ts": ts, "nonce": nonce,
                "payload": payload}
    if idem:
        envelope["idempotency_key"] = idem

    accepted_with = None
    if row[2] and hmac.compare_digest(sign(row[2], envelope), signature):
        accepted_with = "current"
    elif row[3] and (row[4] or 0) + ROTATION_OVERLAP_SECONDS > _now():
        if hmac.compare_digest(sign(row[3], envelope), signature):
            accepted_with = "previous"

    if not accepted_with:
        return {"ok": False, "error": "bad_signature",
                "detail": "HMAC did not match. POST the same envelope to "
                          "/x/peer/canonical to see the exact string this "
                          "server signs.",
                "string_to_sign_sha256":
                    hashlib.sha256(
                        string_to_sign(envelope).encode()).hexdigest(),
                }, 401

    payload_digest = _digest(payload)

    # ---- idempotency, before the nonce check so a retry is a clean no-op
    if idem:
        prior = ctx["conn"].execute(
            "SELECT payload_digest, response_json FROM peer_submission "
            "WHERE peer_id = ? AND idempotency_key = ?",
            (peer_id, idem)).fetchone()
        if prior:
            if prior[0] != payload_digest:
                return {"ok": False, "error": "idempotency_conflict",
                        "detail": "That idempotency key was used with a "
                                  "different payload."}, 409
            out = json.loads(prior[1])
            out["replayed"] = True
            out["note"] = ("Idempotent retry. This is the original receipt; "
                           "nothing was sealed twice.")
            return out, 200

    # ---- replay
    _sweep_nonces(ctx)
    seen = ctx["conn"].execute(
        "SELECT seen_at FROM peer_nonce WHERE peer_id = ? AND nonce = ?",
        (peer_id, nonce)).fetchone()
    if seen:
        return {"ok": False, "error": "replay",
                "detail": "That nonce has already been used by this peer "
                          "within the %ds window. Use a fresh nonce, or "
                          "send an idempotency_key if you meant to retry."
                          % NONCE_TTL_SECONDS}, 409

    # ---- accept: seal it
    now = _now()
    event = {"module": "peer", "action": "submit", "peer_id": peer_id,
             "chain_name": row[1], "payload_digest": payload_digest,
             "payload": payload}
    result = {"accepted": True, "signed_with": accepted_with}
    audit_hash = block_index = receipt_seq = None
    try:
        audit_hash, block_index, receipt_seq = ctx["seal"](
            event, result, now, None)
    except Exception:
        pass

    out = {
        "ok": True,
        "accepted": True,
        "peer_id": peer_id,
        "chain_name": row[1],
        "payload_digest": payload_digest,
        "signed_with": accepted_with,
        "received_at": _iso(now),
        "receipt": {"audit_hash": audit_hash,
                    "block_index": block_index,
                    "receipt_seq": receipt_seq},
        "verify": {
            "inclusion": "/x/complete/prove",
            "ancestry": "/x/consistency/ancestor?tip=<any tip we served>",
            "append_only": "/x/consistency/proof?first=&second=",
        },
    }

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO peer_nonce (peer_id, nonce, seen_at) "
            "VALUES (?,?,?)", (peer_id, nonce, now))
        ctx["conn"].execute(
            "INSERT INTO peer_submission (peer_id, ts, idempotency_key, "
            "payload_digest, response_json, audit_hash) VALUES (?,?,?,?,?,?)",
            (peer_id, now, idem or None, payload_digest,
             json.dumps(out), audit_hash))
        ctx["conn"].execute(
            "UPDATE peer_registry SET submissions = submissions + 1, "
            "last_seen = ? WHERE peer_id = ?", (now, peer_id))
        ctx["conn"].commit()

    if accepted_with == "previous":
        out["warning"] = ("Accepted with the previous secret. The overlap "
                          "window ends %s." % _iso((row[4] or 0) +
                                                   ROTATION_OVERLAP_SECONDS))
    return out, 200


# ------------------------------------------------------------- operator

def _register(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not _PEER_ID_RE.match(peer_id):
        return {"ok": False, "error": "bad_peer_id",
                "detail": "lowercase letters, digits, dot, dash, "
                          "underscore; 2-63 chars"}, 400
    if ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                           (peer_id,)).fetchone():
        return {"ok": False, "error": "peer_exists",
                "detail": "Use /x/peer/rotate to issue a new secret."}, 409

    secret = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO peer_registry (peer_id, chain_name, url, "
            "secret_current, secret_previous, rotated_at, status, created) "
            "VALUES (?,?,?,?,NULL,NULL,'active',?)",
            (peer_id, (data.get("chain_name") or peer_id).strip()[:120],
             (data.get("url") or "").strip()[:400], secret, now))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": "register",
                     "peer_id": peer_id},
                    {"registered": True}, now, None)
    except Exception:
        pass

    return {
        "ok": True,
        "peer_id": peer_id,
        "secret": secret,
        "warning": "This secret is shown once and is not recoverable. "
                   "Send it to the peer over a channel you trust.",
        "endpoint": "/x/peer/submit",
        "spec": "/x/peer/spec",
    }, 200


def _rotate(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    row = ctx["conn"].execute(
        "SELECT secret_current FROM peer_registry WHERE peer_id = ?",
        (peer_id,)).fetchone()
    if not row:
        return {"ok": False, "error": "unknown_peer"}, 404

    new = _new_secret()
    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET secret_previous = secret_current, "
            "secret_current = ?, rotated_at = ? WHERE peer_id = ?",
            (new, now, peer_id))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": "rotate",
                     "peer_id": peer_id}, {"rotated": True}, now, None)
    except Exception:
        pass

    return {
        "ok": True,
        "peer_id": peer_id,
        "secret": new,
        "previous_valid_until": _iso(now + ROTATION_OVERLAP_SECONDS),
        "detail": "Both secrets are accepted until then, so the peer can "
                  "roll over without downtime. Submissions signed with the "
                  "old one come back marked.",
    }, 200


def _set_status(ctx, data, status):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    if not ctx["conn"].execute("SELECT 1 FROM peer_registry WHERE peer_id = ?",
                               (peer_id,)).fetchone():
        return {"ok": False, "error": "unknown_peer"}, 404
    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE peer_registry SET status = ? WHERE peer_id = ?",
            (status, peer_id))
        ctx["conn"].commit()
    try:
        ctx["seal"]({"module": "peer", "action": status,
                     "peer_id": peer_id}, {"status": status}, _now(), None)
    except Exception:
        pass
    return {"ok": True, "peer_id": peer_id, "status": status}, 200


def _peers(ctx):
    _setup(ctx)
    now = _now()
    rows = ctx["conn"].execute(
        "SELECT peer_id, chain_name, url, status, created, submissions, "
        "last_seen, rotated_at FROM peer_registry ORDER BY created"
    ).fetchall()
    return {
        "ok": True,
        "count": len(rows),
        "peers": [{
            "peer_id": r[0], "chain_name": r[1], "url": r[2] or None,
            "status": r[3], "registered": _iso(r[4]),
            "submissions": r[5], "last_seen": _iso(r[6]) if r[6] else None,
            "rotation_overlap_active":
                bool(r[7] and r[7] + ROTATION_OVERLAP_SECONDS > now),
        } for r in rows],
        "note": "Secrets are never returned by any route.",
    }, 200


def _history(ctx, data):
    _setup(ctx)
    peer_id = (data.get("peer_id") or "").strip().lower()
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    q = ("SELECT peer_id, ts, idempotency_key, payload_digest, audit_hash "
         "FROM peer_submission")
    args = []
    if peer_id:
        q += " WHERE peer_id = ?"
        args.append(peer_id)
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    rows = ctx["conn"].execute(q, args).fetchall()
    return {
        "ok": True, "count": len(rows),
        "submissions": [{
            "peer_id": r[0], "at": _iso(r[1]), "idempotency_key": r[2],
            "payload_digest": r[3], "audit_hash": r[4],
        } for r in rows],
    }, 200


def _canonical_route(data):
    """
    Debugging aid. Give it an envelope, get back the exact string this
    server will sign. Reveals nothing -- the secret is not involved.
    """
    env = dict(data or {})
    env.pop("signature", None)
    if "ts" in env:
        try:
            env["ts"] = int(env["ts"])
        except (TypeError, ValueError):
            return {"ok": False, "error": "malformed_ts"}, 400
    s = string_to_sign(env)
    return {
        "ok": True,
        "string_to_sign": s,
        "sha256": hashlib.sha256(s.encode("utf-8")).hexdigest(),
        "byte_length": len(s.encode("utf-8")),
        "recipe": "\"AILEASH-PEER-v1\\n\" + json.dumps(envelope_without_"
                  "signature, sort_keys=True, separators=(\",\",\":\"), "
                  "ensure_ascii=True)",
        "then": "signature = hmac_sha256(secret, string_to_sign).hexdigest()",
    }, 200


# ------------------------------------------------------------------ spec

def _spec():
    return {
        "module": "peer",
        "version": VERSION,
        "purpose":
            "Signed submission for named peers. Sits beside the open "
            "/x/witness/observe endpoint rather than replacing it. The "
            "open endpoint stays unauthenticated so anyone can audit the "
            "network without an account; this one guarantees that only "
            "the holder of a peer secret can submit as that chain.",
        "envelope": {
            "peer_id": "string, issued at registration",
            "ts": "integer unix seconds",
            "nonce": "string, at least %d chars, unique per peer for %ds"
                     % (NONCE_MIN_LENGTH, NONCE_TTL_SECONDS),
            "idempotency_key": "optional string, max %d chars"
                               % MAX_IDEMPOTENCY_KEY,
            "payload": "object. period roots, tips, whatever is agreed. "
                       "max %d bytes canonicalized." % MAX_PAYLOAD_BYTES,
            "signature": "hex hmac-sha256",
        },
        "canonicalization": {
            "recipe": "json.dumps(obj, sort_keys=True, "
                      "separators=(\",\",\":\"), ensure_ascii=True)",
            "string_to_sign": "\"AILEASH-PEER-v1\\n\" + canonical(envelope "
                              "with the signature field removed)",
            "signature": "hmac_sha256(secret, string_to_sign).hexdigest()",
            "debug": "POST the envelope to /x/peer/canonical to get the "
                     "exact string back. No secret required.",
        },
        "rules": {
            "clock_skew": "+/-%ds. Outside: 401 clock_skew, with the "
                          "server's time in the body."
                          % CLOCK_SKEW_SECONDS,
            "replay": "A nonce is single-use per peer for %ds. Reused: "
                      "409 replay." % NONCE_TTL_SECONDS,
            "idempotency": "Same idempotency_key and same payload returns "
                           "the original receipt verbatim with "
                           "replayed=true; nothing is sealed twice. Same "
                           "key with a different payload: 409 "
                           "idempotency_conflict.",
            "retry": "Retry the identical envelope. With an "
                     "idempotency_key that is a safe no-op. Without one, "
                     "a retry inside the nonce window returns 409 replay "
                     "-- so send an idempotency_key if you intend to "
                     "retry at all.",
            "suspension": "403 peer_suspended. Nothing is deleted and the "
                          "peer's sealed history stands.",
            "rotation": "A new secret is issued and the previous one stays "
                        "valid for %ds. Submissions accepted on the old "
                        "secret come back with signed_with=previous and a "
                        "warning naming the cutoff."
                        % ROTATION_OVERLAP_SECONDS,
        },
        "on_acceptance":
            "The payload is sealed into the audit chain and you get "
            "audit_hash, block_index and receipt_seq. Verify "
            "independently: inclusion at /x/complete/prove, ancestry at "
            "/x/consistency/ancestor, append-only at "
            "/x/consistency/proof. Both offline verifiers "
            "(aileash_verify.py, verify_authority.py) are stdlib only and "
            "touch no network.",
        "routes": {
            "GET spec": "public. this document.",
            "POST canonical": "public. the exact string to sign.",
            "GET peers": "public. peer ids and status. never secrets.",
            "POST submit": "signature authenticated. no API key.",
            "POST register": "keyed. operator issues a credential.",
            "POST rotate": "keyed. new secret, old one overlaps.",
            "POST suspend / POST resume": "keyed.",
            "GET history": "keyed. submissions, optionally by peer.",
        },
        "what_this_does_not_do": [
            "It does not make a submitted root true. It proves who "
            "submitted it and when, and that it has not changed since.",
            "It does not replace /x/witness/observe. Peers who prefer the "
            "open path keep using it and lose nothing.",
            "A shared secret authenticates a channel, not a person. If "
            "the secret leaks, rotate it.",
        ],
        "worked_example": {
            "envelope_before_signing": {
                "peer_id": "example-001",
                "ts": 1755432000,
                "nonce": "0123456789abcdef",
                "payload": {"period": "2026-Q3", "root": "ab12...", "count": 4096},
            },
            "note": "POST exactly that to /x/peer/canonical and you will "
                    "get the string to sign, so you can confirm your "
                    "implementation before you hold a secret.",
        },
    }


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if action == "spec":
        return _spec(), 200
    if action == "canonical":
        return _canonical_route(data)
    if action == "peers":
        return _peers(ctx)
    if action == "submit":
        return _submit(ctx, data)

    if not api_key:
        return {"ok": False, "error": "api_key_required"}, 401

    if action == "register":
        return _register(ctx, data)
    if action == "rotate":
        return _rotate(ctx, data)
    if action == "suspend":
        return _set_status(ctx, data, "suspended")
    if action == "resume":
        return _set_status(ctx, data, "active")
    if action == "history":
        return _history(ctx, data)

    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


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
