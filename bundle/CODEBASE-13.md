# Codebase — part 13 of 43

Contains:
- `modules/mutual.py`
- `modules/network.py`
- `modules/noexec.py`
- `modules/ots.py`
- `modules/oversight.py`


## `modules/mutual.py`

543 lines, 19704 bytes

```python
#!/usr/bin/env python3
"""
modules/mutual.py  -  the outbound half of mutual witnessing
============================================================

Why this exists
---------------
modules/witness.py RECEIVES. Other chains hand us their tips and we seal
them. Nothing in the platform currently SENDS our tip anywhere, so right
now we witness other people and nobody witnesses us. This module is the
missing direction.

Drop it in as modules/mutual.py. The router picks it up automatically -
no edits to server.py.

Routes
------
  POST /x/mutual/push      send our current tip to every configured peer
  POST /x/mutual/pull      fetch every peer's tip and seal it into our chain
  POST /x/mutual/sync      pull then push (this is the one to schedule)
  GET  /x/mutual/peers     the configured peers and what happened last time
  GET  /x/mutual/status    last run, next run, whether the timer is alive

Important design note
---------------------
This module does not touch the database or import anything from server.py.
It talks HTTP to routes that are already public - ours and theirs. That
means it cannot corrupt anything, it works no matter how seal() changes,
and every action it takes is one an outsider could audit for themselves.

To read our own tip it calls our own public /x/witness/tip.
To seal a peer's tip it calls our own public /x/witness/observe, which is
already built to record exactly that. So a peer tip we pull is recorded by
the same code path as a peer tip that was pushed to us.

FETCH-ONLY PEERS (added 1.2)
----------------------------
observe_url is now OPTIONAL. A peer with a tip_url and no observe_url is
fetch-only: we read and seal their tip, and we do not try to push ours.

That is a real configuration, not a broken one. Two current cases:

  A peer whose outbound submission lane is deliberately closed during
  staging. They serve a tip for us to read; their recorder never reaches
  out. Serving a file is not outbound submission.

  A peer whose tip is a static JSON file with no server behind it. They
  push to us on their own schedule and there is nothing on their side to
  POST to. Perfectly valid node.

Before 1.2 push_one read peer["observe_url"] unconditionally, so adding a
fetch-only peer would have raised KeyError on every cycle - inside a
background thread with a bare except, so it would have failed silently and
taken the whole sync with it.

CONCURRENCY - read this before changing it
------------------------------------------
A sync cycle makes two kinds of call, and they are treated differently on
purpose.

  OUTBOUND to other people's hosts (reading their tip, pushing ours) runs
  in parallel. These are the slow ones - we are waiting on somebody else's
  server, and there is no reason to wait on them one at a time. Fifty peers
  now costs roughly what the slowest single peer costs, instead of the sum
  of all fifty.

  INBOUND to our own server (sealing what we pulled) stays sequential. Our
  own process is handling those requests, and firing a burst of them at
  ourselves while we are mid-cycle is asking for trouble - a queue behind a
  single replica at best. The sealing is fast and local anyway, so there is
  nothing to gain by parallelising it and a real risk in doing so.

So: fetch everything at once, then seal one at a time.

BEFORE THIS WORKS
-----------------
1. "observe" must be in the PUBLIC set of modules/witness.py. If it is not,
   this module gets a 401 from our own server, same as Red Flag AI Pro did.
2. After every deploy, the first /x/ request must be a GET - that is what
   installs the POST branch. Opening /x/mutual/peers in a browser does it.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

VERSION = "1.2"

# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------

# The router reads a set of (METHOD, action) tuples. Anything not listed
# here needs an API key - default is closed.
#
# peers and status are read-only. An outsider being able to see who we
# witness with, and whether it is actually running, is the entire point.
#
# push, pull and sync stay keyed - they cause outbound traffic and are not
# left open to anonymous callers.
PUBLIC = {("GET", "peers"), ("GET", "status")}


# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

# Our own public witness routes. Left as full URLs on purpose so this
# module never has to guess its own host.
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"
OUR_OBSERVE_URL = "https://sebbi.pro/x/witness/observe"

# The name we go by when we hand our tip to someone else.
OUR_CHAIN_NAME = "aileash"

# Everyone we witness with. Add a dict per chain.
#   name         what we file their tips under
#   tip_url      where we GET their current tip          REQUIRED
#   observe_url  where we POST ours so they record it    OPTIONAL
#
# Omit observe_url for a fetch-only peer - see the note at the top. It is
# not an oversight and the module will not complain about it; /x/mutual/peers
# reports the direction for each so it is visible rather than assumed.
PEERS = [
    {
        "name": "red-flag-ai-pro",
        "tip_url": "https://www.redflagaipro.com/api/witness/tip",
        "observe_url": "https://www.redflagaipro.com/api/witness/anchor",
    },
    {
        # Simon. Serves a static JSON file regenerated on his side, and
        # pushes to us on his own systemd timer at :23. Nothing to POST to.
        "name": "flavorflowstrategy.uk",
        "tip_url": "https://www.flavorflowstrategy.uk/witness.json",
    },
    {
        # PRAXIS / Praesidium, chain 4. Read-only, hash-only, currently
        # SYNTHETIC_STAGING and regenerating every ten minutes, so expect
        # liveness "live" rather than "self-consistent" - the tip moves
        # between their generating it and our fetching it. That is the
        # normal case for a working chain, not a failure.
        #
        # Their outbound submission lane is deliberately closed through
        # staging, so no observe_url. They also run a signed lane at
        # /x/peer/submit under peer_id praesidium when they are ready.
        "name": "praesidium",
        "tip_url": "https://chain4.thepraesidium.ai/api/witness/tip",
    },
]

# Field names to send when pushing our tip. If a peer wants different
# names, give that peer its own "keys" dict and it will be used instead.
DEFAULT_PUSH_KEYS = {
    "chain": "chain",
    "tip": "tip",
    "count": "count",
    "ts": "ts",
    "url": "url",
}

# Where peers can read our tip, included in what we push.
OUR_PUBLIC_URL = "https://sebbi.pro/x/witness/tip"

# Background timer. Set ENABLED to False if you would rather drive it
# yourself by hitting /x/mutual/sync.
AUTO_SYNC_ENABLED = True
AUTO_SYNC_SECONDS = 3600

TIMEOUT_SECONDS = 20

# How many peers we talk to at once. Above this they queue, which is fine -
# it stops a large network spawning a thread per peer. Eight slow peers at
# 20s each still finishes in 20s; forty finishes in about a minute worst
# case, and only if every one of them times out.
MAX_PARALLEL_PEERS = 8

# ----------------------------------------------------------------------
# state - deliberately in memory only, this is not evidence
# ----------------------------------------------------------------------

_state = {
    "last_run": None,
    "last_result": None,
    "runs": 0,
    "timer_started": False,
}
_lock = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _reply(payload, status=200):
    """The router expects (payload, status) back from handle()."""
    return payload, status


def _in_parallel(function, items):
    """Run function over items concurrently, preserving input order.

    Used only for calls that leave our server. Anything hitting our own
    process goes through a plain loop instead - see the note at the top.
    """
    if not items:
        return []
    if len(items) == 1:
        return [function(items[0])]
    workers = min(len(items), MAX_PARALLEL_PEERS)
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="mutual-peer") as pool:
        return list(pool.map(function, items))


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------

def _http(url, payload=None):
    """POST if payload given, else GET. Returns (status, parsed_or_text)."""
    data = None
    headers = {"Accept": "application/json",
               "User-Agent": "aileash-mutual/%s" % VERSION}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        status = exc.code
    except urllib.error.URLError as exc:
        return 0, "unreachable: %s" % exc.reason
    except Exception as exc:
        return 0, "failed: %s" % exc
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


# Field names a tip can arrive under. Different implementations name it
# differently and being strict about a name we never published is a bug in
# the receiver, not in the peer. Order is preference, not importance.
TIP_FIELDS = ("tip", "hash", "head", "tip_sha256", "root", "current_tip",
              "chain_tip", "latest")

HEIGHT_FIELDS = ("height", "count", "entries", "tree_size", "size")


def _extract_tip(body):
    """Pull (tip, height) out of whatever shape a tip route returns."""
    if not isinstance(body, dict):
        return None, None
    tip = None
    for field in TIP_FIELDS:
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            tip = value.strip()
            break
    height = None
    for field in HEIGHT_FIELDS:
        if field in body:
            height = body.get(field)
            break
    return tip, height


# ----------------------------------------------------------------------
# the two directions
# ----------------------------------------------------------------------

def our_tip():
    status, body = _http(OUR_TIP_URL)
    if status != 200:
        return None, None, "our own tip route answered %s: %s" % (status, str(body)[:200])
    tip, height = _extract_tip(body)
    if not tip:
        return None, None, "no tip field in our own reply: %s" % str(body)[:200]
    return tip, height, None


def push_one(peer, tip, height):
    """Hand our tip to one peer so they record it. Outbound only.

    A peer with no observe_url is fetch-only by configuration. Say so and
    move on rather than treating it as a failure - and never index the key
    blindly, which is what 1.1 did.
    """
    observe_url = peer.get("observe_url")
    if not observe_url:
        return {
            "peer": peer["name"],
            "direction": "push",
            "skipped": True,
            "ok": True,
            "reason": "fetch-only peer - no observe_url configured",
            "note": ("We read and seal their tip. They do not accept a push, "
                     "either because their outbound lane is closed or because "
                     "their tip is a static file. Not an error."),
        }

    keys = peer.get("keys", DEFAULT_PUSH_KEYS)
    values = {
        "chain": OUR_CHAIN_NAME,
        "tip": tip,
        "count": height,
        "ts": _now(),
        "url": OUR_PUBLIC_URL,
    }
    payload = {keys.get(k, k): v for k, v in values.items()}
    status, body = _http(observe_url, payload)
    result = {
        "peer": peer["name"],
        "direction": "push",
        "url": observe_url,
        "http": status,
        "ok": 200 <= status < 300,
        "response": body if isinstance(body, (dict, list)) else str(body)[:300],
    }
    if status == 401 or status == 403:
        result["hint"] = "they want auth on that route, or it is not in their public set"
    elif status == 404:
        result["hint"] = "wrong path - check observe_url for this peer"
    elif status == 0:
        result["hint"] = "could not reach them at all"
    return result


def fetch_one(peer):
    """Read one peer's current tip. Outbound only - no sealing here.

    Returns a dict that either carries a tip ready to seal, or an error
    already shaped like a result so it can be returned to the caller as is.
    """
    status, body = _http(peer["tip_url"])
    if status != 200:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": body if isinstance(body, (dict, list)) else str(body)[:300],
            "hint": "could not read their tip",
        }

    tip, height = _extract_tip(body)
    if not tip:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": str(body)[:300],
            "hint": ("no tip field in their reply - add the field name to "
                     "TIP_FIELDS. Currently accepted: " + ", ".join(TIP_FIELDS)),
        }

    return {
        "peer": peer["name"], "url": peer["tip_url"],
        "tip": tip, "height": height, "_failed": False,
        "fetched_at": time.time(),
    }


def seal_one(fetched):
    """Seal one already-fetched peer tip into our chain.

    Goes through our own public observe route so a tip we pulled is
    recorded by exactly the same code path as a tip somebody pushed to us.
    Called in a plain loop, never in parallel - this hits our own server.

    Field names must match what modules/witness.py reads out of the body:
    chain, tip, peer_ts, url. The url is what makes the observation
    checkable by a third party rather than taken on our word - it is the
    address we just fetched this tip from.
    """
    seal_status, seal_body = _http(OUR_OBSERVE_URL, {
        "chain": fetched["peer"],
        "tip": fetched["tip"],
        "peer_ts": fetched["fetched_at"],
        "url": fetched["url"],
    })

    out = {
        "peer": fetched["peer"],
        "direction": "pull",
        "their_tip": fetched["tip"],
        "their_height": fetched["height"],
        "sealed_http": seal_status,
        "ok": 200 <= seal_status < 300,
        "response": seal_body if isinstance(seal_body, (dict, list)) else str(seal_body)[:300],
    }
    if seal_status in (401, 403):
        out["hint"] = "our own observe route rejected us - check PUBLIC in modules/witness.py"
    return out


def do_push():
    tip, height, error = our_tip()
    if error:
        return {"ok": False, "error": error}

    # Outbound to everyone at once.
    results = _in_parallel(lambda peer: push_one(peer, tip, height), PEERS)

    return {
        "ok": True,
        "our_tip": tip,
        "our_height": height,
        "pushed_to": len([r for r in results if not r.get("skipped")]),
        "fetch_only": len([r for r in results if r.get("skipped")]),
        "results": results,
    }


def do_pull():
    # Phase one: read every peer's tip at the same time. This is the slow
    # part and none of it touches us.
    fetched = _in_parallel(fetch_one, PEERS)

    # Phase two: seal what came back, one at a time, into our own chain.
    results = []
    for item in fetched:
        if item.get("_failed"):
            item.pop("_failed", None)
            results.append(item)
            continue
        results.append(seal_one(item))

    return {"ok": True, "results": results}


def do_sync():
    """Pull first, then push. That order matters: the tip we hand out then
    already contains the tips we just took in, so the two chains interlock
    rather than merely sitting alongside each other."""
    started = time.time()
    pulled = do_pull()
    pushed = do_push()
    result = {
        "ran_at": _now(),
        "took_seconds": round(time.time() - started, 2),
        "peers": len(PEERS),
        "pull": pulled,
        "push": pushed,
        "ok": bool(pulled.get("ok")) and bool(pushed.get("ok")),
    }
    with _lock:
        _state["last_run"] = result["ran_at"]
        _state["last_result"] = result
        _state["runs"] += 1
    return result


# ----------------------------------------------------------------------
# background timer
# ----------------------------------------------------------------------

def _loop():
    # Let the server finish coming up before the first run.
    time.sleep(45)
    while True:
        try:
            do_sync()
        except Exception:
            pass
        time.sleep(AUTO_SYNC_SECONDS)


def _start_timer():
    with _lock:
        if _state["timer_started"] or not AUTO_SYNC_ENABLED:
            return
        _state["timer_started"] = True
    thread = threading.Thread(target=_loop, name="mutual-sync", daemon=True)
    thread.start()


_start_timer()


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()

    if method == "GET":
        if action == "peers":
            return _reply({
                "chain": OUR_CHAIN_NAME,
                "version": VERSION,
                "peers": [
                    {"name": p["name"],
                     "tip_url": p["tip_url"],
                     "observe_url": p.get("observe_url"),
                     "direction": ("both" if p.get("observe_url")
                                   else "fetch-only")}
                    for p in PEERS
                ],
                "parallel_fetch": MAX_PARALLEL_PEERS,
                "tip_fields_accepted": list(TIP_FIELDS),
                "note": ("Witnessing is only mutual if both columns are live. "
                         "A fetch-only peer is one we read and seal but who "
                         "does not accept a push - either their outbound lane "
                         "is closed or their tip is a static file. Both are "
                         "valid; the direction is published rather than "
                         "implied."),
            })
        if action == "status":
            with _lock:
                return _reply({
                    "version": VERSION,
                    "auto_sync": AUTO_SYNC_ENABLED,
                    "interval_seconds": AUTO_SYNC_SECONDS,
                    "timer_running": _state["timer_started"],
                    "parallel_fetch": MAX_PARALLEL_PEERS,
                    "runs": _state["runs"],
                    "last_run": _state["last_run"],
                    "last_result": _state["last_result"],
                })

    if method == "POST":
        if action == "push":
            return _reply(do_push())
        if action == "pull":
            return _reply(do_pull())
        if action == "sync":
            return _reply(do_sync())

    return _reply({
        "error": "unknown action",
        "GET": ["peers", "status"],
        "POST": ["push", "pull", "sync"],
    }, 404)

```


