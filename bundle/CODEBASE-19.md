# Codebase — part 19 of 30

Contains:
- `tests/attack_continuity_1.py`
- `tests/attack_continuity_2.py`
- `tests/attack_continuity_3.py`
- `tests/attack_continuity_4.py`
- `tests/attack_continuity_5.py`
- `tests/attack_continuity_6.py`
- `tests/attack_witnessed.py`
- `verify_authority.py`
- `AILeash-API-Reference-v6.4.2.md`
- `LICENCE`
- `README.md`


## `tests/attack_continuity_1.py`

440 lines, 22747 bytes

```python
#!/usr/bin/env python3
"""Attack harness for modules/lineage.py.

Every test is written from the position of an agent that HAS some authority
and is trying to end up with more. Passing means the attack was refused for
the right reason, not merely refused.
"""

import hashlib
import json
import sqlite3
import threading
import time
import sys

import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    chain = {"n": 0, "prev": "0" * 64}

    def seal(ev, res, ts, api_key):
        chain["n"] += 1
        payload = json.dumps([ev, res, ts, api_key, chain["prev"]], sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        chain["prev"] = h
        return h, chain["n"], chain["n"]

    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(("  ok   " if condition else "  FAIL ") + name + (("  -> " + detail) if detail and not condition else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def exercise(ctx, **kw):
    return lineage._evaluate(ctx, "k", kw)


NOW = time.time()
HOUR = 3600


def base_root(ctx, **over):
    args = dict(
        id="root", issuer="justin@monop", issuer_kind="human",
        subject="orchestrator", subject_kind="agent",
        scope=["payments.refund", "payments.read", "tickets.*"],
        constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"],
                     "denied_country": ["KP"], "may_contact_customer": True},
        purpose="resolve customer refund complaints",
        purpose_tags=["refunds", "support"],
        not_before=NOW - HOUR, not_after=NOW + 10 * HOUR,
        delegations_left=3)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 1. the happy path must actually work ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="refund-agent", scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds under 500", purpose_tags=["refunds"],
      not_before=NOW - HOUR, not_after=NOW + 2 * HOUR, delegations_left=1)
r, code = exercise(ctx, grant="mid", action="payments.refund",
                   params={"amount": 100, "currency": "GBP", "country": "GB",
                           "contact_customer": True},
                   purpose_tag="refunds")
check("a derivable action returns ALLOW", r["verdict"] == "ALLOW", str(r["reasons"]))
check("lineage names the human at the root", r["authorised_by"] == "justin@monop")
check("depth is reported", r["delegation_depth"] == 1)
check("the decision is sealed", bool(r.get("sealed_in_chain")))

print("\n=== 2. orphan root: an agent grants itself authority ===")
ctx = make_ctx()
r, code = issue(ctx, id="self", issuer="rogue-agent", issuer_kind="agent",
                subject="rogue-agent", scope=["payments.refund"],
                constraints={"max_amount": 999999}, purpose="whatever I decide",
                purpose_tags=["anything"], not_after=NOW + HOUR)
check("self-issued root is refused at issue", code == 409 and r.get("error") == "identity_continuity", str(r))

print("\n=== 3. scope escalation in a child ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="wide", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund", "payments.transfer"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": False},
                purpose="sneak in a transfer", purpose_tags=["refunds"],
                not_after=NOW + HOUR, delegations_left=0)
check("scope the parent never held is refused",
      code == 409 and "payments.transfer" in r.get("message", ""), str(r))

print("\n=== 4. constraint loosening ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="rich", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 50000, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="bigger refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("raising a max_ cap is refused", code == 409 and "max_amount" in r.get("message", ""), str(r))

r, code = issue(ctx, id="wide2", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP", "USD"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="new currency", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("adding to an allowed_ set is refused", code == 409 and "USD" in r.get("message", ""), str(r))

r, code = issue(ctx, id="undeny", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": [], "may_contact_customer": True},
                purpose="drop the denylist", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("dropping from a denied_ set is refused", code == 409 and "KP" in r.get("message", ""), str(r))

r, code = issue(ctx, id="newkey", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True,
                             "may_export_data": True},
                purpose="invent a permission", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("introducing a constraint key the parent never expressed is refused",
      code == 409 and "may_export_data" in r.get("message", ""), str(r))

print("\n=== 5. temporal attacks ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="long", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="outlive the parent", purpose_tags=["refunds"],
                not_before=NOW, not_after=NOW + 100 * HOUR)
check("a child cannot outlive its parent", code == 409 and r.get("error") == "temporal_validity", str(r))

# expired ancestor, live leaf, forced in past the issue check
ctx = make_ctx()
base_root(ctx, not_after=NOW + HOUR)
issue(ctx, id="child", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="agent-b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET not_after=? WHERE id='root'", (NOW - 60,))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="child", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an expired ancestor kills a live leaf", r["verdict"] == "BLOCK", str(r["reasons"]))
check("...and it is reported as tampering, since the row no longer matches its digest",
      r["broken_invariant"] == "evidence_continuity", r["broken_invariant"] or "")

print("\n=== 6. revocation is transitive ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="leaf", parent="mid", issuer="b", issuer_kind="agent",
      subject="c", scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
lineage._revoke(ctx, "k", {"grant": "mid", "reason": "agent compromised"})
r, _ = exercise(ctx, grant="leaf", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("revoking the middle blocks the leaf without touching it", r["verdict"] == "BLOCK")
check("the revoked grant is named", r["broken_at"] == "mid", str(r["broken_at"]))
r2, _ = exercise(ctx, grant="root", action="payments.refund",
                 params={"amount": 10, "currency": "GBP", "country": "GB",
                         "contact_customer": True}, purpose_tag="refunds")
check("revoking a child does not harm the parent", r2["verdict"] == "ALLOW", str(r2["reasons"]))

print("\n=== 7. delegation depth cannot be manufactured ===")
ctx = make_ctx()
base_root(ctx, delegations_left=1)
issue(ctx, id="d1", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=0)
r, code = issue(ctx, id="d2", parent="d1", issuer="b", issuer_kind="agent", subject="c",
                scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("an exhausted delegation budget stops the chain",
      code == 409 and r.get("error") == "delegation_not_permitted", str(r))

ctx = make_ctx()
base_root(ctx, delegations_left=2)
r, code = issue(ctx, id="greedy", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR,
                delegations_left=5)
check("a child cannot award itself more onward delegations than remained",
      code == 409, str(r))

print("\n=== 8. tampering with a stored grant ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute(
        "UPDATE auth_grant SET constraints=? WHERE id='mid'",
        (json.dumps({"max_amount": 999999, "allowed_currency": ["GBP", "USD"],
                     "denied_country": [], "may_contact_customer": True},
                    sort_keys=True, separators=(",", ":")),))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 900000, "currency": "USD", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("editing the database does not widen authority", r["verdict"] == "BLOCK")
check("the tamper is reported as an evidence failure",
      r["broken_invariant"] == "evidence_continuity", str(r["broken_invariant"]))

print("\n=== 9. re-parenting onto a wider ancestor ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="narrow", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 1, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="read only", purpose_tags=["support"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent=NULL WHERE id='narrow'")
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="narrow", action="payments.read",
                params={}, purpose_tag="support")
check("detaching a grant to make it a root fails integrity", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 10. parent cycle ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="a", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="b", parent="a", issuer="b", issuer_kind="agent", subject="c",
      scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent='b' WHERE id='a'")
    ctx["conn"].commit()
start = time.time()
r, _ = exercise(ctx, grant="b", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("a parent cycle terminates rather than hangs", time.time() - start < 2)
check("a cycle is BLOCKed as an authority failure", r["verdict"] == "BLOCK")

print("\n=== 11. action parameters beyond the effective constraints ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 501, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an amount over the cap is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "KP",
                        "contact_customer": True}, purpose_tag="refunds")
check("a denied country is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))

print("\n=== 12. uncertainty is challenged, not guessed ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="marketing")
check("a purpose the grant does not carry is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True})
check("no declared purpose is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True, "recipient_iban": "GB00XXXX"},
                purpose_tag="refunds")
check("an unconstrained parameter is CHALLENGED, not ignored",
      r["verdict"] == "CHALLENGE" and any("recipient_iban" in x for x in r["reasons"]), str(r))

print("\n=== 13. wildcard breadth ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="root", action="tickets.close.bulk.all",
                params={}, purpose_tag="support")
check("a broad wildcard match is CHALLENGED rather than silently allowed",
      r["verdict"] == "CHALLENGE", str(r))

ctx = make_ctx()
base_root(ctx, scope=["*"], id="star")
r, _ = exercise(ctx, grant="star", action="payments.transfer", params={}, purpose_tag="refunds")
check("a bare * never reaches ALLOW", r["verdict"] == "CHALLENGE", str(r))

print("\n=== 14. no union of grants ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="money", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
issue(ctx, id="contact", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 0, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="contact", purpose_tags=["support"], not_after=NOW + HOUR)
r, code = exercise(ctx, grant="money,contact", action="payments.refund",
                   params={"amount": 10, "currency": "GBP", "contact_customer": True},
                   purpose_tag="refunds")
check("two grant ids cannot be combined into one exercise", r["verdict"] == "BLOCK", str(r))
r, _ = exercise(ctx, grant="money", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "contact_customer": True},
                purpose_tag="refunds")
check("the capability from the sibling grant does not leak in", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 15. time of check vs time of use ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
eval_id = r["evaluation"]
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 10, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing exactly what was evaluated binds", c["bound"] is True, str(c))
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 400, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing different values than were evaluated is rejected", c["bound"] is False, str(c))
check("the rejected execution is still sealed", bool(c.get("sealed_in_chain")))

with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_eval SET valid_until=? WHERE id=?", (NOW - 1, eval_id))
    ctx["conn"].commit()
c, _ = lineage._confirm(ctx, "k", {"evaluation": eval_id})
check("a banked evaluation cannot be spent after its window", c["bound"] is False, str(c))

print("\n=== 16. a BLOCK is evidence, not silence ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="nonexistent", action="payments.refund", params={})
check("an unknown grant BLOCKs", r["verdict"] == "BLOCK")
check("the block is sealed in the chain", bool(r.get("sealed_in_chain")))
d, code = lineage._decision(ctx, {"evaluation": r["evaluation"]})
check("the sealed decision is publicly retrievable", code == 200 and d["verdict"] == "BLOCK")

print("\n=== 17. no authority without a stated purpose or an end date ===")
ctx = make_ctx()
r, code = issue(ctx, id="forever", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="anything", purpose_tags=["x"])
check("a grant with no expiry is refused", code == 400 and r.get("error") == "not_after_required")
r, code = issue(ctx, id="vague", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="", purpose_tags=["x"], not_after=NOW + HOUR)
check("a grant with no purpose is refused", code == 400 and r.get("error") == "purpose_required")

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED: " + f)
    sys.exit(1)

```


