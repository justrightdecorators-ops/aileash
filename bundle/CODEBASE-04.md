# Codebase — part 4 of 18

Contains:
- `modules/fingerprint.py`
- `modules/lineage.py`
- `modules/mutual.py`
- `modules/network.py`
- `modules/oversight.py`


## `modules/fingerprint.py`

550 lines, 22358 bytes

```python
"""
modules/fingerprint.py  -  is somebody else running my scoring function?

THE IDEA
--------
The scoring engine is deterministic. Identical inputs give an identical score,
every time, forever. That is a compliance property - and it is also a
signature.

So: fire a fixed battery of carefully chosen inputs at any scoring endpoint,
fire the same battery at our own, and compare the two sets of numbers.

  identical across 24 varied vectors        it is this function
  identical shape, different scale          it is this function, reweighted
  same ordering, different curve            similar design, not this code
  unrelated                                 unrelated

WHY THE VECTORS ARE CHOSEN THE WAY THEY ARE
-------------------------------------------
Random inputs would only catch a straight copy. These are picked to probe the
specific design decisions in the function, because those are what survive
someone renaming things or nudging a weight:

  saturation points   velocity terms saturate at different counts per window,
                      so a burst and a grind separate. Vectors sit either side
                      of each saturation point.
  curve shape         amount is log-scaled, so small sums move the score far
                      more than large ones. Vectors walk that curve.
  normalisation       the continuous weights sum to 1.00 and the boolean
                      geography terms sit outside it. Vectors isolate that.
  asymmetry           trust contributes inversely and dominates. Vectors sweep
                      trust alone with everything else held flat.

A copy that renamed every field and changed nothing else matches exactly. A
copy that shifted the weights still tracks the shape, because the saturation
points and the log curve are structural rather than parametric.

WHAT IT CANNOT DO
-----------------
It only sees endpoints it can reach. A private product behind a key with no
free tier is invisible to this, and no amount of cleverness changes that.

It also proves similarity, never theft. Two people can converge on similar
weights honestly. What this produces is a dated, sealed measurement - which is
evidence, not a verdict, and the distinction matters if it is ever put in
front of anyone.

EVERY RUN IS SEALED
-------------------
The probe, the target, the vectors and the result all go into the chain. So a
comparison run today is provable as having been run today, rather than
assembled afterwards to fit an argument.

ROUTES  (all keyed - this is not a public toy)
----------------------------------------------
  POST /x/fingerprint/self      score the battery on our own engine
  POST /x/fingerprint/probe     url, plus optional field mapping. Compare.
  GET  /x/fingerprint/history   previous probes and their verdicts
  GET  /x/fingerprint/vectors   the battery itself
  GET  /x/fingerprint/spec      what a verdict means and does not mean
"""

import ipaddress
import json
import math
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = set()          # nothing public. deliberately.

FETCH_TIMEOUT = 10
MAX_BYTES = 200000
POLITE_DELAY = 0.4      # do not hammer somebody else's server
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# Where the live scorer might be found. Same approach as replay.py - look it
# up at runtime, never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]

_ready = False


# ----------------------------------------------------------------------
# the battery
# ----------------------------------------------------------------------
# Each vector is (label, signals). Signals use the engine's own internal
# names; the probe maps them to whatever the target calls things.

def _v(trust=0.5, v60=0, v5m=0, v1h=0, amount=0.0,
       device_risk=0.0, anomaly=0.0, country_shift=False, unsafe_country=False):
    return {"trust": trust, "v60": v60, "v5m": v5m, "v1h": v1h,
            "amount": amount, "device_risk": device_risk, "anomaly": anomaly,
            "country_shift": country_shift, "unsafe_country": unsafe_country}


VECTORS = [
    # --- trust sweep, everything else flat. Isolates the dominant term.
    ("trust-000", _v(trust=0.00)),
    ("trust-025", _v(trust=0.25)),
    ("trust-050", _v(trust=0.50)),
    ("trust-075", _v(trust=0.75)),
    ("trust-100", _v(trust=1.00)),

    # --- velocity: either side of each window's saturation point.
    ("v60-under",   _v(v60=10)),
    ("v60-at",      _v(v60=20)),
    ("v60-over",    _v(v60=40)),      # saturated: must equal v60-at
    ("v5m-under",   _v(v5m=25)),
    ("v5m-at",      _v(v5m=50)),
    ("v5m-over",    _v(v5m=100)),     # saturated
    ("v1h-under",   _v(v1h=100)),
    ("v1h-at",      _v(v1h=200)),
    ("v1h-over",    _v(v1h=400)),     # saturated

    # --- burst vs grind: same total actions, different distribution.
    ("burst",       _v(v60=20, v5m=20, v1h=20)),
    ("grind",       _v(v60=1,  v5m=8,  v1h=200)),

    # --- amount: walks the log curve. Small steps low, big steps high.
    ("amt-10",      _v(amount=10.0)),
    ("amt-100",     _v(amount=100.0)),
    ("amt-1000",    _v(amount=1000.0)),
    ("amt-10000",   _v(amount=10000.0)),
    ("amt-50000",   _v(amount=50000.0)),   # saturated

    # --- the boolean geography terms, isolated.
    ("geo-shift",   _v(country_shift=True)),
    ("geo-unsafe",  _v(unsafe_country=True)),
    ("geo-both",    _v(country_shift=True, unsafe_country=True)),

    # --- the other two continuous signals.
    ("dev-risk",    _v(device_risk=1.0)),
    ("anomaly",     _v(anomaly=1.0)),

    # --- everything at once. Tests the clamp and the normalisation.
    ("max-all",     _v(trust=0.0, v60=40, v5m=100, v1h=400, amount=50000.0,
                       device_risk=1.0, anomaly=1.0,
                       country_shift=True, unsafe_country=True)),
    ("min-all",     _v(trust=1.0)),
]

# Default mapping from our internal signal names to a target's request body.
DEFAULT_FIELDS = {
    "trust": "trust", "v60": "v60", "v5m": "v5m", "v1h": "v1h",
    "amount": "amount", "device_risk": "device_risk", "anomaly": "anomaly",
    "country_shift": "country_shift", "unsafe_country": "unsafe_country",
}
SCORE_KEYS = ["score", "risk_score", "value", "result", "rating", "confidence"]


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS fingerprint_probe("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,target TEXT,"
            "ran REAL,vectors INTEGER,answered INTEGER,exact INTEGER,"
            "verdict TEXT,correlation REAL,detail TEXT,audit_hash TEXT,"
            "block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_fp_target ON fingerprint_probe(target)")
        ctx["conn"].commit()
    _ready = True


# ----------------------------------------------------------------------
# our own engine
# ----------------------------------------------------------------------

def _find_scorer():
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in SCORER_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _score_locally():
    """Run the battery through the live engine. Returns (scores, source, error)."""
    fn, where = _find_scorer()
    if not fn:
        return None, None, ("could not find the scoring function at runtime - "
                            "add its name to SCORER_NAMES")
    out = []
    for label, signals in VECTORS:
        try:
            result = fn(dict(signals))
            score = result[0] if isinstance(result, (tuple, list)) else result
            out.append((label, round(float(score), 6)))
        except Exception as exc:
            return None, where, "scorer raised on %s: %s" % (label, exc)
    return out, where, None


# ----------------------------------------------------------------------
# reaching a target - same guards as witness.py
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


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
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _post(url, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json",
         "User-Agent": "aileash-fingerprint/%s" % VERSION}
    if headers:
        h.update(headers)
    request = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_BYTES)
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_BYTES)
        except Exception:
            raw = b""
        status = exc.code
    except Exception as exc:
        return 0, "unreachable (%s)" % type(exc).__name__
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return status, raw.decode("utf-8", "replace")[:300]


def _extract_score(payload, key_hint=None):
    """Pull a 0..1 style number out of whatever came back."""
    if isinstance(payload, (int, float)):
        return float(payload)
    if not isinstance(payload, dict):
        return None
    keys = ([key_hint] if key_hint else []) + SCORE_KEYS
    for k in keys:
        if k and k in payload:
            v = payload[k]
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).strip())
            except (TypeError, ValueError):
                pass
    # one level down
    for v in payload.values():
        if isinstance(v, dict):
            found = _extract_score(v, key_hint)
            if found is not None:
                return found
    return None


# ----------------------------------------------------------------------
# comparison
# ----------------------------------------------------------------------

def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def _rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = float(position)
    return ranks


def _compare(ours, theirs):
    """ours/theirs are lists of (label, score). theirs may contain None."""
    paired = [(l, o, t) for (l, o), (_, t) in zip(ours, theirs) if t is not None]
    answered = len(paired)
    if answered < 3:
        return {"verdict": "INCONCLUSIVE", "answered": answered,
                "why": "too few vectors came back to compare anything"}

    a = [p[1] for p in paired]
    b = [p[2] for p in paired]
    exact = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 1e-6)
    close = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 0.01)
    pearson = _pearson(a, b)
    spearman = _pearson(_rank(a), _rank(b))

    # a linear fit: are they our scores, scaled and shifted?
    ma, mb = sum(a) / answered, sum(b) / answered
    va = sum((x - ma) ** 2 for x in a)
    slope = (sum((a[i] - ma) * (b[i] - mb) for i in range(answered)) / va) if va > 0 else None
    intercept = (mb - slope * ma) if slope is not None else None
    residual = None
    if slope is not None:
        residual = max(abs(b[i] - (slope * a[i] + intercept)) for i in range(answered))

    if exact == answered:
        verdict = "IDENTICAL"
        why = ("Every vector matched to six decimal places. Two independently "
               "written scoring functions do not do this.")
    elif exact >= answered * 0.8:
        verdict = "IDENTICAL"
        why = ("%d of %d vectors matched exactly. The rest are consistent with "
               "a small local change on top of the same function." % (exact, answered))
    elif residual is not None and residual < 0.02 and pearson and pearson > 0.99:
        verdict = "DERIVED"
        why = ("Not identical, but every score fits ours scaled by %.3f and "
               "shifted by %.3f, within %.4f. That is this function reweighted, "
               "not a different one." % (slope, intercept, residual))
    elif spearman is not None and spearman > 0.95:
        verdict = "SAME SHAPE"
        why = ("Different numbers, but the same ordering across the battery "
               "(rank correlation %.3f). Consistent with the same design - the "
               "same saturation points and the same curve - rather than the "
               "same code." % spearman)
    elif pearson is not None and pearson > 0.8:
        verdict = "SIMILAR"
        why = ("Correlated (%.3f) but not tightly. Risk scorers tend to agree "
               "roughly on what looks risky, so this is weak on its own." % pearson)
    else:
        verdict = "UNRELATED"
        why = "No meaningful relationship to our scoring."

    return {
        "verdict": verdict, "why": why,
        "vectors": len(ours), "answered": answered,
        "exact_matches": exact, "within_0.01": close,
        "correlation": round(pearson, 4) if pearson is not None else None,
        "rank_correlation": round(spearman, 4) if spearman is not None else None,
        "best_fit": ({"scale": round(slope, 4), "shift": round(intercept, 4),
                      "worst_residual": round(residual, 5)}
                     if slope is not None else None),
        "per_vector": [{"vector": p[0], "ours": p[1], "theirs": p[2],
                        "delta": round(p[2] - p[1], 6)} for p in paired],
    }


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _self(ctx, api_key):
    scores, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503
    return {"source": where, "vectors": len(scores),
            "scores": [{"vector": l, "score": s} for l, s in scores],
            "note": ("This is the baseline every probe is compared against. It "
                     "reveals outputs, never weights.")}, 200


def _probe(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    ok, why = _url_allowed(url)
    if not ok:
        return {"error": "bad_target", "message": why}, 400

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    mapping = dict(DEFAULT_FIELDS)
    mapping.update({k: str(v) for k, v in fields.items() if isinstance(v, str)})
    score_key = data.get("score_key")
    extra = data.get("body") if isinstance(data.get("body"), dict) else {}
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    headers = {str(k)[:60]: str(v)[:300] for k, v in list(headers.items())[:8]}

    ours, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503

    theirs = []
    failures = []
    for label, signals in VECTORS:
        body = dict(extra)
        for internal, external in mapping.items():
            body[external] = signals[internal]
        status, payload = _post(url, body, headers)
        if status < 200 or status >= 300:
            theirs.append((label, None))
            if len(failures) < 5:
                failures.append({"vector": label, "http": status,
                                 "response": payload if isinstance(payload, (dict, list))
                                 else str(payload)[:200]})
        else:
            theirs.append((label, _extract_score(payload, score_key)))
        time.sleep(POLITE_DELAY)

    result = _compare(ours, theirs)
    ts = time.time()

    detail = ("target=" + url + ";verdict=" + result["verdict"] +
              ";exact=" + str(result.get("exact_matches", 0)) +
              "/" + str(result.get("answered", 0)))
    ev = {"user_id": "fp:" + urlparse(url).hostname, "action": "fingerprint_probe",
          "amount": 0, "country": "UK", "device_id": "fingerprint",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_" + result["verdict"].replace(" ", "_"),
           "score": 0, "fingerprint_version": VERSION, "target": url,
           "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO fingerprint_probe(api_key,target,ran,vectors,answered,"
            "exact,verdict,correlation,detail,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, ts, result.get("vectors"), result.get("answered"),
             result.get("exact_matches"), result["verdict"],
             result.get("correlation"), detail, h, idx))
        ctx["conn"].commit()

    out = dict(result)
    out.update({
        "target": url,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "what_this_is": ("A dated, sealed measurement of similarity. It is "
                         "evidence, not an accusation, and it does not "
                         "establish that anything was copied."),
    })
    if failures:
        out["failures"] = failures
        out["failure_note"] = ("Some vectors were rejected. If the target wants "
                               "different field names, pass a \"fields\" map and "
                               "run it again.")
    return out, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT target,ran,verdict,exact,answered,correlation,audit_hash,block_index"
            " FROM fingerprint_probe WHERE api_key=? ORDER BY id DESC LIMIT 100",
            (api_key,)).fetchall()
    return {"probes": [{
        "target": r[0],
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
        "verdict": r[2], "exact_matches": r[3], "answered": r[4],
        "correlation": r[5], "receipt": r[6], "block_index": r[7],
    } for r in rows], "count": len(rows)}, 200


def _vectors():
    return {"count": len(VECTORS),
            "vectors": [{"label": l, "signals": s} for l, s in VECTORS],
            "why_these": ("Chosen to sit either side of each saturation point, "
                          "to walk the amount curve, and to isolate each term. "
                          "Random inputs would only catch a straight copy.")}, 200


def _spec():
    return {
        "module": "fingerprint", "version": VERSION,
        "question_it_answers": "Is this endpoint running my scoring function?",
        "verdicts": {
            "IDENTICAL": "Every vector matches. Independently written functions do not do this.",
            "DERIVED": "Not identical, but every score is ours scaled and shifted. Reweighted, not rewritten.",
            "SAME SHAPE": "Different numbers, same ordering. Same design decisions, probably not the same code.",
            "SIMILAR": "Loosely correlated. Weak - risk scorers broadly agree on what looks risky.",
            "UNRELATED": "No meaningful relationship.",
            "INCONCLUSIVE": "Too few vectors came back.",
        },
        "limits": [
            "Only reaches endpoints it can reach. A private product with no free tier is invisible to this.",
            "Proves similarity, never theft. Two people can converge honestly.",
            "A target that rate limits, randomises or rounds heavily will read as INCONCLUSIVE rather than clean.",
        ],
        "every_run_is_sealed": ("The probe, the target and the result go into the "
                                "chain, so a comparison run today is provable as "
                                "having been run today."),
        "manners": "One request per vector with a %.1fs gap. It is a measurement, not a load test." % POLITE_DELAY,
    }, 200


def handle(method, action, data, api_key, ctx):
    # key first, before anything touches the database
    if not api_key:
        return {"error": "invalid_api_key"}, 401
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "self":
            return _self(ctx, api_key)
        if action == "probe":
            return _probe(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["self", "probe"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "history":
        return _history(ctx, api_key)
    if action == "vectors":
        return _vectors()
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "vectors"]}, 404

```


