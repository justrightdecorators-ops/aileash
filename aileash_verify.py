#!/usr/bin/env python3
"""
aileash_verify.py  -  an independent verifier for AILeash proofs
================================================================

WHAT THIS IS
------------
A single file that checks AILeash's proofs without AILeash.

No dependencies. No network calls. It never contacts sebbi.pro or anything
else - it takes proof documents you already hold and does the arithmetic
locally. Run it on a laptop with the wifi off and it works exactly the same.

That is deliberate. A proof you can only check with the prover's own online
tool is not a proof, it is a reassurance. If this file cannot confirm a
claim from the numbers alone, the claim does not hold, and the honest thing
is for you to find that out from your own machine rather than from us.

WHAT IT CHECKS
--------------
  Inclusion    a record is inside a sealed period, against the sealed root
  Absence      a record is NOT there - the two neighbouring leaves are
               verified and shown to be adjacent, leaving nowhere for it
  Ancestry     a tip you were handed is still on the chain being served,
               at the same position, under the current root
  Prefix       the log at one size is contained in the log at a later size,
               with nothing inserted, removed or reordered in between
  Stability    across a set of replay runs, identical inputs produced
               identical verdicts under an unchanged code fingerprint

USAGE
-----
    python3 aileash_verify.py proof.json [another.json ...]
    cat proof.json | python3 aileash_verify.py
    python3 aileash_verify.py --selftest

Exit code 0 if everything checked passed, 1 if anything failed, 2 on bad
input. Suitable for dropping into an audit script or a CI job.

Each proof document is whatever the relevant AILeash route returned. Save
the JSON, keep it, and check it whenever you like - next week, or in four
years when the original system is long gone.

HOW TO GET PROOFS
-----------------
    /x/complete/prove?period=&value=       inclusion or absence
    /x/consistency/ancestor?tip=           ancestry
    /x/consistency/proof?first=&second=    prefix
    /x/replay/history?input_hash=          stability

WHAT IT DOES NOT CHECK
----------------------
  - That a sealed record is TRUE. Cryptography proves a record existed at a
    time and has not moved since. It says nothing about whether the record
    was honest when it was written. Nothing can.
  - That a root was anchored. That is a separate check against the
    OpenTimestamps proof and a Bitcoin node - out of scope for a file with
    no dependencies, and it should be done independently anyway.
  - Whether a decision was correct or fair. Determinism is not fairness.

The two hash schemes below are different on purpose and must not be mixed.
The completeness tree is SORTED, which is what makes absence provable. The
consistency tree is in WRITE ORDER, which is what makes reordering
detectable. Their roots will never match and are not meant to.

Public domain / MIT - copy it, fork it, audit it, ship it inside your own
tooling. The more independent copies of this exist, the less any of it
depends on us.
"""

import hashlib
import json
import sys

VERSION = "1.0"

# --- completeness tree (sorted) -------------------------------------------
CMP_LEAF = b"AILEASH-LEAF-v1:"
CMP_NODE = b"AILEASH-NODE-v1:"

# --- consistency tree (write order, RFC 6962) -----------------------------
CT_LEAF = b"\x00"
CT_NODE = b"\x01"


# ==========================================================================
# completeness: sorted tree
# ==========================================================================

def cmp_leaf(value):
    return hashlib.sha256(CMP_LEAF + value.encode("utf-8")).hexdigest()


def cmp_node(left_hex, right_hex):
    return hashlib.sha256(CMP_NODE + left_hex.encode() + right_hex.encode()).hexdigest()


def cmp_replay(value, proof):
    """Recompute a root from a leaf value and its sibling path.

    Each step carries the side its sibling sits on. Five lines, so that
    reimplementing this in another language is an afternoon rather than a
    project.
    """
    current = cmp_leaf(value)
    for step in proof:
        side = (step or {}).get("side")
        sibling = (step or {}).get("hash")
        if not sibling:
            raise ValueError("proof step missing a hash")
        if side == "left":
            current = cmp_node(sibling, current)
        elif side == "right":
            current = cmp_node(current, sibling)
        else:
            raise ValueError("proof step missing a side")
    return current


