# Codebase — part 2 of 37

Contains:
- `modules/_ _ i n i t _ _ . p y`
- `modules/agentroom.py`
- `modules/archive.py`
- `modules/armall.py`
- `modules/backups.py`
- `modules/bind.py`
- `modules/binddesk.py`


## `modules/_ _ i n i t _ _ . p y`

2 lines, 37 bytes

```
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


## `modules/backups.py`

150 lines, 5154 bytes

```python
# modules/backups.py
"""
modules/backups.py  v1.1  —  READ-ONLY backup finder

Lists what is sitting in the data volume so you can see, from a phone,
whether daily database backups exist and what dates they carry.

WHAT CHANGED IN v1.1, AND WHY
-----------------------------
v1.0 was PUBLIC and took a caller-supplied `dir` parameter. Together that let
anyone on the internet list any readable directory on the server - /etc, /app,
/root, the lot - and read back file names, sizes and timestamps with no key.
That is a free map of the deployment, handed to whoever asks.

  * every route is now KEYED. PUBLIC is empty.
  * the `dir` parameter is gone. Only the fixed candidate list below is read,
    and a path outside it cannot be reached through this module at all.

Still true, and still the point: this module only READS. It lists file names,
sizes and modified times. It opens nothing, writes nothing, deletes nothing,
and never touches the database or the chain.

REMOVE IT WHEN YOU ARE DONE
---------------------------
This was written during a chain break to find a backup. That job is over. A
route that enumerates the filesystem should not live in a deployment
permanently, even keyed. Delete the file once you no longer need it.

Route:
  GET /x/backups/list    keyed - list the known data locations
"""

import os
import time

VERSION = "1.1.0"

# Nothing here is public. Filesystem layout is not customer-facing.
PUBLIC = set()

# Fixed list. Not caller-supplied, deliberately: a directory parameter on a
# filesystem lister is a directory traversal with extra steps.
CANDIDATE_DIRS = [
    "/data",
    "/data/backups",
    "/data/anchors",
    "/data/backup",
    "/app",
    "/app/data",
]

# File types worth flagging as likely a database or a backup.
DB_HINTS = (".db", ".sqlite", ".sqlite3", ".bak", ".backup", ".dump", ".gz", ".zip")


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))
    except Exception:
        return str(ts)


