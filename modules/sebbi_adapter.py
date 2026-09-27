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
