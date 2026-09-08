# Codebase — part 16 of 33

Contains:
- `modules/tokensaver.py`
- `modules/verifier.py`


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


## `modules/verifier.py`

717 lines, 26299 bytes

```python
#!/usr/bin/env python3
"""
modules/verifier.py  -  hand the verifier out at a URL

WHY THIS EXISTS
---------------
A proof that can only be checked by the party who issued it is not a proof.
So the proof bundles at /x/continuity/proof are useless unless somebody can
easily get hold of something that checks them, and telling people to clone a
repository is a gate.

This serves the standalone verifier as a plain file:

    curl -sO https://sebbi.pro/verify-authority.py
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify-authority.py -

The script it hands out has no dependencies and makes no network calls. It
checks the Ed25519 signature, recomputes every digest, re-runs the whole
derivation from the published rules, and reaches its own verdict - then says
so if that verdict disagrees with ours.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not phone home, and this module records nothing about who downloaded
it. A verification tool that reports back to the party being verified is not
a verification tool.

    GET /verify-authority.py   the script
    GET /x/verifier/status     what is installed, and the script's digest
"""

import hashlib
import sys

VERSION = "1.1"

PUBLIC = {("GET", "status")}

# Deliberately NOT "/verify" - that is the sealed-post verification page and
# this module would silently hijack it, handing a visitor a Python download
# where they expected a page. A route grab is a bug even when the code works.
FILE_PATHS = ("/verify-authority.py", "/verify_authority.py")

_patched = [False]


SCRIPT = r'''#!/usr/bin/env python3
"""
verify_authority.py  -  check an AILeash authority proof without AILeash

    python3 verify_authority.py proof.json
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify_authority.py -

WHAT THIS IS FOR
----------------
A proof that can only be checked by the party who issued it is not a proof.
This script takes a bundle and reaches its own conclusion using nothing but
the Python standard library. It does not call the issuing system, it does not
import anything you have to install, and it does not take a single field of
the bundle at face value.

It does four separate things, and each one can fail on its own:

  1. SIGNATURE   Ed25519 over the canonical bundle. Confirms the bundle came
                 from the holder of the named key and has not been edited by
                 anybody since.

  2. INTEGRITY   Recomputes every grant digest, the lineage digest and the
                 parameter digest from the fields in front of it. Confirms
                 the bundle is internally consistent with its own contents.

  3. DERIVATION  Re-runs the authority rules from scratch: root issued by a
                 human, an unbroken parent chain, scope covered at every hop,
                 constraints narrowing on every axis, purpose narrowing,
                 validity windows contained, nothing revoked, and the action
                 itself inside the effective limits of the whole lineage.

  4. AGREEMENT   Compares the verdict this script reached with the verdict the
                 bundle claims. Disagreement is reported as a failure of the
                 issuer, not of this script.

WHAT A PASS MEANS
-----------------
That the authority for this action was derivable, at that time, from that
human grant - or, for a refusal, that it genuinely was not, and that the named
grant and invariant really are where it broke.

WHAT A PASS DOES NOT MEAN
-------------------------
That the root grant should ever have been issued. That the parameters describe
something that really happened. That the risk engine was right. Derivation is
not merit and it is not truth.

The risk half of a composed verdict cannot be re-derived here, because that
needs the issuer's scoring engine. Where the bundle's authority verdict is
BLOCK, the composed verdict stands regardless, because the composition takes
the worse of the two.
"""

import binascii
import hashlib
import json
import sys

GRANT_PREFIX = b"AILEASH-GRANT-v1:"
EVAL_PREFIX = b"AILEASH-AUTHEVAL-v1:"
BUNDLE_PREFIX = b"AILEASH-AUTHORITY-PROOF-v1:"

MAX_DEPTH = 32
RANK = {"ALLOW": 0, "CHALLENGE": 1, "BLOCK": 2}


# ======================================================================
# Ed25519, RFC 8032, standard library only
# ======================================================================

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _h(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_BX = _xrecover(_BY)
_B = (_BX % _Q, _BY % _Q, 1, (_BX * _BY) % _Q)
_IDENT = (0, 1, 1, 0)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    dd = z1 * 2 * z2 % _Q
    e, f, g, hh = b - a, dd - c, dd + c, b + a
    return (e * f % _Q, g * hh % _Q, f * g % _Q, e * hh % _Q)


def _scalarmult(p, e):
    if e == 0:
        return _IDENT
    q = _scalarmult(p, e // 2)
    q = _add(q, q)
    if e & 1:
        q = _add(q, p)
    return q


def _encodepoint(p):
    x, y, z, _t = p
    zi = _inv(z)
    x, y = x * zi % _Q, y * zi % _Q
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _hint(m):
    h = _h(m)
    return sum(2 ** i * _bit(h, i) for i in range(512))


def _isoncurve(p):
    x, y, z, t = p
    return (z % _Q != 0 and x * y % _Q == z * t % _Q
            and (y * y - x * x - z * z - _D * t * t) % _Q == 0)


def _decodepoint(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if x & 1 != _bit(s, 255):
        x = _Q - x
    p = (x, y, 1, (x * y) % _Q)
    if not _isoncurve(p):
        raise ValueError("point off curve")
    return p


def ed25519_verify(sig, msg, pk):
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        rr = _decodepoint(sig[:32])
        a = _decodepoint(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:64], "little")
    if s >= _L:
        return False
    hh = _hint(sig[:32] + pk + msg)
    return _encodepoint(_scalarmult(_B, s)) == _encodepoint(_add(rr, _scalarmult(a, hh)))


# ======================================================================
# the rules, reimplemented from the published spec
# ======================================================================

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(prefix, text):
    return hashlib.sha256(prefix + text.encode("utf-8")).hexdigest()


def grant_digest(g):
    material = {
        "id": g["id"], "parent": g["parent"], "issuer": g["issuer"],
        "issuer_kind": g["issuer_kind"], "subject": g["subject"],
        "subject_kind": g["subject_kind"], "scope": sorted(g["scope"]),
        "constraints": g["constraints"], "purpose": g["purpose"],
        "purpose_tags": sorted(g["purpose_tags"]),
        "not_before": g["not_before"], "not_after": g["not_after"],
        "depth": g["depth"], "delegations_left": g["delegations_left"],
        "created": g["created"], "risk_accepted_by": g.get("risk_accepted_by"),
    }
    return sha(GRANT_PREFIX, canon(material))


def covers(held, wanted):
    if held == wanted or held == "*":
        return True
    if held.endswith(".*"):
        return wanted == held[:-2] or wanted.startswith(held[:-1])
    return False


def wildcard_breadth(scope, capability):
    best = None
    for held in scope:
        if not covers(held, capability):
            continue
        if held == capability:
            return 0
        width = (capability.count(".") + 2 if held == "*"
                 else capability.count(".") - held[:-2].count("."))
        best = width if best is None else min(best, width)
    return best


def direction(key):
    for p in ("max_", "min_", "allowed_", "denied_", "may_"):
        if key.startswith(p):
            return p
    return None


def num(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("not a number")
    return float(v)


def as_set(v):
    if isinstance(v, (list, tuple, set)):
        return set(v)
    return {v}


def narrower(parent_c, child_c):
    for key in sorted(child_c):
        d = direction(key)
        cval = child_c[key]
        if d is None:
            return False, "constraint '%s' has no narrowing rule" % key
        if key not in parent_c:
            return False, "constraint '%s' is not expressed by the parent" % key
        pval = parent_c[key]
        try:
            if d == "max_" and num(cval) > num(pval):
                return False, "%s raised from %s to %s" % (key, pval, cval)
            if d == "min_" and num(cval) < num(pval):
                return False, "%s lowered from %s to %s" % (key, pval, cval)
            if d == "allowed_" and not as_set(cval) <= as_set(pval):
                return False, "%s adds values the parent does not hold" % key
            if d == "denied_" and not as_set(pval) <= as_set(cval):
                return False, "%s drops values the parent denies" % key
            if d == "may_" and bool(cval) and not bool(pval):
                return False, "%s enabled where the parent withholds it" % key
        except (TypeError, ValueError):
            return False, "constraint '%s' is not comparable" % key
    return True, None


def effective(chain):
    eff = {}
    for g in chain:
        for k, v in g["constraints"].items():
            d = direction(k)
            if k not in eff:
                eff[k] = v
                continue
            cur = eff[k]
            try:
                if d == "max_":
                    eff[k] = min(num(cur), num(v))
                elif d == "min_":
                    eff[k] = max(num(cur), num(v))
                elif d == "allowed_":
                    eff[k] = sorted(as_set(cur) & as_set(v))
                elif d == "denied_":
                    eff[k] = sorted(as_set(cur) | as_set(v))
                elif d == "may_":
                    eff[k] = bool(cur) and bool(v)
            except (TypeError, ValueError):
                eff[k] = v
    return eff


def params_against(params, eff):
    hard, unconstrained = [], []
    for key in sorted(params):
        val = params[key]
        checked = False
        for cname, cval in eff.items():
            d = direction(cname)
            if not d or cname[len(d):] != key:
                continue
            checked = True
            try:
                if d == "max_" and num(val) > num(cval):
                    hard.append("%s=%s exceeds %s=%s" % (key, val, cname, cval))
                elif d == "min_" and num(val) < num(cval):
                    hard.append("%s=%s is below %s=%s" % (key, val, cname, cval))
                elif d == "allowed_" and val not in as_set(cval):
                    hard.append("%s=%s is outside %s" % (key, val, cname))
                elif d == "denied_" and val in as_set(cval):
                    hard.append("%s=%s is denied by %s" % (key, val, cname))
                elif d == "may_" and bool(val) and not bool(cval):
                    hard.append("%s requested where %s withholds it" % (key, cname))
            except (TypeError, ValueError):
                hard.append("%s cannot be compared with %s" % (key, cname))
        if not checked:
            unconstrained.append(key)
    return hard, unconstrained


# ======================================================================
# the four checks
# ======================================================================

class Report(object):
    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, ok, name, detail=""):
        self.rows.append((ok, name, detail))
        if not ok:
            self.failed = True

    def note(self, name, detail=""):
        self.rows.append((None, name, detail))

    def render(self):
        out = []
        for ok, name, detail in self.rows:
            mark = "  ok  " if ok else ("FAIL  " if ok is False else "  --  ")
            out.append(mark + name + (("\n        " + detail) if detail else ""))
        return "\n".join(out)


def check_signature(bundle, rep):
    sig_hex = bundle.get("signature")
    pk_hex = (bundle.get("issued_by") or {}).get("public_key")
    if not sig_hex or not pk_hex:
        rep.add(False, "Signature present", "the bundle carries no signature or no key")
        return
    body = dict(bundle)
    body.pop("signature", None)
    body.pop("verify_with", None)
    try:
        sig = binascii.unhexlify(sig_hex)
        pk = binascii.unhexlify(pk_hex)
    except Exception:
        rep.add(False, "Signature is readable hex")
        return
    ok = ed25519_verify(sig, BUNDLE_PREFIX + canon(body).encode("utf-8"), pk)
    rep.add(ok, "Ed25519 signature over the canonical bundle",
            "key " + pk_hex[:16] + "…  Verify this key independently at the issuer's "
            "published address before trusting who signed." if ok else
            "the bundle was altered after signing, or it was not signed by this key")


def check_integrity(bundle, rep):
    lineage = bundle.get("lineage") or []
    bad = []
    for g in lineage:
        try:
            if grant_digest(g) != g.get("digest"):
                bad.append(g.get("id"))
        except Exception:
            bad.append(g.get("id"))
    rep.add(not bad, "Every grant digest recomputes from its own fields",
            "" if not bad else "mismatched: " + ", ".join(str(b) for b in bad))

    claimed = (bundle.get("decision") or {}).get("lineage_digest")
    mine = sha(EVAL_PREFIX, canon([g.get("digest") for g in lineage]))
    rep.add(mine == claimed, "Lineage digest matches the ordered path",
            "" if mine == claimed else "computed " + mine[:20] + "… claimed " + str(claimed)[:20] + "…")

    req = bundle.get("request") or {}
    claimed_p = (bundle.get("decision") or {}).get("params_digest")
    mine_p = sha(EVAL_PREFIX, canon({"action": req.get("action"),
                                     "params": req.get("params") or {}}))
    rep.add(mine_p == claimed_p, "Parameter digest matches the request as stated",
            "" if mine_p == claimed_p else "the parameters shown are not the "
            "parameters that were judged")


def rederive(bundle, rep):
    """Run the published rules from scratch and reach an independent verdict."""
    lineage = bundle.get("lineage") or []
    decision = bundle.get("decision") or {}
    req = bundle.get("request") or {}
    at = decision.get("evaluated_at_epoch")

    hard, soft = [], []
    broken_at = broken_invariant = None

    def fail(grant, invariant, detail):
        nonlocal broken_at, broken_invariant
        hard.append(detail)
        if broken_at is None:
            broken_at, broken_invariant = grant, invariant

    if not lineage:
        fail(None, "authority_continuity", "the bundle carries no authority path")
    else:
        root = lineage[0]
        if root.get("parent") is not None:
            fail(root["id"], "authority_continuity",
                 "the path does not begin at a parentless root")
        if root.get("issuer_kind") != "human":
            fail(root["id"], "identity_continuity",
                 "the root grant was not issued by a human principal")

        previous = None
        for g in lineage:
            if g.get("revoked_at") is not None:
                fail(g["id"], "authority_continuity",
                     "grant %s was revoked" % g["id"])
            if at is not None:
                if at < g["not_before"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s was not yet valid at the time of the decision" % g["id"])
                if at >= g["not_after"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s had expired at the time of the decision" % g["id"])
            if previous is not None:
                if g.get("parent") != previous.get("id"):
                    fail(g["id"], "authority_continuity",
                         "grant %s does not point at the grant above it" % g["id"])
                missing = [c for c in g["scope"]
                           if not any(covers(p, c) for p in previous["scope"])]
                if missing:
                    fail(g["id"], "boundary_integrity",
                         "%s holds scope its parent does not: %s"
                         % (g["id"], ", ".join(sorted(missing))))
                ok, why = narrower(previous["constraints"], g["constraints"])
                if not ok:
                    fail(g["id"], "boundary_integrity", "%s: %s" % (g["id"], why))
                if not set(g["purpose_tags"]) <= set(previous["purpose_tags"]):
                    fail(g["id"], "intent_continuity",
                         "%s carries purpose tags its parent does not" % g["id"])
                if (g["not_before"] < previous["not_before"]
                        or g["not_after"] > previous["not_after"]):
                    fail(g["id"], "temporal_validity",
                         "%s is valid outside its parent's window" % g["id"])
                if g["depth"] != previous["depth"] + 1:
                    fail(g["id"], "authority_continuity",
                         "%s records a depth inconsistent with its parent" % g["id"])
            previous = g

        if len(lineage) - 1 > MAX_DEPTH:
            fail(lineage[-1]["id"], "boundary_integrity", "delegation depth exceeds the ceiling")

        if not any(g.get("risk_accepted_by") for g in lineage):
            fail(lineage[0]["id"], "identity_continuity",
                 "no grant in this path names who accepted the risk")

        leaf = lineage[-1]
        action = req.get("action")
        params = req.get("params") or {}

        if action and not any(covers(c, action) for c in leaf["scope"]):
            fail(leaf["id"], "boundary_integrity",
                 "action '%s' is outside the scope of the grant exercised" % action)
        elif action:
            breadth = wildcard_breadth(leaf["scope"], action)
            if breadth and breadth >= 2:
                soft.append("action '%s' is only covered by a broad wildcard" % action)

        eff = effective(lineage)
        failures, unconstrained = params_against(params, eff)
        for f in failures:
            fail(leaf["id"], "boundary_integrity", f)
        for u in unconstrained:
            soft.append("parameter '%s' is not constrained anywhere in the path" % u)

        tag = req.get("purpose_tag")
        if tag:
            if tag not in leaf["purpose_tags"]:
                soft.append("declared purpose '%s' is not carried by the grant" % tag)
        else:
            soft.append("the action declared no purpose")

    verdict = "BLOCK" if hard else ("CHALLENGE" if soft else "ALLOW")
    return verdict, hard, soft, broken_at, broken_invariant


def check_agreement(bundle, rep, mine, hard, soft, broken_at, broken_invariant):
    decision = bundle.get("decision") or {}
    claimed = decision.get("authority_verdict") or decision.get("verdict")

    rep.add(mine == claimed,
            "Independently re-derived authority verdict: " + mine,
            "" if mine == claimed else
            "the issuer claims " + str(claimed) + " and this script reaches " + mine +
            " from the same path. One of us is wrong and the rules are published.")

    if mine == "BLOCK":
        same_grant = (broken_at == decision.get("broken_at"))
        same_inv = (broken_invariant == decision.get("broken_invariant"))
        rep.add(same_grant and same_inv,
                "Refusal reproduces at the same grant and invariant",
                ("grant %s, invariant %s" % (broken_at, broken_invariant))
                if same_grant and same_inv else
                "this script breaks at grant %s / %s, the issuer says %s / %s"
                % (broken_at, broken_invariant,
                   decision.get("broken_at"), decision.get("broken_invariant")))
        rep.note("Why authority could not be derived")
        for h in hard:
            rep.note("  " + h)
    elif soft:
        rep.note("Why this could not be settled without a person")
        for x in soft:
            rep.note("  " + x)

    risk = decision.get("risk_verdict")
    if risk and mine != "BLOCK":
        rep.note("Risk verdict reported as " + str(risk) + ", not re-derivable here",
                 "the composed verdict is the worse of the two; the scoring engine "
                 "is not part of this bundle and is not checked by this script")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    raw = sys.stdin.read() if src == "-" else open(src, "r").read()
    try:
        bundle = json.loads(raw)
    except Exception as exc:
        print("Not readable JSON: " + str(exc))
        return 2

    rep = Report()
    print("=" * 66)
    print("AUTHORITY PROOF  ·  independent verification")
    print("=" * 66)
    d = bundle.get("decision") or {}
    print("evaluation   " + str(d.get("evaluation")))
    print("action       " + str((bundle.get("request") or {}).get("action")))
    print("at           " + str(d.get("evaluated_at")))
    print("hops         " + str(max(0, len(bundle.get("lineage") or []) - 1)))
    if bundle.get("lineage"):
        print("authorised   " + str(bundle["lineage"][0].get("issuer")))
        print("executed     " + str(bundle["lineage"][-1].get("subject")))
        acc = [g.get("risk_accepted_by") for g in bundle["lineage"] if g.get("risk_accepted_by")]
        print("risk owner   " + str(acc[-1] if acc else None))
    print("-" * 66)

    check_signature(bundle, rep)
    check_integrity(bundle, rep)
    mine, hard, soft, ba, bi = rederive(bundle, rep)
    check_agreement(bundle, rep, mine, hard, soft, ba, bi)

    print(rep.render())
    print("-" * 66)
    if rep.failed:
        print("RESULT: NOT VERIFIED. Something above did not hold.")
        return 1
    print("RESULT: VERIFIED - " + mine)
    if mine == "BLOCK":
        print("This is a proof that the action was NOT authorised, and where it failed.")
    print("Checked with no network access, no dependencies, and nothing taken on")
    print("the issuer's word except the meaning of their public key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _digest():
    return hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_verifier_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in FILE_PATHS:
            body = SCRIPT.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition",
                                 'attachment; filename="verify-authority.py"')
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
    H._verifier_patched = True
    _patched[0] = True
    print("VERIFIER: /verify-authority.py installed", flush=True)
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
            print("VERIFIER: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "serving": list(FILE_PATHS),
            "script_bytes": len(SCRIPT),
            "script_sha256": _digest(),
            "how_to_use": [
                "curl -sO https://sebbi.pro/verify-authority.py",
                "curl -s 'https://sebbi.pro/x/continuity/proof?evaluation=<id>' "
                "| python3 verify-authority.py -",
            ],
            "dependencies": "none - Python standard library only",
            "network": "the script makes no network calls and reports nothing back. "
                       "A verification tool that phones home to the party being "
                       "verified is not a verification tool.",
            "note": "Check script_sha256 against the file you downloaded. And read it "
                    "before you run it, as you would with anything else handed to you "
                    "by the party you are checking.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```
