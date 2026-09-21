"""
modules/agentroom.py  v1.0.0
The Agent Room - a 3D room at /room. Five AI agents sit in chairs, get their
passports from the core, stand, and walk to the gate. The gate's decisions come
from the live Agent Passport demo on production (/x/passport/demo).

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/agentroom/status after each deploy. 3D via three.js r128 from
cdnjs.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIiPgo8"
    "dGl0bGU+VGhlIEFnZW50IFJvb20g4oCUIHNlYmJpLnBybzwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBjb250ZW50"
    "PSJTdGVwIGluc2lkZS4gV2F0Y2ggQUkgYWdlbnRzIGdldCB0aGVpciBwYXNzcG9ydHMsIHN0YW5kIHVwLCBhbmQgd2FsayB0byB0"
    "aGUgZ2F0ZS4gTGl2ZSBvbiBwcm9kdWN0aW9uLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3Nz"
    "Mj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs1MDAmZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDUwMCZk"
    "aXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KaHRtbCxib2R5e21hcmdpbjowO2hlaWdodDoxMDAlO2JhY2tn"
    "cm91bmQ6IzAzMDUwYztvdmVyZmxvdzpoaWRkZW47Y29sb3I6I2ZmZjtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsdWktbW9u"
    "b3NwYWNlLG1vbm9zcGFjZX0KY2FudmFze2Rpc3BsYXk6YmxvY2s7dG91Y2gtYWN0aW9uOm5vbmV9CiNwb3J0YWx7cG9zaXRpb246"
    "Zml4ZWQ7aW5zZXQ6MDtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7ei1pbmRl"
    "eDoyMDtwb2ludGVyLWV2ZW50czpub25lO2JhY2tncm91bmQ6IzAzMDUwYzt0cmFuc2l0aW9uOm9wYWNpdHkgMS4ycyBlYXNlfQoj"
    "cG9ydGFsIC5yaW5ne3dpZHRoOjQwdm1pbjtoZWlnaHQ6NDB2bWluO2JvcmRlci1yYWRpdXM6NTAlO2JhY2tncm91bmQ6Y29uaWMt"
    "Z3JhZGllbnQoZnJvbSAwZGVnLCNjOWE4NGMsIzdmZTNiMCwjNGFhM2ZmLCNjOWE4NGMpOy13ZWJraXQtbWFzazpyYWRpYWwtZ3Jh"
    "ZGllbnQoY2lyY2xlLHRyYW5zcGFyZW50IDU4JSwjMDAwIDYwJSk7bWFzazpyYWRpYWwtZ3JhZGllbnQoY2lyY2xlLHRyYW5zcGFy"
    "ZW50IDU4JSwjMDAwIDYwJSk7YW5pbWF0aW9uOnNwaW4gMS4ycyBsaW5lYXIgaW5maW5pdGUsZ3JvdyAyLjRzIGN1YmljLWJlemll"
    "ciguNywwLC4zLDEpIGZvcndhcmRzO2ZpbHRlcjpkcm9wLXNoYWRvdygwIDAgMzBweCAjYzlhODRjKX0KQGtleWZyYW1lcyBzcGlu"
    "e3Rve3RyYW5zZm9ybTpyb3RhdGUoMzYwZGVnKX19CkBrZXlmcmFtZXMgZ3Jvd3swJXtzY2FsZTouMjtvcGFjaXR5OjB9MzAle3Nj"
    "YWxlOjE7b3BhY2l0eToxfTEwMCV7c2NhbGU6OTtvcGFjaXR5OjB9fQojaHVke3Bvc2l0aW9uOmZpeGVkO2xlZnQ6MDtyaWdodDow"
    "O3RvcDowO3BhZGRpbmc6Y2FsYygxNHB4ICsgZW52KHNhZmUtYXJlYS1pbnNldC10b3AsMHB4KSkgMTZweCAwO3otaW5kZXg6MTA7"
    "cG9pbnRlci1ldmVudHM6bm9uZX0KI2h1ZCAuYnJhbmR7Zm9udC1zaXplOjEyLjVweDtjb2xvcjpyZ2JhKDI1NSwyNTUsMjU1LC43"
    "KX0jaHVkIC5icmFuZCBie2NvbG9yOiNjOWE4NGM7Zm9udC13ZWlnaHQ6NTAwfQojaHVkIGgxe2ZvbnQtZmFtaWx5OidOZXdzcmVh"
    "ZGVyJyxHZW9yZ2lhLHNlcmlmO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6Y2xhbXAoMjRweCw1dncsMzhweCk7bWFyZ2luOjhw"
    "eCAwIDRweDt0ZXh0LXNoYWRvdzowIDJweCAyMHB4ICMwMDB9CiNodWQgcHtmb250LXNpemU6MTIuNXB4O2NvbG9yOnJnYmEoMjU1"
    "LDI1NSwyNTUsLjcpO21heC13aWR0aDo0NmNoO21hcmdpbjowfQojY2Fwe3Bvc2l0aW9uOmZpeGVkO2xlZnQ6NTAlO3RvcDo0NCU7"
    "dHJhbnNmb3JtOnRyYW5zbGF0ZSgtNTAlLC01MCUpO3otaW5kZXg6MTE7Zm9udC1zaXplOmNsYW1wKDE1cHgsMy42dncsMjJweCk7"
    "Zm9udC13ZWlnaHQ6NTAwO2xldHRlci1zcGFjaW5nOi4wNGVtO3RleHQtYWxpZ246Y2VudGVyO3BvaW50ZXItZXZlbnRzOm5vbmU7"
    "b3BhY2l0eTowO3RyYW5zaXRpb246b3BhY2l0eSAuNHM7dGV4dC1zaGFkb3c6MCAwIDE4cHggIzAwMCwwIDAgNHB4ICMwMDA7cGFk"
    "ZGluZzowIDE0cHh9CiNsb2d7cG9zaXRpb246Zml4ZWQ7bGVmdDoxMnB4O3JpZ2h0OjEycHg7Ym90dG9tOmNhbGMoODRweCArIGVu"
    "dihzYWZlLWFyZWEtaW5zZXQtYm90dG9tLDBweCkpO3otaW5kZXg6MTA7Zm9udC1zaXplOjExLjVweDttYXgtaGVpZ2h0OjMwdmg7"
    "b3ZlcmZsb3c6aGlkZGVuO2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlvbjpjb2x1bW4tcmV2ZXJzZTtnYXA6NHB4O3BvaW50ZXIt"
    "ZXZlbnRzOm5vbmV9CiNsb2cgZGl2e2JhY2tncm91bmQ6cmdiYSgxMCwxNSwzMCwuNzIpO2JvcmRlci1sZWZ0OjJweCBzb2xpZCAj"
    "YzlhODRjO3BhZGRpbmc6NXB4IDlweDtib3JkZXItcmFkaXVzOjNweH0KI2xvZyAub2t7Ym9yZGVyLWNvbG9yOiM3ZmUzYjB9I2xv"
    "ZyAubm97Ym9yZGVyLWNvbG9yOiNmZjhhODB9CiNiYXJ7cG9zaXRpb246Zml4ZWQ7bGVmdDowO3JpZ2h0OjA7Ym90dG9tOjA7ei1p"
    "bmRleDoxMjtkaXNwbGF5OmZsZXg7Z2FwOjEwcHg7anVzdGlmeS1jb250ZW50OmNlbnRlcjtwYWRkaW5nOjE0cHggMTJweCBjYWxj"
    "KDE0cHggKyBlbnYoc2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwcHgpKTtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCh0cmFuc3Bh"
    "cmVudCxyZ2JhKDMsNSwxMiwuOSkpfQojYmFyIGJ1dHRvbiwjYmFyIGF7YmFja2dyb3VuZDojYzlhODRjO2NvbG9yOiMwYTBmMWU7"
    "Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czo2cHg7cGFkZGluZzoxMnB4IDE2cHg7Zm9udDo1MDAgMTNweCAnSUJNIFBsZXggTW9ubycs"
    "bW9ub3NwYWNlO3RleHQtZGVjb3JhdGlvbjpub25lO2N1cnNvcjpwb2ludGVyfQojYmFyIGF7YmFja2dyb3VuZDp0cmFuc3BhcmVu"
    "dDtjb2xvcjojZmZmO2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMyl9CiNiYXIgYnV0dG9uW2Rpc2FibGVkXXtv"
    "cGFjaXR5Oi41NX0KPC9zdHlsZT48L2hlYWQ+PGJvZHk+CjxkaXYgaWQ9InBvcnRhbCI+PGRpdiBjbGFzcz0icmluZyI+PC9kaXY+"
    "PC9kaXY+CjxkaXYgaWQ9Imh1ZCI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgVEhFIEFHRU5UIFJPT008"
    "L2Rpdj4KPGgxPkV2ZXJ5IGFnZW50IG5lZWRzIGEgcGFzc3BvcnQuPC9oMT4KPHA+Rml2ZSBBSSBhZ2VudHMuIE9uZSBnYXRlLiBU"
    "YXAgcnVuIGFuZCB3YXRjaCB0aGUgcmVhbCBzeXN0ZW0gZGVjaWRlLCBsaXZlIG9uIHByb2R1Y3Rpb24sIHdobyBnZXRzIHRocm91"
    "Z2guPC9wPjwvZGl2Pgo8ZGl2IGlkPSJjYXAiPjwvZGl2PjxkaXYgaWQ9ImxvZyI+PC9kaXY+CjxkaXYgaWQ9ImJhciI+PGJ1dHRv"
    "biBpZD0icnVuIiBvbmNsaWNrPSJydW4oKSI+V2FrZSB0aGUgYWdlbnRzPC9idXR0b24+PGEgaHJlZj0iL3Bhc3Nwb3J0Ij5Ib3cg"
    "aXQgd29ya3M8L2E+PGEgaHJlZj0iL3Byb3ZlIj5Qcm9vZjwvYT48L2Rpdj4KPHNjcmlwdCBzcmM9Imh0dHBzOi8vY2RuanMuY2xv"
    "dWRmbGFyZS5jb20vYWpheC9saWJzL3RocmVlLmpzL3IxMjgvdGhyZWUubWluLmpzIj48L3NjcmlwdD4KPHNjcmlwdD4KKGZ1bmN0"
    "aW9uKCl7CnZhciBXPWlubmVyV2lkdGgsSD1pbm5lckhlaWdodCxHT0xEPTB4YzlhODRjLE9LPTB4N2ZlM2IwLE5PPTB4ZmY1YTUw"
    "LEJMVUU9MHg0YWEzZmY7CnZhciBSPW5ldyBUSFJFRS5XZWJHTFJlbmRlcmVyKHthbnRpYWxpYXM6dHJ1ZX0pO1Iuc2V0UGl4ZWxS"
    "YXRpbyhNYXRoLm1pbihkZXZpY2VQaXhlbFJhdGlvLDIpKTtSLnNldFNpemUoVyxIKTtkb2N1bWVudC5ib2R5LmFwcGVuZENoaWxk"
    "KFIuZG9tRWxlbWVudCk7CnZhciBTPW5ldyBUSFJFRS5TY2VuZSgpO1MuYmFja2dyb3VuZD1uZXcgVEhSRUUuQ29sb3IoMHgwMzA1"
    "MGMpO1MuZm9nPW5ldyBUSFJFRS5Gb2coMHgwMzA1MGMsMTAsMjYpOwp2YXIgQz1uZXcgVEhSRUUuUGVyc3BlY3RpdmVDYW1lcmEo"
    "NTUsVy9ILC4xLDEwMCk7ClMuYWRkKG5ldyBUSFJFRS5BbWJpZW50TGlnaHQoMHg2MDcwYTAsLjU1KSk7CnZhciBrZXk9bmV3IFRI"
    "UkVFLlBvaW50TGlnaHQoR09MRCwxLjYsMzApO2tleS5wb3NpdGlvbi5zZXQoMCw1LjUsMSk7Uy5hZGQoa2V5KTsKdmFyIHJpbT1u"
    "ZXcgVEhSRUUuUG9pbnRMaWdodChCTFVFLDEuMSwzMCk7cmltLnBvc2l0aW9uLnNldCgtNiwzLC00KTtTLmFkZChyaW0pOwpmdW5j"
    "dGlvbiBNKGMsZSxtKXtyZXR1cm4gbmV3IFRIUkVFLk1lc2hTdGFuZGFyZE1hdGVyaWFsKHtjb2xvcjpjLGVtaXNzaXZlOmV8fDAs"
    "bWV0YWxuZXNzOm09PW51bGw/LjY6bSxyb3VnaG5lc3M6LjM1fSl9CnZhciBmbG9vcj1uZXcgVEhSRUUuTWVzaChuZXcgVEhSRUUu"
    "UGxhbmVHZW9tZXRyeSg0MCw0MCksTSgweDA3MGIxOCwwLC4yKSk7Zmxvb3Iucm90YXRpb24ueD0tTWF0aC5QSS8yO1MuYWRkKGZs"
    "b29yKTsKdmFyIGdyaWQ9bmV3IFRIUkVFLkdyaWRIZWxwZXIoNDAsNDAsR09MRCwweDFhMjQ0MCk7Z3JpZC5tYXRlcmlhbC50cmFu"
    "c3BhcmVudD10cnVlO2dyaWQubWF0ZXJpYWwub3BhY2l0eT0uMzU7Uy5hZGQoZ3JpZCk7Ci8vIGdhdGUKdmFyIGdhdGU9bmV3IFRI"
    "UkVFLkdyb3VwKCk7Z2F0ZS5wb3NpdGlvbi5zZXQoMCwwLC02KTtTLmFkZChnYXRlKTsKdmFyIGdtPU0oMHgxMDE4MmUsR09MRCwu"
    "OCk7Z20uZW1pc3NpdmVJbnRlbnNpdHk9LjM1OwpbLTEuNCwxLjRdLmZvckVhY2goZnVuY3Rpb24oeCl7dmFyIHA9bmV3IFRIUkVF"
    "Lk1lc2gobmV3IFRIUkVFLkJveEdlb21ldHJ5KC4yNSwzLjIsLjI1KSxnbSk7cC5wb3NpdGlvbi5zZXQoeCwxLjYsMCk7Z2F0ZS5h"
    "ZGQocCl9KTsKdmFyIHRvcD1uZXcgVEhSRUUuTWVzaChuZXcgVEhSRUUuQm94R2VvbWV0cnkoMy4wNSwuMjUsLjI1KSxnbSk7dG9w"
    "LnBvc2l0aW9uLnk9My4yO2dhdGUuYWRkKHRvcCk7CnZhciBmaWVsZE1hdD1uZXcgVEhSRUUuTWVzaEJhc2ljTWF0ZXJpYWwoe2Nv"
    "bG9yOkJMVUUsdHJhbnNwYXJlbnQ6dHJ1ZSxvcGFjaXR5Oi4xOCxzaWRlOlRIUkVFLkRvdWJsZVNpZGV9KTsKdmFyIGZpZWxkPW5l"
    "dyBUSFJFRS5NZXNoKG5ldyBUSFJFRS5QbGFuZUdlb21ldHJ5KDIuNTUsMy4wNSksZmllbGRNYXQpO2ZpZWxkLnBvc2l0aW9uLnk9"
    "MS41NTtnYXRlLmFkZChmaWVsZCk7CnZhciBnYXRlTGlnaHQ9bmV3IFRIUkVFLlBvaW50TGlnaHQoQkxVRSwxLjIsOCk7Z2F0ZUxp"
    "Z2h0LnBvc2l0aW9uLnNldCgwLDIsLjYpO2dhdGUuYWRkKGdhdGVMaWdodCk7Ci8vIGNvcmUKdmFyIGNvcmU9bmV3IFRIUkVFLk1l"
    "c2gobmV3IFRIUkVFLk9jdGFoZWRyb25HZW9tZXRyeSguNDUpLG5ldyBUSFJFRS5NZXNoU3RhbmRhcmRNYXRlcmlhbCh7Y29sb3I6"
    "R09MRCxlbWlzc2l2ZTpHT0xELGVtaXNzaXZlSW50ZW5zaXR5Oi45LG1ldGFsbmVzczouOSxyb3VnaG5lc3M6LjJ9KSk7Y29yZS5w"
    "b3NpdGlvbi5zZXQoMCw0LjQsMCk7Uy5hZGQoY29yZSk7CnZhciBoYWxvPW5ldyBUSFJFRS5NZXNoKG5ldyBUSFJFRS5Ub3J1c0dl"
    "b21ldHJ5KC44LC4wMyw4LDQ4KSxuZXcgVEhSRUUuTWVzaEJhc2ljTWF0ZXJpYWwoe2NvbG9yOkdPTER9KSk7aGFsby5wb3NpdGlv"
    "bi5jb3B5KGNvcmUucG9zaXRpb24pO1MuYWRkKGhhbG8pOwovLyByb2JvdHMgYW5kIGNoYWlycwp2YXIgYm90cz1bXSxOPTUsYm9k"
    "eT1NKDB4ZDhkZGU2LDAsLjcpLGRhcms9TSgweDFiMjMzNiwwLC42KTsKZnVuY3Rpb24gbGltYih3LGgpe3ZhciBnPW5ldyBUSFJF"
    "RS5Hcm91cCgpO3ZhciBtPW5ldyBUSFJFRS5NZXNoKG5ldyBUSFJFRS5Cb3hHZW9tZXRyeSh3LGgsdyksYm9keSk7bS5wb3NpdGlv"
    "bi55PS1oLzI7Zy5hZGQobSk7cmV0dXJuIGd9CmZvcih2YXIgaT0wO2k8TjtpKyspewogdmFyIGE9KGktKE4tMSkvMikqLjQyLHg9"
    "TWF0aC5zaW4oYSkqNS4yLHo9My42LU1hdGguY29zKGEpKjEuNDsKIHZhciBjaGFpcj1uZXcgVEhSRUUuR3JvdXAoKTtjaGFpci5w"
    "b3NpdGlvbi5zZXQoeCwwLHopO2NoYWlyLnJvdGF0aW9uLnk9YTsKIHZhciBzZWF0PW5ldyBUSFJFRS5NZXNoKG5ldyBUSFJFRS5C"
    "b3hHZW9tZXRyeSguOSwuMSwuOSksZGFyayk7c2VhdC5wb3NpdGlvbi55PS41NTtjaGFpci5hZGQoc2VhdCk7CiB2YXIgYmFjaz1u"
    "ZXcgVEhSRUUuTWVzaChuZXcgVEhSRUUuQm94R2VvbWV0cnkoLjksMSwuMSksZGFyayk7YmFjay5wb3NpdGlvbi5zZXQoMCwxLjA1"
    "LC40Mik7Y2hhaXIuYWRkKGJhY2spOwogdmFyIGxlZz1uZXcgVEhSRUUuTWVzaChuZXcgVEhSRUUuQ3lsaW5kZXJHZW9tZXRyeSgu"
    "MDYsLjA2LC41NSksZGFyayk7bGVnLnBvc2l0aW9uLnk9LjI3O2NoYWlyLmFkZChsZWcpOwogUy5hZGQoY2hhaXIpOwogdmFyIGI9"
    "bmV3IFRIUkVFLkdyb3VwKCksaGlwcz1uZXcgVEhSRUUuR3JvdXAoKTtiLmFkZChoaXBzKTsKIHZhciB0b3Jzbz1uZXcgVEhSRUUu"
    "TWVzaChuZXcgVEhSRUUuQm94R2VvbWV0cnkoLjYyLC43MiwuMzYpLGJvZHkpO3RvcnNvLnBvc2l0aW9uLnk9LjQyO2hpcHMuYWRk"
    "KHRvcnNvKTsKIHZhciBjaGVzdD1uZXcgVEhSRUUuTWVzaChuZXcgVEhSRUUuQm94R2VvbWV0cnkoLjIsLjEyLC4wMiksbmV3IFRI"
    "UkVFLk1lc2hCYXNpY01hdGVyaWFsKHtjb2xvcjoweDIyM30pKTtjaGVzdC5wb3NpdGlvbi5zZXQoMCwuNTUsLS4xOSk7aGlwcy5h"
    "ZGQoY2hlc3QpOwogdmFyIGhlYWQ9bmV3IFRIUkVFLkdyb3VwKCk7aGVhZC5wb3NpdGlvbi55PTEuMDtoaXBzLmFkZChoZWFkKTsK"
    "IGhlYWQuYWRkKG5ldyBUSFJFRS5NZXNoKG5ldyBUSFJFRS5Cb3hHZW9tZXRyeSguNDIsLjM2LC4zOCksYm9keSkpOwogdmFyIHZp"
    "c29yTWF0PW5ldyBUSFJFRS5NZXNoQmFzaWNNYXRlcmlhbCh7Y29sb3I6MHgyMjMzNTV9KTt2YXIgdmlzb3I9bmV3IFRIUkVFLk1l"
    "c2gobmV3IFRIUkVFLkJveEdlb21ldHJ5KC4zNCwuMDksLjAyKSx2aXNvck1hdCk7dmlzb3IucG9zaXRpb24uc2V0KDAsLjAzLC0u"
    "Mik7aGVhZC5hZGQodmlzb3IpOwogdmFyIGFybUw9bGltYiguMTMsLjYyKSxhcm1SPWxpbWIoLjEzLC42Mik7YXJtTC5wb3NpdGlv"
    "bi5zZXQoLS40LC43NCwwKTthcm1SLnBvc2l0aW9uLnNldCguNCwuNzQsMCk7aGlwcy5hZGQoYXJtTCk7aGlwcy5hZGQoYXJtUik7"
    "CiB2YXIgdGhMPWxpbWIoLjE2LC40NiksdGhSPWxpbWIoLjE2LC40Niksc2hMPWxpbWIoLjE0LC40Niksc2hSPWxpbWIoLjE0LC40"
    "Nik7CiB0aEwucG9zaXRpb24uc2V0KC0uMTYsMCwwKTt0aFIucG9zaXRpb24uc2V0KC4xNiwwLDApO3NoTC5wb3NpdGlvbi55PS0u"
    "NDY7c2hSLnBvc2l0aW9uLnk9LS40Njt0aEwuYWRkKHNoTCk7dGhSLmFkZChzaFIpO2hpcHMuYWRkKHRoTCk7aGlwcy5hZGQodGhS"
    "KTsKIGIucG9zaXRpb24uc2V0KHgsMCx6KTtiLnJvdGF0aW9uLnk9YTtTLmFkZChiKTsKIHZhciBiZWFtPW5ldyBUSFJFRS5MaW5l"
    "KG5ldyBUSFJFRS5CdWZmZXJHZW9tZXRyeSgpLnNldEZyb21Qb2ludHMoW2NvcmUucG9zaXRpb24uY2xvbmUoKSxuZXcgVEhSRUUu"
    "VmVjdG9yMyh4LDEuNyx6KV0pLG5ldyBUSFJFRS5MaW5lQmFzaWNNYXRlcmlhbCh7Y29sb3I6R09MRCx0cmFuc3BhcmVudDp0cnVl"
    "LG9wYWNpdHk6MH0pKTtTLmFkZChiZWFtKTsKIHZhciByPXtnOmIsaGlwczpoaXBzLGhlYWQ6aGVhZCx2aXNvcjp2aXNvck1hdCxj"
    "aGVzdDpjaGVzdC5tYXRlcmlhbCxhcm1MOmFybUwsYXJtUjphcm1SLHRoTDp0aEwsdGhSOnRoUixzaEw6c2hMLHNoUjpzaFIsYmVh"
    "bTpiZWFtLGhvbWU6e3g6eCx6OnosYTphfSxzdGFuZDowLHdhbGs6MCx0Ok1hdGgucmFuZG9tKCkqNn07CiBwb3NlKHIpO2JvdHMu"
    "cHVzaChyKTsKfQpmdW5jdGlvbiBwb3NlKHIpe3ZhciBzPXIuc3RhbmQ7ci5oaXBzLnBvc2l0aW9uLnk9LjYyK3MqLjM0OwogdmFy"
    "IHN3PU1hdGguc2luKHIudCo3KSouNTUqci53YWxrOwogci50aEwucm90YXRpb24ueD0tTWF0aC5QSS8yKigxLXMpK3N3O3IudGhS"
    "LnJvdGF0aW9uLng9LU1hdGguUEkvMiooMS1zKS1zdzsKIHIuc2hMLnJvdGF0aW9uLng9TWF0aC5QSS8yKigxLXMpK01hdGgubWF4"
    "KDAsLXN3KSouODtyLnNoUi5yb3RhdGlvbi54PU1hdGguUEkvMiooMS1zKStNYXRoLm1heCgwLHN3KSouODsKIHIuYXJtTC5yb3Rh"
    "dGlvbi54PS0uMjUqKDEtcyktc3cqLjg7ci5hcm1SLnJvdGF0aW9uLng9LS4yNSooMS1zKStzdyouODsKIHIuaGVhZC5yb3RhdGlv"
    "bi54PSgxLXMpKi4xOH0KLy8gdHdlZW5zCnZhciB0dz1bXTtmdW5jdGlvbiBhbmltKGQsZil7cmV0dXJuIG5ldyBQcm9taXNlKGZ1"
    "bmN0aW9uKHJlcyl7dHcucHVzaCh7ZDpkKjEwMDAsczpwZXJmb3JtYW5jZS5ub3coKSxmOmYscmVzOnJlc30pfSl9CmZ1bmN0aW9u"
    "IGVhc2UocCl7cmV0dXJuIHA8LjU/MipwKnA6MS1NYXRoLnBvdygtMipwKzIsMikvMn0KZnVuY3Rpb24gd2FpdChzKXtyZXR1cm4g"
    "YW5pbShzLGZ1bmN0aW9uKCl7fSl9Ci8vIGNhbWVyYSwgcG9ydGFsIGVudHJ5IGFuZCBkcmFnCnZhciB5YXc9MCxkcmFnPW51bGws"
    "aW50cm89MCx0MD1wZXJmb3JtYW5jZS5ub3coKTsKYWRkRXZlbnRMaXN0ZW5lcigncG9pbnRlcmRvd24nLGZ1bmN0aW9uKGUpe2Ry"
    "YWc9ZS5jbGllbnRYfSk7YWRkRXZlbnRMaXN0ZW5lcigncG9pbnRlcnVwJyxmdW5jdGlvbigpe2RyYWc9bnVsbH0pOwphZGRFdmVu"
    "dExpc3RlbmVyKCdwb2ludGVybW92ZScsZnVuY3Rpb24oZSl7aWYoZHJhZyE9bnVsbCl7eWF3Kz0oZS5jbGllbnRYLWRyYWcpKi4w"
    "MDQ7eWF3PU1hdGgubWF4KC0uOCxNYXRoLm1pbiguOCx5YXcpKTtkcmFnPWUuY2xpZW50WH19KTsKYWRkRXZlbnRMaXN0ZW5lcign"
    "cmVzaXplJyxmdW5jdGlvbigpe1c9aW5uZXJXaWR0aDtIPWlubmVySGVpZ2h0O1Iuc2V0U2l6ZShXLEgpO0MuYXNwZWN0PVcvSDtD"
    "LnVwZGF0ZVByb2plY3Rpb25NYXRyaXgoKX0pOwpzZXRUaW1lb3V0KGZ1bmN0aW9uKCl7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "J3BvcnRhbCcpLnN0eWxlLm9wYWNpdHk9MH0sMTQwMCk7CmZ1bmN0aW9uIGxvb3Aobm93KXtyZXF1ZXN0QW5pbWF0aW9uRnJhbWUo"
    "bG9vcCk7CiBmb3IodmFyIGk9dHcubGVuZ3RoLTE7aT49MDtpLS0pe3ZhciBrPXR3W2ldLHA9TWF0aC5taW4oMSwobm93LWsucykv"
    "ay5kKTtrLmYoZWFzZShwKSk7aWYocD49MSl7dHcuc3BsaWNlKGksMSk7ay5yZXMoKX19CiBpbnRybz1NYXRoLm1pbigxLChub3ct"
    "dDApLzMyMDApO3ZhciBpZT0xLU1hdGgucG93KDEtaW50cm8sMyksZGlzdD05LjUrKDEtaWUpKjE2LHBvcnRyYWl0PUg+Vz8zOjA7"
    "CiBDLnBvc2l0aW9uLnNldChNYXRoLnNpbih5YXcpKihkaXN0K3BvcnRyYWl0KSwzLjMrKDEtaWUpKjIsTWF0aC5jb3MoeWF3KSoo"
    "ZGlzdCtwb3J0cmFpdCkpO0MubG9va0F0KDAsMS4zLC0xKTsKIGNvcmUucm90YXRpb24ueSs9LjAxO2NvcmUucm90YXRpb24ueCs9"
    "LjAwNDtoYWxvLnJvdGF0aW9uLng9TWF0aC5QSS8yK01hdGguc2luKG5vdy85MDApKi4yO2hhbG8ucm90YXRpb24ueSs9LjAxMjsK"
    "IGZpZWxkTWF0Lm9wYWNpdHk9LjE0K01hdGguc2luKG5vdy8zMDApKi4wNTsKIGJvdHMuZm9yRWFjaChmdW5jdGlvbihyKXtyLnQr"
    "PS4wMTYqKHIud2Fsaz8xOi4yNSk7cG9zZShyKX0pOwogUi5yZW5kZXIoUyxDKX0KcmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3Ap"
    "OwovLyB0aGUgc3RvcnkKdmFyIGNhcD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2FwJyksbG9nRWw9ZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoJ2xvZycpOwpmdW5jdGlvbiBzYXkodCxjKXtjYXAudGV4dENvbnRlbnQ9dDtjYXAuc3R5bGUuY29sb3I9Y3x8JyNm"
    "ZmYnO2NhcC5zdHlsZS5vcGFjaXR5PTF9CmZ1bmN0aW9uIGh1c2goKXtjYXAuc3R5bGUub3BhY2l0eT0wfQpmdW5jdGlvbiBsb2co"
    "dCxjbHMpe3ZhciBkPWRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2RpdicpO2QudGV4dENvbnRlbnQ9dDtpZihjbHMpZC5jbGFzc05h"
    "bWU9Y2xzO2xvZ0VsLmluc2VydEJlZm9yZShkLGxvZ0VsLmZpcnN0Q2hpbGQpO3doaWxlKGxvZ0VsLmNoaWxkcmVuLmxlbmd0aD42"
    "KWxvZ0VsLnJlbW92ZUNoaWxkKGxvZ0VsLmxhc3RDaGlsZCl9CmZ1bmN0aW9uIHNldEdhdGUoY29sKXtmaWVsZE1hdC5jb2xvci5z"
    "ZXRIZXgoY29sKTtnYXRlTGlnaHQuY29sb3Iuc2V0SGV4KGNvbCl9CmFzeW5jIGZ1bmN0aW9uIGNvbm5lY3Qocil7ci5iZWFtLm1h"
    "dGVyaWFsLm9wYWNpdHk9Ljk7ci52aXNvci5jb2xvci5zZXRIZXgoR09MRCk7ci5jaGVzdC5jb2xvci5zZXRIZXgoR09MRCk7CiBh"
    "d2FpdCBhbmltKC41LGZ1bmN0aW9uKHApe3IuYmVhbS5tYXRlcmlhbC5vcGFjaXR5PS45KigxLXApKy4yfSk7ci5iZWFtLm1hdGVy"
    "aWFsLm9wYWNpdHk9MDsKIGF3YWl0IGFuaW0oLjksZnVuY3Rpb24ocCl7ci5zdGFuZD1wfSl9CmFzeW5jIGZ1bmN0aW9uIHdhbGtU"
    "byhyLHgseixkKXt2YXIgc3g9ci5nLnBvc2l0aW9uLngsc3o9ci5nLnBvc2l0aW9uLnosYW5nPU1hdGguYXRhbjIoc3gteCxzei16"
    "KTtyLmcucm90YXRpb24ueT1hbmc7ci53YWxrPTE7CiBhd2FpdCBhbmltKGQsZnVuY3Rpb24ocCl7ci5nLnBvc2l0aW9uLng9c3gr"
    "KHgtc3gpKnA7ci5nLnBvc2l0aW9uLno9c3orKHotc3opKnB9KTtyLndhbGs9MH0KYXN5bmMgZnVuY3Rpb24gZ29Ib21lKHIpe2F3"
    "YWl0IHdhbGtUbyhyLHIuaG9tZS54LHIuaG9tZS56LDEuOCk7ci5nLnJvdGF0aW9uLnk9ci5ob21lLmE7YXdhaXQgYW5pbSguOCxm"
    "dW5jdGlvbihwKXtyLnN0YW5kPTEtcH0pOwogci52aXNvci5jb2xvci5zZXRIZXgoMHgyMjMzNTUpO3IuY2hlc3QuY29sb3Iuc2V0"
    "SGV4KDB4MjIyMjMzKX0KYXN5bmMgZnVuY3Rpb24gdGhyb3VnaChyKXtzZXRHYXRlKE9LKTtyLnZpc29yLmNvbG9yLnNldEhleChP"
    "Syk7YXdhaXQgd2Fsa1RvKHIsMCwtNy40LDEuNCk7CiBhd2FpdCBhbmltKC41LGZ1bmN0aW9uKHApe3IuZy5zY2FsZS5zZXRTY2Fs"
    "YXIoMS1wKi45KX0pO3IuZy52aXNpYmxlPWZhbHNlO3NldEdhdGUoQkxVRSl9CmFzeW5jIGZ1bmN0aW9uIHJlZnVzZWQocix3aHkp"
    "e3NldEdhdGUoTk8pO3Iudmlzb3IuY29sb3Iuc2V0SGV4KE5PKTtyLmNoZXN0LmNvbG9yLnNldEhleChOTyk7c2F5KCdSRUZVU0VE"
    "IOKAlCAnK3doeSwnI2ZmOGE4MCcpOwogYXdhaXQgYW5pbSguMzUsZnVuY3Rpb24ocCl7ci5nLnBvc2l0aW9uLno9LTUuMStNYXRo"
    "LnNpbihwKk1hdGguUEkpKi40fSk7YXdhaXQgd2FpdCgxKTtzZXRHYXRlKEJMVUUpO2h1c2goKTthd2FpdCBnb0hvbWUocil9CmZ1"
    "bmN0aW9uIHJlYXNvbih3KXt3PSh3JiZ3WzBdfHwnJykudG9Mb3dlckNhc2UoKTtpZih3LmluZGV4T2YoJ2FscmVhZHknKT49MCly"
    "ZXR1cm4gJ2FscmVhZHkgdXNlZCc7aWYody5pbmRleE9mKCdyZXZva2VkJyk+PTApcmV0dXJuICdhdXRob3JpdHkgcmV2b2tlZCc7"
    "CiBpZih3LmluZGV4T2YoJ2lzc3VlZCBmb3InKT49MClyZXR1cm4gJ3dyb25nIHNpdGUnO2lmKHcuaW5kZXhPZigncGFyYW1ldGVy"
    "cycpPj0wKXJldHVybiAnYW1vdW50IGNoYW5nZWQnO3JldHVybiAnbm90IGF1dGhvcmlzZWQnfQpmdW5jdGlvbiByZXNldCgpe2Jv"
    "dHMuZm9yRWFjaChmdW5jdGlvbihyKXtyLmcudmlzaWJsZT10cnVlO3IuZy5zY2FsZS5zZXRTY2FsYXIoMSk7ci5nLnBvc2l0aW9u"
    "LnNldChyLmhvbWUueCwwLHIuaG9tZS56KTtyLmcucm90YXRpb24ueT1yLmhvbWUuYTtyLnN0YW5kPTA7ci53YWxrPTA7ci52aXNv"
    "ci5jb2xvci5zZXRIZXgoMHgyMjMzNTUpO3IuY2hlc3QuY29sb3Iuc2V0SGV4KDB4MjIyMjMzKX0pfQp2YXIgYnVzeT1mYWxzZTsK"
    "d2luZG93LnJ1bj1hc3luYyBmdW5jdGlvbigpe2lmKGJ1c3kpcmV0dXJuO2J1c3k9dHJ1ZTt2YXIgYnRuPWRvY3VtZW50LmdldEVs"
    "ZW1lbnRCeUlkKCdydW4nKTtidG4uZGlzYWJsZWQ9dHJ1ZTtidG4udGV4dENvbnRlbnQ9J1J1bm5pbmcgb24gcHJvZHVjdGlvbuKA"
    "pic7cmVzZXQoKTtsb2dFbC5pbm5lckhUTUw9Jyc7CiB2YXIgZD1udWxsO3RyeXt2YXIgcmVzPWF3YWl0IGZldGNoKCcveC9wYXNz"
    "cG9ydC9kZW1vJyx7Y2FjaGU6J25vLXN0b3JlJ30pO2Q9YXdhaXQgcmVzLmpzb24oKX1jYXRjaChlKXt9CiBpZighZHx8IWQuc3Rv"
    "cnkpe3NheShkJiZkLnJldHJ5X2FmdGVyX3NlY29uZHM/J1NvbWVvbmUganVzdCByYW4gaXQuIEFnYWluIGluICcrZC5yZXRyeV9h"
    "ZnRlcl9zZWNvbmRzKydzJzonVGhlIHJvb20gaXMgcmVzdGluZy4gVHJ5IGFnYWluIHNob3J0bHkuJyk7YXdhaXQgd2FpdCgyLjUp"
    "O2h1c2goKTtidG4uZGlzYWJsZWQ9ZmFsc2U7YnRuLnRleHRDb250ZW50PSdXYWtlIHRoZSBhZ2VudHMnO2J1c3k9ZmFsc2U7cmV0"
    "dXJufQogdmFyIHN0PWQuc3RvcnksY2FzdD1bCiAge3I6Ym90c1syXSxpbnRybzonQSBodW1hbiBncmFudHMgYXV0aG9yaXR5LiBU"
    "aGUgY29yZSBpc3N1ZXMgYSBwYXNzcG9ydC4nLHN0ZXA6c3RbM10sbGFiZWw6J1BheXMgwqMyMCBhdCB0aGUgcmlnaHQgc2l0ZSd9"
    "LAogIHtyOmJvdHNbMV0saW50cm86J1NvbWVvbmUgcmVwbGF5cyB0aGUgc2FtZSBwYXNzcG9ydC4nLHN0ZXA6c3RbNF0sbGFiZWw6"
    "J1JlcGxheSd9LAogIHtyOmJvdHNbM10saW50cm86J1ZhbGlkIHBhc3Nwb3J0LiBUaGVuIHRoZSBodW1hbiBwdWxscyB0aGUgYXV0"
    "aG9yaXR5Licsc3RlcDpzdFs3XSxsYWJlbDonUmV2b2tlZCBhIHNlY29uZCBiZWZvcmUgYWN0aW5nJ30sCiAge3I6Ym90c1swXSxp"
    "bnRybzonQSBnZW51aW5lIHBhc3Nwb3J0LCBwcmVzZW50ZWQgYXQgdGhlIHdyb25nIHNpdGUuJyxzdGVwOnN0WzhdLGxhYmVsOidX"
    "cm9uZyBzaXRlJ30sCiAge3I6Ym90c1s0XSxpbnRybzonUmlnaHQgc2l0ZS4gwqMyMCBhdXRob3Jpc2VkLCDCozQ5IHByZXNlbnRl"
    "ZC4nLHN0ZXA6c3RbOV0sbGFiZWw6J0VkaXRlZCBhbW91bnQnfV07CiBsb2coJ0xJVkUgwrcgc2ViYmkucHJvIHByb2R1Y3Rpb24g"
    "wrcgZXZlcnkgc3RlcCBzZWFsZWQnKTsKIGZvcih2YXIgaT0wO2k8Y2FzdC5sZW5ndGg7aSsrKXt2YXIgYz1jYXN0W2ldO3NheShj"
    "LmludHJvKTthd2FpdCBjb25uZWN0KGMucik7bG9nKCdwYXNzcG9ydCBpc3N1ZWQgwrcgJytjLmxhYmVsKTsKICBhd2FpdCB3YWxr"
    "VG8oYy5yLDAsLTQuOCwyLjIpO2h1c2goKTsKICBpZihjLnN0ZXAmJmMuc3RlcC5yZWRlZW1lZCl7c2F5KCdCT1VORCDigJQgYXV0"
    "aG9yaXNlZCwgb25jZScsJyM3ZmUzYjAnKTtsb2coJ0JPVU5EIMK3ICcrYy5sYWJlbCsoYy5zdGVwLmJsb2NrPycgwrcgYmxvY2sg"
    "JytjLnN0ZXAuYmxvY2s6JycpLCdvaycpO2F3YWl0IHRocm91Z2goYy5yKX0KICBlbHNle3ZhciB3PXJlYXNvbihjLnN0ZXAmJmMu"
    "c3RlcC53aHkpO2xvZygnUkVGVVNFRCDCtyAnK3crJyDCtyBzZWFsZWQnLCdubycpO2F3YWl0IHJlZnVzZWQoYy5yLHcpfQogIGh1"
    "c2goKTthd2FpdCB3YWl0KC40KX0KIHNheShkLnJlc3VsdD09PSdBTEwgVEVOIEJFSEFWRUQnPydPbmUgcGF5bWVudC4gRm91ciBy"
    "ZWZ1c2Fscy4gQWxsIG9uIHRoZSBjaGFpbi4nOmQucmVzdWx0LCcjYzlhODRjJyk7bG9nKCdkb25lIMK3ICcrZC5yZXN1bHQsJ29r"
    "Jyk7CiBhd2FpdCB3YWl0KDMpO2h1c2goKTtidG4uZGlzYWJsZWQ9ZmFsc2U7YnRuLnRleHRDb250ZW50PSdSdW4gaXQgYWdhaW4n"
    "O2J1c3k9ZmFsc2V9Owp9KSgpOwo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/room": (_d(_HTML_B64), "text/html; charset=utf-8"),
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
    if getattr(cls, "_agentroom_patched", False):
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
    cls._agentroom_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "agentroom", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
