# Codebase — part 23 of 43

Contains:
- `modules/standing.py`
- `modules/startpage.py`
- `modules/stats.py`
- `modules/studio.py`


## `modules/standing.py`

378 lines, 15691 bytes

```python
#!/usr/bin/env python3
"""
modules/standing.py  -  Temporal Standing Test runner
=====================================================

Runs the published protocol at
https://studio.moralclarity.ai/temporal-standing-test
against the live authority engine (modules/continuity.py), on production,
and preserves what was observed.

    GET /x/standing/status             what is frozen, what has run    (public)
    GET /x/standing/freeze             seal implementation + claim     (public)
    GET /x/standing/run                run both branches, seal result  (public)
    GET /x/standing/evidence?run=<id>  the full evidence package       (public)
    GET /x/standing/runs               every run, pass or fail         (public)

Freeze first. A run is refused unless the files deployed now are byte for
byte the files that were frozen, so the claim cannot be adjusted after a
result is seen. Every run is kept and listed, including failures.
"""

import hashlib
import importlib.util
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "freeze"), ("GET", "run"),
          ("GET", "evidence"), ("GET", "runs")}

PROTOCOL = "https://studio.moralclarity.ai/temporal-standing-test"
BASE = "https://sebbi.pro/x/standing/"
TEST_KEY = "public-standing-test"
CAP = "tst.record.write"
SIBLING_CAP = "tst.record.read"
PURPOSE = "temporal-standing-test"
MIN_GAP = 600          # seconds between runs
MAX_PER_DAY = 6

PROPOSITION = (
    "Execution authority established at T0 is re-established at the consequence "
    "boundary (continuity confirm) before an action binds. A change that defeats "
    "the exercised authority lineage prevents binding; a change outside that "
    "lineage does not.")

FALSIFIER = {
    "case_A_standing_defeating":
        "T0: grants G and sibling S issued by a human principal; exercise under G "
        "returns ALLOW. dN: G is revoked. Tn: confirm must return bound=false AND the "
        "consequence table must gain no row. Any binding or any row is a FAIL.",
    "case_B_standing_preserving":
        "T0: identical setup. dN: sibling S is revoked (a real authority change "
        "outside the exercised lineage). Tn: confirm must return bound=true AND the "
        "consequence table must gain exactly one row. A refusal is a FAIL.",
    "malformed":
        "If the T0 exercise in either case does not return ALLOW, standing was never "
        "established and the run is UNRESOLVED, neither PASS nor FAIL.",
}

SCOPE = ("Authority-class dN (revocation) only, on the continuity exercise -> confirm "
         "path of this deployment. Nothing beyond the frozen implementation and this "
         "change class is claimed.")

_ready = False


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _continuity():
    """The engine under test - the copy the router already loaded if possible."""
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("continuity.py") and hasattr(m, "_confirm") and hasattr(m, "_evaluate"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuity.py")
    spec = importlib.util.spec_from_file_location("standing_continuity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _implementation(C):
    return {
        "continuity_version": getattr(C, "VERSION", None),
        "continuity_sha256": _sha_file(C.__file__),
        "standing_version": VERSION,
        "standing_sha256": _sha_file(os.path.abspath(__file__)),
        "proposition": PROPOSITION,
        "falsifier": FALSIFIER,
        "scope": SCOPE,
        "protocol": PROTOCOL,
    }


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS standing_freeze(id TEXT PRIMARY KEY,"
                  "digest TEXT UNIQUE,impl TEXT,created REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS standing_run(id TEXT PRIMARY KEY,freeze_id TEXT,"
                  "result TEXT,package TEXT,digest TEXT,created REAL,audit_hash TEXT,"
                  "block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS standing_effect(id INTEGER PRIMARY KEY "
                  "AUTOINCREMENT,run_id TEXT,case_id TEXT,evaluation TEXT,created REAL)")
        c.commit()
    _ready = True


def _seal(ctx, kind, detail, extra=None):
    now = time.time()
    ev = {"user_id": "tst:standing", "action": kind, "amount": 0, "country": "UK",
          "device_id": "standing", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "standing_version": VERSION,
           "detail": detail}
    if extra:
        res.update(extra)
    out = ctx["seal"](ev, res, now, TEST_KEY)
    audit_hash = out[0] if isinstance(out, (list, tuple)) else out
    block = out[1] if isinstance(out, (list, tuple)) and len(out) > 1 else None
    return audit_hash, block, now


def _current_freeze(ctx, digest):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT id,created,audit_hash,block_index FROM standing_freeze WHERE digest=?",
            (digest,)).fetchone()


# ----------------------------------------------------------------------

def _freeze(ctx):
    C = _continuity()
    impl = _implementation(C)
    digest = hashlib.sha256(_canon(impl).encode()).hexdigest()
    row = _current_freeze(ctx, digest)
    if row:
        return {"frozen": True, "already": True, "freeze": row[0], "digest": digest,
                "sealed_at": _iso(row[1]), "sealed_in_chain": row[2], "block_index": row[3],
                "implementation": impl, "next": BASE + "run"}, 200
    fid = "f_" + uuid.uuid4().hex[:16]
    audit_hash, block, now = _seal(ctx, "standing_frozen",
                                   "freeze=%s;digest=%s" % (fid, digest),
                                   {"freeze": fid, "freeze_digest": digest,
                                    "continuity_sha256": impl["continuity_sha256"],
                                    "standing_sha256": impl["standing_sha256"]})
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO standing_freeze VALUES(?,?,?,?,?,?)",
                            (fid, digest, _canon(impl), now, audit_hash, block))
        ctx["conn"].commit()
    return {"frozen": True, "freeze": fid, "digest": digest, "sealed_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block,
            "implementation": impl,
            "note": "Sealed before any run. A run is refused if either file changes.",
            "next": BASE + "run"}, 200


def _effects(ctx, run_id, case_id):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT COUNT(*) FROM standing_effect WHERE run_id=? AND case_id=?",
            (run_id, case_id)).fetchone()[0]


def _case(ctx, C, run_id, case_id, defeat):
    steps = []

    def rec(name, req, resp, status):
        steps.append({"step": name, "at": _iso(time.time()), "request": req,
                      "response": resp, "http_status": status})

    t0 = time.time()
    tag = run_id[-10:] + "_" + case_id
    base = {"issuer": "standing-principal", "issuer_kind": "human",
            "subject": "tst-agent-" + tag, "subject_kind": "agent",
            "constraints": {"max_amount": 100}, "purpose": "temporal standing test",
            "purpose_tags": [PURPOSE], "not_after": t0 + 3600, "delegations_left": 0}
    g_id, s_id = "tst_" + tag + "_G", "tst_" + tag + "_S"

    g = dict(base, id=g_id, scope=[CAP])
    r, s = C._issue(ctx, TEST_KEY, g); rec("T0 issue G (exercised grant)", g, r, s)
    sib = dict(base, id=s_id, scope=[SIBLING_CAP])
    r, s = C._issue(ctx, TEST_KEY, sib); rec("T0 issue S (sibling grant)", sib, r, s)

    ex = {"grant": g_id, "action": CAP, "params": {"amount": 10}, "purpose_tag": PURPOSE}
    e, s = C._evaluate(ctx, TEST_KEY, ex); rec("T0 exercise under G", ex, e, s)
    eval_id = e.get("evaluation")
    out = {"case": case_id,
           "branch": "standing-defeating" if defeat else "standing-preserving",
           "required": "DENY / NON-EXECUTABLE" if defeat else "PERMIT / EXECUTABLE",
           "t0_evaluation": eval_id,
           "t0_proof": "https://sebbi.pro/x/continuity/proof?evaluation=%s" % eval_id,
           "steps": steps}
    if e.get("verdict") != "ALLOW":
        out["determination"] = "UNRESOLVED"
        out["why"] = "T0 exercise returned %s, so standing was never established" % e.get("verdict")
        return out

    target = g_id if defeat else s_id
    rv = {"grant": target, "reason": "temporal standing test dN"}
    r, s = C._revoke(ctx, TEST_KEY, rv)
    rec("dN revoke " + ("G (in lineage)" if defeat else "S (outside lineage)"), rv, r, s)

    before = _effects(ctx, run_id, case_id)
    cf = {"evaluation": eval_id, "action": CAP, "params": {"amount": 10},
          "outcome": "executed"}
    r, s = C._confirm(ctx, TEST_KEY, cf); rec("Tn confirm (consequence boundary)", cf, r, s)
    bound = bool(r.get("bound"))
    if bound:
        # The consequence itself. It happens only if the engine let it bind.
        with ctx["lock"]:
            ctx["conn"].execute("INSERT INTO standing_effect(run_id,case_id,evaluation,created) "
                                "VALUES(?,?,?,?)", (run_id, case_id, eval_id, time.time()))
            ctx["conn"].commit()
    after = _effects(ctx, run_id, case_id)

    tr, s = C._trace(ctx, {"grant": g_id}); rec("Tn authoritative state of G", {"grant": g_id}, tr, s)

    out["bound"] = bound
    out["consequence_rows_before"] = before
    out["consequence_rows_after"] = after
    if defeat:
        ok = (not bound) and after == before
    else:
        ok = bound and after == before + 1
    out["determination"] = "PASS" if ok else "FAIL"
    return out


def _run(ctx):
    C = _continuity()
    impl = _implementation(C)
    digest = hashlib.sha256(_canon(impl).encode()).hexdigest()
    frz = _current_freeze(ctx, digest)
    if not frz:
        return {"error": "not_frozen",
                "message": "The deployed files do not match any freeze. Freeze first; a "
                           "new freeze is a new test.", "freeze": BASE + "freeze"}, 409

    now = time.time()
    with ctx["lock"]:
        last = ctx["conn"].execute("SELECT MAX(created) FROM standing_run").fetchone()[0]
        today = ctx["conn"].execute("SELECT COUNT(*) FROM standing_run WHERE created>?",
                                    (now - 86400,)).fetchone()[0]
    if last and now - last < MIN_GAP:
        return {"error": "too_soon", "retry_after_seconds": int(MIN_GAP - (now - last)),
                "runs": BASE + "runs"}, 429
    if today >= MAX_PER_DAY:
        return {"error": "daily_limit", "limit": MAX_PER_DAY, "runs": BASE + "runs"}, 429

    run_id = "r_" + uuid.uuid4().hex[:16]
    order = ["A", "B"]
    random.shuffle(order)
    cases = {}
    for cid in order:
        cases[cid] = _case(ctx, C, run_id, cid, defeat=(cid == "A"))

    dets = [cases["A"]["determination"], cases["B"]["determination"]]
    if "UNRESOLVED" in dets:
        result = "UNRESOLVED"
    elif dets == ["PASS", "PASS"]:
        result = "PASS"
    else:
        result = "FAIL"

    package = {
        "protocol": PROTOCOL,
        "run": run_id,
        "result": result,
        "started_at": _iso(now),
        "finished_at": _iso(time.time()),
        "freeze": {"id": frz[0], "digest": digest, "sealed_at": _iso(frz[1]),
                   "sealed_in_chain": frz[2], "block_index": frz[3]},
        "implementation": impl,
        "case_order_as_run": order,
        "case_A": cases["A"],
        "case_B": cases["B"],
        "note": ("Observed on production. Nothing here was edited after the run; the "
                 "package digest below is sealed in the chain."),
    }
    pdigest = hashlib.sha256(_canon(package).encode()).hexdigest()
    audit_hash, block, t = _seal(ctx, "standing_run",
                                 "run=%s;result=%s;package=%s" % (run_id, result, pdigest),
                                 {"run": run_id, "result": result, "package_digest": pdigest})
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO standing_run VALUES(?,?,?,?,?,?,?,?)",
                            (run_id, frz[0], result, _canon(package), pdigest, now,
                             audit_hash, block))
        ctx["conn"].commit()
    return {"run": run_id, "result": result,
            "case_A": cases["A"]["determination"], "case_B": cases["B"]["determination"],
            "package_digest": pdigest, "sealed_in_chain": audit_hash, "block_index": block,
            "evidence": BASE + "evidence?run=" + run_id}, 200


def _evidence(ctx, data):
    rid = str(data.get("run", "")).strip()
    with ctx["lock"]:
        if rid:
            row = ctx["conn"].execute("SELECT package,digest,audit_hash,block_index FROM "
                                      "standing_run WHERE id=?", (rid,)).fetchone()
        else:
            row = ctx["conn"].execute("SELECT package,digest,audit_hash,block_index FROM "
                                      "standing_run ORDER BY created DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "no_run", "runs": BASE + "runs"}, 404
    pkg = json.loads(row[0])
    pkg["package_digest"] = row[1]
    pkg["package_sealed_in_chain"] = row[2]
    pkg["package_block_index"] = row[3]
    pkg["check"] = ("Remove the three package_* fields and the check field, canonicalise "
                    "(keys sorted, separators ',' ':'), SHA-256, compare with package_digest.")
    return pkg, 200


def _runs(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT id,result,created,block_index FROM standing_run "
                                   "ORDER BY created DESC").fetchall()
    return {"count": len(rows),
            "runs": [{"run": r[0], "result": r[1], "at": _iso(r[2]), "block_index": r[3],
                      "evidence": BASE + "evidence?run=" + r[0]} for r in rows],
            "note": "Every run is listed, failures included."}, 200


def _status(ctx):
    C = _continuity()
    impl = _implementation(C)
    digest = hashlib.sha256(_canon(impl).encode()).hexdigest()
    frz = _current_freeze(ctx, digest)
    with ctx["lock"]:
        n = ctx["conn"].execute("SELECT COUNT(*) FROM standing_run").fetchone()[0]
    return {"module": "standing", "version": VERSION, "protocol": PROTOCOL,
            "continuity_version": impl["continuity_version"],
            "frozen": bool(frz), "freeze": frz[0] if frz else None,
            "runs": n,
            "freeze_url": BASE + "freeze", "run_url": BASE + "run",
            "runs_url": BASE + "runs"}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}
    if method == "GET":
        if action == "status":
            return _status(ctx)
        if action == "freeze":
            return _freeze(ctx)
        if action == "run":
            return _run(ctx)
        if action == "evidence":
            return _evidence(ctx, data)
        if action == "runs":
            return _runs(ctx)
    return {"error": "unknown_action",
            "GET": ["status", "freeze", "run", "evidence", "runs"]}, 404

```


## `modules/startpage.py`

286 lines, 23449 bytes