def _human(n):
    try:
        n = float(n)
    except Exception:
        return str(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024
    return "%.1f TB" % n


def _list_dir(path):
    """Read-only listing of one directory. Never raises out."""
    out = {"dir": path, "exists": False, "files": []}
    try:
        if not os.path.isdir(path):
            return out
        out["exists"] = True
        entries = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
                is_dir = os.path.isdir(full)
                entries.append({
                    "name": name,
                    "is_dir": is_dir,
                    "size": None if is_dir else st.st_size,
                    "size_h": "" if is_dir else _human(st.st_size),
                    "modified": _iso(st.st_mtime),
                    "mtime": st.st_mtime,
                    "looks_like_backup": (not is_dir) and name.lower().endswith(DB_HINTS),
                })
            except Exception as e:  # noqa: BLE001
                entries.append({"name": name, "error": type(e).__name__})
        entries.sort(key=lambda e: e.get("mtime", 0), reverse=True)
        out["files"] = entries
        out["count"] = len(entries)
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__ + ": " + str(e)
    return out


def handle(method, action, data, api_key, ctx):
    if not api_key:
        return {"error": "api_key_required",
                "message": "This module lists server filesystem contents. "
                           "It is operator-only."}, 401

    if method != "GET" or action not in ("", "list"):
        return {"error": "GET /x/backups/list only", "version": VERSION}, 404

    seen = set()
    result = []
    for d in CANDIDATE_DIRS:
        if not d or d in seen:
            continue
        seen.add(d)
        result.append(_list_dir(d))

    likely = []
    for block in result:
        for f in block.get("files", []):
            if f.get("looks_like_backup"):
                likely.append({
                    "dir": block["dir"],
                    "name": f["name"],
                    "size": f.get("size_h"),
                    "modified": f.get("modified"),
                })
    likely.sort(key=lambda x: x.get("modified", ""), reverse=True)

    return {
        "version": VERSION,
        "read_only": True,
        "keyed": True,
        "note": ("This module only lists files in a fixed set of data "
                 "directories. It cannot write, delete, or touch the database "
                 "or the chain, and it cannot be pointed at any other path."),
        "likely_backups": likely,
        "likely_backups_count": len(likely),
        "directories_checked": result,
        "remove_when_done": ("This exists to find a backup during an incident. "
                             "Delete the module once you have found what you need "
                             "rather than leaving a filesystem lister deployed."),
    }, 200

```


## `modules/bind.py`

733 lines, 35203 bytes

```python
#!/usr/bin/env python3
"""modules/bind.py - the signed lane.

A peer signs their own submission with a credential, so binding rests on
possession of a secret rather than on a fetcher reaching a url.

v1.2.0 - block indices now carry their chain epoch.

A block_index on its own is not a reference. The chain restarted from
genesis on 7 September 2026, and an index issued before that became wrong
in the last day - not dangling, but resolving to a real, correctly-sealed
block belonging to someone else, as the chain grew past it. A dangling
pointer announces itself. A pointer that quietly lands on another party's
record does not.

So: every row this module writes from now on records the genesis hash of
the chain it was sealed under, and every route publishing an index says
which epoch it belongs to and whether that epoch is still current. Rows
written before this version have no epoch recorded and cannot be given
one retroactively - inventing it would be the same fault one step back -
so they publish as epoch unknown with the index marked unresolvable
against this chain. Raised by Ishaan (Shango MID), whose own rule is that
a grant carries the epoch it was decided under and is refused when the
epoch has moved.

    POST /x/bind/issue      issue a credential for a name   (operator key)
    POST /x/bind/claim      seal a dated claim marker       (operator key)
    POST /x/bind/revoke     revoke a credential             (operator key)
    POST /x/bind/submit     signed tip submission           (signature only)
    GET  /x/bind/name       binding state and history       (public)
    GET  /x/bind/conflicts  every contested name            (public)
    GET  /x/bind/spec       how to sign, in full            (public)
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

VERSION = "1.2.0"

PUBLIC = {("GET", "name"), ("GET", "conflicts"), ("GET", "spec")}

SIG_PREFIX = b"AILEASH-BIND-v1:"
CLOCK_SKEW = 300
NONCE_KEEP = 3600

RESET_DATE = "2026-09-07"

SECRET_SCOPE = (
    "A credential is a shared secret. Holding it proves the submitter had "
    "the secret, and nothing more. This platform holds a copy, so it does "
    "not exclude the operator. Anyone the secret has been shown to - a "
    "screenshot, a paste into another tool, a colleague - holds it too, and "
    "this lane cannot tell them apart. To exclude the operator, use the "
    "Ed25519 lane at /x/signed/enroll, where the private half never leaves "
    "the peer.")

EPOCH_VOCABULARY = {
    "what_an_epoch_is":
        "The genesis hash of the chain a block index was issued under. An "
        "index without it is not a reference: this chain restarted from "
        "genesis on " + RESET_DATE + ", and an index from before that now "
        "resolves to a real, correctly-sealed block belonging to someone "
        "else. Published so a stale pointer is detectably stale rather "
        "than quietly wrong.",
    "current":
        "Issued under the chain this deployment is serving now. The index "
        "resolves to the block it was issued against.",
    "retired":
        "Issued under an earlier chain. The number may still resolve here, "
        "but to a DIFFERENT block. Do not follow it.",
    "unknown":
        "Recorded before this module stored epochs, so the chain it was "
        "issued under is not known. It cannot be resolved against this "
        "chain and no epoch can be assigned to it after the fact.",
}

_ready = False
_genesis_cache = {"hash": None, "blocks": 0}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS bind_credential("
                  "key_id TEXT PRIMARY KEY,name TEXT NOT NULL,secret TEXT NOT NULL,"
                  "issued_to TEXT,issued REAL,revoked REAL,revoke_reason TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_claim("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "claimant TEXT,claimed_at REAL,note TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_submission("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "tip TEXT,key_id TEXT,ts REAL,nonce TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_nonce("
                  "nonce TEXT PRIMARY KEY,ts REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_seq("
                  "name TEXT PRIMARY KEY,seq INTEGER DEFAULT 0)")
        # v1.2.0. Added rather than backfilled: a row written before this
        # version has no epoch and must not be given one now.
        for table in ("bind_credential", "bind_claim", "bind_submission"):
            try:
                c.execute("ALTER TABLE %s ADD COLUMN chain_epoch TEXT" % table)
            except Exception:
                pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_name ON bind_submission(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_claim ON bind_claim(name)")
        c.commit()
    _ready = True


def _genesis(ctx):
    """The current chain's genesis hash, read from audit_log itself.

    Cached against the block count so it costs one cheap query per change.
    Returns None if it cannot be read, and a None epoch is recorded as
    unknown rather than guessed.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()
            blocks = int(row[0]) if row else 0
            if _genesis_cache["hash"] and _genesis_cache["blocks"] == blocks:
                return _genesis_cache["hash"]
            g = ctx["conn"].execute(
                "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1"
            ).fetchone()
        h = g[0] if g else None
        _genesis_cache["hash"] = h
        _genesis_cache["blocks"] = blocks
        return h
    except Exception:
        return None


def _ref(ctx, block_index, stored_epoch):
    """A block index published with the epoch it was issued under."""
    current = _genesis(ctx)
    if not stored_epoch:
        state = "unknown"
    elif current and stored_epoch == current:
        state = "current"
    else:
        state = "retired"
    out = {"block_index": block_index,
           "chain_epoch": stored_epoch,
           "epoch_state": state,
           "current_chain_epoch": current,
           "meaning": EPOCH_VOCABULARY[state]}
    if state == "current":
        out["resolve_at"] = ("https://sebbi.pro/x/walk/block?index=%s"
                             % block_index)
    else:
        out["do_not_resolve"] = (
            "This number may still return a block on this chain. It would "
            "be a different block. Nothing here points at it.")
    return out


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _clean_name(n):
    n = str(n or "").strip().lower()[:120]
    return "".join(ch for ch in n if ch.isalnum() or ch in ".-_/:")


def _sig(secret, name, tip, ts, nonce):
    material = SIG_PREFIX + _canon({"name": name, "tip": tip,
                                    "ts": int(ts), "nonce": nonce}).encode("utf-8")
    return hmac.new(bytes.fromhex(secret), material, hashlib.sha256).hexdigest()


def _latest_seq(ctx, name):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _issue(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400
    to = str(data.get("issued_to", "")).strip()[:200] or None

    with ctx["lock"]:
        live = ctx["conn"].execute(
            "SELECT key_id FROM bind_credential WHERE name=? AND revoked IS NULL",
            (name,)).fetchone()
    if live and not data.get("replace"):
        return {"error": "credential_already_issued", "name": name,
                "key_id": live[0],
                "message": "A live credential exists for this name. Send "
                           "replace true to revoke it and issue another, which "
                           "is itself sealed."}, 409

    secret = secrets.token_hex(32)
    key_id = "bk_" + secrets.token_hex(8)
    now = time.time()
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "credential_issued",
          "amount": 0, "country": "UK", "device_id": "bind",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "CREDENTIAL_ISSUED", "score": 0, "bind_version": VERSION,
           "name": name, "key_id": key_id, "issued_to": to,
           "secret_sealed": False, "chain_epoch": epoch,
           "detail": "name=%s;key_id=%s;issued_to=%s" % (name, key_id, to)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        if live:
            ctx["conn"].execute(
                "UPDATE bind_credential SET revoked=?, revoke_reason=? "
                "WHERE key_id=?", (now, "replaced by " + key_id, live[0]))
        ctx["conn"].execute(
            "INSERT INTO bind_credential(key_id,name,secret,issued_to,issued,"
            "audit_hash,block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (key_id, name, secret, to, now, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "key_id": key_id, "secret": secret,
            "issued_to": to, "issued_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "current_submission_seq": _latest_seq(ctx, name),
            "send_this_once": ("The secret is shown here and nowhere else. It "
                               "is not sealed into the chain and cannot be "
                               "recovered - if it is lost, revoke and reissue."),
            "how_to_sign": "/x/bind/spec",
            "what_it_proves": ("Possession of this secret. It does not prove "
                               "domain ownership and this platform does not "
                               "check that."),
            "secret_scope": SECRET_SCOPE,
            "note_on_sequence": ("current_submission_seq is where this name's "
                                 "receipt numbering stands. Reissuing a "
                                 "credential does not reset it - the sequence "
                                 "belongs to the name's submission history, "
                                 "not to the key."),
            "replaced": live[0] if live else None}, 200


def _claim(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    claimant = str(data.get("claimant", "")).strip()[:200]
    if not name or not claimant:
        return {"error": "name_and_claimant_required"}, 400
    note = str(data.get("note", "")).strip()[:500] or None
    now = time.time()
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "name_claimed", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "NAME_CLAIMED", "score": 0, "bind_version": VERSION,
           "name": name, "claimant": claimant, "note": note,
           "chain_epoch": epoch,
           "detail": "name=%s;claimant=%s" % (name, claimant)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO bind_claim(name,claimant,claimed_at,note,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?)",
            (name, claimant, now, note, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "claimant": claimant, "claimed_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "what_this_is": ("A dated marker, not a binding. Anyone can still "
                             "submit under this name - but their block is "
                             "provably later than this one, and the conflict "
                             "is public."),
            "what_this_is_not": ("Proof that the claimant owns the name, and "
                                 "not a substitute for a credential.")}, 200


def _revoke(ctx, api_key, data):
    key_id = str(data.get("key_id", "")).strip()
    if not key_id:
        return {"error": "key_id_required"}, 400
    reason = str(data.get("reason", "")).strip()[:300] or "not stated"
    now = time.time()

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT name, revoked FROM bind_credential WHERE key_id=?",
            (key_id,)).fetchone()
    if not row:
        return {"error": "unknown_key_id"}, 404
    if row[1]:
        return {"error": "already_revoked", "revoked_at": _iso(row[1])}, 409

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + row[0][:40], "action": "credential_revoked",
          "amount": 0, "country": "UK", "device_id": "bind", "anomaly": 0,
          "device_risk": 1}
    res = {"decision": "CREDENTIAL_REVOKED", "score": 0, "name": row[0],
           "key_id": key_id, "reason": reason, "chain_epoch": epoch,
           "detail": "key_id=%s;reason=%s" % (key_id, reason)}
    h, idx, _ = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE bind_credential SET revoked=?, revoke_reason=? WHERE key_id=?",
            (now, reason, key_id))
        ctx["conn"].commit()

    return {"key_id": key_id, "name": row[0], "revoked_at": _iso(now),
            "reason": reason, "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "note": "Submissions already bound stay bound. Revocation stops "
                    "future ones and does not rewrite the past."}, 200


