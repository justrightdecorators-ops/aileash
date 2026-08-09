# Codebase — part 2 of 16

Contains:
- `modules/_ _ i n i t _ _ . p y`
- `modules/capture.py`
- `modules/codebase.py`
- `modules/conformance.py`
- `modules/consistency.py`
- `modules/console.py`


## `modules/_ _ i n i t _ _ . p y`

2 lines, 37 bytes

```
# makes this folder a python package

```


## `modules/capture.py`

385 lines, 17851 bytes

```python
"""
One-button decision capture - /x/capture/<action>

WHAT IT IS
----------
A drop-in button for an operator's own review screen. A human reviews an AI
output, clicks once, and the decision is sealed into the chain with who
reviewed it, on what device, against which inputs, and how long they took.

WHY IT IS TWO CALLS AND NOT ONE
-------------------------------
The obvious version is a single POST carrying a dwell time measured in the
browser. That number is the whole point - it is what makes rubber stamping
visible - and a number the reviewed party computes for itself is not
evidence. Anyone can set it to whatever looks diligent.

So the widget opens a case first. The server records the open time. When the
reviewer commits, the server computes the dwell itself from two timestamps it
owns. The browser never supplies the figure it is being judged on.

Same reason the verdict is withheld between the two calls: the machine's
answer is sealed at open and only returned at seal, so the chain shows the
human committed before they saw it. Ordering is the one thing that separates
judgement from agreement.

KEYS IN BROWSERS
----------------
An API key pasted into page JavaScript is public. Anyone reading the source
can post as that operator, forever.

So capture accepts a CAPTURE TOKEN: minted server-side by the operator from
their real key, bound to one origin, short-lived, and able to do exactly two
things - open a case and seal it. It cannot read records, cannot see other
cases, cannot touch any other module. Same idea as a publishable key.

The real API key still works for server-to-server calls. It should never
appear in a page.

DEVICES ARE THE BILLING UNIT
----------------------------
Every capture carries a device_id, and distinct devices per calendar month is
what billing is counted on. The registry here is that count: first seen, last
seen, events, per month. An operator can query their own figure at any time
and reconcile it against an invoice, rather than being told a number.

Device identifiers are hashed on arrival. The chain and the registry hold a
fingerprint, never the raw identifier.

    POST /x/capture/token     mint a browser-safe capture token (real key only)
    POST /x/capture/open      start a case, server records the clock
    POST /x/capture/seal      commit a verdict, server computes the dwell
    GET  /x/capture/devices   this month's billable device count
    GET  /x/capture/case?id=  the sealed record of one capture
    GET  /x/capture/summary   dwell and divergence across recent captures
"""

import hashlib, hmac, json, os, re, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate", "approve", "reject"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOKEN_TTL = 3600 * 12
MAX_OPEN_AGE = 3600 * 6

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_cases(case_id TEXT PRIMARY KEY,api_key TEXT,operator_fp TEXT,device_fp TEXT,input_hash TEXT,output_hash TEXT,machine_verdict TEXT,opened REAL,sealed REAL,human_verdict TEXT,dwell REAL,agreed INTEGER,note TEXT)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS capture_devices(api_key TEXT,device_fp TEXT,month TEXT,first_seen REAL,last_seen REAL,events INTEGER DEFAULT 0,PRIMARY KEY(api_key,device_fp,month))")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_key ON capture_cases(api_key,opened)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_cap_dev ON capture_devices(api_key,month)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("CAPTURE_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def _fp(v):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(v).strip().lower().encode(), hashlib.sha256).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _month(ts=None):
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m")


# ------------------------------------------------------------ capture token

def _mint(ctx, api_key, data):
    """Real key only. Returns a token safe to put in a page."""
    s = _secret()
    if not s:
        return {"error": "capture_secret_not_set",
                "message": "Set CAPTURE_SECRET in the environment first."}, 503
    origin = str(data.get("origin", "")).strip().lower()[:120]
    if not origin:
        return {"error": "origin_required",
                "message": "Bind the token to the site that will use it, e.g. https://app.yourcompany.com"}, 400
    try:
        ttl = min(int(data.get("ttl_seconds", TOKEN_TTL)), TOKEN_TTL)
    except (TypeError, ValueError):
        ttl = TOKEN_TTL
    exp = int(time.time()) + max(60, ttl)
    body = api_key + "|" + origin + "|" + str(exp)
    sig = hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32]
    token = "cap_" + str(exp) + "_" + hashlib.sha256(origin.encode()).hexdigest()[:8] + "_" + sig
    return {"capture_token": token, "origin": origin,
            "expires": _iso(exp), "expires_in_seconds": exp - int(time.time()),
            "scope": ["capture:open", "capture:seal"],
            "note": "Safe to place in a page. It cannot read records, cannot see other cases, and cannot reach any other module. Mint a fresh one from your server as needed - never put your real API key in a browser."}, 200


def _verify_token(ctx, token, origin):
    """Returns the owning api_key, or None."""
    s = _secret()
    if not s or not token or not token.startswith("cap_"):
        return None
    parts = token.split("_")
    if len(parts) != 4:
        return None
    try:
        exp = int(parts[1])
    except ValueError:
        return None
    if exp < time.time():
        return None
    ohash, sig = parts[2], parts[3]
    if origin:
        o = str(origin).strip().lower()[:120]
        if hashlib.sha256(o.encode()).hexdigest()[:8] != ohash:
            return None
    else:
        o = None
    with ctx["lock"]:
        keys = ctx["conn"].execute("SELECT key FROM api_keys WHERE active=1").fetchall()
    for (k,) in keys:
        if o is None:
            continue
        body = k + "|" + o + "|" + str(exp)
        if hmac.compare_digest(hmac.new(s, body.encode(), hashlib.sha256).hexdigest()[:32], sig):
            return k
    return None


def _resolve(ctx, api_key, data):
    """A real key wins; otherwise try a capture token bound to an origin."""
    if api_key:
        return api_key, "api_key"
    tok = str(data.get("capture_token", "")).strip()
    origin = str(data.get("origin", "")).strip()
    owner = _verify_token(ctx, tok, origin)
    if owner:
        return owner, "capture_token"
    return None, None


# ------------------------------------------------------------------ devices

def _touch_device(ctx, api_key, device_fp, ts):
    m = _month(ts)
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT events FROM capture_devices WHERE api_key=? AND device_fp=? AND month=?", (api_key, device_fp, m)).fetchone()
        if row:
            ctx["conn"].execute("UPDATE capture_devices SET last_seen=?,events=events+1 WHERE api_key=? AND device_fp=? AND month=?", (ts, api_key, device_fp, m))
            new = False
        else:
            ctx["conn"].execute("INSERT INTO capture_devices(api_key,device_fp,month,first_seen,last_seen,events) VALUES(?,?,?,?,?,1)", (api_key, device_fp, m, ts, ts))
            new = True
        ctx["conn"].commit()
    return new


def _devices(ctx, api_key, data):
    m = str(data.get("month", "")).strip() or _month()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT COUNT(*),SUM(events) FROM capture_devices WHERE api_key=? AND month=?", (api_key, m)).fetchone()
        months = ctx["conn"].execute("SELECT month,COUNT(*) FROM capture_devices WHERE api_key=? GROUP BY month ORDER BY month DESC LIMIT 12", (api_key,)).fetchall()
    n = rows[0] or 0
    return {"month": m, "billable_devices": n, "captures": rows[1] or 0,
            "rate_per_device": 0.50, "currency": "GBP",
            "estimated_charge": round(n * 0.50, 2),
            "history": [{"month": a, "devices": b} for a, b in months],
            "note": "A device counts once per calendar month however many captures it makes. Distinct devices is the billing unit - this is the same figure the invoice uses, so you can reconcile it yourself rather than being told a number."}, 200


# -------------------------------------------------------------------- cases

def _open(ctx, api_key, data):
    if not _secret():
        return {"error": "capture_secret_not_set"}, 503
    operator = str(data.get("operator_id", "")).strip()
    if not operator:
        return {"error": "operator_id_required",
                "message": "A capture with no named reviewer is not oversight."}, 400
    device = str(data.get("device_id", "")).strip()
    if not device:
        return {"error": "device_id_required",
                "message": "Devices are the billing unit and the record needs to say which one acted."}, 400

    ih = str(data.get("input_hash", "")).strip().lower()
    oh = str(data.get("output_hash", "")).strip().lower()
    for name, v in (("input_hash", ih), ("output_hash", oh)):
        if v and not HEX64.match(v):
            return {"error": "invalid_" + name,
                    "message": "Hash the content locally and send 64 hex characters. Never send the content itself."}, 400

    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    ts = time.time()
    ofp, dfp = _fp(operator), _fp(device)
    cid = "CAP-" + secrets.token_hex(5).upper()
    new_device = _touch_device(ctx, api_key, dfp, ts)

    detail = ("operator=" + (ofp or "")[:32] + ";device=" + (dfp or "")[:32] +
              ";input=" + (ih or "none") + ";output=" + (oh or "none") +
              ";machine_verdict_sealed=" + (mv or "none"))
    ev = {"user_id": "cap:" + cid, "action": "capture_opened", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "opened",
           "capture_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "no personal data and no content in this block - fingerprints and hashes only"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO capture_cases(case_id,api_key,operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed,note) VALUES(?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,NULL)",
                            (cid, api_key, ofp, dfp, ih or None, oh or None, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until seal",
            "new_device_this_month": new_device,
            "next": "POST the reviewer's verdict to /x/capture/seal with this case_id",
            "note": "The clock started here, on the server. The dwell time is not something the browser gets to report."}, 200


def _seal(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,machine_verdict,opened,sealed FROM capture_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_sealed",
                "message": "A capture commits once."}, 400

    hv = str(data.get("verdict", "")).strip().lower()
    if hv not in VERDICTS:
        return {"error": "invalid_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()

    ts = time.time()
    dwell = round(ts - row[3], 3)
    if dwell > MAX_OPEN_AGE:
        return {"error": "case_expired",
                "opened": _iso(row[3]),
                "message": "This case was opened more than six hours ago. Open a fresh one rather than sealing a stale clock."}, 400
    agreed = None if not row[2] else (1 if hv == row[2] else 0)

    detail = ("verdict=" + hv + ";dwell_seconds=" + str(dwell) +
              ";server_measured=true;reasoning=" + reasoning[:600])
    ev = {"user_id": "cap:" + cid, "action": "capture_sealed", "amount": 0,
          "country": "UK", "device_id": "capture", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CAPTURE_SEALED", "score": 0, "capture_action": "sealed",
           "capture_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE capture_cases SET sealed=?,human_verdict=?,dwell=?,agreed=? WHERE case_id=? AND api_key=?",
                            (ts, hv, dwell, agreed, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "verdict": hv, "dwell_seconds": dwell,
           "machine_verdict": row[2], "sealed": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "measured_by": "server",
           "note": "Your verdict was sealed before this response revealed ours. The chain fixes that order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "sealed " + str(dwell) + "s after the case opened - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT operator_fp,device_fp,input_hash,output_hash,machine_verdict,opened,sealed,human_verdict,dwell,agreed FROM capture_cases WHERE case_id=? AND api_key=?", (cid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("cap:" + cid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("capture_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    return {"case_id": cid.upper(),
            "operator_fingerprint": (row[0] or "")[:16] + "...",
            "device_fingerprint": (row[1] or "")[:16] + "...",
            "input_hash": row[2], "output_hash": row[3],
            "machine_verdict": row[4], "opened": _iso(row[5]),
            "sealed": _iso(row[6]), "human_verdict": row[7],
            "dwell_seconds": row[8],
            "agreed": (None if row[9] is None else bool(row[9])),
            "events": events,
            "ordering_proof": "The opened block precedes the sealed block in the chain, and both timestamps are the server's."}, 200


def _summary(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM capture_cases WHERE api_key=? AND sealed IS NOT NULL", (api_key,)).fetchall()
        openc = ctx["conn"].execute("SELECT COUNT(*) FROM capture_cases WHERE api_key=? AND sealed IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"captures": 0, "open_cases": openc,
                "note": "No sealed captures yet."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    under2 = len([d for d in dwells if d < 2])
    out = {"captures": len(rows), "open_cases": openc,
           "median_dwell_seconds": (dwells[n // 2] if n else None),
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " captures"
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "token":
            if not api_key:
                return {"error": "api_key_required",
                        "message": "Mint capture tokens from your server using your real key."}, 401
            return _mint(ctx, api_key, data)
        owner, how = _resolve(ctx, api_key, data)
        if not owner:
            return {"error": "invalid_credentials",
                    "message": "Send a real API key server-side, or a valid capture_token with the origin it was bound to."}, 401
        if action == "open":
            return _open(ctx, owner, data)
        if action == "seal":
            return _seal(ctx, owner, data)
    else:
        if not api_key:
            return {"error": "api_key_required",
                    "message": "Reading capture records needs the real key, not a capture token."}, 401
        if action == "devices":
            return _devices(ctx, api_key, data)
        if action == "summary":
            return _summary(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/codebase.py`

