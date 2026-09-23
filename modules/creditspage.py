"""
modules/creditspage.py  v1.1.0
The viewer's credit page at /credits: top up once, then unlock locked videos
anywhere with a tap. Talks to modules/credits.py over /c/.

New in 1.1.0
  * One £5 button, matching the single £5 Stripe payment link (the old £2/£10/£20
    buttons all went to the same £5 link).
  * When Stripe sends the buyer back to /credits?paid=1, the page watches the
    balance and says when the credit has landed.
  * The viewer's full code is shown, so a top-up can always be put right by hand.
  * The out-of-date "card top-ups are being switched on" message is gone.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/creditspage/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.1.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPllvdXIgY3JlZGl0IOKAlCBzZWJiaS5wcm88L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0iVG9w"
    "IHVwIG9uY2UsIHVubG9jayBhbnkgbG9ja2VkIHZpZGVvIHdpdGggYSB0YXAuIEV2ZXJ5IHBhaWQgdmlldyBpcyBzZWFsZWQgb24g"
    "YSBwdWJsaWMgY2hhaW4uIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JQk0r"
    "UGxleCtNb25vOndnaHRANDAwOzUwMDs2MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMCZmYW1pbHk9TmV3"
    "c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgo6cm9vdHst"
    "LWluazojMDUwNzBmOy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLW11dGU6IzhhOTNhZDstLWxpbmU6cmdiYSgyMDEsMTY4"
    "LDc2LC4yMik7LS1tb25vOidJQk0gUGxleCBNb25vJyx1aS1tb25vc3BhY2UsbW9ub3NwYWNlOy0tc2FuczonSUJNIFBsZXggU2Fu"
    "cycsc3lzdGVtLXVpLHNhbnMtc2VyaWY7LS1zZXJpZjonTmV3c3JlYWRlcicsR2VvcmdpYSxzZXJpZn0KKntib3gtc2l6aW5nOmJv"
    "cmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowOy13ZWJraXQtdGFwLWhpZ2hsaWdodC1jb2xvcjp0cmFuc3BhcmVudH0KYm9keXti"
    "YWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAwJSwjMTUxYTNlLCMwNTA3MGYgNjIlKTtjb2xvcjojZThl"
    "ZGY3O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2xpbmUtaGVpZ2h0OjEuNjttaW4taGVpZ2h0OjEwMHZofQoud3JhcHttYXgtd2lk"
    "dGg6NzIwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjAgMjBweCA3MHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRl"
    "bnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVhLWluc2V0"
    "LXRvcCkpIDAgMH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fS5icmFuZCBie2NvbG9yOnZh"
    "cigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBhe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2Nv"
    "bG9yOnZhcigtLW11dGUpO3RleHQtZGVjb3JhdGlvbjpub25lO21hcmdpbi1sZWZ0OjE0cHh9Cmgxe2ZvbnQtZmFtaWx5OnZhcigt"
    "LXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDMwcHgsNi40dncsNDhweCk7bWFyZ2luOjI2cHggMCA4cHg7"
    "YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsI2ZmZiwjYzlhODRjIDQ1JSwjN2ZlM2IwKTstd2Via2l0LWJhY2tncm91"
    "bmQtY2xpcDp0ZXh0O2JhY2tncm91bmQtY2xpcDp0ZXh0O2NvbG9yOnRyYW5zcGFyZW50fQpwLmxlYWR7Y29sb3I6I2I2YzBkNjtt"
    "YXgtd2lkdGg6NTJjaH0KLmJhbGFuY2V7bWFyZ2luOjI2cHggMDt0ZXh0LWFsaWduOmNlbnRlcjtiYWNrZ3JvdW5kOnJnYmEoMTMs"
    "MjAsMzYsLjg1KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MThweDtwYWRkaW5nOjI2cHh9Ci5i"
    "YWxhbmNlIC5ue2ZvbnQ6NjAwIDU2cHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tb2spO2xpbmUtaGVpZ2h0OjF9Ci5iYWxhbmNl"
    "IC5se2ZvbnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7bGV0dGVyLXNwYWNpbmc6LjE2ZW07Y29sb3I6dmFyKC0tbXV0ZSk7bWFyZ2lu"
    "LXRvcDo2cHh9Ci5taW5pe2ZvbnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tbXV0ZSk7bWFyZ2luLXRvcDoxMHB4"
    "O3dvcmQtYnJlYWs6YnJlYWstYWxsfQouYnV5e2Rpc3BsYXk6YmxvY2s7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAs"
    "MzYsLjg1KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWdvbGQpO2JveC1zaGFkb3c6MCAwIDI0cHggcmdiYSgyMDEsMTY4LDc2LC4y"
    "Mik7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MjBweDt0ZXh0LWFsaWduOmNlbnRlcjtjdXJzb3I6cG9pbnRlcjtjb2xvcjoj"
    "ZmZmO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pfQouYnV5IGJ7ZGlzcGxheTpibG9jaztmb250OjYwMCAzMHB4IHZhcigtLW1vbm8p"
    "fS5idXkgc3Bhbntmb250OjUwMCAxMnB4IHZhcigtLW1vbm8pO2NvbG9yOnZhcigtLW11dGUpfQoub3V0e21hcmdpbi10b3A6MThw"
    "eDtiYWNrZ3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEycHg7cGFkZGlu"
    "ZzoxNnB4O2ZvbnQ6MTNweCB2YXIoLS1tb25vKTtjb2xvcjojY2ZlNmQ5O2Rpc3BsYXk6bm9uZX0KLm91dC5vbntkaXNwbGF5OmJs"
    "b2NrfS5vdXQgYXtjb2xvcjp2YXIoLS1vayl9Ci5jYXJke2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwuOCk7Ym9yZGVyOjFweCBz"
    "b2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjE0cHg7cGFkZGluZzoxOHB4O21hcmdpbi10b3A6MTRweH0KLmNhcmQgaDN7"
    "Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MTlweDttYXJnaW4tYm90dG9tOjZweH0u"
    "Y2FyZCBwe2ZvbnQtc2l6ZToxNHB4O2NvbG9yOiNiNmMwZDZ9Ci5idG57ZGlzcGxheTppbmxpbmUtYmxvY2s7bWFyZ2luLXRvcDox"
    "NHB4O3BhZGRpbmc6MTNweCAyMHB4O2JvcmRlci1yYWRpdXM6MTFweDtmb250OjYwMCAxMy41cHggdmFyKC0tbW9ubyk7YmFja2dy"
    "b3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMjQpO3RleHQtZGVj"
    "b3JhdGlvbjpub25lfQo8L3N0eWxlPjwvaGVhZD48Ym9keT48ZGl2IGNsYXNzPSJ3cmFwIj4KPGRpdiBjbGFzcz0idG9wIj48ZGl2"
    "IGNsYXNzPSJicmFuZCI+c2ViYmk8Yj4ucHJvPC9iPiDCtyBDUkVESVQ8L2Rpdj48bmF2PjxhIGhyZWY9Ii9jaW5lbWEiPkNpbmVt"
    "YTwvYT48YSBocmVmPSIvY3JlYXRlIj5TdHVkaW88L2E+PGEgaHJlZj0iLyI+SG9tZTwvYT48L25hdj48L2Rpdj4KPGgxPlRvcCB1"
    "cCBvbmNlLiBUYXAgdG8gd2F0Y2ggYW55dGhpbmcuPC9oMT4KPHAgY2xhc3M9ImxlYWQiPk9uZSBzbWFsbCBiYWxhbmNlIHVubG9j"
    "a3MgbG9ja2VkIHZpZGVvcyBhbnl3aGVyZSBvbiB0aGUgaW50ZXJuZXQsIGEgZmV3IHBlbmNlIGF0IGEgdGltZS4gTm8gYWNjb3Vu"
    "dCwgbm8gY2FyZCBkZXRhaWxzIHN0b3JlZCB3aXRoIHRoZSBjcmVhdG9yLCBhbmQgZXZlcnkgcGFpZCB2aWV3IHNlYWxlZCBvbiBh"
    "IHB1YmxpYyBjaGFpbi48L3A+CjxkaXYgY2xhc3M9ImJhbGFuY2UiPjxkaXYgY2xhc3M9Im4iIGlkPSJiYWwiPuKAlDwvZGl2Pjxk"
    "aXYgY2xhc3M9ImwiPlBFTkNFIE9GIENSRURJVDwvZGl2PjxkaXYgY2xhc3M9Im1pbmkiIGlkPSJ3aG8iPjwvZGl2PjwvZGl2Pgo8"
    "YnV0dG9uIGNsYXNzPSJidXkiIGlkPSJidXkiPjxiPsKjNTwvYj48c3Bhbj41MCB2aWV3cyBhdCAxMHAgwrcgcGF5IGJ5IGNhcmQ8"
    "L3NwYW4+PC9idXR0b24+CjxkaXYgY2xhc3M9Im91dCIgaWQ9Im91dCI+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxoMz5XaGF0"
    "IHlvdSdyZSBidXlpbmc8L2gzPjxwPkNyZWRpdCwgbm90IGEgc3Vic2NyaXB0aW9uLiBJdCBzaXRzIG9uIHlvdXIgYmFsYW5jZSB1"
    "bnRpbCB5b3Ugc3BlbmQgaXQsIGFuZCBhbnkgY3JlYXRvcidzIGxvY2tlZCB2aWRlbyBhY2NlcHRzIGl0LiBVbnNwZW50IGNyZWRp"
    "dCBkb2VzIG5vdCBleHBpcmUuPC9wPjwvZGl2Pgo8ZGl2IGNsYXNzPSJjYXJkIj48aDM+WW91ciBjcmVkaXQgbGl2ZXMgb24gdGhp"
    "cyBkZXZpY2U8L2gzPjxwPkl0IGlzIHRpZWQgdG8gdGhlIGNvZGUgc2hvd24gdW5kZXIgeW91ciBiYWxhbmNlLiBJZiBhbnl0aGlu"
    "ZyBldmVyIGdvZXMgd3Jvbmcgd2l0aCBhIHRvcC11cCwgc2VuZCB0aGF0IGNvZGUgdG8ganVzdHJpZ2h0ZGVjb3JhdG9yc0BnbWFp"
    "bC5jb20gYW5kIGl0IHdpbGwgYmUgcHV0IHJpZ2h0LjwvcD48L2Rpdj4KPGEgY2xhc3M9ImJ0biIgaHJlZj0iL2NpbmVtYSI+R28g"
    "YW5kIHdhdGNoIHNvbWV0aGluZyDihpI8L2E+CjwvZGl2Pgo8c2NyaXB0PgooZnVuY3Rpb24oKXsKInVzZSBzdHJpY3QiOwp2YXIg"
    "QVBJPSIvYy8iOwpmdW5jdGlvbiBpZCgpe3RyeXt2YXIgaz1sb2NhbFN0b3JhZ2UuZ2V0SXRlbSgic2ViYmkudmlld2VyIik7aWYo"
    "aylyZXR1cm4ga31jYXRjaChlKXt9CiB2YXIgcz0idiIsYz0iYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU2Nzg5Ijtm"
    "b3IodmFyIGk9MDtpPDE5O2krKylzKz1jW01hdGguZmxvb3IoTWF0aC5yYW5kb20oKSozNildOwogdHJ5e2xvY2FsU3RvcmFnZS5z"
    "ZXRJdGVtKCJzZWJiaS52aWV3ZXIiLHMpfWNhdGNoKGUpe31yZXR1cm4gc30KdmFyIHZpZXdlcj1pZCgpLG91dD1kb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgib3V0IiksYmFsPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiYWwiKTsKZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoIndobyIpLnRleHRDb250ZW50PSJZb3VyIGNvZGU6ICIrdmlld2VyOwpmdW5jdGlvbiBzYXkoaCl7b3V0LmNsYXNzTGlz"
    "dC5hZGQoIm9uIik7b3V0LmlubmVySFRNTD1ofQpmdW5jdGlvbiBoZWxsbygpe3JldHVybiBmZXRjaChBUEkrImhlbGxvP3ZpZXdl"
    "cj0iK3ZpZXdlcix7Y2FjaGU6Im5vLXN0b3JlIn0pLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpfSl9CmZ1bmN0aW9u"
    "IHNob3coZCl7YmFsLnRleHRDb250ZW50PSh0eXBlb2YgZC5iYWxhbmNlX3BlbmNlPT09Im51bWJlciIpP2QuYmFsYW5jZV9wZW5j"
    "ZToi4oCUIjtyZXR1cm4gZH0KaGVsbG8oKS50aGVuKGZ1bmN0aW9uKGQpewogc2hvdyhkKTsKIGlmKC9bPyZdcGFpZD0xLy50ZXN0"
    "KGxvY2F0aW9uLnNlYXJjaCkpewogIHZhciBzdGFydD1kLmJhbGFuY2VfcGVuY2V8fDAsdHJpZXM9MDsKICBzYXkoIlBheW1lbnQg"
    "cmVjZWl2ZWQuIFlvdXIgY3JlZGl0IGlzIGxhbmRpbmcgbm934oCmIik7CiAgdmFyIHQ9c2V0SW50ZXJ2YWwoZnVuY3Rpb24oKXt0"
    "cmllcysrO2hlbGxvKCkudGhlbihmdW5jdGlvbih4KXtzaG93KHgpOwogICBpZih4LmJhbGFuY2VfcGVuY2U+c3RhcnQpe2NsZWFy"
    "SW50ZXJ2YWwodCk7c2F5KCJEb25lLiDCozUgYWRkZWQg4oCUIHlvdXIgYmFsYW5jZSBpcyAiK3guYmFsYW5jZV9wZW5jZSsicC4i"
    "KTsKICAgIHRyeXtoaXN0b3J5LnJlcGxhY2VTdGF0ZShudWxsLCIiLGxvY2F0aW9uLnBhdGhuYW1lKX1jYXRjaChlKXt9fQogICBl"
    "bHNlIGlmKHRyaWVzPj0yMCl7Y2xlYXJJbnRlcnZhbCh0KTtzYXkoIllvdXIgcGF5bWVudCB3ZW50IHRocm91Z2ggYnV0IHRoZSBj"
    "cmVkaXQgaGFzbid0IHNob3duIHlldC4gUmVmcmVzaCBpbiBhIG1pbnV0ZSDigJQgb3Igc2VuZCB5b3VyIGNvZGUgKCIrdmlld2Vy"
    "KyIpIHRvIGp1c3RyaWdodGRlY29yYXRvcnNAZ21haWwuY29tIGFuZCBpdCB3aWxsIGJlIGFkZGVkIGJ5IGhhbmQuIil9CiAgfSl9"
    "LDIwMDApOwogfQp9KS5jYXRjaChmdW5jdGlvbigpe2JhbC50ZXh0Q29udGVudD0i4oCUIn0pOwpkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgiYnV5Iikub25jbGljaz1mdW5jdGlvbigpewogc2F5KCJPcGVuaW5nIGNoZWNrb3V04oCmIik7CiBmZXRjaChBUEkrInRv"
    "cHVwIix7bWV0aG9kOiJQT1NUIixoZWFkZXJzOnsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiJ9LGJvZHk6SlNPTi5z"
    "dHJpbmdpZnkoe3ZpZXdlcjp2aWV3ZXIscGVuY2U6NTAwfSl9KQogLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpfSku"
    "dGhlbihmdW5jdGlvbihkKXsKICBpZihkLmNoZWNrb3V0KXtzYXkoJ09wZW5pbmcgY2hlY2tvdXTigKYgPGEgaHJlZj0iJytkLmNo"
    "ZWNrb3V0KyciPmNvbnRpbnVlIHRvIHBheW1lbnQ8L2E+Jyk7bG9jYXRpb24uaHJlZj1kLmNoZWNrb3V0O3JldHVybn0KICBpZihk"
    "LnBhaWQpe3NheSgiVGVzdCBjcmVkaXQgYWRkZWQ6ICIrZC5hZGRlZF9wZW5jZSsicC4gWW91ciBiYWxhbmNlIGlzICIrZC5iYWxh"
    "bmNlX3BlbmNlKyJwLiIpO2hlbGxvKCkudGhlbihzaG93KTtyZXR1cm59CiAgc2F5KGQubWVzc2FnZXx8IkNvdWxkIG5vdCBzdGFy"
    "dCBhIHRvcC11cCBqdXN0IG5vdy4iKTsKIH0pLmNhdGNoKGZ1bmN0aW9uKCl7c2F5KCJDb3VsZCBub3QgcmVhY2ggc2ViYmkucHJv"
    "LiIpfSl9Owp9KSgpOwo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    '/credits': (_d(_HTML_B64), "text/html; charset=utf-8"),
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
    if getattr(cls, "_creditspage_patched", False):
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
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._creditspage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "creditspage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