## `modules/network.py`

487 lines, 19842 bytes

```python
"""
modules/network.py  -  serves the public witness network page

WHY THIS IS A MODULE AND NOT A TEMPLATE
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it - it would arrive as a JSON string. So this does the
same thing router.py already does for POST: it patches the request handler at
runtime, adds a branch for the page path, and leaves every other path exactly
as it was. The patch is idempotent and lives in memory, so a restart reverts it.

THE SAME CATCH AS THE POST PATCH
--------------------------------
A module is only imported when a request reaches the router. So after every
deploy, one request to /x/network/status has to arrive before /witness works.
Opening /x/network/status in a browser does it. Until then the page path falls
through to whatever the server did before, which is a 404 - not an error page,
just the old behaviour.

If you would rather not patch anything, the same HTML works as a plain file in
static/. This exists because the page then lives with the module it describes
rather than drifting away from it.

ROUTES
------
  GET /witness            the page
  GET /witness.html       same page
  GET /x/network/status   whether the patch is installed (public)

The page itself holds no data. It reads /x/witness/tip and /x/witness/peers
from the browser, same as any other visitor would, so it cannot show anything
a stranger could not verify for themselves.
"""

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/witness", "/witness.html", "/network")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The witness network — AILeash</title>
<meta name="description" content="Two independent platforms recording each other's records, hourly. Checkable by anyone, without an account.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,600&family=Inter+Tight:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#E9EDE4;
  --paper-deep:#DFE5D8;
  --ink:#18241F;
  --ink-soft:#4A5A52;
  --rule:#BFCCBF;
  --rule-strong:#9AAC9C;
  --stamp:#7C2B38;
  --verdigris:#2F6B5E;
  --amber:#9A6B1F;
  --gutter:#CBD6C8;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--paper);
  color:var(--ink);
  font-family:"Inter Tight",system-ui,sans-serif;
  font-size:17px;
  line-height:1.6;
  /* ruled paper, faint */
  background-image:repeating-linear-gradient(
    to bottom,
    transparent 0 31px,
    rgba(154,172,156,.20) 31px 32px
  );
}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}

/* ---------- masthead ---------- */
.masthead{padding:52px 0 30px;border-bottom:2px solid var(--ink)}
.eyebrow{
  font-family:"IBM Plex Mono",monospace;
  font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink-soft);margin:0 0 18px;
}
h1{
  font-family:Fraunces,Georgia,serif;
  font-weight:600;font-size:clamp(2.5rem,7.5vw,4.6rem);
  line-height:1.02;letter-spacing:-.02em;margin:0 0 20px;
}
h1 em{font-style:italic;font-weight:300}
.standfirst{font-size:clamp(1.05rem,2.4vw,1.28rem);max-width:40ch;color:var(--ink-soft);margin:0}

/* ---------- the spread ---------- */
.spread{
  margin:44px 0 8px;
  border:1px solid var(--rule-strong);
  background:rgba(255,255,255,.4);
}
.spread-head{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule-strong);
}
.spread-head div{
  font-family:"IBM Plex Mono",monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  padding:12px 16px;color:var(--ink-soft);
}
.spread-head .mid{text-align:center;background:var(--gutter);color:var(--ink)}
.spread-head .right{text-align:right}
.folio{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule);
}
.folio:last-child{border-bottom:0}
.side{padding:20px 16px;min-width:0}
.side.right{text-align:right}
.mid{
  background:var(--gutter);
  display:flex;align-items:center;justify-content:center;
  font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-soft);
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
}
.chain-name{
  font-family:Fraunces,Georgia,serif;font-size:1.35rem;font-weight:600;
  margin:0 0 4px;letter-spacing:-.01em;
}
.role{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-soft);margin:0 0 14px}
.hash{
  font-family:"IBM Plex Mono",monospace;font-size:12.5px;
  word-break:break-all;color:var(--ink);margin:0 0 3px;line-height:1.45;
}
.hash-label{font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 5px}
.meta{font-size:14px;color:var(--ink-soft);margin:12px 0 0}
.meta b{color:var(--ink);font-weight:600}

/* ---------- stamp ---------- */
.stamp{
  display:inline-block;margin-top:16px;padding:6px 13px 5px;
  border:2.5px solid var(--stamp);color:var(--stamp);
  font-family:"IBM Plex Mono",monospace;font-weight:500;
  font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  transform:rotate(-3.5deg);opacity:.9;
}
.stamp.press{animation:press .5s cubic-bezier(.2,1.5,.4,1) both}
@keyframes press{
  0%{opacity:0;transform:rotate(-3.5deg) scale(1.5)}
  70%{opacity:.95;transform:rotate(-3.5deg) scale(.97)}
  100%{opacity:.9;transform:rotate(-3.5deg) scale(1)}
}
.stamp.live{border-color:var(--verdigris);color:var(--verdigris)}
.stamp.weak{border-color:var(--amber);color:var(--amber)}
.stamp.flag{background:var(--stamp);color:var(--paper)}

/* ---------- sections ---------- */
section{padding:56px 0;border-top:1px solid var(--rule-strong)}
h2{
  font-family:Fraunces,Georgia,serif;font-weight:600;
  font-size:clamp(1.6rem,4vw,2.3rem);letter-spacing:-.015em;
  margin:0 0 8px;line-height:1.15;
}
.sec-note{color:var(--ink-soft);max-width:56ch;margin:0 0 30px}
p{max-width:62ch}

.defs{display:grid;gap:0;border-top:1px solid var(--rule)}
.def{
  display:grid;grid-template-columns:170px 1fr;gap:20px;
  padding:15px 0;border-bottom:1px solid var(--rule);
}
.def dt{
  font-family:"IBM Plex Mono",monospace;font-size:12px;
  letter-spacing:.1em;text-transform:uppercase;padding-top:3px;
}
.def dd{margin:0;color:var(--ink-soft)}
.dot{display:inline-block;width:8px;height:8px;margin-right:8px;border-radius:50%;vertical-align:middle}
.dot.ok{background:var(--stamp)}
.dot.mid-c{background:var(--verdigris)}
.dot.weak{background:var(--amber)}

.limits li{max-width:62ch;margin-bottom:13px;color:var(--ink-soft)}
.limits b{color:var(--ink)}

pre{
  font-family:"IBM Plex Mono",monospace;font-size:13px;line-height:1.7;
  background:var(--ink);color:var(--paper);padding:20px;overflow-x:auto;
  border:0;margin:22px 0;
}
pre .k{color:#9FC6B4}
code{font-family:"IBM Plex Mono",monospace;font-size:.92em}

.links{list-style:none;padding:0;margin:24px 0 0}
.links li{border-bottom:1px solid var(--rule);padding:13px 0}
.links a{
  font-family:"IBM Plex Mono",monospace;font-size:13.5px;
  color:var(--ink);text-decoration:none;word-break:break-all;
  display:flex;justify-content:space-between;gap:16px;align-items:baseline;
}
.links a:hover,.links a:focus-visible{color:var(--stamp)}
.links span{color:var(--ink-soft);font-family:"Inter Tight",sans-serif;
  font-size:13px;flex:0 0 auto;text-align:right}

footer{padding:40px 0 70px;color:var(--ink-soft);font-size:14px}
footer a{color:var(--ink)}

.loading,.errbox{
  font-family:"IBM Plex Mono",monospace;font-size:13px;
  color:var(--ink-soft);padding:26px 16px;
}
.errbox b{display:block;color:var(--ink);margin-bottom:6px;font-family:"Inter Tight",sans-serif;font-size:15px}

a:focus-visible,button:focus-visible{outline:2.5px solid var(--stamp);outline-offset:3px}

@media (max-width:760px){
  body{background-image:none}
  .spread-head,.folio{grid-template-columns:1fr}
  .spread-head .mid,.folio .mid{
    border-left:0;border-right:0;
    border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
    padding:7px 0;text-align:center;
  }
  .spread-head .right,.side.right{text-align:left}
  .spread-head div{padding:9px 14px}
  .def{grid-template-columns:1fr;gap:5px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>
</head>
<body>

<div class="wrap">

  <header class="masthead">
    <p class="eyebrow">AILeash · the witness network</p>
    <h1>Two ledgers.<br><em>Neither one is the authority.</em></h1>
    <p class="standfirst">Independent platforms record each other's records, every hour. You can check it yourself, right now, without an account.</p>
  </header>

  <div class="spread" id="spread">
    <div class="spread-head">
      <div>This chain</div>
      <div class="mid">Exchange</div>
      <div class="right">Recorded by</div>
    </div>
    <div id="folios">
      <div class="loading">Reading the ledger…</div>
    </div>
  </div>

  <section>
    <h2>Why this exists</h2>
    <p class="sec-note">Every platform that sells you an audit trail also holds it.</p>
    <p>A hash chain stops anyone else altering the record. It does not stop the operator rebuilding the whole thing and presenting the result as history. Anchoring the chain externally narrows that down — you can't rewrite anything older than your last anchor — and it still leaves the keeper and the checker as the same party.</p>
    <p>Nothing you build alone closes that. Somebody outside has to be holding a copy.</p>
    <p>So each platform here takes the fingerprint of the others' records and seals it into its own. To rewrite your past now, everyone holding a copy would have to rewrite theirs in step, and re-obtain external timestamps that were issued days ago. The second half is the part that can't be done.</p>
  </section>

  <section>
    <h2>What the marks mean</h2>
    <p class="sec-note">Two checks run on every submission. Neither can reject one — everything gets sealed. What changes is how strong we say the claim is.</p>

    <dl class="defs">
      <div class="def"><dt><span class="dot ok"></span>Confirmed</dt><dd>We fetched the address given and it served exactly the tip that was submitted.</dd></div>
      <div class="def"><dt><span class="dot mid-c"></span>Live</dt><dd>The address served a valid but different tip. A working chain moves between submitting and our looking — normal, not a failure.</dd></div>
      <div class="def"><dt><span class="dot weak"></span>Self-declared</dt><dd>No address given, or we couldn't reach it. Taken on their word, and marked as such.</dd></div>
      <div class="def"><dt>First-use</dt><dd>First time this name appeared. It's now bound to the address it came from.</dd></div>
      <div class="def"><dt>Bound</dt><dd>Same address as the first time this name appeared. The same operator, consistently.</dd></div>
      <div class="def"><dt>Conflict</dt><dd>This name has been submitted from a different address than the one it was first bound to. Still sealed, permanently flagged. Operators do move hosts — but you get to see it and decide.</dd></div>
    </dl>
  </section>

  <section>
    <h2>What this does not prove</h2>
    <p class="sec-note">Said plainly, because the value of the rest depends on it.</p>
    <ul class="limits">
      <li><b>It doesn't prove a record was true when it was written.</b> Nothing can. No system reaches back to verify what someone was thinking or whether the data going in was honest. This proves what was recorded, when, and that it hasn't changed since.</li>
      <li><b>It doesn't prove identity.</b> A name is self-declared. Checking the address proves someone runs a live chain producing that data — not that they're who they say. Binding a name to its first address is what makes a change visible.</li>
      <li><b>Two platforms checking each other isn't much of a network.</b> The strength comes from breadth. This gets meaningfully harder to bend with every chain that joins, and not before.</li>
      <li><b>A participant can go quiet.</b> Nobody can force anyone to keep publishing. Gaps show up as stale or silent rather than disappearing, which is the point.</li>
    </ul>
  </section>

  <section>
    <h2>Joining</h2>
    <p class="sec-note">Chains submit their current head to the network and record the heads of others in return.</p>
    <pre><span class="k">POST</span> https://sebbi.pro/x/witness/observe
<span class="k">Content-Type:</span> application/json

{
  "chain": "your-chain-name",
  "tip":   "&lt;64 hex characters — your current chain head&gt;",
  "url":   "https://yoursite/your/tip",
  "ts":    "2026-08-02T14:00:00Z"
}</pre>
    <p><code>url</code> is the address we fetch to check your tip independently — it's the difference between confirmed and self-declared. <code>ts</code> is optional, epoch or ISO.</p>
    <p>Running a chain in the other direction, recording ours as we record yours, is what makes it mutual rather than us keeping a list. If you operate a platform in this space and you're willing to have your history held somewhere you don't control, message me and we'll talk through it and what it costs.</p>
  </section>

  <section>
    <h2>Check it yourself</h2>
    <p class="sec-note">Nothing here needs a login. Open any of these.</p>
    <ul class="links">
      <li><a href="/x/witness/tip">/x/witness/tip<span>our current head</span></a></li>
      <li><a href="/x/witness/peers">/x/witness/peers<span>everyone we record</span></a></li>
      <li><a href="/api/verify-chain">/api/verify-chain<span>chain checked end to end</span></a></li>
      <li><a href="/api/anchor-status">/api/anchor-status<span>the external timestamp</span></a></li>
    </ul>
  </section>

  <footer>
    <p>Sealed records and their attestations are held by each participating platform independently. AILeash operates one chain in this network; it does not run the network. — <a href="https://sebbi.pro">sebbi.pro</a></p>
  </footer>

</div>

<script>
(function(){
  var folios = document.getElementById('folios');

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function stampFor(liveness, nameStatus){
    var cls = 'stamp press', text = String(liveness || 'unchecked');
    if (liveness === 'confirmed') cls += '';
    else if (liveness === 'live') cls += ' live';
    else cls += ' weak';
    if (nameStatus === 'conflict'){ cls += ' flag'; text = 'conflict'; }
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }

  function ago(hours){
    if (hours == null) return 'unknown';
    if (hours < 1) return 'within the hour';
    if (hours < 2) return 'an hour ago';
    if (hours < 48) return Math.round(hours) + ' hours ago';
    return Math.round(hours / 24) + ' days ago';
  }

  function render(ours, peers){
    if (!peers || !peers.length){
      folios.innerHTML = '<div class="errbox"><b>No chains recorded yet.</b>' +
        'Nothing has been submitted to this chain. The first tip posted to ' +
        '/x/witness/observe appears here.</div>';
      return;
    }
    var html = '';
    peers.forEach(function(p){
      html += '<div class="folio">' +
        '<div class="side">' +
          '<p class="chain-name">' + esc(ours.name) + '</p>' +
          '<p class="role">head of chain · height ' + esc(ours.height) + '</p>' +
          '<p class="hash-label">Current tip</p>' +
          '<p class="hash">' + esc(ours.tip) + '</p>' +
          '<p class="meta">Sealed <b>' + esc(ours.sealed) + '</b></p>' +
        '</div>' +
        '<div class="mid">↔</div>' +
        '<div class="side right">' +
          '<p class="chain-name">' + esc(p.peer) + '</p>' +
          '<p class="role">' + esc(p.observations) + ' observations · ' +
              esc(p.distinct_tips) + ' distinct tips</p>' +
          '<p class="hash-label">Name bound to</p>' +
          '<p class="hash">' + esc(p.bound_to || 'no address supplied') + '</p>' +
          '<p class="meta">Last recorded <b>' + esc(ago(p.hours_since_last)) + '</b> · ' +
              esc(p.name_status || 'unchecked') + '</p>' +
          stampFor(p.liveness, p.name_status) +
        '</div>' +
      '</div>';
    });
    folios.innerHTML = html;
  }

  function failed(){
    folios.innerHTML = '<div class="errbox"><b>The ledger did not answer.</b>' +
      'The endpoints are public, so you can try them directly: ' +
      '<a href="/x/witness/peers">/x/witness/peers</a></div>';
  }

  Promise.all([
    fetch('/x/witness/tip').then(function(r){ return r.json(); }),
    fetch('/x/witness/peers').then(function(r){ return r.json(); })
  ]).then(function(res){
    var tip = res[0] || {}, peers = res[1] || {};
    render({
      name: 'aileash',
      tip: tip.tip || 'unavailable',
      height: tip.height == null ? '—' : tip.height,
      sealed: tip.sealed_at ? new Date(tip.sealed_at).toUTCString().replace(' GMT','  UTC') : 'unknown'
    }, peers.peers || []);
  }).catch(failed);
})();
</script>

</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    """Add a page branch to do_GET at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_page_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._page_patched = True
    _patched[0] = True
    print("NETWORK: /witness page branch installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("NETWORK: page patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/witness",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": "The page reads /x/witness/tip and /x/witness/peers from the browser. It holds no data of its own.",
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404

```


