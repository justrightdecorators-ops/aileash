# ============================================================
# AILEASH EXECUTION GATE (STRIPE-STYLE FRONT DOOR)
# THIS IS THE ONLY PUBLIC ENTRY POINT
# ============================================================

import time
import json
import hashlib
from server import BrainGovernor, execute_server_logic, _conn

brain = BrainGovernor()


def handle_request(request: dict):
    ts = time.time()

    api_key = request.get("api_key")
    instruction = request.get("instruction")

    if not api_key:
        return {"status": "BLOCKED", "reason": "missing_api_key"}

    if not instruction:
        return {"status": "BLOCKED", "reason": "missing_instruction"}

    # 1. COMPLIANCE DECISION
    decision = brain.evaluate(instruction)

    # 2. ENFORCEMENT
    if decision["decision"] == "BLOCK":
        audit(api_key, instruction, decision, ts, None)
        return {"status": "BLOCKED", "reason": decision["reason"]}

    # 3. EXECUTE CORE SYSTEM (server.py)
    result = execute_server_logic(request)

    # 4. AUDIT ALWAYS
    audit(api_key, instruction, decision, ts, result)

    return {
        "status": "ALLOWED",
        "result": result,
        "decision": decision
    }


def audit(api_key, instruction, decision, ts, result):
    payload = json.dumps({
        "api_key": api_key,
        "instruction": instruction,
        "decision": decision,
        "ts": ts,
        "result": result
    }, sort_keys=True)

    h = hashlib.sha256(payload.encode()).hexdigest()

    _conn.execute(
        "INSERT INTO audit_log(ts, user_id, event_json, result_json, audit_hash) VALUES (?,?,?,?,?)",
        (ts, api_key, instruction, json.dumps(decision), h)
    )
    _conn.commit()
