# Codebase — part 25 of 51

Contains:
- `modules/prove.py`
- `modules/publish.py`
- `modules/pwa.py`
- `modules/ratchet.py`
- `modules/ratelimit.py`


## `modules/prove.py`

352 lines, 30070 bytes

```python
"""
modules/prove.py  v1.0.0
"Prove it all" - every public address that proves something about sebbi.pro,
on one page at /prove, and as a machine-readable index at /prove.json.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/prove/status or /x/armall/status after each deploy.
The page checks every JSON route live from the visitor's browser, one at a
time, and shows green (answered), amber (rate-limited) or red (failed).
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIiPgo8"
    "dGl0bGU+UHJvdmUgaXQgYWxsIOKAlCBzZWJiaS5wcm8sIG1hY2hpbmUgcmVhZGFibGU8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNj"
    "cmlwdGlvbiIgY29udGVudD0iRXZlcnkgcHVibGljIHJvdXRlIHRoYXQgcHJvdmVzIHNvbWV0aGluZyBhYm91dCBzZWJiaS5wcm8s"
    "IGluIG9uZSBwbGFjZSwgY2hlY2tlZCBsaXZlLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3Nz"
    "Mj9mYW1pbHk9TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmZhbWlseT1JQk0rUGxleCtTYW5zOndnaHRANDAwOzUwMDs2"
    "MDAmZmFtaWx5PUlCTStQbGV4K01vbm86d2dodEA0MDA7NTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxl"
    "Pgo6cm9vdHstLWluazojMGEwZjFlOy0taW5rMjojMTAxODJlOy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLWVycjojZmY4"
    "YTgwOy0tYW1iOiNmMGM2NzQ7LS1tdXQ6cmdiYSgyNTUsMjU1LDI1NSwuNjIpOy0tbGluZTpyZ2JhKDIwMSwxNjgsNzYsLjE4KTsK"
    "LS1zYW5zOidJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidOZXdzcmVhZGVyJyxHZW9yZ2lhLHNl"
    "cmlmOy0tbW9ubzonSUJNIFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZX0KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7"
    "bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZmZmO2ZvbnQtZmFtaWx5OnZhcigt"
    "LXNhbnMpO2xpbmUtaGVpZ2h0OjEuNTU7LXdlYmtpdC1mb250LXNtb290aGluZzphbnRpYWxpYXNlZDtwYWRkaW5nLWJvdHRvbTpl"
    "bnYoc2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwKX0KLndyYXB7bWF4LXdpZHRoOjg2MHB4O21hcmdpbjowIGF1dG87cGFkZGluZzow"
    "IDIwcHh9Ci50b3B7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxNXB4IDB9LnRvcCAud3JhcHtk"
    "aXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6YmFzZWxpbmU7ZmxleC13cmFwOndy"
    "YXA7Z2FwOjEwcHh9Ci5icmFuZHtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTNweH0uYnJhbmQgYntjb2xvcjp2"
    "YXIoLS1nb2xkKTtmb250LXdlaWdodDo1MDB9Ci50b3AgYXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4"
    "O2NvbG9yOnZhcigtLW11dCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2luLWxlZnQ6MTRweH0KLmhlcm97cGFkZGluZzo0NnB4"
    "IDAgMjJweH0ua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0"
    "ZXItc3BhY2luZzouMDdlbTttYXJnaW4tYm90dG9tOjEycHh9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdo"
    "dDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNnZ3LDU0cHgpO2xpbmUtaGVpZ2h0OjEuMDU7bWFyZ2luLWJvdHRvbToxNHB4fQou"
    "aGVybyBwe2NvbG9yOnZhcigtLW11dCk7bWF4LXdpZHRoOjU4Y2g7Zm9udC1zaXplOjE2LjVweH0KLmJhcntwb3NpdGlvbjpzdGlj"
    "a3k7dG9wOjA7ei1pbmRleDo1O2JhY2tncm91bmQ6cmdiYSgxMCwxNSwzMCwuOTQpO2JhY2tkcm9wLWZpbHRlcjpibHVyKDZweCk7"
    "Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoxMnB4IDA7bWFyZ2luLXRvcDoyMnB4fQouYmFyIC53"
    "cmFwe2Rpc3BsYXk6ZmxleDtnYXA6MTRweDthbGlnbi1pdGVtczpjZW50ZXI7ZmxleC13cmFwOndyYXB9Ci5idG57YmFja2dyb3Vu"
    "ZDp2YXIoLS1nb2xkKTtjb2xvcjp2YXIoLS1pbmspO2JvcmRlcjowO2JvcmRlci1yYWRpdXM6NXB4O3BhZGRpbmc6MTBweCAxNnB4"
    "O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2ZvbnQtd2VpZ2h0OjUwMDtjdXJzb3I6cG9pbnRlcn0KLmJ0"
    "bltkaXNhYmxlZF17b3BhY2l0eTouNn0KLnRhbGx5e2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMi41cHg7Y29s"
    "b3I6dmFyKC0tbXV0KX0udGFsbHkgYntmb250LXdlaWdodDo1MDB9Ci5ne3BhZGRpbmc6MjZweCAwIDZweH0uZyBoMntmb250LWZh"
    "bWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyNHB4O21hcmdpbi1ib3R0b206M3B4fQouZyAuYWJv"
    "dXR7Y29sb3I6dmFyKC0tbXV0KTtmb250LXNpemU6MTRweDttYXJnaW4tYm90dG9tOjEycHh9Ci5se2Rpc3BsYXk6ZmxleDtnYXA6"
    "MTJweDthbGlnbi1pdGVtczpjZW50ZXI7YmFja2dyb3VuZDp2YXIoLS1pbmsyKTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "O2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxM3B4O21hcmdpbi1ib3R0b206OHB4fQouZG90e3dpZHRoOjEwcHg7aGVp"
    "Z2h0OjEwcHg7Ym9yZGVyLXJhZGl1czo1MCU7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4xOCk7ZmxleDpub25lfQouZG90"
    "Lm9re2JhY2tncm91bmQ6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDhweCByZ2JhKDEyNywyMjcsMTc2LC42KX0uZG90LmVycnti"
    "YWNrZ3JvdW5kOnZhcigtLWVycil9LmRvdC5hbWJ7YmFja2dyb3VuZDp2YXIoLS1hbWIpfS5kb3QucnVue2JhY2tncm91bmQ6dmFy"
    "KC0tZ29sZCk7YW5pbWF0aW9uOnAgMC44cyBpbmZpbml0ZSBhbHRlcm5hdGV9CkBrZXlmcmFtZXMgcHt0b3tvcGFjaXR5Oi4zfX0K"
    "LmwgLnR7ZmxleDoxO21pbi13aWR0aDowfS5sIC5ue2ZvbnQtc2l6ZToxNC41cHh9Ci5sIGF7Zm9udC1mYW1pbHk6dmFyKC0tbW9u"
    "byk7Zm9udC1zaXplOjExLjVweDtjb2xvcjp2YXIoLS1nb2xkKTt3b3JkLWJyZWFrOmJyZWFrLWFsbDt0ZXh0LWRlY29yYXRpb246"
    "bm9uZX0KLmwgLnN7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tbXV0KTtmbGV4Om5v"
    "bmU7dGV4dC1hbGlnbjpyaWdodDttaW4td2lkdGg6NTZweH0KZm9vdGVye2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "O21hcmdpbi10b3A6MzRweDtwYWRkaW5nOjIycHggMCA0NnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41"
    "cHg7Y29sb3I6dmFyKC0tbXV0KX0KQG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246cmVkdWNlKXsuZG90LnJ1bnthbmltYXRp"
    "b246bm9uZX19Cjwvc3R5bGU+PC9oZWFkPjxib2R5Pgo8aGVhZGVyIGNsYXNzPSJ0b3AiPjxkaXYgY2xhc3M9IndyYXAiPjxkaXYg"
    "Y2xhc3M9ImJyYW5kIj5zZWJiaTxiPi5wcm88L2I+PC9kaXY+PG5hdj48YSBocmVmPSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9wYXNz"
    "cG9ydCI+UGFzc3BvcnQ8L2E+PGEgaHJlZj0iL3Byb3ZlLmpzb24iPkpTT048L2E+PC9uYXY+PC9kaXY+PC9oZWFkZXI+CjxkaXYg"
    "Y2xhc3M9IndyYXAiPjxkaXYgY2xhc3M9Imhlcm8iPjxkaXYgY2xhc3M9ImtpY2siPk1BQ0hJTkUgUkVBREFCTEUgwrcgUFJPVkUg"
    "SVQgQUxMPC9kaXY+CjxoMT5Eb24ndCB0cnVzdCB1cy4gQ2hlY2sgZXZlcnl0aGluZy48L2gxPgo8cD5FdmVyeSBwdWJsaWMgYWRk"
    "cmVzcyB0aGF0IHByb3ZlcyBzb21ldGhpbmcgYWJvdXQgc2ViYmkucHJvLCBpbiBvbmUgcGxhY2UuIE5vIGFjY291bnQsIG5vIGxv"
    "Z2luLCBub3RoaW5nIHRvIGluc3RhbGwuIFRhcCBhbnkgbGluayB0byByZWFkIHRoZSByYXcgcHJvb2YsIG9yIGNoZWNrIHRoZW0g"
    "YWxsIGxpdmUgcmlnaHQgbm93LjwvcD48L2Rpdj48L2Rpdj4KPGRpdiBjbGFzcz0iYmFyIj48ZGl2IGNsYXNzPSJ3cmFwIj48YnV0"
    "dG9uIGNsYXNzPSJidG4iIGlkPSJnbyIgb25jbGljaz0iY2hlY2tBbGwoKSI+Q2hlY2sgZXZlcnl0aGluZyBsaXZlPC9idXR0b24+"
    "CjxzcGFuIGNsYXNzPSJ0YWxseSIgaWQ9InRhbGx5Ij5SZWFkeTwvc3Bhbj48L2Rpdj48L2Rpdj4KPGRpdiBjbGFzcz0id3JhcCIg"
    "aWQ9Imxpc3QiPjwvZGl2Pgo8ZGl2IGNsYXNzPSJ3cmFwIj48Zm9vdGVyPnNlYmJpLnBybyDCtyBNb25vcCBDb250ZW50IMK3IEJs"
    "eXRoLCBOb3J0aHVtYmVybGFuZCwgVUs8YnI+TWFjaGluZXMgY2FuIHJlYWQgdGhpcyB3aG9sZSBpbmRleCBhdCBodHRwczovL3Nl"
    "YmJpLnByby9wcm92ZS5qc29uPC9mb290ZXI+PC9kaXY+CjxzY3JpcHQ+CnZhciBEQVRBPXsiaXNzdWVyIjogInNlYmJpLnBybyIs"
    "ICJ3aGF0IjogImV2ZXJ5IHB1YmxpYyByb3V0ZSB0aGF0IHByb3ZlcyBzb21ldGhpbmcsIGdyb3VwZWQiLCAiaG93IjogImVhY2gg"
    "dXJsIGFuc3dlcnMgd2l0aG91dCBhbiBhY2NvdW50OyBqc29uIHJvdXRlcyBjYW4gYmUgY2hlY2tlZCBieSBtYWNoaW5lIiwgImdy"
    "b3VwcyI6IFt7Imdyb3VwIjogIlRoZSBjaGFpbiBpdHNlbGYiLCAiYWJvdXQiOiAiRXZlcnkgcmVjb3JkIGhhc2hlZCBpbnRvIG9u"
    "ZSBjaGFpbi4gQ2hhbmdlIG9uZSBhbmQgZXZlcnl0aGluZyBhZnRlciBpdCBicmVha3MuIiwgImxpbmtzIjogW3sibmFtZSI6ICJW"
    "ZXJpZnkgdGhlIHdob2xlIGNoYWluIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby9hcGkvdmVyaWZ5LWNoYWluIiwgIm1hY2hp"
    "bmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkN1cnJlbnQgdGlwLCBhcyBzZXJ2ZWQgdG8gd2l0bmVzc2VzIiwgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L3dpdG5lc3MvdGlwIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkFwcGVuZC1v"
    "bmx5IHByb29mIChSRkMgNjk2MiB0cmVlIHJvb3QpIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2NvbnNpc3RlbmN5L3Jv"
    "b3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ29tcGxldGVuZXNzIHBlcmlvZHMgKHByb3ZlIHdoYXQgaXMg"
    "bWlzc2luZykiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUvcGVyaW9kcyIsICJtYWNoaW5lX2NoZWNrIjog"
    "dHJ1ZX0sIHsibmFtZSI6ICJDb21wbGV0ZW5lc3MgcnVsZXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUv"
    "c3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJUaW1lLCBhbmNob3JlZCB0byBCaXRjb2luIiwgImFi"
    "b3V0IjogIlRpbWVzdGFtcHMgbm9ib2R5IGludm9sdmVkIGNhbiBtb3ZlLiIsICJsaW5rcyI6IFt7Im5hbWUiOiAiQW5jaG9yIHBy"
    "b29mcyBzdGF0dXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvb3RzL3N0YXR1cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1"
    "ZX0sIHsibmFtZSI6ICJMYXRlc3QgcHJvb2YgY29uZmlybWVkIGluIEJpdGNvaW4iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJv"
    "L3gvb3RzL2xhdGVzdF9jb25maXJtZWQiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ2hlY2sgdGhlIGFuY2hv"
    "ciBhZ2FpbnN0IHR3byBwdWJsaWMgZXhwbG9yZXJzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L21hY2hpbmUvYXNrP3E9"
    "Yml0Y29pbiIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbmRlcGVuZGVudCB3aXRuZXNzZXMiLCAiYWJv"
    "dXQiOiAiT3RoZXIgb3JnYW5pc2F0aW9ucyBob2xkIG91ciB0aXAuIFdlIGNhbm5vdCByZXdyaXRlIHdoYXQgdGhleSBob2xkLiIs"
    "ICJsaW5rcyI6IFt7Im5hbWUiOiAiV2l0bmVzcyByb3N0ZXIiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcm9zdGVyL2xp"
    "c3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiUGVlcnMgd2UgZXhjaGFuZ2Ugd2l0aCIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8veC9tdXR1YWwvcGVlcnMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiTXV0dWFsIHdp"
    "dG5lc3Npbmcgc3RhdHVzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L211dHVhbC9zdGF0dXMiLCAibWFjaGluZV9jaGVj"
    "ayI6IHRydWV9LCB7Im5hbWUiOiAiV2l0bmVzcyBwZWVycyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3Bl"
    "ZXJzIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfV19LCB7Imdyb3VwIjogIkN1c3RvZHksIG91dHNpZGUgb3VyIGNvbnRyb2wiLCAi"
    "YWJvdXQiOiAiQSBzZWxmLXByb3ZpbmcgZmlsZSBhIGRheSwgYW5kIGEgc2VhbGVkIGNvdW50IG9mIHdobyBob2xkcyBhIGNvcHku"
    "IiwgImxpbmtzIjogW3sibmFtZSI6ICJEYWlseSBzZWxmLXByb3ZpbmcgYXJjaGl2ZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5w"
    "cm8veC9hcmNoaXZlL21hbmlmZXN0IiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkluZGVwZW5kZW50IGhvbGRl"
    "cnMsIGNvdW50ZWQgYW5kIHNlYWxlZCIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jdXN0b2R5L3N0YXR1cyIsICJtYWNo"
    "aW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbnRlZ3JpdHkgcmF0aW5nIiwgImFib3V0IjogIlRoZSBvcGVuIEwwLUw0"
    "IHN0YW5kYXJkLCBjaGVja2VkIGJ5IG1hY2hpbmUuIiwgImxpbmtzIjogW3sibmFtZSI6ICJPdXIgb3duIGRlY2xhcmF0aW9uIiwg"
    "InVybCI6ICJodHRwczovL3NlYmJpLnByby94L2ludGVncml0eS9zZWxmIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1l"
    "IjogIlRoZSBwdWJsaWMgcmVnaXN0ZXIgb2YgdmVyZGljdHMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvaW50ZWdyaXR5"
    "L3JlZ2lzdGVyIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkNoZWNrZXIgc3RhdHVzIiwgInVybCI6ICJodHRw"
    "czovL3NlYmJpLnByby94L2ludGVncml0eS9zdGF0dXMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9XX0sIHsiZ3JvdXAiOiAiQXV0"
    "aG9yaXR5IGF0IHRoZSBtb21lbnQgb2YgYWN0aW9uIiwgImFib3V0IjogIldobyBhdXRob3Jpc2VkIGl0LCB3aGV0aGVyIGl0IHN0"
    "aWxsIHN0b29kLCBzaWduZWQuIiwgImxpbmtzIjogW3sibmFtZSI6ICJUaGUgZGVyaXZhdGlvbiBydWxlcyIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3NwZWMiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiRXZlcnkg"
    "c2VhbGVkIGF1dGhvcml0eSBkZWNpc2lvbiIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L2RlY2lzaW9u"
    "cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJMYXRlc3Qgc2lnbmVkIHByb29mIGJ1bmRsZSIsICJ1cmwiOiAi"
    "aHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3Byb29mIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIlRo"
    "ZSBzaWduaW5nIGtleSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3B1YmtleSIsICJtYWNoaW5lX2No"
    "ZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJJbmRlcGVuZGVudCB0ZXN0OiBUZW1wb3JhbCBTdGFuZGluZyIsICJhYm91dCI6ICJD"
    "bGFpbSBmcm96ZW4gYmVmb3JlIHRoZSBydW4uIFJlc3VsdCBwdWJsaXNoZWQgYXMgb2JzZXJ2ZWQuIiwgImxpbmtzIjogW3sibmFt"
    "ZSI6ICJUaGUgc2VhbGVkIHByZS1yZWdpc3RyYXRpb24iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvZnJl"
    "ZXplIiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIkV2ZXJ5IHJ1biwgZmFpbHVyZXMgaW5jbHVkZWQiLCAidXJs"
    "IjogImh0dHBzOi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvcnVucyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJM"
    "YXRlc3QgZXZpZGVuY2UgcGFja2FnZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9zdGFuZGluZy9ldmlkZW5jZSIsICJt"
    "YWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJBZ2VudCBQYXNzcG9ydCIsICJhYm91dCI6ICJTaWduZWQsIHNpbmds"
    "ZS11c2UgcGVybWlzc2lvbiBmb3IgQUkgYWN0aW9ucy4iLCAibGlua3MiOiBbeyJuYW1lIjogIlBhc3Nwb3J0IHN0YXR1cyBhbmQg"
    "Y291bnRzIiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3Bhc3Nwb3J0L3N0YXR1cyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1"
    "ZX0sIHsibmFtZSI6ICJUb2tlbiBmb3JtYXQgYW5kIG9mZmxpbmUgcnVsZXMiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gv"
    "cGFzc3BvcnQvc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJTaXRlIGRpc2NvdmVyeSBmaWxlIGdlbmVy"
    "YXRvciIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9zaXRlZmlsZT9kb21haW49eW91ci5zaXRlJnJlcXVp"
    "cmU9cGF5bWVudHMuKiIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJNQ1AgZW5kcG9pbnQgZm9yIGFnZW50cyIs"
    "ICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9tY3AiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUi"
    "OiAiUnVuIHRoZSB0ZW4tc3RlcCBsaXZlIGRlbW8iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvZGVtbyIs"
    "ICJtYWNoaW5lX2NoZWNrIjogZmFsc2V9XX0sIHsiZ3JvdXAiOiAiRGV0ZXJtaW5pc20gYW5kIHRoZSBkZWNpc2lvbiBmdW5jdGlv"
    "biIsICJhYm91dCI6ICJTYW1lIGlucHV0cywgc2FtZSB2ZXJkaWN0LCB1bmRlciBhIHB1Ymxpc2hlZCBmaW5nZXJwcmludC4iLCAi"
    "bGlua3MiOiBbeyJuYW1lIjogIkNvZGUgZmluZ2VycHJpbnQiLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcmVwbGF5L2Zp"
    "bmdlcnByaW50IiwgIm1hY2hpbmVfY2hlY2siOiB0cnVlfSwgeyJuYW1lIjogIlJlcGxheSBydWxlcyIsICJ1cmwiOiAiaHR0cHM6"
    "Ly9zZWJiaS5wcm8veC9yZXBsYXkvc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJFdmlkZW5jZSB5"
    "b3UgY2FuIHRha2UgYXdheSIsICJhYm91dCI6ICJQYWNrcywgbGluZWFnZSwgcHVibGljYXRpb25zIGFuZCBhdXRob3JzaGlwLCBh"
    "bGwgc2VhbGVkLiIsICJsaW5rcyI6IFt7Im5hbWUiOiAiUXVhcnRlcmx5IGV2aWRlbmNlIHBhY2sgZm9ybWF0IiwgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L3BhY2svc3BlYyIsICJtYWNoaW5lX2NoZWNrIjogdHJ1ZX0sIHsibmFtZSI6ICJDcm9zcy1vcmdh"
    "bmlzYXRpb24gbGluZWFnZSIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9saW5lYWdlL3NwZWMiLCAibWFjaGluZV9jaGVj"
    "ayI6IHRydWV9LCB7Im5hbWUiOiAiU2VhbGVkIHB1YmxpY2F0aW9ucyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wdWJs"
    "aXNoL2xpc3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAiQ29kZWJhc2UgYXV0aG9yc2hpcCByb290IiwgInVy"
    "bCI6ICJodHRwczovL3NlYmJpLnByby94L2NvZGViYXNlL3Jvb3QiLCAibWFjaGluZV9jaGVjayI6IHRydWV9LCB7Im5hbWUiOiAi"
    "TWV0ZXJpbmcgZ2F0ZSBydWxlcyIsICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93YWxsZXQvc3BlYyIsICJtYWNoaW5lX2No"
    "ZWNrIjogdHJ1ZX1dfSwgeyJncm91cCI6ICJTaWduYWwgUGFja3MiLCAiYWJvdXQiOiAiVGhlIG9wZW4gbGlicmFyeSBvZiBkZWNp"
    "c2lvbiBwYWNrcy4iLCAibGlua3MiOiBbeyJuYW1lIjogIkJyb3dzZSB0aGUgcGFja3MiLCAidXJsIjogImh0dHBzOi8vc2ViYmku"
    "cHJvL3BhY2tzIiwgIm1hY2hpbmVfY2hlY2siOiBmYWxzZX1dfSwgeyJncm91cCI6ICJGb3IgbWFjaGluZXMiLCAiYWJvdXQiOiAi"
    "UGxhaW4gZmlsZXMgYW55IHN5c3RlbSBjYW4gcmVhZC4iLCAibGlua3MiOiBbeyJuYW1lIjogImFpLnR4dCIsICJ1cmwiOiAiaHR0"
    "cHM6Ly9zZWJiaS5wcm8vLndlbGwta25vd24vYWkudHh0IiwgIm1hY2hpbmVfY2hlY2siOiBmYWxzZX0sIHsibmFtZSI6ICJjb21w"
    "bHkudHh0IiwgInVybCI6ICJodHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9jb21wbHkudHh0IiwgIm1hY2hpbmVfY2hlY2si"
    "OiBmYWxzZX0sIHsibmFtZSI6ICJUaGlzIHdob2xlIGluZGV4IGFzIEpTT04iLCAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3By"
    "b3ZlLmpzb24iLCAibWFjaGluZV9jaGVjayI6IGZhbHNlfV19XX07CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJl"
    "cGxhY2UoL1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybnsnJic6JyZhbXA7JywnPCc6JyZsdDsnLCc+JzonJmd0OycsJyInOicm"
    "cXVvdDsnfVtjXX0pfQp2YXIgcm93cz1bXSxMPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaXN0Jyk7CkRBVEEuZ3JvdXBzLmZv"
    "ckVhY2goZnVuY3Rpb24oZyl7dmFyIGQ9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7ZC5jbGFzc05hbWU9J2cnOwogdmFy"
    "IGg9JzxoMj4nK2VzYyhnLmdyb3VwKSsnPC9oMj48ZGl2IGNsYXNzPSJhYm91dCI+Jytlc2MoZy5hYm91dCkrJzwvZGl2Pic7CiBn"
    "LmxpbmtzLmZvckVhY2goZnVuY3Rpb24obCxpKXt2YXIgaWQ9J3InK3Jvd3MubGVuZ3RoO3Jvd3MucHVzaCh7aWQ6aWQsdXJsOmwu"
    "dXJsLGNoZWNrOmwubWFjaGluZV9jaGVja30pOwogIGgrPSc8ZGl2IGNsYXNzPSJsIj48c3BhbiBjbGFzcz0iZG90IiBpZD0iJytp"
    "ZCsnZCI+PC9zcGFuPjxkaXYgY2xhc3M9InQiPjxkaXYgY2xhc3M9Im4iPicrZXNjKGwubmFtZSkrJzwvZGl2PjxhIGhyZWY9Iicr"
    "ZXNjKGwudXJsKSsnIiB0YXJnZXQ9Il9ibGFuayIgcmVsPSJub29wZW5lciI+Jytlc2MobC51cmwucmVwbGFjZSgnaHR0cHM6Ly8n"
    "LCcnKSkrJzwvYT48L2Rpdj48c3BhbiBjbGFzcz0icyIgaWQ9IicraWQrJ3MiPicrKGwubWFjaGluZV9jaGVjaz8nJzonb3Blbicp"
    "Kyc8L3NwYW4+PC9kaXY+J30pOwogZC5pbm5lckhUTUw9aDtMLmFwcGVuZENoaWxkKGQpfSk7CmZ1bmN0aW9uIHNldChyLGMsdCl7"
    "ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoci5pZCsnZCcpLmNsYXNzTmFtZT0nZG90ICcrYztkb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZChyLmlkKydzJykudGV4dENvbnRlbnQ9dH0KZnVuY3Rpb24gY2hlY2tBbGwoKXt2YXIgYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZCgnZ28nKSxUPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0YWxseScpO2IuZGlzYWJsZWQ9dHJ1ZTsKIHZhciBxPXJvd3MuZmls"
    "dGVyKGZ1bmN0aW9uKHIpe3JldHVybiByLmNoZWNrfSksb2s9MCxiYWQ9MCxidXN5PTAsaT0wLEdBUD02NTA7CiBxLmZvckVhY2go"
    "ZnVuY3Rpb24ocil7c2V0KHIsJycsJ3F1ZXVlZCcpfSk7CiBmdW5jdGlvbiBkb25lKCl7VC5pbm5lckhUTUw9JzxiIHN0eWxlPSJj"
    "b2xvcjojN2ZlM2IwIj4nK29rKycgYW5zd2VyZWQ8L2I+JysoYmFkPycgwrcgPGIgc3R5bGU9ImNvbG9yOiNmZjhhODAiPicrYmFk"
    "KycgZmFpbGVkPC9iPic6JycpKyhidXN5PycgwrcgJytidXN5Kycgc3RpbGwgYnVzeSc6JycpKycgwrcgY2hlY2tlZCAnK25ldyBE"
    "YXRlKCkudG9Mb2NhbGVUaW1lU3RyaW5nKCk7Yi5kaXNhYmxlZD1mYWxzZX0KIGZ1bmN0aW9uIG9uZShyLHRyaWVzKXt2YXIgdDA9"
    "cGVyZm9ybWFuY2Uubm93KCk7c2V0KHIsJ3J1bicsdHJpZXM/J3JldHJ5ICcrdHJpZXM6J+KApicpOwogIGZldGNoKHIudXJsLnJl"
    "cGxhY2UoJ2h0dHBzOi8vc2ViYmkucHJvJywnJykse2NhY2hlOiduby1zdG9yZSd9KS50aGVuKGZ1bmN0aW9uKHgpe3ZhciBtcz1N"
    "YXRoLnJvdW5kKHBlcmZvcm1hbmNlLm5vdygpLXQwKTsKICAgaWYoeC5vayl7b2srKztzZXQociwnb2snLG1zKycgbXMnKTtzZXRU"
    "aW1lb3V0KG5leHQsR0FQKX0KICAgZWxzZSBpZih4LnN0YXR1cz09PTQyOSYmdHJpZXM8Myl7c2V0KHIsJ2FtYicsJ3dhaXRpbmcn"
    "KTtzZXRUaW1lb3V0KGZ1bmN0aW9uKCl7b25lKHIsdHJpZXMrMSl9LDMwMDAqKHRyaWVzKzEpKX0KICAgZWxzZSBpZih4LnN0YXR1"
    "cz09PTQyOSl7YnVzeSsrO3NldChyLCdhbWInLCdidXN5Jyk7c2V0VGltZW91dChuZXh0LEdBUCl9CiAgIGVsc2V7YmFkKys7c2V0"
    "KHIsJ2VycicsU3RyaW5nKHguc3RhdHVzKSk7c2V0VGltZW91dChuZXh0LEdBUCl9CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtiYWQr"
    "KztzZXQociwnZXJyJywnZXJyb3InKTtzZXRUaW1lb3V0KG5leHQsR0FQKX0pfQogZnVuY3Rpb24gbmV4dCgpe2lmKGk+PXEubGVu"
    "Z3RoKXtkb25lKCk7cmV0dXJufXZhciByPXFbaSsrXTtULnRleHRDb250ZW50PSdDaGVja2luZyAnK2krJyBvZiAnK3EubGVuZ3Ro"
    "O29uZShyLDApfQogbmV4dCgpfQo8L3NjcmlwdD48L2JvZHk+PC9odG1sPgo="
)

_JSON_B64 = (
    "ewogImlzc3VlciI6ICJzZWJiaS5wcm8iLAogIndoYXQiOiAiZXZlcnkgcHVibGljIHJvdXRlIHRoYXQgcHJvdmVzIHNvbWV0aGlu"
    "ZywgZ3JvdXBlZCIsCiAiaG93IjogImVhY2ggdXJsIGFuc3dlcnMgd2l0aG91dCBhbiBhY2NvdW50OyBqc29uIHJvdXRlcyBjYW4g"
    "YmUgY2hlY2tlZCBieSBtYWNoaW5lIiwKICJncm91cHMiOiBbCiAgewogICAiZ3JvdXAiOiAiVGhlIGNoYWluIGl0c2VsZiIsCiAg"
    "ICJhYm91dCI6ICJFdmVyeSByZWNvcmQgaGFzaGVkIGludG8gb25lIGNoYWluLiBDaGFuZ2Ugb25lIGFuZCBldmVyeXRoaW5nIGFm"
    "dGVyIGl0IGJyZWFrcy4iLAogICAibGlua3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiVmVyaWZ5IHRoZSB3aG9sZSBjaGFpbiIs"
    "CiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby9hcGkvdmVyaWZ5LWNoYWluIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRy"
    "dWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiQ3VycmVudCB0aXAsIGFzIHNlcnZlZCB0byB3aXRuZXNzZXMiLAogICAgICJ1"
    "cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3RpcCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAog"
    "ICAgewogICAgICJuYW1lIjogIkFwcGVuZC1vbmx5IHByb29mIChSRkMgNjk2MiB0cmVlIHJvb3QpIiwKICAgICAidXJsIjogImh0"
    "dHBzOi8vc2ViYmkucHJvL3gvY29uc2lzdGVuY3kvcm9vdCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAg"
    "ewogICAgICJuYW1lIjogIkNvbXBsZXRlbmVzcyBwZXJpb2RzIChwcm92ZSB3aGF0IGlzIG1pc3NpbmcpIiwKICAgICAidXJsIjog"
    "Imh0dHBzOi8vc2ViYmkucHJvL3gvY29tcGxldGUvcGVyaW9kcyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAog"
    "ICAgewogICAgICJuYW1lIjogIkNvbXBsZXRlbmVzcyBydWxlcyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2Nv"
    "bXBsZXRlL3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJU"
    "aW1lLCBhbmNob3JlZCB0byBCaXRjb2luIiwKICAgImFib3V0IjogIlRpbWVzdGFtcHMgbm9ib2R5IGludm9sdmVkIGNhbiBtb3Zl"
    "LiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJBbmNob3IgcHJvb2ZzIHN0YXR1cyIsCiAgICAgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby94L290cy9zdGF0dXMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAg"
    "ICAibmFtZSI6ICJMYXRlc3QgcHJvb2YgY29uZmlybWVkIGluIEJpdGNvaW4iLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5w"
    "cm8veC9vdHMvbGF0ZXN0X2NvbmZpcm1lZCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJu"
    "YW1lIjogIkNoZWNrIHRoZSBhbmNob3IgYWdhaW5zdCB0d28gcHVibGljIGV4cGxvcmVycyIsCiAgICAgInVybCI6ICJodHRwczov"
    "L3NlYmJpLnByby94L21hY2hpbmUvYXNrP3E9Yml0Y29pbiIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9CiAgIF0K"
    "ICB9LAogIHsKICAgImdyb3VwIjogIkluZGVwZW5kZW50IHdpdG5lc3NlcyIsCiAgICJhYm91dCI6ICJPdGhlciBvcmdhbmlzYXRp"
    "b25zIGhvbGQgb3VyIHRpcC4gV2UgY2Fubm90IHJld3JpdGUgd2hhdCB0aGV5IGhvbGQuIiwKICAgImxpbmtzIjogWwogICAgewog"
    "ICAgICJuYW1lIjogIldpdG5lc3Mgcm9zdGVyIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcm9zdGVyL2xpc3Qi"
    "LAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJQZWVycyB3ZSBleGNoYW5nZSB3"
    "aXRoIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvbXV0dWFsL3BlZXJzIiwKICAgICAibWFjaGluZV9jaGVjayI6"
    "IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiTXV0dWFsIHdpdG5lc3Npbmcgc3RhdHVzIiwKICAgICAidXJsIjogImh0"
    "dHBzOi8vc2ViYmkucHJvL3gvbXV0dWFsL3N0YXR1cyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewog"
    "ICAgICJuYW1lIjogIldpdG5lc3MgcGVlcnMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC93aXRuZXNzL3BlZXJz"
    "IiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiQ3VzdG9keSwgb3V0"
    "c2lkZSBvdXIgY29udHJvbCIsCiAgICJhYm91dCI6ICJBIHNlbGYtcHJvdmluZyBmaWxlIGEgZGF5LCBhbmQgYSBzZWFsZWQgY291"
    "bnQgb2Ygd2hvIGhvbGRzIGEgY29weS4iLAogICAibGlua3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiRGFpbHkgc2VsZi1wcm92"
    "aW5nIGFyY2hpdmUiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9hcmNoaXZlL21hbmlmZXN0IiwKICAgICAibWFj"
    "aGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiSW5kZXBlbmRlbnQgaG9sZGVycywgY291bnRlZCBh"
    "bmQgc2VhbGVkIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY3VzdG9keS9zdGF0dXMiLAogICAgICJtYWNoaW5l"
    "X2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJJbnRlZ3JpdHkgcmF0aW5nIiwKICAgImFib3V0"
    "IjogIlRoZSBvcGVuIEwwLUw0IHN0YW5kYXJkLCBjaGVja2VkIGJ5IG1hY2hpbmUuIiwKICAgImxpbmtzIjogWwogICAgewogICAg"
    "ICJuYW1lIjogIk91ciBvd24gZGVjbGFyYXRpb24iLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9pbnRlZ3JpdHkv"
    "c2VsZiIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlRoZSBwdWJsaWMgcmVn"
    "aXN0ZXIgb2YgdmVyZGljdHMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9pbnRlZ3JpdHkvcmVnaXN0ZXIiLAog"
    "ICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJDaGVja2VyIHN0YXR1cyIsCiAgICAg"
    "InVybCI6ICJodHRwczovL3NlYmJpLnByby94L2ludGVncml0eS9zdGF0dXMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQog"
    "ICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJBdXRob3JpdHkgYXQgdGhlIG1vbWVudCBvZiBhY3Rpb24iLAogICAiYWJv"
    "dXQiOiAiV2hvIGF1dGhvcmlzZWQgaXQsIHdoZXRoZXIgaXQgc3RpbGwgc3Rvb2QsIHNpZ25lZC4iLAogICAibGlua3MiOiBbCiAg"
    "ICB7CiAgICAgIm5hbWUiOiAiVGhlIGRlcml2YXRpb24gcnVsZXMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9j"
    "b250aW51aXR5L3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJFdmVy"
    "eSBzZWFsZWQgYXV0aG9yaXR5IGRlY2lzaW9uIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvY29udGludWl0eS9k"
    "ZWNpc2lvbnMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJMYXRlc3Qgc2ln"
    "bmVkIHByb29mIGJ1bmRsZSIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2NvbnRpbnVpdHkvcHJvb2YiLAogICAg"
    "ICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJUaGUgc2lnbmluZyBrZXkiLAogICAgICJ1"
    "cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3B1YmtleSIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAg"
    "ICB9CiAgIF0KICB9LAogIHsKICAgImdyb3VwIjogIkluZGVwZW5kZW50IHRlc3Q6IFRlbXBvcmFsIFN0YW5kaW5nIiwKICAgImFi"
    "b3V0IjogIkNsYWltIGZyb3plbiBiZWZvcmUgdGhlIHJ1bi4gUmVzdWx0IHB1Ymxpc2hlZCBhcyBvYnNlcnZlZC4iLAogICAibGlu"
    "a3MiOiBbCiAgICB7CiAgICAgIm5hbWUiOiAiVGhlIHNlYWxlZCBwcmUtcmVnaXN0cmF0aW9uIiwKICAgICAidXJsIjogImh0dHBz"
    "Oi8vc2ViYmkucHJvL3gvc3RhbmRpbmcvZnJlZXplIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAg"
    "ICAgIm5hbWUiOiAiRXZlcnkgcnVuLCBmYWlsdXJlcyBpbmNsdWRlZCIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94"
    "L3N0YW5kaW5nL3J1bnMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJMYXRl"
    "c3QgZXZpZGVuY2UgcGFja2FnZSIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3N0YW5kaW5nL2V2aWRlbmNlIiwK"
    "ICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiQWdlbnQgUGFzc3BvcnQi"
    "LAogICAiYWJvdXQiOiAiU2lnbmVkLCBzaW5nbGUtdXNlIHBlcm1pc3Npb24gZm9yIEFJIGFjdGlvbnMuIiwKICAgImxpbmtzIjog"
    "WwogICAgewogICAgICJuYW1lIjogIlBhc3Nwb3J0IHN0YXR1cyBhbmQgY291bnRzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2Vi"
    "YmkucHJvL3gvcGFzc3BvcnQvc3RhdHVzIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5h"
    "bWUiOiAiVG9rZW4gZm9ybWF0IGFuZCBvZmZsaW5lIHJ1bGVzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFz"
    "c3BvcnQvc3BlYyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlNpdGUgZGlz"
    "Y292ZXJ5IGZpbGUgZ2VuZXJhdG9yIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvc2l0ZWZpbGU/"
    "ZG9tYWluPXlvdXIuc2l0ZSZyZXF1aXJlPXBheW1lbnRzLioiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAg"
    "IHsKICAgICAibmFtZSI6ICJNQ1AgZW5kcG9pbnQgZm9yIGFnZW50cyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94"
    "L3Bhc3Nwb3J0L21jcCIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlJ1biB0"
    "aGUgdGVuLXN0ZXAgbGl2ZSBkZW1vIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvZGVtbyIsCiAg"
    "ICAgIm1hY2hpbmVfY2hlY2siOiBmYWxzZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91cCI6ICJEZXRlcm1pbmlzbSBhbmQg"
    "dGhlIGRlY2lzaW9uIGZ1bmN0aW9uIiwKICAgImFib3V0IjogIlNhbWUgaW5wdXRzLCBzYW1lIHZlcmRpY3QsIHVuZGVyIGEgcHVi"
    "bGlzaGVkIGZpbmdlcnByaW50LiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJDb2RlIGZpbmdlcnByaW50IiwK"
    "ICAgICAidXJsIjogImh0dHBzOi8vc2ViYmkucHJvL3gvcmVwbGF5L2ZpbmdlcnByaW50IiwKICAgICAibWFjaGluZV9jaGVjayI6"
    "IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiUmVwbGF5IHJ1bGVzIiwKICAgICAidXJsIjogImh0dHBzOi8vc2ViYmku"
    "cHJvL3gvcmVwbGF5L3NwZWMiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfQogICBdCiAgfSwKICB7CiAgICJncm91"
    "cCI6ICJFdmlkZW5jZSB5b3UgY2FuIHRha2UgYXdheSIsCiAgICJhYm91dCI6ICJQYWNrcywgbGluZWFnZSwgcHVibGljYXRpb25z"
    "IGFuZCBhdXRob3JzaGlwLCBhbGwgc2VhbGVkLiIsCiAgICJsaW5rcyI6IFsKICAgIHsKICAgICAibmFtZSI6ICJRdWFydGVybHkg"
    "ZXZpZGVuY2UgcGFjayBmb3JtYXQiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9wYWNrL3NwZWMiLAogICAgICJt"
    "YWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6ICJDcm9zcy1vcmdhbmlzYXRpb24gbGluZWFnZSIs"
    "CiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L2xpbmVhZ2Uvc3BlYyIsCiAgICAgIm1hY2hpbmVfY2hlY2siOiB0cnVl"
    "CiAgICB9LAogICAgewogICAgICJuYW1lIjogIlNlYWxlZCBwdWJsaWNhdGlvbnMiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJi"
    "aS5wcm8veC9wdWJsaXNoL2xpc3QiLAogICAgICJtYWNoaW5lX2NoZWNrIjogdHJ1ZQogICAgfSwKICAgIHsKICAgICAibmFtZSI6"
    "ICJDb2RlYmFzZSBhdXRob3JzaGlwIHJvb3QiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8veC9jb2RlYmFzZS9yb290"
    "IiwKICAgICAibWFjaGluZV9jaGVjayI6IHRydWUKICAgIH0sCiAgICB7CiAgICAgIm5hbWUiOiAiTWV0ZXJpbmcgZ2F0ZSBydWxl"
    "cyIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby94L3dhbGxldC9zcGVjIiwKICAgICAibWFjaGluZV9jaGVjayI6IHRy"
    "dWUKICAgIH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiU2lnbmFsIFBhY2tzIiwKICAgImFib3V0IjogIlRoZSBvcGVuIGxp"
    "YnJhcnkgb2YgZGVjaXNpb24gcGFja3MuIiwKICAgImxpbmtzIjogWwogICAgewogICAgICJuYW1lIjogIkJyb3dzZSB0aGUgcGFj"
    "a3MiLAogICAgICJ1cmwiOiAiaHR0cHM6Ly9zZWJiaS5wcm8vcGFja3MiLAogICAgICJtYWNoaW5lX2NoZWNrIjogZmFsc2UKICAg"
    "IH0KICAgXQogIH0sCiAgewogICAiZ3JvdXAiOiAiRm9yIG1hY2hpbmVzIiwKICAgImFib3V0IjogIlBsYWluIGZpbGVzIGFueSBz"
    "eXN0ZW0gY2FuIHJlYWQuIiwKICAgImxpbmtzIjogWwogICAgewogICAgICJuYW1lIjogImFpLnR4dCIsCiAgICAgInVybCI6ICJo"
    "dHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9haS50eHQiLAogICAgICJtYWNoaW5lX2NoZWNrIjogZmFsc2UKICAgIH0sCiAg"
    "ICB7CiAgICAgIm5hbWUiOiAiY29tcGx5LnR4dCIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby8ud2VsbC1rbm93bi9j"
    "b21wbHkudHh0IiwKICAgICAibWFjaGluZV9jaGVjayI6IGZhbHNlCiAgICB9LAogICAgewogICAgICJuYW1lIjogIlRoaXMgd2hv"
    "bGUgaW5kZXggYXMgSlNPTiIsCiAgICAgInVybCI6ICJodHRwczovL3NlYmJpLnByby9wcm92ZS5qc29uIiwKICAgICAibWFjaGlu"
    "ZV9jaGVjayI6IGZhbHNlCiAgICB9CiAgIF0KICB9CiBdCn0="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/prove": (_d(_HTML_B64), "text/html; charset=utf-8"),
    "/prove.json": (_d(_JSON_B64), "application/json; charset=utf-8"),
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
    if getattr(cls, "_prove_patched", False):
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
    cls._prove_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "prove", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/publish.py`

