# Codebase — part 3 of 15

Contains:
- `modules/counterfactual.py`
- `modules/declare.py`
- `modules/demo.py`
- `modules/dsr.py`
- `modules/lineage.py`
- `modules/mutual.py`


## `modules/counterfactual.py`

397 lines, 16121 bytes

```python
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

```


## `modules/declare.py`

345 lines, 13493 bytes

```python
"""
Declaration notary - /x/declare/<action>

THE IDEA
--------
An operator uploads their own file saying what must always be true of their
decisions. It is sealed, versioned, and published. Every record is then tested
against it, and every violation is sealed.

WHY THIS ISN'T CIRCULAR
-----------------------
The obvious objection: if they write their own rules AND supply their own
data, checking one against the other proves nothing. They could declare
nothing and pass.

Two things stop that.

1. THE RULES COME FIRST. A declaration is sealed before the records it judges.
   You cannot write the rule after seeing the outcome, because the chain shows
   which came first. Retrofitting a standard to a result is exactly what this
   makes impossible.

2. YOU CANNOT QUIETLY WEAKEN IT. Every version is kept and sealed. If you
   published a strict rule in March and a loose one in September, both are
   permanent and the change is dated. Nobody can pretend the strict one never
   existed. Weakening your own standard becomes a visible act.

So the file does not prove you are honest. It converts your claims into
something that can be tested, and takes away your ability to move the goalposts
afterwards. An auditor reads the declaration, reads the violations, and reads
the version history. All three are sealed.

RULE FORMAT
-----------
    {"rules": [
      {"id": "no-silent-high-value",
       "describe": "Payments over 10000 are never auto-allowed",
       "when":    {"field": "amount",   "op": ">",  "value": 10000},
       "require": {"field": "decision", "op": "in", "value": ["CHALLENGE","BLOCK"]}}
    ]}

    ops: == != > >= < <= in not_in exists

HONEST LIMITS
-------------
- Weak rules prove weak things. A declaration that requires nothing passes
  everything. Publish it and let people judge the rules themselves.
- This tests what was sealed. A decision never recorded cannot violate a rule
  - gapless receipts are what cover that gap, not this.
- The operator still supplies the data. This is not an external audit. It is a
  published standard, sealed before the evidence, that they can be held to.

    POST /x/declare/publish     declaration file - sealed and versioned
    GET  /x/declare/current     the live declaration
    GET  /x/declare/history     every version ever published
    POST /x/declare/check       test sealed records against it, seal the result
    GET  /x/declare/violations  what failed, and when
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.0"
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "exists"}
MAX_RULES = 100

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declarations(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,version INTEGER,body TEXT,sha256 TEXT,published REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declare_checks(check_id TEXT PRIMARY KEY,api_key TEXT,decl_version INTEGER,ran REAL,tested INTEGER,passed INTEGER,violated INTEGER,detail TEXT,audit_hash TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dec_key ON declarations(api_key,version)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, ref, action, detail):
    ts = time.time()
    ev = {"user_id": "dec:" + ref, "action": "declare_" + action, "amount": 0,
          "country": "UK", "device_id": "declare", "anomaly": 0, "device_risk": 0}
    res = {"decision": "DECLARATION_SEALED", "score": 0, "declare_action": action,
           "declare_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _validate(body):
    if not isinstance(body, dict):
        return "declaration must be an object"
    rules = body.get("rules")
    if not isinstance(rules, list) or not rules:
        return "declaration needs a non-empty rules list"
    if len(rules) > MAX_RULES:
        return "too many rules (max " + str(MAX_RULES) + ")"
    seen = set()
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            return "rule " + str(i) + " is not an object"
        rid = str(r.get("id", "")).strip()
        if not rid:
            return "rule " + str(i) + " has no id"
        if rid in seen:
            return "duplicate rule id: " + rid
        seen.add(rid)
        req = r.get("require")
        if not isinstance(req, dict) or not req.get("field"):
            return "rule " + rid + " has no require.field"
        for part in ("when", "require"):
            c = r.get(part)
            if c is None:
                continue
            if not isinstance(c, dict):
                return "rule " + rid + ": " + part + " must be an object"
            if c.get("op", "==") not in OPS:
                return "rule " + rid + ": unknown op " + str(c.get("op"))
    return None


def _get(record, field):
    cur = record
    for part in str(field).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _test(cond, record):
    if not cond:
        return True
    val = _get(record, cond["field"])
    op = cond.get("op", "==")
    want = cond.get("value")
    if op == "exists":
        return (val is not None) == bool(want if want is not None else True)
    if val is None:
        return False
    try:
        if op == "==":
            return str(val).strip().lower() == str(want).strip().lower()
        if op == "!=":
            return str(val).strip().lower() != str(want).strip().lower()
        if op == "in":
            return str(val).strip().lower() in [str(x).strip().lower() for x in want]
        if op == "not_in":
            return str(val).strip().lower() not in [str(x).strip().lower() for x in want]
        v, w = float(val), float(want)
        if op == ">":
            return v > w
        if op == ">=":
            return v >= w
        if op == "<":
            return v < w
        if op == "<=":
            return v <= w
    except Exception:
        return False
    return False


def _current(ctx, api_key):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT version,body,sha256,published,audit_hash FROM declarations WHERE api_key=? ORDER BY version DESC LIMIT 1", (api_key,)).fetchone()


def _publish(ctx, api_key, data):
    body = data.get("declaration")
    if body is None:
        body = {k: v for k, v in data.items() if k != "declaration"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"error": "declaration_not_json"}, 400
    err = _validate(body)
    if err:
        return {"error": "invalid_declaration", "detail": err}, 400

    prev = _current(ctx, api_key)
    ver = (prev[0] + 1) if prev else 1
    sha = _sha(body)
    if prev and prev[2] == sha:
        return {"error": "unchanged",
                "message": "Identical to version " + str(prev[0]) + ". Nothing to publish."}, 400

    ref = "V" + str(ver)
    ids = [str(r.get("id")) for r in body["rules"]]
    detail = ("version=" + str(ver) + ";sha256=" + sha + ";rules=" + str(len(ids)) +
              ";ids=" + ",".join(ids[:40]) +
              (";replaces=" + prev[2] if prev else ";first_declaration=true"))
    h, idx, seq, ts = _seal_event(ctx, api_key, ref, "published", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO declarations(api_key,version,body,sha256,published,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
                            (api_key, ver, json.dumps(body), sha, ts, h, idx))
        ctx["conn"].commit()

    out = {"version": ver, "sha256": sha, "rules": len(ids), "rule_ids": ids,
           "published": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "Sealed. Every record from this point is judged against it, and this version cannot be removed."}
    if prev:
        out["replaces_version"] = prev[0]
        out["warning"] = "Version " + str(prev[0]) + " remains sealed and readable. Changes to your own standard are permanent and dated."
    return out, 200


def _current_view(ctx, api_key):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration",
                "message": "Nothing published yet."}, 404
    return {"version": row[0], "declaration": json.loads(row[1]),
            "sha256": row[2], "published": _iso(row[3]),
            "sealed": row[4]}, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT version,sha256,published,audit_hash,body FROM declarations WHERE api_key=? ORDER BY version ASC", (api_key,)).fetchall()
    if not rows:
        return {"count": 0, "versions": []}, 200
    out = []
    for v, sha, ts, ah, body in rows:
        try:
            n = len(json.loads(body).get("rules", []))
        except Exception:
            n = None
        out.append({"version": v, "sha256": sha, "published": _iso(ts),
                    "sealed": ah, "rules": n})
    return {"count": len(out), "versions": out,
            "note": "Every version ever published. Loosening a standard is visible here permanently."}, 200


def _check(ctx, api_key, data):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration"}, 404
    ver, body = row[0], json.loads(row[1])
    rules = body["rules"]

    try:
        limit = min(int(data.get("limit", 500)), 5000)
    except Exception:
        limit = 500

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT id,user_id,event_json,result_json,ts FROM audit_log WHERE api_key=? AND ts>=? ORDER BY id DESC LIMIT ?", (api_key, row[3], limit)).fetchall()

    violations = []
    tested = 0
    for bid, uid, ev_json, res_json, bts in recs:
        try:
            rec = {}
            rec.update(json.loads(ev_json))
            rec.update(json.loads(res_json))
        except Exception:
            continue
        if rec.get("decision", "").endswith("_SEALED"):
            continue
        tested += 1
        for r in rules:
            if not _test(r.get("when"), rec):
                continue
            if not _test(r.get("require"), rec):
                violations.append({"block_index": bid, "record_id": uid,
                                   "rule": r.get("id"),
                                   "describe": r.get("describe"),
                                   "at": _iso(bts)})

    ts = time.time()
    cid = "CHK-" + _sha(str(ts) + api_key)[:8].upper()
    detail = ("decl_version=" + str(ver) + ";tested=" + str(tested) +
              ";violated=" + str(len(violations)) +
              ";rules=" + ",".join(sorted({v["rule"] for v in violations})[:20]))
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "checked", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO declare_checks(check_id,api_key,decl_version,ran,tested,passed,violated,detail,audit_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                            (cid, api_key, ver, ts, tested, tested - len({v["block_index"] for v in violations}), len(violations), json.dumps(violations[:200]), h))
        ctx["conn"].commit()

    out = {"check_id": cid, "declaration_version": ver, "records_tested": tested,
           "violations": len(violations), "ran_at": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "note": "Result sealed whichever way it went."}
    if violations:
        out["failed_rules"] = sorted({v["rule"] for v in violations})
        out["detail"] = violations[:20]
        out["flag"] = str(len(violations)) + " record(s) violate your own published rules"
    return out, 200


def _violations(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT check_id,decl_version,ran,tested,violated,detail FROM declare_checks WHERE api_key=? ORDER BY ran DESC LIMIT 50", (api_key,)).fetchall()
    if not rows:
        return {"checks": 0, "note": "No checks run yet."}, 200
    latest = rows[0]
    try:
        detail = json.loads(latest[5])
    except Exception:
        detail = []
    return {"checks": len(rows),
            "latest": {"check_id": latest[0], "declaration_version": latest[1],
                       "ran": _iso(latest[2]), "tested": latest[3],
                       "violations": latest[4], "detail": detail[:50]},
            "history": [{"check_id": r[0], "ran": _iso(r[2]), "tested": r[3],
                         "violations": r[4]} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "publish":
            return _publish(ctx, api_key, data)
        if action == "check":
            return _check(ctx, api_key, data)
    else:
        if action == "current":
            return _current_view(ctx, api_key)
        if action == "history":
            return _history(ctx, api_key)
        if action == "violations":
            return _violations(ctx, api_key)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/demo.py`