def _submit(ctx, data):
    name = _clean_name(data.get("name"))
    tip = str(data.get("tip", "")).strip().lower()
    key_id = str(data.get("key_id", "")).strip()
    sig = str(data.get("signature", "")).strip().lower()
    nonce = str(data.get("nonce", "")).strip()[:80]
    try:
        ts = int(data.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0

    missing = [k for k, v in (("name", name), ("tip", tip), ("key_id", key_id),
                              ("signature", sig), ("nonce", nonce)) if not v]
    if missing or not ts:
        return {"error": "incomplete_submission",
                "missing": missing + ([] if ts else ["ts"]),
                "how_to_sign": "/x/bind/spec"}, 400
    if len(tip) != 64:
        return {"error": "tip_must_be_64_hex"}, 400

    now = time.time()
    if abs(now - ts) > CLOCK_SKEW:
        return {"error": "timestamp_outside_window",
                "your_ts": ts, "our_ts": int(now),
                "window_seconds": CLOCK_SKEW,
                "why": "a signature valid forever is a signature that can be "
                       "replayed forever"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT secret, revoked, issued_to FROM bind_credential "
            "WHERE key_id=? AND name=?", (key_id, name)).fetchone()
        used = ctx["conn"].execute(
            "SELECT 1 FROM bind_nonce WHERE nonce=?", (nonce,)).fetchone()

    if not cred:
        return {"error": "no_credential_for_that_name_and_key"}, 401
    if cred[1]:
        return {"error": "credential_revoked", "revoked_at": _iso(cred[1])}, 401
    if used:
        return {"error": "nonce_already_used",
                "why": "each signature may be presented once"}, 409

    expected = _sig(cred[0], name, tip, ts, nonce)
    if not hmac.compare_digest(expected, sig):
        return {"error": "signature_did_not_verify",
                "check": "/x/bind/spec sets out the exact bytes signed"}, 401

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + name[:40], "action": "signed_tip", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "TIP_BOUND", "score": 0, "bind_version": VERSION,
           "name": name, "tip": tip, "key_id": key_id, "binding": "signature",
           "chain_epoch": epoch,
           "detail": "name=%s;tip=%s;key_id=%s" % (name, tip, key_id)}

    try:
        h, idx, key_seq = ctx["seal"](ev, res, now, None)
    except Exception as exc:
        return {"ok": False, "bound": False, "error": "seal_failed",
                "detail": "Your signature verified, but the audit chain did "
                          "not seal the submission, so there is no receipt to "
                          "give you. This is a fault on this deployment and "
                          "not a problem with your submission.",
                "seal_error": "%s: %s" % (type(exc).__name__, str(exc)[:300]),
                "recorded": False,
                "retry": "Nothing was written. Your nonce is unused and the "
                         "identical submission can be resent once this is "
                         "fixed.",
                "name": name, "tip": tip}, 500
    if not h:
        return {"ok": False, "bound": False, "error": "seal_incomplete",
                "detail": "The audit chain returned no hash, so nothing was "
                          "sealed and no receipt exists. Fault on this "
                          "deployment.",
                "recorded": False, "name": name, "tip": tip}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO bind_seq(name,seq) VALUES(?,0)", (name,))
        ctx["conn"].execute(
            "UPDATE bind_seq SET seq = COALESCE(seq,0) + 1 WHERE name=?", (name,))
        srow = ctx["conn"].execute(
            "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        receipt_seq = int(srow[0]) if srow and srow[0] is not None else None

        ctx["conn"].execute(
            "INSERT INTO bind_submission(name,tip,key_id,ts,nonce,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (name, tip, key_id, now, nonce, h, idx, epoch))
        ctx["conn"].execute("INSERT OR IGNORE INTO bind_nonce(nonce,ts) "
                            "VALUES(?,?)", (nonce, now))
        ctx["conn"].execute("DELETE FROM bind_nonce WHERE ts < ?",
                            (now - NONCE_KEEP,))
        ctx["conn"].commit()

    return {"bound": True, "name": name, "tip": tip, "key_id": key_id,
            "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "receipt_seq": receipt_seq,
            "receipt_seq_scope": "per-name",
            "key_seq": key_seq,
            "binding": "signature",
            "gapless": ("receipt_seq increments by exactly one for each "
                        "accepted submission under this name. Two receipts "
                        "numbered N and N+2 prove a third exists and you did "
                        "not receive it. The current highest is published at "
                        "/x/bind/name?name=" + name + " so the check does not "
                        "depend on asking us."),
            "key_seq_note": ("The server-wide per-API-key sequence, null on "
                             "this lane and always will be. That counter lives "
                             "on an api_key and this lane authenticates by "
                             "signature with no key to count against. Returned "
                             "rather than omitted so the absence is visible "
                             "instead of inferred."),
            "what_this_proves": ("that a holder of the credential issued for "
                                 "this name submitted this tip, and that the "
                                 "submission has not been altered since it was "
                                 "signed"),
            "what_this_does_not_prove": ("which holder. The secret is shared, "
                                         "so this does not exclude the "
                                         "operator or anyone else it has been "
                                         "disclosed to. It also does not prove "
                                         "domain ownership, or that anything "
                                         "in their chain is true"),
            "secret_scope": SECRET_SCOPE,
            "check_it": "/x/bind/name?name=" + name}, 200


def _name(ctx, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT key_id, issued, revoked, issued_to, block_index, "
            "chain_epoch FROM bind_credential WHERE name=? ORDER BY issued DESC",
            (name,)).fetchall()
        claims = ctx["conn"].execute(
            "SELECT claimant, claimed_at, note, block_index, chain_epoch "
            "FROM bind_claim WHERE name=? ORDER BY claimed_at ASC",
            (name,)).fetchall()
        subs = ctx["conn"].execute(
            "SELECT tip, key_id, ts, block_index, chain_epoch "
            "FROM bind_submission WHERE name=? ORDER BY ts DESC LIMIT 20",
            (name,)).fetchall()

    live = [c for c in cred if not c[2]]
    state = ("bound" if live else
             "claimed" if claims else
             "unbound")

    out = {
        "name": name,
        "state": state,
        "lane": "signed (credential). The open lane records a separate "
                "address-level binding, published per entry on "
                "/x/roster/list. The two answer different questions and can "
                "differ without either being wrong.",
        "latest_receipt_seq": _latest_seq(ctx, name),
        "credential": ({"key_id": live[0][0], "issued_at": _iso(live[0][1]),
                        "issued_to": live[0][3],
                        "sealed_at": _ref(ctx, live[0][4], live[0][5])}
                       if live else None),
        "claims": [{"claimant": c[0], "claimed_at": _iso(c[1]), "note": c[2],
                    "sealed_at": _ref(ctx, c[3], c[4])} for c in claims],
        "signed_submissions": [{"tip": s[0], "key_id": s[1], "at": _iso(s[2]),
                                "sealed_at": _ref(ctx, s[3], s[4])}
                               for s in subs],
        "revoked_credentials": [{"key_id": c[0], "revoked_at": _iso(c[2]),
                                 "sealed_at": _ref(ctx, c[4], c[5])}
                                for c in cred if c[2]],
        "chain_epoch": EPOCH_VOCABULARY,
    }
    out["receipt_seq_note"] = (
        "latest_receipt_seq is the highest receipt number issued under this "
        "name. A holder whose own highest receipt is lower than this has not "
        "received one of them, and can say exactly how many. Public on "
        "purpose - a gap you can only see from the inside is not evidence of "
        "anything.")
    if state == "bound":
        out["meaning"] = ("A live credential exists for this name, and every "
                          "submission under it carries a signature made with "
                          "that credential. A submission establishes that "
                          "SOMEONE holding the secret sent it - not which "
                          "holder, and not that the holder is the party the "
                          "name names.")
        out["secret_scope"] = SECRET_SCOPE
    elif state == "claimed":
        out["meaning"] = ("Claimed but not bound. The dated claim above is in "
                          "the chain, so a competing submission would be "
                          "provably later - but nothing prevents one being "
                          "made. Issue a credential to close that.")
        out["flag"] = "claimable"
    else:
        out["meaning"] = ("Nobody holds a credential for this name and nobody "
                          "has claimed it. It is claimable by anyone.")
        out["flag"] = "claimable"
    out["what_binding_never_proves"] = (
        "domain ownership. A credential is a shared secret; it makes a name "
        "unstealable by a third party on this network, not a claim honest, "
        "and not unsubmittable by the operator.")
    return out, 200


def _conflicts(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT claimant) FROM bind_claim "
            "GROUP BY name HAVING COUNT(DISTINCT claimant) > 1").fetchall()
        keys = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT key_id) FROM bind_credential "
            "WHERE revoked IS NULL GROUP BY name "
            "HAVING COUNT(DISTINCT key_id) > 1").fetchall()
    return {"contested_claims": [{"name": r[0], "claimants": r[1]} for r in rows],
            "names_with_multiple_live_credentials":
                [{"name": k[0], "credentials": k[1]} for k in keys],
            "note": ("A conflict is recorded, not arbitrated. This platform "
                     "does not decide who owns a name and should not.")}, 200


