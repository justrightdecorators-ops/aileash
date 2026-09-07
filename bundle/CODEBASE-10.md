# Codebase — part 10 of 30

Contains:
- `modules/ratchet.py`
- `modules/reconcile.py`
- `modules/register.py`


## `modules/ratchet.py`

615 lines, 25928 bytes

```python
"""
ratchet.py - time only runs one way for the machine.

WHAT THIS IS FOR
----------------
heartbeat.py proves WHEN a record can have been made. sortition.py proves
NOBODY CHOSE what got reviewed. This one proves an actor cannot move
backwards through time.

Every action an agent takes is bound to the beacon round current at the
moment it acted. Beacon rounds only ever increase. So an actor's actions
form a strictly rising ladder, and the rule is one line:

    an action carrying a beacon round at or below the actor's last
    recorded round is REFUSED.

WHAT THAT KILLS, WITHOUT A POLICY, A PROMPT OR A PROMISE
--------------------------------------------------------
BACKDATING     An agent cannot produce an action claiming to sit earlier
               than one it already took. The earlier round is already
               spent.
REPLAY         Capture a valid action and fire it again later: the round
               is stale and the digest is already on the ladder.
PRE-COMPUTATION
               An agent cannot prepare a batch of actions in advance,
               because it cannot know tomorrow's beacon values today. A
               round that has not been sealed here yet is refused.
REWIND         Restore an agent from an old snapshot to undo its history
               and its next action lands below the recorded floor. The
               ladder is in a chain the agent does not control, so
               restoring the agent does not restore its position.

REFUSALS ARE SEALED, NOT DROPPED
--------------------------------
This is the part that matters. A refused action is written into the chain
with the reason. An agent trying to rewind is the single most interesting
event this system can observe, and throwing it away as a 409 would be
throwing away the evidence. /x/ratchet/refusals is public.

HONEST LIMITS
-------------
- It binds an actor's actions to an order. It says nothing about whether
  any action was correct, authorised, or wise.
- An actor that simply stops acting cannot be forced to continue. Silence
  is visible (last_seen goes stale) but is not prevented.
- Two different actor ids are two different ladders. Anyone able to mint
  new actor ids can start a fresh ladder; that is an identity problem,
  handled by whatever issues the ids, not here.
- The floor is only as fine-grained as the beat cadence. At a five
  minute cadence, two actions inside the same beat are ordered by
  sequence, not by beacon time, and that is reported rather than dressed
  up.
- It depends on heartbeat. With no beats sealed, nothing can be admitted,
  and this module says so rather than waving actions through.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec      public  what this is and the exact admission rules
  GET  actor     public  ?id= - one actor's current rung and ladder
  GET  actors    public  every ladder, with staleness
  GET  refusals  public  every refused attempt, with reason. The good bit.
  GET  verify    public  ?id= - re-walk a ladder and report any break
  GET  status    public  coverage, admission and refusal counts
  POST act       keyed   submit an action. Admitted or refused; both sealed.
"""

import json
import time
import hashlib

VERSION = "1.0.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "actor"),
    ("GET", "actors"),
    ("GET", "refusals"),
    ("GET", "verify"),
    ("GET", "status"),
}

MAX_LAG_BEATS = 3          # how far behind the newest beat an action may be
MAX_ACTOR_LEN = 120
STALE_SECONDS = 3600

REASONS = {
    "ok": "Admitted. The round is ahead of this actor's last rung.",
    "no_beats": (
        "Refused: no beacon has been sealed on this server, so there is no "
        "time to bind to. Nothing is admitted on trust."),
    "round_unknown": (
        "Refused: that beacon round has not been sealed here. Either it has "
        "not happened yet - which would mean the actor knew a value before "
        "it existed - or this server has not observed it."),
    "round_not_advanced": (
        "Refused: the round is at or below this actor's last rung. This is "
        "the ratchet. An actor cannot move backwards through beacon time, "
        "whether by backdating, by replay, or by being restored from an "
        "older snapshot."),
    "round_too_stale": (
        "Refused: the round is further behind the current beat than the "
        "permitted lag. An action bound to old time is a replay or a very "
        "slow actor; both are refused and both are recorded."),
    "digest_replayed": (
        "Refused: this exact action digest is already on this actor's "
        "ladder. Identical work resubmitted is a replay by definition."),
    "bad_request": "Refused: malformed submission.",
}

WHAT_THIS_PROVES = (
    "That an actor's recorded actions only ever moved forward in a public "
    "time nobody controls. It does not prove any action was correct, "
    "authorised, or sensible."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS ratchet_rung (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        actor         TEXT NOT NULL,
        seq           INTEGER NOT NULL,
        beacon_round  INTEGER NOT NULL,
        beacon_value  TEXT,
        digest        TEXT NOT NULL,
        label         TEXT,
        at            REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rat_seq ON ratchet_rung(actor, seq)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rat_dig ON ratchet_rung(actor, digest)",
    "CREATE INDEX IF NOT EXISTS idx_rat_actor ON ratchet_rung(actor)",
    """CREATE TABLE IF NOT EXISTS ratchet_refusal (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        actor         TEXT NOT NULL,
        claimed_round INTEGER,
        last_round    INTEGER,
        digest        TEXT,
        reason        TEXT NOT NULL,
        at            REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_rat_ref ON ratchet_refusal(actor)",
]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        conn.commit()


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
        return "%d hours" % (s // 3600)
    return "%d days" % (s // 86400)


def _seal(ctx, action, payload):
    """server.py: seal(event, result, ts, api_key=None); event is a DICT
    carrying user_id; returns (audit_hash, block_index, key_seq)."""
    fn = ctx.get("seal")
    if fn is None:
        return None, None
    ts = time.time()
    event = {"user_id": "ratchet", "action": action, "amount": 0,
             "country": "UK", "device_id": "ratchet", "anomaly": 0,
             "device_risk": 0}
    result = dict(payload)
    result.setdefault("decision", "RATCHET")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)
    for call in (lambda: fn(event, result, ts),
                 lambda: fn(event, result, ts, None),
                 lambda: fn(event, result)):
        try:
            out = call()
        except TypeError:
            continue
        except Exception:
            return None, None
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return h, idx
    return None, None


def _newest_beat(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT beacon_round, value, fetched_at FROM heartbeat_tick"
                    " WHERE chain_rowid IS NOT NULL AND beacon_round IS NOT NULL"
                    " ORDER BY beacon_round DESC LIMIT 1")
        return cur.fetchone()
    except Exception:
        return None


def _beat(conn, rnd):
    try:
        cur = conn.cursor()
        cur.execute("SELECT beacon_round, value, fetched_at FROM heartbeat_tick"
                    " WHERE beacon_round=? AND chain_rowid IS NOT NULL LIMIT 1",
                    (rnd,))
        return cur.fetchone()
    except Exception:
        return None


def _beats_between(conn, low, high):
    """How many sealed beats sit in (low, high]. Used for the lag check."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick WHERE chain_rowid IS"
                    " NOT NULL AND beacon_round>? AND beacon_round<=?",
                    (low, high))
        return cur.fetchone()[0]
    except Exception:
        return 0


def _top(conn, actor):
    cur = conn.cursor()
    cur.execute("SELECT seq, beacon_round, digest, at FROM ratchet_rung"
                " WHERE actor=? ORDER BY seq DESC LIMIT 1", (actor,))
    return cur.fetchone()


def _refuse(ctx, conn, lock, actor, rnd, last, digest, reason, extra=None):
    now = time.time()
    with lock:
        cur = conn.cursor()
        cur.execute("INSERT INTO ratchet_refusal (actor, claimed_round,"
                    " last_round, digest, reason, at) VALUES (?,?,?,?,?,?)",
                    (actor, rnd, last, digest, reason, now))
        rid = cur.lastrowid
        conn.commit()
    h, idx = _seal(ctx, "ratchet_refused", {
        "kind": "ratchet_refusal", "actor": actor, "claimed_round": rnd,
        "last_admitted_round": last, "digest": digest, "reason": reason,
        "explanation": REASONS.get(reason, reason),
        "note": ("A refused action is sealed rather than discarded. An actor "
                 "attempting to move backwards is the most interesting event "
                 "this module can observe."),
    })
    if h or idx:
        with lock:
            conn.execute("UPDATE ratchet_refusal SET chain_rowid=?,"
                         " audit_hash=? WHERE id=?", (idx, h, rid))
            conn.commit()
    out = {
        "admitted": False,
        "reason": reason,
        "explanation": REASONS.get(reason, reason),
        "actor": actor,
        "claimed_round": rnd,
        "last_admitted_round": last,
        "refusal_sealed_at_block": idx,
        "refusal_audit_hash": h,
        "this_refusal_is_permanent": True,
        "public_record": "/x/ratchet/refusals",
    }
    if extra:
        out.update(extra)
    return out


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    if method == "GET" and action == "spec":
        return _spec(), 200

    # -------------------------------------------------- act
    if method == "POST" and action == "act":
        actor = str(data.get("actor") or "").strip().lower()[:MAX_ACTOR_LEN]
        digest = str(data.get("digest") or "").strip().lower()
        label = str(data.get("label") or "")[:200] or None
        rnd = data.get("round")

        if not actor:
            return {"error": "actor_required",
                    "note": "A stable identifier for the acting agent."}, 400
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return {"error": "digest_required",
                    "note": ("A SHA-256 of the action. The action itself never "
                             "leaves your system.")}, 400

        newest = _newest_beat(conn)
        if not newest:
            top = _top(conn, actor)
            return _refuse(ctx, conn, lock, actor, rnd,
                           top[1] if top else None, digest, "no_beats"), 503

        newest_round = newest[0]
        if rnd is None:
            rnd = newest_round          # bind to now if the caller does not say
        try:
            rnd = int(rnd)
        except (TypeError, ValueError):
            return {"error": "round_invalid"}, 400

        top = _top(conn, actor)
        last_round = top[1] if top else None
        last_seq = top[0] if top else 0

        if not _beat(conn, rnd):
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_unknown",
                           {"newest_sealed_round": newest_round}), 409

        if last_round is not None and rnd <= last_round:
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_not_advanced",
                           {"the_rule": ("beacon round must be strictly greater "
                                         "than the actor's last rung")}), 409

        lag = _beats_between(conn, rnd, newest_round)
        if lag > MAX_LAG_BEATS:
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_too_stale",
                           {"beats_behind": lag,
                            "max_lag_beats": MAX_LAG_BEATS,
                            "newest_sealed_round": newest_round}), 409

        cur = conn.cursor()
        cur.execute("SELECT seq FROM ratchet_rung WHERE actor=? AND digest=?",
                    (actor, digest))
        if cur.fetchone():
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "digest_replayed"), 409

        beat = _beat(conn, rnd)
        now = time.time()
        seq = last_seq + 1
        with lock:
            cur = conn.cursor()
            cur.execute("INSERT INTO ratchet_rung (actor, seq, beacon_round,"
                        " beacon_value, digest, label, at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (actor, seq, rnd, beat[1], digest, label, now))
            rid = cur.lastrowid
            conn.commit()

        h, idx = _seal(ctx, "ratchet_step", {
            "kind": "ratchet_step", "actor": actor, "seq": seq,
            "beacon_round": rnd, "beacon_value": beat[1], "digest": digest,
            "label": label, "previous_round": last_round,
            "note": ("Bound to a public beacon value the actor could not have "
                     "known before that round existed."),
        })
        if h or idx:
            with lock:
                conn.execute("UPDATE ratchet_rung SET chain_rowid=?,"
                             " audit_hash=? WHERE id=?", (idx, h, rid))
                conn.commit()

        return {
            "admitted": True, "actor": actor, "seq": seq,
            "beacon_round": rnd, "beacon_value": beat[1],
            "previous_round": last_round, "digest": digest,
            "sealed_at_block": idx, "audit_hash": h,
            "floor": ("This action cannot have been created before beacon "
                      "round %d at %s." % (rnd, _iso(beat[2]))),
            "ratchet": ("This actor can no longer act at or below round %d. "
                        "That door is shut permanently." % rnd),
            "verify_beacon": "/x/heartbeat/verify?round=%d" % rnd,
        }, 200

    # -------------------------------------------------- actor
    if method == "GET" and action == "actor":
        actor = str(data.get("id") or "").strip().lower()
        if not actor:
            return {"error": "id_required",
                    "usage": "/x/ratchet/actor?id=<actor>"}, 400
        cur = conn.cursor()
        cur.execute("SELECT seq, beacon_round, digest, label, at, chain_rowid,"
                    " audit_hash FROM ratchet_rung WHERE actor=? ORDER BY seq",
                    (actor,))
        rungs = cur.fetchall()
        if not rungs:
            return {"actor": actor, "rungs": 0,
                    "message": "No ladder for this actor."}, 404
        cur.execute("SELECT COUNT(*) FROM ratchet_refusal WHERE actor=?", (actor,))
        refused = cur.fetchone()[0]
        last = rungs[-1]
        age = time.time() - last[4]
        return {
            "actor": actor,
            "rungs": len(rungs),
            "current_round": last[1],
            "current_seq": last[0],
            "last_action_at": _iso(last[4]),
            "seconds_since": round(age, 1),
            "status": "current" if age < STALE_SECONDS else "silent",
            "refusals": refused,
            "ladder": [{"seq": r[0], "round": r[1], "digest": r[2],
                        "label": r[3], "at": _iso(r[4]), "block": r[5],
                        "audit_hash": r[6]} for r in rungs[-50:]],
            "floor_now": ("This actor cannot act at or below round %d."
                          % last[1]),
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    # -------------------------------------------------- actors
    if method == "GET" and action == "actors":
        now = time.time()
        cur = conn.cursor()
        cur.execute("SELECT actor, COUNT(*), MAX(beacon_round), MAX(at)"
                    " FROM ratchet_rung GROUP BY actor ORDER BY MAX(at) DESC")
        out = []
        for a, n, rnd, at in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM ratchet_refusal WHERE actor=?", (a,))
            out.append({"actor": a, "rungs": n, "current_round": rnd,
                        "last_action": _iso(at),
                        "silent_for": _human(now - at) if now - at > STALE_SECONDS else None,
                        "refusals": cur2.fetchone()[0]})
        return {"count": len(out), "actors": out,
                "note": ("Silence is visible but not prevented. An actor that "
                         "stops acting simply stops, and no design fixes "
                         "that.")}, 200

    # -------------------------------------------------- refusals
    if method == "GET" and action == "refusals":
        try:
            limit = min(int(data.get("limit", 100)), 500)
        except (TypeError, ValueError):
            limit = 100
        cur = conn.cursor()
        cur.execute("SELECT actor, claimed_round, last_round, digest, reason,"
                    " at, chain_rowid, audit_hash FROM ratchet_refusal"
                    " ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        mix = {}
        for r in rows:
            mix[r[4]] = mix.get(r[4], 0) + 1
        return {
            "count": len(rows),
            "by_reason": mix,
            "refusals": [{"actor": r[0], "claimed_round": r[1],
                          "last_admitted_round": r[2], "digest": r[3],
                          "reason": r[4], "explanation": REASONS.get(r[4], r[4]),
                          "at": _iso(r[5]), "block": r[6], "audit_hash": r[7]}
                         for r in rows],
            "why_this_is_public": (
                "A refused action is sealed rather than discarded, and the "
                "list is open. An actor attempting to move backwards through "
                "time is the single most interesting thing this system can "
                "see, and hiding it would defeat the point of building it."),
        }, 200

    # -------------------------------------------------- verify
    if method == "GET" and action == "verify":
        actor = str(data.get("id") or "").strip().lower()
        if not actor:
            return {"error": "id_required"}, 400
        cur = conn.cursor()
        cur.execute("SELECT seq, beacon_round, beacon_value, digest FROM"
                    " ratchet_rung WHERE actor=? ORDER BY seq", (actor,))
        rungs = cur.fetchall()
        if not rungs:
            return {"error": "unknown_actor", "actor": actor}, 404
        breaks = []
        prev_seq = 0
        prev_round = None
        seen = set()
        for seq, rnd, val, dig in rungs:
            if seq != prev_seq + 1:
                breaks.append({"at_seq": seq, "fault": "sequence_gap",
                               "expected": prev_seq + 1})
            if prev_round is not None and rnd <= prev_round:
                breaks.append({"at_seq": seq, "fault": "round_did_not_advance",
                               "round": rnd, "previous": prev_round})
            if dig in seen:
                breaks.append({"at_seq": seq, "fault": "duplicate_digest"})
            b = _beat(conn, rnd)
            if not b:
                breaks.append({"at_seq": seq, "fault": "beacon_round_not_sealed",
                               "round": rnd})
            elif b[1] != val:
                breaks.append({"at_seq": seq, "fault": "beacon_value_mismatch",
                               "round": rnd})
            seen.add(dig)
            prev_seq, prev_round = seq, rnd
        return {
            "actor": actor, "rungs": len(rungs), "intact": not breaks,
            "breaks": breaks,
            "checked": ["sequence has no gaps",
                        "beacon round strictly increases",
                        "no digest appears twice",
                        "each rung's beacon value matches the sealed beat"],
            "do_it_without_us": (
                "Every beacon round on the ladder is re-fetchable from the "
                "beacon operator. Confirm each value there, then confirm each "
                "audit_hash is in the chain at /api/verify-chain. Neither step "
                "needs our cooperation."),
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    # -------------------------------------------------- status
    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT actor) FROM ratchet_rung")
        rungs, actors = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM ratchet_refusal")
        refused = cur.fetchone()[0]
        cur.execute("SELECT reason, COUNT(*) FROM ratchet_refusal GROUP BY reason")
        mix = {r[0]: r[1] for r in cur.fetchall()}
        newest = _newest_beat(conn)
        return {
            "version": VERSION,
            "actors": actors, "rungs_admitted": rungs,
            "actions_refused": refused,
            "refusals_by_reason": mix,
            "current_beacon_round": newest[0] if newest else None,
            "beacon_available": newest is not None,
            "max_lag_beats": MAX_LAG_BEATS,
            "depends_on": {
                "heartbeat": ("supplies the time. With no beats sealed, "
                              "nothing is admitted - actions are refused "
                              "rather than waved through on trust."),
            },
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "actor", "actors", "refusals", "verify",
                        "status", "act"]}, 404


def _spec():
    return {
        "module": "ratchet",
        "version": VERSION,
        "one_line": "Time only runs one way for the machine.",
        "the_rule": (
            "An action carrying a beacon round at or below the actor's last "
            "recorded round is refused. Beacon rounds only increase, so an "
            "actor's ladder only rises."),
        "what_it_kills": {
            "backdating": "the earlier round is already spent",
            "replay": "stale round, and the digest is already on the ladder",
            "pre_computation": ("an unsealed future round is refused, and "
                                "nobody can know a beacon value early"),
            "rewind": ("the ladder lives in a chain the actor does not "
                       "control, so restoring an agent from a snapshot does "
                       "not restore its position"),
        },
        "admission_rules_in_order": [
            "1. A beat must exist. No beats, nothing admitted.",
            "2. The claimed round must already be sealed here.",
            "3. The round must be strictly above the actor's last rung.",
            "4. The round must be within %d beats of the newest." % MAX_LAG_BEATS,
            "5. The digest must not already be on this actor's ladder.",
        ],
        "refusals_are_sealed": (
            "A refused action is written into the chain with its reason and "
            "published at /x/ratchet/refusals. Discarding it would throw away "
            "the most interesting evidence the system can produce."),
        "privacy": (
            "Only a SHA-256 of the action is submitted. The action itself, "
            "its inputs and its outputs never leave the caller's system."),
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It proves order, not correctness, authority or good judgement.",
            "An actor that stops acting is visible but not prevented.",
            "New actor ids start new ladders; identity is not this module's "
            "problem and it does not pretend otherwise.",
            "Within a single beat, actions are ordered by sequence rather "
            "than by beacon time. At a five minute cadence that is a five "
            "minute grain, and it is reported rather than dressed up.",
        ],
        "routes": {
            "POST /x/ratchet/act": "keyed - submit an action digest",
            "GET /x/ratchet/actor?id=": "one ladder",
            "GET /x/ratchet/actors": "every ladder",
            "GET /x/ratchet/refusals": "every refused attempt and why",
            "GET /x/ratchet/verify?id=": "re-walk a ladder",
            "GET /x/ratchet/status": "counts and current round",
        },
    }

```