358 lines, 15159 bytes

```python
"""
Public proving ground - /x/demo/<action>

WHY THIS EXISTS
---------------
Every page on this platform says "check it, don't trust it" and then asks for
an email address before anyone can check anything. That is the same bargain
every other vendor offers, dressed in better language.

This removes the bargain. No key, no account, no email. A visitor sends a
scenario, gets a real verdict from the live engine, and it is sealed into the
production chain - the same chain, the same sequence, covered by the same
external anchor. They get the block index back and can verify it themselves at
a public endpoint that has never heard of them.

The demonstration is not a simulation of the product. It IS the product, run
once, by a stranger, for free.

WHAT IS DELIBERATELY REAL
-------------------------
  - the scoring is the engine's own arithmetic, not a mock
  - the seal is a genuine block in the live chain
  - the counterfactual is computed by inverting the real function
  - the review flow really does withhold the verdict until commitment
  - the dwell time is really measured and really sealed

WHAT IS DELIBERATELY NOT REAL
-----------------------------
  - demo events do not touch any customer's trust history; user ids are
    namespaced to demo: and scored from a neutral starting trust
  - nothing about a visitor is recorded beyond what they typed

ABUSE
-----
Public routes are rate limited per client by the router. A visitor cannot
flood the chain, and the cost of a demo block is a few hundred bytes.

    POST /x/demo/govern   scenario -> verdict, seal, counterfactual
    POST /x/demo/review   open a review case, verdict withheld
    POST /x/demo/commit   commit a verdict, then see what the machine said
    GET  /x/demo/stats    how many people have tried it
"""

import json, math, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"

# No key required for any of these - that is the entire point.
PUBLIC = {("POST", "govern"), ("POST", "review"), ("POST", "commit"),
          ("GET", "stats"), ("GET", "")}

DEMO_KEY = "public_demo"
LN_CAP = math.log1p(10000)
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK", "FI", "IE", "NZ"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_cases(case_id TEXT PRIMARY KEY,opened REAL,material TEXT,machine_verdict TEXT,score REAL,committed REAL,human_verdict TEXT,dwell REAL)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_stats(k TEXT PRIMARY KEY,v INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _bump(ctx, k):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_stats(k,v) VALUES(?,1) ON CONFLICT(k) DO UPDATE SET v=v+1", (k,))
        ctx["conn"].commit()


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


def _signals(data):
    country = str(data.get("country", "UK")).strip().upper()[:4] or "UK"
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, min(_f(data, "v60"), 10000)),
        "v5m": max(0.0, min(_f(data, "v5m"), 10000)),
        "v1h": max(0.0, min(_f(data, "v1h"), 100000)),
        "amount": max(0.0, min(_f(data, "amount"), 10000000)),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country": country,
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": country not in SAFE,
    }


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


def _reasons(s):
    r = []
    if s["trust"] < 0.4:
        r.append("low_trust")
    if s["v60"] > 10:
        r.append("velocity_spike")
    if s["amount"] > 500:
        r.append("high_amount")
    if s["device_risk"] > 0.5:
        r.append("risky_device")
    if s["anomaly"] > 0.5:
        r.append("behaviour_anomaly")
    if s["country_shift"]:
        r.append("country_shift")
    if s["unsafe_country"]:
        r.append("unsafe_country")
    return r


def _verdict(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def _counterfactual(s, score, verdict):
    """Exact inversion. Returns the cheapest single change, or None."""
    if verdict == "ALLOW":
        return None, "Already the most permissive verdict."
    ceiling = 0.70 if verdict == "BLOCK" else 0.35
    target = "CHALLENGE" if verdict == "BLOCK" else "ALLOW"
    needed = score - ceiling + 0.0001

    contribs = [
        ("trust", (1 - s["trust"]) * 0.30),
        ("amount", min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15),
        ("v60", min(s["v60"] / 20.0, 1) * 0.15),
        ("v5m", min(s["v5m"] / 50.0, 1) * 0.10),
        ("v1h", min(s["v1h"] / 200.0, 1) * 0.10),
        ("device_risk", s["device_risk"] * 0.10),
        ("anomaly", s["anomaly"] * 0.10),
        ("country_shift", 0.10 if s["country_shift"] else 0.0),
        ("unsafe_country", 0.10 if s["unsafe_country"] else 0.0),
    ]
    contribs.sort(key=lambda kv: -kv[1])

    for name, c in contribs:
        if c <= 0 or c < needed:
            continue
        t = c - needed
        if name == "trust":
            v = 1 - (t / 0.30)
            if v <= 1.0:
                return {"factor": "trust", "required": round(_clamp(v), 3),
                        "was": round(s["trust"], 3)}, ("a trust score of "
                        + str(round(_clamp(v), 3)) + " instead of "
                        + str(round(s["trust"], 3)) + " would have made this "
                        + target)
        if name == "amount":
            v = math.expm1((t / 0.15) * LN_CAP)
            return {"factor": "amount", "required": round(v, 2),
                    "was": round(s["amount"], 2)}, ("an amount of "
                    + str(round(v, 2)) + " instead of " + str(round(s["amount"], 2))
                    + " would have made this " + target)
        if name in ("v60", "v5m", "v1h"):
            cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[name]
            v = (t / w) * cap
            lbl = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[name]
            return {"factor": name, "required": int(v), "was": int(s[name])}, (
                "a " + lbl + " velocity of " + str(int(v)) + " instead of "
                + str(int(s[name])) + " would have made this " + target)
        if name in ("device_risk", "anomaly"):
            v = t / 0.10
            lbl = "device risk" if name == "device_risk" else "behavioural anomaly"
            return {"factor": name, "required": round(_clamp(v), 3), "was": round(s[name], 3)}, (
                "a " + lbl + " of " + str(round(_clamp(v), 3)) + " instead of "
                + str(round(s[name], 3)) + " would have made this " + target)
        if name in ("country_shift", "unsafe_country"):
            lbl = ("no country change from the previous event" if name == "country_shift"
                   else "an event from a jurisdiction on the safe list")
            return {"factor": name, "required": 0, "was": 1}, (
                lbl + " would have made this " + target)
    return None, ("no single factor, changed alone, would have reached "
                  + target + " - several drove this together")


def _govern(ctx, data):
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    reasons = _reasons(s)
    cf, cf_text = _counterfactual(s, score, verdict)

    ts = time.time()
    uid = "demo:" + secrets.token_hex(3)
    ev = {"user_id": uid, "action": str(data.get("action", "payment"))[:40],
          "amount": s["amount"], "country": s["country"],
          "device_id": "demo", "anomaly": s["anomaly"],
          "device_risk": s["device_risk"]}
    res = {"decision": verdict, "score": score, "reasons": reasons,
           "demo": True, "demo_version": VERSION, "timestamp": ts,
           "signals": {k: s[k] for k in ("trust", "v60", "v5m", "v1h",
                                          "country_shift", "unsafe_country")},
           "note": "public demonstration - sealed into the live chain like any other decision"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)
    _bump(ctx, "govern")

    return {"decision": verdict, "score": score, "reasons": reasons,
            "sealed_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "counterfactual": cf,
            "counterfactual_statement": cf_text,
            "verify": {
                "this_block": "/api/inclusion?hash=" + h,
                "whole_chain": "/api/verify-chain",
                "external_anchor": "/api/anchor-status"},
            "what_just_happened": [
                "Your scenario was scored by the live engine, not a simulation.",
                "The verdict was sealed into the production chain as block " + str(idx) + ".",
                "That block is now covered by the next external timestamp.",
                "Nothing about you was recorded. No account, no email, no key.",
                "Verify any of it at the links above - they have never heard of you."]}, 200


def _review(ctx, data):
    """Open a review case. The verdict is computed and sealed - and withheld."""
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    cid = "DEMO-" + secrets.token_hex(4).upper()
    ts = time.time()
    material = {"action": str(data.get("action", "payment"))[:40],
                "amount": s["amount"], "country": s["country"],
                "60_second_velocity": int(s["v60"]),
                "5_minute_velocity": int(s["v5m"]),
                "device_risk": s["device_risk"],
                "behavioural_anomaly": s["anomaly"],
                "country_changed": s["country_shift"],
                "trust_history": round(s["trust"], 3)}
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_cases(case_id,opened,material,machine_verdict,score,committed,human_verdict,dwell) VALUES(?,?,?,?,?,NULL,NULL,NULL)",
                            (cid, ts, json.dumps(material), verdict, score))
        ctx["conn"].commit()
    _bump(ctx, "review_opened")
    return {"case_id": cid, "opened": _iso(ts), "material": material,
            "machine_verdict": "withheld until you commit",
            "your_options": ["allow", "challenge", "block"],
            "instruction": "Decide for yourself, then POST your verdict to /x/demo/commit with this case_id. The clock is running and your answer is sealed before ours is shown."}, 200


def _commit(ctx, data):
    cid = str(data.get("case_id", "")).strip().upper()
    hv = str(data.get("verdict", "")).strip().upper()
    if hv not in ("ALLOW", "CHALLENGE", "BLOCK"):
        return {"error": "verdict_required", "allowed": ["allow", "challenge", "block"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT opened,material,machine_verdict,score,committed FROM demo_cases WHERE case_id=?", (cid,)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_committed",
                "message": "You commit once. That is the point of it."}, 400

    ts = time.time()
    dwell = round(ts - row[0], 2)
    agreed = (hv == row[2])

    ev = {"user_id": "demo:" + cid, "action": "demo_oversight_commit",
          "amount": 0, "country": "UK", "device_id": "demo",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "DEMO_OVERSIGHT_SEALED", "score": 0, "demo": True,
           "timestamp": ts, "human_verdict": hv, "dwell_seconds": dwell,
           "detail": "human verdict sealed before the machine verdict was revealed"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE demo_cases SET committed=?,human_verdict=?,dwell=? WHERE case_id=?",
                            (ts, hv, dwell, cid))
        ctx["conn"].commit()
    _bump(ctx, "review_committed")

    out = {"case_id": cid, "your_verdict": hv,
           "machine_verdict": row[2], "machine_score": row[3],
           "agreed": agreed, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "what_just_happened": [
               "Your verdict was sealed as block " + str(idx) + " BEFORE this response revealed ours.",
               "The chain fixes that order permanently and it cannot be reversed.",
               "Your dwell time of " + str(dwell) + "s is part of the record.",
               "That is the difference between a reviewer who decided and one who agreed."]}
    if dwell < 2:
        out["flag"] = ("committed in " + str(dwell) + " seconds - on a real system that would sit "
                       "in your record permanently, and a pattern of it would be visible to an auditor")
    if agreed:
        out["note"] = "You agreed with the engine - but the chain shows you did so without having seen it."
    else:
        out["note"] = "You diverged from the engine. On a real system that is evidence of independent judgement."
    return out, 200


def _stats(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT k,v FROM demo_stats").fetchall()
        cases = ctx["conn"].execute("SELECT COUNT(*),AVG(dwell) FROM demo_cases WHERE committed IS NOT NULL").fetchone()
        fast = ctx["conn"].execute("SELECT COUNT(*) FROM demo_cases WHERE dwell IS NOT NULL AND dwell<2").fetchone()
    d = {k: v for k, v in rows}
    out = {"decisions_run": d.get("govern", 0),
           "review_cases_opened": d.get("review_opened", 0),
           "review_cases_committed": d.get("review_committed", 0)}
    if cases and cases[0]:
        out["median_dwell_seconds"] = round(cases[1] or 0, 2)
        out["committed_under_2_seconds"] = fast[0] if fast else 0
        out["note"] = ("Visitors who committed in under two seconds did not read the case. "
                       "On a real deployment that is exactly what the record would show.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "govern":
            return _govern(ctx, data)
        if action == "review":
            return _review(ctx, data)
        if action == "commit":
            return _commit(ctx, data)
    else:
        if action in ("", "stats"):
            return _stats(ctx)
    return {"error": "unknown_action", "action": action,
            "available": ["POST govern", "POST review", "POST commit", "GET stats"]}, 404

```


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/lineage.py`

528 lines, 24761 bytes

```python
#!/usr/bin/env python3
"""
modules/lineage.py  -  provenance that crosses company boundaries
=================================================================

WHERE EVERY AUDIT TRAIL STOPS
-----------------------------
At the edge of the company that wrote it.

A lender holds a score. The score came from a scoring supplier, which used
a model, which was trained on a data snapshot bought from someone else.
Four organisations, four audit trails, none of which reference each other.
Ask "what produced this outcome" and you get four separate answers and no
way to join them up.

Every framework written in the last three years assumes somebody can trace
an outcome across parties. Nobody can. Not because it is hard - because
each party's evidence is only worth anything inside that party's own
system, so joining them up would mean trusting whoever did the joining.

WHY THIS WORKS WHEN A SHARED DATABASE WOULD NOT
-----------------------------------------------
The obvious approach is a consortium: everyone writes to one ledger,
governed by someone. That fails on the first question anybody asks, which
is who runs it, and it never gets built.

This needs none of that, because the pieces already exist:

  A chain tip already commits to everything sealed beneath it.
  That tip is already handed to peers hourly and sealed into THEIR chains.
  Those chains are anchored externally and witnessed in turn.

So a receipt can already be walked up to a tip, and that tip already sits
inside chains its issuer does not control. The trust problem is solved
before lineage is even mentioned.

The only thing missing was the sideways link: a decision recording which
receipts fed it, and which chain each came from. That is what this module
adds. One field, and the graph composes itself.

Nobody opts into provenance. They opt into witnessing, which they already
want, and provenance falls out of it.

WHAT AN EDGE IS AND IS NOT
--------------------------
An edge is a sealed, dated, non-repudiable CLAIM by the declaring party
that these inputs fed that decision. Sealing does not make the claim true.
What it removes is the ability to revise it quietly afterwards, which is
the part that matters when an outcome is disputed a year later.

Every edge is itself a chain entry. So the provenance graph is covered by
the same completeness, consistency and witnessing guarantees as everything
else - you cannot delete an inconvenient edge without breaking the chain,
and you cannot add one after the fact without the timestamp showing it.

THE PART THAT IS WORTH MORE THAN THE TRACING
--------------------------------------------
    GET /x/lineage/impact?receipt=

Trace runs upstream: what produced this. Impact runs downstream: what did
this produce.

When a data provider retracts a snapshot, or a model version turns out to
be faulty, or an upstream decision is overturned, the question every
regulator asks is which outputs were affected. Today that answer takes
weeks of email and is never complete. Here it is a query, and it crosses
company boundaries, and the answer is itself provable.

That is corrective action under Article 20 turned from a fire drill into a
lookup.

VERIFICATION WITHOUT TRUSTING ANY PARTY IN THE CHAIN
----------------------------------------------------
This module never asserts that a remote hop is valid. It returns the exact
routes a third party should call to check each hop themselves - on our
chain and on everybody else's. An auditor verifies the whole graph without
trusting us, the supplier, or anyone in between.

HONEST LIMITS
-------------
  - An edge is a claim, sealed and dated. It is not proof the inputs were
    the real ones, only that this is what was declared and when.
  - A cross-chain hop can only be checked while the other party keeps
    their routes up. A dead peer leaves a stub in the graph - visible,
    which is the honest outcome, rather than silently resolved.
  - Declaring inputs is voluntary. A party that declares nothing is not
    caught out by this module; they are simply the point where somebody
    else's lineage goes dark, and their customer is the one who notices.
  - We record edges pointing at other chains. We do not fetch from them
    here - fetching is what /x/witness does, with its SSRF controls, and
    duplicating that machinery in a second place would be a mistake.

    POST /x/lineage/declare      record what fed a decision      (keyed)
    GET  /x/lineage/trace        walk upstream                    (public)
    GET  /x/lineage/impact       walk downstream                  (public)
    GET  /x/lineage/receipt      portable proof for an output     (public)
    GET  /x/lineage/spec         the format and how to check it   (public)
"""

