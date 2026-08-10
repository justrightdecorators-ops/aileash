# Codebase — part 2 of 19

Contains:
- `modules/Continuity.py`
- `modules/_ _ i n i t _ _ . p y`
- `modules/capture.py`
- `modules/codebase.py`


## `modules/Continuity.py`

1347 lines, 64660 bytes

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

import hashlib
import json
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.2"

PUBLIC = {("GET", "trace"), ("GET", "decision"), ("GET", "decisions"), ("GET", "spec")}

GRANT_PREFIX = b"AILEASH-GRANT-v1:"
EVAL_PREFIX = b"AILEASH-AUTHEVAL-v1:"

# The live scorer is found at runtime rather than imported, the same way
# replay.py finds it. server.py is never imported by a module.
SCORER_NAMES = ["score_event", "score", "evaluate_event", "evaluate", "decide", "risk_score"]

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


def _read_verdict(result):
    """Pull a decision out of whatever shape the engine returns."""
    if isinstance(result, dict):
        for key in ("decision", "verdict", "action"):
            v = result.get(key)
            if isinstance(v, str) and v.upper() in RANK:
                return v.upper(), result
    if isinstance(result, (list, tuple)):
        for item in result:
            v, _ = _read_verdict(item)
            if v:
                return v, result if isinstance(result, dict) else {"raw": list(result)}
            if isinstance(item, str) and item.upper() in RANK:
                return item.upper(), {"raw": list(result)}
    if isinstance(result, str) and result.upper() in RANK:
        return result.upper(), {"raw": result}
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
    if isinstance(detail, dict) and "score" in detail:
        out["score"] = detail["score"]
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
    if action and params and actual != params_digest:
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
                           "block_index": r[4]} for r in rows],
            "totals": {"allowed": tally.get("ALLOW", 0),
                       "challenged": tally.get("CHALLENGE", 0),
                       "blocked": tally.get("BLOCK", 0)},
            "open_any_of_them": "/x/continuity/decision?evaluation=<id> for the decision, "
                                "/x/continuity/trace?grant=<grant> for the authority path",
            "why_the_blocks_are_here": "A refusal that leaves no public record is "
                                       "indistinguishable from never having been asked. Every "
                                       "verdict is listed, including ours going wrong.",
            "what_this_is_not": "This is not a demonstration run for visitors. These are real "
                                "evaluations from real traffic, and an empty list means no "
                                "authority has been exercised yet rather than that none failed."}, 200


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
            "GET": ["spec", "trace", "decision", "decisions"],
            "POST": ["issue", "revoke", "exercise", "confirm"]}, 404

```


## `modules/_ _ i n i t _ _ . p y`

2 lines, 37 bytes

```
# makes this folder a python package

```


## `modules/capture.py`

385 lines, 17851 bytes

```python
"""
One-button decision capture - /x/capture/<action>

WHAT IT IS
----------
A drop-in button for an operator's own review screen. A human reviews an AI
output, clicks once, and the decision is sealed into the chain with who
reviewed it, on what device, against which inputs, and how long they took.

WHY IT IS TWO CALLS AND NOT ONE
-------------------------------
The obvious version is a single POST carrying a dwell time measured in the
browser. That number is the whole point - it is what makes rubber stamping
visible - and a number the reviewed party computes for itself is not
evidence. Anyone can set it to whatever looks diligent.

So the widget opens a case first. The server records the open time. When the
reviewer commits, the server computes the dwell itself from two timestamps it
owns. The browser never supplies the figure it is being judged on.

Same reason the verdict is withheld between the two calls: the machine's
answer is sealed at open and only returned at seal, so the chain shows the
human committed before they saw it. Ordering is the one thing that separates
judgement from agreement.

KEYS IN BROWSERS
----------------
An API key pasted into page JavaScript is public. Anyone reading the source
can post as that operator, forever.

So capture accepts a CAPTURE TOKEN: minted server-side by the operator from
their real key, bound to one origin, short-lived, and able to do exactly two
things - open a case and seal it. It cannot read records, cannot see other
cases, cannot touch any other module. Same idea as a publishable key.

The real API key still works for server-to-server calls. It should never
appear in a page.

DEVICES ARE THE BILLING UNIT
----------------------------
Every capture carries a device_id, and distinct devices per calendar month is
what billing is counted on. The registry here is that count: first seen, last
seen, events, per month. An operator can query their own figure at any time
and reconcile it against an invoice, rather than being told a number.

Device identifiers are hashed on arrival. The chain and the registry hold a
fingerprint, never the raw identifier.

    POST /x/capture/token     mint a browser-safe capture token (real key only)
    POST /x/capture/open      start a case, server records the clock
    POST /x/capture/seal      commit a verdict, server computes the dwell
    GET  /x/capture/devices   this month's billable device count
    GET  /x/capture/case?id=  the sealed record of one capture
    GET  /x/capture/summary   dwell and divergence across recent captures
"""

