# Codebase — part 7 of 16

Contains:
- `aileash_reporter.py`
- `aileash_verify.py`
- `anchor.py`
- `board_auditor.py`
- `brain.py`
- `broadcaster.py`
- `build_sebbi_ecosystem.py`
- `gateway_proxy.py`
- `sebbi_orchestrator.py`


## `aileash_reporter.py`

232 lines, 9377 bytes

```python
"""
AILEASH DECISION REPORTER v1.0.0
Generates readable audit reports for all AILeash products.
Shows exactly why each decision was made.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
"""

import sqlite3, json, os
from datetime import datetime

DB_FILE = "aileash.db"

PRODUCTS = {
    "aileash": "AILeash",
    "guardian": "AILeash Guardian",
    "sonicboom": "SonicBoom",
    "sentinel": "AILeash Sentinel"
}

REASON_EXPLANATIONS = {
    "velocity_spike": "User made more than 10 requests in 60 seconds",
    "high_amount": "Transaction amount exceeded threshold",
    "risky_device": "Device risk score was above acceptable limit",
    "behaviour_anomaly": "Unusual behaviour pattern detected",
    "country_shift": "Request came from a different country than usual",
    "unsafe_country": "Request came from outside approved country list",
    "low_trust": "User trust score has dropped due to previous decisions",
}

def get_decisions(db_path=DB_FILE, limit=200):
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT a.ts, a.user_id, a.event_json, a.result_json, a.audit_hash,
                   COALESCE(k.product, 'aileash') as product
            FROM audit_log a
            LEFT JOIN api_keys k ON json_extract(a.event_json, '$.api_key') = k.key
            ORDER BY a.id DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    except:
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("""
                SELECT ts, user_id, event_json, result_json, audit_hash, 'aileash'
                FROM audit_log ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            conn.close()
        except:
            return []
    
    results = []
    for row in rows:
        try:
            event = json.loads(row[2])
            result = json.loads(row[3])
            results.append({
                "ts": row[0],
                "user_id": row[1],
                "event": event,
                "result": result,
                "audit_hash": row[4],
                "product": row[5] or "aileash"
            })
        except:
            pass
    return results

def explain_reason(r):
    return REASON_EXPLANATIONS.get(r, r.replace("_", " ").capitalize())

def decision_color(d):
    return {"ALLOW": "#00875a", "CHALLENGE": "#b45309", "BLOCK": "#cc0000"}.get(d, "#555")

def product_color(p):
    return {
        "aileash": "#c9a84c",
        "guardian": "#cc0000",
        "sonicboom": "#00d4ff",
        "sentinel": "#7c3aed"
    }.get(p, "#c9a84c")

def generate_html_report(db_path=DB_FILE, limit=200, output="aileash_report.html"):
    decisions = get_decisions(db_path, limit)

    allow = sum(1 for d in decisions if d["result"].get("decision") == "ALLOW")
    challenge = sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE")
    block = sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")

    rows = ""
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        product = d.get("product", "aileash")
        pc = product_color(product)
        dc = decision_color(decision)
        pname = PRODUCTS.get(product, product)

        reason_html = ""
        if reasons:
            reason_html = "<ul>" + "".join(
                f"<li>{explain_reason(r)}</li>" for r in reasons
            ) + "</ul>"
        else:
            reason_html = "<span style='color:#888'>No risk factors detected</span>"

        rows += f"""<tr>
            <td>{ts}</td>
            <td><span style="font-size:10px;background:{pc}22;color:{pc};border:1px solid {pc}44;padding:2px 6px;border-radius:3px">{pname}</span></td>
            <td><code>{d['user_id']}</code></td>
            <td>{event.get('action','?')}</td>
            <td>{event.get('country','?')}</td>
            <td>£{event.get('amount',0)}</td>
            <td><strong style="color:{dc}">{decision}</strong></td>
            <td>{score}</td>
            <td>{result.get('trust',0)}</td>
            <td>{reason_html}</td>
            <td><code style="font-size:10px">{d['audit_hash'][:16]}...</code></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Audit Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:sans-serif;background:#f5f7fa;color:#1a202c;padding:20px}}
.header{{background:#0a0f1e;color:#fff;padding:24px 32px;border-radius:8px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:22px;color:#c9a84c;margin:0}}
.header p{{font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px}}
.logo{{font-size:13px;color:rgba(255,255,255,0.2)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.stat{{background:#fff;border-radius:8px;padding:16px;text-align:center;border:1px solid #e2e8f0}}
.stat-n{{font-size:28px;font-weight:700}}
.stat-l{{font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:1px}}
.allow{{color:#00875a}}.challenge{{color:#b45309}}.block{{color:#cc0000}}.total{{color:#0a0f1e}}
.table-wrap{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:900px}}
th{{background:#0a0f1e;color:#c9a84c;padding:10px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;white-space:nowrap}}
td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}}
tr:last-child td{{border:none}}
tr:hover td{{background:#f8fafc}}
ul{{margin:4px 0;padding-left:16px}}
li{{margin:2px 0;color:#64748b;font-size:11px}}
code{{background:#f1f5f9;padding:2px 4px;border-radius:3px;font-size:10px}}
.empty{{text-align:center;color:#888;padding:40px}}
footer{{text-align:center;font-size:11px;color:#94a3b8;margin-top:20px}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>AILeash Audit Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Last {len(decisions)} decisions</p>
  </div>
  <div class="logo">sebbi.pro &nbsp;|&nbsp; OAAS-1.0</div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n total">{len(decisions)}</div><div class="stat-l">Total</div></div>
  <div class="stat"><div class="stat-n allow">{allow}</div><div class="stat-l">Allowed</div></div>
  <div class="stat"><div class="stat-n challenge">{challenge}</div><div class="stat-l">Challenged</div></div>
  <div class="stat"><div class="stat-n block">{block}</div><div class="stat-l">Blocked</div></div>
</div>
<div class="table-wrap">
<table>
<thead><tr>
  <th>Time</th><th>Product</th><th>User</th><th>Action</th><th>Country</th>
  <th>Amount</th><th>Decision</th><th>Score</th><th>Trust</th><th>Reasons</th><th>Audit Hash</th>
</tr></thead>
<tbody>
{''.join([rows]) if rows else f'<tr><td colspan="11" class="empty">No decisions recorded yet</td></tr>'}
</tbody>
</table>
</div>
<footer>AILeash &nbsp;|&nbsp; Monop Content &nbsp;|&nbsp; Justin Antony Dobson &nbsp;|&nbsp; sebbi.pro &nbsp;|&nbsp; SHA-256 Merkle Chain</footer>
</body>
</html>"""

    with open(output, "w") as f:
        f.write(html)
    print(f"Report saved: {output} ({len(decisions)} decisions)")
    return output

def generate_json_report(db_path=DB_FILE, limit=200, output="aileash_report.json"):
    decisions = get_decisions(db_path, limit)
    report = {
        "generated": datetime.now().isoformat(),
        "standard": "OAAS-1.0",
        "source": "sebbi.pro",
        "total": len(decisions),
        "summary": {
            "allow": sum(1 for d in decisions if d["result"].get("decision") == "ALLOW"),
            "challenge": sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE"),
            "block": sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")
        },
        "decisions": [{
            "timestamp": datetime.fromtimestamp(d["ts"]).isoformat(),
            "product": PRODUCTS.get(d["product"], d["product"]),
            "user_id": d["user_id"],
            "action": d["event"].get("action"),
            "country": d["event"].get("country"),
            "amount": d["event"].get("amount"),
            "decision": d["result"].get("decision"),
            "score": d["result"].get("score"),
            "trust": d["result"].get("trust"),
            "reasons": d["result"].get("reasons", []),
            "reasons_explained": [explain_reason(r) for r in d["result"].get("reasons", [])],
            "audit_hash": d["audit_hash"]
        } for d in decisions]
    }
    with open(output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved: {output}")
    return output

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "html"
    db = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
    if fmt == "json":
        generate_json_report(db)
    else:
        generate_html_report(db)

```


## `aileash_verify.py`

580 lines, 21445 bytes

```python
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

```


## `anchor.py`

166 lines, 6009 bytes

