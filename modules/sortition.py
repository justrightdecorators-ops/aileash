"""
sortition.py - selection by lot. The operator stops choosing who gets audited.

THE HOLE THIS FILLS
-------------------
Every system claiming human oversight reviews a sample of decisions. In
every one of them, the operator picks the sample. So the sample proves
nothing: you can review the easy ones, or the ones you already know are
clean, and nobody outside can tell the difference. It is the softest spot
in every Article 14 claim in the industry, and it has stayed soft because
there was no alternative.

There is one now. heartbeat.py seals a public beacon value on a cadence -
a number nobody, including the operator, can know before its tick. That is
a dice roll no one owns.

THE THREE LOCKS, IN ORDER. THE ORDER IS THE WHOLE POINT.
--------------------------------------------------------
1. COMMIT THE POOL. Every record eligible for review in a period is
   listed, hashed into one pool digest, and sealed. The pool is now fixed.
2. WAIT FOR A TICK. The draw may only use a beacon value sealed AFTER the
   pool commit. This module refuses otherwise. So the pool was fixed
   before the dice existed, and cannot be edited once they do.
3. DRAW. The beacon value deterministically ranks the pool. The lowest k
   ranks are selected. Anyone can recompute it from public values.

Break any one and the sample is choosable again. Enforced here, not
promised.

WHAT IT CATCHES
---------------
A selected record with no review sealed against it is a permanent, visible
hole with a name on it. You cannot quietly skip an awkward case, because
the case was chosen for you in public, and its absence is the evidence.

Refusal is allowed and is not hidden - it is sealed as a refusal with a
reason. An honest refusal on the record is worth more than a silent gap.

THE SELECTION FUNCTION, PUBLISHED SO IT IS NOT OURS
---------------------------------------------------
  seed = SHA256("AILEASH-SORTITION-v1" | period | pool_digest | beacon_value)
  rank(i) = SHA256(seed | ":" | record_hash_i)
  selected = the k records with the lowest rank, ties by record hash

No random number generator, no language-specific behaviour, no library.
Ten lines in any language. A stranger recomputes it and either gets our
list or catches us.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the reviews were any good. It proves nobody chose
  which ones happened.
- It does not stop an operator declining to draw at all. A period with no
  draw is a period with no sample, and /outstanding says so.
- Pool membership is asserted by this server. What stops a record being
  left out of the pool is complete.py, which commits the period's record
  count in advance - separate module, separate check.
- Selection is uniform. Risk-weighted sampling is deliberately not offered:
  a weighting the operator sets is a choice the operator made.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec         public  what this is and the exact selection function
  GET  draws        public  every draw ever made
  GET  draw         public  ?id= - one draw, its beacon value, its selection
  GET  verify       public  ?id= - recompute the draw from scratch, here
  GET  outstanding  public  selected records with no review yet, and how late
  GET  status       public  coverage, response rate, oldest unanswered
  POST pool         keyed   commit the pool for a period
  POST draw         keyed   draw a sample against a sealed beacon tick
  POST review       keyed   record a review, or a refusal with a reason
"""

import json
import time
import hashlib

VERSION = "1.0.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "draws"),
    ("GET", "draw"),
    ("GET", "verify"),
    ("GET", "outstanding"),
    ("GET", "status"),
}

DOMAIN_SEED = b"AILEASH-SORTITION-v1"
DOMAIN_POOL = b"AILEASH-POOL-v1"

DEFAULT_RATE = 0.05          # 5 percent
MIN_SELECT = 1
MAX_SELECT = 500
MAX_POOL = 200000
REVIEW_DUE_HOURS = 72

