# Codebase — part 29 of 29

Contains:
- `whitepaper.html`


## `whitepaper.html`

1305 lines, 107234 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>The sebbi.pro System — the deterministic evidence layer for AI</title>
<meta name="description" content="An interactive map of the sebbi.pro evidence layer. Tap any part of the system — the chain, anchoring, witnessing, oversight, the notaries — and read what it does, with the public routes to check it yourself.">
<style>
:root{
  --void:#07050a; --deep:#100a0d; --panel:#14100f; --panel2:#1b1614;
  --line:#3a2c1c; --line2:#4d3a22;
  --gold:#e0a94a; --ember:#ff9d3c; --cyan:#6fd6e0; --violet:#b895f0; --green:#8fe3a8; --amber:#f5c26b;
  --text:#f2ece2; --muted:#b8ad9c; --faint:#6d6355;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden;background:var(--void)}
body{font-family:var(--sans);color:var(--text);overscroll-behavior:none}

#stage{position:fixed;inset:0}
canvas{display:block;width:100%;height:100%;touch-action:none;cursor:grab}
canvas.drag{cursor:grabbing}

/* ---------- HUD chrome ---------- */
header{
  position:fixed;top:0;left:0;right:0;z-index:20;
  background:linear-gradient(180deg,rgba(7,5,10,.97) 62%,rgba(7,5,10,0));
  pointer-events:none;font-family:var(--mono);
}
header > *{pointer-events:auto}

/* top readout strip — the instrument row */
.hud{
  display:flex;align-items:center;gap:0;overflow-x:auto;scrollbar-width:none;
  border-bottom:1px solid var(--line);background:rgba(20,14,12,.72);
  padding:0 10px;height:30px;
}
.hud::-webkit-scrollbar{display:none}
.hud .cell{display:flex;align-items:baseline;gap:6px;padding:0 11px;flex:0 0 auto;white-space:nowrap}
.hud .cell + .cell{border-left:1px solid var(--line)}
.hud .k{font-size:8.5px;letter-spacing:1.7px;text-transform:uppercase;color:var(--faint)}
.hud .v{font-size:10.5px;color:var(--gold);letter-spacing:.4px}
.hud .v.pending{color:var(--faint)}
.hud .v.fail{color:#b8624a}
.hud .mark{font-size:8.5px;letter-spacing:2.4px;text-transform:uppercase;color:var(--ember);
  padding:0 11px 0 2px;flex:0 0 auto;font-weight:700}

/* control row — flat terminal buttons */
.bar{display:flex;gap:0;border-bottom:1px solid var(--line);background:rgba(16,10,13,.6);overflow-x:auto;scrollbar-width:none}
.bar::-webkit-scrollbar{display:none}
.chip{
  flex:0 0 auto;font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;
  padding:8px 13px;border:0;border-right:1px solid var(--line);background:transparent;
  color:var(--faint);cursor:pointer;
}
.chip:hover{color:var(--text);background:rgba(224,169,74,.06)}
.chip[data-on="1"]{background:var(--gold);color:#0b0709;font-weight:700}

.qwrap{display:flex;align-items:center;gap:8px;padding:7px 12px}
#q{
  flex:1;min-width:0;background:transparent;border:0;border-bottom:1px solid var(--line);
  padding:4px 0;color:var(--text);font-family:var(--mono);font-size:11.5px;outline:none;letter-spacing:.5px;
}
#q:focus{border-color:var(--gold)}
#q::placeholder{color:var(--faint);letter-spacing:1.2px;text-transform:uppercase;font-size:9.5px}
.iconbtn{
  background:transparent;border:1px solid var(--line);border-radius:0;color:var(--faint);
  font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;
  padding:6px 10px;cursor:pointer;white-space:nowrap;
}
.iconbtn:hover{border-color:var(--gold);color:var(--gold)}
.chip:focus-visible,.iconbtn:focus-visible,#q:focus-visible{outline:2px solid var(--cyan);outline-offset:2px}

/* ---------- legend ---------- */
#legend{
  position:fixed;left:14px;bottom:14px;z-index:15;font-family:var(--mono);font-size:9.5px;
  color:var(--faint);letter-spacing:.6px;line-height:1.9;pointer-events:none;
}
#legend b{color:var(--muted);font-weight:400}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;vertical-align:1px}

/* ---------- panel ---------- */
#panel{
  position:fixed;z-index:30;background:var(--panel);border:1px solid var(--line);
  display:flex;flex-direction:column;transition:transform .28s cubic-bezier(.3,.9,.3,1);
}
@media (max-width:760px){
  #panel{left:0;right:0;bottom:0;height:74vh;border-radius:18px 18px 0 0;border-bottom:0;transform:translateY(101%)}
  #panel.open{transform:translateY(0)}
  .grab{width:38px;height:4px;border-radius:3px;background:var(--line2);margin:9px auto 0;flex:0 0 auto}
}
@media (min-width:761px){
  #panel{top:0;right:0;bottom:0;width:430px;border-radius:0;border-right:0;transform:translateX(101%)}
  #panel.open{transform:translateX(0)}
  .grab{display:none}
  header{right:430px}
}
.phead{padding:16px 20px 13px;border-bottom:1px solid var(--line);flex:0 0 auto}
.pcluster{font-family:var(--mono);font-size:9.5px;letter-spacing:1.7px;text-transform:uppercase;margin-bottom:7px}
.phead h2{font-size:20px;font-weight:800;letter-spacing:-.4px;line-height:1.2}
.plede{font-size:13px;color:var(--muted);margin-top:7px;line-height:1.55}
#close{
  position:absolute;top:12px;right:14px;background:none;border:0;color:var(--faint);
  font-family:var(--mono);font-size:19px;cursor:pointer;padding:5px 8px;line-height:1;
}
#close:hover{color:var(--text)}
.pbody{padding:16px 20px 60px;overflow-y:auto;flex:1;-webkit-overflow-scrolling:touch}
.pbody p{font-size:14px;color:var(--muted);line-height:1.68;margin-bottom:13px}
.phead h2{font-family:var(--mono);letter-spacing:-.6px}
.pbody p b{color:var(--text);font-weight:600}
.pbody h3{
  font-family:var(--mono);font-size:10px;letter-spacing:1.6px;text-transform:uppercase;
  color:var(--gold);margin:22px 0 9px;
}
.live{
  background:var(--panel2);border:1px solid var(--line2);border-radius:11px;padding:13px 15px;margin-bottom:15px;
}
.live .lbl{font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--faint);margin-bottom:7px}
.live .val{font-family:var(--mono);font-size:13px;color:var(--green);word-break:break-all;line-height:1.6}
.live .val.pending{color:var(--faint)}
.live .val.fail{color:var(--amber)}
.routes{display:flex;flex-direction:column;gap:7px;margin-bottom:6px}
.routes a{
  font-family:var(--mono);font-size:12px;color:var(--cyan);text-decoration:none;
  background:var(--panel2);border:1px solid var(--line2);border-radius:9px;padding:10px 12px;
  display:flex;justify-content:space-between;gap:10px;align-items:center;
}
.routes a:hover{border-color:var(--cyan)}
.routes a span{color:var(--faint);font-size:10px;flex:0 0 auto}
.limit{
  border-left:2px solid var(--amber);background:rgba(240,179,84,.05);
  padding:12px 14px;border-radius:0 9px 9px 0;margin-bottom:15px;
}
.limit .lbl{font-family:var(--mono);font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--amber);margin-bottom:6px}
.limit p{font-size:13px;margin:0;color:var(--muted)}
.links{display:flex;flex-wrap:wrap;gap:7px;margin-top:4px}
.links button{
  font-family:var(--mono);font-size:11px;background:var(--panel2);border:1px solid var(--line2);
  border-radius:20px;padding:6px 12px;color:var(--muted);cursor:pointer;
}
.links button:hover{border-color:var(--gold);color:var(--text)}

#toast{
  position:fixed;left:50%;bottom:22px;transform:translate(-50%,20px);z-index:40;
  background:var(--panel);border:1px solid var(--line2);border-radius:9px;
  padding:9px 15px;font-family:var(--mono);font-size:11.5px;color:var(--muted);
  opacity:0;pointer-events:none;transition:.25s;
}
#toast.show{opacity:1;transform:translate(-50%,0)}

@media (prefers-reduced-motion:reduce){
  *{transition-duration:.01ms!important;animation-duration:.01ms!important}
}
</style>
</head>
<body>

<div id="stage"><canvas id="c"></canvas></div>

<header>
  <div class="hud" id="hud">
    <div class="mark">sebbi.pro × systems whitepaper × v8</div>
    <div class="cell"><span class="k">chain</span><span class="v pending" data-hud="tip">····</span></div>
    <div class="cell"><span class="k">roster</span><span class="v pending" data-hud="roster">····</span></div>
    <div class="cell"><span class="k">anchor</span><span class="v pending" data-hud="ots">····</span></div>
    <div class="cell"><span class="k">keys</span><span class="v pending" data-hud="keys">····</span></div>
    <div class="cell"><span class="k">nodes</span><span class="v" id="hudn">36</span></div>
  </div>
  <div class="bar" id="chips"></div>
  <div class="qwrap">
    <input id="q" placeholder="search the system" autocomplete="off" spellcheck="false" aria-label="Search the system">
    <button class="iconbtn" id="reset">recentre</button>
  </div>
</header>

<div id="legend">
  <div><span class="dot" style="background:var(--ember)"></span><b>tap any node</b> — the whole system, one piece at a time</div>
  <div><span class="dot" style="background:var(--gold)"></span><b>tap any node</b> — panel opens with routes to check it</div>
  <div><span class="dot" style="background:var(--ember)"></span><b>lit filament</b> — one part depends on another</div>
</div>

<aside id="panel" aria-live="polite">
  <div class="grab"></div>
  <div class="phead">
    <button id="close" aria-label="Close">×</button>
    <div class="pcluster" id="pcluster"></div>
    <h2 id="ptitle"></h2>
    <div class="plede" id="plede"></div>
  </div>
  <div class="pbody" id="pbody"></div>
</aside>

<div id="toast"></div>

<script>
"use strict";
const BASE = "https://sebbi.pro";

/* ============================================================
   CLUSTERS
   ============================================================ */
const CLUSTERS = {
  foundation:{name:"Foundation", col:"#f0a94a"},
  proof:     {name:"Proof layer", col:"#6fd6e0"},
  engine:    {name:"Engine",      col:"#c79bf5"},
  open:      {name:"Open & free", col:"#8fe3a8"},
  business:  {name:"Business",    col:"#f2d08a"}
};

/* ============================================================
   LIVE ROUTES — each returns a short string, or throws.
   Add a route here and it appears on its node automatically.
   ============================================================ */
const dig = (o, keys) => { for (const k of keys) if (o && o[k] !== undefined && o[k] !== null) return o[k]; return undefined; };
const short = h => (typeof h === "string" && h.length > 20) ? h.slice(0,12) + "…" + h.slice(-6) : h;

const LIVE = {
  roster: {
    url: "/x/roster/list",
    hud: d => ((d.count ?? (d.peers||[]).length) + " chains"),
    render: d => {
      const n = dig(d,["count"]) ?? (d.peers||[]).length;
      const w = dig(d,["witnessable"]), st = dig(d,["stale"]), si = dig(d,["silent"]);
      let s = n + " chain" + (n===1?"":"s") + " on the roster";
      const bits = [];
      if (st !== undefined) bits.push(st + " stale");
      if (si !== undefined) bits.push(si + " silent");
      if (bits.length) s += " · " + bits.join(" · ");
      return s;
    }
  },
  tip: {
    url: "/x/witness/tip",
    hud: d => { const h=dig(d,["height","blocks","index","block"]); const t=dig(d,["tip","head","chain_tip","hash"]);
                return h!==undefined ? ("block "+h) : (t?String(t).slice(0,10)+"…":"live"); },
    render: d => {
      const t = dig(d,["tip","head","chain_tip","hash"]);
      const h = dig(d,["height","blocks","index","block"]);
      let s = t ? short(t) : "tip served";
      if (h !== undefined) s += "  ·  block " + h;
      return s;
    }
  },
  keys: {
    url: "/x/signed/keys",
    hud: d => { const arr=d.keys||d.chains||d.enrolled||[]; const n=dig(d,["count"]) ?? (Array.isArray(arr)?arr.length:0); return n+" enrolled"; },
    render: d => {
      const arr = d.keys || d.chains || d.enrolled || [];
      const n = dig(d,["count"]) ?? (Array.isArray(arr) ? arr.length : 0);
      return n + " chain" + (n===1?"":"s") + " enrolled with a signing key";
    }
  },
  ots: {
    url: "/x/ots/status",
    hud: d => { const c=dig(d,["confirmed","anchored","complete"]); const pn=dig(d,["pending","submitted","upgrading"]);
                return (c===undefined&&pn===undefined) ? "served" : ((c??0)+" conf / "+(pn??0)+" pend"); },
    render: d => {
      const c = dig(d,["confirmed","anchored","complete"]);
      const p = dig(d,["pending","submitted","upgrading"]);
      if (c === undefined && p === undefined) return "anchor status served";
      return (c ?? 0) + " confirmed · " + (p ?? 0) + " pending upgrade";
    }
  },
  schema: {
    url: "/x/peer/schema",
    render: d => "machine-readable schema served (" + (Object.keys(d.properties||d).length) + " top-level fields)"
  }
};

