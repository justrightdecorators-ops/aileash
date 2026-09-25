# Codebase — part 7 of 40

Contains:
- `modules/creditspage.py`
- `modules/custody.py`
- `modules/declare.py`
- `modules/demo.py`
- `modules/disclosure.py`
- `modules/dsr.py`
- `modules/earnpage.py`


## `modules/creditspage.py`

181 lines, 11747 bytes

```python
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

```


## `modules/custody.py`

491 lines, 19866 bytes

```python
"""
modules/custody.py  v1.0.2  -  independent copies, proven and counted

The self-proving archive file (/x/archive) can be checked anywhere. This
module proves WHERE it is actually held, by parties other than sebbi.pro.

Every day it:
  1. asks the Internet Archive whether it holds each recent sealed file, and
     if it does, fetches that copy and checks its fingerprint;
  2. fetches every registered holder's copy and checks its fingerprint;
  3. counts the independent holders whose copy is byte-for-byte a sealed
     file, and SEALS that count - with every holder, address and
     fingerprint - into the chain as a public block.

A copy only counts if it matches a fingerprint sealed in the chain. A holder
only counts if it is not sebbi.pro. The count can be checked by anyone, and
cannot be inflated: every entry names an address you can fetch yourself.

Anyone can become a holder:
  - tap the Internet Archive link on /x/custody/status, or
  - keep the file anywhere public and register the address:
      https://sebbi.pro/x/custody/offer?url=https://your.site/sebbi.json&name=You
    (it is fetched and checked before it is listed), or
  - run the keeper script (/x/custody/keeper) daily to fetch, verify and keep
    each day's file automatically.

Routes (public): status, holders, offer, keeper, spec. run is keyed.
Armed by the first visit to /x/custody/status.
"""

import gzip
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.2"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/custody/"
USER_ID = "system_custody"
UA = "sebbi-custody/1.0.2 (+https://sebbi.pro/x/custody/spec)"
TIMEOUT = 60
MAX_BYTES = 256 * 1024 * 1024
RECENT_FILES = 3
OPERATOR_HOSTS = ("sebbi.pro", "www.sebbi.pro")

PUBLIC = {("GET", a) for a in ("status", "holders", "offer", "keeper", "spec")}

_state = {"armed": False, "ctx": None, "last_run": None, "last_result": None}
_lock = threading.Lock()
_run_lock = threading.Lock()
_offer_busy = threading.BoundedSemaphore(2)


# ---------------------------------------------------------------- helpers

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_holders ("
        "url TEXT PRIMARY KEY, name TEXT, host TEXT, added_at REAL, "
        "last_checked REAL, last_verified REAL, last_fingerprint TEXT, "
        "last_date TEXT, last_status TEXT, times_verified INTEGER DEFAULT 0)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custody_runs ("
        "day TEXT PRIMARY KEY, sealed_block INTEGER, sealed_hash TEXT, "
        "independent_holders INTEGER, holding_latest INTEGER, "
        "latest_sha256 TEXT, ran_at REAL)")
    conn.commit()


def _host(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _public_https(url):
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if p.scheme != "https" or p.port not in (None, 443) or not p.hostname:
        return False
    if p.username or p.password:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443,
                                       proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
    except Exception:
        return False
    return True


def _get(url, max_bytes=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("too large")
    if raw[:2] == b"\x1f\x8b":
        # Archives keep a page exactly as it was sent - often zipped.
        raw = gzip.decompress(raw)
    return raw


def _canonical_sha(raw):
    obj = json.loads(raw.decode("utf-8"))
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _sealed_files():
    """date -> sha256, and sha256 -> file row, from the archive manifest."""
    data = json.loads(_get(SITE + "/x/archive/manifest").decode("utf-8"))
    files = data.get("files") or []
    return files, {f["sha256"]: f for f in files if f.get("sha256")}


def _seal(ctx, action, result):
    seal = (ctx or {}).get("seal")
    if not callable(seal):
        return None, None
    now = time.time()
    result = dict(result, decision=action.upper(), score=0, timestamp=now)
    event = {"user_id": USER_ID, "action": action, "amount": 0,
             "country": "UK", "device_id": "custody", "anomaly": 0,
             "device_risk": 0}
    try:
        res = seal(event, result, now)
    except Exception:
        return None, None
    if isinstance(res, (list, tuple)):
        return res[0], (res[1] if len(res) > 1 else None)
    if isinstance(res, dict):
        return (res.get("audit_hash") or res.get("hash"),
                res.get("block_index") or res.get("index"))
    return res, None


# ---------------------------------------------------------------- checks

def _wayback_captures(target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = json.loads(_get(
            "https://web.archive.org/cdx/search/cdx?url=" +
            urllib.parse.quote(target, safe="") +
            "&output=json&filter=statuscode:200&limit=-10",
            4 * 1024 * 1024).decode("utf-8"))
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = json.loads(_get(
            "https://archive.org/wayback/available?url=" +
            urllib.parse.quote(target, safe=""), 1024 * 1024).decode("utf-8"))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def _check_internet_archive(files):
    """For each recent sealed file: does the Internet Archive hold it, and
    is its copy byte-for-byte the sealed file?"""
    out = []
    for f in files[:RECENT_FILES]:
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
        row = {"holder": "Internet Archive", "date": f.get("date"),
               "sealed_sha256": f["sha256"],
               "archive_it": "https://web.archive.org/save/" + target}
        stamps = _wayback_captures(target)
        if stamps is None:
            row.update({"held": None, "note": "archive could not be asked"})
        elif not stamps:
            row.update({"held": False})
        else:
            row.update({"held": False, "captures_listed": len(stamps)})
            for stamp in stamps[:3]:
                raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, target)
                try:
                    fp = _canonical_sha(_get(raw_url))
                except Exception:
                    continue
                row.update({"held": fp == f["sha256"], "copy": raw_url,
                            "captured": stamp, "fingerprint": fp})
                if fp == f["sha256"]:
                    break
        out.append(row)
    return out


def _check_holder(url, by_sha):
    try:
        fp = _canonical_sha(_get(url))
    except Exception as exc:
        return {"fingerprint": None, "status": "unreachable (%s)"
                % exc.__class__.__name__}
    f = by_sha.get(fp)
    if not f:
        return {"fingerprint": fp,
                "status": "serves a file that is not a sealed archive file"}
    return {"fingerprint": fp, "date": f.get("date"), "status": "verified"}


def _run(ctx, force=False):
    conn, dblock = ctx.get("conn"), ctx.get("lock")
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        done = conn.execute("SELECT sealed_block FROM custody_runs WHERE day = ?",
                            (day,)).fetchone()
        if done and not force:
            return {"ok": True, "skipped": "already counted today",
                    "sealed_block": done[0]}
        holders = conn.execute("SELECT url, name FROM custody_holders").fetchall()

    files, by_sha = _sealed_files()
    if not files:
        return {"ok": False, "error": "no sealed archive files yet"}
    latest = files[0]["sha256"]

    ia = _check_internet_archive(files)
    results = []
    for url, name in holders:
        r = _check_holder(url, by_sha)
        r.update({"holder": name, "url": url})
        results.append(r)
        now = time.time()
        with dblock:
            if r["status"] == "verified":
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_verified = ?, last_fingerprint = ?, last_date = ?, "
                    "last_status = ?, times_verified = times_verified + 1 "
                    "WHERE url = ?", (now, now, r["fingerprint"], r.get("date"),
                                      r["status"], url))
            else:
                conn.execute(
                    "UPDATE custody_holders SET last_checked = ?, "
                    "last_status = ? WHERE url = ?", (now, r["status"], url))
            conn.commit()

    verified = [r for r in results if r["status"] == "verified"]
    ia_held = [r for r in ia if r.get("held")]
    hosts = set(_host(r["url"]) for r in verified)
    if ia_held:
        hosts.add("web.archive.org")
    holding_latest = len([r for r in verified if r["fingerprint"] == latest]) + \
        (1 if any(r["sealed_sha256"] == latest for r in ia_held) else 0)

    result = {"day": day, "latest_file_sha256": latest,
              "independent_holders": len(hosts),
              "holding_latest_file": holding_latest,
              "internet_archive": ia, "registered_holders": results,
              "rule": "A copy counts only if its canonical fingerprint is a "
                      "sealed archive file, and only if it is held somewhere "
                      "other than sebbi.pro. Every entry names an address "
                      "anyone can fetch to check it."}
    sealed_hash, sealed_block = _seal(ctx, "custody_counted", result)
    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO custody_runs (day, sealed_block, sealed_hash, "
            "independent_holders, holding_latest, latest_sha256, ran_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (day, sealed_block, sealed_hash, len(hosts), holding_latest,
             latest, time.time()))
        conn.commit()
    return {"ok": True, "day": day, "independent_holders": len(hosts),
            "holding_latest_file": holding_latest, "sealed_block": sealed_block,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, sealed_block))
            if sealed_block else None}


def _loop():
    time.sleep(120)
    while True:
        ctx = _state.get("ctx")
        if ctx and _run_lock.acquire(blocking=False):
            try:
                _state["last_result"] = _run(ctx)
            except Exception as exc:
                _state["last_result"] = {"ok": False, "error": str(exc)[:200]}
            finally:
                _run_lock.release()
            _state["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
        time.sleep(3600)


def _arm(ctx):
    with _lock:
        _state["ctx"] = ctx
        if _state["armed"]:
            return
        _state["armed"] = True
    threading.Thread(target=_loop, name="custody", daemon=True).start()


# ---------------------------------------------------------------- routes

def _q(data, k):
    v = (data or {}).get(k)
    return v[0] if isinstance(v, list) and v else v


def _offer(data, ctx):
    url = str(_q(data, "url") or "").strip()
    name = re.sub(r"[^A-Za-z0-9 .,&'()_-]", "", str(_q(data, "name") or ""))[:60]
    if not url:
        return {"ok": False, "error": "url_required",
                "example": BASE + "offer?url=https://your.site/sebbi.json&name=Your%20Name"}, 400
    if _host(url) in OPERATOR_HOSTS:
        return {"ok": False, "error": "operator_host",
                "detail": "A copy on sebbi.pro is not independent of sebbi.pro."}, 400
    if not _public_https(url):
        return {"ok": False, "error": "not_a_public_https_address"}, 400
    if not _offer_busy.acquire(timeout=10):
        return {"ok": False, "error": "busy"}, 429
    try:
        files, by_sha = _sealed_files()
        r = _check_holder(url, by_sha)
    finally:
        _offer_busy.release()
    if r["status"] != "verified":
        return {"ok": False, "error": "copy_not_verified", "detail": r["status"],
                "fingerprint": r.get("fingerprint"),
                "sealed_files": SITE + "/x/archive/manifest"}, 400
    conn, dblock = ctx["conn"], ctx["lock"]
    now = time.time()
    with dblock:
        _ensure(conn)
        conn.execute(
            "INSERT OR IGNORE INTO custody_holders (url, name, host, added_at, "
            "last_checked, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (url, name or _host(url), _host(url), now, now, now,
             r["fingerprint"], r.get("date"), "verified"))
        conn.commit()
    _, block = _seal(ctx, "custody_holder_registered", {
        "holder": name or _host(url), "url": url,
        "fingerprint": r["fingerprint"], "file_date": r.get("date")})
    return {"ok": True, "registered": url, "holder": name or _host(url),
            "fingerprint": r["fingerprint"], "file_date": r.get("date"),
            "sealed_in_block": block,
            "note": "Your copy was fetched and matches a sealed file. It will "
                    "be re-checked daily and counted in the sealed custody "
                    "count."}, 200


def _holders(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        rows = conn.execute(
            "SELECT url, name, last_verified, last_fingerprint, last_date, "
            "last_status, times_verified FROM custody_holders "
            "ORDER BY added_at").fetchall()
    iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)) if t else None
    return {"ok": True, "holders": [
        {"url": u, "name": n, "last_verified": iso(lv),
         "last_fingerprint": fp, "file_date": d, "status": st,
         "times_verified": tv} for u, n, lv, fp, d, st, tv in rows]}, 200


def _status(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        runs = conn.execute(
            "SELECT day, sealed_block, independent_holders, holding_latest, "
            "latest_sha256 FROM custody_runs ORDER BY day DESC LIMIT 14").fetchall()
        n_holders = conn.execute("SELECT COUNT(*) FROM custody_holders").fetchone()[0]
    latest_link = None
    try:
        files, _ = _sealed_files()
        if files:
            latest_link = ("https://web.archive.org/save/%s/x/archive/file?"
                           "sha256=%s" % (SITE, files[0]["sha256"]))
    except Exception:
        pass
    return {
        "ok": True, "module": "custody", "version": VERSION,
        "armed": _state["armed"], "last_run": _state["last_run"],
        "last_result": _state["last_result"],
        "independent_holders_today": runs[0][2] if runs else None,
        "registered_holders": n_holders,
        "recent_counts": [{"day": d, "sealed_block": b,
                           "check_block": ("%s/x/walk/block?index=%s" % (SITE, b))
                           if b else None,
                           "independent_holders": i, "holding_latest_file": h,
                           "latest_file": s} for d, b, i, h, s in runs],
        "become_a_holder": {
            "one_tap": latest_link,
            "register_your_own_copy": BASE + "offer?url=https://your.site/sebbi.json&name=You",
            "keep_it_automatically": BASE + "keeper"},
        "rule": "Counted only if byte-for-byte a sealed file, and only if held "
                "somewhere other than sebbi.pro. Each day's count is sealed.",
    }, 200


KEEPER = r'''#!/usr/bin/env python3
"""sebbi.pro keeper - fetch, verify and keep each day's self-proving file.

Run daily (for example from cron). Standard library only.
    python3 keeper.py /path/to/public/folder
Keeps every day's file that PASSES its own built-in checks, plus latest.json.
Serve that folder publicly, then register your latest.json once at:
    https://sebbi.pro/x/custody/offer?url=https://YOUR.SITE/latest.json&name=YOU
"""
import json, os, subprocess, sys, tempfile, urllib.request

out = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(out, exist_ok=True)
ua = {"User-Agent": "sebbi-keeper/1.0"}
latest = json.load(urllib.request.urlopen(urllib.request.Request(
    "https://sebbi.pro/x/archive/latest", headers=ua), timeout=60))
url = latest["file"]
raw = urllib.request.urlopen(urllib.request.Request(url, headers=ua),
                             timeout=300).read()
fd, tmp = tempfile.mkstemp(suffix=".json")
os.write(fd, raw); os.close(fd)
check = subprocess.run([sys.executable, "-c",
    "import json,sys;exec(json.load(open(sys.argv[1]))['verifier_py'])", tmp],
    capture_output=True, text=True)
print(check.stdout)
if check.returncode != 0:
    os.remove(tmp)
    sys.exit("Not kept: the file failed its own checks.")
name = "sebbi-chain-%s-%s.json" % (latest["date"], latest["sha256"])
os.replace(tmp, os.path.join(out, name))
with open(os.path.join(out, "latest.json"), "wb") as fh:
    fh.write(raw)
print("Kept", name, "and latest.json in", out)
'''


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "holders":
            return _holders(ctx)
        if action == "offer":
            return _offer(data, ctx)
        if action == "keeper":
            return {"ok": True, "keeper_py": KEEPER,
                    "how": "Save keeper_py as keeper.py, run it daily with a "
                           "folder you serve publicly, then register that "
                           "folder's latest.json once."}, 200
        if action == "spec":
            return {"module": "custody", "version": VERSION,
                    "counts": "independent holders whose copy is byte-for-byte "
                              "a sealed archive file",
                    "sealed": "each day's count, with every holder and "
                              "fingerprint, is sealed into the chain",
                    "routes": {"status": BASE + "status",
                               "holders": BASE + "holders",
                               "offer": BASE + "offer?url=<https address>&name=<name>",
                               "keeper": BASE + "keeper"}}, 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            with _run_lock:
                return _run(ctx, force=True), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET")}, 404
    except Exception as exc:
        return {"ok": False, "error": "custody_failed",
                "detail": str(exc)[:200]}, 500

```


