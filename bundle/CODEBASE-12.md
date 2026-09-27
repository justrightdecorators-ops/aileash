# Codebase — part 12 of 42

Contains:
- `modules/lineage.py`
- `modules/lineagedesk.py`
- `modules/machine.py`
- `modules/map.py`
- `modules/marquee.py`
- `modules/meter.py`


## `modules/lineage.py`

498 lines, 22905 bytes

```python
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

```


## `modules/lineagedesk.py`

215 lines, 7806 bytes

```python
"""
Lineage desk - a keyed page at /lineage-desk.

Exists because lineage declare is POST-with-a-key, and a phone browser address
bar can send neither. Own _lineagedesk_patched attribute so it composes with
console.py, packconsole.py, peerconsole.py and binddesk.py.

Arm after every deploy by hitting /x/lineagedesk/status.
"""

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "health"), ("GET", "spec")}

_patched = [False]

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lineage desk</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f5f5f5;color:#111}
h1{font-size:20px;margin:0 0 4px}
p.sub{margin:0 0 16px;color:#555;font-size:14px}
label{display:block;margin:12px 0 4px;font-size:14px;font-weight:500}
input,textarea,select{width:100%;padding:10px;font-size:15px;border:1px solid #ccc;
border-radius:6px;box-sizing:border-box;font-family:inherit}
textarea{min-height:90px;font-family:ui-monospace,monospace;font-size:13px}
button{width:100%;padding:12px;margin-top:12px;font-size:15px;font-weight:500;
border:0;border-radius:6px;background:#1a1a1a;color:#fff}
button.alt{background:#fff;color:#1a1a1a;border:1px solid #ccc}
.row{display:flex;gap:8px}
.row button{flex:1}
pre{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;
white-space:pre-wrap;word-break:break-all;font-size:12px;margin-top:16px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:16px}
small{color:#666;font-size:12px}
</style>
</head>
<body>
<h1>Lineage desk</h1>
<p class="sub">Declare what fed a decision, and read it back.</p>

<div class="card">
<label>API key</label>
<input id="key" type="password" placeholder="paste your key" autocomplete="off">
<small>Kept in this page only. Never sent anywhere but sebbi.pro.</small>
</div>

<div class="card">
<label>Decision receipt (the child, 64 hex)</label>
<input id="child" placeholder="audit hash of the decision" autocomplete="off">

<label>Input chain</label>
<input id="pchain" placeholder="aileash, mir, supplier-name" value="aileash" autocomplete="off">

<label>Input receipt (the parent, 64 hex)</label>
<input id="parent" placeholder="audit hash of what fed it" autocomplete="off">

<label>Role</label>
<select id="role">
<option>input</option><option>model</option><option>data</option>
<option>policy</option><option>document</option><option>upstream-decision</option>
<option>supplier</option><option>other</option>
</select>

<label>Their base address (optional)</label>
<input id="pbase" placeholder="https://supplier.example" autocomplete="off">

<label>Note (optional)</label>
<input id="note" placeholder="200 characters" autocomplete="off">

<button onclick="declareOne()">Declare this input</button>
</div>

<div class="card">
<label>Or paste a full declaration body</label>
<textarea id="raw" placeholder='{"receipt":"...","inputs":[{"chain":"mir","receipt":"..."}]}'></textarea>
<button class="alt" onclick="declareRaw()">Declare from JSON</button>
</div>

<div class="card">
<label>Read it back</label>
<div class="row">
<button class="alt" onclick="read('trace')">Trace up</button>
<button class="alt" onclick="read('impact')">Impact down</button>
</div>
<button class="alt" onclick="read('receipt')">Portable receipt</button>
<button class="alt" onclick="status()">Module status</button>
</div>

<pre id="out">Ready.</pre>

<script>
function val(id){return document.getElementById(id).value.trim();}
function show(o){document.getElementById('out').textContent =
  typeof o === 'string' ? o : JSON.stringify(o, null, 2);}

function post(body){
  var k = val('key');
  if(!k){show('Paste your API key first.');return;}
  show('Sending...');
  fetch('/x/lineage/declare', {
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},
    body:JSON.stringify(body)
  }).then(function(r){return r.json().then(function(j){
      return {http:r.status, response:j};});})
    .then(show).catch(function(e){show('Failed: '+e);});
}

function declareOne(){
  var child = val('child'), parent = val('parent');
  if(child.length !== 64){show('The decision receipt must be 64 hex characters.');return;}
  if(parent.length !== 64){show('The input receipt must be 64 hex characters.');return;}
  var item = {chain: val('pchain') || 'aileash', receipt: parent, role: val('role')};
  if(val('pbase')) item.base = val('pbase');
  if(val('note')) item.note = val('note');
  post({receipt: child, inputs: [item]});
}

function declareRaw(){
  var t = val('raw');
  if(!t){show('Nothing to send.');return;}
  var body;
  try{body = JSON.parse(t);}catch(e){show('That is not valid JSON: '+e);return;}
  post(body);
}

function read(action){
  var r = val('child');
  if(r.length !== 64){show('Put a 64 hex receipt in the decision receipt box.');return;}
  show('Reading...');
  fetch('/x/lineage/'+action+'?receipt='+encodeURIComponent(r))
    .then(function(x){return x.json();}).then(show)
    .catch(function(e){show('Failed: '+e);});
}

function status(){
  show('Reading...');
  fetch('/x/lineage/status').then(function(x){return x.json();})
    .then(show).catch(function(e){show('Failed: '+e);});
}
</script>
</body>
</html>"""


def _install_page(ctx):
    if _patched[0]:
        return "already installed"
    import sys
    s = sys.modules.get("__main__")
    if s is None or not hasattr(s, "get_bearer"):
        s = sys.modules.get("server")
    if s is None:
        return "server not found"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_lineagedesk_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.rstrip("/") == "/lineage-desk":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original(self)

    H.do_GET = do_GET
    H._lineagedesk_patched = True
    _patched[0] = True
    print("LINEAGEDESK: /lineage-desk installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    action = str(action or "status").strip().lower().strip("/")
    result = _install_page(ctx)

    if action in ("", "status", "health", "index"):
        return {"module": "lineagedesk", "version": VERSION, "ok": True,
                "page_install": result,
                "page": "https://sebbi.pro/lineage-desk",
                "note": "Hit this route after every deploy to arm the page."}, 200

    if action == "spec":
        return {"module": "lineagedesk", "version": VERSION,
                "what_it_does": "Serves a keyed page at /lineage-desk so lineage declarations "
                                "can be made from a phone, where a browser address bar cannot "
                                "send a POST or an Authorization header.",
                "page": "https://sebbi.pro/lineage-desk",
                "arm": "https://sebbi.pro/x/lineagedesk/status",
                "calls": ["POST /x/lineage/declare",
                          "GET /x/lineage/trace", "GET /x/lineage/impact",
                          "GET /x/lineage/receipt", "GET /x/lineage/status"]}, 200

    return {"error": "unknown_action", "action": action,
            "known_actions": ["status", "spec"]}, 404

```


## `modules/machine.py`

658 lines, 27386 bytes

