# Codebase — part 5 of 31

Contains:
- `modules/continuity.py`
- `modules/counterfactual.py`


## `modules/continuity.py`

1795 lines, 82796 bytes

```python
#!/usr/bin/env python3
"""
modules/continuity.py  -  authority continuity
===========================================

THE QUESTION THIS ANSWERS
-------------------------
Can every autonomous action be traced from the human authority that started
it to the execution that ended it, and can it be shown that identity,
authority, boundary, intent and validity survived every hop in between?

Permissions answer "may this actor do this now". That is one hop. An
autonomous system is many hops, and the interesting failures are never at
the last one. They are three delegations back, where a scope was widened by
a system that had every right to delegate and no right to delegate THAT.

WHAT THIS MODULE IS NOT
-----------------------
It is not a new evidence layer. AILeash already has one, and a second would
be a second thing to trust. Every record here is sealed through ctx["seal"]
into the same chain, so authority evidence inherits ordering, integrity,
period commitment, absence proofs and external anchoring without asking for
any of it.

It is also not a permission system. It sits underneath one. A permission
system answers from a table. This answers from a derivation.

THE INVARIANT
-------------
A downstream agent may inherit or narrow authority. It can never exercise
more authority than can be derived from a valid upstream grant.

Everything below is machinery for making that sentence checkable.

  IDENTITY      every grant names an issuer and a subject, and the grant
                record is sealed, so the actor at each hop is attributable
                to something that cannot be edited afterwards.
  AUTHORITY     every grant except a root points at a parent. A root must
                be issued by a human principal and is marked as such.
                An orphan is not a root, it is a forgery.
  BOUNDARY      a child must be a subset of its parent on every axis, and
                the check is re-run at exercise, not just at issue. Issue
                time is not enough: the parent may have been narrowed or
                revoked since.
  INTENT        purpose tags are carried and must narrow. An action whose
                declared purpose is not covered is not assumed hostile and
                is not assumed fine - it is CHALLENGED.
  TEMPORAL      every ancestor must be valid at the instant of evaluation.
                A leaf inside its window under an expired parent is dead.
  EVIDENCE      the evaluation, the full lineage digest, and the parameter
                digest are sealed together, so what was decided and what it
                was decided about cannot drift apart later.

DETERMINISTIC WHERE POSSIBLE, HONEST WHERE NOT
----------------------------------------------
Structure is decidable. Scope containment, constraint narrowing, temporal
windows, revocation, depth, cycles and record integrity are arithmetic and
set membership, and every one of them produces BLOCK on failure with the
exact grant and invariant named. No scoring, no thresholds, no judgement.

Meaning is not decidable. Whether "process the refund queue" covers paying
a supplier is a question about intent, and a system that answers it with a
confident boolean is lying. Those cases return CHALLENGE, which is the
mechanism AILeash already has for exactly this: a machine that knows it
does not know, escalating to a human whose answer is sealed before the
machine's own view is revealed.

Three things trigger CHALLENGE rather than ALLOW:

  1. The action declares a purpose the grant does not carry. Intent
     compatibility is unproven in both directions.
  2. Authority is only covered by a broad wildcard. Technically derived,
     practically unreviewable, and the place scope creep hides.
  3. The action varies a dimension no ancestor constrains. An unconstrained
     dimension is not permission, it is an unasked question.

WHAT IS DELIBERATELY REFUSED
----------------------------
  - No union of grants. One action derives from one lineage. Two narrow
    grants that jointly exceed either is the oldest escalation trick there
    is, and the only defence that holds is to never combine them.
  - No re-parenting. A grant's parent is fixed at issue and part of its
    digest.
  - No retroactive widening. Editing a stored grant changes its digest and
    fails integrity against the sealed value.
  - No implicit inheritance of unknown keys. A constraint the parent never
    expressed cannot be narrowed by a child, so a child that introduces one
    is escalating.

HONEST LIMITS
-------------
  - This proves authority was derivable, not that the human who issued the
    root grant should have. Root legitimacy is an organisational question.
  - Grants are authenticated by sealing rather than by signature, so an
    outside party verifies them through the chain rather than offline.
    Offline verification needs per-issuer signing keys and is not built.
  - An action that never reached this module is outside all of it, exactly
    as with completeness. What changes is that the operator cannot choose
    which of the evaluated actions to show.

    POST /x/continuity/issue      grant or delegate authority     (keyed)
    POST /x/continuity/revoke     revoke, transitively            (keyed)
    POST /x/continuity/exercise   evaluate an action              (keyed)
    POST /x/continuity/confirm    bind execution to evaluation    (keyed)
    GET  /x/continuity/trace      full lineage of a grant         (public)
    GET  /x/continuity/decision   a sealed evaluation             (public)
    GET  /x/continuity/spec       the exact derivation rules      (public)
"""

import binascii
import hashlib
import json
import os
import secrets
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.5.1"

PUBLIC = {("GET", "trace"), ("GET", "decision"), ("GET", "decisions"),
          ("GET", "spec"), ("GET", "proof"), ("GET", "pubkey")}

BUNDLE_VERSION = "1.0"
BUNDLE_PREFIX = b"AILEASH-AUTHORITY-PROOF-v1:"

# ----------------------------------------------------------------------
# Ed25519, RFC 8032, standard library only.
#
# Carried in full rather than imported so that anyone verifying a proof from
# this system runs the same code with nothing installed. A proof that requires
# the verifier to fetch a dependency is a proof with a gatekeeper, and the
# whole point of an exported proof is that it survives leaving here.
#
# Cross-checked against an independent implementation: identical public keys
# and byte-identical signatures across random keys and messages, both
# directions, with every tampered variant rejected.
# ----------------------------------------------------------------------


_ed_Q = 2 ** 255 - 19
_ed_L = 2 ** 252 + 27742317777372353535851937790883648493
_ed_D = -121665 * pow(121666, _ed_Q - 2, _ed_Q) % _ed_Q
_ed_I = pow(2, (_ed_Q - 1) // 4, _ed_Q)


def _ed_h(m):
    return hashlib.sha512(m).digest()


def _ed_inv(x):
    return pow(x, _ed_Q - 2, _ed_Q)


def _ed_xrecover(y):
    xx = (y * y - 1) * _ed_inv(_ed_D * y * y + 1)
    x = pow(xx, (_ed_Q + 3) // 8, _ed_Q)
    if (x * x - xx) % _ed_Q != 0:
        x = (x * _ed_I) % _ed_Q
    if x % 2 != 0:
        x = _ed_Q - x
    return x


_ed_BY = 4 * _ed_inv(5) % _ed_Q
_ed_BX = _ed_xrecover(_ed_BY)
_ed_B = (_ed_BX % _ed_Q, _ed_BY % _ed_Q, 1, (_ed_BX * _ed_BY) % _ed_Q)

_ed_IDENT = (0, 1, 1, 0)


def _ed_add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _ed_Q
    b = (y1 + x1) * (y2 + x2) % _ed_Q
    c = t1 * 2 * _ed_D * t2 % _ed_Q
    dd = z1 * 2 * z2 % _ed_Q
    e = b - a
    f = dd - c
    g = dd + c
    hh = b + a
    return (e * f % _ed_Q, g * hh % _ed_Q, f * g % _ed_Q, e * hh % _ed_Q)


def _ed_double(p):
    return _ed_add(p, p)


def _ed_scalarmult(p, e):
    if e == 0:
        return _ed_IDENT
    q = _ed_scalarmult(p, e // 2)
    q = _ed_double(q)
    if e & 1:
        q = _ed_add(q, p)
    return q


def _ed_encodepoint(p):
    x, y, z, _t = p
    zi = _ed_inv(z)
    x = x * zi % _ed_Q
    y = y * zi % _ed_Q
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _ed_bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _ed_publickey(sk):
    """32-byte seed -> 32-byte public key."""
    h = _ed_h(sk)
    a = 2 ** 254 + sum(2 ** i * _ed_bit(h, i) for i in range(3, 254))
    return _ed_encodepoint(_ed_scalarmult(_ed_B, a))


def _ed_hint(m):
    h = _ed_h(m)
    return sum(2 ** i * _ed_bit(h, i) for i in range(512))


def _ed_signature(m, sk, pk):
    h = _ed_h(sk)
    a = 2 ** 254 + sum(2 ** i * _ed_bit(h, i) for i in range(3, 254))
    r = _ed_hint(h[32:64] + m)
    rr = _ed_scalarmult(_ed_B, r)
    enc_r = _ed_encodepoint(rr)
    s = (r + _ed_hint(enc_r + pk + m) * a) % _ed_L
    return enc_r + s.to_bytes(32, "little")


def _ed_isoncurve(p):
    x, y, z, t = p
    return (z % _ed_Q != 0
            and x * y % _ed_Q == z * t % _ed_Q
            and (y * y - x * x - z * z - _ed_D * t * t) % _ed_Q == 0)


def _ed_decodepoint(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _ed_xrecover(y)
    if x & 1 != _ed_bit(s, 255):
        x = _ed_Q - x
    p = (x, y, 1, (x * y) % _ed_Q)
    if not _ed_isoncurve(p):
        raise ValueError("point off curve")
    return p


def _ed_checkvalid(sig, m, pk):
    """True when sig is a valid Ed25519 _ed_signature over m under pk."""
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        rr = _ed_decodepoint(sig[:32])
        a = _ed_decodepoint(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:64], "little")
    if s >= _ed_L:
        return False
    hh = _ed_hint(sig[:32] + pk + m)
    x1 = _ed_scalarmult(_ed_B, s)
    x2 = _ed_add(rr, _ed_scalarmult(a, hh))
    return _ed_encodepoint(x1) == _ed_encodepoint(x2)


GRANT_PREFIX = b"AILEASH-GRANT-v1:"
EVAL_PREFIX = b"AILEASH-AUTHEVAL-v1:"

# The live scorer is found at runtime rather than imported, the same way
# replay.py finds it. server.py is never imported by a module.
SCORER_NAMES = ["score_event", "score", "evaluate_event", "evaluate", "decide", "risk_score"]

# Some scorers answer with a band, some with a number. When it is a number it
# has to be banded here, and these two figures MUST match the deployed engine.
# They are a copy, and a copy is a thing that drifts: change a threshold in
# server.py and this file is silently wrong until someone notices. Prefer a
# scorer that returns its own decision, which needs none of this.
ALLOW_BELOW = 0.35
CHALLENGE_BELOW = 0.70

MAX_DEPTH = 32            # hard ceiling on lineage length
MAX_WALK = 128            # cycle guard, independent of MAX_DEPTH
DEFAULT_WINDOW = 300      # seconds an ALLOW stays bindable before re-evaluation
ID_RE = re.compile(r"^[A-Za-z0-9._:@+-]{1,120}$")
# Capabilities are matched by string equality and prefix, so a value that
# differs only by whitespace or case would be a different capability that
# looks identical in a report. Rejected rather than normalised: silently
# trimming means the action evaluated is not the action the caller sent.
CAP_RE = re.compile(r"^[A-Za-z0-9._*-]{1,200}$")

# Constraint key grammar. The prefix decides the narrowing direction, so a
# new constraint needs no code change - only a name that says which way it
# tightens. A key that fits no rule is not guessed at.
#   max_*      child must be <= parent
#   min_*      child must be >= parent
#   allowed_*  child set must be a subset of parent set
#   denied_*   child set must be a superset of parent set
#   may_*      child may be True only if parent is True
def _num(value):
    """Numeric coercion that refuses booleans.

    float(True) is 1.0, so a boolean sails under any max_ cap. A boolean is
    not a small number, it is a different type arriving where a number was
    expected, and that is a comparison failure rather than a pass.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError("not a number")
    return float(value)


def _as_set(value):
    """Set coercion for allowed_/denied_ axes.

    A bare string is one member, never its characters. Without this,
    allowed_currency: "GBP" would accept "G", because "G" is in "GBP".
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        return set(value)
    return {value}


NUMERIC_MAX = "max_"
NUMERIC_MIN = "min_"
ALLOWED = "allowed_"
DENIED = "denied_"
FLAG = "may_"

RANK = {"ALLOW": 0, "CHALLENGE": 1, "BLOCK": 2}

_signing = {}


def _keys(ctx):
    """The signing key for exported proofs.

    Read from the CONTINUITY_SIGNING_SEED environment variable when set, so
    the key can live outside the database. Otherwise generated once and
    stored, which is worse and says so in the response rather than quietly.
    """
    if _signing.get("pk"):
        return _signing["seed"], _signing["pk"], _signing["source"]

    seed = None
    source = "environment"
    env = os.environ.get("CONTINUITY_SIGNING_SEED", "").strip()
    if env:
        try:
            raw = binascii.unhexlify(env)
            if len(raw) == 32:
                seed = raw
        except Exception:
            seed = None
    if seed is None:
        source = "database"
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT v FROM auth_meta WHERE k='signing_seed'").fetchone()
            if row:
                seed = binascii.unhexlify(row[0])
            else:
                seed = secrets.token_bytes(32)
                ctx["conn"].execute("INSERT INTO auth_meta(k,v) VALUES(?,?)",
                                    ("signing_seed", binascii.hexlify(seed).decode()))
                ctx["conn"].commit()
                print("CONTINUITY: generated a signing key. Move it to "
                      "CONTINUITY_SIGNING_SEED to keep it out of the database.",
                      flush=True)

    pk = _ed_publickey(seed)
    _signing.update(seed=seed, pk=pk, source=source)
    return seed, pk, source

_ready = False


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _live_scorer():
    """The deployed decision function, located by name at runtime.

    Authority is a gate in front of the existing engine, not a rival to it.
    If the scorer cannot be found, that is reported rather than silently
    treated as an ALLOW - a missing risk opinion is missing, not favourable.
    """
    s = _srv()
    if s is None:
        return None, "server module not reachable from this module"
    for name in SCORER_NAMES:
        fn = getattr(s, name, None)
        if callable(fn):
            return fn, name
    return None, "no scorer found under " + ", ".join(SCORER_NAMES)


def _band(score):
    """A number turned into a band. Only used when the engine gives no word."""
    if score < ALLOW_BELOW:
        return "ALLOW"
    if score < CHALLENGE_BELOW:
        return "CHALLENGE"
    return "BLOCK"


def _as_score(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _read_verdict(result):
    """Pull a decision out of whatever shape the engine returns.

    A stated decision always wins. A bare score is banded, and the response
    says so, because a banded score is this module's reading of the engine
    rather than the engine's own answer.
    """
    if isinstance(result, dict):
        for key in ("decision", "verdict", "action"):
            v = result.get(key)
            if isinstance(v, str) and v.upper() in RANK:
                return v.upper(), dict(result)
        for key in ("score", "risk_score", "risk", "value", "result"):
            sc = _as_score(result.get(key))
            if sc is not None:
                out = dict(result)
                out["banded_from_score"] = sc
                return _band(sc), out

    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str) and item.upper() in RANK:
                return item.upper(), {"raw": list(result)}
        for item in result:
            v, detail = _read_verdict(item)
            if v:
                return v, detail if isinstance(detail, dict) else {"raw": list(result)}
        for item in result:
            sc = _as_score(item)
            if sc is not None:
                return _band(sc), {"raw": list(result), "banded_from_score": sc}

    if isinstance(result, str) and result.upper() in RANK:
        return result.upper(), {"raw": result}

    sc = _as_score(result)
    if sc is not None:
        return _band(sc), {"raw": result, "banded_from_score": sc}

    return None, None


def _risk_opinion(event):
    """Ask the existing engine what it thinks of the same action.

    Failure here is never an ALLOW. The engine either answers or is recorded
    as not having answered, and an unanswered risk question is a reason to
    involve a human rather than to proceed.
    """
    fn, why = _live_scorer()
    if fn is None:
        return None, {"available": False, "reason": why}
    try:
        raw = fn(event)
    except Exception as exc:
        return None, {"available": False, "reason": "scorer raised: " + str(exc)[:160]}
    verdict, detail = _read_verdict(raw)
    if verdict is None:
        return None, {"available": False,
                      "reason": "scorer returned a shape this module could not read"}
    out = {"available": True, "verdict": verdict, "scorer": _live_scorer()[1]}
    if isinstance(detail, dict):
        if "score" in detail:
            out["score"] = detail["score"]
        if "banded_from_score" in detail:
            out["banded_from_score"] = detail["banded_from_score"]
            out["note"] = ("the engine returned a number rather than a decision, so it was "
                           "banded here using thresholds this module holds a copy of")
    return verdict, out


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS auth_grant("
                  "id TEXT PRIMARY KEY,parent TEXT,root TEXT,issuer TEXT,issuer_kind TEXT,"
                  "subject TEXT,subject_kind TEXT,scope TEXT,constraints TEXT,"
                  "purpose TEXT,purpose_tags TEXT,not_before REAL,not_after REAL,"
                  "depth INTEGER,delegations_left INTEGER,created REAL,digest TEXT,"
                  "audit_hash TEXT,block_index INTEGER,api_key TEXT,"
                  "risk_accepted_by TEXT,risk_accepted_at REAL)")
        # Deployments that predate risk acceptance get the columns added
        # rather than rebuilt. A grant with no acceptor is not silently
        # treated as accepted - it fails at exercise, which is the point.
        for ddl in ("ALTER TABLE auth_grant ADD COLUMN risk_accepted_by TEXT",
                    "ALTER TABLE auth_grant ADD COLUMN risk_accepted_at REAL"):
            try:
                c.execute(ddl)
            except Exception:
                pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_auth_parent ON auth_grant(parent)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_auth_subject ON auth_grant(subject)")
        c.execute("CREATE TABLE IF NOT EXISTS auth_revoke("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,grant_id TEXT,reason TEXT,"
                  "revoked REAL,api_key TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_auth_rev ON auth_revoke(grant_id)")
        c.execute("CREATE TABLE IF NOT EXISTS auth_eval("
                  "id TEXT PRIMARY KEY,grant_id TEXT,action TEXT,params_digest TEXT,"
                  "lineage_digest TEXT,verdict TEXT,reasons TEXT,broken_at TEXT,"
                  "broken_invariant TEXT,evaluated REAL,valid_until REAL,"
                  "audit_hash TEXT,block_index INTEGER,api_key TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_auth_eval_g ON auth_eval(grant_id)")
        c.execute("CREATE TABLE IF NOT EXISTS auth_meta(k TEXT PRIMARY KEY,v TEXT)")
        # The lineage as it stood at the instant of the decision. A proof that
        # re-read the grants later would describe today's authority, not the
        # authority the action was actually judged against.
        try:
            c.execute("ALTER TABLE auth_eval ADD COLUMN lineage_json TEXT")
        except Exception:
            pass
        c.execute("CREATE TABLE IF NOT EXISTS auth_exec("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,eval_id TEXT,outcome TEXT,"
                  "params_digest TEXT,confirmed REAL,audit_hash TEXT,block_index INTEGER)")
        # One accepted binding per evaluation, enforced by the database rather
        # than by a read followed by a write. Two concurrent executions of the
        # same ALLOW is a race, and a race is exactly where a check-then-act
        # guard loses.
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_exec_once "
                  "ON auth_exec(eval_id) WHERE outcome<>'rejected'")
        c.commit()
    _ready = True


def _iso(ts):
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _grant_digest(g):
    """Everything that makes the grant what it is. Parent is included, so a
    grant cannot be re-parented onto a wider ancestor after the fact."""
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
    return hashlib.sha256(GRANT_PREFIX + _canon(material).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# scope
# ----------------------------------------------------------------------

def _covers(held, wanted):
    """Does capability `held` cover capability `wanted`?

    Dot-separated segments. A trailing * covers any deeper path. A bare *
    covers everything, which is legal and always suspicious - see
    _wildcard_breadth.
    """
    if held == wanted:
        return True
    if held == "*":
        return True
    if held.endswith(".*"):
        return wanted == held[:-2] or wanted.startswith(held[:-1])
    return False


def _scope_subset(parent_scope, child_scope):
    missing = [c for c in child_scope if not any(_covers(p, c) for p in parent_scope)]
    if missing:
        return False, "scope not derivable from parent: " + ", ".join(sorted(missing)[:5])
    return True, None


def _wildcard_breadth(scope, capability):
    """How broad is the grant that lets this capability through?

    0  exact match
    1  wildcard one level above the requested capability
    2+ wildcard further up, or a bare *
    """
    best = None
    for held in scope:
        if not _covers(held, capability):
            continue
        if held == capability:
            return 0
        if held == "*":
            width = capability.count(".") + 2
        else:
            width = capability.count(".") - held[:-2].count(".")
        best = width if best is None else min(best, width)
    return best


# ----------------------------------------------------------------------
# constraints
# ----------------------------------------------------------------------

def _constraint_direction(key):
    for prefix in (NUMERIC_MAX, NUMERIC_MIN, ALLOWED, DENIED, FLAG):
        if key.startswith(prefix):
            return prefix
    return None


def _constraints_narrower(parent_c, child_c):
    """Child must be at least as tight as parent on every axis.

    A key the child introduces that the parent never expressed is an
    expansion of the constrained surface, not a tightening of it, and is
    refused. Silence upstream is not permission downstream.
    """
    for key, cval in sorted(child_c.items()):
        direction = _constraint_direction(key)
        if direction is None:
            return False, "constraint '%s' has no narrowing rule - refused rather than guessed" % key
        if key not in parent_c:
            return False, "constraint '%s' is not expressed by the parent, so a child cannot introduce it" % key
        pval = parent_c[key]
        try:
            if direction == NUMERIC_MAX:
                if _num(cval) > _num(pval):
                    return False, "%s raised from %s to %s" % (key, pval, cval)
            elif direction == NUMERIC_MIN:
                if _num(cval) < _num(pval):
                    return False, "%s lowered from %s to %s" % (key, pval, cval)
            elif direction == ALLOWED:
                if not _as_set(cval) <= _as_set(pval):
                    extra = sorted(str(x) for x in _as_set(cval) - _as_set(pval))
                    return False, "%s adds %s" % (key, ", ".join(extra[:5]))
            elif direction == DENIED:
                if not _as_set(pval) <= _as_set(cval):
                    dropped = sorted(str(x) for x in _as_set(pval) - _as_set(cval))
                    return False, "%s drops %s" % (key, ", ".join(dropped[:5]))
            elif direction == FLAG:
                if bool(cval) and not bool(pval):
                    return False, "%s enabled where the parent withholds it" % key
        except (TypeError, ValueError):
            return False, "constraint '%s' is not comparable with the parent's value" % key
    return True, None


def _effective_constraints(chain):
    """Tightest value on each axis across the whole lineage.

    Narrowing is enforced at issue and re-checked at exercise, so in a sound
    chain this equals the leaf. It is computed anyway: a grant issued before
    a rule was tightened must not be able to outlive the rule.
    """
    eff = {}
    for g in chain:
        for key, val in g["constraints"].items():
            direction = _constraint_direction(key)
            if key not in eff:
                eff[key] = val
                continue
            cur = eff[key]
            try:
                if direction == NUMERIC_MAX:
                    eff[key] = min(_num(cur), _num(val))
                elif direction == NUMERIC_MIN:
                    eff[key] = max(_num(cur), _num(val))
                elif direction == ALLOWED:
                    eff[key] = sorted(_as_set(cur) & _as_set(val))
                elif direction == DENIED:
                    eff[key] = sorted(_as_set(cur) | _as_set(val))
                elif direction == FLAG:
                    eff[key] = bool(cur) and bool(val)
            except (TypeError, ValueError):
                eff[key] = val
    return eff


def _params_against_constraints(params, eff):
    """Check the action's own parameters against the effective constraints.

    Returns (hard_failures, unconstrained_dimensions).
    """
    failures = []
    unconstrained = []
    for key, val in sorted(params.items()):
        checked = False
        for cname, cval in eff.items():
            direction = _constraint_direction(cname)
            axis = cname[len(direction):] if direction else cname
            if axis != key:
                continue
            checked = True
            try:
                if direction == NUMERIC_MAX and _num(val) > _num(cval):
                    failures.append("%s=%s exceeds %s=%s" % (key, val, cname, cval))
                elif direction == NUMERIC_MIN and _num(val) < _num(cval):
                    failures.append("%s=%s is below %s=%s" % (key, val, cname, cval))
                elif direction == ALLOWED and val not in _as_set(cval):
                    failures.append("%s=%s is outside %s" % (key, val, cname))
                elif direction == DENIED and val in _as_set(cval):
                    failures.append("%s=%s is denied by %s" % (key, val, cname))
                elif direction == FLAG and bool(val) and not bool(cval):
                    failures.append("%s requested where %s withholds it" % (key, cname))
            except (TypeError, ValueError):
                failures.append("%s cannot be compared with %s" % (key, cname))
        if not checked:
            unconstrained.append(key)
    return failures, unconstrained


# ----------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------

def _row_to_grant(row):
    return {
        "id": row[0], "parent": row[1], "root": row[2], "issuer": row[3],
        "issuer_kind": row[4], "subject": row[5], "subject_kind": row[6],
        "scope": json.loads(row[7]), "constraints": json.loads(row[8]),
        "purpose": row[9], "purpose_tags": json.loads(row[10]),
        "not_before": row[11], "not_after": row[12], "depth": row[13],
        "delegations_left": row[14], "created": row[15], "digest": row[16],
        "audit_hash": row[17], "block_index": row[18],
        "risk_accepted_by": row[19], "risk_accepted_at": row[20],
    }


_COLUMNS = ("id,parent,root,issuer,issuer_kind,subject,subject_kind,scope,constraints,"
            "purpose,purpose_tags,not_before,not_after,depth,delegations_left,created,"
            "digest,audit_hash,block_index,risk_accepted_by,risk_accepted_at")


def _get(ctx, grant_id):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT " + _COLUMNS + " FROM auth_grant WHERE id=?", (grant_id,)).fetchone()
    return _row_to_grant(row) if row else None


def _revocation(ctx, grant_id):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT revoked,reason,audit_hash,block_index FROM auth_revoke "
            "WHERE grant_id=? ORDER BY id ASC LIMIT 1", (grant_id,)).fetchone()
    if not row:
        return None
    return {"revoked_at": _iso(row[0]), "revoked_ts": row[0], "reason": row[1],
            "sealed_in_chain": row[2], "block_index": row[3]}


def _accountable(chain):
    """Who accepts the risk of this authority existing.

    Distinct from who granted it and who holds it. An issuer says "you may".
    A subject does the acting. Neither of those is a person putting their
    name to the risk of the capability being switched on at all, and that is
    the name an incident actually needs.

    Resolved by walking down from the root and taking the nearest grant that
    states one, so an acceptor set high up covers everything beneath it
    until someone explicitly takes it on further down.
    """
    accountable = None
    at = None
    for g in chain:
        if g.get("risk_accepted_by"):
            accountable = g["risk_accepted_by"]
            at = g.get("risk_accepted_at")
    return accountable, at


def _walk(ctx, grant_id):
    """Leaf to root. Returns (chain_root_first, error).

    Cycle and length guards are separate on purpose: a cycle is an attack,
    an over-long chain is a policy breach, and they should not be reported
    as the same thing.
    """
    chain = []
    seen = set()
    current = grant_id
    while current:
        if current in seen:
            return None, {"invariant": "authority_continuity",
                          "grant": current,
                          "detail": "parent cycle - the lineage does not terminate at a root"}
        seen.add(current)
        g = _get(ctx, current)
        if g is None:
            return None, {"invariant": "authority_continuity",
                          "grant": current,
                          "detail": "grant not found, so no authority can be derived through it"}
        chain.append(g)
        if len(chain) > MAX_WALK:
            return None, {"invariant": "authority_continuity",
                          "grant": current,
                          "detail": "lineage exceeds the walk limit of %d" % MAX_WALK}
        current = g["parent"]
    chain.reverse()
    return chain, None


# ----------------------------------------------------------------------
# issue
# ----------------------------------------------------------------------

def _issue(ctx, api_key, data):
    now = time.time()
    parent_id = data.get("parent")
    issuer = str(data.get("issuer", "")).strip()
    subject = str(data.get("subject", "")).strip()
    issuer_kind = str(data.get("issuer_kind", "")).strip().lower()
    subject_kind = str(data.get("subject_kind", "agent")).strip().lower()
    scope = data.get("scope") or []
    constraints = data.get("constraints") or {}
    purpose = str(data.get("purpose", "")).strip()
    purpose_tags = data.get("purpose_tags") or []

    if not issuer or not subject:
        return {"error": "issuer_and_subject_required"}, 400
    for ident in (issuer, subject):
        if not ID_RE.match(ident):
            return {"error": "bad_identifier", "value": ident}, 400
    if not isinstance(scope, list) or not scope or not all(isinstance(s, str) for s in scope):
        return {"error": "scope_required", "message": "a non-empty list of capability strings"}, 400
    bad = [s for s in scope if not CAP_RE.match(s)]
    if bad:
        return {"error": "bad_capability", "values": bad[:5],
                "message": "Capabilities are matched exactly. A value carrying whitespace or "
                           "characters outside the grammar would read as one capability and "
                           "match another, so it is refused rather than cleaned up."}, 400
    if not isinstance(constraints, dict):
        return {"error": "constraints_must_be_an_object"}, 400
    if not isinstance(purpose_tags, list):
        return {"error": "purpose_tags_must_be_a_list"}, 400
    if not purpose:
        return {"error": "purpose_required",
                "message": "Authority without a stated purpose cannot be checked for intent "
                           "drift later, so it is not accepted."}, 400

    not_before = float(data.get("not_before") or now)
    not_after = data.get("not_after")
    if not_after is None:
        return {"error": "not_after_required",
                "message": "Authority that never expires cannot be temporally checked. "
                           "Give it an end."}, 400
    not_after = float(not_after)
    if not_after <= not_before:
        return {"error": "empty_validity_window"}, 400

    delegations_left = int(data.get("delegations_left", 0))
    if delegations_left < 0:
        return {"error": "delegations_left_must_not_be_negative"}, 400

    risk_accepted_by = str(data.get("risk_accepted_by", "")).strip() or None
    if risk_accepted_by and not ID_RE.match(risk_accepted_by):
        return {"error": "bad_identifier", "value": risk_accepted_by}, 400

    parent = None
    if parent_id:
        parent = _get(ctx, parent_id)
        if parent is None:
            return {"error": "parent_not_found", "parent": parent_id}, 404

        integrity = _grant_digest(parent)
        if integrity != parent["digest"]:
            return {"error": "parent_integrity_failed", "parent": parent_id,
                    "message": "The stored parent does not match the digest sealed when it was "
                               "issued. Nothing may be derived from it."}, 409

        rev = _revocation(ctx, parent_id)
        if rev:
            return {"error": "parent_revoked", "parent": parent_id, "revocation": rev}, 409
        if parent["not_after"] <= now:
            return {"error": "parent_expired", "parent": parent_id,
                    "expired_at": _iso(parent["not_after"])}, 409
        if parent["delegations_left"] <= 0:
            return {"error": "delegation_not_permitted", "parent": parent_id,
                    "message": "The parent grant carries no remaining delegations."}, 409
        if parent["depth"] + 1 > MAX_DEPTH:
            return {"error": "max_depth_exceeded", "limit": MAX_DEPTH}, 409

        ok, why = _scope_subset(parent["scope"], scope)
        if not ok:
            return {"error": "boundary_integrity", "parent": parent_id, "message": why}, 409
        ok, why = _constraints_narrower(parent["constraints"], constraints)
        if not ok:
            return {"error": "boundary_integrity", "parent": parent_id, "message": why}, 409
        if not set(purpose_tags) <= set(parent["purpose_tags"]):
            extra = sorted(set(purpose_tags) - set(parent["purpose_tags"]))
            return {"error": "intent_continuity", "parent": parent_id,
                    "message": "purpose tags not carried by the parent: " + ", ".join(extra)}, 409
        if not_before < parent["not_before"] or not_after > parent["not_after"]:
            return {"error": "temporal_validity", "parent": parent_id,
                    "message": "the child window is not contained by the parent window",
                    "parent_window": [_iso(parent["not_before"]), _iso(parent["not_after"])]}, 409
        if delegations_left > parent["delegations_left"] - 1:
            return {"error": "boundary_integrity", "parent": parent_id,
                    "message": "a child cannot carry more onward delegations than the parent "
                               "had left, minus the one it just used"}, 409

        # Handing an agent the power to hand authority on again is the
        # moment a capability gets switched on, and it is the moment someone
        # has to put their name to it. Inheriting an acceptor from further
        # up would mean a person accepting a risk that did not exist when
        # they accepted it.
        if delegations_left > 0 and not risk_accepted_by:
            return {"error": "risk_acceptance_required",
                    "parent": parent_id,
                    "message": "This grant lets its holder delegate onward. Name who accepts "
                               "the risk of that, in risk_accepted_by. A grant that only "
                               "narrows and cannot delegate inherits the acceptor above it."}, 409

        depth = parent["depth"] + 1
        root = parent["root"]
    else:
        if issuer_kind != "human":
            return {"error": "identity_continuity",
                    "message": "A root grant must be issued by a human principal. A grant with "
                               "no parent and no human issuer is an orphan, not a root."}, 409
        if not risk_accepted_by:
            risk_accepted_by = issuer
        depth = 0
        root = None

    grant_id = str(data.get("id") or ("g_" + uuid.uuid4().hex[:20]))
    if not ID_RE.match(grant_id):
        return {"error": "bad_identifier", "value": grant_id}, 400
    if _get(ctx, grant_id) is not None:
        return {"error": "grant_exists", "id": grant_id}, 409
    if root is None:
        root = grant_id

    g = {"id": grant_id, "parent": parent_id, "root": root, "issuer": issuer,
         "issuer_kind": issuer_kind or ("human" if depth == 0 else "agent"),
         "subject": subject, "subject_kind": subject_kind,
         "scope": sorted(set(scope)), "constraints": constraints, "purpose": purpose,
         "purpose_tags": sorted(set(purpose_tags)), "not_before": not_before,
         "not_after": not_after, "depth": depth, "delegations_left": delegations_left,
         "created": now, "risk_accepted_by": risk_accepted_by,
         "risk_accepted_at": (now if risk_accepted_by else None)}
    digest = _grant_digest(g)

    ev = {"user_id": "cty:" + subject[:32], "action": "authority_granted", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "AUTHORITY_GRANTED", "score": 0, "continuity_version": VERSION,
           "grant": grant_id, "parent": parent_id, "root": root, "depth": depth,
           "issuer": issuer, "subject": subject, "digest": digest,
           "risk_accepted_by": risk_accepted_by,
           "detail": "grant=%s;parent=%s;depth=%d;risk_accepted_by=%s;digest=%s"
                     % (grant_id, parent_id, depth, risk_accepted_by or "inherited", digest)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO auth_grant(id,parent,root,issuer,issuer_kind,subject,subject_kind,"
            "scope,constraints,purpose,purpose_tags,not_before,not_after,depth,"
            "delegations_left,created,digest,audit_hash,block_index,api_key,"
            "risk_accepted_by,risk_accepted_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (grant_id, parent_id, root, issuer, g["issuer_kind"], subject, subject_kind,
             _canon(g["scope"]), _canon(constraints), purpose, _canon(g["purpose_tags"]),
             not_before, not_after, depth, delegations_left, now, digest,
             audit_hash, block_index, api_key, risk_accepted_by,
             g["risk_accepted_at"]))
        ctx["conn"].commit()

    return {"grant": grant_id, "parent": parent_id, "root": root, "depth": depth,
            "issuer": issuer, "subject": subject, "scope": g["scope"],
            "constraints": constraints, "purpose": purpose, "purpose_tags": g["purpose_tags"],
            "not_before": _iso(not_before), "not_after": _iso(not_after),
            "delegations_left": delegations_left, "digest": digest,
            "risk_accepted_by": risk_accepted_by,
            "risk_accepted_at": _iso(g["risk_accepted_at"]),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "note": "Sealed at issue. Any later edit to the stored grant changes its digest "
                    "and fails integrity, so this grant cannot be widened after the fact."}, 200


# ----------------------------------------------------------------------
# revoke
# ----------------------------------------------------------------------

def _revoke(ctx, api_key, data):
    grant_id = str(data.get("grant", "")).strip()
    reason = str(data.get("reason", "revoked")).strip()[:200]
    if not grant_id:
        return {"error": "grant_required"}, 400
    g = _get(ctx, grant_id)
    if g is None:
        return {"error": "grant_not_found", "grant": grant_id}, 404
    existing = _revocation(ctx, grant_id)
    if existing:
        return {"already_revoked": True, "grant": grant_id, "revocation": existing}, 200

    now = time.time()
    ev = {"user_id": "cty:" + g["subject"][:32], "action": "authority_revoked", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "AUTHORITY_REVOKED", "score": 0, "continuity_version": VERSION,
           "grant": grant_id, "reason": reason,
           "detail": "grant=%s;reason=%s" % (grant_id, reason)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO auth_revoke(grant_id,reason,revoked,api_key,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (grant_id, reason, now, api_key, audit_hash, block_index))
        ctx["conn"].commit()

    return {"grant": grant_id, "revoked_at": _iso(now), "reason": reason,
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "effect": "Transitive. Every grant derived from this one stops evaluating, without "
                      "each descendant having to be found and revoked separately.",
            "note": "Revocation does not rewrite history. Actions already evaluated and sealed "
                    "under this grant remain exactly as they were decided."}, 200


# ----------------------------------------------------------------------
# exercise
# ----------------------------------------------------------------------

def _evaluate(ctx, api_key, data, seal=True):
    now = time.time()
    grant_id = str(data.get("grant", "")).strip()
    action_raw = str(data.get("action", ""))
    action = action_raw.strip()
    params = data.get("params") or {}
    declared_purpose = data.get("purpose_tag")
    declared_purpose = str(declared_purpose).strip() if declared_purpose else None

    if not grant_id or not action:
        return {"error": "grant_and_action_required"}, 400
    if not isinstance(params, dict):
        return {"error": "params_must_be_an_object"}, 400
    malformed_action = (action_raw != action) or not CAP_RE.match(action)

    params_digest = hashlib.sha256(
        EVAL_PREFIX + _canon({"action": action, "params": params}).encode("utf-8")).hexdigest()

    hard = []          # any entry means BLOCK
    soft = []          # any entry means CHALLENGE
    broken_at = None
    broken_invariant = None
    lineage_view = []
    snapshot = []

    chain, walk_error = _walk(ctx, grant_id)

    if walk_error:
        hard.append(walk_error["detail"])
        broken_at = walk_error["grant"]
        broken_invariant = walk_error["invariant"]
        chain = []

    def fail(grant, invariant, detail):
        nonlocal broken_at, broken_invariant
        hard.append(detail)
        if broken_at is None:
            broken_at, broken_invariant = grant, invariant

    if chain:
        root = chain[0]
        if root["parent"] is not None:
            fail(root["id"], "authority_continuity",
                 "the lineage does not terminate at a parentless root")
        if root["issuer_kind"] != "human":
            fail(root["id"], "identity_continuity",
                 "the root grant was not issued by a human principal")

        previous = None
        for g in chain:
            snapshot.append({
                "id": g["id"], "parent": g["parent"], "issuer": g["issuer"],
                "issuer_kind": g["issuer_kind"], "subject": g["subject"],
                "subject_kind": g["subject_kind"], "scope": g["scope"],
                "constraints": g["constraints"], "purpose": g["purpose"],
                "purpose_tags": g["purpose_tags"], "not_before": g["not_before"],
                "not_after": g["not_after"], "depth": g["depth"],
                "delegations_left": g["delegations_left"], "created": g["created"],
                "risk_accepted_by": g.get("risk_accepted_by"),
                "digest": g["digest"], "block_index": g["block_index"],
                "audit_hash": g["audit_hash"],
                "revoked_at": (_revocation(ctx, g["id"]) or {}).get("revoked_ts"),
            })
            entry = {"grant": g["id"], "depth": g["depth"], "issuer": g["issuer"],
                     "issuer_kind": g["issuer_kind"], "subject": g["subject"],
                     "scope": g["scope"], "constraints": g["constraints"],
                     "purpose": g["purpose"], "purpose_tags": g["purpose_tags"],
                     "window": [_iso(g["not_before"]), _iso(g["not_after"])],
                     "risk_accepted_by": g.get("risk_accepted_by"),
                     "digest": g["digest"], "block_index": g["block_index"]}

            if _grant_digest(g) != g["digest"]:
                fail(g["id"], "evidence_continuity",
                     "grant %s does not match the digest sealed when it was issued" % g["id"])
                entry["integrity"] = "FAILED"
            else:
                entry["integrity"] = "ok"

            rev = _revocation(ctx, g["id"])
            if rev:
                fail(g["id"], "authority_continuity",
                     "grant %s was revoked at %s" % (g["id"], rev["revoked_at"]))
                entry["revoked"] = rev

            if now < g["not_before"]:
                fail(g["id"], "temporal_validity",
                     "grant %s is not valid until %s" % (g["id"], _iso(g["not_before"])))
            if now >= g["not_after"]:
                fail(g["id"], "temporal_validity",
                     "grant %s expired at %s" % (g["id"], _iso(g["not_after"])))

            if previous is not None:
                ok, why = _scope_subset(previous["scope"], g["scope"])
                if not ok:
                    fail(g["id"], "boundary_integrity", "%s: %s" % (g["id"], why))
                ok, why = _constraints_narrower(previous["constraints"], g["constraints"])
                if not ok:
                    fail(g["id"], "boundary_integrity", "%s: %s" % (g["id"], why))
                if not set(g["purpose_tags"]) <= set(previous["purpose_tags"]):
                    extra = sorted(set(g["purpose_tags"]) - set(previous["purpose_tags"]))
                    fail(g["id"], "intent_continuity",
                         "%s carries purpose tags its parent does not: %s"
                         % (g["id"], ", ".join(extra)))
                if g["not_before"] < previous["not_before"] or g["not_after"] > previous["not_after"]:
                    fail(g["id"], "temporal_validity",
                         "%s is valid outside its parent's window" % g["id"])
                if g["depth"] != previous["depth"] + 1:
                    fail(g["id"], "authority_continuity",
                         "%s records a depth inconsistent with its parent" % g["id"])

            lineage_view.append(entry)
            previous = g

        if len(chain) - 1 > MAX_DEPTH:
            fail(chain[-1]["id"], "boundary_integrity",
                 "delegation depth %d exceeds the ceiling of %d" % (len(chain) - 1, MAX_DEPTH))

        leaf = chain[-1]

        # --- who owns the risk -------------------------------------------
        accountable, accepted_at = _accountable(chain)
        if not accountable:
            fail(chain[0]["id"], "identity_continuity",
                 "no grant in this lineage names who accepts the risk of the authority "
                 "existing, so an incident has an actor but no accountable person")

        # --- the action itself -------------------------------------------
        if malformed_action:
            fail(leaf["id"], "boundary_integrity",
                 "the action as submitted is not a well-formed capability, so what would be "
                 "sealed is not what was sent")
        elif not any(_covers(cap, action) for cap in leaf["scope"]):
            fail(leaf["id"], "boundary_integrity",
                 "action '%s' is not within the scope of the grant exercised" % action)
        else:
            breadth = _wildcard_breadth(leaf["scope"], action)
            if breadth and breadth >= 2:
                soft.append("action '%s' is only covered by a wildcard %d levels broader than "
                            "the action itself" % (action, breadth))

        eff = _effective_constraints(chain)
        failures, unconstrained = _params_against_constraints(params, eff)
        for f in failures:
            fail(leaf["id"], "boundary_integrity", f)
        for u in unconstrained:
            soft.append("parameter '%s' is not constrained anywhere in the lineage" % u)

        if declared_purpose:
            if declared_purpose not in leaf["purpose_tags"]:
                soft.append("declared purpose '%s' is not carried by the grant, whose purpose is "
                            "'%s'" % (declared_purpose, leaf["purpose"]))
        else:
            soft.append("the action declares no purpose, so intent compatibility with '%s' "
                        "cannot be established either way" % leaf["purpose"])
    else:
        broken_invariant = broken_invariant or "authority_continuity"

    if hard:
        authority_verdict = "BLOCK"
    elif soft:
        authority_verdict = "CHALLENGE"
    else:
        authority_verdict = "ALLOW"

    # --- compose with the existing engine --------------------------------
    # Authority and risk answer different questions and neither overrides the
    # other. A perfectly derived authority does not make a fraudulent payment
    # safe, and a clean risk score does not confer authority nobody granted.
    # The composed verdict is the worst of the two, so either can stop an
    # action and neither can wave one through alone.
    risk_verdict, risk_detail = None, {"available": False, "reason": "not consulted"}
    if authority_verdict == "BLOCK":
        risk_detail = {"available": False,
                       "reason": "authority failed, so the action was never put to the engine"}
    else:
        # The engine's own signal names. Getting these wrong does not fail
        # loudly - the scorer raises, the risk opinion goes missing, and every
        # action drops to CHALLENGE. Defaults are neutral rather than
        # flattering: an unstated signal should not improve a score.
        engine_event = {
            "user_id": (chain[-1]["subject"] if chain else "unknown")[:64],
            "action": action,
            "amount": params.get("amount", 0),
            "country": params.get("country", "UK"),
            "device_id": params.get("device_id", "agent"),
            "trust": params.get("trust", 0.5),
            "v60": params.get("v60", 0),
            "v5m": params.get("v5m", 0),
            "v1h": params.get("v1h", 0),
            "anomaly": params.get("anomaly", 0),
            "device_risk": params.get("device_risk", 0),
            "country_shift": bool(params.get("country_shift", False)),
        }
        for field in ("amount", "trust", "v60", "v5m", "v1h", "anomaly", "device_risk"):
            try:
                engine_event[field] = _num(engine_event[field])
            except (TypeError, ValueError):
                engine_event[field] = 0
        risk_verdict, risk_detail = _risk_opinion(engine_event)
        if risk_verdict is None and authority_verdict == "ALLOW":
            # The engine is part of the decision. Without its answer the
            # decision is incomplete, and an incomplete decision is a
            # CHALLENGE rather than a convenient ALLOW.
            soft.append("the risk engine did not return a usable verdict (%s), so the action "
                        "is not fully evaluated" % risk_detail.get("reason"))
            authority_verdict = "CHALLENGE"

    verdict = authority_verdict
    if risk_verdict and RANK[risk_verdict] > RANK[verdict]:
        verdict = risk_verdict

    lineage_digest = hashlib.sha256(
        EVAL_PREFIX + _canon([e.get("digest") for e in lineage_view]).encode("utf-8")).hexdigest()

    horizon = min([g["not_after"] for g in chain] or [now])
    valid_until = min(now + DEFAULT_WINDOW, horizon) if verdict == "ALLOW" else None

    eval_id = "e_" + uuid.uuid4().hex[:20]
    reasons = hard if hard else soft
    out = {
        "evaluation": eval_id,
        "verdict": verdict,
        "authority_verdict": authority_verdict,
        "risk_verdict": risk_verdict,
        "risk_engine": risk_detail,
        "action": action,
        "grant": grant_id,
        "root": chain[0]["id"] if chain else None,
        "authorised_by": chain[0]["issuer"] if chain else None,
        "executed_by": chain[-1]["subject"] if chain else None,
        "risk_accepted_by": (_accountable(chain)[0] if chain else None),
        "risk_accepted_at": _iso(_accountable(chain)[1]) if chain else None,
        "delegation_depth": (len(chain) - 1) if chain else None,
        "lineage": lineage_view,
        "lineage_digest": lineage_digest,
        "params_digest": params_digest,
        "effective_constraints": _effective_constraints(chain) if chain else {},
        "reasons": reasons,
        "broken_at": broken_at,
        "broken_invariant": broken_invariant,
        "evaluated_at": _iso(now),
        "valid_until": _iso(valid_until) if valid_until else None,
        "composition": "The verdict is the worse of the authority verdict and the existing "
                       "engine's verdict. Authority answers whether the action could be "
                       "derived from a human grant; the engine answers whether it should "
                       "happen anyway. Neither can overrule the other.",
        "what_this_means": {
            "ALLOW": "Every invariant held and the engine agreed. The action is derivable "
                     "from a valid human grant.",
            "CHALLENGE": "Nothing is provably broken and nothing is provably fine. The "
                         "uncertainty is named rather than resolved by guessing.",
            "BLOCK": "At least one invariant failed, and the grant and invariant are named.",
        }[verdict],
    }

    if seal:
        ev = {"user_id": "cty:" + (chain[-1]["subject"][:32] if chain else "unknown"),
              "action": "authority_evaluated", "amount": 0, "country": "UK",
              "device_id": "lineage", "anomaly": 0,
              "device_risk": 1 if verdict == "BLOCK" else 0}
        res = {"decision": verdict, "score": 0, "continuity_version": VERSION,
               "authority_verdict": authority_verdict, "risk_verdict": risk_verdict,
               "evaluation": eval_id, "grant": grant_id, "action": action,
               "risk_accepted_by": (_accountable(chain)[0] if chain else None),
               "lineage_digest": lineage_digest, "params_digest": params_digest,
               "broken_at": broken_at, "broken_invariant": broken_invariant,
               "detail": "eval=%s;verdict=%s;authority=%s;risk=%s;grant=%s;action=%s;"
                         "lineage=%s;params=%s"
                         % (eval_id, verdict, authority_verdict, risk_verdict or "n/a",
                            grant_id, action, lineage_digest, params_digest)}
        audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO auth_eval(id,grant_id,action,params_digest,lineage_digest,"
                "verdict,reasons,broken_at,broken_invariant,evaluated,valid_until,"
                "audit_hash,block_index,api_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (eval_id, grant_id, action, params_digest, lineage_digest, verdict,
                 _canon(reasons), broken_at, broken_invariant, now, valid_until,
                 audit_hash, block_index, api_key))
            ctx["conn"].execute(
                "UPDATE auth_eval SET lineage_json=? WHERE id=?",
                (_canon({"lineage": snapshot, "action": action, "params": params,
                         "purpose_tag": declared_purpose,
                         "authority_verdict": authority_verdict,
                         "risk_verdict": risk_verdict}), eval_id))
            ctx["conn"].commit()
        out["sealed_in_chain"] = audit_hash
        out["block_index"] = block_index
        out["receipt_seq"] = seq
        out["note"] = ("Sealed whether it allowed or blocked. A refusal that leaves no record "
                       "is indistinguishable from never having been asked.")

    return out, 200


# ----------------------------------------------------------------------
# confirm - closing the gap between decision and execution
# ----------------------------------------------------------------------

def _confirm(ctx, api_key, data):
    """Bind an execution to the evaluation that permitted it.

    Without this, an ALLOW is a decision about a request that may never
    have been the request executed. The parameter digest is re-derived from
    what actually ran and compared, and the window is enforced, so an
    evaluation cannot be banked and spent later against different values.
    """
    eval_id = str(data.get("evaluation", "")).strip()
    outcome = str(data.get("outcome", "executed")).strip()[:60]
    action = str(data.get("action", "")).strip()
    params = data.get("params") or {}
    if not eval_id:
        return {"error": "evaluation_required"}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT grant_id,action,params_digest,verdict,valid_until,lineage_digest "
            "FROM auth_eval WHERE id=?", (eval_id,)).fetchone()
    if not row:
        return {"error": "evaluation_not_found", "evaluation": eval_id}, 404
    grant_id, eval_action, params_digest, verdict, valid_until, lineage_digest = row

    now = time.time()
    problems = []
    if verdict != "ALLOW":
        problems.append("the evaluation returned %s, which does not permit execution" % verdict)

    with ctx["lock"]:
        spent = ctx["conn"].execute(
            "SELECT confirmed FROM auth_exec WHERE eval_id=? AND outcome<>'rejected' "
            "ORDER BY id ASC LIMIT 1", (eval_id,)).fetchone()
    if spent:
        problems.append("this evaluation was already bound to an execution at %s. One decision "
                        "authorises one action; a second would be an unauthorised repeat wearing "
                        "the first one's evidence." % _iso(spent[0]))
    if valid_until and now > valid_until:
        problems.append("the evaluation expired at %s and must be re-run" % _iso(valid_until))

    actual = hashlib.sha256(EVAL_PREFIX + _canon(
        {"action": action or eval_action, "params": params}).encode("utf-8")).hexdigest()
    # Unconditional. An empty params object is a claim about what executed
    # just as much as a full one, and skipping the comparison when it is
    # empty is exactly the gap this function exists to close: an ALLOW banked
    # against one set of values and spent against another.
    if actual != params_digest:
        problems.append("the executed parameters do not match the parameters evaluated")

    # Claim the binding before sealing it. Sealing first would put an
    # EXECUTION_BOUND record in the chain for an execution that the database
    # then refuses, and a chain that disagrees with the system it describes is
    # worse than no chain.
    accepted = not problems
    row_id = None
    if accepted:
        try:
            with ctx["lock"]:
                cur = ctx["conn"].execute(
                    "INSERT INTO auth_exec(eval_id,outcome,params_digest,confirmed) "
                    "VALUES(?,?,?,?)", (eval_id, outcome, actual, now))
                row_id = cur.lastrowid
                ctx["conn"].commit()
        except sqlite3.IntegrityError:
            accepted = False
            problems.append("a concurrent request bound this evaluation first. The race was "
                            "settled by a unique index rather than by application logic, so "
                            "only one of them can ever have executed.")
    if not accepted:
        with ctx["lock"]:
            cur = ctx["conn"].execute(
                "INSERT INTO auth_exec(eval_id,outcome,params_digest,confirmed) "
                "VALUES(?,?,?,?)", (eval_id, "rejected", actual, now))
            row_id = cur.lastrowid
            ctx["conn"].commit()

    ev = {"user_id": "cty:exec", "action": "authority_execution", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0,
          "device_risk": 0 if accepted else 1}
    res = {"decision": "EXECUTION_BOUND" if accepted else "EXECUTION_REJECTED", "score": 0,
           "continuity_version": VERSION, "evaluation": eval_id, "grant": grant_id,
           "outcome": outcome if accepted else "rejected", "params_digest": actual,
           "lineage_digest": lineage_digest,
           "detail": "eval=%s;bound=%s;params=%s" % (eval_id, accepted, actual)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE auth_exec SET audit_hash=?,block_index=? WHERE id=?",
                            (audit_hash, block_index, row_id))
        ctx["conn"].commit()

    return {"evaluation": eval_id, "bound": accepted, "problems": problems,
            "grant": grant_id, "outcome": outcome if accepted else "rejected",
            "params_digest": actual, "expected_params_digest": params_digest,
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "note": "The rejection is sealed too. An execution that failed to bind is evidence, "
                    "not an absence of evidence."}, 200 if accepted else 409


# ----------------------------------------------------------------------
# read-only
# ----------------------------------------------------------------------

def _trace(ctx, data):
    grant_id = str(data.get("grant", "")).strip()
    if not grant_id:
        return {"error": "grant_required"}, 400
    chain, err = _walk(ctx, grant_id)
    if err:
        return {"error": "lineage_broken", "detail": err}, 409
    out = []
    for g in chain:
        rev = _revocation(ctx, g["id"])
        out.append({"grant": g["id"], "depth": g["depth"], "parent": g["parent"],
                    "issuer": g["issuer"], "issuer_kind": g["issuer_kind"],
                    "subject": g["subject"], "subject_kind": g["subject_kind"],
                    "scope": g["scope"], "constraints": g["constraints"],
                    "purpose": g["purpose"], "purpose_tags": g["purpose_tags"],
                    "window": [_iso(g["not_before"]), _iso(g["not_after"])],
                    "delegations_left": g["delegations_left"],
                    "risk_accepted_by": g.get("risk_accepted_by"),
                    "risk_accepted_at": _iso(g.get("risk_accepted_at")),
                    "integrity": "ok" if _grant_digest(g) == g["digest"] else "FAILED",
                    "revoked": rev, "digest": g["digest"],
                    "sealed_in_chain": g["audit_hash"], "block_index": g["block_index"]})
    accountable, accepted_at = _accountable(chain)
    return {"grant": grant_id, "root": chain[0]["id"], "depth": len(chain) - 1,
            "authorised_by": chain[0]["issuer"], "holder": chain[-1]["subject"],
            "risk_accepted_by": accountable, "risk_accepted_at": _iso(accepted_at),
            "lineage": out,
            "effective_constraints": _effective_constraints(chain),
            "note": "Root first. Every hop is a sealed record with its own block index, so the "
                    "path can be checked against the chain rather than against this answer."}, 200


def _decision(ctx, data):
    eval_id = str(data.get("evaluation", "")).strip()
    if not eval_id:
        return {"error": "evaluation_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id,grant_id,action,params_digest,lineage_digest,verdict,reasons,"
            "broken_at,broken_invariant,evaluated,valid_until,audit_hash,block_index "
            "FROM auth_eval WHERE id=?", (eval_id,)).fetchone()
    if not row:
        return {"error": "evaluation_not_found"}, 404
    return {"evaluation": row[0], "grant": row[1], "action": row[2],
            "params_digest": row[3], "lineage_digest": row[4], "verdict": row[5],
            "reasons": json.loads(row[6]) if row[6] else [], "broken_at": row[7],
            "broken_invariant": row[8], "evaluated_at": _iso(row[9]),
            "valid_until": _iso(row[10]), "sealed_in_chain": row[11],
            "block_index": row[12]}, 200


def _decisions(ctx, data):
    """Recent sealed authority decisions, readable without a key.

    The point of publishing this is not the list. It is that a stranger can
    pick any id off it and pull the full decision and the full lineage at
    /x/continuity/decision and /x/continuity/trace, on real traffic, without
    an account - including the ones that escalated rather than executed.

    Deliberately thin. Verdict, which invariant broke, and where it sits in
    the chain. No scopes, no subjects, no parameters: what is being made
    checkable is that authority was enforced, not what anybody was doing.
    """
    try:
        limit = max(1, min(int(data.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50

    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT id,verdict,broken_invariant,evaluated,block_index FROM auth_eval "
            "ORDER BY evaluated DESC LIMIT ?", (limit,)).fetchall()
        counts = ctx["conn"].execute(
            "SELECT verdict,COUNT(*) FROM auth_eval GROUP BY verdict").fetchall()

    tally = {v: n for v, n in counts}
    return {"count": len(rows),
            "decisions": [{"evaluation": r[0], "verdict": r[1],
                           "broken_invariant": r[2], "evaluated_at": _iso(r[3]),
                           "block_index": r[4],
                           "proof": "/x/continuity/proof?evaluation=" + str(r[0]),
                           "decision": "/x/continuity/decision?evaluation=" + str(r[0])}
                          for r in rows],
            "totals": {"allowed": tally.get("ALLOW", 0),
                       "challenged": tally.get("CHALLENGE", 0),
                       "blocked": tally.get("BLOCK", 0)},
            "open_any_of_them": "every entry above carries its own links. "
                                "/x/continuity/proof with no id returns the most recent, "
                                "so a stranger can start without knowing anything.",
            "latest_proof": "/x/continuity/proof",
            "why_the_blocks_are_here": "A refusal that leaves no public record is "
                                       "indistinguishable from never having been asked. Every "
                                       "verdict is listed, including ours going wrong.",
            "what_this_is_not": "This is not a demonstration run for visitors. These are real "
                                "evaluations from real traffic, and an empty list means no "
                                "authority has been exercised yet rather than that none failed."}, 200


def _proof(ctx, data):
    """A portable, signed proof of one authority decision.

    Everything a stranger needs to reach the same verdict without this system:
    the lineage exactly as it stood at the instant of the decision, the action
    and parameters it was judged against, the digests, the chain receipts, and
    a signature over the whole thing.

    The important case is the refusal. A BLOCK bundle carries the grant and
    the invariant that failed, and the failure is re-derivable from the same
    fields - so an agent can prove it was NOT authorised, which is a claim no
    dashboard can make and the one thing a counterparty actually needs when
    an action does not happen.

    Every field of the bundle except the signature itself is inside the
    signed material, which is what the bundle's own verify_with instruction
    tells a stranger to check. Anything added after signing would be a field
    a verifier following that instruction cannot account for.
    """
    eval_id = str(data.get("evaluation", "")).strip()

    # No id, or "latest": hand back the most recent decision that carries a
    # lineage snapshot. A proof route that demands an identifier a visitor has
    # no way to obtain is a link nobody can follow, which is the same as not
    # publishing it.
    if not eval_id or eval_id.lower() == "latest":
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT id FROM auth_eval WHERE lineage_json IS NOT NULL "
                "ORDER BY evaluated DESC LIMIT 1").fetchone()
        if not row:
            return {"error": "nothing_to_prove",
                    "message": "No authority has been exercised yet, so there is no decision "
                               "to export. That is an empty record rather than a failure - "
                               "and it is what an empty one honestly looks like.",
                    "list": "/x/continuity/decisions"}, 404
        eval_id = row[0]

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id,grant_id,action,params_digest,lineage_digest,verdict,reasons,"
            "broken_at,broken_invariant,evaluated,valid_until,audit_hash,block_index,"
            "lineage_json FROM auth_eval WHERE id=?", (eval_id,)).fetchone()
    if not row:
        return {"error": "evaluation_not_found", "evaluation": eval_id}, 404
    if not row[13]:
        return {"error": "no_lineage_snapshot", "evaluation": eval_id,
                "message": "This decision predates signed proofs. Only evaluations "
                           "made after the proof route was deployed carry the lineage "
                           "as it stood at the time, and reconstructing it now would "
                           "describe today's authority rather than the authority the "
                           "action was judged against."}, 409

    try:
        captured = json.loads(row[13])
    except Exception:
        return {"error": "unreadable_snapshot"}, 500

    seed, pk, source = _keys(ctx)

    body = {
        "bundle_version": BUNDLE_VERSION,
        "continuity_version": VERSION,
        "issued_by": {
            "algorithm": "Ed25519",
            "public_key": binascii.hexlify(pk).decode(),
            "public_key_at": "/x/continuity/pubkey",
        },
        "decision": {
            "evaluation": row[0],
            "grant_exercised": row[1],
            "action": row[2],
            "params_digest": row[3],
            "lineage_digest": row[4],
            "verdict": row[5],
            "authority_verdict": captured.get("authority_verdict"),
            "risk_verdict": captured.get("risk_verdict"),
            "reasons": json.loads(row[6]) if row[6] else [],
            "broken_at": row[7],
            "broken_invariant": row[8],
            "evaluated_at": _iso(row[9]),
            "evaluated_at_epoch": row[9],
        },
        "request": {
            "action": captured.get("action"),
            "params": captured.get("params"),
            "purpose_tag": captured.get("purpose_tag"),
        },
        "lineage": captured.get("lineage", []),
        "chain": {
            "audit_hash": row[11],
            "block_index": row[12],
            "inclusion": "/api/inclusion?hash=" + str(row[11]),
            "whole_chain": "/api/verify-chain",
            "external_anchor": "/api/anchor-status",
            "note": "The signature stands on its own. These make the decision "
                    "locatable in an externally anchored log as well, which is a "
                    "second and independent thing to check.",
        },
        "rules": {
            "derivation": "/x/continuity/spec",
            "grant_digest": "sha256('AILEASH-GRANT-v1:' || canonical JSON of the "
                            "grant's semantic fields, keys sorted, no whitespace)",
            "lineage_digest": "sha256('AILEASH-AUTHEVAL-v1:' || canonical JSON of the "
                              "ordered list of grant digests, root first)",
            "params_digest": "sha256('AILEASH-AUTHEVAL-v1:' || canonical JSON of "
                             "{action, params})",
            "signature": "Ed25519 over 'AILEASH-AUTHORITY-PROOF-v1:' || canonical "
                         "JSON of every field of this bundle except signature itself",
            "canonical_json": "keys sorted, separators (',',':'), UTF-8",
        },
        "what_this_proves": (
            "That this decision was reached against this exact authority path, on "
            "these exact parameters, at this time, by the holder of the named key. "
            "A verifier can re-derive the verdict from the lineage alone and "
            "disagree with it."
            if row[5] != "BLOCK" else
            "That authority for this action could NOT be derived, and exactly where "
            "it failed: grant " + str(row[7]) + ", invariant " + str(row[8]) + ". "
            "The failure is re-derivable from the fields in this bundle, so the "
            "refusal is provable rather than merely asserted."),
        "what_a_verifier_can_re_derive": (
            "The authority verdict, in full, from the lineage in this bundle. The "
            "risk verdict cannot be re-derived without the scoring engine and is "
            "reported here rather than proved; the composed verdict is the worse of "
            "the two, so an authority BLOCK stands whatever the engine said."),
        "what_this_does_not_prove": (
            "That the root grant should have been issued, or that the parameters "
            "describe something that really happened. It proves derivation, not "
            "merit and not truth."),
        "verify_with": ("Any Ed25519 implementation, or the standalone verifier "
                        "published alongside this system. Remove the signature "
                        "field, canonicalise what remains, prepend the prefix "
                        "above, and check."),
    }

    # Signed last, over everything above. verify_with is inside the material
    # because the instruction it carries says to remove only the signature -
    # a field added after signing would make that instruction false and every
    # published proof unverifiable by the method the proof itself states.
    sig = _ed_signature(BUNDLE_PREFIX + _canon(body).encode("utf-8"), seed, pk)
    body["signature"] = binascii.hexlify(sig).decode()
    return body, 200


def _pubkey(ctx):
    _seed, pk, source = _keys(ctx)
    return {"algorithm": "Ed25519",
            "public_key": binascii.hexlify(pk).decode(),
            "key_source": source,
            "signs": "authority proof bundles at /x/continuity/proof?evaluation=<id>",
            "note": "Signatures are byte-compatible with RFC 8032. Any standard "
                    "library will verify them; nothing of ours has to be trusted "
                    "or installed."}, 200


def _spec():
    return {
        "continuity_version": VERSION,
        "invariants": {
            "identity_continuity": "every grant names issuer and subject; a root must be issued "
                                   "by a human principal",
            "authority_continuity": "every non-root grant points at a parent, the walk terminates "
                                    "at a root, and no ancestor is revoked",
            "boundary_integrity": "scope is a subset of the parent's, constraints are at least as "
                                  "tight on every axis, onward delegations decrease",
            "intent_continuity": "purpose tags narrow; an action outside them is challenged, not "
                                 "assumed",
            "temporal_validity": "every ancestor is inside its window at the instant of "
                                 "evaluation, not at the instant of issue",
            "evidence_continuity": "every grant, revocation, evaluation and execution binding is "
                                   "sealed in the AILeash chain",
            "risk_acceptance": "every lineage names a person who accepts the risk of the "
                               "authority existing, separately from who granted it and who "
                               "holds it. A grant that lets its holder delegate onward must "
                               "name its own acceptor rather than inherit one, because that "
                               "risk did not exist when the acceptor above signed up to it",
        },
        "scope_grammar": "dot-separated capabilities. 'a.b.*' covers 'a.b' and anything beneath "
                         "it. '*' covers everything and always challenges.",
        "constraint_grammar": {
            "max_*": "child <= parent; action value must not exceed the tightest in the lineage",
            "min_*": "child >= parent",
            "allowed_*": "child set is a subset of the parent set",
            "denied_*": "child set is a superset of the parent set",
            "may_*": "child may be true only where the parent is true",
            "unknown": "a key matching no rule, or absent from the parent, is refused rather "
                       "than guessed at",
        },
        "verdicts": {
            "ALLOW": "no invariant failed and no uncertainty remained",
            "CHALLENGE": "no invariant failed but intent, breadth or an unconstrained dimension "
                         "left a question a machine should not answer alone",
            "BLOCK": "an invariant failed; the response names the grant and the invariant",
        },
        "no_union": "one action derives from one lineage. Grants are never combined, because two "
                    "narrow authorities that jointly exceed either is the oldest escalation there "
                    "is.",
        "digest": "sha256('AILEASH-GRANT-v1:' || canonical JSON of the grant's semantic fields, "
                  "keys sorted, no whitespace). Parent is inside the digest, so re-parenting is "
                  "detectable.",
        "proof_signature": "Ed25519 over 'AILEASH-AUTHORITY-PROOF-v1:' || canonical JSON of "
                           "every field of the proof bundle except signature. Only signature "
                           "is removed before checking; every other field the bundle carries "
                           "is inside the signed material.",
        "why_published": "An authority decision nobody can re-derive is an assertion. These rules "
                         "are sufficient to reimplement the evaluator and disagree with us.",
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
        if action == "trace":
            return _trace(ctx, data)
        if action == "decision":
            return _decision(ctx, data)
        if action == "decisions":
            return _decisions(ctx, data)
        if action == "proof":
            return _proof(ctx, data)
        if action == "pubkey":
            return _pubkey(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "issue":
            return _issue(ctx, api_key, data)
        if action == "revoke":
            return _revoke(ctx, api_key, data)
        if action == "exercise":
            return _evaluate(ctx, api_key, data)
        if action == "confirm":
            return _confirm(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "trace", "decision", "decisions", "proof", "pubkey"],
            "POST": ["issue", "revoke", "exercise", "confirm"]}, 404

```


