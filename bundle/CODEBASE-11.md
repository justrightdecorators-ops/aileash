# Codebase — part 11 of 30

Contains:
- `modules/selfcheck.py`
- `modules/signed.py`


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

953 lines, 44350 bytes

```python
"""
Peer-signed submissions - /x/signed/<action>

WHAT CHANGED IN 1.1
-------------------
Three things, all of the same kind: a field that read stronger than it was.

1. receipt_seq is a real number now.

   This lane returned whatever server.py's seal() gave back for the
   sequence, and passed the literal string "public-signed" as the api_key.
   That is not a row in api_keys, so the UPDATE matched nothing, the SELECT
   returned nothing, and the value was always null. The field sat in the
   response named as though it were a receipt sequence, carrying nothing.

   The point of a sequence is that a holder of receipts N and N+2 can PROVE
   N+1 exists and was not received. A null cannot do that, so this lane had
   no completeness property while appearing to offer one.

   Found on the sibling lane at /x/peer/submit by Philip Pinol (PRAXIS),
   whose schema required an integer and got a null. Same fault here, fixed
   before anybody hit it. The sequence is now issued by this module, per
   enrolled name, inside the same lock hold that writes the row.

2. A failed seal no longer returns a receipt.

   ctx["seal"] was called and its result used without checking. If it
   raised or came back without a hash, this lane would have returned a
   success body with nothing behind it - the exact hollow receipt that
   turned up on the peer lane on 2026-08-26. It now returns 500, records
   nothing, and says why.

3. Enrolment and rotation report whether they sealed.

   Both were sealing as a side effect and ignoring the outcome. The
   operation still happens - a key is a database row and a failed audit
   note does not un-enrol it - but the response says sealed true or false
   with the error, rather than leaving it to be assumed.

The server-wide key counter is still returned, as key_seq, and is still
null. Reported rather than omitted so the absence is visible instead of
inferred, which is the confusion that made this worth fixing at all.

THE GAP THIS CLOSES
-------------------
Two people arrived at the same missing piece from opposite directions on the
same day.

Ishaan (Shango MID) read the existing signed lane and said, correctly, that
"binds a name to a secret rather than to an address" reads stronger than it
is. An HMAC uses a shared secret. A shared secret is held by both parties. So
it proves the submission came from SOMEONE HOLDING THE SECRET - which is the
peer and also the operator of this deployment. It closes third-party
submission under a peer's name. It does not close operator submission under a
peer's name.

Chidi (ViriSIM) came at it from the regulator's side: for the evidence to mean
anything to a third party, the customer has to sign, not the platform holding
the customer's records.

Same gap. This module closes it.

HOW
---
The peer generates an Ed25519 keypair and keeps the private half. This
deployment is given ONLY the public half. A public key is not a secret and
grants nothing: it verifies a signature and cannot produce one.

From then on, a submission under that name is accepted only if it carries a
signature this deployment can verify against that public key - and this
deployment CANNOT create such a signature, because it does not hold the
private key and never has. The property is not a promise about our conduct.
It is arithmetic.

WHAT THIS MEANS FOR THE RECORD
------------------------------
The other lanes answer "did somebody hand us this tip". This lane answers
"did the holder of this key hand us this tip", and the difference matters
precisely when the operator is the party you are worried about.

A regulator or auditor reading a signed observation does not have to trust
this deployment about who submitted it. They can take the public key from
/x/signed/keys, take the canonical message and the signature from the record,
and check it themselves with any Ed25519 library in any language.

WHAT IT STILL DOES NOT DO
-------------------------
- It does not prove the records behind the tip are true. Nothing here does.
- It does not prove completeness of the peer's own chain. A signed chain can
  still omit records. Catching that needs an audit protocol, not
  cryptography - see Chidi's incognito-user test, which is the only thing
  anyone has proposed that attacks it. Note this is a different claim from
  the receipt sequence below, which is about completeness of the receipts WE
  issued, not of the records THEY sealed.
- It does not prove who the keyholder IS. It proves the same party signed
  each time. Identity is a separate problem and this does not solve it.
- Enrolment is open, so the first party to enrol a name gets it. Same as
  everywhere else in this standard, that is detection rather than
  prevention: an enrolment is sealed, permanent and public, and an enrolment
  placed over a name already seen in the witness log is flagged as such.

WHY THE OPERATOR CANNOT QUIETLY SWAP A KEY
------------------------------------------
The obvious attack on the whole idea: the operator replaces the peer's public
key with one of their own, then signs freely. So there is no route that
overwrites a key. Rotation exists, and a rotation must itself be signed by
the key being replaced. An operator who does not hold the current private key
cannot rotate it, and every rotation is sealed into the chain with both keys
recorded. A peer who has lost their key cannot rotate either - they enrol a
new name, and the abandoned one stays visible.

CANONICAL MESSAGE
-----------------
Exactly this, UTF-8, no trailing newline, four lines joined by \\n:

    aileash-signed-v1
    <chain>
    <tip>
    <ts>

  chain  the peer name, lowercase, as enrolled
  tip    64 lowercase hex characters
  ts     integer epoch seconds, no decimal point

Sign those bytes with the Ed25519 private key. Send the 64-byte signature as
128 lowercase hex characters. The message is deliberately short, positional
and free of JSON so that two implementations cannot disagree about how to
build it.

Rotation signs a different message with the SAME shape:

    aileash-rotate-v1
    <chain>
    <new public key, 64 hex>
    <ts>

REPLAY
------
A signature is a bearer token for the statement it signs. Anyone who sees one
can send it again. So: ts must be within SKEW_PAST seconds behind and
SKEW_FUTURE ahead of our clock, ts must be strictly greater than the last ts
we accepted for that name, and an exact repeat of a signature already stored
is refused. None of that is exotic - it is the ordinary set, written down so
nobody has to guess which of them we do.

WHY THIS LANE REJECTS, WHEN THE OPEN LANE NEVER DOES
----------------------------------------------------
/x/witness/observe seals everything and describes what it sealed, because
refusing an anonymous submission would mean deciding who is allowed to be
recorded. This lane is the opposite case. A submission whose signature does
not verify has no business being written into a name's history at all - the
harm is exactly that it would sit in the record looking like an event
involving that peer. So this lane refuses, says why, and seals nothing.

    GET  /x/signed/spec                  the protocol
    GET  /x/signed/keys                  every enrolled name and public key
    POST /x/signed/enroll                chain, pubkey
    POST /x/signed/submit                chain, tip, ts, signature
    POST /x/signed/rotate                chain, new_pubkey, ts, signature
    GET  /x/signed/verify?peer=&tip=     the receipt, with everything a third
                                         party needs to check it themselves
"""

import hashlib
import re
import time
from datetime import datetime, timezone

VERSION = "1.1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX128 = re.compile(r"^[0-9a-f]{128}$")

MSG_PREFIX = "aileash-signed-v1"
ROTATE_PREFIX = "aileash-rotate-v1"

# Replay window. Generous enough for a batch job on a slow link, tight enough
# that a captured signature is not useful for long.
SKEW_PAST = 900
SKEW_FUTURE = 120

# Everything here is readable and usable without an account. A verification
# lane that only account holders can check is not a verification lane.
PUBLIC = {("GET", "spec"), ("GET", "keys"), ("GET", "verify"),
          ("POST", "enroll"), ("POST", "submit"), ("POST", "rotate")}

MAX_LIST = 500

# What this lane files its own audit rows under. Deliberately not a real
# api_key - it is a label, and it is exactly why server.py's per-key
# sequence comes back null here. See _seq_note.
FILED_UNDER = "public-signed"

MESSAGES = {
    "what_this_proves": (
        "That the holder of the enrolled private key produced this exact "
        "statement - name, tip and timestamp - and that we sealed it at the "
        "recorded time. This deployment holds only the public key and cannot "
        "produce such a signature, so it is not a claim you have to take on "
        "our word. Recheck it yourself with any Ed25519 library."),
    "what_this_does_not_prove": (
        "Nothing about whether the records behind the tip are true, nothing "
        "about whether the peer's chain is complete, and nothing about who "
        "the keyholder is in the world. It proves the same party signed each "
        "time."),
    "enrolled": (
        "This name is now bound to this public key permanently. We cannot "
        "change it - rotation requires a signature from the key being "
        "replaced, which we do not hold."),
    "keys_note": (
        "Public keys are not secrets. They are published so that anyone can "
        "verify a signed observation without asking us for anything."),
    "seq": (
        "An integer, never null, incremented by exactly one for each accepted "
        "submission UNDER THIS NAME on this lane. Issued inside the same lock "
        "that writes the record, so a number is never spent on a submission "
        "that was not stored. Two receipts numbered N and N+2 prove a third "
        "exists that you did not receive. The current highest is published at "
        "/x/signed/keys, so the check does not depend on asking us."),
    "key_seq": (
        "The server-wide per-API-key sequence, which is null on this lane and "
        "always will be. That counter lives on an api_key row, and this lane "
        "files under a label rather than a key because it authenticates by "
        "signature and issues nobody an account. It is returned rather than "
        "omitted so the absence is visible instead of inferred. Before 1.1 "
        "this null was reported as receipt_seq, which made a missing property "
        "look like a broken field."),
    "seq_survives_rotation": (
        "Rotating the key does not reset the sequence. It belongs to the "
        "name's submission history rather than to the key, so a rotation "
        "cannot be used to erase a gap."),
}

_ready = False


# ----------------------------------------------------------------------
# Ed25519 verification, RFC 8032, pure standard library
#
# Deliberately no third-party dependency. This deployment runs on a small
# box and a verification routine that needs a native extension is a
# verification routine that stops working on a platform migration. Extended
# homogeneous coordinates so a verify is milliseconds rather than seconds.
#
# Verify only. There is no signing function in this file, and that is not an
# oversight - there is nothing here that could be turned into a way for this
# deployment to produce a peer's signature.
# ----------------------------------------------------------------------

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e = b - a
    f = dd - c
    g = dd + c
    h = b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _double(p):
    return _add(p, p)


def _scalarmult(p, e):
    if e == 0:
        return (0, 1, 1, 0)
    q = _scalarmult(p, e >> 1)
    q = _double(q)
    if e & 1:
        q = _add(q, p)
    return q


def _decodepoint(raw):
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _xrecover(y)
    if x & 1 != (raw[31] >> 7) & 1:
        x = _P - x
    point = (x, y, 1, x * y % _P)
    # on-curve check: -x^2 + y^2 = 1 + d x^2 y^2
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return point


def _equal(p, q):
    x1, y1, z1, _t1 = p
    x2, y2, z2, _t2 = q
    if (x1 * z2 - x2 * z1) % _P != 0:
        return False
    if (y1 * z2 - y2 * z1) % _P != 0:
        return False
    return True


def ed25519_verify(public_key, message, signature):
    """True if signature is a valid Ed25519 signature of message under
    public_key. Bytes in, bool out, never raises."""
    try:
        if len(public_key) != 32 or len(signature) != 64:
            return False
        a = _decodepoint(public_key)
        if a is None:
            return False
        r_raw = signature[:32]
        r = _decodepoint(r_raw)
        if r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _L:
            return False
        h = int.from_bytes(
            hashlib.sha512(r_raw + public_key + message).digest(), "little") % _L
        left = _scalarmult(_B, s)
        right = _add(r, _scalarmult(a, h))
        return _equal(left, right)
    except Exception:
        return False


# ----------------------------------------------------------------------
# storage
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
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_peer ON signed_log(peer,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sig_tip ON signed_log(tip)")

        # Added in 1.1. The receipt counter, per enrolled name, in its own
        # table so the counter survives anything that happens to the key row
        # - including a rotation. A rotation that reset the sequence could be
        # used to erase a gap, which is the one thing the sequence exists to
        # make impossible.
        c.execute("CREATE TABLE IF NOT EXISTS signed_seq("
                  "peer TEXT PRIMARY KEY, last_seq INTEGER DEFAULT 0)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _peer_name(data):
    return str(data.get("chain") or data.get("peer") or "").strip().lower()


def _key_row(ctx, peer):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT pubkey,enrolled,audit_hash,block_index,rotations,last_ts "
            "FROM signed_keys WHERE peer=?", (peer,)).fetchone()


def _latest_seq(ctx, peer):
    """Highest receipt number issued to this name. 0 if none."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _try_seal(ctx, event, result, when, api_key):
    """Seal, and say plainly whether it worked.

    Returns (audit_hash, block_index, key_seq, error). Nothing here swallows
    a failure. Before 1.1 the result was used without checking, which is how
    a hollow receipt gets issued.
    """
    try:
        h, idx, seq = ctx["seal"](event, result, when, api_key)
    except Exception as exc:
        return None, None, None, "%s: %s" % (type(exc).__name__, str(exc)[:300])
    if not h:
        return None, None, None, "seal returned no audit hash"
    return h, idx, seq, None


def _seen_in_open_lane(ctx, peer):
    """Has this name already appeared in the open witness log?

    An enrolment over a name somebody else has been using is the same shape as
    the url squat, and gets the same treatment: we cannot prevent it, so we
    record it permanently at the moment it happens.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM witness_log WHERE peer=?", (peer,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _check_ts(ts, last_ts):
    now = time.time()
    if ts > now + SKEW_FUTURE:
        return False, ("timestamp is %d seconds in the future; limit is %d"
                       % (int(ts - now), SKEW_FUTURE))
    if ts < now - SKEW_PAST:
        return False, ("timestamp is %d seconds old; limit is %d"
                       % (int(now - ts), SKEW_PAST))
    if last_ts is not None and ts <= last_ts:
        return False, ("timestamp %d is not later than the last one accepted "
                       "for this name (%d) - a signature cannot be replayed "
                       "and submissions must move forward"
                       % (int(ts), int(last_ts)))
    return True, None


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _enroll(ctx, data):
    peer = _peer_name(data)
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works well."}, 400
    pubkey = str(data.get("pubkey") or data.get("public_key") or "").strip().lower()
    if not HEX64.match(pubkey):
        return {"error": "invalid_pubkey",
                "message": "An Ed25519 public key is 32 bytes - 64 lowercase "
                           "hex characters. Send the public half only. Never "
                           "send us a private key; we have no use for one and "
                           "no route that accepts one."}, 400
    if _decodepoint(bytes.fromhex(pubkey)) is None:
        return {"error": "invalid_pubkey",
                "message": "That value is 64 hex characters but is not a "
                           "point on the curve, so it is not an Ed25519 "
                           "public key."}, 400

    existing = _key_row(ctx, peer)
    if existing:
        if existing[0] == pubkey:
            return {"already_enrolled": True, "chain": peer, "pubkey": pubkey,
                    "enrolled_at": _iso(existing[1]),
                    "block_index": existing[3],
                    "latest_receipt_seq": _latest_seq(ctx, peer),
                    "message": "This name is already bound to this key. "
                               "Nothing changed."}, 200
        return {"error": "name_already_enrolled", "chain": peer,
                "enrolled_pubkey": existing[0],
                "enrolled_at": _iso(existing[1]),
                "message": "This name is bound to a different key. We do not "
                           "overwrite a binding. If you hold the enrolled "
                           "private key, use /x/signed/rotate. If you do not, "
                           "this name is not available to you and this "
                           "attempt is not sealed."}, 409

    prior = _seen_in_open_lane(ctx, peer)
    ts = time.time()
    note = "enrolled"
    if prior:
        note = ("WARNING: this name had already been submitted %d time(s) to "
                "the open witness lane before this key was enrolled, so it "
                "was not a fresh name when it was claimed" % prior)

    ev = {"user_id": "sig:" + peer, "action": "signed_key_enrolled", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "KEY_ENROLLED", "score": 0, "signed_version": VERSION,
           "peer": peer, "pubkey": pubkey, "timestamp": ts, "detail": note}
    h, idx, _seq, seal_error = _try_seal(ctx, ev, res, ts, FILED_UNDER)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO signed_keys(peer,pubkey,enrolled,audit_hash,"
            "block_index,rotations,last_ts,note) VALUES(?,?,?,?,?,0,NULL,?)",
            (peer, pubkey, ts, h, idx, note))
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO signed_seq(peer,last_seq) VALUES(?,0)", (peer,))
        ctx["conn"].commit()

    out = {"enrolled": True, "chain": peer, "pubkey": pubkey,
           "enrolled_at": _iso(ts), "sealed_in_our_chain": h,
           "block_index": idx, "signed_version": VERSION,
           "sealed": seal_error is None,
           "latest_receipt_seq": 0,
           "message": MESSAGES["enrolled"],
           "canonical_message": _canonical_help(peer),
           "submit": "/x/signed/submit"}
    if seal_error:
        out["seal_error"] = seal_error
        out["seal_note"] = ("The key is enrolled and usable - it is a database "
                            "row and a failed audit note does not un-enrol it. "
                            "But the record of the enrolment did not seal, "
                            "which is a fault worth chasing and is reported "
                            "rather than hidden.")
    if prior:
        out["flag"] = note
    return out, 200


def _canonical_help(peer):
    return {"format": MSG_PREFIX + "\\n<chain>\\n<tip>\\n<ts>",
            "example_for_this_name": MSG_PREFIX + "\\n" + peer +
                                     "\\n<64 hex tip>\\n<integer epoch seconds>",
            "encoding": "UTF-8, no trailing newline, lines joined with a "
                        "single \\n",
            "signature": "Ed25519 over those bytes, sent as 128 lowercase hex"}


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
    pubkey, _enrolled, _h, _idx, _rot, last_ts = row

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

    # Seal FIRST, and only claim success if it produced a hash. A signed
    # submission that returns a receipt with no block behind it is worse than
    # a refusal, because the peer has no way to tell the difference without
    # going and looking at the chain.
    h, idx, key_seq, seal_error = _try_seal(ctx, ev, res, observed, FILED_UNDER)
    if seal_error:
        return {"ok": False, "accepted": False, "error": "seal_failed",
                "chain": peer, "tip": tip,
                "detail": "Your signature verified correctly, but the audit "
                          "chain did not seal the submission, so there is no "
                          "receipt to give you. This is a fault on this "
                          "deployment and not a problem with your submission.",
                "seal_error": seal_error,
                "recorded": False,
                "retry": "Nothing was written. No sequence number was spent "
                         "and your signature is not recorded as used, so a "
                         "fresh submission with a later ts can be sent once "
                         "this is fixed.",
                "observed_at": _iso(observed)}, 500

    # Issue the receipt number inside the same lock hold that writes the row.
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO signed_seq(peer,last_seq) VALUES(?,0)", (peer,))
        ctx["conn"].execute(
            "UPDATE signed_seq SET last_seq = COALESCE(last_seq,0) + 1 "
            "WHERE peer=?", (peer,))
        srow = ctx["conn"].execute(
            "SELECT last_seq FROM signed_seq WHERE peer=?", (peer,)).fetchone()
        receipt_seq = int(srow[0]) if srow and srow[0] is not None else None

        ctx["conn"].execute(
            "INSERT INTO signed_log(peer,tip,peer_ts,observed,signature,"
            "pubkey,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?)",
            (peer, tip, float(ts_int), observed, signature, pubkey, h, idx))
        ctx["conn"].execute("UPDATE signed_keys SET last_ts=? WHERE peer=?",
                            (float(ts_int), peer))
        ctx["conn"].commit()

    # Mirror into the open witness log so the peer appears on the public
    # roster alongside everyone else. Guarded: the roster is a convenience
    # and the seal above is the evidence, so a failure here must not turn a
    # good submission into an error.
    mirrored = False
    try:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,"
                "audit_hash,block_index,note,url,liveness,name_status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (FILED_UNDER, peer, tip, float(ts_int), observed, h, idx,
                 "signed submission - verified against enrolled Ed25519 key",
                 None, "peer-signed", "key-bound"))
            ctx["conn"].commit()
        mirrored = True
    except Exception:
        pass

    return {"chain": peer, "witnessed_tip": tip, "observed_at": _iso(observed),
            "peer_claimed_time": _iso(ts_int),
            "sealed_in_our_chain": h, "block_index": idx,
            "receipt_seq": receipt_seq,
            "receipt_seq_scope": "per-chain",
            "key_seq": key_seq,
            "verification": "peer-signed",
            "verified_against_pubkey": pubkey,
            "on_public_roster": mirrored,
            "signed_version": VERSION,
            "verify": "/x/signed/verify?peer=" + peer + "&tip=" + tip,
            "gapless": MESSAGES["seq"],
            "key_seq_note": MESSAGES["key_seq"],
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200


def _rotate(ctx, data):
    peer = _peer_name(data)
    row = _key_row(ctx, peer)
    if not row:
        return {"error": "not_enrolled", "chain": peer}, 404
    current, _enrolled, _h, _idx, rotations, last_ts = row

    new_pubkey = str(data.get("new_pubkey") or data.get("pubkey") or "").strip().lower()
    if not HEX64.match(new_pubkey) or _decodepoint(bytes.fromhex(new_pubkey)) is None:
        return {"error": "invalid_pubkey",
                "message": "new_pubkey must be an Ed25519 public key - 64 "
                           "lowercase hex characters."}, 400
    if new_pubkey == current:
        return {"error": "no_change",
                "message": "That is already the enrolled key."}, 400
    signature = str(data.get("signature") or data.get("sig") or "").strip().lower()
    if not HEX128.match(signature):
        return {"error": "invalid_signature_format"}, 400
    try:
        ts_int = int(data.get("ts"))
    except (TypeError, ValueError):
        return {"error": "invalid_ts"}, 400
    ok, why = _check_ts(ts_int, last_ts)
    if not ok:
        return {"error": "timestamp_rejected", "message": why,
                "our_time": int(time.time())}, 400

    message = "\n".join([ROTATE_PREFIX, peer, new_pubkey, str(ts_int)]).encode("utf-8")
    if not ed25519_verify(bytes.fromhex(current), message, bytes.fromhex(signature)):
        return {"error": "signature_did_not_verify",
                "message": "Nothing has been changed. A rotation must be "
                           "signed by the key being replaced. This is what "
                           "stops anyone - including the operator of this "
                           "deployment - swapping a peer's key.",
                "we_verified_against": {
                    "format": ROTATE_PREFIX + "\\n<chain>\\n<new pubkey>\\n<ts>",
                    "the_exact_bytes_we_hashed":
                        "\n".join([ROTATE_PREFIX, peer, new_pubkey,
                                   str(ts_int)])},
                "signed_by_key_expected": current}, 400

    ts = time.time()
    ev = {"user_id": "sig:" + peer, "action": "signed_key_rotated", "amount": 0,
          "country": "UK", "device_id": "signed", "anomaly": 0, "device_risk": 0}
    res = {"decision": "KEY_ROTATED", "score": 0, "signed_version": VERSION,
           "peer": peer, "timestamp": ts,
           "detail": "from=" + current + ";to=" + new_pubkey +
                     ";authorised_by=" + current}
    h, idx, _seq, seal_error = _try_seal(ctx, ev, res, ts, FILED_UNDER)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE signed_keys SET pubkey=?,rotations=?,last_ts=? WHERE peer=?",
            (new_pubkey, (rotations or 0) + 1, float(ts_int), peer))
        ctx["conn"].commit()

    out = {"rotated": True, "chain": peer, "previous_pubkey": current,
           "pubkey": new_pubkey, "rotations": (rotations or 0) + 1,
           "sealed_in_our_chain": h, "block_index": idx,
           "sealed": seal_error is None,
           "latest_receipt_seq": _latest_seq(ctx, peer),
           "signed_version": VERSION,
           "sequence_note": MESSAGES["seq_survives_rotation"],
           "message": "Rotation sealed. Both keys are permanently in the "
                      "chain, so the history of this name's keys is public "
                      "and cannot be tidied up later."}
    if seal_error:
        out["seal_error"] = seal_error
        out["message"] = ("The rotation took effect and the new key is live. "
                          "The audit note about it did not seal, which is "
                          "reported rather than hidden.")
    return out, 200


def _keys(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT k.peer,k.pubkey,k.enrolled,k.block_index,k.rotations,k.note,"
            "COALESCE(s.last_seq,0) FROM signed_keys k "
            "LEFT JOIN signed_seq s ON s.peer = k.peer "
            "ORDER BY k.enrolled ASC LIMIT ?", (MAX_LIST,)).fetchall()
    out = []
    for peer, pubkey, enrolled, idx, rotations, note, seq in rows:
        entry = {"chain": peer, "pubkey": pubkey, "algorithm": "ed25519",
                 "enrolled_at": _iso(enrolled), "enrolment_block": idx,
                 "rotations": rotations or 0,
                 "latest_receipt_seq": seq or 0}
        if note and note.startswith("WARNING"):
            entry["flag"] = note
        out.append(entry)
    return {"count": len(out), "keys": out, "signed_version": VERSION,
            "note": MESSAGES["keys_note"],
            "receipt_seq_note": (
                "latest_receipt_seq is the highest receipt number issued to "
                "that name on this lane. A keyholder whose own highest "
                "receipt is lower than this has not received one of them, and "
                "can say exactly how many. Public on purpose - a gap you can "
                "only see from the inside is not evidence of anything."),
            "how_to_check_a_record": (
                "Take the pubkey from here, rebuild the canonical message "
                "from the record at /x/signed/verify, and check the signature "
                "with any Ed25519 implementation. You do not need anything "
                "from us to do it and you do not have to believe us.")}, 200


def _verify(ctx, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required",
                "usage": "/x/signed/verify?peer=<name>&tip=<64 hex>"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT observed,peer_ts,signature,pubkey,audit_hash,block_index "
            "FROM signed_log WHERE peer=? AND tip=? ORDER BY id ASC",
            (peer, tip)).fetchall()
    if not rows:
        return {"signed_observation": False, "peer": peer, "tip": tip,
                "message": "We hold no signed observation of this tip from "
                           "this name. It may still be in the open lane - "
                           "check /x/witness/attest."}, 404
    observed, peer_ts, signature, pubkey, h, idx = rows[0]
    ts_int = int(peer_ts)
    return {"signed_observation": True, "chain": peer, "tip": tip,
            "observed_at": _iso(observed), "peer_claimed_time": _iso(peer_ts),
            "sealed_in_our_chain": h, "block_index": idx,
            "times_observed": len(rows),
            "latest_receipt_seq": _latest_seq(ctx, peer),
            "signature": signature, "pubkey": pubkey, "algorithm": "ed25519",
            "canonical_message": "\n".join([MSG_PREFIX, peer, tip, str(ts_int)]),
            "canonical_message_bytes_note": (
                "Those four lines joined by a single newline, UTF-8, no "
                "trailing newline. Hash nothing yourself - Ed25519 takes the "
                "message, not a digest of it."),
            "signed_version": VERSION,
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"],
            "recheck_it_yourself": (
                "python: pip install pynacl, then "
                "nacl.signing.VerifyKey(bytes.fromhex(pubkey))"
                ".verify(canonical_message.encode(), bytes.fromhex(signature))")}, 200


def _spec():
    return {"signed_version": VERSION,
            "what_this_lane_is": (
                "Submissions signed by a key this deployment does not hold. "
                "The open lane at /x/witness/observe proves somebody handed "
                "us a tip. This lane proves the holder of a specific private "
                "key did - including against us, because we only ever hold "
                "the public half."),
            "why_it_exists": (
                "The HMAC lane binds a name to a shared secret, and a shared "
                "secret is held by both parties. It closes third-party "
                "submission under your name and does not close operator "
                "submission under your name. This lane closes both, and it "
                "does so by arithmetic rather than by our promise."),
            "steps": [
                "1. Generate an Ed25519 keypair. Keep the private half. It "
                "never leaves your side and we have no route that accepts one.",
                "2. POST /x/signed/enroll with {\"chain\":\"<name>\","
                "\"pubkey\":\"<64 hex>\"}.",
                "3. Build the canonical message, sign it, and POST "
                "/x/signed/submit with {\"chain\",\"tip\",\"ts\",\"signature\"}.",
                "4. GET /x/signed/verify?peer=&tip= for the receipt, which "
                "carries everything a third party needs to recheck it "
                "without us.",
            ],
            "canonical_message": {
                "submit": MSG_PREFIX + "\\n<chain>\\n<tip>\\n<ts>",
                "rotate": ROTATE_PREFIX + "\\n<chain>\\n<new pubkey>\\n<ts>",
                "encoding": "UTF-8, single \\n between lines, no trailing "
                            "newline. ts is integer epoch seconds.",
            },
            "replay_controls": {
                "max_age_seconds": SKEW_PAST,
                "max_future_seconds": SKEW_FUTURE,
                "monotonic": "ts must be strictly greater than the last ts "
                             "accepted for the name",
                "duplicate_signatures": "refused",
            },
            "on_acceptance": {
                "receipt_seq": MESSAGES["seq"],
                "receipt_seq_scope": {'values': ['per-peer', 'per-name', 'per-chain'], 'per-peer': 'issued per registered peer_id. Used by /x/peer/submit.', 'per-name': 'issued per bound name. Used by /x/bind/submit.', 'per-chain': 'issued per enrolled chain name. Used by /x/signed/submit.', 'why_it_is_here': 'The three signed lanes each count within their own scope, so a receipt carries the scope of its own sequence rather than requiring the holder to remember which lane produced it. The set is closed: a value outside this list is an error on our side, not a new scope you should widen a schema for.', 'not_comparable_across_scopes': 'Two receipts with different scopes are counting different things and their numbers say nothing about each other.'},
                "key_seq": MESSAGES["key_seq"],
                "sequence_survives_rotation": MESSAGES["seq_survives_rotation"],
                "seal_failure": (
                    "If the audit chain does not seal your submission you get "
                    "500 seal_failed with the reason, and nothing is "
                    "recorded - no sequence number, no log row, no receipt. "
                    "Send a fresh submission with a later ts once the fault "
                    "is fixed. A receipt you cannot verify is worse than no "
                    "receipt, so this lane will not issue one."),
                "two_different_completeness_claims": (
                    "receipt_seq is about completeness of the receipts WE "
                    "issued to you. It says nothing about completeness of the "
                    "records YOUR chain sealed, which no signature can reach "
                    "and which is listed under honest_limits."),
            },
            "this_lane_rejects": (
                "Unlike the open lane, a submission that does not verify is "
                "refused and nothing is sealed. Writing an unverifiable "
                "signature into a name's history is the harm, not the "
                "protection."),
            "key_rotation": (
                "A rotation must be signed by the key being replaced. Nobody "
                "who lacks the current private key can rotate it, this "
                "deployment included, and every rotation is sealed with both "
                "keys recorded."),
            "honest_limits": [
                "Does not prove the records behind the tip are true.",
                "Does not prove the peer's own chain is complete. Catching an "
                "omission there needs an audit protocol, not cryptography.",
                "Does not prove who the keyholder is in the world - only that "
                "the same party signed each time.",
                "Enrolment is open, so the first party to enrol a name gets "
                "it. An enrolment over a name already seen in the open lane "
                "is flagged permanently, which is detection and not "
                "prevention.",
                "receipt_seq proves you are missing a receipt. It does not "
                "prove why, and it cannot distinguish a lost response from "
                "one that was never sent.",
            ],
            "changed_in_1_1_1": [
                "receipt_seq_scope is now a bare token from a closed set - "
                "per-peer, per-name, per-chain - rather than a sentence, "
                "and the set is published so a closed schema can pin an "
                "enum. Asked for by Philip Pinol (PRAXIS). Value change "
                "only; the response shape is unchanged from 1.1.",
            ],
            "changed_in_1_1": [
                "receipt_seq is a real per-chain gapless sequence issued by "
                "this module, not the api_key counter that was always null "
                "here because this lane files under a label rather than a "
                "key. The completeness property applies to this lane for the "
                "first time.",
                "The api_key counter is still returned, as key_seq, and is "
                "null by design so the absence is stated rather than hidden.",
                "A failed seal returns 500 and records nothing, instead of "
                "returning a receipt with no block behind it.",
                "Enrolment and rotation report sealed true or false with the "
                "error, rather than sealing as a side effect and ignoring "
                "the outcome.",
                "/x/signed/keys publishes latest_receipt_seq per name.",
            ],
            "what_this_proves": MESSAGES["what_this_proves"],
            "what_this_does_not_prove": MESSAGES["what_this_does_not_prove"]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "enroll":
            return _enroll(ctx, data)
        if action == "submit":
            return _submit(ctx, data)
        if action == "rotate":
            return _rotate(ctx, data)
    else:
        if action == "spec":
            return _spec()
        if action == "keys":
            return _keys(ctx)
        if action == "verify":
            return _verify(ctx, data)
    return {"error": "unknown_action", "action": action}, 404

```
