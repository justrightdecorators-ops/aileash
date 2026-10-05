"""
modules/roundlyverify.py  v1.0.0

Serves the Roundly domain-verification token at
    https://sebbi.pro/.well-known/roundly-verification.txt

Roundly (roundly.vc) proves a founder controls the company website by
fetching that file and checking it contains the token shown in the
founder workspace. This module serves exactly that token as plain text.

Same runtime do_GET patch as packconsole.py: it adds one path and passes
everything else straight through to whatever was there before. server.py
is not touched.

After a deploy, arm it like everything else:
    https://sebbi.pro/x/arm/status
or on its own:
    https://sebbi.pro/x/roundlyverify/status
"""

import sys
from urllib.parse import urlparse

VERSION = "1.0.0"

PUBLIC = {("GET", "status")}

TOKEN = "roundly-verify-465301e3d69cf82e47acec2f117f6ccc"

PAGE_PATHS = ("/.well-known/roundly-verification.txt",)

_patched = [False]


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
    if getattr(H, "_roundlyverify_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = (TOKEN + "\n").encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._roundlyverify_patched = True
    _patched[0] = True
    print("ROUNDLYVERIFY: /.well-known/roundly-verification.txt installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found", "armed": False}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("ROUNDLYVERIFY: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {"module": "roundlyverify",
                "version": VERSION,
                "armed": bool(_patched[0]),
                "install_result": state,
                "serves": "https://sebbi.pro/.well-known/roundly-verification.txt"}, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404
