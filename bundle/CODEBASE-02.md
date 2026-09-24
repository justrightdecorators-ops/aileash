# Codebase — part 2 of 41

Contains:
- `modules/_ _ i n i t _ _ . p y`
- `modules/agentroom.py`
- `modules/archive.py`
- `modules/armall.py`
- `modules/auditbridge.py`
- `modules/backups.py`


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


## `modules/auditbridge.py`

490 lines, 27978 bytes

```python
"""
modules/auditbridge.py  v1.0.0
sebbi.pro for auditors: the chain answers inside Excel and Google Sheets.

Page module (runtime do_GET patch, like map.py). Serves:

    /auditors                     the page
    /a/help                       every command, plain text
    /a/verify?hash=H              VERIFIED · block N · time   or   NOT FOUND
    /a/tip                        the latest block
    /a/count?day=YYYY[-MM[-DD]]   records sealed in that period
    /a/btc                        the latest Bitcoin block height and hash
    /a/sample?n=25&btc=HEIGHT     a CSV sample selected by that Bitcoin block's hash
    /a/audit?domain=D             any company's AI integrity level, checked live, sealed
    /a/oscal                      OSCAL assessment results pointing at live proofs

Plain text (one line, or CSV for samples) so spreadsheets read it directly:
    Google Sheets  =IMPORTDATA("https://sebbi.pro/a/verify?hash="&A2)
    Excel          =WEBSERVICE("https://sebbi.pro/a/verify?hash="&A2)

Read-only against the chain, except /a/audit, which runs the existing
integrity checker (that checker seals its own verdicts, one per domain per day).
Armed by /x/auditbridge/status after each deploy.
"""

import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
PAGE = "/auditors"
BASE = "https://sebbi.pro"
MAX_SAMPLE = 200

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij48bWV0YSBuYW1lPSJ2aWV3"
    "cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MSx2aWV3cG9ydC1maXQ9Y292ZXIiPgo8dGl0"
    "bGU+c2ViYmkucHJvIGZvciBhdWRpdG9ycyDigJQgdGhlIGNoYWluIGluc2lkZSB5b3VyIHNwcmVhZHNoZWV0PC90aXRsZT4KPG1l"
    "dGEgbmFtZT0iZGVzY3JpcHRpb24iIGNvbnRlbnQ9IlR5cGUgYSBmb3JtdWxhIGluIEV4Y2VsIG9yIEdvb2dsZSBTaGVldHMgYW5k"
    "IGV2ZXJ5IHJvdyB2ZXJpZmllcyBpdHNlbGYgYWdhaW5zdCB0aGUgc2ViYmkucHJvIGNoYWluLiBQbHVzIHRoZSBhdWRpdCBzYW1w"
    "bGUgbm9ib2R5IGNob3NlLCBzZWVkZWQgYnkgYSBmdXR1cmUgQml0Y29pbiBibG9jay4iPgo8bGluayBocmVmPSJodHRwczovL2Zv"
    "bnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDUwMCZmYW1pbHk9SUJNK1Bs"
    "ZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMCZkaXNwbGF5PXN3YXAiIHJl"
    "bD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzBhMGYxZTstLXBhcGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7"
    "LS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0tbXV0ZWQ6IzVBNjI3MDstLXNhbnM6J0lCTSBQbGV4IFNhbnMnLHN5c3RlbS11"
    "aSxzYW5zLXNlcmlmOy0tc2VyaWY6J05ld3NyZWFkZXInLEdlb3JnaWEsc2VyaWY7LS1tb25vOidJQk0gUGxleCBNb25vJyx1aS1t"
    "b25vc3BhY2UsbW9ub3NwYWNlfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Ym9keXtmb250LWZh"
    "bWlseTp2YXIoLS1zYW5zKTtiYWNrZ3JvdW5kOnZhcigtLXBhcGVyKTtjb2xvcjp2YXIoLS1pbmspO2xpbmUtaGVpZ2h0OjEuNn0K"
    "LndyYXB7bWF4LXdpZHRoOjgyMHB4O21hcmdpbjowIGF1dG87cGFkZGluZzowIDIwcHh9LnRvcHtib3JkZXItYm90dG9tOjFweCBz"
    "b2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjE1cHggMH0udG9wIC53cmFwe2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3Bh"
    "Y2UtYmV0d2VlbjtmbGV4LXdyYXA6d3JhcDtnYXA6MTBweH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6"
    "ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0udG9wIGF7Zm9udC1mYW1pbHk6dmFyKC0t"
    "bW9ubyk7Zm9udC1zaXplOjEyLjVweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2luLWxlZnQ6"
    "MTRweH0KLmhlcm97cGFkZGluZzo1MHB4IDAgMjRweH0ua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJw"
    "eDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDdlbTttYXJnaW4tYm90dG9tOjEycHh9Cmgxe2ZvbnQtZmFtaWx5"
    "OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDMycHgsNnZ3LDUycHgpO2xpbmUtaGVpZ2h0OjEu"
    "MDY7bWF4LXdpZHRoOjE3Y2g7bWFyZ2luLWJvdHRvbToxNnB4fS5oZXJvIHB7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbXV0"
    "ZWQpO21heC13aWR0aDo1OGNofQpzZWN0aW9ue3BhZGRpbmc6MzhweCAwO2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "fWgye2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDI0cHgsNHZ3LDM0cHgp"
    "O2xpbmUtaGVpZ2h0OjEuMTU7bWFyZ2luLWJvdHRvbToxMnB4O21heC13aWR0aDoyNGNofQoubGVhZHtjb2xvcjp2YXIoLS1tdXRl"
    "ZCk7bWF4LXdpZHRoOjYyY2g7bWFyZ2luLWJvdHRvbToxOHB4fQouc2hlZXR7YmFja2dyb3VuZDojZmZmO2JvcmRlcjoxcHggc29s"
    "aWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo4cHg7b3ZlcmZsb3c6aGlkZGVuO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2Zv"
    "bnQtc2l6ZToxMnB4fQouc2hlZXQgLmZ4e2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6OXB4IDEy"
    "cHg7YmFja2dyb3VuZDojZjNmMmVjO292ZXJmbG93LXg6YXV0bzt3aGl0ZS1zcGFjZTpub3dyYXB9LnNoZWV0IC5meCBie2NvbG9y"
    "OnZhcigtLWdvbGQpfQouc2hlZXQgdGFibGV7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2V9LnNoZWV0IHRke2Jv"
    "cmRlci10b3A6MXB4IHNvbGlkICNlZWU7cGFkZGluZzo4cHggMTJweDt3aGl0ZS1zcGFjZTpub3dyYXB9LnNoZWV0IHRkLm9re2Nv"
    "bG9yOnZhcigtLW9rKTtmb250LXdlaWdodDo1MDB9LnNoZWV0IHRkLmJhZHtjb2xvcjojOUMyRjI2O2ZvbnQtd2VpZ2h0OjUwMH0K"
    "LmdyaWR7ZGlzcGxheTpncmlkO2dhcDoxMnB4O2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9QG1lZGlhKG1pbi13aWR0aDo3MDBw"
    "eCl7LmdyaWR7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnJ9fQouY2FyZHtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyOjFweCBz"
    "b2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjE4cHggMjBweH0uY2FyZCAudHtmb250LWZhbWlseTp2"
    "YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDVlbX0uY2FyZCBoM3tm"
    "b250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyMHB4O21hcmdpbjo0cHggMCA2cHh9LmNh"
    "cmQgcHtmb250LXNpemU6MTQuNXB4O2NvbG9yOnZhcigtLW11dGVkKX0KY29kZSxwcmV7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7"
    "Zm9udC1zaXplOjEycHh9cHJle2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZThlNmRmO2JvcmRlci1yYWRpdXM6NnB4O3Bh"
    "ZGRpbmc6MTJweCAxNHB4O292ZXJmbG93LXg6YXV0bzttYXJnaW4tdG9wOjhweDt3aGl0ZS1zcGFjZTpwcmV9Ci50cnl7ZGlzcGxh"
    "eTpmbGV4O2dhcDo4cHg7ZmxleC13cmFwOndyYXA7bWFyZ2luLXRvcDoxMnB4fS50cnkgaW5wdXR7ZmxleDoxO21pbi13aWR0aDoy"
    "MDBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxMnB4O2ZvbnQt"
    "ZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fQouYnRue2JhY2tncm91bmQ6dmFyKC0tZ29sZCk7Y29sb3I6dmFyKC0t"
    "aW5rKTtib3JkZXI6MDtib3JkZXItcmFkaXVzOjZweDtwYWRkaW5nOjExcHggMTZweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtm"
    "b250LXNpemU6MTNweDtmb250LXdlaWdodDo1MDA7Y3Vyc29yOnBvaW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmU7ZGlzcGxheTpp"
    "bmxpbmUtYmxvY2t9CiNvdXR7bWFyZ2luLXRvcDoxMnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2Jh"
    "Y2tncm91bmQ6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTJweDt3"
    "aGl0ZS1zcGFjZTpwcmUtd3JhcDtkaXNwbGF5Om5vbmU7d29yZC1icmVhazpicmVhay1hbGx9CmZvb3Rlcntib3JkZXItdG9wOjFw"
    "eCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjIycHggMCA0NnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZTox"
    "MS41cHg7Y29sb3I6IzhBOTBBMH0KPC9zdHlsZT48L2hlYWQ+PGJvZHk+CjxoZWFkZXIgY2xhc3M9InRvcCI+PGRpdiBjbGFzcz0i"
    "d3JhcCI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgZm9yIGF1ZGl0b3JzPC9kaXY+PG5hdj48YSBocmVm"
    "PSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9wcm92ZSI+UHJvb2Y8L2E+PGEgaHJlZj0iL2Evb3NjYWwiPk9TQ0FMPC9hPjwvbmF2Pjwv"
    "ZGl2PjwvaGVhZGVyPgo8ZGl2IGNsYXNzPSJ3cmFwIj4KPGRpdiBjbGFzcz0iaGVybyI+PGRpdiBjbGFzcz0ia2ljayI+VEhFIENI"
    "QUlOLCBJTlNJREUgWU9VUiBTUFJFQURTSEVFVDwvZGl2Pgo8aDE+VHlwZSBhIGZvcm11bGEuIEV2ZXJ5IHJvdyBwcm92ZXMgaXRz"
    "ZWxmLjwvaDE+CjxwPk5vIGxvZ2luLCBubyBwbHVnLWluLCBubyBleHBvcnQgcmVxdWVzdC4gQXVkaXRvcnMgYWxyZWFkeSBsaXZl"
    "IGluIEV4Y2VsIGFuZCBHb29nbGUgU2hlZXRzLiBTbyB0aGUgc2ViYmkucHJvIGNoYWluIG5vdyBhbnN3ZXJzIGZyb20gaW5zaWRl"
    "IGEgY2VsbDogcGFzdGUgYSBjb2x1bW4gb2YgcmVjZWlwdHMsIGRyYWcgb25lIGZvcm11bGEgZG93biwgYW5kIGV2ZXJ5IHJvdyB2"
    "ZXJpZmllcyBpdHNlbGYgbGl2ZSBhZ2FpbnN0IHRoZSBjaGFpbi48L3A+PC9kaXY+Cgo8c2VjdGlvbiBpZD0iYW55b25lIj48aDI+"
    "QXVkaXQgYW55b25lIGluIHRoZSBsYW5kPC9oMj4KPHAgY2xhc3M9ImxlYWQiPlR5cGUgYW55IGNvbXBhbnkncyBkb21haW4uIHNl"
    "YmJpLnBybyBjaGVja3MgdGhlaXIgcHVibGlzaGVkIEFJIGludGVncml0eSBkZWNsYXJhdGlvbiBsaXZlLCB3YWxrcyBhbmQgcmVj"
    "b21wdXRlcyB0aGVpciBjaGFpbiBpZiB0aGV5IGhhdmUgb25lLCByYXRlcyB0aGVtIEwwIHRvIEw0LCBhbmQgc2VhbHMgdGhlIHZl"
    "cmRpY3QgaW50byBvdXIgY2hhaW4gc28gaXQgY2FuIG5ldmVyIGJlIHF1aWV0bHkgY2hhbmdlZC4gTm8gZGVjbGFyYXRpb24gbWVh"
    "bnMgTDAsIGFuZCB0aGF0IGlzIHNlYWxlZCB0b28uPC9wPgo8ZGl2IGNsYXNzPSJ0cnkiPjxpbnB1dCBpZD0iZCIgcGxhY2Vob2xk"
    "ZXI9ImFueS1jb21wYW55LmNvbSI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJnbygnYXVkaXQ/ZG9tYWluPScrZW5jb2Rl"
    "VVJJQ29tcG9uZW50KGQudmFsdWUudHJpbSgpKSkiPkF1ZGl0IHRoZW08L2J1dHRvbj48L2Rpdj4KPHByZT49SU1QT1JUREFUQSgi"
    "aHR0cHM6Ly9zZWJiaS5wcm8vYS9hdWRpdD9kb21haW49IiZhbXA7QTIpPC9wcmU+CjxwIGNsYXNzPSJsZWFkIiBzdHlsZT0ibWFy"
    "Z2luLXRvcDoxMnB4Ij5QdXQgYSBsaXN0IG9mIHlvdXIgc3VwcGxpZXJzIGluIGNvbHVtbiBBIGFuZCBkcmFnLiBFdmVyeSBBSSBz"
    "dXBwbGllciB5b3UgcmVseSBvbiwgcmF0ZWQgYW5kIHNlYWxlZCwgaW4gb25lIHNoZWV0LjwvcD48L3NlY3Rpb24+Cgo8c2VjdGlv"
    "bj48aDI+VmVyaWZ5IGEgd2hvbGUgY29sdW1uIGluIG9uZSBkcmFnPC9oMj4KPHAgY2xhc3M9ImxlYWQiPkVhY2ggY2VsbCBhc2tz"
    "IHRoZSBjaGFpbiBkaXJlY3RseSBhbmQgZ2V0cyBvbmUgcGxhaW4gbGluZSBiYWNrLjwvcD4KPGRpdiBjbGFzcz0ic2hlZXQiPjxk"
    "aXYgY2xhc3M9ImZ4Ij48Yj5meDwvYj4mbmJzcDsgPUlNUE9SVERBVEEoImh0dHBzOi8vc2ViYmkucHJvL2EvdmVyaWZ5P2hhc2g9"
    "IiZhbXA7QTIpPC9kaXY+Cjx0YWJsZT48dHI+PHRkPjRkZmU5NWFi4oCmYzU3NDg4MzQ8L3RkPjx0ZCBjbGFzcz0ib2siPlZFUklG"
    "SUVEIMK3IGJsb2NrIDIzOTggwrcgMjAyNi0wOS0yMVQxNDowMToyMlo8L3RkPjwvdHI+Cjx0cj48dGQ+ZDdlNzIwODDigKZkYTE2"
    "ZmM1Zjk8L3RkPjx0ZCBjbGFzcz0ib2siPlZFUklGSUVEIMK3IGJsb2NrIDIzODcgwrcgMjAyNi0wOS0yMVQxNDowMTowOVo8L3Rk"
    "PjwvdHI+Cjx0cj48dGQ+MDAwMGJhZGPigKYwZmZlZTAwMDwvdGQ+PHRkIGNsYXNzPSJiYWQiPk5PVCBGT1VORCDCtyB0aGlzIGhh"
    "c2ggaXMgbm90IGluIHRoZSBjaGFpbjwvdGQ+PC90cj48L3RhYmxlPjwvZGl2Pgo8cHJlPkdvb2dsZSBTaGVldHM6ICA9SU1QT1JU"
    "REFUQSgiaHR0cHM6Ly9zZWJiaS5wcm8vYS92ZXJpZnk/aGFzaD0iJmFtcDtBMikKRXhjZWwgKFdpbmRvd3MpOiA9V0VCU0VSVklD"
    "RSgiaHR0cHM6Ly9zZWJiaS5wcm8vYS92ZXJpZnk/aGFzaD0iJmFtcDtBMik8L3ByZT4KPGRpdiBjbGFzcz0idHJ5Ij48aW5wdXQg"
    "aWQ9ImgiIHBsYWNlaG9sZGVyPSJwYXN0ZSBhbnkgcmVjZWlwdCBoYXNoIj48YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9Imdv"
    "KCd2ZXJpZnk/aGFzaD0nK2VuY29kZVVSSUNvbXBvbmVudChoLnZhbHVlLnRyaW0oKSkpIj5WZXJpZnk8L2J1dHRvbj48L2Rpdj4K"
    "PGRpdiBpZD0ib3V0Ij48L2Rpdj48L3NlY3Rpb24+Cgo8c2VjdGlvbj48aDI+VGhlIGF1ZGl0IHNhbXBsZSBub2JvZHkgY2hvc2U8"
    "L2gyPgo8cCBjbGFzcz0ibGVhZCI+RXZlcnkgYXVkaXQgdGVzdHMgYSBzYW1wbGUsIGFuZCB0aGUgb2xkIHF1ZXN0aW9uIGlzIHdo"
    "byBwaWNrZWQgaXQuIEhlcmUgdGhlIHJhbmRvbSBzZWVkIGlzIGEgQml0Y29pbiBibG9jayB0aGF0IGhhcyBub3QgYmVlbiBtaW5l"
    "ZCB5ZXQgd2hlbiB5b3UgYXNrLiBOb2JvZHksIG5vdCB0aGUgY29tcGFueSwgbm90IHRoZSBhdWRpdG9yLCBub3Qgc2ViYmkucHJv"
    "LCBjYW4gaW5mbHVlbmNlIGl0LiBXaGVuIHRoZSBibG9jayBsYW5kcywgdGhlIHNhbXBsZSBleGlzdHM7IGJlZm9yZSB0aGVuIGl0"
    "IGNhbm5vdC48L3A+CjxwcmU+PUlNUE9SVERBVEEoImh0dHBzOi8vc2ViYmkucHJvL2Evc2FtcGxlP249MjUmYW1wO2J0Yz08aT5m"
    "dXR1cmUgYmxvY2sgaGVpZ2h0PC9pPiIpPC9wcmU+CjxwIGNsYXNzPSJsZWFkIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij5Zb3Ug"
    "Z2V0IGEgQ1NWIG9mIHNhbXBsZWQgcmVjb3Jkcywgc3RyYWlnaHQgaW50byBTaGVldHMsIEV4Y2VsLCBJREVBIG9yIEFDTCwgd2l0"
    "aCB0aGUgQml0Y29pbiBibG9jayBoYXNoIHRoYXQgc2VsZWN0ZWQgdGhlbSwgc28gYW55b25lIGNhbiByZS1ydW4gdGhlIHNlbGVj"
    "dGlvbiBhbmQgZ2V0IHRoZSBzYW1lIHJvd3MuPC9wPgo8ZGl2IGNsYXNzPSJ0cnkiPjxidXR0b24gY2xhc3M9ImJ0biIgb25jbGlj"
    "az0iZ28oJ2J0YycpIj5XaGF0J3MgdGhlIG5leHQgQml0Y29pbiBibG9jaz88L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4iIG9u"
    "Y2xpY2s9ImdvKCdzYW1wbGU/bj0xMCZidGM9bGF0ZXN0JykiPlNhbXBsZSAxMCB1c2luZyB0aGUgbGF0ZXN0IGJsb2NrPC9idXR0"
    "b24+PC9kaXY+PC9zZWN0aW9uPgoKPHNlY3Rpb24+PGgyPkV2ZXJ5IGNvbW1hbmQsIG9uZSBsaW5lIGJhY2s8L2gyPgo8ZGl2IGNs"
    "YXNzPSJncmlkIj4KPGRpdiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idCI+L2EvdmVyaWZ5P2hhc2g9PC9kaXY+PGgzPklzIHRo"
    "aXMgcmVjb3JkIGluIHRoZSBjaGFpbj88L2gzPjxwPlZFUklGSUVEIHdpdGggYmxvY2sgYW5kIHRpbWUsIG9yIE5PVCBGT1VORC48"
    "L3A+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL2F1ZGl0P2RvbWFpbj08L2Rpdj48aDM+QXVkaXQg"
    "YW55IGNvbXBhbnk8L2gzPjxwPlRoZWlyIEFJIGludGVncml0eSBsZXZlbCwgY2hlY2tlZCBsaXZlIGFuZCBzZWFsZWQuPC9wPjwv"
    "ZGl2Pgo8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0Ij4vYS90aXA8L2Rpdj48aDM+V2hlcmUgaXMgdGhlIGNoYWluIG5v"
    "dz88L2gzPjxwPkxhdGVzdCBibG9jaywgaXRzIGhhc2ggYW5kIHdoZW4gaXQgd2FzIHNlYWxlZC48L3A+PC9kaXY+CjxkaXYgY2xh"
    "c3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL2NvdW50P2RheT0yMDI2LTA5LTIxPC9kaXY+PGgzPkhvdyBtYW55IHJlY29yZHMg"
    "dGhhdCBkYXk/PC9oMz48cD5UaGUgY291bnQgZm9yIGFueSBkYXksIG1vbnRoIG9yIHllYXIsIHRvIHJlY29uY2lsZSBhZ2FpbnN0"
    "IHlvdXIgcG9wdWxhdGlvbi48L3A+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL3NhbXBsZT9uPTI1"
    "JmFtcDtidGM9PC9kaXY+PGgzPlRoZSBzYW1wbGUgbm9ib2R5IGNob3NlPC9oMz48cD5TZWVkZWQgYnkgYSBmdXR1cmUgQml0Y29p"
    "biBibG9jay4gUmUtcnVubmFibGUgYnkgYW55b25lLjwvcD48L2Rpdj4KPGRpdiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idCI+"
    "L2Evb3NjYWw8L2Rpdj48aDM+T1NDQUwgYXNzZXNzbWVudCByZXN1bHRzPC9oMz48cD5UaGUgVVMgZ292ZXJubWVudCdzIG1hY2hp"
    "bmUgZm9ybWF0IGZvciBhdWRpdCBldmlkZW5jZS4gSW1wb3J0IGl0IGludG8gR1JDIHRvb2xzOyBldmVyeSBmaW5kaW5nIHBvaW50"
    "cyBhdCBhIGxpdmUgcHJvb2YuPC9wPjwvZGl2Pgo8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0Ij4vYS9oZWxwPC9kaXY+"
    "PGgzPkFsbCBjb21tYW5kczwvaDM+PHA+UGxhaW4gdGV4dCwgcmVhZGFibGUgYnkgYW55IHRvb2wsIHNjcmlwdCBvciBBSS48L3A+"
    "PC9kaXY+CjwvZGl2Pjwvc2VjdGlvbj4KCjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZmZmO2JvcmRl"
    "ci1yYWRpdXM6MTBweDtwYWRkaW5nOjMwcHggMjRweDttYXJnaW46MzRweCAwIDQ4cHgiPgo8aDIgc3R5bGU9ImNvbG9yOiNmZmYi"
    "PkF1ZGl0b3JzOiBzdG9wIGFza2luZyBmb3Igc2NyZWVuc2hvdHMuPC9oMj4KPHAgc3R5bGU9ImNvbG9yOnJnYmEoMjU1LDI1NSwy"
    "NTUsLjc1KTttYXgtd2lkdGg6NTZjaDttYXJnaW4tYm90dG9tOjE4cHgiPkFzayB0aGUgY2hhaW4uIEl0IGFuc3dlcnMgaW4geW91"
    "ciBvd24gdG9vbHMsIHdpdGggb3VyIHNlcnZlcnMgc3dpdGNoZWQgb2ZmIGZvciBhbnl0aGluZyB5b3UgaGF2ZSBhbHJlYWR5IHZl"
    "cmlmaWVkIG9mZmxpbmUuPC9wPgo8YSBjbGFzcz0iYnRuIiBocmVmPSIjYW55b25lIj5BdWRpdCBhIGNvbXBhbnkgbm93PC9hPiA8"
    "YSBjbGFzcz0iYnRuIiBocmVmPSIvcHJvdmUiIHN0eWxlPSJiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2NvbG9yOiNmZmY7Ym9yZGVy"
    "OjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4zKSI+U2VlIGV2ZXJ5IHByb29mPC9hPjwvZGl2Pgo8L2Rpdj4KPGZvb3Rlcj48"
    "ZGl2IGNsYXNzPSJ3cmFwIj5zZWJiaS5wcm8gwrcgTW9ub3AgQ29udGVudCDCtyBCbHl0aCwgTm9ydGh1bWJlcmxhbmQsIFVLPC9k"
    "aXY+PC9mb290ZXI+CjxzY3JpcHQ+CnZhciBoPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdoJyksbz1kb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgnb3V0Jyk7CmZ1bmN0aW9uIGdvKHEpe28uc3R5bGUuZGlzcGxheT0nYmxvY2snO28udGV4dENvbnRlbnQ9J0Fza2lu"
    "ZyB0aGUgY2hhaW7igKYnO2ZldGNoKCcvYS8nK3Ese2NhY2hlOiduby1zdG9yZSd9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiBy"
    "LnRleHQoKX0pLnRoZW4oZnVuY3Rpb24odCl7by50ZXh0Q29udGVudD10fSkuY2F0Y2goZnVuY3Rpb24oKXtvLnRleHRDb250ZW50"
    "PSdDb3VsZCBub3QgcmVhY2ggdGhlIGNoYWluLid9KX0KPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)
_HTML = base64.b64decode("".join(_HTML_B64.split()))
_patched = False
_ctx = {}
_cols = {}
_btc_cache = {}


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(ts)


def _schema():
    """Find the audit_log column names rather than assuming them."""
    if _cols:
        return _cols
    with _ctx["lock"]:
        rows = _ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall()
    names = [r[1] for r in rows]
    if not names:
        return {}

    def first(opts):
        for o in opts:
            if o in names:
                return o
        return None
    _cols.update(hash=first(["audit_hash", "hash", "block_hash"]),
                 ts=first(["ts", "timestamp", "created", "time"]),
                 idx=first(["block_index", "idx", "block", "height", "id"]) or "rowid")
    return _cols


def _q(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _period(s):
    s = (s or "").strip()
    try:
        if re.fullmatch(r"\d{4}", s):
            a = datetime(int(s), 1, 1, tzinfo=timezone.utc); b = datetime(int(s) + 1, 1, 1, tzinfo=timezone.utc)
        elif re.fullmatch(r"\d{4}-\d{2}", s):
            y, m = map(int, s.split("-")); a = datetime(y, m, 1, tzinfo=timezone.utc)
            b = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            a = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc); b = a.fromtimestamp(a.timestamp() + 86400, tz=timezone.utc)
        else:
            return None
    except ValueError:
        return None
    return a.timestamp(), b.timestamp()


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "sebbi-auditbridge/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(200000).decode("utf-8", "replace").strip()


def _btc(height=None):
    """Bitcoin block (height, hash) from two public explorers; they must agree."""
    key = str(height)
    if key in _btc_cache and (height is not None or time.time() - _btc_cache[key][2] < 60):
        return _btc_cache[key][:2]
    if height is None:
        height = int(_get("https://mempool.space/api/blocks/tip/height"))
    hashes = []
    for url in ("https://mempool.space/api/block-height/%d" % height,
                "https://blockstream.info/api/block-height/%d" % height):
        try:
            hashes.append(_get(url))
        except Exception:
            pass
    good = [h for h in hashes if re.fullmatch(r"[0-9a-f]{64}", h)]
    if not good:
        return height, None
    if len(set(good)) > 1:
        raise ValueError("explorers disagree on block %d" % height)
    _btc_cache[key] = (height, good[0], time.time())
    return height, good[0]


# ---------------------------------------------------------------- commands

def c_help(q):
    return ("sebbi.pro auditor commands (plain text, one line each)\n"
            "/a/verify?hash=H             is this record in the chain\n"
            "/a/tip                       latest block\n"
            "/a/count?day=YYYY[-MM[-DD]]  records in a period\n"
            "/a/btc                       latest Bitcoin block\n"
            "/a/sample?n=25&btc=HEIGHT    sample chosen by a Bitcoin block (CSV)\n"
            "/a/audit?domain=D            any company's AI integrity level, sealed\n"
            "/a/oscal                     OSCAL assessment results\n"
            "Sheets: =IMPORTDATA(\"https://sebbi.pro/a/verify?hash=\"&A2)\n"
            "Excel:  =WEBSERVICE(\"https://sebbi.pro/a/verify?hash=\"&A2)\n"), "text/plain"


def c_verify(q):
    c = _schema()
    h = (q.get("hash") or "").strip().lower()
    if not c.get("hash"):
        return "ERROR · chain table not readable", "text/plain"
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        return "INVALID · a receipt hash is 64 hex characters", "text/plain"
    r = _q("SELECT %s,%s FROM audit_log WHERE %s=? LIMIT 1" % (c["idx"], c["ts"] or "NULL", c["hash"]), (h,))
    if not r:
        return "NOT FOUND · this hash is not in the chain", "text/plain"
    tip = _q("SELECT MAX(%s) FROM audit_log" % c["idx"])[0][0]
    depth = (tip - r[0][0]) if isinstance(tip, int) and isinstance(r[0][0], int) else "?"
    return "VERIFIED · block %s · %s · %s blocks deep" % (r[0][0], _iso(r[0][1]), depth), "text/plain"


def c_tip(q):
    c = _schema()
    r = _q("SELECT %s,%s,%s FROM audit_log ORDER BY %s DESC LIMIT 1" % (c["idx"], c["hash"], c["ts"] or "NULL", c["idx"]))
    if not r:
        return "EMPTY", "text/plain"
    return "TIP · block %s · %s · %s" % (r[0][0], r[0][1], _iso(r[0][2])), "text/plain"


def c_count(q):
    c = _schema()
    p = _period(q.get("day") or q.get("period"))
    if not p or not c.get("ts"):
        return "INVALID · use day=YYYY, YYYY-MM or YYYY-MM-DD", "text/plain"
    n = _q("SELECT COUNT(*) FROM audit_log WHERE %s>=? AND %s<?" % (c["ts"], c["ts"]), p)[0][0]
    return "COUNT · %s · %d records" % (q.get("day") or q.get("period"), n), "text/plain"


def c_btc(q):
    try:
        h, bh = _btc()
    except Exception as e:
        return "ERROR · %s" % e, "text/plain"
    return "BITCOIN · latest block %s · %s · ask for a sample with btc=%d or later" % (h, bh, h + 1), "text/plain"


def c_sample(q):
    c = _schema()
    try:
        n = max(1, min(MAX_SAMPLE, int(q.get("n", 25))))
    except ValueError:
        n = 25
    want = (q.get("btc") or "").strip().lower()
    try:
        height, bh = _btc(None if want in ("", "latest") else int(want))
    except ValueError as e:
        return "ERROR · %s" % e, "text/plain"
    except Exception:
        return "ERROR · could not reach Bitcoin explorers", "text/plain"
    if not bh:
        return ("PENDING · Bitcoin block %s is not mined yet. The sample cannot exist until it is, "
                "so nobody can have chosen it. Ask again after it lands." % height), "text/plain"
    total = _q("SELECT COUNT(*) FROM audit_log")[0][0]
    if not total:
        return "EMPTY", "text/plain"
    picks, seen, i = [], set(), 0
    while len(picks) < min(n, total):
        k = int(hashlib.sha256(("%s:%d" % (bh, i)).encode()).hexdigest(), 16) % total
        i += 1
        if k in seen:
            continue
        seen.add(k)
        r = _q("SELECT %s,%s,%s FROM audit_log ORDER BY %s LIMIT 1 OFFSET ?" % (c["idx"], c["hash"], c["ts"] or "NULL", c["idx"]), (k,))
        if r:
            picks.append((k, r[0]))
    lines = ["position,block,hash,sealed_at,verify"]
    for k, r in sorted(picks):
        lines.append("%d,%s,%s,%s,%s/a/verify?hash=%s" % (k, r[0], r[1], _iso(r[2]), BASE, r[1]))
    lines.append("# selected by Bitcoin block %s hash %s from %d records" % (height, bh, total))
    lines.append("# rule: position_i = int(sha256(blockhash + ':' + i)) mod total, skipping repeats, ordered by chain position")
    return "\n".join(lines) + "\n", "text/csv"


def _integrity():
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("integrity.py") and hasattr(m, "handle"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrity.py")
    spec = importlib.util.spec_from_file_location("auditbridge_integrity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _find(obj, keys, depth=0):
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and isinstance(obj[k], (str, int)):
                return obj[k]
        for v in obj.values():
            r = _find(v, keys, depth + 1)
            if r is not None:
                return r
    return None


def c_audit(q):
    d = (q.get("domain") or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    if not re.fullmatch(r"[a-z0-9.-]{3,253}", d) or "." not in d:
        return "INVALID · give a domain like example.com", "text/plain"
    try:
        res = _integrity().handle("GET", "check", {"domain": d}, None, _ctx)
        body = res[0] if isinstance(res, tuple) else res
    except Exception as e:
        return "ERROR · checker unavailable: %s" % str(e)[:120], "text/plain"
    lvl = _find(body, ["verified_level", "level", "verdict", "rating", "result"]) or "UNRATED"
    blk = _find(body, ["block_index", "sealed_block", "block"])
    why = _find(body, ["summary", "reason", "message", "note"])
    out = "%s · %s" % (d, lvl)
    if blk is not None:
        out += " · sealed in block %s" % blk
    if why:
        out += " · %s" % str(why)[:160]
    return out + " · full report %s/x/integrity/check?domain=%s" % (BASE, d), "text/plain"


def c_oscal(q):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tip = c_tip(q)[0]
    obs = [("Record integrity", "Every record is SHA-256 hash-chained; any edit breaks all later records.", "/api/verify-chain"),
           ("Append-only log", "RFC 6962 consistency proofs show the log only grows.", "/x/consistency/root"),
           ("Completeness", "Per-period Merkle roots with committed counts; absence is provable.", "/x/complete/periods"),
           ("External time anchor", "Chain tips anchored to Bitcoin via OpenTimestamps.", "/x/ots/latest_confirmed"),
           ("Independent witnessing", "Independent organisations hold and witness chain tips.", "/x/roster/list"),
           ("Custody", "Daily self-proving archive file with a sealed count of independent holders.", "/x/custody/status"),
           ("Authority at the moment of action", "Authority re-derived at the execution boundary; signed proofs.", "/x/continuity/decisions"),
           ("Agent permission", "Signed single-use Agent Passports, redeemed once with standing re-checked.", "/x/passport/status")]
    doc = {"assessment-results": {
        "uuid": hashlib.sha256(("sebbi-oscal:" + now[:10]).encode()).hexdigest()[:32],
        "metadata": {"title": "sebbi.pro live assessment results", "last-modified": now, "version": VERSION,
                     "oscal-version": "1.1.2", "parties": [{"type": "organization", "name": "Monop Content (sebbi.pro)"}]},
        "results": [{"title": "Live machine-verifiable evidence", "start": now,
                     "description": "Each observation links to a public route that returns the evidence itself. " + tip,
                     "observations": [{"title": t, "description": desc, "methods": ["TEST"],
                                       "relevant-evidence": [{"href": BASE + u, "description": "live, no account required"}],
                                       "collected": now} for t, desc, u in obs]}]}}
    return json.dumps(doc, indent=1), "application/json"


CMDS = {"help": c_help, "verify": c_verify, "tip": c_tip, "count": c_count, "btc": c_btc,
        "sample": c_sample, "audit": c_audit, "oscal": c_oscal}


def _send(h, body, ctype, code=200):
    b = body.encode("utf-8") if isinstance(body, str) else body
    h.send_response(code)
    h.send_header("Content-Type", ctype + ("; charset=utf-8" if not ctype.endswith("utf-8") else ""))
    h.send_header("Content-Length", str(len(b)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(b)


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


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_auditbridge_patched", False):
        _patched = True
        return True
    original = cls.do_GET

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        if path == PAGE:
            return _send(self, _HTML, "text/html")
        if path.startswith("/a/") and path[3:] in CMDS:
            if "conn" not in _ctx:
                return _send(self, "NOT ARMED · open /x/auditbridge/status once", "text/plain", 503)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            try:
                body, ctype = CMDS[path[3:]](q)
            except Exception as e:
                body, ctype = "ERROR · %s" % str(e)[:160], "text/plain"
            return _send(self, body, ctype)
        return original(self)

    cls.do_GET = do_GET
    cls._auditbridge_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    return {"module": "auditbridge", "version": VERSION, "armed": armed,
            "serves": [PAGE] + ["/a/" + k for k in CMDS],
            "page": BASE + PAGE}, 200

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