```python
"""
modules/machine.py  v1.0.3  -  the machine

Ask it in a web address. It goes out to the internet, does the work, and
answers in data anyone - person or program - can check.

    https://sebbi.pro/x/machine/ask?q=find 35ff59fa
    https://sebbi.pro/x/machine/ask?q=bitcoin
    https://sebbi.pro/x/machine/ask?q=verify today
    https://sebbi.pro/x/machine/ask?q=block 2013
    https://sebbi.pro/x/machine/ask?q=check openai.com
    https://sebbi.pro/x/machine/ask?q=archive today
    https://sebbi.pro/x/machine/ask?q=witness
    https://sebbi.pro/x/machine/ask?q=walk
    https://sebbi.pro/x/machine/help

Every command is also its own route (/x/machine/find?sha256=..., etc).

Every answer carries:
  sources   - each thing it fetched, with the SHA-256 of what came back
  evidence  - what it computed from that
  check_it_yourself - how to redo the same work without this machine

The machine reads and checks. It never changes anything. All routes public.
"""

import base64
import gzip
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.3"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/machine/"
UA = "sebbi-machine/1.0.3 (+https://sebbi.pro/x/machine/help)"
TIMEOUT = 30
MAX_BYTES = 96 * 1024 * 1024
EXPLORERS = [
    ("mempool.space", "https://mempool.space/api"),
    ("blockstream.info", "https://blockstream.info/api"),
]

PUBLIC = {("GET", a) for a in (
    "help", "ask", "find", "verify", "bitcoin", "block", "check",
    "archive", "witness", "walk", "register", "status", "spec")}

_busy = threading.BoundedSemaphore(3)


# ---------------------------------------------------------------- fetching

class _Trail(object):
    """Every fetch is recorded with the hash of what came back."""

    def __init__(self):
        self.sources = []

    def get(self, url, max_bytes=MAX_BYTES, accept="application/json"):
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read(max_bytes + 1)
                final = resp.geturl()
        except urllib.error.HTTPError as exc:
            self.sources.append({"url": url, "result": "HTTP %s" % exc.code})
            raise
        except Exception as exc:
            self.sources.append({"url": url, "result": "unreachable (%s)"
                                 % exc.__class__.__name__})
            raise
        if len(raw) > max_bytes:
            self.sources.append({"url": url, "result": "too large"})
            raise ValueError("response too large")
        compressed = raw[:2] == b"\x1f\x8b"
        if compressed:
            # Archives keep a page exactly as it was sent - often zipped.
            raw = gzip.decompress(raw)
        self.sources.append({"url": url, "final_url": final,
                             "was_compressed": compressed,
                             "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "ms": int((time.time() - t0) * 1000)})
        return raw

    def json(self, url, **kw):
        return json.loads(self.get(url, **kw).decode("utf-8"))

    def text(self, url):
        return self.get(url, accept="text/plain").decode("utf-8").strip()


def _public_https(url):
    """For addresses a caller supplies: https, port 443, public host only."""
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if p.scheme != "https" or p.port not in (None, 443) or not p.hostname:
        return False
    if p.username or p.password:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443,
                                       proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
    except Exception:
        return False
    return True


def _canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _answer(command, answer, evidence, trail, check, ok=True, **extra):
    out = {"ok": ok, "machine": VERSION, "command": command,
           "answer": answer, "evidence": evidence,
           "sources": trail.sources, "check_it_yourself": check,
           "answered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out.update(extra)
    return out


# ---------------------------------------------------------------- the chain

def _recompute(blocks, prev="GENESIS"):
    problems, public, withheld = [], 0, 0
    for b in blocks:
        h = b.get("audit_hash")
        if "preimage" in b:
            pre = b["preimage"]
            if hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                problems.append("block %s does not recompute" % b.get("block_index"))
            try:
                stated = json.loads(pre).get("prev_hash")
            except Exception:
                stated = None
            public += 1
        else:
            stated = b.get("prev_hash")
            withheld += 1
        if stated != prev:
            problems.append("block %s does not link to the block before it"
                            % b.get("block_index"))
        prev = h
    return {"blocks": len(blocks), "recomputed_from_own_text": public,
            "linkage_only": withheld, "tip": prev,
            "problems": problems[:20]}


def _walk_all(trail):
    blocks, after = [], 0
    while True:
        page = trail.json("%s/x/walk/blocks?after=%d&limit=500" % (SITE, after))
        blocks.extend(page.get("blocks") or [])
        if not page.get("has_more"):
            return blocks
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            raise ValueError("walk paging did not advance")
        after = nxt


def cmd_walk(q):
    t = _Trail()
    blocks = _walk_all(t)
    r = _recompute(blocks)
    ok = not r["problems"]
    return _answer(
        "walk",
        "Walked all %d blocks from genesis to tip and recomputed them: %s."
        % (r["blocks"], "PASS" if ok else "FAIL"),
        r, t,
        ["Fetch https://sebbi.pro/x/walk/blocks?after=0&limit=500 and each "
         "next page", "For every block with a preimage: SHA-256 it, compare "
         "with audit_hash, and check its prev_hash is the block before",
         "Method: https://sebbi.pro/x/walk/spec"], ok=ok)


def cmd_block(q):
    t = _Trail()
    try:
        n = int(q.get("n") or q.get("index"))
    except (TypeError, ValueError):
        return _answer("block", "Give a block number, e.g. block 2013.", {},
                       t, [], ok=False)
    data = t.json("%s/x/walk/block?index=%d" % (SITE, n))
    b = data.get("block") or {}
    ev = {"block_index": n, "audit_hash": b.get("audit_hash"),
          "previous_block_hash": data.get("previous_audit_hash")}
    if "preimage" in b:
        pre = b["preimage"]
        ev["recomputed_hash"] = hashlib.sha256(pre.encode("utf-8")).hexdigest()
        ev["matches"] = ev["recomputed_hash"] == b.get("audit_hash")
        try:
            ev["sealed_text"] = json.loads(pre)
            ev["links_to_previous"] = (ev["sealed_text"].get("prev_hash") ==
                                       data.get("previous_audit_hash"))
        except Exception:
            pass
        ans = ("Block %d recomputes from its own sealed text and links to the "
               "block before it." % n) if ev.get("matches") and \
            ev.get("links_to_previous") else "Block %d does NOT check out." % n
        ok = bool(ev.get("matches") and ev.get("links_to_previous"))
    else:
        ev["withheld_reason"] = b.get("withheld_reason")
        ev["links_to_previous"] = b.get("prev_hash") == data.get("previous_audit_hash")
        ans = ("Block %d is withheld from public view (%s); its link to the "
               "block before it checks out." % (n, b.get("withheld_reason")))
        ok = bool(ev["links_to_previous"])
    return _answer("block", ans, ev, t,
                   ["Open https://sebbi.pro/x/walk/block?index=%d" % n,
                    "SHA-256 the preimage text; it must equal audit_hash"],
                   ok=ok)


# ---------------------------------------------------------------- archive files

def _manifest(t):
    return t.json(SITE + "/x/archive/manifest").get("files") or []


def _resolve_file(t, ref):
    """ref: 'today', 'latest', a date, or a fingerprint or its prefix."""
    files = _manifest(t)
    ref = (ref or "latest").strip().lower()
    if ref in ("today", "latest", ""):
        return files[0] if files else None
    for f in files:
        if f.get("date") == ref:
            return f
        if len(ref) >= 8 and str(f.get("sha256", "")).startswith(ref):
            return f
    return None


def _wayback_captures(t, target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = t.json("https://web.archive.org/cdx/search/cdx?url=" +
                      urllib.parse.quote(target, safe="") +
                      "&output=json&filter=statuscode:200&limit=-10")
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = t.json("https://archive.org/wayback/available?url=" +
                       urllib.parse.quote(target, safe=""))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def cmd_find(q):
    """Hunt for copies of an archive file across the internet, and prove
    each one is the sealed file."""
    t = _Trail()
    ref = q.get("sha256") or q.get("ref") or "latest"
    f = _resolve_file(t, ref)
    if not f:
        return _answer("find", "No sealed file matches '%s'." % ref, {}, t,
                       ["List every sealed file: https://sebbi.pro/x/archive/manifest"],
                       ok=False)
    sha = f["sha256"]
    file_url = "%s/x/archive/file?sha256=%s" % (SITE, sha)
    copies = []

    # 1. the operator's own server
    try:
        body = json.loads(t.get(file_url).decode("utf-8"))
        got = _canonical_sha(body)
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "fingerprint": got, "is_the_sealed_file": got == sha})
    except Exception:
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "found": False})

    # 2. the Internet Archive - independent, owes nothing to the operator
    stamps = _wayback_captures(t, file_url)
    if stamps is None:
        copies.append({"where": "Internet Archive (independent)",
                       "found": None, "note": "archive could not be asked"})
    elif not stamps:
        copies.append({"where": "Internet Archive (independent)",
                       "found": False,
                       "archive_it_now": "https://web.archive.org/save/" + file_url,
                       "note": "Not archived yet. Opening archive_it_now "
                               "from any phone or browser makes an "
                               "independent copy."})
    else:
        best = None
        for stamp in stamps[:3]:
            raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, file_url)
            try:
                body = json.loads(t.get(raw_url).decode("utf-8"))
                got = _canonical_sha(body)
                best = {"where": "Internet Archive (independent)",
                        "url": "https://web.archive.org/web/%s/%s" % (stamp, file_url),
                        "raw_copy": raw_url, "captured": stamp,
                        "fingerprint": got, "is_the_sealed_file": got == sha,
                        "captures_listed": len(stamps)}
                if got == sha:
                    break
            except Exception:
                best = best or {"where": "Internet Archive (independent)",
                                "found": True, "captured": stamp,
                                "note": "capture listed but could not be read"}
        copies.append(best)

    # 3. registered holders (custody) - read if the module exists
    try:
        holders = t.json(SITE + "/x/custody/holders").get("holders") or []
        for h in holders:
            copies.append({"where": h.get("name") or "holder",
                           "url": h.get("url"),
                           "fingerprint": h.get("last_fingerprint"),
                           "is_the_sealed_file": h.get("last_fingerprint") == sha,
                           "last_verified": h.get("last_verified")})
    except Exception:
        pass

    verified = [c for c in copies if c.get("is_the_sealed_file")]
    independent = [c for c in verified if "operator" not in c["where"]]
    return _answer(
        "find",
        "Found %d verified cop%s of file %s… (%d independent of sebbi.pro)."
        % (len(verified), "y" if len(verified) == 1 else "ies", sha[:12],
           len(independent)),
        {"file": {"date": f.get("date"), "sha256": sha,
                  "sealed_in_block": f.get("sealed_in_block"),
                  "check_block": f.get("check_block")},
         "copies": copies}, t,
        ["Take any copy's raw bytes, parse the JSON, re-serialise it with "
         "sorted keys and no spaces, SHA-256 it",
         "It must equal the fingerprint sealed in block %s" % f.get("sealed_in_block"),
         "Then run the checker inside the file: python3 -c \"import json,sys;"
         "exec(json.load(open(sys.argv[1]))['verifier_py'])\" FILE.json"])


def cmd_verify(q):
    """Verify a whole archive file here: fingerprint, every block, every link."""
    t = _Trail()
    url = q.get("url")
    sealed = {f["sha256"]: f for f in _manifest(t)}
    if url:
        if not _public_https(url):
            return _answer("verify", "Only public https addresses are fetched.",
                           {}, t, [], ok=False)
        where = url
    else:
        f = _resolve_file(t, q.get("sha256") or q.get("ref") or "latest")
        if not f:
            return _answer("verify", "No sealed file matches that.", {}, t,
                           [], ok=False)
        where = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
    body = json.loads(t.get(where).decode("utf-8"))
    fp = _canonical_sha(body)
    chain = (body.get("chain") or {})
    r = _recompute(chain.get("blocks") or [])
    checks = {
        "fingerprint": fp,
        "fingerprint_is_sealed": fp in sealed,
        "sealed_in_block": (sealed.get(fp) or {}).get("sealed_in_block"),
        "chain": r,
        "tip_matches_declared": r["tip"] == chain.get("tip"),
        "genesis_matches_declared": bool(chain.get("blocks")) and
        chain["blocks"][0].get("audit_hash") == chain.get("genesis_hash"),
        "previous_file": body.get("previous_file_sha256"),
    }
    ok = (checks["fingerprint_is_sealed"] and not r["problems"] and
          checks["tip_matches_declared"] and checks["genesis_matches_declared"])
    return _answer(
        "verify",
        "%s: file %s… is %s, and its %d blocks %s." % (
            "PASS" if ok else "FAIL", fp[:12],
            "a sealed file" if checks["fingerprint_is_sealed"] else "NOT a sealed file",
            r["blocks"], "all check out" if not r["problems"] else "do not all check out"),
        checks, t,
        ["The same checks run with nothing from us: the program is inside the "
         "file. python3 -c \"import json,sys;exec(json.load(open(sys.argv[1]))"
         "['verifier_py'])\" FILE.json"], ok=ok)


def cmd_archive(q):
    """Ask the Internet Archive to take an independent copy, and hand back
    a one-tap link that works from any phone if it refuses a server."""
    t = _Trail()
    what = (q.get("what") or "today").strip().lower()
    if what in ("today", "latest", "file"):
        f = _resolve_file(t, "latest")
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"]) if f else None
    elif what.startswith("block"):
        n = re.sub(r"[^0-9]", "", what)
        target = "%s/x/walk/block?index=%s" % (SITE, n) if n else None
    elif what in ("chain", "genesis"):
        target = SITE + "/x/walk/genesis"
    elif what in ("register", "ratings"):
        target = SITE + "/x/integrity/register"
    else:
        target = None
    if not target:
        return _answer("archive", "Say what to archive: today, block 2013, "
                       "genesis or register.", {}, t, [], ok=False)
    tap = "https://web.archive.org/save/" + target
    result = None
    try:
        t.get(tap, accept="*/*", max_bytes=4 * 1024 * 1024)
        result = "the archive accepted the request from this server"
    except Exception:
        result = ("the archive turned this server away, as it often does "
                  "with cloud servers - the one-tap link below works from "
                  "any phone or browser")
    return _answer(
        "archive",
        "Archive request for %s: %s." % (target, result),
        {"target": target, "one_tap_archive": tap,
         "then_find_it": BASE + "find?ref=latest"}, t,
        ["Open one_tap_archive on your own device", "Then ask the machine to "
         "find it: https://sebbi.pro/x/machine/ask?q=find today"])


# ---------------------------------------------------------------- bitcoin

def cmd_bitcoin(q):
    """Follow the chain's anchor all the way into Bitcoin, and check it
    against two independent Bitcoin explorers."""
    t = _Trail()
    a = t.json(SITE + "/x/ots/latest_confirmed")
    if not a.get("ok"):
        return _answer("bitcoin", "No confirmed Bitcoin proof yet.", a, t, [],
                       ok=False)
    tip = str(a.get("tip") or "").lower()
    ev = {"chain_tip": tip, "tip_is_block": a.get("tip_is_block"),
          "stamp_id": a.get("stamp_id")}
    attest = []
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(
            base64.b64decode(a["ots_base64"])))
        tb = bytes.fromhex(tip)
        forms = {
            "sha256 of the tip's bytes": hashlib.sha256(tb).digest(),
            "the tip's bytes directly": tb,
            "sha256 of the tip as text": hashlib.sha256(tip.encode("ascii")).digest(),
            "sha256 of the tip as a line of text":
                hashlib.sha256((tip + "\n").encode("ascii")).digest(),
        }
        match = [name for name, d in forms.items() if det.file_digest == d]
        ev["proof_is_for_this_tip"] = bool(match)
        ev["proof_commits_to"] = match[0] if match else None
        for msg, att in det.timestamp.all_attestations():
            if isinstance(att, BitcoinBlockHeaderAttestation):
                attest.append((att.height, msg[::-1].hex()))
    except ImportError:
        ev["note"] = "proof reader not installed on this server"
    except Exception as exc:
        ev["note"] = "proof could not be read: %s" % exc.__class__.__name__
    if not attest:
        heights = a.get("bitcoin_block_heights") or []
        attest = [(h, None) for h in heights]
    results = []
    for height, expected_root in attest[:2]:
        row = {"bitcoin_block": height,
               "proof_computes_merkle_root": expected_root, "explorers": []}
        for name, api in EXPLORERS:
            try:
                bh = t.text("%s/block-height/%d" % (api, height))
                blk = t.json("%s/block/%s" % (api, bh))
                row["explorers"].append({
                    "explorer": name, "block_hash": bh,
                    "merkle_root": blk.get("merkle_root"),
                    "time": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(blk.get("timestamp", 0))),
                    "matches_proof": (expected_root is not None and
                                      blk.get("merkle_root") == expected_root)})
            except Exception:
                row["explorers"].append({"explorer": name,
                                         "result": "unreachable"})
        roots = set(e.get("merkle_root") for e in row["explorers"]
                    if e.get("merkle_root"))
        row["explorers_agree"] = len(roots) == 1
        row["proof_lands_on_block"] = bool(expected_root) and \
            roots == {expected_root}
        results.append(row)
    ev["bitcoin"] = results
    ok = bool(results) and all(r.get("proof_lands_on_block") for r in results) \
        and ev.get("proof_is_for_this_tip", False)
    first = results[0] if results else {}
    when = next((e.get("time") for e in first.get("explorers", [])
                 if e.get("time")), None)
    return _answer(
        "bitcoin",
        ("The chain tip at block %s is committed in Bitcoin block %s (%s). "
         "The proof lands exactly on that block's merkle root, and two "
         "independent explorers agree on it." % (
             a.get("tip_is_block"), first.get("bitcoin_block"), when))
        if ok else "The Bitcoin proof could not be fully confirmed; see evidence.",
        ev, t,
        ["Download the proof: https://sebbi.pro/x/ots/latest_confirmed "
         "(ots_base64)", "Run: ots verify, which checks the same merkle root "
         "against your own Bitcoin node",
         "Or open the block on mempool.space and blockstream.info and compare "
         "its merkle root with proof_computes_merkle_root"], ok=ok)


# ---------------------------------------------------------------- others

def cmd_check(q):
    t = _Trail()
    d = (q.get("domain") or "").strip().lower()
    if not d:
        return _answer("check", "Give a domain, e.g. check openai.com.", {}, t,
                       [], ok=False)
    r = t.json(SITE + "/x/integrity/check?domain=" + urllib.parse.quote(d))
    return _answer(
        "check", "%s verifies as %s (%s)." % (d, r.get("verified_level"),
                                              r.get("badge")),
        {k: r.get(k) for k in ("domain", "verified_level", "badge",
                               "claimed_level", "overclaimed", "verdict",
                               "request_sealed", "verdict_sealed")}, t,
        ["Full result: https://sebbi.pro/x/integrity/check?domain=" + d,
         "The verdict is sealed in the block shown; recompute it with "
         "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_witness(q):
    t = _Trail()
    held = t.json("https://mir.events/v1/transparency/held/tips?peer=sebbi")
    tips = [e.get("peer_tip") for e in (held.get("tips") or []) if e.get("peer_tip")]
    found = []
    blocks = _walk_all(t)
    index = {b["audit_hash"]: b.get("block_index") for b in blocks}
    for tip in tips:
        if tip in index:
            found.append(index[tip])
    return _answer(
        "witness",
        "MIR, an independent chain, holds %d of sebbi.pro's tips; %d are "
        "blocks in the chain as served today." % (len(tips), len(found)),
        {"witness": "MIR (MIRegistry)", "tips_held": len(tips),
         "matched_blocks": sorted(found)[-20:]}, t,
        ["Fetch https://mir.events/v1/transparency/held/tips?peer=sebbi",
         "Look each peer_tip up in the walk; every match is a block MIR holds"])


def cmd_register(q):
    t = _Trail()
    r = t.json(SITE + "/x/integrity/register")
    rows = [{"domain": e.get("domain"), "level": e.get("verified_level"),
             "badge": e.get("badge"), "sealed_in_block": e.get("sealed_in_block")}
            for e in r.get("entries") or []]
    return _answer("register", "%d domains rated; every rating is sealed."
                   % len(rows), {"entries": rows}, t,
                   ["Recompute any rating's block: "
                    "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_help(q):
    ex = lambda s: BASE + "ask?q=" + urllib.parse.quote(s)
    return {"ok": True, "machine": VERSION,
            "what": "Ask in a web address. The machine goes out to the "
                    "internet, does the work, and answers with its sources "
                    "and a way to check the answer without it.",
            "commands": {
                "find <fingerprint|today|date>": ex("find today"),
                "verify <fingerprint|today>": ex("verify today"),
                "bitcoin": ex("bitcoin"),
                "block <number>": ex("block 2013"),
                "walk": ex("walk"),
                "check <domain>": ex("check openai.com"),
                "witness": ex("witness"),
                "archive <today|block N|genesis|register>": ex("archive today"),
                "register": ex("register"),
            },
            "rule": "The machine reads and checks. It never changes anything."}


COMMANDS = {"find": cmd_find, "verify": cmd_verify, "bitcoin": cmd_bitcoin,
            "block": cmd_block, "walk": cmd_walk, "check": cmd_check,
            "witness": cmd_witness, "archive": cmd_archive,
            "register": cmd_register, "help": cmd_help}


def _parse(text):
    text = str(text or "").strip()
    # Clean copy-pasted Markdown link syntax or attached URLs
    text = re.sub(r'\]?https?://\S+', '', text).strip()
    text = re.sub(r'^[\[\(\s]+|[\]\)\s]+$', '', text)

    words = text.split()
    if not words:
        return "help", {}
    cmd = words[0].lower()
    arg = " ".join(words[1:]).strip()
    q = {}
    if cmd in ("find", "verify"):
        q["ref"] = arg or "latest"
    elif cmd == "block":
        q["n"] = arg
    elif cmd == "check":
        q["domain"] = arg
    elif cmd == "archive":
        q["what"] = arg or "today"
    return cmd, q


def handle(method, action, data, api_key, ctx):
    q = {}
    for k, v in (data or {}).items():
        q[k] = v[0] if isinstance(v, list) and v else v
    action = action or "help"
    if action == "ask":
        action, parsed = _parse(q.get("q"))
        q.update(parsed)
    if action in ("status", "spec"):
        action = "help"
    fn = COMMANDS.get(action)
    if not fn:
        out = cmd_help(q)
        out.update({"ok": False, "error": "unknown command: %s" % action})
        return out, 404
    if action == "help":
        return fn(q), 200
    if not _busy.acquire(timeout=20):
        return {"ok": False, "error": "busy",
                "detail": "Three commands are running. Try again shortly."}, 429
    try:
        out = fn(q)
        return out, 200
    except Exception as exc:
        return {"ok": False, "command": action,
                "error": "%s: %s" % (exc.__class__.__name__, str(exc)[:200])}, 502
    finally:
        _busy.release()

```