import hashlib, hmac, json, os, re, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate", "approve", "reject"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN_TTL = 3600 * 12
MAX_OPEN_AGE = 3600 * 6

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_cases(case_id TEXT PRIMARY KEY,api_key TEXT,operator_fp TEXT,device_fp TEXT,input_hash TEXT,output_hash TEXT,machine_verdict TEXT,opened REAL,sealed REAL,human_verdict TEXT,dwell REAL,agreed INTEGER,note TEXT)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_devices(api_key TEXT,device_fp TEXT,month TEXT,first_seen REAL,last_seen REAL,events INTEGER DEFAULT 0,PRIMARY KEY(api_key,device_fp,month))")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_key ON capture_cases(api_key,opened)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_dev ON capture_devices(api_key,month)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("CAPTURE_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def _fp(v):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(v).strip().lower().encode(), hashlib.sha256).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _month(ts=None):
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m")


# ------------------------------------------------------------ capture token

def _mint(ctx, api_key, data):
    """Real key only. Returns a token safe to put in a page."""
    s = _secret()
    if not s:
        return {"error": "capture_secret_not_set",
                "message": "Set CAPTURE_SECRET in the environment first."}, 503
    origin = str(data.get("origin", "")).strip().lower()[:120]
    if not origin:
        return {"error": "origin_required",
                "message": "Bind the token to the site that will use it, e.g. https://app.yourcompany.com"}, 400
    try:
        ttl = min(int(data.get("ttl_seconds", TOKEN_TTL)), TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = TOKEN_TTL
    exp = int(time.time()) + max(60, ttl)
    body = api_key + "|" + origin + "|" + str(exp)
    sig = hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32]
    token = "cap_" + str(exp) + "_" + hashlib.sha256(origin.encode()).hexdigest()[:8] + "_" + sig
    return {"capture_token": token, "origin": origin,
            "expires": _iso(exp), "expires_in_seconds": exp - int(time.time()),
            "scope": ["capture:open", "capture:seal"],
            "note": "Safe to place in a page. It cannot read records, cannot see other cases, and cannot reach any other module. Mint a fresh one from your server as needed - never put your real API key in a browser."}, 200


def _verify_token(ctx, token, origin):
    """Returns the owning api_key, or None."""
    s = _secret()
    if not s or not token or not token.startswith("cap_"):
        return None
    parts = token.split("_")
    if len(parts) != 4:
        return None
    try:
        exp = int(parts[1])
    except ValueError:
        return None
    if exp < time.time():
        return None
    ohash, sig = parts[2], parts[3]
    if origin:
        o = str(origin).strip().lower()[:120]
        if hashlib.sha256(o.encode()).hexdigest()[:8] != ohash:
            return None
    else:
        o = None
    with ctx["lock"]:
        keys = ctx["conn"].execute("SELECT key FROM api_keys WHERE active=1").fetchall()
    for (k,) in keys:
        if o is None:
            continue
        body = k + "|" + o + "|" + str(exp)
        if hmac.compare_digest(hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32], sig):
            return k
    return None


def _resolve(ctx, api_key, data):
    """A real key wins; otherwise try a capture token bound to an origin."""
    if api_key:
        return api_key, "api_key"
    tok = str(data.get("capture_token", "")).strip()
    origin = str(data.get("origin", "")).strip()
    owner = _verify_token(ctx, tok, origin)
    if owner:
        return owner, "capture_token"
    return None, None


# ------------------------------------------------------------------ devices

