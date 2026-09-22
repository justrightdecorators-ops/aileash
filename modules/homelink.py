"""
modules/homelink.py  v1.7.0
Adds the "Auditors", "Cinema", "Deep Run", "Agent Room", "Machine readable" and "Agent Passport" buttons to the sebbi.pro homepage without
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

VERSION = "1.7.0"
PATHS = ("/", "/index.html")
MARK = b"<!--sebbi-homelink-->"

BUTTON = (
    b'<!--sebbi-homelink--><style>@keyframes sbspin{to{transform:rotate(360deg)}}'
    b'@keyframes sbpulse{0%,100%{box-shadow:0 0 12px rgba(74,163,255,.55),0 5px 18px rgba(0,0,0,.4)}'
    b'50%{box-shadow:0 0 22px rgba(201,168,76,.8),0 5px 18px rgba(0,0,0,.4)}}'
    b'@keyframes sbfloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}'
    b'#sebbi-homelink{position:fixed;right:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:8px}'
    b'#sebbi-homelink a{display:flex;align-items:center;gap:7px;background:#0a0f1e;color:#fff;'
    b'border-radius:999px;padding:8px 13px;font:500 12px/1 \'IBM Plex Mono\',ui-monospace,monospace;'
    b'text-decoration:none;box-shadow:0 5px 18px rgba(0,0,0,.35)}'
    b'#sebbi-homelink .tag{border-radius:999px;padding:3px 6px;font-size:9.5px;letter-spacing:.05em;color:#0a0f1e}'
    b'#sebbi-homelink .portal{position:relative;border:0;padding:9px 15px 9px 10px;animation:sbpulse 2.4s infinite}'
    b'#sebbi-homelink .portal:before{content:"";position:absolute;inset:-2px;border-radius:999px;z-index:-1;'
    b'background:conic-gradient(from 0deg,#c9a84c,#7fe3b0,#4aa3ff,#c9a84c)}'
    b'#sebbi-homelink .ring{width:18px;height:18px;border-radius:50%;flex:none;'
    b'background:conic-gradient(#c9a84c,#7fe3b0,#4aa3ff,#c9a84c);animation:sbspin 1.4s linear infinite;'
    b'-webkit-mask:radial-gradient(circle,transparent 45%,#000 50%);mask:radial-gradient(circle,transparent 45%,#000 50%)}'
    b'#sebbi-homelink .x{width:30px;height:30px;padding:0;justify-content:center;border:1px solid rgba(255,255,255,.3);'
    b'font-size:14px;cursor:pointer}'
    b'#sebbi-bubble{display:none;position:fixed;right:18px;bottom:calc(18px + env(safe-area-inset-bottom,0px));'
    b'z-index:2147483000;width:62px;height:62px;border-radius:50%;cursor:pointer;animation:sbfloat 3.2s ease-in-out infinite;'
    b'background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.95) 0,rgba(255,255,255,.35) 12%,rgba(143,208,255,.35) 30%,'
    b'rgba(201,168,76,.35) 62%,rgba(10,15,30,.55) 100%);'
    b'box-shadow:inset -8px -10px 18px rgba(10,15,30,.55),inset 6px 6px 14px rgba(255,255,255,.35),'
    b'0 10px 26px rgba(0,0,0,.45),0 0 24px rgba(143,208,255,.35);border:1px solid rgba(255,255,255,.35);'
    b'display:none;align-items:center;justify-content:center;font:600 11px \'IBM Plex Mono\',monospace;color:#fff;'
    b'text-shadow:0 1px 4px rgba(0,0,0,.6)}'
    b'#sebbi-tools{position:fixed;left:14px;bottom:calc(14px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'display:none;flex-direction:column;align-items:flex-start;gap:8px}'
    b'#sebbi-tools a{display:flex;align-items:center;gap:7px;background:#0a0f1e;color:#fff;border-radius:999px;'
    b'padding:8px 13px;font:500 12px/1 \'IBM Plex Mono\',ui-monospace,monospace;text-decoration:none;'
    b'box-shadow:0 5px 18px rgba(0,0,0,.35);border:1.5px solid rgba(255,255,255,.2)}'
    b'#sebbi-tools a.x{width:30px;height:30px;padding:0;justify-content:center;font-size:14px}'
    b'#sebbi-toolbubble{position:fixed;left:18px;bottom:calc(18px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'width:62px;height:62px;border-radius:50%;cursor:pointer;animation:sbfloat 3.6s ease-in-out infinite;'
    b'background:radial-gradient(circle at 32% 28%,rgba(255,255,255,.95) 0,rgba(255,255,255,.35) 12%,rgba(127,227,176,.4) 30%,'
    b'rgba(213,155,255,.35) 62%,rgba(10,15,30,.55) 100%);'
    b'box-shadow:inset -8px -10px 18px rgba(10,15,30,.55),inset 6px 6px 14px rgba(255,255,255,.35),'
    b'0 10px 26px rgba(0,0,0,.45),0 0 24px rgba(127,227,176,.35);border:1px solid rgba(255,255,255,.35);'
    b'display:flex;align-items:center;justify-content:center;font:600 11px \'IBM Plex Mono\',monospace;color:#fff;'
    b'text-shadow:0 1px 4px rgba(0,0,0,.6)}'
    b'</style>'
    b'<div id="sebbi-toolbubble" onclick="this.style.display=\'none\';document.getElementById(\'sebbi-tools\').style.display=\'flex\'">'
    b'tools</div>'
    b'<div id="sebbi-tools">'
    b'<a class="x" href="#" aria-label="Close" onclick="event.preventDefault();this.parentNode.style.display=\'none\';'
    b'document.getElementById(\'sebbi-toolbubble\').style.display=\'flex\'">&times;</a>'
    b'<a href="/tools#meter" style="border-color:#7fe3b0"><span class="tag" style="background:#7fe3b0">01</span>Token Meter</a>'
    b'<a href="/tools#lens" style="border-color:#c9a84c"><span class="tag" style="background:#c9a84c">02</span>Receipt Lens</a>'
    b'<a href="/tools#shield" style="border-color:#ff8a80"><span class="tag" style="background:#ff8a80">03</span>Prompt Shield</a>'
    b'<a href="/tools#guard" style="border-color:#8fd0ff"><span class="tag" style="background:#8fd0ff">04</span>Spend Guard</a>'
    b'<a href="/tools#badge" style="border-color:#d59bff"><span class="tag" style="background:#d59bff">05</span>Proof Badge</a>'
    b'<a href="/tools" style="border-color:rgba(255,255,255,.35)">All free tools &rarr;</a>'
    b'</div>'
    b'<a id="sebbi-start" href="/start" style="position:fixed;left:12px;top:calc(12px + env(safe-area-inset-top,0px));'
    b'z-index:2147483000;display:flex;align-items:center;gap:7px;background:rgba(10,15,30,.9);color:#fff;'
    b'border:1.5px solid #c9a84c;border-radius:999px;padding:7px 12px 7px 8px;font:600 11.5px/1 \'IBM Plex Mono\',monospace;'
    b'text-decoration:none;box-shadow:0 0 18px rgba(201,168,76,.45)">'
    b'<span style="width:16px;height:16px;border-radius:50%;background:conic-gradient(#c9a84c,#7fe3b0,#4aa3ff,#c9a84c);'
    b'animation:sbspin 1.4s linear infinite;-webkit-mask:radial-gradient(circle,transparent 42%,#000 48%);'
    b'mask:radial-gradient(circle,transparent 42%,#000 48%)"></span>START HERE &rarr;</a>'
    b'<div id="sebbi-bubble" onclick="this.style.display=\'none\';document.getElementById(\'sebbi-homelink\').style.display=\'flex\'">'
    b'sebbi</div>'
    b'<div id="sebbi-homelink">'
    b'<a class="x" href="#" aria-label="Close" onclick="event.preventDefault();this.parentNode.style.display=\'none\';'
    b'var b=document.getElementById(\'sebbi-bubble\');b.style.display=\'flex\'">&times;</a>'
    b'<a href="/auditors" style="background:#c9a84c;color:#0a0f1e;border:0;font-weight:700;'
    b'box-shadow:0 0 24px rgba(201,168,76,.5),0 5px 18px rgba(0,0,0,.4)">&#9878; AUDITORS &rarr;</a>'
    b'<a href="/cinema" style="border:1.5px solid #8fd0ff"><span class="tag" style="background:#8fd0ff">WATCH</span>Cinema &#127916;</a>'
    b'<a href="/game" style="border:1.5px solid #d59bff"><span class="tag" style="background:#d59bff">PLAY</span>Deep Run &#9654;</a>'
    b'<a class="portal" href="/room"><span class="ring"></span>Enter the Agent Room &rarr;</a>'
    b'<a href="/prove" style="border:1.5px solid #7fe3b0"><span class="tag" style="background:#7fe3b0">PROOF</span>Machine readable &rarr;</a>'
    b'<a href="/passport" style="border:1.5px solid #c9a84c"><span class="tag" style="background:#c9a84c">NEW</span>Agent Passport &rarr;</a>'
    b'</div>'
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
             "adds": "Free tools bubble (/tools, bottom left), Start here (/start, top left), Auditors (/auditors), Cinema (/cinema), Deep Run (/game), Agent Room (/room), Machine readable (/prove) and Agent Passport (/passport) buttons",
             "safe": "any response that is not a plain 200 HTML page is sent untouched"}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
