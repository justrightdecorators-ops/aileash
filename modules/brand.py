"""
modules/brand.py  v1.0.0  -  one brand on every page: Monop Content

    Arm:  https://sebbi.pro/x/brand/status   (also armed by /x/arm/status)

The pages carry the founder's name and town in footers, taglines, buttons and
form placeholders. This presents them as Monop Content instead, without
editing a single page file: every HTML response is rewritten on its way out
of the server, whichever file or module produced it.

HOW
---
It wraps the request handler's handle_one_request, so it sits outside every
page patch whatever order modules were armed in. The response is held only
until its headers show what it is: anything that is not HTML (JSON, images,
video, downloads, event streams) is passed straight through untouched and
unbuffered. HTML is rewritten and its Content-Length corrected.

LEFT AS THEY ARE, ON PURPOSE
----------------------------
  /terms, /data-protection, /risk-policy, /human-oversight   the law and auditors
      expect the privacy notice and policies to name who is responsible
  /investor-prospectus                                investors expect the founder
  /admin, /console and other operator screens         your own tools

To switch it off without a deploy: https://sebbi.pro/x/brand/off
(back on with /x/brand/on). Both need your API key.
"""

import sys
import threading

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec")}

# Longest and most specific first, so a shorter rule never splits a longer one.
RULES = [
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; ",
     "&copy; 2026 Monop Content &middot; "),
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK", "&copy; 2026 Monop Content"),
    ("built by Monop Content in Blyth, United Kingdom", "built by Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content · Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland", "Monop Content"),
    ("Monop Content &middot; Blyth, UK", "Monop Content"),
    ("Monop Content · Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth", "Monop Content"),
    (" &middot; Blyth, Northumberland, UK", ""),
    (" &middot; Blyth, UK", ""),
    (" · Blyth, UK", ""),
    (" &middot; Justin Antony Dobson", ""),
    (" · Justin Antony Dobson", ""),
    ("Contact Justin at Monop Content", "Contact Monop Content"),
    ("Contact Justin", "Contact us"),
    ("talk to Justin", "talk to us"),
    ("Justin has been notified", "Our team has been notified"),
    ('placeholder="Justin Antony Dobson"', 'placeholder="Your full name"'),
    ('placeholder="Justin"', 'placeholder="First name"'),
    ("Building tamper-evident AI compliance from Blyth.", "Building tamper-evident AI compliance."),
]
RULES_B = [(a.encode("utf-8"), b.encode("utf-8")) for a, b in RULES]

SKIP_PATHS = ("/terms", "/data-protection", "/risk-policy", "/human-oversight", "/investor-prospectus",
              "/admin", "/console", "/peers", "/pack", "/lineage-desk")

_state = {"installed": False, "on": True, "rewritten": 0, "replacements": 0, "last_error": None}
_lock = threading.Lock()


def rewrite(body):
    n = 0
    for old, new in RULES_B:
        if old in body:
            n += body.count(old)
            body = body.replace(old, new)
    return body, n


class _Out(object):
    """Stands in for wfile for one request. Passes non-HTML straight through."""

    def __init__(self, real):
        self.real = real
        self.buf = bytearray()
        self.mode = None  # None = reading headers, "pass", "html"

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            if b"content-type: text/html" in head and b"content-encoding" not in head:
                self.mode = "html"
            else:
                self._go_pass()
        elif len(self.buf) > 8 * 1024 * 1024:
            self._go_pass()  # an enormous page is sent as it is rather than held
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if self.mode != "html" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        new_body, n = rewrite(body)
        if n:
            lines = head.split(b"\r\n")
            lines = [l for l in lines if not l.lower().startswith(b"content-length:")]
            lines.append(b"Content-Length: " + str(len(new_body)).encode())
            head = b"\r\n".join(lines)
            _state["rewritten"] += 1
            _state["replacements"] += n
        self.real.write(head + b"\r\n\r\n" + new_body)
        try:
            self.real.flush()
        except Exception:
            pass


def _handler_class():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return getattr(m, "Handler", None)


def _install():
    with _lock:
        if _state["installed"]:
            return True
        H = _handler_class()
        if H is None:
            return False
        if getattr(H, "_brand_patched", False):
            _state["installed"] = True
            return True
        original = H.handle_one_request

        def handle_one_request(self):
            if not _state["on"]:
                return original(self)
            real = self.wfile
            out = _Out(real)
            self.wfile = out
            try:
                original(self)
            finally:
                self.wfile = real
                try:
                    path = (getattr(self, "path", "") or "").split("?")[0]
                    if path.startswith(SKIP_PATHS) and out.mode == "html":
                        out.mode = "pass_html"
                        real.write(bytes(out.buf))
                        out.buf = bytearray()
                    out.finish()
                except Exception as e:
                    _state["last_error"] = str(e)[:200]
                    try:
                        if out.buf:
                            real.write(bytes(out.buf))
                    except Exception:
                        pass

        H.handle_one_request = handle_one_request
        H._brand_patched = True
        _state["installed"] = True
        return True


def handle(method, action, data, api_key, ctx):
    armed = _install()
    if action in ("off", "on"):
        if not api_key:
            return {"error": "api_key_required"}, 401
        _state["on"] = action == "on"
    if action == "spec":
        return {"module": "brand", "version": VERSION,
                "what": "Every HTML page presented as Monop Content, rewritten as it is served. No page file is edited.",
                "rules": [{"from": a, "to": b} for a, b in RULES],
                "left_as_they_are": list(SKIP_PATHS)}, 200
    return {"module": "brand", "version": VERSION, "armed": armed, "on": _state["on"],
            "pages_rewritten": _state["rewritten"], "replacements": _state["replacements"],
            "left_as_they_are": list(SKIP_PATHS), "last_error": _state["last_error"]}, 200
