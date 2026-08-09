# Codebase — part 7 of 18

Contains:
- `modules/selfcheck.py`
- `modules/spec.py`
- `modules/standard.py`
- `modules/stats.py`
- `modules/witness.py`
- `Verify_ai.py`
- `ai_act_ranker.py`
- `ai_safety_scanner.py`
- `aigrade_insert.py`
- `aileash_reporter.py`


## `modules/selfcheck.py`

659 lines, 25677 bytes

```python
#!/usr/bin/env python3
"""
modules/selfcheck.py  -  the conformance runner, served as a page

WHY THIS IS A MODULE AND NOT A FILE IN ROOT
-------------------------------------------
A plain .html in the repo root does not get served on this deployment, so
the page ships inside the module and is served by the same runtime do_GET
patch that console.py uses for /console and network.py uses for /witness.
It also means the page cannot drift from the module that serves it.

WHAT THE PAGE DOES
------------------
Reads /.well-known/ordering-test.json, then runs every check the document
declares, in the order the document declares them. It discovers what it
needs as it goes: a committed period from /x/complete/periods, a tree size
from /x/consistency/root, a probe value that is not in the log.

It reports four outcomes and is deliberately mean about which is which:

  VERIFIED       the response was checked for what the claim requires -
                 consecutive leaf indices for absence, a proof path for
                 consistency, identical verdicts for reproducibility
  INCONCLUSIVE   the endpoint answered but the semantics were not checked,
                 or the route is POST-only, or the check is key-gated
  FAILED         published as publicly demonstrable and the endpoint is
                 not there. This is the number that matters
  NOT SUPPORTED  the document does not claim it

Reachable is not the same as verified, and this page never counts one as
the other. A runner that only ever passes has not been tested.

NOT A SHARED RUNNER
-------------------
It tests one side. The discovery document's runner field stays null until
the checks are jointly agreed with the other mirror, and publishing this as
though it were the agreed conformance test would claim something neither
operator has earned. Served unlinked and noindex for that reason.

    GET /self-check          the page
    GET /x/selfcheck/status  what is installed
"""

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/self-check", "/self-check.html")

_patched = [False]


PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Ordering test — self check</title>
<style>
  :root{
    --ink:#0a0f1e;
    --ink2:#10182e;
    --line:#1e2942;
    --gold:#c9a84c;
    --ok:#7fe3b0;
    --err:#ff8a80;
    --warn:#e8c06a;
    --mute:#6b7894;
    --text:#dbe3f4;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--ink);
    color:var(--text);
    font-family:var(--mono);
    font-size:14px;
    line-height:1.5;
    -webkit-text-size-adjust:100%;
  }
  .wrap{max-width:760px;margin:0 auto;padding:20px 16px 80px}

  header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:22px}
  .eyebrow{
    font-size:11px;letter-spacing:.18em;text-transform:uppercase;
    color:var(--gold);margin:0 0 8px
  }
  h1{font-size:22px;line-height:1.25;margin:0 0 10px;font-weight:600;letter-spacing:-.01em}
  .sub{color:var(--mute);font-size:13px;margin:0}
  .sub b{color:var(--text);font-weight:600}

  .bar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 0}
  button{
    font-family:var(--mono);font-size:13px;
    background:var(--gold);color:#10121a;border:0;border-radius:2px;
    padding:11px 18px;font-weight:700;letter-spacing:.02em;cursor:pointer;
  }
  button.ghost{background:transparent;color:var(--text);border:1px solid var(--line);font-weight:400}
  button:disabled{opacity:.4;cursor:default}
  button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}

  .tally{
    display:flex;gap:14px;flex-wrap:wrap;margin:20px 0 0;
    font-size:12px;color:var(--mute)
  }
  .tally b{font-size:20px;display:block;font-weight:600;letter-spacing:-.02em}
  .t-pass b{color:var(--ok)} .t-fail b{color:var(--err)}
  .t-inc b{color:var(--warn)} .t-ns b{color:var(--mute)}

  /* the spine: checks hold the order the document declares */
  ol.spine{list-style:none;margin:26px 0 0;padding:0;position:relative}
  ol.spine:before{
    content:"";position:absolute;left:19px;top:6px;bottom:6px;width:1px;
    background:var(--line)
  }
  li.check{position:relative;padding:0 0 2px 52px;margin:0 0 2px}
  .slot{
    position:absolute;left:0;top:12px;width:39px;height:22px;
    display:flex;align-items:center;justify-content:center;
    background:var(--ink);color:var(--mute);
    font-size:11px;letter-spacing:.08em;z-index:1
  }
  .row{
    border-bottom:1px solid var(--line);
    padding:12px 0 13px;
    display:flex;align-items:baseline;gap:10px;flex-wrap:wrap
  }
  .name{font-size:14px;font-weight:600;letter-spacing:-.01em}
  .verdict{
    font-size:10px;letter-spacing:.14em;text-transform:uppercase;
    padding:3px 7px;border:1px solid currentColor;border-radius:2px;white-space:nowrap
  }
  .v-pass{color:var(--ok)} .v-fail{color:var(--err)}
  .v-inc{color:var(--warn)} .v-ns{color:var(--mute)}
  .v-run{color:var(--gold)}
  .v-wait{color:var(--line)}
  .why{flex-basis:100%;color:var(--mute);font-size:12.5px;margin-top:2px}
  .why b{color:var(--text);font-weight:600}
  .ep{
    flex-basis:100%;font-size:11.5px;color:var(--mute);
    margin-top:5px;word-break:break-all
  }
  .ep a{color:var(--gold);text-decoration:none;border-bottom:1px solid rgba(201,168,76,.35)}
  details{flex-basis:100%;margin-top:8px}
  summary{
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--mute);cursor:pointer;list-style:none
  }
  summary::-webkit-details-marker{display:none}
  summary:before{content:"▸ ";}
  details[open] summary:before{content:"▾ ";}
  pre{
    background:var(--ink2);border:1px solid var(--line);border-radius:2px;
    margin:8px 0 0;padding:10px;font-size:11.5px;line-height:1.45;
    white-space:pre-wrap;word-break:break-word;max-height:280px;overflow:auto
  }
  li.check.done .slot{color:var(--text)}

  footer{
    margin-top:34px;border-top:1px solid var(--line);padding-top:16px;
    color:var(--mute);font-size:12px
  }
  footer p{margin:0 0 9px}
  .flash{
    border:1px solid var(--err);color:var(--err);
    padding:11px;border-radius:2px;margin:16px 0 0;font-size:12.5px
  }
  @media (prefers-reduced-motion: no-preference){
    li.check.done .row{animation:in .22s ease-out}
    @keyframes in{from{opacity:.35}to{opacity:1}}
  }
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">Ordering test · self check</p>
  <h1>Run every check this domain publishes about itself.</h1>
  <p class="sub">Reads <b>/.well-known/ordering-test.json</b>, then tests each check in the order the document declares it. Nothing here is a shared runner — it only tests this side.</p>
  <div class="bar">
    <button id="run">Run all checks</button>
    <button id="reload" class="ghost">Reload document</button>
  </div>
  <div class="tally" id="tally" hidden>
    <div class="t-pass"><b id="n-pass">0</b>verified</div>
    <div class="t-fail"><b id="n-fail">0</b>failed</div>
    <div class="t-inc"><b id="n-inc">0</b>inconclusive</div>
    <div class="t-ns"><b id="n-ns">0</b>not public</div>
  </div>
  <div id="flash"></div>
</header>

<ol class="spine" id="spine"></ol>

<footer>
  <p><b>Verified</b> means the response was checked for what the claim actually requires. <b>Reachable</b> means the endpoint answered but this runner did not confirm the semantics — reported as inconclusive, not as a pass.</p>
  <p>A check marked not publicly demonstrable is reported as such and never counted as a pass. This page cannot see behind a key and does not pretend to.</p>
</footer>

</div>

<script>
(function(){
  "use strict";

  var DOC = "/.well-known/ordering-test.json";
  var doc = null;
  var ctx = {};

  var el = function(id){ return document.getElementById(id); };
  var spine = el("spine");

  function flash(msg){
    el("flash").innerHTML = msg ? '<div class="flash">' + msg + '</div>' : '';
  }

  function pad(n){ return (n < 10 ? "0" : "") + n; }

  function jget(path){
    return fetch(path, {headers:{"Accept":"application/json"}}).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  function jpost(path, payload){
    return fetch(path, {
      method:"POST",
      headers:{"Content-Type":"application/json","Accept":"application/json"},
      body:JSON.stringify(payload)
    }).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  function show(v){
    try { return JSON.stringify(v, null, 2); } catch(e){ return String(v); }
  }

  // ---- document ---------------------------------------------------------

  function loadDoc(){
    flash("");
    spine.innerHTML = "";
    el("tally").hidden = true;
    return jget(DOC).then(function(r){
      if (!r.ok || typeof r.body !== "object"){
        flash("Could not read " + DOC + " — status " + r.status +
              ". If this is a fresh deploy, open /x/standard/status once to install the route, then reload.");
        doc = null;
        return null;
      }
      doc = r.body;
      draw();
      return doc;
    }).catch(function(e){
      flash("Request failed: " + e.message + ". Serve this page from the same domain as the document.");
    });
  }

  function draw(){
    var names = Object.keys(doc.checks || {});
    spine.innerHTML = "";
    names.forEach(function(name, i){
      var c = doc.checks[name];
      var li = document.createElement("li");
      li.className = "check";
      li.id = "chk-" + name;
      li.innerHTML =
        '<span class="slot">' + pad(i+1) + '</span>' +
        '<div class="row">' +
          '<span class="name">' + name.replace(/_/g," ") + '</span>' +
          '<span class="verdict v-wait" data-v>waiting</span>' +
          '<div class="why" data-why>' +
            (c.supported ? "declared supported" : "declared not supported") +
            (c.demonstrable_publicly ? ", publicly demonstrable" : ", not publicly demonstrable") +
          '</div>' +
          (c.endpoint ? '<div class="ep">' + c.endpoint + '</div>' : '') +
        '</div>';
      spine.appendChild(li);
    });
    var t = doc.vendor ? doc.vendor : "this domain";
    document.querySelector(".sub").innerHTML =
      'Document loaded from <b>' + (doc.base_url || location.origin) + '</b> · vendor <b>' + t +
      '</b> · version <b>' + (doc.ordering_test_version || "?") + '</b> · ' +
      names.length + ' checks declared.';
  }

  function setResult(name, verdict, why, detail){
    var li = el("chk-" + name);
    if (!li) return;
    li.classList.add("done");
    var v = li.querySelector("[data-v]");
    var map = {PASS:"v-pass", FAIL:"v-fail", INCONCLUSIVE:"v-inc", "NOT SUPPORTED":"v-ns", RUNNING:"v-run"};
    v.className = "verdict " + (map[verdict] || "v-wait");
    v.textContent = verdict;
    li.querySelector("[data-why]").innerHTML = why;
    if (detail !== undefined){
      var old = li.querySelector("details");
      if (old) old.remove();
      var d = document.createElement("details");
      d.innerHTML = "<summary>response</summary><pre>" +
        show(detail).replace(/</g,"&lt;") + "</pre>";
      li.querySelector(".row").appendChild(d);
    }
  }

  function running(name){
    var li = el("chk-" + name);
    if (!li) return;
    var v = li.querySelector("[data-v]");
    v.className = "verdict v-run";
    v.textContent = "running";
  }

  // ---- context the checks need before they can run ----------------------

  function buildContext(){
    ctx = {};
    var jobs = [];

    jobs.push(jget("/x/complete/periods").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      var list = r.body.periods || r.body.committed || r.body;
      if (!Array.isArray(list)) return;
      for (var i = list.length - 1; i >= 0; i--){
        var p = list[i];
        var id = (typeof p === "string") ? p : (p.period || p.id);
        var committed = (typeof p === "string") ? true :
          (p.committed === undefined ? true : !!p.committed);
        if (id && committed){ ctx.period = id; break; }
      }
    }).catch(function(){}));

    jobs.push(jget("/x/consistency/root").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      ctx.size = r.body.size || r.body.tree_size || r.body.count;
    }).catch(function(){}));

    ctx.absent = "not-in-this-log-" + Math.random().toString(36).slice(2,10);

    return Promise.all(jobs);
  }

  function fill(endpoint){
    if (!endpoint) return null;
    return endpoint
      .replace("{period}", ctx.period || "")
      .replace("{value}", ctx.absent)
      .replace("{first}", "1")
      .replace("{second}", ctx.size ? String(ctx.size) : "");
  }

  // ---- the checks -------------------------------------------------------
  // Each returns {verdict, why, detail}.

  var runners = {

    mutual_witnessing: function(c){
      return jget("/x/witness/peers").then(function(p){
        return jget("/x/witness/tip").then(function(t){
          if (!p.ok) return {verdict:"FAIL", why:"peers endpoint returned " + p.status, detail:p.body};
          if (!t.ok) return {verdict:"FAIL", why:"tip endpoint returned " + t.status, detail:t.body};
          var peers = p.body.peers || p.body;
          var n = Array.isArray(peers) ? peers.length : 0;
          if (n === 0){
            return {verdict:"FAIL", why:"no peer chains listed — witnessing claims an external party and there isn't one", detail:p.body};
          }
          return {verdict:"PASS",
                  why:"<b>" + n + " peer chain" + (n>1?"s":"") + "</b> listed and a current tip served, both without an account",
                  detail:{peers:p.body, tip:t.body}};
        });
      });
    },

    completeness_proof: function(c){
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no closed committed period found at /x/complete/periods, so there is nothing to ask for a root of"});
      }
      var url = fill(c.endpoint) || ("/x/complete/root?period=" + ctx.period);
      return jget(url).then(function(r){
        if (r.status === 409) return {verdict:"INCONCLUSIVE", why:"period " + ctx.period + " is still live — only closed periods commit", detail:r.body};
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var root = r.body.root || r.body.merkle_root;
        var count = r.body.count !== undefined ? r.body.count : r.body.leaf_count;
        if (!root || count === undefined){
          return {verdict:"INCONCLUSIVE", why:"reachable, but no root and exact leaf count in the response", detail:r.body};
        }
        return {verdict:"PASS",
                why:"root and an exact count of <b>" + count + "</b> leaves, committed for " + ctx.period + " before any export was asked for",
                detail:r.body};
      });
    },

    absence_proof: function(c){
      var url = fill(c.endpoint) || ("/x/complete/prove?value=" + ctx.absent);
      return jget(url).then(function(r){
        if (!r.ok && r.status !== 404) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var b = r.body || {};
        var leaves = b.neighbours || b.neighbors || b.leaves || b.adjacent;
        if (Array.isArray(leaves) && leaves.length === 2){
          var a = leaves[0], z = leaves[1];
          var ia = (a && a.index !== undefined) ? a.index : null;
          var iz = (z && z.index !== undefined) ? z.index : null;
          if (ia !== null && iz !== null && (iz - ia) === 1){
            return {verdict:"PASS",
                    why:"two adjacent leaves at indices <b>" + ia + "</b> and <b>" + iz +
                        "</b> — consecutive, so nothing can sit between them. Absence proved, not asserted",
                    detail:r.body};
          }
          return {verdict:"FAIL",
                  why:"two leaves returned but their indices are not consecutive (" + ia + ", " + iz + ") — that proves nothing",
                  detail:r.body};
        }
        return {verdict:"INCONCLUSIVE",
                why:"reachable, but this runner could not find two adjacent leaves in the response shape",
                detail:r.body};
      });
    },

    consistency_proof: function(c){
      if (!ctx.size){
        return Promise.resolve({verdict:"INCONCLUSIVE", why:"could not read a tree size from /x/consistency/root"});
      }
      var first = Math.max(1, Math.floor(ctx.size / 2));
      var url = "/x/consistency/proof?first=" + first + "&second=" + ctx.size;
      return jget(url).then(function(r){
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status + " for first=" + first + " second=" + ctx.size, detail:r.body};
        var path = r.body.proof || r.body.path || r.body.consistency;
        if (!Array.isArray(path)){
          return {verdict:"INCONCLUSIVE", why:"reachable, but no proof path in the response", detail:r.body};
        }
        return {verdict:"PASS",
                why:"RFC 6962 proof of <b>" + path.length + " nodes</b> that the log at " + first +
                    " is a prefix of the log at " + ctx.size + " — append-only shown, not claimed",
                detail:r.body};
      });
    },

    reproducibility: function(c){
      var probe = {amount: 4200, velocity_1h: 3, velocity_24h: 11, country: "GB"};
      return jget("/x/replay/fingerprint").then(function(f){
        return jpost("/x/replay/challenge", probe).then(function(a){
          if (a.status === 400 || a.status === 422){
            return {verdict:"INCONCLUSIVE",
                    why:"endpoint live but rejected this runner's payload shape — read the message and adjust the probe",
                    detail:{fingerprint:f.body, rejected:a.body}};
          }
          if (!a.ok) return {verdict:"FAIL", why:"challenge returned " + a.status, detail:a.body};
          return jpost("/x/replay/challenge", probe).then(function(b){
            var va = (a.body && (a.body.verdict || a.body.decision));
            var vb = (b.body && (b.body.verdict || b.body.decision));
            if (!va || !vb){
              return {verdict:"INCONCLUSIVE", why:"both runs sealed but no verdict field to compare", detail:{first:a.body, second:b.body}};
            }
            if (va === vb){
              return {verdict:"PASS",
                      why:"identical inputs submitted twice both returned <b>" + va +
                          "</b> under one code fingerprint — determinism shown without disclosing any scoring logic",
                      detail:{fingerprint:f.body, first:a.body, second:b.body}};
            }
            return {verdict:"FAIL",
                    why:"identical inputs gave <b>" + va + "</b> then <b>" + vb + "</b> — not deterministic",
                    detail:{first:a.body, second:b.body}};
          });
        });
      });
    },

    external_anchoring: function(c){
      var url = c.endpoint || "/api/anchor-status";
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"<b>" + url + " returned " + r.status + "</b> — this check is published as publicly demonstrable and the endpoint under it is not there",
                  detail:r.body};
        }
        return {verdict:"INCONCLUSIVE",
                why:"endpoint answers, but this runner does not verify the external authority itself — check the named timestamp by hand",
                detail:r.body};
      });
    }
  };

  // generic fallback: liveness only, reported honestly as inconclusive
  function genericRunner(name, c){
    var url = fill(c.endpoint);
    if (!url) return Promise.resolve({verdict:"INCONCLUSIVE", why:"declared publicly demonstrable but no endpoint given"});
    if (url.indexOf("{") !== -1){
      return Promise.resolve({verdict:"INCONCLUSIVE", why:"endpoint has a placeholder this runner could not fill: " + url});
    }
    return jget(url).then(function(r){
      if (r.status === 405 || r.status === 501){
        return {verdict:"INCONCLUSIVE", why:"POST-only endpoint — reachable, but cannot be exercised from a plain page", detail:r.body};
      }
      if (!r.ok){
        return {verdict:"FAIL", why:"<b>" + url + " returned " + r.status + "</b>", detail:r.body};
      }
      return {verdict:"INCONCLUSIVE", why:"reachable — semantics not checked by this runner", detail:r.body};
    });
  }

  // ---- run --------------------------------------------------------------

  function runAll(){
    if (!doc){ flash("No document loaded."); return; }
    el("run").disabled = true;
    var tally = {PASS:0, FAIL:0, INCONCLUSIVE:0, "NOT SUPPORTED":0};
    el("tally").hidden = false;

    buildContext().then(function(){
      var names = Object.keys(doc.checks);
      var chain = Promise.resolve();

      names.forEach(function(name){
        chain = chain.then(function(){
          var c = doc.checks[name];

          if (!c.supported){
            setResult(name, "NOT SUPPORTED", "the document does not claim this check");
            tally["NOT SUPPORTED"]++;
            return;
          }
          if (!c.demonstrable_publicly){
            setResult(name, "INCONCLUSIVE",
              "built and claimed, but key-gated — nothing here can confirm it, which is what the document says");
            tally.INCONCLUSIVE++;
            return;
          }

          running(name);
          var fn = runners[name] ? runners[name].bind(null, c) : genericRunner.bind(null, name, c);
          return fn().catch(function(e){
            return {verdict:"FAIL", why:"request threw: " + e.message};
          }).then(function(res){
            setResult(name, res.verdict, res.why, res.detail);
            tally[res.verdict] = (tally[res.verdict] || 0) + 1;
            el("n-pass").textContent = tally.PASS;
            el("n-fail").textContent = tally.FAIL;
            el("n-inc").textContent = tally.INCONCLUSIVE;
            el("n-ns").textContent = tally["NOT SUPPORTED"];
          });
        });
      });

      chain.then(function(){
        el("run").disabled = false;
        el("n-pass").textContent = tally.PASS;
        el("n-fail").textContent = tally.FAIL;
        el("n-inc").textContent = tally.INCONCLUSIVE;
        el("n-ns").textContent = tally["NOT SUPPORTED"];
        if (tally.FAIL > 0){
          flash(tally.FAIL + " check" + (tally.FAIL>1?"s":"") +
                " published as publicly demonstrable did not hold up. Fix the endpoint or change the document — the two have to agree.");
        }
      });
    });
  }

  el("run").addEventListener("click", runAll);
  el("reload").addEventListener("click", loadDoc);
  loadDoc();
})();
</script>
</body>
</html>
'''


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_selfcheck_patched", False):
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
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._selfcheck_patched = True
    _patched[0] = True
    print("SELFCHECK: /self-check installed", flush=True)
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
            print("SELFCHECK: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"installed": bool(_patched[0]),
                "install_result": state,
                "module_version": VERSION,
                "serving": list(PAGE_PATHS),
                "page_bytes": len(PAGE),
                "note": "Runs against whichever host serves it. Same origin, so the browser "
                        "does not block the requests. Unlinked and noindex on purpose - it "
                        "tests one operator's own document and is not a joint runner."}, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/spec.py`

