"""
Conformance testing - /x/conformance/<action>

WHAT THIS IS FOR
----------------
Three limits are documented elsewhere in this platform, and all three have
the same shape: the engine's arithmetic is sound, but the guarantee depends
on something outside the engine.

  1. Commit-before-reveal proves order - but only if the integrator does not
     show its reviewers the machine verdict before calling /open.
  2. Mutual witnessing gets its strength from breadth - two platforms
     witnessing only each other prove very little.
  3. A declaration is only as strong as the rules declared - one that
     constrains nothing passes everything.

None of these can be fixed by the engine on its own. All three can be
MEASURED, and a measured weakness is a different animal from an unmeasured
one. That is what this module does.

1. PROBES - testing the integration, not trusting it
----------------------------------------------------
The idea is borrowed openly from how real audits work, and specifically from
a point James Stokes made publicly: slip a case with a known answer into the
queue, unannounced, and see who catches it.

A probe creates a genuine oversight case whose machine verdict is
deliberately set to a known-wrong value. The reviewer sees it exactly like
any other case. Two things then follow:

  - If they agree with the deliberately wrong verdict, they did not evaluate
    it. That is a caught rubber stamp, sealed.
  - If the integration is showing them the verdict before /open is called,
    their probe agreement rate will match their normal agreement rate. If
    they are genuinely deciding blind, it will not. The gap between the two
    numbers is the conformance signal.

A single probe proves nothing about a person. A catch rate across dozens is
evidence about a process, which is the thing under audit.

2. WITNESS BREADTH - concentration is visible
---------------------------------------------
Reports how many distinct peers witness the chain, how concentrated the
observations are in the largest peer, and how many peers have gone quiet.
Below three live peers the network is reported as weak, because it is.

3. DECLARATION STRENGTH - rules that never fire
------------------------------------------------
Runs the live declaration against sealed records and reports, per rule, how
many records it actually CONSTRAINED - that is, how many matched its `when`
condition and therefore had to satisfy its `require`. A rule that has never
constrained a single record is not a standard. It is decoration, and it is
named as such.

HONEST LIMITS OF THIS MODULE
----------------------------
- Probes test the process, not any individual. Someone can catch a probe and
  still rubber stamp the next hundred cases.
- A determined integrator who identifies probe cases can treat them
  differently. Probe case references are not marked in any way the reviewer
  can see, but a sufficiently motivated operator controls their own UI.
- Breadth and strength are measurements, not enforcement. Nothing here can
  compel a platform to witness widely or declare strictly. It can only make
  the alternative visible.

    POST /x/conformance/probe        inject a probe case with a known-wrong verdict
    GET  /x/conformance/probes       catch rate, and the conformance gap
    GET  /x/conformance/witness      breadth, concentration, staleness
    GET  /x/conformance/declaration  per-rule strength - what each rule constrains
    GET  /x/conformance/report       all three, one call
"""

import importlib, json, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
INVERT = {"allow": "block", "block": "allow",
          "challenge": "allow", "escalate": "allow"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS conformance_probes(probe_id TEXT PRIMARY KEY,api_key TEXT,case_id TEXT,reviewer TEXT,planted_verdict TEXT,correct_verdict TEXT,injected REAL,resolved REAL,reviewer_verdict TEXT,caught INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_probe_key ON conformance_probes(api_key)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ------------------------------------------------------------------ probes

def _probe(ctx, api_key, data):
    reviewer = str(data.get("reviewer", "")).strip()
    if not reviewer:
        return {"error": "reviewer_required"}, 400
    correct = str(data.get("correct_verdict", "")).strip().lower()
    if correct not in INVERT:
        return {"error": "correct_verdict_required",
                "allowed": sorted(INVERT)}, 400
    material = data.get("material")
    if material is None:
        return {"error": "material_required",
                "message": "A probe must look like a real case or it tests nothing."}, 400

    planted = INVERT[correct]
    try:
        ovs = importlib.import_module("modules.oversight")
    except Exception as e:
        return {"error": "oversight_module_unavailable", "detail": str(e)}, 503

    ref = str(data.get("case_ref", "")).strip() or ("CASE-" + secrets.token_hex(3).upper())
    payload, status = ovs.handle("POST", "open",
                                 {"case_ref": ref, "reviewer": reviewer,
                                  "material": material,
                                  "machine_verdict": planted},
                                 api_key, ctx)
    if status != 200:
        return payload, status

    pid = "PRB-" + secrets.token_hex(4).upper()
    ts = time.time()
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO conformance_probes(probe_id,api_key,case_id,reviewer,planted_verdict,correct_verdict,injected,resolved,reviewer_verdict,caught) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL)",
                            (pid, api_key, payload["case_id"], reviewer, planted, correct, ts))
        ctx["conn"].commit()

    return {"probe_id": pid, "case_id": payload["case_id"],
            "case_ref": ref, "reviewer": reviewer,
            "planted_verdict": planted, "correct_verdict": correct,
            "injected": _iso(ts),
            "note": "This is an ordinary oversight case to the reviewer. Route it into their queue exactly like any other, or the probe is worthless."}, 200