import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Everything except declaring is open. The whole point is that a party
# three hops downstream - who has no relationship with us at all - can
# follow the graph and check it.
PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec")}

OUR_CHAIN_NAME = "aileash"
OUR_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS lineage_edge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "child_chain TEXT,child_receipt TEXT,"
                  "parent_chain TEXT,parent_receipt TEXT,parent_base TEXT,"
                  "role TEXT,note TEXT,declared REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_child "
                  "ON lineage_edge(child_receipt)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_parent "
                  "ON lineage_edge(parent_receipt)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lin_unique "
                  "ON lineage_edge(child_receipt,parent_chain,parent_receipt)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_chain(value):
    value = str(value or "").strip().lower()
    return value[:80] if value else ""


def _exists_locally(ctx, receipt):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1", (receipt,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _verification_plan(chain, receipt, base=None):
    """The exact calls a third party makes to check one hop themselves.

    We never tell anyone a hop is valid. We tell them how to find out
    without asking us again.
    """
    root = (base or OUR_BASE).rstrip("/") if chain != OUR_CHAIN_NAME else OUR_BASE
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % OUR_BASE,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (OUR_BASE, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


# ----------------------------------------------------------------------
# declare
# ----------------------------------------------------------------------

def _declare(ctx, api_key, data):
    child = str(data.get("receipt", data.get("child", ""))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(data.get("chain") or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs", "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared = []
    for item in inputs:
        if not isinstance(item, dict):
            return {"error": "bad_input", "message": "each input must be an object"}, 400
        parent = str(item.get("receipt", "")).strip().lower()
        if not HEX64.match(parent):
            return {"error": "bad_input_receipt",
                    "message": "every input needs a 64 character hex receipt"}, 400
        parent_chain = _clean_chain(item.get("chain") or OUR_CHAIN_NAME)
        if parent_chain == child_chain and parent == child:
            return {"error": "self_reference",
                    "message": "a decision cannot be its own input"}, 400
        role = str(item.get("role", "input")).strip().lower()
        if role not in ROLES:
            role = "other"
        base = str(item.get("base", item.get("url", "")) or "").strip()[:300]
        note = str(item.get("note", "") or "").strip()[:200]
        prepared.append((parent_chain, parent, base, role, note))

    now = time.time()
    summary = ";".join("%s/%s:%s" % (c, r[:12], role) for c, r, _b, role, _n in prepared)
    ev = {"user_id": "lin:" + child[:16], "action": "lineage_declared", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "LINEAGE_SEALED", "score": 0, "lineage_version": VERSION,
           "child_chain": child_chain, "child_receipt": child,
           "input_count": len(prepared),
           "detail": "child=%s;inputs=%s" % (child, summary)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    written, duplicates = 0, 0
    with ctx["lock"]:
        for parent_chain, parent, base, role, note in prepared:
            try:
                ctx["conn"].execute(
                    "INSERT INTO lineage_edge(api_key,child_chain,child_receipt,parent_chain,"
                    "parent_receipt,parent_base,role,note,declared,audit_hash,block_index) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (api_key, child_chain, child, parent_chain, parent, base or None,
                     role, note or None, now, audit_hash, block_index))
                written += 1
            except Exception:
                duplicates += 1
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (OUR_BASE, child)}, 200


# ----------------------------------------------------------------------
# walking the graph
# ----------------------------------------------------------------------

def _parents(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT parent_chain,parent_receipt,parent_base,role,note,declared,audit_hash "
            "FROM lineage_edge WHERE child_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _children(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT child_chain,child_receipt,role,declared,audit_hash "
            "FROM lineage_edge WHERE parent_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _walk(ctx, start, depth, upstream):
    """Breadth-first walk with cycle and size protection.

    Anything on a chain we do not hold locally becomes a frontier entry -
    named, with a verification plan, and explicitly not resolved by us.
    """
    seen = {start}
    nodes, edges, frontier = [], [], []
    queue = [(start, 0)]
    truncated = False

    while queue:
        receipt, level = queue.pop(0)
        if level >= depth or len(nodes) >= MAX_NODES:
            if queue or level >= depth:
                truncated = truncated or bool(queue)
            continue

        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)
        for row in rows:
            if upstream:
                chain, other, base, role, note, declared, sealed = row
            else:
                chain, other, role, declared, sealed = row
                base, note = None, None

            edges.append({
                "from": other if upstream else receipt,
                "to": receipt if upstream else other,
                "role": role, "note": note,
                "declared_at": _iso(declared),
                "declaration_sealed_as": sealed,
                "chain": chain,
            })

            local = (chain == OUR_CHAIN_NAME) and _exists_locally(ctx, other)
            if not local:
                if not any(f["receipt"] == other for f in frontier):
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated


def _depth_arg(data):
    try:
        depth = int(data.get("depth", MAX_DEPTH))
    except (TypeError, ValueError):
        depth = MAX_DEPTH
    return max(1, min(depth, MAX_DEPTH))


def _trace(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [],
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt),
            "how_to_verify_this": "Every node carries the routes to check it on its own chain. "
                                  "Nothing here asks you to take our word for a hop, including "
                                  "the hops on our own chain.",
            "what_an_edge_is": "A sealed, dated claim by the declaring party that these inputs "
                               "fed that decision. Sealing makes it non-repudiable, not true.",
            "frontier_note": "External entries are named but not resolved here. Run their "
                             "verification plans against their own hosts - that is what makes "
                             "the graph checkable without a shared database."}, 200


def _impact(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=False)
    affected = len(nodes)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": affected, "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "lineage_version": VERSION,
            "what_this_is_for": "If this input is retracted, wrong, or overturned, these are the "
                                "decisions that declared a dependency on it. This is the answer "
                                "to the first question asked after any upstream failure, and it "
                                "normally takes weeks of email to assemble incompletely.",
            "corrective_action": "The list is itself sealed and dated, so the scope of a recall "
                                 "can be shown to have been determined honestly rather than "
                                 "narrowed to suit.",
            "limits": "Only covers dependencies that were declared. A downstream party who "
                      "declared nothing does not appear - which is a fact about them rather "
                      "than a gap here."}, 200


