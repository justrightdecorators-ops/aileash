# Codebase — part 6 of 35

Contains:
- `modules/declare.py`
- `modules/demo.py`
- `modules/disclosure.py`
- `modules/dsr.py`
- `modules/fingerprint.py`
- `modules/genesis.py`
- `modules/grade.py`


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


## `modules/disclosure.py`

201 lines, 7648 bytes

```python
"""
disclosure.py v1.0.0 - the chain reset, put on the record inside the chain.

Lives at modules/disclosure.py and answers at https://sebbi.pro/x/disclosure/<action>.
All routes are public.

WHAT IT DOES
The audit chain restarted from genesis on 7 September 2026. Until now that
was said in messages and in route text, but not sealed. This module seals one
fixed statement about the reset into the chain, exactly once, and then serves
the block number so anyone can find it and recompute it.

The first visit to /status seals it. Every visit after that returns the same
block. Nothing is ever sealed twice, and the text cannot be changed by calling
the route - it is fixed in this file.

The statement is sealed under user_id "system_reset_disclosure", which is on
the public list in walk.py, so its full preimage is served at /x/walk and can be
recomputed by anyone.

Module contract: handle(method, action, data, api_key, ctx) -> (dict, status).
"""

import json
import threading
import time

VERSION = "1.0.0"
HOST = "https://sebbi.pro"
BASE = HOST + "/x/disclosure/"
USER_ID = "system_reset_disclosure"

RESET_DATE = "2026-09-07"

# If you still hold the final tip hash or block count of the chain as it stood
# before the reset, put them here before deploying. Left empty, the statement
# says plainly that they are not recorded in this disclosure.
PREVIOUS_CHAIN_FINAL_TIP = ""
PREVIOUS_CHAIN_FINAL_HEIGHT = ""

STATEMENT = (
    "On " + RESET_DATE + " the operator of sebbi.pro reset the audit chain and "
    "it restarted from genesis. Blocks sealed before that date are not part of "
    "this chain and cannot be verified against it. A block index quoted before "
    "that date belongs to the earlier chain; if the same number exists on this "
    "chain, it is a different block. Some records kept outside the chain from "
    "before the reset, including completeness period commitments, still quote "
    "block indexes from the earlier chain. This disclosure is sealed into the "
    "current chain so the break is on the record rather than something a "
    "verifier has to ask about."
)

_lock = threading.Lock()

PUBLIC = {("GET", "status"), ("GET", "statement"), ("GET", "spec")}


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reset_disclosure("
        "id INTEGER PRIMARY KEY CHECK (id = 1), block_index INTEGER, "
        "audit_hash TEXT, ts REAL, statement_json TEXT)")
    conn.commit()


def _stored(conn):
    r = conn.execute(
        "SELECT block_index, audit_hash, ts, statement_json FROM reset_disclosure "
        "WHERE id = 1").fetchone()
    if not r:
        return None
    try:
        body = json.loads(r[3])
    except Exception:
        body = {}
    return {"block_index": r[0], "audit_hash": r[1], "ts": r[2], "statement": body}


def _genesis_hash(conn):
    r = conn.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1").fetchone()
    return r[0] if r else None


def _links(rec):
    idx = rec["block_index"]
    return {
        "block": HOST + "/x/walk/block?index=" + str(idx),
        "verify_method": HOST + "/x/walk/spec",
        "statement": BASE + "statement",
    }


def _seal_once(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with _lock:
        with dblock:
            _ensure_table(conn)
            rec = _stored(conn)
            if rec:
                return rec, False
            genesis = _genesis_hash(conn)
        body = {
            "kind": "chain_reset_disclosure",
            "reset_date": RESET_DATE,
            "current_chain_genesis_hash": genesis,
            "current_chain_genesis_block_index": 1,
            "previous_chain_final_tip": PREVIOUS_CHAIN_FINAL_TIP or "not recorded in this disclosure",
            "previous_chain_final_height": PREVIOUS_CHAIN_FINAL_HEIGHT or "not recorded in this disclosure",
            "statement": STATEMENT,
            "disclosure_version": VERSION,
        }
        ts = time.time()
        event = {
            "user_id": USER_ID,
            "action": "chain_reset_disclosed",
            "amount": 0,
            "country": "UK",
            "device_id": "server",
            "anomaly": 0,
            "device_risk": 0,
        }
        result = dict(body)
        result["decision"] = "DISCLOSED"
        result["score"] = 0
        result["timestamp"] = ts
        # ctx seal takes its own lock - do not hold the db lock here.
        out = ctx["seal"](event, result, ts)
        if isinstance(out, (list, tuple)):
            h = out[0]
            idx = out[1] if len(out) > 1 else None
        elif isinstance(out, dict):
            h = out.get("audit_hash") or out.get("hash")
            idx = out.get("block_index") or out.get("index")
        else:
            h, idx = out, None
        with dblock:
            conn.execute(
                "INSERT OR IGNORE INTO reset_disclosure(id, block_index, audit_hash, ts, statement_json) "
                "VALUES (1, ?, ?, ?, ?)", (idx, h, ts, json.dumps(body)))
            conn.commit()
            rec = _stored(conn)
        return rec, True


def _spec():
    return {
        "module": "disclosure",
        "version": VERSION,
        "purpose": "Seals one fixed statement about the " + RESET_DATE + " chain reset "
                   "into the current chain, once, and serves where it is.",
        "routes": {
            "status": BASE + "status",
            "statement": BASE + "statement",
            "spec": BASE + "spec",
        },
        "behaviour": "The first call to status seals the statement. Every later call "
                     "returns the same block. The text is fixed in the module and "
                     "cannot be changed through any route.",
        "verify": "Open the block link in the response. Its preimage is served in full; "
                  "sha256 of it must equal audit_hash, and its prev_hash must equal the "
                  "block before. Method: " + HOST + "/x/walk/spec",
    }


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action == "spec":
            return _spec(), 200
        if method == "GET" and action == "status":
            rec, new = _seal_once(ctx)
            if not rec or rec.get("block_index") is None:
                return {"error": "seal_failed", "detail": "no block index returned"}, 500
            return {
                "module": "disclosure",
                "version": VERSION,
                "sealed": True,
                "sealed_just_now": new,
                "block_index": rec["block_index"],
                "audit_hash": rec["audit_hash"],
                "sealed_at": rec["ts"],
                "links": _links(rec),
                "statement": rec["statement"],
            }, 200
        if method == "GET" and action == "statement":
            conn, dblock = ctx["conn"], ctx["lock"]
            with dblock:
                _ensure_table(conn)
                rec = _stored(conn)
            if not rec:
                return {"sealed": False,
                        "note": "Not sealed yet. The first visit to " + BASE + "status seals it."}, 404
            return {"sealed": True, "block_index": rec["block_index"],
                    "audit_hash": rec["audit_hash"], "sealed_at": rec["ts"],
                    "links": _links(rec), "statement": rec["statement"]}, 200
        return {"error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": [], "spec": BASE + "spec"}, 404
    except Exception as e:
        return {"error": "disclosure_failed", "detail": str(e)[:300]}, 500

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


## `modules/fingerprint.py`

550 lines, 22358 bytes

```python
"""
modules/fingerprint.py  -  is somebody else running my scoring function?

THE IDEA
--------
The scoring engine is deterministic. Identical inputs give an identical score,
every time, forever. That is a compliance property - and it is also a
signature.

So: fire a fixed battery of carefully chosen inputs at any scoring endpoint,
fire the same battery at our own, and compare the two sets of numbers.

  identical across 24 varied vectors        it is this function
  identical shape, different scale          it is this function, reweighted
  same ordering, different curve            similar design, not this code
  unrelated                                 unrelated

WHY THE VECTORS ARE CHOSEN THE WAY THEY ARE
-------------------------------------------
Random inputs would only catch a straight copy. These are picked to probe the
specific design decisions in the function, because those are what survive
someone renaming things or nudging a weight:

  saturation points   velocity terms saturate at different counts per window,
                      so a burst and a grind separate. Vectors sit either side
                      of each saturation point.
  curve shape         amount is log-scaled, so small sums move the score far
                      more than large ones. Vectors walk that curve.
  normalisation       the continuous weights sum to 1.00 and the boolean
                      geography terms sit outside it. Vectors isolate that.
  asymmetry           trust contributes inversely and dominates. Vectors sweep
                      trust alone with everything else held flat.

A copy that renamed every field and changed nothing else matches exactly. A
copy that shifted the weights still tracks the shape, because the saturation
points and the log curve are structural rather than parametric.

WHAT IT CANNOT DO
-----------------
It only sees endpoints it can reach. A private product behind a key with no
free tier is invisible to this, and no amount of cleverness changes that.

It also proves similarity, never theft. Two people can converge on similar
weights honestly. What this produces is a dated, sealed measurement - which is
evidence, not a verdict, and the distinction matters if it is ever put in
front of anyone.

EVERY RUN IS SEALED
-------------------
The probe, the target, the vectors and the result all go into the chain. So a
comparison run today is provable as having been run today, rather than
assembled afterwards to fit an argument.

ROUTES  (all keyed - this is not a public toy)
----------------------------------------------
  POST /x/fingerprint/self      score the battery on our own engine
  POST /x/fingerprint/probe     url, plus optional field mapping. Compare.
  GET  /x/fingerprint/history   previous probes and their verdicts
  GET  /x/fingerprint/vectors   the battery itself
  GET  /x/fingerprint/spec      what a verdict means and does not mean
"""

