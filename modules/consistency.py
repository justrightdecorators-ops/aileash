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
