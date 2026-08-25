"""
Mutual witness network - /x/witness/<action>

THE PROBLEM
-----------
Every compliance vendor, this one included, holds the evidence about its own
conduct. A hash chain stops anyone else altering it. It does not stop the
operator rebuilding the whole chain from scratch and presenting the result as
history. External anchoring narrows that to "you cannot rewrite anything older
than your last CONFIRMED anchor" - which is good, and still not enough.

WHAT THIS DOES
--------------
Platforms witness each other.

Each platform periodically hands its current chain tip to its peers. Each peer
seals that tip into its OWN chain. From that moment the first platform's
history is recorded inside chains it does not control.

To rewrite your own history now, you would need every peer who witnessed you
to rewrite theirs too, in step. That is not a technical exercise. That is a
conspiracy, and it grows harder with every platform that joins.

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
     self-declared    no url, or we could not reach it, or we reached it and
                      it did not serve a valid tip

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

REACHED IS NOT THE SAME AS PARSED (corrected in 1.4)
-----------------------------------------------------
Up to v1.3 a submission whose url answered with HTML sealed this flag:

    "url did not return json; no reachable url, so nothing to bind this
     name to"

The first clause is true. The second is false. The url was reachable - it
answered, over TLS, with a body. What the check established was that the body
was not JSON, and it then asserted a conclusion about reachability that it had
never tested. That statement is sealed and cannot be withdrawn.

It is the same failure as the "confirmed" rename one field over: wording that
claimed more than the check performed. That it happened again, in a file whose
whole purpose is claim discipline, is the point rather than the excuse. Raised
by Ishaan (Shango MID) against block 1600, correctly.

Two things changed:

  - reachability is now its own recorded value, not something inferred from a
    parse failure. REACHED_YES, REACHED_NO and REACHED_UNTRIED are sealed
    alongside liveness, so "we got a response we could not use" and "we never
    got a response" stop being the same record.

  - no message in this module asserts unreachability unless the fetch actually
    failed to connect. Where a url answered and was unusable, the record says
    exactly that.

Older blocks keep their original wording, including the false clause. They are
not editable and pretending otherwise would defeat the point of sealing them.
What this version changes is what gets written from here on.

WHY EVERY READER-FACING PHRASE LIVES IN ONE BLOCK (added in 1.3)
-----------------------------------------------------------------
Four separate corrections in one week were all the same job: find the
sentence, change the sentence, and hope there is not a second copy of it
somewhere else in the file. There usually was. A word that goes into a sealed
record, or into a response a peer will quote back at us, is not incidental
prose - it is part of the interface, and it needs one home.

Everything a reader sees now lives in VOCABULARY and MESSAGES at the top of
this file. The code below references those keys and never spells a claim out
inline. The next peer who finds an overstatement costs one line in one place,
and the wording can be reviewed on its own without reading the logic.

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
- ANCHORING IS PER-PROOF, NOT A PROPERTY OF THE CHAIN. Up to v1.2 this module
  told readers "our chain is externally anchored" as a standing fact. It is
  not. A proof is submitted to the OpenTimestamps calendars immediately, and
  only becomes Bitcoin-confirmed once it has been upgraded and independently
  verified. A given block is anchored when a proof covering it has confirmed,
  and not before. Raised by Philip Pinol (PRAXIS / ThePraesidium.ai) against
  block 846, correctly. Every route now points at /x/ots/status rather than
  asserting a state this module cannot see.
- Witnessing proves a tip EXISTED at a time. It says nothing about whether the
  records behind it are true or complete. Garbage sealed on time is still
  garbage.
- Two colluding platforms witnessing only each other prove very little. The
  guarantee comes from breadth.
- This module does not verify a peer's chain is internally valid. It records
  what they claimed, when, and how well it stood up to checking.
- REACHED_YES means we received an HTTP response. It does not mean the
  endpoint is the peer's, that it is healthy, or that anything it served is
  true. It is the narrowest possible fact and is recorded as such.
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
    GET  /x/witness/spec                the protocol, in four calls
    GET  /x/witness/history?peer=       every tip we hold for that peer (keyed)
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

VERSION = "1.4"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# ----------------------------------------------------------------------
# values that get sealed
#
# Anything in this section is written into a permanent record AND compared
# against in code. Both roles are invisible to each other from outside, which
# is exactly how renaming the match value in 1.2 silently broke first-use
# binding. One constant, one meaning, every comparison through the name.
# ----------------------------------------------------------------------

# The liveness value written when a submitted url serves exactly the submitted
# tip. Was "confirmed" up to v1.1 - see the docstring.
LIVENESS_MATCH = "self-consistent"

# Historical value for the same check, still present in blocks sealed before
# v1.2. Sealed blocks cannot be altered, so both are accepted wherever a
# comparison is made.
LIVENESS_MATCH_LEGACY = "confirmed"

# The url answered with a valid tip, but a different one. A moving chain.
LIVENESS_MOVED = "live"

# No url, unreachable url, or a url that answered without a valid tip.
LIVENESS_NONE = "self-declared"

# Values that count as "we reached a url and it served a valid tip", for the
# purpose of binding a name to that url.
LIVENESS_REACHED = (LIVENESS_MATCH, LIVENESS_MATCH_LEGACY, LIVENESS_MOVED)

# Reachability. Added in 1.4 and deliberately separate from liveness, because
# conflating the two is what put a false statement in a sealed block. This
# records only whether an HTTP response arrived - not what was in it.
REACHED_YES = "reached"
REACHED_NO = "not-reached"
REACHED_UNTRIED = "not-attempted"

NAME_FIRST = "first-use"
NAME_BOUND = "bound"
NAME_CONFLICT = "conflict"
NAME_UNBOUND = "unbound"

# ----------------------------------------------------------------------
# everything a reader sees
#
# Nothing below this block spells out a claim inline. If a phrase needs
# correcting it is corrected here, once, and every route that returns it
# changes together.
# ----------------------------------------------------------------------

# Said wherever this module would previously have asserted that the chain is
# anchored. It is not this module's fact to assert - anchoring state lives in
# the OTS proofs and only /x/ots/status can see it.
ANCHOR_NOTE = (
    "Separately from the hash chain: this deployment submits its chain to the "
    "OpenTimestamps calendars for Bitcoin anchoring. Submission is not "
    "confirmation. A block is Bitcoin-confirmed only once a proof covering it "
    "has been upgraded and verified with a standard OpenTimestamps client. "
    "Check /x/ots/status for the state of the proof covering this block. "
    "Until that proof confirms, the guarantee here is the hash chain and not "
    "Bitcoin."
)

VOCABULARY = {
    LIVENESS_MATCH: (
        "The submitted url served exactly the submitted tip. Both halves came "
        "from the submitter, so this records self-consistency - NOT "
        "verification by us or any third party. Written as '%s' from witness "
        "v1.2 onward." % LIVENESS_MATCH),
    LIVENESS_MATCH_LEGACY: (
        "The same check as '%s', under the name used before witness v1.2. It "
        "was renamed because the old name implied third-party verification "
        "that the check does not perform. Sealed blocks cannot be altered, so "
        "this record keeps the original word." % LIVENESS_MATCH),
    LIVENESS_MOVED: (
        "The url served a valid but different tip. A chain that moves between "
        "submitting and our fetching is the normal case, not a failure."),
    LIVENESS_NONE: (
        "No usable tip was obtained. That covers three different situations - "
        "no url was supplied, a url was supplied and could not be reached, or "
        "a url was reached and did not serve a valid tip. Read the "
        "'reachability' field beside this one to see which. Before witness "
        "v1.4 those three were reported identically and the flag text "
        "asserted unreachability in all of them, which was wrong in the third "
        "case and is sealed in blocks from that period."),
    None: "Not checked. Recorded before liveness checking existed.",
}

# Added in 1.4. Reachability answers one question and nothing else: did an
# HTTP response arrive. It says nothing about the content, the health of the
# endpoint, or who operates it.
REACH_VOCABULARY = {
    REACHED_YES: (
        "An HTTP response was received from the submitted url. That is the "
        "whole claim. It does not mean the response was usable, that the "
        "endpoint belongs to the submitter, or that anything it served is "
        "true - only that the address answered."),
    REACHED_NO: (
        "A url was supplied and no HTTP response was received - refused, "
        "timed out, would not resolve, or was refused by our own address "
        "rules before any request was made."),
    REACHED_UNTRIED: (
        "No url was supplied, so nothing was attempted. Distinct from "
        "'not-reached', which means we tried and failed."),
    None: (
        "Not recorded. This observation predates witness v1.4, when "
        "reachability and parseability were reported as one value."),
}

NAME_VOCABULARY = {
    NAME_FIRST: (
        "First time this name was seen with a url serving a valid tip, so the "
        "name is now bound to it network-wide. Any later submission under this "
        "name from a different address records as conflict, permanently."),
    NAME_BOUND: (
        "Submitted from the same url this name was first bound to. Same "
        "operator, consistently."),
    NAME_CONFLICT: (
        "This name has been submitted from a different address than the one "
        "it was first bound to. Not proof of theft - operators move hosts - "
        "but it is the event an auditor needs to see, and it is permanent."),
    NAME_UNBOUND: (
        "No url served a valid tip, so there is nothing to bind this name to. "
        "Note that this covers a url we never reached AND a url that answered "
        "with something we could not use - check the 'reachability' field to "
        "see which happened here. "
        "IMPORTANT: an unbound name stays claimable. Whoever submits it next "
        "WITH a url serving a valid tip takes the binding, and your own later "
        "submission would then read conflict. We cannot prevent that - an "
        "open endpoint has no way to tell two claimants apart - but a binding "
        "placed over a name that was submitted before is recorded as such. If "
        "the name matters, either submit with a url serving your tip, or use "
        "the signed lane at /x/peer/submit."),
    None: "Not checked.",
}

# What the signed lane does and does not bind. Agreed wording, unsoftened:
# a shared secret is held by both parties, so it excludes third parties and
# does not exclude the operator. Stated here rather than left for a peer to
# work out from the word "signed".
SIGNED_LANE_NOTE = (
    "The signed lane at /x/peer/submit binds a name to knowledge of a shared "
    "secret, not to control of an address. Because the operator of this "
    "deployment holds the same secret, it closes third-party submission under "
    "your name and does not close operator submission under your name. That "
    "is a normal property of HMAC and it is stated rather than implied."
)

MESSAGES = {
    "tip_note": (
        "Record this tip in your own chain. Hand us yours at "
        "/x/witness/observe and we will record it in ours."),
    "tip_verify": (
        "/api/verify-chain checks this chain end to end. /x/ots/status shows "
        "the state of each external timestamp proof."),
    "observe_ok": (
        "Your tip is now inside a chain you do not control. What that block "
        "carries is stated in what_this_proves - it is a record that this "
        "value was handed to us at this time, and nothing about whether the "
        "records behind it are true."),
    "observe_advice": (
        "Send a url serving your current tip and this becomes checkable by "
        "anyone rather than taken on your word. Read name_vocabulary first: "
        "withholding a url also leaves the name claimable."),
    "observe_advice_unusable": (
        "Your url answered but did not serve a tip we could read, so there is "
        "nothing to bind the name to. We accept a tip as 64 lowercase hex in "
        "a JSON object under any of the field names listed at "
        "/x/witness/spec. This is a parsing outcome and not a statement that "
        "your endpoint is down - the reachability field records that "
        "separately."),
    "observe_conflict": (
        "Sealed, and flagged. This name has been used from a different "
        "address before. That discrepancy is now permanent in our chain."),
    "attest_proves": (
        "That this tip was handed to us at this time and sealed into our "
        "chain. Liveness records whether a url the submitter supplied served "
        "the same tip the submitter sent - self-consistency, not verification "
        "by us. Reachability records only whether that url answered at all. "
        "Neither proves the submitter's identity."),
    "attest_proof": (
        "This observation is a block in our chain. Altering or removing it "
        "breaks every block after it, and that is checkable by anyone at "
        "/api/verify-chain. " + ANCHOR_NOTE),
    "list_is": (
        "Parties that have submitted a tip to this deployment. Being listed "
        "here is not membership of anything, not endorsement of anything "
        "sealed in this chain, and implies no relationship beyond having sent "
        "a hash."),
    "list_note": (
        "Silent peers are visible by design. A network you cannot audit is "
        "not a network. Nothing here proves identity - it shows how well each "
        "claim stood up to checking."),
    "history_note": (
        "If this peer ever presents a history whose tips do not match these, "
        "the divergence is provable."),
    "chain_required": "A short stable identifier - a domain works well.",
    "invalid_tip": "A tip is 64 hex characters - a SHA-256 chain head.",
    "not_witnessed": "We hold no record of this tip from this peer.",
}

LEGEND = {
    LIVENESS_MATCH: VOCABULARY[LIVENESS_MATCH],
    LIVENESS_MATCH_LEGACY: VOCABULARY[LIVENESS_MATCH_LEGACY],
    LIVENESS_MOVED: VOCABULARY[LIVENESS_MOVED],
    LIVENESS_NONE: VOCABULARY[LIVENESS_NONE],
    REACHED_YES: REACH_VOCABULARY[REACHED_YES],
    REACHED_NO: REACH_VOCABULARY[REACHED_NO],
    REACHED_UNTRIED: REACH_VOCABULARY[REACHED_UNTRIED],
    NAME_FIRST: NAME_VOCABULARY[NAME_FIRST],
    NAME_BOUND: NAME_VOCABULARY[NAME_BOUND],
    NAME_CONFLICT: NAME_VOCABULARY[NAME_CONFLICT],
    NAME_UNBOUND: NAME_VOCABULARY[NAME_UNBOUND],
    "reached_is_not_parsed": (
        "Reachability and liveness answer different questions and are "
        "recorded separately from witness v1.4. A url can be reached and "
        "still serve nothing we can use; before v1.4 both were reported as "
        "though the url could not be reached, which was false in that case "
        "and is sealed permanently in blocks from that period."),
    "unbound_costs_you_the_name": (
        "A submission with no url serving a valid tip does not bind the name. "
        "Whoever submits it next with one takes the binding. Choosing the "
        "accurate weaker liveness status therefore leaves the name claimable "
        "- a coupling worth knowing before it bites."),
    "signed_lane": SIGNED_LANE_NOTE,
    "anchoring": ANCHOR_NOTE,
}

# Routes that need no API key. A third party must be able to check the
# network without holding an account, or the claim that anyone can audit
# it is not true.
PUBLIC = {("GET", "attest"), ("GET", "peers"), ("GET", "tip"),
          ("GET", "spec"), ("POST", "observe")}

# Observations arriving without a key are filed under this.
ANON_KEY = "public-witness"

# Liveness fetch limits. Deliberately tight - this runs on an anonymous
# request, so every one of these is also a denial-of-service control.
FETCH_TIMEOUT = 4
MAX_FETCH_BYTES = 65536
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# Field names other implementations serve their tip under. Being strict about
# a name we never published is a bug in the receiver, not in the peer. Kept
# identical to the list mutual.py advertises.
TIP_FIELDS = ("tip", "hash", "head", "tip_sha256", "root", "current_tip",
              "chain_tip", "latest")

MAX_HISTORY = 500

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

        # Added in 1.1, extended in 1.4 with reachability. Existing rows keep
        # NULL, which reads as unrecorded - correct, because it was not
        # recorded separately before 1.4.
        have = set()
        try:
            for row in c.execute("PRAGMA table_info(witness_log)").fetchall():
                have.add(row[1])
        except Exception:
            pass
        for col in ("url", "liveness", "name_status", "reachability"):
            if col not in have:
                try:
                    c.execute("ALTER TABLE witness_log ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass

        # Added in 1.3. /x/witness/peers previously read every row in the
        # table on every call to work out each peer's latest status. At 700
        # observations that is wasteful; at 70,000 it is a problem. This index
        # lets the same answer come from a grouped query.
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer_id ON witness_log(peer,id)")
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
            "note": MESSAGES["tip_note"],
            "verify": MESSAGES["tip_verify"],
            "anchoring": ANCHOR_NOTE}, 200


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


def _norm_url(url):
    """Normalise a url for COMPARISON only. The raw string is what gets stored
    and shown.

    Added in 1.3. Binding compared raw strings, so the same endpoint submitted
    as https://x.test/w and https://X.test/w/ recorded a permanent conflict
    against an operator who had done nothing wrong. A conflict is the loudest
    thing this module can say about somebody and it cannot be withdrawn, so it
    should fire on a genuinely different address and not on a trailing slash.

    Deliberately conservative: case on scheme and host, the default port, and
    one trailing slash. Path case, query order and anything else still count
    as different, because they can be.
    """
    if not url:
        return ""
    raw = url.strip()
    try:
        p = urlparse(raw)
    except Exception:
        return raw.lower()
    scheme = (p.scheme or "").lower()
    host = (p.hostname or "").lower()
    if not scheme or not host:
        return raw.lower()
    port = p.port
    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        port = None
    netloc = host + (":%d" % port if port else "")
    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    out = scheme + "://" + netloc + path
    if p.query:
        out += "?" + p.query
    return out


def _fetch_tip(url):
    """Returns (tip_or_None, note, reachability). Never raises.

    Changed in 1.4 to report reachability separately. Every path that used to
    return None with a note now also says whether an HTTP response actually
    arrived, because "we could not connect" and "it answered with HTML" are
    different facts and reporting them as one put a false statement in a
    sealed block.
    """
    ok, why = _url_allowed(url)
    if not ok:
        # Refused before any request was made, so nothing was attempted
        # against the address itself.
        return None, why, REACHED_NO
    request = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "aileash-witness/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            code = response.getcode()
            if code != 200:
                # It answered. That is reached, whatever the status.
                return None, "url answered %s" % code, REACHED_YES
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # An HTTP error IS a response. The server was reached.
        return None, "url answered %s" % exc.code, REACHED_YES
    except Exception as exc:
        return None, "could not reach url (%s)" % type(exc).__name__, REACHED_NO
    if len(body) > MAX_FETCH_BYTES:
        return None, "url answered, response too large to read", REACHED_YES
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None, "url answered but did not return json", REACHED_YES
    if not isinstance(data, dict):
        return None, "url answered but did not return an object", REACHED_YES
    found = ""
    for field in TIP_FIELDS:
        value = data.get(field)
        if value:
            found = str(value).strip().lower()
            break
    if not HEX64.match(found or ""):
        return None, "url answered but served no valid tip", REACHED_YES
    return found, None, REACHED_YES


def _check_liveness(url, tip):
    """Returns (liveness, note, reachability). Never rejects anything.

    Note what self-consistent means: the submitter told us the tip AND told us
    where to look, and the two agreed. That is the submitter agreeing with
    themselves. It is worth recording and it is not third-party verification.
    """
    if not url:
        return LIVENESS_NONE, "no url supplied", REACHED_UNTRIED
    found, why, reached = _fetch_tip(url)
    if found is None:
        return LIVENESS_NONE, why, reached
    if found == tip:
        return LIVENESS_MATCH, ("the submitted url served exactly the submitted "
                                "tip - both sides of this check come from the "
                                "submitter, so this is self-consistency, not "
                                "third-party verification"), reached
    return LIVENESS_MOVED, ("url serves a different tip (%s) - chain has moved "
                            "on since submitting" % found[:16]), reached


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
    is what the signed lane at /x/peer/submit is for - within the limit
    stated in SIGNED_LANE_NOTE.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM witness_log WHERE peer=? AND "
                "(url IS NULL OR url='')", (peer,)).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _check_name(ctx, peer, url, liveness, reachability):
    """first-use / bound / conflict / unbound.

    Only bind a name to a url that served a valid tip. Binding to a url that
    never produced one would let someone reserve a name with an address that
    answers with anything at all.

    Corrected in 1.4: the unbound message used to say "no reachable url",
    which was false whenever a url answered and simply was not usable. It now
    reports what was actually established, and the reachability value is
    carried in beside it rather than inferred.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT url,first_seen FROM witness_names WHERE peer=?", (peer,)).fetchone()

    if row and row[0]:
        if not url:
            return NAME_UNBOUND, "no url supplied; this name is bound to %s" % row[0]
        if _norm_url(url) == _norm_url(row[0]):
            if url.strip() != row[0]:
                return NAME_BOUND, ("same address as the binding, written "
                                    "differently (bound as %s, submitted as "
                                    "%s)" % (row[0], url.strip()))
            return NAME_BOUND, None
        return NAME_CONFLICT, ("this name was first seen at %s and has now been submitted from %s"
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
        return NAME_FIRST, note

    # Say only what was established. Three different situations reach here and
    # they are no longer described as though they were one.
    if not url:
        why = "no url was supplied, so there is nothing to bind this name to"
    elif reachability == REACHED_YES:
        why = ("the url answered but served no tip we could read, so there is "
               "nothing to bind this name to. This is a parsing outcome, not "
               "a statement that the endpoint is unreachable")
    else:
        why = ("the url could not be reached, so there is nothing to bind "
               "this name to")
    return NAME_UNBOUND, (why + ". This name remains claimable by anyone who "
                          "submits it with a url serving a valid tip - see "
                          "name_vocabulary")


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
                "message": MESSAGES["chain_required"],
                "field": "chain (peer also accepted)"}, 400
    tip = str(data.get("tip", "")).strip().lower()
    if not HEX64.match(tip):
        return {"error": "invalid_tip", "message": MESSAGES["invalid_tip"]}, 400

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

    liveness, live_note, reachability = _check_liveness(url, tip)
    name_status, name_note = _check_name(ctx, peer, url, liveness, reachability)

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
              ";liveness=" + liveness + ";reachability=" + reachability +
              ";name=" + name_status +
              ";peer_ts=" + str(peer_ts) + (";note=" + note if note else ""))
    ev = {"user_id": "wit:" + peer, "action": "witness_observed", "amount": 0,
          "country": "UK", "device_id": "witness", "anomaly": 0, "device_risk": 0}
    res = {"decision": "WITNESS_SEALED", "score": 0, "witness_version": VERSION,
           "peer": peer, "peer_tip": tip, "timestamp": ts,
           "liveness": liveness, "reachability": reachability,
           "name_status": name_status, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    # The seal is the record. If this insert fails the block still exists and
    # is still valid - the index row is a convenience for lookup, not the
    # evidence - so a failure here must not be reported as a failed
    # observation.
    index_ok = True
    try:
        with ctx["lock"]:
            ctx["conn"].execute("INSERT INTO witness_log(api_key,peer,tip,peer_ts,observed,audit_hash,block_index,note,url,liveness,name_status,reachability) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                (api_key, peer, tip, peer_ts, ts, h, idx, note or None,
                                 url or None, liveness, name_status, reachability))
            ctx["conn"].commit()
    except Exception as exc:
        index_ok = False
        index_error = type(exc).__name__

    our, _t, height = _our_tip(ctx)
    out = {"peer": peer, "witnessed_tip": tip, "observed_at": _iso(ts),
           "sealed_in_our_chain": h, "block_index": idx, "receipt_seq": seq,
           "our_tip_now": our, "our_height": height,
           "liveness": liveness, "reachability": reachability,
           "name_status": name_status,
           "attest": "/x/witness/attest?peer=" + peer + "&tip=" + tip,
           "message": MESSAGES["observe_ok"],
           "anchoring": ANCHOR_NOTE}
    if note:
        out["flag"] = note
    out["witness_version"] = VERSION
    out["liveness_vocabulary"] = _vocab(liveness)
    out["reachability_vocabulary"] = _reach_vocab(reachability)
    out["name_vocabulary"] = _name_vocab(name_status)
    if not index_ok:
        out["index_warning"] = (
            "Sealed into the chain, but our lookup index did not accept the "
            "row (%s). The block is valid and permanent; /x/witness/attest "
            "may not find it until the index is repaired. Reported rather "
            "than hidden." % index_error)
    if liveness == LIVENESS_NONE:
        out["advice"] = (MESSAGES["observe_advice_unusable"]
                         if reachability == REACHED_YES
                         else MESSAGES["observe_advice"])
    if name_status == NAME_CONFLICT:
        out["warning"] = MESSAGES["observe_conflict"]
    return out, 200


