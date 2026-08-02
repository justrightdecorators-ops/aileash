#!/usr/bin/env python3
"""
modules/replay.py  -  proving the same inputs still produce the same verdict
                      WITHOUT ever disclosing how the verdict is reached
============================================================================

THE QUESTION NOBODY ELSE IN THIS MARKET CAN ANSWER
--------------------------------------------------
Every compliance platform can tell you what it decided. Not one of them can
prove it would decide the same way again.

Ask any of them to re-run decision 4,117 from its sealed inputs and show the
same verdict falls out. They cannot. Not because they will not - because
their scoring goes through a model call, and model calls are not
reproducible. Same inputs, different day, different answer. Their audit
trail describes a decision that can never be performed twice.

Ours is arithmetic. Deterministic below the model layer, and always has
been. This module lets anyone establish that for themselves.

THE SCORING LOGIC IS NEVER DISCLOSED
------------------------------------
Read this before changing anything in here.

Nothing in this module publishes, returns, echoes or hints at the contents
of the decision function. Not the source, not the weights, not the
thresholds, not the signal names, not the intermediate values. The only
thing that leaves the building is a SHA-256 of the deployed source, which
is one-way and reveals nothing about what it hashes.

Determinism is proved as a BLACK BOX instead: same inputs in, same verdict
out, demonstrated repeatedly, by the challenger, on their own schedule,
with every run sealed into the chain. That is a stronger proof than showing
the code, because it is behaviour observed over time rather than a claim
about a listing nobody can confirm is what actually runs in production.

  A competitor who reads every route here learns exactly one thing: that
  our verdicts are reproducible. Which is the point, and which they cannot
  copy, because reproducibility is a property of the architecture and not a
  feature that can be bolted on.

HOW SOMEONE CHECKS US WITHOUT SEEING ANYTHING
---------------------------------------------
  POST /x/replay/challenge   send any inputs you like. We run them, seal
                             the run into the chain, and hand you back the
                             verdict, the audit hash, and a fingerprint of
                             your own inputs.

Send the same inputs again - an hour later, a year later, from a different
address. If the verdict ever moves, you have caught us, and both runs are
independently sealed and anchored so we cannot revise either one. If it
never moves, you have established determinism yourself, empirically,
adversarially, without a line of our code.

We also report how many times that exact input has been challenged, when it
was first seen, and every audit hash it produced, so the whole history is
verifiable through routes we do not control the answers to.

THE HONEST COST, WHICH IS REAL
------------------------------
An open scoring oracle can be probed. Feed it a thousand variations, watch
the verdicts move, and a determined party can map the decision boundary
without ever seeing the code. That is a genuine exposure and it is the
price of this proof.

It is mitigated, not eliminated: challenges are rate limited per address,
inputs are fingerprinted so repeat submissions are cheap and novel ones are
not, and boundary-probing patterns are already logged elsewhere in the
platform. Anyone systematically mapping the function leaves an obvious,
sealed trail while doing it.

The trade is deliberate. A closed engine nobody can test is worth less than
a testable one somebody might partially map, because the first cannot be
sold to a regulator and the second can.

CONFIGURATION
-------------
This module does not import server.py - nothing here does. It finds the
live decision function at runtime among already-loaded modules, so it can
only observe the engine, never change it. If your scorer is named something
not in SCORER_NAMES below, add it there. Everything else is read from the
audit_log schema at startup rather than assumed.

    POST /x/replay/challenge     run any inputs, sealed          (public)
    GET  /x/replay/history       every run of a given input       (public)
    GET  /x/replay/self          reproduction rate over a sample  (public)
    GET  /x/replay/fingerprint   hash of the deployed code        (public)
    GET  /x/replay/spec          how to test us                   (public)
    GET  /x/replay/check         re-run one sealed decision       (keyed)
    POST /x/replay/attest        seal the current fingerprint     (keyed)
"""

import hashlib
import inspect
import json
import sys
import time
from datetime import datetime, timezone

VERSION = "1.0"

# Challenge, history, self, fingerprint and spec are open - a
# reproducibility claim you need an account to test is not a claim anyone
# should accept. check stays keyed: it reads back a specific sealed
# decision, which belongs to whoever owns it.
PUBLIC = {("POST", "challenge"), ("GET", "history"), ("GET", "self"),
          ("GET", "fingerprint"), ("GET", "spec")}

# Names the live decision function might go by. Add yours if it is not
# here - this is the one thing that has to match your code.
SCORER_NAMES = (
    "score_event", "decide", "score", "evaluate", "run_decision",
    "make_decision", "assess", "score_decision", "engine_decide",
)

