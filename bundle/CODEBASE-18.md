# Codebase — part 18 of 41

Contains:
- `modules/replay.py`
- `modules/roster.py`
- `modules/router.py`
- `modules/rulebind.py`


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


## `modules/roster.py`

604 lines, 26550 bytes

```python
"""modules/roster.py v1.4 - the canonical network list.

Publishes every party that has submitted a tip here, so a peer's sync can
witness everybody rather than just whoever introduced them. Witnesses
nothing itself.

v1.4 - the decaying fields.
hours_since and status are computed when the response is generated and
are wrong the moment the document is cached. A stale copy served every
peer at hours_since 0.0 and status current, against this route's own
six-hour definition, while how_to_use tells peers to poll it. Rewording
does not reach that. So the response now carries the epoch it was
generated at, an explicit freshness block, and every decaying field is
marked as computed-at-generation. A reader can compare generated_epoch
against their own clock and discard a document that has aged.
Found by Ishaan (Shango MID) in a stale read of this route.

v1.3 fixed three read-side faults from the same reviewer: the bound /
unbound disagreement with /x/bind/name, witnessable claiming more than it
checked, and the unbound wording asserting unreachability.

Nothing here seals. This module only reads.
"""

import time

VERSION = "1.4"

PUBLIC = {("GET", "list"), ("GET", "spec"), ("GET", "health")}

CURRENT_UNDER_HOURS = 6
SILENT_AFTER_HOURS = 48

# How long this document's decaying fields stay meaningful. Past this, a
# reader should refetch rather than believe hours_since.
FRESH_FOR_SECONDS = 120

SELF_CHAIN = "sebbi.pro"
SELF_TIP = "https://sebbi.pro/x/witness/tip"
SELF_OBSERVE = "https://sebbi.pro/x/witness/observe"
SELF_SIGNED = "https://sebbi.pro/x/signed/submit"

DECAYING_FIELDS = ("hours_since", "status", "generated", "generated_epoch")

LIVENESS_VOCABULARY = {
    "self-consistent": "The url the submitter gave served exactly the tip "
        "the submitter sent. Both halves came from the submitter, so this "
        "records self-consistency - NOT verification by us or anyone else.",
    "confirmed": "The same check as self-consistent, under the name used "
        "before witness v1.2. Sealed blocks cannot be altered, so older "
        "records still carry the original word.",
    "live": "The url served a valid but different tip. A chain that moves "
        "between submitting and our fetching is normal, not a failure.",
    "self-declared": "Either no url was given, or the url did not return "
        "JSON we could read a tip from. Taken on the submitter's word and "
        "checked by nobody. Not a finding about reachability - a page "
        "serving HTML is reachable and still lands here.",
    "peer-signed": "Submitted through /x/signed/submit and verified against "
        "an Ed25519 public key the submitter enrolled. We hold only the "
        "public half, so we could not have produced that signature.",
    "self": "This deployment's own entry. Not a check of anything.",
    "unchecked": "Recorded before liveness checking existed.",
}

NAME_VOCABULARY = {
    "first-use": "First time this name was seen with a url that returned a "
        "tip in JSON, so the name is bound to that address network-wide. A "
        "later submission from a different address records as conflict.",
    "bound": "Submitted from the same url this name was first bound to.",
    "conflict": "Submitted from a different address than the one it was "
        "first bound to. Not proof of theft - operators move hosts - but "
        "it is the event an auditor needs to see.",
    "unbound": "No url has yet returned a tip in JSON under this name on "
        "the open lane, so there is nothing here to bind the name to an "
        "address. This says nothing about whether the url is reachable: a "
        "url serving HTML is reachable and still leaves a name unbound. An "
        "unbound name stays claimable on the open lane by whoever next "
        "submits it WITH a url that returns JSON - unless a credential or "
        "key is held for it, which the binding block reports separately.",
    "key-bound": "Bound to an Ed25519 public key rather than a host "
        "address. Only the holder of the private key can submit under it, "
        "and that holder is not us.",
    "publisher": "The deployment publishing this roster.",
    "unchecked": "Recorded before name binding existed.",
}

STATUS_VOCABULARY = {
    "current": "observed within the last %dh" % CURRENT_UNDER_HOURS,
    "stale": "last observed between %dh and %dh ago"
             % (CURRENT_UNDER_HOURS, SILENT_AFTER_HOURS),
    "silent": "not observed for more than %dh" % SILENT_AFTER_HOURS,
    "unknown": "we hold no usable timestamp for this entry",
    "read_this": "These describe elapsed time since we last recorded an "
        "observation, and nothing else. A peer publishing on a human "
        "schedule reads stale between sessions, correctly. It is not a "
        "claim that anyone's endpoint was unavailable.",
    "computed_when": "At generation. If this document has been cached, "
        "every one of these words is as old as the document. Check "
        "freshness.generated_epoch against your own clock before using "
        "them.",
}

BINDING_VOCABULARY = {
    "open_lane": "What witness.py recorded: whether a url served back the "
        "tip it was sent with. An address-level fact.",
    "signed_lane": "What bind.py holds: a live credential, a dated claim, "
        "or nothing. A possession-level fact. /x/bind/name is authority.",
    "agree": "true when both lanes say the name is held, false when they "
        "disagree, null when the signed lane has no record. A false is not "
        "a fault - the lanes check different things.",
    "none": "bind.py holds no credential and no claim for this name.",
    "claimed": "bind.py holds a dated claim but no live credential.",
    "credential": "bind.py holds a live credential for this name.",
    "unavailable": "bind.py is not deployed here or its tables cannot be "
        "read. Absence of an answer, not an answer.",
}

SUBMIT_NOTE = ("Unknown. This deployment records where it can FETCH a "
    "peer's tip. It has no record of whether that peer runs an endpoint "
    "you can POST to, so it does not tell you to post to one.")


def _freshness(generated_epoch):
    return {
        "generated_epoch": int(generated_epoch),
        "fresh_for_seconds": FRESH_FOR_SECONDS,
        "decaying_fields": list(DECAYING_FIELDS),
        "read_this":
            "hours_since and status are computed at generation, not when "
            "you read this. If this document was served from a cache, "
            "those fields are as old as the document and can say current "
            "about a peer that has since gone silent. Compare "
            "generated_epoch against your own clock: if the difference "
            "exceeds fresh_for_seconds, refetch before relying on them. "
            "Everything else here - chain names, tip urls, first_seen, "
            "last_seen, observations, binding - does not decay.",
        "how_to_defeat_a_cache":
            "Append a changing query parameter, for example "
            "/x/roster/list?t=<unix seconds>. This route ignores unknown "
            "parameters.",
        "why_this_is_here":
            "A stale copy of this route was read with every peer at "
            "hours_since 0.0 and status current, contradicting this same "
            "document's six-hour definition, while how_to_use tells peers "
            "to poll it. Found by Ishaan (Shango MID).",
    }


def _epoch(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        import datetime
        return datetime.datetime.fromisoformat(
            s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _iso(ts):
    e = _epoch(ts)
    if e is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e))
    except Exception:
        return None


def _cols(conn, table):
    try:
        return [r[1] for r in conn.execute(
            "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


def _status_for(hours):
    if hours is None:
        return "unknown"
    if hours <= CURRENT_UNDER_HOURS:
        return "current"
    if hours <= SILENT_AFTER_HOURS:
        return "stale"
    return "silent"


def _signed_keys(ctx):
    keys = {}
    try:
        rows = ctx["conn"].execute(
            "SELECT peer, pubkey, rotations FROM signed_keys").fetchall()
        for peer, pubkey, rot in rows:
            if peer:
                keys[peer.strip()] = {"pubkey": pubkey, "rotations": rot or 0}
    except Exception:
        pass
    return keys


def _bind_state(ctx):
    """Returns None when bind.py is absent, so the response can say
    unavailable rather than none. Different answers."""
    state = {}
    try:
        rows = ctx["conn"].execute(
            "SELECT name, key_id, issued FROM bind_credential "
            "WHERE revoked IS NULL").fetchall()
    except Exception:
        return None
    for name, key_id, issued in rows:
        if not name:
            continue
        cur = state.setdefault(str(name).strip(),
            {"signed_lane": "none", "key_id": None, "issued_at": None,
             "claims": 0})
        cur["signed_lane"] = "credential"
        cur["key_id"] = key_id
        cur["issued_at"] = _iso(issued)
    try:
        claims = ctx["conn"].execute(
            "SELECT name, COUNT(*) FROM bind_claim GROUP BY name").fetchall()
    except Exception:
        claims = []
    for name, count in claims:
        if not name:
            continue
        cur = state.setdefault(str(name).strip(),
            {"signed_lane": "none", "key_id": None, "issued_at": None,
             "claims": 0})
        cur["claims"] = int(count or 0)
        if cur["signed_lane"] == "none":
            cur["signed_lane"] = "claimed"
    return state


def _binding_block(name_status, row, has_key, available):
    if not available:
        return {"open_lane": name_status, "signed_lane": "unavailable",
                "agree": None, "read_this": BINDING_VOCABULARY["unavailable"],
                "authority_for_signed_lane": "/x/bind/name"}
    signed = (row or {}).get("signed_lane", "none")
    if has_key and signed == "none":
        signed = "credential"
    open_held = name_status in ("bound", "first-use", "key-bound", "publisher")
    agree = None if signed == "none" else (
        bool(open_held) == bool(signed == "credential"))
    block = {"open_lane": name_status, "signed_lane": signed, "agree": agree,
             "authority_for_signed_lane": "/x/bind/name"}
    if row:
        if row.get("key_id"):
            block["credential_key_id"] = row["key_id"]
            block["credential_issued_at"] = row.get("issued_at")
        if row.get("claims"):
            block["dated_claims"] = row["claims"]
    if agree is False:
        block["why_they_differ"] = (
            "One lane says this name is held and the other does not. "
            "Expected rather than broken: a credential can exist for a name "
            "that never served a tip in JSON, and a url can bind a name "
            "holding no credential. Neither corrects the other.")
    return block


def _gather(ctx, now):
    conn = ctx["conn"]
    out = {}
    cols = _cols(conn, "witness_log")
    if not cols:
        return out
    chain_col = None
    for c in ("chain", "peer", "chain_name", "name"):
        if c in cols:
            chain_col = c
            break
    if not chain_col:
        return out
    ts_col = None
    for c in ("observed", "ts", "seen", "peer_ts"):
        if c in cols:
            ts_col = c
            break
    url_col = "url" if "url" in cols else None
    live_col = "liveness" if "liveness" in cols else None
    name_col = "name_status" if "name_status" in cols else None
    sel = [chain_col]
    for c in (ts_col, url_col, live_col, name_col):
        sel.append(c if c else "NULL")
    try:
        rows = conn.execute("SELECT %s FROM witness_log ORDER BY rowid"
                            % ", ".join(sel)).fetchall()
    except Exception:
        return out
    for r in rows:
        chain = (r[0] or "").strip()
        if not chain:
            continue
        e = out.setdefault(chain, {"chain": chain, "observations": 0,
            "first_seen": None, "last_seen": None, "url": None,
            "liveness": None, "name_status": None})
        e["observations"] += 1
        ts = _epoch(r[1])
        if ts is not None:
            if e["first_seen"] is None or ts < e["first_seen"]:
                e["first_seen"] = ts
            if e["last_seen"] is None or ts > e["last_seen"]:
                e["last_seen"] = ts
        if r[2]:
            e["url"] = r[2]
        if r[3]:
            e["liveness"] = r[3]
        if r[4]:
            e["name_status"] = r[4]
    for e in out.values():
        last = e["last_seen"]
        hours = ((now - last) / 3600.0) if last else None
        e["hours_since"] = round(hours, 1) if hours is not None else None
        e["status"] = _status_for(hours)
    return out


def _entries(ctx, now):
    peers = _gather(ctx, now)
    keys = _signed_keys(ctx)
    binds = _bind_state(ctx)
    available = binds is not None
    listed = []
    for chain, e in sorted(peers.items(), key=lambda kv: kv[0]):
        fetchable = bool(e["url"])
        entry = {
            "chain": e["chain"],
            "tip_url": e["url"],
            "observations": e["observations"],
            "first_seen": _iso(e["first_seen"]),
            "last_seen": _iso(e["last_seen"]),
            "last_seen_epoch": int(e["last_seen"]) if e["last_seen"] else None,
            "hours_since": e["hours_since"],
            "hours_since_computed_at": int(now),
            "status": e["status"],
            "liveness": e["liveness"],
            "name_status": e["name_status"],
            "fetchable": fetchable,
            "witnessable": fetchable,
            "submit_endpoint": None,
            "submit_endpoint_known": False,
            "binding": _binding_block(e["name_status"],
                                      (binds or {}).get(chain),
                                      chain in keys, available),
        }
        key = keys.get(chain)
        if key:
            entry["signing_key"] = {
                "algorithm": "ed25519", "pubkey": key["pubkey"],
                "rotations": key["rotations"],
                "means": "Only the holder of the matching private key can "
                         "submit under this name. This deployment holds the "
                         "public half only and cannot sign for them.",
                "verify_at": "/x/signed/keys"}
        listed.append(entry)
    listed.insert(0, {
        "chain": SELF_CHAIN, "tip_url": SELF_TIP, "observations": None,
        "first_seen": None, "last_seen": _iso(now),
        "last_seen_epoch": int(now), "hours_since": 0,
        "hours_since_computed_at": int(now),
        "status": "current", "liveness": "self", "name_status": "publisher",
        "fetchable": True, "witnessable": True,
        "submit_endpoint": SELF_OBSERVE, "submit_endpoint_known": True,
        "binding": {"open_lane": "publisher", "signed_lane": "n/a",
                    "agree": None,
                    "authority_for_signed_lane": "/x/bind/name"},
        "note": "The publisher of this roster. Its hours_since is zero by "
                "construction and is not an observation."})
    return listed


def _used_vocabulary(entries):
    live, names, stats, binds = {}, {}, {}, {}
    for e in entries:
        v = e.get("liveness")
        if v:
            live[v] = LIVENESS_VOCABULARY.get(v,
                "Undefined in roster v%s - introduced by another module and "
                "not described here. Treat as unexplained." % VERSION)
        n = e.get("name_status")
        if n:
            names[n] = NAME_VOCABULARY.get(n,
                "Undefined in roster v%s - see above." % VERSION)
        s = e.get("status")
        if s:
            stats[s] = STATUS_VOCABULARY.get(s, "")
        b = (e.get("binding") or {}).get("signed_lane")
        if b and b in BINDING_VOCABULARY:
            binds[b] = BINDING_VOCABULARY[b]
    stats["read_this"] = STATUS_VOCABULARY["read_this"]
    stats["computed_when"] = STATUS_VOCABULARY["computed_when"]
    binds["open_lane"] = BINDING_VOCABULARY["open_lane"]
    binds["signed_lane"] = BINDING_VOCABULARY["signed_lane"]
    binds["agree"] = BINDING_VOCABULARY["agree"]
    return {"liveness": live, "name_status": names, "status": stats,
            "binding": binds}


def _list(ctx):
    now = time.time()
    entries = _entries(ctx, now)
    fetchable = [e for e in entries if e["fetchable"]]
    signed = [e for e in entries if e.get("signing_key")]
    disagree = [e["chain"] for e in entries
                if (e.get("binding") or {}).get("agree") is False]
    return {
        "ok": True,
        "roster_version": VERSION,
        "generated": _iso(now),
        "generated_epoch": int(now),
        "freshness": _freshness(now),
        "submit_to": SELF_OBSERVE,
        "submit_signed_to": SELF_SIGNED,
        "count": len(entries),
        "fetchable": len(fetchable),
        "witnessable": len(fetchable),
        "stale": len([e for e in entries if e["status"] == "stale"]),
        "silent": len([e for e in entries if e["status"] == "silent"]),
        "with_signing_key": len(signed),
        "lanes_disagree": disagree,
        "peers": entries,
        "vocabulary": _used_vocabulary(entries),
        "what_this_list_is":
            "Parties that have submitted a tip to this deployment. That is "
            "all it records. Not a membership list, not partners, not "
            "participants in anything AILeash is building. Being listed "
            "implies no relationship beyond having sent a hash.",
        "how_to_use":
            "Poll this route on your own schedule, with a changing query "
            "parameter so you are not served a cached copy. Check "
            "generated_epoch against your own clock before trusting "
            "hours_since or status. For every entry with fetchable=true, "
            "fetch tip_url and seal the tip in your own chain. Whether that "
            "peer accepts your tip in return is not recorded here - "
            "submit_endpoint is unknown for every entry but ours. Ask the "
            "operator before posting to anything.",
        "witnessable_note":
            "witnessable is an alias of fetchable, kept so existing sync "
            "code keeps working. It means we hold a tip url for this "
            "entry. It has never meant the peer accepts submissions.",
        "note":
            "Quiet chains stay listed and are marked stale or silent. "
            "Removing them would make this a claim rather than a record. "
            "An entry with fetchable=false has no tip url here, which is "
            "not a statement about their infrastructure.",
    }, 200


def _health(ctx):
    now = time.time()
    entries = _entries(ctx, now)
    others = [e for e in entries if e["chain"] != SELF_CHAIN]
    return {
        "ok": True,
        "generated": _iso(now),
        "generated_epoch": int(now),
        "freshness": _freshness(now),
        "chains_listed": len(entries),
        "submitting_currently": len([e for e in others
                                     if e["status"] == "current"]),
        "stale": len([e for e in others if e["status"] == "stale"]),
        "silent": len([e for e in others if e["status"] == "silent"]),
        "with_signing_key": len([e for e in others if e.get("signing_key")]),
        "lanes_disagree": [e["chain"] for e in others
                           if (e.get("binding") or {}).get("agree") is False],
        "status_vocabulary": STATUS_VOCABULARY,
        "what_this_counts":
            "Parties that have submitted a tip to this deployment, and how "
            "recently. Nothing more. The counts of current, stale and "
            "silent are computed at generation and decay with this "
            "document.",
        "what_this_does_not_tell_you": [
            "Whether any of these parties witness each other.",
            "Whether any of them has agreed to anything.",
            "Whether the records behind any of these tips are true.",
            "Whether a peer was reachable. Stale or silent is a fact about "
            "this list, not about their infrastructure.",
        ],
    }, 200


def _spec():
    return {
        "module": "roster",
        "version": VERSION,
        "what": "A list of parties that have submitted a tip to this "
                "deployment, with the tip url each supplied.",
        "what_it_is_not":
            "Not a membership list. Not partners, adopters, validators or "
            "participants. Appearing here means a party posted a hash to an "
            "open endpoint. Being sealed in the chain and being named on "
            "this list are two things; neither is consent to the other.",
        "routes": {
            "GET list": "public. the roster. poll this.",
            "GET health": "public. one-line network summary.",
            "GET spec": "public. this document.",
        },
        "freshness": {
            "decaying_fields": list(DECAYING_FIELDS),
            "fresh_for_seconds": FRESH_FOR_SECONDS,
            "read_this":
                "hours_since and status are computed at generation. A "
                "cached copy of this route serves them unchanged, so they "
                "can contradict this document's own definitions - every "
                "peer reading current at hours_since 0.0, for instance. "
                "Every response carries generated_epoch; compare it "
                "against your own clock and refetch past "
                "fresh_for_seconds. Rewording cannot fix this, so the "
                "response states its own age instead.",
            "stable_fields":
                "chain, tip_url, first_seen, last_seen, last_seen_epoch, "
                "observations, liveness, name_status, binding and "
                "signing_key do not decay. last_seen_epoch is published so "
                "a reader can compute elapsed time against their own clock "
                "rather than trusting ours.",
        },
        "entry_fields": {
            "chain": "the chain's name as it submitted it",
            "tip_url": "where to fetch their current tip. null if none.",
            "fetchable": "true when tip_url is present. Means we can fetch "
                         "from them. Says nothing about what they accept.",
            "witnessable": "alias of fetchable, kept for existing sync code",
            "submit_endpoint": "null for every entry but ours. " + SUBMIT_NOTE,
            "last_seen_epoch": "unix seconds of our last observation. Does "
                               "not decay - compute elapsed time yourself.",
            "hours_since": "elapsed time at generation. Decays.",
            "hours_since_computed_at": "the unix second hours_since was "
                                       "computed at.",
            "status": "current, stale, silent or unknown, computed at "
                      "generation. Decays. Matches the bands on "
                      "/x/witness/peers.",
            "observations": "how many tips they have submitted to us",
            "liveness": "as recorded at submission - see vocabulary",
            "name_status": "open-lane binding as recorded at submission",
            "binding": "both binding lanes side by side, with agree saying "
                       "whether they match. /x/bind/name is the authority "
                       "for the signed lane.",
            "signing_key": "present only when an Ed25519 key is enrolled",
        },
        "liveness_vocabulary": LIVENESS_VOCABULARY,
        "name_vocabulary": NAME_VOCABULARY,
        "status_vocabulary": STATUS_VOCABULARY,
        "binding_vocabulary": BINDING_VOCABULARY,
        "joining": {
            "open": "POST a tip to %s with {\"chain\", \"tip\", \"url\"}. No "
                    "account, no key." % SELF_OBSERVE,
            "signed": "To make sure nobody - including this operator - can "
                      "submit under your name, enrol an Ed25519 public key "
                      "at /x/signed/enroll and submit at %s." % SELF_SIGNED,
        },
        "what_this_does_not_do": [
            "It does not witness anything. It is a phone book.",
            "It does not establish that anyone listed is a peer of anyone.",
            "It does not prove a listed chain is honest.",
            "It cannot make another operator witness you.",
            "It reflects submissions to this deployment only.",
            "The status word is not a statement about anyone's uptime.",
            "It cannot stop an intermediary caching it. It can only state "
            "when it was generated, which it now does.",
        ],
        "changed_in_1_4": [
            "Every response carries generated_epoch and a freshness block "
            "naming the fields that decay, so a cached copy can be "
            "detected as cached by whoever reads it.",
            "last_seen_epoch added per entry, so elapsed time can be "
            "computed against the reader's own clock rather than ours.",
            "hours_since_computed_at added per entry.",
            "Found by Ishaan (Shango MID) in a stale read that showed every "
            "peer at hours_since 0.0 and status current.",
        ],
        "changed_in_1_3": [
            "Both binding lanes published per entry with an agree boolean.",
            "witnessable split into fetchable; submit_endpoint reported as "
            "unknown rather than implied by how_to_use.",
            "The unbound wording no longer asserts a url was unreachable.",
        ],
        "drop_in":
            "meshwitness.py reads this route and fetches every entry on it. "
            "Standard library, one file, one cron line.",
    }


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return _spec(), 200
    if action == "health":
        return _health(ctx)
    if action in ("list", "", "status"):
        return _list(ctx)
    return {"ok": False, "error": "unknown_action", "action": action}, 404

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

588 lines, 24701 bytes

```python
"""
modules/rulebind.py  v1.2.0  —  rule binding, verifiable without an account

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

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. It proves which
ruleset produced which verdict and that the pairing was fixed at the time
rather than asserted later. Narrow, and the only part that is actually
provable.

THE v1.1 MISTAKE, AND WHAT v1.2 DOES ABOUT IT
---------------------------------------------
v1.0 let anyone POST arbitrary inputs and returned a six-decimal score,
unlimited. That is a scoring oracle: enough calls and the decision boundary
can be mapped without the weights ever being disclosed.

v1.1 closed it by keying prove. That was right about the oracle and wrong
about the consequence: the published ordering-test document declares this
check demonstrable_publicly, and after v1.1 no stranger could complete it.
The self-check runner went from PASS to INCONCLUSIVE, correctly, because a
browser holds no key. A check nobody outside can run is not a public check,
and leaving the document claiming otherwise would have been exactly the fault
this codebase keeps getting caught on - a statement one step past what the
thing beneath it does.

v1.2 gives the demonstration back without reopening the oracle:

  1. GET or POST /x/rulebind/demo - PUBLIC. Runs ONE fixed input set, the same
     one every time, hardcoded below. A fixed input cannot map a boundary: you
     learn one point on a curve, and it is the same point on every call. The
     response carries every component and the full binding_material, so anyone
     can recompute the digest with a shell command and check it.

  2. POST /x/rulebind/prove with NO key - allowed only when that exact input
     set is ALREADY on record. A repeat discloses nothing new; its score is
     already public through /verify. Novel input sets still need a key, and
     are still capped per key per hour.

The rule underneath both: what is already public stays public, and what would
make the boundary mappable stays keyed.

ROUTES
------
  GET/POST /x/rulebind/demo             public  fixed fixture, full material
  POST     /x/rulebind/prove            public for repeats, keyed for novel
  GET      /x/rulebind/verify?receipt=  public  recompute a sealed binding
  GET      /x/rulebind/packs            public  ruleset versions and dates
  GET      /x/rulebind/spec             public  what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.2.0"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

PUBLIC = {("GET", "verify"), ("GET", "packs"), ("GET", "spec"), ("GET", ""),
          ("GET", "demo"), ("POST", "demo"), ("POST", "prove")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Cap on NOVEL input sets per key per hour. Repeats are never limited.
NOVEL_PER_HOUR = 40

# The demo fixture. One input set, fixed, using the engine's real signal names.
# Deliberately unremarkable: an ordinary allow-shaped request, so the single
# point it discloses is the least informative point available.
DEMO_INPUTS = {
    "action": "purchase",
    "amount": 40.00,
    "trust": 0.80,
    "v60": 1,
    "v5m": 2,
    "v1h": 3,
    "device_risk": 0.10,
    "anomaly": 0.05,
    "country": "GB",
    "country_shift": 0,
}
DEMO_RESEAL_AFTER = 3600   # seal the fixture at most once an hour

SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

FALLBACK_ALLOW_BELOW = 0.35
FALLBACK_CHALLENGE_BELOW = 0.70

ANCHOR_NOTE = ("External timestamping is per proof, not a property of the "
               "chain. A proof is submitted first and confirmed later, and "
               "submitted is not confirmed. Check the state of any individual "
               "proof at /x/ots/status.")

_ready = False
_novel = {}


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
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_inputs ON rulebind_log(inputs_digest)")
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


def _find_bands():
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        a = getattr(mod, "ALLOW_BELOW", None)
        c = getattr(mod, "CHALLENGE_BELOW", None)
        if isinstance(a, (int, float)) and isinstance(c, (int, float)):
            return float(a), float(c), modname + ".ALLOW_BELOW/CHALLENGE_BELOW"
    return (FALLBACK_ALLOW_BELOW, FALLBACK_CHALLENGE_BELOW,
            "rulebind fallback constants")


def _active_pack(ctx):
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
    fn, where = _find(SCORER_NAMES)
    if fn:
        try:
            import inspect
            return "core-nine", _sha(inspect.getsource(fn))
        except Exception:
            return "core-nine", _sha("core-nine|" + str(where))
    return "unknown", _sha("unknown")


def _canonical_inputs(data):
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


def _last_for_inputs(ctx, inputs_digest):
    try:
        with ctx["lock"]:
            return ctx["conn"].execute(
                "SELECT pack_id,pack_hash,verdict,score,sealed_at,binding,"
                "audit_hash,block_index FROM rulebind_log WHERE inputs_digest=? "
                "ORDER BY id DESC LIMIT 1", (inputs_digest,)).fetchone()
    except Exception:
        return None


def _novel_allowed(api_key):
    now = time.time()
    cutoff = now - 3600
    for k in list(_novel.keys()):
        kept = [t for t in _novel[k] if t > cutoff]
        if kept:
            _novel[k] = kept
        else:
            del _novel[k]
    hits = _novel.get(api_key, [])
    if len(hits) >= NOVEL_PER_HOUR:
        return False, int(3600 - (now - min(hits))) + 1
    hits.append(now)
    _novel[api_key] = hits
    return True, 0


# ----------------------------------------------------------------------
# scoring and sealing
# ----------------------------------------------------------------------

def _score_and_seal(ctx, api_key, inputs, inputs_digest):
    scorer, _ = _find(SCORER_NAMES)
    if not scorer:
        return None, ({"error": "engine_unavailable",
                       "message": "The scoring function could not be found at runtime."}, 503)
    try:
        result = scorer(dict(inputs))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return None, ({"error": "scoring_failed", "message": str(exc)[:200]}, 400)

    decider, decider_where = _find(DECIDER_NAMES)
    verdict, verdict_source = None, None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
            verdict_source = "engine (" + str(decider_where) + ")"
        except Exception:
            verdict = None
    if verdict is None:
        a, c, band_source = _find_bands()
        verdict = "ALLOW" if score < a else ("CHALLENGE" if score < c else "BLOCK")
        verdict_source = "banded by rulebind using " + band_source

    pack_id, pack_hash = _active_pack(ctx)
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

    try:
        h, idx, seq = ctx["seal"](ev, res, sealed_at, api_key)
    except Exception as exc:
        return None, ({"error": "seal_failed",
                       "detail": type(exc).__name__ + ": " + str(exc)[:250],
                       "note": "Nothing was written. Send the identical inputs again."}, 500)
    if not h:
        return None, ({"error": "seal_failed", "detail": "seal returned no hash"}, 500)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict, "verdict_source": verdict_source,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding": binding, "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
    }, None


RECOMPUTE = {
    "step_1": ("Take binding_material exactly as returned - it is the string "
               "that was hashed, printed in full."),
    "step_2": "SHA-256 it. You should get the value in binding.",
    "step_3": ("Confirm the ruleset hash appears inside that string. It is a "
               "component of the digest, not a field beside it - change it and "
               "the digest no longer recomputes."),
    "step_4": ("Check the block sits in the chain, that our tip was recorded by "
               "operators we do not control at /x/roster/list, and the state of "
               "the timestamp proof covering it at /x/ots/status."),
    "shell": "printf '%s' \"$MATERIAL\" | shasum -a 256",
}

PROVES = ("That this verdict and this ruleset version were committed together, "
          "at this time, in one object. The pairing cannot be altered afterwards "
          "without breaking the digest, and the digest cannot be altered without "
          "breaking the chain.")

NOT_PROVES = ("That the rules were good, or the verdict correct. Only which "
              "ruleset produced it and that the pairing was fixed at the time.")


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _demo(ctx):
    """Public. One fixed input set, the same on every call.

    Fixed inputs are not an oracle: every caller learns the same single point,
    and that point is published here on purpose. Sealed at most once an hour so
    the route cannot be used to write blocks."""
    inputs_digest = _sha(_canonical_inputs(DEMO_INPUTS))
    row = _last_for_inputs(ctx, inputs_digest)

    fresh = False
    if row and (time.time() - float(row[4])) < DEMO_RESEAL_AFTER:
        pack_id, pack_hash, verdict, score, sealed_at, binding, receipt, block = row
        material, _ = _binding(pack_id, pack_hash, inputs_digest,
                               verdict, score, sealed_at)
        body = {
            "verdict": verdict, "score": score,
            "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
            "inputs_digest": inputs_digest,
            "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
            "binding": binding, "binding_material": material,
            "sealed": {"receipt": receipt, "block_index": block},
        }
    else:
        body, err = _score_and_seal(ctx, "public-rulebind-demo",
                                    DEMO_INPUTS, inputs_digest)
        if err:
            return err
        fresh = True

    body.update({
        "demo": True,
        "freshly_sealed": fresh,
        "inputs_used": DEMO_INPUTS,
        "why_the_inputs_are_fixed": (
            "This route runs one input set and always the same one, so it "
            "cannot be used to map the decision boundary - every caller learns "
            "the same single point, and that point is published above. Running "
            "your own inputs needs a key, which is what keeps the boundary "
            "closed while leaving this check demonstrable by anyone."),
        "reseal_after_seconds": DEMO_RESEAL_AFTER,
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + str(
            (body.get("sealed") or {}).get("receipt")),
    })
    return body, 200


def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values. Without a key, only input "
                            "sets already on record are accepted - see "
                            "/x/rulebind/demo for one anyone can run.")}, 400

    inputs_digest = _sha(_canonical_inputs(data))
    repeat = _last_for_inputs(ctx, inputs_digest) is not None

    if not api_key:
        if not repeat:
            return {
                "error": "api_key_required_for_novel_inputs",
                "message": ("This input set is not on record. Running the live "
                            "scorer on new inputs needs a key, because unlimited "
                            "public scoring of arbitrary inputs would map the "
                            "decision boundary."),
                "what_you_can_do_without_a_key": {
                    "run_the_check": "/x/rulebind/demo",
                    "recompute_any_sealed_binding": "/x/rulebind/verify?receipt=...",
                    "ruleset_history": "/x/rulebind/packs",
                },
            }, 401
        api_key = "public-rulebind-repeat"
    else:
        if not repeat:
            ok, retry_after = _novel_allowed(api_key)
            if not ok:
                return {"error": "novel_input_rate_limited",
                        "novel_inputs_per_hour": NOVEL_PER_HOUR,
                        "retry_after_seconds": retry_after,
                        "note": ("Input sets already on record are never "
                                 "limited. Only new ones are capped.")}, 429

    body, err = _score_and_seal(ctx, api_key, data, inputs_digest)
    if err:
        return err

    body.update({
        "inputs_already_on_record": repeat,
        "authenticated": not str(api_key).startswith("public-"),
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + body["sealed"]["receipt"],
    })
    return body, 200


def _verify(ctx, data):
    receipt = str((data or {}).get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required",
                "use": "/x/rulebind/verify?receipt=<audit hash>"}, 400
    if not HEX64.match(receipt):
        return {"error": "receipt_malformed",
                "expected": "64 lowercase hex characters"}, 400
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
        "found": True, "receipt": receipt, "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict, "score": score, "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored, "binding_material": material,
        "binding_recomputed": recomputed, "binding_matches": matches,
        "result": ("The ruleset version recomputes into the binding that was "
                   "sealed with this decision. It was bound at the time, not "
                   "attached afterwards."
                   if matches else
                   "MISMATCH. The stored binding does not recompute from the "
                   "stored components. Something has been altered and this "
                   "record should not be relied upon."),
        "what_this_check_is": (
            "A recomputation of the binding from its own published components. "
            "It does not by itself verify the chain, the witnesses or the "
            "timestamp proof - those are separate checks at the links below, "
            "run by you."),
        "chain_tip": "/x/witness/tip",
        "witnessed_by": "/x/roster/list",
        "timestamp_proofs": "/x/ots/status",
        "anchoring": ANCHOR_NOTE,
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
                 "record rather than a silent edit."),
        "limit_of_this_list": (
            "It shows versions that have bound at least one decision through "
            "this module. A ruleset that was live but never used here does not "
            "appear."),
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
        "demonstrable_publicly": True,
        "public_demonstration": "/x/rulebind/demo",
        "routes": {
            "GET or POST /x/rulebind/demo": "public - one fixed input set, full material",
            "POST /x/rulebind/prove": ("public for input sets already on record, "
                                       "keyed for new ones"),
            "GET /x/rulebind/verify?receipt=": "public - recomputes a sealed binding",
            "GET /x/rulebind/packs": "public - ruleset versions and dates",
            "GET /x/rulebind/spec": "public - this document",
        },
        "how_the_oracle_is_closed_without_closing_the_check": (
            "Running arbitrary inputs against the live scorer returns a numeric "
            "score, and unlimited public access to that maps the decision "
            "boundary without any weight being disclosed. So new input sets need "
            "a key and are capped at %d per key per hour. What stays public is "
            "everything that discloses nothing new: one fixed demo input set, "
            "repeats of input sets already on record, and recomputation of any "
            "sealed binding." % NOVEL_PER_HOUR),
        "how_to_test_it_with_no_account": [
            "GET /x/rulebind/demo",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Check the witnesses at /x/roster/list and the proof state at /x/ots/status.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names beyond the fixed demo input set, "
            "and intermediate values. Submitted inputs are published as a digest, "
            "not as values."),
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "cost": "Free. The public demonstration needs no account.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if action == "demo":
        return _demo(ctx)

    if method == "POST":
        if action == "prove":
            return _prove(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["prove", "demo"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "demo", "verify", "packs"], "POST": ["prove", "demo"]}, 404

```
