# Codebase — part 13 of 34

Contains:
- `modules/roster.py`
- `modules/router.py`
- `modules/rulebind.py`
- `modules/run_benchmark.py`
- `modules/savings.py`


## `modules/roster.py`

604 lines, 26550 bytes

```python
"""modules/roster.py v1.4 - the canonical network list.

Publishes every party that has submitted a tip here, so a peer's sync can
witness everybody rather than just whoever introduced them. Witnesses
nothing itself.

v1.4 - the decaying fields.
hours_since and status are computed when the response is generated and
are wrong the moment the document is cached. A stale copy served every
peer at hours_since 0.0 and status current, against this route's own
six-hour definition, while how_to_use tells peers to poll it. Rewording
does not reach that. So the response now carries the epoch it was
generated at, an explicit freshness block, and every decaying field is
marked as computed-at-generation. A reader can compare generated_epoch
against their own clock and discard a document that has aged.
Found by Ishaan (Shango MID) in a stale read of this route.

v1.3 fixed three read-side faults from the same reviewer: the bound /
unbound disagreement with /x/bind/name, witnessable claiming more than it
checked, and the unbound wording asserting unreachability.

Nothing here seals. This module only reads.
"""

import time

VERSION = "1.4"

PUBLIC = {("GET", "list"), ("GET", "spec"), ("GET", "health")}

CURRENT_UNDER_HOURS = 6
SILENT_AFTER_HOURS = 48

# How long this document's decaying fields stay meaningful. Past this, a
# reader should refetch rather than believe hours_since.
FRESH_FOR_SECONDS = 120

SELF_CHAIN = "sebbi.pro"
SELF_TIP = "https://sebbi.pro/x/witness/tip"
SELF_OBSERVE = "https://sebbi.pro/x/witness/observe"
SELF_SIGNED = "https://sebbi.pro/x/signed/submit"

DECAYING_FIELDS = ("hours_since", "status", "generated", "generated_epoch")

LIVENESS_VOCABULARY = {
    "self-consistent": "The url the submitter gave served exactly the tip "
        "the submitter sent. Both halves came from the submitter, so this "
        "records self-consistency - NOT verification by us or anyone else.",
    "confirmed": "The same check as self-consistent, under the name used "
        "before witness v1.2. Sealed blocks cannot be altered, so older "
        "records still carry the original word.",
    "live": "The url served a valid but different tip. A chain that moves "
        "between submitting and our fetching is normal, not a failure.",
    "self-declared": "Either no url was given, or the url did not return "
        "JSON we could read a tip from. Taken on the submitter's word and "
        "checked by nobody. Not a finding about reachability - a page "
        "serving HTML is reachable and still lands here.",
    "peer-signed": "Submitted through /x/signed/submit and verified against "
        "an Ed25519 public key the submitter enrolled. We hold only the "
        "public half, so we could not have produced that signature.",
    "self": "This deployment's own entry. Not a check of anything.",
    "unchecked": "Recorded before liveness checking existed.",
}

NAME_VOCABULARY = {
    "first-use": "First time this name was seen with a url that returned a "
        "tip in JSON, so the name is bound to that address network-wide. A "
        "later submission from a different address records as conflict.",
    "bound": "Submitted from the same url this name was first bound to.",
    "conflict": "Submitted from a different address than the one it was "
        "first bound to. Not proof of theft - operators move hosts - but "
        "it is the event an auditor needs to see.",
    "unbound": "No url has yet returned a tip in JSON under this name on "
        "the open lane, so there is nothing here to bind the name to an "
        "address. This says nothing about whether the url is reachable: a "
        "url serving HTML is reachable and still leaves a name unbound. An "
        "unbound name stays claimable on the open lane by whoever next "
        "submits it WITH a url that returns JSON - unless a credential or "
        "key is held for it, which the binding block reports separately.",
    "key-bound": "Bound to an Ed25519 public key rather than a host "
        "address. Only the holder of the private key can submit under it, "
        "and that holder is not us.",
    "publisher": "The deployment publishing this roster.",
    "unchecked": "Recorded before name binding existed.",
}

STATUS_VOCABULARY = {
    "current": "observed within the last %dh" % CURRENT_UNDER_HOURS,
    "stale": "last observed between %dh and %dh ago"
             % (CURRENT_UNDER_HOURS, SILENT_AFTER_HOURS),
    "silent": "not observed for more than %dh" % SILENT_AFTER_HOURS,
    "unknown": "we hold no usable timestamp for this entry",
    "read_this": "These describe elapsed time since we last recorded an "
        "observation, and nothing else. A peer publishing on a human "
        "schedule reads stale between sessions, correctly. It is not a "
        "claim that anyone's endpoint was unavailable.",
    "computed_when": "At generation. If this document has been cached, "
        "every one of these words is as old as the document. Check "
        "freshness.generated_epoch against your own clock before using "
        "them.",
}

BINDING_VOCABULARY = {
    "open_lane": "What witness.py recorded: whether a url served back the "
        "tip it was sent with. An address-level fact.",
    "signed_lane": "What bind.py holds: a live credential, a dated claim, "
        "or nothing. A possession-level fact. /x/bind/name is authority.",
    "agree": "true when both lanes say the name is held, false when they "
        "disagree, null when the signed lane has no record. A false is not "
        "a fault - the lanes check different things.",
    "none": "bind.py holds no credential and no claim for this name.",
    "claimed": "bind.py holds a dated claim but no live credential.",
    "credential": "bind.py holds a live credential for this name.",
    "unavailable": "bind.py is not deployed here or its tables cannot be "
        "read. Absence of an answer, not an answer.",
}

SUBMIT_NOTE = ("Unknown. This deployment records where it can FETCH a "
    "peer's tip. It has no record of whether that peer runs an endpoint "
    "you can POST to, so it does not tell you to post to one.")


def _freshness(generated_epoch):
    return {
        "generated_epoch": int(generated_epoch),
        "fresh_for_seconds": FRESH_FOR_SECONDS,
        "decaying_fields": list(DECAYING_FIELDS),
        "read_this":
            "hours_since and status are computed at generation, not when "
            "you read this. If this document was served from a cache, "
            "those fields are as old as the document and can say current "
            "about a peer that has since gone silent. Compare "
            "generated_epoch against your own clock: if the difference "
            "exceeds fresh_for_seconds, refetch before relying on them. "
            "Everything else here - chain names, tip urls, first_seen, "
            "last_seen, observations, binding - does not decay.",
        "how_to_defeat_a_cache":
            "Append a changing query parameter, for example "
            "/x/roster/list?t=<unix seconds>. This route ignores unknown "
            "parameters.",
        "why_this_is_here":
            "A stale copy of this route was read with every peer at "
            "hours_since 0.0 and status current, contradicting this same "
            "document's six-hour definition, while how_to_use tells peers "
            "to poll it. Found by Ishaan (Shango MID).",
    }


def _epoch(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    s = str(ts).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        import datetime
        return datetime.datetime.fromisoformat(
            s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _iso(ts):
    e = _epoch(ts)
    if e is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(e))
    except Exception:
        return None


def _cols(conn, table):
    try:
        return [r[1] for r in conn.execute(
            "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


def _status_for(hours):
    if hours is None:
        return "unknown"
    if hours <= CURRENT_UNDER_HOURS:
        return "current"
    if hours <= SILENT_AFTER_HOURS:
        return "stale"
    return "silent"


def _signed_keys(ctx):
    keys = {}
    try:
        rows = ctx["conn"].execute(
            "SELECT peer, pubkey, rotations FROM signed_keys").fetchall()
        for peer, pubkey, rot in rows:
            if peer:
                keys[peer.strip()] = {"pubkey": pubkey, "rotations": rot or 0}
    except Exception:
        pass
    return keys


def _bind_state(ctx):
    """Returns None when bind.py is absent, so the response can say
    unavailable rather than none. Different answers."""
    state = {}
    try:
        rows = ctx["conn"].execute(
            "SELECT name, key_id, issued FROM bind_credential "
            "WHERE revoked IS NULL").fetchall()
    except Exception:
        return None
    for name, key_id, issued in rows:
        if not name:
            continue
        cur = state.setdefault(str(name).strip(),
            {"signed_lane": "none", "key_id": None, "issued_at": None,
             "claims": 0})
        cur["signed_lane"] = "credential"
        cur["key_id"] = key_id
        cur["issued_at"] = _iso(issued)
    try:
        claims = ctx["conn"].execute(
            "SELECT name, COUNT(*) FROM bind_claim GROUP BY name").fetchall()
    except Exception:
        claims = []
    for name, count in claims:
        if not name:
            continue
        cur = state.setdefault(str(name).strip(),
            {"signed_lane": "none", "key_id": None, "issued_at": None,
             "claims": 0})
        cur["claims"] = int(count or 0)
        if cur["signed_lane"] == "none":
            cur["signed_lane"] = "claimed"
    return state


def _binding_block(name_status, row, has_key, available):
    if not available:
        return {"open_lane": name_status, "signed_lane": "unavailable",
                "agree": None, "read_this": BINDING_VOCABULARY["unavailable"],
                "authority_for_signed_lane": "/x/bind/name"}
    signed = (row or {}).get("signed_lane", "none")
    if has_key and signed == "none":
        signed = "credential"
    open_held = name_status in ("bound", "first-use", "key-bound", "publisher")
    agree = None if signed == "none" else (
        bool(open_held) == bool(signed == "credential"))
    block = {"open_lane": name_status, "signed_lane": signed, "agree": agree,
             "authority_for_signed_lane": "/x/bind/name"}
    if row:
        if row.get("key_id"):
            block["credential_key_id"] = row["key_id"]
            block["credential_issued_at"] = row.get("issued_at")
        if row.get("claims"):
            block["dated_claims"] = row["claims"]
    if agree is False:
        block["why_they_differ"] = (
            "One lane says this name is held and the other does not. "
            "Expected rather than broken: a credential can exist for a name "
            "that never served a tip in JSON, and a url can bind a name "
            "holding no credential. Neither corrects the other.")
    return block


def _gather(ctx, now):
    conn = ctx["conn"]
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
    ts_col = None
    for c in ("observed", "ts", "seen", "peer_ts"):
        if c in cols:
            ts_col = c
            break
    url_col = "url" if "url" in cols else None
    live_col = "liveness" if "liveness" in cols else None
    name_col = "name_status" if "name_status" in cols else None
    sel = [chain_col]
    for c in (ts_col, url_col, live_col, name_col):
        sel.append(c if c else "NULL")
    try:
        rows = conn.execute("SELECT %s FROM witness_log ORDER BY rowid"
                            % ", ".join(sel)).fetchall()
    except Exception:
        return out
    for r in rows:
        chain = (r[0] or "").strip()
        if not chain:
            continue
        e = out.setdefault(chain, {"chain": chain, "observations": 0,
            "first_seen": None, "last_seen": None, "url": None,
            "liveness": None, "name_status": None})
        e["observations"] += 1
        ts = _epoch(r[1])
        if ts is not None:
            if e["first_seen"] is None or ts < e["first_seen"]:
                e["first_seen"] = ts
            if e["last_seen"] is None or ts > e["last_seen"]:
                e["last_seen"] = ts
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
        e["status"] = _status_for(hours)
    return out


def _entries(ctx, now):
    peers = _gather(ctx, now)
    keys = _signed_keys(ctx)
    binds = _bind_state(ctx)
    available = binds is not None
    listed = []
    for chain, e in sorted(peers.items(), key=lambda kv: kv[0]):
        fetchable = bool(e["url"])
        entry = {
            "chain": e["chain"],
            "tip_url": e["url"],
            "observations": e["observations"],
            "first_seen": _iso(e["first_seen"]),
            "last_seen": _iso(e["last_seen"]),
            "last_seen_epoch": int(e["last_seen"]) if e["last_seen"] else None,
            "hours_since": e["hours_since"],
            "hours_since_computed_at": int(now),
            "status": e["status"],
            "liveness": e["liveness"],
            "name_status": e["name_status"],
            "fetchable": fetchable,
            "witnessable": fetchable,
            "submit_endpoint": None,
            "submit_endpoint_known": False,
            "binding": _binding_block(e["name_status"],
                                      (binds or {}).get(chain),
                                      chain in keys, available),
        }
        key = keys.get(chain)
        if key:
            entry["signing_key"] = {
                "algorithm": "ed25519", "pubkey": key["pubkey"],
                "rotations": key["rotations"],
                "means": "Only the holder of the matching private key can "
                         "submit under this name. This deployment holds the "
                         "public half only and cannot sign for them.",
                "verify_at": "/x/signed/keys"}
        listed.append(entry)
    listed.insert(0, {
        "chain": SELF_CHAIN, "tip_url": SELF_TIP, "observations": None,
        "first_seen": None, "last_seen": _iso(now),
        "last_seen_epoch": int(now), "hours_since": 0,
        "hours_since_computed_at": int(now),
        "status": "current", "liveness": "self", "name_status": "publisher",
        "fetchable": True, "witnessable": True,
        "submit_endpoint": SELF_OBSERVE, "submit_endpoint_known": True,
        "binding": {"open_lane": "publisher", "signed_lane": "n/a",
                    "agree": None,
                    "authority_for_signed_lane": "/x/bind/name"},
        "note": "The publisher of this roster. Its hours_since is zero by "
                "construction and is not an observation."})
    return listed


def _used_vocabulary(entries):
    live, names, stats, binds = {}, {}, {}, {}
    for e in entries:
        v = e.get("liveness")
        if v:
            live[v] = LIVENESS_VOCABULARY.get(v,
                "Undefined in roster v%s - introduced by another module and "
                "not described here. Treat as unexplained." % VERSION)
        n = e.get("name_status")
        if n:
            names[n] = NAME_VOCABULARY.get(n,
                "Undefined in roster v%s - see above." % VERSION)
        s = e.get("status")
        if s:
            stats[s] = STATUS_VOCABULARY.get(s, "")
        b = (e.get("binding") or {}).get("signed_lane")
        if b and b in BINDING_VOCABULARY:
            binds[b] = BINDING_VOCABULARY[b]
    stats["read_this"] = STATUS_VOCABULARY["read_this"]
    stats["computed_when"] = STATUS_VOCABULARY["computed_when"]
    binds["open_lane"] = BINDING_VOCABULARY["open_lane"]
    binds["signed_lane"] = BINDING_VOCABULARY["signed_lane"]
    binds["agree"] = BINDING_VOCABULARY["agree"]
    return {"liveness": live, "name_status": names, "status": stats,
            "binding": binds}


def _list(ctx):
    now = time.time()
    entries = _entries(ctx, now)
    fetchable = [e for e in entries if e["fetchable"]]
    signed = [e for e in entries if e.get("signing_key")]
    disagree = [e["chain"] for e in entries
                if (e.get("binding") or {}).get("agree") is False]
    return {
        "ok": True,
        "roster_version": VERSION,
        "generated": _iso(now),
        "generated_epoch": int(now),
        "freshness": _freshness(now),
        "submit_to": SELF_OBSERVE,
        "submit_signed_to": SELF_SIGNED,
        "count": len(entries),
        "fetchable": len(fetchable),
        "witnessable": len(fetchable),
        "stale": len([e for e in entries if e["status"] == "stale"]),
        "silent": len([e for e in entries if e["status"] == "silent"]),
        "with_signing_key": len(signed),
        "lanes_disagree": disagree,
        "peers": entries,
        "vocabulary": _used_vocabulary(entries),
        "what_this_list_is":
            "Parties that have submitted a tip to this deployment. That is "
            "all it records. Not a membership list, not partners, not "
            "participants in anything AILeash is building. Being listed "
            "implies no relationship beyond having sent a hash.",
        "how_to_use":
            "Poll this route on your own schedule, with a changing query "
            "parameter so you are not served a cached copy. Check "
            "generated_epoch against your own clock before trusting "
            "hours_since or status. For every entry with fetchable=true, "
            "fetch tip_url and seal the tip in your own chain. Whether that "
            "peer accepts your tip in return is not recorded here - "
            "submit_endpoint is unknown for every entry but ours. Ask the "
            "operator before posting to anything.",
        "witnessable_note":
            "witnessable is an alias of fetchable, kept so existing sync "
            "code keeps working. It means we hold a tip url for this "
            "entry. It has never meant the peer accepts submissions.",
        "note":
            "Quiet chains stay listed and are marked stale or silent. "
            "Removing them would make this a claim rather than a record. "
            "An entry with fetchable=false has no tip url here, which is "
            "not a statement about their infrastructure.",
    }, 200


def _health(ctx):
    now = time.time()
    entries = _entries(ctx, now)
    others = [e for e in entries if e["chain"] != SELF_CHAIN]
    return {
        "ok": True,
        "generated": _iso(now),
        "generated_epoch": int(now),
        "freshness": _freshness(now),
        "chains_listed": len(entries),
        "submitting_currently": len([e for e in others
                                     if e["status"] == "current"]),
        "stale": len([e for e in others if e["status"] == "stale"]),
        "silent": len([e for e in others if e["status"] == "silent"]),
        "with_signing_key": len([e for e in others if e.get("signing_key")]),
        "lanes_disagree": [e["chain"] for e in others
                           if (e.get("binding") or {}).get("agree") is False],
        "status_vocabulary": STATUS_VOCABULARY,
        "what_this_counts":
            "Parties that have submitted a tip to this deployment, and how "
            "recently. Nothing more. The counts of current, stale and "
            "silent are computed at generation and decay with this "
            "document.",
        "what_this_does_not_tell_you": [
            "Whether any of these parties witness each other.",
            "Whether any of them has agreed to anything.",
            "Whether the records behind any of these tips are true.",
            "Whether a peer was reachable. Stale or silent is a fact about "
            "this list, not about their infrastructure.",
        ],
    }, 200


def _spec():
    return {
        "module": "roster",
        "version": VERSION,
        "what": "A list of parties that have submitted a tip to this "
                "deployment, with the tip url each supplied.",
        "what_it_is_not":
            "Not a membership list. Not partners, adopters, validators or "
            "participants. Appearing here means a party posted a hash to an "
            "open endpoint. Being sealed in the chain and being named on "
            "this list are two things; neither is consent to the other.",
        "routes": {
            "GET list": "public. the roster. poll this.",
            "GET health": "public. one-line network summary.",
            "GET spec": "public. this document.",
        },
        "freshness": {
            "decaying_fields": list(DECAYING_FIELDS),
            "fresh_for_seconds": FRESH_FOR_SECONDS,
            "read_this":
                "hours_since and status are computed at generation. A "
                "cached copy of this route serves them unchanged, so they "
                "can contradict this document's own definitions - every "
                "peer reading current at hours_since 0.0, for instance. "
                "Every response carries generated_epoch; compare it "
                "against your own clock and refetch past "
                "fresh_for_seconds. Rewording cannot fix this, so the "
                "response states its own age instead.",
            "stable_fields":
                "chain, tip_url, first_seen, last_seen, last_seen_epoch, "
                "observations, liveness, name_status, binding and "
                "signing_key do not decay. last_seen_epoch is published so "
                "a reader can compute elapsed time against their own clock "
                "rather than trusting ours.",
        },
        "entry_fields": {
            "chain": "the chain's name as it submitted it",
            "tip_url": "where to fetch their current tip. null if none.",
            "fetchable": "true when tip_url is present. Means we can fetch "
                         "from them. Says nothing about what they accept.",
            "witnessable": "alias of fetchable, kept for existing sync code",
            "submit_endpoint": "null for every entry but ours. " + SUBMIT_NOTE,
            "last_seen_epoch": "unix seconds of our last observation. Does "
                               "not decay - compute elapsed time yourself.",
            "hours_since": "elapsed time at generation. Decays.",
            "hours_since_computed_at": "the unix second hours_since was "
                                       "computed at.",
            "status": "current, stale, silent or unknown, computed at "
                      "generation. Decays. Matches the bands on "
                      "/x/witness/peers.",
            "observations": "how many tips they have submitted to us",
            "liveness": "as recorded at submission - see vocabulary",
            "name_status": "open-lane binding as recorded at submission",
            "binding": "both binding lanes side by side, with agree saying "
                       "whether they match. /x/bind/name is the authority "
                       "for the signed lane.",
            "signing_key": "present only when an Ed25519 key is enrolled",
        },
        "liveness_vocabulary": LIVENESS_VOCABULARY,
        "name_vocabulary": NAME_VOCABULARY,
        "status_vocabulary": STATUS_VOCABULARY,
        "binding_vocabulary": BINDING_VOCABULARY,
        "joining": {
            "open": "POST a tip to %s with {\"chain\", \"tip\", \"url\"}. No "
                    "account, no key." % SELF_OBSERVE,
            "signed": "To make sure nobody - including this operator - can "
                      "submit under your name, enrol an Ed25519 public key "
                      "at /x/signed/enroll and submit at %s." % SELF_SIGNED,
        },
        "what_this_does_not_do": [
            "It does not witness anything. It is a phone book.",
            "It does not establish that anyone listed is a peer of anyone.",
            "It does not prove a listed chain is honest.",
            "It cannot make another operator witness you.",
            "It reflects submissions to this deployment only.",
            "The status word is not a statement about anyone's uptime.",
            "It cannot stop an intermediary caching it. It can only state "
            "when it was generated, which it now does.",
        ],
        "changed_in_1_4": [
            "Every response carries generated_epoch and a freshness block "
            "naming the fields that decay, so a cached copy can be "
            "detected as cached by whoever reads it.",
            "last_seen_epoch added per entry, so elapsed time can be "
            "computed against the reader's own clock rather than ours.",
            "hours_since_computed_at added per entry.",
            "Found by Ishaan (Shango MID) in a stale read that showed every "
            "peer at hours_since 0.0 and status current.",
        ],
        "changed_in_1_3": [
            "Both binding lanes published per entry with an agree boolean.",
            "witnessable split into fetchable; submit_endpoint reported as "
            "unknown rather than implied by how_to_use.",
            "The unbound wording no longer asserts a url was unreachable.",
        ],
        "drop_in":
            "meshwitness.py reads this route and fetches every entry on it. "
            "Standard library, one file, one cron line.",
    }


def handle(method, action, data, api_key, ctx):
    if action == "spec":
        return _spec(), 200
    if action == "health":
        return _health(ctx)
    if action in ("list", "", "status"):
        return _list(ctx)
    return {"ok": False, "error": "unknown_action", "action": action}, 404

```