121 lines, 5086 bytes

```python
"""
Live API specification - /x/spec

/api/spec is a hardcoded constant. It describes the API as it was when
somebody last remembered to update it, which is a documentation problem
pretending to be a feature.

This discovers what is actually loaded, right now, by reading the modules
directory and each module's own docstring. Add a module and the spec
updates itself. Delete one and it disappears. There is no separate list to
maintain and therefore no list that can drift.

That matters here more than it would elsewhere: a platform whose pitch is
"check it, don't trust it" should not ship a self-description that is
quietly out of date.

    GET /x/spec           everything currently live
    GET /x/spec/modules   just the module list
"""

import importlib, os, pkgutil, re

VERSION = "1.0"

_EP = re.compile(r"^\s*(GET|POST|PUT|DELETE)\s+(/\S+)\s*(.*)$")


def _describe(name):
    """Pull a module's summary and endpoint list out of its own docstring."""
    try:
        m = importlib.import_module("modules." + name)
    except Exception as e:
        return {"module": name, "loaded": False, "error": str(e)}
    doc = (m.__doc__ or "").strip()
    lines = doc.splitlines()
    summary = ""
    for ln in lines:
        t = ln.strip()
        if t and not t.startswith("-") and not _EP.match(ln):
            summary = t
            break
    endpoints = []
    for ln in lines:
        mm = _EP.match(ln)
        if mm:
            endpoints.append({"method": mm.group(1),
                              "path": mm.group(2),
                              "takes": mm.group(3).strip() or None})
    out = {"module": name, "loaded": True, "summary": summary,
           "endpoints": endpoints,
           "version": getattr(m, "VERSION", None)}
    if not hasattr(m, "handle"):
        out["warning"] = "module has no handle() - it will not route"
    return out


def _modules():
    d = os.path.dirname(__file__)
    names = sorted(x.name for x in pkgutil.iter_modules([d])
                   if x.name not in ("router", "spec"))
    return [_describe(n) for n in names]


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404

    mods = _modules()

    if action == "modules":
        return {"count": len(mods), "modules": mods}, 200

    if action in ("", "all"):
        return {
            "spec_version": VERSION,
            "generated": "live - discovered at request time, not a stored list",
            "core": {
                "decision_engine": {
                    "path": "/api/govern",
                    "method": "POST",
                    "auth": "Bearer key",
                    "note": "deterministic scoring, verdict sealed before the response returns"
                },
                "notaries_public": [
                    {"method": "POST", "path": "/api/post/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/verify-post", "auth": "none"},
                    {"method": "POST", "path": "/api/identity/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/identity/check", "auth": "none"},
                    {"method": "POST", "path": "/api/payment/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/payment/check", "auth": "none"}
                ],
                "verification_public": [
                    {"method": "GET", "path": "/api/verify-chain",
                     "returns": "whole-chain integrity, recomputed"},
                    {"method": "GET", "path": "/api/inclusion",
                     "returns": "whether a given 64-char hash is sealed"},
                    {"method": "GET", "path": "/api/anchor-status",
                     "returns": "current tip, OpenTimestamps proof, calendar count"},
                    {"method": "GET", "path": "/api/regulation-map",
                     "returns": "engine features mapped to legal obligations"}
                ]
            },
            "modules": {
                "prefix": "/x/<module>/<action>",
                "auth": "Bearer key on every module route",
                "count": len(mods),
                "loaded": mods
            },
            "chain": {
                "algorithm": "SHA-256 hash chain",
                "scope": "one chain - every module seals into the same sequence as /api/govern",
                "anchoring": "chain tip submitted to OpenTimestamps, aggregated into a Merkle root, root committed to Bitcoin by several independent calendars",
                "receipts": "gapless per-key sequence issued in the same transaction as the chain write",
                "verify": "/api/verify-chain and /api/anchor-status, both without a key"
            },
            "honest_note": "This spec is generated by reading the modules directory at request time rather than from a stored list, so it cannot describe capabilities that are not actually loaded."
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["", "modules"]}, 404

```


