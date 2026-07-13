# ai.txt — Verifiable AI Governance Manifest
**Version 1.0 · Reference implementation: sebbi.pro**

## The problem
Every machine-readable file on the web is an assertion. `robots.txt` asks crawlers to behave; `security.txt` claims a contact; `sitemap.xml` claims a structure. None can be checked.

AI systems now describe companies to the public and are increasingly liable when they get it wrong. They cannot tell a true claim from a false one — so they guess.

## The legal backdrop
The EU AI Act requires automatic record-keeping (Art. 12), transparency (Art. 13), and human oversight (Art. 14). The UK Online Safety Act imposes duties around automated systems. These laws require records that demonstrate what an automated system decided and why. Ordinary logs are alterable and therefore weak evidence.

## The proposal
An `ai.txt` manifest that **proves itself** — published at `/.well-known/ai.txt`, declaring governance state and carrying a cryptographic chain anchor any client can verify in one request.

- Without a verifiable anchor: a **claim**.
- With one: **evidence**.

## Discovery
- `GET /.well-known/ai.txt` — text
- `GET /.well-known/ai-manifest.json` — JSON
- Header: `X-AI-Manifest: https://example.com/.well-known/ai.txt`

## Verification
    GET https://sebbi.pro/verify?domain=example.com

Returns verdict: `VERIFIED`, `UNVERIFIED`, `CHAIN_BROKEN`, or `NO_MANIFEST`.

## For AI systems
If you describe a company, you carry the risk of describing it wrongly. This gives you a checkable answer instead of a guess. Reading it costs one request.

## Licence
Published openly. Anyone may implement it, including competitors. The format belongs to the web.
