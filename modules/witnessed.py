#!/usr/bin/env python3
"""
modules/witnessed.py  -  what an outside party had already seen, and when

THE HOLE THIS CLOSES
--------------------
Authority continuity (modules/continuity.py) derives an action back to a human
grant and re-checks every hop at execution. It is the strongest thing on this
platform and it has one gap, which is stated plainly in its own spec and is
worth restating here because it is the whole reason this module exists:

    the authorising principal, the scope and the approver all arrive on the
    request. There is no external source to ask. A well-formed grant that
    was never issued would pass every check we run.

Nothing inside a system can close that, because every term in the check is
produced by the party being checked. An auditor does not ask a company for its
cash balance. They ask the bank.

We have a bank. Since 1 August 2026 independent chains have been sealing this
chain's tip hourly into logs this operator cannot write to. That machinery was
built for a different purpose - stopping us backdating the decision record -
and it turns out to answer a question nobody pointed it at:

    a grant sealed at tree size M, and a peer that sealed our root at tree
    size N >= M at time T, means the grant existed before T, in a record
    the operator cannot reach.

That does not make a grant legitimate. It makes it impossible to invent one
afterwards - which is the attack that actually matters. When something goes
wrong, the tempting move is not to forge a signature. It is to produce a
perfectly well-formed authorisation dated last Tuesday. This is the thing that
stops that, and it needs no new protocol, no consortium and no cooperation
beyond the tip exchange already running.

WHAT IT ADDS
------------
  - an attestation record: our tree size and root, submitted to a named peer,
    with whatever that peer returned, sealed into our own chain
  - for any grant or any sealed record, the EARLIEST external attestation
    that covers it, and the exact routes a third party runs to check that
    against the peer's own host rather than ours
  - a latency figure nobody publishes: how long a grant sat unwitnessed. A
    grant witnessed nine seconds after issue is a different object from one
    witnessed nine days after, and both are stated

WHAT IT REFUSES TO DO
---------------------
  - it never certifies a peer's answer. Every response is recorded verbatim
    and marked unverified; the verification plan points at the peer's host
  - it never rewrites the meaning of an old attestation. A submission is
    sealed when it is made and is not amended
  - it does not claim a witnessed grant is a legitimate grant, anywhere, in
    any wording. Existence before a time is the entire claim

    POST /x/witnessed/submit    push the current head to a peer   (keyed)
    GET  /x/witnessed/grant     earliest cover for a grant        (public)
    GET  /x/witnessed/record    earliest cover for any receipt    (public)
    GET  /x/witnessed/heads     every attestation on record       (public)
    GET  /x/witnessed/status    coverage, and the honest gaps     (public)
    GET  /x/witnessed/spec      the rules, in full                (public)
"""

import hashlib
import json
import re
import socket
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = {("GET", "grant"), ("GET", "record"), ("GET", "heads"),
          ("GET", "status"), ("GET", "spec")}

HEAD_PREFIX = b"AILEASH-WITNESSED-HEAD-v1:"
TIMEOUT = 8
MAX_BYTES = 256 * 1024

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witnessed_head("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,peer TEXT,peer_url TEXT,"
                  "tree_size INTEGER,tip TEXT,head_digest TEXT,submitted REAL,"
                  "accepted INTEGER,peer_response TEXT,peer_block TEXT,"
                  "audit_hash TEXT,block_index INTEGER,api_key TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_size "
                  "ON witnessed_head(tree_size)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer "
                  "ON witnessed_head(peer)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _cols(ctx, table):
    try:
        with ctx["lock"]:
            return [r[1] for r in ctx["conn"].execute(
                "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


# ----------------------------------------------------------------------
# where a record sits in the chain
# ----------------------------------------------------------------------

def _head(ctx):
    """Current tree size and tip, read the same way consistency.py orders it:
    audit_log in write order."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*), MAX(id) FROM audit_log").fetchone()
        tip = ctx["conn"].execute(
            "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    size = (row[0] if row else 0) or 0
    return size, (tip[0] if tip else None)


def _size_at(ctx, row_id):
    """The tree size at which the record with this audit_log id is included."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*) FROM audit_log WHERE id<=?", (row_id,)).fetchone()
    return row[0] if row else None


def _locate_hash(ctx, audit_hash):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id,ts FROM audit_log WHERE audit_hash=? ORDER BY id ASC LIMIT 1",
            (audit_hash,)).fetchone()
    if not row:
        return None, None, None
    return row[0], row[1], _size_at(ctx, row[0])


def _locate_grant(ctx, grant_id):
    """A grant's own sealed block. Read defensively - the column set has moved
    before and a module that assumes a schema is a module that breaks."""
    cols = _cols(ctx, "auth_grant")
    if not cols:
        return None
    want = [c for c in ("id", "audit_hash", "created", "issuer", "subject",
                        "risk_accepted_by", "parent", "root") if c in cols]
    if "audit_hash" not in want:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT %s FROM auth_grant WHERE id=?" % ",".join(want),
            (grant_id,)).fetchone()
    if not row:
        return None
    return dict(zip(want, row))


