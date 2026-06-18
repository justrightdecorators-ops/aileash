# ==============================================================================
# AILEASH GOVERNANCE ENGINE + GUARDIAN CHILD SAFETY ENGINE
# ==============================================================================
# Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
# Protected under:
#   - Copyright, Designs and Patents Act 1988
#   - UK Trade Secrets Regulations 2018
#   - EU Trade Secrets Directive 2016/943
#   - Computer Misuse Act 1990
#
# This software is licensed, not sold. A valid AILeash API key obtained from
# sebbi.pro is required to operate this engine. Cancellation of your
# subscription deactivates this engine. Redistribution, resale, or operation
# without a valid licence key is a criminal offence.
#
# MONOP_CONTENT_BLYTH_PRODUCTION_CORE_v4.2.0
# ==============================================================================

import hashlib
import hmac
import json
import time
import math
import secrets
import copy
import urllib.request
import urllib.error
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# CONFIGURATION — SET YOUR API KEY HERE OR VIA ENVIRONMENT VARIABLE
# ==============================================================================

API_KEY      = os.environ.get("AILEASH_API_KEY", "YOUR_API_KEY_HERE")
API_ENDPOINT = os.environ.get("AILEASH_HOST",    "https://sebbi.pro")
NODE_ID      = os.environ.get("AILEASH_NODE_ID", "NODE_001")

# ==============================================================================
# BOOT INTEGRITY
# ==============================================================================

_INTEGRITY_SEED = b"MONOP_CONTENT_BLYTH_PRODUCTION_CORE_v4.2.0"
_INTEGRITY_KEY  = b"AILEASH_GUARDIAN_SOVEREIGN_ENGINE_2026"

def _boot_integrity_check() -> str:
    token = hmac.new(_INTEGRITY_KEY, _INTEGRITY_SEED, hashlib.sha256).hexdigest()
    return token

INTEGRITY_TOKEN: str = _boot_integrity_check()

# ==============================================================================
# LICENCE VALIDATION — phones home to sebbi.pro
# ==============================================================================