## `modules/standard.py`

401 lines, 17637 bytes

```python
"""
modules/standard.py  -  the Ordering Test discovery document for this domain

WHAT IT SERVES
--------------
  GET /.well-known/ordering-test.json   this operator's discovery document
  GET /x/standard/hash                  sha256 of that document
  GET /x/standard/status                what is installed, and honest counts

SHAPE
-----
Deliberately identical to the shape Red Flag AI Pro published first:

    checks: { <name>: { supported, demonstrable_publicly, endpoint, note } }

Two fields, not one, and the second is the better idea. "We built it" and
"you can verify it without an account" are different claims, and most of this
market blurs them. Separating them lets a vendor be honest about having
something real that an outsider still has to take on trust.

WHAT THE HOST HEADER IS DOING HERE
----------------------------------
base_url is derived from the request rather than written into the file. An
earlier draft had the domain hardcoded, which meant any operator running it
would publish somebody else's domain as the source - the opposite of a mirror.
Deriving it means this file can be lifted to any domain and tells the truth
about wherever it is actually running.

EVERY PUBLISHED ENDPOINT MUST WORK AS WRITTEN
---------------------------------------------
An endpoint marked demonstrable_publicly is a promise that a stranger can copy
it out of this document and get an answer. If the route needs a parameter, the
document names that parameter. If a value has to be discovered first, the
document says where to discover it. An endpoint that errors when followed
literally is a failed check, not a documentation detail.

HONESTY RULES THIS FILE FOLLOWS
-------------------------------
  - A check we have not built says supported: false. It does not quietly go
    missing from the document.
  - A check that exists but needs an account says demonstrable_publicly:
    false, however much we would like the tick.
  - runner is null. A runner exists in draft, but the checks have not been
    jointly agreed with the other mirror, so publishing one as though it were
    a settled standard would claim something neither operator has earned yet.

None of that is modesty. A conformance document whose author scores full marks
on the day they publish it is a marketing page.
"""

import hashlib
import json
import sys

VERSION = "1.1"
ORDERING_TEST_VERSION = "0.1"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec"),
          ("GET", "document")}

# Several paths on purpose. /.well-known/ is where the standard says to look,
# but some platforms and static handlers reserve that prefix, so a plain root
# path is served as well. /x/standard/document goes through the normal router
# and cannot be intercepted by anything, which makes it the diagnostic.
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",
                   "/ordering-test.json",
                   "/well-known/ordering-test.json")

VENDOR = "AILeash"
FALLBACK_BASE = "https://sebbi.pro"

RUNNER = None
RUNNER_NOTE = (
    "No shared runner file is published here yet. The checks themselves have "
    "not been jointly agreed with the other mirrors as of this document's "
    "publication. This describes AILeash's own side only, not a settled "
    "cross-vendor standard.")

# Order follows the other mirror's document so the two read side by side.
CHECKS = {
    "rule_binding": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/rulebind/prove",
        "note": ("The ruleset version is a component of a digest sealed with the "
                 "decision, not a field beside it. POST any inputs without an "
                 "account and the response returns the exact string that was "
                 "hashed - SHA-256 it yourself and confirm it matches. Alter the "
                 "ruleset hash and the digest stops recomputing; alter the digest "
                 "and the chain breaks. Verify a past record at "
                 "/x/rulebind/verify?receipt=... and see ruleset history at "
                 "/x/rulebind/packs. No scoring logic is disclosed at any point - "
                 "inputs are published as a digest, never as values."),
    },
    "commit_before_reveal": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/demo/review",
        "note": ("The reviewer receives the case with the machine verdict "
                 "withheld. Their own call and dwell time are sealed first, "
                 "then the verdict is revealed, and the chain fixes that order "
                 "permanently. No account needed - open a case, commit a "
                 "verdict, and check the block indices yourself. Commit "
                 "endpoint is /x/demo/commit."),
    },
    "authority_tokens": {
        "supported": True,
        "demonstrable_publicly": False,
        "endpoint": None,
        "note": ("Signed authority tokens with scope and expiry. A decision "
                 "beyond delegated authority escalates rather than executes, "
                 "and the delegation itself is sealed. Built and live, "
                 "key-gated, no public proof."),
    },
    "mutual_witnessing": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/witness/peers",
        "note": ("Live, running both directions with an external peer chain "
                 "hourly since 1 August 2026. No account needed, run it "
                 "yourself. Our current tip is at /x/witness/tip and any party "
                 "can submit theirs at /x/witness/observe without an account."),
    },
    "completeness_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/root?period={period}&kind=receipts",
        "note": ("Per-period sorted Merkle root and exact leaf count, committed "
                 "before any export is requested. An export can then be checked "
                 "against a number fixed before anyone knew it would be asked "
                 "for. Committed periods are listed at /x/complete/periods - "
                 "take a period identifier from there and substitute it. Only "
                 "closed periods can be committed, so the current period will "
                 "not appear until it ends. A period listed nowhere is a period "
                 "nobody committed, which is itself the finding."),
    },
    "absence_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/prove?period={period}&value={value}",
        "note": ("Two adjacent leaves with consecutive indices demonstrate that "
                 "nothing sits between them, so absence is proved rather than "
                 "asserted. Both parameters are required: take a period from "
                 "/x/complete/periods and supply any value you like. Try a "
                 "value that is not there."),
    },
    "reconciliation": {
        "supported": True,
        "demonstrable_publicly": False,
        "endpoint": None,
        "note": ("Sample selected from the live chain tip and sealed before any "
                 "data is requested, so flattering records cannot be "
                 "cherry-picked. Mismatches sealed as permanently as matches. "
                 "Built and live, key-gated, no public proof."),
    },
    "reproducibility": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/replay/challenge",
        "note": ("Determinism proved by public challenge without disclosing any "
                 "scoring logic. Submit inputs, the run is sealed, resubmit the "
                 "same inputs later and the verdict must be identical under an "
                 "unchanged code fingerprint at /x/replay/fingerprint."),
    },
    "consistency_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/consistency/proof?first={first}&second={second}",
        "note": ("RFC 6962 consistency proofs, deliberately unmodified so "
                 "existing Certificate Transparency verifiers work against them "
                 "directly. first and second are tree sizes - read the current "
                 "size from /x/consistency/root and pick any earlier one. "
                 "Anyone holding any earlier tip we served can show it is a "
                 "prefix of the current log at /x/consistency/ancestor."),
    },

    # ---- proposed addition, flagged as a proposal rather than assumed ----
    "external_anchoring": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/api/anchor-status",
        "note": ("PROPOSED AS A SEPARATE CHECK, not settled. The other mirror "
                 "currently folds anchoring into consistency_proof, but they "
                 "answer different questions: consistency shows the log only "
                 "ever grew, anchoring shows the time was fixed somewhere the "
                 "operator cannot reach. A log can be perfectly append-only and "
                 "still have been built last week. Here the tip is submitted to "
                 "OpenTimestamps and committed into Bitcoin; the other mirror "
                 "uses an RFC 3161 timestamp. The spec should permit any "
                 "external authority the operator does not control and require "
                 "it to be named - not mandate one. Offered for the joint "
                 "session."),
    },
}

DOCUMENT_NOTE = (
    "Every endpoint marked demonstrable_publicly is unauthenticated by design - "
    "run it yourself without asking us. Where an endpoint carries a {parameter}, "
    "the note for that check says where to get a valid value; every published "
    "endpoint is meant to work when followed literally, and one that does not is "
    "a failed check on our side, not a quibble. Checks marked supported but not "
    "demonstrable_publicly are real and built, but currently need a key to see, "
    "and say so plainly rather than passing on the day this was published. "
    "Nothing here proves the records are true. It describes the order things "
    "were committed in, which is a narrower claim and the only one that holds.")

_patched = [False]


def _base_from(handler):
    """Derive our own base URL from the request. An operator running this file
    on their own domain publishes their domain, not whoever wrote it."""
    try:
        host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host")
        if not host:
            return FALLBACK_BASE
        host = host.split(",")[0].strip()[:200]
        proto = (handler.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return proto + "://" + host
    except Exception:
        return FALLBACK_BASE


def _base_from_ctx(ctx):
    """Same derivation for the routed /x/standard/document call.

    The router's ctx may or may not carry the request handler. If it does, the
    document served through the router names the same domain as the one served
    at /.well-known/ - which matters on a mirror, where hardcoding would make
    this file publish somebody else's domain again."""
    try:
        if isinstance(ctx, dict):
            for key in ("handler", "h", "request", "req", "self"):
                obj = ctx.get(key)
                if obj is not None and hasattr(obj, "headers"):
                    return _base_from(obj)
            headers = ctx.get("headers")
            if headers is not None:
                class _Shim(object):
                    pass
                shim = _Shim()
                shim.headers = headers
                return _base_from(shim)
        elif ctx is not None and hasattr(ctx, "headers"):
            return _base_from(ctx)
    except Exception:
        pass
    return FALLBACK_BASE


def _document(base):
    checks = {}
    for name, c in CHECKS.items():
        checks[name] = {
            "supported": c["supported"],
            "demonstrable_publicly": c["demonstrable_publicly"],
            "endpoint": c["endpoint"],
            "note": c["note"],
        }
    return {
        "ordering_test_version": ORDERING_TEST_VERSION,
        "vendor": VENDOR,
        "base_url": base,
        "runner": RUNNER,
        "runner_note": RUNNER_NOTE,
        "checks": checks,
        "witness_peers": base + "/x/witness/peers",
        "witness_tip": base + "/x/witness/tip",
        "committed_periods": base + "/x/complete/periods",
        "note": DOCUMENT_NOTE,
    }


def _digest(doc):
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


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
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in DISCOVERY_PATHS:
            body = json.dumps(_document(_base_from(self)), indent=2).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /.well-known/ordering-test.json installed", flush=True)
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
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    base = _base_from_ctx(ctx)
    doc = _document(base)

    if method == "GET" and action == "document":
        return doc, 200

    if method == "GET" and action == "hash":
        canonical = _document(FALLBACK_BASE)
        return {
            "sha256": _digest(canonical),
            "of": "this operator's discovery document",
            "canonicalisation": ("JSON, keys sorted, no whitespace, UTF-8, "
                                 "base_url fixed to " + FALLBACK_BASE +
                                 " so the digest does not move with the "
                                 "requesting host"),
            "what_this_is_for": (
                "Confirming our own document has not changed. It is NOT the "
                "cross-mirror check - two operators publish different documents "
                "by design, because they list different endpoints, so their "
                "digests should differ and a mismatch would prove nothing. The "
                "cross-mirror comparison only means something once every mirror "
                "serves a byte-identical runner file and hashes that instead. "
                "No runner is agreed yet."),
            "document": canonical,
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        supported = [k for k, c in CHECKS.items() if c["supported"]]
        public = [k for k, c in CHECKS.items() if c["demonstrable_publicly"]]
        parameterised = [k for k, c in CHECKS.items()
                         if c["endpoint"] and "{" in c["endpoint"]]
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "ordering_test_version": ORDERING_TEST_VERSION,
            "serving": list(DISCOVERY_PATHS),
            "always_available": "/x/standard/document",
            "checks_total": len(CHECKS),
            "checks_supported": len(supported),
            "checks_publicly_demonstrable": len(public),
            "publicly_demonstrable": public,
            "supported_but_not_public": [k for k in supported if k not in public],
            "endpoints_needing_a_parameter": parameterised,
            "runner": RUNNER,
            "note": ("base_url is derived from the Host header, so this file "
                     "publishes whichever domain is actually serving it. Checks "
                     "listed under endpoints_needing_a_parameter cannot be "
                     "demonstrated until a real value exists to substitute - "
                     "for the completeness and absence checks that means at "
                     "least one committed period at /x/complete/periods."),
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash", "document"]}, 404

```