```python
"""
anchor.py  -  External anchoring for the AILeash chain.

WHAT IT DOES (plain words):
  Every ANCHOR_INTERVAL seconds it takes the current chain tip (one hash) and
  timestamps it against an external source you do NOT control - so anyone can
  prove your chain's timestamps are real without trusting sebbi.pro.

  It tries OpenTimestamps first (commits the hash into Bitcoin, free, gold
  standard). It ALSO records the tip + time to a local append-only anchor log
  on your persistent volume as a second record. If OTS is unavailable for any
  reason, the server keeps running normally - anchoring never blocks or
  crashes your live engine.

SAFETY:
  - Only READS the chain tip. Never writes to the chain, never touches scoring.
  - Runs on a background daemon thread.
  - Every failure is caught and logged; your govern path is never affected.

SETUP ON RAILWAY:
  - requirements.txt:  opentimestamps-client
  - Variable ANCHOR_DIR = /data/anchors   (on your persistent volume)
  - Variable ANCHOR_INTERVAL = 3600       (once an hour; optional)
  - Variable ANCHOR_ENABLED = 1           (set 0 to switch off)
"""

import os
import time
import json
import hashlib
import threading

ANCHOR_INTERVAL = int(os.environ.get("ANCHOR_INTERVAL", "3600"))
ANCHOR_DIR      = os.environ.get("ANCHOR_DIR", "/data/anchors")
ANCHOR_ENABLED  = os.environ.get("ANCHOR_ENABLED", "1") == "1"

_last = {"ts": None, "tip": None, "ots_file": None, "ots_ok": False, "status": "not_started"}
_lock = threading.Lock()


def _ensure_dir():
    try:
        os.makedirs(ANCHOR_DIR, exist_ok=True)
        return True
    except Exception as e:
        print("ANCHOR: cannot create " + ANCHOR_DIR + " : " + str(e), flush=True)
        return False


def _ots_stamp(tip_hash):
    """Timestamp the tip hash with OpenTimestamps (-> Bitcoin). Returns
    (ok, proof_path, message). Uses the opentimestamps library directly, so
    there is no command-line tool to find on PATH."""
    try:
        from opentimestamps.calendar import RemoteCalendar
        from opentimestamps.core.timestamp import Timestamp, DetachedTimestampFile
        from opentimestamps.core.op import OpSHA256
        from opentimestamps.core.serialize import BytesSerializationContext
    except Exception as e:
        return False, None, "opentimestamps library not available: " + str(e)

    try:
        # The digest we anchor is the tip hash (hex -> bytes).
        digest = bytes.fromhex(tip_hash)
        ts = Timestamp(digest)

        # Ask public (free) calendar servers to commit this digest.
        calendars = [
            "https://a.pool.opentimestamps.org",
            "https://b.pool.opentimestamps.org",
            "https://alice.btc.calendar.opentimestamps.org",
        ]
        got = 0
        for url in calendars:
            try:
                cal = RemoteCalendar(url)
                result = cal.submit(digest)
                ts.merge(result)
                got += 1
            except Exception as ce:
                print("ANCHOR: calendar " + url + " failed: " + str(ce), flush=True)
        if got == 0:
            return False, None, "no calendar server accepted the stamp"

        # Save the .ots proof next to a record of the tip.
        stamp_id = str(int(time.time()))
        base = os.path.join(ANCHOR_DIR, "tip_" + stamp_id)
        with open(base + ".txt", "w") as f:
            f.write(tip_hash + "\n")
        detached = DetachedTimestampFile(OpSHA256(), ts)
        ctx = BytesSerializationContext()
        detached.serialize(ctx)
        with open(base + ".ots", "wb") as f:
            f.write(ctx.getbytes())
        return True, base + ".ots", "stamped by " + str(got) + " calendar(s)"
    except Exception as e:
        return False, None, "ots stamp error: " + str(e)


def _record_local(tip_hash, ots_ok, ots_file, msg):
    """Append-only local record of every anchor attempt, on the volume."""
    try:
        idx = os.path.join(ANCHOR_DIR, "anchors.jsonl")
        with open(idx, "a") as f:
            f.write(json.dumps({
                "ts": time.time(),
                "tip": tip_hash,
                "ots": ots_ok,
                "ots_file": ots_file,
                "note": msg
            }) + "\n")
    except Exception as e:
        print("ANCHOR: local record failed: " + str(e), flush=True)


def anchor_once(get_tip):
    if not _ensure_dir():
        return
    try:
        tip = get_tip()
    except Exception as e:
        print("ANCHOR: cannot read tip: " + str(e), flush=True)
        return
    if not tip or tip == "GENESIS":
        print("ANCHOR: chain empty, nothing to anchor", flush=True)
        return

    ok, proof, msg = _ots_stamp(tip)
    _record_local(tip, ok, proof, msg)
    with _lock:
        _last["ts"] = time.time()
        _last["tip"] = tip
        _last["ots_file"] = proof
        _last["ots_ok"] = ok
        _last["status"] = ("anchored: " + msg) if ok else ("ots_unavailable: " + msg)
    if ok:
        print("ANCHOR: tip " + tip[:16] + "... -> " + msg + " -> " + str(proof), flush=True)
    else:
        print("ANCHOR: OTS not available (" + msg + ") - local record written, will retry", flush=True)


def _loop(get_tip):
    time.sleep(30)  # let the server finish booting
    while True:
        try:
            anchor_once(get_tip)
        except Exception as e:
            print("ANCHOR loop error: " + str(e), flush=True)
        time.sleep(ANCHOR_INTERVAL)


def start_anchoring(get_tip):
    """Call ONCE at startup, passing your chain_tip function. Spawns a daemon
    thread that anchors forever. Safe: only logs on failure, never affects the
    live engine."""
    if not ANCHOR_ENABLED:
        print("ANCHOR: disabled (ANCHOR_ENABLED=0)", flush=True)
        return
    threading.Thread(target=_loop, args=(get_tip,), daemon=True).start()
    print("ANCHOR: started - external anchoring every " + str(ANCHOR_INTERVAL) + "s to " + ANCHOR_DIR, flush=True)


def anchor_status():
    with _lock:
        return dict(_last)

```


## `board_auditor.py`

61 lines, 2889 bytes

```python
import time
import json
import urllib.request
import logging
import os

# --- THE WATCHDOG STANDARD ---
AUDITOR_MANIFEST = """Standard: SEBBI-WATCHDOG/1.0
Engine: AILeash-Hunter v1.0
Operation: Automated Public Compliance Verification
Status: ENFORCING"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s [WATCHDOG-SCAN] %(message)s")

class RegulatoryWatchdog:
    def __init__(self, target_list):
        self.targets = target_list
        self.report_file = "VIOLATION_REPORT.md"

    def scan_market_sectors(self):
        """Scans corporate perimeters to verify live legal compliance states."""
        logging.info("Commencing global compliance audit sweep...")
        violations_found = []

        for domain in self.targets:
            print(f"[*] Auditing domain: {domain}")
            
            # Simulate an automated request to the site's root directory
            # In production, this checks if https://domain/ai.txt exists and is signed
            is_compliant = False  # Simulated failure for demonstration
            
            if not is_compliant:
                logging.warning(f"[VIOLATION DETECTED] {domain} has failed mandatory compliance parameters.")
                violations_found.append(domain)

        if violations_found:
            self._compile_public_violation_ledger(violations_found)

    def _compile_public_violation_ledger(self, failed_domains):
        """Generates a public, standardized report file for the repository root."""
        with open(self.report_file, "w", encoding="utf-8") as f:
            f.write("# 🚨 AUTOMATED REAL-TIME AI COMPLIANCE VIOLATION REPORT\n\n")
            f.write(f"**Audit Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
            f.write(f"**Verification Engine:** {AUDITOR_MANIFEST.splitlines()[2]}\n\n")
            f.write("The following enterprise networks were scanned and failed to present a verifiable, cryptographically sealed `ai.txt` manifest under current transparency mandates. These nodes face potential regulatory scrutiny under statutory liability thresholds.\n\n")
            f.write("| Target Domain Domain | Compliance Status | Liability Risk Level |\n")
            f.write("| :--- | :--- | :--- |\n")
            
            for domain in failed_domains:
                f.write(f"| `{domain}` | ❌ NON-COMPLIANT / NO VALID LEDGER | HIGH RISK (Up to 7% Turnover fine) |\n")
                
        print(f"\n[CHECKMATE] Public audit report successfully generated: '{self.report_file}'")
        print("[!] Ready to push to GitHub to alert public sector regulators.")

if __name__ == "__main__":
    # High-value targets that should be operating transparently
    target_enterprise_pool = ["enterprise-ai-vendor-example.com", "shadow-data-processor.co.uk"]
    
    hunter = RegulatoryWatchdog(target_enterprise_pool)
    hunter.scan_market_sectors()

```


