"""
modules/rulebind.py  -  rule binding, verifiable without an account

THE QUESTION THIS ANSWERS
-------------------------
Eighteen months after a decision, nobody asks what was decided. They ask which
rules were live at that instant. Most systems answer with a changelog somebody
could have edited, or with a version number sitting beside the record rather
than inside it - which proves nothing, because anything beside a record can be
changed afterwards to suit.

The claim worth making is narrower and harder: the ruleset version was
committed at the moment of the decision, in the same sealed object, and a
verdict cannot later be reattributed to different rules.

HOW IT IS PROVED WITHOUT TRUSTING US
------------------------------------
Every decision here produces a binding digest:

    AILEASH-RULEBIND-v1|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|<score>|<sealed_at>

SHA-256 of that string is what gets sealed into the chain. Every component is
published. So anyone can take the components we return, rebuild the string
themselves, hash it, and check it equals the binding in the sealed record.

  - change the pack hash after the fact and the binding no longer recomputes
  - change the binding and the chain breaks from that block onwards
  - change the chain and it stops matching the peer chains that recorded our
    tip, and the timestamp proofs for the blocks that carry a confirmed one

None of those require taking our word for anything, and none require us to
disclose the scoring logic - the inputs are published as a digest, not as
values, and the weights are never exposed at any point.

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. That the pack
does what its description says. It proves which ruleset produced which verdict
and that the pairing was fixed at the time rather than asserted later. Narrow,
and the only part that is actually provable.

WHY prove IS KEYED  (changed in v1.1)
-------------------------------------
v1.0 ran the live scorer on arbitrary input from anyone and returned the score
to six decimal places, unlimited. That is an open oracle: enough calls and the
decision boundary can be mapped without ever seeing the weights. replay.py
already rate-limits novel inputs for exactly this reason, and a second free
route around it defeats the first. v1.0 also sealed a block on every
unauthenticated POST.

So: prove needs a key, and novel input sets are capped per key per hour.
Resubmitting an input set already on record is NEVER limited - repeating a
decision to check it is stable is the honest use, and throttling that would
break the thing the module exists to demonstrate.

Verification stays public. verify, packs and spec need no account, because a
proof only somebody with a key can check is not a proof.

ROUTES
------
  POST /x/rulebind/prove             KEYED   run a decision, get every component
  GET  /x/rulebind/verify?receipt=   public  recompute the binding for a record
  GET  /x/rulebind/packs             public  ruleset versions and first-sealed dates
  GET  /x/rulebind/spec              public  what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.1"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

# prove is deliberately NOT public. Everything that only reads is.
PUBLIC = {("GET", "verify"), ("GET", "packs"), ("GET", "spec"), ("GET", "")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Matches replay.py. Novel input sets only; repeats are unlimited.
NOVEL_PER_HOUR = 40

# Same runtime lookup replay.py uses - never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

# Fallback bands, used ONLY if the live engine exposes no decider and no band
# constants. Every response says which of the three produced the verdict, so a
# banded verdict is never passed off as one the engine stated itself.
FALLBACK_ALLOW_BELOW = 0.35
FALLBACK_CHALLENGE_BELOW = 0.70

ANCHOR_NOTE = ("External timestamping is per proof, not a property of the "
               "chain. A proof is submitted first and confirmed later, and "
               "submitted is not confirmed. Check the state of any individual "
               "proof at /x/ots/status.")

_ready = False
_novel = {}          # api_key -> [timestamps of novel input sets]


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute(
            "CREATE TABLE IF NOT EXISTS rulebind_log("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,pack_id TEXT,"
            "pack_hash TEXT,inputs_digest TEXT,verdict TEXT,score REAL,"
            "sealed_at REAL,binding TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_hash ON rulebind_log(audit_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_pack ON rulebind_log(pack_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_inputs ON rulebind_log(inputs_digest)")
        c.commit()
    _ready = True


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ----------------------------------------------------------------------
# the engine, found at runtime
# ----------------------------------------------------------------------

def _find(names):
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _find_bands():
    """Read the engine's own band constants if it publishes them, so this file
    does not become one more place where 0.35 and 0.70 are written down and
    quietly drift. Returns (allow_below, challenge_below, source)."""
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        a = getattr(mod, "ALLOW_BELOW", None)
        c = getattr(mod, "CHALLENGE_BELOW", None)
        if isinstance(a, (int, float)) and isinstance(c, (int, float)):
            return float(a), float(c), modname + ".ALLOW_BELOW/CHALLENGE_BELOW"
    return (FALLBACK_ALLOW_BELOW, FALLBACK_CHALLENGE_BELOW,
            "rulebind fallback constants")


def _active_pack(ctx):
    """The ruleset in force. Read from signal_packs if the table is there,
    otherwise fall back to a hash of the core engine's own identity - either
    way the value is stable and published."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT pack_id,version,pack_hash FROM signal_packs "
                "ORDER BY id DESC LIMIT 1").fetchone()
        if row and row[2]:
            return str(row[0] or "core"), str(row[2])
        if row:
            return str(row[0] or "core"), _sha("pack:%s:v%s" % (row[0], row[1]))
    except Exception:
        pass

    fn, where = _find(SCORER_NAMES)
    if fn:
        try:
            import inspect
            return "core-nine", _sha(inspect.getsource(fn))
        except Exception:
            return "core-nine", _sha("core-nine|" + str(where))
    return "unknown", _sha("unknown")