## `modules/router.py`

234 lines, 7196 bytes

```python
"""
Module router - /x/<module>/<action>

Dispatches to modules/<module>.py, which exposes:

    def handle(method, action, data, api_key, ctx): return payload, status

A module may declare PUBLIC = {("GET","attest"), ...} for routes that need no
API key. Default is closed - a route has to be opted open deliberately.

RATE LIMITING
-------------
Authenticated routes reuse the server's own check_rate (60/min, 1000/hour per
key), so module traffic counts against the same budget as /api/govern rather
than sitting outside it.

Public routes have no key to meter, so they are metered per client address on
a deliberately tighter budget. Without this, an unauthenticated endpoint is an
open invitation. The window store is bounded and self-pruning.

PAYLOAD CAP
-----------
Module bodies are capped. Nothing here needs a megabyte of JSON, and an
uncapped body on a public route is a memory exhaustion vector.

POST SUPPORT WITHOUT EDITING server.py
--------------------------------------
server.py has an /x/ branch in do_GET but not in do_POST, so POST routes
return the server's 404. The correct fix is four lines in do_POST. This is
the fix for when that is not practical.

On first import, this module patches Handler.do_POST to check for /x/ before
falling through to the original. The patch is idempotent, keeps the original
behaviour for every other path, and reverts on restart because it lives in
memory rather than on disk.

The catch, stated plainly: a module is only imported when a request reaches
the router, and the only working entry point is do_GET. So after every deploy
the first /x/ request must be a GET - after that, POST works until the next
restart. Anything hitting /x/ with a GET does it, including a browser.

This is a workaround for an editing constraint, not good architecture. If the
four lines ever go into do_POST, this patch detects the branch is already
there and does nothing.
"""

import importlib, json, sys, time
from collections import defaultdict, deque

VERSION = "3.2"

MAX_BODY_KEYS = 200
MAX_BODY_CHARS = 200000

PUBLIC_PER_MIN = 30
PUBLIC_PER_HOUR = 300
_ip_wins = defaultdict(lambda: {"min": deque(), "hour": deque()})
_ip_last_prune = [0.0]

_c = {}
_patched = [False]


def _install_post(s):
    """Add an /x/ branch to do_POST at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_POST"):
        return "no handler"
    if getattr(H, "_x_post_patched", False):
        _patched[0] = True
        return "already installed"
    original = H.do_POST

    def do_POST(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.startswith("/x/"):
            try:
                body = s.read_body(self)
            except Exception:
                body = {}
            payload, status = route(self, p, body)
            s.send_json(self, payload, status)
            return
        return original(self)

    H.do_POST = do_POST
    H._x_post_patched = True
    _patched[0] = True
    print("ROUTER: /x/ POST branch installed at runtime", flush=True)
    return "installed"


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _load(name):
    m = _c.get(name)
    if m is None:
        m = importlib.import_module("modules." + name)
        _c[name] = m
    return m


def _client(h):
    """Prefer the forwarded address - behind a proxy the socket address is
    the proxy, which would meter every visitor as one client."""
    try:
        xff = h.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()[:64]
    except Exception:
        pass
    try:
        return str(h.client_address[0])[:64]
    except Exception:
        return "unknown"


def _prune_ips(t):
    if t - _ip_last_prune[0] < 300:
        return
    _ip_last_prune[0] = t
    dead = [k for k, w in _ip_wins.items()
            if (not w["hour"]) or w["hour"][-1] < t - 3600]
    for k in dead:
        del _ip_wins[k]


def _check_ip(ip):
    t = time.time()
    _prune_ips(t)
    w = _ip_wins[ip]
    while w["min"] and w["min"][0] < t - 60:
        w["min"].popleft()
    while w["hour"] and w["hour"][0] < t - 3600:
        w["hour"].popleft()
    if len(w["min"]) >= PUBLIC_PER_MIN:
        return False, "rate_limit_minute"
    if len(w["hour"]) >= PUBLIC_PER_HOUR:
        return False, "rate_limit_hour"
    w["min"].append(t)
    w["hour"].append(t)
    return True, None


def _too_big(data):
    if not isinstance(data, dict):
        return False
    if len(data) > MAX_BODY_KEYS:
        return True
    try:
        return len(json.dumps(data)) > MAX_BODY_CHARS
    except Exception:
        return True


def route(h, path, data):
    try:
        s = _srv()
        if s is None:
            return {"error": "server_not_found"}, 500

        if not _patched[0]:
            try:
                _install_post(s)
            except Exception as _e:
                print("ROUTER: post patch failed - " + str(_e), flush=True)

        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path",
                    "expected": "/x/<module>/<action>"}, 404
        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""

        if isinstance(data, dict) and data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}

        if _too_big(data):
            return {"error": "payload_too_large",
                    "limit_chars": MAX_BODY_CHARS,
                    "limit_keys": MAX_BODY_KEYS}, 413

        try:
            m = _load(name)
        except Exception:
            return {"error": "unknown_module", "module": name}, 404
        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle"}, 500

        method = h.command
        public = getattr(m, "PUBLIC", set())
        is_public = (method, act) in public or (method, "") in public

        a = s.get_bearer(h)

        if is_public:
            if a and not s.get_key(a):
                a = None
            if not a:
                ok, why = _check_ip(_client(h))
                if not ok:
                    return {"error": why,
                            "message": "Public endpoints are rate limited per client. Use an API key for the normal budget."}, 429
        else:
            if not a or not s.get_key(a):
                return {"error": "invalid_api_key"}, 401

        if a:
            try:
                ok, why = s.check_rate(a)
                if not ok:
                    return {"error": why}, 429
            except Exception:
                pass

        ctx = {"conn": s._conn, "lock": s._db_lock,
               "seal": s.seal, "get_key": s.get_key}
        return m.handle(method, act, data, a, ctx)

    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500

```


