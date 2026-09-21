# Codebase — part 7 of 36

Contains:
- `modules/grade.py`
- `modules/heartbeat.py`
- `modules/held.py`
- `modules/homelink.py`


## `modules/grade.py`

674 lines, 26478 bytes

```python
"""
modules/grade.py  v1.0.0  —  public transparency-file scanner

WHAT IT DOES
------------
Fetches a domain's public convention files and reports, per file, what was
actually found: served or not, parses or not, and the specific fields present.
Nothing else.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not issue a letter grade, a score, or a verdict, and the words
"compliant" and "non-compliant" appear nowhere in its output.

The reason is not squeamishness. Half of these files are conventions rather
than requirements. No law anywhere obliges a company to serve ai.txt,
comply.txt, llms.txt or an AI-safety file, and two of those are conventions
this operator helped write. Scoring the market against your own file format
and publishing a letter is marking other people's homework with your own
marking scheme. So this reports observations and lets the reader conclude.

Absence is reported as absence. That is a fact about a file. It is not a
finding about a company, and this module never converts one into the other.

THE CLOAKING CHECK WAS REMOVED
------------------------------
An earlier version compared homepage byte-length under two user agents and
scored a >10% difference as cloaking. Any page with a clock, a nonce or a
rotating banner fails that; real cloaking returning a similar-length page
passes it. It measured noise and reported it as a signal, so it is gone
rather than reworded.

ROUTES
------
  POST /x/grade/scan          KEYED   scan a domain, seal the result
  GET  /x/grade/report        public  ?domain= — the last scan of that domain
  GET  /x/grade/list          public  domains scanned, most recent first
  GET  /x/grade/spec          public  what each check means
  GET  /grade-badge?domain=   public  SVG, served from cache ONLY

BADGE BEHAVIOUR THAT MATTERS
----------------------------
The badge never triggers a fetch of the target. An earlier version re-ran
every check on every image load, so embedding the badge on a busy page would
have pointed sustained unsolicited traffic at somebody else's server from
this IP. The badge now renders from the stored scan or says "not scanned".

SAFETY
------
https only, port 443, DNS resolved and checked against private, loopback,
link-local, multicast and reserved ranges before any request, redirects not
followed, 8s timeout, 256KB cap per file. Known limit, stated rather than
hidden: resolve-then-connect leaves a DNS rebinding window, the same gap
witness.py has.

/robots.txt is read first and its Disallow rules for * are honoured. A
scanner that ignores robots while grading other people on transparency
would be a poor advertisement for the point being made.
"""

import json
import socket
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0.0"

PUBLIC = {("GET", "report"), ("GET", "list"), ("GET", "spec"), ("GET", "")}

PAGE_PATHS = ("/grade-badge",)

UA = "AILeash-Transparency-Scan/1.0 (+https://sebbi.pro/x/grade/spec)"
TIMEOUT = 8
MAX_BYTES = 262144
CACHE_TTL = 3600

# Files that are genuine public-web standards with an RFC or a long-standing
# convention behind them. Absence here is still not a legal finding, but the
# expectation is at least widely shared.
STANDARDS = [
    ("security_txt", "/.well-known/security.txt", "RFC 9116 security contact"),
    ("robots_txt", "/robots.txt", "crawler directives"),
    ("sitemap_xml", "/sitemap.xml", "site index"),
]

# Files that are emerging AI-transparency conventions. Reported as adoption
# facts, never scored, because nobody is obliged to serve any of them.
CONVENTIONS = [
    ("ai_txt", "/.well-known/ai.txt", "AI system manifest"),
    ("ai_txt_root", "/ai.txt", "AI system manifest at root"),
    ("comply_txt", "/.well-known/comply.txt", "compliance index"),
    ("llms_txt", "/llms.txt", "guidance for language models"),
    ("ai_safety_txt", "/.well-known/ai-safety.txt", "AI-safety declaration"),
]

_patched = [False]
_ready = [False]
_cache = {}


def _setup(ctx):
    if _ready[0]:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS grade_scan("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,domain TEXT,scanned REAL,"
            "findings TEXT,standards_served INTEGER,conventions_served INTEGER,"
            "audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_domain ON grade_scan(domain)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_grade_hash ON grade_scan(audit_hash)")
        ctx["conn"].commit()
    _ready[0] = True


# ----------------------------------------------------------------------
# safety
# ----------------------------------------------------------------------

def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = d.replace("https://", "").replace("http://", "")
    d = d.split("/")[0].split("?")[0].strip().rstrip(".")
    if "@" in d or ":" in d or " " in d:
        return None
    if not d or "." not in d or len(d) > 253:
        return None
    for ch in d:
        if not (ch.isalnum() or ch in ".-"):
            return None
    return d


def _private(ip):
    parts = ip.split(".")
    if len(parts) == 4:
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            return True
        if a == 10 or a == 127 or a == 0:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
        if a == 192 and b == 168:
            return True
        if a == 169 and b == 254:
            return True
        if a == 100 and 64 <= b <= 127:
            return True
        if a >= 224:
            return True
        return False
    low = ip.lower()
    if low in ("::1", "::", "") or low.startswith(("fc", "fd", "fe80", "::ffff:")):
        return True
    return False


def _resolvable(domain):
    try:
        infos = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "dns_failed: " + type(exc).__name__
    for info in infos:
        ip = info[4][0]
        if _private(ip):
            return False, "resolves_to_non_public_address"
    return True, None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _get(url):
    """One request. Returns (status, text, note). Never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener(
        _NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            raw = resp.read(MAX_BYTES + 1)
            truncated = len(raw) > MAX_BYTES
            text = raw[:MAX_BYTES].decode("utf-8", errors="replace")
            return resp.status, text, ("truncated" if truncated else None)
    except urllib.error.HTTPError as exc:
        return exc.code, None, None
    except Exception as exc:
        return None, None, type(exc).__name__


# ----------------------------------------------------------------------
# parsing — every check states exactly what it looked at
# ----------------------------------------------------------------------

def _fields(text):
    """Key: value lines, lowercased keys. Comments and blanks ignored."""
    out = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        if k and k not in out:
            out[k] = v.strip()
    return out


def _check_security(text):
    f = _fields(text)
    return {
        "parses_as_fields": bool(f),
        "has_contact": "contact" in f,
        "has_expires": "expires" in f,
        "expires_value": f.get("expires"),
        "note": ("RFC 9116 requires Contact and Expires. Both presence checks "
                 "above are literal: the field is there or it is not. Whether "
                 "the contact works is not tested."),
    }


def _check_robots(text):
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    directives = [l for l in lines if ":" in l and not l.startswith("#")]
    return {
        "non_empty": bool(lines),
        "directive_lines": len(directives),
        "note": "Presence and shape only. The rules themselves are not judged.",
    }


def _check_sitemap(text):
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(text or "")
        return {"parses_as_xml": True,
                "note": "Parsed as XML. Contents and freshness are not checked."}
    except Exception as exc:
        return {"parses_as_xml": False, "parse_error": type(exc).__name__,
                "note": "Served but did not parse as XML."}


def _check_ai_safety(text):
    """The old version passed if the file contained 'ai-safe:' and the word
    'true' anywhere in it, so 'AI-Safe: false' with 'true' elsewhere passed.
    This reads the field's own value and reports it verbatim."""
    f = _fields(text)
    val = f.get("ai-safe")
    return {
        "has_ai_safe_field": val is not None,
        "ai_safe_value": val,
        "declared_safe": (val.strip().lower() == "true") if val else None,
        "note": ("This reports what the domain declares about itself. A "
                 "self-declaration is not a verification, and nothing here "
                 "checks whether the declaration is true."),
    }


def _check_manifest(text):
    f = _fields(text)
    interesting = ["standard", "domain", "chain-head", "chain-tip-url", "witness-tip",
                   "verify-chain", "consistency-proof", "self-check",
                   "security-contact", "contact", "governance-engine"]
    return {
        "parses_as_fields": bool(f),
        "field_count": len(f),
        "fields_present": [k for k in interesting if k in f],
        "declares_standard": f.get("standard"),
        "note": ("Fields are reported as served. Nothing here follows the URLs "
                 "they contain or verifies any chain they point at."),
    }


def _check_present(text):
    return {"non_empty": bool(text and text.strip()),
            "bytes": len(text or ""),
            "note": "Presence and size only."}


PARSERS = {
    "security_txt": _check_security,
    "robots_txt": _check_robots,
    "sitemap_xml": _check_sitemap,
    "ai_safety_txt": _check_ai_safety,
    "ai_txt": _check_manifest,
    "ai_txt_root": _check_manifest,
    "comply_txt": _check_manifest,
    "llms_txt": _check_present,
}


def _disallowed(robots_text):
    """Paths Disallowed for * in robots.txt. Honoured for every other fetch."""
    blocked = []
    applies = False
    for line in (robots_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "user-agent":
            applies = (v == "*")
        elif k == "disallow" and applies and v:
            blocked.append(v)
    return blocked


def _blocked(path, rules):
    for rule in rules:
        if rule == "/" or path.startswith(rule):
            return True
    return False


# ----------------------------------------------------------------------
# the scan
# ----------------------------------------------------------------------

def _scan(domain):
    base = "https://" + domain
    findings = {}

    status, robots_text, note = _get(base + "/robots.txt")
    rules = _disallowed(robots_text) if status == 200 else []
    findings["robots_txt"] = {
        "path": "/robots.txt", "http_status": status,
        "served": status == 200, "transport_note": note,
        "detail": _check_robots(robots_text) if status == 200 else None,
        "kind": "standard", "description": "crawler directives",
    }

    for key, path, desc in STANDARDS + CONVENTIONS:
        if key == "robots_txt":
            continue
        if _blocked(path, rules):
            findings[key] = {
                "path": path, "served": None, "http_status": None,
                "skipped": "disallowed_by_robots_txt",
                "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
                "description": desc,
                "note": ("This domain's robots.txt disallows it, so it was not "
                         "requested. Not requested is not the same as absent."),
            }
            continue
        st, text, tnote = _get(base + path)
        served = (st == 200 and bool(text and text.strip()))
        findings[key] = {
            "path": path, "http_status": st, "served": served,
            "transport_note": tnote,
            "detail": PARSERS[key](text) if served else None,
            "kind": "standard" if key in [k for k, _, _ in STANDARDS] else "convention",
            "description": desc,
        }

    std_keys = [k for k, _, _ in STANDARDS]
    conv_keys = [k for k, _, _ in CONVENTIONS]
    std_served = sum(1 for k in std_keys if findings.get(k, {}).get("served"))
    conv_served = sum(1 for k in conv_keys if findings.get(k, {}).get("served"))

    return findings, std_served, conv_served


def _summary(domain, findings, std, conv, scanned, receipt=None, block=None):
    return {
        "domain": domain,
        "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(scanned)),
        "standards_served": "%d of %d" % (std, len(STANDARDS)),
        "conventions_served": "%d of %d" % (conv, len(CONVENTIONS)),
        "findings": findings,
        "receipt": receipt,
        "block_index": block,
        "what_this_is": (
            "A record of which public files this domain served at the time of "
            "the scan, and what each one contained. Every check is named and "
            "every result is what the fetch returned."),
        "what_this_is_not": (
            "Not a grade, not a score, and not a statement about whether this "
            "organisation complies with anything. No law requires any of the "
            "files above. Absence of a file is absence of a file."),
        "conventions_disclaimer": (
            "ai.txt and comply.txt are conventions sebbi.pro publishes and helped "
            "shape. A domain not serving them has declined nothing and broken "
            "nothing - it has simply not adopted a format that is not a standard."),
        "if_you_are_the_domain_owner": (
            "This scan requested public files over https and followed your "
            "robots.txt. Nothing was crawled beyond the paths listed. The scan "
            "is sealed, so exactly what was fetched and when is on record and "
            "can be produced. Contact justrightdecorators@gmail.com to have a "
            "scan removed from the public list."),
    }


# ----------------------------------------------------------------------
# badge — cache only, never triggers a fetch of the target
# ----------------------------------------------------------------------

def _badge_svg(label, value, colour):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="260" height="20" '
        'role="img" aria-label="%s %s">'
        '<rect width="176" height="20" fill="#0a0f1e"/>'
        '<rect x="176" width="84" height="20" fill="%s"/>'
        '<text x="88" y="14" fill="#fff" font-family="Verdana,sans-serif" '
        'font-size="10" text-anchor="middle">%s</text>'
        '<text x="218" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" '
        'font-size="10" font-weight="bold" text-anchor="middle">%s</text>'
        '</svg>' % (label, value, colour, label, value))


def _srv():
    import sys
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s, ctx):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_grade_patched", False):
        _patched[0] = True
        return "already installed"

    conn, lock = ctx["conn"], ctx["lock"]
    original = H.do_GET

    def do_GET(self):
        try:
            u = urlparse(self.path)
            p = u.path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            domain = ""
            try:
                q = dict(pair.split("=", 1) for pair in (u.query or "").split("&") if "=" in pair)
                domain = _clean_domain(q.get("domain", "")) or ""
            except Exception:
                domain = ""
            label = "transparency files"
            value, colour = "not scanned", "#6b6353"
            if domain:
                try:
                    with lock:
                        row = conn.execute(
                            "SELECT standards_served,conventions_served FROM grade_scan "
                            "WHERE domain=? ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
                    if row:
                        value = "%d/%d std · %d/%d conv" % (
                            row[0], len(STANDARDS), row[1], len(CONVENTIONS))
                        colour = "#7fe3b0" if row[0] == len(STANDARDS) else "#c9a84c"
                except Exception:
                    pass
            body = _badge_svg(label, value, colour).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._grade_patched = True
    _patched[0] = True
    print("GRADE: /grade-badge installed at runtime", flush=True)
    return "installed"


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _do_scan(ctx, api_key, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required",
                "message": "Send {\"domain\": \"example.com\"}."}, 400

    cached = _cache.get(domain)
    if cached and (time.time() - cached[0]) < CACHE_TTL and not (data or {}).get("force"):
        out = dict(cached[1])
        out["from_cache"] = True
        out["cache_age_seconds"] = int(time.time() - cached[0])
        return out, 200

    ok, why = _resolvable(domain)
    if not ok:
        return {"error": "domain_refused", "domain": domain, "reason": why,
                "message": "Only public, resolvable hosts are scanned."}, 400

    scanned = time.time()
    findings, std, conv = _scan(domain)

    ev = {"user_id": "grade:" + domain, "action": "transparency_scan",
          "amount": 0, "country": "UK", "device_id": "grade",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "SCAN_RECORDED", "score": 0, "grade_version": VERSION,
           "domain": domain, "standards_served": std, "conventions_served": conv,
           "timestamp": scanned,
           "detail": "domain=%s;standards=%d/%d;conventions=%d/%d"
                     % (domain, std, len(STANDARDS), conv, len(CONVENTIONS))}
    try:
        h, idx, seq = ctx["seal"](ev, res, scanned, api_key)
    except Exception as exc:
        return {"error": "seal_failed",
                "detail": type(exc).__name__ + ": " + str(exc)[:250],
                "message": ("The scan ran but was not recorded, so nothing is "
                            "published. A scan nobody can audit is not published "
                            "here.")}, 500
    if not h:
        return {"error": "seal_failed", "detail": "seal returned no hash"}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO grade_scan(domain,scanned,findings,standards_served,"
            "conventions_served,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
            (domain, scanned, json.dumps(findings), std, conv, h, idx))
        ctx["conn"].commit()

    out = _summary(domain, findings, std, conv, scanned, h, idx)
    out["receipt_seq"] = seq
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    out["report"] = "https://sebbi.pro/x/grade/report?domain=" + domain
    _cache[domain] = (scanned, out)
    if len(_cache) > 500:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
            _cache.pop(k, None)
    return out, 200


def _report(ctx, data):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"error": "domain_required"}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT scanned,findings,standards_served,conventions_served,"
            "audit_hash,block_index FROM grade_scan WHERE domain=? "
            "ORDER BY id DESC LIMIT 1", (domain,)).fetchone()
    if not row:
        return {"found": False, "domain": domain,
                "message": "This domain has not been scanned."}, 404
    try:
        findings = json.loads(row[1])
    except Exception:
        findings = {}
    out = _summary(domain, findings, row[2], row[3], row[0], row[4], row[5])
    out["found"] = True
    out["badge"] = "https://sebbi.pro/grade-badge?domain=" + domain
    return out, 200


def _list(ctx, data):
    try:
        limit = min(200, max(1, int((data or {}).get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT domain,MAX(scanned),standards_served,conventions_served "
            "FROM grade_scan GROUP BY domain ORDER BY MAX(scanned) DESC LIMIT ?",
            (limit,)).fetchall()
    return {
        "count": len(rows),
        "scans": [{
            "domain": r[0],
            "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
            "standards_served": "%d of %d" % (r[2], len(STANDARDS)),
            "conventions_served": "%d of %d" % (r[3], len(CONVENTIONS)),
            "report": "/x/grade/report?domain=" + r[0],
        } for r in rows],
        "what_this_list_is": (
            "Domains that have been scanned, with what they served. It is not a "
            "ranking, not a shortlist and not an allegation about anyone on it."),
    }, 200


def _spec():
    return {
        "module": "grade", "version": VERSION,
        "question": "Which public transparency files does this domain serve, and what is in them?",
        "standards_checked": [{"key": k, "path": p, "what": d} for k, p, d in STANDARDS],
        "conventions_checked": [{"key": k, "path": p, "what": d} for k, p, d in CONVENTIONS],
        "no_grade": (
            "This module issues no letter, no score and no verdict, and the word "
            "compliant appears nowhere in its output. Half of these files are "
            "conventions rather than requirements, two of them are conventions "
            "sebbi.pro helped write, and grading strangers against your own "
            "format would be marking their homework with your marking scheme."),
        "absence": (
            "A file that is not served is reported as not served. That is a fact "
            "about a file and never a finding about a company."),
        "self_declarations": (
            "Where a file declares something about the domain - ai-safe: true, a "
            "chain head, a standard version - the declaration is reported "
            "verbatim and is never treated as verified. Nothing here follows the "
            "URLs a manifest contains."),
        "how_it_fetches": {
            "scheme": "https only, port 443",
            "redirects": "not followed",
            "timeout_seconds": TIMEOUT,
            "max_bytes_per_file": MAX_BYTES,
            "address_check": ("DNS resolved and rejected if it points at private, "
                              "loopback, link-local, multicast or reserved space"),
            "known_limit": ("resolve-then-connect leaves a DNS rebinding window; "
                            "stated rather than hidden"),
            "robots": "/robots.txt is read first and Disallow rules for * are honoured",
            "user_agent": UA,
        },
        "badge": {
            "url": "https://sebbi.pro/grade-badge?domain=example.com",
            "behaviour": ("renders from the stored scan only and never fetches the "
                          "target, so embedding it cannot point traffic at anyone"),
        },
        "every_scan_is_sealed": (
            "Each scan is written into the audit chain with its receipt, so a "
            "domain owner who objects can be shown exactly what was requested "
            "and when."),
        "auth": "scan is keyed. report, list, spec and the badge are public.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    s = _srv()
    if s is not None and not _patched[0]:
        try:
            _install(s, ctx)
        except Exception as exc:
            print("GRADE: patch failed - " + str(exc), flush=True)

    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "scan":
            if not api_key:
                return {"error": "api_key_required",
                        "message": ("Scanning fetches somebody else's server, so it "
                                    "is keyed and attributable. Reading results is "
                                    "public.")}, 401
            return _do_scan(ctx, api_key, data)
        return {"error": "unknown_action", "action": action, "POST": ["scan"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "report":
        return _report(ctx, data)
    if action == "list":
        return _list(ctx, data)
    if action == "status":
        return {"module": "grade", "version": VERSION,
                "badge_installed": bool(_patched[0]),
                "cached_domains": len(_cache)}, 200
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "report", "list", "status"], "POST": ["scan"]}, 404

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


## `modules/held.py`

145 lines, 5162 bytes

```python
"""
modules/held.py  v1.0  -  the tips sebbi.pro holds for other chains

Every time a peer submits its tip, sebbi.pro seals the observation into its
own chain as a block under user_id "wit:<peer>", with the peer's tip inside.
Those blocks are already public in the walk. This module lists them per
peer, so another chain can point a verifier at sebbi.pro as its witness and
have a machine confirm it.

Reads only. Seals nothing, writes nothing, creates no tables. All public.

Routes:
  https://sebbi.pro/x/held/status
  https://sebbi.pro/x/held/peers
  https://sebbi.pro/x/held/tips?peer=mir
"""

