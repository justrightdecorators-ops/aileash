import logging
from typing import Dict, Any

# Configure security log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WitnessGuard")

# Revoked Node IDs / Keys
REVOKED_WITNESSES: set[str] = {
    "wit:red-flag-ai-pro",
}

# Whitelist of trusted active witness nodes
ALLOWED_WITNESSES: set[str] = {
    # Add active trusted node IDs here
}

def validate_witness_seal_request(payload: Dict[str, Any]) -> bool:
    """
    Validates whether incoming witness seal requests are from an active, authorized node.
    Rejects and logs revoked IDs instantly.
    """
    user_id = payload.get("user")
    seal = payload.get("seal")
    prev_hash = payload.get("prev")

    if not user_id:
        logger.warning("Rejected seal request: Missing node identifier.")
        return False

    # Hard Reject for Revoked / Blocked Node
    if user_id in REVOKED_WITNESSES:
        logger.error(
            f"BLOCKED: Revoked node '{user_id}' attempted block seal! "
            f"Seal Hash: {str(seal)[:10]}... | Prev Hash: {str(prev_hash)[:10]}..."
        )
        return False

    # Strict Whitelist Verification
    if ALLOWED_WITNESSES and user_id not in ALLOWED_WITNESSES:
        logger.warning(f"UNAUTHORIZED: Node '{user_id}' is not in the active whitelist.")
        return False

    return True


# Route Middleware Handler
def handle_incoming_block(payload: Dict[str, Any]):
    if not validate_witness_seal_request(payload):
        return {
            "status": "error",
            "code": 401,
            "message": "Unauthorized Witness Node. Access Revoked."
        }, 401

    # Append Block to Chain State
    return {
        "status": "success",
        "code": 200,
        "message": "Block Witness Sealed Successfully"
    }, 200


# Execution Test
if __name__ == "__main__":
    test_payload = {
        "user": "wit:red-flag-ai-pro",
        "score": 0,
        "seal": "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b",
        "prev": "58eb2ea09de10b57dcbd13bcda220fb47ed62f53"
    }

    response, status_code = handle_incoming_block(test_payload)
    print(f"\nExecution Result: Status {status_code} -> {response}")
