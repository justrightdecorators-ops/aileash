"""
modules/social_meta.py  v1.0.0
Make sebbi.pro look sharp wherever a link lands, and legible to search engines
and AIs.

Two jobs, both additive - no existing file is touched:

1. Serves the share-card image at  https://sebbi.pro/og-cover.png

2. On the main shareable pages, if the page does NOT already set its own
   Open Graph tags, it injects, just before </head>:
     - Open Graph tags (og:title/description/image/url/type/site_name)
     - Twitter summary_large_image card
     - a canonical link
     - JSON-LD structured data (Organization + WebSite + SoftwareApplication)
   so a pasted link renders a premium preview card on LinkedIn, X, Slack,
   WhatsApp, iMessage etc., and Google / AI assistants read sebbi.pro as a
   real, described product.

Pages that already carry og: tags (answers, cinema) are left untouched.

Mirrors the proven homelink.py response-buffer pattern. Idempotent.

Arm with everything:  https://sebbi.pro/x/arm/status
See the card:         https://sebbi.pro/og-cover.png
"""

import io
import os
import re
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

SITE = "https://sebbi.pro"
IMG_PATH = "/og-cover.png"
MARK = b'id="sebbi-og"'

# Pages worth dressing for sharing. /og-cover.png is served on any path.
SHARE_PATHS = {
    "/", "/index.html", "/connect", "/spend", "/bitcoin", "/keys", "/dossier",
    "/forever", "/reseller", "/developers", "/pilot", "/scan", "/witness",
    "/build", "/passport", "/tokensaver", "/notary", "/start", "/tools",
}

DEF_TITLE = "sebbi.pro - Every AI decision, provable."
DEF_DESC = ("Score, seal and prove any AI decision, timestamped into Bitcoin - "
            "checkable by anyone, without trusting us.")

_state = {"patched": False, "last_error": None, "img": None}
_patched = False


def _img_bytes():
    if _state["img"] is None:
        for p in ("og-cover.png", os.path.join(os.getcwd(), "og-cover.png")):
            try:
                with open(p, "rb") as f:
                    _state["img"] = f.read()
                    break
            except Exception:
                continue
    return _state["img"]


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


def _esc(s):
    return (s or "").replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _extract(body_lower, body, tag_re):
    m = re.search(tag_re, body_lower)
    if not m:
        return None
    try:
        return body[m.start(1):m.end(1)].decode("utf-8", "replace").strip()
    except Exception:
        return None


def _block(title, desc, canonical):
    import json
    title = title or DEF_TITLE
    desc = desc or DEF_DESC
    img = SITE + IMG_PATH
    ld = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "@id": SITE + "/#org", "name": "sebbi.pro",
             "url": SITE, "logo": img, "description": DEF_DESC},
            {"@type": "WebSite", "@id": SITE + "/#site", "url": SITE,
             "name": "sebbi.pro", "publisher": {"@id": SITE + "/#org"}},
            {"@type": "SoftwareApplication", "name": "sebbi.pro / AILeash",
             "applicationCategory": "BusinessApplication", "operatingSystem": "Web",
             "url": SITE, "description": DEF_DESC,
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "GBP",
                        "description": "Free for 90 days, then 50p per device per month"}},
        ],
    }
    t, d = _esc(title), _esc(desc)
    html = (
        '<meta id="sebbi-og" property="og:type" content="website">'
        '<meta property="og:site_name" content="sebbi.pro">'
        '<meta property="og:title" content="' + t + '">'
        '<meta property="og:description" content="' + d + '">'
        '<meta property="og:image" content="' + img + '">'
        '<meta property="og:image:width" content="1200">'
        '<meta property="og:image:height" content="630">'
        '<meta property="og:url" content="' + _esc(canonical) + '">'
        '<meta name="twitter:card" content="summary_large_image">'
        '<meta name="twitter:title" content="' + t + '">'
        '<meta name="twitter:description" content="' + d + '">'
        '<meta name="twitter:image" content="' + img + '">'
        '<link rel="canonical" href="' + _esc(canonical) + '">'
        '<script type="application/ld+json">' + json.dumps(ld) + '</script>'
    )
    return html.encode("utf-8")


def _inject(raw, path):
    head, sep, body = raw.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or b" 200" not in lines[0]:
        return None
    lower = head.lower()
    if b"text/html" not in lower or b"content-encoding" in lower or b"chunked" in lower:
        return None
    blow = body.lower()
    if MARK in body or b"og:title" in blow:
        return None
    hat = blow.find(b"</head>")
    if hat < 0:
        return None
    import html as _html
    title = _extract(blow, body, rb"<title[^>]*>(.*?)</title>")
    desc = _extract(blow, body, rb'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']')
    if title:
        title = _html.unescape(title)
    if desc:
        desc = _html.unescape(desc)
    canonical = SITE + (path or "/")
    block = _block(title, desc, canonical)
    new_body = body[:hat] + block + body[hat:]
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
    if getattr(cls, "_social_meta_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0]
        # serve the share image
        if path == IMG_PATH:
            data = _img_bytes()
            if data:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                if getattr(self, "command", "GET") != "HEAD":
                    self.wfile.write(data)
                return
            return original_do_GET(self)
        # only dress the shareable pages
        if path not in SHARE_PATHS:
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
            changed = _inject(raw, path)
        except Exception:
            changed = None
        real.write(changed if changed is not None else raw)

    cls.do_GET = do_GET
    cls._social_meta_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _state["patched"] = _install(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:160]
    if action == "spec":
        return {"module": "social_meta", "version": VERSION,
                "image": SITE + IMG_PATH, "pages": sorted(SHARE_PATHS)}, 200
    return ({"module": "social_meta", "version": VERSION, "armed": _state["patched"],
             "image": SITE + IMG_PATH, "image_bytes": len(_img_bytes() or b""),
             "last_error": _state["last_error"]}, 200)
