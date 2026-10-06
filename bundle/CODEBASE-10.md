# Codebase — part 10 of 50

Contains:
- `modules/dossier.py`
- `modules/dsr.py`
- `modules/earnpage.py`


## `modules/dossier.py`

1206 lines, 60143 bytes

```python
"""
modules/dossier.py  v1.0.0  -  the machine-proof decision report

    Page:   https://sebbi.pro/dossier
    Arm:    https://sebbi.pro/x/dossier/status

WHAT IT IS
----------
Pick any sealed block and get one report with everything about it:

  the decision    the exact event and result as sealed, verdict, score, reasons
  who             the account that sent it (name, organisation, email, plan),
                  the end user it was about, their device, their history,
                  any authority they acted under, any human who reviewed it
  where           the IP address that sent the request, the full forwarded
                  chain, user agent, origin, referer, language, request id
  integrity       the block rehashed, linked both ways, the whole chain
                  re-verified from genesis to this block, a Merkle inclusion
                  proof, and the account's receipt sequence checked for gaps
  time            the heartbeat beacons either side (a floor and a ceiling),
                  the first Bitcoin anchor that covers it, confirmed or pending
  linked records  every later block that refers to this one
  limits          what the report does not prove, printed inside it

Issue it and the report's own digest is sealed into the chain, so the
document you hand over is itself on the record.

HOW "WHERE" IS CAPTURED WITHOUT TOUCHING server.py
--------------------------------------------------
On arming, the server's seal() is wrapped. Every time a block is sealed, the
wrapper looks up the request being served on that thread and records its IP,
forwarded chain, user agent and headers against the new block. A block sealed
by a background job (heartbeat, anchoring) is recorded as exactly that.

PERSONAL DATA STAYS OFF THE CHAIN
---------------------------------
The chain is append-only, so an IP address written into it could never be
erased. So the raw context lives in its own table, and only its SHA-256
fingerprint is sealed: every few minutes the fingerprints of new context
rows are rolled into a Merkle root and that root is sealed as one block.
Each report carries the inclusion proof, so the context is tamper-evident
without being permanent. After DOSSIER_RETENTION_DAYS (default 730) the raw
fields are deleted and the fingerprint stays - the report then says so.

END-USER CONTEXT
----------------
The IP captured is the machine that called the API - usually the customer's
server. A customer who wants the end user's address in the report attaches it
straight after sealing with POST /x/dossier/attach. It is stored the same way,
off the chain with its fingerprint sealed, and the report shows how long after
sealing it was attached.

ACCESS
------
A report holds personal data, so it is never public. An API key can pull
reports for blocks it sealed. The owner's admin token (from /admin) can pull
any block. Anyone can verify an issued report's digest, and anyone can run the
integrity half of a report, which carries no personal data.

ROUTES
------
  GET  /x/dossier/status            public  - arm and report what is captured
  GET  /x/dossier/spec              public  - this, as JSON
  GET  /x/dossier/verify?block=N    public  - integrity and time only, no personal data
  GET  /x/dossier/check?digest=     public  - was a report with this digest issued?
  GET  /x/dossier/report?block=N    keyed   - full report, own blocks (or receipt=<hash>)
  POST /x/dossier/issue             keyed   - seal the report digest into the chain
  POST /x/dossier/attach            keyed   - attach end-user context to a block you sealed
  GET  /dossier                     page    - look up, read, print, issue
  GET  /dossier/data?block=N        key or admin token - full report
  POST /dossier/issue               key or admin token - seal it
"""

import hashlib
import json
import os
import sys
import threading
import time
import traceback
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _UK = ZoneInfo("Europe/London")
except Exception:
    _UK = None

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "verify"), ("GET", "check")}

ROOT_EVERY = int(os.environ.get("DOSSIER_ROOT_SECONDS", "300"))
RETENTION_DAYS = int(os.environ.get("DOSSIER_RETENTION_DAYS", "730"))
ATTACH_WINDOW = int(os.environ.get("DOSSIER_ATTACH_SECONDS", "900"))
MAX_VERIFY_ROWS = 300000
MAX_MERKLE_ROWS = 200000

HEADERS_KEPT = [
    "X-Forwarded-For", "X-Real-IP", "Forwarded", "User-Agent", "Origin", "Referer",
    "Accept-Language", "Host", "Content-Length", "Content-Type",
    "X-Request-Id", "X-Railway-Request-Id", "CF-Connecting-IP", "CF-IPCountry",
    "Sec-CH-UA", "Sec-CH-UA-Platform",
]
END_USER_FIELDS = ["ip", "user_agent", "session_id", "actor", "actor_role",
                   "location", "channel", "note"]

_state = {"ready": False, "wrapped": False, "page": False, "root_thread": False,
          "started": None, "captured": 0, "last_root": None, "last_error": None}
_lock = threading.Lock()
_srv_ref = [None]
_orig_seal = [None]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _srv():
    if _srv_ref[0] is not None:
        return _srv_ref[0]
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    _srv_ref[0] = m
    return m


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except Exception:
        return None


def _uk(ts):
    try:
        d = datetime.fromtimestamp(float(ts), _UK or timezone.utc)
        return d.strftime("%d %b %Y, %H:%M:%S %Z")
    except Exception:
        return None


def _mask_key(k):
    if not k:
        return None
    return (k[:8] + "…" + k[-4:]) if len(k) > 14 else "…"


def _setup(conn, lock):
    with lock:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS dossier_context("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT, block_index INTEGER, audit_hash TEXT,"
                  "kind TEXT, source TEXT, ip TEXT, context_json TEXT, digest TEXT,"
                  "captured_at REAL, root_block INTEGER, expired INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_dctx_block ON dossier_context(block_index)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_dctx_root ON dossier_context(root_block)")
        c.execute("CREATE TABLE IF NOT EXISTS dossier_root("
                  "block_index INTEGER PRIMARY KEY, audit_hash TEXT, root TEXT,"
                  "first_id INTEGER, last_id INTEGER, count INTEGER, sealed_at REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS dossier_issued("
                  "digest TEXT PRIMARY KEY, subject_block INTEGER, issued_block INTEGER,"
                  "issued_hash TEXT, issued_at REAL, requester TEXT, report_json TEXT)")
        conn.commit()


# ---------------------------------------------------------------------
# capture: wrap seal() and read the request off the stack
# ---------------------------------------------------------------------

def _find_request():
    f = sys._getframe(2)
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(s, "headers") and hasattr(s, "client_address") \
                and hasattr(s, "command"):
            return s
        f = f.f_back
    return None


def _request_context(h):
    hdr = {}
    for name in HEADERS_KEPT:
        try:
            v = h.headers.get(name)
        except Exception:
            v = None
        if v:
            hdr[name.lower()] = str(v)[:400]
    xff = hdr.get("x-forwarded-for", "")
    chain = [p.strip() for p in xff.split(",") if p.strip()] if xff else []
    try:
        socket_ip = str(h.client_address[0])
    except Exception:
        socket_ip = None
    ip = hdr.get("cf-connecting-ip") or (chain[0] if chain else None) or hdr.get("x-real-ip") or socket_ip
    path = str(getattr(h, "path", ""))[:300]
    try:
        bearer = _srv().get_bearer(h) or ""
    except Exception:
        bearer = ""
    return {
        "ip": ip,
        "forwarded_chain": chain,
        "socket_peer": socket_ip,
        "method": str(getattr(h, "command", "")),
        "path": path.split("?")[0],
        "query_present": "?" in path,
        "headers": hdr,
        "credential_fingerprint": _sha(bearer)[:16] if bearer else None,
        "thread": threading.current_thread().name,
    }


def _record(conn, lock, block_index, audit_hash, kind, source, ip, ctx_obj, ts):
    body = {"block_index": block_index, "audit_hash": audit_hash, "kind": kind,
            "source": source, "captured_at": ts, "context": ctx_obj}
    digest = _sha(_canon(body))
    with lock:
        conn.execute("INSERT INTO dossier_context(block_index,audit_hash,kind,source,ip,"
                     "context_json,digest,captured_at) VALUES(?,?,?,?,?,?,?,?)",
                     (block_index, audit_hash, kind, source, ip, _canon(ctx_obj), digest, ts))
        conn.commit()
    _state["captured"] += 1
    return digest


_queue = []
_q_lock = threading.Lock()
_q_event = threading.Event()


def _flush():
    """Write queued contexts in one transaction. Safe to call from anywhere
    that does not already hold the server's database lock."""
    with _q_lock:
        items = _queue[:]
        del _queue[:]
    if not items:
        return 0
    s = _srv()
    rows = []
    for idx, h, kind, source, ip, ctx_obj, ts in items:
        body = {"block_index": idx, "audit_hash": h, "kind": kind,
                "source": source, "captured_at": ts, "context": ctx_obj}
        rows.append((idx, h, kind, source, ip, _canon(ctx_obj), _sha(_canon(body)), ts))
    with s._db_lock:
        s._conn.executemany("INSERT INTO dossier_context(block_index,audit_hash,kind,source,ip,"
                            "context_json,digest,captured_at) VALUES(?,?,?,?,?,?,?,?)", rows)
        s._conn.commit()
    _state["captured"] += len(rows)
    return len(rows)


def _start_writer():
    with _lock:
        if _state.get("writer"):
            return
        _state["writer"] = True

    def loop():
        while True:
            _q_event.wait(5)
            _q_event.clear()
            time.sleep(0.25)  # gather a burst into one commit
            try:
                _flush()
            except Exception as e:
                _state["last_error"] = "writer: %s" % e

    threading.Thread(target=loop, name="dossier-writer", daemon=True).start()


def _wrap_seal():
    s = _srv()
    if s is None or not hasattr(s, "seal"):
        return False
    if getattr(s.seal, "_dossier_wrapped", False):
        _state["wrapped"] = True
        return True
    original = s.seal
    _orig_seal[0] = original

    def seal(*a, **kw):
        out = original(*a, **kw)
        try:
            h = idx = None
            if isinstance(out, (tuple, list)):
                h = out[0] if len(out) > 0 else None
                idx = out[1] if len(out) > 1 else None
            elif isinstance(out, str):
                h = out
            req = _find_request()
            now = time.time()
            if req is not None:
                ctx_obj = _request_context(req)
                item = (idx, h, "request", "http", ctx_obj.get("ip"), ctx_obj, now)
            else:
                ctx_obj = {"thread": threading.current_thread().name,
                           "note": "sealed by a background job on the server, not by an HTTP request"}
                item = (idx, h, "internal", ctx_obj["thread"], None, ctx_obj, now)
            # written by the writer thread, so sealing never waits on an extra commit
            with _q_lock:
                _queue.append(item)
            _q_event.set()
        except Exception as e:
            _state["last_error"] = "capture: %s" % e
        return out

    seal._dossier_wrapped = True
    seal.__wrapped__ = original
    s.seal = seal
    _state["wrapped"] = True
    _state["started"] = _state["started"] or time.time()
    try:
        with s._db_lock:
            s._conn.execute("INSERT OR IGNORE INTO config(k,v) VALUES('dossier_capture_started',?)",
                            (str(time.time()),))
            s._conn.commit()
    except Exception:
        pass
    return True


def _capture_started(conn, lock):
    try:
        with lock:
            r = conn.execute("SELECT v FROM config WHERE k='dossier_capture_started'").fetchone()
        return float(r[0]) if r else None
    except Exception:
        return None


# ---------------------------------------------------------------------
# context roots: seal the fingerprints, keep the data off the chain
# ---------------------------------------------------------------------

def _merkle_mod():
    try:
        from modules import consistency as C
    except Exception:
        import consistency as C
    return C


def _context_root_once():
    s = _srv()
    conn, lock = s._conn, s._db_lock
    _flush()
    with lock:
        rows = conn.execute("SELECT id,digest FROM dossier_context WHERE root_block IS NULL "
                            "ORDER BY id ASC LIMIT 5000").fetchall()
    if not rows:
        return None
    C = _merkle_mod()
    leaves = [r[1] for r in rows]
    root = C._mth(leaves).hex()
    ts = time.time()
    event = {"user_id": "dossier", "action": "context_root", "amount": 0, "country": "UK",
             "device_id": "dossier", "anomaly": 0, "device_risk": 0}
    result = {"decision": "NOTARISED", "score": 0, "version": VERSION, "timestamp": ts,
              "context_root": root, "first_id": rows[0][0], "last_id": rows[-1][0],
              "count": len(rows),
              "note": "Merkle root of request-context fingerprints. The personal data stays "
                      "off the chain; this root makes it tamper-evident."}
    seal_fn = _orig_seal[0] or s.seal
    out = seal_fn(event, result, ts)
    h, idx = out[0], out[1]
    with lock:
        conn.execute("UPDATE dossier_context SET root_block=? WHERE id>=? AND id<=? AND root_block IS NULL",
                     (idx, rows[0][0], rows[-1][0]))
        conn.execute("INSERT OR REPLACE INTO dossier_root VALUES(?,?,?,?,?,?,?)",
                     (idx, h, root, rows[0][0], rows[-1][0], len(rows), ts))
        conn.commit()
    _state["last_root"] = {"block_index": idx, "count": len(rows), "at": _iso(ts)}
    return idx


def _expire_once():
    if RETENTION_DAYS <= 0:
        return 0
    s = _srv()
    cut = time.time() - RETENTION_DAYS * 86400
    with s._db_lock:
        n = s._conn.execute("UPDATE dossier_context SET ip=NULL, context_json=NULL, expired=1 "
                            "WHERE expired=0 AND captured_at<? AND root_block IS NOT NULL", (cut,)).rowcount
        s._conn.commit()
    return n


def _start_root_thread():
    with _lock:
        if _state["root_thread"]:
            return
        _state["root_thread"] = True

    def loop():
        while True:
            time.sleep(ROOT_EVERY)
            try:
                _context_root_once()
                _expire_once()
            except Exception as e:
                _state["last_error"] = "root: %s" % e

    threading.Thread(target=loop, name="dossier-root", daemon=True).start()


# ---------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------

def _row(conn, lock, block=None, receipt=None):
    q = "SELECT id,ts,user_id,event_json,result_json,prev_hash,audit_hash,api_key,key_seq FROM audit_log "
    with lock:
        if block is not None:
            return conn.execute(q + "WHERE id=?", (int(block),)).fetchone()
        return conn.execute(q + "WHERE audit_hash=?", (str(receipt),)).fetchone()


def _loads(t):
    try:
        return json.loads(t) if t else {}
    except Exception:
        return {"unparsed": str(t)[:2000]}


def _rehash(s, row):
    p = {"prev_hash": row[5], "ts": row[1], "event": json.loads(row[3]), "result": json.loads(row[4])}
    return s.sha(p)


def _integrity(s, row):
    conn, lock = s._conn, s._db_lock
    out = {}
    try:
        out["block_hash_recomputes"] = _rehash(s, row) == row[6]
    except Exception as e:
        out["block_hash_recomputes"] = False
        out["rehash_error"] = str(e)[:200]
    with lock:
        prev = conn.execute("SELECT id,audit_hash FROM audit_log WHERE id<? ORDER BY id DESC LIMIT 1",
                            (row[0],)).fetchone()
        nxt = conn.execute("SELECT id,audit_hash,prev_hash FROM audit_log WHERE id>? ORDER BY id ASC LIMIT 1",
                           (row[0],)).fetchone()
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    out["previous_block"] = {"index": prev[0], "hash": prev[1]} if prev else {"index": None, "hash": "GENESIS"}
    out["links_to_previous"] = (row[5] == (prev[1] if prev else "GENESIS"))
    if nxt:
        out["next_block"] = {"index": nxt[0], "hash": nxt[1], "links_back_to_this": nxt[2] == row[6]}
    else:
        out["next_block"] = None
        out["note_next"] = "This is the newest block. Nothing has been sealed after it yet."

    # the whole chain, genesis to here, rehashed
    with lock:
        n_upto = conn.execute("SELECT COUNT(*) FROM audit_log WHERE id<=?", (row[0],)).fetchone()[0]
    if n_upto <= MAX_VERIFY_ROWS:
        with lock:
            rows = conn.execute("SELECT event_json,result_json,prev_hash,audit_hash,ts FROM audit_log "
                                "WHERE id<=? ORDER BY id ASC", (row[0],)).fetchall()
        p = "GENESIS"
        broken = None
        for i, r in enumerate(rows):
            try:
                ok = s.sha({"prev_hash": r[2], "ts": r[4], "event": json.loads(r[0]),
                            "result": json.loads(r[1])}) == r[3] and r[2] == p
            except Exception:
                ok = False
            if not ok:
                broken = i
                break
            p = r[3]
        out["chain_verified_genesis_to_here"] = broken is None
        out["blocks_rehashed"] = len(rows) if broken is None else broken
        if broken is not None:
            out["chain_broken_at_position"] = broken
    else:
        out["chain_verified_genesis_to_here"] = None
        out["note_chain"] = "Chain too long to rehash inside one report; use /api/verify-chain."

    # Merkle inclusion against the current tree
    if total <= MAX_MERKLE_ROWS:
        try:
            C = _merkle_mod()
            with lock:
                leaves = [r[0] for r in conn.execute("SELECT audit_hash FROM audit_log ORDER BY id ASC").fetchall()]
            li = leaves.index(row[6])
            out["merkle_inclusion"] = {
                "algorithm": "RFC 6962 Merkle Tree Hash over audit hashes in write order",
                "tree_size": len(leaves), "leaf_index": li,
                "root": C._mth(leaves).hex(),
                "audit_path": [x.hex() for x in C._inclusion(li, leaves)],
                "check": "https://sebbi.pro/x/consistency/root",
            }
        except Exception as e:
            out["merkle_inclusion"] = {"error": str(e)[:200]}

    # receipt sequence for the sealing account
    if row[7]:
        with lock:
            seqs = [r[0] for r in conn.execute(
                "SELECT key_seq FROM audit_log WHERE api_key=? AND key_seq IS NOT NULL ORDER BY key_seq ASC",
                (row[7],)).fetchall()]
        gaps = []
        for a, b in zip(seqs, seqs[1:]):
            if b != a + 1:
                gaps.append([a, b])
        out["receipt_sequence"] = {
            "this_receipt": row[8], "account_receipts": len(seqs),
            "first": seqs[0] if seqs else None, "last": seqs[-1] if seqs else None,
            "gaps": gaps[:50], "gapless": not gaps,
            "meaning": "Every sealed record for this account carries the next number. A gap "
                       "would mean a missing record; gapless means none is missing.",
        }
    return out


def _time(s, row):
    conn, lock = s._conn, s._db_lock
    out = {"sealed_at_utc": _iso(row[1]), "sealed_at_uk": _uk(row[1]), "unix": row[1]}
    try:
        with lock:
            fl = conn.execute("SELECT source,beacon_round,value,fetched_at,chain_rowid FROM heartbeat_tick "
                              "WHERE chain_rowid IS NOT NULL AND chain_rowid<=? ORDER BY chain_rowid DESC LIMIT 1",
                              (row[0],)).fetchone()
            ce = conn.execute("SELECT source,beacon_round,value,fetched_at,chain_rowid FROM heartbeat_tick "
                              "WHERE chain_rowid IS NOT NULL AND chain_rowid>? ORDER BY chain_rowid ASC LIMIT 1",
                              (row[0],)).fetchone()

        def beat(r, role):
            if not r:
                return None
            return {"role": role, "source": r[0], "round": r[1], "value": r[2],
                    "beacon_fetched_utc": _iso(r[3]), "sealed_at_block": r[4]}
        out["heartbeat"] = {
            "floor": beat(fl, "not created before this public beacon existed"),
            "ceiling": beat(ce, "created before this beacon was sealed"),
            "meaning": "A public random beacon cannot be known before it is published. The beat "
                       "sealed before this block is a floor on when it was created; the next "
                       "beat is a ceiling.",
        }
        if fl and ce:
            out["heartbeat"]["window_seconds"] = round(ce[3] - fl[3], 1)
    except Exception:
        out["heartbeat"] = {"note": "no heartbeat beacons recorded on this deployment"}

    # first OpenTimestamps anchor whose tip is at or after this block
    try:
        try:
            from modules import ots as O
        except Exception:
            import ots as O
        anchors = O._read_index()
        best = None
        with lock:
            for a in anchors:
                tip = a.get("tip")
                if not tip or not a.get("ots"):
                    continue
                r = conn.execute("SELECT id FROM audit_log WHERE audit_hash=?", (tip,)).fetchone()
                if r and r[0] >= row[0]:
                    if best is None or r[0] < best[0]:
                        best = (r[0], a)
        if best:
            sid = O._stamp_id(best[1].get("ots_file"))
            state = "unknown"
            heights = []
            raw, _p, _e = O._proof_bytes(sid) if sid else (None, None, None)
            if raw:
                d = O._describe(raw)
                state, heights = d.get("state"), d.get("bitcoin_block_heights", [])
            out["bitcoin_anchor"] = {
                "anchored_tip_block": best[0], "anchored_tip": best[1].get("tip"),
                "submitted_utc": _iso(best[1].get("ts")), "state": state,
                "bitcoin_block_heights": heights,
                "proof": ("https://sebbi.pro/x/ots/proof?ts=%s" % sid) if sid else None,
                "meaning": "This block sits before the anchored tip, so once the proof is "
                           "confirmed in Bitcoin it cannot have been created after that block.",
            }
        else:
            out["bitcoin_anchor"] = {"state": "not_yet",
                                     "note": "No anchor covers this block yet. Anchors run hourly."}
    except Exception as e:
        out["bitcoin_anchor"] = {"state": "unavailable", "note": str(e)[:160]}
    return out


def _who(s, row, ev, res):
    conn, lock = s._conn, s._db_lock
    out = {}
    if row[7]:
        with lock:
            a = conn.execute("SELECT name,org,org_type,email,phone,product,plan_type,is_paid,created,active "
                             "FROM api_keys WHERE key=?", (row[7],)).fetchone()
        if a:
            out["account"] = {
                "name": a[0], "organisation": a[1], "organisation_type": a[2], "email": a[3],
                "phone": a[4], "product": a[5], "plan": a[6], "paid": bool(a[7]),
                "account_created_utc": _iso(a[8]), "active": bool(a[9]),
                "key": _mask_key(row[7]), "key_fingerprint": _sha(row[7])[:16],
            }
    else:
        out["account"] = None
        out["account_note"] = "Sealed without an API key - a public or internal route."
    uid = row[2]
    out["subject_user"] = uid
    out["device"] = ev.get("device_id")
    if uid:
        with lock:
            hist = conn.execute("SELECT id,ts,result_json FROM audit_log WHERE user_id=? AND id<>? "
                                "ORDER BY id DESC LIMIT 400", (uid, row[0])).fetchall()
        counts = {}
        recent = []
        prev_dec = None
        for h in hist:
            r = _loads(h[2])
            d = r.get("decision", "?")
            counts[d] = counts.get(d, 0) + 1
            if len(recent) < 10:
                recent.append({"block": h[0], "utc": _iso(h[1]), "verdict": d, "score": r.get("score")})
            if prev_dec is None and h[0] < row[0]:
                prev_dec = {"block": h[0], "utc": _iso(h[1]), "verdict": d, "score": r.get("score"),
                            "trust_after": r.get("trust"),
                            "seconds_before_this": round(row[1] - h[1], 1)}
        out["subject_history"] = {
            "other_records": len(hist), "verdict_counts": counts,
            "previous_decision": prev_dec, "most_recent": recent,
            "trust_after_this_decision": res.get("trust"),
        }
    if res.get("authority") or ev.get("authority_token"):
        out["authority"] = dict(res.get("authority") or {})
        out["authority"]["token_presented"] = bool(ev.get("authority_token"))
    # humans: a resolved challenge, an oversight or capture case on this block
    humans = []
    with lock:
        ch = conn.execute("SELECT id,ts,result_json FROM audit_log WHERE id>? AND event_json LIKE ? LIMIT 5",
                          (row[0], '%"original_block": "' + row[6] + '"%')).fetchall()
    for c in ch:
        humans.append({"kind": "challenge resolved by a human", "block": c[0], "utc": _iso(c[1]),
                       "seconds_after_decision": round(c[1] - row[1], 1)})
    for table, col, fields in (
            ("oversight_cases", "material_hash",
             "case_id,reviewer,machine_verdict,reviewer_verdict,agreed,dwell,opened,committed,status"),
            ("capture_cases", "output_hash",
             "case_id,operator_fp,machine_verdict,human_verdict,agreed,dwell,opened,sealed,note")):
        try:
            with lock:
                rs = conn.execute("SELECT %s FROM %s WHERE %s=? LIMIT 5" % (fields, table, col),
                                  (row[6],)).fetchall()
            for r in rs:
                humans.append(dict(zip(fields.split(","), r), kind=table.replace("_", " ")))
        except Exception:
            pass
    out["human_review"] = humans or None
    return out


def _where(s, row):
    conn, lock = s._conn, s._db_lock
    started = _capture_started(conn, lock)
    with lock:
        rows = conn.execute("SELECT id,kind,source,ip,context_json,digest,captured_at,root_block,expired "
                            "FROM dossier_context WHERE block_index=? ORDER BY id ASC", (row[0],)).fetchall()
    if not rows:
        why = ("This block was sealed before request capture began on %s." % _uk(started)) \
            if started and row[1] < started else \
            "No request context was recorded for this block."
        return {"captured": False, "why": why}
    C = _merkle_mod()
    items = []
    for r in rows:
        ctx_obj = _loads(r[4]) if r[4] else None
        item = {"kind": r[1], "source": r[2], "captured_utc": _iso(r[6]),
                "context_fingerprint": r[5]}
        if r[1] == "end_user":
            item["attached_seconds_after_sealing"] = round(r[6] - row[1], 2)
        if r[8]:
            item["expired"] = True
            item["note"] = "Raw details deleted under the %d-day retention rule; the sealed fingerprint remains." % RETENTION_DAYS
        elif ctx_obj is not None:
            item["context"] = ctx_obj
            body = {"block_index": row[0], "audit_hash": row[6], "kind": r[1], "source": r[2],
                    "captured_at": r[6], "context": ctx_obj}
            item["fingerprint_recomputes"] = _sha(_canon(body)) == r[5]
        if r[7]:
            with lock:
                rr = conn.execute("SELECT root,first_id,last_id,audit_hash FROM dossier_root WHERE block_index=?",
                                  (r[7],)).fetchone()
                leaves = [x[0] for x in conn.execute(
                    "SELECT digest FROM dossier_context WHERE id>=? AND id<=? AND root_block=? ORDER BY id ASC",
                    (rr[1], rr[2], r[7])).fetchall()] if rr else []
            if rr and r[5] in leaves:
                li = leaves.index(r[5])
                item["sealed_in"] = {
                    "root_block": r[7], "root_block_hash": rr[3], "root": rr[0],
                    "leaf_index": li, "leaves": len(leaves),
                    "audit_path": [x.hex() for x in C._inclusion(li, leaves)],
                    "root_recomputes": C._mth(leaves).hex() == rr[0],
                }
        else:
            item["sealed_in"] = {"pending": True,
                                 "note": "Fingerprint joins the next context root, sealed every %d seconds." % ROOT_EVERY}
        items.append(item)
    first = next((i for i in items if i["kind"] == "request"), items[0])
    ctx0 = first.get("context") or {}
    summary = {
        "captured": True,
        "sent_by": "an HTTP request" if first["kind"] == "request" else "a background job on the server",
        "ip": ctx0.get("ip"),
        "forwarded_chain": ctx0.get("forwarded_chain"),
        "user_agent": (ctx0.get("headers") or {}).get("user-agent"),
        "method": ctx0.get("method"), "path": ctx0.get("path"),
        "origin": (ctx0.get("headers") or {}).get("origin"),
        "referer": (ctx0.get("headers") or {}).get("referer"),
        "country_header": (ctx0.get("headers") or {}).get("cf-ipcountry"),
        "request_id": (ctx0.get("headers") or {}).get("x-railway-request-id") or
                      (ctx0.get("headers") or {}).get("x-request-id"),
        "records": items,
    }
    eu = [i for i in items if i["kind"] == "end_user" and i.get("context")]
    if eu:
        summary["end_user"] = eu[-1]["context"]
    return summary


def _linked(s, row):
    with s._db_lock:
        rs = s._conn.execute("SELECT id,ts,user_id,result_json FROM audit_log WHERE id>? AND "
                             "(event_json LIKE ? OR result_json LIKE ?) ORDER BY id ASC LIMIT 25",
                             (row[0], "%" + row[6] + "%", "%" + row[6] + "%")).fetchall()
    return [{"block": r[0], "utc": _iso(r[1]), "by": r[2],
             "decision": _loads(r[3]).get("decision")} for r in rs] or None


LIMITS = [
    "It proves this record existed in this form when sealed and has not changed since. It does not prove the decision was right.",
    "The IP address is the machine that called the API, usually the operator's own server. The end user's address appears only if the operator attached it.",
    "Request details can be forged by whoever controls the calling machine. They record what arrived, not who was really behind it.",
    "Request details are captured for blocks sealed after capture began; older blocks are reported as not captured rather than guessed.",
    "The Bitcoin anchor fixes a ceiling on time only once its proof is confirmed. A pending proof is shown as pending.",
    "Account details are what the account holder gave at signup. They are not identity-verified by this report.",
]


def build(block=None, receipt=None, full=True):
    s = _srv()
    _setup(s._conn, s._db_lock)
    _flush()
    row = _row(s._conn, s._db_lock, block, receipt)
    if not row:
        return None
    ev, res = _loads(row[3]), _loads(row[4])
    kind = "decision" if res.get("decision") in ("ALLOW", "CHALLENGE", "BLOCK") else "record"
    rep = {
        "report": "sebbi.pro machine-proof report",
        "report_version": "1.0",
        "generated_utc": _iso(time.time()),
        "generated_by": "sebbi.pro dossier v" + VERSION + " / platform v" + str(getattr(s, "VERSION", "?")),
        "subject": {
            "block_index": row[0], "audit_hash": row[6], "kind": kind,
            "verdict": res.get("decision"), "score": res.get("score"),
            "reasons": res.get("reasons"), "action": ev.get("action"),
            "amount": ev.get("amount"), "country": ev.get("country"),
            "sealed_at_utc": _iso(row[1]), "sealed_at_uk": _uk(row[1]),
            "signal_pack": res.get("signal_pack"), "jurisdiction": res.get("jurisdiction"),
        },
        "integrity": _integrity(s, row),
        "time": _time(s, row),
    }
    if full:
        rep["decision"] = {"event": ev, "result": res}
        rep["who"] = _who(s, row, ev, res)
        rep["where"] = _where(s, row)
        rep["linked_records"] = _linked(s, row)
    else:
        rep["personal_data"] = "Withheld. This is the public half of the report - integrity and time only."
    rep["limits"] = LIMITS
    rep["check_it_yourself"] = {
        "whole_chain": "https://sebbi.pro/api/verify-chain",
        "merkle_root": "https://sebbi.pro/x/consistency/root",
        "anchors": "https://sebbi.pro/x/ots/status",
        "this_report_public_half": "https://sebbi.pro/x/dossier/verify?block=%d" % row[0],
        "check_an_issued_report": "https://sebbi.pro/x/dossier/check?digest=<digest>",
    }
    rep["digest"] = _sha(_canon({k: v for k, v in rep.items() if k not in ("generated_utc", "digest")}))
    return rep


def _owner_of(block, receipt):
    s = _srv()
    r = _row(s._conn, s._db_lock, block, receipt)
    return (r[7] if r else None), r


def _issue(rep, requester):
    s = _srv()
    ts = time.time()
    event = {"user_id": "dossier", "action": "report_issued", "amount": 0, "country": "UK",
             "device_id": "dossier", "anomaly": 0, "device_risk": 0}
    result = {"decision": "NOTARISED", "score": 0, "version": VERSION, "timestamp": ts,
              "report_digest": rep["digest"], "subject_block": rep["subject"]["block_index"],
              "subject_hash": rep["subject"]["audit_hash"],
              "note": "A machine-proof report was issued. Its digest is sealed; its contents are not."}
    out = s.seal(event, result, ts)
    with s._db_lock:
        s._conn.execute("INSERT OR IGNORE INTO dossier_issued VALUES(?,?,?,?,?,?,?)",
                        (rep["digest"], rep["subject"]["block_index"], out[1], out[0], ts,
                         requester, _canon(rep)))
        s._conn.commit()
    return {"issued": True, "digest": rep["digest"], "issued_block": out[1], "issued_hash": out[0],
            "issued_utc": _iso(ts), "check": "https://sebbi.pro/x/dossier/check?digest=" + rep["digest"]}


def _parse_target(data):
    data = data or {}
    b = data.get("block") or data.get("index")
    r = data.get("receipt") or data.get("hash")
    try:
        b = int(b) if b not in (None, "") else None
    except (TypeError, ValueError):
        b = None
    r = str(r).strip()[:64] if r else None
    return b, r


# ---------------------------------------------------------------------
# page + direct routes (admin token or API key)
# ---------------------------------------------------------------------

def _auth(h, owner_key):
    s = _srv()
    tok = s.get_bearer(h)
    if not tok:
        return False, None
    try:
        if s.check_admin(h):
            return True, "admin"
    except Exception:
        pass
    if owner_key and tok == owner_key and s.get_key(tok):
        return True, "key:" + _sha(tok)[:16]
    return False, None


def _send(h, payload, status=200, ctype="application/json"):
    body = payload if isinstance(payload, bytes) else (
        json.dumps(payload, indent=2, default=str).encode("utf-8") if ctype == "application/json"
        else payload.encode("utf-8"))
    h.send_response(status)
    h.send_header("Content-Type", ctype + ("; charset=utf-8" if "charset" not in ctype else ""))
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.send_header("X-Robots-Tag", "noindex")
    h.end_headers()
    h.wfile.write(body)


def _qs(h):
    from urllib.parse import urlparse, parse_qs
    return {k: v[0] for k, v in parse_qs(urlparse(h.path).query).items()}


def _find_handler_class():
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is not None:
        return H
    f = sys._getframe()
    while f is not None:
        o = f.f_locals.get("self")
        if o is not None and hasattr(type(o), "do_GET") and hasattr(o, "wfile"):
            return type(o)
        f = f.f_back
    return None


def _install_page():
    if _state["page"]:
        return True
    H = _find_handler_class()
    if H is None:
        return False
    if getattr(H, "_dossier_patched", False):
        _state["page"] = True
        return True
    orig_get, orig_post = H.do_GET, H.do_POST

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/dossier":
            return _send(self, PAGE, 200, "text/html")
        if p == "/dossier/data":
            try:
                b, r = _parse_target(_qs(self))
                owner, row = _owner_of(b, r)
                if not row:
                    return _send(self, {"error": "no_such_block"}, 404)
                ok, who = _auth(self, owner)
                if not ok:
                    return _send(self, {"error": "not_authorised",
                                        "message": "Use the API key that sealed this block, or your admin token."}, 401)
                return _send(self, build(row[0]))
            except Exception as e:
                traceback.print_exc()
                return _send(self, {"error": "report_failed", "detail": str(e)[:200]}, 500)
        return orig_get(self)

    def do_POST(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/dossier/issue":
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                data = json.loads(self.rfile.read(min(n, 4096)) or b"{}") if n else {}
                b, r = _parse_target(data)
                owner, row = _owner_of(b, r)
                if not row:
                    return _send(self, {"error": "no_such_block"}, 404)
                ok, who = _auth(self, owner)
                if not ok:
                    return _send(self, {"error": "not_authorised"}, 401)
                rep = build(row[0])
                out = _issue(rep, who)
                out["report"] = rep
                return _send(self, out)
            except Exception as e:
                traceback.print_exc()
                return _send(self, {"error": "issue_failed", "detail": str(e)[:200]}, 500)
        return orig_post(self)

    H.do_GET = do_GET
    H.do_POST = do_POST
    H._dossier_patched = True
    _state["page"] = True
    return True


def arm(ctx=None):
    s = _srv()
    if s is None:
        return False
    _setup(s._conn, s._db_lock)
    _start_writer()
    _wrap_seal()
    # modules armed after this one in the same pass (heartbeat, witness...)
    # keep the ctx they were armed with; hand them the capturing seal
    if isinstance(ctx, dict) and "seal" in ctx and _state["wrapped"]:
        ctx["seal"] = s.seal
    _install_page()
    _start_root_thread()
    _state["ready"] = True
    return True


# ---------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------

def _status():
    s = _srv()
    conn, lock = s._conn, s._db_lock
    _flush()
    with lock:
        n = conn.execute("SELECT COUNT(*) FROM dossier_context").fetchone()[0]
        pend = conn.execute("SELECT COUNT(*) FROM dossier_context WHERE root_block IS NULL").fetchone()[0]
        roots = conn.execute("SELECT COUNT(*) FROM dossier_root").fetchone()[0]
        issued = conn.execute("SELECT COUNT(*) FROM dossier_issued").fetchone()[0]
    return {"module": "dossier", "version": VERSION,
            "armed": _state["wrapped"] and _state["page"],
            "capture_on": _state["wrapped"], "page": "https://sebbi.pro/dossier",
            "capture_started_uk": _uk(_capture_started(conn, lock)),
            "contexts_recorded": n, "awaiting_next_root": pend, "context_roots_sealed": roots,
            "reports_issued": issued, "root_every_seconds": ROOT_EVERY,
            "retention_days": RETENTION_DAYS, "last_root": _state["last_root"],
            "last_error": _state["last_error"]}


def _spec():
    return {"module": "dossier", "version": VERSION,
            "what": "One report with everything about a sealed block: the decision, who sent it, "
                    "the IP and request it came from, the integrity proofs and the time proofs.",
            "routes": {
                "status": "GET https://sebbi.pro/x/dossier/status - public",
                "verify": "GET https://sebbi.pro/x/dossier/verify?block=N - public, no personal data",
                "check": "GET https://sebbi.pro/x/dossier/check?digest=D - public",
                "report": "GET https://sebbi.pro/x/dossier/report?block=N - API key, own blocks",
                "issue": "POST https://sebbi.pro/x/dossier/issue {block} - API key, own blocks",
                "attach": "POST https://sebbi.pro/x/dossier/attach {block, ip, user_agent, session_id, actor, ...} - API key, within %d seconds of sealing" % ATTACH_WINDOW,
                "page": "https://sebbi.pro/dossier",
            },
            "privacy": "Request details are kept off the chain. Only their fingerprints are sealed, "
                       "rolled into a Merkle root every %d seconds. Raw details are deleted after %d days."
                       % (ROOT_EVERY, RETENTION_DAYS),
            "limits": LIMITS}


def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    s = _srv()
    if action in ("", "status"):
        return _status(), 200
    if action == "spec":
        return _spec(), 200
    if action == "check" and method == "GET":
        d = str((data or {}).get("digest", "")).strip()[:64]
        with s._db_lock:
            r = s._conn.execute("SELECT subject_block,issued_block,issued_hash,issued_at FROM dossier_issued "
                                "WHERE digest=?", (d,)).fetchone()
        if not r:
            return {"issued": False, "digest": d,
                    "meaning": "No report with this digest was issued by sebbi.pro."}, 404
        return {"issued": True, "digest": d, "subject_block": r[0], "issued_block": r[1],
                "issued_hash": r[2], "issued_utc": _iso(r[3]),
                "meaning": "A report with exactly this digest was issued and its digest sealed "
                           "at the block shown. Change one character of the report and the digest changes."}, 200
    b, r = _parse_target(data)
    if action == "verify" and method == "GET":
        if b is None and not r:
            return {"error": "give block=N or receipt=<hash>"}, 400
        rep = build(b, r, full=False)
        return (rep, 200) if rep else ({"error": "no_such_block"}, 404)
    if action in ("report", "issue", "attach"):
        if b is None and not r:
            return {"error": "give block=N or receipt=<hash>"}, 400
        owner, row = _owner_of(b, r)
        if not row:
            return {"error": "no_such_block"}, 404
        if not api_key or owner != api_key:
            return {"error": "not_your_block",
                    "message": "An API key can only open reports for blocks it sealed."}, 403
        if action == "report" and method == "GET":
            return build(row[0]), 200
        if action == "issue" and method == "POST":
            rep = build(row[0])
            out = _issue(rep, "key:" + _sha(api_key)[:16])
            out["report"] = rep
            return out, 200
        if action == "attach" and method == "POST":
            age = time.time() - row[1]
            if age > ATTACH_WINDOW:
                return {"error": "too_late",
                        "message": "End-user context must be attached within %d seconds of sealing, "
                                   "so it cannot be added after the fact to fit a story." % ATTACH_WINDOW}, 409
            ctx_obj = {k: str(data.get(k))[:300] for k in END_USER_FIELDS if data.get(k) not in (None, "")}
            if not ctx_obj:
                return {"error": "nothing_to_attach", "fields": END_USER_FIELDS}, 400
            dg = _record(s._conn, s._db_lock, row[0], row[6], "end_user", "operator", ctx_obj.get("ip"),
                         ctx_obj, time.time())
            return {"attached": True, "block": row[0], "fingerprint": dg,
                    "seconds_after_sealing": round(age, 2),
                    "sealed": "fingerprint joins the next context root within %d seconds" % ROOT_EVERY}, 200
    return {"error": "unknown_action", "spec": "https://sebbi.pro/x/dossier/spec"}, 404


# ---------------------------------------------------------------------
# the page
# ---------------------------------------------------------------------

PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Machine-proof report · sebbi.pro</title>
<meta name="robots" content="noindex">
<meta name="description" content="Everything about one sealed AI decision in one report: the decision, who sent it, where from, and the proofs that it has not changed.">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--ink3:#16203a;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--amb:#f0c674;--mut:rgba(255,255,255,.64);--line:rgba(201,168,76,.2);
--sans:'IBM Plex Sans',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:#fff;font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased;padding-bottom:env(safe-area-inset-bottom,0)}
.wrap{max-width:900px;margin:0 auto;padding:0 16px}
.top{border-bottom:1px solid var(--line);padding:14px 0}
.top .wrap{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}
.brand{font-family:var(--mono);font-size:13px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
.top a.l{font-family:var(--mono);font-size:12px;color:var(--mut);text-decoration:none;margin-left:12px}
.hero{padding:40px 0 18px}.kick{font-family:var(--mono);font-size:12px;color:var(--gold);letter-spacing:.07em;margin-bottom:10px}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(32px,6vw,52px);line-height:1.05;margin-bottom:12px}
h1 em{color:var(--gold);font-style:italic}
.hero p{color:var(--mut);max-width:60ch;font-size:16px}
.card{background:var(--ink2);border:1px solid var(--line);border-radius:8px;padding:18px;margin:18px 0}
label{display:block;font-family:var(--mono);font-size:11.5px;color:var(--gold);letter-spacing:.05em;margin:10px 0 5px}
input{width:100%;background:var(--ink);border:1px solid var(--line);border-radius:5px;color:#fff;padding:11px 12px;font-family:var(--mono);font-size:14px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:600px){.row{grid-template-columns:1fr}}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.btn{background:var(--gold);color:var(--ink);border:0;border-radius:5px;padding:11px 16px;font-family:var(--mono);font-size:13px;font-weight:500;cursor:pointer}
.btn.g{background:transparent;color:var(--gold);border:1px solid var(--gold)}.btn[disabled]{opacity:.55}
.hint{font-size:13px;color:var(--mut);margin-top:10px}
.msg{font-family:var(--mono);font-size:13px;margin-top:12px;min-height:1em}.msg.err{color:var(--err)}.msg.ok{color:var(--ok)}
#out{display:none}
.verdict{display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.pill{font-family:var(--mono);font-weight:500;font-size:20px;padding:8px 16px;border-radius:6px;border:1px solid}
.ALLOW{color:var(--ok);border-color:var(--ok)}.CHALLENGE{color:var(--amb);border-color:var(--amb)}.BLOCK{color:var(--err);border-color:var(--err)}.other{color:var(--gold);border-color:var(--gold)}
.big{font-family:var(--serif);font-size:24px}
h2{font-family:var(--serif);font-weight:500;font-size:22px;margin:4px 0 10px}
h2 small{font-family:var(--mono);font-size:11px;color:var(--gold);letter-spacing:.07em;display:block;margin-bottom:2px}
dl{display:grid;grid-template-columns:minmax(120px,190px) 1fr;gap:6px 14px;font-size:14px}
dt{color:var(--mut);font-size:13px}dd{font-family:var(--mono);font-size:13px;word-break:break-all}
@media(max-width:560px){dl{grid-template-columns:1fr}dt{margin-top:6px}}
.ck{display:flex;gap:10px;align-items:flex-start;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:14px}
.ck:last-child{border:0}.dot{width:10px;height:10px;border-radius:50%;margin-top:6px;flex:none}
.dot.ok{background:var(--ok);box-shadow:0 0 8px rgba(127,227,176,.6)}.dot.err{background:var(--err)}.dot.amb{background:var(--amb)}
pre{background:var(--ink);border:1px solid var(--line);border-radius:5px;padding:12px;overflow:auto;font-family:var(--mono);font-size:12px;max-height:340px;white-space:pre-wrap;word-break:break-all}
details summary{cursor:pointer;font-family:var(--mono);font-size:12.5px;color:var(--gold);margin:8px 0}
ul.lim{padding-left:18px;color:var(--mut);font-size:14px}ul.lim li{margin:5px 0}
.digest{font-family:var(--mono);font-size:12px;color:var(--gold);word-break:break-all}
footer{border-top:1px solid var(--line);margin-top:30px;padding:20px 0;font-size:12.5px;color:var(--mut)}
@media print{body{background:#fff;color:#000}.card{background:#fff;border-color:#bbb}.top,.form,.btns,footer{display:none}
dd,pre,.digest{color:#000}dt,.hero p,ul.lim{color:#333}pre{background:#f6f6f6;max-height:none;border-color:#ccc}.pill{border-color:#000;color:#000}h2 small,.kick{color:#7a5d00}}
</style></head><body>
<div class="top"><div class="wrap"><a class="brand" href="https://sebbi.pro/">AI<b>Leash</b> · sebbi.pro</a>
<span><a class="l" href="https://sebbi.pro/developers">Developers</a><a class="l" href="https://sebbi.pro/prove">Proof</a></span></div></div>
<div class="wrap">
<div class="hero"><div class="kick">MACHINE-PROOF REPORT</div>
<h1>One decision. <em>Every detail.</em></h1>
<p>The decision exactly as sealed. The account that sent it, the end user it was about, the IP address and request it came from. The chain re-verified from the first block to this one, a Merkle proof, the receipt sequence, and the public clocks either side of it. One report, one digest, sealed into the record when you issue it.</p></div>

<div class="card form">
<div class="row"><div><label>BLOCK NUMBER</label><input id="block" inputmode="numeric" placeholder="e.g. 7920"></div>
<div><label>OR RECEIPT HASH</label><input id="receipt" placeholder="64-character audit hash"></div></div>
<label>YOUR API KEY OR ADMIN TOKEN</label><input id="key" type="password" autocomplete="off" placeholder="al_live_…">
<div class="btns"><button class="btn" id="go">Build the report</button><button class="btn g" id="pub">Public half only</button></div>
<div class="hint">Your key opens reports for blocks it sealed. Without a key you get the public half: integrity and time, no personal data. The key stays in this page and is sent only to sebbi.pro.</div>
<div class="msg" id="msg"></div></div>

<div id="out"></div>
</div>
<footer><div class="wrap">Monop Content · Blyth, UK · <a style="color:var(--gold)" href="https://sebbi.pro/x/dossier/spec">How this report is built</a></div></footer>
<script>
const $=s=>document.querySelector(s);
const esc=v=>String(v==null?'—':v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let last=null;
function target(){const b=$('#block').value.trim(),r=$('#receipt').value.trim();
 if(b)return 'block='+encodeURIComponent(b); if(r)return 'receipt='+encodeURIComponent(r); return null}
function msg(t,c){const m=$('#msg');m.textContent=t;m.className='msg '+(c||'')}
function dl(obj){return '<dl>'+Object.entries(obj).filter(([k,v])=>v!==undefined).map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+(typeof v==='object'&&v!==null?esc(JSON.stringify(v)):esc(v))+'</dd>').join('')+'</dl>'}
function ck(ok,text){const c=ok===true?'ok':ok===false?'err':'amb';return '<div class="ck"><span class="dot '+c+'"></span><span>'+text+'</span></div>'}
function section(kick,title,body){return '<div class="card"><h2><small>'+kick+'</small>'+title+'</h2>'+body+'</div>'}
function render(r){
 last=r;const s=r.subject,i=r.integrity||{},t=r.time||{};
 const v=['ALLOW','CHALLENGE','BLOCK'].includes(s.verdict)?s.verdict:'other';
 let h=section('BLOCK '+esc(s.block_index),'The decision',
  '<div class="verdict"><span class="pill '+v+'">'+esc(s.verdict)+'</span><span class="big">score '+esc(s.score)+'</span></div><br>'+
  dl({'Sealed (UK)':s.sealed_at_uk,'Sealed (UTC)':s.sealed_at_utc,'Action':s.action,'Amount':s.amount,'Country':s.country,'Reasons':(s.reasons||[]).join(', ')||'none','Signal pack':s.signal_pack?JSON.stringify(s.signal_pack):'core nine','Audit hash':s.audit_hash}));
 if(r.who){const w=r.who,a=w.account||{};
  h+=section('WHO','Who did it',
   (w.account?dl({'Account holder':a.name,'Organisation':a.organisation,'Email':a.email,'Phone':a.phone,'Product':a.product,'Plan':(a.plan||'')+(a.paid?' · paid':' · trial'),'Account since':a.account_created_utc,'Key':a.key}):'<p class="hint">'+esc(w.account_note)+'</p>')+'<br>'+
   dl({'End user':w.subject_user,'Device':w.device,'Trust after':w.subject_history&&w.subject_history.trust_after_this_decision,'Other records':w.subject_history&&w.subject_history.other_records,'Verdict history':w.subject_history&&w.subject_history.verdict_counts,'Previous decision':w.subject_history&&w.subject_history.previous_decision,'Authority':w.authority,'Human review':w.human_review||'none recorded'}));}
 if(r.where){const x=r.where;
  h+=section('WHERE','Where it came from', x.captured?
   dl({'Sent by':x.sent_by,'IP address':x.ip,'Forwarded chain':(x.forwarded_chain||[]).join(' → ')||'—','User agent':x.user_agent,'Request':(x.method||'')+' '+(x.path||''),'Origin':x.origin,'Referer':x.referer,'Country header':x.country_header,'Request id':x.request_id,'End user context':x.end_user||'not attached'})+
   (x.records||[]).map(rc=>ck(rc.fingerprint_recomputes!==false&&!(rc.sealed_in&&rc.sealed_in.root_recomputes===false),'Context fingerprint '+esc((rc.context_fingerprint||'').slice(0,16))+'… '+(rc.sealed_in&&rc.sealed_in.root_block?'sealed in block '+esc(rc.sealed_in.root_block)+' (Merkle root recomputes)':'joins the next context root'))).join('')
   :'<p class="hint">'+esc(x.why)+'</p>');}
 let ic='';
 ic+=ck(i.block_hash_recomputes,'This block rehashes to the hash recorded when it was sealed');
 ic+=ck(i.links_to_previous,'It links to the block before it ('+esc(i.previous_block&&i.previous_block.index)+')');
 ic+=i.next_block?ck(i.next_block.links_back_to_this,'The next block ('+esc(i.next_block.index)+') links back to it'):ck(null,'Newest block — nothing sealed after it yet');
 ic+=ck(i.chain_verified_genesis_to_here,'Whole chain rehashed from genesis to here: '+esc(i.blocks_rehashed)+' blocks');
 if(i.merkle_inclusion&&i.merkle_inclusion.root)ic+=ck(true,'Merkle inclusion proof: leaf '+esc(i.merkle_inclusion.leaf_index)+' of '+esc(i.merkle_inclusion.tree_size)+', root '+esc(i.merkle_inclusion.root.slice(0,16))+'…');
 if(i.receipt_sequence)ic+=ck(i.receipt_sequence.gapless,'Account receipt sequence: '+esc(i.receipt_sequence.account_receipts)+' receipts, '+(i.receipt_sequence.gapless?'no gaps':'gaps found: '+esc(JSON.stringify(i.receipt_sequence.gaps))));
 h+=section('INTEGRITY','Has it changed?',ic);
 let tc='';const hb=t.heartbeat||{},an=t.bitcoin_anchor||{};
 tc+=ck(hb.floor?true:null,hb.floor?'Floor: created after public beacon '+esc(hb.floor.source)+' round '+esc(hb.floor.round)+' ('+esc(hb.floor.beacon_fetched_utc)+')':'No beacon before this block');
 tc+=ck(hb.ceiling?true:null,hb.ceiling?'Ceiling: sealed before beacon round '+esc(hb.ceiling.round)+' ('+esc(hb.ceiling.beacon_fetched_utc)+')'+(hb.window_seconds?' — a '+esc(hb.window_seconds)+'s window':''):'No beacon sealed after it yet');
 tc+=ck(an.state==='confirmed'?true:an.state==='pending'?null:null,'Bitcoin anchor: '+esc(an.state)+(an.anchored_tip_block?' — covered by the tip at block '+esc(an.anchored_tip_block)+(an.bitcoin_block_heights&&an.bitcoin_block_heights.length?', Bitcoin block '+esc(an.bitcoin_block_heights.join(', ')):''):'')+(an.proof?' · <a style="color:var(--gold)" href="'+esc(an.proof)+'">proof</a>':''));
 h+=section('TIME','When it happened',tc);
 if(r.linked_records)h+=section('LINKED','Later records that refer to it',dl(Object.fromEntries(r.linked_records.map(l=>['Block '+l.block,l.decision+' · '+l.utc+' · '+l.by]))));
 h+=section('LIMITS','What this report does not prove','<ul class="lim">'+(r.limits||[]).map(l=>'<li>'+esc(l)+'</li>').join('')+'</ul>');
 h+='<div class="card"><h2><small>DIGEST</small>This report\'s fingerprint</h2><div class="digest">'+esc(r.digest)+'</div>'+
  (r.issued?'<p class="msg ok">Issued and sealed at block '+esc(r.issued.issued_block)+'. Anyone can check it at <a style="color:var(--gold)" href="'+esc(r.issued.check)+'">'+esc(r.issued.check)+'</a></p>':'')+
  '<div class="btns">'+(r.who?'<button class="btn" id="issue">Issue and seal it</button>':'')+'<button class="btn g" id="print">Print / save PDF</button><button class="btn g" id="json">Download JSON</button></div>'+
  '<details><summary>Full report as data</summary><pre>'+esc(JSON.stringify(r,null,2))+'</pre></details></div>';
 $('#out').innerHTML=h;$('#out').style.display='block';
 $('#print').onclick=()=>window.print();
 $('#json').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(r,null,2)],{type:'application/json'}));a.download='sebbi-report-block-'+s.block_index+'.json';a.click()};
 const is=$('#issue');if(is)is.onclick=issue;
 $('#out').scrollIntoView({behavior:'smooth'});
}
async function go(pub){const t=target();if(!t){msg('Give a block number or a receipt hash.','err');return}
 const k=$('#key').value.trim();msg('Building…');
 try{const url=pub||!k?'/x/dossier/verify?'+t:'/dossier/data?'+t;
  const r=await fetch(url,{headers:k&&!pub?{'Authorization':'Bearer '+k}:{}});const d=await r.json();
  if(!r.ok){msg((d.message||d.error||('error '+r.status)),'err');return}
  msg(pub||!k?'Public half built — no personal data.':'Report built.','ok');render(d)}
 catch(e){msg('Could not reach sebbi.pro: '+e.message,'err')}}
async function issue(){const k=$('#key').value.trim(),btn=$('#issue');btn.disabled=true;btn.textContent='Sealing…';
 try{const r=await fetch('/dossier/issue',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},body:JSON.stringify({block:last.subject.block_index})});
  const d=await r.json();if(!r.ok){msg(d.error||'issue failed','err');btn.disabled=false;btn.textContent='Issue and seal it';return}
  const rep=d.report;rep.issued=d;render(rep);msg('Issued. The digest is sealed at block '+d.issued_block+'.','ok')}
 catch(e){msg(e.message,'err');btn.disabled=false}}
$('#go').onclick=()=>go(false);$('#pub').onclick=()=>go(true);
const q=new URLSearchParams(location.search);if(q.get('block')){$('#block').value=q.get('block')}if(q.get('receipt')){$('#receipt').value=q.get('receipt')}
</script></body></html>"""

```


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/earnpage.py`

293 lines, 21176 bytes

```python
"""
modules/earnpage.py  v1.0.1
The creator's withdrawal page at /earn, plus a "My earnings" button on the
homepage.

  /earn   claim a creator name (get a private key), see earnings and paid
          unlocks, link a bank through Stripe, withdraw to it, and see every
          past withdrawal with its proof in the chain.

Talks to modules/credits.py (v1.2.0 or later) over /c/creator/.

1.0.1: no longer touches the homepage at all. The homepage belongs to
index.html and homelink.py; the My earnings button goes in homelink.py.

Page module, same family as creditspage.py: a runtime do_GET patch.
Armed by /x/earnpage/status after each deploy.
"""

