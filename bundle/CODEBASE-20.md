# Codebase — part 20 of 20

Contains:
- `whitepaper.html`


## `whitepaper.html`

541 lines, 100517 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The sebbi.pro System — the deterministic evidence layer for AI</title>
<meta name="description" content="A plain-English systems whitepaper: the deterministic gatekeeper, the tamper-evident chain, Bitcoin anchoring, mutual witnessing, completeness and absence proofs, fork detection, reproducibility, cross-organisation lineage, Signal Packs, basis sealing, SonicBoom, Sentinel, Guardian, the Notaries, Brain, ai.txt — one evidence layer, and where it goes next.">
<style>
  :root{
    --ink:#0a0f1e;--ink2:#111a30;--line:#232d4a;--line2:#2a3350;
    --gold:#c9a84c;--gold-dim:#8a7838;--ok:#7fe3b0;--block:#ff8a80;--cyan:#7cc8ff;
    --text:#e8e8f0;--muted:#c2c8dc;--faint:#5a6178;--code-bg:#0b1226;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--ink);color:#fff;line-height:1.7;-webkit-font-smoothing:antialiased}
  .wrap{max-width:720px;margin:0 auto;padding:26px 20px 90px}
  a.back{color:var(--gold);text-decoration:none;font-size:13px;font-family:ui-monospace,Menlo,monospace;letter-spacing:.5px}
  .eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;letter-spacing:2px;text-transform:uppercase;color:var(--gold-dim);margin:22px 0 10px}
  h1{font-size:32px;font-weight:800;letter-spacing:-1px;margin-bottom:10px;line-height:1.15}
  h1 span{color:var(--gold)}
  .lead{font-size:16.5px;color:var(--text);margin-bottom:6px}
  .sub{font-size:14px;color:var(--faint);margin-bottom:26px}

  h2{font-size:20px;font-weight:800;margin:44px 0 6px;letter-spacing:-.3px}
  h2 .n{color:var(--gold);font-family:ui-monospace,Menlo,monospace;font-size:14px;margin-right:8px}
  h3{font-size:15px;font-weight:700;color:var(--gold);margin:24px 0 8px}
  p{font-size:15px;color:var(--muted);margin-bottom:14px}
  p b{color:#fff}
  ul{margin:0 0 14px 0;list-style:none}
  li{position:relative;padding-left:20px;margin-bottom:9px;font-size:14.5px;color:var(--muted)}
  li::before{content:'';position:absolute;left:0;top:9px;width:6px;height:6px;border-radius:50%;background:var(--gold)}
  li b{color:#fff}
  code{background:var(--code-bg);border:1px solid var(--line2);border-radius:5px;padding:2px 7px;font-size:13px;color:var(--ok);font-family:ui-monospace,Menlo,monospace}
  pre{background:var(--code-bg);border:1px solid var(--line2);border-radius:10px;padding:15px;font-size:12.5px;color:var(--muted);overflow-x:auto;margin:14px 0;font-family:ui-monospace,Menlo,monospace;line-height:1.8}
  pre b{color:var(--ok);font-weight:400}pre i{color:var(--gold);font-style:normal}

  .box{background:var(--ink2);border:1px solid var(--line);border-radius:14px;padding:20px;margin:16px 0}
  .box .t{font-family:ui-monospace,Menlo,monospace;font-size:10.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--gold);margin-bottom:12px}
  .honest{border:1px solid rgba(201,168,76,.35);background:rgba(201,168,76,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .honest b{color:var(--gold)}
  .proves{background:rgba(127,227,176,.05);border:1px solid rgba(127,227,176,.3);border-radius:12px;padding:16px 20px;margin:16px 0}
  .proves .t{font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--ok);margin-bottom:10px}
  .proves p{font-size:13.5px;margin-bottom:8px}
  .fwd{border:1px dashed rgba(124,200,255,.45);background:rgba(124,200,255,.05);border-radius:12px;padding:16px 20px;margin:16px 0;font-size:13.5px;color:var(--muted);line-height:1.75}
  .fwd b{color:var(--cyan)}
  .stack{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;line-height:2;color:var(--muted);background:var(--code-bg);border:1px solid var(--line2);border-radius:10px;padding:16px;margin:14px 0;overflow-x:auto;white-space:pre}
  .stack em{color:var(--gold);font-style:normal}
  .stack s{color:var(--ok);text-decoration:none}
  .toc{background:var(--ink2);border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin:20px 0;font-size:13.5px}
  .toc a{display:block;color:var(--muted);text-decoration:none;padding:3px 0}
  .toc a:hover{color:var(--gold)}
  .toc .n{color:var(--gold);font-family:ui-monospace,Menlo,monospace;margin-right:8px;font-size:12px}
  .toc .grp{font-family:ui-monospace,Menlo,monospace;font-size:9.5px;letter-spacing:1.5px;text-transform:uppercase;color:var(--faint);margin:12px 0 4px}
  .tl{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:18px 0}
  .tlr{display:grid;grid-template-columns:120px 1fr;border-top:1px solid var(--line)}
  .tlr:first-child{border-top:none;background:var(--ink2)}
  .tlr:first-child div{font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--gold)}
  .tlr .d{padding:12px 14px;font-family:ui-monospace,Menlo,monospace;font-size:12.5px;color:#fff;border-right:1px solid var(--line)}
  .tlr .w{padding:12px 14px;font-size:13.5px;color:var(--muted)}
  .tlr .w b{color:#fff}
  .cmp{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:18px 0}
  .cmpr{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line)}
  .cmpr:first-child{border-top:none;background:var(--ink2)}
  .cmpr:first-child div{font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--gold)}
  .cmpr div{padding:12px 14px;font-size:13.5px;color:var(--muted)}
  .cmpr div:first-child{border-right:1px solid var(--line)}
  .cmpr .y{color:var(--ok)}.cmpr .n2{color:var(--block)}
  .gap{display:flex;align-items:stretch;gap:0;margin:16px 0;border:1px solid var(--line);border-radius:12px;overflow:hidden;background:var(--code-bg)}
  .gap .lf{flex:1 1 0;min-width:0;padding:14px;font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--ok);word-break:break-all}
  .gap .lf span{display:block;color:var(--gold);font-size:10px;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:6px}
  .gap .vd{flex:0 0 132px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;border-left:1px solid var(--line);border-right:1px solid var(--line);font-family:ui-monospace,Menlo,monospace;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;color:var(--faint);text-align:center;padding:0 8px}
  @media(max-width:560px){.tlr,.cmpr{grid-template-columns:1fr}.tlr .d,.cmpr div:first-child{border-right:none;padding-bottom:0}.gap{flex-direction:column}.gap .vd{flex:0 0 auto;border-left:none;border-right:none;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:10px}}
  hr{border:none;height:1px;background:linear-gradient(90deg,transparent,rgba(201,168,76,.25),transparent);margin:40px 0 0}
  footer{margin-top:40px;text-align:center;font-size:12px;color:var(--faint);font-family:ui-monospace,Menlo,monospace}
  footer a{color:var(--gold);text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">&larr; sebbi.pro</a>

  <div class="eyebrow">sebbi.pro · systems whitepaper · v7 · plain english</div>
  <h1>One chain. Every proof.<br><span>The deterministic evidence layer for AI.</span></h1>
  <p class="lead">This document explains every piece of sebbi.pro the way a systems engineer would explain it to a colleague: what each part does, why it is built that way, how the parts fit into one evidence layer — and where the design goes next.</p>
  <p class="sub">No marketing language. Where something has a limit, the limit is stated. Where something is not yet built, it is marked as such. That discipline is not decoration around the product; it is the product.</p>

  <div class="honest" style="margin-bottom:26px"><b>New in v7 (11 August 2026).</b> Section 31 documents <b>authority continuity</b>: proving an autonomous action was derivable from a human grant, with every hop re-checked at the instant of execution, the person who accepted the risk named separately from the issuer and the subject, and a signed proof bundle that a third party verifies on their own machine with no dependencies and no network — including a proof of <i>refusal</i> when authority could not be derived. Sections 25 to 30 (v6) documented completeness and absence proofs, proof of erasure, fork detection, black-box reproducibility and cross-organisation lineage. Sections 1 to 24 are unchanged in substance from v5.</div>

  <div class="toc">
    <div class="grp">Foundations</div>
    <a href="#s1"><span class="n">1</span>The problem: records you can edit are not evidence</a>
    <a href="#s2"><span class="n">2</span>The deterministic gatekeeper</a>
    <a href="#s3"><span class="n">3</span>The core: the hash chain</a>
    <a href="#s4"><span class="n">4</span>The outside clock: anchoring to Bitcoin</a>
    <a href="#s5"><span class="n">5</span>The witness network: one chain can be rebuilt, ten cannot</a>
    <a href="#s6"><span class="n">6</span>Gapless receipts: omission is countable</a>
    <a href="#s7"><span class="n">7</span>The second record: basis sealing</a>
    <div class="grp">The engine</div>
    <a href="#s8"><span class="n">8</span>Human oversight: commit before reveal</a>
    <a href="#s9"><span class="n">9</span>SonicBoom — the decision engine</a>
    <a href="#s10"><span class="n">10</span>Signal Packs — extending the engine, provably</a>
    <a href="#s11"><span class="n">11</span>Authority, identity &amp; jurisdiction</a>
    <div class="grp">The products</div>
    <a href="#s12"><span class="n">12</span>Sentinel — pattern and velocity detection</a>
    <a href="#s13"><span class="n">13</span>Guardian — child safety flags</a>
    <a href="#s14"><span class="n">14</span>The Notaries — the chain, opened to everyone</a>
    <a href="#s15"><span class="n">15</span>Brain — the instruction gate</a>
    <a href="#s16"><span class="n">16</span>ai.txt and comply.txt — the declaration layer</a>
    <div class="grp">The whole</div>
    <a href="#s17"><span class="n">17</span>How it all fits together</a>
    <a href="#s18"><span class="n">18</span>Regulation: what this evidences</a>
    <a href="#s19"><span class="n">19</span>Deployment and pricing</a>
    <a href="#s20"><span class="n">20</span>Future potential</a>
    <a href="#s21"><span class="n">21</span>For investors</a>
    <a href="#s22"><span class="n">22</span>Conformance: measuring what cannot be guaranteed</a>
    <a href="#s23"><span class="n">23</span>Honest limits — read this</a>
    <a href="#s24"><span class="n">24</span>Verify everything yourself</a>
    <div class="grp">The proof layer — August 2026</div>
    <a href="#s25"><span class="n">25</span>Completeness: proving what isn't there</a>
    <a href="#s26"><span class="n">26</span>Erasure without breaking the chain</a>
    <a href="#s27"><span class="n">27</span>Fork detection: proving we never ran two histories</a>
    <a href="#s28"><span class="n">28</span>Reproducibility, without disclosing the rules</a>
    <a href="#s29"><span class="n">29</span>Lineage: provenance across company boundaries</a>
    <a href="#s30"><span class="n">30</span>The offline verifier</a>
    <div class="grp">Authority — August 2026</div>
    <a href="#s31"><span class="n">31</span>Authority continuity: proving an agent was entitled to act</a>
  </div>

  <h2 id="s1"><span class="n">1.</span>The problem: records you can edit are not evidence</h2>
  <p>Nearly every system keeps logs. Logs live in databases. Databases can be edited by anyone with the right access — an attacker, an insider, or the operator itself. That means an ordinary log can only ever say <b>"this is what we currently claim happened."</b> It cannot say "and nobody has changed it since."</p>
  <p>Most of the time nobody notices the difference. The difference appears the day someone with authority — a regulator, a court, an insurer, a customer in dispute — stops accepting your word and asks for proof. At that moment, "our system recorded it" and "here is proof it was not changed" are two different sentences, and only the second one carries weight.</p>
  <p>The problem has become urgent for a specific reason. Software used to do what it was told, so a log of the inputs implied the outputs. AI systems produce outputs that cannot be derived from the inputs by inspection, which means the output has to be recorded as a fact in its own right — and the regulation now arriving says so explicitly. The volume of decisions requiring evidence has risen by orders of magnitude; the mechanism most organisations use to evidence them has not changed since the 1990s.</p>
  <p>Everything at sebbi.pro exists to produce the second sentence, cheaply, automatically, as a by-product of systems doing their normal work.</p>

  <h2 id="s2"><span class="n">2.</span>The deterministic gatekeeper</h2>
  <p>Before any component, one design decision governs the entire platform: <b>the governance layer is not an AI.</b> Not a model, not a classifier, not a language model with a system prompt. It is arithmetic — fixed weights, fixed thresholds, an explicit published formula.</p>
  <p>This is not a technical preference. It is the only arrangement under which the layer can do its job.</p>
  <h3>Why governing AI with AI fails</h3>
  <p>Put a model in charge of deciding whether another model behaved acceptably, and every property you needed from the governance layer disappears at once. The verdict cannot be reproduced, because the same input may score differently tomorrow. It cannot be truly explained, because the explanation is itself generated rather than derived. It drifts silently, because a retrained or updated model changes its judgements without anyone choosing to change them. And it can be attacked through its inputs, because anything that reads natural language can be manipulated by natural language.</p>
  <p>Worst of all, it regresses. If a model needs governing, and the governor is a model, the governor needs governing. There is no bottom to that stack. The regress terminates only at something that cannot behave unexpectedly — which means arithmetic.</p>
  <div class="cmp">
    <div class="cmpr"><div>A model as gatekeeper</div><div>Deterministic gatekeeper</div></div>
    <div class="cmpr"><div class="n2">Same input can produce different verdicts</div><div class="y">Same input always produces the identical verdict</div></div>
    <div class="cmpr"><div class="n2">Explanation is generated after the fact</div><div class="y">Explanation is the arithmetic that produced the score</div></div>
    <div class="cmpr"><div class="n2">Silent drift on retraining</div><div class="y">No training; change requires an explicit, sealed edit</div></div>
    <div class="cmpr"><div class="n2">Susceptible to prompt injection</div><div class="y">No language understanding to subvert</div></div>
    <div class="cmpr"><div class="n2">Verdict cannot be re-derived by a third party</div><div class="y">Anyone with inputs and ruleset recomputes it exactly</div></div>
    <div class="cmpr"><div class="n2">Requires trust in the vendor's model</div><div class="y">Requires trust in nothing</div></div>
  </div>
  <h3>What determinism buys at audit</h3>
  <p>A regulator, a court or a counterparty examining a decision two years later does not want a narrative. They want to establish that the decision followed from the stated rules. Determinism makes that a mechanical check: take the sealed inputs, take the sealed ruleset version, recompute. If the result matches the sealed verdict, the decision was not a judgement call and was not tampered with — it was the rules applied to the facts, and anybody can confirm it without the vendor in the room.</p>
  <p>This is the difference between a record that <b>describes</b> a decision and a record that <b>reproduces</b> it. Only the second is evidence in any strong sense. Section 28 turns that property into something a stranger can test directly, without being shown the rules.</p>
  <div class="honest"><b>Honest scope:</b> a deterministic gate is not smarter than a model, and is not meant to be. It will miss things a good classifier would catch, because it has no semantic understanding at all. The trade is deliberate: <b>the governance layer buys reproducibility at the cost of cleverness</b>, because a clever governor whose verdicts cannot be reproduced is not a governor. Use models to do the work; use arithmetic to prove what the work did.</div>

  <h2 id="s3"><span class="n">3.</span>The core: the hash chain</h2>
  <p>At the centre of the whole platform is one data structure: an append-only chain of sealed records. Every product described below — the decision engine, the fraud detectors, the notaries, Brain — writes into a chain built the same way.</p>
  <p>Each record is sealed at the moment it is created. The seal is a SHA-256 hash computed over the record's content <b>together with the seal of the record before it</b>. Because each seal contains its predecessor, every block's integrity depends on the entire history beneath it:</p>
  <pre>seal(n) = SHA-256( seal(n−1) · timestamp · event · result · <i>basis</i> )

verify:  recompute every seal from genesis;
         any mismatch localises tampering to an exact block index</pre>
  <p>Alter one character of one historic record and every seal after it fails verification. There is no way to repair the chain after an edit without recomputing every subsequent seal — and the current tip is recorded in the same transaction as every write, so even chopping records off the end is detected. The operator cannot rewrite its own records. Neither can we.</p>
  <p>Engineering properties, stated plainly:</p>
  <ul>
    <li><b>Concurrency-safe:</b> the tip read, hash computation and insert happen inside a single lock hold and a single transaction. There is no race window in which two writers can fork the chain.</li>
    <li><b>Crash-safe:</b> write-ahead journaling with full synchronous commits. A power cut mid-write rolls back cleanly; the chain cannot be left with a torn, half-sealed block.</li>
    <li><b>Truncation-evident:</b> the chain tip and last sequence number are recorded in the same transaction as each seal. Deleting blocks from the end breaks the tip record and is reported as tampering.</li>
    <li><b>Fast:</b> score + decide + seal + respond runs inline in under 30ms; the engine's median is 28ms. Sealing is not a batch job that happens later — it happens before the response returns.</li>
    <li><b>Resilient:</b> automatic daily database backups; the chain survives restarts intact.</li>
  </ul>
  <p>One sentence captures the design philosophy: <b>a system that does not trust its own creator is the only kind whose records qualify as evidence.</b></p>

  <h2 id="s4"><span class="n">4.</span>The outside clock: anchoring to Bitcoin</h2>
  <p>The chain described above has a hole in it, and it is the same hole every tamper-evident audit product has. Most do not mention it.</p>
  <p>A hash chain proves no record was altered <b>after</b> the chain was built. It does not, on its own, prove <b>when</b> the chain was built. An operator with full control of the system could in principle discard the whole chain and construct a fresh one from scratch, containing whatever it preferred, dated however it liked. Every seal in that fabricated chain would verify perfectly. Internal integrity is necessary; alone it is not sufficient, because the operator still controls the clock.</p>
  <p><b>So the clock was moved outside the building.</b> At a defined interval the current tip of the chain is submitted to <b>OpenTimestamps</b>. OpenTimestamps aggregates that tip with thousands of unrelated timestamps into a single Merkle tree and commits the root of that tree to the <b>Bitcoin blockchain</b>. The proof returned is a path from our tip to that root, and from the root to a Bitcoin block. Several independent calendar servers perform this in parallel, so no single calendar can fail, disappear or lie without the others contradicting it.</p>
  <p>The distinction matters and is worth stating precisely, because the loose version — "we write your hash to Bitcoin" — is both technically wrong and commercially misleading. We do not make a Bitcoin transaction per anchor. We contribute to one. That is why anchoring runs continuously rather than when someone remembers the cost: the marginal cost of an anchor is effectively zero, and a timestamp that only happens when convenient is not a timestamp.</p>
  <p>From that moment the timestamp is not ours to move, not ours to re-issue, and not ours to quietly correct. Fabricating an earlier history would require rewriting Bitcoin itself.</p>
  <pre>anchor:  tip(n) &rarr; OpenTimestamps &rarr; Merkle root &rarr; Bitcoin block
returns: <b>chain tip</b> · <b>transaction id</b> · <b>block height</b> · <b>time</b>

proves:  the chain stood in exactly this state at or before
         that block — verifiable by anyone, without asking us</pre>
  <h3>What it answers</h3>
  <p>The oldest objection to any audit trail is a single sentence: <i>you could have written all of this last week.</i> Every assurance a vendor offers in reply is another claim from the party being questioned. An anchored chain answers with arithmetic instead. The person checking needs no account, no cooperation from us, and no continued existence of this company — the reference sits in a public ledger, permanently, and the check is the same check whether we are still trading or not.</p>
  <p>That last property deserves dwelling on, because it is the one buyers of compliance infrastructure ask about last and depend on most: <b>the evidence outlives the vendor.</b> A customer's sealed history remains verifiable if this company disappears entirely. Section 30 extends that to the checking tool itself.</p>
  <h3>Three deliberate design points</h3>
  <ul>
    <li><b>Nobody holds crypto.</b> Neither the platform nor the customer holds, buys, or is exposed to any token. Bitcoin is used purely as a timestamp nobody owns; the asset's price is irrelevant to the function.</li>
    <li><b>Anchoring is not the integrity mechanism.</b> The hash chain provides integrity; anchoring fixes that chain in time. Conflating the two is the standard error in "blockchain audit" marketing, and they really do different jobs.</li>
    <li><b>The reference is returned to you.</b> Anchor data comes back with the record, so an auditor, a court or a customer can verify independently. Going through us is optional at every stage.</li>
  </ul>
  <div class="proves">
    <div class="t">What the pair proves together</div>
    <p><b>The chain</b> — nothing has been edited since it was written.</p>
    <p><b>The anchor</b> — it was written no later than a fixed, externally witnessed moment.</p>
    <p style="margin-bottom:0">Neither is sufficient alone. Together they close both directions: history cannot be rewritten, and it cannot be manufactured after the fact.</p>
  </div>
  <div class="honest"><b>The honest boundary, because someone always asks:</b> anchoring proves existence and timing. It does not prove the record was <b>true</b> at the moment of capture — but neither does any recording system ever built. No ledger, court transcript, witness statement or set of company books verifies the truth of its own inputs; that is what recording <i>is</i>, and a vendor claiming to have solved it is describing something that does not exist. What can be proved is the decision itself, from both sides of it: the input is sealed at capture so it cannot be swapped afterwards to justify the verdict, and the scoring is deterministic with its ruleset version sealed alongside, so the verdict can be re-derived and cannot be re-explained afterwards either. The only unverifiable interval is the instant of capture. Everything either side of it is arithmetic.</div>

  <h2 id="s5"><span class="n">5.</span>The witness network: one chain can be rebuilt, ten cannot</h2>
  <p>Anchoring closes backdating, but only up to the last anchor. Between anchors an operator with full control of their own server can still, in principle, construct a history and present it. The gap is small, and it is real, and it is the same gap every vendor in this market has.</p>
  <p>It closes when platforms witness each other. Each platform periodically publishes its current chain tip; each peer seals that tip into <b>its own chain</b>. From that moment one platform's history is recorded inside chains it does not control, which are themselves independently anchored.</p>
  <p>To rewrite your own past you would now need every peer who witnessed you to rewrite theirs, in step, and re-anchor all of it. That is no longer a technical operation on a database. It is a coordinated conspiracy between commercial competitors, and the difficulty scales with the number of participants rather than with the size of anyone's engineering team.</p>
  <p>The economics make it practical. A chain tip is 64 characters. Witnessing one is a single sealed block. Ten platforms exchanging tips hourly generates a few hundred blocks a day <b>between all of them</b> — an integrity property strong enough to matter, at a cost small enough to ignore.</p>
  <h3>The submission endpoint is open, permanently and on purpose</h3>
  <p>The route that accepts a chain tip requires no account, no key and no approval from anyone. That is not an oversight and it is not generosity — it is the answer to the only serious objection the model faces.</p>
  <p>The objection is collusion: if we choose our witnesses, we can choose witnesses who will lie with us. It is a fair challenge and it has been put to us directly. The answer has three parts. First, a peer lying <i>about</i> us cannot help us — sealing a tip we never issued produces an entry pointing at a chain state that does not exist, which fails the moment anyone checks. A peer can only conspire with us, never frame us. Second, our peers are anchored too, so the conspiracy is not two parties agreeing a story but two parties defeating timestamps already published in a ledger neither controls. Third, and decisively: <b>because anyone can witness us without asking, we cannot know who is doing it.</b> A client, an auditor, a regulator or a competitor can pull our tip on a timer and seal it wherever they like. Collusion requires knowing your co-conspirators. Open witnessing removes that knowledge from us permanently.</p>
  <p>Three further properties are deliberate. <b>Nobody owns it:</b> there is no licence and no revenue share, because an integrity property is participated in rather than purchased. <b>Anyone can query it:</b> a third party can ask whether a given tip was witnessed, and when, and receive the block it was sealed in. <b>Silence is visible:</b> peers who stop publishing are marked stale and then silent, and a replayed tip is flagged automatically, because a network that cannot be audited is not a network.</p>
  <h3>Names, and what can actually be proved about them</h3>
  <p>Because submission is open, the chain name in a submission is self-declared — anyone can post under any name. That is not solved with accounts, because accounts would close the network. It is solved by publishing how strong each claim is, and by remembering. Two checks run on every submission and <b>neither can reject it</b>; a submission is always sealed, and what changes is what is said about it. A <b>liveness</b> check fetches the submitted URL and reports <i>confirmed</i> (it serves exactly the tip submitted), <i>live</i> (it serves a different valid tip, which is what a busy chain does between submitting and being fetched) or <i>self-declared</i> (no URL, or unreachable). A <b>name binding</b> check records the URL a name was first seen at and compares every later submission: <i>first-use</i>, <i>bound</i>, or <i>conflict</i> where the same name has been submitted from a different address. A conflict is not proof of theft — operators move hosts — but it is exactly the event an auditor needs to see, and it is recorded permanently in the chain rather than resolved quietly by us.</p>
  <p class="honest"><b>What this does not do.</b> Witnessing proves a tip existed at a time. It says nothing about whether the records behind it are true — garbage sealed on time remains garbage. Two platforms witnessing only each other prove very little; the guarantee comes from breadth, which is why participants should publish who witnesses them. The liveness check proves the submitter operates a live chain producing that data; it does not prove they are who they say, because anyone running a real chain can point a stolen name at their own URL. And no design can compel a peer to keep publishing. These are properties of the model, not defects in the implementation.</p>

  <h2 id="s6"><span class="n">6.</span>Gapless receipts: omission is countable</h2>
  <p>A tamper-evident chain proves records were not <b>edited</b>. It does not by itself prove records were not <b>omitted</b> — an operator could simply fail to write an inconvenient event. The receipt system closes that hole.</p>
  <p>Every sealed decision is issued a sequence number, generated <b>in the same transaction</b> as the chain write. Sequences are gapless by construction: 46, 47, 48. The caller stores their receipts. If you ever hold receipts 46 and 48 with no 47, a record has been omitted — and you can prove it by arithmetic, not argument.</p>
  <p><b>Edited records break the chain. Missing records break the sequence. Fabricated history breaks the anchor.</b> Between the three, every way of quietly rewriting the past is detectable from outside, by anyone, without trusting the operator. That triple is the whole security model, and it is deliberately small enough to hold in your head.</p>
  <p>Receipts protect the holder of the receipt. They do not help a party who never received one, and they cannot answer "is this the complete set" for someone auditing from outside. Section 25 closes that remaining gap.</p>

  <h2 id="s7"><span class="n">7.</span>The second record: basis sealing</h2>
  <p>There are two different records hiding inside "what a system did." The first is the <b>action</b>: this decision, this result, this timestamp, sealed. The second is the <b>basis</b>: what the decision was permitted to rely on when it acted — which sources, which versions of them, which ruleset it was checked against.</p>
  <p>A seal on the action alone proves the action happened exactly as recorded. It cannot show what the action rested on — and a decision made on the wrong source, sealed, is just a tamper-proof error. So the engine seals both, in the same block:</p>
  <pre>basis = { sources:         [<b>"invoice_4471.pdf"</b>, <b>"supplier_record_88"</b>],
          source_versions: [<b>"sha256:ab12…"</b>, <b>"sha256:cd34…"</b>],
          ruleset:         <b>"AI-TXT/1.0 + EU-AI-Act-2024/1689"</b>,
          ruleset_version: <b>"regmap-v7"</b>,
          signal_pack:     <b>"payments-fraud v4 · sha256:7ab1…"</b> }</pre>
  <p>The basis is canonicalised, hashed, and folded into the block seal. Edit the recorded basis later and the chain breaks exactly as if the action had been edited. Even "no basis was supplied" is itself sealed as a fixed sentinel — so the absence of a basis is a provable fact, not a blank that can be filled in later.</p>
  <p>Basis sealing records what a decision rested on <b>inside one organisation</b>. Section 29 extends the same idea across organisational boundaries, where the source of a decision is another company's decision.</p>
  <div class="honest"><b>The honest boundary, stated once and repeated everywhere it matters:</b> basis sealing proves <b>what</b> a decision relied on and that the record of it is unaltered. It does <b>not</b> prove the basis was <b>correct</b> — that a source was genuine or the ruleset was the right one. Integrity is provable by mathematics; correctness is a separate discipline involving people and process. Any product claiming to cryptographically prove correctness is misdescribing what cryptography can do.</div>

  <h2 id="s8"><span class="n">8.</span>Human oversight: commit before reveal</h2>
  <p>Article 14 requires that natural persons can <b>effectively oversee</b> a high-risk system. Every vendor in this market claims to satisfy it, and the honest position is that none of them can, including this one. Whether a reviewer genuinely deliberated is an internal state. No logging reaches it. Any product claiming to prove human thought is selling something that does not exist.</p>
  <p>Rubber stamping, however, is not an internal state. It is a behavioural pattern, and patterns leave marks provided the right things are recorded, in the right order, at the time. Three mechanisms follow from that.</p>
  <p><b>Order.</b> The case is presented to the reviewer without the machine's verdict. Their own decision and their reasoning are sealed first; the verdict is revealed only afterwards. Two blocks, in that sequence, in a chain that cannot be reordered. A reviewer therefore cannot have merely agreed with an answer they had already been shown, because the chain fixes which came first.</p>
  <p><b>Attention.</b> The interval between opening a case and committing to it is sealed alongside the decision. A 0.8-second approval sits in the record permanently, beside a two-minute one. This is not proof of thought, and a single fast decision proves nothing. Four hundred consecutive sub-second decisions is a different kind of object — one that survives being explained away.</p>
  <p><b>Independence.</b> Agreement rate is recorded per reviewer over time. A reviewer who has never once diverged from the machine across a meaningful sample is visible in the data; one who diverges sometimes is demonstrably exercising judgement. The measurement is dull, which is precisely why it works.</p>
  <p>What an auditor receives is therefore not an assertion that oversight occurred, but a dataset that can be tested — and one that a rubber stamper cannot hide inside. It sits in the same chain as the decisions themselves, under the same anchor.</p>
  <p class="honest"><b>What this does not do.</b> A reviewer can leave a screen open, so dwell time is gameable by anyone deliberately gaming it. The system cannot establish that the material was read, only that it was available and that time passed. Most importantly, the ordering guarantee is only as strong as the integration honouring it: if a platform displays the machine verdict to its own staff before calling the API, the sealed order proves nothing at all. That constraint is documented in the code rather than buried in it, because a guarantee whose failure mode is undisclosed is not a guarantee.</p>

  <h2 id="s9"><span class="n">9.</span>SonicBoom — the decision engine</h2>
  <p>SonicBoom is the scoring engine at the heart of the paid platform — the component that looks at an event and answers, in a fraction of a second: allow it, challenge it, or block it. It is the deterministic gatekeeper of section 2, made concrete.</p>
  <h3>What it takes in</h3>
  <p>Seven fields per event: who is acting (<code>user_id</code>), what they are doing (<code>action</code>), the value involved (<code>amount</code>), where from (<code>country</code>), on what (<code>device_id</code>), plus two optional risk signals your own systems may already produce (<code>anomaly</code>, <code>device_risk</code>). If you do not have those signals, send zero — the engine works from its own analysis. An optional eighth field, <code>authority_token</code>, carries delegated authority, covered in section 11.</p>
  <h3>What it does with them</h3>
  <p>The engine combines several independent signals: how fast events are arriving for this user and device (velocity), whether the country has changed or is off the expected list, how large the amount is on a log scale, and a <b>per-user trust score learned over time</b>. Trust is earned slowly with every allowed action and lost roughly eight times faster on every block — so an account behaving normally builds standing, and a burst attack destroys its own standing as it runs, making each successive attempt score worse.</p>
  <h3>What comes back</h3>
  <ul>
    <li><b>ALLOW</b> (score below 0.35) — proceed.</li>
    <li><b>CHALLENGE</b> (below 0.70) — borderline; verify further before proceeding.</li>
    <li><b>BLOCK</b> — refuse, with the reasons stated in plain English (for example: "velocity spike", "new country", "low trust").</li>
  </ul>
  <p>Every verdict is sealed into the chain <b>before the response returns</b>, with its reasons, its jurisdiction tag, its active Signal Pack version, and — where supplied — its basis. The caller receives the verdict, the plain-English reasons, the sealed hash and the gapless receipt number in one response, in about 28 milliseconds.</p>
  <h3>The challenge flow — human oversight built in</h3>
  <p>When the verdict is CHALLENGE, the response includes a hosted resolution flow: a signed link your user can open to confirm or deny the action, a status endpoint you poll for the outcome, and an expiry. The tokens are stateless and HMAC-signed; the resolution is sealed into the chain as its own block. The exception path — the moment a human steps in — becomes part of the evidence trail rather than a gap in it. Integration is three lines: if the verdict is CHALLENGE, show the link, poll the status.</p>
  <h3>Monitoring</h3>
  <p>Two authenticated endpoints give the operator live sight of their own traffic: a pulse view (last hour's verdicts, recent decisions with reasons and seals, current chain tip) and a coverage view reconciling receipts issued against blocks sealed — one call that answers "is my evidence complete?" with a yes or no. When the engine blocks on your traffic, the sealed evidence is emailed to the account address, throttled to once per hour so a burst cannot flood you.</p>

  <h2 id="s10"><span class="n">10.</span>Signal Packs — extending the engine, provably</h2>
  <p>The core engine scores every event against nine signals: trust, velocity at three windows (60 seconds, 5 minutes, 1 hour), amount, device risk, anomaly, country shift and unsafe country. Those nine are domain-neutral — they describe the shape of behaviour, not the specifics of an industry.</p>
  <p>It is worth being precise about what those nine are and are not, because it is a fair criticism and it has been put to us. They are transaction-risk signals: velocity, anomaly, device, geography. That is the lineage of the engine and it is the right toolkit for fraud and abuse. It is <b>not</b> a risk taxonomy for the AI Act's risk-management obligations, and describing it as one would be an overclaim. What the platform provides toward those obligations is different and stated plainly in section 18: the evidence that a risk-management system was defined, was in force at a given moment, and governed the decisions taken under it. The taxonomy belongs to the operator. The proof that it operated belongs here.</p>
  <p>A <b>Signal Pack</b> is a versioned bundle of additional signals, weights and thresholds loaded on top of the core, tuned to one kind of risk. Packs run on the same deterministic engine — no model, no training, no drift. Identical inputs under an identical pack produce an identical verdict, permanently.</p>
  <ul>
    <li><b>Payments &amp; fraud</b> — value jumps, new beneficiaries, card-testing signatures, burst velocity.</li>
    <li><b>Child safety</b> — grooming and contact-escalation patterns, age context, off-platform pull. Content is never stored, only fingerprinted.</li>
    <li><b>Lending &amp; onboarding</b> — identity consistency, document risk, affordability shifts, and a forced CHALLENGE pathway wherever a decision materially affects a person's access to a service.</li>
    <li><b>Marketplace integrity</b> — account age, listing anomalies, coordinated activity, reinstatement history.</li>
    <li><b>Custom</b> — an operator's own signals, weights and thresholds, on the same engine and the same guarantees.</li>
  </ul>
  <h3>Why packs are versioned and sealed</h3>
  <p>This is the part that matters at audit, and most systems do not solve it. Suppose an examiner asks, two years later, why a particular decision came out the way it did. To answer, you must establish <b>which rules were live at that moment</b>. Almost every platform answers from a changelog — a document someone with access could have edited afterwards. The answer rests on the operator's word again, which is exactly the thing this system exists to remove.</p>
  <p>So every pack carries a version hash over its full definition, and when a decision is sealed the pack hash is sealed inside the same block. Change a weight, change a threshold, add a signal, and the pack takes a new hash and the change enters the chain as its own timestamped, anchored block.</p>
  <pre>decision  seal <b>9f3c1a…</b>  verdict <i>CHALLENGE</i>  score 0.41
pack      <b>payments-fraud</b> · v4 · sha256:<b>7ab1…</b>
meaning   this verdict, from these inputs, under these exact
          rules, at this exact time — re-derivable by anyone</pre>
  <p><b>Rule changes become auditable events, never silent edits.</b> And because scoring is deterministic, any sealed decision can be independently re-run: take the sealed inputs, take the sealed pack version, recompute, confirm the verdict was what the rules dictated. The decision is not merely recorded — it is reproducible.</p>
  <div class="honest"><b>Honest scope:</b> a Signal Pack encodes a judgement about what matters in a given domain, and that judgement can be wrong. Sealing proves which rules ran and that the verdict followed from them; it says nothing about whether those were the right rules. Choosing and reviewing thresholds remains a human responsibility — the system makes that choice visible and permanent rather than tacit.</div>

  <h2 id="s11"><span class="n">11.</span>Authority, identity &amp; jurisdiction</h2>
  <p>Three questions sit around every automated decision that the decision itself cannot answer: <b>who authorised this person to act</b>, <b>who is this person in the legal sense</b>, and <b>which rules governed the moment it happened</b>. The delegation layer answers all three with the same machinery — sealed, deterministic, verifiable.</p>
  <h3>Delegated authority — Article 14 done as engineering</h3>
  <p>Human oversight only means something if the human doing the overseeing was actually authorised to. The engine issues <b>signed authority tokens</b>: a single call binds a user to a role, a spending limit and an expiry, HMAC-signed server-side. The grant is sealed into the chain as its own block — so "who gave this person this power, and when" is a permanent record, not an HR email.</p>
  <p>Events can then carry the token. The engine verifies it deterministically: wrong user, expired grant, tampered token, or an amount above the granted limit each escalates the verdict and seals the reason — <code>authority_expired</code>, <code>authority_exceeds_limit</code> — into the record. An approval made outside granted authority is no longer a quiet judgement call; it is a flagged, sealed, examinable event.</p>
  <h3>Identity — KYC results, sealed without the data</h3>
  <p>The platform does not verify passports — specialist providers do that, and pretending otherwise would be theatre. What the engine does is make the <b>outcome</b> provable: a single call seals a verification result — provider, verified or not, and the SHA-256 fingerprint of the provider's reference — into the chain. The document itself, and even the raw reference number, are never stored. Later, "this user was KYC-verified by provider X on date Y" is a sealed fact any auditor can check, with zero personal data held to leak.</p>
  <h3>Jurisdiction — which rules applied, sealed at decision time</h3>
  <p>Every governed decision is tagged with the regulatory frameworks that applied at the moment it was made — EU AI Act, GDPR and DSA for EU-origin events, the Online Safety Act, UK GDPR and Children's Code for the UK, and so on — using a versioned mapping sealed inside the decision block. A multinational can answer "show every decision and which regulator's rules governed it" from the chain alone.</p>
  <div class="honest"><b>Honest scope, because this is where competitors overclaim:</b> the jurisdiction layer records <b>which obligations applied</b> — it does not and cannot <b>decide</b> legal authority. No software can; courts do that. Any product claiming to "determine which jurisdiction controls" is describing a lookup table in grander language. This one is a lookup table too — versioned, sealed, and honest about it.</div>

  <h2 id="s12"><span class="n">12.</span>Sentinel — pattern and velocity detection</h2>
  <p>Sentinel is the fraud-watching layer: it looks at the <b>speed and shape</b> of activity rather than the content of any single event. The patterns it recognises are the classic signatures of attack: a flood of login attempts against one account (credential stuffing), a burst of transactions in seconds (card testing, automated abuse), an account appearing in a new country moments after its last action (takeover).</p>
  <p>Sentinel and SonicBoom work together: Sentinel's velocity analysis is one of the signals driving SonicBoom's score, and when a pattern crosses the line the flag — what fired, when, on what evidence — is sealed into the same chain. The result for a fraud team is not just an alert, but an alert with a tamper-evident, externally anchored record behind it that survives scrutiny later: exactly what happened, in what order, provably unaltered.</p>

  <h2 id="s13"><span class="n">13.</span>Guardian — child safety flags</h2>
  <p>Guardian applies the same machinery to a different and more serious problem: platforms where children are present. It watches for the recognised behavioural warning signs that precede grooming — pressure toward secrecy, attempts to isolate, moves toward private channels — and flags them.</p>
  <p>Two design decisions matter here. First, <b>message content is never stored</b> — only a fingerprint of it. Privacy is preserved; what is kept is proof that the flagged exchange existed in the exact form it had. Second, every flag is sealed into the chain, so the evidence trail handed to a parent, a platform's safety team or the authorities is tamper-evident from the moment of detection and externally anchored shortly after. A safeguarding report backed by an anchored chain is a fundamentally stronger document than one backed by an editable log — and in the one context where this evidence may end up in front of a court, that difference is the entire point.</p>
  <div class="honest"><b>Honest scope:</b> Guardian is a detection and evidence aid. It supports a platform's duty of care; it does not discharge it. Child-safety decisions must always involve trained people and, where warranted, the proper authorities.</div>

  <h2 id="s14"><span class="n">14.</span>The Notaries — the chain, opened to everyone</h2>
  <p>The notaries expose the chain directly to the public, free, with no account and no code. They exist for two reasons. The obvious one: most people and small businesses have no "system" to integrate, but still have things worth proving. The strategic one: <b>a claim about evidence infrastructure is only credible if anyone can test it in thirty seconds without asking permission.</b> The notaries are that test, permanently available.</p>
  <p>All three share one privacy-preserving design: <b>your content never leaves your device.</b> Your browser computes a SHA-256 fingerprint locally; only that 64-character fingerprint is sent and sealed. The chain proves a document with exactly that fingerprint existed at that moment. You reveal the original only if and when you ever need to — and if you never need to, nobody ever sees it.</p>
  <h3>Post notary — the words, fixed</h3>
  <p>Seal the exact words of anything before you send or publish it: a quote, a contract, an announcement, a message. Later, anyone can verify those exact words existed on that date and have not been edited. A tradesman who sealed a £2,400 quote the day he sent it ends a "you said £1,800" dispute with mathematics rather than argument — and it cost him nothing and took ten seconds.</p>
  <h3>Identity notary — the profile, dated</h3>
  <p>Seal your name, role and links; receive a short verification code for your public profile. If a fraudster clones the profile, the clone fails the check — the genuine one was sealed first, and the chain proves which came first. Impersonation defence is usually framed as detection; this reframes it as chronology, which is a far easier thing to prove.</p>
  <h3>Payment notary — the details, verified before money moves</h3>
  <p>A business seals its genuine bank details once; every invoice carries a short code; the payer checks the code before releasing funds. If an intercepted invoice's details were swapped — the classic authorised-push-payment fraud — the check returns MISMATCH and the payment stops. The verification itself is sealed and returned as a receipt, so <b>both sides hold provable evidence that care was taken before money moved</b>. Under the 2024 mandatory reimbursement rules, that record speaks directly to where liability falls.</p>
  <p>Every seal returns a unique 12-character code — the holder's permanent claim to that specific record. One shared chain underneath, anchored like everything else; one private, verifiable receipt each. A sole trader's sealed quote and a bank's sealed decision sit in the same structure with the same guarantees. That was deliberate.</p>

  <h3>The data subject request notary</h3>
  <p>When a person asks an organisation to delete their data, three facts must be provable afterwards: that the request was received and on what date, that it was actually considered and on what grounds, and that it was answered inside the statutory deadline. Almost no organisation can prove any of the three. They have an email thread and a recollection.</p>
  <p>The notary seals the whole lifecycle — received, assessed with the reasoning, extended, completed — as ordinary blocks in the main chain. The calendar-month deadline is computed and sealed at receipt, and an extension is its own sealed block recording both the old and new dates, so an extension cannot be applied retrospectively to cover a deadline that was already missed.</p>
  <p>The chain never holds the person's identity. The identifier supplied by the caller is fingerprinted on arrival and only the fingerprint is stored or sealed. This answers the objection that an append-only chain conflicts with the right to erasure: it does not. The personal data lives in the operator's own systems and is deleted there in the ordinary way. What remains in the chain is a seal that resolves to nothing — evidence that erasure was handled correctly, without obstructing it. Section 26 completes that story by making the erasure itself provable to the person who asked for it.</p>

  <h3>The reconciliation notary</h3>
  <p>A sealed chain proves records were not altered afterwards. It does not prove they were true when written. An operator who seals fiction on time possesses a tamper-evident chain of fiction, and everyone honest in this field knows it. The reconciliation notary attacks that directly, by doing what auditors have always done: substantive testing against source records.</p>
  <p>The mechanism that makes it more than theatre is the ordering. A selection seed is derived from the current chain tip — a value the operator cannot predict in advance and cannot alter afterwards without breaking the chain — the records to be tested are chosen from it, and that selection is <b>sealed before any data is requested</b>. Only then are the identifiers returned for the operator to fetch from their own live system.</p>
  <p>The operator therefore cannot choose which records are examined, cannot prepare only the flattering ones, and cannot quietly discard a test that went badly: every planned run is sealed at the moment it is planned, and a plan with no submitted result remains permanently visible as an abandoned test. Mismatches are sealed with precisely the same permanence as matches. A reconciliation system that can bury its own failures is decoration.</p>
  <p>What a pass means, stated exactly: two systems the operator controls agree with each other, on records the operator could not select, at a moment the operator could not choose. That is not proof of truth. An operator fabricating consistently across every system in real time, without knowing what will be sampled, will pass. What it changes is the cost of lying — from editing one database to maintaining a coherent parallel reality across independent systems indefinitely, under unpredictable sampling, with every failure sealed permanently.</p>

  <h3>The declaration notary</h3>
  <p>An operator publishes a file stating what must always be true of their decisions: payments above a threshold are never auto-approved, every decision carries reasons, and so on. Every sealed record is then tested against it and violations are sealed.</p>
  <p>The obvious objection is circularity — they wrote their own rules and supplied their own data. Two properties answer it. First, <b>the rules are sealed before the records they judge</b>, so a standard cannot be retrofitted to an outcome; the chain fixes which came first. Second, every version is retained and sealed, so loosening your own standard becomes a dated, permanent and public act rather than a quiet edit. The strict rule published in March remains readable in September, next to the loose one that replaced it.</p>
  <p>The declaration does not establish that an operator is honest. It converts their claims into something testable, and removes their ability to move the goalposts afterwards. An auditor reads the declaration, the violations and the version history — all three sealed, none of them editable.</p>
  <p class="honest"><b>What these do not do.</b> Weak rules prove weak things: a declaration requiring nothing passes everything, which is precisely why the declaration itself is published rather than merely its pass rate. Reconciliation tests the operator's systems against each other, not against the world. And none of these can find a decision that was never recorded at all — gapless receipts cover that hole, not these.</p>

  <h2 id="s15"><span class="n">15.</span>Brain — the instruction gate</h2>
  <p>Brain applies the evidence layer to a newer problem: the instructions fed to AI systems. An AI does what it is told — so the question becomes who checks what it is being told. A poisoned instruction ("ignore your rules", "export the customer data", "delete the logs") walks straight in unless something stands in front.</p>
  <p>Brain is that something: a gate every instruction passes through before the AI acts. It checks against five categories of known-dangerous patterns — child safety, data exfiltration, compliance bypass, prompt injection, system destruction — with normalisation defences so unicode look-alikes, zero-width characters and spacing tricks resolve to the same fingerprint as the plain form. Dangerous instructions are blocked with the reason stated. And every decision, allowed or blocked, is sealed — with its basis, where supplied — into a chain with all the properties above: gapless, anchored, truncation-evident.</p>
  <p>Brain is deliberately distributed differently from the rest of the platform: a single pure-Python file, free to download, standard library only, no cloud, no API key. It runs entirely on your own machine and your instructions never leave your system. It is meant to be read before it is run — every line of it — because a governance tool you cannot inspect is itself an ungoverned claim.</p>
  <div class="honest"><b>Honest scope:</b> Brain blocks known-dangerous patterns. It does not catch every possible paraphrase of a bad instruction — no filter honestly can, and any vendor claiming complete coverage of natural language is overclaiming. What Brain guarantees is the record: every instruction, every decision, every basis, sealed and tamper-evident. The filter is the first line; the evidence is the product.</div>

  <h2 id="s16"><span class="n">16.</span>ai.txt and comply.txt — the declaration layer</h2>
  <p>The final layer is not code but a convention, modelled on robots.txt and security.txt: two small public text files at well-known paths that let any organisation declare, machine-readably, how its AI is governed.</p>
  <ul>
    <li><b>ai.txt</b> — the public declaration: what AI the organisation operates, what decision model governs it, what audit method backs it, what regulations it is designed toward, and where a human override sits.</li>
    <li><b>comply.txt</b> — the rulebook: the specific rules every instruction and decision is subject to.</li>
  </ul>
  <p>On their own these are declarations — claims, not proof. Anyone can write "tamper-evident audit" in a text file. Their force comes from the third step: sealing the declarations themselves into the chain, so "this is our governance, as declared on this date" becomes provable and its history becomes tamper-evident. Declaration → rulebook → enforcement: words, backed by rules, backed by working code, backed by an external clock.</p>

  <h2 id="s17"><span class="n">17.</span>How it all fits together</h2>
  <p>Every piece above is one layer of a single stack. Reading from the bottom up:</p>
  <div class="stack"><em>DECLARATION</em>   ai.txt · comply.txt      what we claim, publicly, machine-readably
<em>GATE</em>          Brain                    instructions checked before the AI acts
<em>DELEGATION</em>    authority · identity ·   who may act, who they legally are,
              jurisdiction             and which rules governed the moment
<em>DECISION</em>      SonicBoom + packs        every event scored: allow / challenge / block,
                                       deterministically, under a sealed ruleset
<em>DETECTION</em>     Sentinel · Guardian      attack patterns · child-safety patterns
<em>PUBLIC ACCESS</em> the Notaries             the same chain, free, for anyone
<em>AUTHORITY</em>     <s>derivation</s> · <s>risk owner</s>   every hop back to a human, re-derived at
              <s>exported proof</s>          execution, checkable off our machines · §31
<em>LINEAGE</em>       cross-org provenance     what fed a decision, hop by hop, across
                                       company boundaries · §29
<em>PROOF</em>         <s>completeness</s> · <s>absence</s>   what is in a period, what is not,
              <s>consistency</s> · <s>replay</s>      never forked, still reproducible · §25–28
<em>EVIDENCE</em>      <s>the hash chain</s>           every layer above seals into here:
                                       action + basis + receipt, gapless
<em>WITNESS</em>       <s>peer chains</s>              our tip sealed inside chains we do not own
<em>TIME</em>          <s>Bitcoin anchoring</s>        the chain tip fixed in a ledger
                                       nobody involved controls</div>
  <p>The flow of a single event: an instruction or action arrives → Brain checks it against the declared rules → the delegation layer establishes authority, identity and applicable jurisdiction → SonicBoom scores it under the active Signal Pack, informed by Sentinel's pattern analysis → the verdict, its reasons, its jurisdiction tag, its pack version and its basis are sealed into the chain in the same transaction, with a gapless receipt → any upstream receipts it depended on are declared as lineage edges → the period it falls in is later committed with its exact total → the chain tip is anchored externally and handed to peer chains → and anyone, at any time, can verify the whole thing from outside without an account.</p>
  <p>The design principle tying it together: <b>evidence accrues as a by-product of the system working.</b> Nobody remembers to log anything. Nobody compiles an audit file before an inspection. The proof exists because the system ran — and it is exactly as trustworthy whether the operator is honest or not, which is the only kind of trustworthy that counts.</p>

  <h2 id="s18"><span class="n">18.</span>Regulation: what this evidences</h2>
  <p>The platform maintains a versioned <b>regulation map</b> — itself hash-sealed, itself served at a public endpoint — linking each engine capability to the obligations it helps evidence: the EU AI Act's record-keeping, transparency and human-oversight expectations (Articles 9, 12, 13 and 14, with delegated-authority tokens directly supporting Article 14's requirement for effective, attributable human oversight), the UK Online Safety Act's duty-of-care documentation, and the ICO Children's Code. Jurisdiction tagging extends the map to the per-decision level. The map is versioned, so when regulations change, the history of what was mapped when is itself tamper-evident.</p>
  <h3>The current EU timeline</h3>
  <p>The 2026 AI Omnibus amended the AI Act's application dates. The high-risk obligations moved back; the transparency obligations did not, and one deadline was shortened. The delay is widely misreported, so the dates are set out here rather than summarised.</p>
  <div class="tl">
    <div class="tlr"><div class="d">Date</div><div class="w">What applies</div></div>
    <div class="tlr"><div class="d">2 Aug 2026</div><div class="w"><b>Transparency obligations apply.</b> Disclosure that a person is interacting with an AI system; machine-readable marking of AI-generated or manipulated content; deepfake disclosure. Commission enforcement powers over general-purpose models begin the same day, as does the penalty regime.</div></div>
    <div class="tlr"><div class="d">2 Dec 2026</div><div class="w"><b>Content-marking grace period ends</b> — reduced from six months to three. Also the date the prohibition on AI-generated non-consensual intimate imagery and CSAM takes effect.</div></div>
    <div class="tlr"><div class="d">2 Dec 2027</div><div class="w"><b>High-risk obligations apply to stand-alone systems</b> — Articles 9, 12, 13 and 14.</div></div>
    <div class="tlr"><div class="d">2 Aug 2028</div><div class="w"><b>High-risk obligations apply to AI embedded in regulated products.</b></div></div>
  </div>
  <p>The delay is widely read as breathing room. It is not, for one structural reason: <b>the evidence these articles require is historical.</b> An organisation assessed in 2028 will be asked what its systems decided and why across the preceding period. Records cannot be created retrospectively — that is the entire point of a tamper-evident, externally anchored chain, and it is why the useful moment to start recording is before the obligation bites rather than when it does.</p>
  <h3>What the proof layer adds, article by article</h3>
  <ul>
    <li><b>Article 12, record-keeping.</b> Completeness (§25) changes the answer from "here are our decisions" to "here are all 1,204 decisions in this period, and here is the proof there were no others" — with the total fixed before any request arrived.</li>
    <li><b>Article 15, right of access; Article 17, erasure.</b> Absence proofs (§25) make "we hold no record of you" a provable statement rather than an assurance, and tombstoned erasure (§26) gives a data subject proof their record existed and was deleted, while holding none of it.</li>
    <li><b>Article 9, risk management.</b> The nine core signals are not a risk taxonomy and are not offered as one. What the platform evidences is that a defined, versioned risk-management ruleset was in force at a given moment and governed the decisions taken under it — the taxonomy remains the operator's, the proof that it operated is the platform's.</li>
    <li><b>Article 20, corrective action.</b> Downstream lineage (§29) answers "which outputs were affected by this faulty input" as a query rather than a fire drill, and the scope of the recall is itself sealed and dated, so it can be shown not to have been narrowed to suit.</li>
    <li><b>Value-chain and third-party obligations.</b> Cross-organisation lineage (§29) is the first mechanism here that follows an outcome past the boundary of the company that produced it.</li>
  </ul>
  <div class="honest"><b>Stated precisely, because precision is the product:</b> these tools help an organisation <b>evidence</b> its obligations — they produce tamper-evident, explainable, independently verifiable records of what its systems decided and why. They do not, on their own, make an organisation compliant, and no software does. Compliance is an organisational discipline; this is the evidence layer underneath it.</div>

  <h2 id="s19"><span class="n">19.</span>Deployment and pricing</h2>
  <p>The platform runs two ways. <b>Cloud:</b> integrate against the hosted API — a few lines of code where your system makes decisions, an API key for the paid engine, nothing for the notaries. <b>Sovereign:</b> for organisations whose data cannot leave the building, the engine runs entirely inside your own network — decisions, chain and database on your hardware. Licensing for sovereign deployments is offline by design: HMAC-signed 365-day tokens validated with pure cryptography, no phone-home, suitable for air-gapped environments.</p>
  <p>Pricing is deliberately simple: <b>50p per active device per month</b>. Partners embedding the platform set their own customer pricing and keep the margin above the platform fee. The notaries and Brain are free — they are the public proof the machinery works, and the standard (ai.txt) is open because standards only matter if anyone can adopt them.</p>
  <h3>The witnessing network is free, and structurally cannot be otherwise</h3>
  <p>Joining the witness network costs nothing and always will. There is no gate to price: the submission endpoint takes a tip from anybody, and as section 5 sets out, that openness is the mechanism by which the collusion objection is answered. A witness you must ask permission from is a weaker witness. Charging for admission would damage the thing being sold.</p>
  <p>What is charged for sits in the layer above, where real work happens: the engine that produces a chain worth witnessing in the first place, hosted chains for operators who will not run infrastructure, periodic evidence packs, certification and listing, dispute-time evidence bundles, and implementation work. This is the shape of every open protocol with a commercial layer on it — nobody charges for the transport, everybody charges for what runs on it.</p>
  <p>Two commitments follow, and they are architectural rather than promises. <b>The open protocol code never checks whether anyone has paid</b> — it has no concept of a subscription, so the claim that it is ungated is true by construction rather than by policy. And each paid service checks only its own status, so an operator who stops paying for hosting but runs their own infrastructure keeps sealing and keeps being witnessed indefinitely, with no gap in their record.</p>
  <p>Evidence packs are issued periodically: a customer's record for the period, with every seal, its witnesses, its anchors and the routes to verify each, as a document they own outright and may hand to anyone. Non-payment removes nothing — sealed history cannot be withdrawn without breaking the chain, and is not — but coverage stops, and the gap that opens cannot be filled in later at any price, because the only way to have had a period covered was to be covered during it.</p>

  <h2 id="s20"><span class="n">20.</span>Future potential</h2>
  <div class="fwd"><b>Everything in this section is forward-looking.</b> None of it is deployed today, and it is separated from the rest of the document for exactly that reason. Sections 1–19 and 22–30 describe what exists and can be verified now; this section describes where the architecture leads. Read the two differently.</div>
  <h3>What has moved out of this section</h3>
  <p>Mutual anchoring was described here as a future direction in v4. It shipped and is documented in section 5. Completeness, absence, erasure proofs, fork detection, reproducibility testing and cross-organisation lineage were unwritten when v5 was published on 1 August 2026; all six shipped in the following two days and are documented in sections 25 to 30. They are listed here only so readers of earlier versions can see what moved from intention to deployment, and when.</p>
  <h3>Key-signed intermittent sync — designed, not built</h3>
  <p>The witnessing spec currently assumes both parties run always-on servers, because the first two chains happened to. That assumption is not required by the design and excludes exactly the systems most in need of it: edge deployments, off-grid nodes, anything with intermittent connectivity. The proposed replacement removes it. A node registers a public key once and signs every tip thereafter, so identity binds to a signature rather than to a reachable address; tips are pushed in batches whenever the node reaches a network. Before pushing, the node pulls the peer's current tip and seals it into its own chain — so its offline work is bounded at <b>both</b> ends: no later than its sync by the peer's observation, and no earlier than its previous sync by the peer tip sealed inside it. The sync event becomes the proof rather than a gap in it. The residual limit is honest and inherent: the bounding is only as tight as the sync frequency, and within a long offline stretch the ordering remains the node's own assertion.</p>
  <h3>Signal Packs as a market</h3>
  <p>A pack is a versioned, hashable, portable artefact — which means it can be authored by someone other than the platform. A fraud consultancy, a child-safety charity, a trade body or a regulator could publish a pack encoding their own expertise, and any operator could load it and prove which version they ran. Two consequences follow. Expertise becomes distributable without becoming a consultancy engagement. And a sector body gains something it has never had: <b>a way to publish a standard that adopters can prove they actually applied</b>, rather than a PDF everyone claims to have read.</p>
  <h3>Evidence-priced risk</h3>
  <p>Insurers and lenders price uncertainty. Today an organisation's controls are assessed through questionnaires and periodic audit — self-report plus sampling. An anchored, reproducible decision history is a different class of input: continuous, externally verifiable, and impossible to dress up before an inspection. It is reasonable to expect verifiable evidence to eventually attract better pricing than asserted evidence, in cyber cover, professional indemnity and payment-fraud liability. That is a hypothesis about a market, not a product feature, and it is stated as one.</p>
  <h3>Admissibility and dispute</h3>
  <p>The notaries already produce records with the properties evidence law cares about: fixed content, fixed time, independent verifiability, no reliance on the interested party. The natural extension is tooling aimed at that use directly — export formats for disputes and small claims, verification a non-technical third party can complete unaided, and plain-language explanations of exactly what a seal does and does not establish. Much of the value here is not cryptographic but explanatory: <b>the proof already works; what is missing is a way for a non-specialist to rely on it confidently.</b></p>
  <h3>The standard as the long game</h3>
  <p>ai.txt and comply.txt are the smallest part of the platform by code and potentially the largest by consequence. Conventions of this shape — robots.txt, security.txt — succeed not by enforcement but by becoming the obvious thing to do, and value accrues to the reference implementation that got there first and kept practising it. The adoption path is deliberately staged: <b>technical</b> (the tools work and anyone can check), then <b>network</b> (enough operators declare and anchor that checking becomes routine), then <b>expectation</b> (an organisation without a declaration and a verifiable history looks like one with something to hide). Nothing about that sequence is guaranteed. It is, however, the reason the standard is open and the notaries are free.</p>
  <h3>What would have to be true</h3>
  <p>Honesty about a roadmap means naming its dependencies. A wide witness network requires peers willing to coordinate. Cross-organisation lineage requires a second organisation actually declaring its inputs — the mechanism is built and the graph is empty until somebody else joins it. A pack market requires authors with reputations worth attaching to their packs. Evidence-priced risk requires an underwriter prepared to move first. The standard requires adoption this platform cannot manufacture alone. Each is plausible; none is in hand. <b>The parts of this platform that exist do not depend on any of them</b> — which is the property that makes it responsible to write this section at all.</p>

  <h2 id="s21"><span class="n">21.</span>For investors</h2>
  <p>Written with the same rule as the rest of the document: no claims that cannot be checked, and limits stated plainly.</p>
  <h3>The market moment</h3>
  <p>Three regimes converge. The EU AI Act's transparency obligations and full penalty regime apply from <b>2 August 2026</b>, with high-risk obligations following in <b>December 2027</b> and <b>August 2028</b>, penalties measured in percentages of global turnover. The UK Online Safety Act and the 2024 Payment Services reimbursement rules are already in force. Every one shares a single practical demand: <b>records that survive scrutiny</b>. Most organisations meet that demand with editable database logs — which is to say, they do not meet it.</p>
  <p>The Omnibus delay is commercially useful rather than harmful, and any investor who raises it deserves the structural answer: obligations arriving in 2027 will be assessed against <b>historical</b> records, and evidence cannot be back-filled. That makes the intervening period the natural adoption window rather than a pause. Organisations that start recording in 2026 have a defensible history in 2028; those that wait do not, and cannot acquire one.</p>
  <h3>What exists today — checkable, not claimed</h3>
  <p>A deployed, running platform: the deterministic decision engine (~28ms), the tamper-evident chain with gapless receipts and public verification endpoints, <b>external anchoring of the chain tip to Bitcoin</b>, a live mutual witness network exchanging tips hourly with an independent platform, versioned Signal Packs sealed per decision, delegated-authority tokens, KYC result sealing, per-decision jurisdiction tagging, three free public notaries, the Brain instruction gate, the Guardian child-safety suite, Stripe-metered per-device billing with automatic quantity sync, and a partner/white-label programme. Added in August 2026: completeness and absence proofs, proof of erasure, fork detection, black-box reproducibility testing and cross-organisation lineage, plus a standalone offline verifier. All verifiable right now at sebbi.pro — including by recomputing the chain yourself, checking the anchor in a public ledger, and running the verifier on your own machine with the network disconnected. Built and operated by a solo founder at near-zero fixed cost.</p>
  <h3>The economics</h3>
  <p>Infrastructure, not consultancy: <b>50p per active device per month</b>, metered on real usage, billed automatically. Marginal cost per additional device is effectively zero; the same engine serves one customer or ten thousand. Partners and white-label operators build their own margin on top and bring their own customers — distribution that scales without headcount. The notaries, Brain, the witness network and the offline verifier are free by design: they are the demonstration layer that converts scrutiny into signups.</p>
  <h3>The moat</h3>
  <p>Five parts. <b>The chain</b>: switching costs rise every day a customer's evidence accrues, because an anchored history cannot be migrated mid-stream without breaking its own continuity — the anchors belong to the chain that was anchored. <b>Determinism</b>: a competitor building its governance layer on a model cannot offer reproducibility, and cannot retrofit it without rebuilding from the bottom; section 28 makes that difference testable by anyone in under a minute. <b>Time</b>: an unbroken witnessed record is the one input nobody can shortcut, because the only way to have had last year covered was to be in it last year. <b>The standard</b>: an open convention this platform originated and practises, and standards accrue value to their reference implementation. And least copyable, <b>the honesty position</b>: every competitor overclaims; a documented refusal to — limits stated on every page, in this document, and sealed into the platform's own chain — is precisely the property a buyer of evidence infrastructure is buying.</p>
  <h3>Stage, honestly stated</h3>
  <p>Pre-revenue. The platform is live with a 90-day free trial converting to metered billing; the pipeline is founder-led outreach and inbound from the free tools. The raise is a seed round with one purpose: to move the founder full-time onto the platform and fund the first sales and partnership cycle through the August 2026 transparency deadline and into the 2027 high-risk window — the period in which the historical record a customer will later need is either being created or is not.</p>
  <p><b>Contact:</b> justin@monopcontent.com — the technical demonstration takes fifteen minutes and every claim in sections 1–19 and 22–30 can be verified during it.</p>

  <h2 id="s22"><span class="n">22.</span>Conformance: measuring what cannot be guaranteed</h2>
  <p>Three claims in this document have a soft edge, and the same soft edge in each case: the arithmetic is sound, but the guarantee depends on something outside the engine.</p>
  <p>Commit-before-reveal proves ordering — but only if the integrator does not display the machine verdict to its reviewers before calling the endpoint. Mutual witnessing draws its strength from breadth — two platforms witnessing only each other prove very little. A declaration is only as strong as the rules declared — one that constrains nothing passes everything.</p>
  <p>None of these can be closed by the engine alone, and a vendor claiming otherwise would be overstating what software can do. What they can be is <b>measured</b>. A measured weakness is a different object from an unmeasured one: it can be reported, tracked, compared between deployments and put in front of an auditor. That is what conformance testing does here.</p>

  <h3>Probes — testing the integration rather than trusting it</h3>
  <p>The method is borrowed openly from how substantive audit has always worked, and specifically from a point made publicly by James Stokes of Red Flag AI Pro: put a case with a known answer into the queue, unannounced, and see who catches it.</p>
  <p>A probe creates a genuine oversight case whose machine verdict has been deliberately set to a known-wrong value. To the reviewer it is indistinguishable from any other case. Two things follow. If the reviewer agrees with the planted verdict, they did not evaluate the case — that is a caught rubber stamp, sealed like any other event. And if the integration is displaying the verdict before the case is opened, the reviewer's agreement rate on probes will track their agreement rate on ordinary cases; if they are genuinely deciding blind, it will not. <b>The gap between those two numbers is the conformance signal</b>, and it is the closest thing available to testing an integration you cannot see inside.</p>
  <p>A single probe establishes nothing about an individual. A catch rate across dozens is evidence about a process, and the process is what is under audit.</p>

  <h3>Breadth — concentration made visible</h3>
  <p>The witness network reports how many distinct peers are live, how concentrated observations are in the largest of them, and how many have gone quiet. Fewer than three live peers is reported as weak, because it is. A single peer pair carries an explicit warning that two parties witnessing only each other can still collude. None of this prevents a thin network. It prevents a thin network being presented as a thick one.</p>

  <h3>Strength — rules that never fire</h3>
  <p>Each rule in a live declaration is run against sealed records and reported on individually: how many records it actually constrained, meaning how many matched its condition and therefore had to satisfy its requirement. A rule that has never constrained a single record is named in the output as decoration rather than a standard. An operator can still publish a weak declaration. They can no longer publish one and have its weakness go unstated.</p>

  <p class="honest"><b>What conformance testing does not do.</b> Probes test a process, not a person: someone can catch a probe and rubber stamp the next hundred cases. A sufficiently motivated operator who identifies probe cases controls their own interface and can treat them differently — probe references carry no marking a reviewer can see, but that is a speed bump rather than a wall. And none of this is enforcement. Nothing here compels a platform to witness widely, declare strictly or integrate honestly. It makes the alternative visible, which is the most that an evidence layer can honestly claim to do.</p>

  <h2 id="s23"><span class="n">23.</span>Honest limits — read this</h2>
  <p>A whitepaper that only lists strengths is marketing. These are the limits, stated as plainly as the capabilities:</p>
  <ul>
    <li><b>Sealing proves integrity and timing, not truth at capture.</b> A sealed, anchored record proves exact content existed no later than an externally witnessed moment and has not changed since. It does not prove the contents were true when written — and no recording system of any kind does, which is a fact about recording rather than a defect of this one.</li>
    <li><b>Determinism costs cleverness.</b> The gate has no semantic understanding and will miss things a good classifier would catch. That trade is deliberate and permanent.</li>
    <li><b>Basis sealing proves what was relied on, not that it was right.</b> The chain shows a decision rested on invoice X, version Y, ruleset Z — unalterably. Whether X was genuine is a matter for process, not cryptography.</li>
    <li><b>Signal Packs prove which rules ran, not that they were the right rules.</b> Reproducibility is guaranteed; the judgement encoded in the thresholds remains a human one. The nine core signals are transaction-risk signals and are not a risk taxonomy for Article 9.</li>
    <li><b>Authority tokens prove the grant, not the wisdom.</b> A sealed token proves who was empowered, to what limit, until when — not that granting it was a good idea.</li>
    <li><b>Jurisdiction tagging records applicable frameworks; it does not decide law.</b> Courts decide legal authority. The tag is a versioned, sealed mapping — nothing grander, deliberately.</li>
    <li><b>Brain's filter is a first line, not a wall.</b> Known-dangerous patterns are caught, including obfuscated forms. Novel phrasings can pass. The guarantee is the sealed record of every decision, not perfect detection.</li>
    <li><b>Fingerprint matching is exact.</b> The notaries prove an identical file or text. A re-encoded copy, a paraphrase or a re-saved image produces a different fingerprint and will not match.</li>
    <li><b>Anchoring inherits Bitcoin's assumptions.</b> The external timestamp is as durable as the ledger carrying it. A conservative choice — but a dependency, named here rather than hidden.</li>
    <li><b>Human oversight sealing proves order, not thought.</b> <i>(Measured — see section 22.)</i> Commit-before-reveal proves a reviewer decided before the machine's verdict was disclosed to them. It cannot prove they read the material — a screen can be left open — and dwell time is gameable by anyone deliberately gaming it. Most importantly the guarantee depends entirely on the integration: if a platform shows the verdict to its own staff before calling the API, the sealed order proves nothing.</li>
    <li><b>Witnessing proves a tip existed, not that its contents are true.</b> <i>(Breadth measured — see section 22.)</i> Two platforms witnessing only each other prove very little; the strength comes from breadth. And no design can compel a peer to keep publishing — silence is made visible, not prevented.</li>
    <li><b>Reconciliation proves consistency, not truth.</b> It tests systems the operator controls against each other, on records they could not select. An operator fabricating coherently across every system in real time will pass. It raises the cost of lying; it does not make lying impossible.</li>
    <li><b>Declarations are only as strong as the rules declared.</b> <i>(Strength measured — see section 22.)</i> A declaration requiring nothing passes everything. The protection is that the rules themselves are published and version-sealed, so a weak standard and a weakened standard are both visible — not that the standard is good.</li>
    <li><b>Completeness covers what was sealed, not what never arrived.</b> <i>(See section 25.)</i> A period's total is fixed before any export is requested, so the sealed set cannot be cherry-picked. A decision that never reached the engine at all is outside anything the chain can see.</li>
    <li><b>Absence proofs are scoped to a period, and disclose neighbours.</b> "No record of you, ever" means checking every committed period, which is why the period list is public. And an absence proof reveals the two adjacent keys; where keys are themselves sensitive they should be hashed before they become leaves.</li>
    <li><b>Fork detection needs someone to look.</b> <i>(See section 27.)</i> A fork is only caught if a holder of an old tip actually checks it. If nobody keeps our tips, there is nothing to catch us with — which is why the route is public, free and automatable.</li>
    <li><b>Reproducibility is not fairness.</b> <i>(See section 28.)</i> That the same inputs still produce the same verdict says nothing about whether the verdict was correct or the inputs honestly captured. And an open scoring oracle can be probed: a determined party submitting many varied inputs can map a decision boundary without seeing any code. That exposure is real, mitigated rather than eliminated, and disclosed here rather than discovered later.</li>
    <li><b>A lineage edge is a claim, not a proof of the claim.</b> <i>(See section 29.)</i> Sealing makes it dated and non-repudiable; it never made it true. Declaring inputs is voluntary, and a party who declares nothing is simply the point at which someone else's trail goes dark.</li>
    <li><b>None of these find what was never recorded.</b> Reconciliation, declarations and completeness test sealed records. A decision that was never sent to the engine cannot violate a rule or fail a sample. Gapless receipts cover omission at the point of issue; nothing covers a system that was never connected.</li>
    <li><b>Authority continuity proves derivation, not merit.</b> <i>(See section 31.)</i> It proves the authority used was derivable from a human grant — not that the human should have issued it, and not that the parameters describe something that really happened. Grants are authenticated by sealing rather than per-issuer signatures, so an outside party verifies them through the chain rather than entirely offline; signature-based offline verification of grants is a known extension and is not built.</li>
    <li><b>A composed verdict is only half re-derivable.</b> The authority half can be re-run by anyone from the published rules. The risk half needs the scoring engine and cannot be, which the exported bundle states rather than glosses over. Where the authority verdict is BLOCK the composed verdict stands regardless, because composition takes the worse of the two.</li>
    <li><b>Section 20 is not a product.</b> Everything remaining in Future Potential is unbuilt and depends on parties outside this company. Nothing in the built sections depends on any of it.</li>
    <li><b>The tools evidence compliance; they do not confer it.</b> Regulators assess organisations, not endpoints. This platform makes your records provable; your obligations remain yours.</li>
  </ul>
  <p>Every one of these limits is stated on the product pages as well. A system whose whole value is honesty cannot afford a single overclaim — and a vendor who tells you their limits is giving you the strongest evidence available about how they will behave when it matters.</p>

  <h2 id="s24"><span class="n">24.</span>Verify everything yourself</h2>
  <p>Nothing in this document asks to be believed. Every claim about the chain is checkable from outside, now, without an account:</p>
  <ul>
    <li><b>Verify the whole chain</b> — the public verification endpoint recomputes every seal from genesis and reports either integrity or the exact block where tampering begins.</li>
    <li><b>Check the anchor</b> — the live anchor endpoint returns the current chain tip, the OpenTimestamps proof file and how many independent calendars have stamped it. Take the proof and verify it against Bitcoin with any OpenTimestamps client. Nothing about that check involves us.</li>
    <li><b>Check any receipt</b> — the inclusion endpoint confirms whether a given sealed hash is in the chain, with its block index and sequence.</li>
    <li><b>Re-derive a decision</b> — take the sealed inputs and the sealed pack version, apply the published formula, and confirm the verdict was what the rules dictated.</li>
    <li><b>Test reproducibility with your own inputs</b> — send anything you like to the challenge endpoint, keep the input fingerprint, and send it again next month from anywhere. Every run is sealed. <code>/x/replay/spec</code></li>
    <li><b>Ask what a period contained</b> — the committed total for any sealed period, fixed before any export was requested. <code>/x/complete/periods</code></li>
    <li><b>Ask about something that isn't there</b> — request a proof for any value at all and receive an absence proof against the sealed root. <code>/x/complete/prove</code></li>
    <li><b>Check we never forked</b> — hand back any tip we ever gave you and we prove it is still on the chain we serve today, in the same position. <code>/x/consistency/ancestor</code></li>
    <li><b>Check the log is append-only</b> — a prefix proof between any two sizes, showing nothing was inserted, removed or reordered. <code>/x/consistency/proof</code></li>
    <li><b>Follow a decision across companies</b> — trace upstream, or run it backwards to see what an input produced. <code>/x/lineage/trace</code> · <code>/x/lineage/impact</code></li>
    <li><b>Read the authority rules</b> — enough to reimplement the evaluator and disagree with our result. <code>/x/continuity/spec</code></li>
    <li><b>Open a real authority decision</b> — blocks listed beside allows, each carrying its own links, and the whole path back to the human who granted it. <code>/x/continuity/decisions</code> · <code>/x/continuity/trace</code></li>
    <li><b>Export a signed proof and check it without us</b> — with no identifier it returns the most recent, so you can start knowing nothing. <code>/x/continuity/proof</code> · <code>/verify-authority.py</code></li>
    <li><b>Run the offline verifier</b> — one file, no dependencies, no network. Check every proof above on your own machine with the wifi off, and run <code>--selftest</code> first so you are not trusting the tool either.</li>
    <li><b>Seal something yourself</b> — use the notaries with no account: seal a post, verify it, then change one character and watch verification fail.</li>
    <li><b>Read the gate's code</b> — download Brain and read every line before running it.</li>
    <li><b>Ask who witnessed us</b> — the attestation endpoint answers whether a given peer's tip was witnessed and when, and returns the block it was sealed in. Peers who have gone silent are reported as silent.</li>
    <li><b>Witness us yourself</b> — take our tip and seal it wherever you like. No account, no key, no permission. We have no way to know you are doing it, which is the point.</li>
    <li><b>Check a reviewer's record</b> — the oversight endpoints return median dwell time, divergence rate and the proportion of sub-two-second decisions per reviewer. A reviewer who has never once diverged is reported as such.</li>
    <li><b>Read our declaration and its history</b> — the rules we hold ourselves to, every version ever published, with the dates. If we have ever loosened our own standard, it is there.</li>
  </ul>
  <p><b>Check us. Don't trust us.</b> That is not a slogan; it is the system's design requirement, and the only standard by which an evidence layer should ever be judged.</p>

  <h2 id="s25"><span class="n">25.</span>Completeness: proving what isn't there</h2>
  <p>Every audit log in existence proves what happened. None of them prove what didn't.</p>
  <p>A hash chain proves inclusion. It cannot prove exclusion. So when a firm hands an examiner four hundred decisions, there is nothing in the mathematics that shows it was not six hundred. Gapless receipts (§6) protect whoever holds a receipt, but they say nothing to a third party auditing the set as a whole. Every audit ever conducted has run on the assumption that the sample handed over is the whole sample. That assumption has never been provable. It has simply been accepted.</p>
  <h3>The mechanism</h3>
  <p>At the close of each period, every record sealed in it is taken, <b>sorted</b>, built into a Merkle tree, and the root and the exact count are sealed into the chain — and from there anchored externally and witnessed like everything else. Crucially this happens before anybody has asked for anything.</p>
  <p>Sorting is the whole trick. In an unsorted tree you can only prove a leaf is present. In a sorted one you can prove a leaf is <b>absent</b>: produce the two leaves either side of where the queried value would have sorted, verify both against the sealed root, and show their indices are consecutive. Nothing can exist between two adjacent leaves of a sorted tree.</p>
  <div class="gap">
    <div class="lf"><span>leaf 4,117</span>a3f1c8…</div>
    <div class="vd">nothing<br>can be<br>here</div>
    <div class="lf"><span>leaf 4,118</span>a3f4e2…</div>
  </div>
  <p>Three claims become checkable, by anyone, with no account:</p>
  <ul>
    <li><b>Inclusion</b> — this record is inside the sealed set for the period and cannot have been added afterwards.</li>
    <li><b>Absence</b> — no record for this value exists in the period. Not "we looked and found nothing", which is a report about our diligence. A proof, against a root fixed before the question was asked.</li>
    <li><b>Completeness</b> — the total was committed in advance. An export claiming four hundred against a sealed six hundred is contradicting an externally anchored number, and the arithmetic exposes it without argument.</li>
  </ul>
  <h3>Why commitments are frozen</h3>
  <p>A commitment is worth nothing if it can be recomputed later to suit circumstances. So a period can only be committed once it has <b>closed</b> — attempting to commit a live period is refused, because more records could still arrive. A period can only be committed <b>once</b>; a second attempt returns the existing root rather than a new one. And the sorted leaf list is <b>stored at commit time</b> rather than recomputed on demand, so proofs issued this year still verify against the root sealed this year even after records are erased next year.</p>
  <p>Two commitment types are supported: over the receipts themselves, and over the distinct subjects those records concerned — which is what turns "do you hold anything about me" into an answerable question. The tree is built over key material only and never over content, so a leaf reveals whether something exists, not what it said.</p>
  <p class="honest"><b>What this does not do.</b> It proves completeness of what was <b>sealed</b>. A decision that never reached the chain is outside anything it can see; garbage in still applies. What changes is that the operator can no longer choose which of the sealed records to show. Absence is scoped to a period, so "no record, ever" means checking every committed period — which is why the period list is public, and why a missing period is itself a visible fact worth asking about. And an absence proof discloses the two neighbouring keys, so where keys are sensitive they should be hashed before they become leaves; the proof works identically and we hold nothing legible.</p>

  <h2 id="s26"><span class="n">26.</span>Erasure without breaking the chain</h2>
  <p>There is a contradiction sitting inside every append-only compliance product, this one included, and most vendors disclaim it rather than solve it: append-only and the right to erasure do not obviously coexist. If nothing can be removed, how can a person's data be deleted? And if it can be removed, what was the chain for?</p>
  <p>Section 14 gives half the answer — personal data lives in the operator's own systems and is deleted there, while the chain holds only a fingerprint that resolves to nothing. This section gives the other half: proving to the person who asked that it actually happened.</p>
  <h3>Tombstones</h3>
  <p>The payload is deleted by the operator's own system. The <b>position</b> in the tree remains, and the erasure itself is sealed as its own dated event. What can then be established, holding none of the content:</p>
  <ul>
    <li>a record existed;</li>
    <li>it was erased;</li>
    <li>and when — against a timestamp nobody involved controls.</li>
  </ul>
  <p>A data subject therefore receives <b>proof of erasure</b> rather than an assurance of it, and the organisation receives something equally useful: evidence it complied, which survives the deletion of the very data that would otherwise have been the evidence.</p>
  <p>Roots committed before the erasure still contain the leaf, and that is correct rather than a leak. A leaf is key material, not content; and a root that changed after the fact would prove nothing about anything, which would defeat the whole structure. Combined with the DSR notary in section 14 — receipt, assessment, deadline and completion all sealed in order — an organisation can evidence the entire lifecycle of a request without retaining a single field of the data it was asked to destroy.</p>
  <p class="honest"><b>Honest scope:</b> the tombstone proves the erasure was <b>recorded</b>, and that the record cannot have been backdated. It does not prove every copy in every backup and downstream system was actually destroyed — that is an operational discipline, and no cryptographic structure can reach into systems it does not sit in.</p>

  <h2 id="s27"><span class="n">27.</span>Fork detection: proving we never ran two histories</h2>
  <p>Mutual witnessing means several parties hold hashes of our chain. Until now, none of them could check whether they were all holding hashes of the <b>same</b> chain.</p>
  <p>Nothing in the design so far stopped an operator running two histories in parallel: serve chain A to a witness, chain B to an auditor. Both receive a valid tip. Both anchor it. Both verify perfectly against the copy they were given. Neither can tell, because there was no way to ask the question that would expose it

```
