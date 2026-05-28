# AILeash EU AI Act Compliance

## Regulation 2024/1689 Mapping

### Article 6: High-Risk Classification

✅ **In Scope:**
- Critical infrastructure systems
- Employment and education
- Essential services
- Financial services

**AILeash provides:** Governance layer for high-risk AI action decisions.

### Article 9: Risk Management System

✅ **Continuous Assessment**
- Multi-signal risk evaluation on every action
- User trust decay modeling (updated per action)
- Velocity-based anomaly detection
- Geographic and device risk factors

✅ **Known and Foreseeable Risks**
- Unsafe country detection
- High-amount transaction flagging
- Behavioral anomaly thresholds
- Device risk scoring

✅ **Appropriate Measures**
- Three-tier decision framework: ALLOW / CHALLENGE / BLOCK
- Human oversight pathway (CHALLENGE decisions)
- Trust-based access control
- Real-time decision logging

### Article 12: Record Keeping & Logging

✅ **Automatic Logging**
- Every decision recorded with timestamp
- Full request and response JSON stored
- Immutable SQLite audit log

✅ **Traceability**
- Unique `audit_hash` per decision (SHA-256)
- Previous hash chained (`prev_hash`)
- Chain integrity verifiable via `/api/verify`

✅ **Audit Trail Retention**
- All records retained indefinitely
- Database backups recommended
- Merkle root for batch verification

**Audit Record Contents:**
```json
{
  "id": 42,
  "ts": 1234567890.123,
  "user_id": "agent_fin_01",
  "event_json": "{...request...}",
  "result_json": "{...decision...}",
  "prev_hash": "abc123...",
  "audit_hash": "def456...",
  "merkle_root": "xyz789..."
}
```

### Article 13: Transparency & Information

✅ **Decision Explainability**
- Every response includes `reasons` array
- Possible reasons: `low_trust`, `velocity_spike`, `high_amount`, `risky_device`, `country_shift`, `unsafe_country`, `behaviour_anomaly`
- All factors mapped to regulatory categories

✅ **System Information**
- Version tracking (`version` in response)
- Deterministic scoring (same inputs → same output)
- Action-type profiles documented
- Risk weights published

✅ **User Information**
- Current trust score returned: `trust`
- Risk factors explained in `reasons`
- User can request audit records for their account

### Article 17: Quality Management

✅ **Reproducibility**
- Scoring algorithm deterministic
- Version pinned (3.0.0)
- Risk profiles fixed per action type
- No randomness or ML drift

✅ **Governance System**
- Trust model transparent
- Action weights documented
- Decision thresholds fixed (0.35, 0.70)

✅ **Human Oversight Integration**
- CHALLENGE decisions flag for manual review
- GDPR Art.22 compliant pathway
- System blocks fully automated high-risk decisions

## GDPR Article 22: Automated Decision-Making

✅ **Compliant Pathway:**

| Decision | Classification | GDPR Compliance |
|----------|----------------|------------------|
| ALLOW | Low-risk | ✅ Automated allowed |
| CHALLENGE | Medium-risk | ✅ Requires human review |
| BLOCK | High-risk | ✅ Blocked + audit trail |

**Right to Human Review:**
- CHALLENGE decisions create mandatory review slot
- User/controller must assign human reviewer
- Decision appealable within review period
- Full reasoning provided for appeal

## ISO 42001: AI Management System

✅ **Sections Addressed:**

- **4.1 Risk Assessment** → Multi-signal scoring
- **4.2 Risk Treatment** → Decision framework (ALLOW/CHALLENGE/BLOCK)
- **4.3 Monitoring** → Continuous audit logging
- **4.4 Documentation** → Audit trail retention
- **4.5 Governance** → API controls + human oversight

## Safe Country List

AlignedWith EU/EEA + Trusted Jurisdictions:

```
UK, US, DE, FR, CA, AU, NL, SE, NO, DK, FI, IE, NZ
```

**Rationale:**
- EU member states (DE, FR, NL, SE, DK, FI, IE)
- EEA (NO, IS)
- UK (post-Brexit adequacy)
- Five Eyes allies with data protection frameworks (US, CA, AU, NZ)

## Audit Trail Example

```json
{
  "decision": "BLOCK",
  "reasons": ["unsafe_country", "behaviour_anomaly"],
  "audit_hash": "a3f9c1d8e2b7f4c0a9d8e1f2b3c4d5e6",
  "merkle_root": "7e2b4f91a8c3d6e9f0a1b2c3d4e5f6g7",
  "score": 0.9141
}
```

**Chain Verification:**
```bash
curl https://your-aileash.com/api/verify

# Response:
{
  "valid": true,
  "blocks": 12847,
  "merkle_root": "7e2b4f91a8c3d6e9f0a1b2c3d4e5f6g7",
  "message": "Chain intact — all hashes verified"
}
```

## Regulatory Filing Checklist

Use this when documenting your high-risk AI system for authorities:

- [ ] Risk assessment completed (Reference: Art. 9, 4.1)
- [ ] AILeash governance layer deployed
- [ ] Audit trail retention policy documented (Retention: Indefinite)
- [ ] Human oversight process defined (CHALLENGE → Manual Review)
- [ ] GDPR Art.22 compliance confirmed
- [ ] Safe country list documented
- [ ] Trust decay policy explained
- [ ] Velocity thresholds justified
- [ ] Chain verification procedure tested
- [ ] Staff training completed
- [ ] System documentation archived

## Enforcement Timeline

- **August 2026** — EU AI Act enforcement begins
- **Penalties** — Up to €30M or 6% of global annual turnover
- **Preparation** — Deploy AILeash now; test compliance by Q2 2026

## Further Questions?

Consult:
- EU Commission AI Regulation docs: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- Your DPO for GDPR specifics
- Legal counsel for jurisdiction-specific requirements
