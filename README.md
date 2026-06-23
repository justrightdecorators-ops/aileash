# AILeash — sebbi.pro

> Cryptographic AI compliance infrastructure. SHA-256 Merkle audit chain. 9-signal EWMA scoring engine. Sub-20ms. Zero dependencies. Runs inside your own stack.

[![AILeash Status](https://sebbi.pro/api/badge/status)](https://sebbi.pro)
[![Live Decision](https://sebbi.pro/api/badge/decision)](https://sebbi.pro/sonicboom)
[![SHA-256 Chain](https://sebbi.pro/api/badge/chain)](https://sebbi.pro/api/verify-chain)

---

## What this is

Every day, AI systems make decisions that affect real people. Loan approvals. Insurance quotes. Content moderation. Fraud flags. Job applications. Medical triage.

When those decisions are challenged — by a regulator, a lawyer, a court, or the person affected — most organisations have nothing to show. A log file someone could have edited. A dashboard screenshot. A consultant's report written after the fact.

That is not evidence. That is not compliance. That is exposure.

AILeash is a SHA-256 Merkle chain audit system for AI decisions. Every decision is scored across 9 weighted signals, sealed into a cryptographic chain that nobody can alter, and returned with a plain-language explanation. Sub-20ms. Zero external dependencies. Runs inside your own infrastructure.

---

## Why this matters

The EU AI Act begins enforcement in **August 2026**.

Article 12 requires a tamper-evident audit chain for every AI decision affecting a person. Standard database logs do not satisfy this. You need a cryptographic chain that nobody — including your own team — can alter retrospectively.

Article 9 requires continuous risk management, not annual reviews.
Article 13 requires every decision to be explainable in plain language automatically.
Article 14 requires human oversight pathways.

AILeash satisfies all four. From a single API call. At 50p per device per month.

The Online Safety Act 2023 is already in force. Ofcom is actively investigating platforms. The ICO fined TikTok £12.7 million for Children's Code violations. A moderation team and a report button is not compliance.

**The organisations that build AILeash into their stack now will have years of cryptographic compliance history when regulators come knocking. The ones that wait will have nothing.**

---

## Four products

| Product | What it does | Who needs it |
|---|---|---|
| **AILeash** | AI governance and EU AI Act compliance | Any platform using AI to make decisions |
| **AILeash Guardian** | Child safety and grooming detection | Gaming, social, education, any platform children access |
| **AILeash Sentinel** | Real-time fraud and anomaly monitoring | Call centres, fintech, e-commerce |
| **SonicBoom** | Downloadable local engine — runs inside your infrastructure | Developers, enterprises requiring data sovereignty |

All four products. Same engine. Same 50p per device per month. You set your own user price and keep the margin.

---

## The engine

```
Signal 1  — Trust Score (EWMA decay)          Weight: 30%
Signal 2  — Velocity 60s                       Weight: 15%
Signal 3  — Velocity 5m + 1h                  Weight: 20%
Signal 4  — Transaction Amount (log-scaled)   Weight: 15%
Signal 5  — Device Risk                        Weight: 10%
Signal 6  — Anomaly Score                      Weight: 10%
Signal 7  — Country Shift                      Weight: 10%
Signal 8  — Safe Country                       Weight: 10%
Signal 9  — Trust Floor                        Compounding

Score < 0.35   →  ALLOW
Score 0.35–0.70  →  CHALLENGE
Score > 0.70   →  BLOCK
```

---

## Quick start

```python
import urllib.request, json

def govern(event, api_key):
    req = urllib.request.Request(
        "https://sebbi.pro/api/govern",
        data=json.dumps(event).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

result = govern({
    "user_id":     "user_123",
    "action":      "login",
    "amount":      0,
    "country":     "GB",
    "device_id":   "device_abc",
    "anomaly":     0.05,
    "device_risk": 0.02
}, "YOUR_API_KEY")

print(result["decision"])    # ALLOW
print(result["score"])       # 0.0812
print(result["audit_hash"])  # a3f9b2c1...
```

Zero dependencies. Python standard library only. Copy paste and run.

---

## API

### POST /api/govern

```bash
curl -X POST https://sebbi.pro/api/govern \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_123",
    "action": "purchase",
    "amount": 299.00,
    "country": "GB",
    "device_id": "device_abc",
    "anomaly": 0.1,
    "device_risk": 0.05
  }'
```

```json
{
  "decision":   "ALLOW",
  "score":      0.1842,
  "trust":      0.7341,
  "reasons":    [],
  "audit_hash": "a3f9b2c1d4e5f6a7...",
  "timestamp":  1719999999.123
}
```

### GET /api/verify-chain

```json
{
  "valid":   true,
  "blocks":  14392,
  "tip":     "b7d2e4f1a9c3...",
  "message": "Chain intact"
}
```

### GET /download/engine

Returns `sebdog_engine.py` for authenticated paid keys. The standalone local engine. Zero dependencies. Runs anywhere.

---

## SonicBoom — local deployment

```bash
python sebdog_engine.py --key al_live_your_key --port 9090
```

```
[SEBDOG] Engine running on port 9090
[SEBDOG] All decisions are local. No data leaves your network.
[SEBDOG] Ready.
```

Point your platform at `http://localhost:9090/govern`. Same API. Same audit chain. Sub-20ms. No network hop. Your data never leaves your network.

---

## Compliance coverage

| Regulation | Requirement | AILeash |
|---|---|---|
| EU AI Act Art. 9 | Continuous risk management | EWMA trust decay per user across all sessions |
| EU AI Act Art. 12 | Tamper-evident audit chain | SHA-256 Merkle chain — mathematically unalterable |
| EU AI Act Art. 13 | Explainable decisions | Plain-language reasons array on every decision |
| EU AI Act Art. 14 | Human oversight | CHALLENGE tier — mandatory review pathway |
| Online Safety Act 2023 | Systematic risk assessment | Full audit trail per decision — Ofcom ready |
| ICO Children's Code | Protection by default | Guardian product — grooming detection |
| FCA AI guidance | Explainable auditable decisions | Signal breakdown on every BLOCK and CHALLENGE |

---

## Technical stack

```
Language      Pure Python — zero external dependencies
Server        ThreadingMixIn HTTP server
Database      SQLite WAL mode
Audit chain   SHA-256 Merkle — tamper-evident
Scoring       9-signal EWMA weighted engine
Billing       Stripe — 50p per device per month
Deployment    Railway — sebbi.pro
Engine dist   sebdog_engine.py — local deployment
```

---

## Pricing

```
Free tier     100 decisions — no card required
Paid tier     50p per device per month — Stripe billing
Referral      10p per device per month — no cap — no expiry
```

You set your own user price. You keep everything above 50p. We take 50p. Every month. Forever.

---

## Repository

```
server.py                    Main platform
sebdog_engine.py             Standalone local engine
sonicboom.html               SonicBoom — local engine product page
compliance-assistant.html    AILeash product page and technical white paper
guardian-app.html            AILeash Guardian — child safety
sentinel.html                AILeash Sentinel — fraud detection
reseller.html                Reseller and partner programme
scan.html                    EU AI Act compliance scanner
sitemap.xml                  Sitemap for search engines
robots.txt                   Search engine crawl rules
README.md                    This file
```

---

## Built by

**Justin Antony Dobson** — Monop Content — Blyth, Northumberland, UK

Built entirely on an Android phone. No desktop computer. No team. No external funding. Evenings and weekends alongside a full-time decorating business.

The compliance tooling enterprises pay £50,000 a year for. At 50p per device per month.

📧 justin@monopcontent.com
📞 07908 269428
🌐 [sebbi.pro](https://sebbi.pro)

---

**Get your free API key:** [sebbi.pro](https://sebbi.pro) — no card — 100 free decisions — 60 seconds

---

*Copyright © 2026 Justin Antony Dobson / Monop Content, Blyth, UK*
*Copyright, Designs and Patents Act 1988 | UK Trade Secrets Regulations 2018*
