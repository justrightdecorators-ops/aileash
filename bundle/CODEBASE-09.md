# Codebase — part 9 of 38

Contains:
- `modules/heartbeat.py`
- `modules/held.py`
- `modules/integrity.py`


## `modules/heartbeat.py`

872 lines, 31733 bytes

```python
"""
heartbeat.py - the two-sided clock.

WHAT PROBLEM THIS SOLVES
------------------------
Every timestamp in this system is a number the operator wrote. External
anchoring (OpenTimestamps) and peer witnessing both prove a record existed
BEFORE some later public event. They are ceilings.

Nothing proved a floor. Nothing stopped a record being created EARLIER than
it claims, or a whole chain being pre-computed in advance and released
slowly to look live. That is the fraud that actually happens: the grant
written after the incident, the decision dated last Tuesday.

A clock cannot fix this. Anyone can write down what a clock will say at
14:32:07 tomorrow, so hashing a clock face adds a hash, not a time.

WHAT DOES FIX IT
----------------
A public beacon: a source that ticks on a fixed cadence like a clock, but
whose value at each tick cannot be known by anyone until the tick happens.
drand (League of Entropy) publishes one every 30 seconds. Bitcoin publishes
one roughly every ten minutes.

Fold that value into a sealed block and the block cannot have been created
before the tick existed. Not because we say so - because it contains a
number that did not exist yet.

THE INTERLEAVE, WHICH IS THE WHOLE TRICK
----------------------------------------
We do NOT stamp every decision. We seal one beat into the chain every few
minutes. The chain is append-only and prev-hash linked, so any record
sitting between beat A and beat B was necessarily created after A and
before B.

One beat therefore gives a floor to every record that follows it, and the
next beat gives all of them a ceiling. Every decision gets a two-sided
window for free, with no change to seal(), no change to server.py, and no
extra latency on the decision path.

The window width is published on every answer. It is a live public
measurement of how much room the operator would have to lie in. It is the
only number in this system that gets better by us doing more work, and
worse by us doing less, which is why it is published.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the record is true. It proves when it can have been made.
- It does not verify drand's BLS signature (not feasible in pure stdlib).
  It records the round and the randomness verbatim, and anyone can re-fetch
  that round from drand and confirm the value matches. Deterministic,
  public, and does not involve us.
- A record inside an open window (after the last beat, before the next) has
  a floor and no ceiling yet. That is reported as open, never as closed.
- Beats can only be sealed by whoever runs this server. What stops the
  operator sealing a stale tick is that the tick is timestamped and public:
  sealing round N long after round N happened widens the window and shows.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec        public   what this is, how to verify it yourself
  GET  latest      public   the most recent beat sealed
  GET  ticks       public   recent beats
  GET  window      public   ?block= or ?receipt= - the two-sided window
  GET  verify      public   ?round= - what we sealed, and where to check it
  GET  status      public   cadence, coverage, mean window
  POST beat        keyed    fetch a tick now and seal it
  POST source      keyed    add a beacon reading fetched elsewhere (air-gap)
"""

import json
import time
import sqlite3
import threading
import urllib.request
import urllib.error

VERSION = "1.3.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "latest"),
    ("GET", "ticks"),
    ("GET", "window"),
    ("GET", "verify"),
    ("GET", "status"),
}

# ---------------------------------------------------------------------
# Beacon sources. Fixed hosts only - this is an allowlist, not a fetcher.
# ---------------------------------------------------------------------
# Each source: name, url, cadence in seconds, and a parser returning
# (round, value, source_time_or_None).

BEACON_HOSTS = {
    "api.drand.sh",
    "drand.cloudflare.com",
    "mempool.space",
}

FETCH_TIMEOUT = 8
MAX_BODY = 65536

BEAT_SECONDS = 300          # one beat every five minutes
AUTO_BEAT = True
MIN_BEAT_GAP = 60           # refuse to beat more often than this

_timer_lock = threading.Lock()
_timer_started = False
_beat_runs = 0
_beat_last = None
_beat_last_error = None


def _parse_drand(raw):
    d = json.loads(raw)
    rnd = int(d["round"])
    val = str(d["randomness"])
    if not val or len(val) < 32:
        raise ValueError("drand randomness missing or too short")
    return rnd, val, None


def _parse_btc_tip(raw):
    val = raw.strip()
    if len(val) != 64 or any(c not in "0123456789abcdefABCDEF" for c in val):
        raise ValueError("bitcoin tip hash not a 64-char hex string")
    return None, val.lower(), None


SOURCES = [
    {
        "name": "drand-quicknet",
        "url": "https://api.drand.sh/v2/beacons/quicknet/rounds/latest",
        "cadence_seconds": 3,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/v2/beacons/quicknet/rounds/{round}",
        "note": "League of Entropy public randomness beacon, quicknet chain",
    },
    {
        "name": "drand-default",
        "url": "https://api.drand.sh/public/latest",
        "cadence_seconds": 30,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/public/{round}",
        "note": "League of Entropy public randomness beacon, default chain",
    },
    {
        "name": "bitcoin-tip",
        "url": "https://mempool.space/api/blocks/tip/hash",
        "cadence_seconds": 600,
        "parse": _parse_btc_tip,
        "verify_url": "https://mempool.space/block/{value}",
        "note": "Bitcoin chain tip - slower, but the hardest to influence",
    },
]

VOCABULARY = {
    "floor": (
        "The record was created after this beat, because the chain is "
        "append-only and the record sits after a block containing a value "
        "that did not exist before the beat."
    ),
    "ceiling": (
        "The record was created before this beat, because the record sits "
        "before it in an append-only chain."
    ),
    "window": (
        "The span between floor and ceiling. The record can have been "
        "created at any moment inside it and no moment outside it. Smaller "
        "is stronger. This is a measurement, not a claim."
    ),
    "open": (
        "There is a floor but no ceiling yet: the next beat has not been "
        "sealed. Reported as open rather than closed. It closes on the "
        "next beat, and nothing about the record changes when it does."
    ),
    "unfloored": (
        "The record predates the first beat ever sealed. It has no floor "
        "from this module. Its ceiling still holds."
    ),
}

WHAT_THIS_PROVES = (
    "A window, not a truth. Inside the window the record could have been "
    "created at any instant. Outside it, it could not have been created at "
    "all. It says nothing about whether the record's contents are correct."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS heartbeat_tick (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source       TEXT NOT NULL,
        beacon_round INTEGER,
        value        TEXT NOT NULL,
        fetched_at   REAL NOT NULL,
        cadence      INTEGER,
        chain_rowid  INTEGER,
        audit_hash   TEXT,
        note         TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hb_rowid ON heartbeat_tick(chain_rowid)",
    "CREATE INDEX IF NOT EXISTS idx_hb_round ON heartbeat_tick(source, beacon_round)",
]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        # diagnostic columns, added without breaking an existing table
        cur.execute("PRAGMA table_info(heartbeat_tick)")
        have = [r[1] for r in cur.fetchall()]
        for col in ("seal_shape", "seal_error"):
            if col not in have:
                try:
                    cur.execute("ALTER TABLE heartbeat_tick ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass
        conn.commit()


def _host_of(url):
    try:
        rest = url.split("://", 1)[1]
    except IndexError:
        return ""
    return rest.split("/", 1)[0].split(":", 1)[0].lower()


def _fetch(url):
    if not url.startswith("https://"):
        raise ValueError("https only")
    host = _host_of(url)
    if host not in BEACON_HOSTS:
        raise ValueError("host not on the beacon allowlist: %s" % host)
    req = urllib.request.Request(url, headers={"User-Agent": "aileash-heartbeat/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        return r.read(MAX_BODY).decode("utf-8", "replace")


def _read_tick(fetcher=None):
    """Try each source in order. Returns dict or raises."""
    fetcher = fetcher or _fetch
    errors = []
    for src in SOURCES:
        try:
            raw = fetcher(src["url"])
            rnd, val, _ = src["parse"](raw)
            return {
                "source": src["name"],
                "beacon_round": rnd,
                "value": val,
                "cadence": src["cadence_seconds"],
                "note": src["note"],
            }
        except Exception as e:
            errors.append("%s: %s" % (src["name"], e))
    raise RuntimeError("no beacon reachable | " + " | ".join(errors))


def _seal(ctx, action, payload):
    """Seal through the host's seal().

    Confirmed from server.py: seal(event, result, ts, api_key=None) where
    EVENT IS A DICT carrying user_id (it is subscripted inside), and the
    return is (audit_hash, block_index, key_seq). So the block position
    comes back directly and does not have to be guessed from MAX(rowid).

    Returns (ok, shape, error, audit_hash, block_index).
    """
    fn = ctx.get("seal")
    if fn is None:
        return False, None, "ctx has no seal function", None, None

    ts = time.time()
    event = {
        "user_id": "heartbeat",
        "action": action,
        "amount": 0,
        "country": "UK",
        "device_id": "heartbeat",
        "anomaly": 0,
        "device_risk": 0,
    }
    result = dict(payload)
    result.setdefault("decision", "BEACON_SEALED")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)

    attempts = [
        ("seal(event_dict, result, ts)", lambda: fn(event, result, ts)),
        ("seal(event_dict, result, ts, None)", lambda: fn(event, result, ts, None)),
        ("seal(event_dict, result)", lambda: fn(event, result)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            out = call()
        except Exception as e:
            errors.append("%s -> %s: %s" % (shape, type(e).__name__, e))
            continue
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return True, shape, None, h, idx
    return False, None, " | ".join(errors), None, None


def _audit_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    return cur.fetchone() is not None


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for name in ("audit_hash", "hash", "block_hash"):
        if name in c:
            return name
    return None


def _latest_rowid(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(rowid) FROM audit_log")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def _backfill(conn, lock, tick_id):
    """After a seal, learn which chain row it landed on."""
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        row = cur.fetchone()
        rid = row[0] if row and row[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute(
            "UPDATE heartbeat_tick SET chain_rowid=?, audit_hash=? WHERE id=?",
            (rid, h, tick_id),
        )
        conn.commit()
    return rid, h


# ---------------------------------------------------------------------
# the beat
# ---------------------------------------------------------------------

def _do_beat(ctx, fetcher=None, forced=False):
    global _beat_runs, _beat_last, _beat_last_error
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    with lock:
        cur = conn.cursor()
        cur.execute("SELECT fetched_at FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if row and not forced and (time.time() - row[0]) < MIN_BEAT_GAP:
        return {"beat": False, "reason": "too_soon", "min_gap_seconds": MIN_BEAT_GAP}, 429

    tick = _read_tick(fetcher)
    now = time.time()

    event = "heartbeat_beat"
    result = {
        "kind": "beacon_tick",
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "fetched_at": now,
        "note": (
            "Unpredictable public value. Any block after this one in this "
            "append-only chain was created after this tick existed."
        ),
    }

    with lock:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO heartbeat_tick (source, beacon_round, value, fetched_at,"
            " cadence, note) VALUES (?,?,?,?,?,?)",
            (tick["source"], tick["beacon_round"], tick["value"], now,
             tick["cadence"], tick["note"]),
        )
        tick_id = cur.lastrowid
        conn.commit()

    ok, shape, err, h, rid = _seal(ctx, event, result)
    if ok and (rid is None or h is None):
        try:
            rid2, h2 = _backfill(conn, lock, tick_id)
            rid = rid if rid is not None else rid2
            h = h if h is not None else h2
        except Exception:
            pass
    with lock:
        conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                     " chain_rowid=?, audit_hash=? WHERE id=?",
                     (shape, err, rid, h, tick_id))
        conn.commit()

    _beat_runs += 1
    _beat_last = now
    _beat_last_error = err

    return {
        "beat": True,
        "sealed_into_chain": bool(ok and rid),
        "seal_shape": shape,
        "seal_error": err,
        "tick_id": tick_id,
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "sealed_at_chain_rowid": rid,
        "audit_hash": h,
        "verify_yourself": _verify_url(tick["source"], tick["beacon_round"], tick["value"]),
    }, 200


def _verify_url(source, rnd, value):
    for s in SOURCES:
        if s["name"] == source:
            u = s["verify_url"]
            if rnd is not None:
                return u.replace("{round}", str(rnd)).replace("{value}", str(value))
            return u.replace("{value}", str(value))
    return None


def _start_timer(ctx):
    global _timer_started
    with _timer_lock:
        if _timer_started or not AUTO_BEAT:
            return
        _timer_started = True

    for t in threading.enumerate():
        if t.name == "heartbeat" and t.is_alive():
            return

    def loop():
        global _beat_last_error
        while True:
            try:
                _do_beat(ctx)
            except Exception as e:
                _beat_last_error = str(e)
            time.sleep(BEAT_SECONDS)

    t = threading.Thread(target=loop, name="heartbeat", daemon=True)
    t.start()


# ---------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------

def _find_rowid(conn, block, receipt):
    if block is not None:
        try:
            return int(block)
        except (TypeError, ValueError):
            return None
    if receipt:
        hcol = _hash_col(conn)
        if not hcol:
            return None
        cur = conn.cursor()
        cur.execute("SELECT rowid FROM audit_log WHERE %s=? LIMIT 1" % hcol, (receipt,))
        r = cur.fetchone()
        return r[0] if r else None
    return None


def _window_for(conn, rowid):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid<=?"
        " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
    floor = cur.fetchone()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
        " ORDER BY chain_rowid ASC LIMIT 1", (rowid,))
    ceil = cur.fetchone()
    return floor, ceil


def _beat_obj(row, err=None, shape=None):
    if not row:
        return None
    out = {
        "source": row[1],
        "round": row[2],
        "value": row[3],
        "at": _iso(row[4]),
        "at_epoch": row[4],
        "chain_rowid": row[5],
        "audit_hash": row[6],
        "verify_yourself": _verify_url(row[1], row[2], row[3]),
    }
    if row[5] is None:
        out["in_chain"] = False
        out["warning"] = ("This beat is NOT sealed into the chain, so it is "
                          "not a floor for anything. See seal_error.")
        if err:
            out["seal_error"] = err
    else:
        out["in_chain"] = True
        if shape:
            out["seal_shape"] = shape
    return out


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes %d seconds" % (s // 60, s % 60)
    return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]

    if not _audit_table(conn):
        return {"error": "audit_log_missing"}, 500

    _ensure(conn, lock)
    _start_timer(ctx)

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "latest":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return {"beats": 0, "message": "no beat sealed yet"}, 200
        age = time.time() - row[4]
        return {
            "latest_beat": _beat_obj(row),
            "seconds_since": round(age, 1),
            "open_window_so_far": _human(age),
            "meaning": (
                "Anything sealed since this beat has this beat as its floor "
                "and no ceiling until the next beat."
            ),
        }, 200

    if method == "GET" and action == "ticks":
        try:
            limit = min(int(data.get("limit", 25)), 200)
        except (TypeError, ValueError):
            limit = 25
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash, seal_error, seal_shape FROM heartbeat_tick"
            " ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return {
            "count": len(rows),
            "beats": [_beat_obj(r, r[7], r[8]) for r in rows],
            "cadence_target_seconds": BEAT_SECONDS,
        }, 200

    if method == "GET" and action == "window":
        rowid = _find_rowid(conn, data.get("block"), data.get("receipt"))
        if rowid is None:
            return {"error": "block_or_receipt_required",
                    "usage": "/x/heartbeat/window?block=846 or ?receipt=<audit_hash>"}, 400

        floor, ceil = _window_for(conn, rowid)
        out = {
            "block": rowid,
            "floor": _beat_obj(floor),
            "ceiling": _beat_obj(ceil),
            "what_this_proves": WHAT_THIS_PROVES,
            "vocabulary": VOCABULARY,
        }

        if floor and ceil:
            width = ceil[4] - floor[4]
            out["state"] = "closed"
            out["window_seconds"] = round(width, 1)
            out["window"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s and before %s. Window: %s."
                % (rowid, _iso(floor[4]), _iso(ceil[4]), _human(width))
            )
        elif floor:
            width = time.time() - floor[4]
            out["state"] = "open"
            out["window_seconds_so_far"] = round(width, 1)
            out["window_so_far"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s. The ceiling is not sealed "
                "yet, so the window is open." % (rowid, _iso(floor[4]))
            )
        elif ceil:
            out["state"] = "unfloored"
            out["statement"] = (
                "Block %d predates the first beat, so it has no floor from "
                "this module. It was created before %s." % (rowid, _iso(ceil[4]))
            )
        else:
            out["state"] = "no_beats"
            out["statement"] = "No beats have been sealed, so no window exists."

        out["external_ceiling"] = {
            "note": (
                "A second, independent ceiling comes from OpenTimestamps. "
                "Anchoring is per proof and has its own pending/confirmed "
                "state."
            ),
            "where": "/x/ots/status",
        }
        return out, 200

    if method == "GET" and action == "verify":
        rnd = data.get("round")
        if rnd is None:
            return {"error": "round_required"}, 400
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick WHERE beacon_round=?"
            " ORDER BY id DESC LIMIT 1", (rnd,))
        row = cur.fetchone()
        if not row:
            return {"error": "round_not_sealed", "round": rnd}, 404
        return {
            "sealed": _beat_obj(row),
            "how_to_verify": [
                "Fetch the round from the beacon operator at the url above.",
                "Compare its randomness with the value we sealed. They must match.",
                "Confirm the beat's audit_hash is in our chain at /api/verify-chain.",
                "Nothing in these three steps requires our cooperation.",
            ],
            "we_do_not_verify_the_signature": (
                "drand signs each round with BLS, which this server does not "
                "implement. We record the round and value verbatim. The "
                "operator's own endpoint is the authority, not us."
            ),
        }, 200

    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(fetched_at), MAX(fetched_at) FROM heartbeat_tick")
        n, first, last = cur.fetchone()
        cur.execute(
            "SELECT fetched_at FROM heartbeat_tick WHERE chain_rowid IS NOT NULL"
            " ORDER BY chain_rowid ASC")
        times = [r[0] for r in cur.fetchall()]
        gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        mean = sum(gaps) / len(gaps) if gaps else None
        widest = max(gaps) if gaps else None
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        tip = cur.fetchone()[0] or 0
        cur.execute("SELECT MIN(chain_rowid) FROM heartbeat_tick WHERE chain_rowid IS NOT NULL")
        firstrow = cur.fetchone()[0]
        covered = (tip - firstrow) if firstrow else 0
        return {
            "version": VERSION,
            "beats_sealed": n,
            "first_beat": _iso(first),
            "latest_beat": _iso(last),
            "cadence_target_seconds": BEAT_SECONDS,
            "auto_beat": AUTO_BEAT,
            "timer_running": _timer_started,
            "beat_runs_this_process": _beat_runs,
            "last_error": _beat_last_error,
            "beats_not_in_chain": _orphans(conn),
            "last_seal_error": _last_seal_error(conn),
            "last_seal_shape": _last_seal_shape(conn),
            "mean_window_seconds": round(mean, 1) if mean else None,
            "mean_window": _human(mean),
            "widest_window_seconds": round(widest, 1) if widest else None,
            "widest_window": _human(widest),
            "records_with_a_floor": covered,
            "chain_height": tip,
            "honest_note": (
                "Mean window is the average distance between beats. It is the "
                "typical amount of room a record has. Widest is the worst "
                "case, which is the number that actually matters."
            ),
        }, 200

    if method == "POST" and action == "beat":
        try:
            return _do_beat(ctx, forced=bool(data.get("force")))
        except Exception as e:
            return {"beat": False, "error": "beacon_unreachable", "detail": str(e)}, 503

    if method == "POST" and action == "source":
        # For an engine with no outbound network. The operator hands it a
        # reading fetched elsewhere. Sealed exactly as supplied and marked.
        val = data.get("value")
        src = data.get("source") or "supplied"
        rnd = data.get("round")
        if not val or len(str(val)) < 32:
            return {"error": "value_required", "note": "at least 32 characters"}, 400
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO heartbeat_tick (source, beacon_round, value,"
                " fetched_at, cadence, note) VALUES (?,?,?,?,?,?)",
                (src, rnd, str(val), now, None,
                 "supplied by operator, not fetched by this server"),
            )
            tick_id = cur.lastrowid
            conn.commit()
        ok, shape, err, h, rid = _seal(ctx, "heartbeat_beat", {
            "kind": "beacon_tick_supplied",
            "source": src, "round": rnd, "value": str(val), "fetched_at": now,
            "note": ("Supplied by the operator rather than fetched here. The "
                     "floor it gives is only as good as the reader's trust in "
                     "that source, and it is marked so nobody mistakes it."),
        })
        if ok and (rid is None or h is None):
            try:
                rid2, h2 = _backfill(conn, lock, tick_id)
                rid = rid if rid is not None else rid2
                h = h if h is not None else h2
            except Exception:
                pass
        with lock:
            conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                         " chain_rowid=?, audit_hash=? WHERE id=?",
                         (shape, err, rid, h, tick_id))
            conn.commit()
        return {"beat": True, "supplied": True, "tick_id": tick_id,
                "sealed_at_chain_rowid": rid, "audit_hash": h,
                "marked": "supplied by operator, not fetched by this server"}, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "latest", "ticks", "window", "verify",
                        "status", "beat", "source"]}, 404


def _orphans(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick WHERE chain_rowid IS NULL")
        return cur.fetchone()[0]
    except Exception:
        return None


def _last_seal_error(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_error FROM heartbeat_tick WHERE seal_error IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _last_seal_shape(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_shape FROM heartbeat_tick WHERE seal_shape IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _spec():
    return {
        "module": "heartbeat",
        "version": VERSION,
        "what_it_is": (
            "A clock nobody can wind. Public beacon values are sealed into "
            "the chain on a cadence. Because a beacon value cannot be known "
            "before its tick, and because the chain is append-only, every "
            "record between two beats has a provable earliest and latest "
            "moment of creation."
        ),
        "why_a_clock_alone_fails": (
            "Anyone can write down what a clock will read tomorrow. A clock "
            "reading proves nothing about when it was written down. A beacon "
            "value cannot be written down in advance by anyone."
        ),
        "the_interleave": (
            "Decisions are not stamped individually. One beat every few "
            "minutes gives a floor to everything after it and a ceiling to "
            "everything before the next one. No change to the decision path "
            "and no added latency."
        ),
        "sources": [
            {"name": s["name"], "cadence_seconds": s["cadence_seconds"],
             "note": s["note"], "url": s["url"]} for s in SOURCES
        ],
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It bounds when a record can have been made. It says nothing "
            "about whether the record is correct.",
            "drand signatures are BLS and are not verified here. The round "
            "and value are recorded verbatim and are re-fetchable by anyone "
            "from the beacon operator.",
            "A record after the newest beat has an open window until the "
            "next beat is sealed.",
            "Beats sealed from a value the operator supplied by hand rather "
            "than fetched are marked as such and are weaker.",
            "A wide window is reported wide. The number is a measurement of "
            "our own cadence, and it can embarrass us.",
        ],
        "routes": {
            "GET /x/heartbeat/spec": "this document",
            "GET /x/heartbeat/latest": "most recent beat and the open window so far",
            "GET /x/heartbeat/ticks?limit=": "recent beats",
            "GET /x/heartbeat/window?block=|?receipt=": "two-sided window for a record",
            "GET /x/heartbeat/verify?round=": "what we sealed and where to check it",
            "GET /x/heartbeat/status": "cadence, coverage, mean and widest window",
            "POST /x/heartbeat/beat": "keyed - fetch and seal now",
            "POST /x/heartbeat/source": "keyed - seal a reading fetched elsewhere",
        },
    }

```