import ipaddress
import json
import math
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = set()          # nothing public. deliberately.

FETCH_TIMEOUT = 10
MAX_BYTES = 200000
POLITE_DELAY = 0.4      # do not hammer somebody else's server
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# Where the live scorer might be found. Same approach as replay.py - look it
# up at runtime, never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]

_ready = False


# ----------------------------------------------------------------------
# the battery
# ----------------------------------------------------------------------
# Each vector is (label, signals). Signals use the engine's own internal
# names; the probe maps them to whatever the target calls things.

def _v(trust=0.5, v60=0, v5m=0, v1h=0, amount=0.0,
       device_risk=0.0, anomaly=0.0, country_shift=False, unsafe_country=False):
    return {"trust": trust, "v60": v60, "v5m": v5m, "v1h": v1h,
            "amount": amount, "device_risk": device_risk, "anomaly": anomaly,
            "country_shift": country_shift, "unsafe_country": unsafe_country}


VECTORS = [
    # --- trust sweep, everything else flat. Isolates the dominant term.
    ("trust-000", _v(trust=0.00)),
    ("trust-025", _v(trust=0.25)),
    ("trust-050", _v(trust=0.50)),
    ("trust-075", _v(trust=0.75)),
    ("trust-100", _v(trust=1.00)),

    # --- velocity: either side of each window's saturation point.
    ("v60-under",   _v(v60=10)),
    ("v60-at",      _v(v60=20)),
    ("v60-over",    _v(v60=40)),      # saturated: must equal v60-at
    ("v5m-under",   _v(v5m=25)),
    ("v5m-at",      _v(v5m=50)),
    ("v5m-over",    _v(v5m=100)),     # saturated
    ("v1h-under",   _v(v1h=100)),
    ("v1h-at",      _v(v1h=200)),
    ("v1h-over",    _v(v1h=400)),     # saturated

    # --- burst vs grind: same total actions, different distribution.
    ("burst",       _v(v60=20, v5m=20, v1h=20)),
    ("grind",       _v(v60=1,  v5m=8,  v1h=200)),

    # --- amount: walks the log curve. Small steps low, big steps high.
    ("amt-10",      _v(amount=10.0)),
    ("amt-100",     _v(amount=100.0)),
    ("amt-1000",    _v(amount=1000.0)),
    ("amt-10000",   _v(amount=10000.0)),
    ("amt-50000",   _v(amount=50000.0)),   # saturated

    # --- the boolean geography terms, isolated.
    ("geo-shift",   _v(country_shift=True)),
    ("geo-unsafe",  _v(unsafe_country=True)),
    ("geo-both",    _v(country_shift=True, unsafe_country=True)),

    # --- the other two continuous signals.
    ("dev-risk",    _v(device_risk=1.0)),
    ("anomaly",     _v(anomaly=1.0)),

    # --- everything at once. Tests the clamp and the normalisation.
    ("max-all",     _v(trust=0.0, v60=40, v5m=100, v1h=400, amount=50000.0,
                       device_risk=1.0, anomaly=1.0,
                       country_shift=True, unsafe_country=True)),
    ("min-all",     _v(trust=1.0)),
]

# Default mapping from our internal signal names to a target's request body.
DEFAULT_FIELDS = {
    "trust": "trust", "v60": "v60", "v5m": "v5m", "v1h": "v1h",
    "amount": "amount", "device_risk": "device_risk", "anomaly": "anomaly",
    "country_shift": "country_shift", "unsafe_country": "unsafe_country",
}
SCORE_KEYS = ["score", "risk_score", "value", "result", "rating", "confidence"]


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS fingerprint_probe("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,target TEXT,"
            "ran REAL,vectors INTEGER,answered INTEGER,exact INTEGER,"
            "verdict TEXT,correlation REAL,detail TEXT,audit_hash TEXT,"
            "block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_fp_target ON fingerprint_probe(target)")
        ctx["conn"].commit()
    _ready = True


