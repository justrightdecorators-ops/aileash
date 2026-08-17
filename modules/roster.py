"""
modules/roster.py  v1.0  -  the canonical network list

WHY
    Witnessing runs on each operator's own machine. A new chain can join
    the network and nobody else's server knows it exists, because nobody
    told it. The result is a star with one operator in the middle, which
    is the shape a witnessed log is supposed to avoid.

    This publishes the list. Every peer, every tip URL, one public route.
    A peer's sync reads it and witnesses everyone on it, including
    whoever joined this morning.

    It does not witness anything itself. It is a phone book.

WHERE THE DATA COMES FROM
    witness_log and witness_names, which witness.py already maintains.
    Nothing new is recorded and no existing module changes. A chain
    appears here because it submitted a tip with a url, which is the
    same thing that binds its name today.

WHAT MAKES THE LIST HONEST
    Every entry carries its own evidence: when it was first and last
    seen, how many observations, whether its name is bound to a host,
    and whether it has gone quiet. Nothing is filtered out for looking
    bad. A silent chain stays listed and is marked silent, because
    hiding it would make the list a claim rather than a record.

ROUTES
    GET  list      public   the roster. this is the one peers poll.
    GET  spec      public   what this is and how to consume it
    GET  health    public   one-line network summary
"""

import json
import time

VERSION = "1.0"

PUBLIC = {("GET", "list"), ("GET", "spec"), ("GET", "health")}

# A chain that has not submitted within this window is marked silent.
# It stays on the list. Silence is information, not a reason to hide it.
SILENT_AFTER_HOURS = 6

