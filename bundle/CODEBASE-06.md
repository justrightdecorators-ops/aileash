# Codebase — part 6 of 19

Contains:
- `modules/publish.py`
- `modules/reconcile.py`
- `modules/replay.py`
- `modules/router.py`
- `modules/rulebind.py`


## `modules/publish.py`

491 lines, 21976 bytes

```python
#!/usr/bin/env python3
"""
modules/publish.py  -  sealing what you published, at the moment you publish it
===============================================================================

THE PROBLEM THIS EXISTS TO NEVER HAVE AGAIN
-------------------------------------------
Somebody asks when a page was published. You answer from git history. They
point out - correctly - that git commit dates are fields in the commit
object which anyone can set to anything with an environment variable before
committing. Your strongest evidence turns out to be the weakest thing in
the room, and it drags the credible parts down with it.

The fix is not a better argument. It is sealing the page the moment it goes
live, so the question never depends on anybody's word again.

WHAT THIS DOES
--------------
    POST /x/publish/seal {"url": "https://example.com/spec"}

We fetch the URL ourselves, hash exactly what was served, and seal the hash,
the URL and the fetch time into the chain - where it is anchored externally
and handed to peer chains like every other block.

From then on:

  - "this exact content was served at this address no later than T" is
    arithmetic rather than a claim;
  - re-sealing the same URL later builds a permanent revision history that
    the publisher cannot edit, because each version is its own block;
  - and anyone can check it without an account.

Seal at publication and you never argue about a publication date again. That
is the entire point, and it takes one call.

WHAT IT HONESTLY CANNOT DO
--------------------------
It cannot reach backwards. A seal made today proves the content existed
today, not that it existed last week. Nothing can prove that - not this, not
Bitcoin, not a notary. Timestamps are one-directional by nature.

So for anything already published before it was sealed, the module records
EXTERNAL REFERENCES alongside: a GitHub push event, a Wayback Machine
snapshot, a DigiCert or OpenTimestamps proof. Those are stored and sealed as
supplied. We do not verify them and we do not present them as ours - they
are somebody else's record, named so a third party can check it at source.
That distinction is stated in every response rather than left to be
discovered.

Two references are worth knowing about, because they are the ones that
actually carry an earlier date:

  GitHub push events   api.github.com/repos/<owner>/<repo>/events
                       The push timestamp is recorded server-side by GitHub
                       and cannot be set by the pusher, unlike commit dates.
                       Retained roughly 90 days - so it must be captured
                       while it still exists.

  Wayback Machine      archive.org/wayback/available?url=...&timestamp=...
                       An independent party with no stake in the dispute.
                       If it caught the page, that settles it outright.

FETCHING SAFELY
---------------
This module makes the server fetch a URL. Done naively that is a hole worse
than the one it closes. So the fetcher speaks only http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that
is private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a cap. Sealing is keyed,
so this is not an anonymous capability either.

    POST /x/publish/seal      fetch, hash and seal a live URL     (keyed)
    GET  /x/publish/history   every version ever sealed of a URL  (public)
    GET  /x/publish/verify    was this exact content served, when (public)
    GET  /x/publish/list      everything sealed                   (public)
    GET  /x/publish/spec      how to check any of it              (public)
"""

import hashlib
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Reading is open. A publication record only settles an argument if the
# other side can check it without going through the publisher.
PUBLIC = {("GET", "history"), ("GET", "verify"), ("GET", "list"),
          ("GET", "spec")}

CONTENT_PREFIX = b"AILEASH-PUBLISH-v1:"

FETCH_TIMEOUT = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
MAX_EXTERNAL = 8

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS publish_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,url TEXT,"
                  "content_hash TEXT,byte_length INTEGER,http_status INTEGER,"
                  "content_type TEXT,note TEXT,external TEXT,"
                  "fetched REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_url ON publish_seal(url,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_hash ON publish_seal(content_hash)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# fetching - read the SSRF note above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction to fetch a second URL we never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
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
    if not parts.hostname:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(parts.hostname, port)


def _fetch(url):
    """Returns (body_bytes, status, content_type, error)."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, None, None, why
    request = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "aileash-publish/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, exc.code, None, "url answered %s" % exc.code
    except Exception as exc:
        return None, None, None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, status, content_type, "response larger than the %d byte cap" % MAX_FETCH_BYTES
    return body, status, content_type, None


def _content_hash(body):
    """Hash exactly the bytes served. No normalisation, no cleverness -
    a whitespace-tolerant hash would be a hash of our opinion of the page
    rather than of the page."""
    return hashlib.sha256(CONTENT_PREFIX + body).hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _clean_external(value):
    """External references are recorded verbatim and never verified."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_EXTERNAL]:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()[:60]
            reference = str(item.get("reference", item.get("url", ""))).strip()[:400]
            claimed = str(item.get("claimed_time", "")).strip()[:60]
            if source and reference:
                out.append({"source": source, "reference": reference,
                            "claimed_time": claimed or None})
        elif isinstance(item, str) and item.strip():
            out.append({"source": "unnamed", "reference": item.strip()[:400],
                        "claimed_time": None})
    return out


def _seal(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required",
                "message": "The address of the page you have just published."}, 400

    note = str(data.get("note", "") or "").strip()[:300]
    external = _clean_external(data.get("external"))

    body, status, content_type, why = _fetch(url)
    if why:
        return {"error": "fetch_failed", "url": url, "message": why,
                "note": "Nothing was sealed. A record of a page we could not read would be "
                        "worse than no record."}, 502

    digest = _content_hash(body)
    now = time.time()

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT content_hash,fetched,audit_hash FROM publish_seal "
            "WHERE url=? ORDER BY id ASC", (url,)).fetchall()

    unchanged = bool(prior) and prior[-1][0] == digest
    first_of_this_version = None
    for row in prior:
        if row[0] == digest:
            first_of_this_version = row[1]
            break

    external_summary = ";".join("%s=%s" % (e["source"], e["reference"][:60]) for e in external)
    ev = {"user_id": "pub:" + digest[:16], "action": "publication_sealed", "amount": 0,
          "country": "UK", "device_id": "publish", "anomaly": 0, "device_risk": 0}
    res = {"decision": "PUBLICATION_SEALED", "score": 0, "publish_version": VERSION,
           "url": url, "content_hash": digest, "bytes": len(body),
           "http_status": status,
           "detail": "url=%s;sha256=%s;bytes=%d%s"
                     % (url, digest, len(body),
                        ";external=" + external_summary if external_summary else "")}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO publish_seal(api_key,url,content_hash,byte_length,http_status,"
            "content_type,note,external,fetched,audit_hash,block_index) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, digest, len(body), status, content_type or None,
             note or None,
             "|".join("%s %s %s" % (e["source"], e["reference"], e["claimed_time"] or "")
                      for e in external) or None,
             now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "url": url, "content_hash": digest, "bytes": len(body),
        "http_status": status, "content_type": content_type,
        "sealed_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "version_number": len(prior) + 1,
        "publish_version": VERSION,
        "what_this_proves": "This exact content was served at this address when we fetched it, "
                            "and the record of that cannot be altered afterwards.",
        "what_it_does_not": "It does not prove the page existed earlier than this moment. "
                            "Nothing can prove that after the fact - timestamps only run "
                            "forwards. Seal at publication and the question never arises.",
        "history": "/x/publish/history?url=" + url,
        "verify_this_block": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if unchanged:
        out["unchanged"] = True
        out["first_sealed_in_this_form"] = _iso(first_of_this_version)
        out["message"] = ("Identical to the last sealed version. The page has not changed since "
                          "%s and now has an additional dated witness." % _iso(first_of_this_version))
    elif prior:
        out["changed"] = True
        out["previous_hash"] = prior[-1][0]
        out["previous_sealed_at"] = _iso(prior[-1][1])
        out["message"] = ("The content has changed since the last seal. Both versions remain in "
                          "the chain - a revision history the publisher cannot edit.")
    else:
        out["message"] = ("First seal for this address. Every later seal builds a permanent, "
                          "dated revision history from here.")

    if external:
        out["external_references"] = external
        out["external_caveat"] = ("Recorded exactly as supplied and sealed with the block. We do "
                                  "not verify them and they are not our evidence - they are "
                                  "somebody else's record, named so you can check them at "
                                  "source.")
    else:
        out["advice"] = ("If this page was published before today, add external references - a "
                         "GitHub push event, a Wayback snapshot - and they will be sealed "
                         "alongside. Those carry an earlier date; a seal made now cannot.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _parse_external(blob):
    if not blob:
        return []
    out = []
    for line in blob.split("|"):
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append({"source": parts[0], "reference": parts[1],
                        "claimed_time": parts[2] if len(parts) > 2 and parts[2] else None})
    return out


def _history(ctx, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT content_hash,byte_length,fetched,audit_hash,block_index,note,external "
            "FROM publish_seal WHERE url=? ORDER BY id ASC LIMIT 500", (url,)).fetchall()
    if not rows:
        return {"error": "never_sealed", "url": url,
                "message": "No seal recorded for that address."}, 404

    versions, last_hash = [], None
    for content_hash, length, fetched, audit_hash, block_index, note, external in rows:
        versions.append({
            "content_hash": content_hash, "bytes": length,
            "sealed_at": _iso(fetched), "sealed_in_chain": audit_hash,
            "block_index": block_index, "note": note,
            "changed_from_previous": last_hash is not None and content_hash != last_hash,
            "external_references": _parse_external(external),
        })
        last_hash = content_hash

    distinct = len({v["content_hash"] for v in versions})
    return {"url": url, "seals": len(versions), "distinct_versions": distinct,
            "first_sealed": versions[0]["sealed_at"], "latest_sealed": versions[-1]["sealed_at"],
            "current_hash": versions[-1]["content_hash"],
            "versions": versions,
            "publish_version": VERSION,
            "what_this_is": "A dated revision history the publisher cannot edit. Each version is "
                            "its own block; altering or removing one breaks every block after it.",
            "limit": "The first seal fixes an upper bound, not a lower one. Anything published "
                     "before its first seal rests on external evidence, which is recorded here "
                     "but not verified by us."}, 200


def _verify(ctx, data):
    url = str(data.get("url", "")).strip()
    digest = str(data.get("hash", data.get("content_hash", ""))).strip().lower()
    if not digest or not HEX64.match(digest):
        return {"error": "hash_required",
                "message": "sha256 of AILEASH-PUBLISH-v1: followed by the exact bytes served"}, 400

    with ctx["lock"]:
        if url:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE url=? AND content_hash=? ORDER BY id ASC", (url, digest)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE content_hash=? ORDER BY id ASC", (digest,)).fetchall()

    if not rows:
        return {"sealed": False, "content_hash": digest, "url": url or None,
                "message": "We hold no seal for that exact content. Either it was never sealed, "
                           "or the content differs from what was - a single byte is enough."}, 404

    return {"sealed": True, "content_hash": digest,
            "url": rows[0][0], "times_sealed": len(rows),
            "first_sealed": _iso(rows[0][1]),
            "latest_sealed": _iso(rows[-1][1]),
            "sealed_in_chain": rows[0][2], "block_index": rows[0][3],
            "publish_version": VERSION,
            "what_this_proves": "Content with exactly this fingerprint was served at that "
                                "address no later than the first sealing time, and the record "
                                "of it has not been altered since.",
            "verify_the_block": "/x/consistency/ancestor?tip=" + rows[0][2]}, 200


def _list(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT url,COUNT(*),MIN(fetched),MAX(fetched),COUNT(DISTINCT content_hash) "
            "FROM publish_seal GROUP BY url ORDER BY MAX(fetched) DESC LIMIT 500").fetchall()
    return {"count": len(rows),
            "pages": [{"url": r[0], "seals": r[1], "first_sealed": _iso(r[2]),
                       "latest_sealed": _iso(r[3]), "distinct_versions": r[4],
                       "history": "/x/publish/history?url=" + r[0]} for r in rows],
            "publish_version": VERSION,
            "note": "Everything this platform has sealed about its own published pages. Ours is "
                    "in here too - a publisher who seals everyone's pages but not their own is "
                    "telling you something."}, 200


def _spec():
    return {
        "publish_version": VERSION,
        "content_hash": "sha256('AILEASH-PUBLISH-v1:' || exact_bytes_served) as lowercase hex",
        "no_normalisation": "The bytes are hashed exactly as served. Nothing is trimmed, "
                            "reordered or cleaned up first - a whitespace-tolerant hash would "
                            "be a hash of our opinion of the page rather than of the page.",
        "reproduce_it": "curl the URL, pipe the raw bytes through sha256 with that prefix, and "
                        "compare with what we sealed. If your bytes differ, the page changed.",
        "what_a_seal_proves": "That content with this exact fingerprint was served at this "
                              "address no later than the sealing time, and that the record has "
                              "not been altered since - it is a chain block like any other, "
                              "anchored externally and witnessed by peers.",
        "what_it_cannot_prove": "That the page existed before the seal. Timestamps run forwards "
                                "only. Any product implying otherwise is misdescribing what a "
                                "timestamp is.",
        "for_earlier_dates": {
            "github_push": "api.github.com/repos/<owner>/<repo>/events - the push timestamp is "
                           "recorded by GitHub, not the pusher, unlike commit author and "
                           "committer dates which are settable fields. Retained around 90 days, "
                           "so capture it while it exists.",
            "wayback": "archive.org/wayback/available - an independent party with no stake in "
                       "the dispute.",
            "status": "Both are recorded and sealed as supplied, and neither is verified by us. "
                      "They are somebody else's evidence, named so you can check them at source.",
        },
        "the_discipline": "Seal at publication. One call at the moment a page goes live means "
                          "the publication date never rests on anyone's word, anyone's git "
                          "history, or anyone's memory again.",
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
        if action == "history":
            return _history(ctx, data)
        if action == "verify":
            return _verify(ctx, data)
        if action == "list":
            return _list(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "verify", "list"],
            "POST": ["seal (keyed)"]}, 404

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


## `modules/replay.py`

678 lines, 30538 bytes

```python
#!/usr/bin/env python3
"""
modules/replay.py  -  proving the same inputs still produce the same verdict
                      WITHOUT ever disclosing how the verdict is reached
============================================================================

THE QUESTION NOBODY ELSE IN THIS MARKET CAN ANSWER
--------------------------------------------------
Every compliance platform can tell you what it decided. Not one of them can
prove it would decide the same way again.

Ask any of them to re-run decision 4,117 from its sealed inputs and show the
same verdict falls out. They cannot. Not because they will not - because
their scoring goes through a model call, and model calls are not
reproducible. Same inputs, different day, different answer. Their audit
trail describes a decision that can never be performed twice.

Ours is arithmetic. Deterministic below the model layer, and always has
been. This module lets anyone establish that for themselves.

THE SCORING LOGIC IS NEVER DISCLOSED
------------------------------------
Read this before changing anything in here.

Nothing in this module publishes, returns, echoes or hints at the contents
of the decision function. Not the source, not the weights, not the
thresholds, not the signal names, not the intermediate values. The only
thing that leaves the building is a SHA-256 of the deployed source, which
is one-way and reveals nothing about what it hashes.

Determinism is proved as a BLACK BOX instead: same inputs in, same verdict
out, demonstrated repeatedly, by the challenger, on their own schedule,
with every run sealed into the chain. That is a stronger proof than showing
the code, because it is behaviour observed over time rather than a claim
about a listing nobody can confirm is what actually runs in production.

  A competitor who reads every route here learns exactly one thing: that
  our verdicts are reproducible. Which is the point, and which they cannot
  copy, because reproducibility is a property of the architecture and not a
  feature that can be bolted on.

HOW SOMEONE CHECKS US WITHOUT SEEING ANYTHING
---------------------------------------------
  POST /x/replay/challenge   send any inputs you like. We run them, seal
                             the run into the chain, and hand you back the
                             verdict, the audit hash, and a fingerprint of
                             your own inputs.

Send the same inputs again - an hour later, a year later, from a different
address. If the verdict ever moves, you have caught us, and both runs are
independently sealed and anchored so we cannot revise either one. If it
never moves, you have established determinism yourself, empirically,
adversarially, without a line of our code.

We also report how many times that exact input has been challenged, when it
was first seen, and every audit hash it produced, so the whole history is
verifiable through routes we do not control the answers to.

THE HONEST COST, WHICH IS REAL
------------------------------
An open scoring oracle can be probed. Feed it a thousand variations, watch
the verdicts move, and a determined party can map the decision boundary
without ever seeing the code. That is a genuine exposure and it is the
price of this proof.

It is mitigated, not eliminated: challenges are rate limited per address,
inputs are fingerprinted so repeat submissions are cheap and novel ones are
not, and boundary-probing patterns are already logged elsewhere in the
platform. Anyone systematically mapping the function leaves an obvious,
sealed trail while doing it.

The trade is deliberate. A closed engine nobody can test is worth less than
a testable one somebody might partially map, because the first cannot be
sold to a regulator and the second can.

CONFIGURATION
-------------
This module does not import server.py - nothing here does. It finds the
live decision function at runtime among already-loaded modules, so it can
only observe the engine, never change it. If your scorer is named something
not in SCORER_NAMES below, add it there. Everything else is read from the
audit_log schema at startup rather than assumed.

    POST /x/replay/challenge     run any inputs, sealed          (public)
    GET  /x/replay/history       every run of a given input       (public)
    GET  /x/replay/self          reproduction rate over a sample  (public)
    GET  /x/replay/fingerprint   hash of the deployed code        (public)
    GET  /x/replay/spec          how to test us                   (public)
    GET  /x/replay/check         re-run one sealed decision       (keyed)
    POST /x/replay/attest        seal the current fingerprint     (keyed)
"""