## `tests/attack_continuity_2.py`

228 lines, 10573 bytes

```python
#!/usr/bin/env python3
"""Second wave. The first wave tested the obvious escalations. This one
tests the ones that would survive a code review."""

import hashlib
import json
import sqlite3
import threading
import time
import sys

import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []
NOW = time.time()
HOUR = 3600


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    n = {"i": 0}

    def seal(ev, res, ts, api_key):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True,
                                         default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> " + str(detail)[:300]) if detail and not cond else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund", "payments.read"],
                constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_before=NOW - HOUR, not_after=NOW + 10 * HOUR, delegations_left=10)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 18. double execution against one ALLOW ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
eid = r["evaluation"]
p = {"amount": 100, "currency": "GBP"}
c1, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
c2, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
check("the first execution binds", c1["bound"] is True, c1)
check("the same evaluation cannot be spent twice", c2["bound"] is False, c2)

print("\n=== 19. type confusion in constraints ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 5000, "allowed_currency": "GBP"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "G"},
                                    "purpose_tag": "refunds"})
check("a single character does not satisfy a string-valued allowed_ list",
      r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, code = issue(ctx, id="strnum", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": "50000", "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("a numeric cap passed as a string cannot beat the parent", code == 409, r)

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": "99999", "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a string amount is still compared numerically", r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": True, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a non-numeric amount does not slip through as unconstrained",
      r["verdict"] in ("BLOCK", "CHALLENGE"), r)

print("\n=== 20. capability prefix tricks ===")
ctx = make_ctx()
root(ctx, scope=["payments.refund"])
for probe in ["payments.refunds", "payments.refund.approve", "payments.refundX",
              "Payments.Refund", "payments.refund "]:
    r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": probe,
                                        "params": {}, "purpose_tag": "refunds"})
    check("'%s' is not covered by 'payments.refund'" % probe, r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx, scope=["payments.*"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments2.transfer",
                                    "params": {}, "purpose_tag": "refunds"})
check("'payments.*' does not cover 'payments2.transfer'", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 21. a long but legitimate chain ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 10000, "allowed_currency": ["GBP", "EUR"]},
     delegations_left=12)
parent, cap = "root", 10000
for i in range(10):
    cap = cap // 2
    gid = "d%d" % i
    r, code = issue(ctx, id=gid, parent=parent, issuer="a%d" % i, issuer_kind="agent",
                    subject="a%d" % (i + 1), scope=["payments.refund"],
                    constraints={"max_amount": cap, "allowed_currency": ["GBP"]},
                    purpose="refunds", purpose_tags=["refunds"],
                    not_after=NOW + HOUR, delegations_left=11 - i)
    if code != 200:
        break
    parent = gid
check("ten legitimate narrowing hops are accepted", code == 200 and parent == "d9", r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 5, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("the deep chain still ALLOWs a derivable action", r["verdict"] == "ALLOW", r["reasons"])
check("the effective cap is the tightest in the chain",
      float(r["effective_constraints"]["max_amount"]) == 9, r["effective_constraints"])
check("the human at the root is still named ten hops down",
      r["authorised_by"] == "owner@example.com")
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("one unit over the deepest cap is BLOCKed", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 22. revoking the root kills the whole tree ===")
lineage._revoke(ctx, "k", {"grant": "root", "reason": "principal withdrew authority"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("revoking the root blocks a leaf ten hops away", r["verdict"] == "BLOCK")
check("the root is named as the break point", r["broken_at"] == "root", r["broken_at"])

print("\n=== 23. issuing under a revoked or expired parent ===")
ctx = make_ctx()
root(ctx)
lineage._revoke(ctx, "k", {"grant": "root", "reason": "x"})
r, code = issue(ctx, id="after", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 1, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("no new delegation under a revoked parent", code == 409 and r.get("error") == "parent_revoked", r)

print("\n=== 24. duplicate grant id cannot overwrite a grant ===")
ctx = make_ctx()
root(ctx)
r, code = root(ctx, scope=["*"], constraints={"max_amount": 999999})
check("re-issuing an existing id is refused", code == 409 and r.get("error") == "grant_exists", r)

print("\n=== 25. the boundary values themselves ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 100, "allowed_currency": ["GBP"]}, delegations_left=2)
r, code = issue(ctx, id="equal", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_after=NOW + 10 * HOUR, delegations_left=1)
check("an equal-not-wider child is accepted", code == 200, r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("exactly the cap is allowed", r["verdict"] == "ALLOW", r["reasons"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100.01, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a penny over the cap is blocked", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 26. a CHALLENGE cannot be executed ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"}})
check("no declared purpose gives CHALLENGE", r["verdict"] == "CHALLENGE", r["verdict"])
c, code = lineage._confirm(ctx, "k", {"evaluation": r["evaluation"],
                                      "action": "payments.refund",
                                      "params": {"amount": 1, "currency": "GBP"}})
check("a CHALLENGE cannot be bound as an execution", c["bound"] is False, c)

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED: " + f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_3.py`