import base64
import io
import re
import sys

VERSION = "1.0.1"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk15IGVhcm5pbmdzIOKAlCBNb25vcCBTdHVkaW88L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0i"
    "WW91ciBNb25vcCBTdHVkaW8gZWFybmluZ3MuIEV2ZXJ5IHVubG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgc3RyYWlnaHQgdG8g"
    "eW91ciBiYW5rLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9VW5ib3VuZGVk"
    "OndnaHRANjAwOzgwMCZmYW1pbHk9RmlndHJlZTp3Z2h0QDUwMDs3MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8"
    "c3R5bGU+Cjpyb290ey0tYmc6IzJiM2JmZjstLWRlZXA6IzExMTY1ZTstLXBpbms6I2ZmM2Q4YjstLXN1bjojZmZlMTRkOy0tbWlu"
    "dDojM2RmZmIyOy0td2hpdGU6I2ZmZjstLXNvZnQ6cmdiYSgyNTUsMjU1LDI1NSwuNzgpOwotLWQ6J1VuYm91bmRlZCcsJ0FyaWFs"
    "IEJsYWNrJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXQ6J0ZpZ3RyZWUnLHN5c3RlbS11aSwtYXBwbGUtc3lzdGVtLCdTZWdvZSBV"
    "SScsc2Fucy1zZXJpZn0KQG1lZGlhIChwcmVmZXJzLWNvbG9yLXNjaGVtZTogZGFyayl7OnJvb3Q6bm90KFtkYXRhLXRoZW1lPSJs"
    "aWdodCJdKXstLWJnOiMyYjNiZmZ9fQo6cm9vdFtkYXRhLXRoZW1lPSJkYXJrIl17LS1iZzojMmIzYmZmfQo6cm9vdHtib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7cGFkZGluZy10b3A6ZW52KHNhZmUtYXJlYS1pbnNldC10b3AsMHB4KTtwYWRkaW5nLWJvdHRvbTplbnYo"
    "c2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwcHgpfQpodG1se3Njcm9sbC1wYWRkaW5nLXRvcDplbnYoc2FmZS1hcmVhLWluc2V0LXRv"
    "cCwwcHgpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdlYmtpdC10YXAtaGlnaGxpZ2h0LWNv"
    "bG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXdoaXRlKTtmb250LWZhbWlseTp2"
    "YXIoLS10KTtsaW5lLWhlaWdodDoxLjU7bWluLWhlaWdodDoxMDAlfQoud3JhcHttYXgtd2lkdGg6NTYwcHg7bWFyZ2luOjAgYXV0"
    "bztwYWRkaW5nOjE4cHggMjBweCA2MHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjth"
    "bGlnbi1pdGVtczpjZW50ZXI7Zm9udC13ZWlnaHQ6NzAwfQoudG9wIGF7Y29sb3I6dmFyKC0td2hpdGUpO3RleHQtZGVjb3JhdGlv"
    "bjpub25lO29wYWNpdHk6Ljg1O21hcmdpbi1sZWZ0OjE2cHg7Zm9udC1zaXplOjE0cHh9Ci5icmFuZHtmb250LWZhbWlseTp2YXIo"
    "LS1kKTtmb250LXNpemU6MTVweH0KaDF7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFt"
    "cCgzMHB4LDguNXZ3LDQ2cHgpO2xpbmUtaGVpZ2h0OjEuMDI7bWFyZ2luOjI2cHggMCAxMHB4fQoudGFne2Rpc3BsYXk6aW5saW5l"
    "LWJsb2NrO3BhZGRpbmc6LjA1ZW0gLjNlbTtib3JkZXItcmFkaXVzOi4xOGVtO3RyYW5zZm9ybTpyb3RhdGUoLTJkZWcpO2JhY2tn"
    "cm91bmQ6dmFyKC0tcGluayl9CnAubGVhZHtjb2xvcjp2YXIoLS1zb2Z0KTtmb250LXNpemU6MTdweDttYXgtd2lkdGg6NDRjaH0K"
    "LmNhcmR7YmFja2dyb3VuZDp2YXIoLS1kZWVwKTtib3JkZXItcmFkaXVzOjIycHg7cGFkZGluZzoyMnB4O21hcmdpbi10b3A6MThw"
    "eH0KLmNhcmQgaDJ7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC1zaXplOjE5cHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5jYXJkIHB7"
    "Y29sb3I6dmFyKC0tc29mdCk7Zm9udC1zaXplOjE1cHh9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQt"
    "c2l6ZToxNHB4O21hcmdpbjoxNHB4IDAgNnB4fQppbnB1dHt3aWR0aDoxMDAlO3BhZGRpbmc6MTVweCAxNnB4O2JvcmRlci1yYWRp"
    "dXM6MTRweDtib3JkZXI6MDtmb250OjcwMCAxN3B4IHZhcigtLXQpO2NvbG9yOnZhcigtLWRlZXApO2JhY2tncm91bmQ6I2ZmZn0K"
    "aW5wdXQ6Zm9jdXN7b3V0bGluZTozcHggc29saWQgdmFyKC0tc3VuKX0KYnV0dG9uLC5idG57ZGlzcGxheTppbmxpbmUtYmxvY2s7"
    "d2lkdGg6MTAwJTttYXJnaW4tdG9wOjE0cHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLXJhZGl1czo5OTlweDtib3JkZXI6MDtj"
    "dXJzb3I6cG9pbnRlcjsKIGZvbnQ6ODAwIDE2cHggdmFyKC0tZCk7YmFja2dyb3VuZDp2YXIoLS1zdW4pO2NvbG9yOiMxYTEzMDA7"
    "dGV4dC1hbGlnbjpjZW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmV9CmJ1dHRvbjpmb2N1cy12aXNpYmxlLC5idG46Zm9jdXMtdmlz"
    "aWJsZXtvdXRsaW5lOjNweCBzb2xpZCAjZmZmO291dGxpbmUtb2Zmc2V0OjNweH0KYnV0dG9uLnBpbmt7YmFja2dyb3VuZDp2YXIo"
    "LS1waW5rKTtjb2xvcjojZmZmfQpidXR0b24uZ2hvc3R7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlcjoy"
    "cHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuNCl9CmJ1dHRvbjpkaXNhYmxlZHtvcGFjaXR5Oi40NTtjdXJzb3I6bm90LWFsbG93"
    "ZWR9Ci5iYWx7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFtcCg1NHB4LDE3dncsODhw"
    "eCk7bGluZS1oZWlnaHQ6MTtjb2xvcjp2YXIoLS1zdW4pO21hcmdpbjo2cHggMCA0cHg7Zm9udC12YXJpYW50LW51bWVyaWM6dGFi"
    "dWxhci1udW1zfQoucm93e2Rpc3BsYXk6ZmxleDtnYXA6MTBweH0ucm93Pip7ZmxleDoxfQouc3RhdHtiYWNrZ3JvdW5kOnJnYmEo"
    "MjU1LDI1NSwyNTUsLjA4KTtib3JkZXItcmFkaXVzOjE2cHg7cGFkZGluZzoxMnB4IDE0cHh9Ci5zdGF0IGJ7ZGlzcGxheTpibG9j"
    "aztmb250LWZhbWlseTp2YXIoLS1kKTtmb250LXNpemU6MjJweH0uc3RhdCBzcGFue2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigt"
    "LXNvZnQpfQoua2V5Ym94e21hcmdpbi10b3A6MTJweDtiYWNrZ3JvdW5kOiNmZmY7Y29sb3I6dmFyKC0tZGVlcCk7Ym9yZGVyLXJh"
    "ZGl1czoxNHB4O3BhZGRpbmc6MTRweDtmb250OjcwMCAxNHB4IHVpLW1vbm9zcGFjZSxNZW5sbyxtb25vc3BhY2U7d29yZC1icmVh"
    "azpicmVhay1hbGx9Ci5tc2d7bWFyZ2luLXRvcDoxNHB4O3BhZGRpbmc6MTRweCAxNnB4O2JvcmRlci1yYWRpdXM6MTRweDtiYWNr"
    "Z3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjEyKTtmb250LXdlaWdodDo3MDA7ZGlzcGxheTpub25lfQoubXNnLm9ue2Rpc3BsYXk6"
    "YmxvY2t9Lm1zZy5nb29ke2JhY2tncm91bmQ6dmFyKC0tbWludCk7Y29sb3I6IzA3MzAxZn0ubXNnLmJhZHtiYWNrZ3JvdW5kOnZh"
    "cigtLXBpbmspfQouc3RhdGV7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweDtmb250LXdlaWdodDo3MDA7"
    "bWFyZ2luLXRvcDo2cHh9Ci5kb3R7d2lkdGg6MTJweDtoZWlnaHQ6MTJweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZh"
    "cigtLXN1bik7ZmxleDpub25lfS5kb3Qub2t7YmFja2dyb3VuZDp2YXIoLS1taW50KX0KLmxpc3QgZGl2e2Rpc3BsYXk6ZmxleDtq"
    "dXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtwYWRkaW5nOjEwcHggMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwy"
    "NTUsMjU1LC4xMik7Zm9udC1zaXplOjE1cHh9Ci5saXN0IGF7Y29sb3I6dmFyKC0tbWludCl9Ci5zbWFsbHtmb250LXNpemU6MTNw"
    "eDtjb2xvcjp2YXIoLS1zb2Z0KTttYXJnaW4tdG9wOjEwcHh9Ci5zbWFsbCBhe2NvbG9yOiNmZmZ9CltoaWRkZW5de2Rpc3BsYXk6"
    "bm9uZSFpbXBvcnRhbnR9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0b3AiPjxk"
    "aXYgY2xhc3M9ImJyYW5kIj5Nb25vcCBTdHVkaW88L2Rpdj48bmF2PjxhIGhyZWY9Ii9jcmVhdGUiPlN0dWRpbzwvYT48YSBocmVm"
    "PSIvY2luZW1hIj5DaW5lbWE8L2E+PGEgaHJlZj0iLyI+SG9tZTwvYT48L25hdj48L2Rpdj4KCjxzZWN0aW9uIGlkPSJqb2luIiBo"
    "aWRkZW4+CiAgPGgxPkdldCBwYWlkIGZvciA8c3BhbiBjbGFzcz0idGFnIj55b3VyIHZpZGVvcy48L3NwYW4+PC9oMT4KICA8cCBj"
    "bGFzcz0ibGVhZCI+Q2xhaW0geW91ciBjcmVhdG9yIG5hbWUsIGxvY2sgeW91ciB2aWRlb3Mgd2l0aCBpdCwgYW5kIGV2ZXJ5IHVu"
    "bG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgdG8geW91ciBiYW5rIHdoZW5ldmVyIHlvdSBsaWtlLjwvcD4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj4KICAgIDxoMj5DbGFpbSB5b3VyIGNyZWF0b3IgbmFtZTwvaDI+CiAgICA8cD5Vc2UgZXhhY3RseSB0aGlzIG5hbWUg"
    "aW4gdGhlIHN0dWRpbyB3aGVuIHlvdSBsb2NrIGEgdmlkZW8uIFRoYXQncyBob3cgeW91ciBlYXJuaW5ncyBmaW5kIHlvdS48L3A+"
    "CiAgICA8bGFiZWwgZm9yPSJuYW1lIj5DcmVhdG9yIG5hbWU8L2xhYmVsPgogICAgPGlucHV0IGlkPSJuYW1lIiBtYXhsZW5ndGg9"
    "IjQwIiBhdXRvY29tcGxldGU9Im9mZiIgcGxhY2Vob2xkZXI9ImUuZy4gS2lja2ZsaXBLYWkiPgogICAgPGJ1dHRvbiBpZD0iam9p"
    "bkJ0biI+Q2xhaW0gbXkgbmFtZTwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgPGgyPkFscmVhZHkg"
    "aGF2ZSBhIGtleT88L2gyPgogICAgPHA+U2lnbiBpbiBvbiB0aGlzIGRldmljZSB3aXRoIHRoZSBrZXkgeW91IHNhdmVkLjwvcD4K"
    "ICAgIDxsYWJlbCBmb3I9ImtleUluIj5Zb3VyIGtleTwvbGFiZWw+CiAgICA8aW5wdXQgaWQ9ImtleUluIiBhdXRvY29tcGxldGU9"
    "Im9mZiIgcGxhY2Vob2xkZXI9ImNrX+KApiI+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImtleUJ0biI+U2lnbiBpbjwv"
    "YnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9Im1zZyIgaWQ9ImpvaW5Nc2ciPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlv"
    "biBpZD0ic2F2ZWQiIGhpZGRlbj4KICA8aDE+U2F2ZSA8c3BhbiBjbGFzcz0idGFnIj55b3VyIGtleS48L3NwYW4+PC9oMT4KICA8"
    "cCBjbGFzcz0ibGVhZCI+VGhpcyBrZXkgaXMgaG93IHlvdSB3aXRoZHJhdyB5b3VyIG1vbmV5LiBJdCdzIHNhdmVkIG9uIHRoaXMg"
    "cGhvbmUsIGJ1dCBrZWVwIGEgY29weSBzb21ld2hlcmUgc2FmZS4gSWYgeW91IGxvc2UgaXQsIG5vYm9keSBjYW4gZ2V0IHlvdXIg"
    "ZWFybmluZ3MgYmFjay48L3A+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDIgaWQ9InNhdmVkTmFtZSI+PC9oMj4KICAgIDxk"
    "aXYgY2xhc3M9ImtleWJveCIgaWQ9InNhdmVkS2V5Ij48L2Rpdj4KICAgIDxidXR0b24gaWQ9ImNvcHlCdG4iPkNvcHkgbXkga2V5"
    "PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImRvbmVCdG4iPkkndmUgc2F2ZWQgaXQ8L2J1dHRvbj4KICA8"
    "L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9ImRhc2giIGhpZGRlbj4KICA8aDEgaWQ9ImhlbGxvIj5Zb3VyIGVhcm5pbmdz"
    "PC9oMT4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgIDxwPlJlYWR5IHRvIHdpdGhkcmF3PC9wPgogICAgPGRpdiBjbGFzcz0iYmFs"
    "IiBpZD0iYmFsIj7CozAuMDA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiIGlkPSJ2aWV3cyI+MDwvYj48c3Bhbj5wYWlkIHVubG9ja3M8L3NwYW4+PC9kaXY+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiPjdwPC9iPjxzcGFuPnBlciB1bmxvY2s8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rp"
    "dj4KICA8ZGl2IGNsYXNzPSJjYXJkIiBpZD0icGF5Q2FyZCI+CiAgICA8aDI+V2l0aGRyYXcgdG8geW91ciBiYW5rPC9oMj4KICAg"
    "IDxkaXYgY2xhc3M9InN0YXRlIj48c3BhbiBjbGFzcz0iZG90IiBpZD0iZG90Ij48L3NwYW4+PHNwYW4gaWQ9InN0YXRlVGV4dCI+"
    "Q2hlY2tpbmfigKY8L3NwYW4+PC9kaXY+CiAgICA8YnV0dG9uIGlkPSJzZXR1cEJ0biIgaGlkZGVuPlNldCB1cCBwYXlvdXRzPC9i"
    "dXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJwaW5rIiBpZD0id2l0aGRyYXdCdG4iIGhpZGRlbj5XaXRoZHJhdzwvYnV0dG9uPgog"
    "ICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiIGlkPSJzdHJpcGVCdG4iIGhpZGRlbj5PcGVuIG15IFN0cmlwZSBhY2NvdW50PC9idXR0"
    "b24+CiAgICA8cCBjbGFzcz0ic21hbGwiIGlkPSJwYXlOb3RlIj5QYXlvdXRzIGdvIHRocm91Z2ggU3RyaXBlLCBzdHJhaWdodCB0"
    "byB5b3VyIGJhbmsuIFVuZGVyIDE4PyBBIHBhcmVudCBvciBndWFyZGlhbiBzZXRzIHRoaXMgdXAgd2l0aCB0aGVpciBkZXRhaWxz"
    "LjwvcD4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJtc2ciIGlkPSJkYXNoTXNnIj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj4K"
    "ICAgIDxoMj5QYXN0IHdpdGhkcmF3YWxzPC9oMj4KICAgIDxkaXYgY2xhc3M9Imxpc3QiIGlkPSJsaXN0Ij48cD5Ob25lIHlldC48"
    "L3A+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDI+TG9jayBhIHZpZGVvPC9oMj4KICAgIDxwPklu"
    "IHRoZSBzdHVkaW8sIHB1dCA8YiBpZD0ibmFtZUhpbnQiPjwvYj4gYXMgdGhlIGNyZWF0b3IgbmFtZSBzbyBldmVyeSB1bmxvY2sg"
    "cGF5cyB5b3UuPC9wPgogICAgPGEgY2xhc3M9ImJ0biIgaHJlZj0iL2NyZWF0ZSI+T3BlbiB0aGUgc3R1ZGlvPC9hPgogIDwvZGl2"
    "PgogIDxwIGNsYXNzPSJzbWFsbCI+U2lnbmVkIGluIG9uIHRoaXMgZGV2aWNlLiA8YSBocmVmPSIjIiBpZD0ib3V0QnRuIj5TaWdu"
    "IG91dDwvYT48L3A+Cjwvc2VjdGlvbj4KPC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewoidXNlIHN0cmljdCI7CnZhciBBUEk9"
    "Ii9jL2NyZWF0b3IvIiwgSz0ic2ViYmkuY3JlYXRvciI7CmZ1bmN0aW9uICQoaSl7cmV0dXJuIGRvY3VtZW50LmdldEVsZW1lbnRC"
    "eUlkKGkpfQpmdW5jdGlvbiBsb2FkKCl7dHJ5e3JldHVybiBKU09OLnBhcnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKEspfHwibnVs"
    "bCIpfWNhdGNoKGUpe3JldHVybiBudWxsfX0KZnVuY3Rpb24gc2F2ZSh2KXt0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oSyxKU09O"
    "LnN0cmluZ2lmeSh2KSl9Y2F0Y2goZSl7fX0KZnVuY3Rpb24gZ2JwKHApe3A9cHx8MDtyZXR1cm4gIsKjIitNYXRoLmZsb29yKHAv"
    "MTAwKSsiLiIrKCIwIisocCUxMDApKS5zbGljZSgtMil9CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2Uo"
    "L1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybiB7IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7"
    "In1bY119KX0KZnVuY3Rpb24gc2F5KGlkLHRleHQsa2luZCl7dmFyIG09JChpZCk7bS5jbGFzc05hbWU9Im1zZyBvbiIrKGtpbmQ/"
    "IiAiK2tpbmQ6IiIpO20udGV4dENvbnRlbnQ9dGV4dH0KZnVuY3Rpb24gcG9zdCh3aGF0LGJvZHkpe3JldHVybiBmZXRjaChBUEkr"
    "d2hhdCx7bWV0aG9kOiJQT1NUIixoZWFkZXJzOnsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiJ9LGJvZHk6SlNPTi5z"
    "dHJpbmdpZnkoYm9keSl9KQogLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpLnRoZW4oZnVuY3Rpb24oZCl7ZC5fb2s9"
    "ci5vaztyZXR1cm4gZH0pfSl9CmZ1bmN0aW9uIHZpZXcodil7WyJqb2luIiwic2F2ZWQiLCJkYXNoIl0uZm9yRWFjaChmdW5jdGlv"
    "bihzKXskKHMpLmhpZGRlbj0ocyE9PXYpfSk7d2luZG93LnNjcm9sbFRvKDAsMCl9CnZhciBtZT1sb2FkKCksIGRhdGE9bnVsbDsK"
    "CmZ1bmN0aW9uIHJlZnJlc2goKXsKICByZXR1cm4gcG9zdCgibWUiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXsKICAg"
    "IGlmKCFkLl9vayl7IGlmKGQuZXJyb3I9PT0iYmFkX2tleSIpe21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIik7c2F5KCJq"
    "b2luTXNnIiwiVGhhdCBrZXkgd2Fzbid0IHJlY29nbmlzZWQuIFNpZ24gaW4gYWdhaW4uIiwiYmFkIil9IHJldHVybiB9CiAgICBk"
    "YXRhPWQ7IHZpZXcoImRhc2giKTsKICAgICQoImhlbGxvIikudGV4dENvbnRlbnQ9IkhpICIrZC5uYW1lOwogICAgJCgibmFtZUhp"
    "bnQiKS50ZXh0Q29udGVudD1kLm5hbWU7CiAgICAkKCJiYWwiKS50ZXh0Q29udGVudD1nYnAoZC5iYWxhbmNlX3BlbmNlKTsKICAg"
    "ICQoInZpZXdzIikudGV4dENvbnRlbnQ9KGQucGFpZF92aWV3c3x8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUdCIik7CiAgICB2YXIg"
    "c2I9JCgic2V0dXBCdG4iKSx3Yj0kKCJ3aXRoZHJhd0J0biIpLHN0PSQoInN0cmlwZUJ0biIpLGRvdD0kKCJkb3QiKSx0eD0kKCJz"
    "dGF0ZVRleHQiKTsKICAgIHNiLmhpZGRlbj13Yi5oaWRkZW49c3QuaGlkZGVuPXRydWU7ZG90LmNsYXNzTmFtZT0iZG90IjsKICAg"
    "IGlmKCFkLnBheW91dHNfcmVhZHlfb25fc2l0ZSl7dHgudGV4dENvbnRlbnQ9IlBheW91dHMgYXJlIGJlaW5nIHN3aXRjaGVkIG9u"
    "LiBZb3VyIGVhcm5pbmdzIGFyZSBzYWZlIG9uIHlvdXIgYmFsYW5jZS4ifQogICAgZWxzZSBpZighZC5iYW5rX2xpbmtlZCl7dHgu"
    "dGV4dENvbnRlbnQ9Ik5vIGJhbmsgbGlua2VkIHlldC4iO3NiLmhpZGRlbj1mYWxzZTtzYi50ZXh0Q29udGVudD0iU2V0IHVwIHBh"
    "eW91dHMifQogICAgZWxzZSBpZighZC5wYXlvdXRzX2VuYWJsZWQpe3R4LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/"
    "IlN0cmlwZSBpcyBjaGVja2luZyB5b3VyIGRldGFpbHMuIjoiU2V0dXAgbm90IGZpbmlzaGVkLiI7c2IuaGlkZGVuPWZhbHNlO3Ni"
    "LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/IkNoZWNrIG15IGRldGFpbHMiOiJGaW5pc2ggc2V0dXAifQogICAgZWxz"
    "ZXsKICAgICAgZG90LmNsYXNzTmFtZT0iZG90IG9rIjt0eC50ZXh0Q29udGVudD0iQmFuayBsaW5rZWQuIFJlYWR5IHRvIHBheSBv"
    "dXQuIjtzdC5oaWRkZW49ZmFsc2U7d2IuaGlkZGVuPWZhbHNlOwogICAgICBpZihkLmJhbGFuY2VfcGVuY2U+PWQubWluX3dpdGhk"
    "cmF3X3BlbmNlKXt3Yi5kaXNhYmxlZD1mYWxzZTt3Yi50ZXh0Q29udGVudD0iV2l0aGRyYXcgIitnYnAoZC5iYWxhbmNlX3BlbmNl"
    "KX0KICAgICAgZWxzZXt3Yi5kaXNhYmxlZD10cnVlO3diLnRleHRDb250ZW50PSJXaXRoZHJhdyBmcm9tICIrZ2JwKGQubWluX3dp"
    "dGhkcmF3X3BlbmNlKX0KICAgIH0KICAgIHZhciBMPSQoImxpc3QiKTsKICAgIGlmKCFkLnBheW91dHN8fCFkLnBheW91dHMubGVu"
    "Z3RoKXtMLmlubmVySFRNTD0iPHA+Tm9uZSB5ZXQuPC9wPiJ9CiAgICBlbHNle0wuaW5uZXJIVE1MPWQucGF5b3V0cy5tYXAoZnVu"
    "Y3Rpb24ocCl7CiAgICAgIHZhciB3aGVuPXAuYXQuc2xpY2UoMCwxMCksIHM9cC5zdGF0dXM9PT0ic2VudCI/IlNlbnQiOihwLnN0"
    "YXR1cz09PSJmYWlsZWQiPyJEaWRuJ3QgZ28gdGhyb3VnaCwgcmV0dXJuZWQiOiJTZW5kaW5nIik7CiAgICAgIHZhciBwcm9vZj1w"
    "LmJsb2NrX2luZGV4IT1udWxsPycgwrcgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8veC93YWxrL2Jsb2NrP2luZGV4PScrcC5i"
    "bG9ja19pbmRleCsnIj5wcm9vZjwvYT4nOiIiOwogICAgICByZXR1cm4gIjxkaXY+PHNwYW4+Iit3aGVuKyIgwrcgIitzK3Byb29m"
    "KyI8L3NwYW4+PGI+IitnYnAocC5wZW5jZSkrIjwvYj48L2Rpdj4ifSkuam9pbigiIil9CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtz"
    "YXkoImRhc2hNc2ciLCJDb3VsZG4ndCByZWFjaCBzZWJiaS5wcm8uIENoZWNrIHlvdXIgY29ubmVjdGlvbi4iLCJiYWQiKX0pOwp9"
    "CgpmdW5jdGlvbiBnb1N0cmlwZSgpewogIHNheSgiZGFzaE1zZyIsIk9wZW5pbmcgU3RyaXBl4oCmIik7CiAgcG9zdCgiY29ubmVj"
    "dCIse2tleTptZS5rZXl9KS50aGVuKGZ1bmN0aW9uKGQpeyBpZihkLnVybCl7bG9jYXRpb24uaHJlZj1kLnVybH0gZWxzZSBzYXko"
    "ImRhc2hNc2ciLGQubWVzc2FnZXx8IkNvdWxkbid0IG9wZW4gU3RyaXBlIGp1c3Qgbm93LiIsImJhZCIpIH0pCiAgLmNhdGNoKGZ1"
    "bmN0aW9uKCl7c2F5KCJkYXNoTXNnIiwiQ291bGRuJ3QgcmVhY2ggc2ViYmkucHJvLiIsImJhZCIpfSk7Cn0KCiQoImpvaW5CdG4i"
    "KS5vbmNsaWNrPWZ1bmN0aW9uKCl7CiAgdmFyIG49JCgibmFtZSIpLnZhbHVlLnRyaW0oKTsgaWYobi5sZW5ndGg8Myl7c2F5KCJq"
    "b2luTXNnIiwiUGljayBhIG5hbWUgb2YgYXQgbGVhc3QgMyBsZXR0ZXJzIG9yIG51bWJlcnMuIiwiYmFkIik7cmV0dXJufQogIHRo"
    "aXMuZGlzYWJsZWQ9dHJ1ZTt2YXIgYj10aGlzOwogIHBvc3QoImpvaW4iLHtuYW1lOm59KS50aGVuKGZ1bmN0aW9uKGQpe2IuZGlz"
    "YWJsZWQ9ZmFsc2U7CiAgICBpZighZC5fb2spe3NheSgiam9pbk1zZyIsZC5tZXNzYWdlfHwiQ291bGRuJ3QgY2xhaW0gdGhhdCBu"
    "YW1lLiIsImJhZCIpO3JldHVybn0KICAgIG1lPXtrZXk6ZC5rZXksbmFtZTpkLm5hbWUsaWQ6ZC5jcmVhdG9yX2lkfTtzYXZlKG1l"
    "KTsKICAgICQoInNhdmVkTmFtZSIpLnRleHRDb250ZW50PWQubmFtZTskKCJzYXZlZEtleSIpLnRleHRDb250ZW50PWQua2V5O3Zp"
    "ZXcoInNhdmVkIik7CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtiLmRpc2FibGVkPWZhbHNlO3NheSgiam9pbk1zZyIsIkNvdWxkbid0"
    "IHJlYWNoIHNlYmJpLnByby4iLCJiYWQiKX0pOwp9OwokKCJrZXlCdG4iKS5vbmNsaWNrPWZ1bmN0aW9uKCl7dmFyIGs9JCgia2V5"
    "SW4iKS52YWx1ZS50cmltKCk7aWYoIWspcmV0dXJuO21lPXtrZXk6a307c2F2ZShtZSk7cmVmcmVzaCgpfTsKJCgiY29weUJ0biIp"
    "Lm9uY2xpY2s9ZnVuY3Rpb24oKXt2YXIgaz1tZSYmbWUua2V5O2lmKCFrKXJldHVybjsKICAobmF2aWdhdG9yLmNsaXBib2FyZD9u"
    "YXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChrKTpQcm9taXNlLnJlamVjdCgpKS50aGVuKGZ1bmN0aW9uKCl7JCgiY29weUJ0"
    "biIpLnRleHRDb250ZW50PSJDb3BpZWQifSxmdW5jdGlvbigpeyQoImNvcHlCdG4iKS50ZXh0Q29udGVudD0iUHJlc3MgYW5kIGhv"
    "bGQgdGhlIGtleSB0byBjb3B5IGl0In0pfTsKJCgiZG9uZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtyZWZyZXNoKCl9OwokKCJz"
    "ZXR1cEJ0biIpLm9uY2xpY2s9Z29TdHJpcGU7CiQoInN0cmlwZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtwb3N0KCJkYXNoYm9h"
    "cmQiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtpZihkLnVybClsb2NhdGlvbi5ocmVmPWQudXJsO2Vsc2Ugc2F5KCJk"
    "YXNoTXNnIixkLm1lc3NhZ2V8fCJDb3VsZG4ndCBvcGVuIFN0cmlwZS4iLCJiYWQiKX0pfTsKJCgid2l0aGRyYXdCdG4iKS5vbmNs"
    "aWNrPWZ1bmN0aW9uKCl7CiAgdmFyIGI9dGhpcztiLmRpc2FibGVkPXRydWU7Yi50ZXh0Q29udGVudD0iU2VuZGluZ+KApiI7CiAg"
    "cG9zdCgid2l0aGRyYXciLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtzYXkoImRhc2hNc2ciLGQubWVzc2FnZXx8KGQu"
    "cGFpZD8iU2VudC4iOiJEaWRuJ3QgZ28gdGhyb3VnaC4iKSxkLnBhaWQ/Imdvb2QiOiJiYWQiKTtyZWZyZXNoKCl9KQogIC5jYXRj"
    "aChmdW5jdGlvbigpe3NheSgiZGFzaE1zZyIsIkNvdWxkbid0IHJlYWNoIHNlYmJpLnByby4gTm90aGluZyB3YXMgdGFrZW4gZnJv"
    "bSB5b3VyIGJhbGFuY2UuIiwiYmFkIik7cmVmcmVzaCgpfSk7Cn07CiQoIm91dEJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oZSl7ZS5w"
    "cmV2ZW50RGVmYXVsdCgpO21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIil9OwoKdmFyIHE9bG9jYXRpb24uc2VhcmNoOwpp"
    "ZihtZSYmbWUua2V5KXsKICByZWZyZXNoKCkudGhlbihmdW5jdGlvbigpewogICAgaWYoL1s/Jl1yZXRyeT0xLy50ZXN0KHEpKSBn"
    "b1N0cmlwZSgpOwogICAgZWxzZSBpZigvWz8mXWNvbm5lY3RlZD0xLy50ZXN0KHEpKSBzYXkoImRhc2hNc2ciLCJUaGFua3MuIFN0"
    "cmlwZSBoYXMgeW91ciBkZXRhaWxzLiBJdCBjYW4gdGFrZSBhIGZldyBtaW51dGVzIGZvciB0aGVtIHRvIGJlIGNoZWNrZWQuIiwi"
    "Z29vZCIpOwogICAgdHJ5e2hpc3RvcnkucmVwbGFjZVN0YXRlKG51bGwsIiIsbG9jYXRpb24ucGF0aG5hbWUpfWNhdGNoKGUpe30K"
    "ICB9KTsKfSBlbHNlIHZpZXcoImpvaW4iKTsKfSkoKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/earn": (_d(_HTML_B64), "text/html; charset=utf-8"),
}