def _attest(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip().lower()
    tip = str(data.get("tip", "")).strip().lower()
    if not peer or not tip:
        return {"error": "peer_and_tip_required",
                "usage": "/x/witness/attest?peer=<name>&tip=<64 hex>"}, 400
    with ctx["lock"]:
        if api_key:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url,reachability FROM witness_log WHERE api_key=? AND peer=? AND tip=? ORDER BY id ASC", (api_key, peer, tip)).fetchall()
        else:
            rows = ctx["conn"].execute("SELECT observed,audit_hash,block_index,peer_ts,liveness,name_status,url,reachability FROM witness_log WHERE peer=? AND tip=? ORDER BY id ASC", (peer, tip)).fetchall()
    if not rows:
        return {"witnessed": False, "peer": peer, "tip": tip,
                "message": MESSAGES["not_witnessed"]}, 404
    return {"witnessed": True, "peer": peer, "tip": tip,
            "first_observed": _iso(rows[0][0]),
            "last_observed": _iso(rows[-1][0]),
            "times_observed": len(rows),
            "sealed_in_our_chain": rows[0][1],
            "block_index": rows[0][2],
            "peer_claimed_time": _iso(rows[0][3]),
            "liveness": rows[0][4] or "unchecked",
            "liveness_vocabulary": _vocab(rows[0][4]),
            "reachability": rows[0][7] or "unrecorded",
            "reachability_vocabulary": _reach_vocab(rows[0][7]),
            "name_status": rows[0][5] or "unchecked",
            "name_vocabulary": _name_vocab(rows[0][5]),
            "submitted_url": rows[0][6],
            "witness_version": VERSION,
            "what_this_proves": MESSAGES["attest_proves"],
            "proof": MESSAGES["attest_proof"],
            "anchoring": ANCHOR_NOTE}, 200


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
    follow it.

    General form worth keeping: a name a reader treats as documentation may
    be a value the code branches on, and the two roles are invisible to each
    other from outside.
    """
    return VOCABULARY.get(liveness, VOCABULARY[None])


def _reach_vocab(reachability):
    """What the reachability value means, travelling with the value.

    Added in 1.4. Same reasoning as _vocab: a value that gets quoted
    elsewhere needs its meaning attached, not left in a legend on a page
    somebody may never open.
    """
    return REACH_VOCABULARY.get(reachability, REACH_VOCABULARY[None])


def _name_vocab(name_status):
    """What the name status means, and what it costs.

    Travels with the value for the same reason liveness vocabulary does. The
    unbound entry states the exposure plainly rather than leaving a submitter
    to work it out: choosing the accurate weaker liveness status by
    withholding a url also leaves the name claimable, and nobody should have
    to discover that coupling by being squatted.
    """
    return NAME_VOCABULARY.get(name_status, NAME_VOCABULARY[None])


def _peers(ctx, api_key):
    """Who we witness, and how consistently.

    Rewritten in 1.3. This used to read every row in witness_log to find each
    peer's most recent liveness and name status. Now the same answer comes
    from a grouped query against the (peer,id) index, so the cost stops
    growing with the size of the log.
    """
    with ctx["lock"]:
        c = ctx["conn"]
        if api_key:
            rows = c.execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log WHERE api_key=? GROUP BY peer ORDER BY MAX(observed) DESC", (api_key,)).fetchall()
        else:
            rows = c.execute("SELECT peer,COUNT(*),MIN(observed),MAX(observed),COUNT(DISTINCT tip) FROM witness_log GROUP BY peer ORDER BY MAX(observed) DESC").fetchall()

        latest = {}
        for p, live, name, reach in c.execute(
                "SELECT w.peer,w.liveness,w.name_status,w.reachability FROM witness_log w "
                "JOIN (SELECT peer,MAX(id) AS mid FROM witness_log GROUP BY peer) m "
                "ON w.id=m.mid").fetchall():
            latest[p] = (live, name, reach)

        conflicts = {}
        for p, n in c.execute(
                "SELECT peer,COUNT(*) FROM witness_log WHERE name_status=? "
                "GROUP BY peer", (NAME_CONFLICT,)).fetchall():
            conflicts[p] = n

        bindings = {}
        for p, u in c.execute("SELECT peer,url FROM witness_names").fetchall():
            bindings[p] = u

    t = time.time()
    peers = []
    for p, n, first, last, distinct in rows:
        hours = round((t - last) / 3600, 1)
        live, name, reach = latest.get(p, (None, None, None))
        entry = {"peer": p, "observations": n, "distinct_tips": distinct,
                 "first_seen": _iso(first), "last_seen": _iso(last),
                 "hours_since_last": hours,
                 "status": ("current" if hours < 6 else "stale" if hours < 48 else "silent"),
                 "liveness": live or "unchecked",
                 "reachability": reach or "unrecorded",
                 "name_status": name or "unchecked",
                 "bound_to": bindings.get(p)}
        if conflicts.get(p):
            entry["name_conflicts"] = conflicts[p]
        peers.append(entry)
    return {"count": len(peers), "peers": peers,
            "witness_version": VERSION,
            "what_this_list_is": MESSAGES["list_is"],
            "status_vocabulary": {
                "current": "observed within the last 6 hours",
                "stale": "last observed between 6 and 48 hours ago",
                "silent": "not observed for more than 48 hours",
                "note": ("These describe elapsed time since we last recorded "
                         "an observation and nothing else. A peer that "
                         "publishes on a human schedule rather than a timer "
                         "will read stale between sessions, correctly. It is "
                         "not a claim that anyone's endpoint was unavailable."),
            },
            "legend": LEGEND,
            "note": MESSAGES["list_note"]}, 200


def _history(ctx, api_key, peer):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT tip,observed,audit_hash,block_index,note,liveness,name_status,url,reachability FROM witness_log WHERE api_key=? AND peer=? ORDER BY id ASC LIMIT ?", (api_key, peer, MAX_HISTORY)).fetchall()
    if not rows:
        return {"error": "unknown_peer", "peer": peer}, 404
    return {"peer": peer, "count": len(rows), "limit": MAX_HISTORY,
            "witness_version": VERSION,
            "observations": [{"tip": r[0], "observed": _iso(r[1]),
                              "sealed": r[2], "block_index": r[3],
                              "flag": r[4], "liveness": r[5] or "unchecked",
                              "name_status": r[6] or "unchecked",
                              "reachability": r[8] or "unrecorded",
                              "url": r[7]} for r in rows],
            "note": MESSAGES["history_note"]}, 200


def _spec():
    """The whole protocol, for someone who is not going to run our code.

    Added in 1.3. Every other module publishes a spec route and this one did
    not, which meant the four calls a new peer needs were only written down
    in a page they had to be sent a link to.
    """
    return {"witness_version": VERSION,
            "the_protocol_in_four_calls": [
                "1. GET /x/witness/tip - our current chain head.",
                "2. Seal that value into your own chain, however your chain works.",
                "3. POST /x/witness/observe with {\"chain\":\"<your name>\","
                "\"tip\":\"<your 64 hex head>\",\"url\":\"<where you publish "
                "your head>\"}. No account, no key.",
                "4. GET /x/witness/attest?peer=<your name>&tip=<your head> - "
                "your receipt, readable by anyone.",
            ],
            "fields": {
                "chain": "required. Short stable identifier, 80 chars max. "
                         "'peer' accepted as an alias.",
                "tip": "required. 64 lowercase hex characters.",
                "url": "optional but strongly advised - see name_vocabulary. "
                       "http or https, port 80 or 443, must resolve to a "
                       "publicly routable address, no redirects followed. It "
                       "must serve JSON containing your tip - a page that "
                       "answers with HTML is reachable but not bindable, and "
                       "those two facts are recorded separately.",
                "peer_ts": "optional. Epoch seconds or ISO 8601. 'ts' accepted "
                           "as an alias.",
            },
            "tip_fields_we_accept_at_your_url": list(TIP_FIELDS),
            "nothing_is_rejected": (
                "Both checks are non-rejecting. Every well-formed submission "
                "is sealed. What varies is what the record says about it."),
            "liveness_vocabulary": {k: v for k, v in VOCABULARY.items() if k},
            "reachability_vocabulary": {k: v for k, v in REACH_VOCABULARY.items() if k},
            "reached_is_not_parsed": LEGEND["reached_is_not_parsed"],
            "name_vocabulary": {k: v for k, v in NAME_VOCABULARY.items() if k},
            "signed_lane": SIGNED_LANE_NOTE,
            "anchoring": ANCHOR_NOTE,
            "what_this_is_not": MESSAGES["list_is"]}, 200


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
        if action == "spec":
            return _spec()
        if action == "history":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            peer = str(data.get("peer", "")).strip().lower()
            if not peer:
                return {"error": "peer_required"}, 400
            return _history(ctx, api_key, peer)
    return {"error": "unknown_action", "action": action}, 404