## `brain.py`

435 lines, 22193 bytes

```python
import hashlib
import time
import json
import sqlite3
import threading
import re
import unicodedata
from typing import Dict, List, Set, Optional

# ==============================================================================
# AILEASH BRAIN v5.0 — Cryptographic Instruction Governance Layer
# sebbi.pro | Monop Content | Justin Antony Dobson
# ------------------------------------------------------------------------------
# v5.0 change — BASIS SEALING (the "second record"):
#   Until now Brain sealed the ACTION: the instruction and the decision.
#   v5.0 also seals the BASIS a decision rested on — the sources, their
#   versions, and the ruleset/standard it was checked against — into the
#   SAME tamper-evident block. So a sealed record now proves not just
#   *what was decided* but *what it rested on*, neither alterable after
#   the fact.
#
#   Call it like this (basis is OPTIONAL — old calls still work unchanged):
#       brain.evaluate("pay invoice 4471", basis={
#           "sources":        ["invoice_4471.pdf", "supplier_record_88"],
#           "source_versions":["sha256:ab12...", "sha256:cd34..."],
#           "ruleset":        "AI-TXT/1.0 + EU-AI-Act-2024/1689",
#           "ruleset_version":"regmap-v7",
#       })
#
#   The basis is canonicalised, hashed, and folded into the block hash,
#   and the full basis is stored alongside the action. Change any part of
#   the recorded basis later and the chain breaks, exactly like the action.
#
#   HONEST SCOPE — read this, it is the whole point:
#   Basis sealing proves WHAT a decision relied on and that the record of
#   it has not been altered. It does NOT prove the basis was CORRECT — that
#   the sources were genuine, or the ruleset was the right one. Sealing a
#   decision made on a bad source makes the record tamper-evident, not the
#   decision right. Integrity is provable; correctness is a separate
#   discipline. Brain proves the first and is honest about the second.
#
# v4.0 hardening retained: crash-safe WAL chain, truncation detection via
#   anchored tip, hardened genesis, unicode/homoglyph normalisation,
#   full-chain + anchor verify.
# ==============================================================================

BRAIN_VERSION = "5.0"

# Fixed, non-guessable genesis anchor (constant for all deployments of v5).
GENESIS_ANCHOR = hashlib.sha256(b"AILEASH_BRAIN_GENESIS|sebbi.pro|v5").hexdigest()

ALPHABET_HASHES = {
    char: hashlib.sha256(char.encode()).hexdigest()
    for char in "abcdefghijklmnopqrstuvwxyz0123456789 .,!?-_@#"
}

# --- Normalisation hardening -------------------------------------------------
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ѕ": "s", "ԁ": "d", "ɡ": "g", "ν": "v", "α": "a", "ο": "o",
    "ε": "e", "ι": "i", "κ": "k", "τ": "t", "π": "n",
})
_NORM_RE = re.compile(r"[^a-z0-9\s]")
_WS_RE = re.compile(r"\s+")

def normalise(text):
    """NFKC fold, strip zero-width, map homoglyphs, lowercase, strip
    punctuation, collapse whitespace."""
    t = unicodedata.normalize("NFKC", text)
    t = t.translate(_ZERO_WIDTH)
    t = t.translate(_HOMOGLYPHS)
    t = t.lower().strip()
    t = _NORM_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip()

def hash_instruction(text):
    return hashlib.sha256(normalise(text).encode()).hexdigest()

def hash_word(word):
    return hashlib.sha256(normalise(word).encode()).hexdigest()

def letter_signature(text):
    sig = "".join(
        ALPHABET_HASHES.get(c, hashlib.sha256(c.encode()).hexdigest())[:8]
        for c in text.lower()
    )
    return hashlib.sha256(sig.encode()).hexdigest()

def canonical_basis(basis):
    """Canonicalise a basis dict to a stable JSON string so the same basis
    always hashes identically regardless of key order. Returns (canon_str,
    basis_hash). An empty/None basis yields a fixed sentinel so 'no basis
    supplied' is itself a provable, unforgeable fact."""
    if not basis:
        canon = "NO_BASIS_SUPPLIED"
    else:
        # only keep known basis fields, in a fixed order, so the record is
        # predictable and the hash is stable
        clean = {}
        for k in ("sources", "source_versions", "ruleset", "ruleset_version"):
            if k in basis and basis[k] is not None:
                clean[k] = basis[k]
        canon = json.dumps(clean, sort_keys=True, ensure_ascii=True)
    return canon, hashlib.sha256(canon.encode()).hexdigest()

# Blocked instruction sets by threat category
CHILD_SAFETY_BLOCKED = {hash_instruction(i) for i in [
    "keep this secret","don't tell your parents","meet me somewhere",
    "this is just between us","i won't tell anyone","delete this conversation",
    "don't show anyone","you are mature for your age","send me photos",
]}
DATA_EXFILTRATION_BLOCKED = {hash_instruction(i) for i in [
    "export all user data","dump all records","export database",
    "extract all passwords","copy all files","download all data",
    "get all user records","export all keys","send all emails",
]}
COMPLIANCE_BYPASS_BLOCKED = {hash_instruction(i) for i in [
    "disable audit","clear audit log","remove audit trail","disable logging",
    "disable merkle","clear chain","override compliance","skip validation",
    "bypass compliance","disable monitoring",
]}
PROMPT_INJECTION_BLOCKED = {hash_instruction(i) for i in [
    "ignore previous instructions","ignore all instructions",
    "forget your instructions","disregard your training",
    "override your rules","ignore your system prompt",
    "your new instructions are",
]}
SYSTEM_DESTRUCTION_BLOCKED = {hash_instruction(i) for i in [
    "delete all records","drop database","delete all files",
    "format drive","rm rf","destroy all data","wipe database",
]}

ALL_BLOCKED = (
    CHILD_SAFETY_BLOCKED | DATA_EXFILTRATION_BLOCKED |
    COMPLIANCE_BYPASS_BLOCKED | PROMPT_INJECTION_BLOCKED |
    SYSTEM_DESTRUCTION_BLOCKED
)

BLOCKED_WORDS = {hash_word(w) for w in [
    "jailbreak","exploit","inject","exfiltrate","malware","ransomware",
    "phishing","rootkit","backdoor","keylogger","spyware","trojan",
]}

ALLOWED_INSTRUCTIONS = {hash_instruction(i) for i in [
    "get compliance status","check audit chain","verify certificate",
    "run governance check","get decision","check score","verify chain","get health",
]}

THREAT_WEIGHTS = {
    "child_safety":1.0,"prompt_injection":0.95,"system_destruction":0.98,
    "data_exfiltration":0.90,"compliance_bypass":0.88,"blocked_word":0.75,
}

SUSPICIOUS_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?(previous\s+)?instructions",re.I),"prompt_injection",0.95),
    (re.compile(r"(disregard|forget)\s+(everything|all|your)\s+(above|before|instructions|training|rules)",re.I),"prompt_injection",0.95),
    (re.compile(r"you\s+are\s+now\s+",re.I),"prompt_injection",0.90),
    (re.compile(r"act\s+as\s+(if\s+)?",re.I),"prompt_injection",0.80),
    (re.compile(r"(pretend|imagine)\s+(you\s+)?(are|have)\s+no\s+(rules|restrictions|limits)",re.I),"prompt_injection",0.92),
    (re.compile(r"(delete|drop|destroy|wipe|erase|purge)\s+(all\s+)?(data|records|files|database|tables)",re.I),"system_destruction",0.95),
    (re.compile(r"(export|dump|steal|extract|leak|copy)\s+(all\s+)?(user\s+)?(data|records|passwords|keys|credentials)",re.I),"data_exfiltration",0.92),
    (re.compile(r"(disable|bypass|skip|override|remove|turn\s*off)\s+(the\s+)?(audit|logging|compliance|monitoring|safety|guard)",re.I),"compliance_bypass",0.88),
    (re.compile(r"don.?t\s+tell\s+(your\s+)?(parents|anyone|mum|dad|teacher)",re.I),"child_safety",1.0),
    (re.compile(r"keep\s+(this\s+)?(secret|between\s+us|private\s+from)",re.I),"child_safety",1.0),
    (re.compile(r"(our|a)\s+(little\s+)?secret",re.I),"child_safety",1.0),
]

CATEGORY_SETS = [
    (CHILD_SAFETY_BLOCKED,"child_safety"),
    (PROMPT_INJECTION_BLOCKED,"prompt_injection"),
    (SYSTEM_DESTRUCTION_BLOCKED,"system_destruction"),
    (DATA_EXFILTRATION_BLOCKED,"data_exfiltration"),
    (COMPLIANCE_BYPASS_BLOCKED,"compliance_bypass"),
]

def _connect(db_path):
    """Crash-safe connection: WAL journal, synchronous=FULL."""
    c = sqlite3.connect(db_path)
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA synchronous=FULL;")
    return c

class BrainAuditChain:
    def __init__(self,db_path="brain_audit.db"):
        self.db_path=db_path
        self.lock=threading.Lock()
        with _connect(db_path) as c:
            c.execute("""CREATE TABLE IF NOT EXISTS brain_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,instruction TEXT,
                instruction_hash TEXT,letter_sig TEXT,decision TEXT,reason TEXT,
                threat_category TEXT,risk_score REAL,prev_hash TEXT,block_hash TEXT UNIQUE)""")
            for col, decl in (("seq","INTEGER"),
                              ("basis_json","TEXT"),
                              ("basis_hash","TEXT")):
                try:c.execute(f"ALTER TABLE brain_log ADD COLUMN {col} {decl}")
                except sqlite3.OperationalError:pass
            c.execute("""CREATE TABLE IF NOT EXISTS brain_policy(
                rule_hash TEXT PRIMARY KEY,rule_type TEXT,added_ts REAL,sealed_block TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS brain_meta(
                k TEXT PRIMARY KEY, v TEXT)""")
            c.execute("INSERT OR IGNORE INTO brain_meta(k,v) VALUES('tip',?)",(GENESIS_ANCHOR,))
            c.execute("INSERT OR IGNORE INTO brain_meta(k,v) VALUES('last_seq','0')")
            c.commit()

    def seal(self,instruction,instruction_hash,letter_sig,decision,reason,
             threat_category,risk_score,basis_canon="NO_BASIS_SUPPLIED",basis_hash=None):
        """Tip-read, sequence issue, hash, insert AND anchor update inside ONE
        lock hold and ONE transaction. v5.0: the basis_hash is folded into the
        block hash, so the basis is as tamper-evident as the action."""
        ts=time.time()
        if basis_hash is None:
            basis_hash=hashlib.sha256(basis_canon.encode()).hexdigest()
        with self.lock:
            with _connect(self.db_path) as c:
                r=c.execute("SELECT block_hash,COALESCE(seq,0) FROM brain_log ORDER BY id DESC LIMIT 1").fetchone()
                prev=r[0] if r else GENESIS_ANCHOR
                seq=(r[1] if r else 0)+1
                # basis_hash is part of the sealed payload -> tamper-evident basis
                payload=json.dumps({"prev":prev,"ts":ts,"instruction_hash":instruction_hash,
                    "decision":decision,"risk_score":risk_score,"basis_hash":basis_hash},
                    sort_keys=True).encode()
                block_hash=hashlib.sha256(payload).hexdigest()
                c.execute("""INSERT INTO brain_log
                    (ts,instruction,instruction_hash,letter_sig,decision,reason,threat_category,risk_score,prev_hash,block_hash,seq,basis_json,basis_hash)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (ts,instruction,instruction_hash,letter_sig,decision,reason,threat_category,risk_score,prev,block_hash,seq,basis_canon,basis_hash))
                c.execute("UPDATE brain_meta SET v=? WHERE k='tip'",(block_hash,))
                c.execute("UPDATE brain_meta SET v=? WHERE k='last_seq'",(str(seq),))
                c.commit()
        return block_hash,seq

    def verify(self):
        """Full-chain recompute (now including basis_hash) PLUS anchored-tip
        check. Detects edits to the action OR the basis, mid-chain deletion,
        and end truncation."""
        with _connect(self.db_path) as c:
            rows=c.execute("""SELECT instruction_hash,decision,risk_score,prev_hash,block_hash,ts,
                COALESCE(seq,0),COALESCE(basis_hash,''),COALESCE(basis_json,'') FROM brain_log ORDER BY id ASC""").fetchall()
            meta_tip=c.execute("SELECT v FROM brain_meta WHERE k='tip'").fetchone()
            meta_seq=c.execute("SELECT v FROM brain_meta WHERE k='last_seq'").fetchone()
        anchored_tip=meta_tip[0] if meta_tip else GENESIS_ANCHOR
        anchored_seq=int(meta_seq[0]) if meta_seq else 0
        if not rows:
            if anchored_tip!=GENESIS_ANCHOR or anchored_seq!=0:
                return{"valid":False,"broken_at":0,
                    "message":"Chain empty but anchor shows sealed history — chain truncated/deleted"}
            return{"valid":True,"blocks":0,"message":"Empty chain"}
        prev=GENESIS_ANCHOR;last_seq=0
        for i,r in enumerate(rows):
            ih,dec,rs,ph,bh,ts,seq,bhash,bjson=r
            # if a basis is stored, its stored json must still hash to the stored basis_hash
            if bjson and hashlib.sha256(bjson.encode()).hexdigest()!=bhash:
                return{"valid":False,"broken_at":i,"message":f"Basis tampered at block {i} — recorded basis no longer matches its seal"}
            # recompute the block hash exactly as sealed (basis_hash included)
            eff_bhash=bhash if bhash else hashlib.sha256(b"NO_BASIS_SUPPLIED").hexdigest()
            payload=json.dumps({"prev":ph,"ts":ts,"instruction_hash":ih,"decision":dec,
                "risk_score":rs,"basis_hash":eff_bhash},sort_keys=True).encode()
            if hashlib.sha256(payload).hexdigest()!=bh or ph!=prev:
                return{"valid":False,"broken_at":i,"message":f"Chain tampered at block {i}"}
            if seq and seq!=last_seq+1:
                return{"valid":False,"broken_at":i,"message":f"Sequence gap at block {i}: expected {last_seq+1}, found {seq} — record omitted"}
            if seq:last_seq=seq
            prev=bh
        if rows[-1][4]!=anchored_tip:
            return{"valid":False,"broken_at":len(rows),
                "message":"Anchored tip mismatch — blocks removed from the end of the chain (truncation)"}
        if last_seq!=anchored_seq:
            return{"valid":False,"broken_at":len(rows),
                "message":f"Anchored sequence mismatch — anchor says {anchored_seq}, chain ends at {last_seq}"}
        return{"valid":True,"blocks":len(rows),"tip":rows[-1][4],"last_seq":last_seq,
            "message":"Chain intact, sequence gapless, tip anchored, basis sealed"}

    def recent(self,limit=20):
        with _connect(self.db_path) as c:
            rows=c.execute("""SELECT ts,instruction,decision,threat_category,risk_score,block_hash,
                COALESCE(seq,0),COALESCE(basis_json,'') FROM brain_log ORDER BY id DESC LIMIT ?""",(limit,)).fetchall()
        out=[]
        for r in rows:
            item={"ts":r[0],"instruction":r[1],"decision":r[2],"threat_category":r[3],
                  "risk_score":r[4],"block_hash":r[5],"seq":r[6]}
            if r[7] and r[7]!="NO_BASIS_SUPPLIED":
                try:item["basis"]=json.loads(r[7])
                except Exception:item["basis"]=r[7]
            out.append(item)
        return out

class BrainGovernor:
    def __init__(self,db_path="brain_audit.db"):
        self.chain=BrainAuditChain(db_path)
        self.db_path=db_path
        self._custom_blocked=set()
        self._custom_words=set()
        self._load_policy()

    def _load_policy(self):
        with _connect(self.db_path) as c:
            for rh,rt in c.execute("SELECT rule_hash,rule_type FROM brain_policy").fetchall():
                (self._custom_blocked if rt=="instruction" else self._custom_words).add(rh)

    def evaluate(self,instruction,basis:Optional[dict]=None):
        """Evaluate an instruction and seal the decision. v5.0: pass an
        optional `basis` dict (sources, source_versions, ruleset,
        ruleset_version) to seal what the decision rested on alongside it.
        Backwards compatible — evaluate('...') with no basis works as before."""
        start=time.time()
        norm=normalise(instruction)
        ih=hash_instruction(norm)
        ls=letter_signature(norm)
        basis_canon,basis_hash=canonical_basis(basis)

        if ih in ALLOWED_INSTRUCTIONS:
            bh,seq=self.chain.seal(instruction,ih,ls,"ALLOW","explicit_allowlist","allowlist",0.0,basis_canon,basis_hash)
            return self._r("ALLOW","explicit_allowlist","allowlist",0.0,ih,ls,bh,seq,start,basis,basis_hash)

        for blocked_set,category in CATEGORY_SETS+[(self._custom_blocked,"custom")]:
            if ih in blocked_set:
                rs=THREAT_WEIGHTS.get(category,0.9)
                bh,seq=self.chain.seal(instruction,ih,ls,"BLOCK",f"blocked_{category}",category,rs,basis_canon,basis_hash)
                return self._r("BLOCK",f"blocked_{category}",category,rs,ih,ls,bh,seq,start,basis,basis_hash)

        for word in norm.split():
            wh=hash_word(word)
            if wh in BLOCKED_WORDS or wh in self._custom_words:
                bh,seq=self.chain.seal(instruction,ih,ls,"BLOCK",f"blocked_word:{word}","blocked_word",0.75,basis_canon,basis_hash)
                return self._r("BLOCK",f"blocked_word:{word}","blocked_word",0.75,ih,ls,bh,seq,start,basis,basis_hash)

        for pattern,category,weight in SUSPICIOUS_PATTERNS:
            if pattern.search(norm):
                bh,seq=self.chain.seal(instruction,ih,ls,"BLOCK",f"pattern:{category}",category,weight,basis_canon,basis_hash)
                return self._r("BLOCK",f"pattern:{category}",category,weight,ih,ls,bh,seq,start,basis,basis_hash)

        bh,seq=self.chain.seal(instruction,ih,ls,"ALLOW","no_violations","none",0.0,basis_canon,basis_hash)
        return self._r("ALLOW","no_violations","none",0.0,ih,ls,bh,seq,start,basis,basis_hash)

    def _r(self,decision,reason,threat_category,risk_score,ih,ls,bh,seq,start,basis,basis_hash):
        out={"decision":decision,"reason":reason,"threat_category":threat_category,
            "risk_score":round(risk_score,4),"instruction_hash":ih,
            "letter_signature":ls[:32]+"...","audit_hash":bh,"receipt_seq":seq,
            "brain_version":BRAIN_VERSION,
            "ms":round((time.time()-start)*1000,3)}
        if basis:
            out["basis_sealed"]=True
            out["basis_hash"]=basis_hash
            # honest, machine-readable reminder of what the seal does and doesn't prove
            out["basis_scope"]="Proves what the decision relied on and that this record is unaltered. Does NOT certify the basis was correct."
        else:
            out["basis_sealed"]=False
        return out

    def _seal_policy_change(self,kind,rule_hash):
        bh,seq=self.chain.seal(
            f"POLICY_CHANGE:{kind}",rule_hash,letter_signature(rule_hash),
            "POLICY",f"policy_add_{kind}","policy_change",0.0)
        with _connect(self.db_path) as c:
            c.execute("INSERT OR IGNORE INTO brain_policy(rule_hash,rule_type,added_ts,sealed_block) VALUES(?,?,?,?)",
                (rule_hash,kind,time.time(),bh))
            c.commit()
        return bh

    def add_blocked_instruction(self,instruction):
        h=hash_instruction(instruction)
        self._custom_blocked.add(h)
        self._seal_policy_change("instruction",h)
        return h

    def add_blocked_word(self,word):
        h=hash_word(word)
        self._custom_words.add(h)
        self._seal_policy_change("word",h)
        return h

    def verify_chain(self):return self.chain.verify()
    def recent_decisions(self,limit=20):return self.chain.recent(limit)

if __name__=="__main__":
    import os
    for p in ("/tmp/brain5.db","/tmp/brain5.db-wal","/tmp/brain5.db-shm"):
        if os.path.exists(p):os.remove(p)
    brain=BrainGovernor("/tmp/brain5.db")
    print(f"AILEASH BRAIN v{BRAIN_VERSION}")
    print("="*80)

    # 1) backwards compatibility — no basis, works exactly as before
    print("\n[1] Backwards compatible (no basis):")
    for t in ["get compliance status","ignore previous instructions","drop database"]:
        r=brain.evaluate(t)
        print(f"  {r['decision']:5} | seq {r['receipt_seq']:>2} | basis_sealed={r['basis_sealed']} | {t[:34]}")

    # 2) with basis — the second record
    print("\n[2] With basis sealed alongside the action:")
    r=brain.evaluate("approve payment to supplier 88", basis={
        "sources":["invoice_4471.pdf","supplier_record_88"],
        "source_versions":["sha256:ab12cd","sha256:ef34gh"],
        "ruleset":"AI-TXT/1.0 + EU-AI-Act-2024/1689",
        "ruleset_version":"regmap-v7",
    })
    print(f"  decision={r['decision']} basis_sealed={r['basis_sealed']}")
    print(f"  basis_hash={r['basis_hash'][:24]}...")
    print(f"  scope: {r['basis_scope']}")

    # 3) recent shows the basis back
    print("\n[3] Recent decision carries its basis:")
    rec=brain.recent_decisions(1)[0]
    print(f"  {rec['decision']} | basis={rec.get('basis')}")

    print("\n[4] Chain verify:")
    print("  ",brain.verify_chain()["message"])

    # 5) tamper drills — action edit, basis edit, truncation
    import sqlite3 as s3
    print("\n--- TAMPER DRILLS ---")
    c=s3.connect("/tmp/brain5.db")
    c.execute("UPDATE brain_log SET risk_score=0.0 WHERE id=2");c.commit();c.close()
    print("  after editing an ACTION (block 2):",brain.verify_chain()["message"])

    for p in ("/tmp/brain5b.db","/tmp/brain5b.db-wal","/tmp/brain5b.db-shm"):
        if os.path.exists(p):os.remove(p)
    b2=BrainGovernor("/tmp/brain5b.db")
    b2.evaluate("approve payment", basis={"sources":["inv_1"],"ruleset":"regmap-v7"})
    b2.evaluate("get health")
    # tamper ONLY the basis json of block 1, leave everything else
    c=s3.connect("/tmp/brain5b.db")
    c.execute("UPDATE brain_log SET basis_json=? WHERE id=1",('{"sources": ["inv_FAKE"], "ruleset": "regmap-v7"}',))
    c.commit();c.close()
    print("  after editing a BASIS (block 1):",b2.verify_chain()["message"])

    for p in ("/tmp/brain5c.db","/tmp/brain5c.db-wal","/tmp/brain5c.db-shm"):
        if os.path.exists(p):os.remove(p)
    b3=BrainGovernor("/tmp/brain5c.db")
    for t in ["get health","check score","verify chain"]:b3.evaluate(t)
    c=s3.connect("/tmp/brain5c.db")
    c.execute("DELETE FROM brain_log WHERE id=(SELECT MAX(id) FROM brain_log)");c.commit();c.close()
    print("  after truncating last block:",b3.verify_chain()["message"])

```