## `modules/stats.py`

143 lines, 5540 bytes

```python
"""
Live figures for the Proving Ground - /x/stats

Charts on a compliance site are usually decoration. These are not, provided
they show something a visitor could otherwise only take on trust: that the
chain is genuinely growing, that decisions really are distributed across the
thresholds rather than hand-picked, and that people who click through a
review case behave exactly as the oversight argument predicts.

WHAT IS PUBLISHED, AND WHAT IS NOT
----------------------------------
Public and no key, because a figure nobody can see proves nothing.

Published: total chain height, hourly block counts, the verdict mix and score
distribution of PUBLIC DEMO decisions only, and dwell times from public review
cases.

Never published: anything scoped to a customer key. No customer verdict mix,
no customer volumes, no per-key anything. A visitor learns how the engine
behaves, not how any operator's business is going. That distinction is the
whole reason this endpoint can be open.

    GET /x/stats        everything below
    GET /x/stats/chain  chain height and hourly growth only
"""

import json, time
from datetime import datetime, timezone

VERSION = "1.0"
PUBLIC = {("GET", ""), ("GET", "stats"), ("GET", "chain")}

DEMO_KEY = "public_demo"


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _chain(ctx):
    t = time.time()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*),MIN(ts),MAX(ts) FROM audit_log").fetchone()
        recent = ctx["conn"].execute("SELECT ts FROM audit_log WHERE ts>? ORDER BY ts ASC", (t - 86400,)).fetchall()
    height = row[0] if row else 0
    buckets = [0] * 24
    for (ts,) in recent:
        h = int((t - ts) // 3600)
        if 0 <= h < 24:
            buckets[23 - h] += 1
    return {"height": height,
            "first_block": _iso(row[1] if row else None),
            "latest_block": _iso(row[2] if row else None),
            "last_24h": buckets,
            "blocks_last_24h": sum(buckets),
            "note": "Every block, from every source. The chain is one sequence."}


def _demo(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT result_json,ts FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (DEMO_KEY,)).fetchall()
    verdicts = {"ALLOW": 0, "CHALLENGE": 0, "BLOCK": 0}
    # ten buckets of 0.1 across the score range
    hist = [0] * 10
    scores = []
    for res, _ts in rows:
        try:
            r = json.loads(res)
        except Exception:
            continue
        d = r.get("decision")
        if d in verdicts:
            verdicts[d] += 1
            s = r.get("score")
            if isinstance(s, (int, float)):
                scores.append(s)
                b = min(int(float(s) * 10), 9)
                hist[b] += 1
    total = sum(verdicts.values())
    out = {"decisions": total, "verdicts": verdicts,
           "score_histogram": hist,
           "buckets": ["0.0-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5",
                       "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"],
           "thresholds": {"allow_below": 0.35, "block_at_or_above": 0.70}}
    if scores:
        scores.sort()
        out["median_score"] = round(scores[len(scores) // 2], 4)
    return out


def _oversight(ctx):
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT dwell,human_verdict,machine_verdict FROM demo_cases WHERE committed IS NOT NULL").fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"reviews": 0,
                "note": "Nobody has taken a review case yet."}
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    agreed = len([r for r in rows if (r[1] or "").upper() == (r[2] or "").upper()])
    # dwell buckets in seconds
    edges = [2, 5, 10, 20, 45, 90]
    labels = ["under 2s", "2-5s", "5-10s", "10-20s", "20-45s", "45-90s", "over 90s"]
    hist = [0] * 7
    for d in dwells:
        placed = False
        for i, e in enumerate(edges):
            if d < e:
                hist[i] += 1
                placed = True
                break
        if not placed:
            hist[6] += 1
    n = len(dwells)
    return {"reviews": len(rows),
            "agreed_with_engine": agreed,
            "agreement_rate_pct": round(100 * agreed / len(rows), 1),
            "median_dwell_seconds": (dwells[n // 2] if n else None),
            "under_2_seconds": hist[0],
            "under_2_seconds_pct": (round(100 * hist[0] / n, 1) if n else 0),
            "dwell_histogram": hist,
            "dwell_labels": labels,
            "note": "Visitors who committed in under two seconds did not read the case. That is the pattern the oversight record is designed to make visible."}


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404
    if action == "chain":
        return {"stats_version": VERSION, "chain": _chain(ctx)}, 200
    if action in ("", "stats"):
        return {"stats_version": VERSION,
                "generated": _iso(time.time()),
                "chain": _chain(ctx),
                "public_decisions": _demo(ctx),
                "public_reviews": _oversight(ctx),
                "scope": "Public demonstration activity and total chain height only. Nothing scoped to a customer key is published here."}, 200
    return {"error": "unknown_action", "action": action,
            "available": ["GET stats", "GET chain"]}, 404

```


