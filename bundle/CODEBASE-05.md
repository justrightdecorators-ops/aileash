# Codebase — part 5 of 28

Contains:
- `modules/fingerprint.py`
- `modules/heartbeat.py`
- `modules/investor.py`
- `modules/lineage.py`


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


## `modules/heartbeat.py`

872 lines, 31733 bytes

```python
"""
heartbeat.py - the two-sided clock.

WHAT PROBLEM THIS SOLVES
------------------------
Every timestamp in this system is a number the operator wrote. External
anchoring (OpenTimestamps) and peer witnessing both prove a record existed
BEFORE some later public event. They are ceilings.

Nothing proved a floor. Nothing stopped a record being created EARLIER than
it claims, or a whole chain being pre-computed in advance and released
slowly to look live. That is the fraud that actually happens: the grant
written after the incident, the decision dated last Tuesday.

A clock cannot fix this. Anyone can write down what a clock will say at
14:32:07 tomorrow, so hashing a clock face adds a hash, not a time.

WHAT DOES FIX IT
----------------
A public beacon: a source that ticks on a fixed cadence like a clock, but
whose value at each tick cannot be known by anyone until the tick happens.
drand (League of Entropy) publishes one every 30 seconds. Bitcoin publishes
one roughly every ten minutes.

Fold that value into a sealed block and the block cannot have been created
before the tick existed. Not because we say so - because it contains a
number that did not exist yet.

THE INTERLEAVE, WHICH IS THE WHOLE TRICK
----------------------------------------
We do NOT stamp every decision. We seal one beat into the chain every few
minutes. The chain is append-only and prev-hash linked, so any record
sitting between beat A and beat B was necessarily created after A and
before B.

One beat therefore gives a floor to every record that follows it, and the
next beat gives all of them a ceiling. Every decision gets a two-sided
window for free, with no change to seal(), no change to server.py, and no
extra latency on the decision path.

The window width is published on every answer. It is a live public
measurement of how much room the operator would have to lie in. It is the
only number in this system that gets better by us doing more work, and
worse by us doing less, which is why it is published.

WHAT THIS DOES NOT DO
---------------------
- It does not prove the record is true. It proves when it can have been made.
- It does not verify drand's BLS signature (not feasible in pure stdlib).
  It records the round and the randomness verbatim, and anyone can re-fetch
  that round from drand and confirm the value matches. Deterministic,
  public, and does not involve us.
- A record inside an open window (after the last beat, before the next) has
  a floor and no ceiling yet. That is reported as open, never as closed.
- Beats can only be sealed by whoever runs this server. What stops the
  operator sealing a stale tick is that the tick is timestamped and public:
  sealing round N long after round N happened widens the window and shows.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec        public   what this is, how to verify it yourself
  GET  latest      public   the most recent beat sealed
  GET  ticks       public   recent beats
  GET  window      public   ?block= or ?receipt= - the two-sided window
  GET  verify      public   ?round= - what we sealed, and where to check it
  GET  status      public   cadence, coverage, mean window
  POST beat        keyed    fetch a tick now and seal it
  POST source      keyed    add a beacon reading fetched elsewhere (air-gap)
"""

import json
import time
import sqlite3
import threading
import urllib.request
import urllib.error

VERSION = "1.3.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "latest"),
    ("GET", "ticks"),
    ("GET", "window"),
    ("GET", "verify"),
    ("GET", "status"),
}

# ---------------------------------------------------------------------
# Beacon sources. Fixed hosts only - this is an allowlist, not a fetcher.
# ---------------------------------------------------------------------
# Each source: name, url, cadence in seconds, and a parser returning
# (round, value, source_time_or_None).

BEACON_HOSTS = {
    "api.drand.sh",
    "drand.cloudflare.com",
    "mempool.space",
}

FETCH_TIMEOUT = 8
MAX_BODY = 65536

BEAT_SECONDS = 300          # one beat every five minutes
AUTO_BEAT = True
MIN_BEAT_GAP = 60           # refuse to beat more often than this

_timer_lock = threading.Lock()
_timer_started = False
_beat_runs = 0
_beat_last = None
_beat_last_error = None


def _parse_drand(raw):
    d = json.loads(raw)
    rnd = int(d["round"])
    val = str(d["randomness"])
    if not val or len(val) < 32:
        raise ValueError("drand randomness missing or too short")
    return rnd, val, None


def _parse_btc_tip(raw):
    val = raw.strip()
    if len(val) != 64 or any(c not in "0123456789abcdefABCDEF" for c in val):
        raise ValueError("bitcoin tip hash not a 64-char hex string")
    return None, val.lower(), None


SOURCES = [
    {
        "name": "drand-quicknet",
        "url": "https://api.drand.sh/v2/beacons/quicknet/rounds/latest",
        "cadence_seconds": 3,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/v2/beacons/quicknet/rounds/{round}",
        "note": "League of Entropy public randomness beacon, quicknet chain",
    },
    {
        "name": "drand-default",
        "url": "https://api.drand.sh/public/latest",
        "cadence_seconds": 30,
        "parse": _parse_drand,
        "verify_url": "https://api.drand.sh/public/{round}",
        "note": "League of Entropy public randomness beacon, default chain",
    },
    {
        "name": "bitcoin-tip",
        "url": "https://mempool.space/api/blocks/tip/hash",
        "cadence_seconds": 600,
        "parse": _parse_btc_tip,
        "verify_url": "https://mempool.space/block/{value}",
        "note": "Bitcoin chain tip - slower, but the hardest to influence",
    },
]

VOCABULARY = {
    "floor": (
        "The record was created after this beat, because the chain is "
        "append-only and the record sits after a block containing a value "
        "that did not exist before the beat."
    ),
    "ceiling": (
        "The record was created before this beat, because the record sits "
        "before it in an append-only chain."
    ),
    "window": (
        "The span between floor and ceiling. The record can have been "
        "created at any moment inside it and no moment outside it. Smaller "
        "is stronger. This is a measurement, not a claim."
    ),
    "open": (
        "There is a floor but no ceiling yet: the next beat has not been "
        "sealed. Reported as open rather than closed. It closes on the "
        "next beat, and nothing about the record changes when it does."
    ),
    "unfloored": (
        "The record predates the first beat ever sealed. It has no floor "
        "from this module. Its ceiling still holds."
    ),
}

WHAT_THIS_PROVES = (
    "A window, not a truth. Inside the window the record could have been "
    "created at any instant. Outside it, it could not have been created at "
    "all. It says nothing about whether the record's contents are correct."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS heartbeat_tick (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source       TEXT NOT NULL,
        beacon_round INTEGER,
        value        TEXT NOT NULL,
        fetched_at   REAL NOT NULL,
        cadence      INTEGER,
        chain_rowid  INTEGER,
        audit_hash   TEXT,
        note         TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_hb_rowid ON heartbeat_tick(chain_rowid)",
    "CREATE INDEX IF NOT EXISTS idx_hb_round ON heartbeat_tick(source, beacon_round)",
]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        # diagnostic columns, added without breaking an existing table
        cur.execute("PRAGMA table_info(heartbeat_tick)")
        have = [r[1] for r in cur.fetchall()]
        for col in ("seal_shape", "seal_error"):
            if col not in have:
                try:
                    cur.execute("ALTER TABLE heartbeat_tick ADD COLUMN %s TEXT" % col)
                except Exception:
                    pass
        conn.commit()


def _host_of(url):
    try:
        rest = url.split("://", 1)[1]
    except IndexError:
        return ""
    return rest.split("/", 1)[0].split(":", 1)[0].lower()


def _fetch(url):
    if not url.startswith("https://"):
        raise ValueError("https only")
    host = _host_of(url)
    if host not in BEACON_HOSTS:
        raise ValueError("host not on the beacon allowlist: %s" % host)
    req = urllib.request.Request(url, headers={"User-Agent": "aileash-heartbeat/1.0"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
        return r.read(MAX_BODY).decode("utf-8", "replace")


def _read_tick(fetcher=None):
    """Try each source in order. Returns dict or raises."""
    fetcher = fetcher or _fetch
    errors = []
    for src in SOURCES:
        try:
            raw = fetcher(src["url"])
            rnd, val, _ = src["parse"](raw)
            return {
                "source": src["name"],
                "beacon_round": rnd,
                "value": val,
                "cadence": src["cadence_seconds"],
                "note": src["note"],
            }
        except Exception as e:
            errors.append("%s: %s" % (src["name"], e))
    raise RuntimeError("no beacon reachable | " + " | ".join(errors))


def _seal(ctx, action, payload):
    """Seal through the host's seal().

    Confirmed from server.py: seal(event, result, ts, api_key=None) where
    EVENT IS A DICT carrying user_id (it is subscripted inside), and the
    return is (audit_hash, block_index, key_seq). So the block position
    comes back directly and does not have to be guessed from MAX(rowid).

    Returns (ok, shape, error, audit_hash, block_index).
    """
    fn = ctx.get("seal")
    if fn is None:
        return False, None, "ctx has no seal function", None, None

    ts = time.time()
    event = {
        "user_id": "heartbeat",
        "action": action,
        "amount": 0,
        "country": "UK",
        "device_id": "heartbeat",
        "anomaly": 0,
        "device_risk": 0,
    }
    result = dict(payload)
    result.setdefault("decision", "BEACON_SEALED")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)

    attempts = [
        ("seal(event_dict, result, ts)", lambda: fn(event, result, ts)),
        ("seal(event_dict, result, ts, None)", lambda: fn(event, result, ts, None)),
        ("seal(event_dict, result)", lambda: fn(event, result)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            out = call()
        except Exception as e:
            errors.append("%s -> %s: %s" % (shape, type(e).__name__, e))
            continue
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return True, shape, None, h, idx
    return False, None, " | ".join(errors), None, None


def _audit_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    return cur.fetchone() is not None


def _cols(conn, table):
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    return [r[1] for r in cur.fetchall()]


def _hash_col(conn):
    c = _cols(conn, "audit_log")
    for name in ("audit_hash", "hash", "block_hash"):
        if name in c:
            return name
    return None


def _latest_rowid(conn):
    cur = conn.cursor()
    cur.execute("SELECT MAX(rowid) FROM audit_log")
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0


def _backfill(conn, lock, tick_id):
    """After a seal, learn which chain row it landed on."""
    hcol = _hash_col(conn)
    with lock:
        cur = conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        row = cur.fetchone()
        rid = row[0] if row and row[0] is not None else None
        h = None
        if rid is not None and hcol:
            cur.execute("SELECT %s FROM audit_log WHERE rowid=?" % hcol, (rid,))
            r2 = cur.fetchone()
            h = r2[0] if r2 else None
        cur.execute(
            "UPDATE heartbeat_tick SET chain_rowid=?, audit_hash=? WHERE id=?",
            (rid, h, tick_id),
        )
        conn.commit()
    return rid, h


# ---------------------------------------------------------------------
# the beat
# ---------------------------------------------------------------------

def _do_beat(ctx, fetcher=None, forced=False):
    global _beat_runs, _beat_last, _beat_last_error
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    with lock:
        cur = conn.cursor()
        cur.execute("SELECT fetched_at FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
    if row and not forced and (time.time() - row[0]) < MIN_BEAT_GAP:
        return {"beat": False, "reason": "too_soon", "min_gap_seconds": MIN_BEAT_GAP}, 429

    tick = _read_tick(fetcher)
    now = time.time()

    event = "heartbeat_beat"
    result = {
        "kind": "beacon_tick",
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "fetched_at": now,
        "note": (
            "Unpredictable public value. Any block after this one in this "
            "append-only chain was created after this tick existed."
        ),
    }

    with lock:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO heartbeat_tick (source, beacon_round, value, fetched_at,"
            " cadence, note) VALUES (?,?,?,?,?,?)",
            (tick["source"], tick["beacon_round"], tick["value"], now,
             tick["cadence"], tick["note"]),
        )
        tick_id = cur.lastrowid
        conn.commit()

    ok, shape, err, h, rid = _seal(ctx, event, result)
    if ok and (rid is None or h is None):
        try:
            rid2, h2 = _backfill(conn, lock, tick_id)
            rid = rid if rid is not None else rid2
            h = h if h is not None else h2
        except Exception:
            pass
    with lock:
        conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                     " chain_rowid=?, audit_hash=? WHERE id=?",
                     (shape, err, rid, h, tick_id))
        conn.commit()

    _beat_runs += 1
    _beat_last = now
    _beat_last_error = err

    return {
        "beat": True,
        "sealed_into_chain": bool(ok and rid),
        "seal_shape": shape,
        "seal_error": err,
        "tick_id": tick_id,
        "source": tick["source"],
        "round": tick["beacon_round"],
        "value": tick["value"],
        "cadence_seconds": tick["cadence"],
        "sealed_at_chain_rowid": rid,
        "audit_hash": h,
        "verify_yourself": _verify_url(tick["source"], tick["beacon_round"], tick["value"]),
    }, 200


def _verify_url(source, rnd, value):
    for s in SOURCES:
        if s["name"] == source:
            u = s["verify_url"]
            if rnd is not None:
                return u.replace("{round}", str(rnd)).replace("{value}", str(value))
            return u.replace("{value}", str(value))
    return None


def _start_timer(ctx):
    global _timer_started
    with _timer_lock:
        if _timer_started or not AUTO_BEAT:
            return
        _timer_started = True

    for t in threading.enumerate():
        if t.name == "heartbeat" and t.is_alive():
            return

    def loop():
        global _beat_last_error
        while True:
            try:
                _do_beat(ctx)
            except Exception as e:
                _beat_last_error = str(e)
            time.sleep(BEAT_SECONDS)

    t = threading.Thread(target=loop, name="heartbeat", daemon=True)
    t.start()


# ---------------------------------------------------------------------
# the window
# ---------------------------------------------------------------------

def _find_rowid(conn, block, receipt):
    if block is not None:
        try:
            return int(block)
        except (TypeError, ValueError):
            return None
    if receipt:
        hcol = _hash_col(conn)
        if not hcol:
            return None
        cur = conn.cursor()
        cur.execute("SELECT rowid FROM audit_log WHERE %s=? LIMIT 1" % hcol, (receipt,))
        r = cur.fetchone()
        return r[0] if r else None
    return None


def _window_for(conn, rowid):
    cur = conn.cursor()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid<=?"
        " ORDER BY chain_rowid DESC LIMIT 1", (rowid,))
    floor = cur.fetchone()
    cur.execute(
        "SELECT id, source, beacon_round, value, fetched_at, chain_rowid, audit_hash"
        " FROM heartbeat_tick WHERE chain_rowid IS NOT NULL AND chain_rowid>?"
        " ORDER BY chain_rowid ASC LIMIT 1", (rowid,))
    ceil = cur.fetchone()
    return floor, ceil


def _beat_obj(row, err=None, shape=None):
    if not row:
        return None
    out = {
        "source": row[1],
        "round": row[2],
        "value": row[3],
        "at": _iso(row[4]),
        "at_epoch": row[4],
        "chain_rowid": row[5],
        "audit_hash": row[6],
        "verify_yourself": _verify_url(row[1], row[2], row[3]),
    }
    if row[5] is None:
        out["in_chain"] = False
        out["warning"] = ("This beat is NOT sealed into the chain, so it is "
                          "not a floor for anything. See seal_error.")
        if err:
            out["seal_error"] = err
    else:
        out["in_chain"] = True
        if shape:
            out["seal_shape"] = shape
    return out


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes %d seconds" % (s // 60, s % 60)
    return "%d hours %d minutes" % (s // 3600, (s % 3600) // 60)


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]

    if not _audit_table(conn):
        return {"error": "audit_log_missing"}, 500

    _ensure(conn, lock)
    _start_timer(ctx)

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "latest":
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return {"beats": 0, "message": "no beat sealed yet"}, 200
        age = time.time() - row[4]
        return {
            "latest_beat": _beat_obj(row),
            "seconds_since": round(age, 1),
            "open_window_so_far": _human(age),
            "meaning": (
                "Anything sealed since this beat has this beat as its floor "
                "and no ceiling until the next beat."
            ),
        }, 200

    if method == "GET" and action == "ticks":
        try:
            limit = min(int(data.get("limit", 25)), 200)
        except (TypeError, ValueError):
            limit = 25
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash, seal_error, seal_shape FROM heartbeat_tick"
            " ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        return {
            "count": len(rows),
            "beats": [_beat_obj(r, r[7], r[8]) for r in rows],
            "cadence_target_seconds": BEAT_SECONDS,
        }, 200

    if method == "GET" and action == "window":
        rowid = _find_rowid(conn, data.get("block"), data.get("receipt"))
        if rowid is None:
            return {"error": "block_or_receipt_required",
                    "usage": "/x/heartbeat/window?block=846 or ?receipt=<audit_hash>"}, 400

        floor, ceil = _window_for(conn, rowid)
        out = {
            "block": rowid,
            "floor": _beat_obj(floor),
            "ceiling": _beat_obj(ceil),
            "what_this_proves": WHAT_THIS_PROVES,
            "vocabulary": VOCABULARY,
        }

        if floor and ceil:
            width = ceil[4] - floor[4]
            out["state"] = "closed"
            out["window_seconds"] = round(width, 1)
            out["window"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s and before %s. Window: %s."
                % (rowid, _iso(floor[4]), _iso(ceil[4]), _human(width))
            )
        elif floor:
            width = time.time() - floor[4]
            out["state"] = "open"
            out["window_seconds_so_far"] = round(width, 1)
            out["window_so_far"] = _human(width)
            out["statement"] = (
                "Block %d was created after %s. The ceiling is not sealed "
                "yet, so the window is open." % (rowid, _iso(floor[4]))
            )
        elif ceil:
            out["state"] = "unfloored"
            out["statement"] = (
                "Block %d predates the first beat, so it has no floor from "
                "this module. It was created before %s." % (rowid, _iso(ceil[4]))
            )
        else:
            out["state"] = "no_beats"
            out["statement"] = "No beats have been sealed, so no window exists."

        out["external_ceiling"] = {
            "note": (
                "A second, independent ceiling comes from OpenTimestamps. "
                "Anchoring is per proof and has its own pending/confirmed "
                "state."
            ),
            "where": "/x/ots/status",
        }
        return out, 200

    if method == "GET" and action == "verify":
        rnd = data.get("round")
        if rnd is None:
            return {"error": "round_required"}, 400
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source, beacon_round, value, fetched_at, chain_rowid,"
            " audit_hash FROM heartbeat_tick WHERE beacon_round=?"
            " ORDER BY id DESC LIMIT 1", (rnd,))
        row = cur.fetchone()
        if not row:
            return {"error": "round_not_sealed", "round": rnd}, 404
        return {
            "sealed": _beat_obj(row),
            "how_to_verify": [
                "Fetch the round from the beacon operator at the url above.",
                "Compare its randomness with the value we sealed. They must match.",
                "Confirm the beat's audit_hash is in our chain at /api/verify-chain.",
                "Nothing in these three steps requires our cooperation.",
            ],
            "we_do_not_verify_the_signature": (
                "drand signs each round with BLS, which this server does not "
                "implement. We record the round and value verbatim. The "
                "operator's own endpoint is the authority, not us."
            ),
        }, 200

    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(fetched_at), MAX(fetched_at) FROM heartbeat_tick")
        n, first, last = cur.fetchone()
        cur.execute(
            "SELECT fetched_at FROM heartbeat_tick WHERE chain_rowid IS NOT NULL"
            " ORDER BY chain_rowid ASC")
        times = [r[0] for r in cur.fetchall()]
        gaps = [times[i + 1] - times[i] for i in range(len(times) - 1)]
        mean = sum(gaps) / len(gaps) if gaps else None
        widest = max(gaps) if gaps else None
        cur.execute("SELECT MAX(rowid) FROM audit_log")
        tip = cur.fetchone()[0] or 0
        cur.execute("SELECT MIN(chain_rowid) FROM heartbeat_tick WHERE chain_rowid IS NOT NULL")
        firstrow = cur.fetchone()[0]
        covered = (tip - firstrow) if firstrow else 0
        return {
            "version": VERSION,
            "beats_sealed": n,
            "first_beat": _iso(first),
            "latest_beat": _iso(last),
            "cadence_target_seconds": BEAT_SECONDS,
            "auto_beat": AUTO_BEAT,
            "timer_running": _timer_started,
            "beat_runs_this_process": _beat_runs,
            "last_error": _beat_last_error,
            "beats_not_in_chain": _orphans(conn),
            "last_seal_error": _last_seal_error(conn),
            "last_seal_shape": _last_seal_shape(conn),
            "mean_window_seconds": round(mean, 1) if mean else None,
            "mean_window": _human(mean),
            "widest_window_seconds": round(widest, 1) if widest else None,
            "widest_window": _human(widest),
            "records_with_a_floor": covered,
            "chain_height": tip,
            "honest_note": (
                "Mean window is the average distance between beats. It is the "
                "typical amount of room a record has. Widest is the worst "
                "case, which is the number that actually matters."
            ),
        }, 200

    if method == "POST" and action == "beat":
        try:
            return _do_beat(ctx, forced=bool(data.get("force")))
        except Exception as e:
            return {"beat": False, "error": "beacon_unreachable", "detail": str(e)}, 503

    if method == "POST" and action == "source":
        # For an engine with no outbound network. The operator hands it a
        # reading fetched elsewhere. Sealed exactly as supplied and marked.
        val = data.get("value")
        src = data.get("source") or "supplied"
        rnd = data.get("round")
        if not val or len(str(val)) < 32:
            return {"error": "value_required", "note": "at least 32 characters"}, 400
        now = time.time()
        with lock:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO heartbeat_tick (source, beacon_round, value,"
                " fetched_at, cadence, note) VALUES (?,?,?,?,?,?)",
                (src, rnd, str(val), now, None,
                 "supplied by operator, not fetched by this server"),
            )
            tick_id = cur.lastrowid
            conn.commit()
        ok, shape, err, h, rid = _seal(ctx, "heartbeat_beat", {
            "kind": "beacon_tick_supplied",
            "source": src, "round": rnd, "value": str(val), "fetched_at": now,
            "note": ("Supplied by the operator rather than fetched here. The "
                     "floor it gives is only as good as the reader's trust in "
                     "that source, and it is marked so nobody mistakes it."),
        })
        if ok and (rid is None or h is None):
            try:
                rid2, h2 = _backfill(conn, lock, tick_id)
                rid = rid if rid is not None else rid2
                h = h if h is not None else h2
            except Exception:
                pass
        with lock:
            conn.execute("UPDATE heartbeat_tick SET seal_shape=?, seal_error=?,"
                         " chain_rowid=?, audit_hash=? WHERE id=?",
                         (shape, err, rid, h, tick_id))
            conn.commit()
        return {"beat": True, "supplied": True, "tick_id": tick_id,
                "sealed_at_chain_rowid": rid, "audit_hash": h,
                "marked": "supplied by operator, not fetched by this server"}, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "latest", "ticks", "window", "verify",
                        "status", "beat", "source"]}, 404


def _orphans(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick WHERE chain_rowid IS NULL")
        return cur.fetchone()[0]
    except Exception:
        return None


def _last_seal_error(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_error FROM heartbeat_tick WHERE seal_error IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _last_seal_shape(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT seal_shape FROM heartbeat_tick WHERE seal_shape IS NOT NULL"
                    " ORDER BY id DESC LIMIT 1")
        r = cur.fetchone()
        return r[0] if r else None
    except Exception:
        return None


def _spec():
    return {
        "module": "heartbeat",
        "version": VERSION,
        "what_it_is": (
            "A clock nobody can wind. Public beacon values are sealed into "
            "the chain on a cadence. Because a beacon value cannot be known "
            "before its tick, and because the chain is append-only, every "
            "record between two beats has a provable earliest and latest "
            "moment of creation."
        ),
        "why_a_clock_alone_fails": (
            "Anyone can write down what a clock will read tomorrow. A clock "
            "reading proves nothing about when it was written down. A beacon "
            "value cannot be written down in advance by anyone."
        ),
        "the_interleave": (
            "Decisions are not stamped individually. One beat every few "
            "minutes gives a floor to everything after it and a ceiling to "
            "everything before the next one. No change to the decision path "
            "and no added latency."
        ),
        "sources": [
            {"name": s["name"], "cadence_seconds": s["cadence_seconds"],
             "note": s["note"], "url": s["url"]} for s in SOURCES
        ],
        "vocabulary": VOCABULARY,
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It bounds when a record can have been made. It says nothing "
            "about whether the record is correct.",
            "drand signatures are BLS and are not verified here. The round "
            "and value are recorded verbatim and are re-fetchable by anyone "
            "from the beacon operator.",
            "A record after the newest beat has an open window until the "
            "next beat is sealed.",
            "Beats sealed from a value the operator supplied by hand rather "
            "than fetched are marked as such and are weaker.",
            "A wide window is reported wide. The number is a measurement of "
            "our own cadence, and it can embarrass us.",
        ],
        "routes": {
            "GET /x/heartbeat/spec": "this document",
            "GET /x/heartbeat/latest": "most recent beat and the open window so far",
            "GET /x/heartbeat/ticks?limit=": "recent beats",
            "GET /x/heartbeat/window?block=|?receipt=": "two-sided window for a record",
            "GET /x/heartbeat/verify?round=": "what we sealed and where to check it",
            "GET /x/heartbeat/status": "cadence, coverage, mean and widest window",
            "POST /x/heartbeat/beat": "keyed - fetch and seal now",
            "POST /x/heartbeat/source": "keyed - seal a reading fetched elsewhere",
        },
    }

```