def _touch_device(ctx, api_key, device_fp, ts):
    m = _month(ts)
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT events FROM capture_devices WHERE api_key=? AND device_fp=? AND month=?", (api_key, device_fp, m)).fetchone()
        if row:
            ctx["conn"].execute("UPDATE capture_devices SET last_seen=?,events=events+1 WHERE api_key=? AND device_fp=? AND month=?", (ts, api_key, device_fp, m))
            new = False
        else:
            ctx["conn"].execute("INSERT INTO capture_devices(api_key,device_fp,month,first_seen,last_seen,events) VALUES(?,?,?,?,?,1)", (api_key, device_fp, m, ts, ts))
            new = True
        ctx["conn"].commit()
    return new


def _devices(ctx, api_key, data):
    m = str(data.get("month", "")).strip() or _month()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT COUNT(*),SUM(events) FROM capture_devices WHERE api_key=? AND month=?", (api_key, m)).fetchone()
        months = ctx["conn"].execute("SELECT month,COUNT(*) FROM capture_devices WHERE api_key=? GROUP BY month ORDER BY month DESC LIMIT 12", (api_key,)).fetchall()
    n = rows[0] or 0
    return {"month": m, "billable_devices": n, "captures": rows[1] or 0,
            "rate_per_device": 0.50, "currency": "GBP",
            "estimated_charge": round(n * 0.50, 2),
            "history": [{"month": a, "devices": b} for a, b in months],
            "note": "A device counts once per calendar month however many captures it makes. Distinct devices is the billing unit - this is the same figure the invoice uses, so you can reconcile it yourself rather than being told a number."}, 200


# -------------------------------------------------------------------- cases

def _open(ctx, api_key, data):
    if not _secret():
        return {"error": "capture_secret_not_set"}, 503
    operator = str(data.get("operator_id", "")).strip()
    if not operator:
        return {"error": "operator_id_required",
                "message": "A capture with no named reviewer is not oversight."}, 400
    device = str(data.get("device_id", "")).strip()
    if not device:
        return {"error": "device_id_required",
                "message": "Devices are the billing unit and the record needs to say which one acted."}, 400

    ih = str(data.get("input_hash", "")).strip().lower()
    oh = str(data.get("output_hash", "")).strip().lower()
    for name, v in (("input_hash", ih), ("output_hash", oh)):
        if v and not HEX64.match(v):
            return {"error": "invalid_" + name,
                    "message": "Hash the content locally and send 64 hex characters. Never send the content itself."}, 400

    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    ts = time.time()
    ofp, dfp = _fp(operator), _fp(device)
    cid = "CAP-" + secrets.token_hex(5).upper()
    new_device = _touch_device(ctx, api_key, dfp, ts)

    detail = ("operator=" + (ofp or "")[:32] + ";device=" + (dfp or "")[:32] +
              ";input=" + (ih or "none") + ";output=" + (oh or "none") +
              ";machine_verdict_sealed=" + (mv or "none"))
    ev = {"user_id": "cap:" + cid, "action": "capture_opened", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "opened",
           "capture_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "no personal data and no content in this block - fingerprints and hashes only"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO capture_cases(case_id,api_key,operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed,note) VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                            (cid, api_key, ofp, dfp, ih or None, oh or None, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until seal",
            "new_device_this_month": new_device,
            "next": "POST the reviewer's verdict to /x/capture/seal with this case_id",
            "note": "The clock started here, on the server. The dwell time is not something the browser gets to report."}, 200


