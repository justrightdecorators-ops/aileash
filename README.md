# AILeash Live Governance Engine (`sebbi.pro`)

[![Compliance: EU AI Act 2024/1689](https://shields.io)](https://europa.eu)
[![Latency: 0ms Overhead](https://shields.io)]()
[![Security: SHA--256 Chained](https://shields.io)]()

> **Deterministic AI Infrastructure for Regulated Enterprises, High-Velocity Financial Systems, and Autonomous Agents.**

AILeash is a zero-dependency, ultra-low-latency real-time governance firewall built explicitly to meet the stringent operational requirements of the **EU AI Act (Regulation 2024/1689)** ahead of the August 2026 enforcement deadlines.

---

## 🏛️ Core Compliance Architecture

AILeash maps directly to the legal obligations mandated for providers and deployers of high-risk AI systems:

### 🔹 Article 13: Transparency and Provision of Information
* **The Mechanism**: Every single API decision returns an explicit, explainable signal breakdown. 
* **The Response Contract**: Decisions are never "black box." System responses provide a clear telemetry log (`velocity_spike`, `country_shift`, etc.) to guarantee mathematical auditability.

### 🔹 Article 14: Human Oversight
* **The Mechanism**: Built-in 3-Tier Decision Engine (`ALLOW`, `CHALLENGE`, `BLOCK`).
* **The Enforcement**: Actions triggering risk anomalies automatically emit a `CHALLENGE` state, forcing integration pipelines to route the payload to human-in-the-loop review queues before execution can proceed.

### 🔹 Articles 9 & 12: Record-Keeping and Audit Integrity
* **The Mechanism**: Cryptographically sealed forensic trails.
* **The Enforcement**: Every response is bound by a tamper-evident **SHA-256 chained audit hash**. Any attempt to alter historical telemetry or bypass enforcement breaks the cryptographic chain instantly, providing forensic-grade evidence retention.

---

## ⚡ The 9-Signal Risk Framework

AILeash concurrently evaluates incoming requests across nine distinct risk vectors in real time:
1. **Velocity Tracking (01-03)**: Triple-window observation (60s, 5m, 1h) to neutralize API extraction and payload spamming.
2. **Adaptive Trust (04)**: Real-time user trust decay and recovery models.
3. **Logarithmic Amount Scoring (05)**: Financial asset exposure weighting scaled dynamically by transaction size.
4. **Device Integrity Risk (06)**: Hardware and client stack anomaly ingestion.
5. **Behavioural Pipeline Sync (07)**: Ingests external ML model outputs into a deterministic final rule matrix.
6. **Geographic Compliance (08-09)**: Cross-border jurisdiction evaluation across 150+ regions against strict safe-country allowlists.

---

## 🚀 Technical Quickstart

AILeash is architected to run with **zero dependencies** and integrates into any production middleware in under five minutes.

### Production Endpoint
```http
POST https://sebbi.pro
Authorization: Bearer <your_live_api_key>
Content-Type: application/json
```

### Pure cURL Implementation
```bash
curl -X POST https://sebbi.pro \
  -H "Authorization: Bearer al_live_production_key" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id":    "enterprise_user_881",
    "action":     "wire_transfer",
    "amount":     25000,
    "country":    "UK",
    "device_id":  "secure_endpoint_client",
    "device_risk": 0.05,
    "anomaly":    0.01
  }'
```

### Deterministic Payload Response
```json
{
  "decision": "ALLOW",
  "score": 0.2841,
  "trust": 0.8120,
  "reasons": [],
  "audit_hash": "a3f9c2d1b4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1"
}
```

---

## 🛠️ Infrastructure Component (`app.py`)

This repository contains the lightweight production routing component built on the high-performance **Pyramid** WSGI framework to handle SEO discoverability, global indexing, and semantic validation without impacting the main scoring engine runtime.

### Running the Engine Node
1. Install core WSGI routing assets:
   ```bash
   pip install pyramid
   ```
2. Fire up the local network listener:
   ```bash
   python app.py
   ```

---

## 📈 System Metrics
* **Extra Latency Overhead**: 0ms 
* **Engine Type**: 100% Deterministic Risk Architecture
* **Target Enforcement Horizon**: EU AI Act August 2026 Ready

---
*Built by Monop, Blyth UK. Managed and deployed at [sebbi.pro](https://sebbi.pro).*
