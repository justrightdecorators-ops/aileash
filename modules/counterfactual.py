"""
Counterfactual explanation - /x/counterfactual/<action>

WHAT THIS IS
------------
Every governance vendor claims explainability. What they nearly all mean is
attribution: a list of which factors pushed the score up. That answers "why
did this happen" and leaves the only question anyone actually cares about
untouched - "what would have had to be different?"

That second question is the one a person contesting a decision needs, the
one Article 22 recourse turns on, and the one an ML-based system genuinely
cannot answer. A neural model is not invertible: you can attribute, you can
approximate with a sampling method, you cannot state the exact boundary.

This engine is arithmetic with published weights. Arithmetic runs backwards.
So for any sealed decision, the exact minimum change in every single factor
that would have produced a different verdict can be computed, stated, and
sealed - and anyone can re-derive it independently.

THE SCORING FUNCTION, RUN BACKWARDS
-----------------------------------
    score = (1 - trust)              x 0.30
          + min(v60/20, 1)           x 0.15
          + min(v5m/50, 1)           x 0.10
          + min(v1h/200, 1)          x 0.10
          + min(ln(1+amt)/ln(10001), 1) x 0.15
          + device_risk              x 0.10
          + anomaly                  x 0.10
          + 0.10 if country_shift
          + 0.10 if unsafe_country

    ALLOW < 0.35 <= CHALLENGE < 0.70 <= BLOCK

Each term is monotonic and independently invertible, so the required delta
for any single factor is exact rather than estimated.

WHAT YOU GET BACK
-----------------
  - the margin: how far the score sat from the nearest boundary. A BLOCK at
    0.701 and a BLOCK at 0.94 are not the same decision, and treating them
    the same is a failure of explanation.
  - per factor: the exact value that factor would have needed, alone, to
    reach the next verdict down - or a statement that this factor alone
    could not have done it, however far it moved.
  - the cheapest single change, where one exists.
  - a recourse statement in plain English, suitable for handing to the
    person the decision was about.

THE UNCOMFORTABLE PART, STATED UP FRONT
---------------------------------------
Perfect explainability and resistance to gaming are in direct tension, and
almost nobody in this field says so.

Telling a legitimate subject "your 60-second velocity needed to be under 11"
also tells a fraudster exactly where the wall is. This is not a flaw that
better engineering removes - it is what explanation IS. Publishing weights
means the boundary is derivable by anyone who reads the whitepaper anyway;
this module makes explicit what was already implicit.

The mitigations are honest rather than complete: these routes require a key
and are rate limited; every counterfactual request is itself sealed, so a
pattern of boundary probing is visible in the chain afterwards; and the
trust signal is history-dependent, so knowing the boundary does not let you
arrive at it instantly.

Operators handing counterfactuals to end users should treat that as a
deliberate choice with a cost, not a free feature.

    POST /x/counterfactual/explain    signals + verdict -> full analysis
    GET  /x/counterfactual/decision?block=N   explain a sealed decision
    GET  /x/counterfactual/probing    who has been mapping the boundary
"""

import json, math, time
from datetime import datetime, timezone

VERSION = "1.0"

ALLOW_MAX = 0.35
CHALLENGE_MAX = 0.70
LN_CAP = math.log1p(10000)

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS cf_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,ts REAL,block_index INTEGER,verdict TEXT,score REAL,target TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cf_key ON cf_requests(api_key,ts)")
        ctx["conn"].commit()
    _ready = True


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _verdict(sc):
    if sc < ALLOW_MAX:
        return "ALLOW"
    if sc < CHALLENGE_MAX:
        return "CHALLENGE"
    return "BLOCK"


def _normalise(data):
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, _f(data, "v60")),
        "v5m": max(0.0, _f(data, "v5m")),
        "v1h": max(0.0, _f(data, "v1h")),
        "amount": max(0.0, _f(data, "amount")),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": bool(data.get("unsafe_country")),
    }


# ---- per-factor contribution and inversion -------------------------------

def _contribs(s):
    return {
        "trust": (1 - s["trust"]) * 0.30,
        "v60": min(s["v60"] / 20.0, 1) * 0.15,
        "v5m": min(s["v5m"] / 50.0, 1) * 0.10,
        "v1h": min(s["v1h"] / 200.0, 1) * 0.10,
        "amount": min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15,
        "device_risk": s["device_risk"] * 0.10,
        "anomaly": s["anomaly"] * 0.10,
        "country_shift": 0.10 if s["country_shift"] else 0.0,
        "unsafe_country": 0.10 if s["unsafe_country"] else 0.0,
    }