## `modules/map.py`

238 lines, 17926 bytes

```python
"""
modules/map.py  v1.0.0
Serves the layer-map page at /map.

Page module, same family as investor.py / console.py / network.py: a runtime
do_GET patch puts a full HTML page at a clean URL. Armed by hitting
/x/map/status once after each deploy. server.py is never edited. The page is
base64-embedded so no character in the HTML can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"
PAGE_PATH = "/map"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIi"
    "Pgo8dGl0bGU+V2hlcmUgc2ViYmkucHJvIHNpdHMg4oCUIHRoZSBsYXllciBtYXA8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlw"
    "dGlvbiIgY29udGVudD0iQSBiaXJkJ3MtZXllIG1hcCBvZiB0aGUgc3RhY2suIE1vbml0b3Jpbmcgd2F0Y2hlcyBmcm9tIHRoZSBz"
    "aWRlLCBhZnRlciB0aGUgZmFjdC4gQXV0b25vbW91cyBkZWNpc2lvbnMgY2FuJ3QgYmUgcHJvdmVuIGZyb20gdGhhdCBsYXllci4g"
    "c2ViYmkucHJvIHNpdHMgdW5kZXJuZWF0aCB0aGUgZGVjaXNpb24sIHNlYWxpbmcgaXQgYXMgaXQgaGFwcGVucy4iPgo8bGluayBy"
    "ZWw9InByZWNvbm5lY3QiIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20iPgo8bGluayBocmVmPSJodHRwczovL2Zv"
    "bnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDQwMDs2Li43Miw1MDA7Ni4u"
    "NzIsNjAwJmZhbWlseT1JQk0rUGxleCtTYW5zOndnaHRANDAwOzUwMDs2MDA7NzAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRA"
    "NDAwOzUwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7CiAgLS1pbms6IzBhMGYxZTstLWlu"
    "azI6IzEwMTgyZTstLXBhcGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7CiAgLS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0t"
    "b2stYmc6I0U0RUNFODsKICAtLXdhcm46IzlDMkYyNjstLXdhcm4tYmc6I0Y1RTZFMzstLW11dGVkOiM1QTYyNzA7LS1mYWludDoj"
    "OEE5MEEwOwogIC0tc2FuczonSUJNIFBsZXggU2Fucycsc3lzdGVtLXVpLHNhbnMtc2VyaWY7CiAgLS1zZXJpZjonTmV3c3JlYWRl"
    "cicsR2VvcmdpYSxzZXJpZjsKICAtLW1vbm86J0lCTSBQbGV4IE1vbm8nLHVpLW1vbm9zcGFjZSxtb25vc3BhY2U7Cn0KKntib3gt"
    "c2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2JhY2tncm91"
    "bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50"
    "aWFsaWFzZWR9Ci53cmFwe21heC13aWR0aDo4MjBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6MCAyNHB4fQoKLyogdG9wIGJhciAq"
    "LwoudG9we2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MTZweCAwfQoudG9wIC53cmFwe2Rpc3Bs"
    "YXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpiYXNlbGluZTtnYXA6MTJweDtmbGV4LXdy"
    "YXA6d3JhcH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluayl9Ci5i"
    "cmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBuYXZ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7"
    "Zm9udC1zaXplOjEyLjVweH0KLnRvcCBuYXYgYXtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2lu"
    "LWxlZnQ6MTZweH0KLnRvcCBuYXYgYTpob3Zlcntjb2xvcjp2YXIoLS1pbmspfQoKLyogaGVybyAqLwouaGVyb3twYWRkaW5nOjU2"
    "cHggMCAyMHB4fQouaGVybyBoMXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFt"
    "cCgzMHB4LDUuNXZ3LDUwcHgpO2xpbmUtaGVpZ2h0OjEuMDg7bGV0dGVyLXNwYWNpbmc6LTAuMDFlbTttYXgtd2lkdGg6MTdjaDtt"
    "YXJnaW4tYm90dG9tOjE4cHh9Ci5oZXJvIHB7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo1NmNo"
    "fQoKLyogdGhlIHN0YWNrIOKAlCB0aGUgaGVybyB2aXN1YWwgKi8KLnN0YWNre3BhZGRpbmc6MjRweCAwIDhweH0KLmxheWVye2Jv"
    "cmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo2cHg7cGFkZGluZzoyMHB4IDIycHg7bWFyZ2luLWJvdHRv"
    "bToxNHB4O2JhY2tncm91bmQ6I2ZmZjtwb3NpdGlvbjpyZWxhdGl2ZX0KLmxheWVyIC50YWd7Zm9udC1mYW1pbHk6dmFyKC0tbW9u"
    "byk7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MC4wNGVtO2NvbG9yOnZhcigtLWZhaW50KTttYXJnaW4tYm90dG9tOjdw"
    "eH0KLmxheWVyIGgze2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOjIxcHg7bWFyZ2lu"
    "LWJvdHRvbTo2cHg7bGluZS1oZWlnaHQ6MS4yfQoubGF5ZXIgcHtmb250LXNpemU6MTQuNXB4O2NvbG9yOnZhcigtLW11dGVkKTtt"
    "YXgtd2lkdGg6NjBjaH0KLmxheWVyIC52ZXJkaWN0e2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8p"
    "O2ZvbnQtc2l6ZToxMnB4O21hcmdpbi10b3A6MTJweDtwYWRkaW5nOjRweCAxMHB4O2JvcmRlci1yYWRpdXM6M3B4fQoudi1ub3ti"
    "YWNrZ3JvdW5kOnZhcigtLXdhcm4tYmcpO2NvbG9yOnZhcigtLXdhcm4pfQoudi15ZXN7YmFja2dyb3VuZDp2YXIoLS1vay1iZyk7"
    "Y29sb3I6dmFyKC0tb2spfQoKLyogdGhlIHR3byB3YXRjaGVyIGxheWVycywgZHJhd24gYXMgYm9sdGVkIG9uIGJlc2lkZSAqLwou"
    "d2F0Y2h7Ym9yZGVyLXN0eWxlOmRhc2hlZDtib3JkZXItY29sb3I6I0M5Q0JkMH0KLndhdGNoIGgze2NvbG9yOnZhcigtLW11dGVk"
    "KX0KLmFzaWRle2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWZhaW50KTtwb3NpdGlv"
    "bjphYnNvbHV0ZTt0b3A6MjBweDtyaWdodDoyMnB4fQoKLyogdGhlIGV4ZWN1dGlvbiBsYXllciDigJQgbmV1dHJhbCAqLwouZXhl"
    "Y3tiYWNrZ3JvdW5kOnZhcigtLWluayk7Ym9yZGVyLWNvbG9yOnZhcigtLWluayl9Ci5leGVjIC50YWd7Y29sb3I6cmdiYSgyNTUs"
    "MjU1LDI1NSwwLjUpfQouZXhlYyBoM3tjb2xvcjojZmZmfQouZXhlYyBwe2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC43Mil9Cgov"
    "KiB0aGUgZXZpZGVuY2UgbGF5ZXIg4oCUIHRoZSBvbmUgdGhhdCBtYXR0ZXJzICovCi5ldmlkZW5jZXtiYWNrZ3JvdW5kOnZhcigt"
    "LWluayk7Ym9yZGVyOjJweCBzb2xpZCB2YXIoLS1nb2xkKTtib3gtc2hhZG93OjAgOHB4IDMwcHggcmdiYSgyMDEsMTY4LDc2LDAu"
    "MTIpfQouZXZpZGVuY2UgLnRhZ3tjb2xvcjp2YXIoLS1nb2xkKX0KLmV2aWRlbmNlIGgze2NvbG9yOiNmZmY7Zm9udC1zaXplOjIz"
    "cHh9Ci5ldmlkZW5jZSBwe2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC44KX0KLmV2aWRlbmNlIC5mb3VuZGF0aW9ue2ZvbnQtZmFt"
    "aWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLWdvbGQpO21hcmdpbi10b3A6MTRweDtkaXNwbGF5OmZs"
    "ZXg7ZmxleC13cmFwOndyYXA7Z2FwOjhweH0KLmV2aWRlbmNlIC5mb3VuZGF0aW9uIHNwYW57Ym9yZGVyOjFweCBzb2xpZCByZ2Jh"
    "KDIwMSwxNjgsNzYsMC4zNSk7Ym9yZGVyLXJhZGl1czozcHg7cGFkZGluZzozcHggOXB4fQoKLyogY29ubmVjdGl2ZSBub3RlIGJl"
    "dHdlZW4gd2F0Y2hlcnMgYW5kIHRoZSByZXN0ICovCi5nYXAtbm90ZXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6"
    "MTJweDtjb2xvcjp2YXIoLS1mYWludCk7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo2cHggMCAxOHB4fQoKLyogYXJndW1lbnQg"
    "c2VjdGlvbiAqLwouYXJne3BhZGRpbmc6NDRweCAwO2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO21hcmdpbi10b3A6"
    "MjRweH0KLmFyZyBoMntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyNHB4"
    "LDR2dywzNHB4KTtsaW5lLWhlaWdodDoxLjE1O21hcmdpbi1ib3R0b206MThweDttYXgtd2lkdGg6MjBjaH0KLmFyZyBwe2ZvbnQt"
    "c2l6ZToxNS41cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo2MmNoO21hcmdpbi1ib3R0b206MTRweH0KLmFyZyBwIGJ7"
    "Y29sb3I6dmFyKC0taW5rKTtmb250LXdlaWdodDo2MDB9CgovKiB0aGUgZm91ciBxdWVzdGlvbnMgKi8KLnF7Ym9yZGVyLWxlZnQ6"
    "MnB4IHNvbGlkIHZhcigtLWdvbGQpO3BhZGRpbmc6NHB4IDAgNHB4IDE4cHg7bWFyZ2luOjAgMCAyMHB4fQoucSBoNHtmb250LXNp"
    "emU6MTZweDttYXJnaW4tYm90dG9tOjVweH0KLnEgcHtmb250LXNpemU6MTQuNXB4O21hcmdpbjowfQoKLyogY2xvc2UgKi8KLmNs"
    "b3Nle2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjp2YXIoLS1wYXBlcik7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzozNHB4"
    "O21hcmdpbjozMHB4IDAgNjBweH0KLmNsb3NlIGgye2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Y29s"
    "b3I6I2ZmZjtmb250LXNpemU6MjZweDttYXJnaW4tYm90dG9tOjEycHg7bWF4LXdpZHRoOjIyY2h9Ci5jbG9zZSBwe2ZvbnQtc2l6"
    "ZToxNXB4O2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC43NSk7bWF4LXdpZHRoOjU2Y2g7bWFyZ2luLWJvdHRvbToyMHB4fQouY2xv"
    "c2UgYXtkaXNwbGF5OmlubGluZS1ibG9jaztmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTMuNXB4O3RleHQtZGVj"
    "b3JhdGlvbjpub25lO21hcmdpbjo0cHggMTRweCA0cHggMH0KLmNsb3NlIGEucHJpbWFyeXtiYWNrZ3JvdW5kOnZhcigtLWdvbGQp"
    "O2NvbG9yOnZhcigtLWluayk7cGFkZGluZzoxMnB4IDIwcHg7Ym9yZGVyLXJhZGl1czo1cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2xv"
    "c2UgYS5naG9zdHtjb2xvcjp2YXIoLS1nb2xkKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAxLDE2OCw3NiwwLjQpO3BhZGRpbmc6"
    "MTJweCAyMHB4O2JvcmRlci1yYWRpdXM6NXB4fQoKZm9vdGVye2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRp"
    "bmc6MjRweCAwIDUwcHh9CmZvb3RlciBwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41cHg7Y29sb3I6dmFy"
    "KC0tZmFpbnQpO2xpbmUtaGVpZ2h0OjEuOH0KCkBtZWRpYShwcmVmZXJzLXJlZHVjZWQtbW90aW9uOnJlZHVjZSl7Knt0cmFuc2l0"
    "aW9uOm5vbmUhaW1wb3J0YW50O2FuaW1hdGlvbjpub25lIWltcG9ydGFudH19Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8aGVh"
    "ZGVyIGNsYXNzPSJ0b3AiPgogIDxkaXYgY2xhc3M9IndyYXAiPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwv"
    "Yj48L2Rpdj4KICAgIDxuYXY+CiAgICAgIDxhIGhyZWY9Ii8iPkhvbWU8L2E+CiAgICAgIDxhIGhyZWY9Ii93aGl0ZXBhcGVyIj5X"
    "aGl0ZXBhcGVyPC9hPgogICAgICA8YSBocmVmPSIvaW52ZXN0b3ItcHJvc3BlY3R1cyI+SW52ZXN0PC9hPgogICAgPC9uYXY+CiAg"
    "PC9kaXY+CjwvaGVhZGVyPgoKPGRpdiBjbGFzcz0id3JhcCI+CgogIDxzZWN0aW9uIGNsYXNzPSJoZXJvIj4KICAgIDxoMT5FdmVy"
    "eW9uZSBpcyB3YXRjaGluZyB0aGUgc3lzdGVtLiBBbG1vc3Qgbm9ib2R5IGlzIHVuZGVybmVhdGggaXQuPC9oMT4KICAgIDxwPlRo"
    "aXMgaXMgdGhlIHdob2xlIHN0YWNrLCB0b3AgdG8gYm90dG9tLiBUaGUgdG9vbHMgbW9zdCBvcmdhbmlzYXRpb25zIHJlbHkgb24g"
    "c2l0IHRvIHRoZSBzaWRlIGFuZCB3YXRjaC4gVGhlIHBsYWNlIGEgZGVjaXNpb24gYWN0dWFsbHkgaGFzIHRvIGJlIHByb3ZlbiBp"
    "cyB0aGUgbGF5ZXIgYmVuZWF0aCBpdCDigJQgYW5kIHRoYXQgbGF5ZXIgaXMgbmVhcmx5IGFsd2F5cyBlbXB0eS48L3A+CiAgPC9z"
    "ZWN0aW9uPgoKICA8c2VjdGlvbiBjbGFzcz0ic3RhY2siIGFyaWEtbGFiZWw9IlRoZSBzdGFjaywgdG9wIHRvIGJvdHRvbSI+Cgog"
    "ICAgPGRpdiBjbGFzcz0ibGF5ZXIgd2F0Y2giPgogICAgICA8ZGl2IGNsYXNzPSJ0YWciPmJvbHRlZCBvbiDCtyB3YXRjaGVzIGZy"
    "b20gdGhlIHNpZGU8L2Rpdj4KICAgICAgPHNwYW4gY2xhc3M9ImFzaWRlIj5vYnNlcnZhYmlsaXR5PC9zcGFuPgogICAgICA8aDM+"
    "TW9uaXRvcmluZyAmYW1wOyBkYXNoYm9hcmRzPC9oMz4KICAgICAgPHA+TG9nZ2luZyBwbGF0Zm9ybXMsIGRhc2hib2FyZHMsIGFs"
    "ZXJ0aW5nLiBUaGV5IHJlYWQgd2hhdCB0aGUgc3lzdGVtIGVtaXRzIGFuZCBzaG93IGl0IGJhY2sgdG8geW91LiBUaGUgcmVjb3Jk"
    "IHRoZXkga2VlcCBsaXZlcyBpbiBhIGRhdGFiYXNlIHlvdXIgb3duIHRlYW0gY2FuIGVkaXQsIHNvIGl0IHNheXMgd2hhdCB5b3Ug"
    "Y3VycmVudGx5IGNsYWltIGhhcHBlbmVkIOKAlCBub3QgdGhhdCBub3RoaW5nIGNoYW5nZWQgaXQgc2luY2UuPC9wPgogICAgICA8"
    "c3BhbiBjbGFzcz0idmVyZGljdCB2LW5vIj53YXRjaGVzIMK3IGNhbm5vdCBwcm92ZTwvc3Bhbj4KICAgIDwvZGl2PgoKICAgIDxk"
    "aXYgY2xhc3M9ImxheWVyIHdhdGNoIj4KICAgICAgPGRpdiBjbGFzcz0idGFnIj5ib2x0ZWQgb24gwrcgcmVhZHMgdGhlIG91dHB1"
    "dDwvZGl2PgogICAgICA8c3BhbiBjbGFzcz0iYXNpZGUiPmd1YXJkcmFpbHM8L3NwYW4+CiAgICAgIDxoMz5GaWx0ZXJzICZhbXA7"
    "IGd1YXJkcmFpbHM8L2gzPgogICAgICA8cD5Db250ZW50IGZpbHRlcnMgYW5kIHBvbGljeSBsYXllcnMgdGhhdCBpbnNwZWN0IHdo"
    "YXQgYSBtb2RlbCBzYXlzLiBVc2VmdWwsIGJ1dCB0aGV5IGFjdCBvbiB0aGUgdGV4dCBhZnRlciB0aGUgbW9kZWwgaGFzIHByb2R1"
    "Y2VkIGl0LCBhbmQgdGhleSBrZWVwIG5vIGV2aWRlbmNlIGEgcmVndWxhdG9yIGNhbiBjaGVjayB3aXRob3V0IHRydXN0aW5nIHRo"
    "ZSB2ZW5kb3Igd2hvIHdyb3RlIHRoZW0uPC9wPgogICAgICA8c3BhbiBjbGFzcz0idmVyZGljdCB2LW5vIj5maWx0ZXJzIMK3IGNh"
    "bm5vdCBwcm92ZTwvc3Bhbj4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImdhcC1ub3RlIj7ihpEgZXZlcnl0aGluZyBhYm92"
    "ZSB3YXRjaGVzIGFmdGVyIHRoZSBmYWN0IOKGkTwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImxheWVyIGV4ZWMiPgogICAgICA8ZGl2"
    "IGNsYXNzPSJ0YWciPndoZXJlIHRoZSBkZWNpc2lvbiBoYXBwZW5zPC9kaXY+CiAgICAgIDxoMz5UaGUgZXhlY3V0aW9uIGxheWVy"
    "PC9oMz4KICAgICAgPHA+VGhlIG1vZGVsLCB0aGUgYWdlbnQsIHRoZSBhdXRvbWF0ZWQgZGVjaXNpb24gaXRzZWxmIOKAlCB0aGUg"
    "bW9tZW50IHNvbWV0aGluZyBpcyBhY3R1YWxseSBkZWNpZGVkIGFuZCBhY3RlZCBvbi4gVGhpcyBpcyB0aGUgZXZlbnQgdGhhdCBo"
    "YXMgdG8gYmUgZXZpZGVuY2VkLiBJdCBpcyBhbHNvIHRoZSBtb21lbnQgdGhlIHdhdGNoaW5nIGxheWVycyBhYm92ZSBvbmx5IGV2"
    "ZXIgc2VlIHNlY29uZC1oYW5kLjwvcD4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImxheWVyIGV2aWRlbmNlIj4KICAgICAg"
    "PGRpdiBjbGFzcz0idGFnIj51bmRlcm5lYXRoIHRoZSBkZWNpc2lvbiDCtyBzZWFscyBpdCBhcyBpdCBoYXBwZW5zPC9kaXY+CiAg"
    "ICAgIDxoMz5UaGUgZXZpZGVuY2UgbGF5ZXIg4oCUIHdoZXJlIHNlYmJpLnBybyBzaXRzPC9oMz4KICAgICAgPHA+RWFjaCBkZWNp"
    "c2lvbiBpcyBzZWFsZWQgaW50byBhIGhhc2ggY2hhaW4gYXQgdGhlIG1vbWVudCBpdCBpcyBtYWRlLCBhbmNob3JlZCB0byBhIGNs"
    "b2NrIG5vYm9keSBjb250cm9scywgYW5kIGNyb3NzLXdpdG5lc3NlZCBieSBpbmRlcGVuZGVudCBzeXN0ZW1zLiBOb3QgYSByZWNv"
    "cmQgeW91IGtlZXAgYW5kIGhvcGUgaXMgYmVsaWV2ZWQg4oCUIGEgcmVjb3JkIGFueW9uZSBjYW4gdmVyaWZ5IHdpdGggeW91ciBj"
    "b21wYW55IHN3aXRjaGVkIG9mZi48L3A+CiAgICAgIDxkaXYgY2xhc3M9ImZvdW5kYXRpb24iPgogICAgICAgIDxzcGFuPmhhc2gg"
    "Y2hhaW48L3NwYW4+PHNwYW4+ZXh0ZXJuYWwgYW5jaG9yPC9zcGFuPjxzcGFuPmluZGVwZW5kZW50IHdpdG5lc3Nlczwvc3Bhbj48"
    "c3Bhbj5wdWJsaWMgdmVyaWZpY2F0aW9uPC9zcGFuPgogICAgICA8L2Rpdj4KICAgICAgPHNwYW4gY2xhc3M9InZlcmRpY3Qgdi15"
    "ZXMiPnByb3ZlcyDCtyBjYW5ub3QgYmUgZWRpdGVkPC9zcGFuPgogICAgPC9kaXY+CgogIDwvc2VjdGlvbj4KCiAgPHNlY3Rpb24g"
    "Y2xhc3M9ImFyZyI+CiAgICA8aDI+V2h5IHRoZSB3YXRjaGluZyBsYXllciBjYW4ndCBjYXJyeSBhdXRvbm9tb3VzIGRlY2lzaW9u"
    "czwvaDI+CiAgICA8cD5XaGVuIHNvZnR3YXJlIGRpZCB3aGF0IGl0IHdhcyB0b2xkLCB3YXRjaGluZyBpdCB3YXMgZW5vdWdoIOKA"
    "lCB0aGUgaW5wdXRzIGltcGxpZWQgdGhlIG91dHB1dHMsIGFuZCBhIGxvZyBvZiB0aGUgaW5wdXRzIHdhcyBhcyBnb29kIGFzIGEg"
    "cmVjb3JkIG9mIHdoYXQgaGFwcGVuZWQuIFRoYXQgaXMgbm8gbG9uZ2VyIHRydWUuPC9wPgogICAgPHA+QW4gYXV0b25vbW91cyBz"
    "eXN0ZW0gcHJvZHVjZXMgb3V0cHV0cyB5b3UgY2Fubm90IGRlcml2ZSBieSBsb29raW5nIGF0IHRoZSBpbnB1dHMuIFNvIHRoZSBv"
    "dXRwdXQgaGFzIHRvIGJlIHJlY29yZGVkIGFzIGEgZmFjdCBpbiBpdHMgb3duIHJpZ2h0LCBhdCB0aGUgbW9tZW50IGl0IGhhcHBl"
    "bnMsIGluIGEgZm9ybSBub2JvZHkgY2FuIHF1aWV0bHkgY2hhbmdlIGFmdGVyd2FyZHMuIDxiPkEgbGF5ZXIgdGhhdCB3YXRjaGVz"
    "IGZyb20gdGhlIHNpZGUgY2Fubm90IGRvIHRoYXQ8L2I+IOKAlCBieSB0aGUgdGltZSBpdCBzZWVzIHRoZSBkZWNpc2lvbiwgdGhl"
    "IGRlY2lzaW9uIGhhcyBhbHJlYWR5IGhhcHBlbmVkLCBhbmQgdGhlIG9ubHkgcmVjb3JkIGlzIG9uZSB0aGUgb3BlcmF0b3IgY2Fu"
    "IGVkaXQuPC9wPgogICAgPHA+VGhpcyBpcyB3aHkgdGhlIHZvbHVtZSBwcm9ibGVtIGJpdGVzLiBPbmUgcmV2aWV3ZWQgZGVjaXNp"
    "b24gYSBkYXkgY2FuIGJlIHdhdGNoZWQgYnkgYSBwZXJzb24uIE1pbGxpb25zIG9mIGF1dG9tYXRlZCBkZWNpc2lvbnMgYSBtb250"
    "aCBjYW5ub3Qg4oCUIGFuZCB0aGUgbW9tZW50IG9uZSBpcyBjb250ZXN0ZWQsICJvdXIgZGFzaGJvYXJkIHNob3dlZCBpdCIgaXMg"
    "bm90IGV2aWRlbmNlLiBJdCBpcyBhbiBhc3NlcnRpb24gd2l0aCBnb29kIGZvcm1hdHRpbmcuPC9wPgogIDwvc2VjdGlvbj4KCiAg"
    "PHNlY3Rpb24gY2xhc3M9ImFyZyIgc3R5bGU9ImJvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmctdG9wOjM2"
    "cHgiPgogICAgPGgyPkZvdXIgcXVlc3Rpb25zIHRoZSB3YXRjaGluZyBsYXllciBhbnN3ZXJzICJubyIgdG88L2gyPgogICAgPGRp"
    "diBjbGFzcz0icSI+PGg0PkNhbiB0aGUgcGVvcGxlIGJlaW5nIGF1ZGl0ZWQgZWRpdCB0aGUgYXVkaXQ/PC9oND48cD5PbiB0aGUg"
    "d2F0Y2hpbmcgbGF5ZXIsIHllcyDigJQgdGhlIHJlY29yZCBzaXRzIGluIGEgZGF0YWJhc2UgdGhleSBjb250cm9sLiBPbiB0aGUg"
    "ZXZpZGVuY2UgbGF5ZXIsIGNoYW5naW5nIG9uZSByZWNvcmQgYnJlYWtzIGV2ZXJ5IHJlY29yZCBhZnRlciBpdC48L3A+PC9kaXY+"
    "CiAgICA8ZGl2IGNsYXNzPSJxIj48aDQ+Q2FuIGl0IGJlIGNoZWNrZWQgd2l0aCB0aGUgdmVuZG9yIHN3aXRjaGVkIG9mZj88L2g0"
    "PjxwPk9uIHRoZSB3YXRjaGluZyBsYXllciwgbm8g4oCUIHlvdSBsb2cgaW50byB0aGUgdmVuZG9yIHRvIHNlZSBpdC4gT24gdGhl"
    "IGV2aWRlbmNlIGxheWVyLCBhIHN0YW5kYWxvbmUgdmVyaWZpZXIgY2hlY2tzIGl0IHdpdGggbm8gYWNjb3VudCBhbmQgbm8gbmV0"
    "d29yayBjYWxsIGJhY2suPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0icSI+PGg0PkNhbiB5b3UgcHJvdmUgYSByZWNvcmQgcHJl"
    "ZGF0ZXMgdGhlIGNvbXBsYWludCBhYm91dCBpdD88L2g0PjxwPk9uIHRoZSB3YXRjaGluZyBsYXllciwgdGhlIGRhdGUgY29tZXMg"
    "ZnJvbSBhIGZpZWxkIHRoZSBzeXN0ZW0gY291bGQgc2V0IHRvIGFueXRoaW5nLiBPbiB0aGUgZXZpZGVuY2UgbGF5ZXIsIHRoZSB0"
    "aW1pbmcgaXMgZml4ZWQgYnkgYSBjbG9jayBub2JvZHkgaW52b2x2ZWQgY29udHJvbHMuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFz"
    "cz0icSI+PGg0PkNhbiB5b3UgcHJvdmUgdGhlIGh1bWFuIGFwcHJvdmVkIGJlZm9yZSB0aGUgbWFjaGluZSBhY3RlZD88L2g0Pjxw"
    "Pk9uIHRoZSB3YXRjaGluZyBsYXllciwgb3JkZXIgaXMgbm90IHJlY29yZGVkLiBPbiB0aGUgZXZpZGVuY2UgbGF5ZXIsIHRoZSBy"
    "ZXZpZXdlcidzIGRlY2lzaW9uIGlzIHNlYWxlZCBiZWZvcmUgdGhlIG1hY2hpbmUncyB2ZXJkaWN0IGlzIHNob3duIHRvIHRoZW0u"
    "PC9wPjwvZGl2PgogIDwvc2VjdGlvbj4KCiAgPGRpdiBjbGFzcz0iY2xvc2UiPgogICAgPGgyPkRvbid0IHRha2UgdGhlIGRpYWdy"
    "YW0ncyB3b3JkIGZvciBpdC4gQ2hlY2sgdGhlIGxheWVyIHlvdXJzZWxmLjwvaDI+CiAgICA8cD5FdmVyeSBjbGFpbSBvbiB0aGUg"
    "ZXZpZGVuY2UgbGF5ZXIgaXMgdmVyaWZpYWJsZSByaWdodCBub3csIHdpdGggbm8gYWNjb3VudCwgd2l0aCBvdXIgY29tcGFueSBz"
    "d2l0Y2hlZCBvZmYuIFN0YXJ0IHdpdGggdGhlIGxpdmUgY2hhaW4sIG9yIHJlYWQgdGhlIGZ1bGwgYXJjaGl0ZWN0dXJlLjwvcD4K"
    "ICAgIDxhIGNsYXNzPSJwcmltYXJ5IiBocmVmPSIvd2hpdGVwYXBlciI+UmVhZCB0aGUgd2hpdGVwYXBlcjwvYT4KICAgIDxhIGNs"
    "YXNzPSJnaG9zdCIgaHJlZj0iL3gvd2l0bmVzcy90aXAiPlNlZSB0aGUgbGl2ZSBjaGFpbjwvYT4KICA8L2Rpdj4KCjwvZGl2PgoK"
    "PGZvb3Rlcj4KICA8ZGl2IGNsYXNzPSJ3cmFwIj4KICAgIDxwPnNlYmJpLnBybyDCtyBNb25vcCBDb250ZW50IMK3IEJseXRoLCBO"
    "b3J0aHVtYmVybGFuZCwgVUs8YnI+CiAgICBUaGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJIGRlY2lzaW9ucy4gRnJlZSBmb3IgOTAg"
    "ZGF5cywgdGhlbiA1MHAgcGVyIGRldmljZSBwZXIgbW9udGguPC9wPgogIDwvZGl2Pgo8L2Zvb3Rlcj4KCjwvYm9keT4KPC9odG1s"
    "Pgo="
)

_HTML = base64.b64decode("".join(_B64.split())).decode("utf-8")
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_map_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == PAGE_PATH:
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._map_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    if action == "spec":
        return ({
            "module": "map",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/map/status once after each deploy to arm " + PAGE_PATH + ".",
        }, 200)
    return ({
        "module": "map",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/marquee.py`

