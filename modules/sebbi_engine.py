# modules/sebbi_engine.py
"""
Public engine-state endpoint for /x/sebbi_engine/verify

Returns the LIVE state of the audit chain — the real current tip and height —
read at request time. It never returns a hardcoded or constant value dressed up
as verification: if the live chain cannot be read, it says so plainly rather
than reporting a reassuring "sealed" status it cannot stand behind.

Dual-signature handle(...) so it works with the router
    handle(method, action, data, api_key, ctx) -> (payload, status)
and with older direct-write callers
    handle(handler, path, query_params=None) -> writes the response, returns True

Import-safe: nothing here can crash the server on import.
"""

import os
import json
import time
import hashlib

MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")
DEFAULT_TOKEN_BUDGET = 66000

# GET /verify is public — no API key required, by design. The whole point is
# that anyone can inspect live state without permission.
PUBLIC = {("GET", "verify")}

try:
    print("modules.sebbi_engine: loaded (live-state mode)", flush=True)
except Exception:
    pass


def _token_budget():
    try:
        return int(os.environ.get("TOKEN_BUDGET", str(DEFAULT_TOKEN_BUDGET)))
    except Exception:
        return DEFAULT_TOKEN_BUDGET


def _read_live_chain(ctx):
    """
    Read the real current chain tip and height from the live database via ctx.

    Returns a dict describing what was actually found, or a dict recording that
    live state could not be read. It NEVER invents a value.

    Tries a few common column/table shapes defensively, because the point is to
    report the truth, not to guess prettily.
    """
    if not isinstance(ctx, dict):
        return {"live": False, "reason": "no_context"}

    conn = ctx.get("conn") or ctx.get("db") or ctx.get("connection")
    lock = ctx.get("lock")
    if conn is None:
        return {"live": False, "reason": "no_db_handle"}

    # Candidate queries for "the latest sealed block". Ordered from most to
    # least specific; the first that works wins. Adjust table/column names here
    # if your schema differs — every branch reads REAL rows, none fabricate.
    candidates = [
        # Real schema, matched to modules/witness.py _our_tip(): the chain
        # lives in audit_log, sealed hash is audit_hash, height is id.
        "SELECT audit_hash AS seal, id AS height FROM audit_log ORDER BY id DESC LIMIT 1",
    ]

    def _run():
        for q in candidates:
            try:
                row = conn.execute(q).fetchone()
            except Exception:
                continue
            if not row:
                continue
            try:
                seal = row[0]
                height = row[1]
            except Exception:
                continue
            if seal is None:
                continue
            return {
                "live": True,
                "tip": str(seal),
                "height": int(height) if height is not None else None,
            }
        return None

    try:
        if lock is not None:
            with lock:
                result = _run()
        else:
            result = _run()
    except Exception as e:  # noqa: BLE001
        return {"live": False, "reason": "read_error:" + e.__class__.__name__}

    if result is None:
        # DB is reachable but no chain rows were found under any known shape.
        return {"live": False, "reason": "no_chain_rows"}
    return result


def _build_payload(ctx):
    """
    The real state manifest. Reports live chain state, and is honest when it
    can't reach it.
    """
    now = int(time.time())
    chain = _read_live_chain(ctx)

    payload = {
        "module": MODULE_NAME,
        "token_budget": _token_budget(),
        "checked_at": now,
        "verify_the_chain_yourself": "https://sebbi.pro/x/witness/tip",
    }

    if chain.get("live"):
        payload["status"] = "sealed"
        payload["chain_tip"] = chain["tip"]
        payload["chain_height"] = chain["height"]
        # A convenience digest OF THE REAL TIP, clearly labelled as derived from
        # live state — not a constant standing in for verification.
        payload["tip_digest"] = hashlib.sha256(
            chain["tip"].encode("utf-8")
        ).hexdigest()
        payload["note"] = (
            "Live chain state, read at request time. This changes as the chain "
            "grows. Verify independently at the link above."
        )
    else:
        # HONEST failure. Never report 'sealed' when we can't see the chain.
        payload["status"] = "live_state_unavailable"
        payload["reason"] = chain.get("reason", "unknown")
        payload["note"] = (
            "The live chain could not be read for this request, so no sealed "
            "state is reported. This endpoint never returns a placeholder value "
            "in place of real state. Verify the chain directly at the link above."
        )

    return payload


def handle(*args, **kwargs):
    """Dual-signature handler; autodetects call style from the first argument."""

    # Legacy direct-write style: first arg is an HTTP handler
    if args and hasattr(args[0], "send_response") and hasattr(args[0], "wfile"):
        handler = args[0]
        # ctx isn't passed in this style; try to reach it off the handler if the
        # server attaches it, otherwise report honestly that state is unavailable.
        ctx = getattr(handler, "ctx", None)
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        body = json.dumps(payload, indent=2).encode("utf-8")
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            try:
                handler.send_response(500)
                handler.send_header("Content-Type", "text/plain")
                handler.end_headers()
                handler.wfile.write(b"sebbi_engine: response failed\n")
            except Exception:
                pass
        return True

    # Router style: handle(method, action, data, api_key, ctx)
    method = args[0] if len(args) > 0 else kwargs.get("method")
    action = args[1] if len(args) > 1 else kwargs.get("action", "")
    ctx = args[4] if len(args) > 4 else kwargs.get("ctx")

    # Tolerate action arriving as a full path
    if isinstance(action, str) and action.startswith("/"):
        parts = [x for x in action.strip("/").split("/") if x]
        if len(parts) >= 3 and parts[1] == "sebbi_engine":
            action = parts[2]

    if action != "verify":
        return {"error": "not_found"}, 404
    if method != "GET":
        return {"error": "method_not_allowed"}, 405

    return _build_payload(ctx if isinstance(ctx, dict) else None), 200