## `modules/counterfactual.py`

397 lines, 16121 bytes

```python
"""
Counterfactual explanation - /x/counterfactual/<action>

WHAT THIS IS
------------
Every governance vendor claims explainability. What they nearly all mean is
attribution: a list of which factors pushed the score up. That answers "why
did this happen" and leaves the only question anyone actually cares about
untouched - "what would have had to be different?"

That second question is the one a person contesting a decision needs, the
one Article 22 recourse turns on, and the one an ML-based system genuinely
cannot answer. A neural model is not invertible: you can attribute, you can
approximate with a sampling method, you cannot state the exact boundary.

This engine is arithmetic with published weights. Arithmetic runs backwards.
So for any sealed decision, the exact minimum change in every single factor
that would have produced a different verdict can be computed, stated, and
sealed - and anyone can re-derive it independently.

THE SCORING FUNCTION, RUN BACKWARDS
-----------------------------------
    score = (1 - trust)              x 0.30
          + min(v60/20, 1)           x 0.15
          + min(v5m/50, 1)           x 0.10
          + min(v1h/200, 1)          x 0.10
          + min(ln(1+amt)/ln(10001), 1) x 0.15
          + device_risk              x 0.10
          + anomaly                  x 0.10
          + 0.10 if country_shift
          + 0.10 if unsafe_country

    ALLOW < 0.35 <= CHALLENGE < 0.70 <= BLOCK

Each term is monotonic and independently invertible, so the required delta
for any single factor is exact rather than estimated.

WHAT YOU GET BACK
-----------------
  - the margin: how far the score sat from the nearest boundary. A BLOCK at
    0.701 and a BLOCK at 0.94 are not the same decision, and treating them
    the same is a failure of explanation.
  - per factor: the exact value that factor would have needed, alone, to
    reach the next verdict down - or a statement that this factor alone
    could not have done it, however far it moved.
  - the cheapest single change, where one exists.
  - a recourse statement in plain English, suitable for handing to the
    person the decision was about.

THE UNCOMFORTABLE PART, STATED UP FRONT
---------------------------------------
Perfect explainability and resistance to gaming are in direct tension, and
almost nobody in this field says so.

Telling a legitimate subject "your 60-second velocity needed to be under 11"
also tells a fraudster exactly where the wall is. This is not a flaw that
better engineering removes - it is what explanation IS. Publishing weights
means the boundary is derivable by anyone who reads the whitepaper anyway;
this module makes explicit what was already implicit.

The mitigations are honest rather than complete: these routes require a key
and are rate limited; every counterfactual request is itself sealed, so a
pattern of boundary probing is visible in the chain afterwards; and the
trust signal is history-dependent, so knowing the boundary does not let you
arrive at it instantly.

Operators handing counterfactuals to end users should treat that as a
deliberate choice with a cost, not a free feature.

    POST /x/counterfactual/explain    signals + verdict -> full analysis
    GET  /x/counterfactual/decision?block=N   explain a sealed decision
    GET  /x/counterfactual/probing    who has been mapping the boundary
"""

import json, math, time
from datetime import datetime, timezone

VERSION = "1.0"

ALLOW_MAX = 0.35
CHALLENGE_MAX = 0.70
LN_CAP = math.log1p(10000)

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS cf_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,ts REAL,block_index INTEGER,verdict TEXT,score REAL,target TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cf_key ON cf_requests(api_key,ts)")
        ctx["conn"].commit()
    _ready = True


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _verdict(sc):
    if sc < ALLOW_MAX:
        return "ALLOW"
    if sc < CHALLENGE_MAX:
        return "CHALLENGE"
    return "BLOCK"


def _normalise(data):
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, _f(data, "v60")),
        "v5m": max(0.0, _f(data, "v5m")),
        "v1h": max(0.0, _f(data, "v1h")),
        "amount": max(0.0, _f(data, "amount")),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": bool(data.get("unsafe_country")),
    }


# ---- per-factor contribution and inversion -------------------------------

def _contribs(s):
    return {
        "trust": (1 - s["trust"]) * 0.30,
        "v60": min(s["v60"] / 20.0, 1) * 0.15,
        "v5m": min(s["v5m"] / 50.0, 1) * 0.10,
        "v1h": min(s["v1h"] / 200.0, 1) * 0.10,
        "amount": min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15,
        "device_risk": s["device_risk"] * 0.10,
        "anomaly": s["anomaly"] * 0.10,
        "country_shift": 0.10 if s["country_shift"] else 0.0,
        "unsafe_country": 0.10 if s["unsafe_country"] else 0.0,
    }


def _invert(factor, target_contrib, s):
    """Value this factor would need for the stated contribution.
    Returns (value, human_string) or None where impossible."""
    t = target_contrib
    if factor == "trust":
        v = 1 - (t / 0.30)
        if v > 1.0:
            return None
        return round(_clamp(v), 4), "trust of " + str(round(_clamp(v), 3)) + " or higher (was " + str(round(s["trust"], 3)) + ")"
    if factor in ("v60", "v5m", "v1h"):
        cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[factor]
        v = (t / w) * cap
        if v < 0:
            return None
        label = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[factor]
        return round(v, 2), label + " velocity of " + str(int(v)) + " or fewer (was " + str(int(s[factor])) + ")"
    if factor == "amount":
        v = math.expm1((t / 0.15) * LN_CAP)
        if v < 0:
            return None
        return round(v, 2), "amount of " + str(round(v, 2)) + " or less (was " + str(round(s["amount"], 2)) + ")"
    if factor in ("device_risk", "anomaly"):
        v = t / 0.10
        if v < 0:
            return None
        nice = "device risk" if factor == "device_risk" else "behavioural anomaly"
        return round(_clamp(v), 4), nice + " of " + str(round(_clamp(v), 3)) + " or lower (was " + str(round(s[factor], 3)) + ")"
    if factor in ("country_shift", "unsafe_country"):
        if t >= 0.10:
            return None
        nice = "no country change from the previous event" if factor == "country_shift" else "an event from a jurisdiction on the safe list"
        return 0, nice
    return None


def _analyse(s, want=None):
    score = _score(s)
    verdict = _verdict(score)
    contribs = _contribs(s)

    if verdict == "BLOCK":
        target_v, ceiling = "CHALLENGE", CHALLENGE_MAX
    elif verdict == "CHALLENGE":
        target_v, ceiling = "ALLOW", ALLOW_MAX
    else:
        return {"score": score, "verdict": verdict,
                "margin_to_next_boundary": round(ALLOW_MAX - score, 4),
                "note": "Already the most permissive verdict. Nothing needed to change it."}, contribs, None

    if want in ("ALLOW", "CHALLENGE"):
        target_v = want
        ceiling = ALLOW_MAX if want == "ALLOW" else CHALLENGE_MAX

    # need score strictly below ceiling
    needed = round(score - ceiling, 6)
    factors = []
    cheapest = None

    for name, c in sorted(contribs.items(), key=lambda kv: -kv[1]):
        entry = {"factor": name,
                 "contributed": round(c, 4),
                 "share_of_score_pct": (round(100 * c / score, 1) if score else 0)}
        if c <= 0:
            entry["alone_sufficient"] = False
            entry["reason"] = "contributed nothing to this score"
            factors.append(entry)
            continue
        # contribution required so total lands just under the ceiling
        target_contrib = c - needed - 0.0001
        if target_contrib < 0:
            entry["alone_sufficient"] = False
            entry["reason"] = ("even at zero this factor only removes "
                               + str(round(c, 4)) + " of the "
                               + str(round(needed, 4)) + " required")
        else:
            inv = _invert(name, target_contrib, s)
            if inv is None:
                entry["alone_sufficient"] = False
                entry["reason"] = "no attainable value of this factor reaches the threshold"
            else:
                val, human = inv
                entry["alone_sufficient"] = True
                entry["required_value"] = val
                entry["statement"] = human
                if cheapest is None:
                    cheapest = {"factor": name, "required_value": val, "statement": human}
        factors.append(entry)

    summary = {
        "score": score,
        "verdict": verdict,
        "target_verdict": target_v,
        "threshold": ceiling,
        "margin": round(score - ceiling, 4),
        "score_reduction_required": max(0.0, needed),
        "factors": factors,
    }
    if cheapest:
        summary["single_change_that_would_have_sufficed"] = cheapest
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". The threshold for " + target_v + " is " + str(ceiling) +
            ". The decision would have been " + target_v + " with " +
            cheapest["statement"] + ", all else unchanged.")
    else:
        summary["single_change_that_would_have_sufficed"] = None
        summary["recourse_statement"] = (
            "This decision was " + verdict + " with a score of " + str(score) +
            ". No single factor, changed alone, would have reached " + target_v +
            " - the score was driven by several factors together.")
    return summary, contribs, cheapest


def _log(ctx, api_key, block_index, verdict, score, target):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO cf_requests(api_key,ts,block_index,verdict,score,target) VALUES(?,?,?,?,?,?)",
                            (api_key, time.time(), block_index, verdict, score, target))
        ctx["conn"].commit()


def _seal(ctx, api_key, summary, block_index):
    ts = time.time()
    ev = {"user_id": "cf:" + str(block_index or "adhoc"), "action": "counterfactual",
          "amount": 0, "country": "UK", "device_id": "counterfactual",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "COUNTERFACTUAL_SEALED", "score": 0,
           "cf_version": VERSION, "timestamp": ts,
           "explained_verdict": summary.get("verdict"),
           "explained_score": summary.get("score"),
           "target_verdict": summary.get("target_verdict"),
           "detail": summary.get("recourse_statement")}
    return ctx["seal"](ev, res, ts, api_key)


def _explain(ctx, api_key, data):
    s = _normalise(data)
    want = str(data.get("target_verdict", "")).strip().upper() or None
    summary, _c, _ch = _analyse(s, want)
    h, idx, seq = _seal(ctx, api_key, summary, None)
    _log(ctx, api_key, None, summary.get("verdict"), summary.get("score"), want)
    summary["inputs_used"] = s
    summary["audit_hash"] = h
    summary["block_index"] = idx
    summary["receipt_seq"] = seq
    summary["reproduce"] = "Weights are published. Re-run the arithmetic yourself - this result is not an approximation."
    return summary, 200


def _decision(ctx, api_key, data):
    try:
        bid = int(data.get("block", 0))
    except (TypeError, ValueError):
        return {"error": "block_required", "message": "Pass ?block=<block_index> from a sealed decision."}, 400
    if bid <= 0:
        return {"error": "block_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT event_json,result_json,ts FROM audit_log WHERE id=? AND api_key=?", (bid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_block", "block": bid}, 404
    try:
        ev = json.loads(row[0])
        res = json.loads(row[1])
    except Exception:
        return {"error": "block_unreadable"}, 500
    if str(res.get("decision", "")).endswith("_SEALED"):
        return {"error": "not_a_decision",
                "message": "That block is a notary event, not an engine decision."}, 400

    sig = res.get("signals") or res.get("applied") or {}
    s = _normalise({
        "trust": sig.get("trust", res.get("trust", 0.5)),
        "v60": sig.get("v60", 0), "v5m": sig.get("v5m", 0), "v1h": sig.get("v1h", 0),
        "amount": ev.get("amount", 0),
        "device_risk": ev.get("device_risk", 0),
        "anomaly": ev.get("anomaly", 0),
        "country_shift": sig.get("country_shift", False),
        "unsafe_country": sig.get("unsafe_country", False),
    })
    summary, _c, _ch = _analyse(s)
    sealed_score = res.get("score")
    if sealed_score is not None and abs(float(sealed_score) - summary["score"]) > 0.0002:
        summary["reconstruction_warning"] = (
            "Recomputed score " + str(summary["score"]) + " does not match the sealed score "
            + str(sealed_score) + ". The sealed record does not carry every signal value, "
            "so this explanation is indicative rather than exact. Pass the signals directly "
            "to /explain for an exact result.")
    else:
        summary["reconstruction"] = "exact - recomputed score matches the sealed score"
    summary["explained_block"] = bid
    summary["sealed_at"] = _iso(row[2])
    h, idx, seq = _seal(ctx, api_key, summary, bid)
    _log(ctx, api_key, bid, summary.get("verdict"), summary.get("score"), None)
    summary["audit_hash"] = h
    summary["block_index"] = idx
    return summary, 200


def _probing(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT ts,verdict,score FROM cf_requests WHERE api_key=? AND ts>? ORDER BY ts DESC", (api_key, t - 86400)).fetchall()
    if not rows:
        return {"requests_24h": 0,
                "note": "No counterfactual requests in the last 24 hours."}, 200
    scores = [r[2] for r in rows if r[2] is not None]
    near = len([x for x in scores if abs(x - CHALLENGE_MAX) < 0.02 or abs(x - ALLOW_MAX) < 0.02])
    out = {"requests_24h": len(rows),
           "last_request": _iso(rows[0][0]),
           "near_boundary_requests": near,
           "note": "Every counterfactual request is sealed. Boundary probing leaves a trail whether or not anyone is watching at the time."}
    if len(rows) >= 50:
        out["flag"] = str(len(rows)) + " counterfactual requests in 24 hours - consistent with systematic boundary mapping"
    if near >= 10:
        out["boundary_flag"] = str(near) + " requests sat within 0.02 of a threshold"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "explain":
            return _explain(ctx, api_key, data)
    else:
        if action == "decision":
            return _decision(ctx, api_key, data)
        if action == "probing":
            return _probing(ctx, api_key)
    return {"error": "unknown_action", "action": action,
            "available": ["POST explain", "GET decision?block=", "GET probing"]}, 404

```