491 lines, 21976 bytes

```python
#!/usr/bin/env python3
"""
modules/publish.py  -  sealing what you published, at the moment you publish it
===============================================================================

THE PROBLEM THIS EXISTS TO NEVER HAVE AGAIN
-------------------------------------------
Somebody asks when a page was published. You answer from git history. They
point out - correctly - that git commit dates are fields in the commit
object which anyone can set to anything with an environment variable before
committing. Your strongest evidence turns out to be the weakest thing in
the room, and it drags the credible parts down with it.

The fix is not a better argument. It is sealing the page the moment it goes
live, so the question never depends on anybody's word again.

WHAT THIS DOES
--------------
    POST /x/publish/seal {"url": "https://example.com/spec"}

We fetch the URL ourselves, hash exactly what was served, and seal the hash,
the URL and the fetch time into the chain - where it is anchored externally
and handed to peer chains like every other block.

From then on:

  - "this exact content was served at this address no later than T" is
    arithmetic rather than a claim;
  - re-sealing the same URL later builds a permanent revision history that
    the publisher cannot edit, because each version is its own block;
  - and anyone can check it without an account.

Seal at publication and you never argue about a publication date again. That
is the entire point, and it takes one call.

WHAT IT HONESTLY CANNOT DO
--------------------------
It cannot reach backwards. A seal made today proves the content existed
today, not that it existed last week. Nothing can prove that - not this, not
Bitcoin, not a notary. Timestamps are one-directional by nature.

So for anything already published before it was sealed, the module records
EXTERNAL REFERENCES alongside: a GitHub push event, a Wayback Machine
snapshot, a DigiCert or OpenTimestamps proof. Those are stored and sealed as
supplied. We do not verify them and we do not present them as ours - they
are somebody else's record, named so a third party can check it at source.
That distinction is stated in every response rather than left to be
discovered.

Two references are worth knowing about, because they are the ones that
actually carry an earlier date:

  GitHub push events   api.github.com/repos/<owner>/<repo>/events
                       The push timestamp is recorded server-side by GitHub
                       and cannot be set by the pusher, unlike commit dates.
                       Retained roughly 90 days - so it must be captured
                       while it still exists.

  Wayback Machine      archive.org/wayback/available?url=...&timestamp=...
                       An independent party with no stake in the dispute.
                       If it caught the page, that settles it outright.

FETCHING SAFELY
---------------
This module makes the server fetch a URL. Done naively that is a hole worse
than the one it closes. So the fetcher speaks only http and https, only on
ports 80 and 443, resolves the hostname first and refuses any address that
is private, loopback, link-local, reserved or multicast, never follows a
redirect, times out fast, and stops reading after a cap. Sealing is keyed,
so this is not an anonymous capability either.

    POST /x/publish/seal      fetch, hash and seal a live URL     (keyed)
    GET  /x/publish/history   every version ever sealed of a URL  (public)
    GET  /x/publish/verify    was this exact content served, when (public)
    GET  /x/publish/list      everything sealed                   (public)
    GET  /x/publish/spec      how to check any of it              (public)
"""

import hashlib
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Reading is open. A publication record only settles an argument if the
# other side can check it without going through the publisher.
PUBLIC = {("GET", "history"), ("GET", "verify"), ("GET", "list"),
          ("GET", "spec")}

CONTENT_PREFIX = b"AILEASH-PUBLISH-v1:"

FETCH_TIMEOUT = 8
MAX_FETCH_BYTES = 2 * 1024 * 1024
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)
MAX_EXTERNAL = 8

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS publish_seal("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,url TEXT,"
                  "content_hash TEXT,byte_length INTEGER,http_status INTEGER,"
                  "content_type TEXT,note TEXT,external TEXT,"
                  "fetched REAL,audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_url ON publish_seal(url,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pub_hash ON publish_seal(content_hash)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


# ----------------------------------------------------------------------
# fetching - read the SSRF note above before touching any of this
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an instruction to fetch a second URL we never checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _address_allowed(host, port):
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    if not infos:
        return False, "host resolved to nothing"
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    if not parts.hostname:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    return _address_allowed(parts.hostname, port)


def _fetch(url):
    """Returns (body_bytes, status, content_type, error)."""
    ok, why = _url_allowed(url)
    if not ok:
        return None, None, None, why
    request = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "aileash-publish/%s" % VERSION,
    })
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            body = response.read(MAX_FETCH_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, exc.code, None, "url answered %s" % exc.code
    except Exception as exc:
        return None, None, None, "could not reach url (%s)" % type(exc).__name__
    if len(body) > MAX_FETCH_BYTES:
        return None, status, content_type, "response larger than the %d byte cap" % MAX_FETCH_BYTES
    return body, status, content_type, None


def _content_hash(body):
    """Hash exactly the bytes served. No normalisation, no cleverness -
    a whitespace-tolerant hash would be a hash of our opinion of the page
    rather than of the page."""
    return hashlib.sha256(CONTENT_PREFIX + body).hexdigest()


# ----------------------------------------------------------------------
# seal
# ----------------------------------------------------------------------

def _clean_external(value):
    """External references are recorded verbatim and never verified."""
    if not isinstance(value, list):
        return []
    out = []
    for item in value[:MAX_EXTERNAL]:
        if isinstance(item, dict):
            source = str(item.get("source", "")).strip()[:60]
            reference = str(item.get("reference", item.get("url", ""))).strip()[:400]
            claimed = str(item.get("claimed_time", "")).strip()[:60]
            if source and reference:
                out.append({"source": source, "reference": reference,
                            "claimed_time": claimed or None})
        elif isinstance(item, str) and item.strip():
            out.append({"source": "unnamed", "reference": item.strip()[:400],
                        "claimed_time": None})
    return out


def _seal(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required",
                "message": "The address of the page you have just published."}, 400

    note = str(data.get("note", "") or "").strip()[:300]
    external = _clean_external(data.get("external"))

    body, status, content_type, why = _fetch(url)
    if why:
        return {"error": "fetch_failed", "url": url, "message": why,
                "note": "Nothing was sealed. A record of a page we could not read would be "
                        "worse than no record."}, 502

    digest = _content_hash(body)
    now = time.time()

    with ctx["lock"]:
        prior = ctx["conn"].execute(
            "SELECT content_hash,fetched,audit_hash FROM publish_seal "
            "WHERE url=? ORDER BY id ASC", (url,)).fetchall()

    unchanged = bool(prior) and prior[-1][0] == digest
    first_of_this_version = None
    for row in prior:
        if row[0] == digest:
            first_of_this_version = row[1]
            break

    external_summary = ";".join("%s=%s" % (e["source"], e["reference"][:60]) for e in external)
    ev = {"user_id": "pub:" + digest[:16], "action": "publication_sealed", "amount": 0,
          "country": "UK", "device_id": "publish", "anomaly": 0, "device_risk": 0}
    res = {"decision": "PUBLICATION_SEALED", "score": 0, "publish_version": VERSION,
           "url": url, "content_hash": digest, "bytes": len(body),
           "http_status": status,
           "detail": "url=%s;sha256=%s;bytes=%d%s"
                     % (url, digest, len(body),
                        ";external=" + external_summary if external_summary else "")}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO publish_seal(api_key,url,content_hash,byte_length,http_status,"
            "content_type,note,external,fetched,audit_hash,block_index) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, digest, len(body), status, content_type or None,
             note or None,
             "|".join("%s %s %s" % (e["source"], e["reference"], e["claimed_time"] or "")
                      for e in external) or None,
             now, audit_hash, block_index))
        ctx["conn"].commit()

    out = {
        "url": url, "content_hash": digest, "bytes": len(body),
        "http_status": status, "content_type": content_type,
        "sealed_at": _iso(now),
        "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
        "version_number": len(prior) + 1,
        "publish_version": VERSION,
        "what_this_proves": "This exact content was served at this address when we fetched it, "
                            "and the record of that cannot be altered afterwards.",
        "what_it_does_not": "It does not prove the page existed earlier than this moment. "
                            "Nothing can prove that after the fact - timestamps only run "
                            "forwards. Seal at publication and the question never arises.",
        "history": "/x/publish/history?url=" + url,
        "verify_this_block": "/x/consistency/ancestor?tip=" + audit_hash,
    }

    if unchanged:
        out["unchanged"] = True
        out["first_sealed_in_this_form"] = _iso(first_of_this_version)
        out["message"] = ("Identical to the last sealed version. The page has not changed since "
                          "%s and now has an additional dated witness." % _iso(first_of_this_version))
    elif prior:
        out["changed"] = True
        out["previous_hash"] = prior[-1][0]
        out["previous_sealed_at"] = _iso(prior[-1][1])
        out["message"] = ("The content has changed since the last seal. Both versions remain in "
                          "the chain - a revision history the publisher cannot edit.")
    else:
        out["message"] = ("First seal for this address. Every later seal builds a permanent, "
                          "dated revision history from here.")

    if external:
        out["external_references"] = external
        out["external_caveat"] = ("Recorded exactly as supplied and sealed with the block. We do "
                                  "not verify them and they are not our evidence - they are "
                                  "somebody else's record, named so you can check them at "
                                  "source.")
    else:
        out["advice"] = ("If this page was published before today, add external references - a "
                         "GitHub push event, a Wayback snapshot - and they will be sealed "
                         "alongside. Those carry an earlier date; a seal made now cannot.")
    return out, 200


# ----------------------------------------------------------------------
# reading
# ----------------------------------------------------------------------

def _parse_external(blob):
    if not blob:
        return []
    out = []
    for line in blob.split("|"):
        parts = line.strip().split(" ", 2)
        if len(parts) >= 2:
            out.append({"source": parts[0], "reference": parts[1],
                        "claimed_time": parts[2] if len(parts) > 2 and parts[2] else None})
    return out


def _history(ctx, data):
    url = str(data.get("url", "")).strip()
    if not url:
        return {"error": "url_required"}, 400
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT content_hash,byte_length,fetched,audit_hash,block_index,note,external "
            "FROM publish_seal WHERE url=? ORDER BY id ASC LIMIT 500", (url,)).fetchall()
    if not rows:
        return {"error": "never_sealed", "url": url,
                "message": "No seal recorded for that address."}, 404

    versions, last_hash = [], None
    for content_hash, length, fetched, audit_hash, block_index, note, external in rows:
        versions.append({
            "content_hash": content_hash, "bytes": length,
            "sealed_at": _iso(fetched), "sealed_in_chain": audit_hash,
            "block_index": block_index, "note": note,
            "changed_from_previous": last_hash is not None and content_hash != last_hash,
            "external_references": _parse_external(external),
        })
        last_hash = content_hash

    distinct = len({v["content_hash"] for v in versions})
    return {"url": url, "seals": len(versions), "distinct_versions": distinct,
            "first_sealed": versions[0]["sealed_at"], "latest_sealed": versions[-1]["sealed_at"],
            "current_hash": versions[-1]["content_hash"],
            "versions": versions,
            "publish_version": VERSION,
            "what_this_is": "A dated revision history the publisher cannot edit. Each version is "
                            "its own block; altering or removing one breaks every block after it.",
            "limit": "The first seal fixes an upper bound, not a lower one. Anything published "
                     "before its first seal rests on external evidence, which is recorded here "
                     "but not verified by us."}, 200


def _verify(ctx, data):
    url = str(data.get("url", "")).strip()
    digest = str(data.get("hash", data.get("content_hash", ""))).strip().lower()
    if not digest or not HEX64.match(digest):
        return {"error": "hash_required",
                "message": "sha256 of AILEASH-PUBLISH-v1: followed by the exact bytes served"}, 400

    with ctx["lock"]:
        if url:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE url=? AND content_hash=? ORDER BY id ASC", (url, digest)).fetchall()
        else:
            rows = ctx["conn"].execute(
                "SELECT url,fetched,audit_hash,block_index FROM publish_seal "
                "WHERE content_hash=? ORDER BY id ASC", (digest,)).fetchall()

    if not rows:
        return {"sealed": False, "content_hash": digest, "url": url or None,
                "message": "We hold no seal for that exact content. Either it was never sealed, "
                           "or the content differs from what was - a single byte is enough."}, 404

    return {"sealed": True, "content_hash": digest,
            "url": rows[0][0], "times_sealed": len(rows),
            "first_sealed": _iso(rows[0][1]),
            "latest_sealed": _iso(rows[-1][1]),
            "sealed_in_chain": rows[0][2], "block_index": rows[0][3],
            "publish_version": VERSION,
            "what_this_proves": "Content with exactly this fingerprint was served at that "
                                "address no later than the first sealing time, and the record "
                                "of it has not been altered since.",
            "verify_the_block": "/x/consistency/ancestor?tip=" + rows[0][2]}, 200


def _list(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT url,COUNT(*),MIN(fetched),MAX(fetched),COUNT(DISTINCT content_hash) "
            "FROM publish_seal GROUP BY url ORDER BY MAX(fetched) DESC LIMIT 500").fetchall()
    return {"count": len(rows),
            "pages": [{"url": r[0], "seals": r[1], "first_sealed": _iso(r[2]),
                       "latest_sealed": _iso(r[3]), "distinct_versions": r[4],
                       "history": "/x/publish/history?url=" + r[0]} for r in rows],
            "publish_version": VERSION,
            "note": "Everything this platform has sealed about its own published pages. Ours is "
                    "in here too - a publisher who seals everyone's pages but not their own is "
                    "telling you something."}, 200


def _spec():
    return {
        "publish_version": VERSION,
        "content_hash": "sha256('AILEASH-PUBLISH-v1:' || exact_bytes_served) as lowercase hex",
        "no_normalisation": "The bytes are hashed exactly as served. Nothing is trimmed, "
                            "reordered or cleaned up first - a whitespace-tolerant hash would "
                            "be a hash of our opinion of the page rather than of the page.",
        "reproduce_it": "curl the URL, pipe the raw bytes through sha256 with that prefix, and "
                        "compare with what we sealed. If your bytes differ, the page changed.",
        "what_a_seal_proves": "That content with this exact fingerprint was served at this "
                              "address no later than the sealing time, and that the record has "
                              "not been altered since - it is a chain block like any other, "
                              "anchored externally and witnessed by peers.",
        "what_it_cannot_prove": "That the page existed before the seal. Timestamps run forwards "
                                "only. Any product implying otherwise is misdescribing what a "
                                "timestamp is.",
        "for_earlier_dates": {
            "github_push": "api.github.com/repos/<owner>/<repo>/events - the push timestamp is "
                           "recorded by GitHub, not the pusher, unlike commit author and "
                           "committer dates which are settable fields. Retained around 90 days, "
                           "so capture it while it exists.",
            "wayback": "archive.org/wayback/available - an independent party with no stake in "
                       "the dispute.",
            "status": "Both are recorded and sealed as supplied, and neither is verified by us. "
                      "They are somebody else's evidence, named so you can check them at source.",
        },
        "the_discipline": "Seal at publication. One call at the moment a page goes live means "
                          "the publication date never rests on anyone's word, anyone's git "
                          "history, or anyone's memory again.",
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action == "history":
            return _history(ctx, data)
        if action == "verify":
            return _verify(ctx, data)
        if action == "list":
            return _list(ctx)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "seal":
            return _seal(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "verify", "list"],
            "POST": ["seal (keyed)"]}, 404

```


