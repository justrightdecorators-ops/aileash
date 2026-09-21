"""
modules/homelink.py  v1.0.0
Adds a "NEW - Agent Passport" button to the sebbi.pro homepage without
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

VERSION = "1.0.0"
PATHS = ("/", "/index.html")
MARK = b"<!--sebbi-homelink-->"

BUTTON = (
    b'<!--sebbi-homelink--><a href="/passport" id="sebbi-homelink" '
    b'style="position:fixed;right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;display:flex;align-items:center;gap:8px;'
    b'background:#0a0f1e;color:#fff;border:1.5px solid #c9a84c;border-radius:999px;'
    b'padding:10px 16px;font:500 13px/1 \'IBM Plex Mono\',ui-monospace,monospace;'
    b'text-decoration:none;box-shadow:0 6px 24px rgba(0,0,0,.35)">'
    b'<span style="background:#c9a84c;color:#0a0f1e;border-radius:999px;padding:3px 7px;'
    b'font-size:10.5px;letter-spacing:.05em">NEW</span>Agent Passport &rarr;</a>'
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
             "adds": "NEW - Agent Passport button on the homepage, linking to /passport",
             "safe": "any response that is not a plain 200 HTML page is sent untouched"}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
