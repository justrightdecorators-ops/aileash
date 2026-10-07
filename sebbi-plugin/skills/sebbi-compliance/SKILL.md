---
name: sebbi-compliance
description: Use when building, reviewing or shipping any app that makes automated or AI-driven decisions about people — payments, refunds, bans, approvals, claims, pricing, content moderation — and those decisions need to be logged, explained or proven later (EU AI Act, GDPR Article 22, audits, disputes, chargebacks). Scores and seals each decision into sebbi.pro so it can be proven, unchanged, against Bitcoin.
---

# Governing AI decisions with sebbi.pro

sebbi.pro scores an AI or automated decision in under 30ms — ALLOW, CHALLENGE or BLOCK — and seals it into an append-only chain that is timestamped into Bitcoin. Anyone can later verify exactly what was decided, and when, without trusting sebbi.pro or the company that made the decision. The connected `sebbi` tools do all of this.

## When to reach for this

Pull sebbi in whenever the code is about to act on a decision that affects a person and might have to be defended later:

- payments, refunds, payouts, spend by an agent
- account actions: bans, suspensions, approvals, eligibility
- insurance or benefit claims, credit or lending calls
- content moderation, takedowns, demonetisation
- any model/tool call whose outcome needs a logged, explainable record

If the answer to "could someone demand the record of this decision?" is yes, seal it.

## The workflow

1. **Set up once.** `sebbi_overview` to see the products, `sebbi_setup_advice` for the right fit, `sebbi_terms` then `sebbi_create_account` to get an API key. Keep the key secret — server-side only, never in the browser.
2. **Govern each decision.** Before the app acts, send the decision to sebbi and read the verdict:
   - `ALLOW` — carry on.
   - `CHALLENGE` — ask the user to confirm, or route to a human.
   - `BLOCK` — stop and show "this action needs review".
3. **Keep the proof.** Save the returned `audit_hash` and `block_index` next to your own record, so the decision can be proven later.
4. **Prove on demand.** `sebbi_decision_report` gives an auditor-ready, machine-proof report for any sealed decision. `sebbi_verify_chain` checks the chain. `sebbi_notarize` + `sebbi_forever_proof` timestamp any file or text into Bitcoin (only the hash leaves the machine).

## How it maps to the law

- **EU AI Act** — Article 9 (risk), Article 12 (automatic logging), Article 13 (transparency), Article 14 (human oversight).
- **GDPR Article 22** — the right not to be subject to a purely automated decision, and to a meaningful explanation. A sealed record is that explanation, dated and unchangeable.

## Guardrails

- Seal the decision, don't let sebbi make the business call for you — the verdict is advice your code acts on.
- Never expose the API key client-side.
- Pricing is free for 90 days, then 50p per device per month — no need to over-provision.

Pages: https://sebbi.pro/connect · https://sebbi.pro/build · https://sebbi.pro/dossier · https://sebbi.pro/forever