## `modules/reconcile.py`

440 lines, 20123 bytes

```python
"""
Reconciliation notary - /x/reconcile/<action>

THE PROBLEM THIS ATTACKS
------------------------
A sealed chain proves records were not altered after the fact. It does not
prove they were true when written. An operator who seals fiction on time has
a tamper-evident chain of fiction. Every honest person in this market knows
that, and almost nobody says it.

You cannot prove truth from outside a system. What you CAN do is what real
auditors do: substantive testing. Take the sealed claim, go to the operator's
own live system, and check whether the two agree - then seal the result of
that check, including the failures.

WHY THIS ONE IS DIFFERENT
-------------------------
The sample is fixed before the operator sees it.

/plan derives a selection seed from the current chain tip - a value the
operator cannot predict in advance and cannot change afterwards without
breaking the chain - picks the records to be tested, and seals that selection
BEFORE any data is requested. Only then are the record identifiers returned.

So the operator cannot choose which records get examined, cannot prepare only
the flattering ones, and cannot quietly drop a test that came back badly:
every planned run is sealed at the moment it is planned, and a plan with no
submitted result is visible forever as an abandoned test.

Mismatches are sealed with the same permanence as matches. That is the whole
design. A reconciliation system that can bury its own failures is decoration.

WHAT A PASS ACTUALLY MEANS
--------------------------
That two systems the operator controls agree with each other, on records the
operator could not choose, at a time the operator could not pick.

That is not proof of truth. An operator who fabricates consistently across
every system, in real time, without knowing what will be sampled, will pass.
What it does is raise the cost of lying from "edit one database" to
"maintain a coherent parallel reality across independent systems indefinitely,
under unpredictable sampling, with every failure sealed permanently."

That is the honest claim. It is also, as far as I know, more than anyone else
in this market is doing.

HONEST LIMITS
-------------
- Consistency is not truth. Two agreeing systems can both be wrong.
- The operator supplies the comparison data. This tests their systems against
  each other, not against the world.
- Sampling only covers what has been sealed. It cannot find a decision that
  was never recorded at all - gapless receipts are what cover that.
- A high match rate on a badly chosen field proves nothing. Reconcile the
  fields that would hurt to get wrong.

    POST /x/reconcile/plan     sample_size, field  - seals the selection first
    POST /x/reconcile/submit   run_id, results     - seals the comparison
    GET  /x/reconcile/run?id=RUN-XXXXXXXX
    GET  /x/reconcile/score
    GET  /x/reconcile/list
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.1"
MAX_SAMPLE = 200

# Planning and submitting stay keyed - they touch an operator's own records.
# What is public is the part that decides whether any of it means anything:
# that the sample was fixed before the data was asked for, and that failures
# were sealed as permanently as passes.
PUBLIC = {("GET", "public"), ("GET", "proof")}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS reconcile_runs(run_id TEXT PRIMARY KEY,api_key TEXT,field TEXT,seed TEXT,planned REAL,submitted REAL,sample_size INTEGER,matched INTEGER,mismatched INTEGER,missing INTEGER,status TEXT DEFAULT 'planned',block_ids TEXT,detail TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_rec_key ON reconcile_runs(api_key)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, rid, action, detail):
    ts = time.time()
    ev = {"user_id": "rec:" + rid, "action": "reconcile_" + action, "amount": 0,
          "country": "UK", "device_id": "reconcile", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RECONCILE_SEALED", "score": 0, "reconcile_action": action,
           "reconcile_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _plan(ctx, api_key, data):
    try:
        n = int(data.get("sample_size", 25))
    except Exception:
        return {"error": "invalid_sample_size"}, 400
    if n < 1 or n > MAX_SAMPLE:
        return {"error": "sample_size_out_of_range", "max": MAX_SAMPLE}, 400
    field = str(data.get("field", "decision")).strip()[:60] or "decision"

    with ctx["lock"]:
        tiprow = ctx["conn"].execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        rows = ctx["conn"].execute("SELECT id,user_id,result_json,ts FROM audit_log WHERE api_key=? ORDER BY id ASC", (api_key,)).fetchall()

    if not rows:
        return {"error": "nothing_to_reconcile",
                "message": "No sealed records under this key yet."}, 400

    tip = tiprow[0] if tiprow else "GENESIS"
    ts = time.time()
    # Seed is bound to the chain tip. The operator cannot know it before the
    # records exist, and cannot alter it afterwards without breaking the chain.
    seed = _sha(tip + ":" + str(int(ts)) + ":" + field + ":" + str(n))

    # Deterministic selection from the seed - reproducible by anyone holding it.
    scored = sorted(rows, key=lambda r: _sha(seed + ":" + str(r[0])))
    picked = scored[:min(n, len(scored))]

    rid = "RUN-" + seed[:8].upper()
    block_ids = [p[0] for p in picked]

    sample = []
    for bid, uid, res_json, bts in picked:
        try:
            r = json.loads(res_json)
            sealed_val = r.get(field)
        except Exception:
            sealed_val = None
        sample.append({"block_index": bid, "record_id": uid,
                       "sealed_at": _iso(bts),
                       "sealed_value_sha256": _sha(str(sealed_val))})

    detail = ("field=" + field + ";sample_size=" + str(len(picked)) +
              ";seed=" + seed + ";from_tip=" + tip +
              ";blocks=" + ",".join(str(b) for b in block_ids[:60]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "planned", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO reconcile_runs(run_id,api_key,field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,block_ids,detail) VALUES(?,?,?,?,?,NULL,?,NULL,NULL,NULL,'planned',?,NULL)",
                            (rid, api_key, field, seed, ts, len(picked), json.dumps(block_ids)))
        ctx["conn"].commit()

    return {"run_id": rid, "field": field, "sample_size": len(picked),
            "seed": seed, "derived_from_tip": tip, "planned_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "sample": sample,
            "next": "Fetch these record_ids from your own live system and POST them to /x/reconcile/submit",
            "note": "This selection is now sealed. It cannot be changed, and an unsubmitted plan stays visible as an abandoned test."}, 200


def _submit(ctx, api_key, data):
    rid = str(data.get("run_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,status,block_ids FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_run_id"}, 404
    if row[2] != "planned":
        return {"error": "already_submitted",
                "message": "A run is reconciled once. Re-running until it passes is not reconciliation."}, 400

    results = data.get("results")
    if not isinstance(results, dict) or not results:
        return {"error": "results_required",
                "message": "Send {block_index: live_value} from your own system."}, 400

    field = row[0]
    block_ids = json.loads(row[3])

    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT id,user_id,result_json FROM audit_log WHERE id IN (" + ",".join("?" * len(block_ids)) + ")", block_ids).fetchall()

    sealed = {}
    for bid, uid, res_json in rows:
        try:
            sealed[bid] = json.loads(res_json).get(field)
        except Exception:
            sealed[bid] = None

    matched, mismatched, missing = [], [], []
    for bid in block_ids:
        key = str(bid)
        if key not in results:
            missing.append({"block_index": bid})
            continue
        live = results[key]
        want = sealed.get(bid)
        if str(live).strip().lower() == str(want).strip().lower():
            matched.append(bid)
        else:
            mismatched.append({"block_index": bid,
                               "sealed_value": want,
                               "live_value": live})

    ts = time.time()
    rate = round(100 * len(matched) / len(block_ids), 2) if block_ids else 0
    detail = ("field=" + field + ";matched=" + str(len(matched)) +
              ";mismatched=" + str(len(mismatched)) + ";missing=" + str(len(missing)) +
              ";match_rate=" + str(rate) +
              ";mismatch_blocks=" + ",".join(str(m["block_index"]) for m in mismatched[:40]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "reconciled", detail)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE reconcile_runs SET submitted=?,matched=?,mismatched=?,missing=?,status='reconciled',detail=? WHERE run_id=? AND api_key=?",
                            (ts, len(matched), len(mismatched), len(missing), json.dumps({"mismatched": mismatched[:100], "missing": missing[:100]}), rid, api_key))
        ctx["conn"].commit()

    out = {"run_id": rid, "field": field, "sample_size": len(block_ids),
           "matched": len(matched), "mismatched": len(mismatched),
           "missing": len(missing), "match_rate_pct": rate,
           "reconciled_at": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "This result is sealed whichever way it went. It cannot be withdrawn."}
    if mismatched:
        out["mismatches"] = mismatched[:20]
        out["flag"] = "sealed records and live system disagree on " + str(len(mismatched)) + " of " + str(len(block_ids))
    if missing:
        out["missing_detail"] = "records the live system did not return - a gap, not a match"
    return out, 200


def _run(ctx, api_key, rid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,detail FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_run_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("rec:" + rid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("reconcile_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    total = row[4] or 0
    out = {"run_id": rid.upper(), "field": row[0], "seed": row[1],
           "planned": _iso(row[2]), "submitted": _iso(row[3]),
           "sample_size": total, "matched": row[5], "mismatched": row[6],
           "missing": row[7], "status": row[8], "events": events,
           "ordering_proof": "The plan block precedes the result block. The sample was fixed before any data was requested."}
    if row[9]:
        try:
            out["detail"] = json.loads(row[9])
        except Exception:
            pass
    if row[8] == "planned":
        out["flag"] = "planned but never submitted - an abandoned test, visible permanently"
    return out, 200


def _score(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT sample_size,matched,mismatched,missing,status,planned FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 500", (api_key,)).fetchall()
    if not rows:
        return {"runs": 0, "note": "No reconciliation runs on record."}, 200
    done = [r for r in rows if r[4] == "reconciled"]
    abandoned = len(rows) - len(done)
    tested = sum(r[0] or 0 for r in done)
    ok = sum(r[1] or 0 for r in done)
    bad = sum(r[2] or 0 for r in done)
    gone = sum(r[3] or 0 for r in done)
    out = {"runs": len(rows), "reconciled": len(done), "abandoned": abandoned,
           "records_tested": tested, "matched": ok, "mismatched": bad,
           "missing": gone,
           "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
           "last_run": _iso(rows[0][5])}
    if abandoned:
        out["flag"] = str(abandoned) + " planned run(s) never submitted"
    return out, 200


def _list(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,missing,status FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 200", (api_key,)).fetchall()
    return {"count": len(rows),
            "runs": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                      "submitted": _iso(r[3]), "sample_size": r[4],
                      "matched": r[5], "mismatched": r[6], "missing": r[7],
                      "status": r[8]} for r in rows]}, 200


def _public(ctx):
    """The reconciliation record, readable without a key.

    Counts only. No record identifiers, no field values, no operator
    identity. What a stranger gets is the three numbers that cannot be
    flattered: how many runs were reconciled, how many disagreed, and how
    many were planned and then quietly abandoned.

    Abandoned runs are the important one. A planned run is sealed at the
    moment it is planned, so a test that came back badly and was dropped
    cannot be deleted - it sits here forever as a plan with no result.
    """
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,"
            "missing,status FROM reconcile_runs ORDER BY planned DESC LIMIT 200").fetchall()

    done = [r for r in rows if r[8] == "reconciled"]
    abandoned = [r for r in rows if r[8] != "reconciled"]
    tested = sum(r[4] or 0 for r in done)
    ok = sum(r[5] or 0 for r in done)
    bad = sum(r[6] or 0 for r in done)
    gone = sum(r[7] or 0 for r in done)

    out = {
        "runs": len(rows),
        "reconciled": len(done),
        "abandoned": len(abandoned),
        "records_tested": tested,
        "matched": ok,
        "mismatched": bad,
        "missing": gone,
        "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
        "recent": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                    "submitted": _iso(r[3]), "sample_size": r[4],
                    "matched": r[5], "mismatched": r[6], "missing": r[7],
                    "status": r[8]} for r in rows[:50]],
        "check_any_of_them": "/x/reconcile/proof?id=RUN-XXXXXXXX",
        "what_is_being_shown": "Not that the records are true. That the sample was fixed "
                               "before the data was requested, and that what came back was "
                               "sealed either way.",
        "what_a_mismatch_means": "The sealed record and the operator's own live system "
                                 "disagreed. It is published because a reconciliation system "
                                 "that can bury its own failures is decoration.",
    }
    if abandoned:
        out["flag"] = (str(len(abandoned)) + " run(s) planned and never submitted. A sample was "
                       "fixed, and no result was ever sealed against it.")
    return out, 200


def _proof(ctx, rid):
    """The ordering, straight out of the chain, without a key.

    Both events are already sealed under a public identifier, so this route
    reveals nothing the chain does not already carry. It just makes the one
    claim that matters legible: the plan block comes before the result block.
    """
    rid = (rid or "").strip().upper()
    if not rid:
        return {"error": "id_required"}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status "
            "FROM reconcile_runs WHERE run_id=?", (rid,)).fetchone()
        blocks = ctx["conn"].execute(
            "SELECT id,ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC",
            ("rec:" + rid,)).fetchall()
    if not row:
        return {"error": "unknown_run_id", "list": "/x/reconcile/public"}, 404

    events = []
    plan_block = result_block = None
    for bid, bts, res, ah in blocks:
        try:
            r = json.loads(res)
        except Exception:
            continue
        what = r.get("reconcile_action")
        events.append({"event": what, "at": _iso(bts), "block_index": bid,
                       "sealed_in_chain": ah, "sealed_detail": r.get("detail")})
        if what == "planned" and plan_block is None:
            plan_block = bid
        if what == "reconciled" and result_block is None:
            result_block = bid

    ordered = (plan_block is not None and result_block is not None
               and plan_block < result_block)

    out = {"run_id": rid, "field": row[0], "status": row[8],
           "seed": row[1], "planned_at": _iso(row[2]), "submitted_at": _iso(row[3]),
           "sample_size": row[4], "matched": row[5], "mismatched": row[6],
           "missing": row[7],
           "plan_block_index": plan_block, "result_block_index": result_block,
           "selection_precedes_result": ordered,
           "events": events,
           "how_to_check_this_yourself": [
               "The seed is derived from the chain tip at planning time, which the operator "
               "cannot predict in advance or change afterwards without breaking the chain.",
               "The plan block seals which records were selected, and its detail is above.",
               "The result block seals what came back. Compare the two block indices.",
               "A lower plan index than result index means the sample was fixed before any "
               "data was requested. That is the whole claim, and it is the only one made."],
           "what_this_does_not_prove": "That the records are true. Two systems the operator "
                                       "controls agreeing with each other is consistency, not "
                                       "truth."}
    if row[8] != "reconciled":
        out["flag"] = ("planned and never submitted. The selection is sealed and no result "
                       "was ever put against it.")
    elif not ordered:
        out["flag"] = ("the plan block does not precede the result block. That should be "
                       "impossible and it is the finding.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "plan":
            return _plan(ctx, api_key, data)
        if action == "submit":
            return _submit(ctx, api_key, data)
    else:
        if action == "public":
            return _public(ctx)
        if action == "proof":
            return _proof(ctx, str((data or {}).get("id", "")))
        if action == "score":
            return _score(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "run":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _run(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action,
            "GET": ["public", "proof", "score", "list", "run"],
            "POST": ["plan", "submit"]}, 404

```