## `modules/investor.py`

284 lines, 23104 bytes

```python
"""
modules/investor.py  v1.2.0
Serves the investor / partner page at /investor-prospectus.

Page module, same family as map.py / console.py / network.py: a runtime do_GET
patch puts the page at a clean URL, armed by hitting /x/investor/status once
after each deploy. server.py is never edited. Page is base64-embedded.
"""

import base64
import sys

VERSION = "1.2.0"
PAGE_PATH = "/investor-prospectus"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+c2ViYmkucHJv"
    "IOKAlCB0aGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJLiBQYXJ0bmVyIG9wcG9ydHVuaXR5LjwvdGl0bGU+CjxtZXRhIG5hbWU9ImRl"
    "c2NyaXB0aW9uIiBjb250ZW50PSJBIGxpdmUsIHB1YmxpY2x5IHZlcmlmaWFibGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJIGRlY2lz"
    "aW9ucy4gQnVpbHQsIHJ1bm5pbmcsIGFuZCBzdHJ1Y3R1cmFsbHkgaW1wb3NzaWJsZSBmb3IgaW5jdW1iZW50cyB0byBjb3B5LiBT"
    "ZWVraW5nIG9uZSBvcGVyYXRpbmcgcGFydG5lciB0byB0YWtlIGl0IGludG8gcmVndWxhdGVkIGVudGVycHJpc2UuIj4KPGxpbmsg"
    "cmVsPSJwcmVjb25uZWN0IiBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9m"
    "b250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1OZXdzcmVhZGVyOm9wc3osd2dodEA2Li43Miw0MDA7Ni4uNzIsNTAwOzYu"
    "LjcyLDYwMDs2Li43Miw3MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMDs3MDAmZmFtaWx5PUlCTStQbGV4"
    "K01vbm86d2dodEA0MDA7NTAwOzYwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7CiAgLS1w"
    "YXBlcjojRkFGQUY2Oy0taW5rOiMxNDE3MUM7LS1pbmstc29mdDojNDU0QjU0Oy0tY2hhaW46IzJFNUU0RTsKICAtLWNoYWluLWxp"
    "Z2h0OiNFNEVDRTg7LS1nb2xkOiM5QTdCMUY7LS1nb2xkLWxpZ2h0OiNGM0VDRDg7LS1saW5lOiNERURCRDE7Cn0KKntib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBTYW5zJyxzYW5zLXNl"
    "cmlmO2JhY2tncm91bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1z"
    "bW9vdGhpbmc6YW50aWFsaWFzZWR9CmgxLGgyLGgzLC5kaXNwbGF5e2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJpZjtmb250"
    "LXdlaWdodDo1MDA7bGV0dGVyLXNwYWNpbmc6LTAuMDFlbX0KLm1vbm97Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9z"
    "cGFjZX0KYXtjb2xvcjp2YXIoLS1jaGFpbil9Ci53cmFwe21heC13aWR0aDo3NjBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6MCAy"
    "OHB4fQoKaGVhZGVye3BhZGRpbmc6NTZweCAwIDQwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9Ci5kb2Mt"
    "bGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzow"
    "LjFlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MjBweDtkaXNw"
    "bGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47ZmxleC13cmFwOndyYXA7Z2FwOjhweH0KaDF7Zm9udC1zaXpl"
    "OmNsYW1wKDM0cHgsNXZ3LDUwcHgpO2xpbmUtaGVpZ2h0OjEuMDg7bWF4LXdpZHRoOjE3Y2g7bWFyZ2luLWJvdHRvbToxOHB4fQou"
    "dGFnbGluZXtmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmstc29mdCk7bWF4LXdpZHRoOjU0Y2h9Ci50YWdsaW5lIGJ7Y29s"
    "b3I6dmFyKC0taW5rKX0KCi5ibG9ja3twb3NpdGlvbjpyZWxhdGl2ZTtwYWRkaW5nOjhweCAwIDQ0cHggMjRweDtib3JkZXItbGVm"
    "dDoxcHggc29saWQgdmFyKC0tbGluZSk7bWFyZ2luLWxlZnQ6NHB4fQouYmxvY2s6bGFzdC1vZi10eXBle2JvcmRlci1sZWZ0OjFw"
    "eCBzb2xpZCB0cmFuc3BhcmVudH0KLmJsb2NrLW51bXtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQt"
    "c2l6ZToxMXB4O2NvbG9yOnZhcigtLWNoYWluKTtsZXR0ZXItc3BhY2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNl"
    "O21hcmdpbi1ib3R0b206MTBweH0KLmJsb2NrIGgye2ZvbnQtc2l6ZToyN3B4O21hcmdpbi1ib3R0b206MTZweDtsaW5lLWhlaWdo"
    "dDoxLjE1fQouYmxvY2sgaDN7Zm9udC1zaXplOjE3cHg7bWFyZ2luOjIycHggMCA4cHh9Ci5ibG9jayBwe2ZvbnQtc2l6ZToxNS41"
    "cHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTRweDttYXgtd2lkdGg6NjBjaH0KLmJsb2NrIHA6bGFzdC1j"
    "aGlsZHttYXJnaW4tYm90dG9tOjB9Ci5ibG9jayB1bHttYXJnaW46MCAwIDE0cHggMThweH0KLmJsb2NrIGxpe2ZvbnQtc2l6ZTox"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tYm90dG9tOjhweDttYXgtd2lkdGg6NThjaH0KLmJsb2NrIGxpIGIsLmJs"
    "b2NrIHAgYntjb2xvcjp2YXIoLS1pbmspfQoKLnByb29mLWdyaWR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczox"
    "ZnIgMWZyO2dhcDoxNHB4O21hcmdpbi10b3A6MThweH0KQG1lZGlhKG1heC13aWR0aDo1NjBweCl7LnByb29mLWdyaWR7Z3JpZC10"
    "ZW1wbGF0ZS1jb2x1bW5zOjFmcn19Ci5wcm9vZntiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7"
    "cGFkZGluZzoxOHB4IDIwcHg7Ym9yZGVyLXJhZGl1czo0cHh9Ci5wcm9vZi1ue2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJp"
    "Zjtmb250LXNpemU6MjZweDtmb250LXdlaWdodDo2MDA7Y29sb3I6dmFyKC0tY2hhaW4pfQoucHJvb2YtbHtmb250LXNpemU6MTIu"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjNweH0KLnByb29mLXNyY3tmb250LWZhbWlseTonSUJNIFBsZXgg"
    "TW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMHB4O2NvbG9yOiM5OTk7bWFyZ2luLXRvcDo2cHh9CgouY291bnRkb3due2JhY2tn"
    "cm91bmQ6dmFyKC0tZ29sZC1saWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDE1NCwxMjMsMzEsMC4yNSk7Ym9yZGVyLXJhZGl1"
    "czo0cHg7cGFkZGluZzoyMHB4IDI0cHg7bWFyZ2luOjIwcHggMH0KLmNvdW50ZG93bi1sYWJlbHtmb250LWZhbWlseTonSUJNIFBs"
    "ZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWdvbGQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2Fz"
    "ZTtsZXR0ZXItc3BhY2luZzowLjA4ZW07bWFyZ2luLWJvdHRvbTo4cHh9Ci5jb3VudGRvd24tZGF5c3tmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjM4cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLWdvbGQpO2xpbmUtaGVpZ2h0"
    "OjF9Ci5jb3VudGRvd24tc3Vie2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjZweDtsaW5l"
    "LWhlaWdodDoxLjZ9CgoucHVsbHtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tY2hhaW4pO3BhZGRpbmc6NnB4IDAgNnB4IDIw"
    "cHg7bWFyZ2luOjIwcHggMDtmb250LWZhbWlseTonTmV3c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjIycHg7bGluZS1oZWlnaHQ6"
    "MS4zNTtjb2xvcjp2YXIoLS1pbmspfQoKLmFzay1ib3h7YmFja2dyb3VuZDp2YXIoLS1pbmspO2NvbG9yOnZhcigtLXBhcGVyKTti"
    "b3JkZXItcmFkaXVzOjRweDtwYWRkaW5nOjMycHg7bWFyZ2luLXRvcDoyMHB4fQouYXNrLWFtb3VudHtmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjQ0cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOndoaXRlO2xpbmUtaGVpZ2h0OjEuMDV9"
    "Ci5hc2stbGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3Bh"
    "Y2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM4RkE4OUM7bWFyZ2luLWJvdHRvbTo2cHh9Ci5hc2st"
    "Ym94IHB7Zm9udC1zaXplOjE0LjVweDtjb2xvcjojQzdEMkNDO21hcmdpbi10b3A6MTRweDttYXgtd2lkdGg6NTZjaH0KLmFzay1i"
    "b3ggcCBie2NvbG9yOiNmZmZ9CgoudXNlLW9mLWZ1bmRze21hcmdpbi10b3A6MjJweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rp"
    "b246Y29sdW1uO2dhcDoxMHB4fQoudWYtcm93e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGln"
    "bi1pdGVtczpiYXNlbGluZTtwYWRkaW5nLWJvdHRvbToxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwy"
    "NTUsMC4xMik7Zm9udC1zaXplOjE0cHg7Z2FwOjE2cHh9Ci51Zi1yb3c6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci51"
    "Zi1yb3cgc3BhbjpmaXJzdC1jaGlsZHtjb2xvcjojQzdEMkNDfQoudWYtcGN0e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxt"
    "b25vc3BhY2U7Y29sb3I6IzhGQTg5QztmbGV4OjAgMCBhdXRvfQoKLnZlcmlmeS1ib3h7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1s"
    "aWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMjUpO2JvcmRlci1yYWRpdXM6NHB4O3BhZGRpbmc6MjBweCAy"
    "NHB4O21hcmdpbi10b3A6MThweH0KLnZlcmlmeS1ib3ggaDR7Zm9udC1zaXplOjE1cHg7bWFyZ2luLWJvdHRvbToxMHB4fQoudmVy"
    "aWZ5LWJveCBwe2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1ib3R0b206OHB4fQoudmVyaWZ5LWJveCBjb2Rle2ZvbnQtZmFtaWx5OidJ"
    "Qk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjEyLjVweDtiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQg"
    "dmFyKC0tbGluZSk7cGFkZGluZzoycHggN3B4O2JvcmRlci1yYWRpdXM6M3B4O2NvbG9yOnZhcigtLWNoYWluKX0KCi5jb250YWN0"
    "LWJsb2Nre3BhZGRpbmc6NDRweCAwIDY0cHh9Ci5jb250YWN0LWNhcmR7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1saWdodCk7Ym9y"
    "ZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMik7Ym9yZGVyLXJhZGl1czo0cHg7cGFkZGluZzoyOHB4fQouY29udGFjdC1j"
    "YXJkIGgze2ZvbnQtc2l6ZToyMHB4O21hcmdpbi1ib3R0b206MTBweH0KLmNvbnRhY3QtY2FyZCBwe2ZvbnQtc2l6ZToxNC41cHg7"
    "Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTZweH0KLmNvbnRhY3QtbGlua3N7ZGlzcGxheTpmbGV4O2ZsZXgt"
    "ZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjE0"
    "cHh9Ci5jb250YWN0LWxpbmtzIGF7Y29sb3I6dmFyKC0tY2hhaW4pO3RleHQtZGVjb3JhdGlvbjpub25lO2ZvbnQtd2VpZ2h0OjUw"
    "MH0KCmZvb3RlcntwYWRkaW5nOjAgMCA0OHB4fQpmb290ZXIgcHtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNl"
    "O2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiM5OTk7bGluZS1oZWlnaHQ6MS44fQoKQG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246"
    "cmVkdWNlKXsqe3RyYW5zaXRpb246bm9uZSFpbXBvcnRhbnQ7YW5pbWF0aW9uOm5vbmUhaW1wb3J0YW50fX0KPC9zdHlsZT4KPC9o"
    "ZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9IndyYXAiPgoKPGhlYWRlcj4KICA8ZGl2IGNsYXNzPSJkb2MtbGFiZWwiPgogICAgPHNw"
    "YW4+UGFydG5lciBPcHBvcnR1bml0eSAmbWlkZG90OyBzZWJiaS5wcm88L3NwYW4+CiAgICA8c3BhbiBpZD0iZG9jLWRhdGUiPiZt"
    "ZGFzaDs8L3NwYW4+CiAgPC9kaXY+CiAgPGgxPlRoZSBldmlkZW5jZSBsYXllciBmb3IgQUkgaXMgYnVpbHQsIGxpdmUsIGFuZCBs"
    "b29raW5nIGZvciBvbmUgcGFydG5lci48L2gxPgogIDxwIGNsYXNzPSJ0YWdsaW5lIj5zZWJiaS5wcm8gaXMgYSBwdWJsaWNseSB2"
    "ZXJpZmlhYmxlIGV2aWRlbmNlIGxheWVyIGZvciBBSSBkZWNpc2lvbnMgJm1kYXNoOyBydW5uaW5nIGluIHByb2R1Y3Rpb24gdG9k"
    "YXksIGNoZWNrYWJsZSBieSBhbnlvbmUgd2l0aCB0aGUgY29tcGFueSBzd2l0Y2hlZCBvZmYuIDxiPlRoZSBoYXJkIHBhcnQgaXMg"
    "ZG9uZS4gV2hhdCdzIGxlZnQgaXMgZGlzdHJpYnV0aW9uLjwvYj48L3A+CjwvaGVhZGVyPgoKPGRpdiBjbGFzcz0iYmxvY2siPgog"
    "IDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDEgJm1kYXNoOyBUaGUgb3Bwb3J0dW5pdHk8L2Rpdj4KICA8aDI+RXZlcnkgQUkgZGVj"
    "aXNpb24gaXMgYWJvdXQgdG8gbmVlZCBldmlkZW5jZS4gQWxtb3N0IG5vdGhpbmcgcHJvZHVjZXMgaXQuPC9oMj4KICA8cD5UaHJl"
    "ZSByZWd1bGF0b3J5IHJlZ2ltZXMgYXJlIGNvbnZlcmdpbmcgb24gdGhlIHNhbWUgZGVtYW5kOiByZWNvcmRzIHRoYXQgc3Vydml2"
    "ZSBzY3J1dGlueS4gVGhlIEVVIEFJIEFjdCwgdGhlIFVLIE9ubGluZSBTYWZldHkgQWN0LCBhbmQgdGhlIDIwMjQgUGF5bWVudCBT"
    "ZXJ2aWNlcyByZWltYnVyc2VtZW50IHJ1bGVzIGFsbCByZXF1aXJlIGFuIG9yZ2FuaXNhdGlvbiB0byBwcm92ZSB3aGF0IGl0cyBz"
    "eXN0ZW1zIGRpZCAmbWRhc2g7IG5vdCBhc3NlcnQgaXQsIHByb3ZlIGl0LjwvcD4KICA8cD5BbG1vc3QgZXZlcnkgb3JnYW5pc2F0"
    "aW9uIG1lZXRzIHRoYXQgZGVtYW5kIHdpdGggZGF0YWJhc2UgbG9ncyB0aGVpciBvd24gdGVhbSBjYW4gZWRpdC4gVGhhdCBpcyBu"
    "b3QgZXZpZGVuY2UsIGFuZCB0aGUgZGF5IGEgcmVndWxhdG9yLCBjb3VydCBvciBjdXN0b21lciBzdG9wcyB0YWtpbmcgdGhlaXIg"
    "d29yZCBmb3IgaXQsIHRoZXkgZGlzY292ZXIgdGhlIGdhcC4gPGI+VGhlIG1hcmtldCB0aGF0IGNsb3NlcyB0aGF0IGdhcCBkb2Vz"
    "IG5vdCByZWFsbHkgZXhpc3QgeWV0LjwvYj4gc2ViYmkucHJvIGlzIGFscmVhZHkgaW4gaXQuPC9wPgoKICA8ZGl2IGNsYXNzPSJw"
    "dWxsIj5BIGxvZyB5b3UgY2FuIGVkaXQgdGVsbHMgcGVvcGxlIHdoYXQgeW91IGN1cnJlbnRseSBjbGFpbSBoYXBwZW5lZC4gSXQg"
    "Y2Fubm90IHRlbGwgdGhlbSBub2JvZHkgY2hhbmdlZCBpdCBzaW5jZS4gT25seSBvbmUgb2YgdGhvc2UgaXMgd29ydGggYW55dGhp"
    "bmcgd2hlbiBpdCBtYXR0ZXJzLjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJjb3VudGRvd24iPgogICAgPGRpdiBjbGFzcz0iY291bnRk"
    "b3duLWxhYmVsIj5VbnRpbCBoaWdoLXJpc2sgQUkgb2JsaWdhdGlvbnMgYXBwbHk8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNvdW50"
    "ZG93bi1kYXlzIG1vbm8iIGlkPSJjb3VudGRvd24tZGF5cyI+Jm1kYXNoOyBkYXlzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjb3Vu"
    "dGRvd24tc3ViIj5Db3VudGluZyB0byAyIERlY2VtYmVyIDIwMjcuIFRoZSBldmlkZW5jZSB0aGVzZSBvYmxpZ2F0aW9ucyByZXF1"
    "aXJlIGlzIGhpc3RvcmljYWwgJm1kYXNoOyBpdCBjYW5ub3QgYmUgY3JlYXRlZCBhZnRlciB0aGUgZmFjdC4gRXZlcnkgb3JnYW5p"
    "c2F0aW9uIG5vdCByZWNvcmRpbmcgbm93IGlzIGFjY3J1aW5nIGEgZ2FwIGl0IGNhbiBuZXZlciBmaWxsLiBUaGF0IGlzIHRoZSBi"
    "dXlpbmcgcHJlc3N1cmUsIGFuZCBpdCBvbmx5IGdyb3dzLjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2Nr"
    "Ij4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPjAyICZtZGFzaDsgV2hhdCBpcyBhbHJlYWR5IGJ1aWx0PC9kaXY+CiAgPGgyPkxp"
    "dmUgaW4gcHJvZHVjdGlvbi4gTm90IGEgZGVjaywgbm90IGEgZGVtby48L2gyPgogIDxwPlRoaXMgcnVucyB0b2RheSwgb24gcmVh"
    "bCBpbmZyYXN0cnVjdHVyZSwgYW5kIGV2ZXJ5IGNsYWltIGJlbG93IGNhbiBiZSB2ZXJpZmllZCBieSBhIHRoaXJkIHBhcnR5IHdp"
    "dGggbm8gYWNjb3VudCBhbmQgbm8gcGVybWlzc2lvbi4gU2l4IHByb2R1Y3RzIG9uIG9uZSBlbmdpbmUsIG9uZSB0YW1wZXItZXZp"
    "ZGVudCBjaGFpbiB1bmRlcm5lYXRoIGFsbCBvZiB0aGVtLjwvcD4KCiAgPGRpdiBjbGFzcz0icHJvb2YtZ3JpZCI+CiAgICA8ZGl2"
    "IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0icHJvb2YtbiBtb25vIj42PC9kaXY+PGRpdiBjbGFzcz0icHJvb2YtbCI+UHJvZHVj"
    "dHMsIG9uZSBlbmdpbmU8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPkFJTGVhc2gsIEd1YXJkaWFuLCBTZW50aW5lbCwgU29u"
    "aWNCb29tLCBTZWJkb2csIFRva2VuIFNhdmVyPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0i"
    "cHJvb2YtbiBtb25vIj5+MjhtczwvZGl2PjxkaXYgY2xhc3M9InByb29mLWwiPk1lZGlhbiBkZWNpc2lvbiB0aW1lPC9kaXY+PGRp"
    "diBjbGFzcz0icHJvb2Ytc3JjIj5EZXRlcm1pbmlzdGljLCBvbiBsaXZlIHRyYWZmaWM8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xh"
    "c3M9InByb29mIj48ZGl2IGNsYXNzPSJwcm9vZi1uIG1vbm8iPlNIQS0yNTY8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1sIj5IYXNo"
    "LWNoYWluZWQsIGV4dGVybmFsbHkgYW5jaG9yZWQ8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPkNyb3NzLXdpdG5lc3NlZCBi"
    "eSBpbmRlcGVuZGVudCBzeXN0ZW1zPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0icHJvb2Yt"
    "biBtb25vIj5QdWJsaWM8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1sIj5WZXJpZmlhYmxlIHdpdGggdGhlIHZlbmRvciBzd2l0Y2hl"
    "ZCBvZmY8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPlN0YW5kYWxvbmUgdmVyaWZpZXIsIG5vIGFjY291bnQ8L2Rpdj48L2Rp"
    "dj4KICA8L2Rpdj4KCiAgPHAgc3R5bGU9Im1hcmdpbi10b3A6MThweCI+VGhlIHdob2xlIHJhbmdlIHNoYXJlcyBvbmUgc3BpbmU6"
    "IGV2ZXJ5IGRlY2lzaW9uIHNlYWxlZCBhcyBpdCBoYXBwZW5zLCBhbmNob3JlZCB0byBhIGNsb2NrIG5vYm9keSBjb250cm9scywg"
    "YW5kIHdpdG5lc3NlZCBob3VybHkgYnkgYW4gaW5kZXBlbmRlbnQgcGxhdGZvcm0gJm1kYXNoOyB1bmF0dGVuZGVkLCBydW5uaW5n"
    "IG5vdy4gQSByZWd1bGF0b3IsIGFuIGF1ZGl0b3Igb3IgYSBjdXN0b21lciBjaGVja3MgYW55IG9mIGl0IHRoZW1zZWx2ZXMuIFRo"
    "YXQgaXMgdGhlIHByb2R1Y3QsIGFuZCBpdCBleGlzdHMuPC9wPgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNs"
    "YXNzPSJibG9jay1udW0iPjAzICZtZGFzaDsgV2h5IGluY3VtYmVudHMgY2FuJ3QgZm9sbG93PC9kaXY+CiAgPGgyPlRoZSBtb2F0"
    "IGlzIHN0cnVjdHVyYWwsIG5vdCBhIGhlYWQgc3RhcnQuPC9oMj4KICA8cD5FdmVyeSBsb2dnaW5nLCBtb25pdG9yaW5nIGFuZCBh"
    "dWRpdCBwbGF0Zm9ybSBvbiB0aGUgbWFya2V0IGtlZXBzIGEgcmVjb3JkIGl0cyBvd24gY3VzdG9tZXIgY29udHJvbHMuIFRoYXQg"
    "aXMgbm90IGEgZmxhdyB0aGV5IGNhbiBwYXRjaCAmbWRhc2g7IGl0IGlzIHRoZSBmb3VuZGF0aW9uIHRoZWlyIGJ1c2luZXNzIHN0"
    "YW5kcyBvbi4gVG8gbWF0Y2ggc2ViYmkucHJvIHRoZXkgd291bGQgaGF2ZSB0byBnaXZlIHRoZSBjdXN0b21lciBhIHJlY29yZCB0"
    "aGUgY3VzdG9tZXIgY2Fubm90IGVkaXQsIHdoaWNoIGJyZWFrcyB0aGUgdGhpbmcgdGhleSBzZWxsLjwvcD4KICA8dWw+CiAgICA8"
    "bGk+PGI+VGhleSBjYW4ndCBjb3B5IHRoZSBxdWVzdGlvbi48L2I+ICJDYW4gdGhlIHBlb3BsZSBiZWluZyBhdWRpdGVkIGVkaXQg"
    "dGhlIGF1ZGl0PyIgaW5kaWN0cyB0aGVpciBlbnRpcmUgY2F0ZWdvcnkuIFRoZXkgYW5zd2VyIG5vIGJ5IGFkbWl0dGluZyB0aGVp"
    "ciBldmlkZW5jZSB3YXMgbmV2ZXIgZXZpZGVuY2UuPC9saT4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIHRpbWUuPC9i"
    "PiBBbiB1bmJyb2tlbiwgZXh0ZXJuYWxseSB3aXRuZXNzZWQgcmVjb3JkIGlzIHRoZSBvbmUgaW5wdXQgbm9ib2R5IGNhbiBzaG9y"
    "dGN1dC4gVGhlIG9ubHkgd2F5IHRvIGhhdmUgbGFzdCB5ZWFyIGNvdmVyZWQgd2FzIHRvIGJlIHJlY29yZGluZyBsYXN0IHllYXIu"
    "PC9saT4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIGhvbmVzdHkuPC9iPiBFdmVyeSBjb21wZXRpdG9yIG92ZXJjbGFp"
    "bXMuIHNlYmJpLnBybyBwdWJsaXNoZXMgaXRzIG93biBsaW1pdHMgb24gZXZlcnkgcGFnZSBhbmQgc2VhbHMgdGhlbSBpbnRvIGl0"
    "cyBvd24gY2hhaW4gJm1kYXNoOyB3aGljaCBpcyBleGFjdGx5IHRoZSBwcm9wZXJ0eSBhIGJ1eWVyIG9mIGV2aWRlbmNlIGluZnJh"
    "c3RydWN0dXJlIGlzIHBheWluZyBmb3IuPC9saT4KICA8L3VsPgoKICA8ZGl2IGNsYXNzPSJ2ZXJpZnktYm94Ij4KICAgIDxoND5W"
    "ZXJpZnkgaXQgYmVmb3JlIHlvdSByZWFkIGFub3RoZXIgbGluZTwvaDQ+CiAgICA8cD5Ob3RoaW5nIGhlcmUgYXNrcyB0byBiZSBi"
    "ZWxpZXZlZC4gPGNvZGU+L3gvd2l0bmVzcy90aXA8L2NvZGU+IHJldHVybnMgdGhlIGxpdmUgY2hhaW4gdGlwLiA8Y29kZT4veC9v"
    "dHMvc3RhdHVzPC9jb2RlPiBzaG93cyBpdHMgZXh0ZXJuYWwgYW5jaG9yaW5nLCBwZXIgcHJvb2YuIDxjb2RlPi94L3Jvc3Rlci9s"
    "aXN0PC9jb2RlPiBzaG93cyB0aGUgaW5kZXBlbmRlbnQgcGxhdGZvcm1zIHdpdG5lc3NpbmcgaXQuPC9wPgogICAgPHAgc3R5bGU9"
    "Im1hcmdpbi1ib3R0b206MCI+QWxsIHB1YmxpYywgYWxsIG5lZWQgbm8gYWNjb3VudCwgYWxsIGFuc3dlciB0byBhbnlvbmUuIFRo"
    "ZSBvZmZsaW5lIHZlcmlmaWVyIHJlYWNoZXMgYSB2ZXJkaWN0IHdpdGggdGhlIHdpZmkgb2ZmLjwvcD4KICA8L2Rpdj4KPC9kaXY+"
    "Cgo8ZGl2IGNsYXNzPSJibG9jayI+CiAgPGRpdiBjbGFzcz0iYmxvY2stbnVtIj4wNCAmbWRhc2g7IFRoZSBlY29ub21pY3M8L2Rp"
    "dj4KICA8aDI+WmVybyBtYXJnaW5hbCBjb3N0LiBEaXN0cmlidXRpb24gc2NhbGVzIHdpdGhvdXQgaGVhZGNvdW50LjwvaDI+CiAg"
    "PHA+VGhlIHNhbWUgZW5naW5lIHNlcnZlcyBvbmUgY3VzdG9tZXIgb3IgdGVuIHRob3VzYW5kICZtZGFzaDsgbWFyZ2luYWwgY29z"
    "dCBwZXIgYWRkaXRpb25hbCBkZXZpY2UgaXMgZWZmZWN0aXZlbHkgemVyby4gVGhhdCBtYWtlcyBkaXN0cmlidXRpb24sIG5vdCBl"
    "bmdpbmVlcmluZywgdGhlIGVudGlyZSBncm93dGggbGV2ZXIsIGFuZCBpdCBtYWtlcyBhIHJlc2VsbGVyIGNoYW5uZWwgcHVyZSBt"
    "YXJnaW4gcmF0aGVyIHRoYW4gYSBjb3N0IGxpbmUuPC9wPgogIDxwPjxiPjUwcCBwZXIgYWN0aXZlIGRldmljZSBwZXIgbW9udGg8"
    "L2I+LCBtZXRlcmVkIG9uIHJlYWwgdXNhZ2UuIFBhcnRuZXJzIGVtYmVkZGluZyB0aGUgcGxhdGZvcm0gc2V0IHRoZWlyIG93biBj"
    "dXN0b21lciBwcmljZSBhbmQga2VlcCBldmVyeXRoaW5nIGFib3ZlIHRoZSBwbGF0Zm9ybSBmZWUuIFRoZSB3aXRuZXNzIG5ldHdv"
    "cmsgc3RheXMgZnJlZSBhbmQgb3BlbiBieSBkZXNpZ24gJm1kYXNoOyBpdCBpcyB0aGUgbWVjaGFuaXNtIHRoYXQgbWFrZXMgdGhl"
    "IGV2aWRlbmNlIGNyZWRpYmxlLCBhbmQgY2hhcmdpbmcgZm9yIGl0IHdvdWxkIHdlYWtlbiB0aGUgdGhpbmcgYmVpbmcgc29sZC48"
    "L3A+CiAgPHA+VGhlIHJvdXRlIHRvIG1hcmtldCBpcyB0aGUgcGxhdGZvcm1zLCBub3Qgb25lIGN1c3RvbWVyIGF0IGEgdGltZS4g"
    "T3RoZXIgY29tcGxpYW5jZSBwbGF0Zm9ybXMgYWxyZWFkeSBob2xkIHJlbGF0aW9uc2hpcHMgd2l0aCB0aGUgZXhhY3QgYnV5ZXJz"
    "IHdobyBuZWVkIHRoaXMgYW5kIGFyZSB1bmlmb3JtbHkgd2VhayBvbiBldmlkZW5jZS4gVGhlIGVuZ2luZSBzaXRzIHVuZGVybmVh"
    "dGggdGhlaXIgcHJvZHVjdCBhcyB0aGUgZXZpZGVuY2UgbGF5ZXIgdGhleSBjYW4ndCBidWlsZCB0aGVtc2VsdmVzLiBGaXZlIGZv"
    "dW5kaW5nIHNlYXRzOyBmb3VyIGFscmVhZHkgdGFrZW4uPC9wPgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNs"
    "YXNzPSJibG9jay1udW0iPjA1ICZtZGFzaDsgVGhlIGFzazwvZGl2PgogIDxoMj5PbmUgb3BlcmF0aW5nIHBhcnRuZXIuIDMwJSBv"
    "ZiB0aGUgYnVzaW5lc3MuPC9oMj4KICA8ZGl2IGNsYXNzPSJhc2stYm94Ij4KICAgIDxkaXYgY2xhc3M9ImFzay1sYWJlbCI+T2Zm"
    "ZXJlZDwvZGl2PgogICAgPGRpdiBjbGFzcz0iYXNrLWFtb3VudCI+MzAlIGZvciB0aGUgcmlnaHQ8YnI+b3BlcmF0aW5nIHBhcnRu"
    "ZXI8L2Rpdj4KICAgIDxwPkJ1aWx0IGFuZCBydW4gYXQgbmVhci16ZXJvIGZpeGVkIGNvc3QsIGxpdmUgYW5kIHByb3Zlbi4gRXZl"
    "cnl0aGluZyB0aGUgaGFyZCBtb25leSB1c3VhbGx5IGZ1bmRzIGlzIGFscmVhZHkgZG9uZS4gVGhlIHBhcnRuZXIgd2hvIGNhbiBv"
    "cGVuIHJlZ3VsYXRlZCBlbnRlcnByaXNlIGFuZCBnb3Zlcm5tZW50ICZtZGFzaDsgPGI+ZGVmZW5jZSwgaGVhbHRoY2FyZSwgdGVs"
    "ZWNvbW11bmljYXRpb25zPC9iPiAmbWRhc2g7IHRha2VzIGEgc3Vic3RhbnRpYWwgc3Rha2UgaW4gYSBwbGF0Zm9ybSB0aGF0IGlz"
    "IHJlYWR5IHRvIHNjYWxlIHRoZSBkYXkgdGhleSB3YWxrIGluLjwvcD4KICAgIDxkaXYgY2xhc3M9InVzZS1vZi1mdW5kcyI+CiAg"
    "ICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+UmVndWxhdGVkIGVudGVycHJpc2UgJmFtcDsgZ292ZXJubWVudCBjaGFubmVs"
    "IGFjY2Vzczwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5jb3JlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1y"
    "b3ciPjxzcGFuPlJlc2VsbGVyIC8gTVNQIGRpc3RyaWJ1dGlvbiBhdCBzY2FsZTwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5j"
    "b3JlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPkV4dGVybmFsIHNlY3VyaXR5IGF1ZGl0ICZh"
    "bXA7IGxlZ2FsIHJldmlldyBvZiBjbGFpbXM8L3NwYW4+PHNwYW4gY2xhc3M9InVmLXBjdCI+ZnVuZDwvc3Bhbj48L2Rpdj4KICAg"
    "ICAgPGRpdiBjbGFzcz0idWYtcm93Ij48c3Bhbj5JbmZyYXN0cnVjdHVyZSBoYXJkZW5pbmcgZm9yIGVudGVycHJpc2UgbG9hZDwv"
    "c3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5mdW5kPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPHAgc3R5bGU9"
    "Im1hcmdpbi10b3A6MTZweCI+VGhlc2UgYXJlIHNlY3RvcnMgd2hlcmUgZXZpZGVuY2Ugb2JsaWdhdGlvbnMgYXJlIGhhcmRlc3Qs"
    "IHByb2N1cmVtZW50IHJ1bnMgZWlnaHRlZW4gbW9udGhzLCBhbmQgYSBmb3VuZGVyIGFsb25lIGRvZXMgbm90IGdldCBpbiB0aGUg"
    "cm9vbS4gVGhlIGVjb25vbWljcyBzdWl0IGV4YWN0bHkgdGhhdDogaGlnaC12YWx1ZSwgbG9uZy1jeWNsZSwgYW5kIHNlcnZlZCBi"
    "eSBhbiBlbmdpbmUgdGhhdCBjb3N0cyBub3RoaW5nIG1vcmUgdG8gcnVuIGF0IGEgdGhvdXNhbmQgY3VzdG9tZXJzIHRoYW4gYXQg"
    "b25lLjwvcD4KPC9kaXY+Cgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImNvbnRhY3QtYmxvY2sgd3JhcCI+CiAgPGRpdiBjbGFzcz0iY29u"
    "dGFjdC1jYXJkIj4KICAgIDxoMz5UYWxrIHRvIHRoZSBmb3VuZGVyIGRpcmVjdGx5PC9oMz4KICAgIDxwPlRoZSBmdWxsIHRlY2hu"
    "aWNhbCBkZW1vbnN0cmF0aW9uIHRha2VzIGZpZnRlZW4gbWludXRlcywgYW5kIGV2ZXJ5IGNsYWltIG9uIHRoaXMgcGFnZSBjYW4g"
    "YmUgdmVyaWZpZWQgbGl2ZSBkdXJpbmcgaXQuPC9wPgogICAgPGRpdiBjbGFzcz0iY29udGFjdC1saW5rcyI+CiAgICAgIDxhIGhy"
    "ZWY9Im1haWx0bzpqdXN0aW5AbW9ub3Bjb250ZW50LmNvbSI+anVzdGluQG1vbm9wY29udGVudC5jb208L2E+CiAgICAgIDxhIGhy"
    "ZWY9Imh0dHBzOi8vc2ViYmkucHJvIj5zZWJiaS5wcm88L2E+CiAgICAgIDxhIGhyZWY9Imh0dHBzOi8vc2ViYmkucHJvL21hcCI+"
    "c2ViYmkucHJvL21hcCAmbWRhc2g7IHRoZSBzeXN0ZW0sIG1hcHBlZDwvYT4KICAgICAgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5w"
    "cm8vd2hpdGVwYXBlciI+c2ViYmkucHJvL3doaXRlcGFwZXI8L2E+CiAgICA8L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8Zm9vdGVy"
    "IGNsYXNzPSJ3cmFwIj4KICA8cD5KdXN0aW4gQW50b255IERvYnNvbiAmbWlkZG90OyBNb25vcCBDb250ZW50ICZtaWRkb3Q7IEJs"
    "eXRoLCBOb3J0aHVtYmVybGFuZCwgVUs8YnI+CiAgVGhpcyBkb2N1bWVudCBpcyBhIHN1bW1hcnkgZm9yIGluZm9ybWF0aW9uIGFu"
    "ZCBkb2VzIG5vdCBjb25zdGl0dXRlIGFuIG9mZmVyIG9mIHNlY3VyaXRpZXMuIEFsbCBmaWd1cmVzIHNob3VsZCBiZSBpbmRlcGVu"
    "ZGVudGx5IHZlcmlmaWVkIGJlZm9yZSBhbnkgaW52ZXN0bWVudCBkZWNpc2lvbi4gUmVndWxhdG9yeSBkYXRlcyBhcmUgc3RhdGVk"
    "IGFzIGFtZW5kZWQgYnkgdGhlIEFJIE9tbmlidXMgYW5kIGFyZSBzdWJqZWN0IHRvIGNoYW5nZS48L3A+CjwvZm9vdGVyPgoKPHNj"
    "cmlwdD4KICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG9jLWRhdGUnKS50ZXh0Q29udGVudCA9IG5ldyBEYXRlKCkudG9Mb2Nh"
    "bGVEYXRlU3RyaW5nKCdlbi1HQicse2RheTonbnVtZXJpYycsbW9udGg6J2xvbmcnLHllYXI6J251bWVyaWMnfSk7CiAgdmFyIGRl"
    "YWRsaW5lID0gbmV3IERhdGUoJzIwMjctMTItMDJUMDA6MDA6MDBaJyk7CiAgdmFyIG5vdyA9IG5ldyBEYXRlKCk7CiAgdmFyIGRh"
    "eXMgPSBNYXRoLm1heCgwLCBNYXRoLmNlaWwoKGRlYWRsaW5lIC0gbm93KSAvICgxMDAwKjYwKjYwKjI0KSkpOwogIGRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCdjb3VudGRvd24tZGF5cycpLnRleHRDb250ZW50ID0gZGF5cy50b0xvY2FsZVN0cmluZygpICsgJyBk"
    "YXlzJzsKPC9zY3JpcHQ+Cgo8L2JvZHk+CjwvaHRtbD4K"
)

_HTML = base64.b64decode("".join(_B64.split())).decode("utf-8")
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_investor_patched", False):
        _patched = True
        return True
    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == PAGE_PATH:
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._investor_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    if action == "spec":
        return ({
            "module": "investor",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/investor/status once after each deploy to arm " + PAGE_PATH + ".",
        }, 200)
    return ({
        "module": "investor",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/lineage.py`