## `modules/pwa.py`

243 lines, 20540 bytes

```python
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

```


## `modules/ratchet.py`

615 lines, 25928 bytes

```python
"""
ratchet.py - time only runs one way for the machine.

WHAT THIS IS FOR
----------------
heartbeat.py proves WHEN a record can have been made. sortition.py proves
NOBODY CHOSE what got reviewed. This one proves an actor cannot move
backwards through time.

Every action an agent takes is bound to the beacon round current at the
moment it acted. Beacon rounds only ever increase. So an actor's actions
form a strictly rising ladder, and the rule is one line:

    an action carrying a beacon round at or below the actor's last
    recorded round is REFUSED.

WHAT THAT KILLS, WITHOUT A POLICY, A PROMPT OR A PROMISE
--------------------------------------------------------
BACKDATING     An agent cannot produce an action claiming to sit earlier
               than one it already took. The earlier round is already
               spent.
REPLAY         Capture a valid action and fire it again later: the round
               is stale and the digest is already on the ladder.
PRE-COMPUTATION
               An agent cannot prepare a batch of actions in advance,
               because it cannot know tomorrow's beacon values today. A
               round that has not been sealed here yet is refused.
REWIND         Restore an agent from an old snapshot to undo its history
               and its next action lands below the recorded floor. The
               ladder is in a chain the agent does not control, so
               restoring the agent does not restore its position.

REFUSALS ARE SEALED, NOT DROPPED
--------------------------------
This is the part that matters. A refused action is written into the chain
with the reason. An agent trying to rewind is the single most interesting
event this system can observe, and throwing it away as a 409 would be
throwing away the evidence. /x/ratchet/refusals is public.

HONEST LIMITS
-------------
- It binds an actor's actions to an order. It says nothing about whether
  any action was correct, authorised, or wise.
- An actor that simply stops acting cannot be forced to continue. Silence
  is visible (last_seen goes stale) but is not prevented.
- Two different actor ids are two different ladders. Anyone able to mint
  new actor ids can start a fresh ladder; that is an identity problem,
  handled by whatever issues the ids, not here.
- The floor is only as fine-grained as the beat cadence. At a five
  minute cadence, two actions inside the same beat are ordered by
  sequence, not by beacon time, and that is reported rather than dressed
  up.
- It depends on heartbeat. With no beats sealed, nothing can be admitted,
  and this module says so rather than waving actions through.

Contract: handle(method, action, data, api_key, ctx) -> (dict, status)
Routes:
  GET  spec      public  what this is and the exact admission rules
  GET  actor     public  ?id= - one actor's current rung and ladder
  GET  actors    public  every ladder, with staleness
  GET  refusals  public  every refused attempt, with reason. The good bit.
  GET  verify    public  ?id= - re-walk a ladder and report any break
  GET  status    public  coverage, admission and refusal counts
  POST act       keyed   submit an action. Admitted or refused; both sealed.
"""

import json
import time
import hashlib

VERSION = "1.0.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "actor"),
    ("GET", "actors"),
    ("GET", "refusals"),
    ("GET", "verify"),
    ("GET", "status"),
}

MAX_LAG_BEATS = 3          # how far behind the newest beat an action may be
MAX_ACTOR_LEN = 120
STALE_SECONDS = 3600

REASONS = {
    "ok": "Admitted. The round is ahead of this actor's last rung.",
    "no_beats": (
        "Refused: no beacon has been sealed on this server, so there is no "
        "time to bind to. Nothing is admitted on trust."),
    "round_unknown": (
        "Refused: that beacon round has not been sealed here. Either it has "
        "not happened yet - which would mean the actor knew a value before "
        "it existed - or this server has not observed it."),
    "round_not_advanced": (
        "Refused: the round is at or below this actor's last rung. This is "
        "the ratchet. An actor cannot move backwards through beacon time, "
        "whether by backdating, by replay, or by being restored from an "
        "older snapshot."),
    "round_too_stale": (
        "Refused: the round is further behind the current beat than the "
        "permitted lag. An action bound to old time is a replay or a very "
        "slow actor; both are refused and both are recorded."),
    "digest_replayed": (
        "Refused: this exact action digest is already on this actor's "
        "ladder. Identical work resubmitted is a replay by definition."),
    "bad_request": "Refused: malformed submission.",
}

WHAT_THIS_PROVES = (
    "That an actor's recorded actions only ever moved forward in a public "
    "time nobody controls. It does not prove any action was correct, "
    "authorised, or sensible."
)

DDL = [
    """CREATE TABLE IF NOT EXISTS ratchet_rung (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        actor         TEXT NOT NULL,
        seq           INTEGER NOT NULL,
        beacon_round  INTEGER NOT NULL,
        beacon_value  TEXT,
        digest        TEXT NOT NULL,
        label         TEXT,
        at            REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rat_seq ON ratchet_rung(actor, seq)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rat_dig ON ratchet_rung(actor, digest)",
    "CREATE INDEX IF NOT EXISTS idx_rat_actor ON ratchet_rung(actor)",
    """CREATE TABLE IF NOT EXISTS ratchet_refusal (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        actor         TEXT NOT NULL,
        claimed_round INTEGER,
        last_round    INTEGER,
        digest        TEXT,
        reason        TEXT NOT NULL,
        at            REAL NOT NULL,
        chain_rowid   INTEGER,
        audit_hash    TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_rat_ref ON ratchet_refusal(actor)",
]


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _ensure(conn, lock):
    with lock:
        cur = conn.cursor()
        for stmt in DDL:
            cur.execute(stmt)
        conn.commit()


def _iso(t):
    if t is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def _human(seconds):
    if seconds is None:
        return None
    s = int(round(seconds))
    if s < 60:
        return "%d seconds" % s
    if s < 3600:
        return "%d minutes" % (s // 60)
    if s < 86400:
        return "%d hours" % (s // 3600)
    return "%d days" % (s // 86400)


def _seal(ctx, action, payload):
    """server.py: seal(event, result, ts, api_key=None); event is a DICT
    carrying user_id; returns (audit_hash, block_index, key_seq)."""
    fn = ctx.get("seal")
    if fn is None:
        return None, None
    ts = time.time()
    event = {"user_id": "ratchet", "action": action, "amount": 0,
             "country": "UK", "device_id": "ratchet", "anomaly": 0,
             "device_risk": 0}
    result = dict(payload)
    result.setdefault("decision", "RATCHET")
    result.setdefault("score", 0)
    result.setdefault("version", VERSION)
    result.setdefault("timestamp", ts)
    for call in (lambda: fn(event, result, ts),
                 lambda: fn(event, result, ts, None),
                 lambda: fn(event, result)):
        try:
            out = call()
        except TypeError:
            continue
        except Exception:
            return None, None
        h = idx = None
        if isinstance(out, (tuple, list)):
            for item in out:
                if isinstance(item, str) and len(item) == 64 and h is None:
                    h = item
                elif isinstance(item, int) and idx is None:
                    idx = item
        elif isinstance(out, str):
            h = out
        return h, idx
    return None, None


def _newest_beat(conn):
    try:
        cur = conn.cursor()
        cur.execute("SELECT beacon_round, value, fetched_at FROM heartbeat_tick"
                    " WHERE chain_rowid IS NOT NULL AND beacon_round IS NOT NULL"
                    " ORDER BY beacon_round DESC LIMIT 1")
        return cur.fetchone()
    except Exception:
        return None


def _beat(conn, rnd):
    try:
        cur = conn.cursor()
        cur.execute("SELECT beacon_round, value, fetched_at FROM heartbeat_tick"
                    " WHERE beacon_round=? AND chain_rowid IS NOT NULL LIMIT 1",
                    (rnd,))
        return cur.fetchone()
    except Exception:
        return None


def _beats_between(conn, low, high):
    """How many sealed beats sit in (low, high]. Used for the lag check."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM heartbeat_tick WHERE chain_rowid IS"
                    " NOT NULL AND beacon_round>? AND beacon_round<=?",
                    (low, high))
        return cur.fetchone()[0]
    except Exception:
        return 0


def _top(conn, actor):
    cur = conn.cursor()
    cur.execute("SELECT seq, beacon_round, digest, at FROM ratchet_rung"
                " WHERE actor=? ORDER BY seq DESC LIMIT 1", (actor,))
    return cur.fetchone()


def _refuse(ctx, conn, lock, actor, rnd, last, digest, reason, extra=None):
    now = time.time()
    with lock:
        cur = conn.cursor()
        cur.execute("INSERT INTO ratchet_refusal (actor, claimed_round,"
                    " last_round, digest, reason, at) VALUES (?,?,?,?,?,?)",
                    (actor, rnd, last, digest, reason, now))
        rid = cur.lastrowid
        conn.commit()
    h, idx = _seal(ctx, "ratchet_refused", {
        "kind": "ratchet_refusal", "actor": actor, "claimed_round": rnd,
        "last_admitted_round": last, "digest": digest, "reason": reason,
        "explanation": REASONS.get(reason, reason),
        "note": ("A refused action is sealed rather than discarded. An actor "
                 "attempting to move backwards is the most interesting event "
                 "this module can observe."),
    })
    if h or idx:
        with lock:
            conn.execute("UPDATE ratchet_refusal SET chain_rowid=?,"
                         " audit_hash=? WHERE id=?", (idx, h, rid))
            conn.commit()
    out = {
        "admitted": False,
        "reason": reason,
        "explanation": REASONS.get(reason, reason),
        "actor": actor,
        "claimed_round": rnd,
        "last_admitted_round": last,
        "refusal_sealed_at_block": idx,
        "refusal_audit_hash": h,
        "this_refusal_is_permanent": True,
        "public_record": "/x/ratchet/refusals",
    }
    if extra:
        out.update(extra)
    return out


# ---------------------------------------------------------------------
# handle
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    conn, lock = ctx["conn"], ctx["lock"]
    _ensure(conn, lock)

    if method == "GET" and action == "spec":
        return _spec(), 200

    # -------------------------------------------------- act
    if method == "POST" and action == "act":
        actor = str(data.get("actor") or "").strip().lower()[:MAX_ACTOR_LEN]
        digest = str(data.get("digest") or "").strip().lower()
        label = str(data.get("label") or "")[:200] or None
        rnd = data.get("round")

        if not actor:
            return {"error": "actor_required",
                    "note": "A stable identifier for the acting agent."}, 400
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return {"error": "digest_required",
                    "note": ("A SHA-256 of the action. The action itself never "
                             "leaves your system.")}, 400

        newest = _newest_beat(conn)
        if not newest:
            top = _top(conn, actor)
            return _refuse(ctx, conn, lock, actor, rnd,
                           top[1] if top else None, digest, "no_beats"), 503

        newest_round = newest[0]
        if rnd is None:
            rnd = newest_round          # bind to now if the caller does not say
        try:
            rnd = int(rnd)
        except (TypeError, ValueError):
            return {"error": "round_invalid"}, 400

        top = _top(conn, actor)
        last_round = top[1] if top else None
        last_seq = top[0] if top else 0

        if not _beat(conn, rnd):
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_unknown",
                           {"newest_sealed_round": newest_round}), 409

        if last_round is not None and rnd <= last_round:
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_not_advanced",
                           {"the_rule": ("beacon round must be strictly greater "
                                         "than the actor's last rung")}), 409

        lag = _beats_between(conn, rnd, newest_round)
        if lag > MAX_LAG_BEATS:
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "round_too_stale",
                           {"beats_behind": lag,
                            "max_lag_beats": MAX_LAG_BEATS,
                            "newest_sealed_round": newest_round}), 409

        cur = conn.cursor()
        cur.execute("SELECT seq FROM ratchet_rung WHERE actor=? AND digest=?",
                    (actor, digest))
        if cur.fetchone():
            return _refuse(ctx, conn, lock, actor, rnd, last_round, digest,
                           "digest_replayed"), 409

        beat = _beat(conn, rnd)
        now = time.time()
        seq = last_seq + 1
        with lock:
            cur = conn.cursor()
            cur.execute("INSERT INTO ratchet_rung (actor, seq, beacon_round,"
                        " beacon_value, digest, label, at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (actor, seq, rnd, beat[1], digest, label, now))
            rid = cur.lastrowid
            conn.commit()

        h, idx = _seal(ctx, "ratchet_step", {
            "kind": "ratchet_step", "actor": actor, "seq": seq,
            "beacon_round": rnd, "beacon_value": beat[1], "digest": digest,
            "label": label, "previous_round": last_round,
            "note": ("Bound to a public beacon value the actor could not have "
                     "known before that round existed."),
        })
        if h or idx:
            with lock:
                conn.execute("UPDATE ratchet_rung SET chain_rowid=?,"
                             " audit_hash=? WHERE id=?", (idx, h, rid))
                conn.commit()

        return {
            "admitted": True, "actor": actor, "seq": seq,
            "beacon_round": rnd, "beacon_value": beat[1],
            "previous_round": last_round, "digest": digest,
            "sealed_at_block": idx, "audit_hash": h,
            "floor": ("This action cannot have been created before beacon "
                      "round %d at %s." % (rnd, _iso(beat[2]))),
            "ratchet": ("This actor can no longer act at or below round %d. "
                        "That door is shut permanently." % rnd),
            "verify_beacon": "/x/heartbeat/verify?round=%d" % rnd,
        }, 200

    # -------------------------------------------------- actor
    if method == "GET" and action == "actor":
        actor = str(data.get("id") or "").strip().lower()
        if not actor:
            return {"error": "id_required",
                    "usage": "/x/ratchet/actor?id=<actor>"}, 400
        cur = conn.cursor()
        cur.execute("SELECT seq, beacon_round, digest, label, at, chain_rowid,"
                    " audit_hash FROM ratchet_rung WHERE actor=? ORDER BY seq",
                    (actor,))
        rungs = cur.fetchall()
        if not rungs:
            return {"actor": actor, "rungs": 0,
                    "message": "No ladder for this actor."}, 404
        cur.execute("SELECT COUNT(*) FROM ratchet_refusal WHERE actor=?", (actor,))
        refused = cur.fetchone()[0]
        last = rungs[-1]
        age = time.time() - last[4]
        return {
            "actor": actor,
            "rungs": len(rungs),
            "current_round": last[1],
            "current_seq": last[0],
            "last_action_at": _iso(last[4]),
            "seconds_since": round(age, 1),
            "status": "current" if age < STALE_SECONDS else "silent",
            "refusals": refused,
            "ladder": [{"seq": r[0], "round": r[1], "digest": r[2],
                        "label": r[3], "at": _iso(r[4]), "block": r[5],
                        "audit_hash": r[6]} for r in rungs[-50:]],
            "floor_now": ("This actor cannot act at or below round %d."
                          % last[1]),
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    # -------------------------------------------------- actors
    if method == "GET" and action == "actors":
        now = time.time()
        cur = conn.cursor()
        cur.execute("SELECT actor, COUNT(*), MAX(beacon_round), MAX(at)"
                    " FROM ratchet_rung GROUP BY actor ORDER BY MAX(at) DESC")
        out = []
        for a, n, rnd, at in cur.fetchall():
            cur2 = conn.cursor()
            cur2.execute("SELECT COUNT(*) FROM ratchet_refusal WHERE actor=?", (a,))
            out.append({"actor": a, "rungs": n, "current_round": rnd,
                        "last_action": _iso(at),
                        "silent_for": _human(now - at) if now - at > STALE_SECONDS else None,
                        "refusals": cur2.fetchone()[0]})
        return {"count": len(out), "actors": out,
                "note": ("Silence is visible but not prevented. An actor that "
                         "stops acting simply stops, and no design fixes "
                         "that.")}, 200

    # -------------------------------------------------- refusals
    if method == "GET" and action == "refusals":
        try:
            limit = min(int(data.get("limit", 100)), 500)
        except (TypeError, ValueError):
            limit = 100
        cur = conn.cursor()
        cur.execute("SELECT actor, claimed_round, last_round, digest, reason,"
                    " at, chain_rowid, audit_hash FROM ratchet_refusal"
                    " ORDER BY id DESC LIMIT ?", (limit,))
        rows = cur.fetchall()
        mix = {}
        for r in rows:
            mix[r[4]] = mix.get(r[4], 0) + 1
        return {
            "count": len(rows),
            "by_reason": mix,
            "refusals": [{"actor": r[0], "claimed_round": r[1],
                          "last_admitted_round": r[2], "digest": r[3],
                          "reason": r[4], "explanation": REASONS.get(r[4], r[4]),
                          "at": _iso(r[5]), "block": r[6], "audit_hash": r[7]}
                         for r in rows],
            "why_this_is_public": (
                "A refused action is sealed rather than discarded, and the "
                "list is open. An actor attempting to move backwards through "
                "time is the single most interesting thing this system can "
                "see, and hiding it would defeat the point of building it."),
        }, 200

    # -------------------------------------------------- verify
    if method == "GET" and action == "verify":
        actor = str(data.get("id") or "").strip().lower()
        if not actor:
            return {"error": "id_required"}, 400
        cur = conn.cursor()
        cur.execute("SELECT seq, beacon_round, beacon_value, digest FROM"
                    " ratchet_rung WHERE actor=? ORDER BY seq", (actor,))
        rungs = cur.fetchall()
        if not rungs:
            return {"error": "unknown_actor", "actor": actor}, 404
        breaks = []
        prev_seq = 0
        prev_round = None
        seen = set()
        for seq, rnd, val, dig in rungs:
            if seq != prev_seq + 1:
                breaks.append({"at_seq": seq, "fault": "sequence_gap",
                               "expected": prev_seq + 1})
            if prev_round is not None and rnd <= prev_round:
                breaks.append({"at_seq": seq, "fault": "round_did_not_advance",
                               "round": rnd, "previous": prev_round})
            if dig in seen:
                breaks.append({"at_seq": seq, "fault": "duplicate_digest"})
            b = _beat(conn, rnd)
            if not b:
                breaks.append({"at_seq": seq, "fault": "beacon_round_not_sealed",
                               "round": rnd})
            elif b[1] != val:
                breaks.append({"at_seq": seq, "fault": "beacon_value_mismatch",
                               "round": rnd})
            seen.add(dig)
            prev_seq, prev_round = seq, rnd
        return {
            "actor": actor, "rungs": len(rungs), "intact": not breaks,
            "breaks": breaks,
            "checked": ["sequence has no gaps",
                        "beacon round strictly increases",
                        "no digest appears twice",
                        "each rung's beacon value matches the sealed beat"],
            "do_it_without_us": (
                "Every beacon round on the ladder is re-fetchable from the "
                "beacon operator. Confirm each value there, then confirm each "
                "audit_hash is in the chain at /api/verify-chain. Neither step "
                "needs our cooperation."),
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    # -------------------------------------------------- status
    if method == "GET" and action == "status":
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT actor) FROM ratchet_rung")
        rungs, actors = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM ratchet_refusal")
        refused = cur.fetchone()[0]
        cur.execute("SELECT reason, COUNT(*) FROM ratchet_refusal GROUP BY reason")
        mix = {r[0]: r[1] for r in cur.fetchall()}
        newest = _newest_beat(conn)
        return {
            "version": VERSION,
            "actors": actors, "rungs_admitted": rungs,
            "actions_refused": refused,
            "refusals_by_reason": mix,
            "current_beacon_round": newest[0] if newest else None,
            "beacon_available": newest is not None,
            "max_lag_beats": MAX_LAG_BEATS,
            "depends_on": {
                "heartbeat": ("supplies the time. With no beats sealed, "
                              "nothing is admitted - actions are refused "
                              "rather than waved through on trust."),
            },
            "what_this_proves": WHAT_THIS_PROVES,
        }, 200

    return {"error": "unknown_action", "action": action,
            "actions": ["spec", "actor", "actors", "refusals", "verify",
                        "status", "act"]}, 404


def _spec():
    return {
        "module": "ratchet",
        "version": VERSION,
        "one_line": "Time only runs one way for the machine.",
        "the_rule": (
            "An action carrying a beacon round at or below the actor's last "
            "recorded round is refused. Beacon rounds only increase, so an "
            "actor's ladder only rises."),
        "what_it_kills": {
            "backdating": "the earlier round is already spent",
            "replay": "stale round, and the digest is already on the ladder",
            "pre_computation": ("an unsealed future round is refused, and "
                                "nobody can know a beacon value early"),
            "rewind": ("the ladder lives in a chain the actor does not "
                       "control, so restoring an agent from a snapshot does "
                       "not restore its position"),
        },
        "admission_rules_in_order": [
            "1. A beat must exist. No beats, nothing admitted.",
            "2. The claimed round must already be sealed here.",
            "3. The round must be strictly above the actor's last rung.",
            "4. The round must be within %d beats of the newest." % MAX_LAG_BEATS,
            "5. The digest must not already be on this actor's ladder.",
        ],
        "refusals_are_sealed": (
            "A refused action is written into the chain with its reason and "
            "published at /x/ratchet/refusals. Discarding it would throw away "
            "the most interesting evidence the system can produce."),
        "privacy": (
            "Only a SHA-256 of the action is submitted. The action itself, "
            "its inputs and its outputs never leave the caller's system."),
        "what_this_proves": WHAT_THIS_PROVES,
        "limits": [
            "It proves order, not correctness, authority or good judgement.",
            "An actor that stops acting is visible but not prevented.",
            "New actor ids start new ladders; identity is not this module's "
            "problem and it does not pretend otherwise.",
            "Within a single beat, actions are ordered by sequence rather "
            "than by beacon time. At a five minute cadence that is a five "
            "minute grain, and it is reported rather than dressed up.",
        ],
        "routes": {
            "POST /x/ratchet/act": "keyed - submit an action digest",
            "GET /x/ratchet/actor?id=": "one ladder",
            "GET /x/ratchet/actors": "every ladder",
            "GET /x/ratchet/refusals": "every refused attempt and why",
            "GET /x/ratchet/verify?id=": "re-walk a ladder",
            "GET /x/ratchet/status": "counts and current round",
        },
    }

```


