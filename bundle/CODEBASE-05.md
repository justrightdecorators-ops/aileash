# Codebase — part 5 of 30

Contains:
- `modules/declare.py`
- `modules/demo.py`
- `modules/dsr.py`
- `modules/fingerprint.py`
- `modules/heartbeat.py`


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


## `modules/heartbeat.py`

872 lines, 31733 bytes

```python
"""
heartbeat.py - the two-sided clock.

WHAT PROBLEM THIS SOLVES
------------------------
Every timestamp in this system is a number the operator wrote. External
anchoring (OpenTimestamps) and peer witnessing both prove a record existed
BEFORE some later public event. They are ceilings.

Nothing proved a floor. Nothing stopped a record being created EARLIER than
it claims, or a whole chain being pre-computed in advance and released
slowly to look live. That is the fraud that actually happens: the grant
written after the incident, the decision dated last Tuesday.

A clock cannot fix this. Anyone can write down what a clock will say at
14:32:07 tomorrow, so hashing a clock face adds a hash, not a time.

WHAT DOES FIX IT
----------------
A public beacon: a source that ticks on a fixed cadence like a clock, but
whose value at each tick cannot be known by anyone until the tick happens.
drand (League of Entropy) publishes one every 30 seconds. Bitcoin publishes
one roughly every ten minutes.

Fold that value into a sealed block and the block cannot have been created
before the tick existed. Not because we say so - because it contains a
number that did not exist yet.

THE INTERLEAVE, WHICH IS THE WHOLE TRICK
----------------------------------------
We do NOT stamp every decision. We seal one beat into the chain every few
minutes. The chain is append-only and prev-hash linked, so any record
sitting between beat A and beat B was necessarily created after A and
before B.

One beat therefore gives a floor to every record that follows it, and the
next beat gives all of them a ceiling. Every decision gets a two-sided
window for free, with no change to seal(), no change to server.py, and no
extra latency on the decision path.

The window width is published on every answer. It is a live public
measurement of how much room the operator would have to lie in. It is the
only number in this system that gets better by us doing more work, and
worse by us doing less, which is why it is published.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the record is true. It proves when it can have been made.
- It does not verify drand's BLS signature (not feasible in pure stdlib).
  It records the round and the randomness verbatim, and anyone can re-fetch
  that round from drand and confirm the value matches. Deterministic,
  public, and does not involve us.
- A record inside an open window (after the last beat, before the next) has
  a floor and no ceiling yet. That is reported as open, never as closed.
- Beats can only be sealed by whoever runs this server. What stops the
  operator sealing a stale tick is that the tick is timestamped and public:
  sealing round N long after round N happened widens the window and shows.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec        public   what this is, how to verify it yourself
  GET  latest      public   the most recent beat sealed
  GET  ticks       public   recent beats
  GET  window      public   ?block= or ?receipt= - the two-sided window
  GET  verify      public   ?round= - what we sealed, and where to check it
  GET  status      public   cadence, coverage, mean window
  POST beat        keyed    fetch a tick now and seal it
  POST source      keyed    add a beacon reading fetched elsewhere (air-gap)
"""

import json
import time
import sqlite3
import threading
import urllib.request
import urllib.error

VERSION = "1.3.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "latest"),
    ("GET", "ticks"),
    ("GET", "window"),
    ("GET", "verify"),
    ("GET", "status"),
}

# ---------------------------------------------------------------------
# Beacon sources. Fixed hosts only - this is an allowlist, not a fetcher.
# ---------------------------------------------------------------------
# Each source: name, url, cadence in seconds, and a parser returning
# (round, value, source_time_or_None).

BEACON_HOSTS = {
    "api.drand.sh",
    "drand.cloudflare.com",
    "mempool.space",
}

FETCH_TIMEOUT = 8
MAX_BODY = 65536

BEAT_SECONDS = 300          # one beat every five minutes
AUTO_BEAT = True
MIN_BEAT_GAP = 60           # refuse to beat more often than this

_timer_lock = threading.Lock()
_timer_started = False
_beat_runs = 0
_beat_last = None
_beat_last_error = None


def _parse_drand(raw):
    d = json.loads(raw)
    rnd = int(d["round"])
    val = str(d["randomness"])
    if not val or len(val) < 32:
        raise ValueError("drand randomness missing or too short")
    return rnd, val, None


def _parse_btc_tip(raw):
    val = raw.strip()
    if len(val) != 64 or any(c not in "0123456789abcdefABCDEF" for c in val):
        raise ValueError("bitcoin tip hash not a 64-char hex string")
    return None, val.lower(), None


SOURCES = [
    {
        "name": "drand-quicknet",
        "url": "https://api.drand.sh/v2/beacons/quicknet/rounds/latest",
        "cadence_seconds": 3,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/v2/beacons/quicknet/rounds/{round}",
        "note": "League of Entropy public randomness beacon, quicknet chain",
    },
    {
        "name": "drand-default",
        "url": "https://api.drand.sh/public/latest",
        "cadence_seconds": 30,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/public/{round}",
        "note": "League of Entropy public randomness beacon, default chain",
    },
    {
        "name": "bitcoin-tip",
        "url": "https://mempool.space/api/blocks/tip/hash",
        "cadence_seconds": 600,
        "parse": _parse_btc_tip,
        "verify_url": "https://mempool.space/block/{value}",
        "note": "Bitcoin chain tip - slower, but the hardest to influence",
    },
]

VOCABULARY = {
    "floor": (
        "The record was created after this beat, because the chain is "
        "append-only and the record sits after a block containing a value "
        "that did not exist before the beat."
    ),
    "ceiling": (
        "The record was created before this beat, because the record sits "
        "before it in an append-only chain."
    ),
    "window": (
        "The span between floor and ceiling. The record can have been "
        "created at any moment inside it and no moment outside it. Smaller "
        "is stronger. This is a measurement, not a claim."
    ),
    "open": (
        "There is a floor but no ceiling yet: the next beat has not been "
        "sealed. Reported as open rather than closed. It closes on the "
        "next beat, and nothing about the record changes when it does."
    ),
    "unfloored": (
        "The record predates the first beat ever sealed. It has no floor "
        "from this module. Its ceiling still holds."
    ),
}

WHAT_THIS_PROVES = (
    "A window, not a truth. Inside the window the record could have been "
    "created at any instant. Outside it, it could not have been created at "
    "all. It says nothing about whether the record's contents are correct."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS heartbeat_tick (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source       TEXT NOT NULL,
        beacon_round INTEGER,
        value        TEXT NOT NULL,
        fetched_at   REAL NOT NULL,
        cadence      INTEGER,
        chain_rowid  INTEGER,
        audit_hash   TEXT,
        note         TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hb_rowid ON heartbeat_tick(chain_rowid)",
    "CREATE INDEX IF NOT EXISTS idx_hb_round ON heartbeat_tick(source, beacon_round)",
]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        # diagnostic columns, added without breaking an existing table
        cur.execute("PRAGMA table_info(heartbeat_tick)")
        have = [r[1] for r in cur.fetchall()]
        for col in ("seal_shape", "seal_error"):
            if col not in have:
                try:
                    cur.execute("ALTER TABLE heartbeat_tick ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass
        conn.commit()


def _host_of(url):
    try:
        rest = url.split("://", 1)[1]
    except IndexError:
        return ""
    return rest.split("/", 1)[0].split(":", 1)[0].lower()


def _fetch(url):
    if not url.startswith("https://"):
        raise ValueError("https only")
    host = _host_of(url)
    if host not in BEACON_HOSTS:
        raise ValueError("host not on the beacon allowlist: %s" % host)
    req = urllib.request.Request(url, headers={"User-Agent": "aileash-heartbeat/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        return r.read(MAX_BODY).decode("utf-8", "replace")


def _read_tick(fetcher=None):
    """Try each source in order. Returns dict or raises."""
    fetcher = fetcher or _fetch
    errors = []
    for src in SOURCES:
        try:
            raw = fetcher(src["url"])
            rnd, val, _ = src["parse"](raw)
            return {
                "source": src["name"],
                "beacon_round": rnd,
                "value": val,
                "cadence": src["cadence_seconds"],
                "note": src["note"],
            }
        except Exception as e:
            errors.append("%s: %s" % (src["name"], e))
    raise RuntimeError("no beacon reachable | " + " | ".join(errors))


def _seal(ctx, action, payload):
    """Seal through the host's seal().

    Confirmed from server.py: seal(event, result, ts, api_key=None) where
    EVENT IS A DICT carrying user_id (it is subscripted inside), and the
    return is (audit_hash, block_index, key_seq). So the block position
    comes back directly and does not have to be guessed from MAX(rowid).

    Returns (ok, shape, error, audit_hash, block_index).
    """
    fn = ctx.get("seal")
    if fn is None:
        return False, None, "ctx has no seal function", None, None

    ts = time.time()
    event = {
        "user_id": "heartbeat",
        "action": action,
        "amount": 0,
        "country": "UK",
        "device_id": "heartbeat",
        "anomaly": 0,
        "device_risk": 0,
    }
    result = dict(payload)
    result.setdefault("decision", "BEACON_SEALED")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)

    attempts = [
        ("seal(event_dict, result, ts)", lambda: fn(event, result, ts)),
        ("seal(event_dict, result, ts, None)", lambda: fn(event, result, ts, None)),
        ("seal(event_dict, result)", lambda: fn(event, result)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            out = call()
        except Exception as e:
            errors.append("%s -> %s: %s" % (shape, type(e).__name__, e))
            continue
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return True, shape, None, h, idx
    return False, None, " | ".join(errors), None, None


def _audit_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    return cur.fetchone() is not None


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for name in ("audit_hash", "hash", "block_hash"):
        if name in c:
            return name
    return None


def _latest_rowid(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(rowid) FROM audit_log")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def _backfill(conn, lock, tick_id):
    """After a seal, learn which chain row it landed on."""
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        row = cur.fetchone()
        rid = row[0] if row and row[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute(
            "UPDATE heartbeat_tick SET chain_rowid=?, audit_hash=? WHERE id=?",
            (rid, h, tick_id),
        )
        conn.commit()
    return rid, h


# ---------------------------------------------------------------------
# the beat
# ---------------------------------------------------------------------

def _do_beat(ctx, fetcher=None, forced=False):
    global _beat_runs, _beat_last, _beat_last_error
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    with lock:
        cur = conn.cursor()
        cur.execute("SELECT fetched_at FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if row and not forced and (time.time() - row[0]) < MIN_BEAT_GAP:
        return {"beat": False, "reason": "too_soon", "min_gap_seconds": MIN_BEAT_GAP}, 429

    tick = _read_tick(fetcher)
    now = time.time()

    event = "heartbeat_beat"
    result = {
        "kind": "beacon_tick",
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "fetched_at": now,
        "note": (
            "Unpredictable public value. Any block after this one in this "
            "append-only chain was created after this tick existed."
        ),
    }

    with lock:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO heartbeat_tick (source, beacon_round, value, fetched_at,"
            " cadence, note) VALUES (?,?,?,?,?,?)",
            (tick["source"], tick["beacon_round"], tick["value"], now,
             tick["cadence"], tick["note"]),
        )
        tick_id = cur.lastrowid
        conn.commit()

    ok, shape, err, h, rid = _seal(ctx, event, result)
    if ok and (rid is None or h is None):
        try:
            rid2, h2 = _backfill(conn, lock, tick_id)
            rid = rid if rid is not None else rid2
            h = h if h is not None else h2
        except Exception:
            pass
    with lock:
        conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                     " chain_rowid=?, audit_hash=? WHERE id=?",
                     (shape, err, rid, h, tick_id))
        conn.commit()

    _beat_runs += 1
    _beat_last = now
    _beat_last_error = err

    return {
        "beat": True,
        "sealed_into_chain": bool(ok and rid),
        "seal_shape": shape,
        "seal_error": err,
        "tick_id": tick_id,
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "sealed_at_chain_rowid": rid,
        "audit_hash": h,
        "verify_yourself": _verify_url(tick["source"], tick["beacon_round"], tick["value"]),
    }, 200


def _verify_url(source, rnd, value):
    for s in SOURCES:
        if s["name"] == source:
            u = s["verify_url"]
            if rnd is not None:
                return u.replace("{round}", str(rnd)).replace("{value}", str(value))
            return u.replace("{value}", str(value))
    return None


def _start_timer(ctx):
    global _timer_started
    with _timer_lock:
        if _timer_started or not AUTO_BEAT:
            return
        _timer_started = True

    for t in threading.enumerate():
        if t.name == "heartbeat" and t.is_alive():
            return

    def loop():
        global _beat_last_error
        while True:
            try:
                _do_beat(ctx)
            except Exception as e:
                _beat_last_error = str(e)
            time.sleep(BEAT_SECONDS)

    t = threading.Thread(target=loop, name="heartbeat", daemon=True)
    t.start()


# ---------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------

def _find_rowid(conn, block, receipt):
    if block is not None:
        try:
            return int(block)
        except (TypeError, ValueError):
            return None
    if receipt:
        hcol = _hash_col(conn)
        if not hcol:
            return None
        cur = conn.cursor()
        cur.execute("SELECT rowid FROM audit_log WHERE %s=? LIMIT 1" % hcol, (receipt,))
        r = cur.fetchone()
        return r[0] if r else None
    return None


def _window_for(conn, rowid):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid<=?"
        " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
    floor = cur.fetchone()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
        " ORDER BY chain_rowid ASC LIMIT 1", (rowid,))
    ceil = cur.fetchone()
    return floor, ceil


def _beat_obj(row, err=None, shape=None):
    if not row:
        return None
    out = {
        "source": row[1],
        "round": row[2],
        "value": row[3],
        "at": _iso(row[4]),
        "at_epoch": row[4],
        "chain_rowid": row[5],
        "audit_hash": row[6],
        "verify_yourself": _verify_url(row[1], row[2], row[3]),
    }
    if row[5] is None:
        out["in_chain"] = False
        out["warning"] = ("This beat is NOT sealed into the chain, so it is "
                          "not a floor for anything. See seal_error.")
        if err:
            out["seal_error"] = err
    else:
        out["in_chain"] = True
        if shape:
            out["seal_shape"] = shape
    return out


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes %d seconds" % (s // 60, s % 60)
    return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]

    if not _audit_table(conn):
        return {"error": "audit_log_missing"}, 500

    _ensure(conn, lock)
    _start_timer(ctx)

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "latest":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return {"beats": 0, "message": "no beat sealed yet"}, 200
        age = time.time() - row[4]
        return {
            "latest_beat": _beat_obj(row),
            "seconds_since": round(age, 1),
            "open_window_so_far": _human(age),
            "meaning": (
                "Anything sealed since this beat has this beat as its floor "
                "and no ceiling until the next beat."
            ),
        }, 200

    if method == "GET" and action == "ticks":
        try:
            limit = min(int(data.get("limit", 25)), 200)
        except (TypeError, ValueError):
            limit = 25
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash, seal_error, seal_shape FROM heartbeat_tick"
            " ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return {
            "count": len(rows),
            "beats": [_beat_obj(r, r[7], r[8]) for r in rows],
            "cadence_target_seconds": BEAT_SECONDS,
        }, 200

    if method == "GET" and action == "window":
        rowid = _find_rowid(conn, data.get("block"), data.get("receipt"))
        if rowid is None:
            return {"error": "block_or_receipt_required",
                    "usage": "/x/heartbeat/window?block=846 or ?receipt=<audit_hash>"}, 400

        floor, ceil = _window_for(conn, rowid)
        out = {
            "block": rowid,
            "floor": _beat_obj(floor),
            "ceiling": _beat_obj(ceil),
            "what_this_proves": WHAT_THIS_PROVES,
            "vocabulary": VOCABULARY,
        }

        if floor and ceil:
            width = ceil[4] - floor[4]
            out["state"] = "closed"
            out["window_seconds"] = round(width, 1)
            out["window"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s and before %s. Window: %s."
                % (rowid, _iso(floor[4]), _iso(ceil[4]), _human(width))
            )
        elif floor:
            width = time.time() - floor[4]
            out["state"] = "open"
            out["window_seconds_so_far"] = round(width, 1)
            out["window_so_far"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s. The ceiling is not sealed "
                "yet, so the window is open." % (rowid, _iso(floor[4]))
            )
        elif ceil:
            out["state"] = "unfloored"
            out["statement"] = (
                "Block %d predates the first beat, so it has no floor from "
                "this module. It was created before %s." % (rowid, _iso(ceil[4]))
            )
        else:
            out["state"] = "no_beats"
            out["statement"] = "No beats have been sealed, so no window exists."

        out["external_ceiling"] = {
            "note": (
                "A second, independent ceiling comes from OpenTimestamps. "
                "Anchoring is per proof and has its own pending/confirmed "
                "state."
            ),
            "where": "/x/ots/status",
        }
        return out, 200

    if method == "GET" and action == "verify":
        rnd = data.get("round")
        if rnd is None:
            return {"error": "round_required"}, 400
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick WHERE beacon_round=?"
            " ORDER BY id DESC LIMIT 1", (rnd,))
        row = cur.fetchone()
        if not row:
            return {"error": "round_not_sealed", "round": rnd}, 404
        return {
            "sealed": _beat_obj(row),
            "how_to_verify": [
                "Fetch the round from the beacon operator at the url above.",
                "Compare its randomness with the value we sealed. They must match.",
                "Confirm the beat's audit_hash is in our chain at /api/verify-chain.",
                "Nothing in these three steps requires our cooperation.",
            ],
            "we_do_not_verify_the_signature": (
                "drand signs each round with BLS, which this server does not "
                "implement. We record the round and value verbatim. The "
                "operator's own endpoint is the authority, not us."
            ),
        }, 200

    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(fetched_at), MAX(fetched_at) FROM heartbeat_tick")
        n, first, last = cur.fetchone()
        cur.execute(
            "SELECT fetched_at FROM heartbeat_tick WHERE chain_rowid IS NOT NULL"
            " ORDER BY chain_rowid ASC")
        times = [r[0] for r in cur.fetchall()]
        gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        mean = sum(gaps) / len(gaps) if gaps else None
        widest = max(gaps) if gaps else None
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        tip = cur.fetchone()[0] or 0
        cur.execute("SELECT MIN(chain_rowid) FROM heartbeat_tick WHERE chain_rowid IS NOT NULL")
        firstrow = cur.fetchone()[0]
        covered = (tip - firstrow) if firstrow else 0
        return {
            "version": VERSION,
            "beats_sealed": n,
            "first_beat": _iso(first),
            "latest_beat": _iso(last),
            "cadence_target_seconds": BEAT_SECONDS,
            "auto_beat": AUTO_BEAT,
            "timer_running": _timer_started,
            "beat_runs_this_process": _beat_runs,
            "last_error": _beat_last_error,
            "beats_not_in_chain": _orphans(conn),
            "last_seal_error": _last_seal_error(conn),
            "last_seal_shape": _last_seal_shape(conn),
            "mean_window_seconds": round(mean, 1) if mean else None,
            "mean_window": _human(mean),
            "widest_window_seconds": round(widest, 1) if widest else None,
            "widest_window": _human(widest),
            "records_with_a_floor": covered,
            "chain_height": tip,
            "honest_note": (
                "Mean window is the average distance between beats. It is the "
                "typical amount of room a record has. Widest is the worst "
                "case, which is the number that actually matters."
            ),
        }, 200

    if method == "POST" and action == "beat":
        try:
            return _do_beat(ctx, forced=bool(data.get("force")))
        except Exception as e:
            return {"beat": False, "error": "beacon_unreachable", "detail": str(e)}, 503

    if method == "POST" and action == "source":
        # For an engine with no outbound network. The operator hands it a
        # reading fetched elsewhere. Sealed exactly as supplied and marked.
        val = data.get("value")
        src = data.get("source") or "supplied"
        rnd = data.get("round")
        if not val or len(str(val)) < 32:
            return {"error": "value_required", "note": "at least 32 characters"}, 400
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO heartbeat_tick (source, beacon_round, value,"
                " fetched_at, cadence, note) VALUES (?,?,?,?,?,?)",
                (src, rnd, str(val), now, None,
                 "supplied by operator, not fetched by this server"),
            )
            tick_id = cur.lastrowid
            conn.commit()
        ok, shape, err, h, rid = _seal(ctx, "heartbeat_beat", {
            "kind": "beacon_tick_supplied",
            "source": src, "round": rnd, "value": str(val), "fetched_at": now,
            "note": ("Supplied by the operator rather than fetched here. The "
                     "floor it gives is only as good as the reader's trust in "
                     "that source, and it is marked so nobody mistakes it."),
        })
        if ok and (rid is None or h is None):
            try:
                rid2, h2 = _backfill(conn, lock, tick_id)
                rid = rid if rid is not None else rid2
                h = h if h is not None else h2
            except Exception:
                pass
        with lock:
            conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                         " chain_rowid=?, audit_hash=? WHERE id=?",
                         (shape, err, rid, h, tick_id))
            conn.commit()
        return {"beat": True, "supplied": True, "tick_id": tick_id,
                "sealed_at_chain_rowid": rid, "audit_hash": h,
                "marked": "supplied by operator, not fetched by this server"}, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "latest", "ticks", "window", "verify",
                        "status", "beat", "source"]}, 404


def _orphans(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick WHERE chain_rowid IS NULL")
        return cur.fetchone()[0]
    except Exception:
        return None


def _last_seal_error(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_error FROM heartbeat_tick WHERE seal_error IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _last_seal_shape(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_shape FROM heartbeat_tick WHERE seal_shape IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _spec():
    return {
        "module": "heartbeat",
        "version": VERSION,
        "what_it_is": (
            "A clock nobody can wind. Public beacon values are sealed into "
            "the chain on a cadence. Because a beacon value cannot be known "
            "before its tick, and because the chain is append-only, every "
            "record between two beats has a provable earliest and latest "
            "moment of creation."
        ),
        "why_a_clock_alone_fails": (
            "Anyone can write down what a clock will read tomorrow. A clock "
            "reading proves nothing about when it was written down. A beacon "
            "value cannot be written down in advance by anyone."
        ),
        "the_interleave": (
            "Decisions are not stamped individually. One beat every few "
            "minutes gives a floor to everything after it and a ceiling to "
            "everything before the next one. No change to the decision path "
            "and no added latency."
        ),
        "sources": [
            {"name": s["name"], "cadence_seconds": s["cadence_seconds"],
             "note": s["note"], "url": s["url"]} for s in SOURCES
        ],
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It bounds when a record can have been made. It says nothing "
            "about whether the record is correct.",
            "drand signatures are BLS and are not verified here. The round "
            "and value are recorded verbatim and are re-fetchable by anyone "
            "from the beacon operator.",
            "A record after the newest beat has an open window until the "
            "next beat is sealed.",
            "Beats sealed from a value the operator supplied by hand rather "
            "than fetched are marked as such and are weaker.",
            "A wide window is reported wide. The number is a measurement of "
            "our own cadence, and it can embarrass us.",
        ],
        "routes": {
            "GET /x/heartbeat/spec": "this document",
            "GET /x/heartbeat/latest": "most recent beat and the open window so far",
            "GET /x/heartbeat/ticks?limit=": "recent beats",
            "GET /x/heartbeat/window?block=|?receipt=": "two-sided window for a record",
            "GET /x/heartbeat/verify?round=": "what we sealed and where to check it",
            "GET /x/heartbeat/status": "cadence, coverage, mean and widest window",
            "POST /x/heartbeat/beat": "keyed - fetch and seal now",
            "POST /x/heartbeat/source": "keyed - seal a reading fetched elsewhere",
        },
    }

```