/* ============================================================
   NODES
   ============================================================ */
const N = [
/* ================= FOUNDATION ================= */
{
 id:"problem", c:"foundation", label:"The problem", size:1.3,
 lede:"A log you can edit is not evidence. It only says what you currently claim happened.",
 body:[
  "Nearly every system keeps logs, and logs live in databases. A database can be edited by anyone with the right access — an attacker, an insider, or the operator itself. So an ordinary log can only ever say <b>this is what we currently claim happened</b>. It cannot say <b>and nobody has changed it since</b>.",
  "Most of the time nobody notices the difference. It appears the day someone with authority — a regulator, a court, an insurer, a customer in dispute — stops accepting your word and asks for proof. At that moment \"our system recorded it\" and \"here is proof it was not changed\" are two different sentences, and only the second carries weight.",
  "It has become urgent for a specific reason. Software used to do what it was told, so a log of the inputs implied the outputs. AI systems produce outputs that cannot be derived from the inputs by inspection, so the output has to be recorded as a fact in its own right — and the regulation now arriving says so explicitly. The volume of decisions requiring evidence has risen by orders of magnitude. The mechanism most organisations use to evidence them has not changed since the 1990s.",
  "Everything here exists to produce that second sentence — cheaply, automatically, as a by-product of systems doing their normal work."
 ],
 to:["chain","determinism","regulation"]
},
{
 id:"determinism", c:"foundation", label:"Deterministic gate", size:1.2,
 lede:"The governance layer is not an AI. It is arithmetic — and that is the only arrangement where it can do its job.",
 body:[
  "Put a model in charge of judging whether another model behaved acceptably and every property you needed disappears at once. The verdict cannot be reproduced, because the same input may score differently tomorrow. It cannot truly be explained, because the explanation is itself generated rather than derived. It drifts silently, because a retrained model changes its judgements without anyone choosing to change them. And anything that reads natural language can be attacked with natural language.",
  "Worst of all it regresses. If a model needs governing and the governor is a model, the governor needs governing. There is no bottom to that stack. It terminates only at something that cannot behave unexpectedly — which means arithmetic: fixed weights, fixed thresholds, an explicit published formula.",
  "<b>What determinism buys at audit.</b> A regulator or a court examining a decision two years later does not want a narrative. They want to establish that the decision followed from the stated rules. Determinism makes that mechanical: take the sealed inputs, take the sealed ruleset version, recompute. If the result matches the sealed verdict, the decision was the rules applied to the facts — and anybody can confirm it without the vendor in the room.",
  "That is the difference between a record that <b>describes</b> a decision and one that <b>reproduces</b> it. Only the second is evidence in any strong sense."
 ],
 limit:"A deterministic gate is not smarter than a model and is not meant to be. It will miss things a good classifier would catch, because it has no semantic understanding at all. The trade is deliberate: reproducibility bought at the cost of cleverness. Use models to do the work; use arithmetic to prove what the work did.",
 to:["sonicboom","reproducibility"]
},
{
 id:"chain", c:"foundation", label:"The hash chain", size:1.6, core:true,
 lede:"One append-only chain. Every seal contains the one before it, so history cannot be edited quietly.",
 body:[
  "At the centre of the whole platform is one data structure: an append-only chain of sealed records. Every product — the decision engine, the fraud detectors, the notaries, Brain — writes into a chain built the same way.",
  "Each record is sealed at the moment it is created. The seal is a SHA-256 hash over the record's content <b>together with the seal of the record before it</b>. Because each seal contains its predecessor, every block's integrity depends on the entire history beneath it.",
  "<b>seal(n) = SHA-256( seal(n−1) · timestamp · event · result · basis )</b>",
  "Alter one character of one historic record and every seal after it fails. There is no way to repair the chain after an edit without recomputing every subsequent seal — and the current tip is recorded in the same transaction as every write, so even chopping records off the end is detected.",
  "<b>Concurrency-safe:</b> the tip read, hash computation and insert happen inside a single lock hold and a single transaction. There is no race window in which two writers can fork the chain. <b>Crash-safe:</b> write-ahead journaling with full synchronous commits; a power cut mid-write rolls back cleanly. <b>Truncation-evident:</b> deleting blocks from the end breaks the tip record and is reported as tampering. <b>Fast:</b> score, decide, seal and respond runs inline, median 28ms — sealing is not a batch job that happens later.",
  "One sentence captures the design philosophy: <b>a system that does not trust its own creator is the only kind whose records qualify as evidence.</b>"
 ],
 live:"tip",
 routes:[["/x/witness/tip","current tip"]],
 to:["anchor","receipts","basis","completeness","erasure","forks","verifier"]
},
{
 id:"anchor", c:"foundation", label:"Bitcoin anchoring", size:1.35,
 lede:"A chain proves nothing was altered. It does not prove when the chain was built. So the clock was moved outside.",
 body:[
  "This is the hole every tamper-evident audit product has, and most do not mention it. An operator with full control could discard the chain and construct a fresh one dated however they liked, and every seal in the fabricated chain would verify perfectly. Internal integrity is necessary. Alone it is not sufficient, because the operator still controls the clock.",
  "So at a defined interval the current tip is submitted to <b>OpenTimestamps</b>, which aggregates it with thousands of unrelated timestamps into one Merkle tree and commits that root to the Bitcoin blockchain. Several independent calendar servers do this in parallel, so no single calendar can fail, disappear or lie without the others contradicting it.",
  "The distinction matters, because the loose version — \"we write your hash to Bitcoin\" — is both technically wrong and commercially misleading. We do not make a Bitcoin transaction per anchor. We contribute to one. That is why anchoring runs continuously rather than when someone remembers the cost: the marginal cost is effectively zero, and a timestamp that only happens when convenient is not a timestamp.",
  "<b>Submitted is not confirmed.</b> A calendar promises to commit the tip; the transaction lands later. Until the proof has been upgraded and confirmed, it is pending — not anchored. Per-proof state is published rather than asserted, because this platform described it wrongly for three weeks before someone checked.",
  "The oldest objection to any audit trail is one sentence: <i>you could have written all of this last week.</i> Every assurance a vendor offers in reply is another claim from the party being questioned. An anchored chain answers with arithmetic instead — and the person checking needs no account, no cooperation from us, and no continued existence of this company. <b>The evidence outlives the vendor.</b>",
  "Three deliberate design points. <b>Nobody holds crypto</b> — Bitcoin is used purely as a timestamp nobody owns, and the asset's price is irrelevant to the function. <b>Anchoring is not the integrity mechanism</b> — the chain provides integrity, anchoring fixes it in time; conflating the two is the standard error in blockchain-audit marketing. <b>The reference is returned to you</b>, so going through us is optional at every stage."
 ],
 live:"ots",
 routes:[["/x/ots/status","anchor state, per proof"]],
 limit:"Anchoring proves existence and timing. It does not prove the record was true at capture — but no ledger, court transcript or set of company books verifies the truth of its own inputs. It also closes backdating only up to the last confirmed proof; between anchors, the gap is small, real, and shared by every vendor in this market. And it inherits Bitcoin's assumptions: a conservative choice, but a dependency.",
 to:["witness"]
},
{
 id:"receipts", c:"foundation", label:"Gapless receipts", size:1.15,
 lede:"A chain proves records were not edited. Receipts prove records were not omitted.",
 body:[
  "A tamper-evident chain says nothing about a record that was never written. An operator could simply fail to seal an inconvenient event. Receipts close that.",
  "Every sealed decision is issued a sequence number <b>in the same transaction</b> as the chain write, and sequences are gapless by construction: 46, 47, 48. You keep your receipts. If you ever hold 46 and 48 with no 47, a record has been omitted — and you can show it by arithmetic rather than argument.",
  "<b>Edited records break the chain. Missing records break the sequence. Fabricated history breaks the anchor.</b> Between the three, every way of quietly rewriting the past is detectable from outside, by anyone, without trusting the operator. That triple is the whole security model, and it is deliberately small enough to hold in your head.",
  "Every signing lane issues its own gapless sequence, scoped and published: per-peer, per-name, per-chain. Not comparable across scopes, and each spec publishes the closed enum so nobody has to guess."
 ],
 limit:"Receipts protect whoever holds the receipt. They do not help a party who never received one, and they cannot answer \"is this the complete set\" for someone auditing from outside. Completeness closes that.",
 to:["completeness","peer-lane"]
},
{
 id:"basis", c:"foundation", label:"Basis sealing", size:1.1,
 lede:"Two records hide inside \"what a system did\": the action, and what the action was allowed to rely on.",
 body:[
  "A seal on the action alone proves the action happened exactly as recorded. It cannot show what the action rested on — and a decision made on the wrong source, sealed, is just a tamper-proof error. So the engine seals both, in the same block.",
  "The basis records which sources were used, the content hash of each version of them, the ruleset and ruleset version that applied, and the signal pack in force. It is canonicalised, hashed and folded into the block seal.",
  "Edit the recorded basis later and the chain breaks exactly as if the action had been edited. Even <b>no basis was supplied</b> is sealed as a fixed sentinel — so the absence of a basis is a provable fact, not a blank that can be filled in later."
 ],
 limit:"Basis sealing proves what a decision relied on and that the record of it is unaltered. It does not prove the basis was correct — that a source was genuine or the ruleset was the right one. Integrity is provable by mathematics; correctness is a separate discipline involving people and process. Any product claiming to cryptographically prove correctness is misdescribing what cryptography can do.",
 to:["packs","lineage"]
},

/* ================= WITNESS ================= */
{
 id:"witness", c:"foundation", label:"Witness network", size:1.5, core:true,
 lede:"One chain can be rebuilt. Ten cannot — not without everyone who watched you rewriting theirs in step.",
 body:[
  "Anchoring closes backdating, but only up to the last anchor. Between anchors an operator with full control of their own server can still, in principle, construct a history and present it. It closes when platforms witness each other.",
  "Each platform periodically publishes its current chain tip; each peer seals that tip into <b>its own chain</b>. From that moment one platform's history is recorded inside chains it does not control, which are themselves independently anchored. To rewrite your own past you would need every peer who witnessed you to rewrite theirs, in step, and re-anchor all of it. That is no longer a technical operation on a database. It is a coordinated conspiracy between commercial competitors, and the difficulty scales with the number of participants rather than the size of anyone's engineering team.",
  "The economics make it practical. A chain tip is 64 characters. Witnessing one is a single sealed block. Ten platforms exchanging tips hourly generates a few hundred blocks a day <b>between all of them</b> — an integrity property strong enough to matter, at a cost small enough to ignore.",
  "Two asymmetries make it work. A peer lying <i>about</i> us cannot help us: sealing a tip we never issued produces an entry pointing at a chain state that does not exist, which fails the moment anyone checks. A peer can only conspire with us, never frame us. And our peers are anchored too, so the conspiracy is not two parties agreeing a story — it is two parties defeating timestamps already published in a ledger neither controls."
 ],
 live:"roster",
 routes:[["/x/roster/list","the public roster"],["/x/witness/spec","the protocol"],["/x/witness/observe","submit a tip"],["/x/witness/attest","ask who witnessed us"]],
 limit:"Witnessing proves a tip existed at a time. It says nothing about whether the records behind it are true — garbage sealed on time remains garbage. Two platforms witnessing only each other prove very little; the guarantee comes from breadth. And no design can compel a peer to keep publishing: silence is made visible, not prevented.",
 to:["roster","signed","forks","open-endpoint","names","conformance"]
},
{
 id:"open-endpoint", c:"open", label:"Open submission", size:1.1,
 lede:"Anyone can submit a tip. No account, no key, no approval — permanently and on purpose.",
 body:[
  "The route that accepts a chain tip requires nothing from anyone. That is not an oversight and it is not generosity. It is the answer to the only serious objection the model faces.",
  "The objection is collusion: if we choose our witnesses, we can choose witnesses who will lie with us. It is a fair challenge and it has been put to us directly. The decisive part of the answer is this — <b>because anyone can witness us without asking, we cannot know who is doing it.</b> A client, an auditor, a regulator or a competitor can pull our tip on a timer and seal it wherever they like. Collusion requires knowing your co-conspirators. Open witnessing removes that knowledge from us permanently.",
  "Three further properties are deliberate. <b>Nobody owns it</b> — there is no licence and no revenue share, because an integrity property is participated in rather than purchased. <b>Anyone can query it</b> — a third party can ask whether a given tip was witnessed, when, and in which block. <b>Silence is visible</b> — peers who stop publishing are marked stale and then silent, and a replayed tip is flagged automatically.",
  "A witnessing network that only accepts submissions from account holders is a customer list, not a witness network."
 ],
 routes:[["/x/witness/observe","POST a tip"],["/x/roster/list","who has submitted"]],
 to:["roster"]
},
{
 id:"names", c:"foundation", label:"Names & binding", size:1.0,
 lede:"Submission is open, so a chain name is self-declared. The fix is not accounts — it is publishing how strong each claim is.",
 body:[
  "Two checks run on every submission and <b>neither can reject it</b>. A submission is always sealed; what changes is what is said about it.",
  "A <b>liveness</b> check fetches the submitted URL. <i>Live</i> means it served a valid but different tip, which is what a busy chain does between submitting and being fetched. <i>Self-consistent</i> means it served exactly the tip the submitter sent — both halves came from the submitter, so this records self-consistency and not verification by us or any third party. <i>Self-declared</i> means no URL, or we could not reach it: taken on the submitter's word and checked by nobody.",
  "A <b>name binding</b> check records the URL a name was first seen at and compares every later submission: first-use, bound, or <i>conflict</i> where the same name arrives from a different address. A conflict is not proof of theft — operators move hosts — but it is exactly the event an auditor needs to see, and it is recorded permanently rather than resolved quietly by us.",
  "That vocabulary exists because an earlier version conflated <i>reachable</i> with <i>verified</i>. An outside reviewer caught it. The correction is published in the route's own body text rather than quietly patched."
 ],
 routes:[["/x/bind/spec","binding specification"],["/x/roster/list","status vocabulary, published"]],
 limit:"The liveness check proves the submitter operates a live chain producing that data. It does not prove they are who they say, because anyone running a real chain can point a stolen name at their own URL.",
 to:["roster","signed"]
},
{
 id:"roster", c:"open", label:"The roster", size:1.2,
 lede:"Who has submitted, when they were last seen, and how each name is bound. Published, not described.",
 body:[
  "The roster is the network's own audit surface. For each chain it publishes the tip URL, how many observations have been recorded, when it was first and last seen, hours elapsed since, and how the name is bound to whoever submits under it.",
  "It publishes its own vocabulary alongside the data, so no reader has to guess what a status means. <i>Current</i> is observed within six hours, <i>stale</i> between six and forty-eight, <i>silent</i> beyond that. The route says in its own body that these describe elapsed time since we last recorded an observation and nothing else — a peer publishing on a human schedule reads stale between sessions, correctly, and it is not a judgement about anyone.",
  "It also states what the list is not: parties that have submitted a tip, and that is all it records. Not a membership list, not a set of partners, not participants in anything being built. Being listed implies no relationship beyond having sent a hash, and no endorsement of anything sealed in anyone's chain including ours."
 ],
 live:"roster",
 routes:[["/x/roster/list","the full roster"]],
 to:["signed","conformance"]
},
{
 id:"signed", c:"foundation", label:"Signing keys", size:1.25,
 lede:"You generate the keypair. You keep the private half. We hold the public half and can never produce a signature.",
 body:[
  "A shared-secret lane binds a submission to a secret. If the operator issued that secret, the operator could in principle have produced the submission. That is a real limit, and three separate reviewers arrived at it independently before it was fixed.",
  "The Ed25519 lane removes it. You generate the keypair and keep the private half — it never travels and there is no route that accepts one. The public half can go over any channel at all, because a public key is not a secret: LinkedIn, email, a postcard, read out over the phone. We hold only the public half, which means we can verify a signature and can never produce one.",
  "That is arithmetic rather than a promise about our conduct, and it is stronger than any channel we could have offered. Rotation is yours too: a rotation must be signed by the key being replaced, so we cannot swap your key even if we wanted to.",
  "The canonical message is four lines joined by newlines — protocol tag, chain name, tip, integer epoch seconds — deliberately positional and free of JSON so two implementations cannot disagree about how to build it. The receipt carries the public key, the exact canonical message and the signature, so a third party rechecks it with any Ed25519 library without asking either party for anything."
 ],
 live:"keys",
 routes:[["/x/signed/spec","the specification"],["/x/signed/keys","enrolled keys"],["/x/signed/enroll","enrol your own key"]],
 limit:"Enrolment is open, so the first party to enrol a name gets it. Detection rather than prevention: an enrolment placed over a name already seen in the open lane is flagged permanently. And if you lose the private half you enrol a new name and the abandoned one stays visible — the honest cost of the stronger property.",
 to:["schema","peer-lane"]
},
{
 id:"peer-lane", c:"foundation", label:"Peer submission lane", size:1.1,
 lede:"How an external platform seals into this chain, with a receipt it can validate against a published schema.",
 body:[
  "A peer submits a hash-only envelope. Nothing but digests crosses the boundary — no payloads, ever. What comes back is a receipt: the sealed audit hash, the block, a per-peer gapless sequence number, and the verification properties that receipt actually carries — inclusion, ancestry, append-only — named individually rather than asserted as a lump.",
  "The sequence is real and per-peer, so a peer holding receipts 5 and 7 can show a sixth exists that it never received. It survives key rotation deliberately, because a counter that reset on rotation could be used to erase a gap.",
  "A failed seal now returns an error and writes nothing. It used to return success with empty seal fields — see <b>Refused receipts</b> for how that was found and by whom."
 ],
 routes:[["/x/peer/spec","the specification"],["/x/peer/schema","machine-readable schema"]],
 to:["schema","refusals"]
},
{
 id:"schema", c:"open", label:"Published schema", size:1.05,
 lede:"The response shape as machine-readable JSON Schema, so a validator loads it rather than transcribing prose.",
 body:[
  "Every disagreement in the integration described under <b>Refused receipts</b> came from the same place: a reviewer read a written description, built rules from it, and the description and the actual bytes had drifted. The behaviour was correct every time. The transcription was not.",
  "The fix was to stop writing better prose. The response shape is published as a JSON Schema, draft 2020-12, with closed objects throughout. An integrator points a validator at it directly. There is no transcription step left to get wrong.",
  "Any interface described only in sentences will drift from what it actually returns. The schema route is the interface; the prose is commentary on it."
 ],
 live:"schema",
 routes:[["/x/peer/schema","the schema"]],
 to:["conformance"]
},
{
 id:"refusals", c:"open", label:"Refused receipts", size:1.3, core:true,
 lede:"An external reviewer refused eight consecutive receipts. Every refusal was right, and every fault was ours.",
 body:[
  "In August 2026 an independent platform built a closed schema against our published response shape and refused to accept any receipt its own verifier would not validate. Not logged a warning — refused. Nine submissions. Eight rejected.",
  "<b>The first receipt said the submission was sealed. It was not.</b> No block existed at that timestamp. The sealing call had failed and a bare exception handler swallowed it, so the response reported success while carrying nothing behind it. That route had never been exercised by an outside party, so the fault had been there since the day it was written. Their verifier caught it. Ours did not, because we had none pointed at ourselves.",
  "<b>Then a sequence field that was always empty.</b> It read a counter that lives on an API key, and that lane has no key, so the field was permanently null while being named as a sequence. It looked like a completeness guarantee — receipts N and N+2 proving a third exists you never received. It was not one. Anyone relying on it could not have proved anything.",
  "<b>Then three rounds of shape disagreement</b>, all the same underlying cause. A field documented in one place and returned in another. Each time, the behaviour was right and the description was wrong. So the response shape was published as a machine-readable schema and the transcription step disappeared. The next submission verified end to end with zero refusals, first attempt.",
  "The agreed description of what that established, and nothing beyond it: <b>a one-directional bounded external sealing test, verified end to end.</b> Not reciprocal verification. Not mutual witnessing. Not production proof, compliance certification, or live customer deployment. Both sides hold that line.",
  "Separately and independently: three reviewers arrived at the same objection to the shared-secret lane, which produced the Ed25519 path. One found that <i>reachable</i> and <i>verified</i> were being conflated in the roster vocabulary, which produced the published status definitions. One established that <i>submitted</i> to a timestamp calendar is not <i>anchored</i>, which produced the per-proof status route.",
  "None of this was found by us. It is recorded here because a system that holds evidence about its own conduct cannot be trusted to mark its own work, and the only meaningful answer is to be marked by somebody else — in public, including when the result is embarrassing. If you are building anything that issues proofs: find someone who will refuse them."
 ],
 to:["schema","conformance","peer-lane"]
},

/* ================= ENGINE ================= */
{
 id:"sonicboom", c:"engine", label:"SonicBoom", size:1.35, core:true,
 lede:"The decision engine. Allow, challenge or block — deterministically, in about 28 milliseconds.",
 body:[
  "Seven fields per event: who is acting, what they are doing, the value involved, where from, on what device, plus two optional risk signals your own systems may already produce. Send zero if you do not have them — the engine works from its own analysis. An optional eighth field carries delegated authority.",
  "The engine combines independent signals: how fast events are arriving for this user and device, whether the country has changed or is off the expected list, how large the amount is on a log scale, and a <b>per-user trust score learned over time</b>. Trust is earned slowly with every allowed action and lost roughly eight times faster on every block — so an account behaving normally builds standing, and a burst attack destroys its own standing as it runs, making each successive attempt score worse.",
  "<b>ALLOW</b> below 0.35 — proceed. <b>CHALLENGE</b> below 0.70 — borderline, verify further. <b>BLOCK</b> — refuse, with the reasons stated in plain English: velocity spike, new country, low trust.",
  "Every verdict is sealed into the chain <b>before the response returns</b>, with its reasons, its jurisdiction tag, its active pack version and its basis. The caller receives the verdict, the reasons, the sealed hash and the gapless receipt number in one response."
 ],
 to:["packs","sentinel","oversight","authority","chain","challenge","monitoring"]
},
{
 id:"challenge", c:"engine", label:"The challenge flow", size:0.95,
 lede:"When the verdict is borderline, the human step becomes part of the evidence rather than a gap in it.",
 body:[
  "A CHALLENGE response includes a hosted resolution flow: a signed link your user can open to confirm or deny the action, a status endpoint you poll for the outcome, and an expiry. Tokens are stateless and signed; the resolution is sealed into the chain as its own block.",
  "Integration is three lines — if the verdict is CHALLENGE, show the link, poll the status. The exception path, which is exactly the moment a human steps in, is recorded rather than lost."
 ],
 to:["oversight"]
},
{
 id:"monitoring", c:"engine", label:"Monitoring", size:0.9,
 lede:"One call that answers \"is my evidence complete?\" with a yes or a no.",
 body:[
  "Two authenticated endpoints give an operator live sight of their own traffic. A pulse view: the last hour's verdicts, recent decisions with their reasons and seals, and the current chain tip. A coverage view: receipts issued reconciled against blocks sealed.",
  "When the engine blocks on your traffic the sealed evidence is emailed to the account address, throttled to once an hour so a burst cannot flood you."
 ],
 to:["receipts"]
},
{
 id:"packs", c:"engine", label:"Signal Packs", size:1.15,
 lede:"Domain rules, versioned and sealed into every decision they governed.",
 body:[
  "The core engine scores every event against nine signals: trust, velocity at 60 seconds, 5 minutes and 1 hour, amount, device risk, anomaly, country shift and unsafe country. Those nine are domain-neutral — they describe the shape of behaviour, not the specifics of an industry.",
  "It is worth being precise about what they are and are not, because it is a fair criticism and it has been put to us. They are transaction-risk signals. That is the lineage of the engine and the right toolkit for fraud and abuse. It is <b>not</b> a risk taxonomy for the AI Act's risk-management obligations, and describing it as one would be an overclaim. The taxonomy belongs to the operator; the proof that it operated belongs here.",
  "A pack is a versioned bundle of additional signals, weights and thresholds loaded on top of the core. Packs run on the same deterministic engine — no model, no training, no drift. Payments and fraud; child safety; lending and onboarding; marketplace integrity; or an operator's own signals on the same guarantees.",
  "<b>Why versioning matters at audit.</b> Suppose an examiner asks, two years later, why a decision came out as it did. To answer you must establish which rules were live at that moment. Almost every platform answers from a changelog — a document someone with access could have edited afterwards. So every pack carries a version hash over its full definition, and the pack hash is sealed inside the decision block. Change a weight and the pack takes a new hash, and the change enters the chain as its own timestamped, anchored block. <b>Rule changes become auditable events, never silent edits.</b>"
 ],
 limit:"A pack encodes a judgement about what matters in a domain, and that judgement can be wrong. Sealing proves which rules ran and that the verdict followed from them; it says nothing about whether those were the right rules.",
 to:["reproducibility"]
},
{
 id:"sentinel", c:"engine", label:"Sentinel", size:1.0,
 lede:"The speed and shape of activity, rather than the content of any single event.",
 body:[
  "The patterns are the classic signatures of attack: a flood of login attempts against one account, a burst of transactions in seconds, an account appearing in a new country moments after its last action.",
  "Sentinel's velocity analysis is one of the signals driving the engine's score, and when a pattern crosses the line the flag — what fired, when, on what evidence — is sealed into the same chain. A fraud team gets not just an alert but an alert with a tamper-evident, externally anchored record behind it that survives scrutiny later."
 ],
 to:["guardian"]
},
{
 id:"guardian", c:"engine", label:"Guardian", size:1.1,
 lede:"The same machinery aimed at platforms where children are present.",
 body:[
  "Guardian watches for the recognised behavioural warning signs that precede grooming — pressure toward secrecy, attempts to isolate, moves toward private channels — and flags them.",
  "Two design decisions matter. <b>Message content is never stored</b>, only a fingerprint of it: privacy is preserved, and what is kept is proof that the flagged exchange existed in exactly the form it had. And every flag is sealed, so the trail handed to a parent, a platform's safety team or the authorities is tamper-evident from the moment of detection and externally anchored shortly after.",
  "In the one context where this evidence may end up in front of a court, a safeguarding report backed by an anchored chain is a fundamentally stronger document than one backed by an editable log. That difference is the entire point."
 ],
 limit:"Guardian is a detection and evidence aid. It supports a platform's duty of care; it does not discharge it. Child-safety decisions must always involve trained people and, where warranted, the proper authorities.",
 to:["chain","regulation"]
},
{
 id:"oversight", c:"engine", label:"Human oversight", size:1.3, core:true,
 lede:"Nobody can prove a human deliberated. Rubber-stamping, though, leaves marks.",
 body:[
  "Article 14 requires that natural persons can <b>effectively oversee</b> a high-risk system. Every vendor in this market claims to satisfy it, and the honest position is that none of them can, including this one. Whether a reviewer genuinely deliberated is an internal state. No logging reaches it. Any product claiming to prove human thought is selling something that does not exist.",
  "Rubber-stamping is not an internal state. It is a behavioural pattern, and patterns leave marks provided the right things are recorded, in the right order, at the time. Three mechanisms follow.",
  "<b>Order.</b> The case is presented to the reviewer without the machine's verdict. Their own decision and reasoning are sealed first; the verdict is revealed only afterwards. Two blocks, in that sequence, in a chain that cannot be reordered. A reviewer cannot have merely agreed with an answer they had already been shown, because the chain fixes which came first.",
  "<b>Attention.</b> The interval between opening a case and committing to it is sealed alongside the decision. A 0.8-second approval sits in the record permanently, beside a two-minute one. A single fast decision proves nothing. Four hundred consecutive sub-second decisions is a different kind of object — one that survives being explained away.",
  "<b>Independence.</b> Agreement rate is recorded per reviewer over time. A reviewer who has never once diverged from the machine across a meaningful sample is visible in the data. The measurement is dull, which is precisely why it works.",
  "So \"a human reviewed it\" and \"a human clicked accept on a recommendation\" stop being indistinguishable six months later — and only one of them is oversight."
 ],
 limit:"This proves order, not thought. A reviewer can leave a screen open, and dwell time is gameable by anyone deliberately gaming it. Most importantly the ordering guarantee is only as strong as the integration honouring it: if a platform displays the machine verdict to its own staff before calling the endpoint, the sealed order proves nothing at all. That constraint is documented in the code rather than buried in it, because a guarantee whose failure mode is undisclosed is not a guarantee.",
 to:["authority","conformance","probes"]
},
{
 id:"authority", c:"engine", label:"Delegated authority", size:1.1,
 lede:"Human oversight only means something if the human doing it was actually authorised to.",
 body:[
  "The engine issues signed authority tokens: a single call binds a user to a role, a spending limit and an expiry, signed server-side. The grant is sealed into the chain as its own block — so who gave this person this power, and when, is a permanent record rather than an HR email.",
  "Events then carry the token. The engine verifies it deterministically: wrong user, expired grant, tampered token, or an amount above the granted limit each escalates the verdict and seals the reason into the record. An approval made outside granted authority is no longer a quiet judgement call; it is a flagged, sealed, examinable event."
 ],
 limit:"A sealed token proves who was empowered, to what limit, until when. Not that granting it was a good idea.",
 to:["identity","jurisdiction","authority-cont"]
},
{
 id:"identity", c:"engine", label:"Identity sealing", size:0.9,
 lede:"KYC outcomes made provable, with zero personal data held.",
 body:[
  "The platform does not verify passports — specialist providers do that, and pretending otherwise would be theatre. What the engine does is make the <b>outcome</b> provable: one call seals the provider, whether verification passed, and the fingerprint of the provider's reference.",
  "The document, and even the raw reference number, are never stored. Later, \"this user was verified by provider X on date Y\" is a sealed fact any auditor can check, with nothing personal held to leak."
 ],
 to:[]
},
{
 id:"jurisdiction", c:"engine", label:"Jurisdiction tagging", size:0.9,
 lede:"Which rules governed the moment, sealed at decision time.",
 body:[
  "Every governed decision is tagged with the frameworks that applied when it was made — EU AI Act, GDPR and DSA for EU-origin events; the Online Safety Act, UK GDPR and Children's Code for the UK — using a versioned mapping sealed inside the decision block. A multinational can answer \"show every decision and which regulator's rules governed it\" from the chain alone."
 ],
 limit:"This records which obligations applied. It does not and cannot decide legal authority — courts do that. Any product claiming to determine which jurisdiction controls is describing a lookup table in grander language. This one is a lookup table too: versioned, sealed, and honest about it.",
 to:["regulation"]
},
{
 id:"brain", c:"engine", label:"Brain", size:1.1,
 lede:"A gate every instruction passes through before the AI acts.",
 body:[
  "An AI does what it is told, so the question becomes who checks what it is being told. A poisoned instruction — ignore your rules, export the customer data, delete the logs — walks straight in unless something stands in front of it.",
  "Brain checks against five categories of known-dangerous pattern: child safety, data exfiltration, compliance bypass, prompt injection, system destruction. Normalisation defences mean unicode look-alikes, zero-width characters and spacing tricks resolve to the same fingerprint as the plain form. Dangerous instructions are blocked with the reason stated, and every decision — allowed or blocked — is sealed with its basis.",
  "Brain is distributed differently from the rest of the platform: a single pure-Python file, free to download, standard library only, no cloud, no API key. It runs entirely on your machine and your instructions never leave your system. It is meant to be read before it is run — every line — because <b>a governance tool you cannot inspect is itself an ungoverned claim.</b>"
 ],
 routes:[["/brain","download it, free"]],
 limit:"Brain blocks known-dangerous patterns. It does not catch every possible paraphrase of a bad instruction — no filter honestly can, and any vendor claiming complete coverage of natural language is overclaiming. The filter is the first line; the evidence is the product.",
 to:["chain","aitxt"]
},

/* ================= NOTARIES ================= */
{
 id:"notaries", c:"open", label:"The Notaries", size:1.25, core:true,
 lede:"The same chain, free, no account, no code. Your content never leaves your device.",
 body:[
  "The notaries expose the chain directly to the public. They exist for two reasons. The obvious one: most people and small businesses have no system to integrate, but still have things worth proving. The strategic one: <b>a claim about evidence infrastructure is only credible if anyone can test it in thirty seconds without asking permission.</b>",
  "They share one privacy design. Your browser computes a SHA-256 fingerprint locally; only that 64-character fingerprint is sent and sealed. The chain proves a document with exactly that fingerprint existed at that moment. You reveal the original only if you ever need to — and if you never need to, nobody ever sees it.",
  "Every seal returns a unique 12-character code, the holder's permanent claim to that record. One shared chain underneath, anchored like everything else; one private receipt each. A sole trader's sealed quote and a bank's sealed decision sit in the same structure with the same guarantees. That was deliberate."
 ],
 routes:[["/notary","use them, free"]],
 limit:"Fingerprint matching is exact. A re-encoded copy, a paraphrase or a re-saved image produces a different fingerprint and will not match.",
 to:["notary-post","notary-pay","notary-dsr","notary-recon","notary-decl","chain"]
},
{
 id:"notary-post", c:"open", label:"Post & identity notary", size:0.9,
 lede:"The exact words, fixed. And a profile, dated before the clone.",
 body:[
  "Seal the exact words of anything before you send or publish it — a quote, a contract, an announcement, a message. Later, anyone can verify those words existed on that date and have not been edited. A tradesman who sealed a £2,400 quote the day he sent it ends a \"you said £1,800\" dispute with mathematics rather than argument. It cost him nothing and took ten seconds.",
  "The identity notary seals your name, role and links and returns a short verification code for your public profile. If a fraudster clones the profile, the clone fails the check — the genuine one was sealed first and the chain proves which came first. Impersonation defence is usually framed as detection; this reframes it as chronology, which is a far easier thing to prove."
 ],
 to:[]
},
{
 id:"notary-pay", c:"open", label:"Payment notary", size:0.95,
 lede:"Bank details verified before money moves — and both sides hold the proof.",
 body:[
  "A business seals its genuine bank details once; every invoice carries a short code; the payer checks the code before releasing funds. If an intercepted invoice's details were swapped — the classic authorised-push-payment fraud — the check returns MISMATCH and the payment stops.",
  "The verification itself is sealed and returned as a receipt, so <b>both sides hold provable evidence that care was taken before money moved</b>. Under the 2024 mandatory reimbursement rules, that record speaks directly to where liability falls."
 ],
 to:["regulation"]
},
{
 id:"notary-dsr", c:"open", label:"Data subject requests", size:0.95,
 lede:"Received, assessed, extended, completed — sealed in order, holding no personal data.",
 body:[
  "When a person asks an organisation to delete their data, three facts must be provable afterwards: that the request was received and when, that it was actually considered and on what grounds, and that it was answered inside the statutory deadline. Almost no organisation can prove any of the three. They have an email thread and a recollection.",
  "The notary seals the whole lifecycle as ordinary blocks. The calendar-month deadline is computed and sealed at receipt, and an extension is its own sealed block recording both the old and new dates — so an extension cannot be applied retrospectively to cover a deadline that was already missed.",
  "The chain never holds the person's identity. The identifier supplied is fingerprinted on arrival and only the fingerprint is stored. This answers the objection that an append-only chain conflicts with the right to erasure: the personal data lives in the operator's systems and is deleted there. What remains is a seal that resolves to nothing."
 ],
 to:["erasure"]
},
{
 id:"notary-recon", c:"open", label:"Reconciliation notary", size:1.05,
 lede:"A sealed chain of fiction is still fiction. This attacks that directly.",
 body:[
  "An operator who seals fiction on time possesses a tamper-evident chain of fiction, and everyone honest in this field knows it. The reconciliation notary does what auditors have always done: substantive testing against source records.",
  "The mechanism that makes it more than theatre is the ordering. A selection seed is derived from the current chain tip — a value the operator cannot predict in advance and cannot alter afterwards without breaking the chain. The records to be tested are chosen from it, and <b>that selection is sealed before any data is requested</b>. Only then are the identifiers returned for the operator to fetch from their own live system.",
  "So the operator cannot choose which records are examined, cannot prepare only the flattering ones, and cannot quietly discard a test that went badly: every planned run is sealed when it is planned, and a plan with no submitted result remains permanently visible as an abandoned test. Mismatches are sealed with exactly the same permanence as matches. A reconciliation system that can bury its own failures is decoration.",
  "What a pass means, stated exactly: two systems the operator controls agree with each other, on records the operator could not select, at a moment the operator could not choose. That is not proof of truth. What it changes is the cost of lying — from editing one database to maintaining a coherent parallel reality across independent systems indefinitely, under unpredictable sampling, with every failure sealed permanently."
 ],
 limit:"It tests systems the operator controls against each other, not against the world. An operator fabricating coherently across every system in real time will pass.",
 to:[]
},
{
 id:"notary-decl", c:"open", label:"Declaration notary", size:0.95,
 lede:"Publish the rules you hold yourself to — before the records they judge.",
 body:[
  "An operator publishes a file stating what must always be true of their decisions: payments above a threshold are never auto-approved, every decision carries reasons. Every sealed record is then tested against it and violations are sealed.",
  "The obvious objection is circularity — they wrote their own rules and supplied their own data. Two properties answer it. <b>The rules are sealed before the records they judge</b>, so a standard cannot be retrofitted to an outcome. And every version is retained and sealed, so loosening your own standard becomes a dated, permanent and public act rather than a quiet edit. The strict rule published in March remains readable in September, next to the loose one that replaced it.",
  "The declaration does not establish that an operator is honest. It converts their claims into something testable, and removes their ability to move the goalposts afterwards."
 ],
 limit:"Weak rules prove weak things. A declaration requiring nothing passes everything — which is precisely why the declaration itself is published rather than merely its pass rate.",
 to:["aitxt","conformance"]
},
{
 id:"aitxt", c:"open", label:"ai.txt & comply.txt", size:1.05,
 lede:"Two small public files letting any organisation declare, machine-readably, how its AI is governed.",
 body:[
  "Modelled on robots.txt and security.txt. <b>ai.txt</b> declares what AI the organisation operates, what decision model governs it, what audit method backs it, which regulations it is designed toward, and where a human override sits. <b>comply.txt</b> is the rulebook every instruction and decision is subject to.",
  "On their own these are claims, not proof — anyone can write \"tamper-evident audit\" in a text file. Their force comes from the third step: sealing the declarations themselves into the chain, so \"this is our governance, as declared on this date\" becomes provable and its history becomes tamper-evident.",
  "Declaration, then rulebook, then enforcement: words, backed by rules, backed by working code, backed by an external clock.",
  "This is the smallest part of the platform by code and potentially the largest by consequence. Conventions of this shape succeed not by enforcement but by becoming the obvious thing to do, and value accrues to the reference implementation that got there first and kept practising it."
 ],
 to:["standard"]
},

/* ================= PROOF LAYER ================= */
{
 id:"completeness", c:"proof", label:"Completeness", size:1.2,
 lede:"Every audit log proves what happened. None of them prove what didn't.",
 body:[
  "A hash chain proves inclusion. It cannot prove exclusion. So when a firm hands an examiner four hundred decisions, nothing in the mathematics shows it was not six hundred. Every audit ever conducted has run on the assumption that the sample handed over is the whole sample. That assumption has never been provable. It has simply been accepted.",
  "At the close of each period, every record sealed in it is taken, <b>sorted</b>, built into a Merkle tree, and the root and the exact count are sealed into the chain — then anchored and witnessed like everything else. Crucially this happens before anybody has asked for anything.",
  "Sorting is the whole trick. In an unsorted tree you can only prove a leaf is present. In a sorted one you can prove a leaf is <b>absent</b>: produce the two leaves either side of where the queried value would have sorted, verify both against the sealed root, and show their indices are consecutive. Nothing can exist between two adjacent leaves of a sorted tree.",
  "<b>Why commitments are frozen.</b> A commitment is worth nothing if it can be recomputed later to suit circumstances. A period can only be committed once it has closed — attempting to commit a live period is refused. It can only be committed once; a second attempt returns the existing root. And the sorted leaf list is stored at commit time rather than recomputed on demand, so proofs issued this year still verify against the root sealed this year even after records are erased next year."
 ],
 routes:[["/x/complete/periods","committed periods"],["/x/complete/prove","request a proof"]],
 limit:"It proves completeness of what was sealed. A decision that never reached the chain is outside anything it can see. What changes is that the operator can no longer choose which of the sealed records to show.",
 to:["absence","erasure"]
},
{
 id:"absence", c:"proof", label:"Absence proofs", size:1.0,
 lede:"Not \"we looked and found nothing\". A proof, against a root fixed before the question was asked.",
 body:[
  "\"We hold no record of you\" is normally a report about the diligence of whoever searched. An absence proof makes it arithmetic: the two neighbouring leaves a missing record would have sorted between, verified against the sealed root, with consecutive indices.",
  "Two commitment types are supported — over the receipts themselves, and over the distinct subjects those records concerned, which is what turns \"do you hold anything about me\" into an answerable question. The tree is built over key material only and never over content, so a leaf reveals whether something exists, not what it said."
 ],
 limit:"Absence is scoped to a period, so \"no record, ever\" means checking every committed period — which is why the period list is public, and why a missing period is itself a visible fact worth asking about. And a proof discloses the two neighbouring keys, so where keys are sensitive they should be hashed before they become leaves.",
 to:[]
},
{
 id:"erasure", c:"proof", label:"Erasure & tombstones", size:1.05,
 lede:"Append-only and the right to erasure look incompatible. Most vendors disclaim it rather than solve it.",
 body:[
  "If nothing can be removed, how is a person's data deleted? And if it can be removed, what was the chain for?",
  "The payload is deleted by the operator's own system. The <b>position</b> in the tree remains, and the erasure is sealed as its own dated event. Holding none of the content, three things can then be established: a record existed, it was erased, and when — against a timestamp nobody involved controls.",
  "So a data subject receives <b>proof of erasure</b> rather than an assurance of it, and the organisation receives evidence it complied which survives the deletion of the very data that would otherwise have been the evidence.",
  "Roots committed before the erasure still contain the leaf, and that is correct rather than a leak. A leaf is key material, not content; and a root that changed after the fact would prove nothing about anything, which would defeat the whole structure."
 ],
 limit:"The tombstone proves the erasure was recorded and cannot have been backdated. It does not prove every copy in every backup and downstream system was destroyed — that is an operational discipline, and no cryptographic structure can reach into systems it does not sit in.",
 to:[]
},
{
 id:"forks", c:"proof", label:"Fork detection", size:1.05,
 lede:"Several parties hold hashes of our chain. Until this, none could check they held hashes of the same chain.",
 body:[
  "Nothing in the design so far stopped an operator running two histories in parallel: serve chain A to a witness, chain B to an auditor. Both receive a valid tip. Both anchor it. Both verify perfectly against the copy they were given. Neither can tell, because there was no way to ask the question that would expose it.",
  "Fork detection is that question, made askable. Hand back any tip we ever gave you and we prove it is still on the chain we serve today, in the same position. A prefix proof between any two sizes shows nothing was inserted, removed or reordered.",
  "That turns a set of separate observers into a single cross-checkable record."
 ],
 routes:[["/x/consistency/ancestor","is my old tip still here"],["/x/consistency/proof","append-only prefix proof"]],
 limit:"A fork is only caught if a holder of an old tip actually checks it. If nobody keeps our tips, there is nothing to catch us with — which is why the route is public, free and automatable.",
 to:[]
},
{
 id:"reproducibility", c:"proof", label:"Reproducibility", size:1.05,
 lede:"A stranger can test that the engine is deterministic without being shown the rules.",
 body:[
  "Determinism is only worth anything if someone outside can test it. Send anything you like to the challenge endpoint, keep the input fingerprint, and send it again next month from anywhere. Every run is sealed. Same inputs, same verdict — or the claim is false and you have the sealed evidence of it.",
  "That is what makes determinism a testable property rather than a design assertion, and it is the difference a competitor building on a model cannot retrofit without rebuilding from the bottom."
 ],
 routes:[["/x/replay/spec","how to test it"]],
 limit:"Reproducibility is not fairness. That the same inputs still produce the same verdict says nothing about whether the verdict was correct or the inputs honestly captured. And an open scoring oracle can be probed: a determined party submitting many varied inputs can map a decision boundary without seeing any code. That exposure is real, mitigated rather than eliminated, and disclosed here rather than discovered later.",
 to:[]
},
{
 id:"lineage", c:"proof", label:"Cross-org lineage", size:1.0,
 lede:"What fed a decision, hop by hop, across company boundaries.",
 body:[
  "Basis sealing records what a decision rested on inside one organisation. Lineage extends the same idea across organisational boundaries, where the source of a decision is another company's decision.",
  "Trace upstream to see what fed an outcome, or run it backwards to see what a faulty input produced. That turns \"which outputs were affected by this bad source\" from a fire drill into a query — and the scope of a recall is itself sealed and dated, so it can be shown not to have been narrowed to suit."
 ],
 routes:[["/x/lineage/trace","trace upstream"],["/x/lineage/impact","run it backwards"]],
 limit:"A lineage edge is a claim, not a proof of the claim. Sealing makes it dated and non-repudiable; it never made it true. Declaring inputs is voluntary, and a party who declares nothing is simply the point at which someone else's trail goes dark. The mechanism is built and the graph is empty until somebody else joins it.",
 to:[]
},
{
 id:"verifier", c:"open", label:"Offline verifier", size:1.1,
 lede:"One file, no dependencies, no network. Check everything with the wifi off.",
 body:[
  "Every claim about the chain is checkable from outside, but checking it through our endpoints still routes through us. The offline verifier removes even that: download it, disconnect, and recompute.",
  "Run <code>--selftest</code> first, so you are not trusting the tool either.",
  "A verifier that needs the vendor's server to reach a verdict is not independent. This one does not — and the evidence therefore outlives both the vendor and its infrastructure."
 ],
 routes:[["/verify","verification tools"]],
 to:["chain","verify-all"]
},
{
 id:"authority-cont", c:"proof", label:"Authority continuity", size:1.15,
 lede:"Proving an autonomous action was derivable from a human grant — every hop re-checked at execution.",
 body:[
  "An agent acted. Something authorised the agent. Something authorised that. Eventually the chain of delegation ends at a person, or it does not end at all — and the second case is the one that matters when someone asks who is answerable.",
  "Continuity re-derives the whole path <b>at the instant of execution</b>, from sealed grants, rather than relying on a claim recorded earlier. The person who accepted the risk is named separately from the issuer and from the subject, so \"who granted this\" and \"who carries it\" are different fields rather than one blurred one.",
  "What comes out is a signed proof bundle a third party verifies on their own machine, with no dependencies and no network — including a <b>proof of refusal</b> when authority could not be derived. A blocked action is evidence in exactly the way an allowed one is.",
  "The rules are published in enough detail to reimplement the evaluator and disagree with our result."
 ],
 routes:[["/x/continuity/spec","the rules"],["/x/continuity/decisions","real decisions, blocks beside allows"],["/x/continuity/trace","the path back to a human"],["/x/continuity/proof","export a signed bundle"]],
 limit:"It proves the authority used was derivable from a human grant — not that the human should have issued it, and not that the parameters describe something that really happened. Grants are authenticated by sealing rather than per-issuer signatures, so an outside party verifies them through the chain rather than entirely offline; signature-based offline verification of grants is a known extension and is not built. And a composed verdict is only half re-derivable: the authority half can be re-run by anyone from the published rules, the risk half needs the scoring engine and cannot be — which the exported bundle states rather than glosses over.",
 to:["authority","verifier"]
},

/* ================= WHOLE / BUSINESS ================= */
{
 id:"stack", c:"business", label:"How it fits together", size:1.25, core:true,
 lede:"Every piece is one layer of a single stack, and evidence accrues as a by-product of the system working.",
 body:[
  "Reading from the bottom up: <b>time</b> — the chain tip fixed in a ledger nobody involved controls. <b>Witness</b> — our tip sealed inside chains we do not own. <b>Evidence</b> — the hash chain, where every layer above seals action plus basis plus a gapless receipt. <b>Proof</b> — completeness, absence, consistency, replay. <b>Lineage</b> — what fed a decision across company boundaries. <b>Authority</b> — every hop back to a human, re-derived at execution.",
  "Above those: <b>public access</b> through the notaries, <b>detection</b> through Sentinel and Guardian, <b>decision</b> through the engine and its packs, <b>delegation</b> establishing who may act and under which rules, the <b>gate</b> checking instructions before the AI acts, and at the top the <b>declaration</b> of what is claimed, publicly and machine-readably.",
  "The flow of a single event: an instruction arrives, Brain checks it against the declared rules, the delegation layer establishes authority, identity and jurisdiction, the engine scores it under the active pack informed by Sentinel's pattern analysis, and the verdict with its reasons, jurisdiction tag, pack version and basis is sealed in the same transaction with a gapless receipt. Upstream receipts are declared as lineage edges. The period is later committed with its exact total. The tip is anchored externally and handed to peer chains. And anyone, at any time, can verify the whole thing from outside without an account.",
  "The principle tying it together: <b>evidence accrues as a by-product of the system working.</b> Nobody remembers to log anything. Nobody compiles an audit file before an inspection. The proof exists because the system ran — and it is exactly as trustworthy whether the operator is honest or not, which is the only kind of trustworthy that counts."
 ],
 to:["chain","witness","sonicboom","notaries","brain","regulation"]
},
{
 id:"regulation", c:"business", label:"Regulation", size:1.15,
 lede:"What this evidences, article by article — and what it does not.",
 body:[
  "The platform maintains a versioned regulation map, itself hash-sealed and served at a public endpoint, linking each capability to the obligations it helps evidence: the EU AI Act's record-keeping, transparency and human-oversight expectations under Articles 9, 12, 13 and 14, the UK Online Safety Act's duty-of-care documentation, and the ICO Children's Code. The map is versioned, so when regulations change, the history of what was mapped when is itself tamper-evident.",
  "<b>The current timeline.</b> The 2026 AI Omnibus amended the AI Act's application dates. The high-risk obligations moved back; the transparency obligations did not, and one deadline was shortened. <b>2 Aug 2026</b> — transparency obligations, deepfake disclosure, Commission enforcement powers over general-purpose models, and the penalty regime. <b>2 Dec 2026</b> — the content-marking grace period ends, cut from six months to three; the prohibition on AI-generated non-consensual intimate imagery and CSAM takes effect. <b>2 Dec 2027</b> — high-risk obligations for stand-alone systems. <b>2 Aug 2028</b> — high-risk obligations for AI embedded in regulated products.",
  "The delay is widely read as breathing room. It is not, for one structural reason: <b>the evidence these articles require is historical.</b> An organisation assessed in 2028 will be asked what its systems decided and why across the preceding period. Records cannot be created retrospectively.",
  "Article by article: <b>12, record-keeping</b> — completeness changes the answer from \"here are our decisions\" to \"here are all 1,204 decisions in this period, and here is the proof there were no others\", with the total fixed before any request arrived. <b>15 and 17, access and erasure</b> — absence proofs make \"we hold no record of you\" provable, and tombstoned erasure gives a data subject proof their record existed and was deleted while holding none of it. <b>9, risk management</b> — the evidence that a defined, versioned ruleset was in force and governed the decisions taken under it. <b>20, corrective action</b> — downstream lineage answers \"which outputs were affected by this faulty input\" as a query rather than a fire drill."
 ],
 limit:"These tools help an organisation evidence its obligations. They do not, on their own, make an organisation compliant, and no software does. Regulators assess organisations, not endpoints. Compliance is an organisational discipline; this is the evidence layer underneath it.",
 to:["pricing","limits"]
},
{
 id:"sovereign", c:"business", label:"Sovereign deployment", size:1.2,
 lede:"The engine runs inside your own network. One file, no dependencies, no phone home.",
 body:[
  "For organisations whose data cannot leave the building, the engine runs entirely on your hardware — decisions, chain and database, all local. Pure Python, a single file, no dependencies. It builds the chain locally, keeps daily backups, verifies itself end to end, and serves the routes the witness network needs.",
  "Licensing is offline by design: signed 365-day tokens validated with pure cryptography, no phone-home, suitable for air-gapped environments.",
  "It is the only component that runs somewhere we cannot reach, and that is the point of it. The sovereignty claim is about the engine, not just about where the data sits."
 ],
 to:["pricing","witness"]
},
{
 id:"pricing", c:"business", label:"Deployment & pricing", size:1.1,
 lede:"50p per active device per month. The proof layer is free and structurally has to be.",
 body:[
  "Two ways to run: integrate against the hosted API — a few lines of code where your system makes decisions — or run it sovereign inside your own network. Pricing is deliberately simple: <b>50p per active device per month</b>, metered on real usage, billed automatically. Partners embedding the platform set their own customer pricing and keep the margin above the platform fee.",
  "<b>The witnessing network is free and structurally cannot be otherwise.</b> There is no gate to price: the submission endpoint takes a tip from anybody, and that openness is the mechanism by which the collusion objection is answered. A witness you must ask permission from is a weaker witness. Charging for admission would damage the thing being sold.",
  "Two commitments follow, and they are architectural rather than promises. <b>The open protocol code never checks whether anyone has paid</b> — it has no concept of a subscription, so the claim that it is ungated is true by construction rather than by policy. And each paid service checks only its own status, so an operator who stops paying for hosting but runs their own infrastructure keeps sealing and keeps being witnessed indefinitely, with no gap in their record.",
  "Evidence packs are issued periodically: a customer's record for the period, with every seal, its witnesses, its anchors and the routes to verify each, as a document they own outright and may hand to anyone. Non-payment removes nothing — sealed history cannot be withdrawn without breaking the chain, and is not. But coverage stops, and the gap that opens cannot be filled in later at any price, because the only way to have had a period covered was to be covered during it."
 ],
 to:["partner"]
},
{
 id:"partner", c:"business", label:"The raise", size:1.3, core:true,
 lede:"30% of the business for an operating partner who can take this into defence, healthcare and telecoms.",
 body:[
  "Built and operated by a solo founder at near-zero fixed cost. The platform is live. The constraint is not engineering.",
  "<b>What is offered.</b> A substantial equity stake — up to 30% — for a partner who can open regulated enterprise and government channels. Defence, healthcare, telecommunications: sectors where evidence obligations are hardest, procurement cycles run eighteen months, and a founder alone does not get in the room. Mass rollout through resellers who set their own pricing and keep the margin above the platform fee.",
  "<b>Why the economics suit that shape.</b> Marginal cost per additional device is effectively zero; the same engine serves one customer or ten thousand. Distribution scales without headcount. A reseller channel is therefore pure margin expansion rather than a cost line, and the sovereign engine means a customer whose data cannot leave the building is not an exception to the model but an ordinary sale.",
  "<b>The market moment.</b> Three regimes converge: the EU AI Act's transparency obligations and full penalty regime from August 2026, with high-risk obligations in December 2027 and August 2028; the UK Online Safety Act; and the 2024 Payment Services reimbursement rules. All share one practical demand — records that survive scrutiny. Most organisations meet it with editable database logs, which is to say they do not meet it.",
  "<b>The moat is time.</b> Switching costs rise every day a customer's evidence accrues, because an anchored history cannot be migrated mid-stream without breaking its own continuity. An unbroken witnessed record is the one input nobody can shortcut, because the only way to have had last year covered was to be in it last year. A competitor building governance on a model cannot offer reproducibility and cannot retrofit it without rebuilding from the bottom. And least copyable: every competitor overclaims. A documented refusal to — limits stated on every page and sealed into the platform's own chain — is precisely the property a buyer of evidence infrastructure is buying.",
  "<b>Stated plainly.</b> Pre-revenue, with a 90-day free trial converting to metered billing. The pipeline is founder-led outreach and inbound from the free tools. Commercial terms with the peers on the roster have not been discussed — they joined an open network, not a company, and that is deliberate. The market's deadlines move; the structural argument does not.",
  "<b>Contact:</b> justin@monopcontent.com — the technical demonstration takes fifteen minutes, and every claim on this map can be verified during it."
 ],
 routes:[["/whitepaper","the full whitepaper"]],
 to:["sovereign","limits","standard"]
},
{
 id:"future", c:"business", label:"Future potential", size:1.0,
 lede:"Forward-looking, and separated for exactly that reason. None of this is deployed.",
 body:[
  "<b>What has already moved out of this section.</b> Mutual anchoring was a future direction in v4; it shipped. Completeness, absence, erasure proofs, fork detection, reproducibility testing and cross-organisation lineage were unwritten in v5 and all six shipped within two days of it. They are listed only so readers of earlier versions can see what moved from intention to deployment, and when.",
  "<b>Key-signed intermittent sync — designed, not built.</b> The witnessing spec currently assumes both parties run always-on servers, because the first two chains happened to. That assumption is not required by the design and excludes exactly the systems most in need of it: edge deployments, off-grid nodes, anything with intermittent connectivity. A node would register a public key once and sign every tip thereafter, pushing in batches whenever it reaches a network, pulling the peer's tip first and sealing it — so offline work is bounded at both ends. The residual limit is inherent: bounding is only as tight as the sync frequency.",
  "<b>Signal Packs as a market.</b> A pack is a versioned, hashable, portable artefact, which means it can be authored by someone other than us. A fraud consultancy, a child-safety charity or a regulator could publish a pack, and any operator could load it and prove which version they ran. A sector body would gain something it has never had: a way to publish a standard that adopters can prove they actually applied, rather than a PDF everyone claims to have read.",
  "<b>Evidence-priced risk.</b> Insurers price uncertainty, today through questionnaires and periodic audit. An anchored, reproducible decision history is a different class of input: continuous, externally verifiable, impossible to dress up before an inspection. It is reasonable to expect verifiable evidence to eventually attract better pricing than asserted evidence. That is a hypothesis about a market, not a product feature.",
  "<b>What would have to be true.</b> A wide witness network requires peers willing to coordinate. Cross-organisation lineage requires a second organisation actually declaring its inputs. A pack market requires authors with reputations worth attaching. Evidence-priced risk requires an underwriter prepared to move first. Each is plausible; none is in hand. <b>The parts of this platform that exist do not depend on any of them</b> — which is the property that makes it responsible to write this section at all."
 ],
 to:["standard","packs"]
},
{
 id:"standard", c:"business", label:"The standard", size:1.0,
 lede:"The smallest part by code, potentially the largest by consequence.",
 body:[
  "Conventions of this shape — robots.txt, security.txt — succeed not by enforcement but by becoming the obvious thing to do, and value accrues to the reference implementation that got there first and kept practising it.",
  "The adoption path is deliberately staged. <b>Technical</b>: the tools work and anyone can check. <b>Network</b>: enough operators declare and anchor that checking becomes routine. <b>Expectation</b>: an organisation without a declaration and a verifiable history looks like one with something to hide.",
  "Nothing about that sequence is guaranteed. It is, however, the reason the standard is open and the notaries are free."
 ],
 to:["aitxt"]
},

/* ================= SCRUTINY ================= */
{
 id:"conformance", c:"business", label:"Conformance", size:1.1,
 lede:"Three claims here have a soft edge. Rather than hide them, they are measured.",
 body:[
  "Commit-before-reveal proves ordering, but only if the integrator does not show reviewers the verdict first. Witnessing draws strength from breadth, and two platforms witnessing only each other prove very little. A declaration is only as strong as the rules declared.",
  "None of these can be closed by the engine alone, and a vendor claiming otherwise would be overstating what software can do. What they can be is <b>measured</b> — and a measured weakness is a different object from an unmeasured one. It can be reported, tracked, compared between deployments and put in front of an auditor.",
  "<b>Breadth.</b> The network reports how many distinct peers are live, how concentrated observations are in the largest of them, and how many have gone quiet. Fewer than three live peers is reported as weak, because it is. A single peer pair carries an explicit warning that two parties witnessing only each other can still collude. None of this prevents a thin network. It prevents a thin network being presented as a thick one.",
  "<b>Strength.</b> Each rule in a live declaration is run against sealed records and reported individually: how many records it actually constrained. A rule that has never constrained a single record is named in the output as decoration rather than a standard. An operator can still publish a weak declaration. They can no longer publish one and have its weakness go unstated."
 ],
 limit:"None of this is enforcement. Nothing here compels a platform to witness widely, declare strictly or integrate honestly. It makes the alternative visible, which is the most an evidence layer can honestly claim to do.",
 to:["probes","limits"]
},
{
 id:"probes", c:"business", label:"Probes", size:1.0,
 lede:"Put a case with a known answer into the queue, unannounced, and see who catches it.",
 body:[
  "The method is borrowed openly from how substantive audit has always worked, and specifically from a point made publicly by James Stokes of Red Flag AI Pro.",
  "A probe creates a genuine oversight case whose machine verdict has been deliberately set to a known-wrong value. To the reviewer it is indistinguishable from any other case. Two things follow. If the reviewer agrees with the planted verdict, they did not evaluate the case — a caught rubber stamp, sealed like any other event. And if the integration is displaying the verdict before the case is opened, the reviewer's agreement rate on probes will track their rate on ordinary cases; if they are genuinely deciding blind, it will not.",
  "<b>The gap between those two numbers is the conformance signal</b>, and it is the closest thing available to testing an integration you cannot see inside. A single probe establishes nothing about an individual. A catch rate across dozens is evidence about a process, and the process is what is under audit."
 ],
 limit:"Probes test a process, not a person: someone can catch a probe and rubber-stamp the next hundred cases. A sufficiently motivated operator who identifies probe cases controls their own interface and can treat them differently — probe references carry no marking a reviewer can see, but that is a speed bump rather than a wall.",
 to:["oversight"]
},
{
 id:"limits", c:"business", label:"Honest limits", size:1.3, core:true,
 lede:"A whitepaper that only lists strengths is marketing. These are the limits, as plainly as the capabilities.",
 body:[
  "<b>Sealing proves integrity and timing, not truth at capture.</b> A sealed, anchored record proves exact content existed no later than an externally witnessed moment and has not changed since. It does not prove the contents were true when written — and no recording system of any kind does, which is a fact about recording rather than a defect of this one.",
  "<b>Determinism costs cleverness.</b> The gate has no semantic understanding and will miss things a good classifier would catch. Deliberate and permanent.",
  "<b>Basis sealing proves what was relied on, not that it was right.</b> Whether the source was genuine is a matter for process, not cryptography.",
  "<b>Packs prove which rules ran, not that they were the right rules.</b> The nine core signals are transaction-risk signals and are not a risk taxonomy for Article 9.",
  "<b>Authority tokens prove the grant, not the wisdom.</b> Jurisdiction tagging records applicable frameworks; it does not decide law.",
  "<b>Anchoring inherits Bitcoin's assumptions</b>, and submitted is not confirmed.",
  "<b>Oversight sealing proves order, not thought</b> — and depends entirely on the integration honouring it.",
  "<b>Witnessing proves a tip existed, not that its contents are true.</b> Strength comes from breadth, and no design can compel a peer to keep publishing.",
  "<b>Reconciliation proves consistency, not truth.</b> Declarations are only as strong as the rules declared.",
  "<b>Fork detection needs someone to look.</b> Reproducibility is not fairness. A lineage edge is a claim, not proof of the claim.",
  "<b>None of these find what was never recorded.</b> A decision that was never sent to the engine cannot violate a rule or fail a sample. Gapless receipts cover omission at the point of issue; nothing covers a system that was never connected.",
  "<b>And none of this prevents anything.</b> The layer produces evidence that something happened and has not been altered. A sealed record of a harmful action is still a harmful action. What changes is that afterwards there is an answer to what happened and who authorised it — which today, in most systems, there is not.",
  "Every one of these limits is stated on the product pages as well. A system whose whole value is honesty cannot afford a single overclaim — and a vendor who tells you their limits is giving you the strongest evidence available about how they will behave when it matters."
 ],
 to:["verify-all"]
},
{
 id:"verify-all", c:"open", label:"Check us, don't trust us", size:1.25, core:true,
 lede:"Nothing here asks to be believed. Every claim is checkable from outside, now, without an account.",
 body:[
  "<b>Verify the whole chain</b> — the public endpoint recomputes every seal from genesis and reports either integrity or the exact block where tampering begins.",
  "<b>Check the anchor</b> — the live endpoint returns the tip, the OpenTimestamps proof file and how many independent calendars have stamped it. Verify it against Bitcoin with any OpenTimestamps client. Nothing about that check involves us.",
  "<b>Check any receipt</b>, <b>re-derive a decision</b> from the sealed inputs and pack version, and <b>test reproducibility with your own inputs</b> — send anything, keep the fingerprint, send it again next month from anywhere.",
  "<b>Ask what a period contained</b>, <b>ask about something that isn't there</b> and receive an absence proof, <b>check we never forked</b> by handing back any tip we ever gave you, and <b>check the log is append-only</b> with a prefix proof between any two sizes.",
  "<b>Follow a decision across companies</b>, <b>read the authority rules</b> in enough detail to reimplement the evaluator and disagree with our result, and <b>export a signed proof and check it without us</b> — with no identifier it returns the most recent, so you can start knowing nothing.",
  "<b>Run the offline verifier</b> with the wifi off, and run its selftest first so you are not trusting the tool either. <b>Seal something yourself</b> with the notaries, then change one character and watch verification fail. <b>Read the gate's code</b> before running it.",
  "<b>Ask who witnessed us</b>, and <b>witness us yourself</b> — take our tip and seal it wherever you like. No account, no key, no permission. We have no way to know you are doing it, which is the point.",
  "<b>Check a reviewer's record</b> — median dwell time, divergence rate, and the proportion of sub-two-second decisions. A reviewer who has never once diverged is reported as such. And <b>read our declaration and its history</b>: if we have ever loosened our own standard, it is there.",
  "That is not a slogan. It is the system's design requirement, and the only standard by which an evidence layer should ever be judged."
 ],
 routes:[["/verify","start here"],["/x/roster/list","the roster"],["/x/ots/status","anchor state"],["/x/peer/schema","the schema"]],
 to:["verifier","refusals"]
}
]

