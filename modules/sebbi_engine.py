# modules/sebbi_engine.py
"""
Live chain-state endpoint  -  GET /x/sebbi_engine/state

WHAT CHANGED IN v1.1, AND WHY
-----------------------------
v1.0 served this at /verify and returned "status": "sealed". It performed no
verification: no rehash, no chain walk, no proof check. It read the last row of
audit_log and reported that a row existed. A route called verify that returns
sealed, having checked neither, is a word one step past what the check does -
the same fault that has been raised against this codebase before, and the word
an auditor will quote back.

So v1.1 does the same honest job under honest names:

  * action renamed  verify -> state
  * status is now  live / unavailable, never "sealed"
  * tip_digest removed - it was a hash of a hash, proving nothing
  * token_budget removed - unrelated to chain state, it did not belong here
  * every response names the routes that DO verify, and says plainly that
    this one does not

WHAT THIS ROUTE IS
------------------
The current tip and height, read from the database at request time. Nothing
cached, nothing hardcoded. If the chain cannot be read it says so rather than
reporting a reassuring value it cannot stand behind.

WHAT IT IS NOT
--------------
It is not verification. Reading the last row proves a row exists. Verifying
the chain means rewalking it, and confirming the tip was recorded by operators
we do not control. Those are separate routes, listed in every response.

Dual-signature handle(...) so it works with the router
    handle(method, action, data, api_key, ctx) -> (payload, status)
and with older direct-write callers
    handle(handler, path, query_params=None) -> writes the response, returns True

Import-safe: nothing here can crash the server on import.
"""

import os
import json
import time

VERSION = "1.1"
MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")

# GET /state is public by design - anyone can read live state without an
# account. The old ("GET", "verify") pair is kept so existing callers get the
# renamed answer rather than a bare 404.
PUBLIC = {("GET", "state"), ("GET", "verify"), ("GET", "spec"), ("GET", "")}

VERIFY_ELSEWHERE = {
    "chain_tip": "https://sebbi.pro/x/witness/tip",
    "append_only_proof": "https://sebbi.pro/x/consistency/proof",
    "is_my_tip_still_on_this_chain": "https://sebbi.pro/x/consistency/ancestor",
    "who_recorded_our_tip": "https://sebbi.pro/x/roster/list",
    "timestamp_proof_state": "https://sebbi.pro/x/ots/status",
}

NOT_VERIFICATION = (
    "This route reads the current tip and height. It does not verify anything: "
    "it does not rewalk the chain, recompute any hash, or check any external "
    "record. Reading the last row proves a row exists and nothing more. The "
    "routes above are the ones that verify, and you run them yourself."
)

try:
    print("modules.sebbi_engine: loaded (v%s, live-state mode)" % VERSION, flush=True)
except Exception:
    pass


def _read_live_chain(ctx):
    """
    Read the real current chain tip and height from the live database via ctx.

    Returns what was actually found, or a record of why it could not be read.
    It never invents a value.
    """
    if not isinstance(ctx, dict):
        return {"live": False, "reason": "no_context"}

    conn = ctx.get("conn") or ctx.get("db") or ctx.get("connection")
    lock = ctx.get("lock")
    if conn is None:
        return {"live": False, "reason": "no_db_handle"}

    # Matched to modules/witness.py _our_tip(): the chain lives in audit_log,
    # the sealed hash is audit_hash, the height is id.
    query = ("SELECT audit_hash AS seal, id AS height FROM audit_log "
             "ORDER BY id DESC LIMIT 1")

    def _run():
        try:
            row = conn.execute(query).fetchone()
        except Exception:
            return {"live": False, "reason": "query_failed"}
        if not row:
            return {"live": False, "reason": "no_chain_rows"}
        seal = row[0]
        height = row[1]
        if seal is None:
            return {"live": False, "reason": "null_tip"}
        return {"live": True, "tip": str(seal),
                "height": int(height) if height is not None else None}

    try:
        if lock is not None:
            with lock:
                return _run()
        return _run()
    except Exception as e:  # noqa: BLE001
        return {"live": False, "reason": "read_error:" + e.__class__.__name__}


def _build_payload(ctx):
    now = int(time.time())
    chain = _read_live_chain(ctx)

    payload = {
        "module": MODULE_NAME,
        "version": VERSION,
        "read_at": now,
        "read_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }

    if chain.get("live"):
        payload["status"] = "live"
        payload["chain_tip"] = chain["tip"]
        payload["chain_height"] = chain["height"]
        payload["note"] = (
            "Live chain state, read at request time. It changes as the chain "
            "grows, so two reads a minute apart are expected to differ.")
    else:
        payload["status"] = "unavailable"
        payload["chain_tip"] = None
        payload["chain_height"] = None
        payload["reason"] = chain.get("reason", "unknown")
        payload["note"] = (
            "The live chain could not be read for this request, so no state is "
            "reported. This endpoint never returns a placeholder in place of "
            "real state.")

    payload["height_is_not_activity"] = (
        "A liveness beacon seals a block every five minutes, so most of the "
        "height is heartbeat rather than customer decisions. Do not read this "
        "number as usage.")
    payload["this_is_not_verification"] = NOT_VERIFICATION
    payload["verify_it_yourself"] = VERIFY_ELSEWHERE
    return payload


def _spec():
    return {
        "module": MODULE_NAME,
        "version": VERSION,
        "route": "GET /x/sebbi_engine/state",
        "what_it_returns": "The current chain tip and height, read at request time.",
        "what_it_does_not_do": NOT_VERIFICATION,
        "renamed_in_v1_1": (
            "The action was called verify and returned status sealed. It "
            "verified nothing, so both names were wrong. verify still answers, "
            "and returns this same state payload under the honest names."),
        "verify_it_yourself": VERIFY_ELSEWHERE,
        "cost": "Free. No account, no key.",
    }, 200


def handle(*args, **kwargs):
    """Dual-signature handler; autodetects call style from the first argument."""

    # Legacy direct-write style: first arg is an HTTP handler
    if args and hasattr(args[0], "send_response") and hasattr(args[0], "wfile"):
        handler = args[0]
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

    action = (action or "").strip("/").lower()

    if method != "GET":
        return {"error": "method_not_allowed", "GET": ["state", "spec"]}, 405

    if action == "spec":
        return _spec()

    if action in ("state", ""):
        return _build_payload(ctx if isinstance(ctx, dict) else None), 200

    if action == "verify":
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        payload["renamed"] = (
            "This action is now /x/sebbi_engine/state. It was called verify and "
            "returned status sealed, while verifying nothing. Same data, honest "
            "names. Update your caller when convenient.")
        return payload, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["state", "spec"]}, 404