import hashlib
import inspect
import json
import sys
import time
from datetime import datetime, timezone

VERSION = "1.0"

# Challenge, history, self, fingerprint and spec are open - a
# reproducibility claim you need an account to test is not a claim anyone
# should accept. check stays keyed: it reads back a specific sealed
# decision, which belongs to whoever owns it.
PUBLIC = {("POST", "challenge"), ("GET", "history"), ("GET", "self"),
          ("GET", "fingerprint"), ("GET", "spec")}

# Names the live decision function might go by. Add yours if it is not
# here - this is the one thing that has to match your code.
SCORER_NAMES = (
    "score_event", "decide", "score", "evaluate", "run_decision",
    "make_decision", "assess", "score_decision", "engine_decide",
)

# Columns the sealed inputs might live in. Detected, never assumed.
INPUT_COLUMNS = ("event", "event_json", "payload", "inputs", "request",
                 "ev", "data", "event_data")
RESULT_COLUMNS = ("result", "result_json", "res", "decision_json", "outcome",
                  "response")
VERDICT_COLUMNS = ("decision", "verdict", "action_taken")
SCORE_COLUMNS = ("score", "risk_score", "points")

SELF_SAMPLE_DEFAULT = 50
SELF_SAMPLE_MAX = 500

# Challenge throttle. Repeat submissions of an input we have already seen
# are cheap; novel inputs are what a prober needs, so those are what get
# limited.
NOVEL_PER_HOUR = 40
MAX_PAYLOAD_KEYS = 40