/* ============================================================
   GRAPH
   ============================================================ */
const byId = {}; N.forEach(n=>byId[n.id]=n);
const E = [];
const seen = new Set();
N.forEach(n => (n.to||[]).forEach(t=>{
  if(!byId[t]) return;
  const k = [n.id,t].sort().join("|");
  if(seen.has(k)) return; seen.add(k);
  E.push({a:n, b:byId[t]});
}));

const cv = document.getElementById("c"), ctx = cv.getContext("2d");
let W=0,H=0,DPR=1;
let cam={x:0,y:0,z:1}, tgt={x:0,y:0,z:1};
let active=null, hover=null, filter=null, query="";
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

function resize(){
  DPR = Math.min(devicePixelRatio||1, 2);
  W = cv.clientWidth; H = cv.clientHeight;
  cv.width = W*DPR; cv.height = H*DPR;
  ctx.setTransform(DPR,0,0,DPR,0,0);
}
addEventListener("resize", resize);

// seed positions by cluster ring
const order = Object.keys(CLUSTERS);
N.forEach((n,i)=>{
  const ci = order.indexOf(n.c);
  const ang = (i/N.length)*Math.PI*2 + ci;
  const r = 150 + ci*95 + (i%4)*22;
  n.x = Math.cos(ang)*r; n.y = Math.sin(ang)*r*0.82;
  n.vx = 0; n.vy = 0;
  n.r = 15*(n.size||1) * (n.core?1.22:1);
  n.a = 0; // reveal alpha
});

