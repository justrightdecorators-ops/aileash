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

485 lines, 44634 bytes

```python
"""
modules/studio.py  v2.0.0
Monop Studio at /create. Lock a video in the browser: the file is read,
fingerprinted and wrapped in its own player with the paywall inside it, then
handed back as a download. The video is never uploaded anywhere. Also the demo
film, the pricing, the earnings calculator and the form that sends a locked
video to the cinema's 10p Wing (modules/marquee.py).

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/studio/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "2.0.0"

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
    "IHVwbG9hZGVkPC9zcGFuPjxzcGFuPvCfkrcgWW91IGtlZXAgNzAlPC9zcGFuPjxzcGFuPuKaoSBSZWFkeSBpbiBzZWNvbmRzPC9z"
    "cGFuPjxzcGFuPvCfjqwgU2hhcmUgYW55d2hlcmU8L3NwYW4+PC9kaXY+CjwvZGl2PgoKPHNlY3Rpb24gaWQ9ImxvY2tpdCIgc3R5"
    "bGU9ImJvcmRlci10b3A6MDttYXJnaW4tdG9wOjIwcHg7cGFkZGluZy10b3A6MTBweCI+CiA8aDI+TG9jayBhIHZpZGVvIG5vdzwv"
    "aDI+CiA8cCBjbGFzcz0ibGVhZCI+RXZlcnl0aGluZyBoYXBwZW5zIG9uIHlvdXIgb3duIGRldmljZS4gVGhlIHZpZGVvIGlzIHJl"
    "YWQsIGZpbmdlcnByaW50ZWQgYW5kIHdyYXBwZWQgaW4gaXRzIG93biBwbGF5ZXIsIHRoZW4gaGFuZGVkIGJhY2sgdG8geW91IGFz"
    "IG9uZSBmaWxlLjwvcD4KIDxkaXYgY2xhc3M9ImdyaWQgdHdvIj4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgPGxhYmVsPllvdXIg"
    "dmlkZW88L2xhYmVsPjxpbnB1dCB0eXBlPSJmaWxlIiBpZD0idUZpbGUiIGFjY2VwdD0idmlkZW8vKiI+CiAgIDxsYWJlbD5UaXRs"
    "ZTwvbGFiZWw+PGlucHV0IGlkPSJ1VGl0bGUiIHBsYWNlaG9sZGVyPSJXaGF0IGlzIGl0IGNhbGxlZD8iPgogICA8bGFiZWw+RnJl"
    "ZSBwcmV2aWV3PC9sYWJlbD48aW5wdXQgaWQ9InVGcmVlIiB0eXBlPSJyYW5nZSIgbWluPSIxMCIgbWF4PSI4MCIgdmFsdWU9IjUw"
    "Ij4KICAgPGRpdiBjbGFzcz0ibWluaSIgaWQ9InVGcmVlTGFiIj5GaXJzdCA1MCUgcGxheXMgZnJlZTwvZGl2PgogICA8bGFiZWw+"
    "UHJpY2UgdG8gdW5sb2NrIChwZW5jZSk8L2xhYmVsPjxpbnB1dCBpZD0idVByaWNlIiBpbnB1dG1vZGU9ImRlY2ltYWwiIHZhbHVl"
    "PSIxMCI+CiAgIDxsYWJlbD5Zb3VyIHBheW1lbnQgbGluayAob3B0aW9uYWwpPC9sYWJlbD48aW5wdXQgaWQ9InVQYXkiIHBsYWNl"
    "aG9sZGVyPSJodHRwczovL2J1eS5zdHJpcGUuY29tL+KApiI+CiAgIDxkaXYgY2xhc3M9Im1pbmkiPlBhc3RlIHlvdXIgb3duIHBh"
    "eW1lbnQgbGluayBhbmQgdGhlIHVubG9jayBidXR0b24gc2VuZHMgdmlld2VycyB0byBpdC4gTGVhdmUgaXQgYmxhbmsgYW5kIHRo"
    "ZSBsb2NrIHJ1bnMgaW4gZGVtbyBtb2RlIHNvIHlvdSBjYW4gdGVzdCBpdC48L2Rpdj4KICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBp"
    "ZD0idUdvIiBzdHlsZT0id2lkdGg6MTAwJTttYXJnaW4tdG9wOjE4cHgiPvCflJIgTG9jayBpdDwvYnV0dG9uPgogICA8ZGl2IGNs"
    "YXNzPSJwcm9nIiBpZD0idVByb2dXcmFwIiBzdHlsZT0iZGlzcGxheTpub25lIj48aSBpZD0idVByb2ciPjwvaT48L2Rpdj4KICAg"
    "PGRpdiBjbGFzcz0ib3V0IiBpZD0idU91dCI+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgIDxoMz5XaGF0"
    "IGNvbWVzIGJhY2s8L2gzPgogICA8cD5PbmUgZmlsZTogPGI+eW91ci10aXRsZS1sb2NrZWQuaHRtbDwvYj4uIE9wZW4gaXQgb24g"
    "YW55IHBob25lIG9yIGNvbXB1dGVyLCBlbWFpbCBpdCwgcHV0IGl0IG9uIHlvdXIgd2Vic2l0ZSwgb3IgcG9zdCB0aGUgbGluayBh"
    "bnl3aGVyZS48L3A+CiAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+CiAgICA8ZGl2IGNsYXNzPSJzdHAiPjxkaXYgY2xh"
    "c3M9Im4iPjE8L2Rpdj48ZGl2PjxoND5QbGF5cyBmcmVlIHRvIHlvdXIgY3V0LW9mZjwvaDQ+PHA+WW91ciB2aWV3ZXIgd2F0Y2hl"
    "cyB0aGUgcHJldmlldyBleGFjdGx5IGFzIG5vcm1hbC48L3A+PC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJzdHAiPjxkaXYg"
    "Y2xhc3M9Im4iPjI8L2Rpdj48ZGl2PjxoND5UaGUgbG9jayBkcm9wcyBpbjwvaDQ+PHA+Qmx1cnJlZCwgd2l0aCB5b3VyIHByaWNl"
    "IG9uIGl0LiBTa2lwcGluZyBhaGVhZCBpcyBibG9ja2VkLjwvcD48L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InN0cCI+PGRp"
    "diBjbGFzcz0ibiI+MzwvZGl2PjxkaXY+PGg0PlRoZXkgcGF5LCBpdCBwbGF5czwvaDQ+PHA+WW91ciBwYXltZW50IGxpbmsgb3Bl"
    "bnM7IHdoZW4gdGhleSBjb21lIGJhY2sgaXQgdW5sb2NrcyBhbmQgc3RheXMgdW5sb2NrZWQgb24gdGhhdCBkZXZpY2UuPC9wPjwv"
    "ZGl2PjwvZGl2PgogICA8L2Rpdj4KICAgPHAgY2xhc3M9Im5vdGUiPkJlc3QgdXAgdG8gYWJvdXQgMjUgTUIsIHdoaWNoIGlzIHR3"
    "byBvciB0aHJlZSBtaW51dGVzIG9mIHBob25lIHZpZGVvLiBCaWdnZXIgZmlsbXMgc3RpbGwgd29yayBidXQgdGFrZSBsb25nZXIg"
    "dG8gYnVpbGQuPC9wPgogIDwvZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJkZW1vIj4KIDxoMj5TZWUgZXhh"
    "Y3RseSB3aGF0IGEgdmlld2VyIHNlZXM8L2gyPgogPHAgY2xhc3M9ImxlYWQiPlRoaXMgaXMgYSByZWFsIDM4LXNlY29uZCBmaWxt"
    "IGFib3V0IHNlYmJpLnBybywgcGxheWluZyBpbiB0aGUgc2FtZSBsb2NrLiBJdCBzdG9wcyBoYWxmd2F5LCBqdXN0IGxpa2UgeW91"
    "cnMgd2lsbC48L3A+CiA8ZGl2IGNsYXNzPSJwbGF5ZXIiIGlkPSJwbGF5ZXIiPgogIDxjYW52YXMgaWQ9ImN2IiB3aWR0aD0iMTI4"
    "MCIgaGVpZ2h0PSI3MjAiPjwvY2FudmFzPgogIDxidXR0b24gY2xhc3M9InBidG4iIGlkPSJwYiI+4pa2PC9idXR0b24+PGRpdiBj"
    "bGFzcz0icHRpbWUiIGlkPSJwdCI+MDowMCAvIDA6Mzg8L2Rpdj4KICA8ZGl2IGNsYXNzPSJwYmFyIj48aSBpZD0icGYiPjwvaT48"
    "L2Rpdj4KICA8ZGl2IGNsYXNzPSJsb2NrIiBpZD0ibG9jayI+CiAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZTozMHB4Ij7wn5SSPC9k"
    "aXY+CiAgIDxoMyBzdHlsZT0iZm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6Y2xhbXAo"
    "MjBweCw0dncsMzBweCkiPjEwcCB0byB3YXRjaCB0aGUgcmVzdDwvaDM+CiAgIDxwIHN0eWxlPSJjb2xvcjojYjZjMGQ2O2ZvbnQt"
    "c2l6ZToxMy41cHg7bWF4LXdpZHRoOjQwY2giPllvdSBoYXZlIGhhZCB0aGUgZnJlZSBoYWxmLiBVbmxvY2sgdGhlIGZ1bGwgdmlk"
    "ZW8gZm9yIDEwcCwgb25lIHRhcC48L3A+CiAgIDxidXR0b24gY2xhc3M9ImJ0biBnb2xkIiBpZD0icGF5QnRuIj5VbmxvY2sgZm9y"
    "IDEwcDwvYnV0dG9uPgogICA8ZGl2IGNsYXNzPSJtaW5pIj5EZW1vIG9ubHkg4oCUIG5vIHBheW1lbnQgaXMgdGFrZW48L2Rpdj4K"
    "ICAgPGRpdiBpZD0icmNwdCIgc3R5bGU9ImZvbnQ6NTAwIDExLjVweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1vaykiPjwvZGl2"
    "PgogIDwvZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjaW5lbWEiPgogPGgyPlB1dCBpdCBpbiB0aGUgMTBw"
    "IFdpbmc8L2gyPgogPHAgY2xhc3M9ImxlYWQiPlRoZSBzZWJiaS5wcm8gY2luZW1hIGhhcyB0d28gd2luZ3M6IGdvdmVybmFuY2Ug"
    "b24gb25lIHNpZGUsIGFuZCB0aGUgMTBwIFdpbmcgb24gdGhlIG90aGVyLCB3aGVyZSBjcmVhdG9ycycgbG9ja2VkIHZpZGVvcyBw"
    "bGF5LiBTZW5kIHVzIHRoZSBsaW5rIHRvIHlvdXIgbG9ja2VkIHBsYXllciBhbmQgaXQgdGFrZXMgYSBzY3JlZW4uPC9wPgogPGRp"
    "diBjbGFzcz0iZ3JpZCB0d28iPgogIDxkaXYgY2xhc3M9ImNhcmQiPgogICA8bGFiZWw+TGluayB0byB5b3VyIGxvY2tlZCB2aWRl"
    "bzwvbGFiZWw+PGlucHV0IGlkPSJtVXJsIiBwbGFjZWhvbGRlcj0iaHR0cHM6Ly/igKYiPgogICA8bGFiZWw+VGl0bGU8L2xhYmVs"
    "PjxpbnB1dCBpZD0ibVRpdGxlIiBwbGFjZWhvbGRlcj0iV2hhdCBpcyBpdCBjYWxsZWQ/Ij4KICAgPGxhYmVsPllvdXIgbmFtZSBv"
    "ciBjaGFubmVsPC9sYWJlbD48aW5wdXQgaWQ9Im1XaG8iIHBsYWNlaG9sZGVyPSJXaG8gbWFkZSBpdD8iPgogICA8bGFiZWw+UHJp"
    "Y2UgKHBlbmNlKTwvbGFiZWw+PGlucHV0IGlkPSJtUHJpY2UiIGlucHV0bW9kZT0ibnVtZXJpYyIgdmFsdWU9IjEwIj4KICAgPGJ1"
    "dHRvbiBjbGFzcz0iYnRuIiBpZD0ibUdvIiBzdHlsZT0id2lkdGg6MTAwJTttYXJnaW4tdG9wOjE2cHgiPvCfjqwgU2VuZCBpdCB0"
    "byB0aGUgMTBwIFdpbmc8L2J1dHRvbj4KICAgPGRpdiBjbGFzcz0ib3V0IiBpZD0ibU91dCI+PC9kaXY+CiAgPC9kaXY+CiAgPGRp"
    "diBjbGFzcz0iY2FyZCI+CiAgIDxoMz5Ib3VzZSBydWxlczwvaDM+CiAgIDxwPk9ubHkgeW91ciBvd24gd29yay4gQnkgc2VuZGlu"
    "ZyBpdCB5b3UgY29uZmlybSB5b3UgaG9sZCB0aGUgcmlnaHRzIHRvIHRoZSB2aWRlbyBhbmQgZXZlcnl0aGluZyBpbiBpdC48L3A+"
    "CiAgIDxwIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPldlIG5ldmVyIGhvbGQgeW91ciB2aWRlbywgb25seSB0aGUgbGluayB5b3Ug"
    "Z2l2ZSB1cyBhbmQgdGhlIHRpdGxlLiBFdmVyeSBzdWJtaXNzaW9uIGlzIHNlYWxlZCBvbiB0aGUgY2hhaW4gd2hlbiBpdCBsYW5k"
    "cywgc28gdGhlIGRhdGUgeW91IHNlbnQgaXQgaXMgcHJvdmFibGUuPC9wPgogICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxMHB4Ij5T"
    "Y3JlZW5zIGFyZSByZXZpZXdlZCBiZWZvcmUgdGhleSBnbyB1cC48L3A+CiAgIDxhIGNsYXNzPSJidG4gZ2hvc3QiIGhyZWY9Ii9j"
    "aW5lbWEiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiPlZpc2l0IHRoZSBjaW5lbWEg4oaSPC9hPgogIDwvZGl2PgogPC9kaXY+Cjwv"
    "c2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJwcmljZSI+CiA8aDI+V2hhdCBpdCBjb3N0czwvaDI+CiA8ZGl2IGNsYXNzPSJncmlkIHR3"
    "byI+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPjUwcCBwZXIgdmlkZW8sIHBlciBtb250aDwvaDM+PHA+VGhlIGtlZXAtaXQtbG9j"
    "a2VkIGZlZS4gU3RvcCBwYXlpbmcgYW5kIHRoZSBsb2NrIGxpZnRzLiBUaGUgdmlkZW8gc3RheXMgeW91cnMgYW5kIGV2ZXJ5IHBl"
    "bm55IHlvdSBoYXZlIG1hZGUgc3RheXMgeW91cnMuPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPjxoMz5Zb3Uga2VlcCA3"
    "cCBvZiBldmVyeSAxMHA8L2gzPjxwPlRocmVlIHBlbmNlIG9mIGVhY2ggdW5sb2NrIGNvdmVycyB0aGUgbG9jaywgdGhlIHBheW1l"
    "bnQgYW5kIHRoZSBzZWFsZWQgcmVjZWlwdC4gVGhhdCBpcyA3MCUgdG8geW91LjwvcD48L2Rpdj4KIDwvZGl2PgogPHRhYmxlPjx0"
    "cj48dGg+WW91ciBwcmljZTwvdGg+PHRoPllvdSBrZWVwPC90aD48dGg+c2ViYmkucHJvPC90aD48dGg+MSwwMDAgdmlld3M8L3Ro"
    "PjwvdHI+CiA8dHI+PHRkPjVwPC90ZD48dGQ+PGI+My41cDwvYj48L3RkPjx0ZD4xLjVwPC90ZD48dGQ+PGI+wqMzNTwvYj48L3Rk"
    "PjwvdHI+CiA8dHI+PHRkPjEwcDwvdGQ+PHRkPjxiPjdwPC9iPjwvdGQ+PHRkPjNwPC90ZD48dGQ+PGI+wqM3MDwvYj48L3RkPjwv"
    "dHI+CiA8dHI+PHRkPjI1cDwvdGQ+PHRkPjxiPjE3LjVwPC9iPjwvdGQ+PHRkPjcuNXA8L3RkPjx0ZD48Yj7CozE3NTwvYj48L3Rk"
    "PjwvdHI+CiA8dHI+PHRkPjUwcDwvdGQ+PHRkPjxiPjM1cDwvYj48L3RkPjx0ZD4xNXA8L3RkPjx0ZD48Yj7CozM1MDwvYj48L3Rk"
    "PjwvdHI+PC90YWJsZT4KIDxkaXYgY2xhc3M9ImdyaWQgdHdvIiBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj4KICAgPGgzPldvcmsgb3V0IHlvdXIgbW9udGg8L2gzPgogICA8bGFiZWw+UHJpY2UgcGVyIHZpZXcgKHBlbmNlKTwv"
    "bGFiZWw+PGlucHV0IGlkPSJjUHJpY2UiIGlucHV0bW9kZT0iZGVjaW1hbCIgdmFsdWU9IjEwIj4KICAgPGxhYmVsPlZpZGVvcyBs"
    "b2NrZWQ8L2xhYmVsPjxpbnB1dCBpZD0iY1ZpZHMiIGlucHV0bW9kZT0ibnVtZXJpYyIgdmFsdWU9IjQiPgogICA8bGFiZWw+UGFp"
    "ZCB2aWV3cyBwZXIgdmlkZW8sIHBlciBtb250aDwvbGFiZWw+PGlucHV0IGlkPSJjVmlld3MiIGlucHV0bW9kZT0ibnVtZXJpYyIg"
    "dmFsdWU9IjUwMCI+CiAgIDxkaXYgY2xhc3M9Im91dCBvbiIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCI+PHNwYW4gY2xhc3M9ImJp"
    "ZyIgaWQ9ImNPdXQiPsKjMDwvc3Bhbj55b3VycyBhZnRlciB0aGUgbW9udGhseSBmZWU8ZGl2IGlkPSJjRGV0YWlsIiBzdHlsZT0i"
    "Y29sb3I6IzhhOTNhZDttYXJnaW4tdG9wOjZweCI+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgz"
    "PldoeSBwZW9wbGUgdGFwPC9oMz48cD5Ob2JvZHkgcGF5cyBmb3IgYSB2aWRlbyB0aGV5IGhhdmUgbm90IHNlZW4uIEFsbW9zdCBl"
    "dmVyeW9uZSB0YXBzIDEwcCBvbmNlIHRoZXkgYXJlIGhvb2tlZCBoYWxmd2F5IHRocm91Z2guIFRoZSBmcmVlIGhhbGYgc2VsbHMg"
    "aXQ7IHRoZSBsb2NrIGVhcm5zIGZyb20gaXQuPC9wPgogIDxwIHN0eWxlPSJtYXJnaW4tdG9wOjEwcHgiPkFuZCBiZWNhdXNlIGV2"
    "ZXJ5IHBhaWQgdmlldyBjYW4gYmUgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluLCB5b3UgY2FuIHNob3cgYSBzcG9uc29yIGEgdmll"
    "dyBjb3VudCB0aGV5IGNhbiBjaGVjayB0aGVtc2VsdmVzLiBObyBvdGhlciBwbGF0Zm9ybSBnaXZlcyB5b3UgdGhhdC48L3A+PC9k"
    "aXY+CiA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9ImNlbnRyZSI+CiA8aDI+WW91ciBjb250cm9sIGNlbnRyZTwvaDI+"
    "CiA8ZGl2IGNsYXNzPSJncmlkIHRocmVlIj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+TG9jayBidWlsZGVyPC9oMz48cD5DdXQt"
    "b2ZmIHBvaW50LCBwcmljZSBhbmQgcGF5bWVudCBsaW5rLiBQcmV2aWV3IGV4YWN0bHkgd2hhdCBhIHZpZXdlciBzZWVzLjwvcD48"
    "L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+U2hhcmUgcGFjazwvaDM+PHA+T25lIGZpbGUsIG9uZSBsaW5rLCBhbmQgYW4g"
    "ZW1iZWQgc25pcHBldCBmb3IgeW91ciBvd24gc2l0ZS48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPlNlYWxlZCBy"
    "ZWNlaXB0czwvaDM+PHA+UGFpZCB2aWV3cyB3aXRoIGJsb2NrIG51bWJlcnMsIGV4cG9ydGFibGUgZm9yIGEgc3BvbnNvciBvciBh"
    "biBhY2NvdW50YW50LjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+VGhlIDEwcCBXaW5nPC9oMz48cD5Zb3VyIGxv"
    "Y2tlZCB2aWRlb3Mgb24gdGhlIGNpbmVtYSdzIGNyZWF0b3Igc2NyZWVucy48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+"
    "PGgzPkZpbmdlcnByaW50czwvaDM+PHA+RXZlcnkgZmlsZSBjYXJyaWVzIGEgaGFzaCBvZiB5b3VyIGV4YWN0IGN1dCwgc28geW91"
    "IGNhbiBwcm92ZSB3aGljaCB2ZXJzaW9uIGlzIHlvdXJzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+UHJvb2Yg"
    "YmFkZ2U8L2gzPjxwPlNob3cgYSB2ZXJpZmllZCB2aWV3IGNvdW50IG9uIHlvdXIgb3duIHNpdGUsIGxpdmUuPC9wPjwvZGl2Pgog"
    "PC9kaXY+CiA8cHJlPiZsdDtpZnJhbWUgc3JjPSJodHRwczovL3lvdXItc2l0ZS5jb20veW91ci12aWRlby1sb2NrZWQuaHRtbCIg"
    "d2lkdGg9IjEwMCUiIGhlaWdodD0iNDIwIiBhbGxvd2Z1bGxzY3JlZW4mZ3Q7Jmx0Oy9pZnJhbWUmZ3Q7PC9wcmU+CiA8YSBjbGFz"
    "cz0iYnRuIiBocmVmPSIjbG9ja2l0Ij5Mb2NrIHlvdXIgZmlyc3QgdmlkZW8g4oaSPC9hPgo8L3NlY3Rpb24+CjwvZGl2Pgo8c2Ny"
    "aXB0IGlkPSJ0cGwiIHR5cGU9InRleHQvcGxhaW4iPlBDRkVUME5VV1ZCRklHaDBiV3crUEdoMGJXd2diR0Z1WnowaVpXNGlQanhv"
    "WldGa1BqeHRaWFJoSUdOb1lYSnpaWFE5SWxWVVJpMDRJajRLUEcxbGRHRWdibUZ0WlQwaWRtbGxkM0J2Y25RaUlHTnZiblJsYm5R"
    "OUluZHBaSFJvUFdSbGRtbGpaUzEzYVdSMGFDeHBibWwwYVdGc0xYTmpZV3hsUFRFc2RtbGxkM0J2Y25RdFptbDBQV052ZG1WeUlq"
    "NEtQSFJwZEd4bFBsOWZWRWxVVEVWZlh6d3ZkR2wwYkdVK0NqeHRaWFJoSUc1aGJXVTlJbVJsYzJOeWFYQjBhVzl1SWlCamIyNTBa"
    "VzUwUFNKZlgxUkpWRXhGWDE4ZzRvQ1VJR3h2WTJ0bFpDQjNhWFJvSUUxdmJtOXdJRk4wZFdScGJ5SStDanh6ZEhsc1pUNEtLbnRp"
    "YjNndGMybDZhVzVuT21KdmNtUmxjaTFpYjNnN2JXRnlaMmx1T2pBN2NHRmtaR2x1Wnpvd2ZRcGliMlI1ZTJKaFkydG5jbTkxYm1R"
    "NmNtRmthV0ZzTFdkeVlXUnBaVzUwS0dWc2JHbHdjMlVnWVhRZ05UQWxJREFsTENNeFlURXdNemdzSXpBMU1EY3daaUEyTlNVcE8y"
    "TnZiRzl5T2lObE9HVmtaamM3Wm05dWRDMW1ZVzFwYkhrNmMzbHpkR1Z0TFhWcExDMWhjSEJzWlMxemVYTjBaVzBzSWxObFoyOWxJ"
    "RlZKSWl4ellXNXpMWE5sY21sbU8yMXBiaTFvWldsbmFIUTZNVEF3ZG1nN1pHbHpjR3hoZVRwbWJHVjRPMkZzYVdkdUxXbDBaVzF6"
    "T21ObGJuUmxjanRxZFhOMGFXWjVMV052Ym5SbGJuUTZZMlZ1ZEdWeU8zQmhaR1JwYm1jNk1UWndlSDBLTG5kN2QybGtkR2c2TVRB"
    "d0pUdHRZWGd0ZDJsa2RHZzZPRFl3Y0hoOUNtZ3hlMlp2Ym5RdGMybDZaVHBqYkdGdGNDZ3hPSEI0TERSMmR5d3lObkI0S1R0bWIy"
    "NTBMWGRsYVdkb2REbzJNREE3YldGeVoybHVMV0p2ZEhSdmJUb3hNSEI0ZlFvdWNIdHdiM05wZEdsdmJqcHlaV3hoZEdsMlpUdGli"
    "M0prWlhJdGNtRmthWFZ6T2pFMmNIZzdiM1psY21ac2IzYzZhR2xrWkdWdU8ySmhZMnRuY205MWJtUTZJekF3TUR0aWIzSmtaWEk2"
    "TVhCNElITnZiR2xrSUhKblltRW9NakF4TERFMk9DdzNOaXd1TXpVcE8ySnZlQzF6YUdGa2IzYzZNQ0F5Tm5CNElEY3djSGdnY21k"
    "aVlTZ3dMREFzTUN3dU5qVXBMREFnTUNBME5IQjRJSEpuWW1Fb01qRXpMREUxTlN3eU5UVXNMakV5S1gwS2RtbGtaVzk3ZDJsa2RH"
    "ZzZNVEF3SlR0a2FYTndiR0Y1T21Kc2IyTnJmUW91Ykd0N2NHOXphWFJwYjI0NllXSnpiMngxZEdVN2FXNXpaWFE2TUR0a2FYTndi"
    "R0Y1T201dmJtVTdabXhsZUMxa2FYSmxZM1JwYjI0NlkyOXNkVzF1TzJGc2FXZHVMV2wwWlcxek9tTmxiblJsY2p0cWRYTjBhV1o1"
    "TFdOdmJuUmxiblE2WTJWdWRHVnlPMmRoY0RveE1uQjRPM1JsZUhRdFlXeHBaMjQ2WTJWdWRHVnlPM0JoWkdScGJtYzZNakp3ZUR0"
    "aVlXTnJaM0p2ZFc1a09uSm5ZbUVvTlN3M0xERTFMQzQ0TmlrN1ltRmphMlJ5YjNBdFptbHNkR1Z5T21Kc2RYSW9PWEI0S1gwS0xt"
    "eHJMbTl1ZTJScGMzQnNZWGs2Wm14bGVIMEtMbWxqZTJadmJuUXRjMmw2WlRvek1uQjRmUW91YkdzZ2FESjdabTl1ZEMxemFYcGxP"
    "bU5zWVcxd0tERTVjSGdzTkM0MmRuY3NNekJ3ZUNrN1ptOXVkQzEzWldsbmFIUTZOakF3ZlFvdWJHc2djSHRqYjJ4dmNqb2pZalpq"
    "TUdRMk8yWnZiblF0YzJsNlpUb3hOSEI0TzIxaGVDMTNhV1IwYURvek9HTm9mUW91WW50aVlXTnJaM0p2ZFc1a09pTmpPV0U0TkdN"
    "N1kyOXNiM0k2SXpBMU1EY3daanRpYjNKa1pYSTZNRHRpYjNKa1pYSXRjbUZrYVhWek9qRXhjSGc3Y0dGa1pHbHVaem94TkhCNElE"
    "STBjSGc3Wm05dWREbzJNREFnTVRWd2VDQjFhUzF0YjI1dmMzQmhZMlVzVFdWdWJHOHNiVzl1YjNOd1lXTmxPMk4xY25OdmNqcHdi"
    "Mmx1ZEdWeU8zUmxlSFF0WkdWamIzSmhkR2x2YmpwdWIyNWxPMkp2ZUMxemFHRmtiM2M2TUNBd0lESTRjSGdnY21kaVlTZ3lNREVz"
    "TVRZNExEYzJMQzQwTlNsOUNpNXRlMlp2Ym5RNk5UQXdJREV4Y0hnZ2RXa3RiVzl1YjNOd1lXTmxMRzF2Ym05emNHRmpaVHRqYjJ4"
    "dmNqb2pPR0U1TTJGa2ZRb3VZbUZ5ZTNCdmMybDBhVzl1T21GaWMyOXNkWFJsTzJ4bFpuUTZNRHR5YVdkb2REb3dPMkp2ZEhSdmJU"
    "b3dPMmhsYVdkb2REbzBjSGc3WW1GamEyZHliM1Z1WkRweVoySmhLREkxTlN3eU5UVXNNalUxTEM0eE1pbDlDaTVpWVhJZ2FYdGth"
    "WE53YkdGNU9tSnNiMk5yTzJobGFXZG9kRG94TURBbE8zZHBaSFJvT2pBN1ltRmphMmR5YjNWdVpEcHNhVzVsWVhJdFozSmhaR2xs"
    "Ym5Rb09UQmtaV2NzSTJRMU9XSm1aaXdqWXpsaE9EUmpMQ00zWm1VellqQXBmUW91Wm5KbFpYdHdiM05wZEdsdmJqcGhZbk52YkhW"
    "MFpUdDBiM0E2TVRCd2VEdHNaV1owT2pFeWNIZzdZbUZqYTJkeWIzVnVaRHB5WjJKaEtEVXNOeXd4TlN3dU56VXBPMkp2Y21SbGNq"
    "b3hjSGdnYzI5c2FXUWdjbWRpWVNneU1ERXNNVFk0TERjMkxDNDBLVHRpYjNKa1pYSXRjbUZrYVhWek9qazVPWEI0TzNCaFpHUnBi"
    "bWM2TlhCNElERXdjSGc3Wm05dWREbzJNREFnTVRBdU5YQjRJSFZwTFcxdmJtOXpjR0ZqWlN4dGIyNXZjM0JoWTJVN1kyOXNiM0k2"
    "STJNNVlUZzBZMzBLTG5SN2JXRnlaMmx1TFhSdmNEb3hNbkI0TzJadmJuUTZOVEF3SURFeExqVndlQ0IxYVMxdGIyNXZjM0JoWTJV"
    "c2JXOXViM053WVdObE8yTnZiRzl5T2lNNFlUa3pZV1E3ZEdWNGRDMWhiR2xuYmpwalpXNTBaWEk3YkdsdVpTMW9aV2xuYUhRNk1T"
    "NDNmUW91ZENCaGUyTnZiRzl5T2lOak9XRTROR003ZEdWNGRDMWtaV052Y21GMGFXOXVPbTV2Ym1WOUNqd3ZjM1I1YkdVK1BDOW9a"
    "V0ZrUGp4aWIyUjVQanhrYVhZZ1kyeGhjM005SW5jaVBnbzhhREUrWDE5VVNWUk1SVjlmUEM5b01UNEtQR1JwZGlCamJHRnpjejBp"
    "Y0NJK0NpQThkbWxrWlc4Z2FXUTlJbllpSUhCc1lYbHphVzVzYVc1bElHTnZiblJ5YjJ4eklHTnZiblJ5YjJ4elRHbHpkRDBpYm05"
    "a2IzZHViRzloWkNJZ1pHbHpZV0pzWlhCcFkzUjFjbVZwYm5CcFkzUjFjbVVnYzNKalBTSmZYMU5TUTE5ZklqNDhMM1pwWkdWdlBn"
    "b2dQR1JwZGlCamJHRnpjejBpWm5KbFpTSWdhV1E5SW1aeVpXVlVZV2NpUGtaU1JVVWdVRkpGVmtsRlZ6d3ZaR2wyUGdvZ1BHUnBk"
    "aUJqYkdGemN6MGlZbUZ5SWo0OGFTQnBaRDBpY0dZaVBqd3ZhVDQ4TDJScGRqNEtJRHhrYVhZZ1kyeGhjM005SW14cklpQnBaRDBp"
    "YkdzaVBnb2dJRHhrYVhZZ1kyeGhjM005SW1saklqNG1JekV5T0RJM05EczhMMlJwZGo0S0lDQThhREkrWDE5UVVrbERSVjlmY0NC"
    "MGJ5QjNZWFJqYUNCMGFHVWdjbVZ6ZER3dmFESStDaUFnUEhBK1ZHaGhkQ0IzWVhNZ2RHaGxJR1p5WldVZ2NISmxkbWxsZHk0Z1ZX"
    "NXNiMk5ySUhSb1pTQm1kV3hzSUhacFpHVnZJR0Z1WkNCclpXVndJSGRoZEdOb2FXNW5Mand2Y0Q0S0lDQmZYMUJCV1VKVVRsOWZD"
    "aUE4TDJScGRqNEtQQzlrYVhZK0NqeGthWFlnWTJ4aGMzTTlJblFpUGt4dlkydGxaQ0IzYVhSb0lEeGhJR2h5WldZOUltaDBkSEJ6"
    "T2k4dmMyVmlZbWt1Y0hKdkwyTnlaV0YwWlNJZ2RHRnlaMlYwUFNKZllteGhibXNpSUhKbGJEMGlibTl2Y0dWdVpYSWlQazF2Ym05"
    "d0lGTjBkV1JwYnp3dllUNGdKbTFwWkdSdmREc2dabWx1WjJWeWNISnBiblFnWDE5VFNFOVNWRWhCVTBoZlh5Wm9aV3hzYVhBN1BH"
    "SnlQZ3BVYUdseklIWnBaR1Z2SUhkaGN5QnVaWFpsY2lCMWNHeHZZV1JsWkNCaGJubDNhR1Z5WlM0Z1NYUWdiR2wyWlhNZ2FXNXph"
    "V1JsSUhSb2FYTWdabWxzWlM0OEwyUnBkajRLUEM5a2FYWStDanh6WTNKcGNIUStDaWhtZFc1amRHbHZiaWdwZXdvaWRYTmxJSE4w"
    "Y21samRDSTdDblpoY2lCMlBXUnZZM1Z0Wlc1MExtZGxkRVZzWlcxbGJuUkNlVWxrS0NKMklpa3NiR3M5Wkc5amRXMWxiblF1WjJW"
    "MFJXeGxiV1Z1ZEVKNVNXUW9JbXhySWlrc2NHWTlaRzlqZFcxbGJuUXVaMlYwUld4bGJXVnVkRUo1U1dRb0luQm1JaWtzQ2lBZ0lD"
    "QjBZV2M5Wkc5amRXMWxiblF1WjJWMFJXeGxiV1Z1ZEVKNVNXUW9JbVp5WldWVVlXY2lLU3huYnoxa2IyTjFiV1Z1ZEM1blpYUkZi"
    "R1Z0Wlc1MFFubEpaQ2dpWjI4aUtTd0tJQ0FnSUVaU1JVVTlYMTlHVWtWRlgxOHNJRXRGV1QwaWJXOXViM0E2WDE5VFNFOVNWRWhC"
    "VTBoZlh5SXNJSEJoYVdROVptRnNjMlU3Q25SeWVYc2dhV1lvYkc5allXeFRkRzl5WVdkbExtZGxkRWwwWlcwb1MwVlpLVDA5UFNJ"
    "eElpa2djR0ZwWkQxMGNuVmxPeUI5WTJGMFkyZ29aU2w3ZlFwcFppaHNiMk5oZEdsdmJpNXpaV0Z5WTJndWFXNWtaWGhQWmlnaWNH"
    "RnBaRDB4SWlrK1BUQXBleUJ3WVdsa1BYUnlkV1U3SUhSeWVYdHNiMk5oYkZOMGIzSmhaMlV1YzJWMFNYUmxiU2hMUlZrc0lqRWlL"
    "WDFqWVhSamFDaGxLWHQ5SUgwS2FXWW9jR0ZwWkNrZ2RHRm5Mbk4wZVd4bExtUnBjM0JzWVhrOUltNXZibVVpT3dwMkxtRmtaRVYy"
    "Wlc1MFRHbHpkR1Z1WlhJb0luUnBiV1YxY0dSaGRHVWlMR1oxYm1OMGFXOXVLQ2w3Q2lBZ2FXWW9JWFl1WkhWeVlYUnBiMjRwSUhK"
    "bGRIVnlianNLSUNCd1ppNXpkSGxzWlM1M2FXUjBhRDBvZGk1amRYSnlaVzUwVkdsdFpTOTJMbVIxY21GMGFXOXVLakV3TUNrcklp"
    "VWlPd29nSUdsbUtIQmhhV1FwSUhKbGRIVnlianNLSUNCcFppaDJMbU4xY25KbGJuUlVhVzFsSUQ0OUlIWXVaSFZ5WVhScGIyNHFS"
    "bEpGUlNsN0lIWXVjR0YxYzJVb0tUc2dkaTVqZFhKeVpXNTBWR2x0WlQxMkxtUjFjbUYwYVc5dUtrWlNSVVU3SUd4ckxtTnNZWE56"
    "VEdsemRDNWhaR1FvSW05dUlpazdJSDBLZlNrN0NuWXVZV1JrUlhabGJuUk1hWE4wWlc1bGNpZ2ljMlZsYTJsdVp5SXNablZ1WTNS"
    "cGIyNG9LWHNnYVdZb0lYQmhhV1FnSmlZZ2RpNWtkWEpoZEdsdmJpQW1KaUIyTG1OMWNuSmxiblJVYVcxbElENGdkaTVrZFhKaGRH"
    "bHZiaXBHVWtWRktYc2dkaTVqZFhKeVpXNTBWR2x0WlQxMkxtUjFjbUYwYVc5dUtrWlNSVVU3SUd4ckxtTnNZWE56VEdsemRDNWha"
    "R1FvSW05dUlpazdJSDBnZlNrN0NtbG1LR2R2S1NCbmJ5NWhaR1JGZG1WdWRFeHBjM1JsYm1WeUtDSmpiR2xqYXlJc1puVnVZM1Jw"
    "YjI0b0tYc2dYMTlRUVZsS1UxOWZJSDBwT3dwOUtTZ3BPd284TDNOamNtbHdkRDQ4TDJKdlpIaytQQzlvZEcxc1Bnbz08L3Njcmlw"
    "dD4KPHNjcmlwdD4KKGZ1bmN0aW9uKCl7CiJ1c2Ugc3RyaWN0IjsKLyogLS0tLS0tLS0tLS0tLS0tLSBkZW1vIGZpbG0gLS0tLS0t"
    "LS0tLS0tLS0tLSAqLwp2YXIgY3Y9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImN2IiksZz1jdi5nZXRDb250ZXh0KCIyZCIpLFc9"
    "MTI4MCxIPTcyMDsKdmFyIERVUj0zOCxGUkVFPS41LHQ9MCxwbGF5aW5nPWZhbHNlLGxhc3Q9MCx1bmxvY2tlZD1mYWxzZTsKdmFy"
    "IEdPTEQ9IiNjOWE4NGMiLE9LPSIjN2ZlM2IwIixCTFVFPSIjOGZkMGZmIixQSU5LPSIjZDU5YmZmIjsKZnVuY3Rpb24gYmcoKXt2"
    "YXIgZD1nLmNyZWF0ZUxpbmVhckdyYWRpZW50KDAsMCxXLEgpO2QuYWRkQ29sb3JTdG9wKDAsIiMwYjEwMjYiKTtkLmFkZENvbG9y"
    "U3RvcCgxLCIjMDMwNTBiIik7Zy5maWxsU3R5bGU9ZDtnLmZpbGxSZWN0KDAsMCxXLEgpOwogZy5nbG9iYWxBbHBoYT0uMjI7Zy5z"
    "dHJva2VTdHlsZT0iIzFkMmE1MiI7Zy5saW5lV2lkdGg9MTtmb3IodmFyIHg9MDt4PFc7eCs9NjQpe2cuYmVnaW5QYXRoKCk7Zy5t"
    "b3ZlVG8oeCwwKTtnLmxpbmVUbyh4LEgpO2cuc3Ryb2tlKCl9CiBmb3IodmFyIHk9MDt5PEg7eSs9NjQpe2cuYmVnaW5QYXRoKCk7"
    "Zy5tb3ZlVG8oMCx5KTtnLmxpbmVUbyhXLHkpO2cuc3Ryb2tlKCl9Zy5nbG9iYWxBbHBoYT0xfQpmdW5jdGlvbiB0eHQocyx5LHNp"
    "emUsY29sKXtnLmZpbGxTdHlsZT1jb2x8fCIjZmZmIjtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjYwMCAiK3NpemUrInB4"
    "ICdJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gc2VyaWYo"
    "cyx5LHNpemUsY29sKXtnLmZpbGxTdHlsZT1jb2x8fCIjZmZmIjtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3Np"
    "emUrInB4IE5ld3NyZWFkZXIsR2VvcmdpYSxzZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gbW9ubyhzLHksc2l6"
    "ZSxjb2wpe2cuZmlsbFN0eWxlPWNvbHx8R09MRDtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3NpemUrInB4IHVp"
    "LW1vbm9zcGFjZSxNZW5sbyxtb25vc3BhY2UiO2cuZmlsbFRleHQocyxXLzIseSl9CmZ1bmN0aW9uIGJsb2NrKHgseSx3LGgsY29s"
    "LGdsb3cpe2cuc2F2ZSgpO2cuc2hhZG93Q29sb3I9Y29sO2cuc2hhZG93Qmx1cj1nbG93fHwxODtnLmZpbGxTdHlsZT0iIzBkMTQy"
    "NCI7Zy5zdHJva2VTdHlsZT1jb2w7Zy5saW5lV2lkdGg9MzsKIGcuYmVnaW5QYXRoKCk7Zy5yb3VuZFJlY3QoeCx5LHcsaCwxMCk7"
    "Zy5maWxsKCk7Zy5zdHJva2UoKTtnLnJlc3RvcmUoKX0KZnVuY3Rpb24gcm9ib3QoeCx5LHMsY29sKXtnLnNhdmUoKTtnLnRyYW5z"
    "bGF0ZSh4LHkpO2cuc2NhbGUocyxzKTtnLmZpbGxTdHlsZT0iI2Q4ZGRlNiI7CiBnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0y"
    "NiwtNzAsNTIsNDAsOCk7Zy5maWxsKCk7Zy5maWxsU3R5bGU9Y29sO2cuZmlsbFJlY3QoLTE4LC01OCwzNiw5KTsKIGcuZmlsbFN0"
    "eWxlPSIjYzNjOWQ0IjtnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0zMiwtMjYsNjQsNTQsMTApO2cuZmlsbCgpOwogZy5maWxs"
    "U3R5bGU9IiNhZWI2YzQiO2cuZmlsbFJlY3QoLTI0LDMwLDE4LDQyKTtnLmZpbGxSZWN0KDYsMzAsMTgsNDIpO2cucmVzdG9yZSgp"
    "fQpmdW5jdGlvbiBzY2VuZShpLHApewogaWYoaT09PTApe3ZhciBhPU1hdGgubWluKDEscCozKTtnLmdsb2JhbEFscGhhPWE7c2Vy"
    "aWYoInNlYmJpLnBybyIsSC8yLTQwLDk2KTttb25vKCJQUk9PRiBGT1IgVEhFIE1BQ0hJTkUgQUdFIixILzIrMzAsMjYsR09MRCk7"
    "CiAgZy5zdHJva2VTdHlsZT1HT0xEO2cuZ2xvYmFsQWxwaGE9YSouNjtnLmxpbmVXaWR0aD0yO2cuYmVnaW5QYXRoKCk7Zy5hcmMo"
    "Vy8yLEgvMi0xMCwxODArcCo0MCwwLDYuMjgzKTtnLnN0cm9rZSgpO2cuZ2xvYmFsQWxwaGE9MX0KIGVsc2UgaWYoaT09PTEpe3R4"
    "dCgiWW91ciBBSSBqdXN0IGRpZCBzb21ldGhpbmcuIiwxMjAsNTQpO21vbm8oIldITyBTQUlEIElUIENPVUxEPyIsMTc2LDI0LFBJ"
    "TkspOwogIHJvYm90KFcvMi0yNjAsSC8yKzE0MCwxLjYsT0spOwogIGcuc3Ryb2tlU3R5bGU9R09MRDtnLmxpbmVXaWR0aD00O2cu"
    "c2V0TGluZURhc2goWzEyLDEwXSk7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbyhXLzItMjAwLEgvMis0MCk7Zy5saW5lVG8oVy8yKzE2"
    "MCtwKjgwLEgvMis0MCk7Zy5zdHJva2UoKTtnLnNldExpbmVEYXNoKFtdKTsKICBibG9jayhXLzIrMjAwLEgvMi00MCwyMjAsMTYw"
    "LEdPTEQpO3R4dCgiwqM0LDAwMCIsSC8yKzUwLDQ0LEdPTEQpO21vbm8oIlBBWU1FTlQiLEgvMis5MCwyMCwiIzhhOTNhZCIpfQog"
    "ZWxzZSBpZihpPT09Mil7dHh0KCJzZWJiaS5wcm8gY2hlY2tzIGF0IHRoZSBtb21lbnQgaXQgaGFwcGVucy4iLDExMCw0Nik7CiAg"
    "dmFyIG49TWF0aC5mbG9vcihwKjQpKzEsTD1bIkh1bWFuIGF1dGhvcml0eT8iLCJTdGlsbCB2YWxpZCBub3c/IiwiUmlnaHQgYW1v"
    "dW50PyIsIlVzZWQgYmVmb3JlPyJdOwogIGZvcih2YXIgaz0wO2s8NDtrKyspe3ZhciBvbj1rPG47Zy5nbG9iYWxBbHBoYT1vbj8x"
    "Oi4yNTtibG9jaygxODArayoyNDAsMzAwLDIwMCwxMjAsb24/T0s6IiMzMzQiLG9uPzIyOjYpOwogICBnLmZpbGxTdHlsZT1vbj9P"
    "SzoiIzY2NyI7Zy50ZXh0QWxpZ249ImNlbnRlciI7Zy5mb250PSI2MDAgMjJweCAnSUJNIFBsZXggU2Fucycsc2Fucy1zZXJpZiI7"
    "Zy5maWxsVGV4dChMW2tdLDI4MCtrKjI0MCwzNTIpOwogICBnLmZvbnQ9IjYwMCAzNHB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2Ui"
    "O2cuZmlsbFRleHQob24/IuKckyI6IsK3IiwyODArayoyNDAsMzk4KTtnLmdsb2JhbEFscGhhPTF9CiAgbW9ubygiTUlMTElTRUNP"
    "TkRTIMK3IE5PIFNFQ09ORCBBSSBNT0RFTCIsNTIwLDI0LEdPTEQpfQogZWxzZSBpZihpPT09Myl7dHh0KCJUaGVuIGl0IGlzIHNl"
    "YWxlZC4gRm9yZXZlci4iLDExMCw1MCk7CiAgZm9yKHZhciBiPTA7Yjw2O2IrKyl7aWYocCo2PGIpY29udGludWU7YmxvY2soMTIw"
    "K2IqMTgwLDI4MCwxNTAsMTQwLEdPTEQsMTYpO21vbm8oIiMiKygyNTEwK2IpLDM1MCwyMCxHT0xEKTsKICAgZy5maWxsU3R5bGU9"
    "T0s7Zy50ZXh0QWxpZ249ImNlbnRlciI7Zy5mb250PSI1MDAgMTVweCB1aS1tb25vc3BhY2UsbW9ub3NwYWNlIjtnLmZpbGxUZXh0"
    "KCJhNGY54oCmIisoYio3KzExKSwxMjArYioxODArNzUsMzMwKTsKICAgaWYoYil7Zy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdp"
    "ZHRoPTM7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygxMjArYioxODAtMzAsMzUwKTtnLmxpbmVUbygxMjArYioxODAsMzUwKTtnLnN0"
    "cm9rZSgpfX0KICBtb25vKCJDSEFOR0UgT05FIEFORCBFVkVSWSBPTkUgQUZURVIgSVQgQlJFQUtTIiw1MjAsMjQsIiM4YTkzYWQi"
    "KX0KIGVsc2UgaWYoaT09PTQpe3R4dCgiVGltZXN0YW1wZWQgaW4gQml0Y29pbi4iLDExMCw1MCk7CiAgZy5zYXZlKCk7Zy50cmFu"
    "c2xhdGUoVy8yLDM2MCk7Zy5yb3RhdGUocCoxLjYpO2cuc3Ryb2tlU3R5bGU9IiNmNzkzMWEiO2cubGluZVdpZHRoPTY7Zy5iZWdp"
    "blBhdGgoKTtnLmFyYygwLDAsMTEwLDAsNi4yODMpO2cuc3Ryb2tlKCk7Zy5yZXN0b3JlKCk7CiAgZy5maWxsU3R5bGU9IiNmNzkz"
    "MWEiO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNjAwIDkwcHggJ0lCTSBQbGV4IFNhbnMnLHNhbnMtc2VyaWYiO2cuZmls"
    "bFRleHQoIuKCvyIsVy8yLDM5MCk7CiAgbW9ubygiQSBDTE9DSyBOT0JPRFkgSU5WT0xWRUQgQ09OVFJPTFMiLDUyMCwyNCwiI2Y3"
    "OTMxYSIpfQogZWxzZSBpZihpPT09NSl7dHh0KCJIZWxkIGJ5IHBlb3BsZSB5b3UgZG8gbm90IGNvbnRyb2wuIiwxMTAsNDgpOwog"
    "IGZvcih2YXIgdz0wO3c8NTt3Kyspe3ZhciBhbmc9LU1hdGguUEkvMisody0yKSouNSx4PVcvMitNYXRoLmNvcyhhbmcpKjI2MCx5"
    "PTQyMCtNYXRoLnNpbihhbmcpKjEyMDsKICAgZy5zdHJva2VTdHlsZT1CTFVFO2cuZ2xvYmFsQWxwaGE9LjU7Zy5saW5lV2lkdGg9"
    "MjtnLmJlZ2luUGF0aCgpO2cubW92ZVRvKFcvMiwzMDApO2cubGluZVRvKHgseSk7Zy5zdHJva2UoKTtnLmdsb2JhbEFscGhhPTE7"
    "CiAgIGcuZmlsbFN0eWxlPUJMVUU7Zy5iZWdpblBhdGgoKTtnLmFyYyh4LHksMjIsMCw2LjI4Myk7Zy5maWxsKCl9CiAgYmxvY2so"
    "Vy8yLTkwLDI0MCwxODAsMTEwLEdPTEQpO21vbm8oIllPVVIgQ0hBSU4iLDMwNSwyMixHT0xEKTttb25vKCJJTkRFUEVOREVOVCBX"
    "SVRORVNTRVMiLDYwMCwyNCxCTFVFKX0KIGVsc2V7dHh0KCJFdmVyeSBkZWNpc2lvbi4gUHJvdmFibGUuIixILzItNjAsNjApO21v"
    "bm8oIlNFQkJJLlBSTyIsSC8yKzIwLDQwLEdPTEQpO21vbm8oIkZSRUUgRk9SIDkwIERBWVMgwrcgNTBwIFBFUiBERVZJQ0UiLEgv"
    "Mis4MCwyMiwiIzhhOTNhZCIpfX0KZnVuY3Rpb24gZHJhdygpe2JnKCk7dmFyIHBlcj1EVVIvNyxpPU1hdGgubWluKDYsTWF0aC5m"
    "bG9vcih0L3BlcikpO3NjZW5lKGksKHQtaSpwZXIpL3Blcik7CiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGYiKS5zdHlsZS53"
    "aWR0aD0odC9EVVIqMTAwKSsiJSI7CiB2YXIgcz1NYXRoLmZsb29yKHQlNjApO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwdCIp"
    "LnRleHRDb250ZW50PSIwOiIrKHM8MTA/IjAiOiIiKStzKyIgLyAwOjM4In0KZnVuY3Rpb24gbG9vcChub3cpe2lmKCFwbGF5aW5n"
    "KXJldHVybjt2YXIgZHQ9KG5vdy1sYXN0KS8xMDAwO2xhc3Q9bm93O3QrPWR0OwogaWYoIXVubG9ja2VkJiZ0Pj1EVVIqRlJFRSl7"
    "dD1EVVIqRlJFRTtwbGF5aW5nPWZhbHNlO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwYiIpLnRleHRDb250ZW50PSLilrYiO2Rv"
    "Y3VtZW50LmdldEVsZW1lbnRCeUlkKCJsb2NrIikuY2xhc3NMaXN0LmFkZCgib24iKTtkcmF3KCk7cmV0dXJufQogaWYodD49RFVS"
    "KXt0PURVUjtwbGF5aW5nPWZhbHNlO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwYiIpLnRleHRDb250ZW50PSLihrsifQogZHJh"
    "dygpO3JlcXVlc3RBbmltYXRpb25GcmFtZShsb29wKX0KZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInBiIikub25jbGljaz1mdW5j"
    "dGlvbigpe2lmKHQ+PURVUil0PTA7cGxheWluZz0hcGxheWluZzt0aGlzLnRleHRDb250ZW50PXBsYXlpbmc/IuKdmuKdmiI6IuKW"
    "tiI7bGFzdD1wZXJmb3JtYW5jZS5ub3coKTtpZihwbGF5aW5nKXJlcXVlc3RBbmltYXRpb25GcmFtZShsb29wKX07CmRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJwYXlCdG4iKS5vbmNsaWNrPWZ1bmN0aW9uKCl7dW5sb2NrZWQ9dHJ1ZTsKIGRvY3VtZW50LmdldEVs"
    "ZW1lbnRCeUlkKCJyY3B0IikudGV4dENvbnRlbnQ9IuKckyBVbmxvY2tlZCDCtyBwYWlkIHZpZXcgc2VhbGVkIGluIGJsb2NrICIr"
    "KDI1MDArTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKjQwMCkpKyIgwrcgY3JlYXRvciBlYXJucyA3cCI7CiB0aGlzLnRleHRDb250"
    "ZW50PSJVbmxvY2tlZCDinJMiO3ZhciBzZWxmPXRoaXM7CiBzZXRUaW1lb3V0KGZ1bmN0aW9uKCl7ZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoImxvY2siKS5jbGFzc0xpc3QucmVtb3ZlKCJvbiIpO3BsYXlpbmc9dHJ1ZTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgi"
    "cGIiKS50ZXh0Q29udGVudD0i4p2a4p2aIjtsYXN0PXBlcmZvcm1hbmNlLm5vdygpO3JlcXVlc3RBbmltYXRpb25GcmFtZShsb29w"
    "KX0sMTEwMCl9OwpkcmF3KCk7CgovKiAtLS0tLS0tLS0tLS0tLS0tIGxvY2sgYSB2aWRlbyAtLS0tLS0tLS0tLS0tLS0tICovCnZh"
    "ciBUUEw9YXRvYihkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidHBsIikudGV4dENvbnRlbnQudHJpbSgpKTsKdmFyIEY9ZG9jdW1l"
    "bnQuZ2V0RWxlbWVudEJ5SWQoInVGcmVlIiksRkw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInVGcmVlTGFiIik7CkYuYWRkRXZl"
    "bnRMaXN0ZW5lcigiaW5wdXQiLGZ1bmN0aW9uKCl7RkwudGV4dENvbnRlbnQ9IkZpcnN0ICIrRi52YWx1ZSsiJSBwbGF5cyBmcmVl"
    "In0pOwpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmluZyhzKS5yZXBsYWNlKC9bJjw+IiddL2csZnVuY3Rpb24oYyl7cmV0dXJu"
    "eyImIjoiJmFtcDsiLCI8IjoiJmx0OyIsIj4iOiImZ3Q7IiwnIic6IiZxdW90OyIsIiciOiImIzM5OyJ9W2NdfSl9CmZ1bmN0aW9u"
    "IHNoYShidWYpe3JldHVybiBjcnlwdG8uc3VidGxlLmRpZ2VzdCgiU0hBLTI1NiIsYnVmKS50aGVuKGZ1bmN0aW9uKGgpewogcmV0"
    "dXJuIEFycmF5LnByb3RvdHlwZS5tYXAuY2FsbChuZXcgVWludDhBcnJheShoKSxmdW5jdGlvbihiKXtyZXR1cm4gYi50b1N0cmlu"
    "ZygxNikucGFkU3RhcnQoMiwiMCIpfSkuam9pbigiIil9KX0KZnVuY3Rpb24gYnVpbGQobyl7CiB2YXIgcGF5QnRuID0gby5wYXkK"
    "ICAgPyAnPGEgY2xhc3M9ImIiIGlkPSJnbyIgaHJlZj0iJytlc2Moby5wYXkpKyciIHRhcmdldD0iX2JsYW5rIiByZWw9Im5vb3Bl"
    "bmVyIj5VbmxvY2sgZm9yICcrby5wcmljZSsncDwvYT48ZGl2IGNsYXNzPSJtIj5Zb3Ugd2lsbCBjb21lIGJhY2sgaGVyZSBhZnRl"
    "ciBwYXlpbmc8L2Rpdj4nCiAgIDogJzxidXR0b24gY2xhc3M9ImIiIGlkPSJnbyI+VW5sb2NrIGZvciAnK28ucHJpY2UrJ3A8L2J1"
    "dHRvbj48ZGl2IGNsYXNzPSJtIj5EZW1vIG1vZGUgJm1pZGRvdDsgbm8gcGF5bWVudCB0YWtlbjwvZGl2Pic7CiB2YXIgcGF5SnMg"
    "PSBvLnBheQogICA/ICd0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oS0VZLCIxIil9Y2F0Y2goZSl7fScKICAgOiAncGFpZD10cnVl"
    "O2xrLmNsYXNzTGlzdC5yZW1vdmUoIm9uIik7dGFnLnN0eWxlLmRpc3BsYXk9Im5vbmUiO3YucGxheSgpOyc7CiByZXR1cm4gVFBM"
    "LnNwbGl0KCJfX1RJVExFX18iKS5qb2luKGVzYyhvLnRpdGxlKSkKICAgLnNwbGl0KCJfX1BSSUNFX18iKS5qb2luKFN0cmluZyhv"
    "LnByaWNlKSkKICAgLnNwbGl0KCJfX0ZSRUVfXyIpLmpvaW4oU3RyaW5nKG8uZnJlZSkpCiAgIC5zcGxpdCgiX19TSE9SVEhBU0hf"
    "XyIpLmpvaW4oby5oYXNoLnNsaWNlKDAsMTYpKQogICAuc3BsaXQoIl9fUEFZQlROX18iKS5qb2luKHBheUJ0bikKICAgLnNwbGl0"
    "KCJfX1BBWUpTX18iKS5qb2luKHBheUpzKQogICAuc3BsaXQoIl9fU1JDX18iKS5qb2luKG8uc3JjKTsKfQp2YXIgb3V0PWRvY3Vt"
    "ZW50LmdldEVsZW1lbnRCeUlkKCJ1T3V0IikscHc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInVQcm9nV3JhcCIpLHByPWRvY3Vt"
    "ZW50LmdldEVsZW1lbnRCeUlkKCJ1UHJvZyIpLGJ0bj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidUdvIik7CmZ1bmN0aW9uIHN0"
    "ZXAocGN0LG1zZyl7cHcuc3R5bGUuZGlzcGxheT0iYmxvY2siO3ByLnN0eWxlLndpZHRoPXBjdCsiJSI7b3V0LmNsYXNzTGlzdC5h"
    "ZGQoIm9uIik7b3V0LmlubmVySFRNTD1tc2d9CmJ0bi5vbmNsaWNrPWZ1bmN0aW9uKCl7CiB2YXIgZj1kb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgidUZpbGUiKS5maWxlc1swXTsKIGlmKCFmKXtvdXQuY2xhc3NMaXN0LmFkZCgib24iKTtvdXQuaW5uZXJIVE1MPSJQ"
    "aWNrIGEgdmlkZW8gZmlyc3QuIjtyZXR1cm59CiB2YXIgdGl0bGU9KGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ1VGl0bGUiKS52"
    "YWx1ZXx8Zi5uYW1lLnJlcGxhY2UoL1wuW14uXSskLywiIikpLnRyaW0oKS5zbGljZSgwLDgwKTsKIHZhciBwcmljZT1NYXRoLm1h"
    "eCgxLE1hdGgucm91bmQocGFyc2VGbG9hdChkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidVByaWNlIikudmFsdWUpfHwxMCkpOwog"
    "dmFyIGZyZWU9KHBhcnNlSW50KEYudmFsdWUsMTApfHw1MCkvMTAwOwogdmFyIHBheT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgi"
    "dVBheSIpLnZhbHVlLnRyaW0oKTsKIGlmKHBheSAmJiAhL15odHRwczpcL1wvLy50ZXN0KHBheSkpe291dC5jbGFzc0xpc3QuYWRk"
    "KCJvbiIpO291dC5pbm5lckhUTUw9IllvdXIgcGF5bWVudCBsaW5rIG5lZWRzIHRvIHN0YXJ0IHdpdGggaHR0cHM6Ly8iO3JldHVy"
    "bn0KIGJ0bi5kaXNhYmxlZD10cnVlO3N0ZXAoMTAsIlJlYWRpbmcgeW91ciB2aWRlbyAoIisoZi5zaXplLzEwNDg1NzYpLnRvRml4"
    "ZWQoMSkrIiBNQinigKYgbm90aGluZyBpcyBiZWluZyB1cGxvYWRlZC4iKTsKIGYuYXJyYXlCdWZmZXIoKS50aGVuKGZ1bmN0aW9u"
    "KGJ1Zil7c3RlcCgzNSwiRmluZ2VycHJpbnRpbmcgeW91ciBleGFjdCBjdXTigKYiKTtyZXR1cm4gc2hhKGJ1Zil9KQogLnRoZW4o"
    "ZnVuY3Rpb24oaCl7c3RlcCg1NSwiV3JhcHBpbmcgaXQgaW4gaXRzIG93biBwbGF5ZXLigKYiKTsKICByZXR1cm4gbmV3IFByb21p"
    "c2UoZnVuY3Rpb24ocmVzLHJlail7dmFyIHI9bmV3IEZpbGVSZWFkZXIoKTtyLm9ubG9hZD1mdW5jdGlvbigpe3JlcyhbaCxTdHJp"
    "bmcoci5yZXN1bHQpXSl9O3Iub25lcnJvcj1yZWo7ci5yZWFkQXNEYXRhVVJMKGYpfSl9KQogLnRoZW4oZnVuY3Rpb24ocGFpcil7"
    "CiAgdmFyIGg9cGFpclswXSxzcmM9cGFpclsxXTsKICBzdGVwKDg1LCJCdWlsZGluZyB5b3VyIGZpbGXigKYiKTsKICB2YXIgaHRt"
    "bD1idWlsZCh7dGl0bGU6dGl0bGUscHJpY2U6cHJpY2UsZnJlZTpmcmVlLHBheTpwYXksaGFzaDpoLHNyYzpzcmN9KTsKICB2YXIg"
    "dXJsPVVSTC5jcmVhdGVPYmplY3RVUkwobmV3IEJsb2IoW2h0bWxdLHt0eXBlOiJ0ZXh0L2h0bWwifSkpOwogIHZhciBuYW1lPSh0"
    "aXRsZS5yZXBsYWNlKC9bXkEtWmEtejAtOSBfLV0vZywiIikudHJpbSgpLnJlcGxhY2UoL1xzKy9nLCItIikudG9Mb3dlckNhc2Uo"
    "KXx8InZpZGVvIikrIi1sb2NrZWQuaHRtbCI7CiAgc3RlcCgxMDAsJzxzcGFuIGNsYXNzPSJiaWciPkxvY2tlZCDinJM8L3NwYW4+"
    "JysKICAgIkZpbmdlcnByaW50ICIraC5zbGljZSgwLDMyKSsi4oCmPGJyPkZyZWUgcHJldmlldzogZmlyc3QgIitNYXRoLnJvdW5k"
    "KGZyZWUqMTAwKSsiJSDCtyBVbmxvY2s6ICIrcHJpY2UrInAgwrcgIisocGF5PyJwYXlpbmcgdGhyb3VnaCB5b3VyIGxpbmsiOiJk"
    "ZW1vIG1vZGUiKSsKICAgJzxicj48YSBjbGFzcz0iYnRuIGdvbGQiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiIGhyZWY9IicrdXJs"
    "KyciIGRvd25sb2FkPSInK25hbWUrJyI+4qyHIERvd25sb2FkIHlvdXIgbG9ja2VkIHZpZGVvPC9hPicrCiAgICc8ZGl2IGNsYXNz"
    "PSJub3RlIj5Zb3VyIHZpZGVvIG5ldmVyIGxlZnQgdGhpcyBkZXZpY2UuIE9wZW4gdGhlIGZpbGUsIHNoYXJlIGl0LCBvciBzZW5k"
    "IHRoZSBsaW5rIHRvIHRoZSAxMHAgV2luZyBiZWxvdy48L2Rpdj4nKTsKICBidG4uZGlzYWJsZWQ9ZmFsc2U7CiB9KS5jYXRjaChm"
    "dW5jdGlvbihlKXtzdGVwKDAsIkNvdWxkIG5vdCBidWlsZCBpdDogIitTdHJpbmcoZSkuc2xpY2UoMCwxNDApKTtidG4uZGlzYWJs"
    "ZWQ9ZmFsc2V9KTsKfTsKCi8qIC0tLS0tLS0tLS0tLS0tLS0gc2VuZCB0byB0aGUgMTBwIFdpbmcgLS0tLS0tLS0tLS0tLS0tLSAq"
    "Lwpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibUdvIikub25jbGljaz1mdW5jdGlvbigpewogdmFyIG89ZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoIm1PdXQiKSx1cmw9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1VcmwiKS52YWx1ZS50cmltKCk7CiBvLmNsYXNz"
    "TGlzdC5hZGQoIm9uIik7CiBpZighL15odHRwczpcL1wvLy50ZXN0KHVybCkpe28uaW5uZXJIVE1MPSJHaXZlIHRoZSBodHRwczov"
    "LyBsaW5rIHRvIHlvdXIgbG9ja2VkIHZpZGVvLiI7cmV0dXJufQogby5pbm5lckhUTUw9IlNlbmRpbmfigKYiOwogZmV0Y2goIi94"
    "L21hcnF1ZWUvc3VibWl0Iix7bWV0aG9kOiJQT1NUIixoZWFkZXJzOnsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiJ9"
    "LAogIGJvZHk6SlNPTi5zdHJpbmdpZnkoe3VybDp1cmwsdGl0bGU6ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm1UaXRsZSIpLnZh"
    "bHVlLAogICBjcmVhdG9yOmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJtV2hvIikudmFsdWUscHJpY2U6ZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoIm1QcmljZSIpLnZhbHVlfSl9KQogLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpfSkudGhlbihmdW5j"
    "dGlvbihkKXsKICBvLmlubmVySFRNTCA9IGQucmVjZWl2ZWQKICAgPyAnPHNwYW4gY2xhc3M9ImJpZyI+U2VudCDinJM8L3NwYW4+"
    "U2VhbGVkIGluIGJsb2NrICcrZC5ibG9ja19pbmRleCsnLiBJdCBnb2VzIHVwIG9uY2UgaXQgaGFzIGJlZW4gbG9va2VkIGF0LicK"
    "ICAgOiAoZC5tZXNzYWdlfHwiQ291bGQgbm90IHNlbmQgaXQuIik7CiB9KS5jYXRjaChmdW5jdGlvbigpe28uaW5uZXJIVE1MPSJD"
    "b3VsZCBub3QgcmVhY2ggdGhlIGNpbmVtYS4ifSk7Cn07CgovKiAtLS0tLS0tLS0tLS0tLS0tIGNhbGN1bGF0b3IgLS0tLS0tLS0t"
    "LS0tLS0tLSAqLwpmdW5jdGlvbiBjYWxjKCl7dmFyIHA9cGFyc2VGbG9hdChkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY1ByaWNl"
    "IikudmFsdWUpfHwwLHY9cGFyc2VJbnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWRzIikudmFsdWUpfHwwLG49cGFyc2VJ"
    "bnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWV3cyIpLnZhbHVlKXx8MDsKIHZhciBrZWVwPXAqLjcsZ3Jvc3M9a2VlcCp2"
    "Km4vMTAwLGZlZT0uNSp2LG5ldD1ncm9zcy1mZWU7CiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY091dCIpLnRleHRDb250ZW50"
    "PSLCoyIrKG5ldD4wP25ldC50b0ZpeGVkKDIpOiIwLjAwIik7CiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgiY0RldGFpbCIpLnRl"
    "eHRDb250ZW50PSh2Km4pKyIgcGFpZCB2aWV3cyDDlyAiK2tlZXAudG9GaXhlZCgxKSsicCA9IMKjIitncm9zcy50b0ZpeGVkKDIp"
    "KyIgIMK3ICBtb250aGx5IGxvY2sgZmVlIMKjIitmZWUudG9GaXhlZCgyKX0KWyJjUHJpY2UiLCJjVmlkcyIsImNWaWV3cyJdLmZv"
    "ckVhY2goZnVuY3Rpb24oaWQpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKS5hZGRFdmVudExpc3RlbmVyKCJpbnB1dCIsY2Fs"
    "Yyl9KTtjYWxjKCk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
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