## `modules/register.py`

1517 lines, 61178 bytes

```python
"""
modules/register.py  v1.0.0  —  The Safe AI Registry

What makes this different from every other registry, trust mark and
certification list:

  Ordinary registries are mutable databases. The operator can insert an
  entry, back-date it, quietly delist someone, or revoke a seal and leave
  no trace. You must trust the registrar absolutely.

  This one publishes proofs about its own behaviour:

    * ABSENCE   — prove a domain was NOT listed on a given date.
                  Not "we have no record": a sorted-tree proof showing two
                  adjacent leaves with consecutive indices, so nothing can
                  sit between them.

    * APPEND-ONLY — RFC 6962 consistency proof that the register at any
                  past size is a prefix of the register now. A back-dated
                  listing is arithmetically impossible to hide, and the
                  proof verifies with any standard Certificate Transparency
                  verifier, not one of ours.

    * REVOCATION — a delisted entry does not vanish. The revocation is
                  sealed and the history stays readable. "Listed from D1,
                  revoked D2, reason R" is permanent.

  The registrar is auditable against the registrar. That is the product.

CONSENT
  No domain is ever listed because the operator typed it in. A domain
  lists itself by proving it controls the domain:

    1. POST /x/register/challenge {"domain": "example.com"}
         -> returns a one-time token, sealed.
    2. The domain serves that token at
         https://example.com/.well-known/aileash-register.txt
       (or puts a `Register-Token:` line in its ai.txt).
    3. POST /x/register/claim {"domain": "example.com"}
         -> we fetch, verify the token, run the checks, seal the result
            and list it.

  Peers on the witness network are not auto-listed. A listing they
  claimed themselves is better evidence than one we granted them.

VOCABULARY  (deliberately not "compliant", "covered" or "certified")
    unverified    claimed, checks not yet run
    checks-passed every check in the suite returned pass, on the date shown
    checks-failed at least one check did not pass
    stale         last successful check is older than STALE_AFTER_DAYS
    withdrawn     the domain asked to be removed
    revoked       the operator removed it; reason sealed

Module contract:
    handle(method, action, data, api_key, ctx) -> (dict, status)
    PUBLIC is a set of (METHOD, action) tuples
    ctx exposes conn, lock, seal
    every sealed event carries a user_id
    no seal is wrapped in a bare except
"""

import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.2.0"
SUITE_VERSION = "oaas-checks-1"

# ---------------------------------------------------------------- constants

STALE_AFTER_DAYS = 90
CHALLENGE_TTL_SECONDS = 86400
MAX_FETCH_BYTES = 512 * 1024
FETCH_TIMEOUT = 8
WELL_KNOWN_PATH = "/.well-known/aileash-register.txt"
AI_TXT_PATHS = ["/.well-known/ai.txt", "/ai.txt"]
AI_TXT_PATH = AI_TXT_PATHS[0]   # the one quoted in guidance
FIELD_ALIASES = {
    "chain_tip_url": ["chain-tip-url", "chain-head", "witness-tip", "chain-anchor"],
    "verifier": ["verifier", "verify-chain", "consistency-proof", "self-check"],
    "contact": ["contact", "security-contact"],
}

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

STATUS_UNVERIFIED = "unverified"
STATUS_PASSED = "checks-passed"
STATUS_FAILED = "checks-failed"
STATUS_STALE = "stale"
STATUS_WITHDRAWN = "withdrawn"
STATUS_REVOKED = "revoked"

LIVE_STATUSES = (STATUS_UNVERIFIED, STATUS_PASSED, STATUS_FAILED, STATUS_STALE)

# Domain-separation prefixes. Two different trees answer two different
# questions and their roots deliberately never match.
LEAF_PREFIX = b"\x00"          # RFC 6962 ordered tree, over events
NODE_PREFIX = b"\x01"
SORTED_LEAF = b"AILEASH-REGISTER-LEAF-v1\x00"    # sorted tree, over domains
SORTED_NODE = b"AILEASH-REGISTER-NODE-v1\x00"

VOCABULARY = {
    STATUS_UNVERIFIED: "The domain proved control and is listed. The check suite has not been run against it yet.",
    STATUS_PASSED: "Every check in suite %s returned pass on the date shown. This describes what the checks observed on that date and nothing else." % SUITE_VERSION,
    STATUS_FAILED: "At least one check did not pass. The failing check names are published.",
    STATUS_STALE: "The last successful check is more than %d days old. Nothing was withdrawn; the evidence simply aged." % STALE_AFTER_DAYS,
    STATUS_WITHDRAWN: "The domain asked to be removed. The listing history remains readable.",
    STATUS_REVOKED: "The operator removed the listing. The reason is sealed alongside it and the history remains readable.",
}

WHAT_THIS_IS_NOT = [
    "Not a certification. Nobody has been certified by anyone.",
    "Not a statement that any law applies to a listed domain, or that a listed domain satisfies it. Whether a regulation applies to an organisation is a question for that organisation's own advisers.",
    "Not an audit. No third party has audited this registry or any domain on it.",
    "Not a claim about anything a domain did not seal. A check observes what is served at a URL at a moment in time.",
]

MESSAGES = {
    "domain_required": "domain is required",
    "bad_domain": "domain must be a bare hostname, e.g. example.com — no scheme, no path",
    "no_challenge": "no live challenge for this domain. POST /x/register/challenge first.",
    "challenge_expired": "challenge expired. Request a new one.",
    "token_not_found": "the token was not served at either location",
    "not_listed": "this domain has no entry in the register",
    "already_final": "this entry is withdrawn or revoked and cannot be changed",
    "no_checkpoint": "no checkpoint has been sealed at or before that time",
    "seal_failed": "the register could not seal this event, so nothing was written. Retry.",
}

PUBLIC = {
    ("GET", "spec"),
    ("GET", "list"),
    ("GET", "entry"),
    ("GET", "history"),
    ("GET", "absence"),
    ("GET", "consistency"),
    ("GET", "inclusion"),
    ("GET", "checkpoints"),
    ("GET", "roots"),
    ("GET", "sealcheck"),
    ("GET", "tokens"),
    ("GET", "vocabulary"),
    ("POST", "challenge"),
    ("POST", "claim"),
    ("POST", "recheck"),
    ("POST", "withdraw"),
}


# ---------------------------------------------------------------- utilities

def _now():
    return time.time()


def _iso(ts):
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_when(s):
    """Accept an ISO date, an ISO datetime or an epoch. Return epoch seconds."""
    if s is None or s == "":
        return None
    s = str(s).strip()
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    t = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            if fmt is None:
                d = datetime.fromisoformat(t)
            else:
                d = datetime.strptime(t, fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.timestamp()
        except (TypeError, ValueError):
            continue
    return None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _clean_domain(raw):
    if not raw:
        return None
    d = str(raw).strip().lower()
    if "://" in d:
        d = urllib.parse.urlsplit(d).netloc or d
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if d.startswith("www."):
        d = d[4:]
    if "@" in d or ":" in d:
        return None
    if not DOMAIN_RE.match(d):
        return None
    return d


# ------------------------------------------------------------------- fetch
# Same posture as witness.py: http/https only, ports 80/443, resolve first,
# reject non-public addresses, no redirects, hard timeout, size cap.

def _is_public_addr(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as e:
        return False, "dns_failed: %s" % e
    if not infos:
        return False, "dns_empty"
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, "unparseable_address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False, "non_public_address"
    return True, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url):
    """Return (ok, body_text_or_none, note_dict)."""
    parts = urllib.parse.urlsplit(url)
    note = {"url": url, "fetched_at": _iso(_now())}
    if parts.scheme not in ("http", "https"):
        note["error"] = "scheme_not_allowed"
        return False, None, note
    if parts.port not in (None, 80, 443):
        note["error"] = "port_not_allowed"
        return False, None, note
    host = parts.hostname
    if not host:
        note["error"] = "no_host"
        return False, None, note
    ok, why = _is_public_addr(host)
    if not ok:
        note["error"] = why
        return False, None, note

    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers={
        "User-Agent": "AILeash-Register/%s (+https://sebbi.pro/x/register/spec)" % VERSION,
        "Accept": "text/plain, application/json, */*",
    })
    started = time.time()
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            note["http_status"] = resp.getcode()
            raw = resp.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as e:
        note["http_status"] = e.code
        note["error"] = "http_%s" % e.code
        note["took_ms"] = int((time.time() - started) * 1000)
        return False, None, note
    except Exception as e:
        note["error"] = "fetch_failed: %s" % type(e).__name__
        note["took_ms"] = int((time.time() - started) * 1000)
        return False, None, note

    note["took_ms"] = int((time.time() - started) * 1000)
    if len(raw) > MAX_FETCH_BYTES:
        note["error"] = "too_large"
        return False, None, note
    note["bytes"] = len(raw)
    note["body_sha256"] = _sha(raw)
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:
        note["error"] = "undecodable"
        return False, None, note
    return True, text, note


# ------------------------------------------------------------------ merkle

def _ct_leaf(data_bytes):
    return hashlib.sha256(LEAF_PREFIX + data_bytes).digest()


def _ct_node(l, r):
    return hashlib.sha256(NODE_PREFIX + l + r).digest()


def _ct_root(leaves):
    """RFC 6962 root over an ordered list of leaf digests (bytes)."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaves[0]
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return _ct_node(_ct_root(leaves[:k]), _ct_root(leaves[k:]))


def _ct_inclusion(leaves, index):
    """RFC 6962 inclusion proof for leaves[index]. Returns list of hex."""
    def walk(sub, i):
        if len(sub) <= 1:
            return []
        k = 1
        while k * 2 < len(sub):
            k *= 2
        if i < k:
            return walk(sub[:k], i) + [_ct_root(sub[k:])]
        return walk(sub[k:], i - k) + [_ct_root(sub[:k])]
    return [h.hex() for h in walk(leaves, index)]


def _ct_consistency(leaves, m):
    """RFC 6962 consistency proof between size m and size len(leaves)."""
    n = len(leaves)
    if m <= 0 or m > n:
        return None

    def subproof(m_, sub, is_complete):
        if m_ == len(sub):
            return [] if is_complete else [_ct_root(sub)]
        k = 1
        while k * 2 < len(sub):
            k *= 2
        if m_ <= k:
            return subproof(m_, sub[:k], is_complete) + [_ct_root(sub[k:])]
        return subproof(m_ - k, sub[k:], False) + [_ct_root(sub[:k])]

    return [h.hex() for h in subproof(m, leaves, True)]


def _sorted_leaf(value):
    return hashlib.sha256(SORTED_LEAF + value.encode("utf-8")).digest()


def _sorted_root(leaves):
    """Sorted tree. Odd nodes are promoted, never self-paired."""
    if not leaves:
        return hashlib.sha256(SORTED_LEAF + b"EMPTY").digest()
    level = list(leaves)
    while len(level) > 1:
        nxt = []
        i = 0
        while i + 1 < len(level):
            nxt.append(hashlib.sha256(SORTED_NODE + level[i] + level[i + 1]).digest())
            i += 2
        if i < len(level):
            nxt.append(level[i])
        level = nxt
    return level[0]


def _sorted_path(leaves, index):
    """Audit path in the promoted-odd sorted tree."""
    path = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        nxt = []
        i = 0
        new_idx = idx
        while i + 1 < len(level):
            pair = (level[i], level[i + 1])
            if idx == i:
                path.append({"side": "right", "hash": pair[1].hex()})
                new_idx = len(nxt)
            elif idx == i + 1:
                path.append({"side": "left", "hash": pair[0].hex()})
                new_idx = len(nxt)
            nxt.append(hashlib.sha256(SORTED_NODE + pair[0] + pair[1]).digest())
            i += 2
        if i < len(level):
            if idx == i:
                new_idx = len(nxt)
            nxt.append(level[i])
        level = nxt
        idx = new_idx
    return path


# ------------------------------------------------------------------ schema

def _ensure(ctx):
    conn = ctx["conn"]
    with ctx["lock"]:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS register_entry (
            domain        TEXT PRIMARY KEY,
            status        TEXT NOT NULL,
            first_listed  REAL NOT NULL,
            last_event    REAL NOT NULL,
            last_checked  REAL,
            last_pass     REAL,
            checks_json   TEXT,
            contact       TEXT,
            claim_method  TEXT,
            reason        TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS register_event (
            seq        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         REAL NOT NULL,
            domain     TEXT NOT NULL,
            kind       TEXT NOT NULL,
            detail     TEXT NOT NULL,
            leaf_hex   TEXT NOT NULL,
            audit_hash TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_event_domain ON register_event(domain, seq)")
        c.execute("""CREATE TABLE IF NOT EXISTS register_checkpoint (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            ts            REAL NOT NULL,
            tree_size     INTEGER NOT NULL,
            event_root    TEXT NOT NULL,
            domain_root   TEXT NOT NULL,
            domain_count  INTEGER NOT NULL,
            domains_json  TEXT NOT NULL,
            audit_hash    TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_checkpoint_ts ON register_checkpoint(ts)")
        c.execute("""CREATE TABLE IF NOT EXISTS register_challenge (
            domain  TEXT PRIMARY KEY,
            token   TEXT NOT NULL,
            issued  REAL NOT NULL
        )""")
        # v1.1: every issued token stays valid until it expires, so asking
        # for a new one never invalidates the one already published.
        c.execute("""CREATE TABLE IF NOT EXISTS register_token (
            token   TEXT PRIMARY KEY,
            domain  TEXT NOT NULL,
            issued  REAL NOT NULL
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_register_token_domain ON register_token(domain, issued)")
        conn.commit()


def _event_leaves(ctx):
    """Ordered list of leaf digests for the whole event log."""
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT leaf_hex FROM register_event ORDER BY seq ASC").fetchall()
    return [bytes.fromhex(r[0]) for r in rows]


def _live_domains(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain FROM register_entry WHERE status IN (?,?,?,?)",
            LIVE_STATUSES).fetchall()
    return sorted(r[0] for r in rows)


def _extract_hash(result):
    """server.py's seal has returned different shapes over time. Accept them all."""
    if result is None:
        return None
    if isinstance(result, str):
        return result or None
    if isinstance(result, dict):
        for k in ("audit_hash", "hash", "audit", "block_hash", "sealed_hash"):
            v = result.get(k)
            if isinstance(v, str) and v:
                return v
        return None
    if isinstance(result, (tuple, list)):
        for item in result:
            h = _extract_hash(item)
            if h:
                return h
    return None


def _do_seal(ctx, event, result=None):
    """Call ctx['seal'] with the ONE correct signature and exactly once.

    This is the signature witness.py uses and that is proven against this
    server: seal(event, result, ts, api_key), returning (audit_hash,
    block_index, seq).

    WHY THIS WAS REWRITTEN (v1.2.0 -> safe):
    The previous version tried four different argument shapes in a loop. seal
    WRITES a block to the chain as a side effect. A shape that partially
    succeeded — wrote a block but returned something _extract_hash could not
    read — would fall through and the loop would call seal AGAIN, writing a
    SECOND block. Two blocks for one logical event, or a written-then-retried
    call, breaks the chain's prev-hash linkage. That is the fault that broke
    the chain. This calls seal once, the correct way, and never retries a call
    that may already have written.
    """
    seal = ctx["seal"]
    ts = _now()
    if result is None:
        result = event.get("kind") or event.get("type") or "register"
    if not isinstance(result, str):
        result = _canon(result)

    # Register events are not tied to a customer key. A stable module key
    # partitions them the way witness.py partitions anonymous observations.
    api_key = "register"

    out = seal(event, result, ts, api_key)

    h = _extract_hash(out)
    if h:
        return h
    if isinstance(out, (tuple, list)) and out and isinstance(out[0], str) and out[0]:
        return out[0]
    raise RuntimeError("seal returned no audit_hash: %r" % (out,))


def _seal_event(ctx, domain, kind, detail):
    """Seal, then write. A failed seal writes nothing and raises."""
    ts = _now()
    leaf_payload = _canon({"v": 1, "ts": round(ts, 3), "domain": domain,
                           "kind": kind, "detail": detail}).encode("utf-8")
    leaf_hex = _ct_leaf(leaf_payload).hex()

    event = {
        "user_id": "register:%s" % domain,
        "type": "register_event",
        "domain": domain,
        "kind": kind,
        "leaf": leaf_hex,
        "suite": SUITE_VERSION,
        "detail": detail,
    }
    audit_hash = _do_seal(ctx, event, result=kind)

    with ctx["lock"]:
        cur = ctx["conn"].execute(
            "INSERT INTO register_event (ts, domain, kind, detail, leaf_hex, audit_hash)"
            " VALUES (?,?,?,?,?,?)",
            (ts, domain, kind, _canon(detail), leaf_hex, audit_hash))
        seq = cur.lastrowid
        ctx["conn"].commit()

    return {"seq": seq, "ts": ts, "at": _iso(ts), "leaf": leaf_hex,
            "audit_hash": audit_hash, "kind": kind}


def _seal_checkpoint(ctx):
    """Seal the current state: ordered event root + sorted domain root."""
    leaves = _event_leaves(ctx)
    domains = _live_domains(ctx)
    event_root = _ct_root(leaves).hex()
    domain_root = _sorted_root([_sorted_leaf(d) for d in domains]).hex()
    ts = _now()

    event = {
        "user_id": "register:checkpoint",
        "type": "register_checkpoint",
        "tree_size": len(leaves),
        "event_root": event_root,
        "domain_root": domain_root,
        "domain_count": len(domains),
        "suite": SUITE_VERSION,
    }
    audit_hash = _do_seal(ctx, event, result="checkpoint")

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO register_checkpoint (ts, tree_size, event_root, domain_root,"
            " domain_count, domains_json, audit_hash) VALUES (?,?,?,?,?,?,?)",
            (ts, len(leaves), event_root, domain_root, len(domains),
             _canon(domains), audit_hash))
        ctx["conn"].commit()

    return {"at": _iso(ts), "tree_size": len(leaves), "event_root": event_root,
            "domain_root": domain_root, "domain_count": len(domains),
            "audit_hash": audit_hash}


# ------------------------------------------------------------- check suite

def _find_manifest(domain):
    """Try the well-known path first, then the root. Return (path, body, note)."""
    tried = []
    for path in AI_TXT_PATHS:
        ok, body, note = _fetch("https://%s%s" % (domain, path))
        tried.append({"path": path, "ok": ok, "note": note})
        if ok and body:
            return path, body, {"served_at": path, "attempts": tried, "observed": note}
    return None, None, {"served_at": None, "attempts": tried}


def _pick(fields, key):
    """Return (alias_used, value) for the first alias present."""
    for alias in FIELD_ALIASES[key]:
        if fields.get(alias):
            return alias, fields[alias]
    return None, None


def _run_checks(domain):
    """Observe what the domain serves. Every check names what it looked at."""
    checks = []

    path, body, mnote = _find_manifest(domain)
    checks.append({
        "id": "ai_txt_reachable",
        "asks": "Does %s serve a manifest at %s?" % (domain, " or ".join(AI_TXT_PATHS)),
        "pass": bool(body),
        "observed": mnote,
    })

    fields = {}
    if body:
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip().lower()
            v = v.strip()
            if k and v and k not in fields:
                fields[k] = v

    tip_alias, tip_url = _pick(fields, "chain_tip_url")
    ver_alias, verifier = _pick(fields, "verifier")
    con_alias, contact = _pick(fields, "contact")

    missing = []
    if not tip_url:
        missing.append("chain tip url (%s)" % "/".join(FIELD_ALIASES["chain_tip_url"]))
    if not verifier:
        missing.append("verifier (%s)" % "/".join(FIELD_ALIASES["verifier"]))
    if not contact:
        missing.append("contact (%s)" % "/".join(FIELD_ALIASES["contact"]))

    checks.append({
        "id": "ai_txt_declares_required_fields",
        "asks": "Does the manifest declare a chain tip url, a verifier and a contact, under any accepted field name?",
        "pass": bool(body) and not missing,
        "observed": {
            "matched": {"chain_tip_url": tip_alias, "verifier": ver_alias, "contact": con_alias},
            "missing": missing,
            "field_count": len(fields),
        },
    })

    tip_value = None
    if tip_url:
        tok, tbody, tnote = _fetch(tip_url)
        parsed_tip = None
        if tok and tbody:
            try:
                obj = json.loads(tbody)
                for key in ("tip", "tip_sha256", "chain_tip", "head", "root",
                            "current_tip", "latest", "hash"):
                    if isinstance(obj.get(key), str):
                        parsed_tip = obj[key]
                        break
            except Exception:
                stripped = tbody.strip()
                if re.fullmatch(r"[0-9a-fA-F]{64}", stripped):
                    parsed_tip = stripped
        tip_value = parsed_tip
        checks.append({
            "id": "chain_tip_served",
            "asks": "Does the declared chain tip url return a tip value?",
            "pass": bool(parsed_tip),
            "observed": dict(tnote, declared_as=tip_alias, tip_field_found=bool(parsed_tip)),
        })
        checks.append({
            "id": "chain_tip_is_sha256",
            "asks": "Is the served tip a 64-character hex digest?",
            "pass": bool(parsed_tip) and bool(re.fullmatch(r"[0-9a-fA-F]{64}", parsed_tip or "")),
            "observed": {"tip": parsed_tip},
        })
    else:
        for cid, asks in (("chain_tip_served", "Does the declared chain tip url return a tip value?"),
                          ("chain_tip_is_sha256", "Is the served tip a 64-character hex digest?")):
            checks.append({"id": cid, "asks": asks, "pass": False,
                           "observed": {"error": "no chain tip url declared"}})

    checks.append({
        "id": "verifier_named",
        "asks": "Does the manifest name instructions or a tool a third party can use to check the chain themselves?",
        "pass": bool(verifier),
        "observed": {"verifier": verifier, "declared_as": ver_alias},
    })

    passed = all(c["pass"] for c in checks)
    return {
        "suite": SUITE_VERSION,
        "ran_at": _iso(_now()),
        "manifest_path": path,
        "all_passed": passed,
        "failed": [c["id"] for c in checks if not c["pass"]],
        "checks": checks,
        "tip_observed": tip_value,
        "contact": contact,
        "declared": fields,
    }


# ------------------------------------------------------------------ actions

def _spec(ctx):
    return {
        "module": "register",
        "version": VERSION,
        "suite_version": SUITE_VERSION,
        "what_this_is":
            "A registry that publishes proofs about its own behaviour. Absence proofs "
            "show a domain was not listed on a date. RFC 6962 consistency proofs show "
            "no entry was inserted behind an earlier position. Revocations are sealed "
            "rather than deleted, so a removed listing stays readable.",
        "why_that_matters":
            "Every other registry is a mutable database whose operator can add, "
            "back-date or quietly delete entries. Trusting the list means trusting the "
            "registrar. This one is checkable against its own operator.",
        "what_this_is_not": WHAT_THIS_IS_NOT,
        "status_vocabulary": VOCABULARY,
        "how_to_get_listed": [
            "Simplest, nothing to edit: if your manifest already carries a `Domain: <yourdomain>` line matching the domain you are claiming, POST /x/register/claim and you are listed. A manifest served from your domain naming your domain could only have been published by you.",
            "If your manifest does not name itself, use the token route instead:",
            "1. POST /x/register/challenge with {\"domain\": \"example.com\"} — returns a one-time token.",
            "2. Serve that token at https://example.com%s, or add a `Register-Token: <token>` line to your manifest at %s" % (WELL_KNOWN_PATH, " or ".join(AI_TXT_PATHS)),
            "Any token issued in the last 24 hours will verify — asking for a new one does not invalidate one you already published. See /x/register/tokens?domain=example.com",
            "3. POST /x/register/claim with {\"domain\": \"example.com\"} — we fetch, verify, run the checks and seal the result.",
            "Opt out at any time with a `Register: no` line in the manifest — the register refuses the claim and says so.",
            "Nobody is listed by the operator. A domain lists itself by proving it controls the domain.",
        ],
        "manifest_paths_tried": AI_TXT_PATHS,
        "field_aliases": FIELD_ALIASES,
        "checks_run": [
            "ai_txt_reachable", "ai_txt_declares_required_fields",
            "chain_tip_served", "chain_tip_is_sha256", "verifier_named",
        ],
        "trees": {
            "event_tree": "RFC 6962 ordered tree over every register event in write order. Answers append-only. Verifies with any standard Certificate Transparency verifier.",
            "domain_tree": "Sorted tree over the domains listed at a checkpoint, odd nodes promoted, domain-separated prefixes. Answers absence.",
            "note": "The two roots answer different questions and deliberately never match.",
        },
        "proof_of_control": {"preferred": "manifest-self-declaration (a Domain: line naming itself)",
                             "fallback": "one-time token served at a path we name",
                             "opt_out": "a `Register: no` line in the manifest"},
        "stale_after_days": STALE_AFTER_DAYS,
        "challenge_ttl_seconds": CHALLENGE_TTL_SECONDS,
        "routes": {
            "public": sorted("%s /x/register/%s" % (m, a) for m, a in PUBLIC),
            "keyed": ["POST /x/register/recheck-all", "POST /x/register/checkpoint",
                      "POST /x/register/revoke"],
        },
        "honest_limits": [
            "A check observes what a URL served at a moment in time. It cannot know what a domain did not seal.",
            "Domain control proves control of the domain, not the truth of anything the domain declares.",
            "Absence proofs are only as good as the checkpoint they are made against. A period with no checkpoint has nothing to prove absence from.",
            "Nobody can be forced to keep publishing. A listing goes stale when the evidence ages, and that is the honest outcome rather than a failure of the register.",
        ],
    }, 200


def _challenge(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not data.get("domain"):
        return {"error": MESSAGES["domain_required"]}, 400
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
    if row and row[0] in (STATUS_REVOKED,):
        return {"error": MESSAGES["already_final"], "domain": domain,
                "status": row[0]}, 409

    # Idempotent: if a live token already exists for this domain, return THAT
    # one. Minting a new token on every request is how an operator ends up with
    # a published token the register no longer recognises.
    existing = _live_tokens(ctx, domain)
    if existing:
        token, issued = existing[0]
        return {
            "ok": True,
            "domain": domain,
            "token": token,
            "reused": True,
            "issued_at": _iso(issued),
            "expires_at": _iso(issued + CHALLENGE_TTL_SECONDS),
            "serve_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                         "or a `Register-Token: %s` line in your manifest at %s"
                         % (token, " or ".join(AI_TXT_PATHS))],
            "then": "POST /x/register/claim {\"domain\": \"%s\"}" % domain,
            "note": "This is the token already issued for this domain. Requesting "
                    "again does not replace it, so anything you have already "
                    "published stays valid.",
        }, 200

    token = "aileash-register-" + secrets.token_hex(16)
    ts = _now()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO register_challenge (domain, token, issued) VALUES (?,?,?)"
            " ON CONFLICT(domain) DO UPDATE SET token=excluded.token, issued=excluded.issued",
            (domain, token, ts))
        ctx["conn"].execute(
            "INSERT OR REPLACE INTO register_token (token, domain, issued) VALUES (?,?,?)",
            (token, domain, ts))
        ctx["conn"].execute(
            "DELETE FROM register_token WHERE domain=? AND issued<?",
            (domain, ts - CHALLENGE_TTL_SECONDS))
        ctx["conn"].commit()

    try:
        sealed = _seal_event(ctx, domain, "challenge_issued",
                             {"token_sha256": _sha(token.encode())})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    return {
        "ok": True,
        "domain": domain,
        "token": token,
        "expires_at": _iso(ts + CHALLENGE_TTL_SECONDS),
        "serve_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                     "or a `Register-Token: %s` line in https://%s%s" % (token, domain, AI_TXT_PATH)],
        "then": "POST /x/register/claim {\"domain\": \"%s\"}" % domain,
        "sealed": sealed,
        "note": "The token itself is not sealed — only its digest, so the challenge cannot be replayed from the public chain.",
    }, 200


def _live_tokens(ctx, domain):
    """Every token issued for this domain that has not expired, newest first."""
    cutoff = _now() - CHALLENGE_TTL_SECONDS
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT token, issued FROM register_token WHERE domain=? AND issued>=?"
            " ORDER BY issued DESC", (domain, cutoff)).fetchall()
    return [(r[0], r[1]) for r in rows]


def _verify_self_declaration(domain):
    """Proof of control with nothing to edit.

    A manifest served over https from the domain, whose own `Domain:` line
    names that same domain, was published by whoever controls the domain.
    Nobody else can put a file there. That IS the consent a token was
    standing in for, so a token is only needed when the manifest does not
    name itself (or the operator has opted out).

    An operator who does not want to be listed writes `Register: no`.
    """
    path, body, mnote = _find_manifest(domain)
    if not body:
        return False, {"reason": "no manifest served", "attempts": mnote}

    declared = None
    opted_out = False
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip().lower()
        if k == "domain" and declared is None:
            declared = v.lstrip("www.")
        if k == "register" and v in ("no", "false", "off", "opt-out"):
            opted_out = True

    if opted_out:
        return False, {"reason": "manifest declares Register: no",
                       "respected": True, "served_at": path}
    if not declared:
        return False, {"reason": "manifest does not declare a Domain: line",
                       "served_at": path}
    if declared != domain:
        return False, {"reason": "manifest declares a different domain",
                       "declared": declared, "claimed": domain, "served_at": path}

    return True, {"method": "manifest-self-declaration", "served_at": path,
                  "declared_domain": declared, "observed": mnote.get("observed"),
                  "what_this_proves": "The manifest at this path names this domain "
                                      "as its own. Only the party controlling the "
                                      "domain can serve that file."}


def _verify_any_token(ctx, domain):
    """Accept ANY live token for this domain. Requesting a new one must never
    invalidate one the operator has already published."""
    tokens = _live_tokens(ctx, domain)
    if not tokens:
        return False, None, {"error": "no_live_token"}
    last = None
    for token, issued in tokens:
        ok, evidence = _verify_token(domain, token)
        if ok:
            evidence["token_issued"] = _iso(issued)
            evidence["tokens_live"] = len(tokens)
            return True, token, evidence
        last = evidence
    return False, None, {"tokens_live": len(tokens), "none_matched": True,
                         "last_attempt": last}


def _verify_token(domain, token):
    ok, body, note = _fetch("https://%s%s" % (domain, WELL_KNOWN_PATH))
    if ok and body and token in body:
        return True, {"method": "well-known", "observed": note}
    tried = [{"path": WELL_KNOWN_PATH, "note": note}]
    for path in AI_TXT_PATHS:
        ok2, body2, note2 = _fetch("https://%s%s" % (domain, path))
        tried.append({"path": path, "note": note2})
        if ok2 and body2:
            for line in body2.splitlines():
                if line.strip().lower().startswith("register-token:") and token in line:
                    return True, {"method": "manifest:%s" % path, "observed": note2}
    return False, {"method": None, "tried": tried}


def _claim(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400

    verified, evidence = _verify_self_declaration(domain)
    if not verified:
        self_decl_evidence = evidence
        if evidence.get("respected"):
            return {"ok": False, "domain": domain,
                    "error": "this domain has opted out with a `Register: no` line",
                    "evidence": evidence}, 403
        if not _live_tokens(ctx, domain):
            return {"ok": False, "domain": domain,
                    "error": "could not prove control of this domain",
                    "self_declaration": self_decl_evidence,
                    "how_to_fix": [
                        "Easiest: add a `Domain: %s` line to your manifest at %s."
                        % (domain, " or ".join(AI_TXT_PATHS)),
                        "Or: POST /x/register/challenge and serve the token it returns.",
                    ]}, 400
        verified, matched_token, tok_evidence = _verify_any_token(ctx, domain)
        evidence = dict(tok_evidence or {}, self_declaration=self_decl_evidence)
    if not verified:
        try:
            _seal_event(ctx, domain, "claim_refused", {"reason": "token_not_found",
                                                       "evidence": evidence})
        except Exception as e:
            return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500
        return {"ok": False, "domain": domain, "error": MESSAGES["token_not_found"],
                "looked_at": ["https://%s%s" % (domain, WELL_KNOWN_PATH),
                              "https://%s%s" % (domain, AI_TXT_PATH)],
                "evidence": evidence,
                "note": "The refusal is sealed. Fix the token and claim again."}, 400

    checks = _run_checks(domain)
    status = STATUS_PASSED if checks["all_passed"] else STATUS_FAILED
    contact = checks.get("contact")
    ts = _now()

    try:
        sealed = _seal_event(ctx, domain, "listed", {
            "claim_method": evidence.get("method"),
            "status": status,
            "suite": SUITE_VERSION,
            "failed": checks["failed"],
            "tip_observed": checks["tip_observed"],
        })
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        existing = ctx["conn"].execute(
            "SELECT first_listed FROM register_entry WHERE domain=?", (domain,)).fetchone()
        first = existing[0] if existing else ts
        ctx["conn"].execute(
            "INSERT INTO register_entry (domain, status, first_listed, last_event,"
            " last_checked, last_pass, checks_json, contact, claim_method, reason)"
            " VALUES (?,?,?,?,?,?,?,?,?,NULL)"
            " ON CONFLICT(domain) DO UPDATE SET status=excluded.status,"
            " last_event=excluded.last_event, last_checked=excluded.last_checked,"
            " last_pass=excluded.last_pass, checks_json=excluded.checks_json,"
            " contact=excluded.contact, claim_method=excluded.claim_method, reason=NULL",
            (domain, status, first, ts, ts,
             ts if checks["all_passed"] else None,
             _canon(checks), contact, evidence.get("method")))
        ctx["conn"].execute("DELETE FROM register_challenge WHERE domain=?", (domain,))
        ctx["conn"].execute("DELETE FROM register_token WHERE domain=?", (domain,))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": status,
            "status_means": VOCABULARY[status],
            "claim_method": evidence.get("method"),
            "checks": checks, "sealed": sealed, "checkpoint": cp,
            "entry_url": "/x/register/entry?domain=%s" % domain}, 200


def _recheck(ctx, data):
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status, first_listed FROM register_entry WHERE domain=?",
            (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404
    if row[0] in (STATUS_WITHDRAWN, STATUS_REVOKED):
        return {"error": MESSAGES["already_final"], "domain": domain, "status": row[0]}, 409

    checks = _run_checks(domain)
    status = STATUS_PASSED if checks["all_passed"] else STATUS_FAILED
    ts = _now()

    try:
        sealed = _seal_event(ctx, domain, "rechecked", {
            "status": status, "suite": SUITE_VERSION, "failed": checks["failed"],
            "tip_observed": checks["tip_observed"],
        })
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, last_checked=?,"
            " last_pass=COALESCE(?, last_pass), checks_json=? WHERE domain=?",
            (status, ts, ts, ts if checks["all_passed"] else None,
             _canon(checks), domain))
        ctx["conn"].commit()

    return {"ok": True, "domain": domain, "status": status,
            "status_means": VOCABULARY[status], "checks": checks, "sealed": sealed}, 200


def _withdraw(ctx, data):
    """A domain removes itself. Proved the same way it listed itself."""
    domain = _clean_domain(data.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404
    verified, evidence = _verify_self_declaration(domain)
    if not verified:
        if not _live_tokens(ctx, domain):
            return {"error": MESSAGES["no_challenge"], "domain": domain,
                    "note": "Withdrawal is proved the same way listing is."}, 404
        verified, matched_token, evidence = _verify_any_token(ctx, domain)
    if not verified:
        return {"ok": False, "error": MESSAGES["token_not_found"], "evidence": evidence}, 400

    ts = _now()
    try:
        sealed = _seal_event(ctx, domain, "withdrawn",
                             {"by": "domain", "method": evidence.get("method")})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, reason=? WHERE domain=?",
            (STATUS_WITHDRAWN, ts, "withdrawn by domain", domain))
        ctx["conn"].execute("DELETE FROM register_challenge WHERE domain=?", (domain,))
        ctx["conn"].execute("DELETE FROM register_token WHERE domain=?", (domain,))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": STATUS_WITHDRAWN,
            "status_means": VOCABULARY[STATUS_WITHDRAWN],
            "sealed": sealed, "checkpoint": cp,
            "note": "The listing history remains readable at /x/register/history?domain=%s" % domain}, 200


def _revoke(ctx, data):
    domain = _clean_domain(data.get("domain"))
    reason = (data.get("reason") or "").strip()
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    if not reason:
        return {"error": "reason is required — a revocation with no sealed reason is exactly what this register exists to prevent"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT status FROM register_entry WHERE domain=?", (domain,)).fetchone()
    if not row:
        return {"error": MESSAGES["not_listed"], "domain": domain}, 404

    ts = _now()
    try:
        sealed = _seal_event(ctx, domain, "revoked", {"by": "operator", "reason": reason})
    except Exception as e:
        return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE register_entry SET status=?, last_event=?, reason=? WHERE domain=?",
            (STATUS_REVOKED, ts, reason, domain))
        ctx["conn"].commit()

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}

    return {"ok": True, "domain": domain, "status": STATUS_REVOKED,
            "reason": reason, "sealed": sealed, "checkpoint": cp,
            "note": "Nothing was deleted. The revocation is sealed and the history stays public."}, 200


def _recheck_all(ctx):
    domains = _live_domains(ctx)
    results = []
    for d in domains:
        body, _ = _recheck(ctx, {"domain": d})
        results.append({"domain": d, "status": body.get("status"),
                        "failed": (body.get("checks") or {}).get("failed")})
    # age anything whose last pass is old
    cutoff = _now() - STALE_AFTER_DAYS * 86400
    aged = []
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain, last_pass FROM register_entry WHERE status=?",
            (STATUS_PASSED,)).fetchall()
    for domain, last_pass in rows:
        if last_pass is None or last_pass < cutoff:
            try:
                _seal_event(ctx, domain, "stale", {"last_pass": _iso(last_pass) if last_pass else None})
            except Exception:
                continue
            with ctx["lock"]:
                ctx["conn"].execute(
                    "UPDATE register_entry SET status=?, last_event=? WHERE domain=?",
                    (STATUS_STALE, _now(), domain))
                ctx["conn"].commit()
            aged.append(domain)

    cp = None
    try:
        cp = _seal_checkpoint(ctx)
    except Exception as e:
        cp = {"error": "checkpoint_failed", "detail": str(e)}
    return {"ok": True, "rechecked": results, "moved_to_stale": aged,
            "checkpoint": cp}, 200


def _list(ctx, q):
    want = (q.get("status") or "").strip().lower()
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain, status, first_listed, last_event, last_checked, last_pass,"
            " checks_json, reason FROM register_entry ORDER BY domain ASC").fetchall()
    out = []
    for r in rows:
        checks = {}
        try:
            checks = json.loads(r[6]) if r[6] else {}
        except Exception:
            checks = {}
        entry = {
            "domain": r[0],
            "status": r[1],
            "status_means": VOCABULARY.get(r[1], "unexplained value — treat as unverified"),
            "first_listed": _iso(r[2]),
            "last_event": _iso(r[3]),
            "last_checked": _iso(r[4]) if r[4] else None,
            "last_pass": _iso(r[5]) if r[5] else None,
            "failed_checks": checks.get("failed") or [],
            "reason": r[7],
        }
        if not want or entry["status"] == want:
            out.append(entry)

    with ctx["lock"]:
        cp = ctx["conn"].execute(
            "SELECT ts, tree_size, event_root, domain_root, domain_count"
            " FROM register_checkpoint ORDER BY id DESC LIMIT 1").fetchone()

    return {
        "registry_version": VERSION,
        "suite_version": SUITE_VERSION,
        "count": len(out),
        "entries": out,
        "status_vocabulary": VOCABULARY,
        "what_this_list_is_not": WHAT_THIS_IS_NOT,
        "latest_checkpoint": ({
            "at": _iso(cp[0]), "tree_size": cp[1], "event_root": cp[2],
            "domain_root": cp[3], "domain_count": cp[4],
        } if cp else None),
        "prove_absence": "/x/register/absence?domain=example.com&at=2026-01-01",
        "prove_append_only": "/x/register/consistency?first=<size>&second=<size>",
    }, 200


def _entry(ctx, q):
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        r = ctx["conn"].execute(
            "SELECT domain, status, first_listed, last_event, last_checked, last_pass,"
            " checks_json, contact, claim_method, reason FROM register_entry WHERE domain=?",
            (domain,)).fetchone()
    if not r:
        return {"error": MESSAGES["not_listed"], "domain": domain,
                "prove_it": "/x/register/absence?domain=%s&at=<date>" % domain}, 404
    try:
        checks = json.loads(r[6]) if r[6] else {}
    except Exception:
        checks = {}
    return {
        "domain": r[0], "status": r[1],
        "status_means": VOCABULARY.get(r[1], "unexplained value — treat as unverified"),
        "first_listed": _iso(r[2]), "last_event": _iso(r[3]),
        "last_checked": _iso(r[4]) if r[4] else None,
        "last_pass": _iso(r[5]) if r[5] else None,
        "claim_method": r[8], "reason": r[9],
        "checks": checks,
        "what_this_is_not": WHAT_THIS_IS_NOT,
        "history": "/x/register/history?domain=%s" % domain,
    }, 200


def _history(ctx, q):
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT seq, ts, kind, detail, leaf_hex, audit_hash FROM register_event"
            " WHERE domain=? ORDER BY seq ASC", (domain,)).fetchall()
    events = []
    for s, ts, kind, detail, leaf, ah in rows:
        try:
            d = json.loads(detail)
        except Exception:
            d = detail
        events.append({"seq": s, "at": _iso(ts), "kind": kind, "detail": d,
                       "leaf": leaf, "audit_hash": ah,
                       "inclusion": "/x/register/inclusion?seq=%d" % s})
    return {"domain": domain, "count": len(events), "events": events,
            "note": "Nothing is ever removed from this history, including revocations."}, 200


def _absence(ctx, q):
    """Prove a domain was NOT listed at a given time."""
    domain = _clean_domain(q.get("domain"))
    if not domain:
        return {"error": MESSAGES["bad_domain"]}, 400
    at = _parse_when(q.get("at"))
    with ctx["lock"]:
        if at is None:
            cp = ctx["conn"].execute(
                "SELECT ts, tree_size, domain_root, domain_count, domains_json, audit_hash"
                " FROM register_checkpoint ORDER BY id DESC LIMIT 1").fetchone()
        else:
            cp = ctx["conn"].execute(
                "SELECT ts, tree_size, domain_root, domain_count, domains_json, audit_hash"
                " FROM register_checkpoint WHERE ts<=? ORDER BY ts DESC LIMIT 1",
                (at,)).fetchone()
    if not cp:
        return {"error": MESSAGES["no_checkpoint"], "domain": domain,
                "asked_about": _iso(at) if at else "now"}, 404

    domains = json.loads(cp[4])
    leaves = [_sorted_leaf(d) for d in domains]
    root = _sorted_root(leaves).hex()

    if domain in domains:
        idx = domains.index(domain)
        return {
            "domain": domain,
            "present": True,
            "at": _iso(cp[0]),
            "checkpoint_root": root,
            "index": idx,
            "path": _sorted_path(leaves, idx),
            "proves": "This domain WAS listed at the checkpoint shown. This is an inclusion proof, not an absence proof.",
        }, 200

    # find the two adjacent leaves it would sit between
    lo, hi = None, None
    for i, d in enumerate(domains):
        if d < domain:
            lo = i
        if d > domain and hi is None:
            hi = i
    neighbours = []
    if lo is not None:
        neighbours.append({"position": "before", "index": lo, "domain": domains[lo],
                           "leaf": leaves[lo].hex(), "path": _sorted_path(leaves, lo)})
    if hi is not None:
        neighbours.append({"position": "after", "index": hi, "domain": domains[hi],
                           "leaf": leaves[hi].hex(), "path": _sorted_path(leaves, hi)})

    if lo is not None and hi is not None:
        proves = ("Indices %d and %d are consecutive in a sorted tree committed at %s. "
                  "Nothing can sit between them, and %s sorts between them, so it was "
                  "not listed at that checkpoint." % (lo, hi, _iso(cp[0]), domain))
    elif not domains:
        proves = ("The register held no listings at all at that checkpoint "
                  "(count 0, sealed root %s), so %s was not listed." % (root, domain))
    elif lo is None:
        proves = ("%s sorts before the first leaf at index 0, and the leaf count was "
                  "committed in advance, so it was not listed at that checkpoint." % domain)
    else:
        proves = ("%s sorts after the last leaf at index %d, and the leaf count was "
                  "committed in advance, so it was not listed at that checkpoint." % (domain, lo))

    return {
        "domain": domain,
        "present": False,
        "asked_about": _iso(at) if at else "now",
        "checkpoint_at": _iso(cp[0]),
        "checkpoint_root": root,
        "sealed_root": cp[2],
        "roots_agree": root == cp[2],
        "domain_count": cp[3],
        "neighbours": neighbours,
        "proves": proves,
        "how_to_check_yourself": [
            "leaf   = SHA256('AILEASH-REGISTER-LEAF-v1\\x00' + domain)",
            "node   = SHA256('AILEASH-REGISTER-NODE-v1\\x00' + left + right)",
            "Odd nodes are promoted to the next level, never paired with themselves.",
            "Recompute each neighbour's path to the root and confirm it equals checkpoint_root.",
        ],
        "limit": "An absence proof is against a checkpoint. It says nothing about moments between checkpoints.",
    }, 200


def _consistency(ctx, q):
    """RFC 6962 proof that the register at size `first` is a prefix of size `second`."""
    leaves = _event_leaves(ctx)
    n = len(leaves)
    try:
        first = int(q.get("first")) if q.get("first") else None
        second = int(q.get("second")) if q.get("second") else n
    except (TypeError, ValueError):
        return {"error": "first and second must be integers"}, 400
    if first is None:
        return {"error": "first is required — the tree size you already hold",
                "current_size": n}, 400
    if not (0 < first <= second <= n):
        return {"error": "need 0 < first <= second <= current size",
                "current_size": n}, 400

    proof = _ct_consistency(leaves[:second], first)
    return {
        "first": first,
        "second": second,
        "current_size": n,
        "first_root": _ct_root(leaves[:first]).hex(),
        "second_root": _ct_root(leaves[:second]).hex(),
        "proof": proof,
        "algorithm": "RFC 6962 consistency proof, SHA-256, leaf prefix 0x00, node prefix 0x01",
        "proves": ("The register at size %d is a prefix of the register at size %d. "
                   "No entry was inserted, altered or removed behind an earlier "
                   "position — including by the operator." % (first, second)),
        "verify_with": "Any standard Certificate Transparency verifier. This tree is deliberately unmodified so you do not have to use ours.",
    }, 200


def _inclusion(ctx, q):
    leaves = _event_leaves(ctx)
    try:
        seq = int(q.get("seq"))
    except (TypeError, ValueError):
        return {"error": "seq is required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT seq, ts, domain, kind, leaf_hex, audit_hash FROM register_event"
            " WHERE seq=?", (seq,)).fetchone()
    if not row:
        return {"error": "no event at that seq"}, 404
    index = seq - 1
    if index < 0 or index >= len(leaves):
        return {"error": "seq out of range of the current tree"}, 409
    return {
        "seq": seq, "index": index, "at": _iso(row[1]), "domain": row[2],
        "kind": row[3], "leaf": row[4], "audit_hash": row[5],
        "tree_size": len(leaves),
        "root": _ct_root(leaves).hex(),
        "proof": _ct_inclusion(leaves, index),
        "algorithm": "RFC 6962 inclusion proof, SHA-256",
    }, 200


def _checkpoints(ctx, q):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT id, ts, tree_size, event_root, domain_root, domain_count, audit_hash"
            " FROM register_checkpoint ORDER BY id DESC LIMIT 200").fetchall()
    return {
        "count": len(rows),
        "checkpoints": [{
            "id": r[0], "at": _iso(r[1]), "tree_size": r[2],
            "event_root": r[3], "domain_root": r[4],
            "domain_count": r[5], "audit_hash": r[6],
        } for r in rows],
        "note": "event_root answers append-only. domain_root answers absence. They are different trees and never match.",
    }, 200


def _roots(ctx):
    leaves = _event_leaves(ctx)
    domains = _live_domains(ctx)
    return {
        "tree_size": len(leaves),
        "event_root": _ct_root(leaves).hex(),
        "domain_count": len(domains),
        "domain_root": _sorted_root([_sorted_leaf(d) for d in domains]).hex(),
        "at": _iso(_now()),
        "note": "Live values. A root only becomes evidence once it is sealed by a checkpoint.",
    }, 200


# ------------------------------------------------------------------ handle

def handle(method, action, data, api_key, ctx):
    _ensure(ctx)
    data = data or {}
    q = data if isinstance(data, dict) else {}

    if method == "GET":
        if action == "spec":
            return _spec(ctx)
        if action == "vocabulary":
            return {"status_vocabulary": VOCABULARY,
                    "what_this_is_not": WHAT_THIS_IS_NOT,
                    "suite_version": SUITE_VERSION}, 200
        if action == "list":
            return _list(ctx, q)
        if action == "entry":
            return _entry(ctx, q)
        if action == "history":
            return _history(ctx, q)
        if action == "absence":
            return _absence(ctx, q)
        if action == "consistency":
            return _consistency(ctx, q)
        if action == "inclusion":
            return _inclusion(ctx, q)
        if action == "checkpoints":
            return _checkpoints(ctx, q)
        if action == "roots":
            return _roots(ctx)
        if action == "tokens":
            d = _clean_domain(q.get("domain"))
            if not d:
                return {"error": MESSAGES["bad_domain"]}, 400
            live = _live_tokens(ctx, d)
            return {"domain": d, "live_tokens": len(live),
                    "tokens": [{"token": t, "issued": _iso(i),
                                "expires": _iso(i + CHALLENGE_TTL_SECONDS)} for t, i in live],
                    "note": "Any of these will verify. Requesting a new token does not "
                            "invalidate one you have already published."}, 200
        if action == "sealcheck":
            probe = {"user_id": "register:sealcheck", "type": "register_sealcheck",
                     "kind": "probe", "at": _iso(_now())}
            try:
                h = _do_seal(ctx, probe, result="sealcheck")
                return {"ok": True, "audit_hash": h,
                        "note": "The register can seal. This probe is a real sealed block."}, 200
            except Exception as e:
                return {"ok": False, "error": "seal_failed", "detail": str(e),
                        "note": "Nothing was written. The detail names what server.py's seal did."}, 500
        return {"error": "unknown action", "see": "/x/register/spec"}, 404

    if method == "POST":
        if action == "challenge":
            return _challenge(ctx, q)
        if action == "claim":
            return _claim(ctx, q)
        if action == "recheck":
            return _recheck(ctx, q)
        if action == "withdraw":
            return _withdraw(ctx, q)
        # keyed below
        if not api_key:
            return {"error": "api key required for this action"}, 401
        if action == "revoke":
            return _revoke(ctx, q)
        if action == "checkpoint":
            try:
                return {"ok": True, "checkpoint": _seal_checkpoint(ctx)}, 200
            except Exception as e:
                return {"error": MESSAGES["seal_failed"], "detail": str(e)}, 500
        if action == "recheck-all":
            return _recheck_all(ctx)
        return {"error": "unknown action", "see": "/x/register/spec"}, 404

    return {"error": "method not allowed"}, 405

```