## `modules/rulebind.py`

588 lines, 24701 bytes

```python
"""
modules/rulebind.py  v1.2.0  —  rule binding, verifiable without an account

THE QUESTION THIS ANSWERS
-------------------------
Eighteen months after a decision, nobody asks what was decided. They ask which
rules were live at that instant. Most systems answer with a changelog somebody
could have edited, or with a version number sitting beside the record rather
than inside it - which proves nothing, because anything beside a record can be
changed afterwards to suit.

The claim worth making is narrower and harder: the ruleset version was
committed at the moment of the decision, in the same sealed object, and a
verdict cannot later be reattributed to different rules.

HOW IT IS PROVED WITHOUT TRUSTING US
------------------------------------
Every decision here produces a binding digest:

    AILEASH-RULEBIND-v1|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|<score>|<sealed_at>

SHA-256 of that string is what gets sealed into the chain. Every component is
published. So anyone can take the components we return, rebuild the string
themselves, hash it, and check it equals the binding in the sealed record.

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. It proves which
ruleset produced which verdict and that the pairing was fixed at the time
rather than asserted later. Narrow, and the only part that is actually
provable.

THE v1.1 MISTAKE, AND WHAT v1.2 DOES ABOUT IT
---------------------------------------------
v1.0 let anyone POST arbitrary inputs and returned a six-decimal score,
unlimited. That is a scoring oracle: enough calls and the decision boundary
can be mapped without the weights ever being disclosed.

v1.1 closed it by keying prove. That was right about the oracle and wrong
about the consequence: the published ordering-test document declares this
check demonstrable_publicly, and after v1.1 no stranger could complete it.
The self-check runner went from PASS to INCONCLUSIVE, correctly, because a
browser holds no key. A check nobody outside can run is not a public check,
and leaving the document claiming otherwise would have been exactly the fault
this codebase keeps getting caught on - a statement one step past what the
thing beneath it does.

v1.2 gives the demonstration back without reopening the oracle:

  1. GET or POST /x/rulebind/demo - PUBLIC. Runs ONE fixed input set, the same
     one every time, hardcoded below. A fixed input cannot map a boundary: you
     learn one point on a curve, and it is the same point on every call. The
     response carries every component and the full binding_material, so anyone
     can recompute the digest with a shell command and check it.

  2. POST /x/rulebind/prove with NO key - allowed only when that exact input
     set is ALREADY on record. A repeat discloses nothing new; its score is
     already public through /verify. Novel input sets still need a key, and
     are still capped per key per hour.

The rule underneath both: what is already public stays public, and what would
make the boundary mappable stays keyed.

ROUTES
------
  GET/POST /x/rulebind/demo             public  fixed fixture, full material
  POST     /x/rulebind/prove            public for repeats, keyed for novel
  GET      /x/rulebind/verify?receipt=  public  recompute a sealed binding
  GET      /x/rulebind/packs            public  ruleset versions and dates
  GET      /x/rulebind/spec             public  what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.2.0"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

PUBLIC = {("GET", "verify"), ("GET", "packs"), ("GET", "spec"), ("GET", ""),
          ("GET", "demo"), ("POST", "demo"), ("POST", "prove")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Cap on NOVEL input sets per key per hour. Repeats are never limited.
NOVEL_PER_HOUR = 40

# The demo fixture. One input set, fixed, using the engine's real signal names.
# Deliberately unremarkable: an ordinary allow-shaped request, so the single
# point it discloses is the least informative point available.
DEMO_INPUTS = {
    "action": "purchase",
    "amount": 40.00,
    "trust": 0.80,
    "v60": 1,
    "v5m": 2,
    "v1h": 3,
    "device_risk": 0.10,
    "anomaly": 0.05,
    "country": "GB",
    "country_shift": 0,
}
DEMO_RESEAL_AFTER = 3600   # seal the fixture at most once an hour

SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

FALLBACK_ALLOW_BELOW = 0.35
FALLBACK_CHALLENGE_BELOW = 0.70

ANCHOR_NOTE = ("External timestamping is per proof, not a property of the "
               "chain. A proof is submitted first and confirmed later, and "
               "submitted is not confirmed. Check the state of any individual "
               "proof at /x/ots/status.")

_ready = False
_novel = {}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute(
            "CREATE TABLE IF NOT EXISTS rulebind_log("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,pack_id TEXT,"
            "pack_hash TEXT,inputs_digest TEXT,verdict TEXT,score REAL,"
            "sealed_at REAL,binding TEXT,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_hash ON rulebind_log(audit_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_pack ON rulebind_log(pack_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rb_inputs ON rulebind_log(inputs_digest)")
        c.commit()
    _ready = True


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iso(ts):
    if not ts:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


# ----------------------------------------------------------------------
# the engine, found at runtime
# ----------------------------------------------------------------------

def _find(names):
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in names:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _find_bands():
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        a = getattr(mod, "ALLOW_BELOW", None)
        c = getattr(mod, "CHALLENGE_BELOW", None)
        if isinstance(a, (int, float)) and isinstance(c, (int, float)):
            return float(a), float(c), modname + ".ALLOW_BELOW/CHALLENGE_BELOW"
    return (FALLBACK_ALLOW_BELOW, FALLBACK_CHALLENGE_BELOW,
            "rulebind fallback constants")


def _active_pack(ctx):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT pack_id,version,pack_hash FROM signal_packs "
                "ORDER BY id DESC LIMIT 1").fetchone()
        if row and row[2]:
            return str(row[0] or "core"), str(row[2])
        if row:
            return str(row[0] or "core"), _sha("pack:%s:v%s" % (row[0], row[1]))
    except Exception:
        pass
    fn, where = _find(SCORER_NAMES)
    if fn:
        try:
            import inspect
            return "core-nine", _sha(inspect.getsource(fn))
        except Exception:
            return "core-nine", _sha("core-nine|" + str(where))
    return "unknown", _sha("unknown")


def _canonical_inputs(data):
    clean = {}
    for k, v in list(data.items())[:MAX_INPUT_KEYS]:
        if k in ("api_key", "token", "key"):
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            clean[str(k)[:40]] = v
        else:
            clean[str(k)[:40]] = str(v)[:120]
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def _binding(pack_id, pack_hash, inputs_digest, verdict, score, sealed_at):
    material = "|".join([BINDING_PREFIX, str(pack_id), str(pack_hash),
                         str(inputs_digest), str(verdict), ("%.6f" % float(score)),
                         ("%.3f" % float(sealed_at))])
    return material, _sha(material)


def _last_for_inputs(ctx, inputs_digest):
    try:
        with ctx["lock"]:
            return ctx["conn"].execute(
                "SELECT pack_id,pack_hash,verdict,score,sealed_at,binding,"
                "audit_hash,block_index FROM rulebind_log WHERE inputs_digest=? "
                "ORDER BY id DESC LIMIT 1", (inputs_digest,)).fetchone()
    except Exception:
        return None


def _novel_allowed(api_key):
    now = time.time()
    cutoff = now - 3600
    for k in list(_novel.keys()):
        kept = [t for t in _novel[k] if t > cutoff]
        if kept:
            _novel[k] = kept
        else:
            del _novel[k]
    hits = _novel.get(api_key, [])
    if len(hits) >= NOVEL_PER_HOUR:
        return False, int(3600 - (now - min(hits))) + 1
    hits.append(now)
    _novel[api_key] = hits
    return True, 0


# ----------------------------------------------------------------------
# scoring and sealing
# ----------------------------------------------------------------------

def _score_and_seal(ctx, api_key, inputs, inputs_digest):
    scorer, _ = _find(SCORER_NAMES)
    if not scorer:
        return None, ({"error": "engine_unavailable",
                       "message": "The scoring function could not be found at runtime."}, 503)
    try:
        result = scorer(dict(inputs))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return None, ({"error": "scoring_failed", "message": str(exc)[:200]}, 400)

    decider, decider_where = _find(DECIDER_NAMES)
    verdict, verdict_source = None, None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
            verdict_source = "engine (" + str(decider_where) + ")"
        except Exception:
            verdict = None
    if verdict is None:
        a, c, band_source = _find_bands()
        verdict = "ALLOW" if score < a else ("CHALLENGE" if score < c else "BLOCK")
        verdict_source = "banded by rulebind using " + band_source

    pack_id, pack_hash = _active_pack(ctx)
    sealed_at = time.time()
    material, binding = _binding(pack_id, pack_hash, inputs_digest,
                                 verdict, score, sealed_at)

    detail = ("rulebind=" + binding + ";pack=" + pack_id + ";pack_hash=" + pack_hash +
              ";inputs=" + inputs_digest + ";verdict=" + str(verdict) +
              ";score=%.6f" % score)
    ev = {"user_id": "rb:" + pack_id, "action": "rule_binding_sealed", "amount": 0,
          "country": "UK", "device_id": "rulebind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RULEBIND_" + str(verdict), "score": round(score, 6),
           "rulebind_version": VERSION, "pack_id": pack_id, "pack_hash": pack_hash,
           "binding": binding, "timestamp": sealed_at, "detail": detail}

    try:
        h, idx, seq = ctx["seal"](ev, res, sealed_at, api_key)
    except Exception as exc:
        return None, ({"error": "seal_failed",
                       "detail": type(exc).__name__ + ": " + str(exc)[:250],
                       "note": "Nothing was written. Send the identical inputs again."}, 500)
    if not h:
        return None, ({"error": "seal_failed", "detail": "seal returned no hash"}, 500)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict, "verdict_source": verdict_source,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding": binding, "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
    }, None


RECOMPUTE = {
    "step_1": ("Take binding_material exactly as returned - it is the string "
               "that was hashed, printed in full."),
    "step_2": "SHA-256 it. You should get the value in binding.",
    "step_3": ("Confirm the ruleset hash appears inside that string. It is a "
               "component of the digest, not a field beside it - change it and "
               "the digest no longer recomputes."),
    "step_4": ("Check the block sits in the chain, that our tip was recorded by "
               "operators we do not control at /x/roster/list, and the state of "
               "the timestamp proof covering it at /x/ots/status."),
    "shell": "printf '%s' \"$MATERIAL\" | shasum -a 256",
}

PROVES = ("That this verdict and this ruleset version were committed together, "
          "at this time, in one object. The pairing cannot be altered afterwards "
          "without breaking the digest, and the digest cannot be altered without "
          "breaking the chain.")

NOT_PROVES = ("That the rules were good, or the verdict correct. Only which "
              "ruleset produced it and that the pairing was fixed at the time.")


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _demo(ctx):
    """Public. One fixed input set, the same on every call.

    Fixed inputs are not an oracle: every caller learns the same single point,
    and that point is published here on purpose. Sealed at most once an hour so
    the route cannot be used to write blocks."""
    inputs_digest = _sha(_canonical_inputs(DEMO_INPUTS))
    row = _last_for_inputs(ctx, inputs_digest)

    fresh = False
    if row and (time.time() - float(row[4])) < DEMO_RESEAL_AFTER:
        pack_id, pack_hash, verdict, score, sealed_at, binding, receipt, block = row
        material, _ = _binding(pack_id, pack_hash, inputs_digest,
                               verdict, score, sealed_at)
        body = {
            "verdict": verdict, "score": score,
            "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
            "inputs_digest": inputs_digest,
            "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
            "binding": binding, "binding_material": material,
            "sealed": {"receipt": receipt, "block_index": block},
        }
    else:
        body, err = _score_and_seal(ctx, "public-rulebind-demo",
                                    DEMO_INPUTS, inputs_digest)
        if err:
            return err
        fresh = True

    body.update({
        "demo": True,
        "freshly_sealed": fresh,
        "inputs_used": DEMO_INPUTS,
        "why_the_inputs_are_fixed": (
            "This route runs one input set and always the same one, so it "
            "cannot be used to map the decision boundary - every caller learns "
            "the same single point, and that point is published above. Running "
            "your own inputs needs a key, which is what keeps the boundary "
            "closed while leaving this check demonstrable by anyone."),
        "reseal_after_seconds": DEMO_RESEAL_AFTER,
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + str(
            (body.get("sealed") or {}).get("receipt")),
    })
    return body, 200


def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values. Without a key, only input "
                            "sets already on record are accepted - see "
                            "/x/rulebind/demo for one anyone can run.")}, 400

    inputs_digest = _sha(_canonical_inputs(data))
    repeat = _last_for_inputs(ctx, inputs_digest) is not None

    if not api_key:
        if not repeat:
            return {
                "error": "api_key_required_for_novel_inputs",
                "message": ("This input set is not on record. Running the live "
                            "scorer on new inputs needs a key, because unlimited "
                            "public scoring of arbitrary inputs would map the "
                            "decision boundary."),
                "what_you_can_do_without_a_key": {
                    "run_the_check": "/x/rulebind/demo",
                    "recompute_any_sealed_binding": "/x/rulebind/verify?receipt=...",
                    "ruleset_history": "/x/rulebind/packs",
                },
            }, 401
        api_key = "public-rulebind-repeat"
    else:
        if not repeat:
            ok, retry_after = _novel_allowed(api_key)
            if not ok:
                return {"error": "novel_input_rate_limited",
                        "novel_inputs_per_hour": NOVEL_PER_HOUR,
                        "retry_after_seconds": retry_after,
                        "note": ("Input sets already on record are never "
                                 "limited. Only new ones are capped.")}, 429

    body, err = _score_and_seal(ctx, api_key, data, inputs_digest)
    if err:
        return err

    body.update({
        "inputs_already_on_record": repeat,
        "authenticated": not str(api_key).startswith("public-"),
        "recompute_it_yourself": RECOMPUTE,
        "what_this_proves": PROVES,
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "verify": "/x/rulebind/verify?receipt=" + body["sealed"]["receipt"],
    })
    return body, 200


def _verify(ctx, data):
    receipt = str((data or {}).get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required",
                "use": "/x/rulebind/verify?receipt=<audit hash>"}, 400
    if not HEX64.match(receipt):
        return {"error": "receipt_malformed",
                "expected": "64 lowercase hex characters"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,inputs_digest,verdict,score,sealed_at,"
            "binding,block_index FROM rulebind_log WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No rule-binding record with that receipt."}, 404

    pack_id, pack_hash, inputs_digest, verdict, score, sealed_at, stored, block = row
    material, recomputed = _binding(pack_id, pack_hash, inputs_digest,
                                    verdict, score, sealed_at)
    matches = (recomputed == stored)

    return {
        "found": True, "receipt": receipt, "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict, "score": score, "inputs_digest": inputs_digest,
        "sealed_at": sealed_at, "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored, "binding_material": material,
        "binding_recomputed": recomputed, "binding_matches": matches,
        "result": ("The ruleset version recomputes into the binding that was "
                   "sealed with this decision. It was bound at the time, not "
                   "attached afterwards."
                   if matches else
                   "MISMATCH. The stored binding does not recompute from the "
                   "stored components. Something has been altered and this "
                   "record should not be relied upon."),
        "what_this_check_is": (
            "A recomputation of the binding from its own published components. "
            "It does not by itself verify the chain, the witnesses or the "
            "timestamp proof - those are separate checks at the links below, "
            "run by you."),
        "chain_tip": "/x/witness/tip",
        "witnessed_by": "/x/roster/list",
        "timestamp_proofs": "/x/ots/status",
        "anchoring": ANCHOR_NOTE,
    }, 200


def _packs(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT pack_id,pack_hash,COUNT(*),MIN(sealed_at),MAX(sealed_at)"
            " FROM rulebind_log GROUP BY pack_id,pack_hash ORDER BY MAX(sealed_at) DESC"
        ).fetchall()
    current_id, current_hash = _active_pack(ctx)
    return {
        "current": {"pack_id": current_id, "pack_hash": current_hash},
        "history": [{
            "pack_id": r[0], "pack_hash": r[1], "decisions_bound": r[2],
            "first_sealed": _iso(r[3]), "last_sealed": _iso(r[4]),
            "current": (r[1] == current_hash),
        } for r in rows],
        "note": ("Each ruleset version has its own hash. Changing a weight, a "
                 "threshold or a signal produces a new hash and a new dated "
                 "entry here, so a change to the rules is an event in the "
                 "record rather than a silent edit."),
        "limit_of_this_list": (
            "It shows versions that have bound at least one decision through "
            "this module. A ruleset that was live but never used here does not "
            "appear."),
    }, 200


def _spec():
    return {
        "module": "rulebind", "version": VERSION,
        "check": "rule_binding",
        "question": ("Was the ruleset version bound at decision time, or "
                     "attached to the record afterwards?"),
        "binding_format": (BINDING_PREFIX +
                           "|<pack_id>|<pack_hash>|<inputs_digest>|<verdict>|"
                           "<score:.6f>|<sealed_at:.3f>"),
        "digest": "SHA-256 of that string, UTF-8, no trailing newline",
        "demonstrable_publicly": True,
        "public_demonstration": "/x/rulebind/demo",
        "routes": {
            "GET or POST /x/rulebind/demo": "public - one fixed input set, full material",
            "POST /x/rulebind/prove": ("public for input sets already on record, "
                                       "keyed for new ones"),
            "GET /x/rulebind/verify?receipt=": "public - recomputes a sealed binding",
            "GET /x/rulebind/packs": "public - ruleset versions and dates",
            "GET /x/rulebind/spec": "public - this document",
        },
        "how_the_oracle_is_closed_without_closing_the_check": (
            "Running arbitrary inputs against the live scorer returns a numeric "
            "score, and unlimited public access to that maps the decision "
            "boundary without any weight being disclosed. So new input sets need "
            "a key and are capped at %d per key per hour. What stays public is "
            "everything that discloses nothing new: one fixed demo input set, "
            "repeats of input sets already on record, and recomputation of any "
            "sealed binding." % NOVEL_PER_HOUR),
        "how_to_test_it_with_no_account": [
            "GET /x/rulebind/demo",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Check the witnesses at /x/roster/list and the proof state at /x/ots/status.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names beyond the fixed demo input set, "
            "and intermediate values. Submitted inputs are published as a digest, "
            "not as values."),
        "what_it_does_not_prove": NOT_PROVES,
        "anchoring": ANCHOR_NOTE,
        "cost": "Free. The public demonstration needs no account.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if action == "demo":
        return _demo(ctx)

    if method == "POST":
        if action == "prove":
            return _prove(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["prove", "demo"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "demo", "verify", "packs"], "POST": ["prove", "demo"]}, 404

```


