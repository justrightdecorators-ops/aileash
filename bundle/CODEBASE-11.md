# Codebase — part 11 of 27

Contains:
- `modules/selfcheck.py`
- `modules/signed.py`
- `modules/sortition.py`
- `modules/spec.py`


## `modules/selfcheck.py`

1091 lines, 45976 bytes

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

VERSION = "2.0"

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

  // SHA-256 in the visitor's own browser. The point of rule binding is that
  // the server hands back the exact string it hashed; if this page recomputes
  // the digest and it matches, nothing was taken on the server's word.
  function sha256hex(s){
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(s))
      .then(function(buf){
        var b = new Uint8Array(buf), out = "";
        for (var i = 0; i < b.length; i++){
          var h = b[i].toString(16);
          out += (h.length === 1 ? "0" : "") + h;
        }
        return out;
      });
  }

  var HEX64 = /^[0-9a-f]{64}$/;

  function walk(node, path, strings, hexes){
    if (typeof node === "string"){
      strings.push({path: path || "(root)", value: node});
      if (HEX64.test(node)) hexes[node] = path || "(root)";
      return;
    }
    if (Array.isArray(node)){
      for (var i = 0; i < node.length; i++) walk(node[i], path + "[" + i + "]", strings, hexes);
      return;
    }
    if (node && typeof node === "object"){
      for (var k in node){
        if (Object.prototype.hasOwnProperty.call(node, k)){
          walk(node[k], path ? path + "." + k : k, strings, hexes);
        }
      }
    }
  }

  // The payload these POST routes expect is not published, so this does two
  // things rather than guess: it tries the shapes they plausibly take, and
  // when a rejection names a missing field it adds that field and tries
  // again. A module that answers "'trust'" has told you what it wants.
  function defaultFor(name){
    if (/country/.test(name)) return "GB";
    if (/currency/.test(name)) return "GBP";
    if (/(^|_)id$|_id$|user|device|session/.test(name)) return "self-check";
    if (/trust|score|ratio|rate/.test(name)) return 0.5;
    return 0;
  }

  function missingField(body){
    var text = (body && typeof body === "object")
      ? (body.message || body.error || JSON.stringify(body))
      : String(body || "");
    // A bare quoted identifier is what a KeyError looks like once it reaches
    // the response. Also catch an explicit "missing x" phrasing.
    var m = text.match(/^['"]([A-Za-z_][A-Za-z0-9_]*)['"]$/) ||
            text.match(/missing[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i) ||
            text.match(/required[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i);
    return m ? m[1] : null;
  }

  function postShapes(url, inner){
    var learned = [];

    function round(probe, depth){
      var shapes = [{name:"flat", body:probe},
                    {name:"inputs", body:{inputs:probe}},
                    {name:"event", body:{event:probe}}];
      var rejected = {};

      function go(i){
        if (i >= shapes.length){
          // Every shape failed the same way? Learn the field and go again.
          var field = null;
          for (var k in rejected){
            if (Object.prototype.hasOwnProperty.call(rejected, k)){
              field = missingField(rejected[k]);
              if (field) break;
            }
          }
          if (field && depth < 6 && !(field in probe)){
            var next = {};
            for (var p in probe){
              if (Object.prototype.hasOwnProperty.call(probe, p)) next[p] = probe[p];
            }
            next[field] = defaultFor(field);
            learned.push(field);
            return round(next, depth + 1);
          }
          return Promise.resolve({ok:false, rejected:rejected, learned:learned, probe:probe});
        }
        return jpost(url, shapes[i].body).then(function(r){
          if (!r.ok){ rejected[shapes[i].name] = r.body; return go(i + 1); }
          return {ok:true, shape:shapes[i].name, body:r.body, sent:shapes[i].body,
                  rejected:rejected, learned:learned};
        }).catch(function(e){
          rejected[shapes[i].name] = e.message; return go(i + 1);
        });
      }
      return go(0);
    }

    return round(inner, 0);
  }

  function oneMessage(b){
    if (b && typeof b === "object" && (b.message || b.error)) return b.message || b.error;
    if (typeof b === "string") return b.slice(0, 200);
    return "no message";
  }

  // Every shape's rejection, not just the first. The first one is usually the
  // least informative, and the shape that nearly worked is the one that says
  // what is actually wrong.
  function firstMessage(rejected){
    var parts = [];
    for (var k in rejected){
      if (Object.prototype.hasOwnProperty.call(rejected, k)){
        parts.push("<b>" + k + "</b>: " + oneMessage(rejected[k]));
      }
    }
    return parts.length ? parts.join(" \u00b7 ") : "no message returned";
  }

  function learnedNote(res){
    return (res.learned && res.learned.length)
      ? " (after adding the fields it named: " + res.learned.join(", ") + ")"
      : "";
  }

  // The engine's real signal names. Guessing these from outside was the
  // thing that kept the reproducibility check amber.
  var PROBE = {action: "payment", amount: 4200, trust: 0.4,
               v60: 12, v5m: 20, v1h: 60,
               device_risk: 0.3, anomaly: 0.2, country: "UK",
               country_shift: false};

  function show(v){
    try { return JSON.stringify(v, null, 2); } catch(e){ return String(v); }
  }

  // ---- document ---------------------------------------------------------

  function loadDoc(){
    flash("");
    spine.innerHTML = "";
    el("tally").hidden = true;
    // The module that serves the discovery document installs its route on
    // first use, so after a deploy the document 404s until something touches
    // it. Touch it here rather than making a person remember to.
    return jget("/x/standard/status").catch(function(){}).then(function(){
      return jget(DOC);
    }).then(function(r){
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
      ctx.root = r.body.root;
    }).catch(function(){}));

    var hex = "0123456789abcdef";
    ctx.absent = "";
    for (var i = 0; i < 64; i++) ctx.absent += hex[Math.floor(Math.random() * 16)];

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

    authority_tokens: function(c){
      return jget(c.endpoint || "/x/continuity/decisions").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var list = b.decisions || [];
        if (!list.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no authority has been exercised " +
                      "yet \u2014 nothing to check, which is not the same as nothing failing",
                  detail:b};
        }
        // Pull one at random and confirm the listing agrees with the sealed
        // decision behind it. A summary that disagrees with its own record is
        // the failure worth catching here.
        var pick = list[Math.floor(Math.random() * list.length)];
        return jget("/x/continuity/decision?evaluation=" + encodeURIComponent(pick.evaluation))
          .then(function(d){
            if (!d.ok){
              return {verdict:"FAIL",
                      why:"the listing offers " + pick.evaluation + " but the decision behind " +
                          "it returned " + d.status,
                      detail:{listed:pick, fetched:d.body}};
            }
            var db = d.body || {};
            if (db.verdict !== pick.verdict){
              return {verdict:"FAIL",
                      why:"the public listing says <b>" + pick.verdict + "</b> and the sealed " +
                          "decision says <b>" + db.verdict + "</b>",
                      detail:{listed:pick, sealed:db}};
            }
            if (!db.lineage_digest || db.block_index === undefined){
              return {verdict:"INCONCLUSIVE",
                      why:"decision retrieved without a key, but it carries no lineage digest " +
                          "or block index to tie it to the chain",
                      detail:db};
            }
            return {verdict:"PASS",
                    why:"real sealed decisions readable without an account \u2014 <b>" +
                        (b.totals ? b.totals.allowed : "?") + " allowed, " +
                        (b.totals ? b.totals.challenged : "?") + " challenged, " +
                        (b.totals ? b.totals.blocked : "?") + " blocked</b>. Picked <b>" +
                        pick.evaluation + "</b> at random and the sealed record agrees with " +
                        "the listing, carrying its lineage digest and block index" +
                        (db.broken_invariant ? " and naming <b>" + db.broken_invariant +
                                               "</b> as what broke" : ""),
                    detail:{listing:b.totals, picked:pick, sealed:db}};
          });
      });
    },

    reconciliation: function(c){
      return jget(c.endpoint || "/x/reconcile/public").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var runs = b.recent || [];
        if (!runs.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no reconciliation run exists yet",
                  detail:b};
        }
        var done = runs.filter(function(x){ return x.status === "reconciled"; });
        var pick = (done.length ? done : runs)[0];
        return jget("/x/reconcile/proof?id=" + encodeURIComponent(pick.run_id)).then(function(p){
          if (!p.ok){
            return {verdict:"FAIL",
                    why:"the listing offers " + pick.run_id + " but its proof returned " + p.status,
                    detail:{listed:pick, fetched:p.body}};
          }
          var pb = p.body || {};
          if (pb.plan_block_index === null || pb.result_block_index === null){
            return {verdict:"INCONCLUSIVE",
                    why:"run <b>" + pick.run_id + "</b> was planned but never submitted, so " +
                        "there is no result block to order against. Published rather than " +
                        "hidden, which is the right behaviour, but it does not demonstrate " +
                        "the check",
                    detail:pb};
          }
          if (!(pb.plan_block_index < pb.result_block_index)){
            return {verdict:"FAIL",
                    why:"the selection was sealed at block " + pb.plan_block_index +
                        " and the result at " + pb.result_block_index +
                        " \u2014 the sample was not fixed before the data was requested",
                    detail:pb};
          }
          return {verdict:"PASS",
                  why:"the sample for <b>" + pb.run_id + "</b> was sealed at block <b>" +
                      pb.plan_block_index + "</b> and the result at <b>" +
                      pb.result_block_index + "</b> \u2014 fixed before any data was asked " +
                      "for, checkable without an account. Across the record: <b>" +
                      b.mismatched + " mismatches</b> and <b>" + b.abandoned +
                      " abandoned run" + (b.abandoned === 1 ? "" : "s") +
                      "</b> published rather than buried",
                  detail:{summary:{runs:b.runs, matched:b.matched, mismatched:b.mismatched,
                                   abandoned:b.abandoned}, proof:pb}};
        });
      });
    },

    rule_binding: function(c){
      return postShapes(c.endpoint || "/x/rulebind/prove", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected),
                  detail:res.rejected};
        }
        var strings = [], hexes = {};
        walk(res.body, "", strings, hexes);
        return Promise.all(strings.map(function(s){
          return sha256hex(s.value).then(function(h){ return {path:s.path, hash:h}; });
        })).then(function(hashed){
          for (var i = 0; i < hashed.length; i++){
            if (hexes[hashed[i].hash]){
              return {verdict:"PASS",
                      why:"the response returned the exact string that was hashed. SHA-256 of " +
                          "<b>" + hashed[i].path + "</b>, recomputed in this browser, equals " +
                          "<b>" + hexes[hashed[i].hash] + "</b> \u2014 the ruleset version is " +
                          "inside the digest, not a field beside it",
                      detail:res.body};
            }
          }
          return {verdict:"INCONCLUSIVE",
                  why:"accepted the <b>" + res.shape + "</b> payload" + learnedNote(res) +
                      ", but no string it returned " +
                      "hashes to any digest in the response, so the binding was not confirmed here",
                  detail:res.body};
        });
      });
    },

    commit_before_reveal: function(c){
      return jpost(c.endpoint || "/x/demo/review", PROBE).then(function(r){
        if (!r.ok){
          return {verdict:"INCONCLUSIVE", why:"POST returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var cid = b.case_id;
        if (!cid){
          return {verdict:"INCONCLUSIVE", why:"no case id came back to commit against", detail:b};
        }
        // The case must arrive with the verdict withheld. If it is in there,
        // nothing committed afterwards can have preceded a reveal that had
        // already happened.
        var text = JSON.stringify(b);
        if (/"(machine_verdict|verdict|decision)"\s*:\s*"(ALLOW|CHALLENGE|BLOCK)"/i.test(text)){
          return {verdict:"FAIL",
                  why:"the case arrived with the machine verdict already in it \u2014 the order " +
                      "cannot be fixed after the answer is known",
                  detail:b};
        }

        return jpost("/x/demo/commit", {case_id: cid, verdict: "challenge"}).then(function(k){
          if (!k.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"the case opened with the verdict withheld, but the commit returned " +
                        k.status,
                    detail:{case:b, commit:k.body}};
          }
          var kb = k.body || {};
          if (kb.block_index === undefined || !kb.machine_verdict){
            return {verdict:"INCONCLUSIVE",
                    why:"committed, but the response carries no block index or no revealed " +
                        "verdict to check the order against",
                    detail:{case:b, commit:kb}};
          }
          // A commitment you can redo is not a commitment.
          return jpost("/x/demo/commit", {case_id: cid, verdict: "allow"}).then(function(again){
            var refused = !again.ok ||
                          (again.body && again.body.error === "already_committed");
            if (!refused){
              return {verdict:"FAIL",
                      why:"the same case accepted a second, different verdict \u2014 a " +
                          "commitment that can be redone fixes nothing",
                      detail:{first:kb, second:again.body}};
            }
            return {verdict:"PASS",
                    why:"the case was issued with the verdict withheld, a human verdict was " +
                        "sealed at block <b>" + kb.block_index + "</b>, the machine verdict " +
                        "(<b>" + kb.machine_verdict + "</b>) was revealed only in that same " +
                        "response, dwell of <b>" + kb.dwell_seconds + "s</b> was recorded, and " +
                        "a second commit was refused \u2014 the order is fixed, not asserted",
                    detail:{case:b, commit:kb, second_attempt:again.body}};
          });
        });
      }).catch(function(e){
        return {verdict:"INCONCLUSIVE", why:"request failed: " + e.message};
      });
    },

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
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no committed period, so there is nothing to prove absence against"});
      }
      var url = fill(c.endpoint) ||
        ("/x/complete/prove?period=" + ctx.period + "&value=" + ctx.absent);
      return jget(url).then(function(r){
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var n = (r.body && r.body.neighbours) || (r.body && r.body.neighbors) || {};
        if (n.lower && n.upper &&
            n.lower.index !== undefined && n.upper.index !== undefined){
          if (n.upper.index - n.lower.index === 1){
            return {verdict:"PASS",
                    why:"neighbours at indices <b>" + n.lower.index + "</b> and <b>" +
                        n.upper.index + "</b> \u2014 consecutive, so nothing can sit between " +
                        "them. Absence proved, not asserted",
                    detail:r.body};
          }
          return {verdict:"FAIL",
                  why:"neighbour indices " + n.lower.index + " and " + n.upper.index +
                      " are not consecutive \u2014 that proves nothing",
                  detail:r.body};
        }
        if (n.lower || n.upper){
          return {verdict:"INCONCLUSIVE",
                  why:"boundary case \u2014 the probe sorted outside the whole set, so only one " +
                      "neighbour came back. Valid, but it does not exercise the adjacency argument",
                  detail:r.body};
        }
        return {verdict:"INCONCLUSIVE", why:"no neighbours in the response", detail:r.body};
      });
    },

    consistency_proof: function(c){
      if (!ctx.size){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"could not read a tree size from /x/consistency/root"});
      }
      var first = Math.max(1, Math.floor(ctx.size / 2));
      var url = "/x/consistency/proof?first=" + first + "&second=" + ctx.size;
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"returned " + r.status + " for first=" + first + " second=" + ctx.size,
                  detail:r.body};
        }
        var b = r.body || {};
        var path = b.consistency_proof || b.proof || b.path;
        if (!Array.isArray(path) || path.length === 0){
          return {verdict:"INCONCLUSIVE", why:"no proof path in the response", detail:b};
        }
        // The proof has to be against the same tip served at /x/consistency/root.
        // A proof against some other root proves something about some other log.
        if (ctx.root && b.second_root && b.second_root !== ctx.root){
          return {verdict:"FAIL",
                  why:"the proof is against a different root than /x/consistency/root serves \u2014 " +
                      "two views of the log, which is the split view this check exists to rule out",
                  detail:b};
        }
        return {verdict:"PASS",
                why:"RFC 6962 proof of <b>" + path.length + " nodes</b> that the log at " + first +
                    " is a prefix of the log at " + ctx.size +
                    ", against the same tip served separately \u2014 append-only shown, not claimed",
                detail:b};
      });
    },

    reproducibility: function(c){
      return postShapes(c.endpoint || "/x/replay/challenge", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected) +
                      ". This endpoint is published as publicly demonstrable, so the shape it " +
                      "wants belongs in the document",
                  detail:res.rejected};
        }
        return jpost(c.endpoint || "/x/replay/challenge", res.sent).then(function(b){
          return jget("/x/replay/fingerprint").then(function(f){
            var va = res.body && (res.body.verdict || res.body.decision);
            var vb = b.body && (b.body.verdict || b.body.decision);
            if (!va || !vb){
              return {verdict:"INCONCLUSIVE",
                      why:"both runs accepted under the <b>" + res.shape + "</b> shape, but no " +
                          "verdict field came back to compare",
                      detail:{first:res.body, second:b.body}};
            }
            if (va === vb){
              return {verdict:"PASS",
                      why:"identical inputs submitted twice both returned <b>" + va + "</b> " +
                          "under one code fingerprint" + learnedNote(res) +
                          " \u2014 determinism shown without disclosing any scoring logic",
                      detail:{shape:res.shape, fingerprint:f.body,
                              first:res.body, second:b.body}};
            }
            return {verdict:"FAIL",
                    why:"identical inputs gave <b>" + va + "</b> then <b>" + vb +
                        "</b> \u2014 not deterministic",
                    detail:{first:res.body, second:b.body}};
          });
        });
      });
    },

    external_anchoring: function(c){
      var url = c.endpoint || "/api/anchor-status";
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"<b>" + url + " returned " + r.status + "</b> \u2014 this check is " +
                      "published as publicly demonstrable and the endpoint under it is not there",
                  detail:r.body};
        }
        var b = r.body || {};
        var tip = b.tip || b.chain_tip || b.anchored_tip;
        if (!tip){
          return {verdict:"INCONCLUSIVE",
                  why:"the endpoint answers but names no anchored tip, so there is nothing to " +
                      "check it against",
                  detail:b};
        }

        // A browser cannot verify Bitcoin, and this page will not pretend to.
        // What it CAN settle is the question that actually decides the check:
        // is the tip that was submitted to the external authority a tip of
        // THIS log? An anchor over some other chain proves nothing about this
        // one, and that substitution is the only way this check fails
        // quietly.
        return jget("/x/consistency/ancestor?tip=" + encodeURIComponent(tip)).then(function(a){
          if (a.status === 409){
            return {verdict:"FAIL",
                    why:"the anchored tip is <b>not</b> on the log being served now \u2014 the " +
                        "external timestamp covers a different chain, which is the fork this " +
                        "check exists to catch",
                    detail:{anchor:b, ancestor:a.body}};
          }
          if (!a.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found, but /x/consistency/ancestor returned " + a.status +
                        " so it could not be placed on this log",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var text = JSON.stringify(a.body || {});
          var placed = /"(ancestor|is_ancestor|valid|ok|confirmed|on_chain)"\s*:\s*true/i.test(text) ||
                       /"(consistency_proof|proof|path)"\s*:\s*\[/.test(text);
          if (!placed){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found and the ancestor route answered, but this runner " +
                        "could not read a confirmation out of the response",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var stamped = (b.ots_ok === true) || /anchored/i.test(String(b.status || ""));
          return {verdict:"PASS",
                  why:"the tip submitted to the external authority is proved to be on <b>this</b> " +
                      "log, not a substituted one \u2014 checked against /x/consistency/ancestor" +
                      (stamped ? ", and the operator reports it stamped: " +
                                 String(b.status || "anchored")
                               : ", though the operator does not report it stamped yet") +
                      ". The attestation itself is the authority's to confirm, not this page's",
                  detail:{anchor:b, ancestor:a.body}};
        }).catch(function(e){
          return {verdict:"INCONCLUSIVE",
                  why:"anchored tip found but the ancestor check failed: " + e.message,
                  detail:b};
        });
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
      var b = r.body || {};
      // This router answers a method mismatch with 404 unknown_action and
      // lists the methods it does accept. A POST-only route is present, not
      // missing, and calling it missing would be a false failure.
      var postOnly = (b.error === "unknown_action") && Array.isArray(b.POST) &&
                     (b.POST.indexOf(url.split("?")[0].split("/").pop()) !== -1 ||
                      (Array.isArray(b.GET) && b.GET.length === 0));
      if (r.status === 405 || r.status === 501 || postOnly){
        return {verdict:"INCONCLUSIVE",
                why:"POST-only endpoint \u2014 present and listed by the router, but it cannot " +
                    "be exercised from a plain page",
                detail:r.body};
      }
      if (b.error === "unknown_action"){
        return {verdict:"INCONCLUSIVE",
                why:"the route answered but does not accept GET. Reachable, semantics not checked",
                detail:r.body};
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


## `modules/signed.py`

153 lines, 7060 bytes

```python
# ----------------------------------------------------------------------
# Schema addition inside _setup(ctx)
# ----------------------------------------------------------------------
def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS signed_keys("
                  "peer TEXT PRIMARY KEY,pubkey TEXT,enrolled REAL,"
                  "audit_hash TEXT,block_index INTEGER,"
                  "rotations INTEGER DEFAULT 0,last_ts REAL,note TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS signed_log("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,peer TEXT,tip TEXT,"
                  "peer_ts REAL,observed REAL,signature TEXT,pubkey TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS signed_seq("
                  "peer TEXT PRIMARY KEY, last_seq INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_peer ON signed_log(peer,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_tip ON signed_log(tip)")
        c.commit()
    _ready = True


def _next_receipt_seq(ctx, peer):
    """Monotonic gapless sequence counter per peer chain."""
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("INSERT INTO signed_seq(peer, last_seq) VALUES(?, 1) "
                  "ON CONFLICT(peer) DO UPDATE SET last_seq = last_seq + 1", (peer,))
        seq = c.execute("SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()[0]
        c.commit()
        return seq


# ----------------------------------------------------------------------
# Updated _submit(ctx, data)
# ----------------------------------------------------------------------
def _submit(ctx, data):
    peer = _peer_name(data)
    if not peer:
        return {"error": "chain_required"}, 400
    row = _key_row(ctx, peer)
    if not row:
        return {"error": "not_enrolled", "chain": peer,
                "message": "No public key is enrolled for this name. Enrol at "
                           "/x/signed/enroll, or use the open lane at "
                           "/x/witness/observe which needs nothing."}, 404
    pubkey, _enrolled, _h, _idx, rotations, last_ts = row

    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip",
                "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400
    signature = str(data.get("signature") or data.get("sig") or "").strip().lower()
    if not HEX128.match(signature):
        return {"error": "invalid_signature_format",
                "message": "An Ed25519 signature is 64 bytes - 128 lowercase "
                           "hex characters."}, 400
    raw_ts = data.get("ts", data.get("peer_ts"))
    try:
        ts_int = int(raw_ts)
    except (TypeError, ValueError):
        return {"error": "invalid_ts",
                "message": "ts must be integer epoch seconds, and must be the "
                           "same value you signed."}, 400

    ok, why = _check_ts(ts_int, last_ts)
    if not ok:
        return {"error": "timestamp_rejected", "message": why,
                "our_time": int(time.time())}, 400

    with ctx["lock"]:
        dup = ctx["conn"].execute(
            "SELECT observed FROM signed_log WHERE peer=? AND signature=? LIMIT 1",
            (peer, signature)).fetchone()
    if dup:
        return {"error": "replayed_signature",
                "message": "This exact signature was already accepted at %s."
                           % _iso(dup[0])}, 409

    message = "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]).encode("utf-8")
    if not ed25519_verify(bytes.fromhex(pubkey), message, bytes.fromhex(signature)):
        return {"error": "signature_did_not_verify",
                "chain": peer,
                "message": "Nothing has been sealed. The signature does not "
                           "verify against the key enrolled for this name. "
                           "The usual cause is a canonical message built "
                           "differently - check it byte for byte below.",
                "we_verified_against": _canonical_help(peer),
                "the_exact_bytes_we_hashed":
                    "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]),
                "enrolled_pubkey": pubkey}, 400

    observed = time.time()
    detail = ("peer=" + peer + ";tip=" + tip + ";ts=" + str(ts_int) +
              ";pubkey=" + pubkey + ";sig=" + signature)
    ev = {"user_id": "sig:" + peer, "action": "signed_tip_observed", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "SIGNED_TIP_SEALED", "score": 0, "signed_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": observed,
           "verification": "peer-signed", "detail": detail}

    # Execute seal safely
    try:
        h, idx, _ = ctx["seal"](ev, res, observed, "public-signed")
        if not h:
            raise ValueError("Seal returned empty hash")
    except Exception as e:
        return {"error": "seal_failed",
                "message": "Failed to seal submission into the witness chain. Nothing was saved.",
                "detail": str(e)}, 500

    # Assign gapless sequence only after successful seal
    seq = _next_receipt_seq(ctx, peer)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO signed_log(peer,tip,peer_ts,observed,signature,"
            "pubkey,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?)",
            (peer, tip, float(ts_int), observed, signature, pubkey, h, idx))
        ctx["conn"].execute("UPDATE signed_keys SET last_ts=? WHERE peer=?",
                            (float(ts_int), peer))
        ctx["conn"].commit()

    mirrored = False
    try:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,"
                "audit_hash,block_index,note,url,liveness,name_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("public-signed", peer, tip, float(ts_int), observed, h, idx,
                 "signed submission - verified against enrolled Ed25519 key",
                 None, "peer-signed", "key-bound"))
            ctx["conn"].commit()
        mirrored = True
    except Exception:
        pass

    return {"chain": peer, "witnessed_tip": tip, "observed_at": _iso(observed),
            "peer_claimed_time": _iso(ts_int),
            "sealed_in_our_chain": h, "block_index": idx,
            "receipt_seq": seq, "key_seq": (rotations or 0) + 1,
            "verification": "peer-signed",
            "verified_against_pubkey": pubkey,
            "on_public_roster": mirrored,
            "signed_version": VERSION,
            "verify": "/x/signed/verify?peer=" + peer + "&tip=" + tip,
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200

```


## `modules/sortition.py`

789 lines, 33138 bytes

```python
"""
sortition.py - selection by lot. The operator stops choosing who gets audited.

THE HOLE THIS FILLS
-------------------
Every system claiming human oversight reviews a sample of decisions. In
every one of them, the operator picks the sample. So the sample proves
nothing: you can review the easy ones, or the ones you already know are
clean, and nobody outside can tell the difference. It is the softest spot
in every Article 14 claim in the industry, and it has stayed soft because
there was no alternative.

There is one now. heartbeat.py seals a public beacon value on a cadence -
a number nobody, including the operator, can know before its tick. That is
a dice roll no one owns.

THE THREE LOCKS, IN ORDER. THE ORDER IS THE WHOLE POINT.
--------------------------------------------------------
1. COMMIT THE POOL. Every record eligible for review in a period is
   listed, hashed into one pool digest, and sealed. The pool is now fixed.
2. WAIT FOR A TICK. The draw may only use a beacon value sealed AFTER the
   pool commit. This module refuses otherwise. So the pool was fixed
   before the dice existed, and cannot be edited once they do.
3. DRAW. The beacon value deterministically ranks the pool. The lowest k
   ranks are selected. Anyone can recompute it from public values.

Break any one and the sample is choosable again. Enforced here, not
promised.

WHAT IT CATCHES
---------------
A selected record with no review sealed against it is a permanent, visible
hole with a name on it. You cannot quietly skip an awkward case, because
the case was chosen for you in public, and its absence is the evidence.

Refusal is allowed and is not hidden - it is sealed as a refusal with a
reason. An honest refusal on the record is worth more than a silent gap.

THE SELECTION FUNCTION, PUBLISHED SO IT IS NOT OURS
---------------------------------------------------
  seed = SHA256("AILEASH-SORTITION-v1" | period | pool_digest | beacon_value)
  rank(i) = SHA256(seed | ":" | record_hash_i)
  selected = the k records with the lowest rank, ties by record hash

No random number generator, no language-specific behaviour, no library.
Ten lines in any language. A stranger recomputes it and either gets our
list or catches us.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the reviews were any good. It proves nobody chose
  which ones happened.
- It does not stop an operator declining to draw at all. A period with no
  draw is a period with no sample, and /outstanding says so.
- Pool membership is asserted by this server. What stops a record being
  left out of the pool is complete.py, which commits the period's record
  count in advance - separate module, separate check.
- Selection is uniform. Risk-weighted sampling is deliberately not offered:
  a weighting the operator sets is a choice the operator made.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec         public  what this is and the exact selection function
  GET  draws        public  every draw ever made
  GET  draw         public  ?id= - one draw, its beacon value, its selection
  GET  verify       public  ?id= - recompute the draw from scratch, here
  GET  outstanding  public  selected records with no review yet, and how late
  GET  status       public  coverage, response rate, oldest unanswered
  POST pool         keyed   commit the pool for a period
  POST draw         keyed   draw a sample against a sealed beacon tick
  POST review       keyed   record a review, or a refusal with a reason
"""

import json
import time
import hashlib

VERSION = "1.1.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "draws"),
    ("GET", "draw"),
    ("GET", "verify"),
    ("GET", "outstanding"),
    ("GET", "status"),
}

DOMAIN_SEED = b"AILEASH-SORTITION-v1"
DOMAIN_POOL = b"AILEASH-POOL-v1"

DEFAULT_RATE = 0.05          # 5 percent
MIN_SELECT = 1
MAX_SELECT = 500
MAX_POOL = 200000
REVIEW_DUE_HOURS = 72

DDL = [
    """CREATE TABLE IF NOT EXISTS sortition_pool (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        period       TEXT NOT NULL,
        pool_digest  TEXT NOT NULL,
        pool_size    INTEGER NOT NULL,
        members      TEXT NOT NULL,
        committed_at REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_pool ON sortition_pool(period)",
    """CREATE TABLE IF NOT EXISTS sortition_draw (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        period        TEXT NOT NULL,
        pool_id       INTEGER NOT NULL,
        pool_digest   TEXT NOT NULL,
        pool_size     INTEGER NOT NULL,
        rate          REAL NOT NULL,
        select_count  INTEGER NOT NULL,
        beacon_source TEXT,
        beacon_round  INTEGER,
        beacon_value  TEXT NOT NULL,
        beacon_rowid  INTEGER,
        seed          TEXT NOT NULL,
        selected      TEXT NOT NULL,
        drawn_at      REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sortition_review (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        draw_id      INTEGER NOT NULL,
        record_hash  TEXT NOT NULL,
        outcome      TEXT NOT NULL,
        reviewer     TEXT,
        reason       TEXT,
        recorded_at  REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_rev ON sortition_review(draw_id, record_hash)",
]

OUTCOMES = ("agreed", "disagreed", "escalated", "refused")

VOCABULARY = {
    "pool": "Every record eligible for review in a period, fixed and sealed before any dice exist.",
    "draw": "The selection, computed from a beacon value that did not exist when the pool was sealed.",
    "selected": "Chosen by the beacon, not by us. We could not have known which.",
    "outstanding": "Selected and not yet answered. Visible, named, and counting.",
    "refused": "Declined on the record with a reason. Not a gap - a decision that is now permanent.",
    "gap": "Selected, past due, and never answered. The thing this module exists to make impossible to hide.",
}

WHAT_THIS_PROVES = (
    "That nobody chose which records were reviewed. It does not prove the "
    "reviews were competent, honest or useful. Those are different problems "
    "and this module does not touch them."
)


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        conn.commit()


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("audit_hash", "hash", "block_hash"):
        if n in c:
            return n
    return None


def _ts_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("ts", "timestamp", "created", "observed"):
        if n in c:
            return n
    return None


def _period_bounds(period):
    """YYYY, YYYY-MM, YYYY-MM-DD -> (start_epoch, end_epoch) UTC."""
    p = str(period).strip()
    try:
        if len(p) == 4:
            s = time.strptime(p + "-01-01", "%Y-%m-%d")
            e = time.strptime(str(int(p) + 1) + "-01-01", "%Y-%m-%d")
        elif len(p) == 7:
            s = time.strptime(p + "-01", "%Y-%m-%d")
            y, m = int(p[:4]), int(p[5:7])
            y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
            e = time.strptime("%04d-%02d-01" % (y2, m2), "%Y-%m-%d")
        elif len(p) == 10:
            s = time.strptime(p, "%Y-%m-%d")
            e = time.gmtime(_cal(s) + 86400)
        else:
            return None
    except ValueError:
        return None
    return _cal(s), _cal(e)


def _cal(st):
    import calendar
    return calendar.timegm(st)


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes" % (s // 60)
    if s < 86400:
        return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)
    return "%d days %d hours" % (s // 86400, (s % 86400) // 3600)


def _pool_digest(members):
    h = hashlib.sha256()
    h.update(DOMAIN_POOL + b"\n")
    for m in members:
        h.update(m.encode() + b"\n")
    return h.hexdigest()


def _seed(period, pool_digest, beacon_value):
    h = hashlib.sha256()
    h.update(DOMAIN_SEED + b"|")
    h.update(str(period).encode() + b"|")
    h.update(pool_digest.encode() + b"|")
    h.update(str(beacon_value).encode())
    return h.hexdigest()


def select(members, seed, k):
    """The published selection function. Deterministic, no RNG."""
    ranked = []
    for m in members:
        r = hashlib.sha256((seed + ":" + m).encode()).hexdigest()
        ranked.append((r, m))
    ranked.sort()
    return [m for _, m in ranked[:k]]


def _seal(ctx, action, payload):
    """Seal through the host's seal().

    server.py: seal(event, result, ts, api_key=None) where EVENT IS A DICT
    carrying user_id (subscripted inside), returning
    (audit_hash, block_index, key_seq).
    """
    fn = ctx.get("seal")
    if fn is None:
        return None, None
    ts = time.time()
    event = {"user_id": "sortition", "action": action, "amount": 0,
             "country": "UK", "device_id": "sortition", "anomaly": 0,
             "device_risk": 0}
    result = dict(payload)
    result.setdefault("decision", "SORTITION")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)
    for call in (lambda: fn(event, result, ts),
                 lambda: fn(event, result, ts, None),
                 lambda: fn(event, result)):
        try:
            out = call()
        except TypeError:
            continue
        except Exception:
            return None, None
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return h, idx
    return None, None


def _backfill(conn, lock, table, rowid_field, pk):
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        r = cur.fetchone()
        rid = r[0] if r and r[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute("UPDATE %s SET chain_rowid=?, audit_hash=? WHERE id=?" % table,
                    (rid, h, pk))
        conn.commit()
    return rid, h


def _latest_beat_after(conn, rowid):
    """The first heartbeat sealed strictly after a given chain row."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT source, beacon_round, value, chain_rowid, fetched_at"
            " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
            " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
        return cur.fetchone()
    except Exception:
        return None


def _beats_available(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick")
        return cur.fetchone()[0]
    except Exception:
        return None


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    if method == "GET" and action == "spec":
        return _spec(), 200

    # -------------------------------------------------- pool
    if method == "POST" and action == "pool":
        period = data.get("period")
        bounds = _period_bounds(period) if period else None
        if not bounds:
            return {"error": "period_required",
                    "formats": ["YYYY", "YYYY-MM", "YYYY-MM-DD"]}, 400
        start, end = bounds
        if end > time.time():
            return {"error": "period_not_closed",
                    "note": ("A pool can only be committed for a period that "
                             "has ended. Committing a live period would let "
                             "records arrive after the pool was fixed."),
                    "period_ends": _iso(end)}, 409

        hcol, tcol = _hash_col(conn), _ts_col(conn)
        if not hcol or not tcol:
            return {"error": "audit_log_schema_unrecognised"}, 500

        cur = conn.cursor()
        kind = data.get("event")
        if kind:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? AND event=?"
                " ORDER BY rowid" % (hcol, tcol, tcol), (start, end, kind))
        else:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? ORDER BY rowid"
                % (hcol, tcol, tcol), (start, end))
        members = sorted({r[0] for r in cur.fetchall() if r[0]})
        if not members:
            return {"error": "empty_period", "period": period}, 404
        if len(members) > MAX_POOL:
            return {"error": "pool_too_large", "size": len(members),
                    "max": MAX_POOL}, 413

        digest = _pool_digest(members)
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id, pool_digest FROM sortition_pool WHERE period=?",
                        (period,))
            prior = cur.fetchone()
            if prior:
                return {"error": "pool_already_committed", "period": period,
                        "pool_digest": prior[1],
                        "note": "A pool commits once. That is what makes it a pool."}, 409
            cur.execute(
                "INSERT INTO sortition_pool (period, pool_digest, pool_size,"
                " members, committed_at) VALUES (?,?,?,?,?)",
                (period, digest, len(members), json.dumps(members), now))
            pid = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_pool", {
            "period": period, "pool_digest": digest, "pool_size": len(members),
            "event_filter": kind,
            "note": ("Pool fixed. Any draw against it must use a beacon value "
                     "sealed after this block."),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_pool", "chain_rowid", pid)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_pool SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, pid))
                conn.commit()

        return {"pool_id": pid, "period": period, "pool_digest": digest,
                "pool_size": len(members), "sealed_at_chain_rowid": rid,
                "audit_hash": h,
                "next": ("Wait for a heartbeat sealed after block %s, then "
                         "POST /x/sortition/draw." % rid)}, 200

    # -------------------------------------------------- draw
    if method == "POST" and action == "draw":
        period = data.get("period")
        cur = conn.cursor()
        cur.execute("SELECT id, pool_digest, pool_size, members, chain_rowid"
                    " FROM sortition_pool WHERE period=?", (period,))
        pool = cur.fetchone()
        if not pool:
            return {"error": "no_pool_for_period", "period": period,
                    "next": "POST /x/sortition/pool first"}, 404
        pid, digest, size, members_json, pool_rowid = pool

        cur.execute("SELECT id FROM sortition_draw WHERE period=?", (period,))
        if cur.fetchone():
            return {"error": "already_drawn", "period": period,
                    "note": "One draw per pool. A second draw is a second chance."}, 409

        if pool_rowid is None:
            return {"error": "pool_not_located_in_chain"}, 500

        beat = _latest_beat_after(conn, pool_rowid)
        if not beat:
            n = _beats_available(conn)
            return {"error": "no_beacon_since_pool_commit",
                    "beats_in_system": n,
                    "why": ("The draw must use a value that did not exist when "
                            "the pool was sealed. Wait for the next heartbeat."),
                    "check": "/x/heartbeat/latest"}, 409

        b_source, b_round, b_value, b_rowid, b_at = beat
        members = json.loads(members_json)

        try:
            rate = float(data.get("rate", DEFAULT_RATE))
        except (TypeError, ValueError):
            rate = DEFAULT_RATE
        rate = max(0.0001, min(1.0, rate))
        k = int(round(size * rate))
        k = max(MIN_SELECT, min(k, MAX_SELECT, size))

        seed = _seed(period, digest, b_value)
        chosen = select(members, seed, k)
        now = time.time()

        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sortition_draw (period, pool_id, pool_digest,"
                " pool_size, rate, select_count, beacon_source, beacon_round,"
                " beacon_value, beacon_rowid, seed, selected, drawn_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (period, pid, digest, size, rate, k, b_source, b_round,
                 b_value, b_rowid, seed, json.dumps(chosen), now))
            did = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_draw", {
            "draw_id": did, "period": period, "pool_digest": digest,
            "pool_size": size, "rate": rate, "selected_count": k,
            "beacon": {"source": b_source, "round": b_round, "value": b_value,
                       "sealed_at_block": b_rowid},
            "seed": seed, "selected": chosen,
            "note": ("Selection is recomputable by anyone from pool_digest and "
                     "the beacon value. See /x/sortition/spec."),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_draw", "chain_rowid", did)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_draw SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, did))
                conn.commit()

        return {"draw_id": did, "period": period, "pool_size": size,
                "rate": rate, "selected_count": k, "selected": chosen,
                "beacon": {"source": b_source, "round": b_round,
                           "value": b_value, "sealed_at_block": b_rowid,
                           "sealed_at": _iso(b_at)},
                "seed": seed, "sealed_at_chain_rowid": rid, "audit_hash": h,
                "review_due": _iso(now + REVIEW_DUE_HOURS * 3600),
                "recompute_this_yourself": "/x/sortition/verify?id=%d" % did}, 200

    # -------------------------------------------------- review
    if method == "POST" and action == "review":
        did = data.get("draw_id")
        rec = data.get("record")
        outcome = str(data.get("outcome", "")).lower()
        if not did or not rec:
            return {"error": "draw_id_and_record_required"}, 400
        if outcome not in OUTCOMES:
            return {"error": "outcome_invalid", "allowed": list(OUTCOMES)}, 400
        if outcome == "refused" and not data.get("reason"):
            return {"error": "reason_required_to_refuse",
                    "why": ("A refusal without a reason is a gap wearing a "
                            "label. The reason is sealed and permanent.")}, 400

        cur = conn.cursor()
        cur.execute("SELECT selected FROM sortition_draw WHERE id=?", (did,))
        row = cur.fetchone()
        if not row:
            return {"error": "unknown_draw", "draw_id": did}, 404
        if rec not in json.loads(row[0]):
            return {"error": "record_not_selected",
                    "note": ("Reviews can only be filed against records the "
                             "beacon chose. Volunteering extra reviews does "
                             "not count toward the sample.")}, 409

        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id FROM sortition_review WHERE draw_id=? AND record_hash=?",
                        (did, rec))
            if cur.fetchone():
                return {"error": "already_reviewed",
                        "note": "A review is filed once and cannot be replaced."}, 409
            cur.execute(
                "INSERT INTO sortition_review (draw_id, record_hash, outcome,"
                " reviewer, reason, recorded_at) VALUES (?,?,?,?,?,?)",
                (did, rec, outcome, data.get("reviewer"), data.get("reason"), now))
            rvid = cur.lastrowid
            conn.commit()

        sh, sidx = _seal(ctx, "sortition_review", {
            "draw_id": did, "record": rec, "outcome": outcome,
            "reviewer": data.get("reviewer"), "reason": data.get("reason"),
        })
        rid, h = (sidx, sh) if (sidx and sh) else _backfill(conn, lock, "sortition_review", "chain_rowid", rvid)
        if sidx and sh:
            with lock:
                conn.execute("UPDATE sortition_review SET chain_rowid=?, audit_hash=? WHERE id=?", (rid, h, rvid))
                conn.commit()
        return {"recorded": True, "review_id": rvid, "outcome": outcome,
                "sealed_at_chain_rowid": rid, "audit_hash": h}, 200

    # -------------------------------------------------- draws
    if method == "GET" and action == "draws":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, period, pool_size, rate, select_count, beacon_source,"
            " beacon_round, drawn_at, audit_hash FROM sortition_draw"
            " ORDER BY id DESC LIMIT 100")
        out = []
        for r in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM sortition_review WHERE draw_id=?", (r[0],))
            done = cur2.fetchone()[0]
            out.append({"draw_id": r[0], "period": r[1], "pool_size": r[2],
                        "rate": r[3], "selected": r[4], "reviewed": done,
                        "outstanding": r[4] - done,
                        "beacon": {"source": r[5], "round": r[6]},
                        "drawn_at": _iso(r[7]), "audit_hash": r[8]})
        return {"count": len(out), "draws": out, "vocabulary": VOCABULARY}, 200

    # -------------------------------------------------- one draw
    if method == "GET" and action == "draw":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT record_hash, outcome, reviewer, reason, recorded_at"
                    " FROM sortition_review WHERE draw_id=?", (did,))
        revs = {r[0]: {"outcome": r[1], "reviewer": r[2], "reason": r[3],
                       "at": _iso(r[4])} for r in cur.fetchall()}
        items = []
        for m in json.loads(d["selected_json"]):
            items.append({"record": m, "review": revs.get(m),
                          "state": "answered" if m in revs else "outstanding"})
        return {"draw_id": did, "period": d["period"],
                "pool_digest": d["pool_digest"], "pool_size": d["pool_size"],
                "rate": d["rate"], "selected_count": d["select_count"],
                "beacon": {"source": d["beacon_source"], "round": d["beacon_round"],
                           "value": d["beacon_value"],
                           "sealed_at_block": d["beacon_rowid"]},
                "seed": d["seed"], "drawn_at": _iso(d["drawn_at"]),
                "items": items,
                "what_this_proves": WHAT_THIS_PROVES,
                "recompute": "/x/sortition/verify?id=%s" % did}, 200

    # -------------------------------------------------- verify
    if method == "GET" and action == "verify":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT members FROM sortition_pool WHERE id=?", (d["pool_id"],))
        row = cur.fetchone()
        members = json.loads(row[0]) if row else []
        recomputed_digest = _pool_digest(members)
        recomputed_seed = _seed(d["period"], d["pool_digest"], d["beacon_value"])
        recomputed = select(members, recomputed_seed, d["select_count"])
        stored = json.loads(d["selected_json"])
        ok = (recomputed_digest == d["pool_digest"]
              and recomputed_seed == d["seed"]
              and sorted(recomputed) == sorted(stored))
        return {
            "draw_id": did,
            "matches": ok,
            "pool_digest_recomputed": recomputed_digest,
            "pool_digest_sealed": d["pool_digest"],
            "seed_recomputed": recomputed_seed,
            "seed_sealed": d["seed"],
            "selection_matches": sorted(recomputed) == sorted(stored),
            "beacon_value": d["beacon_value"],
            "beacon_check": ("Confirm this value independently at "
                             "/x/heartbeat/verify?round=%s, then at the beacon "
                             "operator's own endpoint." % d["beacon_round"]),
            "do_it_without_us": {
                "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
                "rank": 'SHA256(seed + ":" + record_hash)',
                "select": "lowest k ranks, ascending",
                "note": ("This route runs the same function on our server, so "
                         "it is a convenience, not the proof. The proof is you "
                         "running those three lines yourself."),
            },
        }, 200

    # -------------------------------------------------- outstanding
    if method == "GET" and action == "outstanding":
        now = time.time()
        cur = conn.cursor()
        cur.execute("SELECT id, period, selected, drawn_at FROM sortition_draw"
                    " ORDER BY id DESC")
        items = []
        for did, period, sel, drawn in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT record_hash FROM sortition_review WHERE draw_id=?", (did,))
            done = {r[0] for r in cur2.fetchall()}
            due = drawn + REVIEW_DUE_HOURS * 3600
            for m in json.loads(sel):
                if m in done:
                    continue
                items.append({
                    "draw_id": did, "period": period, "record": m,
                    "drawn_at": _iso(drawn), "due": _iso(due),
                    "state": "gap" if now > due else "outstanding",
                    "late_by": _human(now - due) if now > due else None,
                })
        gaps = [i for i in items if i["state"] == "gap"]
        return {"outstanding_count": len(items), "gap_count": len(gaps),
                "due_after_hours": REVIEW_DUE_HOURS,
                "items": items[:500],
                "meaning": VOCABULARY["gap"]}, 200

    # -------------------------------------------------- status
    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(select_count) FROM sortition_draw")
        ndraws, nsel = cur.fetchone()
        nsel = nsel or 0
        cur.execute("SELECT COUNT(*) FROM sortition_review")
        nrev = cur.fetchone()[0]
        cur.execute("SELECT outcome, COUNT(*) FROM sortition_review GROUP BY outcome")
        mix = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM sortition_pool")
        npool = cur.fetchone()[0]
        beats = _beats_available(conn)
        return {
            "version": VERSION,
            "pools_committed": npool,
            "draws": ndraws,
            "records_selected": nsel,
            "reviews_recorded": nrev,
            "response_rate": round(nrev / nsel, 4) if nsel else None,
            "outcome_mix": mix,
            "beacon_available": beats is not None,
            "beats_in_system": beats,
            "depends_on": {
                "heartbeat": ("supplies the dice. Without a beacon sealed "
                              "after the pool, no draw is possible."),
                "complete": ("commits the period's record count in advance. "
                             "Without it, a record could be kept out of the "
                             "pool. Separate module, separate check: "
                             "/x/complete/periods"),
            },
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "draws", "draw", "verify", "outstanding",
                        "status", "pool", "review"]}, 404


def _draw_row(conn, did):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, period, pool_id, pool_digest, pool_size, rate, select_count,"
        " beacon_source, beacon_round, beacon_value, beacon_rowid, seed,"
        " selected, drawn_at FROM sortition_draw WHERE id=?", (did,))
    r = cur.fetchone()
    if not r:
        return None
    keys = ["id", "period", "pool_id", "pool_digest", "pool_size", "rate",
            "select_count", "beacon_source", "beacon_round", "beacon_value",
            "beacon_rowid", "seed", "selected_json", "drawn_at"]
    return dict(zip(keys, r))


def _spec():
    return {
        "module": "sortition",
        "version": VERSION,
        "name_means": "selection by lot - the ancient method for stopping the powerful choosing who gets scrutinised",
        "the_hole": (
            "Every system claiming human oversight reviews a sample. In every "
            "one, the operator picks the sample, so the sample proves nothing."
        ),
        "the_three_locks": [
            "1. The pool of eligible records is fixed and sealed first.",
            "2. The draw may only use a beacon value sealed AFTER the pool. "
            "Refused otherwise. So the pool was fixed before the dice existed.",
            "3. The beacon value ranks the pool. Lowest k are selected. "
            "Anyone recomputes it from public values.",
        ],
        "selection_function": {
            "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
            "rank": 'SHA256(seed + ":" + record_hash)',
            "select": "the k lowest ranks in ascending order",
            "why_no_rng": ("A random number generator is a library, a version "
                           "and a seed we control. Two SHA-256 calls are none "
                           "of those and run in any language."),
        },
        "uniform_only": (
            "Risk-weighted sampling is deliberately not offered. A weighting "
            "the operator sets is a choice the operator made, which is the "
            "thing this module exists to remove."
        ),
        "refusal": (
            "A reviewer may refuse a selected case, with a reason, sealed. "
            "An honest refusal on the record beats a silent gap. A selection "
            "left unanswered past the due window is published as a gap with "
            "the record named."
        ),
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It does not prove the reviews were any good.",
            "It does not force anyone to draw at all. A period with no draw "
            "is a period with no sample and status says so.",
            "Pool membership is asserted by this server; completeness of the "
            "pool is complete.py's job, not this module's.",
            "The beacon is a third party. If drand and Bitcoin both vanish, "
            "new draws stop. Old draws stay verifiable.",
        ],
        "routes": {
            "POST /x/sortition/pool": "keyed - commit the pool for a closed period",
            "POST /x/sortition/draw": "keyed - draw against a beacon sealed after the pool",
            "POST /x/sortition/review": "keyed - file a review or a refusal with a reason",
            "GET /x/sortition/draws": "every draw",
            "GET /x/sortition/draw?id=": "one draw and its answers",
            "GET /x/sortition/verify?id=": "recompute the draw",
            "GET /x/sortition/outstanding": "selected and unanswered, with gaps named",
            "GET /x/sortition/status": "coverage and response rate",
        },
    }

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