## `modules/declare.py`

345 lines, 13493 bytes

```python
"""
Declaration notary - /x/declare/<action>

THE IDEA
--------
An operator uploads their own file saying what must always be true of their
decisions. It is sealed, versioned, and published. Every record is then tested
against it, and every violation is sealed.

WHY THIS ISN'T CIRCULAR
-----------------------
The obvious objection: if they write their own rules AND supply their own
data, checking one against the other proves nothing. They could declare
nothing and pass.

Two things stop that.

1. THE RULES COME FIRST. A declaration is sealed before the records it judges.
   You cannot write the rule after seeing the outcome, because the chain shows
   which came first. Retrofitting a standard to a result is exactly what this
   makes impossible.

2. YOU CANNOT QUIETLY WEAKEN IT. Every version is kept and sealed. If you
   published a strict rule in March and a loose one in September, both are
   permanent and the change is dated. Nobody can pretend the strict one never
   existed. Weakening your own standard becomes a visible act.

So the file does not prove you are honest. It converts your claims into
something that can be tested, and takes away your ability to move the goalposts
afterwards. An auditor reads the declaration, reads the violations, and reads
the version history. All three are sealed.

RULE FORMAT
-----------
    {"rules": [
      {"id": "no-silent-high-value",
       "describe": "Payments over 10000 are never auto-allowed",
       "when":    {"field": "amount",   "op": ">",  "value": 10000},
       "require": {"field": "decision", "op": "in", "value": ["CHALLENGE","BLOCK"]}}
    ]}

    ops: == != > >= < <= in not_in exists

HONEST LIMITS
-------------
- Weak rules prove weak things. A declaration that requires nothing passes
  everything. Publish it and let people judge the rules themselves.
- This tests what was sealed. A decision never recorded cannot violate a rule
  - gapless receipts are what cover that gap, not this.
- The operator still supplies the data. This is not an external audit. It is a
  published standard, sealed before the evidence, that they can be held to.

    POST /x/declare/publish     declaration file - sealed and versioned
    GET  /x/declare/current     the live declaration
    GET  /x/declare/history     every version ever published
    POST /x/declare/check       test sealed records against it, seal the result
    GET  /x/declare/violations  what failed, and when
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.0"
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "exists"}
MAX_RULES = 100

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declarations(id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,version INTEGER,body TEXT,sha256 TEXT,published REAL,audit_hash TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS declare_checks(check_id TEXT PRIMARY KEY,api_key TEXT,decl_version INTEGER,ran REAL,tested INTEGER,passed INTEGER,violated INTEGER,detail TEXT,audit_hash TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dec_key ON declarations(api_key,version)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    if not isinstance(s, str):
        s = json.dumps(s, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, ref, action, detail):
    ts = time.time()
    ev = {"user_id": "dec:" + ref, "action": "declare_" + action, "amount": 0,
          "country": "UK", "device_id": "declare", "anomaly": 0, "device_risk": 0}
    res = {"decision": "DECLARATION_SEALED", "score": 0, "declare_action": action,
           "declare_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _validate(body):
    if not isinstance(body, dict):
        return "declaration must be an object"
    rules = body.get("rules")
    if not isinstance(rules, list) or not rules:
        return "declaration needs a non-empty rules list"
    if len(rules) > MAX_RULES:
        return "too many rules (max " + str(MAX_RULES) + ")"
    seen = set()
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            return "rule " + str(i) + " is not an object"
        rid = str(r.get("id", "")).strip()
        if not rid:
            return "rule " + str(i) + " has no id"
        if rid in seen:
            return "duplicate rule id: " + rid
        seen.add(rid)
        req = r.get("require")
        if not isinstance(req, dict) or not req.get("field"):
            return "rule " + rid + " has no require.field"
        for part in ("when", "require"):
            c = r.get(part)
            if c is None:
                continue
            if not isinstance(c, dict):
                return "rule " + rid + ": " + part + " must be an object"
            if c.get("op", "==") not in OPS:
                return "rule " + rid + ": unknown op " + str(c.get("op"))
    return None


def _get(record, field):
    cur = record
    for part in str(field).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _test(cond, record):
    if not cond:
        return True
    val = _get(record, cond["field"])
    op = cond.get("op", "==")
    want = cond.get("value")
    if op == "exists":
        return (val is not None) == bool(want if want is not None else True)
    if val is None:
        return False
    try:
        if op == "==":
            return str(val).strip().lower() == str(want).strip().lower()
        if op == "!=":
            return str(val).strip().lower() != str(want).strip().lower()
        if op == "in":
            return str(val).strip().lower() in [str(x).strip().lower() for x in want]
        if op == "not_in":
            return str(val).strip().lower() not in [str(x).strip().lower() for x in want]
        v, w = float(val), float(want)
        if op == ">":
            return v > w
        if op == ">=":
            return v >= w
        if op == "<":
            return v < w
        if op == "<=":
            return v <= w
    except Exception:
        return False
    return False


def _current(ctx, api_key):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT version,body,sha256,published,audit_hash FROM declarations WHERE api_key=? ORDER BY version DESC LIMIT 1", (api_key,)).fetchone()


def _publish(ctx, api_key, data):
    body = data.get("declaration")
    if body is None:
        body = {k: v for k, v in data.items() if k != "declaration"}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"error": "declaration_not_json"}, 400
    err = _validate(body)
    if err:
        return {"error": "invalid_declaration", "detail": err}, 400

    prev = _current(ctx, api_key)
    ver = (prev[0] + 1) if prev else 1
    sha = _sha(body)
    if prev and prev[2] == sha:
        return {"error": "unchanged",
                "message": "Identical to version " + str(prev[0]) + ". Nothing to publish."}, 400

    ref = "V" + str(ver)
    ids = [str(r.get("id")) for r in body["rules"]]
    detail = ("version=" + str(ver) + ";sha256=" + sha + ";rules=" + str(len(ids)) +
              ";ids=" + ",".join(ids[:40]) +
              (";replaces=" + prev[2] if prev else ";first_declaration=true"))
    h, idx, seq, ts = _seal_event(ctx, api_key, ref, "published", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO declarations(api_key,version,body,sha256,published,audit_hash,block_index) VALUES(?,?,?,?,?,?,?)",
                            (api_key, ver, json.dumps(body), sha, ts, h, idx))
        ctx["conn"].commit()

    out = {"version": ver, "sha256": sha, "rules": len(ids), "rule_ids": ids,
           "published": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "Sealed. Every record from this point is judged against it, and this version cannot be removed."}
    if prev:
        out["replaces_version"] = prev[0]
        out["warning"] = "Version " + str(prev[0]) + " remains sealed and readable. Changes to your own standard are permanent and dated."
    return out, 200


def _current_view(ctx, api_key):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration",
                "message": "Nothing published yet."}, 404
    return {"version": row[0], "declaration": json.loads(row[1]),
            "sha256": row[2], "published": _iso(row[3]),
            "sealed": row[4]}, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT version,sha256,published,audit_hash,body FROM declarations WHERE api_key=? ORDER BY version ASC", (api_key,)).fetchall()
    if not rows:
        return {"count": 0, "versions": []}, 200
    out = []
    for v, sha, ts, ah, body in rows:
        try:
            n = len(json.loads(body).get("rules", []))
        except Exception:
            n = None
        out.append({"version": v, "sha256": sha, "published": _iso(ts),
                    "sealed": ah, "rules": n})
    return {"count": len(out), "versions": out,
            "note": "Every version ever published. Loosening a standard is visible here permanently."}, 200


def _check(ctx, api_key, data):
    row = _current(ctx, api_key)
    if not row:
        return {"error": "no_declaration"}, 404
    ver, body = row[0], json.loads(row[1])
    rules = body["rules"]

    try:
        limit = min(int(data.get("limit", 500)), 5000)
    except Exception:
        limit = 500

    with ctx["lock"]:
        recs = ctx["conn"].execute("SELECT id,user_id,event_json,result_json,ts FROM audit_log WHERE api_key=? AND ts>=? ORDER BY id DESC LIMIT ?", (api_key, row[3], limit)).fetchall()

    violations = []
    tested = 0
    for bid, uid, ev_json, res_json, bts in recs:
        try:
            rec = {}
            rec.update(json.loads(ev_json))
            rec.update(json.loads(res_json))
        except Exception:
            continue
        if rec.get("decision", "").endswith("_SEALED"):
            continue
        tested += 1
        for r in rules:
            if not _test(r.get("when"), rec):
                continue
            if not _test(r.get("require"), rec):
                violations.append({"block_index": bid, "record_id": uid,
                                   "rule": r.get("id"),
                                   "describe": r.get("describe"),
                                   "at": _iso(bts)})

    ts = time.time()
    cid = "CHK-" + _sha(str(ts) + api_key)[:8].upper()
    detail = ("decl_version=" + str(ver) + ";tested=" + str(tested) +
              ";violated=" + str(len(violations)) +
              ";rules=" + ",".join(sorted({v["rule"] for v in violations})[:20]))
    h, idx, seq, _x = _seal_event(ctx, api_key, cid, "checked", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO declare_checks(check_id,api_key,decl_version,ran,tested,passed,violated,detail,audit_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                            (cid, api_key, ver, ts, tested, tested - len({v["block_index"] for v in violations}), len(violations), json.dumps(violations[:200]), h))
        ctx["conn"].commit()

    out = {"check_id": cid, "declaration_version": ver, "records_tested": tested,
           "violations": len(violations), "ran_at": _iso(ts),
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "note": "Result sealed whichever way it went."}
    if violations:
        out["failed_rules"] = sorted({v["rule"] for v in violations})
        out["detail"] = violations[:20]
        out["flag"] = str(len(violations)) + " record(s) violate your own published rules"
    return out, 200


def _violations(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT check_id,decl_version,ran,tested,violated,detail FROM declare_checks WHERE api_key=? ORDER BY ran DESC LIMIT 50", (api_key,)).fetchall()
    if not rows:
        return {"checks": 0, "note": "No checks run yet."}, 200
    latest = rows[0]
    try:
        detail = json.loads(latest[5])
    except Exception:
        detail = []
    return {"checks": len(rows),
            "latest": {"check_id": latest[0], "declaration_version": latest[1],
                       "ran": _iso(latest[2]), "tested": latest[3],
                       "violations": latest[4], "detail": detail[:50]},
            "history": [{"check_id": r[0], "ran": _iso(r[2]), "tested": r[3],
                         "violations": r[4]} for r in rows]}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "publish":
            return _publish(ctx, api_key, data)
        if action == "check":
            return _check(ctx, api_key, data)
    else:
        if action == "current":
            return _current_view(ctx, api_key)
        if action == "history":
            return _history(ctx, api_key)
        if action == "violations":
            return _violations(ctx, api_key)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/demo.py`