def _spec(ctx):
    return {
        "bind_version": VERSION,
        "why_it_exists": ("Name binding used to depend on a fetcher reaching a "
                          "URL and parsing JSON. A reachable page serving HTML "
                          "did not bind, an unbound name was claimable by "
                          "anyone, and the failure text asserted the URL was "
                          "unreachable when the check had only established the "
                          "response was not JSON. This lane removes the fetcher "
                          "from the trust path."),
        "signing": {
            "material": "AILEASH-BIND-v1: || canonical JSON of "
                        "{name, tip, ts, nonce}, keys sorted, separators "
                        "(',',':'), UTF-8",
            "algorithm": "HMAC-SHA256, secret as raw bytes from the hex issued",
            "signature": "lower-case hex digest",
            "ts": "unix seconds, must be within %d seconds of ours" % CLOCK_SKEW,
            "nonce": "any string, once only, remembered for %d seconds"
                     % NONCE_KEEP,
        },
        "worked_example": {
            "1": "material = b'AILEASH-BIND-v1:' + "
                 '\'{"name":"example.com","nonce":"abc123",'
                 '"tip":"<64 hex>","ts":1787000000}\'.encode()',
            "2": "signature = hmac.new(bytes.fromhex(secret), material, "
                 "hashlib.sha256).hexdigest()",
            "3": "POST /x/bind/submit with name, tip, ts, nonce, key_id, signature",
            "note": "the JSON in step 1 has its keys sorted, which is why "
                    "nonce appears before tip",
        },
        "secret_scope": SECRET_SCOPE,
        "block_indices": dict(
            EPOCH_VOCABULARY,
            current_chain_epoch=_genesis(ctx),
            shape="Every index is published as an object - block_index, "
                  "chain_epoch, epoch_state, current_chain_epoch - never as "
                  "a bare number. A bare number cannot be checked for "
                  "staleness by whoever receives it.",
            rows_before_1_2_0="Recorded without an epoch and published as "
                              "unknown. No epoch is assigned to them now: "
                              "guessing one would be the same fault the "
                              "field exists to prevent.",
        ),
        "on_acceptance": {
            "receipt_seq": ("An integer, never null, incremented by exactly "
                            "one for each accepted submission UNDER THIS NAME "
                            "on this lane. Issued inside the same lock that "
                            "writes the record. Two receipts numbered N and "
                            "N+2 prove a third exists that you did not "
                            "receive. The current highest is published at "
                            "/x/bind/name."),
            "receipt_seq_scope": {
                "values": ["per-peer", "per-name", "per-chain"],
                "per-peer": "issued per registered peer_id. /x/peer/submit.",
                "per-name": "issued per bound name. /x/bind/submit.",
                "per-chain": "issued per enrolled chain name. /x/signed/submit.",
                "why_it_is_here": "The three signed lanes each count within "
                                  "their own scope, so a receipt carries the "
                                  "scope of its own sequence. The set is "
                                  "closed: a value outside this list is an "
                                  "error on our side.",
                "not_comparable_across_scopes": "Two receipts with different "
                                                "scopes are counting different "
                                                "things.",
            },
            "sealed_at": ("Where the submission landed in the chain, as an "
                          "epoch-qualified reference rather than a bare "
                          "index. See block_indices."),
            "key_seq": ("The server-wide per-API-key sequence, null on this "
                        "lane and always will be. That counter lives on an "
                        "api_key and this lane authenticates by signature "
                        "with no key to count against. Returned rather than "
                        "omitted so the absence is visible."),
            "sequence_survives_rotation": ("Reissuing or revoking a credential "
                                           "does not reset the sequence, so a "
                                           "rotation cannot be used to erase a "
                                           "gap."),
            "seal_failure": ("If the audit chain does not seal your "
                             "submission, you get 500 seal_failed and nothing "
                             "is recorded - no nonce, no sequence number, no "
                             "receipt. Resend the identical submission once "
                             "the fault is fixed."),
        },
        "what_a_signed_binding_proves": (
            "that a holder of the credential issued for that name submitted, "
            "and that the submission is unaltered since signing"),
        "what_it_does_not_prove": [
            "which holder. The secret is shared, so this does not exclude the "
            "operator or anyone it has been disclosed to.",
            "domain ownership - not checked, not implied",
            "that the submitter is who the name suggests",
            "that anything in their chain is true",
        ],
        "claims": ("A name with no credential can be given a dated claim "
                   "marker. That is not a binding. It means a later competing "
                   "submission is provably second and the conflict is public."),
        "conflicts": ("Recorded at /x/bind/conflicts and never arbitrated here. "
                      "A network that lets its operator decide who owns a name "
                      "has replaced one trusted party with another."),
        "honest_limits": [
            "A credential is a shared secret. This platform holds a copy, so "
            "in principle it could sign on a peer's behalf - which is why the "
            "public-key lane at /x/signed/enroll is the right end state and "
            "this is the interim.",
            "A secret that has been screenshotted, pasted into another tool or "
            "shown to a colleague is held by more parties than two, and this "
            "lane cannot tell them apart. Revoke and reissue, or move to the "
            "key lane.",
            "Revoking a credential stops future submissions and does not "
            "unbind past ones.",
            "An index recorded before 1.2.0 cannot be resolved against this "
            "chain and will never be resolvable. The epoch it was issued "
            "under was not recorded and cannot honestly be reconstructed.",
            "Nothing here checks DNS, TLS or WHOIS.",
            "receipt_seq proves you are missing a receipt. It does not prove "
            "why, and cannot distinguish a lost response from one never sent.",
        ],
        "changed_in_1_2_0": [
            "Block indices now travel with the genesis hash of the chain "
            "they were issued under, and every route publishing one reports "
            "whether that epoch is current, retired or unknown. Before this, "
            "an index issued under the pre-7-September chain was published "
            "as a bare number; once the chain grew past it, it resolved to a "
            "real, correctly-sealed block belonging to a different party. A "
            "dangling pointer is visibly broken - a pointer that resolves to "
            "someone else's record is not. Raised by Ishaan (Shango MID).",
            "Rows written before this version have no epoch and publish as "
            "unknown, marked unresolvable against this chain. They are not "
            "backfilled.",
            "The sealing path is unchanged except that chain_epoch now "
            "appears in the sealed result of new blocks.",
        ],
        "changed_in_1_1_2": [
            "The bound-state text no longer says only the holder can submit. "
            "SECRET_SCOPE appears wherever a secret is issued, used or "
            "reported. Raised by Ishaan (Shango MID).",
        ],
        "changed_in_1_1_1": [
            "receipt_seq_scope is a bare token from a closed set. Asked for "
            "by Philip Pinol (PRAXIS).",
        ],
        "changed_in_1_1": [
            "receipt_seq is a real per-name gapless sequence issued by this "
            "module, not the api_key counter that was always null here.",
            "A failed seal returns 500 and records nothing.",
        ],
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec(ctx)
        if action == "name":
            return _name(ctx, data)
        if action == "conflicts":
            return _conflicts(ctx)

    if method == "POST":
        if action == "submit":
            return _submit(ctx, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "issue":
            return _issue(ctx, api_key, data)
        if action == "claim":
            return _claim(ctx, api_key, data)
        if action == "revoke":
            return _revoke(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "name", "conflicts"],
            "POST": ["issue", "claim", "revoke", "submit"]}, 404

```


## `modules/binddesk.py`

312 lines, 13381 bytes

```python
#!/usr/bin/env python3
"""
modules/binddesk.py  -  buttons for the signed lane

modules/bind.py is the engine. It answers POST requests with a key, which is
correct and completely unusable from a phone: a browser address bar can only
send GET, and nothing in it can attach an Authorization header.

So this is the page. Paste the key once, tap a button. Same routes underneath,
nothing new in the trust path.

Served at /bind-desk by the same runtime do_GET patch console.py uses. The
page holds nothing - the key is typed in, kept in the tab, and sent on each
request. Every route it calls checks that key itself.

PUBLIC is empty. Nothing here is reachable without a key except the page
itself, and the page is inert until one is pasted into it.
"""

import sys

VERSION = "1.1"

# ("GET", "status") is public on purpose. The page is installed by a runtime
# patch that only runs once this module is touched, and every other route here
# needs a key - which locked the operator out of their own page, because a
# browser cannot send an Authorization header. The status route reveals only
# that the desk exists and where the page is.
PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/bind-desk", "/bind-desk.html", "/binddesk")
_patched = [False]


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Bind desk</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0f1e;color:#e8ecf5;font-family:ui-monospace,Menlo,monospace;
 font-size:14px;line-height:1.55;padding:0 0 80px}
