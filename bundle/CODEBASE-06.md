# Codebase — part 6 of 18

Contains:
- `modules/replay.py`
- `modules/router.py`
- `modules/rulebind.py`
- `modules/savings.py`
- `modules/spec.py`
- `modules/standard.py`


## `modules/replay.py`

678 lines, 30538 bytes

```python
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

```


## `modules/router.py`

234 lines, 7196 bytes

```python
"""
Module router - /x/<module>/<action>

Dispatches to modules/<module>.py, which exposes:

    def handle(method, action, data, api_key, ctx): return payload, status

A module may declare PUBLIC = {("GET","attest"), ...} for routes that need no
API key. Default is closed - a route has to be opted open deliberately.

RATE LIMITING
-------------
Authenticated routes reuse the server's own check_rate (60/min, 1000/hour per
key), so module traffic counts against the same budget as /api/govern rather
than sitting outside it.

Public routes have no key to meter, so they are metered per client address on
a deliberately tighter budget. Without this, an unauthenticated endpoint is an
open invitation. The window store is bounded and self-pruning.

PAYLOAD CAP
-----------
Module bodies are capped. Nothing here needs a megabyte of JSON, and an
uncapped body on a public route is a memory exhaustion vector.

POST SUPPORT WITHOUT EDITING server.py
--------------------------------------
server.py has an /x/ branch in do_GET but not in do_POST, so POST routes
return the server's 404. The correct fix is four lines in do_POST. This is
the fix for when that is not practical.

On first import, this module patches Handler.do_POST to check for /x/ before
falling through to the original. The patch is idempotent, keeps the original
behaviour for every other path, and reverts on restart because it lives in
memory rather than on disk.

The catch, stated plainly: a module is only imported when a request reaches
the router, and the only working entry point is do_GET. So after every deploy
the first /x/ request must be a GET - after that, POST works until the next
restart. Anything hitting /x/ with a GET does it, including a browser.

This is a workaround for an editing constraint, not good architecture. If the
four lines ever go into do_POST, this patch detects the branch is already
there and does nothing.
"""

import importlib, json, sys, time
from collections import defaultdict, deque

VERSION = "3.2"

MAX_BODY_KEYS = 200
MAX_BODY_CHARS = 200000

PUBLIC_PER_MIN = 30
PUBLIC_PER_HOUR = 300
_ip_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_ip_last_prune = [0.0]

_c = {}
_patched = [False]


def _install_post(s):
    """Add an /x/ branch to do_POST at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_POST"):
        return "no handler"
    if getattr(H, "_x_post_patched", False):
        _patched[0] = True
        return "already installed"
    original = H.do_POST

    def do_POST(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.startswith("/x/"):
            try:
                body = s.read_body(self)
            except Exception:
                body = {}
            payload, status = route(self, p, body)
            s.send_json(self, payload, status)
            return
        return original(self)

    H.do_POST = do_POST
    H._x_post_patched = True
    _patched[0] = True
    print("ROUTER: /x/ POST branch installed at runtime", flush=True)
    return "installed"


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _load(name):
    m = _c.get(name)
    if m is None:
        m = importlib.import_module("modules." + name)
        _c[name] = m
    return m


def _client(h):
    """Prefer the forwarded address - behind a proxy the socket address is
    the proxy, which would meter every visitor as one client."""
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
    except Exception:
        pass
    try:
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def _prune_ips(t):
    if t - _ip_last_prune[0] < 300:
        return
    _ip_last_prune[0] = t
    dead = [k for k, w in _ip_wins.items()
            if (not w["hour"]) or w["hour"][-1] < t - 3600]
    for k in dead:
        del _ip_wins[k]


def _check_ip(ip):
    t = time.time()
    _prune_ips(t)
    w = _ip_wins[ip]
    while w["min"] and w["min"][0] < t - 60:
        w["min"].popleft()
    while w["hour"] and w["hour"][0] < t - 3600:
        w["hour"].popleft()
    if len(w["min"]) >= PUBLIC_PER_MIN:
        return False, "rate_limit_minute"
    if len(w["hour"]) >= PUBLIC_PER_HOUR:
        return False, "rate_limit_hour"
    w["min"].append(t)
    w["hour"].append(t)
    return True, None


def _too_big(data):
    if not isinstance(data, dict):
        return False
    if len(data) > MAX_BODY_KEYS:
        return True
    try:
        return len(json.dumps(data)) > MAX_BODY_CHARS
    except Exception:
        return True


def route(h, path, data):
    try:
        s = _srv()
        if s is None:
            return {"error": "server_not_found"}, 500

        if not _patched[0]:
            try:
                _install_post(s)
            except Exception as _e:
                print("ROUTER: post patch failed - " + str(_e), flush=True)

        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path",
                    "expected": "/x/<module>/<action>"}, 404
        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""

        if isinstance(data, dict) and data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}

        if _too_big(data):
            return {"error": "payload_too_large",
                    "limit_chars": MAX_BODY_CHARS,
                    "limit_keys": MAX_BODY_KEYS}, 413

        try:
            m = _load(name)
        except Exception:
            return {"error": "unknown_module", "module": name}, 404
        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle"}, 500

        method = h.command
        public = getattr(m, "PUBLIC", set())
        is_public = (method, act) in public or (method, "") in public

        a = s.get_bearer(h)

        if is_public:
            if a and not s.get_key(a):
                a = None
            if not a:
                ok, why = _check_ip(_client(h))
                if not ok:
                    return {"error": why,
                            "message": "Public endpoints are rate limited per client. Use an API key for the normal budget."}, 429
        else:
            if not a or not s.get_key(a):
                return {"error": "invalid_api_key"}, 401

        if a:
            try:
                ok, why = s.check_rate(a)
                if not ok:
                    return {"error": why}, 429
            except Exception:
                pass

        ctx = {"conn": s._conn, "lock": s._db_lock,
               "seal": s.seal, "get_key": s.get_key}
        return m.handle(method, act, data, a, ctx)

    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500

```


## `modules/rulebind.py`

371 lines, 15359 bytes