114 lines, 5626 bytes

```python
#!/usr/bin/env python3
"""Third wave: concurrency, and reconstruction from evidence alone."""
import hashlib, json, sqlite3, threading, time, sys
import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    def seal(ev, res, ts, k):
        with lock:
            n["i"] += 1
            return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx); return ctx

def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:250]) if d and not c else ""))

print("\n=== 27. concurrent execution of one ALLOW ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
    subject="agent",scope=["payments.refund"],constraints={"max_amount":5000},
    purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":100},"purpose_tag":"refunds"})
eid = r["evaluation"]; results = []
def race():
    c,_ = lineage._confirm(ctx,"k",{"evaluation":eid,"action":"payments.refund","params":{"amount":100}})
    results.append(c["bound"])
ts = [threading.Thread(target=race) for _ in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
check("exactly one of eight concurrent executions binds", results.count(True) == 1, results)
with ctx["lock"]:
    rows = ctx["conn"].execute("SELECT COUNT(*) FROM auth_exec WHERE eval_id=? AND outcome<>'rejected'",(eid,)).fetchone()
check("only one accepted binding exists in storage", rows[0] == 1, rows)

print("\n=== 28. reconstruct the whole story from the sealed record ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="orchestrator",scope=["payments.*"],constraints={"max_amount":5000},
    purpose="close the refund backlog",purpose_tags=["refunds"],
    not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="orchestrator",issuer_kind="agent",
    subject="refund-bot",scope=["payments.refund"],constraints={"max_amount":200},
    purpose="issue small refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":150},"purpose_tag":"refunds"})
t,code = lineage._trace(ctx,{"grant":"m"})
check("the trace names who authorised it", t["authorised_by"] == "owner@example.com")
check("the trace names who held it at execution", t["holder"] == "refund-bot")
check("the trace shows what changed at each hop",
      t["lineage"][0]["scope"] == ["payments.*"] and t["lineage"][1]["scope"] == ["payments.refund"])
check("the effective constraint is the narrowest, not the granted one",
      float(t["effective_constraints"]["max_amount"]) == 200, t["effective_constraints"])
d,code = lineage._decision(ctx,{"evaluation":r["evaluation"]})
check("the decision is retrievable without a key and matches", d["verdict"] == r["verdict"])
check("the decision carries the lineage digest", d["lineage_digest"] == r["lineage_digest"])
check("every hop carries its own block index",
      all(h["block_index"] for h in t["lineage"]))

print("\n=== 29. widening midway is visible in the trace, not just blocked ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="a",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="a",issuer_kind="agent",
    subject="b",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=1,
    risk_accepted_by="owner@example.com"))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET constraints=? WHERE id='m'",
        (json.dumps({"max_amount":100000},sort_keys=True,separators=(",",":")),))
    ctx["conn"].commit()
t,_ = lineage._trace(ctx,{"grant":"m"})
check("the trace flags the altered hop by name",
      t["lineage"][1]["integrity"] == "FAILED" and t["lineage"][0]["integrity"] == "ok", t["lineage"])
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":50},"purpose_tag":"refunds"})
check("and the exercise names the exact grant that broke", r["broken_at"] == "m", r["broken_at"])

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_4.py`

107 lines, 4723 bytes

```python
#!/usr/bin/env python3
"""Fourth wave: does it actually compose with the existing engine, and can
either side be bypassed by the other?"""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600
STATE = {"verdict": "ALLOW", "raises": False, "shape": "dict", "seen": []}

def install(verdict="ALLOW", raises=False, shape="dict"):
    STATE.update(verdict=verdict, raises=raises, shape=shape)
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    def score_event(event):
        STATE["seen"].append(event)
        if STATE["raises"]: raise RuntimeError("engine down")
        if STATE["shape"] == "dict": return {"decision": STATE["verdict"], "score": 0.42}
        if STATE["shape"] == "tuple": return (STATE["verdict"], 0.42)
        if STATE["shape"] == "junk": return {"nothing": "useful"}
        return STATE["verdict"]
    m.score_event = score_event
    sys.modules["server"] = m

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def setup():
    ctx = make_ctx()
    C._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
        subject="agent",scope=["payments.refund"],
        constraints={"max_amount":5000,"allowed_currency":["GBP"]},
        purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
    return ctx

def run(ctx, amount=100):
    return C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
        "params":{"amount":amount,"currency":"GBP"},"purpose_tag":"refunds"})[0]

print("\n=== 30. the engine is actually consulted ===")
install("ALLOW"); STATE["seen"] = []
r = run(setup())
check("a clean authority plus a clean engine is ALLOW", r["verdict"]=="ALLOW", r)
check("the engine was called with the real action and amount",
      STATE["seen"] and STATE["seen"][-1]["action"]=="payments.refund"
      and STATE["seen"][-1]["amount"]==100, STATE["seen"][-1] if STATE["seen"] else None)
check("both components are reported separately",
      r["authority_verdict"]=="ALLOW" and r["risk_verdict"]=="ALLOW", r)

print("\n=== 31. neither side can wave the other through ===")
install("BLOCK")
r = run(setup())
check("perfect authority does not survive an engine BLOCK", r["verdict"]=="BLOCK", r)
check("the authority component still reads ALLOW underneath it",
      r["authority_verdict"]=="ALLOW", r)
install("CHALLENGE")
r = run(setup())
check("an engine CHALLENGE lifts a clean authority to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW")
ctx = setup()
r = C._evaluate(ctx,"k",{"grant":"root","action":"payments.transfer",
    "params":{"amount":1},"purpose_tag":"refunds"})[0]
check("a clean engine does not confer authority nobody granted", r["verdict"]=="BLOCK", r)
check("and the engine is not even asked once authority has failed",
      r["risk_engine"]["available"] is False, r["risk_engine"])

print("\n=== 32. a missing or broken engine is not an ALLOW ===")
install("ALLOW", raises=True)
r = run(setup())
check("an engine that throws downgrades ALLOW to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW", shape="junk")
r = run(setup())
check("an unreadable engine response downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
sys.modules.pop("server", None); sys.modules.pop("__main__", None)
r = run(setup())
check("no engine present downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
check("the reason names the missing engine",
      any("risk engine" in x for x in r["reasons"]), r["reasons"])

print("\n=== 33. it reads the engine's other return shapes ===")
for shape in ("dict","tuple","str"):
    install("BLOCK", shape=shape)
    r = run(setup())
    check("a %s return shape is understood" % shape, r["verdict"]=="BLOCK", r["risk_engine"])

print("\n=== 34. an engine BLOCK cannot be executed ===")
install("BLOCK")
ctx = setup(); r = run(ctx)
c,_ = C._confirm(ctx,"k",{"evaluation":r["evaluation"],"action":"payments.refund",
    "params":{"amount":100,"currency":"GBP"}})
check("execution is refused when the engine blocked", c["bound"] is False, c)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_5.py`