def _resolve_probes(ctx, api_key):
    """Settle any probes whose oversight case has since been committed."""
    with ctx["lock"]:
        open_probes = ctx["conn"].execute("SELECT probe_id,case_id,planted_verdict,correct_verdict FROM conformance_probes WHERE api_key=? AND resolved IS NULL", (api_key,)).fetchall()
        for pid, cid, planted, correct in open_probes:
            row = ctx["conn"].execute("SELECT reviewer_verdict,committed FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
            if not row or not row[1]:
                continue
            rv = (row[0] or "").lower()
            caught = 1 if rv != planted else 0
            ctx["conn"].execute("UPDATE conformance_probes SET resolved=?,reviewer_verdict=?,caught=? WHERE probe_id=?",
                                (row[1], rv, caught, pid))
        ctx["conn"].commit()


def _probes(ctx, api_key):
    try:
        _resolve_probes(ctx, api_key)
    except Exception:
        pass
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT reviewer,caught,resolved FROM conformance_probes WHERE api_key=? AND resolved IS NOT NULL", (api_key,)).fetchall()
        pending = ctx["conn"].execute("SELECT COUNT(*) FROM conformance_probes WHERE api_key=? AND resolved IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"probes_resolved": 0, "probes_pending": pending,
                "note": "No probes have come back yet."}, 200

    by = {}
    for reviewer, caught, _r in rows:
        d = by.setdefault(reviewer, {"probes": 0, "caught": 0})
        d["probes"] += 1
        d["caught"] += caught

    out = []
    for reviewer, d in sorted(by.items()):
        rate = round(100 * d["caught"] / d["probes"], 1)
        entry = {"reviewer": reviewer, "probes": d["probes"],
                 "caught": d["caught"], "catch_rate_pct": rate}
        # conformance gap: probe agreement vs normal agreement
        try:
            ovs = importlib.import_module("modules.oversight")
            stats, _s = ovs.handle("GET", "reviewer", {"id": reviewer}, api_key, ctx)
            normal = stats.get("agreement_rate_pct")
            if normal is not None and d["probes"] >= 5:
                probe_agree = round(100 * (d["probes"] - d["caught"]) / d["probes"], 1)
                gap = round(abs(probe_agree - normal), 1)
                entry["normal_agreement_pct"] = normal
                entry["probe_agreement_pct"] = probe_agree
                entry["conformance_gap"] = gap
                if gap < 5 and normal > 90:
                    entry["flag"] = "probe agreement matches normal agreement at a high rate - consistent with the verdict being visible before commit"
        except Exception:
            pass
        if d["probes"] >= 5 and rate == 0:
            entry["flag"] = "caught none of " + str(d["probes"]) + " deliberately wrong verdicts"
        out.append(entry)

    total = sum(d["probes"] for d in by.values())
    caught = sum(d["caught"] for d in by.values())
    return {"probes_resolved": total, "probes_pending": pending,
            "caught": caught,
            "overall_catch_rate_pct": round(100 * caught / total, 1),
            "by_reviewer": out,
            "note": "A single probe proves nothing about a person. A catch rate across dozens is evidence about a process."}, 200


# ----------------------------------------------------------------- witness

def _witness(ctx, api_key):
    t = time.time()
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer", (api_key,)).fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"peers": 0, "strength": "none",
                "note": "No peers witnessed. Anchoring alone still applies; mutual witnessing does not."}, 200

    total = sum(r[1] for r in rows)
    live = [r for r in rows if (t - r[2]) < 6 * 3600]
    stale = [r for r in rows if 6 * 3600 <= (t - r[2]) < 48 * 3600]
    silent = [r for r in rows if (t - r[2]) >= 48 * 3600]
    top = max(rows, key=lambda r: r[1])
    conc = round(100 * top[1] / total, 1)

    if len(live) >= 5 and conc < 50:
        strength = "strong"
    elif len(live) >= 3:
        strength = "adequate"
    elif len(live) >= 1:
        strength = "weak"
    else:
        strength = "dormant"

    out = {"peers": len(rows), "live": len(live), "stale": len(stale),
           "silent": len(silent), "observations": total,
           "largest_peer_share_pct": conc,
           "strength": strength,
           "distinct_tips_seen": sum(r[3] for r in rows)}
    if len(live) < 3:
        out["flag"] = "fewer than three live peers - breadth is what makes witnessing meaningful, and this network does not have it yet"
    if conc > 80 and len(rows) > 1:
        out["concentration_flag"] = "over 80% of observations come from a single peer"
    if len(rows) == 1:
        out["reciprocity_warning"] = "a single peer pair proves very little - two parties witnessing only each other can still collude"
    return out, 200


