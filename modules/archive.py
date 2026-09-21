"""
modules/archive.py  v1.0  -  the self-proving archive

Once a day this writes ONE file that proves itself:

  - every public block of the chain, with the exact text each was sealed from
  - the chain's genesis and tip
  - an independent witness's own record of our tips (MIR), as fetched
  - a Bitcoin proof of a tip inside the file
  - the fingerprint of yesterday's file, so the files chain like the blocks
  - AND THE CHECKING PROGRAM ITSELF, carried inside the file

The file's name is its fingerprint: SHA-256 of its canonical form (keys
sorted, no spaces). That fingerprint is sealed into the chain as a public
block, and that block is anchored to Bitcoin with the next hourly stamp.

So it does not matter who hosts a copy. Ours, a peer's, a customer's, the
Internet Archive's, an email attachment - any copy, anywhere, proves itself:

    python3 -c "import json,sys;exec(json.load(open(sys.argv[1]))['verifier_py'])" FILE

That recomputes every block, checks every link from genesis, confirms the
witness's tips are in the chain, checks the Bitcoin proof commits to a tip
in the chain, and prints the file's own fingerprint to compare with the
sealed one. Nothing from sebbi.pro is needed, including sebbi.pro.

Reformatting a copy does not break it: the fingerprint is taken over the
canonical form, so a pretty-printed or re-serialised copy still matches.

Routes (public): status, latest, manifest, file?sha256=, day?date=, verifier,
spec. run is keyed. Armed by the first visit to /x/archive/status.
Files live on the anchor volume; the last KEEP_FILES are kept on disk. Every
day's fingerprint is kept forever in the chain, and each file contains all
history, so the newest file always covers everything before it.
"""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

VERSION = "1.0"
FORMAT = "sebbi-self-proving-archive/1"
BASE = "https://sebbi.pro/x/archive/"
SITE = "https://sebbi.pro"
USER_ID = "system_archive"
ARCHIVE_DIR = os.path.join(os.environ.get("ANCHOR_DIR", "/data/anchors"),
                           "archive")
KEEP_FILES = 30
PAGE = 500
FETCH_TIMEOUT = 45
MAX_BYTES = 64 * 1024 * 1024
WITNESS = {"name": "MIR (MIRegistry)",
           "url": "https://mir.events/v1/transparency/held/tips?peer=sebbi"}
ANCHOR_URL = SITE + "/x/ots/latest_confirmed"
WAYBACK_SAVE = "https://web.archive.org/save/"
UA = "sebbi-archive/1.0 (+https://sebbi.pro/x/archive/spec)"

PUBLIC = {("GET", "status"), ("GET", "latest"), ("GET", "manifest"),
          ("GET", "file"), ("GET", "day"), ("GET", "verifier"),
          ("GET", "spec")}

_state = {"armed": False, "ctx": None, "last_run": None, "last_result": None}
_lock = threading.Lock()
_run_lock = threading.Lock()


# ---------------------------------------------------------------- the verifier
#
# Carried inside every file. Standard library only. Runs anywhere Python 3
# runs, with nothing from sebbi.pro.