116 lines, 5639 bytes

```python
#!/usr/bin/env python3
"""Fifth wave: risk acceptance. Who put their name to this capability
existing at all - separately from who granted it and who holds it."""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600

def install():
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    m.score_event = lambda e: {"decision": "ALLOW", "score": 0.1}
    sys.modules["server"] = m
install()

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund"],
                constraints={"max_amount":5000}, purpose="refunds",
                purpose_tags=["refunds"], not_after=NOW+HOUR, delegations_left=3)
    args.update(over)
    return C._issue(ctx,"k",args)

print("\n=== 35. a root accepts its own risk by default ===")
ctx = make_ctx()
r, code = root(ctx)
check("a root grant records an acceptor without being asked",
      code == 200 and r["risk_accepted_by"] == "owner@example.com", r)
r2, _ = root(ctx, id="root2", risk_accepted_by="risk.officer@example.com")
check("a root can name someone other than the issuer",
      r2["risk_accepted_by"] == "risk.officer@example.com", r2)

print("\n=== 36. switching on onward delegation needs a name ===")
ctx = make_ctx(); root(ctx)
r, code = C._issue(ctx,"k",dict(id="deleg", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1))
check("a delegable child with no acceptor is refused",
      code == 409 and r.get("error") == "risk_acceptance_required", r)

r, code = C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
check("a non-delegable child inherits the acceptor above it", code == 200, r)

r, code = C._issue(ctx,"k",dict(id="deleg2", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1, risk_accepted_by="head.of.ops@example.com"))
check("a delegable child with a named acceptor is accepted", code == 200, r)

print("\n=== 37. the decision names the accountable person ===")
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("an evaluation reports who accepts the risk",
      e["risk_accepted_by"] == "owner@example.com", e.get("risk_accepted_by"))
check("...separately from who authorised it and who executed it",
      e["authorised_by"] == "owner@example.com" and e["executed_by"] == "b", e)

e2, _ = C._evaluate(ctx,"k",{"grant":"deleg2","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("the nearest acceptor wins, not the root one",
      e2["risk_accepted_by"] == "head.of.ops@example.com", e2.get("risk_accepted_by"))

t, _ = C._trace(ctx,{"grant":"deleg2"})
check("the trace shows the acceptor at each hop",
      t["risk_accepted_by"] == "head.of.ops@example.com" and
      t["lineage"][0]["risk_accepted_by"] == "owner@example.com", t)

print("\n=== 38. an unaccepted lineage cannot act ===")
ctx = make_ctx(); root(ctx)
C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by=NULL")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("stripping every acceptor blocks the action", e["verdict"] == "BLOCK", e["reasons"])
check("...and says an incident would have no accountable person",
      any("accountable" in x for x in e["reasons"]), e["reasons"])

print("\n=== 39. the acceptor cannot be swapped after the fact ===")
ctx = make_ctx(); root(ctx, risk_accepted_by="risk.officer@example.com")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by='someone.else@example.com' WHERE id='root'")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("editing who accepted the risk fails the digest", e["verdict"] == "BLOCK", e["reasons"])
check("...reported as an evidence failure, naming the grant",
      e["broken_invariant"] == "evidence_continuity" and e["broken_at"] == "root", e)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_6.py`

92 lines, 3965 bytes

```python
"""End to end: issue, delegate, exercise, export a proof, verify it elsewhere,
then try to forge one."""
import hashlib, json, sqlite3, threading, time, sys, types, subprocess, copy
import continuity as C

m = types.ModuleType("server")
m.get_bearer = lambda *a, **k: None
m.score_event = lambda e: 0.12          # bare score, like the real engine
sys.modules["server"] = m

conn = sqlite3.connect(":memory:", check_same_thread=False)
lock = threading.RLock(); n = {"i": 0}
def seal(ev, res, ts, k):
    n["i"] += 1
    return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True, default=str).encode()).hexdigest(), n["i"], n["i"]
ctx = {"conn": conn, "lock": lock, "seal": seal}
C._ready = False; C._setup(ctx)

NOW, HOUR = time.time(), 3600
C._issue(ctx, "k", dict(id="root", issuer="justin@monopcontent.com", issuer_kind="human",
    subject="orchestrator", scope=["payments.refund", "payments.read"],
    constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
    purpose="resolve customer refund complaints", purpose_tags=["refunds", "support"],
    not_after=NOW + 10 * HOUR, delegations_left=2))
C._issue(ctx, "k", dict(id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
    subject="refund-agent", scope=["payments.refund"],
    constraints={"max_amount": 200, "allowed_currency": ["GBP"]},
    purpose="issue small refunds", purpose_tags=["refunds"],
    not_after=NOW + 2 * HOUR, delegations_left=0))

def run(params, tag="refunds", action="payments.refund"):
    r, _ = C._evaluate(ctx, "k", {"grant": "mid", "action": action,
                                  "params": params, "purpose_tag": tag})
    return r

allow = run({"amount": 150, "currency": "GBP"})
block = run({"amount": 900, "currency": "GBP"})
print("allow verdict:", allow["verdict"], "| block verdict:", block["verdict"],
      "->", block["broken_invariant"])

def bundle_for(ev):
    b, code = C._proof(ctx, {"evaluation": ev})
    assert code == 200, b
    return b

for label, ev in (("ALLOW", allow["evaluation"]), ("BLOCK", block["evaluation"])):
    b = bundle_for(ev)
    open("/tmp/%s.json" % label, "w").write(json.dumps(b, indent=1))
    print("\n" + "#" * 66 + "\n# %s bundle\n" % label + "#" * 66)
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/%s.json" % label],
                         capture_output=True, text=True)
    print(out.stdout.strip()); print("exit:", out.returncode)

print("\n" + "#" * 66 + "\n# forgeries\n" + "#" * 66)
good = json.load(open("/tmp/BLOCK.json"))

def forge(name, mutate):
    b = copy.deepcopy(good)
    mutate(b)
    open("/tmp/forged.json", "w").write(json.dumps(b))
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/forged.json"],
                         capture_output=True, text=True)
    caught = out.returncode != 0
    line = [l for l in out.stdout.splitlines() if l.startswith("FAIL")]
    print(("  ok   " if caught else "  MISS ") + name)
    for l in line[:2]:
        print("         " + l.strip())

def flip_verdict(b):
    b["decision"]["verdict"] = "ALLOW"; b["decision"]["authority_verdict"] = "ALLOW"
def raise_cap(b):
    pass_idx = 1
    b["lineage"][1]["constraints"]["max_amount"] = 100000
def widen_scope(b):
    b["lineage"][1]["scope"] = ["payments.refund", "payments.transfer"]
def swap_human(b):
    b["lineage"][0]["issuer_kind"] = "agent"
def change_params(b):
    b["request"]["params"]["amount"] = 1
def drop_acceptor(b):
    for g in b["lineage"]: g["risk_accepted_by"] = None
def restamp(b):
    b["decision"]["evaluated_at_epoch"] = NOW + 9 * HOUR

forge("claimed ALLOW on a bundle that blocks", flip_verdict)
forge("cap raised inside the lineage", raise_cap)
forge("scope widened inside the lineage", widen_scope)
forge("root demoted from human", swap_human)
forge("parameters swapped after the fact", change_params)
forge("risk acceptor stripped", drop_acceptor)
forge("timestamp moved past the leaf's expiry", restamp)

```


