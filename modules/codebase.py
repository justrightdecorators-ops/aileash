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