```python
"""
modules/rulebind.py  -  rule binding, provable without an account

THE QUESTION THIS ANSWERS
-------------------------
Eighteen months after a decision, nobody asks what was decided. They ask which
rules were live at that instant. Most systems answer with a changelog somebody
could have edited, or with a version number sitting beside the record rather
than inside it - which proves nothing, because anything beside a record can be
changed afterwards to suit.

The claim worth making is narrower and harder: the ruleset version was
committed at the moment of the decision, in the same sealed object, and a
verdict cannot later be reattributed to different rules.

HOW IT IS PROVED WITHOUT TRUSTING US
------------------------------------
Every decision here produces a binding digest:

    AILEASH-RULEBIND-v1|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|<score>|<sealed_at>

SHA-256 of that string is what gets sealed into the chain. Every component is
published. So anyone can take the components we return, rebuild the string
themselves, hash it, and check it equals the binding in the sealed record.

That is the whole proof, and it works in both directions:

  - change the pack hash after the fact and the binding no longer recomputes
  - change the binding and the chain breaks from that block onwards
  - change the chain and it stops matching the external anchor and the peer
    chain that recorded our tip an hour later

None of those require taking our word for anything, and none require us to
disclose the scoring logic - the inputs are published as a digest, not as
values, and the weights are never exposed at any point.

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. That the pack
does what its description says. It proves which ruleset produced which verdict
and that the pairing was fixed at the time rather than asserted later. Narrow,
and the only part that is actually provable.

ROUTES  (all public - the point is that no account is needed)
------------------------------------------------------------
  POST /x/rulebind/prove       run a decision, get every component back
  GET  /x/rulebind/verify?receipt=   recompute the binding for a sealed record
  GET  /x/rulebind/packs       ruleset versions and when each was first sealed
  GET  /x/rulebind/spec        what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.0"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

PUBLIC = {("POST", "prove"), ("GET", "verify"), ("GET", "packs"),
          ("GET", "spec"), ("GET", "")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Same runtime lookup replay.py uses - never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute(
            "CREATE TABLE IF NOT EXISTS rulebind_log("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,pack_id TEXT,"
            "pack_hash TEXT,inputs_digest TEXT,verdict TEXT,score REAL,"
            "sealed_at REAL,binding TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_hash ON rulebind_log(audit_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_pack ON rulebind_log(pack_hash)")
        c.commit()
    _ready = True


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ----------------------------------------------------------------------
# the engine, found at runtime
# ----------------------------------------------------------------------

def _find(names):
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _active_pack(ctx):
    """The ruleset in force. Read from signal_packs if the table is there,
    otherwise fall back to a hash of the core engine's own identity - either
    way the value is stable and published."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT pack_id,version,pack_hash FROM signal_packs "
                "ORDER BY id DESC LIMIT 1").fetchone()
        if row and row[2]:
            return str(row[0] or "core"), str(row[2])
        if row:
            return str(row[0] or "core"), _sha("pack:%s:v%s" % (row[0], row[1]))
    except Exception:
        pass

    # No pack table, or a different schema. Fall back to the core nine, whose
    # identity is fixed by the deployed decision function itself.
    fn, where = _find(SCORER_NAMES)
    if fn:
        try:
            import inspect
            return "core-nine", _sha(inspect.getsource(fn))
        except Exception:
            return "core-nine", _sha("core-nine|" + str(where))
    return "unknown", _sha("unknown")


def _canonical_inputs(data):
    """Inputs are published as a digest, never as values. Somebody testing this
    knows what they sent; nobody else learns anything from the record."""
    clean = {}
    for k, v in list(data.items())[:MAX_INPUT_KEYS]:
        if k in ("api_key", "token", "key"):
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            clean[str(k)[:40]] = v
        else:
            clean[str(k)[:40]] = str(v)[:120]
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def _binding(pack_id, pack_hash, inputs_digest, verdict, score, sealed_at):
    material = "|".join([BINDING_PREFIX, str(pack_id), str(pack_hash),
                         str(inputs_digest), str(verdict), ("%.6f" % float(score)),
                         ("%.3f" % float(sealed_at))])
    return material, _sha(material)


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values.")}, 400

    scorer, scorer_where = _find(SCORER_NAMES)
    if not scorer:
        return {"error": "engine_unavailable",
                "message": "The scoring function could not be found at runtime."}, 503

    try:
        result = scorer(dict(data))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return {"error": "scoring_failed", "message": str(exc)[:200]}, 400

    decider, _ = _find(DECIDER_NAMES)
    verdict = None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
        except Exception:
            verdict = None
    if verdict is None:
        verdict = "ALLOW" if score < 0.35 else ("CHALLENGE" if score < 0.70 else "BLOCK")

    pack_id, pack_hash = _active_pack(ctx)
    inputs_digest = _sha(_canonical_inputs(data))
    sealed_at = time.time()
    material, binding = _binding(pack_id, pack_hash, inputs_digest,
                                 verdict, score, sealed_at)

    detail = ("rulebind=" + binding + ";pack=" + pack_id + ";pack_hash=" + pack_hash +
              ";inputs=" + inputs_digest + ";verdict=" + str(verdict) +
              ";score=%.6f" % score)
    ev = {"user_id": "rb:" + pack_id, "action": "rule_binding_sealed", "amount": 0,
          "country": "UK", "device_id": "rulebind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RULEBIND_" + str(verdict), "score": round(score, 6),
           "rulebind_version": VERSION, "pack_id": pack_id, "pack_hash": pack_hash,
           "binding": binding, "timestamp": sealed_at, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, sealed_at, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding": binding,
        "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "recompute_it_yourself": {
            "step_1": ("Take binding_material exactly as returned - it is the "
                       "string that was hashed, printed in full."),
            "step_2": "SHA-256 it. You should get the value in binding.",
            "step_3": ("Confirm the ruleset hash appears inside that string. It "
                       "is a component of the digest, not a field beside it - "
                       "change it and the digest no longer recomputes."),
            "step_4": ("Check the block is in the chain at /api/verify-chain, "
                       "externally timestamped at /api/anchor-status, and that "
                       "our tip was recorded by an independent operator at "
                       "/x/witness/peers."),
            "shell": ("printf '%s' \"$MATERIAL\" | shasum -a 256"),
        },
        "what_this_proves": (
            "That this verdict and this ruleset version were committed together, "
            "at this time, in one object. The pairing cannot be altered afterwards "
            "without breaking the digest, and the digest cannot be altered without "
            "breaking the chain."),
        "what_it_does_not_prove": (
            "That the rules were good, or the verdict correct. Only which ruleset "
            "produced it and that the pairing was fixed at the time."),
        "verify": "/x/rulebind/verify?receipt=" + h,
    }, 200


def _verify(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,inputs_digest,verdict,score,sealed_at,"
            "binding,block_index FROM rulebind_log WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No rule-binding record with that receipt."}, 404

    pack_id, pack_hash, inputs_digest, verdict, score, sealed_at, stored, block = row
    material, recomputed = _binding(pack_id, pack_hash, inputs_digest,
                                    verdict, score, sealed_at)
    matches = (recomputed == stored)

    return {
        "found": True,
        "receipt": receipt,
        "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict,
        "score": score,
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored,
        "binding_material": material,
        "binding_recomputed": recomputed,
        "binding_matches": matches,
        "result": ("The ruleset version recomputes into the binding that was "
                   "sealed with this decision. It was bound at the time, not "
                   "attached afterwards."
                   if matches else
                   "MISMATCH. The stored binding does not recompute from the "
                   "stored components. Something has been altered and this "
                   "record should not be relied upon."),
        "chain": "/api/verify-chain",
        "external_clock": "/api/anchor-status",
        "witnessed_by": "/x/witness/peers",
    }, 200


def _packs(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,COUNT(*),MIN(sealed_at),MAX(sealed_at)"
            " FROM rulebind_log GROUP BY pack_id,pack_hash ORDER BY MAX(sealed_at) DESC"
        ).fetchall()
    current_id, current_hash = _active_pack(ctx)
    return {
        "current": {"pack_id": current_id, "pack_hash": current_hash},
        "history": [{
            "pack_id": r[0], "pack_hash": r[1], "decisions_bound": r[2],
            "first_sealed": _iso(r[3]), "last_sealed": _iso(r[4]),
            "current": (r[1] == current_hash),
        } for r in rows],
        "note": ("Each ruleset version has its own hash. Changing a weight, a "
                 "threshold or a signal produces a new hash and a new dated "
                 "entry here, so a change to the rules is an event in the "
                 "record rather than a silent edit. Decisions stay bound to the "
                 "version that produced them."),
    }, 200


def _spec():
    return {
        "module": "rulebind", "version": VERSION,
        "check": "rule_binding",
        "question": ("Was the ruleset version bound at decision time, or "
                     "attached to the record afterwards?"),
        "binding_format": (BINDING_PREFIX +
                           "|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|"
                           "<score:.6f>|<sealed_at:.3f>"),
        "digest": "SHA-256 of that string, UTF-8, no trailing newline",
        "how_to_test_it": [
            "POST any inputs to /x/rulebind/prove. No account needed.",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Confirm the block is in the chain, anchored, and witnessed.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names and intermediate values. Inputs "
            "are published as a digest, not as values. Nothing here requires the "
            "scoring logic to be revealed, and none of it is."),
        "what_it_does_not_prove": (
            "That the rules were good or the verdict correct. Only which ruleset "
            "produced which verdict, and that the pairing was fixed at the time."),
        "cost": "Free. No account, no key.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    key = api_key or "public-rulebind"

    if method == "POST":
        if action == "prove":
            return _prove(ctx, key, data)
        return {"error": "unknown_action", "action": action, "POST": ["prove"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "verify", "packs"]}, 404

```