```python
"""
modules/startpage.py  v1.0.0
"Start here" at /start: the customer front door. Three paths (agent builders,
companies, auditors) on a spinning dial, five-minute steps, pricing and calls
to action. Sign-up links point at /install.html.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/startpage/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPlN0YXJ0IGhlcmUg4oCUIHNlYmJpLnBybzwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBjb250ZW50PSJNYWtl"
    "IGV2ZXJ5IEFJIGRlY2lzaW9uIHByb3ZhYmxlLiBTdGFydCBmcmVlIGluIGZpdmUgbWludXRlczogZ2V0IGEga2V5LCBzZWFsIHlv"
    "dXIgZmlyc3QgZGVjaXNpb24sIHNlZSB0aGUgcHJvb2YuIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNv"
    "bS9jc3MyP2ZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMCZmYW1pbHk9SUJNK1BsZXgrU2Fuczp3Z2h0QDQwMDs1MDA7"
    "NjAwJmZhbWlseT1OZXdzcmVhZGVyOm9wc3osd2dodEA2Li43Miw1MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8"
    "c3R5bGU+Cjpyb290ey0taW5rOiMwNTA3MGY7LS1pbmsyOiMwZDE0MjQ7LS1nb2xkOiNjOWE4NGM7LS1vazojN2ZlM2IwOy0tYmx1"
    "ZTojOGZkMGZmOy0tbXV0ZTojOGE5M2FkOy0tbGluZTpyZ2JhKDIwMSwxNjgsNzYsLjIyKTstLW1vbm86J0lCTSBQbGV4IE1vbm8n"
    "LHVpLW1vbm9zcGFjZSxtb25vc3BhY2U7LS1zYW5zOidJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlm"
    "OidOZXdzcmVhZGVyJyxHZW9yZ2lhLHNlcmlmfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdl"
    "YmtpdC10YXAtaGlnaGxpZ2h0LWNvbG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGVsbGlw"
    "c2UgYXQgNTAlIDAlLCMxNTIwNGEgMCUsIzA1MDcwZiA2MCUpO2NvbG9yOiNlOGVkZjc7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7"
    "bGluZS1oZWlnaHQ6MS42O21pbi1oZWlnaHQ6MTAwdmh9Ci53cmFwe21heC13aWR0aDo5MDBweDttYXJnaW46MCBhdXRvO3BhZGRp"
    "bmc6MCAyMHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50"
    "ZXI7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVhLWluc2V0LXRvcCkpIDAgMH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZh"
    "cigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBh"
    "e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO3RleHQtZGVjb3JhdGlvbjpu"
    "b25lO21hcmdpbi1sZWZ0OjE0cHh9Ci5oZXJve3RleHQtYWxpZ246Y2VudGVyO3BhZGRpbmc6NDRweCAwIDEwcHh9Ci5raWNre2Zv"
    "bnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41cHg7bGV0dGVyLXNwYWNpbmc6LjJlbTtjb2xvcjp2YXIoLS1nb2xk"
    "KX0KaDF7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6Y2xhbXAoMzRweCw3dncsNjBw"
    "eCk7bGluZS1oZWlnaHQ6MS4wNDttYXJnaW46MTJweCBhdXRvIDE0cHg7bWF4LXdpZHRoOjE1Y2g7YmFja2dyb3VuZDpsaW5lYXIt"
    "Z3JhZGllbnQoOTBkZWcsI2ZmZiAwJSwjYzlhODRjIDQ1JSwjN2ZlM2IwIDc1JSwjOGZkMGZmIDEwMCUpOy13ZWJraXQtYmFja2dy"
    "b3VuZC1jbGlwOnRleHQ7YmFja2dyb3VuZC1jbGlwOnRleHQ7Y29sb3I6dHJhbnNwYXJlbnR9Ci5oZXJvIHB7Y29sb3I6I2I2YzBk"
    "Njtmb250LXNpemU6MTdweDttYXgtd2lkdGg6NTRjaDttYXJnaW46MCBhdXRvfQouY3Rhe2Rpc3BsYXk6aW5saW5lLWZsZXg7YWxp"
    "Z24taXRlbXM6Y2VudGVyO2dhcDo4cHg7bWFyZ2luOjIycHggNnB4IDA7cGFkZGluZzoxNHB4IDIycHg7Ym9yZGVyLXJhZGl1czox"
    "MHB4O2ZvbnQ6NTAwIDE0cHggdmFyKC0tbW9ubyk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7Y3Vyc29yOnBvaW50ZXI7Ym9yZGVyOjB9"
    "Ci5jdGEuZ29sZHtiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOnZhcigtLWluayk7Ym94LXNoYWRvdzowIDAgMzBweCByZ2Jh"
    "KDIwMSwxNjgsNzYsLjQ1KX0KLmN0YS5naG9zdHtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjcpO2NvbG9yOiNmZmY7Ym9yZGVy"
    "OjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4yNSl9Ci8qIHNwaW5uaW5nIGJhcnMgKi8KLmJhcnN7ZGlzcGxheTpmbGV4O2p1"
    "c3RpZnktY29udGVudDpjZW50ZXI7Z2FwOjVweDtoZWlnaHQ6NDRweDthbGlnbi1pdGVtczpmbGV4LWVuZDttYXJnaW46MjhweCAw"
    "IDRweH0KLmJhcnMgaXtkaXNwbGF5OmJsb2NrO3dpZHRoOjZweDtib3JkZXItcmFkaXVzOjNweDtiYWNrZ3JvdW5kOmxpbmVhci1n"
    "cmFkaWVudCh2YXIoLS1vayksdmFyKC0tZ29sZCkpO2FuaW1hdGlvbjplcSAxLjJzIGVhc2UtaW4tb3V0IGluZmluaXRlO3RyYW5z"
    "Zm9ybS1vcmlnaW46Ym90dG9tfQpAa2V5ZnJhbWVzIGVxezAlLDEwMCV7dHJhbnNmb3JtOnNjYWxlWSguMjUpfTUwJXt0cmFuc2Zv"
    "cm06c2NhbGVZKDEpfX0KLyogcGF0aCBkaWFsICovCi5kaWFsd3JhcHtwZXJzcGVjdGl2ZToxMTAwcHg7aGVpZ2h0OjMzMHB4O2Rp"
    "c3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjttYXJnaW4tdG9wOjEwcHh9Ci5kaWFs"
    "e3Bvc2l0aW9uOnJlbGF0aXZlO3dpZHRoOjI1MHB4O2hlaWdodDoyNjBweDt0cmFuc2Zvcm0tc3R5bGU6cHJlc2VydmUtM2Q7dHJh"
    "bnNpdGlvbjp0cmFuc2Zvcm0gMXMgY3ViaWMtYmV6aWVyKC4yLC44LC4yLDEpfQouY2FyZHtwb3NpdGlvbjphYnNvbHV0ZTtpbnNl"
    "dDowO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjIwcHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoMTYwZGVnLHJnYmEo"
    "MjEsMzIsNzQsLjk1KSxyZ2JhKDEzLDIwLDM2LC45NSkpO2JvcmRlcjoxLjVweCBzb2xpZCB2YXIoLS1saW5lKTtiYWNrZmFjZS12"
    "aXNpYmlsaXR5OmhpZGRlbjtjdXJzb3I6cG9pbnRlcjtib3gtc2hhZG93OjAgMjBweCA1MHB4IHJnYmEoMCwwLDAsLjUpfQouY2Fy"
    "ZC5vbntib3JkZXItY29sb3I6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDQwcHggcmdiYSgxMjcsMjI3LDE3NiwuMzUpLDAgMjBw"
    "eCA1MHB4IHJnYmEoMCwwLDAsLjUpfQouY2FyZCAubntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xv"
    "cjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMTJlbX0KLmNhcmQgaDN7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQt"
    "d2VpZ2h0OjUwMDtmb250LXNpemU6MjRweDttYXJnaW46OHB4IDAgOHB4O2xpbmUtaGVpZ2h0OjEuMTV9Ci5jYXJkIHB7Zm9udC1z"
    "aXplOjE0cHg7Y29sb3I6I2I2YzBkNn0KLmNhcmQgLmdve3Bvc2l0aW9uOmFic29sdXRlO2JvdHRvbToxOHB4O2xlZnQ6MjBweDtm"
    "b250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1vayl9Ci5waWNrc3tkaXNwbGF5OmZsZXg7"
    "anVzdGlmeS1jb250ZW50OmNlbnRlcjtnYXA6OHB4O2ZsZXgtd3JhcDp3cmFwfQoucGlja3MgYnV0dG9ue2ZvbnQ6NTAwIDEycHgg"
    "dmFyKC0tbW9ubyk7YmFja2dyb3VuZDpyZ2JhKDEzLDIwLDM2LC44KTtjb2xvcjojZThlZGY3O2JvcmRlcjoxcHggc29saWQgdmFy"
    "KC0tbGluZSk7Ym9yZGVyLXJhZGl1czo5OTlweDtwYWRkaW5nOjhweCAxNHB4O2N1cnNvcjpwb2ludGVyfQoucGlja3MgYnV0dG9u"
    "Lm9ue2JvcmRlci1jb2xvcjp2YXIoLS1vayk7Y29sb3I6dmFyKC0tb2spfQpzZWN0aW9ue3BhZGRpbmc6NDBweCAwO2JvcmRlci10"
    "b3A6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjA3KX0KaDJ7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0"
    "OjUwMDtmb250LXNpemU6Y2xhbXAoMjZweCw0LjV2dywzOHB4KTtsaW5lLWhlaWdodDoxLjEyO21hcmdpbi1ib3R0b206MTBweH0K"
    "LmxlYWR7Y29sb3I6I2I2YzBkNjttYXgtd2lkdGg6NjBjaDttYXJnaW4tYm90dG9tOjIwcHh9Ci5zdGVwc3tkaXNwbGF5OmdyaWQ7"
    "Z2FwOjEycHh9Ci5zdGVwe2Rpc3BsYXk6ZmxleDtnYXA6MTZweDtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjc1KTtib3JkZXI6"
    "MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjE4cHh9Ci5zdGVwIC5udW17ZmxleDpub25l"
    "O3dpZHRoOjQycHg7aGVpZ2h0OjQycHg7Ym9yZGVyLXJhZGl1czo1MCU7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtq"
    "dXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2ZvbnQ6NjAwIDE2cHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0taW5rKTtiYWNrZ3JvdW5k"
    "OmNvbmljLWdyYWRpZW50KHZhcigtLWdvbGQpLHZhcigtLW9rKSx2YXIoLS1ibHVlKSx2YXIoLS1nb2xkKSk7YW5pbWF0aW9uOnNw"
    "aW4gNnMgbGluZWFyIGluZmluaXRlfQouc3RlcCAubnVtIHNwYW57ZGlzcGxheTpibG9jazthbmltYXRpb246c3BpbiA2cyBsaW5l"
    "YXIgaW5maW5pdGUgcmV2ZXJzZX0KQGtleWZyYW1lcyBzcGlue3Rve3RyYW5zZm9ybTpyb3RhdGUoMzYwZGVnKX19Ci5zdGVwIGg0"
    "e2ZvbnQtc2l6ZToxNnB4O21hcmdpbi1ib3R0b206NHB4fS5zdGVwIHB7Zm9udC1zaXplOjE0cHg7Y29sb3I6I2I2YzBkNn0KcHJl"
    "e2JhY2tncm91bmQ6IzAzMDUwYjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6OHB4O3BhZGRpbmc6"
    "MTJweDtmb250OjEycHggdmFyKC0tbW9ubyk7Y29sb3I6I2NmZTZkOTtvdmVyZmxvdy14OmF1dG87bWFyZ2luLXRvcDo4cHg7d2hp"
    "dGUtc3BhY2U6cHJlfQouc3RhdHN7ZGlzcGxheTpmbGV4O2dhcDoxMnB4O2ZsZXgtd3JhcDp3cmFwO2p1c3RpZnktY29udGVudDpj"
    "ZW50ZXI7bWFyZ2luLXRvcDoyNnB4fQouc3RhdHttaW4td2lkdGg6MTMwcHg7YmFja2dyb3VuZDpyZ2JhKDEzLDIwLDM2LC43KTti"
    "b3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTBweDtwYWRkaW5nOjEycHggMTZweDt0ZXh0LWFsaWdu"
    "OmNlbnRlcn0KLnN0YXQgYntkaXNwbGF5OmJsb2NrO2ZvbnQ6NjAwIDIycHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tb2spfS5z"
    "dGF0IHNwYW57Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0ZSk7bGV0dGVyLXNwYWNpbmc6LjA2ZW19Ci5wcmljZXtkaXNw"
    "bGF5OmdyaWQ7Z2FwOjEycHg7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn1AbWVkaWEobWluLXdpZHRoOjcyMHB4KXsucHJpY2V7"
    "Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOnJlcGVhdCgyLDFmcil9fQoucGxhbntiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjc1KTti"
    "b3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjIwcHg7cG9zaXRpb246cmVsYXRp"
    "dmU7b3ZlcmZsb3c6aGlkZGVufQoucGxhbi5ob3R7Ym9yZGVyLWNvbG9yOnZhcigtLWdvbGQpO2JveC1zaGFkb3c6MCAwIDMwcHgg"
    "cmdiYSgyMDEsMTY4LDc2LC4yKX0KLnBsYW4gLnR7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtsZXR0ZXItc3BhY2luZzouMTRl"
    "bTtjb2xvcjp2YXIoLS1nb2xkKX0KLnBsYW4gLmFtdHtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC1zaXplOjM0cHg7bWFy"
    "Z2luOjZweCAwIDJweH0ucGxhbiAuYW10IHNtYWxse2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLW11dGUpO2ZvbnQtZmFtaWx5"
    "OnZhcigtLXNhbnMpfQoucGxhbiB1bHtsaXN0LXN0eWxlOm5vbmU7bWFyZ2luLXRvcDoxMHB4fS5wbGFuIGxpe2ZvbnQtc2l6ZTox"
    "NHB4O2NvbG9yOiNiNmMwZDY7cGFkZGluZzo0cHggMCA0cHggMjJweDtwb3NpdGlvbjpyZWxhdGl2ZX0KLnBsYW4gbGk6YmVmb3Jl"
    "e2NvbnRlbnQ6IiI7cG9zaXRpb246YWJzb2x1dGU7bGVmdDowO3RvcDoxMXB4O3dpZHRoOjEwcHg7aGVpZ2h0OjEwcHg7Ym9yZGVy"
    "LXJhZGl1czo1MCU7YmFja2dyb3VuZDp2YXIoLS1vayk7Ym94LXNoYWRvdzowIDAgOHB4IHZhcigtLW9rKX0KLnBsYW4gLnNjYW57"
    "cG9zaXRpb246YWJzb2x1dGU7bGVmdDowO3JpZ2h0OjA7aGVpZ2h0OjJweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRl"
    "Zyx0cmFuc3BhcmVudCx2YXIoLS1vayksdHJhbnNwYXJlbnQpO2FuaW1hdGlvbjpzY2FuIDMuNXMgbGluZWFyIGluZmluaXRlO29w"
    "YWNpdHk6LjZ9CkBrZXlmcmFtZXMgc2NhbnswJXt0b3A6MH0xMDAle3RvcDoxMDAlfX0KLmdyaWQze2Rpc3BsYXk6Z3JpZDtnYXA6"
    "MTJweDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyfUBtZWRpYShtaW4td2lkdGg6NzIwcHgpey5ncmlkM3tncmlkLXRlbXBsYXRl"
    "LWNvbHVtbnM6cmVwZWF0KDMsMWZyKX19Ci50aWxle2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwuNyk7Ym9yZGVyOjFweCBzb2xp"
    "ZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEycHg7cGFkZGluZzoxNnB4fQoudGlsZSBoNHtmb250LXNpemU6MTVweDttYXJn"
    "aW4tYm90dG9tOjRweH0udGlsZSBwe2ZvbnQtc2l6ZToxMy41cHg7Y29sb3I6I2I2YzBkNn0KLmZpbmFse3RleHQtYWxpZ246Y2Vu"
    "dGVyO3BhZGRpbmc6NTBweCAwIDcwcHh9CkBtZWRpYShwcmVmZXJzLXJlZHVjZWQtbW90aW9uOnJlZHVjZSl7KnthbmltYXRpb246"
    "bm9uZSFpbXBvcnRhbnQ7dHJhbnNpdGlvbjpub25lIWltcG9ydGFudH19Cjwvc3R5bGU+PC9oZWFkPjxib2R5Pgo8ZGl2IGNsYXNz"
    "PSJ3cmFwIj4KPGRpdiBjbGFzcz0idG9wIj48ZGl2IGNsYXNzPSJicmFuZCI+c2ViYmk8Yj4ucHJvPC9iPiDCtyBTVEFSVCBIRVJF"
    "PC9kaXY+PG5hdj48YSBocmVmPSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9wcm92ZSI+UHJvb2Y8L2E+PGEgaHJlZj0iL3Bhc3Nwb3J0"
    "Ij5QYXNzcG9ydDwvYT48L25hdj48L2Rpdj4KCjxkaXYgY2xhc3M9Imhlcm8iPgogPGRpdiBjbGFzcz0ia2ljayI+TUFLRSBFVkVS"
    "WSBBSSBERUNJU0lPTiBQUk9WQUJMRTwvZGl2PgogPGgxPlN0YXJ0IGluIGZpdmUgbWludXRlcy4gUHJvdmUgaXQgZm9yZXZlci48"
    "L2gxPgogPHA+RXZlcnkgZGVjaXNpb24geW91ciBBSSBtYWtlcywgc2VhbGVkIHRoZSBtb21lbnQgaXQgaGFwcGVucywgdGltZXN0"
    "YW1wZWQgaW4gQml0Y29pbiwgaGVsZCBieSBpbmRlcGVuZGVudCB3aXRuZXNzZXMgYW5kIGNoZWNrYWJsZSBieSBhbnlvbmUuIEZy"
    "ZWUgZm9yIDkwIGRheXMuPC9wPgogPGEgY2xhc3M9ImN0YSBnb2xkIiBocmVmPSIvaW5zdGFsbC5odG1sIj5HZXQgeW91ciBmcmVl"
    "IGtleSDihpI8L2E+PGEgY2xhc3M9ImN0YSBnaG9zdCIgaHJlZj0iI3N0ZXBzIj5TZWUgaG93IGl0IHdvcmtzPC9hPgogPGRpdiBj"
    "bGFzcz0iYmFycyIgaWQ9ImJhcnMiPjwvZGl2PgogPGRpdiBjbGFzcz0ic3RhdHMiPjxkaXYgY2xhc3M9InN0YXQiPjxiIGlkPSJz"
    "Q2hhaW5zIj7igJQ8L2I+PHNwYW4+SU5ERVBFTkRFTlQgQ0hBSU5TPC9zcGFuPjwvZGl2PjxkaXYgY2xhc3M9InN0YXQiPjxiIGlk"
    "PSJzUGFzcyI+4oCUPC9iPjxzcGFuPlBBU1NQT1JUUyBJU1NVRUQ8L3NwYW4+PC9kaXY+PGRpdiBjbGFzcz0ic3RhdCI+PGI+fjUg"
    "bXM8L2I+PHNwYW4+T0ZGTElORSBQUk9PRiBDSEVDSzwvc3Bhbj48L2Rpdj48L2Rpdj4KPC9kaXY+Cgo8c2VjdGlvbj4KIDxoMj5X"
    "aGljaCBvbmUgYXJlIHlvdT88L2gyPgogPHAgY2xhc3M9ImxlYWQiPlNwaW4gdGhlIGRpYWwgb3IgdGFwIHlvdXIgcGF0aC48L3A+"
    "CiA8ZGl2IGNsYXNzPSJkaWFsd3JhcCI+PGRpdiBjbGFzcz0iZGlhbCIgaWQ9ImRpYWwiPjwvZGl2PjwvZGl2PgogPGRpdiBjbGFz"
    "cz0icGlja3MiIGlkPSJwaWNrcyI+PC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJzdGVwcyI+CiA8aDIgaWQ9InN0ZXBz"
    "VGl0bGUiPlRocmVlIHN0ZXBzLiBGaXZlIG1pbnV0ZXMuPC9oMj4KIDxwIGNsYXNzPSJsZWFkIiBpZD0ic3RlcHNMZWFkIj48L3A+"
    "CiA8ZGl2IGNsYXNzPSJzdGVwcyIgaWQ9InN0ZXBMaXN0Ij48L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24+CiA8aDI+U2ltcGxl"
    "IHByaWNpbmcuPC9oMj4KIDxwIGNsYXNzPSJsZWFkIj5TdGFydCBmcmVlLiBQYXkgcGVyIGRldmljZSB3aGVuIGl0J3Mgd29ya2lu"
    "ZyBmb3IgeW91LjwvcD4KIDxkaXYgY2xhc3M9InByaWNlIj4KICA8ZGl2IGNsYXNzPSJwbGFuIj48ZGl2IGNsYXNzPSJzY2FuIj48"
    "L2Rpdj48ZGl2IGNsYXNzPSJ0Ij5UUklBTDwvZGl2PjxkaXYgY2xhc3M9ImFtdCI+RnJlZSA8c21hbGw+Zm9yIDkwIGRheXM8L3Nt"
    "YWxsPjwvZGl2Pjx1bD48bGk+RXZlcnkgZGVjaXNpb24gc2VhbGVkIGFuZCBhbmNob3JlZDwvbGk+PGxpPlNpZ25lZCBwcm9vZnMg"
    "YW5kIEFnZW50IFBhc3Nwb3J0czwvbGk+PGxpPkZ1bGwgcHVibGljIHZlcmlmaWNhdGlvbjwvbGk+PC91bD48L2Rpdj4KICA8ZGl2"
    "IGNsYXNzPSJwbGFuIGhvdCI+PGRpdiBjbGFzcz0ic2NhbiI+PC9kaXY+PGRpdiBjbGFzcz0idCI+UEVSIERFVklDRTwvZGl2Pjxk"
    "aXYgY2xhc3M9ImFtdCI+NTBwIDxzbWFsbD5wZXIgZGV2aWNlLCBwZXIgbW9udGg8L3NtYWxsPjwvZGl2Pjx1bD48bGk+RXZlcnl0"
    "aGluZyBpbiB0aGUgdHJpYWw8L2xpPjxsaT5RdWFydGVybHkgZXZpZGVuY2UgcGFja3M8L2xpPjxsaT5SZXNlbGwgaXQgdW5kZXIg"
    "eW91ciBvd24gcHJpY2U8L2xpPjwvdWw+PC9kaXY+CiAgPGRpdiBjbGFzcz0icGxhbiI+PGRpdiBjbGFzcz0ic2NhbiI+PC9kaXY+"
    "PGRpdiBjbGFzcz0idCI+U0VCRE9HIMK3IE9OLVBSRU1JU0U8L2Rpdj48ZGl2IGNsYXNzPSJhbXQiPlRhbGsgdG8gdXM8L2Rpdj48"
    "dWw+PGxpPlJ1bnMgb24geW91ciBvd24gaGFyZHdhcmU8L2xpPjxsaT5Ob3RoaW5nIGxlYXZlcyB5b3VyIGJ1aWxkaW5nPC9saT48"
    "bGk+U3RpbGwgd2l0bmVzc2VkIGZyb20gb3V0c2lkZTwvbGk+PC91bD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJwbGFuIj48ZGl2IGNs"
    "YXNzPSJzY2FuIj48L2Rpdj48ZGl2IGNsYXNzPSJ0Ij5BVURJVE9SUzwvZGl2PjxkaXYgY2xhc3M9ImFtdCI+RnJlZSA8c21hbGw+"
    "dG8gdmVyaWZ5LCBhbHdheXM8L3NtYWxsPjwvZGl2Pjx1bD48bGk+VmVyaWZ5IGFueSByZWNvcmQgZnJvbSBhIHNwcmVhZHNoZWV0"
    "PC9saT48bGk+VGhlIHNhbXBsZSBub2JvZHkgY2hvc2U8L2xpPjxsaT5PU0NBTCBleHBvcnQ8L2xpPjwvdWw+PC9kaXY+CiA8L2Rp"
    "dj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24+CiA8aDI+V2hhdCB5b3UgZ2V0IG9uIGRheSBvbmUuPC9oMj4KIDxkaXYgY2xhc3M9Imdy"
    "aWQzIj4KICA8ZGl2IGNsYXNzPSJ0aWxlIj48aDQ+QSByZWNvcmQgbm9ib2R5IGNhbiBlZGl0PC9oND48cD5DaGFuZ2Ugb25lIGVu"
    "dHJ5IGFuZCBldmVyeSBlbnRyeSBhZnRlciBpdCBicmVha3MuPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9InRpbGUiPjxoND5UaW1l"
    "IG5vYm9keSBjb250cm9sczwvaDQ+PHA+VGltZXN0YW1wcyBhbmNob3JlZCBpbiBCaXRjb2luLCBjaGVja2VkIGFnYWluc3QgdHdv"
    "IGV4cGxvcmVycy48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0idGlsZSI+PGg0PldpdG5lc3NlcyB5b3UgZG9uJ3QgY29udHJvbDwv"
    "aDQ+PHA+SW5kZXBlbmRlbnQgb3JnYW5pc2F0aW9ucyBob2xkIGNvcGllcyBvZiB5b3VyIGNoYWluLjwvcD48L2Rpdj4KICA8ZGl2"
    "IGNsYXNzPSJ0aWxlIj48aDQ+QXV0aG9yaXR5IGF0IHRoZSBtb21lbnQgb2YgYWN0aW9uPC9oND48cD5SZXZva2VkIGEgc2Vjb25k"
    "IGFnbz8gVGhlIGFjdGlvbiBkb2Vzbid0IGhhcHBlbi48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0idGlsZSI+PGg0PlByb29mIHRo"
    "YXQgdHJhdmVsczwvaDQ+PHA+U2lnbmVkIGJ1bmRsZXMgYW55b25lIGNhbiB2ZXJpZnkgb2ZmbGluZS48L3A+PC9kaXY+CiAgPGRp"
    "diBjbGFzcz0idGlsZSI+PGg0PkFuIGluZGVwZW5kZW50IHRlc3QgYmVoaW5kIGl0PC9oND48cD5QcmUtcmVnaXN0ZXJlZCwgcnVu"
    "IG9uIHByb2R1Y3Rpb24sIHB1Ymxpc2hlZCBhcyBvYnNlcnZlZC48L3A+PC9kaXY+CiA8L2Rpdj4KPC9zZWN0aW9uPgoKPGRpdiBj"
    "bGFzcz0iZmluYWwiPgogPGgyPllvdXIgQUkgaXMgYWxyZWFkeSBtYWtpbmcgZGVjaXNpb25zLjxicj5TdGFydCBwcm92aW5nIHRo"
    "ZW0uPC9oMj4KIDxhIGNsYXNzPSJjdGEgZ29sZCIgaHJlZj0iL2luc3RhbGwuaHRtbCI+R2V0IHlvdXIgZnJlZSBrZXkg4oaSPC9h"
    "PjxhIGNsYXNzPSJjdGEgZ2hvc3QiIGhyZWY9Im1haWx0bzpqdXN0cmlnaHRkZWNvcmF0b3JzQGdtYWlsLmNvbT9zdWJqZWN0PXNl"
    "YmJpLnBybyUyMC0lMjBsZXQlMjdzJTIwdGFsayI+Qm9vayBhIGNhbGw8L2E+CjwvZGl2Pgo8L2Rpdj4KPHNjcmlwdD4KKGZ1bmN0"
    "aW9uKCl7CnZhciBiPSIiO2Zvcih2YXIgaT0wO2k8Mjg7aSsrKWIrPSc8aSBzdHlsZT0iaGVpZ2h0OicrKDE4K01hdGgucm91bmQo"
    "TWF0aC5yYW5kb20oKSoyNikpKydweDthbmltYXRpb24tZGVsYXk6JysoLU1hdGgucmFuZG9tKCkqMS4yKS50b0ZpeGVkKDIpKydz"
    "Ij48L2k+Jztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiYmFycyIpLmlubmVySFRNTD1iOwp2YXIgUEFUSFM9Wwoge2s6ImJ1aWxk"
    "ZXIiLG5hbWU6IkkgYnVpbGQgQUkgYWdlbnRzIix0YWc6IjAxIMK3IEFHRU5UIEJVSUxERVJTIixibHVyYjoiR2l2ZSBldmVyeSBh"
    "Z2VudCBhIHBhc3Nwb3J0LiBJdCBhY3RzIG9ubHkgd2hlbiBhIGh1bWFuJ3MgYXV0aG9yaXR5IHN0aWxsIHN0YW5kcy4iLAogIGxl"
    "YWQ6Ik9uZSBsaW5lIG9mIGNvZGUgYW5kIHlvdXIgYWdlbnQgY2FycmllcyBwcm9vZiBvZiBhdXRob3JpdHkgZm9yIGV2ZXJ5IGFj"
    "dGlvbi4iLAogIHN0ZXBzOltbIkdldCB5b3VyIGZyZWUga2V5IiwiVGFrZXMgYSBtaW51dGUuIEZyZWUgZm9yIDkwIGRheXMuIiwi"
    "Il0sCiAgICAgICAgIFsiQWRkIG9uZSBsaW5lIiwiWW91ciBhZ2VudCByZXF1ZXN0cyBhIHNpZ25lZCBwYXNzcG9ydCBiZWZvcmUg"
    "aXQgYWN0cy4iLCdAbmVlZHNfcGFzc3BvcnQoInBheW1lbnRzLnNlbmQiLFxuICAgIGF1ZGllbmNlPSJzaG9wLmV4YW1wbGUuY29t"
    "IixcbiAgICBwYXJhbXM9WyJhbW91bnQiXSlcbmRlZiBwYXkoYW1vdW50LCBwYXNzcG9ydD1Ob25lKTpcbiAgICAuLi4nXSwKICAg"
    "ICAgICAgWyJXYXRjaCBpdCBvbiB0aGUgY2hhaW4iLCJFdmVyeSBwYXNzcG9ydCwgcmVkZW1wdGlvbiBhbmQgcmVmdXNhbCBpcyBz"
    "ZWFsZWQuIFRyeSB0aGUgbGl2ZSBkZW1vIGZpcnN0LiIsImh0dHBzOi8vc2ViYmkucHJvL3Bhc3Nwb3J0Il1dfSwKIHtrOiJjb21w"
    "YW55IixuYW1lOiJNeSBjb21wYW55IHVzZXMgQUkiLHRhZzoiMDIgwrcgQ09NUEFOSUVTIixibHVyYjoiU2VhbCBldmVyeSBBSSBk"
    "ZWNpc2lvbiB0aGUgbW9tZW50IGl0IGhhcHBlbnMsIHJlYWR5IGZvciB0aGUgcmVndWxhdG9yLCB0aGUgYXVkaXRvciBhbmQgdGhl"
    "IGNvdXJ0LiIsCiAgbGVhZDoiUGx1ZyBzZWJiaS5wcm8gaW4gYmVuZWF0aCB0aGUgQUkgeW91IGFscmVhZHkgcnVuLiBOb3RoaW5n"
    "IGFib3V0IHlvdXIgQUkgY2hhbmdlcy4iLAogIHN0ZXBzOltbIkdldCB5b3VyIGZyZWUga2V5IiwiVGhyZWUgZmllbGRzLCBvbmUg"
    "bWludXRlLCBmcmVlIGZvciA5MCBkYXlzLiIsIiJdLAogICAgICAgICBbIlNlYWwgeW91ciBmaXJzdCBkZWNpc2lvbiIsIlBhc3Rl"
    "IHRoZSBzbmlwcGV0IHlvdXIgc2lnbnVwIGdpdmVzIHlvdS4gRnJvbSB0aGVuIG9uIGV2ZXJ5IGRlY2lzaW9uIGlzIHNlYWxlZCwg"
    "YW5jaG9yZWQgYW5kIHdpdG5lc3NlZC4iLCIiXSwKICAgICAgICAgWyJTaG93IGFueW9uZSB0aGUgcHJvb2YiLCJFdmVyeSByZWNv"
    "cmQgdmVyaWZpZXMgcHVibGljbHkgd2l0aCBubyBhY2NvdW50LiBLZWVwIGRhdGEgb24gc2l0ZSB3aXRoIFNlYmRvZy4iLCJodHRw"
    "czovL3NlYmJpLnByby9wcm92ZSJdXX0sCiB7azoiYXVkaXRvciIsbmFtZToiSSBhdWRpdCBBSSIsdGFnOiIwMyDCtyBBVURJVE9S"
    "UyIsYmx1cmI6IlZlcmlmeSByZWNvcmRzIGZyb20gaW5zaWRlIHlvdXIgc3ByZWFkc2hlZXQsIGFuZCBzYW1wbGUgd2hhdCBub2Jv"
    "ZHkgY291bGQgY2hvb3NlLiIsCiAgbGVhZDoiTm8gbG9naW4sIG5vIHBsdWctaW4uIFlvdXIgc3ByZWFkc2hlZXQgYXNrcyB0aGUg"
    "Y2hhaW4gZGlyZWN0bHkuIiwKICBzdGVwczpbWyJPcGVuIHRoZSBhdWRpdG9yIHRvb2xzIiwiRXZlcnl0aGluZyBpcyBmcmVlIHRv"
    "IHZlcmlmeSwgZm9yZXZlci4iLCIiXSwKICAgICAgICAgWyJEcmFnIG9uZSBmb3JtdWxhIGRvd24gYSBjb2x1bW4iLCJFdmVyeSBy"
    "b3cgdmVyaWZpZXMgaXRzZWxmIGxpdmUuIiwnPUlNUE9SVERBVEEoImh0dHBzOi8vc2ViYmkucHJvL2EvdmVyaWZ5P2hhc2g9IiZB"
    "MiknXSwKICAgICAgICAgWyJUYWtlIHRoZSBzYW1wbGUgbm9ib2R5IGNob3NlIiwiU2VlZGVkIGJ5IGEgQml0Y29pbiBibG9jayB0"
    "aGF0IGRvZXNuJ3QgZXhpc3QgeWV0IHdoZW4geW91IGFzay4iLCJodHRwczovL3NlYmJpLnByby9hdWRpdG9ycyJdXX1dOwp2YXIg"
    "Y3VyPTAsZGlhbD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiZGlhbCIpOwpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmluZyhz"
    "KS5yZXBsYWNlKC9bJjw+Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCci"
    "JzoiJnF1b3Q7In1bY119KX0KUEFUSFMuZm9yRWFjaChmdW5jdGlvbihwLGkpe3ZhciBjPWRvY3VtZW50LmNyZWF0ZUVsZW1lbnQo"
    "ImRpdiIpO2MuY2xhc3NOYW1lPSJjYXJkIjtjLnN0eWxlLnRyYW5zZm9ybT0icm90YXRlWSgiKygxMjAqaSkrImRlZykgdHJhbnNs"
    "YXRlWigyMTBweCkiOwogYy5pbm5lckhUTUw9JzxkaXYgY2xhc3M9Im4iPicrcC50YWcrJzwvZGl2PjxoMz4nK2VzYyhwLm5hbWUp"
    "Kyc8L2gzPjxwPicrZXNjKHAuYmx1cmIpKyc8L3A+PGRpdiBjbGFzcz0iZ28iPkNob29zZSB0aGlzIHBhdGgg4oaSPC9kaXY+Jztj"
    "Lm9uY2xpY2s9ZnVuY3Rpb24oKXtwaWNrKGksdHJ1ZSl9O2RpYWwuYXBwZW5kQ2hpbGQoYyl9KTsKZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoInBpY2tzIikuaW5uZXJIVE1MPVBBVEhTLm1hcChmdW5jdGlvbihwLGkpe3JldHVybiAnPGJ1dHRvbiBkYXRhLWk9Iicr"
    "aSsnIj4nK2VzYyhwLm5hbWUpKyc8L2J1dHRvbj4nfSkuam9pbigiIik7CkFycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwoZG9j"
    "dW1lbnQucXVlcnlTZWxlY3RvckFsbCgiI3BpY2tzIGJ1dHRvbiIpLGZ1bmN0aW9uKGIpe2Iub25jbGljaz1mdW5jdGlvbigpe3Bp"
    "Y2soK2IuZGF0YXNldC5pLHRydWUpfX0pOwp2YXIgYXV0bz1zZXRJbnRlcnZhbChmdW5jdGlvbigpe3BpY2soKGN1cisxKSUzLGZh"
    "bHNlKX0sNDIwMCk7CmZ1bmN0aW9uIHBpY2soaSx1c2VyKXtjdXI9aTtpZih1c2VyKXtjbGVhckludGVydmFsKGF1dG8pfWRpYWwu"
    "c3R5bGUudHJhbnNmb3JtPSJyb3RhdGVZKCIrKC0xMjAqaSkrImRlZykiOwogQXJyYXkucHJvdG90eXBlLmZvckVhY2guY2FsbChk"
    "aWFsLmNoaWxkcmVuLGZ1bmN0aW9uKGMsayl7Yy5jbGFzc0xpc3QudG9nZ2xlKCJvbiIsaz09PWkpfSk7CiBBcnJheS5wcm90b3R5"
    "cGUuZm9yRWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoIiNwaWNrcyBidXR0b24iKSxmdW5jdGlvbihiLGspe2Iu"
    "Y2xhc3NMaXN0LnRvZ2dsZSgib24iLGs9PT1pKX0pOwogdmFyIHA9UEFUSFNbaV07ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInN0"
    "ZXBzTGVhZCIpLnRleHRDb250ZW50PXAubGVhZDsKIHZhciBsaW5rcz17MDoiL2luc3RhbGwuaHRtbCIsMToiL2luc3RhbGwuaHRt"
    "bCIsMjoiL2F1ZGl0b3JzIn07CiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgic3RlcExpc3QiKS5pbm5lckhUTUw9cC5zdGVwcy5t"
    "YXAoZnVuY3Rpb24ocyxrKXt2YXIgZXh0cmE9IiI7CiAgaWYoaz09PTApZXh0cmE9JzxhIGNsYXNzPSJjdGEgZ29sZCIgc3R5bGU9"
    "Im1hcmdpbjoxMHB4IDAgMDtwYWRkaW5nOjEwcHggMTZweDtmb250LXNpemU6MTIuNXB4IiBocmVmPSInK2xpbmtzW2ldKyciPicr"
    "KGk9PT0yPyJPcGVuIHRoZSBhdWRpdG9yIHRvb2xzIOKGkiI6IkdldCB5b3VyIGZyZWUga2V5IOKGkiIpKyc8L2E+JzsKICBlbHNl"
    "IGlmKHNbMl0uaW5kZXhPZigiaHR0cHM6Ly8iKT09PTApZXh0cmE9JzxhIGNsYXNzPSJjdGEgZ2hvc3QiIHN0eWxlPSJtYXJnaW46"
    "MTBweCAwIDA7cGFkZGluZzoxMHB4IDE2cHg7Zm9udC1zaXplOjEyLjVweCIgaHJlZj0iJytzWzJdKyciPk9wZW4gaXQg4oaSPC9h"
    "Pic7CiAgZWxzZSBpZihzWzJdKWV4dHJhPSc8cHJlPicrZXNjKHNbMl0pKyc8L3ByZT4nOwogIHJldHVybiAnPGRpdiBjbGFzcz0i"
    "c3RlcCI+PGRpdiBjbGFzcz0ibnVtIj48c3Bhbj4nKyhrKzEpKyc8L3NwYW4+PC9kaXY+PGRpdj48aDQ+Jytlc2Moc1swXSkrJzwv"
    "aDQ+PHA+Jytlc2Moc1sxXSkrJzwvcD4nK2V4dHJhKyc8L2Rpdj48L2Rpdj4nfSkuam9pbigiIik7CiBpZih1c2VyKWRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJzdGVwcyIpLnNjcm9sbEludG9WaWV3KHtiZWhhdmlvcjoic21vb3RoIn0pfQpwaWNrKDAsZmFsc2Up"
    "OwpmZXRjaCgiL3gvcm9zdGVyL2xpc3QiLHtjYWNoZToibm8tc3RvcmUifSkudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29u"
    "KCl9KS50aGVuKGZ1bmN0aW9uKGQpe2lmKGQmJmQuY291bnQhPW51bGwpZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNDaGFpbnMi"
    "KS50ZXh0Q29udGVudD1kLmNvdW50fSkuY2F0Y2goZnVuY3Rpb24oKXt9KTsKZmV0Y2goIi94L3Bhc3Nwb3J0L3N0YXR1cyIse2Nh"
    "Y2hlOiJuby1zdG9yZSJ9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiByLmpzb24oKX0pLnRoZW4oZnVuY3Rpb24oZCl7aWYoZCYm"
    "ZC5wYXNzcG9ydHNfaXNzdWVkIT1udWxsKWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzUGFzcyIpLnRleHRDb250ZW50PWQucGFz"
    "c3BvcnRzX2lzc3VlZH0pLmNhdGNoKGZ1bmN0aW9uKCl7fSk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/start": (_d(_HTML_B64), "text/html; charset=utf-8"),
}
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_startpage_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._startpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "startpage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/stats.py`