import json
import re
import time

VERSION = "1.0"
BASE = "https://sebbi.pro/x/held/"
DEFAULT_LIMIT = 100
MAX_LIMIT = 500

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "peers"),
          ("GET", "tips")}

_PEER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _q(data, name, default=None):
    v = (data or {}).get(name, default)
    if isinstance(v, list):
        v = v[0] if v else default
    return v


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except Exception:
        return None


def _peers(ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT user_id, COUNT(*), MAX(id), MAX(ts) FROM audit_log "
            "WHERE user_id LIKE 'wit:%' GROUP BY user_id").fetchall()
    out = []
    for uid, n, last_idx, last_ts in rows:
        name = str(uid)[4:]
        out.append({"peer": name, "tips_held": n,
                    "last_block_index": last_idx,
                    "last_observed_at": _iso(last_ts),
                    "list": BASE + "tips?peer=" + name})
    out.sort(key=lambda r: -(r["tips_held"] or 0))
    return {"ok": True, "holder": "sebbi.pro", "count": len(out),
            "peers": out}, 200


def _tips(data, ctx):
    peer = str(_q(data, "peer", "") or "").strip().lower()
    if not _PEER_RE.match(peer):
        return {"ok": False, "error": "peer_required",
                "example": BASE + "tips?peer=mir",
                "peers": BASE + "peers"}, 400
    try:
        limit = max(1, min(MAX_LIMIT, int(_q(data, "limit", DEFAULT_LIMIT))))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    conn, lock = ctx["conn"], ctx["lock"]
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            ("wit:" + peer, limit)).fetchall()
    tips = []
    for idx, ts, h, rj in rows:
        try:
            res = json.loads(rj)
        except Exception:
            res = {}
        tip = str(res.get("peer_tip") or "").lower()
        if not re.match(r"^[0-9a-f]{64}$", tip):
            continue
        tips.append({
            "peer_tip": tip,
            "observed_at": _iso(ts),
            "liveness": res.get("liveness"),
            "sealed_in_block": idx,
            "sealed_block_hash": h,
            "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
        })
    return {
        "ok": True,
        "holder": "sebbi.pro",
        "peer": peer,
        "count": len(tips),
        "newest_first": True,
        "tips": tips,
        "what_this_proves": (
            "sebbi.pro recorded each of these tips from %s and sealed the "
            "observation into its own public chain. Open check_block to see "
            "the sealed block, recompute its hash, and confirm peer_tip is "
            "inside it. sebbi.pro is run independently of %s and cannot be "
            "made to rewrite these blocks by %s." % (peer, peer, peer)),
        "what_this_does_not_prove": (
            "That the tip was correct when submitted - only that this is the "
            "tip sebbi.pro was shown, and when."),
    }, 200