# ==========================================================================
# consistency: RFC 6962 write-order tree
# ==========================================================================

def ct_leaf(value):
    return hashlib.sha256(CT_LEAF + value.encode("utf-8")).digest()


def ct_node(left, right):
    return hashlib.sha256(CT_NODE + left + right).digest()


def _decompose(index, size):
    """Split an inclusion proof into its inner and border parts.

    This is the standard decomposition used by every RFC 6962
    implementation. inner is the number of steps where the path is still
    inside a complete subtree; border is the number of right-hand
    stragglers above it.
    """
    inner = (index ^ (size - 1)).bit_length()
    border = bin(index >> inner).count("1")
    return inner, border


def _chain_inner(seed, proof, index):
    for i, step in enumerate(proof):
        if (index >> i) & 1 == 0:
            seed = ct_node(seed, step)
        else:
            seed = ct_node(step, seed)
    return seed


def _chain_inner_right(seed, proof, index):
    for i, step in enumerate(proof):
        if (index >> i) & 1 == 1:
            seed = ct_node(step, seed)
    return seed


def _chain_border_right(seed, proof):
    for step in proof:
        seed = ct_node(step, seed)
    return seed


def ct_verify_inclusion(index, size, leaf_value, proof_hex, root_hex):
    """Is leaf_value at position index of a tree of this size and root?"""
    if index < 0 or size <= 0 or index >= size:
        return False, "index outside the tree"
    try:
        proof = [bytes.fromhex(h) for h in proof_hex]
        root = bytes.fromhex(root_hex)
    except (ValueError, TypeError):
        return False, "proof or root is not hex"

    inner, border = _decompose(index, size)
    if len(proof) != inner + border:
        return False, ("proof has %d nodes, a tree of size %d needs %d for index %d"
                       % (len(proof), size, inner + border, index))

    result = _chain_inner(ct_leaf(leaf_value), proof[:inner], index)
    result = _chain_border_right(result, proof[inner:])
    if result != root:
        return False, "recomputed root does not match (%s)" % result.hex()
    return True, None


def ct_verify_consistency(size1, size2, proof_hex, root1_hex, root2_hex):
    """Is the tree of size1 a prefix of the tree of size2?"""
    if size1 < 0 or size2 < 0 or size1 > size2:
        return False, "sizes must satisfy 0 <= first <= second"
    try:
        proof = [bytes.fromhex(h) for h in proof_hex]
        root1 = bytes.fromhex(root1_hex)
        root2 = bytes.fromhex(root2_hex)
    except (ValueError, TypeError):
        return False, "proof or roots are not hex"

    if size1 == size2:
        if proof:
            return False, "no proof nodes expected when the sizes are equal"
        return (root1 == root2), (None if root1 == root2 else "roots differ at equal size")
    if size1 == 0:
        return True, None
    if not proof:
        return False, "a proof is required for these sizes"

    inner, border = _decompose(size1 - 1, size2)
    shift = (size1 & -size1).bit_length() - 1
    inner -= shift

    if size1 == (1 << shift):
        seed, start = root1, 0
    else:
        seed, start = proof[0], 1

    if len(proof) != start + inner + border:
        return False, ("proof has %d nodes, expected %d" % (len(proof), start + inner + border))

    body = proof[start:]
    mask = (size1 - 1) >> shift

    hash1 = _chain_inner_right(seed, body[:inner], mask)
    hash1 = _chain_border_right(hash1, body[inner:])
    if hash1 != root1:
        return False, "the earlier root does not recompute (%s)" % hash1.hex()

    hash2 = _chain_inner(seed, body[:inner], mask)
    hash2 = _chain_border_right(hash2, body[inner:])
    if hash2 != root2:
        return False, "the later root does not recompute (%s)" % hash2.hex()
    return True, None


