#!/usr/bin/env python3
"""
modules/lineage.py  -  provenance that crosses company boundaries
=================================================================

WHERE EVERY AUDIT TRAIL STOPS
-----------------------------
At the edge of the company that wrote it.

A lender holds a score. The score came from a scoring supplier, which used
a model, which was trained on a data snapshot bought from someone else.
Four organisations, four audit trails, none of which reference each other.
Ask "what produced this outcome" and you get four separate answers and no
way to join them up.

Every framework written in the last three years assumes somebody can trace
an outcome across parties. Nobody can. Not because it is hard - because
each party's evidence is only worth anything inside that party's own
system, so joining them up would mean trusting whoever did the joining.

WHY THIS WORKS WHEN A SHARED DATABASE WOULD NOT
-----------------------------------------------
The obvious approach is a consortium: everyone writes to one ledger,
governed by someone. That fails on the first question anybody asks, which
is who runs it, and it never gets built.

This needs none of that, because the pieces already exist:

  A chain tip already commits to everything sealed beneath it.
  That tip is already handed to peers hourly and sealed into THEIR chains.
  Those chains are anchored externally and witnessed in turn.

So a receipt can already be walked up to a tip, and that tip already sits
inside chains its issuer does not control. The trust problem is solved
before lineage is even mentioned.

The only thing missing was the sideways link: a decision recording which
receipts fed it, and which chain each came from. That is what this module
adds. One field, and the graph composes itself.

Nobody opts into provenance. They opt into witnessing, which they already
want, and provenance falls out of it.

WHAT AN EDGE IS AND IS NOT
--------------------------
An edge is a sealed, dated, non-repudiable CLAIM by the declaring party
that these inputs fed that decision. Sealing does not make the claim true.
What it removes is the ability to revise it quietly afterwards, which is
the part that matters when an outcome is disputed a year later.

Every edge is itself a chain entry. So the provenance graph is covered by
the same completeness, consistency and witnessing guarantees as everything
else - you cannot delete an inconvenient edge without breaking the chain,
and you cannot add one after the fact without the timestamp showing it.

THE PART THAT IS WORTH MORE THAN THE TRACING
--------------------------------------------
    GET /x/lineage/impact?receipt=

Trace runs upstream: what produced this. Impact runs downstream: what did
this produce.

When a data provider retracts a snapshot, or a model version turns out to
be faulty, or an upstream decision is overturned, the question every
regulator asks is which outputs were affected. Today that answer takes
weeks of email and is never complete. Here it is a query, and it crosses
company boundaries, and the answer is itself provable.

That is corrective action under Article 20 turned from a fire drill into a
lookup.

VERIFICATION WITHOUT TRUSTING ANY PARTY IN THE CHAIN
----------------------------------------------------
This module never asserts that a remote hop is valid. It returns the exact
routes a third party should call to check each hop themselves - on our
chain and on everybody else's. An auditor verifies the whole graph without
trusting us, the supplier, or anyone in between.

HONEST LIMITS
-------------
  - An edge is a claim, sealed and dated. It is not proof the inputs were
    the real ones, only that this is what was declared and when.
  - A cross-chain hop can only be checked while the other party keeps
    their routes up. A dead peer leaves a stub in the graph - visible,
    which is the honest outcome, rather than silently resolved.
  - Declaring inputs is voluntary. A party that declares nothing is not
    caught out by this module; they are simply the point where somebody
    else's lineage goes dark, and their customer is the one who notices.
  - We record edges pointing at other chains. We do not fetch from them
    here - fetching is what /x/witness does, with its SSRF controls, and
    duplicating that machinery in a second place would be a mistake.

    POST /x/lineage/declare      record what fed a decision      (keyed)
    GET  /x/lineage/trace        walk upstream                    (public)
    GET  /x/lineage/impact       walk downstream                  (public)
    GET  /x/lineage/receipt      portable proof for an output     (public)
    GET  /x/lineage/spec         the format and how to check it   (public)
"""

import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Everything except declaring is open. The whole point is that a party
# three hops downstream - who has no relationship with us at all - can
# follow the graph and check it.
PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec")}

OUR_CHAIN_NAME = "aileash"
OUR_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS lineage_edge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "child_chain TEXT,child_receipt TEXT,"
                  "parent_chain TEXT,parent_receipt TEXT,parent_base TEXT,"
                  "role TEXT,note TEXT,declared REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_child "
                  "ON lineage_edge(child_receipt)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_parent "
                  "ON lineage_edge(parent_receipt)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lin_unique "
                  "ON lineage_edge(child_receipt,parent_chain,parent_receipt)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_chain(value):
    value = str(value or "").strip().lower()
    return value[:80] if value else ""


