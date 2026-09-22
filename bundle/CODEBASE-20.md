# Codebase — part 20 of 39

Contains:
- `modules/standing.py`
- `modules/startpage.py`
- `modules/stats.py`
- `modules/tokensaver.py`


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


## `modules/tokensaver.py`

1670 lines, 64529 bytes

```python
#!/usr/bin/env python3
"""
modules/tokensaver.py  v2.0.0
sebbi.pro - the token saver

Reached at /x/tokensaver/<action>.

WHAT IT IS
----------
A deterministic gate that sits in front of a model and decides, in
arithmetic alone, whether a request is answered from store, sent to the
model, sent to a cheaper one, held for a person, or refused.

It also tells the caller, on every single request, exactly what in that
request is costing money that it does not need to cost.

Every decision seals into the platform chain. The saving is a receipt,
not a claim.

HOW IT IS BUILT
---------------
Three layers, in this order, because a cost gate that depends entirely
on tuned weights is a cost gate nobody can defend in a meeting.

  Layer 1  HARD RULES
           Absolute, arithmetic, untunable. A budget that is spent is
           spent. A request repeating identically eight times is a
           runaway. These do not consult the score at all.

  Layer 2  THE SCORE
           Nine weighted signals summing to exactly 1.00, split into
           the ones that measure what this request will SPEND and the
           ones that measure whether that spend is WASTE.

  Layer 3  FINDINGS
           Named, itemised waste inside the request, each with a token
           figure attached and each marked exact or estimated. This is
           the part that saves the most money, because it changes what
           the caller sends next time.

THREE TIERS OF CERTAINTY, NEVER MIXED
-------------------------------------
  tokens_not_bought          EXACT. Provider-reported counts on a
                             request that was served from store.
                             This is the only number that goes in a
                             savings total.

  worst_case_tokens_avoided  A CEILING, not a saving. When a request
                             is refused, max_tokens tells you the most
                             it could have cost. Reported separately
                             and never added to the exact figure.

  findings tokens            ESTIMATED where marked. Character counts
                             divided by four. Never enters any total.

Nothing on this page is ever expressed as a percentage saved.

WHAT IT DOES NOT DO
-------------------
- It never calls a model to reach a decision. Every signal is
  arithmetic on the request itself.
- It only serves a stored answer for an IDENTICAL request. Matching
  similar prompts needs an embedding, which is a model call, which
  would defeat the entire point.
- It does not judge whether a stored answer is still correct.
- It does not store answers to requests that asked for varied output,
  unless the caller overrides that deliberately.

MODULE CONTRACT
---------------
handle(method, action, data, api_key, ctx) -> (dict, status)
PUBLIC is a set of (METHOD, action) tuples.
ctx exposes conn, lock and seal.
"""

import hashlib
import inspect
import json
import math
import sqlite3
import threading
import time

VERSION = "2.2.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "stats"),
    ("GET", "verify"),
}

# ============================================================ layer 1
# Hard rules. Absolute. Not weights, not tunable by score band.

LOOP_WINDOW = 120          # seconds a repeat still counts as a repeat
LOOP_HARD = 8              # identical repeats in the window = runaway
LOOP_HARD_UNATTENDED = 4   # lower bar when no human is watching
BURST_HARD = 120           # requests in 60s from one key = runaway

# ============================================================ layer 2
# Nine signals. Base weights MUST sum to exactly 1.00.
#
# What this request will SPEND ......................... 0.62
W_EXPOSURE = 0.18   # worst case spend against remaining budget
W_SIZE = 0.14       # prompt characters
W_ASK = 0.14        # max_tokens ceiling the caller authorised
W_DEPTH = 0.10      # conversation turns, re-sent on every call
W_TOOLS = 0.06      # tool definitions, re-sent on every call
#
# Whether that spend is WASTE .......................... 0.38
W_LOOP = 0.16       # the same request going round again
W_BURST = 0.09      # requests in the last 60 seconds
W_GRIND = 0.07      # requests in the last hour
W_NOVELTY = 0.06    # first time this shape has been seen

BASE_SUM = (W_EXPOSURE + W_SIZE + W_ASK + W_DEPTH + W_TOOLS
            + W_LOOP + W_BURST + W_GRIND + W_NOVELTY)

# Sits outside the base sum, deliberately.
W_UNATTENDED = 0.10

BAND_CHALLENGE = 0.55
BAND_BLOCK = 0.80

SAT_LOOP = 5
SAT_BURST = 20
SAT_GRIND = 200
SAT_SIZE = 100_000
SAT_ASK = 8_000
SAT_DEPTH = 40
SAT_TOOLS = 24

# A request only earns the cheap model by being genuinely small.
# Suspicion never routes a request to a weaker model.
CHEAP_MAX_CHARS = 4_000
CHEAP_MAX_TURNS = 6
CHEAP_MAX_ASK = 1_000
CHEAP_MAX_SCORE = 0.30

W60 = 60
W1H = 3600

# ============================================================ layer 3
CTX_KEEP_TURNS = 8          # turns beyond this are flagged as carried
CTX_FLAG_TURNS = 12         # only flag once the conversation is this deep
SYSTEM_FLAG_CHARS = 2_000
CHARS_PER_TOKEN = 4.0       # the estimate, used only in findings

DEFAULT_TTL = 30 * 24 * 3600
MAX_STORED_BYTES = 512 * 1024
MAX_PROMPT_CHARS = 2_000_000

KEYED_FIELDS = (
    "model", "messages", "system", "prompt", "input",
    "temperature", "top_p", "top_k",
    "max_tokens", "max_completion_tokens",
    "stop", "stop_sequences",
    "tools", "tool_choice", "response_format", "seed",
)

VOCABULARY = {
    "SERVE": "answered from an identical earlier request; nothing was bought",
    "ALLOW": "send it to the model as asked",
    "DOWNGRADE": "small and simple enough for the cheap model",
    "CHALLENGE": "hold it for a person before spending",
    "BLOCK": "refused; it never reaches the model, so no completion is paid for",
}

LIMITS = [
    "Matching is exact. A reworded prompt is a different request and goes "
    "to the model.",
    "Savings totals use only token counts the provider itself reported. "
    "Nothing in a total is estimated.",
    "A refused request has a worst case cost, not a known cost. It is "
    "reported separately and never added to the savings total.",
    "Token figures inside findings are estimated from character counts and "
    "are marked as estimates. They never enter a total.",
    "A stored answer is returned unchanged. This module does not judge "
    "whether it is still correct.",
    "No model is called to reach any decision here.",
]


# --------------------------------------------------------------- helpers

def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _fingerprint(req):
    keyed = {k: req[k] for k in KEYED_FIELDS if k in req}
    return _sha(b"SEBBI-TOKENSAVER-v2\n" + _canonical(keyed))


def _content_chars(v):
    if v is None:
        return 0
    if isinstance(v, str):
        return len(v)
    return len(_canonical(v))


def _prompt_chars(req):
    total = 0
    for key in ("prompt", "input", "system"):
        total += _content_chars(req.get(key))
    msgs = req.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            total += _content_chars(m.get("content") if isinstance(m, dict) else m)
    tools = req.get("tools")
    if tools is not None:
        total += _content_chars(tools)
    return total


def _est_tokens(chars):
    """Estimate only. Marked as such everywhere it appears."""
    return int(chars / CHARS_PER_TOKEN)


def _ask_ceiling(req):
    """The caller's own authorised output ceiling. Exact, not estimated."""
    v = req.get("max_tokens")
    if v is None:
        v = req.get("max_completion_tokens")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _shape(req):
    n = len(req.get("messages") or [])
    t = len(req.get("tools") or [])
    band = int(math.log10(max(_prompt_chars(req), 1)) * 2)
    return _sha("%s|%d|%d|%d" % (req.get("model") or "", n, t, band))


def _measure(req):
    """Everything the decision needs, taken from a full request."""
    return {
        "fp": _fingerprint(req),
        "shape": _shape(req),
        "chars": _prompt_chars(req),
        "ask": _ask_ceiling(req),
        "depth": len(req.get("messages") or []),
        "tools": len(req.get("tools") or []),
        "deterministic": _deterministic(req),
        "from_digest": False,
    }


def _measure_from_digest(d):
    """
    The same measurements, supplied by a client that kept its content at
    home. The client is measuring its own spend against its own budget,
    so there is nothing to gain by misreporting.
    """
    if not isinstance(d, dict):
        return None, "digest must be an object"
    fp = d.get("fingerprint")
    if not isinstance(fp, str) or len(fp) != 64:
        return None, "digest needs a 64 character fingerprint"
    try:
        int(fp, 16)
    except ValueError:
        return None, "fingerprint must be hexadecimal"

    def _n(key, cap):
        v = d.get(key, 0)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, min(v, cap))

    m = {
        "fp": fp,
        "chars": _n("prompt_characters", MAX_PROMPT_CHARS),
        "ask": _n("max_tokens", 10_000_000),
        "depth": _n("conversation_turns", 100_000),
        "tools": _n("tool_definitions", 100_000),
        "deterministic": bool(d.get("deterministic", True)),
        "from_digest": True,
    }
    band = int(math.log10(max(m["chars"], 1)) * 2)
    m["shape"] = _sha("%s|%d|%d|%d" % (d.get("model") or "", m["depth"],
                                       m["tools"], band))
    return m, None


def _log_scale(value, saturation):
    if value <= 0:
        return 0.0
    if value >= saturation:
        return 1.0
    return math.log1p(value) / math.log1p(saturation)


def _linear(value, saturation):
    if value <= 0:
        return 0.0
    return min(1.0, float(value) / float(saturation))


def _deterministic(req):
    t = req.get("temperature")
    if t is None:
        return True
    try:
        return float(t) == 0.0
    except (TypeError, ValueError):
        return False


def _usage(resp):
    if not isinstance(resp, dict):
        return (None, None)
    u = resp.get("usage")
    if not isinstance(u, dict):
        return (None, None)
    i = u.get("input_tokens", u.get("prompt_tokens"))
    o = u.get("output_tokens", u.get("completion_tokens"))
    try:
        return (int(i) if i is not None else None,
                int(o) if o is not None else None)
    except (TypeError, ValueError):
        return (None, None)


def _money(tokens_in, tokens_out, price_in, price_out):
    if price_in is None and price_out is None:
        return None
    m = 0.0
    if price_in:
        m += (tokens_in or 0) / 1_000_000.0 * price_in
    if price_out:
        m += (tokens_out or 0) / 1_000_000.0 * price_out
    return round(m, 4)


# --------------------------------------------------------------- storage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ts_store (
    api_key       TEXT NOT NULL,
    fp            TEXT NOT NULL,
    model         TEXT,
    response      TEXT NOT NULL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    stored_at     REAL NOT NULL,
    expires_at    REAL,
    hits          INTEGER NOT NULL DEFAULT 0,
    last_hit      REAL,
    PRIMARY KEY (api_key, fp)
);

CREATE TABLE IF NOT EXISTS ts_seen (
    api_key  TEXT NOT NULL,
    fp       TEXT NOT NULL,
    ts       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ts_shape (
    api_key  TEXT NOT NULL,
    shape    TEXT NOT NULL,
    first_ts REAL NOT NULL,
    PRIMARY KEY (api_key, shape)
);

CREATE TABLE IF NOT EXISTS ts_decision (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key     TEXT NOT NULL,
    ts          REAL NOT NULL,
    fp          TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    rule        TEXT,
    score       REAL NOT NULL,
    signals     TEXT NOT NULL,
    exact_in    INTEGER,
    exact_out   INTEGER,
    ceiling_in  INTEGER,
    ceiling_out INTEGER,
    audit_hash  TEXT
);

CREATE TABLE IF NOT EXISTS ts_account (
    api_key    TEXT PRIMARY KEY,
    ceiling    INTEGER NOT NULL DEFAULT 0,
    spent      INTEGER NOT NULL DEFAULT 0,
    price_in   REAL,
    price_out  REAL,
    currency   TEXT,
    updated    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ts_seen_key ON ts_seen(api_key, ts);
CREATE INDEX IF NOT EXISTS ts_seen_fp ON ts_seen(api_key, fp, ts);
CREATE INDEX IF NOT EXISTS ts_dec_key ON ts_decision(api_key, id);
CREATE INDEX IF NOT EXISTS ts_dec_hash ON ts_decision(audit_hash);
CREATE INDEX IF NOT EXISTS ts_store_exp ON ts_store(expires_at);
"""

_ready = {}


def _init(ctx):
    # Keyed by id, but the connection itself is kept as the value so the
    # id cannot be recycled while we still believe in it.
    k = id(ctx.conn)
    if _ready.get(k) is ctx.conn:
        return
    with ctx.lock:
        ctx.conn.executescript(_SCHEMA)
        ctx.conn.commit()
    _ready[k] = ctx.conn


def _account(ctx, api_key):
    row = ctx.conn.execute(
        "SELECT ceiling, spent, price_in, price_out, currency "
        "FROM ts_account WHERE api_key=?", (api_key,)
    ).fetchone()
    if not row:
        return {"ceiling": 0, "spent": 0, "price_in": None,
                "price_out": None, "currency": None}
    return {"ceiling": row[0], "spent": row[1], "price_in": row[2],
            "price_out": row[3], "currency": row[4]}


def _prune(ctx, api_key, now):
    ctx.conn.execute("DELETE FROM ts_seen WHERE api_key=? AND ts < ?",
                     (api_key, now - W1H))


# ================================================================ layer 3

def _findings(req, loop_n, has_stored, acct):
    """
    Named waste inside this request. Every item carries a token figure
    and says whether that figure is exact or estimated. This never
    feeds a total.
    """
    out = []
    msgs = req.get("messages") or []
    depth = len(msgs)
    tools = req.get("tools") or []
    ask = _ask_ceiling(req)

    # The biggest one in agent systems: the same request going round
    # and nobody recording the answer.
    if loop_n >= 2 and not has_stored:
        out.append({
            "code": "repeating_without_recording",
            "severity": "high",
            "detail": "This exact request has gone out %d times in the last "
                      "%d seconds and no answer has been recorded. Post the "
                      "response back to record and every repeat after that "
                      "costs nothing."
                      % (loop_n, LOOP_WINDOW),
            "tokens": None,
            "certainty": "not counted",
        })

    if not _deterministic(req):
        out.append({
            "code": "varied_output_blocks_reuse",
            "severity": "medium",
            "detail": "temperature is above zero, so this answer cannot be "
                      "safely reused. If this request does not genuinely need "
                      "varied output, setting temperature to zero makes every "
                      "repeat free.",
            "tokens": None,
            "certainty": "not counted",
        })

    if depth > CTX_FLAG_TURNS:
        carried = msgs[:-CTX_KEEP_TURNS] if CTX_KEEP_TURNS < depth else []
        chars = sum(_content_chars(m.get("content") if isinstance(m, dict)
                                   else m) for m in carried)
        out.append({
            "code": "carrying_old_turns",
            "severity": "high" if chars > 20_000 else "medium",
            "detail": "%d turns are being re-sent on every call. The oldest "
                      "%d of them account for roughly the tokens below, paid "
                      "again each time this conversation continues."
                      % (depth, len(carried)),
            "tokens": _est_tokens(chars),
            "certainty": "estimated from character count",
        })

    if tools:
        used = False
        for m in msgs:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            blob = c if isinstance(c, str) else _canonical(c).decode("utf-8", "ignore")
            if "tool_use" in blob or "tool_call" in blob:
                used = True
                break
        if not used:
            chars = _content_chars(tools)
            out.append({
                "code": "unused_tool_definitions",
                "severity": "high" if chars > 8_000 else "medium",
                "detail": "%d tool definitions are attached and nothing in "
                          "this conversation has called one. They are sent in "
                          "full on every request."
                          % len(tools),
                "tokens": _est_tokens(chars),
                "certainty": "estimated from character count",
            })

    sys_chars = _content_chars(req.get("system"))
    if sys_chars > SYSTEM_FLAG_CHARS and depth > 4:
        out.append({
            "code": "large_system_prompt_resent",
            "severity": "low",
            "detail": "The system prompt is re-sent on every call in this "
                      "conversation. If your provider offers prompt caching, "
                      "this is the block to cache.",
            "tokens": _est_tokens(sys_chars),
            "certainty": "estimated from character count",
        })

    if ask:
        out.append({
            "code": "output_ceiling_authorised",
            "severity": "low",
            "detail": "max_tokens is set to %d, so this single call is "
                      "authorised to buy up to that many output tokens." % ask,
            "tokens": ask,
            "certainty": "exact ceiling set by the caller",
        })

    seen = {}
    for m in msgs:
        if not isinstance(m, dict):
            continue
        k = _sha(_canonical(m.get("content")))
        seen[k] = seen.get(k, 0) + 1
    dupes = sum(n - 1 for n in seen.values() if n > 1)
    if dupes >= 2:
        out.append({
            "code": "duplicate_turns_in_context",
            "severity": "medium",
            "detail": "%d turns inside this conversation are byte-identical "
                      "to an earlier turn. They are being paid for twice."
                      % dupes,
            "tokens": None,
            "certainty": "not counted",
        })

    if acct["ceiling"] and acct["spent"] >= acct["ceiling"] * 0.8:
        out.append({
            "code": "budget_nearly_gone",
            "severity": "high",
            "detail": "This key has used %d of its %d token ceiling."
                      % (acct["spent"], acct["ceiling"]),
            "tokens": None,
            "certainty": "exact, from provider-reported usage",
        })

    return out


# ================================================================ layers 1+2

def _decide(ctx, api_key, m, now, unattended, count_it):
    """
    Takes a measurement bundle from _measure or _measure_from_digest, so
    the same decision runs whether the caller sent the request or kept it
    at home and sent only its shape.

    rule is set only when a hard rule fired, in which case the score is
    still computed and reported but did not decide anything.
    """
    fp = m["fp"]
    shape = m["shape"]
    acct = _account(ctx, api_key)

    loop_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND fp=? AND ts > ?",
        (api_key, fp, now - LOOP_WINDOW)).fetchone()[0]
    burst_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND ts > ?",
        (api_key, now - W60)).fetchone()[0]
    grind_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND ts > ?",
        (api_key, now - W1H)).fetchone()[0]
    seen_shape = ctx.conn.execute(
        "SELECT 1 FROM ts_shape WHERE api_key=? AND shape=?",
        (api_key, shape)).fetchone()
    has_stored = ctx.conn.execute(
        "SELECT 1 FROM ts_store WHERE api_key=? AND fp=?",
        (api_key, fp)).fetchone() is not None

    chars = m["chars"]
    ask = m["ask"]
    depth = m["depth"]
    tools = m["tools"]

    # Worst case this one call could cost: an exact ceiling on output,
    # an estimate on input. Kept apart accordingly.
    ceiling_out = ask
    est_in = _est_tokens(chars)
    remaining = max(0, acct["ceiling"] - acct["spent"]) if acct["ceiling"] else 0
    if remaining:
        exposure = _linear(est_in + ceiling_out, remaining)
    else:
        exposure = 0.0

    s = {
        "exposure": round(exposure, 4),
        "size": round(_log_scale(chars, SAT_SIZE), 4),
        "ask": round(_log_scale(ask, SAT_ASK), 4),
        "depth": round(_linear(depth, SAT_DEPTH), 4),
        "tools": round(_linear(tools, SAT_TOOLS), 4),
        "loop": round(_linear(loop_n, SAT_LOOP), 4),
        "burst": round(_linear(burst_n, SAT_BURST), 4),
        "grind": round(_linear(grind_n, SAT_GRIND), 4),
        "novelty": 0.0 if seen_shape else 1.0,
    }

    score = (W_EXPOSURE * s["exposure"] + W_SIZE * s["size"]
             + W_ASK * s["ask"] + W_DEPTH * s["depth"]
             + W_TOOLS * s["tools"] + W_LOOP * s["loop"]
             + W_BURST * s["burst"] + W_GRIND * s["grind"]
             + W_NOVELTY * s["novelty"])

    s["unattended"] = bool(unattended)
    if unattended:
        score += W_UNATTENDED
    score = round(min(1.0, score), 4)

    measured = {
        "prompt_characters": chars,
        "estimated_input_tokens": est_in,
        "estimated_input_tokens_note": "estimated from characters, never "
                                       "counted in a savings total",
        "authorised_output_tokens": ceiling_out,
        "conversation_turns": depth,
        "tool_definitions": tools,
        "same_request_in_last_%ds" % LOOP_WINDOW: loop_n,
        "requests_in_last_60s": burst_n,
        "requests_in_last_hour": grind_n,
        "budget_ceiling_tokens": acct["ceiling"],
        "budget_spent_tokens": acct["spent"],
    }

    # ---- layer 1: hard rules, in order, no appeal to the score --------
    rule = None
    verdict = None

    if acct["ceiling"] and acct["spent"] >= acct["ceiling"]:
        rule, verdict = "budget_exhausted", "BLOCK"
    elif acct["ceiling"] and (est_in + ceiling_out) > remaining:
        # An overdraft. Catching this after the fact is too late: the
        # money is already gone. A person may raise the ceiling, so an
        # attended call is held rather than refused.
        rule = "exceeds_remaining_budget"
        verdict = "BLOCK" if unattended else "CHALLENGE"
    elif loop_n >= LOOP_HARD:
        rule, verdict = "runaway_loop", "BLOCK"
    elif unattended and loop_n >= LOOP_HARD_UNATTENDED:
        rule, verdict = "runaway_loop_unattended", "BLOCK"
    elif burst_n >= BURST_HARD:
        rule, verdict = "runaway_burst", "BLOCK"

    # ---- layer 2: the score -------------------------------------------
    if verdict is None:
        if score >= BAND_BLOCK:
            verdict = "BLOCK"
        elif score >= BAND_CHALLENGE:
            verdict = "CHALLENGE"
        elif (score < CHEAP_MAX_SCORE and chars <= CHEAP_MAX_CHARS
              and depth <= CHEAP_MAX_TURNS and ask <= CHEAP_MAX_ASK
              and tools == 0):
            verdict = "DOWNGRADE"
        else:
            verdict = "ALLOW"

    if count_it:
        ctx.conn.execute("INSERT INTO ts_seen (api_key, fp, ts) VALUES (?,?,?)",
                         (api_key, fp, now))
        ctx.conn.execute(
            "INSERT OR IGNORE INTO ts_shape (api_key, shape, first_ts) "
            "VALUES (?,?,?)", (api_key, shape, now))
        _prune(ctx, api_key, now)

    measured["measured_from"] = ("a digest supplied by the client; the "
                                "content stayed on their side"
                                if m.get("from_digest") else
                                "the request body")
    return (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
            est_in, ceiling_out, acct)


def _record_decision(ctx, api_key, fp, verdict, rule, score, signals,
                     ex_in, ex_out, ce_in, ce_out, seal_hash, now):
    """Writes the row and returns its id, so the receipt can be stamped on
    afterwards once the lock has been released."""
    cur = ctx.conn.execute(
        "INSERT INTO ts_decision (api_key, ts, fp, verdict, rule, score, "
        "signals, exact_in, exact_out, ceiling_in, ceiling_out, audit_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (api_key, now, fp, verdict, rule, score,
         json.dumps(signals, sort_keys=True), ex_in, ex_out, ce_in, ce_out,
         seal_hash))
    return cur.lastrowid


def _seal_and_stamp(ctx, event, detail, api_key, decision_id):
    """
    Seal with the lock released, then write the receipt back onto the row
    in a second short lock. Splitting it this way is what keeps the
    platform's non-reentrant lock from deadlocking the request.
    """
    seal = ctx.seal(event, detail, api_key)
    h = seal.get("hash") if isinstance(seal, dict) else None
    if h and decision_id:
        try:
            with ctx.lock:
                ctx.conn.execute(
                    "UPDATE ts_decision SET audit_hash=? WHERE id=?",
                    (h, decision_id))
                ctx.conn.commit()
        except Exception:                        # noqa: BLE001
            pass
    return seal


# --------------------------------------------------------------- actions

def _a_spec():
    return {
        "module": "tokensaver",
        "version": VERSION,
        "what_it_is": "A deterministic gate in front of a model. It decides "
                      "whether a request is answered from store, sent to the "
                      "model, sent to a cheaper model, held for a person, or "
                      "refused. It also names the waste inside every request "
                      "it sees.",
        "model_calls_made_to_reach_a_decision": 0,
        "layers": {
            "1_hard_rules": {
                "why": "A cost gate that depends only on tuned weights is a "
                       "cost gate nobody can defend. These are absolute.",
                "rules": {
                    "budget_exhausted": "spend has reached the key's ceiling",
                    "exceeds_remaining_budget":
                        "this one call could cost more than the budget left. "
                        "Output uses the exact ceiling you set; input is "
                        "estimated from characters, so this rule is "
                        "deliberately cautious. Held for a person when a "
                        "human is declared, refused when one is not.",
                    "runaway_loop": "the same request %d times in %d seconds"
                                    % (LOOP_HARD, LOOP_WINDOW),
                    "runaway_loop_unattended": "the same request %d times in "
                                               "%d seconds with no human "
                                               "declared"
                                               % (LOOP_HARD_UNATTENDED,
                                                  LOOP_WINDOW),
                    "runaway_burst": "%d requests from one key in 60 seconds"
                                     % BURST_HARD,
                },
            },
            "2_the_score": {
                "spend_signals": {
                    "exposure": {"weight": W_EXPOSURE,
                                 "measures": "worst case cost of this call "
                                             "against the budget left"},
                    "size": {"weight": W_SIZE, "saturates_at": SAT_SIZE,
                             "measures": "prompt characters, log scaled"},
                    "ask": {"weight": W_ASK, "saturates_at": SAT_ASK,
                            "measures": "the max_tokens ceiling the caller set"},
                    "depth": {"weight": W_DEPTH, "saturates_at": SAT_DEPTH,
                              "measures": "turns re-sent on every call"},
                    "tools": {"weight": W_TOOLS, "saturates_at": SAT_TOOLS,
                              "measures": "tool definitions re-sent on every call"},
                },
                "waste_signals": {
                    "loop": {"weight": W_LOOP, "saturates_at": SAT_LOOP},
                    "burst": {"weight": W_BURST, "saturates_at": SAT_BURST},
                    "grind": {"weight": W_GRIND, "saturates_at": SAT_GRIND},
                    "novelty": {"weight": W_NOVELTY},
                },
                "spend_weight_total": round(W_EXPOSURE + W_SIZE + W_ASK
                                            + W_DEPTH + W_TOOLS, 4),
                "waste_weight_total": round(W_LOOP + W_BURST + W_GRIND
                                            + W_NOVELTY, 4),
                "base_weights_sum_to": round(BASE_SUM, 4),
                "outside_the_base_sum": {"unattended": W_UNATTENDED},
                "bands": {"CHALLENGE": ">= %.2f" % BAND_CHALLENGE,
                          "BLOCK": ">= %.2f" % BAND_BLOCK},
                "downgrade_is_earned_not_suspected": {
                    "max_score": CHEAP_MAX_SCORE,
                    "max_prompt_characters": CHEAP_MAX_CHARS,
                    "max_turns": CHEAP_MAX_TURNS,
                    "max_output_tokens": CHEAP_MAX_ASK,
                    "tools_allowed": 0,
                    "why": "a suspicious request is never sent to a weaker "
                           "model. Only a genuinely small one is.",
                },
            },
            "3_findings": {
                "why": "The verdict saves money on this call. The findings "
                       "change what the caller sends next time, which saves "
                       "far more.",
                "codes": ["repeating_without_recording",
                          "varied_output_blocks_reuse",
                          "carrying_old_turns",
                          "unused_tool_definitions",
                          "large_system_prompt_resent",
                          "output_ceiling_authorised",
                          "duplicate_turns_in_context",
                          "budget_nearly_gone"],
            },
        },
        "verdict_vocabulary": VOCABULARY,
        "certainty_tiers": {
            "tokens_not_bought": "exact, provider reported, the only figure "
                                 "that enters a savings total",
            "worst_case_tokens_avoided": "a ceiling on what a refused request "
                                         "could have cost, reported separately",
            "findings_tokens": "estimated from characters where marked, never "
                               "entering any total",
        },
        "two_ways_to_call_it": {
            "request": "send the provider request body. This platform sees "
                       "your prompt.",
            "digest": "send only a fingerprint and counts. Your prompts and "
                      "answers never leave your building, the decision is "
                      "identical, and the receipt is the same. The downloaded "
                      "client uses this path by default.",
        },
        "honest_limits": LIMITS,
        "routes": {
            "public": ["spec", "stats", "verify"],
            "keyed": ["estimate", "gate", "record", "ledger", "budget",
                      "prices", "forget"],
        },
    }


def _bundle(data):
    """
    A caller may send the whole request, or only a digest of it. The
    digest path exists so a customer's prompts and answers never leave
    their own building. Returns (measurements, request_or_None, error, code).
    """
    req = data.get("request")
    if isinstance(req, dict):
        if _prompt_chars(req) > MAX_PROMPT_CHARS:
            return None, None, {"error": "request_too_large"}, 413
        return _measure(req), req, None, None

    dig = data.get("digest")
    if dig is not None:
        m, err = _measure_from_digest(dig)
        if err:
            return None, None, {"error": "bad_digest", "detail": err}, 400
        return m, None, None, None

    return None, None, {
        "error": "request_or_digest_required",
        "detail": "send the provider request body under 'request', or a "
                  "content-free digest under 'digest' with fingerprint, "
                  "prompt_characters, max_tokens, conversation_turns, "
                  "tool_definitions and deterministic",
    }, 400


def _digest_findings(m, loop_n, has_stored, acct):
    """
    What can honestly be said when the content stayed at home. Anything
    needing the actual messages is left to the client, which has them.
    """
    out = []
    if loop_n >= 2 and not has_stored:
        out.append({
            "code": "repeating_without_recording",
            "severity": "high",
            "detail": "This exact request has gone out %d times in the last "
                      "%d seconds and no answer has been recorded. Post the "
                      "response back to record and every repeat after that "
                      "costs nothing." % (loop_n, LOOP_WINDOW),
            "tokens": None,
            "certainty": "not counted",
        })
    if not m["deterministic"]:
        out.append({
            "code": "varied_output_blocks_reuse",
            "severity": "medium",
            "detail": "temperature is above zero, so this answer cannot be "
                      "safely reused.",
            "tokens": None,
            "certainty": "not counted",
        })
    if m["depth"] > CTX_FLAG_TURNS:
        out.append({
            "code": "carrying_old_turns",
            "severity": "medium",
            "detail": "%d turns are being re-sent on every call. Your client "
                      "holds the content and can size this exactly."
                      % m["depth"],
            "tokens": None,
            "certainty": "not counted here; the client can measure it",
        })
    if m["ask"]:
        out.append({
            "code": "output_ceiling_authorised",
            "severity": "low",
            "detail": "max_tokens is set to %d, so this call is authorised "
                      "to buy up to that many output tokens." % m["ask"],
            "tokens": m["ask"],
            "certainty": "exact ceiling set by the caller",
        })
    if acct["ceiling"] and acct["spent"] >= acct["ceiling"] * 0.8:
        out.append({
            "code": "budget_nearly_gone",
            "severity": "high",
            "detail": "This key has used %d of its %d token ceiling."
                      % (acct["spent"], acct["ceiling"]),
            "tokens": None,
            "certainty": "exact, from provider-reported usage",
        })
    return out


def _a_estimate(ctx, api_key, data, now):
    """Cost a request and name its waste. Changes nothing, seals nothing."""
    m, req, err, code = _bundle(data)
    if err:
        return err, code

    with ctx.lock:
        (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
         est_in, ceil_out, acct) = _decide(
            ctx, api_key, m, now, bool(data.get("unattended")), False)
        findings = (_findings(req, loop_n, has_stored, acct) if req
                    else _digest_findings(m, loop_n, has_stored, acct))
        stored = has_stored

    money = _money(est_in, ceil_out, acct["price_in"], acct["price_out"])
    out = {
        "would_be": verdict,
        "rule": rule,
        "score": score,
        "signals": s,
        "measured": measured,
        "findings": findings,
        "fingerprint": fp,
        "stored_answer_available": stored,
        "worst_case_cost": {
            "estimated_input_tokens": est_in,
            "authorised_output_tokens": ceil_out,
            "certainty": "input estimated from characters; output is the "
                         "exact ceiling you set",
        },
        "note": "estimate changes nothing, counts towards no velocity window "
                "and seals nothing. Use gate for the real decision.",
    }
    if money is not None:
        out["worst_case_cost"]["money_at_your_prices"] = money
        out["worst_case_cost"]["currency"] = acct["currency"]
    return out, 200


def _a_gate(ctx, api_key, data, now):
    m, req, err, code = _bundle(data)
    if err:
        return err, code

    unattended = bool(data.get("unattended"))
    fp = m["fp"]

    # ---- everything that touches the database, under the lock ----------
    with ctx.lock:
        row = ctx.conn.execute(
            "SELECT response, model, input_tokens, output_tokens, hits, "
            "expires_at FROM ts_store WHERE api_key=? AND fp=?",
            (api_key, fp)).fetchone()

        expired = False
        if row and row[5] is not None and row[5] < now:
            ctx.conn.execute("DELETE FROM ts_store WHERE api_key=? AND fp=?",
                             (api_key, fp))
            expired = True
            row = None

        acct = _account(ctx, api_key)
        budget_gone = bool(acct["ceiling"]) and acct["spent"] >= acct["ceiling"]

        client_held = False
        if row:
            try:
                client_held = (json.loads(row[0]).get("held_by") == "client")
            except (ValueError, AttributeError):
                client_held = False

        served = bool(row) and not budget_gone
        if served:
            ctx.conn.execute(
                "UPDATE ts_store SET hits=hits+1, last_hit=? "
                "WHERE api_key=? AND fp=?", (now, api_key, fp))
            did = _record_decision(
                ctx, api_key, fp, "SERVE",
                "stored_by_client" if client_held else "stored_answer",
                0.0, {"repeat": 1.0}, row[2], row[3], None, None, None, now)
        else:
            (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
             est_in, ceil_out, acct) = _decide(ctx, api_key, m, now,
                                               unattended, True)
            findings = (_findings(req, loop_n, has_stored, acct) if req
                        else _digest_findings(m, loop_n, has_stored, acct))
            ce_in = est_in if verdict == "BLOCK" else None
            ce_out = ceil_out if verdict == "BLOCK" else None
            did = _record_decision(ctx, api_key, fp, verdict, rule, score, s,
                                   None, None, ce_in, ce_out, None, now)
        ctx.conn.commit()

    # ---- sealing happens with the lock RELEASED -------------------------
    # The platform's seal takes the same lock, and it is not reentrant.
    # Calling it from inside the block above deadlocks the request.
    if expired:
        ctx.seal("tokensaver_expired",
                 {"module": "tokensaver", "fingerprint": fp}, api_key)

    if served:
        detail = {
            "module": "tokensaver", "verdict": "SERVE", "fingerprint": fp,
            "model": row[1],
            "tokens_not_bought": {"input": row[2], "output": row[3]},
            "usage_reported_by_provider": (row[2] is not None
                                           or row[3] is not None),
            "hit_number": row[4] + 1,
        }
        if client_held:
            detail["content_held_by"] = "client"
        seal = _seal_and_stamp(ctx, "tokensaver_serve", detail, api_key, did)

        known = (row[2] is not None or row[3] is not None)
        out = {
            "verdict": "SERVE",
            "meaning": VOCABULARY["SERVE"],
            "call_the_model": False,
            "fingerprint": fp,
            "tokens_not_bought": {
                "input": row[2], "output": row[3],
                "total": ((row[2] or 0) + (row[3] or 0)) if known else None,
                "certainty": "exact, as reported by the provider on the "
                             "original call" if known else
                             "the provider reported no usage on the original "
                             "call, so this saving is real but its size is "
                             "unknown",
            },
            "hit_number": row[4] + 1,
            "receipt": seal,
        }
        if client_held:
            out["content_held_by"] = "client"
            out["serve_from_your_own_store"] = True
        else:
            out["response"] = json.loads(row[0])
        money = _money(row[2], row[3], acct["price_in"], acct["price_out"])
        if money is not None:
            out["money_not_spent_at_your_prices"] = money
            out["currency"] = acct["currency"]
        return out, 200

    detail = {
        "module": "tokensaver", "verdict": verdict, "rule": rule,
        "score": score, "fingerprint": fp, "signals": s,
        "measured": measured, "findings": [f["code"] for f in findings],
    }
    seal = _seal_and_stamp(ctx, "tokensaver_decision", detail, api_key, did)

    out = {
        "verdict": verdict,
        "meaning": VOCABULARY[verdict],
        "decided_by": ("hard rule: " + rule) if rule else "score",
        "rule": rule,
        "score": score,
        "signals": s,
        "measured": measured,
        "findings": findings,
        "fingerprint": fp,
        "call_the_model": verdict in ("ALLOW", "DOWNGRADE"),
        "use_cheap_model": verdict == "DOWNGRADE",
        "receipt": seal,
    }
    if verdict == "BLOCK":
        money = _money(est_in, ceil_out, acct["price_in"], acct["price_out"])
        out["worst_case_avoided"] = {
            "estimated_input_tokens": est_in,
            "authorised_output_tokens": ceil_out,
            "certainty": "a ceiling, not a saving. Nobody knows what this "
                         "call would actually have cost, so it is reported "
                         "separately and never added to tokens not bought.",
        }
        if money is not None:
            out["worst_case_avoided"]["money_at_your_prices"] = money
    if verdict in ("ALLOW", "DOWNGRADE"):
        out["next"] = ("call the model, then POST the response to "
                       "/x/tokensaver/record so the next identical request "
                       "costs nothing")
    return out, 200


def _a_record(ctx, api_key, data, now):
    req = data.get("request")
    resp = data.get("response")
    dig = data.get("digest")

    # Content-free path: the client stored the answer at home and is only
    # reporting what it cost, so the budget and the totals stay true.
    if not isinstance(req, dict) and isinstance(dig, dict):
        m, err = _measure_from_digest(dig)
        if err:
            return {"error": "bad_digest", "detail": err}, 400
        u = data.get("usage") or {}
        try:
            t_in = (int(u["input_tokens"])
                    if u.get("input_tokens") is not None else None)
            t_out = (int(u["output_tokens"])
                     if u.get("output_tokens") is not None else None)
        except (TypeError, ValueError):
            return {"error": "usage_must_be_whole_numbers"}, 400
        with ctx.lock:
            if t_in is not None or t_out is not None:
                _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
            ctx.conn.execute(
                "INSERT OR REPLACE INTO ts_store (api_key, fp, model, "
                "response, input_tokens, output_tokens, stored_at, "
                "expires_at, hits, last_hit) VALUES (?,?,?,?,?,?,?,?,0,NULL)",
                (api_key, m["fp"], dig.get("model"),
                 json.dumps({"held_by": "client",
                             "note": "the answer is stored on the customer's "
                                     "own machine and never came here"}),
                 t_in, t_out, now, now + DEFAULT_TTL))
            ctx.conn.commit()
        seal = ctx.seal("tokensaver_store", {
            "module": "tokensaver", "fingerprint": m["fp"],
            "model": dig.get("model"), "content_held_by": "client",
            "usage_reported_by_provider": (t_in is not None
                                           or t_out is not None),
            "input_tokens": t_in, "output_tokens": t_out}, api_key)
        return {"stored": True, "fingerprint": m["fp"],
                "content_held_by": "client", "input_tokens": t_in,
                "output_tokens": t_out, "receipt": seal,
                "note": "the cost is on the record here; the answer itself "
                        "stayed on your machine"}, 200

    if not isinstance(req, dict) or not isinstance(resp, dict):
        return {"error": "request_and_response_required",
                "detail": "send request and response, or a digest with usage"}, 400

    body = json.dumps(resp)
    if len(body.encode("utf-8")) > MAX_STORED_BYTES:
        return {"error": "response_too_large",
                "limit_bytes": MAX_STORED_BYTES}, 413

    fp = _fingerprint(req)
    t_in, t_out = _usage(resp)

    if not _deterministic(req) and not data.get("store_varied"):
        with ctx.lock:
            if t_in is not None or t_out is not None:
                _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
            ctx.conn.commit()
        ctx.seal("tokensaver_refused_to_store", {
            "module": "tokensaver", "fingerprint": fp,
            "reason": "temperature above zero; serving a stored answer "
                      "would change how the system behaves"}, api_key)
        return {
            "stored": False,
            "spend_recorded": (t_in is not None or t_out is not None),
            "reason": "temperature is above zero. Serving a stored answer to "
                      "a request that asked for varied output would change "
                      "how your system behaves. Send store_varied true to "
                      "override deliberately.",
        }, 200

    ttl = data.get("ttl_seconds", DEFAULT_TTL)
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL
    expires = now + ttl if ttl > 0 else None

    with ctx.lock:
        ctx.conn.execute(
            "INSERT OR REPLACE INTO ts_store (api_key, fp, model, response, "
            "input_tokens, output_tokens, stored_at, expires_at, hits, "
            "last_hit) VALUES (?,?,?,?,?,?,?,?,0,NULL)",
            (api_key, fp, req.get("model"), body, t_in, t_out, now, expires))
        if t_in is not None or t_out is not None:
            _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_store", {
        "module": "tokensaver", "fingerprint": fp, "model": req.get("model"),
        "usage_reported_by_provider": (t_in is not None or t_out is not None),
        "input_tokens": t_in, "output_tokens": t_out}, api_key)

    return {
        "stored": True,
        "fingerprint": fp,
        "usage_reported_by_provider": (t_in is not None or t_out is not None),
        "input_tokens": t_in,
        "output_tokens": t_out,
        "receipt": seal,
        "note": "the next identical request will be served from store and "
                "will buy nothing"
                if (t_in is not None or t_out is not None) else
                "stored, but the provider reported no usage, so future "
                "savings on this request will be real without a known size",
    }, 200


def _spend(ctx, api_key, tokens, now):
    ctx.conn.execute(
        "INSERT INTO ts_account (api_key, ceiling, spent, updated) "
        "VALUES (?,0,?,?) ON CONFLICT(api_key) DO UPDATE SET "
        "spent = spent + ?, updated = ?",
        (api_key, tokens, now, tokens, now))


def _totals(ctx, api_key=None):
    where = "WHERE api_key=?" if api_key else ""
    args = (api_key,) if api_key else ()

    rows = ctx.conn.execute(
        "SELECT hits, input_tokens, output_tokens FROM ts_store " + where,
        args).fetchall()
    exact_in = exact_out = unknown = 0
    for h, i, o in rows:
        if i is None and o is None:
            unknown += h
            continue
        exact_in += (i or 0) * h
        exact_out += (o or 0) * h

    counts = {}
    for v, c in ctx.conn.execute(
            "SELECT verdict, COUNT(*) FROM ts_decision " + where
            + " GROUP BY verdict", args).fetchall():
        counts[v] = c

    crow = ctx.conn.execute(
        "SELECT COALESCE(SUM(ceiling_in),0), COALESCE(SUM(ceiling_out),0) "
        "FROM ts_decision " + (where + " AND " if where else "WHERE ")
        + "verdict='BLOCK'", args).fetchone()

    rules = {}
    for r, c in ctx.conn.execute(
            "SELECT rule, COUNT(*) FROM ts_decision "
            + (where + " AND " if where else "WHERE ")
            + "rule IS NOT NULL GROUP BY rule", args).fetchall():
        rules[r] = c

    total = sum(counts.values())
    served = counts.get("SERVE", 0)

    return {
        "decisions": total,
        "verdicts": counts,
        "hard_rules_fired": rules,
        "serve_rate_percent": round(100.0 * served / total, 2) if total else 0.0,
        "tokens_not_bought": {
            "input": exact_in,
            "output": exact_out,
            "total": exact_in + exact_out,
            "certainty": "exact. Provider-reported counts on requests served "
                         "from store.",
        },
        "worst_case_tokens_avoided": {
            "estimated_input": crow[0],
            "authorised_output": crow[1],
            "certainty": "a ceiling on refused requests, not a saving. Never "
                         "added to tokens not bought.",
        },
        "serves_with_no_usage_reported": unknown,
        "stored_answers": len(rows),
    }


def _a_stats(ctx):
    with ctx.lock:
        t = _totals(ctx)
    t["version"] = VERSION
    t["model_calls_made_to_reach_a_decision"] = 0
    t["note"] = ("No figure here is a percentage saved. Exact savings and "
                 "worst case ceilings are reported apart and never summed.")
    return t, 200


def _a_ledger(ctx, api_key, data, now):
    try:
        limit = min(200, max(1, int(data.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    with ctx.lock:
        rows = ctx.conn.execute(
            "SELECT ts, fp, verdict, rule, score, exact_in, exact_out, "
            "ceiling_in, ceiling_out, audit_hash FROM ts_decision "
            "WHERE api_key=? ORDER BY id DESC LIMIT ?",
            (api_key, limit)).fetchall()
        totals = _totals(ctx, api_key)
        acct = _account(ctx, api_key)

    out = {
        "totals": totals,
        "budget": {
            "ceiling_tokens": acct["ceiling"],
            "spent_tokens": acct["spent"],
            "remaining_tokens": max(0, acct["ceiling"] - acct["spent"])
                                if acct["ceiling"] else None,
            "note": "no ceiling set; set one with budget"
                    if not acct["ceiling"] else None,
        },
        "recent": [{
            "ts": r[0], "fingerprint": r[1], "verdict": r[2], "rule": r[3],
            "score": r[4],
            "tokens_not_bought": ((r[5] or 0) + (r[6] or 0))
                                 if r[2] == "SERVE" else 0,
            "worst_case_avoided": ((r[7] or 0) + (r[8] or 0))
                                  if r[2] == "BLOCK" else 0,
            "receipt": r[9],
        } for r in rows],
    }
    m = _money(totals["tokens_not_bought"]["input"],
               totals["tokens_not_bought"]["output"],
               acct["price_in"], acct["price_out"])
    if m is not None:
        out["money_not_spent_at_your_prices"] = m
        out["currency"] = acct["currency"]
        out["money_note"] = ("calculated only from provider-reported counts "
                             "on requests served from store, at the prices "
                             "you supplied")
    return out, 200


def _a_budget(ctx, api_key, data, now):
    if "ceiling_tokens" not in data:
        return {"error": "ceiling_tokens_required",
                "detail": "the number of tokens this key may spend before "
                          "every request is refused"}, 400
    try:
        ceiling = int(data["ceiling_tokens"])
    except (TypeError, ValueError):
        return {"error": "ceiling_tokens_must_be_a_whole_number"}, 400
    if ceiling < 0:
        return {"error": "ceiling_tokens_must_not_be_negative"}, 400

    reset = bool(data.get("reset_spent"))
    with ctx.lock:
        ctx.conn.execute(
            "INSERT INTO ts_account (api_key, ceiling, spent, updated) "
            "VALUES (?,?,0,?) ON CONFLICT(api_key) DO UPDATE SET "
            "ceiling=?, updated=?", (api_key, ceiling, now, ceiling, now))
        if reset:
            ctx.conn.execute("UPDATE ts_account SET spent=0 WHERE api_key=?",
                             (api_key,))
        acct = _account(ctx, api_key)
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_budget", {
        "module": "tokensaver", "ceiling_tokens": ceiling,
        "spent_reset": reset}, api_key)

    return {"ceiling_tokens": acct["ceiling"], "spent_tokens": acct["spent"],
            "receipt": seal,
            "note": "when spent reaches the ceiling, every request is refused "
                    "before it reaches the model"}, 200


def _a_prices(ctx, api_key, data, now):
    """Prices come from the customer's own contract. Never assumed."""
    pi = data.get("price_per_million_input")
    po = data.get("price_per_million_output")
    if pi is None and po is None:
        return {"error": "prices_required",
                "detail": "send price_per_million_input and/or "
                          "price_per_million_output from your own provider "
                          "contract. Nothing is assumed on your behalf."}, 400
    try:
        pi = float(pi) if pi is not None else None
        po = float(po) if po is not None else None
    except (TypeError, ValueError):
        return {"error": "prices_must_be_numbers"}, 400
    if (pi is not None and pi < 0) or (po is not None and po < 0):
        return {"error": "prices_must_not_be_negative"}, 400

    cur = (data.get("currency") or "").strip()[:8] or None
    with ctx.lock:
        ctx.conn.execute(
            "INSERT INTO ts_account (api_key, ceiling, spent, price_in, "
            "price_out, currency, updated) VALUES (?,0,0,?,?,?,?) "
            "ON CONFLICT(api_key) DO UPDATE SET price_in=?, price_out=?, "
            "currency=?, updated=?",
            (api_key, pi, po, cur, now, pi, po, cur, now))
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_prices", {
        "module": "tokensaver", "price_per_million_input": pi,
        "price_per_million_output": po, "currency": cur}, api_key)

    return {"price_per_million_input": pi, "price_per_million_output": po,
            "currency": cur, "receipt": seal,
            "note": "money figures now appear alongside token figures. They "
                    "are your prices applied to provider-reported counts, "
                    "never an assumption about what you pay."}, 200


def _a_forget(ctx, api_key, data, now):
    fp = data.get("fingerprint")
    req = data.get("request")
    if not fp and isinstance(req, dict):
        fp = _fingerprint(req)
    if not fp:
        return {"error": "fingerprint_or_request_required"}, 400

    with ctx.lock:
        cur = ctx.conn.execute(
            "DELETE FROM ts_store WHERE api_key=? AND fp=?", (api_key, fp))
        removed = cur.rowcount
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_forget", {
        "module": "tokensaver", "fingerprint": fp, "removed": removed},
        api_key)

    return {"removed": removed, "fingerprint": fp, "receipt": seal,
            "note": "the stored answer is gone. Decisions already sealed "
                    "stay sealed."}, 200


def _a_verify(ctx, data):
    h = data.get("receipt") or data.get("hash")
    if not h:
        return {"error": "receipt_required",
                "detail": "pass ?receipt=<chain hash from a decision>"}, 400
    with ctx.lock:
        row = ctx.conn.execute(
            "SELECT ts, verdict, rule, score, exact_in, exact_out, "
            "ceiling_in, ceiling_out, fp FROM ts_decision WHERE audit_hash=?",
            (h,)).fetchone()
    if not row:
        return {"found": False, "receipt": h,
                "note": "no decision on this platform carries that receipt"}, 404
    return {
        "found": True,
        "receipt": h,
        "ts": row[0],
        "verdict": row[1],
        "meaning": VOCABULARY.get(row[1], row[1]),
        "decided_by": ("hard rule: " + row[2]) if row[2] else "score",
        "score": row[3],
        "tokens_not_bought": ((row[4] or 0) + (row[5] or 0))
                             if row[1] == "SERVE" else 0,
        "worst_case_avoided": ((row[6] or 0) + (row[7] or 0))
                              if row[1] == "BLOCK" else 0,
        "fingerprint": row[8],
        "what_this_proves": "that this decision was sealed into the chain "
                            "with these values at this position.",
        "what_this_does_not_prove": "that a stored answer is still correct, "
                                    "or what a refused request would actually "
                                    "have cost.",
    }, 200


# ---------------------------------------------------------------- handler
# ---------------------------------------------------------------- the ctx

def _fallback_conn():
    global _FALLBACK_CONN
    with _FALLBACK_LOCK:
        if _FALLBACK_CONN is None:
            _FALLBACK_CONN = sqlite3.connect("tokensaver.db",
                                             check_same_thread=False)
            _FALLBACK_CONN.execute("PRAGMA journal_mode=WAL")
        return _FALLBACK_CONN


class _Bridge:
    """
    A router may hand a module a context object, or a plain dict. Rather
    than assume which, find what is actually needed: something that can
    run SQL, something that can be held, and something that can seal.

    Anything missing is reported honestly in the response instead of
    being faked.
    """

    def __init__(self, raw):
        self.raw = raw
        self.conn = self._find(
            lambda v: hasattr(v, "execute") and hasattr(v, "commit"),
            ("conn", "db", "_conn", "_db", "database", "sql", "sqlite"))
        self.lock = self._find(
            lambda v: hasattr(v, "acquire") and hasattr(v, "release"),
            ("lock", "db_lock", "_db_lock", "_lock", "mutex"))
        # A sqlite3 Connection is itself callable, so "anything callable"
        # is not a safe test for a seal function - it would quietly pick the
        # database. Require an actual function or method.
        self._seal = self._find(
            lambda v: (inspect.isroutine(v)
                       and v is not self.conn and v is not self.lock),
            ("seal", "seal_fn", "seal_block", "add_block", "chain_seal",
             "append_block"))
        self.notes = []

        if self.conn is None:
            # Last resort so the module still answers rather than 500s.
            self.conn = _fallback_conn()
            self.notes.append("no database was found in the router context, so "
                              "this module opened its own file")
        if self.lock is None:
            self.lock = _FALLBACK_LOCK
            self.notes.append("no lock was found in the router context, so "
                              "this module used its own")
        if self._seal is None:
            self.notes.append("no seal function was found in the router "
                              "context, so decisions are recorded but not "
                              "sealed into the platform chain")

    def _find(self, test, names):
        raw = self.raw
        if isinstance(raw, dict):
            for n in names:                      # preferred names first
                if n in raw and raw[n] is not None:
                    try:
                        if test(raw[n]):
                            return raw[n]
                    except Exception:            # noqa: BLE001
                        pass
            for v in raw.values():               # then anything that fits
                try:
                    if v is not None and test(v):
                        return v
                except Exception:                # noqa: BLE001
                    pass
            return None
        for n in names:
            v = getattr(raw, n, None)
            if v is not None:
                try:
                    if test(v):
                        return v
                except Exception:                # noqa: BLE001
                    pass
        return None

    def seal(self, event, detail, api_key=None):
        """
        MUST NOT be called while holding self.lock. The platform's own seal
        takes that same lock, and it is a plain Lock rather than a reentrant
        one, so calling it from inside a held lock deadlocks the request.
        """
        if self._seal is None:
            return {"sealed": False,
                    "reason": "the platform chain was not reachable from this "
                              "module"}

        ev = {"user_id": "tokensaver", "action": str(event), "amount": 0,
              "country": "UK", "device_id": "module", "anomaly": 0,
              "device_risk": 0}
        now = time.time()

        attempts = (
            lambda: self._seal(ev, detail, now, api_key),
            lambda: self._seal(ev, detail, now),
            lambda: self._seal(event, detail),
            lambda: self._seal({"event": event, "detail": detail}),
        )
        r = None
        last = None
        for call in attempts:
            try:
                r = call()
                break
            except TypeError as e:
                last = e
                continue
            except Exception as e:               # noqa: BLE001
                return {"sealed": False, "reason": str(e)}
        if r is None:
            return {"sealed": False,
                    "reason": "could not match the chain's seal signature: "
                              + str(last)}

        if isinstance(r, dict):
            return r
        if isinstance(r, str):
            return {"hash": r}
        if isinstance(r, (list, tuple)) and r:
            out = {"hash": str(r[0])}
            if len(r) > 1 and r[1] is not None:
                out["block_index"] = r[1]
            if len(r) > 2 and r[2] is not None:
                out["key_seq"] = r[2]
            return out
        return {"sealed": True}


_FALLBACK_LOCK = threading.RLock()
_FALLBACK_CONN = None


def _bridge(raw):
    """
    Built fresh every call on purpose. Caching it by id() is unsafe:
    Python recycles ids once an object is collected, so a cached bridge
    can end up serving a different request's context.
    """
    if isinstance(raw, _Bridge):
        return raw
    return _Bridge(raw)


def handle(method, action, data, api_key, ctx):
    ctx = _bridge(ctx)
    _init(ctx)
    data = data or {}
    now = time.time()

    if method == "GET" and action == "spec":
        sp = _a_spec()
        if ctx.notes:
            sp["wiring_notes"] = ctx.notes
        return sp, 200
    if method == "GET" and action == "stats":
        return _a_stats(ctx)
    if method == "GET" and action == "verify":
        return _a_verify(ctx, data)

    if not api_key:
        return {"error": "key_required"}, 401

    if method == "POST" and action == "estimate":
        return _a_estimate(ctx, api_key, data, now)
    if method == "POST" and action == "gate":
        return _a_gate(ctx, api_key, data, now)
    if method == "POST" and action == "record":
        return _a_record(ctx, api_key, data, now)
    if method == "GET" and action == "ledger":
        return _a_ledger(ctx, api_key, data, now)
    if method == "POST" and action == "budget":
        return _a_budget(ctx, api_key, data, now)
    if method == "POST" and action == "prices":
        return _a_prices(ctx, api_key, data, now)
    if method == "POST" and action == "forget":
        return _a_forget(ctx, api_key, data, now)

    return {"error": "unknown_action",
            "actions": ["spec", "stats", "verify", "estimate", "gate",
                        "record", "ledger", "budget", "prices", "forget"]}, 404

```
