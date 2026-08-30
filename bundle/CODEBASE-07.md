# Codebase — part 7 of 30

Contains:
- `modules/mutual.py`
- `modules/network.py`
- `modules/ots.py`
- `modules/oversight.py`
- `modules/pack.py`


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


## `modules/ots.py`

604 lines, 23912 bytes

```python
"""
modules/ots.py  v1.0  -  serve the OpenTimestamps proofs, and upgrade them

anchor.py stamps the chain tip hourly and writes the .ots proof to the
anchor volume. Nothing served those files, so "anchored to Bitcoin" was a
claim a third party had to take on trust.

PENDING IS NOT CONFIRMED. A proof written at stamping time holds a PENDING
attestation - a calendar's promise to commit the digest to Bitcoin. It is
not evidence of anything on chain until it is UPGRADED, after the
calendar's transaction lands. anchor.py never upgraded, so every proof
written before this module is pending. Said plainly because an auditor's
own verifier says it first.

Routes: spec, status, list, proof public. upgrade keyed.
Proofs live at ANCHOR_DIR (default /data/anchors) - only durable on Railway
if a volume is mounted there. /x/ots/status reports what is really present.
"""

import base64
import hashlib
import json
import os
import threading
import time

VERSION = "1.0"

PUBLIC = {("GET", "spec"), ("GET", "status"), ("GET", "list"),
          ("GET", "proof")}

ANCHOR_DIR = os.environ.get("ANCHOR_DIR", "/data/anchors")
MAX_PROOF_BYTES = 262144

CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://alice.btc.calendar.opentimestamps.org",
]

# ---- automatic upgrading
#
# anchor.py stamps and walks away, which is how 767 proofs ended up pending.
# This finishes the job on a timer so nobody has to remember to.
#
# The calendars are free public infrastructure run by volunteers. Firing 767
# requests at them in one go would be rude and would probably get us rate
# limited, so this works in small batches, oldest first, and skips anything
# too young to have confirmed yet. A backlog clears over days rather than
# minutes, which is fine - nothing is lost by a proof staying pending a
# little longer, and the stamp time is already fixed regardless.
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


def _pending_candidates():
    """Stamps old enough to be worth asking about, oldest first.

    Oldest first on purpose: the oldest pending proofs are the ones most
    likely to have confirmed, so a backlog clears from the far end rather
    than the recent end.
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
        out.append(sid)
    return out


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
        "confirmed_since_start": _auto["confirmed_total"],
        "eligible_now": len(_pending_candidates()),
        "note": ("Runs oldest first in small batches. The calendars are free "
                 "infrastructure run by volunteers, so a backlog clears over "
                 "days rather than minutes. Nothing is lost by a proof "
                 "staying pending longer - the stamp time is already fixed."),
    }

    out["honest_note"] = (
        "A proof written at stamping time is PENDING - a promise to commit "
        "the digest to Bitcoin, not evidence that it has been. It becomes "
        "confirmed only after being upgraded. anchor.py never upgraded; "
        "POST /x/ots/upgrade does. Until then, pending is what these are.")
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
            entry["proof"] = "/x/ots/proof?ts=%s" % sid
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
                              "/x/ots/list shows every attempt."}, 404

    if not stamp_id:
        return {"ok": False, "error": "ts_or_tip_required",
                "detail": "?ts=<stamp_id> or ?tip=<64 hex>. Ids at "
                          "/x/ots/list."}, 400
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
        "note": "These are the bytes as written at stamping time. Nothing "
                "regenerated or normalised.",
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
        # Oldest first, and only ones old enough to have confirmed.
        candidates = _pending_candidates()[:limit]
    elif only:
        candidates = [only]
    else:
        # Manual run: newest first, which is what someone checking by hand
        # usually wants to see.
        candidates = [_stamp_id(r.get("ots_file"))
                      for r in reversed(_read_index()) if r.get("ots")]
        candidates = [c for c in candidates if c][:limit]

    results = []
    upgraded = confirmed = still_pending = errors = 0

    for sid in candidates:
        if not sid:
            continue
        raw, path, err = _proof_bytes(sid)
        if raw is None:
            results.append({"stamp_id": sid, "ok": False, "detail": err})
            errors += 1
            continue

        before = _describe(raw)
        if before["state"] == "confirmed":
            confirmed += 1
            results.append({"stamp_id": sid, "ok": True, "state": "confirmed",
                            "bitcoin_block_heights": before["bitcoin_block_heights"],
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
                    completed = RemoteCalendar(uri).get_timestamp(timestamp.msg)
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
            results.append({"stamp_id": sid, "ok": True, "state": "pending",
                            "action": "no calendar had it ready yet",
                            "detail": "Normal. A Bitcoin confirmation takes "
                                      "hours. Run again later."})
            continue

        try:
            ctx = BytesSerializationContext()
            detached.serialize(ctx)
            new_bytes = ctx.getbytes()
            with open(path, "wb") as handle:
                handle.write(new_bytes)
        except Exception as exc:
            results.append({"stamp_id": sid, "ok": False,
                            "detail": "upgraded but could not write: %s" % exc})
            errors += 1
            continue

        after = _describe(new_bytes)
        upgraded += 1
        if after["state"] == "confirmed":
            confirmed += 1
        results.append({"stamp_id": sid, "ok": True, "state": after["state"],
                        "bitcoin_block_heights": after["bitcoin_block_heights"],
                        "action": "upgraded, %d calendar response(s) merged"
                                  % merged[0],
                        "proof_bytes": len(new_bytes)})

    return {"ok": True, "examined": len(results), "upgraded": upgraded,
            "now_confirmed": confirmed, "still_pending": still_pending,
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
                "now_confirmed": result.get("now_confirmed"),
                "still_pending": result.get("still_pending"),
                "errors": result.get("errors"),
            }
            _auto["upgraded_total"] += int(result.get("upgraded") or 0)
            _auto["confirmed_total"] += int(result.get("now_confirmed") or 0)
            if result.get("upgraded"):
                print("OTS: upgraded %s proof(s), %s now confirmed"
                      % (result.get("upgraded"), result.get("now_confirmed")),
                      flush=True)
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
          "%dh old" % (AUTO_UPGRADE_INTERVAL, AUTO_UPGRADE_BATCH,
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
                       "its transaction lands. anchor.py never did that, so "
                       "every proof written before this module is pending.",
        },
        "routes": {
            "GET spec": "public. this document.",
            "GET status": "public. anchor state, storage health, latest proof.",
            "GET list": "public. every attempt, newest first, failures kept.",
            "GET proof": "public. ?ts= or ?tip= -> the .ots, base64.",
            "POST upgrade": "keyed. asks the calendars to complete pending proofs.",
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
                           "/x/ots/status reports what is present."
                           % ANCHOR_DIR,
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


## `modules/pack.py`

501 lines, 20695 bytes

```python
"""
Evidence pack - /x/pack/<action>

WHAT THIS IS
------------
The sellable artifact. Everything else in this platform produces evidence;
this produces the document someone hands an auditor.

For a chosen period it does not summarise the chain, it RE-VERIFIES it:
every block in the range is rehashed from its stored contents using the
same function that sealed it, and compared to the hash recorded at the
time. Then the links between blocks are walked, and for a single key the
gapless receipt sequence is checked end to end.

A summary is a claim. A re-verification is a check anyone can repeat.

WHAT IT DOES NOT PROVE
----------------------
- That any decision recorded here was correct. Wrong answers seal just as
  cleanly as right ones.
- That an external peer's own chain is honest. That is checked at the
  peer's host, not here.
- Anything about periods outside the range requested.

    GET  /x/pack/spec                        public - what this does
    GET  /x/pack/preview?period=2026-Q2      keyed  - the pack as JSON
    GET  /x/pack/render?period=2026-Q2       keyed  - the pack as one page
    GET  /x/pack/history                     keyed  - packs issued
    POST /x/pack/issue                       keyed  - seal it into the chain

period accepts YYYY, YYYY-MM, YYYY-Qn. Add scope=me to limit the pack to
your own key; omit scope for a deployment-wide pack.
"""