def _seal(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,machine_verdict,opened,sealed FROM capture_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_sealed",
                "message": "A capture commits once."}, 400

    hv = str(data.get("verdict", "")).strip().lower()
    if hv not in VERDICTS:
        return {"error": "invalid_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()

    ts = time.time()
    dwell = round(ts - row[3], 3)
    if dwell > MAX_OPEN_AGE:
        return {"error": "case_expired",
                "opened": _iso(row[3]),
                "message": "This case was opened more than six hours ago. Open a fresh one rather than sealing a stale clock."}, 400
    agreed = None if not row[2] else (1 if hv == row[2] else 0)

    detail = ("verdict=" + hv + ";dwell_seconds=" + str(dwell) +
              ";server_measured=true;reasoning=" + reasoning[:600])
    ev = {"user_id": "cap:" + cid, "action": "capture_sealed", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "sealed",
           "capture_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE capture_cases SET sealed=?,human_verdict=?,dwell=?,agreed=? WHERE case_id=? AND api_key=?",
                            (ts, hv, dwell, agreed, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "verdict": hv, "dwell_seconds": dwell,
           "machine_verdict": row[2], "sealed": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "measured_by": "server",
           "note": "Your verdict was sealed before this response revealed ours. The chain fixes that order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "sealed " + str(dwell) + "s after the case opened - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed FROM capture_cases WHERE case_id=? AND api_key=?", (cid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("cap:" + cid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("capture_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    return {"case_id": cid.upper(),
            "operator_fingerprint": (row[0] or "")[:16] + "...",
            "device_fingerprint": (row[1] or "")[:16] + "...",
            "input_hash": row[2], "output_hash": row[3],
            "machine_verdict": row[4], "opened": _iso(row[5]),
            "sealed": _iso(row[6]), "human_verdict": row[7],
            "dwell_seconds": row[8],
            "agreed": (None if row[9] is None else bool(row[9])),
            "events": events,
            "ordering_proof": "The opened block precedes the sealed block in the chain, and both timestamps are the server's."}, 200


def _summary(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM capture_cases WHERE api_key=? AND sealed IS NOT NULL", (api_key,)).fetchall()
        openc = ctx["conn"].execute("SELECT COUNT(*) FROM capture_cases WHERE api_key=? AND sealed IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"captures": 0, "open_cases": openc,
                "note": "No sealed captures yet."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    under2 = len([d for d in dwells if d < 2])
    out = {"captures": len(rows), "open_cases": openc,
           "median_dwell_seconds": (dwells[n // 2] if n else None),
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " captures"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "token":
            if not api_key:
                return {"error": "api_key_required",
                        "message": "Mint capture tokens from your server using your real key."}, 401
            return _mint(ctx, api_key, data)
        owner, how = _resolve(ctx, api_key, data)
        if not owner:
            return {"error": "invalid_credentials",
                    "message": "Send a real API key server-side, or a valid capture_token with the origin it was bound to."}, 401
        if action == "open":
            return _open(ctx, owner, data)
        if action == "seal":
            return _seal(ctx, owner, data)
    else:
        if not api_key:
            return {"error": "api_key_required",
                    "message": "Reading capture records needs the real key, not a capture token."}, 401
        if action == "devices":
            return _devices(ctx, api_key, data)
        if action == "summary":
            return _summary(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/codebase.py`

489 lines, 21403 bytes

```python
#!/usr/bin/env python3
"""
modules/codebase.py  -  dated evidence of what you held, and when
=================================================================

WHAT THIS IS, STATED HONESTLY FIRST
-----------------------------------
This does not prove ownership. Nothing cryptographic can. Ownership of
software is a legal fact established by authorship, company records and
signed assignment - not by a hash.

What it does produce is the evidence that decides most disputes about
software in practice: a dated, tamper-evident, externally anchored record
that a specific person held a specific body of code, in a specific form, at
a specific moment. When two parties later disagree about who had what
first, that is the question a court, a mediator or an investor actually
asks - and it is normally answered with commit dates, which are settable
fields that prove nothing.

This answers it with arithmetic instead.

WHAT IT DOES
------------
    POST /x/codebase/seal

Walks the deployed source tree, hashes every file, builds one manifest root
over all of them, and seals that root - together with a declaration of
authorship you supply - into the chain. From there it is anchored
externally and handed to peer chains like every other block.

Run it again next week and you get a second dated point. Run it on every
deploy and you accumulate a continuous, uneditable record of the codebase
evolving under your hand, which is a far stronger thing than a single
snapshot: a body of work with a history is much harder to dispute than a
file that appeared once.

WHAT THE MANIFEST CONTAINS - AND WHAT IT DOES NOT
-------------------------------------------------
For each file: its path and the SHA-256 of its exact bytes. Nothing else.
No contents leave the server, ever, by any route here. The hashes are
one-way, so the manifest reveals nothing about what the code does; it only
lets you demonstrate later that a file you hold now is byte-identical to
the file you held then.

The manifest route is deliberately KEYED rather than public. Only the root,
the file count and the total byte size are public. A public file listing
would hand an attacker a map of the deployment for no gain - the root is
all a third party needs in order to check a manifest you show them.

Excluded by default and never hashed: version control internals, caches,
databases, and anything that looks like a secret. Sealing a hash of your
own credentials file would be a poor way to protect them.

HOW YOU USE IT IN A DISPUTE
---------------------------
  1. You produce the sealed root, its block index, and the chain's
     external anchor.
  2. You produce your copy of the code.
  3. Anyone recomputes the manifest from your copy - the rules are
     published at /x/codebase/spec - and compares.

If it matches, you demonstrably held exactly that code no later than the
sealing time, and the record of it has not been altered since, because it
is a block in an anchored chain that peers also hold.

WHAT STILL HAS TO HAPPEN OUTSIDE THIS FILE
------------------------------------------
Stated plainly, because a module that let you believe it had settled your
legal position would be doing you harm:

  - Copyright arises on authorship. Sealing evidences it; it does not
    create or register it.
  - If a company operates the platform, the IP needs to sit with the right
    entity in writing, or the position is muddier than it looks.
  - Where two parties have collaborated, the only reliable answer is an
    agreement saying who owns what, signed before it matters rather than
    after.

This module makes the factual record unarguable. The legal position is a
separate job and needs a solicitor, not a hash.

    POST /x/codebase/seal      hash the tree, seal the root      (keyed)
    GET  /x/codebase/manifest  the full file list for a seal     (keyed)
    GET  /x/codebase/history   every seal, with root changes     (public)
    GET  /x/codebase/root      the latest sealed root            (public)
    GET  /x/codebase/spec      how to recompute it yourself      (public)
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Roots and history are public - a dated claim nobody can check is not
# evidence. The file listing is keyed, because it is a map of the
# deployment and a third party never needs it to verify a manifest.
PUBLIC = {("GET", "history"), ("GET", "root"), ("GET", "spec")}

FILE_PREFIX = b"AILEASH-FILE-v1:"
MANIFEST_PREFIX = b"AILEASH-MANIFEST-v1:"

MAX_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

# Never walked into.
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
             "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
             "dist", "build", ".cache", "backups"}

# Never hashed. Secrets and databases are excluded on purpose - a hash of
# your credentials file is not evidence of anything you want to prove.
SKIP_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal",
                 ".db-shm", ".pyc", ".pyo", ".log", ".ots", ".pem", ".key",
                 ".crt", ".p12", ".pfx")
SKIP_NAMES = {".env", ".env.local", ".env.production", "secrets.json",
              "credentials.json", ".netrc", "id_rsa", ".DS_Store"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS codebase_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "manifest_root TEXT,file_count INTEGER,total_bytes INTEGER,"
                  "declaration TEXT,manifest TEXT,sealed REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cb_root ON codebase_seal(manifest_root)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _app_root():
    """The directory the application is deployed from.

    This module lives in modules/, so the parent of that directory is the
    tree we want. Resolved rather than assumed, so it is correct whatever
    the working directory happens to be when the server starts.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    return parent if parent else here


def _skip(name):
    if name in SKIP_NAMES:
        return True
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in SKIP_SUFFIXES)


def _file_hash(path):
    """SHA-256 of the exact bytes, read in chunks so a large file cannot
    exhaust memory."""
    digest = hashlib.sha256()
    digest.update(FILE_PREFIX)
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                return None, size
            digest.update(chunk)
    return digest.hexdigest(), size


def _walk(root):
    """Every file under root, sorted by relative path.

    Sorting matters: the manifest must be reproducible by anyone holding
    the same files, and directory order is not stable across systems.
    """
    entries, skipped, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if _skip(filename):
                skipped.append(os.path.relpath(os.path.join(dirpath, filename), root))
                continue
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                digest, size = _file_hash(full)
            except OSError:
                skipped.append(relative)
                continue
            if digest is None:
                skipped.append(relative)
                continue
            entries.append({"path": relative, "sha256": digest, "bytes": size})
            total += size
            if len(entries) >= MAX_FILES:
                return entries, skipped, total, True
    return entries, skipped, total, False


def _manifest_root(entries):
    """One root over the whole tree.

    Deliberately a flat, ordered digest rather than a Merkle tree: there is
    no need for per-file proofs here, and a rule anyone can reimplement in
    four lines is worth more than a clever structure nobody checks.
    """
    digest = hashlib.sha256()
    digest.update(MANIFEST_PREFIX)
    for entry in entries:
        digest.update(("%s\0%s\n" % (entry["path"], entry["sha256"])).encode("utf-8"))
    return digest.hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _seal(ctx, api_key, data):
    author = str(data.get("author", "") or "").strip()[:120]
    entity = str(data.get("entity", "") or "").strip()[:120]
    statement = str(data.get("statement", "") or "").strip()[:1000]

    if not author:
        return {"error": "author_required",
                "message": "The name of the person declaring authorship. This is sealed "
                           "verbatim and becomes part of the permanent record."}, 400

    root_path = _app_root()
    started = time.time()
    entries, skipped, total_bytes, truncated = _walk(root_path)
    if not entries:
        return {"error": "nothing_to_seal",
                "message": "No files found to hash under the application root."}, 500

    manifest_root = _manifest_root(entries)
    now = time.time()

    declaration = {
        "author": author,
        "entity": entity or None,
        "statement": statement or None,
        "declared_at": _iso(now),
    }

    ev = {"user_id": "cb:" + manifest_root[:16], "action": "codebase_sealed", "amount": 0,
          "country": "UK", "device_id": "codebase", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CODEBASE_SEALED", "score": 0, "codebase_version": VERSION,
           "manifest_root": manifest_root, "file_count": len(entries),
           "total_bytes": total_bytes, "author": author, "entity": entity or None,
           "statement": statement or None,
           "detail": "root=%s;files=%d;bytes=%d;author=%s"
                     % (manifest_root, len(entries), total_bytes, author)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT manifest_root,sealed FROM codebase_seal ORDER BY id ASC").fetchall()
        ctx["conn"].execute(
            "INSERT INTO codebase_seal(api_key,manifest_root,file_count,total_bytes,"
            "declaration,manifest,sealed,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, manifest_root, len(entries), total_bytes,
             json.dumps(declaration), json.dumps(entries), now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "manifest_root": manifest_root,
        "file_count": len(entries), "total_bytes": total_bytes,
        "files_skipped": len(skipped),
        "sealed_at": _iso(now),
        "took_seconds": round(now - started, 2),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "declaration": declaration,
        "seal_number": len(prior) + 1,
        "codebase_version": VERSION,
        "what_this_establishes": ("That the person named above held a body of code producing "
                                  "exactly this manifest root, no later than this moment, and "
                                  "that the record cannot be altered afterwards - it is a block "
                                  "in a chain that is externally anchored and held by peers."),
        "what_it_does_not": ("It does not establish legal ownership. Ownership comes from "
                             "authorship, company records and signed assignment. This is the "
                             "dated factual record those arguments rest on, not a substitute "
                             "for them."),
        "how_to_use_it": ("Keep this response. To demonstrate the claim later, produce your copy "
                          "of the code and let anyone recompute the manifest root from it using "
                          "the published rules. If it matches, you held exactly that code by "
                          "this date."),
        "verify_the_block": "/x/consistency/ancestor?tip=" + audit_hash,
        "spec": "/x/codebase/spec",
    }

    if truncated:
        out["truncated"] = ("Hit the %d file cap. The root covers the files listed and no more - "
                            "raise MAX_FILES if the tree is genuinely larger." % MAX_FILES)
    if prior:
        last_root, last_time = prior[-1]
        if last_root == manifest_root:
            out["unchanged_since"] = _iso(last_time)
            out["message"] = ("Identical to the previous seal. The codebase has not changed "
                              "since %s and now carries an additional dated witness."
                              % _iso(last_time))
        else:
            out["previous_root"] = last_root
            out["previous_sealed_at"] = _iso(last_time)
            out["message"] = ("The codebase has changed since the last seal. Both roots remain "
                              "in the chain - a dated history of the work, which is stronger "
                              "evidence than any single snapshot.")
    else:
        out["message"] = ("First seal. Run this on every deploy and the history becomes a "
                          "continuous record of the work developing under one hand.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _manifest(ctx, data):
    root = str(data.get("root", data.get("manifest_root", ""))).strip().lower()
    with ctx["lock"]:
        if root:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal WHERE manifest_root=? LIMIT 1",
                (root,)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "not_found", "root": root or None}, 404

    try:
        files = json.loads(row[4])
    except Exception:
        files = []
    try:
        declaration = json.loads(row[3])
    except Exception:
        declaration = None

    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "declaration": declaration, "sealed_at": _iso(row[5]),
            "sealed_in_chain": row[6], "block_index": row[7],
            "files": files,
            "codebase_version": VERSION,
            "note": "Paths and hashes only. No file contents are held or returned by any route "
                    "in this module."}, 200


def _history(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,declaration,sealed,audit_hash,"
            "block_index FROM codebase_seal ORDER BY id ASC LIMIT 500").fetchall()
    if not rows:
        return {"count": 0, "seals": [],
                "message": "No codebase seal recorded yet."}, 200

    seals, last = [], None
    for root, count, total, declaration, sealed, audit_hash, block_index in rows:
        try:
            parsed = json.loads(declaration)
            author = parsed.get("author")
        except Exception:
            author = None
        seals.append({"manifest_root": root, "file_count": count, "total_bytes": total,
                      "author": author, "sealed_at": _iso(sealed),
                      "sealed_in_chain": audit_hash, "block_index": block_index,
                      "changed_from_previous": last is not None and root != last})
        last = root

    authors = {s["author"] for s in seals if s["author"]}
    return {"count": len(seals),
            "first_sealed": seals[0]["sealed_at"], "latest_sealed": seals[-1]["sealed_at"],
            "distinct_roots": len({s["manifest_root"] for s in seals}),
            "declared_authors": sorted(authors),
            "seals": seals,
            "codebase_version": VERSION,
            "what_this_is": "A dated, uneditable record of one body of code developing over "
                            "time under a declared author. A continuous history is materially "
                            "harder to dispute than a single snapshot.",
            "file_list": "Keyed - /x/codebase/manifest. The root is all anyone needs to check a "
                         "manifest you show them."}, 200


def _root(ctx):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,sealed,audit_hash,block_index,"
            "declaration FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "never_sealed"}, 404
    try:
        author = json.loads(row[6]).get("author")
    except Exception:
        author = None
    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "sealed_at": _iso(row[3]), "sealed_in_chain": row[4], "block_index": row[5],
            "declared_author": author,
            "codebase_version": VERSION,
            "verify_the_block": "/x/consistency/ancestor?tip=" + row[4],
            "recompute_it": "/x/codebase/spec"}, 200


def _spec():
    return {
        "codebase_version": VERSION,
        "purpose": "Dated, tamper-evident evidence that a named person held a specific body of "
                   "code at a specific moment.",
        "not_ownership": "This does not establish legal ownership and is not offered as though "
                         "it does. Ownership comes from authorship, company records and signed "
                         "assignment. This is the factual record those arguments rest on.",
        "file_hash": "sha256('AILEASH-FILE-v1:' || exact_file_bytes) as lowercase hex",
        "manifest_root": "sha256('AILEASH-MANIFEST-v1:' || for each file in path order: "
                         "path + NUL + file_hash + newline) as lowercase hex",
        "ordering": "files sorted by relative path, forward slashes, relative to the "
                    "application root",
        "excluded": {
            "directories": sorted(SKIP_DIRS),
            "suffixes": list(SKIP_SUFFIXES),
            "names": sorted(SKIP_NAMES),
            "why": "Version control internals and caches are not the work. Databases and "
                   "anything resembling a secret are excluded because hashing them proves "
                   "nothing worth proving and risks something worth protecting.",
        },
        "recompute_it_yourself": [
            "Take your copy of the source tree.",
            "Drop the excluded directories, suffixes and names above.",
            "Hash each remaining file with the file rule.",
            "Sort by relative path and apply the manifest rule.",
            "Compare with the sealed root. A match means byte-identical code.",
        ],
        "privacy": "No file contents are stored or returned by any route. The manifest holds "
                   "paths and one-way hashes only, and the file list itself is keyed.",
        "the_discipline": "Seal on every deploy. A single snapshot is a claim about one day; a "
                          "continuous dated history is a record of the work.",
        "what_to_do_as_well": "Get the legal position in writing - entity ownership of the IP, "
                              "and a signed agreement with any collaborator saying who owns "
                              "what. Do it before it matters. This module makes the facts "
                              "unarguable; it cannot make the paperwork exist.",
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
        if action == "history":
            return _history(ctx)
        if action == "root":
            return _root(ctx)
        if action == "manifest":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _manifest(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "root", "manifest (keyed)"],
            "POST": ["seal (keyed)"]}, 404

```