def _canonical_inputs(data):
    """Inputs are published as a digest, never as values. Somebody testing this
    knows what they sent; nobody else learns anything from the record."""
    clean = {}
    for k, v in list(data.items())[:MAX_INPUT_KEYS]:
        if k in ("api_key", "token", "key"):
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            clean[str(k)[:40]] = v
        else:
            clean[str(k)[:40]] = str(v)[:120]
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def _binding(pack_id, pack_hash, inputs_digest, verdict, score, sealed_at):
    material = "|".join([BINDING_PREFIX, str(pack_id), str(pack_hash),
                         str(inputs_digest), str(verdict), ("%.6f" % float(score)),
                         ("%.3f" % float(sealed_at))])
    return material, _sha(material)


def _seen_before(ctx, inputs_digest):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT 1 FROM rulebind_log WHERE inputs_digest=? LIMIT 1",
                (inputs_digest,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _novel_allowed(api_key):
    """Rate limit novel input sets only. Prunes as it goes, so this dict cannot
    grow without bound the way W60/W5M/W1H did before prune_memory()."""
    now = time.time()
    cutoff = now - 3600
    for k in list(_novel.keys()):
        kept = [t for t in _novel[k] if t > cutoff]
        if kept:
            _novel[k] = kept
        else:
            del _novel[k]
    hits = _novel.get(api_key, [])
    if len(hits) >= NOVEL_PER_HOUR:
        oldest = min(hits)
        return False, int(3600 - (now - oldest)) + 1
    hits.append(now)
    _novel[api_key] = hits
    return True, 0


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values.")}, 400

    inputs_digest = _sha(_canonical_inputs(data))
    repeat = _seen_before(ctx, inputs_digest)
    if not repeat:
        ok, retry_after = _novel_allowed(api_key)
        if not ok:
            return {
                "error": "novel_input_rate_limited",
                "novel_inputs_per_hour": NOVEL_PER_HOUR,
                "retry_after_seconds": retry_after,
                "note": ("Input sets already on record can be resubmitted "
                         "without limit - repeating a decision to check it is "
                         "stable is never throttled. Only new input sets are "
                         "capped, because an unlimited scoring oracle can be "
                         "used to map the decision boundary."),
            }, 429

    scorer, scorer_where = _find(SCORER_NAMES)
    if not scorer:
        return {"error": "engine_unavailable",
                "message": "The scoring function could not be found at runtime."}, 503

    try:
        result = scorer(dict(data))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return {"error": "scoring_failed", "message": str(exc)[:200]}, 400

    decider, decider_where = _find(DECIDER_NAMES)
    verdict = None
    verdict_source = None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
            verdict_source = "engine (" + str(decider_where) + ")"
        except Exception:
            verdict = None
    if verdict is None:
        allow_below, challenge_below, band_source = _find_bands()
        verdict = ("ALLOW" if score < allow_below
                   else ("CHALLENGE" if score < challenge_below else "BLOCK"))
        verdict_source = "banded by rulebind using " + band_source

    pack_id, pack_hash = _active_pack(ctx)
    sealed_at = time.time()
    material, binding = _binding(pack_id, pack_hash, inputs_digest,
                                 verdict, score, sealed_at)

    detail = ("rulebind=" + binding + ";pack=" + pack_id + ";pack_hash=" + pack_hash +
              ";inputs=" + inputs_digest + ";verdict=" + str(verdict) +
              ";score=%.6f" % score)
    ev = {"user_id": "rb:" + pack_id, "action": "rule_binding_sealed", "amount": 0,
          "country": "UK", "device_id": "rulebind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RULEBIND_" + str(verdict), "score": round(score, 6),
           "rulebind_version": VERSION, "pack_id": pack_id, "pack_hash": pack_hash,
           "binding": binding, "timestamp": sealed_at, "detail": detail}

    try:
        h, idx, seq = ctx["seal"](ev, res, sealed_at, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "note": ("Nothing was written. Send the identical inputs again "
                         "once the cause is fixed - no partial record was "
                         "stored.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash",
                "note": "Nothing was written. The same inputs can be resent."}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict,
        "verdict_source": verdict_source,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "inputs_already_on_record": repeat,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding": binding,
        "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "recompute_it_yourself": {
            "step_1": ("Take binding_material exactly as returned - it is the "
                       "string that was hashed, printed in full."),
            "step_2": "SHA-256 it. You should get the value in binding.",
            "step_3": ("Confirm the ruleset hash appears inside that string. It "
                       "is a component of the digest, not a field beside it - "
                       "change it and the digest no longer recomputes."),
            "step_4": ("Check the block sits in the chain, that our tip was "
                       "recorded by operators we do not control at "
                       "/x/roster/list and /x/witness/peers, and the state of "
                       "the timestamp proof covering it at /x/ots/status."),
            "shell": ("printf '%s' \"$MATERIAL\" | shasum -a 256"),
        },
        "what_this_proves": (
            "That this verdict and this ruleset version were committed together, "
            "at this time, in one object. The pairing cannot be altered afterwards "
            "without breaking the digest, and the digest cannot be altered without "
            "breaking the chain."),
        "what_it_does_not_prove": (
            "That the rules were good, or the verdict correct. Only which ruleset "
            "produced it and that the pairing was fixed at the time."),
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + h,
    }, 200