def _invert(factor, target_contrib, s):
    """Value this factor would need for the stated contribution.
    Returns (value, human_string) or None where impossible."""
    t = target_contrib
    if factor == "trust":
        v = 1 - (t / 0.30)
        if v > 1.0:
            return None
        return round(_clamp(v), 4), "trust of " + str(round(_clamp(v), 3)) + " or higher (was " + str(round(s["trust"], 3)) + ")"
    if factor in ("v60", "v5m", "v1h"):
        cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[factor]
        v = (t / w) * cap
        if v < 0:
            return None
        label = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[factor]
        return round(v, 2), label + " velocity of " + str(int(v)) + " or fewer (was " + str(int(s[factor])) + ")"
    if factor == "amount":
        v = math.expm1((t / 0.15) * LN_CAP)
        if v < 0:
            return None
        return round(v, 2), "amount of " + str(round(v, 2)) + " or less (was " + str(round(s["amount"], 2)) + ")"
    if factor in ("device_risk", "anomaly"):
        v = t / 0.10
        if v < 0:
            return None
        nice = "device risk" if factor == "device_risk" else "behavioural anomaly"
        return round(_clamp(v), 4), nice + " of " + str(round(_clamp(v), 3)) + " or lower (was " + str(round(s[factor], 3)) + ")"
    if factor in ("country_shift", "unsafe_country"):
        if t >= 0.10:
            return None
        nice = "no country change from the previous event" if factor == "country_shift" else "an event from a jurisdiction on the safe list"
        return 0, nice
    return None


def _analyse(s, want=None):
    score = _score(s)
    verdict = _verdict(score)
    contribs = _contribs(s)

    if verdict == "BLOCK":
        target_v, ceiling = "CHALLENGE", CHALLENGE_MAX
    elif verdict == "CHALLENGE":
        target_v, ceiling = "ALLOW", ALLOW_MAX
    else:
        return {"score": score, "verdict": verdict,
                "margin_to_next_boundary": round(ALLOW_MAX - score, 4),
                "note": "Already the most permissive verdict. Nothing needed to change it."}, contribs, None

    if want in ("ALLOW", "CHALLENGE"):
        target_v = want
        ceiling = ALLOW_MAX if want == "ALLOW" else CHALLENGE_MAX

    # need score strictly below ceiling
    needed = round(score - ceiling, 6)
    factors = []
    cheapest = None

    for name, c in sorted(contribs.items(), key=lambda kv: -kv[1]):
        entry = {"factor": name,
                 "contributed": round(c, 4),
                 "share_of_score_pct": (round(100 * c / score, 1) if score else 0)}
        if c <= 0:
            entry["alone_sufficient"] = False
            entry["reason"] = "contributed nothing to this score"
            factors.append(entry)
            continue
        # contribution required so total lands just under the ceiling
        target_contrib = c - needed - 0.0001
        if target_contrib < 0:
            entry["alone_sufficient"] = False
            entry["reason"] = ("even at zero this factor only removes "
                               + str(round(c, 4)) + " of the "
                               + str(round(needed, 4)) + " required")
        else:
            inv = _invert(name, target_contrib, s)
            if inv is None:
                entry["alone_sufficient"] = False
                entry["reason"] = "no attainable value of this factor reaches the threshold"
            else:
                val, human = inv
                entry["alone_sufficient"] = True
                entry["required_value"] = val
                entry["statement"] = human
                if cheapest is None:
                    cheapest = {"factor": name, "required_value": val, "statement": human}
        factors.append(entry)

    summary = {
        "score": score,
        "verdict": verdict,
        "target_verdict": target_v,
        "threshold": ceiling,
        "margin": round(score - ceiling, 4),
        "score_reduction_required": max(0.0, needed),
        "factors": factors,
    }
    if cheapest:
        summary["single_change_that_would_have_sufficed"] = cheapest
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". The threshold for " + target_v + " is " + str(ceiling) +
            ". The decision would have been " + target_v + " with " +
            cheapest["statement"] + ", all else unchanged.")
    else:
        summary["single_change_that_would_have_sufficed"] = None
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". No single factor, changed alone, would have reached " + target_v +
            " - the score was driven by several factors together.")
    return summary, contribs, cheapest


def _log(ctx, api_key, block_index, verdict, score, target):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO cf_requests(api_key,ts,block_index,verdict,score,target) VALUES(?,?,?,?,?,?)",
                            (api_key, time.time(), block_index, verdict, score, target))
        ctx["conn"].commit()