358 lines, 15159 bytes

```python
"""
Public proving ground - /x/demo/<action>

WHY THIS EXISTS
---------------
Every page on this platform says "check it, don't trust it" and then asks for
an email address before anyone can check anything. That is the same bargain
every other vendor offers, dressed in better language.

This removes the bargain. No key, no account, no email. A visitor sends a
scenario, gets a real verdict from the live engine, and it is sealed into the
production chain - the same chain, the same sequence, covered by the same
external anchor. They get the block index back and can verify it themselves at
a public endpoint that has never heard of them.

The demonstration is not a simulation of the product. It IS the product, run
once, by a stranger, for free.

WHAT IS DELIBERATELY REAL
-------------------------
  - the scoring is the engine's own arithmetic, not a mock
  - the seal is a genuine block in the live chain
  - the counterfactual is computed by inverting the real function
  - the review flow really does withhold the verdict until commitment
  - the dwell time is really measured and really sealed

WHAT IS DELIBERATELY NOT REAL
-----------------------------
  - demo events do not touch any customer's trust history; user ids are
    namespaced to demo: and scored from a neutral starting trust
  - nothing about a visitor is recorded beyond what they typed

ABUSE
-----
Public routes are rate limited per client by the router. A visitor cannot
flood the chain, and the cost of a demo block is a few hundred bytes.

    POST /x/demo/govern   scenario -> verdict, seal, counterfactual
    POST /x/demo/review   open a review case, verdict withheld
    POST /x/demo/commit   commit a verdict, then see what the machine said
    GET  /x/demo/stats    how many people have tried it
"""

import json, math, secrets, time
from datetime import datetime, timezone

VERSION = "1.0"

# No key required for any of these - that is the entire point.
PUBLIC = {("POST", "govern"), ("POST", "review"), ("POST", "commit"),
          ("GET", "stats"), ("GET", "")}

DEMO_KEY = "public_demo"
LN_CAP = math.log1p(10000)
SAFE = {"UK", "US", "DE", "FR", "CA", "AU", "NL", "SE", "NO", "DK", "FI", "IE", "NZ"}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_cases(case_id TEXT PRIMARY KEY,opened REAL,material TEXT,machine_verdict TEXT,score REAL,committed REAL,human_verdict TEXT,dwell REAL)")
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS demo_stats(k TEXT PRIMARY KEY,v INTEGER)")
        ctx["conn"].commit()
    _ready = True


def _bump(ctx, k):
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_stats(k,v) VALUES(?,1) ON CONFLICT(k) DO UPDATE SET v=v+1", (k,))
        ctx["conn"].commit()


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _f(d, k, default=0.0):
    try:
        return float(d.get(k, default))
    except (TypeError, ValueError):
        return default


def _signals(data):
    country = str(data.get("country", "UK")).strip().upper()[:4] or "UK"
    return {
        "trust": _clamp(_f(data, "trust", 0.5)),
        "v60": max(0.0, min(_f(data, "v60"), 10000)),
        "v5m": max(0.0, min(_f(data, "v5m"), 10000)),
        "v1h": max(0.0, min(_f(data, "v1h"), 100000)),
        "amount": max(0.0, min(_f(data, "amount"), 10000000)),
        "device_risk": _clamp(_f(data, "device_risk")),
        "anomaly": _clamp(_f(data, "anomaly")),
        "country": country,
        "country_shift": bool(data.get("country_shift")),
        "unsafe_country": country not in SAFE,
    }


def _score(s):
    sc = (1 - s["trust"]) * 0.30
    sc += min(s["v60"] / 20.0, 1) * 0.15
    sc += min(s["v5m"] / 50.0, 1) * 0.10
    sc += min(s["v1h"] / 200.0, 1) * 0.10
    sc += min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15
    sc += s["device_risk"] * 0.10
    sc += s["anomaly"] * 0.10
    if s["country_shift"]:
        sc += 0.10
    if s["unsafe_country"]:
        sc += 0.10
    return round(_clamp(sc), 4)


def _reasons(s):
    r = []
    if s["trust"] < 0.4:
        r.append("low_trust")
    if s["v60"] > 10:
        r.append("velocity_spike")
    if s["amount"] > 500:
        r.append("high_amount")
    if s["device_risk"] > 0.5:
        r.append("risky_device")
    if s["anomaly"] > 0.5:
        r.append("behaviour_anomaly")
    if s["country_shift"]:
        r.append("country_shift")
    if s["unsafe_country"]:
        r.append("unsafe_country")
    return r


def _verdict(sc):
    if sc < 0.35:
        return "ALLOW"
    if sc < 0.70:
        return "CHALLENGE"
    return "BLOCK"


def _counterfactual(s, score, verdict):
    """Exact inversion. Returns the cheapest single change, or None."""
    if verdict == "ALLOW":
        return None, "Already the most permissive verdict."
    ceiling = 0.70 if verdict == "BLOCK" else 0.35
    target = "CHALLENGE" if verdict == "BLOCK" else "ALLOW"
    needed = score - ceiling + 0.0001

    contribs = [
        ("trust", (1 - s["trust"]) * 0.30),
        ("amount", min(math.log1p(s["amount"]) / LN_CAP, 1) * 0.15),
        ("v60", min(s["v60"] / 20.0, 1) * 0.15),
        ("v5m", min(s["v5m"] / 50.0, 1) * 0.10),
        ("v1h", min(s["v1h"] / 200.0, 1) * 0.10),
        ("device_risk", s["device_risk"] * 0.10),
        ("anomaly", s["anomaly"] * 0.10),
        ("country_shift", 0.10 if s["country_shift"] else 0.0),
        ("unsafe_country", 0.10 if s["unsafe_country"] else 0.0),
    ]
    contribs.sort(key=lambda kv: -kv[1])

    for name, c in contribs:
        if c <= 0 or c < needed:
            continue
        t = c - needed
        if name == "trust":
            v = 1 - (t / 0.30)
            if v <= 1.0:
                return {"factor": "trust", "required": round(_clamp(v), 3),
                        "was": round(s["trust"], 3)}, ("a trust score of "
                        + str(round(_clamp(v), 3)) + " instead of "
                        + str(round(s["trust"], 3)) + " would have made this "
                        + target)
        if name == "amount":
            v = math.expm1((t / 0.15) * LN_CAP)
            return {"factor": "amount", "required": round(v, 2),
                    "was": round(s["amount"], 2)}, ("an amount of "
                    + str(round(v, 2)) + " instead of " + str(round(s["amount"], 2))
                    + " would have made this " + target)
        if name in ("v60", "v5m", "v1h"):
            cap, w = {"v60": (20.0, 0.15), "v5m": (50.0, 0.10), "v1h": (200.0, 0.10)}[name]
            v = (t / w) * cap
            lbl = {"v60": "60-second", "v5m": "5-minute", "v1h": "1-hour"}[name]
            return {"factor": name, "required": int(v), "was": int(s[name])}, (
                "a " + lbl + " velocity of " + str(int(v)) + " instead of "
                + str(int(s[name])) + " would have made this " + target)
        if name in ("device_risk", "anomaly"):
            v = t / 0.10
            lbl = "device risk" if name == "device_risk" else "behavioural anomaly"
            return {"factor": name, "required": round(_clamp(v), 3), "was": round(s[name], 3)}, (
                "a " + lbl + " of " + str(round(_clamp(v), 3)) + " instead of "
                + str(round(s[name], 3)) + " would have made this " + target)
        if name in ("country_shift", "unsafe_country"):
            lbl = ("no country change from the previous event" if name == "country_shift"
                   else "an event from a jurisdiction on the safe list")
            return {"factor": name, "required": 0, "was": 1}, (
                lbl + " would have made this " + target)
    return None, ("no single factor, changed alone, would have reached "
                  + target + " - several drove this together")


def _govern(ctx, data):
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    reasons = _reasons(s)
    cf, cf_text = _counterfactual(s, score, verdict)

    ts = time.time()
    uid = "demo:" + secrets.token_hex(3)
    ev = {"user_id": uid, "action": str(data.get("action", "payment"))[:40],
          "amount": s["amount"], "country": s["country"],
          "device_id": "demo", "anomaly": s["anomaly"],
          "device_risk": s["device_risk"]}
    res = {"decision": verdict, "score": score, "reasons": reasons,
           "demo": True, "demo_version": VERSION, "timestamp": ts,
           "signals": {k: s[k] for k in ("trust", "v60", "v5m", "v1h",
                                          "country_shift", "unsafe_country")},
           "note": "public demonstration - sealed into the live chain like any other decision"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)
    _bump(ctx, "govern")

    return {"decision": verdict, "score": score, "reasons": reasons,
            "sealed_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "counterfactual": cf,
            "counterfactual_statement": cf_text,
            "verify": {
                "this_block": "/api/inclusion?hash=" + h,
                "whole_chain": "/api/verify-chain",
                "external_anchor": "/api/anchor-status"},
            "what_just_happened": [
                "Your scenario was scored by the live engine, not a simulation.",
                "The verdict was sealed into the production chain as block " + str(idx) + ".",
                "That block is now covered by the next external timestamp.",
                "Nothing about you was recorded. No account, no email, no key.",
                "Verify any of it at the links above - they have never heard of you."]}, 200


def _review(ctx, data):
    """Open a review case. The verdict is computed and sealed - and withheld."""
    s = _signals(data)
    score = _score(s)
    verdict = _verdict(score)
    cid = "DEMO-" + secrets.token_hex(4).upper()
    ts = time.time()
    material = {"action": str(data.get("action", "payment"))[:40],
                "amount": s["amount"], "country": s["country"],
                "60_second_velocity": int(s["v60"]),
                "5_minute_velocity": int(s["v5m"]),
                "device_risk": s["device_risk"],
                "behavioural_anomaly": s["anomaly"],
                "country_changed": s["country_shift"],
                "trust_history": round(s["trust"], 3)}
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO demo_cases(case_id,opened,material,machine_verdict,score,committed,human_verdict,dwell) VALUES(?,?,?,?,?,NULL,NULL,NULL)",
                            (cid, ts, json.dumps(material), verdict, score))
        ctx["conn"].commit()
    _bump(ctx, "review_opened")
    return {"case_id": cid, "opened": _iso(ts), "material": material,
            "machine_verdict": "withheld until you commit",
            "your_options": ["allow", "challenge", "block"],
            "instruction": "Decide for yourself, then POST your verdict to /x/demo/commit with this case_id. The clock is running and your answer is sealed before ours is shown."}, 200


def _commit(ctx, data):
    cid = str(data.get("case_id", "")).strip().upper()
    hv = str(data.get("verdict", "")).strip().upper()
    if hv not in ("ALLOW", "CHALLENGE", "BLOCK"):
        return {"error": "verdict_required", "allowed": ["allow", "challenge", "block"]}, 400
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT opened,material,machine_verdict,score,committed FROM demo_cases WHERE case_id=?", (cid,)).fetchone()
    if not row:
        return {"error": "unknown_case_id"}, 404
    if row[4]:
        return {"error": "already_committed",
                "message": "You commit once. That is the point of it."}, 400

    ts = time.time()
    dwell = round(ts - row[0], 2)
    agreed = (hv == row[2])

    ev = {"user_id": "demo:" + cid, "action": "demo_oversight_commit",
          "amount": 0, "country": "UK", "device_id": "demo",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "DEMO_OVERSIGHT_SEALED", "score": 0, "demo": True,
           "timestamp": ts, "human_verdict": hv, "dwell_seconds": dwell,
           "detail": "human verdict sealed before the machine verdict was revealed"}
    h, idx, seq = ctx["seal"](ev, res, ts, DEMO_KEY)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE demo_cases SET committed=?,human_verdict=?,dwell=? WHERE case_id=?",
                            (ts, hv, dwell, cid))
        ctx["conn"].commit()
    _bump(ctx, "review_committed")

    out = {"case_id": cid, "your_verdict": hv,
           "machine_verdict": row[2], "machine_score": row[3],
           "agreed": agreed, "dwell_seconds": dwell,
           "audit_hash": h, "block_index": idx, "receipt_seq": seq,
           "what_just_happened": [
               "Your verdict was sealed as block " + str(idx) + " BEFORE this response revealed ours.",
               "The chain fixes that order permanently and it cannot be reversed.",
               "Your dwell time of " + str(dwell) + "s is part of the record.",
               "That is the difference between a reviewer who decided and one who agreed."]}
    if dwell < 2:
        out["flag"] = ("committed in " + str(dwell) + " seconds - on a real system that would sit "
                       "in your record permanently, and a pattern of it would be visible to an auditor")
    if agreed:
        out["note"] = "You agreed with the engine - but the chain shows you did so without having seen it."
    else:
        out["note"] = "You diverged from the engine. On a real system that is evidence of independent judgement."
    return out, 200


def _stats(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT k,v FROM demo_stats").fetchall()
        cases = ctx["conn"].execute("SELECT COUNT(*),AVG(dwell) FROM demo_cases WHERE committed IS NOT NULL").fetchone()
        fast = ctx["conn"].execute("SELECT COUNT(*) FROM demo_cases WHERE dwell IS NOT NULL AND dwell<2").fetchone()
    d = {k: v for k, v in rows}
    out = {"decisions_run": d.get("govern", 0),
           "review_cases_opened": d.get("review_opened", 0),
           "review_cases_committed": d.get("review_committed", 0)}
    if cases and cases[0]:
        out["median_dwell_seconds"] = round(cases[1] or 0, 2)
        out["committed_under_2_seconds"] = fast[0] if fast else 0
        out["note"] = ("Visitors who committed in under two seconds did not read the case. "
                       "On a real deployment that is exactly what the record would show.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "govern":
            return _govern(ctx, data)
        if action == "review":
            return _review(ctx, data)
        if action == "commit":
            return _commit(ctx, data)
    else:
        if action in ("", "stats"):
            return _stats(ctx)
    return {"error": "unknown_action", "action": action,
            "available": ["POST govern", "POST review", "POST commit", "GET stats"]}, 404

```