## `modules/savings.py`

755 lines, 33108 bytes

```python
"""
modules/savings.py  -  the cost model at /savings

WHAT IT IS
----------
One page. Enter a device count, see what a traditional compliance architecture
costs against a proof-based one, and change every assumption behind it.

WHY THE ASSUMPTIONS ARE EDITABLE
--------------------------------
The saving rests on one number - what the traditional architecture costs per
device per year - and that number is ours, not theirs. Asserted, it is the
first thing a finance director dismisses. Broken into ingestion, storage,
monitoring, pipeline and engineering, with every line editable, the arithmetic
runs on their figures instead of ours. Harder to wave away, and honest.

The page will also say plainly when the saving goes negative on the numbers
somebody has typed. A calculator that can only ever produce a good answer is
not a calculator.

NO TRACKING, NO STORAGE
-----------------------
Everything happens in the browser. Nothing is submitted, nothing is recorded,
no figure anyone types reaches the server. A buyer modelling their own costs
should not have to wonder where those went.

SAME PATCH AS network.py AND console.py
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime, adds one path, leaves
every other path alone. After each deploy one /x/ request must arrive before
/savings exists - opening /x/savings/status does it.
"""

import json
import sys
import time

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "verify"), ("POST", "seal")}

PAGE_PATHS = ("/savings", "/savings.html", "/cost", "/proof-machine")

_patched = [False]
_ready = [False]


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS savings_model("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,devices INTEGER,"
            "assumptions TEXT,traditional_per REAL,proof_per REAL,"
            "annual_saving REAL,modelled REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_sav_hash ON savings_model(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The cost of proving it — AILeash</title>
<meta name="description" content="What AI governance costs at enterprise scale, and what a proof-based architecture changes. Put your own figures in.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0f1e; --ink2:#10182e; --paper:#f6f3ec; --line:#e3ddcf;
  --gold:#c9a84c; --mute:#6b6353; --mutei:rgba(255,255,255,.45);
  --save:#1a9e6e; --spend:#c8362b;
  --disp:Fraunces,Georgia,serif; --body:'Space Grotesk',system-ui,sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
body{background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.65}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}

header{background:var(--ink);color:#fff;padding:52px 0 44px;margin-bottom:38px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
h1{font-family:var(--disp);font-weight:900;font-size:clamp(32px,8vw,54px);
  line-height:1;letter-spacing:-.025em}
h1 i{font-style:italic;color:var(--gold)}
.stand{color:var(--mutei);margin-top:16px;max-width:52ch;font-size:15.5px}
.stand b{color:#fff}

h2{font-family:var(--disp);font-weight:900;font-size:clamp(22px,5vw,30px);
  letter-spacing:-.02em;margin-bottom:6px}
.note{color:var(--mute);font-size:14.5px;margin-bottom:22px;max-width:56ch}

section{margin-bottom:40px}

/* device input */
.devices{border:1px solid var(--line);border-left:3px solid var(--ink);
  background:#fff;padding:22px;margin-bottom:14px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--mute);margin-bottom:9px}
.count{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.count input[type=number]{flex:1;min-width:150px;background:var(--paper);
  border:1px solid var(--line);padding:13px 14px;border-radius:4px;
  font-family:var(--mono);font-size:20px;color:var(--ink);outline:none}
.count input:focus{border-color:var(--gold)}
input[type=range]{width:100%;-webkit-appearance:none;appearance:none;height:3px;
  background:var(--line);border-radius:2px;outline:none;margin-top:18px}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;
  border-radius:50%;background:var(--ink);border:4px solid var(--gold);cursor:pointer}
input[type=range]::-moz-range-thumb{width:22px;height:22px;border-radius:50%;
  background:var(--ink);border:4px solid var(--gold);cursor:pointer}
.presets{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
.presets button{background:transparent;border:1px solid var(--line);color:var(--mute);
  font-family:var(--mono);font-size:11.5px;padding:7px 11px;border-radius:3px;cursor:pointer}
.presets button:hover,.presets button.on{border-color:var(--ink);color:var(--ink)}

/* the headline */
.headline{background:var(--ink);color:#fff;padding:30px 24px;margin-bottom:14px}
.hl-l{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.hl-v{font-family:var(--disp);font-weight:900;font-size:clamp(38px,12vw,68px);
  line-height:1;letter-spacing:-.03em;color:#7fe3b0}
.hl-s{color:var(--mutei);font-size:14px;margin-top:12px}

/* the stacked comparison - the signature */
.compare{border:1px solid var(--line);background:#fff;padding:24px}
.row{margin-bottom:26px}
.row:last-child{margin-bottom:0}
.row-h{display:flex;justify-content:space-between;align-items:baseline;
  gap:12px;margin-bottom:10px}
.row-t{font-family:var(--disp);font-weight:600;font-size:18px}
.row-v{font-family:var(--mono);font-size:15px;font-weight:500}
.stack{display:flex;height:44px;border-radius:3px;overflow:hidden;background:var(--paper)}
.seg{position:relative;transition:width .4s ease;min-width:0}
.seg:not(:last-child){border-right:1px solid rgba(255,255,255,.35)}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;
  font-family:var(--mono);font-size:11px;color:var(--mute)}
.legend span{display:flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.gap-note{font-family:var(--mono);font-size:11.5px;color:var(--save);
  margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}

/* assumptions */
.assump{border:1px solid var(--line);background:#fff}
.a-row{display:grid;grid-template-columns:1fr 116px;gap:14px;align-items:center;
  padding:14px 18px;border-bottom:1px solid var(--line)}
.a-row:last-of-type{border-bottom:none}
.a-name{font-size:14.5px}
.a-name small{display:block;color:var(--mute);font-size:12px;margin-top:2px;line-height:1.45}
.a-in{display:flex;align-items:center;gap:5px}
.a-in span{font-family:var(--mono);font-size:13px;color:var(--mute)}
.a-in input{width:100%;background:var(--paper);border:1px solid var(--line);
  padding:9px 10px;border-radius:3px;font-family:var(--mono);font-size:14px;
  color:var(--ink);outline:none;text-align:right}
.a-in input:focus{border-color:var(--gold)}
.a-total{display:grid;grid-template-columns:1fr 116px;gap:14px;padding:15px 18px;
  background:var(--ink);color:#fff;align-items:center}
.a-total .a-name{font-family:var(--disp);font-weight:600;font-size:16px}
.a-total .v{font-family:var(--mono);font-size:15px;text-align:right;color:var(--gold)}
.reset{background:none;border:none;color:var(--mute);font-family:var(--mono);
  font-size:11.5px;text-decoration:underline;cursor:pointer;padding:12px 18px}

/* three year */
.years{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--line);border:1px solid var(--line);margin-top:14px}
.yr{background:#fff;padding:18px 14px;text-align:center}
.yr .l{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--mute);margin-bottom:8px}
.yr .v{font-family:var(--disp);font-weight:900;font-size:clamp(18px,5vw,26px);
  color:var(--save);line-height:1}

.split{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);
  border:1px solid var(--line);margin-bottom:16px}
.half{background:#fff;padding:20px}
.half.measured{border-top:3px solid var(--save)}
.half.modelled{border-top:3px solid var(--gold)}
.h-l{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--mute);margin-bottom:14px}
.measured .h-l{color:var(--save)}
.m-row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
  border-bottom:1px solid var(--line);font-size:13.5px;align-items:baseline}
.m-row:last-of-type{border-bottom:none}
.m-row b{font-family:var(--mono);font-size:13px}
.h-n{font-size:13px;color:var(--mute);line-height:1.65;margin-top:12px}
.sealbox{border:1px dashed var(--gold);background:rgba(201,168,76,.07);padding:22px}
.s-h{font-family:var(--disp);font-weight:900;font-size:19px;margin-bottom:8px}
.s-n{font-size:13.5px;color:var(--mute);line-height:1.65;margin-bottom:16px}
#sealbtn{background:var(--ink);color:#fff;border:none;border-radius:3px;padding:14px 22px;
  font-family:var(--body);font-weight:700;font-size:14px;cursor:pointer}
#sealbtn:hover:not(:disabled){background:#243156}
#sealbtn:disabled{opacity:.5;cursor:default}
#sealout{margin-top:14px;font-family:var(--mono);font-size:12px;line-height:1.9;
  color:var(--mute);word-break:break-all}
#sealout a{color:var(--ink)}
#sealout .ok{color:var(--save)}
#sealout .bad{color:var(--spend)}
@media(max-width:560px){.split{grid-template-columns:1fr}}
.straight{border-left:3px solid var(--gold);background:rgba(201,168,76,.07);
  padding:20px 22px;font-size:14.5px;line-height:1.7;color:var(--mute)}
.straight b{color:var(--ink)}
.straight p+p{margin-top:12px}

.cta{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}
.cta a{display:inline-block;padding:15px 26px;border-radius:3px;text-decoration:none;
  font-weight:700;font-size:14.5px}
.gold{background:var(--gold);color:var(--ink)}
.ghost{border:1px solid var(--line);color:var(--ink)}

footer{border-top:1px solid var(--line);margin-top:44px;padding:26px 0 60px;
  font-family:var(--mono);font-size:11px;color:var(--mute);line-height:1.9}
footer a{color:var(--ink)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(max-width:560px){
  .a-row,.a-total{grid-template-columns:1fr 96px;gap:10px;padding:13px 14px}
  .years{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>

<header>
  <div class="wrap">
    <p class="eyebrow">AILeash · what it costs to prove it</p>
    <h1>Everyone prices the model.<br><i>Nobody prices the proof.</i></h1>
    <p class="stand">At enterprise scale the model is rarely the expensive part. <b>Ingestion, log storage, monitoring, compliance pipelines and the engineering time to hold it all together</b> usually cost more — and none of it proves anything on its own.</p>
  </div>
</header>

<div class="wrap">

<section>
  <h2>Your deployment</h2>
  <p class="note">Everything below recalculates from this.</p>
  <div class="devices">
    <label for="dev">Devices under governance</label>
    <div class="count">
      <input id="dev" type="number" min="100" step="100" value="100000" inputmode="numeric">
    </div>
    <input id="devr" type="range" min="2" max="6" step="0.01" value="5">
    <div class="presets">
      <button data-n="10000">10k</button>
      <button data-n="25000">25k</button>
      <button data-n="50000">50k</button>
      <button data-n="100000" class="on">100k</button>
      <button data-n="250000">250k</button>
      <button data-n="500000">500k</button>
    </div>
  </div>
</section>

<section>
  <div class="headline">
    <p class="hl-l">Potential annual saving</p>
    <p class="hl-v" id="save">—</p>
    <p class="hl-s" id="save-sub">—</p>
  </div>

  <div class="compare">
    <div class="row">
      <div class="row-h">
        <span class="row-t">Traditional compliance architecture</span>
        <span class="row-v" id="trad-v">—</span>
      </div>
      <div class="stack" id="trad-stack"></div>
      <div class="legend" id="trad-legend"></div>
    </div>

    <div class="row">
      <div class="row-h">
        <span class="row-t">Proof-based, on AILeash</span>
        <span class="row-v" id="proof-v">—</span>
      </div>
      <div class="stack" id="proof-stack"></div>
      <div class="legend">
        <span><i class="sw" style="background:#c9a84c"></i>50p per device per month, flat</span>
      </div>
    </div>

    <p class="gap-note" id="gap">—</p>
  </div>

  <div class="years">
    <div class="yr"><div class="l">Year one</div><div class="v" id="y1">—</div></div>
    <div class="yr"><div class="l">Three years</div><div class="v" id="y3">—</div></div>
    <div class="yr"><div class="l">Per device, per year</div><div class="v" id="ypd">—</div></div>
  </div>
</section>

<section>
  <h2>Change any of these</h2>
  <p class="note">These are the figures the saving rests on. They are illustrative, and yours will differ — so put yours in. The arithmetic follows whatever you type.</p>
  <div class="assump" id="assump">
    <div class="a-row">
      <div class="a-name">Data ingestion
        <small>Getting decision data out of your systems and into somewhere it can be queried.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ingest" value="3.20" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Log storage
        <small>Retention at the volumes an audit trail implies, for as long as the regulation implies.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-store" value="2.80" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Monitoring platform
        <small>Licences and seats on whatever watches it.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-monitor" value="2.40" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Compliance pipeline
        <small>Turning raw logs into something a regulator will accept.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-pipeline" value="2.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Engineering time
        <small>Building it, and keeping it running once it exists.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-eng" value="1.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">AILeash
        <small>50p per device per month. Change it if you have been quoted something else.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ail" value="6.00" step="0.50" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-total">
      <div class="a-name">Traditional, per device per year</div>
      <div class="v" id="a-sum">—</div>
    </div>
  </div>
  <button class="reset" id="reset">Put the illustrative figures back</button>
</section>

<section>
  <h2>What is measured, and what is modelled</h2>
  <p class="note">The two halves of this page are not the same kind of number, and it matters which is which.</p>

  <div class="split">
    <div class="half measured">
      <div class="h-l">Measured — read from the live chain just now</div>
      <div class="m-row"><span>Blocks sealed</span><b id="m-height">…</b></div>
      <div class="m-row"><span>Bytes per seal</span><b>32</b></div>
      <div class="m-row"><span>Size of the record behind it</span><b>irrelevant</b></div>
      <div class="m-row"><span>External timestamp</span><b id="m-anchor">…</b></div>
      <p class="h-n">A seal is a SHA-256 digest. Thirty-two bytes, whether the decision behind it is one line or a megabyte. That is not a claim about our architecture, it is what a hash is — and it is the whole reason the cost stops tracking the volume.</p>
    </div>
    <div class="half modelled">
      <div class="h-l">Modelled — assumptions, including yours</div>
      <div class="m-row"><span>What you spend today</span><b>your figures</b></div>
      <div class="m-row"><span>What you would stop spending</span><b>an estimate</b></div>
      <p class="h-n">Nobody can prove what an organisation <i>would have</i> spent. That number does not exist anywhere to be measured, here or in any vendor's business case. What this page can do is make the assumptions visible and let you replace every one of them.</p>
    </div>
  </div>

  <div class="sealbox">
    <div class="s-h">Seal this calculation</div>
    <p class="s-n">Puts your inputs and the result into the audit chain, dated and tamper-evident, and hands you a receipt anyone can check. Then what was modelled, and on whose assumptions, is a matter of record rather than of memory — including ours.</p>
    <button id="sealbtn">Seal it and give me a receipt</button>
    <div id="sealout"></div>
  </div>
</section>

<section>
  <h2>Why a proof layer costs less</h2>
  <p class="note">It is not a discount on the same architecture. It is less architecture.</p>
  <div class="straight">
    <p><b>Most of that cost is moving and keeping data.</b> Sensitive records get shipped somewhere central, held for years, indexed so they can be searched, and watched so nothing goes missing — because the plan is to reconstruct what happened by reading it all back later.</p>
    <p><b>A proof-based layer answers the question at the moment the decision is made.</b> The decision is scored, sealed into a hash chain, externally timestamped and recorded by an independent platform. What survives is a proof that the decision happened, under stated rules, and has not been altered since.</p>
    <p><b>So the volume stops being the problem.</b> A seal is the same size whether the record behind it is a line or a megabyte, and it does not have to leave your systems for the proof to hold. You keep your own data where it already is.</p>
    <p>It does not replace your logs, and it is not meant to. It replaces the machinery built to make logs trustworthy — which is the part that scales badly.</p>
  </div>
  <div class="cta">
    <a class="gold" href="/#signup">Get an API key · 90 days free</a>
    <a class="ghost" href="/whitepaper">Read the whitepaper</a>
    <a class="ghost" href="/api/verify-chain">Check the chain</a>
  </div>
</section>

<footer>
  Illustrative model. Real figures vary with cloud provider, data volume, retention policy, engineering rates and existing contracts — which is why every input above is yours to change. No saving is guaranteed and nothing here is a quotation.<br>
  <a href="https://sebbi.pro">sebbi.pro</a> · Monop Content, Blyth
</footer>

</div>

<script>
(function(){
  var DEFAULTS = { ingest:3.20, store:2.80, monitor:2.40, pipeline:2.60, eng:1.60, ail:6.00 };
  var SEGMENTS = [
    { id:'ingest',   label:'Data ingestion',      colour:'#0a0f1e' },
    { id:'store',    label:'Log storage',         colour:'#243156' },
    { id:'monitor',  label:'Monitoring',          colour:'#3d4f7d' },
    { id:'pipeline', label:'Compliance pipeline', colour:'#5b6e9e' },
    { id:'eng',      label:'Engineering time',    colour:'#8794b8' }
  ];

  var $ = function(id){ return document.getElementById(id); };
  var dev = $('dev'), devr = $('devr');

  function money(n){
    if(!isFinite(n)) return '—';
    if(Math.abs(n) >= 1000000) return '£' + (n/1000000).toFixed(2).replace(/\.00$/,'') + 'm';
    return '£' + Math.round(n).toLocaleString('en-GB');
  }
  function per(n){ return '£' + n.toFixed(2); }
  function val(id){
    var v = parseFloat($(id).value);
    return (isFinite(v) && v >= 0) ? v : 0;
  }
  function devices(){
    var v = parseInt(dev.value, 10);
    if(!isFinite(v) || v < 1) v = 1;
    return v;
  }

  function draw(){
    var n = devices();
    var parts = SEGMENTS.map(function(s){ return { s:s, v: val('a-' + s.id) }; });
    var tradPer = parts.reduce(function(a,p){ return a + p.v; }, 0);
    var ailPer = val('a-ail');

    var trad = tradPer * n, proof = ailPer * n, saved = trad - proof;

    $('a-sum').textContent = per(tradPer);
    $('trad-v').textContent = money(trad) + ' / year';
    $('proof-v').textContent = money(proof) + ' / year';

    $('save').textContent = saved > 0 ? money(saved) : money(0);
    $('save').style.color = saved > 0 ? '#7fe3b0' : '#ffb4ad';
    $('save-sub').textContent = n.toLocaleString('en-GB') + ' devices · ' +
      per(tradPer) + ' against ' + per(ailPer) + ' per device per year';

    // stacked bars, both scaled to the larger of the two
    var scale = Math.max(tradPer, ailPer) || 1;
    var tradHtml = '', legendHtml = '';
    parts.forEach(function(p){
      if(p.v <= 0) return;
      tradHtml += '<div class="seg" style="width:' + ((p.v/scale)*100) + '%;background:' +
        p.s.colour + '" title="' + p.s.label + ' · ' + per(p.v) + '"></div>';
      legendHtml += '<span><i class="sw" style="background:' + p.s.colour + '"></i>' +
        p.s.label + ' ' + per(p.v) + '</span>';
    });
    $('trad-stack').innerHTML = tradHtml;
    $('trad-legend').innerHTML = legendHtml;
    $('proof-stack').innerHTML = '<div class="seg" style="width:' +
      ((ailPer/scale)*100) + '%;background:#c9a84c"></div>';

    if(saved > 0){
      var pct = Math.round((saved / (tradPer * n)) * 100);
      $('gap').textContent = 'The gap is ' + money(saved) + ' a year — about ' + pct +
        '% of the traditional figure, on these inputs.';
      $('gap').style.color = '#1a9e6e';
    } else if(saved === 0){
      $('gap').textContent = 'On these inputs the two cost the same.';
      $('gap').style.color = '#6b6353';
    } else {
      $('gap').textContent = 'On these inputs the proof layer costs ' + money(-saved) +
        ' a year more. Worth knowing, and worth saying.';
      $('gap').style.color = '#c8362b';
    }

    $('y1').textContent = money(Math.max(0, saved));
    $('y3').textContent = money(Math.max(0, saved * 3));
    $('ypd').textContent = per(Math.max(0, tradPer - ailPer));

    document.querySelectorAll('.presets button').forEach(function(b){
      b.classList.toggle('on', parseInt(b.dataset.n,10) === n);
    });
  }

  // slider is logarithmic: 100 to 1,000,000
  function syncFromSlider(){
    dev.value = Math.round(Math.pow(10, parseFloat(devr.value)) / 100) * 100;
    draw();
  }
  function syncFromNumber(){
    var n = devices();
    devr.value = Math.min(6, Math.max(2, Math.log(n) / Math.LN10));
    draw();
  }

  devr.addEventListener('input', syncFromSlider);
  dev.addEventListener('input', syncFromNumber);
  document.querySelectorAll('.presets button').forEach(function(b){
    b.addEventListener('click', function(){
      dev.value = b.dataset.n; syncFromNumber();
    });
  });
  document.querySelectorAll('#assump input').forEach(function(i){
    i.addEventListener('input', draw);
  });
  $('reset').addEventListener('click', function(){
    Object.keys(DEFAULTS).forEach(function(k){ $('a-' + k).value = DEFAULTS[k].toFixed(2); });
    draw();
  });

  syncFromNumber();

  // ---- measured half: read the live chain, do not assert it
  (async function(){
    try{
      var r = await fetch('/x/stats');
      if(r.ok){
        var d = await r.json();
        var h = (d.chain && d.chain.height);
        $('m-height').textContent = h ? h.toLocaleString('en-GB') : 'unavailable';
      } else { $('m-height').textContent = 'unavailable'; }
    }catch(e){ $('m-height').textContent = 'unavailable'; }
    try{
      var a = await fetch('/api/anchor-status');
      if(a.ok){
        var ad = await a.json();
        var cal = ad.calendars || ad.calendar_count;
        $('m-anchor').textContent = cal ? (cal + ' calendars') : 'live';
      } else { $('m-anchor').textContent = 'unavailable'; }
    }catch(e){ $('m-anchor').textContent = 'unavailable'; }
  })();

  // ---- seal the calculation
  var sealbtn = $('sealbtn'), sealout = $('sealout');
  sealbtn.addEventListener('click', async function(){
    sealbtn.disabled = true;
    sealout.innerHTML = 'sealing…';
    var body = {
      devices: devices(),
      assumptions: {
        ingestion: val('a-ingest'), storage: val('a-store'),
        monitoring: val('a-monitor'), pipeline: val('a-pipeline'),
        engineering: val('a-eng'), aileash: val('a-ail')
      }
    };
    try{
      var r = await fetch('/x/savings/seal', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      var d = await r.json();
      if(r.status === 429){
        sealout.innerHTML = '<span class="bad">Rate limited. Give it a minute.</span>';
      } else if(!r.ok || !d.receipt){
        sealout.innerHTML = '<span class="bad">' +
          ((d && (d.message || d.error)) || ('HTTP ' + r.status)) + '</span>';
      } else {
        sealout.innerHTML =
          '<span class="ok">Sealed at block ' + d.block_index + '</span><br>' +
          'receipt ' + d.receipt + '<br>' +
          '<a href="' + d.verify + '" target="_blank" rel="noopener">check it yourself →</a>';
      }
    }catch(e){
      sealout.innerHTML = '<span class="bad">Could not reach the server.</span>';
    }
    sealbtn.disabled = false;
  });
})();
</script>
</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_savings_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._savings_patched = True
    _patched[0] = True
    print("SAVINGS: /savings page installed at runtime", flush=True)
    return "installed"


def _seal(ctx, api_key, data):
    try:
        devices = int(data.get("devices", 0))
    except (TypeError, ValueError):
        devices = 0
    if devices < 1 or devices > 100000000:
        return {"error": "devices_required",
                "message": "Send a device count between 1 and 100,000,000."}, 400

    a = data.get("assumptions")
    if not isinstance(a, dict):
        return {"error": "assumptions_required"}, 400

    fields = ["ingestion", "storage", "monitoring", "pipeline", "engineering", "aileash"]
    vals = {}
    for f in fields:
        try:
            v = float(a.get(f, 0))
        except (TypeError, ValueError):
            v = 0.0
        if v < 0 or v > 100000:
            v = 0.0
        vals[f] = round(v, 2)

    traditional_per = round(sum(vals[f] for f in fields if f != "aileash"), 2)
    proof_per = vals["aileash"]
    traditional = round(traditional_per * devices, 2)
    proof = round(proof_per * devices, 2)
    saving = round(traditional - proof, 2)

    ts = time.time()
    detail = ("devices=" + str(devices) +
              ";" + ";".join("%s=%.2f" % (f, vals[f]) for f in fields) +
              ";traditional_per=%.2f;proof_per=%.2f;saving=%.2f"
              % (traditional_per, proof_per, saving))

    ev = {"user_id": "sav:" + str(devices), "action": "savings_modelled",
          "amount": 0, "country": "UK", "device_id": "savings",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SAVINGS_SEALED", "score": 0, "savings_version": VERSION,
           "devices": devices, "assumptions": vals,
           "traditional_per_device_year": traditional_per,
           "proof_per_device_year": proof_per,
           "annual_saving": saving, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO savings_model(api_key,devices,assumptions,traditional_per,"
            "proof_per,annual_saving,modelled,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, devices, json.dumps(vals), traditional_per, proof_per,
             saving, ts, h, idx))
        ctx["conn"].commit()

    return {
        "sealed": True,
        "receipt": h,
        "block_index": idx,
        "receipt_seq": seq,
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "devices": devices,
        "assumptions": vals,
        "traditional_per_device_year": traditional_per,
        "proof_per_device_year": proof_per,
        "annual_saving": saving,
        "verify": "/x/savings/verify?receipt=" + h,
        "what_this_proves": ("That this calculation, on these assumptions, was run at "
                             "this time and has not been altered since. It does not "
                             "prove the assumptions are right - they are yours - and "
                             "no record can prove what an organisation would otherwise "
                             "have spent."),
    }, 200


def _verify(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT devices,assumptions,traditional_per,proof_per,annual_saving,"
            "modelled,block_index FROM savings_model WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No calculation with that receipt exists in this chain."}, 404
    try:
        assumptions = json.loads(row[1])
    except Exception:
        assumptions = {}
    return {
        "found": True, "receipt": receipt,
        "devices": row[0], "assumptions": assumptions,
        "traditional_per_device_year": row[2],
        "proof_per_device_year": row[3],
        "annual_saving": row[4],
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[5])),
        "block_index": row[6],
        "proof": ("This calculation is a block in a hash chain that is externally "
                  "timestamped and recorded by an independent platform. Altering or "
                  "removing it breaks every block after it."),
        "chain": "/api/verify-chain",
        "external_clock": "/api/anchor-status",
    }, 200


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("SAVINGS: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "seal":
            _setup(ctx)
            return _seal(ctx, api_key or "public-savings", data)
        return {"error": "unknown_action", "action": action, "POST": ["seal"]}, 404

    if action in ("", "status"):
        return {
            "page": "/savings",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": ("The calculator runs in the browser. Nothing a visitor types is "
                     "submitted unless they choose to seal it."),
        }, 200
    if action == "verify":
        _setup(ctx)
        return _verify(ctx, data)
    return {"error": "unknown_action", "action": action,
            "GET": ["status", "verify"], "POST": ["seal"]}, 404

```


