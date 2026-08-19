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

VERSION = "1.1.0"

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


def _seal(ctx, event, result):
    """Call the host seal() whatever shape it takes.

    Returns (ok, shape_used, error_text). Nothing is swallowed: if every
    shape fails, the reason is stored on the tick row and published, because
    a beat that never reached the chain is not a floor and must not look
    like one.
    """
    fn = ctx.get("seal")
    if fn is None:
        return False, None, "ctx has no seal function"

    payload = result if isinstance(result, str) else json.dumps(result, sort_keys=True)
    conn = ctx.get("conn")

    attempts = [
        ("seal(event, json_string)", lambda: fn(event, payload)),
        ("seal(event, dict)", lambda: fn(event, result)),
        ("seal(conn, event, json_string)", lambda: fn(conn, event, payload)),
        ("seal(conn, event, dict)", lambda: fn(conn, event, result)),
        ("seal(event=, result=)", lambda: fn(event=event, result=payload)),
        ("seal(event, json_string, None)", lambda: fn(event, payload, None)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            call()
            return True, shape, None
        except Exception as e:
            errors.append("%s -> %s: %s" % (shape, type(e).__name__, e))
    return False, None, " | ".join(errors)


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

    ok, shape, err = _seal(ctx, event, result)
    with lock:
        conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=? WHERE id=?",
                     (shape, err, tick_id))
        conn.commit()
    rid, h = (None, None)
    if ok:
        try:
            rid, h = _backfill(conn, lock, tick_id)
        except Exception as e:
            with lock:
                conn.execute("UPDATE heartbeat_tick SET seal_error=? WHERE id=?",
                             ("backfill failed: %s" % e, tick_id))
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
        _seal(ctx, "heartbeat_beat", {
            "kind": "beacon_tick_supplied",
            "source": src, "round": rnd, "value": str(val), "fetched_at": now,
            "note": ("Supplied by the operator rather than fetched here. The "
                     "floor it gives is only as good as the reader's trust in "
                     "that source, and it is marked so nobody mistakes it."),
        })
        rid, h = _backfill(conn, lock, tick_id)
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