def _verify(ctx, data):
    receipt = str((data or {}).get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required",
                "use": "/x/rulebind/verify?receipt=<audit hash>"}, 400
    if not HEX64.match(receipt):
        return {"error": "receipt_malformed",
                "expected": "64 lowercase hex characters"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,inputs_digest,verdict,score,sealed_at,"
            "binding,block_index FROM rulebind_log WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No rule-binding record with that receipt."}, 404

    pack_id, pack_hash, inputs_digest, verdict, score, sealed_at, stored, block = row
    material, recomputed = _binding(pack_id, pack_hash, inputs_digest,
                                    verdict, score, sealed_at)
    matches = (recomputed == stored)

    return {
        "found": True,
        "receipt": receipt,
        "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict,
        "score": score,
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored,
        "binding_material": material,
        "binding_recomputed": recomputed,
        "binding_matches": matches,
        "result": ("The ruleset version recomputes into the binding that was "
                   "sealed with this decision. It was bound at the time, not "
                   "attached afterwards."
                   if matches else
                   "MISMATCH. The stored binding does not recompute from the "
                   "stored components. Something has been altered and this "
                   "record should not be relied upon."),
        "what_this_check_is": (
            "A recomputation of the binding from its own published components. "
            "It does not by itself verify the chain, the witnesses or the "
            "timestamp proof - those are separate checks at the links below, "
            "run by you."),
        "chain_tip": "/x/witness/tip",
        "witnessed_by": "/x/roster/list",
        "timestamp_proofs": "/x/ots/status",
        "anchoring": ANCHOR_NOTE,
    }, 200


