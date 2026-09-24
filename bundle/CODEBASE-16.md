# Codebase — part 16 of 41

Contains:
- `modules/prove.py`
- `modules/publish.py`
- `modules/ratchet.py`
- `modules/reconcile.py`


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


## `modules/reconcile.py`

440 lines, 20123 bytes

```python
"""
Reconciliation notary - /x/reconcile/<action>

THE PROBLEM THIS ATTACKS
------------------------
A sealed chain proves records were not altered after the fact. It does not
prove they were true when written. An operator who seals fiction on time has
a tamper-evident chain of fiction. Every honest person in this market knows
that, and almost nobody says it.

You cannot prove truth from outside a system. What you CAN do is what real
auditors do: substantive testing. Take the sealed claim, go to the operator's
own live system, and check whether the two agree - then seal the result of
that check, including the failures.

WHY THIS ONE IS DIFFERENT
-------------------------
The sample is fixed before the operator sees it.

/plan derives a selection seed from the current chain tip - a value the
operator cannot predict in advance and cannot change afterwards without
breaking the chain - picks the records to be tested, and seals that selection
BEFORE any data is requested. Only then are the record identifiers returned.

So the operator cannot choose which records get examined, cannot prepare only
the flattering ones, and cannot quietly drop a test that came back badly:
every planned run is sealed at the moment it is planned, and a plan with no
submitted result is visible forever as an abandoned test.

Mismatches are sealed with the same permanence as matches. That is the whole
design. A reconciliation system that can bury its own failures is decoration.

WHAT A PASS ACTUALLY MEANS
--------------------------
That two systems the operator controls agree with each other, on records the
operator could not choose, at a time the operator could not pick.

That is not proof of truth. An operator who fabricates consistently across
every system, in real time, without knowing what will be sampled, will pass.
What it does is raise the cost of lying from "edit one database" to
"maintain a coherent parallel reality across independent systems indefinitely,
under unpredictable sampling, with every failure sealed permanently."

That is the honest claim. It is also, as far as I know, more than anyone else
in this market is doing.

HONEST LIMITS
-------------
- Consistency is not truth. Two agreeing systems can both be wrong.
- The operator supplies the comparison data. This tests their systems against
  each other, not against the world.
- Sampling only covers what has been sealed. It cannot find a decision that
  was never recorded at all - gapless receipts are what cover that.
- A high match rate on a badly chosen field proves nothing. Reconcile the
  fields that would hurt to get wrong.

    POST /x/reconcile/plan     sample_size, field  - seals the selection first
    POST /x/reconcile/submit   run_id, results     - seals the comparison
    GET  /x/reconcile/run?id=RUN-XXXXXXXX
    GET  /x/reconcile/score
    GET  /x/reconcile/list
"""

import hashlib, json, time
from datetime import datetime, timezone

VERSION = "1.1"
MAX_SAMPLE = 200

# Planning and submitting stay keyed - they touch an operator's own records.
# What is public is the part that decides whether any of it means anything:
# that the sample was fixed before the data was asked for, and that failures
# were sealed as permanently as passes.
PUBLIC = {("GET", "public"), ("GET", "proof")}

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS reconcile_runs(run_id TEXT PRIMARY KEY,api_key TEXT,field TEXT,seed TEXT,planned REAL,submitted REAL,sample_size INTEGER,matched INTEGER,mismatched INTEGER,missing INTEGER,status TEXT DEFAULT 'planned',block_ids TEXT,detail TEXT)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_rec_key ON reconcile_runs(api_key)")
        ctx["conn"].commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def _seal_event(ctx, api_key, rid, action, detail):
    ts = time.time()
    ev = {"user_id": "rec:" + rid, "action": "reconcile_" + action, "amount": 0,
          "country": "UK", "device_id": "reconcile", "anomaly": 0, "device_risk": 0}
    res = {"decision": "RECONCILE_SEALED", "score": 0, "reconcile_action": action,
           "reconcile_version": VERSION, "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _plan(ctx, api_key, data):
    try:
        n = int(data.get("sample_size", 25))
    except Exception:
        return {"error": "invalid_sample_size"}, 400
    if n < 1 or n > MAX_SAMPLE:
        return {"error": "sample_size_out_of_range", "max": MAX_SAMPLE}, 400
    field = str(data.get("field", "decision")).strip()[:60] or "decision"

    with ctx["lock"]:
        tiprow = ctx["conn"].execute("SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        rows = ctx["conn"].execute("SELECT id,user_id,result_json,ts FROM audit_log WHERE api_key=? ORDER BY id ASC", (api_key,)).fetchall()

    if not rows:
        return {"error": "nothing_to_reconcile",
                "message": "No sealed records under this key yet."}, 400

    tip = tiprow[0] if tiprow else "GENESIS"
    ts = time.time()
    # Seed is bound to the chain tip. The operator cannot know it before the
    # records exist, and cannot alter it afterwards without breaking the chain.
    seed = _sha(tip + ":" + str(int(ts)) + ":" + field + ":" + str(n))

    # Deterministic selection from the seed - reproducible by anyone holding it.
    scored = sorted(rows, key=lambda r: _sha(seed + ":" + str(r[0])))
    picked = scored[:min(n, len(scored))]

    rid = "RUN-" + seed[:8].upper()
    block_ids = [p[0] for p in picked]

    sample = []
    for bid, uid, res_json, bts in picked:
        try:
            r = json.loads(res_json)
            sealed_val = r.get(field)
        except Exception:
            sealed_val = None
        sample.append({"block_index": bid, "record_id": uid,
                       "sealed_at": _iso(bts),
                       "sealed_value_sha256": _sha(str(sealed_val))})

    detail = ("field=" + field + ";sample_size=" + str(len(picked)) +
              ";seed=" + seed + ";from_tip=" + tip +
              ";blocks=" + ",".join(str(b) for b in block_ids[:60]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "planned", detail)

    with ctx["lock"]:
        ctx["conn"].execute("INSERT OR REPLACE INTO reconcile_runs(run_id,api_key,field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,block_ids,detail) VALUES(?,?,?,?,?,NULL,?,NULL,NULL,NULL,'planned',?,NULL)",
                            (rid, api_key, field, seed, ts, len(picked), json.dumps(block_ids)))
        ctx["conn"].commit()

    return {"run_id": rid, "field": field, "sample_size": len(picked),
            "seed": seed, "derived_from_tip": tip, "planned_at": _iso(ts),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "sample": sample,
            "next": "Fetch these record_ids from your own live system and POST them to /x/reconcile/submit",
            "note": "This selection is now sealed. It cannot be changed, and an unsubmitted plan stays visible as an abandoned test."}, 200


def _submit(ctx, api_key, data):
    rid = str(data.get("run_id", "")).strip().upper()
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,status,block_ids FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid, api_key)).fetchone()
    if not row:
        return {"error": "unknown_run_id"}, 404
    if row[2] != "planned":
        return {"error": "already_submitted",
                "message": "A run is reconciled once. Re-running until it passes is not reconciliation."}, 400

    results = data.get("results")
    if not isinstance(results, dict) or not results:
        return {"error": "results_required",
                "message": "Send {block_index: live_value} from your own system."}, 400

    field = row[0]
    block_ids = json.loads(row[3])

    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT id,user_id,result_json FROM audit_log WHERE id IN (" + ",".join("?" * len(block_ids)) + ")", block_ids).fetchall()

    sealed = {}
    for bid, uid, res_json in rows:
        try:
            sealed[bid] = json.loads(res_json).get(field)
        except Exception:
            sealed[bid] = None

    matched, mismatched, missing = [], [], []
    for bid in block_ids:
        key = str(bid)
        if key not in results:
            missing.append({"block_index": bid})
            continue
        live = results[key]
        want = sealed.get(bid)
        if str(live).strip().lower() == str(want).strip().lower():
            matched.append(bid)
        else:
            mismatched.append({"block_index": bid,
                               "sealed_value": want,
                               "live_value": live})

    ts = time.time()
    rate = round(100 * len(matched) / len(block_ids), 2) if block_ids else 0
    detail = ("field=" + field + ";matched=" + str(len(matched)) +
              ";mismatched=" + str(len(mismatched)) + ";missing=" + str(len(missing)) +
              ";match_rate=" + str(rate) +
              ";mismatch_blocks=" + ",".join(str(m["block_index"]) for m in mismatched[:40]))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, "reconciled", detail)

    with ctx["lock"]:
        ctx["conn"].execute("UPDATE reconcile_runs SET submitted=?,matched=?,mismatched=?,missing=?,status='reconciled',detail=? WHERE run_id=? AND api_key=?",
                            (ts, len(matched), len(mismatched), len(missing), json.dumps({"mismatched": mismatched[:100], "missing": missing[:100]}), rid, api_key))
        ctx["conn"].commit()

    out = {"run_id": rid, "field": field, "sample_size": len(block_ids),
           "matched": len(matched), "mismatched": len(mismatched),
           "missing": len(missing), "match_rate_pct": rate,
           "reconciled_at": _iso(ts), "audit_hash": h, "block_index": idx,
           "receipt_seq": seq,
           "note": "This result is sealed whichever way it went. It cannot be withdrawn."}
    if mismatched:
        out["mismatches"] = mismatched[:20]
        out["flag"] = "sealed records and live system disagree on " + str(len(mismatched)) + " of " + str(len(block_ids))
    if missing:
        out["missing_detail"] = "records the live system did not return - a gap, not a match"
    return out, 200


def _run(ctx, api_key, rid):
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status,detail FROM reconcile_runs WHERE run_id=? AND api_key=?", (rid.upper(), api_key)).fetchone()
        if not row:
            return {"error": "unknown_run_id"}, 404
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC", ("rec:" + rid.upper(),)).fetchall()
    events = []
    for bts, res, ah in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(bts), "event": r.get("reconcile_action"),
                           "detail": r.get("detail"), "sealed": ah})
        except Exception:
            pass
    total = row[4] or 0
    out = {"run_id": rid.upper(), "field": row[0], "seed": row[1],
           "planned": _iso(row[2]), "submitted": _iso(row[3]),
           "sample_size": total, "matched": row[5], "mismatched": row[6],
           "missing": row[7], "status": row[8], "events": events,
           "ordering_proof": "The plan block precedes the result block. The sample was fixed before any data was requested."}
    if row[9]:
        try:
            out["detail"] = json.loads(row[9])
        except Exception:
            pass
    if row[8] == "planned":
        out["flag"] = "planned but never submitted - an abandoned test, visible permanently"
    return out, 200


def _score(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT sample_size,matched,mismatched,missing,status,planned FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 500", (api_key,)).fetchall()
    if not rows:
        return {"runs": 0, "note": "No reconciliation runs on record."}, 200
    done = [r for r in rows if r[4] == "reconciled"]
    abandoned = len(rows) - len(done)
    tested = sum(r[0] or 0 for r in done)
    ok = sum(r[1] or 0 for r in done)
    bad = sum(r[2] or 0 for r in done)
    gone = sum(r[3] or 0 for r in done)
    out = {"runs": len(rows), "reconciled": len(done), "abandoned": abandoned,
           "records_tested": tested, "matched": ok, "mismatched": bad,
           "missing": gone,
           "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
           "last_run": _iso(rows[0][5])}
    if abandoned:
        out["flag"] = str(abandoned) + " planned run(s) never submitted"
    return out, 200


def _list(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,missing,status FROM reconcile_runs WHERE api_key=? ORDER BY planned DESC LIMIT 200", (api_key,)).fetchall()
    return {"count": len(rows),
            "runs": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                      "submitted": _iso(r[3]), "sample_size": r[4],
                      "matched": r[5], "mismatched": r[6], "missing": r[7],
                      "status": r[8]} for r in rows]}, 200


def _public(ctx):
    """The reconciliation record, readable without a key.

    Counts only. No record identifiers, no field values, no operator
    identity. What a stranger gets is the three numbers that cannot be
    flattered: how many runs were reconciled, how many disagreed, and how
    many were planned and then quietly abandoned.

    Abandoned runs are the important one. A planned run is sealed at the
    moment it is planned, so a test that came back badly and was dropped
    cannot be deleted - it sits here forever as a plan with no result.
    """
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT run_id,field,planned,submitted,sample_size,matched,mismatched,"
            "missing,status FROM reconcile_runs ORDER BY planned DESC LIMIT 200").fetchall()

    done = [r for r in rows if r[8] == "reconciled"]
    abandoned = [r for r in rows if r[8] != "reconciled"]
    tested = sum(r[4] or 0 for r in done)
    ok = sum(r[5] or 0 for r in done)
    bad = sum(r[6] or 0 for r in done)
    gone = sum(r[7] or 0 for r in done)

    out = {
        "runs": len(rows),
        "reconciled": len(done),
        "abandoned": len(abandoned),
        "records_tested": tested,
        "matched": ok,
        "mismatched": bad,
        "missing": gone,
        "match_rate_pct": (round(100 * ok / tested, 2) if tested else None),
        "recent": [{"run_id": r[0], "field": r[1], "planned": _iso(r[2]),
                    "submitted": _iso(r[3]), "sample_size": r[4],
                    "matched": r[5], "mismatched": r[6], "missing": r[7],
                    "status": r[8]} for r in rows[:50]],
        "check_any_of_them": "/x/reconcile/proof?id=RUN-XXXXXXXX",
        "what_is_being_shown": "Not that the records are true. That the sample was fixed "
                               "before the data was requested, and that what came back was "
                               "sealed either way.",
        "what_a_mismatch_means": "The sealed record and the operator's own live system "
                                 "disagreed. It is published because a reconciliation system "
                                 "that can bury its own failures is decoration.",
    }
    if abandoned:
        out["flag"] = (str(len(abandoned)) + " run(s) planned and never submitted. A sample was "
                       "fixed, and no result was ever sealed against it.")
    return out, 200


def _proof(ctx, rid):
    """The ordering, straight out of the chain, without a key.

    Both events are already sealed under a public identifier, so this route
    reveals nothing the chain does not already carry. It just makes the one
    claim that matters legible: the plan block comes before the result block.
    """
    rid = (rid or "").strip().upper()
    if not rid:
        return {"error": "id_required"}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT field,seed,planned,submitted,sample_size,matched,mismatched,missing,status "
            "FROM reconcile_runs WHERE run_id=?", (rid,)).fetchone()
        blocks = ctx["conn"].execute(
            "SELECT id,ts,result_json,audit_hash FROM audit_log WHERE user_id=? ORDER BY id ASC",
            ("rec:" + rid,)).fetchall()
    if not row:
        return {"error": "unknown_run_id", "list": "/x/reconcile/public"}, 404

    events = []
    plan_block = result_block = None
    for bid, bts, res, ah in blocks:
        try:
            r = json.loads(res)
        except Exception:
            continue
        what = r.get("reconcile_action")
        events.append({"event": what, "at": _iso(bts), "block_index": bid,
                       "sealed_in_chain": ah, "sealed_detail": r.get("detail")})
        if what == "planned" and plan_block is None:
            plan_block = bid
        if what == "reconciled" and result_block is None:
            result_block = bid

    ordered = (plan_block is not None and result_block is not None
               and plan_block < result_block)

    out = {"run_id": rid, "field": row[0], "status": row[8],
           "seed": row[1], "planned_at": _iso(row[2]), "submitted_at": _iso(row[3]),
           "sample_size": row[4], "matched": row[5], "mismatched": row[6],
           "missing": row[7],
           "plan_block_index": plan_block, "result_block_index": result_block,
           "selection_precedes_result": ordered,
           "events": events,
           "how_to_check_this_yourself": [
               "The seed is derived from the chain tip at planning time, which the operator "
               "cannot predict in advance or change afterwards without breaking the chain.",
               "The plan block seals which records were selected, and its detail is above.",
               "The result block seals what came back. Compare the two block indices.",
               "A lower plan index than result index means the sample was fixed before any "
               "data was requested. That is the whole claim, and it is the only one made."],
           "what_this_does_not_prove": "That the records are true. Two systems the operator "
                                       "controls agreeing with each other is consistency, not "
                                       "truth."}
    if row[8] != "reconciled":
        out["flag"] = ("planned and never submitted. The selection is sealed and no result "
                       "was ever put against it.")
    elif not ordered:
        out["flag"] = ("the plan block does not precede the result block. That should be "
                       "impossible and it is the finding.")
    return out, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "plan":
            return _plan(ctx, api_key, data)
        if action == "submit":
            return _submit(ctx, api_key, data)
    else:
        if action == "public":
            return _public(ctx)
        if action == "proof":
            return _proof(ctx, str((data or {}).get("id", "")))
        if action == "score":
            return _score(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "run":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _run(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action,
            "GET": ["public", "proof", "score", "list", "run"],
            "POST": ["plan", "submit"]}, 404

```
