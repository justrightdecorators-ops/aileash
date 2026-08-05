"""
modules/standard.py  -  publishes the Ordering Test from this domain

WHAT IT SERVES
--------------
  GET /ordering-test.py                   the runner itself, as plain text
  GET /.well-known/ordering-test.json     this vendor's discovery document
  GET /x/standard/hash                    sha256 of the file we are serving
  GET /x/standard/status                  whether the route is installed

WHY IT IS SERVED FROM HERE RATHER THAN A REPOSITORY
---------------------------------------------------
The specification is mirrored on the domain of every operator who authors it.
That is deliberate. A standard that lives in one vendor's repository is that
vendor's product with a neutral name on it. Served identically from several
independent domains, with a published digest anyone can compare, it belongs to
none of them - and a divergence between mirrors is visible rather than
arguable.

/x/standard/hash exists for exactly that. Fetch it from each mirror and compare.
If they differ, one operator has edited the standard unilaterally, and you can
prove it without asking either of them.

THE DISCOVERY DOCUMENT
----------------------
This is how this platform takes the test rather than only publishing it. Every
endpoint listed is public - no key, no account - so an auditor can run the
whole thing from their own machine without our permission or knowledge.

One check is deliberately not listed. Rule binding has no public endpoint here
yet, so it will report NOT SUPPORTED rather than passing. That is the honest
result and it stays that way until the endpoint exists. A test whose authors
score full marks on the day they publish it is not a test.
"""

import hashlib
import json
import os
import sys
import time

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "hash"), ("GET", "spec")}

FILE_PATHS = ("/ordering-test.py", "/ordering_test.py")
DISCOVERY_PATHS = ("/.well-known/ordering-test.json",)

# The runner sits in the repository root, one level above modules/.
SOURCE_CANDIDATES = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "ordering_test.py"),
    os.path.join(os.getcwd(), "ordering_test.py"),
    "/app/ordering_test.py",
]

VENDOR = "AILeash / Monop Content"
BASE = "https://sebbi.pro"

# Every endpoint here is public. An auditor needs nothing from us to run this.
DISCOVERY = {
    "ordering_test_version": "0.1",
    "vendor": VENDOR,
    "runner": BASE + "/ordering-test.py",
    "runner_digest": BASE + "/x/standard/hash",
    "endpoints": {
        "oversight_open":    "/x/demo/review",
        "oversight_commit":  "/x/demo/commit",
        "period_root":       "/x/complete/root?period={period}",
        "absence_proof":     "/x/complete/prove?value={value}",
        "inclusion_proof":   "/x/complete/prove?leaf={leaf}",
        "consistency_proof": "/x/consistency/proof?first={first}&second={second}",
        "replay":            "/x/replay/challenge",
        "anchor_status":     "/api/anchor-status",
        "witness_peers":     "/x/witness/peers",
    },
    "not_published": {
        "rule_binding": ("No public endpoint yet. This check will report NOT "
                         "SUPPORTED against us, which is the accurate result "
                         "until it exists."),
    },
    "note": ("All endpoints listed are public. Run the test yourself without "
             "asking us. Compare /x/standard/hash against the other mirrors "
             "before trusting the runner you downloaded."),
}

_patched = [False]
_cache = {"text": None, "digest": None, "read_at": 0, "path": None}
CACHE_SECONDS = 60


def _load():
    """Read the runner off disk. Cached briefly so a deploy is picked up
    without a restart, and a missing file is reported rather than hidden."""
    now = time.time()
    if _cache["text"] is not None and now - _cache["read_at"] < CACHE_SECONDS:
        return _cache["text"], _cache["digest"], None
    for path in SOURCE_CANDIDATES:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                text = handle.read()
        except Exception:
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        _cache.update({"text": text, "digest": digest, "read_at": now, "path": path})
        return text, digest, None
    return None, None, ("ordering_test.py was not found in the deployment. "
                        "It belongs in the repository root, alongside server.py.")


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_standard_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def _send(self, body, content_type, extra=None):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        try:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)
        except Exception:
            pass

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in FILE_PATHS:
            text, digest, error = _load()
            if error:
                _send(self, json.dumps({"error": "runner_unavailable",
                                        "message": error}, indent=2),
                      "application/json; charset=utf-8")
                return
            _send(self, text, "text/plain; charset=utf-8",
                  {"X-Ordering-Test-SHA256": digest,
                   "Content-Disposition": 'inline; filename="ordering_test.py"'})
            return

        if p in DISCOVERY_PATHS:
            _send(self, json.dumps(DISCOVERY, indent=2),
                  "application/json; charset=utf-8")
            return

        return original(self)

    H.do_GET = do_GET
    H._standard_patched = True
    _patched[0] = True
    print("STANDARD: /ordering-test.py and discovery document installed", flush=True)
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
            print("STANDARD: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()
    text, digest, error = _load()

    if method == "GET" and action == "hash":
        if error:
            return {"error": "runner_unavailable", "message": error}, 503
        return {
            "file": "ordering_test.py",
            "sha256": digest,
            "bytes": len(text.encode("utf-8")),
            "served_from": BASE + "/ordering-test.py",
            "why": ("Fetch this from every mirror and compare. Identical digests "
                    "mean every operator is serving the same specification. A "
                    "difference means one of them has changed it on their own, "
                    "and you can demonstrate that without asking any of them."),
        }, 200

    if method == "GET" and action in ("", "status", "spec"):
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "version": VERSION,
            "serving": list(FILE_PATHS) + list(DISCOVERY_PATHS),
            "runner_found": error is None,
            "runner_error": error,
            "runner_sha256": digest,
            "discovery": DISCOVERY,
            "how_to_run": "python3 ordering_test.py " + BASE,
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status", "hash"]}, 404