# ----------------------------------------------------------------------
# our own engine
# ----------------------------------------------------------------------

def _find_scorer():
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in SCORER_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _score_locally():
    """Run the battery through the live engine. Returns (scores, source, error)."""
    fn, where = _find_scorer()
    if not fn:
        return None, None, ("could not find the scoring function at runtime - "
                            "add its name to SCORER_NAMES")
    out = []
    for label, signals in VECTORS:
        try:
            result = fn(dict(signals))
            score = result[0] if isinstance(result, (tuple, list)) else result
            out.append((label, round(float(score), 6)))
        except Exception as exc:
            return None, where, "scorer raised on %s: %s" % (label, exc)
    return out, where, None


# ----------------------------------------------------------------------
# reaching a target - same guards as witness.py
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    host = parts.hostname
    if not host:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _post(url, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json",
         "User-Agent": "aileash-fingerprint/%s" % VERSION}
    if headers:
        h.update(headers)
    request = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_BYTES)
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_BYTES)
        except Exception:
            raw = b""
        status = exc.code
    except Exception as exc:
        return 0, "unreachable (%s)" % type(exc).__name__
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return status, raw.decode("utf-8", "replace")[:300]


def _extract_score(payload, key_hint=None):
    """Pull a 0..1 style number out of whatever came back."""
    if isinstance(payload, (int, float)):
        return float(payload)
    if not isinstance(payload, dict):
        return None
    keys = ([key_hint] if key_hint else []) + SCORE_KEYS
    for k in keys:
        if k and k in payload:
            v = payload[k]
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).strip())
            except (TypeError, ValueError):
                pass
    # one level down
    for v in payload.values():
        if isinstance(v, dict):
            found = _extract_score(v, key_hint)
            if found is not None:
                return found
    return None


# ----------------------------------------------------------------------
# comparison
# ----------------------------------------------------------------------

def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def _rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = float(position)
    return ranks


def _compare(ours, theirs):
    """ours/theirs are lists of (label, score). theirs may contain None."""
    paired = [(l, o, t) for (l, o), (_, t) in zip(ours, theirs) if t is not None]
    answered = len(paired)
    if answered < 3:
        return {"verdict": "INCONCLUSIVE", "answered": answered,
                "why": "too few vectors came back to compare anything"}

    a = [p[1] for p in paired]
    b = [p[2] for p in paired]
    exact = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 1e-6)
    close = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 0.01)
    pearson = _pearson(a, b)
    spearman = _pearson(_rank(a), _rank(b))

    # a linear fit: are they our scores, scaled and shifted?
    ma, mb = sum(a) / answered, sum(b) / answered
    va = sum((x - ma) ** 2 for x in a)
    slope = (sum((a[i] - ma) * (b[i] - mb) for i in range(answered)) / va) if va > 0 else None
    intercept = (mb - slope * ma) if slope is not None else None
    residual = None
    if slope is not None:
        residual = max(abs(b[i] - (slope * a[i] + intercept)) for i in range(answered))

    if exact == answered:
        verdict = "IDENTICAL"
        why = ("Every vector matched to six decimal places. Two independently "
               "written scoring functions do not do this.")
    elif exact >= answered * 0.8:
        verdict = "IDENTICAL"
        why = ("%d of %d vectors matched exactly. The rest are consistent with "
               "a small local change on top of the same function." % (exact, answered))
    elif residual is not None and residual < 0.02 and pearson and pearson > 0.99:
        verdict = "DERIVED"
        why = ("Not identical, but every score fits ours scaled by %.3f and "
               "shifted by %.3f, within %.4f. That is this function reweighted, "
               "not a different one." % (slope, intercept, residual))
    elif spearman is not None and spearman > 0.95:
        verdict = "SAME SHAPE"
        why = ("Different numbers, but the same ordering across the battery "
               "(rank correlation %.3f). Consistent with the same design - the "
               "same saturation points and the same curve - rather than the "
               "same code." % spearman)
    elif pearson is not None and pearson > 0.8:
        verdict = "SIMILAR"
        why = ("Correlated (%.3f) but not tightly. Risk scorers tend to agree "
               "roughly on what looks risky, so this is weak on its own." % pearson)
    else:
        verdict = "UNRELATED"
        why = "No meaningful relationship to our scoring."

    return {
        "verdict": verdict, "why": why,
        "vectors": len(ours), "answered": answered,
        "exact_matches": exact, "within_0.01": close,
        "correlation": round(pearson, 4) if pearson is not None else None,
        "rank_correlation": round(spearman, 4) if spearman is not None else None,
        "best_fit": ({"scale": round(slope, 4), "shift": round(intercept, 4),
                      "worst_residual": round(residual, 5)}
                     if slope is not None else None),
        "per_vector": [{"vector": p[0], "ours": p[1], "theirs": p[2],
                        "delta": round(p[2] - p[1], 6)} for p in paired],
    }


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _self(ctx, api_key):
    scores, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503
    return {"source": where, "vectors": len(scores),
            "scores": [{"vector": l, "score": s} for l, s in scores],
            "note": ("This is the baseline every probe is compared against. It "
                     "reveals outputs, never weights.")}, 200


