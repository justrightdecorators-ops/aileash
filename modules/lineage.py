import re
import sqlite3
import time
from datetime import datetime, timezone

VERSION = "1.4"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec"), ("GET", "status"), ("GET", "health")}

OUR_CHAIN_NAME = "aileash"
DEFAULT_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
DEFAULT_DEPTH = 3
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")
ACTIONS = ("status", "health", "spec", "trace", "impact", "receipt", "declare")

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


def _get_base_url(ctx):
    if isinstance(ctx, dict):
        base = ctx.get("base_url") or (ctx.get("config") or {}).get("base_url")
        if base:
            return str(base).rstrip("/")
    return DEFAULT_BASE


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_chain(value):
    value = str(value or "").strip().lower()
    return value[:80] if value else ""


def _one(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _depth_arg(data):
    raw = _one((data or {}).get("depth", DEFAULT_DEPTH))
    try:
        depth = int(str(raw).strip())
    except Exception:
        depth = DEFAULT_DEPTH
    if depth < 1:
        depth = 1
    if depth > MAX_DEPTH:
        depth = MAX_DEPTH
    return depth


def _receipt_arg(data):
    return str(_one((data or {}).get("receipt", ""))).strip().lower()


def _exists_locally(ctx, receipt):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    return bool(row)


def _parents(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT parent_chain,parent_receipt,parent_base,role,note,declared,audit_hash "
            "FROM lineage_edge WHERE child_receipt=? ORDER BY id", (receipt,)).fetchall()


def _children(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT child_chain,child_receipt,role,declared,audit_hash "
            "FROM lineage_edge WHERE parent_receipt=? ORDER BY id", (receipt,)).fetchall()


def _verification_plan(chain, receipt, base=None, our_base=DEFAULT_BASE):
    root = (base or our_base).rstrip("/") if chain != OUR_CHAIN_NAME else our_base
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % our_base,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (our_base, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


def _declare(ctx, api_key, data):
    our_base = _get_base_url(ctx)
    child = str(_one(data.get("receipt", data.get("child", "")))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(_one(data.get("chain")) or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs",
                "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared, pairs = [], set()
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
        if (parent_chain, parent) in pairs:
            return {"error": "duplicate_input",
                    "message": "the same chain and receipt appears twice in one declaration"}, 400
        pairs.add((parent_chain, parent))
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

    try:
        audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)
    except Exception as exc:
        return {"error": "seal_failed", "message": str(exc),
                "what_happened": "Nothing was written. The declaration is not recorded and the "
                                 "identical request can be sent again."}, 500
    if not audit_hash:
        return {"error": "seal_failed", "message": "seal returned no audit hash",
                "what_happened": "Nothing was written. The declaration is not recorded and the "
                                 "identical request can be sent again."}, 500

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
            except sqlite3.IntegrityError:
                duplicates += 1
            except Exception as exc:
                ctx["conn"].rollback()
                return {"error": "edge_write_failed", "message": str(exc),
                        "sealed_in_chain": audit_hash, "block_index": block_index,
                        "what_happened": "The declaration was sealed but the edges were not "
                                         "stored. The seal stands as a dated record of the "
                                         "attempt; resend to store the edges."}, 500
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "already_declared_means": "Refused by the unique index because this exact child, "
                                      "chain and parent were declared before. Any other write "
                                      "failure is an error, not a duplicate.",
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (our_base, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (our_base, child)}, 200


def _walk(ctx, start, depth, upstream):
    our_base = _get_base_url(ctx)
    seen = {start}
    nodes, edges, frontier = [], [], []
    frontier_keys = set()
    queue = [(start, 0)]
    truncated = False
    node_cap_hit = False

    while queue:
        receipt, level = queue.pop(0)
        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)

        if level >= depth:
            if rows:
                truncated = True
            continue
        if len(nodes) >= MAX_NODES:
            if rows:
                truncated = True
                node_cap_hit = True
            continue

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
                if (chain, other) not in frontier_keys:
                    frontier_keys.add((chain, other))
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base, our_base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                node_cap_hit = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base, our_base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated, node_cap_hit


def _truncation_note(truncated, node_cap_hit, depth):
    if not truncated:
        return None
    if node_cap_hit:
        return ("Stopped at the %d node ceiling. More declared hops exist beyond what is "
                "listed here." % MAX_NODES)
    return ("Stopped at depth %d. Nodes at that edge have further declared hops that were not "
            "followed - raise depth (max %d) to see them." % (depth, MAX_DEPTH))


def _trace(ctx, data):
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)
    our_base = _get_base_url(ctx)

    nodes, edges, frontier, truncated, cap = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [], "truncated": False,
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "truncation_note": _truncation_note(truncated, cap, depth),
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base),
            "how_to_verify_this": "Every node carries the routes to check it on its own chain. "
                                  "Nothing here asks you to take our word for a hop, including "
                                  "the hops on our own chain.",
            "what_an_edge_is": "A sealed, dated claim by the declaring party that these inputs "
                               "fed that decision. Sealing makes it non-repudiable, not true.",
            "frontier_note": "External entries are named but not resolved here. Run their "
                             "verification plans against their own hosts - that is what makes "
                             "the graph checkable without a shared database."}, 200