143 lines, 5540 bytes

```python
"""
Live figures for the Proving Ground - /x/stats

Charts on a compliance site are usually decoration. These are not, provided
they show something a visitor could otherwise only take on trust: that the
chain is genuinely growing, that decisions really are distributed across the
thresholds rather than hand-picked, and that people who click through a
review case behave exactly as the oversight argument predicts.

WHAT IS PUBLISHED, AND WHAT IS NOT
----------------------------------
Public and no key, because a figure nobody can see proves nothing.

Published: total chain height, hourly block counts, the verdict mix and score
distribution of PUBLIC DEMO decisions only, and dwell times from public review
cases.

Never published: anything scoped to a customer key. No customer verdict mix,
no customer volumes, no per-key anything. A visitor learns how the engine
behaves, not how any operator's business is going. That distinction is the
whole reason this endpoint can be open.

    GET /x/stats        everything below
    GET /x/stats/chain  chain height and hourly growth only
"""

import json, time
from datetime import datetime, timezone

VERSION = "1.0"
PUBLIC = {("GET", ""), ("GET", "stats"), ("GET", "chain")}

DEMO_KEY = "public_demo"


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _chain(ctx):
    t = time.time()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*),MIN(ts),MAX(ts) FROM audit_log").fetchone()
        recent = ctx["conn"].execute("SELECT ts FROM audit_log WHERE ts>? ORDER BY ts ASC", (t - 86400,)).fetchall()
    height = row[0] if row else 0
    buckets = [0] * 24
    for (ts,) in recent:
        h = int((t - ts) // 3600)
        if 0 <= h < 24:
            buckets[23 - h] += 1
    return {"height": height,
            "first_block": _iso(row[1] if row else None),
            "latest_block": _iso(row[2] if row else None),
            "last_24h": buckets,
            "blocks_last_24h": sum(buckets),
            "note": "Every block, from every source. The chain is one sequence."}


def _demo(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT result_json,ts FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (DEMO_KEY,)).fetchall()
    verdicts = {"ALLOW": 0, "CHALLENGE": 0, "BLOCK": 0}
    # ten buckets of 0.1 across the score range
    hist = [0] * 10
    scores = []
    for res, _ts in rows:
        try:
            r = json.loads(res)
        except Exception:
            continue
        d = r.get("decision")
        if d in verdicts:
            verdicts[d] += 1
            s = r.get("score")
            if isinstance(s, (int, float)):
                scores.append(s)
                b = min(int(float(s) * 10), 9)
                hist[b] += 1
    total = sum(verdicts.values())
    out = {"decisions": total, "verdicts": verdicts,
           "score_histogram": hist,
           "buckets": ["0.0-0.1", "0.1-0.2", "0.2-0.3", "0.3-0.4", "0.4-0.5",
                       "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"],
           "thresholds": {"allow_below": 0.35, "block_at_or_above": 0.70}}
    if scores:
        scores.sort()
        out["median_score"] = round(scores[len(scores) // 2], 4)
    return out


def _oversight(ctx):
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT dwell,human_verdict,machine_verdict FROM demo_cases WHERE committed IS NOT NULL").fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"reviews": 0,
                "note": "Nobody has taken a review case yet."}
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    agreed = len([r for r in rows if (r[1] or "").upper() == (r[2] or "").upper()])
    # dwell buckets in seconds
    edges = [2, 5, 10, 20, 45, 90]
    labels = ["under 2s", "2-5s", "5-10s", "10-20s", "20-45s", "45-90s", "over 90s"]
    hist = [0] * 7
    for d in dwells:
        placed = False
        for i, e in enumerate(edges):
            if d < e:
                hist[i] += 1
                placed = True
                break
        if not placed:
            hist[6] += 1
    n = len(dwells)
    return {"reviews": len(rows),
            "agreed_with_engine": agreed,
            "agreement_rate_pct": round(100 * agreed / len(rows), 1),
            "median_dwell_seconds": (dwells[n // 2] if n else None),
            "under_2_seconds": hist[0],
            "under_2_seconds_pct": (round(100 * hist[0] / n, 1) if n else 0),
            "dwell_histogram": hist,
            "dwell_labels": labels,
            "note": "Visitors who committed in under two seconds did not read the case. That is the pattern the oversight record is designed to make visible."}


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404
    if action == "chain":
        return {"stats_version": VERSION, "chain": _chain(ctx)}, 200
    if action in ("", "stats"):
        return {"stats_version": VERSION,
                "generated": _iso(time.time()),
                "chain": _chain(ctx),
                "public_decisions": _demo(ctx),
                "public_reviews": _oversight(ctx),
                "scope": "Public demonstration activity and total chain height only. Nothing scoped to a customer key is published here."}, 200
    return {"error": "unknown_action", "action": action,
            "available": ["GET stats", "GET chain"]}, 404

```


