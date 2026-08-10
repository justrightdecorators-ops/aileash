# Codebase — part 3 of 19

Contains:
- `modules/consistency.py`
- `modules/console.py`
- `modules/continuity.py`


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

556 lines, 23275 bytes

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

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/console", "/console.html")

_patched = [False]


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
.v-why{font-size:14px;color:var(--mute);margin-top:11px;line-height:1.6}
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

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/console",
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "note": ("The page holds no credentials. Every route it calls checks "
                     "the key itself."),
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


## `modules/continuity.py`

1337 lines, 64030 bytes

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

VERSION = "1.1"

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
        engine_event = {
            "user_id": (chain[-1]["subject"] if chain else "unknown")[:64],
            "action": action,
            "amount": params.get("amount", 0),
            "country": params.get("country", "GB"),
            "device_id": params.get("device_id", "agent"),
            "anomaly": params.get("anomaly", 0),
            "device_risk": params.get("device_risk", 0),
        }
        try:
            engine_event["amount"] = _num(engine_event["amount"])
        except (TypeError, ValueError):
            engine_event["amount"] = 0
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