import calendar
import datetime
import hashlib
import json
import time

VERSION = "1.0"

# (METHOD, action). Only the spec is open - a pack is customer evidence.
PUBLIC = {("GET", "spec")}

MAX_ROWS = 200000

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS pack_issued("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
            "period TEXT,scope TEXT,digest TEXT,issued REAL,"
            "entries INTEGER,verified INTEGER,mismatches INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_pack_key "
            "ON pack_issued(api_key)")
        ctx["conn"].commit()
    _ready = True


def _sha(p):
    """Identical to the engine's own sha(). Written out here rather than
    imported so this module depends on no other module's internals."""
    return hashlib.sha256(
        json.dumps(p, sort_keys=True).encode()).hexdigest()


def _iso(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(ts):
    if ts is None:
        return None
    return datetime.datetime.utcfromtimestamp(
        float(ts)).strftime("%Y-%m-%d")


def _epoch(y, m, d):
    return float(calendar.timegm((y, m, d, 0, 0, 0, 0, 0, 0)))


def _bounds(period):
    """YYYY | YYYY-MM | YYYY-Qn -> (start, end, label)."""
    p = str(period or "").strip().upper()
    try:
        if len(p) == 4:
            y = int(p)
            return _epoch(y, 1, 1), _epoch(y + 1, 1, 1), p
        if len(p) == 7 and p[4] == "-" and p[5] == "Q":
            y, q = int(p[:4]), int(p[6])
            if q < 1 or q > 4:
                return None
            m = (q - 1) * 3 + 1
            em, ey = m + 3, y
            if em > 12:
                em, ey = em - 12, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
        if len(p) == 7 and p[4] == "-":
            y, m = int(p[:4]), int(p[5:])
            em, ey = m + 1, y
            if em > 12:
                em, ey = 1, y + 1
            return _epoch(y, m, 1), _epoch(ey, em, 1), p
    except (ValueError, IndexError):
        return None
    return None


# ----------------------------------------------------------------------
# assembly - the actual re-verification
# ----------------------------------------------------------------------

def _assemble(ctx, start, end, label, scope):
    c = ctx["conn"]
    cols = ("id,ts,event_json,result_json,prev_hash,audit_hash,"
            "api_key,key_seq")

    with ctx["lock"]:
        if scope:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "AND api_key=? ORDER BY id ASC LIMIT ?",
                (start, end, scope, MAX_ROWS)).fetchall()
            began = c.execute(
                "SELECT MIN(ts) FROM audit_log WHERE api_key=?",
                (scope,)).fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=?",
                (scope,)).fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen WHERE api_key=? "
                "AND first_seen>=? AND first_seen<?",
                (scope, start, end)).fetchone()
        else:
            rows = c.execute(
                "SELECT " + cols + " FROM audit_log WHERE ts>=? AND ts<? "
                "ORDER BY id ASC LIMIT ?",
                (start, end, MAX_ROWS)).fetchall()
            began = c.execute("SELECT MIN(ts) FROM audit_log").fetchone()
            dev_all = c.execute(
                "SELECT COUNT(*) FROM device_seen").fetchone()
            dev_new = c.execute(
                "SELECT COUNT(*) FROM device_seen "
                "WHERE first_seen>=? AND first_seen<?",
                (start, end)).fetchone()
        chain_total = c.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]

    verdicts = {}
    actions = {}
    seqs = []
    verified = 0
    mismatched = []
    link_breaks = []
    expect_prev = None
    per_day = {}

    for rid, ts, ev_j, res_j, prev, ah, akey, kseq in rows:
        try:
            ev = json.loads(ev_j)
            res = json.loads(res_j)
        except Exception:
            mismatched.append(rid)
            expect_prev = ah
            continue

        if _sha({"prev_hash": prev, "ts": ts,
                 "event": ev, "result": res}) == ah:
            verified += 1
        else:
            mismatched.append(rid)

        if expect_prev is not None and prev != expect_prev:
            link_breaks.append(rid)
        expect_prev = ah

        d = str(res.get("decision", "UNRECORDED"))
        verdicts[d] = verdicts.get(d, 0) + 1
        a = str(ev.get("action", "unrecorded"))
        actions[a] = actions.get(a, 0) + 1
        if kseq is not None:
            try:
                seqs.append(int(kseq))
            except (TypeError, ValueError):
                pass
        k = _day(ts)
        per_day[k] = per_day.get(k, 0) + 1

    # does the first block in the period chain to the one before it
    entry_link = "no_entries_in_period"
    if rows:
        with ctx["lock"]:
            before = c.execute(
                "SELECT audit_hash FROM audit_log WHERE id<? "
                "ORDER BY id DESC LIMIT 1", (rows[0][0],)).fetchone()
        if before is None:
            entry_link = ("intact_from_genesis"
                          if rows[0][4] == "GENESIS" else "broken")
        else:
            entry_link = "intact" if rows[0][4] == before[0] else "broken"

    seq = {"applicable": bool(scope and seqs)}
    if seq["applicable"]:
        lo, hi = min(seqs), max(seqs)
        have = set(seqs)
        missing = [n for n in range(lo, hi + 1) if n not in have]
        seq.update({"first": lo, "last": hi, "received": len(seqs),
                    "expected": hi - lo + 1,
                    "missing": missing[:200],
                    "gapless": not missing,
                    "note": "Receipt numbers are issued with no gaps by "
                            "construction. A missing number is a record "
                            "that left this chain."})

    clean = (not mismatched and not link_breaks
             and entry_link in ("intact", "intact_from_genesis"))

    p = {
        "pack_version": VERSION,
        "period": label,
        "period_start": _iso(start),
        "period_end": _iso(end),
        "generated_at": _iso(time.time()),
        "scope": ("key " + str(scope)[:12] + "\u2026") if scope
                 else "deployment-wide",
        "unbroken_since": _day(began[0] if began else None),
        "entries_in_period": len(rows),
        "chain_total_entries": chain_total,
        "first_block": rows[0][0] if rows else None,
        "first_hash": rows[0][5] if rows else None,
        "last_block": rows[-1][0] if rows else None,
        "last_hash": rows[-1][5] if rows else None,
        "integrity": {
            "clean": clean,
            "blocks_recomputed": len(rows),
            "hashes_verified": verified,
            "hash_mismatches": mismatched[:50],
            "link_breaks": link_breaks[:50],
            "link_into_period": entry_link,
            "method": "SHA-256 over {prev_hash, ts, event, result}, "
                      "recomputed from the stored row and compared to "
                      "the hash sealed at the time",
        },
        "receipt_sequence": seq,
        "verdicts": verdicts,
        "actions": dict(sorted(actions.items(), key=lambda x: -x[1])[:20]),
        "devices": {"total_ever": dev_all[0] if dev_all else 0,
                    "first_seen_in_period": dev_new[0] if dev_new else 0},
        "busiest_days": [{"day": d, "entries": n} for d, n in
                         sorted(per_day.items(), key=lambda x: -x[1])[:5]],
        "check_this_yourself": {
            "offline": "aileash_verify.py - stdlib only, no network",
            "still_on_this_chain": "/x/consistency/ancestor?tip=<last_hash>",
            "append_only": "/x/consistency/proof?first=&second=",
            "record_included": "/x/complete/prove",
            "who_witnessed_us": "/x/witness/peers",
        },
        "this_does_not_prove": [
            "That any decision recorded here was correct.",
            "That an external peer's own chain is honest - that is "
            "checked at the peer's host, not here.",
            "Anything about periods outside the dates above.",
        ],
    }
    p["pack_digest"] = hashlib.sha256(
        b"AILEASH-PACK-v1\x00" + json.dumps(
            p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return p


# ----------------------------------------------------------------------
# one page, self contained
# ----------------------------------------------------------------------

def _html(p):
    ig = p["integrity"]
    sq = p["receipt_sequence"]
    good = "#7fe3b0"
    bad = "#ff8a80"

    def card(inner):
        return ("<div style='background:#10182e;border:1px solid #223055;"
                "border-radius:12px;padding:16px;margin-bottom:14px'>"
                + inner + "</div>")

    def row(k, v):
        return ("<tr><td style='padding:7px 0;border-bottom:1px solid "
                "#1d2a4a'>" + str(k) + "</td><td style='padding:7px 0;"
                "border-bottom:1px solid #1d2a4a;text-align:right;"
                "color:#c9a84c;font-weight:600'>" + str(v) + "</td></tr>")

    def mono(v):
        return ("<code style='font:12px ui-monospace,monospace;"
                "color:#9fb3d9;word-break:break-all'>" + str(v)
                + "</code>")

    integ = ("<div style='font-size:26px;font-weight:600;color:"
             + (good if ig["clean"] else bad) + "'>"
             + str(ig["hashes_verified"]) + " of "
             + str(ig["blocks_recomputed"]) + " blocks re-verified</div>"
             "<div style='color:#93a0bd;font-size:13px;margin-top:6px'>"
             + ig["method"] + "</div>")
    if not ig["clean"]:
        integ += ("<div style='color:" + bad + ";font-size:13px;"
                  "margin-top:8px'>mismatched blocks "
                  + str(ig["hash_mismatches"]) + " &middot; link breaks "
                  + str(ig["link_breaks"]) + " &middot; entry link "
                  + ig["link_into_period"] + "</div>")

    if sq.get("applicable"):
        seqbox = ("<div style='font-size:20px;font-weight:600;color:"
                  + (good if sq["gapless"] else bad) + "'>"
                  + ("Receipt sequence complete" if sq["gapless"]
                     else "GAPS IN RECEIPT SEQUENCE") + "</div>"
                  "<div style='color:#93a0bd;font-size:13px'>"
                  + str(sq["received"]) + " of " + str(sq["expected"])
                  + " received, numbers " + str(sq["first"]) + " to "
                  + str(sq["last"]) + "</div>")
        if not sq["gapless"]:
            seqbox += ("<div style='color:" + bad + ";font:12px "
                       "ui-monospace,monospace;margin-top:6px'>missing "
                       + str(sq["missing"]) + "</div>")
    else:
        seqbox = ("<div style='color:#93a0bd;font-size:13px'>Receipt "
                  "sequence applies to a single key. This pack is "
                  "deployment-wide.</div>")

    checks = "".join("<li><b>" + k.replace("_", " ") + "</b> " + mono(v)
                     + "</li>" for k, v in
                     p["check_this_yourself"].items())
    nots = "".join("<li>" + x + "</li>" for x in p["this_does_not_prove"])

    return (
        "<!doctype html><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Evidence Pack " + p["period"] + " - AILeash</title>"
        "<body style='background:#0a0f1e;color:#e8ecf5;margin:0;"
        "padding:22px;font:15px/1.55 -apple-system,system-ui,sans-serif'>"
        "<div style='max-width:760px;margin:0 auto'>"
        "<h1 style='font-size:21px;margin:0 0 4px;color:#c9a84c'>"
        "Evidence Pack &mdash; " + p["period"] + "</h1>"
        "<div style='color:#93a0bd;font-size:13px;margin-bottom:20px'>"
        + p["scope"] + " &middot; " + str(p["period_start"]) + " to "
        + str(p["period_end"]) + " &middot; generated "
        + str(p["generated_at"]) + "</div>"
        + card("<div style='color:#93a0bd;font-size:13px'>Unbroken since"
               "</div><div style='font-size:26px;color:" + good
               + ";font-weight:600'>" + str(p["unbroken_since"])
               + "</div>")
        + card(integ)
        + card(seqbox)
        + card("<table style='width:100%;border-collapse:collapse;"
               "font-size:14px'>"
               + row("Entries in period", p["entries_in_period"])
               + row("Chain total entries", p["chain_total_entries"])
               + row("Devices, total ever", p["devices"]["total_ever"])
               + row("Devices first seen this period",
                     p["devices"]["first_seen_in_period"])
               + "".join(row(k, v) for k, v in sorted(
                   p["verdicts"].items()))
               + "".join(row(k, v) for k, v in p["actions"].items())
               + "</table>")
        + card("<div style='color:#93a0bd;font-size:13px'>First block</div>"
               + mono("#" + str(p["first_block"]) + " "
                      + str(p["first_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Last block</div>"
               + mono("#" + str(p["last_block"]) + " "
                      + str(p["last_hash"]))
               + "<div style='color:#93a0bd;font-size:13px;margin-top:10px'>"
                 "Pack digest</div>" + mono(p["pack_digest"]))
        + card("<div style='color:#93a0bd;font-size:13px'>Check every "
               "figure above yourself:</div><ul style='margin:6px 0 0 18px;"
               "padding:0;font-size:13px'>" + checks + "</ul>"
               "<div style='color:#93a0bd;font-size:13px;margin-top:14px'>"
               "What this pack does not prove:</div>"
               "<ul style='margin:6px 0 0 18px;padding:0;color:#93a0bd;"
               "font-size:13px'>" + nots + "</ul>")
        + "<div style='color:#6d7b99;font-size:12px;margin-top:18px'>"
          "AILeash &middot; sebbi.pro</div></div>")


# ----------------------------------------------------------------------

def _resolve(data, api_key):
    b = _bounds(data.get("period"))
    if not b:
        return None, ({"error": "period_required",
                       "accepts": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                       "example": "/x/pack/preview?period=2026-Q2"}, 400)
    start, end, label = b
    if end > time.time():
        return None, ({"error": "period_not_closed", "period": label,
                       "message": "A pack can only cover a period that "
                                  "has finished."}, 409)
    scope = data.get("scope")
    if scope == "me":
        scope = api_key
    return (start, end, label, scope or None), None


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return {"module": "pack", "version": VERSION,
                "purpose": "Re-verifies every block in a period against "
                           "the hash sealed at the time, and checks the "
                           "gapless receipt sequence for a single key.",
                "periods": ["YYYY", "YYYY-MM", "YYYY-Qn"],
                "routes": {"GET /x/pack/spec": "public",
                           "GET /x/pack/preview?period=": "keyed, json",
                           "GET /x/pack/render?period=": "keyed, one page",
                           "GET /x/pack/history": "keyed",
                           "POST /x/pack/issue": "keyed, seals the pack"},
                "scope": "add scope=me for your key only; omit for "
                         "deployment-wide",
                "does_not_prove": [
                    "That any decision recorded here was correct.",
                    "That an external peer's chain is honest.",
                ]}, 200

    if not api_key:
        return {"error": "invalid_api_key"}, 401

    _setup(ctx)

    if method == "GET":
        if action == "history":
            with ctx["lock"]:
                rows = ctx["conn"].execute(
                    "SELECT period,scope,digest,issued,entries,verified,"
                    "mismatches,audit_hash,block_index FROM pack_issued "
                    "WHERE api_key=? ORDER BY id DESC LIMIT 200",
                    (api_key,)).fetchall()
            return {"count": len(rows), "packs": [
                {"period": r[0], "scope": r[1], "digest": r[2],
                 "issued": _iso(r[3]), "entries": r[4],
                 "hashes_verified": r[5], "mismatches": r[6],
                 "sealed_in_chain": r[7], "block_index": r[8]}
                for r in rows]}, 200

        if action in ("preview", "render"):
            got, err = _resolve(data, api_key)
            if err:
                return err
            start, end, label, scope = got
            p = _assemble(ctx, start, end, label, scope)
            if action == "preview":
                return p, 200
            return {"period": label, "content_type": "text/html",
                    "html": _html(p)}, 200

    if method == "POST" and action == "issue":
        got, err = _resolve(data, api_key)
        if err:
            return err
        start, end, label, scope = got
        p = _assemble(ctx, start, end, label, scope)
        ig = p["integrity"]
        ts = time.time()
        ev = {"user_id": "pack:" + label, "action": "evidence_pack_issued",
              "amount": 0, "country": "UK", "device_id": "pack",
              "anomaly": 0, "device_risk": 0}
        res = {"decision": "PACK_ISSUED", "score": 0, "pack_version": VERSION,
               "timestamp": ts, "period": label, "scope": p["scope"],
               "entries": p["entries_in_period"],
               "blocks_recomputed": ig["blocks_recomputed"],
               "hashes_verified": ig["hashes_verified"],
               "clean": ig["clean"], "pack_digest": p["pack_digest"],
               "note": "evidence pack issued; the pack's own digest is "
                       "now sealed, so the document cannot be edited "
                       "after the fact"}
        h, idx, seq = ctx["seal"](ev, res, ts, api_key)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO pack_issued(api_key,period,scope,digest,"
                "issued,entries,verified,mismatches,audit_hash,"
                "block_index) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (api_key, label, p["scope"], p["pack_digest"], ts,
                 p["entries_in_period"], ig["hashes_verified"],
                 len(ig["hash_mismatches"]), h, idx))
            ctx["conn"].commit()
        p["sealed"] = {"audit_hash": h, "block_index": idx,
                       "receipt_seq": seq}
        return p, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "preview", "render", "history"],
            "POST": ["issue"]}, 404

```