def _probe(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    ok, why = _url_allowed(url)
    if not ok:
        return {"error": "bad_target", "message": why}, 400

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    mapping = dict(DEFAULT_FIELDS)
    mapping.update({k: str(v) for k, v in fields.items() if isinstance(v, str)})
    score_key = data.get("score_key")
    extra = data.get("body") if isinstance(data.get("body"), dict) else {}
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    headers = {str(k)[:60]: str(v)[:300] for k, v in list(headers.items())[:8]}

    ours, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503

    theirs = []
    failures = []
    for label, signals in VECTORS:
        body = dict(extra)
        for internal, external in mapping.items():
            body[external] = signals[internal]
        status, payload = _post(url, body, headers)
        if status < 200 or status >= 300:
            theirs.append((label, None))
            if len(failures) < 5:
                failures.append({"vector": label, "http": status,
                                 "response": payload if isinstance(payload, (dict, list))
                                 else str(payload)[:200]})
        else:
            theirs.append((label, _extract_score(payload, score_key)))
        time.sleep(POLITE_DELAY)

    result = _compare(ours, theirs)
    ts = time.time()

    detail = ("target=" + url + ";verdict=" + result["verdict"] +
              ";exact=" + str(result.get("exact_matches", 0)) +
              "/" + str(result.get("answered", 0)))
    ev = {"user_id": "fp:" + urlparse(url).hostname, "action": "fingerprint_probe",
          "amount": 0, "country": "UK", "device_id": "fingerprint",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_" + result["verdict"].replace(" ", "_"),
           "score": 0, "fingerprint_version": VERSION, "target": url,
           "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO fingerprint_probe(api_key,target,ran,vectors,answered,"
            "exact,verdict,correlation,detail,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, ts, result.get("vectors"), result.get("answered"),
             result.get("exact_matches"), result["verdict"],
             result.get("correlation"), detail, h, idx))
        ctx["conn"].commit()

    out = dict(result)
    out.update({
        "target": url,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "what_this_is": ("A dated, sealed measurement of similarity. It is "
                         "evidence, not an accusation, and it does not "
                         "establish that anything was copied."),
    })
    if failures:
        out["failures"] = failures
        out["failure_note"] = ("Some vectors were rejected. If the target wants "
                               "different field names, pass a \"fields\" map and "
                               "run it again.")
    return out, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT target,ran,verdict,exact,answered,correlation,audit_hash,block_index"
            " FROM fingerprint_probe WHERE api_key=? ORDER BY id DESC LIMIT 100",
            (api_key,)).fetchall()
    return {"probes": [{
        "target": r[0],
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
        "verdict": r[2], "exact_matches": r[3], "answered": r[4],
        "correlation": r[5], "receipt": r[6], "block_index": r[7],
    } for r in rows], "count": len(rows)}, 200


def _vectors():
    return {"count": len(VECTORS),
            "vectors": [{"label": l, "signals": s} for l, s in VECTORS],
            "why_these": ("Chosen to sit either side of each saturation point, "
                          "to walk the amount curve, and to isolate each term. "
                          "Random inputs would only catch a straight copy.")}, 200


def _spec():
    return {
        "module": "fingerprint", "version": VERSION,
        "question_it_answers": "Is this endpoint running my scoring function?",
        "verdicts": {
            "IDENTICAL": "Every vector matches. Independently written functions do not do this.",
            "DERIVED": "Not identical, but every score is ours scaled and shifted. Reweighted, not rewritten.",
            "SAME SHAPE": "Different numbers, same ordering. Same design decisions, probably not the same code.",
            "SIMILAR": "Loosely correlated. Weak - risk scorers broadly agree on what looks risky.",
            "UNRELATED": "No meaningful relationship.",
            "INCONCLUSIVE": "Too few vectors came back.",
        },
        "limits": [
            "Only reaches endpoints it can reach. A private product with no free tier is invisible to this.",
            "Proves similarity, never theft. Two people can converge honestly.",
            "A target that rate limits, randomises or rounds heavily will read as INCONCLUSIVE rather than clean.",
        ],
        "every_run_is_sealed": ("The probe, the target and the result go into the "
                                "chain, so a comparison run today is provable as "
                                "having been run today."),
        "manners": "One request per vector with a %.1fs gap. It is a measurement, not a load test." % POLITE_DELAY,
    }, 200


def handle(method, action, data, api_key, ctx):
    # key first, before anything touches the database
    if not api_key:
        return {"error": "invalid_api_key"}, 401
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "self":
            return _self(ctx, api_key)
        if action == "probe":
            return _probe(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["self", "probe"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "history":
        return _history(ctx, api_key)
    if action == "vectors":
        return _vectors()
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "vectors"]}, 404

```


## `modules/genesis.py`

282 lines, 12662 bytes

```python
"""
Chain identity - /x/genesis/<action>

WHY THIS EXISTS
---------------
A receipt that does not say which chain state it belongs to is ambiguous the
moment a chain is ever reset, and this one was: on 7 September 2026, during
registry work, the chain was reset. Receipts issued before that date belong to
a state that does not continue forward. Nothing in those receipts says so, and
a peer holding one has no way to discover it from the receipt itself.

Philip Pinol (PRAXIS / ThePraesidium.ai) independently verified block 846 of
the prior state. That verification was sound for the state it was performed
against. It is not continuous with the chain running now, and saying so is
this module's job.

WHAT IT DOES
------------
Publishes the genesis hash of the current chain state and a short stable
identifier derived from it, so any party can pin their own records to a named
state rather than to a block number that may refer to two different things.

    chain_id = first 16 characters of the genesis block's audit hash

Deliberately a slice rather than a computation. Anyone can confirm the
identifier against the genesis hash by eye, in the response that carries both,
without running anything.

WHY IT IS A SEPARATE MODULE
---------------------------
Read-only, by construction. It opens the same database as the sealing code and
never writes to it: no inserts, no schema changes, no seal calls. A fault here
returns a 500 on this route and the chain carries on sealing, because the
module that seals does not import this one and does not know it exists.

That is not tidiness. Editing a file that writes an append-only chain in order
to add a reporting route is how the 7 September reset happened.

WHAT IT DOES NOT CLAIM
----------------------
- It does not assert when the reset occurred. It reports the sealed timestamp
  of block 1 as the database holds it, and states the reset date separately as
  a claim by the operator. If the two disagree, the disagreement is visible in
  the response rather than resolved quietly here.
- A chain_id identifies a state. It says nothing about whether the records in
  that state are true, complete, or externally anchored. Check /x/ots/status
  for anchoring and /api/verify-chain for internal validity.
- Two different deployments could in principle produce the same 16-character
  identifier. The full genesis hash is returned alongside it and is what
  should be pinned where collision matters.

    GET /x/genesis/chain    genesis hash, chain_id, height, current tip
    GET /x/genesis/status   is this module loaded and can it read the chain
    GET /x/genesis/spec     what the identifier is and how to pin it
"""

from datetime import datetime, timezone

VERSION = "1.0.1"

# Length of the genesis hash used as the chain identifier. Sixteen hex
# characters is 64 bits - long enough that two states will not collide by
# accident, short enough to quote in an email without wrapping.
CHAIN_ID_LEN = 16

# Routes that need no API key. A third party must be able to establish which
# chain state a receipt belongs to without holding an account, or the receipt
# is only checkable by customers.
PUBLIC = {("GET", "chain"), ("GET", "status"), ("GET", "spec")}

# ----------------------------------------------------------------------
# everything a reader sees
# ----------------------------------------------------------------------

