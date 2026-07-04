# AILeash Changelog

## v6.4.2 — Forensic Capture (2026-07-04)

### Major Features
- **Forensic-Grade Technical Capture**: Microsecond-precision timing across all decision phases
- **Full Request Context**: IP, port, protocol, TLS version/cipher, user-agent, device fingerprint
- **Signal Derivation Audit**: Raw values → normalized → weighted contributions logged
- **GeoIP/ASN Lookup**: Geographic context for routing analysis
- **Chain Continuity Proof**: Genesis link + previous 3 blocks for tampering detection
- **Guardian Network Safeguarding**: Predatory pattern detection with behavioral timelines
- **CEOP/NCA Integration Ready**: Evidence package generation for law enforcement

### Technical Improvements
- Added `forensic_evidence` table: request context, timing, signal derivation, chain continuity
- Added `guardian_patterns` table: pattern type, severity, confidence, behavioral timeline
- Velocity windows now sealed into chain (not in-memory only)
- Request handler context extraction (IP, user-agent, device fingerprint)
- GeoIP lookup placeholder (extensible for MaxMind/IP2Location)
- TimingContext class for microsecond-precision phase tracking

### API Changes
- New: `GET /api/forensic/{audit_id}` — Full forensic reconstruction
- New: `POST /api/guardian/pattern-detect` — Pattern detection
- New: `POST /api/guardian/report-ceop` — Evidence package for CEOP
- `/api/govern` now includes `challenge_url`, `challenge_expires_in`

### Security
- Request context captured for all decisions (forensic completeness)
- Chain continuity proof prevents chain rebuilding attacks
- Velocity windows sealed (prevents temporal manipulation)
- Device fingerprinting via IP+user-agent+device_id hash

### Documentation
- Updated whitepaper.html with v6.4.2 features
- New api-routes.md with all endpoints and examples
- New ROUTES.json (machine-readable route list)

---

## v6.4.1 — Enhanced Technical Capture (2026-07-04)

### Major Features
- Raw signal values sealed into chain (trust, velocities, amount, risks, anomalies)
- Full request context capture (IP, user-agent, device fingerprint)
- Request handler passed to `govern()` for network metadata extraction
- Threat logging enhanced with IP + fingerprint
- Receipts include raw signal snapshot + timestamps

### Technical Improvements
- Added `raw_signals` table: all 9 signal values per decision
- Request context extracted in `extract_forensic_context()`
- Device fingerprinting via SHA256(IP+user-agent+device_id)
- Guardian refactored: network/business focused, not parental

### Guardian Refactoring
- Simplified product: predatory pattern detection only
- Network operator focus: not for parents/children
- Pattern detection functions placeholder
- CEOP reporting placeholder
- Free for safeguarding teams
- Aligned with ICO Children's Code + UK Online Safety Act

---

## v6.4.0 — Production Baseline

### Core Features
- Deterministic weighted scoring (9 signals)
- Per-decision SHA-256 audit chain
- Real-time block alerting with sealed evidence
- Gapless per-key receipt sequences
- Challenge verdict with hosted resolution
- Regulatory mapping (EU AI Act, UK Online Safety Act, ICO Children's Code)
- Stripe billing integration
- Sovereign deployment support
- Public verification endpoints

### Products
- **AILeash**: AI governance engine (50p per device/month)
- **Guardian**: Family tooling (free)
- **SonicBoom**: Speed optimization (50p per device/month)
- **Sentinel**: Fraud detection (50p per device/month)
