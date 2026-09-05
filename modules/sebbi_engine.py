# modules/sebbi_engine.py
"""
AILeash module for /x/sebbi_engine/verify

Exposes `handle(method, action, data, api_key, ctx)` as required by
modules/router.py. This file is deliberately minimal and public for GET /verify
so it can be machine-checked without an API key. No state is modified.

This variant adds lightweight import-time logging so import failures or
configuration values are visible in server logs. It remains non-invasive and
does not modify server.py or any DB/state.
"""

import os
import hashlib
import time

MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")
DEFAULT_SEAL_PHRASE = "APEX_ENGINE_SEAL"
DEFAULT_TOKEN_BUDGET = 66000

# Allow GET /verify without an API key
PUBLIC = {("GET", "verify")}

# Import-time log for easier debugging on the running host. This is intentionally
# tiny and safe: it only prints a short status line to stdout so the server log
# shows the module loaded and the configured token budget / seal phrase length.
try:
    _seal_preview = os.environ.get("SEAL_PHRASE", DEFAULT_SEAL_PHRASE)
    print(
        f"modules.sebbi_engine: loaded (MODULE_NAME={MODULE_NAME}, TOKEN_BUDGET={os.environ.get('TOKEN_BUDGET',str(DEFAULT_TOKEN_BUDGET))}, SEAL_PREVIEW={_seal_preview[:8]}...),"
        flush=True,
    )
except Exception as _e:
    try:
        print("modules.sebbi_engine: loaded (logging failed): " + str(_e), flush=True)
    except Exception:
        pass


def handle(method, action, data, api_key, ctx):
    """Handle module routes. Called from modules/router.route().

    Args:
        method: HTTP method string (e.g., 'GET')
        action: action part of the path (e.g., 'verify' for /x/sebbi_engine/verify)
        data: parsed query/body
        api_key: provided API key or None
        ctx: context dict with 'conn','lock','seal', etc. (unused)

    Returns:
        (payload_dict, http_status_int)
    """
    # Only support GET /verify for now
    if action != "verify":
        return {"error": "not_found"}, 404

    if method != "GET":
        return {"error": "method_not_allowed"}, 405

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
        # include a machine-friendly checked timestamp
        "checked_at": int(time.time()),
    }
    return payload, 200