# ------------------------------------------------------------- declaration

def _declaration(ctx, api_key):
    try:
        dec = importlib.import_module("modules.declare")
    except Exception as e:
        return {"error": "declare_module_unavailable", "detail": str(e)}, 503

    cur, status = dec.handle("GET", "current", {}, api_key, ctx)
    if status != 200:
        return cur, status
    rules = cur["declaration"]["rules"]
    ver = cur["version"]

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT event_json,result_json FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (api_key,)).fetchall()

    parsed = []
    for ev, res in recs:
        try:
            r = {}
            r.update(json.loads(ev))
            r.update(json.loads(res))
            if str(r.get("decision", "")).endswith("_SEALED"):
                continue
            parsed.append(r)
        except Exception:
            pass

    report = []
    for rule in rules:
        constrained = 0
        violated = 0
        for r in parsed:
            if not dec._test(rule.get("when"), r):
                continue
            constrained += 1
            if not dec._test(rule.get("require"), r):
                violated += 1
        entry = {"rule": rule.get("id"), "describe": rule.get("describe"),
                 "records_constrained": constrained,
                 "violations": violated,
                 "coverage_pct": (round(100 * constrained / len(parsed), 1) if parsed else 0)}
        if constrained == 0:
            entry["flag"] = "this rule has never constrained a single record - it is decoration, not a standard"
        report.append(entry)

    dead = len([r for r in report if r["records_constrained"] == 0])
    covered = len({i for i, rule in enumerate(rules)
                   if report[i]["records_constrained"] > 0})
    out = {"declaration_version": ver, "rules": len(rules),
           "records_examined": len(parsed),
           "rules_that_constrain_nothing": dead,
           "rules_with_effect": covered,
           "per_rule": report}
    if dead:
        out["flag"] = str(dead) + " of " + str(len(rules)) + " rules constrain nothing"
    if not rules:
        out["flag"] = "an empty declaration passes everything"
    return out, 200


# ---------------------------------------------------------------- routing

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "probe":
            return _probe(ctx, api_key, data)
    else:
        if action == "probes":
            return _probes(ctx, api_key)
        if action == "witness":
            return _witness(ctx, api_key)
        if action == "declaration":
            return _declaration(ctx, api_key)
        if action in ("", "report"):
            p, _a = _probes(ctx, api_key)
            w, _b = _witness(ctx, api_key)
            d, _c = _declaration(ctx, api_key)
            return {"conformance_version": VERSION,
                    "integration": p, "witness_breadth": w,
                    "declaration_strength": d,
                    "note": "These are measurements, not enforcement. Nothing here compels good behaviour - it only makes the alternative visible."}, 200
    return {"error": "unknown_action", "action": action}, 404