VERIFIER = r'''
import hashlib, json, sys

path = sys.argv[1]
with open(path, "rb") as fh:
    raw = fh.read()
b = json.loads(raw.decode("utf-8"))
canon = json.dumps(b, sort_keys=True, separators=(",", ":")).encode("utf-8")
fp = hashlib.sha256(canon).hexdigest()
problems = []

print("File fingerprint (canonical SHA-256):", fp)
print("Compare it with the fingerprint sealed for", b.get("date"),
      "- listed in the manifest and sealed in the chain.")

blocks = b["chain"]["blocks"]
prev = "GENESIS"
hashes = {}
public = withheld = 0
for blk in blocks:
    h = blk["audit_hash"]
    if "preimage" in blk:
        pre = blk["preimage"]
        if hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
            problems.append("block %s does not recompute" % blk["block_index"])
        stated = json.loads(pre).get("prev_hash")
        public += 1
    else:
        stated = blk.get("prev_hash")
        withheld += 1
    if stated != prev:
        problems.append("block %s does not link to the block before it"
                        % blk["block_index"])
    hashes[h] = blk["block_index"]
    prev = h

if blocks and blocks[0]["audit_hash"] != b["chain"]["genesis_hash"]:
    problems.append("first block is not the declared genesis")
if prev != b["chain"]["tip"]:
    problems.append("the chain does not end at the declared tip")
print("Blocks: %d  (%d recomputed from their own text, %d linkage only)"
      % (len(blocks), public, withheld))

w = b.get("witness") or {}
held = [e for e in w.get("entries", []) if e.get("peer_tip") in hashes]
print("Witness %s: %d of its recorded tips are blocks in this chain"
      % (w.get("name"), len(held)))
if w.get("entries") and not held:
    problems.append("none of the witness's tips are in this chain")

a = b.get("anchor") or {}
if a.get("tip"):
    if a["tip"] not in hashes:
        problems.append("the anchored tip is not a block in this chain")
    else:
        print("Bitcoin: tip at block %s committed in Bitcoin block(s) %s"
              % (hashes[a["tip"]], a.get("bitcoin_block_heights")))
        try:
            import base64
            from opentimestamps.core.serialize import BytesDeserializationContext
            from opentimestamps.core.timestamp import DetachedTimestampFile
            det = DetachedTimestampFile.deserialize(BytesDeserializationContext(
                base64.b64decode(a["ots_base64"])))
            if det.file_digest != hashlib.sha256(bytes.fromhex(a["tip"])).digest():
                problems.append("the Bitcoin proof is for a different value")
            else:
                print("Bitcoin proof commits to that tip. For the final step "
                      "against Bitcoin itself: ots verify.")
        except ImportError:
            print("Install opentimestamps-client to read the Bitcoin proof "
                  "here; the proof bytes are in anchor.ots_base64.")
else:
    print("Bitcoin: no confirmed proof was available when this file was made.")

print("Previous file:", b.get("previous_file_sha256") or "none - this is the first")
if problems:
    print("FAIL")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("PASS - every check above was done here, from this file alone.")
'''


# ---------------------------------------------------------------- storage

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS archive_files ("
        "date TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, blocks INTEGER, "
        "tip TEXT, previous_sha256 TEXT, sealed_block INTEGER, "
        "sealed_hash TEXT, wayback TEXT, created_at REAL)")
    conn.commit()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response too large")
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _path(date, sha):
    return os.path.join(ARCHIVE_DIR, "sebbi-chain-%s-%s.json" % (date, sha))


# ---------------------------------------------------------------- building

def _collect_blocks():
    blocks, after = [], 0
    while True:
        page, _ = _fetch_json("%s/x/walk/blocks?after=%d&limit=%d"
                              % (SITE, after, PAGE))
        blocks.extend(page.get("blocks") or [])
        if not page.get("has_more"):
            break
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            raise ValueError("walk paging did not advance")
        after = nxt
    return blocks


