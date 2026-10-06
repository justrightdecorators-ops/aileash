# Codebase — part 2 of 51

Contains:
- `modules/__init__.py`
- `modules/agentroom.py`
- `modules/ainews.py`
- `modules/answers.py`
- `modules/archive.py`
- `modules/arm.py`
- `modules/armall.py`


## `modules/__init__.py`

2 lines, 37 bytes

```python
# makes this folder a python package

```


## `modules/agentroom.py`

269 lines, 21543 bytes

```python
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

```


## `modules/ainews.py`

373 lines, 15376 bytes

```python
"""
modules/ainews.py  v1.0.0  -  a live AI news ticker along the bottom of sebbi.pro

    Arm:   https://sebbi.pro/x/arm/status
    Feed:  https://sebbi.pro/x/ainews/feed

Every ten minutes the server reads the AI sections of major technology
publishers, keeps only stories that are about AI, and holds the newest few
dozen. Every page on the site then gets a slim ticker along the bottom:
headline and publisher, scrolling slowly, pausing when touched, each linking
to the publisher's own article. Headlines and links only - nothing is copied.

The page is rewritten as it is served, like the brand module; no page file
is edited. The homelink bubbles are lifted above the bar so nothing overlaps.
Visitors can close it; it stays closed for that visit. Operator screens,
full-screen experiences and legal pages are left alone.

Nothing shows until there is news to show, so a fresh deploy or a network
problem never puts an empty bar on the site.
"""

import html
import json
import os
import re
import sys
import threading
import time
import urllib.request
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "feed"), ("GET", "spec")}

FEEDS = [
    ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed"),
    ("VentureBeat", "https://venturebeat.com/category/ai/feed/"),
    ("The Guardian", "https://www.theguardian.com/technology/artificialintelligence/rss"),
    ("Ars Technica", "https://arstechnica.com/ai/feed/"),
    ("Wired", "https://www.wired.com/feed/tag/ai/latest/rss"),
    ("BBC News", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
]
REFRESH = 600
MAX_AGE = 3 * 86400
MAX_ITEMS = 24

AI_RE = re.compile(r"(\bAI\b|\bA\.I\.|artificial intelligence|\bAGI\b|OpenAI|Anthropic|ChatGPT|\bGPT|Claude|Gemini|"
                   r"DeepMind|Mistral|\bLlama\b|\bLLMs?\b|large language model|machine learning|chatbot|Copilot|"
                   r"deepfake|neural net|generative|\bagentic\b|AI agent|xAI|Grok|Perplexity|Hugging Face|"
                   r"Nvidia|data cent(?:er|re)s? for AI|EU AI Act|superintelligence)", re.I)

SKIP = ("/admin", "/console", "/peers", "/pack", "/lineage-desk", "/bind-desk", "/cinema", "/game", "/room",
        "/create", "/v/", "/terms", "/data-protection", "/risk-policy", "/human-oversight", "/dossier/data",
        "/mcp", "/x/", "/api/", "/c/", "/p/")

_items = []
_state = {"installed": False, "thread": False, "last_run": None, "last_error": None, "sources_ok": 0, "served": 0}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _text(el, *names):
    for n in names:
        x = el.find(n)
        if x is not None:
            if x.text and x.text.strip():
                return x.text.strip()
            if x.get("href"):
                return x.get("href").strip()
    return ""


def _when(s):
    if not s:
        return None
    try:
        return parsedate_to_datetime(s).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _parse(source, raw):
    out = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    atom = "{http://www.w3.org/2005/Atom}"
    entries = root.findall(".//item") or root.findall(".//%sentry" % atom)
    for e in entries[:60]:
        title = _text(e, "title", atom + "title")
        link = _text(e, "link", atom + "link")
        if not link:
            for l in e.findall(atom + "link"):
                if l.get("rel", "alternate") == "alternate" and l.get("href"):
                    link = l.get("href")
                    break
        when = _when(_text(e, "pubDate", atom + "published", atom + "updated",
                           "{http://purl.org/dc/elements/1.1/}date"))
        title = html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()
        if not title or not link.startswith("http"):
            continue
        if not AI_RE.search(title):
            continue
        out.append({"title": title[:180], "link": link[:500], "source": source, "ts": when or 0})
    return out


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sebbi.pro AI news ticker; +https://sebbi.pro)",
                                               "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read(2 * 1024 * 1024)


def refresh():
    got, ok = [], 0
    local = os.environ.get("AINEWS_FEED_DIR")  # test copies read feeds from files; the live site never sets this
    for i, (source, url) in enumerate(FEEDS):
        try:
            if local:
                path = os.path.join(local, "feed_%d.xml" % i)
                if not os.path.exists(path):
                    continue
                with open(path, "rb") as f:
                    raw = f.read()
            else:
                raw = _fetch(url)
            got.extend(_parse(source, raw))
            ok += 1
        except Exception as e:
            _state["last_error"] = "%s: %s" % (source, str(e)[:120])
    now = time.time()
    seen, fresh = set(), []
    for it in sorted(got, key=lambda x: x["ts"], reverse=True):
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key in seen or it["link"] in seen:
            continue
        if it["ts"] and now - it["ts"] > MAX_AGE:
            continue
        seen.add(key)
        seen.add(it["link"])
        fresh.append(it)
    # keep the mix varied: no more than five from any one publisher
    per, picked = {}, []
    for it in fresh:
        if per.get(it["source"], 0) >= 5:
            continue
        per[it["source"]] = per.get(it["source"], 0) + 1
        picked.append(it)
        if len(picked) >= MAX_ITEMS:
            break
    with _lock:
        if picked:
            _items[:] = picked
        _state["last_run"] = now
        _state["sources_ok"] = ok
    return len(picked)


def _loop():
    while True:
        try:
            refresh()
        except Exception as e:
            _state["last_error"] = str(e)[:160]
        time.sleep(REFRESH)


def _ago(ts):
    if not ts:
        return ""
    m = int((time.time() - ts) / 60)
    if m < 60:
        return "%dm" % max(1, m)
    if m < 1440:
        return "%dh" % (m // 60)
    return "%dd" % (m // 1440)


def _bar():
    with _lock:
        items = list(_items)
    if len(items) < 3:
        return b""
    li = "".join('<a href="%s" target="_blank" rel="noopener"><i>%s</i>%s<em>%s</em></a>' % (
        html.escape(it["link"], quote=True), html.escape(it["source"]), html.escape(it["title"]),
        _ago(it["ts"])) for it in items)
    secs = max(60, len(items) * 7)
    return (BAR.replace("__ITEMS__", li).replace("__SECS__", str(secs))).encode("utf-8")


BAR = r"""<!--sebbi-ainews--><div id="sbn" role="region" aria-label="Live AI news">
<style>
html.sbn-on body{padding-bottom:calc(32px + env(safe-area-inset-bottom,0px))}
html.sbn-on #sebbi-homelink,html.sbn-on #sebbi-bubble,html.sbn-on #sebbi-tools,html.sbn-on #sebbi-toolbubble,
html.sbn-on #sebbi-studio,html.sbn-on #sebbi-studiobubble,html.sbn-on #sebbi-plug,html.sbn-on #sebbi-plugbubble{margin-bottom:34px}
#sbn{position:fixed;left:0;right:0;bottom:0;z-index:2147482990;height:calc(32px + env(safe-area-inset-bottom,0px));padding-bottom:env(safe-area-inset-bottom,0px);
background:rgba(8,12,24,.94);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-top:1px solid rgba(201,168,76,.28);
display:none;align-items:center;font:400 12.5px/1 'IBM Plex Sans',system-ui,sans-serif;color:#efe6cc}
html.sbn-on #sbn{display:flex}
#sbn .lab{flex:none;display:flex;align-items:center;gap:7px;padding:0 12px 0 14px;height:100%;color:#c9a84c;font-weight:500;letter-spacing:.02em;
border-right:1px solid rgba(201,168,76,.22);background:linear-gradient(90deg,rgba(201,168,76,.10),transparent)}
#sbn .dot{width:6px;height:6px;border-radius:50%;background:#e8b04b;box-shadow:0 0 0 0 rgba(232,176,75,.6);animation:sbnp 2.4s infinite}
@keyframes sbnp{0%{box-shadow:0 0 0 0 rgba(232,176,75,.55)}70%{box-shadow:0 0 0 7px rgba(232,176,75,0)}100%{box-shadow:0 0 0 0 rgba(232,176,75,0)}}
#sbn .win{flex:1;overflow:hidden;height:100%;-webkit-mask:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);mask:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}
#sbn .run{display:flex;width:max-content;height:100%;align-items:center;animation:sbnr __SECS__s linear infinite}
#sbn .win:hover .run,#sbn .win:focus-within .run{animation-play-state:paused}
@keyframes sbnr{to{transform:translateX(-50%)}}
#sbn .run a{display:inline-flex;align-items:baseline;gap:8px;color:#efe6cc;text-decoration:none;padding:0 22px;white-space:nowrap;border-right:1px solid rgba(239,230,204,.10)}
#sbn .run a:hover,#sbn .run a:focus-visible{color:#fff;outline:none}
#sbn .run a:focus-visible{text-decoration:underline}
#sbn .run i{font-style:normal;color:#c9a84c;font-size:11.5px}
#sbn .run em{font-style:normal;color:rgba(239,230,204,.42);font-size:11px}
#sbn .x{flex:none;width:32px;height:100%;border:0;border-left:1px solid rgba(201,168,76,.18);background:transparent;color:rgba(239,230,204,.55);font-size:15px;cursor:pointer}
#sbn .x:hover{color:#fff}
@media(prefers-reduced-motion:reduce){#sbn .run{animation:none}#sbn .win{overflow-x:auto}}
@media(max-width:520px){#sbn .lab span{display:none}#sbn .lab{padding:0 10px}}
</style>
<div class="lab"><b class="dot" aria-hidden="true"></b><span>AI news</span></div>
<div class="win"><div class="run">__ITEMS____ITEMS__</div></div>
<button class="x" type="button" aria-label="Hide AI news">&times;</button>
<script>(function(){var d=document.documentElement,b=document.getElementById('sbn');var off=false;try{off=sessionStorage.getItem('sebbi.news.off')==='1'}catch(e){}
if(!off)d.classList.add('sbn-on');b.querySelector('.x').onclick=function(){d.classList.remove('sbn-on');try{sessionStorage.setItem('sebbi.news.off','1')}catch(e){}};
var r=b.querySelector('.run');var h=r.innerHTML;r.querySelectorAll('a').forEach(function(a,i){if(i>=r.children.length/2){a.setAttribute('tabindex','-1');a.setAttribute('aria-hidden','true')}});})();</script>
</div>"""


class _Out(object):
    def __init__(self, real):
        self.real, self.buf, self.mode = real, bytearray(), None

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
            self._go_pass()
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

    def finish(self, bar):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if not bar or self.mode != "html" or end < 0 or not raw.startswith(b"HTTP/1.") or b" 200 " not in raw[:20]:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        at = body.rfind(b"</body>")
        if at < 0 or b"<!--sebbi-ainews-->" in body:
            self.real.write(raw)
            return
        body = body[:at] + bar + body[at:]
        lines = [l for l in head.split(b"\r\n") if not l.lower().startswith(b"content-length:")]
        lines.append(b"Content-Length: " + str(len(body)).encode())
        self.real.write(b"\r\n".join(lines) + b"\r\n\r\n" + body)
        _state["served"] += 1
        try:
            self.real.flush()
        except Exception:
            pass


def _install():
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_ainews_patched", False):
        return True
    original = H.handle_one_request

    def handle_one_request(self):
        real = self.wfile
        out = _Out(real)
        self.wfile = out
        try:
            original(self)
        finally:
            self.wfile = real
            try:
                path = (getattr(self, "path", "") or "").split("?")[0]
                want = getattr(self, "command", "") == "GET" and not path.startswith(SKIP)
                out.finish(_bar() if want else b"")
            except Exception as e:
                _state["last_error"] = str(e)[:200]
                try:
                    if out.buf:
                        real.write(bytes(out.buf))
                except Exception:
                    pass

    H.handle_one_request = handle_one_request
    H._ainews_patched = True
    return True


def arm():
    with _lock:
        start = not _state["thread"]
        _state["thread"] = True
    _state["installed"] = _install()
    if start:
        threading.Thread(target=_loop, name="ainews", daemon=True).start()


def handle(method, action, data, api_key, ctx):
    try:
        arm()
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    with _lock:
        items = list(_items)
    if action == "feed":
        return {"stories": [dict(it, age=_ago(it["ts"]),
                                 published_utc=datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if it["ts"] else None)
                            for it in items],
                "count": len(items), "refreshes_every_seconds": REFRESH}, 200
    if action == "spec":
        return {"module": "ainews", "version": VERSION, "sources": [s for s, _u in FEEDS],
                "what": "A live AI-only news ticker along the bottom of every page. Headlines and links to the publisher.",
                "refreshes_every_seconds": REFRESH, "left_alone": list(SKIP)}, 200
    return {"module": "ainews", "version": VERSION, "armed": _state["installed"], "stories": len(items),
            "sources_reached": "%d of %d" % (_state["sources_ok"], len(FEEDS)),
            "last_refresh_utc": datetime.fromtimestamp(_state["last_run"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if _state["last_run"] else None,
            "pages_served_with_ticker": _state["served"], "last_error": _state["last_error"]}, 200

```