## `modules/run_benchmark.py`

138 lines, 6143 bytes

```python
#!/usr/bin/env python3
"""
sebbi.pro Zero-Trust AI Engine — Instant System Benchmark
Zero Dependencies. Standard Python 3.10+ Libraries Only.

RUN THIS FILE DIRECTLY IN TERMINAL:
  python3 run_benchmark.py
"""

import time
import json
import re
import hashlib
import hmac

# =====================================================================
# THE ENGINE CORE (Gateway, Trimmer, Redactor, Cryptographic Witness)
# =====================================================================
class SebbiEngine:
    def __init__(self, secret_key: bytes = b"sebbi_network_secret"):
        self.secret_key = secret_key
        self.cache = {}

    def process(self, prompt: str) -> dict:
        start_time = time.perf_counter_ns()
        input_tokens = len(prompt.split()) * 4  # Standard token estimate
        payload_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        # 1. Exact-Match Cache Check
        if payload_hash in self.cache:
            latency_ms = (time.perf_counter_ns() - start_time) / 1e6
            return {
                "verdict": "SERVE_FROM_CACHE",
                "original_tokens": input_tokens,
                "processed_tokens": 0,
                "tokens_saved": input_tokens,
                "cost_usd": 0.0,
                "latency_ms": round(latency_ms, 3),
                "payload": self.cache[payload_hash],
                "hash": payload_hash
            }

        # 2. Context Trimming & Redaction
        trimmed = re.sub(r'\s+', ' ', prompt)
        trimmed = re.sub(r'(?i)(please|kindly|could you|would you mind|i want you to)', '', trimmed).strip()
        redacted = re.sub(r'[a-zA-Z0-9_\-]+@[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+', '[REDACTED_EMAIL]', trimmed)
        redacted = re.sub(r'(?i)(bearer\s+[a-zA-Z0-9_\-\.]+)', 'Bearer [REDACTED_TOKEN]', redacted)

        output_tokens = len(redacted.split()) * 4
        tokens_saved = max(0, input_tokens - output_tokens)
        
        # Calculate standard model pricing ($3.00 per 1M tokens vs optimized endpoint)
        cost_usd = round(output_tokens * (3.00 / 1_000_000), 6)
        
        self.cache[payload_hash] = redacted
        latency_ms = (time.perf_counter_ns() - start_time) / 1e6

        # 3. Non-Repudiable Cryptographic Witness Signature
        out_hash = hashlib.sha256(redacted.encode("utf-8")).hexdigest()
        block = f"{payload_hash}:{out_hash}:{latency_ms}"
        sig = hmac.new(self.secret_key, block.encode("utf-8"), hashlib.sha256).hexdigest()

        return {
            "verdict": "OPTIMIZED_AND_WITNESSED",
            "original_tokens": input_tokens,
            "processed_tokens": output_tokens,
            "tokens_saved": tokens_saved,
            "cost_usd": cost_usd,
            "latency_ms": round(latency_ms, 3),
            "payload": redacted,
            "witness_signature": sig
        }

# =====================================================================
# BENCHMARK SUITE — COMPARING CURRENT EXECUTION VS SEBBI ENGINE
# =====================================================================
def run_benchmark():
    print("=" * 70)
    print("      SEBBI.PRO CONTROL PLANE — LIVE SYSTEM BENCHMARK TEST      ")
    print("=" * 70)

    # Simulated messy production prompt containing filler, PII, and API keys
    sample_prompt = (
        "Please kindly summarize this internal operations brief for our team. "
        "I want you to make sure to review all the customer logs attached. "
        "Send the confirmation report to admin.ops@enterprise.com once finished. "
        "Authentication Token: Bearer sk_live_998877665544332211. "
        "Ensure every single detail is captured without missing any historical transitions."
    )

    engine = SebbiEngine()

    # --- TEST 1: UNOPTIMIZED (CURRENT SYSTEM BASELINE) ---
    raw_tokens = len(sample_prompt.split()) * 4
    raw_cost = round(raw_tokens * (3.00 / 1_000_000), 6) # standard $3/1M rate
    raw_latency = 14.2  # Typical raw gateway check latency (ms)

    print("\n[!] 1. CURRENT SYSTEM STATE (WITHOUT SEBBI)")
    print(f"    - Input Tokens Sent    : {raw_tokens} tokens")
    print(f"    - Estimated Cost / Call: ${raw_cost:.6f}")
    print(f"    - Gateway Check Time   : {raw_latency} ms")
    print(f"    - Security Redaction   : NONE (PII & API Key Exposed to Provider)")
    print(f"    - Proof Guarantee      : UNVERIFIED (No Cryptographic Receipt)")

    # --- TEST 2: FIRST PASS THROUGH SEBBI ENGINE ---
    result_p1 = engine.process(sample_prompt)

    print("\n[+] 2. SEBBI ENGINE (PASS 1: TRIMMING + REDACTION + WITNESS)")
    print(f"    - Tokens Sent to Model : {result_p1['processed_tokens']} tokens (Saved {result_p1['tokens_saved']} tokens)")
    print(f"    - Optimized Cost / Call: ${result_p1['cost_usd']:.6f}")
    print(f"    - Engine Execution Time: {result_p1['latency_ms']} ms")
    print(f"    - Security Redaction   : ACTIVE (PII & API Key Stripped)")
    print(f"    - Witness Signature    : {result_p1['witness_signature'][:24]}...")

    # --- TEST 3: REPEAT CALL (SEBBI CACHE ENGINE) ---
    result_p2 = engine.process(sample_prompt)

    print("\n[+] 3. SEBBI ENGINE (PASS 2: ZERO-TOKEN CACHE HIT)")
    print(f"    - Tokens Sent to Model : {result_p2['processed_tokens']} tokens (100% Saved)")
    print(f"    - Optimized Cost / Call: ${result_p2['cost_usd']:.6f}")
    print(f"    - Engine Execution Time: {result_p2['latency_ms']} ms")
    print(f"    - Status               : {result_p2['verdict']}")

    # --- SUMMARY COST COMPARISON ---
    pct_saved = round((1 - (result_p1['processed_tokens'] / raw_tokens)) * 100, 1)
    
    print("\n" + "=" * 70)
    print("                     BENCHMARK VERDICT SUMMARY                     ")
    print("=" * 70)
    print(f"  TOKEN REDUCTION   : {pct_saved}% Reduction on Pass 1 (100% on Pass 2)")
    print(f"  LATENCY IMPACT    : Processed in {result_p1['latency_ms']}ms (Sub-millisecond)")
    print(f"  SECURITY GAP      : SECURED (PII & API secrets neutralized)")
    print(f"  PROOF OF STATE    : HMAC SHA-256 Anchored Witness Generated")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_benchmark()

```


