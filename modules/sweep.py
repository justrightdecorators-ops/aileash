"""
Velocity window sweeper - /x/sweep/<action>

THE LEAK
--------
Velocity tracking keeps three deques per user_id - 60 second, 5 minute and
1 hour windows. Old timestamps inside each deque are pruned correctly, but
the dictionary KEY is never removed. So every user_id ever scored leaves an
empty deque behind forever.

Nothing breaks. Memory just creeps upward, week after week, until one day
years from now the process is killed at an inconvenient hour for reasons
nobody remembers.

THE FIX
-------
Drop any user_id whose windows are all empty. An empty window means that
user has done nothing in the last hour, so the entry carries no information
- it is pure residue. If they come back, the dictionary recreates the entry
on their next event exactly as it did the first time. Nothing is lost and
no behaviour changes.

RUNNING IT
----------
Two options, neither of which touches server.py.

  1. Call POST /x/sweep/run yourself when you think of it.
  2. Point any free uptime or cron service at it hourly. It is idempotent
     and cheap - on a quiet hour it does nothing and says so.

For it to run automatically on boot it would need a thread started in
server.py. That is a four line change and it is deliberately not done here,
because the whole point of the module layout is that server.py stays shut.

    GET  /x/sweep/status   how many entries are tracked, and how many are residue
    POST /x/sweep/run      drop the residue, report what went
"""

import sys, time

VERSION = "1.0"

_last_run = None
_last_dropped = 0
_total_dropped = 0


def _server():
    m = sys.modules.get("__main__")
    if hasattr(m, "WINDOW_60S"):
        return m
    return sys.modules.get("server")


def _windows(s):
    return [("60s", getattr(s, "WINDOW_60S", None)),
            ("5m", getattr(s, "WINDOW_5M", None)),
            ("1h", getattr(s, "WINDOW_1H", None))]


def _status(s):
    out = {}
    keys = set()
    empty = set()
    for name, w in _windows(s):
        if w is None:
            out[name] = "not found"
            continue
        out[name] = len(w)
        for k, q in w.items():
            keys.add(k)
            if not q:
                empty.add(k)
    # a key is residue only if it is empty in every window it appears in
    residue = set()
    for k in empty:
        if all((w is None) or (k not in w) or (not w[k]) for _n, w in _windows(s)):
            residue.add(k)
    return out, len(keys), len(residue)


def handle(method, action, data, api_key, ctx):
    global _last_run, _last_dropped, _total_dropped
    s = _server()
    if s is None or getattr(s, "WINDOW_60S", None) is None:
        return {"error": "windows_not_found",
                "message": "Velocity windows are not exposed by the running server."}, 500

    per_window, tracked, residue = _status(s)

    if method == "GET" and action in ("", "status"):
        return {"tracked_users": tracked,
                "residue_entries": residue,
                "live_entries": tracked - residue,
                "per_window": per_window,
                "last_run": _last_run,
                "last_run_dropped": _last_dropped,
                "dropped_since_boot": _total_dropped,
                "note": "Residue is a user_id with no activity in any window. Dropping it changes nothing except memory."}, 200

    if method == "POST" and action == "run":
        t0 = time.time()
        dropped = 0
        for _name, w in _windows(s):
            if w is None:
                continue
            for k in [k for k, q in list(w.items()) if not q]:
                # re-check under the same pass - a request could have landed
                if not w.get(k):
                    del w[k]
                    dropped += 1
        _last_run = t0
        _last_dropped = dropped
        _total_dropped += dropped
        after, tracked_after, residue_after = _status(s)
        return {"dropped_entries": dropped,
                "tracked_before": tracked,
                "tracked_after": tracked_after,
                "per_window_after": after,
                "took_ms": round((time.time() - t0) * 1000, 2),
                "note": ("nothing to do - no residue this run" if not dropped
                         else "residue removed; returning users are recreated on their next event")}, 200

    return {"error": "unknown_action", "action": action,
            "available": ["GET status", "POST run"]}, 404