def _status():
    return {"ok": True, "module": "held", "version": VERSION,
            "what": "Tips sebbi.pro holds for other chains, from its own "
                    "sealed witness blocks.",
            "routes": {"peers": BASE + "peers",
                       "tips": BASE + "tips?peer=mir",
                       "status": BASE + "status"},
            "use_as_witness": "In an AI Integrity Declaration, set a "
                              "witness tip_endpoint to " + BASE +
                              "tips?peer=<your peer name>. The checker at "
                              "https://sebbi.pro/x/integrity/check then "
                              "confirms sebbi.pro holds your tip."}


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action in ("status", "spec", ""):
            return _status(), 200
        if method == "GET" and action == "peers":
            return _peers(ctx)
        if method == "GET" and action == "tips":
            return _tips(data, ctx)
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": []}, 404
    except Exception as exc:
        return {"ok": False, "error": "held_failed",
                "detail": str(exc)[:200]}, 500

```


## `modules/homelink.py`

134 lines, 4758 bytes

```python
"""
modules/homelink.py  v1.1.0
Adds the "Machine readable" and "Agent Passport" buttons to the sebbi.pro homepage without
editing index.html or server.py.

Page module, same family as map.py: a runtime do_GET patch. For the homepage
only ("/" and "/index.html") it lets the normal handler build the page into a
buffer, inserts one small fixed button before </body>, corrects the
Content-Length, and sends it on. If anything about the response is not a plain
200 HTML page with a </body> tag, the original bytes are sent untouched - the
homepage can never be broken by this module, only left as it was.

Armed by hitting /x/homelink/status once after each deploy.
"""