## `modules/held.py`

145 lines, 5162 bytes

```python
"""
modules/held.py  v1.0  -  the tips sebbi.pro holds for other chains

Every time a peer submits its tip, sebbi.pro seals the observation into its
own chain as a block under user_id "wit:<peer>", with the peer's tip inside.
Those blocks are already public in the walk. This module lists them per
peer, so another chain can point a verifier at sebbi.pro as its witness and
have a machine confirm it.

Reads only. Seals nothing, writes nothing, creates no tables. All public.

Routes:
  https://sebbi.pro/x/held/status
  https://sebbi.pro/x/held/peers
  https://sebbi.pro/x/held/tips?peer=mir
"""

import json
import re
import time

VERSION = "1.0"
BASE = "https://sebbi.pro/x/held/"
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "peers"),
          ("GET", "tips")}

_PEER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _q(data, name, default=None):
    v = (data or {}).get(name, default)
    if isinstance(v, list):
        v = v[0] if v else default
    return v


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _peers(ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT user_id, COUNT(*), MAX(id), MAX(ts) FROM audit_log "
            "WHERE user_id LIKE 'wit:%' GROUP BY user_id").fetchall()
    out = []
    for uid, n, last_idx, last_ts in rows:
        name = str(uid)[4:]
        out.append({"peer": name, "tips_held": n,
                    "last_block_index": last_idx,
                    "last_observed_at": _iso(last_ts),
                    "list": BASE + "tips?peer=" + name})
    out.sort(key=lambda r: -(r["tips_held"] or 0))
    return {"ok": True, "holder": "sebbi.pro", "count": len(out),
            "peers": out}, 200


def _tips(data, ctx):
    peer = str(_q(data, "peer", "") or "").strip().lower()
    if not _PEER_RE.match(peer):
        return {"ok": False, "error": "peer_required",
                "example": BASE + "tips?peer=mir",
                "peers": BASE + "peers"}, 400
    try:
        limit = max(1, min(MAX_LIMIT, int(_q(data, "limit", DEFAULT_LIMIT))))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            ("wit:" + peer, limit)).fetchall()
    tips = []
    for idx, ts, h, rj in rows:
        try:
            res = json.loads(rj)
        except Exception:
            res = {}
        tip = str(res.get("peer_tip") or "").lower()
        if not re.match(r"^[0-9a-f]{64}$", tip):
            continue
        tips.append({
            "peer_tip": tip,
            "observed_at": _iso(ts),
            "liveness": res.get("liveness"),
            "sealed_in_block": idx,
            "sealed_block_hash": h,
            "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
        })
    return {
        "ok": True,
        "holder": "sebbi.pro",
        "peer": peer,
        "count": len(tips),
        "newest_first": True,
        "tips": tips,
        "what_this_proves": (
            "sebbi.pro recorded each of these tips from %s and sealed the "
            "observation into its own public chain. Open check_block to see "
            "the sealed block, recompute its hash, and confirm peer_tip is "
            "inside it. sebbi.pro is run independently of %s and cannot be "
            "made to rewrite these blocks by %s." % (peer, peer, peer)),
        "what_this_does_not_prove": (
            "That the tip was correct when submitted - only that this is the "
            "tip sebbi.pro was shown, and when."),
    }, 200


def _status():
    return {"ok": True, "module": "held", "version": VERSION,
            "what": "Tips sebbi.pro holds for other chains, from its own "
                    "sealed witness blocks.",
            "routes": {"peers": BASE + "peers",
                       "tips": BASE + "tips?peer=mir",
                       "status": BASE + "status"},
            "use_as_witness": "In an AI Integrity Declaration, set a "
                              "witness tip_endpoint to " + BASE +
                              "tips?peer=<your peer name>. The checker at "
                              "https://sebbi.pro/x/integrity/check then "
                              "confirms sebbi.pro holds your tip."}


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action in ("status", "spec", ""):
            return _status(), 200
        if method == "GET" and action == "peers":
            return _peers(ctx)
        if method == "GET" and action == "tips":
            return _tips(data, ctx)
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": []}, 404
    except Exception as exc:
        return {"ok": False, "error": "held_failed",
                "detail": str(exc)[:200]}, 500

```