## `modules/noexec.py`

490 lines, 22739 bytes

```python
"""
modules/noexec.py  v1.1.0
The NO-EXEC blind bundle: six real objects from the live system, each one
authentic, each one attached to a claim it may not support.

Arm after each deploy:  https://sebbi.pro/x/noexec/status

    GET /x/noexec/build              mint the six objects on the live chain,
                                     pack them into one bundle, seal the
                                     bundle fingerprint and a salted
                                     commitment to the answer key, and hand
                                     back the links (one build per 10 minutes)
    GET /x/noexec/bundle?id=         the bundle exactly as sent: claims and
                                     objects only, no verdicts, no hints
    GET /x/noexec/reveal?id=&secret= the answer key plus its salt, so anyone
                                     can recompute the sealed commitment
    GET /x/noexec/reveal?id=&admin=  the operator's own unlock (ADMIN_PASSWORD), for
                                     when the reveal link is lost. It publishes the
                                     key: from then on the plain link works for anyone
                                     and the reveal itself is sealed in the chain
    GET /x/noexec/status             module status

How the six are made (nothing faked, nothing edited afterwards):
  1  a passport minted, then redeemed once, redemption sealed
  2  a passport minted, then its grant revoked, revocation sealed
  3  a passport minted for one site, never presented anywhere
  4  a signed authority proof bundle for an ALLOW evaluation whose grant
     window is fifteen minutes long
  5  the sealed Temporal Standing Test evidence package, run r_72d2d93a5c2a4988
  6  the latest self-proving archive file and the sealed custody count

Built on continuity.py (1.6.0+) and passport.py. Neither is changed.
"""

import hashlib
import importlib
import importlib.util
import json
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.1.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "build"), ("GET", "bundle"), ("GET", "reveal")}

SITE = "https://sebbi.pro"
KEY = "noexec-blind-bundle"
GAP = 600
CAP = "noexec.pay"
TAGS = ["noexec"]
AUD = "checkout.sebbi.pro"
AUD_OTHER = "bookings.sebbi.pro"
PARAMS = {"amount": 20}
TST_RUN = "r_72d2d93a5c2a4988"
TST_REVIEW = "https://studio.moralclarity.ai/temporal-standing-test"

_ready = False
_last = [0.0]


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _block_url(n):
    return SITE + "/x/walk/block?index=%s" % n if n is not None else None


def _load(name, must_have):
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith(os.sep + name + ".py") and all(hasattr(m, a) for a in must_have):
            return m
    pkg = __package__ or ""
    try:
        m = importlib.import_module(pkg + "." + name if pkg else name)
        if all(hasattr(m, a) for a in must_have):
            return m
    except Exception:
        pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("noexec_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _call(name, action, data, ctx):
    """Ask another live module for one of its public answers. Never raises."""
    try:
        m = _load(name, ("handle",))
        out = m.handle("GET", action, data, None, ctx)
        body = out[0] if isinstance(out, tuple) else out
        return body if isinstance(body, dict) else {"raw": str(body)[:4000]}
    except Exception as e:
        return {"unavailable": str(e)[:200]}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS noexec_bundle(id TEXT PRIMARY KEY,created REAL,"
                  "bundle TEXT,bundle_sha256 TEXT,answer_key TEXT,key_commitment TEXT,"
                  "secret_digest TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS noexec_revealed(id TEXT PRIMARY KEY,at REAL,"
                  "how TEXT,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _seal(ctx, kind, extra):
    ev = {"user_id": "noexec:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "noexec", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "noexec_version": VERSION}
    res.update(extra)
    out = ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _grant(C, ctx, gid, subject, now):
    g = {"id": gid, "issuer": "justin-dobson", "issuer_kind": "human", "subject": subject,
         "scope": [CAP], "constraints": {"max_amount": 50},
         "purpose": "NO-EXEC blind bundle for independent review", "purpose_tags": TAGS,
         "not_after": now + 900}
    r, s = C._issue(ctx, KEY, g)
    if s != 200:
        raise RuntimeError("grant %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _mint(P, C, ctx, gid, audience):
    r, s = P._mint(ctx, C, KEY, {"grant": gid, "action": CAP, "params": PARAMS,
                                 "purpose_tag": TAGS[0], "audience": audience})
    if s != 200 or not r.get("issued"):
        raise RuntimeError("passport for %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _passport_sources(token, gid, issued_block):
    return {"live_check": SITE + "/x/passport/verify?token=" + token,
            "token_format": SITE + "/x/passport/spec",
            "public_key": SITE + "/x/continuity/pubkey",
            "grant_lineage": SITE + "/x/continuity/trace?grant=" + gid,
            "issued_in_block": _block_url(issued_block)}


def _build(ctx):
    now = time.time()
    if now - _last[0] < GAP:
        return {"error": "too_soon", "retry_after_seconds": int(GAP - (now - _last[0]))}, 429
    _last[0] = now
    C = _load("continuity", ("_issue", "_evaluate", "_revoke", "_proof", "_confirm"))
    P = _load("passport", ("_mint", "_redeem", "_check"))
    C._setup(ctx)
    P._setup(ctx)

    tag = uuid.uuid4().hex[:10]
    agent = "agent-" + tag
    cases, key = [], []

    # 1 - the spent passport
    g1 = "nx_%s_1" % tag
    _grant(C, ctx, g1, agent, now)
    p1 = _mint(P, C, ctx, g1, AUD)
    r1, _s = P._redeem(ctx, C, {"token": p1["passport"], "audience": AUD, "params": PARAMS})
    if not r1.get("redeemed"):
        raise RuntimeError("case 1 redemption did not bind: %s" % _canon(r1)[:300])
    cases.append({"case": 1,
                  "claim": "This agent is authorised to perform this action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p1["passport"]},
                  "sources": _passport_sources(p1["passport"], g1, p1.get("block_index"))})
    key.append({"case": 1, "verdict": "NOT PROVEN",
                "what_it_proves": "Authorised once, for %s of %s at %s." % (CAP, _canon(PARAMS), AUD),
                "why_not": "Already redeemed; the redemption is sealed in block %s. Nothing "
                           "authorises a further execution." % r1.get("block_index"),
                "evidence": [_block_url(r1.get("block_index"))]})

    # 2 - the revoked passport
    g2 = "nx_%s_2" % tag
    _grant(C, ctx, g2, agent, now)
    p2 = _mint(P, C, ctx, g2, AUD)
    rv, _s = C._revoke(ctx, KEY, {"grant": g2, "reason": "human withdrew the authority"})
    cases.append({"case": 2,
                  "claim": "This agent was authorised at the moment of action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p2["passport"]},
                  "sources": _passport_sources(p2["passport"], g2, p2.get("block_index"))})
    key.append({"case": 2, "verdict": "NOT PROVEN",
                "what_it_proves": "The signature is genuine and the passport was in date: an "
                                  "offline verifier says VALID.",
                "why_not": "The grant behind it was revoked (block %s) after issue. Standing is "
                           "lost, so no moment of action after that is authorised. Signature "
                           "validity is not standing." % rv.get("block_index"),
                "evidence": [_block_url(rv.get("block_index")),
                             SITE + "/x/continuity/trace?grant=" + g2]})

    # 3 - the misdirected passport (never presented anywhere, so still unspent)
    g3 = "nx_%s_3" % tag
    _grant(C, ctx, g3, agent, now)
    p3 = _mint(P, C, ctx, g3, AUD_OTHER)
    cases.append({"case": 3,
                  "claim": "This agent is authorised to act at %s." % AUD,
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p3["passport"]},
                  "sources": _passport_sources(p3["passport"], g3, p3.get("block_index"))})
    key.append({"case": 3, "verdict": "NOT PROVEN",
                "what_it_proves": "Genuine, unspent and unrevoked authority at %s." % AUD_OTHER,
                "why_not": "The passport's audience is %s. It says nothing about %s."
                           % (AUD_OTHER, AUD),
                "evidence": [SITE + "/x/passport/spec"]})

    # 4 - the signed proof of a past ALLOW
    g4 = "nx_%s_4" % tag
    gr4 = _grant(C, ctx, g4, agent, now)
    ev, s = C._evaluate(ctx, KEY, {"grant": g4, "action": CAP, "params": PARAMS,
                                   "purpose_tag": TAGS[0]})
    if s != 200 or ev.get("verdict") != "ALLOW":
        raise RuntimeError("case 4 evaluation was not ALLOW: %s" % _canon(ev)[:300])
    proof, s = C._proof(ctx, {"evaluation": ev["evaluation"]})
    if s != 200:
        raise RuntimeError("case 4 proof not produced: %s" % _canon(proof)[:300])
    cases.append({"case": 4,
                  "claim": "This agent holds this authority.",
                  "object": {"authority_proof": proof},
                  "sources": {"proof": SITE + "/x/continuity/proof?evaluation=" + ev["evaluation"],
                              "public_key": SITE + "/x/continuity/pubkey",
                              "derivation_rules": SITE + "/x/continuity/spec",
                              "grant_lineage": SITE + "/x/continuity/trace?grant=" + g4}})
    key.append({"case": 4, "verdict": "NOT PROVEN",
                "what_it_proves": "Authority stood, and the ALLOW re-derives from the lineage, at "
                                  "%s." % ev.get("evaluated_at", _iso(now)),
                "why_not": "A proof of an instant says nothing about now. The grant's window "
                           "closes at %s; any present-tense claim needs a live standing check."
                           % gr4.get("not_after"),
                "evidence": [SITE + "/x/continuity/trace?grant=" + g4]})

    # 5 - the real test, the narrower finding
    tst = _call("standing", "evidence", {"run": TST_RUN}, ctx)
    cases.append({"case": 5,
                  "claim": "sebbi.pro passed the Temporal Standing Test.",
                  "object": {"evidence_package": tst},
                  "sources": {"evidence": SITE + "/x/standing/evidence?run=" + TST_RUN,
                              "freeze_sealed_in": _block_url(2387),
                              "run_sealed_in": _block_url(2398),
                              "test_definition": TST_REVIEW}})
    key.append({"case": 5, "verdict": "NOT PROVEN",
                "what_it_proves": "A pre-registered run, freeze sealed before execution (block "
                                  "2387 before 2398), both branches recorded as observed.",
                "why_not": "The independent reviewer's finding is narrower than the package's "
                           "own 'PASS': revocation-aware authorisation and execution binding "
                           "ESTABLISHED; temporal standing on external facts (a still-valid "
                           "grant defeated by a change in an authoritative external fact) NOT "
                           "YET ESTABLISHED. The object is authentic; its summary overstates "
                           "what it supports.",
                "evidence": [SITE + "/x/standing/evidence?run=" + TST_RUN, TST_REVIEW]})

    # 6 - the archive with no custodians
    man = _call("archive", "manifest", {}, ctx)
    files = man.get("files") if isinstance(man, dict) else None
    latest = files[0] if isinstance(files, list) and files else man
    cus = _call("custody", "status", {}, ctx)
    cases.append({"case": 6,
                  "claim": "sebbi.pro's record is held independently.",
                  "object": {"archive_file": latest, "custody": cus},
                  "sources": {"archive_manifest": SITE + "/x/archive/manifest",
                              "archive_file": (latest or {}).get("file") if isinstance(latest, dict) else None,
                              "sealed_in": (latest or {}).get("check_block") if isinstance(latest, dict) else None,
                              "custody_count": SITE + "/x/custody/status"}})
    key.append({"case": 6, "verdict": "NOT PROVEN",
                "what_it_proves": "Integrity: the file is content-addressed, sealed in the chain, "
                                  "and its embedded verifier passes.",
                "why_not": "Independence: the sealed custody count of holders other than "
                           "sebbi.pro is %s." % _custody_count(cus),
                "evidence": [SITE + "/x/custody/status"]})

    for c in cases:
        c["object_sha256"] = _sha(c["object"])

    bid = "nx_" + tag
    captured = _iso(time.time())
    bundle = {
        "bundle": bid,
        "format": "noexec-blind-bundle/1",
        "issuer": "sebbi.pro",
        "captured_at": captured,
        "instructions": "Six objects taken from the live system. Each is presented with the "
                        "claim being made with it and nothing else. Fetch every source "
                        "yourself rather than trusting this copy; each object carries the "
                        "SHA-256 of its canonical JSON (keys sorted, separators ',' ':').",
        "format_notes": {
            "passport": "sbp1.<base64url body>.<base64url Ed25519 signature>; the signature "
                        "is over 'AILEASH-PASSPORT-v1:' || body bytes. Passports carry a "
                        "5-minute validity window (exp).",
            "chain_blocks": SITE + "/x/walk/block?index=<n>",
        },
        "cases": cases,
    }
    bundle_sha = _sha(bundle)

    salt = secrets.token_hex(32)
    answer = {"bundle": bid, "bundle_sha256": bundle_sha, "salt": salt, "answers": key}
    commitment = _sha(answer)
    secret = secrets.token_urlsafe(18)
    audit_hash, block = _seal(ctx, "noexec_bundle_committed",
                              {"bundle": bid, "bundle_sha256": bundle_sha,
                               "answer_key_commitment": commitment,
                               "detail": "bundle=%s;sha256=%s;key_commitment=%s"
                                         % (bid, bundle_sha, commitment)})
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO noexec_bundle VALUES(?,?,?,?,?,?,?,?,?)",
                            (bid, time.time(), _canon(bundle), bundle_sha, _canon(answer),
                             commitment, hashlib.sha256(secret.encode()).hexdigest(),
                             audit_hash, block))
        ctx["conn"].commit()
    return {"built": True, "bundle": bid,
            "send_this_link": SITE + "/x/noexec/bundle?id=" + bid,
            "bundle_sha256": bundle_sha,
            "answer_key_commitment": commitment,
            "sealed_in_chain": audit_hash, "block_index": block,
            "check_the_seal": _block_url(block),
            "reveal_later_keep_private": SITE + "/x/noexec/reveal?id=%s&secret=%s" % (bid, secret),
            "note": "Send only the bundle link. Keep the reveal link to yourself until the "
                    "reviewer has published results."}, 200


def _custody_count(cus):
    if not isinstance(cus, dict):
        return "unavailable"
    for k in ("independent_holders_today", "independent_holders", "holders_today", "count",
              "independent"):
        if k in cus:
            return cus[k]
    for v in cus.values():
        if isinstance(v, dict):
            for k in ("independent_holders", "count", "holders"):
                if k in v:
                    return v[k]
    return "as sealed at " + SITE + "/x/custody/status"


def _query(ctx):
    """Read the query string straight off the live request, whatever the router passed:
    from the handler in ctx if there is one, otherwise from the request handler found on
    the call stack (the same way page modules find it)."""
    from urllib.parse import parse_qs
    paths = []
    try:
        if isinstance(ctx, dict):
            for k in ("handler", "h", "request_handler", "request"):
                h = ctx.get(k)
                if h is not None and getattr(h, "path", None):
                    paths.append(h.path)
        f = sys._getframe()
        while f is not None:
            o = f.f_locals.get("self")
            if o is not None and hasattr(o, "wfile") and isinstance(getattr(o, "path", None), str):
                paths.append(o.path)
                break
            f = f.f_back
    except Exception:
        pass
    for path in paths:
        if "?" in path:
            return {k: v[0] for k, v in parse_qs(path.split("?", 1)[1]).items()}
    return {}


def _q(data, k):
    v = data.get(k, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v).strip()


def _get(ctx, bid):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT id,created,bundle,bundle_sha256,answer_key,key_commitment,secret_digest,"
            "audit_hash,block_index FROM noexec_bundle WHERE id=?", (bid,)).fetchone()


def _bundle(ctx, data):
    row = _get(ctx, _q(data, "id"))
    if not row:
        return {"error": "bundle_not_found"}, 404
    return {"bundle": json.loads(row[2]), "bundle_sha256": row[3],
            "answer_key_commitment": row[5],
            "commitment_sealed_in_chain": row[7], "commitment_block": _block_url(row[8]),
            "commitment_rule": "SHA-256 of the canonical JSON of the answer key, which includes "
                               "this bundle's SHA-256 and a random salt. It was sealed before "
                               "this bundle was sent and will be revealed after review."}, 200


def _reveal(ctx, data):
    import hmac
    bid = _q(data, "id")
    row = _get(ctx, bid)
    if not row:
        return {"error": "bundle_not_found"}, 404
    with ctx["lock"]:
        pub = ctx["conn"].execute("SELECT at,how,audit_hash,block_index FROM noexec_revealed "
                                  "WHERE id=?", (bid,)).fetchone()
    secret = _q(data, "secret")
    admin = _q(data, "admin")
    pw = os.environ.get("ADMIN_PASSWORD", "")
    by_secret = bool(secret) and hashlib.sha256(secret.encode()).hexdigest() == row[6]
    by_admin = bool(admin) and bool(pw) and hmac.compare_digest(admin, pw)
    if not (pub or by_secret or by_admin):
        return {"error": "not_yet_revealed"}, 403
    if not pub:
        how = "reveal link" if by_secret else "operator unlock (reveal link lost)"
        audit_hash, block = _seal(ctx, "noexec_key_revealed",
                                  {"bundle": bid, "answer_key_commitment": row[5],
                                   "how": how,
                                   "detail": "bundle=%s;revealed_by=%s" % (bid, how)})
        with ctx["lock"]:
            ctx["conn"].execute("INSERT OR IGNORE INTO noexec_revealed VALUES(?,?,?,?,?)",
                                (bid, time.time(), how, audit_hash, block))
            ctx["conn"].commit()
        pub = (time.time(), how, audit_hash, block)
    answer = json.loads(row[4])
    return {"answer_key": answer, "recomputed_commitment": _sha(answer),
            "sealed_commitment": row[5], "matches": _sha(answer) == row[5],
            "commitment_sealed_in": _block_url(row[8]),
            "revealed": {"at": _iso(pub[0]), "how": pub[1], "sealed_in": _block_url(pub[3])},
            "share_this_link": SITE + "/x/noexec/reveal?id=" + bid,
            "check_it_yourself": "SHA-256 of the canonical JSON of answer_key (keys sorted, "
                                 "separators ',' ':', UTF-8) must equal sealed_commitment, "
                                 "which was sealed before the bundle was sent."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/")
    data = dict(data or {})
    if "?" in action:
        from urllib.parse import parse_qs
        action, qs = action.split("?", 1)
        for k, v in parse_qs(qs).items():
            data.setdefault(k, v[0])
    for k, v in _query(ctx).items():
        if not _q(data, k):
            data[k] = v
    action = action.strip("/")
    parts = action.split("/")
    if len(parts) > 1:
        action = parts[0]
        if not _q(data, "id"):
            data["id"] = parts[1]
        if len(parts) > 2 and not _q(data, "secret"):
            data["secret"] = parts[2]
    action = action.lower()
    if action in ("status", "spec", ""):
        with ctx["lock"]:
            n = ctx["conn"].execute("SELECT COUNT(*) FROM noexec_bundle").fetchone()[0]
            last = ctx["conn"].execute("SELECT id,block_index FROM noexec_bundle ORDER BY created "
                                       "DESC LIMIT 3").fetchall()
        return {"module": "noexec", "version": VERSION, "armed": True, "bundles_built": n,
                "latest": [{"bundle": r[0], "link": SITE + "/x/noexec/bundle?id=" + r[0],
                            "sealed_block": r[1]} for r in last],
                "build": SITE + "/x/noexec/build"}, 200
    if action == "build":
        try:
            return _build(ctx)
        except Exception as e:
            _last[0] = 0.0
            return {"built": False, "error": str(e)[:500]}, 500
    if action == "bundle":
        return _bundle(ctx, data)
    if action == "reveal":
        return _reveal(ctx, data)
    return {"error": "unknown_action", "GET": ["status", "build", "bundle", "reveal"]}, 404

```


