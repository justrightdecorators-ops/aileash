# Codebase — part 9 of 17

Contains:
- `tests/attack_continuity_1.py`
- `tests/attack_continuity_2.py`
- `tests/attack_continuity_3.py`
- `tests/attack_continuity_4.py`
- `AILeash-API-Reference-v6.4.2.md`
- `LICENCE`
- `README.md`
- `admin.html`
- `ai-standard.html`
- `ai-txt-kit.html`
- `aitxt-popup-live.html`


## `tests/attack_continuity_1.py`

437 lines, 22577 bytes

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

225 lines, 10403 bytes

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

113 lines, 5584 bytes

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
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=1))
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


## `admin.html`

212 lines, 12327 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>sebbi.pro - Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#fff;line-height:1.5}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
h1{font-size:22px;font-weight:800;margin-bottom:4px}h1 span{color:#c9a84c}
.sub{color:#8a90a6;font-size:13px;margin-bottom:20px}
/* login */
#login{max-width:360px;margin:80px auto;text-align:center}
#login input{width:100%;padding:14px;border-radius:10px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:16px;margin:12px 0}
button{background:#c9a84c;color:#0a0f1e;border:none;border-radius:10px;padding:13px 22px;font-weight:800;cursor:pointer;font-size:15px;width:100%}
button.small{width:auto;padding:8px 16px;font-size:13px}
.err{color:#ff7b6e;font-size:13px;margin-top:8px;min-height:18px}
/* dashboard */
#dash{display:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:16px}
.stat .big{font-size:26px;font-weight:800;color:#c9a84c}
.stat .lab{font-size:11px;color:#8a90a6;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
.stat.good .big{color:#7fe3b0}.stat.bad .big{color:#ff7b6e}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tab{background:#111a30;border:1px solid #232d4a;color:#8a90a6;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600}
.tab.on{background:#c9a84c;color:#0a0f1e;border-color:#c9a84c}
.panel{display:none}.panel.on{display:block}
.card{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:14px;margin-bottom:10px;font-size:14px}
.card .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.card .nm{font-weight:700}
.card .meta{color:#8a90a6;font-size:12px}
.badge{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:uppercase}
.badge.paid{background:#0d2018;color:#7fe3b0;border:1px solid #1fae79}
.badge.free{background:#1a1206;color:#c9a84c;border:1px solid #c9a84c}
.stripe-link{color:#7fe3b0;font-size:12px;text-decoration:none;font-family:monospace}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.mono{font-family:monospace;font-size:12px;color:#8a90a6;word-break:break-all}
.empty{color:#5a6178;text-align:center;padding:30px;font-size:14px}
a.ext{display:inline-block;background:#0d2018;border:1px solid #1fae79;color:#7fe3b0;padding:10px 16px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;margin-bottom:16px}
</style>
</head>
<body>
<div class="wrap">

  <div id="login">
    <h1>sebbi<span>.pro</span> admin</h1>
    <div class="sub">Private control panel</div>
    <input id="pw" type="password" placeholder="Admin password" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">Log in</button>
    <div class="err" id="loginerr"></div>
  </div>

  <div id="dash">
    <div class="bar">
      <div><h1>sebbi<span>.pro</span> admin</h1><div class="sub">Everything Stripe doesn't show you</div></div>
      <button class="small" onclick="logout()">Log out</button>
    </div>

    <a class="ext" href="https://dashboard.stripe.com" target="_blank" rel="noopener">Open Stripe dashboard for payments, revenue &amp; billing addresses &rarr;</a>

    <div class="stats" id="statgrid"></div>

    <div class="tabs">
      <div class="tab on" onclick="show('customers',this)">Customers &amp; leads</div>
      <div class="tab" onclick="show('contacts',this)">Contact messages</div>
      <div class="tab" onclick="show('referrals',this)">Referrals</div>
      <div class="tab" onclick="show('audit',this)">Audit records</div>
    </div>

    <div class="panel on" id="p-customers"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-contacts"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-referrals"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-audit">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <input id="auditkey" placeholder="Filter by API key (optional)" style="flex:1;min-width:180px;padding:10px;border-radius:8px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:13px">
        <button class="small" onclick="loadAudit()">Search</button>
        <button class="small" onclick="verifyChain()" style="background:#1fae79">Verify chain</button>
        <button class="small" onclick="exportAudit()" style="background:#0d2018;color:#7fe3b0;border:1px solid #1fae79">Export</button>
      </div>
      <div id="auditchain" style="font-family:monospace;font-size:12px;color:#7fe3b0;margin-bottom:12px"></div>
      <div id="auditlist"><div class="empty">Loading...</div></div>
    </div>
  </div>

</div>
<script>
var TOKEN="";
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function when(ts){if(!ts)return"";try{return new Date(ts*1000).toLocaleString()}catch(e){return""}}

async function doLogin(){
  var pw=document.getElementById("pw").value;
  document.getElementById("loginerr").textContent="";
  try{
    var r=await fetch("/admin/auth",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:pw})});
    var d=await r.json();
    if(d.token){TOKEN=d.token;document.getElementById("login").style.display="none";document.getElementById("dash").style.display="block";loadAll();}
    else if(d.error==="admin_disabled"){document.getElementById("loginerr").textContent="Admin password not set. Add ADMIN_PASSWORD in Railway variables.";}
    else if(d.error==="too_many_attempts"){document.getElementById("loginerr").textContent="Too many attempts. Wait a minute.";}
    else{document.getElementById("loginerr").textContent="Wrong password.";}
  }catch(e){document.getElementById("loginerr").textContent="Connection error.";}
}
function logout(){TOKEN="";document.getElementById("dash").style.display="none";document.getElementById("login").style.display="block";document.getElementById("pw").value="";}

async function api(path){
  var r=await fetch(path,{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:"{}"});
  return await r.json();
}

async function loadAll(){
  // stats
  try{
    var s=await api("/admin/stats");
    document.getElementById("statgrid").innerHTML=
      stat(s.total_keys,"Total signups")+
      stat(s.paid_keys,"Paying",  "good")+
      stat((s.total_keys||0)-(s.paid_keys||0),"Free / leads")+
      stat(s.audit_blocks,"Audit blocks")+
      stat(s.chain_valid?"OK":"BROKEN","Chain",s.chain_valid?"good":"bad");
  }catch(e){}
  loadCustomers();loadContacts();loadReferrals();loadAudit();
}
function stat(v,l,cls){return '<div class="stat '+(cls||"")+'"><div class="big">'+esc(v)+'</div><div class="lab">'+esc(l)+'</div></div>';}

async function loadCustomers(){
  try{
    var d=await api("/admin/keys");var ks=d.keys||[];
    if(!ks.length){document.getElementById("p-customers").innerHTML='<div class="empty">No signups yet.</div>';return;}
    var h="";
    ks.forEach(function(k){
      var paid=k.is_paid==1;
      h+='<div class="card"><div class="top"><span class="nm">'+esc(k.name||"(no name)")+' <span class="meta">'+esc(k.org||"")+'</span></span>'
        +'<span class="badge '+(paid?"paid":"free")+'">'+(paid?"paying":"free")+'</span></div>'
        +'<div class="meta">'+esc(k.email||"")+' &middot; '+esc(k.product||"")+' &middot; '+esc(k.devices||0)+' devices &middot; used '+esc(k.actions_used||0)+'/'+esc(k.free_quota||0)+'</div>'
        +'<div class="meta">Joined '+when(k.created)+'</div>'
        +(k.key?'<div class="mono">'+esc(k.key)+'</div>':'')
        +'</div>';
    });
    document.getElementById("p-customers").innerHTML=h;
  }catch(e){document.getElementById("p-customers").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadContacts(){
  try{
    var d=await api("/admin/contacts");var cs=d.contacts||[];
    if(!cs.length){document.getElementById("p-contacts").innerHTML='<div class="empty">No messages yet.</div>';return;}
    var h="";
    cs.forEach(function(c){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(c.name||"(no name)")+'</span><span class="meta">'+when(c.ts)+'</span></div>'
        +'<div class="meta">'+esc(c.email||"")+(c.phone?' &middot; '+esc(c.phone):'')+(c.org?' &middot; '+esc(c.org):'')+'</div>'
        +'<div style="margin-top:6px">'+esc(c.message||"")+'</div></div>';
    });
    document.getElementById("p-contacts").innerHTML=h;
  }catch(e){document.getElementById("p-contacts").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadReferrals(){
  try{
    var d=await api("/admin/referrals");var rs=d.referrals||[];
    if(!rs.length){document.getElementById("p-referrals").innerHTML='<div class="empty">No referrals yet.</div>';return;}
    var h="";
    rs.forEach(function(r){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(r.referrer_name||"(no name)")+' <span class="meta">'+esc(r.code||"")+'</span></span>'
        +'<span class="badge paid">&pound;'+((r.earnings_pence||0)/100).toFixed(2)+'</span></div>'
        +'<div class="meta">'+esc(r.referrer_email||"")+' &middot; '+esc(r.devices_referred||0)+' devices referred</div></div>';
    });
    document.getElementById("p-referrals").innerHTML=h;
  }catch(e){document.getElementById("p-referrals").innerHTML='<div class="empty">Could not load.</div>';}
}

var LAST_AUDIT=[];
async function loadAudit(){
  try{
    var key=document.getElementById("auditkey").value.trim();
    var r=await fetch("/admin/audit",{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:JSON.stringify({limit:500,api_key:key})});
    var d=await r.json();LAST_AUDIT=d.records||[];
    document.getElementById("auditchain").innerHTML=(d.chain_valid?"CHAIN INTACT":"CHAIN BROKEN")+" &middot; "+esc(d.chain_blocks)+" blocks &middot; tip "+esc(String(d.chain_tip||"").slice(0,24))+"...";
    if(!LAST_AUDIT.length){document.getElementById("auditlist").innerHTML='<div class="empty">No sealed records'+(key?" for that key":"")+' yet.</div>';return;}
    var h="";
    LAST_AUDIT.forEach(function(a){
      var dec=esc(a.decision||"");
      var col=dec==="BLOCK"?"#ff7b6e":dec==="CHALLENGE"?"#c9a84c":"#7fe3b0";
      h+='<div class="card"><div class="top"><span class="nm">#'+esc(a.seq)+' <span style="color:'+col+'">'+dec+'</span></span><span class="meta">'+when(a.ts)+'</span></div>'
        +'<div class="meta">user: '+esc(a.user_id||"-")+(a.score!==""?' &middot; score '+esc(a.score):'')+(a.reasons&&a.reasons.length?' &middot; '+esc(a.reasons.join(", ")):'')+'</div>'
        +'<div class="mono" style="margin-top:6px">seal: '+esc(String(a.audit_hash||"").slice(0,40))+'...</div>'
        +'<div class="mono">prev: '+esc(String(a.prev_hash||"").slice(0,40))+'...</div></div>';
    });
    document.getElementById("auditlist").innerHTML=h;
  }catch(e){document.getElementById("auditlist").innerHTML='<div class="empty">Could not load audit records.</div>';}
}
async function verifyChain(){
  try{
    var r=await fetch("/api/verify-chain");var d=await r.json();
    document.getElementById("auditchain").innerHTML=(d.valid?"VERIFIED - CHAIN INTACT":"WARNING - CHAIN BROKEN")+" &middot; "+esc(d.blocks)+" blocks &middot; "+esc(d.message||"");
  }catch(e){}
}
function exportAudit(){
  var blob=new Blob([JSON.stringify(LAST_AUDIT,null,2)],{type:"application/json"});
  var url=URL.createObjectURL(blob);var a=document.createElement("a");
  a.href=url;a.download="sebbi-audit-export-"+Date.now()+".json";a.click();URL.revokeObjectURL(url);
}
function show(name,el){
  document.querySelectorAll(".tab").forEach(function(t){t.className="tab";});el.className="tab on";
  document.querySelectorAll(".panel").forEach(function(p){p.className="panel";});
  document.getElementById("p-"+name).className="panel on";
}
</script>
</body>
</html>

```


## `ai-standard.html`

97 lines, 4847 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0f1e">
<title>ai.txt - Free Download</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#e8e8f0;min-height:100vh;display:flex;flex-direction:column}
nav{border-bottom:1px solid #1e2a45;padding:16px 20px}
nav a{color:#c9a84c;text-decoration:none;font-family:monospace;font-size:14px}
.wrap{flex:1;display:flex;align-items:center;justify-content:center;padding:30px 20px}
.card{max-width:560px;width:100%;background:#0d1428;border:1px solid #1e2a45;border-radius:16px;padding:36px 28px;text-align:center}
h1{font-size:32px;font-weight:800;margin-bottom:14px;line-height:1.15}
h1 span{color:#c9a84c}
p{color:#8a90a6;font-size:15px;line-height:1.7;margin-bottom:14px}
p b{color:#e8e8f0}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;width:100%;background:#c9a84c;color:#0a0f1e;padding:18px;border-radius:10px;font-weight:800;font-size:17px;border:none;cursor:pointer;font-family:inherit;margin:20px 0 10px}
.sub{font-family:monospace;font-size:12px;color:#7fe3b0;margin-bottom:24px}
.steps{text-align:left;background:#0b1226;border:1px solid #1e2a45;border-radius:10px;padding:18px 20px;margin-top:8px}
.steps li{color:#8a90a6;font-size:14px;margin:10px 0 10px 6px;line-height:1.6}
.steps li b{color:#c9a84c}
.back{margin-top:22px}
.back a{color:#c9a84c;text-decoration:none;font-size:14px;font-weight:600}
footer{border-top:1px solid #1e2a45;padding:20px;text-align:center;color:#5a6178;font-size:12px}
footer a{color:#c9a84c;text-decoration:none}
</style>
</head>
<body>
<nav><a href="/">&larr; AILeash</a></nav>
<div class="wrap">
  <div class="card">
    <h1>Download <span>ai.txt</span> &mdash; free</h1>
    <div class="sub">NO KEY &middot; NO ACCOUNT &middot; NO COST</div>
    <p>ai.txt is the free, open standard for declaring how your AI is governed. Download the file, and it shows your system exactly what it needs to become compliant.</p>
    <button class="btn" onclick="downloadIt()">&#8681; Download ai.txt free</button>
    <ul class="steps">
      <li><b>1.</b> Tap download &mdash; the file saves as ai.txt</li>
      <li><b>2.</b> Fill in your details, put it on your domain at yourdomain.com/ai.txt</li>
      <li><b>3.</b> Want it verified and provable? <b><a href="/" style="color:#c9a84c">Come back to AILeash</a></b> to seal it into a tamper-evident chain.</li>
    </ul>
    <div class="back"><a href="/ai.txt">See the live ai.txt &rarr;</a></div>
  </div>
</div>
<footer>ai.txt is a free, open standard by <a href="/">Monop Content</a> &middot; Blyth, UK &middot; <a href="/ai.txt">reference</a></footer>
<script>
var AITXT = [
"# ============================================================================",
"# ai.txt - AI Governance Declaration  (AI-TXT/1.0)",
"# A free, open standard. Copy this to the root of your domain as /ai.txt",
"# Replace the values below with your own. Delete any line that does not apply.",
"# No key, no account, no permission, no cost. Just publish it.",
"# See it live: https://sebbi.pro/ai.txt",
"# ============================================================================",
"",
"Standard: AI-TXT/1.0",
"Operator: YOUR COMPANY NAME",
"Operator-Location: YOUR CITY, COUNTRY",
"Contact: you@yourdomain.com",
"Last-Updated: 2026-01-01",
"",
"# --- How your AI makes decisions ---",
"Decision-Model: describe it (deterministic rules / ML model / human-in-loop)",
"Decision-Outcomes: ALLOW, REVIEW, BLOCK",
"Human-Override: yes / no",
"Plain-Language-Reasons: yes / no",
"",
"# --- Your audit record (how you prove what happened) ---",
"Audit-Chain: describe it (SHA-256 hash chain / signed logs / none)",
"Chain-Property: tamper-evident / tamper-resistant / none",
"Verify-Endpoint: https://yourdomain.com/your-verify-url",
"",
"# --- Regulations you are designing towards ---",
"Regulation: EU AI Act 2024/1689",
"Regulation: UK Online Safety Act 2023",
"",
"# --- Optional: public status surfaces ---",
"Live-Status: https://yourdomain.com/health",
"Whitepaper: https://yourdomain.com/whitepaper",
"",
"# ============================================================================",
"# ai.txt is a free, open standard. Publish yours, share it, build on it.",
"# ============================================================================"
].join("\n");
function downloadIt(){
  var blob = new Blob([AITXT], {type:"text/plain"});
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url; a.download = "ai.txt";
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
</script>
</body>
</html>

```


## `ai-txt-kit.html`

86 lines, 6554 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0f1e">
<title>ai.txt Starter Kit &mdash; publish AI governance free in 5 minutes</title>
<meta name="description" content="Publish an ai.txt on your own domain, free. Copy the template, add the badge, make it provable. No key, no account.">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#e8e8f0;line-height:1.6}
.mono{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace}
nav{position:sticky;top:0;z-index:10;background:rgba(10,15,30,.94);backdrop-filter:blur(10px);border-bottom:1px solid #1e2a45;padding:0 20px;height:54px;display:flex;align-items:center;justify-content:space-between}
nav a.logo{display:flex;align-items:center;gap:8px;color:#c9a84c;text-decoration:none;font-family:"JetBrains Mono",monospace;font-size:13px}
nav .links a{color:#8a90a6;text-decoration:none;font-size:13px;margin-left:16px}
.wrap{max-width:760px;margin:0 auto;padding:44px 20px 90px}
.eyebrow{font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#c9a84c;margin-bottom:12px}
h1{font-size:34px;font-weight:800;letter-spacing:-.02em;line-height:1.1;margin-bottom:14px}
h1 span{color:#c9a84c}
.lede{color:#8a90a6;font-size:16px;margin-bottom:8px}
.free{display:inline-block;background:rgba(0,229,160,.1);border:1px solid #00b87d;color:#7fe3b0;font-family:"JetBrains Mono",monospace;font-size:12px;padding:5px 12px;border-radius:5px;margin:14px 0 30px}
h2{font-size:20px;font-weight:700;margin:40px 0 8px;padding-top:26px;border-top:1px solid #1e2a45}
.step-n{font-family:"JetBrains Mono",monospace;color:#c9a84c;font-size:13px}
p{color:#8a90a6;margin-bottom:14px}
p b{color:#e8e8f0}
.box{background:#0b1226;border:1px solid #1e2a45;border-radius:10px;padding:18px;margin:16px 0;font-family:"JetBrains Mono",monospace;font-size:12.5px;color:#7fe3b0;white-space:pre-wrap;word-break:break-word;line-height:1.8;overflow-x:auto}
.btn{display:inline-flex;align-items:center;gap:8px;background:#c9a84c;color:#0a0f1e;padding:12px 22px;border-radius:8px;font-weight:800;font-size:14px;text-decoration:none;border:none;cursor:pointer;font-family:inherit}
.btn.ghost{background:transparent;border:1px solid #2a3350;color:#e8e8f0}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.badge-demo{display:inline-flex;align-items:center;gap:8px;background:#111a30;border:1px solid #c9a84c;border-radius:8px;padding:8px 14px;font-family:"JetBrains Mono",monospace;font-size:12px;color:#c9a84c;text-decoration:none}
.badge-demo svg{flex-shrink:0}
.onramp{background:linear-gradient(135deg,rgba(0,229,160,.06),rgba(201,168,76,.05));border:1px solid #00b87d;border-radius:12px;padding:24px;margin-top:30px}
.onramp h3{color:#7fe3b0;font-size:16px;margin-bottom:8px}
.onramp p{color:#a9b0c4}
.copied{color:#7fe3b0;font-size:12px;margin-left:10px;opacity:0;transition:opacity .2s}
.copied.show{opacity:1}
footer{border-top:1px solid #1e2a45;padding:26px 20px;text-align:center;color:#5a6178;font-size:12px}
footer a{color:#c9a84c;text-decoration:none}
</style>
</head>
<body>
<nav>
  <a class="logo" href="/"><svg width="18" height="18" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/></svg>AILeash</a>
  <div class="links"><a href="/ai.txt">Spec</a><a href="/whitepaper">Whitepaper</a></div>
</nav>
<div class="wrap">
  <div class="eyebrow">// ai.txt starter kit</div>
  <h1>Publish AI governance on your own site. <span>Free.</span></h1>
  <p class="lede">ai.txt is the robots.txt of AI governance: one small file at your domain root that declares how your AI is governed and where anyone can verify it. Here is everything you need to publish one in about five minutes.</p>
  <div class="free">FREE STANDARD &middot; NO KEY &middot; NO ACCOUNT &middot; NO PERMISSION</div>

  <h2><span class="step-n">01 /</span> Grab the template</h2>
  <p>A ready-to-fill ai.txt with every line commented. Download it, or read the live example on our own domain.</p>
  <div class="btnrow">
    <a class="btn" href="/ai-txt-template.txt" download="ai.txt">&#8681; Download template</a>
    <a class="btn ghost" href="/ai.txt" target="_blank">Read a live example</a>
  </div>

  <h2><span class="step-n">02 /</span> Fill it in and publish</h2>
  <p>Replace the example values with your own facts. <b>Delete any line you cannot back with a real verify endpoint</b> &mdash; an honest short ai.txt beats an aspirational long one. Then upload it to the root of your domain so it lives at:</p>
  <div class="box">https://yourdomain.com/ai.txt</div>
  <p>That is the whole spec. One file, at the root, readable by anyone &mdash; a regulator, a partner, or another machine deciding whether to trust you.</p>

  <h2><span class="step-n">03 /</span> Add the badge</h2>
  <p>Show visitors and crawlers that you have declared your AI governance. Copy this HTML onto your site &mdash; it renders a small badge linking to your ai.txt:</p>
  <p>Preview:</p>
  <a class="badge-demo" href="/ai.txt"><svg width="14" height="14" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="3" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.4" fill="#c9a84c"/></svg>AI-Governed &middot; ai.txt</a>
  <div class="box" id="badge">&lt;a href="/ai.txt" style="display:inline-flex;align-items:center;gap:6px;font-family:monospace;font-size:12px;color:#c9a84c;text-decoration:none;border:1px solid #c9a84c;border-radius:6px;padding:6px 10px"&gt;AI-Governed &middot; ai.txt&lt;/a&gt;</div>
  <button class="btn ghost" onclick="copyBadge()">Copy badge HTML<span class="copied" id="cp">copied</span></button>

</div>
</div>
<footer>
  ai.txt (AI-TXT/1.0) is a free, open standard by <a href="/">Monop Content</a> &middot; Blyth, UK &middot; <a href="/ai.txt">spec</a> &middot; <a href="/comply.txt">comply.txt</a>
</footer>
<script>
function copyBadge(){
  var t=document.getElementById('badge').textContent;
  navigator.clipboard.writeText(t).then(function(){
    var c=document.getElementById('cp');c.classList.add('show');setTimeout(function(){c.classList.remove('show')},1500);
  });
}
</script>
</body>
</html>

```


## `aitxt-popup-live.html`

165 lines, 7279 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ai.txt Live Compliance Widget — Preview</title>
<style>
  body{margin:0;background:#e8e6df;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;min-height:100vh;}
  .demo-note{position:fixed;top:16px;left:16px;right:16px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;font-size:13px;color:#555;max-width:560px;margin:0 auto;text-align:center;z-index:2;}
</style>
</head>
<body>
<div class="demo-note">This page has no ai.txt, so the badge will honestly say "not found." Click it to see the real check running live.</div>

<!-- ============================================================
     THE DELIVERABLE: one script tag. Paste into any site.
     On load, it actually fetches /ai.txt from that same domain
     and reports the true result — nothing hardcoded, nothing faked.
============================================================= -->
<script>
(function(){
  var CSS = `
    #aitxt-badge{
      position:fixed;bottom:20px;right:20px;z-index:999998;
      background:#0a0f1e;color:#8b93ac;border:1px solid #232c48;
      font-family:'SF Mono','JetBrains Mono',Consolas,monospace;
      font-size:12px;padding:10px 16px;border-radius:999px;cursor:pointer;
      box-shadow:0 4px 18px rgba(0,0,0,.25);display:flex;align-items:center;gap:8px;
      transition:transform .15s ease;
    }
    #aitxt-badge:hover{transform:translateY(-2px);}
    #aitxt-badge .dot{width:7px;height:7px;border-radius:50%;background:#8b93ac;flex-shrink:0;transition:background .2s ease;}
    #aitxt-badge .dot.ok{background:#7fe3b0;}
    #aitxt-badge .dot.warn{background:#ff8a80;}
    #aitxt-badge .dot.checking{background:#c9a84c;animation:aitxt-pulse 1s ease-in-out infinite;}
    @keyframes aitxt-pulse{50%{opacity:.3;}}
    #aitxt-overlay{
      position:fixed;inset:0;background:rgba(10,15,30,.6);z-index:999999;
      display:none;align-items:center;justify-content:center;padding:20px;
    }
    #aitxt-overlay.open{display:flex;}
    #aitxt-modal{
      background:#10182e;border:1px solid #232c48;border-radius:12px;
      max-width:420px;width:100%;color:#e7ebf5;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
      overflow:hidden;
    }
    #aitxt-modal .aitxt-head{padding:20px 22px 0;}
    #aitxt-modal .aitxt-eyebrow{
      font-family:'SF Mono',Consolas,monospace;font-size:11px;letter-spacing:.1em;
      text-transform:uppercase;color:#c9a84c;margin-bottom:10px;
    }
    #aitxt-modal h3{margin:0 0 8px;font-size:19px;line-height:1.3;}
    #aitxt-modal p{margin:0 0 18px;font-size:13.5px;line-height:1.55;color:#8b93ac;}
    #aitxt-modal .aitxt-body{padding:0 22px 22px;}
    #aitxt-modal .aitxt-status{
      display:flex;align-items:center;gap:8px;padding:12px 14px;
      background:#161f38;border:1px solid #232c48;border-radius:8px;margin-bottom:16px;
      font-family:'SF Mono',Consolas,monospace;font-size:12px;
    }
    #aitxt-modal .aitxt-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
    #aitxt-modal .aitxt-dot.ok{background:#7fe3b0;}
    #aitxt-modal .aitxt-dot.warn{background:#ff8a80;}
    #aitxt-modal .aitxt-dot.checking{background:#c9a84c;animation:aitxt-pulse 1s ease-in-out infinite;}
    #aitxt-modal .aitxt-status.ok span.label{color:#7fe3b0;}
    #aitxt-modal .aitxt-status.warn span.label{color:#ff8a80;}
    #aitxt-modal .aitxt-status.checking span.label{color:#c9a84c;}
    #aitxt-modal a.aitxt-cta{
      display:block;text-align:center;background:#c9a84c;color:#0a0f1e;
      font-weight:600;font-size:14px;padding:11px;border-radius:7px;
      text-decoration:none;margin-bottom:10px;
    }
    #aitxt-modal button.aitxt-close{
      display:block;width:100%;background:transparent;border:1px solid #232c48;
      color:#8b93ac;font-size:13px;padding:10px;border-radius:7px;cursor:pointer;
    }
  `;
  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  var badge = document.createElement('div');
  badge.id = 'aitxt-badge';
  badge.innerHTML = '<span class="dot checking"></span><span class="label">Checking AI governance…</span>';
  document.body.appendChild(badge);

  var overlay = document.createElement('div');
  overlay.id = 'aitxt-overlay';
  overlay.innerHTML = `
    <div id="aitxt-modal">
      <div class="aitxt-head">
        <div class="aitxt-eyebrow">ai.txt · sebbi.pro</div>
        <h3>AI governance declaration</h3>
        <p>ai.txt is a plain-text file — like robots.txt — that states how this site's AI systems are governed. This check looked for it at the domain root, live, just now.</p>
      </div>
      <div class="aitxt-body">
        <div class="aitxt-status checking" id="aitxt-modal-status">
          <span class="aitxt-dot checking"></span>
          <span class="label">Checking…</span>
        </div>
        <a class="aitxt-cta" href="https://sebbi.pro" target="_blank" id="aitxt-cta">Generate ai.txt — free</a>
        <button class="aitxt-close">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  var badgeDot = badge.querySelector('.dot');
  var badgeLabel = badge.querySelector('.label');
  var modalStatus = overlay.querySelector('#aitxt-modal-status');
  var modalDot = modalStatus.querySelector('.aitxt-dot');
  var modalLabel = modalStatus.querySelector('.label');
  var cta = overlay.querySelector('#aitxt-cta');

  function setState(state, text, modalText){
    badgeDot.className = 'dot ' + state;
    badgeLabel.textContent = text;
    modalStatus.className = 'aitxt-status ' + state;
    modalDot.className = 'aitxt-dot ' + state;
    modalLabel.textContent = modalText;
    if(state === 'ok'){
      cta.textContent = 'View declaration';
    } else {
      cta.textContent = 'Generate ai.txt — free';
    }
  }

  // The real check — looks for ai.txt on this exact page's own domain.
  // Checks the standard /.well-known/ai.txt location first, then falls
  // back to /ai.txt at root. Same-origin, no backend needed, and it
  // can't be faked by hardcoding a result: it either finds the file or
  // it doesn't.
  function checkPath(path){
    return fetch(path, {method:'GET', cache:'no-store'})
      .then(function(res){ return res.ok ? path : null; })
      .catch(function(){ return null; });
  }

  Promise.all([
    checkPath('/.well-known/ai.txt'),
    checkPath('/ai.txt')
  ]).then(function(results){
    var foundAt = results.find(function(p){ return p !== null; });
    if(foundAt){
      setState('ok', 'AI governance declared', 'ai.txt found at ' + foundAt);
    } else {
      setState('warn', 'No ai.txt found', 'No ai.txt file found at this domain');
    }
  });

  badge.addEventListener('click', function(){ overlay.classList.add('open'); });
  overlay.addEventListener('click', function(e){
    if(e.target === overlay) overlay.classList.remove('open');
  });
  overlay.querySelector('.aitxt-close').addEventListener('click', function(){
    overlay.classList.remove('open');
  });
})();
</script>
<!-- ============================================================
     END OF SNIPPET
============================================================= -->

</body>
</html>

```
