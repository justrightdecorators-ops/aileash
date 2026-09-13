"""
modules/rulebind.py  v1.2.0  —  rule binding, verifiable without an account

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

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. It proves which
ruleset produced which verdict and that the pairing was fixed at the time
rather than asserted later. Narrow, and the only part that is actually
provable.

THE v1.1 MISTAKE, AND WHAT v1.2 DOES ABOUT IT
---------------------------------------------
v1.0 let anyone POST arbitrary inputs and returned a six-decimal score,
unlimited. That is a scoring oracle: enough calls and the decision boundary
can be mapped without the weights ever being disclosed.

v1.1 closed it by keying prove. That was right about the oracle and wrong
about the consequence: the published ordering-test document declares this
check demonstrable_publicly, and after v1.1 no stranger could complete it.
The self-check runner went from PASS to INCONCLUSIVE, correctly, because a
browser holds no key. A check nobody outside can run is not a public check,
and leaving the document claiming otherwise would have been exactly the fault
this codebase keeps getting caught on - a statement one step past what the
thing beneath it does.

v1.2 gives the demonstration back without reopening the oracle:

  1. GET or POST /x/rulebind/demo - PUBLIC. Runs ONE fixed input set, the same
     one every time, hardcoded below. A fixed input cannot map a boundary: you
     learn one point on a curve, and it is the same point on every call. The
     response carries every component and the full binding_material, so anyone
     can recompute the digest with a shell command and check it.

  2. POST /x/rulebind/prove with NO key - allowed only when that exact input
     set is ALREADY on record. A repeat discloses nothing new; its score is
     already public through /verify. Novel input sets still need a key, and
     are still capped per key per hour.

The rule underneath both: what is already public stays public, and what would
make the boundary mappable stays keyed.

ROUTES
------
  GET/POST /x/rulebind/demo             public  fixed fixture, full material
  POST     /x/rulebind/prove            public for repeats, keyed for novel
  GET      /x/rulebind/verify?receipt=  public  recompute a sealed binding
  GET      /x/rulebind/packs            public  ruleset versions and dates
  GET      /x/rulebind/spec             public  what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.2.0"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

PUBLIC = {("GET", "verify"), ("GET", "packs"), ("GET", "spec"), ("GET", ""),
          ("GET", "demo"), ("POST", "demo"), ("POST", "prove")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Cap on NOVEL input sets per key per hour. Repeats are never limited.
NOVEL_PER_HOUR = 40

# The demo fixture. One input set, fixed, using the engine's real signal names.
# Deliberately unremarkable: an ordinary allow-shaped request, so the single
# point it discloses is the least informative point available.
DEMO_INPUTS = {
    "action": "purchase",
    "amount": 40.00,
    "trust": 0.80,
    "v60": 1,
    "v5m": 2,
    "v1h": 3,
    "device_risk": 0.10,
    "anomaly": 0.05,
    "country": "GB",
    "country_shift": 0,
}
DEMO_RESEAL_AFTER = 3600   # seal the fixture at most once an hour

SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

FALLBACK_ALLOW_BELOW = 0.35
FALLBACK_CHALLENGE_BELOW = 0.70

ANCHOR_NOTE = ("External timestamping is per proof, not a property of the "
               "chain. A proof is submitted first and confirmed later, and "
               "submitted is not confirmed. Check the state of any individual "
               "proof at /x/ots/status.")

_ready = False
_novel = {}


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


def _last_for_inputs(ctx, inputs_digest):
    try:
        with ctx["lock"]:
            return ctx["conn"].execute(
                "SELECT pack_id,pack_hash,verdict,score,sealed_at,binding,"
                "audit_hash,block_index FROM rulebind_log WHERE inputs_digest=? "
                "ORDER BY id DESC LIMIT 1", (inputs_digest,)).fetchone()
    except Exception:
        return None


def _novel_allowed(api_key):
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
        return False, int(3600 - (now - min(hits))) + 1
    hits.append(now)
    _novel[api_key] = hits
    return True, 0


# ----------------------------------------------------------------------
# scoring and sealing
# ----------------------------------------------------------------------

def _score_and_seal(ctx, api_key, inputs, inputs_digest):
    scorer, _ = _find(SCORER_NAMES)
    if not scorer:
        return None, ({"error": "engine_unavailable",
                       "message": "The scoring function could not be found at runtime."}, 503)
    try:
        result = scorer(dict(inputs))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return None, ({"error": "scoring_failed", "message": str(exc)[:200]}, 400)

    decider, decider_where = _find(DECIDER_NAMES)
    verdict, verdict_source = None, None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
            verdict_source = "engine (" + str(decider_where) + ")"
        except Exception:
            verdict = None
    if verdict is None:
        a, c, band_source = _find_bands()
        verdict = "ALLOW" if score < a else ("CHALLENGE" if score < c else "BLOCK")
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
        return None, ({"error": "seal_failed",
                       "detail": type(exc).__name__ + ": " + str(exc)[:250],
                       "note": "Nothing was written. Send the identical inputs again."}, 500)
    if not h:
        return None, ({"error": "seal_failed", "detail": "seal returned no hash"}, 500)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict, "verdict_source": verdict_source,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding": binding, "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
    }, None


RECOMPUTE = {
    "step_1": ("Take binding_material exactly as returned - it is the string "
               "that was hashed, printed in full."),
    "step_2": "SHA-256 it. You should get the value in binding.",
    "step_3": ("Confirm the ruleset hash appears inside that string. It is a "
               "component of the digest, not a field beside it - change it and "
               "the digest no longer recomputes."),
    "step_4": ("Check the block sits in the chain, that our tip was recorded by "
               "operators we do not control at /x/roster/list, and the state of "
               "the timestamp proof covering it at /x/ots/status."),
    "shell": "printf '%s' \"$MATERIAL\" | shasum -a 256",
}

PROVES = ("That this verdict and this ruleset version were committed together, "
          "at this time, in one object. The pairing cannot be altered afterwards "
          "without breaking the digest, and the digest cannot be altered without "
          "breaking the chain.")

NOT_PROVES = ("That the rules were good, or the verdict correct. Only which "
              "ruleset produced it and that the pairing was fixed at the time.")


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _demo(ctx):
    """Public. One fixed input set, the same on every call.

    Fixed inputs are not an oracle: every caller learns the same single point,
    and that point is published here on purpose. Sealed at most once an hour so
    the route cannot be used to write blocks."""
    inputs_digest = _sha(_canonical_inputs(DEMO_INPUTS))
    row = _last_for_inputs(ctx, inputs_digest)

    fresh = False
    if row and (time.time() - float(row[4])) < DEMO_RESEAL_AFTER:
        pack_id, pack_hash, verdict, score, sealed_at, binding, receipt, block = row
        material, _ = _binding(pack_id, pack_hash, inputs_digest,
                               verdict, score, sealed_at)
        body = {
            "verdict": verdict, "score": score,
            "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
            "inputs_digest": inputs_digest,
            "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
            "binding": binding, "binding_material": material,
            "sealed": {"receipt": receipt, "block_index": block},
        }
    else:
        body, err = _score_and_seal(ctx, "public-rulebind-demo",
                                    DEMO_INPUTS, inputs_digest)
        if err:
            return err
        fresh = True

    body.update({
        "demo": True,
        "freshly_sealed": fresh,
        "inputs_used": DEMO_INPUTS,
        "why_the_inputs_are_fixed": (
            "This route runs one input set and always the same one, so it "
            "cannot be used to map the decision boundary - every caller learns "
            "the same single point, and that point is published above. Running "
            "your own inputs needs a key, which is what keeps the boundary "
            "closed while leaving this check demonstrable by anyone."),
        "reseal_after_seconds": DEMO_RESEAL_AFTER,
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + str(
            (body.get("sealed") or {}).get("receipt")),
    })
    return body, 200


def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values. Without a key, only input "
                            "sets already on record are accepted - see "
                            "/x/rulebind/demo for one anyone can run.")}, 400

    inputs_digest = _sha(_canonical_inputs(data))
    repeat = _last_for_inputs(ctx, inputs_digest) is not None

    if not api_key:
        if not repeat:
            return {
                "error": "api_key_required_for_novel_inputs",
                "message": ("This input set is not on record. Running the live "
                            "scorer on new inputs needs a key, because unlimited "
                            "public scoring of arbitrary inputs would map the "
                            "decision boundary."),
                "what_you_can_do_without_a_key": {
                    "run_the_check": "/x/rulebind/demo",
                    "recompute_any_sealed_binding": "/x/rulebind/verify?receipt=...",
                    "ruleset_history": "/x/rulebind/packs",
                },
            }, 401
        api_key = "public-rulebind-repeat"
    else:
        if not repeat:
            ok, retry_after = _novel_allowed(api_key)
            if not ok:
                return {"error": "novel_input_rate_limited",
                        "novel_inputs_per_hour": NOVEL_PER_HOUR,
                        "retry_after_seconds": retry_after,
                        "note": ("Input sets already on record are never "
                                 "limited. Only new ones are capped.")}, 429

    body, err = _score_and_seal(ctx, api_key, data, inputs_digest)
    if err:
        return err

    body.update({
        "inputs_already_on_record": repeat,
        "authenticated": not str(api_key).startswith("public-"),
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + body["sealed"]["receipt"],
    })
    return body, 200


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
        "found": True, "receipt": receipt, "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict, "score": score, "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored, "binding_material": material,
        "binding_recomputed": recomputed, "binding_matches": matches,
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
                 "record rather than a silent edit."),
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
        "demonstrable_publicly": True,
        "public_demonstration": "/x/rulebind/demo",
        "routes": {
            "GET or POST /x/rulebind/demo": "public - one fixed input set, full material",
            "POST /x/rulebind/prove": ("public for input sets already on record, "
                                       "keyed for new ones"),
            "GET /x/rulebind/verify?receipt=": "public - recomputes a sealed binding",
            "GET /x/rulebind/packs": "public - ruleset versions and dates",
            "GET /x/rulebind/spec": "public - this document",
        },
        "how_the_oracle_is_closed_without_closing_the_check": (
            "Running arbitrary inputs against the live scorer returns a numeric "
            "score, and unlimited public access to that maps the decision "
            "boundary without any weight being disclosed. So new input sets need "
            "a key and are capped at %d per key per hour. What stays public is "
            "everything that discloses nothing new: one fixed demo input set, "
            "repeats of input sets already on record, and recomputation of any "
            "sealed binding." % NOVEL_PER_HOUR),
        "how_to_test_it_with_no_account": [
            "GET /x/rulebind/demo",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Check the witnesses at /x/roster/list and the proof state at /x/ots/status.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names beyond the fixed demo input set, "
            "and intermediate values. Submitted inputs are published as a digest, "
            "not as values."),
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "cost": "Free. The public demonstration needs no account.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if action == "demo":
        return _demo(ctx)

    if method == "POST":
        if action == "prove":
            return _prove(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["prove", "demo"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "demo", "verify", "packs"], "POST": ["prove", "demo"]}, 404
