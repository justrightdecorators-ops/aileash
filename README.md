# AILeash - Governance Engine

A pure Python governance engine for scoring AI actions with fraud detection, trust tracking, and immutable audit logging.

## Features

- **Multi-factor Risk Scoring**: Evaluates trust, velocity, device risk, anomaly detection, location shifts, and transaction amounts
- **Trust System**: Dynamic trust scores that adjust based on user behavior (ALLOW/CHALLENGE/BLOCK decisions)
- **Velocity Detection**: Monitors action frequency across 60s, 5m, and 1h windows
- **Audit Trail**: Immutable hash chain for compliance and forensics
- **Thread-safe**: Concurrent request handling with SQLite locking
- **Zero Dependencies**: Pure Python — no external libraries required

## API Endpoints

### GET `/health`
Liveness check.

**Response:**
```json
{
  "status": "ok",
  "service": "AILeash Governance Engine",
  "version": "1.0.0"
}
```

### POST `/govern`
Score an AI action event.

**Request:**
```json
{
  "user_id": "user123",
  "action": "transfer",
  "amount": 1000,
  "country": "US",
  "device_id": "device456",
  "anomaly": 0.2,
  "device_risk": 0.1
}
```

**Response:**
```json
{
  "decision": "ALLOW",
  "score": 0.2341,
  "trust": 0.5051,
  "reasons": [],
  "audit_hash": "abc123..."
}
```

**Decisions:**
- `ALLOW` (score < 0.35)
- `CHALLENGE` (0.35 ≤ score < 0.70)
- `BLOCK` (score ≥ 0.70)

### GET `/audit`
Retrieve last 50 audit log records.

**Response:**
```json
{
  "count": 50,
  "records": [
    {
      "ts": 1234567890.123,
      "user_id": "user123",
      "event": { ... },
      "result": { ... },
      "prev_hash": "genesis",
      "audit_hash": "abc123..."
    }
  ]
}
```

### GET `/user/<id>`
Get user trust state and metadata.

**Response:**
```json
{
  "user_id": "user123",
  "trust": 0.5051,
  "last_country": "US"
}
```

## Risk Scoring Breakdown

Score is computed from weighted signals (0.0 - 1.0):

| Factor | Weight | Description |
|--------|--------|-------------|
| Trust (inverse) | 30% | 1 - user_trust |
| 60s Velocity | 15% | Min(count / 20, 1) |
| 5m Velocity | 10% | Min(count / 50, 1) |
| 1h Velocity | 10% | Min(count / 200, 1) |
| Amount | 15% | Min(log(amount) / log(10000), 1) |
| Device Risk | 10% | Direct signal value |
| Anomaly Score | 10% | Direct signal value |
| Country Shift | Bonus | +0.10 if different from last |
| Unsafe Country | Bonus | +0.10 if not in SAFE_COUNTRIES |

**Safe Countries:** UK, US, DE, FR, CA, AU

## Deployment

### Local
```bash
python server.py
```

Runs on `http://0.0.0.0:8080` (configurable via `PORT` env var)

### Railway
Deploy with the included `railway.json`:
```bash
railway up
```

- Uses NIXPACKS builder
- Starts with `python server.py`
- Health check: `/health`
- Restart policy: ON_FAILURE (max 3 retries)

## Database

SQLite database (`aileash.db`) with two tables:

### users
| Column | Type | Purpose |
|--------|------|----------|
| user_id | TEXT (PK) | Unique user identifier |
| trust | REAL | Trust score (0.05-1.0) |
| last_country | TEXT | Last known country |

### audit_log
| Column | Type | Purpose |
|--------|------|----------|
| id | INT (PK) | Auto-increment |
| ts | REAL | Timestamp |
| user_id | TEXT (FK) | Reference to user |
| event_json | TEXT | Original event |
| result_json | TEXT | Governance decision |
| prev_hash | TEXT | Previous audit hash |
| audit_hash | TEXT (UNIQUE) | Hash chain entry |

## Implementation Notes

- **Thread Safety**: Database operations use `threading.Lock` to prevent concurrent modification issues
- **Velocity Windows**: In-memory deques with time-based pruning. Lost on restart (consider persistence if needed)
- **Trust Bounds**: Clamped to [0.05, 1.0] to prevent accounts from being permanently unrecoverable
- **Audit Chain**: SHA256 hash chain for immutability; starts with "GENESIS" block

## Known Limitations

1. Velocity windows are not persisted—restarting loses history
2. No atomic transaction for chain_tip() + append_audit() (potential race condition under extreme load)
3. User dictionary cleanup not implemented (memory grows with unique users)
4. No input validation for numeric signal ranges (amount, anomaly, device_risk)

## Future Improvements

- [ ] Persist velocity windows to database
- [ ] Atomic audit chain writes with transactions
- [ ] Configurable safe countries and thresholds
- [ ] Machine learning-based anomaly detection
- [ ] Webhook notifications for high-risk events
- [ ] Rate limiting and DDoS protection
- [ ] Multi-tenant support with API keys

## License

Proprietary