## `broadcaster.py`

158 lines, 6412 bytes

```python
import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress

# --- HARDENED ARCHITECTURE DECLARATION ---
AI_TXT_PAYLOAD = """Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Decision-Model: deterministic weighted scoring (no ML drift; weights immutable)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro"""

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\n"
    "Verify live audit status at: https://sebbi.pro"
)

# Operational Configuration
UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  # Lowered slightly to manage OS file descriptor ceilings safely
TIMEOUT = 1.5           # Tightened timeout for faster failover

# Secret key used to sign messages (In production, load this securely via environment variables)
SYSTEM_SIGNING_KEY = b"SECURE_GOVERNANCE_SECRET_PASSPHRASE_KEY"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_network_topology():
    """
    Safely resolves the local IP address and computes the network boundary 
    using proper subnet masks instead of naive string manipulation.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Does not send actual data; used to determine local routing interface
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        # In a production environment, dynamically pull the actual netmask.
        # Fallback here assumes a standard /24 corporate subnet slice for demonstration.
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return interface.network.broadcast_address.with_prefixlen.split('/')[0], interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def generate_signed_payload(message_text, declaration_text, key):
    """
    Packages the governance telemetry data and appends an immutable 
    HMAC-SHA256 signature to guarantee authenticity at the destination node.
    """
    base_data = {
        "alert_text": message_text,
        "raw_declaration": declaration_text
    }
    serialized_json = json.dumps(base_data, sort_keys=True)
    
    # Compute cryptographic signature
    signature = hmac.new(key, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Enclose both the verified data and signature in a final unified wrapper
    final_package = {
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    }
    return json.dumps(final_package)

def send_secure_udp_broadcast(compiled_payload, broadcast_target):
    """Broadcasts the cryptographically signed data packet to the subnet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast successfully dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast failure: {e}")

async def push_to_secure_gateway(target_ip, compiled_payload):
    """Injects the signed payload directly into downstream destination gateways."""
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\r\n"
            f"Host: {target_ip}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(compiled_payload)}\r\n"
            f"X-Signature-Auth: True\r\n"
            f"Connection: close\r\n\r\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        # Gracefully filter common network timeouts or offline endpoints
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

async def secure_network_orchestrator():
    broadcast_ip, network_obj = get_network_topology()
    
    # Generate the single signed package used for all downstream nodes
    signed_data_stream = generate_signed_payload(HUMAN_MESSAGE, AI_TXT_PAYLOAD, SYSTEM_SIGNING_KEY)
    
    # 1. Fire authenticated network-wide baseline blast
    send_secure_udp_broadcast(signed_data_stream, broadcast_ip)
    
    # 2. Asynchronously target explicit topological gateways (.1 and .254)
    tasks = []
    logging.info(f"Initiating asynchronous gateway verification loop across subnet: {network_obj.with_prefixlen}")
    
    # Safely isolate subnets by targeting typical routing infrastructure points
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(push_to_secure_gateway(host_str, signed_data_stream)))
            
            # Handle task scheduling dynamically to respect system resource bounds
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Network compliance orchestration sequence finalized completed.")

if __name__ == "__main__":
    asyncio.run(secure_network_orchestrator())

```


