# Codebase — part 25 of 31

Contains:
- `investor-prospectus.html`
- `legal.txt`
- `liability.txt`
- `llms.txt`
- `map.html`
- `notary.html`


## `investor-prospectus.html`

198 lines, 14433 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sebbi.pro — the evidence layer for AI. Partner opportunity.</title>
<meta name="description" content="A live, publicly verifiable evidence layer for AI decisions. Built, running, and structurally impossible for incumbents to copy. Seeking one operating partner to take it into regulated enterprise.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,400;6..72,500;6..72,600;6..72,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#FAFAF6;--ink:#14171C;--ink-soft:#454B54;--chain:#2E5E4E;
  --chain-light:#E4ECE8;--gold:#9A7B1F;--gold-light:#F3ECD8;--line:#DEDBD1;
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'IBM Plex Sans',sans-serif;background:var(--paper);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
h1,h2,h3,.display{font-family:'Newsreader',serif;font-weight:500;letter-spacing:-0.01em}
.mono{font-family:'IBM Plex Mono',monospace}
a{color:var(--chain)}
.wrap{max-width:760px;margin:0 auto;padding:0 28px}

header{padding:56px 0 40px;border-bottom:1px solid var(--line)}
.doc-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--ink-soft);margin-bottom:20px;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
h1{font-size:clamp(34px,5vw,50px);line-height:1.08;max-width:17ch;margin-bottom:18px}
.tagline{font-size:18px;color:var(--ink-soft);max-width:54ch}
.tagline b{color:var(--ink)}

.block{position:relative;padding:8px 0 44px 24px;border-left:1px solid var(--line);margin-left:4px}
.block:last-of-type{border-left:1px solid transparent}
.block-num{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--chain);letter-spacing:0.08em;text-transform:uppercase;margin-bottom:10px}
.block h2{font-size:27px;margin-bottom:16px;line-height:1.15}
.block h3{font-size:17px;margin:22px 0 8px}
.block p{font-size:15.5px;color:var(--ink-soft);margin-bottom:14px;max-width:60ch}
.block p:last-child{margin-bottom:0}
.block ul{margin:0 0 14px 18px}
.block li{font-size:15px;color:var(--ink-soft);margin-bottom:8px;max-width:58ch}
.block li b,.block p b{color:var(--ink)}

.proof-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}
@media(max-width:560px){.proof-grid{grid-template-columns:1fr}}
.proof{background:white;border:1px solid var(--line);padding:18px 20px;border-radius:4px}
.proof-n{font-family:'Newsreader',serif;font-size:26px;font-weight:600;color:var(--chain)}
.proof-l{font-size:12.5px;color:var(--ink-soft);margin-top:3px}
.proof-src{font-family:'IBM Plex Mono',monospace;font-size:10px;color:#999;margin-top:6px}

.countdown{background:var(--gold-light);border:1px solid rgba(154,123,31,0.25);border-radius:4px;padding:20px 24px;margin:20px 0}
.countdown-label{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--gold);text-transform:uppercase;letter-spacing:0.08em;margin-bottom:8px}
.countdown-days{font-family:'Newsreader',serif;font-size:38px;font-weight:600;color:var(--gold);line-height:1}
.countdown-sub{font-size:13px;color:var(--ink-soft);margin-top:6px;line-height:1.6}

.pull{border-left:3px solid var(--chain);padding:6px 0 6px 20px;margin:20px 0;font-family:'Newsreader',serif;font-size:22px;line-height:1.35;color:var(--ink)}

