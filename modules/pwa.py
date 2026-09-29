#!/usr/bin/env python3
"""
modules/pwa.py  v1.0.1
Makes sebbi.pro installable: an app on the home screen, full-screen, its own
icon. No app store, no fees, payments unchanged. Arm after each deploy:
    https://sebbi.pro/x/pwa/status
Serves /manifest.webmanifest, /sw.js and the app icons at clean URLs. The
install button and the manifest link live in the pages themselves.
"""

import base64
import sys

VERSION = "1.0.1"
PUBLIC = {("GET", "status"), ("GET", "spec")}

MANIFEST = '{"name":"sebbi.pro \\u2014 10p Wing","short_name":"10p Wing","description":"Watch free, then 10p for the rest. 7p goes to the creator.","start_url":"/cinema?src=pwa","scope":"/","display":"standalone","background_color":"#0a0f1e","theme_color":"#0a0f1e","orientation":"portrait-primary","categories":["entertainment","video"],"icons":[{"src":"/app-icon-192.png","sizes":"192x192","type":"image/png","purpose":"any"},{"src":"/app-icon-512.png","sizes":"512x512","type":"image/png","purpose":"any"},{"src":"/app-icon-maskable.png","sizes":"512x512","type":"image/png","purpose":"maskable"}]}'
SW = "const C='sebbi-shell-v1';\nself.addEventListener('install',function(e){self.skipWaiting()});\nself.addEventListener('activate',function(e){e.waitUntil(self.clients.claim())});\nself.addEventListener('fetch',function(e){\n  if(e.request.method!=='GET')return;\n  e.respondWith(fetch(e.request).catch(function(){return caches.match(e.request)}));\n});\n"
_I192 = (
    "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"
)
_I512 = (
    "iVBORw0KGgoAAAANSUhEUgAAAgAAAAIABAMAAAAGVsnJAAAAMFBMVEXJqEzJqEvIqEvGpUu3mUenjUOYgUCCbzpmWTRWTDBCPCsoJyQRFR8LDx"
    "0KDx4KDx0uKk37AAAPY0lEQVR42u3dS3Bb1RkH8P+9kmxKIVh0QrvpVISSdLqpqIF4posKQpOUbkwoEEoXZgLBQJmGJATbCTNMIbFDYiYzpY0D"
    "SepFM43Lo+rOEEK16Ext54G6KyEx6kxn2gKJxdB2sC1ddSE/JFl+3PP4zrnX31lA4vhK9/z0fec75z50nStY3s0FAzAAAzAAAzAAAzAAAzAAAz"
    "AAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAA"
    "AzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzAAAzCApS1q6o3Pjo2N5ceufPrnO26MO/F4fJ2h/X"
    "BMPGrLO3f+7Js1P7ttXfNNiWUBcO1b50Yy9aNxS/PN3wk7wLVHBzILZeQzd90SZoDL7y7YfRMElACXX38ns4RfoyWgA1hi96kJyABGejI+fjva"
    "vSVcAN7Akz63ePCZRIgALg70+t5m7a47QgMwvD8jsBVNGhAAeEd2C265eZf+NNC/GPL6RPuPk1254AMUu/eIbzz4RDboAMWeXpnNhzqzwQaQ7D"
    "8wrFtA7yBY2NUv/RoNJ1OBjYBPt8r3HxMP/CmoAMV9aRUvM/lgNpgAXk+/mhea6MwFEaB0slfVSw3vzgdwEPzLjxS+2EO/DFwEfPCkylf73ctB"
    "A/hEbd56PX8IVgoUtqYVv2Ls7WSAIkBRAawqho/nAgQwckjDoNIbHIDJ3Tpe9WQ6KABet5apW1FLEugAGD6kJVgx3hsMgKt3Q1PTkQTqAbx2bW"
    "sXHUmgHmCwH9ra+HP2A1x9UOfqffCPtgN4HToX7yi25ywHuHAIWtv4cbsBvJeguR3JWQ0wnNYNMNlrM0DxALS3gazFAMMZ/QCFXnsBCntA0AYz"
    "1gK8naUAKB60FWDiOZC0obSlAH05GgDvCTsBJp4HUfui30qAkyBru20EKPTTAUykLQSgKQFTheCofQDFYyBsI1nrACgmgTqmg6oAigdB2t7JWg"
    "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"
    "xAAAAAAElFTkSuQmCC"
)
_IMASK = (
    "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"
    "SUVORK5CYII="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/manifest.webmanifest": (MANIFEST.encode("utf-8"), "application/manifest+json; charset=utf-8"),
    "/sw.js": (SW.encode("utf-8"), "text/javascript; charset=utf-8"),
    "/app-icon-192.png": (_d(_I192), "image/png"),
    "/app-icon-512.png": (_d(_I512), "image/png"),
    "/app-icon-maskable.png": (_d(_IMASK), "image/png"),
}
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


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_pwa_patched", False):
        _patched = True
        return True
    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Service-Worker-Allowed", "/")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._pwa_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "pwa", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)