## `modules/lineage.py`

528 lines, 24761 bytes

```python
#!/usr/bin/env python3
"""
modules/lineage.py  -  provenance that crosses company boundaries
=================================================================

WHERE EVERY AUDIT TRAIL STOPS
-----------------------------
At the edge of the company that wrote it.

A lender holds a score. The score came from a scoring supplier, which used
a model, which was trained on a data snapshot bought from someone else.
Four organisations, four audit trails, none of which reference each other.
Ask "what produced this outcome" and you get four separate answers and no
way to join them up.

Every framework written in the last three years assumes somebody can trace
an outcome across parties. Nobody can. Not because it is hard - because
each party's evidence is only worth anything inside that party's own
system, so joining them up would mean trusting whoever did the joining.

WHY THIS WORKS WHEN A SHARED DATABASE WOULD NOT
-----------------------------------------------
The obvious approach is a consortium: everyone writes to one ledger,
governed by someone. That fails on the first question anybody asks, which
is who runs it, and it never gets built.

This needs none of that, because the pieces already exist:

  A chain tip already commits to everything sealed beneath it.
  That tip is already handed to peers hourly and sealed into THEIR chains.
  Those chains are anchored externally and witnessed in turn.

So a receipt can already be walked up to a tip, and that tip already sits
inside chains its issuer does not control. The trust problem is solved
before lineage is even mentioned.

The only thing missing was the sideways link: a decision recording which
receipts fed it, and which chain each came from. That is what this module
adds. One field, and the graph composes itself.

Nobody opts into provenance. They opt into witnessing, which they already
want, and provenance falls out of it.

WHAT AN EDGE IS AND IS NOT
--------------------------
An edge is a sealed, dated, non-repudiable CLAIM by the declaring party
that these inputs fed that decision. Sealing does not make the claim true.
What it removes is the ability to revise it quietly afterwards, which is
the part that matters when an outcome is disputed a year later.

Every edge is itself a chain entry. So the provenance graph is covered by
the same completeness, consistency and witnessing guarantees as everything
else - you cannot delete an inconvenient edge without breaking the chain,
and you cannot add one after the fact without the timestamp showing it.

THE PART THAT IS WORTH MORE THAN THE TRACING
--------------------------------------------
    GET /x/lineage/impact?receipt=

Trace runs upstream: what produced this. Impact runs downstream: what did
this produce.

When a data provider retracts a snapshot, or a model version turns out to
be faulty, or an upstream decision is overturned, the question every
regulator asks is which outputs were affected. Today that answer takes
weeks of email and is never complete. Here it is a query, and it crosses
company boundaries, and the answer is itself provable.

That is corrective action under Article 20 turned from a fire drill into a
lookup.

VERIFICATION WITHOUT TRUSTING ANY PARTY IN THE CHAIN
----------------------------------------------------
This module never asserts that a remote hop is valid. It returns the exact
routes a third party should call to check each hop themselves - on our
chain and on everybody else's. An auditor verifies the whole graph without
trusting us, the supplier, or anyone in between.

HONEST LIMITS
-------------
  - An edge is a claim, sealed and dated. It is not proof the inputs were
    the real ones, only that this is what was declared and when.
  - A cross-chain hop can only be checked while the other party keeps
    their routes up. A dead peer leaves a stub in the graph - visible,
    which is the honest outcome, rather than silently resolved.
  - Declaring inputs is voluntary. A party that declares nothing is not
    caught out by this module; they are simply the point where somebody
    else's lineage goes dark, and their customer is the one who notices.
  - We record edges pointing at other chains. We do not fetch from them
    here - fetching is what /x/witness does, with its SSRF controls, and
    duplicating that machinery in a second place would be a mistake.

    POST /x/lineage/declare      record what fed a decision      (keyed)
    GET  /x/lineage/trace        walk upstream                    (public)
    GET  /x/lineage/impact       walk downstream                  (public)
    GET  /x/lineage/receipt      portable proof for an output     (public)
    GET  /x/lineage/spec         the format and how to check it   (public)
"""

import re
import time
from datetime import datetime, timezone

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Everything except declaring is open. The whole point is that a party
# three hops downstream - who has no relationship with us at all - can
# follow the graph and check it.
PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec")}

OUR_CHAIN_NAME = "aileash"
OUR_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS lineage_edge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "child_chain TEXT,child_receipt TEXT,"
                  "parent_chain TEXT,parent_receipt TEXT,parent_base TEXT,"
                  "role TEXT,note TEXT,declared REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_child "
                  "ON lineage_edge(child_receipt)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_parent "
                  "ON lineage_edge(parent_receipt)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lin_unique "
                  "ON lineage_edge(child_receipt,parent_chain,parent_receipt)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_chain(value):
    value = str(value or "").strip().lower()
    return value[:80] if value else ""


def _exists_locally(ctx, receipt):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1", (receipt,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _verification_plan(chain, receipt, base=None):
    """The exact calls a third party makes to check one hop themselves.

    We never tell anyone a hop is valid. We tell them how to find out
    without asking us again.
    """
    root = (base or OUR_BASE).rstrip("/") if chain != OUR_CHAIN_NAME else OUR_BASE
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % OUR_BASE,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (OUR_BASE, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


# ----------------------------------------------------------------------
# declare
# ----------------------------------------------------------------------

def _declare(ctx, api_key, data):
    child = str(data.get("receipt", data.get("child", ""))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(data.get("chain") or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs", "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared = []
    for item in inputs:
        if not isinstance(item, dict):
            return {"error": "bad_input", "message": "each input must be an object"}, 400
        parent = str(item.get("receipt", "")).strip().lower()
        if not HEX64.match(parent):
            return {"error": "bad_input_receipt",
                    "message": "every input needs a 64 character hex receipt"}, 400
        parent_chain = _clean_chain(item.get("chain") or OUR_CHAIN_NAME)
        if parent_chain == child_chain and parent == child:
            return {"error": "self_reference",
                    "message": "a decision cannot be its own input"}, 400
        role = str(item.get("role", "input")).strip().lower()
        if role not in ROLES:
            role = "other"
        base = str(item.get("base", item.get("url", "")) or "").strip()[:300]
        note = str(item.get("note", "") or "").strip()[:200]
        prepared.append((parent_chain, parent, base, role, note))

    now = time.time()
    summary = ";".join("%s/%s:%s" % (c, r[:12], role) for c, r, _b, role, _n in prepared)
    ev = {"user_id": "lin:" + child[:16], "action": "lineage_declared", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "LINEAGE_SEALED", "score": 0, "lineage_version": VERSION,
           "child_chain": child_chain, "child_receipt": child,
           "input_count": len(prepared),
           "detail": "child=%s;inputs=%s" % (child, summary)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    written, duplicates = 0, 0
    with ctx["lock"]:
        for parent_chain, parent, base, role, note in prepared:
            try:
                ctx["conn"].execute(
                    "INSERT INTO lineage_edge(api_key,child_chain,child_receipt,parent_chain,"
                    "parent_receipt,parent_base,role,note,declared,audit_hash,block_index) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (api_key, child_chain, child, parent_chain, parent, base or None,
                     role, note or None, now, audit_hash, block_index))
                written += 1
            except Exception:
                duplicates += 1
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (OUR_BASE, child)}, 200


# ----------------------------------------------------------------------
# walking the graph
# ----------------------------------------------------------------------

def _parents(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT parent_chain,parent_receipt,parent_base,role,note,declared,audit_hash "
            "FROM lineage_edge WHERE child_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _children(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT child_chain,child_receipt,role,declared,audit_hash "
            "FROM lineage_edge WHERE parent_receipt=? ORDER BY id ASC", (receipt,)).fetchall()


def _walk(ctx, start, depth, upstream):
    """Breadth-first walk with cycle and size protection.

    Anything on a chain we do not hold locally becomes a frontier entry -
    named, with a verification plan, and explicitly not resolved by us.
    """
    seen = {start}
    nodes, edges, frontier = [], [], []
    queue = [(start, 0)]
    truncated = False

    while queue:
        receipt, level = queue.pop(0)
        if level >= depth or len(nodes) >= MAX_NODES:
            if queue or level >= depth:
                truncated = truncated or bool(queue)
            continue

        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)
        for row in rows:
            if upstream:
                chain, other, base, role, note, declared, sealed = row
            else:
                chain, other, role, declared, sealed = row
                base, note = None, None

            edges.append({
                "from": other if upstream else receipt,
                "to": receipt if upstream else other,
                "role": role, "note": note,
                "declared_at": _iso(declared),
                "declaration_sealed_as": sealed,
                "chain": chain,
            })

            local = (chain == OUR_CHAIN_NAME) and _exists_locally(ctx, other)
            if not local:
                if not any(f["receipt"] == other for f in frontier):
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated


def _depth_arg(data):
    try:
        depth = int(data.get("depth", MAX_DEPTH))
    except (TypeError, ValueError):
        depth = MAX_DEPTH
    return max(1, min(depth, MAX_DEPTH))


def _trace(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [],
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt),
            "how_to_verify_this": "Every node carries the routes to check it on its own chain. "
                                  "Nothing here asks you to take our word for a hop, including "
                                  "the hops on our own chain.",
            "what_an_edge_is": "A sealed, dated claim by the declaring party that these inputs "
                               "fed that decision. Sealing makes it non-repudiable, not true.",
            "frontier_note": "External entries are named but not resolved here. Run their "
                             "verification plans against their own hosts - that is what makes "
                             "the graph checkable without a shared database."}, 200


def _impact(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=False)
    affected = len(nodes)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": affected, "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "lineage_version": VERSION,
            "what_this_is_for": "If this input is retracted, wrong, or overturned, these are the "
                                "decisions that declared a dependency on it. This is the answer "
                                "to the first question asked after any upstream failure, and it "
                                "normally takes weeks of email to assemble incompletely.",
            "corrective_action": "The list is itself sealed and dated, so the scope of a recall "
                                 "can be shown to have been determined honestly rather than "
                                 "narrowed to suit.",
            "limits": "Only covers dependencies that were declared. A downstream party who "
                      "declared nothing does not appear - which is a fact about them rather "
                      "than a gap here."}, 200


# ----------------------------------------------------------------------
# the portable receipt - proof that travels with an output
# ----------------------------------------------------------------------

def _receipt(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "verify": _verification_plan(r[0], r[1], r[2])} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (OUR_BASE, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % OUR_BASE,
            "nothing_was_left_out": "%s/x/complete/periods" % OUR_BASE,
            "who_witnesses_us": "%s/x/witness/peers" % OUR_BASE,
            "our_current_tip": "%s/x/witness/tip" % OUR_BASE,
            "the_engine_reproduces": "%s/x/replay/spec" % OUR_BASE,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (OUR_BASE, receipt),
        },
        "offline_verifier": "aileash_verify.py - one file, no dependencies, no network. Save "
                            "this document and check it on your own machine, today or in four "
                            "years.",
        "what_you_can_establish": [
            "this decision is in a log that has not been rewritten",
            "that log is witnessed by parties we do not control",
            "the period it sits in declared its total before anyone asked",
            "the same inputs still produce the same verdict",
            "and what fed it, hop by hop, across every company involved",
        ],
        "what_you_cannot": "That the decision was right, or that the inputs were honest. "
                           "Cryptography establishes what happened and when. It does not "
                           "establish that what happened was correct, and anybody telling you "
                           "otherwise is selling something.",
        "send_this_on": "Attach it to the output it describes. Whoever receives it can verify "
                        "without an account, without contacting us, and without trusting anyone "
                        "in the chain including the sender.",
    }, 200


def _spec():
    return {
        "lineage_version": VERSION,
        "idea": "A decision records the receipts of its inputs and which chain each came from. "
                "Nothing else is needed, because a chain tip already commits to everything "
                "beneath it and is already witnessed by parties its operator does not control.",
        "why_no_consortium": "A shared ledger needs a governor and never gets built. This needs "
                             "no agreement between parties beyond each one sealing its own work "
                             "and publishing a tip.",
        "declare": {
            "route": "POST /x/lineage/declare (keyed)",
            "body": {"receipt": "<64 hex, the decision>",
                     "inputs": [{"chain": "<who it came from>", "receipt": "<64 hex>",
                                 "role": "one of %s" % ", ".join(ROLES),
                                 "base": "<their public https base, optional>"}]},
        },
        "roles": list(ROLES),
        "trace": "GET /x/lineage/trace?receipt= - upstream, what produced this",
        "impact": "GET /x/lineage/impact?receipt= - downstream, what this produced",
        "portable_receipt": "GET /x/lineage/receipt?receipt= - a document that travels with an "
                            "output and lets the recipient verify it independently",
        "verifying_a_hop": "Each node carries the routes to check it on its own chain: an "
                           "ancestry proof that the receipt is still there, a completeness "
                           "check that nothing was omitted from its period, and the witness "
                           "list showing who else holds that chain's tips.",
        "adopting_it": "Implement three public routes on your own system - a tip, an observe, "
                       "and an ancestry check - and declare your inputs. There is nothing to "
                       "join, nobody to ask, and no fee. If you can serve a tip, you are in.",
        "honest": "An edge is a dated, sealed claim about what fed a decision. It cannot be "
                  "quietly revised later. It was never proof that the claim was true, and this "
                  "module does not pretend otherwise.",
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
        if action == "trace":
            return _trace(ctx, data)
        if action == "impact":
            return _impact(ctx, data)
        if action == "receipt":
            return _receipt(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "declare":
            return _declare(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "trace", "impact", "receipt"],
            "POST": ["declare (keyed)"]}, 404

```


