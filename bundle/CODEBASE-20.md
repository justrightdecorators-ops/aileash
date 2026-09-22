# Codebase — part 20 of 40

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

328 lines, 27911 bytes

```python
"""
modules/studio.py  v1.0.0
Monop Studio at /create: the content creator centre. A demo video plays in a
canvas player, the lock drops at the halfway mark, and one tap unlocks it with
a sealed paid-view receipt. Plus the pricing, the earnings calculator and the
creator control centre. The unlock is a demonstration and takes no payment.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/studio/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk1vbm9wIFN0dWRpbyDigJQgbW9ub3BvbGlzZSB5b3VyIGNvbnRlbnQ8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlv"
    "biIgY29udGVudD0iUHV0IHlvdXIgdmlkZW8gYmVoaW5kIGEgdGFwLXRvLXBheSBsb2NrLiBWaWV3ZXJzIHBheSBwZW5uaWVzIHRv"
    "IHdhdGNoIHRoZSByZXN0LCB5b3Uga2VlcCBtb3N0IG9mIGl0LCBhbmQgZXZlcnkgcGFpZCB2aWV3IGlzIHNlYWxlZCBvbiBhIHB1"
    "YmxpYyBjaGFpbi4iPgo8bGluayBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PUlCTStQbGV4"
    "K01vbm86d2dodEA0MDA7NTAwOzYwMCZmYW1pbHk9SUJNK1BsZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1OZXdzcmVh"
    "ZGVyOm9wc3osd2dodEA2Li43Miw1MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8c3R5bGU+Cjpyb290ey0taW5r"
    "OiMwNTA3MGY7LS1pbmsyOiMwZDE0MjQ7LS1nb2xkOiNjOWE4NGM7LS1vazojN2ZlM2IwOy0tYmx1ZTojOGZkMGZmOy0tcGluazoj"
    "ZDU5YmZmOy0tbXV0ZTojOGE5M2FkOy0tbGluZTpyZ2JhKDIwMSwxNjgsNzYsLjIyKTstLW1vbm86J0lCTSBQbGV4IE1vbm8nLHVp"
    "LW1vbm9zcGFjZSxtb25vc3BhY2U7LS1zYW5zOidJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidO"
    "ZXdzcmVhZGVyJyxHZW9yZ2lhLHNlcmlmfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdlYmtp"
    "dC10YXAtaGlnaGxpZ2h0LWNvbG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGVsbGlwc2Ug"
    "YXQgNTAlIDAlLCMxYTEwMzggMCUsIzA1MDcwZiA2MiUpO2NvbG9yOiNlOGVkZjc7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7bGlu"
    "ZS1oZWlnaHQ6MS42O21pbi1oZWlnaHQ6MTAwdmh9Ci53cmFwe21heC13aWR0aDo5MDBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6"
    "MCAyMHB4IDcwcHh9Ci50b3B7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNl"
    "bnRlcjtwYWRkaW5nOmNhbGMoMTRweCArIGVudihzYWZlLWFyZWEtaW5zZXQtdG9wKSkgMCAwfQouYnJhbmR7Zm9udC1mYW1pbHk6"
    "dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEzcHh9LmJyYW5kIGJ7Y29sb3I6dmFyKC0tcGluayk7Zm9udC13ZWlnaHQ6NTAwfQoudG9w"
    "IGF7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZSk7dGV4dC1kZWNvcmF0aW9u"
    "Om5vbmU7bWFyZ2luLWxlZnQ6MTRweH0KLmhlcm97dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo0MHB4IDAgNHB4fQoua2lja3tm"
    "b250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTEuNXB4O2xldHRlci1zcGFjaW5nOi4yZW07Y29sb3I6dmFyKC0tcGlu"
    "ayl9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsN3Z3LDU4"
    "cHgpO2xpbmUtaGVpZ2h0OjEuMDQ7bWFyZ2luOjEycHggYXV0byAxMnB4O21heC13aWR0aDoxNWNoO2JhY2tncm91bmQ6bGluZWFy"
    "LWdyYWRpZW50KDkwZGVnLCNmZmYsI2Q1OWJmZiA0MCUsI2M5YTg0YyA3MCUsIzdmZTNiMCk7LXdlYmtpdC1iYWNrZ3JvdW5kLWNs"
    "aXA6dGV4dDtiYWNrZ3JvdW5kLWNsaXA6dGV4dDtjb2xvcjp0cmFuc3BhcmVudH0KLmhlcm8gcHtjb2xvcjojYjZjMGQ2O21heC13"
    "aWR0aDo1NmNoO21hcmdpbjowIGF1dG87Zm9udC1zaXplOjE2LjVweH0KLyogcGxheWVyICovCi5wbGF5ZXJ7cG9zaXRpb246cmVs"
    "YXRpdmU7bWFyZ2luOjI2cHggYXV0byAwO21heC13aWR0aDo3MjBweDthc3BlY3QtcmF0aW86MTYvOTtib3JkZXItcmFkaXVzOjE2"
    "cHg7b3ZlcmZsb3c6aGlkZGVuO2JhY2tncm91bmQ6IzAzMDUwYjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JveC1zaGFk"
    "b3c6MCAzMHB4IDcwcHggcmdiYSgwLDAsMCwuNiksMCAwIDUwcHggcmdiYSgyMTMsMTU1LDI1NSwuMTUpfQoucGxheWVyIGNhbnZh"
    "c3t3aWR0aDoxMDAlO2hlaWdodDoxMDAlO2Rpc3BsYXk6YmxvY2t9Ci5wYmFye3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MDtyaWdo"
    "dDowO2JvdHRvbTowO2hlaWdodDo1cHg7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4xMil9Ci5wYmFyIGl7ZGlzcGxheTpi"
    "bG9jaztoZWlnaHQ6MTAwJTt3aWR0aDowO2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXBpbmspLHZhcigt"
    "LWdvbGQpLHZhcigtLW9rKSl9Ci5wYnRue3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MTJweDtib3R0b206MTRweDtiYWNrZ3JvdW5k"
    "OnJnYmEoNSw3LDE1LC43KTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KTtjb2xvcjojZmZmO2JvcmRlci1y"
    "YWRpdXM6OTk5cHg7d2lkdGg6MzhweDtoZWlnaHQ6MzhweDtmb250LXNpemU6MTRweDtjdXJzb3I6cG9pbnRlcn0KLnB0aW1le3Bv"
    "c2l0aW9uOmFic29sdXRlO3JpZ2h0OjE0cHg7Ym90dG9tOjIwcHg7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtjb2xvcjojY2Zk"
    "NmU2O3RleHQtc2hhZG93OjAgMXB4IDRweCAjMDAwfQoubG9ja3twb3NpdGlvbjphYnNvbHV0ZTtpbnNldDowO2Rpc3BsYXk6bm9u"
    "ZTtmbGV4LWRpcmVjdGlvbjpjb2x1bW47YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7Z2FwOjEwcHg7"
    "dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyNHB4OwogYmFja2dyb3VuZDpyZ2JhKDUsNywxNSwuODIpO2JhY2tkcm9wLWZpbHRl"
    "cjpibHVyKDdweCl9Ci5sb2NrLm9ue2Rpc3BsYXk6ZmxleH0KLmxvY2sgLmlje2ZvbnQtc2l6ZTozMHB4fQoubG9jayBoM3tmb250"
    "LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyMHB4LDR2dywzMHB4KX0KLmxvY2sg"
    "cHtjb2xvcjojYjZjMGQ2O2ZvbnQtc2l6ZToxMy41cHg7bWF4LXdpZHRoOjQwY2h9Ci5wYXl7ZGlzcGxheTppbmxpbmUtZmxleDth"
    "bGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweDtiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOiMwNTA3MGY7Ym9yZGVyOjA7Ym9y"
    "ZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTNweCAyMnB4O2ZvbnQ6NjAwIDE0cHggdmFyKC0tbW9ubyk7Y3Vyc29yOnBvaW50ZXI7"
    "Ym94LXNoYWRvdzowIDAgMjhweCByZ2JhKDIwMSwxNjgsNzYsLjQpfQoubWluaXtmb250OjUwMCAxMC41cHggdmFyKC0tbW9ubyk7"
    "Y29sb3I6dmFyKC0tbXV0ZSl9Ci5yZWNlaXB0e2ZvbnQ6NTAwIDExLjVweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1vayl9Ci8q"
    "IHNlY3Rpb25zICovCnNlY3Rpb257cGFkZGluZzo0NHB4IDAgMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1"
    "LC4wNyk7bWFyZ2luLXRvcDo0NHB4fQpoMntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6"
    "ZTpjbGFtcCgyNXB4LDQuNXZ3LDM2cHgpO21hcmdpbi1ib3R0b206MTBweH0KLmxlYWR7Y29sb3I6I2I2YzBkNjttYXgtd2lkdGg6"
    "NjJjaDttYXJnaW4tYm90dG9tOjE4cHh9Ci5ncmlke2Rpc3BsYXk6Z3JpZDtnYXA6MTJweH1AbWVkaWEobWluLXdpZHRoOjcyMHB4"
    "KXsuZ3JpZC50d297Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnJ9LmdyaWQudGhyZWV7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5z"
    "OnJlcGVhdCgzLDFmcil9fQouY2FyZHtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjgpO2JvcmRlcjoxcHggc29saWQgdmFyKC0t"
    "bGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MThweH0KLmNhcmQgaDN7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2Zv"
    "bnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MjBweDttYXJnaW4tYm90dG9tOjZweH0uY2FyZCBwe2ZvbnQtc2l6ZToxNHB4O2NvbG9y"
    "OiNiNmMwZDZ9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtsZXR0ZXItc3BhY2luZzouMWVt"
    "O2NvbG9yOnZhcigtLW11dGUpO21hcmdpbjoxMnB4IDAgNHB4fQppbnB1dCxzZWxlY3R7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOiMw"
    "MzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtjb2xvcjojZmZmO3BhZGRpbmc6MTFw"
    "eDtmb250OjE0cHggdmFyKC0tbW9ubyl9Ci5jYWxjIGJ7Y29sb3I6dmFyKC0tb2spfQoub3V0e21hcmdpbi10b3A6MTRweDtiYWNr"
    "Z3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxNHB4"
    "O2ZvbnQ6MTNweCB2YXIoLS1tb25vKTtjb2xvcjojY2ZlNmQ5fQoub3V0IC5iaWd7Zm9udC1zaXplOjI2cHg7Y29sb3I6dmFyKC0t"
    "b2spO2Rpc3BsYXk6YmxvY2s7bWFyZ2luLWJvdHRvbTo0cHh9CnByZXtiYWNrZ3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xp"
    "ZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjEycHg7Zm9udDoxMnB4IHZhcigtLW1vbm8pO2NvbG9yOiNj"
    "ZmU2ZDk7b3ZlcmZsb3cteDphdXRvO3doaXRlLXNwYWNlOnByZS13cmFwO3dvcmQtYnJlYWs6YnJlYWstYWxsO21hcmdpbi10b3A6"
    "OHB4fQouYnRue2Rpc3BsYXk6aW5saW5lLWZsZXg7Z2FwOjhweDttYXJnaW4tdG9wOjEycHg7cGFkZGluZzoxMnB4IDE4cHg7Ym9y"
    "ZGVyLXJhZGl1czoxMHB4O2ZvbnQ6NjAwIDEzcHggdmFyKC0tbW9ubyk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7YmFja2dyb3VuZDp2"
    "YXIoLS1waW5rKTtjb2xvcjojMDUwNzBmO2JvcmRlcjowO2N1cnNvcjpwb2ludGVyfQouYnRuLmdob3N0e2JhY2tncm91bmQ6dHJh"
    "bnNwYXJlbnQ7Y29sb3I6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KX0KLnN0ZXBze2NvdW50ZXIt"
    "cmVzZXQ6c30KLnN0cHtkaXNwbGF5OmZsZXg7Z2FwOjE0cHg7cGFkZGluZzoxMnB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQg"
    "cmdiYSgyNTUsMjU1LDI1NSwuMDYpfQouc3RwIC5ue2ZsZXg6bm9uZTt3aWR0aDozNHB4O2hlaWdodDozNHB4O2JvcmRlci1yYWRp"
    "dXM6NTAlO2JhY2tncm91bmQ6Y29uaWMtZ3JhZGllbnQodmFyKC0tcGluayksdmFyKC0tZ29sZCksdmFyKC0tb2spLHZhcigtLXBp"
    "bmspKTtjb2xvcjojMDUwNzBmO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtm"
    "b250OjcwMCAxNHB4IHZhcigtLW1vbm8pfQouc3RwIGg0e2ZvbnQtc2l6ZToxNS41cHh9LnN0cCBwe2ZvbnQtc2l6ZToxMy41cHg7"
    "Y29sb3I6I2I2YzBkNn0KdGFibGV7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7bWFyZ2luLXRvcDoxMHB4O2Zv"
    "bnQtc2l6ZToxNHB4fQp0ZCx0aHt0ZXh0LWFsaWduOmxlZnQ7cGFkZGluZzo4cHggNnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlk"
    "IHJnYmEoMjU1LDI1NSwyNTUsLjA4KX0KdGh7Zm9udDo1MDAgMTAuNXB4IHZhcigtLW1vbm8pO2xldHRlci1zcGFjaW5nOi4xZW07"
    "Y29sb3I6dmFyKC0tbXV0ZSl9CnRkIGJ7Y29sb3I6dmFyKC0tb2spfQoubm90ZXtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1t"
    "dXRlKTttYXJnaW4tdG9wOjEwcHh9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0"
    "b3AiPjxkaXYgY2xhc3M9ImJyYW5kIj5tb25vcDxiPiBzdHVkaW88L2I+IMK3IGJ5IHNlYmJpLnBybzwvZGl2PjxuYXY+PGEgaHJl"
    "Zj0iLyI+SG9tZTwvYT48YSBocmVmPSIvdG9vbHMiPlRvb2xzPC9hPjxhIGhyZWY9Ii9zdGFydCI+U3RhcnQ8L2E+PC9uYXY+PC9k"
    "aXY+Cgo8ZGl2IGNsYXNzPSJoZXJvIj48ZGl2IGNsYXNzPSJraWNrIj5NT05PUE9MSVNFIFlPVVIgQ09OVEVOVDwvZGl2Pgo8aDE+"
    "WW91ciB2aWRlby4gWW91ciBsb2NrLiBZb3VyIG1vbmV5LjwvaDE+CjxwPkdpdmUgYXdheSB0aGUgZmlyc3QgaGFsZi4gTG9jayB0"
    "aGUgcmVzdCBiZWhpbmQgYSB0YXAuIFZpZXdlcnMgcGF5IHBlbm5pZXMsIHlvdSBrZWVwIG1vc3Qgb2YgaXQsIGFuZCBldmVyeSBw"
    "YWlkIHZpZXcgaXMgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluIHNvIHlvdXIgbnVtYmVycyBjYW4gYmUgcHJvdmVkLCBub3QganVz"
    "dCBjbGFpbWVkLjwvcD48L2Rpdj4KCjxkaXYgY2xhc3M9InBsYXllciIgaWQ9InBsYXllciI+CiA8Y2FudmFzIGlkPSJjdiIgd2lk"
    "dGg9IjEyODAiIGhlaWdodD0iNzIwIj48L2NhbnZhcz4KIDxidXR0b24gY2xhc3M9InBidG4iIGlkPSJwYiI+4pa2PC9idXR0b24+"
    "PGRpdiBjbGFzcz0icHRpbWUiIGlkPSJwdCI+MDowMCAvIDA6Mzg8L2Rpdj4KIDxkaXYgY2xhc3M9InBiYXIiPjxpIGlkPSJwZiI+"
    "PC9pPjwvZGl2PgogPGRpdiBjbGFzcz0ibG9jayIgaWQ9ImxvY2siPgogIDxkaXYgY2xhc3M9ImljIj7wn5SSPC9kaXY+CiAgPGgz"
    "IGlkPSJsb2NrSCI+MTBwIHRvIHdhdGNoIHRoZSByZXN0PC9oMz4KICA8cCBpZD0ibG9ja1AiPllvdSd2ZSBoYWQgdGhlIGZyZWUg"
    "aGFsZi4gVW5sb2NrIHRoZSBmdWxsIHZpZGVvIGZvciAxMHAsIHN0cmFpZ2h0IGZyb20geW91ciBiYWxhbmNlLCBvbmUgdGFwLjwv"
    "cD4KICA8YnV0dG9uIGNsYXNzPSJwYXkiIGlkPSJwYXlCdG4iPlVubG9jayBmb3IgMTBwPC9idXR0b24+CiAgPGRpdiBjbGFzcz0i"
    "bWluaSI+RGVtbyBvbmx5IOKAlCBubyBwYXltZW50IGlzIHRha2VuPC9kaXY+CiAgPGRpdiBjbGFzcz0icmVjZWlwdCIgaWQ9InJj"
    "cHQiPjwvZGl2PgogPC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJub3RlIiBzdHlsZT0idGV4dC1hbGlnbjpjZW50ZXIiPlRhcCBw"
    "bGF5LiBUaGUgbG9jayBkcm9wcyBpbiBhdCB0aGUgaGFsZndheSBtYXJrLCBleGFjdGx5IGFzIHlvdXIgdmlld2VycyB3b3VsZCBz"
    "ZWUgaXQuPC9kaXY+Cgo8c2VjdGlvbiBpZD0iaG93Ij4KIDxoMj5Ib3cgY3JlYXRvcnMgbWFrZSBtb25leTwvaDI+CiA8ZGl2IGNs"
    "YXNzPSJzdGVwcyI+CiAgPGRpdiBjbGFzcz0ic3RwIj48ZGl2IGNsYXNzPSJuIj4xPC9kaXY+PGRpdj48aDQ+VXBsb2FkIG9yIGxp"
    "bmsgeW91ciB2aWRlbzwvaDQ+PHA+QW55dGhpbmcgeW91IG93bi4gWW91IGNob29zZSB3aGVyZSB0aGUgZnJlZSBwYXJ0IGVuZHM6"
    "IDMwIHNlY29uZHMsIGhhbGYsIG9yIHRoZSBmaXJzdCBjaGFwdGVyLjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzdHAi"
    "PjxkaXYgY2xhc3M9Im4iPjI8L2Rpdj48ZGl2PjxoND5TZXQgeW91ciBwcmljZTwvaDQ+PHA+RnJvbSA1cCB0byDCozUgYSB2aWV3"
    "LiBUZW4gcGVuY2UgaXMgdGhlIHN3ZWV0IHNwb3Q6IHNtYWxsIGVub3VnaCB0aGF0IG5vYm9keSB0aGlua3MgdHdpY2UsIGJpZyBl"
    "bm91Z2ggdG8gYWRkIHVwLjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzdHAiPjxkaXYgY2xhc3M9Im4iPjM8L2Rpdj48"
    "ZGl2PjxoND5TaGFyZSBpdCBhbnl3aGVyZTwvaDQ+PHA+T25lIGxpbmssIG9uZSBlbWJlZC4gUG9zdCBpdCBvbiB5b3VyIG93biBm"
    "ZWVkcywgeW91ciBzaXRlLCBhbnl3aGVyZS4gVGhlIGxvY2sgdHJhdmVscyB3aXRoIGl0LjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2"
    "IGNsYXNzPSJzdHAiPjxkaXYgY2xhc3M9Im4iPjQ8L2Rpdj48ZGl2PjxoND5HZXQgcGFpZCwgYW5kIGdldCBwcm9vZjwvaDQ+PHA+"
    "WW91ciBzaGFyZSBsYW5kcyBpbiB5b3VyIGJhbGFuY2UuIEV2ZXJ5IHBhaWQgdmlldyBpcyBzZWFsZWQgb24gdGhlIGNoYWluIHdp"
    "dGggYSBibG9jayBudW1iZXIsIHNvIHlvdXIgdmlldyBjb3VudCBpcyBldmlkZW5jZSwgbm90IGEgY2xhaW0uPC9wPjwvZGl2Pjwv"
    "ZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJwcmljZSI+CiA8aDI+V2hhdCBpdCBjb3N0czwvaDI+CiA8cCBj"
    "bGFzcz0ibGVhZCI+U2ltcGxlIGFuZCB0aGUgc2FtZSBmb3IgZXZlcnlvbmUuPC9wPgogPGRpdiBjbGFzcz0iZ3JpZCB0d28iPgog"
    "IDxkaXYgY2xhc3M9ImNhcmQiPjxoMz41MHAgcGVyIHZpZGVvLCBwZXIgbW9udGg8L2gzPjxwPlRoYXQncyB0aGUga2VlcC1pdC1s"
    "b2NrZWQgZmVlLiBTdG9wIHBheWluZyBhbmQgdGhlIGxvY2sgbGlmdHM7IHRoZSB2aWRlbyBzdGF5cyB5b3VycyBhbmQgdGhlIG1v"
    "bmV5IHlvdSd2ZSBtYWRlIHN0YXlzIHlvdXJzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+WW91IGtlZXAgN3Ag"
    "b2YgZXZlcnkgMTBwPC9oMz48cD5UaHJlZSBwZW5jZSBvZiBlYWNoIHVubG9jayBjb3ZlcnMgdGhlIGxvY2ssIHRoZSBwYXltZW50"
    "IGFuZCB0aGUgc2VhbGVkIHJlY2VpcHQuIE9uIGEgMTBwIHZpZXcgeW91IHRha2UgNzAlLjwvcD48L2Rpdj4KIDwvZGl2PgogPHRh"
    "YmxlPjx0cj48dGg+WW91ciBwcmljZTwvdGg+PHRoPllvdSBrZWVwPC90aD48dGg+c2ViYmkucHJvPC90aD48dGg+MSwwMDAgdmll"
    "d3M8L3RoPjwvdHI+CiA8dHI+PHRkPjVwPC90ZD48dGQ+PGI+My41cDwvYj48L3RkPjx0ZD4xLjVwPC90ZD48dGQ+PGI+wqMzNTwv"
    "Yj48L3RkPjwvdHI+CiA8dHI+PHRkPjEwcDwvdGQ+PHRkPjxiPjdwPC9iPjwvdGQ+PHRkPjNwPC90ZD48dGQ+PGI+wqM3MDwvYj48"
    "L3RkPjwvdHI+CiA8dHI+PHRkPjI1cDwvdGQ+PHRkPjxiPjE3LjVwPC9iPjwvdGQ+PHRkPjcuNXA8L3RkPjx0ZD48Yj7CozE3NTwv"
    "Yj48L3RkPjwvdHI+CiA8dHI+PHRkPjUwcDwvdGQ+PHRkPjxiPjM1cDwvYj48L3RkPjx0ZD4xNXA8L3RkPjx0ZD48Yj7CozM1MDwv"
    "Yj48L3RkPjwvdHI+PC90YWJsZT4KIDxwIGNsYXNzPSJub3RlIj5WaWV3ZXJzIHRvcCB1cCBhIHNtYWxsIGJhbGFuY2Ugb25jZSBh"
    "bmQgc3BlbmQgaXQgYSB0YXAgYXQgYSB0aW1lIGFjcm9zcyBldmVyeSBsb2NrZWQgdmlkZW8sIHNvIGEgY2FyZCBpcyBjaGFyZ2Vk"
    "IG9uY2UgcmF0aGVyIHRoYW4gb24gZXZlcnkgdmlldy48L3A+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjYWxjIj4KIDxoMj5X"
    "b3JrIG91dCB5b3VyIG1vbnRoPC9oMj4KIDxkaXYgY2xhc3M9ImdyaWQgdHdvIj4KICA8ZGl2IGNsYXNzPSJjYXJkIGNhbGMiPgog"
    "ICA8bGFiZWw+UHJpY2UgcGVyIHZpZXcgKHBlbmNlKTwvbGFiZWw+PGlucHV0IGlkPSJjUHJpY2UiIGlucHV0bW9kZT0iZGVjaW1h"
    "bCIgdmFsdWU9IjEwIj4KICAgPGxhYmVsPlZpZGVvcyB5b3UnbGwgbG9jazwvbGFiZWw+PGlucHV0IGlkPSJjVmlkcyIgaW5wdXRt"
    "b2RlPSJudW1lcmljIiB2YWx1ZT0iNCI+CiAgIDxsYWJlbD5QYWlkIHZpZXdzIHBlciB2aWRlbywgcGVyIG1vbnRoPC9sYWJlbD48"
    "aW5wdXQgaWQ9ImNWaWV3cyIgaW5wdXRtb2RlPSJudW1lcmljIiB2YWx1ZT0iNTAwIj4KICAgPGRpdiBjbGFzcz0ib3V0Ij48c3Bh"
    "biBjbGFzcz0iYmlnIiBpZD0iY091dCI+wqMwPC9zcGFuPnlvdXJzIGFmdGVyIHRoZSBtb250aGx5IGZlZTxkaXYgaWQ9ImNEZXRh"
    "aWwiIHN0eWxlPSJjb2xvcjojOGE5M2FkO21hcmdpbi10b3A6NnB4Ij48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj48aDM+V2h5IHBlb3BsZSBwYXk8L2gzPjxwPk5vYm9keSBwYXlzIMKjNSBmb3IgYSB2aWRlbyB0aGV5IGhhdmVuJ3Qg"
    "c2Vlbi4gQWxtb3N0IGV2ZXJ5Ym9keSB0YXBzIDEwcCBvbmNlIHRoZXkncmUgaG9va2VkIGhhbGZ3YXkgdGhyb3VnaC4gVGhlIGZy"
    "ZWUgaGFsZiBkb2VzIHRoZSBzZWxsaW5nOyB0aGUgbG9jayBkb2VzIHRoZSBlYXJuaW5nLjwvcD4KICA8cCBzdHlsZT0ibWFyZ2lu"
    "LXRvcDoxMHB4Ij5BbmQgYmVjYXVzZSBldmVyeSB1bmxvY2sgaXMgc2VhbGVkLCB5b3UgY2FuIHNob3cgYSBzcG9uc29yIGEgdmll"
    "dyBjb3VudCB0aGV5IGNhbiB2ZXJpZnkgdGhlbXNlbHZlcy4gTm8gcGxhdGZvcm0gb24gZWFydGggZ2l2ZXMgeW91IHRoYXQuPC9w"
    "PjwvZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjZW50cmUiPgogPGgyPllvdXIgY29udHJvbCBjZW50cmU8"
    "L2gyPgogPGRpdiBjbGFzcz0iZ3JpZCB0aHJlZSI+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPkxvY2sgYnVpbGRlcjwvaDM+PHA+"
    "UGljayB0aGUgY3V0LW9mZiBwb2ludCwgdGhlIHByaWNlIGFuZCB0aGUgcG9zdGVyIGZyYW1lLiBQcmV2aWV3IGV4YWN0bHkgd2hh"
    "dCBhIHZpZXdlciBzZWVzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+U2hhcmUgcGFjazwvaDM+PHA+T25lIGxp"
    "bmssIG9uZSBlbWJlZCBzbmlwcGV0LCBhbmQgYSByZWFkeS1tYWRlIHRodW1ibmFpbCB3aXRoIHRoZSBwcmljZSBiYWRnZSBidXJu"
    "ZWQgb24uPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPjxoMz5TZWFsZWQgcmVjZWlwdHM8L2gzPjxwPkV2ZXJ5IHBhaWQg"
    "dmlldyB3aXRoIGl0cyBibG9jayBudW1iZXIsIGV4cG9ydGFibGUgZm9yIGEgc3BvbnNvciwgYW4gYWNjb3VudGFudCBvciBhIGNv"
    "dXJ0LjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+RWFybmluZ3M8L2gzPjxwPkJhbGFuY2UsIHBheW91dHMgYW5k"
    "IHRoZSBmZWUsIHBlciB2aWRlbyBhbmQgcGVyIG1vbnRoLCBubyBndWVzc2luZy48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2Fy"
    "ZCI+PGgzPkNsaXAgY3V0dGVyPC9oMz48cD5DaG9vc2UgdGhlIGZyZWUgdGVhc2VyOiBmaXJzdCAzMCBzZWNvbmRzLCBmaXJzdCBo"
    "YWxmLCBvciBhIG1vbWVudCB5b3UgcGljay48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPlByb29mIGJhZGdlPC9o"
    "Mz48cD5QdXQgeW91ciB2ZXJpZmllZCB2aWV3IGNvdW50IG9uIHlvdXIgb3duIHNpdGUsIGxpdmUsIHNvIHNwb25zb3JzIGNhbiBj"
    "aGVjayBpdCB3aXRob3V0IGFza2luZyB5b3UuPC9wPjwvZGl2PgogPC9kaXY+CiA8cHJlPiZsdDshLS0geW91ciBzaGFyZSBzbmlw"
    "cGV0IGxvb2tzIGxpa2UgdGhpcyAtLSZndDsKJmx0O2lmcmFtZSBzcmM9Imh0dHBzOi8vc2ViYmkucHJvL3YvWU9VUl9WSURFT19J"
    "RCIgd2lkdGg9IjEwMCUiIGhlaWdodD0iNDAwIiBhbGxvd2Z1bGxzY3JlZW4mZ3Q7Jmx0Oy9pZnJhbWUmZ3Q7PC9wcmU+CiA8YSBj"
    "bGFzcz0iYnRuIiBocmVmPSJtYWlsdG86anVzdHJpZ2h0ZGVjb3JhdG9yc0BnbWFpbC5jb20/c3ViamVjdD1Nb25vcCUyMFN0dWRp"
    "byUyMC0lMjBlYXJseSUyMGNyZWF0b3IiPkdldCBvbiB0aGUgZmlyc3QgY3JlYXRvciBsaXN0IOKGkjwvYT4KIDxhIGNsYXNzPSJi"
    "dG4gZ2hvc3QiIGhyZWY9Ii9jaW5lbWEiPlNlZSBpdCBpbiB0aGUgY2luZW1hPC9hPgogPHAgY2xhc3M9Im5vdGUiPk1vbm9wIFN0"
    "dWRpbyBpcyBvcGVuaW5nIHRvIGEgZmlyc3QgZ3JvdXAgb2YgY3JlYXRvcnMuIFRoZSBwbGF5ZXIsIHRoZSBsb2NrIGFuZCB0aGUg"
    "c2VhbGVkIHJlY2VpcHRzIGFyZSBidWlsdDsgc2lnbiB1cCBhYm92ZSBhbmQgeW91J2xsIGJlIGluIHRoZSBmaXJzdCByb3VuZC48"
    "L3A+Cjwvc2VjdGlvbj4KPC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewp2YXIgY3Y9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "ImN2IiksZz1jdi5nZXRDb250ZXh0KCIyZCIpLFc9MTI4MCxIPTcyMDsKdmFyIERVUj0zOCwgRlJFRT0wLjUsIHQ9MCwgcGxheWlu"
    "Zz1mYWxzZSwgbGFzdD0wLCB1bmxvY2tlZD1mYWxzZTsKdmFyIEdPTEQ9IiNjOWE4NGMiLE9LPSIjN2ZlM2IwIixCTFVFPSIjOGZk"
    "MGZmIixQSU5LPSIjZDU5YmZmIjsKZnVuY3Rpb24gYmcoKXt2YXIgZ3JkPWcuY3JlYXRlTGluZWFyR3JhZGllbnQoMCwwLFcsSCk7"
    "Z3JkLmFkZENvbG9yU3RvcCgwLCIjMGIxMDI2Iik7Z3JkLmFkZENvbG9yU3RvcCgxLCIjMDMwNTBiIik7Zy5maWxsU3R5bGU9Z3Jk"
    "O2cuZmlsbFJlY3QoMCwwLFcsSCk7CiBnLmdsb2JhbEFscGhhPS4yNTtnLnN0cm9rZVN0eWxlPSIjMWQyYTUyIjtnLmxpbmVXaWR0"
    "aD0xO2Zvcih2YXIgeD0wO3g8Vzt4Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbyh4LDApO2cubGluZVRvKHgsSCk7Zy5zdHJv"
    "a2UoKX0KIGZvcih2YXIgeT0wO3k8SDt5Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygwLHkpO2cubGluZVRvKFcseSk7Zy5z"
    "dHJva2UoKX1nLmdsb2JhbEFscGhhPTF9CmZ1bmN0aW9uIHR4dChzLHksc2l6ZSxjb2wsYWxpZ24pe2cuZmlsbFN0eWxlPWNvbHx8"
    "IiNmZmYiO2cudGV4dEFsaWduPWFsaWdufHwiY2VudGVyIjtnLmZvbnQ9IjYwMCAiK3NpemUrInB4ICdJQk0gUGxleCBTYW5zJyxz"
    "eXN0ZW0tdWksc2Fucy1zZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gc2VyaWYocyx5LHNpemUsY29sKXtnLmZp"
    "bGxTdHlsZT1jb2x8fCIjZmZmIjtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3NpemUrInB4IE5ld3NyZWFkZXIs"
    "R2VvcmdpYSxzZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gbW9ubyhzLHksc2l6ZSxjb2wpe2cuZmlsbFN0eWxl"
    "PWNvbHx8R09MRDtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3NpemUrInB4IHVpLW1vbm9zcGFjZSxNZW5sbyxt"
    "b25vc3BhY2UiO2cuZmlsbFRleHQocyxXLzIseSl9CmZ1bmN0aW9uIGZhZGUoYSl7cmV0dXJuIE1hdGgubWF4KDAsTWF0aC5taW4o"
    "MSxhKSl9CmZ1bmN0aW9uIGJsb2NrKHgseSx3LGgsY29sLGdsb3cpe2cuc2F2ZSgpO2cuc2hhZG93Q29sb3I9Y29sO2cuc2hhZG93"
    "Qmx1cj1nbG93fHwxODtnLmZpbGxTdHlsZT0iIzBkMTQyNCI7Zy5zdHJva2VTdHlsZT1jb2w7Zy5saW5lV2lkdGg9MzsKIGcuYmVn"
    "aW5QYXRoKCk7Zy5yb3VuZFJlY3QoeCx5LHcsaCwxMCk7Zy5maWxsKCk7Zy5zdHJva2UoKTtnLnJlc3RvcmUoKX0KZnVuY3Rpb24g"
    "cm9ib3QoeCx5LHMsY29sKXtnLnNhdmUoKTtnLnRyYW5zbGF0ZSh4LHkpO2cuc2NhbGUocyxzKTtnLmZpbGxTdHlsZT0iI2Q4ZGRl"
    "NiI7CiBnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0yNiwtNzAsNTIsNDAsOCk7Zy5maWxsKCk7Zy5maWxsU3R5bGU9Y29sO2cu"
    "ZmlsbFJlY3QoLTE4LC01OCwzNiw5KTsKIGcuZmlsbFN0eWxlPSIjYzNjOWQ0IjtnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0z"
    "MiwtMjYsNjQsNTQsMTApO2cuZmlsbCgpOwogZy5maWxsU3R5bGU9IiNhZWI2YzQiO2cuZmlsbFJlY3QoLTI0LDMwLDE4LDQyKTtn"
    "LmZpbGxSZWN0KDYsMzAsMTgsNDIpO2cucmVzdG9yZSgpfQpmdW5jdGlvbiBzY2VuZShpLHApewogaWYoaT09PTApe3ZhciBhPWZh"
    "ZGUocCozKTtnLmdsb2JhbEFscGhhPWE7c2VyaWYoInNlYmJpLnBybyIsSC8yLTQwLDk2LCIjZmZmIik7bW9ubygiUFJPT0YgRk9S"
    "IFRIRSBNQUNISU5FIEFHRSIsSC8yKzMwLDI2LEdPTEQpO2cuZ2xvYmFsQWxwaGE9MTsKICBnLnN0cm9rZVN0eWxlPUdPTEQ7Zy5n"
    "bG9iYWxBbHBoYT1hKi42O2cubGluZVdpZHRoPTI7Zy5iZWdpblBhdGgoKTtnLmFyYyhXLzIsSC8yLTEwLDE4MCtwKjQwLDAsNi4y"
    "ODMpO2cuc3Ryb2tlKCk7Zy5nbG9iYWxBbHBoYT0xfQogZWxzZSBpZihpPT09MSl7dHh0KCJZb3VyIEFJIGp1c3QgZGlkIHNvbWV0"
    "aGluZy4iLDEyMCw1NCk7bW9ubygiV0hPIFNBSUQgSVQgQ09VTEQ/IiwxNzYsMjQsUElOSyk7CiAgcm9ib3QoVy8yLTI2MCxILzIr"
    "MTQwLDEuNixPSyk7CiAgZy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdpZHRoPTQ7Zy5zZXRMaW5lRGFzaChbMTIsMTBdKTtnLmJl"
    "Z2luUGF0aCgpO2cubW92ZVRvKFcvMi0yMDAsSC8yKzQwKTtnLmxpbmVUbyhXLzIrMTYwK3AqODAsSC8yKzQwKTtnLnN0cm9rZSgp"
    "O2cuc2V0TGluZURhc2goW10pOwogIGJsb2NrKFcvMisyMDAsSC8yLTQwLDIyMCwxNjAsR09MRCk7dHh0KCLCozQsMDAwIixILzIr"
    "NTAsNDQsR09MRCk7bW9ubygiUEFZTUVOVCIsSC8yKzkwLDIwLCIjOGE5M2FkIil9CiBlbHNlIGlmKGk9PT0yKXt0eHQoInNlYmJp"
    "LnBybyBjaGVja3MgYXQgdGhlIG1vbWVudCBpdCBoYXBwZW5zLiIsMTEwLDQ2KTsKICB2YXIgbj1NYXRoLmZsb29yKHAqNCkrMSxs"
    "YWJlbHM9WyJIdW1hbiBhdXRob3JpdHk/IiwiU3RpbGwgdmFsaWQgbm93PyIsIlJpZ2h0IGFtb3VudD8iLCJVc2VkIGJlZm9yZT8i"
    "XTsKICBmb3IodmFyIGs9MDtrPDQ7aysrKXt2YXIgb249azxuO2cuZ2xvYmFsQWxwaGE9b24/MTouMjU7YmxvY2soMTgwK2sqMjQw"
    "LDMwMCwyMDAsMTIwLG9uP09LOiIjMzM0Iixvbj8yMjo2KTsKICAgZy5maWxsU3R5bGU9b24/T0s6IiM2NjciO2cudGV4dEFsaWdu"
    "PSJjZW50ZXIiO2cuZm9udD0iNjAwIDIycHggJ0lCTSBQbGV4IFNhbnMnLHNhbnMtc2VyaWYiO2cuZmlsbFRleHQobGFiZWxzW2td"
    "LDI4MCtrKjI0MCwzNTIpOwogICBnLmZvbnQ9IjYwMCAzNHB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2UiO2cuZmlsbFRleHQob24/"
    "IuKckyI6IsK3IiwyODArayoyNDAsMzk4KTtnLmdsb2JhbEFscGhhPTF9CiAgbW9ubygiTUlMTElTRUNPTkRTIMK3IE5PIFNFQ09O"
    "RCBBSSBNT0RFTCIsNTIwLDI0LEdPTEQpfQogZWxzZSBpZihpPT09Myl7dHh0KCJUaGVuIGl0J3Mgc2VhbGVkLiBGb3JldmVyLiIs"
    "MTEwLDUwKTsKICBmb3IodmFyIGI9MDtiPDY7YisrKXt2YXIgdmlzPXAqNj5iO2lmKCF2aXMpY29udGludWU7YmxvY2soMTIwK2Iq"
    "MTgwLDI4MCwxNTAsMTQwLEdPTEQsMTYpOwogICBtb25vKCIjIisoMjUxMCtiKSwzNTAsMjAsR09MRCk7Zy5zYXZlKCk7Zy50cmFu"
    "c2xhdGUoMTIwK2IqMTgwKzc1LDMzMCk7Zy5maWxsU3R5bGU9T0s7Zy5mb250PSI1MDAgMTVweCB1aS1tb25vc3BhY2UsbW9ub3Nw"
    "YWNlIjsKICAgZy50ZXh0QWxpZ249ImNlbnRlciI7Zy5maWxsVGV4dCgiYTRmOeKApiIrKGIqNysxMSksMCwwKTtnLnJlc3RvcmUo"
    "KTsKICAgaWYoYil7Zy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdpZHRoPTM7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygxMjArYiox"
    "ODAtMzAsMzUwKTtnLmxpbmVUbygxMjArYioxODAsMzUwKTtnLnN0cm9rZSgpfX0KICBtb25vKCJDSEFOR0UgT05FIEFORCBFVkVS"
    "WSBPTkUgQUZURVIgSVQgQlJFQUtTIiw1MjAsMjQsIiM4YTkzYWQiKX0KIGVsc2UgaWYoaT09PTQpe3R4dCgiVGltZXN0YW1wZWQg"
    "aW4gQml0Y29pbi4iLDExMCw1MCk7CiAgZy5zYXZlKCk7Zy50cmFuc2xhdGUoVy8yLDM2MCk7Zy5yb3RhdGUocCoxLjYpO2cuc3Ry"
    "b2tlU3R5bGU9IiNmNzkzMWEiO2cubGluZVdpZHRoPTY7Zy5iZWdpblBhdGgoKTtnLmFyYygwLDAsMTEwLDAsNi4yODMpO2cuc3Ry"
    "b2tlKCk7Zy5yZXN0b3JlKCk7CiAgZy5maWxsU3R5bGU9IiNmNzkzMWEiO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNjAw"
    "IDkwcHggJ0lCTSBQbGV4IFNhbnMnLHNhbnMtc2VyaWYiO2cuZmlsbFRleHQoIuKCvyIsVy8yLDM5MCk7CiAgbW9ubygiQSBDTE9D"
    "SyBOT0JPRFkgSU5WT0xWRUQgQ09OVFJPTFMiLDUyMCwyNCwiI2Y3OTMxYSIpfQogZWxzZSBpZihpPT09NSl7dHh0KCJIZWxkIGJ5"
    "IHBlb3BsZSB5b3UgZG9uJ3QgY29udHJvbC4iLDExMCw0OCk7CiAgZm9yKHZhciB3PTA7dzw1O3crKyl7dmFyIGFuZz0tTWF0aC5Q"
    "SS8yKyh3LTIpKjAuNSx4PVcvMitNYXRoLmNvcyhhbmcpKjI2MCx5PTQyMCtNYXRoLnNpbihhbmcpKjEyMDsKICAgZy5zdHJva2VT"
    "dHlsZT1CTFVFO2cuZ2xvYmFsQWxwaGE9LjU7Zy5saW5lV2lkdGg9MjtnLmJlZ2luUGF0aCgpO2cubW92ZVRvKFcvMiwzMDApO2cu"
    "bGluZVRvKHgseSk7Zy5zdHJva2UoKTtnLmdsb2JhbEFscGhhPTE7CiAgIGcuZmlsbFN0eWxlPUJMVUU7Zy5iZWdpblBhdGgoKTtn"
    "LmFyYyh4LHksMjIsMCw2LjI4Myk7Zy5maWxsKCl9CiAgYmxvY2soVy8yLTkwLDI0MCwxODAsMTEwLEdPTEQpO21vbm8oIllPVVIg"
    "Q0hBSU4iLDMwNSwyMixHT0xEKTsKICBtb25vKCJJTkRFUEVOREVOVCBXSVRORVNTRVMiLDYwMCwyNCxCTFVFKX0KIGVsc2V7dHh0"
    "KCJFdmVyeSBkZWNpc2lvbi4gUHJvdmFibGUuIixILzItNjAsNjApO21vbm8oIlNFQkJJLlBSTyIsSC8yKzIwLDQwLEdPTEQpO21v"
    "bm8oIkZSRUUgRk9SIDkwIERBWVMgwrcgNTBwIFBFUiBERVZJQ0UiLEgvMis4MCwyMiwiIzhhOTNhZCIpfQp9CmZ1bmN0aW9uIGRy"
    "YXcoKXtiZygpO3ZhciBwZXI9RFVSLzcsaT1NYXRoLm1pbig2LE1hdGguZmxvb3IodC9wZXIpKSxwPSh0LWkqcGVyKS9wZXI7c2Nl"
    "bmUoaSxwKTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwZiIpLnN0eWxlLndpZHRoPSh0L0RVUioxMDApKyIlIjsKIHZhciBt"
    "PU1hdGguZmxvb3IodC82MCkscz1NYXRoLmZsb29yKHQlNjApO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwdCIpLnRleHRDb250"
    "ZW50PW0rIjoiKyhzPDEwPyIwIjoiIikrcysiIC8gMDozOCJ9CmZ1bmN0aW9uIGxvb3Aobm93KXtpZighcGxheWluZylyZXR1cm47"
    "dmFyIGR0PShub3ctbGFzdCkvMTAwMDtsYXN0PW5vdzt0Kz1kdDsKIGlmKCF1bmxvY2tlZCYmdD49RFVSKkZSRUUpe3Q9RFVSKkZS"
    "RUU7cGxheWluZz1mYWxzZTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGIiKS50ZXh0Q29udGVudD0i4pa2Ijtkb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgibG9jayIpLmNsYXNzTGlzdC5hZGQoIm9uIik7ZHJhdygpO3JldHVybn0KIGlmKHQ+PURVUil7dD1EVVI7"
    "cGxheWluZz1mYWxzZTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGIiKS50ZXh0Q29udGVudD0i4oa7In0KIGRyYXcoKTtyZXF1"
    "ZXN0QW5pbWF0aW9uRnJhbWUobG9vcCl9CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwYiIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtp"
    "Zih0Pj1EVVIpe3Q9MH1wbGF5aW5nPSFwbGF5aW5nO3RoaXMudGV4dENvbnRlbnQ9cGxheWluZz8i4p2a4p2aIjoi4pa2IjtsYXN0"
    "PXBlcmZvcm1hbmNlLm5vdygpO2lmKHBsYXlpbmcpcmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3ApfTsKZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoInBheUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXt1bmxvY2tlZD10cnVlOwogdmFyIGJsaz0yNTAwK01hdGguZmxv"
    "b3IoTWF0aC5yYW5kb20oKSo0MDApOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJjcHQiKS5pbm5lckhUTUw9IuKckyBVbmxv"
    "Y2tlZCDCtyBwYWlkIHZpZXcgc2VhbGVkIGluIGJsb2NrICIrYmxrKyIgwrcgY3JlYXRvciBlYXJucyA3cCI7CiB2YXIgc2VsZj10"
    "aGlzO3NlbGYudGV4dENvbnRlbnQ9IlVubG9ja2VkIOKckyI7c2V0VGltZW91dChmdW5jdGlvbigpe2RvY3VtZW50LmdldEVsZW1l"
    "bnRCeUlkKCJsb2NrIikuY2xhc3NMaXN0LnJlbW92ZSgib24iKTsKICBwbGF5aW5nPXRydWU7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5"
    "SWQoInBiIikudGV4dENvbnRlbnQ9IuKdmuKdmiI7bGFzdD1wZXJmb3JtYW5jZS5ub3coKTtyZXF1ZXN0QW5pbWF0aW9uRnJhbWUo"
    "bG9vcCl9LDEyMDApfTsKZHJhdygpOwpmdW5jdGlvbiBjYWxjKCl7dmFyIHA9cGFyc2VGbG9hdChkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgiY1ByaWNlIikudmFsdWUpfHwwLHY9cGFyc2VJbnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWRzIikudmFsdWUp"
    "fHwwLG49cGFyc2VJbnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWV3cyIpLnZhbHVlKXx8MDsKIHZhciBrZWVwPXAqMC43"
    "LGdyb3NzPWtlZXAqdipuLzEwMCxmZWU9MC41KnYsbmV0PWdyb3NzLWZlZTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjT3V0"
    "IikudGV4dENvbnRlbnQ9IsKjIisobmV0PjA/bmV0LnRvRml4ZWQoMik6IjAuMDAiKTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlk"
    "KCJjRGV0YWlsIikudGV4dENvbnRlbnQ9dipuKyIgcGFpZCB2aWV3cyDDlyAiK2tlZXAudG9GaXhlZCgxKSsicCA9IMKjIitncm9z"
    "cy50b0ZpeGVkKDIpKyIgIMK3ICBtb250aGx5IGxvY2sgZmVlIMKjIitmZWUudG9GaXhlZCgyKX0KWyJjUHJpY2UiLCJjVmlkcyIs"
    "ImNWaWV3cyJdLmZvckVhY2goZnVuY3Rpb24oaWQpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKS5hZGRFdmVudExpc3RlbmVy"
    "KCJpbnB1dCIsY2FsYyl9KTtjYWxjKCk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/create": (_d(_HTML_B64), "text/html; charset=utf-8"),
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