115 lines, 5126 bytes

```python
"""
modules/marquee.py  v1.0.0
The 10p Wing: creator submissions for the sebbi.pro cinema.

    POST /x/marquee/submit    {url, title, creator, price}   (public)
    GET  /x/marquee/list      approved screens                (public)
    GET  /x/marquee/status    counts                          (public)
    GET  /x/marquee/pending   everything waiting              (keyed)
    POST /x/marquee/approve   {id, approved}                  (keyed)

We never hold anyone's video. A submission is a link, a title, a name and a
price, nothing else. Every submission is sealed into the chain when it lands,
so the date it was sent is provable, and nothing appears in the cinema until
it has been approved.
"""

import re
import time

VERSION = "1.0.0"
PUBLIC = {("POST", "submit"), ("GET", "list"), ("GET", "status"), ("GET", "spec")}
KEY = "public-marquee"
URL_RE = re.compile(r"^https://[A-Za-z0-9.\-]{3,253}(/[^\s<>\"']{0,300})?$")
CLEAN = re.compile(r"[<>\"'\\]")
_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS marquee(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                            "url TEXT UNIQUE,title TEXT,creator TEXT,price INTEGER,at REAL,"
                            "approved INTEGER DEFAULT 0,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _clean(s, n):
    return CLEAN.sub("", str(s or "")).strip()[:n]


def _rows(ctx, approved=None):
    q = "SELECT id,url,title,creator,price,at,approved,audit_hash,block_index FROM marquee"
    if approved is not None:
        q += " WHERE approved=%d" % (1 if approved else 0)
    q += " ORDER BY id DESC LIMIT 200"
    with ctx["lock"]:
        rows = ctx["conn"].execute(q).fetchall()
    return [{"id": r[0], "url": r[1], "title": r[2], "creator": r[3], "price": r[4],
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[5])),
             "approved": bool(r[6]), "sealed_in_chain": r[7], "block_index": r[8]} for r in rows]


def _submit(ctx, data):
    url = str(data.get("url", "")).strip()
    if not URL_RE.match(url):
        return {"received": False, "message": "That link does not look right. It needs to start with https://"}, 400
    title = _clean(data.get("title"), 80) or "Untitled"
    creator = _clean(data.get("creator"), 40) or "Anonymous"
    try:
        price = max(1, min(500, int(float(data.get("price", 10)))))
    except (TypeError, ValueError):
        price = 10
    with ctx["lock"]:
        if ctx["conn"].execute("SELECT 1 FROM marquee WHERE url=?", (url,)).fetchone():
            return {"received": False, "message": "That link is already in the queue."}, 200
    now = time.time()
    ev = {"user_id": "mrq:" + creator[:24], "action": "marquee_submission", "amount": 0,
          "country": "UK", "device_id": "cinema", "anomaly": 0, "device_risk": 0}
    res = {"decision": "MARQUEE_SUBMITTED", "score": 0, "marquee_version": VERSION,
           "detail": "creator=%s;title=%s;price=%d;url=%s" % (creator, title, price, url)}
    out = ctx["seal"](ev, res, now, KEY)
    audit_hash = out[0] if isinstance(out, (list, tuple)) else out
    block = out[1] if isinstance(out, (list, tuple)) and len(out) > 1 else None
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO marquee(url,title,creator,price,at,approved,audit_hash,block_index)"
                            " VALUES(?,?,?,?,?,0,?,?)", (url, title, creator, price, now, audit_hash, block))
        ctx["conn"].commit()
    return {"received": True, "title": title, "creator": creator, "price": price,
            "sealed_in_chain": audit_hash, "block_index": block,
            "message": "Sealed. It goes up once it has been looked at."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}
    if action == "submit" and method == "POST":
        return _submit(ctx, data)
    if action == "list":
        return {"screens": _rows(ctx, True)}, 200
    if action == "pending":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        return {"waiting": _rows(ctx, False)}, 200
    if action == "approve" and method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        try:
            i = int(data.get("id"))
        except (TypeError, ValueError):
            return {"error": "id_required"}, 400
        ok = 0 if str(data.get("approved", "1")).lower() in ("0", "false", "no") else 1
        with ctx["lock"]:
            ctx["conn"].execute("UPDATE marquee SET approved=? WHERE id=?", (ok, i))
            ctx["conn"].commit()
        return {"id": i, "approved": bool(ok)}, 200
    with ctx["lock"]:
        a = ctx["conn"].execute("SELECT COUNT(*) FROM marquee WHERE approved=1").fetchone()[0]
        w = ctx["conn"].execute("SELECT COUNT(*) FROM marquee WHERE approved=0").fetchone()[0]
    return {"module": "marquee", "version": VERSION, "on_screen": a, "waiting": w,
            "list": "https://sebbi.pro/x/marquee/list"}, 200

```