# The reset moment, stated to the second and in UTC, because a date alone was
# ambiguous: the chain was reset just after midnight UK time, so the calendar
# date differs between UTC and local and the route appeared to contradict
# itself. Stated precisely rather than rounded to whichever date reads better.
RESET_AT_UTC = "2026-09-06T23:11:12Z"

RESET_RECORD = {
    "occurred": RESET_AT_UTC,
    "occurred_local": (
        "00:11 on 7 September 2026, UK time. The same moment. Recorded in UTC "
        "above because a calendar date is ambiguous within an hour of "
        "midnight and this one falls inside that hour."),
    "reason": "chain reset during registry work",
    "effect": (
        "Receipts, block indexes and audit hashes issued before this date "
        "belong to a prior chain state. That state does not continue forward "
        "into the chain running now. A block index from before the reset and "
        "a block index from after it are not comparable and do not refer to "
        "the same sequence."),
    "prior_verification": (
        "Block 846 of the prior state was independently verified by Philip "
        "Pinol (PRAXIS / ThePraesidium.ai). That verification was sound for "
        "the state it was performed against. It is not evidence about the "
        "current state, and neither party describes it as continuous with it."),
    "what_was_not_lost": (
        "The prior state's records were sealed under the rules in force at "
        "the time and were valid under them. What changed is that the "
        "sequence does not extend. Nothing here claims the earlier records "
        "were wrong."),
    "disclosed_because": (
        "A peer holding a pre-reset receipt cannot discover any of this from "
        "the receipt itself. Published rather than left for someone to find "
        "when their records fail to reconcile."),
}

VOCABULARY = {
    "chain_id": (
        "A short stable identifier for one chain state, being the first %d "
        "characters of that state's genesis block hash. Pin your records to "
        "this rather than to a block index. If a chain is ever reset, the "
        "chain_id changes and the mismatch is visible immediately; a block "
        "index silently refers to a different thing." % CHAIN_ID_LEN),
    "genesis_hash": (
        "The audit hash of block 1 of the current chain state. This is the "
        "value to pin where a 16-character identifier is not enough. It does "
        "not change for the life of the state."),
    "genesis_sealed_at": (
        "The timestamp stored against block 1, as the database holds it. It "
        "is this deployment's own clock at the moment that block was written "
        "and is not evidence of when anything happened. The external "
        "timestamp proofs at /x/ots/status are the answer to that question."),
    "height": (
        "How many blocks the current state holds. Counts from block 1 of this "
        "state, not from the beginning of any prior state."),
    "current_tip": (
        "The audit hash of the most recent block. Changes constantly. "
        "Included so one call establishes the whole identity of the state; "
        "/x/witness/tip is the route to poll."),
}


def _iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _first_block(ctx):
    """Block 1 of the current state. Read-only."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id ASC LIMIT 1"
        ).fetchone()


def _last_block(ctx):
    """Current tip. Read-only. Same query witness.py uses, deliberately."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _chain(ctx):
    first = _first_block(ctx)
    if not first:
        return {"error": "no_genesis",
                "message": ("The audit chain holds no blocks, so there is no "
                            "genesis to report. This is an empty chain rather "
                            "than a fault."),
                "genesis_version": VERSION}, 404

    genesis_hash = str(first[0])
    chain_id = genesis_hash[:CHAIN_ID_LEN]
    last = _last_block(ctx)

    out = {
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "genesis_block_index": first[2],
        "genesis_sealed_at": _iso(first[1]),
        "height": last[2] if last else first[2],
        "current_tip": last[0] if last else genesis_hash,
        "current_sealed_at": _iso(last[1]) if last else _iso(first[1]),
        "genesis_version": VERSION,
        "reset_record": RESET_RECORD,
        "vocabulary": VOCABULARY,
        "how_to_pin": (
            "Record chain_id alongside every receipt you hold from this "
            "deployment. When you later check a receipt, read this route "
            "first: if chain_id has changed, your receipt belongs to a state "
            "that no longer continues and no block index in it is comparable "
            "to a current one."),
        "verify_the_identifier": (
            "chain_id is the first %d characters of genesis_hash. Both are in "
            "this response. Check it by eye - nothing needs to be run."
            % CHAIN_ID_LEN),
        "this_does_not_establish": (
            "That the records in this state are true, complete, or externally "
            "anchored. /api/verify-chain checks the chain end to end. "
            "/x/ots/status shows the state of each external timestamp proof."),
    }

    # State rather than assert. The stated reset moment and the sealed
    # timestamp of block 1 should be the same event. If they are not, the
    # reader sees the disagreement here rather than being told a tidy story.
    #
    # Compared to the minute, in UTC, on both sides. Comparing calendar dates
    # was wrong: this chain was reset at 23:11 UTC, which is the following day
    # locally, so a date comparison reported a contradiction that did not
    # exist. A route that cries wolf about its own honesty is worse than one
    # that says nothing.
    sealed = out["genesis_sealed_at"]
    if sealed and sealed[:16] != RESET_AT_UTC[:16]:
        out["date_note"] = (
            "The sealed timestamp of block 1 (%s) does not match the reset "
            "moment stated in reset_record (%s). Both values are reported as "
            "they are. Reconcile them against the external timestamp proofs "
            "rather than against either party's account."
            % (sealed, RESET_AT_UTC))

    return out, 200


def _status(ctx):
    """Arming route. Says whether this module loaded and can read the chain."""
    readable = False
    detail = None
    try:
        readable = _first_block(ctx) is not None
        if not readable:
            detail = "chain is readable and holds no blocks"
    except Exception as exc:
        detail = "could not read the audit chain (%s)" % type(exc).__name__

    return {"module": "genesis",
            "version": VERSION,
            "chain_readable": readable,
            "detail": detail,
            "writes": "none - this module never writes to the database",
            "routes": sorted(a for _m, a in PUBLIC),
            "genesis_version": VERSION}, 200


def _spec():
    return {"module": "genesis",
            "genesis_version": VERSION,
            "purpose": (
                "Publishes which chain state this deployment is running, so a "
                "receipt can be pinned to a named state rather than to a "
                "block index that may refer to two different sequences."),
            "chain_id_rule": (
                "The first %d characters of the genesis block's audit hash. "
                "Not a hash of a hash, not a derived key - a slice, so it can "
                "be checked by eye against the genesis hash returned beside "
                "it." % CHAIN_ID_LEN),
            "routes": {
                "GET /x/genesis/chain": "chain_id, genesis hash, height, tip",
                "GET /x/genesis/status": "module loaded, chain readable",
                "GET /x/genesis/spec": "this document",
            },
            "vocabulary": VOCABULARY,
            "reset_record": RESET_RECORD,
            "read_only": (
                "This module performs no writes of any kind. It opens the "
                "same database the sealing code uses and issues two SELECT "
                "statements. A fault here cannot affect the chain."),
            "related": {
                "/x/witness/tip": "current tip, for peers to record",
                "/api/verify-chain": "checks this chain end to end",
                "/x/ots/status": "state of each external timestamp proof",
            }}, 200


