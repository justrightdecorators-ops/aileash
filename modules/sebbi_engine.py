# modules/sebbi_engine.py
"""
Compatibility module for /x/sebbi_engine/verify

Exports a single `handle(...)` that accepts two common calling styles so it
works with the router (handle(method, action, data, api_key, ctx) -> (payload, status))
and with older code that calls handle(handler, path, query_params=None) and
expects the module to write the HTTP response directly.

This file is intentionally defensive and import-safe so it won't crash the
server on import. It is a single-file change and does not modify server.py.
"""

import os
import hashlib
import time
import json

MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")
DEFAULT_SEAL_PHRASE = "APEX_ENGINE_SEAL"
DEFAULT_TOKEN_BUDGET = 66000

# Allow GET /verify without an API key
PUBLIC = {("GET", "verify")}

# Import-time log (defensive)
try:
    _seal_preview = os.environ.get("SEAL_PHRASE", DEFAULT_SEAL_PHRASE)
    print(
        f"modules.sebbi_engine: loaded (MODULE_NAME={MODULE_NAME}, TOKEN_BUDGET={os.environ.get('TOKEN_BUDGET',str(DEFAULT_TOKEN_BUDGET))}, SEAL_PREVIEW={_seal_preview[:8]}...)",
        flush=True,
    )
except Exception:
    pass


def _build_payload():
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
    return payload


def handle(*args, **kwargs):
    """Dual-signature handler.

    Two supported call patterns:
    1) Router-style (modules/router.py):
         handle(method, action, data, api_key, ctx) -> (payload_dict, status_int)
    2) Legacy handler-style some code used earlier:
         handle(handler, path, query_params=None) -> writes HTTP response directly and returns True

    The function autodetects which style is being used by inspecting the first
    argument.
    """
    # Legacy style: first arg looks like BaseHTTPRequestHandler (has send_response)
    if args and hasattr(args[0], "send_response") and hasattr(args[0], "wfile"):
        handler = args[0]
        path = args[1] if len(args) > 1 else ""
        # query_params may be provided as third arg, but we don't need it here
        payload = _build_payload()
        body = json.dumps(payload, indent=2).encode("utf-8")
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            # Don't raise during a direct handler write; best-effort only.
            try:
                # fallback: attempt to write minimal text
                handler.send_response(500)
                handler.send_header("Content-Type", "text/plain")
                handler.end_headers()
                handler.wfile.write(b"sebbi_engine: response failed\n")
            except Exception:
                pass
        return True

    # Router-style
    # Expected: method, action, data, api_key, ctx
    method = args[0] if len(args) > 0 else kwargs.get("method")
    action = args[1] if len(args) > 1 else kwargs.get("action", "")
    # keep compatibility: sometimes action can be full path like '/x/sebbi_engine/verify'
    if isinstance(action, str) and action.startswith("/"):
        parts = [x for x in action.strip("/").split("/") if x]
        if len(parts) >= 3 and parts[1] == "sebbi_engine":
            # /x/sebbi_engine/verify -> action is 'verify'
            action = parts[2]
        elif len(parts) >= 2 and parts[0] == "x" and parts[1] == "sebbi_engine":
            action = parts[2] if len(parts) > 2 else ""

    if action != "verify":
        return {"error": "not_found"}, 404
    if method != "GET":
        return {"error": "method_not_allowed"}, 405

    payload = _build_payload()
    return payload, 200