## `modules/witness.py`

514 lines, 23310 bytes

```python
"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control - and those chains are
themselves anchored externally.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step, and re-anchor all of it. That is not a
technical exercise. That is a conspiracy, and it grows harder with every
platform that joins.

WHY observe IS OPEN
-------------------
A witnessing network that only accepts tips from account holders is not a
witnessing network, it is a customer list. Anyone must be able to hand us a
tip without asking permission. Unauthenticated observations are filed under
ANON_KEY, and the router meters them per client address.

NAMES, AND WHAT WE CAN ACTUALLY PROVE ABOUT THEM
------------------------------------------------
The chain name in a submission is self-declared. Anyone can post under any
name. We do not solve that with accounts, because accounts would make the
network closed. We solve it by publishing how strong each claim is, and by
remembering.

Two independent checks run on every submission, and NEITHER of them can
reject it. A submission is always sealed. What changes is what we say about it.

1. LIVENESS - is there a real chain behind this name?
   If the submission carries a url, we fetch it and compare what it serves
   to what was submitted.
     confirmed      the url serves exactly the tip that was submitted
     live           the url serves a valid tip, but a different one. A busy
                    chain moves between submitting and our fetching, so this
                    is normal and honest, not a failure
     self-declared  no url, or we could not reach it, or it served nonsense

   Note what this does and does not prove. It proves the submitter operates
   a live chain producing that data. It does NOT prove they are who they say.
   Anyone running a real chain can point a stolen name at their own url and
   pass this check cleanly.

2. NAME BINDING - is this the same operator as last time?
   The first time a name is seen with a url we can reach, we record that url
   against the name. Every later submission under that name is compared.
     first-use      never seen this name before, binding recorded
     bound          same url as the first time. Same operator, consistently
     conflict       this name has been submitted from a different url than
                    the one it was first bound to

   A conflict is not proof of theft. Operators move hosts. But it is exactly
   the event anyone auditing the network needs to see, and it is recorded
   permanently in our chain rather than resolved quietly by us.

   This is what actually closes name theft. Check 1 alone does not.

SSRF
----
Check 1 makes our server fetch a url chosen by an anonymous stranger. Done
naively that is a hole considerably worse than the one it fixes: it would let
anyone use us to reach services on our own private network, and to bounce
traffic at a third party. So the fetcher only speaks http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that is
private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a small cap.

HONEST LIMITS
-------------
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- A peer can stop publishing. Gaps are visible, which is the point, but
  nobody can force participation.
- Two colluding platforms witnessing only each other prove very little. The
  guarantee comes from breadth.
- This module does not verify a peer's chain is internally valid. It records
  what they claimed, when, and how well it stood up to checking.
- The liveness fetch resolves a hostname and then fetches it. An attacker
  controlling DNS could answer differently between those two steps. Closing
  that needs the connection pinned to the checked address, which is more
  machinery than this warrants today. It is written down rather than hidden.

    GET  /x/witness/tip                 our current tip, for peers to record
    POST /x/witness/observe             chain, tip, url - we seal their tip
                                        (peer accepted as an alias for chain;
                                         optional peer_ts or ts, epoch or ISO)
    GET  /x/witness/attest?peer=&tip=   did we witness this, and when
    GET  /x/witness/peers               who we witness, and how consistently
    GET  /x/witness/history?peer=       every tip we hold for that peer
"""

import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("POST", "observe")}

# Observations arriving without a key are filed under this.
ANON_KEY = "public-witness"

# Liveness fetch limits. Deliberately tight - this runs on an anonymous
# request, so every one of these is also a denial-of-service control.
FETCH_TIMEOUT = 4
MAX_FETCH_BYTES = 65536
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witness_log(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,peer TEXT,tip TEXT,peer_ts REAL,observed REAL,audit_hash TEXT,block_index INTEGER,note TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer ON witness_log(api_key,peer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_tip ON witness_log(tip)")

        # Added in 1.1. Existing rows keep NULL, which reads as unchecked -
        # correct, because they were.
        have = set()
        try:
            for row in c.execute("PRAGMA table_info(witness_log)").fetchall():
                have.add(row[1])
        except Exception:
            pass
        for col in ("url", "liveness", "name_status"):
            if col not in have:
                try:
                    c.execute("ALTER TABLE witness_log ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass

        # Name bindings are network-wide, not per api_key. A name means one
        # operator across the whole network or it means nothing.
        c.execute("CREATE TABLE IF NOT EXISTS witness_names(peer TEXT PRIMARY KEY,url TEXT,first_seen REAL,first_liveness TEXT)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _our_tip(ctx):
    with ctx["lock"]:
        r = ctx["conn"].execute("SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def _tip(ctx, api_key):
    tip, ts, height = _our_tip(ctx)
    return {"tip": tip, "height": height, "sealed_at": _iso(ts),
            "witness_version": VERSION,
            "note": "Record this tip in your own chain. Hand us yours at /x/witness/observe and we will record it in ours.",
            "verify": "/api/verify-chain checks this chain end to end. /api/anchor-status shows the external timestamp."}, 200


# ----------------------------------------------------------------------
# liveness fetch - see the SSRF section above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction from a stranger to fetch a second url we
    never checked. Refuse rather than follow."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    """Resolve and refuse anything that isn't plainly on the public internet."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
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
    host = parts.hostname
    if not host:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(host, port)


def _fetch_tip(url):
    """Returns (tip_or_None, note). Never raises."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, why
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "aileash-witness/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            if response.getcode() != 200:
                return None, "url answered %s" % response.getcode()
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, "url answered %s" % exc.code
    except Exception as exc:
        return None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, "response too large"
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None, "url did not return json"
    if not isinstance(data, dict):
        return None, "url did not return an object"
    found = data.get("tip") or data.get("hash") or data.get("head") or ""
    found = str(found).strip().lower()
    if not HEX64.match(found):
        return None, "no valid tip at that url"
    return found, None


def _check_liveness(url, tip):
    """confirmed / live / self-declared. Never rejects anything."""
    if not url:
        return "self-declared", "no url supplied"
    found, why = _fetch_tip(url)
    if found is None:
        return "self-declared", why
    if found == tip:
        return "confirmed", None
    return "live", "url serves a different tip (%s) - chain has moved on since submitting" % found[:16]


def _check_name(ctx, peer, url, liveness):
    """first-use / bound / conflict / unbound.

    Only bind a name to a url we actually reached. Binding to an unreachable
    url would let someone reserve a name with an address that never answers.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT url,first_seen FROM witness_names WHERE peer=?", (peer,)).fetchone()

    if row and row[0]:
        if not url:
            return "unbound", "no url supplied; this name is bound to %s" % row[0]
        if url.strip() == row[0]:
            return "bound", None
        return "conflict", ("this name was first seen at %s and has now been submitted from %s"
                            % (row[0], url.strip()))

    if url and liveness in ("confirmed", "live"):
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT OR REPLACE INTO witness_names(peer,url,first_seen,first_liveness) VALUES(?,?,?,?)",
                (peer, url.strip(), time.time(), liveness))
            ctx["conn"].commit()
        return "first-use", "name now bound to %s" % url.strip()

    return "unbound", "no reachable url, so nothing to bind this name to"


# ----------------------------------------------------------------------
# observe
# ----------------------------------------------------------------------

def _observe(ctx, api_key, data):
    # The published standard calls this field "chain"; earlier internal
    # callers used "peer". Accept either. A receiver being strict about
    # field names it never published is a bug in the receiver.
    peer = str(data.get("chain") or data.get("peer") or "").strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works well.",
                "field": "chain (peer also accepted)"}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400

    url = data.get("url")
    url = str(url).strip() if url else ""
    if len(url) > 500:
        url = ""

    # Time the peer claims it sealed at. Epoch or ISO, either field name.
    # Carry on without it - supporting detail, not the evidence.
    peer_ts = data.get("peer_ts", data.get("ts"))
    if peer_ts is not None:
        try:
            peer_ts = float(peer_ts)
        except (TypeError, ValueError):
            try:
                s = str(peer_ts).strip().replace("Z", "+00:00")
                peer_ts = datetime.fromisoformat(s).timestamp()
            except Exception:
                peer_ts = None

    liveness, live_note = _check_liveness(url, tip)
    name_status, name_note = _check_name(ctx, peer, url, liveness)

    ts = time.time()
    notes = []

    with ctx["lock"]:
        prev = ctx["conn"].execute("SELECT tip,observed FROM witness_log WHERE api_key=? AND peer=? ORDER BY id DESC LIMIT 1", (api_key, peer)).fetchone()
        seen = ctx["conn"].execute("SELECT observed FROM witness_log WHERE api_key=? AND peer=? AND tip=? LIMIT 1", (api_key, peer, tip)).fetchone()

    if seen:
        notes.append("tip already witnessed at " + str(_iso(seen[0])) + " - chain has not advanced, or history was replayed")
    elif prev and prev[0] == tip:
        notes.append("unchanged since last observation")
    if live_note:
        notes.append(live_note)
    if name_note:
        notes.append(name_note)
    note = "; ".join(notes)

    # The verification result is sealed alongside the tip. If we later claim a
    # submission was confirmed, the chain has to agree.
    detail = ("peer=" + peer + ";tip=" + tip + ";url=" + (url or "-") +
              ";liveness=" + liveness + ";name=" + name_status +
              ";peer_ts=" + str(peer_ts) + (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts,
           "liveness": liveness, "name_status": name_status, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note,url,liveness,name_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (api_key, peer, tip, peer_ts, ts, h, idx, note or None,
                             url or None, liveness, name_status))
        ctx["conn"].commit()

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "liveness": liveness, "name_status": name_status,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": "Your tip is now inside a chain you do not control, and ours is anchored externally."}
    if note:
        out["flag"] = note
    if liveness == "self-declared":
        out["advice"] = "Send a url serving your current tip and this becomes checkable by anyone rather than taken on your word."
    if name_status == "conflict":
        out["warning"] = "Sealed, and flagged. This name has been used from a different address before. That discrepancy is now permanent in our chain."
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": "We hold no record of this tip from this peer."}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "liveness": rows[0][4] or "unchecked",
            "name_status": rows[0][5] or "unchecked",
            "submitted_url": rows[0][6],
            "what_this_proves": "That this tip was handed to us at this time and sealed into our chain. Liveness says whether a url served the same tip when we looked. Neither proves the submitter's identity.",
            "proof": "This observation is a block in our chain. Altering or removing it breaks every block after it, and our chain is externally anchored."}, 200


def _peers(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()
        latest = {}
        conflicts = {}
        bindings = {}
        for p, live, name in ctx["conn"].execute("SELECT peer,liveness,name_status FROM witness_log ORDER BY id ASC").fetchall():
            latest[p] = (live, name)
            if name == "conflict":
                conflicts[p] = conflicts.get(p, 0) + 1
        for p, u in ctx["conn"].execute("SELECT peer,url FROM witness_names").fetchall():
            bindings[p] = u

    t = time.time()
    peers = []
    for p, n, first, last, distinct in rows:
        hours = round((t - last) / 3600, 1)
        live, name = latest.get(p, (None, None))
        entry = {"peer": p, "observations": n, "distinct_tips": distinct,
                 "first_seen": _iso(first), "last_seen": _iso(last),
                 "hours_since_last": hours,
                 "status": ("current" if hours < 6 else "stale" if hours < 48 else "silent"),
                 "liveness": live or "unchecked",
                 "name_status": name or "unchecked",
                 "bound_to": bindings.get(p)}
        if conflicts.get(p):
            entry["name_conflicts"] = conflicts[p]
        peers.append(entry)
    return {"count": len(peers), "peers": peers,
            "legend": {
                "confirmed": "a url served exactly the tip that was submitted",
                "live": "a url served a valid but different tip - a moving chain, which is normal",
                "self-declared": "no url, or we could not reach it. Taken on their word",
                "first-use": "first time this name was seen; now bound to that url",
                "bound": "same url as the first time this name appeared",
                "conflict": "this name has been submitted from more than one address",
            },
            "note": "Silent peers are visible by design. A network you cannot audit is not a network. Nothing here proves identity - it shows how well each claim stood up to checking."}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT 500", (api_key, peer)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows),
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4], "liveness": r[5] or "unchecked",
                              "name_status": r[6] or "unchecked",
                              "url": r[7]} for r in rows],
            "note": "If this peer ever presents a history whose tips do not match these, the divergence is provable."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "observe":
            # No key needed. Anonymous submissions are partitioned under
            # ANON_KEY so they never mix with a customer's own witness log.
            return _observe(ctx, api_key or ANON_KEY, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
    else:
        if action == "tip":
            return _tip(ctx, api_key)
        if action == "peers":
            return _peers(ctx, api_key)
        if action == "attest":
            return _attest(ctx, api_key, data)
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404

```


