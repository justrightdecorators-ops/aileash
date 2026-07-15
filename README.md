# AILeash — AI Compliance & Governance Infrastructure

**Tamper-proof audit chains, real-time risk scoring, and child safety monitoring for AI systems — built to meet the EU AI Act, UK Online Safety Act, and ICO Children's Code.**

[![Live Chain Verification](https://img.shields.io/badge/audit_chain-verify_live-c9a84c)](https://sebbi.pro/api/verify-chain)
[![API Spec](https://img.shields.io/badge/API-public_spec-7fe3b0)](https://sebbi.pro/api/spec)
[![Free Tier](https://img.shields.io/badge/free_tier-100_decisions%2Fmonth-0a0f1e)](https://sebbi.pro/signup)

🔗 **Website:** [sebbi.pro](https://sebbi.pro) · **Whitepaper:** [sebbi.pro/whitepaper](https://sebbi.pro/whitepaper) · **API Docs:** [sebbi.pro/developers](https://sebbi.pro/developers) · **Free Scanner:** [sebbi.pro/scan](https://sebbi.pro/scan)

---

## What is AILeash?

AILeash is AI compliance infrastructure that scores, explains, and cryptographically seals every AI-driven decision your platform makes about a person — payments, logins, content moderation, access control, hiring, lending, and more.

Every decision produces a deterministic score, a human-readable reason, and a SHA-256 Merkle-chained receipt that anyone can independently verify. No black-box machine learning, no silent drift, no retraining — the same inputs always produce the same decision, and the entire history is tamper-evident by design.

If your platform uses AI to make a decision that affects a real person, and you need to **prove** — to a regulator, a court, or a customer — exactly what was decided and why, that's what AILeash produces automatically.

## Why this exists

AI regulation moved fast in 2024–2026. Platforms using automated decision-making now face real obligations under:

- **EU AI Act (Regulation 2024/1689)** — transparency, accuracy, and audit-trail requirements for AI systems used in regulated decisions
- **UK Online Safety Act** — child safety and content moderation duties for platforms accessible to minors
- **ICO Children's Code** — age-appropriate design and data protection for services likely to be accessed by children
- **Digital Services Act (EU)** — accountability and explainability for automated systems

Most platforms bolt compliance on after the fact, with logs that can be edited and dashboards that can't be independently verified. AILeash is built the other way round: the audit trail is the product, not an afterthought.

## The four products

| Product | What it does | Price |
|---|---|---|
| **AILeash** | Core decision engine — scores every AI action, explains the reasoning, seals it in the audit chain | 50p/device/month, 100 free decisions |
| **Guardian** | Free grooming-pattern message checker for families — paste a message, get a plain-English safety assessment | Free, always |
| **SonicBoom** | One-line drop-in compliance layer for AWS, Azure, GCP, OpenAI, and Anthropic API calls | 50p/device/month |
| **Sentinel** | Real-time fraud and anomaly detection — velocity spikes, new-country logins, unusual behavioural patterns | 50p/device/month |

## How the engine works

Every call to `POST /api/govern` runs through a deterministic 9-signal weighted scoring model — trust decay, request velocity across three time windows, transaction amount, device risk, behavioural anomaly, and geographic risk — and returns:

```json
{
  "decision": "ALLOW | CHALLENGE | BLOCK",
  "score": 0.0,
  "trust": 1.0,
  "reasons": ["velocity_spike", "high_amount"],
  "audit_hash": "sha256_hex_string",
  "block_index": 12345
}
```

The full formula, thresholds, and audit-chain mechanics are public: see the [API Reference](./AILeash-API-Reference-v6.4.2.md) and the live [`/api/spec`](https://sebbi.pro/api/spec) endpoint.

Anyone — a regulator, an auditor, a curious developer — can independently verify the integrity of the entire decision history at [`/api/verify-chain`](https://sebbi.pro/api/verify-chain), no account required.

## Quickstart

```bash
# 1. Get a free API key — no card, no signup friction
curl -X POST https://sebbi.pro/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "product": "aileash"}'

# 2. Score your first decision
curl -X POST https://sebbi.pro/api/govern \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "u_123",
    "action": "payment",
    "amount": 250,
    "country": "GB",
    "device_id": "d_456"
  }'
```

100 decisions free every month. No card required to start.

## Built on emerging AI-safety standards

AILeash publishes machine-readable declarations at its domain root so AI systems, crawlers, and agents can check its posture before interacting with it:

- [`/.well-known/ai-safety.txt`](https://sebbi.pro/.well-known/ai-safety.txt) — AI-safety posture declaration
- [`/.well-known/ai.txt`](https://sebbi.pro/.well-known/ai.txt) — usage and licensing preferences
- [`/.well-known/comply.txt`](https://sebbi.pro/.well-known/comply.txt) — compliance declaration

## Who built this

AILeash is built and operated by **Justin Antony Dobson**, trading as **Monop Content**, based in Blyth, Northumberland, United Kingdom. The entire platform — engine, audit chain, child-safety suite, and public verification tools — has been designed and shipped by a single founder, developed and deployed entirely from a mobile device, with no outside funding, co-founders, or institutional backing to date.

sebbi.pro is currently raising seed investment to take AILeash from a working, publicly verifiable platform to a fully resourced compliance product. Get in touch: **justrightdecorators@gmail.com**

## FAQ

**Is AILeash affiliated with OpenAI, Google, Anthropic, or Meta?**
No. AILeash is an independent product and is not endorsed by, partnered with, or connected to any of those companies.

**Does AILeash use machine learning to make decisions?**
No. The scoring engine is fully deterministic — fixed weights, written in code, versioned by release. This is intentional: a deterministic engine is auditable in a way a model with retraining drift is not.

**Is Guardian really free?**
Yes. Guardian, the family-facing grooming-pattern message checker, is free permanently — no account, no card, no catch.

**Can I verify AILeash's claims independently?**
Yes — the full audit chain is publicly verifiable at [`/api/verify-chain`](https://sebbi.pro/api/verify-chain) and the engine specification is public at [`/api/spec`](https://sebbi.pro/api/spec).

---

**Homepage:** [sebbi.pro](https://sebbi.pro) · **Whitepaper:** [sebbi.pro/whitepaper](https://sebbi.pro/whitepaper) · **Developers:** [sebbi.pro/developers](https://sebbi.pro/developers) · **Contact:** justrightdecorators@gmail.com