function physics(){
  for(let i=0;i<N.length;i++){
    const a=N[i];
    for(let j=i+1;j<N.length;j++){
      const b=N[j];
      let dx=b.x-a.x, dy=b.y-a.y;
      let d2=dx*dx+dy*dy; if(d2<1) d2=1;
      const d=Math.sqrt(d2);
      const min=(a.r+b.r)*3.35;
      const f = (d<min ? 2600/d2 : 900/d2);
      const ux=dx/d, uy=dy/d;
      a.vx-=ux*f; a.vy-=uy*f; b.vx+=ux*f; b.vy+=uy*f;
    }
  }
  E.forEach(e=>{
    const dx=e.b.x-e.a.x, dy=e.b.y-e.a.y;
    const d=Math.hypot(dx,dy)||1;
    const rest=205;
    const f=(d-rest)*0.0055;
    const ux=dx/d, uy=dy/d;
    e.a.vx+=ux*f; e.a.vy+=uy*f; e.b.vx-=ux*f; e.b.vy-=uy*f;
  });
  N.forEach(n=>{
    n.vx -= n.x*0.0016; n.vy -= n.y*0.0022;
    n.vx*=0.86; n.vy*=0.86;
    n.x+=n.vx; n.y+=n.vy;
  });
}
for(let i=0;i<420;i++) physics();