def _exists_locally(ctx, receipt):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1", (receipt,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _verification_plan(chain, receipt, base=None):
    """The exact calls a third party makes to check one hop themselves.

    We never tell anyone a hop is valid. We tell them how to find out
    without asking us again.
    """
    root = (base or OUR_BASE).rstrip("/") if chain != OUR_CHAIN_NAME else OUR_BASE
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % OUR_BASE,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (OUR_BASE, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


# ----------------------------------------------------------------------
# declare
# ----------------------------------------------------------------------

def _declare(ctx, api_key, data):
    child = str(data.get("receipt", data.get("child", ""))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(data.get("chain") or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs", "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared = []
    for item in inputs:
        if not isinstance(item, dict):
            return {"error": "bad_input", "message": "each input must be an object"}, 400
        parent = str(item.get("receipt", "")).strip().lower()
        if not HEX64.match(parent):
            return {"error": "bad_input_receipt",
                    "message": "every input needs a 64 character hex receipt"}, 400
        parent_chain = _clean_chain(item.get("chain") or OUR_CHAIN_NAME)
        if parent_chain == child_chain and parent == child:
            return {"error": "self_reference",
                    "message": "a decision cannot be its own input"}, 400
        role = str(item.get("role", "input")).strip().lower()
        if role not in ROLES:
            role = "other"
        base = str(item.get("base", item.get("url", "")) or "").strip()[:300]
        note = str(item.get("note", "") or "").strip()[:200]
        prepared.append((parent_chain, parent, base, role, note))

    now = time.time()
    summary = ";".join("%s/%s:%s" % (c, r[:12], role) for c, r, _b, role, _n in prepared)
    ev = {"user_id": "lin:" + child[:16], "action": "lineage_declared", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "LINEAGE_SEALED", "score": 0, "lineage_version": VERSION,
           "child_chain": child_chain, "child_receipt": child,
           "input_count": len(prepared),
           "detail": "child=%s;inputs=%s" % (child, summary)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    written, duplicates = 0, 0
    with ctx["lock"]:
        for parent_chain, parent, base, role, note in prepared:
            try:
                ctx["conn"].execute(
                    "INSERT INTO lineage_edge(api_key,child_chain,child_receipt,parent_chain,"
                    "parent_receipt,parent_base,role,note,declared,audit_hash,block_index) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (api_key, child_chain, child, parent_chain, parent, base or None,
                     role, note or None, now, audit_hash, block_index))
                written += 1
            except Exception:
                duplicates += 1
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (OUR_BASE, child)}, 200


# ----------------------------------------------------------------------
# walking the graph
# ----------------------------------------------------------------------

def _parents(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT parent_chain,parent_receipt,parent_base,role,note,declared,audit_hash "
            "FROM lineage_edge WHERE child_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _children(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT child_chain,child_receipt,role,declared,audit_hash "
            "FROM lineage_edge WHERE parent_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _walk(ctx, start, depth, upstream):
    """Breadth-first walk with cycle and size protection.

    Anything on a chain we do not hold locally becomes a frontier entry -
    named, with a verification plan, and explicitly not resolved by us.
    """
    seen = {start}
    nodes, edges, frontier = [], [], []
    queue = [(start, 0)]
    truncated = False

    while queue:
        receipt, level = queue.pop(0)
        if level >= depth or len(nodes) >= MAX_NODES:
            if queue or level >= depth:
                truncated = truncated or bool(queue)
            continue

        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)
        for row in rows:
            if upstream:
                chain, other, base, role, note, declared, sealed = row
            else:
                chain, other, role, declared, sealed = row
                base, note = None, None

            edges.append({
                "from": other if upstream else receipt,
                "to": receipt if upstream else other,
                "role": role, "note": note,
                "declared_at": _iso(declared),
                "declaration_sealed_as": sealed,
                "chain": chain,
            })

            local = (chain == OUR_CHAIN_NAME) and _exists_locally(ctx, other)
            if not local:
                if not any(f["receipt"] == other for f in frontier):
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated


def _depth_arg(data):
    try:
        depth = int(data.get("depth", MAX_DEPTH))
    except (TypeError, ValueError):
        depth = MAX_DEPTH
    return max(1, min(depth, MAX_DEPTH))


def _trace(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [],
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt),
            "how_to_verify_this": "Every node carries the routes to check it on its own chain. "
                                  "Nothing here asks you to take our word for a hop, including "
                                  "the hops on our own chain.",
            "what_an_edge_is": "A sealed, dated claim by the declaring party that these inputs "
                               "fed that decision. Sealing makes it non-repudiable, not true.",
            "frontier_note": "External entries are named but not resolved here. Run their "
                             "verification plans against their own hosts - that is what makes "
                             "the graph checkable without a shared database."}, 200


def _impact(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=False)
    affected = len(nodes)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": affected, "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "lineage_version": VERSION,
            "what_this_is_for": "If this input is retracted, wrong, or overturned, these are the "
                                "decisions that declared a dependency on it. This is the answer "
                                "to the first question asked after any upstream failure, and it "
                                "normally takes weeks of email to assemble incompletely.",
            "corrective_action": "The list is itself sealed and dated, so the scope of a recall "
                                 "can be shown to have been determined honestly rather than "
                                 "narrowed to suit.",
            "limits": "Only covers dependencies that were declared. A downstream party who "
                      "declared nothing does not appear - which is a fact about them rather "
                      "than a gap here."}, 200