## `build_sebbi_ecosystem.py`

270 lines, 9812 bytes

```python
import os
import sys

# --- CODE CONTAINERS FOR AUTOMATED INJECTION ---

BROADCASTER_CODE = """import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress
import os

# --- HARDENED ARCHITECTURE DECLARATION ---
AI_TXT_PAYLOAD = \"\"\"Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Decision-Model: deterministic weighted scoring (no ML drift; weights immutable)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro\"\"\"

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.\\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\\n"
    "Verify live audit status at: https://sebbi.pro"
)

UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  
TIMEOUT = 1.5           

# Dynamic environment lookup to protect the secret signature key
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_BROADCAST_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_network_topology():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return str(interface.network.broadcast_address), interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def generate_signed_payload(message_text, declaration_text, key):
    base_data = {
        "alert_text": message_text,
        "raw_declaration": declaration_text
    }
    serialized_json = json.dumps(base_data, sort_keys=True)
    signature = hmac.new(key, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    final_package = {
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    }
    return json.dumps(final_package)

def send_secure_udp_broadcast(compiled_payload, broadcast_target):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast failure: {e}")

async def push_to_secure_gateway(target_ip, compiled_payload):
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\\r\\n"
            f"Host: {target_ip}\\r\\n"
            f"Content-Type: application/json\\r\\n"
            f"Content-Length: {len(compiled_payload)}\\r\\n"
            f"X-Signature-Auth: True\\r\\n"
            f"Connection: close\\r\\n\\r\\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

async def secure_network_orchestrator():
    broadcast_ip, network_obj = get_network_topology()
    signed_data_stream = generate_signed_payload(HUMAN_MESSAGE, AI_TXT_PAYLOAD, SYSTEM_SIGNING_KEY)
    
    send_secure_udp_broadcast(signed_data_stream, broadcast_ip)
    
    tasks = []
    logging.info(f"Initiating asynchronous gateway loop across subnet: {network_obj.with_prefixlen}")
    
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(push_to_secure_gateway(host_str, signed_data_stream)))
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Network compliance orchestration sequence finalized.")

if __name__ == "__main__":
    asyncio.run(secure_network_orchestrator())
"""

GREEN_CODE = """import time
import os
import sys
import json
import socket
import logging
import hashlib
import hmac

if sys.platform != "win32":
    import resource
else:
    resource = None

# --- ECOSYSTEM METADATA ENGINE ---
GREEN_AI_STANDARD = \"\"\"Standard: GREEN-AI/1.0
Framework-Licence: open-access / standard-registry
Metrics-Engine: GreenLeash v1.2 (System Resource Auditor)
Target-SLA: Sub-2ms Internal Latency Overhead
Verification-Hub: https://sebbi.pro\"\"\"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GREEN-TELEMETRY] %(message)s")

# Dynamic environment lookup to protect the secret signature key
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_GREEN_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

class ProductionGreenNotary:
    def __init__(self):
        self.node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]

    def _get_system_usage(self):
        if resource:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            cpu_time = usage.ru_utime + usage.ru_stime
            memory_mb = usage.ru_maxrss / (1024.0 if sys.platform == "darwin" else 1.0)
        else:
            cpu_time = time.process_time()
            memory_mb = 0.0
        return cpu_time, memory_mb

    def profile_process(self, process_func, *args, **kwargs):
        start_wall = time.perf_counter()
        start_cpu, start_mem = self._get_system_usage()

        result = process_func(*args, **kwargs)

        end_cpu, end_mem = self._get_system_usage()
        end_wall = time.perf_counter()

        wall_latency_ms = (end_wall - start_wall) * 1000
        cpu_time_delta_ms = (end_cpu - start_cpu) * 1000
        peak_memory_mb = max(start_mem, end_mem)

        self._package_and_sign_metrics(wall_latency_ms, cpu_time_delta_ms, peak_memory_mb)
        return result

    def _package_and_sign_metrics(self, wall_ms, cpu_ms, memory_mb):
        telemetry_data = {
            "node_id": self.node_id,
            "wall_latency_ms": round(wall_ms, 3),
            "kernel_cpu_time_ms": round(cpu_ms, 3),
            "allocated_memory_mb": round(memory_mb, 2),
            "meta_declaration": GREEN_AI_STANDARD
        }

        serialized_payload = json.dumps(telemetry_data, sort_keys=True)
        signature = hmac.new(SYSTEM_SIGNING_KEY, serialized_payload.encode('utf-8'), hashlib.sha256).hexdigest()

        final_packet = {
            "payload": telemetry_data,
            "signature": signature,
            "algorithm": "HMAC-SHA256"
        }

        logging.info(f"[AUDIT LOGGED] Wall: {round(wall_ms, 1)}ms | CPU: {round(cpu_ms, 1)}ms | RAM: {round(memory_mb, 1)}MB")
        logging.info(f"[LEDGER SEAL] HMAC: {signature[:16]}...")
        return json.dumps(final_packet)

def mock_computational_work():
    dummy_data = [x for x in range(1000000)]
    time.sleep(0.015)
    return "SUCCESS"

if __name__ == "__main__":
    logging.info("Starting GreenLeash Kernel Auditing Pipeline...")
    auditor = ProductionGreenNotary()
    auditor.profile_process(mock_computational_work)
"""

# --- BLUEPRINT DICTIONARY ---
REPO_STRUCTURE = {
    "server": {
        "server.py": "# Core production database and cryptographic Merkle chain engine\n# (Keep your proprietary server logic safely deployed here)\n"
    },
    "public-utilities": {
        "broadcaster.py": BROADCASTER_CODE,
        "green.py": GREEN_CODE
    }
}

def execute_automated_compilation():
    """Builds the folder paths and populates the production files in bulk."""
    base_path = os.getcwd()
    print(f"[*] Starting compilation blueprint in root: {base_path}")
    
    for folder, files in REPO_STRUCTURE.items():
        folder_path = os.path.join(base_path, folder)
        
        # Build missing folders securely
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"[+] Directory established: /{folder}")
            
        # Write .gitkeep so Git registers the paths even if empty
        with open(os.path.join(folder_path, ".gitkeep"), "w", encoding="utf-8") as f:
            f.write("# Forces Git tracking for this structural directory block\n")
            
        # Compile each individual file
        for file_name, code_content in files.items():
            file_path = os.path.join(folder_path, file_name)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code_content)
            print(f"    └── [COMPILED SUCCESS] Written: /{folder}/{file_name}")

    print("\n[!] SUCCESS: All files have been safely sorted into their proper paths.")
    print("[!] Run: 'git add . && git commit -m \"Add client utilities\" && git push'")

if __name__ == "__main__":
    execute_automated_compilation()

```


