"""
modules/public_proof_adapter.py  v1.0.0
The public proof log: legacy systems send sebbi.pro the SHA-256 of a state
change, and get back a receipt proving that hash is in an append-only log.

  * An RFC 6962 Merkle tree (the Certificate Transparency construction):
        leaf hash  = SHA-256(0x00 || entry)      entry = the 32-byte state hash
        node hash  = SHA-256(0x01 || left || right)
    so any receipt can be checked by anyone, with any RFC 6962 verifier,
    without trusting this server.
  * Receipts come back straight away: leaf index, tree size, root and the
    inclusion (audit) path.
  * Tree heads are sealed into the sebbi.pro chain on a schedule (every 60s or
    every 1,000 leaves, whichever comes first). That chain is walkable at
    /x/walk and its tip is timestamped in Bitcoin with OpenTimestamps by the
    existing anchor, so a leaf becomes Bitcoin-anchored once a confirmed
    anchored tip is at or after the block that sealed its tree head.
  * Hash-only. No payloads, labels or customer data are sent or stored.
  * Idempotent: the client sends its own id with each hash, so a retry after a
    lost response returns the original leaf instead of adding a duplicate.

Routes (clean /p/ prefix, armed by /x/public_proof_adapter/status):

    POST /p/submit        {"items":[{"hash":"<64 hex>","cid":"<client id>"}]}
                          or {"hash":"<64 hex>"}      needs an API key
    GET  /p/receipt?leaf=N        receipt against the sealed tree head
    GET  /p/proof?leaf=N&size=M   inclusion path at tree size M
    GET  /p/consistency?first=M&second=N   RFC 6962 consistency proof
    GET  /p/sth                   latest sealed tree head + current size
    GET  /p/find?hash=<64 hex>    leaf indexes holding that entry hash
    GET  /p/                      what this log is and how to check it

The API key goes in the X-Sebbi-Key header (or "key" in the body). Set
ADAPTER_OPEN=1 in Railway to accept submissions without a key (not advised).

Loading: the live server loads modules through modules/router.py and calls
handle(). ALIASES and register(MODULE_MAP) are also provided so a loader that
maps modules by name (e.g. brain.py) can pick it up under "adapter",
"sidecar" or "anchor".

Assumes one server process (as on Railway today). If a second process ever
writes the same database, appends detect it and reload before continuing.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse

VERSION = "1.0.0"
ALIASES = ["adapter", "sidecar", "anchor"]
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "sth"), ("GET", "proof"),
          ("GET", "receipt"), ("GET", "consistency"), ("GET", "find")}

KEY = "public-proof-adapter"
SITE = "https://sebbi.pro"
MAX_ITEMS = 500
MAX_BODY = 262144
CHECKPOINT_SECONDS = max(10, int(os.environ.get("ADAPTER_CHECKPOINT_SECONDS", "60") or 60))
CHECKPOINT_EVERY = max(1, int(os.environ.get("ADAPTER_CHECKPOINT_EVERY", "1000") or 1000))
OPEN = os.environ.get("ADAPTER_OPEN", "0") == "1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SPEC = ("RFC 6962 Merkle tree, SHA-256. leaf_hash = SHA256(0x00 || entry); "
        "node = SHA256(0x01 || left || right); entry = the 32 raw bytes of the submitted hash.")

_ctx = {}
_ready = False
_patched = False
_loaded = False
_leaves = []            # leaf hashes (bytes), index = leaf index
_cache = {}             # (start, size) -> hash, for complete power-of-two subtrees
_tree_lock = threading.Lock()
_cp_lock = threading.Lock()
_loop_started = False


# ---------------------------------------------------------------- RFC 6962

def _h(b):
    return hashlib.sha256(b).digest()


def _leaf_hash(entry):
    return _h(b"\x00" + entry)


def _node(left, right):
    return _h(b"\x01" + left + right)


def _split(n):
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(start, n):
    """Merkle Tree Hash of leaves[start:start+n]."""
    if n == 0:
        return _h(b"")
    if n == 1:
        return _leaves[start]
    full = n >= 16 and (n & (n - 1)) == 0
    if full:
        hit = _cache.get((start, n))
        if hit is not None:
            return hit
    k = _split(n)
    out = _node(_mth(start, k), _mth(start + k, n - k))
    if full:
        _cache[(start, n)] = out
    return out


def _path(m, start, n):
    """Audit path for leaf m within leaves[start:start+n]."""
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, start, k) + [_mth(start + k, n - k)]
    return _path(m - k, start + k, n - k) + [_mth(start, k)]


def _subproof(m, start, n, b):
    if m == n:
        return [] if b else [_mth(start, n)]
    k = _split(n)
    if m <= k:
        return _subproof(m, start, k, b) + [_mth(start + k, n - k)]
    return _subproof(m - k, start + k, n - k, False) + [_mth(start, k)]


def _consistency(m, n):
    if m <= 0 or m >= n:
        return []
    return _subproof(m, 0, n, True)


# ---------------------------------------------------------------- storage

def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS ppa_leaf(idx INTEGER PRIMARY KEY,entry_hash TEXT NOT NULL,"
                  "leaf_hash TEXT NOT NULL,client TEXT,cid TEXT,ts REAL,UNIQUE(client,cid))")
        c.execute("CREATE INDEX IF NOT EXISTS ppa_leaf_entry ON ppa_leaf(entry_hash)")
        c.execute("CREATE TABLE IF NOT EXISTS ppa_sth(tree_size INTEGER PRIMARY KEY,root TEXT NOT NULL,"
                  "ts REAL,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _reload_locked(c):
    """Rebuild the in-memory tree from the database. Caller holds _ctx['lock']."""
    rows = c.execute("SELECT idx,leaf_hash FROM ppa_leaf ORDER BY idx").fetchall()
    fresh = []
    for i, (idx, lh) in enumerate(rows):
        if idx != i:
            raise RuntimeError("leaf index gap at %d" % i)
        fresh.append(bytes.fromhex(lh))
    _cache.clear()
    _leaves[:] = fresh


def _load():
    global _loaded
    if _loaded:
        return
    with _tree_lock:
        if _loaded:
            return
        with _ctx["lock"]:
            _reload_locked(_ctx["conn"])
        _loaded = True


def _seal(kind, detail, extra):
    ev = {"user_id": "ppa:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "public-proof-adapter", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "adapter_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _sth_rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _latest_sth():
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth ORDER BY tree_size DESC LIMIT 1")
    return _sth_dict(r[0]) if r else None


def _covering_sth(idx):
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth WHERE tree_size>? "
                  "ORDER BY tree_size ASC LIMIT 1", (idx,))
    return _sth_dict(r[0]) if r else None


def _sth_dict(r):
    return {"tree_size": r[0], "root": r[1],
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2] or 0)),
            "audit_hash": r[3], "block_index": r[4],
            "walk": SITE + "/x/walk/block?index=%s" % r[4] if r[4] is not None else None,
            "ts": r[2] or 0}


# ---------------------------------------------------------------- appends and checkpoints

def _append(client, items):
    """items: list of (entry_hex, cid or None). Returns list of (idx, entry_hex, replayed, error)."""
    for attempt in range(3):
        out = []
        with _ctx["lock"]:
            c = _ctx["conn"]
            top = c.execute("SELECT COALESCE(MAX(idx),-1) FROM ppa_leaf").fetchone()[0]
            if top + 1 != len(_leaves):
                _reload_locked(c)
            start_len = len(_leaves)
            try:
                for eh, cid in items:
                    if cid:
                        row = c.execute("SELECT idx,entry_hash FROM ppa_leaf WHERE client=? AND cid=?",
                                        (client, cid)).fetchone()
                        if row:
                            if row[1] != eh:
                                out.append((None, eh, False, "cid_reused_for_a_different_hash"))
                            else:
                                out.append((row[0], eh, True, None))
                            continue
                    idx = len(_leaves)
                    lh = _leaf_hash(bytes.fromhex(eh))
                    c.execute("INSERT INTO ppa_leaf(idx,entry_hash,leaf_hash,client,cid,ts) VALUES(?,?,?,?,?,?)",
                              (idx, eh, lh.hex(), client, cid or None, time.time()))
                    _leaves.append(lh)
                    out.append((idx, eh, False, None))
                c.commit()
                return out
            except sqlite3.IntegrityError:
                c.rollback()
                del _leaves[start_len:]
                _reload_locked(c)
            except Exception:
                c.rollback()
                del _leaves[start_len:]
                raise
    raise RuntimeError("could not append after retries")


def _checkpoint(force=False):
    """Seal the current tree head into the chain if it is due. Never runs twice at once."""
    if "conn" not in _ctx or not _cp_lock.acquire(blocking=False):
        return None
    try:
        _load()
        n = len(_leaves)
        last = _latest_sth()
        last_size = last["tree_size"] if last else 0
        if n == 0 or n == last_size:
            return last
        due = force or (n - last_size) >= CHECKPOINT_EVERY or \
            (time.time() - (last["ts"] if last else 0)) >= CHECKPOINT_SECONDS
        if not due:
            return last
        root = _mth(0, n).hex()
        ah, blk = _seal("tree_head", "size=%d;root=%s" % (n, root),
                        {"tree_size": n, "root": root, "prev_tree_size": last_size,
                         "log": "sebbi public proof log", "spec": "RFC6962-SHA256"})
        with _ctx["lock"]:
            _ctx["conn"].execute("INSERT OR IGNORE INTO ppa_sth(tree_size,root,ts,audit_hash,block_index) "
                                 "VALUES(?,?,?,?,?)", (n, root, time.time(), ah, blk))
            _ctx["conn"].commit()
        return _latest_sth()
    finally:
        _cp_lock.release()


def _loop():
    while True:
        time.sleep(10)
        try:
            _checkpoint()
        except Exception as e:
            print("public_proof_adapter checkpoint: " + str(e)[:160], flush=True)


def _start_loop():
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, name="ppa-checkpoint", daemon=True).start()


# ---------------------------------------------------------------- receipts

def _anchoring_note(cp):
    if not cp:
        return ("pending: this leaf is covered by the next tree head, sealed into the chain within about "
                "%d seconds. Fetch /p/receipt?leaf=N again after that." % CHECKPOINT_SECONDS)
    return ("tree head sealed in chain block %s. The chain tip is timestamped in Bitcoin via OpenTimestamps; "
            "once a confirmed anchored tip is at or after that block, this leaf is Bitcoin-anchored. "
            "Check: %s/x/ots/latest_confirmed" % (cp["block_index"], SITE))


def _receipt(idx, size=None):
    _load()
    n = len(_leaves)
    if idx < 0 or idx >= n:
        return None
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT entry_hash FROM ppa_leaf WHERE idx=?", (idx,)).fetchone()
    cp = _covering_sth(idx) if size is None else None
    tsize = size if size is not None else (cp["tree_size"] if cp else n)
    tsize = max(idx + 1, min(tsize, n))
    root = _mth(0, tsize).hex()
    rec = {"log": "sebbi.pro public proof log", "spec": SPEC,
           "entry_hash": row[0] if row else None, "leaf_index": idx,
           "leaf_hash": _leaves[idx].hex(), "tree_size": tsize, "root": root,
           "audit_path": [p.hex() for p in _path(idx, 0, tsize)],
           "checkpoint": None, "anchoring": _anchoring_note(cp)}
    if cp:
        c2 = dict(cp)
        c2.pop("ts", None)
        c2["root_matches"] = (cp["root"] == root)
        rec["checkpoint"] = c2
    return rec


# ---------------------------------------------------------------- commands

def _client_for(key):
    key = str(key or "").strip()
    if key:
        try:
            with _ctx["lock"]:
                row = _ctx["conn"].execute("SELECT active FROM api_keys WHERE key=?", (key,)).fetchone()
        except Exception:
            row = None
        if row and row[0] in (1, None):
            return "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "open" if OPEN else None


def c_submit(q, body, key):
    client = _client_for(key)
    if not client:
        return {"error": "api_key_required",
                "message": "Send your sebbi.pro API key in the X-Sebbi-Key header."}, 401
    raw = body.get("items")
    if raw is None and body.get("hashes") is not None:
        raw = [{"hash": h} for h in body.get("hashes") or []]
    if raw is None and body.get("hash") is not None:
        raw = [{"hash": body.get("hash"), "cid": body.get("cid")}]
    if not isinstance(raw, list) or not raw:
        return {"error": "nothing_to_submit", "message": 'Send {"items":[{"hash":"<64 hex>","cid":"..."}]}'}, 400
    if len(raw) > MAX_ITEMS:
        return {"error": "too_many", "max_items": MAX_ITEMS}, 413
    items, bad = [], []
    for i, it in enumerate(raw):
        it = it if isinstance(it, dict) else {"hash": it}
        h = str(it.get("hash") or "").strip().lower()
        cid = str(it.get("cid") or "").strip() or None
        if not HEX64.match(h):
            bad.append({"position": i, "error": "hash must be 64 hex characters (SHA-256)"})
        elif cid and not CID_RE.match(cid):
            bad.append({"position": i, "error": "cid must be 1-80 letters, numbers, _ . : -"})
        else:
            items.append((h, cid))
    if bad:
        return {"error": "bad_items", "items": bad}, 400
    _load()
    placed = _append(client, items)
    n = len(_leaves)
    last = _latest_sth()
    if n - (last["tree_size"] if last else 0) >= CHECKPOINT_EVERY:
        threading.Thread(target=_checkpoint, daemon=True).start()
    receipts = []
    for (idx, eh, replayed, err), (_, cid) in zip(placed, items):
        if err:
            receipts.append({"cid": cid, "entry_hash": eh, "error": err})
            continue
        r = _receipt(idx, size=n)
        r["cid"] = cid
        r["replayed"] = replayed
        r["anchoring"] = _anchoring_note(None)
        receipts.append(r)
    return {"accepted": sum(1 for r in receipts if "error" not in r), "tree_size": n,
            "root": _mth(0, n).hex(), "receipts": receipts}, 200


def _int(q, name, default=None):
    try:
        return int(str(q.get(name, default)))
    except (TypeError, ValueError):
        return None


def c_receipt(q, body, key):
    idx = _int(q, "leaf")
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx)
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_proof(q, body, key):
    idx, size = _int(q, "leaf"), _int(q, "size", 0)
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx, size=size or len(_leaves))
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_consistency(q, body, key):
    _load()
    m, n = _int(q, "first"), _int(q, "second", len(_leaves))
    if m is None or n is None or m < 1 or m > n or n > len(_leaves):
        return {"error": "need 1 <= first <= second <= tree size", "tree_size": len(_leaves)}, 400
    return {"first": m, "second": n, "first_root": _mth(0, m).hex(), "second_root": _mth(0, n).hex(),
            "proof": [p.hex() for p in _consistency(m, n)], "spec": SPEC}, 200


def c_sth(q, body, key):
    _load()
    last = _latest_sth()
    if last:
        last.pop("ts", None)
    return {"tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "spec": SPEC}, 200


def c_find(q, body, key):
    h = str(q.get("hash") or "").strip().lower()
    if not HEX64.match(h):
        return {"error": "hash must be 64 hex characters"}, 400
    rows = _sth_rows("SELECT idx FROM ppa_leaf WHERE entry_hash=? ORDER BY idx LIMIT 50", (h,))
    return {"entry_hash": h, "leaf_indexes": [r[0] for r in rows]}, 200


def c_index(q, body, key):
    return {"log": "sebbi.pro public proof log", "version": VERSION, "spec": SPEC,
            "submit": "POST " + SITE + "/p/submit with X-Sebbi-Key",
            "check": ["GET " + SITE + "/p/receipt?leaf=N", "GET " + SITE + "/p/consistency?first=M&second=N",
                      "GET " + SITE + "/p/sth"],
            "hash_only": True}, 200


GETS = {"receipt": c_receipt, "proof": c_proof, "consistency": c_consistency, "sth": c_sth,
        "find": c_find, "": c_index}
POSTS = {"submit": c_submit}


# ---------------------------------------------------------------- transport

def _send(h, obj, code=200):
    body = json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(body)


def _run(h, method):
    u = urllib.parse.urlparse(h.path)
    name = u.path[3:].strip("/").lower()
    table = GETS if method == "GET" else POSTS
    if name not in table:
        return False
    if "conn" not in _ctx:
        _send(h, {"error": "not_armed", "message": "open /x/public_proof_adapter/status once"}, 503)
        return True
    _setup()
    q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
    body = {}
    if method == "POST":
        try:
            n = int(h.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n > MAX_BODY:
            _send(h, {"error": "body_too_large", "max_bytes": MAX_BODY}, 413)
            return True
        try:
            body = json.loads(h.rfile.read(n).decode("utf-8") or "{}") if n else {}
            if not isinstance(body, dict):
                body = {}
        except Exception:
            _send(h, {"error": "bad_json"}, 400)
            return True
    key = h.headers.get("X-Sebbi-Key") or body.get("key") or q.get("key")
    try:
        out, code = table[name](q, body, key)
    except Exception as e:
        out, code = {"error": "failed", "detail": str(e)[:160]}, 500
    _send(h, out, code)
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
        _setup()
        _load()
        _start_loop()
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_ppa_patched", False):
        _patched = True
        return True
    og, op, oo = cls.do_GET, getattr(cls, "do_POST", None), getattr(cls, "do_OPTIONS", None)

    def do_GET(self):
        if (self.path == "/p" or self.path.startswith("/p/")) and _run(self, "GET"):
            return
        return og(self)

    def do_POST(self):
        if self.path.startswith("/p/") and _run(self, "POST"):
            return
        return op(self) if op else None

    def do_OPTIONS(self):
        if self.path.startswith("/p/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Sebbi-Key")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        return oo(self) if oo else None

    cls.do_GET = do_GET
    if op:
        cls.do_POST = do_POST
    cls.do_OPTIONS = do_OPTIONS
    cls._ppa_patched = True
    _patched = True
    return True


def _flat(d):
    if not isinstance(d, dict):
        return {}
    return {k: (v[0] if isinstance(v, list) and v else v) for k, v in d.items()}


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    action = (action or "status").strip("/").lower()
    data = _flat(data)
    if "conn" in _ctx and action in POSTS and method == "POST":
        return POSTS[action](data, data, api_key or data.get("key"))
    if "conn" in _ctx and action in GETS and action not in ("",):
        return GETS[action](data, data, api_key)
    last = _latest_sth() if "conn" in _ctx else None
    if last:
        last.pop("ts", None)
    return {"module": "public_proof_adapter", "version": VERSION, "armed": armed,
            "aliases": ALIASES, "tree_size": len(_leaves), "latest_sealed_tree_head": last,
            "checkpoint_every_seconds": CHECKPOINT_SECONDS, "checkpoint_every_leaves": CHECKPOINT_EVERY,
            "open_submissions": OPEN, "spec": SPEC,
            "endpoints": ["POST /p/submit", "/p/receipt", "/p/proof", "/p/consistency", "/p/sth", "/p/find"]}, 200


def register(MODULE_MAP):
    """For name-based loaders: map this module under its own name and its aliases."""
    mod = sys.modules[__name__]
    for name in ["public_proof_adapter"] + ALIASES:
        MODULE_MAP.setdefault(name, mod)
    return MODULE_MAP