/* ---------- ember field ---------- */
// drifting dust
const DUST=[]; for(let i=0;i<260;i++) DUST.push({x:Math.random(),y:Math.random(),s:Math.random()*1.3+.25,p:Math.random()*6.28,v:Math.random()*.00006+.00002});
// per-node particle cloud — precomputed, cheap to draw
N.forEach(n=>{
  const count = Math.round(16 + n.r*1.5);
  n.pts=[];
  for(let i=0;i<count;i++){
    const a=Math.random()*6.283;
    const rr=Math.pow(Math.random(),.55);
    n.pts.push({a, rr, s:Math.random()*1.5+.4, ph:Math.random()*6.28, sp:.12+Math.random()*.3});
  }
});
// filament jitter seeds per edge
E.forEach((e,i)=>{ e.seed=i*13.37; e.bow=(Math.random()-.5)*46; });

function visible(n){
  if(filter && n.c!==filter) return false;
  if(query){
    const hay=(n.label+" "+n.lede+" "+n.body.join(" ")).toLowerCase();
    if(!hay.includes(query)) return false;
  }
  return true;
}

function filament(e,lit,dim,t){
  const mx=(e.a.x+e.b.x)/2, my=(e.a.y+e.b.y)/2;
  const dx=e.b.x-e.a.x, dy=e.b.y-e.a.y, L=Math.hypot(dx,dy)||1;
  const nx=-dy/L, ny=dx/L;
  const threads = lit?4:2;
  for(let k=0;k<threads;k++){
    const off=(k-(threads-1)/2)*2.4;
    const bow=e.bow*0.35+off*3;
    ctx.beginPath();
    ctx.moveTo(e.a.x,e.a.y);
    ctx.quadraticCurveTo(mx+nx*bow, my+ny*bow, e.b.x,e.b.y);
    ctx.strokeStyle = lit ? "#ff9d3c" : "#6b4a2a";
    ctx.globalAlpha = dim ? 0.04 : (lit ? 0.24 - k*0.04 : 0.13 - k*0.045);
    ctx.lineWidth = lit ? 1.1 : 0.7;
    ctx.stroke();
  }
  if(lit && !reduced){
    for(let k=0;k<3;k++){
      const p=((t*0.28 + k/3)%1);
      const q=1-p;
      const x=q*q*e.a.x + 2*q*p*(mx+nx*e.bow*0.35) + p*p*e.b.x;
      const y=q*q*e.a.y + 2*q*p*(my+ny*e.bow*0.35) + p*p*e.b.y;
      ctx.globalAlpha=0.85-k*0.22; ctx.fillStyle="#ffd08a";
      ctx.fillRect(x-1.1,y-1.1,2.2,2.2);
    }
  }
}