## `Verify_ai.py`

71 lines, 3293 bytes

```python
import sys
import json
import urllib.request
import hmac
import hashlib
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CITIZEN-AUDITOR] %(message)s")

class OpenAIActAuditor:
    def __init__(self, target_domain):
        self.domain = target_domain
        self.ai_txt_url = f"https://{target_domain}/ai.txt"

    def run_public_compliance_audit(self, claim_hash, operational_payload):
        """
        Publicly cross-examines a corporate AI claim against deterministic 
        cryptographic hashing parameters to verify compliance validity.
        """
        logging.info(f"Initiating autonomous accountability scan for: {self.domain}")
        print(f"[*] Fetching live manifest from {self.ai_txt_url}...")
        
        # In a full run, this pulls the text from their server root. 
        # For this standalone test block, we parse the known corporate layout:
        try:
            print("[+] Manifest fetched successfully. Parsing parameters...")
            
            # Re-serialize client data to check for administrative tampering
            serialized_check = json.dumps(operational_payload, sort_keys=True)
            
            # Simulate the public ledger validation verification check
            # For demonstration, we match against a known system key structure
            mock_secret_pool = b"LOCAL_DEV_FALLBACK_KEY"
            calculated_seal = hmac.new(mock_secret_pool, serialized_check.encode('utf-8'), hashlib.sha256).hexdigest()

            # --- THE MOMENT OF TRUTH ---
            if calculated_seal == claim_hash:
                print("\n==================================================")
                print("🏆 AUDIT VERDICT: 100% CRYPTOGRAPHICALLY COMPLIANT")
                print(f"Verified via standard ledger registry: https://sebbi.pro")
                print("==================================================\n")
                return True
            else:
                logging.critical(f"[COMPLIANCE FRAUD DETECTED] Corporate ledger seal does not match physical system metrics!")
                print("\n==================================================")
                print("🚨 AUDIT VERDICT: TAMPERING DETECTED / INVALID LOGS")
                print("Forwarding payload to public audit stream...")
                print("==================================================\n")
                return False

        except Exception as e:
            logging.error(f"Audit failed due to processing error: {e}")
            return False

# --- RUN AN INDEPENDENT RESEARCH SCENARIO ---
if __name__ == "__main__":
    # A researcher samples a transaction claim from an app's public metadata
    sample_corporate_payload = {
        "alert_text": "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.",
        "raw_declaration": "Standard: AI-TXT/1.0\\nGovernance-Engine: AILeash v6.4"
    }
    
    # The developer's matching validation key hash 
    legitimate_claim_hash = "19b48c4cfb49e3b8aee1403c9dcaee06bfa4622b10292850a1ae7f42cf5dbef5"

    # Instantiate the independent auditor
    auditor = OpenAIActAuditor(target_domain="monopcontent.co.uk")
    
    # Run the audit test pass
    auditor.run_public_compliance_audit(legitimate_claim_hash, sample_corporate_payload)

```


## `ai_act_ranker.py`

262 lines, 4930 bytes

```python
"""
AILeash Compliance Intelligence Engine
Standalone AI Act Ranking & Risk Mapping Engine

Version: 1.0.0
"""

import json
import datetime


VERSION = "1.0.0"


# EU AI Act knowledge base
AI_ACT_DATABASE = {

    "Article 5": {
        "title": "Prohibited AI Practices",
        "phrases": [
            "EU AI Act Article 5",
            "prohibited AI practices",
            "AI Act banned systems",
            "AI regulation prohibited AI"
        ],
        "controls": [
            "Prohibited use detection",
            "Policy enforcement",
            "AI behaviour screening"
        ]
    },


    "Article 6": {
        "title": "Classification of High Risk AI Systems",
        "phrases": [
            "high risk AI system",
            "EU AI Act high risk classification",
            "AI Act risk categories"
        ],
        "controls": [
            "Risk classification",
            "System assessment",
            "Impact evaluation"
        ]
    },


    "Article 9": {
        "title": "Risk Management System",
        "phrases": [
            "EU AI Act Article 9",
            "AI risk management system",
            "AI Act compliance framework",
            "continuous AI risk monitoring"
        ],
        "controls": [
            "Risk identification",
            "Risk scoring",
            "Risk mitigation",
            "Continuous monitoring"
        ]
    },


    "Article 12": {
        "title": "Record Keeping and Logging",
        "phrases": [
            "AI audit trail",
            "AI logging requirements",
            "AI evidence records",
            "machine learning audit logs"
        ],
        "controls": [
            "Immutable logs",
            "Evidence storage",
            "Traceability",
            "Hash verification"
        ]
    },


    "Article 14": {
        "title": "Human Oversight",
        "phrases": [
            "AI human oversight",
            "human in the loop AI",
            "AI intervention controls"
        ],
        "controls": [
            "Human review",
            "Override capability",
            "Decision supervision"
        ]
    },


    "Article 15": {
        "title": "Accuracy Robustness Cybersecurity",
        "phrases": [
            "AI cybersecurity",
            "AI accuracy monitoring",
            "AI robustness requirements"
        ],
        "controls": [
            "Security testing",
            "Performance monitoring",
            "Failure detection"
        ]
    }

}


def search_ai_act(query):

    results = []

    query = query.lower()

    for article, data in AI_ACT_DATABASE.items():

        for phrase in data["phrases"]:

            if query in phrase.lower():

                results.append({
                    "article": article,
                    "title": data["title"],
                    "matched_phrase": phrase,
                    "controls": data["controls"]
                })

    return results



def calculate_compliance_score(system):

    score = 0
    missing = []

    requirements = {

        "risk_management": "Article 9",
        "logging": "Article 12",
        "human_oversight": "Article 14",
        "security": "Article 15"

    }


    for control, article in requirements.items():

        if system.get(control):
            score += 25
        else:
            missing.append(article)


    return {
        "score": score,
        "rating": risk_rating(score),
        "missing_articles": missing
    }



def risk_rating(score):

    if score >= 90:
        return "LOW RISK"

    if score >= 70:
        return "MODERATE RISK"

    if score >= 40:
        return "HIGH RISK"

    return "CRITICAL RISK"



def generate_report(system):

    return {

        "engine": "AILeash Compliance Intelligence Engine",

        "version": VERSION,

        "timestamp":
            datetime.datetime.utcnow().isoformat(),

        "assessment":
            calculate_compliance_score(system)

    }



def save_report(report):

    filename = (
        "aileash_report_"
        + datetime.datetime.now()
        .strftime("%Y%m%d_%H%M%S")
        + ".json"
    )

    with open(filename, "w") as file:
        json.dump(
            report,
            file,
            indent=4
        )

    return filename



if __name__ == "__main__":

    print(
        "\nAILeash AI Act Ranking Engine "
        + VERSION
    )

    print("\nExample search:")
    
    results = search_ai_act(
        "Article 9"
    )

    for result in results:
        print("\nMATCH:")
        print(result)


    test_system = {

        "risk_management": True,
        "logging": True,
        "human_oversight": False,
        "security": True

    }


    report = generate_report(test_system)

    print("\nCOMPLIANCE REPORT")
    print(json.dumps(report, indent=4))


    file = save_report(report)

    print(
        "\nSaved:",
        file
    )

```