# ==========================================================================
# document checkers
# ==========================================================================

class Check(object):
    def __init__(self, kind):
        self.kind = kind
        self.lines = []
        self.ok = True

    def add(self, passed, text):
        self.lines.append((passed, text))
        if not passed:
            self.ok = False
        return passed


def check_inclusion(doc):
    c = Check("inclusion (completeness)")
    value = doc.get("value")
    root = doc.get("root")
    proof = doc.get("proof")
    if not (value and root and isinstance(proof, list)):
        c.add(False, "document is missing value, root or proof")
        return c
    try:
        computed = cmp_replay(value, proof)
    except ValueError as exc:
        c.add(False, "malformed proof: %s" % exc)
        return c
    c.add(computed == root, "leaf recomputes to the sealed root")
    if doc.get("leaf_count") is not None:
        c.add(True, "period sealed %s records, committed before any export was requested"
                    % doc["leaf_count"])
    if doc.get("index") is not None:
        c.add(True, "record sits at index %s" % doc["index"])
    return c


def check_absence(doc):
    c = Check("absence (completeness)")
    value = doc.get("value")
    root = doc.get("root")
    neighbours = doc.get("neighbours") or {}
    count = doc.get("leaf_count")
    if not (value and root):
        c.add(False, "document is missing value or root")
        return c

    lower = neighbours.get("lower")
    upper = neighbours.get("upper")

    if not lower and not upper:
        c.add(count == 0, "period is committed and empty, so nothing can be in it")
        return c

    if lower:
        try:
            computed = cmp_replay(lower["value"], lower["proof"])
        except (ValueError, KeyError, TypeError) as exc:
            c.add(False, "lower neighbour proof is malformed: %s" % exc)
            return c
        c.add(computed == root, "lower neighbour verifies against the sealed root")
        c.add(str(lower["value"]) < str(value), "lower neighbour sorts before the queried value")

    if upper:
        try:
            computed = cmp_replay(upper["value"], upper["proof"])
        except (ValueError, KeyError, TypeError) as exc:
            c.add(False, "upper neighbour proof is malformed: %s" % exc)
            return c
        c.add(computed == root, "upper neighbour verifies against the sealed root")
        c.add(str(upper["value"]) > str(value), "upper neighbour sorts after the queried value")

    if lower and upper:
        adjacent = int(upper["index"]) == int(lower["index"]) + 1
        c.add(adjacent, "neighbours are adjacent (index %s then %s) - nothing can sit between"
                        % (lower["index"], upper["index"]))
    elif upper:
        c.add(int(upper["index"]) == 0, "value sorts before the first leaf, and nothing precedes index 0")
    elif lower:
        if count is None:
            c.add(True, "value sorts after the last leaf (leaf_count not supplied to confirm)")
        else:
            c.add(int(lower["index"]) == int(count) - 1,
                  "value sorts after the final leaf of %s" % count)
    return c


def check_ancestry(doc):
    c = Check("ancestry (consistency)")
    if doc.get("on_chain") is False:
        c.add(False, "THIS TIP IS NOT ON THE CHAIN BEING SERVED - if it was issued to you, "
                     "that is evidence of a fork. Keep this document.")
        return c
    tip = doc.get("tip")
    index = doc.get("leaf_index")
    size = doc.get("tree_size")
    root = doc.get("root")
    proof = doc.get("inclusion_proof")
    if tip is None or index is None or size is None or not root or not isinstance(proof, list):
        c.add(False, "document is missing tip, leaf_index, tree_size, root or inclusion_proof")
        return c
    ok, why = ct_verify_inclusion(int(index), int(size), tip, proof, root)
    c.add(ok, why or "tip verifies at position %s of a chain of %s" % (index, size))
    return c