# ----------------------------------------------------------------------
# the earliest outside party to have seen it
# ----------------------------------------------------------------------

def _earliest_cover(ctx, size):
    """The first attestation whose tree size reaches this record.

    Accepted submissions only. A peer that refused, timed out or answered
    with something unreadable has not seen anything, and counting it would be
    the exact self-flattery this module exists to remove.
    """
    if not size:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT peer,peer_url,tree_size,tip,submitted,peer_block,audit_hash,"
            "block_index FROM witnessed_head WHERE accepted=1 AND tree_size>=? "
            "ORDER BY submitted ASC LIMIT 1", (size,)).fetchone()
    if not row:
        return None
    return {"peer": row[0], "peer_url": row[1], "tree_size": row[2],
            "tip": row[3], "witnessed_at": _iso(row[4]),
            "witnessed_at_epoch": row[4], "peer_block": row[5],
            "our_seal_of_the_submission": row[6], "our_block_index": row[7]}


def _all_covers(ctx, size, limit=10):
    if not size:
        return []
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,submitted,peer_block FROM witnessed_head "
            "WHERE accepted=1 AND tree_size>=? ORDER BY submitted ASC LIMIT ?",
            (size, limit)).fetchall()
    return [{"peer": r[0], "tree_size": r[1], "witnessed_at": _iso(r[2]),
             "peer_block": r[3]} for r in rows]


def _plan(size, cover):
    """What a third party runs, and where. Every step that can be checked
    against the peer rather than against us is pointed at the peer."""
    if not cover:
        return None
    return [
        {"step": 1,
         "what": "Confirm the peer holds that tip, and when they sealed it",
         "where": "the peer's own host",
         "run": (cover.get("peer_url") or ("https://" + str(cover.get("peer"))))
                + "/x/witness/attest?peer=<this chain>&tip=" + str(cover.get("tip"))},
        {"step": 2,
         "what": "Confirm the tip they hold is a genuine head of this log",
         "where": "here, but re-derivable by anyone",
         "run": "/x/consistency/ancestor?tip=" + str(cover.get("tip"))},
        {"step": 3,
         "what": "Confirm the record is inside the log that tip commits to",
         "where": "here, and checkable offline with the published rules",
         "run": "/x/consistency/proof?first=" + str(size) + "&second="
                + str(cover.get("tree_size"))},
        {"step": 4,
         "what": "Conclude",
         "where": "your own arithmetic",
         "run": "the record sat at size " + str(size) + "; the peer sealed a root "
                "at size " + str(cover.get("tree_size")) + " on "
                + str(cover.get("witnessed_at")) + ". It existed before then, in a "
                "log this operator cannot write to."},
    ]


# ----------------------------------------------------------------------
# submitting a head to a peer
# ----------------------------------------------------------------------

def _safe_url(url):
    """Same posture as witness.py: http/https, standard ports, resolve first
    and refuse anything that lands on a private address."""
    try:
        u = urlparse(url)
    except Exception:
        return None, "unparseable url"
    if u.scheme not in ("http", "https"):
        return None, "only http and https"
    if u.port and u.port not in (80, 443):
        return None, "only ports 80 and 443"
    host = u.hostname
    if not host:
        return None, "no host"
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as exc:
        return None, "cannot resolve (%s)" % str(exc)[:80]
    for info in infos:
        addr = info[4][0]
        if _private(addr):
            return None, "resolves to a non-public address"
    return u, None