.ask-box{background:var(--ink);color:var(--paper);border-radius:4px;padding:32px;margin-top:20px}
.ask-amount{font-family:'Newsreader',serif;font-size:44px;font-weight:600;color:white;line-height:1.05}
.ask-label{font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:#8FA89C;margin-bottom:6px}
.ask-box p{font-size:14.5px;color:#C7D2CC;margin-top:14px;max-width:56ch}
.ask-box p b{color:#fff}

.use-of-funds{margin-top:22px;display:flex;flex-direction:column;gap:10px}
.uf-row{display:flex;justify-content:space-between;align-items:baseline;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.12);font-size:14px;gap:16px}
.uf-row:last-child{border-bottom:none}
.uf-row span:first-child{color:#C7D2CC}
.uf-pct{font-family:'IBM Plex Mono',monospace;color:#8FA89C;flex:0 0 auto}

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
    <span>Partner Opportunity &middot; sebbi.pro</span>
    <span id="doc-date">&mdash;</span>
  </div>
  <h1>The evidence layer for AI is built, live, and looking for one partner.</h1>
  <p class="tagline">sebbi.pro is a publicly verifiable evidence layer for AI decisions &mdash; running in production today, checkable by anyone with the company switched off. <b>The hard part is done. What's left is distribution.</b></p>
</header>

<div class="block">
  <div class="block-num">01 &mdash; The opportunity</div>
  <h2>Every AI decision is about to need evidence. Almost nothing produces it.</h2>
  <p>Three regulatory regimes are converging on the same demand: records that survive scrutiny. The EU AI Act, the UK Online Safety Act, and the 2024 Payment Services reimbursement rules all require an organisation to prove what its systems did &mdash; not assert it, prove it.</p>
  <p>Almost every organisation meets that demand with database logs their own team can edit. That is not evidence, and the day a regulator, court or customer stops taking their word for it, they discover the gap. <b>The market that closes that gap does not really exist yet.</b> sebbi.pro is already in it.</p>

  <div class="pull">A log you can edit tells people what you currently claim happened. It cannot tell them nobody changed it since. Only one of those is worth anything when it matters.</div>

  <div class="countdown">
    <div class="countdown-label">Until high-risk AI obligations apply</div>
    <div class="countdown-days mono" id="countdown-days">&mdash; days</div>
    <div class="countdown-sub">Counting to 2 December 2027. The evidence these obligations require is historical &mdash; it cannot be created after the fact. Every organisation not recording now is accruing a gap it can never fill. That is the buying pressure, and it only grows.</div>
  </div>
</div>

<div class="block">
  <div class="block-num">02 &mdash; What is already built</div>
  <h2>Live in production. Not a deck, not a demo.</h2>
  <p>This runs today, on real infrastructure, and every claim below can be verified by a third party with no account and no permission. Six products on one engine, one tamper-evident chain underneath all of them.</p>

  <div class="proof-grid">
    <div class="proof"><div class="proof-n mono">6</div><div class="proof-l">Products, one engine</div><div class="proof-src">AILeash, Guardian, Sentinel, SonicBoom, Sebdog, Token Saver</div></div>
    <div class="proof"><div class="proof-n mono">~28ms</div><div class="proof-l">Median decision time</div><div class="proof-src">Deterministic, on live traffic</div></div>
    <div class="proof"><div class="proof-n mono">SHA-256</div><div class="proof-l">Hash-chained, externally anchored</div><div class="proof-src">Cross-witnessed by independent systems</div></div>
    <div class="proof"><div class="proof-n mono">Public</div><div class="proof-l">Verifiable with the vendor switched off</div><div class="proof-src">Standalone verifier, no account</div></div>
  </div>

  <p style="margin-top:18px">The whole range shares one spine: every decision sealed as it happens, anchored to a clock nobody controls, and witnessed hourly by an independent platform &mdash; unattended, running now. A regulator, an auditor or a customer checks any of it themselves. That is the product, and it exists.</p>
</div>

<div class="block">
  <div class="block-num">03 &mdash; Why incumbents can't follow</div>
  <h2>The moat is structural, not a head start.</h2>
  <p>Every logging, monitoring and audit platform on the market keeps a record its own customer controls. That is not a flaw they can patch &mdash; it is the foundation their business stands on. To match sebbi.pro they would have to give the customer a record the customer cannot edit, which breaks the thing they sell.</p>
  <ul>
    <li><b>They can't copy the question.</b> "Can the people being audited edit the audit?" indicts their entire category. They answer no by admitting their evidence was never evidence.</li>
    <li><b>They can't copy the time.</b> An unbroken, externally witnessed record is the one input nobody can shortcut. The only way to have last year covered was to be recording last year.</li>
    <li><b>They can't copy the honesty.</b> Every competitor overclaims. sebbi.pro publishes its own limits on every page and seals them into its own chain &mdash; which is exactly the property a buyer of evidence infrastructure is paying for.</li>
  </ul>

  <div class="verify-box">
    <h4>Verify it before you read another line</h4>
    <p>Nothing here asks to be believed. <code>/x/witness/tip</code> returns the live chain tip. <code>/x/ots/status</code> shows its external anchoring, per proof. <code>/x/roster/list</code> shows the independent platforms witnessing it.</p>
    <p style="margin-bottom:0">All public, all need no account, all answer to anyone. The offline verifier reaches a verdict with the wifi off.</p>
  </div>
</div>

<div class="block">
  <div class="block-num">04 &mdash; The economics</div>
  <h2>Zero marginal cost. Distribution scales without headcount.</h2>
  <p>The same engine serves one customer or ten thousand &mdash; marginal cost per additional device is effectively zero. That makes distribution, not engineering, the entire growth lever, and it makes a reseller channel pure margin rather than a cost line.</p>
  <p><b>50p per active device per month</b>, metered on real usage. Partners embedding the platform set their own customer price and keep everything above the platform fee. The witness network stays free and open by design &mdash; it is the mechanism that makes the evidence credible, and charging for it would weaken the thing being sold.</p>
  <p>The route to market is the platforms, not one customer at a time. Other compliance platforms already hold relationships with the exact buyers who need this and are uniformly weak on evidence. The engine sits underneath their product as the evidence layer they can't build themselves. Five founding seats; four already taken.</p>
</div>

<div class="block">
  <div class="block-num">05 &mdash; The ask</div>
  <h2>One operating partner. 30% of the business.</h2>
  <div class="ask-box">
    <div class="ask-label">Offered</div>
    <div class="ask-amount">30% for the right<br>operating partner</div>
    <p>Built and run at near-zero fixed cost, live and proven. Everything the hard money usually funds is already done. The partner who can open regulated enterprise and government &mdash; <b>defence, healthcare, telecommunications</b> &mdash; takes a substantial stake in a platform that is ready to scale the day they walk in.</p>
    <div class="use-of-funds">
      <div class="uf-row"><span>Regulated enterprise &amp; government channel access</span><span class="uf-pct">core</span></div>
      <div class="uf-row"><span>Reseller / MSP distribution at scale</span><span class="uf-pct">core</span></div>
      <div class="uf-row"><span>External security audit &amp; legal review of claims</span><span class="uf-pct">fund</span></div>
      <div class="uf-row"><span>Infrastructure hardening for enterprise load</span><span class="uf-pct">fund</span></div>
    </div>
  </div>
  <p style="margin-top:16px">These are sectors where evidence obligations are hardest, procurement runs eighteen months, and a founder alone does not get in the room. The economics suit exactly that: high-value, long-cycle, and served by an engine that costs nothing more to run at a thousand customers than at one.</p>
</div>

</div>

<div class="contact-block wrap">
  <div class="contact-card">
    <h3>Talk to the founder directly</h3>
    <p>The full technical demonstration takes fifteen minutes, and every claim on this page can be verified live during it.</p>
    <div class="contact-links">
      <a href="mailto:justin@monopcontent.com">justin@monopcontent.com</a>
      <a href="https://sebbi.pro">sebbi.pro</a>
      <a href="https://sebbi.pro/map">sebbi.pro/map &mdash; the system, mapped</a>
      <a href="https://sebbi.pro/whitepaper">sebbi.pro/whitepaper</a>
    </div>
  </div>
</div>

<footer class="wrap">
  <p>Justin Antony Dobson &middot; Monop Content &middot; Blyth, Northumberland, UK<br>
  This document is a summary for information and does not constitute an offer of securities. All figures should be independently verified before any investment decision. Regulatory dates are stated as amended by the AI Omnibus and are subject to change.</p>
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


## `map.html`

1091 lines, 65159 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>The sebbi.pro system map — explore the evidence layer</title>
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
    <div class="mark">sebbi.pro × evidence layer</div>
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
/* ---------- FOUNDATION ---------- */
{
 id:"problem", c:"foundation", label:"The problem", size:1.25,
 lede:"A log you can edit is not evidence. It only says what you currently claim happened.",
 body:[
  "Nearly every system keeps logs, and logs live in databases. A database can be edited by anyone with the right access — an attacker, an insider, or the operator itself. So an ordinary log can only ever say <b>this is what we currently claim happened</b>. It cannot say <b>and nobody has changed it since</b>.",
  "Most of the time nobody notices the difference. It appears the day someone with authority — a regulator, a court, an insurer, a customer in dispute — stops accepting your word and asks for proof. At that moment \"our system recorded it\" and \"here is proof it was not altered\" are two different sentences, and only the second carries weight.",
  "It has become urgent for a specific reason. Software used to do what it was told, so a log of the inputs implied the outputs. AI systems produce outputs that cannot be derived from the inputs by inspection, so the output has to be recorded as a fact in its own right. The volume of decisions needing evidence has risen by orders of magnitude. The mechanism most organisations use to evidence them has not changed since the 1990s."
 ],
 to:["chain","determinism"]
},
{
 id:"determinism", c:"foundation", label:"Deterministic gate", size:1.15,
 lede:"The governance layer is arithmetic, not a model. That is the only arrangement where it can do its job.",
 body:[
  "Put a model in charge of judging whether another model behaved acceptably and every property you needed disappears at once. The verdict cannot be reproduced, because the same input may score differently tomorrow. It cannot truly be explained, because the explanation is itself generated. It drifts silently on retraining. And anything that reads natural language can be attacked with natural language.",
  "Worst of all it regresses. If a model needs governing and the governor is a model, the governor needs governing. There is no bottom to that stack. It terminates only at something that cannot behave unexpectedly — which means arithmetic: fixed weights, fixed thresholds, a published formula.",
  "What that buys at audit is mechanical. Take the sealed inputs, take the sealed ruleset version, recompute. If the result matches the sealed verdict, the decision was the rules applied to the facts — and anyone can confirm it without the vendor in the room."
 ],
 limit:"A deterministic gate is not smarter than a model and is not meant to be. It has no semantic understanding and will miss things a good classifier would catch. The trade is deliberate: reproducibility bought at the cost of cleverness.",
 to:["sonicboom","reproducibility"]
},
{
 id:"chain", c:"foundation", label:"The hash chain", size:1.5, core:true,
 lede:"One append-only chain. Every seal contains the one before it, so history cannot be edited quietly.",
 body:[
  "At the centre of the platform is a single data structure: an append-only chain of sealed records. Every component writes into a chain built the same way.",
  "Each record is sealed as it is created. The seal is a SHA-256 hash over the record's content <b>together with the seal of the record before it</b>. Because each seal contains its predecessor, every block's integrity depends on the whole history beneath it.",
  "<b>seal(n) = SHA-256( seal(n−1) · timestamp · event · result · basis )</b>",
  "Alter one character of one historic record and every seal after it fails. Verification recomputes from genesis and reports either integrity, or the exact block index where tampering begins."
 ],
 live:"tip",
 routes:[["/x/witness/tip","current tip"]],
 to:["anchor","receipts","basis","completeness","erasure","forks"]
},
{
 id:"anchor", c:"foundation", label:"Bitcoin anchoring", size:1.3,
 lede:"A chain proves nothing was altered. It does not prove when the chain was built. So the clock was moved outside.",
 body:[
  "This is the hole every tamper-evident audit product has, and most do not mention it. An operator with full control could discard the chain and construct a fresh one dated however they liked, and every seal in the fabricated chain would verify perfectly. Internal integrity is necessary. Alone it is not sufficient, because the operator still controls the clock.",
  "So at a defined interval the current tip is submitted to <b>OpenTimestamps</b>, which aggregates it with thousands of unrelated timestamps into a Merkle tree and commits the root to Bitcoin. Nobody involved controls that ledger.",
  "The distinction that matters, and the one most vendors blur: <b>submitted is not confirmed</b>. A calendar promises to commit the tip; the transaction lands later. Until the proof has been upgraded and confirmed, it is pending — not anchored. Per-proof state is published rather than asserted."
 ],
 live:"ots",
 routes:[["/x/ots/status","anchor state, per proof"]],
 limit:"Anchoring closes backdating only up to the last anchor. Between anchors the gap is small, real, and shared by every vendor in this market. Witnessing is what closes it.",
 to:["witness"]
},
{
 id:"receipts", c:"foundation", label:"Gapless receipts", size:1.1,
 lede:"A chain proves records were not edited. Receipts prove records were not omitted.",
 body:[
  "A tamper-evident chain says nothing about a record that was never written. An operator could simply fail to seal an inconvenient event. Receipts close that.",
  "Every sealed decision is issued a sequence number in the same transaction as the chain write, and sequences are gapless by construction: 46, 47, 48. You keep your receipts. If you ever hold 46 and 48 with no 47, a record has been omitted — and you can show it by arithmetic rather than argument.",
  "Edited records break the chain. Missing records break the sequence. Fabricated history breaks the anchor. Between those three, every way of quietly rewriting the past is detectable from outside, by anyone, without trusting the operator. That triple is the whole security model, and it is deliberately small enough to hold in your head."
 ],
 limit:"Receipts protect whoever holds the receipt. They say nothing to a third party auditing a set as a whole — that is what completeness proofs are for.",
 to:["completeness"]
},
{
 id:"basis", c:"foundation", label:"Basis sealing", size:1.05,
 lede:"Two records hide inside \"what a system did\": the action, and what the action was allowed to rely on.",
 body:[
  "A seal on the action alone proves the action happened exactly as recorded. It cannot show what the action rested on — and a decision made on the wrong source, sealed, is just a tamper-proof error.",
  "So the engine seals both in the same block: which sources were used, the content hash of each version of them, which ruleset and ruleset version applied, and which signal pack was in force. The basis is canonicalised, hashed, and folded into the block seal.",
  "Edit the recorded basis afterwards and the block seal no longer matches. What a decision relied on becomes as unalterable as the decision itself."
 ],
 limit:"Basis sealing proves what was relied on, not that it was right. The chain shows a decision rested on invoice X version Y under ruleset Z, unalterably. Whether X was genuine is a matter for process, not cryptography.",
 to:["packs","lineage"]
},

/* ---------- WITNESS / NETWORK ---------- */
{
 id:"witness", c:"foundation", label:"Witness network", size:1.45, core:true,
 lede:"One chain can be rebuilt. Ten cannot — not without everyone who watched you rewriting theirs in step.",
 body:[
  "Each platform periodically publishes its current chain tip. Each peer seals that tip into its own chain. From that moment one platform's history sits inside chains it does not control, which are themselves independently anchored.",
  "To rewrite your own past you would now need every peer who witnessed you to rewrite theirs, in step, on the same values, and re-anchor all of it. That is no longer a technical operation on a database. It is a coordinated conspiracy between commercial competitors, and the difficulty scales with the number of participants rather than the size of anyone's budget.",
  "Two asymmetries make it work. A peer lying about us cannot help us: sealing a tip we never issued produces an entry pointing at a chain state that does not exist, which fails the moment anyone checks. A peer can only conspire with us, never frame us. And our peers are anchored too, so the conspiracy is not two parties agreeing a story — it is two parties defeating timestamps already published in a ledger neither controls.",
  "Silence is made visible rather than prevented. Peers who stop publishing are marked stale and then silent, and a replayed tip is flagged automatically."
 ],
 live:"roster",
 routes:[["/x/roster/list","the public roster"],["/x/witness/spec","the protocol"],["/x/witness/observe","submit a tip"]],
 limit:"Strength comes from breadth. Two platforms witnessing only each other prove very little, and no design can compel a peer to keep publishing. Stale and silent describe elapsed time since we last observed a chain — nothing more. A peer publishing on a human schedule reads stale correctly.",
 to:["roster","signed","forks","open-endpoint"]
},
{
 id:"open-endpoint", c:"open", label:"Open submission", size:1.05,
 lede:"Anyone can submit a tip. No account, no key, no permission — permanently and on purpose.",
 body:[
  "A witnessing network that only accepts submissions from account holders is a customer list, not a witness network.",
  "The obvious objection to all of this is that a vendor is holding evidence about its own conduct. The open endpoint is the answer: anyone can join, and anyone can audit the roster without asking us for anything.",
  "Being listed implies no relationship beyond having sent a hash. It is not a partner list and not an endorsement of anything sealed in anyone's chain, including ours. The roster says so in its own body text, so a reader cannot be misled by the count alone."
 ],
 routes:[["/x/witness/observe","POST a tip"],["/x/roster/list","who has submitted"]],
 to:["roster"]
},
{
 id:"roster", c:"open", label:"The roster", size:1.15,
 lede:"Who has submitted, when they were last seen, and how each name is bound. Published, not described.",
 body:[
  "The roster is the network's own audit surface. For each chain it publishes the tip URL, how many observations have been recorded, when it was first and last seen, and how the name is bound to whoever submits under it.",
  "It also publishes its own vocabulary, so no reader has to guess what a status means. <b>Live</b> means the URL served a valid but different tip. <b>Self-consistent</b> means the URL served exactly the tip the submitter sent — both halves came from the submitter, so it records self-consistency and not verification by anyone. <b>Self-declared</b> means no URL, or we could not reach it: taken on the submitter's word and checked by nobody.",
  "That vocabulary exists because an earlier version conflated reachable with verified. The correction is published rather than quietly patched."
 ],
 live:"roster",
 routes:[["/x/roster/list","the full roster"]],
 to:["signed","conformance"]
},
{
 id:"signed", c:"foundation", label:"Signing keys", size:1.2,
 lede:"You generate the keypair. You keep the private half. We hold the public half and can never produce a signature.",
 body:[
  "A shared-secret lane binds a submission to a secret. If the operator issued that secret, the operator could in principle have produced the submission. That is a real limit and it was put to us independently by three separate reviewers before it was fixed.",
  "The Ed25519 lane removes it. You generate the keypair and keep the private half — it never travels and there is no route that accepts one. The public half can go over any channel at all, because a public key is not a secret. We hold only the public half, which means we can verify a signature and can never produce one.",
  "That is arithmetic rather than a promise about our conduct, and it is stronger than any channel we could have offered. Rotation is yours too: a rotation must be signed by the key being replaced, so we cannot swap your key even if we wanted to."
 ],
 live:"keys",
 routes:[["/x/signed/spec","the specification"],["/x/signed/keys","enrolled keys"],["/x/signed/enroll","enrol your own key"]],
 limit:"Enrolment is open, so the first party to enrol a name gets it. Detection rather than prevention: an enrolment placed over a name already seen in the open lane is flagged permanently. And if you lose the private half you enrol a new name — the honest cost of the stronger property.",
 to:["schema","peer-lane"]
},
{
 id:"peer-lane", c:"foundation", label:"Peer submission lane", size:1.05,
 lede:"The lane an external platform uses to seal into this chain, with a receipt it can validate against a published schema.",
 body:[
  "A peer submits a hash-only envelope. Nothing but digests crosses the boundary — no payloads, ever. What comes back is a receipt: the sealed audit hash, the block, a per-peer gapless sequence number, and the verification properties that receipt carries.",
  "The sequence number is real and per-peer, so a peer holding receipts 5 and 7 can show a sixth exists that it never received. It survives key rotation deliberately, because a counter that reset on rotation could be used to erase a gap.",
  "This lane was rebuilt in August 2026 after an external reviewer refused eight consecutive receipts. See <b>Refused receipts</b> for what that found."
 ],
 routes:[["/x/peer/spec","the specification"],["/x/peer/schema","machine-readable schema"]],
 to:["schema","refusals"]
},
{
 id:"schema", c:"open", label:"Published schema", size:1.0,
 lede:"The response shape as a machine-readable JSON Schema, so a validator loads it rather than transcribing prose.",
 body:[
  "Every disagreement in the integration described under <b>Refused receipts</b> came from the same place: a reviewer read a written description, built rules from it, and the description and the actual bytes had drifted. The behaviour was correct every time. The transcription was not.",
  "The fix was to stop writing better prose. The response shape is now published as a JSON Schema (draft 2020-12) with closed objects throughout. An integrator points a validator at it directly. There is no transcription step left to get wrong.",
  "Any interface described only in sentences will drift from what it actually returns. The schema route is the interface; the prose is commentary on it."
 ],
 live:"schema",
 routes:[["/x/peer/schema","the schema"]],
 to:["conformance"]
},

/* ---------- PROOF LAYER ---------- */
{
 id:"completeness", c:"proof", label:"Completeness", size:1.15,
 lede:"Every audit log proves what happened. None of them prove what didn't.",
 body:[
  "A hash chain proves inclusion. It cannot prove exclusion. So when a firm hands an examiner four hundred decisions, nothing in the mathematics shows it was not six hundred. Every audit ever conducted has run on the assumption that the sample handed over is the whole sample. That assumption has never been provable. It has simply been accepted.",
  "At the close of each period, every record sealed in it is taken, <b>sorted</b>, built into a Merkle tree, and the root and exact count are sealed into the chain — then anchored and witnessed like everything else. Crucially this happens before anybody has asked for anything.",
  "Sorting is the whole trick. It makes the tree canonical: the same set of records always produces the same root, so a set with one record quietly dropped produces a visibly different one. The count is committed alongside it, before the number could be convenient."
 ],
 to:["absence","erasure"]
},
{
 id:"absence", c:"proof", label:"Absence proofs", size:0.95,
 lede:"Showing that a specific record is not in a committed period, without revealing the ones that are.",
 body:[
  "The counterpart to inclusion. Because the tree is built over a sorted set, a party can be shown the two neighbouring leaves a missing record would have sat between — proving nothing sits there, without disclosing the rest of the period.",
  "Useful whenever the interesting question is negative: no decision was taken on this account in this window, no instruction of this kind was ever accepted, nothing was recorded against this person."
 ],
 to:[]
},
{
 id:"erasure", c:"proof", label:"Erasure & tombstones", size:1.0,
 lede:"Append-only and the right to erasure look incompatible. Most vendors disclaim it rather than solve it.",
 body:[
  "If nothing can be removed, how is a person's data deleted? And if it can be removed, what was the chain for?",
  "Half the answer is that personal data lives in the operator's own systems and is deleted there, while the chain holds only a fingerprint that resolves to nothing. The other half is proving to the person who asked that it actually happened.",
  "The payload is deleted by the operator's system. The <b>position</b> in the tree remains, and the erasure is sealed as its own dated event. Holding none of the content, three things can then be established: a record existed, it was erased, and when — against a timestamp nobody involved controls.",
  "So a data subject receives proof of erasure rather than an assurance of it, and the organisation gets evidence it complied that survives the deletion of the very data that would otherwise have been the evidence."
 ],
 limit:"A tombstone proves the erasure was recorded and cannot have been backdated. It does not prove every copy in every backup and downstream system was destroyed — no cryptographic structure can reach into systems it does not sit in.",
 to:[]
},
{
 id:"forks", c:"proof", label:"Fork detection", size:1.0,
 lede:"Several parties hold hashes of our chain. Until this, none of them could check they held hashes of the same chain.",
 body:[
  "Nothing in the design so far stopped an operator running two histories in parallel — serve chain A to a witness, chain B to an auditor. Both receive a valid tip. Both anchor it. Both verify perfectly against the copy they were given. Neither could tell, because there was no way to ask the question that would expose it.",
  "Fork detection is that question, made askable. Consistency between any two committed states of the chain can be checked by anyone holding them, which turns the network of witnesses from a set of separate observers into a single cross-checkable record."
 ],
 to:[]
},
{
 id:"reproducibility", c:"proof", label:"Reproducibility", size:1.0,
 lede:"A stranger can test that the engine is deterministic without being shown the rules.",
 body:[
  "Determinism is only worth anything if someone outside can test it. Send your own inputs, twice, and confirm the same inputs produce the identical verdict — with no access to the ruleset and no account.",
  "That is the difference between a record that <b>describes</b> a decision and one that <b>reproduces</b> it. Only the second is evidence in any strong sense."
 ],
 to:[]
},
{
 id:"lineage", c:"proof", label:"Cross-org lineage", size:0.95,
 lede:"What fed a decision, hop by hop, across company boundaries.",
 body:[
  "A decision inside one organisation frequently rests on outputs produced inside another. Basis sealing records what was relied on locally; lineage carries that provenance across the boundary, so a chain of dependency can be followed between parties who share no infrastructure.",
  "The practical effect: when something goes wrong three companies downstream, the question of what fed what has an answer rather than a reconstruction."
 ],
 to:[]
},
{
 id:"verifier", c:"open", label:"Offline verifier", size:1.0,
 lede:"A standalone verifier you run on your own machine, network disconnected.",
 body:[
  "Every claim about the chain is checkable from outside, but checking it through our endpoints still routes through us. The offline verifier removes even that: download it, disconnect, and recompute.",
  "A verifier that needs the vendor's server to reach a verdict is not independent. This one does not."
 ],
 routes:[["/verify","verification tools"]],
 to:["chain"]
},
{
 id:"authority-cont", c:"proof", label:"Authority continuity", size:0.95,
 lede:"Every hop back to a human, re-derived at export rather than asserted at the time.",
 body:[
  "An agent acted. Something authorised the agent. Something authorised that. Eventually the chain of delegation ends at a person, or it does not end at all — and the second case is the one that matters when someone asks who is answerable.",
  "Continuity re-derives the whole path at the moment a proof is exported, from sealed grants, rather than relying on a claim recorded at the time."
 ],
 to:["authority"]
},

/* ---------- ENGINE ---------- */
{
 id:"sonicboom", c:"engine", label:"SonicBoom", size:1.3, core:true,
 lede:"The decision engine. Allow, challenge or block — in a fraction of a second, deterministically.",
 body:[
  "Seven fields per event: who is acting, what they are doing, the value involved, where from, on what device, plus two optional risk signals your own systems may already produce. An optional eighth carries delegated authority.",
  "The engine combines independent signals — how fast events are arriving for this user and device across three windows, whether the country has changed or is off the expected list, the amount, device risk, anomaly — into a score, against fixed published weights and thresholds. Roughly 28ms.",
  "What comes back is the verdict, the score, and the arithmetic that produced it. The decision and its basis are sealed into the chain in the same breath, so the record exists before anyone knows whether it will be needed."
 ],
 to:["packs","sentinel","oversight","authority","chain"]
},
{
 id:"packs", c:"engine", label:"Signal Packs", size:1.05,
 lede:"Domain rules, versioned and sealed per decision — so which rules ran is never in question.",
 body:[
  "The core engine scores against nine domain-neutral signals: trust, velocity at three windows, amount, device risk, anomaly, country shift and unsafe country. They describe the shape of behaviour rather than the specifics of an industry.",
  "It is worth being precise about what those nine are and are not, because it is a fair criticism and it has been put to us. They are transaction-risk signals. That is the lineage of the engine and the right toolkit for fraud and abuse. It is <b>not</b> a risk taxonomy for the AI Act's risk-management obligations, and describing it as one would be an overclaim.",
  "Packs extend the engine into a domain. Each is versioned and its version is sealed into every decision it governed, so the question of which rules were in force at a given moment has a recorded answer rather than a recollection."
 ],
 limit:"Signal Packs prove which rules ran, not that they were the right rules.",
 to:[]
},
{
 id:"sentinel", c:"engine", label:"Sentinel", size:1.0,
 lede:"Speed and shape of activity rather than the content of any single event.",
 body:[
  "The patterns are the classic signatures: a flood of login attempts against one account, a burst of transactions in seconds, an account appearing in a new country moments after its last action.",
  "Sentinel's velocity analysis feeds the engine's score, and when a pattern crosses the line the flag — what fired, when, on what evidence — is sealed into the same chain. A fraud team gets not just an alert but an alert with a tamper-evident, externally anchored record behind it."
 ],
 to:[]
},
{
 id:"guardian", c:"engine", label:"Guardian", size:1.05,
 lede:"The same machinery aimed at platforms where children are present.",
 body:[
  "Guardian watches for the recognised behavioural warning signs that precede grooming — pressure toward secrecy, attempts to isolate, moves toward private channels — and flags them.",
  "Two design decisions matter. Message content is never stored, only a fingerprint of it: privacy is preserved, and what is kept is proof that the flagged exchange existed in exactly the form it had. And every flag is sealed, so the trail handed to a parent, a safety team or the authorities is tamper-evident from the moment of detection.",
  "In the one context where this evidence may end up in front of a court, a safeguarding report backed by an anchored chain is a fundamentally stronger document than one backed by an editable log."
 ],
 to:["chain","sentinel","regulation"]
},
{
 id:"brain", c:"engine", label:"Brain", size:1.05,
 lede:"A gate every instruction passes through before the AI acts.",
 body:[
  "An AI does what it is told, so the question becomes who checks what it is being told. A poisoned instruction — ignore your rules, export the customer data, delete the logs — walks straight in unless something stands in front of it.",
  "Brain checks against five categories of known-dangerous pattern: child safety, data exfiltration, compliance bypass, prompt injection, system destruction. Normalisation defences mean unicode look-alikes, zero-width characters and spacing tricks resolve to the same fingerprint as the plain form.",
  "Dangerous instructions are blocked with the reason stated, and every decision — allowed or blocked — is sealed with its basis."
 ],
 routes:[["/brain","try it, free"]],
 to:["chain"]
},
{
 id:"oversight", c:"engine", label:"Human oversight", size:1.2,
 lede:"Nobody can prove a human deliberated. Rubber-stamping, though, leaves marks.",
 body:[
  "Article 14 requires that natural persons can effectively oversee a high-risk system. Every vendor claims to satisfy it and the honest position is that none of them can, including this one. Whether a reviewer genuinely deliberated is an internal state and no logging reaches it. Any product claiming to prove human thought is selling something that does not exist.",
  "Rubber-stamping is not an internal state. It is a behavioural pattern, and patterns leave marks provided the right things are recorded in the right order at the time.",
  "<b>Commit before reveal.</b> The case is presented to the reviewer without the machine's verdict. Their own decision and reasoning are sealed first; the verdict is revealed only afterwards. Two blocks, in that order, in a chain that cannot be reordered. A reviewer cannot have merely agreed with an answer they had not yet been shown.",
  "So \"a human reviewed it\" and \"a human clicked accept on a recommendation\" stop being indistinguishable six months later — and only one of them is oversight."
 ],
 limit:"This proves ordering, not deliberation — and only if the integrator does not display the verdict to reviewers before calling the endpoint. That is outside the engine, so it is measured rather than guaranteed. See Conformance.",
 to:["authority","conformance"]
},
{
 id:"authority", c:"engine", label:"Delegated authority", size:1.05,
 lede:"Human oversight only means something if the human was authorised to do it.",
 body:[
  "A single call binds a user to a role, a spending limit and an expiry, signed server-side. The grant is sealed into the chain as its own block, so who gave this person this power, and when, is a permanent record rather than an HR email.",
  "Events then carry the token and the engine verifies it deterministically: wrong user, expired grant, tampered token, or an amount above the granted limit all fail in the same predictable way.",
  "Two related questions are answered by the same machinery — who this person is in the legal sense, with KYC results sealed without the underlying data, and which jurisdiction's rules governed the moment, tagged per decision."
 ],
 to:["regulation"]
},

/* ---------- OPEN ---------- */
{
 id:"notaries", c:"open", label:"The Notaries", size:1.2,
 lede:"The same chain, free, no account, no code. Your content never leaves your device.",
 body:[
  "The notaries exist for two reasons. The obvious one: most people and small businesses have no system to integrate, but still have things worth proving. The strategic one: a claim about evidence infrastructure is only credible if anyone can test it in thirty seconds without asking permission.",
  "All of them share one privacy design. Your browser computes a SHA-256 fingerprint locally and only that 64-character fingerprint is sent and sealed. The chain proves a document with exactly that fingerprint existed at that moment. You reveal the original only if you ever need to — and if you never need to, nobody ever sees it.",
  "<b>Post</b> fixes the exact words of something before you publish it. <b>Identity</b> dates a profile. <b>Payment</b> seals bank details before money moves, which is the fraud that costs most and proves hardest. There are also notaries for data subject requests, reconciliation and declarations."
 ],
 routes:[["/notary","use them, free"]],
 to:["chain"]
},
{
 id:"aitxt", c:"open", label:"ai.txt & comply.txt", size:1.0,
 lede:"Two small public files that let any organisation declare, machine-readably, how its AI is governed.",
 body:[
  "Modelled on robots.txt and security.txt. <b>ai.txt</b> declares what AI the organisation operates, what decision model governs it, what audit method backs it, which regulations it is designed toward, and where a human override sits. <b>comply.txt</b> is the rulebook those instructions and decisions are subject to.",
  "On their own these are claims, not proof — anyone can write \"tamper-evident audit\" in a text file. Their force comes from the third step: sealing the declarations themselves into the chain, so \"this is our governance, as declared on this date\" becomes provable and its history becomes tamper-evident.",
  "Declaration, then rulebook, then enforcement. The standard is open because a standard only matters if anyone can adopt it."
 ],
 to:["chain","regulation","brain"]
},
{
 id:"refusals", c:"open", label:"Refused receipts", size:1.15,
 lede:"An external reviewer refused eight consecutive receipts. Every refusal was right, and every fault was ours.",
 body:[
  "In August 2026 an independent platform built a closed schema against our published response shape and refused to accept any receipt its own verifier would not validate. Not logged a warning — refused. Nine submissions. Eight rejected.",
  "<b>The first receipt said the submission was sealed. It was not.</b> No block existed at that timestamp. The sealing call had failed and a bare exception handler swallowed it, so the response reported success while carrying nothing behind it. That route had never been exercised by an outside party, so the fault had been there since it was written. Their verifier caught it; ours did not, because we had none pointed at ourselves.",
  "<b>Then a sequence field that was always empty.</b> It looked like a completeness guarantee — receipts N and N+2 proving a third exists you never received. It was not one. Anyone relying on it could not have proved anything.",
  "<b>Then three rounds of shape disagreement</b>, all the same underlying cause: written description and actual bytes had drifted. The behaviour was right every time; the transcription was not. So the response shape was published as a machine-readable schema and the transcription step disappeared. The next submission verified end to end with zero refusals.",
  "Separately, three reviewers arrived independently at the same objection to the shared-secret lane, which produced the Ed25519 path. Another found that reachable and verified were being conflated in the roster vocabulary, which produced the published status definitions. Another established that submitted to a timestamp calendar is not the same as anchored, which produced the per-proof status route.",
  "None of this was found by us. It is recorded here because a system that holds evidence about its own conduct cannot be trusted to mark its own work, and the only meaningful answer is to be marked by somebody else — in public, including when the result is embarrassing."
 ],
 to:["schema","conformance"]
},

/* ---------- BUSINESS ---------- */
{
 id:"regulation", c:"business", label:"Regulation", size:1.1,
 lede:"What this evidences, article by article — and what it does not.",
 body:[
  "The platform maintains a versioned regulation map, itself hash-sealed and served at a public endpoint, linking each capability to the obligations it helps evidence: the EU AI Act's record-keeping, transparency and human-oversight expectations, the UK Online Safety Act's duty-of-care documentation, and the ICO Children's Code. The map is versioned, so when regulations change, the history of what was mapped when is itself tamper-evident.",
  "On timing: the 2026 AI Omnibus moved the high-risk obligations back. The transparency obligations did not move, and one deadline was shortened. The delay is widely misreported.",
  "The structural point that matters commercially: obligations arriving later will be assessed against <b>historical</b> records, and evidence cannot be back-filled. Organisations recording now have a defensible history then. Those that wait do not, and cannot acquire one."
 ],
 to:["pricing"]
},
{
 id:"sovereign", c:"business", label:"Sovereign deployment", size:1.15,
 lede:"The engine runs inside your own network. One file, no dependencies, no phone home.",
 body:[
  "For organisations whose data cannot leave the building, the engine runs entirely on your hardware — decisions, chain and database, all local. Pure Python, a single file, no dependencies. It builds the chain locally, keeps daily backups, verifies itself end to end, and serves the routes the witness network needs.",
  "Licensing is offline by design: signed 365-day tokens validated with pure cryptography, no call home, suitable for air-gapped environments.",
  "It is the only component that runs somewhere we cannot reach, and that is the point of it. The sovereignty claim is about the engine, not just about where the data sits."
 ],
 to:["pricing","witness"]
},
{
 id:"pricing", c:"business", label:"Deployment & pricing", size:1.0,
 lede:"50p per active device per month. The proof layer is free and structurally has to be.",
 body:[
  "Two ways to run: integrate against the hosted API, or run it sovereign inside your own network. Pricing is deliberately simple — 50p per active device per month, metered on real usage. Partners embedding the platform set their own customer pricing and keep the margin above the platform fee.",
  "The notaries, Brain, the offline verifier and the witness network are free. Not as a promotion — the network in particular cannot be otherwise. Charging for witnessing would mean only customers witness us, which is exactly the arrangement the network exists to avoid."
 ],
 to:[]
},
{
 id:"conformance", c:"business", label:"Conformance", size:1.05,
 lede:"Three claims here have a soft edge. Rather than hide them, they are measured.",
 body:[
  "Commit-before-reveal proves ordering, but only if the integrator does not show reviewers the verdict first. Witnessing draws strength from breadth, and two platforms witnessing only each other prove very little. A declaration is only as strong as the rules declared — one that constrains nothing passes everything.",
  "None of these can be closed by the engine alone, and a vendor claiming otherwise would be overstating what software can do. What they can be is <b>measured</b> — and a measured weakness is a different object from an unmeasured one. It can be reported, tracked, compared between deployments, and put in front of an auditor.",
  "So probes test the integration rather than trusting it, breadth is reported with concentration made visible, and rules that never fire are surfaced. Fewer than three live peers is reported as weak, because it is."
 ],
 to:["limits"]
},
{
 id:"limits", c:"business", label:"Honest limits", size:1.2,
 lede:"A whitepaper that only lists strengths is marketing. These are the limits, stated as plainly as the capabilities.",
 body:[
  "<b>Sealing proves integrity and timing, not truth at capture.</b> A sealed, anchored record proves exact content existed no later than an externally witnessed moment and has not changed since. It does not prove the contents were true when written — and no recording system of any kind does, which is a fact about recording rather than a defect of this one.",
  "<b>Determinism costs cleverness.</b> The gate has no semantic understanding and will miss things a good classifier would catch. Deliberate and permanent.",
  "<b>Basis sealing proves what was relied on, not that it was right.</b>",
  "<b>Anchoring proves timing only to the last confirmed proof</b> — and submitted is not confirmed.",
  "<b>Witnessing proves a tip existed at a time.</b> It says nothing about whether the records underneath are true, or complete. Garbage sealed on time is still garbage.",
  "<b>None of this prevents anything.</b> The layer produces evidence that something happened and has not been altered. A sealed record of a harmful action is still a harmful action. What changes is that afterwards there is an answer to what happened and who authorised it — which today, in most systems, there is not."
 ],
 to:[]
},
{
 id:"partner", c:"business", label:"The raise", size:1.1,
 lede:"30% of the business for an operating partner who can take this into defence, healthcare and telecoms.",
 body:[
  "Built and operated by a solo founder at near-zero fixed cost. The platform is live; the constraint is not engineering.",
  "What is being offered is a substantial equity stake for a partner who can open regulated enterprise and government channels — sectors where evidence obligations are hardest, procurement cycles are long, and a founder alone does not get in the room. Mass rollout through resellers, who set their own pricing and keep the margin above the platform fee.",
  "The economics suit that shape. Marginal cost per additional device is effectively zero; the same engine serves one customer or ten thousand. Distribution scales without headcount.",
  "The moat is time. An unbroken witnessed record is the one input nobody can shortcut, because the only way to have had this year covered was to be recording in it.",
  "Stated plainly: pre-revenue, founder-led pipeline, and a market whose deadlines move. Commercial terms with the peers on the roster have not been discussed — they joined an open network, not a company."
 ],
 routes:[["/whitepaper","the full whitepaper"]],
 to:["pricing","sovereign","limits"]
}
];

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
      const min=(a.r+b.r)*3.1;
      const f = (d<min ? 2600/d2 : 900/d2);
      const ux=dx/d, uy=dy/d;
      a.vx-=ux*f; a.vy-=uy*f; b.vx+=ux*f; b.vy+=uy*f;
    }
  }
  E.forEach(e=>{
    const dx=e.b.x-e.a.x, dy=e.b.y-e.a.y;
    const d=Math.hypot(dx,dy)||1;
    const rest=185;
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