import io
import sys

VERSION = "1.1.0"
PATHS = ("/", "/index.html")
MARK = b"<!--sebbi-homelink-->"

BUTTON = (
    b'<!--sebbi-homelink--><div id="sebbi-homelink" style="position:fixed;right:16px;'
    b'bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;display:flex;'
    b'flex-direction:column;align-items:flex-end;gap:10px">'
    b'<a href="/prove" style="display:flex;align-items:center;gap:8px;background:#0a0f1e;'
    b'color:#fff;border:1.5px solid #7fe3b0;border-radius:999px;padding:10px 16px;'
    b'font:500 13px/1 \'IBM Plex Mono\',ui-monospace,monospace;text-decoration:none;'
    b'box-shadow:0 6px 24px rgba(0,0,0,.35)"><span style="background:#7fe3b0;color:#0a0f1e;'
    b'border-radius:999px;padding:3px 7px;font-size:10.5px;letter-spacing:.05em">PROOF</span>'
    b'Machine readable &rarr;</a>'
    b'<a href="/passport" style="display:flex;align-items:center;gap:8px;background:#0a0f1e;'
    b'color:#fff;border:1.5px solid #c9a84c;border-radius:999px;padding:10px 16px;'
    b'font:500 13px/1 \'IBM Plex Mono\',ui-monospace,monospace;text-decoration:none;'
    b'box-shadow:0 6px 24px rgba(0,0,0,.35)"><span style="background:#c9a84c;color:#0a0f1e;'
    b'border-radius:999px;padding:3px 7px;font-size:10.5px;letter-spacing:.05em">NEW</span>'
    b'Agent Passport &rarr;</a></div>'
)

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