def handle(method, action, data, api_key, ctx):
    if method == "GET":
        if action == "chain":
            return _chain(ctx)
        if action == "status":
            return _status(ctx)
        if action == "spec":
            return _spec()
    return {"error": "unknown_action", "action": action,
            "routes": sorted(a for _m, a in PUBLIC)}, 404

```


## `modules/grade.py`

674 lines, 26478 bytes

```python
"""
modules/grade.py  v1.0.0  —  public transparency-file scanner

WHAT IT DOES
------------
Fetches a domain's public convention files and reports, per file, what was
actually found: served or not, parses or not, and the specific fields present.
Nothing else.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not issue a letter grade, a score, or a verdict, and the words
"compliant" and "non-compliant" appear nowhere in its output.

The reason is not squeamishness. Half of these files are conventions rather
than requirements. No law anywhere obliges a company to serve ai.txt,
comply.txt, llms.txt or an AI-safety file, and two of those are conventions
this operator helped write. Scoring the market against your own file format
and publishing a letter is marking other people's homework with your own
marking scheme. So this reports observations and lets the reader conclude.

Absence is reported as absence. That is a fact about a file. It is not a
finding about a company, and this module never converts one into the other.

THE CLOAKING CHECK WAS REMOVED
------------------------------
An earlier version compared homepage byte-length under two user agents and
scored a >10% difference as cloaking. Any page with a clock, a nonce or a
rotating banner fails that; real cloaking returning a similar-length page
passes it. It measured noise and reported it as a signal, so it is gone
rather than reworded.

ROUTES
------
  POST /x/grade/scan          KEYED   scan a domain, seal the result
  GET  /x/grade/report        public  ?domain= — the last scan of that domain
  GET  /x/grade/list          public  domains scanned, most recent first
  GET  /x/grade/spec          public  what each check means
  GET  /grade-badge?domain=   public  SVG, served from cache ONLY

BADGE BEHAVIOUR THAT MATTERS
----------------------------
The badge never triggers a fetch of the target. An earlier version re-ran
every check on every image load, so embedding the badge on a busy page would
have pointed sustained unsolicited traffic at somebody else's server from
this IP. The badge now renders from the stored scan or says "not scanned".

SAFETY
------
https only, port 443, DNS resolved and checked against private, loopback,
link-local, multicast and reserved ranges before any request, redirects not
followed, 8s timeout, 256KB cap per file. Known limit, stated rather than
hidden: resolve-then-connect leaves a DNS rebinding window, the same gap
witness.py has.

/robots.txt is read first and its Disallow rules for * are honoured. A
scanner that ignores robots while grading other people on transparency
would be a poor advertisement for the point being made.
"""

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0.0"

PUBLIC = {("GET", "report"), ("GET", "list"), ("GET", "spec"), ("GET", "")}

PAGE_PATHS = ("/grade-badge",)

UA = "AILeash-Transparency-Scan/1.0 (+https://sebbi.pro/x/grade/spec)"
TIMEOUT = 8
MAX_BYTES = 262144
CACHE_TTL = 3600

# Files that are genuine public-web standards with an RFC or a long-standing
# convention behind them. Absence here is still not a legal finding, but the
# expectation is at least widely shared.
STANDARDS = [
    ("security_txt", "/.well-known/security.txt", "RFC 9116 security contact"),
    ("robots_txt", "/robots.txt", "crawler directives"),
    ("sitemap_xml", "/sitemap.xml", "site index"),
]

# Files that are emerging AI-transparency conventions. Reported as adoption
# facts, never scored, because nobody is obliged to serve any of them.
CONVENTIONS = [
    ("ai_txt", "/.well-known/ai.txt", "AI system manifest"),
    ("ai_txt_root", "/ai.txt", "AI system manifest at root"),
    ("comply_txt", "/.well-known/comply.txt", "compliance index"),
    ("llms_txt", "/llms.txt", "guidance for language models"),
    ("ai_safety_txt", "/.well-known/ai-safety.txt", "AI-safety declaration"),
]

_patched = [False]
_ready = [False]
_cache = {}


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS grade_scan("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,domain TEXT,scanned REAL,"
            "findings TEXT,standards_served INTEGER,conventions_served INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_domain ON grade_scan(domain)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_hash ON grade_scan(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


# ----------------------------------------------------------------------
# safety
# ----------------------------------------------------------------------

def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0].split("?")[0].strip().rstrip(".")
    if "@" in d or ":" in d or " " in d:
        return None
    if not d or "." not in d or len(d) > 253:
        return None
    for ch in d:
        if not (ch.isalnum() or ch in ".-"):
            return None
    return d


def _private(ip):
    parts = ip.split(".")
    if len(parts) == 4:
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            return True
        if a == 10 or a == 127 or a == 0:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 169 and b == 254:
            return True
        if a == 100 and 64 <= b <= 127:
            return True
        if a >= 224:
            return True
        return False
    low = ip.lower()
    if low in ("::1", "::", "") or low.startswith(("fc", "fd", "fe80", "::ffff:")):
        return True
    return False


def _resolvable(domain):
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "dns_failed: " + type(exc).__name__
    for info in infos:
        ip = info[4][0]
        if _private(ip):
            return False, "resolves_to_non_public_address"
    return True, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url):
    """One request. Returns (status, text, note). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            text = raw[:MAX_BYTES].decode("utf-8", errors="replace")
            return resp.status, text, ("truncated" if truncated else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None, None
    except Exception as exc:
        return None, None, type(exc).__name__


# ----------------------------------------------------------------------
# parsing — every check states exactly what it looked at
# ----------------------------------------------------------------------

def _fields(text):
    """Key: value lines, lowercased keys. Comments and blanks ignored."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        if k and k not in out:
            out[k] = v.strip()
    return out


def _check_security(text):
    f = _fields(text)
    return {
        "parses_as_fields": bool(f),
        "has_contact": "contact" in f,
        "has_expires": "expires" in f,
        "expires_value": f.get("expires"),
        "note": ("RFC 9116 requires Contact and Expires. Both presence checks "
                 "above are literal: the field is there or it is not. Whether "
                 "the contact works is not tested."),
    }