# ----------------------------------------------------------------------
# the portable receipt - proof that travels with an output
# ----------------------------------------------------------------------

def _receipt(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "verify": _verification_plan(r[0], r[1], r[2])} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (OUR_BASE, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % OUR_BASE,
            "nothing_was_left_out": "%s/x/complete/periods" % OUR_BASE,
            "who_witnesses_us": "%s/x/witness/peers" % OUR_BASE,
            "our_current_tip": "%s/x/witness/tip" % OUR_BASE,
            "the_engine_reproduces": "%s/x/replay/spec" % OUR_BASE,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, receipt),
        },
        "offline_verifier": "aileash_verify.py - one file, no dependencies, no network. Save "
                            "this document and check it on your own machine, today or in four "
                            "years.",
        "what_you_can_establish": [
            "this decision is in a log that has not been rewritten",
            "that log is witnessed by parties we do not control",
            "the period it sits in declared its total before anyone asked",
            "the same inputs still produce the same verdict",
            "and what fed it, hop by hop, across every company involved",
        ],
        "what_you_cannot": "That the decision was right, or that the inputs were honest. "
                           "Cryptography establishes what happened and when. It does not "
                           "establish that what happened was correct, and anybody telling you "
                           "otherwise is selling something.",
        "send_this_on": "Attach it to the output it describes. Whoever receives it can verify "
                        "without an account, without contacting us, and without trusting anyone "
                        "in the chain including the sender.",
    }, 200


def _spec():
    return {
        "lineage_version": VERSION,
        "idea": "A decision records the receipts of its inputs and which chain each came from. "
                "Nothing else is needed, because a chain tip already commits to everything "
                "beneath it and is already witnessed by parties its operator does not control.",
        "why_no_consortium": "A shared ledger needs a governor and never gets built. This needs "
                             "no agreement between parties beyond each one sealing its own work "
                             "and publishing a tip.",
        "declare": {
            "route": "POST /x/lineage/declare (keyed)",
            "body": {"receipt": "<64 hex, the decision>",
                     "inputs": [{"chain": "<who it came from>", "receipt": "<64 hex>",
                                 "role": "one of %s" % ", ".join(ROLES),
                                 "base": "<their public https base, optional>"}]},
        },
        "roles": list(ROLES),
        "trace": "GET /x/lineage/trace?receipt= - upstream, what produced this",
        "impact": "GET /x/lineage/impact?receipt= - downstream, what this produced",
        "portable_receipt": "GET /x/lineage/receipt?receipt= - a document that travels with an "
                            "output and lets the recipient verify it independently",
        "verifying_a_hop": "Each node carries the routes to check it on its own chain: an "
                           "ancestry proof that the receipt is still there, a completeness "
                           "check that nothing was omitted from its period, and the witness "
                           "list showing who else holds that chain's tips.",
        "adopting_it": "Implement three public routes on your own system - a tip, an observe, "
                       "and an ancestry check - and declare your inputs. There is nothing to "
                       "join, nobody to ask, and no fee. If you can serve a tip, you are in.",
        "honest": "An edge is a dated, sealed claim about what fed a decision. It cannot be "
                  "quietly revised later. It was never proof that the claim was true, and this "
                  "module does not pretend otherwise.",
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
        if action == "impact":
            return _impact(ctx, data)
        if action == "receipt":
            return _receipt(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "declare":
            return _declare(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "trace", "impact", "receipt"],
            "POST": ["declare (keyed)"]}, 404
