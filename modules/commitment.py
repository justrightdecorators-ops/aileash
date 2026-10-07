"""
modules/commitment.py  v1.0.0  -  the sealed climate & energy commitment

A public page at https://sebbi.pro/commitment showing sebbi.pro's climate and
energy commitment - and the thing no other company's pledge has: it is sealed
into the sebbi.pro chain and timestamped into Bitcoin, so it cannot be quietly
edited, weakened or backdated. The page proves itself.

Two jobs, both additive - no existing file is touched:

  GET  https://sebbi.pro/commitment       the public, self-proving pledge page
  GET  https://sebbi.pro/commitment.txt    the exact canonical bytes that were
                                           hashed, so anyone can recompute the
                                           SHA-256 and confirm it matches the
                                           fingerprint sealed into Bitcoin.

The pledge was sealed via the platform's own notary:
  receipt   https://sebbi.pro/n/NT-EDP9-A35N
  digest    b8179a3f09e3294e9e9437e6f3842fef71f2404a329a1ed2c551adf23aaebc24
  verify    https://sebbi.pro/forever

New file only. Mirrors the proveit.py page pattern. Idempotent.

Arm with everything:  https://sebbi.pro/x/arm/status
See it:               https://sebbi.pro/commitment
"""

import hashlib
import html as _html
import os
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

SITE = "https://sebbi.pro"
OG_IMG = SITE + "/og-cover.png"

# The exact canonical bytes that were hashed and sealed into Bitcoin.
# Do not edit - changing one character changes the digest and breaks the proof.
PLEDGE = (
    "sebbi.pro / Monop Content — Climate & Energy Commitment — 7 October 2026\n\n"
    "We commit to the SME Climate Hub / Race to Zero standard:\n"
    "1. Measure our greenhouse-gas emissions.\n"
    "2. Halve them before 2030.\n"
    "3. Reach net zero before 2050.\n"
    "4. Report progress publicly every year.\n\n"
    "Because sebbi.pro is built to timestamp decisions into Bitcoin, we go further "
    "than a signature: this commitment is sealed into the sebbi.pro chain and "
    "timestamped into Bitcoin, so it cannot be quietly edited, weakened or "
    "backdated. Anyone can verify it at https://sebbi.pro/forever.\n\n"
    "Signed: Justin Dobson, founder, sebbi.pro (Monop Content).\n"
)
PLEDGE_BYTES = PLEDGE.encode("utf-8")
DIGEST = hashlib.sha256(PLEDGE_BYTES).hexdigest()

RECEIPT_CODE = "NT-EDP9-A35N"
RECEIPT_URL = SITE + "/n/" + RECEIPT_CODE
SEALED_DATE = "7 October 2026"
SME_URL = "https://smeclimatehub.org/"
BADGE_PATH = "/sme-committed-2026.png"
BADGE_FILE = "sme-committed-2026.png"

_state = {"patched": False, "last_error": None, "badge": None}


def _badge_bytes():
    if _state["badge"] is None:
        for p in (BADGE_FILE, os.path.join(os.getcwd(), BADGE_FILE)):
            try:
                with open(p, "rb") as f:
                    _state["badge"] = f.read()
                    break
            except Exception:
                continue
    return _state["badge"]


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