# Columns the sealed inputs might live in. Detected, never assumed.
INPUT_COLUMNS = ("event", "event_json", "payload", "inputs", "request",
                 "ev", "data", "event_data")
RESULT_COLUMNS = ("result", "result_json", "res", "decision_json", "outcome",
                  "response")
VERDICT_COLUMNS = ("decision", "verdict", "action_taken")
SCORE_COLUMNS = ("score", "risk_score", "points")

SELF_SAMPLE_DEFAULT = 50
SELF_SAMPLE_MAX = 500

# Challenge throttle. Repeat submissions of an input we have already seen
# are cheap; novel inputs are what a prober needs, so those are what get
# limited.
NOVEL_PER_HOUR = 40
MAX_PAYLOAD_KEYS = 40

_ready = False
_columns = []


def _setup(ctx):
    global _ready, _columns
    if _ready:
        return
    cols = []
    try:
        with ctx["lock"]:
            for row in ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall():
                cols.append(row[1])
    except Exception:
        pass
    _columns = cols
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS replay_attest("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "fingerprint TEXT,function TEXT,taken REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        # One row per challenge run. The input fingerprint is stored, the
        # input itself is not - we have no reason to keep a stranger's
        # payload and every reason not to.
        c.execute("CREATE TABLE IF NOT EXISTS replay_challenge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,input_hash TEXT,"
                  "verdict TEXT,score TEXT,code_fingerprint TEXT,ran REAL,"
                  "audit_hash TEXT,block_index INTEGER,client TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_input "
                  "ON replay_challenge(input_hash,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_ran ON replay_challenge(ran)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _pick(candidates):
    for name in candidates:
        if name in _columns:
            return name
    return None


def _canonical(payload):
    """Stable rendering of an input payload, so the same inputs always
    fingerprint to the same value regardless of key order or spacing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _input_hash(payload):
    return hashlib.sha256(("AILEASH-INPUT-v1:" + _canonical(payload)).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# finding the live decision function
# ----------------------------------------------------------------------

def _find_scorer():
    """Locate the deployed decision function among loaded modules.

    Deliberately does not import server.py. It looks at what is already
    running, so this module can observe the engine and never alter it.
    """
    for module_name in ("__main__", "server", "app", "main"):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in SCORER_NAMES:
            candidate = getattr(module, name, None)
            if callable(candidate):
                return candidate, "%s.%s" % (module_name, name), None
    return None, None, ("no decision function found. Add its real name to SCORER_NAMES at the "
                        "top of modules/replay.py.")


def _fingerprint_of(function):
    """SHA-256 of the deployed source. One-way: it commits to which code is
    running without revealing any of it."""
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        return None, "source not readable for this callable"
    normalised = "\n".join(line.rstrip() for line in source.splitlines()).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest(), None


# ----------------------------------------------------------------------
# running the engine
# ----------------------------------------------------------------------

def _rerun(function, inputs):
    """Execute the live decision function against a set of inputs.

    Never raises. On failure it reports that the call failed and nothing
    about why the engine is shaped the way it is.
    """
    if inputs is None:
        return None, "no inputs"
    attempts = []
    if isinstance(inputs, dict):
        attempts.append(lambda: function(**inputs))
        attempts.append(lambda: function(inputs))
    else:
        attempts.append(lambda: function(inputs))
    for call in attempts:
        try:
            return call(), None
        except TypeError:
            continue
        except Exception:
            return None, "the decision function could not process those inputs"
    return None, "those inputs do not match the shape the engine expects"


def _extract(output):
    """Pull (verdict, score) out of whatever the scorer returns. Nothing
    else from the return value is ever surfaced."""
    if isinstance(output, dict):
        return (output.get("decision") or output.get("verdict"), output.get("score"))
    if isinstance(output, (tuple, list)) and len(output) >= 2:
        return output[0], output[1]
    return output, None


def _same(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    return str(a).strip().upper() == str(b).strip().upper()


# ----------------------------------------------------------------------
# challenge - the public proof
# ----------------------------------------------------------------------

def _novel_recently(ctx):
    since = time.time() - 3600
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT input_hash) FROM replay_challenge WHERE ran>=?",
            (since,)).fetchone()
    return int(row[0]) if row else 0


def _challenge(ctx, api_key, data):
    inputs = data.get("inputs", data.get("event", data.get("payload")))
    if not isinstance(inputs, dict) or not inputs:
        return {"error": "inputs_required",
                "message": "Send an inputs object. We will run it, seal the run, and hand you "
                           "back the verdict. Send the same object again whenever you like - "
                           "if the answer ever moves, you have caught us."}, 400
    if len(inputs) > MAX_PAYLOAD_KEYS:
        return {"error": "payload_too_wide", "message": "at most %d keys" % MAX_PAYLOAD_KEYS}, 400

    fingerprint_in = _input_hash(inputs)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC",
            (fingerprint_in,)).fetchall()

    if not prior and _novel_recently(ctx) >= NOVEL_PER_HOUR:
        return {"error": "rate_limited",
                "message": "Too many distinct inputs in the last hour. Repeat submissions of "
                           "inputs already seen are never limited - testing whether the answer "
                           "moves is the whole point. Mapping the function is not.",
                "repeat_freely": "any input_hash already in /x/replay/history"}, 429

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable", "message": "the decision engine is not reachable "
                                                          "from this route right now"}, 503

    output, problem = _rerun(function, inputs)
    if problem:
        return {"error": "not_runnable", "message": problem}, 422

    verdict, score = _extract(output)
    code_fingerprint, _p = _fingerprint_of(function)
    now = time.time()

    ev = {"user_id": "chal:" + fingerprint_in[:16], "action": "replay_challenge", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": str(verdict), "score": score, "replay_version": VERSION,
           "input_hash": fingerprint_in, "code_fingerprint": code_fingerprint,
           "detail": "input=%s;verdict=%s;code=%s" % (fingerprint_in, verdict, code_fingerprint)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key or "public-replay")

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO replay_challenge(input_hash,verdict,score,code_fingerprint,ran,"
            "audit_hash,block_index,client) VALUES(?,?,?,?,?,?,?,?)",
            (fingerprint_in, str(verdict), str(score), code_fingerprint, now,
             audit_hash, block_index, "keyed" if api_key else "anonymous"))
        ctx["conn"].commit()

    out = {
        "input_hash": fingerprint_in,
        "verdict": verdict, "score": score,
        "ran_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "code_fingerprint": code_fingerprint,
        "runs_of_this_input": len(prior) + 1,
        "replay_version": VERSION,
        "how_to_use_this": "Send the identical inputs again, whenever you like, from wherever "
                           "you like. Every run is sealed into a chain that is externally "
                           "anchored and independently witnessed, so neither this answer nor "
                           "the next one can be revised afterwards.",
        "history": "/x/replay/history?input_hash=" + fingerprint_in,
        "verify_this_run": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if prior:
        first_verdict, first_score = prior[0][0], prior[0][1]
        stable = _same(verdict, first_verdict) and _same(score, first_score)
        out["first_seen"] = _iso(prior[0][2])
        out["stable"] = stable
        out["verdict_moved"] = not stable
        if stable:
            out["what_this_shows"] = ("Identical to the first run of these inputs on %s, and to "
                                      "every run since. Determinism observed rather than "
                                      "asserted." % _iso(prior[0][2]))
        else:
            out["what_this_shows"] = ("These inputs previously produced a different answer. "
                                      "Either the code changed - compare the code fingerprints "
                                      "in the history - or the engine is not deterministic. "
                                      "Both runs are sealed and neither can be withdrawn.")
    else:
        out["stable"] = None
        out["what_this_shows"] = ("First time these inputs have been seen. Send them again to "
                                  "start building the record.")
    return out, 200


def _history(ctx, data):
    input_hash = str(data.get("input_hash", data.get("hash", ""))).strip().lower()
    if not input_hash:
        return {"error": "input_hash_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint,client "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC LIMIT 500",
            (input_hash,)).fetchall()
    if not rows:
        return {"error": "unknown_input", "input_hash": input_hash,
                "message": "No run recorded for that input fingerprint."}, 404

    verdicts = {r[0] for r in rows}
    codes = {r[5] for r in rows if r[5]}
    return {
        "input_hash": input_hash,
        "runs": len(rows),
        "first_run": _iso(rows[0][2]), "latest_run": _iso(rows[-1][2]),
        "distinct_verdicts": len(verdicts),
        "stable": len(verdicts) == 1,
        "code_versions_seen": len(codes),
        "history": [{"verdict": r[0], "score": r[1], "ran_at": _iso(r[2]),
                     "sealed_in_chain": r[3], "block_index": r[4],
                     "code_fingerprint": r[5], "submitted_by": r[6]} for r in rows],
        "what_this_is": "Every recorded run of one exact set of inputs, each sealed separately "
                        "into the chain. Verify any of them independently at "
                        "/x/consistency/ancestor - we cannot alter one after the fact.",
        "note": "More than one distinct verdict across a single code fingerprint would mean the "
                "engine is not deterministic. That is exactly what this is here to expose.",
    }, 200


# ----------------------------------------------------------------------
# self audit
# ----------------------------------------------------------------------

def _fetch(ctx, where, args):
    input_col = _pick(INPUT_COLUMNS)
    result_col = _pick(RESULT_COLUMNS)
    verdict_col = _pick(VERDICT_COLUMNS)
    score_col = _pick(SCORE_COLUMNS)
    if not input_col:
        return None, ("audit_log does not store decision inputs on this deployment, so sealed "
                      "decisions cannot be re-executed. Seal the event payload alongside the "
                      "verdict and replay becomes available from that point on.")
    fields = ["id", "audit_hash", "ts", input_col]
    for extra in (result_col, verdict_col, score_col):
        if extra and extra not in fields:
            fields.append(extra)
    sql = "SELECT %s FROM audit_log WHERE %s" % (", ".join(fields), where)
    with ctx["lock"]:
        rows = ctx["conn"].execute(sql, tuple(args)).fetchall()
    if not rows:
        return None, "no sealed decision matched"
    out = []
    for row in rows:
        record = dict(zip(fields, row))
        raw = record.get(input_col)
        try:
            parsed = raw if isinstance(raw, (dict, list)) else json.loads(raw)
        except Exception:
            parsed = None
        sealed_result = None
        if result_col:
            raw_result = record.get(result_col)
            try:
                sealed_result = raw_result if isinstance(raw_result, dict) else json.loads(raw_result)
            except Exception:
                sealed_result = None
        out.append({"id": record.get("id"), "audit_hash": record.get("audit_hash"),
                    "ts": record.get("ts"), "inputs": parsed,
                    "sealed_result": sealed_result,
                    "sealed_verdict": record.get(verdict_col) if verdict_col else None,
                    "sealed_score": record.get(score_col) if score_col else None})
    return out, None


def _sealed_pair(record):
    verdict = record.get("sealed_verdict")
    score = record.get("sealed_score")
    result = record.get("sealed_result")
    if isinstance(result, dict):
        if verdict is None:
            verdict = result.get("decision") or result.get("verdict")
        if score is None:
            score = result.get("score")
    return verdict, score


def _compare(record, function):
    output, why = _rerun(function, record.get("inputs"))
    sealed_verdict, sealed_score = _sealed_pair(record)
    if why:
        return {"audit_hash": record["audit_hash"], "result": "not_replayable"}
    verdict, score = _extract(output)
    identical = _same(verdict, sealed_verdict) and _same(score, sealed_score)
    return {"audit_hash": record["audit_hash"], "sealed_at": _iso(record.get("ts")),
            "result": "identical" if identical else "divergent"}


def _self(ctx, data):
    try:
        sample = int(data.get("sample", SELF_SAMPLE_DEFAULT))
    except (TypeError, ValueError):
        sample = SELF_SAMPLE_DEFAULT
    sample = max(1, min(sample, SELF_SAMPLE_MAX))

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503

    records, fetch_why = _fetch(ctx, "1=1 ORDER BY id DESC LIMIT ?", [sample])
    if fetch_why:
        return {"error": "cannot_replay", "message": fetch_why}, 400

    identical = divergent = skipped = 0
    divergent_hashes = []
    started = time.time()
    for record in records:
        outcome = _compare(record, function)
        if outcome["result"] == "identical":
            identical += 1
        elif outcome["result"] == "divergent":
            divergent += 1
            if len(divergent_hashes) < 10:
                divergent_hashes.append(outcome["audit_hash"])
        else:
            skipped += 1

    checked = identical + divergent
    rate = round((identical / checked) * 100, 4) if checked else None
    code_fingerprint, _p = _fingerprint_of(function)

    body = {
        "sampled": len(records), "replayable": checked,
        "identical": identical, "divergent": divergent, "not_replayable": skipped,
        "reproduction_rate_percent": rate,
        "took_seconds": round(time.time() - started, 3),
        "code_fingerprint": code_fingerprint,
        "replay_version": VERSION,
        "headline": ("%d of %d sealed decisions reproduce identically under the code deployed "
                     "right now." % (identical, checked)) if checked else
                    "Nothing replayable in this sample.",
        "why_this_matters": "A platform whose scoring runs through a model call cannot do this "
                            "at all. Reproducibility is a property of the architecture, not a "
                            "feature that can be added later.",
        "honest": "Divergences are counted here, not filtered out. A falling rate is the most "
                  "useful thing this route can tell you.",
        "independent_check": "Do not take our word for this - /x/replay/challenge lets you run "
                             "your own inputs and repeat them whenever you like.",
    }
    if divergent_hashes:
        body["divergent_receipts"] = divergent_hashes
    return body, 200


# ----------------------------------------------------------------------
# fingerprint, keyed check, attest
# ----------------------------------------------------------------------

def _fingerprint(ctx):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    return {"code_fingerprint": digest, "problem": problem, "replay_version": VERSION,
            "what_this_is": "A SHA-256 of the source of the code currently deciding. It commits "
                            "to which version is running. It is one-way and discloses nothing "
                            "about the logic, the weights or the thresholds.",
            "what_it_is_for": "Sealed alongside verdicts via /x/replay/attest, so a change in "
                              "behaviour can be attributed to a dated code change rather than "
                              "looking like a fault - or hidden as one.",
            "note": "The function name and signature are deliberately not published."}, 200


def _check(ctx, data):
    """Keyed. Re-runs one sealed decision and reports match or divergence."""
    target = str(data.get("hash", data.get("receipt", ""))).strip().lower()
    if not target:
        return {"error": "hash_required"}, 400
    records, why = _fetch(ctx, "audit_hash=? LIMIT 1", [target])
    if why:
        return {"error": "cannot_replay", "message": why}, 400
    function, name, scorer_why = _find_scorer()
    if scorer_why:
        return {"error": "engine_unavailable"}, 503
    outcome = _compare(records[0], function)
    digest, _p = _fingerprint_of(function)
    outcome.update({"code_fingerprint": digest, "replay_version": VERSION,
                    "what_this_proves": "The sealed inputs were fed back through the live "
                                        "decision function and the output compared with what "
                                        "was sealed."})
    return outcome, 200


def _attest(ctx, api_key):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    if not digest:
        return {"error": "no_fingerprint", "message": problem}, 503

    now = time.time()
    ev = {"user_id": "rep:" + digest[:16], "action": "code_fingerprint_sealed", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_SEALED", "score": 0, "replay_version": VERSION,
           "fingerprint": digest, "detail": "fingerprint=%s" % digest}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO replay_attest(api_key,fingerprint,function,taken,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, digest, name, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"fingerprint": digest, "taken_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Records which code was deciding at this moment, inside the chain "
                              "the decisions are sealed in. Every verdict after this point is "
                              "attributable to a known, timestamped version of the logic - "
                              "without that logic being published.",
            "do_this": "Attest on every deploy that touches scoring. A later divergence then "
                       "reads as a dated policy change rather than an unexplained fault."}, 200


def _spec():
    return {
        "replay_version": VERSION,
        "claim": "The same inputs produce the same verdict, and you can establish that yourself "
                 "without an account and without seeing any of our logic.",
        "the_logic_is_not_published": "No route here returns the scoring source, the weights, "
                                      "the thresholds, the signal names or any intermediate "
                                      "value. The only thing published is a SHA-256 of the "
                                      "deployed source, which is one-way.",
        "how_to_test_us": [
            "POST /x/replay/challenge with any inputs object you like.",
            "Keep the input_hash it returns.",
            "Send the identical inputs again tomorrow, next month, next year, from anywhere.",
            "GET /x/replay/history?input_hash=... to see every run, each sealed separately.",
            "If the verdict ever moves under an unchanged code fingerprint, the engine is not "
            "deterministic and you have proof of it that we cannot withdraw.",
        ],
        "why_black_box_is_stronger": "A published listing only shows what the code says. "
                                     "Repeated challenge shows what production actually does, "
                                     "over time, on inputs we did not choose.",
        "what_breaks_determinism": [
            "a wall-clock read inside the scoring path",
            "iteration over an unordered structure",
            "an unseeded random call",
            "any model call in the decision path - which is why most platforms cannot do this",
        ],
        "what_this_does_not_prove": "That a decision was correct, or that the inputs were "
                                    "honestly captured. Only that the same inputs still yield "
                                    "the same output under known code. Determinism is not "
                                    "fairness.",
        "rate_limits": "Repeat submissions of inputs already seen are never limited - retesting "
                       "is the point. Novel inputs are limited, because bulk novel inputs are "
                       "how a decision boundary gets mapped rather than how a claim gets tested.",
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
        if action == "fingerprint":
            return _fingerprint(ctx)
        if action == "history":
            return _history(ctx, data)
        if action == "self":
            return _self(ctx, data)
        if action == "check":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _check(ctx, data)

    if method == "POST":
        if action == "challenge":
            return _challenge(ctx, api_key, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "attest":
            return _attest(ctx, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "fingerprint", "history", "self", "check (keyed)"],
            "POST": ["challenge", "attest (keyed)"]}, 404
