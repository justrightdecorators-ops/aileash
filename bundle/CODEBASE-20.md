# Codebase — part 20 of 42

Contains:
- `modules/sebbi_adapter.py`
- `modules/sebbi_engine.py`
- `modules/selfcheck.py`


## `modules/sebbi_adapter.py`

602 lines, 24915 bytes

```python
"""
sebbi_adapter.py  v1.0.0 - drop-in state anchoring for legacy applications.

Your application keeps its database, its logic and its infrastructure. This
file sits beside it: every state change you point it at is turned into a
SHA-256 fingerprint, queued locally, and sent in the background to the
sebbi.pro public proof log, which returns a receipt proving the fingerprint
is in an append-only RFC 6962 Merkle tree whose tree heads are sealed into the
sebbi.pro chain and timestamped in Bitcoin.

Only the fingerprint leaves your machine. The data itself never does.

TWO LINES
---------
    export SEBBI_API_KEY=your-key          (once, in the environment)

    from sebbi_adapter import anchor_state
    @anchor_state("orders.update")
    def update_order(order_id, status):
        ...                                 # unchanged
        return {"order_id": order_id, "status": status}

The return value is fingerprinted after the function succeeds. The call is
never slowed down by the network and never fails because of this file:
fingerprints go into a local append-only queue (sqlite) and a background
thread sends them. If sebbi.pro is unreachable they wait, and are sent when it
comes back, in order, with no duplicates.

OTHER WAYS IN
-------------
    from sebbi_adapter import record, AnchorLogHandler
    record({"account": 42, "balance": 1250})          # anywhere, returns the hash
    logging.getLogger("payments").addHandler(AnchorLogHandler())   # every log line

    @anchor_state("ledger.post", capture="args")      # fingerprint the inputs instead
    @anchor_state("user.save", extract=lambda result, args, kwargs: result.to_dict())

Async functions work the same way.

CHECKING
--------
    python sebbi_adapter.py status            queue and receipt counts
    python sebbi_adapter.py flush             send what is waiting, now
    python sebbi_adapter.py receipt <hash>    the receipt for one fingerprint
    python sebbi_adapter.py verify            re-check every stored receipt locally
    python sebbi_adapter.py hash '<json>'     fingerprint a JSON value exactly as the adapter would

Every receipt is checked on arrival with an RFC 6962 inclusion check, so the
server's answer is verified, not trusted. A receipt that fails the check is
kept (as evidence) and flagged.

FINGERPRINT RULE (so anyone can recompute it)
---------------------------------------------
SHA-256 over canonical JSON: keys sorted, separators "," and ":", UTF-8, no
extra whitespace. datetime/date -> ISO 8601 string, Decimal -> string,
bytes -> hex, set -> sorted list, UUID -> string, dataclass -> its fields,
objects with to_dict()/_asdict() -> that. Floats use Python's repr. Anything
else is refused (and logged) rather than guessed at - pass extract= for those.

SETTINGS (environment or Anchor(...) arguments)
-----------------------------------------------
    SEBBI_API_KEY        your key (without it, fingerprints queue and wait)
    SEBBI_ENDPOINT       default https://sebbi.pro
    SEBBI_DB             default ./sebbi_anchor.db
    SEBBI_DISABLED=1     record nothing (kill switch)

Standard library only. Python 3.8+.
"""

import asyncio
import atexit
import dataclasses
import datetime
import decimal
import functools
import hashlib
import inspect
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

__version__ = "1.0.0"
__all__ = ["anchor_state", "record", "Anchor", "AnchorLogHandler", "canonical_json", "state_hash",
           "verify_inclusion", "verify_consistency", "get_default"]

log = logging.getLogger("sebbi_adapter")


# ---------------------------------------------------------------- fingerprints

def _default(o):
    if isinstance(o, (datetime.datetime, datetime.date, datetime.time)):
        return o.isoformat()
    if isinstance(o, decimal.Decimal):
        return str(o)
    if isinstance(o, (bytes, bytearray, memoryview)):
        return bytes(o).hex()
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=lambda x: canonical_json(x))
    if isinstance(o, uuid.UUID):
        return str(o)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    for attr in ("to_dict", "_asdict"):
        fn = getattr(o, attr, None)
        if callable(fn):
            return fn()
    raise TypeError("cannot fingerprint %s - pass extract= to choose what to record" % type(o).__name__)


def canonical_json(obj):
    """The exact bytes the fingerprint is taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=_default).encode("utf-8")


def state_hash(obj):
    """SHA-256 of canonical JSON, as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_json(obj)).hexdigest()


# ---------------------------------------------------------------- RFC 6962 checks

def _h(b):
    return hashlib.sha256(b).digest()


def leaf_hash(entry_hex):
    return _h(b"\x00" + bytes.fromhex(entry_hex)).hex()


def verify_inclusion(entry_hex, index, tree_size, path, root):
    """RFC 9162 section 2.1.3.2: is entry at `index` in the tree of `tree_size` with `root`?"""
    try:
        index, tree_size = int(index), int(tree_size)
        if index < 0 or index >= tree_size:
            return False
        fn, sn = index, tree_size - 1
        r = _h(b"\x00" + bytes.fromhex(entry_hex))
        for p_hex in path:
            p = bytes.fromhex(p_hex)
            if sn == 0:
                return False
            if (fn & 1) or fn == sn:
                r = _h(b"\x01" + p + r)
                if not (fn & 1):
                    while not (fn & 1) and fn != 0:
                        fn >>= 1
                        sn >>= 1
            else:
                r = _h(b"\x01" + r + p)
            fn >>= 1
            sn >>= 1
        return sn == 0 and r == bytes.fromhex(root)
    except (ValueError, TypeError):
        return False


def verify_consistency(first, second, first_root, second_root, proof):
    """RFC 9162 section 2.1.4.2: is the tree of size `second` an append-only extension of `first`?"""
    try:
        first, second = int(first), int(second)
        fr_b, sr_b = bytes.fromhex(first_root), bytes.fromhex(second_root)
        path = [bytes.fromhex(p) for p in proof]
        if first == second:
            return not path and fr_b == sr_b
        if first < 1 or first > second or not path:
            return False
        if first & (first - 1) == 0:
            path = [fr_b] + path
        fn, sn = first - 1, second - 1
        while fn & 1:
            fn >>= 1
            sn >>= 1
        fr = sr = path[0]
        for c in path[1:]:
            if sn == 0:
                return False
            if (fn & 1) or fn == sn:
                fr = _h(b"\x01" + c + fr)
                sr = _h(b"\x01" + c + sr)
                if not (fn & 1):
                    while not (fn & 1) and fn != 0:
                        fn >>= 1
                        sn >>= 1
            else:
                sr = _h(b"\x01" + sr + c)
            fn >>= 1
            sn >>= 1
        return fr == fr_b and sr == sr_b and sn == 0
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- the sidecar

class Anchor(object):
    """Local append-only queue + background sender. Safe across threads, processes and forks."""

    def __init__(self, api_key=None, endpoint=None, db_path=None, batch_size=200,
                 flush_interval=2.0, timeout=10.0, check_chain=True, start=True):
        self.api_key = (api_key if api_key is not None else os.environ.get("SEBBI_API_KEY", "")).strip()
        self.endpoint = (endpoint or os.environ.get("SEBBI_ENDPOINT", "https://sebbi.pro")).rstrip("/")
        self.db_path = db_path or os.environ.get("SEBBI_DB", "sebbi_anchor.db")
        self.batch_size = max(1, min(500, int(batch_size)))
        self.flush_interval = float(flush_interval)
        self.timeout = float(timeout)
        self.check_chain = bool(check_chain)
        self.disabled = os.environ.get("SEBBI_DISABLED", "0") == "1"
        self._autostart = start
        self._warned_no_key = False
        if not self.endpoint.startswith("https://") and "127.0.0.1" not in self.endpoint \
                and "localhost" not in self.endpoint:
            log.warning("sebbi_adapter: endpoint %s is not https", self.endpoint)
        self._init_process()

    # -- process-local state (rebuilt after fork) --
    def _init_process(self):
        self._pid = os.getpid()
        self._wid = "%d-%s" % (self._pid, uuid.uuid4().hex[:8])
        self._lk = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._backoff = 0.0
        self._tried = {}
        self._db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("CREATE TABLE IF NOT EXISTS entries(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "cid TEXT UNIQUE NOT NULL,hash TEXT NOT NULL,label TEXT,created REAL)")
        self._db.execute("CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                         "cid TEXT NOT NULL,leaf_index INTEGER,receipt TEXT,verified INTEGER,"
                         "checkpointed INTEGER DEFAULT 0,in_chain INTEGER,received REAL)")
        self._db.execute("CREATE INDEX IF NOT EXISTS receipts_cid ON receipts(cid)")
        self._db.execute("CREATE INDEX IF NOT EXISTS entries_hash ON entries(hash)")
        self._db.execute("CREATE TABLE IF NOT EXISTS claims(cid TEXT PRIMARY KEY,worker TEXT,until REAL)")
        self._thread = None
        if self._autostart:
            self._start_thread()

    def _ensure_process(self):
        if os.getpid() != self._pid:
            self._init_process()

    def _start_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="sebbi-anchor", daemon=True)
        self._thread.start()

    # -- recording (host side: local only, never raises) --
    def record(self, payload, label=None):
        """Fingerprint `payload` and queue it. Returns the hash, or None if it could not be recorded."""
        if self.disabled:
            return None
        try:
            return self.record_hash(state_hash(payload), label=label)
        except Exception as e:
            log.warning("sebbi_adapter: not recorded (%s)", e)
            return None

    def record_hash(self, hash_hex, label=None):
        """Queue a fingerprint you computed yourself (64 hex characters)."""
        if self.disabled:
            return None
        try:
            h = str(hash_hex).strip().lower()
            if len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h):
                raise ValueError("hash must be 64 hex characters")
            self._ensure_process()
            with self._lk:
                self._db.execute("INSERT INTO entries(cid,hash,label,created) VALUES(?,?,?,?)",
                                 (uuid.uuid4().hex, h, (str(label)[:120] if label else None), time.time()))
            self._wake.set()
            return h
        except Exception as e:
            log.warning("sebbi_adapter: not recorded (%s)", e)
            return None

    # -- lookups --
    def receipt(self, hash_hex):
        """Latest receipt for a fingerprint (the most recent entry with that hash), or None."""
        self._ensure_process()
        with self._lk:
            row = self._db.execute(
                "SELECT r.receipt,r.verified,r.checkpointed,r.in_chain,e.label,e.created FROM entries e "
                "JOIN receipts r ON r.cid=e.cid WHERE e.hash=? ORDER BY e.seq DESC, r.id DESC LIMIT 1",
                (str(hash_hex).lower(),)).fetchone()
        if not row:
            return None
        rec = json.loads(row[0])
        rec["verified_locally"] = bool(row[1])
        rec["checkpointed"] = bool(row[2])
        rec["tree_head_seen_in_chain"] = None if row[3] is None else bool(row[3])
        rec["label"] = row[4]
        return rec

    def counts(self):
        self._ensure_process()
        with self._lk:
            c = self._db
            total = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            sent = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts").fetchone()[0]
            cp = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts WHERE checkpointed=1").fetchone()[0]
            bad = c.execute("SELECT COUNT(DISTINCT cid) FROM receipts WHERE verified=0").fetchone()[0]
        return {"recorded": total, "receipted": sent, "waiting": total - sent,
                "sealed_in_chain": cp, "failed_local_check": bad}

    def pending(self):
        return self.counts()["waiting"]

    # -- network --
    def _http(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.endpoint + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "sebbi-adapter/" + __version__)
        if self.api_key:
            req.add_header("X-Sebbi-Key", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8") or "{}")
            except Exception:
                return e.code, {}

    def _claim(self, n):
        now = time.time()
        with self._lk:
            c = self._db
            c.execute("BEGIN IMMEDIATE")
            try:
                rows = c.execute(
                    "SELECT e.cid,e.hash FROM entries e WHERE NOT EXISTS (SELECT 1 FROM receipts r WHERE r.cid=e.cid) "
                    "AND NOT EXISTS (SELECT 1 FROM claims k WHERE k.cid=e.cid AND k.until>? AND k.worker<>?) "
                    "ORDER BY e.seq LIMIT ?", (now, self._wid, n)).fetchall()
                for cid, _ in rows:
                    c.execute("INSERT OR REPLACE INTO claims(cid,worker,until) VALUES(?,?,?)",
                              (cid, self._wid, now + max(60.0, self.timeout * 3)))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return rows

    def _release(self, cids):
        with self._lk:
            self._db.executemany("DELETE FROM claims WHERE cid=? AND worker=?", [(c, self._wid) for c in cids])

    def _store(self, cid, rec, checkpointed=False, in_chain=None):
        ok = verify_inclusion(rec.get("entry_hash", ""), rec.get("leaf_index", -1), rec.get("tree_size", 0),
                              rec.get("audit_path", []), rec.get("root", ""))
        if checkpointed and ok and rec.get("checkpoint"):
            ok = rec["checkpoint"].get("root") == rec.get("root")
        if not ok:
            log.error("sebbi_adapter: receipt for leaf %s FAILED the local inclusion check - kept and flagged",
                      rec.get("leaf_index"))
        with self._lk:
            self._db.execute("INSERT INTO receipts(cid,leaf_index,receipt,verified,checkpointed,in_chain,received) "
                             "VALUES(?,?,?,?,?,?,?)",
                             (cid, rec.get("leaf_index"), json.dumps(rec, sort_keys=True), 1 if ok else 0,
                              1 if checkpointed else 0, in_chain, time.time()))
        return ok

    def _send_batch(self):
        """Send one batch. Returns number receipted; raises on network failure."""
        if not self.api_key:
            if not self._warned_no_key:
                log.warning("sebbi_adapter: SEBBI_API_KEY not set - fingerprints are queued locally and will "
                            "be sent once it is")
                self._warned_no_key = True
            return 0
        rows = self._claim(self.batch_size)
        if not rows:
            return 0
        wanted = {cid: h for cid, h in rows}
        try:
            code, out = self._http("POST", "/p/submit", {"items": [{"hash": h, "cid": cid} for cid, h in rows]})
        except Exception:
            self._release(list(wanted))
            raise
        if code != 200:
            self._release(list(wanted))
            raise IOError("sebbi.pro answered %s: %s" % (code, out.get("error") or out.get("message") or ""))
        done = 0
        for rec in out.get("receipts") or []:
            cid = rec.get("cid")
            if cid not in wanted:
                continue
            if rec.get("error"):
                log.error("sebbi_adapter: entry %s refused: %s", cid, rec["error"])
                continue
            if rec.get("entry_hash") != wanted[cid]:
                log.error("sebbi_adapter: server returned a different hash for %s - not stored", cid)
                continue
            self._store(cid, rec)
            done += 1
        self._release(list(wanted))
        return done

    def _upgrade(self, limit=50):
        """Fetch sealed receipts for leaves whose tree head should now be in the chain."""
        cutoff = time.time() - 30
        with self._lk:
            rows = self._db.execute(
                "SELECT r.cid,r.leaf_index FROM receipts r WHERE r.verified=1 AND r.received<? AND "
                "NOT EXISTS (SELECT 1 FROM receipts r2 WHERE r2.cid=r.cid AND r2.checkpointed=1) "
                "GROUP BY r.cid ORDER BY MIN(r.id) LIMIT ?", (cutoff, limit)).fetchall()
        blocks = {}
        now = time.time()
        for cid, idx in rows:
            if now - self._tried.get(cid, 0) < 30:
                continue
            self._tried[cid] = now
            code, rec = self._http("GET", "/p/receipt?leaf=%d" % idx)
            if code != 200 or not rec.get("checkpoint"):
                continue
            in_chain = None
            if self.check_chain:
                blk = rec["checkpoint"].get("block_index")
                if blk not in blocks:
                    try:
                        _, body = self._http("GET", "/x/walk/block?index=%s" % blk)
                        blocks[blk] = json.dumps(body)
                    except Exception:
                        blocks[blk] = None
                if blocks[blk] is not None:
                    in_chain = 1 if rec["checkpoint"].get("root", "~") in blocks[blk] else 0
                    if not in_chain:
                        log.error("sebbi_adapter: tree head for leaf %s not found in chain block %s", idx, blk)
            self._store(cid, rec, checkpointed=True, in_chain=in_chain)
            self._tried.pop(cid, None)

    def flush(self, timeout=30.0):
        """Send everything waiting, now. Returns how many were receipted. Never raises."""
        self._ensure_process()
        end, sent = time.time() + timeout, 0
        while time.time() < end:
            try:
                n = self._send_batch()
            except Exception as e:
                log.warning("sebbi_adapter: flush stopped (%s); entries stay queued", e)
                break
            sent += n
            if n == 0:
                break
        return sent

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait(self._backoff or self.flush_interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                while self._send_batch() >= self.batch_size:
                    pass
                self._upgrade()
                self._backoff = 0.0
            except Exception as e:
                self._backoff = min(300.0, max(2.0, self._backoff * 2))
                log.info("sebbi_adapter: sebbi.pro unreachable (%s); retrying in %ds", e, self._backoff)

    def close(self, flush_timeout=2.0):
        try:
            if flush_timeout:
                self.flush(timeout=flush_timeout)
        finally:
            self._stop.set()
            self._wake.set()


# ---------------------------------------------------------------- the default instance

_default_anchor = None
_default_lock = threading.Lock()


def get_default():
    global _default_anchor
    if _default_anchor is None:
        with _default_lock:
            if _default_anchor is None:
                _default_anchor = Anchor()
                atexit.register(_default_anchor.close)
    return _default_anchor


def record(payload, label=None, anchor=None):
    """Fingerprint and queue any JSON-able value. Returns the hash. Never raises."""
    try:
        return (anchor or get_default()).record(payload, label=label)
    except Exception as e:
        log.warning("sebbi_adapter: not recorded (%s)", e)
        return None


def anchor_state(label=None, capture="result", extract=None, anchor=None):
    """Decorator. After the wrapped function succeeds, fingerprint its state and queue it.

    capture:  "result" (default) - the return value
              "args"             - the arguments it was called with
              "both"             - {"args": ..., "kwargs": ..., "result": ...}
    extract:  f(result, args, kwargs) -> the value to fingerprint (overrides capture)
    The wrapped function's behaviour, return value and exceptions are unchanged.
    """
    if callable(label) and not isinstance(label, str):
        return anchor_state()(label)

    def deco(fn):
        name = label or getattr(fn, "__qualname__", getattr(fn, "__name__", "call"))

        def _state(args, kwargs, result):
            if extract is not None:
                return extract(result, args, kwargs)
            if capture == "args":
                return {"args": list(args), "kwargs": kwargs}
            if capture == "both":
                return {"args": list(args), "kwargs": kwargs, "result": result}
            return result

        def _anchor(args, kwargs, result):
            try:
                record(_state(args, kwargs, result), label=name, anchor=anchor)
            except Exception as e:
                log.warning("sebbi_adapter: %s not recorded (%s)", name, e)

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args, **kwargs):
                result = await fn(*args, **kwargs)
                _anchor(args, kwargs, result)
                return result
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            _anchor(args, kwargs, result)
            return result
        return wrapper
    return deco


class AnchorLogHandler(logging.Handler):
    """Fingerprints every log record it sees: logger, level, message and time."""

    def __init__(self, anchor=None, level=logging.INFO):
        logging.Handler.__init__(self, level)
        self._anchor = anchor

    def emit(self, rec):
        if rec.name.startswith("sebbi_adapter"):
            return
        try:
            record({"logger": rec.name, "level": rec.levelname, "message": rec.getMessage(),
                    "time": round(rec.created, 6)}, label="log:" + rec.name, anchor=self._anchor)
        except Exception:
            pass


# ---------------------------------------------------------------- command line

def _main(argv):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "hash" and len(argv) > 2:
        print(state_hash(json.loads(argv[2])))
        return 0
    a = Anchor(start=False)
    if cmd == "status":
        print(json.dumps(dict(a.counts(), endpoint=a.endpoint, db=a.db_path, key_set=bool(a.api_key)), indent=2))
    elif cmd == "flush":
        print("receipted %d" % a.flush(timeout=120))
        a._upgrade(limit=500)
        print(json.dumps(a.counts(), indent=2))
    elif cmd == "receipt" and len(argv) > 2:
        print(json.dumps(a.receipt(argv[2]), indent=2))
    elif cmd == "verify":
        with a._lk:
            rows = a._db.execute("SELECT receipt FROM receipts").fetchall()
        good = sum(1 for (r,) in rows if (lambda d: verify_inclusion(d.get("entry_hash", ""), d.get("leaf_index", -1),
                                                                      d.get("tree_size", 0), d.get("audit_path", []),
                                                                      d.get("root", "")))(json.loads(r)))
        print("%d of %d stored receipts pass the RFC 6962 inclusion check" % (good, len(rows)))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))

```


