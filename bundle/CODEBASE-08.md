# Codebase — part 8 of 40

Contains:
- `modules/fingerprint.py`
- `modules/game.py`
- `modules/genesis.py`


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


## `modules/game.py`

667 lines, 60222 bytes

```python
"""
modules/game.py  v1.0.0
Deep Run - the sebbi.pro game, at /game, with a shared top-pilots board.

Page module (runtime do_GET patch, like map.py) plus a tiny API:

    GET  /x/game/status   arms /game                      (public)
    GET  /x/game/scores   the top ten, each with its block (public)
    POST /x/game/submit   {name, score, sector, kills}     (public)

A submitted score that makes the top ten is sealed into the sebbi.pro chain,
so every name on the board carries a block anyone can check. Scores that do
not make the top ten are not stored and not sealed, so the chain is never
flooded. Light plausibility checks stop obviously impossible scores.
"""

import base64
import re
import sys
import time

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "scores"), ("POST", "submit")}
PAGE_PATH = "/game"
TOP = 10
KEY = "public-game"
NAME_RE = re.compile(r"[^A-Z0-9 ]")

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9InV0Zi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyLG1h"
    "eGltdW0tc2NhbGU9MSx1c2VyLXNjYWxhYmxlPW5vIj4KPG1ldGEgbmFtZT0idGhlbWUtY29sb3IiIGNvbnRlbnQ9IiMwNTA3MGYi"
    "Pgo8dGl0bGU+RGVlcCBSdW4g4oCUIHRoZSBzZWJiaS5wcm8gZ2FtZTwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBj"
    "b250ZW50PSJGbHkgdGhlIExlYXNoIHRocm91Z2ggZmlmdGVlbiBzZWN0b3JzIG9mIHJvZ3VlIEFJIGFnZW50cy4gRXZlcnkgaGln"
    "aCBzY29yZSBpcyBzZWFsZWQgaW50byB0aGUgc2ViYmkucHJvIGNoYWluLiI+CjxzdHlsZT4KOnJvb3R7LS1nb2xkOiNjOWE4NGM7"
    "LS1vazojN2ZlM2IwOy0tZXJyOiNmZjhhODA7LS1ibHVlOiM4ZmQwZmY7LS1tdXRlOiM3ZDg5YTg7LS1saW5lOnJnYmEoMjAxLDE2"
    "OCw3NiwuMjUpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDstd2Via2l0LXRhcC1oaWdobGlnaHQtY29sb3I6dHJhbnNwYXJlbnR9"
    "Cmh0bWwsYm9keXtoZWlnaHQ6MTAwJTttYXJnaW46MDtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMDUwNzBmO2NvbG9yOiNl"
    "OGVkZjc7Zm9udC1mYW1pbHk6IkludGVyIiwiSGVsdmV0aWNhIE5ldWUiLEhlbHZldGljYSxBcmlhbCxzYW5zLXNlcmlmO292ZXJz"
    "Y3JvbGwtYmVoYXZpb3I6bm9uZX0KLm51bXtmb250LWZhbWlseTp1aS1tb25vc3BhY2UsU0ZNb25vLVJlZ3VsYXIsTWVubG8sbW9u"
    "b3NwYWNlO2ZvbnQtdmFyaWFudC1udW1lcmljOnRhYnVsYXItbnVtc30KI3dyYXB7cG9zaXRpb246Zml4ZWQ7aW5zZXQ6MH1jYW52"
    "YXN7ZGlzcGxheTpibG9jazt3aWR0aDoxMDAlO2hlaWdodDoxMDAlO3RvdWNoLWFjdGlvbjpub25lfQojaHVke3Bvc2l0aW9uOmFi"
    "c29sdXRlO2xlZnQ6MDtyaWdodDowO3RvcDowO3otaW5kZXg6MTA7ZGlzcGxheTpmbGV4O2dhcDoxNHB4O3BhZGRpbmc6MTBweCAx"
    "NHB4O3BhZGRpbmctdG9wOmNhbGMoMTBweCArIGVudihzYWZlLWFyZWEtaW5zZXQtdG9wKSk7cG9pbnRlci1ldmVudHM6bm9uZX0K"
    "I2h1ZCAua3tmb250LXNpemU6OXB4O2xldHRlci1zcGFjaW5nOi4xMmVtO2NvbG9yOnZhcigtLW11dGUpfSNodWQgLnZ7Zm9udC1z"
    "aXplOjE1cHg7Zm9udC13ZWlnaHQ6NzAwO3RleHQtc2hhZG93OjAgMCAxMHB4ICMwMDB9CiNjb21ib3tjb2xvcjp2YXIoLS1nb2xk"
    "KX0jY2hhaW57Y29sb3I6dmFyKC0tb2spfQojcmlnaHR7bWFyZ2luLWxlZnQ6YXV0bztkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rp"
    "b246Y29sdW1uO2FsaWduLWl0ZW1zOmZsZXgtZW5kO2dhcDo0cHh9CiNodWxse3dpZHRoOjkycHg7aGVpZ2h0OjdweDtib3JkZXI6"
    "MXB4IHNvbGlkIHJnYmEoMjAxLDE2OCw3NiwuNSk7Ym9yZGVyLXJhZGl1czozcHg7b3ZlcmZsb3c6aGlkZGVufQojaHVsbEZ7aGVp"
    "Z2h0OjEwMCU7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCg5MGRlZywjZmY4YTgwLCM3ZmUzYjApO3RyYW5z"
    "aXRpb246d2lkdGggLjJzfQojcHd7Zm9udC1zaXplOjEwcHg7bGV0dGVyLXNwYWNpbmc6LjA4ZW07Y29sb3I6dmFyKC0tYmx1ZSk7"
    "bWluLWhlaWdodDoxMnB4fQojbXV0ZXtwb3NpdGlvbjphYnNvbHV0ZTtyaWdodDoxMnB4O2JvdHRvbTpjYWxjKDEycHggKyBlbnYo"
    "c2FmZS1hcmVhLWluc2V0LWJvdHRvbSkpO3otaW5kZXg6MTI7YmFja2dyb3VuZDpyZ2JhKDEzLDIwLDM2LC44KTtib3JkZXI6MXB4"
    "IHNvbGlkIHZhcigtLWxpbmUpO2NvbG9yOiNjM2NiZGQ7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzo2cHggOXB4O2ZvbnQtc2l6"
    "ZToxMnB4fQouc2NyZWVue3Bvc2l0aW9uOmFic29sdXRlO2luc2V0OjA7ei1pbmRleDoyMDtkaXNwbGF5Om5vbmU7ZmxleC1kaXJl"
    "Y3Rpb246Y29sdW1uO2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO2dhcDoxNHB4O3BhZGRpbmc6MjZw"
    "eCAyMHB4O3RleHQtYWxpZ246Y2VudGVyO2JhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGVsbGlwc2UgYXQgY2VudGVyLHJnYmEo"
    "MTMsMjAsMzYsLjg4KSxyZ2JhKDUsNywxNSwuOTcpKTtvdmVyZmxvdy15OmF1dG99Ci5zY3JlZW4ub257ZGlzcGxheTpmbGV4fQpo"
    "MXttYXJnaW46MDtmb250LXNpemU6NDRweDtmb250LXdlaWdodDo5MDA7bGV0dGVyLXNwYWNpbmc6LS4wMmVtO2xpbmUtaGVpZ2h0"
    "OjE7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsI2M5YTg0YywjN2ZlM2IwLCM4ZmQwZmYpOy13ZWJraXQtYmFja2dy"
    "b3VuZC1jbGlwOnRleHQ7YmFja2dyb3VuZC1jbGlwOnRleHQ7Y29sb3I6dHJhbnNwYXJlbnQ7ZmlsdGVyOmRyb3Atc2hhZG93KDAg"
    "MCAxOHB4IHJnYmEoMjAxLDE2OCw3NiwuMzUpKX0KaDJ7bWFyZ2luOjA7Zm9udC1zaXplOjIycHg7Zm9udC13ZWlnaHQ6ODAwfQou"
    "c3Vie2ZvbnQtc2l6ZToxMXB4O2xldHRlci1zcGFjaW5nOi4yZW07Y29sb3I6dmFyKC0tZ29sZCl9CnAubGVkZXttYXJnaW46MDtt"
    "YXgtd2lkdGg6MzRjaDtmb250LXNpemU6MTRweDtsaW5lLWhlaWdodDoxLjU1O2NvbG9yOiNiNmMwZDZ9Ci5idG57Ym9yZGVyOjA7"
    "Ym9yZGVyLXJhZGl1czoxMXB4O3BhZGRpbmc6MTRweCAzMHB4O2ZvbnQtc2l6ZToxNXB4O2ZvbnQtd2VpZ2h0OjgwMDtiYWNrZ3Jv"
    "dW5kOnZhcigtLWdvbGQpO2NvbG9yOiMwNTA3MGY7Y3Vyc29yOnBvaW50ZXI7bWluLXdpZHRoOjIxMHB4O2JveC1zaGFkb3c6MCAw"
    "IDI0cHggcmdiYSgyMDEsMTY4LDc2LC4zNSl9Ci5idG4uZ2hvc3R7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjp2YXIoLS1n"
    "b2xkKTtib3JkZXI6MS41cHggc29saWQgdmFyKC0tbGluZSk7Ym94LXNoYWRvdzpub25lfQouc3RhdHN7ZGlzcGxheTpmbGV4O2dh"
    "cDoyNHB4O2p1c3RpZnktY29udGVudDpjZW50ZXI7ZmxleC13cmFwOndyYXB9LnN0YXRzIC5re2ZvbnQtc2l6ZTo5cHg7bGV0dGVy"
    "LXNwYWNpbmc6LjEyZW07Y29sb3I6dmFyKC0tbXV0ZSl9LnN0YXRzIC52e2ZvbnQtc2l6ZToyNnB4O2ZvbnQtd2VpZ2h0OjgwMH0K"
    "LmJvYXJke3dpZHRoOjEwMCU7bWF4LXdpZHRoOjMwMHB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1"
    "czoxMnB4O3BhZGRpbmc6MTBweCAxNHB4O2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwuNil9Ci5ib2FyZCAudHtmb250LXNpemU6"
    "MTBweDtsZXR0ZXItc3BhY2luZzouMThlbTtjb2xvcjp2YXIoLS1nb2xkKTttYXJnaW4tYm90dG9tOjZweH0KLnJvd3tkaXNwbGF5"
    "OmZsZXg7Z2FwOjEwcHg7YWxpZ24taXRlbXM6Y2VudGVyO3BhZGRpbmc6NXB4IDA7Zm9udC1zaXplOjE0cHg7Ym9yZGVyLXRvcDox"
    "cHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMDUpfQoucm93OmZpcnN0LW9mLXR5cGV7Ym9yZGVyLXRvcDowfS5yb3cgLm17d2lk"
    "dGg6MjJweDtmb250LXdlaWdodDo4MDB9LnJvdyAubntmbGV4OjE7dGV4dC1hbGlnbjpsZWZ0O2ZvbnQtd2VpZ2h0OjcwMH0ucm93"
    "IC5ze2ZvbnQtZmFtaWx5OnVpLW1vbm9zcGFjZSxtb25vc3BhY2V9Ci5yb3cgYXtmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1v"
    "ayk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2luLWxlZnQ6NnB4fQojbmFtZUJveHtkaXNwbGF5Om5vbmU7ZmxleC1kaXJlY3Rp"
    "b246Y29sdW1uO2dhcDoxMHB4O2FsaWduLWl0ZW1zOmNlbnRlcn0KI25hbWVJbntiYWNrZ3JvdW5kOiMwZDE0MjQ7Ym9yZGVyOjEu"
    "NXB4IHNvbGlkIHZhcigtLWdvbGQpO2JvcmRlci1yYWRpdXM6MTBweDtjb2xvcjojZmZmO2ZvbnQtc2l6ZToyMHB4O2ZvbnQtd2Vp"
    "Z2h0OjgwMDt0ZXh0LWFsaWduOmNlbnRlcjtwYWRkaW5nOjEwcHg7d2lkdGg6MjMwcHg7bGV0dGVyLXNwYWNpbmc6LjA4ZW07dGV4"
    "dC10cmFuc2Zvcm06dXBwZXJjYXNlfQojc2VhbGVke2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW9rKTttYXgtd2lkdGg6MzRj"
    "aH0KI3NlYWxlZCBhe2NvbG9yOnZhcigtLW9rKX0KI2x2e2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6cmVwZWF0"
    "KDUsMWZyKTtnYXA6N3B4O3dpZHRoOjEwMCU7bWF4LXdpZHRoOjI5MHB4fQojbHYgYnV0dG9ue2FzcGVjdC1yYXRpbzoxO2JvcmRl"
    "ci1yYWRpdXM6OXB4O2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4wMyk7"
    "Y29sb3I6I2MzY2JkZDtmb250LXNpemU6MTRweDtmb250LXdlaWdodDo4MDA7Zm9udC1mYW1pbHk6dWktbW9ub3NwYWNlLG1vbm9z"
    "cGFjZX0KI2x2IGJ1dHRvbi5kb25le2JhY2tncm91bmQ6cmdiYSgyMDEsMTY4LDc2LC4xNik7Y29sb3I6dmFyKC0tZ29sZCk7Ym9y"
    "ZGVyLWNvbG9yOnZhcigtLWdvbGQpfSNsdiBidXR0b24uYm9zc3tib3JkZXItY29sb3I6dmFyKC0tZXJyKX0jbHYgYnV0dG9uLmxv"
    "Y2t7b3BhY2l0eTouMjJ9CiNmbGFzaHtwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjA7cmlnaHQ6MDt0b3A6MjglO3otaW5kZXg6MTU7"
    "dGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjIycHg7Zm9udC13ZWlnaHQ6OTAwO2xldHRlci1zcGFjaW5nOi4wNGVtO3BvaW50"
    "ZXItZXZlbnRzOm5vbmU7b3BhY2l0eTowO3RyYW5zaXRpb246b3BhY2l0eSAuMzVzO3RleHQtc2hhZG93OjAgMCAxOHB4IHJnYmEo"
    "MCwwLDAsLjkpLDAgMCAzMHB4IGN1cnJlbnRDb2xvcn0KI2ZhY3R7cG9zaXRpb246YWJzb2x1dGU7bGVmdDowO3JpZ2h0OjA7dG9w"
    "OmNhbGMoMjglICsgMzRweCk7ei1pbmRleDoxNTt0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTJweDtjb2xvcjojYjZjMGQ2"
    "O3BvaW50ZXItZXZlbnRzOm5vbmU7b3BhY2l0eTowO3RyYW5zaXRpb246b3BhY2l0eSAuMzVzO3BhZGRpbmc6MCAyMHB4fQojaGlu"
    "dHtwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjA7cmlnaHQ6MDtib3R0b206Y2FsYygxNHB4ICsgZW52KHNhZmUtYXJlYS1pbnNldC1i"
    "b3R0b20pKTt6LWluZGV4OjEwO3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMXB4O2xldHRlci1zcGFjaW5nOi4wNmVtO2Nv"
    "bG9yOnZhcigtLW11dGUpO3BvaW50ZXItZXZlbnRzOm5vbmV9Ci5sZWdlbmR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29s"
    "dW1uczoxZnIgMWZyO2dhcDo2cHggMTRweDttYXgtd2lkdGg6MzIwcHg7Zm9udC1zaXplOjExLjVweDt0ZXh0LWFsaWduOmxlZnQ7"
    "Y29sb3I6I2I2YzBkNn0KLmxlZ2VuZCBie2ZvbnQtZmFtaWx5OnVpLW1vbm9zcGFjZSxtb25vc3BhY2U7Zm9udC1zaXplOjExcHh9"
    "Ci5ob21le2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO3RleHQtZGVjb3JhdGlvbjpub25lfQo8L3N0eWxlPgo8L2hl"
    "YWQ+Cjxib2R5Pgo8ZGl2IGlkPSJ3cmFwIj4KPGNhbnZhcyBpZD0iY3YiPjwvY2FudmFzPgo8ZGl2IGlkPSJodWQiPgogPGRpdj48"
    "ZGl2IGNsYXNzPSJrIj5TQ09SRTwvZGl2PjxkaXYgY2xhc3M9InYgbnVtIiBpZD0iaFNjb3JlIj4wPC9kaXY+PC9kaXY+CiA8ZGl2"
    "PjxkaXYgY2xhc3M9ImsiPlNFQ1RPUjwvZGl2PjxkaXYgY2xhc3M9InYgbnVtIiBpZD0iaExldmVsIj4xPC9kaXY+PC9kaXY+CiA8"
    "ZGl2PjxkaXYgY2xhc3M9ImsiPkNPTUJPPC9kaXY+PGRpdiBjbGFzcz0idiBudW0iIGlkPSJjb21ibyI+eDE8L2Rpdj48L2Rpdj4K"
    "IDxkaXY+PGRpdiBjbGFzcz0iayI+Q0hBSU48L2Rpdj48ZGl2IGNsYXNzPSJ2IG51bSIgaWQ9ImNoYWluIj4jMDwvZGl2PjwvZGl2"
    "PgogPGRpdiBpZD0icmlnaHQiPjxkaXYgaWQ9Imh1bGwiPjxkaXYgaWQ9Imh1bGxGIj48L2Rpdj48L2Rpdj48ZGl2IGlkPSJwdyI+"
    "PC9kaXY+PC9kaXY+CjwvZGl2Pgo8ZGl2IGlkPSJmbGFzaCI+PC9kaXY+PGRpdiBpZD0iZmFjdCI+PC9kaXY+CjxkaXYgaWQ9Imhp"
    "bnQiPkRyYWcgdG8gZmx5IMK3IGd1bnMgZmlyZSB0aGVtc2VsdmVzPC9kaXY+CjxidXR0b24gaWQ9Im11dGUiPvCflIo8L2J1dHRv"
    "bj4KCjxkaXYgY2xhc3M9InNjcmVlbiBvbiIgaWQ9InNjVGl0bGUiPgogPGRpdiBjbGFzcz0ic3ViIj5TRUJCSS5QUk8gUFJFU0VO"
    "VFM8L2Rpdj4KIDxoMT5ERUVQIFJVTjwvaDE+CiA8cCBjbGFzcz0ibGVkZSI+Um9ndWUgQUkgYWdlbnRzIGFyZSBicmVha2luZyBv"
    "dXQuIFlvdSBmbHkgdGhlIExlYXNoLiBFdmVyeSBhZ2VudCB5b3Ugc3RvcCBpcyBzZWFsZWQgaW50byB0aGUgY2hhaW4uIEZpZnRl"
    "ZW4gc2VjdG9ycy4gVGhyZWUgb3JjaGVzdHJhdG9ycy4gRG9uJ3QgbGV0IHRoZW0gdGhyb3VnaC48L3A+CiA8YnV0dG9uIGNsYXNz"
    "PSJidG4iIGlkPSJiU3RhcnQiPkxhdW5jaDwvYnV0dG9uPgogPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0iYlBpY2siPkNo"
    "b29zZSBhIHNlY3RvcjwvYnV0dG9uPgogPGRpdiBjbGFzcz0iYm9hcmQiPjxkaXYgY2xhc3M9InQiPlRPUCBQSUxPVFMgwrcgU0VB"
    "TEVEIE9OIFRIRSBDSEFJTjwvZGl2PjxkaXYgaWQ9ImJvYXJkVCI+TG9hZGluZ+KApjwvZGl2PjwvZGl2PgogPGRpdiBjbGFzcz0i"
    "bGVnZW5kIj4KICA8ZGl2PjxiIHN0eWxlPSJjb2xvcjojN2ZlM2IwIj5VTlNJR05FRDwvYj4gbm8gYXV0aG9yaXR5PC9kaXY+PGRp"
    "dj48YiBzdHlsZT0iY29sb3I6IzhmZDBmZiI+UkVQTEFZPC9iPiBmYXN0LCB3ZWF2aW5nPC9kaXY+CiAgPGRpdj48YiBzdHlsZT0i"
    "Y29sb3I6I2M5YTg0YyI+Rk9SR0VEPC9iPiBhcm1vdXJlZDwvZGl2PjxkaXY+PGIgc3R5bGU9ImNvbG9yOiNmZjhhODAiPlJFVk9L"
    "RUQ8L2I+IGh1bnRzIHlvdTwvZGl2PgogIDxkaXY+PGIgc3R5bGU9ImNvbG9yOiNmNWMyNmIiPlJPR1VFPC9iPiBzaG9vdHMgYmFj"
    "azwvZGl2PjxkaXY+PGIgc3R5bGU9ImNvbG9yOiNkNTliZmYiPlNQTElUVEVSPC9iPiBicmVha3MgaW4gdHdvPC9kaXY+CiAgPGRp"
    "dj48YiBzdHlsZT0iY29sb3I6IzdmZTNiMCI+4peGIFBBU1NQT1JUPC9iPiBzcHJlYWQgc2hvdDwvZGl2PjxkaXY+PGIgc3R5bGU9"
    "ImNvbG9yOiM4ZmQwZmYiPuKXhiBXSVRORVNTPC9iPiBzaGllbGQgZHJvbmVzPC9kaXY+CiAgPGRpdj48YiBzdHlsZT0iY29sb3I6"
    "I2Y3OTMxYSI+4peGIEFOQ0hPUjwvYj4gY2xlYXJzIHRoZSBzY3JlZW48L2Rpdj48ZGl2PjxiIHN0eWxlPSJjb2xvcjojZmY4YTgw"
    "Ij7il4YgUkVQQUlSPC9iPiBwYXRjaGVzIGh1bGw8L2Rpdj4KIDwvZGl2PgogPGEgY2xhc3M9ImhvbWUiIGhyZWY9Ii8iPuKGkCBi"
    "YWNrIHRvIHNlYmJpLnBybzwvYT4KPC9kaXY+Cgo8ZGl2IGNsYXNzPSJzY3JlZW4iIGlkPSJzY1BpY2siPjxoMj5DaG9vc2UgYSBz"
    "ZWN0b3I8L2gyPjxwIGNsYXNzPSJsZWRlIiBpZD0icGlja1N1YiI+PC9wPjxkaXYgaWQ9Imx2Ij48L2Rpdj48YnV0dG9uIGNsYXNz"
    "PSJidG4gZ2hvc3QiIGlkPSJiQmFjayI+QmFjazwvYnV0dG9uPjwvZGl2PgoKPGRpdiBjbGFzcz0ic2NyZWVuIiBpZD0ic2NOZXh0"
    "Ij4KIDxoMiBpZD0ibmV4dFRpdGxlIj5TZWN0b3IgY2xlYXI8L2gyPgogPGRpdiBjbGFzcz0ic3RhdHMiPjxkaXY+PGRpdiBjbGFz"
    "cz0iayI+U0NPUkU8L2Rpdj48ZGl2IGNsYXNzPSJ2IG51bSIgaWQ9Im5TY29yZSI+MDwvZGl2PjwvZGl2PjxkaXY+PGRpdiBjbGFz"
    "cz0iayI+U0VBTEVEPC9kaXY+PGRpdiBjbGFzcz0idiBudW0iIGlkPSJuS2lsbHMiPjA8L2Rpdj48L2Rpdj48L2Rpdj4KIDxwIGNs"
    "YXNzPSJsZWRlIiBpZD0ibmV4dE5vdGUiPjwvcD4KIDxidXR0b24gY2xhc3M9ImJ0biIgaWQ9ImJOZXh0Ij5OZXh0IHNlY3Rvcjwv"
    "YnV0dG9uPgogPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0iYlF1aXQiPkVuZCBydW48L2J1dHRvbj4KPC9kaXY+Cgo8ZGl2"
    "IGNsYXNzPSJzY3JlZW4iIGlkPSJzY092ZXIiPgogPGgyIGlkPSJvdmVyVGl0bGUiPkh1bGwgYnJlYWNoZWQ8L2gyPgogPGRpdiBj"
    "bGFzcz0ic3RhdHMiPjxkaXY+PGRpdiBjbGFzcz0iayI+U0NPUkU8L2Rpdj48ZGl2IGNsYXNzPSJ2IG51bSIgaWQ9Im9TY29yZSI+"
    "MDwvZGl2PjwvZGl2PjxkaXY+PGRpdiBjbGFzcz0iayI+U0VDVE9SPC9kaXY+PGRpdiBjbGFzcz0idiBudW0iIGlkPSJvTGV2ZWwi"
    "PjE8L2Rpdj48L2Rpdj48ZGl2PjxkaXYgY2xhc3M9ImsiPlNFQUxFRDwvZGl2PjxkaXYgY2xhc3M9InYgbnVtIiBpZD0ib0tpbGxz"
    "Ij4wPC9kaXY+PC9kaXY+PC9kaXY+CiA8ZGl2IGlkPSJuYW1lQm94Ij48ZGl2IGNsYXNzPSJzdWIiPk5FVyBUT1AgU0NPUkUg4oCU"
    "IFNFQUwgWU9VUiBOQU1FPC9kaXY+PGlucHV0IGlkPSJuYW1lSW4iIG1heGxlbmd0aD0iMTIiIGF1dG9jb21wbGV0ZT0ib2ZmIiBw"
    "bGFjZWhvbGRlcj0iWU9VUiBOQU1FIj48YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJiU2VhbCI+U2VhbCBpdCBvbiB0aGUgY2hhaW48"
    "L2J1dHRvbj48L2Rpdj4KIDxkaXYgaWQ9InNlYWxlZCI+PC9kaXY+CiA8ZGl2IGNsYXNzPSJib2FyZCI+PGRpdiBjbGFzcz0idCI+"
    "VE9QIFBJTE9UUzwvZGl2PjxkaXYgaWQ9ImJvYXJkTyI+PC9kaXY+PC9kaXY+CiA8YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJiUmV0"
    "cnkiPkZseSBhZ2FpbjwvYnV0dG9uPgogPGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBpZD0iYkhvbWUiPkJhY2sgdG8gc3RhcnQ8"
    "L2J1dHRvbj4KPC9kaXY+CjwvZGl2PgoKPHNjcmlwdD4KKGZ1bmN0aW9uKCl7CiJ1c2Ugc3RyaWN0IjsKdmFyIGN2PWRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJjdiIpLGN0eD1jdi5nZXRDb250ZXh0KCIyZCIpOwp2YXIgVz0wLEg9MCxkcHI9MSxDWD0wLENZPTAs"
    "Rj00NjAsTUFYTFY9MTU7CmZ1bmN0aW9uICQoaSl7cmV0dXJuIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGkpfQpmdW5jdGlvbiBj"
    "bGFtcCh2LGEsYil7cmV0dXJuIHY8YT9hOih2PmI/Yjp2KX1mdW5jdGlvbiBybmQoYSxiKXtyZXR1cm4gYStNYXRoLnJhbmRvbSgp"
    "KihiLWEpfWZ1bmN0aW9uIHBpY2soYSl7cmV0dXJuIGFbKE1hdGgucmFuZG9tKCkqYS5sZW5ndGgpfDBdfQoKLyogLS0tLS0tLS0t"
    "LSBzZWN0b3JzIC0tLS0tLS0tLS0gKi8KdmFyIFRIRU1FUz1bWyJSaW5ncyBvZiBTYXR1cm4iLCJzYXR1cm4iLCIjMGExMDIwIl0s"
    "WyJPY2hyZSBCZWx0IiwicnVzdCIsIiMxMjBjMTQiXSxbIkJsdWUgR2lhbnQiLCJpY2UiLCIjMDgxMTFmIl0sWyJBc2ggRmllbGQi"
    "LCJtb29uIiwiIzBkMGQxMiJdLFsiVGhlIEdhdGVob3VzZSIsImVtYmVyIiwiIzEyMDcwYyJdLAogWyJHcmVlbiBEcmlmdCIsImph"
    "ZGUiLCIjMDcxMzBmIl0sWyJJbm5lciBSaW5ncyIsInNhdHVybiIsIiMwYTEwMjAiXSxbIkNyaW1zb24gUmVhY2giLCJlbWJlciIs"
    "IiMxNDBhMGQiXSxbIlNoYXR0ZXJlZCBNb29uIiwibW9vbiIsIiMwYjBlMTYiXSxbIlRoZSBSZWxheSIsInZvaWQiLCIjMDcwODEy"
    "Il0sCiBbIk5lYnVsYSBSdW4iLCJuZWJ1bGEiLCIjMGMwNzE2Il0sWyJGcm96ZW4gTGVkZ2VyIiwiaWNlIiwiIzA2MGQxYSJdLFsi"
    "VGhlIExvbmcgRGFyayIsInZvaWQiLCIjMDUwNzEwIl0sWyJHZW5lc2lzIEZpZWxkcyIsImphZGUiLCIjMDYxMjBlIl0sWyJUaGUg"
    "Q29yZSIsImVtYmVyIiwiIzEyMDYwYSJdXTsKdmFyIEZBQ1RTPVsiRXZlcnkgYWdlbnQgeW91IHN0b3AgaXMgc2VhbGVkIGludG8g"
    "YSBoYXNoIGNoYWluLiBDaGFuZ2Ugb25lIHJlY29yZCBhbmQgZXZlcnkgcmVjb3JkIGFmdGVyIGl0IGJyZWFrcy4iLAogIkFuIFVO"
    "U0lHTkVEIGFnZW50IGhhcyBubyBhdXRob3JpdHkgdHJhY2VkIGJhY2sgdG8gYSBodW1hbi4gVGhlIExlYXNoIHN0b3BzIGl0LiIs"
    "CiAiQSBSRVBMQVkgdHJpZXMgdG8gc3BlbmQgdGhlIHNhbWUgcGFzc3BvcnQgdHdpY2UuIE9uZSBwYXNzcG9ydCwgb25lIGFjdGlv"
    "bi4gRXZlci4iLAogIkZPUkdFRCBhZ2VudHMgY2FycnkgYSBmYWtlIHNpZ25hdHVyZS4gSXQgZmFpbHMgdGhlIEVkMjU1MTkgY2hl"
    "Y2sgaW4gZml2ZSBtaWxsaXNlY29uZHMuIiwKICJPcmNoZXN0cmF0b3IgZG93bi4gT24gc2ViYmkucHJvLCBldmVyeSByZWZ1c2Fs"
    "IGlzIHNlYWxlZCB0b28g4oCUIGFuIGFnZW50IGNhbiBwcm92ZSBpdCB3YXMgTk9UIGFsbG93ZWQuIiwKICJSRVZPS0VEIGFnZW50"
    "cyBsb3N0IHRoZWlyIGF1dGhvcml0eSBzZWNvbmRzIGFnby4gVGhlIExlYXNoIHJlLWNoZWNrcyBhdCB0aGUgbW9tZW50IG9mIGFj"
    "dGlvbi4iLAogIldJVE5FU1MgZHJvbmVzIGFyZSBsaWtlIHRoZSBpbmRlcGVuZGVudCBvcmdhbmlzYXRpb25zIGhvbGRpbmcgY29w"
    "aWVzIG9mIG91ciBjaGFpbi4iLAogIlRoZSBBTkNIT1Igc3RhbXBzIHRpbWUgaW50byBCaXRjb2luLiBOb2JvZHkgY2FuIG1vdmUg"
    "YSB0aW1lc3RhbXAgYWZ0ZXIgdGhhdC4iLAogIlJPR1VFIGFnZW50cyBmaXJlIGJhY2suIEV2ZXJ5IGRlY2lzaW9uLCBhbGxvdyBv"
    "ciBibG9jaywgc3RpbGwgbGFuZHMgb24gdGhlIGNoYWluLiIsCiAiU2Vjb25kIG9yY2hlc3RyYXRvciBkb3duLiBDaGVjayBldmVy"
    "eSBwcm9vZiB5b3Vyc2VsZiBhdCBzZWJiaS5wcm8vcHJvdmUuIiwKICJTUExJVFRFUlMgdHJ5IHRvIGJlY29tZSB0d28gYWdlbnRz"
    "LiBUd28gbmFycm93IGF1dGhvcml0aWVzIG5ldmVyIGNvbWJpbmUgb24gc2ViYmkucHJvLiIsCiAiVGhlIGNoYWluIGlzIGNoZWNr"
    "ZWQgYWdhaW5zdCB0d28gcHVibGljIEJpdGNvaW4gZXhwbG9yZXJzLCBub3Qgb3VyIG93biBzZXJ2ZXJzLiIsCiAiT3V0IGhlcmUg"
    "dGhlIG9ubHkgbGlnaHQgaXMgcHJvb2YuIFZlcmlmeSBpdCB3aXRoIG91ciBzZXJ2ZXJzIHN3aXRjaGVkIG9mZi4iLAogIkdlbmVz"
    "aXM6IGV2ZXJ5IGNoYWluIHN0YXJ0cyBzb21ld2hlcmUuIE91cnMgaXMgYW5jaG9yZWQgYW5kIHdpdG5lc3NlZC4iLAogIlRoZSBD"
    "b3JlLiBCZWF0IGl0LCBhbmQgeW91ciBuYW1lIGlzIHNlYWxlZCBpbnRvIHRoZSBzZWJiaS5wcm8gY2hhaW4uIl07CnZhciBTRUNU"
    "T1JTPVtdOwpmb3IodmFyIHNpPTA7c2k8TUFYTFY7c2krKyl7dmFyIHRoPVRIRU1FU1tzaV0sbj1zaSsxLGJvc3M9KG4lNT09PTAp"
    "OwogdmFyIG1peGVzPVtbInNjb3V0Iiwic2NvdXQiLCJodWxrIl0sWyJzY291dCIsImh1bGsiLCJtaW5lIl0sWyJzY291dCIsImRh"
    "cnRlciIsImh1bGsiXSxbImRhcnRlciIsIm1pbmUiLCJodWxrIl0sWyJkYXJ0ZXIiLCJ0dXJyZXQiXSwKICBbInNjb3V0IiwiZGFy"
    "dGVyIiwidHVycmV0Iiwic3BsaXQiXSxbImRhcnRlciIsImh1bGsiLCJ0dXJyZXQiXSxbImRhcnRlciIsIm1pbmUiLCJ0dXJyZXQi"
    "LCJzcGxpdCJdLFsiaHVsayIsInR1cnJldCIsImRhcnRlciIsInNwbGl0Il0sWyJkYXJ0ZXIiLCJ0dXJyZXQiXSwKICBbInNwbGl0"
    "IiwiZGFydGVyIiwibWluZSIsInR1cnJldCJdLFsiaHVsayIsInNwbGl0IiwidHVycmV0IiwibWluZSJdLFsiZGFydGVyIiwidHVy"
    "cmV0IiwibWluZSIsImh1bGsiLCJzcGxpdCJdLFsic3BsaXQiLCJ0dXJyZXQiLCJkYXJ0ZXIiLCJodWxrIl0sWyJkYXJ0ZXIiLCJ0"
    "dXJyZXQiLCJzcGxpdCJdXTsKIFNFQ1RPUlMucHVzaCh7bmFtZTp0aFswXSxwbGFuZXQ6dGhbMV0sc2t5OnRoWzJdLGNvdW50OmJv"
    "c3M/MTgrbjoyNCtuKjMsc3BlZWQ6MzMwK24qMjYsZmlyZTouMjgrbiouMSxtaXg6bWl4ZXNbc2ldLGJvc3M6Ym9zcz8obi81KTow"
    "fSk7fQoKLyogLS0tLS0tLS0tLSBlbmVtaWVzIC0tLS0tLS0tLS0gKi8KdmFyIFRZUEU9ewogc2NvdXQ6e2hwOjEscHRzOjYwLHI6"
    "MjYsY29sOiIjN2ZlM2IwIixzcGQ6MSxzd2F5OjEsc2hvb3Q6LjUsbGFiOiJVTlNJR05FRCJ9LAogZGFydGVyOntocDoxLHB0czox"
    "MTAscjoyMixjb2w6IiM4ZmQwZmYiLHNwZDoxLjU1LHN3YXk6Mi4zLHNob290Oi43LGxhYjoiUkVQTEFZIn0sCiBodWxrOntocDo0"
    "LHB0czoyMjAscjo0NCxjb2w6IiNjOWE4NGMiLHNwZDouNzIsc3dheTouNCxzaG9vdDouOCxsYWI6IkZPUkdFRCJ9LAogbWluZTp7"
    "aHA6MSxwdHM6OTAscjoyNCxjb2w6IiNmZjhhODAiLHNwZDouODUsc3dheTowLHNob290OjAsbGFiOiJSRVZPS0VEIn0sCiB0dXJy"
    "ZXQ6e2hwOjIscHRzOjE3MCxyOjMwLGNvbDoiI2Y1YzI2YiIsc3BkOi44LHN3YXk6Ljcsc2hvb3Q6MixsYWI6IlJPR1VFIn0sCiBz"
    "cGxpdDp7aHA6MixwdHM6MTUwLHI6MzIsY29sOiIjZDU5YmZmIixzcGQ6Ljksc3dheToxLjIsc2hvb3Q6LjQsbGFiOiJTUExJVFRF"
    "UiJ9fTsKdmFyIFBXUj17UDp7Y29sOiIjN2ZlM2IwIixsYWI6IlBBU1NQT1JUIn0sVzp7Y29sOiIjOGZkMGZmIixsYWI6IldJVE5F"
    "U1MifSxBOntjb2w6IiNmNzkzMWEiLGxhYjoiQU5DSE9SIn0sUjp7Y29sOiIjZmY4YTgwIixsYWI6IlJFUEFJUiJ9fTsKCi8qIC0t"
    "LS0tLS0tLS0gc3RhdGUgLS0tLS0tLS0tLSAqLwp2YXIgbGV2ZWw9MSxjZmc9U0VDVE9SU1swXSxydW5uaW5nPWZhbHNlLHBhdXNl"
    "ZD10cnVlOwp2YXIgc2NvcmU9MCxraWxscz0wLGh1bGw9MTAwLHN0cmVhaz0wLG11bHQ9MSxjaGFpbk49MDsKdmFyIHN0YXJzPVtd"
    "LGR1c3Q9W10sZm9lcz1bXSxib2x0cz1bXSxmbGFrPVtdLHBvcHM9W10scm9ja3M9W10scmluZ3M9W10sZHJvcHM9W10sZmxvYXRz"
    "PVtdOwp2YXIgYm9zcz1udWxsLHNwYXduZWQ9MCxzcGF3blQ9MCxzaG90VD0wLHNoYWtlPTAsd2FycD0wLGxhc3Q9MCxzcHJlYWQ9"
    "MCxvcmJzPTAsZmxhc2hTY3I9MDsKdmFyIHNoaXA9e3g6MCx5OjAsdHg6MCx0eTowLHJvbGw6MCxpbnY6MH07CnZhciBwcm9nPWxv"
    "YWQoKTsKZnVuY3Rpb24gbG9hZCgpe3RyeXt2YXIgcj1sb2NhbFN0b3JhZ2UuZ2V0SXRlbSgic2ViYmkuZGVlcHJ1bjIiKTtyZXR1"
    "cm4gcj9KU09OLnBhcnNlKHIpOntsdjowLGJlc3Q6MH19Y2F0Y2goZSl7cmV0dXJue2x2OjAsYmVzdDowfX19CmZ1bmN0aW9uIHNh"
    "dmUoKXt0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oInNlYmJpLmRlZXBydW4yIixKU09OLnN0cmluZ2lmeShwcm9nKSl9Y2F0Y2go"
    "ZSl7fX0KCi8qIC0tLS0tLS0tLS0gc291bmQgLS0tLS0tLS0tLSAqLwp2YXIgQUM9bnVsbCxtdXRlZD1mYWxzZTsKZnVuY3Rpb24g"
    "dG9uZShmLGQsdHlwZSx2b2wsc2xpZGUpe2lmKG11dGVkKXJldHVybjt0cnl7QUM9QUN8fG5ldyh3aW5kb3cuQXVkaW9Db250ZXh0"
    "fHx3aW5kb3cud2Via2l0QXVkaW9Db250ZXh0KSgpOwogdmFyIG89QUMuY3JlYXRlT3NjaWxsYXRvcigpLGc9QUMuY3JlYXRlR2Fp"
    "bigpO28udHlwZT10eXBlfHwic3F1YXJlIjtvLmZyZXF1ZW5jeS52YWx1ZT1mO2lmKHNsaWRlKW8uZnJlcXVlbmN5LmV4cG9uZW50"
    "aWFsUmFtcFRvVmFsdWVBdFRpbWUoc2xpZGUsQUMuY3VycmVudFRpbWUrZCk7CiBnLmdhaW4udmFsdWU9dm9sfHwuMDU7Zy5nYWlu"
    "LmV4cG9uZW50aWFsUmFtcFRvVmFsdWVBdFRpbWUoLjAwMDEsQUMuY3VycmVudFRpbWUrZCk7by5jb25uZWN0KGcpO2cuY29ubmVj"
    "dChBQy5kZXN0aW5hdGlvbik7by5zdGFydCgpO28uc3RvcChBQy5jdXJyZW50VGltZStkKX1jYXRjaChlKXt9fQpmdW5jdGlvbiBi"
    "b29tKGJpZyl7aWYobXV0ZWQpcmV0dXJuO3RyeXtBQz1BQ3x8bmV3KHdpbmRvdy5BdWRpb0NvbnRleHR8fHdpbmRvdy53ZWJraXRB"
    "dWRpb0NvbnRleHQpKCk7dmFyIGxlbj1iaWc/Ljc6LjI1LGI9QUMuY3JlYXRlQnVmZmVyKDEsQUMuc2FtcGxlUmF0ZSpsZW4sQUMu"
    "c2FtcGxlUmF0ZSksZD1iLmdldENoYW5uZWxEYXRhKDApOwogZm9yKHZhciBpPTA7aTxkLmxlbmd0aDtpKyspZFtpXT0oTWF0aC5y"
    "YW5kb20oKSoyLTEpKk1hdGgucG93KDEtaS9kLmxlbmd0aCwyKTt2YXIgcz1BQy5jcmVhdGVCdWZmZXJTb3VyY2UoKSxnPUFDLmNy"
    "ZWF0ZUdhaW4oKTtzLmJ1ZmZlcj1iO2cuZ2Fpbi52YWx1ZT1iaWc/LjM1Oi4xMjtzLmNvbm5lY3QoZyk7Zy5jb25uZWN0KEFDLmRl"
    "c3RpbmF0aW9uKTtzLnN0YXJ0KCl9Y2F0Y2goZSl7fX0KJCgibXV0ZSIpLm9uY2xpY2s9ZnVuY3Rpb24oKXttdXRlZD0hbXV0ZWQ7"
    "dGhpcy50ZXh0Q29udGVudD1tdXRlZD8i8J+UhyI6IvCflIoifTsKCmZ1bmN0aW9uIHJlc2l6ZSgpe2Rwcj1NYXRoLm1pbih3aW5k"
    "b3cuZGV2aWNlUGl4ZWxSYXRpb3x8MSwyKTtXPWlubmVyV2lkdGg7SD1pbm5lckhlaWdodDtDWD1XLzI7Q1k9SCouNDQ7Y3Yud2lk"
    "dGg9TWF0aC5yb3VuZChXKmRwcik7Y3YuaGVpZ2h0PU1hdGgucm91bmQoSCpkcHIpO2N0eC5zZXRUcmFuc2Zvcm0oZHByLDAsMCxk"
    "cHIsMCwwKTtGPU1hdGgubWF4KDM4MCxNYXRoLm1pbihXLEgpKjEuMTUpfQphZGRFdmVudExpc3RlbmVyKCJyZXNpemUiLHJlc2l6"
    "ZSk7YWRkRXZlbnRMaXN0ZW5lcigib3JpZW50YXRpb25jaGFuZ2UiLGZ1bmN0aW9uKCl7c2V0VGltZW91dChyZXNpemUsMjAwKX0p"
    "OwpmdW5jdGlvbiBwcm9qKHgseSx6KXt2YXIgcz1GL3o7cmV0dXJue3g6Q1grKHgtc2hpcC54Ki40NSkqcyx5OkNZKyh5LXNoaXAu"
    "eSouNDUpKnMsczpzfX0KCmZ1bmN0aW9uIGZpZWxkSW5pdCgpe3N0YXJzPVtdO2R1c3Q9W107cm9ja3M9W107CiBmb3IodmFyIGk9"
    "MDtpPDIyMDtpKyspc3RhcnMucHVzaCh7eDpybmQoLTI2MDAsMjYwMCkseTpybmQoLTE4MDAsMTgwMCksejpybmQoNjAsMzYwMCks"
    "YjpybmQoLjM1LDEpLGM6TWF0aC5yYW5kb20oKTwuMTU/cGljayhbIiNmZmQ5YTAiLCIjYTBjOGZmIiwiI2ZmYjBjOCJdKToiI2Rm"
    "ZThmZiJ9KTsKIGZvcihpPTA7aTw4MDtpKyspZHVzdC5wdXNoKHt4OnJuZCgtMTQwMCwxNDAwKSx5OnJuZCgtOTAwLDkwMCksejpy"
    "bmQoNjAsMjQwMCl9KTsKIGlmKGNmZy5wbGFuZXQ9PT0ic2F0dXJuInx8Y2ZnLnBsYW5ldD09PSJtb29uIilmb3IoaT0wO2k8Mjg7"
    "aSsrKXJvY2tzLnB1c2goe3g6cm5kKC0xNjAwLDE2MDApLHk6cm5kKC03MDAsNzAwKSx6OnJuZCg0MDAsMzQwMCkscjpybmQoNiwy"
    "Niksc3A6cm5kKC41LDEuMil9KX0KCmZ1bmN0aW9uIGJ1aWxkKG4pe2xldmVsPW47Y2ZnPVNFQ1RPUlNbbi0xXTtmb2VzPVtdO2Jv"
    "bHRzPVtdO2ZsYWs9W107cG9wcz1bXTtyaW5ncz1bXTtkcm9wcz1bXTtmbG9hdHM9W107Ym9zcz1udWxsOwogc3Bhd25lZD0wO3Nw"
    "YXduVD0uODtzaG90VD0wO3NoYWtlPTA7d2FycD0xLjI7c2hpcC54PXNoaXAueT1zaGlwLnR4PXNoaXAudHk9c2hpcC5yb2xsPTA7"
    "c2hpcC5pbnY9MS40O2ZpZWxkSW5pdCgpOwogaWYoY2ZnLmJvc3Mpe3ZhciBocD0xNDArY2ZnLmJvc3MqOTA7Ym9zcz17aHA6aHAs"
    "bWF4OmhwLHg6MCx5Oi00MCx6OjE1MDAsdDowLHBoOjAscjoxNzArY2ZnLmJvc3MqMjAsdGllcjpjZmcuYm9zcyxuYW1lOlsiIiwi"
    "R0FURSBPUkNIRVNUUkFUT1IiLCJSRUxBWSBPUkNIRVNUUkFUT1IiLCJDT1JFIE9SQ0hFU1RSQVRPUiJdW2NmZy5ib3NzXX19fQoK"
    "ZnVuY3Rpb24gc3Bhd25Gb2UodCx4LHkseil7dD10fHxwaWNrKGNmZy5taXgpO3ZhciBkPVRZUEVbdF07CiBmb2VzLnB1c2goe3Q6"
    "dCxocDpkLmhwKyhsZXZlbD45JiZ0PT09Imh1bGsiPzI6MCkscjpkLnIsY29sOmQuY29sLHg6eD09bnVsbD9ybmQoLTQ2MCw0NjAp"
    "OngseTp5PT1udWxsP3JuZCgtMzIwLDMwMCk6eSx6Onp8fHJuZCgyNDAwLDMwMDApLHBoOnJuZCgwLDYuMyksZmlyZTpybmQoLjgs"
    "Mi42KSxkZWFkOmZhbHNlLGhpdDowfSk7aWYoeD09bnVsbClzcGF3bmVkKyt9Cgp2YXIgZmxhc2hFbD0kKCJmbGFzaCIpLGZhY3RF"
    "bD0kKCJmYWN0IiksZmxhc2hUPTA7CmZ1bmN0aW9uIHNheSh0LGMsZmFjdCl7Zmxhc2hFbC50ZXh0Q29udGVudD10O2ZsYXNoRWwu"
    "c3R5bGUuY29sb3I9Y3x8IiNjOWE4NGMiO2ZsYXNoRWwuc3R5bGUub3BhY2l0eT0iMSI7ZmFjdEVsLnRleHRDb250ZW50PWZhY3R8"
    "fCIiO2ZhY3RFbC5zdHlsZS5vcGFjaXR5PWZhY3Q/IjEiOiIwIjtmbGFzaFQ9ZmFjdD8yLjY6MS4yfQpmdW5jdGlvbiBwb3AoeCx5"
    "LHosY29sLG4sc3Ape3NwPXNwfHwxNjA7Zm9yKHZhciBpPTA7aTxuO2krKylwb3BzLnB1c2goe3g6eCx5Onksejp6LHZ4OnJuZCgt"
    "c3Asc3ApLHZ5OnJuZCgtc3Asc3ApLHZ6OnJuZCgtOTAsMTQwKSxsaWZlOjEsY29sOmNvbH0pfQpmdW5jdGlvbiByaW5nKHgseSx6"
    "LGNvbCl7cmluZ3MucHVzaCh7eDp4LHk6eSx6Onoscjo1LGxpZmU6MSxjb2w6Y29sfSl9CmZ1bmN0aW9uIGZsb2F0ZXIoeCx5LHos"
    "dCxjb2wpe2Zsb2F0cy5wdXNoKHt4OngseTp5LHo6eix0OnQsY29sOmNvbCxsaWZlOjF9KX0KCmZ1bmN0aW9uIHN0ZXAodCl7aWYo"
    "IXJ1bm5pbmcpcmV0dXJuO3ZhciBkdD1NYXRoLm1pbigodC1sYXN0KS8xMDAwLC4wNSk7bGFzdD10O2lmKCFwYXVzZWQpdXBkYXRl"
    "KGR0KTtyZW5kZXIoKTtyZXF1ZXN0QW5pbWF0aW9uRnJhbWUoc3RlcCl9CgpmdW5jdGlvbiB1cGRhdGUoZHQpewogdmFyIHNwPWNm"
    "Zy5zcGVlZCood2FycD4wPzIuODoxKSxpLG87CiBpZih3YXJwPjApd2FycC09ZHQ7aWYoc2hha2U+MClzaGFrZS09ZHQqMztpZihz"
    "aGlwLmludj4wKXNoaXAuaW52LT1kdDtpZihmbGFzaFNjcj4wKWZsYXNoU2NyLT1kdCoyOwogaWYoc3ByZWFkPjApc3ByZWFkLT1k"
    "dDsKIGlmKGZsYXNoVD4wKXtmbGFzaFQtPWR0O2lmKGZsYXNoVDw9MCl7Zmxhc2hFbC5zdHlsZS5vcGFjaXR5PSIwIjtmYWN0RWwu"
    "c3R5bGUub3BhY2l0eT0iMCJ9fQogc2hpcC54Kz0oc2hpcC50eC1zaGlwLngpKk1hdGgubWluKDEsZHQqOSk7c2hpcC55Kz0oc2hp"
    "cC50eS1zaGlwLnkpKk1hdGgubWluKDEsZHQqOSk7CiBzaGlwLnJvbGwrPShjbGFtcCgoc2hpcC50eC1zaGlwLngpKi4wMDQsLS40"
    "NSwuNDUpLXNoaXAucm9sbCkqTWF0aC5taW4oMSxkdCo2KTsKIGZvcihpPTA7aTxzdGFycy5sZW5ndGg7aSsrKXtvPXN0YXJzW2ld"
    "O28uei09c3AqLjkqZHQ7aWYoby56PDQwKXtvLno9MzYwMDtvLng9cm5kKC0yNjAwLDI2MDApO28ueT1ybmQoLTE4MDAsMTgwMCl9"
    "fQogZm9yKGk9MDtpPGR1c3QubGVuZ3RoO2krKyl7bz1kdXN0W2ldO28uei09c3AqMS42KmR0O2lmKG8uejw0MCl7by56PTI0MDA7"
    "by54PXJuZCgtMTQwMCwxNDAwKTtvLnk9cm5kKC05MDAsOTAwKX19CiBmb3IoaT0wO2k8cm9ja3MubGVuZ3RoO2krKyl7bz1yb2Nr"
    "c1tpXTtvLnotPXNwKm8uc3AqZHQ7aWYoby56PDQwKXtvLno9MzQwMDtvLng9cm5kKC0xNjAwLDE2MDApO28ueT1ybmQoLTcwMCw3"
    "MDApfX0KIGlmKHNwYXduZWQ8Y2ZnLmNvdW50KXtzcGF3blQtPWR0O2lmKHNwYXduVDw9MCl7c3Bhd25Gb2UoKTtzcGF3blQ9cm5k"
    "KC4zLC44OCkqKDEtTWF0aC5taW4oLjQ1LGxldmVsKi4wMjgpKX19CiBzaG90VC09ZHQ7CiBpZihzaG90VDw9MCYmd2FycDw9MCl7"
    "dmFyIHN5PXNoaXAueSs4O2JvbHRzLnB1c2goe3g6c2hpcC54LTMwLHk6c3ksejo3MCx2eDowfSk7Ym9sdHMucHVzaCh7eDpzaGlw"
    "LngrMzAseTpzeSx6OjcwLHZ4OjB9KTsKICBpZihzcHJlYWQ+MCl7Ym9sdHMucHVzaCh7eDpzaGlwLngtNDAseTpzeSx6OjcwLHZ4"
    "Oi0yNjB9KTtib2x0cy5wdXNoKHt4OnNoaXAueCs0MCx5OnN5LHo6NzAsdng6MjYwfSl9c2hvdFQ9LjE0fQogZm9yKGk9Zm9lcy5s"
    "ZW5ndGgtMTtpPj0wO2ktLSl7dmFyIGY9Zm9lc1tpXTtpZihmLmRlYWQpe2ZvZXMuc3BsaWNlKGksMSk7Y29udGludWV9dmFyIGQ9"
    "VFlQRVtmLnRdOwogIGYuei09c3AqZC5zcGQqZHQ7Zi5waCs9ZHQqMS43O2lmKGYuaGl0PjApZi5oaXQtPWR0KjY7CiAgaWYoZC5z"
    "d2F5KXtmLngrPU1hdGguc2luKGYucGgpKmQuc3dheSo0NipkdDtmLnkrPU1hdGguY29zKGYucGgqLjcpKmQuc3dheSoyNipkdH0K"
    "ICBpZihmLnQ9PT0ibWluZSIpe2YueCs9KHNoaXAueC1mLngpKi4zKmR0O2YueSs9KHNoaXAueS1mLnkpKi4zKmR0fQogIGlmKGQu"
    "c2hvb3Q+MCYmZi56PDIxMDApe2YuZmlyZS09ZHQqZC5zaG9vdCpjZmcuZmlyZTtpZihmLmZpcmU8PTApe2YuZmlyZT1ybmQoMS4x"
    "LDIuNik7Zmxhay5wdXNoKHt4OmYueCx5OmYueSx6OmYueix2eDooc2hpcC54LWYueCkqLjMsdnk6KHNoaXAueS1mLnkpKi4zfSl9"
    "fQogIGlmKGYuejw1Mil7dmFyIG5lYXI9TWF0aC5hYnMoZi54LXNoaXAueCk8Zi5yKzM0JiZNYXRoLmFicyhmLnktc2hpcC55KTxm"
    "LnIrMzA7aWYobmVhcilkYW1hZ2UoZi50PT09Im1pbmUiPzIyOjE1KTtlbHNle3N0cmVhaz0wO211bHQ9MX1wb3AoZi54LGYueSw5"
    "MCxmLmNvbCxuZWFyPzE4OjUpO2YuZGVhZD10cnVlfX0KIGlmKGJvc3Mpe2Jvc3MudCs9ZHQ7Ym9zcy56PTUyMCtNYXRoLnNpbihi"
    "b3NzLnQqLjQpKjE4MDtib3NzLng9TWF0aC5zaW4oYm9zcy50Ki41NSkqMzAwO2Jvc3MueT0tNDArTWF0aC5jb3MoYm9zcy50Ki44"
    "KSo3MDtib3NzLnBoLT1kdDsKICBpZihib3NzLnBoPD0wKXtib3NzLnBoPXJuZCguMzUsLjgpLygxK2Jvc3MudGllciouMjUpO3Zh"
    "ciBmYW49MStib3NzLnRpZXI7Zm9yKHZhciBrPS1mYW47azw9ZmFuO2srKylmbGFrLnB1c2goe3g6Ym9zcy54K2sqMzQseTpib3Nz"
    "LnkrNDAsejpib3NzLnosdng6KHNoaXAueC1ib3NzLngpKi4zK2sqMjgsdnk6KHNoaXAueS1ib3NzLnkpKi4zfSl9CiAgaWYoYm9z"
    "cy50aWVyPj0yJiZNYXRoLnJhbmRvbSgpPGR0Ki42KXNwYXduRm9lKHBpY2soWyJkYXJ0ZXIiLCJzY291dCJdKSxib3NzLngsYm9z"
    "cy55LGJvc3Mueil9CiBmb3IoaT1ib2x0cy5sZW5ndGgtMTtpPj0wO2ktLSl7dmFyIGI9Ym9sdHNbaV07Yi56Kz0xOTAwKmR0O2Iu"
    "eCs9Yi52eCpkdDtpZihiLno+MzIwMCl7Ym9sdHMuc3BsaWNlKGksMSk7Y29udGludWV9dmFyIGhpdD1mYWxzZTsKICBmb3IodmFy"
    "IGo9MDtqPGZvZXMubGVuZ3RoO2orKyl7dmFyIGc9Zm9lc1tqXTtpZihnLmRlYWQpY29udGludWU7CiAgIGlmKE1hdGguYWJzKGIu"
    "ei1nLnopPDcwJiZNYXRoLmFicyhiLngtZy54KTxnLnIrMTYmJk1hdGguYWJzKGIueS1nLnkpPGcucisxNil7Zy5ocC0tO2cuaGl0"
    "PTE7cG9wKGcueCxnLnksZy56LGcuY29sLDQpO2lmKGcuaHA8PTApa2lsbEZvZShnKTtoaXQ9dHJ1ZTticmVha319CiAgaWYoaGl0"
    "KXtib2x0cy5zcGxpY2UoaSwxKTtjb250aW51ZX0KICBpZihib3NzJiZNYXRoLmFicyhiLnotYm9zcy56KTwxMTAmJk1hdGguYWJz"
    "KGIueC1ib3NzLngpPGJvc3MuciYmTWF0aC5hYnMoYi55LWJvc3MueSk8Ym9zcy5yKi41NSl7Ym9zcy5ocC0tO2Jvc3MuaGl0PTE7"
    "c2NvcmUrPTYqbXVsdDtwb3AoYi54LGIueSxiLnosIiNmZjhhODAiLDMpO2JvbHRzLnNwbGljZShpLDEpOwogICBpZihib3NzLmhw"
    "PD0wKXtzY29yZSs9NDAwMCpib3NzLnRpZXI7a2lsbHMrKztjaGFpbk4rKztmb3IodmFyIHE9MDtxPDQ7cSsrKXJpbmcoYm9zcy54"
    "K3JuZCgtODAsODApLGJvc3MueStybmQoLTQwLDQwKSxib3NzLnosIiNmZjhhODAiKTtwb3AoYm9zcy54LGJvc3MueSxib3NzLnos"
    "IiNmZjhhODAiLDE0MCwyNjApO3BvcChib3NzLngsYm9zcy55LGJvc3MueiwiI2M5YTg0YyIsODAsMjAwKTsKICAgIHNoYWtlPTEu"
    "NjtmbGFzaFNjcj0xO2Jvb20odHJ1ZSk7c2F5KGJvc3MubmFtZSsiIFNFQUxFRCIsIiNjOWE4NGMiKTtib3NzPW51bGx9fX0KIGZv"
    "cihpPWZsYWsubGVuZ3RoLTE7aT49MDtpLS0pe3ZhciBmbD1mbGFrW2ldO2ZsLnotPShzcCouOSs1MjApKmR0O2ZsLngrPWZsLnZ4"
    "KmR0O2ZsLnkrPWZsLnZ5KmR0OwogIGlmKG9yYnM+MCYmZmwuejwxNjAmJk1hdGguYWJzKGZsLngtc2hpcC54KTw5MCYmTWF0aC5h"
    "YnMoZmwueS1zaGlwLnkpPDgwKXtvcmJzLS07cG9wKGZsLngsZmwueSxmbC56LCIjOGZkMGZmIiwxMCk7dG9uZSg5MDAsLjA4LCJz"
    "aW5lIiwuMDUpO2ZsYWsuc3BsaWNlKGksMSk7Y29udGludWV9CiAgaWYoZmwuejw0NCl7aWYoTWF0aC5hYnMoZmwueC1zaGlwLngp"
    "PDM4JiZNYXRoLmFicyhmbC55LXNoaXAueSk8MzIpZGFtYWdlKDkpO2ZsYWsuc3BsaWNlKGksMSl9fQogZm9yKGk9ZHJvcHMubGVu"
    "Z3RoLTE7aT49MDtpLS0pe3ZhciBkcD1kcm9wc1tpXTtkcC56LT1zcCouOCpkdDtkcC5waCs9ZHQqMzsKICBpZihkcC56PDcwKXtp"
    "ZihNYXRoLmFicyhkcC54LXNoaXAueCk8NzAmJk1hdGguYWJzKGRwLnktc2hpcC55KTw2MClncmFiKGRwLmspO2Ryb3BzLnNwbGlj"
    "ZShpLDEpfX0KIGZvcihpPXBvcHMubGVuZ3RoLTE7aT49MDtpLS0pe3ZhciBwPXBvcHNbaV07cC54Kz1wLnZ4KmR0O3AueSs9cC52"
    "eSpkdDtwLnorPXAudnoqZHQtc3AqZHQ7cC5saWZlLT1kdCoxLjI7aWYocC5saWZlPD0wfHxwLno8MjApcG9wcy5zcGxpY2UoaSwx"
    "KX0KIGZvcihpPXJpbmdzLmxlbmd0aC0xO2k+PTA7aS0tKXt2YXIgcmc9cmluZ3NbaV07cmcucis9ZHQqMjYwO3JnLmxpZmUtPWR0"
    "KjEuNjtyZy56LT1zcCouNSpkdDtpZihyZy5saWZlPD0wfHxyZy56PDMwKXJpbmdzLnNwbGljZShpLDEpfQogZm9yKGk9ZmxvYXRz"
    "Lmxlbmd0aC0xO2k+PTA7aS0tKXt2YXIgZm89ZmxvYXRzW2ldO2ZvLnktPWR0KjYwO2ZvLmxpZmUtPWR0KjEuMTtmby56LT1zcCou"
    "MypkdDtpZihmby5saWZlPD0wfHxmby56PDQwKWZsb2F0cy5zcGxpY2UoaSwxKX0KIGh1ZCgpOwogaWYoc3Bhd25lZD49Y2ZnLmNv"
    "dW50JiZmb2VzLmxlbmd0aD09PTAmJiFib3NzJiZmbGFzaFQ8PTApY2xlYXIoKX0KCmZ1bmN0aW9uIGtpbGxGb2UoZyl7Zy5kZWFk"
    "PXRydWU7a2lsbHMrKztjaGFpbk4rKztzdHJlYWsrKzttdWx0PU1hdGgubWluKDgsMStNYXRoLmZsb29yKHN0cmVhay82KSk7CiB2"
    "YXIgcHRzPU1hdGgucm91bmQoVFlQRVtnLnRdLnB0cyptdWx0KigxK01hdGgubWluKDEuMixnLnovMjIwMCkpKTtzY29yZSs9cHRz"
    "OwogcG9wKGcueCxnLnksZy56LGcuY29sLDIyKTtyaW5nKGcueCxnLnksZy56LGcuY29sKTtmbG9hdGVyKGcueCxnLnktZy5yLGcu"
    "eiwiKyIrcHRzLGcuY29sKTtib29tKGZhbHNlKTsKIGlmKGcudD09PSJzcGxpdCIpZm9yKHZhciBrPS0xO2s8PTE7ays9MilzcGF3"
    "bkZvZSgic2NvdXQiLGcueCtrKjUwLGcueSxnLnorNDApOwogaWYoTWF0aC5yYW5kb20oKTwuMDg1KyhodWxsPDQwPy4wNTowKSlk"
    "cm9wcy5wdXNoKHt4OmcueCx5OmcueSx6OmcueixwaDowLGs6aHVsbDw0NSYmTWF0aC5yYW5kb20oKTwuNT8iUiI6cGljayhbIlAi"
    "LCJXIiwiQSIsIlAiLCJXIl0pfSk7CiBpZihzdHJlYWs+MCYmc3RyZWFrJTEyPT09MCl7c2F5KCJDSEFJTiB4IitzdHJlYWsrIiDC"
    "tyBCTE9DSyAjIitjaGFpbk4rIiBTRUFMRUQiLCIjN2ZlM2IwIik7dG9uZSg2NjAsLjEyLCJ0cmlhbmdsZSIsLjA2LDEzMjApfX0K"
    "CmZ1bmN0aW9uIGdyYWIoayl7dG9uZSg1MjAsLjE4LCJ0cmlhbmdsZSIsLjA3LDEwNDApO3ZhciBwPVBXUltrXTsKIGlmKGs9PT0i"
    "UCIpe3NwcmVhZD05O3NheSgiUEFTU1BPUlQgwrcgU1BSRUFEIFNIT1QiLHAuY29sKX0KIGVsc2UgaWYoaz09PSJXIil7b3Jicz1N"
    "YXRoLm1pbig2LG9yYnMrMyk7c2F5KCJXSVRORVNTRVMgwrcgU0hJRUxEIFVQIixwLmNvbCl9CiBlbHNlIGlmKGs9PT0iQSIpe3Nh"
    "eSgiQU5DSE9SRUQgVE8gQklUQ09JTiIscC5jb2wpO2ZsYXNoU2NyPTE7c2hha2U9MTtib29tKHRydWUpO2ZsYWs9W107CiAgZm9l"
    "cy5mb3JFYWNoKGZ1bmN0aW9uKGYpe2lmKGYuejwyNjAwKXtmLmhwLT0zO2lmKGYuaHA8PTApa2lsbEZvZShmKX19KTtpZihib3Nz"
    "KXtib3NzLmhwLT0yMH19CiBlbHNle2h1bGw9TWF0aC5taW4oMTAwLGh1bGwrMzApOyQoImh1bGxGIikuc3R5bGUud2lkdGg9aHVs"
    "bCsiJSI7c2F5KCJSRVBBSVJFRCIscC5jb2wpfX0KCmZ1bmN0aW9uIGRhbWFnZShuKXtpZihzaGlwLmludj4wKXJldHVybjtpZihv"
    "cmJzPjApe29yYnMtLTtzaGlwLmludj0uNDt0b25lKDkwMCwuMDgsInNpbmUiLC4wNSk7cmV0dXJufQogaHVsbC09bjtzdHJlYWs9"
    "MDttdWx0PTE7c2hha2U9MTtzaGlwLmludj0uNzt0b25lKDEyMCwuMjUsInNhd3Rvb3RoIiwuMDgsNTApOyQoImh1bGxGIikuc3R5"
    "bGUud2lkdGg9TWF0aC5tYXgoMCxodWxsKSsiJSI7aWYoaHVsbDw9MClvdmVyKGZhbHNlKX0KCi8qIC0tLS0tLS0tLS0gcmVuZGVy"
    "IC0tLS0tLS0tLS0gKi8KZnVuY3Rpb24gcmVuZGVyKCl7Y3R4LnNhdmUoKTtpZihzaGFrZT4wKWN0eC50cmFuc2xhdGUocm5kKC02"
    "LDYpKnNoYWtlLHJuZCgtNiw2KSpzaGFrZSk7CiBjdHguZmlsbFN0eWxlPWNmZy5za3k7Y3R4LmZpbGxSZWN0KC0xMCwtMTAsVysy"
    "MCxIKzIwKTtkcmF3QmFja2Ryb3AoKTsKIGZvcih2YXIgaT0wO2k8c3RhcnMubGVuZ3RoO2krKyl7dmFyIHM9c3RhcnNbaV0scD1w"
    "cm9qKHMueCxzLnkscy56KTtpZihwLng8LTQwfHxwLng+Vys0MHx8cC55PC00MHx8cC55PkgrNDApY29udGludWU7CiAgdmFyIGE9"
    "TWF0aC5taW4oMSxzLmIqKDEtcy56LzM2MDApKy4xMiksc3o9TWF0aC5tYXgoLjYscC5zKjEuNyk7Y3R4Lmdsb2JhbEFscGhhPWE7"
    "Y3R4LmZpbGxTdHlsZT1zLmM7CiAgaWYod2FycD4wKWN0eC5maWxsUmVjdChwLngscC55LHN6LHN6K3dhcnAqMjgqcC5zKjEwKTtl"
    "bHNlIGN0eC5maWxsUmVjdChwLngscC55LHN6LHN6KX0KIGN0eC5nbG9iYWxBbHBoYT0xO2N0eC5zdHJva2VTdHlsZT0icmdiYSgx"
    "ODAsMjA1LDI1NSwuMykiO2N0eC5saW5lV2lkdGg9MTsKIGZvcihpPTA7aTxkdXN0Lmxlbmd0aDtpKyspe3ZhciBkPWR1c3RbaV0s"
    "YTE9cHJvaihkLngsZC55LGQueiksYTI9cHJvaihkLngsZC55LGQueisxMzApO2lmKGExLng8LTMwfHxhMS54PlcrMzApY29udGlu"
    "dWU7Y3R4LmJlZ2luUGF0aCgpO2N0eC5tb3ZlVG8oYTEueCxhMS55KTtjdHgubGluZVRvKGEyLngsYTIueSk7Y3R4LnN0cm9rZSgp"
    "fQogZm9yKGk9MDtpPHJvY2tzLmxlbmd0aDtpKyspe3ZhciByPXJvY2tzW2ldLHJwPXByb2ooci54LHIueSxyLnopLHJyPXIucipy"
    "cC5zO2lmKHJyPC40fHxycC54PC02MHx8cnAueD5XKzYwKWNvbnRpbnVlO2N0eC5nbG9iYWxBbHBoYT1NYXRoLm1pbigxLDEuNC1y"
    "LnovMzQwMCk7CiAgY3R4LmZpbGxTdHlsZT0iIzNiM2Y0ZCI7Y3R4LmJlZ2luUGF0aCgpO2N0eC5hcmMocnAueCxycC55LHJyLDAs"
    "Ni4yODQpO2N0eC5maWxsKCk7Y3R4LmZpbGxTdHlsZT0iIzRiNTA2MCI7Y3R4LmJlZ2luUGF0aCgpO2N0eC5hcmMocnAueC1yciou"
    "MyxycC55LXJyKi4zLHJyKi41NSwwLDYuMjg0KTtjdHguZmlsbCgpfQogY3R4Lmdsb2JhbEFscGhhPTE7CiB2YXIgbGlzdD1bXTtm"
    "b2VzLmZvckVhY2goZnVuY3Rpb24obyl7bGlzdC5wdXNoKHtrOiJmIixvOm8sejpvLnp9KX0pO2lmKGJvc3MpbGlzdC5wdXNoKHtr"
    "OiJCIixvOmJvc3Msejpib3NzLnp9KTsKIGRyb3BzLmZvckVhY2goZnVuY3Rpb24obyl7bGlzdC5wdXNoKHtrOiJkIixvOm8sejpv"
    "Lnp9KX0pO2ZsYWsuZm9yRWFjaChmdW5jdGlvbihvKXtsaXN0LnB1c2goe2s6IngiLG86byx6Om8uen0pfSk7CiBib2x0cy5mb3JF"
    "YWNoKGZ1bmN0aW9uKG8pe2xpc3QucHVzaCh7azoiYiIsbzpvLHo6by56fSl9KTtsaXN0LnNvcnQoZnVuY3Rpb24oYSxiKXtyZXR1"
    "cm4gYi56LWEuen0pOwogZm9yKGk9MDtpPGxpc3QubGVuZ3RoO2krKyl7dmFyIGl0PWxpc3RbaV0sbz1pdC5vLHE9cHJvaihvLngs"
    "by55LG8ueik7aWYoby56PDMwKWNvbnRpbnVlOwogIGlmKGl0Lms9PT0iZiIpZHJhd0ZvZShvLHEpO2Vsc2UgaWYoaXQuaz09PSJC"
    "IilkcmF3Qm9zcyhvLHEpO2Vsc2UgaWYoaXQuaz09PSJkIilkcmF3RHJvcChvLHEpOwogIGVsc2UgaWYoaXQuaz09PSJ4Iil7dmFy"
    "IHhzPU1hdGgubWF4KDIsOSpxLnMpO2N0eC5nbG9iYWxDb21wb3NpdGVPcGVyYXRpb249ImxpZ2h0ZXIiO2N0eC5maWxsU3R5bGU9"
    "InJnYmEoMjU1LDkwLDgwLC4zNSkiO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKHEueCxxLnkseHMqMi40LDAsNi4yODQpO2N0eC5m"
    "aWxsKCk7CiAgIGN0eC5maWxsU3R5bGU9IiNmZmIwYTgiO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKHEueCxxLnkseHMsMCw2LjI4"
    "NCk7Y3R4LmZpbGwoKTtjdHguZ2xvYmFsQ29tcG9zaXRlT3BlcmF0aW9uPSJzb3VyY2Utb3ZlciJ9CiAgZWxzZXt2YXIgcTI9cHJv"
    "aihvLngtby52eCouMDgsby55LG8uei0xNjApO2N0eC5nbG9iYWxDb21wb3NpdGVPcGVyYXRpb249ImxpZ2h0ZXIiO2N0eC5zdHJv"
    "a2VTdHlsZT1zcHJlYWQ+MD8iI2I4ZmZlMCI6IiM5ZmYzYzgiO2N0eC5saW5lV2lkdGg9TWF0aC5tYXgoMS40LDMuNCpxLnMpO2N0"
    "eC5saW5lQ2FwPSJyb3VuZCI7CiAgIGN0eC5iZWdpblBhdGgoKTtjdHgubW92ZVRvKHEyLngscTIueSk7Y3R4LmxpbmVUbyhxLngs"
    "cS55KTtjdHguc3Ryb2tlKCk7Y3R4Lmdsb2JhbENvbXBvc2l0ZU9wZXJhdGlvbj0ic291cmNlLW92ZXIifX0KIGN0eC5nbG9iYWxD"
    "b21wb3NpdGVPcGVyYXRpb249ImxpZ2h0ZXIiOwogZm9yKGk9MDtpPHJpbmdzLmxlbmd0aDtpKyspe3ZhciByZz1yaW5nc1tpXSxy"
    "cT1wcm9qKHJnLngscmcueSxyZy56KTtjdHguZ2xvYmFsQWxwaGE9TWF0aC5tYXgoMCxyZy5saWZlKSouODtjdHguc3Ryb2tlU3R5"
    "bGU9cmcuY29sO2N0eC5saW5lV2lkdGg9TWF0aC5tYXgoMSwzKnJxLnMpO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKHJxLngscnEu"
    "eSxyZy5yKnJxLnMsMCw2LjI4NCk7Y3R4LnN0cm9rZSgpfQogZm9yKGk9MDtpPHBvcHMubGVuZ3RoO2krKyl7dmFyIHBwPXBvcHNb"
    "aV0scHE9cHJvaihwcC54LHBwLnkscHAueik7Y3R4Lmdsb2JhbEFscGhhPU1hdGgubWF4KDAscHAubGlmZSk7Y3R4LmZpbGxTdHls"
    "ZT1wcC5jb2w7dmFyIHBzPU1hdGgubWF4KDEuMiw0LjUqcHEucyk7Y3R4LmZpbGxSZWN0KHBxLngscHEueSxwcyxwcyl9CiBjdHgu"
    "Z2xvYmFsQ29tcG9zaXRlT3BlcmF0aW9uPSJzb3VyY2Utb3ZlciI7Y3R4Lmdsb2JhbEFscGhhPTE7CiBjdHgudGV4dEFsaWduPSJj"
    "ZW50ZXIiOwogZm9yKGk9MDtpPGZsb2F0cy5sZW5ndGg7aSsrKXt2YXIgZm89ZmxvYXRzW2ldLGZxPXByb2ooZm8ueCxmby55LGZv"
    "LnopO2N0eC5nbG9iYWxBbHBoYT1NYXRoLm1heCgwLGZvLmxpZmUpO2N0eC5maWxsU3R5bGU9Zm8uY29sO2N0eC5mb250PSI3MDAg"
    "IitNYXRoLm1heCgxMCxNYXRoLm1pbigyMiwyNipmcS5zKSkrInB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2UiO2N0eC5maWxsVGV4"
    "dChmby50LGZxLngsZnEueSl9CiBjdHguZ2xvYmFsQWxwaGE9MTtkcmF3U2hpcCgpOwogaWYoZmxhc2hTY3I+MCl7Y3R4LmZpbGxT"
    "dHlsZT0icmdiYSgyNTUsMjQwLDIwMCwiKyhmbGFzaFNjciouMzUpKyIpIjtjdHguZmlsbFJlY3QoLTEwLC0xMCxXKzIwLEgrMjAp"
    "fQogdmFyIHZnPWN0eC5jcmVhdGVSYWRpYWxHcmFkaWVudChDWCxILzIsTWF0aC5taW4oVyxIKSouMzUsQ1gsSC8yLE1hdGgubWF4"
    "KFcsSCkqLjc1KTt2Zy5hZGRDb2xvclN0b3AoMCwicmdiYSgwLDAsMCwwKSIpO3ZnLmFkZENvbG9yU3RvcCgxLCJyZ2JhKDAsMCww"
    "LC41NSkiKTtjdHguZmlsbFN0eWxlPXZnO2N0eC5maWxsUmVjdCgtMTAsLTEwLFcrMjAsSCsyMCk7CiBjdHgucmVzdG9yZSgpfQoK"
    "ZnVuY3Rpb24gZHJhd0JhY2tkcm9wKCl7dmFyIHQ9cGVyZm9ybWFuY2Uubm93KCkvMTAwMCxweD1DWC1zaGlwLngqLjE0LHB5PUNZ"
    "LXNoaXAueSouMSxrPWNmZy5wbGFuZXQ7CiBpZihrPT09InZvaWQifHxrPT09Im5lYnVsYSIpe3ZhciBuZWI9Y3R4LmNyZWF0ZVJh"
    "ZGlhbEdyYWRpZW50KHB4K1cqLjIscHktSCouMSwxMCxweCtXKi4yLHB5LUgqLjEsVyouOCk7bmViLmFkZENvbG9yU3RvcCgwLGs9"
    "PT0ibmVidWxhIj8icmdiYSgxNTAsNjAsMjAwLC4zNSkiOiJyZ2JhKDYwLDQwLDkwLC4zKSIpO25lYi5hZGRDb2xvclN0b3AoLjUs"
    "az09PSJuZWJ1bGEiPyJyZ2JhKDQwLDkwLDIwMCwuMTgpIjoicmdiYSgyMCwyMCw0MCwuMSkiKTtuZWIuYWRkQ29sb3JTdG9wKDEs"
    "InJnYmEoNSw3LDE1LDApIik7Y3R4LmZpbGxTdHlsZT1uZWI7Y3R4LmZpbGxSZWN0KDAsMCxXLEgpO3JldHVybn0KIHZhciBSPU1h"
    "dGgubWluKFcsSCkqKGs9PT0ic2F0dXJuIj8uNDI6LjM0KSxjeD1weCtXKi4yNCxjeT1weS1IKi4xNjsKIHZhciBib2R5PXtzYXR1"
    "cm46WyIjZTZkM2EzIiwiIzljODM1MiJdLHJ1c3Q6WyIjYzk3YjRhIiwiIzVkMmYxYyJdLGljZTpbIiM5YWQ0ZmYiLCIjMmI1Yjg2"
    "Il0sbW9vbjpbIiNjOWNjZDYiLCIjNGE0ZTVjIl0samFkZTpbIiM4ZmUwYjQiLCIjMjc2MDRhIl0sZW1iZXI6WyIjZmY5YTdhIiwi"
    "IzZkMjIyMiJdfVtrXXx8WyIjYzljY2Q2IiwiIzRhNGU1YyJdOwogdmFyIGF0PWN0eC5jcmVhdGVSYWRpYWxHcmFkaWVudChjeCxj"
    "eSxSKi45LGN4LGN5LFIqMS4yNSk7YXQuYWRkQ29sb3JTdG9wKDAsInJnYmEoMjU1LDI1NSwyNTUsLjEyKSIpO2F0LmFkZENvbG9y"
    "U3RvcCgxLCJyZ2JhKDI1NSwyNTUsMjU1LDApIik7Y3R4LmZpbGxTdHlsZT1hdDtjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhjeCxj"
    "eSxSKjEuMjUsMCw2LjI4NCk7Y3R4LmZpbGwoKTsKIGlmKGs9PT0ic2F0dXJuIil7Y3R4LnNhdmUoKTtjdHgudHJhbnNsYXRlKGN4"
    "LGN5KTtjdHgucm90YXRlKC0uNDIpO2N0eC5zdHJva2VTdHlsZT0icmdiYSgyMTQsMTkzLDE1MCwuNTUpIjtjdHgubGluZVdpZHRo"
    "PVIqLjE2O2N0eC5iZWdpblBhdGgoKTtjdHguZWxsaXBzZSgwLDAsUioxLjc1LFIqLjQyLDAsTWF0aC5QSSxNYXRoLlBJKjIpO2N0"
    "eC5zdHJva2UoKTtjdHgucmVzdG9yZSgpfQogdmFyIGc9Y3R4LmNyZWF0ZVJhZGlhbEdyYWRpZW50KGN4LVIqLjM1LGN5LVIqLjM1"
    "LFIqLjEsY3gsY3ksUik7Zy5hZGRDb2xvclN0b3AoMCxib2R5WzBdKTtnLmFkZENvbG9yU3RvcCgxLGJvZHlbMV0pO2N0eC5maWxs"
    "U3R5bGU9ZztjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhjeCxjeSxSLDAsNi4yODQpO2N0eC5maWxsKCk7CiBpZihrPT09Im1vb24i"
    "KXtjdHguZmlsbFN0eWxlPSJyZ2JhKDAsMCwwLC4xNikiO2Zvcih2YXIgaT0wO2k8NztpKyspe3ZhciBhPWkqMS40KzEscnI9Uioo"
    "LjA4KygoaSozNyklMTEpLzYwKTtjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhjeCtNYXRoLmNvcyhhKSpSKi41LGN5K01hdGguc2lu"
    "KGEpKlIqLjQ1LHJyLDAsNi4yODQpO2N0eC5maWxsKCl9fQogaWYoaz09PSJzYXR1cm4ifHxrPT09ImphZGUifHxrPT09InJ1c3Qi"
    "KXtjdHguZ2xvYmFsQWxwaGE9LjE4O2N0eC5maWxsU3R5bGU9InJnYmEoMCwwLDAsLjYpIjtmb3IodmFyIGI9MDtiPDQ7YisrKXtj"
    "dHguYmVnaW5QYXRoKCk7Y3R4LmVsbGlwc2UoY3gsY3ktUiouNStiKlIqLjM0K01hdGguc2luKHQqLjIrYikqMyxSKi45MixSKi4w"
    "NzUsMCwwLDYuMjg0KTtjdHguZmlsbCgpfWN0eC5nbG9iYWxBbHBoYT0xfQogY3R4LmZpbGxTdHlsZT0icmdiYSg1LDcsMTUsLjU1"
    "KSI7Y3R4LmJlZ2luUGF0aCgpO2N0eC5hcmMoY3grUiouMyxjeStSKi4xMixSLDAsNi4yODQpO2N0eC5maWxsKCk7CiBpZihrPT09"
    "InNhdHVybiIpe2N0eC5zYXZlKCk7Y3R4LnRyYW5zbGF0ZShjeCxjeSk7Y3R4LnJvdGF0ZSgtLjQyKTtjdHguc3Ryb2tlU3R5bGU9"
    "InJnYmEoMjMyLDIxNCwxNzUsLjc1KSI7Y3R4LmxpbmVXaWR0aD1SKi4xNjtjdHguYmVnaW5QYXRoKCk7Y3R4LmVsbGlwc2UoMCww"
    "LFIqMS43NSxSKi40MiwwLDAsTWF0aC5QSSk7Y3R4LnN0cm9rZSgpO2N0eC5yZXN0b3JlKCl9fQoKZnVuY3Rpb24gZHJhd0ZvZShm"
    "LHApe3ZhciByPWYucipwLnM7aWYocjwuNilyZXR1cm47Y3R4Lmdsb2JhbEFscGhhPU1hdGgubWluKDEsKDMwMDAtZi56KS83MDAr"
    "LjI1KTsKIHZhciBjb2w9Zi5oaXQ+MD8iI2ZmZmZmZiI6Zi5jb2w7CiBjdHguZ2xvYmFsQ29tcG9zaXRlT3BlcmF0aW9uPSJsaWdo"
    "dGVyIjt2YXIgZ2w9Y3R4LmNyZWF0ZVJhZGlhbEdyYWRpZW50KHAueCxwLnksMCxwLngscC55LHIqMik7Z2wuYWRkQ29sb3JTdG9w"
    "KDAsZi5jb2wrIjU1Iik7Z2wuYWRkQ29sb3JTdG9wKDEsZi5jb2wrIjAwIik7Y3R4LmZpbGxTdHlsZT1nbDtjdHguYmVnaW5QYXRo"
    "KCk7Y3R4LmFyYyhwLngscC55LHIqMiwwLDYuMjg0KTtjdHguZmlsbCgpO2N0eC5nbG9iYWxDb21wb3NpdGVPcGVyYXRpb249InNv"
    "dXJjZS1vdmVyIjsKIGlmKGYudD09PSJtaW5lIil7Y3R4LnN0cm9rZVN0eWxlPWNvbDtjdHgubGluZVdpZHRoPU1hdGgubWF4KDEs"
    "ciouMTYpO2Zvcih2YXIgaT0wO2k8ODtpKyspe3ZhciBhPWkqLjc4NStmLnBoO2N0eC5iZWdpblBhdGgoKTtjdHgubW92ZVRvKHAu"
    "eCtNYXRoLmNvcyhhKSpyKi42LHAueStNYXRoLnNpbihhKSpyKi42KTtjdHgubGluZVRvKHAueCtNYXRoLmNvcyhhKSpyKjEuMjUs"
    "cC55K01hdGguc2luKGEpKnIqMS4yNSk7Y3R4LnN0cm9rZSgpfWN0eC5maWxsU3R5bGU9Y29sO2N0eC5iZWdpblBhdGgoKTtjdHgu"
    "YXJjKHAueCxwLnksciouNiwwLDYuMjg0KTtjdHguZmlsbCgpfQogZWxzZSBpZihmLnQ9PT0ic3BsaXQiKXtjdHguZmlsbFN0eWxl"
    "PWNvbDtjdHguYmVnaW5QYXRoKCk7Zm9yKHZhciBqPTA7ajw2O2orKyl7dmFyIGFuPWoqMS4wNDcrZi5waCouNTtjdHgubGluZVRv"
    "KHAueCtNYXRoLmNvcyhhbikqcixwLnkrTWF0aC5zaW4oYW4pKnIpfWN0eC5jbG9zZVBhdGgoKTtjdHguZmlsbCgpO2N0eC5zdHJv"
    "a2VTdHlsZT0icmdiYSg1LDcsMTUsLjcpIjtjdHgubGluZVdpZHRoPU1hdGgubWF4KDEsciouMTIpO2N0eC5iZWdpblBhdGgoKTtj"
    "dHgubW92ZVRvKHAueCxwLnktcik7Y3R4LmxpbmVUbyhwLngscC55K3IpO2N0eC5zdHJva2UoKX0KIGVsc2V7Y3R4LmZpbGxTdHls"
    "ZT1jb2w7Y3R4LmJlZ2luUGF0aCgpO2N0eC5tb3ZlVG8ocC54LHAueStyKi45KTtjdHgubGluZVRvKHAueCtyKjEuMTUscC55LXIq"
    "LjUpO2N0eC5saW5lVG8ocC54K3IqLjQscC55LXIqLjE1KTtjdHgubGluZVRvKHAueC1yKi40LHAueS1yKi4xNSk7Y3R4LmxpbmVU"
    "byhwLngtcioxLjE1LHAueS1yKi41KTtjdHguY2xvc2VQYXRoKCk7Y3R4LmZpbGwoKTsKICBjdHguZmlsbFN0eWxlPSJyZ2JhKDUs"
    "NywxNSwuNzUpIjtjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhwLngscC55K3IqLjA1LHIqLjMsMCw2LjI4NCk7Y3R4LmZpbGwoKTsK"
    "ICBpZihmLnQ9PT0iaHVsayIpe2N0eC5zdHJva2VTdHlsZT0icmdiYSg1LDcsMTUsLjYpIjtjdHgubGluZVdpZHRoPU1hdGgubWF4"
    "KDEsciouMTIpO2N0eC5iZWdpblBhdGgoKTtjdHgubW92ZVRvKHAueC1yLHAueS1yKi40Mik7Y3R4LmxpbmVUbyhwLngrcixwLnkt"
    "ciouNDIpO2N0eC5zdHJva2UoKX0KICBjdHguZmlsbFN0eWxlPSJyZ2JhKDI1NSwyNTUsMjU1LC43KSI7Y3R4LmZpbGxSZWN0KHAu"
    "eC1yKi4xMixwLnktciouNjIsciouMjQsciouMil9CiBpZihyPjE0KXtjdHguZm9udD0iNzAwICIrTWF0aC5taW4oMTIsciouMzUp"
    "KyJweCB1aS1tb25vc3BhY2UsbW9ub3NwYWNlIjtjdHgudGV4dEFsaWduPSJjZW50ZXIiO2N0eC5maWxsU3R5bGU9Zi5jb2w7Y3R4"
    "LmZpbGxUZXh0KFRZUEVbZi50XS5sYWIscC54LHAueS1yKjEuMzUpfQogY3R4Lmdsb2JhbEFscGhhPTF9CgpmdW5jdGlvbiBkcmF3"
    "RHJvcChkLHApe3ZhciByPU1hdGgubWF4KDQsMzAqcC5zKSxjPVBXUltkLmtdLmNvbDtjdHguc2F2ZSgpO2N0eC50cmFuc2xhdGUo"
    "cC54LHAueSk7Y3R4LnJvdGF0ZShkLnBoKTsKIGN0eC5nbG9iYWxDb21wb3NpdGVPcGVyYXRpb249ImxpZ2h0ZXIiO2N0eC5maWxs"
    "U3R5bGU9YysiNDQiO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKDAsMCxyKjEuOCwwLDYuMjg0KTtjdHguZmlsbCgpO2N0eC5nbG9i"
    "YWxDb21wb3NpdGVPcGVyYXRpb249InNvdXJjZS1vdmVyIjsKIGN0eC5maWxsU3R5bGU9YztjdHguYmVnaW5QYXRoKCk7Y3R4Lm1v"
    "dmVUbygwLC1yKTtjdHgubGluZVRvKHIsMCk7Y3R4LmxpbmVUbygwLHIpO2N0eC5saW5lVG8oLXIsMCk7Y3R4LmNsb3NlUGF0aCgp"
    "O2N0eC5maWxsKCk7Y3R4LnJvdGF0ZSgtZC5waCk7CiBjdHguZmlsbFN0eWxlPSIjMDUwNzBmIjtjdHguZm9udD0iOTAwICIrKHIq"
    "LjkpKyJweCBJbnRlcixBcmlhbCI7Y3R4LnRleHRBbGlnbj0iY2VudGVyIjtjdHgudGV4dEJhc2VsaW5lPSJtaWRkbGUiO2N0eC5m"
    "aWxsVGV4dChkLms9PT0iQSI/IuKCvyI6ZC5rLDAsMSk7Y3R4LnRleHRCYXNlbGluZT0iYWxwaGFiZXRpYyI7Y3R4LnJlc3RvcmUo"
    "KTsKIGlmKHI+MTIpe2N0eC5mb250PSI3MDAgMTBweCB1aS1tb25vc3BhY2UsbW9ub3NwYWNlIjtjdHguZmlsbFN0eWxlPWM7Y3R4"
    "LnRleHRBbGlnbj0iY2VudGVyIjtjdHguZmlsbFRleHQoUFdSW2Qua10ubGFiLHAueCxwLnkrcioxLjkpfX0KCmZ1bmN0aW9uIGRy"
    "YXdCb3NzKGIscCl7dmFyIHI9Yi5yKnAucyx0PWIudCxob3Q9Yi5oaXQ+MDtpZihiLmhpdD4wKWIuaGl0LT0uMTsKIGN0eC5nbG9i"
    "YWxDb21wb3NpdGVPcGVyYXRpb249ImxpZ2h0ZXIiO3ZhciBnbD1jdHguY3JlYXRlUmFkaWFsR3JhZGllbnQocC54LHAueSwwLHAu"
    "eCxwLnkscioxLjYpO2dsLmFkZENvbG9yU3RvcCgwLCJyZ2JhKDI1NSw5MCw5MCwuMzUpIik7Z2wuYWRkQ29sb3JTdG9wKDEsInJn"
    "YmEoMjU1LDkwLDkwLDApIik7Y3R4LmZpbGxTdHlsZT1nbDtjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhwLngscC55LHIqMS42LDAs"
    "Ni4yODQpO2N0eC5maWxsKCk7Y3R4Lmdsb2JhbENvbXBvc2l0ZU9wZXJhdGlvbj0ic291cmNlLW92ZXIiOwogY3R4LnN0cm9rZVN0"
    "eWxlPSJyZ2JhKDI1NSwxMzgsMTI4LC42KSI7Y3R4LmxpbmVXaWR0aD1NYXRoLm1heCgxLHIqLjAzKTtjdHguYmVnaW5QYXRoKCk7"
    "Y3R4LmVsbGlwc2UocC54LHAueSxyKjEuMyxyKi4yOCx0Ki41LDAsNi4yODQpO2N0eC5zdHJva2UoKTsKIGN0eC5maWxsU3R5bGU9"
    "aG90PyIjZmZmIjoiIzdhMjIzMCI7Y3R4LmJlZ2luUGF0aCgpO2N0eC5lbGxpcHNlKHAueCxwLnkscixyKi40NCwwLDAsNi4yODQp"
    "O2N0eC5maWxsKCk7CiBjdHguZmlsbFN0eWxlPSIjZmY4YTgwIjtjdHguYmVnaW5QYXRoKCk7Y3R4LmVsbGlwc2UocC54LHAueS1y"
    "Ki4xMixyKi42MixyKi4zLDAsMCw2LjI4NCk7Y3R4LmZpbGwoKTsKIHZhciBleWU9KE1hdGguc2luKHQqMykrMSkvMjtjdHguZmls"
    "bFN0eWxlPSJyZ2JhKDI1NSwyNTUsMjU1LCIrKC41K2V5ZSouNSkrIikiO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKHAueCtNYXRo"
    "LnNpbih0KSpyKi4yLHAueS1yKi4xMixyKi4xLDAsNi4yODQpO2N0eC5maWxsKCk7CiBjdHguZmlsbFN0eWxlPSIjMDUwNzBmIjtm"
    "b3IodmFyIGk9LTI7aTw9MjtpKyspY3R4LmZpbGxSZWN0KHAueCtpKnIqLjI0LXIqLjA1LHAueStyKi4xMixyKi4xLHIqLjEyKTsK"
    "IHZhciBidz1NYXRoLm1pbihXKi43LHIqMS44KTtjdHguZmlsbFN0eWxlPSJyZ2JhKDI1NSwyNTUsMjU1LC4xNSkiO2N0eC5maWxs"
    "UmVjdChwLngtYncvMixwLnktciouNyxidyw2KTtjdHguZmlsbFN0eWxlPSIjZmY4YTgwIjtjdHguZmlsbFJlY3QocC54LWJ3LzIs"
    "cC55LXIqLjcsYncqKGIuaHAvYi5tYXgpLDYpOwogY3R4LmZvbnQ9IjgwMCAxMnB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2UiO2N0"
    "eC50ZXh0QWxpZ249ImNlbnRlciI7Y3R4LmZpbGxTdHlsZT0iI2ZmOGE4MCI7Y3R4LmZpbGxUZXh0KGIubmFtZSxwLngscC55LXIq"
    "LjctOCl9CgpmdW5jdGlvbiBkcmF3U2hpcCgpe3ZhciBzeD1DWCtzaGlwLngqLjU1LHN5PUgtNzYrc2hpcC55Ki4xODsKIGlmKG9y"
    "YnM+MCl7Y3R4Lmdsb2JhbENvbXBvc2l0ZU9wZXJhdGlvbj0ibGlnaHRlciI7Zm9yKHZhciBvPTA7bzxvcmJzO28rKyl7dmFyIGE9"
    "cGVyZm9ybWFuY2Uubm93KCkvNDAwK28qNi4yODMvb3Jiczt2YXIgb3g9c3grTWF0aC5jb3MoYSkqNTQsb3k9c3krTWF0aC5zaW4o"
    "YSkqMjQ7CiAgY3R4LmZpbGxTdHlsZT0icmdiYSgxNDMsMjA4LDI1NSwuMzUpIjtjdHguYmVnaW5QYXRoKCk7Y3R4LmFyYyhveCxv"
    "eSwxMSwwLDYuMjg0KTtjdHguZmlsbCgpO2N0eC5maWxsU3R5bGU9IiNjZmVhZmYiO2N0eC5iZWdpblBhdGgoKTtjdHguYXJjKG94"
    "LG95LDQuNSwwLDYuMjg0KTtjdHguZmlsbCgpfWN0eC5nbG9iYWxDb21wb3NpdGVPcGVyYXRpb249InNvdXJjZS1vdmVyIn0KIGlm"
    "KHNoaXAuaW52PjAmJigoc2hpcC5pbnYqMTQpfDApJTIpcmV0dXJuOwogY3R4LnNhdmUoKTtjdHgudHJhbnNsYXRlKHN4LHN5KTtj"
    "dHgucm90YXRlKHNoaXAucm9sbCk7CiBjdHguZ2xvYmFsQ29tcG9zaXRlT3BlcmF0aW9uPSJsaWdodGVyIjtjdHguZmlsbFN0eWxl"
    "PSJyZ2JhKDI0NSwxOTQsMTA3LC4zNSkiO2N0eC5iZWdpblBhdGgoKTtjdHguZWxsaXBzZSgtOSwzMCw5LDE4K01hdGgucmFuZG9t"
    "KCkqOCwwLDAsNi4yODQpO2N0eC5lbGxpcHNlKDksMzAsOSwxOCtNYXRoLnJhbmRvbSgpKjgsMCwwLDYuMjg0KTtjdHguZmlsbCgp"
    "OwogY3R4LmZpbGxTdHlsZT0icmdiYSgyNTUsMjMwLDE3MCwuOTUpIjtjdHguZmlsbFJlY3QoLTEyLDE2LDYsMTArTWF0aC5yYW5k"
    "b20oKSoxNCk7Y3R4LmZpbGxSZWN0KDYsMTYsNiwxMCtNYXRoLnJhbmRvbSgpKjE0KTtjdHguZ2xvYmFsQ29tcG9zaXRlT3BlcmF0"
    "aW9uPSJzb3VyY2Utb3ZlciI7CiB2YXIgc2c9Y3R4LmNyZWF0ZUxpbmVhckdyYWRpZW50KDAsLTI2LDAsMjQpO3NnLmFkZENvbG9y"
    "U3RvcCgwLCIjZjNkOThhIik7c2cuYWRkQ29sb3JTdG9wKDEsIiM5YTdiMmMiKTtjdHguZmlsbFN0eWxlPXNnOwogY3R4LmJlZ2lu"
    "UGF0aCgpO2N0eC5tb3ZlVG8oMCwtMjgpO2N0eC5saW5lVG8oMTUsNik7Y3R4LmxpbmVUbyg0MiwxOCk7Y3R4LmxpbmVUbygzNiwy"
    "NSk7Y3R4LmxpbmVUbyg5LDIwKTtjdHgubGluZVRvKC05LDIwKTtjdHgubGluZVRvKC0zNiwyNSk7Y3R4LmxpbmVUbygtNDIsMTgp"
    "O2N0eC5saW5lVG8oLTE1LDYpO2N0eC5jbG9zZVBhdGgoKTtjdHguZmlsbCgpOwogY3R4LmZpbGxTdHlsZT0iIzBkMTQyNCI7Y3R4"
    "LmJlZ2luUGF0aCgpO2N0eC5tb3ZlVG8oMCwtMTcpO2N0eC5saW5lVG8oNyw0KTtjdHgubGluZVRvKC03LDQpO2N0eC5jbG9zZVBh"
    "dGgoKTtjdHguZmlsbCgpOwogY3R4LmZpbGxTdHlsZT1zcHJlYWQ+MD8iI2I4ZmZlMCI6IiM3ZmUzYjAiO2N0eC5maWxsUmVjdCgt"
    "Mi41LC0xMSw1LDkpOwogY3R4LmZpbGxTdHlsZT0iIzdmZTNiMCI7Y3R4LmZpbGxSZWN0KC00MiwxNyw0LDMpO2N0eC5maWxsU3R5"
    "bGU9IiNmZjhhODAiO2N0eC5maWxsUmVjdCgzOCwxNyw0LDMpO2N0eC5yZXN0b3JlKCl9CgpmdW5jdGlvbiBodWQoKXskKCJoU2Nv"
    "cmUiKS50ZXh0Q29udGVudD1zY29yZTskKCJoTGV2ZWwiKS50ZXh0Q29udGVudD1sZXZlbDskKCJjb21ibyIpLnRleHRDb250ZW50"
    "PSJ4IittdWx0OyQoImNoYWluIikudGV4dENvbnRlbnQ9IiMiK2NoYWluTjsKIHZhciBzPVtdO2lmKHNwcmVhZD4wKXMucHVzaCgi"
    "UEFTU1BPUlQgIitNYXRoLmNlaWwoc3ByZWFkKSsicyIpO2lmKG9yYnM+MClzLnB1c2goIldJVE5FU1MgeCIrb3Jicyk7JCgicHci"
    "KS50ZXh0Q29udGVudD1zLmpvaW4oIiDCtyAiKX0KCi8qIC0tLS0tLS0tLS0gbGVhZGVyYm9hcmQgLS0tLS0tLS0tLSAqLwp2YXIg"
    "Ym9hcmQ9W107CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2UoL1smPD4iXS9nLGZ1bmN0aW9uKGMpe3Jl"
    "dHVybnsiJiI6IiZhbXA7IiwiPCI6IiZsdDsiLCI+IjoiJmd0OyIsJyInOiImcXVvdDsifVtjXX0pfQpmdW5jdGlvbiBkcmF3Qm9h"
    "cmQoZWwpe2lmKCFib2FyZC5sZW5ndGgpe2VsLmlubmVySFRNTD0nPGRpdiBjbGFzcz0icm93Ij48c3BhbiBjbGFzcz0ibiIgc3R5"
    "bGU9ImNvbG9yOiM3ZDg5YTgiPk5vIHBpbG90cyB5ZXQuIEJlIHRoZSBmaXJzdC48L3NwYW4+PC9kaXY+JztyZXR1cm59CiB2YXIg"
    "bT1bIvCfpYciLCLwn6WIIiwi8J+liSJdO2VsLmlubmVySFRNTD1ib2FyZC5zbGljZSgwLDMpLm1hcChmdW5jdGlvbihlLGkpe3Jl"
    "dHVybiAnPGRpdiBjbGFzcz0icm93Ij48c3BhbiBjbGFzcz0ibSI+JyttW2ldKyc8L3NwYW4+PHNwYW4gY2xhc3M9Im4iPicrZXNj"
    "KGUubmFtZSkrJzwvc3Bhbj48c3BhbiBjbGFzcz0icyI+JytlLnNjb3JlKyc8L3NwYW4+JysoZS5ibG9ja19pbmRleD8nPGEgaHJl"
    "Zj0iJytlc2MoZS52ZXJpZnkpKyciIHRhcmdldD0iX2JsYW5rIj5ibG9jayAnK2UuYmxvY2tfaW5kZXgrJzwvYT4nOicnKSsnPC9k"
    "aXY+J30pLmpvaW4oIiIpfQpmdW5jdGlvbiBsb2FkQm9hcmQoY2Ipe2ZldGNoKCIveC9nYW1lL3Njb3JlcyIse2NhY2hlOiJuby1z"
    "dG9yZSJ9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiByLmpzb24oKX0pLnRoZW4oZnVuY3Rpb24oZCl7Ym9hcmQ9ZC5zY29yZXN8"
    "fFtdO2RyYXdCb2FyZCgkKCJib2FyZFQiKSk7ZHJhd0JvYXJkKCQoImJvYXJkTyIpKTtjYiYmY2IoKX0pCiAuY2F0Y2goZnVuY3Rp"
    "b24oKXtib2FyZD1bXTskKCJib2FyZFQiKS5pbm5lckhUTUw9JzxkaXYgY2xhc3M9InJvdyI+PHNwYW4gY2xhc3M9Im4iIHN0eWxl"
    "PSJjb2xvcjojN2Q4OWE4Ij5CZXN0IG9uIHRoaXMgZGV2aWNlOiAnKyhwcm9nLmJlc3R8fDApKyc8L3NwYW4+PC9kaXY+JztjYiYm"
    "Y2IoKX0pfQpmdW5jdGlvbiBxdWFsaWZpZXMoKXtyZXR1cm4gc2NvcmU+MCYmKGJvYXJkLmxlbmd0aDwzfHxzY29yZT5ib2FyZFtN"
    "YXRoLm1pbigyLGJvYXJkLmxlbmd0aC0xKV0uc2NvcmUpfQokKCJiU2VhbCIpLm9uY2xpY2s9ZnVuY3Rpb24oKXt2YXIgbm09JCgi"
    "bmFtZUluIikudmFsdWUudG9VcHBlckNhc2UoKS5yZXBsYWNlKC9bXkEtWjAtOSBdL2csIiIpLnRyaW0oKS5zbGljZSgwLDEyKTtp"
    "Zighbm0peyQoIm5hbWVJbiIpLmZvY3VzKCk7cmV0dXJufQogdGhpcy5kaXNhYmxlZD10cnVlOyQoInNlYWxlZCIpLnRleHRDb250"
    "ZW50PSJTZWFsaW5nIGludG8gdGhlIGNoYWlu4oCmIjsKIGZldGNoKCIveC9nYW1lL3N1Ym1pdCIse21ldGhvZDoiUE9TVCIsaGVh"
    "ZGVyczp7IkNvbnRlbnQtVHlwZSI6ImFwcGxpY2F0aW9uL2pzb24ifSxib2R5OkpTT04uc3RyaW5naWZ5KHtuYW1lOm5tLHNjb3Jl"
    "OnNjb3JlLHNlY3RvcjpsZXZlbCxraWxsczpraWxsc30pfSkKIC50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiByLmpzb24oKX0pLnRo"
    "ZW4oZnVuY3Rpb24oZCl7JCgibmFtZUJveCIpLnN0eWxlLmRpc3BsYXk9Im5vbmUiOwogIGlmKGQuc2VhbGVkKXskKCJzZWFsZWQi"
    "KS5pbm5lckhUTUw9IlNlYWxlZCBpbiBibG9jayAiK2QuYmxvY2tfaW5kZXgrJy4gQW55b25lIGNhbiBjaGVjayBpdDogPGEgaHJl"
    "Zj0iJytlc2MoZC52ZXJpZnkpKyciIHRhcmdldD0iX2JsYW5rIj52ZXJpZnk8L2E+J31lbHNleyQoInNlYWxlZCIpLnRleHRDb250"
    "ZW50PWQubWVzc2FnZXx8Ik5vdCBzYXZlZC4ifQogIGxvYWRCb2FyZCgpfSkuY2F0Y2goZnVuY3Rpb24oKXskKCJzZWFsZWQiKS50"
    "ZXh0Q29udGVudD0iQ291bGRuJ3QgcmVhY2ggdGhlIGNoYWluLiBUcnkgYWdhaW4gbGF0ZXIuIn0pLnRoZW4oZnVuY3Rpb24oKXsk"
    "KCJiU2VhbCIpLmRpc2FibGVkPWZhbHNlfSl9OwoKLyogLS0tLS0tLS0tLSBmbG93IC0tLS0tLS0tLS0gKi8KZnVuY3Rpb24gc2hv"
    "dyhpZCl7WyJzY1RpdGxlIiwic2NQaWNrIiwic2NOZXh0Iiwic2NPdmVyIl0uZm9yRWFjaChmdW5jdGlvbihzKXskKHMpLmNsYXNz"
    "TGlzdC50b2dnbGUoIm9uIixzPT09aWQpfSk7cGF1c2VkPSEhaWQ7JCgiaGludCIpLnN0eWxlLm9wYWNpdHk9aWQ/IjAiOiIxIn0K"
    "ZnVuY3Rpb24gc3RhcnRMZXZlbChuKXtyZXNpemUoKTtidWlsZChuKTtodWQoKTtzaG93KG51bGwpOyQoImh1bGxGIikuc3R5bGUu"
    "d2lkdGg9aHVsbCsiJSI7aWYoIXJ1bm5pbmcpe3J1bm5pbmc9dHJ1ZTtsYXN0PXBlcmZvcm1hbmNlLm5vdygpO3JlcXVlc3RBbmlt"
    "YXRpb25GcmFtZShzdGVwKX0KIHNheShjZmcuYm9zcz8iU0VDVE9SICIrbisiIMK3ICIrY2ZnLm5hbWUudG9VcHBlckNhc2UoKToi"
    "U0VDVE9SICIrbisiIMK3ICIrY2ZnLm5hbWUsY2ZnLmJvc3M/IiNmZjhhODAiOiIjYzlhODRjIixjZmcuYm9zcz8iQW4gb3JjaGVz"
    "dHJhdG9yIGlzIHdhaXRpbmcuIjoiIik7dG9uZSgyMjAsLjQsInNpbmUiLC4wNiw0NDApfQpmdW5jdGlvbiBzdGFydFJ1bihuKXtz"
    "Y29yZT0wO2tpbGxzPTA7Y2hhaW5OPTA7aHVsbD0xMDA7c3RyZWFrPTA7bXVsdD0xO3NwcmVhZD0wO29yYnM9MDtzdGFydExldmVs"
    "KG4pfQpmdW5jdGlvbiBjbGVhcigpe3BhdXNlZD10cnVlO2lmKGxldmVsPihwcm9nLmx2fHwwKSlwcm9nLmx2PWxldmVsO2lmKHNj"
    "b3JlPihwcm9nLmJlc3R8fDApKXByb2cuYmVzdD1zY29yZTtzYXZlKCk7CiBodWxsPU1hdGgubWluKDEwMCxodWxsKzIwKTskKCJo"
    "dWxsRiIpLnN0eWxlLndpZHRoPWh1bGwrIiUiOyQoIm5TY29yZSIpLnRleHRDb250ZW50PXNjb3JlOyQoIm5LaWxscyIpLnRleHRD"
    "b250ZW50PWtpbGxzOwogaWYobGV2ZWw+PU1BWExWKXtvdmVyKHRydWUpO3JldHVybn0KICQoIm5leHRUaXRsZSIpLnRleHRDb250"
    "ZW50PWNmZy5uYW1lKyIgY2xlYXIiOyQoIm5leHROb3RlIikudGV4dENvbnRlbnQ9RkFDVFNbbGV2ZWwtMV07CiAkKCJiTmV4dCIp"
    "LnRleHRDb250ZW50PShTRUNUT1JTW2xldmVsXS5ib3NzPyLimqAgIjoiIikrIlNlY3RvciAiKyhsZXZlbCsxKTtzaG93KCJzY05l"
    "eHQiKX0KZnVuY3Rpb24gb3Zlcih3b24pe3BhdXNlZD10cnVlO3J1bm5pbmc9ZmFsc2U7aWYoc2NvcmU+KHByb2cuYmVzdHx8MCkp"
    "e3Byb2cuYmVzdD1zY29yZTtzYXZlKCl9CiAkKCJvdmVyVGl0bGUiKS50ZXh0Q29udGVudD13b24/IllvdSBiZWF0IHRoZSBDb3Jl"
    "IjoiSHVsbCBicmVhY2hlZCI7JCgib1Njb3JlIikudGV4dENvbnRlbnQ9c2NvcmU7JCgib0xldmVsIikudGV4dENvbnRlbnQ9bGV2"
    "ZWw7JCgib0tpbGxzIikudGV4dENvbnRlbnQ9a2lsbHM7CiAkKCJzZWFsZWQiKS50ZXh0Q29udGVudD0iIjskKCJuYW1lQm94Iiku"
    "c3R5bGUuZGlzcGxheT0ibm9uZSI7c2hvdygic2NPdmVyIik7CiBsb2FkQm9hcmQoZnVuY3Rpb24oKXtpZihxdWFsaWZpZXMoKSl7"
    "JCgibmFtZUJveCIpLnN0eWxlLmRpc3BsYXk9ImZsZXgiOyQoIm5hbWVJbiIpLnZhbHVlPSIifX0pfQoKLyogLS0tLS0tLS0tLSBp"
    "bnB1dCAtLS0tLS0tLS0tICovCnZhciBkcmFnPWZhbHNlLG94PTAsb3k9MCxzeDA9MCxzeTA9MDtmdW5jdGlvbiBwdChlKXt2YXIg"
    "dD1lLnRvdWNoZXM/ZS50b3VjaGVzWzBdOmU7cmV0dXJue3g6dC5jbGllbnRYLHk6dC5jbGllbnRZfX0KY3YuYWRkRXZlbnRMaXN0"
    "ZW5lcigidG91Y2hzdGFydCIsZnVuY3Rpb24oZSl7ZHJhZz10cnVlO3ZhciBwPXB0KGUpO294PXAueDtveT1wLnk7c3gwPXNoaXAu"
    "dHg7c3kwPXNoaXAudHl9LHtwYXNzaXZlOmZhbHNlfSk7CmN2LmFkZEV2ZW50TGlzdGVuZXIoInRvdWNobW92ZSIsZnVuY3Rpb24o"
    "ZSl7aWYoIWRyYWd8fHBhdXNlZClyZXR1cm47dmFyIHA9cHQoZSk7c2hpcC50eD1jbGFtcChzeDArKHAueC1veCkqMS43LC00MzAs"
    "NDMwKTtzaGlwLnR5PWNsYW1wKHN5MCsocC55LW95KSoxLjQsLTI2MCwyNDApO2lmKGUuY2FuY2VsYWJsZSllLnByZXZlbnREZWZh"
    "dWx0KCl9LHtwYXNzaXZlOmZhbHNlfSk7CmN2LmFkZEV2ZW50TGlzdGVuZXIoInRvdWNoZW5kIixmdW5jdGlvbigpe2RyYWc9ZmFs"
    "c2V9KTsKY3YuYWRkRXZlbnRMaXN0ZW5lcigibW91c2Vkb3duIixmdW5jdGlvbihlKXtkcmFnPXRydWU7dmFyIHA9cHQoZSk7b3g9"
    "cC54O295PXAueTtzeDA9c2hpcC50eDtzeTA9c2hpcC50eX0pOwphZGRFdmVudExpc3RlbmVyKCJtb3VzZW1vdmUiLGZ1bmN0aW9u"
    "KGUpe2lmKCFkcmFnfHxwYXVzZWQpcmV0dXJuO3ZhciBwPXB0KGUpO3NoaXAudHg9Y2xhbXAoc3gwKyhwLngtb3gpKjEuNywtNDMw"
    "LDQzMCk7c2hpcC50eT1jbGFtcChzeTArKHAueS1veSkqMS40LC0yNjAsMjQwKX0pOwphZGRFdmVudExpc3RlbmVyKCJtb3VzZXVw"
    "IixmdW5jdGlvbigpe2RyYWc9ZmFsc2V9KTsKYWRkRXZlbnRMaXN0ZW5lcigia2V5ZG93biIsZnVuY3Rpb24oZSl7aWYoZG9jdW1l"
    "bnQuYWN0aXZlRWxlbWVudD09PSQoIm5hbWVJbiIpKXJldHVybjtpZihlLmtleT09PSJBcnJvd0xlZnQiKXNoaXAudHg9Y2xhbXAo"
    "c2hpcC50eC00NiwtNDMwLDQzMCk7aWYoZS5rZXk9PT0iQXJyb3dSaWdodCIpc2hpcC50eD1jbGFtcChzaGlwLnR4KzQ2LC00MzAs"
    "NDMwKTtpZihlLmtleT09PSJBcnJvd1VwIilzaGlwLnR5PWNsYW1wKHNoaXAudHktNDAsLTI2MCwyNDApO2lmKGUua2V5PT09IkFy"
    "cm93RG93biIpc2hpcC50eT1jbGFtcChzaGlwLnR5KzQwLC0yNjAsMjQwKX0pOwokKCJiU3RhcnQiKS5vbmNsaWNrPWZ1bmN0aW9u"
    "KCl7c3RhcnRSdW4oMSl9OyQoImJQaWNrIikub25jbGljaz1mdW5jdGlvbigpe2dyaWQoKTtzaG93KCJzY1BpY2siKX07JCgiYkJh"
    "Y2siKS5vbmNsaWNrPWZ1bmN0aW9uKCl7c2hvdygic2NUaXRsZSIpfTsKJCgiYlF1aXQiKS5vbmNsaWNrPWZ1bmN0aW9uKCl7b3Zl"
    "cihmYWxzZSl9OyQoImJIb21lIikub25jbGljaz1mdW5jdGlvbigpe2xvYWRCb2FyZCgpO3Nob3coInNjVGl0bGUiKX07JCgiYlJl"
    "dHJ5Iikub25jbGljaz1mdW5jdGlvbigpe3N0YXJ0UnVuKGxldmVsKX07CiQoImJOZXh0Iikub25jbGljaz1mdW5jdGlvbigpe3N0"
    "YXJ0TGV2ZWwobGV2ZWwrMSl9OwpmdW5jdGlvbiBncmlkKCl7dmFyIGc9JCgibHYiKSxiZXN0PXByb2cubHZ8fDAscz0iIjskKCJw"
    "aWNrU3ViIikudGV4dENvbnRlbnQ9YmVzdCsiIG9mICIrTUFYTFYrIiBjbGVhcmVkIMK3IHJlZCA9IG9yY2hlc3RyYXRvciI7CiBm"
    "b3IodmFyIGk9MTtpPD1NQVhMVjtpKyspe3ZhciBjPWk8PWJlc3Q/ImRvbmUiOihpPD1iZXN0KzE/IiI6ImxvY2siKTtpZihTRUNU"
    "T1JTW2ktMV0uYm9zcyljKz0iIGJvc3MiO3MrPSc8YnV0dG9uIGNsYXNzPSInK2MrJyIgZGF0YS1uPSInK2krJyI+JytpKyc8L2J1"
    "dHRvbj4nfQogZy5pbm5lckhUTUw9cztBcnJheS5wcm90b3R5cGUuZm9yRWFjaC5jYWxsKGcucXVlcnlTZWxlY3RvckFsbCgiYnV0"
    "dG9uIiksZnVuY3Rpb24oYil7aWYoYi5jbGFzc0xpc3QuY29udGFpbnMoImxvY2siKSlyZXR1cm47Yi5vbmNsaWNrPWZ1bmN0aW9u"
    "KCl7c3RhcnRSdW4ocGFyc2VJbnQoYi5kYXRhc2V0Lm4sMTApKX19KX0KcmVzaXplKCk7Y2ZnPVNFQ1RPUlNbMF07ZmllbGRJbml0"
    "KCk7aHVkKCk7cmVuZGVyKCk7bG9hZEJvYXJkKCk7Cn0pKCk7Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K"
)
_HTML = base64.b64decode("".join(_HTML_B64.split()))
_patched = False
_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS game_score(id INTEGER PRIMARY KEY "
                            "AUTOINCREMENT,name TEXT,score INTEGER,sector INTEGER,kills INTEGER,"
                            "at REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].commit()
    _ready = True


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
    if getattr(cls, "_game_patched", False):
        _patched = True
        return True
    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == PAGE_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(_HTML)))
            self.end_headers()
            self.wfile.write(_HTML)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._game_patched = True
    _patched = True
    return True


def _verify(block):
    return "https://sebbi.pro/x/walk/block?index=%s" % block if block is not None else None


def _top(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT name,score,sector,kills,at,audit_hash,block_index "
                                   "FROM game_score ORDER BY score DESC, at ASC LIMIT ?",
                                   (TOP,)).fetchall()
    return [{"name": r[0], "score": r[1], "sector": r[2], "kills": r[3],
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[4])),
             "sealed_in_chain": r[5], "block_index": r[6], "verify": _verify(r[6])} for r in rows]


def _int(v, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def _submit(ctx, data):
    name = NAME_RE.sub("", str(data.get("name", "")).upper()).strip()[:12]
    score = _int(data.get("score"), 1, 5000000)
    sector = _int(data.get("sector"), 1, 15)
    kills = _int(data.get("kills"), 0, 5000)
    if not name or score is None or sector is None or kills is None:
        return {"sealed": False, "message": "That score could not be read."}, 400
    bosses = sector // 5
    if score > kills * 1800 + bosses * 16000 + 5000:
        return {"sealed": False, "message": "That score is not possible for the run described."}, 400
    top = _top(ctx)
    if len(top) >= TOP and score <= top[-1]["score"]:
        return {"sealed": False, "message": "Great run, but not quite top ten."}, 200
    now = time.time()
    ev = {"user_id": "game:" + name, "action": "game_score", "amount": 0, "country": "UK",
          "device_id": "deep-run", "anomaly": 0, "device_risk": 0}
    res = {"decision": "GAME_SCORE_SEALED", "score": 0, "game_version": VERSION,
           "detail": "name=%s;score=%d;sector=%d;kills=%d" % (name, score, sector, kills)}
    out = ctx["seal"](ev, res, now, KEY)
    audit_hash = out[0] if isinstance(out, (list, tuple)) else out
    block = out[1] if isinstance(out, (list, tuple)) and len(out) > 1 else None
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO game_score(name,score,sector,kills,at,audit_hash,block_index) "
                            "VALUES(?,?,?,?,?,?,?)", (name, score, sector, kills, now, audit_hash, block))
        ctx["conn"].commit()
    rank = 1 + sum(1 for t in top if t["score"] >= score)
    return {"sealed": True, "name": name, "score": score, "rank": rank,
            "sealed_in_chain": audit_hash, "block_index": block, "verify": _verify(block)}, 200


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}
    if action == "scores":
        return {"scores": _top(ctx)}, 200
    if action == "submit" and method == "POST":
        return _submit(ctx, data)
    return {"module": "game", "version": VERSION, "armed": armed, "serves": PAGE_PATH,
            "scores": "https://sebbi.pro/x/game/scores"}, 200

```