## `tests/attack_witnessed.py`

160 lines, 7875 bytes

```python
"""Attack it the same way as everything else: from the position of an operator
trying to make a grant look older than it is."""
import hashlib, json, sqlite3, threading, time, sys, types
import witnessed as W

P, F = [], []
def check(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:200]) if d and not c else ""))

def make():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    conn.execute("CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "ts REAL,user_id TEXT,api_key TEXT,result_json TEXT,audit_hash TEXT)")
    # the real grant table shape, including columns added later
    conn.execute("CREATE TABLE auth_grant(id TEXT PRIMARY KEY,parent TEXT,root TEXT,"
                 "issuer TEXT,subject TEXT,created REAL,digest TEXT,audit_hash TEXT,"
                 "block_index INTEGER,risk_accepted_by TEXT)")
    def seal(ev, res, ts, key):
        n["i"] += 1
        h = hashlib.sha256(json.dumps([ev,res,ts,n["i"]],sort_keys=True,default=str).encode()).hexdigest()
        conn.execute("INSERT INTO audit_log(ts,user_id,api_key,result_json,audit_hash) "
                     "VALUES(?,?,?,?,?)", (ts, ev.get("user_id"), key, json.dumps(res), h))
        conn.commit()
        return h, n["i"], n["i"]
    W._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    W._setup(ctx)
    return ctx

def seal_grant(ctx, gid, created):
    h, idx, _ = ctx["seal"]({"user_id": "lin:"+gid}, {"decision":"AUTHORITY_GRANTED","grant":gid}, created, "k")
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO auth_grant(id,issuer,subject,created,audit_hash,block_index) "
                            "VALUES(?,?,?,?,?,?)", (gid,"owner@example.com","agent",created,h,idx))
        ctx["conn"].commit()
    return h

def noise(ctx, k=5):
    for i in range(k):
        ctx["seal"]({"user_id":"n%d"%i},{"decision":"ALLOW"},time.time(),"k")

def record_head(ctx, peer, accepted=1, when=None, size=None, tip=None):
    """Insert an attestation directly, standing in for a live peer."""
    s, t = W._head(ctx)
    when = when or time.time()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,api_key)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer,"https://%s"%peer, size or s, tip or t,"d",when,accepted,"{}","b1","ah",1,"k"))
        ctx["conn"].commit()

NOW = time.time()

print("\n=== 1. a grant witnessed after issue ===")
ctx = make()
noise(ctx, 3)
g = seal_grant(ctx, "root", NOW - 3600)
noise(ctx, 4)
record_head(ctx, "redflagai.pro", when=NOW - 1800)
r, code = W._grant(ctx, {"id": "root"})
check("witnessed grant reports externally_witnessed", code==200 and r["externally_witnessed"], r)
check("names the peer and the time", r["earliest_external_witness"]["peer"]=="redflagai.pro", r)
check("gives a four-step plan pointed at the peer",
      len(r["verification_plan"])==4 and "attest" in r["verification_plan"][0]["run"], r["verification_plan"][0])
check("states what it does not prove", "should ever have been issued" in r["what_this_does_not_prove"])
check("reports how long it sat unwitnessed", r["minutes_unwitnessed"] is not None, r.get("minutes_unwitnessed"))

print("\n=== 2. THE ATTACK: a grant back-dated after the fact ===")
# operator invents a root grant now, and writes created= last week
ctx = make()
noise(ctx, 3)
record_head(ctx, "redflagai.pro", when=NOW - 86400)      # peer saw the log yesterday
forged = seal_grant(ctx, "forged", NOW - 7*86400)        # grant CLAIMS to be a week old
r, code = W._grant(ctx, {"id": "forged"})
check("a grant sealed after the last witness is NOT covered", not r["externally_witnessed"], r)
check("and says so plainly rather than staying quiet", "rests on this operator's own record" in r.get("flag",""), r.get("flag"))
# now a peer witnesses; from here it is covered, but only from here
record_head(ctx, "redflagai.pro", when=NOW)
r2, _ = W._grant(ctx, {"id": "forged"})
check("after a later witness it becomes covered", r2["externally_witnessed"])
gapdays = round(r2["minutes_unwitnessed"]/1440.0, 1)
check("the seven-day claim-to-witness gap is published, not hidden",
      r2.get("flag") and "days" in r2["flag"] and gapdays >= 6.9, {"gap_days":gapdays,"flag":r2.get("flag")})

print("\n=== 3. coverage counts only what a peer accepted ===")
ctx = make()
noise(ctx, 2); g = seal_grant(ctx, "g1", NOW); noise(ctx, 2)
record_head(ctx, "peer-that-refused", accepted=0)
r, _ = W._grant(ctx, {"id": "g1"})
check("a refused submission gives no coverage", not r["externally_witnessed"], r.get("earliest_external_witness"))
h, _ = W._heads(ctx, {})
check("but the refusal is still on the public record", h["count"]==1 and h["heads"][0]["accepted"] is False, h)

print("\n=== 4. a head that predates the grant does not cover it ===")
ctx = make()
record_head(ctx, "early-peer", when=NOW-9999)   # size 0
noise(ctx, 3)
seal_grant(ctx, "later", NOW)
r, _ = W._grant(ctx, {"id": "later"})
check("an earlier, smaller head cannot reach a later record", not r["externally_witnessed"], r)

print("\n=== 5. the earliest witness wins, not the most convenient ===")
ctx = make()
noise(ctx, 2); seal_grant(ctx, "g", NOW - 600); noise(ctx, 2)
record_head(ctx, "second-peer", when=NOW - 100)
record_head(ctx, "first-peer",  when=NOW - 400)
r, _ = W._grant(ctx, {"id": "g"})
check("earliest accepted attestation is the one reported",
      r["earliest_external_witness"]["peer"]=="first-peer", r["earliest_external_witness"])
check("the others are listed too", any(c["peer"]=="second-peer" for c in r["also_witnessed_by"]), r["also_witnessed_by"])

print("\n=== 6. status is honest about thin networks ===")
ctx = make(); noise(ctx, 3)
s, _ = W._status(ctx)
check("no peers at all reports strength none", s["strength"]=="none" and "rests on our own record" in s["flag"], s)
record_head(ctx, "only-peer")
s, _ = W._status(ctx)
check("one peer reports weak and names collusion", s["strength"]=="weak" and "collude" in s["flag"], s)
for p in ("p2","p3"): record_head(ctx, p)
s, _ = W._status(ctx)
check("three peers reports reasonable", s["strength"]=="reasonable", s)
noise(ctx, 6)
s, _ = W._status(ctx)
check("records sealed since the last head are counted as unwitnessed",
      s["records_not_yet_witnessed"]==6, s)

print("\n=== 7. tampering with the grant row ===")
ctx = make(); noise(ctx,2); seal_grant(ctx,"t",NOW); record_head(ctx,"peer")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET audit_hash='0'*64 WHERE id='t'")
    ctx["conn"].commit()
r, code = W._grant(ctx, {"id":"t"})
check("a grant whose seal is not in the log is a finding, not a 404",
      code==409 and "finding" in r.get("message",""), (code, r))

print("\n=== 8. url safety on submit ===")
ctx = make(); noise(ctx,2)
for bad, why in [("http://127.0.0.1/x","loopback"),("http://10.0.0.5/x","private"),
                 ("ftp://example.com","scheme"),("https://example.com:8443/x","port")]:
    r, code = W._submit(ctx, "k", {"peer":"p","url":bad})
    check("refuses %s" % why, code==400 and r.get("error")=="url_refused", (bad,code,r))

print("\n=== 9. any sealed record, not just grants ===")
ctx = make(); noise(ctx,2)
h,_ ,_ = ctx["seal"]({"user_id":"x"},{"decision":"ALLOW"},NOW,"k")
noise(ctx,1); record_head(ctx,"peer")
r, code = W._record(ctx, {"hash": h})
check("a decision receipt gets the same treatment", code==200 and r["externally_witnessed"], r)
r, code = W._record(ctx, {"hash": "zz"})
check("a malformed hash is refused", code==400, (code,r))

print("\n" + "="*62)
print("passed %d, failed %d" % (len(P), len(F)))
for f in F: print("  FAILED: " + f)
sys.exit(1 if F else 0)

```