## `modules/integrity.py`

1487 lines, 65650 bytes

```python
"""
modules/integrity.py  v1.4.4  -  the AI Integrity Declaration, a public checker,
                              and a sealed public register of verdicts

Serves the open standard that rates every AI deployment from L0_DIARY
(no checkable record) up to L4_OVERSIGHT_VERIFIED, and checks any domain
against it. Reads only. Seals nothing, writes nothing, creates no tables.
Every route is public.

Routes:
  https://sebbi.pro/x/integrity/status                    what this is
  https://sebbi.pro/x/integrity/declaration               the standard, as JSON
  https://sebbi.pro/x/integrity/self                      sebbi.pro's own declaration
  https://sebbi.pro/x/integrity/check?domain=example.com  rate any domain
  https://sebbi.pro/x/integrity/register                  every sealed verdict

v1.4: THE CHECKER'S OWN VERDICTS ARE NOW EVIDENCE.
Every fresh verdict is sealed into the sebbi.pro chain as a public block,
so a rating cannot be quietly changed later - not by the domain rated, and
not by sebbi.pro.

v1.4.3: THE REQUEST IS SEALED TOO, BEFORE THE CHECK RUNS.
A sealed verdict proves what the checker said, not what it left unsaid: an
inconvenient result could simply go unsealed, and from outside, silence and
never-asked look the same. Now the request is sealed first. A domain that
was asked about and has no verdict after it shows up in the register as
exactly that. (Raised by Richard Whitney, MIRegistry.) The register lists the latest sealed verdict per domain,
each with the block that holds it. A checker that rates others by whether
their records can be altered now holds its own ratings to the same rule.

HOW THE CHECKER DECIDES
It looks for a declaration at https://<domain>/.well-known/ai-integrity.json,
then https://<domain>/x/integrity/self. None found: L0_DIARY.
It never takes the declaration's word. It walks the declared chain and
recomputes every public block itself, asks each declared witness for its
tip, and opens each anchor proof. A level is awarded only when every check
that level needs has passed. Claiming more than that is OVERCLAIMED.

Human-oversight checks (INV-005, INV-006) cannot be tested from outside yet,
so this checker never awards L4. It says so rather than guessing.

SAFETY
The checker fetches addresses taken from other people's declarations, so
it only fetches https on port 443, refuses redirects, refuses any host that
resolves to a private, loopback or internal address, caps every response
size and every timeout, and caps the number of fetches per check.
"""

import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.4.4"
BASE = "https://sebbi.pro/x/integrity/"

PUBLIC = {("GET", "status"), ("GET", "declaration"), ("GET", "spec"),
          ("GET", "self"), ("GET", "check"), ("GET", "register")}

# ---------------------------------------------------------------- the standard

DECLARATION = json.loads(r'''{
  "spec": "ai-integrity-declaration",
  "version": "1.0.4",
  "declaration_id": "DEC-2026-AI-INTEGRITY",
  "status": "open_standard",
  "published": "2026-09-19",
  "issuer": {
    "name": "Monop Content",
    "product": "sebbi.pro",
    "url": "https://sebbi.pro"
  },
  "principle": "A record kept only by the party it describes is a diary, not evidence. Any AI deployment can be checked against this standard by anyone, without an account, a key, or permission.",
  "scope": "Autonomous agents and AI systems that make or support decisions affecting people, money, access or safety.",
  "maps_to": [
    {
      "framework": "EU AI Act",
      "provisions": [
        "Article 12 record-keeping",
        "Article 14 human oversight"
      ]
    },
    {
      "framework": "UK Online Safety Act 2023",
      "provisions": [
        "record-keeping and review duties"
      ]
    },
    {
      "framework": "ICO Age Appropriate Design Code",
      "provisions": [
        "data minimisation",
        "transparency"
      ]
    }
  ],
  "related": {
    "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
    "relationship": "The Ordering Test lists which checks a vendor supports and which anyone can run without an account. This declaration turns those checks into levels, so every AI deployment gets a rating whether or not it publishes."
  },
  "discovery": {
    "paths": [
      "/.well-known/ai-integrity.json",
      "/x/integrity/self"
    ],
    "rule": "Every AI deployment is rated. A verifier looks for a declaration at each path in order, over HTTPS, on the deployment's own domain. A deployment with no declaration at any of these paths is rated L0_DIARY. Absence is itself the result.",
    "absence_verdict": "L0_DIARY"
  },
  "levels": {
    "L0_DIARY": {
      "badge": "GREY",
      "meaning": "No public, independently checkable record. The operator's word is the only evidence.",
      "requires": []
    },
    "L1_SEALED": {
      "badge": "BRONZE",
      "meaning": "Every decision is sealed into a public append-only chain that anyone can walk and recompute.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-007"
      ]
    },
    "L2_WITNESSED": {
      "badge": "SILVER",
      "meaning": "Independent parties hold the chain's fingerprints, so the operator cannot rewrite history unnoticed.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-007"
      ]
    },
    "L3_ANCHORED": {
      "badge": "GOLD",
      "meaning": "The chain is also anchored to a public timestamp no single party controls.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-007"
      ]
    },
    "L4_OVERSIGHT_VERIFIED": {
      "badge": "GOLD_LIVE_VERIFIED",
      "meaning": "Human oversight is itself provable: reviewers commit before seeing the machine, and rubber-stamping is detected.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-005",
        "INV-006",
        "INV-007"
      ]
    }
  },
  "invariants": {
    "INV-001-SEALED-CHAIN": {
      "requirement": "Every decision is sealed at the moment it is made, with what it rested on, into an append-only hash chain.",
      "test": "Fetch the declared walk endpoint. Starting from genesis, recompute every public block from the served preimage and confirm each block names its parent.",
      "pass": "All public blocks recompute; all links unbroken; the tip reached equals the tip published.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-002-FINGERPRINTS-ONLY": {
      "requirement": "Raw prompts, documents and personal data stay with their owner. Only fingerprints are published. Short or guessable personal values are salted or keyed before hashing.",
      "test": "Inspect public blocks. No raw personal data, secrets or credentials appear. The declaration states the hashing method for personal values.",
      "pass": "No raw personal data in any public block; method declared.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-003-INDEPENDENT-WITNESS": {
      "requirement": "At least one party independent of the operator holds the chain's tip. The declaration states how many independent parties would have to collude or fail at the same time for the history to be rewritten unnoticed.",
      "independence": "A witness is independent when the operator cannot alter, delete or withhold the witness's record of the tip. Payment does not by itself break independence; control does. Any commercial relationship between operator and witness is disclosed in the declaration.",
      "witness_strength": {
        "sealed": "The witness sealed the tip inside its own hash chain, and the checker recomputed that block and found the tip in it.",
        "bound": "The witness recorded the tip against a position in its own anchored chain, which dates the record but does not seal it.",
        "listed": "The witness publishes the tip, with nothing in its own chain binding the record.",
        "note": "Strength is reported for every passing witness. It does not yet change the level; it will be graded from 1.1.0. A witness can climb from listed to bound to sealed, and the declaration shows which it is."
      },
      "test": "Query each declared witness. Its recorded tip must appear in the operator's chain at the position it claims.",
      "pass": "At least one independent witness confirms; the collusion threshold is disclosed.",
      "fail_verdict": "L1_SEALED"
    },
    "INV-004-PUBLIC-TIME-ANCHOR": {
      "requirement": "Chain tips are anchored to a public timestamp no single party controls, such as OpenTimestamps on Bitcoin.",
      "test": "Verify the anchor proof offline against the tip it names.",
      "pass": "Proof commits to a tip present in the chain.",
      "fail_verdict": "L2_WITNESSED"
    },
    "INV-005-COMMIT-BEFORE-REVEAL": {
      "requirement": "Where a human reviews an AI decision, the reviewer's verdict is sealed before the machine's verdict is shown to them.",
      "test": "For each reviewed case, the reviewer's sealed commitment sits in an earlier block than the reveal of the machine verdict.",
      "pass": "Every reviewed case shows commit before reveal.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-006-ANTI-RUBBER-STAMP": {
      "requirement": "Review behaviour that indicates rubber-stamping is detected and sealed.",
      "parameters": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98,
        "window": "rolling 30 days, per reviewer"
      },
      "test": "Any reviewer approving in under minimum_review_seconds, or agreeing with the machine more often than maximum_agreement_rate across the window, has a flag sealed into the chain.",
      "pass": "Flags are raised and sealed whenever the thresholds are crossed; the thresholds in use are declared.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-007-DISCLOSED-DISCONTINUITY": {
      "requirement": "Where the chain is reset, or the meaning of a field or the referent of an identifier changes after records using it have been sealed, the change is sealed into the record itself with the date it took effect. Records sealed under the earlier meaning remain valid under that meaning and are never silently repaired.",
      "test": "Every discontinuity or change of meaning is disclosed either as a block sealed in the chain, or in the declaration with the kind of change and the evidence a verifier can use to detect it. Where the checker can detect a discontinuity itself (for example records sealed long after the window they cover), an undisclosed one fails.",
      "detection_rule": "A discontinuity that is detected rather than asserted states the rule that detected it (for example \"createdAt - rangeEnd > 2 hours\"), so any verifier can recount it and get the same number. Where a rule is declared, the checker applies that rule rather than its own and reports whether it reproduces the declared count. In 1.0.3 a missing rule is reported; from 1.1.0 it fails.",
      "detection_rule_location": "Inside the discontinuity it describes: discontinuities[].detection_rule, beside that entry's own counts (checkpoints, through_seq). A rule anywhere else is not read.",
      "pass": "Every discontinuity is disclosed in the chain.",
      "fail_verdict": "L0_DIARY"
    }
  },
  "verifier_rules": [
    "Never accept an operator's own statement that its record is valid. Recompute.",
    "A verifier assigns the highest level whose every required invariant passes.",
    "If a declaration claims a higher level than verification supports, the verdict is OVERCLAIMED, shown alongside the verified level.",
    "A declaration that cannot be fetched, or cannot be parsed, is rated L0_DIARY."
  ],
  "declaration_template": {
    "spec": "ai-integrity-declaration",
    "version": "1.0.0",
    "organisation": "",
    "system": "",
    "claimed_level": "",
    "chain": {
      "walk_endpoint": "",
      "genesis_hash": "",
      "seal_method_url": ""
    },
    "personal_data_hashing": "",
    "witnesses": [
      {
        "name": "",
        "tip_endpoint": ""
      }
    ],
    "collusion_threshold": 0,
    "anchor": {
      "method": "",
      "proof_endpoint": ""
    },
    "oversight": {
      "commit_before_reveal": false,
      "anti_rubber_stamp": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98
      }
    },
    "discontinuities": [
      {
        "date": "",
        "disclosure_block": "",
        "kind": "",
        "detail": ""
      }
    ],
    "known_gaps": []
  },
  "not_yet_rated": {
    "availability": "Every level answers 'has this been altered'. None yet answers 'will this still be served'. Until a level for availability is defined, declare availability limits in known_gaps."
  },
  "reference_implementation": {
    "name": "sebbi.pro",
    "walk": "https://sebbi.pro/x/walk/status",
    "method": "https://sebbi.pro/x/walk/spec",
    "genesis": "https://sebbi.pro/x/walk/genesis",
    "discontinuity_example": "https://sebbi.pro/x/walk/block?index=2013"
  },
  "changelog": [
    {
      "version": "1.0.1",
      "date": "2026-09-20",
      "change": "Added /x/integrity/self as a second discovery path, for deployments whose server cannot serve /.well-known. Added the public checker."
    },
    {
      "version": "1.0.4",
      "date": "2026-09-20",
      "change": "Fixed where detection_rule lives: inside its discontinuity, beside the counts it produces. Where a rule is declared, the checker now reports the count under that rule first and its own default second, instead of leading with its default. Check requests are now sealed before the check runs, so a request with no verdict after it is visible in the register. Both raised by Richard Whitney (MIRegistry)."
    },
    {
      "version": "1.0.3",
      "date": "2026-09-20",
      "change": "detection_rule for detected discontinuities, applied by the checker to recount the declared figure. Witness strength (sealed, bound, listed) reported for every witness. Both raised by Richard Whitney (MIRegistry). Every fresh checker verdict is now sealed into the sebbi.pro chain and listed in a public register, so ratings themselves cannot be quietly altered."
    },
    {
      "version": "1.0.2",
      "date": "2026-09-20",
      "change": "Defined witness independence (control, not payment). INV-007 accepts discontinuities disclosed in the declaration with detection evidence, and fails undisclosed ones the checker can detect. Added known_gaps and the unrated availability axis. All three raised by Richard Whitney (MIRegistry) while writing the first external declaration."
    }
  ],
  "public_checker": "https://sebbi.pro/x/integrity/check?domain=example.com",
  "public_register": "https://sebbi.pro/x/integrity/register"
}''')

_CANONICAL = json.dumps(DECLARATION, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False)
DECLARATION_SHA256 = hashlib.sha256(_CANONICAL.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------- our own declaration
#
# sebbi.pro's own claim. Kept honest: it claims only what the checker can
# confirm today. To move up a level, add a witness below - an address run
# by someone else that returns the sebbi.pro tip they hold - and raise
# claimed_level only once the checker agrees.

SELF_WITNESSES = [
    {"name": "MIR (MIRegistry)",
     "tip_endpoint": "https://mir.events/v1/transparency/held/tips?peer=sebbi",
     "note": "MIR records each sebbi.pro tip it observes against its own "
             "anchored chain position and never refreshes an entry. As MIR "
             "states in its own payload, these observations are bound to an "
             "anchored MIR tip, not sealed inside MIR's merkle root."},
]

SELF = {
    "spec": "ai-integrity-declaration",
    "version": "1.0.3",
    "organisation": "Monop Content",
    "system": "sebbi.pro",
    "claimed_level": "L3_ANCHORED",
    "chain": {
        "walk_endpoint": "https://sebbi.pro/x/walk/blocks",
        "genesis_hash": "534f9e5cefb1a48566674911262151f34eedc1e6840a094d9465af4d846972c6",
        "seal_method_url": "https://sebbi.pro/x/walk/spec",
    },
    "personal_data_hashing": "Customer decisions are never published. Blocks sealed under a customer key, from non-public sources, or carrying anything secret-shaped are served without payload; only their hash and link are public.",
    "witnesses": SELF_WITNESSES,
    "collusion_threshold": 1,
    "collusion_note": "One: only witnesses a machine can verify are counted. Other chains witness sebbi.pro but do not yet publish a list the checker can read, so they are not counted.",
    "held_for_others": "https://sebbi.pro/x/held/peers",
    "anchor": {
        "method": "OpenTimestamps on Bitcoin",
        "proof_endpoint": "https://sebbi.pro/x/ots/latest_confirmed",
        "status_url": "https://sebbi.pro/x/ots/status",
        "note": "Tips are stamped hourly. proof_endpoint always serves the newest proof that is confirmed in Bitcoin and whose tip is a block in the current chain. Anchoring is not claimed until the checker verifies it.",
    },
    "oversight": {
        "commit_before_reveal": True,
        "demonstration": "https://sebbi.pro/x/demo/review",
        "anti_rubber_stamp": {"minimum_review_seconds": 1.5,
                              "maximum_agreement_rate": 0.98},
    },
    "discontinuities": [
        {"date": "2026-09-07", "disclosure_block": 2013, "kind": "chain_reset",
         "detail": "The chain restarted from genesis. The reset is sealed in block 2013; block indexes quoted before that date belong to the earlier chain."},
    ],
    "known_gaps": [
        "Availability: every level answers 'has this been altered', none yet answers 'will this still be served'. A reader currently depends on sebbi.pro continuing to serve these endpoints.",
        "Anchoring: tips are stamped to Bitcoin hourly and confirm a few hours later, so the newest hour or so rests on witnessing until its proof confirms.",
    ],
}

# ---------------------------------------------------------------- safe fetching

FETCH_TIMEOUT = 8
MAX_DECL_BYTES = 262144
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_FETCHES = 45
WALK_PAGE = 500
WALK_MAX_BLOCKS = 20000
CHECK_BUDGET_SECONDS = 60
CACHE_SECONDS = 600
USER_AGENT = "sebbi-integrity-checker/1.4.4 (+https://sebbi.pro/x/integrity/status)"

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home",
                     ".corp", ".intranet", ".arpa")

_cache = {}
_cache_lock = threading.Lock()
_running = threading.BoundedSemaphore(2)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code,
                                     "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _Budget(object):
    def __init__(self):
        self.fetches = 0
        self.deadline = time.time() + CHECK_BUDGET_SECONDS

    def spend(self):
        self.fetches += 1
        if self.fetches > MAX_FETCHES:
            raise RuntimeError("fetch limit reached")
        if time.time() > self.deadline:
            raise RuntimeError("time limit reached")


def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if "@" in d or ":" in d:
        return None
    d = d.rstrip(".")
    if not _HOST_RE.match(d):
        return None
    if d == "localhost" or d.endswith(_BLOCKED_SUFFIXES):
        return None
    return d


def _host_is_public(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "does not resolve"
    if not infos:
        return False, "does not resolve"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, "resolves to a non-public address"
    return True, None


def _safe_url(url):
    try:
        p = urllib.parse.urlsplit(str(url))
    except Exception:
        return None, "unreadable address"
    if p.scheme != "https":
        return None, "only https addresses are fetched"
    if p.port not in (None, 443):
        return None, "only port 443 is fetched"
    if p.username or p.password:
        return None, "addresses with credentials are refused"
    host = _clean_domain(p.hostname or "")
    if not host:
        return None, "not a public domain name"
    ok, why = _host_is_public(host)
    if not ok:
        return None, why
    return urllib.parse.urlunsplit(("https", host, p.path or "/", p.query, "")), None


def _fetch_raw(url, budget, max_bytes=MAX_DECL_BYTES, accept="application/json"):
    """Returns (bytes, error). Never raises."""
    safe, why = _safe_url(url)
    if not safe:
        return None, why
    try:
        budget.spend()
    except RuntimeError as exc:
        return None, str(exc)
    req = urllib.request.Request(safe, headers={
        "User-Agent": USER_AGENT, "Accept": accept})
    try:
        with _OPENER.open(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return None, "HTTP %s" % exc.code
    except Exception as exc:
        return None, "could not fetch (%s)" % exc.__class__.__name__
    if len(raw) > max_bytes:
        return None, "response too large"
    return raw, None


def _fetch_json(url, budget, max_bytes=MAX_DECL_BYTES, allow_text=False):
    """Returns (data, error). Never raises.

    allow_text: if the response is not JSON (an ordinary web page), return
    {"_text": <page text>} instead of an error, so a witness can publish its
    record as a normal page."""
    raw, err = _fetch_raw(url, budget, max_bytes)
    if err:
        return None, err
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text), None
    except Exception:
        if allow_text:
            return {"_text": text}, None
        return None, "not valid JSON"


# ---------------------------------------------------------------- checks

_HEX64 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
WITNESS_MAX_BYTES = 2 * 1024 * 1024
_SECRET_SHAPES = [
    ("api key", re.compile(r"\b(?:al|sb|se)_live_[0-9a-f]{16,}")),
    ("api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("cloud key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("access token", re.compile(r"\b(?:ghp|gho|xox[abp])[_-][A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]


_ZERO64 = "0" * 64
BACKFILL_HOURS = 6

_RULE_RE = re.compile(
    r"createdAt\s*-\s*rangeEnd\s*(>=|>)\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)


def _parse_rule(text):
    """'createdAt - rangeEnd > 2 hours' -> (op, seconds) or None."""
    m = _RULE_RE.search(str(text or ""))
    if not m:
        return None
    n = float(m.group(2))
    unit = m.group(3).lower()
    mult = 3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1
    return m.group(1), n * mult


def _recount(meta, op, seconds):
    count, through = 0, None
    for seq in sorted(meta):
        cp = meta[seq]
        c, r = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if c is None or r is None:
            continue
        lag = c - r
        if (lag >= seconds) if op == ">=" else (lag > seconds):
            count += 1
            through = seq
    return count, through


def _iso_ts(v):
    try:
        return time.mktime(time.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S")) \
            - time.timezone
    except Exception:
        return None


def _walk(endpoint, budget):
    """Walk a declared chain and recompute it.

    Two published formats are understood:
      blocks       the sebbi.pro walk format (https://sebbi.pro/x/walk/spec)
      checkpoints  the MIR checkpoint format (seq/tip/prevTip, newest first)
    The format is detected from what the endpoint serves, never assumed."""
    first, err = _fetch_json(endpoint, budget, MAX_PAGE_BYTES)
    if err:
        out = _empty_walk(endpoint)
        out["first_problem"] = "could not read walk endpoint: %s" % err
        return out, {}, {}, {}
    if isinstance(first, dict) and isinstance(first.get("checkpoints"), list):
        return _walk_checkpoints(endpoint, first, budget)
    if isinstance(first, dict) and isinstance(first.get("blocks"), list):
        return _walk_blocks(endpoint, budget)
    out = _empty_walk(endpoint)
    out["first_problem"] = ("endpoint serves neither the blocks nor the "
                            "checkpoints walk format")
    return out, {}, {}, {}


def _empty_walk(endpoint):
    return {"endpoint": endpoint, "format": None, "blocks": 0,
            "public_recomputed": 0, "withheld_linkage_only": 0,
            "complete": False, "genesis_prev_is_GENESIS": None,
            "first_problem": None, "tip": None}


def _walk_blocks(endpoint, budget):
    out = _empty_walk(endpoint)
    out["format"] = "blocks"
    hashes = {}
    public_text = {}
    prev = "GENESIS"
    after = 0
    base = endpoint.split("?")[0]
    while True:
        url = "%s?after=%d&limit=%d" % (base, after, WALK_PAGE)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page after block %d: %s" % (after, err))
            break
        blocks = page.get("blocks") if isinstance(page, dict) else None
        if not isinstance(blocks, list):
            out["first_problem"] = "endpoint does not serve the walk format"
            break
        if after == 0:
            first_prev = page.get("previous_audit_hash")
            out["genesis_prev_is_GENESIS"] = (first_prev == "GENESIS")
        for b in blocks:
            idx = b.get("block_index")
            h = str(b.get("audit_hash") or "")
            if "preimage" in b:
                pre = b.get("preimage")
                if not isinstance(pre, str) or \
                        hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                    out["first_problem"] = out["first_problem"] or (
                        "block %s does not recompute" % idx)
                try:
                    stated_prev = json.loads(pre).get("prev_hash")
                except Exception:
                    stated_prev = None
                out["public_recomputed"] += 1
                public_text[idx] = pre
            else:
                stated_prev = b.get("prev_hash")
                out["withheld_linkage_only"] += 1
            if stated_prev != prev:
                out["first_problem"] = out["first_problem"] or (
                    "block %s does not link to the block before it" % idx)
            prev = h
            hashes[h] = idx
            out["blocks"] += 1
        if out["blocks"] >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d blocks; the checker walks at most %d"
                % (out["blocks"], WALK_MAX_BLOCKS))
            break
        if not page.get("has_more"):
            out["complete"] = True
            break
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            out["first_problem"] = out["first_problem"] or "paging did not advance"
            break
        after = nxt
    out["tip"] = prev if out["blocks"] else None
    return out, hashes, public_text, {}


def _walk_checkpoints(endpoint, first, budget):
    """MIR format: tip = sha256(seq:rangeStart:rangeEnd:eventCount:
    merkleRoot:prevTip), newest first, paged backwards with beforeSeq."""
    out = _empty_walk(endpoint)
    out["format"] = "checkpoints"
    base = endpoint.split("?")[0]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(endpoint).query))
    limit = q.get("limit", "200")
    rows = {}
    page = first
    while True:
        cps = page.get("checkpoints") if isinstance(page, dict) else None
        if not isinstance(cps, list) or not cps:
            break
        for cp in cps:
            try:
                rows[int(cp.get("seq"))] = cp
            except (TypeError, ValueError):
                out["first_problem"] = out["first_problem"] or \
                    "a checkpoint has no readable seq"
        lowest = min(int(c.get("seq")) for c in cps
                     if str(c.get("seq", "")).lstrip("-").isdigit())
        if lowest <= 0:
            break
        if len(rows) >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d checkpoints; the checker walks at most %d"
                % (len(rows), WALK_MAX_BLOCKS))
            break
        url = "%s?limit=%s&beforeSeq=%d" % (base, limit, lowest)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page before seq %d: %s" % (lowest, err))
            break

    hashes, public_text, meta = {}, {}, {}
    backfilled, backfill_through = 0, None
    prev = _ZERO64
    seqs = sorted(rows)
    if seqs and seqs[0] != 0:
        out["first_problem"] = out["first_problem"] or \
            "walk did not reach genesis (seq 0)"
    for n, seq in enumerate(seqs):
        cp = rows[seq]
        if n and seq != seqs[n - 1] + 1:
            out["first_problem"] = out["first_problem"] or \
                "gap in seq before %d" % seq
        tip = str(cp.get("tip") or "").lower()
        pre = ":".join([str(seq), str(cp.get("rangeStart")),
                        str(cp.get("rangeEnd")), str(cp.get("eventCount")),
                        str(cp.get("merkleRoot")), str(cp.get("prevTip"))])
        if hashlib.sha256(pre.encode("utf-8")).hexdigest() != tip:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not recompute" % seq
        if str(cp.get("prevTip") or "").lower() != prev:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not link to the one before it" % seq
        if seq == 0:
            out["genesis_prev_is_GENESIS"] = \
                (str(cp.get("prevTip") or "") == _ZERO64)
        created, rend = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if created is not None and rend is not None and \
                created - rend > BACKFILL_HOURS * 3600:
            backfilled += 1
            backfill_through = seq
        prev = tip
        hashes[tip] = seq
        public_text[seq] = json.dumps(cp, sort_keys=True)
        meta[seq] = cp
        out["public_recomputed"] += 1
        out["blocks"] += 1
    out["complete"] = bool(seqs) and seqs[0] == 0 and not out["first_problem"]
    out["tip"] = prev if seqs else None
    out["backfill_detected"] = {
        "checkpoints": backfilled, "through_seq": backfill_through,
        "rule": "checker default: sealed more than %d hours after the window "
                "it covers" % BACKFILL_HOURS,
        "note": "Where the declaration states its own detection_rule, the "
                "count under that rule is in INV-007."}
    return out, hashes, public_text, meta


def _hex_values(obj, found=None):
    found = found if found is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            _hex_values(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _hex_values(v, found)
    elif isinstance(obj, str):
        for m in _HEX64.findall(obj.lower()):
            found.add(m)
    return found


def _anchor_check(proof_endpoint, hashes, budget, meta=None):
    if not proof_endpoint:
        return "fail", "no anchor proof address declared"
    tip, raw = None, None
    if "{seq}" in proof_endpoint:
        done = [sq for sq, cp in (meta or {}).items()
                if str(cp.get("otsStatus")) in ("upgraded", "confirmed")]
        if not done:
            return "fail", "no checkpoint is marked as anchored"
        seq = max(done)
        tip = str(meta[seq].get("tip") or "").lower()
        raw, err = _fetch_raw(proof_endpoint.replace("{seq}", str(seq)),
                              budget, MAX_DECL_BYTES, "*/*")
        if err:
            return "fail", "could not read anchor proof: %s" % err
        if raw[:1] in (b"{", b"["):
            try:
                data = json.loads(raw.decode("utf-8"))
                import base64
                raw = base64.b64decode(data.get("ots_base64") or "")
            except Exception:
                return "fail", "anchor proof could not be read"
    else:
        data, err = _fetch_json(proof_endpoint, budget)
        if err:
            return "fail", "could not read anchor proof: %s" % err
        tip = str(data.get("tip") or "").lower() if isinstance(data, dict) else ""
        b64 = data.get("ots_base64") if isinstance(data, dict) else None
        if not b64:
            return "fail", "no proof bytes served (expected ots_base64)"
        import base64
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return "fail", "anchor proof could not be read"
    if not tip or tip not in hashes:
        return "fail", "the anchored tip is not in the walked chain"
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    except Exception:
        return "untested", "proof reader not available on this checker"
    try:
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
    except Exception:
        return "fail", "anchor proof could not be read"
    tb = bytes.fromhex(tip)
    candidates = (hashlib.sha256(tb).digest(), tb,
                  hashlib.sha256(tip.encode("ascii")).digest())
    if det.file_digest not in candidates:
        return "fail", "anchor proof is for a different value than the tip it names"
    heights = []

    def walk(ts):
        for att in ts.attestations:
            if isinstance(att, BitcoinBlockHeaderAttestation):
                heights.append(att.height)
        for _, sub in ts.ops.items():
            walk(sub)
    try:
        walk(det.timestamp)
    except Exception:
        return "fail", "anchor proof could not be walked"
    if not heights:
        return "fail", "anchor proof is still pending, not yet in Bitcoin"
    return "pass", ("proof commits a chain tip to Bitcoin block %s; the block "
                    "header itself is not re-checked here - run ots verify "
                    "to confirm against Bitcoin" % min(heights))


def _is_declaration(data):
    spec = str(data.get("spec") or "")
    return spec == "ai-integrity-declaration" or \
        spec.rstrip("/").endswith("/x/integrity/declaration")


def _witness_strength(data, held, budget):
    """sealed / bound / listed - how the witness binds its record."""
    rows = []
    if isinstance(data, dict):
        for key in ("tips", "held", "observations", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    row = None
    for r in rows:
        if isinstance(r, dict) and \
                str(r.get("peer_tip") or r.get("tip") or "").lower() in held:
            row = r
            break
    if row is None:
        return {"grade": "listed",
                "why": "tip found on the witness's page; no binding record read"}
    tip = str(row.get("peer_tip") or row.get("tip") or "").lower()
    blk_url, blk_hash = row.get("check_block"), row.get("sealed_block_hash")
    if blk_url and blk_hash:
        page, err = _fetch_json(blk_url, budget)
        blk = page.get("block") if isinstance(page, dict) else None
        pre = blk.get("preimage") if isinstance(blk, dict) else None
        if isinstance(pre, str) and tip in pre.lower() and \
                hashlib.sha256(pre.encode("utf-8")).hexdigest() == \
                str(blk_hash).lower():
            return {"grade": "sealed",
                    "why": "the witness's own block was recomputed and "
                           "contains the tip",
                    "witness_block": blk_url}
        return {"grade": "listed",
                "why": "a sealed block was claimed but could not be "
                       "recomputed here (%s)" % (err or "mismatch")}
    if row.get("our_tip_at_observation") or row.get("witness_tip_at_observation"):
        return {"grade": "bound",
                "why": "recorded against a position in the witness's own "
                       "anchored chain; dated, not sealed"}
    return {"grade": "listed",
            "why": "published with nothing binding it in the witness's chain"}


_ORDER = ["L0_DIARY", "L1_SEALED", "L2_WITNESSED", "L3_ANCHORED",
          "L4_OVERSIGHT_VERIFIED"]


def _check(domain):
    budget = _Budget()
    result = {"domain": domain, "checked_at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checker_version": VERSION,
        "standard": BASE + "declaration"}

    decl, found_at, tried = None, None, []
    for path in DECLARATION["discovery"]["paths"]:
        url = "https://%s%s" % (domain, path)
        data, err = _fetch_json(url, budget)
        tried.append({"url": url, "result": err or "found"})
        if data is not None and isinstance(data, dict) and \
                _is_declaration(data):
            decl, found_at = data, url
            break
        if data is not None and not err:
            tried[-1]["result"] = "not an ai-integrity-declaration"
    result["looked_at"] = tried

    if decl is None:
        result.update({
            "verified_level": "L0_DIARY", "badge": "GREY",
            "verdict": "No declaration found. Under the standard, silence is "
                       "a rating: L0_DIARY, the operator's word is the only "
                       "evidence.",
            "how_to_improve": "Publish a declaration at https://%s/.well-known/"
                              "ai-integrity.json using the declaration_template "
                              "in %s" % (domain, BASE + "declaration")})
        return result

    result["declaration_url"] = found_at
    result["declaration_sha256"] = hashlib.sha256(json.dumps(
        decl, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    claimed = str(decl.get("claimed_level") or "")
    result["claimed_level"] = claimed or None
    checks = {}

    # INV-001 and INV-007 need the chain.
    chain = decl.get("chain") or {}
    endpoint = chain.get("walk_endpoint")
    hashes, public_text, walk, meta = {}, {}, None, {}
    if not endpoint:
        checks["INV-001"] = {"result": "fail", "why": "no walk_endpoint declared"}
    else:
        walk, hashes, public_text, meta = _walk(endpoint, budget)
        ok = (walk["complete"] and walk["blocks"] > 0 and
              walk["genesis_prev_is_GENESIS"] and not walk["first_problem"])
        genesis_ok = True
        declared_genesis = str(chain.get("genesis_hash") or "").lower()
        if declared_genesis and hashes:
            first = min(hashes.items(), key=lambda kv: kv[1] if isinstance(kv[1], int) else 0)
            genesis_ok = (first[0] == declared_genesis)
        checks["INV-001"] = {
            "result": "pass" if (ok and genesis_ok) else "fail",
            "why": walk["first_problem"] or (
                None if genesis_ok else "declared genesis_hash is not the first block"),
            "walk": walk}

    # INV-002: no secret-shaped or personal values in public blocks.
    hits = []
    for idx, text in public_text.items():
        for label, rx in _SECRET_SHAPES:
            if rx.search(text):
                hits.append({"block_index": idx, "found": label})
                break
        if len(hits) >= 10:
            break
    if not decl.get("personal_data_hashing"):
        checks["INV-002"] = {"result": "fail",
                             "why": "personal_data_hashing not declared"}
    elif not public_text:
        checks["INV-002"] = {"result": "fail",
                             "why": "no public records to inspect"}
    elif hits:
        checks["INV-002"] = {"result": "fail",
                             "why": "public blocks contain values that look "
                                    "personal or secret (values not repeated here)",
                             "blocks": hits}
    else:
        checks["INV-002"] = {"result": "pass",
                             "why": "%d public blocks inspected; nothing "
                                    "personal or secret-shaped found"
                                    % len(public_text)}

    # INV-007: every discontinuity is disclosed - sealed in the chain, or
    # declared with the evidence to detect it - and anything the checker
    # can detect for itself must have been declared.
    discs = decl.get("discontinuities") or []
    missing, sealed, declared = [], 0, []
    for disc in discs:
        if not isinstance(disc, dict):
            missing.append(str(disc))
            continue
        blk = disc.get("disclosure_block")
        if blk not in (None, ""):
            try:
                blk = int(blk)
            except (TypeError, ValueError):
                missing.append(str(blk))
                continue
            if blk in public_text:
                sealed += 1
            else:
                missing.append(str(blk))
        elif disc.get("kind") and disc.get("detail"):
            declared.append(str(disc.get("kind")))
        else:
            missing.append("an entry with neither a disclosure_block nor kind and detail")
    undisclosed = None
    bf = (walk or {}).get("backfill_detected") or {}
    if bf.get("checkpoints"):
        claimed_bf = [d for d in discs if isinstance(d, dict) and
                      "backfill" in str(d.get("kind", "")).lower()]
        if not claimed_bf:
            undisclosed = ("%d checkpoints were sealed long after the window "
                           "they cover, and no backfill is declared"
                           % bf["checkpoints"])
    if checks["INV-001"]["result"] != "pass":
        checks["INV-007"] = {"result": "fail", "why": "chain could not be verified"}
    elif missing:
        checks["INV-007"] = {"result": "fail",
                             "why": "declared disclosures not found: %s"
                                    % ", ".join(missing)}
    elif undisclosed:
        checks["INV-007"] = {"result": "fail", "why": undisclosed}
    else:
        parts = []
        if sealed:
            parts.append("%d sealed in the chain" % sealed)
        if declared:
            parts.append("%d declared with detection evidence (%s)"
                         % (len(declared), ", ".join(declared)))
        checks["INV-007"] = {
            "result": "pass",
            "why": ("discontinuities disclosed: " + "; ".join(parts))
                   if parts else "no discontinuities declared, and none detected"}
        checker_default = None
        if bf.get("checkpoints"):
            checker_default = {
                "backfilled_checkpoints": bf["checkpoints"],
                "through_seq": bf["through_seq"],
                "rule": str(bf.get("rule")),
                "note": "The checker's own threshold, used only when no rule "
                        "is declared. Shown for comparison."}
        recounts = []
        for d in discs:
            if not isinstance(d, dict) or \
                    "backfill" not in str(d.get("kind", "")).lower():
                continue
            rule_text = d.get("detection_rule") or d.get("detectionRule")
            entry = {"kind": d.get("kind"), "declared_rule": rule_text,
                     "declared_count": d.get("checkpoints") or d.get("count"),
                     "declared_through_seq": d.get("through_seq")}
            parsed = _parse_rule(rule_text) if rule_text else None
            if not rule_text:
                entry["result"] = "rule_missing"
                entry["note"] = ("No detection_rule declared. Reported in "
                                 "1.0.3; from 1.1.0 this fails.")
            elif not parsed or not meta:
                entry["result"] = "rule_unreadable"
                entry["note"] = ("The declared rule could not be applied "
                                 "automatically. Reported, not failed.")
            else:
                n, through = _recount(meta, parsed[0], parsed[1])
                entry["recounted_under_declared_rule"] = n
                entry["recounted_through_seq"] = through
                try:
                    ok = int(entry["declared_count"]) == n
                except (TypeError, ValueError):
                    ok = None
                entry["reproduces"] = ok
                entry["result"] = ("reproduced" if ok else
                                   "differs" if ok is False else "recounted")
            recounts.append(entry)
        applied = [r for r in recounts
                   if r.get("result") in ("reproduced", "differs", "recounted")]
        if applied:
            a = applied[0]
            checks["INV-007"]["independently_detected"] = {
                "backfilled_checkpoints": a.get("recounted_under_declared_rule"),
                "through_seq": a.get("recounted_through_seq"),
                "rule": "declared: " + str(a.get("declared_rule")),
                "reproduces_declared_count": a.get("reproduces"),
                "note": "Recounted by the checker from createdAt against "
                        "rangeEnd, under the rule the declaration states. "
                        "Nothing taken on trust."}
            if checker_default:
                checks["INV-007"]["checker_default_for_comparison"] = checker_default
        elif checker_default:
            checks["INV-007"]["independently_detected"] = checker_default
        if recounts:
            checks["INV-007"]["detection_rule_recount"] = recounts

    # INV-003: at least one declared witness holds a tip that is in our chain.
    witnesses = decl.get("witnesses") or []
    witness_results = []
    for w in witnesses[:5]:
        if not isinstance(w, dict) or not w.get("tip_endpoint"):
            continue
        data, err = _fetch_json(w.get("tip_endpoint"), budget,
                                WITNESS_MAX_BYTES, allow_text=True)
        if err:
            witness_results.append({"name": w.get("name"), "result": "fail",
                                    "why": err})
            continue
        held = _hex_values(data) & set(hashes.keys())
        entry = {
            "name": w.get("name"),
            "url": w.get("tip_endpoint"),
            "result": "pass" if held else "fail",
            "why": "publishes %d hash(es) that are blocks in the chain"
                   % len(held) if held else
                   "published no value found in the chain"}
        if held:
            entry["matched_blocks"] = sorted(
                hashes[h] for h in held if isinstance(hashes.get(h), int))[-5:]
            entry["witness_strength"] = _witness_strength(data, held, budget)
        witness_results.append(entry)
    if any(r["result"] == "pass" for r in witness_results):
        checks["INV-003"] = {"result": "pass", "witnesses": witness_results,
                             "collusion_threshold_declared":
                                 decl.get("collusion_threshold"),
                             "note": "Independence of each witness is as "
                                     "declared; the checker confirms they "
                                     "hold the tip, not who runs them."}
    else:
        checks["INV-003"] = {"result": "fail",
                             "why": "no declared witness confirmed a tip in "
                                    "the chain" if witness_results else
                                    "no witnesses declared",
                             "witnesses": witness_results}

    # INV-004: an anchor proof committing a chain tip to Bitcoin.
    anchor = decl.get("anchor") or {}
    res, why = _anchor_check(anchor.get("proof_endpoint"), hashes, budget, meta)
    checks["INV-004"] = {"result": res, "why": why}

    # INV-005 / INV-006 cannot be tested from outside yet.
    for inv in ("INV-005", "INV-006"):
        checks[inv] = {"result": "untested",
                       "why": "human-oversight checks cannot yet be tested "
                              "from outside; this checker never awards L4"}

    level = "L0_DIARY"
    for name in _ORDER[1:]:
        needs = [r.split("-")[0] + "-" + r.split("-")[1]
                 for r in DECLARATION["levels"][name]["requires"]]
        if all(checks.get(n, {}).get("result") == "pass" for n in needs):
            level = name
        else:
            break

    if decl.get("known_gaps"):
        result["known_gaps_declared"] = decl.get("known_gaps")
    result["checks"] = checks
    result["verified_level"] = level
    result["badge"] = DECLARATION["levels"][level]["badge"]
    if claimed in _ORDER and _ORDER.index(claimed) > _ORDER.index(level):
        result["verdict"] = "OVERCLAIMED: declares %s, verifies as %s." % (claimed, level)
        result["overclaimed"] = True
    else:
        result["verdict"] = "Verifies as %s." % level
        result["overclaimed"] = False
    result["rule"] = ("Nothing in the declaration was taken on trust. Every "
                      "pass above was recomputed or fetched by this checker.")
    return result


VERDICT_USER = "system_integrity_verdict"
VERDICT_RESEAL_SECONDS = 24 * 3600
VERDICT_MAX_PER_HOUR = 30
_seal_times = []
_seal_lock = threading.Lock()


def _verdict_fingerprint(out):
    return (out.get("verified_level"), out.get("claimed_level"),
            out.get("overclaimed"), bool(out.get("error")))


def _verdict_ref(idx, h):
    return {"block_index": idx, "audit_hash": h,
            "check_block": ("https://sebbi.pro/x/walk/block?index=%s" % idx)
            if idx is not None else None}


def _already_sealed(conn, domain, fp, now):
    """The chain itself is the memory: find a verdict for this domain,
    sealed today (UTC), with the same outcome. Per UTC day, like requests,
    so each day's first request is always followed by a verdict."""
    rows = conn.execute(
        "SELECT id, audit_hash, result_json FROM audit_log "
        "WHERE user_id = ? AND ts >= ? ORDER BY id DESC LIMIT 200",
        (VERDICT_USER, now - (now % 86400))).fetchall()
    for idx, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        if r.get("domain") != domain:
            continue
        if (r.get("verified_level"), r.get("claimed_level"),
                r.get("overclaimed")) == fp[:3]:
            return _verdict_ref(idx, h)
        return None   # latest verdict for this domain differs: reseal
    return None


REQUEST_USER = "system_integrity_request"


def _claim(conn, domain, day, key, now):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
        "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
        "PRIMARY KEY (domain, day, verdict))")
    cur = conn.execute(
        "INSERT OR IGNORE INTO integrity_verdict_claims "
        "(domain, day, verdict, claimed_at) VALUES (?, ?, ?, ?)",
        (domain, day, key, now))
    conn.commit()
    return cur.rowcount == 1


def _seal_request(domain, ctx):
    """Seal that a check was asked for, before it runs. Once per domain per
    UTC day, so the chain shows every domain that was asked about - and the
    register can show any request with no verdict after it."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    with lock:
        won = _claim(conn, domain, day, "__request__", now)
        if not won:
            r = conn.execute(
                "SELECT id, audit_hash FROM audit_log WHERE user_id = ? AND "
                "ts > ? AND result_json LIKE ? ORDER BY id DESC LIMIT 1",
                (REQUEST_USER, now - 86400,
                 '%"domain": "' + domain + '"%')).fetchone()
            ref = _verdict_ref(r[0], r[1]) if r else {}
            return dict(ref, sealed_now=False)
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; request not sealed"}
        _seal_times.append(now)
    event = {"user_id": REQUEST_USER, "action": "integrity_check_requested",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "REQUESTED", "score": 0, "domain": domain,
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(now)),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, "__request__"))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _seal_verdict(domain, out, ctx):
    """Seal a verdict into the chain at most once per domain per UTC day,
    unless the verdict changes.

    v1.4 kept that limit in server memory, so a server running several
    copies of itself sealed once per copy. v1.4.1 asks the chain first,
    then claims the seal in a table every copy shares, so only one copy
    can seal a given verdict on a given day."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    if out.get("error"):
        # A check that failed to run has no verdict to seal. Its request is
        # already sealed, so the register shows it as asked and unanswered.
        return {"sealed_now": False,
                "note": "the check did not complete, so no verdict was sealed; "
                        "the request stays on record without one"}
    now = time.time()
    fp = _verdict_fingerprint(out)
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    claim = json.dumps(list(fp))
    with lock:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
            "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
            "PRIMARY KEY (domain, day, verdict))")
        ref = _already_sealed(conn, domain, fp, now)
        if ref:
            conn.commit()
            return dict(ref, sealed_now=False)
        won = _claim(conn, domain, day, claim, now)
    if not won:
        return {"sealed_now": False,
                "note": "this verdict was already sealed today"}
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; verdict not sealed"}
        _seal_times.append(now)
    walk = ((out.get("checks") or {}).get("INV-001") or {}).get("walk") or {}
    event = {"user_id": VERDICT_USER, "action": "integrity_verdict",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "VERDICT", "score": 0, "domain": domain,
              "verified_level": out.get("verified_level"),
              "badge": out.get("badge"),
              "claimed_level": out.get("claimed_level"),
              "overclaimed": out.get("overclaimed"),
              "declaration_url": out.get("declaration_url"),
              "declaration_sha256": out.get("declaration_sha256"),
              "chain_tip_reached": walk.get("tip"),
              "blocks_walked": walk.get("blocks"),
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "checked_at": out.get("checked_at"),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, claim))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _register(data, ctx):
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if conn is None or lock is None:
        return {"ok": False, "error": "register_unavailable"}, 503
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 2000",
            (VERDICT_USER,)).fetchall()
    with lock:
        req_rows = conn.execute(
            "SELECT id, ts, result_json FROM audit_log WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 2000", (REQUEST_USER,)).fetchall()
    last_request = {}
    for ridx, rts, rj in req_rows:
        try:
            d = json.loads(rj).get("domain")
        except Exception:
            continue
        if d and d not in last_request:
            last_request[d] = (ridx, rts)
    latest = {}
    history = {}
    for idx, ts, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        d = r.get("domain")
        if not d:
            continue
        history[d] = history.get(d, 0) + 1
        if d in latest:
            continue
        latest[d] = {"domain": d, "verified_level": r.get("verified_level"),
                     "badge": r.get("badge"),
                     "claimed_level": r.get("claimed_level"),
                     "overclaimed": r.get("overclaimed"),
                     "checked_at": r.get("checked_at"),
                     "sealed_in_block": idx, "sealed_block_hash": h,
                     "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
                     "check_now": BASE + "check?domain=" + d}
    order = {n: i for i, n in enumerate(_ORDER)}
    entries = sorted(latest.values(), key=lambda e: (
        -order.get(e.get("verified_level"), -1), e["domain"]))
    for e in entries:
        e["verdicts_sealed"] = history.get(e["domain"], 0)
        lr = last_request.get(e["domain"])
        if lr:
            e["last_request_block"] = lr[0]
    unanswered = []
    for d, (ridx, rts) in sorted(last_request.items()):
        v = latest.get(d)
        if v is None or v["sealed_in_block"] < ridx:
            # a verdict sealed earlier the same day still answers a request
            # sealed later only if the verdict was unchanged; show it anyway
            # so a reader can judge, and say which case it is.
            unanswered.append({
                "domain": d, "request_block": ridx,
                "check_request": "https://sebbi.pro/x/walk/block?index=%d" % ridx,
                "latest_verdict_block": v["sealed_in_block"] if v else None,
                "reading": ("an unchanged verdict sealed earlier the same day "
                            "stands for this request") if v else
                           "asked about, and no verdict has been sealed"})
    return {"ok": True, "register": "AI Integrity Declaration - sealed verdicts",
            "standard": BASE + "declaration",
            "domains": len(entries), "entries": entries,
            "requests_without_a_later_verdict": unanswered,
            "what_this_is": "The latest verdict the checker sealed for each "
                            "domain, highest level first. Every row points "
                            "at the public block that holds it, so no rating "
                            "here can be changed after it was given - by the "
                            "domain, or by sebbi.pro. Every request is sealed "
                            "before its check runs, so a question that was "
                            "asked and never answered is visible below the "
                            "list, not hidden by it."}, 200


def _check_route(data, ctx=None):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"ok": False, "error": "domain_required",
                "example": BASE + "check?domain=example.com",
                "detail": "Give a public domain name, e.g. domain=example.com"}, 400
    now = time.time()
    with _cache_lock:
        hit = _cache.get(domain)
        if hit and now - hit[0] < CACHE_SECONDS:
            out = dict(hit[1])
            out["cached_seconds_ago"] = int(now - hit[0])
            return out, 200
    if not _running.acquire(blocking=False):
        return {"ok": False, "error": "busy",
                "detail": "Two checks are already running. Try again in a "
                          "minute."}, 429
    request = _seal_request(domain, ctx)
    try:
        out = _check(domain)
    except Exception as exc:
        out = {"domain": domain, "verified_level": "L0_DIARY", "badge": "GREY",
               "error": "check_failed", "detail": str(exc)[:200]}
    finally:
        _running.release()
    out["ok"] = True
    if request:
        out["request_sealed"] = request
    sealed = _seal_verdict(domain, out, ctx)
    if sealed:
        out["verdict_sealed"] = sealed
    with _cache_lock:
        _cache[domain] = (time.time(), out)
        if len(_cache) > 500:
            oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:100]
            for k, _ in oldest:
                _cache.pop(k, None)
    return out, 200


def _status():
    return {
        "ok": True,
        "module": "integrity",
        "version": VERSION,
        "standard": DECLARATION.get("spec"),
        "standard_version": DECLARATION.get("version"),
        "declaration_id": DECLARATION.get("declaration_id"),
        "declaration_sha256": DECLARATION_SHA256,
        "levels": list(DECLARATION.get("levels", {}).keys()),
        "invariants": list(DECLARATION.get("invariants", {}).keys()),
        "links": {
            "declaration": BASE + "declaration",
            "check_any_domain": BASE + "check?domain=example.com",
            "sebbi_self_declaration": BASE + "self",
            "check_sebbi": BASE + "check?domain=sebbi.pro",
            "register": BASE + "register",
            "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
        },
        "how_to_adopt": "Publish your own filled-in declaration_template at "
                        "/.well-known/ai-integrity.json on your own domain, "
                        "then check it at " + BASE + "check?domain=yourdomain",
        "hash_note": "declaration_sha256 is SHA-256 of the declaration as "
                     "compact JSON with sorted keys, so anyone can confirm "
                     "the text they are reading is the text published.",
    }


def handle(method, action, data, api_key, ctx):
    data = data or {}
    if isinstance(data.get("domain"), list):
        data = dict(data)
        data["domain"] = data["domain"][0] if data["domain"] else ""
    if method == "GET" and action in ("status", "spec", ""):
        return _status(), 200
    if method == "GET" and action == "declaration":
        return DECLARATION, 200
    if method == "GET" and action == "self":
        return SELF, 200
    if method == "GET" and action == "check":
        return _check_route(data, ctx)
    if method == "GET" and action == "register":
        return _register(data, ctx)
    return {"ok": False, "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": []}, 404

```