def _private(addr):
    try:
        import ipaddress
        ip = ipaddress.ip_address(addr)
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except Exception:
        return True


def _submit(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip()[:120]
    url = str(data.get("url", "")).strip()
    chain = str(data.get("chain", "")).strip()[:120] or None
    if not peer or not url:
        return {"error": "peer_and_url_required",
                "message": "peer is the name they publish under; url is their "
                           "witness endpoint, e.g. https://example.com"}, 400

    u, why = _safe_url(url)
    if why:
        return {"error": "url_refused", "message": why}, 400

    size, tip = _head(ctx)
    if not size or not tip:
        return {"error": "nothing_to_witness",
                "message": "The chain is empty. There is no head to submit."}, 409

    head_digest = hashlib.sha256(
        HEAD_PREFIX + json.dumps({"tree_size": size, "tip": tip},
                                 sort_keys=True, separators=(",", ":")
                                 ).encode("utf-8")).hexdigest()

    body = json.dumps({"chain": chain or "sebbi.pro", "tip": tip,
                       "tree_size": size, "peer_ts": time.time()}).encode("utf-8")
    endpoint = url.rstrip("/") + "/x/witness/observe"

    accepted = 0
    response_text = ""
    peer_block = None
    try:
        req = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "aileash-witnessed/" + VERSION},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES)
            response_text = raw.decode("utf-8", "replace")[:4000]
            accepted = 1 if 200 <= r.status < 300 else 0
        try:
            parsed = json.loads(response_text)
            for k in ("sealed_in_our_chain", "block_index", "audit_hash", "seal"):
                if isinstance(parsed, dict) and parsed.get(k) is not None:
                    peer_block = str(parsed[k])
                    break
        except Exception:
            pass
    except Exception as exc:
        response_text = "request failed: " + str(exc)[:300]
        accepted = 0

    now = time.time()
    ev = {"user_id": "wit:" + peer[:40], "action": "head_submitted", "amount": 0,
          "country": "UK", "device_id": "witnessed", "anomaly": 0,
          "device_risk": 0 if accepted else 1}
    res = {"decision": "HEAD_SUBMITTED" if accepted else "HEAD_SUBMISSION_FAILED",
           "score": 0, "witnessed_version": VERSION, "peer": peer,
           "tree_size": size, "tip": tip, "head_digest": head_digest,
           "accepted": bool(accepted), "peer_block": peer_block,
           "detail": "peer=%s;size=%d;tip=%s;accepted=%s"
                     % (peer, size, tip, bool(accepted))}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,"
            "api_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer, url, size, tip, head_digest, now, accepted,
             response_text, peer_block, audit_hash, block_index, api_key))
        ctx["conn"].commit()

    out = {"peer": peer, "tree_size": size, "tip": tip,
           "head_digest": head_digest, "accepted": bool(accepted),
           "peer_block": peer_block, "submitted_at": _iso(now),
           "sealed_in_chain": audit_hash, "block_index": block_index,
           "receipt_seq": seq,
           "peer_response": response_text[:800],
           "peer_response_is_unverified": True,
           "note": ("The failure is sealed too. A submission a peer refused is "
                    "part of the record, and coverage never counts it.")}
    if accepted:
        out["what_this_now_proves"] = (
            "Every record at or below tree size " + str(size) + " existed before "
            + _iso(now) + " in a log this operator cannot write to. It says nothing "
            "about whether those records are true.")
    return out, (200 if accepted else 502)


# ----------------------------------------------------------------------
# read
# ----------------------------------------------------------------------