## `modules/spec.py`

121 lines, 5086 bytes

```python
"""
Live API specification - /x/spec

/api/spec is a hardcoded constant. It describes the API as it was when
somebody last remembered to update it, which is a documentation problem
pretending to be a feature.

This discovers what is actually loaded, right now, by reading the modules
directory and each module's own docstring. Add a module and the spec
updates itself. Delete one and it disappears. There is no separate list to
maintain and therefore no list that can drift.

That matters here more than it would elsewhere: a platform whose pitch is
"check it, don't trust it" should not ship a self-description that is
quietly out of date.

    GET /x/spec           everything currently live
    GET /x/spec/modules   just the module list
"""

import importlib, os, pkgutil, re

VERSION = "1.0"

_EP = re.compile(r"^\s*(GET|POST|PUT|DELETE)\s+(/\S+)\s*(.*)$")


def _describe(name):
    """Pull a module's summary and endpoint list out of its own docstring."""
    try:
        m = importlib.import_module("modules." + name)
    except Exception as e:
        return {"module": name, "loaded": False, "error": str(e)}
    doc = (m.__doc__ or "").strip()
    lines = doc.splitlines()
    summary = ""
    for ln in lines:
        t = ln.strip()
        if t and not t.startswith("-") and not _EP.match(ln):
            summary = t
            break
    endpoints = []
    for ln in lines:
        mm = _EP.match(ln)
        if mm:
            endpoints.append({"method": mm.group(1),
                              "path": mm.group(2),
                              "takes": mm.group(3).strip() or None})
    out = {"module": name, "loaded": True, "summary": summary,
           "endpoints": endpoints,
           "version": getattr(m, "VERSION", None)}
    if not hasattr(m, "handle"):
        out["warning"] = "module has no handle() - it will not route"
    return out


def _modules():
    d = os.path.dirname(__file__)
    names = sorted(x.name for x in pkgutil.iter_modules([d])
                   if x.name not in ("router", "spec"))
    return [_describe(n) for n in names]


def handle(method, action, data, api_key, ctx):
    if method != "GET":
        return {"error": "unknown_action", "action": action}, 404

    mods = _modules()

    if action == "modules":
        return {"count": len(mods), "modules": mods}, 200

    if action in ("", "all"):
        return {
            "spec_version": VERSION,
            "generated": "live - discovered at request time, not a stored list",
            "core": {
                "decision_engine": {
                    "path": "/api/govern",
                    "method": "POST",
                    "auth": "Bearer key",
                    "note": "deterministic scoring, verdict sealed before the response returns"
                },
                "notaries_public": [
                    {"method": "POST", "path": "/api/post/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/verify-post", "auth": "none"},
                    {"method": "POST", "path": "/api/identity/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/identity/check", "auth": "none"},
                    {"method": "POST", "path": "/api/payment/seal", "auth": "none"},
                    {"method": "GET", "path": "/api/payment/check", "auth": "none"}
                ],
                "verification_public": [
                    {"method": "GET", "path": "/api/verify-chain",
                     "returns": "whole-chain integrity, recomputed"},
                    {"method": "GET", "path": "/api/inclusion",
                     "returns": "whether a given 64-char hash is sealed"},
                    {"method": "GET", "path": "/api/anchor-status",
                     "returns": "current tip, OpenTimestamps proof, calendar count"},
                    {"method": "GET", "path": "/api/regulation-map",
                     "returns": "engine features mapped to legal obligations"}
                ]
            },
            "modules": {
                "prefix": "/x/<module>/<action>",
                "auth": "Bearer key on every module route",
                "count": len(mods),
                "loaded": mods
            },
            "chain": {
                "algorithm": "SHA-256 hash chain",
                "scope": "one chain - every module seals into the same sequence as /api/govern",
                "anchoring": "chain tip submitted to OpenTimestamps, aggregated into a Merkle root, root committed to Bitcoin by several independent calendars",
                "receipts": "gapless per-key sequence issued in the same transaction as the chain write",
                "verify": "/api/verify-chain and /api/anchor-status, both without a key"
            },
            "honest_note": "This spec is generated by reading the modules directory at request time rather than from a stored list, so it cannot describe capabilities that are not actually loaded."
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["", "modules"]}, 404

```


