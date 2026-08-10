# Codebase — part 3 of 20

Contains:
- `modules/consistency.py`
- `modules/console.py`


## `modules/consistency.py`

461 lines, 19146 bytes

```python
#!/usr/bin/env python3
"""
modules/consistency.py  -  proving we have never run two histories
==================================================================

THE ATTACK NOTHING ELSE HERE STOPS
----------------------------------
Mutual witnessing means several parties hold hashes of our chain. What
none of them can currently check is whether they are all holding hashes of
the SAME chain.

Nothing in the design so far stops an operator running two histories in
parallel. Serve chain A to one witness, chain B to an auditor. Both get a
valid-looking tip. Both anchor it. Both verify perfectly against the copy
they were given. Neither can tell, because there is no way to ask the
question that would expose it:

    is the tip you are holding actually an ancestor of my current head?

That is the split-view attack. Witnessing does not stop it. Anchoring does
not stop it - two forks can both be anchored. It is the last place an
operator can lie, and it is the one nobody in compliance has closed,
because the defence came out of Certificate Transparency and has not
crossed over.

WHAT THIS DOES
--------------
Builds an ordered Merkle tree over the audit chain and answers one
question for anybody, forever, without our cooperation:

    GET /x/consistency/ancestor?tip=<any tip we ever served>

If that tip is on our chain, we return its position and a proof, against
our current head, that it is still there and still in the same place. If
it is not on our chain, we say so - and the party holding it knows they
were served a history we no longer stand behind.

Every witness can check every tip they have ever held, automatically, on a
timer, for as long as they keep the tips. Which means we cannot show two
faces to the network: the moment any holder of any old tip checks it, a
fork stops being hidden and becomes provable arithmetic.

APPEND-ONLY, PROVED RATHER THAN ASSERTED
----------------------------------------
    GET /x/consistency/proof?first=21&second=48

Proves the log at size 21 is a PREFIX of the log at size 48. Not that both
exist - that the second was reached from the first by appending only, with
nothing inserted, removed or reordered in between. That is the actual
meaning of "append-only", and until now it has been a claim rather than
something a stranger could check.

WHY THE MATHS IS BORROWED, NOT INVENTED
---------------------------------------
The tree here follows RFC 6962 - Certificate Transparency - deliberately,
including its leaf and node prefixes and its split at the largest power of
two. Anyone who has implemented a CT verifier can point it at this and it
will work. Inventing a bespoke tree would mean nobody could check us
without writing new code first, which is the opposite of the point.

Note this tree is ORDERED, unlike the sorted tree in modules/complete.py.
The two answer different questions. Sorted proves what is absent. Ordered
proves nothing was reordered. They are not interchangeable and both are
needed.

HONEST LIMITS
-------------
  - This proves our published chain is internally append-only and that a
    given tip belongs to it. It says nothing about whether an entry should
    have been written in the first place.
  - A fork is only DETECTED if someone actually checks a tip they were
    given. The network has to do its half. That is why the route is public
    and needs no account - so checking costs nothing and can be automated.
  - If nobody ever holds an old tip of ours, there is nothing to check us
    against. Detection scales with how many witnesses keep history, which
    is another reason breadth matters more than depth.
  - Recomputation is O(n) hashing over the chain. Cached per size. On a
    very large log a checkpoint-based approach would be better; that is
    written down rather than hidden.

    GET  /x/consistency/root         current size and root      (public)
    GET  /x/consistency/ancestor     is this tip on our chain    (public)
    GET  /x/consistency/proof        prefix proof between sizes  (public)
    GET  /x/consistency/spec         the exact hashing rules     (public)
    POST /x/consistency/verify       check a proof we gave out   (public)
    POST /x/consistency/checkpoint   seal the current root       (keyed)
"""

import hashlib
import re
import threading
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# All the read routes are open. A consistency check you need an account to
# run is worthless - the party most likely to want it is the one who has
# stopped trusting us.
PUBLIC = {("GET", "root"), ("GET", "ancestor"), ("GET", "proof"),
          ("GET", "spec"), ("POST", "verify")}

# RFC 6962 domain separation. Leaf and internal hashes must never be
# confusable or an internal node can be passed off as a leaf.
LEAF_BYTE = b"\x00"
NODE_BYTE = b"\x01"

MAX_LEAVES = 500000

_ready = False
_cache = {"size": -1, "leaves": [], "root": None, "built": 0}
_cache_lock = threading.Lock()


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS consistency_checkpoint("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,tree_size INTEGER,"
                  "root TEXT,taken REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cons_size "
                  "ON consistency_checkpoint(tree_size)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# RFC 6962 tree
# ----------------------------------------------------------------------

def _leaf(value):
    return hashlib.sha256(LEAF_BYTE + value.encode("utf-8")).digest()


def _node(left, right):
    return hashlib.sha256(NODE_BYTE + left + right).digest()


def _split(n):
    """Largest power of two strictly less than n. RFC 6962 splits here."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(leaves):
    """Merkle Tree Hash over an ordered slice. Returns raw bytes."""
    n = len(leaves)
    if n == 0:
        return hashlib.sha256(b"").digest()
    if n == 1:
        return _leaf(leaves[0])
    k = _split(n)
    return _node(_mth(leaves[:k]), _mth(leaves[k:]))


def _inclusion(index, leaves):
    """Audit path for leaf at index within this slice. Raw bytes list."""
    n = len(leaves)
    if n <= 1:
        return []
    k = _split(n)
    if index < k:
        return _inclusion(index, leaves[:k]) + [_mth(leaves[k:])]
    return _inclusion(index - k, leaves[k:]) + [_mth(leaves[:k])]


def _subproof(m, leaves, is_root):
    n = len(leaves)
    if m == n:
        return [] if is_root else [_mth(leaves)]
    k = _split(n)
    if m <= k:
        return _subproof(m, leaves[:k], is_root) + [_mth(leaves[k:])]
    return _subproof(m - k, leaves[k:], False) + [_mth(leaves[:k])]


def _consistency(m, leaves):
    """Proof that the tree of the first m leaves is a prefix of this one."""
    if m <= 0 or m > len(leaves):
        return None
    if m == len(leaves):
        return []
    return _subproof(m, leaves, True)


def _hexed(nodes):
    return [n.hex() for n in nodes]


# ----------------------------------------------------------------------
# reading the chain
# ----------------------------------------------------------------------

def _load(ctx):
    """Every audit hash in order, cached until the chain grows.

    Order is the point here - this is not the sorted tree from
    modules/complete.py and the two must never be confused.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT COUNT(*) FROM audit_log").fetchone()
    size = int(row[0]) if row else 0

    with _cache_lock:
        if _cache["size"] == size and _cache["root"] is not None:
            return _cache["leaves"], _cache["root"], size, None

    if size > MAX_LEAVES:
        return None, None, size, "chain holds %d entries, above the %d cap for live recomputation" % (size, MAX_LEAVES)

    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT audit_hash FROM audit_log ORDER BY id ASC").fetchall()
    leaves = [str(r[0]) for r in rows if r[0]]
    root = _mth(leaves)

    with _cache_lock:
        _cache["size"] = len(leaves)
        _cache["leaves"] = leaves
        _cache["root"] = root
        _cache["built"] = time.time()

    return leaves, root, len(leaves), None


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _root(ctx):
    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503
    return {"tree_size": size, "root": root.hex(), "consistency_version": VERSION,
            "algorithm": "RFC 6962 Merkle Tree Hash over audit hashes in write order",
            "note": "Record this alongside any tip you hold. Later you can ask us to prove the "
                    "log you saw is a prefix of the log we serve today.",
            "check": "/x/consistency/proof?first=<your size>&second=%d" % size,
            "spec": "/x/consistency/spec"}, 200


def _ancestor(ctx, data):
    tip = str(data.get("tip", "")).strip().lower()
    if not tip:
        return {"error": "tip_required",
                "message": "Any tip we ever served you. We will prove whether it is still on "
                           "the chain we serve now."}, 400

    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503

    try:
        index = leaves.index(tip)
    except ValueError:
        return {"on_chain": False, "tip": tip, "tree_size": size, "root": root.hex(),
                "what_this_means": "This tip is not in the chain we serve. Either it was never "
                                   "ours, or it belongs to a history we are no longer publishing. "
                                   "If we gave you this tip, that is a fork and you now have "
                                   "evidence of it.",
                "keep_this": "This response, the tip, and whatever we originally sent you with "
                             "it. Together they are the record of the discrepancy.",
                "consistency_version": VERSION}, 409

    path = _inclusion(index, leaves)
    return {"on_chain": True, "tip": tip, "leaf_index": index, "height": index + 1,
            "tree_size": size, "root": root.hex(),
            "inclusion_proof": _hexed(path),
            "consistency_version": VERSION,
            "what_this_proves": "This tip sits at position %d of a chain of %d, and the current "
                                "root recomputes from it. It has not been moved, removed or "
                                "reordered since we gave it to you." % (index, size),
            "verify_yourself": "/x/consistency/spec has the rules. Recompute upward from the "
                               "leaf and compare with the root above.",
            "prefix_proof": "/x/consistency/proof?first=%d&second=%d" % (index + 1, size)}, 200


def _proof(ctx, data):
    try:
        first = int(data.get("first", 0))
        second = int(data.get("second", 0) or 0)
    except (TypeError, ValueError):
        return {"error": "bad_sizes", "message": "first and second are tree sizes, as integers"}, 400

    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503
    if not second:
        second = size
    if first < 1 or first > second or second > size:
        return {"error": "bad_range",
                "message": "Need 1 <= first <= second <= %d" % size,
                "tree_size": size}, 400

    older = leaves[:first]
    newer = leaves[:second]
    proof = _consistency(first, newer)
    if proof is None:
        return {"error": "no_proof", "message": "could not build a proof for that range"}, 400

    return {"first": first, "second": second,
            "first_root": _mth(older).hex(),
            "second_root": _mth(newer).hex(),
            "consistency_proof": _hexed(proof),
            "consistency_version": VERSION,
            "what_this_proves": "The log at size %d is a prefix of the log at size %d. Nothing "
                                "was inserted, removed or reordered between them - only "
                                "appended. That is what append-only actually means, and this is "
                                "it demonstrated rather than asserted." % (first, second),
            "algorithm": "RFC 6962 section 2.1.2",
            "spec": "/x/consistency/spec"}, 200


def _verify(data):
    """Recompute an inclusion proof. Convenience only - anyone relying on
    us to check our own proof has not checked anything."""
    leaf_value = str(data.get("leaf", data.get("tip", ""))).strip().lower()
    index = data.get("index", data.get("leaf_index"))
    size = data.get("tree_size")
    root = str(data.get("root", "")).strip().lower()
    proof = data.get("inclusion_proof", data.get("proof"))

    if not leaf_value or not HEX64.match(root) or not isinstance(proof, list):
        return {"error": "leaf_root_and_proof_required"}, 400
    try:
        index = int(index)
        size = int(size)
    except (TypeError, ValueError):
        return {"error": "index_and_tree_size_required"}, 400
    if index < 0 or size <= 0 or index >= size:
        return {"error": "index_out_of_range"}, 400

    current = _leaf(leaf_value)
    node_index, last_index = index, size - 1
    try:
        for step in proof:
            sibling = bytes.fromhex(str(step))
            if node_index % 2 == 1 or node_index == last_index:
                if node_index % 2 == 1:
                    current = _node(sibling, current)
                else:
                    current = _node(sibling, current)
                while node_index % 2 == 0 and node_index != 0:
                    node_index //= 2
                    last_index //= 2
            else:
                current = _node(current, sibling)
            node_index //= 2
            last_index //= 2
    except Exception as exc:
        return {"error": "bad_proof", "message": str(exc)[:200]}, 400

    return {"valid": current.hex() == root,
            "computed_root": current.hex(), "given_root": root,
            "note": "Recomputed from the leaf upward using RFC 6962 audit path rules."}, 200


def _checkpoint(ctx, api_key):
    """Seal the current size and root into the chain itself.

    A checkpoint is our own signature on 'this is what the log looked like
    at this moment'. Once anchored, publishing a different history for that
    size contradicts something we already sealed and externally timestamped.
    """
    leaves, root, size, why = _load(ctx)
    if why:
        return {"error": "too_large", "message": why, "tree_size": size}, 503

    now = time.time()
    root_hex = root.hex()
    ev = {"user_id": "cons:%d" % size, "action": "consistency_checkpoint", "amount": 0,
          "country": "UK", "device_id": "consistency", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CHECKPOINT_SEALED", "score": 0, "consistency_version": VERSION,
           "tree_size": size, "root": root_hex,
           "detail": "size=%d;root=%s" % (size, root_hex)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO consistency_checkpoint(api_key,tree_size,root,taken,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, size, root_hex, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"tree_size": size, "root": root_hex, "taken_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Commits our own view of the log at this size, inside the log, "
                              "where it gets anchored with everything else. Serving a different "
                              "history for this size now contradicts a sealed, timestamped "
                              "record of our own making.",
            "note": "The checkpoint itself becomes an entry, so the next size is larger. That is "
                    "expected and does not affect the proof for this one."}, 200


def _spec():
    return {
        "consistency_version": VERSION,
        "based_on": "RFC 6962 (Certificate Transparency), deliberately unmodified so existing "
                    "verifiers work against this without new code",
        "leaves": "the audit_hash of every chain entry, in write order (id ascending), as "
                  "lowercase hex strings encoded UTF-8",
        "empty_root": hashlib.sha256(b"").hexdigest(),
        "leaf_hash": "sha256(0x00 || leaf_value_utf8)",
        "node_hash": "sha256(0x01 || left || right)",
        "split": "for n > 1 leaves, split at k = the largest power of two strictly less than n",
        "inclusion": "RFC 6962 section 2.1.1 audit path",
        "consistency": "RFC 6962 section 2.1.2 - proves the tree at size m is a prefix of the "
                       "tree at size n",
        "ordered_not_sorted": "This tree is in write order. /x/complete uses a SORTED tree, "
                              "which answers a different question (absence). Do not confuse the "
                              "two - the roots will not match and are not meant to.",
        "how_to_catch_us": "Keep every tip and root we ever hand you. Ask /x/consistency/ancestor "
                           "about the old ones on a timer. If one ever comes back on_chain false, "
                           "or a prefix proof fails to verify, we have served two histories and "
                           "you can prove it without our help.",
        "why_published": "Because a log nobody can check is a log you are being asked to trust.",
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
        if action == "root":
            return _root(ctx)
        if action == "ancestor":
            return _ancestor(ctx, data)
        if action == "proof":
            return _proof(ctx, data)

    if method == "POST":
        if action == "verify":
            return _verify(data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "checkpoint":
            return _checkpoint(ctx, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "root", "ancestor", "proof"],
            "POST": ["verify", "checkpoint"]}, 404

```