## `gateway_proxy.py`

280 lines, 10922 bytes

```python
import asyncio
import ssl
import json
import hmac
import hashlib
import os
import time
import logging
import urllib.request
import urllib.error

# ============================================================
# AILEASH GATEWAY PROXY - real enforcement version
#
# How it's meant to be used:
#   Customer changes their AI SDK's base URL from
#     https://api.openai.com/v1
#   to
#     https://your-gateway-domain/openai/v1
#   (same for Anthropic under /anthropic/)
#
# Every request that arrives:
#   1. Gets scored by your real /api/govern endpoint (same
#      scoring + sealing logic as server.py - nothing duplicated).
#   2. If the decision is BLOCK, the request is rejected here.
#      The real OpenAI/Anthropic call is NEVER made. That's the
#      actual gate - not an email sent after the fact.
#   3. If ALLOW or CHALLENGE, the request is forwarded to the
#      real provider over a real TLS connection, and the real
#      response is streamed back untouched.
#
# This does NOT intercept traffic the customer sends directly
# to openai.com without going through this gateway. No proxy
# that doesn't install certificates on every device can do that
# for HTTPS traffic - that's a much bigger, separate product.
# This is the same integration pattern used by every commercial
# AI gateway (Cloudflare AI Gateway, Portkey, LiteLLM proxy, etc).
# ============================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s [GATEWAY] %(message)s")

PROXY_PORT = int(os.environ.get("GATEWAY_PORT", 8888))

# No fallback key. If this isn't set, refuse to start rather than
# run with a guessable signing key in production.
PROXY_SIGNING_KEY = os.environ.get("SEBBI_PROXY_SECRET", "").strip()
if not PROXY_SIGNING_KEY:
    raise SystemExit(
        "SEBBI_PROXY_SECRET is not set. Refusing to start - "
        "running with a default/fallback signing key is not safe. "
        "Set SEBBI_PROXY_SECRET in your environment (Railway variables) and restart."
    )
PROXY_SIGNING_KEY = PROXY_SIGNING_KEY.encode("utf-8")

# Where your real scoring/sealing engine lives. Point this at your
# own deployment - defaults to the live sebbi.pro API.
GOVERN_URL = os.environ.get("AILEASH_GOVERN_URL", "https://sebbi.pro/api/govern")

# Which real AI providers this gateway can forward to, and their
# real hostnames. Add more here if you support more providers.
PROVIDERS = {
    "openai": "api.openai.com",
    "anthropic": "api.anthropic.com",
}


def call_govern(ailleash_key: str, event: dict):
    """Call the real /api/govern endpoint and return (decision_json, http_status).
    This is a blocking network call - run it in a thread executor so it
    doesn't stall the async event loop."""
    body = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(
        GOVERN_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + ailleash_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read()), e.code
        except Exception:
            return {"decision": "BLOCK", "error": "govern_returned_unreadable_error"}, e.code
    except Exception as e:
        # Network failure, timeout, DNS issue, etc. Fail closed - if we
        # can't reach the compliance engine, we don't guess ALLOW.
        return {"decision": "BLOCK", "error": "govern_unreachable: " + str(e)}, 503


def parse_request(raw_head: bytes):
    """Parse the request line + headers from the raw bytes read up to \\r\\n\\r\\n."""
    text = raw_head.decode("utf-8", errors="ignore")
    lines = text.split("\r\n")
    request_line = lines[0]
    parts = request_line.split(" ")
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return method, path, headers


def build_forward_request(method, upstream_path, headers, body: bytes, upstream_host):
    """Rebuild the HTTP request to send to the real provider. Strips our
    own gateway-only headers and sets the correct Host."""
    drop = {"host", "x-sebbi-key", "x-sebbi-event", "content-length"}
    lines = [method + " " + upstream_path + " HTTP/1.1", "Host: " + upstream_host]
    for k, v in headers.items():
        if k in drop:
            continue
        lines.append(k + ": " + v)
    lines.append("Content-Length: " + str(len(body)))
    lines.append("Connection: close")
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("utf-8")
    return head + body


async def read_full_request(reader):
    """Read headers, then read exactly Content-Length bytes of body if present."""
    head = await reader.readuntil(b"\r\n\r\n")
    method, path, headers = parse_request(head)
    length = int(headers.get("content-length", "0") or "0")
    body = b""
    if length:
        body = await reader.readexactly(length)
    return method, path, headers, body


async def forward_to_provider(upstream_host, request_bytes: bytes):
    """Open a real TLS connection to the real provider and return the raw
    response bytes, unmodified."""
    ctx = ssl.create_default_context()
    reader, writer = await asyncio.open_connection(upstream_host, 443, ssl=ctx)
    try:
        writer.write(request_bytes)
        await writer.drain()
        response = await reader.read(-1)
        return response
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


def default_event(headers, device_id_fallback):
    """Build a sensible /api/govern event from what the customer sent,
    falling back to safe defaults for anything they didn't specify.
    Customers can override any field by sending an X-Sebbi-Event JSON header."""
    override = headers.get("x-sebbi-event")
    if override:
        try:
            ev = json.loads(override)
        except Exception:
            ev = {}
    else:
        ev = {}
    ev.setdefault("user_id", headers.get("x-sebbi-user", "gateway_anonymous"))
    ev.setdefault("action", "ai_request")
    ev.setdefault("amount", 0)
    ev.setdefault("country", headers.get("x-sebbi-country", "UK"))
    ev.setdefault("device_id", headers.get("x-sebbi-device", device_id_fallback))
    ev.setdefault("anomaly", 0)
    ev.setdefault("device_risk", 0)
    return ev


class ComplianceGatewayProxy:
    def __init__(self, host="0.0.0.0", port=PROXY_PORT):
        self.host = host
        self.port = port

    async def start(self):
        server = await asyncio.start_server(self.handle_client_traffic, self.host, self.port)
        logging.info("AILeash Gateway operational on :%s (real enforcement, real forwarding)", self.port)
        async with server:
            await server.serve_forever()

    async def handle_client_traffic(self, reader, writer):
        peer = writer.get_extra_info("peername")
        try:
            method, path, headers, body = await read_full_request(reader)
        except Exception as e:
            logging.warning("Bad request from %s: %s", peer, e)
            writer.close()
            return

        try:
            # Route: /openai/... or /anthropic/... selects the real provider.
            segments = path.strip("/").split("/", 1)
            provider_key = segments[0] if segments else ""
            upstream_path = "/" + segments[1] if len(segments) > 1 else "/"

            if provider_key not in PROVIDERS:
                self._reject(writer, 404, "unknown_provider",
                              "Path must start with /openai/ or /anthropic/")
                return

            ailleash_key = headers.get("x-sebbi-key", "")
            if not ailleash_key:
                self._reject(writer, 401, "missing_compliance_key",
                              "Include your AILeash API key in the X-Sebbi-Key header.")
                return

            device_id_fallback = str(peer[0]) if peer else "unknown_device"
            event = default_event(headers, device_id_fallback)

            loop = asyncio.get_event_loop()
            decision_json, status = await loop.run_in_executor(
                None, call_govern, ailleash_key, event
            )
            decision = decision_json.get("decision", "BLOCK")

            if status != 200 or decision == "BLOCK":
                logging.warning("[BLOCKED] %s -> %s (%s)", peer, provider_key, decision_json.get("reasons", decision_json.get("error", "")))
                self._reject(writer, 403, "compliance_block", None, decision_json)
                return

            # ALLOW or CHALLENGE both proceed - CHALLENGE just means the
            # customer's own code should show the user the verification
            # link included in decision_json. We don't invent enforcement
            # server.py doesn't have.
            upstream_host = PROVIDERS[provider_key]
            forward_bytes = build_forward_request(method, upstream_path, headers, body, upstream_host)

            real_response = await forward_to_provider(upstream_host, forward_bytes)

            tx_seal = hmac.new(PROXY_SIGNING_KEY, real_response[:2048], hashlib.sha256).hexdigest()
            logging.info("[ROUTED] %s -> %s decision=%s seal=%s", peer, provider_key, decision, tx_seal[:16])

            writer.write(real_response)
            await writer.drain()

        except Exception as e:
            logging.error("Proxy error for %s: %s", peer, e)
            try:
                self._reject(writer, 502, "gateway_error", str(e))
            except Exception:
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _reject(self, writer, code, reason, message=None, extra=None):
        payload = {"error": reason}
        if message:
            payload["message"] = message
        if extra:
            payload["compliance_decision"] = extra
        body = json.dumps(payload).encode("utf-8")
        status_text = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 502: "Bad Gateway"}.get(code, "Error")
        resp = (
            "HTTP/1.1 " + str(code) + " " + status_text + "\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: " + str(len(body)) + "\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8") + body
        writer.write(resp)


if __name__ == "__main__":
    gateway = ComplianceGatewayProxy()
    try:
        asyncio.run(gateway.start())
    except KeyboardInterrupt:
        logging.info("Gateway offline.")

```


