<div align="center">

# Monop Content Platform

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/aileash)

**[Get Free API Key](https://sebbi.pro/#signup) &nbsp;&bull;&nbsp; [Live Demo](https://sebbi.pro) &nbsp;&bull;&nbsp; [EU AI Act Scanner](https://sebbi.pro/scan) &nbsp;&bull;&nbsp; [AI Compliance Assistant](https://sebbi.pro/compliance-assistant) &nbsp;&bull;&nbsp; [Partner Programme](https://sebbi.pro/reseller)**

</div>

---

> *"90% of platforms have nothing in place. Ofcom is already fining people. The EU AI Act enforcement deadline is August 2026. This is the fix. It costs 50p."*

---

## What Most Compliance Officers Get Wrong

Let us be direct about something.

Most organisations think AI compliance means having a policy document. It does not.

Most think it means running an annual risk assessment. It does not.

Most think their standard server logs satisfy Article 12 of the EU AI Act. They do not.

When Ofcom or a regulator comes to your door — and they will — they will ask for one thing: **prove it**. Prove that every AI decision affecting a person was logged, cannot be altered, can be explained, and was subject to human oversight where required.

A Word document does not prove it. A spreadsheet does not prove it. A database log that your own team can edit does not prove it.

A **SHA-256 Merkle chain** proves it. Because every block contains the cryptographic hash of the previous block. Alter any single record and every subsequent block fails verification instantly. It is mathematically impossible to tamper with it without detection.

That is what this platform provides. Not a policy. Not a framework. **Proof.**

---

## Try It Right Now

No signup. No API key. Hit the live engine directly:

```bash
curl -X POST https://sebbi.pro/api/govern \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_001",
    "action": "send_message",
    "amount": 0,
    "country": "UK",
    "device_id": "test_device",
    "anomaly": 0.1,
    "device_risk": 0.1
  }'
```

You will get back a real decision, a real risk score, real reasons, and a real SHA-256 audit hash sealed to the chain. Right now. In under 30ms.

```json
{
  "decision": "ALLOW",
  "score": 0.1823,
  "trust": 0.5018,
  "reasons": [],
  "audit_hash": "a3f8c2d1e9b4...",
  "timestamp": 1750000000.0,
  "version": "5.0.0"
}
```

Now try a high risk event:

```bash
curl -X POST https://sebbi.pro/api/govern \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "threat_001",
    "action": "send_message",
    "amount": 0,
    "country": "NG",
    "device_id": "burner",
    "anomaly": 0.95,
    "device_risk": 0.95
  }'
```

That will return `BLOCK`. Evidence sealed. Law enforcement pathway activated.

Verify the chain is intact:

```bash
curl https://sebbi.pro/api/verify-chain
```

---

## The Law — What It Actually Requires

### EU AI Act 2024/1689 — Enforcement: August 2026

Most people have heard of the EU AI Act. Few have read it. Here is what it actually requires:

**Article 9 — Risk Management**
Not a one-time assessment. A *continuous* risk management system that identifies, analyses and mitigates risks throughout the entire lifecycle of the AI system. It must be documented. It must be updated. It must be operational at all times.

**Article 12 — Record Keeping**
High-risk AI systems must automatically log events *in a way that cannot be altered*. Standard database logs where your team has write access do not satisfy this. You need a tamper-evident chain.

**Article 13 — Transparency**
Every decision must be explainable. "The algorithm decided" is not an explanation. You need to say: these specific signals, at these specific weights, produced this specific score, which triggered this specific decision. Every time. Automatically.

**Article 14 — Human Oversight**
High-risk AI decisions cannot be fully automated without a human override pathway. ALLOW and BLOCK alone are not sufficient. You need a CHALLENGE state that routes to human review.

**The fine:** Up to 3% of global annual turnover or €15 million — whichever is higher. Per violation.

---

### Online Safety Act 2023 — UK — Already In Force

Every platform where users can interact — gaming, social, messaging, forums — has a statutory duty of care. Ofcom is already investigating. The ICO fined TikTok £12.7 million for Children's Code violations.

What most platforms have: a moderation team and a report button.

What the Online Safety Act requires: documented, systematic, auditable risk assessment that you can show to Ofcom on demand.

---

### ICO Children's Code — Already In Force

If children under 18 can access your platform — even if you did not intend them to — you are subject to the Children's Code. You must apply the best interests of the child by default, minimise data collection, prevent profiling, and ensure children are not subject to solely automated high-risk decisions.

---

## Three Products

### AILeash — AI Governance

Nine concurrent weighted signals scored on every interaction. Real-time decisions. SHA-256 Merkle chain. Satisfies EU AI Act Articles 9, 12, 13 and 14 simultaneously.

| Signal | Weight | What It Catches |
|--------|--------|-----------------|
| Behavioural trust decay | 30% | Bad actors. Asymmetric — trust decays 8% on BLOCK, recovers 1% on ALLOW |
| Velocity 60 seconds | 15% | Burst attacks, spam, automated abuse |
| Content and amount risk | 15% | Logarithmic scaling — proportional not linear |
| Velocity 5 minutes | 10% | Sustained attack patterns |
| Velocity 1 hour | 10% | Low-and-slow adversaries |
| Device risk | 10% | Hardware-level signal |
| Behavioural anomaly | 10% | Deviation from baseline |
| Geographic risk | +10% | Unsafe jurisdiction |
| Country shift | +10% | Account takeover signal |

| Decision | Score | Meaning |
|----------|-------|---------|
| ALLOW | < 0.35 | Safe. Proceeds. Audit record created. |
| CHALLENGE | 0.35 to 0.70 | Elevated. Human review required. Art.14 satisfied. |
| BLOCK | > 0.70 | High risk. Halted. Evidence preserved. |

---

### AILeash Guardian — Child Safety

Same engine. Block threshold drops to 0.60. Six child-specific signals added. CSAM triggers mandatory BLOCK regardless of overall score.

Detects: grooming patterns, psychological manipulation, love bombing, CSAM, cross-border predator evasion, bot and fake accounts.

Every BLOCK generates a SHA-256 evidence package formatted for Action Fraud and CEOP submission. Court-admissible in UK courts.

Guardian App for parents — installs on any phone in 60 seconds. Push notification on block. No app store required.

---

### SonicBoom — Speed and Compliance Plugin

One line of code around your existing AI calls. AWS, Azure, GCP, OpenAI — works with everything. Significantly faster than standard cloud AI. SHA-256 audit chain added automatically. EU AI Act compliant from first call.

```python
from sonicboom import turbo
result = turbo("your_api_key").govern(your_existing_ai_call)
# result.decision    ALLOW / CHALLENGE / BLOCK
# result.audit_hash  sha256:a3f8...
# result.compliant   True
```

---

## The Sovereign Engine

Every customer gets `engine.py` — a single Python file that runs on their own hardware. Their data never leaves their network. Licence validates against sebbi.pro hourly. Cancel and the engine locks. The audit chain stays with the customer permanently.

```bash
python engine.py
# AILeash Engine v4.2.0
# Licence validated. Node NODE_001 active.
# All systems operational.
```

---

## The Business Model

Platforms integrate free. Users pay for protection. You set the price. We take 50p.

| You charge | 1,000 devices | You keep | We take |
|-----------|---------------|----------|---------|
| £1.99/mo | 1,000 | £1,490/mo | £500/mo |
| £2.99/mo | 1,000 | £2,490/mo | £500/mo |
| £4.99/mo | 1,000 | £4,490/mo | £500/mo |

Call centres and resellers: [sebbi.pro/reseller](https://sebbi.pro/reseller)

---

## Compliance Coverage

| Regulation | Articles Covered |
|------------|-----------------|
| EU AI Act 2024/1689 | Art.9, 12, 13, 14, GDPR Art.22 |
| Online Safety Act 2023 UK | Full duty of care infrastructure |
| ICO Children's Code UK | Full age-appropriate design |
| Digital Services Act EU | Systemic risk, transparency, minor protection |

---

## Files in This Repo

| File | Purpose |
|------|---------|
| `server.py` | Main application — all three products and all endpoints |
| `engine.py` | Sovereign local governance engine |
| `scan.html` | EU AI Act compliance scanner |
| `guardian-app.html` | Parent Guardian mobile PWA |
| `sonicboom.html` | SonicBoom product page |
| `reseller.html` | Partner and reseller programme |
| `report-threat.html` | Law enforcement reporting |
| `compliance-assistant.html` | AI compliance assistant powered by Claude |
| `sitemap.xml` | Search engine sitemap |
| `Procfile` | Railway deployment |

---

## One Click Deploy

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template/aileash)

---

## Contact

**Justin Antony Dobson**
Founder, Monop Content
Blyth, Northumberland, UK
justin@monopcontent.com
07908 269428
[sebbi.pro](https://sebbi.pro)

---

*Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK. All rights reserved.*
*Protected under the Copyright, Designs and Patents Act 1988 and UK Trade Secrets Regulations 2018.*