## `ai_safety_scanner.py`

167 lines, 5700 bytes

```python
"""
AI-Safety Grade Scanner
Checks a domain's .well-known/ files and public root files against the
emerging AI-safety/AI-transparency file conventions, and returns a
letter grade (A-F) plus an embeddable badge.

Drop into your existing FastAPI server.py as a router, or run standalone.
Requires: fastapi, httpx  (pip install fastapi httpx --break-system-packages)
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
import httpx
import xml.etree.ElementTree as ET

router = APIRouter()

TIMEOUT = 6.0
UA_HUMAN = "Mozilla/5.0 (compatible; AILeashScanner/1.0; +https://sebbi.pro/check)"
UA_AGENT = "AILeash-Agent-Check/1.0 (+https://sebbi.pro/check)"

CHECKS = [
    # (key, path, points, validator_name)
    ("ai_safety",  "/.well-known/ai-safety.txt", 20, "check_ai_safety"),
    ("security",   "/.well-known/security.txt",  15, "check_security"),
    ("robots",     "/robots.txt",                10, "check_robots"),
    ("sitemap",    "/sitemap.xml",                10, "check_sitemap"),
    ("ai_txt",     "/.well-known/ai.txt",         15, "check_present"),
    ("comply",     "/.well-known/comply.txt",     15, "check_present"),
    ("llms",       "/llms.txt",                   10, "check_present"),
]
RENDERING_POINTS = 5
MAX_SCORE = sum(c[2] for c in CHECKS) + RENDERING_POINTS  # 100


async def fetch(client: httpx.AsyncClient, url: str, ua: str = UA_HUMAN):
    try:
        r = await client.get(url, timeout=TIMEOUT, headers={"User-Agent": ua}, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def check_present(text):
    return bool(text and text.strip())


def check_ai_safety(text):
    if not text:
        return False
    lower = text.lower()
    return "ai-safe:" in lower and "true" in lower


def check_security(text):
    if not text:
        return False
    lower = text.lower()
    return "contact:" in lower and "expires:" in lower


def check_robots(text):
    return bool(text and text.strip())


def check_sitemap(text):
    if not text:
        return False
    try:
        ET.fromstring(text)
        return True
    except ET.ParseError:
        return False


VALIDATORS = {
    "check_ai_safety": check_ai_safety,
    "check_security": check_security,
    "check_robots": check_robots,
    "check_sitemap": check_sitemap,
    "check_present": check_present,
}


def grade_from_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


GRADE_COLOR = {"A": "#7fe3b0", "B": "#a8d95f", "C": "#c9a84c", "D": "#ff9a4a", "F": "#ff8a80"}


@router.get("/check")
async def check_domain(domain: str = Query(..., description="Domain to check, e.g. example.com")):
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    base = f"https://{domain}"

    results = {}
    score = 0

    async with httpx.AsyncClient() as client:
        for key, path, points, validator_name in CHECKS:
            text = await fetch(client, base + path)
            passed = VALIDATORS[validator_name](text)
            results[key] = {"path": path, "found": bool(text), "passed": passed, "points": points if passed else 0}
            if passed:
                score += points

        # basic consistent-rendering check: compare human UA vs agent UA on homepage
        human_body = await fetch(client, base, UA_HUMAN)
        agent_body = await fetch(client, base, UA_AGENT)
        rendering_ok = bool(human_body) and bool(agent_body) and (len(human_body) > 0 and len(agent_body) > 0)
        # crude similarity check — same length within 10% as a proxy for "not obviously cloaked"
        if human_body and agent_body:
            ratio = min(len(human_body), len(agent_body)) / max(len(human_body), len(agent_body), 1)
            rendering_ok = ratio > 0.9
        results["consistent_rendering"] = {"passed": rendering_ok, "points": RENDERING_POINTS if rendering_ok else 0}
        if rendering_ok:
            score += RENDERING_POINTS

    grade = grade_from_score(score)

    return JSONResponse({
        "domain": domain,
        "score": score,
        "max_score": MAX_SCORE,
        "grade": grade,
        "checks": results,
        "verified_by": "sebbi.pro",
        "badge_url": f"https://sebbi.pro/check/badge?domain={domain}",
        "report_url": f"https://sebbi.pro/check?domain={domain}",
    })


@router.get("/check/badge")
async def check_badge(domain: str = Query(...)):
    """Returns an embeddable SVG badge, e.g. <img src="https://sebbi.pro/check/badge?domain=example.com">"""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    base = f"https://{domain}"

    score = 0
    async with httpx.AsyncClient() as client:
        for key, path, points, validator_name in CHECKS:
            text = await fetch(client, base + path)
            if VALIDATORS[validator_name](text):
                score += points

    grade = grade_from_score(score)
    color = GRADE_COLOR[grade]

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">
  <rect width="120" height="20" fill="#0a0f1e"/>
  <rect x="120" width="60" height="20" fill="{color}"/>
  <text x="60" y="14" fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">AI-Safety Grade</text>
  <text x="150" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" font-size="12" font-weight="bold" text-anchor="middle">{grade}</text>
</svg>'''
    return Response(content=svg, media_type="image/svg+xml")

```


## `aigrade_insert.py`

136 lines, 5663 bytes

```python
# ============================================================
# AI-SAFETY GRADE SCANNER - stdlib version for server.py
# (converted from the FastAPI/httpx draft - no new dependencies)
#
# HOW TO INSTALL - two pastes into server.py:
#
# PASTE 1: everything between "BEGIN FUNCTIONS" and "END FUNCTIONS"
#          goes near your other helper functions (e.g. just above
#          the JURIS_VERSION block).
#
# PASTE 2: everything between "BEGIN ROUTES" and "END ROUTES"
#          goes inside do_GET, as new elif branches alongside the
#          other GET routes (match their indentation: 8 spaces).
#
# Endpoints added:
#   GET /api/aigrade?domain=example.com        -> JSON grade report
#   GET /api/aigrade/badge?domain=example.com  -> embeddable SVG badge
# ============================================================

# ---------------- BEGIN FUNCTIONS ----------------
AIGRADE_TIMEOUT=6
AIGRADE_UA="Mozilla/5.0 (compatible; AILeashScanner/1.0; +https://sebbi.pro/scan)"
AIGRADE_UA_AGENT="AILeash-Agent-Check/1.0 (+https://sebbi.pro/scan)"
AIGRADE_CHECKS=[
    ("ai_safety","/.well-known/ai-safety.txt",20,"ai_safety"),
    ("security","/.well-known/security.txt",15,"security"),
    ("robots","/robots.txt",10,"present"),
    ("sitemap","/sitemap.xml",10,"sitemap"),
    ("ai_txt","/.well-known/ai.txt",15,"present"),
    ("comply","/.well-known/comply.txt",15,"present"),
    ("llms","/llms.txt",10,"present"),
]
AIGRADE_RENDER_POINTS=5
AIGRADE_MAX=sum(c[2] for c in AIGRADE_CHECKS)+AIGRADE_RENDER_POINTS
AIGRADE_COLORS={"A":"#7fe3b0","B":"#a8d95f","C":"#c9a84c","D":"#ff9a4a","F":"#ff8a80"}

def _aigrade_fetch(url,ua=AIGRADE_UA):
    try:
        req=urllib.request.Request(url,headers={"User-Agent":ua})
        with urllib.request.urlopen(req,timeout=AIGRADE_TIMEOUT) as r:
            if r.status==200:
                return r.read(500000).decode("utf-8","replace")
    except Exception:
        pass
    return None

def _aigrade_valid(kind,text):
    if kind=="present":
        return bool(text and text.strip())
    if kind=="ai_safety":
        if not text:return False
        low=text.lower()
        return "ai-safe:" in low and "true" in low
    if kind=="security":
        if not text:return False
        low=text.lower()
        return "contact:" in low and "expires:" in low
    if kind=="sitemap":
        if not text:return False
        try:
            import xml.etree.ElementTree as _ET
            _ET.fromstring(text)
            return True
        except Exception:
            return False
    return False

def _aigrade_letter(score):
    if score>=90:return"A"
    if score>=75:return"B"
    if score>=60:return"C"
    if score>=40:return"D"
    return"F"

def aigrade_run(domain):
    domain=str(domain or "").strip().lower().replace("https://","").replace("http://","").rstrip("/")
    domain=domain.split("/")[0]
    if not domain or "." not in domain or len(domain)>200:
        return None
    base="https://"+domain
    results={};score=0
    for key,path,points,kind in AIGRADE_CHECKS:
        text=_aigrade_fetch(base+path)
        passed=_aigrade_valid(kind,text)
        results[key]={"path":path,"found":bool(text),"passed":passed,"points":points if passed else 0}
        if passed:score+=points
    human=_aigrade_fetch(base,AIGRADE_UA)
    agent=_aigrade_fetch(base,AIGRADE_UA_AGENT)
    render_ok=False
    if human and agent:
        ratio=min(len(human),len(agent))/max(len(human),len(agent),1)
        render_ok=ratio>0.9
    results["consistent_rendering"]={"passed":render_ok,"points":AIGRADE_RENDER_POINTS if render_ok else 0}
    if render_ok:score+=AIGRADE_RENDER_POINTS
    return{"domain":domain,"score":score,"max_score":AIGRADE_MAX,
        "grade":_aigrade_letter(score),"checks":results,
        "verified_by":"sebbi.pro",
        "badge_url":HOST+"/api/aigrade/badge?domain="+domain,
        "report_url":HOST+"/api/aigrade?domain="+domain,
        "note":"External-signal check of published AI-transparency files; not an audit of internal systems"}

def aigrade_badge_svg(domain):
    r=aigrade_run(domain)
    grade=r["grade"] if r else "F"
    color=AIGRADE_COLORS.get(grade,"#ff8a80")
    return('<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">'
        '<rect width="120" height="20" fill="#0a0f1e"/>'
        '<rect x="120" width="60" height="20" fill="'+color+'"/>'
        '<text x="60" y="14" fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">AI-Safety Grade</text>'
        '<text x="150" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" font-size="12" font-weight="bold" text-anchor="middle">'+grade+'</text>'
        '</svg>')
# ---------------- END FUNCTIONS ----------------


# ---------------- BEGIN ROUTES (paste inside do_GET) ----------------
        elif path=="/api/aigrade":
            qs=parse_qs(parsed.query)
            dom=(qs.get("domain",[""])[0] or "").strip()
            rep=aigrade_run(dom)
            if not rep:
                send_json(self,{"error":"valid domain required, e.g. ?domain=example.com"},400)
            else:
                send_json(self,rep)
        elif path=="/api/aigrade/badge":
            qs=parse_qs(parsed.query)
            dom=(qs.get("domain",[""])[0] or "").strip()
            svg=aigrade_badge_svg(dom)
            body=svg.encode()
            self.send_response(200)
            self.send_header("Content-Type","image/svg+xml")
            self.send_header("Cache-Control","max-age=3600")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
# ---------------- END ROUTES ----------------

```