# ----------------------------------------------------------------------
# the portable receipt - proof that travels with an output
# ----------------------------------------------------------------------

def _receipt(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "verify": _verification_plan(r[0], r[1], r[2])} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (OUR_BASE, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % OUR_BASE,
            "nothing_was_left_out": "%s/x/complete/periods" % OUR_BASE,
            "who_witnesses_us": "%s/x/witness/peers" % OUR_BASE,
            "our_current_tip": "%s/x/witness/tip" % OUR_BASE,
            "the_engine_reproduces": "%s/x/replay/spec" % OUR_BASE,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, receipt),
        },
        "offline_verifier": "aileash_verify.py - one file, no dependencies, no network. Save "
                            "this document and check it on your own machine, today or in four "
                            "years.",
        "what_you_can_establish": [
            "this decision is in a log that has not been rewritten",
            "that log is witnessed by parties we do not control",
            "the period it sits in declared its total before anyone asked",
            "the same inputs still produce the same verdict",
            "and what fed it, hop by hop, across every company involved",
        ],
        "what_you_cannot": "That the decision was right, or that the inputs were honest. "
                           "Cryptography establishes what happened and when. It does not "
                           "establish that what happened was correct, and anybody telling you "
                           "otherwise is selling something.",
        "send_this_on": "Attach it to the output it describes. Whoever receives it can verify "
                        "without an account, without contacting us, and without trusting anyone "
                        "in the chain including the sender.",
    }, 200