## `modules/disclosure.py`

201 lines, 7648 bytes

```python
"""
disclosure.py v1.0.0 - the chain reset, put on the record inside the chain.

Lives at modules/disclosure.py and answers at https://sebbi.pro/x/disclosure/<action>.
All routes are public.

WHAT IT DOES
The audit chain restarted from genesis on 7 September 2026. Until now that
was said in messages and in route text, but not sealed. This module seals one
fixed statement about the reset into the chain, exactly once, and then serves
the block number so anyone can find it and recompute it.

The first visit to /status seals it. Every visit after that returns the same
block. Nothing is ever sealed twice, and the text cannot be changed by calling
the route - it is fixed in this file.

The statement is sealed under user_id "system_reset_disclosure", which is on
the public list in walk.py, so its full preimage is served at /x/walk and can be
recomputed by anyone.

Module contract: handle(method, action, data, api_key, ctx) -> (dict, status).
"""

import json
import threading
import time

VERSION = "1.0.0"
HOST = "https://sebbi.pro"
BASE = HOST + "/x/disclosure/"
USER_ID = "system_reset_disclosure"

RESET_DATE = "2026-09-07"

# If you still hold the final tip hash or block count of the chain as it stood
# before the reset, put them here before deploying. Left empty, the statement
# says plainly that they are not recorded in this disclosure.
PREVIOUS_CHAIN_FINAL_TIP = ""
PREVIOUS_CHAIN_FINAL_HEIGHT = ""

STATEMENT = (
    "On " + RESET_DATE + " the operator of sebbi.pro reset the audit chain and "
    "it restarted from genesis. Blocks sealed before that date are not part of "
    "this chain and cannot be verified against it. A block index quoted before "
    "that date belongs to the earlier chain; if the same number exists on this "
    "chain, it is a different block. Some records kept outside the chain from "
    "before the reset, including completeness period commitments, still quote "
    "block indexes from the earlier chain. This disclosure is sealed into the "
    "current chain so the break is on the record rather than something a "
    "verifier has to ask about."
)

_lock = threading.Lock()

PUBLIC = {("GET", "status"), ("GET", "statement"), ("GET", "spec")}


def _ensure_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS reset_disclosure("
        "id INTEGER PRIMARY KEY CHECK (id = 1), block_index INTEGER, "
        "audit_hash TEXT, ts REAL, statement_json TEXT)")
    conn.commit()


def _stored(conn):
    r = conn.execute(
        "SELECT block_index, audit_hash, ts, statement_json FROM reset_disclosure "
        "WHERE id = 1").fetchone()
    if not r:
        return None
    try:
        body = json.loads(r[3])
    except Exception:
        body = {}
    return {"block_index": r[0], "audit_hash": r[1], "ts": r[2], "statement": body}


def _genesis_hash(conn):
    r = conn.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1").fetchone()
    return r[0] if r else None


def _links(rec):
    idx = rec["block_index"]
    return {
        "block": HOST + "/x/walk/block?index=" + str(idx),
        "verify_method": HOST + "/x/walk/spec",
        "statement": BASE + "statement",
    }


def _seal_once(ctx):
    conn, dblock = ctx["conn"], ctx["lock"]
    with _lock:
        with dblock:
            _ensure_table(conn)
            rec = _stored(conn)
            if rec:
                return rec, False
            genesis = _genesis_hash(conn)
        body = {
            "kind": "chain_reset_disclosure",
            "reset_date": RESET_DATE,
            "current_chain_genesis_hash": genesis,
            "current_chain_genesis_block_index": 1,
            "previous_chain_final_tip": PREVIOUS_CHAIN_FINAL_TIP or "not recorded in this disclosure",
            "previous_chain_final_height": PREVIOUS_CHAIN_FINAL_HEIGHT or "not recorded in this disclosure",
            "statement": STATEMENT,
            "disclosure_version": VERSION,
        }
        ts = time.time()
        event = {
            "user_id": USER_ID,
            "action": "chain_reset_disclosed",
            "amount": 0,
            "country": "UK",
            "device_id": "server",
            "anomaly": 0,
            "device_risk": 0,
        }
        result = dict(body)
        result["decision"] = "DISCLOSED"
        result["score"] = 0
        result["timestamp"] = ts
        # ctx seal takes its own lock - do not hold the db lock here.
        out = ctx["seal"](event, result, ts)
        if isinstance(out, (list, tuple)):
            h = out[0]
            idx = out[1] if len(out) > 1 else None
        elif isinstance(out, dict):
            h = out.get("audit_hash") or out.get("hash")
            idx = out.get("block_index") or out.get("index")
        else:
            h, idx = out, None
        with dblock:
            conn.execute(
                "INSERT OR IGNORE INTO reset_disclosure(id, block_index, audit_hash, ts, statement_json) "
                "VALUES (1, ?, ?, ?, ?)", (idx, h, ts, json.dumps(body)))
            conn.commit()
            rec = _stored(conn)
        return rec, True


def _spec():
    return {
        "module": "disclosure",
        "version": VERSION,
        "purpose": "Seals one fixed statement about the " + RESET_DATE + " chain reset "
                   "into the current chain, once, and serves where it is.",
        "routes": {
            "status": BASE + "status",
            "statement": BASE + "statement",
            "spec": BASE + "spec",
        },
        "behaviour": "The first call to status seals the statement. Every later call "
                     "returns the same block. The text is fixed in the module and "
                     "cannot be changed through any route.",
        "verify": "Open the block link in the response. Its preimage is served in full; "
                  "sha256 of it must equal audit_hash, and its prev_hash must equal the "
                  "block before. Method: " + HOST + "/x/walk/spec",
    }


def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action == "spec":
            return _spec(), 200
        if method == "GET" and action == "status":
            rec, new = _seal_once(ctx)
            if not rec or rec.get("block_index") is None:
                return {"error": "seal_failed", "detail": "no block index returned"}, 500
            return {
                "module": "disclosure",
                "version": VERSION,
                "sealed": True,
                "sealed_just_now": new,
                "block_index": rec["block_index"],
                "audit_hash": rec["audit_hash"],
                "sealed_at": rec["ts"],
                "links": _links(rec),
                "statement": rec["statement"],
            }, 200
        if method == "GET" and action == "statement":
            conn, dblock = ctx["conn"], ctx["lock"]
            with dblock:
                _ensure_table(conn)
                rec = _stored(conn)
            if not rec:
                return {"sealed": False,
                        "note": "Not sealed yet. The first visit to " + BASE + "status seals it."}, 404
            return {"sealed": True, "block_index": rec["block_index"],
                    "audit_hash": rec["audit_hash"], "sealed_at": rec["ts"],
                    "links": _links(rec), "statement": rec["statement"]}, 200
        return {"error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET"),
                "post": [], "spec": BASE + "spec"}, 404
    except Exception as e:
        return {"error": "disclosure_failed", "detail": str(e)[:300]}, 500

```


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/earnpage.py`

293 lines, 21176 bytes

```python
"""
modules/earnpage.py  v1.0.1
The creator's withdrawal page at /earn, plus a "My earnings" button on the
homepage.

  /earn   claim a creator name (get a private key), see earnings and paid
          unlocks, link a bank through Stripe, withdraw to it, and see every
          past withdrawal with its proof in the chain.

Talks to modules/credits.py (v1.2.0 or later) over /c/creator/.

1.0.1: no longer touches the homepage at all. The homepage belongs to
index.html and homelink.py; the My earnings button goes in homelink.py.

Page module, same family as creditspage.py: a runtime do_GET patch.
Armed by /x/earnpage/status after each deploy.
"""

