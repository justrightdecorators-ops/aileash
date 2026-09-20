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
