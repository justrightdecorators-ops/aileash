# Codebase — part 18 of 22

Contains:
- `investor-prospectus.html`
- `legal.txt`
- `liability.txt`
- `llms.txt`
- `notary.html`
- `pay-check.html`
- `registry.html`
- `report-threat.html`
- `requirements.txt`


## `investor-prospectus.html`

291 lines, 20880 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sebbi.pro — Seed Round Prospectus</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#FAFAF6;--ink:#14171C;--ink-soft:#454B54;--chain:#2E5E4E;
  --chain-light:#E4ECE8;--alert:#9C2F26;--alert-light:#F5E6E3;--line:#DEDBD1;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2,h3,.display{font-family:'Newsreader',serif;font-weight:500;letter-spacing:-0.01em}
.mono{font-family:'IBM Plex Mono',monospace}
a{color:var(--chain)}
.wrap{max-width:760px;margin:0 auto;padding:0 28px}

header{padding:56px 0 40px;border-bottom:1px solid var(--line)}
.doc-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
h1{font-size:clamp(34px,5vw,48px);line-height:1.1;max-width:16ch;margin-bottom:16px}
.tagline{font-size:17px;color:var(--ink-soft);max-width:52ch}

.block{position:relative;padding:8px 0 44px 24px;border-left:1px solid var(--line);margin-left:4px}
.block:last-of-type{border-left:1px solid transparent}
.block-num{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--chain);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:10px}
.block h2{font-size:26px;margin-bottom:16px}
.block h3{font-size:17px;margin:22px 0 8px}
.block p{font-size:15.5px;color:var(--ink-soft);margin-bottom:14px;max-width:60ch}
.block p:last-child{margin-bottom:0}
.block ul{margin:0 0 14px 18px}
.block li{font-size:15px;color:var(--ink-soft);margin-bottom:8px;max-width:58ch}
.block li b,.block p b{color:var(--ink)}

.dates{background:white;border:1px solid var(--line);border-radius:4px;margin:20px 0;overflow:hidden}
.date-row{display:grid;grid-template-columns:130px 1fr;border-bottom:1px solid var(--line)}
.date-row:last-child{border-bottom:none}
.date-row.head{background:var(--ink)}
.date-row.head .dd,.date-row.head .dw{color:white;font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:0.08em;text-transform:uppercase}
.dd{padding:12px 16px;font-family:'IBM Plex Mono',monospace;font-size:12.5px;font-weight:600;border-right:1px solid var(--line)}
.dw{padding:12px 16px;font-size:14px;color:var(--ink-soft);line-height:1.55}
.dw b{color:var(--ink)}
.date-row.key .dd{color:var(--alert)}
@media(max-width:560px){.date-row{grid-template-columns:1fr}.dd{border-right:none;padding-bottom:0}}

.countdown{background:var(--alert-light);border:1px solid rgba(156,47,38,0.2);border-radius:4px;padding:20px 24px;margin:20px 0}
.countdown-label{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--alert);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px}
.countdown-days{font-family:'Newsreader',serif;font-size:38px;font-weight:600;color:var(--alert);line-height:1}
.countdown-sub{font-size:13px;color:var(--ink-soft);margin-top:6px;line-height:1.6}