def _packs(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,COUNT(*),MIN(sealed_at),MAX(sealed_at)"
            " FROM rulebind_log GROUP BY pack_id,pack_hash ORDER BY MAX(sealed_at) DESC"
        ).fetchall()
    current_id, current_hash = _active_pack(ctx)
    return {
        "current": {"pack_id": current_id, "pack_hash": current_hash},
        "history": [{
            "pack_id": r[0], "pack_hash": r[1], "decisions_bound": r[2],
            "first_sealed": _iso(r[3]), "last_sealed": _iso(r[4]),
            "current": (r[1] == current_hash),
        } for r in rows],
        "note": ("Each ruleset version has its own hash. Changing a weight, a "
                 "threshold or a signal produces a new hash and a new dated "
                 "entry here, so a change to the rules is an event in the "
                 "record rather than a silent edit. Decisions stay bound to the "
                 "version that produced them."),
        "limit_of_this_list": (
            "It shows versions that have bound at least one decision through "
            "this module. A ruleset that was live but never used here does not "
            "appear."),
    }, 200


def _spec():
    return {
        "module": "rulebind", "version": VERSION,
        "check": "rule_binding",
        "question": ("Was the ruleset version bound at decision time, or "
                     "attached to the record afterwards?"),
        "binding_format": (BINDING_PREFIX +
                           "|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|"
                           "<score:.6f>|<sealed_at:.3f>"),
        "digest": "SHA-256 of that string, UTF-8, no trailing newline",
        "routes": {
            "POST /x/rulebind/prove": "keyed - runs a decision and seals the binding",
            "GET /x/rulebind/verify?receipt=": "public - recomputes a sealed binding",
            "GET /x/rulebind/packs": "public - ruleset versions and dates",
            "GET /x/rulebind/spec": "public - this document",
        },
        "why_prove_is_keyed": (
            "It runs the live scoring function and returns a numeric score. "
            "Unlimited public access to that is a scoring oracle: enough calls "
            "and the decision boundary can be mapped without the weights ever "
            "being disclosed. It is keyed, and novel input sets are capped at "
            "%d per key per hour. Resubmitting an input set already on record "
            "is never limited, because checking that a decision is stable is "
            "the honest use." % NOVEL_PER_HOUR),
        "why_verification_is_public": (
            "A proof only account holders can check is not a proof. Anyone can "
            "recompute any binding and check any receipt without an account."),
        "how_to_test_it": [
            "POST inputs to /x/rulebind/prove with your key.",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Check the witnesses at /x/roster/list and the proof state at /x/ots/status.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names and intermediate values. Inputs "
            "are published as a digest, not as values. Nothing here requires the "
            "scoring logic to be revealed, and none of it is."),
        "what_it_does_not_prove": (
            "That the rules were good or the verdict correct. Only which ruleset "
            "produced which verdict, and that the pairing was fixed at the time."),
        "anchoring": ANCHOR_NOTE,
        "cost": "Verification is free and needs no account. Sealing needs a key.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "prove":
            if not api_key:
                return {"error": "api_key_required",
                        "message": ("prove runs the live scoring function, so it "
                                    "needs a key. Verification is public: "
                                    "/x/rulebind/verify, /x/rulebind/packs and "
                                    "/x/rulebind/spec need no account.")}, 401
            return _prove(ctx, api_key, data)
        return {"error": "unknown_action", "action": action, "POST": ["prove"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "verify", "packs"]}, 404