## `modules/genesis.py`

282 lines, 12662 bytes

```python
"""
Chain identity - /x/genesis/<action>

WHY THIS EXISTS
---------------
A receipt that does not say which chain state it belongs to is ambiguous the
moment a chain is ever reset, and this one was: on 7 September 2026, during
registry work, the chain was reset. Receipts issued before that date belong to
a state that does not continue forward. Nothing in those receipts says so, and
a peer holding one has no way to discover it from the receipt itself.

Philip Pinol (PRAXIS / ThePraesidium.ai) independently verified block 846 of
the prior state. That verification was sound for the state it was performed
against. It is not continuous with the chain running now, and saying so is
this module's job.

WHAT IT DOES
------------
Publishes the genesis hash of the current chain state and a short stable
identifier derived from it, so any party can pin their own records to a named
state rather than to a block number that may refer to two different things.

    chain_id = first 16 characters of the genesis block's audit hash

Deliberately a slice rather than a computation. Anyone can confirm the
identifier against the genesis hash by eye, in the response that carries both,
without running anything.

WHY IT IS A SEPARATE MODULE
---------------------------
Read-only, by construction. It opens the same database as the sealing code and
never writes to it: no inserts, no schema changes, no seal calls. A fault here
returns a 500 on this route and the chain carries on sealing, because the
module that seals does not import this one and does not know it exists.

That is not tidiness. Editing a file that writes an append-only chain in order
to add a reporting route is how the 7 September reset happened.

WHAT IT DOES NOT CLAIM
----------------------
- It does not assert when the reset occurred. It reports the sealed timestamp
  of block 1 as the database holds it, and states the reset date separately as
  a claim by the operator. If the two disagree, the disagreement is visible in
  the response rather than resolved quietly here.
- A chain_id identifies a state. It says nothing about whether the records in
  that state are true, complete, or externally anchored. Check /x/ots/status
  for anchoring and /api/verify-chain for internal validity.
- Two different deployments could in principle produce the same 16-character
  identifier. The full genesis hash is returned alongside it and is what
  should be pinned where collision matters.

    GET /x/genesis/chain    genesis hash, chain_id, height, current tip
    GET /x/genesis/status   is this module loaded and can it read the chain
    GET /x/genesis/spec     what the identifier is and how to pin it
"""

from datetime import datetime, timezone

VERSION = "1.0.1"

# Length of the genesis hash used as the chain identifier. Sixteen hex
# characters is 64 bits - long enough that two states will not collide by
# accident, short enough to quote in an email without wrapping.
CHAIN_ID_LEN = 16

# Routes that need no API key. A third party must be able to establish which
# chain state a receipt belongs to without holding an account, or the receipt
# is only checkable by customers.
PUBLIC = {("GET", "chain"), ("GET", "status"), ("GET", "spec")}

# ----------------------------------------------------------------------
# everything a reader sees
# ----------------------------------------------------------------------

# The reset moment, stated to the second and in UTC, because a date alone was
# ambiguous: the chain was reset just after midnight UK time, so the calendar
# date differs between UTC and local and the route appeared to contradict
# itself. Stated precisely rather than rounded to whichever date reads better.
RESET_AT_UTC = "2026-09-06T23:11:12Z"

RESET_RECORD = {
    "occurred": RESET_AT_UTC,
    "occurred_local": (
        "00:11 on 7 September 2026, UK time. The same moment. Recorded in UTC "
        "above because a calendar date is ambiguous within an hour of "
        "midnight and this one falls inside that hour."),
    "reason": "chain reset during registry work",
    "effect": (
        "Receipts, block indexes and audit hashes issued before this date "
        "belong to a prior chain state. That state does not continue forward "
        "into the chain running now. A block index from before the reset and "
        "a block index from after it are not comparable and do not refer to "
        "the same sequence."),
    "prior_verification": (
        "Block 846 of the prior state was independently verified by Philip "
        "Pinol (PRAXIS / ThePraesidium.ai). That verification was sound for "
        "the state it was performed against. It is not evidence about the "
        "current state, and neither party describes it as continuous with it."),
    "what_was_not_lost": (
        "The prior state's records were sealed under the rules in force at "
        "the time and were valid under them. What changed is that the "
        "sequence does not extend. Nothing here claims the earlier records "
        "were wrong."),
    "disclosed_because": (
        "A peer holding a pre-reset receipt cannot discover any of this from "
        "the receipt itself. Published rather than left for someone to find "
        "when their records fail to reconcile."),
}

VOCABULARY = {
    "chain_id": (
        "A short stable identifier for one chain state, being the first %d "
        "characters of that state's genesis block hash. Pin your records to "
        "this rather than to a block index. If a chain is ever reset, the "
        "chain_id changes and the mismatch is visible immediately; a block "
        "index silently refers to a different thing." % CHAIN_ID_LEN),
    "genesis_hash": (
        "The audit hash of block 1 of the current chain state. This is the "
        "value to pin where a 16-character identifier is not enough. It does "
        "not change for the life of the state."),
    "genesis_sealed_at": (
        "The timestamp stored against block 1, as the database holds it. It "
        "is this deployment's own clock at the moment that block was written "
        "and is not evidence of when anything happened. The external "
        "timestamp proofs at /x/ots/status are the answer to that question."),
    "height": (
        "How many blocks the current state holds. Counts from block 1 of this "
        "state, not from the beginning of any prior state."),
    "current_tip": (
        "The audit hash of the most recent block. Changes constantly. "
        "Included so one call establishes the whole identity of the state; "
        "/x/witness/tip is the route to poll."),
}


def _iso(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def _first_block(ctx):
    """Block 1 of the current state. Read-only."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id ASC LIMIT 1"
        ).fetchone()


def _last_block(ctx):
    """Current tip. Read-only. Same query witness.py uses, deliberately."""
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT audit_hash,ts,id FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()


def _chain(ctx):
    first = _first_block(ctx)
    if not first:
        return {"error": "no_genesis",
                "message": ("The audit chain holds no blocks, so there is no "
                            "genesis to report. This is an empty chain rather "
                            "than a fault."),
                "genesis_version": VERSION}, 404

    genesis_hash = str(first[0])
    chain_id = genesis_hash[:CHAIN_ID_LEN]
    last = _last_block(ctx)

    out = {
        "chain_id": chain_id,
        "genesis_hash": genesis_hash,
        "genesis_block_index": first[2],
        "genesis_sealed_at": _iso(first[1]),
        "height": last[2] if last else first[2],
        "current_tip": last[0] if last else genesis_hash,
        "current_sealed_at": _iso(last[1]) if last else _iso(first[1]),
        "genesis_version": VERSION,
        "reset_record": RESET_RECORD,
        "vocabulary": VOCABULARY,
        "how_to_pin": (
            "Record chain_id alongside every receipt you hold from this "
            "deployment. When you later check a receipt, read this route "
            "first: if chain_id has changed, your receipt belongs to a state "
            "that no longer continues and no block index in it is comparable "
            "to a current one."),
        "verify_the_identifier": (
            "chain_id is the first %d characters of genesis_hash. Both are in "
            "this response. Check it by eye - nothing needs to be run."
            % CHAIN_ID_LEN),
        "this_does_not_establish": (
            "That the records in this state are true, complete, or externally "
            "anchored. /api/verify-chain checks the chain end to end. "
            "/x/ots/status shows the state of each external timestamp proof."),
    }

    # State rather than assert. The stated reset moment and the sealed
    # timestamp of block 1 should be the same event. If they are not, the
    # reader sees the disagreement here rather than being told a tidy story.
    #
    # Compared to the minute, in UTC, on both sides. Comparing calendar dates
    # was wrong: this chain was reset at 23:11 UTC, which is the following day
    # locally, so a date comparison reported a contradiction that did not
    # exist. A route that cries wolf about its own honesty is worse than one
    # that says nothing.
    sealed = out["genesis_sealed_at"]
    if sealed and sealed[:16] != RESET_AT_UTC[:16]:
        out["date_note"] = (
            "The sealed timestamp of block 1 (%s) does not match the reset "
            "moment stated in reset_record (%s). Both values are reported as "
            "they are. Reconcile them against the external timestamp proofs "
            "rather than against either party's account."
            % (sealed, RESET_AT_UTC))

    return out, 200


def _status(ctx):
    """Arming route. Says whether this module loaded and can read the chain."""
    readable = False
    detail = None
    try:
        readable = _first_block(ctx) is not None
        if not readable:
            detail = "chain is readable and holds no blocks"
    except Exception as exc:
        detail = "could not read the audit chain (%s)" % type(exc).__name__

    return {"module": "genesis",
            "version": VERSION,
            "chain_readable": readable,
            "detail": detail,
            "writes": "none - this module never writes to the database",
            "routes": sorted(a for _m, a in PUBLIC),
            "genesis_version": VERSION}, 200


def _spec():
    return {"module": "genesis",
            "genesis_version": VERSION,
            "purpose": (
                "Publishes which chain state this deployment is running, so a "
                "receipt can be pinned to a named state rather than to a "
                "block index that may refer to two different sequences."),
            "chain_id_rule": (
                "The first %d characters of the genesis block's audit hash. "
                "Not a hash of a hash, not a derived key - a slice, so it can "
                "be checked by eye against the genesis hash returned beside "
                "it." % CHAIN_ID_LEN),
            "routes": {
                "GET /x/genesis/chain": "chain_id, genesis hash, height, tip",
                "GET /x/genesis/status": "module loaded, chain readable",
                "GET /x/genesis/spec": "this document",
            },
            "vocabulary": VOCABULARY,
            "reset_record": RESET_RECORD,
            "read_only": (
                "This module performs no writes of any kind. It opens the "
                "same database the sealing code uses and issues two SELECT "
                "statements. A fault here cannot affect the chain."),
            "related": {
                "/x/witness/tip": "current tip, for peers to record",
                "/api/verify-chain": "checks this chain end to end",
                "/x/ots/status": "state of each external timestamp proof",
            }}, 200


def handle(method, action, data, api_key, ctx):
    if method == "GET":
        if action == "chain":
            return _chain(ctx)
        if action == "status":
            return _status(ctx)
        if action == "spec":
            return _spec()
    return {"error": "unknown_action", "action": action,
            "routes": sorted(a for _m, a in PUBLIC)}, 404

```
