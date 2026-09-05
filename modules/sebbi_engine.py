# modules/sebbi_engine.py
"""
Minimal, non-invasive module for AILeash.

Provides a route(handler, path, qs_or_data) function so the existing server
(which forwards /x/* to modules.router) will call this code for
/x/sebbi_engine/verify. This file is intentionally tiny and has no side
effects other than returning a JSON payload.

Environment variables:
- SEAL_PHRASE (default: "APEX_ENGINE_SEAL")
- TOKEN_BUDGET (default: 66000)
- MODULE_NAME (default: "sebbi_engine")

Return: (payload_dict, http_status_int)
"""

import os
import hashlib
import time

MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")
DEFAULT_SEAL_PHRASE = "APEX_ENGINE_SEAL"
DEFAULT_TOKEN_BUDGET = 66000


def route(handler, path, qs_or_data):
    """Handle /x/sebbi_engine/verify requests.

    The server calls modules.router.route(self, path, qs) or with data for POSTs.
    We accept either and return (payload, status_code). Do not alter any state.
    """
    # Normalize the expected path
    if path != "/x/sebbi_engine/verify":
        return {"error": "not_found"}, 404

    seal_phrase = os.environ.get("SEAL_PHRASE", DEFAULT_SEAL_PHRASE).encode("utf-8")
    try:
        token_budget = int(os.environ.get("TOKEN_BUDGET", str(DEFAULT_TOKEN_BUDGET)))
    except Exception:
        token_budget = DEFAULT_TOKEN_BUDGET

    digest = hashlib.sha256(seal_phrase).hexdigest()
    payload = {
        "module": MODULE_NAME,
        "status": "sealed",
        "token_budget": token_budget,
        "state_validation": digest,
        "checked_at": int(time.time()),
    }
    return payload, 200