.w{max-width:620px;margin:0 auto;padding:22px 16px}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:#6b7894;font-size:12.5px;margin-bottom:22px}
h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#c9a84c;
 margin:0 0 12px}
label{display:block;font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#6b7894;margin:12px 0 6px}
input{width:100%;background:#131b2e;border:1px solid #223052;color:#e8ecf5;
 font-family:inherit;font-size:14px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:#c9a84c}
button{width:100%;background:#c9a84c;color:#0a0f1e;border:0;border-radius:4px;
 padding:14px;font-family:inherit;font-weight:700;font-size:14px;margin-top:12px;
 cursor:pointer}
button:active{opacity:.8}
button.q{background:transparent;color:#8f98ad;border:1px solid #223052;font-weight:400}
button.danger{background:transparent;color:#ff8a80;border:1px solid #4a2422;font-weight:400}
.card{background:#131b2e;border:1px solid #223052;border-radius:7px;
 padding:18px;margin:16px 0}
.note{color:#6b7894;font-size:11.5px;line-height:1.6;margin-top:10px}
.out{margin-top:12px;font-size:12px;white-space:pre-wrap;word-break:break-all;
 background:#080c16;border:1px solid #223052;border-radius:4px;padding:12px;
 max-height:320px;overflow:auto}
.ok{color:#7fe3b0}.bad{color:#ff8a80}.warn{color:#c9a84c}
.secret{background:#0f1c15;border:1px solid #2c5c44;border-radius:5px;
 padding:14px;margin-top:12px}
.secret .lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#7fe3b0;margin-bottom:6px}
.secret .val{font-size:13px;color:#7fe3b0;word-break:break-all;line-height:1.8}
.secret .warnline{color:#c9a84c;font-size:11.5px;margin-top:10px;line-height:1.6}
.step{display:inline-block;background:#223052;color:#8f98ad;border-radius:3px;
 padding:2px 8px;font-size:11px;margin-bottom:10px}
</style></head><body><div class="w">

<h1>Bind desk</h1>
<p class="sub">Names on the witness network. Your key stays in this tab.</p>

<div class="card">
  <label for="k">Your API key</label>
  <input id="k" type="password" placeholder="paste it here" autocomplete="off">
  <p class="note">Typed once, used by every button below. Nothing is stored.</p>
</div>

<div class="card">
  <span class="step">STEP 1</span>
  <h2>Claim a name</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">Puts a dated marker in
  the chain. Does not stop anyone else submitting — but theirs is provably
  later. Do this first if the name is exposed.</p>
  <label for="cn">Name</label>
  <input id="cn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="cc">Who is claiming it</label>
  <input id="cc" placeholder="Ishaan">
  <label for="cnote">Note (optional)</label>
  <input id="cnote" placeholder="pending credential">
  <button onclick="doClaim()">Seal the claim</button>
  <div id="o-claim"></div>
</div>

<div class="card">
  <span class="step">STEP 2</span>
  <h2>Issue a credential</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">This is the real fix.
  Once issued, only the holder of the secret can submit under that name.</p>
  <label for="in">Name</label>
  <input id="in" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="ito">Issued to</label>
  <input id="ito" placeholder="Ishaan">
  <button onclick="doIssue(false)">Issue it</button>
  <button class="q" onclick="doIssue(true)">Replace the existing one</button>
  <div id="o-issue"></div>
</div>

<div class="card">
  <h2>Check a name</h2>
  <label for="qn">Name</label>
  <input id="qn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <button class="q" onclick="doLook()">Look it up</button>
  <button class="q" onclick="doConflicts()">Show every contested name</button>
  <div id="o-look"></div>
</div>

<div class="card">
  <h2>Revoke a credential</h2>
  <label for="rk">Key id</label>
  <input id="rk" placeholder="bk_..." autocapitalize="off" autocorrect="off">
  <label for="rr">Reason</label>
  <input id="rr" placeholder="rotating">
  <button class="danger" onclick="doRevoke()">Revoke</button>
  <p class="note">Stops future submissions. Anything already bound stays bound.</p>
  <div id="o-revoke"></div>
</div>

</div>
<script>
var $=function(i){return document.getElementById(i)};
function key(){var k=$('k').value.trim();return k||null}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function show(id,cls,txt){$(id).innerHTML='<div class="out '+cls+'">'+esc(txt)+'</div>'}
function shown(id,html){$(id).innerHTML=html}

async function call(path,method,body){
  var k=key();
  if(!k){return {status:0,data:{error:'paste your key at the top first'}}}
  var o={method:method,headers:{'Authorization':'Bearer '+k}};
  if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  try{
    var r=await fetch(path,o);
    var d; try{d=await r.json()}catch(e){d={error:'unreadable response'}}
    return {status:r.status,data:d};
  }catch(e){return {status:0,data:{error:'could not reach the server'}}}
}

async function doClaim(){
  var n=$('cn').value.trim(), c=$('cc').value.trim();
  if(!n||!c){show('o-claim','bad','Fill in the name and who is claiming it.');return}
  show('o-claim','','Sealing...');
  var r=await call('/x/bind/claim','POST',{name:n,claimant:c,note:$('cnote').value.trim()});
  if(r.status!==200){show('o-claim','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-claim','ok','CLAIMED\\n\\nname     '+r.data.name
    +'\\nclaimant '+r.data.claimant
    +'\\nsealed   '+r.data.sealed_in_chain
    +'\\nblock    '+r.data.block_index
    +'\\n\\nThis is a dated marker, not a binding. Do step 2.');
}

async function doIssue(replace){
  var n=$('in').value.trim(), t=$('ito').value.trim();
  if(!n){show('o-issue','bad','Enter the name.');return}
  show('o-issue','','Issuing...');
  var r=await call('/x/bind/issue','POST',{name:n,issued_to:t,replace:!!replace});
  if(r.status===409){
    show('o-issue','warn','A credential already exists for '+n
      +'.\\n\\nUse "Replace the existing one" if you mean to revoke it and issue another.');
    return;
  }
  if(r.status!==200){show('o-issue','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  shown('o-issue','<div class="secret">'
    +'<div class="lbl">send both of these to them privately</div>'
    +'<div class="val">key_id&nbsp;&nbsp;'+esc(r.data.key_id)+'</div>'
    +'<div class="val">secret&nbsp;&nbsp;'+esc(r.data.secret)+'</div>'
    +'<div class="warnline">The secret is shown here once and is not stored '
    +'anywhere. Copy it now. If it is lost you have to revoke and reissue.</div>'
    +'<div class="warnline">Do not send it over LinkedIn or anywhere public.</div>'
    +'</div>'
    +'<div class="out ok">sealed  '+esc(r.data.sealed_in_chain)
    +'\\nblock   '+esc(r.data.block_index)+'</div>');
}

async function doLook(){
  var n=$('qn').value.trim();
  if(!n){show('o-look','bad','Enter a name.');return}
  show('o-look','','Looking...');
  var r=await call('/x/bind/name?name='+encodeURIComponent(n),'GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'not found');return}
  var d=r.data;
  var cls = d.state==='bound' ? 'ok' : 'warn';
  var t='STATE   '+d.state.toUpperCase()+'\\n\\n'+d.meaning+'\\n';
  if(d.credential){t+='\\nkey_id     '+d.credential.key_id
    +'\\nissued to  '+(d.credential.issued_to||'-')
    +'\\nissued at  '+d.credential.issued_at;}
  if(d.claims&&d.claims.length){t+='\\n\\nCLAIMS';
    d.claims.forEach(function(c){t+='\\n  '+c.claimant+'  '+c.claimed_at
      +'  block '+c.block_index;});}
  if(d.signed_submissions&&d.signed_submissions.length){
    t+='\\n\\nSIGNED SUBMISSIONS  '+d.signed_submissions.length;
    d.signed_submissions.slice(0,5).forEach(function(s){
      t+='\\n  '+s.at+'  block '+s.block_index;});}
  show('o-look',cls,t);
}

async function doConflicts(){
  show('o-look','','Checking...');
  var r=await call('/x/bind/conflicts','GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'failed');return}
  var d=r.data, t='';
  if(!d.contested_claims.length && !d.names_with_multiple_live_credentials.length){
    t='No contested names.';
  } else {
    d.contested_claims.forEach(function(c){t+='CONTESTED  '+c.name+'  ('+c.claimants+' claimants)\\n'});
    d.names_with_multiple_live_credentials.forEach(function(c){
      t+='MULTIPLE CREDENTIALS  '+c.name+'  ('+c.credentials+')\\n'});
  }
  show('o-look', t==='No contested names.'?'ok':'warn', t+'\\n\\n'+d.note);
}

async function doRevoke(){
  var k=$('rk').value.trim();
  if(!k){show('o-revoke','bad','Enter the key id.');return}
  show('o-revoke','','Revoking...');
  var r=await call('/x/bind/revoke','POST',{key_id:k,reason:$('rr').value.trim()});
  if(r.status!==200){show('o-revoke','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-revoke','ok','REVOKED\\n\\nname    '+r.data.name
    +'\\nkey_id  '+r.data.key_id
    +'\\nsealed  '+r.data.sealed_in_chain
    +'\\n\\n'+r.data.note);
}
</script></body></html>"""


def _install():
    if _patched[0]:
        return "already installed"
    m = sys.modules.get("__main__")
    srv = m if (m is not None and hasattr(m, "get_bearer")) else sys.modules.get("server")
    if srv is None:
        return "no server"
    H = getattr(srv, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_binddesk_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._binddesk_patched = True
    _patched[0] = True
    print("BINDDESK: /bind-desk installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    state = _install()
    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"binddesk_version": VERSION,
                "installed": bool(_patched[0]),
                "install_result": state,
                "page": "/bind-desk",
                "engine": "/x/bind/spec",
                "what_it_does": ("Buttons for the signed lane. Claim a name, "
                                 "issue a credential, look one up, revoke one. "
                                 "The page sends the same POST requests the "
                                 "engine already accepts."),
                "note": "The page is not public in any useful sense - it is "
                        "inert until a key is pasted into it, and every route "
                        "it calls checks that key."}, 200

    if not api_key:
        return {"error": "invalid_api_key",
                "note": "Use the page at /bind-desk."}, 401

    return {"error": "unknown_action", "GET": ["status"]}, 404

```