## `modules/answers.py`

386 lines, 30743 bytes

```python
"""
modules/answers.py  v1.0.0  -  plain answers to the questions people ask, and the AI guide

    Arm:      https://sebbi.pro/x/arm/status
    Answers:  https://sebbi.pro/answers
    Standard: https://sebbi.pro/standard/forever-proof
    AI guide: https://sebbi.pro/llms.txt

When someone asks Google, ChatGPT, Claude or a forum "how do I prove what my
AI decided?", the answer that gets quoted is the clearest page that answers
exactly that question. These pages do that: one question per page, the
answer in the first two sentences, then how it works and where to do it,
with schema.org FAQ markup search engines and AI tools read.

Also serves /llms.txt (the guide AI tools read - the file existed but no
route served it), the open Forever Proof standard, and a sitemap for these
pages at /sitemap-answers.xml.

Adds pages only. Reads nothing from the chain and writes nothing anywhere.
"""

import json
import os
import sys
import threading

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "")}
SITE = "https://sebbi.pro"
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

_state = {"pages": False, "served": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


# ---------------------------------------------------------------------------
# the answers. "a" is the direct answer (first thing read and quoted),
# "how" the steps, "do" the places to act, "more" extra paragraphs.
# ---------------------------------------------------------------------------

ANSWERS = [
    {"slug": "prove-an-ai-decision-to-a-regulator",
     "q": "How do I prove an AI decision to a regulator?",
     "a": "Seal each decision at the moment it is made into a tamper-evident record that the regulator can check themselves, without relying on your word or your vendor's database. sebbi.pro does this: every AI decision is scored, sealed into a hash chain, witnessed by independent chains and committed to Bitcoin every hour, and any single decision can be checked against Bitcoin in a browser at sebbi.pro/forever.",
     "how": ["Send the decision to sebbi.pro as it happens (one API call, or connect your AI assistant at sebbi.pro/mcp).",
             "It is scored ALLOW, CHALLENGE or BLOCK in under 30 ms and sealed into the chain with a numbered receipt.",
             "Every hour the whole chain is folded into one Merkle root and written into Bitcoin.",
             "When asked, hand the regulator the block number or the Forever Proof file. They check it themselves at sebbi.pro/forever, or offline with one Python file."],
     "more": ["A report produced by the company being audited is a claim. A record the regulator can check against a public blockchain nobody controls is evidence. For a single decision you can also give the full machine-proof report: the decision, who sent it, where it came from, and every integrity and time proof (sebbi.pro/dossier)."],
     "do": [("Check a decision against Bitcoin", "/forever"), ("Connect your AI", "/connect"), ("Machine-proof report", "/dossier")]},

    {"slug": "tamper-proof-ai-audit-logs",
     "q": "How do I make AI audit logs tamper-proof?",
     "a": "Chain every log entry to the one before it with a cryptographic hash, have independent parties hold copies, number entries so gaps show, and anchor the chain to Bitcoin so even the operator cannot rewrite history. sebbi.pro provides all of these layers for every AI decision it seals.",
     "how": ["Hash chain: each record includes the hash of the previous one. Change any record and every record after it breaks.",
             "Unpredictable time: each seal carries public drand randomness, which nobody can know in advance, so records cannot be backdated.",
             "Witnesses: independent peer chains on the witness network hold and vouch for copies of the chain.",
             "Receipts: each customer's decisions are numbered in order with no gaps, so a missing record proves itself missing.",
             "Bitcoin: every hour the chain's Merkle root is committed to Bitcoin through OpenTimestamps."],
     "more": ["A log in an ordinary database is only as trustworthy as whoever has write access to it. These layers mean a record cannot be faked before it happened, changed afterwards, quietly deleted, or lost if the operator disappears. The chain can be re-verified by anyone at sebbi.pro/api/verify-chain."],
     "do": [("Verify the live chain", "/api/verify-chain"), ("Forever Proof", "/forever"), ("Developers", "/developers")]},

    {"slug": "eu-ai-act-record-keeping",
     "q": "What records does the EU AI Act require for high-risk AI?",
     "a": "The EU AI Act requires high-risk AI systems to automatically record events (logs) over their lifetime (Article 12), requires providers to keep those logs for at least six months (Article 19), and requires deployers to keep the logs under their control for at least six months (Article 26). sebbi.pro records every decision automatically, seals it so it cannot be altered, and keeps it provable long after six months through Bitcoin anchoring.",
     "how": ["Article 12: logs must allow events relevant to risk, post-market monitoring and operational monitoring to be recorded automatically.",
             "Article 19 and Article 26(6): automatically generated logs kept for at least six months, longer where other law requires.",
             "Article 14: human oversight, so a person can understand, override or stop the system. sebbi.pro's CHALLENGE verdict routes a decision to a human.",
             "Article 86: people affected by certain high-risk decisions can ask for an explanation, which needs a record of what was decided and why."],
     "more": ["Application dates and details can change through EU implementing acts and amendments, so check the current text for your system. This page is a plain summary, not legal advice. The free EU AI Act scanner at sebbi.pro/scan gives a quick first view of where you stand."],
     "do": [("Free EU AI Act scanner", "/scan"), ("Start sealing decisions", "/connect"), ("Whitepaper", "/whitepaper")]},

    {"slug": "timestamp-a-file-in-bitcoin",
     "q": "How do I timestamp a file in Bitcoin?",
     "a": "Fingerprint the file with SHA-256 and commit that fingerprint to Bitcoin through the OpenTimestamps calendars. The easiest way is the free Bitcoin Notary at sebbi.pro/bitcoin: drop the file in, it is fingerprinted on your own device, and you get a receipt that confirms in a Bitcoin block, normally within a few hours.",
     "how": ["Open sebbi.pro/bitcoin and drop in one or more files, or paste text or a fingerprint.",
             "Your browser computes the SHA-256. The file itself never leaves your device.",
             "Every few minutes all fingerprints are folded into one Merkle tree, and its root is sent to Bitcoin.",
             "Your receipt page shows when it lands in a Bitcoin block, and gives you a Forever Proof anyone can check."],
     "more": ["Companies and tools can do the same by API: POST the fingerprints to sebbi.pro/x/notary/stamp. Without a key there is a daily limit of 500 per visitor; with an API key it is 100,000 a day. AI assistants connected at sebbi.pro/mcp can call sebbi_notarize directly."],
     "do": [("Bitcoin Notary", "/bitcoin"), ("Notary spec", "/x/notary/spec"), ("Discovery document", "/.well-known/sebbi-notary.json")]},

    {"slug": "what-is-a-forever-proof",
     "q": "What is a Forever Proof?",
     "a": "A Forever Proof is a small file that proves a fingerprint existed before a specific Bitcoin block was mined. It holds the fingerprint, its Merkle path to a batch root, and the OpenTimestamps proof linking that root to Bitcoin, so anyone can check it against the Bitcoin blockchain without sebbi.pro.",
     "how": ["The fingerprint (a sebbi.pro decision, a notarised file or a Human Keys proof) is a leaf in a Merkle tree.",
             "The path of sibling hashes folds the leaf up to the tree's root.",
             "The OpenTimestamps proof replays the operations from that root to a Bitcoin block's Merkle root.",
             "A verifier compares the result with the real block, fetched from independent explorers or your own node."],
     "more": ["The format is open (sebbi-forever-proof/1) and free to implement. Because the proof is a file the holder keeps, it still works if sebbi.pro is offline, in a dispute with them, or gone."],
     "do": [("Check a proof", "/forever"), ("The open standard", "/standard/forever-proof"), ("Download the verifier", "/forever-verify.py")]},

    {"slug": "verify-without-trusting-the-vendor",
     "q": "How do I check a proof without trusting the company that made it?",
     "a": "Check it against a public record the company does not control. Every sebbi.pro proof can be checked against Bitcoin in your own browser at sebbi.pro/forever, or offline with forever-verify.py, a single Python file that needs nothing installed and can use your own Bitcoin node.",
     "how": ["Get the Forever Proof file (from the receipt page, the company you are checking, or sebbi.pro/forever).",
             "Run python3 forever-verify.py proof.json, or drop it on sebbi.pro/forever where the checking runs in your browser.",
             "The verifier replays every step and fetches the Bitcoin block from two independent explorers, or from your node with --node.",
             "VERIFIED means the record existed before that block. Nothing from sebbi.pro was trusted to reach that answer."],
     "more": ["Add --file to check that the original file is the one that was proven, --text for a Human Keys text, or --block for the decision itself if you are its owner."],
     "do": [("Verify in your browser", "/forever"), ("Download forever-verify.py", "/forever-verify.py")]},

    {"slug": "prove-a-human-wrote-it",
     "q": "How do I prove a human wrote something, not an AI?",
     "a": "Type it on Human Keys at sebbi.pro/keys. The page measures how you type — the rhythm, corrections and pauses — never what you type, seals the result with a fingerprint of the text, and gives you a code anyone can check. The proof is signed by a key on your own phone and dated by Bitcoin, so the original can always show it came first.",
     "how": ["Type on sebbi.pro/keys. The text stays on your device; only its fingerprint is sent.",
             "The typing rhythm is scored on the server against a challenge that cannot be prepared in advance.",
             "You get a code like HK-7Q2M-X9KD and a check page others can open and paste the text into.",
             "The proof joins the next Bitcoin batch, and you can prove ownership with your phone's key."],
     "more": ["50p a month for unlimited proofs. Checking a proof is always free."],
     "do": [("Human Keys", "/keys"), ("Check a proof", "/k/")]},

    {"slug": "prove-nothing-was-deleted",
     "q": "How do I prove a record was not deleted?",
     "a": "Number every record in order with no gaps, and publish consistency proofs that show today's log contains yesterday's. On sebbi.pro every customer's decisions get sequence numbers with no gaps, so holding receipts 41 and 43 proves 42 is missing, and the RFC 6962 consistency root lets anyone prove the log they saw earlier is still part of the log served now.",
     "how": ["Each sealed decision gets a block number and a per-customer sequence number, issued together.",
             "Sequence numbers have no gaps by construction.",
             "The consistency root at sebbi.pro/x/consistency/root covers every record in order, and the same root is committed to Bitcoin hourly.",
             "Independent witness chains hold copies, so removing a record means fooling all of them."],
     "do": [("Consistency root", "/x/consistency/root"), ("Forever Proof", "/forever")]},

    {"slug": "audit-trail-for-ai-agents",
     "q": "How do I give an AI agent an audit trail?",
     "a": "Have the agent send each action to sebbi.pro before it acts, and keep the sealed receipt. Agents can do it themselves through the MCP connector at sebbi.pro/mcp, and an Agent Passport gives one signed, single-use permission for a single action that can be checked offline.",
     "how": ["Connect the agent's assistant at sebbi.pro/mcp, or call the API from the agent's code.",
             "Each action is scored ALLOW, CHALLENGE or BLOCK before it runs, and sealed.",
             "High-risk actions can require an Agent Passport: a signed permission for that one action.",
             "Every action then has a receipt that outlives the agent, the model and the vendor, provable against Bitcoin."],
     "do": [("Connect your AI", "/connect"), ("Agent Passport", "/passport"), ("Build your own rules", "/build")]},

    {"slug": "govern-every-openai-call",
     "q": "How do I govern every OpenAI or Anthropic call without changing my code?",
     "a": "Change one line: point your app's OpenAI or Anthropic base URL at the sebbi.pro gateway. Every call is then scored before it leaves, stopped if it should be, sealed into a tamper-evident chain, and answered with an AI-Decision-Receipt header anyone can check against Bitcoin.",
     "how": ["Get your private gateway URL at sebbi.pro/gateway (or ask your AI assistant connected at sebbi.pro/mcp to set it up).",
             "Set it as base_url in the OpenAI or Anthropic SDK. Your provider key stays in your app and passes straight through.",
             "Each request is fingerprinted, scored ALLOW, CHALLENGE or BLOCK, and sealed. BLOCK never reaches the provider.",
             "Answers stream back token by token with an AI-Decision-Receipt header; request and response fingerprints are timestamped in Bitcoin."],
     "more": ["Prompts, answers and provider keys are never stored, only their fingerprints. The receipt header is an open standard any system can emit."],
     "do": [("Set up the gateway", "/gateway"), ("The receipt standard", "/standard/ai-decision-receipt")]},

    {"slug": "prove-code-existed-on-a-date",
     "q": "How do I prove my code existed on a date?",
     "a": "Fingerprint every file and timestamp the fingerprints in Bitcoin, then re-seal whenever a file changes. Drop your files on the Bitcoin Notary at sebbi.pro/bitcoin, or send the output of sha256sum to the notary API. sebbi.pro does this for its own code: every file is timestamped in Bitcoin at sebbi.pro/bitcoin/code.",
     "how": ["Fingerprint each file (your browser does it on sebbi.pro/bitcoin, or run sha256sum).",
             "Send the fingerprints to the notary. Only fingerprints are sent, so private code stays private.",
             "Keep the receipts. Each one confirms in a Bitcoin block within hours.",
             "Later, anyone with a copy of a file can drop it on 'Check a file' to see the date it was first sealed."],
     "do": [("Bitcoin Notary", "/bitcoin"), ("Our code in Bitcoin", "/bitcoin/code")]},
]
BY_SLUG = {a["slug"]: a for a in ANSWERS}


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


_CSS = """<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,500;1,6..72,500&family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--gold2:#f0d78a;--btc:#f7931a;--mut:rgba(255,255,255,.66);--line:rgba(201,168,76,.22)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:#fff;font-family:'IBM Plex Sans',system-ui,sans-serif;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header{border-bottom:1px solid var(--line);padding:14px 0}header .wrap{display:flex;justify-content:space-between;align-items:baseline}
.brand{font-family:'IBM Plex Mono',monospace;font-size:13px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
header nav a{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--mut);text-decoration:none;margin-left:14px}
.crumb{font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--gold);letter-spacing:.06em;margin:38px 0 12px}.crumb a{color:var(--gold);text-decoration:none}
h1{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:clamp(32px,6.4vw,50px);line-height:1.08;margin-bottom:18px}
.answer{font-size:18.5px;color:#fff;border-left:3px solid var(--btc);padding:4px 0 4px 16px;margin-bottom:26px}
h2{font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:25px;margin:28px 0 10px}
ol{padding-left:22px}ol li{margin:8px 0;color:var(--mut);font-size:16px}ol li::marker{color:var(--gold);font-family:'IBM Plex Mono',monospace}
p.more{color:var(--mut);font-size:16px;margin:10px 0}
.do{display:flex;flex-wrap:wrap;gap:10px;margin:22px 0}
.do a{background:var(--gold);color:var(--ink);border-radius:8px;padding:12px 16px;font-family:'IBM Plex Mono',monospace;font-size:13.5px;text-decoration:none}
.do a+a{background:transparent;color:var(--gold);border:1px solid var(--gold)}
.rel{border-top:1px solid var(--line);margin-top:34px;padding-top:8px}.rel a{display:block;color:var(--gold2);text-decoration:none;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:15.5px}
.list a{display:block;background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin:10px 0;color:#fff;text-decoration:none}
.list a b{display:block;font-family:'Newsreader',Georgia,serif;font-weight:500;font-size:21px;line-height:1.25;margin-bottom:4px}.list a span{color:var(--mut);font-size:14px}
pre{background:#060a15;border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:14px;font-family:'IBM Plex Mono',monospace;font-size:12.5px;overflow-x:auto;color:#e6e6e6;margin:10px 0}
code{font-family:'IBM Plex Mono',monospace;font-size:13.5px;color:var(--gold2)}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:14px}td,th{text-align:left;vertical-align:top;padding:9px 6px;border-bottom:1px solid rgba(255,255,255,.07)}th{color:var(--mut);font-weight:500}td:first-child{font-family:'IBM Plex Mono',monospace;color:var(--gold2);white-space:nowrap}
footer{border-top:1px solid var(--line);margin-top:40px;padding:22px 0 30px;font-size:12.5px;color:var(--mut)}footer a{color:var(--gold);text-decoration:none;margin-right:14px}
</style>"""

_HEADER = """<header><div class="wrap"><a class="brand" href="/">sebbi<b>.pro</b></a><nav><a href="/answers">Answers</a><a href="/forever">Forever Proof</a><a href="/bitcoin">Notary</a></nav></div></header>"""
_FOOTER = """<footer><div class="wrap"><a href="/answers">Answers</a><a href="/standard/forever-proof">Forever Proof standard</a><a href="/llms.txt">llms.txt</a><a href="/terms">Terms</a><p style="margin-top:12px">&copy; 2026 Monop Content &middot; sebbi.pro</p></div></footer>"""


def _head(title, desc, path, ld):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>%s</title><meta name="description" content="%s">'
            '<link rel="canonical" href="%s%s">'
            '<meta property="og:title" content="%s"><meta property="og:description" content="%s">'
            '<meta property="og:type" content="article"><meta property="og:url" content="%s%s">'
            '<script type="application/ld+json">%s</script>%s</head><body>'
            % (_esc(title), _esc(desc), SITE, path, _esc(title), _esc(desc), SITE, path,
               json.dumps(ld).replace("</", "<\\/"), _CSS))


def _short(text, n=155):
    t = text.split(". ")[0]
    return (t if len(t) <= n else t[:n - 1].rsplit(" ", 1)[0] + "…").rstrip(".") + "."


def answer_page(a):
    path = "/answers/" + a["slug"]
    full = a["a"] + " " + " ".join(a.get("more", []))
    ld = [{"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": a["q"],
                           "acceptedAnswer": {"@type": "Answer", "text": full}}]},
          {"@context": "https://schema.org", "@type": "BreadcrumbList",
           "itemListElement": [{"@type": "ListItem", "position": 1, "name": "Answers", "item": SITE + "/answers"},
                               {"@type": "ListItem", "position": 2, "name": a["q"], "item": SITE + path}]}]
    if a.get("how"):
        ld.append({"@context": "https://schema.org", "@type": "HowTo", "name": a["q"],
                   "step": [{"@type": "HowToStep", "position": i + 1, "text": s} for i, s in enumerate(a["how"])]})
    h = [_head(a["q"] + " — sebbi.pro", _short(a["a"]), path, ld), _HEADER, '<main class="wrap">',
         '<div class="crumb"><a href="/answers">ANSWERS</a></div>',
         "<h1>%s</h1>" % _esc(a["q"]), '<p class="answer">%s</p>' % _esc(a["a"])]
    if a.get("how"):
        h.append("<h2>How it works</h2><ol>%s</ol>" % "".join("<li>%s</li>" % _esc(s) for s in a["how"]))
    for m in a.get("more", []):
        h.append('<p class="more">%s</p>' % _esc(m))
    if a.get("do"):
        h.append('<div class="do">%s</div>' % "".join('<a href="%s">%s</a>' % (_esc(u), _esc(t)) for t, u in a["do"]))
    rel = [b for b in ANSWERS if b["slug"] != a["slug"]][:5]
    h.append('<div class="rel"><h2>Related questions</h2>%s</div>' %
             "".join('<a href="/answers/%s">%s</a>' % (b["slug"], _esc(b["q"])) for b in rel))
    h.append("</main>" + _FOOTER + "</body></html>")
    return "".join(h)


def index_page():
    ld = {"@context": "https://schema.org", "@type": "FAQPage",
          "mainEntity": [{"@type": "Question", "name": a["q"],
                          "acceptedAnswer": {"@type": "Answer", "text": a["a"]}} for a in ANSWERS]}
    h = [_head("Answers: proving AI decisions, Bitcoin timestamps and human authorship — sebbi.pro",
               "Plain answers to how to prove an AI decision, keep tamper-proof AI audit logs, meet EU AI Act record-keeping, timestamp files in Bitcoin and prove a human wrote something.",
               "/answers", ld), _HEADER, '<main class="wrap">', '<div class="crumb">ANSWERS</div>',
         "<h1>Straight answers about proving what AI did</h1>",
         '<p class="answer">How to prove an AI decision, keep logs nobody can alter, meet the EU AI Act, timestamp anything in Bitcoin, and prove a human wrote it. Each answer says exactly how, and where to do it.</p>',
         '<div class="list">']
    for a in ANSWERS:
        h.append('<a href="/answers/%s"><b>%s</b><span>%s</span></a>' % (a["slug"], _esc(a["q"]), _esc(_short(a["a"], 140))))
    h.append('<a href="/standard/forever-proof"><b>The Forever Proof standard</b><span>The open proof format anyone can implement.</span></a>')
    h.append("</div></main>" + _FOOTER + "</body></html>")
    return "".join(h)


EXAMPLE_BUNDLE = """{
  "format": "sebbi-forever-proof/1",
  "subject": { "kind": "hash", "code": "NT-7Q2M-X9KD", "digest": "<sha256 of the file>" },
  "leaf": "sebbi-notary/1|<sha256 of the file>",
  "merkle": {
    "algorithm": "RFC 6962 SHA-256 (leaf 0x00, node 0x01)",
    "index": 41, "tree_size": 300,
    "path": ["<hex>", "<hex>", "..."],
    "root": "<hex>"
  },
  "bitcoin": { "state": "confirmed", "heights": [917204], "proof_ots_base64": "<OpenTimestamps proof of the root>" }
}"""


def standard_page():
    ld = {"@context": "https://schema.org", "@type": "TechArticle",
          "headline": "Forever Proof (sebbi-forever-proof/1) - an open format for proving a fingerprint existed before a Bitcoin block",
          "author": {"@type": "Organization", "name": "Monop Content"}, "url": SITE + "/standard/forever-proof",
          "isAccessibleForFree": True}
    rows = [("format", "Always <code>sebbi-forever-proof/1</code>."),
            ("subject", "What is being proven. <code>kind</code> is <code>hash</code> (a notarised fingerprint), <code>humankeys</code> (a Human Keys proof) or <code>chain_block</code> (a block on a sebbi.pro chain), with the fields for that kind."),
            ("leaf", "The exact UTF-8 string placed in the tree. <code>hash</code>: <code>sebbi-notary/1|&lt;digest&gt;</code>. <code>humankeys</code>: <code>sebbi-humankeys/1|&lt;code&gt;|&lt;text_hash&gt;|&lt;verdict&gt;|&lt;sealed_at&gt;</code>. <code>chain_block</code>: the block's audit hash."),
            ("merkle", "<code>index</code>, <code>tree_size</code>, <code>path</code> (sibling hashes, leaf upwards, hex) and <code>root</code>. RFC 6962: leaf hash = SHA-256(0x00 &#8214; leaf), node = SHA-256(0x01 &#8214; left &#8214; right). Verified with the RFC 9162 §2.1.3.2 algorithm."),
            ("bitcoin", "<code>proof_ots_base64</code>: a standard OpenTimestamps detached proof whose file digest is the Merkle root. <code>state</code> is <code>pending</code> until a Bitcoin attestation is present.")]
    steps = ["Recompute the leaf from what you hold (the file's SHA-256, the Human Keys text fingerprint, or the chain block) and compare with <code>leaf</code>.",
             "Hash the leaf and fold it up <code>path</code> to the root. It must equal <code>merkle.root</code>.",
             "Decode the OpenTimestamps proof. Its file digest must equal the root.",
             "Replay every operation in the proof. For each Bitcoin attestation, the resulting message, byte-reversed, must equal that block's Merkle root as reported by independent sources or your own node.",
             "The subject existed before that block's time."]
    h = [_head("Forever Proof standard (sebbi-forever-proof/1) — sebbi.pro",
               "An open, free-to-implement format for proving a fingerprint existed before a Bitcoin block: leaf, RFC 6962 Merkle path and an OpenTimestamps proof.",
               "/standard/forever-proof", ld), _HEADER, '<main class="wrap">',
         '<div class="crumb">OPEN STANDARD · VERSION 1</div>',
         "<h1>Forever Proof</h1>",
         '<p class="answer">A small JSON document that proves a fingerprint existed before a specific Bitcoin block was mined, checkable by anyone with no help from whoever issued it. The format is open: anyone may produce or verify Forever Proofs, with no permission or fee.</p>',
         "<h2>The document</h2><pre>%s</pre>" % _esc(EXAMPLE_BUNDLE),
         "<h2>Fields</h2><table><tbody>%s</tbody></table>" % "".join("<tr><td>%s</td><td>%s</td></tr>" % r for r in rows),
         "<h2>Verifying</h2><ol>%s</ol>" % "".join("<li>%s</li>" % s for s in steps),
         '<p class="more">Built on two existing open standards: RFC 6962 Merkle trees (as used by Certificate Transparency) and OpenTimestamps. Nothing proprietary sits between the subject and Bitcoin.</p>',
         "<h2>Reference implementations</h2>",
         '<p class="more">Python, standard library only: <a href="/forever-verify.py" style="color:var(--gold2)">forever-verify.py</a>. In-browser JavaScript: the verifier on <a href="/forever" style="color:var(--gold2)">sebbi.pro/forever</a> (view source). Proofs are issued by <a href="/x/notary/spec" style="color:var(--gold2)">the sebbi.pro notary</a>.</p>',
         '<div class="do"><a href="/forever-verify.py">Download the verifier</a><a href="/forever">Verify in your browser</a></div>',
         "</main>" + _FOOTER + "</body></html>"]
    return "".join(h)


def sitemap():
    urls = [SITE + "/answers", SITE + "/standard/forever-proof", SITE + "/forever", SITE + "/bitcoin",
            SITE + "/bitcoin/code", SITE + "/gateway", SITE + "/standard/ai-decision-receipt", SITE + "/pilot"] + [SITE + "/answers/" + a["slug"] for a in ANSWERS]
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
            "".join("  <url><loc>%s</loc><changefreq>weekly</changefreq></url>\n" % u for u in urls) + "</urlset>\n")


def _llms():
    try:
        with open(os.path.join(ROOT, "llms.txt"), "r", encoding="utf-8") as fh:
            return fh.read()
    except Exception:
        return None


def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "public, max-age=300")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)
    _state["served"] += 1


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_answers_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        try:
            if p == "/answers":
                return _send(self, index_page(), "text/html; charset=utf-8")
            if p.startswith("/answers/") and p[9:] in BY_SLUG:
                return _send(self, answer_page(BY_SLUG[p[9:]]), "text/html; charset=utf-8")
            if p == "/standard/forever-proof":
                return _send(self, standard_page(), "text/html; charset=utf-8")
            if p == "/sitemap-answers.xml":
                return _send(self, sitemap(), "application/xml; charset=utf-8")
            if p == "/llms.txt":
                body = _llms()
                if body:
                    return _send(self, body, "text/plain; charset=utf-8")
        except Exception as e:
            _state["last_error"] = str(e)[:200]
        return orig(self)

    H.do_GET = do_GET
    H._answers_pages = True
    _state["pages"] = True
    return True


def handle(method, action, data, api_key, ctx):
    with _lock:
        try:
            _install_pages()
        except Exception as e:
            _state["last_error"] = str(e)[:200]
    if action == "spec":
        return {"module": "answers", "version": VERSION,
                "pages": [SITE + "/answers"] + [SITE + "/answers/" + a["slug"] for a in ANSWERS],
                "standard": SITE + "/standard/forever-proof", "llms_txt": SITE + "/llms.txt",
                "sitemap": SITE + "/sitemap-answers.xml"}, 200
    return {"module": "answers", "version": VERSION, "armed": _state["pages"], "answers": len(ANSWERS),
            "index": SITE + "/answers", "llms_txt": SITE + "/llms.txt", "llms_txt_present": bool(_llms()),
            "sitemap": SITE + "/sitemap-answers.xml", "served": _state["served"],
            "last_error": _state["last_error"]}, 200

```