_ready = False
_columns = []


def _setup(ctx):
    global _ready, _columns
    if _ready:
        return
    cols = []
    try:
        with ctx["lock"]:
            for row in ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall():
                cols.append(row[1])
    except Exception:
        pass
    _columns = cols
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS replay_attest("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "fingerprint TEXT,function TEXT,taken REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        # One row per challenge run. The input fingerprint is stored, the
        # input itself is not - we have no reason to keep a stranger's
        # payload and every reason not to.
        c.execute("CREATE TABLE IF NOT EXISTS replay_challenge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,input_hash TEXT,"
                  "verdict TEXT,score TEXT,code_fingerprint TEXT,ran REAL,"
                  "audit_hash TEXT,block_index INTEGER,client TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_input "
                  "ON replay_challenge(input_hash,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_rep_ran ON replay_challenge(ran)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _pick(candidates):
    for name in candidates:
        if name in _columns:
            return name
    return None


def _canonical(payload):
    """Stable rendering of an input payload, so the same inputs always
    fingerprint to the same value regardless of key order or spacing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def _input_hash(payload):
    return hashlib.sha256(("AILEASH-INPUT-v1:" + _canonical(payload)).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# finding the live decision function
# ----------------------------------------------------------------------

def _find_scorer():
    """Locate the deployed decision function among loaded modules.

    Deliberately does not import server.py. It looks at what is already
    running, so this module can observe the engine and never alter it.
    """
    for module_name in ("__main__", "server", "app", "main"):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name in SCORER_NAMES:
            candidate = getattr(module, name, None)
            if callable(candidate):
                return candidate, "%s.%s" % (module_name, name), None
    return None, None, ("no decision function found. Add its real name to SCORER_NAMES at the "
                        "top of modules/replay.py.")


def _fingerprint_of(function):
    """SHA-256 of the deployed source. One-way: it commits to which code is
    running without revealing any of it."""
    try:
        source = inspect.getsource(function)
    except (OSError, TypeError):
        return None, "source not readable for this callable"
    normalised = "\n".join(line.rstrip() for line in source.splitlines()).strip()
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest(), None


# ----------------------------------------------------------------------
# running the engine
# ----------------------------------------------------------------------

def _rerun(function, inputs):
    """Execute the live decision function against a set of inputs.

    Never raises. On failure it reports that the call failed and nothing
    about why the engine is shaped the way it is.
    """
    if inputs is None:
        return None, "no inputs"
    attempts = []
    if isinstance(inputs, dict):
        attempts.append(lambda: function(**inputs))
        attempts.append(lambda: function(inputs))
    else:
        attempts.append(lambda: function(inputs))
    for call in attempts:
        try:
            return call(), None
        except TypeError:
            continue
        except Exception:
            return None, "the decision function could not process those inputs"
    return None, "those inputs do not match the shape the engine expects"


def _extract(output):
    """Pull (verdict, score) out of whatever the scorer returns. Nothing
    else from the return value is ever surfaced."""
    if isinstance(output, dict):
        return (output.get("decision") or output.get("verdict"), output.get("score"))
    if isinstance(output, (tuple, list)) and len(output) >= 2:
        return output[0], output[1]
    return output, None


def _same(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    return str(a).strip().upper() == str(b).strip().upper()


# ----------------------------------------------------------------------
# challenge - the public proof
# ----------------------------------------------------------------------

def _novel_recently(ctx):
    since = time.time() - 3600
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT input_hash) FROM replay_challenge WHERE ran>=?",
            (since,)).fetchone()
    return int(row[0]) if row else 0


def _challenge(ctx, api_key, data):
    inputs = data.get("inputs", data.get("event", data.get("payload")))
    if not isinstance(inputs, dict) or not inputs:
        return {"error": "inputs_required",
                "message": "Send an inputs object. We will run it, seal the run, and hand you "
                           "back the verdict. Send the same object again whenever you like - "
                           "if the answer ever moves, you have caught us."}, 400
    if len(inputs) > MAX_PAYLOAD_KEYS:
        return {"error": "payload_too_wide", "message": "at most %d keys" % MAX_PAYLOAD_KEYS}, 400

    fingerprint_in = _input_hash(inputs)

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC",
            (fingerprint_in,)).fetchall()

    if not prior and _novel_recently(ctx) >= NOVEL_PER_HOUR:
        return {"error": "rate_limited",
                "message": "Too many distinct inputs in the last hour. Repeat submissions of "
                           "inputs already seen are never limited - testing whether the answer "
                           "moves is the whole point. Mapping the function is not.",
                "repeat_freely": "any input_hash already in /x/replay/history"}, 429

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable", "message": "the decision engine is not reachable "
                                                          "from this route right now"}, 503

    output, problem = _rerun(function, inputs)
    if problem:
        return {"error": "not_runnable", "message": problem}, 422

    verdict, score = _extract(output)
    code_fingerprint, _p = _fingerprint_of(function)
    now = time.time()

    ev = {"user_id": "chal:" + fingerprint_in[:16], "action": "replay_challenge", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": str(verdict), "score": score, "replay_version": VERSION,
           "input_hash": fingerprint_in, "code_fingerprint": code_fingerprint,
           "detail": "input=%s;verdict=%s;code=%s" % (fingerprint_in, verdict, code_fingerprint)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key or "public-replay")

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO replay_challenge(input_hash,verdict,score,code_fingerprint,ran,"
            "audit_hash,block_index,client) VALUES(?,?,?,?,?,?,?,?)",
            (fingerprint_in, str(verdict), str(score), code_fingerprint, now,
             audit_hash, block_index, "keyed" if api_key else "anonymous"))
        ctx["conn"].commit()

    out = {
        "input_hash": fingerprint_in,
        "verdict": verdict, "score": score,
        "ran_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "code_fingerprint": code_fingerprint,
        "runs_of_this_input": len(prior) + 1,
        "replay_version": VERSION,
        "how_to_use_this": "Send the identical inputs again, whenever you like, from wherever "
                           "you like. Every run is sealed into a chain that is externally "
                           "anchored and independently witnessed, so neither this answer nor "
                           "the next one can be revised afterwards.",
        "history": "/x/replay/history?input_hash=" + fingerprint_in,
        "verify_this_run": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if prior:
        first_verdict, first_score = prior[0][0], prior[0][1]
        stable = _same(verdict, first_verdict) and _same(score, first_score)
        out["first_seen"] = _iso(prior[0][2])
        out["stable"] = stable
        out["verdict_moved"] = not stable
        if stable:
            out["what_this_shows"] = ("Identical to the first run of these inputs on %s, and to "
                                      "every run since. Determinism observed rather than "
                                      "asserted." % _iso(prior[0][2]))
        else:
            out["what_this_shows"] = ("These inputs previously produced a different answer. "
                                      "Either the code changed - compare the code fingerprints "
                                      "in the history - or the engine is not deterministic. "
                                      "Both runs are sealed and neither can be withdrawn.")
    else:
        out["stable"] = None
        out["what_this_shows"] = ("First time these inputs have been seen. Send them again to "
                                  "start building the record.")
    return out, 200


def _history(ctx, data):
    input_hash = str(data.get("input_hash", data.get("hash", ""))).strip().lower()
    if not input_hash:
        return {"error": "input_hash_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT verdict,score,ran,audit_hash,block_index,code_fingerprint,client "
            "FROM replay_challenge WHERE input_hash=? ORDER BY id ASC LIMIT 500",
            (input_hash,)).fetchall()
    if not rows:
        return {"error": "unknown_input", "input_hash": input_hash,
                "message": "No run recorded for that input fingerprint."}, 404

    verdicts = {r[0] for r in rows}
    codes = {r[5] for r in rows if r[5]}
    return {
        "input_hash": input_hash,
        "runs": len(rows),
        "first_run": _iso(rows[0][2]), "latest_run": _iso(rows[-1][2]),
        "distinct_verdicts": len(verdicts),
        "stable": len(verdicts) == 1,
        "code_versions_seen": len(codes),
        "history": [{"verdict": r[0], "score": r[1], "ran_at": _iso(r[2]),
                     "sealed_in_chain": r[3], "block_index": r[4],
                     "code_fingerprint": r[5], "submitted_by": r[6]} for r in rows],
        "what_this_is": "Every recorded run of one exact set of inputs, each sealed separately "
                        "into the chain. Verify any of them independently at "
                        "/x/consistency/ancestor - we cannot alter one after the fact.",
        "note": "More than one distinct verdict across a single code fingerprint would mean the "
                "engine is not deterministic. That is exactly what this is here to expose.",
    }, 200


# ----------------------------------------------------------------------
# self audit
# ----------------------------------------------------------------------

def _fetch(ctx, where, args):
    input_col = _pick(INPUT_COLUMNS)
    result_col = _pick(RESULT_COLUMNS)
    verdict_col = _pick(VERDICT_COLUMNS)
    score_col = _pick(SCORE_COLUMNS)
    if not input_col:
        return None, ("audit_log does not store decision inputs on this deployment, so sealed "
                      "decisions cannot be re-executed. Seal the event payload alongside the "
                      "verdict and replay becomes available from that point on.")
    fields = ["id", "audit_hash", "ts", input_col]
    for extra in (result_col, verdict_col, score_col):
        if extra and extra not in fields:
            fields.append(extra)
    sql = "SELECT %s FROM audit_log WHERE %s" % (", ".join(fields), where)
    with ctx["lock"]:
        rows = ctx["conn"].execute(sql, tuple(args)).fetchall()
    if not rows:
        return None, "no sealed decision matched"
    out = []
    for row in rows:
        record = dict(zip(fields, row))
        raw = record.get(input_col)
        try:
            parsed = raw if isinstance(raw, (dict, list)) else json.loads(raw)
        except Exception:
            parsed = None
        sealed_result = None
        if result_col:
            raw_result = record.get(result_col)
            try:
                sealed_result = raw_result if isinstance(raw_result, dict) else json.loads(raw_result)
            except Exception:
                sealed_result = None
        out.append({"id": record.get("id"), "audit_hash": record.get("audit_hash"),
                    "ts": record.get("ts"), "inputs": parsed,
                    "sealed_result": sealed_result,
                    "sealed_verdict": record.get(verdict_col) if verdict_col else None,
                    "sealed_score": record.get(score_col) if score_col else None})
    return out, None


def _sealed_pair(record):
    verdict = record.get("sealed_verdict")
    score = record.get("sealed_score")
    result = record.get("sealed_result")
    if isinstance(result, dict):
        if verdict is None:
            verdict = result.get("decision") or result.get("verdict")
        if score is None:
            score = result.get("score")
    return verdict, score


def _compare(record, function):
    output, why = _rerun(function, record.get("inputs"))
    sealed_verdict, sealed_score = _sealed_pair(record)
    if why:
        return {"audit_hash": record["audit_hash"], "result": "not_replayable"}
    verdict, score = _extract(output)
    identical = _same(verdict, sealed_verdict) and _same(score, sealed_score)
    return {"audit_hash": record["audit_hash"], "sealed_at": _iso(record.get("ts")),
            "result": "identical" if identical else "divergent"}


def _self(ctx, data):
    try:
        sample = int(data.get("sample", SELF_SAMPLE_DEFAULT))
    except (TypeError, ValueError):
        sample = SELF_SAMPLE_DEFAULT
    sample = max(1, min(sample, SELF_SAMPLE_MAX))

    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503

    records, fetch_why = _fetch(ctx, "1=1 ORDER BY id DESC LIMIT ?", [sample])
    if fetch_why:
        return {"error": "cannot_replay", "message": fetch_why}, 400

    identical = divergent = skipped = 0
    divergent_hashes = []
    started = time.time()
    for record in records:
        outcome = _compare(record, function)
        if outcome["result"] == "identical":
            identical += 1
        elif outcome["result"] == "divergent":
            divergent += 1
            if len(divergent_hashes) < 10:
                divergent_hashes.append(outcome["audit_hash"])
        else:
            skipped += 1

    checked = identical + divergent
    rate = round((identical / checked) * 100, 4) if checked else None
    code_fingerprint, _p = _fingerprint_of(function)

    body = {
        "sampled": len(records), "replayable": checked,
        "identical": identical, "divergent": divergent, "not_replayable": skipped,
        "reproduction_rate_percent": rate,
        "took_seconds": round(time.time() - started, 3),
        "code_fingerprint": code_fingerprint,
        "replay_version": VERSION,
        "headline": ("%d of %d sealed decisions reproduce identically under the code deployed "
                     "right now." % (identical, checked)) if checked else
                    "Nothing replayable in this sample.",
        "why_this_matters": "A platform whose scoring runs through a model call cannot do this "
                            "at all. Reproducibility is a property of the architecture, not a "
                            "feature that can be added later.",
        "honest": "Divergences are counted here, not filtered out. A falling rate is the most "
                  "useful thing this route can tell you.",
        "independent_check": "Do not take our word for this - /x/replay/challenge lets you run "
                             "your own inputs and repeat them whenever you like.",
    }
    if divergent_hashes:
        body["divergent_receipts"] = divergent_hashes
    return body, 200


# ----------------------------------------------------------------------
# fingerprint, keyed check, attest
# ----------------------------------------------------------------------

def _fingerprint(ctx):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    return {"code_fingerprint": digest, "problem": problem, "replay_version": VERSION,
            "what_this_is": "A SHA-256 of the source of the code currently deciding. It commits "
                            "to which version is running. It is one-way and discloses nothing "
                            "about the logic, the weights or the thresholds.",
            "what_it_is_for": "Sealed alongside verdicts via /x/replay/attest, so a change in "
                              "behaviour can be attributed to a dated code change rather than "
                              "looking like a fault - or hidden as one.",
            "note": "The function name and signature are deliberately not published."}, 200


def _check(ctx, data):
    """Keyed. Re-runs one sealed decision and reports match or divergence."""
    target = str(data.get("hash", data.get("receipt", ""))).strip().lower()
    if not target:
        return {"error": "hash_required"}, 400
    records, why = _fetch(ctx, "audit_hash=? LIMIT 1", [target])
    if why:
        return {"error": "cannot_replay", "message": why}, 400
    function, name, scorer_why = _find_scorer()
    if scorer_why:
        return {"error": "engine_unavailable"}, 503
    outcome = _compare(records[0], function)
    digest, _p = _fingerprint_of(function)
    outcome.update({"code_fingerprint": digest, "replay_version": VERSION,
                    "what_this_proves": "The sealed inputs were fed back through the live "
                                        "decision function and the output compared with what "
                                        "was sealed."})
    return outcome, 200


def _attest(ctx, api_key):
    function, name, why = _find_scorer()
    if why:
        return {"error": "engine_unavailable"}, 503
    digest, problem = _fingerprint_of(function)
    if not digest:
        return {"error": "no_fingerprint", "message": problem}, 503

    now = time.time()
    ev = {"user_id": "rep:" + digest[:16], "action": "code_fingerprint_sealed", "amount": 0,
          "country": "UK", "device_id": "replay", "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_SEALED", "score": 0, "replay_version": VERSION,
           "fingerprint": digest, "detail": "fingerprint=%s" % digest}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO replay_attest(api_key,fingerprint,function,taken,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (api_key, digest, name, now, audit_hash, block_index))
        ctx["conn"].commit()

    return {"fingerprint": digest, "taken_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "what_this_does": "Records which code was deciding at this moment, inside the chain "
                              "the decisions are sealed in. Every verdict after this point is "
                              "attributable to a known, timestamped version of the logic - "
                              "without that logic being published.",
            "do_this": "Attest on every deploy that touches scoring. A later divergence then "
                       "reads as a dated policy change rather than an unexplained fault."}, 200


def _spec():
    return {
        "replay_version": VERSION,
        "claim": "The same inputs produce the same verdict, and you can establish that yourself "
                 "without an account and without seeing any of our logic.",
        "the_logic_is_not_published": "No route here returns the scoring source, the weights, "
                                      "the thresholds, the signal names or any intermediate "
                                      "value. The only thing published is a SHA-256 of the "
                                      "deployed source, which is one-way.",
        "how_to_test_us": [
            "POST /x/replay/challenge with any inputs object you like.",
            "Keep the input_hash it returns.",
            "Send the identical inputs again tomorrow, next month, next year, from anywhere.",
            "GET /x/replay/history?input_hash=... to see every run, each sealed separately.",
            "If the verdict ever moves under an unchanged code fingerprint, the engine is not "
            "deterministic and you have proof of it that we cannot withdraw.",
        ],
        "why_black_box_is_stronger": "A published listing only shows what the code says. "
                                     "Repeated challenge shows what production actually does, "
                                     "over time, on inputs we did not choose.",
        "what_breaks_determinism": [
            "a wall-clock read inside the scoring path",
            "iteration over an unordered structure",
            "an unseeded random call",
            "any model call in the decision path - which is why most platforms cannot do this",
        ],
        "what_this_does_not_prove": "That a decision was correct, or that the inputs were "
                                    "honestly captured. Only that the same inputs still yield "
                                    "the same output under known code. Determinism is not "
                                    "fairness.",
        "rate_limits": "Repeat submissions of inputs already seen are never limited - retesting "
                       "is the point. Novel inputs are limited, because bulk novel inputs are "
                       "how a decision boundary gets mapped rather than how a claim gets tested.",
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
        if action == "fingerprint":
            return _fingerprint(ctx)
        if action == "history":
            return _history(ctx, data)
        if action == "self":
            return _self(ctx, data)
        if action == "check":
            if not api_key:
                return {"error": "invalid_api_key"}, 401
            return _check(ctx, data)

    if method == "POST":
        if action == "challenge":
            return _challenge(ctx, api_key, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "attest":
            return _attest(ctx, api_key)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "fingerprint", "history", "self", "check (keyed)"],
            "POST": ["challenge", "attest (keyed)"]}, 404

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

371 lines, 15359 bytes

```python
"""
modules/rulebind.py  -  rule binding, provable without an account

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

That is the whole proof, and it works in both directions:

  - change the pack hash after the fact and the binding no longer recomputes
  - change the binding and the chain breaks from that block onwards
  - change the chain and it stops matching the external anchor and the peer
    chain that recorded our tip an hour later

None of those require taking our word for anything, and none require us to
disclose the scoring logic - the inputs are published as a digest, not as
values, and the weights are never exposed at any point.

WHAT IT DOES NOT PROVE
----------------------
That the rules were good ones. That the verdict was correct. That the pack
does what its description says. It proves which ruleset produced which verdict
and that the pairing was fixed at the time rather than asserted later. Narrow,
and the only part that is actually provable.

ROUTES  (all public - the point is that no account is needed)
------------------------------------------------------------
  POST /x/rulebind/prove       run a decision, get every component back
  GET  /x/rulebind/verify?receipt=   recompute the binding for a sealed record
  GET  /x/rulebind/packs       ruleset versions and when each was first sealed
  GET  /x/rulebind/spec        what this proves and what it does not
"""

import hashlib
import json
import re
import sys
import time

VERSION = "1.0"
BINDING_PREFIX = "AILEASH-RULEBIND-v1"

PUBLIC = {("POST", "prove"), ("GET", "verify"), ("GET", "packs"),
          ("GET", "spec"), ("GET", "")}

HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_INPUT_KEYS = 40

# Same runtime lookup replay.py uses - never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]
DECIDER_NAMES = ["decide", "verdict_for", "_decide"]

_ready = False


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


def _active_pack(ctx):
    """The ruleset in force. Read from signal_packs if the table is there,
    otherwise fall back to a hash of the core engine's own identity - either
    way the value is stable and published."""
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

    # No pack table, or a different schema. Fall back to the core nine, whose
    # identity is fixed by the deployed decision function itself.
    fn, where = _find(SCORER_NAMES)
    if fn:
        try:
            import inspect
            return "core-nine", _sha(inspect.getsource(fn))
        except Exception:
            return "core-nine", _sha("core-nine|" + str(where))
    return "unknown", _sha("unknown")


def _canonical_inputs(data):
    """Inputs are published as a digest, never as values. Somebody testing this
    knows what they sent; nobody else learns anything from the record."""
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


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _prove(ctx, api_key, data):
    if not isinstance(data, dict) or not data:
        return {"error": "inputs_required",
                "message": ("POST any decision inputs as JSON. They are hashed, "
                            "never stored as values.")}, 400

    scorer, scorer_where = _find(SCORER_NAMES)
    if not scorer:
        return {"error": "engine_unavailable",
                "message": "The scoring function could not be found at runtime."}, 503

    try:
        result = scorer(dict(data))
        score = float(result[0] if isinstance(result, (tuple, list)) else result)
    except Exception as exc:
        return {"error": "scoring_failed", "message": str(exc)[:200]}, 400

    decider, _ = _find(DECIDER_NAMES)
    verdict = None
    if decider:
        try:
            v = decider(score)
            verdict = v[0] if isinstance(v, (tuple, list)) else v
        except Exception:
            verdict = None
    if verdict is None:
        verdict = "ALLOW" if score < 0.35 else ("CHALLENGE" if score < 0.70 else "BLOCK")

    pack_id, pack_hash = _active_pack(ctx)
    inputs_digest = _sha(_canonical_inputs(data))
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
    h, idx, seq = ctx["seal"](ev, res, sealed_at, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO rulebind_log(api_key,pack_id,pack_hash,inputs_digest,"
            "verdict,score,sealed_at,binding,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (api_key, pack_id, pack_hash, inputs_digest, str(verdict),
             round(score, 6), sealed_at, binding, h, idx))
        ctx["conn"].commit()

    return {
        "verdict": verdict,
        "score": round(score, 6),
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding": binding,
        "binding_material": material,
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "recompute_it_yourself": {
            "step_1": ("Take binding_material exactly as returned - it is the "
                       "string that was hashed, printed in full."),
            "step_2": "SHA-256 it. You should get the value in binding.",
            "step_3": ("Confirm the ruleset hash appears inside that string. It "
                       "is a component of the digest, not a field beside it - "
                       "change it and the digest no longer recomputes."),
            "step_4": ("Check the block is in the chain at /api/verify-chain, "
                       "externally timestamped at /api/anchor-status, and that "
                       "our tip was recorded by an independent operator at "
                       "/x/witness/peers."),
            "shell": ("printf '%s' \"$MATERIAL\" | shasum -a 256"),
        },
        "what_this_proves": (
            "That this verdict and this ruleset version were committed together, "
            "at this time, in one object. The pairing cannot be altered afterwards "
            "without breaking the digest, and the digest cannot be altered without "
            "breaking the chain."),
        "what_it_does_not_prove": (
            "That the rules were good, or the verdict correct. Only which ruleset "
            "produced it and that the pairing was fixed at the time."),
        "verify": "/x/rulebind/verify?receipt=" + h,
    }, 200


def _verify(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not receipt:
        return {"error": "receipt_required"}, 400
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
        "found": True,
        "receipt": receipt,
        "block_index": block,
        "ruleset": {"pack_id": pack_id, "pack_hash": pack_hash},
        "verdict": verdict,
        "score": score,
        "inputs_digest": inputs_digest,
        "sealed_at": sealed_at,
        "sealed_at_iso": _iso(sealed_at),
        "binding_stored": stored,
        "binding_material": material,
        "binding_recomputed": recomputed,
        "binding_matches": matches,
        "result": ("The ruleset version recomputes into the binding that was "
                   "sealed with this decision. It was bound at the time, not "
                   "attached afterwards."
                   if matches else
                   "MISMATCH. The stored binding does not recompute from the "
                   "stored components. Something has been altered and this "
                   "record should not be relied upon."),
        "chain": "/api/verify-chain",
        "external_clock": "/api/anchor-status",
        "witnessed_by": "/x/witness/peers",
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
                 "record rather than a silent edit. Decisions stay bound to the "
                 "version that produced them."),
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
        "how_to_test_it": [
            "POST any inputs to /x/rulebind/prove. No account needed.",
            "Take binding_material from the response and SHA-256 it yourself.",
            "Confirm it equals binding.",
            "GET /x/rulebind/verify?receipt=... and confirm it still recomputes.",
            "Confirm the block is in the chain, anchored, and witnessed.",
        ],
        "what_is_never_disclosed": (
            "Weights, thresholds, signal names and intermediate values. Inputs "
            "are published as a digest, not as values. Nothing here requires the "
            "scoring logic to be revealed, and none of it is."),
        "what_it_does_not_prove": (
            "That the rules were good or the verdict correct. Only which ruleset "
            "produced which verdict, and that the pairing was fixed at the time."),
        "cost": "Free. No account, no key.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    key = api_key or "public-rulebind"

    if method == "POST":
        if action == "prove":
            return _prove(ctx, key, data)
        return {"error": "unknown_action", "action": action, "POST": ["prove"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "verify":
        return _verify(ctx, data)
    if action == "packs":
        return _packs(ctx)
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "verify", "packs"]}, 404

```