import base64
import io
import re
import sys

VERSION = "1.0.1"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk15IGVhcm5pbmdzIOKAlCBNb25vcCBTdHVkaW88L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0i"
    "WW91ciBNb25vcCBTdHVkaW8gZWFybmluZ3MuIEV2ZXJ5IHVubG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgc3RyYWlnaHQgdG8g"
    "eW91ciBiYW5rLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9VW5ib3VuZGVk"
    "OndnaHRANjAwOzgwMCZmYW1pbHk9RmlndHJlZTp3Z2h0QDUwMDs3MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8"
    "c3R5bGU+Cjpyb290ey0tYmc6IzJiM2JmZjstLWRlZXA6IzExMTY1ZTstLXBpbms6I2ZmM2Q4YjstLXN1bjojZmZlMTRkOy0tbWlu"
    "dDojM2RmZmIyOy0td2hpdGU6I2ZmZjstLXNvZnQ6cmdiYSgyNTUsMjU1LDI1NSwuNzgpOwotLWQ6J1VuYm91bmRlZCcsJ0FyaWFs"
    "IEJsYWNrJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXQ6J0ZpZ3RyZWUnLHN5c3RlbS11aSwtYXBwbGUtc3lzdGVtLCdTZWdvZSBV"
    "SScsc2Fucy1zZXJpZn0KQG1lZGlhIChwcmVmZXJzLWNvbG9yLXNjaGVtZTogZGFyayl7OnJvb3Q6bm90KFtkYXRhLXRoZW1lPSJs"
    "aWdodCJdKXstLWJnOiMyYjNiZmZ9fQo6cm9vdFtkYXRhLXRoZW1lPSJkYXJrIl17LS1iZzojMmIzYmZmfQo6cm9vdHtib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7cGFkZGluZy10b3A6ZW52KHNhZmUtYXJlYS1pbnNldC10b3AsMHB4KTtwYWRkaW5nLWJvdHRvbTplbnYo"
    "c2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwcHgpfQpodG1se3Njcm9sbC1wYWRkaW5nLXRvcDplbnYoc2FmZS1hcmVhLWluc2V0LXRv"
    "cCwwcHgpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdlYmtpdC10YXAtaGlnaGxpZ2h0LWNv"
    "bG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXdoaXRlKTtmb250LWZhbWlseTp2"
    "YXIoLS10KTtsaW5lLWhlaWdodDoxLjU7bWluLWhlaWdodDoxMDAlfQoud3JhcHttYXgtd2lkdGg6NTYwcHg7bWFyZ2luOjAgYXV0"
    "bztwYWRkaW5nOjE4cHggMjBweCA2MHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjth"
    "bGlnbi1pdGVtczpjZW50ZXI7Zm9udC13ZWlnaHQ6NzAwfQoudG9wIGF7Y29sb3I6dmFyKC0td2hpdGUpO3RleHQtZGVjb3JhdGlv"
    "bjpub25lO29wYWNpdHk6Ljg1O21hcmdpbi1sZWZ0OjE2cHg7Zm9udC1zaXplOjE0cHh9Ci5icmFuZHtmb250LWZhbWlseTp2YXIo"
    "LS1kKTtmb250LXNpemU6MTVweH0KaDF7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFt"
    "cCgzMHB4LDguNXZ3LDQ2cHgpO2xpbmUtaGVpZ2h0OjEuMDI7bWFyZ2luOjI2cHggMCAxMHB4fQoudGFne2Rpc3BsYXk6aW5saW5l"
    "LWJsb2NrO3BhZGRpbmc6LjA1ZW0gLjNlbTtib3JkZXItcmFkaXVzOi4xOGVtO3RyYW5zZm9ybTpyb3RhdGUoLTJkZWcpO2JhY2tn"
    "cm91bmQ6dmFyKC0tcGluayl9CnAubGVhZHtjb2xvcjp2YXIoLS1zb2Z0KTtmb250LXNpemU6MTdweDttYXgtd2lkdGg6NDRjaH0K"
    "LmNhcmR7YmFja2dyb3VuZDp2YXIoLS1kZWVwKTtib3JkZXItcmFkaXVzOjIycHg7cGFkZGluZzoyMnB4O21hcmdpbi10b3A6MThw"
    "eH0KLmNhcmQgaDJ7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC1zaXplOjE5cHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5jYXJkIHB7"
    "Y29sb3I6dmFyKC0tc29mdCk7Zm9udC1zaXplOjE1cHh9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQt"
    "c2l6ZToxNHB4O21hcmdpbjoxNHB4IDAgNnB4fQppbnB1dHt3aWR0aDoxMDAlO3BhZGRpbmc6MTVweCAxNnB4O2JvcmRlci1yYWRp"
    "dXM6MTRweDtib3JkZXI6MDtmb250OjcwMCAxN3B4IHZhcigtLXQpO2NvbG9yOnZhcigtLWRlZXApO2JhY2tncm91bmQ6I2ZmZn0K"
    "aW5wdXQ6Zm9jdXN7b3V0bGluZTozcHggc29saWQgdmFyKC0tc3VuKX0KYnV0dG9uLC5idG57ZGlzcGxheTppbmxpbmUtYmxvY2s7"
    "d2lkdGg6MTAwJTttYXJnaW4tdG9wOjE0cHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLXJhZGl1czo5OTlweDtib3JkZXI6MDtj"
    "dXJzb3I6cG9pbnRlcjsKIGZvbnQ6ODAwIDE2cHggdmFyKC0tZCk7YmFja2dyb3VuZDp2YXIoLS1zdW4pO2NvbG9yOiMxYTEzMDA7"
    "dGV4dC1hbGlnbjpjZW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmV9CmJ1dHRvbjpmb2N1cy12aXNpYmxlLC5idG46Zm9jdXMtdmlz"
    "aWJsZXtvdXRsaW5lOjNweCBzb2xpZCAjZmZmO291dGxpbmUtb2Zmc2V0OjNweH0KYnV0dG9uLnBpbmt7YmFja2dyb3VuZDp2YXIo"
    "LS1waW5rKTtjb2xvcjojZmZmfQpidXR0b24uZ2hvc3R7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlcjoy"
    "cHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuNCl9CmJ1dHRvbjpkaXNhYmxlZHtvcGFjaXR5Oi40NTtjdXJzb3I6bm90LWFsbG93"
    "ZWR9Ci5iYWx7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFtcCg1NHB4LDE3dncsODhw"
    "eCk7bGluZS1oZWlnaHQ6MTtjb2xvcjp2YXIoLS1zdW4pO21hcmdpbjo2cHggMCA0cHg7Zm9udC12YXJpYW50LW51bWVyaWM6dGFi"
    "dWxhci1udW1zfQoucm93e2Rpc3BsYXk6ZmxleDtnYXA6MTBweH0ucm93Pip7ZmxleDoxfQouc3RhdHtiYWNrZ3JvdW5kOnJnYmEo"
    "MjU1LDI1NSwyNTUsLjA4KTtib3JkZXItcmFkaXVzOjE2cHg7cGFkZGluZzoxMnB4IDE0cHh9Ci5zdGF0IGJ7ZGlzcGxheTpibG9j"
    "aztmb250LWZhbWlseTp2YXIoLS1kKTtmb250LXNpemU6MjJweH0uc3RhdCBzcGFue2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigt"
    "LXNvZnQpfQoua2V5Ym94e21hcmdpbi10b3A6MTJweDtiYWNrZ3JvdW5kOiNmZmY7Y29sb3I6dmFyKC0tZGVlcCk7Ym9yZGVyLXJh"
    "ZGl1czoxNHB4O3BhZGRpbmc6MTRweDtmb250OjcwMCAxNHB4IHVpLW1vbm9zcGFjZSxNZW5sbyxtb25vc3BhY2U7d29yZC1icmVh"
    "azpicmVhay1hbGx9Ci5tc2d7bWFyZ2luLXRvcDoxNHB4O3BhZGRpbmc6MTRweCAxNnB4O2JvcmRlci1yYWRpdXM6MTRweDtiYWNr"
    "Z3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjEyKTtmb250LXdlaWdodDo3MDA7ZGlzcGxheTpub25lfQoubXNnLm9ue2Rpc3BsYXk6"
    "YmxvY2t9Lm1zZy5nb29ke2JhY2tncm91bmQ6dmFyKC0tbWludCk7Y29sb3I6IzA3MzAxZn0ubXNnLmJhZHtiYWNrZ3JvdW5kOnZh"
    "cigtLXBpbmspfQouc3RhdGV7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweDtmb250LXdlaWdodDo3MDA7"
    "bWFyZ2luLXRvcDo2cHh9Ci5kb3R7d2lkdGg6MTJweDtoZWlnaHQ6MTJweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZh"
    "cigtLXN1bik7ZmxleDpub25lfS5kb3Qub2t7YmFja2dyb3VuZDp2YXIoLS1taW50KX0KLmxpc3QgZGl2e2Rpc3BsYXk6ZmxleDtq"
    "dXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtwYWRkaW5nOjEwcHggMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwy"
    "NTUsMjU1LC4xMik7Zm9udC1zaXplOjE1cHh9Ci5saXN0IGF7Y29sb3I6dmFyKC0tbWludCl9Ci5zbWFsbHtmb250LXNpemU6MTNw"
    "eDtjb2xvcjp2YXIoLS1zb2Z0KTttYXJnaW4tdG9wOjEwcHh9Ci5zbWFsbCBhe2NvbG9yOiNmZmZ9CltoaWRkZW5de2Rpc3BsYXk6"
    "bm9uZSFpbXBvcnRhbnR9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0b3AiPjxk"
    "aXYgY2xhc3M9ImJyYW5kIj5Nb25vcCBTdHVkaW88L2Rpdj48bmF2PjxhIGhyZWY9Ii9jcmVhdGUiPlN0dWRpbzwvYT48YSBocmVm"
    "PSIvY2luZW1hIj5DaW5lbWE8L2E+PGEgaHJlZj0iLyI+SG9tZTwvYT48L25hdj48L2Rpdj4KCjxzZWN0aW9uIGlkPSJqb2luIiBo"
    "aWRkZW4+CiAgPGgxPkdldCBwYWlkIGZvciA8c3BhbiBjbGFzcz0idGFnIj55b3VyIHZpZGVvcy48L3NwYW4+PC9oMT4KICA8cCBj"
    "bGFzcz0ibGVhZCI+Q2xhaW0geW91ciBjcmVhdG9yIG5hbWUsIGxvY2sgeW91ciB2aWRlb3Mgd2l0aCBpdCwgYW5kIGV2ZXJ5IHVu"
    "bG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgdG8geW91ciBiYW5rIHdoZW5ldmVyIHlvdSBsaWtlLjwvcD4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj4KICAgIDxoMj5DbGFpbSB5b3VyIGNyZWF0b3IgbmFtZTwvaDI+CiAgICA8cD5Vc2UgZXhhY3RseSB0aGlzIG5hbWUg"
    "aW4gdGhlIHN0dWRpbyB3aGVuIHlvdSBsb2NrIGEgdmlkZW8uIFRoYXQncyBob3cgeW91ciBlYXJuaW5ncyBmaW5kIHlvdS48L3A+"
    "CiAgICA8bGFiZWwgZm9yPSJuYW1lIj5DcmVhdG9yIG5hbWU8L2xhYmVsPgogICAgPGlucHV0IGlkPSJuYW1lIiBtYXhsZW5ndGg9"
    "IjQwIiBhdXRvY29tcGxldGU9Im9mZiIgcGxhY2Vob2xkZXI9ImUuZy4gS2lja2ZsaXBLYWkiPgogICAgPGJ1dHRvbiBpZD0iam9p"
    "bkJ0biI+Q2xhaW0gbXkgbmFtZTwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgPGgyPkFscmVhZHkg"
    "aGF2ZSBhIGtleT88L2gyPgogICAgPHA+U2lnbiBpbiBvbiB0aGlzIGRldmljZSB3aXRoIHRoZSBrZXkgeW91IHNhdmVkLjwvcD4K"
    "ICAgIDxsYWJlbCBmb3I9ImtleUluIj5Zb3VyIGtleTwvbGFiZWw+CiAgICA8aW5wdXQgaWQ9ImtleUluIiBhdXRvY29tcGxldGU9"
    "Im9mZiIgcGxhY2Vob2xkZXI9ImNrX+KApiI+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImtleUJ0biI+U2lnbiBpbjwv"
    "YnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9Im1zZyIgaWQ9ImpvaW5Nc2ciPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlv"
    "biBpZD0ic2F2ZWQiIGhpZGRlbj4KICA8aDE+U2F2ZSA8c3BhbiBjbGFzcz0idGFnIj55b3VyIGtleS48L3NwYW4+PC9oMT4KICA8"
    "cCBjbGFzcz0ibGVhZCI+VGhpcyBrZXkgaXMgaG93IHlvdSB3aXRoZHJhdyB5b3VyIG1vbmV5LiBJdCdzIHNhdmVkIG9uIHRoaXMg"
    "cGhvbmUsIGJ1dCBrZWVwIGEgY29weSBzb21ld2hlcmUgc2FmZS4gSWYgeW91IGxvc2UgaXQsIG5vYm9keSBjYW4gZ2V0IHlvdXIg"
    "ZWFybmluZ3MgYmFjay48L3A+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDIgaWQ9InNhdmVkTmFtZSI+PC9oMj4KICAgIDxk"
    "aXYgY2xhc3M9ImtleWJveCIgaWQ9InNhdmVkS2V5Ij48L2Rpdj4KICAgIDxidXR0b24gaWQ9ImNvcHlCdG4iPkNvcHkgbXkga2V5"
    "PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImRvbmVCdG4iPkkndmUgc2F2ZWQgaXQ8L2J1dHRvbj4KICA8"
    "L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9ImRhc2giIGhpZGRlbj4KICA8aDEgaWQ9ImhlbGxvIj5Zb3VyIGVhcm5pbmdz"
    "PC9oMT4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgIDxwPlJlYWR5IHRvIHdpdGhkcmF3PC9wPgogICAgPGRpdiBjbGFzcz0iYmFs"
    "IiBpZD0iYmFsIj7CozAuMDA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiIGlkPSJ2aWV3cyI+MDwvYj48c3Bhbj5wYWlkIHVubG9ja3M8L3NwYW4+PC9kaXY+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiPjdwPC9iPjxzcGFuPnBlciB1bmxvY2s8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rp"
    "dj4KICA8ZGl2IGNsYXNzPSJjYXJkIiBpZD0icGF5Q2FyZCI+CiAgICA8aDI+V2l0aGRyYXcgdG8geW91ciBiYW5rPC9oMj4KICAg"
    "IDxkaXYgY2xhc3M9InN0YXRlIj48c3BhbiBjbGFzcz0iZG90IiBpZD0iZG90Ij48L3NwYW4+PHNwYW4gaWQ9InN0YXRlVGV4dCI+"
    "Q2hlY2tpbmfigKY8L3NwYW4+PC9kaXY+CiAgICA8YnV0dG9uIGlkPSJzZXR1cEJ0biIgaGlkZGVuPlNldCB1cCBwYXlvdXRzPC9i"
    "dXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJwaW5rIiBpZD0id2l0aGRyYXdCdG4iIGhpZGRlbj5XaXRoZHJhdzwvYnV0dG9uPgog"
    "ICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiIGlkPSJzdHJpcGVCdG4iIGhpZGRlbj5PcGVuIG15IFN0cmlwZSBhY2NvdW50PC9idXR0"
    "b24+CiAgICA8cCBjbGFzcz0ic21hbGwiIGlkPSJwYXlOb3RlIj5QYXlvdXRzIGdvIHRocm91Z2ggU3RyaXBlLCBzdHJhaWdodCB0"
    "byB5b3VyIGJhbmsuIFVuZGVyIDE4PyBBIHBhcmVudCBvciBndWFyZGlhbiBzZXRzIHRoaXMgdXAgd2l0aCB0aGVpciBkZXRhaWxz"
    "LjwvcD4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJtc2ciIGlkPSJkYXNoTXNnIj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj4K"
    "ICAgIDxoMj5QYXN0IHdpdGhkcmF3YWxzPC9oMj4KICAgIDxkaXYgY2xhc3M9Imxpc3QiIGlkPSJsaXN0Ij48cD5Ob25lIHlldC48"
    "L3A+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDI+TG9jayBhIHZpZGVvPC9oMj4KICAgIDxwPklu"
    "IHRoZSBzdHVkaW8sIHB1dCA8YiBpZD0ibmFtZUhpbnQiPjwvYj4gYXMgdGhlIGNyZWF0b3IgbmFtZSBzbyBldmVyeSB1bmxvY2sg"
    "cGF5cyB5b3UuPC9wPgogICAgPGEgY2xhc3M9ImJ0biIgaHJlZj0iL2NyZWF0ZSI+T3BlbiB0aGUgc3R1ZGlvPC9hPgogIDwvZGl2"
    "PgogIDxwIGNsYXNzPSJzbWFsbCI+U2lnbmVkIGluIG9uIHRoaXMgZGV2aWNlLiA8YSBocmVmPSIjIiBpZD0ib3V0QnRuIj5TaWdu"
    "IG91dDwvYT48L3A+Cjwvc2VjdGlvbj4KPC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewoidXNlIHN0cmljdCI7CnZhciBBUEk9"
    "Ii9jL2NyZWF0b3IvIiwgSz0ic2ViYmkuY3JlYXRvciI7CmZ1bmN0aW9uICQoaSl7cmV0dXJuIGRvY3VtZW50LmdldEVsZW1lbnRC"
    "eUlkKGkpfQpmdW5jdGlvbiBsb2FkKCl7dHJ5e3JldHVybiBKU09OLnBhcnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKEspfHwibnVs"
    "bCIpfWNhdGNoKGUpe3JldHVybiBudWxsfX0KZnVuY3Rpb24gc2F2ZSh2KXt0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oSyxKU09O"
    "LnN0cmluZ2lmeSh2KSl9Y2F0Y2goZSl7fX0KZnVuY3Rpb24gZ2JwKHApe3A9cHx8MDtyZXR1cm4gIsKjIitNYXRoLmZsb29yKHAv"
    "MTAwKSsiLiIrKCIwIisocCUxMDApKS5zbGljZSgtMil9CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2Uo"
    "L1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybiB7IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7"
    "In1bY119KX0KZnVuY3Rpb24gc2F5KGlkLHRleHQsa2luZCl7dmFyIG09JChpZCk7bS5jbGFzc05hbWU9Im1zZyBvbiIrKGtpbmQ/"
    "IiAiK2tpbmQ6IiIpO20udGV4dENvbnRlbnQ9dGV4dH0KZnVuY3Rpb24gcG9zdCh3aGF0LGJvZHkpe3JldHVybiBmZXRjaChBUEkr"
    "d2hhdCx7bWV0aG9kOiJQT1NUIixoZWFkZXJzOnsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiJ9LGJvZHk6SlNPTi5z"
    "dHJpbmdpZnkoYm9keSl9KQogLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpLnRoZW4oZnVuY3Rpb24oZCl7ZC5fb2s9"
    "ci5vaztyZXR1cm4gZH0pfSl9CmZ1bmN0aW9uIHZpZXcodil7WyJqb2luIiwic2F2ZWQiLCJkYXNoIl0uZm9yRWFjaChmdW5jdGlv"
    "bihzKXskKHMpLmhpZGRlbj0ocyE9PXYpfSk7d2luZG93LnNjcm9sbFRvKDAsMCl9CnZhciBtZT1sb2FkKCksIGRhdGE9bnVsbDsK"
    "CmZ1bmN0aW9uIHJlZnJlc2goKXsKICByZXR1cm4gcG9zdCgibWUiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXsKICAg"
    "IGlmKCFkLl9vayl7IGlmKGQuZXJyb3I9PT0iYmFkX2tleSIpe21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIik7c2F5KCJq"
    "b2luTXNnIiwiVGhhdCBrZXkgd2Fzbid0IHJlY29nbmlzZWQuIFNpZ24gaW4gYWdhaW4uIiwiYmFkIil9IHJldHVybiB9CiAgICBk"
    "YXRhPWQ7IHZpZXcoImRhc2giKTsKICAgICQoImhlbGxvIikudGV4dENvbnRlbnQ9IkhpICIrZC5uYW1lOwogICAgJCgibmFtZUhp"
    "bnQiKS50ZXh0Q29udGVudD1kLm5hbWU7CiAgICAkKCJiYWwiKS50ZXh0Q29udGVudD1nYnAoZC5iYWxhbmNlX3BlbmNlKTsKICAg"
    "ICQoInZpZXdzIikudGV4dENvbnRlbnQ9KGQucGFpZF92aWV3c3x8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUdCIik7CiAgICB2YXIg"
    "c2I9JCgic2V0dXBCdG4iKSx3Yj0kKCJ3aXRoZHJhd0J0biIpLHN0PSQoInN0cmlwZUJ0biIpLGRvdD0kKCJkb3QiKSx0eD0kKCJz"
    "dGF0ZVRleHQiKTsKICAgIHNiLmhpZGRlbj13Yi5oaWRkZW49c3QuaGlkZGVuPXRydWU7ZG90LmNsYXNzTmFtZT0iZG90IjsKICAg"
    "IGlmKCFkLnBheW91dHNfcmVhZHlfb25fc2l0ZSl7dHgudGV4dENvbnRlbnQ9IlBheW91dHMgYXJlIGJlaW5nIHN3aXRjaGVkIG9u"
    "LiBZb3VyIGVhcm5pbmdzIGFyZSBzYWZlIG9uIHlvdXIgYmFsYW5jZS4ifQogICAgZWxzZSBpZighZC5iYW5rX2xpbmtlZCl7dHgu"
    "dGV4dENvbnRlbnQ9Ik5vIGJhbmsgbGlua2VkIHlldC4iO3NiLmhpZGRlbj1mYWxzZTtzYi50ZXh0Q29udGVudD0iU2V0IHVwIHBh"
    "eW91dHMifQogICAgZWxzZSBpZighZC5wYXlvdXRzX2VuYWJsZWQpe3R4LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/"
    "IlN0cmlwZSBpcyBjaGVja2luZyB5b3VyIGRldGFpbHMuIjoiU2V0dXAgbm90IGZpbmlzaGVkLiI7c2IuaGlkZGVuPWZhbHNlO3Ni"
    "LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/IkNoZWNrIG15IGRldGFpbHMiOiJGaW5pc2ggc2V0dXAifQogICAgZWxz"
    "ZXsKICAgICAgZG90LmNsYXNzTmFtZT0iZG90IG9rIjt0eC50ZXh0Q29udGVudD0iQmFuayBsaW5rZWQuIFJlYWR5IHRvIHBheSBv"
    "dXQuIjtzdC5oaWRkZW49ZmFsc2U7d2IuaGlkZGVuPWZhbHNlOwogICAgICBpZihkLmJhbGFuY2VfcGVuY2U+PWQubWluX3dpdGhk"
    "cmF3X3BlbmNlKXt3Yi5kaXNhYmxlZD1mYWxzZTt3Yi50ZXh0Q29udGVudD0iV2l0aGRyYXcgIitnYnAoZC5iYWxhbmNlX3BlbmNl"
    "KX0KICAgICAgZWxzZXt3Yi5kaXNhYmxlZD10cnVlO3diLnRleHRDb250ZW50PSJXaXRoZHJhdyBmcm9tICIrZ2JwKGQubWluX3dp"
    "dGhkcmF3X3BlbmNlKX0KICAgIH0KICAgIHZhciBMPSQoImxpc3QiKTsKICAgIGlmKCFkLnBheW91dHN8fCFkLnBheW91dHMubGVu"
    "Z3RoKXtMLmlubmVySFRNTD0iPHA+Tm9uZSB5ZXQuPC9wPiJ9CiAgICBlbHNle0wuaW5uZXJIVE1MPWQucGF5b3V0cy5tYXAoZnVu"
    "Y3Rpb24ocCl7CiAgICAgIHZhciB3aGVuPXAuYXQuc2xpY2UoMCwxMCksIHM9cC5zdGF0dXM9PT0ic2VudCI/IlNlbnQiOihwLnN0"
    "YXR1cz09PSJmYWlsZWQiPyJEaWRuJ3QgZ28gdGhyb3VnaCwgcmV0dXJuZWQiOiJTZW5kaW5nIik7CiAgICAgIHZhciBwcm9vZj1w"
    "LmJsb2NrX2luZGV4IT1udWxsPycgwrcgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8veC93YWxrL2Jsb2NrP2luZGV4PScrcC5i"
    "bG9ja19pbmRleCsnIj5wcm9vZjwvYT4nOiIiOwogICAgICByZXR1cm4gIjxkaXY+PHNwYW4+Iit3aGVuKyIgwrcgIitzK3Byb29m"
    "KyI8L3NwYW4+PGI+IitnYnAocC5wZW5jZSkrIjwvYj48L2Rpdj4ifSkuam9pbigiIil9CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtz"
    "YXkoImRhc2hNc2ciLCJDb3VsZG4ndCByZWFjaCBzZWJiaS5wcm8uIENoZWNrIHlvdXIgY29ubmVjdGlvbi4iLCJiYWQiKX0pOwp9"
    "CgpmdW5jdGlvbiBnb1N0cmlwZSgpewogIHNheSgiZGFzaE1zZyIsIk9wZW5pbmcgU3RyaXBl4oCmIik7CiAgcG9zdCgiY29ubmVj"
    "dCIse2tleTptZS5rZXl9KS50aGVuKGZ1bmN0aW9uKGQpeyBpZihkLnVybCl7bG9jYXRpb24uaHJlZj1kLnVybH0gZWxzZSBzYXko"
    "ImRhc2hNc2ciLGQubWVzc2FnZXx8IkNvdWxkbid0IG9wZW4gU3RyaXBlIGp1c3Qgbm93LiIsImJhZCIpIH0pCiAgLmNhdGNoKGZ1"
    "bmN0aW9uKCl7c2F5KCJkYXNoTXNnIiwiQ291bGRuJ3QgcmVhY2ggc2ViYmkucHJvLiIsImJhZCIpfSk7Cn0KCiQoImpvaW5CdG4i"
    "KS5vbmNsaWNrPWZ1bmN0aW9uKCl7CiAgdmFyIG49JCgibmFtZSIpLnZhbHVlLnRyaW0oKTsgaWYobi5sZW5ndGg8Myl7c2F5KCJq"
    "b2luTXNnIiwiUGljayBhIG5hbWUgb2YgYXQgbGVhc3QgMyBsZXR0ZXJzIG9yIG51bWJlcnMuIiwiYmFkIik7cmV0dXJufQogIHRo"
    "aXMuZGlzYWJsZWQ9dHJ1ZTt2YXIgYj10aGlzOwogIHBvc3QoImpvaW4iLHtuYW1lOm59KS50aGVuKGZ1bmN0aW9uKGQpe2IuZGlz"
    "YWJsZWQ9ZmFsc2U7CiAgICBpZighZC5fb2spe3NheSgiam9pbk1zZyIsZC5tZXNzYWdlfHwiQ291bGRuJ3QgY2xhaW0gdGhhdCBu"
    "YW1lLiIsImJhZCIpO3JldHVybn0KICAgIG1lPXtrZXk6ZC5rZXksbmFtZTpkLm5hbWUsaWQ6ZC5jcmVhdG9yX2lkfTtzYXZlKG1l"
    "KTsKICAgICQoInNhdmVkTmFtZSIpLnRleHRDb250ZW50PWQubmFtZTskKCJzYXZlZEtleSIpLnRleHRDb250ZW50PWQua2V5O3Zp"
    "ZXcoInNhdmVkIik7CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtiLmRpc2FibGVkPWZhbHNlO3NheSgiam9pbk1zZyIsIkNvdWxkbid0"
    "IHJlYWNoIHNlYmJpLnByby4iLCJiYWQiKX0pOwp9OwokKCJrZXlCdG4iKS5vbmNsaWNrPWZ1bmN0aW9uKCl7dmFyIGs9JCgia2V5"
    "SW4iKS52YWx1ZS50cmltKCk7aWYoIWspcmV0dXJuO21lPXtrZXk6a307c2F2ZShtZSk7cmVmcmVzaCgpfTsKJCgiY29weUJ0biIp"
    "Lm9uY2xpY2s9ZnVuY3Rpb24oKXt2YXIgaz1tZSYmbWUua2V5O2lmKCFrKXJldHVybjsKICAobmF2aWdhdG9yLmNsaXBib2FyZD9u"
    "YXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChrKTpQcm9taXNlLnJlamVjdCgpKS50aGVuKGZ1bmN0aW9uKCl7JCgiY29weUJ0"
    "biIpLnRleHRDb250ZW50PSJDb3BpZWQifSxmdW5jdGlvbigpeyQoImNvcHlCdG4iKS50ZXh0Q29udGVudD0iUHJlc3MgYW5kIGhv"
    "bGQgdGhlIGtleSB0byBjb3B5IGl0In0pfTsKJCgiZG9uZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtyZWZyZXNoKCl9OwokKCJz"
    "ZXR1cEJ0biIpLm9uY2xpY2s9Z29TdHJpcGU7CiQoInN0cmlwZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtwb3N0KCJkYXNoYm9h"
    "cmQiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtpZihkLnVybClsb2NhdGlvbi5ocmVmPWQudXJsO2Vsc2Ugc2F5KCJk"
    "YXNoTXNnIixkLm1lc3NhZ2V8fCJDb3VsZG4ndCBvcGVuIFN0cmlwZS4iLCJiYWQiKX0pfTsKJCgid2l0aGRyYXdCdG4iKS5vbmNs"
    "aWNrPWZ1bmN0aW9uKCl7CiAgdmFyIGI9dGhpcztiLmRpc2FibGVkPXRydWU7Yi50ZXh0Q29udGVudD0iU2VuZGluZ+KApiI7CiAg"
    "cG9zdCgid2l0aGRyYXciLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtzYXkoImRhc2hNc2ciLGQubWVzc2FnZXx8KGQu"
    "cGFpZD8iU2VudC4iOiJEaWRuJ3QgZ28gdGhyb3VnaC4iKSxkLnBhaWQ/Imdvb2QiOiJiYWQiKTtyZWZyZXNoKCl9KQogIC5jYXRj"
    "aChmdW5jdGlvbigpe3NheSgiZGFzaE1zZyIsIkNvdWxkbid0IHJlYWNoIHNlYmJpLnByby4gTm90aGluZyB3YXMgdGFrZW4gZnJv"
    "bSB5b3VyIGJhbGFuY2UuIiwiYmFkIik7cmVmcmVzaCgpfSk7Cn07CiQoIm91dEJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oZSl7ZS5w"
    "cmV2ZW50RGVmYXVsdCgpO21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIil9OwoKdmFyIHE9bG9jYXRpb24uc2VhcmNoOwpp"
    "ZihtZSYmbWUua2V5KXsKICByZWZyZXNoKCkudGhlbihmdW5jdGlvbigpewogICAgaWYoL1s/Jl1yZXRyeT0xLy50ZXN0KHEpKSBn"
    "b1N0cmlwZSgpOwogICAgZWxzZSBpZigvWz8mXWNvbm5lY3RlZD0xLy50ZXN0KHEpKSBzYXkoImRhc2hNc2ciLCJUaGFua3MuIFN0"
    "cmlwZSBoYXMgeW91ciBkZXRhaWxzLiBJdCBjYW4gdGFrZSBhIGZldyBtaW51dGVzIGZvciB0aGVtIHRvIGJlIGNoZWNrZWQuIiwi"
    "Z29vZCIpOwogICAgdHJ5e2hpc3RvcnkucmVwbGFjZVN0YXRlKG51bGwsIiIsbG9jYXRpb24ucGF0aG5hbWUpfWNhdGNoKGUpe30K"
    "ICB9KTsKfSBlbHNlIHZpZXcoImpvaW4iKTsKfSkoKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/earn": (_d(_HTML_B64), "text/html; charset=utf-8"),
}