## `modules/archive.py`

493 lines, 20135 bytes

```python
"""
modules/archive.py  v1.0  -  the self-proving archive

Once a day this writes ONE file that proves itself:

  - every public block of the chain, with the exact text each was sealed from
  - the chain's genesis and tip
  - an independent witness's own record of our tips (MIR), as fetched
  - a Bitcoin proof of a tip inside the file
  - the fingerprint of yesterday's file, so the files chain like the blocks
  - AND THE CHECKING PROGRAM ITSELF, carried inside the file

The file's name is its fingerprint: SHA-256 of its canonical form (keys
sorted, no spaces). That fingerprint is sealed into the chain as a public
block, and that block is anchored to Bitcoin with the next hourly stamp.

So it does not matter who hosts a copy. Ours, a peer's, a customer's, the
Internet Archive's, an email attachment - any copy, anywhere, proves itself:

    python3 -c "import json,sys;exec(json.load(open(sys.argv[1]))['verifier_py'])" FILE

That recomputes every block, checks every link from genesis, confirms the
witness's tips are in the chain, checks the Bitcoin proof commits to a tip
in the chain, and prints the file's own fingerprint to compare with the
sealed one. Nothing from sebbi.pro is needed, including sebbi.pro.

Reformatting a copy does not break it: the fingerprint is taken over the
canonical form, so a pretty-printed or re-serialised copy still matches.

Routes (public): status, latest, manifest, file?sha256=, day?date=, verifier,
spec. run is keyed. Armed by the first visit to /x/archive/status.
Files live on the anchor volume; the last KEEP_FILES are kept on disk. Every
day's fingerprint is kept forever in the chain, and each file contains all
history, so the newest file always covers everything before it.
"""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

VERSION = "1.0"
FORMAT = "sebbi-self-proving-archive/1"
BASE = "https://sebbi.pro/x/archive/"
SITE = "https://sebbi.pro"
USER_ID = "system_archive"
ARCHIVE_DIR = os.path.join(os.environ.get("ANCHOR_DIR", "/data/anchors"),
                           "archive")
KEEP_FILES = 30
PAGE = 500
FETCH_TIMEOUT = 45
MAX_BYTES = 64 * 1024 * 1024
WITNESS = {"name": "MIR (MIRegistry)",
           "url": "https://mir.events/v1/transparency/held/tips?peer=sebbi"}
ANCHOR_URL = SITE + "/x/ots/latest_confirmed"
WAYBACK_SAVE = "https://web.archive.org/save/"
UA = "sebbi-archive/1.0 (+https://sebbi.pro/x/archive/spec)"

PUBLIC = {("GET", "status"), ("GET", "latest"), ("GET", "manifest"),
          ("GET", "file"), ("GET", "day"), ("GET", "verifier"),
          ("GET", "spec")}

_state = {"armed": False, "ctx": None, "last_run": None, "last_result": None}
_lock = threading.Lock()
_run_lock = threading.Lock()


# ---------------------------------------------------------------- the verifier
#
# Carried inside every file. Standard library only. Runs anywhere Python 3
# runs, with nothing from sebbi.pro.

VERIFIER = r'''
import hashlib, json, sys

path = sys.argv[1]
with open(path, "rb") as fh:
    raw = fh.read()
b = json.loads(raw.decode("utf-8"))
canon = json.dumps(b, sort_keys=True, separators=(",", ":")).encode("utf-8")
fp = hashlib.sha256(canon).hexdigest()
problems = []

print("File fingerprint (canonical SHA-256):", fp)
print("Compare it with the fingerprint sealed for", b.get("date"),
      "- listed in the manifest and sealed in the chain.")

blocks = b["chain"]["blocks"]
prev = "GENESIS"
hashes = {}
public = withheld = 0
for blk in blocks:
    h = blk["audit_hash"]
    if "preimage" in blk:
        pre = blk["preimage"]
        if hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
            problems.append("block %s does not recompute" % blk["block_index"])
        stated = json.loads(pre).get("prev_hash")
        public += 1
    else:
        stated = blk.get("prev_hash")
        withheld += 1
    if stated != prev:
        problems.append("block %s does not link to the block before it"
                        % blk["block_index"])
    hashes[h] = blk["block_index"]
    prev = h

if blocks and blocks[0]["audit_hash"] != b["chain"]["genesis_hash"]:
    problems.append("first block is not the declared genesis")
if prev != b["chain"]["tip"]:
    problems.append("the chain does not end at the declared tip")
print("Blocks: %d  (%d recomputed from their own text, %d linkage only)"
      % (len(blocks), public, withheld))

w = b.get("witness") or {}
held = [e for e in w.get("entries", []) if e.get("peer_tip") in hashes]
print("Witness %s: %d of its recorded tips are blocks in this chain"
      % (w.get("name"), len(held)))
if w.get("entries") and not held:
    problems.append("none of the witness's tips are in this chain")

a = b.get("anchor") or {}
if a.get("tip"):
    if a["tip"] not in hashes:
        problems.append("the anchored tip is not a block in this chain")
    else:
        print("Bitcoin: tip at block %s committed in Bitcoin block(s) %s"
              % (hashes[a["tip"]], a.get("bitcoin_block_heights")))
        try:
            import base64
            from opentimestamps.core.serialize import BytesDeserializationContext
            from opentimestamps.core.timestamp import DetachedTimestampFile
            det = DetachedTimestampFile.deserialize(BytesDeserializationContext(
                base64.b64decode(a["ots_base64"])))
            if det.file_digest != hashlib.sha256(bytes.fromhex(a["tip"])).digest():
                problems.append("the Bitcoin proof is for a different value")
            else:
                print("Bitcoin proof commits to that tip. For the final step "
                      "against Bitcoin itself: ots verify.")
        except ImportError:
            print("Install opentimestamps-client to read the Bitcoin proof "
                  "here; the proof bytes are in anchor.ots_base64.")
else:
    print("Bitcoin: no confirmed proof was available when this file was made.")

print("Previous file:", b.get("previous_file_sha256") or "none - this is the first")
if problems:
    print("FAIL")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print("PASS - every check above was done here, from this file alone.")
'''


# ---------------------------------------------------------------- storage

def _ensure(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS archive_files ("
        "date TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, blocks INTEGER, "
        "tip TEXT, previous_sha256 TEXT, sealed_block INTEGER, "
        "sealed_hash TEXT, wayback TEXT, created_at REAL)")
    conn.commit()


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("response too large")
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def _path(date, sha):
    return os.path.join(ARCHIVE_DIR, "sebbi-chain-%s-%s.json" % (date, sha))


# ---------------------------------------------------------------- building

def _collect_blocks():
    blocks, after = [], 0
    while True:
        page, _ = _fetch_json("%s/x/walk/blocks?after=%d&limit=%d"
                              % (SITE, after, PAGE))
        blocks.extend(page.get("blocks") or [])
        if not page.get("has_more"):
            break
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            raise ValueError("walk paging did not advance")
        after = nxt
    return blocks


def _build(ctx):
    conn, dblock, seal = ctx.get("conn"), ctx.get("lock"), ctx.get("seal")
    date = time.strftime("%Y-%m-%d", time.gmtime())
    with dblock:
        _ensure(conn)
        if conn.execute("SELECT 1 FROM archive_files WHERE date = ?",
                        (date,)).fetchone():
            return {"ok": True, "skipped": "today's file already exists"}
        prev = conn.execute("SELECT sha256 FROM archive_files "
                            "ORDER BY date DESC LIMIT 1").fetchone()

    blocks = _collect_blocks()
    if not blocks:
        return {"ok": False, "error": "no blocks to archive"}
    hashes = set(b["audit_hash"] for b in blocks)

    witness = {"name": WITNESS["name"], "source": WITNESS["url"],
               "entries": [], "fetched_sha256": None, "note": None}
    try:
        data, digest = _fetch_json(WITNESS["url"])
        witness["fetched_sha256"] = digest
        witness["entries"] = [e for e in (data.get("tips") or [])
                              if e.get("peer_tip") in hashes]
        witness["note"] = ("Entries kept are those whose peer_tip is a block "
                           "in this file. fetched_sha256 is the hash of the "
                           "witness's response as served on the day.")
    except Exception as exc:
        witness["note"] = "witness unreachable on the day (%s)" % \
            exc.__class__.__name__

    anchor = None
    try:
        data, _ = _fetch_json(ANCHOR_URL)
        if data.get("ok") and data.get("tip") in hashes:
            anchor = {k: data.get(k) for k in (
                "tip", "stamp_id", "stamped_at", "bitcoin_block_heights",
                "ots_base64", "tip_is_block")}
    except Exception:
        anchor = None

    bundle = {
        "format": FORMAT,
        "date": date,
        "made_by": "https://sebbi.pro",
        "chain": {"genesis_hash": blocks[0]["audit_hash"],
                  "tip": blocks[-1]["audit_hash"],
                  "block_count": len(blocks),
                  "seal_formula": "audit_hash = sha256 of the block's preimage "
                                  "text; each preimage names the previous "
                                  "block's hash as prev_hash; the first is "
                                  "GENESIS.",
                  "blocks": blocks},
        "witness": witness,
        "anchor": anchor,
        "previous_file_sha256": prev[0] if prev else None,
        "fingerprint_rule": "SHA-256 of this file's canonical form: JSON with "
                            "keys sorted and no whitespace. Reformatting a "
                            "copy does not change it.",
        "verify": "python3 -c \"import json,sys;exec(json.load(open(sys.argv[1]))"
                  "['verifier_py'])\" THIS_FILE.json",
        "verifier_py": VERIFIER,
        "not_included": "Blocks sealed under a customer's key appear with "
                        "hash and link only; their owners hold the contents.",
    }
    canon = _canonical(bundle)
    sha = hashlib.sha256(canon).hexdigest()

    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    tmp = _path(date, sha) + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(canon)
    os.replace(tmp, _path(date, sha))

    file_url = "%sfile?sha256=%s" % (BASE, sha)
    sealed_block = sealed_hash = None
    if callable(seal):
        now = time.time()
        event = {"user_id": USER_ID, "action": "self_proving_archive_written",
                 "amount": 0, "country": "UK", "device_id": "archive",
                 "anomaly": 0, "device_risk": 0}
        result = {"decision": "ARCHIVED", "score": 0, "date": date,
                  "file_sha256": sha, "bytes": len(canon),
                  "blocks": len(blocks), "chain_tip": blocks[-1]["audit_hash"],
                  "previous_file_sha256": bundle["previous_file_sha256"],
                  "witness_entries": len(witness["entries"]),
                  "bitcoin_anchor_included": bool(anchor),
                  "file_url": file_url, "timestamp": now}
        try:
            res = seal(event, result, now)
            if isinstance(res, (list, tuple)):
                sealed_hash, sealed_block = res[0], (res[1] if len(res) > 1 else None)
            elif isinstance(res, dict):
                sealed_hash = res.get("audit_hash") or res.get("hash")
                sealed_block = res.get("block_index") or res.get("index")
        except Exception:
            pass

    wayback = _offer_to_archive(file_url)

    with dblock:
        conn.execute(
            "INSERT OR REPLACE INTO archive_files (date, sha256, bytes, blocks, "
            "tip, previous_sha256, sealed_block, sealed_hash, wayback, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (date, sha, len(canon), len(blocks), blocks[-1]["audit_hash"],
             bundle["previous_file_sha256"], sealed_block, sealed_hash,
             wayback, time.time()))
        conn.commit()
    _prune()
    return {"ok": True, "date": date, "sha256": sha, "bytes": len(canon),
            "blocks": len(blocks), "sealed_block": sealed_block,
            "file": file_url, "wayback": wayback}


def _offer_to_archive(url):
    """One courtesy request a day to the Internet Archive. If it refuses,
    nothing depends on it - the file proves itself wherever it is kept."""
    try:
        req = urllib.request.Request(WAYBACK_SAVE + url,
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as resp:
            final = resp.geturl()
        return final if "/web/" in final else "requested"
    except urllib.error.HTTPError as exc:
        return "refused (HTTP %s)" % exc.code
    except Exception as exc:
        return "unreachable (%s)" % exc.__class__.__name__


def _prune():
    try:
        files = sorted(f for f in os.listdir(ARCHIVE_DIR)
                       if f.startswith("sebbi-chain-") and f.endswith(".json"))
        for f in files[:-KEEP_FILES]:
            os.remove(os.path.join(ARCHIVE_DIR, f))
    except Exception:
        pass


def _loop():
    time.sleep(90)
    while True:
        ctx = _state.get("ctx")
        if ctx and _run_lock.acquire(blocking=False):
            try:
                _state["last_result"] = _build(ctx)
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
    threading.Thread(target=_loop, name="archive", daemon=True).start()


# ---------------------------------------------------------------- routes

def _rows(ctx, limit=400):
    conn, dblock = ctx["conn"], ctx["lock"]
    with dblock:
        _ensure(conn)
        return conn.execute(
            "SELECT date, sha256, bytes, blocks, tip, previous_sha256, "
            "sealed_block, wayback FROM archive_files ORDER BY date DESC "
            "LIMIT ?", (limit,)).fetchall()


def _entry(r):
    date, sha, size, blocks, tip, prev, blk, wb = r
    on_disk = os.path.exists(_path(date, sha))
    return {"date": date, "sha256": sha, "bytes": size, "blocks": blocks,
            "chain_tip": tip, "previous_file_sha256": prev,
            "sealed_in_block": blk,
            "check_block": ("%s/x/walk/block?index=%s" % (SITE, blk)) if blk else None,
            "file": ("%sfile?sha256=%s" % (BASE, sha)) if on_disk else None,
            "on_this_server": on_disk, "internet_archive": wb}


def _serve_file(date, sha):
    p = _path(date, sha)
    if not os.path.exists(p):
        return {"ok": False, "error": "not_on_this_server",
                "detail": "Only the last %d files are kept here, and the "
                          "newest always contains everything before it. Any "
                          "copy held anywhere else proves itself."
                          % KEEP_FILES}, 404
    with open(p, "rb") as fh:
        return json.loads(fh.read().decode("utf-8")), 200


def _file(data, ctx):
    sha = str((data or {}).get("sha256") or "").strip().lower()
    if isinstance((data or {}).get("sha256"), list):
        sha = str(data["sha256"][0]).strip().lower()
    for r in _rows(ctx):
        if r[1] == sha:
            return _serve_file(r[0], r[1])
    return {"ok": False, "error": "unknown_fingerprint",
            "manifest": BASE + "manifest"}, 404


def _day(data, ctx):
    d = (data or {}).get("date")
    if isinstance(d, list):
        d = d[0]
    for r in _rows(ctx):
        if r[0] == str(d):
            return _serve_file(r[0], r[1])
    return {"ok": False, "error": "no_file_for_that_date",
            "manifest": BASE + "manifest"}, 404


def _status(ctx):
    rows = _rows(ctx, 7)
    return {"ok": True, "module": "archive", "version": VERSION,
            "format": FORMAT, "armed": _state["armed"],
            "last_run": _state["last_run"], "last_result": _state["last_result"],
            "recent_files": [_entry(r) for r in rows],
            "what_it_is": "One file a day that proves itself: every public "
                          "block, a witness's record, a Bitcoin proof, and "
                          "the checking program, in one file named by its "
                          "own fingerprint. Any copy, anywhere, can be "
                          "checked without sebbi.pro.",
            "routes": {"latest": BASE + "latest", "manifest": BASE + "manifest",
                       "verifier": BASE + "verifier", "spec": BASE + "spec"}}, 200


def handle(method, action, data, api_key, ctx):
    ctx = ctx or {}
    try:
        _arm(ctx)
        if action in ("status", ""):
            return _status(ctx)
        if action == "latest":
            rows = _rows(ctx, 1)
            if not rows:
                return {"ok": False, "error": "no_file_yet",
                        "detail": "The first file is written about 90 "
                                  "seconds after /x/archive/status is "
                                  "first opened."}, 404
            return dict(_entry(rows[0]), ok=True), 200
        if action == "manifest":
            return {"ok": True, "format": FORMAT,
                    "files": [_entry(r) for r in _rows(ctx)],
                    "note": "Every fingerprint here is also sealed in the "
                            "chain, in the block shown."}, 200
        if action == "file":
            return _file(data, ctx)
        if action == "day":
            return _day(data, ctx)
        if action == "verifier":
            return {"ok": True, "verifier_py": VERIFIER,
                    "run": "python3 -c \"import json,sys;exec(json.load("
                           "open(sys.argv[1]))['verifier_py'])\" FILE.json",
                    "note": "The same program is carried inside every file."}, 200
        if action == "spec":
            return {"module": "archive", "version": VERSION, "format": FORMAT,
                    "fingerprint": "SHA-256 of the file's canonical JSON "
                                   "(sorted keys, no whitespace)",
                    "chained": "each file names the previous day's fingerprint",
                    "sealed": "each day's fingerprint is sealed in the chain, "
                              "which is anchored to Bitcoin hourly",
                    "routes": {"status": BASE + "status",
                               "latest": BASE + "latest",
                               "manifest": BASE + "manifest",
                               "file": BASE + "file?sha256=<fingerprint>",
                               "day": BASE + "day?date=YYYY-MM-DD",
                               "verifier": BASE + "verifier"}}, 200
        if action == "run":
            if not api_key:
                return {"ok": False, "error": "api_key_required"}, 401
            with _run_lock:
                return _build(ctx), 200
        return {"ok": False, "error": "unknown_action",
                "get": sorted(a for m, a in PUBLIC if m == "GET")}, 404
    except Exception as exc:
        return {"ok": False, "error": "archive_failed",
                "detail": str(exc)[:200]}, 500

```