# Our own entry, so a consumer of the roster does not have to be told
# separately who publishes it.
SELF_CHAIN = "sebbi.pro"
SELF_TIP = "https://sebbi.pro/x/witness/tip"
SELF_OBSERVE = "https://sebbi.pro/x/witness/observe"


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _cols(conn, table):
    try:
        return [r[1] for r in conn.execute(
            "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


def _gather(ctx):
    """
    Read whatever witness.py has. Written defensively: this module must
    never be the reason a deploy breaks, so a missing table or column
    degrades to a shorter list rather than a 500.
    """
    conn = ctx["conn"]
    now = time.time()
    out = {}

    cols = _cols(conn, "witness_log")
    if not cols:
        return out

    chain_col = None
    for c in ("chain", "peer", "chain_name", "name"):
        if c in cols:
            chain_col = c
            break
    if not chain_col:
        return out

    ts_col = "ts" if "ts" in cols else ("seen" if "seen" in cols else None)
    url_col = "url" if "url" in cols else None
    live_col = "liveness" if "liveness" in cols else None
    name_col = "name_status" if "name_status" in cols else None

    sel = [chain_col]
    for c in (ts_col, url_col, live_col, name_col):
        sel.append(c if c else "NULL")

    try:
        rows = conn.execute(
            "SELECT %s FROM witness_log ORDER BY rowid" % ", ".join(sel)
        ).fetchall()
    except Exception:
        return out

    for r in rows:
        chain = (r[0] or "").strip()
        if not chain:
            continue
        e = out.setdefault(chain, {
            "chain": chain, "observations": 0, "first_seen": None,
            "last_seen": None, "url": None, "liveness": None,
            "name_status": None,
        })
        e["observations"] += 1
        ts = r[1]
        if ts:
            try:
                ts = float(ts)
                if e["first_seen"] is None or ts < e["first_seen"]:
                    e["first_seen"] = ts
                if e["last_seen"] is None or ts > e["last_seen"]:
                    e["last_seen"] = ts
            except (TypeError, ValueError):
                pass
        if r[2]:
            e["url"] = r[2]
        if r[3]:
            e["liveness"] = r[3]
        if r[4]:
            e["name_status"] = r[4]

    for e in out.values():
        last = e["last_seen"]
        hours = ((now - last) / 3600.0) if last else None
        e["hours_since"] = round(hours, 1) if hours is not None else None
        e["status"] = ("unknown" if hours is None
                       else ("current" if hours <= SILENT_AFTER_HOURS
                             else "silent"))
    return out


def _entries(ctx):
    peers = _gather(ctx)
    now = time.time()

    listed = []
    for chain, e in sorted(peers.items(), key=lambda kv: kv[0]):
        listed.append({
            "chain": e["chain"],
            "tip_url": e["url"],
            "observations": e["observations"],
            "first_seen": _iso(e["first_seen"]),
            "last_seen": _iso(e["last_seen"]),
            "hours_since": e["hours_since"],
            "status": e["status"],
            "liveness": e["liveness"],
            "name_status": e["name_status"],
            "witnessable": bool(e["url"]),
        })

    listed.insert(0, {
        "chain": SELF_CHAIN,
        "tip_url": SELF_TIP,
        "observations": None,
        "first_seen": None,
        "last_seen": _iso(now),
        "hours_since": 0,
        "status": "current",
        "liveness": "self",
        "name_status": "publisher",
        "witnessable": True,
        "note": "The publisher of this roster. Listed so a consumer does "
                "not have to be told separately who to witness.",
    })
    return listed


def _list(ctx):
    entries = _entries(ctx)
    usable = [e for e in entries if e["witnessable"]]
    return {
        "ok": True,
        "roster_version": VERSION,
        "generated": _iso(time.time()),
        "submit_to": SELF_OBSERVE,
        "count": len(entries),
        "witnessable": len(usable),
        "silent": len([e for e in entries if e["status"] == "silent"]),
        "peers": entries,
        "how_to_use":
            "Poll this route on your own schedule. For every entry with "
            "witnessable=true, fetch tip_url, seal the tip in your own "
            "chain, and POST your tip to their submit endpoint. A chain "
            "that joins tomorrow appears here and gets picked up on your "
            "next cycle with nothing to configure.",
        "note":
            "Chains that have gone quiet stay listed and are marked "
            "silent. Removing them would make this a claim rather than a "
            "record. An entry with witnessable=false has never bound a "
            "url and cannot be fetched from.",
    }, 200


def _health(ctx):
    entries = _entries(ctx)
    peers = [e for e in entries if e["chain"] != SELF_CHAIN]
    current = [e for e in peers if e["status"] == "current"]
    return {
        "ok": True,
        "chains_listed": len(entries),
        "peers_current": len(current),
        "peers_silent": len([e for e in peers if e["status"] == "silent"]),
        "shape":
            "mesh" if len(current) >= 3 else
            ("triangle" if len(current) == 2 else
             ("pair" if len(current) == 1 else "none")),
        "honest_note":
            "This counts chains that submit to us. It does not tell you "
            "whether they witness each other. Ask them, or read their "
            "own rosters.",
    }, 200


def _spec():
    return {
        "module": "roster",
        "version": VERSION,
        "what": "The canonical list of chains on the witness network, "
                "with their tip URLs.",
        "why":
            "Witnessing runs on each operator's own machine, so a server "
            "only witnesses chains it has been told about. Without a "
            "shared list, every new joiner connects to whoever invited "
            "them and the network becomes a star with one operator in "
            "the middle. This route is the list, so a peer's sync can "
            "witness everybody instead of just its introducer.",
        "routes": {
            "GET list": "public. the roster. poll this.",
            "GET health": "public. one-line network summary.",
            "GET spec": "public. this document.",
        },
        "entry_fields": {
            "chain": "the chain's name as it submitted it",
            "tip_url": "where to fetch their current tip. null if they "
                       "have never bound one.",
            "witnessable": "true when tip_url is present",
            "status": "current, silent (no submission in %dh), or unknown"
                      % SILENT_AFTER_HOURS,
            "observations": "how many tips they have submitted to us",
            "liveness": "confirmed / live / self-declared, as recorded at "
                        "submission",
            "name_status": "first-use / bound / conflict / unbound",
        },
        "joining":
            "POST a tip to %s with {\"chain\", \"tip\", \"url\"}. No "
            "account, no key. The url field is what makes you "
            "witnessable by everyone else, so do not omit it." % SELF_OBSERVE,
        "what_this_does_not_do": [
            "It does not witness anything. It is a phone book.",
            "It does not prove a listed chain is honest, only that it "
            "submitted to us and when.",
            "It cannot make another operator witness you. Their server "
            "decides that. This only makes sure they know you exist.",
            "It reflects submissions to this deployment. Another node "
            "publishing its own roster may list a different set.",
        ],
        "drop_in":
            "meshwitness.py reads this route and witnesses every entry on "
            "it. Standard library, one file, one cron line.",
    }


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return _spec(), 200
    if action == "health":
        return _health(ctx)
    if action in ("list", "", "status"):
        return _list(ctx)
    return {"ok": False, "error": "unknown_action", "action": action}, 404