let t0=performance.now();
function draw(now){
  const t=(now-t0)/1000;
  cam.x += (tgt.x-cam.x)*0.12;
  cam.y += (tgt.y-cam.y)*0.12;
  cam.z += (tgt.z-cam.z)*0.12;

  // ---- background: warm void, low horizon glow ----
  ctx.globalAlpha=1;
  ctx.fillStyle="#07050a"; ctx.fillRect(0,0,W,H);
  const g=ctx.createRadialGradient(W*0.42,H*0.62,0,W*0.42,H*0.62,Math.max(W,H)*0.9);
  g.addColorStop(0,"#22140e"); g.addColorStop(0.45,"#120b0c"); g.addColorStop(1,"#07050a");
  ctx.fillStyle=g; ctx.fillRect(0,0,W,H);

  // dust
  DUST.forEach(d=>{
    if(!reduced) d.x += d.v; if(d.x>1) d.x-=1;
    const tw = reduced?0.4:(0.25+0.3*Math.sin(t*0.8+d.p));
    ctx.globalAlpha=tw*0.5; ctx.fillStyle="#c9a06a";
    ctx.fillRect(d.x*W, d.y*H, d.s, d.s);
  });

  // scanline grain
  ctx.globalAlpha=0.035; ctx.fillStyle="#000";
  for(let y=0;y<H;y+=3) ctx.fillRect(0,y,W,1);
  ctx.globalAlpha=1;

  ctx.save();
  ctx.translate(W/2+cam.x, H/2+cam.y); ctx.scale(cam.z,cam.z);

  const neigh=new Set();
  if(active) E.forEach(e=>{ if(e.a===active) neigh.add(e.b); if(e.b===active) neigh.add(e.a); });

  // ---- filaments ----
  E.forEach(e=>{
    const va=visible(e.a), vb=visible(e.b);
    const dim=(query||filter)&&!(va&&vb);
    const lit=active&&(e.a===active||e.b===active);
    filament(e,lit,dim,t);
  });
  ctx.globalAlpha=1;

  // ---- nodes as ember clusters ----
  N.forEach(n=>{
    const vis=visible(n);
    n.a += ((vis?1:0.1)-n.a)*0.15;
    if(n.a<0.02) return;
    const col=CLUSTERS[n.c].col;
    const isA=n===active, isN=neigh.has(n), isH=n===hover;
    const hot=isA||isH;
    const r=n.r*(n.core&&!reduced ? 1+0.04*Math.sin(t*1.4+n.x*0.01) : 1);

    // bloom
    ctx.globalAlpha=n.a*(hot?0.85:(isN?0.5:0.32));
    const rg=ctx.createRadialGradient(n.x,n.y,0,n.x,n.y,r*(hot?4.2:2.9));
    rg.addColorStop(0,col+(hot?"88":"55"));
    rg.addColorStop(0.35,col+"22");
    rg.addColorStop(1,col+"00");
    ctx.fillStyle=rg;
    ctx.beginPath(); ctx.arc(n.x,n.y,r*(hot?4.2:2.9),0,6.29); ctx.fill();

    // particle cloud
    const spin = reduced?0:t*0.08;
    ctx.globalAlpha=n.a*(hot?1:(isN?0.8:0.55));
    ctx.fillStyle=col;
    for(const q of n.pts){
      const ang=q.a+spin*q.sp;
      const rad=r*(0.55+q.rr*1.85)+(reduced?0:Math.sin(t*q.sp*3+q.ph)*1.6);
      ctx.fillRect(n.x+Math.cos(ang)*rad, n.y+Math.sin(ang)*rad*0.92, q.s, q.s);
    }

    // hot core
    ctx.globalAlpha=n.a;
    ctx.beginPath(); ctx.arc(n.x,n.y,r*0.44,0,6.29);
    ctx.fillStyle=hot?"#fff6e2":col; ctx.fill();
    ctx.beginPath(); ctx.arc(n.x,n.y,r*0.44,0,6.29);
    ctx.strokeStyle=col; ctx.lineWidth=hot?1.6:1; ctx.globalAlpha=n.a*0.9; ctx.stroke();

    // live tick
    if(n.live){
      ctx.globalAlpha=n.a;
      ctx.fillStyle=n._liveOk===false?"#b8624a":(n._liveOk?"#8fe3a8":"#6d6355");
      ctx.fillRect(n.x+r*0.95, n.y-r*1.05, 3, 3);
    }

    // label — mono, upper, tracked
    ctx.globalAlpha=n.a*(hot||isN||cam.z>0.7?1:0.5);
    ctx.font="600 10px ui-monospace,Menlo,monospace";
    ctx.textAlign="center"; ctx.textBaseline="top";
    const lab=n.label.toUpperCase();
    ctx.fillStyle="#0a0709"; ctx.globalAlpha=n.a*0.55;
    ctx.fillText(lab, n.x+0.6, n.y+r*2.05+0.6);
    ctx.globalAlpha=n.a*(hot||isN||cam.z>0.7?1:0.5);
    ctx.fillStyle=hot?"#fff2dc":"#cbbfa9";
    ctx.fillText(lab, n.x, n.y+r*2.05);
  });

  ctx.globalAlpha=1;
  ctx.restore();

  // vignette
  const vg=ctx.createRadialGradient(W/2,H/2,Math.min(W,H)*0.42,W/2,H/2,Math.max(W,H)*0.78);
  vg.addColorStop(0,"rgba(0,0,0,0)"); vg.addColorStop(1,"rgba(0,0,0,.62)");
  ctx.fillStyle=vg; ctx.fillRect(0,0,W,H);

  requestAnimationFrame(draw);
}