## `modules/console.py`

954 lines, 40598 bytes

```python
"""
modules/console.py  -  the operator console at /console

WHY IT EXISTS
-------------
Half the useful routes are keyed POSTs. A browser address bar can only issue
GETs without a header, so from a phone those routes are unreachable - which is
most of the time, for this operator.

This serves one page that can reach them. The key is typed in, held in a
variable for that tab, and never written to storage. Close the tab and it is
gone.

WHAT IT CAN DO
--------------
  continuity/issue       grant authority, and delegate it onward
  continuity/exercise    evaluate an action against the whole lineage
  reconcile/plan         fix the sample before any data is requested
  reconcile/submit       seal the comparison, mismatches included
  fingerprint/self       score the 28-vector battery on our own engine
  fingerprint/probe      fire it at somebody else's endpoint and compare
  fingerprint/history    past comparisons
  codebase/seal          hash the tree, seal the manifest with a declaration
  publish/seal           seal the exact bytes a live page is serving

SAME PATCH AS network.py
------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime, adds one path, and
leaves every other path alone. Idempotent, in memory, reverts on restart.

And the same catch: after every deploy, one /x/ request has to arrive before
/console exists. Opening /x/console/status does it.

NOT LINKED FROM ANYWHERE
------------------------
No link on the site, noindex on the page. It holds no secrets - every route it
calls checks the key itself - but there is no reason to advertise it either.
"""

import importlib
import sys

VERSION = "1.3"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/console", "/console.html")

_patched = [False]

# Every page on this deployment is served by a runtime patch, and a module is
# only imported when a request reaches its own /x/ prefix. So after a deploy,
# each page stays 404 until somebody remembers to poke it - which is a stupid
# thing to ask a person to remember, and it has been asked too many times.
#
# One touch here arms all of them. Point Railway's healthcheck at
# /x/console/status and the container arms itself before it ever serves a
# request.
SIBLINGS = ("selfcheck", "standard", "verifier", "network", "publish", "continuity")

_armed = {}


def _arm_siblings(ctx):
    for name in SIBLINGS:
        if _armed.get(name):
            continue
        mod = None
        for path in ("modules." + name, name):
            try:
                mod = importlib.import_module(path)
                break
            except Exception:
                continue
        if mod is None or not hasattr(mod, "handle"):
            _armed[name] = "not found"
            continue
        try:
            mod.handle("GET", "status", {}, None, ctx)
            _armed[name] = "armed"
            print("CONSOLE: armed " + name, flush=True)
        except Exception as exc:
            _armed[name] = "failed: " + str(exc)[:80]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Console — AILeash</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0f1e; --panel:#131b2e; --panel2:#1a2338; --edge:rgba(201,168,76,.22);
  --gold:#c9a84c; --gold-dim:#8a7233;
  --text:#f2efe6; --mute:rgba(242,239,230,.42);
  --allow:#1a9e6e; --challenge:#c07a1d; --block:#c8362b; --ok:#7fe3b0;
  --disp:Fraunces,Georgia,serif; --body:'Space Grotesk',system-ui,sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
body{background:var(--ink);color:var(--text);font-family:var(--body);
  font-size:16px;line-height:1.6;padding:0 0 60px;
  background-image:repeating-linear-gradient(90deg,transparent 0 39px,rgba(201,168,76,.05) 39px 40px)}
.wrap{max-width:640px;margin:0 auto;padding:0 18px}

header{padding:34px 0 22px;border-bottom:1px solid var(--edge);margin-bottom:26px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.24em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
h1{font-family:var(--disp);font-weight:900;font-size:clamp(30px,8vw,44px);
  line-height:1;letter-spacing:-.02em}
h1 span{color:var(--gold)}
.sub{color:var(--mute);font-size:14.5px;margin-top:12px;max-width:44ch}

label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--mute);margin-bottom:7px}
input,textarea{width:100%;background:var(--panel);border:1px solid var(--edge);
  color:var(--text);font-family:var(--mono);font-size:13px;padding:12px 13px;
  border-radius:4px;outline:none}
input:focus,textarea:focus{border-color:var(--gold)}
textarea{resize:vertical;min-height:70px;font-family:var(--body);font-size:14px}

.keybar{background:var(--panel2);border:1px solid var(--edge);border-radius:6px;
  padding:16px;margin-bottom:26px}
.keynote{font-size:12px;color:var(--mute);margin-top:9px;line-height:1.55}

.op{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
  margin-bottom:14px;overflow:hidden}
.op-head{display:flex;align-items:baseline;gap:10px;padding:15px 16px;cursor:pointer;
  user-select:none}
.op-head:hover{background:var(--panel2)}
.op-n{font-family:var(--mono);font-size:10px;color:var(--gold-dim);letter-spacing:.1em}
.op-t{font-family:var(--disp);font-weight:600;font-size:18px;letter-spacing:-.01em}
.op-r{margin-left:auto;font-family:var(--mono);font-size:10px;color:var(--mute)}
.op-body{padding:0 16px 16px;display:none}
.op.open .op-body{display:block}
.op-why{font-size:13.5px;color:var(--mute);margin-bottom:14px;line-height:1.6}
.field{margin-bottom:12px}

button{width:100%;background:var(--gold);color:var(--ink);border:none;border-radius:4px;
  padding:14px;font-family:var(--body);font-weight:700;font-size:14.5px;cursor:pointer;
  transition:background .15s}
button:hover:not(:disabled){background:#dbbd63}
button:disabled{opacity:.45;cursor:default}
button.quiet{background:transparent;color:var(--mute);border:1px solid var(--edge)}
button.quiet:hover:not(:disabled){color:var(--text);border-color:var(--gold)}

/* ---- the readout: this is the thing worth building ---- */
#out{margin-top:26px}
.verdict{border:1px solid var(--edge);border-radius:6px;background:var(--panel);
  overflow:hidden;margin-bottom:14px}
.v-head{padding:22px 18px;border-bottom:1px solid var(--edge)}
.v-word{font-family:var(--disp);font-weight:900;font-size:clamp(28px,9vw,42px);
  line-height:1;letter-spacing:-.02em}
.v-IDENTICAL,.v-err{color:var(--block)}
.v-DERIVED{color:var(--challenge)}
.v-SAME.SHAPE,.v-SIMILAR{color:var(--gold)}
.v-UNRELATED,.v-ok{color:var(--allow)}
.v-INCONCLUSIVE{color:var(--mute)}
.v-ALLOW{color:var(--allow)}
.v-CHALLENGE{color:var(--challenge)}
.v-BLOCK{color:var(--block)}
.lin{padding:16px 18px;border-bottom:1px solid var(--edge)}
.lin-hop{display:flex;gap:10px;align-items:baseline;padding:8px 0;
  border-bottom:1px solid rgba(201,168,76,.10)}
.lin-hop:last-child{border-bottom:none}
.lin-d{font-family:var(--mono);font-size:10px;color:var(--gold-dim);min-width:24px}
.lin-g{font-family:var(--mono);font-size:12px;color:var(--gold)}
.lin-s{font-size:12.5px;color:var(--mute)}
.lin-bad{color:var(--block)}
.v-stats{display:flex;flex-wrap:wrap;gap:18px;padding:14px 18px;
  border-bottom:1px solid var(--edge);font-family:var(--mono);font-size:11px}
.v-stats b{display:block;font-family:var(--disp);font-size:19px;color:var(--text);
  font-weight:600;margin-top:3px}
.v-stats span{color:var(--mute);letter-spacing:.1em;text-transform:uppercase}

/* paired bars: ours above, theirs below, one column per vector */
.strip{padding:18px}
.strip-l{font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
.bars{display:flex;gap:2px;align-items:stretch;height:96px}
.bar{flex:1;display:flex;flex-direction:column;justify-content:center;gap:2px;min-width:0}
.bar i{display:block;border-radius:1px;transition:height .35s ease}
.bar .mine{background:var(--gold);align-self:flex-end;width:100%}
.bar .theirs{background:rgba(242,239,230,.35);width:100%}
.bar.match .theirs{background:var(--block)}
.bar-key{display:flex;gap:16px;margin-top:12px;font-family:var(--mono);font-size:10px;
  color:var(--mute);flex-wrap:wrap}
.dot{display:inline-block;width:8px;height:8px;border-radius:1px;margin-right:6px;
  vertical-align:middle}

pre{font-family:var(--mono);font-size:11.5px;line-height:1.65;background:#080c16;
  color:var(--ok);padding:15px;border-radius:5px;overflow-x:auto;
  border:1px solid var(--edge);max-height:340px}
.msg{font-family:var(--mono);font-size:12.5px;padding:13px 15px;border-radius:5px;
  border:1px solid var(--edge);color:var(--mute);margin-bottom:14px}
.msg.bad{color:#ffb4ad;border-color:rgba(200,54,43,.5);background:rgba(200,54,43,.08)}
.msg.good{color:var(--ok);border-color:rgba(127,227,176,.35);background:rgba(26,158,110,.08)}
.working{font-family:var(--mono);font-size:12px;color:var(--gold)}
.working:after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
footer{margin-top:34px;padding-top:18px;border-top:1px solid var(--edge);
  font-family:var(--mono);font-size:10.5px;color:var(--mute);line-height:1.8}
a{color:var(--gold)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">AILeash · operator console</p>
  <h1>Keyed <span>routes</span></h1>
  <p class="sub">The endpoints a browser cannot reach on its own. Your key stays in this tab and is never stored.</p>
</header>

<div class="keybar">
  <label for="key">API key</label>
  <input id="key" type="password" placeholder="al_live_…" autocomplete="off" spellcheck="false">
  <p class="keynote">Held in memory for this tab only. Close it and the key is gone — nothing is written to the device.</p>
</div>

<div class="op" id="op-self">
  <div class="op-head" onclick="toggle('op-self')">
    <span class="op-n">01</span><span class="op-t">Baseline</span>
    <span class="op-r">POST /x/fingerprint/self</span>
  </div>
  <div class="op-body">
    <p class="op-why">Runs the 28-vector battery through your own engine. Every probe is measured against this. Run it first — if it answers, the module can see your live scorer.</p>
    <button onclick="run('self')">Score the battery</button>
  </div>
</div>

<div class="op" id="op-probe">
  <div class="op-head" onclick="toggle('op-probe')">
    <span class="op-n">02</span><span class="op-t">Probe a target</span>
    <span class="op-r">POST /x/fingerprint/probe</span>
  </div>
  <div class="op-body">
    <p class="op-why">Fires the same battery at somebody else's scoring endpoint and compares the two sets of numbers. One request per vector with a gap between them.</p>
    <div class="field">
      <label for="t-url">Their scoring endpoint</label>
      <input id="t-url" type="url" placeholder="https://example.com/api/score" autocomplete="off">
    </div>
    <div class="field">
      <label for="t-fields">Field names, if theirs differ (optional)</label>
      <input id="t-fields" placeholder='{"amount":"value","trust":"history"}' autocomplete="off">
    </div>
    <div class="field">
      <label for="t-score">Where the score is in their reply (optional)</label>
      <input id="t-score" placeholder="risk_score" autocomplete="off">
    </div>
    <button onclick="run('probe')">Run the comparison</button>
  </div>
</div>

<div class="op" id="op-code">
  <div class="op-head" onclick="toggle('op-code')">
    <span class="op-n">03</span><span class="op-t">Seal the codebase</span>
    <span class="op-r">POST /x/codebase/seal</span>
  </div>
  <div class="op-body">
    <p class="op-why">Hashes every file, commits one manifest root, seals it with your declaration. Dated evidence of what you held and when.</p>
    <div class="field">
      <label for="c-author">Author</label>
      <input id="c-author" value="Justin Antony Dobson" autocomplete="off">
    </div>
    <div class="field">
      <label for="c-entity">Entity</label>
      <input id="c-entity" value="Monop Content" autocomplete="off">
    </div>
    <div class="field">
      <label for="c-stmt">Declaration</label>
      <textarea id="c-stmt">Scoring engine, weighting and trust decay authored solely by me.</textarea>
    </div>
    <button onclick="run('codebase')">Seal it</button>
  </div>
</div>

<div class="op" id="op-pub">
  <div class="op-head" onclick="toggle('op-pub')">
    <span class="op-n">04</span><span class="op-t">Seal a published page</span>
    <span class="op-r">POST /x/publish/seal</span>
  </div>
  <div class="op-body">
    <p class="op-why">Fetches a live page and seals the exact bytes served. Pins what the world could see on a given date, which is not the same as what was in the repo.</p>
    <div class="field">
      <label for="p-url">Page</label>
      <input id="p-url" type="url" value="https://sebbi.pro/" autocomplete="off">
    </div>
    <button onclick="run('publish')">Seal the page</button>
  </div>
</div>

<div class="op" id="op-hist">
  <div class="op-head" onclick="toggle('op-hist')">
    <span class="op-n">05</span><span class="op-t">Past probes</span>
    <span class="op-r">GET /x/fingerprint/history</span>
  </div>
  <div class="op-body">
    <p class="op-why">Every comparison you have run, with its verdict and receipt.</p>
    <button class="quiet" onclick="run('history')">Show them</button>
  </div>
</div>

<div class="op" id="op-spec">
  <div class="op-head" onclick="toggle('op-spec')">
    <span class="op-n">06</span><span class="op-t">Every command</span>
    <span class="op-r">GET /x/spec</span>
  </div>
  <div class="op-body">
    <p class="op-why">Walks every module on the router and reports what each one exposes, and which routes need a key. If you have forgotten what exists, this is the answer.</p>
    <button class="quiet" onclick="run('spec')">List them</button>
  </div>
</div>


<div class="op" id="op-auth">
  <div class="op-head" onclick="toggle('op-auth')">
    <span class="op-n">07</span><span class="op-t">Grant authority</span>
    <span class="op-r">POST /x/continuity/issue</span>
  </div>
  <div class="op-body">
    <p class="op-why">A root grant. It must be issued by a human, it must state a purpose, and it must expire. Whoever is named as accepting the risk is the person an incident lands on.</p>
    <div class="field">
      <label for="a-issuer">Issued by (human)</label>
      <input id="a-issuer" value="justin@monopcontent.com" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-subject">Granted to</label>
      <input id="a-subject" value="orchestrator" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-scope">Scope, comma separated</label>
      <input id="a-scope" value="payments.refund, payments.read" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-max">Maximum amount</label>
      <input id="a-max" value="5000" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-purpose">Purpose</label>
      <input id="a-purpose" value="resolve customer refund complaints" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-tags">Purpose tags, comma separated</label>
      <input id="a-tags" value="refunds, support" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-hours">Valid for (hours)</label>
      <input id="a-hours" value="24" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-deleg">Onward delegations allowed</label>
      <input id="a-deleg" value="2" autocomplete="off">
    </div>
    <div class="field">
      <label for="a-risk">Risk accepted by (leave blank to use the issuer)</label>
      <input id="a-risk" placeholder="risk.officer@example.com" autocomplete="off">
    </div>
    <button onclick="run('issue')">Issue the grant</button>
  </div>
</div>

<div class="op" id="op-deleg">
  <div class="op-head" onclick="toggle('op-deleg')">
    <span class="op-n">08</span><span class="op-t">Delegate it onward</span>
    <span class="op-r">POST /x/continuity/issue</span>
  </div>
  <div class="op-body">
    <p class="op-why">A child can narrow, never widen. Try raising the amount above the parent's and watch it refuse. A child that can delegate again must name its own risk acceptor.</p>
    <div class="field">
      <label for="d-parent">Parent grant id</label>
      <input id="d-parent" placeholder="g_…" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-issuer">Issued by</label>
      <input id="d-issuer" value="orchestrator" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-subject">Granted to</label>
      <input id="d-subject" value="refund-agent" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-scope">Scope, comma separated</label>
      <input id="d-scope" value="payments.refund" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-max">Maximum amount</label>
      <input id="d-max" value="200" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-purpose">Purpose</label>
      <input id="d-purpose" value="issue small refunds" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-tags">Purpose tags</label>
      <input id="d-tags" value="refunds" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-hours">Valid for (hours, must fit inside the parent)</label>
      <input id="d-hours" value="6" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-deleg">Onward delegations allowed</label>
      <input id="d-deleg" value="0" autocomplete="off">
    </div>
    <div class="field">
      <label for="d-risk">Risk accepted by (required if delegations above is not 0)</label>
      <input id="d-risk" placeholder="head.of.ops@example.com" autocomplete="off">
    </div>
    <button onclick="run('delegate')">Delegate</button>
  </div>
</div>

<div class="op" id="op-ex">
  <div class="op-head" onclick="toggle('op-ex')">
    <span class="op-n">09</span><span class="op-t">Exercise authority</span>
    <span class="op-r">POST /x/continuity/exercise</span>
  </div>
  <div class="op-body">
    <p class="op-why">The whole chain is re-derived at this moment, not trusted from when it was issued. Ask for more than the lineage allows and it names the grant and the invariant that broke.</p>
    <div class="field">
      <label for="e-grant">Grant id</label>
      <input id="e-grant" placeholder="g_…" autocomplete="off">
    </div>
    <div class="field">
      <label for="e-action">Action</label>
      <input id="e-action" value="payments.refund" autocomplete="off">
    </div>
    <div class="field">
      <label for="e-params">Parameters</label>
      <input id="e-params" value='{"amount": 150}' autocomplete="off">
    </div>
    <div class="field">
      <label for="e-tag">Declared purpose tag</label>
      <input id="e-tag" value="refunds" autocomplete="off">
    </div>
    <button onclick="run('exercise')">Evaluate it</button>
  </div>
</div>

<div class="op" id="op-plan">
  <div class="op-head" onclick="toggle('op-plan')">
    <span class="op-n">10</span><span class="op-t">Plan a reconciliation</span>
    <span class="op-r">POST /x/reconcile/plan</span>
  </div>
  <div class="op-body">
    <p class="op-why">Seals which records will be tested before any data is fetched. Once this runs you cannot choose a kinder sample, and an abandoned plan stays visible forever.</p>
    <div class="field">
      <label for="r-size">Sample size</label>
      <input id="r-size" value="10" autocomplete="off">
    </div>
    <div class="field">
      <label for="r-field">Field to reconcile</label>
      <input id="r-field" value="decision" autocomplete="off">
    </div>
    <button onclick="run('plan')">Fix the sample</button>
  </div>
</div>

<div class="op" id="op-sub">
  <div class="op-head" onclick="toggle('op-sub')">
    <span class="op-n">11</span><span class="op-t">Submit the comparison</span>
    <span class="op-r">POST /x/reconcile/submit</span>
  </div>
  <div class="op-body">
    <p class="op-why">The values from your own live system, against the sample that was already sealed. Fill these honestly - a mismatch is sealed as permanently as a match, and that is the only reason any of it means anything.</p>
    <div class="field">
      <label for="s-run">Run id</label>
      <input id="s-run" placeholder="RUN-XXXXXXXX" autocomplete="off">
    </div>
    <div class="field">
      <label for="s-results">Results, block index to live value</label>
      <textarea id="s-results" placeholder='{"41": "ALLOW", "58": "BLOCK"}'></textarea>
    </div>
    <button onclick="run('submit')">Seal the comparison</button>
  </div>
</div>

<div id="out"></div>

<footer>
  Public routes need no key and are not listed here.<br>
  Chain: <a href="/api/verify-chain">/api/verify-chain</a> · Clock: <a href="/api/anchor-status">/api/anchor-status</a> · Network: <a href="/x/witness/peers">/x/witness/peers</a>
</footer>

</div>

<script>
(function(){
  var out = document.getElementById('out');
  var busy = false;

  window.toggle = function(id){
    var el = document.getElementById(id);
    el.classList.toggle('open');
  };
  document.getElementById('op-self').classList.add('open');

  function esc(s){
    return String(s==null?'':s).replace(/[&<>"']/g,function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});
  }
  function msg(text, kind){
    out.innerHTML = '<div class="msg '+(kind||'')+'">'+esc(text)+'</div>';
  }
  function raw(obj){
    return '<pre>'+esc(JSON.stringify(obj,null,2))+'</pre>';
  }

  function key(){
    var k = document.getElementById('key').value.trim();
    if(!k){ msg('Paste your API key at the top first.','bad'); return null; }
    return k;
  }

  function parseJSONField(id){
    var v = document.getElementById(id).value.trim();
    if(!v) return null;
    try { return JSON.parse(v); }
    catch(e){ msg('That field-name map is not valid JSON. Example: {"amount":"value"}','bad'); return undefined; }
  }

  async function call(path, method, body){
    var k = key(); if(!k) return null;
    var opts = { method: method, headers: { 'Authorization':'Bearer '+k } };
    if(body){ opts.headers['Content-Type']='application/json'; opts.body=JSON.stringify(body); }
    var r = await fetch(path, opts);
    var d;
    try { d = await r.json(); } catch(e){ d = {error:'unreadable_response'}; }
    return { status: r.status, data: d };
  }

  function bars(perVector){
    var maxV = 0;
    perVector.forEach(function(p){
      maxV = Math.max(maxV, Math.abs(p.ours), Math.abs(p.theirs)); });
    if(maxV <= 0) maxV = 1;
    var html = '<div class="strip"><div class="strip-l">Every vector · yours above, theirs below</div><div class="bars">';
    perVector.forEach(function(p){
      var a = Math.max(2, Math.round((Math.abs(p.ours)/maxV)*44));
      var b = Math.max(2, Math.round((Math.abs(p.theirs)/maxV)*44));
      var match = Math.abs(p.delta) < 0.000001 ? ' match' : '';
      html += '<div class="bar'+match+'" title="'+esc(p.vector)+': '+p.ours+' vs '+p.theirs+'">'
           +  '<i class="mine" style="height:'+a+'px"></i>'
           +  '<i class="theirs" style="height:'+b+'px"></i></div>';
    });
    html += '</div><div class="bar-key">'
         +  '<span><i class="dot" style="background:var(--gold)"></i>yours</span>'
         +  '<span><i class="dot" style="background:var(--block)"></i>theirs, exact match</span>'
         +  '<span><i class="dot" style="background:rgba(242,239,230,.35)"></i>theirs, different</span>'
         +  '</div></div>';
    return html;
  }

  function csv(id){
    return document.getElementById(id).value.split(',')
      .map(function(x){ return x.trim(); }).filter(Boolean);
  }
  function num(id){
    var v = parseFloat(document.getElementById(id).value.trim());
    return isNaN(v) ? 0 : v;
  }
  function val(id){ return document.getElementById(id).value.trim(); }

  function renderGrant(d){
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">GRANTED</div>'
      + '<div class="v-why">Sealed at block ' + esc(d.block_index)
      + '. Depth ' + esc(d.depth) + '. Risk accepted by '
      + esc(d.risk_accepted_by || 'inherited from above') + '.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>grant</span><b style="font-family:var(--mono);font-size:12px">'
      + esc(d.grant) + '</b></div>'
      + '<div><span>expires</span><b style="font-size:13px">'
      + esc(String(d.not_after || '').slice(0,16)) + '</b></div>'
      + '</div></div>';
    // carry the id forward so the next step does not need copying by hand
    if(d.grant){
      var dp = document.getElementById('d-parent');
      var eg = document.getElementById('e-grant');
      if(dp && !dp.value) dp.value = d.grant;
      if(eg) eg.value = d.grant;
    }
    return html;
  }

  function renderExercise(d){
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-' + esc(d.verdict) + '">' + esc(d.verdict) + '</div>'
      + '<div class="v-why">' + esc(d.what_this_means || '') + '</div></div>'
      + '<div class="v-stats">'
      + '<div><span>authorised by</span><b style="font-size:13px">' + esc(d.authorised_by) + '</b></div>'
      + '<div><span>executed by</span><b style="font-size:13px">' + esc(d.executed_by) + '</b></div>'
      + '<div><span>risk accepted by</span><b style="font-size:13px">' + esc(d.risk_accepted_by) + '</b></div>'
      + '<div><span>hops</span><b>' + esc(d.delegation_depth) + '</b></div>'
      + '</div>';
    if(d.lineage && d.lineage.length){
      html += '<div class="lin"><div class="strip-l">Authority path, root first</div>';
      d.lineage.forEach(function(h){
        var bad = (h.integrity !== 'ok' || h.revoked) ? ' lin-bad' : '';
        html += '<div class="lin-hop"><span class="lin-d">' + esc(h.depth) + '</span>'
             +  '<span><span class="lin-g' + bad + '">' + esc(h.grant) + '</span>'
             +  '<div class="lin-s">' + esc(h.issuer) + ' &rarr; ' + esc(h.subject)
             +  ' · ' + esc((h.scope || []).join(', ')) + '</div></span></div>';
      });
      html += '</div>';
    }
    if(d.reasons && d.reasons.length){
      html += '<div class="lin"><div class="strip-l">'
           + (d.verdict === 'BLOCK' ? 'What broke' : 'What could not be settled')
           + '</div>';
      d.reasons.forEach(function(r){
        html += '<div class="lin-s" style="padding:5px 0">' + esc(r) + '</div>'; });
      if(d.broken_at){
        html += '<div class="lin-s" style="padding-top:8px;color:var(--block)">at grant '
             + esc(d.broken_at) + ' · ' + esc(d.broken_invariant) + '</div>';
      }
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  function renderPlan(d){
    // prefill the submit form with the sealed sample so the next step is typing
    // values, not transcribing block numbers
    var skeleton = {};
    (d.sample || []).forEach(function(s){ skeleton[String(s.block_index)] = ''; });
    var sr = document.getElementById('s-run');
    var ss = document.getElementById('s-results');
    if(sr) sr.value = d.run_id;
    if(ss) ss.value = JSON.stringify(skeleton, null, 1);
    document.getElementById('op-sub').classList.add('open');
    return '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">SAMPLE FIXED</div>'
      + '<div class="v-why">' + esc(d.sample_size) + ' records selected from the chain tip and '
      + 'sealed at block ' + esc(d.block_index) + ', before any data was requested. '
      + 'The submit form below has been filled with the block indices.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>run</span><b style="font-family:var(--mono);font-size:12px">'
      + esc(d.run_id) + '</b></div>'
      + '<div><span>field</span><b style="font-size:13px">' + esc(d.field) + '</b></div>'
      + '</div></div>';
  }

  function renderSubmit(d){
    var clean = (d.mismatched === 0 && d.missing === 0);
    return '<div class="verdict"><div class="v-head">'
      + '<div class="v-word ' + (clean ? 'v-ok' : 'v-BLOCK') + '">'
      + esc(d.match_rate_pct) + '%</div>'
      + '<div class="v-why">Sealed at block ' + esc(d.block_index)
      + ' whichever way it went. It cannot be withdrawn.</div></div>'
      + '<div class="v-stats">'
      + '<div><span>matched</span><b>' + esc(d.matched) + '</b></div>'
      + '<div><span>mismatched</span><b>' + esc(d.mismatched) + '</b></div>'
      + '<div><span>missing</span><b>' + esc(d.missing) + '</b></div>'
      + '</div></div>';
  }

  function renderProbe(d){
    var v = String(d.verdict||'').replace(/ /g,'.');
    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-'+esc(v)+'">'+esc(d.verdict)+'</div>'
      + '<div class="v-why">'+esc(d.why||'')+'</div></div>'
      + '<div class="v-stats">'
      +   '<div><span>exact</span><b>'+esc(d.exact_matches)+'/'+esc(d.answered)+'</b></div>'
      +   '<div><span>correlation</span><b>'+esc(d.correlation==null?'—':d.correlation)+'</b></div>'
      +   '<div><span>same order</span><b>'+esc(d.rank_correlation==null?'—':d.rank_correlation)+'</b></div>'
      + '</div>';
    if(d.per_vector && d.per_vector.length) html += bars(d.per_vector);
    html += '</div>';
    if(d.sealed) html += '<div class="msg good">Sealed at block '+esc(d.sealed.block_index)
      + ' · receipt '+esc(String(d.sealed.receipt).slice(0,20))+'…</div>';
    if(d.failures) html += '<div class="msg bad">'+esc(d.failure_note||'Some vectors were rejected.')+'</div>';
    html += raw(d);
    out.innerHTML = html;
  }

  function renderSpec(d){
    // the shape varies by version, so find the module list wherever it is
    var mods = d.modules || d.spec || d;
    var names = [];
    if(Array.isArray(mods)){
      mods.forEach(function(m){
        names.push(typeof m === 'string' ? {name:m} : m); });
    } else if(mods && typeof mods === 'object'){
      Object.keys(mods).forEach(function(k){
        var v = mods[k];
        names.push({name:k, detail:(v && typeof v === 'object') ? v : null}); });
    }
    if(!names.length) return '<div class="msg">Nothing listed. The raw reply is below.</div>';

    var html = '<div class="verdict"><div class="v-head">'
      + '<div class="v-word v-ok">' + names.length + ' modules</div>'
      + '<div class="v-why">Everything currently loaded on the router.</div></div>'
      + '<div class="strip">';
    names.forEach(function(m){
      var routes = '';
      if(m.detail){
        ['public','keyed','GET','POST','routes','actions'].forEach(function(k){
          var v = m.detail[k];
          if(Array.isArray(v) && v.length){
            routes += '<div style="color:var(--mute);font-size:11.5px;margin-top:3px">'
                   + esc(k) + ': ' + esc(v.join(', ')) + '</div>';
          }
        });
      }
      html += '<div style="padding:11px 0;border-bottom:1px solid var(--edge)">'
           +  '<span style="font-family:var(--mono);font-size:13px;color:var(--gold)">/x/'
           +  esc(m.name) + '/</span>' + routes + '</div>';
    });
    html += '</div></div>';
    return html;
  }

  window.run = async function(what){
    if(busy) return;
    var path, method='POST', body=null;

    if(what==='self'){ path='/x/fingerprint/self'; body={}; }

    else if(what==='probe'){
      var url = document.getElementById('t-url').value.trim();
      if(!url){ msg('Give the endpoint you want compared.','bad'); return; }
      var fields = parseJSONField('t-fields');
      if(fields === undefined) return;
      body = { url: url };
      if(fields) body.fields = fields;
      var sk = document.getElementById('t-score').value.trim();
      if(sk) body.score_key = sk;
      path='/x/fingerprint/probe';
    }

    else if(what==='codebase'){
      path='/x/codebase/seal';
      body = { author: document.getElementById('c-author').value.trim(),
               entity: document.getElementById('c-entity').value.trim(),
               statement: document.getElementById('c-stmt').value.trim() };
    }

    else if(what==='publish'){
      var pu = document.getElementById('p-url').value.trim();
      if(!pu){ msg('Give the page to seal.','bad'); return; }
      path='/x/publish/seal'; body={ url: pu };
    }

    else if(what==='issue' || what==='delegate'){
      var pre = (what === 'issue') ? 'a-' : 'd-';
      var hours = num(pre + 'hours') || 1;
      body = {
        issuer: val(pre + 'issuer'),
        issuer_kind: (what === 'issue') ? 'human' : 'agent',
        subject: val(pre + 'subject'),
        scope: csv(pre + 'scope'),
        constraints: { max_amount: num(pre + 'max') },
        purpose: val(pre + 'purpose'),
        purpose_tags: csv(pre + 'tags'),
        not_after: Math.floor(Date.now() / 1000) + Math.round(hours * 3600),
        delegations_left: Math.round(num(pre + 'deleg'))
      };
      var risk = val(pre + 'risk');
      if(risk) body.risk_accepted_by = risk;
      if(what === 'delegate'){
        var par = val('d-parent');
        if(!par){ msg('Give the parent grant id. Issue a root first if you have none.','bad'); return; }
        body.parent = par;
        // a child window must sit inside the parent's, so start it now
        body.not_before = Math.floor(Date.now() / 1000);
      }
      path = '/x/continuity/issue';
    }

    else if(what==='exercise'){
      var g = val('e-grant');
      if(!g){ msg('Give the grant id you are exercising.','bad'); return; }
      var params = {};
      var praw = val('e-params');
      if(praw){
        try { params = JSON.parse(praw); }
        catch(e){ msg('Parameters must be JSON. Example: {"amount": 150}','bad'); return; }
      }
      body = { grant: g, action: val('e-action'), params: params };
      var tag = val('e-tag');
      if(tag) body.purpose_tag = tag;
      path = '/x/continuity/exercise';
    }

    else if(what==='plan'){
      body = { sample_size: Math.round(num('r-size')) || 10, field: val('r-field') || 'decision' };
      path = '/x/reconcile/plan';
    }

    else if(what==='submit'){
      var rid = val('s-run');
      if(!rid){ msg('Give the run id from the plan step.','bad'); return; }
      var results;
      try { results = JSON.parse(val('s-results')); }
      catch(e){ msg('Results must be JSON: {"block index": "live value"}','bad'); return; }
      var empties = Object.keys(results).filter(function(k){
        return String(results[k]).trim() === ''; });
      if(empties.length){
        msg('Fill every value first — ' + empties.length + ' left blank. A blank is not a '
            + 'match, it is a missing record, and it will be sealed as one.','bad');
        return;
      }
      body = { run_id: rid, results: results };
      path = '/x/reconcile/submit';
    }

    else if(what==='history'){ path='/x/fingerprint/history'; method='GET'; }

    else if(what==='spec'){ path='/x/spec'; method='GET'; }

    else return;

    busy = true;
    out.innerHTML = '<div class="msg"><span class="working">'
      + (what==='probe' ? 'Firing 28 vectors, one at a time' : 'Working') + '</span></div>';

    try{
      var res = await call(path, method, body);
      if(!res){ busy=false; return; }

      if(res.status === 401){
        msg('That key was refused. Check it and try again.','bad');
      } else if(res.status === 404 && res.data && res.data.error === 'unknown_module'){
        msg('That module is not deployed yet.','bad');
      } else if(res.status === 429){
        msg('Rate limited. Give it a minute.','bad');
      } else if(res.status >= 400){
        out.innerHTML = '<div class="msg bad">'
          + esc((res.data && (res.data.message || res.data.error)) || ('HTTP '+res.status))
          + '</div>' + raw(res.data);
      } else if(what === 'probe' && res.data.verdict){
        renderProbe(res.data);
      } else if(what === 'self' && res.data.scores){
        out.innerHTML = '<div class="msg good">Baseline read from '
          + esc(res.data.source) + ' · ' + esc(res.data.vectors) + ' vectors</div>' + raw(res.data);
      } else if((what === 'issue' || what === 'delegate') && res.data.grant){
        out.innerHTML = renderGrant(res.data) + raw(res.data);
      } else if(what === 'exercise' && res.data.verdict){
        out.innerHTML = renderExercise(res.data) + raw(res.data);
      } else if(what === 'plan' && res.data.run_id){
        out.innerHTML = renderPlan(res.data) + raw(res.data);
      } else if(what === 'submit' && res.data.match_rate_pct !== undefined){
        out.innerHTML = renderSubmit(res.data) + raw(res.data);
      } else if(what === 'spec'){
        out.innerHTML = renderSpec(res.data) + raw(res.data);
      } else {
        out.innerHTML = '<div class="msg good">Done.</div>' + raw(res.data);
      }
    } catch(e){
      msg('Could not reach the server. That is a real failure, not a staged one.','bad');
    }
    busy = false;
  };
})();
</script>
</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_console_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._console_patched = True
    _patched[0] = True
    print("CONSOLE: /console page installed at runtime", flush=True)
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
            print("CONSOLE: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    try:
        _arm_siblings(ctx)
    except Exception as exc:
        print("CONSOLE: sibling arming failed - " + str(exc)[:120], flush=True)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/console",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "armed": dict(_armed),
            "healthcheck": ("Point Railway at /x/console/status. It runs on every new "
                            "container before traffic arrives, and arms every page "
                            "route here in one go."),
            "note": ("The page holds no credentials. Every route it calls checks "
                     "the key itself."),
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```
