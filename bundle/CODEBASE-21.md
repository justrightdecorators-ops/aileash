# Codebase — part 21 of 41

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

525 lines, 48991 bytes

```python
"""
modules/studio.py  v3.0.0
Monop Studio at /create. Lock a video in the browser: read, fingerprinted and
wrapped in its own player with the paywall inside, then handed back as a
download. The video is never uploaded. Unlocks are paid from a viewer's
sebbi.pro credit (modules/credits.py), 70% to the creator, sealed on the chain.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/studio/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "3.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk1vbm9wIFN0dWRpbyDigJQgbG9jayB5b3VyIHZpZGVvLCBrZWVwIHRoZSBtb25leTwvdGl0bGU+CjxtZXRhIG5hbWU9ImRl"
    "c2NyaXB0aW9uIiBjb250ZW50PSJVcGxvYWQgYSB2aWRlbywgc2V0IGEgcHJpY2UsIGdldCBhIGxvY2tlZCBwbGF5ZXIgZmlsZSBi"
    "YWNrIGluIHNlY29uZHMuIFlvdXIgdmlkZW8gaXMgbmV2ZXIgdXBsb2FkZWQgYW55d2hlcmUuIFZpZXdlcnMgcGF5IHBlbm5pZXMg"
    "dG8gd2F0Y2ggdGhlIHJlc3QuIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1J"
    "Qk0rUGxleCtNb25vOndnaHRANDAwOzUwMDs2MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMCZmYW1pbHk9"
    "TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgo6cm9v"
    "dHstLWluazojMDUwNzBmOy0taW5rMjojMGQxNDI0Oy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLWJsdWU6IzhmZDBmZjst"
    "LXBpbms6I2Q1OWJmZjstLW11dGU6IzhhOTNhZDstLWxpbmU6cmdiYSgyMDEsMTY4LDc2LC4yMik7LS1tb25vOidJQk0gUGxleCBN"
    "b25vJyx1aS1tb25vc3BhY2UsbW9ub3NwYWNlOy0tc2FuczonSUJNIFBsZXggU2Fucycsc3lzdGVtLXVpLHNhbnMtc2VyaWY7LS1z"
    "ZXJpZjonTmV3c3JlYWRlcicsR2VvcmdpYSxzZXJpZn0KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzow"
    "Oy13ZWJraXQtdGFwLWhpZ2hsaWdodC1jb2xvcjp0cmFuc3BhcmVudH0KYm9keXtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChl"
    "bGxpcHNlIGF0IDUwJSAwJSwjMWQxMDQwIDAlLCMwNTA3MGYgNjIlKTtjb2xvcjojZThlZGY3O2ZvbnQtZmFtaWx5OnZhcigtLXNh"
    "bnMpO2xpbmUtaGVpZ2h0OjEuNjttaW4taGVpZ2h0OjEwMHZofQoud3JhcHttYXgtd2lkdGg6OTIwcHg7bWFyZ2luOjAgYXV0bztw"
    "YWRkaW5nOjAgMjBweCA4MHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1p"
    "dGVtczpjZW50ZXI7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVhLWluc2V0LXRvcCkpIDAgMH0KLmJyYW5ke2ZvbnQt"
    "ZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLXBpbmspO2ZvbnQtd2VpZ2h0OjUw"
    "MH0KLnRvcCBhe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO3RleHQtZGVj"
    "b3JhdGlvbjpub25lO21hcmdpbi1sZWZ0OjE0cHh9Ci5oZXJve3RleHQtYWxpZ246Y2VudGVyO3BhZGRpbmc6MzhweCAwIDRweH0K"
    "LmtpY2t7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExLjVweDtsZXR0ZXItc3BhY2luZzouMmVtO2NvbG9yOnZh"
    "cigtLXBpbmspfQpoMXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgzNHB4"
    "LDcuNHZ3LDYwcHgpO2xpbmUtaGVpZ2h0OjEuMDM7bWFyZ2luOjEycHggYXV0byAxMnB4O21heC13aWR0aDoxNGNoO2JhY2tncm91"
    "bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLCNmZmYsI2Q1OWJmZiAzOCUsI2M5YTg0YyA2OCUsIzdmZTNiMCk7LXdlYmtpdC1iYWNr"
    "Z3JvdW5kLWNsaXA6dGV4dDtiYWNrZ3JvdW5kLWNsaXA6dGV4dDtjb2xvcjp0cmFuc3BhcmVudH0KLmhlcm8gcHtjb2xvcjojYjZj"
    "MGQ2O21heC13aWR0aDo1NmNoO21hcmdpbjowIGF1dG87Zm9udC1zaXplOjE2LjVweH0KLmJhZGdlc3tkaXNwbGF5OmZsZXg7Z2Fw"
    "OjhweDtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2ZsZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6MTZweH0KLmJhZGdlcyBzcGFue2Zv"
    "bnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjk5OXB4O3Bh"
    "ZGRpbmc6NnB4IDEycHg7Y29sb3I6I2NmZDZlNn0Kc2VjdGlvbntwYWRkaW5nOjQ0cHggMCAwO2JvcmRlci10b3A6MXB4IHNvbGlk"
    "IHJnYmEoMjU1LDI1NSwyNTUsLjA3KTttYXJnaW4tdG9wOjQ0cHh9Cmgye2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdl"
    "aWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDI1cHgsNC42dncsMzhweCk7bWFyZ2luLWJvdHRvbToxMHB4fQoubGVhZHtjb2xvcjoj"
    "YjZjMGQ2O21heC13aWR0aDo2MmNoO21hcmdpbi1ib3R0b206MThweH0KLmdyaWR7ZGlzcGxheTpncmlkO2dhcDoxNHB4fUBtZWRp"
    "YShtaW4td2lkdGg6NzYwcHgpey5ncmlkLnR3b3tncmlkLXRlbXBsYXRlLWNvbHVtbnM6MS4xZnIgLjlmcn0uZ3JpZC50aHJlZXtn"
    "cmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0KDMsMWZyKX19Ci5jYXJke2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwuODIpO2Jv"
    "cmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6MjBweH0KLmNhcmQgaDN7Zm9udC1m"
    "YW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MjFweDttYXJnaW4tYm90dG9tOjZweH0uY2FyZCBw"
    "e2ZvbnQtc2l6ZToxNHB4O2NvbG9yOiNiNmMwZDZ9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25v"
    "KTtsZXR0ZXItc3BhY2luZzouMWVtO2NvbG9yOnZhcigtLW11dGUpO21hcmdpbjoxNHB4IDAgNXB4fQppbnB1dCxzZWxlY3R7d2lk"
    "dGg6MTAwJTtiYWNrZ3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjlweDtj"
    "b2xvcjojZmZmO3BhZGRpbmc6MTJweDtmb250OjE0cHggdmFyKC0tbW9ubyl9CmlucHV0W3R5cGU9cmFuZ2Vde3BhZGRpbmc6MH0K"
    "aW5wdXRbdHlwZT1maWxlXXtwYWRkaW5nOjEwcHg7Zm9udDoxMi41cHggdmFyKC0tbW9ubyl9Ci5idG57ZGlzcGxheTppbmxpbmUt"
    "ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtnYXA6OHB4O3BhZGRpbmc6MTRweCAyMHB4O2Jv"
    "cmRlci1yYWRpdXM6MTFweDtmb250OjYwMCAxNHB4IHZhcigtLW1vbm8pO3RleHQtZGVjb3JhdGlvbjpub25lO2JhY2tncm91bmQ6"
    "dmFyKC0tcGluayk7Y29sb3I6IzA1MDcwZjtib3JkZXI6MDtjdXJzb3I6cG9pbnRlcn0KLmJ0bi5nb2xke2JhY2tncm91bmQ6dmFy"
    "KC0tZ29sZCl9LmJ0bi5naG9zdHtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2NvbG9yOiNmZmY7Ym9yZGVyOjFweCBzb2xpZCByZ2Jh"
    "KDI1NSwyNTUsMjU1LC4yNSl9Ci5idG5bZGlzYWJsZWRde29wYWNpdHk6LjU1fQoub3V0e21hcmdpbi10b3A6MTZweDtiYWNrZ3Jv"
    "dW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEycHg7cGFkZGluZzoxNnB4O2Zv"
    "bnQ6MTNweCB2YXIoLS1tb25vKTtjb2xvcjojY2ZlNmQ5O2Rpc3BsYXk6bm9uZX0KLm91dC5vbntkaXNwbGF5OmJsb2NrfQoub3V0"
    "IC5iaWd7ZGlzcGxheTpibG9jaztmb250LXNpemU6MjRweDtjb2xvcjp2YXIoLS1vayk7bWFyZ2luLWJvdHRvbTo2cHh9Ci5wcm9n"
    "e2hlaWdodDo2cHg7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4xKTtib3JkZXItcmFkaXVzOjNweDtvdmVyZmxvdzpoaWRk"
    "ZW47bWFyZ2luOjEwcHggMH0KLnByb2cgaXtkaXNwbGF5OmJsb2NrO2hlaWdodDoxMDAlO3dpZHRoOjA7YmFja2dyb3VuZDpsaW5l"
    "YXItZ3JhZGllbnQoOTBkZWcsdmFyKC0tcGluayksdmFyKC0tZ29sZCksdmFyKC0tb2spKTt0cmFuc2l0aW9uOndpZHRoIC4zc30K"
    "Lm1pbml7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1tdXRlKX0KLyogZGVtbyBwbGF5ZXIgKi8KLnBsYXll"
    "cntwb3NpdGlvbjpyZWxhdGl2ZTttYXJnaW46MjRweCBhdXRvIDA7bWF4LXdpZHRoOjcyMHB4O2FzcGVjdC1yYXRpbzoxNi85O2Jv"
    "cmRlci1yYWRpdXM6MTZweDtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMDMwNTBiO2JvcmRlcjoxcHggc29saWQgdmFyKC0t"
    "bGluZSk7Ym94LXNoYWRvdzowIDI2cHggNjZweCByZ2JhKDAsMCwwLC42KX0KLnBsYXllciBjYW52YXN7d2lkdGg6MTAwJTtoZWln"
    "aHQ6MTAwJTtkaXNwbGF5OmJsb2NrfQoucGJhcntwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjA7cmlnaHQ6MDtib3R0b206MDtoZWln"
    "aHQ6NXB4O2JhY2tncm91bmQ6cmdiYSgyNTUsMjU1LDI1NSwuMTIpfQoucGJhciBpe2Rpc3BsYXk6YmxvY2s7aGVpZ2h0OjEwMCU7"
    "d2lkdGg6MDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZyx2YXIoLS1waW5rKSx2YXIoLS1nb2xkKSx2YXIoLS1vaykp"
    "fQoucGJ0bntwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjEycHg7Ym90dG9tOjE0cHg7YmFja2dyb3VuZDpyZ2JhKDUsNywxNSwuNyk7"
    "Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4yNSk7Y29sb3I6I2ZmZjtib3JkZXItcmFkaXVzOjk5OXB4O3dpZHRo"
    "OjM4cHg7aGVpZ2h0OjM4cHg7Zm9udC1zaXplOjE0cHg7Y3Vyc29yOnBvaW50ZXJ9Ci5wdGltZXtwb3NpdGlvbjphYnNvbHV0ZTty"
    "aWdodDoxNHB4O2JvdHRvbToyMHB4O2ZvbnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7Y29sb3I6I2NmZDZlNjt0ZXh0LXNoYWRvdzow"
    "IDFweCA0cHggIzAwMH0KLmxvY2t7cG9zaXRpb246YWJzb2x1dGU7aW5zZXQ6MDtkaXNwbGF5Om5vbmU7ZmxleC1kaXJlY3Rpb246"
    "Y29sdW1uO2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2dhcDoxMHB4O3RleHQtYWxpZ246Y2VudGVy"
    "O3BhZGRpbmc6MjRweDtiYWNrZ3JvdW5kOnJnYmEoNSw3LDE1LC44NCk7YmFja2Ryb3AtZmlsdGVyOmJsdXIoN3B4KX0KLmxvY2su"
    "b257ZGlzcGxheTpmbGV4fQp0YWJsZXt3aWR0aDoxMDAlO2JvcmRlci1jb2xsYXBzZTpjb2xsYXBzZTttYXJnaW4tdG9wOjEwcHg7"
    "Zm9udC1zaXplOjE0cHh9CnRkLHRoe3RleHQtYWxpZ246bGVmdDtwYWRkaW5nOjlweCA2cHg7Ym9yZGVyLWJvdHRvbToxcHggc29s"
    "aWQgcmdiYSgyNTUsMjU1LDI1NSwuMDgpfQp0aHtmb250OjUwMCAxMC41cHggdmFyKC0tbW9ubyk7bGV0dGVyLXNwYWNpbmc6LjFl"
    "bTtjb2xvcjp2YXIoLS1tdXRlKX10ZCBie2NvbG9yOnZhcigtLW9rKX0KLnN0cHtkaXNwbGF5OmZsZXg7Z2FwOjE0cHg7cGFkZGlu"
    "ZzoxMnB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMDYpfQouc3RwIC5ue2ZsZXg6bm9uZTt3"
    "aWR0aDozNHB4O2hlaWdodDozNHB4O2JvcmRlci1yYWRpdXM6NTAlO2JhY2tncm91bmQ6Y29uaWMtZ3JhZGllbnQodmFyKC0tcGlu"
    "ayksdmFyKC0tZ29sZCksdmFyKC0tb2spLHZhcigtLXBpbmspKTtjb2xvcjojMDUwNzBmO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVt"
    "czpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtmb250OjcwMCAxNHB4IHZhcigtLW1vbm8pfQouc3RwIGg0e2ZvbnQtc2l6"
    "ZToxNS41cHh9LnN0cCBwe2ZvbnQtc2l6ZToxMy41cHg7Y29sb3I6I2I2YzBkNn0KcHJle2JhY2tncm91bmQ6IzAzMDUwYjtib3Jk"
    "ZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6OXB4O3BhZGRpbmc6MTJweDtmb250OjEycHggdmFyKC0tbW9u"
    "byk7Y29sb3I6I2NmZTZkOTtvdmVyZmxvdy14OmF1dG87d2hpdGUtc3BhY2U6cHJlLXdyYXA7d29yZC1icmVhazpicmVhay1hbGw7"
    "bWFyZ2luLXRvcDo4cHh9Ci5ub3Rle2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO21hcmdpbi10b3A6MTBweH0KPC9z"
    "dHlsZT48L2hlYWQ+PGJvZHk+PGRpdiBjbGFzcz0id3JhcCI+CjxkaXYgY2xhc3M9InRvcCI+PGRpdiBjbGFzcz0iYnJhbmQiPm1v"
    "bm9wPGI+IHN0dWRpbzwvYj4gwrcgYnkgc2ViYmkucHJvPC9kaXY+PG5hdj48YSBocmVmPSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9j"
    "aW5lbWEiPkNpbmVtYTwvYT48YSBocmVmPSIvdG9vbHMiPlRvb2xzPC9hPjwvbmF2PjwvZGl2PgoKPGRpdiBjbGFzcz0iaGVybyI+"
    "PGRpdiBjbGFzcz0ia2ljayI+TU9OT1BPTElTRSBZT1VSIENPTlRFTlQ8L2Rpdj4KPGgxPkxvY2sgeW91ciB2aWRlbyBpbiAxMCBz"
    "ZWNvbmRzLjwvaDE+CjxwPlBpY2sgYSB2aWRlbywgc2V0IGEgcHJpY2UsIHRhcCBvbmNlLiBZb3UgZ2V0IGEgZmluaXNoZWQgcGxh"
    "eWVyIGJhY2sgd2l0aCB0aGUgbG9jayBhbHJlYWR5IGluIGl0LiBZb3VyIHZpZGVvIG5ldmVyIGxlYXZlcyB5b3VyIHBob25lOiB3"
    "ZSBoYW5kIGl0IHN0cmFpZ2h0IGJhY2ssIGxvY2tlZC48L3A+CjxkaXYgY2xhc3M9ImJhZGdlcyI+PHNwYW4+8J+UkiBOb3RoaW5n"
    "IHVwbG9hZGVkPC9zcGFuPjxzcGFuPvCfkrcgWW91IGtlZXAgNzAlIG9mIGV2ZXJ5IHZpZXc8L3NwYW4+PHNwYW4+4pqhIFJlYWR5"
    "IGluIHNlY29uZHM8L3NwYW4+PHNwYW4+8J+OrCBTaGFyZSBhbnl3aGVyZTwvc3Bhbj48L2Rpdj4KPC9kaXY+Cgo8c2VjdGlvbiBp"
    "ZD0ibG9ja2l0IiBzdHlsZT0iYm9yZGVyLXRvcDowO21hcmdpbi10b3A6MjBweDtwYWRkaW5nLXRvcDoxMHB4Ij4KIDxoMj5Mb2Nr"
    "IGEgdmlkZW8gbm93PC9oMj4KIDxwIGNsYXNzPSJsZWFkIj5FdmVyeXRoaW5nIGhhcHBlbnMgb24geW91ciBvd24gZGV2aWNlLiBU"
    "aGUgdmlkZW8gaXMgcmVhZCwgZmluZ2VycHJpbnRlZCBhbmQgd3JhcHBlZCBpbiBpdHMgb3duIHBsYXllciwgdGhlbiBoYW5kZWQg"
    "YmFjayB0byB5b3UgYXMgb25lIGZpbGUuPC9wPgogPGRpdiBjbGFzcz0iZ3JpZCB0d28iPgogIDxkaXYgY2xhc3M9ImNhcmQiPgog"
    "ICA8bGFiZWw+WW91ciB2aWRlbzwvbGFiZWw+PGlucHV0IHR5cGU9ImZpbGUiIGlkPSJ1RmlsZSIgYWNjZXB0PSJ2aWRlby8qIj4K"
    "ICAgPGxhYmVsPlRpdGxlPC9sYWJlbD48aW5wdXQgaWQ9InVUaXRsZSIgcGxhY2Vob2xkZXI9IldoYXQgaXMgaXQgY2FsbGVkPyI+"
    "CiAgIDxsYWJlbD5GcmVlIHByZXZpZXc8L2xhYmVsPjxpbnB1dCBpZD0idUZyZWUiIHR5cGU9InJhbmdlIiBtaW49IjEwIiBtYXg9"
    "IjgwIiB2YWx1ZT0iNTAiPgogICA8ZGl2IGNsYXNzPSJtaW5pIiBpZD0idUZyZWVMYWIiPkZpcnN0IDUwJSBwbGF5cyBmcmVlPC9k"
    "aXY+CiAgIDxsYWJlbD5QcmljZSB0byB1bmxvY2sgKHBlbmNlKTwvbGFiZWw+PGlucHV0IGlkPSJ1UHJpY2UiIGlucHV0bW9kZT0i"
    "ZGVjaW1hbCIgdmFsdWU9IjEwIj4KICAgPGxhYmVsPllvdXIgY3JlYXRvciBuYW1lPC9sYWJlbD48aW5wdXQgaWQ9InVXaG8iIHBs"
    "YWNlaG9sZGVyPSJXaG8gZ2V0cyBwYWlkPyI+CiAgIDxkaXYgY2xhc3M9Im1pbmkiPlZpZXdlcnMgdW5sb2NrIHdpdGggc2ViYmku"
    "cHJvIGNyZWRpdC4gWW91ciA3MCUgc2hhcmUgbGFuZHMgaW4geW91ciBiYWxhbmNlIHRoZSBtb21lbnQgdGhleSBkbywgYW5kIGV2"
    "ZXJ5IHBhaWQgdmlldyBpcyBzZWFsZWQgb24gdGhlIGNoYWluLjwvZGl2PgogICA8YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJ1R28i"
    "IHN0eWxlPSJ3aWR0aDoxMDAlO21hcmdpbi10b3A6MThweCI+8J+UkiBMb2NrIGl0PC9idXR0b24+CiAgIDxkaXYgY2xhc3M9InBy"
    "b2ciIGlkPSJ1UHJvZ1dyYXAiIHN0eWxlPSJkaXNwbGF5Om5vbmUiPjxpIGlkPSJ1UHJvZyI+PC9pPjwvZGl2PgogICA8ZGl2IGNs"
    "YXNzPSJvdXQiIGlkPSJ1T3V0Ij48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgPGgzPldoYXQgY29tZXMg"
    "YmFjazwvaDM+CiAgIDxwPk9uZSBmaWxlOiA8Yj55b3VyLXRpdGxlLWxvY2tlZC5odG1sPC9iPi4gT3BlbiBpdCBvbiBhbnkgcGhv"
    "bmUgb3IgY29tcHV0ZXIsIGVtYWlsIGl0LCBwdXQgaXQgb24geW91ciB3ZWJzaXRlLCBvciBwb3N0IHRoZSBsaW5rIGFueXdoZXJl"
    "LjwvcD4KICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij4KICAgIDxkaXYgY2xhc3M9InN0cCI+PGRpdiBjbGFzcz0ibiI+"
    "MTwvZGl2PjxkaXY+PGg0PlBsYXlzIGZyZWUgdG8geW91ciBjdXQtb2ZmPC9oND48cD5Zb3VyIHZpZXdlciB3YXRjaGVzIHRoZSBw"
    "cmV2aWV3IGV4YWN0bHkgYXMgbm9ybWFsLjwvcD48L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InN0cCI+PGRpdiBjbGFzcz0i"
    "biI+MjwvZGl2PjxkaXY+PGg0PlRoZSBsb2NrIGRyb3BzIGluPC9oND48cD5CbHVycmVkLCB3aXRoIHlvdXIgcHJpY2Ugb24gaXQu"
    "IFNraXBwaW5nIGFoZWFkIGlzIGJsb2NrZWQuPC9wPjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RwIj48ZGl2IGNsYXNz"
    "PSJuIj4zPC9kaXY+PGRpdj48aDQ+VGhleSBwYXksIGl0IHBsYXlzPC9oND48cD5Zb3VyIHBheW1lbnQgbGluayBvcGVuczsgd2hl"
    "biB0aGV5IGNvbWUgYmFjayBpdCB1bmxvY2tzIGFuZCBzdGF5cyB1bmxvY2tlZCBvbiB0aGF0IGRldmljZS48L3A+PC9kaXY+PC9k"
    "aXY+CiAgIDwvZGl2PgogICA8cCBjbGFzcz0ibm90ZSI+QmVzdCB1cCB0byBhYm91dCAyNSBNQiwgd2hpY2ggaXMgdHdvIG9yIHRo"
    "cmVlIG1pbnV0ZXMgb2YgcGhvbmUgdmlkZW8uIEJpZ2dlciBmaWxtcyBzdGlsbCB3b3JrIGJ1dCB0YWtlIGxvbmdlciB0byBidWls"
    "ZC48L3A+CiAgPC9kaXY+CiA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9InBhaWQiPgogPGgyPkhvdyB2aWV3ZXJzIHBh"
    "eSwgd2l0aCBubyBmYWZmIGZvciB5b3U8L2gyPgogPHAgY2xhc3M9ImxlYWQiPllvdSBzZXQgbm8gcGF5bWVudCBsaW5rcyB1cCBh"
    "bmQgeW91IGNoYXNlIG5vYm9keS4gVmlld2VycyB0b3AgdXAgb25jZSBvbiBzZWJiaS5wcm8gYW5kIHNwZW5kIGl0IGEgdGFwIGF0"
    "IGEgdGltZSBvbiBhbnkgbG9ja2VkIHZpZGVvLjwvcD4KIDxkaXYgY2xhc3M9ImdyaWQgdGhyZWUiPgogIDxkaXYgY2xhc3M9ImNh"
    "cmQiPjxoMz5UaGV5IHRvcCB1cCBvbmNlPC9oMz48cD5BIGZldyBwb3VuZHMgb2YgY3JlZGl0LCBvbmUgY2FyZCBwYXltZW50LCBv"
    "biBzZWJiaS5wcm8uIE5vdCBvbiB5b3VyIHZpZGVvLCBhbmQgbm90IHBlciB2aWV3LjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJj"
    "YXJkIj48aDM+RWFjaCB1bmxvY2sgc3BlbmRzIHBlbm5pZXM8L2gzPjxwPllvdXIgcHJpY2UgY29tZXMgb2ZmIHRoZWlyIGJhbGFu"
    "Y2UuIDcwJSBsYW5kcyBpbiB5b3VyIGJhbGFuY2UsIDMwJSBjb3ZlcnMgdGhlIGxvY2ssIHRoZSBwYXltZW50IGFuZCB0aGUgc2Vh"
    "bGVkIHJlY2VpcHQuPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPjxoMz5FdmVyeSB2aWV3IGlzIHNlYWxlZDwvaDM+PHA+"
    "VGhlIHVubG9jayBpcyB3cml0dGVuIHRvIHRoZSBjaGFpbiB3aXRoIGEgYmxvY2sgbnVtYmVyLCBzbyB5b3VyIHBhaWQgdmlld3Mg"
    "Y2FuIGJlIHByb3ZlZCB0byBhIHNwb25zb3IuPC9wPjwvZGl2PgogPC9kaXY+CiA8YSBjbGFzcz0iYnRuIGdob3N0IiBocmVmPSJo"
    "dHRwczovL3NlYmJpLnByby9jcmVkaXRzIiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4Ij5TZWUgYSB2aWV3ZXIncyBjcmVkaXQgcGFn"
    "ZSDihpI8L2E+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJkZW1vIj4KIDxoMj5TZWUgZXhhY3RseSB3aGF0IGEgdmlld2VyIHNl"
    "ZXM8L2gyPgogPHAgY2xhc3M9ImxlYWQiPlRoaXMgaXMgYSByZWFsIDM4LXNlY29uZCBmaWxtIGFib3V0IHNlYmJpLnBybywgcGxh"
    "eWluZyBpbiB0aGUgc2FtZSBsb2NrLiBJdCBzdG9wcyBoYWxmd2F5LCBqdXN0IGxpa2UgeW91cnMgd2lsbC48L3A+CiA8ZGl2IGNs"
    "YXNzPSJwbGF5ZXIiIGlkPSJwbGF5ZXIiPgogIDxjYW52YXMgaWQ9ImN2IiB3aWR0aD0iMTI4MCIgaGVpZ2h0PSI3MjAiPjwvY2Fu"
    "dmFzPgogIDxidXR0b24gY2xhc3M9InBidG4iIGlkPSJwYiI+4pa2PC9idXR0b24+PGRpdiBjbGFzcz0icHRpbWUiIGlkPSJwdCI+"
    "MDowMCAvIDA6Mzg8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYmFyIj48aSBpZD0icGYiPjwvaT48L2Rpdj4KICA8ZGl2IGNsYXNzPSJs"
    "b2NrIiBpZD0ibG9jayI+CiAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTozMHB4Ij7wn5SSPC9kaXY+CiAgIDxoMyBzdHlsZT0iZm9u"
    "dC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6Y2xhbXAoMjBweCw0dncsMzBweCkiPjEwcCB0"
    "byB3YXRjaCB0aGUgcmVzdDwvaDM+CiAgIDxwIHN0eWxlPSJjb2xvcjojYjZjMGQ2O2ZvbnQtc2l6ZToxMy41cHg7bWF4LXdpZHRo"
    "OjQwY2giPllvdSBoYXZlIGhhZCB0aGUgZnJlZSBoYWxmLiBVbmxvY2sgdGhlIGZ1bGwgdmlkZW8gZm9yIDEwcCwgb25lIHRhcC48"
    "L3A+CiAgIDxidXR0b24gY2xhc3M9ImJ0biBnb2xkIiBpZD0icGF5QnRuIj5VbmxvY2sgZm9yIDEwcDwvYnV0dG9uPgogICA8ZGl2"
    "IGNsYXNzPSJtaW5pIj5EZW1vIG9ubHkg4oCUIG5vIHBheW1lbnQgaXMgdGFrZW48L2Rpdj4KICAgPGRpdiBpZD0icmNwdCIgc3R5"
    "bGU9ImZvbnQ6NTAwIDExLjVweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1vaykiPjwvZGl2PgogIDwvZGl2PgogPC9kaXY+Cjwv"
    "c2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjaW5lbWEiPgogPGgyPlB1dCBpdCBpbiB0aGUgMTBwIFdpbmc8L2gyPgogPHAgY2xhc3M9"
    "ImxlYWQiPlRoZSBzZWJiaS5wcm8gY2luZW1hIGhhcyB0d28gd2luZ3M6IGdvdmVybmFuY2Ugb24gb25lIHNpZGUsIGFuZCB0aGUg"
    "MTBwIFdpbmcgb24gdGhlIG90aGVyLCB3aGVyZSBjcmVhdG9ycycgbG9ja2VkIHZpZGVvcyBwbGF5LiBTZW5kIHVzIHRoZSBsaW5r"
    "IHRvIHlvdXIgbG9ja2VkIHBsYXllciBhbmQgaXQgdGFrZXMgYSBzY3JlZW4uPC9wPgogPGRpdiBjbGFzcz0iZ3JpZCB0d28iPgog"
    "IDxkaXYgY2xhc3M9ImNhcmQiPgogICA8bGFiZWw+TGluayB0byB5b3VyIGxvY2tlZCB2aWRlbzwvbGFiZWw+PGlucHV0IGlkPSJt"
    "VXJsIiBwbGFjZWhvbGRlcj0iaHR0cHM6Ly/igKYiPgogICA8bGFiZWw+VGl0bGU8L2xhYmVsPjxpbnB1dCBpZD0ibVRpdGxlIiBw"
    "bGFjZWhvbGRlcj0iV2hhdCBpcyBpdCBjYWxsZWQ/Ij4KICAgPGxhYmVsPllvdXIgbmFtZSBvciBjaGFubmVsPC9sYWJlbD48aW5w"
    "dXQgaWQ9Im1XaG8iIHBsYWNlaG9sZGVyPSJXaG8gbWFkZSBpdD8iPgogICA8bGFiZWw+UHJpY2UgKHBlbmNlKTwvbGFiZWw+PGlu"
    "cHV0IGlkPSJtUHJpY2UiIGlucHV0bW9kZT0ibnVtZXJpYyIgdmFsdWU9IjEwIj4KICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0i"
    "bUdvIiBzdHlsZT0id2lkdGg6MTAwJTttYXJnaW4tdG9wOjE2cHgiPvCfjqwgU2VuZCBpdCB0byB0aGUgMTBwIFdpbmc8L2J1dHRv"
    "bj4KICAgPGRpdiBjbGFzcz0ib3V0IiBpZD0ibU91dCI+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgIDxo"
    "Mz5Ib3VzZSBydWxlczwvaDM+CiAgIDxwPk9ubHkgeW91ciBvd24gd29yay4gQnkgc2VuZGluZyBpdCB5b3UgY29uZmlybSB5b3Ug"
    "aG9sZCB0aGUgcmlnaHRzIHRvIHRoZSB2aWRlbyBhbmQgZXZlcnl0aGluZyBpbiBpdC48L3A+CiAgIDxwIHN0eWxlPSJtYXJnaW4t"
    "dG9wOjEwcHgiPldlIG5ldmVyIGhvbGQgeW91ciB2aWRlbywgb25seSB0aGUgbGluayB5b3UgZ2l2ZSB1cyBhbmQgdGhlIHRpdGxl"
    "LiBFdmVyeSBzdWJtaXNzaW9uIGlzIHNlYWxlZCBvbiB0aGUgY2hhaW4gd2hlbiBpdCBsYW5kcywgc28gdGhlIGRhdGUgeW91IHNl"
    "bnQgaXQgaXMgcHJvdmFibGUuPC9wPgogICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij5TY3JlZW5zIGFyZSByZXZpZXdlZCBi"
    "ZWZvcmUgdGhleSBnbyB1cC48L3A+CiAgIDxhIGNsYXNzPSJidG4gZ2hvc3QiIGhyZWY9Ii9jaW5lbWEiIHN0eWxlPSJtYXJnaW4t"
    "dG9wOjE0cHgiPlZpc2l0IHRoZSBjaW5lbWEg4oaSPC9hPgogIDwvZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlk"
    "PSJwcmljZSI+CiA8aDI+V2hhdCBpdCBjb3N0czwvaDI+CiA8ZGl2IGNsYXNzPSJncmlkIHR3byI+CiAgPGRpdiBjbGFzcz0iY2Fy"
    "ZCI+PGgzPjUwcCBwZXIgdmlkZW8sIHBlciBtb250aDwvaDM+PHA+VGhlIGtlZXAtaXQtbG9ja2VkIGZlZS4gU3RvcCBwYXlpbmcg"
    "YW5kIHRoZSBsb2NrIGxpZnRzLiBUaGUgdmlkZW8gc3RheXMgeW91cnMgYW5kIGV2ZXJ5IHBlbm55IHlvdSBoYXZlIG1hZGUgc3Rh"
    "eXMgeW91cnMuPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPjxoMz5Zb3Uga2VlcCA3cCBvZiBldmVyeSAxMHA8L2gzPjxw"
    "PlRocmVlIHBlbmNlIG9mIGVhY2ggdW5sb2NrIGNvdmVycyB0aGUgbG9jaywgdGhlIHBheW1lbnQgYW5kIHRoZSBzZWFsZWQgcmVj"
    "ZWlwdC4gVGhhdCBpcyA3MCUgdG8geW91LjwvcD48L2Rpdj4KIDwvZGl2PgogPHRhYmxlPjx0cj48dGg+WW91ciBwcmljZTwvdGg+"
    "PHRoPllvdSBrZWVwPC90aD48dGg+c2ViYmkucHJvPC90aD48dGg+MSwwMDAgdmlld3M8L3RoPjwvdHI+CiA8dHI+PHRkPjVwPC90"
    "ZD48dGQ+PGI+My41cDwvYj48L3RkPjx0ZD4xLjVwPC90ZD48dGQ+PGI+wqMzNTwvYj48L3RkPjwvdHI+CiA8dHI+PHRkPjEwcDwv"
    "dGQ+PHRkPjxiPjdwPC9iPjwvdGQ+PHRkPjNwPC90ZD48dGQ+PGI+wqM3MDwvYj48L3RkPjwvdHI+CiA8dHI+PHRkPjI1cDwvdGQ+"
    "PHRkPjxiPjE3LjVwPC9iPjwvdGQ+PHRkPjcuNXA8L3RkPjx0ZD48Yj7CozE3NTwvYj48L3RkPjwvdHI+CiA8dHI+PHRkPjUwcDwv"
    "dGQ+PHRkPjxiPjM1cDwvYj48L3RkPjx0ZD4xNXA8L3RkPjx0ZD48Yj7CozM1MDwvYj48L3RkPjwvdHI+PC90YWJsZT4KIDxkaXYg"
    "Y2xhc3M9ImdyaWQgdHdvIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgPGgzPldvcmsg"
    "b3V0IHlvdXIgbW9udGg8L2gzPgogICA8bGFiZWw+UHJpY2UgcGVyIHZpZXcgKHBlbmNlKTwvbGFiZWw+PGlucHV0IGlkPSJjUHJp"
    "Y2UiIGlucHV0bW9kZT0iZGVjaW1hbCIgdmFsdWU9IjEwIj4KICAgPGxhYmVsPlZpZGVvcyBsb2NrZWQ8L2xhYmVsPjxpbnB1dCBp"
    "ZD0iY1ZpZHMiIGlucHV0bW9kZT0ibnVtZXJpYyIgdmFsdWU9IjQiPgogICA8bGFiZWw+UGFpZCB2aWV3cyBwZXIgdmlkZW8sIHBl"
    "ciBtb250aDwvbGFiZWw+PGlucHV0IGlkPSJjVmlld3MiIGlucHV0bW9kZT0ibnVtZXJpYyIgdmFsdWU9IjUwMCI+CiAgIDxkaXYg"
    "Y2xhc3M9Im91dCBvbiIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImJpZyIgaWQ9ImNPdXQiPsKjMDwvc3Bh"
    "bj55b3VycyBhZnRlciB0aGUgbW9udGhseSBmZWU8ZGl2IGlkPSJjRGV0YWlsIiBzdHlsZT0iY29sb3I6IzhhOTNhZDttYXJnaW4t"
    "dG9wOjZweCI+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPldoeSBwZW9wbGUgdGFwPC9oMz48"
    "cD5Ob2JvZHkgcGF5cyBmb3IgYSB2aWRlbyB0aGV5IGhhdmUgbm90IHNlZW4uIEFsbW9zdCBldmVyeW9uZSB0YXBzIDEwcCBvbmNl"
    "IHRoZXkgYXJlIGhvb2tlZCBoYWxmd2F5IHRocm91Z2guIFRoZSBmcmVlIGhhbGYgc2VsbHMgaXQ7IHRoZSBsb2NrIGVhcm5zIGZy"
    "b20gaXQuPC9wPgogIDxwIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPkFuZCBiZWNhdXNlIGV2ZXJ5IHBhaWQgdmlldyBjYW4gYmUg"
    "c2VhbGVkIG9uIGEgcHVibGljIGNoYWluLCB5b3UgY2FuIHNob3cgYSBzcG9uc29yIGEgdmlldyBjb3VudCB0aGV5IGNhbiBjaGVj"
    "ayB0aGVtc2VsdmVzLiBObyBvdGhlciBwbGF0Zm9ybSBnaXZlcyB5b3UgdGhhdC48L3A+PC9kaXY+CiA8L2Rpdj4KPC9zZWN0aW9u"
    "PgoKPHNlY3Rpb24gaWQ9ImNlbnRyZSI+CiA8aDI+WW91ciBjb250cm9sIGNlbnRyZTwvaDI+CiA8ZGl2IGNsYXNzPSJncmlkIHRo"
    "cmVlIj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+TG9jayBidWlsZGVyPC9oMz48cD5DdXQtb2ZmIHBvaW50LCBwcmljZSBhbmQg"
    "cGF5bWVudCBsaW5rLiBQcmV2aWV3IGV4YWN0bHkgd2hhdCBhIHZpZXdlciBzZWVzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJj"
    "YXJkIj48aDM+U2hhcmUgcGFjazwvaDM+PHA+T25lIGZpbGUsIG9uZSBsaW5rLCBhbmQgYW4gZW1iZWQgc25pcHBldCBmb3IgeW91"
    "ciBvd24gc2l0ZS48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPlNlYWxlZCByZWNlaXB0czwvaDM+PHA+UGFpZCB2"
    "aWV3cyB3aXRoIGJsb2NrIG51bWJlcnMsIGV4cG9ydGFibGUgZm9yIGEgc3BvbnNvciBvciBhbiBhY2NvdW50YW50LjwvcD48L2Rp"
    "dj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+VGhlIDEwcCBXaW5nPC9oMz48cD5Zb3VyIGxvY2tlZCB2aWRlb3Mgb24gdGhlIGNp"
    "bmVtYSdzIGNyZWF0b3Igc2NyZWVucy48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPkZpbmdlcnByaW50czwvaDM+"
    "PHA+RXZlcnkgZmlsZSBjYXJyaWVzIGEgaGFzaCBvZiB5b3VyIGV4YWN0IGN1dCwgc28geW91IGNhbiBwcm92ZSB3aGljaCB2ZXJz"
    "aW9uIGlzIHlvdXJzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+UHJvb2YgYmFkZ2U8L2gzPjxwPlNob3cgYSB2"
    "ZXJpZmllZCB2aWV3IGNvdW50IG9uIHlvdXIgb3duIHNpdGUsIGxpdmUuPC9wPjwvZGl2PgogPC9kaXY+CiA8cHJlPiZsdDtpZnJh"
    "bWUgc3JjPSJodHRwczovL3lvdXItc2l0ZS5jb20veW91ci12aWRlby1sb2NrZWQuaHRtbCIgd2lkdGg9IjEwMCUiIGhlaWdodD0i"
    "NDIwIiBhbGxvd2Z1bGxzY3JlZW4mZ3Q7Jmx0Oy9pZnJhbWUmZ3Q7PC9wcmU+CiA8YSBjbGFzcz0iYnRuIiBocmVmPSIjbG9ja2l0"
    "Ij5Mb2NrIHlvdXIgZmlyc3QgdmlkZW8g4oaSPC9hPgo8L3NlY3Rpb24+CjwvZGl2Pgo8c2NyaXB0IGlkPSJ0cGwiIHR5cGU9InRl"
    "eHQvcGxhaW4iPlBDRkVUME5VV1ZCRklHaDBiV3crUEdoMGJXd2diR0Z1WnowaVpXNGlQanhvWldGa1BqeHRaWFJoSUdOb1lYSnpa"
    "WFE5SWxWVVJpMDRJajRLUEcxbGRHRWdibUZ0WlQwaWRtbGxkM0J2Y25RaUlHTnZiblJsYm5ROUluZHBaSFJvUFdSbGRtbGpaUzEz"
    "YVdSMGFDeHBibWwwYVdGc0xYTmpZV3hsUFRFc2RtbGxkM0J2Y25RdFptbDBQV052ZG1WeUlqNEtQSFJwZEd4bFBsOWZWRWxVVEVW"
    "Zlh6d3ZkR2wwYkdVK0NqeHpkSGxzWlQ0S0tudGliM2d0YzJsNmFXNW5PbUp2Y21SbGNpMWliM2c3YldGeVoybHVPakE3Y0dGa1pH"
    "bHVaem93ZlFwaWIyUjVlMkpoWTJ0bmNtOTFibVE2Y21Ga2FXRnNMV2R5WVdScFpXNTBLR1ZzYkdsd2MyVWdZWFFnTlRBbElEQWxM"
    "Q014WVRFd016Z3NJekExTURjd1ppQTJOU1VwTzJOdmJHOXlPaU5sT0dWa1pqYzdabTl1ZEMxbVlXMXBiSGs2YzNsemRHVnRMWFZw"
    "TEMxaGNIQnNaUzF6ZVhOMFpXMHNJbE5sWjI5bElGVkpJaXh6WVc1ekxYTmxjbWxtTzIxcGJpMW9aV2xuYUhRNk1UQXdkbWc3Wkds"
    "emNHeGhlVHBtYkdWNE8yRnNhV2R1TFdsMFpXMXpPbU5sYm5SbGNqdHFkWE4wYVdaNUxXTnZiblJsYm5RNlkyVnVkR1Z5TzNCaFpH"
    "UnBibWM2TVRad2VIMEtMbmQ3ZDJsa2RHZzZNVEF3SlR0dFlYZ3RkMmxrZEdnNk9EWXdjSGg5Q21neGUyWnZiblF0YzJsNlpUcGpi"
    "R0Z0Y0NneE9IQjRMRFIyZHl3eU5uQjRLVHRtYjI1MExYZGxhV2RvZERvMk1EQTdiV0Z5WjJsdUxXSnZkSFJ2YlRveE1IQjRmUW91"
    "Y0h0d2IzTnBkR2x2YmpweVpXeGhkR2wyWlR0aWIzSmtaWEl0Y21Ga2FYVnpPakUyY0hnN2IzWmxjbVpzYjNjNmFHbGtaR1Z1TzJK"
    "aFkydG5jbTkxYm1RNkl6QXdNRHRpYjNKa1pYSTZNWEI0SUhOdmJHbGtJSEpuWW1Fb01qQXhMREUyT0N3M05pd3VNelVwTzJKdmVD"
    "MXphR0ZrYjNjNk1DQXlObkI0SURjd2NIZ2djbWRpWVNnd0xEQXNNQ3d1TmpVcExEQWdNQ0EwTkhCNElISm5ZbUVvTWpFekxERTFO"
    "U3d5TlRVc0xqRXlLWDBLZG1sa1pXOTdkMmxrZEdnNk1UQXdKVHRrYVhOd2JHRjVPbUpzYjJOcmZRb3ViR3Q3Y0c5emFYUnBiMjQ2"
    "WVdKemIyeDFkR1U3YVc1elpYUTZNRHRrYVhOd2JHRjVPbTV2Ym1VN1pteGxlQzFrYVhKbFkzUnBiMjQ2WTI5c2RXMXVPMkZzYVdk"
    "dUxXbDBaVzF6T21ObGJuUmxjanRxZFhOMGFXWjVMV052Ym5SbGJuUTZZMlZ1ZEdWeU8yZGhjRG94TVhCNE8zUmxlSFF0WVd4cFoy"
    "NDZZMlZ1ZEdWeU8zQmhaR1JwYm1jNk1qSndlRHRpWVdOclozSnZkVzVrT25KblltRW9OU3czTERFMUxDNDROeWs3WW1GamEyUnli"
    "M0F0Wm1sc2RHVnlPbUpzZFhJb09YQjRLWDBLTG14ckxtOXVlMlJwYzNCc1lYazZabXhsZUgwS0xtbGplMlp2Ym5RdGMybDZaVG96"
    "TW5CNGZRb3ViR3NnYURKN1ptOXVkQzF6YVhwbE9tTnNZVzF3S0RFNWNIZ3NOQzQyZG5jc016QndlQ2s3Wm05dWRDMTNaV2xuYUhR"
    "Nk5qQXdmUW91YkdzZ2NIdGpiMnh2Y2pvallqWmpNR1EyTzJadmJuUXRjMmw2WlRveE5IQjRPMjFoZUMxM2FXUjBhRG96T0dOb2ZR"
    "b3VZbnRpWVdOclozSnZkVzVrT2lOak9XRTROR003WTI5c2IzSTZJekExTURjd1pqdGliM0prWlhJNk1EdGliM0prWlhJdGNtRmth"
    "WFZ6T2pFeGNIZzdjR0ZrWkdsdVp6b3hOSEI0SURJMGNIZzdabTl1ZERvMk1EQWdNVFZ3ZUNCMWFTMXRiMjV2YzNCaFkyVXNUV1Z1"
    "Ykc4c2JXOXViM053WVdObE8yTjFjbk52Y2pwd2IybHVkR1Z5TzNSbGVIUXRaR1ZqYjNKaGRHbHZianB1YjI1bE8ySnZlQzF6YUdG"
    "a2IzYzZNQ0F3SURJNGNIZ2djbWRpWVNneU1ERXNNVFk0TERjMkxDNDBOU2w5Q2k1aUxtZG9iM04wZTJKaFkydG5jbTkxYm1RNmRI"
    "Smhibk53WVhKbGJuUTdZMjlzYjNJNkkyWm1aanRpYjNKa1pYSTZNWEI0SUhOdmJHbGtJSEpuWW1Fb01qVTFMREkxTlN3eU5UVXNM"
    "akk0S1R0aWIzZ3RjMmhoWkc5M09tNXZibVU3Wm05dWRDMXphWHBsT2pFemNIZzdjR0ZrWkdsdVp6b3hNWEI0SURFNGNIaDlDaTV0"
    "ZTJadmJuUTZOVEF3SURFeGNIZ2dkV2t0Ylc5dWIzTndZV05sTEcxdmJtOXpjR0ZqWlR0amIyeHZjam9qT0dFNU0yRmtmUW91YjJ0"
    "N1ptOXVkRG8xTURBZ01USndlQ0IxYVMxdGIyNXZjM0JoWTJVc2JXOXViM053WVdObE8yTnZiRzl5T2lNM1ptVXpZakI5Q2k1aVlY"
    "SjdjRzl6YVhScGIyNDZZV0p6YjJ4MWRHVTdiR1ZtZERvd08zSnBaMmgwT2pBN1ltOTBkRzl0T2pBN2FHVnBaMmgwT2pSd2VEdGlZ"
    "V05yWjNKdmRXNWtPbkpuWW1Fb01qVTFMREkxTlN3eU5UVXNMakV5S1gwS0xtSmhjaUJwZTJScGMzQnNZWGs2WW14dlkyczdhR1Zw"
    "WjJoME9qRXdNQ1U3ZDJsa2RHZzZNRHRpWVdOclozSnZkVzVrT214cGJtVmhjaTFuY21Ga2FXVnVkQ2c1TUdSbFp5d2paRFU1WW1a"
    "bUxDTmpPV0U0TkdNc0l6ZG1aVE5pTUNsOUNpNTBZV2RzYVc1bGUzQnZjMmwwYVc5dU9tRmljMjlzZFhSbE8zUnZjRG94TUhCNE8y"
    "eGxablE2TVRKd2VEdGlZV05yWjNKdmRXNWtPbkpuWW1Fb05TdzNMREUxTEM0M05TazdZbTl5WkdWeU9qRndlQ0J6YjJ4cFpDQnla"
    "MkpoS0RJd01Td3hOamdzTnpZc0xqUXBPMkp2Y21SbGNpMXlZV1JwZFhNNk9UazVjSGc3Y0dGa1pHbHVaem8xY0hnZ01UQndlRHRt"
    "YjI1ME9qWXdNQ0F4TUM0MWNIZ2dkV2t0Ylc5dWIzTndZV05sTEcxdmJtOXpjR0ZqWlR0amIyeHZjam9qWXpsaE9EUmpmUW91ZEh0"
    "dFlYSm5hVzR0ZEc5d09qRXljSGc3Wm05dWREbzFNREFnTVRFdU5YQjRJSFZwTFcxdmJtOXpjR0ZqWlN4dGIyNXZjM0JoWTJVN1ky"
    "OXNiM0k2SXpoaE9UTmhaRHQwWlhoMExXRnNhV2R1T21ObGJuUmxjanRzYVc1bExXaGxhV2RvZERveExqZDlDaTUwSUdGN1kyOXNi"
    "M0k2STJNNVlUZzBZenQwWlhoMExXUmxZMjl5WVhScGIyNDZibTl1WlgwS1BDOXpkSGxzWlQ0OEwyaGxZV1ErUEdKdlpIaytQR1Jw"
    "ZGlCamJHRnpjejBpZHlJK0NqeG9NVDVmWDFSSlZFeEZYMTg4TDJneFBnbzhaR2wySUdOc1lYTnpQU0p3SWo0S0lEeDJhV1JsYnlC"
    "cFpEMGlkaUlnY0d4aGVYTnBibXhwYm1VZ1kyOXVkSEp2YkhNZ1kyOXVkSEp2YkhOTWFYTjBQU0p1YjJSdmQyNXNiMkZrSWlCa2FY"
    "TmhZbXhsY0dsamRIVnlaV2x1Y0dsamRIVnlaU0J6Y21NOUlsOWZVMUpEWDE4aVBqd3ZkbWxrWlc4K0NpQThaR2wySUdOc1lYTnpQ"
    "U0owWVdkc2FXNWxJaUJwWkQwaWRHRm5JajVHVWtWRklGQlNSVlpKUlZjOEwyUnBkajRLSUR4a2FYWWdZMnhoYzNNOUltSmhjaUkr"
    "UEdrZ2FXUTlJbkJtSWo0OEwyaytQQzlrYVhZK0NpQThaR2wySUdOc1lYTnpQU0pzYXlJZ2FXUTlJbXhySWo0S0lDQThaR2wySUdO"
    "c1lYTnpQU0pwWXlJK0ppTXhNamd5TnpRN1BDOWthWFkrQ2lBZ1BHZ3lJR2xrUFNKc2EyZ2lQbDlmVUZKSlEwVmZYM0FnZEc4Z2Qy"
    "RjBZMmdnZEdobElISmxjM1E4TDJneVBnb2dJRHh3SUdsa1BTSnNhM0FpUGxSb1lYUWdkMkZ6SUhSb1pTQm1jbVZsSUhCeVpYWnBa"
    "WGN1SUZWdWJHOWpheUIwYUdVZ2NtVnpkQ0IzYVhSb0lIbHZkWElnYzJWaVlta3VjSEp2SUdOeVpXUnBkQzQ4TDNBK0NpQWdQR0ox"
    "ZEhSdmJpQmpiR0Z6Y3owaVlpSWdhV1E5SW1kdklqNVZibXh2WTJzZ1ptOXlJRjlmVUZKSlEwVmZYM0E4TDJKMWRIUnZiajRLSUNB"
    "OFlTQmpiR0Z6Y3owaVlpQm5hRzl6ZENJZ2FXUTlJblJ2Y0NJZ2FISmxaajBpYUhSMGNITTZMeTl6WldKaWFTNXdjbTh2WTNKbFpH"
    "bDBjeUlnZEdGeVoyVjBQU0pmWW14aGJtc2lJSEpsYkQwaWJtOXZjR1Z1WlhJaVBsUnZjQ0IxY0NCamNtVmthWFE4TDJFK0NpQWdQ"
    "R1JwZGlCamJHRnpjejBpYlNJZ2FXUTlJbUpoYkNJK1BDOWthWFkrQ2lBZ1BHUnBkaUJqYkdGemN6MGliMnNpSUdsa1BTSnlZeUkr"
    "UEM5a2FYWStDaUE4TDJScGRqNEtQQzlrYVhZK0NqeGthWFlnWTJ4aGMzTTlJblFpUGt4dlkydGxaQ0IzYVhSb0lEeGhJR2h5WldZ"
    "OUltaDBkSEJ6T2k4dmMyVmlZbWt1Y0hKdkwyTnlaV0YwWlNJZ2RHRnlaMlYwUFNKZllteGhibXNpSUhKbGJEMGlibTl2Y0dWdVpY"
    "SWlQazF2Ym05d0lGTjBkV1JwYnp3dllUNGdKbTFwWkdSdmREc2dYMTlEVWtWQlZFOVNYMThnSm0xcFpHUnZkRHNnWm1sdVoyVnlj"
    "SEpwYm5RZ1gxOVRTRTlTVkVoQlUwaGZYeVpvWld4c2FYQTdQR0p5UGdwRmRtVnllU0J3WVdsa0lIWnBaWGNnYVhNZ2MyVmhiR1Zr"
    "SUc5dUlHRWdjSFZpYkdsaklHTm9ZV2x1TGlCVWFHbHpJSFpwWkdWdklIZGhjeUJ1WlhabGNpQjFjR3h2WVdSbFpDQmhibmwzYUdW"
    "eVpTNDhMMlJwZGo0S1BDOWthWFkrQ2p4elkzSnBjSFErQ2lobWRXNWpkR2x2YmlncGV3b2lkWE5sSUhOMGNtbGpkQ0k3Q25aaGNp"
    "QkJVRWs5SW1oMGRIQnpPaTh2YzJWaVlta3VjSEp2TDJNdklpd2dWa2xFUlU4OUlsOWZWa2xFUlU5SlJGOWZJaXdnVUZKSlEwVTlY"
    "MTlRVWtsRFJWOWZMQ0JEVWtWQlZFOVNQU0pmWDBOU1JVRlVUMUpmWHlJc0lFWlNSVVU5WDE5R1VrVkZYMTg3Q25aaGNpQjJQV1J2"
    "WTNWdFpXNTBMbWRsZEVWc1pXMWxiblJDZVVsa0tDSjJJaWtzYkdzOVpHOWpkVzFsYm5RdVoyVjBSV3hsYldWdWRFSjVTV1FvSW14"
    "cklpa3NjR1k5Wkc5amRXMWxiblF1WjJWMFJXeGxiV1Z1ZEVKNVNXUW9JbkJtSWlrc0NpQWdJQ0IwWVdjOVpHOWpkVzFsYm5RdVoy"
    "VjBSV3hsYldWdWRFSjVTV1FvSW5SaFp5SXBMR2R2UFdSdlkzVnRaVzUwTG1kbGRFVnNaVzFsYm5SQ2VVbGtLQ0puYnlJcExIUnZj"
    "Rjg5Wkc5amRXMWxiblF1WjJWMFJXeGxiV1Z1ZEVKNVNXUW9JblJ2Y0NJcExBb2dJQ0FnWW1Gc1BXUnZZM1Z0Wlc1MExtZGxkRVZz"
    "WlcxbGJuUkNlVWxrS0NKaVlXd2lLU3h5WXoxa2IyTjFiV1Z1ZEM1blpYUkZiR1Z0Wlc1MFFubEpaQ2dpY21NaUtTeHNhMmc5Wkc5"
    "amRXMWxiblF1WjJWMFJXeGxiV1Z1ZEVKNVNXUW9JbXhyYUNJcExHeHJjRDFrYjJOMWJXVnVkQzVuWlhSRmJHVnRaVzUwUW5sSlpD"
    "Z2liR3R3SWlrN0NuWmhjaUJ3WVdsa1BXWmhiSE5sTENCMmFXVjNaWEk5Ym5Wc2JEc0tablZ1WTNScGIyNGdhV1FvS1h0MGNubDdk"
    "bUZ5SUdzOWJHOWpZV3hUZEc5eVlXZGxMbWRsZEVsMFpXMG9Jbk5sWW1KcExuWnBaWGRsY2lJcE8ybG1LR3NwY21WMGRYSnVJR3Q5"
    "WTJGMFkyZ29aU2w3ZlFvZ2RtRnlJSE05SW5ZaUxHTTlJbUZpWTJSbFptZG9hV3ByYkcxdWIzQnhjbk4wZFhaM2VIbDZNREV5TXpR"
    "MU5qYzRPU0k3Wm05eUtIWmhjaUJwUFRBN2FUd3hPVHRwS3lzcGN5czlZMXROWVhSb0xtWnNiMjl5S0UxaGRHZ3VjbUZ1Wkc5dEtD"
    "a3FNellwWFRzS0lIUnllWHRzYjJOaGJGTjBiM0poWjJVdWMyVjBTWFJsYlNnaWMyVmlZbWt1ZG1sbGQyVnlJaXh6S1gxallYUmph"
    "Q2hsS1h0OWNtVjBkWEp1SUhOOUNuWnBaWGRsY2oxcFpDZ3BPd3BtZFc1amRHbHZiaUIxYm14dlkydE9iM2NvY21WektYdHdZV2xr"
    "UFhSeWRXVTdiR3N1WTJ4aGMzTk1hWE4wTG5KbGJXOTJaU2dpYjI0aUtUdDBZV2N1YzNSNWJHVXVaR2x6Y0d4aGVUMGlibTl1WlNJ"
    "N0NpQnBaaWh5WlhNbUpuSmxjeTVpYkc5amExOXBibVJsZUNseVl5NTBaWGgwUTI5dWRHVnVkRDBpVUdGcFpDQjJhV1YzSUhObFlX"
    "eGxaQ0JwYmlCaWJHOWpheUFpSzNKbGN5NWliRzlqYTE5cGJtUmxlRHNLSUhZdWNHeGhlU2dwZlFwbWRXNWpkR2x2YmlCb1pXeHNi"
    "eWdwZTJabGRHTm9LRUZRU1NzaVkyaGxZMnMvZG1sbGQyVnlQU0lyZG1sbGQyVnlLeUltZG1sa1pXODlJaXRsYm1OdlpHVlZVa2xE"
    "YjIxd2IyNWxiblFvVmtsRVJVOHBMSHRqWVdOb1pUb2libTh0YzNSdmNtVWlmU2tLSUM1MGFHVnVLR1oxYm1OMGFXOXVLSElwZTNK"
    "bGRIVnliaUJ5TG1wemIyNG9LWDBwTG5Sb1pXNG9ablZ1WTNScGIyNG9aQ2w3Q2lBZ2FXWW9aQzUxYm14dlkydGxaQ2w3Y0dGcFpE"
    "MTBjblZsTzNSaFp5NXpkSGxzWlM1a2FYTndiR0Y1UFNKdWIyNWxJbjBLSUNCcFppaDBlWEJsYjJZZ1pDNWlZV3hoYm1ObFgzQmxi"
    "bU5sUFQwOUltNTFiV0psY2lJcFltRnNMblJsZUhSRGIyNTBaVzUwUFNKWmIzVnlJR055WldScGREb2dJaXRrTG1KaGJHRnVZMlZm"
    "Y0dWdVkyVXJJbkFpT3dvZ2ZTa3VZMkYwWTJnb1puVnVZM1JwYjI0b0tYdDlLWDBLYUdWc2JHOG9LVHNLZGk1aFpHUkZkbVZ1ZEV4"
    "cGMzUmxibVZ5S0NKMGFXMWxkWEJrWVhSbElpeG1kVzVqZEdsdmJpZ3Bld29nYVdZb0lYWXVaSFZ5WVhScGIyNHBjbVYwZFhKdU8z"
    "Qm1Mbk4wZVd4bExuZHBaSFJvUFNoMkxtTjFjbkpsYm5SVWFXMWxMM1l1WkhWeVlYUnBiMjRxTVRBd0tTc2lKU0k3Q2lCcFppaHdZ"
    "V2xrS1hKbGRIVnlianNLSUdsbUtIWXVZM1Z5Y21WdWRGUnBiV1UrUFhZdVpIVnlZWFJwYjI0cVJsSkZSU2w3ZGk1d1lYVnpaU2dw"
    "TzNZdVkzVnljbVZ1ZEZScGJXVTlkaTVrZFhKaGRHbHZiaXBHVWtWRk8yeHJMbU5zWVhOelRHbHpkQzVoWkdRb0ltOXVJaWw5ZlNr"
    "N0NuWXVZV1JrUlhabGJuUk1hWE4wWlc1bGNpZ2ljMlZsYTJsdVp5SXNablZ1WTNScGIyNG9LWHRwWmlnaGNHRnBaQ1ltZGk1a2RY"
    "SmhkR2x2YmlZbWRpNWpkWEp5Wlc1MFZHbHRaVDUyTG1SMWNtRjBhVzl1S2taU1JVVXBlM1l1WTNWeWNtVnVkRlJwYldVOWRpNWtk"
    "WEpoZEdsdmJpcEdVa1ZGTzJ4ckxtTnNZWE56VEdsemRDNWhaR1FvSW05dUlpbDlmU2s3Q21kdkxtRmtaRVYyWlc1MFRHbHpkR1Z1"
    "WlhJb0ltTnNhV05ySWl4bWRXNWpkR2x2YmlncGUyZHZMbVJwYzJGaWJHVmtQWFJ5ZFdVN1oyOHVkR1Y0ZEVOdmJuUmxiblE5SWxW"
    "dWJHOWphMmx1WitLQXBpSTdDaUJtWlhSamFDaEJVRWtySW5WdWJHOWpheUlzZTIxbGRHaHZaRG9pVUU5VFZDSXNhR1ZoWkdWeWN6"
    "cDdJa052Ym5SbGJuUXRWSGx3WlNJNkltRndjR3hwWTJGMGFXOXVMMnB6YjI0aWZTd0tJQ0JpYjJSNU9rcFRUMDR1YzNSeWFXNW5h"
    "V1o1S0h0MmFXVjNaWEk2ZG1sbGQyVnlMSFpwWkdWdk9sWkpSRVZQTEdOeVpXRjBiM0k2UTFKRlFWUlBVaXh3Y21salpUcFFVa2xE"
    "UlgwcGZTa0tJQzUwYUdWdUtHWjFibU4wYVc5dUtISXBlM0psZEhWeWJpQnlMbXB6YjI0b0tYMHBMblJvWlc0b1puVnVZM1JwYjI0"
    "b1pDbDdDaUFnWjI4dVpHbHpZV0pzWldROVptRnNjMlU3WjI4dWRHVjRkRU52Ym5SbGJuUTlJbFZ1Ykc5amF5Qm1iM0lnSWl0UVVr"
    "bERSU3NpY0NJN0NpQWdhV1lvWkM1MWJteHZZMnRsWkNsN2RXNXNiMk5yVG05M0tHUXBPM0psZEhWeWJuMEtJQ0JzYTJndWRHVjRk"
    "RU52Ym5SbGJuUTlJbGx2ZFNCdVpXVmtJQ0lyVUZKSlEwVXJJbkFpT3dvZ0lHeHJjQzUwWlhoMFEyOXVkR1Z1ZEQxa0xtMWxjM05o"
    "WjJWOGZDSlViM0FnZFhBZ2VXOTFjaUJqY21Wa2FYUWdZVzVrSUdsMElIVnViRzlqYTNNZ2MzUnlZV2xuYUhRZ1lYZGhlUzRpT3dv"
    "Z0lHbG1LSFI1Y0dWdlppQmtMbUpoYkdGdVkyVmZjR1Z1WTJVOVBUMGliblZ0WW1WeUlpbGlZV3d1ZEdWNGRFTnZiblJsYm5ROUls"
    "bHZkWElnWTNKbFpHbDBPaUFpSzJRdVltRnNZVzVqWlY5d1pXNWpaU3NpY0NJN0NpQWdkRzl3WHk1emRIbHNaUzVrYVhOd2JHRjVQ"
    "U0pwYm14cGJtVXRZbXh2WTJzaU93b2dmU2t1WTJGMFkyZ29ablZ1WTNScGIyNG9LWHRuYnk1a2FYTmhZbXhsWkQxbVlXeHpaVHRu"
    "Ynk1MFpYaDBRMjl1ZEdWdWREMGlWVzVzYjJOcklHWnZjaUFpSzFCU1NVTkZLeUp3SWp0c2EzQXVkR1Y0ZEVOdmJuUmxiblE5SWtO"
    "dmRXeGtJRzV2ZENCeVpXRmphQ0J6WldKaWFTNXdjbTh1SUZSeWVTQmhaMkZwYmlCcGJpQmhJRzF2YldWdWRDNGlmU2w5S1RzS2RH"
    "OXdYeTVoWkdSRmRtVnVkRXhwYzNSbGJtVnlLQ0pqYkdsamF5SXNablZ1WTNScGIyNG9LWHR6WlhSVWFXMWxiM1YwS0dobGJHeHZM"
    "REUxTURBd0tYMHBPd3A5S1NncE93bzhMM05qY21sd2RENDhMMkp2WkhrK1BDOW9kRzFzUGdvPTwvc2NyaXB0Pgo8c2NyaXB0Pgoo"
    "ZnVuY3Rpb24oKXsKInVzZSBzdHJpY3QiOwovKiAtLS0tLS0tLS0tLS0tLS0tIGRlbW8gZmlsbSAtLS0tLS0tLS0tLS0tLS0tICov"
    "CnZhciBjdj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY3YiKSxnPWN2LmdldENvbnRleHQoIjJkIiksVz0xMjgwLEg9NzIwOwp2"
    "YXIgRFVSPTM4LEZSRUU9LjUsdD0wLHBsYXlpbmc9ZmFsc2UsbGFzdD0wLHVubG9ja2VkPWZhbHNlOwp2YXIgR09MRD0iI2M5YTg0"
    "YyIsT0s9IiM3ZmUzYjAiLEJMVUU9IiM4ZmQwZmYiLFBJTks9IiNkNTliZmYiOwpmdW5jdGlvbiBiZygpe3ZhciBkPWcuY3JlYXRl"
    "TGluZWFyR3JhZGllbnQoMCwwLFcsSCk7ZC5hZGRDb2xvclN0b3AoMCwiIzBiMTAyNiIpO2QuYWRkQ29sb3JTdG9wKDEsIiMwMzA1"
    "MGIiKTtnLmZpbGxTdHlsZT1kO2cuZmlsbFJlY3QoMCwwLFcsSCk7CiBnLmdsb2JhbEFscGhhPS4yMjtnLnN0cm9rZVN0eWxlPSIj"
    "MWQyYTUyIjtnLmxpbmVXaWR0aD0xO2Zvcih2YXIgeD0wO3g8Vzt4Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbyh4LDApO2cu"
    "bGluZVRvKHgsSCk7Zy5zdHJva2UoKX0KIGZvcih2YXIgeT0wO3k8SDt5Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygwLHkp"
    "O2cubGluZVRvKFcseSk7Zy5zdHJva2UoKX1nLmdsb2JhbEFscGhhPTF9CmZ1bmN0aW9uIHR4dChzLHksc2l6ZSxjb2wpe2cuZmls"
    "bFN0eWxlPWNvbHx8IiNmZmYiO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNjAwICIrc2l6ZSsicHggJ0lCTSBQbGV4IFNh"
    "bnMnLHN5c3RlbS11aSxzYW5zLXNlcmlmIjtnLmZpbGxUZXh0KHMsVy8yLHkpfQpmdW5jdGlvbiBzZXJpZihzLHksc2l6ZSxjb2wp"
    "e2cuZmlsbFN0eWxlPWNvbHx8IiNmZmYiO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNTAwICIrc2l6ZSsicHggTmV3c3Jl"
    "YWRlcixHZW9yZ2lhLHNlcmlmIjtnLmZpbGxUZXh0KHMsVy8yLHkpfQpmdW5jdGlvbiBtb25vKHMseSxzaXplLGNvbCl7Zy5maWxs"
    "U3R5bGU9Y29sfHxHT0xEO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNTAwICIrc2l6ZSsicHggdWktbW9ub3NwYWNlLE1l"
    "bmxvLG1vbm9zcGFjZSI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gYmxvY2soeCx5LHcsaCxjb2wsZ2xvdyl7Zy5zYXZl"
    "KCk7Zy5zaGFkb3dDb2xvcj1jb2w7Zy5zaGFkb3dCbHVyPWdsb3d8fDE4O2cuZmlsbFN0eWxlPSIjMGQxNDI0IjtnLnN0cm9rZVN0"
    "eWxlPWNvbDtnLmxpbmVXaWR0aD0zOwogZy5iZWdpblBhdGgoKTtnLnJvdW5kUmVjdCh4LHksdyxoLDEwKTtnLmZpbGwoKTtnLnN0"
    "cm9rZSgpO2cucmVzdG9yZSgpfQpmdW5jdGlvbiByb2JvdCh4LHkscyxjb2wpe2cuc2F2ZSgpO2cudHJhbnNsYXRlKHgseSk7Zy5z"
    "Y2FsZShzLHMpO2cuZmlsbFN0eWxlPSIjZDhkZGU2IjsKIGcuYmVnaW5QYXRoKCk7Zy5yb3VuZFJlY3QoLTI2LC03MCw1Miw0MCw4"
    "KTtnLmZpbGwoKTtnLmZpbGxTdHlsZT1jb2w7Zy5maWxsUmVjdCgtMTgsLTU4LDM2LDkpOwogZy5maWxsU3R5bGU9IiNjM2M5ZDQi"
    "O2cuYmVnaW5QYXRoKCk7Zy5yb3VuZFJlY3QoLTMyLC0yNiw2NCw1NCwxMCk7Zy5maWxsKCk7CiBnLmZpbGxTdHlsZT0iI2FlYjZj"
    "NCI7Zy5maWxsUmVjdCgtMjQsMzAsMTgsNDIpO2cuZmlsbFJlY3QoNiwzMCwxOCw0Mik7Zy5yZXN0b3JlKCl9CmZ1bmN0aW9uIHNj"
    "ZW5lKGkscCl7CiBpZihpPT09MCl7dmFyIGE9TWF0aC5taW4oMSxwKjMpO2cuZ2xvYmFsQWxwaGE9YTtzZXJpZigic2ViYmkucHJv"
    "IixILzItNDAsOTYpO21vbm8oIlBST09GIEZPUiBUSEUgTUFDSElORSBBR0UiLEgvMiszMCwyNixHT0xEKTsKICBnLnN0cm9rZVN0"
    "eWxlPUdPTEQ7Zy5nbG9iYWxBbHBoYT1hKi42O2cubGluZVdpZHRoPTI7Zy5iZWdpblBhdGgoKTtnLmFyYyhXLzIsSC8yLTEwLDE4"
    "MCtwKjQwLDAsNi4yODMpO2cuc3Ryb2tlKCk7Zy5nbG9iYWxBbHBoYT0xfQogZWxzZSBpZihpPT09MSl7dHh0KCJZb3VyIEFJIGp1"
    "c3QgZGlkIHNvbWV0aGluZy4iLDEyMCw1NCk7bW9ubygiV0hPIFNBSUQgSVQgQ09VTEQ/IiwxNzYsMjQsUElOSyk7CiAgcm9ib3Qo"
    "Vy8yLTI2MCxILzIrMTQwLDEuNixPSyk7CiAgZy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdpZHRoPTQ7Zy5zZXRMaW5lRGFzaChb"
    "MTIsMTBdKTtnLmJlZ2luUGF0aCgpO2cubW92ZVRvKFcvMi0yMDAsSC8yKzQwKTtnLmxpbmVUbyhXLzIrMTYwK3AqODAsSC8yKzQw"
    "KTtnLnN0cm9rZSgpO2cuc2V0TGluZURhc2goW10pOwogIGJsb2NrKFcvMisyMDAsSC8yLTQwLDIyMCwxNjAsR09MRCk7dHh0KCLC"
    "ozQsMDAwIixILzIrNTAsNDQsR09MRCk7bW9ubygiUEFZTUVOVCIsSC8yKzkwLDIwLCIjOGE5M2FkIil9CiBlbHNlIGlmKGk9PT0y"
    "KXt0eHQoInNlYmJpLnBybyBjaGVja3MgYXQgdGhlIG1vbWVudCBpdCBoYXBwZW5zLiIsMTEwLDQ2KTsKICB2YXIgbj1NYXRoLmZs"
    "b29yKHAqNCkrMSxMPVsiSHVtYW4gYXV0aG9yaXR5PyIsIlN0aWxsIHZhbGlkIG5vdz8iLCJSaWdodCBhbW91bnQ/IiwiVXNlZCBi"
    "ZWZvcmU/Il07CiAgZm9yKHZhciBrPTA7azw0O2srKyl7dmFyIG9uPWs8bjtnLmdsb2JhbEFscGhhPW9uPzE6LjI1O2Jsb2NrKDE4"
    "MCtrKjI0MCwzMDAsMjAwLDEyMCxvbj9PSzoiIzMzNCIsb24/MjI6Nik7CiAgIGcuZmlsbFN0eWxlPW9uP09LOiIjNjY3IjtnLnRl"
    "eHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjYwMCAyMnB4ICdJQk0gUGxleCBTYW5zJyxzYW5zLXNlcmlmIjtnLmZpbGxUZXh0KExb"
    "a10sMjgwK2sqMjQwLDM1Mik7CiAgIGcuZm9udD0iNjAwIDM0cHggdWktbW9ub3NwYWNlLG1vbm9zcGFjZSI7Zy5maWxsVGV4dChv"
    "bj8i4pyTIjoiwrciLDI4MCtrKjI0MCwzOTgpO2cuZ2xvYmFsQWxwaGE9MX0KICBtb25vKCJNSUxMSVNFQ09ORFMgwrcgTk8gU0VD"
    "T05EIEFJIE1PREVMIiw1MjAsMjQsR09MRCl9CiBlbHNlIGlmKGk9PT0zKXt0eHQoIlRoZW4gaXQgaXMgc2VhbGVkLiBGb3JldmVy"
    "LiIsMTEwLDUwKTsKICBmb3IodmFyIGI9MDtiPDY7YisrKXtpZihwKjY8Yiljb250aW51ZTtibG9jaygxMjArYioxODAsMjgwLDE1"
    "MCwxNDAsR09MRCwxNik7bW9ubygiIyIrKDI1MTArYiksMzUwLDIwLEdPTEQpOwogICBnLmZpbGxTdHlsZT1PSztnLnRleHRBbGln"
    "bj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAxNXB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2UiO2cuZmlsbFRleHQoImE0ZjnigKYiKyhi"
    "KjcrMTEpLDEyMCtiKjE4MCs3NSwzMzApOwogICBpZihiKXtnLnN0cm9rZVN0eWxlPUdPTEQ7Zy5saW5lV2lkdGg9MztnLmJlZ2lu"
    "UGF0aCgpO2cubW92ZVRvKDEyMCtiKjE4MC0zMCwzNTApO2cubGluZVRvKDEyMCtiKjE4MCwzNTApO2cuc3Ryb2tlKCl9fQogIG1v"
    "bm8oIkNIQU5HRSBPTkUgQU5EIEVWRVJZIE9ORSBBRlRFUiBJVCBCUkVBS1MiLDUyMCwyNCwiIzhhOTNhZCIpfQogZWxzZSBpZihp"
    "PT09NCl7dHh0KCJUaW1lc3RhbXBlZCBpbiBCaXRjb2luLiIsMTEwLDUwKTsKICBnLnNhdmUoKTtnLnRyYW5zbGF0ZShXLzIsMzYw"
    "KTtnLnJvdGF0ZShwKjEuNik7Zy5zdHJva2VTdHlsZT0iI2Y3OTMxYSI7Zy5saW5lV2lkdGg9NjtnLmJlZ2luUGF0aCgpO2cuYXJj"
    "KDAsMCwxMTAsMCw2LjI4Myk7Zy5zdHJva2UoKTtnLnJlc3RvcmUoKTsKICBnLmZpbGxTdHlsZT0iI2Y3OTMxYSI7Zy50ZXh0QWxp"
    "Z249ImNlbnRlciI7Zy5mb250PSI2MDAgOTBweCAnSUJNIFBsZXggU2Fucycsc2Fucy1zZXJpZiI7Zy5maWxsVGV4dCgi4oK/IixX"
    "LzIsMzkwKTsKICBtb25vKCJBIENMT0NLIE5PQk9EWSBJTlZPTFZFRCBDT05UUk9MUyIsNTIwLDI0LCIjZjc5MzFhIil9CiBlbHNl"
    "IGlmKGk9PT01KXt0eHQoIkhlbGQgYnkgcGVvcGxlIHlvdSBkbyBub3QgY29udHJvbC4iLDExMCw0OCk7CiAgZm9yKHZhciB3PTA7"
    "dzw1O3crKyl7dmFyIGFuZz0tTWF0aC5QSS8yKyh3LTIpKi41LHg9Vy8yK01hdGguY29zKGFuZykqMjYwLHk9NDIwK01hdGguc2lu"
    "KGFuZykqMTIwOwogICBnLnN0cm9rZVN0eWxlPUJMVUU7Zy5nbG9iYWxBbHBoYT0uNTtnLmxpbmVXaWR0aD0yO2cuYmVnaW5QYXRo"
    "KCk7Zy5tb3ZlVG8oVy8yLDMwMCk7Zy5saW5lVG8oeCx5KTtnLnN0cm9rZSgpO2cuZ2xvYmFsQWxwaGE9MTsKICAgZy5maWxsU3R5"
    "bGU9QkxVRTtnLmJlZ2luUGF0aCgpO2cuYXJjKHgseSwyMiwwLDYuMjgzKTtnLmZpbGwoKX0KICBibG9jayhXLzItOTAsMjQwLDE4"
    "MCwxMTAsR09MRCk7bW9ubygiWU9VUiBDSEFJTiIsMzA1LDIyLEdPTEQpO21vbm8oIklOREVQRU5ERU5UIFdJVE5FU1NFUyIsNjAw"
    "LDI0LEJMVUUpfQogZWxzZXt0eHQoIkV2ZXJ5IGRlY2lzaW9uLiBQcm92YWJsZS4iLEgvMi02MCw2MCk7bW9ubygiU0VCQkkuUFJP"
    "IixILzIrMjAsNDAsR09MRCk7bW9ubygiRlJFRSBGT1IgOTAgREFZUyDCtyA1MHAgUEVSIERFVklDRSIsSC8yKzgwLDIyLCIjOGE5"
    "M2FkIil9fQpmdW5jdGlvbiBkcmF3KCl7YmcoKTt2YXIgcGVyPURVUi83LGk9TWF0aC5taW4oNixNYXRoLmZsb29yKHQvcGVyKSk7"
    "c2NlbmUoaSwodC1pKnBlcikvcGVyKTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwZiIpLnN0eWxlLndpZHRoPSh0L0RVUiox"
    "MDApKyIlIjsKIHZhciBzPU1hdGguZmxvb3IodCU2MCk7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInB0IikudGV4dENvbnRlbnQ9"
    "IjA6IisoczwxMD8iMCI6IiIpK3MrIiAvIDA6MzgifQpmdW5jdGlvbiBsb29wKG5vdyl7aWYoIXBsYXlpbmcpcmV0dXJuO3ZhciBk"
    "dD0obm93LWxhc3QpLzEwMDA7bGFzdD1ub3c7dCs9ZHQ7CiBpZighdW5sb2NrZWQmJnQ+PURVUipGUkVFKXt0PURVUipGUkVFO3Bs"
    "YXlpbmc9ZmFsc2U7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInBiIikudGV4dENvbnRlbnQ9IuKWtiI7ZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoImxvY2siKS5jbGFzc0xpc3QuYWRkKCJvbiIpO2RyYXcoKTtyZXR1cm59CiBpZih0Pj1EVVIpe3Q9RFVSO3BsYXlp"
    "bmc9ZmFsc2U7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInBiIikudGV4dENvbnRlbnQ9IuKGuyJ9CiBkcmF3KCk7cmVxdWVzdEFu"
    "aW1hdGlvbkZyYW1lKGxvb3ApfQpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGIiKS5vbmNsaWNrPWZ1bmN0aW9uKCl7aWYodD49"
    "RFVSKXQ9MDtwbGF5aW5nPSFwbGF5aW5nO3RoaXMudGV4dENvbnRlbnQ9cGxheWluZz8i4p2a4p2aIjoi4pa2IjtsYXN0PXBlcmZv"
    "cm1hbmNlLm5vdygpO2lmKHBsYXlpbmcpcmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3ApfTsKZG9jdW1lbnQuZ2V0RWxlbWVudEJ5"
    "SWQoInBheUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXt1bmxvY2tlZD10cnVlOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJj"
    "cHQiKS50ZXh0Q29udGVudD0i4pyTIFVubG9ja2VkIMK3IHBhaWQgdmlldyBzZWFsZWQgaW4gYmxvY2sgIisoMjUwMCtNYXRoLmZs"
    "b29yKE1hdGgucmFuZG9tKCkqNDAwKSkrIiDCtyBjcmVhdG9yIGVhcm5zIDdwIjsKIHRoaXMudGV4dENvbnRlbnQ9IlVubG9ja2Vk"
    "IOKckyI7dmFyIHNlbGY9dGhpczsKIHNldFRpbWVvdXQoZnVuY3Rpb24oKXtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibG9jayIp"
    "LmNsYXNzTGlzdC5yZW1vdmUoIm9uIik7cGxheWluZz10cnVlO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwYiIpLnRleHRDb250"
    "ZW50PSLinZrinZoiO2xhc3Q9cGVyZm9ybWFuY2Uubm93KCk7cmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3ApfSwxMTAwKX07CmRy"
    "YXcoKTsKCi8qIC0tLS0tLS0tLS0tLS0tLS0gbG9jayBhIHZpZGVvIC0tLS0tLS0tLS0tLS0tLS0gKi8KdmFyIFRQTD1hdG9iKGRv"
    "Y3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0cGwiKS50ZXh0Q29udGVudC50cmltKCkpOwp2YXIgRj1kb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgidUZyZWUiKSxGTD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidUZyZWVMYWIiKTsKRi5hZGRFdmVudExpc3RlbmVyKCJp"
    "bnB1dCIsZnVuY3Rpb24oKXtGTC50ZXh0Q29udGVudD0iRmlyc3QgIitGLnZhbHVlKyIlIHBsYXlzIGZyZWUifSk7CmZ1bmN0aW9u"
    "IGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2UoL1smPD4iJ10vZyxmdW5jdGlvbihjKXtyZXR1cm57IiYiOiImYW1wOyIs"
    "IjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7IiwiJyI6IiYjMzk7In1bY119KX0KZnVuY3Rpb24gc2hhKGJ1Zil7cmV0"
    "dXJuIGNyeXB0by5zdWJ0bGUuZGlnZXN0KCJTSEEtMjU2IixidWYpLnRoZW4oZnVuY3Rpb24oaCl7CiByZXR1cm4gQXJyYXkucHJv"
    "dG90eXBlLm1hcC5jYWxsKG5ldyBVaW50OEFycmF5KGgpLGZ1bmN0aW9uKGIpe3JldHVybiBiLnRvU3RyaW5nKDE2KS5wYWRTdGFy"
    "dCgyLCIwIil9KS5qb2luKCIiKX0pfQpmdW5jdGlvbiBidWlsZChvKXsKIHJldHVybiBUUEwuc3BsaXQoIl9fVElUTEVfXyIpLmpv"
    "aW4oZXNjKG8udGl0bGUpKQogICAuc3BsaXQoIl9fUFJJQ0VfXyIpLmpvaW4oU3RyaW5nKG8ucHJpY2UpKQogICAuc3BsaXQoIl9f"
    "RlJFRV9fIikuam9pbihTdHJpbmcoby5mcmVlKSkKICAgLnNwbGl0KCJfX0NSRUFUT1JfXyIpLmpvaW4oZXNjKG8uY3JlYXRvcikp"
    "CiAgIC5zcGxpdCgiX19WSURFT0lEX18iKS5qb2luKG8uaGFzaC5zbGljZSgwLDI0KSkKICAgLnNwbGl0KCJfX1NIT1JUSEFTSF9f"
    "Iikuam9pbihvLmhhc2guc2xpY2UoMCwxNikpCiAgIC5zcGxpdCgiX19TUkNfXyIpLmpvaW4oby5zcmMpOwp9CnZhciBvdXQ9ZG9j"
    "dW1lbnQuZ2V0RWxlbWVudEJ5SWQoInVPdXQiKSxwdz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidVByb2dXcmFwIikscHI9ZG9j"
    "dW1lbnQuZ2V0RWxlbWVudEJ5SWQoInVQcm9nIiksYnRuPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ1R28iKTsKZnVuY3Rpb24g"
    "c3RlcChwY3QsbXNnKXtwdy5zdHlsZS5kaXNwbGF5PSJibG9jayI7cHIuc3R5bGUud2lkdGg9cGN0KyIlIjtvdXQuY2xhc3NMaXN0"
    "LmFkZCgib24iKTtvdXQuaW5uZXJIVE1MPW1zZ30KYnRuLm9uY2xpY2s9ZnVuY3Rpb24oKXsKIHZhciBmPWRvY3VtZW50LmdldEVs"
    "ZW1lbnRCeUlkKCJ1RmlsZSIpLmZpbGVzWzBdOwogaWYoIWYpe291dC5jbGFzc0xpc3QuYWRkKCJvbiIpO291dC5pbm5lckhUTUw9"
    "IlBpY2sgYSB2aWRlbyBmaXJzdC4iO3JldHVybn0KIHZhciB0aXRsZT0oZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInVUaXRsZSIp"
    "LnZhbHVlfHxmLm5hbWUucmVwbGFjZSgvXC5bXi5dKyQvLCIiKSkudHJpbSgpLnNsaWNlKDAsODApOwogdmFyIHByaWNlPU1hdGgu"
    "bWF4KDEsTWF0aC5yb3VuZChwYXJzZUZsb2F0KGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ1UHJpY2UiKS52YWx1ZSl8fDEwKSk7"
    "CiB2YXIgZnJlZT0ocGFyc2VJbnQoRi52YWx1ZSwxMCl8fDUwKS8xMDA7CiB2YXIgd2hvPShkb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZCgidVdobyIpLnZhbHVlfHwiQW5vbnltb3VzIikucmVwbGFjZSgvW15BLVphLXowLTkgLl8tXS9nLCIiKS50cmltKCkuc2xpY2Uo"
    "MCw0MCl8fCJBbm9ueW1vdXMiOwogYnRuLmRpc2FibGVkPXRydWU7c3RlcCgxMCwiUmVhZGluZyB5b3VyIHZpZGVvICgiKyhmLnNp"
    "emUvMTA0ODU3NikudG9GaXhlZCgxKSsiIE1CKeKApiBub3RoaW5nIGlzIGJlaW5nIHVwbG9hZGVkLiIpOwogZi5hcnJheUJ1ZmZl"
    "cigpLnRoZW4oZnVuY3Rpb24oYnVmKXtzdGVwKDM1LCJGaW5nZXJwcmludGluZyB5b3VyIGV4YWN0IGN1dOKApiIpO3JldHVybiBz"
    "aGEoYnVmKX0pCiAudGhlbihmdW5jdGlvbihoKXtzdGVwKDU1LCJXcmFwcGluZyBpdCBpbiBpdHMgb3duIHBsYXllcuKApiIpOwog"
    "IHJldHVybiBuZXcgUHJvbWlzZShmdW5jdGlvbihyZXMscmVqKXt2YXIgcj1uZXcgRmlsZVJlYWRlcigpO3Iub25sb2FkPWZ1bmN0"
    "aW9uKCl7cmVzKFtoLFN0cmluZyhyLnJlc3VsdCldKX07ci5vbmVycm9yPXJlajtyLnJlYWRBc0RhdGFVUkwoZil9KX0pCiAudGhl"
    "bihmdW5jdGlvbihwYWlyKXsKICB2YXIgaD1wYWlyWzBdLHNyYz1wYWlyWzFdOwogIHN0ZXAoODUsIkJ1aWxkaW5nIHlvdXIgZmls"
    "ZeKApiIpOwogIHZhciBodG1sPWJ1aWxkKHt0aXRsZTp0aXRsZSxwcmljZTpwcmljZSxmcmVlOmZyZWUsY3JlYXRvcjp3aG8saGFz"
    "aDpoLHNyYzpzcmN9KTsKICB2YXIgdXJsPVVSTC5jcmVhdGVPYmplY3RVUkwobmV3IEJsb2IoW2h0bWxdLHt0eXBlOiJ0ZXh0L2h0"
    "bWwifSkpOwogIHZhciBuYW1lPSh0aXRsZS5yZXBsYWNlKC9bXkEtWmEtejAtOSBfLV0vZywiIikudHJpbSgpLnJlcGxhY2UoL1xz"
    "Ky9nLCItIikudG9Mb3dlckNhc2UoKXx8InZpZGVvIikrIi1sb2NrZWQuaHRtbCI7CiAgc3RlcCgxMDAsJzxzcGFuIGNsYXNzPSJi"
    "aWciPkxvY2tlZCDinJM8L3NwYW4+JysKICAgIkZpbmdlcnByaW50ICIraC5zbGljZSgwLDMyKSsi4oCmPGJyPkZyZWUgcHJldmll"
    "dzogZmlyc3QgIitNYXRoLnJvdW5kKGZyZWUqMTAwKSsiJSDCtyBVbmxvY2s6ICIrcHJpY2UrInAgwrcgeW91IGtlZXAgIisocHJp"
    "Y2UqMC43KS50b0ZpeGVkKDEpKyJwIGEgdmlldyIrCiAgICc8YnI+PGEgY2xhc3M9ImJ0biBnb2xkIiBzdHlsZT0ibWFyZ2luLXRv"
    "cDoxNHB4IiBocmVmPSInK3VybCsnIiBkb3dubG9hZD0iJytuYW1lKyciPuKshyBEb3dubG9hZCB5b3VyIGxvY2tlZCB2aWRlbzwv"
    "YT4nKwogICAnPGRpdiBjbGFzcz0ibm90ZSI+WW91ciB2aWRlbyBuZXZlciBsZWZ0IHRoaXMgZGV2aWNlLiBPcGVuIHRoZSBmaWxl"
    "LCBzaGFyZSBpdCwgb3Igc2VuZCB0aGUgbGluayB0byB0aGUgMTBwIFdpbmcgYmVsb3cuPC9kaXY+Jyk7CiAgYnRuLmRpc2FibGVk"
    "PWZhbHNlOwogfSkuY2F0Y2goZnVuY3Rpb24oZSl7c3RlcCgwLCJDb3VsZCBub3QgYnVpbGQgaXQ6ICIrU3RyaW5nKGUpLnNsaWNl"
    "KDAsMTQwKSk7YnRuLmRpc2FibGVkPWZhbHNlfSk7Cn07CgovKiAtLS0tLS0tLS0tLS0tLS0tIHNlbmQgdG8gdGhlIDEwcCBXaW5n"
    "IC0tLS0tLS0tLS0tLS0tLS0gKi8KZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1HbyIpLm9uY2xpY2s9ZnVuY3Rpb24oKXsKIHZh"
    "ciBvPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtT3V0IiksdXJsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtVXJsIikudmFs"
    "dWUudHJpbSgpOwogby5jbGFzc0xpc3QuYWRkKCJvbiIpOwogaWYoIS9eaHR0cHM6XC9cLy8udGVzdCh1cmwpKXtvLmlubmVySFRN"
    "TD0iR2l2ZSB0aGUgaHR0cHM6Ly8gbGluayB0byB5b3VyIGxvY2tlZCB2aWRlby4iO3JldHVybn0KIG8uaW5uZXJIVE1MPSJTZW5k"
    "aW5n4oCmIjsKIGZldGNoKCIveC9tYXJxdWVlL3N1Ym1pdCIse21ldGhvZDoiUE9TVCIsaGVhZGVyczp7IkNvbnRlbnQtVHlwZSI6"
    "ImFwcGxpY2F0aW9uL2pzb24ifSwKICBib2R5OkpTT04uc3RyaW5naWZ5KHt1cmw6dXJsLHRpdGxlOmRvY3VtZW50LmdldEVsZW1l"
    "bnRCeUlkKCJtVGl0bGUiKS52YWx1ZSwKICAgY3JlYXRvcjpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibVdobyIpLnZhbHVlLHBy"
    "aWNlOmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtUHJpY2UiKS52YWx1ZX0pfSkKIC50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiBy"
    "Lmpzb24oKX0pLnRoZW4oZnVuY3Rpb24oZCl7CiAgby5pbm5lckhUTUwgPSBkLnJlY2VpdmVkCiAgID8gJzxzcGFuIGNsYXNzPSJi"
    "aWciPlNlbnQg4pyTPC9zcGFuPlNlYWxlZCBpbiBibG9jayAnK2QuYmxvY2tfaW5kZXgrJy4gSXQgZ29lcyB1cCBvbmNlIGl0IGhh"
    "cyBiZWVuIGxvb2tlZCBhdC4nCiAgIDogKGQubWVzc2FnZXx8IkNvdWxkIG5vdCBzZW5kIGl0LiIpOwogfSkuY2F0Y2goZnVuY3Rp"
    "b24oKXtvLmlubmVySFRNTD0iQ291bGQgbm90IHJlYWNoIHRoZSBjaW5lbWEuIn0pOwp9OwoKLyogLS0tLS0tLS0tLS0tLS0tLSBj"
    "YWxjdWxhdG9yIC0tLS0tLS0tLS0tLS0tLS0gKi8KZnVuY3Rpb24gY2FsYygpe3ZhciBwPXBhcnNlRmxvYXQoZG9jdW1lbnQuZ2V0"
    "RWxlbWVudEJ5SWQoImNQcmljZSIpLnZhbHVlKXx8MCx2PXBhcnNlSW50KGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjVmlkcyIp"
    "LnZhbHVlKXx8MCxuPXBhcnNlSW50KGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjVmlld3MiKS52YWx1ZSl8fDA7CiB2YXIga2Vl"
    "cD1wKi43LGdyb3NzPWtlZXAqdipuLzEwMCxmZWU9LjUqdixuZXQ9Z3Jvc3MtZmVlOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "ImNPdXQiKS50ZXh0Q29udGVudD0iwqMiKyhuZXQ+MD9uZXQudG9GaXhlZCgyKToiMC4wMCIpOwogZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoImNEZXRhaWwiKS50ZXh0Q29udGVudD0odipuKSsiIHBhaWQgdmlld3Mgw5cgIitrZWVwLnRvRml4ZWQoMSkrInAgPSDC"
    "oyIrZ3Jvc3MudG9GaXhlZCgyKSsiICDCtyAgbW9udGhseSBsb2NrIGZlZSDCoyIrZmVlLnRvRml4ZWQoMil9ClsiY1ByaWNlIiwi"
    "Y1ZpZHMiLCJjVmlld3MiXS5mb3JFYWNoKGZ1bmN0aW9uKGlkKXtkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCkuYWRkRXZlbnRM"
    "aXN0ZW5lcigiaW5wdXQiLGNhbGMpfSk7Y2FsYygpOwp9KSgpOwo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    '/create': (_d(_HTML_B64), "text/html; charset=utf-8"),
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
    if getattr(cls, "_studio_patched", False):
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
    cls._studio_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "studio", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