def _check_robots(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    directives = [l for l in lines if ":" in l and not l.startswith("#")]
    return {
        "non_empty": bool(lines),
        "directive_lines": len(directives),
        "note": "Presence and shape only. The rules themselves are not judged.",
    }


def _check_sitemap(text):
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(text or "")
        return {"parses_as_xml": True,
                "note": "Parsed as XML. Contents and freshness are not checked."}
    except Exception as exc:
        return {"parses_as_xml": False, "parse_error": type(exc).__name__,
                "note": "Served but did not parse as XML."}


def _check_ai_safety(text):
    """The old version passed if the file contained 'ai-safe:' and the word
    'true' anywhere in it, so 'AI-Safe: false' with 'true' elsewhere passed.
    This reads the field's own value and reports it verbatim."""
    f = _fields(text)
    val = f.get("ai-safe")
    return {
        "has_ai_safe_field": val is not None,
        "ai_safe_value": val,
        "declared_safe": (val.strip().lower() == "true") if val else None,
        "note": ("This reports what the domain declares about itself. A "
                 "self-declaration is not a verification, and nothing here "
                 "checks whether the declaration is true."),
    }


def _check_manifest(text):
    f = _fields(text)
    interesting = ["standard", "domain", "chain-head", "chain-tip-url", "witness-tip",
                   "verify-chain", "consistency-proof", "self-check",
                   "security-contact", "contact", "governance-engine"]
    return {
        "parses_as_fields": bool(f),
        "field_count": len(f),
        "fields_present": [k for k in interesting if k in f],
        "declares_standard": f.get("standard"),
        "note": ("Fields are reported as served. Nothing here follows the URLs "
                 "they contain or verifies any chain they point at."),
    }


def _check_present(text):
    return {"non_empty": bool(text and text.strip()),
            "bytes": len(text or ""),
            "note": "Presence and size only."}


PARSERS = {
    "security_txt": _check_security,
    "robots_txt": _check_robots,
    "sitemap_xml": _check_sitemap,
    "ai_safety_txt": _check_ai_safety,
    "ai_txt": _check_manifest,
    "ai_txt_root": _check_manifest,
    "comply_txt": _check_manifest,
    "llms_txt": _check_present,
}


def _disallowed(robots_text):
    """Paths Disallowed for * in robots.txt. Honoured for every other fetch."""
    blocked = []
    applies = False
    for line in (robots_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            applies = (v == "*")
        elif k == "disallow" and applies and v:
            blocked.append(v)
    return blocked


def _blocked(path, rules):
    for rule in rules:
        if rule == "/" or path.startswith(rule):
            return True
    return False


# ----------------------------------------------------------------------
# the scan
# ----------------------------------------------------------------------

def _scan(domain):
    base = "https://" + domain
    findings = {}

    status, robots_text, note = _get(base + "/robots.txt")
    rules = _disallowed(robots_text) if status == 200 else []
    findings["robots_txt"] = {
        "path": "/robots.txt", "http_status": status,
        "served": status == 200, "transport_note": note,
        "detail": _check_robots(robots_text) if status == 200 else None,
        "kind": "standard", "description": "crawler directives",
    }

    for key, path, desc in STANDARDS + CONVENTIONS:
        if key == "robots_txt":
            continue
        if _blocked(path, rules):
            findings[key] = {
                "path": path, "served": None, "http_status": None,
                "skipped": "disallowed_by_robots_txt",
                "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
                "description": desc,
                "note": ("This domain's robots.txt disallows it, so it was not "
                         "requested. Not requested is not the same as absent."),
            }
            continue
        st, text, tnote = _get(base + path)
        served = (st == 200 and bool(text and text.strip()))
        findings[key] = {
            "path": path, "http_status": st, "served": served,
            "transport_note": tnote,
            "detail": PARSERS[key](text) if served else None,
            "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
            "description": desc,
        }

    std_keys = [k for k, _, _ in STANDARDS]
    conv_keys = [k for k, _, _ in CONVENTIONS]
    std_served = sum(1 for k in std_keys if findings.get(k, {}).get("served"))
    conv_served = sum(1 for k in conv_keys if findings.get(k, {}).get("served"))

    return findings, std_served, conv_served


def _summary(domain, findings, std, conv, scanned, receipt=None, block=None):
    return {
        "domain": domain,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(scanned)),
        "standards_served": "%d of %d" % (std, len(STANDARDS)),
        "conventions_served": "%d of %d" % (conv, len(CONVENTIONS)),
        "findings": findings,
        "receipt": receipt,
        "block_index": block,
        "what_this_is": (
            "A record of which public files this domain served at the time of "
            "the scan, and what each one contained. Every check is named and "
            "every result is what the fetch returned."),
        "what_this_is_not": (
            "Not a grade, not a score, and not a statement about whether this "
            "organisation complies with anything. No law requires any of the "
            "files above. Absence of a file is absence of a file."),
        "conventions_disclaimer": (
            "ai.txt and comply.txt are conventions sebbi.pro publishes and helped "
            "shape. A domain not serving them has declined nothing and broken "
            "nothing - it has simply not adopted a format that is not a standard."),
        "if_you_are_the_domain_owner": (
            "This scan requested public files over https and followed your "
            "robots.txt. Nothing was crawled beyond the paths listed. The scan "
            "is sealed, so exactly what was fetched and when is on record and "
            "can be produced. Contact justrightdecorators@gmail.com to have a "
            "scan removed from the public list."),
    }


# ----------------------------------------------------------------------
# badge — cache only, never triggers a fetch of the target
# ----------------------------------------------------------------------

def _badge_svg(label, value, colour):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="20" '
        'role="img" aria-label="%s %s">'
        '<rect width="176" height="20" fill="#0a0f1e"/>'
        '<rect x="176" width="84" height="20" fill="%s"/>'
        '<text x="88" y="14" fill="#fff" font-family="Verdana,sans-serif" '
        'font-size="10" text-anchor="middle">%s</text>'
        '<text x="218" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" '
        'font-size="10" font-weight="bold" text-anchor="middle">%s</text>'
        '</svg>' % (label, value, colour, label, value))


