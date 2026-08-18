"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control - and those chains are
themselves anchored externally.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step, and re-anchor all of it. That is not a
technical exercise. That is a conspiracy, and it grows harder with every
platform that joins.

WHY observe IS OPEN
-------------------
A witnessing network that only accepts tips from account holders is not a
witnessing network, it is a customer list. Anyone must be able to hand us a
tip without asking permission. Unauthenticated observations are filed under
ANON_KEY, and the router meters them per client address.

NAMES, AND WHAT WE CAN ACTUALLY PROVE ABOUT THEM
------------------------------------------------
The chain name in a submission is self-declared. Anyone can post under any
name. We do not solve that with accounts, because accounts would make the
network closed. We solve it by publishing how strong each claim is, and by
remembering.

Two independent checks run on every submission, and NEITHER of them can
reject it. A submission is always sealed. What changes is what we say about it.

1. LIVENESS - is there a real chain behind this name?
   If the submission carries a url, we fetch it and compare what it serves
   to what was submitted.
     self-consistent  the url serves exactly the tip that was submitted
     live             the url serves a valid tip, but a different one. A busy
                      chain moves between submitting and our fetching, so this
                      is normal and honest, not a failure
     self-declared    no url, or we could not reach it, or it served nonsense

   WHY "self-consistent" AND NOT "confirmed" (changed in 1.2)
   ----------------------------------------------------------
   Both halves of this check come from the same party. The submitter tells us
   the tip and the submitter tells us where to look. Agreement between them
   establishes that the submitter's endpoint agrees with the submitter. That
   is self-consistency, not verification by anyone else.

   Up to v1.1 this value was written as "confirmed", which was the only
   approving word in a schema deliberately built without adjectives - and the
   permanent one, since it is sealed. The docstring carried the caveat and the
   field name contradicted it. Raised by Ishaan (Shango MID), correctly, and
   changed rather than defended.

   Blocks sealed before 1.2 say "confirmed" and cannot be altered - that is
   the property working as intended. Both values mean the same check. The
   legend on /x/witness/peers names both.

   It still proves the submitter operates a live chain producing that data. It
   does NOT prove they are who they say. Anyone running a real chain can point
   a stolen name at their own url and pass this check cleanly.

2. NAME BINDING - is this the same operator as last time?
   The first time a name is seen with a url we can reach, we record that url
   against the name. Every later submission under that name is compared.
     first-use      never seen this name before, binding recorded
     bound          same url as the first time. Same operator, consistently
     conflict       this name has been submitted from a different url than
                    the one it was first bound to

   A conflict is not proof of theft. Operators move hosts. But it is exactly
   the event anyone auditing the network needs to see, and it is recorded
   permanently in our chain rather than resolved quietly by us.

   This is what actually closes name theft. Check 1 alone does not.

SSRF
----
Check 1 makes our server fetch a url chosen by an anonymous stranger. Done
naively that is a hole considerably worse than the one it fixes: it would let
anyone use us to reach services on our own private network, and to bounce
traffic at a third party. So the fetcher only speaks http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that is
private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a small cap.

HONEST LIMITS
-------------
- Nobody can be forced to keep publishing. A witness network's guarantee is
  only as durable as its least persistent member, and that is not a property
  any amount of design can fix. Listed first because it is the one that
  actually bites.
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- Two colluding platforms witnessing only each other prove very little. The
  guarantee comes from breadth.
- This module does not verify a peer's chain is internally valid. It records
  what they claimed, when, and how well it stood up to checking.
- The liveness fetch resolves a hostname and then fetches it. An attacker
  controlling DNS could answer differently between those two steps. Closing
  that needs the connection pinned to the checked address, which is more
  machinery than this warrants today. It is written down rather than hidden.

    GET  /x/witness/tip                 our current tip, for peers to record
    POST /x/witness/observe             chain, tip, url - we seal their tip
                                        (peer accepted as an alias for chain;
                                         optional peer_ts or ts, epoch or ISO)
    GET  /x/witness/attest?peer=&tip=   did we witness this, and when
    GET  /x/witness/peers               who we witness, and how consistently
    GET  /x/witness/history?peer=       every tip we hold for that peer