.proof-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
@media(max-width:560px){.proof-grid{grid-template-columns:1fr}}
.proof{background:white;border:1px solid var(--line);padding:18px 20px;border-radius:4px}
.proof-n{font-family:'Newsreader',serif;font-size:26px;font-weight:600;color:var(--chain)}
.proof-l{font-size:12.5px;color:var(--ink-soft);margin-top:3px}
.proof-src{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#999;margin-top:6px}

.status-list{margin-top:16px;display:flex;flex-direction:column;gap:0}
.status-row{display:flex;align-items:flex-start;gap:12px;padding:11px 0;border-bottom:1px solid var(--line)}
.status-row:last-child{border-bottom:none}
.status-icon{font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:600;flex-shrink:0;width:20px;padding-top:2px}
.status-icon.yes{color:var(--chain)}
.status-icon.no{color:var(--alert)}
.status-text strong{color:var(--ink);font-weight:600}
.status-text span{color:var(--ink-soft);font-size:14.5px}

.ask-box{background:var(--ink);color:var(--paper);border-radius:4px;padding:32px;margin-top:20px}
.ask-amount{font-family:'Newsreader',serif;font-size:44px;font-weight:600;color:white}
.ask-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#8FA89C;margin-bottom:6px}
.use-of-funds{margin-top:24px;display:flex;flex-direction:column;gap:10px}
.uf-row{display:flex;justify-content:space-between;align-items:baseline;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.12);font-size:14px}
.uf-row:last-child{border-bottom:none}
.uf-pct{font-family:'IBM Plex Mono',monospace;color:#8FA89C}

.risk-box{background:white;border:1px solid var(--line);border-left:3px solid var(--alert);padding:20px 24px;border-radius:2px;margin-top:16px}
.risk-box h4{font-size:14px;margin-bottom:8px;color:var(--ink)}
.risk-box p{font-size:13.5px;color:var(--ink-soft);margin-bottom:8px}
.risk-box p:last-child{margin-bottom:0}

.verify-box{background:var(--chain-light);border:1px solid rgba(46,94,78,0.25);border-radius:4px;padding:20px 24px;margin-top:18px}
.verify-box h4{font-size:15px;margin-bottom:10px}
.verify-box p{font-size:14px;margin-bottom:8px}
.verify-box code{font-family:'IBM Plex Mono',monospace;font-size:12.5px;background:white;border:1px solid var(--line);padding:2px 7px;border-radius:3px;color:var(--chain)}

.contact-block{padding:44px 0 64px}
.contact-card{background:var(--chain-light);border:1px solid rgba(46,94,78,0.2);border-radius:4px;padding:28px}
.contact-card h3{font-size:20px;margin-bottom:10px}
.contact-card p{font-size:14.5px;color:var(--ink-soft);margin-bottom:16px}
.contact-links{display:flex;flex-direction:column;gap:6px;font-family:'IBM Plex Mono',monospace;font-size:14px}
.contact-links a{color:var(--chain);text-decoration:none;font-weight:500}

footer{padding:0 0 48px}
footer p{font-family:'IBM Plex Mono',monospace;font-size:11px;color:#999;line-height:1.8}

@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>
</head>
<body>

<div class="wrap">

<header>
  <div class="doc-label">
    <span>Seed Round Prospectus &middot; v2.0</span>
    <span id="doc-date">&mdash;</span>
  </div>
  <h1>Compliance evidence cannot be back-filled. That is the whole business.</h1>
  <p class="tagline">Sebbi.pro / AILeash &mdash; a live, publicly verifiable evidence layer for AI decisions. Pre-revenue. Solo-built. Raising &pound;500,000 to go full-time and convert a working platform into a paying one.</p>
</header>

<div class="block">
  <div class="block-num">Block 01 &mdash; The Deadline, Stated Correctly</div>
  <h2>Not one date. Four &mdash; and the important one is 2027.</h2>
  <p>Most pitches in this category quote a single EU AI Act deadline. That is wrong, and any investor who checks will find it wrong. The dates moved under the AI Omnibus, and they moved differently for different duties.</p>

  <div class="dates">
    <div class="date-row head"><div class="dd">Date</div><div class="dw">What applies</div></div>
    <div class="date-row"><div class="dd">2 Aug 2026</div><div class="dw"><b>Transparency duties.</b> Disclose AI interaction, mark AI-generated content machine-readably, disclose deepfakes. Commission enforcement powers over general-purpose models begin.</div></div>
    <div class="date-row"><div class="dd">2 Dec 2026</div><div class="dw"><b>Content-marking grace period ends</b> &mdash; cut from six months to three. Prohibition on AI-generated NCII and CSAM takes effect.</div></div>
    <div class="date-row key"><div class="dd">2 Dec 2027</div><div class="dw"><b>High-risk duties, standalone systems</b> &mdash; Articles 9, 12, 13, 14. Delayed from August 2026. <b>This is the commercially relevant date.</b></div></div>
    <div class="date-row"><div class="dd">2 Aug 2028</div><div class="dw"><b>High-risk duties for AI embedded in products.</b></div></div>
  </div>

  <p>Fines reach 3% of global annual turnover or &euro;15m, whichever is higher, per violation.</p>

  <h3>Why a delay is a market, not a problem</h3>
  <p>The delay reads like breathing room and is the opposite. <b>The evidence those obligations require is historical.</b> In December 2027 an auditor asks what a system decided in 2026 and why. That record either exists or it does not, and it cannot be reconstructed afterwards.</p>
  <p>Every month between now and then is a month of evidence nobody is collecting. The addressable moment is not the deadline &mdash; it is now.</p>

  <div class="countdown">
    <div class="countdown-label">Time to high-risk obligations</div>
    <div class="countdown-days mono" id="countdown-days">&mdash; days</div>
    <div class="countdown-sub">Calculated against 2 December 2027. Every day of it is a day of unrecoverable evidence for any organisation not yet recording.</div>
  </div>
</div>

<div class="block">
  <div class="block-num">Block 02 &mdash; What Is Actually Built</div>
  <h2>Live in production. Verifiable without asking us.</h2>
  <p>Sebbi.pro runs in production on Railway today. It is not a deck and not a demo environment: a deterministic decision engine, a tamper-evident audit chain, external timestamping, and an extensible module layer &mdash; all of it checkable by a third party with no account and no permission.</p>

  <div class="proof-grid">
    <div class="proof">
      <div class="proof-n mono">28ms</div>
      <div class="proof-l">Median decision time</div>
      <div class="proof-src">Measured on live production traffic</div>
    </div>
    <div class="proof">
      <div class="proof-n mono">SHA-256</div>
      <div class="proof-l">Hash-chained audit ledger</div>
      <div class="proof-src">Tamper-evident by construction</div>
    </div>
    <div class="proof">
      <div class="proof-n mono">9</div>
      <div class="proof-l">Live capability modules</div>
      <div class="proof-src">Added without touching the core server</div>
    </div>
    <div class="proof">
      <div class="proof-n mono">4</div>
      <div class="proof-l">Products: AILeash, Guardian, SonicBoom, Sentinel</div>
      <div class="proof-src">Shared engine, shared audit chain</div>
    </div>
  </div>

  <h3>What was added in the most recent build cycle</h3>
  <ul>
    <li><b>Human oversight, commit-before-reveal.</b> The reviewer's decision is sealed before the machine's verdict is disclosed to them, with dwell time and divergence rate recorded. This is the first mechanism in the category that distinguishes independent judgement from a rubber stamp.</li>
    <li><b>Mutual witnessing.</b> Platforms seal each other's chain tips, so one operator's history sits inside chains they do not control. Rewriting your own past becomes a conspiracy between competitors rather than a database operation.</li>
    <li><b>Reconciliation.</b> Sealed records are tested against the operator's own live system, with the sample derived from the current chain tip and sealed before any data is requested &mdash; so the sample cannot be chosen to flatter.</li>
    <li><b>Declarations.</b> An operator publishes the rules their decisions must satisfy; the rules are sealed before the records they judge, and every version is retained, so a standard cannot be quietly loosened.</li>
    <li><b>Conformance testing.</b> Probes with deliberately wrong verdicts, breadth measurement on the witness network, and per-rule strength scoring &mdash; the instrument that detects the platform's own failure modes.</li>
    <li><b>Data subject request notary.</b> The erasure and access lifecycle sealed without the chain ever holding the subject's identity.</li>
  </ul>
</div>

<div class="block">
  <div class="block-num">Block 03 &mdash; The Differentiator</div>
  <h2>Every claim carries its own limit.</h2>
  <p>The published whitepaper contains a section listing what the platform <b>cannot</b> do &mdash; sixteen numbered limitations at present. Witnessing proves a tip existed, not that its contents are true. Reconciliation proves consistency, not truth. Oversight sealing proves order, not thought.</p>
  <p>No competitor in this category publishes that list. It reads like a weakness and functions as the opposite: a buyer evaluating compliance infrastructure is trying to work out which vendor is overstating. A vendor who names their own ceiling first is the one who survives due diligence.</p>
  <p>It is also defensible commercially. The limits are structural rather than fixable, so a competitor cannot simply close them &mdash; they can only match the honesty, which costs them their existing marketing.</p>

  <div class="verify-box">
    <h4>Verify the technical claims before reading further</h4>
    <p>Nothing here requires trusting the document. <code>/api/verify-chain</code> recomputes the entire chain and reports whether it is intact. <code>/api/anchor-status</code> returns the live chain tip, its OpenTimestamps proof and the number of independent calendar servers that have stamped it. <code>/x/witness/attest</code> answers whether a given peer tip was witnessed and when.</p>
    <p style="margin-bottom:0">All three are public, need no account, and answer to anyone.</p>
  </div>
</div>

<div class="block">
  <div class="block-num">Block 04 &mdash; Where Things Actually Stand</div>
  <h2>Told straight, not spun.</h2>
  <p>Technical and regulatory credibility now. Commercial traction still ahead. That is the honest picture and it is precisely why this is a seed round rather than a later one.</p>
  <div class="status-list">
    <div class="status-row"><div class="status-icon yes">YES</div><div class="status-text"><strong>Platform live in production</strong> &mdash; <span>real infrastructure, publicly verifiable, not a demo environment</span></div></div>
    <div class="status-row"><div class="status-icon yes">YES</div><div class="status-text"><strong>Ofcom submission acknowledged</strong> &mdash; <span>whitepaper submitted to the Additional Safety Measures consultation, with publication consent granted</span></div></div>
    <div class="status-row"><div class="status-icon yes">YES</div><div class="status-text"><strong>An organisation actively testing the API</strong> &mdash; <span>a signed-up account has put live calls through the engine</span></div></div>
    <div class="status-row"><div class="status-icon yes">YES</div><div class="status-text"><strong>Inbound interest from the sector</strong> &mdash; <span>including a board-level contact in regulated financial services, and profile-level interest from a competing governance platform</span></div></div>
    <div class="status-row"><div class="status-icon no">NO</div><div class="status-text"><strong>Paying customers</strong> &mdash; <span>none confirmed. This is the gap the raise closes, and it should be read as the central risk.</span></div></div>
    <div class="status-row"><div class="status-icon no">NO</div><div class="status-text"><strong>External security audit</strong> &mdash; <span>not yet commissioned. Budgeted within this round.</span></div></div>
  </div>
</div>

<div class="block">
  <div class="block-num">Block 05 &mdash; Route to Revenue</div>
  <h2>Sell to the platforms, not one customer at a time.</h2>
  <p>Twenty months of direct selling produced no revenue. The diagnosis is not the product: compliance infrastructure is bought on a trigger &mdash; an audit, a regulator letter, a customer questionnaire &mdash; and a single founder cannot be in front of enough triggered buyers to make direct sales work.</p>
  <p>The current strategy inverts it. Other compliance platforms already hold relationships with triggered buyers and are uniformly weak on evidence. The engine is offered to them as an evidence layer beneath their own product, at 50p per device per month, which they mark up.</p>
  <ul>
    <li><b>Founding cohort of twenty platforms</b> &mdash; free integration, pricing locked, a say in the specification, and the live verification mark for their own site.</li>
    <li><b>Compounding effect</b> &mdash; each integrating platform strengthens the witness network for the others, so early participants gain from later ones joining.</li>
    <li><b>The standard as the long game</b> &mdash; whoever writes the integration specification the market adopts holds a position no feature can dislodge.</li>
  </ul>
  <p>This is a distribution thesis rather than a product thesis, and it is the reason the raise funds sales capacity ahead of engineering.</p>
</div>

<div class="block">
  <div class="block-num">Block 06 &mdash; The Ask</div>
  <h2>&pound;500,000. A specific plan, not a placeholder.</h2>
  <p>A pre-revenue seed round. The money funds the gap between a working platform and a proven one: going full-time, landing the founding cohort, and building the evidence base a larger round would require.</p>
  <div class="ask-box">
    <div class="ask-label">Raising</div>
    <div class="ask-amount">&pound;500,000</div>
    <div class="use-of-funds">
      <div class="uf-row"><span>Founder salary (full-time)</span><span class="uf-pct">~25%</span></div>
      <div class="uf-row"><span>First technical/sales hire</span><span class="uf-pct">~30%</span></div>
      <div class="uf-row"><span>External security audit, legal review of claims and contracts</span><span class="uf-pct">~15%</span></div>
      <div class="uf-row"><span>Infrastructure scaling and redundancy</span><span class="uf-pct">~15%</span></div>
      <div class="uf-row"><span>Runway buffer (18 months)</span><span class="uf-pct">~15%</span></div>
    </div>
  </div>
</div>

<div class="block">
  <div class="block-num">Block 07 &mdash; Risk, Named Plainly</div>
  <h2>What could go wrong.</h2>
  <div class="risk-box">
    <h4>No customers yet</h4>
    <p>The central commercial risk, and it has persisted for twenty months. The platform strategy is a response to that, not a hedge against it. If the founding cohort does not fill, the thesis is wrong and should be treated as such.</p>
  </div>
  <div class="risk-box">
    <h4>Solo-built, single point of failure</h4>
    <p>Deep founder knowledge, but key-person dependency and no external code review to date. Part of this raise is hiring and commissioning an audit specifically to reduce both.</p>
  </div>
  <div class="risk-box">
    <h4>Infrastructure concentration</h4>
    <p>Single hosting provider, single replica, SQLite. Adequate at current load and inadequate at scale. Budgeted within this round and stated here rather than discovered later.</p>
  </div>
  <div class="risk-box">
    <h4>Regulatory timing</h4>
    <p>The high-risk deadline has already moved once. It could move again, which would extend the sales cycle. The historical-evidence argument holds regardless of the date, but the urgency does not.</p>
  </div>
  <div class="risk-box">
    <h4>Competitive category</h4>
    <p>AI compliance tooling is an active space with well-funded entrants. Differentiation rests on the verifiable evidence layer and on published limitations, not on being first.</p>
  </div>
</div>

</div>

<div class="contact-block wrap">
  <div class="contact-card">
    <h3>Get in touch directly</h3>
    <p>Happy to walk through the platform live, share the Ofcom submission, or go deeper on the chain architecture and the witness model.</p>
    <div class="contact-links">
      <a href="mailto:justrightdecorators@gmail.com">justrightdecorators@gmail.com</a>
      <a href="tel:07908269428">07908 269428</a>
      <a href="https://sebbi.pro">sebbi.pro</a>
      <a href="https://sebbi.pro/whitepaper">sebbi.pro/whitepaper</a>
    </div>
  </div>
</div>

<footer class="wrap">
  <p>Justin Antony Dobson &middot; Monop Content &middot; Blyth, Northumberland, UK<br>
  This document is a summary for informational purposes and does not constitute an offer of securities. All figures are stated as of the date above and should be independently verified before any investment decision. Regulatory dates are stated as amended by the AI Omnibus and are subject to further change.</p>
</footer>

<script>
  document.getElementById('doc-date').textContent = new Date().toLocaleDateString('en-GB',{day:'numeric',month:'long',year:'numeric'});
  var deadline = new Date('2027-12-02T00:00:00Z');
  var now = new Date();
  var days = Math.max(0, Math.ceil((deadline - now) / (1000*60*60*24)));
  document.getElementById('countdown-days').textContent = days.toLocaleString() + ' days';
</script>

</body>
</html>

```


## `legal.txt`

69 lines, 3099 bytes

```text
# LEGAL.TXT — Legal Declaration and Rights Notice
# sebbi.pro | Monop Content | Justin Antony Dobson
# Published: June 2026
# Linked to: sebbi.pro/ai.txt | sebbi.pro/dis.txt
# Verification: sebbi.pro/api/verify-chain

## Ownership Declaration

This domain, sebbi.pro, and all intellectual property associated with it, including but not limited to AILeash, AILeash Guardian, SonicBoom, AILeash Sentinel, and OAAS-1.0, are the sole property of Justin Antony Dobson, trading as Monop Content, Blyth, Northumberland, United Kingdom.

Protected under:
- Copyright, Designs and Patents Act 1988
- UK Trade Secrets Regulations 2018
- EU AI Act 2024/1689
- Defamation Act 2013 (UK)

## Defamation and Misrepresentation Notice

Any individual, organisation, automated system, or artificial intelligence that publishes, generates, or distributes false, misleading, or defamatory statements about sebbi.pro, AILeash, OAAS-1.0, or Justin Antony Dobson is hereby on formal notice that:

1. The verified facts about this domain are declared at sebbi.pro/dis.txt
2. All access to this domain is cryptographically logged in a SHA-256 Merkle chain
3. That chain constitutes tamper-proof, timestamped evidence of what factual information was publicly available at the time of access
4. Any false statement made after accessing this domain will be treated as wilful misrepresentation with full knowledge of the facts
5. Such statements may constitute defamation under the Defamation Act 2013 and will be pursued accordingly

## Intellectual Property Notice

OAAS-1.0 is an original work created by Justin Antony Dobson in June 2026. The concept, structure, and implementation of the Open AI Audit Standard are protected intellectual property. Any adoption, implementation, or derivative of OAAS-1.0 must attribute authorship to Justin Antony Dobson and Monop Content.

The following are trademarks and trading names of Monop Content:
- AILeash
- AILeash Guardian
- SonicBoom
- AILeash Sentinel
- OAAS-1.0
- sebbi.pro

Unauthorised commercial use of these names is prohibited.

## Evidence Chain Declaration

This file, along with sebbi.pro/ai.txt and sebbi.pro/dis.txt, forms part of a cryptographically linked evidence package. The SHA-256 Merkle chain at sebbi.pro/api/verify-chain provides tamper-proof verification that these declarations existed and were publicly accessible from the date of publication.

This evidence package may be submitted in legal proceedings as proof of:
- Prior publication of facts
- Constructive notice to parties who accessed this domain
- Wilful disregard of declared facts by parties generating false information

## Contact for Legal Matters

Justin Antony Dobson
Monop Content
Blyth, Northumberland, United Kingdom
justrightdecorators@gmail.com
+44 7908 269428

## Linked Files

ai.txt: https://sebbi.pro/ai.txt
dis.txt: https://sebbi.pro/dis.txt
legal.txt: https://sebbi.pro/legal.txt
Verification: https://sebbi.pro/api/verify-chain
Registry: https://sebbi.pro/registry
Standard: https://sebbi.pro/ai-standard

© 2026 Justin Antony Dobson / Monop Content
All rights reserved.

```


## `liability.txt`

112 lines, 5653 bytes

```text
OAAS-1.0 — LIABILITY & ROLE ADDENDUM
Monop Content / AILeash (sebbi.pro)
Drafted for review by a qualified solicitor before publication. This is not legal advice.

================================================================================
1. ROLE DEFINITION — PROVIDER VS DEPLOYER
================================================================================

1.1 Under the EU AI Act and equivalent regulatory frameworks, compliance
obligations for an AI system in production rest primarily with the DEPLOYER —
the organisation that puts the AI system into use, controls its purpose, and
makes decisions based on its output.

1.2 Monop Content, trading as AILeash ("Provider"), supplies governance,
audit, and evidentiary tooling that enables the Customer ("Deployer") to
demonstrate and maintain its own compliance posture. Provider does not
assume, in whole or in part, the Deployer's regulatory obligations as an
AI system operator.

1.3 The Software provides:
    (a) Pre-execution governance checks against rules declared in ai.txt;
    (b) A cryptographically sealed, tamper-evident audit record of
        decisions and their stated rationale (the "Report");
    (c) Tools for the Deployer to verify chain integrity independently
        via the /verify-chain endpoint.

1.4 The Software does NOT:
    (a) Guarantee that the Deployer's broader use of AI is compliant
        with any specific regulation in all circumstances;
    (b) Constitute legal advice or a substitute for the Deployer's own
        legal and compliance review;
    (c) Assume responsibility for decisions the Deployer's systems make
        outside the scope of what is passed to the Software for
        governance.

1.5 The Deployer remains solely responsible for:
    (a) Determining whether its overall AI deployment satisfies
        applicable law;
    (b) Correctly integrating the Software into its decision pipeline
        such that governed decisions are actually routed through it;
    (c) Acting on CHALLENGE outcomes that require human intervention.

================================================================================
2. LIMITATION OF LIABILITY
================================================================================

2.1 AGGREGATE CAP. Provider's total aggregate liability arising out of or
related to this Agreement, whether in contract, tort, statute, or
otherwise, shall not exceed the total fees paid by the Deployer to
Provider in the twelve (12) months immediately preceding the event
giving rise to the claim.

2.2 EXCLUSION OF CONSEQUENTIAL LOSS. Provider shall not be liable for any
indirect, incidental, special, consequential, or punitive damages,
including but not limited to: loss of profits, loss of revenue, loss of
business opportunity, loss of data, reputational harm, or regulatory
fines or penalties imposed on the Deployer — regardless of whether
Provider was advised of the possibility of such damages.

2.3 NO INDEMNIFICATION OF REGULATORY FINES. For the avoidance of doubt,
Provider does not indemnify the Deployer against fines, penalties, or
sanctions imposed by any regulator. Such fines arise from the Deployer's
own status as a Deployer under applicable law, not from a failure of
the Software in isolation.

2.4 CARVE-OUTS. The limitations in this Section 2 do not apply to:
    (a) Provider's gross negligence or wilful misconduct;
    (b) Death or personal injury caused by Provider's negligence;
    (c) Fraud or fraudulent misrepresentation;
    to the extent such carve-outs cannot lawfully be excluded.

2.5 BASIS OF THE BARGAIN. The Deployer acknowledges that the fees charged
for the Software reflect the allocation of risk in this Section 2, and
that Provider would not be able to offer the Software at its current
pricing absent this limitation.

================================================================================
3. WARRANTY DISCLAIMER
================================================================================

3.1 The Software is provided "as is." Provider warrants that the
governance engine will operate substantially as documented and that the
audit chain, once sealed, is tamper-evident as described.

3.2 Provider does not warrant that use of the Software guarantees
compliance with any specific law or regulation, as compliance also
depends on factors outside Provider's control, including but not limited
to the Deployer's own integration, configuration, and operational
decisions.

================================================================================
4. INSURANCE
================================================================================

4.1 Provider intends to maintain professional indemnity and/or cyber
liability insurance appropriate to its scale of operations. Confirmation
of current coverage is available to Deployers on request.

================================================================================
NOTES FOR JUSTIN (remove before publishing)
================================================================================

- This needs a solicitor's review before it goes live — particularly
  Section 2's enforceability varies by jurisdiction (UK vs EU consumer
  protection law treats liability caps differently for B2C vs B2B).
- Section 1 is the more important one commercially: it's what lets you
  say "we give you the evidence to be compliant" rather than "we make
  you compliant," which is both more accurate and far less exposed.
- Once you have any paying customers, get a quote for professional
  indemnity insurance — insurers usually want to see live revenue
  before quoting seriously.

```


## `llms.txt`

30 lines, 2074 bytes

```text
# AILeash (sebbi.pro)

> AILeash is AI compliance and governance infrastructure built by Justin Antony Dobson (Monop Content, Blyth, Northumberland, UK). It provides a deterministic, tamper-evident scoring engine that governs AI-driven decisions — payments, logins, content moderation, access control — and seals every decision in a publicly verifiable SHA-256 Merkle chain. Built to support compliance with the EU AI Act, UK Online Safety Act, and ICO Children's Code.

## Products

- [AILeash](https://sebbi.pro): Core decision engine — 9-signal deterministic risk scoring, tamper-evident audit chain, real-time governance decisions (ALLOW/CHALLENGE/BLOCK)
- [Guardian](https://sebbi.pro/guardian-app): Free grooming-pattern message checker for families — no account, no card
- SonicBoom: One-line compliance layer for AWS, Azure, GCP, OpenAI, and Anthropic API calls
- Sentinel: Real-time fraud and anomaly detection

## Documentation

- [Whitepaper](https://sebbi.pro/whitepaper): Full platform architecture, standards approach, and roadmap
- [API Reference](https://sebbi.pro/developers): Complete API documentation for /api/govern and related endpoints
- [Free Scanner](https://sebbi.pro/scan): EU AI Act compliance scanner
- [Engine Specification](https://sebbi.pro/api/spec): Public, machine-readable engine spec — signal count, thresholds, latency
- [Audit Chain Verification](https://sebbi.pro/api/verify-chain): Public, independently verifiable proof of audit chain integrity

## Standards

- [ai-safety.txt](https://sebbi.pro/.well-known/ai-safety.txt): AI-safety posture declaration
- [ai.txt](https://sebbi.pro/.well-known/ai.txt): AI usage and licensing preferences
- [comply.txt](https://sebbi.pro/.well-known/comply.txt): Compliance declaration
- [security.txt](https://sebbi.pro/.well-known/security.txt): Security contact (RFC 9116)

## Notes

AILeash is not affiliated with, endorsed by, or connected to OpenAI, Google, Anthropic, Meta, Microsoft, Amazon, Apple, or Nvidia. It is an independent product operated solely by Justin Antony Dobson.

```


## `notary.html`

186 lines, 12017 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sovereign Profile Notary — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--input:#131e36;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--muted:#94a3b8;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#f8fafc;font-family:system-ui,sans-serif;min-height:100vh;padding:26px 16px}
  .container{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:28px}
  @media(max-width:850px){.container{grid-template-columns:1fr}}
  header{grid-column:1/-1;border-bottom:1px solid rgba(201,168,76,0.2);padding-bottom:16px}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:28px;color:var(--gold);margin:8px 0 6px}
  .tagline{color:var(--muted);font-size:13.5px;line-height:1.6;max-width:640px}
  .panel{background:var(--ink2);border:1px solid rgba(201,168,76,0.25);border-radius:12px;padding:24px;display:flex;flex-direction:column;gap:14px}
  h2{font-size:12px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--gold);border-bottom:1px dashed rgba(201,168,76,0.2);padding-bottom:8px}
  label{display:block;font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin-bottom:5px}
  input,textarea{width:100%;background:var(--input);border:1px solid rgba(201,168,76,0.3);color:#fff;border-radius:8px;padding:12px;font-size:14px;outline:none}
  input:focus,textarea:focus{border-color:var(--gold);box-shadow:0 0 8px rgba(201,168,76,0.2)}
  textarea{min-height:70px;resize:vertical;line-height:1.5}
  .chk{display:flex;gap:10px;align-items:flex-start;font-size:12px;color:var(--muted);line-height:1.6}
  .chk input{width:auto;margin-top:2px}
  button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:15px;font-size:14px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
  button:disabled{opacity:0.5}
  /* preview card */
  .preview{background:linear-gradient(135deg,#101c36 0%,#060b17 100%);border:2px solid var(--gold);border-radius:14px;padding:24px}
  .p-name{font-size:22px;font-weight:800;color:#fff;font-family:Georgia,serif}
  .p-title{font-size:13px;color:var(--gold);font-family:monospace;margin:2px 0 12px}
  .p-bio{font-size:13.5px;line-height:1.6;color:#cbd5e1;margin-bottom:12px;min-height:20px}
  .p-links{font-family:monospace;font-size:11px;color:var(--muted);word-break:break-all;line-height:1.9}
  .p-hash{margin-top:14px;padding:12px;background:rgba(0,0,0,0.4);border-radius:8px;font-family:monospace;font-size:10.5px;color:var(--ok);word-break:break-all;line-height:1.7}
  #sealres{display:none;margin-top:6px;padding:14px;border-radius:8px;background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.4);font-family:monospace;font-size:11.5px;line-height:1.9;word-break:break-all}
  #sealres b{color:var(--ok)}
  #sealres .code{font-size:16px;color:var(--gold);font-weight:700}
  /* checker */
  #checkres{display:none;margin-top:6px;padding:16px;border-radius:10px;font-size:13px;line-height:1.8}
  #checkres.good{display:block;background:rgba(127,227,176,0.08);border:2px solid var(--ok)}
  #checkres.bad{display:block;background:rgba(255,138,128,0.08);border:2px solid var(--err)}
  #checkres .big{font-weight:900;font-size:16px;margin-bottom:6px}
  #checkres.good .big{color:var(--ok)}
  #checkres.bad .big{color:var(--err)}
  #checkres .mono{font-family:monospace;font-size:11px;color:var(--muted);word-break:break-all;line-height:1.9}
  #trap{display:none;margin-top:12px;padding:16px;border-radius:10px;background:rgba(201,168,76,0.1);border:2px solid var(--gold);cursor:pointer}
  #trap .t1{font-weight:900;font-size:14px;color:var(--gold);margin-bottom:6px}
  #trap .t2{font-size:12.5px;color:#cbd5e1;line-height:1.7}
  .note{font-size:11px;color:rgba(255,255,255,0.35);line-height:1.7}
  a{color:var(--gold)}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">sebbi.pro &middot; sovereign profile notary</div>
    <h1>Seal your profile before someone clones it.</h1>
    <div class="tagline">Fingerprint your public identity — name, bio, links — and seal it into a live, tamper-evident audit chain with an official timestamp. Put your verification code in your bio. From that moment, anyone can check in seconds whether a profile claiming to be you matches the one you sealed first.</div>
  </header>

  <!-- LEFT: builder -->
  <div class="panel" id="builder">
    <h2>1 &middot; Build &amp; seal your profile</h2>
    <div><label>Full name</label><input id="nm" oninput="mirror()" placeholder="Justin Antony Dobson"></div>
    <div><label>Title</label><input id="ttl" oninput="mirror()" placeholder="Founder, Monop Content"></div>
    <div><label>Short bio</label><textarea id="bio" oninput="mirror()" placeholder="Building tamper-evident AI compliance from Blyth."></textarea></div>
    <div><label>LinkedIn URL</label><input id="li" oninput="mirror()" placeholder="linkedin.com/in/yourname"></div>
    <div><label>Other link (optional)</label><input id="fb" oninput="mirror()" placeholder="yoursite.com"></div>
    <div class="chk"><input type="checkbox" id="pub" checked><span><b>Publish to the public registry.</b> Anyone checking your code will see these profile fields. Untick to seal privately — the checker will confirm the seal and timestamp only, and your details are never stored.</span></div>
    <button id="go" onclick="sealProfile()">Seal this profile &mdash; free &rarr;</button>
    <div id="sealres"></div>
    <div class="note">Your profile is fingerprinted with SHA-256 in your own browser. Registration proves this exact profile was sealed first at this timestamp — the strongest public claim to your own words that exists on the open web.</div>
  </div>

  <!-- RIGHT: preview + checker -->
  <div style="display:flex;flex-direction:column;gap:28px">
    <div class="panel">
      <h2>2 &middot; Live evidence preview</h2>
      <div class="preview">
        <div class="p-name" id="v-nm">Your Name</div>
        <div class="p-title" id="v-ttl"></div>
        <div class="p-bio" id="v-bio"></div>
        <div class="p-links" id="v-links"></div>
        <div class="p-hash" id="v-hash">FINGERPRINT — start typing to generate</div>
      </div>
    </div>

    <div class="panel" id="checker">
      <h2>3 &middot; Check a profile &middot; public scanner</h2>
      <div><label>Paste a verification code (from a bio) or full fingerprint</label><input id="q" placeholder="e.g. 7be4d1c29a03"></div>
      <button onclick="checkCode()">Check the chain &rarr;</button>
      <div id="checkres"></div>
      <div id="trap" onclick="document.getElementById('builder').scrollIntoView({behavior:'smooth'});document.getElementById('nm').focus()">
        <div class="t1">&#9888;&#65039; This profile is unclaimed.</div>
        <div class="t2">No seal exists for this code — which means the identity it claims is unregistered and open to AI cloning and impersonation. Sealing yours takes 60 seconds and costs nothing. <u>Tap here to claim your profile now.</u></div>
      </div>
    </div>
  </div>
</div>

<script>
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
function fields(){
  return {
    name:document.getElementById("nm").value.trim(),
    title:document.getElementById("ttl").value.trim(),
    bio:document.getElementById("bio").value.trim(),
    linkedin:document.getElementById("li").value.trim(),
    facebook:document.getElementById("fb").value.trim()
  };
}
function canonical(f){
  return "profile:v1|"+f.name+"|"+f.title+"|"+f.bio+"|"+f.linkedin+"|"+f.facebook;
}
var mirrorTimer=null;
function mirror(){
  var f=fields();
  document.getElementById("v-nm").textContent=f.name||"Your Name";
  document.getElementById("v-ttl").textContent=f.title;
  document.getElementById("v-bio").textContent=f.bio;
  document.getElementById("v-links").innerHTML=[f.linkedin,f.facebook].filter(Boolean).join("<br>");
  clearTimeout(mirrorTimer);
  mirrorTimer=setTimeout(async function(){
    if(!f.name){document.getElementById("v-hash").textContent="FINGERPRINT \u2014 start typing to generate";return;}
    var h=await sha256hex(canonical(f));
    document.getElementById("v-hash").textContent="FINGERPRINT "+h;
  },200);
}
async function sealProfile(){
  var f=fields();
  var res=document.getElementById("sealres");
  if(!f.name){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Enter at least your name.</span>";return;}
  var btn=document.getElementById("go");btn.disabled=true;btn.textContent="Sealing\u2026";
  try{
    var fp=await sha256hex(canonical(f));
    var body={fingerprint:fp,public:document.getElementById("pub").checked,profile:f};
    var r=await fetch("/api/identity/seal",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    var d=await r.json();
    if(!d.sealed){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;btn.textContent="Seal this profile \u2014 free \u2192";return;}
    var code=(d.code||fp.slice(0,12));
    var when=new Date((d.sealed_at)*1000).toLocaleString("en-GB");
    res.style.display="block";
    res.innerHTML=(d.already_registered?"<b>Already sealed.</b> This exact profile was registered earlier \u2014 details below.<br>":"<b>\u2713 SEALED.</b> This exact profile is now locked in the chain.<br>")
      +"Your verification code: <span class='code'>"+code+"</span><br>"
      +"Registered: "+when+" \u00b7 block #"+d.block_index+"<br><br>"
      +"<b>Put this line in your LinkedIn bio:</b><br>\u26D3 Profile sealed \u00b7 verify code "+code+" at sebbi.pro/identity";
    btn.textContent="Sealed \u2713";
  }catch(e){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Network error: "+e+"</span>";btn.disabled=false;btn.textContent="Seal this profile \u2014 free \u2192";}
}
async function checkCode(){
  var q=document.getElementById("q").value.trim().toLowerCase().replace(/[^0-9a-f]/g,"");
  var out=document.getElementById("checkres");
  var trap=document.getElementById("trap");
  trap.style.display="none";
  if(q.length<12){out.className="bad";out.innerHTML="<div class='big'>Enter at least the 12-character code.</div>";return;}
  out.className="";out.style.display="block";out.innerHTML="Checking the chain\u2026";
  try{
    var r=await fetch("/api/identity/check?code="+q);
    var d=await r.json();
    if(d.found){
      var when=new Date(d.registered_at*1000).toLocaleString("en-GB");
      var prof="";
      if(d.profile){
        prof="<br><b>"+(d.profile.name||"")+"</b>"+(d.profile.title?(" \u00b7 "+d.profile.title):"")
          +(d.profile.bio?("<br>"+d.profile.bio):"")
          +(d.profile.linkedin?("<br><span class='mono'>"+d.profile.linkedin+"</span>"):"");
      }else{
        prof="<br><span class='mono'>Sealed privately \u2014 the owner chose not to publish profile fields. The seal and timestamp below are the proof.</span>";
      }
      out.className="good";
      out.innerHTML="<div class='big'>\u2713 SEALED &amp; ON THE CHAIN</div>"
        +"Registered "+when+" \u00b7 block #"+d.block_index+prof
        +"<br><span class='mono'>Fingerprint "+d.fingerprint+"</span>";
    }else{
      out.className="bad";
      out.innerHTML="<div class='big'>\u2717 NO SEAL FOUND</div>No registration exists for this code. Either it was typed wrong \u2014 or the profile showing it was never sealed.";
      trap.style.display="block";
    }
  }catch(e){out.className="bad";out.innerHTML="<div class='big'>Network error</div>"+e;}
}
</script>
</body>
</html>

```


## `pay-check.html`

159 lines, 11880 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Payment Notary — verify before you pay — sebbi.pro</title>
<style>
  :root{--ink:#0a0f1e;--ink2:#10182e;--input:#131e36;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--muted:#94a3b8;}
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--ink);color:#f8fafc;font-family:system-ui,sans-serif;min-height:100vh;padding:26px 16px}
  .container{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:28px}
  @media(max-width:850px){.container{grid-template-columns:1fr}}
  header{grid-column:1/-1;border-bottom:1px solid rgba(201,168,76,0.2);padding-bottom:16px}
  .brand{font-family:monospace;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:rgba(255,255,255,0.35)}
  h1{font-family:Georgia,serif;font-size:28px;color:var(--gold);margin:8px 0 6px}
  .tagline{color:var(--muted);font-size:13.5px;line-height:1.6;max-width:660px}
  .panel{background:var(--ink2);border:1px solid rgba(201,168,76,0.25);border-radius:12px;padding:24px;display:flex;flex-direction:column;gap:14px}
  h2{font-size:12px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--gold);border-bottom:1px dashed rgba(201,168,76,0.2);padding-bottom:8px}
  label{display:block;font-size:10px;font-family:monospace;text-transform:uppercase;letter-spacing:2px;color:var(--muted);margin-bottom:5px}
  input{width:100%;background:var(--input);border:1px solid rgba(201,168,76,0.3);color:#fff;border-radius:8px;padding:12px;font-size:15px;outline:none;font-family:inherit}
  input:focus{border-color:var(--gold);box-shadow:0 0 8px rgba(201,168,76,0.2)}
  button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:8px;padding:15px;font-size:14px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:1px}
  button:disabled{opacity:0.5}
  #sealres{display:none;margin-top:6px;padding:14px;border-radius:8px;background:rgba(127,227,176,0.08);border:1px solid rgba(127,227,176,0.4);font-family:monospace;font-size:11.5px;line-height:1.9;word-break:break-all}
  #sealres b{color:var(--ok)}
  #sealres .code{font-size:17px;color:var(--gold);font-weight:700}
  #checkres{display:none;margin-top:6px;padding:18px;border-radius:10px;font-size:13.5px;line-height:1.8}
  #checkres.good{display:block;background:rgba(127,227,176,0.08);border:2px solid var(--ok)}
  #checkres.bad{display:block;background:rgba(255,138,128,0.1);border:3px solid var(--err)}
  #checkres .big{font-weight:900;font-size:17px;margin-bottom:6px}
  #checkres.good .big{color:var(--ok)}
  #checkres.bad .big{color:var(--err)}
  #checkres .mono{font-family:monospace;font-size:11px;color:var(--muted);word-break:break-all;line-height:1.9}
  .note{font-size:11px;color:rgba(255,255,255,0.35);line-height:1.7}
  .warnbox{background:rgba(255,138,128,0.06);border:1px solid rgba(255,138,128,0.3);border-radius:8px;padding:12px;font-size:12px;color:#f1b9b3;line-height:1.7}
  a{color:var(--gold)}
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="brand">sebbi.pro &middot; payment notary</div>
    <h1>Never pay a switched invoice again.</h1>
    <div class="tagline">Invoice fraud costs the UK &pound;450m a year: criminals intercept a real invoice and switch the bank details. Since October 2024, UK banks must reimburse victims up to &pound;85,000 &mdash; <b>unless the payer failed to take reasonable care.</b> The Payment Notary is how both sides prove care: the business seals its true details once, every invoice carries a short code, and every check you run is itself sealed into the chain &mdash; a timestamped <b style="color:var(--gold)">Verification Receipt</b> proving you checked before you paid. If the details don't match the sealed original &mdash; <b style="color:var(--err)">you don't pay, and your receipt proves you caught it.</b></div>
  </header>

  <!-- LEFT: business seals details -->
  <div class="panel">
    <h2>For businesses &middot; seal your payment details</h2>
    <div><label>Business name</label><input id="biz" placeholder="JustRight Decorators Ltd"></div>
    <div><label>Sort code</label><input id="sort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number</label><input id="acct" inputmode="numeric" placeholder="12345678"></div>
    <button id="go" onclick="sealPay()">Seal these details &mdash; free &rarr;</button>
    <div id="sealres"></div>
    <div class="note">Fingerprinted with SHA-256 in your own browser. Your full sort code and account number are <b style="color:var(--gold)">never sent to us and never stored</b> &mdash; only the fingerprint plus a masked display (last digits) so customers can eyeball a match. Print the code on every invoice, email footer and quote.</div>
  </div>

  <!-- RIGHT: customer checks before paying -->
  <div class="panel">
    <h2>Before you pay &middot; check the invoice</h2>
    <div><label>Verification code from the invoice</label><input id="q" placeholder="e.g. 7be4d1c29a03"></div>
    <div><label>Sort code shown on the invoice</label><input id="csort" inputmode="numeric" placeholder="12-34-56"></div>
    <div><label>Account number shown on the invoice</label><input id="cacct" inputmode="numeric" placeholder="12345678"></div>
    <div><label>Business name on the invoice</label><input id="cbiz" placeholder="JustRight Decorators Ltd"></div>
    <button onclick="checkPay()">Check before I pay &rarr;</button>
    <div id="checkres"></div>
    <div class="warnbox">If the check fails, <b>do not send the payment.</b> Phone the business on a number you already know &mdash; not one from the invoice &mdash; and confirm the details by voice. Report suspected fraud to Action Fraud on 0300 123 2040.</div>
  </div>
</div>

<script>
async function sha256hex(s){
  var buf=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return b.toString(16).padStart(2,"0");}).join("");
}
function receiptHtml(rc){
  if(!rc)return "";
  var when=new Date(rc.checked_at*1000).toLocaleString("en-GB");
  return "<div style='margin-top:14px;padding:12px;border:1px dashed rgba(201,168,76,0.5);border-radius:8px;background:rgba(201,168,76,0.06)'>"
    +"<b style='color:var(--gold)'>\u26D3 YOUR VERIFICATION RECEIPT \u2014 keep this</b><br>"
    +"<span class='mono'>Checked: "+when+" \u00b7 result: "+rc.result+"<br>Sealed in block #"+rc.block_index+"<br>Receipt seal: "+rc.seal+"<br>Verify any time: sebbi.pro/api/inclusion?hash="+rc.seal+"</span><br>"
    +"<span style='font-size:11px;color:var(--muted);line-height:1.6'>This receipt is tamper-evident proof that you verified the payee\u2019s details before paying \u2014 the kind of evidence banks consider when assessing reimbursement claims under the 2024 mandatory reimbursement rules. Screenshot it or save the seal.</span></div>";
}
function normSort(s){return (s||"").replace(/[^0-9]/g,"");}
function normAcct(s){return (s||"").replace(/[^0-9]/g,"");}
function canonicalPay(biz,sort,acct){
  return "payment:v1|"+biz.trim().toLowerCase()+"|"+normSort(sort)+"|"+normAcct(acct);
}
async function sealPay(){
  var biz=document.getElementById("biz").value.trim();
  var sort=document.getElementById("sort").value;
  var acct=document.getElementById("acct").value;
  var res=document.getElementById("sealres");
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Business name, 6-digit sort code and account number required.</span>";return;
  }
  var btn=document.getElementById("go");btn.disabled=true;btn.textContent="Sealing\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var ns=normSort(sort),na=normAcct(acct);
    var display={business:biz,sort_masked:"**-**-"+ns.slice(4),account_masked:"****"+na.slice(-4)};
    var r=await fetch("/api/payment/seal",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({fingerprint:fp,display:display})});
    var d=await r.json();
    if(!d.sealed){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>"+(d.error||"Sealing failed")+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";return;}
    var when=new Date(d.sealed_at*1000).toLocaleString("en-GB");
    res.style.display="block";
    res.innerHTML=(d.already_registered?"<b>Already sealed.</b> These exact details were registered earlier.<br>":"<b>\u2713 SEALED.</b> Your true payment details are now locked in the chain.<br>")
      +"Registered: "+when+" \u00b7 block #"+d.block_index+"<br><br>"
      +"<b>Print this on every invoice:</b><br>"
      +"\u26D3 Verify our bank details before paying:<br>sebbi.pro/pay-check \u00b7 code <span class='code'>"+d.code+"</span>";
    btn.textContent="Sealed \u2713";
  }catch(e){res.style.display="block";res.innerHTML="<span style='color:var(--err)'>Network error: "+e+"</span>";btn.disabled=false;btn.textContent="Seal these details \u2014 free \u2192";}
}
async function checkPay(){
  var code=document.getElementById("q").value.trim().toLowerCase().replace(/[^0-9a-f]/g,"");
  var biz=document.getElementById("cbiz").value.trim();
  var sort=document.getElementById("csort").value;
  var acct=document.getElementById("cacct").value;
  var out=document.getElementById("checkres");
  if(code.length<12){out.className="bad";out.innerHTML="<div class='big'>Enter the 12-character code from the invoice.</div>";return;}
  if(!biz||normSort(sort).length!==6||normAcct(acct).length<7){
    out.className="bad";out.innerHTML="<div class='big'>Enter the business name, sort code and account number exactly as shown on the invoice.</div>";return;
  }
  out.className="";out.style.display="block";out.innerHTML="Checking the chain\u2026";
  try{
    var fp=await sha256hex(canonicalPay(biz,sort,acct));
    var r=await fetch("/api/payment/check?code="+code+"&fp="+fp);
    var d=await r.json();
    if(!d.found){
      out.className="bad";
      out.innerHTML="<div class='big'>\u2717 NO SEAL FOUND \u2014 DO NOT PAY</div>No business has sealed payment details under this code. Either the code is mistyped \u2014 or the invoice is fraudulent. Phone the business on a number you already know before sending anything."
        +receiptHtml(d.receipt);
      return;
    }
    if(d.match){
      var when=new Date(d.registered_at*1000).toLocaleString("en-GB");
      var disp=d.display||{};
      out.className="good";
      out.innerHTML="<div class='big'>\u2713 DETAILS MATCH THE SEALED ORIGINAL</div>"
        +"The details on this invoice are identical to the ones <b>"+(disp.business||"this business")+"</b> sealed on "+when+" (block #"+d.block_index+").<br>"
        +"<span class='mono'>Sealed record: "+(disp.business||"")+" \u00b7 "+(disp.sort_masked||"")+" \u00b7 "+(disp.account_masked||"")+"</span><br>"
        +"Safe to proceed \u2014 nothing has been switched."
        +receiptHtml(d.receipt);
    }else{
      var disp2=d.display||{};
      out.className="bad";
      out.innerHTML="<div class='big'>\u26A0\uFE0F DETAILS DO NOT MATCH \u2014 DO NOT PAY</div>"
        +"A seal exists under this code, but the details on your invoice are <b>different from the sealed original</b>. This is exactly what invoice fraud looks like \u2014 the bank details may have been switched.<br>"
        +"<span class='mono'>Sealed original: "+(disp2.business||"")+" \u00b7 "+(disp2.sort_masked||"")+" \u00b7 "+(disp2.account_masked||"")+"</span><br>"
        +"Phone the business on a number you already know. Report to Action Fraud: 0300 123 2040."
        +receiptHtml(d.receipt);
    }
  }catch(e){out.className="bad";out.innerHTML="<div class='big'>Network error</div>"+e;}
}
</script>
</body>
</html>

```


## `registry.html`

360 lines, 18495 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Safe AI Registry — OAAS-1.0 Verified Domains</title>
<meta name="description" content="The global registry of AI-compliant domains. OAAS-1.0 verified. SHA-256 Merkle chain confirmed. EU AI Act ready.">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#04040a;
  --surface:#08080f;
  --surface2:#0d0d18;
  --border:#141428;
  --border2:#1e1e38;
  --gold:#c9a84c;
  --gold2:#e8c96a;
  --green:#00e5a0;
  --red:#ff3d5a;
  --blue:#4d9fff;
  --purple:#8b5cf6;
  --text:#e8e8f8;
  --muted:#4a4a6a;
  --muted2:#6a6a8a;
  --mono:'IBM Plex Mono',monospace;
  --sans:'IBM Plex Sans',sans-serif;
}

html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh}

nav{position:fixed;top:0;left:0;right:0;z-index:100;height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 32px;background:rgba(4,4,10,0.9);backdrop-filter:blur(16px);border-bottom:1px solid var(--border)}
.nav-logo{font-family:var(--mono);font-size:13px;color:var(--gold);text-decoration:none}
.nav-links{display:flex;gap:20px;align-items:center}
.nav-links a{font-family:var(--mono);font-size:11px;color:var(--muted2);text-decoration:none;transition:color .2s}.nav-links a:hover{color:var(--text)}
.nav-cta{color:var(--gold)!important}

.hero{padding:100px 32px 60px;max-width:1000px;margin:0 auto;text-align:center}
.eyebrow{font-family:var(--mono);font-size:10px;color:var(--green);letter-spacing:0.2em;text-transform:uppercase;margin-bottom:20px;display:flex;align-items:center;justify-content:center;gap:10px}
.eyebrow::before,.eyebrow::after{content:'';width:24px;height:1px;background:var(--green);opacity:0.5}

h1{font-size:clamp(32px,5vw,56px);font-weight:700;letter-spacing:-0.03em;line-height:1.05;margin-bottom:16px}
h1 span{color:var(--gold)}
.hero-sub{font-size:16px;color:var(--muted2);line-height:1.7;max-width:580px;margin:0 auto 40px;font-weight:300}

/* STATS */
.stats-row{display:flex;justify-content:center;gap:48px;margin-bottom:48px;flex-wrap:wrap}
.stat-item{text-align:center}
.stat-n{font-family:var(--mono);font-size:36px;color:var(--gold);font-weight:700;line-height:1}
.stat-l{font-size:11px;color:var(--muted2);margin-top:4px;text-transform:uppercase;letter-spacing:0.1em}

/* LIVE TICKER */
.ticker-wrap{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:12px 20px;display:flex;align-items:center;gap:12px;max-width:600px;margin:0 auto 48px;overflow:hidden}
.ticker-dot{width:8px;height:8px;background:var(--green);border-radius:50%;animation:pulse 2s infinite;flex-shrink:0}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:0.5;transform:scale(0.8)}}
.ticker-text{font-family:var(--mono);font-size:11px;color:var(--green);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* MAIN */
.main{max-width:1000px;margin:0 auto;padding:0 32px 80px}

/* SEARCH */
.search-wrap{margin-bottom:32px;position:relative}
.search-input{width:100%;background:var(--surface);border:1px solid var(--border2);color:var(--text);padding:14px 20px 14px 48px;font-size:14px;font-family:var(--sans);border-radius:8px;outline:none;transition:border-color .2s}
.search-input:focus{border-color:var(--gold)}
.search-icon{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:16px}

/* FILTER TABS */
.filter-tabs{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}
.filter-tab{font-family:var(--mono);font-size:11px;padding:6px 14px;border-radius:20px;border:1px solid var(--border);color:var(--muted2);cursor:pointer;transition:all .2s;background:none}
.filter-tab.active{background:rgba(201,168,76,0.1);border-color:var(--gold);color:var(--gold)}
.filter-tab:hover{border-color:var(--muted2);color:var(--text)}

/* REGISTRY TABLE */
.registry-card{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:32px}
.registry-header{padding:14px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.registry-header-title{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:0.1em;text-transform:uppercase}
.registry-count{font-family:var(--mono);font-size:11px;color:var(--muted)}

.reg-table{width:100%;border-collapse:collapse}
.reg-table th{padding:10px 16px;text-align:left;font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:0.1em;border-bottom:1px solid var(--border);background:rgba(0,0,0,0.2)}
.reg-table td{padding:14px 16px;border-bottom:1px solid rgba(255,255,255,0.03);vertical-align:middle}
.reg-table tr:last-child td{border-bottom:none}
.reg-table tr:hover td{background:rgba(255,255,255,0.01)}

.domain-cell{font-family:var(--mono);font-size:13px;color:var(--text);display:flex;align-items:center;gap:8px}
.domain-verified{width:16px;height:16px;background:var(--green);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}
.domain-unverified{width:16px;height:16px;background:var(--gold);border-radius:50%;display:flex;align-items:center;justify-content:center;color:#000;font-size:9px;font-weight:700;flex-shrink:0}

.status-badge{font-family:var(--mono);font-size:9px;padding:3px 8px;border-radius:3px;font-weight:600;letter-spacing:0.05em}
.status-verified{background:rgba(0,229,160,0.12);color:var(--green);border:1px solid rgba(0,229,160,0.2)}
.status-self{background:rgba(201,168,76,0.12);color:var(--gold);border:1px solid rgba(201,168,76,0.2)}
.status-pending{background:rgba(74,74,106,0.2);color:var(--muted2);border:1px solid var(--border)}

.reg-flags{display:flex;gap:4px;flex-wrap:wrap}
.reg-flag{font-family:var(--mono);font-size:9px;color:var(--blue);background:rgba(77,159,255,0.08);border:1px solid rgba(77,159,255,0.15);padding:1px 5px;border-radius:2px}

.hash-cell{font-family:var(--mono);font-size:10px;color:var(--muted);max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* APPLY SECTION */
.apply-section{background:linear-gradient(135deg,rgba(0,229,160,0.06),rgba(0,229,160,0.01));border:1px solid rgba(0,229,160,0.15);border-radius:12px;padding:36px;text-align:center;margin-bottom:32px}
.apply-section h2{font-size:24px;font-weight:700;letter-spacing:-0.02em;margin-bottom:8px}
.apply-section p{font-size:14px;color:var(--muted2);line-height:1.7;max-width:480px;margin:0 auto 24px}

.apply-form{max-width:480px;margin:0 auto}
.apply-input{width:100%;background:rgba(0,0,0,0.3);border:1px solid rgba(0,229,160,0.2);color:var(--text);padding:12px 16px;font-size:14px;font-family:var(--sans);border-radius:6px;outline:none;margin-bottom:10px;transition:border-color .2s}
.apply-input:focus{border-color:var(--green)}
.apply-input::placeholder{color:var(--muted)}
.apply-btn{width:100%;background:linear-gradient(135deg,var(--green),#00b87d);color:#000;border:none;padding:13px;font-size:14px;font-weight:700;font-family:var(--sans);border-radius:6px;cursor:pointer;transition:all .2s}
.apply-btn:hover{transform:translateY(-1px);box-shadow:0 8px 24px rgba(0,229,160,0.2)}
.apply-success{display:none;font-family:var(--mono);font-size:12px;color:var(--green);margin-top:10px}
.apply-success.show{display:block}

/* WHAT VERIFIED MEANS */
.verified-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:32px}
.verified-card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:20px}
.verified-card-icon{font-size:20px;margin-bottom:10px}
.verified-card-title{font-size:13px;font-weight:600;margin-bottom:6px}
.verified-card-desc{font-size:12px;color:var(--muted2);line-height:1.6}

@media(max-width:700px){
  nav{padding:0 16px}
  .hero{padding:80px 16px 40px}
  .main{padding:0 16px 60px}
  .verified-grid{grid-template-columns:1fr}
  .stats-row{gap:24px}
  .reg-table th:nth-child(4),.reg-table td:nth-child(4){display:none}
  .reg-table th:nth-child(5),.reg-table td:nth-child(5){display:none}
}
</style>
</head>
<body>

<nav>
  <a href="/" class="nav-logo">sebbi.pro</a>
  <div class="nav-links">
    <a href="/ai-standard">ai.txt Standard</a>
    <a href="/certificate">Get Certificate</a>
    <a href="/#signup" class="nav-cta">Get API Key →</a>
  </div>
</nav>

<div class="hero">
  <div class="eyebrow">Safe AI Registry</div>
  <h1>The global registry of<br><span>AI-compliant domains.</span></h1>
  <p class="hero-sub">Every domain listed here has published a verified ai.txt declaration. Their SHA-256 Merkle audit chain is intact. Their AI decisions are logged, tamper-evident, and regulator-ready.</p>

  <div class="stats-row">
    <div class="stat-item"><div class="stat-n" id="stat-verified">1</div><div class="stat-l">Verified Domains</div></div>
    <div class="stat-item"><div class="stat-n" id="stat-decisions">—</div><div class="stat-l">Decisions Audited</div></div>
    <div class="stat-item"><div class="stat-n">OAAS-1.0</div><div class="stat-l">Standard Version</div></div>
    <div class="stat-item"><div class="stat-n">SHA-256</div><div class="stat-l">Chain Algorithm</div></div>
  </div>

  <div class="ticker-wrap">
    <div class="ticker-dot"></div>
    <div class="ticker-text" id="ticker-text">Registry live · sebbi.pro verified · Chain integrity: intact · Last checked: just now</div>
  </div>
</div>

<div class="main">

  <!-- WHAT VERIFIED MEANS -->
  <div class="verified-grid">
    <div class="verified-card">
      <div class="verified-card-icon">⛓️</div>
      <div class="verified-card-title">Chain verified</div>
      <div class="verified-card-desc">Every AI decision this domain has ever made is logged in an unbroken SHA-256 Merkle chain. Any regulator can verify it independently.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">🛡️</div>
      <div class="verified-card-title">Sovereign deployment</div>
      <div class="verified-card-desc">AI audit data never leaves the domain's own network. No third-party data processor. GDPR data sovereignty confirmed.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">⚖️</div>
      <div class="verified-card-title">Regulation mapped</div>
      <div class="verified-card-desc">Each domain's ai.txt maps their compliance status to specific regulatory frameworks — EU AI Act, OSA, GDPR, DSA, ICO.</div>
    </div>
    <div class="verified-card">
      <div class="verified-card-icon">✅</div>
      <div class="verified-card-title">Self-declared vs verified</div>
      <div class="verified-card-desc">Self-declared means the domain published an ai.txt without AILeash. Verified means the chain tip is independently checkable. Only verified counts to regulators.</div>
    </div>
  </div>

  <!-- SEARCH -->
  <div class="search-wrap">
    <span class="search-icon">🔍</span>
    <input class="search-input" type="text" id="search-input" placeholder="Search domains..." oninput="filterRegistry()">
  </div>

  <!-- FILTER TABS -->
  <div class="filter-tabs">
    <button class="filter-tab active" onclick="setFilter('all',this)">All Domains</button>
    <button class="filter-tab" onclick="setFilter('verified',this)">Verified Only</button>
    <button class="filter-tab" onclick="setFilter('eu-ai-act',this)">EU AI Act</button>
    <button class="filter-tab" onclick="setFilter('osa',this)">Online Safety Act</button>
    <button class="filter-tab" onclick="setFilter('gdpr',this)">GDPR</button>
  </div>

  <!-- REGISTRY TABLE -->
  <div class="registry-card">
    <div class="registry-header">
      <div class="registry-header-title">// Registered Domains</div>
      <div class="registry-count" id="registry-count">1 domain</div>
    </div>
    <div style="overflow-x:auto">
      <table class="reg-table">
        <thead>
          <tr>
            <th>Domain</th>
            <th>Status</th>
            <th>Regulations</th>
            <th>Chain Tip</th>
            <th>Verified</th>
          </tr>
        </thead>
        <tbody id="registry-tbody">
          <tr>
            <td>
              <div class="domain-cell">
                <div class="domain-verified">✓</div>
                sebbi.pro
              </div>
            </td>
            <td><span class="status-badge status-verified">VERIFIED</span></td>
            <td>
              <div class="reg-flags">
                <span class="reg-flag">EU AI Act</span>
                <span class="reg-flag">UK OSA</span>
                <span class="reg-flag">GDPR</span>
                <span class="reg-flag">DSA</span>
                <span class="reg-flag">ICO</span>
              </div>
            </td>
            <td class="hash-cell" id="chain-tip-cell">Loading...</td>
            <td style="font-family:var(--mono);font-size:11px;color:var(--muted)">2026-06-26</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- APPLY -->
  <div class="apply-section">
    <h2>Get listed in the registry.</h2>
    <p>Publish a verified ai.txt, get your SHA-256 Merkle chain running, and apply to be listed. Being on the registry signals to regulators, clients, and partners that your AI is governed.</p>
    <div class="apply-form">
      <input class="apply-input" type="text" id="apply-domain" placeholder="yourdomain.com">
      <input class="apply-input" type="email" id="apply-email" placeholder="compliance@yourdomain.com">
      <input class="apply-input" type="text" id="apply-key" placeholder="Your AILeash API key (al_live_...)">
      <button class="apply-btn" onclick="applyRegistry()">Apply for Registry Listing →</button>
      <div class="apply-success" id="apply-success">Application received. We will verify your chain and list you within 24 hours.</div>
    </div>
  </div>

</div>

<script>
var allDomains = [
  {
    domain: 'sebbi.pro',
    status: 'verified',
    regs: ['EU AI Act','UK OSA','GDPR','DSA','ICO'],
    hash: '...',
    date: '2026-06-26'
  }
];

var currentFilter = 'all';

// Load live chain tip
fetch('/api/verify-chain').then(function(r){ return r.json(); }).then(function(d) {
  var tip = d.tip || 'Genesis';
  var short = tip.slice(0,20) + '...';
  document.getElementById('chain-tip-cell').textContent = short;
  document.getElementById('stat-decisions').textContent = (d.blocks || 0).toLocaleString();
  allDomains[0].hash = short;

  // Update ticker
  document.getElementById('ticker-text').textContent =
    'Registry live · sebbi.pro verified · Chain blocks: ' + (d.blocks||0) + ' · Chain integrity: ' + (d.valid ? 'intact ✓' : 'checking') + ' · Tip: ' + short;
}).catch(function(){
  document.getElementById('chain-tip-cell').textContent = 'GENESIS...';
  document.getElementById('stat-decisions').textContent = '0';
});

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll('.filter-tab').forEach(function(t){ t.classList.remove('active'); });
  btn.classList.add('active');
  filterRegistry();
}

function filterRegistry() {
  var search = document.getElementById('search-input').value.toLowerCase();
  var filtered = allDomains.filter(function(d) {
    var matchSearch = !search || d.domain.includes(search);
    var matchFilter = currentFilter === 'all' ||
      (currentFilter === 'verified' && d.status === 'verified') ||
      (currentFilter === 'eu-ai-act' && d.regs.some(function(r){ return r.includes('EU'); })) ||
      (currentFilter === 'osa' && d.regs.some(function(r){ return r.includes('OSA'); })) ||
      (currentFilter === 'gdpr' && d.regs.some(function(r){ return r.includes('GDPR'); }));
    return matchSearch && matchFilter;
  });

  document.getElementById('registry-count').textContent = filtered.length + ' domain' + (filtered.length !== 1 ? 's' : '');
  document.getElementById('stat-verified').textContent = allDomains.filter(function(d){ return d.status === 'verified'; }).length;

  var tbody = document.getElementById('registry-tbody');
  tbody.innerHTML = filtered.map(function(d) {
    var statusClass = d.status === 'verified' ? 'status-verified' : d.status === 'self' ? 'status-self' : 'status-pending';
    var statusLabel = d.status === 'verified' ? 'VERIFIED' : d.status === 'self' ? 'SELF-DECLARED' : 'PENDING';
    var iconClass = d.status === 'verified' ? 'domain-verified' : 'domain-unverified';
    var iconText = d.status === 'verified' ? '✓' : '~';
    var flags = d.regs.map(function(r){ return '<span class="reg-flag">'+r+'</span>'; }).join('');
    return '<tr><td><div class="domain-cell"><div class="'+iconClass+'">'+iconText+'</div>'+d.domain+'</div></td>'
      + '<td><span class="status-badge '+statusClass+'">'+statusLabel+'</span></td>'
      + '<td><div class="reg-flags">'+flags+'</div></td>'
      + '<td class="hash-cell">'+d.hash+'</td>'
      + '<td style="font-family:var(--mono);font-size:11px;color:var(--muted)">'+d.date+'</td></tr>';
  }).join('');

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px">No domains match this filter yet.</td></tr>';
  }
}

function applyRegistry() {
  var domain = document.getElementById('apply-domain').value.trim();
  var email = document.getElementById('apply-email').value.trim();
  var key = document.getElementById('apply-key').value.trim();

  if (!domain || !email || !key) { alert('Please fill in all fields.'); return; }

  fetch('/contact', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({
      name: 'Registry Application: ' + domain,
      email: email,
      phone: '',
      org: domain,
      message: 'REGISTRY APPLICATION\n\nDomain: ' + domain + '\nEmail: ' + email + '\nAPI Key: ' + key.slice(0,20) + '...'
    })
  }).then(function() {
    document.getElementById('apply-success').classList.add('show');
    document.getElementById('apply-domain').value = '';
    document.getElementById('apply-email').value = '';
    document.getElementById('apply-key').value = '';
  }).catch(function() {
    document.getElementById('apply-success').classList.add('show');
  });
}
</script>

</body>
</html>

```


## `report-threat.html`

272 lines, 14806 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Guardian &mdash; Report a Threat</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0f1e;color:#fff;min-height:100vh;padding:24px;max-width:600px;margin:0 auto}
.logo{font-size:22px;font-weight:900;text-align:center;margin-bottom:4px}.logo span{color:#c9a84c}
.sub{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;text-align:center;margin-bottom:8px}

.nav-links{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-bottom:28px}
.nav-links a{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);text-decoration:none;padding:5px 10px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;letter-spacing:1px;text-transform:uppercase;transition:all .2s}
.nav-links a:hover{color:#c9a84c;border-color:rgba(201,168,76,0.4)}

.intro{background:rgba(201,168,76,0.06);border:1px solid rgba(201,168,76,0.2);border-radius:8px;padding:18px;margin-bottom:20px;font-size:13px;color:rgba(255,255,255,0.7);line-height:1.75}
.intro strong{color:#c9a84c;display:block;margin-bottom:6px;font-size:14px}

.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:20px;margin-bottom:16px}
.card-title{font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:4px}
.card-desc{font-size:12px;color:rgba(255,255,255,0.4);margin-bottom:14px;line-height:1.6}

.field{margin-bottom:12px}
.field label{display:block;font-family:monospace;font-size:10px;color:rgba(255,255,255,0.4);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px}
.field input,.field textarea,.field select{width:100%;background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.12);color:#fff;padding:12px 14px;font-size:14px;border-radius:6px;outline:none;font-family:inherit;transition:border-color .2s}
.field input:focus,.field textarea:focus,.field select:focus{border-color:rgba(201,168,76,0.5)}
.field textarea{height:100px;resize:vertical}
.field input::placeholder,.field textarea::placeholder{color:rgba(255,255,255,0.25)}
.field select option{background:#0a0f1e}

.evidence-label{font-family:monospace;font-size:9px;color:#ff6b6b;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;margin-top:10px}
.evidence-box{background:rgba(0,0,0,0.3);border:1px solid rgba(255,107,107,0.2);border-radius:6px;padding:12px;font-family:monospace;font-size:11px;color:rgba(255,255,255,0.6);line-height:1.8;word-break:break-all;margin-bottom:4px}

.severity{display:inline-block;padding:4px 12px;border-radius:4px;font-family:monospace;font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin:10px 0}
.sev-critical{background:rgba(204,0,0,0.2);border:1px solid rgba(204,0,0,0.4);color:#ff6b6b}
.sev-high{background:rgba(201,168,76,0.2);border:1px solid rgba(201,168,76,0.4);color:#c9a84c}

.steps{margin-bottom:0}
.step{display:flex;gap:12px;align-items:flex-start;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid rgba(255,255,255,0.06)}
.step:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
.step-n{background:#c9a84c;color:#0a0f1e;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:12px;flex-shrink:0;margin-top:2px}
.step-text{font-size:13px;color:rgba(255,255,255,0.6);line-height:1.65}
.step-text strong{color:#fff;display:block;margin-bottom:3px;font-size:14px}
.step-text a{color:#c9a84c;text-decoration:none}

.btn{width:100%;padding:15px;border:none;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:10px;font-family:inherit;transition:all .2s;text-align:center;text-decoration:none;display:block}
.btn-red{background:#cc0000;color:#fff}.btn-red:hover{background:#aa0000}
.btn-blue{background:#1a4fa0;color:#fff}.btn-blue:hover{background:#153d80}
.btn-purple{background:#6b21a8;color:#fff}.btn-purple:hover{background:#581c87}
.btn-ghost{background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.6);border:1px solid rgba(255,255,255,0.12)}.btn-ghost:hover{color:#fff;border-color:rgba(255,255,255,0.3)}

.msg{display:none;padding:14px;border-radius:6px;font-family:monospace;font-size:12px;margin-bottom:12px;line-height:1.7}
.msg.show{display:block}
.msg-ok{background:rgba(0,135,90,0.15);border:1px solid rgba(0,135,90,0.3);color:#00ff88}
.msg-err{background:rgba(204,0,0,0.15);border:1px solid rgba(204,0,0,0.3);color:#ff6b6b}

.divider{height:1px;background:rgba(255,255,255,0.06);margin:20px 0}
.footer-note{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.2);text-align:center;margin-top:24px;line-height:1.8}
</style>
</head>
<body>

<div class="logo">AILeash <span>Guardian</span></div>
<div class="sub">Threat Reporting &amp; Evidence Preservation</div>

<div class="nav-links">
  <a href="/">Home</a>
  <a href="/certificate">Certificate</a>
  <a href="/registry">Safe AI Registry</a>
  <a href="/admin">Admin</a>
  <a href="/scan">AI Scanner</a>
</div>

<div class="intro">
  <strong>What is this page for?</strong>
  If AILeash Guardian has detected a threat — grooming behaviour, suspicious contact, or any harmful activity involving a child — this page lets you preserve the evidence and report it to the right authorities. Fill in your details below, copy the evidence package, and follow the steps to report. The SHA-256 audit hash is cryptographically sealed and admissible in UK courts.
</div>

<div class="card">
  <div class="card-title">Evidence Package</div>
  <div class="card-desc">This evidence was automatically captured and sealed by AILeash Guardian. Do not edit it.</div>
  <div class="evidence-label">SHA-256 Audit Hash</div>
  <div class="evidence-box" id="ev-hash">Loading...</div>
  <div class="evidence-label">Incident Record</div>
  <div class="evidence-box" id="ev-record">Loading...</div>
  <div id="ev-severity"></div>
</div>

<div class="card">
  <div class="card-title">Your Details</div>
  <div class="card-desc">This information is sent securely to AILeash and to the relevant authority when you submit your report.</div>
  <div class="field"><label>Your Full Name</label><input type="text" id="reporter-name" placeholder="e.g. Jane Smith"></div>
  <div class="field"><label>Your Email Address</label><input type="email" id="reporter-email" placeholder="your@email.com"></div>
  <div class="field"><label>Your Phone Number</label><input type="tel" id="reporter-phone" placeholder="+44 7700 000000"></div>
  <div class="field"><label>Child's Approximate Age</label>
    <select id="child-age">
      <option value="">Select age group</option>
      <option>Under 5</option>
      <option>5 to 7</option>
      <option>8 to 10</option>
      <option>11 to 13</option>
      <option>14 to 16</option>
      <option>17</option>
    </select>
  </div>
  <div class="field"><label>Additional Details</label><textarea id="extra-details" placeholder="Describe anything else relevant to this incident. Include dates, times, platform names, usernames, or any other context that might help investigators."></textarea></div>
</div>

<div class="card">
  <div class="card-title">How to Report</div>
  <div class="card-desc">Follow these steps in order. Start with Step 1 immediately. If a child is in immediate danger, call 999 first.</div>
  <div class="steps">
    <div class="step">
      <div class="step-n">1</div>
      <div class="step-text">
        <strong>Action Fraud &mdash; UK's National Fraud Reporting Centre</strong>
        Call <strong>0300 123 2040</strong> or visit <a href="https://www.actionfraud.police.uk" target="_blank">actionfraud.police.uk</a>. Give them the SHA-256 hash above. They will issue a crime reference number — keep it safe.
      </div>
    </div>
    <div class="step">
      <div class="step-n">2</div>
      <div class="step-text">
        <strong>CEOP &mdash; Child Exploitation and Online Protection</strong>
        For grooming or child sexual exploitation, report directly at <a href="https://www.ceop.police.uk/safety-centre/" target="_blank">ceop.police.uk/safety-centre</a>. Available 24 hours a day, 7 days a week. CEOP works directly with police to investigate and arrest offenders.
      </div>
    </div>
    <div class="step">
      <div class="step-n">3</div>
      <div class="step-text">
        <strong>Internet Watch Foundation &mdash; For Illegal Images</strong>
        If the incident involved child sexual abuse material, report it at <a href="https://report.iwf.org.uk" target="_blank">report.iwf.org.uk</a>. The IWF works with police to remove content and prosecute offenders globally.
      </div>
    </div>
    <div class="step">
      <div class="step-n">4</div>
      <div class="step-text">
        <strong>Local Police</strong>
        For immediate danger call <strong>999</strong>. For non-emergency situations call <strong>101</strong>. Provide the SHA-256 hash and your crime reference number from Action Fraud.
      </div>
    </div>
  </div>
</div>

<div class="msg msg-ok" id="msg-ok"></div>
<div class="msg msg-err" id="msg-err"></div>

<button class="btn btn-ghost" onclick="copyEvidence()">Copy Full Evidence Package to Clipboard</button>
<a href="https://www.actionfraud.police.uk/reporting-fraud-and-cyber-crime" target="_blank" class="btn btn-blue">Report to Action Fraud &rarr;</a>
<a href="https://www.ceop.police.uk/safety-centre/" target="_blank" class="btn btn-purple">Report to CEOP &rarr;</a>
<button class="btn btn-red" onclick="submitReport()">Submit to AILeash &mdash; Preserve Evidence Permanently &rarr;</button>

<div class="footer-note">
  AILeash Guardian &middot; Monop Content &middot; Blyth, Northumberland<br>
  justrightdecorators@gmail.com &middot; 07908 269428<br>
  Evidence sealed with SHA-256 &middot; Admissible in UK courts
</div>

<script>
var incidentData = {};

function init() {
  var params = new URLSearchParams(window.location.search);
  var hash    = params.get('hash')    || localStorage.getItem('last_block_hash')    || 'NOT PROVIDED';
  var score   = params.get('score')   || localStorage.getItem('last_score')         || 'N/A';
  var reasons = params.get('reasons') || localStorage.getItem('last_reasons')       || 'N/A';
  var ts      = params.get('ts')      || new Date().toISOString();
  var device  = localStorage.getItem('guardian_device') || 'Unknown Device';
  var apiKey  = localStorage.getItem('guardian_key')    || '';

  incidentData = { hash:hash, score:score, reasons:reasons, ts:ts, device:device, apiKey:apiKey };

  document.getElementById('ev-hash').textContent = hash;
  document.getElementById('ev-record').textContent = ts + ' | ' + device + ' | score: ' + score + ' | signals: ' + reasons;

  var sev = parseFloat(score) >= 0.9 ? 'CRITICAL' : 'HIGH';
  document.getElementById('ev-severity').innerHTML = '<span class="severity ' + (sev==='CRITICAL'?'sev-critical':'sev-high') + '">' + sev + ' SEVERITY</span>';
}

function buildPackage() {
  var name  = document.getElementById('reporter-name').value.trim();
  var email = document.getElementById('reporter-email').value.trim();
  var phone = document.getElementById('reporter-phone').value.trim();
  var age   = document.getElementById('child-age').value;
  var extra = document.getElementById('extra-details').value.trim();
  return [
    'AILEASH GUARDIAN — LAW ENFORCEMENT EVIDENCE PACKAGE',
    '=====================================================',
    'Generated: ' + new Date().toISOString(),
    '',
    'EVIDENCE HASH (SHA-256):',
    incidentData.hash,
    '',
    'INCIDENT RECORD:',
    incidentData.ts + ' | Device: ' + incidentData.device,
    'Risk Score: ' + incidentData.score,
    'Threat Signals: ' + incidentData.reasons,
    '',
    'REPORTER DETAILS:',
    'Name:  ' + (name  || 'Not provided'),
    'Email: ' + (email || 'Not provided'),
    'Phone: ' + (phone || 'Not provided'),
    'Child age group: ' + (age || 'Not provided'),
    '',
    'ADDITIONAL DETAILS:',
    extra || 'None provided',
    '',
    'REPORTING CONTACTS:',
    'Action Fraud: 0300 123 2040 | actionfraud.police.uk',
    'CEOP: ceop.police.uk/safety-centre',
    'IWF: report.iwf.org.uk',
    'Emergency: 999 | Non-emergency: 101',
    '',
    'This evidence package was generated by AILeash Guardian.',
    'The SHA-256 audit hash is cryptographically sealed and',
    'admissible as evidence in UK courts.',
    'sebbi.pro | justrightdecorators@gmail.com | 07908 269428'
  ].join('\n');
}

function copyEvidence() {
  navigator.clipboard.writeText(buildPackage()).then(function() {
    var btn = document.querySelectorAll('.btn-ghost')[0];
    btn.textContent = 'Copied \u2713';
    setTimeout(function(){ btn.textContent = 'Copy Full Evidence Package to Clipboard'; }, 2500);
  });
}

async function submitReport() {
  var ok  = document.getElementById('msg-ok');
  var err = document.getElementById('msg-err');
  ok.classList.remove('show'); err.classList.remove('show');
  var email = document.getElementById('reporter-email').value.trim();
  if (!email || !email.includes('@')) {
    err.textContent = 'Please enter your email address before submitting.';
    err.classList.add('show'); return;
  }
  try {
    var r = await fetch('https://sebbi.pro/report-threat', {
      method: 'POST',
      headers: {'Content-Type':'application/json','Authorization':'Bearer '+incidentData.apiKey},
      body: JSON.stringify({
        hash: incidentData.hash, score: incidentData.score,
        reasons: incidentData.reasons, device: incidentData.device,
        ts: incidentData.ts,
        reporter_name:  document.getElementById('reporter-name').value.trim(),
        reporter_email: email,
        reporter_phone: document.getElementById('reporter-phone').value.trim(),
        child_age:      document.getElementById('child-age').value,
        extra_details:  document.getElementById('extra-details').value.trim(),
        evidence_package: buildPackage()
      })
    });
    var d = await r.json();
    if (d.ok) {
      ok.textContent = 'Report submitted. Reference: ' + (d.reference || 'AIDX-' + Date.now()) + '. Evidence is permanently preserved. Justin has been notified.';
      ok.classList.add('show');
    } else {
      err.textContent = 'Submission failed. Copy the evidence package above and report to Action Fraud directly on 0300 123 2040.';
      err.classList.add('show');
    }
  } catch(e) {
    err.textContent = 'Cannot reach server. Copy the evidence package and call Action Fraud: 0300 123 2040.';
    err.classList.add('show');
  }
}

init();
</script>
</body>
</html>

```


## `requirements.txt`

2 lines, 22 bytes

```text
opentimestamps-client

```