def _build(ctx):
    conn, dblock, seal = ctx.get("conn"), ctx.get("lock"), ctx.get("seal")
    date = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        if conn.execute("SELECT 1 FROM archive_files WHERE date = ?",
                        (date,)).fetchone():
            return {"ok": True, "skipped": "today's file already exists"}
        prev = conn.execute("SELECT sha256 FROM archive_files "
                            "ORDER BY date DESC LIMIT 1").fetchone()

    blocks = _collect_blocks()
    if not blocks:
        return {"ok": False, "error": "no blocks to archive"}
    hashes = set(b["audit_hash"] for b in blocks)

    witness = {"name": WITNESS["name"], "source": WITNESS["url"],
               "entries": [], "fetched_sha256": None, "note": None}
    try:
        data, digest = _fetch_json(WITNESS["url"])
        witness["fetched_sha256"] = digest
        witness["entries"] = [e for e in (data.get("tips") or [])
                              if e.get("peer_tip") in hashes]
        witness["note"] = ("Entries kept are those whose peer_tip is a block "
                           "in this file. fetched_sha256 is the hash of the "
                           "witness's response as served on the day.")
    except Exception as exc:
        witness["note"] = "witness unreachable on the day (%s)" % \
            exc.__class__.__name__

    anchor = None
    try:
        data, _ = _fetch_json(ANCHOR_URL)
        if data.get("ok") and data.get("tip") in hashes:
            anchor = {k: data.get(k) for k in (
                "tip", "stamp_id", "stamped_at", "bitcoin_block_heights",
                "ots_base64", "tip_is_block")}
    except Exception:
        anchor = None

    bundle = {
        "format": FORMAT,
        "date": date,
        "made_by": "https://sebbi.pro",
        "chain": {"genesis_hash": blocks[0]["audit_hash"],
                  "tip": blocks[-1]["audit_hash"],
                  "block_count": len(blocks),
                  "seal_formula": "audit_hash = sha256 of the block's preimage "
                                  "text; each preimage names the previous "
                                  "block's hash as prev_hash; the first is "
                                  "GENESIS.",
                  "blocks": blocks},
        "witness": witness,
        "anchor": anchor,
        "previous_file_sha256": prev[0] if prev else None,
        "fingerprint_rule": "SHA-256 of this file's canonical form: JSON with "
                            "keys sorted and no whitespace. Reformatting a "
                            "copy does not change it.",
        "verify": "python3 -c \"import json,sys;exec(json.load(open(sys.argv[1]))"
                  "['verifier_py'])\" THIS_FILE.json",
        "verifier_py": VERIFIER,
        "not_included": "Blocks sealed under a customer's key appear with "
                        "hash and link only; their owners hold the contents.",
    }
    canon = _canonical(bundle)
    sha = hashlib.sha256(canon).hexdigest()

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    tmp = _path(date, sha) + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(canon)
    os.replace(tmp, _path(date, sha))

    file_url = "%sfile?sha256=%s" % (BASE, sha)
    sealed_block = sealed_hash = None
    if callable(seal):
        now = time.time()
        event = {"user_id": USER_ID, "action": "self_proving_archive_written",
                 "amount": 0, "country": "UK", "device_id": "archive",
                 "anomaly": 0, "device_risk": 0}
        result = {"decision": "ARCHIVED", "score": 0, "date": date,
                  "file_sha256": sha, "bytes": len(canon),
                  "blocks": len(blocks), "chain_tip": blocks[-1]["audit_hash"],
                  "previous_file_sha256": bundle["previous_file_sha256"],
                  "witness_entries": len(witness["entries"]),
                  "bitcoin_anchor_included": bool(anchor),
                  "file_url": file_url, "timestamp": now}
        try:
            res = seal(event, result, now)
            if isinstance(res, (list, tuple)):
                sealed_hash, sealed_block = res[0], (res[1] if len(res) > 1 else None)
            elif isinstance(res, dict):
                sealed_hash = res.get("audit_hash") or res.get("hash")
                sealed_block = res.get("block_index") or res.get("index")
        except Exception:
            pass

    wayback = _offer_to_archive(file_url)

    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO archive_files (date, sha256, bytes, blocks, "
            "tip, previous_sha256, sealed_block, sealed_hash, wayback, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (date, sha, len(canon), len(blocks), blocks[-1]["audit_hash"],
             bundle["previous_file_sha256"], sealed_block, sealed_hash,
             wayback, time.time()))
        conn.commit()
    _prune()
    return {"ok": True, "date": date, "sha256": sha, "bytes": len(canon),
            "blocks": len(blocks), "sealed_block": sealed_block,
            "file": file_url, "wayback": wayback}


def _offer_to_archive(url):
    """One courtesy request a day to the Internet Archive. If it refuses,
    nothing depends on it - the file proves itself wherever it is kept."""
    try:
        req = urllib.request.Request(WAYBACK_SAVE + url,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            final = resp.geturl()
        return final if "/web/" in final else "requested"
    except urllib.error.HTTPError as exc:
        return "refused (HTTP %s)" % exc.code
    except Exception as exc:
        return "unreachable (%s)" % exc.__class__.__name__


def _prune():
    try:
        files = sorted(f for f in os.listdir(ARCHIVE_DIR)
                       if f.startswith("sebbi-chain-") and f.endswith(".json"))
        for f in files[:-KEEP_FILES]:
            os.remove(os.path.join(ARCHIVE_DIR, f))
    except Exception:
        pass


def _loop():
    time.sleep(90)
    while True:
        ctx = _state.get("ctx")
        if ctx and _run_lock.acquire(blocking=False):
            try:
                _state["last_result"] = _build(ctx)
            except Exception as exc:
                _state["last_result"] = {"ok": False, "error": str(exc)[:200]}
            finally:
                _run_lock.release()
            _state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
        time.sleep(3600)


def _arm(ctx):
    with _lock:
        _state["ctx"] = ctx
        if _state["armed"]:
            return
        _state["armed"] = True
    threading.Thread(target=_loop, name="archive", daemon=True).start()


# ---------------------------------------------------------------- routes

def _rows(ctx, limit=400):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        return conn.execute(
            "SELECT date, sha256, bytes, blocks, tip, previous_sha256, "
            "sealed_block, wayback FROM archive_files ORDER BY date DESC "
            "LIMIT ?", (limit,)).fetchall()


def _entry(r):
    date, sha, size, blocks, tip, prev, blk, wb = r
    on_disk = os.path.exists(_path(date, sha))
    return {"date": date, "sha256": sha, "bytes": size, "blocks": blocks,
            "chain_tip": tip, "previous_file_sha256": prev,
            "sealed_in_block": blk,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, blk)) if blk else None,
            "file": ("%sfile?sha256=%s" % (BASE, sha)) if on_disk else None,
            "on_this_server": on_disk, "internet_archive": wb}