## `modules/arm.py`

86 lines, 2810 bytes

```python
"""
modules/arm.py  v1.0.1
One tap arms everything:  https://sebbi.pro/x/arm/status

Every Railway deploy clears the page hooks that modules add. This finds every
module in the modules folder by itself - including any added later, so it
never needs updating - and arms each one in the right order:

    meter first (so the device meter is counting straight away),
    everything else,
    homelink and earnpage last (they wrap the homepage).

It answers with each module's name, version and whether it armed, so one
look tells you the whole site is up. A module that fails is reported and
skipped; it never stops the others.

v1.0.1: two taps at once now run one after the other, so a double tap or a
browser retrying a slow first tap never has two threads patching the page
handler at the same moment.
"""

import importlib
import os
import threading
import time

VERSION = "1.0.1"
PUBLIC = {("GET", "status"), ("GET", "spec")}

FIRST = ["meter"]
LAST = ["homelink", "earnpage"]
SKIP = {"arm", "router", "armall", "__init__"}


def _names():
    here = os.path.dirname(os.path.abspath(__file__))
    found = sorted(f[:-3] for f in os.listdir(here)
                   if f.endswith(".py") and not f.startswith("_") and f[:-3] not in SKIP)
    middle = [n for n in found if n not in FIRST and n not in LAST]
    return [n for n in FIRST if n in found] + middle + [n for n in LAST if n in found]


def _load(name):
    pkg = __package__ or ""
    return importlib.import_module(pkg + "." + name if pkg else name)


_run_lock = threading.Lock()


def handle(method, action, data, api_key, ctx):
    with _run_lock:
        return _arm_all(ctx)


def _arm_all(ctx):
    started = time.time()
    results, ok, failed = [], 0, 0
    for name in _names():
        entry = {"module": name}
        try:
            mod = _load(name)
            fn = getattr(mod, "handle", None)
            if not callable(fn):
                entry["armed"] = None
                entry["note"] = "no status route"
            else:
                out = fn("GET", "status", {}, None, ctx)
                body = out[0] if isinstance(out, tuple) else out
                body = body if isinstance(body, dict) else {}
                entry["version"] = body.get("version")
                entry["armed"] = body.get("armed", True)
            if entry.get("armed") is False:
                failed += 1
            else:
                ok += 1
        except Exception as e:
            entry["armed"] = False
            entry["error"] = str(e)[:160]
            failed += 1
        results.append(entry)
    return ({"module": "arm", "version": VERSION, "armed": failed == 0,
             "modules_armed": ok, "modules_failed": failed,
             "seconds": round(time.time() - started, 2),
             "results": results}, 200)

```