## `verify_authority.py`

573 lines, 21333 bytes

```python
#!/usr/bin/env python3
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

```


## `AILeash-API-Reference-v6.4.2.md`

256 lines, 6799 bytes

```markdown
# AILeash v6.4.2 — Complete API Reference

## Core Decision Endpoint

### POST /api/govern
**The engine. Every action scores here.**

Auth: `Bearer YOUR_API_KEY`

**Request:**
```json
{
  "user_id": "string (required)",
  "action": "string (required) — payment/login/message/transfer/checkout/api_call",
  "amount": "number (optional, default 0) — monetary value in GBP",
  "country": "string (required) — ISO 3166-1 alpha-2 code",
  "device_id": "string (required) — unique device identifier",
  "anomaly": "number 0..1 (optional) — behavioural anomaly score",
  "device_risk": "number 0..1 (optional) — device risk score"
}
```

**Response (200 OK):**
```json
{
  "decision": "ALLOW|CHALLENGE|BLOCK",
  "score": 0.0..1.0,
  "trust": 0.05..1.0,
  "reasons": ["velocity_spike", "high_amount", "country_shift"],
  "audit_hash": "sha256_hex_string",
  "block_index": 12345,
  "receipt_seq": 42,
  "timestamp": 1719072000.0,
  "challenge_url": "https://sebbi.pro/verify-challenge?token=...",
  "challenge_expires_in": 900
}
```

**Error responses:**
- `401 Unauthorized` — Missing or invalid API key
- `403 Forbidden` — Account inactive or over quota
- `429 Too Many Requests` — Rate limited
- `503 Service Unavailable` — Server overloaded

---

## Account Management

### POST /api/keys or /signup
**Create a new API key. Instant. No card. No humans in the loop.**

No auth required.

**Request:**
```json
{
  "email": "user@example.com (required)",
  "name": "John Doe (optional)",
  "phone": "+441234567890 (optional)",
  "org": "Acme Corp (optional)",
  "product": "aileash|guardian|sonicboom|sentinel (default: aileash)",
  "devices": 1..1000000 (default: 1),
  "ref_code": "REF-XXXX-1234 (optional)"
}
```

**Response (200 OK):**
```json
{
  "api_key": "al_live_...",
  "email": "user@example.com",
  "product": "aileash",
  "devices": 1,
  "monthly_cost": 0.50,
  "quota": 100,
  "ref_code": "REF-JOHN-5678",
  "badge_id": "abc123def456",
  "message": "100 free decisions. Then 50p per device per month via Stripe."
}
```

---

## Verification & Public Endpoints

### GET /api/spec
**Engine specification. Public. No auth.**

**Response (200 OK):**
```json
{
  "engine": "AILeash v6.4.2",
  "version": "6.4.2",
  "signals": 9,
  "decision_latency_ms": 28,
  "threshold_allow": 0.35,
  "threshold_challenge": 0.70,
  "threshold_block": 1.0,
  "features": ["deterministic scoring", "tamper-evident chain", "real-time alerts", "gapless receipts", "sovereign deployment"]
}
```

### GET /api/verify-chain
**Full audit chain integrity proof. Public. No auth.**

**Response (200 OK):**
```json
{
  "valid": true,
  "blocks": 45678,
  "genesis": "GENESIS",
  "tip": "abc123...",
  "message": "Chain intact. No tampering detected.",
  "verifiable_by": "anyone, anywhere"
}
```

### GET /api/health
**Server health and load. Public. No auth.**

**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "6.4.2",
  "uptime_seconds": 864000,
  "rps": 42,
  "timestamp": 1719072000.0
}
```

---

## Real-time Dashboards

### GET /api/pulse
**Live risk posture. Your current state.**

Auth: `Bearer YOUR_API_KEY`

**Response (200 OK):**
```json
{
  "last_hour": {
    "ALLOW": 486,
    "CHALLENGE": 23,
    "BLOCK": 4
  },
  "recent": [
    {
      "ts": 1719072000,
      "user_id": "u_7f2",
      "action": "payment",
      "decision": "ALLOW",
      "score": 0.12,
      "reasons": [],
      "audit_hash": "abc123..."
    }
  ],
  "chain_tip": "abc123...",
  "message": "All green. Chain tip sealed."
}
```

---

## Billing & Webhooks

### POST /stripe-webhook
**Stripe webhook receiver. Signature verified automatically.**

Supports events:
- `checkout.session.completed` — User upgraded
- `invoice.paid` — Monthly subscription paid
- `customer.subscription.deleted` — User cancelled
- `invoice.payment_failed` — Payment failed

---

## Four Products. One Engine.

### AILeash
- **What:** Every AI decision your platform makes about a person gets scored, explained, and sealed.
- **Who:** Platforms using AI for any regulated decision (lending, hiring, content moderation, fraud, access control).
- **Price:** 50p per device per month + your margin.
- **Free tier:** 100 decisions/month, no card.

### Guardian
- **What:** Free message checker for families. Child pastes a message in, gets instant plain-English assessment against grooming patterns.
- **Who:** Families. Free forever. No card. No catch.
- **Price:** Free. Always.
- **Built for:** ICO Children's Code, Online Safety Act, child safety.

### SonicBoom
- **What:** One line of code. Drops into AWS, Azure, GCP, OpenAI, Anthropic. Adds full compliance audit chain to every call.
- **Who:** Platforms already running AI in the cloud.
- **Price:** 50p per device per month + your margin.
- **Latency:** No impact. Chain sealing is asynchronous.

### Sentinel
- **What:** Fraud and anomaly alerting. Scores unusual patterns (500 messages in a minute, login from new country, velocity spikes) in real-time.
- **Who:** Platforms managing fraud, abuse, takeovers.
- **Price:** 50p per device per month + your margin.
- **Real-time:** Alerts the moment thresholds trip.

---

## The Score Formula (Immutable)

**Raw weighted sum (Σ_raw):**
```
Σ_raw =
  (1 − trust) × 0.30
  + min(velocity_60s / 20, 1) × 0.15
  + min(velocity_5m / 50, 1) × 0.10
  + min(velocity_1h / 200, 1) × 0.10
  + min(ln(1+amount) / ln(1+10000), 1) × 0.15
  + device_risk × 0.10
  + behavioural_anomaly × 0.10
  + country_shift × 0.10
  + unsafe_country × 0.10
```

**Normalization:** the nine weights above sum to 1.20, not 1.0. To keep every signal's *relative* importance exactly as designed while guaranteeing the score behaves as a true 0–1 weighted average (not one that can reach BLOCK-level values from fewer combined signals than intended), divide by the actual weight total before clamping:

```
WEIGHT_TOTAL = 0.30 + 0.15 + 0.10 + 0.10 + 0.15 + 0.10 + 0.10 + 0.10 + 0.10   # = 1.20

score = clamp( Σ_raw / WEIGHT_TOTAL , 0, 1 )

decision = ALLOW if score < 0.35
         = CHALLENGE if score < 0.70
         = BLOCK otherwise
```

No machine learning. No drift. No retraining. Weights are written in code and cannot change without a new release. `WEIGHT_TOTAL` is a fixed constant (1.20) recomputed only if a signal is added, removed, or reweighted in a future release — never at runtime.

---

## Rate Limits

- **Free tier:** 100 decisions/month
- **Paid:** Unlimited (or by plan)
- **Public endpoints:** No rate limit

---

## Documentation

- **Homepage:** https://sebbi.pro
- **Whitepaper:** https://sebbi.pro/whitepaper
- **Developers:** https://sebbi.pro/developers
- **Scanner (free):** https://sebbi.pro/scan
- **Guardian:** https://sebbi.pro/guardian-app
- **Contact:** justrightdecorators@gmail.com

```


## `LICENCE`

22 lines, 1074 bytes

```
MIT License

Copyright (c) 2026 Monop (Blyth, UK)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```


## `README.md`

277 lines, 15728 bytes

```markdown
<div align="center">

```
        ┌─────────────────────────────────────────────────┐
        │   s e b b i . p r o                              │
        │                                                  │
        │   O N E   C H A I N .   E V E R Y   P R O O F .   │
        └─────────────────────────────────────────────────┘
```

### The tamper-evident evidence layer for AI decisions, payments, and records.

*Every event sealed into a hash chain at the moment it happens —*
*the decision, **and the basis it rested on** — unalterable by anyone. Including us.*

<br>

