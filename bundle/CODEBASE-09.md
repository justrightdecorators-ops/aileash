# Codebase — part 9 of 33

Contains:
- `modules/packs.py`


## `modules/packs.py`

2079 lines, 80594 bytes

```python
"""
Signal Packs - /x/packs/<action>

WHAT THIS IS
------------
A public library of decision rules for the token saver, written by anyone,
readable by anyone, runnable only through this engine.

A pack is a JSON document. It contains no code. It contains conditions
written over the nine signals the token saver already measures, and a
verdict for each condition. Nothing in a pack can call anything, read
anything, or reach anything. It is a list of thresholds and a list of
answers, and that is all it will ever be.

WHY IT IS BUILT THIS WAY
------------------------
Publishing is free and needs no account. Reading is free and needs no
account. A pack can be forked, sealed, dated and proved to be yours
without anyone paying anything.

Running a pack needs a key.

That split is deliberate and it is the whole commercial design. A pack on
its own is a text file - it decides nothing, seals nothing and produces no
receipt. The value is not in the thresholds. It is in what happens when
they are executed: a measured request, a verdict, and a block in a hash
chain that an outsider can verify without an account. That half cannot be
copied out of the library because it is not in the library.

So an author can build something genuinely theirs, publish it, prove they
wrote it first, and have other people use it - and every one of those
people arrives here to run it.

WHAT A PACK LOOKS LIKE
----------------------
    {
      "name": "Legal document review",
      "author": "someone",
      "version": "1.0.0",
      "vertical": "legal",
      "summary": "One line a buyer would understand.",
      "rules": [
        {"when": "loop_count >= 3 and not deterministic",
         "then": "challenge",
         "why": "A retried non-deterministic review is being paid for twice."},
        {"when": "turns > 25 and tool_count == 0",
         "then": "challenge",
         "why": "Long review threads carry the whole document every call."}
      ],
      "default": "allow"
    }

Rules are tried in order. The first that matches decides. If none match,
the pack's default decides.

THE EXPRESSION LANGUAGE
-----------------------
Deliberately small. Comparisons, and, or, not, brackets, numbers, and the
names below. No function calls, no attribute access, no assignment, no
loops, no strings. It is parsed into a tree and walked; nothing is ever
handed to eval, exec, or compile.

Names available inside a rule:

  the nine scored signals, each 0.0 to 1.0
    exposure   worst case spend against the budget left
    size       prompt characters, log scaled
    ask        the output ceiling the caller authorised
    depth      conversation turns
    tools      tool definitions attached
    loop       the same request going round again
    burst      requests in the last sixty seconds
    grind      requests in the last hour
    novelty    first time this shape has been seen

  the raw measurements the signals came from
    chars, max_tokens, turns, tool_count,
    loop_count, burst_count, grind_count

  the engine's own overall score, 0.0 to 1.0
    score

  two flags
    unattended      no human is watching this system
    deterministic   temperature is zero, so the answer can be reused

VERDICTS A RULE MAY RETURN
--------------------------
    allow       send it to the model as asked
    downgrade   small and simple enough for the cheap model
    challenge   hold it for a person before spending
    block       refuse it; it never reaches the model

A pack can never return "serve". Serving from store is decided by whether
an identical request has been answered before, which is a fact, not a
policy, and no pack is allowed a say in it.

WHAT A PACK CANNOT DO
---------------------
- It cannot loosen a hard rule. If the token saver's own budget and
  runaway rules fire, they fire. A pack runs after them and can only make
  a decision stricter than the one the engine reached, never weaker.
- It cannot see a prompt. Packs are evaluated against measurements, and on
  the digest path the content never left the customer's building at all.
- It cannot read or write anything. There is no I/O in the language.

    GET  /x/packs/spec                    public  the language and the rules
    GET  /x/packs/list                    public  browse the library
    GET  /x/packs/get?id=                 public  one pack, whole
    POST /x/packs/validate                public  parse it, no publishing
    POST /x/packs/publish                 public  seal it into the chain
    POST /x/packs/fork                    public  publish with a parent named
    POST /x/packs/run                     KEYED   evaluate against a request
    GET  /x/packs/status                  public  config, and arms /packs
"""

import hashlib
import json
import math
import re
import sys
import time
from datetime import datetime, timezone

VERSION = "1.0.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "list"),
    ("GET", "get"),
    ("GET", "status"),
    ("POST", "validate"),
    ("POST", "publish"),
    ("POST", "fork"),
}

# ---------------------------------------------------------------- limits

MAX_RULES = 40
MAX_EXPR_CHARS = 400
MAX_TOKENS_PER_EXPR = 120
MAX_NAME = 80
MAX_SUMMARY = 240
MAX_WHY = 300
MAX_MANIFEST_BYTES = 32 * 1024
LIST_LIMIT = 200

VERDICTS = ("allow", "downgrade", "challenge", "block")

# How strict each verdict is. A pack may raise this number, never lower it.
STRICTNESS = {"allow": 0, "downgrade": 1, "challenge": 2, "block": 3}

SIGNALS = ("exposure", "size", "ask", "depth", "tools",
           "loop", "burst", "grind", "novelty")

MEASURES = ("chars", "max_tokens", "turns", "tool_count",
            "loop_count", "burst_count", "grind_count")

FLAGS = ("unattended", "deterministic")

NAMES = set(SIGNALS) | set(MEASURES) | set(FLAGS) | {"score"}

VERTICALS = (
    "legal", "medical", "support", "coding", "finance", "retail",
    "education", "research", "translation", "moderation", "sales",
    "recruitment", "logistics", "gaming", "media", "security",
    "insurance", "property", "ecommerce", "public-sector", "general",
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SEMVER_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,4}$")


# ---------------------------------------------------------------- helpers

def _now():
    return time.time()


def _iso(ts):
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _digest(obj):
    return hashlib.sha256(b"SEBBI-SIGNALPACK-v1\n" + _canonical(obj)).hexdigest()


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:64] or "pack"


# ================================================================ language
#
# A tiny expression language, parsed by hand into a tuple tree and walked.
# Nothing here reaches eval, exec or compile, and there is no syntax for
# calling anything, so an untrusted pack cannot do anything but compare
# numbers it was given.

_TOKEN_RE = re.compile(r"""
    \s*(?:
        (?P<num>\d+(?:\.\d+)?)
      | (?P<op>>=|<=|==|!=|>|<)
      | (?P<lp>\()
      | (?P<rp>\))
      | (?P<word>[A-Za-z_][A-Za-z0-9_]*)
    )
""", re.VERBOSE)

_WORD_OPS = {"and", "or", "not", "true", "false"}


class PackError(ValueError):
    """Anything wrong with a pack, reported to the author in plain words."""


def _tokenise(src):
    if len(src) > MAX_EXPR_CHARS:
        raise PackError("expression is longer than %d characters"
                        % MAX_EXPR_CHARS)
    out = []
    pos = 0
    n = len(src)
    while pos < n:
        m = _TOKEN_RE.match(src, pos)
        if not m or m.end() == m.start():
            rest = src[pos:pos + 12]
            raise PackError("cannot read %r - the language has numbers, "
                            "names, brackets, and the operators "
                            "> >= < <= == != and or not" % rest)
        pos = m.end()
        if m.group("num"):
            out.append(("num", float(m.group("num"))))
        elif m.group("op"):
            out.append(("op", m.group("op")))
        elif m.group("lp"):
            out.append(("lp", "("))
        elif m.group("rp"):
            out.append(("rp", ")"))
        else:
            w = m.group("word")
            lw = w.lower()
            if lw in _WORD_OPS:
                out.append(("kw", lw))
            elif w in NAMES:
                out.append(("name", w))
            else:
                raise PackError(
                    "unknown name %r. Available: %s"
                    % (w, ", ".join(sorted(NAMES))))
        if len(out) > MAX_TOKENS_PER_EXPR:
            raise PackError("expression has too many parts (limit %d)"
                            % MAX_TOKENS_PER_EXPR)
        if pos < n and src[pos:].strip() == "":
            break
    return out


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, kind, val=None):
        k, v = self.take()
        if k != kind or (val is not None and v != val):
            raise PackError("expected %s here" % (val or kind))
        return v

    def parse(self):
        node = self.or_expr()
        if self.i != len(self.t):
            raise PackError("unexpected extra text at the end of the "
                            "expression")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.peek() == ("kw", "or"):
            self.take()
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.peek() == ("kw", "and"):
            self.take()
            node = ("and", node, self.not_expr())
        return node

    def not_expr(self):
        if self.peek() == ("kw", "not"):
            self.take()
            return ("not", self.not_expr())
        return self.comparison()

    def comparison(self):
        left = self.primary()
        k, v = self.peek()
        if k == "op":
            self.take()
            right = self.primary()
            return ("cmp", v, left, right)
        return left

    def primary(self):
        k, v = self.take()
        if k == "num":
            return ("num", v)
        if k == "name":
            return ("name", v)
        if k == "kw" and v in ("true", "false"):
            return ("bool", v == "true")
        if k == "kw" and v == "not":
            return ("not", self.not_expr())
        if k == "lp":
            node = self.or_expr()
            self.expect("rp")
            return node
        raise PackError("expected a number, a signal name, or a bracket")


def compile_expr(src):
    """Text to tree. Raises PackError with something an author can act on."""
    if not isinstance(src, str) or not src.strip():
        raise PackError("a rule needs a 'when' expression")
    toks = _tokenise(src)
    if not toks:
        raise PackError("empty expression")
    return _Parser(toks).parse()


def _truth(v):
    if isinstance(v, bool):
        return v
    return bool(v)


def eval_expr(node, env):
    """Walk the tree. No recursion into anything the pack controls."""
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "bool":
        return node[1]
    if kind == "name":
        return env.get(node[1], 0)
    if kind == "not":
        return not _truth(eval_expr(node[1], env))
    if kind == "and":
        return (_truth(eval_expr(node[1], env))
                and _truth(eval_expr(node[2], env)))
    if kind == "or":
        return (_truth(eval_expr(node[1], env))
                or _truth(eval_expr(node[2], env)))
    if kind == "cmp":
        op = node[1]
        a = eval_expr(node[2], env)
        b = eval_expr(node[3], env)
        if isinstance(a, bool) or isinstance(b, bool):
            a = 1 if a is True else 0 if a is False else a
            b = 1 if b is True else 0 if b is False else b
        try:
            if op == ">":
                return a > b
            if op == ">=":
                return a >= b
            if op == "<":
                return a < b
            if op == "<=":
                return a <= b
            if op == "==":
                return a == b
            if op == "!=":
                return a != b
        except TypeError:
            return False
    raise PackError("unreadable expression")


def _names_used(node, found=None):
    """Which signals a rule actually reads. Used to draw the sigil."""
    if found is None:
        found = {}
    kind = node[0]
    if kind == "name":
        found[node[1]] = found.get(node[1], 0) + 1
    elif kind in ("not",):
        _names_used(node[1], found)
    elif kind in ("and", "or"):
        _names_used(node[1], found)
        _names_used(node[2], found)
    elif kind == "cmp":
        _names_used(node[2], found)
        _names_used(node[3], found)
    return found


# ================================================================ manifest

def validate(manifest):
    """
    Returns (clean_manifest, compiled_rules, profile).

    Everything an author can get wrong is named in words they can act on,
    because a library where publishing fails with 'invalid input' is a
    library nobody publishes to.
    """
    if not isinstance(manifest, dict):
        raise PackError("a pack is a JSON object")
    if len(_canonical(manifest)) > MAX_MANIFEST_BYTES:
        raise PackError("a pack must be under %d bytes" % MAX_MANIFEST_BYTES)

    name = str(manifest.get("name") or "").strip()
    if not name or len(name) > MAX_NAME:
        raise PackError("name is required, up to %d characters" % MAX_NAME)

    author = str(manifest.get("author") or "").strip()
    if not author or len(author) > MAX_NAME:
        raise PackError("author is required - a name, a domain or a handle")

    version = str(manifest.get("version") or "1.0.0").strip()
    if not SEMVER_RE.match(version):
        raise PackError("version must look like 1.0.0")

    summary = str(manifest.get("summary") or "").strip()
    if len(summary) > MAX_SUMMARY:
        raise PackError("summary must be under %d characters" % MAX_SUMMARY)

    vertical = str(manifest.get("vertical") or "general").strip().lower()
    if vertical not in VERTICALS:
        raise PackError("vertical must be one of: %s" % ", ".join(VERTICALS))

    default = str(manifest.get("default") or "allow").strip().lower()
    if default not in VERDICTS:
        raise PackError("default must be one of: %s" % ", ".join(VERDICTS))

    rules = manifest.get("rules")
    if not isinstance(rules, list) or not rules:
        raise PackError("a pack needs at least one rule")
    if len(rules) > MAX_RULES:
        raise PackError("a pack may hold up to %d rules" % MAX_RULES)

    clean_rules = []
    compiled = []
    usage = {}
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            raise PackError("rule %d is not an object" % (i + 1))
        when = r.get("when")
        try:
            tree = compile_expr(when)
        except PackError as exc:
            raise PackError("rule %d: %s" % (i + 1, exc))
        then = str(r.get("then") or "").strip().lower()
        if then not in VERDICTS:
            raise PackError("rule %d: 'then' must be one of: %s"
                            % (i + 1, ", ".join(VERDICTS)))
        why = str(r.get("why") or "").strip()
        if len(why) > MAX_WHY:
            raise PackError("rule %d: 'why' must be under %d characters"
                            % (i + 1, MAX_WHY))
        if not why:
            raise PackError("rule %d needs a 'why'. A verdict with no stated "
                            "reason is the thing this whole platform exists "
                            "to remove." % (i + 1))
        clean_rules.append({"when": str(when).strip(), "then": then,
                            "why": why})
        compiled.append((tree, then, why))
        for k, n in _names_used(tree).items():
            usage[k] = usage.get(k, 0) + n

    clean = {
        "name": name,
        "author": author,
        "version": version,
        "vertical": vertical,
        "summary": summary,
        "default": default,
        "rules": clean_rules,
    }
    return clean, compiled, _profile(usage, clean_rules)


def _profile(usage, rules):
    """
    The pack's signal fingerprint: how heavily it leans on each of the nine
    signals, normalised to 0..1. Deterministic from the manifest, so the
    same pack always draws the same sigil, and two packs that reason
    differently never look alike.
    """
    raw = {}
    for s in SIGNALS:
        direct = usage.get(s, 0)
        # A pack that reads a raw measure is leaning on that signal too.
        kin = {"size": "chars", "ask": "max_tokens", "depth": "turns",
               "tools": "tool_count", "loop": "loop_count",
               "burst": "burst_count", "grind": "grind_count"}.get(s)
        indirect = usage.get(kin, 0) if kin else 0
        raw[s] = direct * 1.0 + indirect * 0.85
    top = max(raw.values()) if raw else 0
    prof = {s: (round(raw[s] / top, 3) if top else 0.0) for s in SIGNALS}
    strict = max((STRICTNESS[r["then"]] for r in rules), default=0)
    return {
        "signals": prof,
        "reads": sorted([s for s in SIGNALS if prof[s] > 0]),
        "rule_count": len(rules),
        "hardest_verdict": [k for k, v in STRICTNESS.items()
                            if v == strict][0],
        "note": "Each spoke is how heavily this pack leans on that signal. "
                "Computed from the rules themselves, so the drawing is the "
                "pack rather than a picture attached to it.",
    }


# ================================================================ evaluate

def _env(measured, signals, score, unattended, deterministic):
    env = {}
    for s in SIGNALS:
        try:
            env[s] = float(signals.get(s, 0) or 0)
        except (TypeError, ValueError):
            env[s] = 0.0
    env["score"] = float(score or 0)
    env["chars"] = int(measured.get("prompt_characters", 0) or 0)
    env["max_tokens"] = int(measured.get("authorised_output_tokens", 0) or 0)
    env["turns"] = int(measured.get("conversation_turns", 0) or 0)
    env["tool_count"] = int(measured.get("tool_definitions", 0) or 0)
    env["loop_count"] = int(measured.get("loop_count", 0) or 0)
    env["burst_count"] = int(measured.get("requests_in_last_60s", 0) or 0)
    env["grind_count"] = int(measured.get("requests_in_last_hour", 0) or 0)
    env["unattended"] = bool(unattended)
    env["deterministic"] = bool(deterministic)
    return env


def apply_pack(compiled, default, env, engine_verdict):
    """
    Run the rules in order, first match wins.

    A pack may only make the engine's own decision stricter. If the engine
    already refused a request under a hard rule, a pack saying 'allow'
    changes nothing - and the response says so rather than quietly
    discarding it, because an author debugging a pack needs to see that
    their rule fired and was capped.
    """
    fired = None
    for idx, (tree, then, why) in enumerate(compiled):
        try:
            hit = _truth(eval_expr(tree, env))
        except PackError:
            hit = False
        if hit:
            fired = {"rule": idx + 1, "then": then, "why": why}
            break

    pack_verdict = fired["then"] if fired else default
    base = STRICTNESS.get(engine_verdict, 0)
    want = STRICTNESS.get(pack_verdict, 0)

    if want >= base:
        final = pack_verdict
        capped = False
    else:
        final = engine_verdict
        capped = True

    return {
        "engine_verdict": engine_verdict,
        "pack_verdict": pack_verdict,
        "verdict": final,
        "matched_rule": fired,
        "used_default": fired is None,
        "capped_by_engine": capped,
        "capping_note": (
            "the pack asked for a weaker verdict than the engine had already "
            "reached, so the engine's stands. A pack can only ever tighten."
            if capped else None),
    }


# ================================================================ storage

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute(
            "CREATE TABLE IF NOT EXISTS packs("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "pack_id TEXT UNIQUE,"
            "slug TEXT,"
            "name TEXT,"
            "author TEXT,"
            "version TEXT,"
            "vertical TEXT,"
            "summary TEXT,"
            "manifest TEXT,"
            "profile TEXT,"
            "digest TEXT,"
            "published REAL,"
            "forked_from TEXT,"
            "runs INTEGER NOT NULL DEFAULT 0,"
            "audit_hash TEXT,"
            "block_index INTEGER,"
            "seeded INTEGER NOT NULL DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_packs_vert "
                  "ON packs(vertical)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_packs_slug ON packs(slug)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_packs_dig ON packs(digest)")
        c.commit()
    _ready = True
    _seed(ctx)


def _pack_id(slug, version, digest):
    return "%s@%s.%s" % (slug, version, digest[:8])


def _row_to_pack(r, full=False):
    out = {
        "id": r[1],
        "slug": r[2],
        "name": r[3],
        "author": r[4],
        "version": r[5],
        "vertical": r[6],
        "summary": r[7],
        "profile": json.loads(r[9]) if r[9] else None,
        "digest": r[10],
        "published": _iso(r[11]),
        "forked_from": r[12],
        "runs": r[13],
        "sealed_in_chain": r[14],
        "block_index": r[15],
        "origin": "library seed" if r[16] else "published",
    }
    if full:
        out["manifest"] = json.loads(r[8])
    return out


def _seal(ctx, event, result, api_key=None):
    """Seal, tolerating whichever signature this deployment's seal has."""
    ts = _now()
    ev = {"user_id": "packs", "action": event, "amount": 0,
          "country": "UK", "device_id": "packs", "anomaly": 0,
          "device_risk": 0}
    res = dict(result)
    res.setdefault("decision", "PACK_EVENT")
    res.setdefault("score", 0)
    res.setdefault("timestamp", ts)
    fn = ctx.get("seal")
    if not fn:
        return None, None, None
    for call in (lambda: fn(ev, res, ts, api_key),
                 lambda: fn(ev, res, ts),
                 lambda: fn(ev, res)):
        try:
            out = call()
        except TypeError:
            continue
        except Exception:                                    # noqa: BLE001
            return None, None, None
        if isinstance(out, (tuple, list)):
            return (out[0] if len(out) > 0 else None,
                    out[1] if len(out) > 1 else None,
                    out[2] if len(out) > 2 else None)
        if isinstance(out, dict):
            return (out.get("audit_hash") or out.get("hash"),
                    out.get("block_index"), out.get("key_seq"))
        if isinstance(out, str):
            return out, None, None
    return None, None, None


def _store(ctx, clean, profile, forked_from, api_key, seeded=False):
    digest = _digest(clean)
    slug = _slug(clean["name"])
    pid = _pack_id(slug, clean["version"], digest)

    with ctx["lock"]:
        existing = ctx["conn"].execute(
            "SELECT * FROM packs WHERE digest=?", (digest,)).fetchone()
    if existing:
        out = _row_to_pack(existing, full=True)
        out["already_published"] = True
        out["note"] = ("byte-for-byte identical to a pack already in the "
                       "library, so the original stands. Change something "
                       "or fork it under your own name.")
        return out

    h, idx, seq = _seal(ctx, "signalpack_published", {
        "decision": "PACK_PUBLISHED",
        "pack_id": pid, "name": clean["name"], "author": clean["author"],
        "version": clean["version"], "vertical": clean["vertical"],
        "rules": len(clean["rules"]), "digest": digest,
        "forked_from": forked_from,
        "note": "the pack's own digest is sealed, so the document cannot be "
                "edited after this date without the digest changing",
    }, api_key) if not seeded else _seal(ctx, "signalpack_seeded", {
        "decision": "PACK_SEEDED", "pack_id": pid, "digest": digest,
        "note": "library seed published by the deployment operator",
    }, api_key)

    now = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO packs(pack_id,slug,name,author,version,"
            "vertical,summary,manifest,profile,digest,published,forked_from,"
            "runs,audit_hash,block_index,seeded) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?)",
            (pid, slug, clean["name"], clean["author"], clean["version"],
             clean["vertical"], clean["summary"], json.dumps(clean),
             json.dumps(profile), digest, now, forked_from, h, idx,
             1 if seeded else 0))
        ctx["conn"].commit()
        row = ctx["conn"].execute(
            "SELECT * FROM packs WHERE pack_id=?", (pid,)).fetchone()

    out = _row_to_pack(row, full=True) if row else {"id": pid}
    out["receipt_seq"] = seq
    out["what_this_proves"] = (
        "that this exact document existed at this position in the chain on "
        "this date. It does not prove the rules are good ones.")
    return out


# ================================================================ the seeds
#
# Twenty packs so the library is not empty on the first day. They are
# marked as seeds rather than passed off as community work, and they are
# forkable like anything else. Every threshold in them is arguable - that
# is the point of a library. Fork one and argue with it.

SEEDS = [
    {
        "name": "Legal document review",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "legal",
        "summary": "Long clause-by-clause review threads carry the whole "
                   "document on every call. This catches that before the bill "
                   "does.",
        "default": "allow",
        "rules": [
            {"when": "turns > 20 and chars > 40000",
             "then": "challenge",
             "why": "A twenty-turn review re-sending forty thousand "
                    "characters is paying for the same contract on every "
                    "question."},
            {"when": "loop_count >= 3 and not deterministic",
             "then": "challenge",
             "why": "The same clause asked three times with temperature "
                    "above zero cannot be reused, so it is bought again "
                    "each time."},
            {"when": "unattended and max_tokens > 4000",
             "then": "block",
             "why": "A four thousand token opinion generated with nobody "
                    "reading it is a cost with no reader."},
        ],
    },
    {
        "name": "Clinical summarisation guard",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "medical",
        "summary": "Holds long unattended clinical generations for a person. "
                   "Deliberately cautious rather than cheap.",
        "default": "allow",
        "rules": [
            {"when": "unattended and max_tokens > 1500",
             "then": "challenge",
             "why": "Clinical text generated at length with no clinician "
                    "watching should reach a person before it reaches a "
                    "record."},
            {"when": "turns > 30",
             "then": "challenge",
             "why": "A thirty-turn history is being re-sent whole on every "
                    "call and is almost certainly carrying resolved "
                    "episodes."},
            {"when": "exposure > 0.7",
             "then": "block",
             "why": "One call about to consume most of the remaining budget "
                    "stops here."},
        ],
    },
    {
        "name": "Support triage - high volume",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "support",
        "summary": "Built for inbox-shaped traffic: short, repetitive, and "
                   "cheap when it is allowed to be.",
        "default": "downgrade",
        "rules": [
            {"when": "loop_count >= 4",
             "then": "block",
             "why": "Four identical tickets in two minutes is a retry loop, "
                    "not four customers."},
            {"when": "chars < 2000 and turns <= 4 and tool_count == 0",
             "then": "downgrade",
             "why": "A short first-line reply does not need the expensive "
                    "model."},
            {"when": "burst_count > 60",
             "then": "challenge",
             "why": "Sixty requests a minute from one key is either a "
                    "migration or a fault, and both want a person."},
        ],
    },
    {
        "name": "Coding agent leash",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "coding",
        "summary": "The pack for autonomous coding loops. Tight on repeats, "
                   "hard on unattended runs.",
        "default": "allow",
        "rules": [
            {"when": "unattended and loop_count >= 2",
             "then": "block",
             "why": "An agent retrying the same call with nobody watching is "
                    "the most expensive failure mode there is."},
            {"when": "tools > 0.6 and tool_count > 12",
             "then": "challenge",
             "why": "Twelve tool definitions on every call is a large fixed "
                    "cost per step in a long loop."},
            {"when": "grind_count > 400",
             "then": "challenge",
             "why": "Four hundred calls in an hour is a run that should be "
                    "confirmed rather than assumed."},
            {"when": "score > 0.7",
             "then": "challenge",
             "why": "The engine already rates this call as costly and "
                    "repetitive."},
        ],
    },
    {
        "name": "Financial analysis desk",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "finance",
        "summary": "Protects a shared budget across a desk where any one "
                   "analyst can spend it.",
        "default": "allow",
        "rules": [
            {"when": "exposure > 0.5",
             "then": "challenge",
             "why": "One call reaching for half the remaining budget is a "
                    "decision, not a request."},
            {"when": "exposure > 0.85",
             "then": "block",
             "why": "Past this point a single call can empty the desk's "
                    "budget."},
            {"when": "max_tokens > 8000 and unattended",
             "then": "block",
             "why": "An eight thousand token report nobody asked to read."},
        ],
    },
    {
        "name": "Retail product copy",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "retail",
        "summary": "Catalogue generation at volume, where the same SKU gets "
                   "asked for twice more often than anyone believes.",
        "default": "downgrade",
        "rules": [
            {"when": "not deterministic and loop_count >= 2",
             "then": "challenge",
             "why": "Varied copy for the same product, generated twice, "
                    "cannot be reused and is paid for twice."},
            {"when": "chars < 3000 and max_tokens <= 800",
             "then": "downgrade",
             "why": "Short product copy is what the cheap model is for."},
            {"when": "burst_count > 90",
             "then": "block",
             "why": "Ninety calls a minute against a catalogue is a runaway "
                    "import."},
        ],
    },
    {
        "name": "Education marking assistant",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "education",
        "summary": "Batch marking runs unattended overnight. This is the "
                   "pack that stops one bad loop eating a term's budget.",
        "default": "allow",
        "rules": [
            {"when": "unattended and loop_count >= 3",
             "then": "block",
             "why": "The same script marked three times is a fault in the "
                    "batch, not three submissions."},
            {"when": "unattended and grind_count > 800",
             "then": "challenge",
             "why": "Eight hundred marks in an hour with nobody watching "
                    "wants confirming before it continues."},
            {"when": "turns > 12",
             "then": "challenge",
             "why": "Marking should not need a twelve-turn conversation; "
                    "something is carrying context it does not need."},
        ],
    },
    {
        "name": "Research literature sweep",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "research",
        "summary": "Long context is the whole job here, so this pack is "
                   "loose on size and tight on repetition.",
        "default": "allow",
        "rules": [
            {"when": "loop_count >= 3",
             "then": "challenge",
             "why": "The same paper summarised three times in two minutes is "
                    "a pipeline retrying, not new reading."},
            {"when": "novelty == 0 and grind_count > 300",
             "then": "challenge",
             "why": "Three hundred calls of a shape already seen is a sweep "
                    "that has stopped finding anything new."},
        ],
    },
    {
        "name": "Translation pipeline",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "translation",
        "summary": "Translation is the purest case for exact reuse: the same "
                   "string, the same language pair, the same answer.",
        "default": "downgrade",
        "rules": [
            {"when": "not deterministic",
             "then": "challenge",
             "why": "Temperature above zero on a translation blocks reuse for "
                    "no benefit. The same string should give the same "
                    "translation."},
            {"when": "chars < 4000 and tool_count == 0",
             "then": "downgrade",
             "why": "Short segment translation does not need the expensive "
                    "model."},
            {"when": "loop_count >= 5",
             "then": "block",
             "why": "Five identical segments in two minutes is a stuck "
                    "queue."},
        ],
    },
    {
        "name": "Content moderation queue",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "moderation",
        "summary": "High volume, low latency, and a hard floor under how "
                   "cheap a decision is allowed to get.",
        "default": "allow",
        "rules": [
            {"when": "burst_count > 100",
             "then": "challenge",
             "why": "A hundred moderation calls a minute is either a brigade "
                    "or a loop."},
            {"when": "unattended and max_tokens > 600",
             "then": "challenge",
             "why": "A moderation verdict should be short. Six hundred "
                    "tokens suggests the model is being asked to write an "
                    "essay nobody reads."},
        ],
    },
    {
        "name": "Sales outreach drafting",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "sales",
        "summary": "Personalised at the top, templated underneath. This "
                   "catches the templated part being paid for at full price.",
        "default": "downgrade",
        "rules": [
            {"when": "chars > 20000 and turns <= 3",
             "then": "challenge",
             "why": "Twenty thousand characters of context for a three-turn "
                    "draft is a prompt carrying a library."},
            {"when": "loop_count >= 4",
             "then": "block",
             "why": "The same outreach drafted four times is a queue "
                    "repeating."},
            {"when": "chars < 5000 and max_tokens <= 1000",
             "then": "downgrade",
             "why": "A short first-touch email is cheap-model work."},
        ],
    },
    {
        "name": "Recruitment screening",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "recruitment",
        "summary": "Screening runs at volume against long documents. Holds "
                   "unattended bulk decisions for a person.",
        "default": "allow",
        "rules": [
            {"when": "unattended and grind_count > 200",
             "then": "challenge",
             "why": "Two hundred screening decisions an hour with nobody "
                    "watching is a process that should be confirmed."},
            {"when": "turns > 15",
             "then": "challenge",
             "why": "Screening one candidate should not take fifteen turns "
                    "of carried context."},
            {"when": "loop_count >= 3",
             "then": "block",
             "why": "The same CV screened three times in two minutes."},
        ],
    },
    {
        "name": "Logistics exception handling",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "logistics",
        "summary": "Exceptions arrive in bursts when something goes wrong "
                   "upstream. This tells a burst from a storm.",
        "default": "allow",
        "rules": [
            {"when": "burst_count > 80 and loop_count >= 2",
             "then": "block",
             "why": "A burst of repeats is an upstream system retrying, and "
                    "every retry is bought."},
            {"when": "burst_count > 80",
             "then": "challenge",
             "why": "A genuine exception storm is worth a person seeing "
                    "before it is worth paying for."},
            {"when": "chars < 2500",
             "then": "downgrade",
             "why": "Most exception routing is short and structured."},
        ],
    },
    {
        "name": "Game NPC dialogue",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "gaming",
        "summary": "Variety is the product here, so this pack does not "
                   "punish temperature. It punishes context bloat instead.",
        "default": "allow",
        "rules": [
            {"when": "turns > 40",
             "then": "challenge",
             "why": "Forty turns of conversation history re-sent per line of "
                    "dialogue is the whole session paid for on every line."},
            {"when": "max_tokens > 500",
             "then": "challenge",
             "why": "NPC lines should be short. A five hundred token ceiling "
                    "on a line of dialogue is an accident."},
            {"when": "chars < 3000 and turns <= 10",
             "then": "downgrade",
             "why": "Short in-scene dialogue is cheap-model work."},
        ],
    },
    {
        "name": "Newsroom drafting",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "media",
        "summary": "Fast, long and deadline-driven. Tight on unattended, "
                   "loose on size.",
        "default": "allow",
        "rules": [
            {"when": "unattended and max_tokens > 3000",
             "then": "block",
             "why": "Three thousand tokens of copy generated with no editor "
                    "attached."},
            {"when": "loop_count >= 3 and not deterministic",
             "then": "challenge",
             "why": "Three regenerations of the same piece at temperature "
                    "cannot be reused and are bought each time."},
        ],
    },
    {
        "name": "Security operations triage",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "security",
        "summary": "Alert volume is the enemy. This pack assumes the "
                   "pipeline will misbehave before the analyst does.",
        "default": "allow",
        "rules": [
            {"when": "loop_count >= 2 and unattended",
             "then": "block",
             "why": "A detection pipeline re-asking the same alert is a "
                    "retry loop and every retry is billed."},
            {"when": "burst_count > 120",
             "then": "block",
             "why": "A hundred and twenty alerts a minute is a flood, and "
                    "paying a model per alert during a flood is how a "
                    "budget disappears in an afternoon."},
            {"when": "chars < 4000 and tool_count == 0",
             "then": "downgrade",
             "why": "Most alert enrichment is short and structured."},
        ],
    },
    {
        "name": "Insurance claims assistant",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "insurance",
        "summary": "Claims carry long histories and strict budgets. This "
                   "watches both.",
        "default": "allow",
        "rules": [
            {"when": "exposure > 0.6",
             "then": "challenge",
             "why": "One claim about to take most of the remaining budget."},
            {"when": "turns > 25 and chars > 30000",
             "then": "challenge",
             "why": "The full claim file is being re-sent on every question."},
            {"when": "unattended and max_tokens > 2000",
             "then": "challenge",
             "why": "A long unattended determination on a claim should reach "
                    "a person first."},
        ],
    },
    {
        "name": "Property listing generation",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "property",
        "summary": "Listings are short, repetitive and generated in batches. "
                   "The cheap model does most of this well.",
        "default": "downgrade",
        "rules": [
            {"when": "loop_count >= 3",
             "then": "block",
             "why": "The same property written three times in two minutes is "
                    "a batch repeating."},
            {"when": "max_tokens > 1200",
             "then": "challenge",
             "why": "A listing longer than twelve hundred tokens is not a "
                    "listing."},
        ],
    },
    {
        "name": "Ecommerce customer answers",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "ecommerce",
        "summary": "The same twenty questions, asked by thousands of people. "
                   "Reuse is where the money is.",
        "default": "downgrade",
        "rules": [
            {"when": "not deterministic",
             "then": "challenge",
             "why": "Temperature above zero on a delivery-times answer stops "
                    "it being reused and buys the same answer again for "
                    "every customer."},
            {"when": "chars < 2500 and turns <= 3",
             "then": "downgrade",
             "why": "A stock answer to a stock question."},
            {"when": "burst_count > 100",
             "then": "challenge",
             "why": "A hundred a minute is a promotion landing or a scraper "
                    "arriving."},
        ],
    },
    {
        "name": "Public sector correspondence",
        "author": "sebbi.pro",
        "version": "1.0.0",
        "vertical": "public-sector",
        "summary": "Written for a fixed annual budget that cannot be topped "
                   "up in March. Conservative by design.",
        "default": "allow",
        "rules": [
            {"when": "exposure > 0.4",
             "then": "challenge",
             "why": "A budget that cannot be increased should be spent in "
                    "deliberate steps, not in one call."},
            {"when": "exposure > 0.75",
             "then": "block",
             "why": "Past this, a single call risks the remainder of the "
                    "year."},
            {"when": "unattended and loop_count >= 2",
             "then": "block",
             "why": "Unattended repetition against a fixed budget."},
            {"when": "chars < 3000 and max_tokens <= 900",
             "then": "downgrade",
             "why": "Standard correspondence is cheap-model work."},
        ],
    },
]


def _seed(ctx):
    """Publish the seeds once. Idempotent - the digest catches repeats."""
    try:
        with ctx["lock"]:
            n = ctx["conn"].execute(
                "SELECT COUNT(*) FROM packs WHERE seeded=1").fetchone()[0]
        if n >= len(SEEDS):
            return
        for m in SEEDS:
            try:
                clean, compiled, profile = validate(m)
                _store(ctx, clean, profile, None, None, seeded=True)
            except Exception:                                # noqa: BLE001
                continue
    except Exception:                                        # noqa: BLE001
        pass


# ================================================================ the page
#
# THE SIGIL
# ---------
# Every pack draws itself. Nine spokes, one per signal, each as long as
# that pack leans on that signal, joined into a shape and given a hue
# derived from its own digest. Two packs that reason the same way look
# alike; two that reason differently cannot be mistaken for each other.
#
# It is not decoration bolted onto a list. The drawing is computed from
# the rules, so a pack that changes one threshold changes its own face.

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Signal Packs — the library</title>
<meta name="description" content="A public library of decision packs for the
token saver. Free to write, free to read, free to fork. Runs on the engine.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,700;9..144,900&family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --void:#05070d;
  --deep:#0a0f1c;
  --slab:#0e1524;
  --slab-2:#131c30;
  --edge:rgba(140,170,255,.14);
  --edge-hot:rgba(201,168,76,.42);
  --corona:#c9a84c;
  --ice:#8fd3ff;
  --text:#e9edf6;
  --mute:rgba(233,237,246,.44);
  --mute-2:rgba(233,237,246,.28);
  --allow:#2fbf87;
  --down:#4fa8d8;
  --chal:#d8a13c;
  --block:#e0574a;
  --disp:Fraunces,Georgia,serif;
  --mono:'IBM Plex Mono',ui-monospace,monospace;
  --body:Inter,system-ui,-apple-system,sans-serif;
}
html{-webkit-text-size-adjust:100%}
body{
  background:var(--void);color:var(--text);font:16px/1.6 var(--body);
  overflow-x:hidden;
  background-image:
    radial-gradient(120% 60% at 50% -10%,rgba(80,120,220,.18),transparent 60%),
    radial-gradient(80% 40% at 50% 0%,rgba(201,168,76,.10),transparent 70%);
  background-attachment:fixed;
}
.wrap{max-width:760px;margin:0 auto;padding:0 18px}
a{color:var(--ice);text-decoration:none}
a:hover{text-decoration:underline}
:focus-visible{outline:2px solid var(--corona);outline-offset:3px}

/* ---------- the eclipse ---------- */
.sky{position:relative;padding:46px 0 34px;text-align:center;overflow:hidden}
.eclipse{
  position:relative;width:172px;height:172px;margin:0 auto 26px;
}
.eclipse .ring{
  position:absolute;inset:0;border-radius:50%;
  background:conic-gradient(from 0deg,
    rgba(201,168,76,0) 0deg,
    rgba(201,168,76,.85) 40deg,
    rgba(143,211,255,.9) 120deg,
    rgba(201,168,76,.55) 210deg,
    rgba(201,168,76,0) 330deg);
  filter:blur(7px);
  animation:spin 34s linear infinite;
}
.eclipse .ring2{
  position:absolute;inset:-16px;border-radius:50%;
  background:conic-gradient(from 180deg,
    rgba(143,211,255,0) 0deg,
    rgba(143,211,255,.35) 90deg,
    rgba(201,168,76,.25) 200deg,
    rgba(143,211,255,0) 300deg);
  filter:blur(20px);opacity:.75;
  animation:spin 58s linear infinite reverse;
}
.eclipse .disc{
  position:absolute;inset:9px;border-radius:50%;
  background:radial-gradient(circle at 50% 45%,#0b1120,#05070d 70%);
  box-shadow:0 0 0 1px rgba(201,168,76,.35),0 0 60px rgba(0,0,0,.9) inset;
}
.eclipse .glyph{
  position:absolute;inset:0;display:grid;place-items:center;
  font:600 10px/1 var(--mono);letter-spacing:.34em;color:var(--corona);
  text-transform:uppercase;text-indent:.34em;
}
@keyframes spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.eclipse .ring,.eclipse .ring2{animation:none}}

h1{font:900 clamp(32px,8.4vw,54px)/1.02 var(--disp);letter-spacing:-.025em}
h1 em{font-style:normal;color:var(--corona)}
.lede{color:var(--mute);font-size:16.5px;max-width:46ch;margin:16px auto 0}
.lede b{color:var(--text);font-weight:600}

.split{
  display:flex;gap:0;justify-content:center;margin:26px auto 0;
  border:1px solid var(--edge);border-radius:3px;max-width:520px;overflow:hidden;
}
.split div{flex:1;padding:13px 12px;font:500 12.5px/1.45 var(--mono)}
.split div:first-child{border-right:1px solid var(--edge);
  background:rgba(47,191,135,.07);color:#9fe6c6}
.split div:last-child{background:rgba(201,168,76,.07);color:#e8cf8f}
.split b{display:block;font:600 10px/1 var(--mono);letter-spacing:.2em;
  text-transform:uppercase;color:var(--mute);margin-bottom:6px}

/* ---------- controls ---------- */
.bar{position:sticky;top:0;z-index:9;background:rgba(5,7,13,.92);
  backdrop-filter:blur(9px);border-bottom:1px solid var(--edge);
  padding:12px 0;margin-top:34px}
.bar .wrap{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input,select,textarea{
  background:var(--slab);border:1px solid var(--edge);border-radius:3px;
  color:var(--text);font:400 14px/1.5 var(--mono);padding:11px 12px;
}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--corona)}
#q{flex:1 1 190px;min-width:0}
select{flex:0 0 auto;max-width:46%}
.count{font:500 11px/1 var(--mono);color:var(--mute);letter-spacing:.12em;
  text-transform:uppercase;margin-left:auto}

/* ---------- a slab ---------- */
.shelf{padding:20px 0 10px}
.slab{
  border:1px solid var(--edge);border-radius:4px;background:var(--slab);
  margin-bottom:12px;overflow:hidden;
  transition:border-color .16s ease,transform .16s ease;
}
.slab:hover{border-color:var(--edge-hot)}
.slab.open{border-color:var(--edge-hot);background:var(--slab-2)}
.head{display:grid;grid-template-columns:74px 1fr;gap:14px;padding:14px;
  cursor:pointer;align-items:center}
.sig{width:74px;height:74px;display:block}
.meta .nm{font:700 17.5px/1.25 var(--disp);letter-spacing:-.01em}
.meta .by{font:400 11.5px/1.5 var(--mono);color:var(--mute);margin-top:3px;
  word-break:break-all}
.meta .sm{font-size:13.5px;color:var(--mute);margin-top:7px;line-height:1.5}
.chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:9px}
.chip{font:500 10px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;
  padding:4px 7px;border-radius:2px;border:1px solid var(--edge);
  color:var(--mute)}
.chip.v{color:#cfe0ff;border-color:rgba(140,170,255,.3)}
.chip.allow{color:var(--allow);border-color:rgba(47,191,135,.35)}
.chip.downgrade{color:var(--down);border-color:rgba(79,168,216,.35)}
.chip.challenge{color:var(--chal);border-color:rgba(216,161,60,.35)}
.chip.block{color:var(--block);border-color:rgba(224,87,74,.35)}

.body{display:none;padding:0 14px 16px;border-top:1px solid var(--edge)}
.slab.open .body{display:block}
.rule{border-bottom:1px solid rgba(140,170,255,.08);padding:12px 0}
.rule:last-child{border-bottom:none}
.when{font:500 13px/1.6 var(--mono);color:#cfe0ff;word-break:break-word}
.then{font:600 10.5px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;
  margin:8px 0 6px;display:inline-block}
.why{font-size:13.5px;color:var(--mute);line-height:1.55}
.foot{display:flex;gap:14px;flex-wrap:wrap;padding-top:12px;
  font:400 11px/1.5 var(--mono);color:var(--mute-2);word-break:break-all}
.acts{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.btn{background:transparent;border:1px solid var(--edge);color:var(--text);
  font:500 12.5px/1 var(--body);padding:10px 13px;border-radius:3px;
  cursor:pointer}
.btn:hover{border-color:var(--corona);color:var(--corona)}
.btn.gold{background:var(--corona);border-color:var(--corona);color:#070a12;
  font-weight:600}
.btn.gold:hover{background:#ddbc63;color:#070a12}

/* ---------- write ---------- */
section.write{border-top:1px solid var(--edge);margin-top:26px;padding:30px 0 10px}
h2{font:700 clamp(22px,5vw,30px)/1.15 var(--disp);letter-spacing:-.015em}
.sub{color:var(--mute);font-size:14.5px;margin:8px 0 18px;max-width:56ch}
textarea{width:100%;min-height:260px;resize:vertical;font-size:12.5px;
  line-height:1.65}
.out{margin-top:12px;border:1px solid var(--edge);border-radius:3px;
  padding:13px;font:400 12.5px/1.65 var(--mono);color:var(--mute);
  white-space:pre-wrap;word-break:break-word;min-height:52px}
.out.ok{color:#9fe6c6;border-color:rgba(47,191,135,.35)}
.out.bad{color:#ffb1a7;border-color:rgba(224,87,74,.4)}
.grammar{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:18px;
  border:1px solid var(--edge);border-radius:3px;overflow:hidden}
@media(max-width:560px){.grammar{grid-template-columns:1fr}}
.gcell{padding:12px 13px;border-bottom:1px solid var(--edge)}
.gcell:nth-child(odd){border-right:1px solid var(--edge)}
@media(max-width:560px){.gcell:nth-child(odd){border-right:none}}
.gcell b{display:block;font:600 10px/1 var(--mono);letter-spacing:.18em;
  text-transform:uppercase;color:var(--corona);margin-bottom:6px}
.gcell span{font:400 12.5px/1.55 var(--mono);color:var(--mute)}
footer{padding:34px 0 60px;color:var(--mute-2);font:400 12px/1.8 var(--mono);
  border-top:1px solid var(--edge);margin-top:30px}
.empty{padding:40px 0;text-align:center;color:var(--mute);font-size:14.5px}
</style>
</head>
<body>

<div class="sky">
  <div class="wrap">
    <div class="eclipse">
      <div class="ring2"></div><div class="ring"></div>
      <div class="disc"></div><div class="glyph">signal packs</div>
    </div>
    <h1>The rules are <em>free</em>.<br>Running them isn't.</h1>
    <p class="lede">A public library of decision packs for the token saver.
    Anyone can write one, anyone can read one, anyone can fork one and prove
    they wrote it first. <b>A pack decides nothing on its own</b> — it needs
    the engine underneath it, and that is where the receipt comes from.</p>
    <div class="split">
      <div><b>Free forever</b>write · read · fork · seal · prove it's yours</div>
      <div><b>Needs the engine</b>evaluate · decide · seal a receipt</div>
    </div>
  </div>
</div>

<div class="bar">
  <div class="wrap">
    <input id="q" placeholder="search the library" autocomplete="off"
           aria-label="Search packs">
    <select id="v" aria-label="Filter by vertical"><option value="">every vertical</option></select>
    <span class="count" id="count">—</span>
  </div>
</div>

<div class="wrap">
  <div class="shelf" id="shelf"><div class="empty">Opening the library…</div></div>

  <section class="write">
    <h2>Write one</h2>
    <p class="sub">No account. No key. Paste a pack, validate it, publish it.
    Publishing seals its digest into the chain, so the date and the wording are
    fixed and provable from that moment — including against me.</p>

    <textarea id="src" spellcheck="false" aria-label="Your pack"></textarea>
    <div class="acts">
      <button class="btn" id="check">Validate</button>
      <button class="btn gold" id="pub">Publish &amp; seal</button>
      <button class="btn" id="reset">Reset example</button>
    </div>
    <div class="out" id="msg">Nothing sent yet.</div>

    <div class="grammar" id="grammar"></div>
  </section>
</div>

<footer>
  <div class="wrap">
    Language, limits and every route: <a href="/x/packs/spec">/x/packs/spec</a><br>
    The engine these run on: <a href="/x/tokensaver/spec">/x/tokensaver/spec</a><br>
    sebbi.pro
  </div>
</footer>

<script>
var SIGNALS = ["exposure","size","ask","depth","tools","loop","burst","grind","novelty"];
var VERDICT_COLOUR = {allow:"#2fbf87",downgrade:"#4fa8d8",challenge:"#d8a13c",block:"#e0574a"};
var all = [];

function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}

/* hue from the digest, so a pack's colour is its own and never assigned */
function hueOf(d){
  var h=0; d=String(d||"");
  for(var i=0;i<16 && i<d.length;i++) h=(h*31+d.charCodeAt(i))%360;
  return h;
}

/* the sigil: nine spokes, one per signal, drawn from the pack's own rules */
function sigil(profile,digest,size){
  size=size||74;
  var c=size/2, R=c-7, hue=hueOf(digest);
  var sig=(profile&&profile.signals)||{};
  var pts=[], spokes="";
  for(var i=0;i<9;i++){
    var a=(Math.PI*2*i/9)-Math.PI/2;
    var w=Math.max(0,Math.min(1,+sig[SIGNALS[i]]||0));
    var r=6+R*w;
    var x=c+Math.cos(a)*r, y=c+Math.sin(a)*r;
    var ox=c+Math.cos(a)*R, oy=c+Math.sin(a)*R;
    pts.push(x.toFixed(1)+","+y.toFixed(1));
    spokes+='<line x1="'+c+'" y1="'+c+'" x2="'+ox.toFixed(1)+'" y2="'+oy.toFixed(1)+
            '" stroke="hsla('+hue+',60%,70%,.13)" stroke-width="1"/>';
    if(w>0) spokes+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+
            '" r="'+(1.6+w*1.9).toFixed(1)+'" fill="hsl('+hue+',72%,68%)"/>';
  }
  return '<svg class="sig" viewBox="0 0 '+size+' '+size+'" aria-hidden="true">'+
    '<circle cx="'+c+'" cy="'+c+'" r="'+R+'" fill="none" '+
      'stroke="hsla('+hue+',60%,65%,.18)" stroke-width="1"/>'+
    spokes+
    '<polygon points="'+pts.join(" ")+'" fill="hsla('+hue+',70%,60%,.20)" '+
      'stroke="hsl('+hue+',75%,66%)" stroke-width="1.4" stroke-linejoin="round"/>'+
    '<circle cx="'+c+'" cy="'+c+'" r="1.8" fill="hsl('+hue+',80%,78%)"/></svg>';
}

function slab(p){
  var m=p.manifest||{}, rules=m.rules||[];
  var body=rules.map(function(r){
    return '<div class="rule"><div class="when">'+esc(r.when)+'</div>'+
      '<div class="then" style="color:'+(VERDICT_COLOUR[r.then]||"#fff")+'">→ '+
      esc(r.then)+'</div><div class="why">'+esc(r.why)+'</div></div>';
  }).join("");
  var chips='<span class="chip v">'+esc(p.vertical)+'</span>'+
    '<span class="chip">'+rules.length+' rules</span>'+
    '<span class="chip '+esc(m.default||"allow")+'">default '+esc(m.default||"allow")+'</span>'+
    (p.origin==="library seed"?'<span class="chip">seed</span>':"")+
    (p.forked_from?'<span class="chip">fork</span>':"");
  return '<article class="slab" data-id="'+esc(p.id)+'">'+
    '<div class="head">'+sigil(p.profile,p.digest)+
      '<div class="meta"><div class="nm">'+esc(p.name)+'</div>'+
      '<div class="by">'+esc(p.author)+' · v'+esc(p.version)+'</div>'+
      (p.summary?'<div class="sm">'+esc(p.summary)+'</div>':"")+
      '<div class="chips">'+chips+'</div></div></div>'+
    '<div class="body">'+body+
      '<div class="foot"><span>id '+esc(p.id)+'</span>'+
      '<span>digest '+esc(String(p.digest||"").slice(0,20))+'…</span>'+
      (p.block_index!=null?'<span>block '+esc(p.block_index)+'</span>':"")+
      '<span>published '+esc(String(p.published||"").slice(0,10))+'</span></div>'+
      '<div class="acts"><button class="btn" data-fork="'+esc(p.id)+'">Fork it</button>'+
      '<button class="btn" data-copy="'+esc(p.id)+'">Copy JSON</button></div>'+
    '</div></article>';
}

function draw(){
  var q=(document.getElementById("q").value||"").toLowerCase().trim();
  var v=document.getElementById("v").value;
  var list=all.filter(function(p){
    if(v && p.vertical!==v) return false;
    if(!q) return true;
    var hay=(p.name+" "+p.author+" "+p.summary+" "+p.vertical+" "+
      JSON.stringify(p.manifest||{})).toLowerCase();
    return hay.indexOf(q)>=0;
  });
  document.getElementById("count").textContent=list.length+" of "+all.length;
  document.getElementById("shelf").innerHTML = list.length
    ? list.map(slab).join("")
    : '<div class="empty">Nothing matches that yet. Write it.</div>';
}

document.addEventListener("click",function(e){
  var h=e.target.closest(".head");
  if(h){ h.parentNode.classList.toggle("open"); return; }
  var f=e.target.getAttribute&&e.target.getAttribute("data-fork");
  if(f){ forkInto(f); return; }
  var c=e.target.getAttribute&&e.target.getAttribute("data-copy");
  if(c){ copyOut(c); return; }
});

function find(id){ for(var i=0;i<all.length;i++) if(all[i].id===id) return all[i]; }

function forkInto(id){
  var p=find(id); if(!p) return;
  var m=JSON.parse(JSON.stringify(p.manifest||{}));
  m.name=m.name+" (fork)";
  m.author="your name here";
  m.version="1.0.0";
  document.getElementById("src").value=JSON.stringify(m,null,2);
  document.getElementById("src").dataset.parent=id;
  document.getElementById("msg").className="out";
  document.getElementById("msg").textContent=
    "Forked "+id+" into the editor. Put your name on it, change what you "+
    "disagree with, then publish. The parent is recorded, so the lineage is "+
    "visible rather than claimed.";
  document.querySelector("section.write").scrollIntoView({behavior:"smooth"});
}

function copyOut(id){
  var p=find(id); if(!p) return;
  var t=JSON.stringify(p.manifest,null,2);
  if(navigator.clipboard) navigator.clipboard.writeText(t);
  document.getElementById("msg").className="out ok";
  document.getElementById("msg").textContent="Copied "+id+" to your clipboard.";
}

function post(action,body){
  return fetch("/x/packs/"+action,{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)}).then(function(r){return r.json();});
}

function readSrc(){
  try{ return JSON.parse(document.getElementById("src").value); }
  catch(e){
    document.getElementById("msg").className="out bad";
    document.getElementById("msg").textContent=
      "That is not valid JSON yet — "+e.message;
    return null;
  }
}

document.getElementById("check").addEventListener("click",function(){
  var m=readSrc(); if(!m) return;
  var out=document.getElementById("msg");
  out.className="out"; out.textContent="Parsing every rule…";
  post("validate",{pack:m}).then(function(d){
    if(d.ok){
      out.className="out ok";
      out.textContent="Valid. "+d.rule_count+" rules, hardest verdict "+
        d.profile.hardest_verdict+", reads: "+d.profile.reads.join(", ")+
        ".\nDigest "+d.digest+"\nNothing published — press Publish when ready.";
    }else{
      out.className="out bad";
      out.textContent=d.detail||d.error||"That did not parse.";
    }
  }).catch(function(e){
    out.className="out bad"; out.textContent="Could not reach the library: "+e;
  });
});

document.getElementById("pub").addEventListener("click",function(){
  var m=readSrc(); if(!m) return;
  var parent=document.getElementById("src").dataset.parent||null;
  var out=document.getElementById("msg");
  out.className="out"; out.textContent="Sealing…";
  post(parent?"fork":"publish",parent?{pack:m,parent:parent}:{pack:m})
  .then(function(d){
    if(d.ok===false||d.error){
      out.className="out bad";
      out.textContent=d.detail||d.error;return;
    }
    out.className="out ok";
    out.textContent="Published as "+d.id+
      (d.block_index!=null?("\nSealed at block "+d.block_index):"")+
      "\nDigest "+d.digest+
      "\nIt is in the library now and anyone can fork it.";
    load();
  }).catch(function(e){
    out.className="out bad"; out.textContent="Could not reach the library: "+e;
  });
});

var EXAMPLE={
  name:"My first pack",
  author:"your name or domain",
  version:"1.0.0",
  vertical:"general",
  summary:"One line someone paying the bill would understand.",
  default:"allow",
  rules:[
    {when:"loop_count >= 3 and not deterministic",
     then:"challenge",
     why:"The same request three times at temperature cannot be reused, so it is bought again each time."},
    {when:"unattended and max_tokens > 4000",
     then:"block",
     why:"A long generation with nobody watching is a cost with no reader."},
    {when:"chars < 2500 and turns <= 4 and tool_count == 0",
     then:"downgrade",
     why:"Short and simple is what the cheap model is for."}
  ]
};
function resetSrc(){
  document.getElementById("src").value=JSON.stringify(EXAMPLE,null,2);
  delete document.getElementById("src").dataset.parent;
  document.getElementById("msg").className="out";
  document.getElementById("msg").textContent="Nothing sent yet.";
}
document.getElementById("reset").addEventListener("click",resetSrc);
document.getElementById("q").addEventListener("input",draw);
document.getElementById("v").addEventListener("change",draw);

function load(){
  fetch("/x/packs/list?limit=200").then(function(r){return r.json();})
  .then(function(d){
    all=d.packs||[];
    var sel=document.getElementById("v"), have={};
    all.forEach(function(p){have[p.vertical]=1;});
    var keep=sel.value;
    sel.innerHTML='<option value="">every vertical</option>'+
      Object.keys(have).sort().map(function(v){
        return '<option value="'+esc(v)+'">'+esc(v)+'</option>';}).join("");
    sel.value=keep;
    if(d.grammar){
      document.getElementById("grammar").innerHTML=
        Object.keys(d.grammar).map(function(k){
          return '<div class="gcell"><b>'+esc(k)+'</b><span>'+
            esc(d.grammar[k])+'</span></div>';}).join("");
    }
    draw();
  }).catch(function(){
    document.getElementById("shelf").innerHTML=
      '<div class="empty">The library could not be reached.</div>';
  });
}
resetSrc();
load();
</script>
</body>
</html>"""


_patched = [False]


def _install_page():
    """Serve /packs by wrapping the running handler's do_GET, once."""
    if _patched[0]:
        return True
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            names = dir(mod)
        except Exception:                                    # noqa: BLE001
            continue
        for nm in names:
            try:
                obj = getattr(mod, nm, None)
            except Exception:                                # noqa: BLE001
                continue
            if not isinstance(obj, type):
                continue
            if not (hasattr(obj, "do_GET") and hasattr(obj, "do_POST")):
                continue
            if getattr(obj, "_packs_patched", False):
                _patched[0] = True
                return True
            original = obj.do_GET

            def patched(self, _original=original):
                try:
                    path = self.path.split("?")[0].rstrip("/") or "/"
                except Exception:                            # noqa: BLE001
                    path = ""
                if path in ("/packs", "/packs.html", "/library"):
                    data = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type",
                                     "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return _original(self)

            obj.do_GET = patched
            obj._packs_patched = True
            _patched[0] = True
            return True
    return False


# ================================================================ routes

GRAMMAR = {
    "signals, 0.0 to 1.0": "exposure size ask depth tools loop burst grind "
                           "novelty",
    "raw counts": "chars max_tokens turns tool_count loop_count burst_count "
                  "grind_count",
    "flags": "unattended deterministic",
    "the engine's score": "score",
    "operators": "> >= < <= == != and or not ( )",
    "verdicts": "allow downgrade challenge block",
}


def _spec():
    return {
        "module": "packs",
        "version": VERSION,
        "what_this_is": (
            "A public library of decision packs for the token saver. A pack "
            "is data, not code: conditions over the nine signals the engine "
            "already measures, and a verdict for each."),
        "the_deal": {
            "free_forever_no_account": [
                "write a pack", "read any pack", "fork any pack",
                "seal a pack so its date and wording are provable",
                "validate a pack's syntax",
            ],
            "needs_a_key": [
                "run a pack against a request",
                "get a verdict",
                "get a sealed receipt for that verdict",
            ],
            "why": (
                "A pack on its own decides nothing and produces no evidence. "
                "The thresholds are the author's and they are public. The "
                "execution, the measurement and the receipt are the engine's, "
                "and that is what is being sold. An author can therefore "
                "build something genuinely theirs and prove it is theirs "
                "without paying anything - and everyone who uses it arrives "
                "here to run it."),
        },
        "language": GRAMMAR,
        "language_notes": [
            "There is no syntax for calling anything, reading anything, or "
            "assigning anything. Expressions are parsed into a tree and "
            "walked; nothing reaches eval, exec or compile.",
            "Rules are tried in order and the first match decides. If none "
            "match, the pack's default decides.",
            "A pack can only make the engine's decision stricter. It can "
            "never weaken a hard rule, and an attempt to do so is reported "
            "rather than silently dropped.",
            "A pack can never return 'serve'. Serving from store is a fact "
            "about whether an identical request was answered before, not a "
            "policy.",
        ],
        "limits": {
            "rules_per_pack": MAX_RULES,
            "characters_per_expression": MAX_EXPR_CHARS,
            "manifest_bytes": MAX_MANIFEST_BYTES,
        },
        "sigil": (
            "Every pack draws itself: nine spokes, one per signal, each as "
            "long as the pack leans on that signal, in a hue derived from "
            "its own digest. Computed from the rules, so the drawing is the "
            "pack rather than a picture attached to it."),
        "routes": {
            "public": ["GET spec", "GET list", "GET get", "GET status",
                       "POST validate", "POST publish", "POST fork"],
            "keyed": ["POST run"],
        },
        "page": "/packs",
        "does_not_prove": [
            "That a pack's thresholds are good ones. Sealing fixes the "
            "wording and the date, not the judgement.",
            "That an author is who they say they are. Names are "
            "self-declared, as everywhere else on this deployment.",
        ],
    }, 200


def _status(ctx):
    installed = _install_page()
    n = seeds = 0
    try:
        with ctx["lock"]:
            n = ctx["conn"].execute("SELECT COUNT(*) FROM packs").fetchone()[0]
            seeds = ctx["conn"].execute(
                "SELECT COUNT(*) FROM packs WHERE seeded=1").fetchone()[0]
    except Exception:                                        # noqa: BLE001
        pass
    return {"module": "packs", "version": VERSION, "page": "/packs",
            "page_installed": installed, "packs": n, "seeds": seeds,
            "published_by_others": max(0, n - seeds),
            "note": "publishing and reading need no key; running one does"}, 200


def _list(ctx, data):
    try:
        limit = min(LIST_LIMIT, max(1, int(data.get("limit") or 100)))
    except (TypeError, ValueError):
        limit = 100
    vertical = str(data.get("vertical") or "").strip().lower()
    with ctx["lock"]:
        if vertical:
            rows = ctx["conn"].execute(
                "SELECT * FROM packs WHERE vertical=? "
                "ORDER BY runs DESC, id DESC LIMIT ?",
                (vertical, limit)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT * FROM packs ORDER BY runs DESC, id DESC LIMIT ?",
                (limit,)).fetchall()
    return {"count": len(rows),
            "packs": [_row_to_pack(r, full=True) for r in rows],
            "verticals": list(VERTICALS),
            "grammar": GRAMMAR,
            "how_to_run_one": (
                "POST /x/packs/run with a key, a pack id, and either a "
                "request body or a token saver digest."),
            "note": ("Being in this library is not endorsement. Anyone may "
                     "publish and nothing here is reviewed.")}, 200


def _get(ctx, data):
    pid = str(data.get("id") or "").strip()
    if not pid:
        return {"error": "id_required",
                "usage": "/x/packs/get?id=<pack id>"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT * FROM packs WHERE pack_id=?", (pid,)).fetchone()
    if not row:
        return {"error": "unknown_pack", "id": pid}, 404
    out = _row_to_pack(row, full=True)
    out["grammar"] = GRAMMAR
    return out, 200


def _validate_action(data):
    m = data.get("pack") or data.get("manifest") or data
    try:
        clean, compiled, profile = validate(m)
    except PackError as exc:
        return {"ok": False, "error": "invalid_pack", "detail": str(exc)}, 400
    return {"ok": True, "rule_count": len(clean["rules"]),
            "digest": _digest(clean), "profile": profile,
            "normalised": clean,
            "note": "nothing was published"}, 200


def _publish_action(ctx, data, api_key, parent=None):
    m = data.get("pack") or data.get("manifest")
    if not isinstance(m, dict):
        return {"error": "pack_required",
                "detail": "send the pack under 'pack'"}, 400
    try:
        clean, compiled, profile = validate(m)
    except PackError as exc:
        return {"ok": False, "error": "invalid_pack", "detail": str(exc)}, 400

    if parent:
        with ctx["lock"]:
            p = ctx["conn"].execute(
                "SELECT pack_id FROM packs WHERE pack_id=?",
                (parent,)).fetchone()
        if not p:
            return {"error": "unknown_parent", "parent": parent}, 404

    out = _store(ctx, clean, profile, parent, api_key)
    out["ok"] = True
    return out, 200


def _run(ctx, data, api_key):
    """
    Evaluate a pack. This is the keyed half and the reason the free half
    can be free.
    """
    pid = str(data.get("id") or data.get("pack_id") or "").strip()
    if not pid:
        return {"error": "id_required",
                "detail": "which pack should decide this?"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT * FROM packs WHERE pack_id=?", (pid,)).fetchone()
    if not row:
        return {"error": "unknown_pack", "id": pid}, 404

    manifest = json.loads(row[8])
    try:
        clean, compiled, profile = validate(manifest)
    except PackError as exc:
        return {"error": "pack_no_longer_valid", "detail": str(exc)}, 500

    measured = data.get("measured")
    signals = data.get("signals")
    if not isinstance(measured, dict) or not isinstance(signals, dict):
        return {"error": "measurements_required",
                "detail": ("send 'measured' and 'signals' exactly as "
                           "/x/tokensaver/gate returned them, plus its "
                           "'score' and 'verdict'. Call the gate first; this "
                           "route decides on top of it, it does not replace "
                           "it."),
                "example": {"id": pid, "verdict": "ALLOW", "score": 0.31,
                            "signals": {"loop": 0.4}, "measured": {}}}, 400

    engine_verdict = str(data.get("verdict") or "allow").strip().lower()
    if engine_verdict == "serve":
        return {"error": "already_served",
                "detail": ("this request was answered from store, so nothing "
                           "was bought and there is nothing for a pack to "
                           "decide")}, 400
    if engine_verdict not in VERDICTS:
        engine_verdict = "allow"

    env = _env(measured, signals, data.get("score"),
               data.get("unattended"), data.get("deterministic", True))
    result = apply_pack(compiled, clean["default"], env, engine_verdict)

    h, idx, seq = _seal(ctx, "signalpack_run", {
        "decision": "PACK_" + result["verdict"].upper(),
        "pack_id": pid, "pack_digest": row[10],
        "pack_version": clean["version"], "pack_author": clean["author"],
        "engine_verdict": engine_verdict,
        "pack_verdict": result["pack_verdict"],
        "final_verdict": result["verdict"],
        "matched_rule": result["matched_rule"],
        "capped_by_engine": result["capped_by_engine"],
        "note": ("the pack that decided this is sealed by digest, so which "
                 "rules were in force at this moment is fixed and cannot be "
                 "edited afterwards"),
    }, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE packs SET runs=runs+1 WHERE pack_id=?", (pid,))
        ctx["conn"].commit()

    out = dict(result)
    out.update({
        "pack": {"id": pid, "name": clean["name"], "author": clean["author"],
                 "version": clean["version"], "digest": row[10]},
        "environment": env,
        "receipt": {"audit_hash": h, "block_index": idx, "receipt_seq": seq},
        "what_this_proves": (
            "that this verdict was reached by this exact pack, against these "
            "measurements, at this position in the chain. The pack's digest "
            "is in the block, so nobody can later claim different rules "
            "applied."),
        "what_this_does_not_prove": (
            "that the pack's thresholds were sensible ones."),
    })
    return out, 200


# ---------------------------------------------------------------- handler

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if method == "GET" and action == "spec":
        return _spec()

    try:
        _setup(ctx)
    except Exception as exc:                                 # noqa: BLE001
        return {"error": "library_unavailable",
                "detail": "%s: %s" % (type(exc).__name__, exc)}, 500

    if method == "GET":
        if action == "status":
            return _status(ctx)
        if action == "list":
            return _list(ctx, data)
        if action == "get":
            return _get(ctx, data)

    if method == "POST":
        if action == "validate":
            return _validate_action(data)
        if action == "publish":
            return _publish_action(ctx, data, api_key)
        if action == "fork":
            parent = str(data.get("parent") or data.get("forked_from")
                         or "").strip()
            if not parent:
                return {"error": "parent_required",
                        "detail": "a fork names the pack it came from"}, 400
            return _publish_action(ctx, data, api_key, parent)
        if action == "run":
            if not api_key:
                return {"error": "invalid_api_key",
                        "detail": ("running a pack needs a key. Writing, "
                                   "reading and forking never will."),
                        "free_routes": ["list", "get", "validate", "publish",
                                        "fork"]}, 401
            return _run(ctx, data, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "status", "list", "get"],
            "POST": ["validate", "publish", "fork", "run (keyed)"]}, 404

```