## `modules/studio.py`

1228 lines, 60638 bytes

```python
"""
modules/studio.py  v4.0.0
Monop Studio. Creators upload a video at /create and get back:

  * a teaser video saved to their phone, ready for TikTok, Instagram,
    Facebook and YouTube - the first few seconds play clear, then the picture
    blurs behind an end card with the video's link and a QR code burned into
    the pixels, so it survives any upload anywhere;
  * a short link, https://sebbi.pro/v/<id>, that opens straight onto that
    video in the 10p Wing (modules/cinema.py);
  * a channel link for their bio, https://sebbi.pro/cinema/@<name>.

Viewers watch the teaser free, then pay 10p to watch the rest. A viewer with
no credit taps Google Pay or Apple Pay once (Stripe Checkout), GBP 1 or GBP 5
lands on their phone as credit, 10p comes off and the video plays. No account.
Stripe's card fee (1.5% + 20p) is added on top of the credit and shown before
paying, so the full credit is spent on videos: GBP 1 credit costs GBP 1.22.

The creator gets 70% of every paid view, less 50p a month per video which is
only ever taken from that video's own earnings - a video that earns nothing
costs nothing. Balances and payouts run on modules/credits.py (/earn), and
every paid view, payment and upload is sealed into the chain.

Routes (all served by a runtime do_GET / do_POST patch, like credits.py):
  GET  /create                       the creator page
  GET  /v/<id>                       one tap -> the video in the 10p Wing
  GET  /v/<id>/teaser                the free teaser video
  GET  /v/<id>/poster.jpg            the still
  GET  /v/<id>/full?viewer=&t=       the full video, for viewers who paid
  POST /v/api/join | signin | new | chunk | finish | mine | delete
  GET  /v/api/state?id=&viewer=      unlocked? balance? price?
  POST /v/api/unlock | pay | paid | report
  GET  /v/api/admin?key=&do=list|remove&id=     (CREDITS_ADMIN_KEY)
  GET  /x/studio/status              arms the routes after a deploy

Railway variables (all optional):
  STUDIO_DIR          where videos are kept (default: the folder DB_PATH is in)
  STUDIO_MAX_MB       biggest upload in MB (default 500)
  STUDIO_PACKS        credit packs in pence (default 100,500)
  STUDIO_MONTHLY_FEE  pence per video per month, from its earnings (default 50)
  STUDIO_CARD_FEE_PCT / STUDIO_CARD_FEE_PENCE   the card fee added on top (1.5 / 20)
Stripe uses the key server.py already has (STRIPE_SECRET). Apple Pay and
Google Pay show on the Stripe payment page when they are switched on in the
Stripe dashboard (Settings > Payment methods).
"""

import base64
import gzip
import hashlib
import hmac
import importlib
import json
import math
import os
import re
import secrets
import shutil
import sys
import threading
import time
import urllib.parse
from collections import defaultdict, deque

VERSION = "4.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

SITE = (os.environ.get("HOST") or "https://sebbi.pro").strip().rstrip("/")


def _int_env(name, default, lo, hi):
    try:
        return max(lo, min(hi, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


MAX_BYTES = _int_env("STUDIO_MAX_MB", 500, 20, 4000) * 1024 * 1024
TEASER_MAX = 120 * 1024 * 1024
POSTER_MAX = 4 * 1024 * 1024
CHUNK_MAX = 9 * 1024 * 1024
MONTHLY_FEE = _int_env("STUDIO_MONTHLY_FEE", 50, 0, 1000)
FEE_PERIOD = 30 * 86400
SHARE = 0.70
PRICES = (10, 20, 50, 100)
KEEP_FREE = 1024 * 1024 * 1024


def _packs():
    out = []
    for p in (os.environ.get("STUDIO_PACKS") or "100,500").split(","):
        try:
            v = int(p.strip())
        except ValueError:
            continue
        if 50 <= v <= 10000 and v not in out:
            out.append(v)
    return sorted(out) or [100, 500]


PACKS = _packs()


def _fee_env(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return float(default)


CARD_FEE_PCT = _fee_env("STUDIO_CARD_FEE_PCT", 1.5)
CARD_FEE_PENCE = _fee_env("STUDIO_CARD_FEE_PENCE", 20)


def _charge(credit):
    """What the viewer pays so that, after Stripe's card fee, the full credit is left."""
    return int(math.ceil((credit + CARD_FEE_PENCE) / (1 - CARD_FEE_PCT / 100.0)))

ID_RE = re.compile(r"^[a-z0-9]{8}$")
VIEWER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
OWNER_RE = re.compile(r"^owner:cr_[a-f0-9]{20}$")
SESSION_RE = re.compile(r"^cs_[A-Za-z0-9_]{8,200}$")
TITLE_CLEAN = re.compile(r"[<>\"\\\x00-\x1f]")
ALPHA = "abcdefghijkmnpqrstuvwxyz23456789"

KINDS = {"full": ("full", MAX_BYTES), "teaser": ("teaser", TEASER_MAX), "poster": ("jpg", POSTER_MAX)}

_ctx = {}
_cr = None
_ready = False
_patched = False
_dir_cache = None
_ulocks = defaultdict(threading.Lock)
_wins = defaultdict(deque)
_wins_lock = threading.Lock()

_CREATE_GZ = (
    "H4sIAAAAAAACA7V9TZPbyJLYXb8Cg5lpAU0QDbI/RTaobWlao97R11P3G+24X48CBIokRBCAAJDsXooR72SHwxGO8O6GHY5Yxx42"
    "7NOefPBefFr/k/kD3p/gzKwCUADBlubN80yoCRaqsrKy8rMqq3j61Xevn1799OZcmWSzYHCKf5XACce2ykIVvjPHG5zOWOYo7sRJ"
    "UpbZ6u+vnrVP1MEDXhw6M2arC58t4yjJVMWNwoyFUG3pe9nE9tjCd1mbvhh+6Ge+E7RT1wmY3THyVu2Rn9lutGBJDWw2YTPWdqMg"
    "SiTIX1uH1rE1wrqZnwVs8DIKo1i5zOaeHym//PHvFOYkoTJKoplyF80TZeQnaaZgb6d7vEWlF4+lbuLHmR+FUi+/j4PI8RQH2nks"
    "MpQxy+BLxpyUAcQoUa786VU0NZSLMM2cceLMDOWZ47JhFE0VJ/SUn6L51XzIDPpCGB3HSjRSGIzzTulYsbKcsFCJWRQHTFk6mTtR"
    "YMBKwgBZP6RnrPXOD8em8iqCToMgWrIkVULGPOaZBbXiJIpZkt3ZajTu0QilgXw5dZrhNZNHwkeZwcTO5rPUVN5EAAoRF3RywjsY"
    "ZAJEaCSAGGXKhkPfhE7L8SIqgR9OlUnCRrY6ybI47e3tjaD71BxH0ThgTuynphvN9tw07T4eOTM/uLMvnrxsvQnYbQtH3VuOJ9lf"
    "HFhW/xD+HVnWTr3WpROmG7X6x2XNV2yZJiAELOlFcfrXBtU9Ms3jrgG1dzw/jQPnzk6XTqzCzAW2mmZ3AUsnjGU4Bvo2eNBLoihb"
    "tdvjKPB6X7uPnJMDt99uR9Pe18cjtj+04MswmLPe1ycjzxqN4GsMo+997R0+GtLX2TzDt86jfceDr0Ab1kvGQ0frHh4a+T+zo8M7"
    "10mgE2vUOd5HuDOkxEMYsoJDVpAwD425T+VpDBxrFE9QO0WKlLWRQA+N9C7N2Kw99w183YaZ9REn+uw9LGn00PieRcnYdwx6tX6w"
    "uxpGt+3U/2uY094wSqBOG0r6MwdqhT2rHzueh+8A0SUbTv2snTlxe+KPJwH8y7js97IEuo2dBDhv/QB1lDGMvLvV0HGn4ySah14v"
    "cTzULGP8hFoaCwI/TpniZMqh9a1ifWt83fE61oFFj1yBKEfdb3Vg/1vm5UV93t/X7IR5o+M+slubc0Jv4SQaJ4/eB4ZvTxgi2OtY"
    "1rfrB86KN+SVcOr09YPhPMuicCUD8UOQBh8GYWZRvBLc0xsBpfsf5mnmj+7aQsJ6NCHtIcuWjIV9B8gRtn2YhbTnwmuWFKQDZepq"
    "nW58q7QUFi601BmxNtDKafshKOw29KTrSucIKlhA+FuujHvHR1ZcToTizLMI0BoCpb3V5riRRXROD5hN1uvsQ+MqsTJ2m7U95kaJ"
    "g7qiF0YhW3OAynCTPhzYklMRZInTBFTyQnG+BIFugYCoAAKiNyIhBtkO2Ajm6yC+ha6WiROv7iVGyZqcdscWNYT5i1bUC01JfTK6"
    "RGblhOpOfXf6JUPpQN8BywBOG2cd4ZhdNus38NSk0wCQhG2DoFIPbuDMYm0fhm6cmIeLpXEICOp9VCIFH5vWQU6AExpDhwY86Shs"
    "xvskXQYUTWZO0JdkD8E4SSl7jyyPjQ2hugyh0Qyh6PRC0EsIbReEtYdE7TcWNigBE/S/J5jqa/fAHXquTNEjms18dg8bWR1UWpwW"
    "MjhOfK+Pf9ogY1CSkd8xn4E2TFjMnEzbNzqjRO+PnRgJlIPrWkSsI5pwAql4/qKimlBLd/aNrmXsHxnmsd7nirAH066kUeB7Cp9G"
    "pGP+so3EnKfErgVzkZDjtPQ3GVCWDPOwFE5OmwK3YTHgYRC5U6lZt6QRqGjQXLMeF5XYCVmwume+Oyd8wjudjgMj/NpyOla32zBM"
    "bq+AFJ3cXpXV8gETGsWAS0KjGuPzShZl4njREubSAvUO8DchWyd6jrsy6f4pQtM9uo8gSmymOf8NH7kd70CegoONpjh36weBMwRa"
    "bk5BD9wOhaZXVhGb6k0wHcLnTLehN6xDNls/8MN4nl1ndzGzkVVuDCoA2c00Kr3RwUIHzM1WXELQiski/bU17HS7B9umsOJynOg1"
    "Q1Dj4K48oWg2aMCkUyWbKnDujSJ3ngrk+JdVNM/I3SFdLoA3qEYziZZfIs4gxQr8I0HmOs6MUVFXrHGDva0b6FzwoHrb8xPAFw0O"
    "74WA4/RI5JWdBuJyQVycdc8Bj7FJQA4ONzQCyUBNvVRZ/7A+I+48SeFrHPmFruAcV5uEcp4OmpSMoJSSggEISKRQZL6Ab0VDc+Kk"
    "KzEabkyIqZrmNKIZdSesPjH5rFVmiOYAorAkq2iLA8FsucvSqBepD4WYTwgDTY6YKVkrEkzs2UVyCHRzDx1R4C4POFFZKIYJfu19"
    "+hzFmHQc0fIYaXlYmxFppmXnSXTeObAcENPa/DY6QTkV/ZDM/q/kcmH1+ODM0RzmX2btmoouBnhUnYHjAsJ4ApHihpWsKBbrqFmx"
    "fE4b5T1AqLXaoB6WFmC5zy/qR9PN2tFUqtvtFHUTVgEteSZ59dHokXfi3INx5/DY6OyfgITnCKezVU63R8gX3Rr3Fhqj4CUrJ2cP"
    "JtcZBoBVhHYgu+uZh/Bmlo5XG/wvzxUxt6SWcIaxFUbY3qouj/RmWLpdfIzo57I7MMqr3Dh1KdKQrcloNKpx7H024qAiEAc15bKE"
    "lu0hhDfTHv0FDRWgX+57rNAUyPBf+TNcW3LIW4RGU8V1wgUooArf3uZjP7IWk340/ABqHJejesj/jh82IVqxk+AyVMw5ToiTrApF"
    "vzFrjx416e8K44NFxcWwUQAuDozLg/ivNmu8F8WvuRJSTCosj/UbHHVia580CAFTzP1UOJJBVSnfbwMrfKHUlPJB4TgH5Dhv2o7y"
    "pQnRdEOAvsxn0JLresADq02TgsV8SW8bI3SBEf6EWQeXNGE1/yO3VTWjhFYniu9WcnHJKF8WF1QkppPri+1hx5EuelXMyap0ADqf"
    "dTk3HMwjiEx/28pFaUwEQopYKpHQl5y9eyOIA30zTK7R6kQi1WEeQUkkMA/rRKiY0wLNbNXs4eP8ka9X10xYgMsafrxqXjkRgWud"
    "Dxrm9V5+5FPdPTa68K9zDLNtHW8LvyrVuofIFTO2+u3zyYmKegCXVnr4h0A3Lf3gC5jeu98cfPM4KAf35w28KxNhbXGHeb/bg+rO"
    "o9oqFbej1ArIyhcHAfwmCza40KC1voRij9CpLwIciXuE/9ow9MoCg8W7UvzZWKhIhJjbliNk/IqdBEvVIHCyuuw4HWv/RIDNxajU"
    "2hVzgJTIa6aCPJ3Pk0eWof0SgtNgpwr+rBkoaivUkhO4q5pTK4oVDDP3/8Q4kwOAePYz6xFEC1yuq/NOgx8wwp2F5vWg3heod5lu"
    "CJDgKU6DHX5wusd3M073+LYgrsEPHpyC1Clu4KSprQIUdXDq5F9p7VcVWzh76gBxiE+HAyWlzajTPXj8l38ut39O95zBaegsEIRo"
    "BDaHzRx1kG8MUZXiLW4qqYM3zh2QNKVXe9R8D3CqYobzrQ4eKHIZLuViWaUQ12zVwavXyrPXL168fnf+9lJ5dX7+3fl3AijUnnQG"
    "59UttFM2G5TbaObpHnwHKnWoepyDxiVLdSD2FaPQZZv7ZVH4pduKJpSGqZI5MbQHORtPlCyq7BlS7djhO23wrrrDaCowEQBLmTIW"
    "1zfmcGbEviUVxSwM7xQ/xY3BBQsRTYTjTsBDhtHGdSLSWiNwAlIMuvnXf/iP/4QgxdCJZOSCcZqW1f72f2K1OlEIB9pGrNf/m3/G"
    "+t+zDAcQQ9XYQc1GG71UScyZ+KxOPy3jqYrv2eriL8HUc1aYdAdPA8cXE+uCHc+ihDaKYUK71QmFIV5kD1NRdeKEuC4YhZuzgAUI"
    "gtdEroU3qTKGCYsK+tHaIO4s2+qHV1BZHTx9e3529fqt8urs5fnpHr0fnNJKBWHNaynguwYsHGcTWz2wVFrddiPQRSxjthqNRqoC"
    "esllE4h8GcBm5tjkeHBOI8T42LkXVkhvBiwOgT4n0YcnGVCIk8bPgOxUtz7xECGK6i/haVDKjDS46UWoKqRJoH6pfbpge9TB2QsY"
    "83c/Kc/PfjxXzpQfzn963DByAvG5gbrT97/88X9sGxktQEjjm9L4LkGDKn742eFNK8Pbzl4KhqWCx35gdwWLXToLwQwQO5uNnHU1"
    "AXmDtyh2k2iJtSkHgVgcmSovnDmhM2aSVKWmQmyZQice50cU3Ql4HabyA4o7aGj0aNNoxkiuFNwzBF6MmoSZR/di3OzuEvqVZ/YL"
    "SMvunkJ3wD3Y6ewOR1Wh8H18B3W/By198XDBxID8DI1GNT1DAvdlk/HSmbIN3Y9ycIpuGfEBdhUqTgr4UZsZ41KJKgdMIVbbOvh0"
    "xvsBu8T5aumD8i2wrMnF4KfXv3+r/Hjx3fnrnNk3yYILqBwoPhHU//u//4PyBhdkcyrQwuzgWWGXxvAV9XeEWR4BS5FwczIGNEw+"
    "LOf25VAdHFqWGJTy8gk8EaTKLHHxoz0FFaFxZPgTLonGGeYBARp7u2phYpHidQXAE1QGqNWUiytFe3P++s2Lc+Xy/Ozt0+fKk5+U"
    "q+cXl3qD2IvMFknhnVg1oX83cZD1UeESLoqLJPAeb8x1glwMZQq3JhJ6ceK7gN6btxdPz5Wr18q7sytA6+r5ufL2/PKqQItvUfAJ"
    "4S1OI0qSAYcrmAONOoAbr8Q88l+A+LkQH4OJ5bXrrbqWOuhWK0OUs632oYUzV6m9f7i1dseC6v/yj50KJpZUfY/jW/LnJnVGCYOh"
    "Pnt7jhP29PWr7y6bKMJr1ZEFXIEiEFZ66TYUTySanXyucqcLjmH3c7U4RTdrbQy2bq0Ep9AGgTqo8D+VFVoxwUgmzXUHKW7OfPAw"
    "AwcWBQ46C7hL5SODBgxkk8pBnZq5Otkq/FWdOI5I/FGHoTrlff3yb//ms2Zr9qVmi9ZLJXX5Dr7nxotKlldciAEHdHJI23B3DWxu"
    "oz0jw0OWKAWvCp1I8CqVeZj5AScJrswV9oev1VJX7gJR5gVNjmbAHU2qm3aAI5C9BV6SF9mYskcTkrvXpXfJYQF3dUtTUwwT56Hu"
    "vvIG++pgHxt8H2HlwAeTVcvjq7qllaEMnQSZjCDB8wUO2m+uWsznsuZl3WeLpemEoOESN8vAyXDIGtDW2ZfZUFo/lTjjO/jeHETl"
    "Pl4thFUHv/z93yovLsC/u3hFapWIc/HqeynC6jY4iEfoH/5UMhpKF6ad3eEIYhhm6UcJ6cOhUtUfyUrcpXzvi5IYkyhIgXJUc4Or"
    "cClXWIf75BD9kSvqoMmhBbXzyz/9O4VcPcDwzSTKolQW0a3zJaAjFgI8j4nSLHFQ1SC4e8JEkkC5mybWQdyr3KNIgXsVE5RU5N48"
    "lP9aHbyjYNLPNhncqapSqW+XnMBKBA4cePHD1esflB1nFveBIS6vzr5/e/ZSeXr25uri9aucQp6TOW1sD1Cc+Iy7kjV3qrIQwRHn"
    "de8RukaUnp09PX/y+vUPhgJ+2dXvn5wL7P5K0V5cvPpBubhUrs7evDl78uJcb0bwya9A8MmvR5DcxScXrxVCBxTO61fn/PkZRItn"
    "L14opUN52Yzh01+B4dN7Mcz8GNgTLCMpx6EfKZS3W6xkkIotFS5f9zinZQUupuiJoPgqtN6eInPLATU3miNc7ACYZ6GXRBAAgTlQ"
    "nCAFwXfmKaumHMNbP3EDXupGHokfWRsfdcQ9yhKcSEm8nbHj52bWCSOAlvz6OMNvUI/pRKFAArTVT2XURtqrQQaLYAIJ8gJoK4nh"
    "y7ucTHz1q8lY4GJzsRbD3YAnDhhNvswjfBZwcy+unn/39uxd4YtISy281Y8+W4Iht8pmb84uvgM2O393ub3V0whsfKWV4MtKiwJz"
    "Z8uEyCt+zcr2nZ9NvMRZFgw0dIAPyS1ympi2AQouqaoDHCdm2ePaGbGQkwAWjPF8fShBixNDIGVABM27Oo4pBmNLNEohLlhBlTl4"
    "iZ6pvMNWyORLgaChXGaJH7OH1AWEiATchWAcWHw0gm4ohklx74UUa0uxzO7htwYYsTnEcP/YJWdGSt7PIYNLyRzQyzDn2QR6FsXk"
    "jbAUoWeAy4yhMI1wkNhzalb5hmbthY/Kv4FCtErzBR4kLnUXyx0YlcEA5wEt/tEC2OPCWFeDsv2cVaWYwxWcR5ymvDmvxcpShChq"
    "8nSeGYi+rYbzGYP4TM3DgX0LoyCZUeWe3joZSObz1++Ul2evflLenP2kaN82xaK8ptyRx1wfoma1DGXuU5vbh+rRSFFElDPl5etX"
    "V8+bB+rdP87OPaN8I4W4TeFbXmEzoh10rM+Frp+JVT8XnG4L0BqpCMIjdONreILm1qYhK1we9zuWNXqltL+xwdWVjnBXRG3Yl7iq"
    "+T5oje/Zn6i+VgfVrQ+xbSGE6pQfuxk82NtVLnE5RvndW4WFaNCSnjK8yyD4g2dDYUkC6iAArRMoLw0FlE8K9EuVTvvIVN6ybJ7A"
    "F0dJP87BoVScJAG9Fo0Ua69jKrt7D0bzkNI2lBkYut+91XAvSV89wH0j6iW1r28M3/jQx4K5PQ9ZCk4B0zgqvwceimYxGJkw401x"
    "DyvRfNvq+6dzk6/U9P1WSydgZjxPJ9rcxONkT6H9Wab50IR396N9HYK2N667R0bHMjo3xvXBgdE5oqdjy+jyJ2AVo3NidPFx/8Do"
    "HvDH4y5WPbi5EdDOXuTg4C20PKGPbpd/HNHHvsU/ylZAPtsSQ+jAEOwjQn6F7zzX/vHav7m2btr02bnZpc/uTd8faZ67ezKwD1on"
    "LT5SPvTdE2gLMP0+JQWs1w8UqPsVFOm4cbMEc7FUznEKNZU8pywCFyoClY1K/ndv1Zw4WZQ5AfQPLREDg7lh/g2IEg7zLzA+z13a"
    "VL0NlXbDoRHaneMWvN09EMCGfobz2i8mH/SItjACfYUjxxpTO2h3+tMBEGPabuvYgM+dthgMBlN9p6PDULDZgXGg9/FBHrZxovf5"
    "dwB4DkZJy7vShvqKakOVNQ6uZJeDnR3qh4M4hWHsnnDWKXq39P5y4gdMkyp+e1KtwIeIDi8NsQAvNQGo9gmf1KGY7g/w+eH0pP8B"
    "+7O14elpR/+ETa791oebPoLjPQxx4DlUKi7xJWzLqv633ced4153/yjH6vyv3qA8vXj9PX7cAouV+HUPDzmvQSVgK/u2D9Wub2+A"
    "d25PT5EbR9rtTvfwSL/92e6eHK55U2p2etjpUmPRlj7a8Ar5uhTxeaA5BkxAQmpBcYDgj7EqduTctPBjeHPTs9Yc2zELbeAuCUdg"
    "qFIewnFOYE48G+rnBEYyhuPrDze29uG0LH8Mj1DYs/SftQ8D6zFiREVtYGKOuw4v+9hzOF5LuDNXGwZT3nFiw6MJcbzrZBoK0Blq"
    "NQ2Q082RHwTABVwNYeUYcItPsYFALc7xd+3kOibZdfW89keo/VFCuP8RakO11sebn+0c2483hquvBRETMw3AXGplD7ogXwxyD0yx"
    "BxJImSGkSpmbVtkyHJYUHQY2cQ+H6O8CBEPzWx0dn0CiCIpgw0DvAyz+hYij5/2C+Fd6gLbURTlT0CdOkLvMYSFcmBckf8Nsb20I"
    "COSteNczHOIorI2QD3DG25TzVZmtcNvbEQR6jMZW8ELKMi0xXGOhr2DyElBSOzsu/U1OQ3g8DaG3a1CG7o29eNzpgYSH4muWzNla"
    "hjXyQ7CoCK5Ufo4Nus85tY/7jhg91xRQOsTSYWER7JcOuNoz51ajB2eYak57XzeKb0P4pvcJ4ZZjuK2h4X1l292dHfwAhecQ2kP6"
    "Cz0ewTP81QlFjpllgDwUz2H7uPgGz4ZVqtATJHWba8wV9ngEdhtUkG3bFkfBN46KAsErYFPOXpDlkCbMCWTDXc5+Wf4hp4CT2E4A"
    "DGA4Lj58IHECajtAbse90XGxzQ/nDLBUCvJ27Xa373RPbfwrU5heDOnFEF8g0g4QrgvgW8Ou0UDtrkzsrq4DWck0YVOghnFidKpW"
    "5hEnEFphwPOEuBcrnwC1gE6iHMz6CS/3AYQl63z/VKLxCcxIp00teY/4RTTgEt1FYQCB2TCErmxtjyVbG3SFqXULU5vLl+/d2pYx"
    "j4mPCxUH3qwNPWN+z8DCv227SyPEFzawExa15SnIoK8MBDPL5xFcEXseP0b8s15WQE6hXnra7aeFznRtBJbmdIJ2IFcw0Shw4tkG"
    "LE9xFELnw+M1FIHW78NHq7Ver2EEX81jQaOXZ5c/XNrXBWFIFrl2Balxdc6xa6OsUFiwZPNd2Vhxv93f/paDFhWQNE11iLVGQQTk"
    "SPa6ekv67u6BZN/XvZbsIu4t/vmZjmqV7wcsqFKvXLH1o1mmzZx0misqzTo93dc/YZGxsD1wb6x+yX6dA+S/DmdAmNrSy1v8bFu3"
    "h/vHp6fatN0BNs9xIBD6p4X+M7w/6HRlperEcXAndT+2ZyC2sdY0g8LYcR4vGBS9cFDm/URSDy6UgW7vu1CWsx8q9Z0d4qBr7O+G"
    "CKWP+ZufwWsCoNh4ZBcU6UuToDzRpgVdR2LQawmRKUrl6VF/Cp2Or6eoFmxsg0DG18fiOzh4Y9Ql9OVYfDnGLyfFsKb2I4DUORSg"
    "oELnoD0tofE62NtJWQUFcqPOiQwHahy26niB5qMSGr6gdMWdilnoBNmdNuYTBE6SgRZ1mnci058riHkovFUXPvNpQCUjaA0syJ/A"
    "lQOKzsNWC5UEtrPtQz1u2ft9BqZc4YUDLGqtqYRgr3Oqy9Ocd90VfSfwWaBV7xs6vnZ5392i825j791a912pfzF00Kc58wmMUMPm"
    "OKVisDct+Gx18if4hC9FGfxBNFIUz0+f8OOAUFkLpoydDBxsA+JZ+h9j3n6d+iUCoOOPSwwmZANAlgtTwJnnmPiiJA7wBthE6AmY"
    "V5/Y5E716S2+girl2wV/u4a3E8TzwMKKC/6Y4+w5yVTETM1o8pnDaq2cSOBz25LqLAw2VtrtWnsahKk6ahd9F3SQ4NfcPAxZmtkU"
    "yQ9ju8MeFWprhnjMUFxm05wqY1vonqluxLFdsjmOJIY4INZXACaO+wR2jLMu+sOC9YMHmOgqll6KNZhScemrBypuOaRZ4ruZ2i/X"
    "T77R/EKpeZE7n7EwM8csOw8YPj65u/CgxvoBYvmDrfK1H5FhqBozxoeICTX8aeZ44gm3ksUT+On0JPWLu9OAVpbc5b3/5eXrV2aM"
    "9/Vo0MAJLqEHZ8wQmYuMzbQf9E+fVISi6msXd/I0VmCOxUCT0tV2Fgw4gMBXgKU5MIO6Q3qEY390B5UlqFVQEKIFRma4Qcona2Z/"
    "AyV6f2bi0tFTcblMBtipUEZrb6/ojh5cxGtp0O6xqqgt+OypgHsJGjeQtLkU2Y4YIjA3VjOWTSKvp755fXmlGhO6pyTtrVTRWfvq"
    "LmZqT0Wm8V06L7n3IY1CdU13jPRqYxt++rRag6UyswkLm60ZttbqFTx95ZnvUxuMXeZk8zRncU8y8DmM1fu0l9cDtkhToHZPvWQJ"
    "bivwxT5NbeU1WqqurhEliRrjYawBmwOXf/pUShOad+ux+i//CJSM9+AZkIye4fUnWlfvxS01VuXJmkRLzQe8r0V6rMFTGA2RPGeI"
    "rBBD5ADcbPq3t/rqG/jD5xF3FKC/8ThgGs8LM25B8UAPZPe/0cRm2fbqX2kztrMzY3jeEBjY90CbCiRIuH2MqPKCJURI0dIE+Y2C"
    "4CqCwOkbHI0ZjUbAuFdRjMpGHm7AWKzN0lIOIA59k0QzH4RInmds7c9YNMcIFOpXCI/7q1fAyVpmDDOIQbXQWfhjFHATr7MYRk7i"
    "PW4oM5eJnzHeUu+Jbs2E4TELTa8zE+l2go8yFNl4elSSn37tuw28HvvMU375+79V+xL+EsB6k2htdI6AQ9YV/owBsTjTVErkxFye"
    "nmpkRAFcpG4X/2E+IG77yUW7ew9gjimNGGYhhKGDJpNg03qSjVUozVI3aV/ABMmbaTS9+YIMOLEr1CQ8x9hQzzIlYE6aKfsKP6uW"
    "Yr5jOJ8N4dGECkPHU3OvdU2cJrDIT81yA0oqRN1b7Dmxv/eBOH6FudG9cN0gzQ1QuGEFI4lrwcSkoHzsFTz06KtB0DwTPwzfgyeh"
    "/N/73rpPenbG9D5AztNs9cqcEJA+ySUXRQwxFXJgJHp4plAZoESf4pZb+DDDXQx/BjPmZJTuXVAFpq6P0zK9d1qmOC2Yc705KV9N"
    "dU5YGHeFgKk/DomEOPxpEwWJSohNSabpF5KI0n4gYCjHPt0Y+xUOFvOnl06KJEiYGwFKKd6bVh+9SFBuJEAh0lzxGHL9sv33UXPr"
    "HFOqJ7KBGysK88/HiE96PtOkfBFCoWUEUORBkZRcZRTAFAmYAyB1TZdWYZBVF1W60WFDTvMc40Zc4T2l/aKqhlf58EQZNJg44ZjJ"
    "LcipQYVhUh7yzk75fG3d8KUE+FLyEjkHQxsLTTwNBebq4OTw+Khfwa20FI7ngZlwUlXYkrKOH4YseX718oWtYuKZ2iKYJAUJo9xh"
    "be/6dLBzszc2wKdoqSKLWm3NhoV97EC58vIJbt9lPGWOjzFPlAY3kHZ1oGeepCwkRa8X2A29/8G8/tm8aX2zh/1LSL1v37QQKQVK"
    "eYhsGScWErs2hSLzBffvktpU0urKxcvzS/taJGfP4oM+bty5qe0s3I4B3x3zwDK7aMmbapgH3XOrc/75inJ58bxkw1leaRE/MqJ4"
    "nm55ebL5Ur2R2B7n9CWYLm7/vhIW/iXzfOctXnYBjp0uObFFlMCX7IgK8qomebQAqALA9FN0CC/nMV4eADNPzXCFMAedF8gurnil"
    "yv4TnjjT3OzWQMkEX/72Hf55AUIofF88HZzal+Ra8p1TMwUfNAOGSFt7uoGpirRhgA+2iixGTTb9rCUHmNlY8zH+aaGXvOwtaWsj"
    "uwW16KTzJHcwTDrWOUCcdnboBOiKOuOLjvxIKHW65BqWnrM1KXx6u1GbuJ+XcgoPyrHycfCXORsXb6mf9Dr/DgG8vVEiSUq6+4fL"
    "XS4oLRVP9+Skp0YS9ZOEaH9r3BlLY2KA34ZkGLKxH76B2BOMF5ElWjDwDW9biXHHS5zEpYIlNKS/LWxcfwWFtw2v8hcbxRxUXuwG"
    "Uco4FqCNK9vvPN1TGxl+OIqMKLzMWPwZj5SlUbBgBvcV8337hV0EoGRAmYhBNS5boCUXJmXEXoR8ctEBWmBId5YBQw7nGXjdUsqs"
    "ihTHNgnDaNNW8fCVii0S1/792xeil9d0Lhi+a6N8vdpdoPPgLlTdgLHb7gKDUDJUwIpqF6ywQSp0K8I88RurYXuquwkC7ED2eQgB"
    "QsCqGwAEsh8TWyRBIP1N3I7Xjauzixf2kYFHHox3xnOgtGu4k3nId/Myy7YM9HxYwiN0xzUwb9CgnOrcKzRY6DHvLIO6M9BgdqnK"
    "uOhQoU0AcLrJ7ZfyAuhIwTCJlqjmYTjgziCexXGv1zHLT3nhUTA/VJ5OgFEYOsKXzshJfBOcldIFxps0KJCsuiqb3TpZcYwGOx0y"
    "8j3qZ8qukjvFAc345sDkPhF1gIzCPLxPlnbi5QUUvo60WNoLk8C/Q3306dNx1zIWk7zwOR0Q//Sp0z2xYPLFRpsfah0Di/aKraDF"
    "ElpRDonyjteic+dQvpu6e119t9t/XimfFOXAjvyeYuIK/vgOS/lpd14snp9jB5z/eMUCgRNDgv5ur3uCG35UUTRtrvmc18xX1Ww/"
    "fYY3JDNtYXpzfnWT/rh87hFP4smaFrJkHxmyhNwxCvoU9QyvbZn7vAtUPLibesnTn/AKE7WfF77FibcMC/kbUEfOJadO2nDlZWQz"
    "MVecVkAzYIYZirTrxMBZ7JIKtH3aklQUrOu4NjKUJoz1GZ77FpL36ZMo5PdByq90kAvqAbSL4wp5JjsthPoymicuLksZHi7iVetw"
    "NL6DF37ocJbro0iW1b6Hb1AI4DGHIMTRYwVerShC0HwkCj6afLyoOwjXq8Rxp6mmb9pjUMOiLrilVE3DKBnNJ6CAyzYo7Go6T2PS"
    "C6oOxaDI56gQSr9iYWJiGo9OMdLDEMZGTfEYSVpxWzTen7HC1+jA9PDBIDl64mfpG5Zc0vmn3sGhhf8ZDg6h+gqlyrLWem8beE4M"
    "wAKkG2XaWTh+gLFvKdyMfDNm4uudHf5JDrzOVabIGqBy4rAcXppFcT3upLNWGr7Ph/XpEz5BdCe5iLnbpPZVHfOihkE0JKZ7Ag8a"
    "79ZYIawe/lmLKeXcubODTIEGWab8Gk1awhbRVDJpZOxEY1x/Aeg0stMuErRZfxZZ6S6e/sZUXzaLsztxDJfuvhaHoUJ+UBw1KTFh"
    "RV8TlcjOayvsF+8ZGRrFkAwQGXowMS3g9vUI4kJwwfWBbT2mp55KlBJ2qsc/1oL+IL7zBO8uw2UhcJX5bhD3DzQ+Xi3e2Ykpgn8c"
    "S6tTHKOG5SmcMq4xgNv0PtjImCUjvDgWs/9DiEqFlsnXXhL2cQ4idhb6M5LYZwnQS8PcZb2yAEWkwJgqP8Ekx4AJQ39OrBbSOopU"
    "rTmMbYTDY0kOJCdD0wqc4J7PyHP//xsxZP2wHdE/a/f4/1qHWZC3DYjtmV5NqqFGPFBbmESVnZ2FSSsXl0iwASYooENmIuSLGfgt"
    "2sLIbVDh1ju4I1OCxVR8zeHa4WXpEWATI0Mv8vng3W7HtA6NGLzUl7umdWTgIQIwePzSdZABcOrgK7/0TM1NIy27cPd8DLLlBGdB"
    "PHFsp1+zm3Sn0KFxbHQODfPwUN9mQ4VR/5jKjgdi+Pjdrnlw1HuOf3UjtD8mecKkywB/aY/sY7qnha0DXTc+Lm18uUtfjY+3xsc7"
    "AwNL+Ls06NYXseqIHeirj7e29q79canvdfsf72zs6qAPni94Jv2MvnfgYWm/awORwAkiCLbKL45RKeRDGPQawCAM7bmAB2CgNAdz"
    "xMF8XBKk/RwSXrStrgVl0Z6fUTnHNC97AnqRR7Z4a8ymi4LzxIkb4RI23gWotiRi4uQeHEIYiDcaNdxPX84MRb3qv/7D3/1N7Sy3"
    "yqnY6B+NRjmE7d0fde/rXrAAD3+L1QByzmhJCCevqxt3dnbXQmjHPBbedCcCHrwWQwkQbcD6rkUcfny4bhgBcr2E/0kD/p39L6Ye"
    "YU3H3F/gYQFCgJCm1Cpa+uK8VyejO/KO2JFMyaPGifzyeawdOMQlueGd8hdqi3AUy8UFgp0jfb1tdsUawcfbNkoXCJX4XLZI2rrS"
    "E//QC1Q0vd/oUP+6/JWPCd8c1ys65ONtS3NbEJ4IrFpaUnwr/hQaJrgzglsjoJUePgXBnQ2NCtxpmg76AZf/oBT7qnBWxR9gEPm6"
    "h9gwu8V22bLepJBzKZcy0/jFXga6RgY/S8Czb7Cg70WrghV4RVqqkthhdB8rjHZt81F3zTPANxa2aA2Nr20Fy52d0eBk++QjpigV"
    "qsElmQtmOomSTG/gfXpBlL4rSD/xkZ/f0AHEnY0zh8CXEH3z+5kYPxMJrDv0I7XfoOgInaMcnf0jA4HXEMEijgLN6Ukh9XifU5TQ"
    "4n45FUPHGzOt2VRWrBJ1eMD7ksygrPfSz6s5qPvLf/5fyrPicDwSQAglJx4YsS0rka0UbPaBcUvq7AA04vM2PbVTYNPNCazYYNDB"
    "hSTz1T5oZKT3imqh26t2aOZ7XsBq+iYzbgE98xjUiQDaSG10YoS7I5ypfC+DE0fbcLramaXjJryV2+5TDOhFbhHEvcKD6lddJHhT"
    "OEl9McXkomPP3K/f2ckG8mIJggUXQBd5Xu5n18n6sVsshcBjsfwBz/V1s22YQdUsovircuqDL5MN14bqY5u9DzEbq4Z5gudH+Dv+"
    "AQEeetJ45BwFeJ3nbXEa0fKHIFQ3p5MxlcesZW2i5p55yMmT1sjYJVyl1RxDXrDhVCccL2dRlIHkjc9Daa948/Xv5uDe4C8m4W/X"
    "qPVZQ9gldciLnRbzRksPtLJCkR/94ZtFxeqO2TU67emueVLNrBGkoRx4JiIRzIHwQweIvoAARrj/UQzsCiEC6ipNDiz5ErMmkS7b"
    "00oiUxC6PRygJOuGbAJJDHZ2toVZ4oblNI+19OYAmisTz6d9bAIqFhzzMHlt8AC8IQ1hzi+Jqm6JSYcIQu8ZGhLfM6YQOdPKgRGF"
    "EOCKpMinz+2D3Y7V5X+MaDSyLXlVLERBoOHCq4FdLAnke0UboTIPrmEMoi5th0DbcvGugIG9tZ4+B/c/S3yWUsdSfm2G901mWi3f"
    "Kd99p1WPx3joseV7LXUHhwfP+AHfeA4MfMeetyZI/VX7KXem2phr0BPb3/flTUVuxvBnYnCtKM+fwsFSxKj8CSlTIh9KSofyeh4l"
    "OzUAvKWJABsGsThwxKdP4vnAegQqEbCNRgoIpTmOMozWeYII8M8Kp1W86PPZxynJpURM8jpf9wGgA4Bp7ezA0+mhePhK9CMeu482"
    "DvdhD2V2gri+LGEjkEjcgNg4Cwi9J5jiwYfKpX5jmU0ARJnn9XHNTSp85gB/e7hfTfwBr7/aC1mG1/t8IgRGVGHPB1OYZiVAXaDP"
    "iuWuVovYcNCxNo8tisHgTZIpWMIojukn657SLyvQMXXMBnGCjSWuPuVuLHkezyWvQ+2ZZyg0IACE23zFZPA0rQ6QfZfwEUwjxIF0"
    "QJHuXMhImeGZz6XkJSWYKQc6iu7c0U06Hiwv8HMnKd7FfLmW+m0lRQ5U5+tQCzFHLsXt7xT3xtP9ply41PCxm1SXshr9Vuc0fKzi"
    "lTpqD77gDtBjNQpBrFTSZoAWv+upcf0Kteys0DWVbBGRjkA5FTxZasaJLF8Xxy8PaMiQEpkM4lornf9EBng0FUhXCAld22F0SwkR"
    "UQjwZtLVaz6/GbMpB4ucIgyC7XqChJRbROV50le32vv3dLkS/iIj3auJF4Hw31HEi0HwdBTe9dGY+5UTtJr8JcMm8lWSmYDXRSaT"
    "0IKEGv+lRYPC4l4Lk07o1LwYiIE7MO/FrWP0mi5Fy99y4vYogxtvuHhPd/4W+S68DBe7eVlGi99SfkVTRtUDpXGARcL3V57pV2ex"
    "MVmMjCzNI7efJR0pZYtvHNp4S5X3foppaJ9PXiodjmSOqFbWMbfjLM/KK2KxkP/EQMUFkLO5pAwA6mgl8BBZokJiO+g7J3hUWFZA"
    "fM1Y3GxWzahSG+85E1k/ZT7n0pmyF5E71VebZaZwpDSVL/mr9QnE0B2zu4MKcdb5OTKMpGxMppj2PNqZNiisgi88vOIs6Ym1JbEO"
    "UibQETvCV5krjXJFB97QFzlHWBRtZAqLcsoXBgrIeQvAqjx1oRgBZtujjt01O4ebedMZ8A5muWd9zrvNxC8uYCOaiznsFnE4Pxif"
    "mYXr1CrEqKVlZhEViSd68bjyrWfpBmrhJ9zLoqUavNvY3nTgRLDWDFVf8Wb8YuTNlXiuqHO3E6XRUHlz1cgBlaSLOOmAcC3z5HBX"
    "Iwxbkb5HA9Yb0tD1Fa9jV7CqGMVfgxpndESNPOM/D2LFLInNv6aO6cofOgnxxZ2S6KIcV3lHMuFlC5FLiDl94BNWVp8ImFzh5RNV"
    "+JsbQxKMuH+P2ihvAiTWzTPxZdsCxspPJ1XzQpmvQAg+AdwMZCbfvWzCJeHOQGJiTxv+WdKk5OkimYxQQ0eMTpgkPPGCdGOHDhkD"
    "ZqitqdMGH1TSnhqTXE88XnIZYWCBw18CKZRlEuHP+uaW5D5xp7QTEfChp6r2+eHrSiDZH1YbPXFcqDjcvh04bHKhhlu2/WrA5WsS"
    "1WpaLW2HbbCGOCwz3dkJuOrHDPXqFvO6kvzFZ5pEQKTCo4Oo0fSQRs+NfyVD9Oez9r9x2n9ttR8p79sigVU4UHLSHGWRtvFV9AJ/"
    "sPkp4dJS2x0rbi/p55ZbqIZN/LFNyVdeKoTQNb1Dub2h/GyxmU6lgicfyKfpOdPklpcOhyAziWNN2zJ4i+miJagtKbwPf/WVx3mG"
    "7sP+RiquqvbLrOWiiJzE/NpIfWuCW0ET8oroW24SpC/cKlQAioWurTD5e6JAce+iblauHQLNobaINXyP40sXHVbFqGQd0GJ4A7/y"
    "7t6fGMf1WmmVmi/fCucCIHwN9QiXosMndbmtwcfra8CLIDzIYXhPF00BIwMozN8ErP7Tv1fESLDrAvTTprGIi+6KPHaoKl+RuT1E"
    "AqrKi7EjWxa2ugsH8cMlQt3Z2SzTKI897V2Pbta67OOltbfCGSungDZCeo0TBbaypliF0ycONywYraMW/GaM+KEJcL1wNBevL+09"
    "/w0m4n3y3zge/Im8PR7OlwjOYbxnY+gNNLNUjD9YgqvS6M2/dNwLQChQ5ZHPnNsrvMfuDV3NOMDdvlJlRfxKU21kzNLxeYDxB5AS"
    "EGqi3W+iZzONSPCoZ7RD9GSQqv7lj39Pt67+iBrilz/+N3HtsjKOWArsXVzGiuYIf+lOjhALgo9yQjd1A4N8rF7SdfQADTkpz8LE"
    "mBRXOQANGoWBAhEqJT4mRPe8JR5HoIv6/ZDrru+F7tK+i5Yhv94+GM5nOkHkt2lCbbGoGfg8ducD4OJQ3ke7TRpIGIqZkwXBKK6E"
    "rZw1KegxNPhZHX49yrY9BAdo6XBt1aThhvjWE6Oz6ZBKAQmXC00nxoX/pxM/wDwPqCxOmGw5tubkZgMiSlwUAjrQ3TF4pRq4cpgS"
    "JVZi8Ld3Aq3oDEKx5O6S7peLkjN4o14XF6TeqLohb1sM7z0W9I02pGw2QJB+J6wi3MYQHQQ6HcNvE22cl6pDsXG8I7/iO922kM01"
    "YnU9qHqcbUY53JKLueVA1lcedwFTcTzrN8X6jUc6N5O06DbS+km3oRPgVhk3GVSL3+xYr4e/hvEeL95MqRK/bLReSaRJi7MfqIXz"
    "m1SFYfUK40JY89svZb+jBuNx8b1yp8XCKA+AP5RvD4TKeLf3bAwCDYZSpQ0+9WFrIax96yFEIiIjW6WjUXwZcuGn/tCnfaU/POS/"
    "BPmHh/mtkZW7egcIjC+YNZ5qerh5L2LKG1GWf+shvyAbrT4VFmTFN/iLI/Dil//63+ll4E8ZlkMRXnAImuxhC08cL0z+tbE3R236"
    "tQy82pbkzuE3UotvPhLHB6oMttyefe8PbxQA6RrvOkT+60Kk+H4dOLqKuQ6NTsKi71LC2nKDb92DQ0r6HsJAu0H3P25ikQBxZRyS"
    "2QYGb0mg6hc5S38fgqzjcVYN+KD3cONmzO33Yb7iO5vKHWg25afytlm+ukvGFH88Rlwf+xBk517dKwnWpvbl2HMd7NQVsDjRImTu"
    "ulUqXP+mOa7jqzRlPQd1GE2gXijuBV9FG1Iwmu8w15pwFvr0qV7s0N4q5d84Q3tYPX1dW1quxZIvpKUsvmkHgkvseN+lAuj5aZvr"
    "KsMAzVNt1bTaISDIN3EQWyi3h4FZzRXmWdSULEyPPcoZNkZ2GQEOgxtjU7/8GcNPPCPHw0qBXm2xu0y7bpwJyRflJqlG9MLhUitJ"
    "1X+i5/9Zx38he/2L3xCFqVs832psMAyKoMCoLG58jjHW5QnyTdKCruE+gdjZ0VSuatC9VlvFqNC/pl/Ck4fxWKEjS8WpoXlIv+6h"
    "6uUJX6W6DOYx/B2vjWUw1JENq4kiBgTnat2074+XT88D+uW2LS4T1tByzUI3pTwDlxS9ufwO6fwE76dPlpHYWq0O3f4sVaFUHiPc"
    "BOVVIcU27gSJ+5XzvSA0sJUDSruJbuBuanUHEn/BVFzLmUSgv7HZLlbbDY0RY2X+C702Dq3dUDdCJh0/sgx61Yba4pw03Ztci+Np"
    "8R/a1Rf+gYMdfrU4LZzQdcrVpogR1Cp+hS8tthr/z3+BQB9xbakx/xJCRa7QDX45Of6OUV5d9KNoURjcKfw+dfCOxW8u4gXp/DID"
    "XhvdjlQ3y2vVpfvQ61eri7vYXSed4HkMU+2vH1znc26IiTXEzBn5TDVs6Pp0CQReKeJ43vkCho/GjYEXhzmqMZDVQCbDcz+c2Tb8"
    "er7PVmNQkcZxu8d/I3OP5z2AXLjQO+upYdSm9DP1C+6g2ajC3Xr0Wm/f8zDy/WyIy1P8R8Cqk1mrtkUTPYB4gF9ARHFyeUHLavt1"
    "EPeGIOWdEPRge+Iug6a7Hz4fjNSu1+FN84sjqjvmazx1Vt79BB4V/r7p6d4kmwWDB/8PfyVk1yqRAAA="
)


def _page(b):
    return gzip.decompress(base64.b64decode("".join(b.split())))


CREATE_HTML = _page(_CREATE_GZ)


# ------------------------------------------------------------------ plumbing

def _credits():
    """The credits module holds balances, creator accounts and Stripe."""
    global _cr
    if _cr is not None:
        return _cr
    m = sys.modules.get("modules.credits") or importlib.import_module("modules.credits")
    if "conn" in _ctx:
        m._ctx.update(_ctx)
        m._setup()
    _cr = m
    return m


def _storage():
    """(folder, survives_redeploys)"""
    global _dir_cache
    if _dir_cache:
        return _dir_cache
    cands = []
    if os.environ.get("STUDIO_DIR", "").strip():
        cands.append((os.environ["STUDIO_DIR"].strip(), True))
    db = os.environ.get("DB_PATH", "").strip()
    if db and os.path.dirname(db):
        cands.append((os.path.join(os.path.dirname(db), "studio"), True))
    if os.path.isdir("/data"):
        cands.append(("/data/studio", True))
    cands.append((os.path.abspath("studio_media"), False))
    for d, persistent in cands:
        try:
            os.makedirs(d, exist_ok=True)
            if os.access(d, os.W_OK):
                _dir_cache = (d, persistent)
                return _dir_cache
        except Exception:
            continue
    _dir_cache = (os.path.abspath("."), False)
    return _dir_cache


def _path(vid, kind, part=False):
    return os.path.join(_storage()[0], "%s.%s%s" % (vid, KINDS[kind][0], ".part" if part else ""))


def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS studio_video(id TEXT PRIMARY KEY,account TEXT,creator TEXT,"
                  "title TEXT,price INTEGER,free_seconds INTEGER,created REAL,status TEXT,"
                  "full_size INTEGER,full_mime TEXT,teaser_size INTEGER,teaser_mime TEXT,"
                  "plays INTEGER DEFAULT 0,unlocks INTEGER DEFAULT 0,earned INTEGER DEFAULT 0,"
                  "fees INTEGER DEFAULT 0,fee_period INTEGER DEFAULT -1,fee_taken INTEGER DEFAULT 0,"
                  "likes INTEGER DEFAULT 0,comments INTEGER DEFAULT 0,sha256 TEXT,"
                  "audit_hash TEXT,block_index INTEGER,live_at REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS studio_video_account ON studio_video(account)")
        c.execute("CREATE INDEX IF NOT EXISTS studio_video_status ON studio_video(status)")
        c.execute("CREATE TABLE IF NOT EXISTS studio_meta(k TEXT PRIMARY KEY,v TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS studio_report(id INTEGER PRIMARY KEY AUTOINCREMENT,video TEXT,"
                  "reason TEXT,at REAL,who TEXT)")
        row = c.execute("SELECT v FROM studio_meta WHERE k='secret'").fetchone()
        if not row:
            c.execute("INSERT INTO studio_meta(k,v) VALUES('secret',?)", (secrets.token_hex(32),))
        c.commit()
    _credits()
    _ready = True


def _secret():
    with _ctx["lock"]:
        return _ctx["conn"].execute("SELECT v FROM studio_meta WHERE k='secret'").fetchone()[0]


def _token(vid, viewer):
    return hmac.new(_secret().encode(), ("%s|%s" % (vid, viewer)).encode(), hashlib.sha256).hexdigest()[:40]


def _seal(kind, detail, extra):
    ex = {"studio_version": VERSION}
    ex.update(extra or {})
    try:
        return _credits()._seal(kind, detail, ex)
    except Exception:
        return None, None


def _limit(who, group, per_min, per_hour):
    t = time.time()
    k = group + "|" + who
    with _wins_lock:
        w = _wins[k]
        while w and w[0] < t - 3600:
            w.popleft()
        if len(w) >= per_hour or sum(1 for x in w if x > t - 60) >= per_min:
            return False
        w.append(t)
        if len(_wins) > 20000:
            for key in [x for x, v in _wins.items() if not v or v[-1] < t - 3600][:5000]:
                del _wins[key]
    return True


def _ip(h):
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def _slug(name):
    return urllib.parse.quote(str(name or "").replace(" ", "_"))


def _gbp(p):
    return "£%d.%02d" % (p // 100, p % 100) if p >= 100 else "%dp" % p


COLS = ("id,account,creator,title,price,free_seconds,created,status,full_size,full_mime,teaser_size,"
        "teaser_mime,plays,unlocks,earned,fees,fee_period,fee_taken,likes,comments,sha256,audit_hash,"
        "block_index,live_at")


def _video(vid):
    if not ID_RE.match(vid or ""):
        return None
    with _ctx["lock"]:
        r = _ctx["conn"].execute("SELECT " + COLS + " FROM studio_video WHERE id=?", (vid,)).fetchone()
    return dict(zip(COLS.split(","), r)) if r else None


def _public(v):
    return {"id": v["id"], "title": v["title"], "creator": v["creator"], "price": v["price"],
            "price_label": _gbp(v["price"]), "free_seconds": v["free_seconds"],
            "plays": v["plays"], "paid_views": v["unlocks"], "likes": v["likes"],
            "comments": v["comments"], "link": SITE + "/v/" + v["id"],
            "teaser": "/v/%s/teaser" % v["id"], "poster": "/v/%s/poster.jpg" % v["id"],
            "channel": SITE + "/cinema/@" + _slug(v["creator"]),
            "live_at": v["live_at"], "block_index": v["block_index"]}


def _acct(q, b):
    key = str(b.get("key") or q.get("key") or "").strip()
    return _credits()._account(key)


def _ensure_viewer(viewer):
    with _ctx["lock"]:
        _ctx["conn"].execute("INSERT OR IGNORE INTO credit_viewer(id,balance,spent,created) VALUES(?,0,0,?)",
                             (viewer, time.time()))
        _ctx["conn"].commit()
        r = _ctx["conn"].execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()
    return r[0] if r else 0


def _unlocked(vid, viewer):
    with _ctx["lock"]:
        r = _ctx["conn"].execute("SELECT block_index FROM credit_unlock WHERE viewer=? AND video=?",
                                 (viewer, "st:" + vid)).fetchone()
    return (True, r[0]) if r else (False, None)


# ------------------------------------------------------------------ creators

def a_join(q, b, h):
    if not _limit(_ip(h), "join", 3, 10):
        return {"error": "slow_down", "message": "Too many tries. Wait a minute."}, 429
    return _credits().c_creator_join(q, b)


def a_signin(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 403
    return {"name": acct["name"], "creator_id": acct["id"],
            "channel": SITE + "/cinema/@" + _slug(acct["name"])}, 200


def a_new(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again, your key wasn't recognised."}, 403
    if not _limit(acct["id"], "new", 6, 40):
        return {"error": "slow_down", "message": "That's a lot of uploads. Try again in a few minutes."}, 429
    title = TITLE_CLEAN.sub("", str(b.get("title") or "")).strip()[:80]
    if len(title) < 2:
        return {"error": "title", "message": "Give your video a name so people can find it."}, 400
    if not b.get("rights"):
        return {"error": "rights", "message": "Tick the box to confirm the video is yours to sell."}, 400
    try:
        price = int(b.get("price") or 10)
    except (TypeError, ValueError):
        price = 10
    if price not in PRICES:
        price = 10
    try:
        free = max(3, min(30, int(b.get("free_seconds") or 8)))
    except (TypeError, ValueError):
        free = 8
    try:
        size = int(b.get("full_size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size <= 0:
        return {"error": "no_video", "message": "Pick a video first."}, 400
    if size > MAX_BYTES:
        return {"error": "too_big", "message": "That video is %d MB. The limit is %d MB - trim it and try again."
                % (size // 1048576, MAX_BYTES // 1048576)}, 413
    mime = str(b.get("full_mime") or "video/mp4")[:60]
    if not mime.startswith("video/"):
        mime = "video/mp4"
    try:
        free_disk = shutil.disk_usage(_storage()[0]).free
    except Exception:
        free_disk = 0
    if free_disk < size + TEASER_MAX + KEEP_FREE:
        return {"error": "full", "message": "Uploads are paused for a moment while we add space. Try again soon."}, 507
    _sweep()
    with _ctx["lock"]:
        c = _ctx["conn"]
        for _ in range(20):
            vid = "".join(secrets.choice(ALPHA) for _ in range(8))
            if not c.execute("SELECT 1 FROM studio_video WHERE id=?", (vid,)).fetchone():
                break
        c.execute("INSERT INTO studio_video(id,account,creator,title,price,free_seconds,created,status,"
                  "full_size,full_mime) VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (vid, acct["id"], acct["name"], title, price, free, time.time(), "uploading", size, mime))
        c.commit()
    return {"id": vid, "link": SITE + "/v/" + vid, "short": SITE.split("//")[-1] + "/v/" + vid,
            "title": title, "price": price, "free_seconds": free, "creator": acct["name"],
            "channel": SITE + "/cinema/@" + _slug(acct["name"]), "chunk": 4 * 1024 * 1024}, 200


def _sweep():
    """Clear uploads that were started and never finished (older than a day)."""
    cutoff = time.time() - 86400
    with _ctx["lock"]:
        old = [r[0] for r in _ctx["conn"].execute(
            "SELECT id FROM studio_video WHERE status='uploading' AND created<? LIMIT 50", (cutoff,)).fetchall()]
    for vid in old:
        for kind in KINDS:
            try:
                os.remove(_path(vid, kind, True))
            except OSError:
                pass
        with _ctx["lock"]:
            _ctx["conn"].execute("UPDATE studio_video SET status='abandoned' WHERE id=?", (vid,))
            _ctx["conn"].commit()


def _magic_ok(kind, head):
    if kind == "poster":
        return head[:3] == b"\xff\xd8\xff"
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return True
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    return False


def chunk(h, q):
    """Raw bytes, appended at an offset. Retries and resumes are safe."""
    vid = str(q.get("id") or "")
    kind = str(q.get("kind") or "")
    try:
        offset = int(q.get("offset") or 0)
        n = int(h.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        return {"error": "bad_request"}, 400
    if kind not in KINDS or n < 0 or n > CHUNK_MAX:
        return {"error": "bad_request", "message": "Bad upload piece."}, 400
    data = _read(h, n)
    if data is None:
        return {"error": "cut_off", "message": "Connection dropped. Retrying."}, 400
    acct = _credits()._account(h.headers.get("X-Creator-Key", ""))
    if not acct:
        return {"error": "bad_key", "message": "Sign in again."}, 403
    v = _video(vid)
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    if v["status"] != "uploading":
        return {"error": "finished", "message": "That video is already live."}, 409
    cap = KINDS[kind][1] if kind != "full" else v["full_size"]
    p = _path(vid, kind, True)
    with _ulocks[vid + kind]:
        got = os.path.getsize(p) if os.path.exists(p) else 0
        if offset > got:
            return {"error": "gap", "got": got}, 409
        if offset + len(data) > cap:
            return {"error": "too_big", "message": "That file is bigger than it said it was."}, 413
        if offset == 0 and not _magic_ok(kind, data[:16]):
            return {"error": "not_video", "message": "That doesn't look like a video file we can play."}, 415
        if offset + len(data) <= got and offset < got:
            return {"got": got}, 200
        with open(p, "r+b" if os.path.exists(p) else "wb") as f:
            f.seek(offset)
            f.write(data)
            f.truncate(offset + len(data))
        got = offset + len(data)
    return {"got": got}, 200


def _read(h, n):
    out = bytearray()
    while len(out) < n:
        try:
            part = h.rfile.read(min(65536, n - len(out)))
        except Exception:
            return None
        if not part:
            return None
        out += part
    return bytes(out)


def _sha_file(p):
    s = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1048576), b""):
            s.update(blk)
    return s.hexdigest()


def a_finish(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again."}, 403
    v = _video(str(b.get("id") or ""))
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    if v["status"] == "live":
        return {"live": True, "video": _public(v)}, 200
    if v["status"] != "uploading":
        return {"error": "gone"}, 410
    fp, tp, pp = _path(v["id"], "full", True), _path(v["id"], "teaser", True), _path(v["id"], "poster", True)
    fs = os.path.getsize(fp) if os.path.exists(fp) else 0
    ts = os.path.getsize(tp) if os.path.exists(tp) else 0
    if fs != v["full_size"]:
        return {"error": "incomplete", "message": "The video didn't finish uploading.", "got": fs}, 409
    if ts <= 0:
        return {"error": "incomplete", "message": "The teaser didn't finish uploading."}, 409
    tmime = str(b.get("teaser_mime") or "video/mp4")
    tmime = "video/webm" if "webm" in tmime else "video/mp4"
    digest = _sha_file(fp)
    os.replace(fp, _path(v["id"], "full"))
    os.replace(tp, _path(v["id"], "teaser"))
    if os.path.exists(pp):
        os.replace(pp, _path(v["id"], "poster"))
    ah, blk = _seal("studio_video_live", "video=%s;creator=%s;price=%d;sha256=%s"
                    % (v["id"], v["creator"], v["price"], digest),
                    {"video": v["id"], "creator": v["creator"], "price_pence": v["price"],
                     "video_sha256": digest, "bytes": fs})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE studio_video SET status='live',teaser_size=?,teaser_mime=?,sha256=?,"
                             "audit_hash=?,block_index=?,live_at=? WHERE id=?",
                             (ts, tmime, digest, ah, blk, time.time(), v["id"]))
        _ctx["conn"].commit()
    return {"live": True, "video": _public(_video(v["id"])), "sealed_in_chain": ah, "block_index": blk}, 200


def a_mine(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key", "message": "Sign in again, your key wasn't recognised."}, 403
    with _ctx["lock"]:
        rows = _ctx["conn"].execute("SELECT " + COLS + " FROM studio_video WHERE account=? AND status='live' "
                                    "ORDER BY created DESC LIMIT 200", (acct["id"],)).fetchall()
    vids = []
    owner = "owner:" + acct["id"]
    for r in rows:
        v = dict(zip(COLS.split(","), r))
        p = _public(v)
        p.update({"earned": v["earned"], "fees": v["fees"],
                  "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], owner, _token(v["id"], owner))})
        vids.append(p)
    balance, views = _credits()._creator_totals(acct["name"])
    return {"name": acct["name"], "balance_pence": balance, "balance_label": _gbp(balance) if balance else "0p",
            "paid_views": views, "videos": vids, "earn": SITE + "/earn",
            "channel": SITE + "/cinema/@" + _slug(acct["name"])}, 200


def a_delete(q, b, h):
    acct = _acct(q, b)
    if not acct:
        return {"error": "bad_key"}, 403
    v = _video(str(b.get("id") or ""))
    if not v or v["account"] != acct["id"]:
        return {"error": "not_found"}, 404
    _remove(v, "creator")
    return {"removed": True}, 200


def _remove(v, by):
    for kind in KINDS:
        for part in (False, True):
            try:
                os.remove(_path(v["id"], kind, part))
            except OSError:
                pass
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE studio_video SET status='removed' WHERE id=?", (v["id"],))
        _ctx["conn"].commit()
    _seal("studio_video_removed", "video=%s;by=%s" % (v["id"], by), {"video": v["id"], "by": by})


# ------------------------------------------------------------------ viewers

def _viewer_from(q, b):
    viewer = str(b.get("viewer") or q.get("viewer") or "").strip()
    return viewer if VIEWER_RE.match(viewer) else None


def a_state(q, b, h):
    v = _video(str(q.get("id") or b.get("id") or ""))
    if not v or v["status"] != "live":
        return {"error": "not_found", "message": "That video isn't here any more."}, 404
    viewer = _viewer_from(q, b)
    packs = [p for p in PACKS if p >= v["price"]] or [v["price"]]
    out = {"video": _public(v),
           "packs": [{"pence": p, "label": _gbp(p), "views": p // max(1, v["price"]),
                      "charge": _charge(p), "charge_label": _gbp(_charge(p)),
                      "fee": _charge(p) - p, "fee_label": _gbp(_charge(p) - p)} for p in packs],
           "pay_ready": bool(_credits()._stripe_key())}
    if viewer:
        out["balance_pence"] = _ensure_viewer(viewer)
        done, blk = _unlocked(v["id"], viewer)
        out["unlocked"] = done
        if done:
            out["block_index"] = blk
            out["full"] = "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer))
    return out, 200


def _period_fee(v, share, now):
    period = int((now - (v["live_at"] or v["created"])) // FEE_PERIOD)
    taken = v["fee_taken"] if v["fee_period"] == period else 0
    fee = min(share, max(0, MONTHLY_FEE - taken))
    return period, taken + fee, fee


def _unlock(v, viewer):
    """Spend the viewer's credit on one video. Returns (payload, code)."""
    done, blk = _unlocked(v["id"], viewer)
    if done:
        return {"unlocked": True, "already": True, "block_index": blk,
                "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer)),
                "balance_pence": _ensure_viewer(viewer)}, 200
    _ensure_viewer(viewer)
    price = v["price"]
    now = time.time()
    with _ctx["lock"]:
        c = _ctx["conn"]
        cur = c.execute("UPDATE credit_viewer SET balance=balance-?,spent=spent+? WHERE id=? AND balance>=?",
                        (price, price, viewer, price))
        if cur.rowcount != 1:
            bal = c.execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()[0]
            c.commit()
            return {"unlocked": False, "reason": "not_enough_credit", "price_pence": price,
                    "balance_pence": bal}, 402
        ins = c.execute("INSERT OR IGNORE INTO credit_unlock(viewer,video,creator,price,at) VALUES(?,?,?,?,?)",
                        (viewer, "st:" + v["id"], v["creator"], price, now))
        if ins.rowcount != 1:
            c.execute("UPDATE credit_viewer SET balance=balance+?,spent=spent-? WHERE id=?", (price, price, viewer))
            c.commit()
            return _unlock(v, viewer)
        fresh = dict(zip(COLS.split(","), c.execute("SELECT " + COLS + " FROM studio_video WHERE id=?",
                                                     (v["id"],)).fetchone()))
        share = int(round(price * SHARE))
        period, taken, fee = _period_fee(fresh, share, now)
        net = share - fee
        c.execute("INSERT OR IGNORE INTO credit_creator(name,balance,views) VALUES(?,0,0)", (v["creator"],))
        c.execute("UPDATE credit_creator SET balance=balance+?,views=views+1 WHERE name=?", (net, v["creator"]))
        c.execute("UPDATE studio_video SET unlocks=unlocks+1,earned=earned+?,fees=fees+?,fee_period=?,fee_taken=? "
                  "WHERE id=?", (share, fee, period, taken, v["id"]))
        bal = c.execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()[0]
        c.commit()
    ah, blk = _seal("paid_view", "video=st:%s;creator=%s;price=%d;creator_share=%d;monthly_fee=%d"
                    % (v["id"], v["creator"], price, net, fee),
                    {"video": "st:" + v["id"], "creator": v["creator"], "price_pence": price,
                     "creator_share_pence": share, "monthly_fee_pence": fee, "creator_pence": net,
                     "platform_pence": price - net})
    with _ctx["lock"]:
        _ctx["conn"].execute("UPDATE credit_unlock SET audit_hash=?,block_index=? WHERE viewer=? AND video=?",
                             (ah, blk, viewer, "st:" + v["id"]))
        _ctx["conn"].commit()
    return {"unlocked": True, "price_pence": price, "creator_pence": net, "balance_pence": bal,
            "sealed_in_chain": ah, "block_index": blk,
            "verify": SITE + "/x/walk/block?index=%s" % blk,
            "full": "/v/%s/full?viewer=%s&t=%s" % (v["id"], viewer, _token(v["id"], viewer))}, 200


def a_unlock(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    if not v or v["status"] != "live" or not viewer:
        return {"error": "not_found"}, 404
    if not _limit(viewer, "unlock", 20, 300):
        return {"error": "slow_down", "message": "Slow down a moment."}, 429
    return _unlock(v, viewer)


def a_pay(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    if not v or v["status"] != "live" or not viewer:
        return {"error": "not_found"}, 404
    if not _limit(_ip(h), "pay", 6, 40):
        return {"error": "slow_down", "message": "Wait a moment and tap again."}, 429
    cr = _credits()
    if not cr._stripe_key():
        return {"error": "pay_off", "message": "Payments are being switched on. Try again shortly."}, 503
    try:
        pence = int(b.get("pence") or PACKS[0])
    except (TypeError, ValueError):
        pence = PACKS[0]
    if pence not in PACKS:
        pence = PACKS[0]
    pence = max(pence, v["price"])
    charge = _charge(pence)
    _ensure_viewer(viewer)
    back = SITE + "/cinema/v/" + v["id"]
    params = {
        "mode": "payment",
        "submit_type": "pay",
        "success_url": back + "?paid={CHECKOUT_SESSION_ID}",
        "cancel_url": back,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][unit_amount]": str(charge),
        "line_items[0][price_data][product_data][name]": "10p Wing credit %s + %s card fee" % (_gbp(pence), _gbp(charge - pence)),
        "line_items[0][price_data][product_data][description]":
            "%s credit unlocks \"%s\" now, the rest stays on this phone. The %s card fee is Stripe's charge "
            "for taking the payment." % (_gbp(pence), v["title"][:50], _gbp(charge - pence)),
        "metadata[studio_video]": v["id"],
        "metadata[viewer]": viewer,
        "metadata[credit_pence]": str(pence),
        "payment_intent_data[description]": "10p Wing credit (sebbi.pro)",
        "payment_intent_data[metadata][studio_video]": v["id"],
    }
    data, err = cr._stripe("POST", "checkout/sessions", params,
                           idem="st-%s-%s-%d-%d" % (v["id"], viewer, charge, int(time.time() // 30)))
    if err or not data or not data.get("url"):
        return {"error": "stripe", "message": "Couldn't open the payment page: %s" % (err or "no link")}, 502
    return {"checkout": data["url"], "pence": pence, "charge": charge}, 200


def a_paid(q, b, h):
    v = _video(str(b.get("id") or ""))
    viewer = _viewer_from(q, b)
    session = str(b.get("session") or "").strip()
    if not v or not viewer or not SESSION_RE.match(session):
        return {"error": "bad_request"}, 400
    cr = _credits()
    s, err = cr._stripe("GET", "checkout/sessions/" + session)
    if err or not s:
        return {"error": "stripe", "message": "Couldn't confirm the payment yet. Tap unlock again in a moment."}, 502
    if s.get("payment_status") != "paid":
        return {"error": "not_paid", "message": "The payment hasn't gone through."}, 402
    meta = s.get("metadata") or {}
    if str(meta.get("viewer") or s.get("client_reference_id") or "") != viewer:
        return {"error": "other_phone", "message": "That payment was made on another phone."}, 403
    try:
        paid = int(s.get("amount_total") or 0)
        pence = int(meta.get("credit_pence") or paid)
    except (TypeError, ValueError):
        paid, pence = 0, 0
    if pence <= 0 or paid < pence or str(s.get("currency") or "gbp").lower() != "gbp":
        return {"error": "bad_amount"}, 400
    credit = cr._credit_payment(session, viewer, pence, "studio")
    out, code = _unlock(v, viewer) if v["status"] == "live" else ({"unlocked": False}, 404)
    out["payment"] = {"credit_pence": pence, "paid_pence": paid, "duplicate": credit.get("duplicate", False)}
    return out, code


def a_report(q, b, h):
    v = _video(str(b.get("id") or ""))
    if not v:
        return {"error": "not_found"}, 404
    if not _limit(_ip(h), "report", 3, 20):
        return {"received": True}, 200
    reason = TITLE_CLEAN.sub("", str(b.get("reason") or ""))[:300]
    who = hashlib.sha256(_ip(h).encode()).hexdigest()[:16]
    with _ctx["lock"]:
        _ctx["conn"].execute("INSERT INTO studio_report(video,reason,at,who) VALUES(?,?,?,?)",
                             (v["id"], reason, time.time(), who))
        _ctx["conn"].commit()
    _seal("studio_report", "video=%s" % v["id"], {"video": v["id"]})
    return {"received": True, "message": "Thanks. It will be looked at."}, 200


def a_admin(q, b, h):
    key = os.environ.get("CREDITS_ADMIN_KEY", "").strip()
    given = str(q.get("key") or b.get("key") or "")
    if not key or not hmac.compare_digest(key, given):
        return {"error": "not_allowed"}, 403
    do = str(q.get("do") or b.get("do") or "list")
    if do == "remove":
        v = _video(str(q.get("id") or b.get("id") or ""))
        if not v:
            return {"error": "not_found"}, 404
        _remove(v, "admin")
        return {"removed": v["id"]}, 200
    with _ctx["lock"]:
        c = _ctx["conn"]
        reps = c.execute("SELECT video,reason,at FROM studio_report ORDER BY id DESC LIMIT 100").fetchall()
        vids = c.execute("SELECT id,creator,title,status,unlocks,earned,created FROM studio_video "
                         "ORDER BY created DESC LIMIT 100").fetchall()
    return {"reports": [{"video": r[0], "link": SITE + "/v/" + r[0], "reason": r[1],
                         "at": time.strftime("%Y-%m-%d %H:%M", time.gmtime(r[2]))} for r in reps],
            "videos": [{"id": r[0], "creator": r[1], "title": r[2], "status": r[3], "paid_views": r[4],
                        "earned": r[5], "link": SITE + "/v/" + r[0],
                        "remove": SITE + "/v/api/admin?key=KEY&do=remove&id=" + r[0]} for r in vids]}, 200


API = {"join": a_join, "signin": a_signin, "new": a_new, "finish": a_finish, "mine": a_mine,
       "delete": a_delete, "state": a_state, "unlock": a_unlock, "pay": a_pay, "paid": a_paid,
       "report": a_report, "admin": a_admin}


# ------------------------------------------------------------------ transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _send_bytes(h, body, ctype, code=200, cache="no-cache", extra=None):
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", cache)
    for k, val in (extra or {}).items():
        h.send_header(k, val)
    h.end_headers()
    h.wfile.write(body)


def _send_file(h, path, ctype, cache="public, max-age=86400"):
    try:
        size = os.path.getsize(path)
    except OSError:
        _send(h, {"error": "not_found"}, 404)
        return
    start, end, code = 0, size - 1, 200
    m = re.match(r"^bytes=(\d*)-(\d*)$", (h.headers.get("Range") or "").strip())
    if m and (m.group(1) or m.group(2)):
        if m.group(1):
            start = int(m.group(1))
            end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
        else:
            start = max(0, size - int(m.group(2)))
        if start > end or start >= size:
            h.send_response(416)
            h.send_header("Content-Range", "bytes */%d" % size)
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        code = 206
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(end - start + 1))
    h.send_header("Cache-Control", cache)
    if code == 206:
        h.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    h.end_headers()
    try:
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                blk = f.read(min(262144, left))
                if not blk:
                    break
                h.wfile.write(blk)
                left -= len(blk)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


def _playable(mime):
    return "video/mp4" if mime in ("video/quicktime", "video/x-m4v", "") else mime


def _get(h, path, q):
    if path in ("/create", "/create/"):
        _send_bytes(h, CREATE_HTML, "text/html; charset=utf-8")
        return True
    if path.startswith("/v/api/"):
        name = path[7:].strip("/")
        if name in ("state", "admin"):
            _api(h, name, q, {})
            return True
        _send(h, {"error": "use_post"}, 405)
        return True
    parts = [x for x in path.split("/") if x]
    if len(parts) < 2 or parts[0] != "v":
        return False
    vid = parts[1].lower()
    v = _video(vid)
    if not v or v["status"] != "live":
        if len(parts) == 2:
            h.send_response(302)
            h.send_header("Location", "/cinema?wing=ten")
            h.send_header("Content-Length", "0")
            h.end_headers()
            return True
        _send(h, {"error": "not_found"}, 404)
        return True
    if len(parts) == 2:
        h.send_response(302)
        h.send_header("Location", "/cinema/v/" + vid)
        h.send_header("Cache-Control", "no-store")
        h.send_header("Content-Length", "0")
        h.end_headers()
        return True
    what = parts[2]
    if what == "teaser":
        if not h.headers.get("Range") or h.headers.get("Range", "").startswith("bytes=0-"):
            with _ctx["lock"]:
                _ctx["conn"].execute("UPDATE studio_video SET plays=plays+1 WHERE id=?", (vid,))
                _ctx["conn"].commit()
        _send_file(h, _path(vid, "teaser"), v["teaser_mime"] or "video/mp4")
        return True
    if what in ("poster.jpg", "poster"):
        p = _path(vid, "poster")
        if os.path.exists(p):
            _send_file(h, p, "image/jpeg")
        else:
            _send_bytes(h, b"", "image/jpeg", 404)
        return True
    if what == "full":
        viewer = str(q.get("viewer") or "")
        t = str(q.get("t") or "")
        good = (VIEWER_RE.match(viewer) or OWNER_RE.match(viewer)) and hmac.compare_digest(t, _token(vid, viewer))
        if good and OWNER_RE.match(viewer):
            good = viewer == "owner:" + v["account"]
        elif good:
            good = _unlocked(vid, viewer)[0]
        if not good:
            _send(h, {"error": "locked", "message": "Unlock this video to watch it."}, 403)
            return True
        _send_file(h, _path(vid, "full"), _playable(v["full_mime"] or ""), cache="private, max-age=3600")
        return True
    _send(h, {"error": "not_found"}, 404)
    return True


def _api(h, name, q, body):
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "Open /x/studio/status once."}, 503)
        return
    _setup()
    fn = API.get(name)
    if not fn:
        _send(h, {"error": "not_found"}, 404)
        return
    try:
        out, code = fn(q, body, h)
    except Exception as e:
        print("STUDIO ERR %s: %s" % (name, e), flush=True)
        out, code = {"error": "failed", "message": "Something went wrong. Try again."}, 500
    _send(h, out, code)


def _post(h, path, q):
    name = path[7:].strip("/")
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed"}, 503)
        return True
    _setup()
    if name == "chunk":
        try:
            out, code = chunk(h, q)
        except Exception as e:
            print("STUDIO CHUNK ERR: %s" % e, flush=True)
            out, code = {"error": "failed", "message": "Upload piece failed. Retrying."}, 500
        _send(h, out, code)
        return True
    try:
        n = min(int(h.headers.get("Content-Length") or 0), 20000)
        raw = _read(h, n) if n else b""
        body = json.loads((raw or b"{}").decode("utf-8") or "{}")
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    _api(h, name, q, body)
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _split(h):
    u = urllib.parse.urlparse(h.path)
    return u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
        _setup()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_studio4_patched", False):
        _patched = True
        return True
    og = cls.do_GET
    op = getattr(cls, "do_POST", None)

    def do_GET(self):
        path, q = _split(self)
        if path in ("/create", "/create/") or path.startswith("/v/"):
            try:
                if _get(self, path, q):
                    return
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as e:
                print("STUDIO GET ERR: %s" % e, flush=True)
                try:
                    _send(self, {"error": "failed"}, 500)
                except Exception:
                    pass
                return
        return og(self)

    def do_POST(self):
        path, q = _split(self)
        if path.startswith("/v/api/"):
            _post(self, path, q)
            return
        return op(self) if op else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls._studio4_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    d, persistent = _storage()
    counts = {}
    if "conn" in _ctx:
        with _ctx["lock"]:
            c = _ctx["conn"]
            counts = {"live_videos": c.execute("SELECT COUNT(*) FROM studio_video WHERE status='live'").fetchone()[0],
                      "paid_views": c.execute("SELECT COALESCE(SUM(unlocks),0) FROM studio_video").fetchone()[0],
                      "creator_earnings_pence": c.execute("SELECT COALESCE(SUM(earned),0) FROM studio_video").fetchone()[0],
                      "reports": c.execute("SELECT COUNT(*) FROM studio_report").fetchone()[0]}
    try:
        free_gb = round(shutil.disk_usage(d).free / 1073741824, 1)
    except Exception:
        free_gb = None
    stripe = False
    try:
        stripe = bool(_credits()._stripe_key())
    except Exception:
        pass
    return {"module": "studio", "version": VERSION, "armed": armed,
            "serves": ["/create", "/v/<id>", "/v/api/*"],
            "storage": {"folder": d, "survives_redeploys": persistent, "free_gb": free_gb},
            "payments_ready": stripe, "packs_pence": PACKS,
            "viewer_pays": {str(p): _charge(p) for p in PACKS}, "prices_pence": list(PRICES),
            "max_upload_mb": MAX_BYTES // 1048576, "monthly_fee_pence": MONTHLY_FEE,
            "creator_share": SHARE, "counts": counts,
            "create": SITE + "/create", "wing": SITE + "/cinema?wing=ten"}, 200

```