## `modules/ratelimit.py`

113 lines, 3662 bytes

```python
"""
modules/ratelimit.py  v1.0.0  -  per-key limits sized for real traffic

    Arm:     https://sebbi.pro/x/arm/status
    Status:  https://sebbi.pro/x/ratelimit/status

server.py allows 60 decisions a minute and 1,000 an hour per API key. That
suits a trial; an app sending every AI call through the gateway passes it in
seconds. This replaces server.check_rate when the site arms - server.py is
not edited, and the same windows and lock are used, so nothing else changes:

    trial keys  300 a minute,   10,000 an hour
    paid keys   3,000 a minute, 200,000 an hour

Each figure can be changed without a deploy of code, through Railway
variables: RATE_TRIAL_MIN, RATE_TRIAL_HOUR, RATE_PAID_MIN, RATE_PAID_HOUR.
"""

import os
import sys
import threading
import time

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "")}


def _int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


LIMITS = {"trial": (_int("RATE_TRIAL_MIN", 300), _int("RATE_TRIAL_HOUR", 10000)),
          "paid": (_int("RATE_PAID_MIN", 3000), _int("RATE_PAID_HOUR", 200000))}
_paid_cache = {}
_state = {"installed": False, "original": None, "refused": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _is_paid(s, key):
    hit = _paid_cache.get(key)
    now = time.time()
    if hit and now - hit[1] < 60:
        return hit[0]
    paid = False
    try:
        ki = s.get_key(key)
        paid = bool(ki and ki[3])
    except Exception:
        pass
    if len(_paid_cache) > 20000:
        _paid_cache.clear()
    _paid_cache[key] = (paid, now)
    return paid


def _install():
    with _lock:
        if _state["installed"]:
            return True
        s = _srv()
        if s is None or not hasattr(s, "check_rate") or not hasattr(s, "_key_wins"):
            return False
        if getattr(s.check_rate, "_sebbi_ratelimit", False):
            _state["installed"] = True
            return True
        _state["original"] = s.check_rate

        def check_rate(key):
            per_min, per_hour = LIMITS["paid" if _is_paid(s, key) else "trial"]
            t = time.time()
            with s._key_lock:
                w = s._key_wins[key]
                while w["min"] and w["min"][0] < t - 60:
                    w["min"].popleft()
                while w["hour"] and w["hour"][0] < t - 3600:
                    w["hour"].popleft()
                if len(w["min"]) >= per_min:
                    _state["refused"] += 1
                    return False, "rate_limit_minute"
                if len(w["hour"]) >= per_hour:
                    _state["refused"] += 1
                    return False, "rate_limit_hour"
                w["min"].append(t)
                w["hour"].append(t)
                return True, None

        check_rate._sebbi_ratelimit = True
        s.check_rate = check_rate
        _state["installed"] = True
        return True


def handle(method, action, data, api_key, ctx):
    try:
        _install()
    except Exception as e:
        _state["last_error"] = str(e)[:200]
    return {"module": "ratelimit", "version": VERSION, "armed": _state["installed"],
            "per_key": {"trial": {"per_minute": LIMITS["trial"][0], "per_hour": LIMITS["trial"][1]},
                        "paid": {"per_minute": LIMITS["paid"][0], "per_hour": LIMITS["paid"][1]}},
            "was": {"per_minute": 60, "per_hour": 1000},
            "refused_since_start": _state["refused"], "last_error": _state["last_error"]}, 200

```