_BUTTON = (
    b'<a id="sebbi-earn-btn" href="/earn" style="position:fixed;right:14px;'
    b'bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'display:flex;align-items:center;gap:8px;padding:12px 16px;border-radius:999px;'
    b'background:#ffe14d;color:#1a1300;font:800 14px system-ui,-apple-system,Segoe UI,sans-serif;'
    b'text-decoration:none;box-shadow:0 6px 20px rgba(0,0,0,.35)">'
    b'<span style="display:grid;place-items:center;width:24px;height:24px;border-radius:50%;'
    b'background:#ff3d8b;color:#fff;font-size:13px">&pound;</span>My earnings</a>'
)

_HOME_PATHS = ("/", "/index.html")
_patched = False


def _inject(raw):
    """Add the button to a captured homepage response. Returns raw unchanged if unsure."""
    try:
        sep = raw.find(b"\r\n\r\n")
        if sep < 0:
            return raw
        head, body = raw[:sep], raw[sep + 4:]
        low = head.lower()
        if b"text/html" not in low or b"content-encoding" in low or b"transfer-encoding" in low:
            return raw
        if b"sebbi-earn-btn" in body:
            return raw
        i = body.lower().rfind(b"</body>")
        if i < 0:
            return raw
        body = body[:i] + _BUTTON + body[i:]
        if re.search(rb"(?im)^content-length:", head):
            head = re.sub(rb"(?im)^(content-length:)\s*\d+", b"\\g<1> " + str(len(body)).encode(), head)
        return head + b"\r\n\r\n" + body
    except Exception:
        return raw


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


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_earnpage_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._earnpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "earnpage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys()), "homepage_button": False}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