_BUTTON = (
    b'<a id="sebbi-earn-btn" href="/earn" style="position:fixed;right:14px;'
    b'bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'display:flex;align-items:center;gap:8px;padding:12px 16px;border-radius:999px;'
    b'background:#ffe14d;color:#1a1300;font:800 14px system-ui,-apple-system,Segoe UI,sans-serif;'
    b'text-decoration:none;box-shadow:0 6px 20px rgba(0,0,0,.35)">'
    b'<span style="display:grid;place-items:center;width:24px;height:24px;border-radius:50%;'
    b'background:#ff3d8b;color:#fff;font-size:13px">&pound;</span>My earnings</a>'
)

_HOME_PATHS = ("/", "/index.html")
_patched = False


def _inject(raw):
    """Add the button to a captured homepage response. Returns raw unchanged if unsure."""
    try:
        sep = raw.find(b"\r\n\r\n")
        if sep < 0:
            return raw
        head, body = raw[:sep], raw[sep + 4:]
        low = head.lower()
        if b"text/html" not in low or b"content-encoding" in low or b"transfer-encoding" in low:
            return raw
        if b"sebbi-earn-btn" in body:
            return raw
        i = body.lower().rfind(b"</body>")
        if i < 0:
            return raw
        body = body[:i] + _BUTTON + body[i:]
        if re.search(rb"(?im)^content-length:", head):
            head = re.sub(rb"(?im)^(content-length:)\s*\d+", b"\\g<1> " + str(len(body)).encode(), head)
        return head + b"\r\n\r\n" + body
    except Exception:
        return raw


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
    if getattr(cls, "_earnpage_patched", False):
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
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._earnpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "earnpage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys()), "homepage_button": False}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