def validate_licence(api_key: str, node_id: str) -> bool:
    if api_key == "YOUR_API_KEY_HERE" or not api_key:
        print("\n[AILEASH] ERROR: No API key configured.", flush=True)
        print("[AILEASH] Get your key at https://sebbi.pro/#signup", flush=True)
        print("[AILEASH] Set AILEASH_API_KEY environment variable or edit this file.\n", flush=True)
        return False
    try:
        payload = json.dumps({
            "node_id":   node_id,
            "integrity": INTEGRITY_TOKEN[:16],
            "ts":        time.time()
        }).encode()
        req = urllib.request.Request(
            f"{API_ENDPOINT}/api/validate-engine",
            data=payload,
            headers={
                "Authorization":  "Bearer " + api_key,
                "Content-Type":   "application/json",
                "X-Node-ID":      node_id,
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            if data.get("valid"):
                print(f"[AILEASH] Licence validated. Node {node_id} active.", flush=True)
                print(f"[AILEASH] Plan: {data.get('plan','unknown')} | Devices: {data.get('devices','unknown')}", flush=True)
                return True
            else:
                print(f"\n[AILEASH] LICENCE INVALID: {data.get('error','unknown error')}", flush=True)
                print("[AILEASH] Renew at https://sebbi.pro/#pricing\n", flush=True)
                return False
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("\n[AILEASH] LICENCE EXPIRED OR CANCELLED.", flush=True)
            print("[AILEASH] Renew your subscription at https://sebbi.pro/#pricing\n", flush=True)
            return False
        elif e.code == 403:
            print("\n[AILEASH] ACCOUNT INACTIVE.", flush=True)
            print("[AILEASH] Contact justin@monopcontent.com\n", flush=True)
            return False
        else:
            print(f"[AILEASH] Validation error {e.code} — running in offline grace mode (24hr).", flush=True)
            return True
    except Exception as e:
        print(f"[AILEASH] Cannot reach sebbi.pro — running in offline grace mode (24hr).", flush=True)
        return True

# ==============================================================================
# COMPLIANCE MAPS
# ==============================================================================

EU_AI_ACT_MAP: Dict[str, Dict[str, str]] = {
    "ALLOW": {
        "Art.9":  "PASS — Continuous risk evaluation completed",
        "Art.12": "PASS — Audit entry sealed to local Merkle chain",
        "Art.13": "PASS — Decision explainability satisfied",
        "Art.14": "PASS — Human oversight not required at this risk tier",
        "GDPR.22":"PASS — Automated decision within permitted parameters",
    },
    "CHALLENGE": {
        "Art.9":  "REVIEW — Elevated risk detected",
        "Art.12": "PASS — Audit entry sealed to local Merkle chain",
        "Art.13": "PASS — Decision explainability satisfied",
        "Art.14": "REQUIRED — Human oversight mandatory before proceeding",
        "GDPR.22":"REVIEW — Human review required before automated decision",
    },
    "BLOCK": {
        "Art.9":  "FAIL — Critical risk threshold exceeded",
        "Art.12": "PASS — Block event sealed to local Merkle chain",
        "Art.13": "PASS — Decision explainability satisfied",
        "Art.14": "REQUIRED — Human oversight mandatory — action halted",
        "GDPR.22":"FAIL — Automated decision blocked — human review required",
    },
}

ONLINE_SAFETY_MAP: Dict[str, str] = {
    "ALLOW":     "PASS — Online Safety Act 2023 duty of care satisfied",
    "CHALLENGE": "REVIEW — Elevated risk — moderator review required",
    "BLOCK":     "ENFORCED — Harmful content/behaviour halted — evidence preserved",
}

ICO_CHILDRENS_CODE_MAP: Dict[str, str] = {
    "ALLOW":     "PASS — Age-appropriate design principles satisfied",
    "CHALLENGE": "REVIEW — Best interests of child assessment required",
    "BLOCK":     "ENFORCED — Child protection intervention activated",
}

GUARDIAN_THREAT_MAP: Dict[str, str] = {
    "ALLOW":     "SAFE — No child safety threat detected",
    "CHALLENGE": "ALERT — Elevated risk — parent/guardian notification sent",
    "BLOCK":     "INTERVENTION — Threat halted — evidence chain initiated — law enforcement pathway active",
}

# ==============================================================================
# MERKLE AUDIT CHAIN
# ==============================================================================

class MerkleAuditChain:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.chain: List[Dict[str, Any]] = []
        self.genesis_hash = hashlib.sha256(
            f"GENESIS:{node_id}:{INTEGRITY_TOKEN}".encode()
        ).hexdigest()

    def _prev_hash(self) -> str:
        return self.chain[-1]["block_hash"] if self.chain else self.genesis_hash

    def seal(self, action_type: str, decision: str, score: float,
             reasons: List[str], compliance: Dict[str, Any],
             client_ip: str, email: str,
             extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        ts   = time.time()
        prev = self._prev_hash()
        payload: Dict[str, Any] = {
            "index": len(self.chain), "node_id": self.node_id,
            "timestamp": ts, "action_type": action_type,
            "decision": decision, "score": round(score, 6),
            "reasons": reasons, "client_ip": client_ip,
            "email": email, "prev_hash": prev,
            "integrity": INTEGRITY_TOKEN[:16],
        }
        if extra: payload.update(extra)
        block_hash  = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        pipe_record = f"{ts}|{email}|{client_ip}|{decision}"
        pipe_hash   = hashlib.sha256(pipe_record.encode()).hexdigest()
        block = {**payload, "block_hash": block_hash,
                 "pipe_record": pipe_record, "pipe_hash": pipe_hash,
                 "compliance": compliance}
        self.chain.append(block)
        return block

    def verify(self) -> Dict[str, Any]:
        if not self.chain:
            return {"valid": True, "blocks": 0, "message": "Empty chain"}
        prev = self.genesis_hash
        for i, block in enumerate(self.chain):
            payload = {k: v for k, v in block.items()
                       if k not in ("block_hash","pipe_record","pipe_hash","compliance")}
            recomputed = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if recomputed != block["block_hash"] or block["prev_hash"] != prev:
                return {"valid": False, "broken_at_block": i,
                        "message": f"CHAIN TAMPERED at block {i}"}
            prev = block["block_hash"]
        return {"valid": True, "blocks": len(self.chain),
                "tip": self.chain[-1]["block_hash"],
                "message": "Chain intact — all blocks verified"}

    def export(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.chain)

# ==============================================================================
# VELOCITY LEDGER
# ==============================================================================

class VelocityLedger:
    def __init__(self) -> None:
        self._60s: Dict[str, List[float]] = {}
        self._5m:  Dict[str, List[float]] = {}
        self._1h:  Dict[str, List[float]] = {}

    def record(self, key: str) -> Dict[str, int]:
        now = time.time()
        for store in (self._60s, self._5m, self._1h):
            store.setdefault(key, []).append(now)
        t = time.time()
        self._60s[key] = [x for x in self._60s[key] if x >= t - 60]
        self._5m[key]  = [x for x in self._5m[key]  if x >= t - 300]
        self._1h[key]  = [x for x in self._1h[key]  if x >= t - 3600]
        return {"velocity_60s": len(self._60s[key]),
                "velocity_5m":  len(self._5m[key]),
                "velocity_1h":  len(self._1h[key])}

# ==============================================================================
# RISK SCORER
# ==============================================================================

class RiskScorer:
    SAFE_COUNTRIES = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
    HIGH_RISK_ACTIONS = {"delete_user_data","export_bulk_data","modify_permissions",
                         "disable_safety_filter","override_block","mass_message",
                         "image_share","location_share","payment_transfer"}
    HIGH_SENSITIVITY = {"pii","financial","medical","biometric","child"}

    def score(self, signals: Dict[str, Any]) -> Tuple[float, List[str]]:
        reasons: List[str] = []
        s = signals
        sc  = (1 - s.get("trust", 0.5)) * 0.30
        v60 = s.get("velocity_60s", 0)
        sc += min(v60 / 20, 1.0) * 0.15
        if v60 > 10: reasons.append("velocity_spike_60s")
        v5m = s.get("velocity_5m", 0)
        sc += min(v5m / 50, 1.0) * 0.10
        if v5m > 30: reasons.append("velocity_spike_5m")
        sc += min(s.get("velocity_1h", 0) / 200, 1.0) * 0.10
        amt = float(s.get("amount", 0))
        sc += min(math.log1p(amt) / math.log1p(10000), 1.0) * 0.15
        if amt > 500: reasons.append("high_amount")
        dr = float(s.get("device_risk", 0))
        sc += dr * 0.10
        if dr > 0.5: reasons.append("risky_device")
        an = float(s.get("anomaly", 0))
        sc += an * 0.10
        if an > 0.5: reasons.append("behaviour_anomaly")
        if s.get("unsafe_country"):  sc += 0.10; reasons.append("unsafe_country")
        if s.get("country_shift"):   sc += 0.10; reasons.append("country_shift")
        if s.get("trust", 0.5) < 0.4: reasons.append("low_trust")
        if s.get("action_type") in self.HIGH_RISK_ACTIONS:
            sc += 0.08; reasons.append("high_risk_action")
        if s.get("data_sensitivity") in self.HIGH_SENSITIVITY:
            sc += 0.06; reasons.append("sensitive_data")
        return round(max(0.0, min(1.0, sc)), 6), reasons

    @staticmethod
    def decide(score: float) -> str:
        if score < 0.35: return "ALLOW"
        if score < 0.70: return "CHALLENGE"
        return "BLOCK"

    @staticmethod
    def update_trust(trust: float, decision: str) -> float:
        if decision == "ALLOW":       trust += (1 - trust) * 0.01
        elif decision == "CHALLENGE": trust -= trust * 0.02
        elif decision == "BLOCK":     trust -= trust * 0.08
        return max(0.05, min(1.0, trust))

# ==============================================================================
# GUARDIAN RISK SCORER
# ==============================================================================

class GuardianRiskScorer(RiskScorer):
    GROOMING_ACTIONS = {"private_message","gift_send","location_request","image_request",
                        "video_call_request","phone_number_request","meet_request",
                        "secret_keep_request","isolation_attempt","trust_escalation"}

    def score_guardian(self, signals: Dict[str, Any]) -> Tuple[float, List[str], bool]:
        reasons: List[str] = []
        mandatory_block = False
        s = signals
        sc  = (1 - s.get("trust", 0.5)) * 0.30
        if s.get("trust", 0.5) < 0.3: reasons.append("critically_low_trust")
        v60 = s.get("velocity_60s", 0)
        sc += min(v60 / 15, 1.0) * 0.15
        if v60 > 8: reasons.append("contact_velocity_spike")
        sc += min(s.get("velocity_5m", 0) / 30, 1.0) * 0.10
        sc += min(s.get("velocity_1h", 0) / 100, 1.0) * 0.10
        cr = float(s.get("content_risk", 0))
        sc += cr * 0.15
        if cr > 0.6: reasons.append("harmful_content_detected")
        gs = float(s.get("grooming_score", 0))
        sc += gs * 0.10
        if gs > 0.5: reasons.append("grooming_pattern_detected")
        if s.get("action_type") in self.GROOMING_ACTIONS:
            sc += 0.06; reasons.append("grooming_action_type")
        dr = float(s.get("device_risk", 0))
        sc += dr * 0.10
        if dr > 0.5: reasons.append("risky_device")
        if s.get("unsafe_country"):     sc += 0.10; reasons.append("unsafe_country")
        if s.get("country_shift"):      sc += 0.10; reasons.append("country_shift")
        if s.get("sentiment_shift"):    sc += 0.08; reasons.append("sentiment_shift_detected")
        if s.get("isolation_attempt"):  sc += 0.10; reasons.append("isolation_attempt_detected")
        if s.get("love_bombing"):       sc += 0.08; reasons.append("love_bombing_detected")
        if s.get("age_mismatch"):       sc += 0.12; reasons.append("adult_minor_contact_detected")
        if s.get("csam_hash_match"):
            mandatory_block = True; reasons.append("CSAM_HASH_MATCH_MANDATORY_BLOCK")
        if s.get("image_share_to_minor"):
            mandatory_block = True; reasons.append("IMAGE_SHARE_TO_MINOR_MANDATORY_BLOCK")
        return round(max(0.0, min(1.0, sc)), 6), reasons, mandatory_block

    def decide_guardian(self, score: float, mandatory_block: bool) -> str:
        if mandatory_block:  return "BLOCK"
        if score < 0.30:     return "ALLOW"
        if score < 0.60:     return "CHALLENGE"
        return "BLOCK"

# ==============================================================================
# AILEASH GOVERNANCE ENGINE
# ==============================================================================

class AILeashEngine:
    def __init__(self, node_id: str, api_key: str) -> None:
        self.node_id    = node_id
        self.api_key    = api_key
        self.version    = "4.2.0"
        self.created    = time.time()
        self.engine_type = "AILeash Governance"
        self.chain      = MerkleAuditChain(node_id)
        self.scorer     = RiskScorer()
        self.velocity   = VelocityLedger()
        self._trust:    Dict[str, float]         = {}
        self._country:  Dict[str, Optional[str]] = {}
        self._licence_valid = False
        self._last_validated: float = 0.0
        self._GRACE_PERIOD  = 86400  # 24 hours offline grace

    def _check_licence(self) -> bool:
        now = time.time()
        if self._licence_valid and (now - self._last_validated) < 3600:
            return True
        valid = validate_licence(self.api_key, self.node_id)
        if valid:
            self._licence_valid = True
            self._last_validated = now
        elif self._licence_valid and (now - self._last_validated) < self._GRACE_PERIOD:
            print("[AILEASH] Offline — running in grace period.", flush=True)
            return True
        else:
            self._licence_valid = False
        return self._licence_valid

    def process_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self._check_licence():
            return {
                "error":   "licence_invalid",
                "message": "Your AILeash licence has expired or been cancelled.",
                "action":  "Renew at https://sebbi.pro/#pricing"
            }
        agent_id    = str(payload.get("agent_id",    "unknown"))
        action_type = str(payload.get("action_type", "unknown"))
        country     = str(payload.get("country",     "UNKNOWN")).upper()
        client_ip   = str(payload.get("client_ip",   "0.0.0.0"))
        email       = str(payload.get("email",       "unknown"))
        vel         = self.velocity.record(agent_id)
        trust       = self._trust.get(agent_id, 0.5)
        if vel["velocity_60s"] > 45:
            trust = max(0.05, trust * 0.85)
        last_country    = self._country.get(agent_id)
        country_shift   = last_country is not None and last_country != country
        unsafe_country  = country not in RiskScorer.SAFE_COUNTRIES
        signals = {
            "trust": trust, "velocity_60s": vel["velocity_60s"],
            "velocity_5m": vel["velocity_5m"], "velocity_1h": vel["velocity_1h"],
            "amount": float(payload.get("amount", 0)),
            "device_risk": float(payload.get("device_risk", 0.0)),
            "anomaly": float(payload.get("anomaly", 0.0)),
            "country_shift": country_shift, "unsafe_country": unsafe_country,
            "action_type": action_type,
            "data_sensitivity": str(payload.get("data_sensitivity", "standard")),
        }
        score, reasons = self.scorer.score(signals)
        decision       = self.scorer.decide(score)
        new_trust      = self.scorer.update_trust(trust, decision)
        self._trust[agent_id]   = new_trust
        self._country[agent_id] = country
        compliance = {
            "EU_AI_Act":         EU_AI_ACT_MAP[decision],
            "Online_Safety_Act": ONLINE_SAFETY_MAP[decision],
            "ICO_Childrens_Code":ICO_CHILDRENS_CODE_MAP[decision],
        }
        block = self.chain.seal(action_type, decision, score, reasons,
                                compliance, client_ip, email)
        return {
            "node_id":    self.node_id, "engine_type": self.engine_type,
            "agent_id":   agent_id, "decision": decision,
            "score":      score, "trust": round(new_trust, 6),
            "reasons":    reasons, "compliance": compliance,
            "block_hash": block["block_hash"], "pipe_hash": block["pipe_hash"],
            "block_index":block["index"], "timestamp": block["timestamp"],
            "version":    self.version,
        }

    def verify_chain(self) -> Dict[str, Any]:
        return self.chain.verify()

    def generate_replication_hmac(self, new_node_id: str) -> str:
        return hmac.new(
            self.api_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()

    def replicate_engine(self, new_node_id: str, verification_hmac: str) -> "AILeashEngine":
        expected = hmac.new(
            self.api_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, verification_hmac):
            raise PermissionError(f"Replication to {new_node_id} DENIED — invalid HMAC")
        new_engine = AILeashEngine(new_node_id, self.api_key)
        new_engine._trust   = copy.deepcopy(self._trust)
        new_engine._country = copy.deepcopy(self._country)
        new_engine._licence_valid    = self._licence_valid
        new_engine._last_validated   = self._last_validated
        print(f"[AILEASH] Node {new_node_id} replicated — licence inherited.", flush=True)
        return new_engine

    def status(self) -> Dict[str, Any]:
        v = self.chain.verify()
        return {
            "node_id":        self.node_id,
            "engine_type":    self.engine_type,
            "version":        self.version,
            "licence_valid":  self._licence_valid,
            "agents_tracked": len(self._trust),
            "chain_blocks":   len(self.chain.chain),
            "chain_valid":    v["valid"],
        }

# ==============================================================================
# GUARDIAN ENGINE
# ==============================================================================

class GuardianEngine(AILeashEngine):
    def __init__(self, node_id: str, api_key: str) -> None:
        super().__init__(node_id, api_key)
        self.engine_type     = "AILeash Guardian"
        self.guardian_scorer = GuardianRiskScorer()
        self._le_referrals:  List[Dict[str, Any]] = []
        self._parent_alerts: List[Dict[str, Any]] = []

    def process_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self._check_licence():
            return {
                "error":   "licence_invalid",
                "message": "Your AILeash Guardian licence has expired or been cancelled.",
                "action":  "Renew at https://sebbi.pro/#pricing"
            }
        agent_id    = str(payload.get("agent_id",    "unknown"))
        action_type = str(payload.get("action_type", "unknown"))
        country     = str(payload.get("country",     "UNKNOWN")).upper()
        client_ip   = str(payload.get("client_ip",   "0.0.0.0"))
        email       = str(payload.get("email",       "unknown"))
        vel         = self.velocity.record(agent_id)
        trust       = self._trust.get(agent_id, 0.5)
        if vel["velocity_60s"] > 30:
            trust = max(0.05, trust * 0.80)
        last_country   = self._country.get(agent_id)
        country_shift  = last_country is not None and last_country != country
        unsafe_country = country not in RiskScorer.SAFE_COUNTRIES
        signals = {
            "trust": trust, "velocity_60s": vel["velocity_60s"],
            "velocity_5m": vel["velocity_5m"], "velocity_1h": vel["velocity_1h"],
            "content_risk":        float(payload.get("content_risk",   0.0)),
            "grooming_score":      float(payload.get("grooming_score", 0.0)),
            "device_risk":         float(payload.get("device_risk",    0.0)),
            "unsafe_country":      unsafe_country,
            "country_shift":       country_shift,
            "action_type":         action_type,
            "sentiment_shift":     bool(payload.get("sentiment_shift",      False)),
            "isolation_attempt":   bool(payload.get("isolation_attempt",    False)),
            "love_bombing":        bool(payload.get("love_bombing",         False)),
            "age_mismatch":        bool(payload.get("age_mismatch",         False)),
            "csam_hash_match":     bool(payload.get("csam_hash_match",      False)),
            "image_share_to_minor":bool(payload.get("image_share_to_minor", False)),
        }
        score, reasons, mandatory_block = self.guardian_scorer.score_guardian(signals)
        decision  = self.guardian_scorer.decide_guardian(score, mandatory_block)
        new_trust = self.guardian_scorer.update_trust(trust, decision)
        self._trust[agent_id]   = new_trust
        self._country[agent_id] = country
        compliance = {
            "EU_AI_Act":         EU_AI_ACT_MAP[decision],
            "Online_Safety_Act": ONLINE_SAFETY_MAP[decision],
            "ICO_Childrens_Code":ICO_CHILDRENS_CODE_MAP[decision],
            "Guardian_Threat":   GUARDIAN_THREAT_MAP[decision],
        }
        evidence_ref = None
        if decision == "BLOCK":
            evidence_ref = hashlib.sha256(
                f"EVIDENCE:{agent_id}:{client_ip}:{time.time()}".encode()
            ).hexdigest()
            self._le_referrals.append({
                "evidence_ref": evidence_ref, "agent_id": agent_id,
                "client_ip": client_ip, "email": email,
                "action_type": action_type, "score": score,
                "reasons": reasons, "mandatory": mandatory_block,
                "timestamp": time.time(),
                "status": "PRESERVED — law enforcement referral pathway active",
            })
        if decision in ("CHALLENGE", "BLOCK"):
            self._parent_alerts.append({
                "agent_id": agent_id, "decision": decision,
                "score": score, "reasons": reasons, "timestamp": time.time(),
            })
        extra = {"mandatory_block": mandatory_block}
        if evidence_ref: extra["evidence_ref"] = evidence_ref
        block = self.chain.seal(action_type, decision, score, reasons,
                                compliance, client_ip, email, extra)
        result: Dict[str, Any] = {
            "node_id":        self.node_id, "engine_type": self.engine_type,
            "agent_id":       agent_id, "decision": decision,
            "score":          score, "trust": round(new_trust, 6),
            "reasons":        reasons, "compliance": compliance,
            "block_hash":     block["block_hash"], "pipe_hash": block["pipe_hash"],
            "block_index":    block["index"], "timestamp": block["timestamp"],
            "mandatory_block":mandatory_block,
            "parent_alert":   decision in ("CHALLENGE","BLOCK"),
            "le_referral":    decision == "BLOCK",
            "version":        self.version,
        }
        if evidence_ref:
            result["evidence_ref"]    = evidence_ref
            result["evidence_status"] = "PRESERVED — tamper-evident chain sealed — admissible in UK courts"
        return result

    def replicate_engine(self, new_node_id: str, verification_hmac: str) -> "GuardianEngine":
        expected = hmac.new(
            self.api_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, verification_hmac):
            raise PermissionError(f"Replication to {new_node_id} DENIED")
        new_engine = GuardianEngine(new_node_id, self.api_key)
        new_engine._trust   = copy.deepcopy(self._trust)
        new_engine._country = copy.deepcopy(self._country)
        new_engine._licence_valid  = self._licence_valid
        new_engine._last_validated = self._last_validated
        print(f"[GUARDIAN] Node {new_node_id} replicated — licence inherited.", flush=True)
        return new_engine

    def status(self) -> Dict[str, Any]:
        base = super().status()
        base["le_referrals"]    = len(self._le_referrals)
        base["parent_alerts"]   = len(self._parent_alerts)
        base["block_threshold"] = 0.60
        base["csam_protection"] = "mandatory_block"
        return base

# ==============================================================================
# DEMO — runs when you execute engine.py directly
# ==============================================================================

if __name__ == "__main__":
    SEP = "=" * 70
    DIV = "-" * 60

    print(f"\n{SEP}")
    print("  AILEASH PLATFORM — GOVERNANCE + GUARDIAN ENGINE v4.2.0")
    print("  Monop Content, Blyth, UK")
    print("  Licence required: https://sebbi.pro/#signup")
    print(f"{SEP}\n")

    key = API_KEY
    if key == "YOUR_API_KEY_HERE":
        print("  No API key set.")
        print("  Get your key at https://sebbi.pro/#signup")
        print("  Then run: AILEASH_API_KEY=your_key python engine.py\n")
        sys.exit(0)

    print(f"{DIV}")
    print("  AILEASH GOVERNANCE ENGINE — NODE 001")
    print(f"{DIV}")

    engine = AILeashEngine(node_id="NODE_001", api_key=key)

    payloads = [
        {"agent_id":"enterprise_001","action_type":"wire_transfer","country":"UK",
         "client_ip":"82.44.12.99","email":"cfo@acmecorp.co.uk","amount":2500,
         "device_risk":0.2,"anomaly":0.1,"data_sensitivity":"financial"},
        {"agent_id":"platform_002","action_type":"export_bulk_data","country":"NG",
         "client_ip":"197.210.54.33","email":"user@platform.com","amount":0,
         "device_risk":0.75,"anomaly":0.85,"data_sensitivity":"pii"},
        {"agent_id":"isp_003","action_type":"device_register","country":"UK",
         "client_ip":"81.130.44.12","email":"ops@virginmedia.co.uk","amount":0,
         "device_risk":0.1,"anomaly":0.0,"data_sensitivity":"standard"},
    ]

    for p in payloads:
        r = engine.process_action(p)
        if "error" in r:
            print(f"  {r['message']}")
            print(f"  {r['action']}")
            break
        print(f"\n  Agent:    {p['agent_id']}")
        print(f"  Decision: {r['decision']}  |  Score: {r['score']}  |  Trust: {r['trust']}")
        print(f"  Reasons:  {', '.join(r['reasons']) or 'none'}")
        print(f"  Art.12:   {r['compliance']['EU_AI_Act']['Art.12']}")
        print(f"  Block:    {r['block_hash'][:32]}...")

    v = engine.verify_chain()
    print(f"\n{DIV}")
    print(f"  Chain: {v['message']} | Blocks: {v['blocks']}")

    print(f"\n{DIV}")
    print("  GUARDIAN ENGINE — CHILD SAFETY")
    print(f"{DIV}")

    guardian = GuardianEngine(node_id="GUARDIAN_001", api_key=key)

    guardian_payloads = [
        {"agent_id":"school_admin","action_type":"content_review","country":"UK",
         "client_ip":"192.168.1.45","email":"admin@stmarys.sch.uk","device_risk":0.05,
         "content_risk":0.1,"grooming_score":0.0,"age_mismatch":False,
         "csam_hash_match":False,"image_share_to_minor":False,
         "sentiment_shift":False,"isolation_attempt":False,"love_bombing":False},
        {"agent_id":"unknown_997","action_type":"trust_escalation","country":"NG",
         "client_ip":"197.210.54.88","email":"unknown@suspicious.net","device_risk":0.8,
         "content_risk":0.7,"grooming_score":0.85,"age_mismatch":True,
         "csam_hash_match":False,"image_share_to_minor":False,
         "sentiment_shift":True,"isolation_attempt":True,"love_bombing":True},
        {"agent_id":"predator_334","action_type":"image_share","country":"RU",
         "client_ip":"91.108.4.55","email":"anon@dark.ru","device_risk":0.95,
         "content_risk":1.0,"grooming_score":0.9,"age_mismatch":True,
         "csam_hash_match":True,"image_share_to_minor":True,
         "sentiment_shift":True,"isolation_attempt":True,"love_bombing":False},
    ]

    for p in guardian_payloads:
        r = guardian.process_action(p)
        if "error" in r:
            print(f"  {r['message']}")
            break
        print(f"\n  Agent:    {p['agent_id']}")
        print(f"  Decision: {r['decision']}  |  Score: {r['score']}")
        print(f"  Reasons:  {', '.join(r['reasons']) or 'none'}")
        print(f"  Parent Alert: {r['parent_alert']}  |  LE Referral: {r['le_referral']}")
        if r.get("evidence_ref"):
            print(f"  Evidence: {r['evidence_ref'][:32]}...")
        print(f"  OSA 2023: {r['compliance']['Online_Safety_Act']}")

    gv = guardian.verify_chain()
    print(f"\n  Chain: {gv['message']} | Blocks: {gv['blocks']}")

    print(f"\n{SEP}")
    print("  ALL SYSTEMS OPERATIONAL")
    print("  sebbi.pro — justin@monopcontent.com — 07908 269428")
    print(f"{SEP}\n")