/* ---------- interaction ---------- */
function toWorld(px,py){
  return { x:(px-W/2-cam.x)/cam.z, y:(py-H/2-cam.y)/cam.z };
}
function hit(px,py){
  const p=toWorld(px,py);
  let best=null,bd=1e9;
  N.forEach(n=>{
    if(!visible(n)) return;
    const d=Math.hypot(n.x-p.x,n.y-p.y);
    if(d<n.r+13 && d<bd){bd=d;best=n;}
  });
  return best;
}
let drag=false, moved=0, lx=0, ly=0, pinch=0;
cv.addEventListener("pointerdown",e=>{
  drag=true; moved=0; lx=e.clientX; ly=e.clientY; cv.classList.add("drag");
  cv.setPointerCapture(e.pointerId);
});
cv.addEventListener("pointermove",e=>{
  if(drag){
    const dx=e.clientX-lx, dy=e.clientY-ly;
    moved+=Math.abs(dx)+Math.abs(dy);
    tgt.x+=dx; tgt.y+=dy; cam.x+=dx; cam.y+=dy;
    lx=e.clientX; ly=e.clientY;
  } else {
    const h=hit(e.clientX,e.clientY);
    hover=h; cv.style.cursor=h?"pointer":"grab";
  }
});
cv.addEventListener("pointerup",e=>{
  drag=false; cv.classList.remove("drag");
  if(moved<8){
    const h=hit(e.clientX,e.clientY);
    if(h) open(h); else close();
  }
});
cv.addEventListener("wheel",e=>{
  e.preventDefault();
  tgt.z = Math.min(2.4, Math.max(0.35, tgt.z * (e.deltaY>0?0.9:1.11)));
},{passive:false});

