# AILeash v6.4.2 API Routes

## Decision Engine

### POST /api/govern
Core governance decision endpoint.

**Auth:** Bearer token (API key)

**Request body:**
```json
{
  "user_id": "string (required)",
  "action": "string (required)",
  "amount": "number (optional, default 0)",
  "country": "string (required, ISO 3166-1 alpha-2)",
  "device_id": "string (required)",
  "anomaly": "number 0..1 (optional)",
  "device_risk": "number 0..1 (optional)"
}
```

**Response (200 OK):**
```json
{
  "decision": "ALLOW|CHALLENGE|BLOCK",
  "score": 0.0..1.0,
  "trust": 0.05..1.0,
  "reasons": ["velocity_spike", "high_amount", "country_shift"],
  "audit_hash": "sha256_hex",
  "block_index": 12345,
  "receipt_seq": 42,
  "version": "6.4.2",
  "timestamp": 1719072000.0,
  "challenge_url": "https://sebbi.pro/verify-challenge?token=...",
  "challenge_expires_in": 900
}
```

**Error responses:**
- `401 Unauthorized` - Missing or invalid API key
- `403 Forbidden` - Account inactive
- `429 Too Many Requests` - Rate limited or quota exceeded
- `503 Service Unavailable` - Server overloaded

---

## Account Management

### POST /api/keys or /signup
Create a new API key.

**Request body:**
```json
{
  "email": "user@example.com (required)",
  "phone": "+441234567890 (optional)",
  "name": "John Doe (optional)",
  "org": "Acme Corp (optional)",
  "org_type": "Enterprise|SME (optional)",
  "product": "aileash|guardian|sonicboom|sentinel (default: aileash)",
  "devices": 1..1000 (default: 1),
  "ref_code": "REF-XXXX-1234 (optional)"
}
```

**Response (200 OK):**
```json
{
  "api_key": "al_live_...",
  "email": "user@example.com",
  "product": "aileash",
  "devices": 1,
  "monthly": 0.50,
  "quota": 100,
  "ref_code": "REF-JOHN-5678",
  "badge_id": "abc123def456",
  "message": "100 free decisions. After trial: £0.50/month via Stripe."
}
```

---

## Verification & Inspection

### GET /api/spec
Engine specification (no auth required).

**Response (200 OK):**
```json
{
  "engine": "AILeash v6.4.2 Forensic Capture",
  "version": "6.4.2",
  "features": ["microsecond timing", "full request context", "signal derivation", "decision trace", "geoip lookup", "chain continuity", "guardian patterns", "ceop ready"]
}
```

### GET /api/verify-chain
Full audit chain integrity check (no auth required).

**Response (200 OK):**
```json
{
  "valid": true,
  "blocks": 45678,
  "tip": "abc123...",
  "message": "Chain intact"
}
```

### GET /api/health
Server health & load (no auth required).

**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "6.4.2",
  "rps": 42
}
```

---

## Billing

### POST /stripe-webhook
Stripe webhook receiver (signature verified).

**Supports:**
- `checkout.session.completed`
- `invoice.paid`
- `customer.subscription.deleted`
- `invoice.payment_failed`

---

## Forensic Evidence (v6.4.2)

### GET /api/forensic/{audit_id}
Full forensic reconstruction for a specific decision (auth required).

**Response (200 OK):**
```json
{
  "request_context": {
    "ip": "203.0.113.42",
    "port": 54321,
    "protocol": "https",
    "tls_version": "1.3",
    "tls_cipher": "TLS_AES_256_GCM_SHA384",
    "user_agent": "Mozilla/5.0...",
    "device_fingerprint": "a1b2c3d4e5f6g7h8"
  },
  "timing_phases": {
    "init": {"delta_ms": 0.001},
    "auth_complete": {"delta_ms": 0.234},
    "signals_computed": {"delta_ms": 1.045},
    "decision_made": {"delta_ms": 1.056},
    "context_extracted": {"delta_ms": 1.078},
    "sealed": {"delta_ms": 1.234}
  },
  "signal_derivation": {
    "trust": {"raw": 0.75, "normalized": 0.75, "weight": 0.30},
    "velocity_60s": {"raw": 5, "normalized": 0.25, "weight": 0.15},
    "amount": {"raw": 150.0, "normalized": 0.31, "weight": 0.15}
  },
  "decision_trace": {
    "score": 0.42,
    "decision": "CHALLENGE",
    "reasons": ["high_amount", "velocity_spike"]
  },
  "geoip_context": {
    "country": "GB",
    "asn": "AS12345",
    "city": "London"
  },
  "velocity_snapshot": {"60s": 5, "5m": 12, "1h": 78},
  "chain_continuity": [
    {"block_id": 12343, "hash": "...prev_prev..."},
    {"block_id": 12344, "hash": "...prev..."},
    {"block_id": 12345, "hash": "...current..."}
  ]
}
```

---

## Guardian Network Safeguarding (v6.4.2)

### POST /api/guardian/pattern-detect
Detect predatory patterns in network.

**Auth:** Bearer token (Guardian product key)

**Request body:**
```json
{
  "network_id": "network_001",
  "user_id": "suspected_user_id",
  "events": [
    {"ts": 1719072000, "action": "contact"},
    {"ts": 1719072100, "action": "request_media"},
    {"ts": 1719072200, "action": "isolation_attempt"}
  ]
}
```

**Response (200 OK):**
```json
{
  "pattern_detected": true,
  "pattern_type": "sustained_contact",
  "severity": "medium",
  "confidence": 0.68,
  "behavioral_timeline": [
    {"ts": 1719072000, "action": "contact", "severity": "low"},
    {"ts": 1719072100, "action": "request_media", "severity": "medium"},
    {"ts": 1719072200, "action": "isolation_attempt", "severity": "high"}
  ],
  "audit_chain": "abc123...",
  "recommended_action": "Contact CEOP immediately"
}
```

### POST /api/guardian/report-ceop
Report detected pattern to CEOP (UK Child Exploitation & Online Protection Command).

**Auth:** Bearer token (Guardian product key)

**Request body:**
```json
{
  "network_id": "network_001",
  "user_id": "suspected_user_id",
  "pattern_type": "sustained_contact",
  "severity": "high",
  "audit_chain": "abc123..."
}
```

**Response (200 OK):**
```json
{
  "report_ref": "CEOP-A1B2C3D4E5F6",
  "timestamp": 1719072300,
  "status": "submitted",
  "message": "Evidence package sealed and prepared for CEOP review"
}
```

---

## Pricing

- **AILeash:** 50p per device per month
- **Guardian:** Free for safeguarding teams, permanently
- **SonicBoom:** 50p per device per month
- **Sentinel:** 50p per device per month

**Free tier:** 100 decisions per month, no credit card required