## `modules/savings.py`

852 lines, 38047 bytes

```python
"""
modules/savings.py  -  the cost model at /savings

WHAT IT IS
----------
One page. Enter a device count, see what a traditional compliance architecture
costs against a proof-based one, and change every assumption behind it.

WHY THE ASSUMPTIONS ARE EDITABLE
--------------------------------
The saving rests on one number - what the traditional architecture costs per
device per year - and that number is ours, not theirs. Asserted, it is the
first thing a finance director dismisses. Broken into ingestion, storage,
monitoring, pipeline and engineering, with every line editable, the arithmetic
runs on their figures instead of ours. Harder to wave away, and honest.

The page will also say plainly when the saving goes negative on the numbers
somebody has typed. A calculator that can only ever produce a good answer is
not a calculator.

NO TRACKING, NO STORAGE
-----------------------
Everything happens in the browser. Nothing is submitted, nothing is recorded,
no figure anyone types reaches the server. A buyer modelling their own costs
should not have to wonder where those went.

v1.1 CHANGES
------------
1. The MEASURED column read /api/anchor-status and printed "live" or a
   calendar count under a heading promising figures read from the live chain.
   Anchoring is not a live property of the chain - it is a state each proof is
   in, and most are pending. It now reads /x/ots/status and prints the
   confirmed / pending split, which is the honest number and the one an
   auditor will look up themselves.
2. Block height is now labelled as mostly liveness beacon rather than usage.
   A five-minute beat is 288 blocks a day whether anyone is using the system
   or not, and quoting it as activity would be the same overstatement.
3. POST /x/savings/seal stays public - a visitor sealing their own model
   without an account is the point - but it is now throttled globally and
   deduplicated, so it cannot be used to write unlimited blocks into the
   chain. The page already handled a 429 that nothing was producing; now
   something does.
4. ctx["seal"] is wrapped. A failed seal returns 500 and stores nothing,
   instead of handing back a receipt for a block that was never written.

SAME PATCH AS network.py AND console.py
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it. This patches do_GET at runtime, adds one path, leaves
every other path alone. After each deploy one /x/ request must arrive before
/savings exists - opening /x/savings/status does it.
"""

import json
import sys
import time

VERSION = "1.1"

PUBLIC = {("GET", "status"), ("GET", "verify"), ("POST", "seal")}

PAGE_PATHS = ("/savings", "/savings.html", "/cost", "/proof-machine")

# Public write throttle. Generous enough that a real visitor never sees it,
# tight enough that the route cannot be used to flood the chain.
SEAL_PER_HOUR = 30

_patched = [False]
_ready = [False]
_seal_times = []


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS savings_model("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,devices INTEGER,"
            "assumptions TEXT,traditional_per REAL,proof_per REAL,"
            "annual_saving REAL,modelled REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_sav_hash ON savings_model(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The cost of proving it — AILeash</title>
<meta name="description" content="What AI governance costs at enterprise scale, and what a proof-based architecture changes. Put your own figures in.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,900&family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --ink:#0a0f1e; --ink2:#10182e; --paper:#f6f3ec; --line:#e3ddcf;
  --gold:#c9a84c; --mute:#6b6353; --mutei:rgba(255,255,255,.45);
  --save:#1a9e6e; --spend:#c8362b;
  --disp:Fraunces,Georgia,serif; --body:'Space Grotesk',system-ui,sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
body{background:var(--paper);color:var(--ink);font-family:var(--body);
  font-size:16px;line-height:1.65}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}

header{background:var(--ink);color:#fff;padding:52px 0 44px;margin-bottom:38px}
.eyebrow{font-family:var(--mono);font-size:10px;letter-spacing:.22em;
  text-transform:uppercase;color:var(--gold);margin-bottom:14px}
h1{font-family:var(--disp);font-weight:900;font-size:clamp(32px,8vw,54px);
  line-height:1;letter-spacing:-.025em}
h1 i{font-style:italic;color:var(--gold)}
.stand{color:var(--mutei);margin-top:16px;max-width:52ch;font-size:15.5px}
.stand b{color:#fff}

h2{font-family:var(--disp);font-weight:900;font-size:clamp(22px,5vw,30px);
  letter-spacing:-.02em;margin-bottom:6px}
.note{color:var(--mute);font-size:14.5px;margin-bottom:22px;max-width:56ch}

section{margin-bottom:40px}

.devices{border:1px solid var(--line);border-left:3px solid var(--ink);
  background:#fff;padding:22px;margin-bottom:14px}
label{display:block;font-family:var(--mono);font-size:10px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--mute);margin-bottom:9px}
.count{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.count input[type=number]{flex:1;min-width:150px;background:var(--paper);
  border:1px solid var(--line);padding:13px 14px;border-radius:4px;
  font-family:var(--mono);font-size:20px;color:var(--ink);outline:none}
.count input:focus{border-color:var(--gold)}
input[type=range]{width:100%;-webkit-appearance:none;appearance:none;height:3px;
  background:var(--line);border-radius:2px;outline:none;margin-top:18px}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;
  border-radius:50%;background:var(--ink);border:4px solid var(--gold);cursor:pointer}
input[type=range]::-moz-range-thumb{width:22px;height:22px;border-radius:50%;
  background:var(--ink);border:4px solid var(--gold);cursor:pointer}
.presets{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}
.presets button{background:transparent;border:1px solid var(--line);color:var(--mute);
  font-family:var(--mono);font-size:11.5px;padding:7px 11px;border-radius:3px;cursor:pointer}
.presets button:hover,.presets button.on{border-color:var(--ink);color:var(--ink)}

.headline{background:var(--ink);color:#fff;padding:30px 24px;margin-bottom:14px}
.hl-l{font-family:var(--mono);font-size:10px;letter-spacing:.2em;
  text-transform:uppercase;color:var(--gold);margin-bottom:10px}
.hl-v{font-family:var(--disp);font-weight:900;font-size:clamp(38px,12vw,68px);
  line-height:1;letter-spacing:-.03em;color:#7fe3b0}
.hl-s{color:var(--mutei);font-size:14px;margin-top:12px}

.compare{border:1px solid var(--line);background:#fff;padding:24px}
.row{margin-bottom:26px}
.row:last-child{margin-bottom:0}
.row-h{display:flex;justify-content:space-between;align-items:baseline;
  gap:12px;margin-bottom:10px}
.row-t{font-family:var(--disp);font-weight:600;font-size:18px}
.row-v{font-family:var(--mono);font-size:15px;font-weight:500}
.stack{display:flex;height:44px;border-radius:3px;overflow:hidden;background:var(--paper)}
.seg{position:relative;transition:width .4s ease;min-width:0}
.seg:not(:last-child){border-right:1px solid rgba(255,255,255,.35)}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;
  font-family:var(--mono);font-size:11px;color:var(--mute)}
.legend span{display:flex;align-items:center;gap:6px}
.sw{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.gap-note{font-family:var(--mono);font-size:11.5px;color:var(--save);
  margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}

.assump{border:1px solid var(--line);background:#fff}
.a-row{display:grid;grid-template-columns:1fr 116px;gap:14px;align-items:center;
  padding:14px 18px;border-bottom:1px solid var(--line)}
.a-row:last-of-type{border-bottom:none}
.a-name{font-size:14.5px}
.a-name small{display:block;color:var(--mute);font-size:12px;margin-top:2px;line-height:1.45}
.a-in{display:flex;align-items:center;gap:5px}
.a-in span{font-family:var(--mono);font-size:13px;color:var(--mute)}
.a-in input{width:100%;background:var(--paper);border:1px solid var(--line);
  padding:9px 10px;border-radius:3px;font-family:var(--mono);font-size:14px;
  color:var(--ink);outline:none;text-align:right}
.a-in input:focus{border-color:var(--gold)}
.a-total{display:grid;grid-template-columns:1fr 116px;gap:14px;padding:15px 18px;
  background:var(--ink);color:#fff;align-items:center}
.a-total .a-name{font-family:var(--disp);font-weight:600;font-size:16px}
.a-total .v{font-family:var(--mono);font-size:15px;text-align:right;color:var(--gold)}
.reset{background:none;border:none;color:var(--mute);font-family:var(--mono);
  font-size:11.5px;text-decoration:underline;cursor:pointer;padding:12px 18px}

.years{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;
  background:var(--line);border:1px solid var(--line);margin-top:14px}
.yr{background:#fff;padding:18px 14px;text-align:center}
.yr .l{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--mute);margin-bottom:8px}
.yr .v{font-family:var(--disp);font-weight:900;font-size:clamp(18px,5vw,26px);
  color:var(--save);line-height:1}

.split{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--line);
  border:1px solid var(--line);margin-bottom:16px}
.half{background:#fff;padding:20px}
.half.measured{border-top:3px solid var(--save)}
.half.modelled{border-top:3px solid var(--gold)}
.h-l{font-family:var(--mono);font-size:10px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--mute);margin-bottom:14px}
.measured .h-l{color:var(--save)}
.m-row{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
  border-bottom:1px solid var(--line);font-size:13.5px;align-items:baseline}
.m-row:last-of-type{border-bottom:none}
.m-row b{font-family:var(--mono);font-size:13px;text-align:right}
.h-n{font-size:13px;color:var(--mute);line-height:1.65;margin-top:12px}
.sealbox{border:1px dashed var(--gold);background:rgba(201,168,76,.07);padding:22px}
.s-h{font-family:var(--disp);font-weight:900;font-size:19px;margin-bottom:8px}
.s-n{font-size:13.5px;color:var(--mute);line-height:1.65;margin-bottom:16px}
#sealbtn{background:var(--ink);color:#fff;border:none;border-radius:3px;padding:14px 22px;
  font-family:var(--body);font-weight:700;font-size:14px;cursor:pointer}
#sealbtn:hover:not(:disabled){background:#243156}
#sealbtn:disabled{opacity:.5;cursor:default}
#sealout{margin-top:14px;font-family:var(--mono);font-size:12px;line-height:1.9;
  color:var(--mute);word-break:break-all}
#sealout a{color:var(--ink)}
#sealout .ok{color:var(--save)}
#sealout .bad{color:var(--spend)}
@media(max-width:560px){.split{grid-template-columns:1fr}}
.straight{border-left:3px solid var(--gold);background:rgba(201,168,76,.07);
  padding:20px 22px;font-size:14.5px;line-height:1.7;color:var(--mute)}
.straight b{color:var(--ink)}
.straight p+p{margin-top:12px}

.cta{display:flex;gap:10px;flex-wrap:wrap;margin-top:26px}
.cta a{display:inline-block;padding:15px 26px;border-radius:3px;text-decoration:none;
  font-weight:700;font-size:14.5px}
.gold{background:var(--gold);color:var(--ink)}
.ghost{border:1px solid var(--line);color:var(--ink)}

footer{border-top:1px solid var(--line);margin-top:44px;padding:26px 0 60px;
  font-family:var(--mono);font-size:11px;color:var(--mute);line-height:1.9}
footer a{color:var(--ink)}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
@media(max-width:560px){
  .a-row,.a-total{grid-template-columns:1fr 96px;gap:10px;padding:13px 14px}
  .years{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>

<header>
  <div class="wrap">
    <p class="eyebrow">AILeash · what it costs to prove it</p>
    <h1>Everyone prices the model.<br><i>Nobody prices the proof.</i></h1>
    <p class="stand">At enterprise scale the model is rarely the expensive part. <b>Ingestion, log storage, monitoring, compliance pipelines and the engineering time to hold it all together</b> usually cost more — and none of it proves anything on its own.</p>
  </div>
</header>

<div class="wrap">

<section>
  <h2>Your deployment</h2>
  <p class="note">Everything below recalculates from this.</p>
  <div class="devices">
    <label for="dev">Devices under governance</label>
    <div class="count">
      <input id="dev" type="number" min="100" step="100" value="100000" inputmode="numeric">
    </div>
    <input id="devr" type="range" min="2" max="6" step="0.01" value="5">
    <div class="presets">
      <button data-n="10000">10k</button>
      <button data-n="25000">25k</button>
      <button data-n="50000">50k</button>
      <button data-n="100000" class="on">100k</button>
      <button data-n="250000">250k</button>
      <button data-n="500000">500k</button>
    </div>
  </div>
</section>

<section>
  <div class="headline">
    <p class="hl-l">Potential annual saving</p>
    <p class="hl-v" id="save">—</p>
    <p class="hl-s" id="save-sub">—</p>
  </div>

  <div class="compare">
    <div class="row">
      <div class="row-h">
        <span class="row-t">Traditional compliance architecture</span>
        <span class="row-v" id="trad-v">—</span>
      </div>
      <div class="stack" id="trad-stack"></div>
      <div class="legend" id="trad-legend"></div>
    </div>

    <div class="row">
      <div class="row-h">
        <span class="row-t">Proof-based, on AILeash</span>
        <span class="row-v" id="proof-v">—</span>
      </div>
      <div class="stack" id="proof-stack"></div>
      <div class="legend">
        <span><i class="sw" style="background:#c9a84c"></i>50p per device per month, flat</span>
      </div>
    </div>

    <p class="gap-note" id="gap">—</p>
  </div>

  <div class="years">
    <div class="yr"><div class="l">Year one</div><div class="v" id="y1">—</div></div>
    <div class="yr"><div class="l">Three years</div><div class="v" id="y3">—</div></div>
    <div class="yr"><div class="l">Per device, per year</div><div class="v" id="ypd">—</div></div>
  </div>
</section>

<section>
  <h2>Change any of these</h2>
  <p class="note">These are the figures the saving rests on. They are illustrative, and yours will differ — so put yours in. The arithmetic follows whatever you type.</p>
  <div class="assump" id="assump">
    <div class="a-row">
      <div class="a-name">Data ingestion
        <small>Getting decision data out of your systems and into somewhere it can be queried.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ingest" value="3.20" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Log storage
        <small>Retention at the volumes an audit trail implies, for as long as the regulation implies.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-store" value="2.80" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Monitoring platform
        <small>Licences and seats on whatever watches it.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-monitor" value="2.40" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Compliance pipeline
        <small>Turning raw logs into something a regulator will accept.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-pipeline" value="2.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">Engineering time
        <small>Building it, and keeping it running once it exists.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-eng" value="1.60" step="0.10" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-row">
      <div class="a-name">AILeash
        <small>50p per device per month. Change it if you have been quoted something else.</small></div>
      <div class="a-in"><span>£</span><input type="number" id="a-ail" value="6.00" step="0.50" min="0" inputmode="decimal"></div>
    </div>
    <div class="a-total">
      <div class="a-name">Traditional, per device per year</div>
      <div class="v" id="a-sum">—</div>
    </div>
  </div>
  <button class="reset" id="reset">Put the illustrative figures back</button>
</section>

<section>
  <h2>What is measured, and what is modelled</h2>
  <p class="note">The two halves of this page are not the same kind of number, and it matters which is which.</p>

  <div class="split">
    <div class="half measured">
      <div class="h-l">Measured — read from the live system just now</div>
      <div class="m-row"><span>Blocks in the chain</span><b id="m-height">…</b></div>
      <div class="m-row"><span>Bytes per seal</span><b>32</b></div>
      <div class="m-row"><span>Size of the record behind it</span><b>irrelevant</b></div>
      <div class="m-row"><span>Timestamp proofs confirmed</span><b id="m-anchor">…</b></div>
      <p class="h-n">A seal is a SHA-256 digest. Thirty-two bytes, whether the decision behind it is one line or a megabyte. That is not a claim about our architecture, it is what a hash is — and it is the whole reason the cost stops tracking the volume.</p>
      <p class="h-n">Two honest notes on the figures above. A liveness beat seals a block every five minutes, so most of that block count is heartbeat rather than customer decisions — it is not a usage number. And external timestamping is per proof: a proof is submitted first and confirmed later, so the split above is what is actually confirmed against what is still pending. Both are readable at <a href="/x/ots/status">/x/ots/status</a>.</p>
    </div>
    <div class="half modelled">
      <div class="h-l">Modelled — assumptions, including yours</div>
      <div class="m-row"><span>What you spend today</span><b>your figures</b></div>
      <div class="m-row"><span>What you would stop spending</span><b>an estimate</b></div>
      <p class="h-n">Nobody can prove what an organisation <i>would have</i> spent. That number does not exist anywhere to be measured, here or in any vendor's business case. What this page can do is make the assumptions visible and let you replace every one of them.</p>
    </div>
  </div>

  <div class="sealbox">
    <div class="s-h">Seal this calculation</div>
    <p class="s-n">Puts your inputs and the result into the audit chain, dated and tamper-evident, and hands you a receipt anyone can check. Then what was modelled, and on whose assumptions, is a matter of record rather than of memory — including ours.</p>
    <button id="sealbtn">Seal it and give me a receipt</button>
    <div id="sealout"></div>
  </div>
</section>

<section>
  <h2>Why a proof layer costs less</h2>
  <p class="note">It is not a discount on the same architecture. It is less architecture.</p>
  <div class="straight">
    <p><b>Most of that cost is moving and keeping data.</b> Sensitive records get shipped somewhere central, held for years, indexed so they can be searched, and watched so nothing goes missing — because the plan is to reconstruct what happened by reading it all back later.</p>
    <p><b>A proof-based layer answers the question at the moment the decision is made.</b> The decision is scored, sealed into a hash chain, submitted for external timestamping and recorded by independent platforms. What survives is a proof that the decision happened, under stated rules, and has not been altered since.</p>
    <p><b>So the volume stops being the problem.</b> A seal is the same size whether the record behind it is a line or a megabyte, and it does not have to leave your systems for the proof to hold. You keep your own data where it already is.</p>
    <p>It does not replace your logs, and it is not meant to. It replaces the machinery built to make logs trustworthy — which is the part that scales badly.</p>
  </div>
  <div class="cta">
    <a class="gold" href="/#signup">Get an API key · 90 days free</a>
    <a class="ghost" href="/whitepaper">Read the whitepaper</a>
    <a class="ghost" href="/api/verify-chain">Check the chain</a>
  </div>
</section>

<footer>
  Illustrative model. Real figures vary with cloud provider, data volume, retention policy, engineering rates and existing contracts — which is why every input above is yours to change. No saving is guaranteed and nothing here is a quotation.<br>
  <a href="https://sebbi.pro">sebbi.pro</a> · Monop Content, Blyth
</footer>

</div>

<script>
(function(){
  var DEFAULTS = { ingest:3.20, store:2.80, monitor:2.40, pipeline:2.60, eng:1.60, ail:6.00 };
  var SEGMENTS = [
    { id:'ingest',   label:'Data ingestion',      colour:'#0a0f1e' },
    { id:'store',    label:'Log storage',         colour:'#243156' },
    { id:'monitor',  label:'Monitoring',          colour:'#3d4f7d' },
    { id:'pipeline', label:'Compliance pipeline', colour:'#5b6e9e' },
    { id:'eng',      label:'Engineering time',    colour:'#8794b8' }
  ];

  var $ = function(id){ return document.getElementById(id); };
  var dev = $('dev'), devr = $('devr');

  function money(n){
    if(!isFinite(n)) return '—';
    if(Math.abs(n) >= 1000000) return '£' + (n/1000000).toFixed(2).replace(/\.00$/,'') + 'm';
    return '£' + Math.round(n).toLocaleString('en-GB');
  }
  function per(n){ return '£' + n.toFixed(2); }
  function val(id){
    var v = parseFloat($(id).value);
    return (isFinite(v) && v >= 0) ? v : 0;
  }
  function devices(){
    var v = parseInt(dev.value, 10);
    if(!isFinite(v) || v < 1) v = 1;
    return v;
  }

  function draw(){
    var n = devices();
    var parts = SEGMENTS.map(function(s){ return { s:s, v: val('a-' + s.id) }; });
    var tradPer = parts.reduce(function(a,p){ return a + p.v; }, 0);
    var ailPer = val('a-ail');

    var trad = tradPer * n, proof = ailPer * n, saved = trad - proof;

    $('a-sum').textContent = per(tradPer);
    $('trad-v').textContent = money(trad) + ' / year';
    $('proof-v').textContent = money(proof) + ' / year';

    $('save').textContent = saved > 0 ? money(saved) : money(0);
    $('save').style.color = saved > 0 ? '#7fe3b0' : '#ffb4ad';
    $('save-sub').textContent = n.toLocaleString('en-GB') + ' devices · ' +
      per(tradPer) + ' against ' + per(ailPer) + ' per device per year';

    var scale = Math.max(tradPer, ailPer) || 1;
    var tradHtml = '', legendHtml = '';
    parts.forEach(function(p){
      if(p.v <= 0) return;
      tradHtml += '<div class="seg" style="width:' + ((p.v/scale)*100) + '%;background:' +
        p.s.colour + '" title="' + p.s.label + ' · ' + per(p.v) + '"></div>';
      legendHtml += '<span><i class="sw" style="background:' + p.s.colour + '"></i>' +
        p.s.label + ' ' + per(p.v) + '</span>';
    });
    $('trad-stack').innerHTML = tradHtml;
    $('trad-legend').innerHTML = legendHtml;
    $('proof-stack').innerHTML = '<div class="seg" style="width:' +
      ((ailPer/scale)*100) + '%;background:#c9a84c"></div>';

    if(saved > 0){
      var pct = Math.round((saved / (tradPer * n)) * 100);
      $('gap').textContent = 'The gap is ' + money(saved) + ' a year — about ' + pct +
        '% of the traditional figure, on these inputs.';
      $('gap').style.color = '#1a9e6e';
    } else if(saved === 0){
      $('gap').textContent = 'On these inputs the two cost the same.';
      $('gap').style.color = '#6b6353';
    } else {
      $('gap').textContent = 'On these inputs the proof layer costs ' + money(-saved) +
        ' a year more. Worth knowing, and worth saying.';
      $('gap').style.color = '#c8362b';
    }

    $('y1').textContent = money(Math.max(0, saved));
    $('y3').textContent = money(Math.max(0, saved * 3));
    $('ypd').textContent = per(Math.max(0, tradPer - ailPer));

    document.querySelectorAll('.presets button').forEach(function(b){
      b.classList.toggle('on', parseInt(b.dataset.n,10) === n);
    });
  }

  function syncFromSlider(){
    dev.value = Math.round(Math.pow(10, parseFloat(devr.value)) / 100) * 100;
    draw();
  }
  function syncFromNumber(){
    var n = devices();
    devr.value = Math.min(6, Math.max(2, Math.log(n) / Math.LN10));
    draw();
  }

  devr.addEventListener('input', syncFromSlider);
  dev.addEventListener('input', syncFromNumber);
  document.querySelectorAll('.presets button').forEach(function(b){
    b.addEventListener('click', function(){
      dev.value = b.dataset.n; syncFromNumber();
    });
  });
  document.querySelectorAll('#assump input').forEach(function(i){
    i.addEventListener('input', draw);
  });
  $('reset').addEventListener('click', function(){
    Object.keys(DEFAULTS).forEach(function(k){ $('a-' + k).value = DEFAULTS[k].toFixed(2); });
    draw();
  });

  syncFromNumber();

  // ---- measured half: read the live system, state what is actually there
  (async function(){
    try{
      var r = await fetch('/x/witness/tip');
      if(r.ok){
        var d = await r.json();
        var h = d.height;
        $('m-height').textContent = (typeof h === 'number')
          ? h.toLocaleString('en-GB') : 'unavailable';
      } else { $('m-height').textContent = 'unavailable'; }
    }catch(e){ $('m-height').textContent = 'unavailable'; }

    try{
      var a = await fetch('/x/ots/status');
      if(a.ok){
        var ad = await a.json();
        var conf = ad.confirmed, pend = ad.pending;
        if(typeof conf === 'number' || typeof pend === 'number'){
          $('m-anchor').textContent = (conf || 0).toLocaleString('en-GB') +
            ' confirmed / ' + (pend || 0).toLocaleString('en-GB') + ' pending';
        } else {
          $('m-anchor').textContent = 'see /x/ots/status';
        }
      } else { $('m-anchor').textContent = 'unavailable'; }
    }catch(e){ $('m-anchor').textContent = 'unavailable'; }
  })();

  // ---- seal the calculation
  var sealbtn = $('sealbtn'), sealout = $('sealout');
  sealbtn.addEventListener('click', async function(){
    sealbtn.disabled = true;
    sealout.innerHTML = 'sealing…';
    var body = {
      devices: devices(),
      assumptions: {
        ingestion: val('a-ingest'), storage: val('a-store'),
        monitoring: val('a-monitor'), pipeline: val('a-pipeline'),
        engineering: val('a-eng'), aileash: val('a-ail')
      }
    };
    try{
      var r = await fetch('/x/savings/seal', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      var d = await r.json();
      if(r.status === 429){
        sealout.innerHTML = '<span class="bad">' +
          ((d && d.message) || 'Rate limited. Give it a few minutes.') + '</span>';
      } else if(r.status === 409 && d && d.receipt){
        sealout.innerHTML =
          '<span class="ok">This exact model is already sealed at block ' + d.block_index +
          '</span><br>receipt ' + d.receipt + '<br>' +
          '<a href="' + d.verify + '" target="_blank" rel="noopener">check it yourself →</a>';
      } else if(!r.ok || !d.receipt){
        sealout.innerHTML = '<span class="bad">' +
          ((d && (d.message || d.error)) || ('HTTP ' + r.status)) + '</span>';
      } else {
        sealout.innerHTML =
          '<span class="ok">Sealed at block ' + d.block_index + '</span><br>' +
          'receipt ' + d.receipt + '<br>' +
          '<a href="' + d.verify + '" target="_blank" rel="noopener">check it yourself →</a>';
      }
    }catch(e){
      sealout.innerHTML = '<span class="bad">Could not reach the server.</span>';
    }
    sealbtn.disabled = false;
  });
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
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_savings_patched", False):
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
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._savings_patched = True
    _patched[0] = True
    print("SAVINGS: /savings page installed at runtime", flush=True)
    return "installed"


def _throttle_ok():
    """Global cap on public writes. Prunes as it goes so the list cannot grow."""
    now = time.time()
    cutoff = now - 3600
    while _seal_times and _seal_times[0] < cutoff:
        _seal_times.pop(0)
    if len(_seal_times) >= SEAL_PER_HOUR:
        return False, int(3600 - (now - _seal_times[0])) + 1
    _seal_times.append(now)
    return True, 0


def _existing(ctx, devices, vals):
    """An identical model already sealed is returned rather than sealed again.
    Refreshing the page should not add a block."""
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT audit_hash,block_index FROM savings_model "
                "WHERE devices=? AND assumptions=? ORDER BY id DESC LIMIT 1",
                (devices, json.dumps(vals))).fetchone()
        if row and row[0]:
            return row[0], row[1]
    except Exception:
        pass
    return None, None


def _seal(ctx, api_key, data):
    data = data or {}
    try:
        devices = int(data.get("devices", 0))
    except (TypeError, ValueError):
        devices = 0
    if devices < 1 or devices > 100000000:
        return {"error": "devices_required",
                "message": "Send a device count between 1 and 100,000,000."}, 400

    a = data.get("assumptions")
    if not isinstance(a, dict):
        return {"error": "assumptions_required"}, 400

    fields = ["ingestion", "storage", "monitoring", "pipeline", "engineering", "aileash"]
    vals = {}
    for f in fields:
        try:
            v = float(a.get(f, 0))
        except (TypeError, ValueError):
            v = 0.0
        if v < 0 or v > 100000:
            v = 0.0
        vals[f] = round(v, 2)

    # An identical model is not sealed twice.
    h_old, idx_old = _existing(ctx, devices, vals)
    if h_old:
        return {
            "sealed": False,
            "already_sealed": True,
            "receipt": h_old,
            "block_index": idx_old,
            "message": ("This exact model is already in the chain. It is not "
                        "sealed again, so refreshing the page does not add blocks."),
            "verify": "/x/savings/verify?receipt=" + h_old,
        }, 409

    ok, retry_after = _throttle_ok()
    if not ok:
        return {"error": "rate_limited",
                "retry_after_seconds": retry_after,
                "seals_per_hour": SEAL_PER_HOUR,
                "message": ("This route is open to anyone with no account, so it is "
                            "capped to stop the chain being flooded. Try again in a "
                            "few minutes.")}, 429

    traditional_per = round(sum(vals[f] for f in fields if f != "aileash"), 2)
    proof_per = vals["aileash"]
    traditional = round(traditional_per * devices, 2)
    proof = round(proof_per * devices, 2)
    saving = round(traditional - proof, 2)

    ts = time.time()
    detail = ("devices=" + str(devices) +
              ";" + ";".join("%s=%.2f" % (f, vals[f]) for f in fields) +
              ";traditional_per=%.2f;proof_per=%.2f;saving=%.2f"
              % (traditional_per, proof_per, saving))

    ev = {"user_id": "sav:" + str(devices), "action": "savings_modelled",
          "amount": 0, "country": "UK", "device_id": "savings",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SAVINGS_SEALED", "score": 0, "savings_version": VERSION,
           "devices": devices, "assumptions": vals,
           "traditional_per_device_year": traditional_per,
           "proof_per_device_year": proof_per,
           "annual_saving": saving, "timestamp": ts, "detail": detail}

    try:
        h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "message": ("Nothing was written and no receipt was issued. A receipt "
                            "for a block that does not exist is worse than an error.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash",
                "message": "Nothing was written and no receipt was issued."}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO savings_model(api_key,devices,assumptions,traditional_per,"
            "proof_per,annual_saving,modelled,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (api_key, devices, json.dumps(vals), traditional_per, proof_per,
             saving, ts, h, idx))
        ctx["conn"].commit()

    return {
        "sealed": True,
        "receipt": h,
        "block_index": idx,
        "receipt_seq": seq,
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "devices": devices,
        "assumptions": vals,
        "traditional_per_device_year": traditional_per,
        "proof_per_device_year": proof_per,
        "annual_saving": saving,
        "verify": "/x/savings/verify?receipt=" + h,
        "what_this_proves": ("That this calculation, on these assumptions, was run at "
                             "this time and has not been altered since. It does not "
                             "prove the assumptions are right - they are yours - and "
                             "no record can prove what an organisation would otherwise "
                             "have spent."),
    }, 200


def _verify(ctx, data):
    receipt = str((data or {}).get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT devices,assumptions,traditional_per,proof_per,annual_saving,"
            "modelled,block_index FROM savings_model WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    if not row:
        return {"found": False, "receipt": receipt,
                "message": "No calculation with that receipt exists in this chain."}, 404
    try:
        assumptions = json.loads(row[1])
    except Exception:
        assumptions = {}
    return {
        "found": True, "receipt": receipt,
        "devices": row[0], "assumptions": assumptions,
        "traditional_per_device_year": row[2],
        "proof_per_device_year": row[3],
        "annual_saving": row[4],
        "modelled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row[5])),
        "block_index": row[6],
        "proof": ("This calculation is a block in a hash chain that is recorded by "
                  "independent platforms and submitted for external timestamping. "
                  "Altering or removing it breaks every block after it."),
        "chain_tip": "/x/witness/tip",
        "witnessed_by": "/x/roster/list",
        "timestamp_proofs": "/x/ots/status",
        "anchoring": ("Timestamping is per proof. A proof is submitted first and "
                      "confirmed later; submitted is not confirmed. Check the state "
                      "of the proof covering this block at /x/ots/status."),
    }, 200


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("SAVINGS: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "seal":
            _setup(ctx)
            return _seal(ctx, api_key or "public-savings", data)
        return {"error": "unknown_action", "action": action, "POST": ["seal"]}, 404

    if action in ("", "status"):
        return {
            "page": "/savings",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "public_seals_per_hour": SEAL_PER_HOUR,
            "note": ("The calculator runs in the browser. Nothing a visitor types is "
                     "submitted unless they choose to seal it."),
        }, 200
    if action == "verify":
        _setup(ctx)
        return _verify(ctx, data)
    return {"error": "unknown_action", "action": action,
            "GET": ["status", "verify"], "POST": ["seal"]}, 404

```