489 lines, 21403 bytes

```python
#!/usr/bin/env python3
"""
modules/codebase.py  -  dated evidence of what you held, and when
=================================================================

WHAT THIS IS, STATED HONESTLY FIRST
-----------------------------------
This does not prove ownership. Nothing cryptographic can. Ownership of
software is a legal fact established by authorship, company records and
signed assignment - not by a hash.

What it does produce is the evidence that decides most disputes about
software in practice: a dated, tamper-evident, externally anchored record
that a specific person held a specific body of code, in a specific form, at
a specific moment. When two parties later disagree about who had what
first, that is the question a court, a mediator or an investor actually
asks - and it is normally answered with commit dates, which are settable
fields that prove nothing.

This answers it with arithmetic instead.

WHAT IT DOES
------------
    POST /x/codebase/seal

Walks the deployed source tree, hashes every file, builds one manifest root
over all of them, and seals that root - together with a declaration of
authorship you supply - into the chain. From there it is anchored
externally and handed to peer chains like every other block.

Run it again next week and you get a second dated point. Run it on every
deploy and you accumulate a continuous, uneditable record of the codebase
evolving under your hand, which is a far stronger thing than a single
snapshot: a body of work with a history is much harder to dispute than a
file that appeared once.

WHAT THE MANIFEST CONTAINS - AND WHAT IT DOES NOT
-------------------------------------------------
For each file: its path and the SHA-256 of its exact bytes. Nothing else.
No contents leave the server, ever, by any route here. The hashes are
one-way, so the manifest reveals nothing about what the code does; it only
lets you demonstrate later that a file you hold now is byte-identical to
the file you held then.

The manifest route is deliberately KEYED rather than public. Only the root,
the file count and the total byte size are public. A public file listing
would hand an attacker a map of the deployment for no gain - the root is
all a third party needs in order to check a manifest you show them.

Excluded by default and never hashed: version control internals, caches,
databases, and anything that looks like a secret. Sealing a hash of your
own credentials file would be a poor way to protect them.

HOW YOU USE IT IN A DISPUTE
---------------------------
  1. You produce the sealed root, its block index, and the chain's
     external anchor.
  2. You produce your copy of the code.
  3. Anyone recomputes the manifest from your copy - the rules are
     published at /x/codebase/spec - and compares.

If it matches, you demonstrably held exactly that code no later than the
sealing time, and the record of it has not been altered since, because it
is a block in an anchored chain that peers also hold.

WHAT STILL HAS TO HAPPEN OUTSIDE THIS FILE
------------------------------------------
Stated plainly, because a module that let you believe it had settled your
legal position would be doing you harm:

  - Copyright arises on authorship. Sealing evidences it; it does not
    create or register it.
  - If a company operates the platform, the IP needs to sit with the right
    entity in writing, or the position is muddier than it looks.
  - Where two parties have collaborated, the only reliable answer is an
    agreement saying who owns what, signed before it matters rather than
    after.

This module makes the factual record unarguable. The legal position is a
separate job and needs a solicitor, not a hash.

    POST /x/codebase/seal      hash the tree, seal the root      (keyed)
    GET  /x/codebase/manifest  the full file list for a seal     (keyed)
    GET  /x/codebase/history   every seal, with root changes     (public)
    GET  /x/codebase/root      the latest sealed root            (public)
    GET  /x/codebase/spec      how to recompute it yourself      (public)
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Roots and history are public - a dated claim nobody can check is not
# evidence. The file listing is keyed, because it is a map of the
# deployment and a third party never needs it to verify a manifest.
PUBLIC = {("GET", "history"), ("GET", "root"), ("GET", "spec")}

FILE_PREFIX = b"AILEASH-FILE-v1:"
MANIFEST_PREFIX = b"AILEASH-MANIFEST-v1:"

MAX_FILES = 5000
MAX_FILE_BYTES = 8 * 1024 * 1024

# Never walked into.
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv",
             "venv", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
             "dist", "build", ".cache", "backups"}

# Never hashed. Secrets and databases are excluded on purpose - a hash of
# your credentials file is not evidence of anything you want to prove.
SKIP_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db-journal", ".db-wal",
                 ".db-shm", ".pyc", ".pyo", ".log", ".ots", ".pem", ".key",
                 ".crt", ".p12", ".pfx")
SKIP_NAMES = {".env", ".env.local", ".env.production", "secrets.json",
              "credentials.json", ".netrc", "id_rsa", ".DS_Store"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS codebase_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "manifest_root TEXT,file_count INTEGER,total_bytes INTEGER,"
                  "declaration TEXT,manifest TEXT,sealed REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_cb_root ON codebase_seal(manifest_root)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _app_root():
    """The directory the application is deployed from.

    This module lives in modules/, so the parent of that directory is the
    tree we want. Resolved rather than assumed, so it is correct whatever
    the working directory happens to be when the server starts.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(here)
    return parent if parent else here


def _skip(name):
    if name in SKIP_NAMES:
        return True
    lower = name.lower()
    return any(lower.endswith(suffix) for suffix in SKIP_SUFFIXES)


def _file_hash(path):
    """SHA-256 of the exact bytes, read in chunks so a large file cannot
    exhaust memory."""
    digest = hashlib.sha256()
    digest.update(FILE_PREFIX)
    size = 0
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                return None, size
            digest.update(chunk)
    return digest.hexdigest(), size


def _walk(root):
    """Every file under root, sorted by relative path.

    Sorting matters: the manifest must be reproducible by anyone holding
    the same files, and directory order is not stable across systems.
    """
    entries, skipped, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for filename in sorted(filenames):
            if _skip(filename):
                skipped.append(os.path.relpath(os.path.join(dirpath, filename), root))
                continue
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                digest, size = _file_hash(full)
            except OSError:
                skipped.append(relative)
                continue
            if digest is None:
                skipped.append(relative)
                continue
            entries.append({"path": relative, "sha256": digest, "bytes": size})
            total += size
            if len(entries) >= MAX_FILES:
                return entries, skipped, total, True
    return entries, skipped, total, False


def _manifest_root(entries):
    """One root over the whole tree.

    Deliberately a flat, ordered digest rather than a Merkle tree: there is
    no need for per-file proofs here, and a rule anyone can reimplement in
    four lines is worth more than a clever structure nobody checks.
    """
    digest = hashlib.sha256()
    digest.update(MANIFEST_PREFIX)
    for entry in entries:
        digest.update(("%s\0%s\n" % (entry["path"], entry["sha256"])).encode("utf-8"))
    return digest.hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _seal(ctx, api_key, data):
    author = str(data.get("author", "") or "").strip()[:120]
    entity = str(data.get("entity", "") or "").strip()[:120]
    statement = str(data.get("statement", "") or "").strip()[:1000]

    if not author:
        return {"error": "author_required",
                "message": "The name of the person declaring authorship. This is sealed "
                           "verbatim and becomes part of the permanent record."}, 400

    root_path = _app_root()
    started = time.time()
    entries, skipped, total_bytes, truncated = _walk(root_path)
    if not entries:
        return {"error": "nothing_to_seal",
                "message": "No files found to hash under the application root."}, 500

    manifest_root = _manifest_root(entries)
    now = time.time()

    declaration = {
        "author": author,
        "entity": entity or None,
        "statement": statement or None,
        "declared_at": _iso(now),
    }

    ev = {"user_id": "cb:" + manifest_root[:16], "action": "codebase_sealed", "amount": 0,
          "country": "UK", "device_id": "codebase", "anomaly": 0, "device_risk": 0}
    res = {"decision": "CODEBASE_SEALED", "score": 0, "codebase_version": VERSION,
           "manifest_root": manifest_root, "file_count": len(entries),
           "total_bytes": total_bytes, "author": author, "entity": entity or None,
           "statement": statement or None,
           "detail": "root=%s;files=%d;bytes=%d;author=%s"
                     % (manifest_root, len(entries), total_bytes, author)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT manifest_root,sealed FROM codebase_seal ORDER BY id ASC").fetchall()
        ctx["conn"].execute(
            "INSERT INTO codebase_seal(api_key,manifest_root,file_count,total_bytes,"
            "declaration,manifest,sealed,audit_hash,block_index) VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, manifest_root, len(entries), total_bytes,
             json.dumps(declaration), json.dumps(entries), now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "manifest_root": manifest_root,
        "file_count": len(entries), "total_bytes": total_bytes,
        "files_skipped": len(skipped),
        "sealed_at": _iso(now),
        "took_seconds": round(now - started, 2),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "declaration": declaration,
        "seal_number": len(prior) + 1,
        "codebase_version": VERSION,
        "what_this_establishes": ("That the person named above held a body of code producing "
                                  "exactly this manifest root, no later than this moment, and "
                                  "that the record cannot be altered afterwards - it is a block "
                                  "in a chain that is externally anchored and held by peers."),
        "what_it_does_not": ("It does not establish legal ownership. Ownership comes from "
                             "authorship, company records and signed assignment. This is the "
                             "dated factual record those arguments rest on, not a substitute "
                             "for them."),
        "how_to_use_it": ("Keep this response. To demonstrate the claim later, produce your copy "
                          "of the code and let anyone recompute the manifest root from it using "
                          "the published rules. If it matches, you held exactly that code by "
                          "this date."),
        "verify_the_block": "/x/consistency/ancestor?tip=" + audit_hash,
        "spec": "/x/codebase/spec",
    }

    if truncated:
        out["truncated"] = ("Hit the %d file cap. The root covers the files listed and no more - "
                            "raise MAX_FILES if the tree is genuinely larger." % MAX_FILES)
    if prior:
        last_root, last_time = prior[-1]
        if last_root == manifest_root:
            out["unchanged_since"] = _iso(last_time)
            out["message"] = ("Identical to the previous seal. The codebase has not changed "
                              "since %s and now carries an additional dated witness."
                              % _iso(last_time))
        else:
            out["previous_root"] = last_root
            out["previous_sealed_at"] = _iso(last_time)
            out["message"] = ("The codebase has changed since the last seal. Both roots remain "
                              "in the chain - a dated history of the work, which is stronger "
                              "evidence than any single snapshot.")
    else:
        out["message"] = ("First seal. Run this on every deploy and the history becomes a "
                          "continuous record of the work developing under one hand.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _manifest(ctx, data):
    root = str(data.get("root", data.get("manifest_root", ""))).strip().lower()
    with ctx["lock"]:
        if root:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal WHERE manifest_root=? LIMIT 1",
                (root,)).fetchone()
        else:
            row = ctx["conn"].execute(
                "SELECT manifest_root,file_count,total_bytes,declaration,manifest,sealed,"
                "audit_hash,block_index FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "not_found", "root": root or None}, 404

    try:
        files = json.loads(row[4])
    except Exception:
        files = []
    try:
        declaration = json.loads(row[3])
    except Exception:
        declaration = None

    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "declaration": declaration, "sealed_at": _iso(row[5]),
            "sealed_in_chain": row[6], "block_index": row[7],
            "files": files,
            "codebase_version": VERSION,
            "note": "Paths and hashes only. No file contents are held or returned by any route "
                    "in this module."}, 200


def _history(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,declaration,sealed,audit_hash,"
            "block_index FROM codebase_seal ORDER BY id ASC LIMIT 500").fetchall()
    if not rows:
        return {"count": 0, "seals": [],
                "message": "No codebase seal recorded yet."}, 200

    seals, last = [], None
    for root, count, total, declaration, sealed, audit_hash, block_index in rows:
        try:
            parsed = json.loads(declaration)
            author = parsed.get("author")
        except Exception:
            author = None
        seals.append({"manifest_root": root, "file_count": count, "total_bytes": total,
                      "author": author, "sealed_at": _iso(sealed),
                      "sealed_in_chain": audit_hash, "block_index": block_index,
                      "changed_from_previous": last is not None and root != last})
        last = root

    authors = {s["author"] for s in seals if s["author"]}
    return {"count": len(seals),
            "first_sealed": seals[0]["sealed_at"], "latest_sealed": seals[-1]["sealed_at"],
            "distinct_roots": len({s["manifest_root"] for s in seals}),
            "declared_authors": sorted(authors),
            "seals": seals,
            "codebase_version": VERSION,
            "what_this_is": "A dated, uneditable record of one body of code developing over "
                            "time under a declared author. A continuous history is materially "
                            "harder to dispute than a single snapshot.",
            "file_list": "Keyed - /x/codebase/manifest. The root is all anyone needs to check a "
                         "manifest you show them."}, 200


def _root(ctx):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT manifest_root,file_count,total_bytes,sealed,audit_hash,block_index,"
            "declaration FROM codebase_seal ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return {"error": "never_sealed"}, 404
    try:
        author = json.loads(row[6]).get("author")
    except Exception:
        author = None
    return {"manifest_root": row[0], "file_count": row[1], "total_bytes": row[2],
            "sealed_at": _iso(row[3]), "sealed_in_chain": row[4], "block_index": row[5],
            "declared_author": author,
            "codebase_version": VERSION,
            "verify_the_block": "/x/consistency/ancestor?tip=" + row[4],
            "recompute_it": "/x/codebase/spec"}, 200


def _spec():
    return {
        "codebase_version": VERSION,
        "purpose": "Dated, tamper-evident evidence that a named person held a specific body of "
                   "code at a specific moment.",
        "not_ownership": "This does not establish legal ownership and is not offered as though "
                         "it does. Ownership comes from authorship, company records and signed "
                         "assignment. This is the factual record those arguments rest on.",
        "file_hash": "sha256('AILEASH-FILE-v1:' || exact_file_bytes) as lowercase hex",
        "manifest_root": "sha256('AILEASH-MANIFEST-v1:' || for each file in path order: "
                         "path + NUL + file_hash + newline) as lowercase hex",
        "ordering": "files sorted by relative path, forward slashes, relative to the "
                    "application root",
        "excluded": {
            "directories": sorted(SKIP_DIRS),
            "suffixes": list(SKIP_SUFFIXES),
            "names": sorted(SKIP_NAMES),
            "why": "Version control internals and caches are not the work. Databases and "
                   "anything resembling a secret are excluded because hashing them proves "
                   "nothing worth proving and risks something worth protecting.",
        },
        "recompute_it_yourself": [
            "Take your copy of the source tree.",
            "Drop the excluded directories, suffixes and names above.",
            "Hash each remaining file with the file rule.",
            "Sort by relative path and apply the manifest rule.",
            "Compare with the sealed root. A match means byte-identical code.",
        ],
        "privacy": "No file contents are stored or returned by any route. The manifest holds "
                   "paths and one-way hashes only, and the file list itself is keyed.",
        "the_discipline": "Seal on every deploy. A single snapshot is a claim about one day; a "
                          "continuous dated history is a record of the work.",
        "what_to_do_as_well": "Get the legal position in writing - entity ownership of the IP, "
                              "and a signed agreement with any collaborator saying who owns "
                              "what. Do it before it matters. This module makes the facts "
                              "unarguable; it cannot make the paperwork exist.",
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
        if action == "history":
            return _history(ctx)
        if action == "root":
            return _root(ctx)
        if action == "manifest":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _manifest(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "root", "manifest (keyed)"],
            "POST": ["seal (keyed)"]}, 404

```