## `modules/mutual.py`

447 lines, 15467 bytes

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
#   tip_url      where we GET their current tip
#   observe_url  where we POST ours so they record it
PEERS = [
    {
        "name": "red-flag-ai-pro",
        "tip_url": "https://www.redflagaipro.com/api/witness/tip",
        "observe_url": "https://www.redflagaipro.com/api/witness/anchor",
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
    headers = {"Accept": "application/json", "User-Agent": "aileash-mutual/1.1"}
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


def _extract_tip(body):
    """Pull (tip, height) out of whatever shape a tip route returns."""
    if not isinstance(body, dict):
        return None, None
    tip = body.get("tip") or body.get("hash") or body.get("head")
    height = body.get("height", body.get("count", body.get("entries")))
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
    """Hand our tip to one peer so they record it. Outbound only."""
    keys = peer.get("keys", DEFAULT_PUSH_KEYS)
    values = {
        "chain": OUR_CHAIN_NAME,
        "tip": tip,
        "count": height,
        "ts": _now(),
        "url": OUR_PUBLIC_URL,
    }
    payload = {keys.get(k, k): v for k, v in values.items()}
    status, body = _http(peer["observe_url"], payload)
    result = {
        "peer": peer["name"],
        "direction": "push",
        "url": peer["observe_url"],
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
            "hint": "no tip field in their reply - add the field name to _extract_tip",
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
                "peers": [
                    {"name": p["name"], "tip_url": p["tip_url"],
                     "observe_url": p["observe_url"]}
                    for p in PEERS
                ],
                "parallel_fetch": MAX_PARALLEL_PEERS,
                "note": "Witnessing is only mutual if both columns are live.",
            })
        if action == "status":
            with _lock:
                return _reply({
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