_CSS = """
*{margin:0;padding:0;box-sizing:border-box}body{background:#05070f;color:#eaf0fb;
font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.55;
background-image:radial-gradient(120% 80% at 50% -10%,rgba(37,52,110,.5),rgba(5,7,15,0) 55%),radial-gradient(90% 60% at 50% 120%,rgba(95,227,161,.08),rgba(5,7,15,0) 60%)}
.wrap{max-width:720px;margin:0 auto;padding:40px 20px 80px}
a{color:#f0d78a}.mut{color:#8b94ab}.gold{color:#f0d78a}.grn{color:#8ff0bf}
.kick{font:600 11px/1 'IBM Plex Mono',monospace;letter-spacing:.3em;color:#5fe3a1;text-transform:uppercase}
h1{font:700 clamp(28px,6vw,42px)/1.07 Inter,sans-serif;letter-spacing:-.02em;margin:14px 0 12px;
background:linear-gradient(92deg,#fff,#8ff0bf 50%,#4fd6e0);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.lead{font-size:17px;color:#c2cbe0;margin-bottom:26px}
h2{font:700 18px Inter;margin:34px 0 12px;color:#eaf0fb}
.pledge{background:rgba(10,15,30,.6);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:26px 24px;margin-top:8px}
.pledge h3{font:700 16px Inter;color:#fff;margin-bottom:14px}
.pledge ol{margin:12px 0 4px 20px}.pledge li{margin:6px 0;color:#d4dcee}
.pledge p{color:#c2cbe0;margin-top:14px}
.badge{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(95,227,161,.4);background:rgba(95,227,161,.1);
color:#8ff0bf;border-radius:999px;padding:8px 15px;font:700 13px Inter;letter-spacing:.02em;margin-bottom:6px}
.dot{width:9px;height:9px;border-radius:50%;background:#5fe3a1;box-shadow:0 0 10px #5fe3a1}
.card{background:rgba(10,15,30,.6);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:22px 24px;margin-top:16px}
.row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:14px}
.row:last-child{border:0}.row .k{color:#8b94ab}.row .v{text-align:right;font-weight:600;word-break:break-all}
.mono{font:12px/1.5 'IBM Plex Mono',monospace}
.cta{display:block;margin-top:14px;background:rgba(201,168,76,.12);border:1px solid rgba(201,168,76,.35);
border-radius:10px;padding:16px;text-decoration:none;color:#f0d78a;font-weight:600}
.cta.g{background:rgba(95,227,161,.1);border-color:rgba(95,227,161,.35);color:#8ff0bf}
.foot{margin-top:40px;font-size:12px;color:#5f6b85;border-top:1px solid rgba(255,255,255,.07);padding-top:18px}
.steps{counter-reset:s;margin-top:10px}
.steps li{list-style:none;position:relative;padding:10px 0 10px 40px;color:#c2cbe0;font-size:14px;border-bottom:1px solid rgba(255,255,255,.05)}
.steps li:before{counter-increment:s;content:counter(s);position:absolute;left:0;top:10px;width:26px;height:26px;border-radius:50%;
background:rgba(95,227,161,.14);border:1px solid rgba(95,227,161,.4);color:#8ff0bf;font:700 12px Inter;display:flex;align-items:center;justify-content:center}
"""