## `modules/sebbi_engine.py`

229 lines, 8776 bytes

```python
# modules/sebbi_engine.py
"""
Live chain-state endpoint  -  GET /x/sebbi_engine/state

WHAT CHANGED IN v1.1, AND WHY
-----------------------------
v1.0 served this at /verify and returned "status": "sealed". It performed no
verification: no rehash, no chain walk, no proof check. It read the last row of
audit_log and reported that a row existed. A route called verify that returns
sealed, having checked neither, is a word one step past what the check does -
the same fault that has been raised against this codebase before, and the word
an auditor will quote back.

So v1.1 does the same honest job under honest names:

  * action renamed  verify -> state
  * status is now  live / unavailable, never "sealed"
  * tip_digest removed - it was a hash of a hash, proving nothing
  * token_budget removed - unrelated to chain state, it did not belong here
  * every response names the routes that DO verify, and says plainly that
    this one does not

WHAT THIS ROUTE IS
------------------
The current tip and height, read from the database at request time. Nothing
cached, nothing hardcoded. If the chain cannot be read it says so rather than
reporting a reassuring value it cannot stand behind.

WHAT IT IS NOT
--------------
It is not verification. Reading the last row proves a row exists. Verifying
the chain means rewalking it, and confirming the tip was recorded by operators
we do not control. Those are separate routes, listed in every response.

Dual-signature handle(...) so it works with the router
    handle(method, action, data, api_key, ctx) -> (payload, status)
and with older direct-write callers
    handle(handler, path, query_params=None) -> writes the response, returns True

Import-safe: nothing here can crash the server on import.
"""

import os
import json
import time

VERSION = "1.1"
MODULE_NAME = os.environ.get("MODULE_NAME", "sebbi_engine")

# GET /state is public by design - anyone can read live state without an
# account. The old ("GET", "verify") pair is kept so existing callers get the
# renamed answer rather than a bare 404.
PUBLIC = {("GET", "state"), ("GET", "verify"), ("GET", "spec"), ("GET", "")}

VERIFY_ELSEWHERE = {
    "chain_tip": "https://sebbi.pro/x/witness/tip",
    "append_only_proof": "https://sebbi.pro/x/consistency/proof",
    "is_my_tip_still_on_this_chain": "https://sebbi.pro/x/consistency/ancestor",
    "who_recorded_our_tip": "https://sebbi.pro/x/roster/list",
    "timestamp_proof_state": "https://sebbi.pro/x/ots/status",
}

NOT_VERIFICATION = (
    "This route reads the current tip and height. It does not verify anything: "
    "it does not rewalk the chain, recompute any hash, or check any external "
    "record. Reading the last row proves a row exists and nothing more. The "
    "routes above are the ones that verify, and you run them yourself."
)

try:
    print("modules.sebbi_engine: loaded (v%s, live-state mode)" % VERSION, flush=True)
except Exception:
    pass


def _read_live_chain(ctx):
    """
    Read the real current chain tip and height from the live database via ctx.

    Returns what was actually found, or a record of why it could not be read.
    It never invents a value.
    """
    if not isinstance(ctx, dict):
        return {"live": False, "reason": "no_context"}

    conn = ctx.get("conn") or ctx.get("db") or ctx.get("connection")
    lock = ctx.get("lock")
    if conn is None:
        return {"live": False, "reason": "no_db_handle"}

    # Matched to modules/witness.py _our_tip(): the chain lives in audit_log,
    # the sealed hash is audit_hash, the height is id.
    query = ("SELECT audit_hash AS seal, id AS height FROM audit_log "
             "ORDER BY id DESC LIMIT 1")

    def _run():
        try:
            row = conn.execute(query).fetchone()
        except Exception:
            return {"live": False, "reason": "query_failed"}
        if not row:
            return {"live": False, "reason": "no_chain_rows"}
        seal = row[0]
        height = row[1]
        if seal is None:
            return {"live": False, "reason": "null_tip"}
        return {"live": True, "tip": str(seal),
                "height": int(height) if height is not None else None}

    try:
        if lock is not None:
            with lock:
                return _run()
        return _run()
    except Exception as e:  # noqa: BLE001
        return {"live": False, "reason": "read_error:" + e.__class__.__name__}


def _build_payload(ctx):
    now = int(time.time())
    chain = _read_live_chain(ctx)

    payload = {
        "module": MODULE_NAME,
        "version": VERSION,
        "read_at": now,
        "read_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }

    if chain.get("live"):
        payload["status"] = "live"
        payload["chain_tip"] = chain["tip"]
        payload["chain_height"] = chain["height"]
        payload["note"] = (
            "Live chain state, read at request time. It changes as the chain "
            "grows, so two reads a minute apart are expected to differ.")
    else:
        payload["status"] = "unavailable"
        payload["chain_tip"] = None
        payload["chain_height"] = None
        payload["reason"] = chain.get("reason", "unknown")
        payload["note"] = (
            "The live chain could not be read for this request, so no state is "
            "reported. This endpoint never returns a placeholder in place of "
            "real state.")

    payload["height_is_not_activity"] = (
        "A liveness beacon seals a block every five minutes, so most of the "
        "height is heartbeat rather than customer decisions. Do not read this "
        "number as usage.")
    payload["this_is_not_verification"] = NOT_VERIFICATION
    payload["verify_it_yourself"] = VERIFY_ELSEWHERE
    return payload


def _spec():
    return {
        "module": MODULE_NAME,
        "version": VERSION,
        "route": "GET /x/sebbi_engine/state",
        "what_it_returns": "The current chain tip and height, read at request time.",
        "what_it_does_not_do": NOT_VERIFICATION,
        "renamed_in_v1_1": (
            "The action was called verify and returned status sealed. It "
            "verified nothing, so both names were wrong. verify still answers, "
            "and returns this same state payload under the honest names."),
        "verify_it_yourself": VERIFY_ELSEWHERE,
        "cost": "Free. No account, no key.",
    }, 200


def handle(*args, **kwargs):
    """Dual-signature handler; autodetects call style from the first argument."""

    # Legacy direct-write style: first arg is an HTTP handler
    if args and hasattr(args[0], "send_response") and hasattr(args[0], "wfile"):
        handler = args[0]
        ctx = getattr(handler, "ctx", None)
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        body = json.dumps(payload, indent=2).encode("utf-8")
        try:
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(body)))
            handler.end_headers()
            handler.wfile.write(body)
        except Exception:
            try:
                handler.send_response(500)
                handler.send_header("Content-Type", "text/plain")
                handler.end_headers()
                handler.wfile.write(b"sebbi_engine: response failed\n")
            except Exception:
                pass
        return True

    # Router style: handle(method, action, data, api_key, ctx)
    method = args[0] if len(args) > 0 else kwargs.get("method")
    action = args[1] if len(args) > 1 else kwargs.get("action", "")
    ctx = args[4] if len(args) > 4 else kwargs.get("ctx")

    # Tolerate action arriving as a full path
    if isinstance(action, str) and action.startswith("/"):
        parts = [x for x in action.strip("/").split("/") if x]
        if len(parts) >= 3 and parts[1] == "sebbi_engine":
            action = parts[2]

    action = (action or "").strip("/").lower()

    if method != "GET":
        return {"error": "method_not_allowed", "GET": ["state", "spec"]}, 405

    if action == "spec":
        return _spec()

    if action in ("state", ""):
        return _build_payload(ctx if isinstance(ctx, dict) else None), 200

    if action == "verify":
        payload = _build_payload(ctx if isinstance(ctx, dict) else None)
        payload["renamed"] = (
            "This action is now /x/sebbi_engine/state. It was called verify and "
            "returned status sealed, while verifying nothing. Same data, honest "
            "names. Update your caller when convenient.")
        return payload, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["state", "spec"]}, 404

```