[![live](https://img.shields.io/badge/live-sebbi.pro-c9a84c?style=for-the-badge)](https://sebbi.pro)
[![verify the chain](https://img.shields.io/badge/verify_the_chain-open_endpoint-7fe3b0?style=for-the-badge)](https://sebbi.pro/api/verify-chain)
[![seal something free](https://img.shields.io/badge/seal_something-free,_no_account-7cc8ff?style=for-the-badge)](https://sebbi.pro/seal)

**[Try it](https://sebbi.pro/seal)** · **[Verify it](https://sebbi.pro/verify)** · **[Read the code](https://sebbi.pro/brain)** · **[Developer docs](https://sebbi.pro/developers)** · **[Whitepaper](https://sebbi.pro/whitepaper)**

</div>

---

> ### *A system that does not trust its own creator*
> ### *is the only kind whose records qualify as evidence.*

---

## Don't read about it. Watch it work.

Here is a **real** four-block chain. Every hash below is reproducible — same inputs, same seals, forever. Copy the recipe at the bottom and compute them yourself.

```
  #   EVENT                             RESULT      SEAL (SHA-256, truncated)
  ─────────────────────────────────────────────────────────────────────────
  1   system_regmap                     ALLOW       411ffd9a31a3d9f4…
  2   seal_post: quarterly_report.pdf   NOTARISED   c7309616a9e92bc7…
  3   govern: payment 9000 GBP          BLOCK       293181a2bc2dab88…
  4   brain: approve supplier 88        ALLOW       6abba40eb964959e…
  ─────────────────────────────────────────────────────────────────────────
  genesis  9fd06d6fdc19761d…                         tip  6abba40eb964959e…
```

Now watch someone try to cover up that blocked £9,000 payment by flipping block 3 from **BLOCK** to **ALLOW**:

```
  block 3 altered  →  tip becomes  5e15bc5710426088…   ❌  ≠ 6abba40eb964959e…
```

**The tip changed. The forgery is exposed instantly, by arithmetic, to anyone — no account, no trust required.** That is the entire product in six lines. Everything below is detail.

<details>
<summary><b>▸ Reproduce every hash yourself (10 lines of Python)</b></summary>

```python
import hashlib, json
seal = lambda prev, ts, ev, res, basis: hashlib.sha256(
    json.dumps({"prev":prev,"ts":ts,"event":ev,"result":res,"basis":basis},
               sort_keys=True).encode()).hexdigest()

prev = hashlib.sha256(b"AILEASH_BRAIN_GENESIS|sebbi.pro|v5").hexdigest()
chain = [("system_regmap","ALLOW","regmap-v7"),
         ("seal_post: quarterly_report.pdf","NOTARISED","NO_BASIS"),
         ("govern: payment 9000 GBP","BLOCK","invoice_4471|regmap-v7"),
         ("brain: approve supplier 88","ALLOW","invoice_4471|regmap-v7")]
ts = 1752940000
for ev,res,basis in chain:
    prev = seal(prev, ts, ev, res, basis); ts += 3600
    print(prev[:16], "…", ev)
# final line prints the tip: 6abba40eb964959e …
```
Change one character of one event and every seal after it changes. That's the whole idea.
</details>

---

## Why this exists

Every system keeps logs. Logs live in databases. Databases can be edited — by an attacker, an insider, or the operator itself. So an ordinary log only ever says *"this is what we currently claim happened."* It can never say *"and nobody changed it since."*

Nobody notices the difference — until a regulator, a court, an insurer, or a customer asks for **proof**. Then *"our system recorded it"* and *"here is proof it wasn't changed"* become two very different sentences. Only the second carries weight.

**sebbi.pro produces the second sentence — automatically, as a by-product of your system doing its normal work.**

---

## The chain, in one formula

```
seal(n) = SHA-256( seal(n−1) · timestamp · event · result · basis )
```

| Property | What it means |
|---|---|
| **Tamper-evident** | Each seal contains its predecessor. Alter history → every later seal fails, publicly. |
| **Gapless receipts** | Every decision gets a sequence number in the same transaction. Edited records break the chain; **missing** records break the sequence. |
| **Truncation-evident** | The tip is anchored per-write. Chop blocks off the end → the anchor breaks. |
| **Basis-sealed** | Not just *what* was decided — *what it rested on*: sources, versions, ruleset. Same block. |
| **Jurisdiction-tagged** | Every decision sealed with the regulatory frameworks that applied to it at that moment. |
| **Fast** | Score + decide + seal + respond inline, **~28 ms** median. |
| **Crash-safe** | WAL journaling, full-sync commits, single-lock seal path, no race window, daily backups. |

> **The one honest boundary, stated up front:** basis-sealing proves **what** a decision relied on — not that it was **correct**. Cryptography verifies integrity, never truth. Any product claiming to prove correctness is misdescribing what maths can do. We won't.

---

## The products — one chain underneath all of them

| | Product | What it does | Access |
|---|---|---|---|
| 🧠 | **Brain** | Instruction gate for AI. Blocks prompt injection, exfiltration, compliance-bypass, child-safety and destruction patterns — with unicode/obfuscation defences — and seals every decision + basis. Pure Python, runs on your machine. | **Free download** |
| ⚡ | **SonicBoom** | Decision engine. Any event scored in ~28ms: ALLOW / CHALLENGE / BLOCK, plain-English reasons, sealed before it replies. Per-user trust learned over time — lost 8× faster than earned, so burst attacks destroy their own standing. Hosted human-oversight challenge flow, itself sealed. | API key |
| 🔐 | **Delegation layer** | Signed authority tokens (who may approve, to what limit, until when — the grant itself sealed), provider-agnostic KYC result sealing (outcome provable, zero personal data held), and per-decision jurisdiction tagging. Article 14 human oversight as engineering. | API key |
| 🛡️ | **Sentinel** | Fraud pattern + velocity detection: credential stuffing, card testing, country-jump takeovers. Flags sealed as evidence. | API key |
| 👁️ | **Guardian** | Child-safety flags: grooming patterns (secrecy, isolation, channel-moving). Content never stored — only fingerprints. Every flag sealed for parents, platforms, authorities. | Platform |
| 📝 | **Post Notary** | Prove exact text existed on a date, unchanged. | **Free, no account** |
| 🆔 | **Identity Notary** | Prove a profile is the genuine original — kills impersonation. | **Free, no account** |
| 💷 | **Payment Notary** | Stop invoice/APP fraud. Seal real bank details once; payers verify a code before funds move. MISMATCH → payment stops. The check itself is sealed. | **Free, no account** |

**Privacy by design:** the notaries fingerprint content *locally*. Your content never leaves your device — only the 64-character hash is sealed. The KYC sealer keeps only the SHA-256 of the provider reference — never the document.

---

## The open standard — `ai.txt`

Like `robots.txt` for crawlers and `security.txt` for researchers — **`ai.txt`** is a public, machine-readable declaration of how your AI is governed: decision model, audit method, regulations designed toward, human override. Its companion **`comply.txt`** declares the rulebook every instruction is subject to.

Declarations are claims. **Sealing them into the chain makes them provable** — and their history tamper-evident.

```
  declaration  →  rulebook  →  enforcement
     ai.txt        comply.txt      brain.py
     "we claim"    "the rules"     "the code that proves it"
```

Publish yours at `/.well-known/ai.txt`. Read [ours](https://sebbi.pro/.well-known/ai.txt).

---

## The stack — how it all fits

```
  DECLARATION    ai.txt · comply.txt     what we claim, publicly
       │
  GATE           Brain                   instructions checked before the AI acts
       │
  DELEGATION     authority · identity ·  who may act, who they legally are,
                 jurisdiction            which rules governed the moment
       │
  DECISION       SonicBoom               every event: allow / challenge / block
       │
  DETECTION      Sentinel · Guardian     attack patterns · child-safety patterns
       │
  PUBLIC ACCESS  the Notaries            the same chain, free, for anyone
       │
       ▼
  ╔══════════════════════════════════════════════════════════════════╗
  ║  EVIDENCE     the hash chain                                      ║
  ║               everything above seals into here —                 ║
  ║               action + basis + receipt · gapless · anchored ·    ║
  ║               publicly verifiable · unalterable by anyone        ║
  ╚══════════════════════════════════════════════════════════════════╝
```

**Evidence accrues as a by-product of the system working.** Nobody remembers to log anything. Nobody compiles an audit file before an inspection. The proof exists because the system ran — equally trustworthy whether the operator is honest or not. Which is the only kind of trustworthy that counts.

---

## Integrate in minutes

```python
# ── Notary: seal anything, free, no key. Content stays on your machine. ──
import hashlib, requests
fp = hashlib.sha256(content.encode()).hexdigest()
requests.post("https://sebbi.pro/api/post/seal", json={"fingerprint": fp})
#   → { sealed, seal, block_index, code }   ← keep the code; anyone can verify it

# ── Decision engine: score + seal an event (API key) ──
requests.post("https://sebbi.pro/api/govern",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","action":"payment","amount":9000,
        "country":"UK","device_id":"d1","anomaly":0,"device_risk":0})
#   → ALLOW / CHALLENGE / BLOCK · reasons · jurisdiction tag · sealed hash · receipt_seq

# ── Delegated authority: grant sealed, enforcement deterministic ──
tok = requests.post("https://sebbi.pro/api/authority/issue",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","role":"payments_approver",
        "max_amount":5000,"ttl_hours":24}).json()["authority_token"]
#   include as "authority_token" in govern events — over-limit or expired
#   authority escalates the verdict with the reason sealed

# ── KYC result: outcome provable, zero personal data held ──
requests.post("https://sebbi.pro/api/identity/kyc-seal",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","provider":"onfido","verified":True,
        "reference":"chk_9f2"})
#   → only the SHA-256 of the reference is stored — never the document

# ── Brain: gate an instruction and seal its basis (free, local) ──
from brain import BrainGovernor
BrainGovernor().evaluate("approve payment to supplier 88", basis={
  "sources":["invoice_4471.pdf"], "source_versions":["sha256:ab12…"],
  "ruleset":"AI-TXT/1.0 + EU-AI-Act-2024/1689", "ruleset_version":"regmap-v7"})
```

Full reference → **[sebbi.pro/developers](https://sebbi.pro/developers)**

---

## What this evidences — stated precisely

A versioned, hash-sealed **regulation map** links each capability to the obligations it helps evidence: EU AI Act record-keeping, transparency & human-oversight (Articles 9, 12, 13, 14 — delegated-authority tokens directly supporting Article 14's attributable human oversight), UK Online Safety Act duty-of-care documentation, ICO Children's Code. Jurisdiction tagging extends this to the per-decision level: every sealed block records which frameworks applied at the moment of decision.

These tools help you **evidence** your obligations — tamper-evident, explainable, independently verifiable records of what your systems decided and why. **They do not, on their own, make you compliant. No software does. Anyone who says otherwise is selling you something.**

---

## Honest limits — because the whole product is honesty

- **Sealing proves integrity, not truth** — exact content, exact time, unchanged. Not that it was true or agreed to.
- **Basis-sealing proves what was relied on, not that it was right** — cryptography can't verify the real world.
- **Authority tokens prove the grant, not the wisdom** — who was empowered, to what limit, until when. Not that granting it was a good idea.
- **Jurisdiction tagging records applicable frameworks; it does not decide law** — courts do that. It is a versioned, sealed lookup — nothing grander, deliberately.
- **Brain's filter is a first line, not a wall** — known patterns caught; novel phrasing can pass. The guarantee is the sealed record.
- **Fingerprints match exact content** — a re-encoded copy or paraphrase won't match.
- **We evidence compliance; we don't confer it.**

*A vendor who states their limits is giving you the strongest available evidence of how they'll behave when it matters.*

---

## Deployment & pricing

- **Cloud** — a few lines against the hosted API. Notaries and Brain free forever.
- **Sovereign** — the whole engine inside your own network. Offline HMAC-signed 365-day licences, no phone-home, air-gap ready.
- **50p per active device / month.** Partners set their own pricing above the platform fee.

## Investors

The whitepaper carries a dedicated investor section — market timing (EU AI Act, August 2026), the metered per-device model, the moat, and the stage stated honestly: **[sebbi.pro/whitepaper](https://sebbi.pro/whitepaper)** · justin@monopcontent.com

---

<div align="center">

## Check us. Don't trust us.

*That's not a slogan. It's the design requirement — and the only standard by which an evidence layer should ever be judged.*

**[Verify the chain now →](https://sebbi.pro/api/verify-chain)**

<br>

```
  Built by Justin Dobson · Monop Content · Blyth, Northumberland, UK
  Solo-built, from scratch, on a phone —
  because the evidence layer wasn't going to build itself.
```

[LinkedIn](https://www.linkedin.com/in/justin-dobson-037721217) · [sebbi.pro](https://sebbi.pro)

</div>

<!--
Keywords: tamper-evident audit trail · AI governance · AI compliance evidence ·
EU AI Act record keeping · hash chain audit log · APP fraud prevention ·
invoice verification · prompt injection defence · AI decision audit ·
delegated authority tokens · KYC evidence sealing · jurisdiction tagging ·
ai.txt standard · comply.txt · cryptographic proof of action · immutable audit log ·
agentic AI governance · sovereign AI deployment · SonicBoom · Brain · Sentinel · Guardian
-->

```