def _page():
    t = "Our climate & energy commitment, sealed into Bitcoin - sebbi.pro"
    d = ("sebbi.pro's climate commitment is not a PDF we can quietly edit. It is "
         "sealed into Bitcoin and verifiable by anyone - the first of its kind.")
    pledge_html = _html.escape(PLEDGE)
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>" + _html.escape(t) + "</title>"
        "<meta name=description content='" + _html.escape(d) + "'>"
        "<meta id='sebbi-og' property='og:type' content='website'>"
        "<meta property='og:site_name' content='sebbi.pro'>"
        "<meta property='og:title' content='" + _html.escape(t) + "'>"
        "<meta property='og:description' content='" + _html.escape(d) + "'>"
        "<meta property='og:image' content='" + OG_IMG + "'>"
        "<meta property='og:url' content='" + SITE + "/commitment'>"
        "<meta name='twitter:card' content='summary_large_image'>"
        "<meta name='twitter:image' content='" + OG_IMG + "'>"
        "<link rel=canonical href='" + SITE + "/commitment'>"
        "<style>" + _CSS + "</style></head><body><div class=wrap>"

        "<div class=kick>&#9728;&nbsp; CLIMATE &amp; ENERGY</div>"
        "<h1>A commitment we can't quietly walk back.</h1>"
        "<p class=lead>Every company signs a climate pledge as a document it can edit or backdate later. "
        "We seal decisions into Bitcoin for a living &mdash; so we sealed this one too. "
        "It is timestamped, tamper-evident, and checkable by anyone, without trusting us. "
        "As far as we know, it is the first climate commitment sealed into Bitcoin.</p>"

        "<div class=badge><span class=dot></span>SEALED &amp; TIMESTAMPED &middot; " + SEALED_DATE + "</div>"

        "<div style='margin:22px 0 2px'><a href='" + SME_URL + "' rel=noopener>"
        "<img src='" + BADGE_PATH + "' alt='SME Climate Hub — Committed 2026' "
        "style='width:100%;max-width:320px;height:auto;display:block'></a></div>"

        "<div class=pledge>"
        "<h3>Our commitment</h3>"
        "<p>sebbi.pro / Monop Content commits to the <a href='" + SME_URL + "' rel=noopener>SME Climate Hub / Race to Zero</a> standard:</p>"
        "<ol>"
        "<li>Measure our greenhouse-gas emissions.</li>"
        "<li>Halve them before 2030.</li>"
        "<li>Reach net zero before 2050.</li>"
        "<li>Report progress publicly every year.</li>"
        "</ol>"
        "<p>Because sebbi.pro timestamps decisions into Bitcoin, we go further than a signature: "
        "this commitment is sealed into the sebbi.pro chain and timestamped into Bitcoin, so it "
        "cannot be quietly edited, weakened or backdated.</p>"
        "<p class=mut style='margin-top:14px'>Signed: Justin Dobson, founder, sebbi.pro (Monop Content).</p>"
        "</div>"

        "<h2>The proof</h2>"
        "<div class=card>"
        "<div class=row><span class=k>Sealed</span><span class=v>" + SEALED_DATE + "</span></div>"
        "<div class=row><span class=k>Receipt</span><span class=v><a href='" + RECEIPT_URL + "'>" + RECEIPT_CODE + "</a></span></div>"
        "<div class=row><span class=k>Fingerprint (SHA-256)</span><span class='v mono'>" + DIGEST + "</span></div>"
        "<div class=row><span class=k>Anchored in</span><span class=v>Bitcoin, via OpenTimestamps</span></div>"
        "</div>"
        "<a class='cta g' href='" + RECEIPT_URL + "'>See the Bitcoin receipt &rarr;</a>"
        "<a class=cta href='" + SITE + "/forever'>Verify it against Bitcoin yourself &rarr;</a>"

        "<h2>Check it in three steps</h2>"
        "<ol class=steps>"
        "<li>Download the exact wording at <a href='" + SITE + "/commitment.txt'>" + SITE + "/commitment.txt</a>.</li>"
        "<li>Run SHA-256 on that file. You get the fingerprint above.</li>"
        "<li>Confirm that same fingerprint is anchored in Bitcoin via the <a href='" + RECEIPT_URL + "'>receipt</a> &mdash; proof of what we said, and when.</li>"
        "</ol>"

        "<div class=foot>This is sebbi.pro's own product used on itself: a decision (this pledge) scored, "
        "sealed and timestamped into Bitcoin. Want the same for your decisions? "
        "<a href='" + SITE + "/connect'>Start free &rarr;</a></div>"

        "</div></body></html>")


def _send(h, body, ctype="text/html; charset=utf-8"):
    data = body if isinstance(body, bytes) else body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(data)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(data)


def _install():
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is None:
        return False
    if getattr(H, "_commitment_patched", False):
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        if p == "/commitment":
            return _send(self, _page())
        if p == "/commitment.txt":
            return _send(self, PLEDGE_BYTES, "text/plain; charset=utf-8")
        if p == BADGE_PATH:
            data = _badge_bytes()
            if data:
                return _send(self, data, "image/png")
            return orig(self)
        return orig(self)

    H.do_GET = do_GET
    H._commitment_patched = True
    _state["patched"] = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _state["patched"] = _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:160]
    if action == "spec":
        return {"module": "commitment", "version": VERSION, "page": SITE + "/commitment",
                "text": SITE + "/commitment.txt", "receipt": RECEIPT_URL,
                "digest": DIGEST, "digest_ok": DIGEST == "b8179a3f09e3294e9e9437e6f3842fef71f2404a329a1ed2c551adf23aaebc24"}, 200
    return ({"module": "commitment", "version": VERSION, "armed": _state["patched"],
             "page": SITE + "/commitment", "receipt": RECEIPT_URL, "digest": DIGEST,
             "digest_ok": DIGEST == "b8179a3f09e3294e9e9437e6f3842fef71f2404a329a1ed2c551adf23aaebc24",
             "last_error": _state["last_error"]}, 200)