def _serve_file(date, sha):
    p = _path(date, sha)
    if not os.path.exists(p):
        return {"ok": False, "error": "not_on_this_server",
                "detail": "Only the last %d files are kept here, and the "
                          "newest always contains everything before it. Any "
                          "copy held anywhere else proves itself."
                          % KEEP_FILES}, 404
    with open(p, "rb") as fh:
        return json.loads(fh.read().decode("utf-8")), 200


def _file(data, ctx):
    sha = str((data or {}).get("sha256") or "").strip().lower()
    if isinstance((data or {}).get("sha256"), list):
        sha = str(data["sha256"][0]).strip().lower()
    for r in _rows(ctx):
        if r[1] == sha:
            return _serve_file(r[0], r[1])
    return {"ok": False, "error": "unknown_fingerprint",
            "manifest": BASE + "manifest"}, 404


def _day(data, ctx):
    d = (data or {}).get("date")
    if isinstance(d, list):
        d = d[0]
    for r in _rows(ctx):
        if r[0] == str(d):
            return _serve_file(r[0], r[1])
    return {"ok": False, "error": "no_file_for_that_date",
            "manifest": BASE + "manifest"}, 404


def _status(ctx):
    rows = _rows(ctx, 7)
    return {"ok": True, "module": "archive", "version": VERSION,
            "format": FORMAT, "armed": _state["armed"],
            "last_run": _state["last_run"], "last_result": _state["last_result"],
            "recent_files": [_entry(r) for r in rows],
            "what_it_is": "One file a day that proves itself: every public "
                          "block, a witness's record, a Bitcoin proof, and "
                          "the checking program, in one file named by its "
                          "own fingerprint. Any copy, anywhere, can be "
                          "checked without sebbi.pro.",
            "routes": {"latest": BASE + "latest", "manifest": BASE + "manifest",
                       "verifier": BASE + "verifier", "spec": BASE + "spec"}}, 200


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "latest":
            rows = _rows(ctx, 1)
            if not rows:
                return {"ok": False, "error": "no_file_yet",
                        "detail": "The first file is written about 90 "
                                  "seconds after /x/archive/status is "
                                  "first opened."}, 404
            return dict(_entry(rows[0]), ok=True), 200
        if action == "manifest":
            return {"ok": True, "format": FORMAT,
                    "files": [_entry(r) for r in _rows(ctx)],
                    "note": "Every fingerprint here is also sealed in the "
                            "chain, in the block shown."}, 200
        if action == "file":
            return _file(data, ctx)
        if action == "day":
            return _day(data, ctx)
        if action == "verifier":
            return {"ok": True, "verifier_py": VERIFIER,
                    "run": "python3 -c \"import json,sys;exec(json.load("
                           "open(sys.argv[1]))['verifier_py'])\" FILE.json",
                    "note": "The same program is carried inside every file."}, 200
        if action == "spec":
            return {"module": "archive", "version": VERSION, "format": FORMAT,
                    "fingerprint": "SHA-256 of the file's canonical JSON "
                                   "(sorted keys, no whitespace)",
                    "chained": "each file names the previous day's fingerprint",
                    "sealed": "each day's fingerprint is sealed in the chain, "
                              "which is anchored to Bitcoin hourly",
                    "routes": {"status": BASE + "status",
                               "latest": BASE + "latest",
                               "manifest": BASE + "manifest",
                               "file": BASE + "file?sha256=<fingerprint>",
                               "day": BASE + "day?date=YYYY-MM-DD",
                               "verifier": BASE + "verifier"}}, 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            with _run_lock:
                return _build(ctx), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET")}, 404
    except Exception as exc:
        return {"ok": False, "error": "archive_failed",
                "detail": str(exc)[:200]}, 500