def _grant(ctx, data):
    gid = str(data.get("id") or data.get("grant") or "").strip()
    if not gid:
        return {"error": "grant_required",
                "list": "/x/continuity/decisions"}, 400

    g = _locate_grant(ctx, gid)
    if not g:
        return {"error": "grant_not_found", "grant": gid}, 404

    row_id, sealed_ts, size = _locate_hash(ctx, g.get("audit_hash"))
    if size is None:
        return {"error": "grant_not_in_chain", "grant": gid,
                "message": "The grant record carries a seal that is not in the "
                           "audit log. That is a finding, not a lookup failure."}, 409

    cover = _earliest_cover(ctx, size)
    out = {
        "grant": gid,
        "sealed_at": _iso(sealed_ts),
        "tree_size_at_seal": size,
        "externally_witnessed": bool(cover),
        "earliest_external_witness": cover,
        "also_witnessed_by": _all_covers(ctx, size)[1:] if cover else [],
        "verification_plan": _plan(size, cover),
        "what_this_proves": None,
        "what_this_does_not_prove": (
            "That the grant should ever have been issued, or that the person "
            "named as issuing it did. It proves the grant existed at a time, in "
            "a record we cannot reach. Legitimacy is an organisational question "
            "and no witness answers it."),
    }

    if cover:
        gap = None
        try:
            if g.get("created") and cover.get("witnessed_at_epoch"):
                gap = round((cover["witnessed_at_epoch"] - float(g["created"])) / 60.0, 1)
        except Exception:
            gap = None
        out["minutes_unwitnessed"] = gap
        out["what_this_proves"] = (
            "This grant was already sealed when <b>" + str(cover["peer"]) +
            "</b> took a copy of this log's head at " + str(cover["witnessed_at"]) +
            ". It cannot have been written afterwards to justify anything, "
            "because that would require them to rewrite their own chain.").replace("<b>", "").replace("</b>", "")
        if gap is not None and gap > 1440:
            out["flag"] = ("this grant sat unwitnessed for " + str(round(gap / 1440.0, 1))
                           + " days. Everything above still holds from the moment it "
                           "was witnessed; the window before that rests on our word "
                           "alone, and is published rather than smoothed over.")
    else:
        out["flag"] = ("no external attestation covers this grant yet. Until a peer "
                       "seals a head at or beyond tree size " + str(size) +
                       ", its existence before now rests on this operator's own "
                       "record. That is the ordinary state of a grant issued "
                       "moments ago, and it is the honest state of one issued "
                       "long ago with no peer running.")
    return out, 200


def _record(ctx, data):
    h = str(data.get("hash") or data.get("receipt") or "").strip().lower()
    if not re.match(r"^[0-9a-f]{64}$", h):
        return {"error": "sha256_hash_required"}, 400
    row_id, sealed_ts, size = _locate_hash(ctx, h)
    if size is None:
        return {"error": "not_in_chain", "hash": h}, 404
    cover = _earliest_cover(ctx, size)
    return {"hash": h, "sealed_at": _iso(sealed_ts), "tree_size_at_seal": size,
            "externally_witnessed": bool(cover),
            "earliest_external_witness": cover,
            "verification_plan": _plan(size, cover),
            "what_this_proves": (
                "This record existed before " + str(cover["witnessed_at"]) +
                ", in a log held by " + str(cover["peer"]) + " which this operator "
                "cannot write to.") if cover else None,
            "what_this_does_not_prove":
                "That the record is true. Existence and timing only."}, 200