"""

import ipaddress
import json
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.2"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# The liveness value written when a submitted url serves exactly the submitted
# tip. Was "confirmed" up to v1.1 - see the docstring. Kept as a constant so
# the value is stated in one place and every comparison uses it.
LIVENESS_MATCH = "self-consistent"

# Historical value for the same check, still present in blocks sealed before
# v1.2. Sealed blocks cannot be altered, so both are accepted wherever a
# comparison is made.
LIVENESS_MATCH_LEGACY = "confirmed"

# Values that count as "we reached a url and it served a valid tip", for the
# purpose of binding a name to that url.
LIVENESS_REACHED = (LIVENESS_MATCH, LIVENESS_MATCH_LEGACY, "live")

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("POST", "observe")}

# Observations arriving without a key are filed under this.
ANON_KEY = "public-witness"

# Liveness fetch limits. Deliberately tight - this runs on an anonymous
# request, so every one of these is also a denial-of-service control.
FETCH_TIMEOUT = 4
MAX_FETCH_BYTES = 65536
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witness_log(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,peer TEXT,tip TEXT,peer_ts REAL,observed REAL,audit_hash TEXT,block_index INTEGER,note TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer ON witness_log(api_key,peer)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_tip ON witness_log(tip)")

        # Added in 1.1. Existing rows keep NULL, which reads as unchecked -
        # correct, because they were.
        have = set()
        try:
            for row in c.execute("PRAGMA table_info(witness_log)").fetchall():
                have.add(row[1])
        except Exception:
            pass
        for col in ("url", "liveness", "name_status"):
            if col not in have:
                try:
                    c.execute("ALTER TABLE witness_log ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass

        # Name bindings are network-wide, not per api_key. A name means one
        # operator across the whole network or it means nothing.
        c.execute("CREATE TABLE IF NOT EXISTS witness_names(peer TEXT PRIMARY KEY,url TEXT,first_seen REAL,first_liveness TEXT)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _our_tip(ctx):
    with ctx["lock"]:
        r = ctx["conn"].execute("SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        return "GENESIS", None, 0
    return r[0], r[1], r[2]


def _tip(ctx, api_key):
    tip, ts, height = _our_tip(ctx)
    return {"tip": tip, "height": height, "sealed_at": _iso(ts),
            "witness_version": VERSION,
            "note": "Record this tip in your own chain. Hand us yours at /x/witness/observe and we will record it in ours.",
            "verify": "/api/verify-chain checks this chain end to end. /api/anchor-status shows the external timestamp."}, 200


# ----------------------------------------------------------------------
# liveness fetch - see the SSRF section above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction from a stranger to fetch a second url we
    never checked. Refuse rather than follow."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    """Resolve and refuse anything that isn't plainly on the public internet."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        raw = info[4][0]
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    host = parts.hostname
    if not host:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(host, port)