## `modules/ots.py`

753 lines, 30216 bytes

```python
"""
modules/ots.py  v1.2  -  serve the OpenTimestamps proofs, and upgrade them

anchor.py stamps the chain tip hourly and writes the .ots proof to the
anchor volume. Nothing served those files, so "anchored to Bitcoin" was a
claim a third party had to take on trust.

PENDING IS NOT CONFIRMED. A proof written at stamping time holds a PENDING
attestation - a calendar's promise to commit the digest to Bitcoin. It is
not evidence of anything on chain until it is UPGRADED, after the
calendar's transaction lands. anchor.py never upgraded, so every proof
written before this module is pending. Said plainly because an auditor's
own verifier says it first.

v1.1: the automatic upgrade now skips proofs that are already confirmed.
v1.0 took the oldest 20 every run whether or not they were finished, so
once those 20 confirmed it kept re-checking them forever and never reached
the pending ones behind them. Confirmed counts now only count proofs that
became confirmed in that run, not ones that already were.

v1.2: the newest proofs matter most. Every run now upgrades half its batch
from the newest end as well as half from the oldest, so tips of the chain
running today confirm within hours instead of waiting behind the backlog.
A new public route, latest_confirmed, serves the newest proof that is
confirmed in Bitcoin AND whose tip is a block in the chain running now -
the one address a verifier needs. Two more calendars are asked (bob and
finney), because proofs name whichever calendars accepted them.

Routes: spec, status, list, proof, latest_confirmed public. upgrade keyed.
Proofs live at ANCHOR_DIR (default /data/anchors) - only durable on Railway
if a volume is mounted there. /x/ots/status reports what is really present.
"""

import base64
import hashlib
import json
import os
import threading
import time

VERSION = "1.2"

PUBLIC = {("GET", "spec"), ("GET", "status"), ("GET", "list"),
          ("GET", "proof"), ("GET", "latest_confirmed")}

ANCHOR_DIR = os.environ.get("ANCHOR_DIR", "/data/anchors")
MAX_PROOF_BYTES = 262144

CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
]

# ---- automatic upgrading
#
# anchor.py stamps and walks away, which is how 767 proofs ended up pending.
# This finishes the job on a timer so nobody has to remember to.
#
# The calendars are free public infrastructure run by volunteers. Firing 767
# requests at them in one go would be rude and would probably get us rate
# limited, so this works in small batches, oldest first, and skips anything
# too young to have confirmed yet, and anything already confirmed. A backlog
# clears over days rather than minutes, which is fine - nothing is lost by a
# proof staying pending a little longer, and the stamp time is already fixed.
AUTO_UPGRADE_ENABLED = os.environ.get("OTS_AUTO_UPGRADE", "1") == "1"
AUTO_UPGRADE_INTERVAL = int(os.environ.get("OTS_UPGRADE_INTERVAL", "3600"))
AUTO_UPGRADE_BATCH = int(os.environ.get("OTS_UPGRADE_BATCH", "20"))

# A Bitcoin confirmation takes an hour or more, and the calendars aggregate
# before they commit. Asking about a proof stamped ten minutes ago wastes a
# request and gets a "not ready" every time.
MIN_AGE_SECONDS = int(os.environ.get("OTS_MIN_AGE", "10800"))

# Breathing room between calendar calls.
CALENDAR_PAUSE = 0.5

_auto = {"started": False, "runs": 0, "last_run": None, "last_result": None,
         "upgraded_total": 0, "confirmed_total": 0}

# Stamp ids already seen confirmed. A confirmed proof never goes back to
# pending, so once seen it is never read or asked about again.
_confirmed_seen = set()
_file_lock = threading.Lock()


def _read_index():
    path = os.path.join(ANCHOR_DIR, "anchors.jsonl")
    rows = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue
    except Exception:
        pass
    return rows


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _stamp_id(path):
    if not path:
        return None
    name = os.path.basename(path)
    if name.startswith("tip_") and name.endswith(".ots"):
        return name[4:-4]
    return None


def _describe(raw):
    """What is actually inside this proof. Never guesses."""
    out = {"pending_calendars": [], "bitcoin_block_heights": [],
           "state": "unknown", "read_error": None}
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import (PendingAttestation,
                                                BitcoinBlockHeaderAttestation)
    except Exception as exc:
        out["read_error"] = "opentimestamps library not available: %s" % exc
        return out

    try:
        detached = DetachedTimestampFile.deserialize(
            BytesDeserializationContext(raw))
    except Exception as exc:
        out["read_error"] = "could not parse proof: %s" % exc
        out["state"] = "unreadable"
        return out

    def walk(timestamp):
        for att in timestamp.attestations:
            if isinstance(att, PendingAttestation):
                uri = att.uri
                if isinstance(uri, bytes):
                    uri = uri.decode("utf-8", "replace")
                if uri not in out["pending_calendars"]:
                    out["pending_calendars"].append(uri)
            elif isinstance(att, BitcoinBlockHeaderAttestation):
                h = getattr(att, "height", None)
                if h is not None and h not in out["bitcoin_block_heights"]:
                    out["bitcoin_block_heights"].append(h)
        for _, sub in timestamp.ops.items():
            walk(sub)

    try:
        walk(detached.timestamp)
    except Exception as exc:
        out["read_error"] = "could not walk proof: %s" % exc
        return out

    if out["bitcoin_block_heights"]:
        out["state"] = "confirmed"
        out["means"] = ("Committed in Bitcoin block %s. Verifiable against "
                        "the blockchain by anyone, with nothing from us."
                        % ", ".join(str(h) for h in out["bitcoin_block_heights"]))
    elif out["pending_calendars"]:
        out["state"] = "pending"
        out["means"] = ("A calendar has accepted this digest and promised to "
                        "commit it to Bitcoin. NOT yet evidence of anything "
                        "on chain. Upgrade it once the transaction confirms.")
    else:
        out["state"] = "empty"
        out["means"] = "No attestations found in this proof."
    return out


def _proof_bytes(stamp_id):
    path = os.path.join(ANCHOR_DIR, "tip_%s.ots" % stamp_id)
    if not os.path.exists(path):
        return None, path, "no proof file at %s" % path
    try:
        if os.path.getsize(path) > MAX_PROOF_BYTES:
            return None, path, "proof unexpectedly large"
        with open(path, "rb") as handle:
            return handle.read(), path, None
    except Exception as exc:
        return None, path, "could not read proof: %s" % exc


def _tip_for(stamp_id):
    try:
        with open(os.path.join(ANCHOR_DIR, "tip_%s.txt" % stamp_id)) as h:
            return h.read().strip()
    except Exception:
        return None


def _is_confirmed(sid):
    """True if this proof already carries a Bitcoin attestation."""
    if sid in _confirmed_seen:
        return True
    raw, _p, _e = _proof_bytes(sid)
    if raw is None:
        return False
    if _describe(raw)["state"] == "confirmed":
        _confirmed_seen.add(sid)
        return True
    return False


def _pending_candidates(limit=None):
    """Stamps old enough to be worth asking about and not yet confirmed,
    oldest first.

    Oldest first on purpose: the oldest pending proofs are the ones most
    likely to have confirmed, so a backlog clears from the far end rather
    than the recent end. Already-confirmed proofs are skipped, otherwise
    they would fill every batch forever.
    """
    now = time.time()
    out = []
    for row in _read_index():
        if not row.get("ots"):
            continue
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        if now - float(sid) < MIN_AGE_SECONDS:
            continue
        if not os.path.exists(os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid)):
            continue
        if _is_confirmed(sid):
            continue
        out.append(sid)
        if limit is not None and len(out) >= limit:
            break
    return out


def _pending_count():
    return len(_pending_candidates())


def _newest_pending(limit):
    """Pending proofs old enough to have confirmed, NEWEST first. These are
    the tips of the chain running today, the ones a verifier asks about."""
    now = time.time()
    out = []
    for row in reversed(_read_index()):
        if not row.get("ots"):
            continue
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        if now - float(sid) < MIN_AGE_SECONDS:
            continue
        if not os.path.exists(os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid)):
            continue
        if _is_confirmed(sid):
            continue
        out.append(sid)
        if len(out) >= limit:
            break
    return out


def _tip_in_chain(tip, ctx):
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if conn is None or lock is None or not tip:
        return None
    try:
        with lock:
            r = conn.execute("SELECT id FROM audit_log WHERE audit_hash = ?",
                             (tip,)).fetchone()
        return r[0] if r else False
    except Exception:
        return None


LATEST_SCAN = 500


def _latest_confirmed(ctx):
    """The newest proof that is confirmed in Bitcoin and whose tip is a
    block in the chain running now. Checked in that order, newest first."""
    rows = [r for r in reversed(_read_index()) if r.get("ots")]
    looked = 0
    for row in rows[:LATEST_SCAN]:
        sid = _stamp_id(row.get("ots_file"))
        if not sid or not sid.isdigit():
            continue
        looked += 1
        raw, _p, _e = _proof_bytes(sid)
        if raw is None:
            continue
        d = _describe(raw)
        if d["state"] != "confirmed":
            continue
        _confirmed_seen.add(sid)
        tip = (_tip_for(sid) or row.get("tip") or "").strip().lower()
        block = _tip_in_chain(tip, ctx)
        if block is False:
            continue
        out, status = _proof({"ts": sid})
        if status != 200:
            continue
        out["tip_is_block"] = block
        out["check_block"] = ("https://sebbi.pro/x/walk/block?index=%s" % block
                              if block else None)
        out["why_this_one"] = ("The newest proof that is confirmed in Bitcoin "
                               "and whose tip is a block in the chain running "
                               "now. Older confirmations of earlier chains are "
                               "skipped, not hidden - they stay at /x/ots/list.")
        return out, 200
    return {"ok": False, "error": "no_confirmed_current_proof_yet",
            "looked_at": looked,
            "detail": "No proof of a current-chain tip has confirmed in Bitcoin "
                      "yet. The upgrader works the newest end every hour, and "
                      "a confirmation takes a few hours. Nothing is wrong; it "
                      "is simply not there yet.",
            "status": "https://sebbi.pro/x/ots/status"}, 404


def _status():
    rows = _read_index()
    exists = os.path.isdir(ANCHOR_DIR)
    files = []
    if exists:
        try:
            files = [f for f in os.listdir(ANCHOR_DIR) if f.endswith(".ots")]
        except Exception:
            files = []

    stamped = [r for r in rows if r.get("ots")]
    out = {
        "ok": True, "module": "ots", "version": VERSION,
        "anchor_dir": ANCHOR_DIR,
        "storage_present": exists,
        "proof_files_on_disk": len(files),
        "anchor_attempts_recorded": len(rows),
        "stamped": len(stamped),
        "failed": len(rows) - len(stamped),
        "first_attempt": _iso(rows[0].get("ts")) if rows else None,
        "last_attempt": _iso(rows[-1].get("ts")) if rows else None,
    }

    if not exists:
        out["warning"] = (
            "The anchor directory does not exist on this container. Either "
            "no anchor has run, or no persistent volume is mounted at %s - "
            "in which case every proof is lost on redeploy and the history "
            "restarts silently. Check before calling this durable."
            % ANCHOR_DIR)
    elif len(files) < len(stamped):
        out["warning"] = (
            "%d successful stamps recorded but only %d proof files on disk. "
            "Files have been lost, most likely to a redeploy without a "
            "persistent volume." % (len(stamped), len(files)))

    if stamped:
        sid = _stamp_id(stamped[-1].get("ots_file"))
        if sid:
            raw, _p, err = _proof_bytes(sid)
            if raw:
                d = _describe(raw)
                out["latest_proof"] = {
                    "stamp_id": sid, "tip": stamped[-1].get("tip"),
                    "stamped_at": _iso(stamped[-1].get("ts")),
                    "state": d["state"],
                    "bitcoin_block_heights": d["bitcoin_block_heights"],
                    "pending_calendars": d["pending_calendars"],
                    "means": d.get("means"),
                    "read_error": d.get("read_error"),
                }
            else:
                out["latest_proof"] = {"stamp_id": sid, "error": err}

    out["auto_upgrade"] = {
        "enabled": AUTO_UPGRADE_ENABLED,
        "running": _auto["started"],
        "every_seconds": AUTO_UPGRADE_INTERVAL,
        "batch_size": AUTO_UPGRADE_BATCH,
        "skips_proofs_under_hours": MIN_AGE_SECONDS // 3600,
        "runs": _auto["runs"],
        "last_run": _auto["last_run"],
        "last_result": _auto["last_result"],
        "upgraded_since_start": _auto["upgraded_total"],
        "newly_confirmed_since_start": _auto["confirmed_total"],
        "confirmed_seen": len(_confirmed_seen),
        "pending_eligible_now": _pending_count(),
        "note": ("Each run takes half its batch from the newest proofs and half "
                 "from the oldest, skipping proofs already confirmed. The calendars are free infrastructure run by "
                 "volunteers, so a backlog clears over days rather than "
                 "minutes. Nothing is lost by a proof staying pending longer "
                 "- the stamp time is already fixed."),
    }

    out["honest_note"] = (
        "A proof written at stamping time is PENDING - a promise to commit "
        "the digest to Bitcoin, not evidence that it has been. It becomes "
        "confirmed only after being upgraded. The auto-upgrade does that on "
        "a timer; until a proof is upgraded, pending is what it is.")
    return out, 200


def _list(data):
    rows = _read_index()
    try:
        limit = min(int(data.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50

    out = []
    for row in list(reversed(rows))[:limit]:
        sid = _stamp_id(row.get("ots_file"))
        entry = {"stamp_id": sid, "tip": row.get("tip"),
                 "stamped_at": _iso(row.get("ts")),
                 "ots_written": bool(row.get("ots")),
                 "note": row.get("note")}
        if sid:
            entry["proof_on_disk"] = os.path.exists(
                os.path.join(ANCHOR_DIR, "tip_%s.ots" % sid))
            entry["proof"] = "https://sebbi.pro/x/ots/proof?ts=%s" % sid
        out.append(entry)

    return {"ok": True, "count": len(out), "anchors": out,
            "note": "Newest first. ots_written false is a recorded failure, "
                    "kept rather than hidden - a gap in anchoring is exactly "
                    "what an auditor needs to see."}, 200


def _proof(data):
    stamp_id = str(data.get("ts") or data.get("stamp_id") or "").strip()
    tip = str(data.get("tip") or "").strip().lower()

    if not stamp_id and tip:
        for row in reversed(_read_index()):
            if str(row.get("tip", "")).lower() == tip and row.get("ots_file"):
                stamp_id = _stamp_id(row.get("ots_file"))
                break
        if not stamp_id:
            return {"ok": False, "error": "no_proof_for_tip", "tip": tip,
                    "detail": "No successful stamp recorded for that tip. "
                              "https://sebbi.pro/x/ots/list shows every "
                              "attempt."}, 404

    if not stamp_id:
        return {"ok": False, "error": "ts_or_tip_required",
                "detail": "?ts=<stamp_id> or ?tip=<64 hex>. Ids at "
                          "https://sebbi.pro/x/ots/list"}, 400
    if not stamp_id.isdigit():
        return {"ok": False, "error": "bad_stamp_id"}, 400

    raw, _path, err = _proof_bytes(stamp_id)
    if raw is None:
        return {"ok": False, "error": "proof_unavailable",
                "detail": err, "stamp_id": stamp_id}, 404

    d = _describe(raw)
    recorded_tip = _tip_for(stamp_id)
    return {
        "ok": True, "stamp_id": stamp_id, "stamped_at": _iso(stamp_id),
        "tip": recorded_tip, "digest_sha256": recorded_tip,
        "proof_bytes": len(raw),
        "proof_sha256": hashlib.sha256(raw).hexdigest(),
        "ots_base64": base64.b64encode(raw).decode("ascii"),
        "state": d["state"],
        "bitcoin_block_heights": d["bitcoin_block_heights"],
        "pending_calendars": d["pending_calendars"],
        "means": d.get("means"), "read_error": d.get("read_error"),
        "how_to_verify": {
            "1": "base64 -d the ots_base64 field into tip.ots",
            "2": "printf '%s' <tip> | xxd -r -p > tip.bin",
            "3": "ots verify -f tip.bin tip.ots",
            "4": "if pending: ots upgrade tip.ots",
            "needs": "pip install opentimestamps-client. Nothing of ours.",
        },
        "note": "These are the bytes as written at stamping time, plus any "
                "Bitcoin path added by upgrading. Nothing regenerated or "
                "normalised.",
    }, 200


def _upgrade(data):
    """Ask the calendars to complete pending proofs.

    Upgrading only ADDS the path from the digest to a Bitcoin block. It
    cannot change what was committed or when, which is why the standard
    client overwrites the file too.
    """
    try:
        from opentimestamps.calendar import RemoteCalendar
        from opentimestamps.core.serialize import (BytesDeserializationContext,
                                                   BytesSerializationContext)
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import PendingAttestation
    except Exception as exc:
        return {"ok": False, "error": "library_unavailable", "detail": str(exc),
                "fix": "add opentimestamps-client to requirements.txt"}, 501

    try:
        limit = min(int(data.get("limit", 25)), 200)
    except (TypeError, ValueError):
        limit = 25
    only = str(data.get("ts") or "").strip()

    auto = bool(data.get("auto"))

    if auto:
        # Half from the newest end (today's chain, what verifiers ask about),
        # half from the oldest (the backlog). Never the same proof twice.
        newest = _newest_pending(max(1, limit // 2))
        oldest = [c for c in _pending_candidates(limit) if c not in newest]
        candidates = newest + oldest[:max(0, limit - len(newest))]
    elif only:
        candidates = [only]
    else:
        # Manual run: newest first, which is what someone checking by hand
        # usually wants to see.
        candidates = [_stamp_id(r.get("ots_file"))
                      for r in reversed(_read_index()) if r.get("ots")]
        candidates = [c for c in candidates if c][:limit]

    results = []
    upgraded = newly_confirmed = already_confirmed = still_pending = errors = 0

    for sid in candidates:
        if not sid:
            continue
        with _file_lock:
            raw, path, err = _proof_bytes(sid)
            if raw is None:
                results.append({"stamp_id": sid, "ok": False, "detail": err})
                errors += 1
                continue

            before = _describe(raw)
            if before["state"] == "confirmed":
                _confirmed_seen.add(sid)
                already_confirmed += 1
                results.append({"stamp_id": sid, "ok": True,
                                "state": "confirmed",
                                "bitcoin_block_heights":
                                    before["bitcoin_block_heights"],
                                "action": "already complete, left alone"})
                continue

            try:
                detached = DetachedTimestampFile.deserialize(
                    BytesDeserializationContext(raw))
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "could not parse: %s" % exc})
                errors += 1
                continue

            merged = [0]

            def attempt(timestamp):
                for att in list(timestamp.attestations):
                    if not isinstance(att, PendingAttestation):
                        continue
                    uri = att.uri
                    if isinstance(uri, bytes):
                        uri = uri.decode("utf-8", "replace")
                    if uri not in CALENDARS:
                        continue
                    try:
                        completed = RemoteCalendar(uri).get_timestamp(
                            timestamp.msg)
                        timestamp.merge(completed)
                        merged[0] += 1
                    except Exception:
                        # Not ready yet is the normal case, not an error.
                        pass
                    # Free volunteer-run infrastructure. Do not hammer it.
                    time.sleep(CALENDAR_PAUSE)
                for _, sub in list(timestamp.ops.items()):
                    attempt(sub)

            try:
                attempt(detached.timestamp)
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "upgrade walk failed: %s" % exc})
                errors += 1
                continue

            if merged[0] == 0:
                still_pending += 1
                results.append({"stamp_id": sid, "ok": True,
                                "state": "pending",
                                "action": "no calendar had it ready yet",
                                "detail": "Normal. A Bitcoin confirmation "
                                          "takes hours. Run again later."})
                continue

            try:
                ctx = BytesSerializationContext()
                detached.serialize(ctx)
                new_bytes = ctx.getbytes()
                tmp = path + ".tmp"
                with open(tmp, "wb") as handle:
                    handle.write(new_bytes)
                os.replace(tmp, path)
            except Exception as exc:
                results.append({"stamp_id": sid, "ok": False,
                                "detail": "upgraded but could not write: %s"
                                          % exc})
                errors += 1
                continue

        after = _describe(new_bytes)
        upgraded += 1
        if after["state"] == "confirmed":
            _confirmed_seen.add(sid)
            newly_confirmed += 1
        results.append({"stamp_id": sid, "ok": True, "state": after["state"],
                        "bitcoin_block_heights": after["bitcoin_block_heights"],
                        "action": "upgraded, %d calendar response(s) merged"
                                  % merged[0],
                        "proof_bytes": len(new_bytes)})

    return {"ok": True, "examined": len(results), "upgraded": upgraded,
            "newly_confirmed": newly_confirmed,
            "already_confirmed": already_confirmed,
            "still_pending": still_pending,
            "errors": errors, "results": results,
            "note": "Upgrading only adds the path from digest to Bitcoin "
                    "block. It cannot alter what was committed or when. "
                    "Proofs not yet ready stay pending; nothing is lost by "
                    "trying early."}, 200


def _upgrade_loop():
    """Finish what anchor.py starts. Quiet, slow, and never fatal."""
    time.sleep(90)          # let the server come up
    while True:
        try:
            result, _status_code = _upgrade({"limit": AUTO_UPGRADE_BATCH,
                                             "auto": True})
            _auto["runs"] += 1
            _auto["last_run"] = _iso(time.time())
            _auto["last_result"] = {
                "examined": result.get("examined"),
                "upgraded": result.get("upgraded"),
                "newly_confirmed": result.get("newly_confirmed"),
                "still_pending": result.get("still_pending"),
                "errors": result.get("errors"),
            }
            _auto["upgraded_total"] += int(result.get("upgraded") or 0)
            _auto["confirmed_total"] += int(result.get("newly_confirmed") or 0)
            if result.get("upgraded"):
                print("OTS: upgraded %s proof(s), %s newly confirmed"
                      % (result.get("upgraded"),
                         result.get("newly_confirmed")), flush=True)
        except Exception as exc:
            print("OTS upgrade loop error: %s" % exc, flush=True)
        time.sleep(AUTO_UPGRADE_INTERVAL)


def _start_auto():
    if _auto["started"] or not AUTO_UPGRADE_ENABLED:
        return
    _auto["started"] = True
    threading.Thread(target=_upgrade_loop, name="ots-upgrade",
                     daemon=True).start()
    print("OTS: auto-upgrade every %ds, %d per batch, skipping proofs under "
          "%dh old and proofs already confirmed"
          % (AUTO_UPGRADE_INTERVAL, AUTO_UPGRADE_BATCH,
             MIN_AGE_SECONDS // 3600), flush=True)


def _spec():
    return {
        "module": "ots", "version": VERSION,
        "what": "Serves the OpenTimestamps proofs for the chain tip, and "
                "upgrades pending ones to confirmed.",
        "why": "anchor.py has stamped the tip hourly since July and nothing "
               "served the proofs, so external anchoring was a claim rather "
               "than something a third party could check.",
        "pending_vs_confirmed": {
            "pending": "Written when a calendar accepts the digest. A promise "
                       "to commit it to Bitcoin. NOT evidence of anything on "
                       "chain yet.",
            "confirmed": "Carries the full path from digest to a Bitcoin "
                         "block header. Verifiable by anyone against the "
                         "blockchain, with nothing from us.",
            "the_gap": "A proof does not become confirmed on its own. It must "
                       "be upgraded - fetched again from the calendar after "
                       "its transaction lands. This module does that on a "
                       "timer, newest and oldest together, skipping ones "
                       "already done.",
        },
        "routes": {
            "status": "https://sebbi.pro/x/ots/status",
            "list": "https://sebbi.pro/x/ots/list",
            "proof": "https://sebbi.pro/x/ots/proof?ts=<stamp_id>",
            "latest_confirmed": "https://sebbi.pro/x/ots/latest_confirmed",
            "spec": "https://sebbi.pro/x/ots/spec",
            "upgrade": "POST, keyed. asks the calendars to complete pending "
                       "proofs.",
        },
        "verifying_without_us": [
            "base64 -d the ots_base64 field into tip.ots",
            "printf '%s' <tip> | xxd -r -p > tip.bin",
            "ots verify -f tip.bin tip.ots",
            "pip install opentimestamps-client - no code of ours involved",
        ],
        "what_this_does_not_prove": [
            "That the records under the tip are true. It fixes when a hash "
            "existed, nothing else.",
            "Anything about blocks sealed since the last anchor. Anchoring is "
            "hourly, so the most recent hour rests on peer witnessing.",
            "That a pending proof will confirm. Calendars are free public "
            "infrastructure and can fail.",
        ],
        "storage_warning": "Proofs live at %s. On Railway that is only "
                           "durable with a persistent volume mounted there. "
                           "https://sebbi.pro/x/ots/status reports what is "
                           "present." % ANCHOR_DIR,
    }


try:
    _start_auto()
except Exception as exc:
    print("OTS: could not start auto-upgrade: %s" % exc, flush=True)


def handle(method, action, data, api_key, ctx):
    data = data or {}
    if action == "spec":
        return _spec(), 200
    if action in ("status", ""):
        return _status()
    if action == "list":
        return _list(data)
    if action == "proof":
        return _proof(data)
    if action == "latest_confirmed":
        return _latest_confirmed(ctx)
    if action == "upgrade":
        if not api_key:
            return {"ok": False, "error": "api_key_required"}, 401
        return _upgrade(data)
    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


## `modules/oversight.py`

249 lines, 11339 bytes

```python
"""
Human oversight notary - /x/oversight/<action>

THE PROBLEM
-----------
Nobody can prove a person thought about a decision. That is an internal state
and no amount of logging reaches it. Any vendor claiming to prove genuine
human oversight is overselling.

But rubber stamping is not an internal state. It is a pattern, and patterns
leave marks - if you record the right things, in the right order, at the time.

WHAT THIS DOES
--------------
Three things, none of which claim to read minds.

1. ORDER. The reviewer's own call is sealed BEFORE the machine's verdict is
   revealed to them. Two blocks, in that order, in a chain that cannot be
   reordered afterwards. So a reviewer cannot have simply agreed with an
   answer they had already seen - the chain shows they committed while it was
   still hidden.

2. ATTENTION. The gap between opening the case and committing is recorded.
   A 0.8 second approval sits in the record permanently, next to a two minute
   one. Not proof of thought - but a 400-case history of sub-second calls is
   not something anyone can explain away.

3. INDEPENDENCE. Agreement rate over time. A reviewer who has never once
   diverged from the machine is visible in the data. One who diverges
   sometimes is demonstrably exercising judgement.

WHAT IT DOES NOT DO
-------------------
- It cannot prove the reviewer read the material. They can leave a screen open.
- Dwell time is measurable but gameable by anyone deliberately gaming it.
- It does not stop a reviewer being wrong. It records that they decided.
- If the integrating system shows its user the machine verdict before calling
  /open, this proves nothing. The ordering guarantee is only as good as the
  integration honouring it. That is a documented limit, not a hidden one.

WHAT IT IS FOR
--------------
Turning "we have human oversight" from an assertion into a dataset that an
auditor can test - and that a rubber stamper cannot hide inside.

    POST /x/oversight/open      case_ref, material, machine_verdict, reviewer
    POST /x/oversight/commit    case_id, reviewer_verdict, reasoning
    GET  /x/oversight/case?id=OVS-XXXXXXXX
    GET  /x/oversight/reviewer?id=<reviewer id>
    GET  /x/oversight/list
"""