def _seal(ctx, api_key, summary, block_index):
    ts = time.time()
    ev = {"user_id": "cf:" + str(block_index or "adhoc"), "action": "counterfactual",
          "amount": 0, "country": "UK", "device_id": "counterfactual",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "COUNTERFACTUAL_SEALED", "score": 0,
           "cf_version": VERSION, "timestamp": ts,
           "explained_verdict": summary.get("verdict"),
           "explained_score": summary.get("score"),
           "target_verdict": summary.get("target_verdict"),
           "detail": summary.get("recourse_statement")}
    return ctx["seal"](ev, res, ts, api_key)


def _explain(ctx, api_key, data):
    s = _normalise(data)
    want = str(data.get("target_verdict", "")).strip().upper() or None
    summary, _c, _ch = _analyse(s, want)
    h, idx, seq = _seal(ctx, api_key, summary, None)
    _log(ctx, api_key, None, summary.get("verdict"), summary.get("score"), want)
    summary["inputs_used"] = s
    summary["audit_hash"] = h
    summary["block_index"] = idx
    summary["receipt_seq"] = seq
    summary["reproduce"] = "Weights are published. Re-run the arithmetic yourself - this result is not an approximation."
    return summary, 200


def _decision(ctx, api_key, data):
    try:
        bid = int(data.get("block", 0))
    except (TypeError, ValueError):
        return {"error": "block_required", "message": "Pass ?block=<block_index> from a sealed decision."}, 400
    if bid <= 0:
        return {"error": "block_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT event_json,result_json,ts FROM audit_log WHERE id=? AND api_key=?", (bid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_block", "block": bid}, 404
    try:
        ev = json.loads(row[0])
        res = json.loads(row[1])
    except Exception:
        return {"error": "block_unreadable"}, 500
    if str(res.get("decision", "")).endswith("_SEALED"):
        return {"error": "not_a_decision",
                "message": "That block is a notary event, not an engine decision."}, 400

    sig = res.get("signals") or res.get("applied") or {}
    s = _normalise({
        "trust": sig.get("trust", res.get("trust", 0.5)),
        "v60": sig.get("v60", 0), "v5m": sig.get("v5m", 0), "v1h": sig.get("v1h", 0),
        "amount": ev.get("amount", 0),
        "device_risk": ev.get("device_risk", 0),
        "anomaly": ev.get("anomaly", 0),
        "country_shift": sig.get("country_shift", False),
        "unsafe_country": sig.get("unsafe_country", False),
    })
    summary, _c, _ch = _analyse(s)
    sealed_score = res.get("score")
    if sealed_score is not None and abs(float(sealed_score) - summary["score"]) > 0.0002:
        summary["reconstruction_warning"] = (
            "Recomputed score " + str(summary["score"]) + " does not match the sealed score "
            + str(sealed_score) + ". The sealed record does not carry every signal value, "
            "so this explanation is indicative rather than exact. Pass the signals directly "
            "to /explain for an exact result.")
    else:
        summary["reconstruction"] = "exact - recomputed score matches the sealed score"
    summary["explained_block"] = bid
    summary["sealed_at"] = _iso(row[2])
    h, idx, seq = _seal(ctx, api_key, summary, bid)
    _log(ctx, api_key, bid, summary.get("verdict"), summary.get("score"), None)
    summary["audit_hash"] = h
    summary["block_index"] = idx
    return summary, 200


def _probing(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT ts,verdict,score FROM cf_requests WHERE api_key=? AND ts>? ORDER BY ts DESC", (api_key, t - 86400)).fetchall()
    if not rows:
        return {"requests_24h": 0,
                "note": "No counterfactual requests in the last 24 hours."}, 200
    scores = [r[2] for r in rows if r[2] is not None]
    near = len([x for x in scores if abs(x - CHALLENGE_MAX) < 0.02 or abs(x - ALLOW_MAX) < 0.02])
    out = {"requests_24h": len(rows),
           "last_request": _iso(rows[0][0]),
           "near_boundary_requests": near,
           "note": "Every counterfactual request is sealed. Boundary probing leaves a trail whether or not anyone is watching at the time."}
    if len(rows) >= 50:
        out["flag"] = str(len(rows)) + " counterfactual requests in 24 hours - consistent with systematic boundary mapping"
    if near >= 10:
        out["boundary_flag"] = str(near) + " requests sat within 0.02 of a threshold"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "explain":
            return _explain(ctx, api_key, data)
    else:
        if action == "decision":
            return _decision(ctx, api_key, data)
        if action == "probing":
            return _probing(ctx, api_key)
    return {"error": "unknown_action", "action": action,
            "available": ["POST explain", "GET decision?block=", "GET probing"]}, 404