// pinch
let pts=new Map();
cv.addEventListener("pointerdown",e=>pts.set(e.pointerId,e));
cv.addEventListener("pointermove",e=>{
  if(!pts.has(e.pointerId)) return;
  pts.set(e.pointerId,e);
  if(pts.size===2){
    const [a,b]=[...pts.values()];
    const d=Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);
    if(pinch) tgt.z=Math.min(2.4,Math.max(0.35,tgt.z*(d/pinch)));
    pinch=d; drag=false;
  }
});
["pointerup","pointercancel"].forEach(ev=>cv.addEventListener(ev,e=>{pts.delete(e.pointerId); if(pts.size<2) pinch=0;}));

/* ---------- panel ---------- */
const panel=document.getElementById("panel");
function esc(s){return s;}
function open(n){
  active=n;
  document.getElementById("pcluster").textContent=CLUSTERS[n.c].name;
  document.getElementById("pcluster").style.color=CLUSTERS[n.c].col;
  document.getElementById("ptitle").textContent=n.label;
  document.getElementById("plede").textContent=n.lede;

  let h="";
  if(n.live){
    const L=LIVE[n.live];
    h+=`<div class="live"><div class="lbl">live from ${L.url}</div><div class="val pending" id="lv">fetching…</div></div>`;
  }
  n.body.forEach(p=>h+=`<p>${p}</p>`);
  if(n.limit) h+=`<div class="limit"><div class="lbl">honest limit</div><p>${n.limit}</p></div>`;
  if(n.routes&&n.routes.length){
    h+=`<h3>Check it yourself</h3><div class="routes">`;
    n.routes.forEach(([u,t])=>h+=`<a href="${BASE}${u}" target="_blank" rel="noopener">${u}<span>${t}</span></a>`);
    h+=`</div>`;
  }
  const rel=[...new Set([...(n.to||[]), ...E.filter(e=>e.b===n).map(e=>e.a.id)])].filter(x=>byId[x]);
  if(rel.length){
    h+=`<h3>Connected</h3><div class="links">`;
    rel.forEach(id=>h+=`<button data-go="${id}">${byId[id].label}</button>`);
    h+=`</div>`;
  }
  const pb=document.getElementById("pbody");
  pb.innerHTML=h; pb.scrollTop=0;
  pb.querySelectorAll("[data-go]").forEach(b=>b.onclick=()=>{ open(byId[b.dataset.go]); centre(byId[b.dataset.go]); });
  panel.classList.add("open");
  centre(n);
  if(n.live) fillLive(n);
}
function centre(n){
  const wide = innerWidth>760;
  tgt.x = -n.x*tgt.z + (wide? -215 : 0);
  tgt.y = -n.y*tgt.z + (wide? 0 : -H*0.16);
}
function close(){ active=null; panel.classList.remove("open"); }
document.getElementById("close").onclick=close;
addEventListener("keydown",e=>{ if(e.key==="Escape") close(); });

/* ---------- live data ---------- */
const cache={};
async function fetchLive(key){
  if(cache[key]) return cache[key];
  const L=LIVE[key];
  const p=(async()=>{
    const r=await fetch(BASE+L.url,{headers:{accept:"application/json"}});
    if(!r.ok) throw new Error("HTTP "+r.status);
    return L.render(await r.json());
  })();
  cache[key]=p; return p;
}
async function fillLive(n){
  const el=document.getElementById("lv"); if(!el) return;
  try{
    const v=await fetchLive(n.live);
    if(document.getElementById("lv")===el){ el.textContent=v; el.className="val"; }
    n._liveOk=true;
  }catch(err){
    if(document.getElementById("lv")===el){
      el.textContent="not reachable from here — open the route directly";
      el.className="val fail";
    }
    n._liveOk=false;
  }
}
// warm the routes: colour the node ticks and fill the instrument row
function hudSet(key,txt,cls){
  const el=document.querySelector('[data-hud="'+key+'"]');
  if(el){ el.textContent=txt; el.className="v"+(cls?" "+cls:""); }
}
Object.keys(LIVE).forEach(k=>{
  const L=LIVE[k];
  fetch(BASE+L.url,{headers:{accept:"application/json"}})
    .then(r=>{ if(!r.ok) throw 0; return r.json(); })
    .then(d=>{
      cache[k]=Promise.resolve(L.render(d));
      N.forEach(n=>{ if(n.live===k) n._liveOk=true; });
      if(L.hud) hudSet(k, L.hud(d));
    })
    .catch(()=>{
      N.forEach(n=>{ if(n.live===k) n._liveOk=false; });
      if(L.hud) hudSet(k,"offline","fail");
    });
});

/* ---------- chips & search ---------- */
const chips=document.getElementById("chips");
Object.entries(CLUSTERS).forEach(([k,v])=>{
  const b=document.createElement("button");
  b.className="chip"; b.textContent=v.name; b.dataset.k=k; b.dataset.on="0";
  b.onclick=()=>{
    filter=(filter===k)?null:k;
    [...chips.children].forEach(c=>{
      const on=c.dataset.k===filter;
      c.dataset.on=on?"1":"0";
      c.style.background = on?CLUSTERS[c.dataset.k].col:"transparent";
      c.style.color = on?"#0b0709":"";
    });
  };
  chips.appendChild(b);
});
document.getElementById("q").addEventListener("input",e=>{ query=e.target.value.trim().toLowerCase(); });
document.getElementById("reset").onclick=()=>{
  tgt={x:0,y:0,z: innerWidth<520?0.62:0.92}; close();
  query=""; document.getElementById("q").value="";
  filter=null; [...chips.children].forEach(c=>{c.dataset.on="0";c.style.background="transparent";c.style.color="";});
};

/* ---------- boot ---------- */
resize();
tgt.z = innerWidth<520?0.62:0.92; cam.z=tgt.z*0.75;
requestAnimationFrame(draw);
setInterval(()=>{ if(!drag) physics(); }, 90);

const toast=document.getElementById("toast");
function say(m){ toast.textContent=m; toast.classList.add("show"); setTimeout(()=>toast.classList.remove("show"),3400); }
document.getElementById("hudn").textContent = N.length;
setTimeout(()=>say("Start anywhere — try THE HASH CHAIN"),900);
</script>
</body>
</html>

```
