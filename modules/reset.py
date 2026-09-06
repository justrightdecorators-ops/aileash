# modules/reset.py
"""
modules/reset.py  —  ONE-TIME chain reset

Clears the audit_log so the chain starts fresh at genesis. Use this once,
after deploying the fixed register.py, to recover from a broken chain when
there is no backup worth keeping and no real customer data to preserve.

SAFETY:
  * KEYED. Requires the operator API key. A stranger cannot trigger it.
  * Requires an explicit confirm word in the body, so it cannot fire by
    accident or from a stray click.
  * Reports the block count before and after, so you can see it worked.
  * Touches ONLY audit_log. It does not delete files, does not touch the
    OTS anchors, does not touch customer/signup tables.

USE:
  1. Deploy this file into modules/.
  2. Deploy the FIXED register.py FIRST (single-seal version) or the fresh
     chain will just break again.
  3. Open, with your key, a POST to /x/reset/chain carrying
     {"confirm": "RESET-THE-CHAIN"}.
     Easiest from a phone: use the console, or any tool that can send a POST
     with the Authorization header. A plain browser GET will NOT do it — that
     is deliberate.
  4. Check /x/reset/status (GET, keyed) to see the block count.
  5. REMOVE this file afterwards. Do not leave a reset route deployed.

After it runs, the very next seal writes block 1 of a clean chain, and
/api/verify-chain should read OK again.
"""

import time

VERSION = "1.0.0"

# Nothing here is public. Reset must never be reachable without the key.
PUBLIC = set()

CONFIRM_WORD = "RESET-THE-CHAIN"


def _count(ctx):
    with ctx["lock"]:
        try:
            r = ctx["conn"].execute("SELECT COUNT(*) FROM audit_log").fetchone()
            return int(r[0]) if r else 0
        except Exception as e:  # noqa: BLE001
            return "error: " + type(e).__name__


def _tip(ctx):
    with ctx["lock"]:
        try:
            r = ctx["conn"].execute(
                "SELECT audit_hash, id FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not r:
                return None, 0
            return r[0], r[1]
        except Exception:
            return None, 0


def handle(method, action, data, api_key, ctx):
    # Keyed, always. No key, no reset — no matter the method or action.
    if not api_key:
        return {"error": "api key required — reset is operator-only"}, 401

    data = data or {}

    if method == "GET" and action == "status":
        tip, height = _tip(ctx)
        return {
            "module": "reset",
            "version": VERSION,
            "audit_log_blocks": _count(ctx),
            "current_tip": tip,
            "current_height": height,
            "how_to_reset": "POST /x/reset/chain with your key and "
                            '{"confirm": "%s"}' % CONFIRM_WORD,
            "warning": "Reset clears audit_log and cannot be undone. There is "
                       "no backup. Only do this if you mean it.",
        }, 200

    if method == "POST" and action == "chain":
        if data.get("confirm") != CONFIRM_WORD:
            return {
                "error": "confirmation required",
                "send": {"confirm": CONFIRM_WORD},
                "note": "This clears the whole chain and cannot be undone. "
                        "The confirm word is there so this cannot happen by accident.",
            }, 400

        before = _count(ctx)

        with ctx["lock"]:
            try:
                # Clear the chain table only. Nothing else is touched.
                ctx["conn"].execute("DELETE FROM audit_log")
                # Reset the autoincrement so the fresh chain starts at id 1.
                try:
                    ctx["conn"].execute(
                        "DELETE FROM sqlite_sequence WHERE name='audit_log'")
                except Exception:
                    pass  # table may not use sqlite_sequence; harmless
                ctx["conn"].commit()
            except Exception as e:  # noqa: BLE001
                return {"error": "reset failed",
                        "detail": type(e).__name__ + ": " + str(e),
                        "note": "Nothing may have been cleared. Check status."}, 500

        after = _count(ctx)
        return {
            "ok": True,
            "reset_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "blocks_before": before,
            "blocks_after": after,
            "next": "The next seal writes block 1 of a clean chain. Check "
                    "/api/verify-chain — it should read OK. Then REMOVE this "
                    "reset module from modules/ so the route is gone.",
        }, 200

    return {"error": "unknown action",
            "use": ["GET /x/reset/status", "POST /x/reset/chain"]}, 404
