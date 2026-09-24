# Codebase — part 10 of 41

Contains:
- `modules/heartbeat.py`
- `modules/held.py`
- `modules/homelink.py`


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


## `modules/homelink.py`

219 lines, 13190 bytes

```python
"""
modules/homelink.py  v1.8.0
Adds the "Auditors", "Cinema", "Deep Run", "Agent Room", "Machine readable" and "Agent Passport" buttons to the sebbi.pro homepage without
editing index.html or server.py.

Page module, same family as map.py: a runtime do_GET patch. For the homepage
only ("/" and "/index.html") it lets the normal handler build the page into a
buffer, inserts one small fixed button before </body>, corrects the
Content-Length, and sends it on. If anything about the response is not a plain
200 HTML page with a </body> tag, the original bytes are sent untouched - the
homepage can never be broken by this module, only left as it was.

Armed by hitting /x/homelink/status once after each deploy.
"""

import io
import sys

VERSION = "1.8.0"
PATHS = ("/", "/index.html")
MARK = b"<!--sebbi-homelink-->"

BUTTON = (
    b'<!--sebbi-homelink--><style>@keyframes sbspin{to{transform:rotate(360deg)}}'
    b'@keyframes sbpulse{0%,100%{box-shadow:0 0 12px rgba(74,163,255,.55),0 5px 18px rgba(0,0,0,.4)}'
    b'50%{box-shadow:0 0 22px rgba(201,168,76,.8),0 5px 18px rgba(0,0,0,.4)}}'
    b'@keyframes sbfloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}'
    b'#sebbi-homelink{position:fixed;right:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:8px}'
    b'#sebbi-homelink a{display:flex;align-items:center;gap:7px;background:#0a0f1e;color:#fff;'
    b'border-radius:999px;padding:8px 13px;font:500 12px/1 \'IBM Plex Mono\',ui-monospace,monospace;'
    b'text-decoration:none;box-shadow:0 5px 18px rgba(0,0,0,.35)}'
    b'#sebbi-homelink .tag{border-radius:999px;padding:3px 6px;font-size:9.5px;letter-spacing:.05em;color:#0a0f1e}'
    b'#sebbi-homelink .portal{position:relative;border:0;padding:9px 15px 9px 10px;animation:sbpulse 2.4s infinite}'
    b'#sebbi-homelink .portal:before{content:"";position:absolute;inset:-2px;border-radius:999px;z-index:-1;'
    b'background:conic-gradient(from 0deg,#c9a84c,#7fe3b0,#4aa3ff,#c9a84c)}'
    b'#sebbi-homelink .ring{width:18px;height:18px;border-radius:50%;flex:none;'
    b'background:conic-gradient(#c9a84c,#7fe3b0,#4aa3ff,#c9a84c);animation:sbspin 1.4s linear infinite;'
    b'-webkit-mask:radial-gradient(circle,transparent 45%,#000 50%);mask:radial-gradient(circle,transparent 45%,#000 50%)}'
    b'#sebbi-homelink .x{width:30px;height:30px;padding:0;justify-content:center;border:1px solid rgba(255,255,255,.3);'
    b'font-size:14px;cursor:pointer}'
    b'#sebbi-bubble{display:none;position:fixed;right:18px;bottom:calc(18px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;width:62px;height:62px;border-radius:50%;cursor:pointer;animation:sbfloat 3.2s ease-in-out infinite;'
    b'background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.95) 0,rgba(255,255,255,.35) 12%,rgba(143,208,255,.35) 30%,'
    b'rgba(201,168,76,.35) 62%,rgba(10,15,30,.55) 100%);'
    b'box-shadow:inset -8px -10px 18px rgba(10,15,30,.55),inset 6px 6px 14px rgba(255,255,255,.35),'
    b'0 10px 26px rgba(0,0,0,.45),0 0 24px rgba(143,208,255,.35);border:1px solid rgba(255,255,255,.35);'
    b'display:none;align-items:center;justify-content:center;font:600 11px \'IBM Plex Mono\',monospace;color:#fff;'
    b'text-shadow:0 1px 4px rgba(0,0,0,.6)}'
    b'#sebbi-tools{position:fixed;left:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'display:none;flex-direction:column;align-items:flex-start;gap:8px}'
    b'#sebbi-tools a{display:flex;align-items:center;gap:7px;background:#0a0f1e;color:#fff;border-radius:999px;'
    b'padding:8px 13px;font:500 12px/1 \'IBM Plex Mono\',ui-monospace,monospace;text-decoration:none;'
    b'box-shadow:0 5px 18px rgba(0,0,0,.35);border:1.5px solid rgba(255,255,255,.2)}'
    b'#sebbi-tools a.x{width:30px;height:30px;padding:0;justify-content:center;font-size:14px}'
    b'#sebbi-toolbubble{position:fixed;left:18px;bottom:calc(18px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'width:62px;height:62px;border-radius:50%;cursor:pointer;animation:sbfloat 3.6s ease-in-out infinite;'
    b'background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.95) 0,rgba(255,255,255,.35) 12%,rgba(127,227,176,.4) 30%,'
    b'rgba(213,155,255,.35) 62%,rgba(10,15,30,.55) 100%);'
    b'box-shadow:inset -8px -10px 18px rgba(10,15,30,.55),inset 6px 6px 14px rgba(255,255,255,.35),'
    b'0 10px 26px rgba(0,0,0,.45),0 0 24px rgba(127,227,176,.35);border:1px solid rgba(255,255,255,.35);'
    b'display:flex;align-items:center;justify-content:center;font:600 11px \'IBM Plex Mono\',monospace;color:#fff;'
    b'text-shadow:0 1px 4px rgba(0,0,0,.6)}'
    b'#sebbi-studio{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(14px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;display:none;flex-direction:column;align-items:center;gap:8px}'
    b'#sebbi-studio a{display:flex;align-items:center;gap:7px;background:#0a0f1e;color:#fff;border-radius:999px;'
    b'padding:8px 13px;font:500 12px/1 \'IBM Plex Mono\',ui-monospace,monospace;text-decoration:none;'
    b'box-shadow:0 5px 18px rgba(0,0,0,.35);border:1.5px solid rgba(213,155,255,.55);white-space:nowrap}'
    b'#sebbi-studio a.x{width:30px;height:30px;padding:0;justify-content:center;font-size:14px;border-color:rgba(255,255,255,.25)}'
    b'#sebbi-studiobubble{position:fixed;left:50%;transform:translateX(-50%);bottom:calc(18px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;width:66px;height:66px;border-radius:50%;cursor:pointer;animation:sbfloat 3s ease-in-out infinite;'
    b'background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.95) 0,rgba(255,255,255,.35) 12%,rgba(213,155,255,.45) 30%,'
    b'rgba(201,168,76,.4) 62%,rgba(10,15,30,.6) 100%);'
    b'box-shadow:inset -8px -10px 18px rgba(10,15,30,.55),inset 6px 6px 14px rgba(255,255,255,.35),'
    b'0 10px 26px rgba(0,0,0,.45),0 0 26px rgba(213,155,255,.45);border:1px solid rgba(255,255,255,.35);'
    b'display:flex;align-items:center;justify-content:center;font:600 10.5px \'IBM Plex Mono\',monospace;color:#fff;'
    b'text-shadow:0 1px 4px rgba(0,0,0,.6);text-align:center;line-height:1.15}'
    b'</style>'
    b'<div id="sebbi-studiobubble" onclick="this.style.display=\'none\';document.getElementById(\'sebbi-studio\').style.display=\'flex\'">'
    b'monop<br>studio</div>'
    b'<div id="sebbi-studio">'
    b'<a class="x" href="#" aria-label="Close" onclick="event.preventDefault();this.parentNode.style.display=\'none\';'
    b'document.getElementById(\'sebbi-studiobubble\').style.display=\'flex\'">&times;</a>'
    b'<a href="/create"><span class="tag" style="background:#d59bff">NEW</span>Monopolise a video</a>'
    b'<a href="/create#player">Watch the demo lock</a>'
    b'<a href="/create#how">How creators get paid</a>'
    b'<a href="/create#price">Pricing &amp; splits</a>'
    b'<a href="/create#calc">Earnings calculator</a>'
    b'<a href="/create#centre">Your control centre</a>'
    b'<a href="/cinema">See it in the cinema</a>'
    b'</div>'
    b'<div id="sebbi-toolbubble" onclick="this.style.display=\'none\';document.getElementById(\'sebbi-tools\').style.display=\'flex\'">'
    b'tools</div>'
    b'<div id="sebbi-tools">'
    b'<a class="x" href="#" aria-label="Close" onclick="event.preventDefault();this.parentNode.style.display=\'none\';'
    b'document.getElementById(\'sebbi-toolbubble\').style.display=\'flex\'">&times;</a>'
    b'<a href="/tools#meter" style="border-color:#7fe3b0"><span class="tag" style="background:#7fe3b0">01</span>Token Meter</a>'
    b'<a href="/tools#lens" style="border-color:#c9a84c"><span class="tag" style="background:#c9a84c">02</span>Receipt Lens</a>'
    b'<a href="/tools#shield" style="border-color:#ff8a80"><span class="tag" style="background:#ff8a80">03</span>Prompt Shield</a>'
    b'<a href="/tools#guard" style="border-color:#8fd0ff"><span class="tag" style="background:#8fd0ff">04</span>Spend Guard</a>'
    b'<a href="/tools#badge" style="border-color:#d59bff"><span class="tag" style="background:#d59bff">05</span>Proof Badge</a>'
    b'<a href="/tools" style="border-color:rgba(255,255,255,.35)">All free tools &rarr;</a>'
    b'</div>'
    b'<a id="sebbi-start" href="/start" style="position:fixed;left:12px;top:calc(12px + env(safe-area-inset-top,0px));'
    b'z-index:2147483000;display:flex;align-items:center;gap:7px;background:rgba(10,15,30,.9);color:#fff;'
    b'border:1.5px solid #c9a84c;border-radius:999px;padding:7px 12px 7px 8px;font:600 11.5px/1 \'IBM Plex Mono\',monospace;'
    b'text-decoration:none;box-shadow:0 0 18px rgba(201,168,76,.45)">'
    b'<span style="width:16px;height:16px;border-radius:50%;background:conic-gradient(#c9a84c,#7fe3b0,#4aa3ff,#c9a84c);'
    b'animation:sbspin 1.4s linear infinite;-webkit-mask:radial-gradient(circle,transparent 42%,#000 48%);'
    b'mask:radial-gradient(circle,transparent 42%,#000 48%)"></span>START HERE &rarr;</a>'
    b'<div id="sebbi-bubble" onclick="this.style.display=\'none\';document.getElementById(\'sebbi-homelink\').style.display=\'flex\'">'
    b'sebbi</div>'
    b'<div id="sebbi-homelink">'
    b'<a class="x" href="#" aria-label="Close" onclick="event.preventDefault();this.parentNode.style.display=\'none\';'
    b'var b=document.getElementById(\'sebbi-bubble\');b.style.display=\'flex\'">&times;</a>'
    b'<a href="/auditors" style="background:#c9a84c;color:#0a0f1e;border:0;font-weight:700;'
    b'box-shadow:0 0 24px rgba(201,168,76,.5),0 5px 18px rgba(0,0,0,.4)">&#9878; AUDITORS &rarr;</a>'
    b'<a href="/cinema" style="border:1.5px solid #8fd0ff"><span class="tag" style="background:#8fd0ff">WATCH</span>Cinema &#127916;</a>'
    b'<a href="/game" style="border:1.5px solid #d59bff"><span class="tag" style="background:#d59bff">PLAY</span>Deep Run &#9654;</a>'
    b'<a class="portal" href="/room"><span class="ring"></span>Enter the Agent Room &rarr;</a>'
    b'<a href="/prove" style="border:1.5px solid #7fe3b0"><span class="tag" style="background:#7fe3b0">PROOF</span>Machine readable &rarr;</a>'
    b'<a href="/passport" style="border:1.5px solid #c9a84c"><span class="tag" style="background:#c9a84c">NEW</span>Agent Passport &rarr;</a>'
    b'</div>'
)

_patched = False


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


def _inject(raw):
    """Return modified response bytes, or None to send the original."""
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or b" 200" not in lines[0]:
        return None
    lower = head.lower()
    if b"text/html" not in lower or b"content-encoding" in lower or b"chunked" in lower:
        return None
    if MARK in body:
        return None
    at = body.rfind(b"</body>")
    if at < 0:
        return None
    new_body = body[:at] + BUTTON + body[at:]
    out = []
    for ln in lines:
        if ln.lower().startswith(b"content-length:"):
            ln = b"Content-Length: " + str(len(new_body)).encode()
        out.append(ln)
    return b"\r\n".join(out) + b"\r\n\r\n" + new_body


def _install(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_homelink_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0]
        if path not in PATHS:
            return original_do_GET(self)
        real = self.wfile
        buf = io.BytesIO()
        self.wfile = buf
        try:
            original_do_GET(self)
            if hasattr(self, "_headers_buffer") and self._headers_buffer:
                self.flush_headers()
        finally:
            self.wfile = real
        raw = buf.getvalue()
        try:
            changed = _inject(raw)
        except Exception:
            changed = None
        real.write(changed if changed is not None else raw)

    cls.do_GET = do_GET
    cls._homelink_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    return ({"module": "homelink", "version": VERSION, "armed": armed,
             "adds": "Monop Studio bubble (/create, bottom centre), Free tools bubble (/tools, bottom left), Start here (/start, top left), Auditors (/auditors), Cinema (/cinema), Deep Run (/game), Agent Room (/room), Machine readable (/prove) and Agent Passport (/passport) buttons",
             "safe": "any response that is not a plain 200 HTML page is sent untouched"}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