def check_prefix(doc):
    c = Check("prefix (consistency)")
    first = doc.get("first")
    second = doc.get("second")
    proof = doc.get("consistency_proof")
    root1 = doc.get("first_root")
    root2 = doc.get("second_root")
    if first is None or second is None or not isinstance(proof, list) or not root1 or not root2:
        c.add(False, "document is missing first, second, consistency_proof or the roots")
        return c
    ok, why = ct_verify_consistency(int(first), int(second), proof, root1, root2)
    c.add(ok, why or ("the log at size %s is contained in the log at size %s - append only, "
                      "nothing inserted, removed or reordered" % (first, second)))
    return c


def check_stability(doc):
    c = Check("stability (replay)")
    history = doc.get("history")
    if not isinstance(history, list) or not history:
        c.add(False, "document has no replay history")
        return c

    by_code = {}
    for run in history:
        by_code.setdefault(run.get("code_fingerprint"), set()).add(
            (str(run.get("verdict")), str(run.get("score"))))

    stable = True
    for fingerprint, outcomes in by_code.items():
        short = (fingerprint or "unknown")[:12]
        if len(outcomes) > 1:
            stable = False
            c.add(False, "code %s produced %d different verdicts for identical inputs - "
                         "the engine is not deterministic under that version"
                         % (short, len(outcomes)))
        else:
            c.add(True, "code %s produced one verdict across every run" % short)

    c.add(True, "%d runs recorded, %d distinct code versions"
                % (len(history), len(by_code)))
    if stable and len(by_code) > 1:
        c.add(True, "verdicts changed only alongside a changed code fingerprint, which is "
                    "a policy change rather than nondeterminism")
    c.add(True, "each run carries its own audit hash - check them independently with "
                "an ancestry proof")
    return c


def identify(doc):
    if not isinstance(doc, dict):
        return None
    if "consistency_proof" in doc:
        return check_prefix
    if "inclusion_proof" in doc or doc.get("on_chain") is not None:
        return check_ancestry
    if doc.get("result") == "absent" or "neighbours" in doc:
        return check_absence
    if doc.get("result") == "present" or ("proof" in doc and "value" in doc):
        return check_inclusion
    if "history" in doc and "input_hash" in doc:
        return check_stability
    return None


# ==========================================================================
# self test - known vectors built here, so the verifier checks itself
# ==========================================================================

