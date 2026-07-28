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
