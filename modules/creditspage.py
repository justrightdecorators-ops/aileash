"""
modules/creditspage.py  v1.0.0
The viewer's credit page at /credits: top up once, then unlock locked videos
anywhere with a tap. Talks to modules/credits.py over /c/.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/creditspage/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPllvdXIgY3JlZGl0IOKAlCBzZWJiaS5wcm88L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0iVG9w"
    "IHVwIG9uY2UsIHVubG9jayBhbnkgbG9ja2VkIHZpZGVvIHdpdGggYSB0YXAuIEV2ZXJ5IHBhaWQgdmlldyBpcyBzZWFsZWQgb24g"
    "YSBwdWJsaWMgY2hhaW4uIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1JQk0r"
    "UGxleCtNb25vOndnaHRANDAwOzUwMDs2MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMCZmYW1pbHk9TmV3"
    "c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgo6cm9vdHst"
    "LWluazojMDUwNzBmOy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLXBpbms6I2Q1OWJmZjstLW11dGU6IzhhOTNhZDstLWxp"
    "bmU6cmdiYSgyMDEsMTY4LDc2LC4yMik7LS1tb25vOidJQk0gUGxleCBNb25vJyx1aS1tb25vc3BhY2UsbW9ub3NwYWNlOy0tc2Fu"
    "czonSUJNIFBsZXggU2Fucycsc3lzdGVtLXVpLHNhbnMtc2VyaWY7LS1zZXJpZjonTmV3c3JlYWRlcicsR2VvcmdpYSxzZXJpZn0K"
    "Kntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowOy13ZWJraXQtdGFwLWhpZ2hsaWdodC1jb2xvcjp0cmFu"
    "c3BhcmVudH0KYm9keXtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAwJSwjMTUxYTNlLCMwNTA3MGYg"
    "NjIlKTtjb2xvcjojZThlZGY3O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2xpbmUtaGVpZ2h0OjEuNjttaW4taGVpZ2h0OjEwMHZo"
    "fQoud3JhcHttYXgtd2lkdGg6NzIwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjAgMjBweCA3MHB4fQoudG9we2Rpc3BsYXk6Zmxl"
    "eDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYo"
    "c2FmZS1hcmVhLWluc2V0LXRvcCkpIDAgMH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fS5i"
    "cmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBhe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2Zv"
    "bnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO3RleHQtZGVjb3JhdGlvbjpub25lO21hcmdpbi1sZWZ0OjE0cHh9Cmgxe2Zv"
    "bnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDMwcHgsNi40dncsNDhweCk7bWFy"
    "Z2luOjI2cHggMCA4cHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQoOTBkZWcsI2ZmZiwjYzlhODRjIDQ1JSwjN2ZlM2IwKTst"
    "d2Via2l0LWJhY2tncm91bmQtY2xpcDp0ZXh0O2JhY2tncm91bmQtY2xpcDp0ZXh0O2NvbG9yOnRyYW5zcGFyZW50fQpwLmxlYWR7"
    "Y29sb3I6I2I2YzBkNjttYXgtd2lkdGg6NTJjaH0KLmJhbGFuY2V7bWFyZ2luOjI2cHggMDt0ZXh0LWFsaWduOmNlbnRlcjtiYWNr"
    "Z3JvdW5kOnJnYmEoMTMsMjAsMzYsLjg1KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MThweDtw"
    "YWRkaW5nOjI2cHh9Ci5iYWxhbmNlIC5ue2ZvbnQ6NjAwIDU2cHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tb2spO2xpbmUtaGVp"
    "Z2h0OjF9Ci5iYWxhbmNlIC5se2ZvbnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7bGV0dGVyLXNwYWNpbmc6LjE2ZW07Y29sb3I6dmFy"
    "KC0tbXV0ZSk7bWFyZ2luLXRvcDo2cHh9Ci5vcHRze2Rpc3BsYXk6Z3JpZDtnYXA6MTBweDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6"
    "cmVwZWF0KDIsMWZyKTttYXJnaW4tdG9wOjE4cHh9CkBtZWRpYShtaW4td2lkdGg6NjIwcHgpey5vcHRze2dyaWQtdGVtcGxhdGUt"
    "Y29sdW1uczpyZXBlYXQoNCwxZnIpfX0KLm9wdHtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjg1KTtib3JkZXI6MXB4IHNvbGlk"
    "IHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE2cHg7dGV4dC1hbGlnbjpjZW50ZXI7Y3Vyc29yOnBvaW50"
    "ZXJ9Ci5vcHQuaG90e2JvcmRlci1jb2xvcjp2YXIoLS1nb2xkKTtib3gtc2hhZG93OjAgMCAyNHB4IHJnYmEoMjAxLDE2OCw3Niwu"
    "MjIpfQoub3B0IGJ7ZGlzcGxheTpibG9jaztmb250OjYwMCAyMnB4IHZhcigtLW1vbm8pO2NvbG9yOiNmZmZ9Lm9wdCBzcGFue2Zv"
    "bnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tbXV0ZSl9Ci5vdXR7bWFyZ2luLXRvcDoxOHB4O2JhY2tncm91bmQ6"
    "IzAzMDUwYjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjE2cHg7Zm9udDox"
    "M3B4IHZhcigtLW1vbm8pO2NvbG9yOiNjZmU2ZDk7ZGlzcGxheTpub25lfQoub3V0Lm9ue2Rpc3BsYXk6YmxvY2t9Lm91dCBhe2Nv"
    "bG9yOnZhcigtLW9rKX0KLmNhcmR7YmFja2dyb3VuZDpyZ2JhKDEzLDIwLDM2LC44KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxp"
    "bmUpO2JvcmRlci1yYWRpdXM6MTRweDtwYWRkaW5nOjE4cHg7bWFyZ2luLXRvcDoxNHB4fQouY2FyZCBoM3tmb250LWZhbWlseTp2"
    "YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToxOXB4O21hcmdpbi1ib3R0b206NnB4fS5jYXJkIHB7Zm9udC1z"
    "aXplOjE0cHg7Y29sb3I6I2I2YzBkNn0KLmhpc3R7bWFyZ2luLXRvcDoxMHB4O2ZvbnQ6MTJweCB2YXIoLS1tb25vKTtjb2xvcjoj"
    "YjZjMGQ2fQouaGlzdCBkaXZ7cGFkZGluZzo2cHggMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4wNyl9"
    "Ci5taW5pe2ZvbnQ6NTAwIDExcHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tbXV0ZSk7bWFyZ2luLXRvcDoxMHB4fQouYnRue2Rp"
    "c3BsYXk6aW5saW5lLWJsb2NrO21hcmdpbi10b3A6MTRweDtwYWRkaW5nOjEzcHggMjBweDtib3JkZXItcmFkaXVzOjExcHg7Zm9u"
    "dDo2MDAgMTMuNXB4IHZhcigtLW1vbm8pO2JhY2tncm91bmQ6dmFyKC0tZ29sZCk7Y29sb3I6IzA1MDcwZjtib3JkZXI6MDtjdXJz"
    "b3I6cG9pbnRlcjt0ZXh0LWRlY29yYXRpb246bm9uZX0KLmJ0bi5naG9zdHtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2NvbG9yOiNm"
    "ZmY7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4yNCl9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9"
    "IndyYXAiPgo8ZGl2IGNsYXNzPSJ0b3AiPjxkaXYgY2xhc3M9ImJyYW5kIj5zZWJiaTxiPi5wcm88L2I+IMK3IENSRURJVDwvZGl2"
    "PjxuYXY+PGEgaHJlZj0iL2NpbmVtYSI+Q2luZW1hPC9hPjxhIGhyZWY9Ii9jcmVhdGUiPlN0dWRpbzwvYT48YSBocmVmPSIvIj5I"
    "b21lPC9hPjwvbmF2PjwvZGl2Pgo8aDE+VG9wIHVwIG9uY2UuIFRhcCB0byB3YXRjaCBhbnl0aGluZy48L2gxPgo8cCBjbGFzcz0i"
    "bGVhZCI+T25lIHNtYWxsIGJhbGFuY2UgdW5sb2NrcyBsb2NrZWQgdmlkZW9zIGFueXdoZXJlIG9uIHRoZSBpbnRlcm5ldCwgYSBm"
    "ZXcgcGVuY2UgYXQgYSB0aW1lLiBObyBhY2NvdW50LCBubyBjYXJkIGRldGFpbHMgc3RvcmVkIHdpdGggdGhlIGNyZWF0b3IsIGFu"
    "ZCBldmVyeSBwYWlkIHZpZXcgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluLjwvcD4KCjxkaXYgY2xhc3M9ImJhbGFuY2UiPjxkaXYg"
    "Y2xhc3M9Im4iIGlkPSJiYWwiPuKAlDwvZGl2PjxkaXYgY2xhc3M9ImwiPlBFTkNFIE9GIENSRURJVDwvZGl2Pgo8ZGl2IGNsYXNz"
    "PSJtaW5pIiBpZD0id2hvIj48L2Rpdj48L2Rpdj4KCjxkaXYgY2xhc3M9Im9wdHMiPgogPGRpdiBjbGFzcz0ib3B0IiBkYXRhLXA9"
    "IjIwMCI+PGI+wqMyPC9iPjxzcGFuPjIwIHZpZXdzIGF0IDEwcDwvc3Bhbj48L2Rpdj4KIDxkaXYgY2xhc3M9Im9wdCBob3QiIGRh"
    "dGEtcD0iNTAwIj48Yj7CozU8L2I+PHNwYW4+NTAgdmlld3MgYXQgMTBwPC9zcGFuPjwvZGl2PgogPGRpdiBjbGFzcz0ib3B0IiBk"
    "YXRhLXA9IjEwMDAiPjxiPsKjMTA8L2I+PHNwYW4+MTAwIHZpZXdzIGF0IDEwcDwvc3Bhbj48L2Rpdj4KIDxkaXYgY2xhc3M9Im9w"
    "dCIgZGF0YS1wPSIyMDAwIj48Yj7CozIwPC9iPjxzcGFuPjIwMCB2aWV3cyBhdCAxMHA8L3NwYW4+PC9kaXY+CjwvZGl2Pgo8ZGl2"
    "IGNsYXNzPSJvdXQiIGlkPSJvdXQiPjwvZGl2PgoKPGRpdiBjbGFzcz0iY2FyZCI+PGgzPldoYXQgeW91J3JlIGJ1eWluZzwvaDM+"
    "PHA+Q3JlZGl0LCBub3QgYSBzdWJzY3JpcHRpb24uIEl0IHNpdHMgb24geW91ciBiYWxhbmNlIHVudGlsIHlvdSBzcGVuZCBpdCwg"
    "YW5kIGFueSBjcmVhdG9yJ3MgbG9ja2VkIHZpZGVvIGFjY2VwdHMgaXQuIFVuc3BlbnQgY3JlZGl0IGRvZXMgbm90IGV4cGlyZS48"
    "L3A+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxoMz5Zb3VyIHVubG9ja3M8L2gzPjxkaXYgY2xhc3M9Imhpc3QiIGlkPSJoaXN0"
    "Ij5Ob3RoaW5nIHlldC48L2Rpdj48L2Rpdj4KPGEgY2xhc3M9ImJ0biBnaG9zdCIgaHJlZj0iL2NpbmVtYSI+R28gYW5kIHdhdGNo"
    "IHNvbWV0aGluZyDihpI8L2E+CjwvZGl2Pgo8c2NyaXB0PgooZnVuY3Rpb24oKXsKInVzZSBzdHJpY3QiOwp2YXIgQVBJPSIvYy8i"
    "OwpmdW5jdGlvbiBpZCgpe3RyeXt2YXIgaz1sb2NhbFN0b3JhZ2UuZ2V0SXRlbSgic2ViYmkudmlld2VyIik7aWYoaylyZXR1cm4g"
    "a31jYXRjaChlKXt9CiB2YXIgcz0idiIsYz0iYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU2Nzg5Ijtmb3IodmFyIGk9"
    "MDtpPDE5O2krKylzKz1jW01hdGguZmxvb3IoTWF0aC5yYW5kb20oKSozNildOwogdHJ5e2xvY2FsU3RvcmFnZS5zZXRJdGVtKCJz"
    "ZWJiaS52aWV3ZXIiLHMpfWNhdGNoKGUpe31yZXR1cm4gc30KdmFyIHZpZXdlcj1pZCgpLG91dD1kb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgib3V0Iik7CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ3aG8iKS50ZXh0Q29udGVudD0iWW91ciBjcmVkaXQgbGl2ZXMg"
    "b24gdGhpcyBkZXZpY2UgwrcgIit2aWV3ZXIuc2xpY2UoMCw4KSsi4oCmIjsKZnVuY3Rpb24gcmVmcmVzaCgpe2ZldGNoKEFQSSsi"
    "aGVsbG8/dmlld2VyPSIrdmlld2VyLHtjYWNoZToibm8tc3RvcmUifSkudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9"
    "KS50aGVuKGZ1bmN0aW9uKGQpewogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImJhbCIpLnRleHRDb250ZW50PSh0eXBlb2YgZC5i"
    "YWxhbmNlX3BlbmNlPT09Im51bWJlciIpP2QuYmFsYW5jZV9wZW5jZToi4oCUIjsKIGlmKGQudGVzdF9tb2RlKXtvdXQuY2xhc3NM"
    "aXN0LmFkZCgib24iKTtvdXQuaW5uZXJIVE1MPSJDYXJkIHRvcC11cHMgYXJlIGJlaW5nIHN3aXRjaGVkIG9uLiBVbnRpbCB0aGVu"
    "LCB0YXAgYW55IGFtb3VudCBhbmQgdGhlIGNyZWRpdCBpcyBhZGRlZCBzbyB5b3UgY2FuIHRyeSBpdC4ifQp9KS5jYXRjaChmdW5j"
    "dGlvbigpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJiYWwiKS50ZXh0Q29udGVudD0i4oCUIn0pfQpyZWZyZXNoKCk7CkFycmF5"
    "LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwoZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgiLm9wdCIpLGZ1bmN0aW9uKG8pe28ub25j"
    "bGljaz1mdW5jdGlvbigpewogdmFyIHA9K28uZGF0YXNldC5wO291dC5jbGFzc0xpc3QuYWRkKCJvbiIpO291dC5pbm5lckhUTUw9"
    "IkFkZGluZyAiK3ArInDigKYiOwogZmV0Y2goQVBJKyJ0b3B1cCIse21ldGhvZDoiUE9TVCIsaGVhZGVyczp7IkNvbnRlbnQtVHlw"
    "ZSI6ImFwcGxpY2F0aW9uL2pzb24ifSxib2R5OkpTT04uc3RyaW5naWZ5KHt2aWV3ZXI6dmlld2VyLHBlbmNlOnB9KX0pCiAudGhl"
    "bihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpewogIGlmKGQuY2hlY2tvdXQpe291dC5pbm5l"
    "ckhUTUw9J09wZW5pbmcgY2hlY2tvdXTigKYgPGEgaHJlZj0iJytkLmNoZWNrb3V0KyciPmNvbnRpbnVlIHRvIHBheW1lbnQ8L2E+"
    "Jztsb2NhdGlvbi5ocmVmPWQuY2hlY2tvdXQ7cmV0dXJufQogIGlmKGQucGFpZCl7b3V0LmlubmVySFRNTD0iQWRkZWQgIitkLmFk"
    "ZGVkX3BlbmNlKyJwLiBTZWFsZWQgaW4gYmxvY2sgIitkLmJsb2NrX2luZGV4KyIuIFlvdXIgYmFsYW5jZSBpcyBub3cgIitkLmJh"
    "bGFuY2VfcGVuY2UrInAuIjtyZWZyZXNoKCk7cmV0dXJufQogIG91dC5pbm5lckhUTUw9ZC5tZXNzYWdlfHwiQ291bGQgbm90IGFk"
    "ZCBjcmVkaXQganVzdCBub3cuIjsKIH0pLmNhdGNoKGZ1bmN0aW9uKCl7b3V0LmlubmVySFRNTD0iQ291bGQgbm90IHJlYWNoIHNl"
    "YmJpLnByby4ifSl9fSk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
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