## `modules/armall.py`

77 lines, 2716 bytes

```python
"""
modules/armall.py  v1.0.0
One tap arms every page module after a deploy.

    GET /x/armall/status

Railway restarts the server on every deploy, and every page module (the ones
that serve their own URL through a do_GET patch - /passport, /map, /witness,
the homepage button, the consoles...) goes quiet until its status route is
hit. This module finds every file in modules/ that installs a do_GET patch
and arms it, in one request, and reports what it armed.

It only touches page modules, and only by calling their own status route -
exactly what tapping each one by hand does. Nothing else in modules/ is run.
New page modules are picked up automatically: no list to maintain.

Point Railway's healthcheck at /x/armall/status and every deploy arms itself.
"""

import importlib.util
import os
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.splitext(os.path.basename(__file__))[0]


def _is_page_module(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except Exception:
        return False
    return ".do_GET = " in src and "def handle(" in src


def _load(name, path):
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f and os.path.abspath(f) == path and hasattr(m, "handle"):
            return m
    spec = importlib.util.spec_from_file_location("armall_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def handle(method, action, data, api_key, ctx):
    armed, failed = {}, {}
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        if name == SELF:
            continue
        path = os.path.join(HERE, fn)
        if not _is_page_module(path):
            continue
        try:
            mod = _load(name, path)
            res = mod.handle("GET", "status", {}, None, ctx)
            body = res[0] if isinstance(res, tuple) else res
            ok = body.get("armed", True) if isinstance(body, dict) else True
            (armed if ok else failed)[name] = (body.get("serves") if isinstance(body, dict)
                                               else None) or "armed"
        except Exception as e:
            failed[name] = str(e)[:160]
    return {"module": "armall", "version": VERSION,
            "armed": armed, "failed": failed,
            "count": len(armed),
            "all_ok": not failed,
            "tip": "Set Railway's healthcheck path to /x/armall/status and deploys arm "
                   "themselves."}, 200

```