def _spec():
    return {
        "lineage_version": VERSION,
        "idea": "A decision records the receipts of its inputs and which chain each came from. "
                "Nothing else is needed, because a chain tip already commits to everything "
                "beneath it and is already witnessed by parties its operator does not control.",
        "why_no_consortium": "A shared ledger needs a governor and never gets built. This needs "
                             "no agreement between parties beyond each one sealing its own work "
                             "and publishing a tip.",
        "declare": {
            "route": "POST /x/lineage/declare (keyed)",
            "body": {"receipt": "<64 hex, the decision>",
                     "inputs": [{"chain": "<who it came from>", "receipt": "<64 hex>",
                                 "role": "one of %s" % ", ".join(ROLES),
                                 "base": "<their public https base, optional>"}]},
        },
        "roles": list(ROLES),
        "trace": "GET /x/lineage/trace?receipt= - upstream, what produced this",
        "impact": "GET /x/lineage/impact?receipt= - downstream, what this produced",
        "portable_receipt": "GET /x/lineage/receipt?receipt= - a document that travels with an "
                            "output and lets the recipient verify it independently",
        "verifying_a_hop": "Each node carries the routes to check it on its own chain: an "
                           "ancestry proof that the receipt is still there, a completeness "
                           "check that nothing was omitted from its period, and the witness "
                           "list showing who else holds that chain's tips.",
        "adopting_it": "Implement three public routes on your own system - a tip, an observe, "
                       "and an ancestry check - and declare your inputs. There is nothing to "
                       "join, nobody to ask, and no fee. If you can serve a tip, you are in.",
        "honest": "An edge is a dated, sealed claim about what fed a decision. It cannot be "
                  "quietly revised later. It was never proof that the claim was true, and this "
                  "module does not pretend otherwise.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "trace":
            return _trace(ctx, data)
        if action == "impact":
            return _impact(ctx, data)
        if action == "receipt":
            return _receipt(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "declare":
            return _declare(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "trace", "impact", "receipt"],
            "POST": ["declare (keyed)"]}, 404

```


## `modules/mutual.py`

447 lines, 15467 bytes

```python
#!/usr/bin/env python3
"""
modules/mutual.py  -  the outbound half of mutual witnessing
============================================================

Why this exists
---------------
modules/witness.py RECEIVES. Other chains hand us their tips and we seal
them. Nothing in the platform currently SENDS our tip anywhere, so right
now we witness other people and nobody witnesses us. This module is the
missing direction.

Drop it in as modules/mutual.py. The router picks it up automatically -
no edits to server.py.

Routes
------
  POST /x/mutual/push      send our current tip to every configured peer
  POST /x/mutual/pull      fetch every peer's tip and seal it into our chain
  POST /x/mutual/sync      pull then push (this is the one to schedule)
  GET  /x/mutual/peers     the configured peers and what happened last time
  GET  /x/mutual/status    last run, next run, whether the timer is alive

Important design note
---------------------
This module does not touch the database or import anything from server.py.
It talks HTTP to routes that are already public - ours and theirs. That
means it cannot corrupt anything, it works no matter how seal() changes,
and every action it takes is one an outsider could audit for themselves.

To read our own tip it calls our own public /x/witness/tip.
To seal a peer's tip it calls our own public /x/witness/observe, which is
already built to record exactly that. So a peer tip we pull is recorded by
the same code path as a peer tip that was pushed to us.

CONCURRENCY - read this before changing it
------------------------------------------
A sync cycle makes two kinds of call, and they are treated differently on
purpose.

  OUTBOUND to other people's hosts (reading their tip, pushing ours) runs
  in parallel. These are the slow ones - we are waiting on somebody else's
  server, and there is no reason to wait on them one at a time. Fifty peers
  now costs roughly what the slowest single peer costs, instead of the sum
  of all fifty.

  INBOUND to our own server (sealing what we pulled) stays sequential. Our
  own process is handling those requests, and firing a burst of them at
  ourselves while we are mid-cycle is asking for trouble - a queue behind a
  single replica at best. The sealing is fast and local anyway, so there is
  nothing to gain by parallelising it and a real risk in doing so.

So: fetch everything at once, then seal one at a time.

BEFORE THIS WORKS
-----------------
1. "observe" must be in the PUBLIC set of modules/witness.py. If it is not,
   this module gets a 401 from our own server, same as Red Flag AI Pro did.
2. After every deploy, the first /x/ request must be a GET - that is what
   installs the POST branch. Opening /x/mutual/peers in a browser does it.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------

# The router reads a set of (METHOD, action) tuples. Anything not listed
# here needs an API key - default is closed.
#
# peers and status are read-only. An outsider being able to see who we
# witness with, and whether it is actually running, is the entire point.
#
# push, pull and sync stay keyed - they cause outbound traffic and are not
# left open to anonymous callers.
PUBLIC = {("GET", "peers"), ("GET", "status")}


# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

# Our own public witness routes. Left as full URLs on purpose so this
# module never has to guess its own host.
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"
OUR_OBSERVE_URL = "https://sebbi.pro/x/witness/observe"

# The name we go by when we hand our tip to someone else.
OUR_CHAIN_NAME = "aileash"

# Everyone we witness with. Add a dict per chain.
#   name         what we file their tips under
#   tip_url      where we GET their current tip
#   observe_url  where we POST ours so they record it
PEERS = [
    {
        "name": "red-flag-ai-pro",
        "tip_url": "https://www.redflagaipro.com/api/witness/tip",
        "observe_url": "https://www.redflagaipro.com/api/witness/anchor",
    },
]

# Field names to send when pushing our tip. If a peer wants different
# names, give that peer its own "keys" dict and it will be used instead.
DEFAULT_PUSH_KEYS = {
    "chain": "chain",
    "tip": "tip",
    "count": "count",
    "ts": "ts",
    "url": "url",
}

# Where peers can read our tip, included in what we push.
OUR_PUBLIC_URL = "https://sebbi.pro/x/witness/tip"

# Background timer. Set ENABLED to False if you would rather drive it
# yourself by hitting /x/mutual/sync.
AUTO_SYNC_ENABLED = True
AUTO_SYNC_SECONDS = 3600

TIMEOUT_SECONDS = 20

# How many peers we talk to at once. Above this they queue, which is fine -
# it stops a large network spawning a thread per peer. Eight slow peers at
# 20s each still finishes in 20s; forty finishes in about a minute worst
# case, and only if every one of them times out.
MAX_PARALLEL_PEERS = 8

# ----------------------------------------------------------------------
# state - deliberately in memory only, this is not evidence
# ----------------------------------------------------------------------

_state = {
    "last_run": None,
    "last_result": None,
    "runs": 0,
    "timer_started": False,
}
_lock = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _reply(payload, status=200):
    """The router expects (payload, status) back from handle()."""
    return payload, status


def _in_parallel(function, items):
    """Run function over items concurrently, preserving input order.

    Used only for calls that leave our server. Anything hitting our own
    process goes through a plain loop instead - see the note at the top.
    """
    if not items:
        return []
    if len(items) == 1:
        return [function(items[0])]
    workers = min(len(items), MAX_PARALLEL_PEERS)
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="mutual-peer") as pool:
        return list(pool.map(function, items))


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------

def _http(url, payload=None):
    """POST if payload given, else GET. Returns (status, parsed_or_text)."""
    data = None
    headers = {"Accept": "application/json", "User-Agent": "aileash-mutual/1.1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        status = exc.code
    except urllib.error.URLError as exc:
        return 0, "unreachable: %s" % exc.reason
    except Exception as exc:
        return 0, "failed: %s" % exc
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


def _extract_tip(body):
    """Pull (tip, height) out of whatever shape a tip route returns."""
    if not isinstance(body, dict):
        return None, None
    tip = body.get("tip") or body.get("hash") or body.get("head")
    height = body.get("height", body.get("count", body.get("entries")))
    return tip, height


# ----------------------------------------------------------------------
# the two directions
# ----------------------------------------------------------------------

def our_tip():
    status, body = _http(OUR_TIP_URL)
    if status != 200:
        return None, None, "our own tip route answered %s: %s" % (status, str(body)[:200])
    tip, height = _extract_tip(body)
    if not tip:
        return None, None, "no tip field in our own reply: %s" % str(body)[:200]
    return tip, height, None


def push_one(peer, tip, height):
    """Hand our tip to one peer so they record it. Outbound only."""
    keys = peer.get("keys", DEFAULT_PUSH_KEYS)
    values = {
        "chain": OUR_CHAIN_NAME,
        "tip": tip,
        "count": height,
        "ts": _now(),
        "url": OUR_PUBLIC_URL,
    }
    payload = {keys.get(k, k): v for k, v in values.items()}
    status, body = _http(peer["observe_url"], payload)
    result = {
        "peer": peer["name"],
        "direction": "push",
        "url": peer["observe_url"],
        "http": status,
        "ok": 200 <= status < 300,
        "response": body if isinstance(body, (dict, list)) else str(body)[:300],
    }
    if status == 401 or status == 403:
        result["hint"] = "they want auth on that route, or it is not in their public set"
    elif status == 404:
        result["hint"] = "wrong path - check observe_url for this peer"
    elif status == 0:
        result["hint"] = "could not reach them at all"
    return result


def fetch_one(peer):
    """Read one peer's current tip. Outbound only - no sealing here.

    Returns a dict that either carries a tip ready to seal, or an error
    already shaped like a result so it can be returned to the caller as is.
    """
    status, body = _http(peer["tip_url"])
    if status != 200:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": body if isinstance(body, (dict, list)) else str(body)[:300],
            "hint": "could not read their tip",
        }

    tip, height = _extract_tip(body)
    if not tip:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": str(body)[:300],
            "hint": "no tip field in their reply - add the field name to _extract_tip",
        }

    return {
        "peer": peer["name"], "url": peer["tip_url"],
        "tip": tip, "height": height, "_failed": False,
        "fetched_at": time.time(),
    }


def seal_one(fetched):
    """Seal one already-fetched peer tip into our chain.

    Goes through our own public observe route so a tip we pulled is
    recorded by exactly the same code path as a tip somebody pushed to us.
    Called in a plain loop, never in parallel - this hits our own server.

    Field names must match what modules/witness.py reads out of the body:
    chain, tip, peer_ts, url. The url is what makes the observation
    checkable by a third party rather than taken on our word - it is the
    address we just fetched this tip from.
    """
    seal_status, seal_body = _http(OUR_OBSERVE_URL, {
        "chain": fetched["peer"],
        "tip": fetched["tip"],
        "peer_ts": fetched["fetched_at"],
        "url": fetched["url"],
    })

    out = {
        "peer": fetched["peer"],
        "direction": "pull",
        "their_tip": fetched["tip"],
        "their_height": fetched["height"],
        "sealed_http": seal_status,
        "ok": 200 <= seal_status < 300,
        "response": seal_body if isinstance(seal_body, (dict, list)) else str(seal_body)[:300],
    }
    if seal_status in (401, 403):
        out["hint"] = "our own observe route rejected us - check PUBLIC in modules/witness.py"
    return out


def do_push():
    tip, height, error = our_tip()
    if error:
        return {"ok": False, "error": error}

    # Outbound to everyone at once.
    results = _in_parallel(lambda peer: push_one(peer, tip, height), PEERS)

    return {
        "ok": True,
        "our_tip": tip,
        "our_height": height,
        "results": results,
    }


def do_pull():
    # Phase one: read every peer's tip at the same time. This is the slow
    # part and none of it touches us.
    fetched = _in_parallel(fetch_one, PEERS)

    # Phase two: seal what came back, one at a time, into our own chain.
    results = []
    for item in fetched:
        if item.get("_failed"):
            item.pop("_failed", None)
            results.append(item)
            continue
        results.append(seal_one(item))

    return {"ok": True, "results": results}


def do_sync():
    """Pull first, then push. That order matters: the tip we hand out then
    already contains the tips we just took in, so the two chains interlock
    rather than merely sitting alongside each other."""
    started = time.time()
    pulled = do_pull()
    pushed = do_push()
    result = {
        "ran_at": _now(),
        "took_seconds": round(time.time() - started, 2),
        "peers": len(PEERS),
        "pull": pulled,
        "push": pushed,
        "ok": bool(pulled.get("ok")) and bool(pushed.get("ok")),
    }
    with _lock:
        _state["last_run"] = result["ran_at"]
        _state["last_result"] = result
        _state["runs"] += 1
    return result


# ----------------------------------------------------------------------
# background timer
# ----------------------------------------------------------------------

def _loop():
    # Let the server finish coming up before the first run.
    time.sleep(45)
    while True:
        try:
            do_sync()
        except Exception:
            pass
        time.sleep(AUTO_SYNC_SECONDS)


def _start_timer():
    with _lock:
        if _state["timer_started"] or not AUTO_SYNC_ENABLED:
            return
        _state["timer_started"] = True
    thread = threading.Thread(target=_loop, name="mutual-sync", daemon=True)
    thread.start()


_start_timer()


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()

    if method == "GET":
        if action == "peers":
            return _reply({
                "chain": OUR_CHAIN_NAME,
                "peers": [
                    {"name": p["name"], "tip_url": p["tip_url"],
                     "observe_url": p["observe_url"]}
                    for p in PEERS
                ],
                "parallel_fetch": MAX_PARALLEL_PEERS,
                "note": "Witnessing is only mutual if both columns are live.",
            })
        if action == "status":
            with _lock:
                return _reply({
                    "auto_sync": AUTO_SYNC_ENABLED,
                    "interval_seconds": AUTO_SYNC_SECONDS,
                    "timer_running": _state["timer_started"],
                    "parallel_fetch": MAX_PARALLEL_PEERS,
                    "runs": _state["runs"],
                    "last_run": _state["last_run"],
                    "last_result": _state["last_result"],
                })

    if method == "POST":
        if action == "push":
            return _reply(do_push())
        if action == "pull":
            return _reply(do_pull())
        if action == "sync":
            return _reply(do_sync())

    return _reply({
        "error": "unknown action",
        "GET": ["peers", "status"],
        "POST": ["push", "pull", "sync"],
    }, 404)

```