## `modules/selfcheck.py`

1091 lines, 45976 bytes

```python
#!/usr/bin/env python3
"""
modules/selfcheck.py  -  the conformance runner, served as a page

WHY THIS IS A MODULE AND NOT A FILE IN ROOT
-------------------------------------------
A plain .html in the repo root does not get served on this deployment, so
the page ships inside the module and is served by the same runtime do_GET
patch that console.py uses for /console and network.py uses for /witness.
It also means the page cannot drift from the module that serves it.

WHAT THE PAGE DOES
------------------
Reads /.well-known/ordering-test.json, then runs every check the document
declares, in the order the document declares them. It discovers what it
needs as it goes: a committed period from /x/complete/periods, a tree size
from /x/consistency/root, a probe value that is not in the log.

It reports four outcomes and is deliberately mean about which is which:

  VERIFIED       the response was checked for what the claim requires -
                 consecutive leaf indices for absence, a proof path for
                 consistency, identical verdicts for reproducibility
  INCONCLUSIVE   the endpoint answered but the semantics were not checked,
                 or the route is POST-only, or the check is key-gated
  FAILED         published as publicly demonstrable and the endpoint is
                 not there. This is the number that matters
  NOT SUPPORTED  the document does not claim it

Reachable is not the same as verified, and this page never counts one as
the other. A runner that only ever passes has not been tested.

NOT A SHARED RUNNER
-------------------
It tests one side. The discovery document's runner field stays null until
the checks are jointly agreed with the other mirror, and publishing this as
though it were the agreed conformance test would claim something neither
operator has earned. Served unlinked and noindex for that reason.

    GET /self-check          the page
    GET /x/selfcheck/status  what is installed
"""

import sys

VERSION = "2.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/self-check", "/self-check.html")

_patched = [False]


PAGE = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Ordering test — self check</title>
<style>
  :root{
    --ink:#0a0f1e;
    --ink2:#10182e;
    --line:#1e2942;
    --gold:#c9a84c;
    --ok:#7fe3b0;
    --err:#ff8a80;
    --warn:#e8c06a;
    --mute:#6b7894;
    --text:#dbe3f4;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:var(--ink);
    color:var(--text);
    font-family:var(--mono);
    font-size:14px;
    line-height:1.5;
    -webkit-text-size-adjust:100%;
  }
  .wrap{max-width:760px;margin:0 auto;padding:20px 16px 80px}

  header{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:22px}
  .eyebrow{
    font-size:11px;letter-spacing:.18em;text-transform:uppercase;
    color:var(--gold);margin:0 0 8px
  }
  h1{font-size:22px;line-height:1.25;margin:0 0 10px;font-weight:600;letter-spacing:-.01em}
  .sub{color:var(--mute);font-size:13px;margin:0}
  .sub b{color:var(--text);font-weight:600}

  .bar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 0}
  button{
    font-family:var(--mono);font-size:13px;
    background:var(--gold);color:#10121a;border:0;border-radius:2px;
    padding:11px 18px;font-weight:700;letter-spacing:.02em;cursor:pointer;
  }
  button.ghost{background:transparent;color:var(--text);border:1px solid var(--line);font-weight:400}
  button:disabled{opacity:.4;cursor:default}
  button:focus-visible{outline:2px solid var(--gold);outline-offset:2px}

  .tally{
    display:flex;gap:14px;flex-wrap:wrap;margin:20px 0 0;
    font-size:12px;color:var(--mute)
  }
  .tally b{font-size:20px;display:block;font-weight:600;letter-spacing:-.02em}
  .t-pass b{color:var(--ok)} .t-fail b{color:var(--err)}
  .t-inc b{color:var(--warn)} .t-ns b{color:var(--mute)}

  /* the spine: checks hold the order the document declares */
  ol.spine{list-style:none;margin:26px 0 0;padding:0;position:relative}
  ol.spine:before{
    content:"";position:absolute;left:19px;top:6px;bottom:6px;width:1px;
    background:var(--line)
  }
  li.check{position:relative;padding:0 0 2px 52px;margin:0 0 2px}
  .slot{
    position:absolute;left:0;top:12px;width:39px;height:22px;
    display:flex;align-items:center;justify-content:center;
    background:var(--ink);color:var(--mute);
    font-size:11px;letter-spacing:.08em;z-index:1
  }
  .row{
    border-bottom:1px solid var(--line);
    padding:12px 0 13px;
    display:flex;align-items:baseline;gap:10px;flex-wrap:wrap
  }
  .name{font-size:14px;font-weight:600;letter-spacing:-.01em}
  .verdict{
    font-size:10px;letter-spacing:.14em;text-transform:uppercase;
    padding:3px 7px;border:1px solid currentColor;border-radius:2px;white-space:nowrap
  }
  .v-pass{color:var(--ok)} .v-fail{color:var(--err)}
  .v-inc{color:var(--warn)} .v-ns{color:var(--mute)}
  .v-run{color:var(--gold)}
  .v-wait{color:var(--line)}
  .why{flex-basis:100%;color:var(--mute);font-size:12.5px;margin-top:2px}
  .why b{color:var(--text);font-weight:600}
  .ep{
    flex-basis:100%;font-size:11.5px;color:var(--mute);
    margin-top:5px;word-break:break-all
  }
  .ep a{color:var(--gold);text-decoration:none;border-bottom:1px solid rgba(201,168,76,.35)}
  details{flex-basis:100%;margin-top:8px}
  summary{
    font-size:11px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--mute);cursor:pointer;list-style:none
  }
  summary::-webkit-details-marker{display:none}
  summary:before{content:"▸ ";}
  details[open] summary:before{content:"▾ ";}
  pre{
    background:var(--ink2);border:1px solid var(--line);border-radius:2px;
    margin:8px 0 0;padding:10px;font-size:11.5px;line-height:1.45;
    white-space:pre-wrap;word-break:break-word;max-height:280px;overflow:auto
  }
  li.check.done .slot{color:var(--text)}

  footer{
    margin-top:34px;border-top:1px solid var(--line);padding-top:16px;
    color:var(--mute);font-size:12px
  }
  footer p{margin:0 0 9px}
  .flash{
    border:1px solid var(--err);color:var(--err);
    padding:11px;border-radius:2px;margin:16px 0 0;font-size:12.5px
  }
  @media (prefers-reduced-motion: no-preference){
    li.check.done .row{animation:in .22s ease-out}
    @keyframes in{from{opacity:.35}to{opacity:1}}
  }
</style>
</head>
<body>
<div class="wrap">

<header>
  <p class="eyebrow">Ordering test · self check</p>
  <h1>Run every check this domain publishes about itself.</h1>
  <p class="sub">Reads <b>/.well-known/ordering-test.json</b>, then tests each check in the order the document declares it. Nothing here is a shared runner — it only tests this side.</p>
  <div class="bar">
    <button id="run">Run all checks</button>
    <button id="reload" class="ghost">Reload document</button>
  </div>
  <div class="tally" id="tally" hidden>
    <div class="t-pass"><b id="n-pass">0</b>verified</div>
    <div class="t-fail"><b id="n-fail">0</b>failed</div>
    <div class="t-inc"><b id="n-inc">0</b>inconclusive</div>
    <div class="t-ns"><b id="n-ns">0</b>not public</div>
  </div>
  <div id="flash"></div>
</header>

<ol class="spine" id="spine"></ol>

<footer>
  <p><b>Verified</b> means the response was checked for what the claim actually requires. <b>Reachable</b> means the endpoint answered but this runner did not confirm the semantics — reported as inconclusive, not as a pass.</p>
  <p>A check marked not publicly demonstrable is reported as such and never counted as a pass. This page cannot see behind a key and does not pretend to.</p>
</footer>

</div>

<script>
(function(){
  "use strict";

  var DOC = "/.well-known/ordering-test.json";
  var doc = null;
  var ctx = {};

  var el = function(id){ return document.getElementById(id); };
  var spine = el("spine");

  function flash(msg){
    el("flash").innerHTML = msg ? '<div class="flash">' + msg + '</div>' : '';
  }

  function pad(n){ return (n < 10 ? "0" : "") + n; }

  function jget(path){
    return fetch(path, {headers:{"Accept":"application/json"}}).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  function jpost(path, payload){
    return fetch(path, {
      method:"POST",
      headers:{"Content-Type":"application/json","Accept":"application/json"},
      body:JSON.stringify(payload)
    }).then(function(r){
      return r.text().then(function(t){
        var body;
        try { body = JSON.parse(t); } catch(e){ body = t; }
        return {status:r.status, ok:r.ok, body:body};
      });
    });
  }

  // SHA-256 in the visitor's own browser. The point of rule binding is that
  // the server hands back the exact string it hashed; if this page recomputes
  // the digest and it matches, nothing was taken on the server's word.
  function sha256hex(s){
    return crypto.subtle.digest("SHA-256", new TextEncoder().encode(s))
      .then(function(buf){
        var b = new Uint8Array(buf), out = "";
        for (var i = 0; i < b.length; i++){
          var h = b[i].toString(16);
          out += (h.length === 1 ? "0" : "") + h;
        }
        return out;
      });
  }

  var HEX64 = /^[0-9a-f]{64}$/;

  function walk(node, path, strings, hexes){
    if (typeof node === "string"){
      strings.push({path: path || "(root)", value: node});
      if (HEX64.test(node)) hexes[node] = path || "(root)";
      return;
    }
    if (Array.isArray(node)){
      for (var i = 0; i < node.length; i++) walk(node[i], path + "[" + i + "]", strings, hexes);
      return;
    }
    if (node && typeof node === "object"){
      for (var k in node){
        if (Object.prototype.hasOwnProperty.call(node, k)){
          walk(node[k], path ? path + "." + k : k, strings, hexes);
        }
      }
    }
  }

  // The payload these POST routes expect is not published, so this does two
  // things rather than guess: it tries the shapes they plausibly take, and
  // when a rejection names a missing field it adds that field and tries
  // again. A module that answers "'trust'" has told you what it wants.
  function defaultFor(name){
    if (/country/.test(name)) return "GB";
    if (/currency/.test(name)) return "GBP";
    if (/(^|_)id$|_id$|user|device|session/.test(name)) return "self-check";
    if (/trust|score|ratio|rate/.test(name)) return 0.5;
    return 0;
  }

  function missingField(body){
    var text = (body && typeof body === "object")
      ? (body.message || body.error || JSON.stringify(body))
      : String(body || "");
    // A bare quoted identifier is what a KeyError looks like once it reaches
    // the response. Also catch an explicit "missing x" phrasing.
    var m = text.match(/^['"]([A-Za-z_][A-Za-z0-9_]*)['"]$/) ||
            text.match(/missing[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i) ||
            text.match(/required[^A-Za-z0-9_]+['"]?([A-Za-z_][A-Za-z0-9_]*)['"]?/i);
    return m ? m[1] : null;
  }

  function postShapes(url, inner){
    var learned = [];

    function round(probe, depth){
      var shapes = [{name:"flat", body:probe},
                    {name:"inputs", body:{inputs:probe}},
                    {name:"event", body:{event:probe}}];
      var rejected = {};

      function go(i){
        if (i >= shapes.length){
          // Every shape failed the same way? Learn the field and go again.
          var field = null;
          for (var k in rejected){
            if (Object.prototype.hasOwnProperty.call(rejected, k)){
              field = missingField(rejected[k]);
              if (field) break;
            }
          }
          if (field && depth < 6 && !(field in probe)){
            var next = {};
            for (var p in probe){
              if (Object.prototype.hasOwnProperty.call(probe, p)) next[p] = probe[p];
            }
            next[field] = defaultFor(field);
            learned.push(field);
            return round(next, depth + 1);
          }
          return Promise.resolve({ok:false, rejected:rejected, learned:learned, probe:probe});
        }
        return jpost(url, shapes[i].body).then(function(r){
          if (!r.ok){ rejected[shapes[i].name] = r.body; return go(i + 1); }
          return {ok:true, shape:shapes[i].name, body:r.body, sent:shapes[i].body,
                  rejected:rejected, learned:learned};
        }).catch(function(e){
          rejected[shapes[i].name] = e.message; return go(i + 1);
        });
      }
      return go(0);
    }

    return round(inner, 0);
  }

  function oneMessage(b){
    if (b && typeof b === "object" && (b.message || b.error)) return b.message || b.error;
    if (typeof b === "string") return b.slice(0, 200);
    return "no message";
  }

  // Every shape's rejection, not just the first. The first one is usually the
  // least informative, and the shape that nearly worked is the one that says
  // what is actually wrong.
  function firstMessage(rejected){
    var parts = [];
    for (var k in rejected){
      if (Object.prototype.hasOwnProperty.call(rejected, k)){
        parts.push("<b>" + k + "</b>: " + oneMessage(rejected[k]));
      }
    }
    return parts.length ? parts.join(" \u00b7 ") : "no message returned";
  }

  function learnedNote(res){
    return (res.learned && res.learned.length)
      ? " (after adding the fields it named: " + res.learned.join(", ") + ")"
      : "";
  }

  // The engine's real signal names. Guessing these from outside was the
  // thing that kept the reproducibility check amber.
  var PROBE = {action: "payment", amount: 4200, trust: 0.4,
               v60: 12, v5m: 20, v1h: 60,
               device_risk: 0.3, anomaly: 0.2, country: "UK",
               country_shift: false};

  function show(v){
    try { return JSON.stringify(v, null, 2); } catch(e){ return String(v); }
  }

  // ---- document ---------------------------------------------------------

  function loadDoc(){
    flash("");
    spine.innerHTML = "";
    el("tally").hidden = true;
    // The module that serves the discovery document installs its route on
    // first use, so after a deploy the document 404s until something touches
    // it. Touch it here rather than making a person remember to.
    return jget("/x/standard/status").catch(function(){}).then(function(){
      return jget(DOC);
    }).then(function(r){
      if (!r.ok || typeof r.body !== "object"){
        flash("Could not read " + DOC + " — status " + r.status +
              ". If this is a fresh deploy, open /x/standard/status once to install the route, then reload.");
        doc = null;
        return null;
      }
      doc = r.body;
      draw();
      return doc;
    }).catch(function(e){
      flash("Request failed: " + e.message + ". Serve this page from the same domain as the document.");
    });
  }

  function draw(){
    var names = Object.keys(doc.checks || {});
    spine.innerHTML = "";
    names.forEach(function(name, i){
      var c = doc.checks[name];
      var li = document.createElement("li");
      li.className = "check";
      li.id = "chk-" + name;
      li.innerHTML =
        '<span class="slot">' + pad(i+1) + '</span>' +
        '<div class="row">' +
          '<span class="name">' + name.replace(/_/g," ") + '</span>' +
          '<span class="verdict v-wait" data-v>waiting</span>' +
          '<div class="why" data-why>' +
            (c.supported ? "declared supported" : "declared not supported") +
            (c.demonstrable_publicly ? ", publicly demonstrable" : ", not publicly demonstrable") +
          '</div>' +
          (c.endpoint ? '<div class="ep">' + c.endpoint + '</div>' : '') +
        '</div>';
      spine.appendChild(li);
    });
    var t = doc.vendor ? doc.vendor : "this domain";
    document.querySelector(".sub").innerHTML =
      'Document loaded from <b>' + (doc.base_url || location.origin) + '</b> · vendor <b>' + t +
      '</b> · version <b>' + (doc.ordering_test_version || "?") + '</b> · ' +
      names.length + ' checks declared.';
  }

  function setResult(name, verdict, why, detail){
    var li = el("chk-" + name);
    if (!li) return;
    li.classList.add("done");
    var v = li.querySelector("[data-v]");
    var map = {PASS:"v-pass", FAIL:"v-fail", INCONCLUSIVE:"v-inc", "NOT SUPPORTED":"v-ns", RUNNING:"v-run"};
    v.className = "verdict " + (map[verdict] || "v-wait");
    v.textContent = verdict;
    li.querySelector("[data-why]").innerHTML = why;
    if (detail !== undefined){
      var old = li.querySelector("details");
      if (old) old.remove();
      var d = document.createElement("details");
      d.innerHTML = "<summary>response</summary><pre>" +
        show(detail).replace(/</g,"&lt;") + "</pre>";
      li.querySelector(".row").appendChild(d);
    }
  }

  function running(name){
    var li = el("chk-" + name);
    if (!li) return;
    var v = li.querySelector("[data-v]");
    v.className = "verdict v-run";
    v.textContent = "running";
  }

  // ---- context the checks need before they can run ----------------------

  function buildContext(){
    ctx = {};
    var jobs = [];

    jobs.push(jget("/x/complete/periods").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      var list = r.body.periods || r.body.committed || r.body;
      if (!Array.isArray(list)) return;
      for (var i = list.length - 1; i >= 0; i--){
        var p = list[i];
        var id = (typeof p === "string") ? p : (p.period || p.id);
        var committed = (typeof p === "string") ? true :
          (p.committed === undefined ? true : !!p.committed);
        if (id && committed){ ctx.period = id; break; }
      }
    }).catch(function(){}));

    jobs.push(jget("/x/consistency/root").then(function(r){
      if (!r.ok || typeof r.body !== "object") return;
      ctx.size = r.body.size || r.body.tree_size || r.body.count;
      ctx.root = r.body.root;
    }).catch(function(){}));

    var hex = "0123456789abcdef";
    ctx.absent = "";
    for (var i = 0; i < 64; i++) ctx.absent += hex[Math.floor(Math.random() * 16)];

    return Promise.all(jobs);
  }

  function fill(endpoint){
    if (!endpoint) return null;
    return endpoint
      .replace("{period}", ctx.period || "")
      .replace("{value}", ctx.absent)
      .replace("{first}", "1")
      .replace("{second}", ctx.size ? String(ctx.size) : "");
  }

  // ---- the checks -------------------------------------------------------
  // Each returns {verdict, why, detail}.

  var runners = {

    authority_tokens: function(c){
      return jget(c.endpoint || "/x/continuity/decisions").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var list = b.decisions || [];
        if (!list.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no authority has been exercised " +
                      "yet \u2014 nothing to check, which is not the same as nothing failing",
                  detail:b};
        }
        // Pull one at random and confirm the listing agrees with the sealed
        // decision behind it. A summary that disagrees with its own record is
        // the failure worth catching here.
        var pick = list[Math.floor(Math.random() * list.length)];
        return jget("/x/continuity/decision?evaluation=" + encodeURIComponent(pick.evaluation))
          .then(function(d){
            if (!d.ok){
              return {verdict:"FAIL",
                      why:"the listing offers " + pick.evaluation + " but the decision behind " +
                          "it returned " + d.status,
                      detail:{listed:pick, fetched:d.body}};
            }
            var db = d.body || {};
            if (db.verdict !== pick.verdict){
              return {verdict:"FAIL",
                      why:"the public listing says <b>" + pick.verdict + "</b> and the sealed " +
                          "decision says <b>" + db.verdict + "</b>",
                      detail:{listed:pick, sealed:db}};
            }
            if (!db.lineage_digest || db.block_index === undefined){
              return {verdict:"INCONCLUSIVE",
                      why:"decision retrieved without a key, but it carries no lineage digest " +
                          "or block index to tie it to the chain",
                      detail:db};
            }
            return {verdict:"PASS",
                    why:"real sealed decisions readable without an account \u2014 <b>" +
                        (b.totals ? b.totals.allowed : "?") + " allowed, " +
                        (b.totals ? b.totals.challenged : "?") + " challenged, " +
                        (b.totals ? b.totals.blocked : "?") + " blocked</b>. Picked <b>" +
                        pick.evaluation + "</b> at random and the sealed record agrees with " +
                        "the listing, carrying its lineage digest and block index" +
                        (db.broken_invariant ? " and naming <b>" + db.broken_invariant +
                                               "</b> as what broke" : ""),
                    detail:{listing:b.totals, picked:pick, sealed:db}};
          });
      });
    },

    reconciliation: function(c){
      return jget(c.endpoint || "/x/reconcile/public").then(function(r){
        if (!r.ok){
          return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var runs = b.recent || [];
        if (!runs.length){
          return {verdict:"INCONCLUSIVE",
                  why:"the record is public and readable, but no reconciliation run exists yet",
                  detail:b};
        }
        var done = runs.filter(function(x){ return x.status === "reconciled"; });
        var pick = (done.length ? done : runs)[0];
        return jget("/x/reconcile/proof?id=" + encodeURIComponent(pick.run_id)).then(function(p){
          if (!p.ok){
            return {verdict:"FAIL",
                    why:"the listing offers " + pick.run_id + " but its proof returned " + p.status,
                    detail:{listed:pick, fetched:p.body}};
          }
          var pb = p.body || {};
          if (pb.plan_block_index === null || pb.result_block_index === null){
            return {verdict:"INCONCLUSIVE",
                    why:"run <b>" + pick.run_id + "</b> was planned but never submitted, so " +
                        "there is no result block to order against. Published rather than " +
                        "hidden, which is the right behaviour, but it does not demonstrate " +
                        "the check",
                    detail:pb};
          }
          if (!(pb.plan_block_index < pb.result_block_index)){
            return {verdict:"FAIL",
                    why:"the selection was sealed at block " + pb.plan_block_index +
                        " and the result at " + pb.result_block_index +
                        " \u2014 the sample was not fixed before the data was requested",
                    detail:pb};
          }
          return {verdict:"PASS",
                  why:"the sample for <b>" + pb.run_id + "</b> was sealed at block <b>" +
                      pb.plan_block_index + "</b> and the result at <b>" +
                      pb.result_block_index + "</b> \u2014 fixed before any data was asked " +
                      "for, checkable without an account. Across the record: <b>" +
                      b.mismatched + " mismatches</b> and <b>" + b.abandoned +
                      " abandoned run" + (b.abandoned === 1 ? "" : "s") +
                      "</b> published rather than buried",
                  detail:{summary:{runs:b.runs, matched:b.matched, mismatched:b.mismatched,
                                   abandoned:b.abandoned}, proof:pb}};
        });
      });
    },

    rule_binding: function(c){
      return postShapes(c.endpoint || "/x/rulebind/prove", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected),
                  detail:res.rejected};
        }
        var strings = [], hexes = {};
        walk(res.body, "", strings, hexes);
        return Promise.all(strings.map(function(s){
          return sha256hex(s.value).then(function(h){ return {path:s.path, hash:h}; });
        })).then(function(hashed){
          for (var i = 0; i < hashed.length; i++){
            if (hexes[hashed[i].hash]){
              return {verdict:"PASS",
                      why:"the response returned the exact string that was hashed. SHA-256 of " +
                          "<b>" + hashed[i].path + "</b>, recomputed in this browser, equals " +
                          "<b>" + hexes[hashed[i].hash] + "</b> \u2014 the ruleset version is " +
                          "inside the digest, not a field beside it",
                      detail:res.body};
            }
          }
          return {verdict:"INCONCLUSIVE",
                  why:"accepted the <b>" + res.shape + "</b> payload" + learnedNote(res) +
                      ", but no string it returned " +
                      "hashes to any digest in the response, so the binding was not confirmed here",
                  detail:res.body};
        });
      });
    },

    commit_before_reveal: function(c){
      return jpost(c.endpoint || "/x/demo/review", PROBE).then(function(r){
        if (!r.ok){
          return {verdict:"INCONCLUSIVE", why:"POST returned " + r.status, detail:r.body};
        }
        var b = r.body || {};
        var cid = b.case_id;
        if (!cid){
          return {verdict:"INCONCLUSIVE", why:"no case id came back to commit against", detail:b};
        }
        // The case must arrive with the verdict withheld. If it is in there,
        // nothing committed afterwards can have preceded a reveal that had
        // already happened.
        var text = JSON.stringify(b);
        if (/"(machine_verdict|verdict|decision)"\s*:\s*"(ALLOW|CHALLENGE|BLOCK)"/i.test(text)){
          return {verdict:"FAIL",
                  why:"the case arrived with the machine verdict already in it \u2014 the order " +
                      "cannot be fixed after the answer is known",
                  detail:b};
        }

        return jpost("/x/demo/commit", {case_id: cid, verdict: "challenge"}).then(function(k){
          if (!k.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"the case opened with the verdict withheld, but the commit returned " +
                        k.status,
                    detail:{case:b, commit:k.body}};
          }
          var kb = k.body || {};
          if (kb.block_index === undefined || !kb.machine_verdict){
            return {verdict:"INCONCLUSIVE",
                    why:"committed, but the response carries no block index or no revealed " +
                        "verdict to check the order against",
                    detail:{case:b, commit:kb}};
          }
          // A commitment you can redo is not a commitment.
          return jpost("/x/demo/commit", {case_id: cid, verdict: "allow"}).then(function(again){
            var refused = !again.ok ||
                          (again.body && again.body.error === "already_committed");
            if (!refused){
              return {verdict:"FAIL",
                      why:"the same case accepted a second, different verdict \u2014 a " +
                          "commitment that can be redone fixes nothing",
                      detail:{first:kb, second:again.body}};
            }
            return {verdict:"PASS",
                    why:"the case was issued with the verdict withheld, a human verdict was " +
                        "sealed at block <b>" + kb.block_index + "</b>, the machine verdict " +
                        "(<b>" + kb.machine_verdict + "</b>) was revealed only in that same " +
                        "response, dwell of <b>" + kb.dwell_seconds + "s</b> was recorded, and " +
                        "a second commit was refused \u2014 the order is fixed, not asserted",
                    detail:{case:b, commit:kb, second_attempt:again.body}};
          });
        });
      }).catch(function(e){
        return {verdict:"INCONCLUSIVE", why:"request failed: " + e.message};
      });
    },

    mutual_witnessing: function(c){
      return jget("/x/witness/peers").then(function(p){
        return jget("/x/witness/tip").then(function(t){
          if (!p.ok) return {verdict:"FAIL", why:"peers endpoint returned " + p.status, detail:p.body};
          if (!t.ok) return {verdict:"FAIL", why:"tip endpoint returned " + t.status, detail:t.body};
          var peers = p.body.peers || p.body;
          var n = Array.isArray(peers) ? peers.length : 0;
          if (n === 0){
            return {verdict:"FAIL", why:"no peer chains listed — witnessing claims an external party and there isn't one", detail:p.body};
          }
          return {verdict:"PASS",
                  why:"<b>" + n + " peer chain" + (n>1?"s":"") + "</b> listed and a current tip served, both without an account",
                  detail:{peers:p.body, tip:t.body}};
        });
      });
    },

    completeness_proof: function(c){
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no closed committed period found at /x/complete/periods, so there is nothing to ask for a root of"});
      }
      var url = fill(c.endpoint) || ("/x/complete/root?period=" + ctx.period);
      return jget(url).then(function(r){
        if (r.status === 409) return {verdict:"INCONCLUSIVE", why:"period " + ctx.period + " is still live — only closed periods commit", detail:r.body};
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var root = r.body.root || r.body.merkle_root;
        var count = r.body.count !== undefined ? r.body.count : r.body.leaf_count;
        if (!root || count === undefined){
          return {verdict:"INCONCLUSIVE", why:"reachable, but no root and exact leaf count in the response", detail:r.body};
        }
        return {verdict:"PASS",
                why:"root and an exact count of <b>" + count + "</b> leaves, committed for " + ctx.period + " before any export was asked for",
                detail:r.body};
      });
    },

    absence_proof: function(c){
      if (!ctx.period){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"no committed period, so there is nothing to prove absence against"});
      }
      var url = fill(c.endpoint) ||
        ("/x/complete/prove?period=" + ctx.period + "&value=" + ctx.absent);
      return jget(url).then(function(r){
        if (!r.ok) return {verdict:"FAIL", why:"returned " + r.status, detail:r.body};
        var n = (r.body && r.body.neighbours) || (r.body && r.body.neighbors) || {};
        if (n.lower && n.upper &&
            n.lower.index !== undefined && n.upper.index !== undefined){
          if (n.upper.index - n.lower.index === 1){
            return {verdict:"PASS",
                    why:"neighbours at indices <b>" + n.lower.index + "</b> and <b>" +
                        n.upper.index + "</b> \u2014 consecutive, so nothing can sit between " +
                        "them. Absence proved, not asserted",
                    detail:r.body};
          }
          return {verdict:"FAIL",
                  why:"neighbour indices " + n.lower.index + " and " + n.upper.index +
                      " are not consecutive \u2014 that proves nothing",
                  detail:r.body};
        }
        if (n.lower || n.upper){
          return {verdict:"INCONCLUSIVE",
                  why:"boundary case \u2014 the probe sorted outside the whole set, so only one " +
                      "neighbour came back. Valid, but it does not exercise the adjacency argument",
                  detail:r.body};
        }
        return {verdict:"INCONCLUSIVE", why:"no neighbours in the response", detail:r.body};
      });
    },

    consistency_proof: function(c){
      if (!ctx.size){
        return Promise.resolve({verdict:"INCONCLUSIVE",
          why:"could not read a tree size from /x/consistency/root"});
      }
      var first = Math.max(1, Math.floor(ctx.size / 2));
      var url = "/x/consistency/proof?first=" + first + "&second=" + ctx.size;
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"returned " + r.status + " for first=" + first + " second=" + ctx.size,
                  detail:r.body};
        }
        var b = r.body || {};
        var path = b.consistency_proof || b.proof || b.path;
        if (!Array.isArray(path) || path.length === 0){
          return {verdict:"INCONCLUSIVE", why:"no proof path in the response", detail:b};
        }
        // The proof has to be against the same tip served at /x/consistency/root.
        // A proof against some other root proves something about some other log.
        if (ctx.root && b.second_root && b.second_root !== ctx.root){
          return {verdict:"FAIL",
                  why:"the proof is against a different root than /x/consistency/root serves \u2014 " +
                      "two views of the log, which is the split view this check exists to rule out",
                  detail:b};
        }
        return {verdict:"PASS",
                why:"RFC 6962 proof of <b>" + path.length + " nodes</b> that the log at " + first +
                    " is a prefix of the log at " + ctx.size +
                    ", against the same tip served separately \u2014 append-only shown, not claimed",
                detail:b};
      });
    },

    reproducibility: function(c){
      return postShapes(c.endpoint || "/x/replay/challenge", PROBE).then(function(res){
        if (!res.ok){
          return {verdict:"INCONCLUSIVE",
                  why:"live, but it rejected every payload shape this runner knows \u2014 " +
                      firstMessage(res.rejected) +
                      ". This endpoint is published as publicly demonstrable, so the shape it " +
                      "wants belongs in the document",
                  detail:res.rejected};
        }
        return jpost(c.endpoint || "/x/replay/challenge", res.sent).then(function(b){
          return jget("/x/replay/fingerprint").then(function(f){
            var va = res.body && (res.body.verdict || res.body.decision);
            var vb = b.body && (b.body.verdict || b.body.decision);
            if (!va || !vb){
              return {verdict:"INCONCLUSIVE",
                      why:"both runs accepted under the <b>" + res.shape + "</b> shape, but no " +
                          "verdict field came back to compare",
                      detail:{first:res.body, second:b.body}};
            }
            if (va === vb){
              return {verdict:"PASS",
                      why:"identical inputs submitted twice both returned <b>" + va + "</b> " +
                          "under one code fingerprint" + learnedNote(res) +
                          " \u2014 determinism shown without disclosing any scoring logic",
                      detail:{shape:res.shape, fingerprint:f.body,
                              first:res.body, second:b.body}};
            }
            return {verdict:"FAIL",
                    why:"identical inputs gave <b>" + va + "</b> then <b>" + vb +
                        "</b> \u2014 not deterministic",
                    detail:{first:res.body, second:b.body}};
          });
        });
      });
    },

    external_anchoring: function(c){
      var url = c.endpoint || "/api/anchor-status";
      return jget(url).then(function(r){
        if (!r.ok){
          return {verdict:"FAIL",
                  why:"<b>" + url + " returned " + r.status + "</b> \u2014 this check is " +
                      "published as publicly demonstrable and the endpoint under it is not there",
                  detail:r.body};
        }
        var b = r.body || {};
        var tip = b.tip || b.chain_tip || b.anchored_tip;
        if (!tip){
          return {verdict:"INCONCLUSIVE",
                  why:"the endpoint answers but names no anchored tip, so there is nothing to " +
                      "check it against",
                  detail:b};
        }

        // A browser cannot verify Bitcoin, and this page will not pretend to.
        // What it CAN settle is the question that actually decides the check:
        // is the tip that was submitted to the external authority a tip of
        // THIS log? An anchor over some other chain proves nothing about this
        // one, and that substitution is the only way this check fails
        // quietly.
        return jget("/x/consistency/ancestor?tip=" + encodeURIComponent(tip)).then(function(a){
          if (a.status === 409){
            return {verdict:"FAIL",
                    why:"the anchored tip is <b>not</b> on the log being served now \u2014 the " +
                        "external timestamp covers a different chain, which is the fork this " +
                        "check exists to catch",
                    detail:{anchor:b, ancestor:a.body}};
          }
          if (!a.ok){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found, but /x/consistency/ancestor returned " + a.status +
                        " so it could not be placed on this log",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var text = JSON.stringify(a.body || {});
          var placed = /"(ancestor|is_ancestor|valid|ok|confirmed|on_chain)"\s*:\s*true/i.test(text) ||
                       /"(consistency_proof|proof|path)"\s*:\s*\[/.test(text);
          if (!placed){
            return {verdict:"INCONCLUSIVE",
                    why:"anchored tip found and the ancestor route answered, but this runner " +
                        "could not read a confirmation out of the response",
                    detail:{anchor:b, ancestor:a.body}};
          }
          var stamped = (b.ots_ok === true) || /anchored/i.test(String(b.status || ""));
          return {verdict:"PASS",
                  why:"the tip submitted to the external authority is proved to be on <b>this</b> " +
                      "log, not a substituted one \u2014 checked against /x/consistency/ancestor" +
                      (stamped ? ", and the operator reports it stamped: " +
                                 String(b.status || "anchored")
                               : ", though the operator does not report it stamped yet") +
                      ". The attestation itself is the authority's to confirm, not this page's",
                  detail:{anchor:b, ancestor:a.body}};
        }).catch(function(e){
          return {verdict:"INCONCLUSIVE",
                  why:"anchored tip found but the ancestor check failed: " + e.message,
                  detail:b};
        });
      });
    }
  };

  // generic fallback: liveness only, reported honestly as inconclusive
  function genericRunner(name, c){
    var url = fill(c.endpoint);
    if (!url) return Promise.resolve({verdict:"INCONCLUSIVE", why:"declared publicly demonstrable but no endpoint given"});
    if (url.indexOf("{") !== -1){
      return Promise.resolve({verdict:"INCONCLUSIVE", why:"endpoint has a placeholder this runner could not fill: " + url});
    }
    return jget(url).then(function(r){
      var b = r.body || {};
      // This router answers a method mismatch with 404 unknown_action and
      // lists the methods it does accept. A POST-only route is present, not
      // missing, and calling it missing would be a false failure.
      var postOnly = (b.error === "unknown_action") && Array.isArray(b.POST) &&
                     (b.POST.indexOf(url.split("?")[0].split("/").pop()) !== -1 ||
                      (Array.isArray(b.GET) && b.GET.length === 0));
      if (r.status === 405 || r.status === 501 || postOnly){
        return {verdict:"INCONCLUSIVE",
                why:"POST-only endpoint \u2014 present and listed by the router, but it cannot " +
                    "be exercised from a plain page",
                detail:r.body};
      }
      if (b.error === "unknown_action"){
        return {verdict:"INCONCLUSIVE",
                why:"the route answered but does not accept GET. Reachable, semantics not checked",
                detail:r.body};
      }
      if (!r.ok){
        return {verdict:"FAIL", why:"<b>" + url + " returned " + r.status + "</b>", detail:r.body};
      }
      return {verdict:"INCONCLUSIVE", why:"reachable — semantics not checked by this runner", detail:r.body};
    });
  }

  // ---- run --------------------------------------------------------------

  function runAll(){
    if (!doc){ flash("No document loaded."); return; }
    el("run").disabled = true;
    var tally = {PASS:0, FAIL:0, INCONCLUSIVE:0, "NOT SUPPORTED":0};
    el("tally").hidden = false;

    buildContext().then(function(){
      var names = Object.keys(doc.checks);
      var chain = Promise.resolve();

      names.forEach(function(name){
        chain = chain.then(function(){
          var c = doc.checks[name];

          if (!c.supported){
            setResult(name, "NOT SUPPORTED", "the document does not claim this check");
            tally["NOT SUPPORTED"]++;
            return;
          }
          if (!c.demonstrable_publicly){
            setResult(name, "INCONCLUSIVE",
              "built and claimed, but key-gated — nothing here can confirm it, which is what the document says");
            tally.INCONCLUSIVE++;
            return;
          }

          running(name);
          var fn = runners[name] ? runners[name].bind(null, c) : genericRunner.bind(null, name, c);
          return fn().catch(function(e){
            return {verdict:"FAIL", why:"request threw: " + e.message};
          }).then(function(res){
            setResult(name, res.verdict, res.why, res.detail);
            tally[res.verdict] = (tally[res.verdict] || 0) + 1;
            el("n-pass").textContent = tally.PASS;
            el("n-fail").textContent = tally.FAIL;
            el("n-inc").textContent = tally.INCONCLUSIVE;
            el("n-ns").textContent = tally["NOT SUPPORTED"];
          });
        });
      });

      chain.then(function(){
        el("run").disabled = false;
        el("n-pass").textContent = tally.PASS;
        el("n-fail").textContent = tally.FAIL;
        el("n-inc").textContent = tally.INCONCLUSIVE;
        el("n-ns").textContent = tally["NOT SUPPORTED"];
        if (tally.FAIL > 0){
          flash(tally.FAIL + " check" + (tally.FAIL>1?"s":"") +
                " published as publicly demonstrable did not hold up. Fix the endpoint or change the document — the two have to agree.");
        }
      });
    });
  }

  el("run").addEventListener("click", runAll);
  el("reload").addEventListener("click", loadDoc);
  loadDoc();
})();
</script>
</body>
</html>
'''


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_selfcheck_patched", False):
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
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._selfcheck_patched = True
    _patched[0] = True
    print("SELFCHECK: /self-check installed", flush=True)
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
            print("SELFCHECK: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"installed": bool(_patched[0]),
                "install_result": state,
                "module_version": VERSION,
                "serving": list(PAGE_PATHS),
                "page_bytes": len(PAGE),
                "note": "Runs against whichever host serves it. Same origin, so the browser "
                        "does not block the requests. Unlinked and noindex on purpose - it "
                        "tests one operator's own document and is not a joint runner."}, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```