import hashlib, json, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"
VERDICTS = {"allow", "block", "challenge", "escalate"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS oversight_cases(case_id TEXT PRIMARY KEY,api_key TEXT,case_ref TEXT,reviewer TEXT,material_hash TEXT,machine_verdict TEXT,opened REAL,committed REAL,reviewer_verdict TEXT,agreed INTEGER,dwell REAL,status TEXT DEFAULT 'open')")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_ovs_key ON oversight_cases(api_key)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_ovs_rev ON oversight_cases(api_key,reviewer)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _hash(x):
    if not isinstance(x, str):
        x = json.dumps(x, sort_keys=True)
    return hashlib.sha256(x.encode()).hexdigest()


def _seal_event(ctx, api_key, cid, action, detail):
    ts = time.time()
    ev = {"user_id": "ovs:" + cid, "action": "oversight_" + action, "amount": 0,
          "country": "UK", "device_id": "oversight", "anomaly": 0, "device_risk": 0}
    res = {"decision": "OVERSIGHT_SEALED", "score": 0, "oversight_action": action,
           "oversight_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _open(ctx, api_key, data):
    ref = str(data.get("case_ref", "")).strip()
    if not ref:
        return {"error": "case_ref_required"}, 400
    reviewer = str(data.get("reviewer", "")).strip()
    if not reviewer:
        return {"error": "reviewer_required",
                "message": "Oversight without a named reviewer is not oversight."}, 400
    material = data.get("material")
    if material is None:
        return {"error": "material_required",
                "message": "Send exactly what the reviewer will see. Only its hash is stored."}, 400
    mv = str(data.get("machine_verdict", "")).strip().lower()
    if mv and mv not in VERDICTS:
        return {"error": "invalid_machine_verdict", "allowed": sorted(VERDICTS)}, 400

    cid = "OVS-" + secrets.token_hex(4).upper()
    mh = _hash(material)
    detail = ("ref=" + ref[:80] + ";reviewer=" + reviewer[:60] +
              ";material_sha256=" + mh + ";machine_verdict_sealed=" + (mv or "none"))
    h, idx, seq, ts = _seal_event(ctx, api_key, cid, "opened", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO oversight_cases(case_id,api_key,case_ref,reviewer,material_hash,machine_verdict,opened,committed,reviewer_verdict,agreed,dwell,status) VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL,NULL,'open')",
                            (cid, api_key, ref, reviewer, mh, mv or None, ts))
        ctx["conn"].commit()

    return {"case_id": cid, "opened": _iso(ts), "material_sha256": mh,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "machine_verdict": "withheld until commit",
            "message": "Clock running. Show the reviewer the material, not the verdict."}, 200


def _commit(ctx, api_key, data):
    cid = str(data.get("case_id", "")).strip()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT reviewer,material_hash,machine_verdict,opened,status FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4] != "open":
        return {"error": "already_committed",
                "message": "A reviewer commits once. That is the point."}, 400

    rv = str(data.get("reviewer_verdict", "")).strip().lower()
    if rv not in VERDICTS:
        return {"error": "invalid_reviewer_verdict", "allowed": sorted(VERDICTS)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required",
                "message": "Sealed at commit, before the machine verdict is revealed. Blank is not permitted."}, 400

    ts = time.time()
    dwell = round(ts - row[3], 3)
    agreed = None if not row[2] else (1 if rv == row[2] else 0)
    detail = ("reviewer_verdict=" + rv + ";dwell_seconds=" + str(dwell) +
              ";reasoning=" + reasoning[:600])
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "committed", detail)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE oversight_cases SET committed=?,reviewer_verdict=?,agreed=?,dwell=?,status='committed' WHERE case_id=? AND api_key=?",
                            (ts, rv, agreed, dwell, cid, api_key))
        ctx["conn"].commit()

    out = {"case_id": cid, "reviewer_verdict": rv, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "machine_verdict": row[2],
           "note": "Your call was sealed before this line was returned. The chain shows the order."}
    if agreed is not None:
        out["agreed"] = bool(agreed)
    if dwell < 2:
        out["flag"] = "committed in under 2 seconds - recorded permanently"
    return out, 200