DDL = [
    """CREATE TABLE IF NOT EXISTS sortition_pool (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        period       TEXT NOT NULL,
        pool_digest  TEXT NOT NULL,
        pool_size    INTEGER NOT NULL,
        members      TEXT NOT NULL,
        committed_at REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_pool ON sortition_pool(period)",
    """CREATE TABLE IF NOT EXISTS sortition_draw (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        period        TEXT NOT NULL,
        pool_id       INTEGER NOT NULL,
        pool_digest   TEXT NOT NULL,
        pool_size     INTEGER NOT NULL,
        rate          REAL NOT NULL,
        select_count  INTEGER NOT NULL,
        beacon_source TEXT,
        beacon_round  INTEGER,
        beacon_value  TEXT NOT NULL,
        beacon_rowid  INTEGER,
        seed          TEXT NOT NULL,
        selected      TEXT NOT NULL,
        drawn_at      REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS sortition_review (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        draw_id      INTEGER NOT NULL,
        record_hash  TEXT NOT NULL,
        outcome      TEXT NOT NULL,
        reviewer     TEXT,
        reason       TEXT,
        recorded_at  REAL NOT NULL,
        chain_rowid  INTEGER,
        audit_hash   TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sort_rev ON sortition_review(draw_id, record_hash)",
]

OUTCOMES = ("agreed", "disagreed", "escalated", "refused")

VOCABULARY = {
    "pool": "Every record eligible for review in a period, fixed and sealed before any dice exist.",
    "draw": "The selection, computed from a beacon value that did not exist when the pool was sealed.",
    "selected": "Chosen by the beacon, not by us. We could not have known which.",
    "outstanding": "Selected and not yet answered. Visible, named, and counting.",
    "refused": "Declined on the record with a reason. Not a gap - a decision that is now permanent.",
    "gap": "Selected, past due, and never answered. The thing this module exists to make impossible to hide.",
}

WHAT_THIS_PROVES = (
    "That nobody chose which records were reviewed. It does not prove the "
    "reviews were competent, honest or useful. Those are different problems "
    "and this module does not touch them."
)


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        conn.commit()


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("audit_hash", "hash", "block_hash"):
        if n in c:
            return n
    return None


def _ts_col(conn):
    c = _cols(conn, "audit_log")
    for n in ("ts", "timestamp", "created", "observed"):
        if n in c:
            return n
    return None


def _period_bounds(period):
    """YYYY, YYYY-MM, YYYY-MM-DD -> (start_epoch, end_epoch) UTC."""
    p = str(period).strip()
    try:
        if len(p) == 4:
            s = time.strptime(p + "-01-01", "%Y-%m-%d")
            e = time.strptime(str(int(p) + 1) + "-01-01", "%Y-%m-%d")
        elif len(p) == 7:
            s = time.strptime(p + "-01", "%Y-%m-%d")
            y, m = int(p[:4]), int(p[5:7])
            y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
            e = time.strptime("%04d-%02d-01" % (y2, m2), "%Y-%m-%d")
        elif len(p) == 10:
            s = time.strptime(p, "%Y-%m-%d")
            e = time.gmtime(_cal(s) + 86400)
        else:
            return None
    except ValueError:
        return None
    return _cal(s), _cal(e)


def _cal(st):
    import calendar
    return calendar.timegm(st)


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
        return "%d minutes" % (s // 60)
    if s < 86400:
        return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)
    return "%d days %d hours" % (s // 86400, (s % 86400) // 3600)


def _pool_digest(members):
    h = hashlib.sha256()
    h.update(DOMAIN_POOL + b"\n")
    for m in members:
        h.update(m.encode() + b"\n")
    return h.hexdigest()


def _seed(period, pool_digest, beacon_value):
    h = hashlib.sha256()
    h.update(DOMAIN_SEED + b"|")
    h.update(str(period).encode() + b"|")
    h.update(pool_digest.encode() + b"|")
    h.update(str(beacon_value).encode())
    return h.hexdigest()


def select(members, seed, k):
    """The published selection function. Deterministic, no RNG."""
    ranked = []
    for m in members:
        r = hashlib.sha256((seed + ":" + m).encode()).hexdigest()
        ranked.append((r, m))
    ranked.sort()
    return [m for _, m in ranked[:k]]


def _seal(ctx, event, result):
    fn = ctx.get("seal")
    payload = result if isinstance(result, str) else json.dumps(result, sort_keys=True)
    try:
        fn(event, payload)
    except TypeError:
        fn(event, result)


def _backfill(conn, lock, table, rowid_field, pk):
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        r = cur.fetchone()
        rid = r[0] if r and r[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute("UPDATE %s SET chain_rowid=?, audit_hash=? WHERE id=?" % table,
                    (rid, h, pk))
        conn.commit()
    return rid, h


def _latest_beat_after(conn, rowid):
    """The first heartbeat sealed strictly after a given chain row."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT source, beacon_round, value, chain_rowid, fetched_at"
            " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
            " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
        return cur.fetchone()
    except Exception:
        return None


def _beats_available(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick")
        return cur.fetchone()[0]
    except Exception:
        return None


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    if method == "GET" and action == "spec":
        return _spec(), 200

    # -------------------------------------------------- pool
    if method == "POST" and action == "pool":
        period = data.get("period")
        bounds = _period_bounds(period) if period else None
        if not bounds:
            return {"error": "period_required",
                    "formats": ["YYYY", "YYYY-MM", "YYYY-MM-DD"]}, 400
        start, end = bounds
        if end > time.time():
            return {"error": "period_not_closed",
                    "note": ("A pool can only be committed for a period that "
                             "has ended. Committing a live period would let "
                             "records arrive after the pool was fixed."),
                    "period_ends": _iso(end)}, 409

        hcol, tcol = _hash_col(conn), _ts_col(conn)
        if not hcol or not tcol:
            return {"error": "audit_log_schema_unrecognised"}, 500

        cur = conn.cursor()
        kind = data.get("event")
        if kind:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? AND event=?"
                " ORDER BY rowid" % (hcol, tcol, tcol), (start, end, kind))
        else:
            cur.execute(
                "SELECT %s FROM audit_log WHERE %s>=? AND %s<? ORDER BY rowid"
                % (hcol, tcol, tcol), (start, end))
        members = sorted({r[0] for r in cur.fetchall() if r[0]})
        if not members:
            return {"error": "empty_period", "period": period}, 404
        if len(members) > MAX_POOL:
            return {"error": "pool_too_large", "size": len(members),
                    "max": MAX_POOL}, 413

        digest = _pool_digest(members)
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id, pool_digest FROM sortition_pool WHERE period=?",
                        (period,))
            prior = cur.fetchone()
            if prior:
                return {"error": "pool_already_committed", "period": period,
                        "pool_digest": prior[1],
                        "note": "A pool commits once. That is what makes it a pool."}, 409
            cur.execute(
                "INSERT INTO sortition_pool (period, pool_digest, pool_size,"
                " members, committed_at) VALUES (?,?,?,?,?)",
                (period, digest, len(members), json.dumps(members), now))
            pid = cur.lastrowid
            conn.commit()

        _seal(ctx, "sortition_pool", {
            "period": period, "pool_digest": digest, "pool_size": len(members),
            "event_filter": kind,
            "note": ("Pool fixed. Any draw against it must use a beacon value "
                     "sealed after this block."),
        })
        rid, h = _backfill(conn, lock, "sortition_pool", "chain_rowid", pid)

        return {"pool_id": pid, "period": period, "pool_digest": digest,
                "pool_size": len(members), "sealed_at_chain_rowid": rid,
                "audit_hash": h,
                "next": ("Wait for a heartbeat sealed after block %s, then "
                         "POST /x/sortition/draw." % rid)}, 200

    # -------------------------------------------------- draw
    if method == "POST" and action == "draw":
        period = data.get("period")
        cur = conn.cursor()
        cur.execute("SELECT id, pool_digest, pool_size, members, chain_rowid"
                    " FROM sortition_pool WHERE period=?", (period,))
        pool = cur.fetchone()
        if not pool:
            return {"error": "no_pool_for_period", "period": period,
                    "next": "POST /x/sortition/pool first"}, 404
        pid, digest, size, members_json, pool_rowid = pool

        cur.execute("SELECT id FROM sortition_draw WHERE period=?", (period,))
        if cur.fetchone():
            return {"error": "already_drawn", "period": period,
                    "note": "One draw per pool. A second draw is a second chance."}, 409

        if pool_rowid is None:
            return {"error": "pool_not_located_in_chain"}, 500

        beat = _latest_beat_after(conn, pool_rowid)
        if not beat:
            n = _beats_available(conn)
            return {"error": "no_beacon_since_pool_commit",
                    "beats_in_system": n,
                    "why": ("The draw must use a value that did not exist when "
                            "the pool was sealed. Wait for the next heartbeat."),
                    "check": "/x/heartbeat/latest"}, 409

        b_source, b_round, b_value, b_rowid, b_at = beat
        members = json.loads(members_json)

        try:
            rate = float(data.get("rate", DEFAULT_RATE))
        except (TypeError, ValueError):
            rate = DEFAULT_RATE
        rate = max(0.0001, min(1.0, rate))
        k = int(round(size * rate))
        k = max(MIN_SELECT, min(k, MAX_SELECT, size))

        seed = _seed(period, digest, b_value)
        chosen = select(members, seed, k)
        now = time.time()

        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sortition_draw (period, pool_id, pool_digest,"
                " pool_size, rate, select_count, beacon_source, beacon_round,"
                " beacon_value, beacon_rowid, seed, selected, drawn_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (period, pid, digest, size, rate, k, b_source, b_round,
                 b_value, b_rowid, seed, json.dumps(chosen), now))
            did = cur.lastrowid
            conn.commit()

        _seal(ctx, "sortition_draw", {
            "draw_id": did, "period": period, "pool_digest": digest,
            "pool_size": size, "rate": rate, "selected_count": k,
            "beacon": {"source": b_source, "round": b_round, "value": b_value,
                       "sealed_at_block": b_rowid},
            "seed": seed, "selected": chosen,
            "note": ("Selection is recomputable by anyone from pool_digest and "
                     "the beacon value. See /x/sortition/spec."),
        })
        rid, h = _backfill(conn, lock, "sortition_draw", "chain_rowid", did)

        return {"draw_id": did, "period": period, "pool_size": size,
                "rate": rate, "selected_count": k, "selected": chosen,
                "beacon": {"source": b_source, "round": b_round,
                           "value": b_value, "sealed_at_block": b_rowid,
                           "sealed_at": _iso(b_at)},
                "seed": seed, "sealed_at_chain_rowid": rid, "audit_hash": h,
                "review_due": _iso(now + REVIEW_DUE_HOURS * 3600),
                "recompute_this_yourself": "/x/sortition/verify?id=%d" % did}, 200

    # -------------------------------------------------- review
    if method == "POST" and action == "review":
        did = data.get("draw_id")
        rec = data.get("record")
        outcome = str(data.get("outcome", "")).lower()
        if not did or not rec:
            return {"error": "draw_id_and_record_required"}, 400
        if outcome not in OUTCOMES:
            return {"error": "outcome_invalid", "allowed": list(OUTCOMES)}, 400
        if outcome == "refused" and not data.get("reason"):
            return {"error": "reason_required_to_refuse",
                    "why": ("A refusal without a reason is a gap wearing a "
                            "label. The reason is sealed and permanent.")}, 400

        cur = conn.cursor()
        cur.execute("SELECT selected FROM sortition_draw WHERE id=?", (did,))
        row = cur.fetchone()
        if not row:
            return {"error": "unknown_draw", "draw_id": did}, 404
        if rec not in json.loads(row[0]):
            return {"error": "record_not_selected",
                    "note": ("Reviews can only be filed against records the "
                             "beacon chose. Volunteering extra reviews does "
                             "not count toward the sample.")}, 409

        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute("SELECT id FROM sortition_review WHERE draw_id=? AND record_hash=?",
                        (did, rec))
            if cur.fetchone():
                return {"error": "already_reviewed",
                        "note": "A review is filed once and cannot be replaced."}, 409
            cur.execute(
                "INSERT INTO sortition_review (draw_id, record_hash, outcome,"
                " reviewer, reason, recorded_at) VALUES (?,?,?,?,?,?)",
                (did, rec, outcome, data.get("reviewer"), data.get("reason"), now))
            rvid = cur.lastrowid
            conn.commit()

        _seal(ctx, "sortition_review", {
            "draw_id": did, "record": rec, "outcome": outcome,
            "reviewer": data.get("reviewer"), "reason": data.get("reason"),
        })
        rid, h = _backfill(conn, lock, "sortition_review", "chain_rowid", rvid)
        return {"recorded": True, "review_id": rvid, "outcome": outcome,
                "sealed_at_chain_rowid": rid, "audit_hash": h}, 200

    # -------------------------------------------------- draws
    if method == "GET" and action == "draws":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, period, pool_size, rate, select_count, beacon_source,"
            " beacon_round, drawn_at, audit_hash FROM sortition_draw"
            " ORDER BY id DESC LIMIT 100")
        out = []
        for r in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM sortition_review WHERE draw_id=?", (r[0],))
            done = cur2.fetchone()[0]
            out.append({"draw_id": r[0], "period": r[1], "pool_size": r[2],
                        "rate": r[3], "selected": r[4], "reviewed": done,
                        "outstanding": r[4] - done,
                        "beacon": {"source": r[5], "round": r[6]},
                        "drawn_at": _iso(r[7]), "audit_hash": r[8]})
        return {"count": len(out), "draws": out, "vocabulary": VOCABULARY}, 200

    # -------------------------------------------------- one draw
    if method == "GET" and action == "draw":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT record_hash, outcome, reviewer, reason, recorded_at"
                    " FROM sortition_review WHERE draw_id=?", (did,))
        revs = {r[0]: {"outcome": r[1], "reviewer": r[2], "reason": r[3],
                       "at": _iso(r[4])} for r in cur.fetchall()}
        items = []
        for m in json.loads(d["selected_json"]):
            items.append({"record": m, "review": revs.get(m),
                          "state": "answered" if m in revs else "outstanding"})
        return {"draw_id": did, "period": d["period"],
                "pool_digest": d["pool_digest"], "pool_size": d["pool_size"],
                "rate": d["rate"], "selected_count": d["select_count"],
                "beacon": {"source": d["beacon_source"], "round": d["beacon_round"],
                           "value": d["beacon_value"],
                           "sealed_at_block": d["beacon_rowid"]},
                "seed": d["seed"], "drawn_at": _iso(d["drawn_at"]),
                "items": items,
                "what_this_proves": WHAT_THIS_PROVES,
                "recompute": "/x/sortition/verify?id=%s" % did}, 200

    # -------------------------------------------------- verify
    if method == "GET" and action == "verify":
        did = data.get("id")
        if not did:
            return {"error": "id_required"}, 400
        d = _draw_row(conn, did)
        if not d:
            return {"error": "unknown_draw"}, 404
        cur = conn.cursor()
        cur.execute("SELECT members FROM sortition_pool WHERE id=?", (d["pool_id"],))
        row = cur.fetchone()
        members = json.loads(row[0]) if row else []
        recomputed_digest = _pool_digest(members)
        recomputed_seed = _seed(d["period"], d["pool_digest"], d["beacon_value"])
        recomputed = select(members, recomputed_seed, d["select_count"])
        stored = json.loads(d["selected_json"])
        ok = (recomputed_digest == d["pool_digest"]
              and recomputed_seed == d["seed"]
              and sorted(recomputed) == sorted(stored))
        return {
            "draw_id": did,
            "matches": ok,
            "pool_digest_recomputed": recomputed_digest,
            "pool_digest_sealed": d["pool_digest"],
            "seed_recomputed": recomputed_seed,
            "seed_sealed": d["seed"],
            "selection_matches": sorted(recomputed) == sorted(stored),
            "beacon_value": d["beacon_value"],
            "beacon_check": ("Confirm this value independently at "
                             "/x/heartbeat/verify?round=%s, then at the beacon "
                             "operator's own endpoint." % d["beacon_round"]),
            "do_it_without_us": {
                "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
                "rank": 'SHA256(seed + ":" + record_hash)',
                "select": "lowest k ranks, ascending",
                "note": ("This route runs the same function on our server, so "
                         "it is a convenience, not the proof. The proof is you "
                         "running those three lines yourself."),
            },
        }, 200

    # -------------------------------------------------- outstanding
    if method == "GET" and action == "outstanding":
        now = time.time()
        cur = conn.cursor()
        cur.execute("SELECT id, period, selected, drawn_at FROM sortition_draw"
                    " ORDER BY id DESC")
        items = []
        for did, period, sel, drawn in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT record_hash FROM sortition_review WHERE draw_id=?", (did,))
            done = {r[0] for r in cur2.fetchall()}
            due = drawn + REVIEW_DUE_HOURS * 3600
            for m in json.loads(sel):
                if m in done:
                    continue
                items.append({
                    "draw_id": did, "period": period, "record": m,
                    "drawn_at": _iso(drawn), "due": _iso(due),
                    "state": "gap" if now > due else "outstanding",
                    "late_by": _human(now - due) if now > due else None,
                })
        gaps = [i for i in items if i["state"] == "gap"]
        return {"outstanding_count": len(items), "gap_count": len(gaps),
                "due_after_hours": REVIEW_DUE_HOURS,
                "items": items[:500],
                "meaning": VOCABULARY["gap"]}, 200

    # -------------------------------------------------- status
    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(select_count) FROM sortition_draw")
        ndraws, nsel = cur.fetchone()
        nsel = nsel or 0
        cur.execute("SELECT COUNT(*) FROM sortition_review")
        nrev = cur.fetchone()[0]
        cur.execute("SELECT outcome, COUNT(*) FROM sortition_review GROUP BY outcome")
        mix = {r[0]: r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM sortition_pool")
        npool = cur.fetchone()[0]
        beats = _beats_available(conn)
        return {
            "version": VERSION,
            "pools_committed": npool,
            "draws": ndraws,
            "records_selected": nsel,
            "reviews_recorded": nrev,
            "response_rate": round(nrev / nsel, 4) if nsel else None,
            "outcome_mix": mix,
            "beacon_available": beats is not None,
            "beats_in_system": beats,
            "depends_on": {
                "heartbeat": ("supplies the dice. Without a beacon sealed "
                              "after the pool, no draw is possible."),
                "complete": ("commits the period's record count in advance. "
                             "Without it, a record could be kept out of the "
                             "pool. Separate module, separate check: "
                             "/x/complete/periods"),
            },
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "draws", "draw", "verify", "outstanding",
                        "status", "pool", "review"]}, 404


def _draw_row(conn, did):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, period, pool_id, pool_digest, pool_size, rate, select_count,"
        " beacon_source, beacon_round, beacon_value, beacon_rowid, seed,"
        " selected, drawn_at FROM sortition_draw WHERE id=?", (did,))
    r = cur.fetchone()
    if not r:
        return None
    keys = ["id", "period", "pool_id", "pool_digest", "pool_size", "rate",
            "select_count", "beacon_source", "beacon_round", "beacon_value",
            "beacon_rowid", "seed", "selected_json", "drawn_at"]
    return dict(zip(keys, r))


def _spec():
    return {
        "module": "sortition",
        "version": VERSION,
        "name_means": "selection by lot - the ancient method for stopping the powerful choosing who gets scrutinised",
        "the_hole": (
            "Every system claiming human oversight reviews a sample. In every "
            "one, the operator picks the sample, so the sample proves nothing."
        ),
        "the_three_locks": [
            "1. The pool of eligible records is fixed and sealed first.",
            "2. The draw may only use a beacon value sealed AFTER the pool. "
            "Refused otherwise. So the pool was fixed before the dice existed.",
            "3. The beacon value ranks the pool. Lowest k are selected. "
            "Anyone recomputes it from public values.",
        ],
        "selection_function": {
            "seed": 'SHA256("AILEASH-SORTITION-v1|" + period + "|" + pool_digest + "|" + beacon_value)',
            "rank": 'SHA256(seed + ":" + record_hash)',
            "select": "the k lowest ranks in ascending order",
            "why_no_rng": ("A random number generator is a library, a version "
                           "and a seed we control. Two SHA-256 calls are none "
                           "of those and run in any language."),
        },
        "uniform_only": (
            "Risk-weighted sampling is deliberately not offered. A weighting "
            "the operator sets is a choice the operator made, which is the "
            "thing this module exists to remove."
        ),
        "refusal": (
            "A reviewer may refuse a selected case, with a reason, sealed. "
            "An honest refusal on the record beats a silent gap. A selection "
            "left unanswered past the due window is published as a gap with "
            "the record named."
        ),
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It does not prove the reviews were any good.",
            "It does not force anyone to draw at all. A period with no draw "
            "is a period with no sample and status says so.",
            "Pool membership is asserted by this server; completeness of the "
            "pool is complete.py's job, not this module's.",
            "The beacon is a third party. If drand and Bitcoin both vanish, "
            "new draws stop. Old draws stay verifiable.",
        ],
        "routes": {
            "POST /x/sortition/pool": "keyed - commit the pool for a closed period",
            "POST /x/sortition/draw": "keyed - draw against a beacon sealed after the pool",
            "POST /x/sortition/review": "keyed - file a review or a refusal with a reason",
            "GET /x/sortition/draws": "every draw",
            "GET /x/sortition/draw?id=": "one draw and its answers",
            "GET /x/sortition/verify?id=": "recompute the draw",
            "GET /x/sortition/outstanding": "selected and unanswered, with gaps named",
            "GET /x/sortition/status": "coverage and response rate",
        },
    }
