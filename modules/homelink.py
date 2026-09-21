"""
modules/homelink.py  v1.3.0
Adds the "Deep Run", "Agent Room", "Machine readable" and "Agent Passport" buttons to the sebbi.pro homepage without
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

VERSION = "1.3.0"
PATHS = ("/", "/index.html")
MARK = b"<!--sebbi-homelink-->"

BUTTON = (
    b'<!--sebbi-homelink--><style>@keyframes sbspin{to{transform:rotate(360deg)}}'
    b'@keyframes sbpulse{0%,100%{box-shadow:0 0 14px rgba(74,163,255,.55),0 6px 24px rgba(0,0,0,.4)}'
    b'50%{box-shadow:0 0 28px rgba(201,168,76,.8),0 6px 24px rgba(0,0,0,.4)}}'
    b'#sebbi-homelink a{display:flex;align-items:center;gap:8px;background:#0a0f1e;color:#fff;'
    b'border-radius:999px;padding:10px 16px;font:500 13px/1 \'IBM Plex Mono\',ui-monospace,monospace;'
    b'text-decoration:none;box-shadow:0 6px 24px rgba(0,0,0,.35)}'
    b'#sebbi-homelink .tag{border-radius:999px;padding:3px 7px;font-size:10.5px;letter-spacing:.05em;color:#0a0f1e}'
    b'#sebbi-homelink .portal{position:relative;border:0;padding:12px 18px 12px 12px;animation:sbpulse 2.4s infinite}'
    b'#sebbi-homelink .portal:before{content:"";position:absolute;inset:-2px;border-radius:999px;z-index:-1;'
    b'background:conic-gradient(from 0deg,#c9a84c,#7fe3b0,#4aa3ff,#c9a84c)}'
    b'#sebbi-homelink .ring{width:22px;height:22px;border-radius:50%;flex:none;'
    b'background:conic-gradient(#c9a84c,#7fe3b0,#4aa3ff,#c9a84c);animation:sbspin 1.4s linear infinite;'
    b'-webkit-mask:radial-gradient(circle,transparent 45%,#000 50%);mask:radial-gradient(circle,transparent 45%,#000 50%)}'
    b'</style><div id="sebbi-homelink" style="position:fixed;right:16px;'
    b'bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;display:flex;'
    b'flex-direction:column;align-items:flex-end;gap:10px">'
    b'<a href="/game" style="border:1.5px solid #d59bff"><span class="tag" style="background:#d59bff">'
    b'PLAY</span>Deep Run &#9654;</a>'
    b'<a class="portal" href="/room"><span class="ring"></span>Enter the Agent Room &rarr;</a>'
    b'<a href="/prove" style="border:1.5px solid #7fe3b0"><span class="tag" style="background:#7fe3b0">'
    b'PROOF</span>Machine readable &rarr;</a>'
    b'<a href="/passport" style="border:1.5px solid #c9a84c"><span class="tag" style="background:#c9a84c">'
    b'NEW</span>Agent Passport &rarr;</a></div>'
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
             "adds": "Deep Run (/game), Agent Room (/room), Machine readable (/prove) and Agent Passport (/passport) buttons",
             "safe": "any response that is not a plain 200 HTML page is sent untouched"}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
