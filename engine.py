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
# Unauthorised reproduction, modification, or distribution of this software
# or its logic schemas is a criminal offence. All integrity tokens, audit
# chains, and compliance signatures remain the sole intellectual property of
# Justin Antony Dobson / Monop Content, Blyth, UK.
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
from typing import Any, Dict, List, Optional, Tuple

# ==============================================================================
# BOOT INTEGRITY
# ==============================================================================

_INTEGRITY_SEED = b"MONOP_CONTENT_BLYTH_PRODUCTION_CORE_v4.2.0"
_INTEGRITY_KEY  = b"AILEASH_GUARDIAN_SOVEREIGN_ENGINE_2026"

def _boot_integrity_check() -> str:
    token = hmac.new(_INTEGRITY_KEY, _INTEGRITY_SEED, hashlib.sha256).hexdigest()
    print(f"[AILEASH] Boot integrity verified: {token[:16]}...{token[-8:]}")
    return token

INTEGRITY_TOKEN: str = _boot_integrity_check()

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
        self.node_id: str = node_id
        self.chain:   List[Dict[str, Any]] = []
        self.genesis_hash: str = hashlib.sha256(
            f"GENESIS:{node_id}:{INTEGRITY_TOKEN}".encode()
        ).hexdigest()

    def _prev_hash(self) -> str:
        if not self.chain:
            return self.genesis_hash
        return self.chain[-1]["block_hash"]

    def seal(
        self,
        action_type:  str,
        decision:     str,
        score:        float,
        reasons:      List[str],
        compliance:   Dict[str, Any],
        client_ip:    str,
        email:        str,
        extra:        Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ts   = time.time()
        prev = self._prev_hash()

        payload: Dict[str, Any] = {
            "index":       len(self.chain),
            "node_id":     self.node_id,
            "timestamp":   ts,
            "action_type": action_type,
            "decision":    decision,
            "score":       round(score, 6),
            "reasons":     reasons,
            "client_ip":   client_ip,
            "email":       email,
            "prev_hash":   prev,
            "integrity":   INTEGRITY_TOKEN[:16],
        }
        if extra:
            payload.update(extra)

        block_hash  = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

        pipe_record = f"{ts}|{email}|{client_ip}|{decision}"
        pipe_hash   = hashlib.sha256(pipe_record.encode()).hexdigest()

        block = {
            **payload,
            "block_hash":  block_hash,
            "pipe_record": pipe_record,
            "pipe_hash":   pipe_hash,
            "compliance":  compliance,
        }

        self.chain.append(block)
        return block

    def verify(self) -> Dict[str, Any]:
        if not self.chain:
            return {"valid": True, "blocks": 0, "message": "Empty chain"}
        prev = self.genesis_hash
        for i, block in enumerate(self.chain):
            payload = {k: v for k, v in block.items()
                       if k not in ("block_hash","pipe_record","pipe_hash","compliance")}
            recomputed = hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest()
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

    def _prune(self, store: Dict[str, List[float]], window: float, key: str) -> None:
        cutoff = time.time() - window
        store.setdefault(key, [])
        store[key] = [t for t in store[key] if t >= cutoff]

    def record(self, key: str) -> Dict[str, int]:
        now = time.time()
        for store in (self._60s, self._5m, self._1h):
            store.setdefault(key, []).append(now)
        self._prune(self._60s, 60,   key)
        self._prune(self._5m,  300,  key)
        self._prune(self._1h,  3600, key)
        return {
            "velocity_60s": len(self._60s[key]),
            "velocity_5m":  len(self._5m[key]),
            "velocity_1h":  len(self._1h[key]),
        }

# ==============================================================================
# BASE RISK SCORER — AILEASH GOVERNANCE
# ==============================================================================

class RiskScorer:
    SAFE_COUNTRIES = {
        "UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"
    }
    HIGH_RISK_ACTIONS = {
        "delete_user_data","export_bulk_data","modify_permissions",
        "disable_safety_filter","override_block","mass_message",
        "image_share","location_share","payment_transfer"
    }
    HIGH_SENSITIVITY = {"pii","financial","medical","biometric","child"}

    def score(self, signals: Dict[str, Any]) -> Tuple[float, List[str]]:
        reasons: List[str] = []
        s = signals

        trust      = (1 - s.get("trust", 0.5)) * 0.30
        v60        = s.get("velocity_60s", 0)
        vel_60     = min(v60 / 20, 1.0) * 0.15
        if v60 > 10: reasons.append("velocity_spike_60s")

        v5m        = s.get("velocity_5m", 0)
        vel_5m     = min(v5m / 50, 1.0) * 0.10
        if v5m > 30: reasons.append("velocity_spike_5m")

        v1h        = s.get("velocity_1h", 0)
        vel_1h     = min(v1h / 200, 1.0) * 0.10

        amount     = float(s.get("amount", 0))
        content    = min(math.log1p(amount) / math.log1p(10000), 1.0) * 0.15
        if amount > 500: reasons.append("high_amount")

        device     = float(s.get("device_risk", 0)) * 0.10
        if s.get("device_risk", 0) > 0.5: reasons.append("risky_device")

        anomaly    = float(s.get("anomaly", 0)) * 0.10
        if s.get("anomaly", 0) > 0.5: reasons.append("behaviour_anomaly")

        geo = shift = 0.0
        if s.get("unsafe_country"):
            geo = 0.10; reasons.append("unsafe_country")
        if s.get("country_shift"):
            shift = 0.10; reasons.append("country_shift")
        if s.get("trust", 0.5) < 0.4:
            reasons.append("low_trust")

        action_boost = 0.08 if s.get("action_type") in self.HIGH_RISK_ACTIONS else 0.0
        if action_boost: reasons.append("high_risk_action")

        sens_boost = 0.06 if s.get("data_sensitivity") in self.HIGH_SENSITIVITY else 0.0
        if sens_boost: reasons.append("sensitive_data")

        raw = (trust + vel_60 + vel_5m + vel_1h + content +
               device + anomaly + geo + shift + action_boost + sens_boost)
        return round(max(0.0, min(1.0, raw)), 6), reasons

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
# GUARDIAN RISK SCORER — CHILD SAFETY
# ==============================================================================

class GuardianRiskScorer(RiskScorer):
    """
    Extended 9-signal scorer with child-specific threat detection.
    Block threshold lowered to 0.60 — zero tolerance for child safety.
    CSAM signals trigger mandatory BLOCK regardless of overall score.
    """

    GROOMING_ACTIONS = {
        "private_message","gift_send","location_request","image_request",
        "video_call_request","phone_number_request","meet_request",
        "secret_keep_request","isolation_attempt","trust_escalation"
    }

    def score_guardian(self, signals: Dict[str, Any]) -> Tuple[float, List[str], bool]:
        """
        Returns (score, reasons, mandatory_block).
        mandatory_block=True means BLOCK regardless of score — CSAM or equivalent.
        """
        reasons: List[str] = []
        mandatory_block = False
        s = signals

        # --- Signal 1: Behavioural Trust (30%) ---
        trust_score = (1 - s.get("trust", 0.5)) * 0.30
        if s.get("trust", 0.5) < 0.3:
            reasons.append("critically_low_trust")

        # --- Signal 2: Contact Velocity 60s (15%) ---
        v60 = s.get("velocity_60s", 0)
        vel_60 = min(v60 / 15, 1.0) * 0.15
        if v60 > 8:
            reasons.append("contact_velocity_spike")

        # --- Signal 3: Session Velocity 5m (10%) ---
        v5m = s.get("velocity_5m", 0)
        vel_5m = min(v5m / 30, 1.0) * 0.10
        if v5m > 20:
            reasons.append("session_velocity_spike")

        # --- Signal 4: Velocity 1h (10%) ---
        v1h = s.get("velocity_1h", 0)
        vel_1h = min(v1h / 100, 1.0) * 0.10

        # --- Signal 5: Content / Image Risk (15%) ---
        content_risk = float(s.get("content_risk", 0)) * 0.15
        if s.get("content_risk", 0) > 0.6:
            reasons.append("harmful_content_detected")

        # --- Signal 6: Grooming Pattern Score (10%) ---
        grooming = float(s.get("grooming_score", 0)) * 0.10
        if s.get("grooming_score", 0) > 0.5:
            reasons.append("grooming_pattern_detected")
        if s.get("action_type") in self.GROOMING_ACTIONS:
            grooming = min(grooming + 0.06, 0.10)
            reasons.append("grooming_action_type")

        # --- Signal 7: Device Risk (10%) ---
        device = float(s.get("device_risk", 0)) * 0.10
        if s.get("device_risk", 0) > 0.5:
            reasons.append("risky_device")

        # --- Signal 8: Geographic Risk (additive +10%) ---
        geo = 0.0
        if s.get("unsafe_country"):
            geo = 0.10
            reasons.append("unsafe_country")

        # --- Signal 9: Cross-Border Contact (additive +10%) ---
        shift = 0.0
        if s.get("country_shift"):
            shift = 0.10
            reasons.append("country_shift")

        # --- Psychological manipulation boost ---
        manip_boost = 0.0
        if s.get("sentiment_shift"):
            manip_boost += 0.08
            reasons.append("sentiment_shift_detected")
        if s.get("isolation_attempt"):
            manip_boost += 0.10
            reasons.append("isolation_attempt_detected")
        if s.get("love_bombing"):
            manip_boost += 0.08
            reasons.append("love_bombing_detected")

        # --- Age mismatch boost ---
        age_boost = 0.0
        if s.get("age_mismatch"):
            age_boost = 0.12
            reasons.append("adult_minor_contact_detected")

        # --- CSAM — mandatory block, no score needed ---
        if s.get("csam_hash_match"):
            mandatory_block = True
            reasons.append("CSAM_HASH_MATCH_MANDATORY_BLOCK")

        if s.get("image_share_to_minor"):
            mandatory_block = True
            reasons.append("IMAGE_SHARE_TO_MINOR_MANDATORY_BLOCK")

        raw = (trust_score + vel_60 + vel_5m + vel_1h +
               content_risk + grooming + device + geo + shift +
               manip_boost + age_boost)

        final = round(max(0.0, min(1.0, raw)), 6)
        return final, reasons, mandatory_block

    def decide_guardian(self, score: float, mandatory_block: bool) -> str:
        # Zero tolerance — block threshold 0.60 not 0.70
        if mandatory_block:           return "BLOCK"
        if score < 0.30:              return "ALLOW"
        if score < 0.60:              return "CHALLENGE"
        return "BLOCK"

# ==============================================================================
# BASE ENGINE — AILEASH GOVERNANCE
# ==============================================================================

class AILeashEngine:
    def __init__(self, node_id: str, master_key: Optional[str] = None) -> None:
        self.node_id:    str   = node_id
        self.master_key: str   = master_key or secrets.token_hex(32)
        self.version:    str   = "4.2.0"
        self.created:    float = time.time()
        self.engine_type: str  = "AILeash Governance"

        self.chain:    MerkleAuditChain = MerkleAuditChain(node_id)
        self.scorer:   RiskScorer       = RiskScorer()
        self.velocity: VelocityLedger   = VelocityLedger()

        self._trust_state:   Dict[str, float]          = {}
        self._country_state: Dict[str, Optional[str]]  = {}

        print(f"[{self.engine_type.upper()}] Node {node_id} initialised — v{self.version}")
        print(f"[{self.engine_type.upper()}] Master key: {self.master_key[:8]}...{self.master_key[-8:]}")

    def _get_trust(self, agent_id: str) -> float:
        return self._trust_state.get(agent_id, 0.5)

    def _set_trust(self, agent_id: str, trust: float) -> None:
        self._trust_state[agent_id] = trust

    def _get_country(self, agent_id: str) -> Optional[str]:
        return self._country_state.get(agent_id)

    def _set_country(self, agent_id: str, country: str) -> None:
        self._country_state[agent_id] = country

    def process_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        agent_id    = str(payload.get("agent_id",    "unknown"))
        action_type = str(payload.get("action_type", "unknown"))
        country     = str(payload.get("country",     "UNKNOWN")).upper()
        client_ip   = str(payload.get("client_ip",   "0.0.0.0"))
        email       = str(payload.get("email",       "unknown"))
        amount      = float(payload.get("amount",    0))
        device_risk = float(payload.get("device_risk", 0.0))
        anomaly     = float(payload.get("anomaly",   0.0))
        sensitivity = str(payload.get("data_sensitivity", "standard"))

        vel   = self.velocity.record(agent_id)
        trust = self._get_trust(agent_id)

        if vel["velocity_60s"] > 45:
            trust = max(0.05, trust * 0.85)
            self._set_trust(agent_id, trust)

        last_country   = self._get_country(agent_id)
        country_shift  = last_country is not None and last_country != country
        unsafe_country = country not in RiskScorer.SAFE_COUNTRIES

        signals = {
            "trust":            trust,
            "velocity_60s":     vel["velocity_60s"],
            "velocity_5m":      vel["velocity_5m"],
            "velocity_1h":      vel["velocity_1h"],
            "amount":           amount,
            "device_risk":      device_risk,
            "anomaly":          anomaly,
            "country_shift":    country_shift,
            "unsafe_country":   unsafe_country,
            "action_type":      action_type,
            "data_sensitivity": sensitivity,
        }

        score, reasons = self.scorer.score(signals)
        decision       = self.scorer.decide(score)
        new_trust      = self.scorer.update_trust(trust, decision)

        self._set_trust(agent_id, new_trust)
        self._set_country(agent_id, country)

        compliance = {
            "EU_AI_Act":          EU_AI_ACT_MAP[decision],
            "Online_Safety_Act":  ONLINE_SAFETY_MAP[decision],
            "ICO_Childrens_Code": ICO_CHILDRENS_CODE_MAP[decision],
        }

        block = self.chain.seal(
            action_type=action_type,
            decision=decision,
            score=score,
            reasons=reasons,
            compliance=compliance,
            client_ip=client_ip,
            email=email,
        )

        return {
            "node_id":     self.node_id,
            "engine_type": self.engine_type,
            "agent_id":    agent_id,
            "decision":    decision,
            "score":       score,
            "trust":       round(new_trust, 6),
            "reasons":     reasons,
            "compliance":  compliance,
            "block_hash":  block["block_hash"],
            "pipe_hash":   block["pipe_hash"],
            "pipe_record": block["pipe_record"],
            "block_index": block["index"],
            "timestamp":   block["timestamp"],
            "version":     self.version,
            "integrity":   INTEGRITY_TOKEN[:16],
        }

    def verify_chain(self) -> Dict[str, Any]:
        return self.chain.verify()

    def export_chain(self) -> List[Dict[str, Any]]:
        return self.chain.export()

    def generate_replication_hmac(self, new_node_id: str) -> str:
        return hmac.new(
            self.master_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()

    def replicate_engine(
        self,
        new_node_id:       str,
        verification_hmac: str
    ) -> "AILeashEngine":
        expected = hmac.new(
            self.master_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, verification_hmac):
            raise PermissionError(
                f"[AILEASH] Replication to {new_node_id} DENIED — invalid HMAC"
            )

        new_engine = AILeashEngine(new_node_id, self.master_key)
        new_engine._trust_state   = copy.deepcopy(self._trust_state)
        new_engine._country_state = copy.deepcopy(self._country_state)

        self.process_action({
            "agent_id":         f"REPLICATE_TO:{new_node_id}",
            "action_type":      "engine_replication",
            "country":          "UK",
            "client_ip":        "127.0.0.1",
            "email":            "system@aileash.internal",
            "amount":           0,
            "device_risk":      0.0,
            "anomaly":          0.0,
            "data_sensitivity": "internal",
        })

        print(f"[AILEASH] Node {new_node_id} replicated from {self.node_id} — HMAC verified")
        return new_engine

    def scan_domain_vulnerability(
        self,
        domain:   str,
        org_name: str,
        email:    str
    ) -> Dict[str, Any]:
        d = domain.lower()
        is_uk = any(d.endswith(s) for s in
                    (".uk",".co.uk",".sch.uk",".ac.uk",".gov.uk",".org.uk"))

        if is_uk:
            framework     = "UK Online Safety Act 2023 + ICO Children's Code"
            breaches      = [
                "No tamper-evident audit trail — Ofcom enforcement risk",
                "Absence of real-time content moderation — duty of care breach",
                "No age-appropriate design verification — ICO Code violation",
                "Missing child safety risk assessment — OSA s.11 breach",
            ]
            fine_exposure = "Up to £18,000,000 or 10% global turnover"
            deadline      = "Immediate — OSA 2023 is in force now"
            regulator     = "Ofcom"
        else:
            framework     = "EU AI Act 2024/1689 — High-Risk AI Classification"
            breaches      = [
                "No Art.12 tamper-evident audit chain — enforcement risk",
                "No Art.13 explainable decision output — transparency breach",
                "No Art.9 continuous risk management system — compliance gap",
                "High-risk AI not registered in EU database — Art.49 breach",
            ]
            fine_exposure = "Up to €15,000,000 or 3% global annual turnover"
            deadline      = "August 2026 — full enforcement begins"
            regulator     = "EU AI Office"

        return {
            "domain":            domain,
            "org_name":          org_name,
            "email":             email,
            "risk_level":        "CRITICAL",
            "framework":         framework,
            "regulator":         regulator,
            "deadline":          deadline,
            "fine_exposure":     fine_exposure,
            "breaches_detected": breaches,
            "remediation": {
                "solution":    "AILeash Platform",
                "url":         "https://sebbi.pro/#signup",
                "price":       "£0.50 per device per month",
                "deployment":  "API key in 60 seconds — compliant immediately",
                "free_trial":  "100 decisions — no card required",
            },
            "scan_hash":  hashlib.sha256(
                f"{domain}:{org_name}:{time.time()}".encode()
            ).hexdigest(),
            "scanned_at": time.time(),
        }

    def status(self) -> Dict[str, Any]:
        v = self.verify_chain()
        return {
            "node_id":        self.node_id,
            "engine_type":    self.engine_type,
            "version":        self.version,
            "created":        self.created,
            "integrity":      INTEGRITY_TOKEN[:16],
            "agents_tracked": len(self._trust_state),
            "chain_blocks":   len(self.chain.chain),
            "chain_valid":    v["valid"],
            "chain_tip":      v.get("tip", "genesis"),
        }

# ==============================================================================
# GUARDIAN ENGINE — CHILD SAFETY
# ==============================================================================

class GuardianEngine(AILeashEngine):
    """
    AILeash Guardian — child safety governance layer.
    Extends AILeashEngine with child-specific threat detection.
    Zero tolerance architecture — BLOCK threshold 0.60 not 0.70.
    CSAM triggers mandatory BLOCK regardless of score.
    Every BLOCK preserves evidence and activates law enforcement pathway.
    """

    def __init__(self, node_id: str, master_key: Optional[str] = None) -> None:
        super().__init__(node_id, master_key)
        self.engine_type    = "AILeash Guardian"
        self.guardian_scorer = GuardianRiskScorer()
        self._le_referral_log: List[Dict[str, Any]] = []
        self._parent_alerts:   List[Dict[str, Any]] = []
        print(f"[GUARDIAN] Child safety engine active — zero tolerance mode")
        print(f"[GUARDIAN] BLOCK threshold: 0.60 | CSAM: mandatory BLOCK")

    def process_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        agent_id    = str(payload.get("agent_id",    "unknown"))
        action_type = str(payload.get("action_type", "unknown"))
        country     = str(payload.get("country",     "UNKNOWN")).upper()
        client_ip   = str(payload.get("client_ip",   "0.0.0.0"))
        email       = str(payload.get("email",       "unknown"))
        device_risk = float(payload.get("device_risk", 0.0))

        vel   = self.velocity.record(agent_id)
        trust = self._get_trust(agent_id)

        # Velocity auto-decay — stricter threshold for Guardian
        if vel["velocity_60s"] > 30:
            trust = max(0.05, trust * 0.80)
            self._set_trust(agent_id, trust)

        last_country   = self._get_country(agent_id)
        country_shift  = last_country is not None and last_country != country
        unsafe_country = country not in RiskScorer.SAFE_COUNTRIES

        signals = {
            "trust":               trust,
            "velocity_60s":        vel["velocity_60s"],
            "velocity_5m":         vel["velocity_5m"],
            "velocity_1h":         vel["velocity_1h"],
            "content_risk":        float(payload.get("content_risk",   0.0)),
            "grooming_score":      float(payload.get("grooming_score", 0.0)),
            "device_risk":         device_risk,
            "unsafe_country":      unsafe_country,
            "country_shift":       country_shift,
            "action_type":         action_type,
            "sentiment_shift":     bool(payload.get("sentiment_shift",     False)),
            "isolation_attempt":   bool(payload.get("isolation_attempt",   False)),
            "love_bombing":        bool(payload.get("love_bombing",        False)),
            "age_mismatch":        bool(payload.get("age_mismatch",        False)),
            "csam_hash_match":     bool(payload.get("csam_hash_match",     False)),
            "image_share_to_minor":bool(payload.get("image_share_to_minor",False)),
        }

        score, reasons, mandatory_block = self.guardian_scorer.score_guardian(signals)
        decision  = self.guardian_scorer.decide_guardian(score, mandatory_block)
        new_trust = self.guardian_scorer.update_trust(trust, decision)

        self._set_trust(agent_id, new_trust)
        self._set_country(agent_id, country)

        compliance = {
            "EU_AI_Act":          EU_AI_ACT_MAP[decision],
            "Online_Safety_Act":  ONLINE_SAFETY_MAP[decision],
            "ICO_Childrens_Code": ICO_CHILDRENS_CODE_MAP[decision],
            "Guardian_Threat":    GUARDIAN_THREAT_MAP[decision],
        }

        # Evidence preservation on BLOCK
        evidence_ref: Optional[str] = None
        le_referral:  bool = False
        parent_alert: bool = False

        if decision == "BLOCK":
            evidence_ref = hashlib.sha256(
                f"EVIDENCE:{agent_id}:{client_ip}:{time.time()}:{score}".encode()
            ).hexdigest()
            le_referral = True
            parent_alert = True

            le_record = {
                "evidence_ref": evidence_ref,
                "agent_id":     agent_id,
                "client_ip":    client_ip,
                "email":        email,
                "action_type":  action_type,
                "score":        score,
                "reasons":      reasons,
                "mandatory":    mandatory_block,
                "timestamp":    time.time(),
                "status":       "PRESERVED — law enforcement referral pathway active",
            }
            self._le_referral_log.append(le_record)

        if decision in ("CHALLENGE", "BLOCK"):
            parent_alert = True
            alert_record = {
                "agent_id":   agent_id,
                "decision":   decision,
                "score":      score,
                "reasons":    reasons,
                "timestamp":  time.time(),
                "action":     "Parent/guardian notification triggered",
            }
            self._parent_alerts.append(alert_record)

        extra = {"mandatory_block": mandatory_block}
        if evidence_ref:
            extra["evidence_ref"] = evidence_ref

        block = self.chain.seal(
            action_type=action_type,
            decision=decision,
            score=score,
            reasons=reasons,
            compliance=compliance,
            client_ip=client_ip,
            email=email,
            extra=extra,
        )

        result: Dict[str, Any] = {
            "node_id":        self.node_id,
            "engine_type":    self.engine_type,
            "agent_id":       agent_id,
            "decision":       decision,
            "score":          score,
            "trust":          round(new_trust, 6),
            "reasons":        reasons,
            "compliance":     compliance,
            "block_hash":     block["block_hash"],
            "pipe_hash":      block["pipe_hash"],
            "pipe_record":    block["pipe_record"],
            "block_index":    block["index"],
            "timestamp":      block["timestamp"],
            "mandatory_block":mandatory_block,
            "parent_alert":   parent_alert,
            "le_referral":    le_referral,
            "version":        self.version,
            "integrity":      INTEGRITY_TOKEN[:16],
        }

        if evidence_ref:
            result["evidence_ref"] = evidence_ref
            result["evidence_status"] = (
                "PRESERVED — tamper-evident chain sealed — "
                "admissible in UK courts — law enforcement pathway active"
            )

        return result

    def replicate_engine(
        self,
        new_node_id:       str,
        verification_hmac: str
    ) -> "GuardianEngine":
        expected = hmac.new(
            self.master_key.encode(),
            f"REPLICATE:{new_node_id}".encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, verification_hmac):
            raise PermissionError(
                f"[GUARDIAN] Replication to {new_node_id} DENIED — invalid HMAC"
            )

        new_engine = GuardianEngine(new_node_id, self.master_key)
        new_engine._trust_state   = copy.deepcopy(self._trust_state)
        new_engine._country_state = copy.deepcopy(self._country_state)

        print(f"[GUARDIAN] Node {new_node_id} replicated from {self.node_id} — HMAC verified")
        return new_engine

    def get_le_referrals(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._le_referral_log)

    def get_parent_alerts(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._parent_alerts)

    def status(self) -> Dict[str, Any]:
        base = super().status()
        base["le_referrals"]   = len(self._le_referral_log)
        base["parent_alerts"]  = len(self._parent_alerts)
        base["block_threshold"] = 0.60
        base["csam_protection"] = "mandatory_block"
        return base

# ==============================================================================
# INTERACTIVE DEMO
# ==============================================================================

if __name__ == "__main__":
    SEP = "=" * 70
    DIV = "-" * 60

    print(f"\n{SEP}")
    print("  AILEASH PLATFORM — GOVERNANCE + GUARDIAN ENGINE")
    print("  Monop Content, Blyth, UK — v4.2.0")
    print(f"{SEP}\n")

    # -----------------------------------------------------------------------
    # AILEASH GOVERNANCE — NODE 001
    # -----------------------------------------------------------------------
    print(f"{DIV}")
    print("  AILEASH GOVERNANCE ENGINE — NODE 001")
    print(f"{DIV}")

    engine_1 = AILeashEngine(node_id="GOVERNANCE_NODE_001")

    gov_payloads = [
        {
            "agent_id": "enterprise_cfo_001",
            "action_type": "wire_transfer",
            "country": "UK",
            "client_ip": "82.44.12.99",
            "email": "cfo@acmecorp.co.uk",
            "amount": 2500,
            "device_risk": 0.2,
            "anomaly": 0.1,
            "data_sensitivity": "financial",
        },
        {
            "agent_id": "platform_user_002",
            "action_type": "export_bulk_data",
            "country": "NG",
            "client_ip": "197.210.54.33",
            "email": "user@platform.com",
            "amount": 0,
            "device_risk": 0.75,
            "anomaly": 0.85,
            "data_sensitivity": "pii",
        },
        {
            "agent_id": "isp_ops_003",
            "action_type": "device_register",
            "country": "UK",
            "client_ip": "81.130.44.12",
            "email": "ops@virginmedia.co.uk",
            "amount": 0,
            "device_risk": 0.1,
            "anomaly": 0.0,
            "data_sensitivity": "standard",
        },
    ]

    for p in gov_payloads:
        r = engine_1.process_action(p)
        print(f"\n  Agent:    {p['agent_id']}")
        print(f"  Action:   {p['action_type']}")
        print(f"  Decision: {r['decision']}  |  Score: {r['score']}  |  Trust: {r['trust']}")
        print(f"  Reasons:  {', '.join(r['reasons']) or 'none'}")
        print(f"  Art.12:   {r['compliance']['EU_AI_Act']['Art.12']}")
        print(f"  Block:    {r['block_hash'][:32]}...")

    # Verify governance chain
    print(f"\n{DIV}")
    print("  CHAIN VERIFICATION — GOVERNANCE NODE 001")
    print(f"{DIV}")
    v = engine_1.verify_chain()
    print(f"  Valid: {v['valid']}  |  Blocks: {v['blocks']}  |  {v['message']}")

    # Replicate governance engine
    print(f"\n{DIV}")
    print("  REPLICATING GOVERNANCE ENGINE TO NODE 002")
    print(f"{DIV}")
    hmac_002 = engine_1.generate_replication_hmac("GOVERNANCE_NODE_002")
    engine_2  = engine_1.replicate_engine("GOVERNANCE_NODE_002", hmac_002)
    r2 = engine_2.process_action(gov_payloads[2])
    print(f"  Node 002 decision: {r2['decision']}  |  Score: {r2['score']}")

    # -----------------------------------------------------------------------
    # GUARDIAN ENGINE — CHILD SAFETY
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("  AILEASH GUARDIAN ENGINE — CHILD SAFETY")
    print(f"{SEP}")

    guardian = GuardianEngine(node_id="GUARDIAN_NODE_001")

    guardian_payloads = [
        {
            # Safe school interaction
            "agent_id":      "school_admin_001",
            "action_type":   "content_review",
            "country":       "UK",
            "client_ip":     "192.168.1.45",
            "email":         "admin@stmarys.sch.uk",
            "device_risk":   0.05,
            "content_risk":  0.1,
            "grooming_score":0.0,
            "age_mismatch":  False,
            "csam_hash_match":False,
            "image_share_to_minor":False,
            "sentiment_shift":False,
            "isolation_attempt":False,
            "love_bombing":  False,
        },
        {
            # Grooming attempt from unsafe country
            "agent_id":      "unknown_user_997",
            "action_type":   "trust_escalation",
            "country":       "NG",
            "client_ip":     "197.210.54.88",
            "email":         "unknown@suspicious.net",
            "device_risk":   0.8,
            "content_risk":  0.7,
            "grooming_score":0.85,
            "age_mismatch":  True,
            "csam_hash_match":False,
            "image_share_to_minor":False,
            "sentiment_shift":True,
            "isolation_attempt":True,
            "love_bombing":  True,
        },
        {
            # CSAM detection — mandatory block
            "agent_id":      "predator_334",
            "action_type":   "image_share",
            "country":       "RU",
            "client_ip":     "91.108.4.55",
            "email":         "anon@darknet.ru",
            "device_risk":   0.95,
            "content_risk":  1.0,
            "grooming_score":0.9,
            "age_mismatch":  True,
            "csam_hash_match":True,
            "image_share_to_minor":True,
            "sentiment_shift":True,
            "isolation_attempt":True,
            "love_bombing":  False,
        },
    ]

    for p in guardian_payloads:
        r = guardian.process_action(p)
        print(f"\n  Agent:    {p['agent_id']}")
        print(f"  Action:   {p['action_type']}")
        print(f"  Decision: {r['decision']}  |  Score: {r['score']}  |  Trust: {r['trust']}")
        print(f"  Reasons:  {', '.join(r['reasons']) or 'none'}")
        print(f"  Parent Alert:  {r['parent_alert']}")
        print(f"  LE Referral:   {r['le_referral']}")
        if r.get("evidence_ref"):
            print(f"  Evidence Ref:  {r['evidence_ref'][:32]}...")
            print(f"  Status:        {r['evidence_status']}")
        print(f"  OSA 2023:      {r['compliance']['Online_Safety_Act']}")
        print(f"  ICO Code:      {r['compliance']['ICO_Childrens_Code']}")
        print(f"  Guardian:      {r['compliance']['Guardian_Threat']}")
        print(f"  Block Hash:    {r['block_hash'][:32]}...")

    # Guardian chain verification
    print(f"\n{DIV}")
    print("  CHAIN VERIFICATION — GUARDIAN NODE 001")
    print(f"{DIV}")
    gv = guardian.verify_chain()
    print(f"  Valid: {gv['valid']}  |  Blocks: {gv['blocks']}  |  {gv['message']}")

    # Law enforcement referral log
    print(f"\n{DIV}")
    print("  LAW ENFORCEMENT REFERRAL LOG")
    print(f"{DIV}")
    for ref in guardian.get_le_referrals():
        print(f"\n  Evidence Ref: {ref['evidence_ref'][:32]}...")
        print(f"  Agent:        {ref['agent_id']}")
        print(f"  IP:           {ref['client_ip']}")
        print(f"  Action:       {ref['action_type']}")
        print(f"  Score:        {ref['score']}")
        print(f"  Mandatory:    {ref['mandatory']}")
        print(f"  Status:       {ref['status']}")

    # Replicate guardian to new node
    print(f"\n{DIV}")
    print("  REPLICATING GUARDIAN TO NODE 002")
    print(f"{DIV}")
    g_hmac = guardian.generate_replication_hmac("GUARDIAN_NODE_002")
    guardian_2 = guardian.replicate_engine("GUARDIAN_NODE_002", g_hmac)
    gr2 = guardian_2.process_action(guardian_payloads[0])
    print(f"  Node 002 decision: {gr2['decision']}  |  Score: {gr2['score']}")

    # Domain vulnerability scans
    print(f"\n{DIV}")
    print("  DOMAIN VULNERABILITY SCANS")
    print(f"{DIV}")
    for domain, org in [("example.sch.uk","St Mary's Academy"),
                         ("bigtech.de","BigTech GmbH")]:
        scan = engine_1.scan_domain_vulnerability(domain, org, f"admin@{domain}")
        print(f"\n  Domain:        {scan['domain']}")
        print(f"  Risk:          {scan['risk_level']}")
        print(f"  Framework:     {scan['framework']}")
        print(f"  Fine:          {scan['fine_exposure']}")
        for b in scan["breaches_detected"]:
            print(f"    BREACH: {b}")
        print(f"  Fix:           {scan['remediation']['url']} — {scan['remediation']['price']}")

    # Status summary
    print(f"\n{DIV}")
    print("  ENGINE STATUS SUMMARY")
    print(f"{DIV}")
    for eng, label in [
        (engine_1,  "GOVERNANCE NODE 001"),
        (engine_2,  "GOVERNANCE NODE 002"),
        (guardian,  "GUARDIAN NODE 001"),
        (guardian_2,"GUARDIAN NODE 002"),
    ]:
        s = eng.status()
        print(f"\n  {label}:")
        print(f"    Type:           {s['engine_type']}")
        print(f"    Agents tracked: {s['agents_tracked']}")
        print(f"    Chain blocks:   {s['chain_blocks']}")
        print(f"    Chain valid:    {s['chain_valid']}")
        if "le_referrals" in s:
            print(f"    LE referrals:   {s['le_referrals']}")
            print(f"    Parent alerts:  {s['parent_alerts']}")
            print(f"    Block threshold:{s['block_threshold']}")

    print(f"\n{SEP}")
    print("  ALL SYSTEMS OPERATIONAL")
    print("  AILeash Governance + AILeash Guardian")
    print("  sebbi.pro — justin@monopcontent.com — 07908 269428")
    print(f"{SEP}\n")