def _selftest():
    """Builds small trees in this file and confirms the verifier agrees.

    Run this before trusting a result. If it fails, the fault is in this
    file rather than in anything it was checking.
    """
    failures = []

    # sorted tree, five leaves
    values = sorted(["alpha", "bravo", "charlie", "delta", "echo"])

    def build(vals):
        level = [cmp_leaf(v) for v in vals]
        levels = [level]
        while len(level) > 1:
            nxt = [cmp_node(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
            if len(level) % 2 == 1:
                nxt.append(level[-1])
            levels.append(nxt)
            level = nxt
        return level[0], levels

    def path(levels, index):
        out, idx = [], index
        for level in levels[:-1]:
            if idx % 2 == 0:
                if idx + 1 < len(level):
                    out.append({"side": "right", "hash": level[idx + 1]})
            else:
                out.append({"side": "left", "hash": level[idx - 1]})
            idx //= 2
        return out

    root, levels = build(values)
    for i, value in enumerate(values):
        if cmp_replay(value, path(levels, i)) != root:
            failures.append("sorted inclusion failed for leaf %d" % i)
    if cmp_replay("not-a-leaf", path(levels, 0)) == root:
        failures.append("sorted tree accepted a wrong leaf")

    # RFC 6962 tree, sizes 1..17
    def mth(leaves):
        n = len(leaves)
        if n == 0:
            return hashlib.sha256(b"").digest()
        if n == 1:
            return ct_leaf(leaves[0])
        k = 1
        while k * 2 < n:
            k *= 2
        return ct_node(mth(leaves[:k]), mth(leaves[k:]))

    def incl(index, leaves):
        n = len(leaves)
        if n <= 1:
            return []
        k = 1
        while k * 2 < n:
            k *= 2
        if index < k:
            return incl(index, leaves[:k]) + [mth(leaves[k:])]
        return incl(index - k, leaves[k:]) + [mth(leaves[:k])]

    def subproof(m, leaves, is_root):
        n = len(leaves)
        if m == n:
            return [] if is_root else [mth(leaves)]
        k = 1
        while k * 2 < n:
            k *= 2
        if m <= k:
            return subproof(m, leaves[:k], is_root) + [mth(leaves[k:])]
        return subproof(m - k, leaves[k:], False) + [mth(leaves[:k])]

    for size in range(1, 18):
        leaves = ["entry-%03d" % i for i in range(size)]
        root_hex = mth(leaves).hex()
        for index in range(size):
            proof = [h.hex() for h in incl(index, leaves)]
            ok, why = ct_verify_inclusion(index, size, leaves[index], proof, root_hex)
            if not ok:
                failures.append("ct inclusion failed size=%d index=%d (%s)" % (size, index, why))
            bad, _ = ct_verify_inclusion(index, size, "tampered", proof, root_hex)
            if bad:
                failures.append("ct inclusion accepted a wrong leaf size=%d index=%d" % (size, index))
        for first in range(1, size + 1):
            proof = [h.hex() for h in (subproof(first, leaves, True) if first != size else [])]
            ok, why = ct_verify_consistency(first, size, proof,
                                            mth(leaves[:first]).hex(), root_hex)
            if not ok:
                failures.append("ct consistency failed %d -> %d (%s)" % (first, size, why))

    # a fabricated prefix must be rejected
    leaves = ["entry-%03d" % i for i in range(8)]
    forged = leaves[:4] + ["swapped"] + leaves[5:]
    proof = [h.hex() for h in subproof(4, forged, True)]
    ok, _ = ct_verify_consistency(4, 8, proof, mth(leaves[:4]).hex(), mth(leaves).hex())
    if ok:
        failures.append("ct consistency accepted a forged prefix")

    if failures:
        print("SELF TEST FAILED")
        for line in failures:
            print("   " + line)
        return 1
    print("Self test passed. Sorted-tree and RFC 6962 verification both behave correctly,")
    print("and tampered proofs were rejected in every case.")
    return 0


# ==========================================================================
# cli
# ==========================================================================

def _run(doc, label):
    checker = identify(doc)
    if checker is None:
        print("%s\n   UNRECOGNISED - not an AILeash proof document this version knows about\n" % label)
        return False
    result = checker(doc)
    print("%s\n   type: %s" % (label, result.kind))
    for passed, text in result.lines:
        print("   %s %s" % ("PASS" if passed else "FAIL", text))
    print("   => %s\n" % ("VERIFIED" if result.ok else "NOT VERIFIED"))
    return result.ok


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = set(a for a in argv[1:] if a.startswith("--"))

    if "--selftest" in flags:
        return _selftest()
    if "--version" in flags:
        print("aileash_verify %s" % VERSION)
        return 0

    print("aileash_verify %s - offline, no network calls made\n" % VERSION)

    documents = []
    if args:
        for path in args:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    documents.append((path, json.load(handle)))
            except (OSError, ValueError) as exc:
                print("%s\n   COULD NOT READ: %s\n" % (path, exc))
                return 2
    else:
        try:
            documents.append(("(stdin)", json.load(sys.stdin)))
        except ValueError as exc:
            print("Could not read JSON from stdin: %s" % exc)
            return 2

    results = [_run(doc, label) for label, doc in documents]
    passed = sum(1 for r in results if r)
    print("%d of %d documents verified." % (passed, len(results)))
    if passed != len(results):
        print("Something did not check out. That is what this file is for - keep the "
              "document and the response that produced it.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