def _fetch_tip(url):
    """Returns (tip_or_None, note). Never raises."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, why
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "aileash-witness/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            if response.getcode() != 200:
                return None, "url answered %s" % response.getcode()
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, "url answered %s" % exc.code
    except Exception as exc:
        return None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, "response too large"
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None, "url did not return json"
    if not isinstance(data, dict):
        return None, "url did not return an object"
    # Field names vary between implementations and being strict about a name
    # we never published is a bug in the receiver, not in the peer.
    found = (data.get("tip") or data.get("hash") or data.get("head")
             or data.get("tip_sha256") or data.get("root")
             or data.get("current_tip") or "")
    found = str(found).strip().lower()
    if not HEX64.match(found):
        return None, "no valid tip at that url"
    return found, None


def _check_liveness(url, tip):
    """self-consistent / live / self-declared. Never rejects anything.

    Note what self-consistent means: the submitter told us the tip AND told us
    where to look, and the two agreed. That is the submitter agreeing with
    themselves. It is worth recording and it is not third-party verification.
    """
    if not url:
        return "self-declared", "no url supplied"
    found, why = _fetch_tip(url)
    if found is None:
        return "self-declared", why
    if found == tip:
        return LIVENESS_MATCH, ("the submitted url served exactly the submitted "
                                "tip - both sides of this check come from the "
                                "submitter, so this is self-consistency, not "
                                "third-party verification")
    return "live", "url serves a different tip (%s) - chain has moved on since submitting" % found[:16]


def _prior_unbound(ctx, peer):
    """How many times this name has been submitted with no bindable url.

    Exists because of a gap Ishaan (Shango MID) found: a submission without
    a url does not bind, so a recognisable name can be used honestly by its
    owner and then bound by somebody else who supplies a url first. The
    owner's later submission would read conflict, and they would be the one
    looking like the impostor.

    An anonymous endpoint cannot tell two claimants apart - there is nothing
    to bind to - so this does not prevent the squat. What it does is make it
    visible: a binding over a name that has been submitted before is
    recorded as such, permanently, in the sealed note. An auditor sees the
    name was not fresh when it was claimed.

    Detection rather than prevention. Prevention needs a credential, which
    is what the signed lane at /x/peer/submit is for.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM witness_log WHERE peer=? AND "
                "(url IS NULL OR url='')", (peer,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _check_name(ctx, peer, url, liveness):
    """first-use / bound / conflict / unbound.

    Only bind a name to a url we actually reached. Binding to an unreachable
    url would let someone reserve a name with an address that never answers.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT url,first_seen FROM witness_names WHERE peer=?", (peer,)).fetchone()

    if row and row[0]:
        if not url:
            return "unbound", "no url supplied; this name is bound to %s" % row[0]
        if url.strip() == row[0]:
            return "bound", None
        return "conflict", ("this name was first seen at %s and has now been submitted from %s"
                            % (row[0], url.strip()))

    # LIVENESS_REACHED, not a literal - renaming the match value in 1.2 would
    # otherwise have silently stopped first-use binding for exact matches.
    if url and liveness in LIVENESS_REACHED:
        prior = _prior_unbound(ctx, peer)
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT OR REPLACE INTO witness_names(peer,url,first_seen,first_liveness) VALUES(?,?,?,?)",
                (peer, url.strip(), time.time(), liveness))
            ctx["conn"].commit()
        note = "name now bound to %s" % url.strip()
        if prior:
            note += ("; WARNING: this name was submitted %d time(s) before "
                     "this binding with no url, so it was not a fresh name "
                     "when it was claimed - if that was not you, the earlier "
                     "submissions are permanently in this chain and so is "
                     "this warning" % prior)
        return "first-use", note

    return "unbound", ("no reachable url, so nothing to bind this name to. "
                       "This name remains claimable by anyone who submits it "
                       "with a reachable url - see liveness_vocabulary")


# ----------------------------------------------------------------------
# observe
# ----------------------------------------------------------------------

def _observe(ctx, api_key, data):
    # The published standard calls this field "chain"; earlier internal
    # callers used "peer". Accept either. A receiver being strict about
    # field names it never published is a bug in the receiver.
    peer = str(data.get("chain") or data.get("peer") or "").strip().lower()
    if not peer or len(peer) > 80:
        return {"error": "chain_required",
                "message": "A short stable identifier - a domain works well.",
                "field": "chain (peer also accepted)"}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": "A tip is 64 hex characters - a SHA-256 chain head."}, 400

    url = data.get("url")
    url = str(url).strip() if url else ""
    if len(url) > 500:
        url = ""

    # Time the peer claims it sealed at. Epoch or ISO, either field name.
    # Carry on without it - supporting detail, not the evidence.
    peer_ts = data.get("peer_ts", data.get("ts"))
    if peer_ts is not None:
        try:
            peer_ts = float(peer_ts)
        except (TypeError, ValueError):
            try:
                s = str(peer_ts).strip().replace("Z", "+00:00")
                peer_ts = datetime.fromisoformat(s).timestamp()
            except Exception:
                peer_ts = None

    liveness, live_note = _check_liveness(url, tip)
    name_status, name_note = _check_name(ctx, peer, url, liveness)

    ts = time.time()
    notes = []

    with ctx["lock"]:
        prev = ctx["conn"].execute("SELECT tip,observed FROM witness_log WHERE api_key=? AND peer=? ORDER BY id DESC LIMIT 1", (api_key, peer)).fetchone()
        seen = ctx["conn"].execute("SELECT observed FROM witness_log WHERE api_key=? AND peer=? AND tip=? LIMIT 1", (api_key, peer, tip)).fetchone()

    if seen:
        notes.append("tip already witnessed at " + str(_iso(seen[0])) + " - chain has not advanced, or history was replayed")
    elif prev and prev[0] == tip:
        notes.append("unchanged since last observation")
    if live_note:
        notes.append(live_note)
    if name_note:
        notes.append(name_note)
    note = "; ".join(notes)

    # The verification result is sealed alongside the tip. If we later claim a
    # submission was self-consistent, the chain has to agree.
    detail = ("peer=" + peer + ";tip=" + tip + ";url=" + (url or "-") +
              ";liveness=" + liveness + ";name=" + name_status +
              ";peer_ts=" + str(peer_ts) + (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts,
           "liveness": liveness, "name_status": name_status, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note,url,liveness,name_status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (api_key, peer, tip, peer_ts, ts, h, idx, note or None,
                             url or None, liveness, name_status))
        ctx["conn"].commit()

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "liveness": liveness, "name_status": name_status,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": "Your tip is now inside a chain you do not control, and ours is anchored externally."}
    if note:
        out["flag"] = note
    out["witness_version"] = VERSION
    out["liveness_vocabulary"] = _vocab(liveness)
    out["name_vocabulary"] = _name_vocab(name_status)
    if liveness == "self-declared":
        out["advice"] = "Send a url serving your current tip and this becomes checkable by anyone rather than taken on your word."
    if name_status == "conflict":
        out["warning"] = "Sealed, and flagged. This name has been used from a different address before. That discrepancy is now permanent in our chain."
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": "We hold no record of this tip from this peer."}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "liveness": rows[0][4] or "unchecked",
            "liveness_vocabulary": _vocab(rows[0][4]),
            "name_status": rows[0][5] or "unchecked",
            "name_vocabulary": _name_vocab(rows[0][5]),
            "submitted_url": rows[0][6],
            "what_this_proves": "That this tip was handed to us at this time and sealed into our chain. Liveness records whether a url the submitter supplied served the same tip the submitter sent - self-consistency, not verification by us. Neither proves the submitter's identity.",
            "proof": "This observation is a block in our chain. Altering or removing it breaks every block after it, and our chain is externally anchored."}, 200


def _vocab(liveness):
    """Make the vocabulary travel with the value.

    The legend on /x/witness/peers reconciles self-consistent and confirmed
    for whoever reads the legend. Sealed blocks travel and legends do not:
    anyone quoting a block elsewhere carries the word without the
    reconciliation attached. Raised by Ishaan (Shango MID) after hitting the
    same thing on his own register - the correction reached the page and not
    the metadata that gets shared with the link.

    So any route that returns an observation returns what the word means at
    the point it is read, rather than pointing at a legend that may not
    follow it. The sealed block already carries witness_version in its
    result; this makes the meaning explicit rather than requiring the reader
    to know which version renamed what.

    General form worth keeping: a name a reader treats as documentation may
    be a value the code branches on, and the two roles are invisible to each
    other from outside.
    """
    if liveness == LIVENESS_MATCH:
        return ("The submitted url served exactly the submitted tip. Both "
                "halves came from the submitter, so this records "
                "self-consistency - NOT verification by us or any third "
                "party. Written as '%s' from witness v1.2 onward."
                % LIVENESS_MATCH)
    if liveness == LIVENESS_MATCH_LEGACY:
        return ("The same check as '%s', under the name used before witness "
                "v1.2. It was renamed because the old name implied "
                "third-party verification that the check does not perform. "
                "Sealed blocks cannot be altered, so this record keeps the "
                "original word." % LIVENESS_MATCH)
    if liveness == "live":
        return ("The url served a valid but different tip. A chain that "
                "moves between submitting and our fetching is the normal "
                "case, not a failure.")
    if liveness == "self-declared":
        return ("No url was supplied, or we could not reach it. Taken on "
                "the submitter's word and checked by nobody.")
    return "Not checked. Recorded before liveness checking existed."


def _name_vocab(name_status):
    """What the name status means, and what it costs.

    Travels with the value for the same reason liveness_vocabulary does.
    The unbound entry states the exposure plainly rather than leaving a
    submitter to work it out: choosing the accurate weaker liveness status
    by withholding a url also leaves the name claimable, and nobody should
    have to discover that coupling by being squatted.
    """
    if name_status == "first-use":
        return ("First time this name was seen with a reachable url, so the "
                "name is now bound to it network-wide. Any later submission "
                "under this name from a different address records as "
                "conflict, permanently.")
    if name_status == "bound":
        return ("Submitted from the same url this name was first bound to. "
                "Same operator, consistently.")
    if name_status == "conflict":
        return ("This name has been submitted from a different address than "
                "the one it was first bound to. Not proof of theft - "
                "operators move hosts - but it is the event an auditor needs "
                "to see, and it is permanent.")
    if name_status == "unbound":
        return ("No reachable url, so there is nothing to bind this name to. "
                "IMPORTANT: an unbound name stays claimable. Whoever submits "
                "it next WITH a reachable url takes the binding, and your "
                "own later submission would then read conflict. We cannot "
                "prevent that - an open endpoint has no way to tell two "
                "claimants apart - but a binding placed over a name that was "
                "submitted before is recorded as such. If the name matters, "
                "either submit with a url serving your tip, or use the "
                "signed lane at /x/peer/submit where a credential binds the "
                "name to you rather than to an address.")
    return "Not checked."


def _peers(ctx, api_key):
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()
        latest = {}
        conflicts = {}
        bindings = {}
        for p, live, name in ctx["conn"].execute("SELECT peer,liveness,name_status FROM witness_log ORDER BY id ASC").fetchall():
            latest[p] = (live, name)
            if name == "conflict":
                conflicts[p] = conflicts.get(p, 0) + 1
        for p, u in ctx["conn"].execute("SELECT peer,url FROM witness_names").fetchall():
            bindings[p] = u

    t = time.time()
    peers = []
    for p, n, first, last, distinct in rows:
        hours = round((t - last) / 3600, 1)
        live, name = latest.get(p, (None, None))
        entry = {"peer": p, "observations": n, "distinct_tips": distinct,
                 "first_seen": _iso(first), "last_seen": _iso(last),
                 "hours_since_last": hours,
                 "status": ("current" if hours < 6 else "stale" if hours < 48 else "silent"),
                 "liveness": live or "unchecked",
                 "name_status": name or "unchecked",
                 "bound_to": bindings.get(p)}
        if conflicts.get(p):
            entry["name_conflicts"] = conflicts[p]
        peers.append(entry)
    return {"count": len(peers), "peers": peers,
            "what_this_list_is": ("Parties that have submitted a tip to this "
                                  "deployment. Being listed here is not "
                                  "membership of anything, not endorsement of "
                                  "anything sealed in this chain, and implies "
                                  "no relationship beyond having sent a hash."),
            "legend": {
                "self-consistent": "the submitted url served exactly the submitted tip. Both halves came from the submitter, so this is self-consistency - NOT verification by us or any third party",
                "confirmed": "the same check, under the name used before witness v1.2. Sealed blocks cannot be altered, so older records still say this",
                "live": "a url served a valid but different tip - a moving chain, which is normal",
                "self-declared": "no url, or we could not reach it. Taken on their word",
                "first-use": "first time this name was seen; now bound to that url",
                "bound": "same url as the first time this name appeared",
                "conflict": "this name has been submitted from more than one address",
                "unbound_costs_you_the_name": (
                    "A submission with no reachable url does not bind the "
                    "name. Whoever submits it next with a url takes the "
                    "binding. Choosing the accurate weaker liveness status "
                    "therefore leaves the name claimable - a coupling worth "
                    "knowing before it bites. The signed lane at "
                    "/x/peer/submit binds a name to a credential instead of "
                    "an address."),
            },
            "note": "Silent peers are visible by design. A network you cannot audit is not a network. Nothing here proves identity - it shows how well each claim stood up to checking."}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note,liveness,name_status,url FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT 500", (api_key, peer)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows),
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4], "liveness": r[5] or "unchecked",
                              "name_status": r[6] or "unchecked",
                              "url": r[7]} for r in rows],
            "note": "If this peer ever presents a history whose tips do not match these, the divergence is provable."}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "observe":
            # No key needed. Anonymous submissions are partitioned under
            # ANON_KEY so they never mix with a customer's own witness log.
            return _observe(ctx, api_key or ANON_KEY, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
    else:
        if action == "tip":
            return _tip(ctx, api_key)
        if action == "peers":
            return _peers(ctx, api_key)
        if action == "attest":
            return _attest(ctx, api_key, data)
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404