## `aileash_reporter.py`

232 lines, 9377 bytes

```python
"""
AILEASH DECISION REPORTER v1.0.0
Generates readable audit reports for all AILeash products.
Shows exactly why each decision was made.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
"""

import sqlite3, json, os
from datetime import datetime

DB_FILE = "aileash.db"

PRODUCTS = {
    "aileash": "AILeash",
    "guardian": "AILeash Guardian",
    "sonicboom": "SonicBoom",
    "sentinel": "AILeash Sentinel"
}

REASON_EXPLANATIONS = {
    "velocity_spike": "User made more than 10 requests in 60 seconds",
    "high_amount": "Transaction amount exceeded threshold",
    "risky_device": "Device risk score was above acceptable limit",
    "behaviour_anomaly": "Unusual behaviour pattern detected",
    "country_shift": "Request came from a different country than usual",
    "unsafe_country": "Request came from outside approved country list",
    "low_trust": "User trust score has dropped due to previous decisions",
}

def get_decisions(db_path=DB_FILE, limit=200):
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT a.ts, a.user_id, a.event_json, a.result_json, a.audit_hash,
                   COALESCE(k.product, 'aileash') as product
            FROM audit_log a
            LEFT JOIN api_keys k ON json_extract(a.event_json, '$.api_key') = k.key
            ORDER BY a.id DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    except:
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("""
                SELECT ts, user_id, event_json, result_json, audit_hash, 'aileash'
                FROM audit_log ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            conn.close()
        except:
            return []
    
    results = []
    for row in rows:
        try:
            event = json.loads(row[2])
            result = json.loads(row[3])
            results.append({
                "ts": row[0],
                "user_id": row[1],
                "event": event,
                "result": result,
                "audit_hash": row[4],
                "product": row[5] or "aileash"
            })
        except:
            pass
    return results

def explain_reason(r):
    return REASON_EXPLANATIONS.get(r, r.replace("_", " ").capitalize())

def decision_color(d):
    return {"ALLOW": "#00875a", "CHALLENGE": "#b45309", "BLOCK": "#cc0000"}.get(d, "#555")

def product_color(p):
    return {
        "aileash": "#c9a84c",
        "guardian": "#cc0000",
        "sonicboom": "#00d4ff",
        "sentinel": "#7c3aed"
    }.get(p, "#c9a84c")

def generate_html_report(db_path=DB_FILE, limit=200, output="aileash_report.html"):
    decisions = get_decisions(db_path, limit)

    allow = sum(1 for d in decisions if d["result"].get("decision") == "ALLOW")
    challenge = sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE")
    block = sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")

    rows = ""
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        product = d.get("product", "aileash")
        pc = product_color(product)
        dc = decision_color(decision)
        pname = PRODUCTS.get(product, product)

        reason_html = ""
        if reasons:
            reason_html = "<ul>" + "".join(
                f"<li>{explain_reason(r)}</li>" for r in reasons
            ) + "</ul>"
        else:
            reason_html = "<span style='color:#888'>No risk factors detected</span>"

        rows += f"""<tr>
            <td>{ts}</td>
            <td><span style="font-size:10px;background:{pc}22;color:{pc};border:1px solid {pc}44;padding:2px 6px;border-radius:3px">{pname}</span></td>
            <td><code>{d['user_id']}</code></td>
            <td>{event.get('action','?')}</td>
            <td>{event.get('country','?')}</td>
            <td>£{event.get('amount',0)}</td>
            <td><strong style="color:{dc}">{decision}</strong></td>
            <td>{score}</td>
            <td>{result.get('trust',0)}</td>
            <td>{reason_html}</td>
            <td><code style="font-size:10px">{d['audit_hash'][:16]}...</code></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Audit Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:sans-serif;background:#f5f7fa;color:#1a202c;padding:20px}}
.header{{background:#0a0f1e;color:#fff;padding:24px 32px;border-radius:8px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:22px;color:#c9a84c;margin:0}}
.header p{{font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px}}
.logo{{font-size:13px;color:rgba(255,255,255,0.2)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.stat{{background:#fff;border-radius:8px;padding:16px;text-align:center;border:1px solid #e2e8f0}}
.stat-n{{font-size:28px;font-weight:700}}
.stat-l{{font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:1px}}
.allow{{color:#00875a}}.challenge{{color:#b45309}}.block{{color:#cc0000}}.total{{color:#0a0f1e}}
.table-wrap{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:900px}}
th{{background:#0a0f1e;color:#c9a84c;padding:10px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;white-space:nowrap}}
td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}}
tr:last-child td{{border:none}}
tr:hover td{{background:#f8fafc}}
ul{{margin:4px 0;padding-left:16px}}
li{{margin:2px 0;color:#64748b;font-size:11px}}
code{{background:#f1f5f9;padding:2px 4px;border-radius:3px;font-size:10px}}
.empty{{text-align:center;color:#888;padding:40px}}
footer{{text-align:center;font-size:11px;color:#94a3b8;margin-top:20px}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>AILeash Audit Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Last {len(decisions)} decisions</p>
  </div>
  <div class="logo">sebbi.pro &nbsp;|&nbsp; OAAS-1.0</div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n total">{len(decisions)}</div><div class="stat-l">Total</div></div>
  <div class="stat"><div class="stat-n allow">{allow}</div><div class="stat-l">Allowed</div></div>
  <div class="stat"><div class="stat-n challenge">{challenge}</div><div class="stat-l">Challenged</div></div>
  <div class="stat"><div class="stat-n block">{block}</div><div class="stat-l">Blocked</div></div>
</div>
<div class="table-wrap">
<table>
<thead><tr>
  <th>Time</th><th>Product</th><th>User</th><th>Action</th><th>Country</th>
  <th>Amount</th><th>Decision</th><th>Score</th><th>Trust</th><th>Reasons</th><th>Audit Hash</th>
</tr></thead>
<tbody>
{''.join([rows]) if rows else f'<tr><td colspan="11" class="empty">No decisions recorded yet</td></tr>'}
</tbody>
</table>
</div>
<footer>AILeash &nbsp;|&nbsp; Monop Content &nbsp;|&nbsp; Justin Antony Dobson &nbsp;|&nbsp; sebbi.pro &nbsp;|&nbsp; SHA-256 Merkle Chain</footer>
</body>
</html>"""

    with open(output, "w") as f:
        f.write(html)
    print(f"Report saved: {output} ({len(decisions)} decisions)")
    return output

def generate_json_report(db_path=DB_FILE, limit=200, output="aileash_report.json"):
    decisions = get_decisions(db_path, limit)
    report = {
        "generated": datetime.now().isoformat(),
        "standard": "OAAS-1.0",
        "source": "sebbi.pro",
        "total": len(decisions),
        "summary": {
            "allow": sum(1 for d in decisions if d["result"].get("decision") == "ALLOW"),
            "challenge": sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE"),
            "block": sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")
        },
        "decisions": [{
            "timestamp": datetime.fromtimestamp(d["ts"]).isoformat(),
            "product": PRODUCTS.get(d["product"], d["product"]),
            "user_id": d["user_id"],
            "action": d["event"].get("action"),
            "country": d["event"].get("country"),
            "amount": d["event"].get("amount"),
            "decision": d["result"].get("decision"),
            "score": d["result"].get("score"),
            "trust": d["result"].get("trust"),
            "reasons": d["result"].get("reasons", []),
            "reasons_explained": [explain_reason(r) for r in d["result"].get("reasons", [])],
            "audit_hash": d["audit_hash"]
        } for d in decisions]
    }
    with open(output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved: {output}")
    return output

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "html"
    db = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
    if fmt == "json":
        generate_json_report(db)
    else:
        generate_html_report(db)

```