def _srv():
    import sys
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s, ctx):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_grade_patched", False):
        _patched[0] = True
        return "already installed"

    conn, lock = ctx["conn"], ctx["lock"]
    original = H.do_GET

    def do_GET(self):
        try:
            u = urlparse(self.path)
            p = u.path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            domain = ""
            try:
                q = dict(pair.split("=", 1) for pair in (u.query or "").split("&") if "=" in pair)
                domain = _clean_domain(q.get("domain", "")) or ""
            except Exception:
                domain = ""
            label = "transparency files"
            value, colour = "not scanned", "#6b6353"
            if domain:
                try:
                    with lock:
                        row = conn.execute(
                            "SELECT standards_served,conventions_served FROM grade_scan "
                            "WHERE domain=? ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
                    if row:
                        value = "%d/%d std · %d/%d conv" % (
                            row[0], len(STANDARDS), row[1], len(CONVENTIONS))
                        colour = "#7fe3b0" if row[0] == len(STANDARDS) else "#c9a84c"
                except Exception:
                    pass
            body = _badge_svg(label, value, colour).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._grade_patched = True
    _patched[0] = True
    print("GRADE: /grade-badge installed at runtime", flush=True)
    return "installed"


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _do_scan(ctx, api_key, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required",
                "message": "Send {\"domain\": \"example.com\"}."}, 400

    cached = _cache.get(domain)
    if cached and (time.time() - cached[0]) < CACHE_TTL and not (data or {}).get("force"):
        out = dict(cached[1])
        out["from_cache"] = True
        out["cache_age_seconds"] = int(time.time() - cached[0])
        return out, 200

    ok, why = _resolvable(domain)
    if not ok:
        return {"error": "domain_refused", "domain": domain, "reason": why,
                "message": "Only public, resolvable hosts are scanned."}, 400

    scanned = time.time()
    findings, std, conv = _scan(domain)

    ev = {"user_id": "grade:" + domain, "action": "transparency_scan",
          "amount": 0, "country": "UK", "device_id": "grade",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SCAN_RECORDED", "score": 0, "grade_version": VERSION,
           "domain": domain, "standards_served": std, "conventions_served": conv,
           "timestamp": scanned,
           "detail": "domain=%s;standards=%d/%d;conventions=%d/%d"
                     % (domain, std, len(STANDARDS), conv, len(CONVENTIONS))}
    try:
        h, idx, seq = ctx["seal"](ev, res, scanned, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "message": ("The scan ran but was not recorded, so nothing is "
                            "published. A scan nobody can audit is not published "
                            "here.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash"}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO grade_scan(domain,scanned,findings,standards_served,"
            "conventions_served,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
            (domain, scanned, json.dumps(findings), std, conv, h, idx))
        ctx["conn"].commit()

    out = _summary(domain, findings, std, conv, scanned, h, idx)
    out["receipt_seq"] = seq
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    out["report"] = "https://sebbi.pro/x/grade/report?domain=" + domain
    _cache[domain] = (scanned, out)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    return out, 200


def _report(ctx, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT scanned,findings,standards_served,conventions_served,"
            "audit_hash,block_index FROM grade_scan WHERE domain=? "
            "ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
    if not row:
        return {"found": False, "domain": domain,
                "message": "This domain has not been scanned."}, 404
    try:
        findings = json.loads(row[1])
    except Exception:
        findings = {}
    out = _summary(domain, findings, row[2], row[3], row[0], row[4], row[5])
    out["found"] = True
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    return out, 200


def _list(ctx, data):
    try:
        limit = min(200, max(1, int((data or {}).get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain,MAX(scanned),standards_served,conventions_served "
            "FROM grade_scan GROUP BY domain ORDER BY MAX(scanned) DESC LIMIT ?",
            (limit,)).fetchall()
    return {
        "count": len(rows),
        "scans": [{
            "domain": r[0],
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
            "standards_served": "%d of %d" % (r[2], len(STANDARDS)),
            "conventions_served": "%d of %d" % (r[3], len(CONVENTIONS)),
            "report": "/x/grade/report?domain=" + r[0],
        } for r in rows],
        "what_this_list_is": (
            "Domains that have been scanned, with what they served. It is not a "
            "ranking, not a shortlist and not an allegation about anyone on it."),
    }, 200


def _spec():
    return {
        "module": "grade", "version": VERSION,
        "question": "Which public transparency files does this domain serve, and what is in them?",
        "standards_checked": [{"key": k, "path": p, "what": d} for k, p, d in STANDARDS],
        "conventions_checked": [{"key": k, "path": p, "what": d} for k, p, d in CONVENTIONS],
        "no_grade": (
            "This module issues no letter, no score and no verdict, and the word "
            "compliant appears nowhere in its output. Half of these files are "
            "conventions rather than requirements, two of them are conventions "
            "sebbi.pro helped write, and grading strangers against your own "
            "format would be marking their homework with your marking scheme."),
        "absence": (
            "A file that is not served is reported as not served. That is a fact "
            "about a file and never a finding about a company."),
        "self_declarations": (
            "Where a file declares something about the domain - ai-safe: true, a "
            "chain head, a standard version - the declaration is reported "
            "verbatim and is never treated as verified. Nothing here follows the "
            "URLs a manifest contains."),
        "how_it_fetches": {
            "scheme": "https only, port 443",
            "redirects": "not followed",
            "timeout_seconds": TIMEOUT,
            "max_bytes_per_file": MAX_BYTES,
            "address_check": ("DNS resolved and rejected if it points at private, "
                              "loopback, link-local, multicast or reserved space"),
            "known_limit": ("resolve-then-connect leaves a DNS rebinding window; "
                            "stated rather than hidden"),
            "robots": "/robots.txt is read first and Disallow rules for * are honoured",
            "user_agent": UA,
        },
        "badge": {
            "url": "https://sebbi.pro/grade-badge?domain=example.com",
            "behaviour": ("renders from the stored scan only and never fetches the "
                          "target, so embedding it cannot point traffic at anyone"),
        },
        "every_scan_is_sealed": (
            "Each scan is written into the audit chain with its receipt, so a "
            "domain owner who objects can be shown exactly what was requested "
            "and when."),
        "auth": "scan is keyed. report, list, spec and the badge are public.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    s = _srv()
    if s is not None and not _patched[0]:
        try:
            _install(s, ctx)
        except Exception as exc:
            print("GRADE: patch failed - " + str(exc), flush=True)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "scan":
            if not api_key:
                return {"error": "api_key_required",
                        "message": ("Scanning fetches somebody else's server, so it "
                                    "is keyed and attributable. Reading results is "
                                    "public.")}, 401
            return _do_scan(ctx, api_key, data)
        return {"error": "unknown_action", "action": action, "POST": ["scan"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "report":
        return _report(ctx, data)
    if action == "list":
        return _list(ctx, data)
    if action == "status":
        return {"module": "grade", "version": VERSION,
                "badge_installed": bool(_patched[0]),
                "cached_domains": len(_cache)}, 200
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "report", "list", "status"], "POST": ["scan"]}, 404

```