def _inject(raw):
    """Return modified response bytes, or None to send the original."""
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or b" 200" not in lines[0]:
        return None
    lower = head.lower()
    if b"text/html" not in lower or b"content-encoding" in lower or b"chunked" in lower:
        return None
    if MARK in body:
        return None
    at = body.rfind(b"</body>")
    if at < 0:
        return None
    new_body = body[:at] + BUTTON + body[at:]
    out = []
    for ln in lines:
        if ln.lower().startswith(b"content-length:"):
            ln = b"Content-Length: " + str(len(new_body)).encode()
        out.append(ln)
    return b"\r\n".join(out) + b"\r\n\r\n" + new_body


def _install(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_homelink_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0]
        if path not in PATHS:
            return original_do_GET(self)
        real = self.wfile
        buf = io.BytesIO()
        self.wfile = buf
        try:
            original_do_GET(self)
            if hasattr(self, "_headers_buffer") and self._headers_buffer:
                self.flush_headers()
        finally:
            self.wfile = real
        raw = buf.getvalue()
        try:
            changed = _inject(raw)
        except Exception:
            changed = None
        real.write(changed if changed is not None else raw)

    cls.do_GET = do_GET
    cls._homelink_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    return ({"module": "homelink", "version": VERSION, "armed": armed,
             "adds": "Machine readable (/prove) and Agent Passport (/passport) buttons on the homepage",
             "safe": "any response that is not a plain 200 HTML page is sent untouched"}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