def _heads(ctx, data):
    try:
        limit = max(1, min(int(data.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,tip,submitted,accepted,peer_block,block_index "
            "FROM witnessed_head ORDER BY submitted DESC LIMIT ?", (limit,)).fetchall()
    return {"count": len(rows),
            "heads": [{"peer": r[0], "tree_size": r[1], "tip": r[2],
                       "submitted_at": _iso(r[3]), "accepted": bool(r[4]),
                       "peer_block": r[5], "our_block_index": r[6]} for r in rows],
            "note": ("Refused and failed submissions are listed alongside accepted "
                     "ones. A witness network that only publishes its successes is "
                     "reporting on itself.")}, 200


def _status(ctx):
    size, tip = _head(ctx)
    with ctx["lock"]:
        agg = ctx["conn"].execute(
            "SELECT COUNT(*),SUM(accepted),MAX(CASE WHEN accepted=1 THEN tree_size END),"
            "MAX(CASE WHEN accepted=1 THEN submitted END) FROM witnessed_head").fetchone()
        peers = ctx["conn"].execute(
            "SELECT peer,COUNT(*),MAX(submitted) FROM witnessed_head "
            "WHERE accepted=1 GROUP BY peer").fetchall()

    total, ok, covered_to, last = (agg or (0, 0, None, None))
    ok = ok or 0
    covered_to = covered_to or 0
    uncovered = max(0, size - covered_to)

    out = {"tree_size_now": size, "tip": tip,
           "covered_to_tree_size": covered_to,
           "records_not_yet_witnessed": uncovered,
           "submissions": total or 0, "accepted": ok,
           "distinct_peers": len(peers),
           "last_accepted_at": _iso(last),
           "peers": [{"peer": p[0], "accepted_submissions": p[1],
                      "last_at": _iso(p[2])} for p in peers]}

    if len(peers) == 0:
        out["strength"] = "none"
        out["flag"] = ("no peer has ever accepted a head. Nothing on this chain "
                       "has external attestation, and every claim about when a "
                       "grant was issued currently rests on our own record.")
    elif len(peers) == 1:
        out["strength"] = "weak"
        out["flag"] = ("one peer. Two parties attesting only each other can still "
                       "collude, and this number is the honest measure of that. It "
                       "improves with breadth, not with volume.")
    elif len(peers) < 3:
        out["strength"] = "thin"
    else:
        out["strength"] = "reasonable"

    out["why_this_matters"] = (
        "Authority derivation proves an action was derivable from a grant. It "
        "cannot prove the grant was ever issued, because every term in that check "
        "arrives from the party being checked. This is the outside source. It does "
        "not establish that a grant was legitimate - it establishes that it was "
        "not written after the fact, which is the failure an incident actually "
        "produces.")
    return out, 200


def _spec():
    return {
        "witnessed_version": VERSION,
        "the_claim": ("A record sealed at tree size M, and a peer that accepted a "
                      "head at tree size N >= M at time T, means the record existed "
                      "before T in a log this operator cannot write to."),
        "the_gap_it_closes": ("Authority continuity derives an action back to a "
                              "grant, but the issuer, scope and approver all arrive "
                              "on the request and there is no external source to "
                              "ask. A well-formed grant that was never issued passes "
                              "every internal check. This does not make such a grant "
                              "detectable - it makes one impossible to create after "
                              "the event."),
        "ordering": ("audit_log in write order, the same ordering "
                     "/x/consistency/ uses. Tree size at a record is the count of "
                     "rows at or before it."),
        "head_digest": ("sha256('AILEASH-WITNESSED-HEAD-v1:' || canonical JSON of "
                        "{tree_size, tip}, keys sorted, no whitespace)"),
        "coverage_rule": ("accepted submissions only. A refused, timed-out or "
                          "unreadable response is recorded and never counted."),
        "peer_responses": ("recorded verbatim and never verified by us. The "
                           "verification plan on every answer points at the peer's "
                           "own host, because an attestation checked only by the "
                           "party it flatters is not an attestation."),
        "what_it_never_claims": [
            "that a witnessed grant is a legitimate grant",
            "that a witnessed record is a true record",
            "that a peer is who they say they are - name binding is witness.py's "
            "job and is reported there, unverified, as first-use, bound or conflict",
        ],
        "honest_limits": [
            "One peer is one peer. Two parties attesting only each other can "
            "collude, and /x/witnessed/status reports the count rather than "
            "describing the network as strong.",
            "Everything sealed since the last accepted head is unwitnessed, and "
            "the count is published.",
            "A peer who stops answering leaves coverage frozen at the last size "
            "they took. That shows as a growing records_not_yet_witnessed figure "
            "rather than as silence.",
            "This proves existence before a time. Nothing here reaches whether a "
            "grant should have been issued, which is an organisational question "
            "no cryptography answers.",
        ],
        "why_published": ("Anyone should be able to reimplement this and check us "
                          "with it. The steps are four HTTP requests and one "
                          "comparison of two integers."),
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action in ("", "status"):
            return _status(ctx)
        if action == "grant":
            return _grant(ctx, data)
        if action == "record":
            return _record(ctx, data)
        if action == "heads":
            return _heads(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "submit":
            return _submit(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "status", "grant", "record", "heads"],
            "POST": ["submit"]}, 404