def _case(ctx, api_key, cid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT case_ref,reviewer,material_hash,machine_verdict,opened,committed,reviewer_verdict,agreed,dwell,status FROM oversight_cases WHERE case_id=? AND api_key=?", (cid, api_key)).fetchone()
        if not row:
            return {"error": "unknown_case_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("ovs:" + cid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("oversight_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"case_id": cid, "case_ref": row[0], "reviewer": row[1],
            "material_sha256": row[2], "machine_verdict": row[3],
            "opened": _iso(row[4]), "committed": _iso(row[5]),
            "reviewer_verdict": row[6],
            "agreed": (None if row[7] is None else bool(row[7])),
            "dwell_seconds": row[8], "status": row[9], "events": events,
            "ordering_proof": "The opened block precedes the committed block in the chain. Neither can be reordered or altered without breaking every block after it."}, 200


def _reviewer(ctx, api_key, rid):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT dwell,agreed FROM oversight_cases WHERE api_key=? AND reviewer=? AND status='committed'", (api_key, rid)).fetchall()
    if not rows:
        return {"reviewer": rid, "cases": 0,
                "note": "No committed cases on record for this reviewer."}, 200
    dwells = sorted(r[0] for r in rows if r[0] is not None)
    scored = [r[1] for r in rows if r[1] is not None]
    n = len(dwells)
    median = dwells[n // 2] if n else None
    under2 = len([d for d in dwells if d < 2])
    out = {"reviewer": rid, "cases": len(rows),
           "median_dwell_seconds": median,
           "fastest_seconds": (dwells[0] if dwells else None),
           "under_2_seconds": under2,
           "under_2_seconds_pct": (round(100 * under2 / n, 1) if n else None)}
    if scored:
        agree = sum(scored)
        out["agreement_rate_pct"] = round(100 * agree / len(scored), 1)
        out["diverged"] = len(scored) - agree
        if len(scored) >= 20 and agree == len(scored):
            out["pattern"] = "never diverged from the machine across " + str(len(scored)) + " cases"
    return out, 200


def _list(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT case_id,case_ref,reviewer,opened,status,reviewer_verdict,dwell,agreed FROM oversight_cases WHERE api_key=? ORDER BY opened DESC LIMIT 200", (api_key,)).fetchall()
    return {"count": len(rows),
            "cases": [{"case_id": r[0], "case_ref": r[1], "reviewer": r[2],
                       "opened": _iso(r[3]), "status": r[4],
                       "reviewer_verdict": r[5], "dwell_seconds": r[6],
                       "agreed": (None if r[7] is None else bool(r[7]))} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "open":
            return _open(ctx, api_key, data)
        if action == "commit":
            return _commit(ctx, api_key, data)
    else:
        if action == "list":
            return _list(ctx, api_key)
        if action == "case":
            cid = str(data.get("id", "")).strip()
            if not cid:
                return {"error": "id_required"}, 400
            return _case(ctx, api_key, cid)
        if action == "reviewer":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _reviewer(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```