def _impact(ctx, data):
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated, cap = _walk(ctx, receipt, depth, upstream=False)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": len(nodes), "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "truncation_note": _truncation_note(truncated, cap, depth),
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


def _portable_receipt(ctx, data):
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    our_base = _get_base_url(ctx)
    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "declared_at": _iso(r[5]), "declaration_sealed_as": r[6],
               "verify": _verification_plan(r[0], r[1], r[2], our_base=our_base)} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (our_base, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % our_base,
            "nothing_was_left_out": "%s/x/complete/periods" % our_base,
            "who_witnesses_us": "%s/x/witness/peers" % our_base,
            "our_current_tip": "%s/x/witness/tip" % our_base,
            "walk_the_whole_chain": "%s/x/walk/status" % our_base,
            "the_engine_reproduces": "%s/x/replay/spec" % our_base,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (our_base, receipt),
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


def _status(ctx):
    our_base = _get_base_url(ctx)
    with ctx["lock"]:
        edges = ctx["conn"].execute("SELECT COUNT(*) FROM lineage_edge").fetchone()[0]
        children = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT child_receipt) FROM lineage_edge").fetchone()[0]
        external = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT parent_chain) FROM lineage_edge "
            "WHERE parent_chain<>?", (OUR_CHAIN_NAME,)).fetchone()[0]
    return {"module": "lineage", "lineage_version": VERSION, "ok": True,
            "edges_declared": edges, "decisions_with_inputs": children,
            "external_chains_referenced": external,
            "spec": "%s/x/lineage/spec" % our_base}, 200


def _spec(ctx):
    our_base = _get_base_url(ctx)
    return {
        "module": "lineage", "lineage_version": VERSION,
        "what_it_does": "Records, as sealed chain entries, which decisions fed which other "
                        "decisions - across companies, without a shared database.",
        "routes": {
            "GET %s/x/lineage/status" % our_base: "counts, public",
            "GET %s/x/lineage/spec" % our_base: "this document, public",
            "GET %s/x/lineage/trace?receipt=<64hex>&depth=3" % our_base:
                "what fed this decision, public",
            "GET %s/x/lineage/impact?receipt=<64hex>&depth=3" % our_base:
                "what this decision fed, public",
            "GET %s/x/lineage/receipt?receipt=<64hex>" % our_base:
                "portable receipt for one decision, public",
            "POST %s/x/lineage/declare" % our_base:
                "declare inputs, requires an API key",
        },
        "declare_body": {"receipt": "<64 hex>", "chain": "aileash (optional)",
                         "inputs": [{"chain": "supplier-name", "receipt": "<64 hex>",
                                     "role": "data", "base": "https://supplier.example",
                                     "note": "optional, 200 chars"}]},
        "roles": list(ROLES),
        "limits": {"inputs_per_declaration": MAX_INPUTS, "default_depth": DEFAULT_DEPTH,
                   "max_depth": MAX_DEPTH, "max_nodes": MAX_NODES},
        "what_a_declaration_is": "A sealed, dated claim by the declaring party. Sealing makes it "
                                 "non-repudiable, not true.",
        "duplicates": "A repeat of the same child, chain and parent is refused by a unique index "
                      "and reported as already_declared. Any other write failure is an error.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    method = str(method or "GET").upper()
    action = str(action or "status").strip().lower().strip("/")
    data = data if isinstance(data, dict) else {}

    if action in ("", "index"):
        action = "status"

    if (method, action) not in PUBLIC and not api_key:
        return {"error": "api_key_required",
                "message": "Declaring lineage needs a key. Reading it never does."}, 401

    if action in ("status", "health"):
        return _status(ctx)
    if action == "spec":
        return _spec(ctx)
    if action == "trace":
        return _trace(ctx, data)
    if action == "impact":
        return _impact(ctx, data)
    if action == "receipt":
        return _portable_receipt(ctx, data)
    if action == "declare":
        if method == "GET":
            return {"error": "post_required",
                    "message": "Send this as POST with a JSON body and an API key.",
                    "spec": "%s/x/lineage/spec" % _get_base_url(ctx)}, 405
        return _declare(ctx, api_key, data)

    return {"error": "unknown_action", "action": action, "method": method,
            "known_actions": list(ACTIONS),
            "spec": "%s/x/lineage/spec" % _get_base_url(ctx)}, 404