## `modules/standard.py`

401 lines, 17637 bytes

```python
"""
modules/standard.py  -  the Ordering Test discovery document for this domain

WHAT IT SERVES
--------------
  GET /.well-known/ordering-test.json   this operator's discovery document
  GET /x/standard/hash                  sha256 of that document
  GET /x/standard/status                what is installed, and honest counts

SHAPE
-----
Deliberately identical to the shape Red Flag AI Pro published first:

    checks: { <name>: { supported, demonstrable_publicly, endpoint, note } }

Two fields, not one, and the second is the better idea. "We built it" and
"you can verify it without an account" are different claims, and most of this
market blurs them. Separating them lets a vendor be honest about having
something real that an outsider still has to take on trust.

WHAT THE HOST HEADER IS DOING HERE
----------------------------------
base_url is derived from the request rather than written into the file. An
earlier draft had the domain hardcoded, which meant any operator running it
would publish somebody else's domain as the source - the opposite of a mirror.
Deriving it means this file can be lifted to any domain and tells the truth
about wherever it is actually running.

EVERY PUBLISHED ENDPOINT MUST WORK AS WRITTEN
---------------------------------------------
An endpoint marked demonstrable_publicly is a promise that a stranger can copy
it out of this document and get an answer. If the route needs a parameter, the
document names that parameter. If a value has to be discovered first, the
document says where to discover it. An endpoint that errors when followed
literally is a failed check, not a documentation detail.

HONESTY RULES THIS FILE FOLLOWS
-------------------------------
  - A check we have not built says supported: false. It does not quietly go
    missing from the document.
  - A check that exists but needs an account says demonstrable_publicly:
    false, however much we would like the tick.
  - runner is null. A runner exists in draft, but the checks have not been
    jointly agreed with the other mirror, so publishing one as though it were
    a settled standard would claim something neither operator has earned yet.

None of that is modesty. A conformance document whose author scores full marks
on the day they publish it is a marketing page.
"""

import hashlib
import json
import sys

VERSION = "1.1"
ORDERING_TEST_VERSION = "0.1"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec"),
          ("GET", "document")}

# Several paths on purpose. /.well-known/ is where the standard says to look,
# but some platforms and static handlers reserve that prefix, so a plain root
# path is served as well. /x/standard/document goes through the normal router
# and cannot be intercepted by anything, which makes it the diagnostic.
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",
                   "/ordering-test.json",
                   "/well-known/ordering-test.json")

VENDOR = "AILeash"
FALLBACK_BASE = "https://sebbi.pro"

RUNNER = None
RUNNER_NOTE = (
    "No shared runner file is published here yet. The checks themselves have "
    "not been jointly agreed with the other mirrors as of this document's "
    "publication. This describes AILeash's own side only, not a settled "
    "cross-vendor standard.")

# Order follows the other mirror's document so the two read side by side.
CHECKS = {
    "rule_binding": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/rulebind/prove",
        "note": ("The ruleset version is a component of a digest sealed with the "
                 "decision, not a field beside it. POST any inputs without an "
                 "account and the response returns the exact string that was "
                 "hashed - SHA-256 it yourself and confirm it matches. Alter the "
                 "ruleset hash and the digest stops recomputing; alter the digest "
                 "and the chain breaks. Verify a past record at "
                 "/x/rulebind/verify?receipt=... and see ruleset history at "
                 "/x/rulebind/packs. No scoring logic is disclosed at any point - "
                 "inputs are published as a digest, never as values."),
    },
    "commit_before_reveal": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/demo/review",
        "note": ("The reviewer receives the case with the machine verdict "
                 "withheld. Their own call and dwell time are sealed first, "
                 "then the verdict is revealed, and the chain fixes that order "
                 "permanently. No account needed - open a case, commit a "
                 "verdict, and check the block indices yourself. Commit "
                 "endpoint is /x/demo/commit."),
    },
    "authority_tokens": {
        "supported": True,
        "demonstrable_publicly": False,
        "endpoint": None,
        "note": ("Signed authority tokens with scope and expiry. A decision "
                 "beyond delegated authority escalates rather than executes, "
                 "and the delegation itself is sealed. Built and live, "
                 "key-gated, no public proof."),
    },
    "mutual_witnessing": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/witness/peers",
        "note": ("Live, running both directions with an external peer chain "
                 "hourly since 1 August 2026. No account needed, run it "
                 "yourself. Our current tip is at /x/witness/tip and any party "
                 "can submit theirs at /x/witness/observe without an account."),
    },
    "completeness_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/root?period={period}&kind=receipts",
        "note": ("Per-period sorted Merkle root and exact leaf count, committed "
                 "before any export is requested. An export can then be checked "
                 "against a number fixed before anyone knew it would be asked "
                 "for. Committed periods are listed at /x/complete/periods - "
                 "take a period identifier from there and substitute it. Only "
                 "closed periods can be committed, so the current period will "
                 "not appear until it ends. A period listed nowhere is a period "
                 "nobody committed, which is itself the finding."),
    },
    "absence_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/complete/prove?period={period}&value={value}",
        "note": ("Two adjacent leaves with consecutive indices demonstrate that "
                 "nothing sits between them, so absence is proved rather than "
                 "asserted. Both parameters are required: take a period from "
                 "/x/complete/periods and supply any value you like. Try a "
                 "value that is not there."),
    },
    "reconciliation": {
        "supported": True,
        "demonstrable_publicly": False,
        "endpoint": None,
        "note": ("Sample selected from the live chain tip and sealed before any "
                 "data is requested, so flattering records cannot be "
                 "cherry-picked. Mismatches sealed as permanently as matches. "
                 "Built and live, key-gated, no public proof."),
    },
    "reproducibility": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/replay/challenge",
        "note": ("Determinism proved by public challenge without disclosing any "
                 "scoring logic. Submit inputs, the run is sealed, resubmit the "
                 "same inputs later and the verdict must be identical under an "
                 "unchanged code fingerprint at /x/replay/fingerprint."),
    },
    "consistency_proof": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/x/consistency/proof?first={first}&second={second}",
        "note": ("RFC 6962 consistency proofs, deliberately unmodified so "
                 "existing Certificate Transparency verifiers work against them "
                 "directly. first and second are tree sizes - read the current "
                 "size from /x/consistency/root and pick any earlier one. "
                 "Anyone holding any earlier tip we served can show it is a "
                 "prefix of the current log at /x/consistency/ancestor."),
    },

    # ---- proposed addition, flagged as a proposal rather than assumed ----
    "external_anchoring": {
        "supported": True,
        "demonstrable_publicly": True,
        "endpoint": "/api/anchor-status",
        "note": ("PROPOSED AS A SEPARATE CHECK, not settled. The other mirror "
                 "currently folds anchoring into consistency_proof, but they "
                 "answer different questions: consistency shows the log only "
                 "ever grew, anchoring shows the time was fixed somewhere the "
                 "operator cannot reach. A log can be perfectly append-only and "
                 "still have been built last week. Here the tip is submitted to "
                 "OpenTimestamps and committed into Bitcoin; the other mirror "
                 "uses an RFC 3161 timestamp. The spec should permit any "
                 "external authority the operator does not control and require "
                 "it to be named - not mandate one. Offered for the joint "
                 "session."),
    },
}

DOCUMENT_NOTE = (
    "Every endpoint marked demonstrable_publicly is unauthenticated by design - "
    "run it yourself without asking us. Where an endpoint carries a {parameter}, "
    "the note for that check says where to get a valid value; every published "
    "endpoint is meant to work when followed literally, and one that does not is "
    "a failed check on our side, not a quibble. Checks marked supported but not "
    "demonstrable_publicly are real and built, but currently need a key to see, "
    "and say so plainly rather than passing on the day this was published. "
    "Nothing here proves the records are true. It describes the order things "
    "were committed in, which is a narrower claim and the only one that holds.")

_patched = [False]


def _base_from(handler):
    """Derive our own base URL from the request. An operator running this file
    on their own domain publishes their domain, not whoever wrote it."""
    try:
        host = handler.headers.get("X-Forwarded-Host") or handler.headers.get("Host")
        if not host:
            return FALLBACK_BASE
        host = host.split(",")[0].strip()[:200]
        proto = (handler.headers.get("X-Forwarded-Proto") or "https").split(",")[0].strip()
        if proto not in ("http", "https"):
            proto = "https"
        return proto + "://" + host
    except Exception:
        return FALLBACK_BASE


def _base_from_ctx(ctx):
    """Same derivation for the routed /x/standard/document call.

    The router's ctx may or may not carry the request handler. If it does, the
    document served through the router names the same domain as the one served
    at /.well-known/ - which matters on a mirror, where hardcoding would make
    this file publish somebody else's domain again."""
    try:
        if isinstance(ctx, dict):
            for key in ("handler", "h", "request", "req", "self"):
                obj = ctx.get(key)
                if obj is not None and hasattr(obj, "headers"):
                    return _base_from(obj)
            headers = ctx.get("headers")
            if headers is not None:
                class _Shim(object):
                    pass
                shim = _Shim()
                shim.headers = headers
                return _base_from(shim)
        elif ctx is not None and hasattr(ctx, "headers"):
            return _base_from(ctx)
    except Exception:
        pass
    return FALLBACK_BASE


def _document(base):
    checks = {}
    for name, c in CHECKS.items():
        checks[name] = {
            "supported": c["supported"],
            "demonstrable_publicly": c["demonstrable_publicly"],
            "endpoint": c["endpoint"],
            "note": c["note"],
        }
    return {
        "ordering_test_version": ORDERING_TEST_VERSION,
        "vendor": VENDOR,
        "base_url": base,
        "runner": RUNNER,
        "runner_note": RUNNER_NOTE,
        "checks": checks,
        "witness_peers": base + "/x/witness/peers",
        "witness_tip": base + "/x/witness/tip",
        "committed_periods": base + "/x/complete/periods",
        "note": DOCUMENT_NOTE,
    }


def _digest(doc):
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in DISCOVERY_PATHS:
            body = json.dumps(_document(_base_from(self)), indent=2).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /.well-known/ordering-test.json installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    base = _base_from_ctx(ctx)
    doc = _document(base)

    if method == "GET" and action == "document":
        return doc, 200

    if method == "GET" and action == "hash":
        canonical = _document(FALLBACK_BASE)
        return {
            "sha256": _digest(canonical),
            "of": "this operator's discovery document",
            "canonicalisation": ("JSON, keys sorted, no whitespace, UTF-8, "
                                 "base_url fixed to " + FALLBACK_BASE +
                                 " so the digest does not move with the "
                                 "requesting host"),
            "what_this_is_for": (
                "Confirming our own document has not changed. It is NOT the "
                "cross-mirror check - two operators publish different documents "
                "by design, because they list different endpoints, so their "
                "digests should differ and a mismatch would prove nothing. The "
                "cross-mirror comparison only means something once every mirror "
                "serves a byte-identical runner file and hashes that instead. "
                "No runner is agreed yet."),
            "document": canonical,
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        supported = [k for k, c in CHECKS.items() if c["supported"]]
        public = [k for k, c in CHECKS.items() if c["demonstrable_publicly"]]
        parameterised = [k for k, c in CHECKS.items()
                         if c["endpoint"] and "{" in c["endpoint"]]
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "ordering_test_version": ORDERING_TEST_VERSION,
            "serving": list(DISCOVERY_PATHS),
            "always_available": "/x/standard/document",
            "checks_total": len(CHECKS),
            "checks_supported": len(supported),
            "checks_publicly_demonstrable": len(public),
            "publicly_demonstrable": public,
            "supported_but_not_public": [k for k in supported if k not in public],
            "endpoints_needing_a_parameter": parameterised,
            "runner": RUNNER,
            "note": ("base_url is derived from the Host header, so this file "
                     "publishes whichever domain is actually serving it. Checks "
                     "listed under endpoints_needing_a_parameter cannot be "
                     "demonstrated until a real value exists to substitute - "
                     "for the completeness and absence checks that means at "
                     "least one committed period at /x/complete/periods."),
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash", "document"]}, 404

```
