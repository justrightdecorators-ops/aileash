# AILeash v3.0.0

Real-time AI action governance engine for EU AI Act compliance.

## Overview

AILeash scores, audits, and controls every AI action before execution. Multi-signal risk assessment with cryptographic audit trails. Built for high-risk AI systems.

**Features:**
- Real-time risk scoring (<15ms decisions)
- SHA-256 chained audit logs with Merkle verification
- User trust decay modeling
- Velocity tracking (60s/5m/1h windows)
- Action-type risk profiles
- GDPR Art.22 compliant decision pathways
- Zero dependencies (pure Python)
- Deterministic, reproducible scoring

## Regulatory Alignment

- **EU AI Act** (Reg. 2024/1689) — Art. 6, 9, 12, 13, 17
- **GDPR** — Art. 22 (human oversight for automated decisions)
- **ISO 42001** — AI management system framework

## Quick Start

### Local Development

```bash
# Clone
git clone https://github.com/justrightdecorators-ops/aileash.git
cd aileash

# Install (no external dependencies)
python3 main.py
```

Server runs on `http://localhost:8080`

### Environment Variables

```bash
PORT=8080                          # HTTP server port
STRIPE_SECRET=sk_live_...          # Stripe API key (optional)
STRIPE_PRICE_ID=price_...          # Stripe price ID (optional)
```

### First Request

1. Visit http://localhost:8080 → Get a free API key
2. Make a governance call:

```bash
curl -X POST http://localhost:8080/api/govern \
  -H "Authorization: Bearer your_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "agent_01",
    "action": "payment",
    "amount": 500,
    "country": "US",
    "device_id": "d1",
    "anomaly": 0.2,
    "device_risk": 0.1
  }'
```

**Response:**

```json
{
  "decision": "ALLOW",
  "score": 0.2847,
  "trust": 0.505,
  "reasons": [],
  "audit_hash": "a3f9c1d8...",
  "merkle_root": "7e2b4f91...",
  "version": "3.0.0"
}
```

## API Endpoints

### `POST /api/govern`

Score an AI action.

**Headers:**
```
Authorization: Bearer al_live_<key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "user_id": "string (required)",
  "action": "payment|wire_transfer|tool_call|data_export|...",
  "amount": "number (required)",
  "country": "string ISO 3166 (required)",
  "device_id": "string (required)",
  "anomaly": "number 0-1 (required)",
  "device_risk": "number 0-1 (required)"
}
```

**Response:**
```json
{
  "decision": "ALLOW | CHALLENGE | BLOCK",
  "score": "number 0-1",
  "trust": "number 0-1",
  "reasons": ["array of string"],
  "audit_hash": "SHA-256 hex",
  "merkle_root": "Merkle root of all audit hashes",
  "version": "3.0.0"
}
```

**Decisions:**
- **ALLOW** (score < 0.35) — Action proceeds. Trust increases +1%.
- **CHALLENGE** (0.35 ≤ score < 0.70) — Requires human review. Trust decreases -2%.
- **BLOCK** (score ≥ 0.70) — Action halted. Trust decreases -8%.

### `GET /api/verify`

Verify audit chain integrity.

**Response:**
```json
{
  "valid": true,
  "blocks": 42,
  "merkle_root": "7e2b4f91...",
  "message": "Chain intact — all hashes verified"
}
```

### `GET /health`

Health check.

**Response:**
```json
{
  "status": "ok",
  "version": "3.0.0"
}
```

### `POST /api/keys`

Generate API key (from landing page form).

**Request Body:**
```json
{
  "email": "user@example.com",
  "stripe_customer": "cus_... (optional)"
}
```

**Response:**
```json
{
  "key": "al_live_...",
  "email": "user@example.com"
}
```

## Risk Scoring

Decision score is a weighted sum of 9 signals:

| Signal | Weight | Notes |
|--------|--------|-------|
| Trust (1 - user_trust) | 30% | User-specific trust history |
| Velocity 60s | 15% | Actions in last 60 seconds (capped at 20) |
| Velocity 5m | 10% | Actions in last 5 minutes (capped at 50) |
| Velocity 1h | 10% | Actions in last hour (capped at 200) |
| Amount | 15% | Log scale up to $10k |
| Device Risk | 10% | External device risk score |
| Anomaly | 10% | Behavioral anomaly score |
| Country Shift | +10% | Different country than last action |
| Unsafe Country | +10% | Country not in SAFE_COUNTRIES list |
| Action Profile | +base% | Action-specific base risk (0-18%) |

**Safe Countries:** UK, US, DE, FR, CA, AU, NL, SE, NO, DK, FI, IE, NZ

**Action Profiles:**
- `wire_transfer`: +18% base
- `financial_transfer`: +18% base
- `payment`: +12% base
- `tool_call`: +12% base
- `account_change`: +14% base
- `data_export`: +15% base
- `content_action`: +8% base
- `default`: +0% base

## Database Schema

SQLite3 (file: `aileash.db`)

```sql
-- User trust profiles
CREATE TABLE users (
  user_id TEXT PRIMARY KEY,
  trust REAL DEFAULT 0.5,
  last_country TEXT
);

-- Immutable audit log (SHA-256 chained)
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  user_id TEXT,
  event_json TEXT,
  result_json TEXT,
  prev_hash TEXT,
  audit_hash TEXT UNIQUE,
  merkle_root TEXT
);

-- API key management
CREATE TABLE api_keys (
  key TEXT PRIMARY KEY,
  email TEXT,
  stripe_customer TEXT,
  actions_used INTEGER DEFAULT 0,
  created REAL,
  active INTEGER DEFAULT 1
);

-- Configuration
CREATE TABLE config (
  k TEXT PRIMARY KEY,
  v TEXT
);

-- Velocity tracking
CREATE TABLE velocity_history (
  user_id TEXT,
  window_type TEXT,
  timestamps TEXT,
  PRIMARY KEY(user_id, window_type)
);
```

## Deployment

### Docker

```bash
docker build -t aileash:3.0.0 .
docker run -p 8080:8080 \
  -e STRIPE_SECRET=sk_live_... \
  -e PORT=8080 \
  aileash:3.0.0
```

### Railway

1. Push to GitHub
2. Connect repo to Railway
3. Set environment variables in Railway dashboard:
   - `PORT=8080`
   - `STRIPE_SECRET=sk_live_...`
   - `STRIPE_PRICE_ID=price_...`
4. Deploy

### Render / Fly.io / AWS Lambda

See `Dockerfile` and `railway.toml` for configuration.

## Security

- **No external dependencies** — Reduces supply chain risk
- **Thread-safe database access** — Mutex locks on all DB operations
- **Deterministic hashing** — SHA-256 with JSON key sorting
- **Merkle proofs** — Tamper-evident chains
- **Bearer token auth** — Standard HTTP authentication
- **CORS open** — Allow frontend integration (restrict in production)

## Testing

```bash
# Verify chain integrity
curl http://localhost:8080/api/verify

# Health check
curl http://localhost:8080/health

# Generate test key
curl -X POST http://localhost:8080/api/keys \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

## License

MIT

## Support

- Docs: https://docs.aileash.dev
- Issues: https://github.com/justrightdecorators-ops/aileash/issues
- Email: support@aileash.dev
