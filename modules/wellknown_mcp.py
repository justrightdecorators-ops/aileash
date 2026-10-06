"""
modules/wellknown_mcp.py  v1.0.0
Serve the domain-ownership proof for the official MCP Registry.

The open MCP Registry (registry.modelcontextprotocol.io) lets you claim the
domain namespace "pro.sebbi/*" if you can prove you own sebbi.pro. The HTTP
proof method is a single file at:

    https://sebbi.pro/.well-known/mcp-registry-auth

containing one line with this domain's Ed25519 public key. The mcp-publisher
CLI then signs the claim with the matching private key (kept secret, never in
this repo) and the registry fetches this file to check them against each other.

This module only adds that one route. It touches nothing else - server.py and
every other module are untouched.

Arm with everything:  https://sebbi.pro/x/arm/status
Check it:             https://sebbi.pro/.well-known/mcp-registry-auth
"""

import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

AUTH_PATH = "/.well-known/mcp-registry-auth"
# Public key for sebbi.pro. The private half is NOT in this repo.
AUTH_BODY = b"v=MCPv1; k=ed25519; p=8jH4kyx5WD3ASq3kWwUvv3FBqNWX7Lga/OJnVjh9KRk=\n"

_state = {"installed": False, "last_error": None}


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _install():
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is None:
        return False
    if getattr(H, "_wellknown_mcp", False):
        return True
    orig_get = H.do_GET

    def do_GET(self):
        try:
            p = self.path.split("?")[0].rstrip("/") if self.path != "/" else self.path
        except Exception:
            p = self.path
        if p == AUTH_PATH:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(AUTH_BODY)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if getattr(self, "command", "GET") != "HEAD":
                self.wfile.write(AUTH_BODY)
            return
        return orig_get(self)

    H.do_GET = do_GET
    H._wellknown_mcp = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _state["installed"] = _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    if action == "spec":
        return {"module": "wellknown_mcp", "version": VERSION, "path": AUTH_PATH,
                "serves": AUTH_BODY.decode().strip()}, 200
    return ({"module": "wellknown_mcp", "version": VERSION, "armed": _state["installed"],
             "url": "https://sebbi.pro/.well-known/mcp-registry-auth",
             "last_error": _state["last_error"]}, 200)