## `modules/conformance.py`

338 lines, 14845 bytes

```python
"""
Conformance testing - /x/conformance/<action>

WHAT THIS IS FOR
----------------
Three limits are documented elsewhere in this platform, and all three have
the same shape: the engine's arithmetic is sound, but the guarantee depends
on something outside the engine.

  1. Commit-before-reveal proves order - but only if the integrator does not
     show its reviewers the machine verdict before calling /open.
  2. Mutual witnessing gets its strength from breadth - two platforms
     witnessing only each other prove very little.
  3. A declaration is only as strong as the rules declared - one that
     constrains nothing passes everything.

None of these can be fixed by the engine on its own. All three can be
MEASURED, and a measured weakness is a different animal from an unmeasured
one. That is what this module does.

1. PROBES - testing the integration, not trusting it
----------------------------------------------------
The idea is borrowed openly from how real audits work, and specifically from
a point James Stokes made publicly: slip a case with a known answer into the
queue, unannounced, and see who catches it.

A probe creates a genuine oversight case whose machine verdict is
deliberately set to a known-wrong value. The reviewer sees it exactly like
any other case. Two things then follow:

  - If they agree with the deliberately wrong verdict, they did not evaluate
    it. That is a caught rubber stamp, sealed.
  - If the integration is showing them the verdict before /open is called,
    their probe agreement rate will match their normal agreement rate. If
    they are genuinely deciding blind, it will not. The gap between the two
    numbers is the conformance signal.

A single probe proves nothing about a person. A catch rate across dozens is
evidence about a process, which is the thing under audit.

2. WITNESS BREADTH - concentration is visible
---------------------------------------------
Reports how many distinct peers witness the chain, how concentrated the
observations are in the largest peer, and how many peers have gone quiet.
Below three live peers the network is reported as weak, because it is.

3. DECLARATION STRENGTH - rules that never fire
------------------------------------------------
Runs the live declaration against sealed records and reports, per rule, how
many records it actually CONSTRAINED - that is, how many matched its `when`
condition and therefore had to satisfy its `require`. A rule that has never
constrained a single record is not a standard. It is decoration, and it is
named as such.

HONEST LIMITS OF THIS MODULE
----------------------------
- Probes test the process, not any individual. Someone can catch a probe and
  still rubber stamp the next hundred cases.
- A determined integrator who identifies probe cases can treat them
  differently. Probe case references are not marked in any way the reviewer
  can see, but a sufficiently motivated operator controls their own UI.
- Breadth and strength are measurements, not enforcement. Nothing here can
  compel a platform to witness widely or declare strictly. It can only make
  the alternative visible.

    POST /x/conformance/probe        inject a probe case with a known-wrong verdict
    GET  /x/conformance/probes       catch rate, and the conformance gap
    GET  /x/conformance/witness      breadth, concentration, staleness
    GET  /x/conformance/declaration  per-rule strength - what each rule constrains
    GET  /x/conformance/report       all three, one call
"""

import importlib, json, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
INVERT = {"allow": "block", "block": "allow",
          "challenge": "allow", "escalate": "allow"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS conformance_probes(probe_id TEXT PRIMARY KEY,api_key TEXT,case_id TEXT,reviewer TEXT,planted_verdict TEXT,correct_verdict TEXT,injected REAL,resolved REAL,reviewer_verdict TEXT,caught INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_probe_key ON conformance_probes(api_key)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ------------------------------------------------------------------ probes

def _probe(ctx, api_key, data):
    reviewer = str(data.get("reviewer", "")).strip()
    if not reviewer:
        return {"error": "reviewer_required"}, 400
    correct = str(data.get("correct_verdict", "")).strip().lower()
    if correct not in INVERT:
        return {"error": "correct_verdict_required",
                "allowed": sorted(INVERT)}, 400
    material = data.get("material")
    if material is None:
        return {"error": "material_required",
                "message": "A probe must look like a real case or it tests nothing."}, 400

    planted = INVERT[correct]
    try:
        ovs = importlib.import_module("modules.oversight")
    except Exception as e:
        return {"error": "oversight_module_unavailable", "detail": str(e)}, 503

    ref = str(data.get("case_ref", "")).strip() or ("CASE-" + secrets.token_hex(3).upper())
    payload, status = ovs.handle("POST", "open",
                                 {"case_ref": ref, "reviewer": reviewer,
                                  "material": material,
                                  "machine_verdict": planted},
                                 api_key, ctx)
    if status != 200:
        return payload, status

    pid = "PRB-" + secrets.token_hex(4).upper()
    ts = time.time()
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO conformance_probes(probe_id,api_key,case_id,reviewer,planted_verdict,correct_verdict,injected,resolved,reviewer_verdict,caught) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL)",
                            (pid, api_key, payload["case_id"], reviewer, planted, correct, ts))
        ctx["conn"].commit()

    return {"probe_id": pid, "case_id": payload["case_id"],
            "case_ref": ref, "reviewer": reviewer,
            "planted_verdict": planted, "correct_verdict": correct,
            "injected": _iso(ts),
            "note": "This is an ordinary oversight case to the reviewer. Route it into their queue exactly like any other, or the probe is worthless."}, 200


def _resolve_probes(ctx, api_key):
    """Settle any probes whose oversight case has since been committed."""
    with ctx["lock"]:
        open_probes = ctx["conn"].execute("SELECT probe_id,case_id,planted_verdict,correct_verdict FROM conformance_probes WHERE api_key=? AND resolved IS NULL", (api_key,)).fetchall()
        for pid, cid, planted, correct in open_probes:
            row = ctx["conn"].execute("SELECT reviewer_verdict,committed FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
            if not row or not row[1]:
                continue
            rv = (row[0] or "").lower()
            caught = 1 if rv != planted else 0
            ctx["conn"].execute("UPDATE conformance_probes SET resolved=?,reviewer_verdict=?,caught=? WHERE probe_id=?",
                                (row[1], rv, caught, pid))
        ctx["conn"].commit()


def _probes(ctx, api_key):
    try:
        _resolve_probes(ctx, api_key)
    except Exception:
        pass
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT reviewer,caught,resolved FROM conformance_probes WHERE api_key=? AND resolved IS NOT NULL", (api_key,)).fetchall()
        pending = ctx["conn"].execute("SELECT COUNT(*) FROM conformance_probes WHERE api_key=? AND resolved IS NULL", (api_key,)).fetchone()[0]
    if not rows:
        return {"probes_resolved": 0, "probes_pending": pending,
                "note": "No probes have come back yet."}, 200

    by = {}
    for reviewer, caught, _r in rows:
        d = by.setdefault(reviewer, {"probes": 0, "caught": 0})
        d["probes"] += 1
        d["caught"] += caught

    out = []
    for reviewer, d in sorted(by.items()):
        rate = round(100 * d["caught"] / d["probes"], 1)
        entry = {"reviewer": reviewer, "probes": d["probes"],
                 "caught": d["caught"], "catch_rate_pct": rate}
        # conformance gap: probe agreement vs normal agreement
        try:
            ovs = importlib.import_module("modules.oversight")
            stats, _s = ovs.handle("GET", "reviewer", {"id": reviewer}, api_key, ctx)
            normal = stats.get("agreement_rate_pct")
            if normal is not None and d["probes"] >= 5:
                probe_agree = round(100 * (d["probes"] - d["caught"]) / d["probes"], 1)
                gap = round(abs(probe_agree - normal), 1)
                entry["normal_agreement_pct"] = normal
                entry["probe_agreement_pct"] = probe_agree
                entry["conformance_gap"] = gap
                if gap < 5 and normal > 90:
                    entry["flag"] = "probe agreement matches normal agreement at a high rate - consistent with the verdict being visible before commit"
        except Exception:
            pass
        if d["probes"] >= 5 and rate == 0:
            entry["flag"] = "caught none of " + str(d["probes"]) + " deliberately wrong verdicts"
        out.append(entry)

    total = sum(d["probes"] for d in by.values())
    caught = sum(d["caught"] for d in by.values())
    return {"probes_resolved": total, "probes_pending": pending,
            "caught": caught,
            "overall_catch_rate_pct": round(100 * caught / total, 1),
            "by_reviewer": out,
            "note": "A single probe proves nothing about a person. A catch rate across dozens is evidence about a process."}, 200


# ----------------------------------------------------------------- witness

def _witness(ctx, api_key):
    t = time.time()
    try:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer", (api_key,)).fetchall()
    except Exception:
        rows = []
    if not rows:
        return {"peers": 0, "strength": "none",
                "note": "No peers witnessed. Anchoring alone still applies; mutual witnessing does not."}, 200

    total = sum(r[1] for r in rows)
    live = [r for r in rows if (t - r[2]) < 6 * 3600]
    stale = [r for r in rows if 6 * 3600 <= (t - r[2]) < 48 * 3600]
    silent = [r for r in rows if (t - r[2]) >= 48 * 3600]
    top = max(rows, key=lambda r: r[1])
    conc = round(100 * top[1] / total, 1)

    if len(live) >= 5 and conc < 50:
        strength = "strong"
    elif len(live) >= 3:
        strength = "adequate"
    elif len(live) >= 1:
        strength = "weak"
    else:
        strength = "dormant"

    out = {"peers": len(rows), "live": len(live), "stale": len(stale),
           "silent": len(silent), "observations": total,
           "largest_peer_share_pct": conc,
           "strength": strength,
           "distinct_tips_seen": sum(r[3] for r in rows)}
    if len(live) < 3:
        out["flag"] = "fewer than three live peers - breadth is what makes witnessing meaningful, and this network does not have it yet"
    if conc > 80 and len(rows) > 1:
        out["concentration_flag"] = "over 80% of observations come from a single peer"
    if len(rows) == 1:
        out["reciprocity_warning"] = "a single peer pair proves very little - two parties witnessing only each other can still collude"
    return out, 200


# ------------------------------------------------------------- declaration

def _declaration(ctx, api_key):
    try:
        dec = importlib.import_module("modules.declare")
    except Exception as e:
        return {"error": "declare_module_unavailable", "detail": str(e)}, 503

    cur, status = dec.handle("GET", "current", {}, api_key, ctx)
    if status != 200:
        return cur, status
    rules = cur["declaration"]["rules"]
    ver = cur["version"]

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT event_json,result_json FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT 2000", (api_key,)).fetchall()

    parsed = []
    for ev, res in recs:
        try:
            r = {}
            r.update(json.loads(ev))
            r.update(json.loads(res))
            if str(r.get("decision", "")).endswith("_SEALED"):
                continue
            parsed.append(r)
        except Exception:
            pass

    report = []
    for rule in rules:
        constrained = 0
        violated = 0
        for r in parsed:
            if not dec._test(rule.get("when"), r):
                continue
            constrained += 1
            if not dec._test(rule.get("require"), r):
                violated += 1
        entry = {"rule": rule.get("id"), "describe": rule.get("describe"),
                 "records_constrained": constrained,
                 "violations": violated,
                 "coverage_pct": (round(100 * constrained / len(parsed), 1) if parsed else 0)}
        if constrained == 0:
            entry["flag"] = "this rule has never constrained a single record - it is decoration, not a standard"
        report.append(entry)

    dead = len([r for r in report if r["records_constrained"] == 0])
    covered = len({i for i, rule in enumerate(rules)
                   if report[i]["records_constrained"] > 0})
    out = {"declaration_version": ver, "rules": len(rules),
           "records_examined": len(parsed),
           "rules_that_constrain_nothing": dead,
           "rules_with_effect": covered,
           "per_rule": report}
    if dead:
        out["flag"] = str(dead) + " of " + str(len(rules)) + " rules constrain nothing"
    if not rules:
        out["flag"] = "an empty declaration passes everything"
    return out, 200


# ---------------------------------------------------------------- routing

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "probe":
            return _probe(ctx, api_key, data)
    else:
        if action == "probes":
            return _probes(ctx, api_key)
        if action == "witness":
            return _witness(ctx, api_key)
        if action == "declaration":
            return _declaration(ctx, api_key)
        if action in ("", "report"):
            p, _a = _probes(ctx, api_key)
            w, _b = _witness(ctx, api_key)
            d, _c = _declaration(ctx, api_key)
            return {"conformance_version": VERSION,
                    "integration": p, "witness_breadth": w,
                    "declaration_strength": d,
                    "note": "These are measurements, not enforcement. Nothing here compels good behaviour - it only makes the alternative visible."}, 200
    return {"error": "unknown_action", "action": action}, 404

```


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
