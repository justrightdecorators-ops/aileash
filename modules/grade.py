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