330 lines, 15462 bytes

```python
import re
import time
from datetime import datetime, timezone

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec")}

OUR_CHAIN_NAME = "aileash"
DEFAULT_BASE = "https://sebbi.pro"

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


def _get_base_url(ctx):
    if isinstance(ctx, dict):
        base = ctx.get("base_url") or (ctx.get("config") or {}).get("base_url")
        if base:
            return str(base).rstrip("/")
    return DEFAULT_BASE


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


def _verification_plan(chain, receipt, base=None, our_base=DEFAULT_BASE):
    root = (base or our_base).rstrip("/") if chain != OUR_CHAIN_NAME else our_base
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % our_base,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (our_base, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


def _declare(ctx, api_key, data):
    our_base = _get_base_url(ctx)
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
            "trace": "%s/x/lineage/trace?receipt=%s" % (our_base, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (our_base, child)}, 200


def _walk(ctx, start, depth, upstream):
    our_base = _get_base_url(ctx)
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
                                     "verify": _verification_plan(chain, other, base, our_base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base, our_base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated


def _trace(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)
    our_base = _get_base_url(ctx)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [],
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base),
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


def _receipt(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    our_base = _get_base_url(ctx)
    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "verify": _verification_plan(r[0], r[1], r[2], our_base=our_base)} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (our_base, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % our_base,
            "nothing_was_left_out": "%s/x/complete/periods" % our_base,
            "who_witnesses_us": "%s/x/witness/peers" % our_base,
            "our_current_tip": "%s/x/witness/tip" % our_base,
            "the_engine_reproduces": "%s/x/replay/spec" % our_base,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (our_base, receipt),
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

```