## `modules/meter.py`

281 lines, 10630 bytes

```python
"""
modules/meter.py  v1.0.0
The 50p device meter, done per device per month - without touching server.py.

Armed by https://sebbi.pro/x/meter/status after each deploy, it swaps these
functions inside the running server for new versions (same names, same
callers, nothing in server.py edited):

  record_device(api_key, device_id)
      Counts each distinct device a key sends in a calendar month (UTC), once,
      however many decisions it makes. Resets every month. Reading the count
      is a single-row lookup, so it holds at millions of devices per key.
      The engine (/api/govern) and the plug-in log (public_proof_adapter.py)
      both call this, so one central server acting for 20 million phones is
      billed for 20 million devices.

  device_count(api_key)
      What the key is billed for: the larger of last month's full count and
      this month so far. Growth is billed straight away; a customer who
      shrinks pays less the month after. Used by the trial-end checkout,
      /api/usage and the trial-expired answers.

  sync_stripe_quantities()
      The existing 6-hourly Stripe job now sets each paying subscription to
      device_count() - up or down - so every renewal charges 50p for each
      device actually used.

On first arming, each key's existing all-time device count is carried into
last month, so nobody's bill drops while the monthly count builds up.

Watch for keys stamping one device id on a whole network:
    https://sebbi.pro/admin/meter      (your admin login)
Public summary (no keys shown):
    https://sebbi.pro/x/meter/status
"""

import json
import sys
import threading
import time
from collections import defaultdict

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
RATE_GBP = 0.50
FLAG_EVENTS_PER_DEVICE = 10000
CACHE_MAX = 500000

_srv = None
_armed = False
_patched_http = False
_cache = {}
_lock = threading.Lock()
_events = defaultdict(int)
_orig = {}


def _month(ts=None):
    return time.strftime("%Y-%m", time.gmtime(ts if ts is not None else time.time()))


def _prev_month(ts=None):
    t = time.gmtime(ts if ts is not None else time.time())
    y, m = t.tm_year, t.tm_mon - 1
    if m == 0:
        y, m = y - 1, 12
    return "%04d-%02d" % (y, m)


def _find_server():
    for name in ("__main__", "server"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "record_device") and hasattr(m, "_conn") and hasattr(m, "_db_lock"):
            return m
    return None


# ---------------------------------------------------------------- the meter

def _setup(s):
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS device_month(api_key TEXT,month TEXT,device_id TEXT,first_seen REAL,"
                  "PRIMARY KEY(api_key,month,device_id)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS device_month_count(api_key TEXT,month TEXT,n INTEGER DEFAULT 0,"
                  "PRIMARY KEY(api_key,month)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT)")
        if not c.execute("SELECT 1 FROM config WHERE k='meter_v2_seeded'").fetchone():
            c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) "
                      "SELECT api_key,?,COUNT(*) FROM device_seen GROUP BY api_key", (_prev_month(),))
            c.execute("INSERT OR REPLACE INTO config(k,v) VALUES('meter_v2_seeded',?)", (str(time.time()),))
        c.commit()


def month_count(api_key, month=None):
    s = _srv
    with s._db_lock:
        try:
            r = s._conn.execute("SELECT n FROM device_month_count WHERE api_key=? AND month=?",
                                (api_key, month or _month())).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0


def device_count(api_key):
    """Billable devices: the larger of last month's full count and this month so far."""
    return max(month_count(api_key, _prev_month()), month_count(api_key))


def record_device(api_key, device_id):
    """Count device_id on api_key for this calendar month. Returns the billable count."""
    if not api_key or not device_id:
        return None
    s = _srv
    device_id = str(device_id)[:200]
    mon = _month()
    ck = (api_key, mon, device_id)
    with _lock:
        _events[(api_key, mon)] += 1
        hit = ck in _cache
    if not hit:
        with s._db_lock:
            try:
                c = s._conn
                cur = c.execute("INSERT OR IGNORE INTO device_month(api_key,month,device_id,first_seen) VALUES(?,?,?,?)",
                                (api_key, mon, device_id, time.time()))
                if cur.rowcount == 1:
                    c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) VALUES(?,?,0)", (api_key, mon))
                    c.execute("UPDATE device_month_count SET n=n+1 WHERE api_key=? AND month=?", (api_key, mon))
                    c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                              (api_key, device_id, time.time()))
                c.commit()
            except Exception as e:
                try:
                    s._conn.rollback()
                except Exception:
                    pass
                print("meter record_device err:" + str(e), flush=True)
                return None
        with _lock:
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[ck] = 1
    return device_count(api_key)


def sync_stripe_quantities():
    """Set each paying subscription's quantity to the billable device count, up or down."""
    s = _srv
    if not getattr(s, "STRIPE_SECRET", ""):
        print("QSYNC skip: no STRIPE_SECRET", flush=True)
        return
    with s._db_lock:
        rows = s._conn.execute("SELECT key,email,stripe_sub FROM api_keys WHERE is_paid=1 AND active=1 "
                               "AND stripe_sub!=''").fetchall()
    for key, email, sub_id in rows:
        try:
            n = device_count(key)
            if not n:
                continue
            sub = s.stripe_call("GET", "/subscriptions/" + sub_id)
            if not sub or "items" not in sub:
                print("QSYNC no sub for " + email, flush=True)
                continue
            items = sub["items"].get("data", [])
            if not items:
                continue
            item = items[0]
            current = int(item.get("quantity", 0) or 0)
            if n != current:
                r = s.stripe_call("POST", "/subscription_items/" + item["id"],
                                  {"quantity": str(n), "proration_behavior": "none"})
                if r and "id" in r:
                    print("QSYNC " + email + ": " + str(current) + " -> " + str(n) + " devices", flush=True)
                else:
                    print("QSYNC FAIL " + email, flush=True)
        except Exception as e:
            print("QSYNC ERR " + email + ": " + str(e), flush=True)


def watch(limit=200):
    mon = _month()
    with _lock:
        ev = [(k, n) for (k, m), n in _events.items() if m == mon]
    out = []
    for k, n in ev:
        d = month_count(k) or 1
        out.append({"key_prefix": k[:12], "events_this_month": n, "devices_this_month": d,
                    "events_per_device": round(n / float(d), 1), "flag": n / float(d) >= FLAG_EVENTS_PER_DEVICE})
    out.sort(key=lambda x: -x["events_per_device"])
    return out[:limit]


# ---------------------------------------------------------------- arming

def _arm():
    global _srv, _armed
    s = _find_server()
    if s is None:
        return False
    _srv = s
    _setup(s)
    if not _armed:
        for name in ("record_device", "device_count", "sync_stripe_quantities"):
            _orig.setdefault(name, getattr(s, name, None))
        s.record_device = record_device
        s.device_count = device_count
        s.sync_stripe_quantities = sync_stripe_quantities
        _armed = True
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        o = f.f_locals.get("self")
        if o is not None and hasattr(type(o), "do_GET") and hasattr(o, "wfile"):
            return type(o)
        f = f.f_back
    return None


def _install_http(ctx):
    """Serve /admin/meter behind the server's own admin login."""
    global _patched_http
    if _patched_http:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_meter_patched", False):
        _patched_http = True
        return True
    og = cls.do_GET

    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") == "/admin/meter":
            ok = False
            try:
                ok = bool(_srv and _srv.check_admin(self))
            except Exception:
                ok = False
            body = json.dumps({"error": "unauthorized"} if not ok else
                              {"month": _month(), "rate_per_device_gbp": RATE_GBP, "keys": watch(),
                               "flag_rule": "%d or more events per device this month - check the key is sending "
                                            "real device ids" % FLAG_EVENTS_PER_DEVICE}).encode("utf-8")
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return og(self)

    cls.do_GET = do_GET
    cls._meter_patched = True
    _patched_http = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _arm()
    http = _install_http(ctx)
    flags = [w for w in watch() if w["flag"]] if armed else []
    return ({"module": "meter", "version": VERSION, "armed": armed and http,
             "month": _month(), "rate_per_device_gbp": RATE_GBP,
             "rule": "50p per distinct device per calendar month; billed on the larger of last month and this month so far",
             "keys_metered_this_month": len(watch()) if armed else 0,
             "keys_flagged": len(flags),
             "stripe_sync": "every 6 hours, follows the meter up and down"}, 200)

```
