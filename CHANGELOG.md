# AILeash Changelog

## v6.4.2 — Forensic Capture (2026-07-04)

### What Changed
- **Microsecond timing** across all decision phases (auth → signals → decision → seal)
- **Full request context** captured: IP, port, protocol, TLS version/cipher, user-agent, device fingerprint
- **Signal derivation logging:** Raw values → normalized → weighted contributions
- **GeoIP/ASN lookup** for geographic routing analysis
- **Chain continuity proof:** Genesis link + previous 3 blocks detect tampering
- **Velocity windows sealed** into audit chain (was in-memory, now permanently recorded)
- **Guardian** network safeguarding: predatory pattern detection with behavioral timelines
- **CEOP/NCA integration ready:** Evidence packages for law enforcement submission

### Technical
- Added `forensic_evidence` table: request context, timing phases, signal derivation, decision trace, geoip, chain continuity
- Added `guardian_patterns` table: pattern type, severity, confidence, behavioral timeline
- New endpoint: `GET /api/forensic/{audit_id}` — full forensic reconstruction
- New endpoint: `POST /api/guardian/pattern-detect` — pattern detection
- New endpoint: `POST /api/guardian/report-ceop` — evidence package for law enforcement
- Request handler context extraction: IP, user-agent, device fingerprint
- TimingContext class for microsecond-precision phase tracking
- Device fingerprinting via SHA256(IP+user-agent+device_id)

### Security
- Request context captured for all decisions (forensic completeness)
- Chain continuity proof prevents chain rebuilding attacks
- Velocity windows sealed (prevents temporal manipulation)
- All forensic data sealed into chain

### Documentation
- Updated whitepaper.html with v6.4.2 features and regulatory alignment
- Updated api-routes.md with all endpoints, examples, and product descriptions
- New ROUTES.json (machine-readable route manifest)
- Updated CHANGELOG with full version history

---

## v6.4.1 — Enhanced Technical Capture (2026-07-04)

### What Changed
- Raw signal values now sealed into chain (trust, velocities, amount, device_risk, anomaly)
- Full request context capture (IP, user-agent, device fingerprint)
- Request handler passed to `govern()` for network metadata extraction
- Threat logging enhanced with IP + fingerprint
- Receipts include raw signal snapshot + timestamps

### Technical
- Added `raw_signals` table: all 9 signal values per decision
- Request context extracted in `extract_forensic_context()`
- Device fingerprinting via SHA256(IP+user-agent+device_id)
- Guardian refactored: network/business focused, not parental control

### Products
- **AILeash:** AI governance engine (50p/device/month)
- **Guardian:** Free message checker for families (free forever)
- **SonicBoom:** Compliance layer for cloud AI (50p/device/month)
- **Sentinel:** Fraud & anomaly alerts (50p/device/month)

---

## v6.4.0 — Production Baseline (2026-07-01)

### Core Features
- Deterministic weighted scoring (9 signals)
- Per-decision SHA-256 audit chain
- Real-time block alerting with sealed evidence
- Gapless per-key receipt sequences
- Challenge verdict with hosted resolution page
- Regulatory mapping (EU AI Act, UK Online Safety Act, ICO Children's Code)
- Stripe billing integration (50p per device per month, you keep the rest)
- Sovereign deployment support (no data leaves your network)
- Public verification endpoints (chain integrity, health, spec)

### Products
- **AILeash:** Every AI decision, sealed. 50p/device/month.
- **Guardian:** Free message checker for families. Free forever.
- **SonicBoom:** Compliance layer for AWS/Azure/GCP/OpenAI/Anthropic. 50p/device/month.
- **Sentinel:** Fraud and anomaly alerting. 50p/device/month.

### Pricing
- Free tier: 100 decisions/month, no credit card
- Paid: 50p per device per month (you charge what you want, we take 50p, you keep the rest)
- Referral bonus: 10p per referred device per month, for as long as they stay
- No contracts. Month-to-month. Cancel anytime.

### Compliance
- **EU AI Act:** Articles 9 (continuous risk management), 12 (record-keeping), 13 (transparency), 14 (human oversight)
- **UK Online Safety Act:** Real-time moderation evidence, sealed audit trail, Ofcom-ready
- **ICO Children's Code:** Guardian message checker, pattern detection, CEOP/Childline integration ready
- **Digital Services Act:** Systemic risk assessment, algorithmic transparency, minor-protection evidence

### Endpoints
- `POST /api/govern` — Core decision endpoint
- `POST /api/keys` or `/signup` — Create API key
- `GET /api/spec` — Engine specification
- `GET /api/verify-chain` — Chain integrity proof
- `GET /api/health` — Server health
- `GET /api/pulse` — Live dashboard
- `POST /stripe-webhook` — Billing webhook

---

## Summary

**AILeash is one tamper-evident engine under four product layers:**

1. **AILeash** — AI governance (decisions scored, explained, sealed)
2. **Guardian** — Child safety (free message checker for families)
3. **SonicBoom** — Cloud compliance (one line of code on your existing AI)
4. **Sentinel** — Fraud detection (real-time anomaly alerts)

**Price:** 50p per device per month. You set your price. You keep the margin.

**Regulatory alignment:** Built for EU AI Act enforcement (August 2026), UK Online Safety Act, ICO Children's Code, and Digital Services Act.

**Verification:** Every claim is checkable. Chain integrity, health, specification, decision accuracy — all live endpoints, all public.