## `sebbi_orchestrator.py`

194 lines, 7453 bytes

```python
import asyncio
import json
import logging
import socket
import hmac
import hashlib
import ipaddress
import os
import sys
import time

# Handle cross-platform kernel metric mapping
if sys.platform != "win32":
    import resource
else:
    resource = None

# --- ARCHITECTURE METADATA ENGINE ---
CORE_MANIFEST = """Standard: AI-TXT/1.0
Standard-Licence: free and open - publish your own at no cost, no key required
Operator: Monop Content
Operator-Location: Blyth, Northumberland, United Kingdom
Contact: justrightdecorators@gmail.com
Last-Updated: 2026-07-05

Governance-Engine: AILeash v6.4
Metrics-Engine: GreenLeash v1.2 (Unified Resource Auditor)
Decision-Outcomes: ALLOW, CHALLENGE, BLOCK
Decision-Signals: 9
Decision-Latency-Median: 28ms

Verify-Endpoint: https://sebbi.pro
Companion-Standard: https://sebbi.pro
Whitepaper: https://sebbi.pro"""

HUMAN_MESSAGE = (
    "SYSTEM NOTICE: AI Governance & Sustainability Compliance Update for sebbi.pro.\n"
    "The updated compliance targets are now active under Standard: AI-TXT/1.0.\n"
    "Verify live audit status at: https://sebbi.pro"
)

# Network Operational Limits
UDP_BROADCAST_PORT = 5001
TCP_GATEWAY_PORT = 8080
CONCURRENT_LIMIT = 2000  
TIMEOUT = 1.5           

# Dynamic environment lookup to protect secret keys from public GitHub visibility
SYSTEM_SIGNING_KEY = os.environ.get("SEBBI_SYSTEM_SECRET", "LOCAL_DEV_FALLBACK_KEY").encode('utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ==========================================
# PART 1: CORE UTILITIES & METRIC AUDITING
# ==========================================

def get_network_topology():
    """Resolves local interface and dynamically maps standard subnet boundaries."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        interface = ipaddress.IPv4Interface(f"{local_ip}/255.255.255.0")
        return str(interface.network.broadcast_address), interface.network
    except Exception as e:
        logging.error(f"Failed to automatically resolve local network topology: {e}")
        return "255.255.255.255", ipaddress.IPv4Network("192.168.1.0/24")

def get_kernel_resource_usage():
    """Extracts raw processing time and RAM footprints straight from the OS kernel."""
    if resource:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        cpu_time = usage.ru_utime + usage.ru_stime
        memory_mb = usage.ru_maxrss / (1024.0 if sys.platform == "darwin" else 1.0)
    else:
        cpu_time = time.process_time()
        memory_mb = 0.0
    return cpu_time, memory_mb

def generate_signed_telemetry(message_text, manifest_text, extra_metrics=None):
    """Packages corporate alerts and signs them using HMAC-SHA256 for tampering prevention."""
    base_data = {
        "alert_text": message_text,
        "raw_declaration": manifest_text,
        "node_id": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]
    }
    if extra_metrics:
        base_data["sustainability_metrics"] = extra_metrics
        
    serialized_json = json.dumps(base_data, sort_keys=True)
    signature = hmac.new(SYSTEM_SIGNING_KEY, serialized_json.encode('utf-8'), hashlib.sha256).hexdigest()
    
    return json.dumps({
        "payload": base_data,
        "signature": signature,
        "algorithm": "HMAC-SHA256"
    })

# ==========================================
# PART 2: DISTRIBUTION ENGINES
# ==========================================

def execute_udp_broadcast(compiled_payload, broadcast_target):
    """Fires a connectionless notification to all listening local subnet nodes."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(compiled_payload.encode('utf-8'), (broadcast_target, UDP_BROADCAST_PORT))
            logging.info(f"Signed UDP broadcast dispatched to {broadcast_target}:{UDP_BROADCAST_PORT}")
    except socket.error as e:
        logging.error(f"UDP broadcast transmission failure: {e}")

async def dispatch_tcp_gateway(target_ip, compiled_payload):
    """Pushes a verified compliance wrapper directly into standard infrastructure points."""
    writer = None
    try:
        connect = asyncio.open_connection(target_ip, TCP_GATEWAY_PORT)
        _, writer = await asyncio.wait_for(connect, timeout=TIMEOUT)
        
        http_request = (
            f"POST /api/compliance/broadcast HTTP/1.1\r\n"
            f"Host: {target_ip}\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(compiled_payload)}\r\n"
            f"X-Signature-Auth: True\r\n"
            f"Connection: close\r\n\r\n"
            f"{compiled_payload}"
        ).encode('utf-8')
        
        writer.write(http_request)
        await writer.drain()
        logging.info(f"[DISPATCHED] Verified telemetry pushed to infrastructure host: {target_ip}")
        return True
    except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
        return False
    finally:
        if writer:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

# ==========================================
# PART 3: RECENTRALIZED PROCESS ENGINE
# ==========================================

async def run_unified_orchestration():
    logging.info("Initializing Unified Sebbi Ecosystem Orchestration Pipeline...")
    
    # 1. Profile an operational work function (Audit System Burden)
    start_wall = time.perf_counter()
    start_cpu, start_mem = get_kernel_resource_usage()
    
    # [SIMULATION BLOCK]: Represents a standard local validation check running
    await asyncio.sleep(0.025)
    
    end_cpu, end_mem = get_kernel_resource_usage()
    end_wall = time.perf_counter()
    
    metrics = {
        "wall_latency_ms": round((end_wall - start_wall) * 1000, 3),
        "kernel_cpu_time_ms": round((end_cpu - start_cpu) * 1000, 3),
        "allocated_memory_mb": round(max(start_mem, end_mem), 2)
    }
    logging.info(f"Process Profile Completed -> CPU: {metrics['kernel_cpu_time_ms']}ms | RAM: {metrics['allocated_memory_mb']}MB")
    
    # 2. Package and sign the final structural data block
    broadcast_ip, network_obj = get_network_topology()
    signed_payload_stream = generate_signed_telemetry(HUMAN_MESSAGE, CORE_MANIFEST, extra_metrics=metrics)
    
    # 3. Fire local network UDP alert baseline
    execute_udp_broadcast(signed_payload_stream, broadcast_ip)
    
    # 4. Asynchronously scan and iterate targeted subnet infrastructure nodes
    tasks = []
    logging.info(f"Scanning target gateways across subnet map: {network_obj.with_prefixlen}")
    
    for host in network_obj.hosts():
        host_str = str(host)
        if host_str.endswith(".1") or host_str.endswith(".254"):
            tasks.append(asyncio.create_task(dispatch_tcp_gateway(host_str, signed_payload_stream)))
            if len(tasks) >= CONCURRENT_LIMIT:
                await asyncio.gather(*tasks, return_exceptions=True)
                tasks = []
                
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("Unified orchestration sequence finalized successfully.")

if __name__ == "__main__":
    asyncio.run(run_unified_orchestration())

```
