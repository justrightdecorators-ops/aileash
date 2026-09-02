"""
modules/map.py  v1.0.0
Serves the layer-map page at /map.

Page module, same family as investor.py / console.py / network.py: a runtime
do_GET patch puts a full HTML page at a clean URL. Armed by hitting
/x/map/status once after each deploy. server.py is never edited. The page is
base64-embedded so no character in the HTML can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"
PAGE_PATH = "/map"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIi"
    "Pgo8dGl0bGU+V2hlcmUgc2ViYmkucHJvIHNpdHMg4oCUIHRoZSBsYXllciBtYXA8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlw"
    "dGlvbiIgY29udGVudD0iQSBiaXJkJ3MtZXllIG1hcCBvZiB0aGUgc3RhY2suIE1vbml0b3Jpbmcgd2F0Y2hlcyBmcm9tIHRoZSBz"
    "aWRlLCBhZnRlciB0aGUgZmFjdC4gQXV0b25vbW91cyBkZWNpc2lvbnMgY2FuJ3QgYmUgcHJvdmVuIGZyb20gdGhhdCBsYXllci4g"
    "c2ViYmkucHJvIHNpdHMgdW5kZXJuZWF0aCB0aGUgZGVjaXNpb24sIHNlYWxpbmcgaXQgYXMgaXQgaGFwcGVucy4iPgo8bGluayBy"
    "ZWw9InByZWNvbm5lY3QiIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20iPgo8bGluayBocmVmPSJodHRwczovL2Zv"
    "bnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDQwMDs2Li43Miw1MDA7Ni4u"
    "NzIsNjAwJmZhbWlseT1JQk0rUGxleCtTYW5zOndnaHRANDAwOzUwMDs2MDA7NzAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRA"
    "NDAwOzUwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7CiAgLS1pbms6IzBhMGYxZTstLWlu"
    "azI6IzEwMTgyZTstLXBhcGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7CiAgLS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0t"
    "b2stYmc6I0U0RUNFODsKICAtLXdhcm46IzlDMkYyNjstLXdhcm4tYmc6I0Y1RTZFMzstLW11dGVkOiM1QTYyNzA7LS1mYWludDoj"
    "OEE5MEEwOwogIC0tc2FuczonSUJNIFBsZXggU2Fucycsc3lzdGVtLXVpLHNhbnMtc2VyaWY7CiAgLS1zZXJpZjonTmV3c3JlYWRl"
    "cicsR2VvcmdpYSxzZXJpZjsKICAtLW1vbm86J0lCTSBQbGV4IE1vbm8nLHVpLW1vbm9zcGFjZSxtb25vc3BhY2U7Cn0KKntib3gt"
    "c2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2JhY2tncm91"
    "bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50"
    "aWFsaWFzZWR9Ci53cmFwe21heC13aWR0aDo4MjBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6MCAyNHB4fQoKLyogdG9wIGJhciAq"
    "LwoudG9we2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6MTZweCAwfQoudG9wIC53cmFwe2Rpc3Bs"
    "YXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpiYXNlbGluZTtnYXA6MTJweDtmbGV4LXdy"
    "YXA6d3JhcH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluayl9Ci5i"
    "cmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBuYXZ7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7"
    "Zm9udC1zaXplOjEyLjVweH0KLnRvcCBuYXYgYXtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2lu"
    "LWxlZnQ6MTZweH0KLnRvcCBuYXYgYTpob3Zlcntjb2xvcjp2YXIoLS1pbmspfQoKLyogaGVybyAqLwouaGVyb3twYWRkaW5nOjU2"
    "cHggMCAyMHB4fQouaGVybyBoMXtmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFt"
    "cCgzMHB4LDUuNXZ3LDUwcHgpO2xpbmUtaGVpZ2h0OjEuMDg7bGV0dGVyLXNwYWNpbmc6LTAuMDFlbTttYXgtd2lkdGg6MTdjaDtt"
    "YXJnaW4tYm90dG9tOjE4cHh9Ci5oZXJvIHB7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo1NmNo"
    "fQoKLyogdGhlIHN0YWNrIOKAlCB0aGUgaGVybyB2aXN1YWwgKi8KLnN0YWNre3BhZGRpbmc6MjRweCAwIDhweH0KLmxheWVye2Jv"
    "cmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo2cHg7cGFkZGluZzoyMHB4IDIycHg7bWFyZ2luLWJvdHRv"
    "bToxNHB4O2JhY2tncm91bmQ6I2ZmZjtwb3NpdGlvbjpyZWxhdGl2ZX0KLmxheWVyIC50YWd7Zm9udC1mYW1pbHk6dmFyKC0tbW9u"
    "byk7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MC4wNGVtO2NvbG9yOnZhcigtLWZhaW50KTttYXJnaW4tYm90dG9tOjdw"
    "eH0KLmxheWVyIGgze2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOjIxcHg7bWFyZ2lu"
    "LWJvdHRvbTo2cHg7bGluZS1oZWlnaHQ6MS4yfQoubGF5ZXIgcHtmb250LXNpemU6MTQuNXB4O2NvbG9yOnZhcigtLW11dGVkKTtt"
    "YXgtd2lkdGg6NjBjaH0KLmxheWVyIC52ZXJkaWN0e2Rpc3BsYXk6aW5saW5lLWJsb2NrO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8p"
    "O2ZvbnQtc2l6ZToxMnB4O21hcmdpbi10b3A6MTJweDtwYWRkaW5nOjRweCAxMHB4O2JvcmRlci1yYWRpdXM6M3B4fQoudi1ub3ti"
    "YWNrZ3JvdW5kOnZhcigtLXdhcm4tYmcpO2NvbG9yOnZhcigtLXdhcm4pfQoudi15ZXN7YmFja2dyb3VuZDp2YXIoLS1vay1iZyk7"
    "Y29sb3I6dmFyKC0tb2spfQoKLyogdGhlIHR3byB3YXRjaGVyIGxheWVycywgZHJhd24gYXMgYm9sdGVkIG9uIGJlc2lkZSAqLwou"
    "d2F0Y2h7Ym9yZGVyLXN0eWxlOmRhc2hlZDtib3JkZXItY29sb3I6I0M5Q0JkMH0KLndhdGNoIGgze2NvbG9yOnZhcigtLW11dGVk"
    "KX0KLmFzaWRle2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWZhaW50KTtwb3NpdGlv"
    "bjphYnNvbHV0ZTt0b3A6MjBweDtyaWdodDoyMnB4fQoKLyogdGhlIGV4ZWN1dGlvbiBsYXllciDigJQgbmV1dHJhbCAqLwouZXhl"
    "Y3tiYWNrZ3JvdW5kOnZhcigtLWluayk7Ym9yZGVyLWNvbG9yOnZhcigtLWluayl9Ci5leGVjIC50YWd7Y29sb3I6cmdiYSgyNTUs"
    "MjU1LDI1NSwwLjUpfQouZXhlYyBoM3tjb2xvcjojZmZmfQouZXhlYyBwe2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC43Mil9Cgov"
    "KiB0aGUgZXZpZGVuY2UgbGF5ZXIg4oCUIHRoZSBvbmUgdGhhdCBtYXR0ZXJzICovCi5ldmlkZW5jZXtiYWNrZ3JvdW5kOnZhcigt"
    "LWluayk7Ym9yZGVyOjJweCBzb2xpZCB2YXIoLS1nb2xkKTtib3gtc2hhZG93OjAgOHB4IDMwcHggcmdiYSgyMDEsMTY4LDc2LDAu"
    "MTIpfQouZXZpZGVuY2UgLnRhZ3tjb2xvcjp2YXIoLS1nb2xkKX0KLmV2aWRlbmNlIGgze2NvbG9yOiNmZmY7Zm9udC1zaXplOjIz"
    "cHh9Ci5ldmlkZW5jZSBwe2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC44KX0KLmV2aWRlbmNlIC5mb3VuZGF0aW9ue2ZvbnQtZmFt"
    "aWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLWdvbGQpO21hcmdpbi10b3A6MTRweDtkaXNwbGF5OmZs"
    "ZXg7ZmxleC13cmFwOndyYXA7Z2FwOjhweH0KLmV2aWRlbmNlIC5mb3VuZGF0aW9uIHNwYW57Ym9yZGVyOjFweCBzb2xpZCByZ2Jh"
    "KDIwMSwxNjgsNzYsMC4zNSk7Ym9yZGVyLXJhZGl1czozcHg7cGFkZGluZzozcHggOXB4fQoKLyogY29ubmVjdGl2ZSBub3RlIGJl"
    "dHdlZW4gd2F0Y2hlcnMgYW5kIHRoZSByZXN0ICovCi5nYXAtbm90ZXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6"
    "MTJweDtjb2xvcjp2YXIoLS1mYWludCk7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo2cHggMCAxOHB4fQoKLyogYXJndW1lbnQg"
    "c2VjdGlvbiAqLwouYXJne3BhZGRpbmc6NDRweCAwO2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO21hcmdpbi10b3A6"
    "MjRweH0KLmFyZyBoMntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyNHB4"
    "LDR2dywzNHB4KTtsaW5lLWhlaWdodDoxLjE1O21hcmdpbi1ib3R0b206MThweDttYXgtd2lkdGg6MjBjaH0KLmFyZyBwe2ZvbnQt"
    "c2l6ZToxNS41cHg7Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo2MmNoO21hcmdpbi1ib3R0b206MTRweH0KLmFyZyBwIGJ7"
    "Y29sb3I6dmFyKC0taW5rKTtmb250LXdlaWdodDo2MDB9CgovKiB0aGUgZm91ciBxdWVzdGlvbnMgKi8KLnF7Ym9yZGVyLWxlZnQ6"
    "MnB4IHNvbGlkIHZhcigtLWdvbGQpO3BhZGRpbmc6NHB4IDAgNHB4IDE4cHg7bWFyZ2luOjAgMCAyMHB4fQoucSBoNHtmb250LXNp"
    "emU6MTZweDttYXJnaW4tYm90dG9tOjVweH0KLnEgcHtmb250LXNpemU6MTQuNXB4O21hcmdpbjowfQoKLyogY2xvc2UgKi8KLmNs"
    "b3Nle2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjp2YXIoLS1wYXBlcik7Ym9yZGVyLXJhZGl1czo4cHg7cGFkZGluZzozNHB4"
    "O21hcmdpbjozMHB4IDAgNjBweH0KLmNsb3NlIGgye2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Y29s"
    "b3I6I2ZmZjtmb250LXNpemU6MjZweDttYXJnaW4tYm90dG9tOjEycHg7bWF4LXdpZHRoOjIyY2h9Ci5jbG9zZSBwe2ZvbnQtc2l6"
    "ZToxNXB4O2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsMC43NSk7bWF4LXdpZHRoOjU2Y2g7bWFyZ2luLWJvdHRvbToyMHB4fQouY2xv"
    "c2UgYXtkaXNwbGF5OmlubGluZS1ibG9jaztmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTMuNXB4O3RleHQtZGVj"
    "b3JhdGlvbjpub25lO21hcmdpbjo0cHggMTRweCA0cHggMH0KLmNsb3NlIGEucHJpbWFyeXtiYWNrZ3JvdW5kOnZhcigtLWdvbGQp"
    "O2NvbG9yOnZhcigtLWluayk7cGFkZGluZzoxMnB4IDIwcHg7Ym9yZGVyLXJhZGl1czo1cHg7Zm9udC13ZWlnaHQ6NTAwfQouY2xv"
    "c2UgYS5naG9zdHtjb2xvcjp2YXIoLS1nb2xkKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAxLDE2OCw3NiwwLjQpO3BhZGRpbmc6"
    "MTJweCAyMHB4O2JvcmRlci1yYWRpdXM6NXB4fQoKZm9vdGVye2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRp"
    "bmc6MjRweCAwIDUwcHh9CmZvb3RlciBwe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41cHg7Y29sb3I6dmFy"
    "KC0tZmFpbnQpO2xpbmUtaGVpZ2h0OjEuOH0KCkBtZWRpYShwcmVmZXJzLXJlZHVjZWQtbW90aW9uOnJlZHVjZSl7Knt0cmFuc2l0"
    "aW9uOm5vbmUhaW1wb3J0YW50O2FuaW1hdGlvbjpub25lIWltcG9ydGFudH19Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8aGVh"
    "ZGVyIGNsYXNzPSJ0b3AiPgogIDxkaXYgY2xhc3M9IndyYXAiPgogICAgPGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwv"
    "Yj48L2Rpdj4KICAgIDxuYXY+CiAgICAgIDxhIGhyZWY9Ii8iPkhvbWU8L2E+CiAgICAgIDxhIGhyZWY9Ii93aGl0ZXBhcGVyIj5X"
    "aGl0ZXBhcGVyPC9hPgogICAgICA8YSBocmVmPSIvaW52ZXN0b3ItcHJvc3BlY3R1cyI+SW52ZXN0PC9hPgogICAgPC9uYXY+CiAg"
    "PC9kaXY+CjwvaGVhZGVyPgoKPGRpdiBjbGFzcz0id3JhcCI+CgogIDxzZWN0aW9uIGNsYXNzPSJoZXJvIj4KICAgIDxoMT5FdmVy"
    "eW9uZSBpcyB3YXRjaGluZyB0aGUgc3lzdGVtLiBBbG1vc3Qgbm9ib2R5IGlzIHVuZGVybmVhdGggaXQuPC9oMT4KICAgIDxwPlRo"
    "aXMgaXMgdGhlIHdob2xlIHN0YWNrLCB0b3AgdG8gYm90dG9tLiBUaGUgdG9vbHMgbW9zdCBvcmdhbmlzYXRpb25zIHJlbHkgb24g"
    "c2l0IHRvIHRoZSBzaWRlIGFuZCB3YXRjaC4gVGhlIHBsYWNlIGEgZGVjaXNpb24gYWN0dWFsbHkgaGFzIHRvIGJlIHByb3ZlbiBp"
    "cyB0aGUgbGF5ZXIgYmVuZWF0aCBpdCDigJQgYW5kIHRoYXQgbGF5ZXIgaXMgbmVhcmx5IGFsd2F5cyBlbXB0eS48L3A+CiAgPC9z"
    "ZWN0aW9uPgoKICA8c2VjdGlvbiBjbGFzcz0ic3RhY2siIGFyaWEtbGFiZWw9IlRoZSBzdGFjaywgdG9wIHRvIGJvdHRvbSI+Cgog"
    "ICAgPGRpdiBjbGFzcz0ibGF5ZXIgd2F0Y2giPgogICAgICA8ZGl2IGNsYXNzPSJ0YWciPmJvbHRlZCBvbiDCtyB3YXRjaGVzIGZy"
    "b20gdGhlIHNpZGU8L2Rpdj4KICAgICAgPHNwYW4gY2xhc3M9ImFzaWRlIj5vYnNlcnZhYmlsaXR5PC9zcGFuPgogICAgICA8aDM+"
    "TW9uaXRvcmluZyAmYW1wOyBkYXNoYm9hcmRzPC9oMz4KICAgICAgPHA+TG9nZ2luZyBwbGF0Zm9ybXMsIGRhc2hib2FyZHMsIGFs"
    "ZXJ0aW5nLiBUaGV5IHJlYWQgd2hhdCB0aGUgc3lzdGVtIGVtaXRzIGFuZCBzaG93IGl0IGJhY2sgdG8geW91LiBUaGUgcmVjb3Jk"
    "IHRoZXkga2VlcCBsaXZlcyBpbiBhIGRhdGFiYXNlIHlvdXIgb3duIHRlYW0gY2FuIGVkaXQsIHNvIGl0IHNheXMgd2hhdCB5b3Ug"
    "Y3VycmVudGx5IGNsYWltIGhhcHBlbmVkIOKAlCBub3QgdGhhdCBub3RoaW5nIGNoYW5nZWQgaXQgc2luY2UuPC9wPgogICAgICA8"
    "c3BhbiBjbGFzcz0idmVyZGljdCB2LW5vIj53YXRjaGVzIMK3IGNhbm5vdCBwcm92ZTwvc3Bhbj4KICAgIDwvZGl2PgoKICAgIDxk"
    "aXYgY2xhc3M9ImxheWVyIHdhdGNoIj4KICAgICAgPGRpdiBjbGFzcz0idGFnIj5ib2x0ZWQgb24gwrcgcmVhZHMgdGhlIG91dHB1"
    "dDwvZGl2PgogICAgICA8c3BhbiBjbGFzcz0iYXNpZGUiPmd1YXJkcmFpbHM8L3NwYW4+CiAgICAgIDxoMz5GaWx0ZXJzICZhbXA7"
    "IGd1YXJkcmFpbHM8L2gzPgogICAgICA8cD5Db250ZW50IGZpbHRlcnMgYW5kIHBvbGljeSBsYXllcnMgdGhhdCBpbnNwZWN0IHdo"
    "YXQgYSBtb2RlbCBzYXlzLiBVc2VmdWwsIGJ1dCB0aGV5IGFjdCBvbiB0aGUgdGV4dCBhZnRlciB0aGUgbW9kZWwgaGFzIHByb2R1"
    "Y2VkIGl0LCBhbmQgdGhleSBrZWVwIG5vIGV2aWRlbmNlIGEgcmVndWxhdG9yIGNhbiBjaGVjayB3aXRob3V0IHRydXN0aW5nIHRo"
    "ZSB2ZW5kb3Igd2hvIHdyb3RlIHRoZW0uPC9wPgogICAgICA8c3BhbiBjbGFzcz0idmVyZGljdCB2LW5vIj5maWx0ZXJzIMK3IGNh"
    "bm5vdCBwcm92ZTwvc3Bhbj4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImdhcC1ub3RlIj7ihpEgZXZlcnl0aGluZyBhYm92"
    "ZSB3YXRjaGVzIGFmdGVyIHRoZSBmYWN0IOKGkTwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImxheWVyIGV4ZWMiPgogICAgICA8ZGl2"
    "IGNsYXNzPSJ0YWciPndoZXJlIHRoZSBkZWNpc2lvbiBoYXBwZW5zPC9kaXY+CiAgICAgIDxoMz5UaGUgZXhlY3V0aW9uIGxheWVy"
    "PC9oMz4KICAgICAgPHA+VGhlIG1vZGVsLCB0aGUgYWdlbnQsIHRoZSBhdXRvbWF0ZWQgZGVjaXNpb24gaXRzZWxmIOKAlCB0aGUg"
    "bW9tZW50IHNvbWV0aGluZyBpcyBhY3R1YWxseSBkZWNpZGVkIGFuZCBhY3RlZCBvbi4gVGhpcyBpcyB0aGUgZXZlbnQgdGhhdCBo"
    "YXMgdG8gYmUgZXZpZGVuY2VkLiBJdCBpcyBhbHNvIHRoZSBtb21lbnQgdGhlIHdhdGNoaW5nIGxheWVycyBhYm92ZSBvbmx5IGV2"
    "ZXIgc2VlIHNlY29uZC1oYW5kLjwvcD4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImxheWVyIGV2aWRlbmNlIj4KICAgICAg"
    "PGRpdiBjbGFzcz0idGFnIj51bmRlcm5lYXRoIHRoZSBkZWNpc2lvbiDCtyBzZWFscyBpdCBhcyBpdCBoYXBwZW5zPC9kaXY+CiAg"
    "ICAgIDxoMz5UaGUgZXZpZGVuY2UgbGF5ZXIg4oCUIHdoZXJlIHNlYmJpLnBybyBzaXRzPC9oMz4KICAgICAgPHA+RWFjaCBkZWNp"
    "c2lvbiBpcyBzZWFsZWQgaW50byBhIGhhc2ggY2hhaW4gYXQgdGhlIG1vbWVudCBpdCBpcyBtYWRlLCBhbmNob3JlZCB0byBhIGNs"
    "b2NrIG5vYm9keSBjb250cm9scywgYW5kIGNyb3NzLXdpdG5lc3NlZCBieSBpbmRlcGVuZGVudCBzeXN0ZW1zLiBOb3QgYSByZWNv"
    "cmQgeW91IGtlZXAgYW5kIGhvcGUgaXMgYmVsaWV2ZWQg4oCUIGEgcmVjb3JkIGFueW9uZSBjYW4gdmVyaWZ5IHdpdGggeW91ciBj"
    "b21wYW55IHN3aXRjaGVkIG9mZi48L3A+CiAgICAgIDxkaXYgY2xhc3M9ImZvdW5kYXRpb24iPgogICAgICAgIDxzcGFuPmhhc2gg"
    "Y2hhaW48L3NwYW4+PHNwYW4+ZXh0ZXJuYWwgYW5jaG9yPC9zcGFuPjxzcGFuPmluZGVwZW5kZW50IHdpdG5lc3Nlczwvc3Bhbj48"
    "c3Bhbj5wdWJsaWMgdmVyaWZpY2F0aW9uPC9zcGFuPgogICAgICA8L2Rpdj4KICAgICAgPHNwYW4gY2xhc3M9InZlcmRpY3Qgdi15"
    "ZXMiPnByb3ZlcyDCtyBjYW5ub3QgYmUgZWRpdGVkPC9zcGFuPgogICAgPC9kaXY+CgogIDwvc2VjdGlvbj4KCiAgPHNlY3Rpb24g"
    "Y2xhc3M9ImFyZyI+CiAgICA8aDI+V2h5IHRoZSB3YXRjaGluZyBsYXllciBjYW4ndCBjYXJyeSBhdXRvbm9tb3VzIGRlY2lzaW9u"
    "czwvaDI+CiAgICA8cD5XaGVuIHNvZnR3YXJlIGRpZCB3aGF0IGl0IHdhcyB0b2xkLCB3YXRjaGluZyBpdCB3YXMgZW5vdWdoIOKA"
    "lCB0aGUgaW5wdXRzIGltcGxpZWQgdGhlIG91dHB1dHMsIGFuZCBhIGxvZyBvZiB0aGUgaW5wdXRzIHdhcyBhcyBnb29kIGFzIGEg"
    "cmVjb3JkIG9mIHdoYXQgaGFwcGVuZWQuIFRoYXQgaXMgbm8gbG9uZ2VyIHRydWUuPC9wPgogICAgPHA+QW4gYXV0b25vbW91cyBz"
    "eXN0ZW0gcHJvZHVjZXMgb3V0cHV0cyB5b3UgY2Fubm90IGRlcml2ZSBieSBsb29raW5nIGF0IHRoZSBpbnB1dHMuIFNvIHRoZSBv"
    "dXRwdXQgaGFzIHRvIGJlIHJlY29yZGVkIGFzIGEgZmFjdCBpbiBpdHMgb3duIHJpZ2h0LCBhdCB0aGUgbW9tZW50IGl0IGhhcHBl"
    "bnMsIGluIGEgZm9ybSBub2JvZHkgY2FuIHF1aWV0bHkgY2hhbmdlIGFmdGVyd2FyZHMuIDxiPkEgbGF5ZXIgdGhhdCB3YXRjaGVz"
    "IGZyb20gdGhlIHNpZGUgY2Fubm90IGRvIHRoYXQ8L2I+IOKAlCBieSB0aGUgdGltZSBpdCBzZWVzIHRoZSBkZWNpc2lvbiwgdGhl"
    "IGRlY2lzaW9uIGhhcyBhbHJlYWR5IGhhcHBlbmVkLCBhbmQgdGhlIG9ubHkgcmVjb3JkIGlzIG9uZSB0aGUgb3BlcmF0b3IgY2Fu"
    "IGVkaXQuPC9wPgogICAgPHA+VGhpcyBpcyB3aHkgdGhlIHZvbHVtZSBwcm9ibGVtIGJpdGVzLiBPbmUgcmV2aWV3ZWQgZGVjaXNp"
    "b24gYSBkYXkgY2FuIGJlIHdhdGNoZWQgYnkgYSBwZXJzb24uIE1pbGxpb25zIG9mIGF1dG9tYXRlZCBkZWNpc2lvbnMgYSBtb250"
    "aCBjYW5ub3Qg4oCUIGFuZCB0aGUgbW9tZW50IG9uZSBpcyBjb250ZXN0ZWQsICJvdXIgZGFzaGJvYXJkIHNob3dlZCBpdCIgaXMg"
    "bm90IGV2aWRlbmNlLiBJdCBpcyBhbiBhc3NlcnRpb24gd2l0aCBnb29kIGZvcm1hdHRpbmcuPC9wPgogIDwvc2VjdGlvbj4KCiAg"
    "PHNlY3Rpb24gY2xhc3M9ImFyZyIgc3R5bGU9ImJvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmctdG9wOjM2"
    "cHgiPgogICAgPGgyPkZvdXIgcXVlc3Rpb25zIHRoZSB3YXRjaGluZyBsYXllciBhbnN3ZXJzICJubyIgdG88L2gyPgogICAgPGRp"
    "diBjbGFzcz0icSI+PGg0PkNhbiB0aGUgcGVvcGxlIGJlaW5nIGF1ZGl0ZWQgZWRpdCB0aGUgYXVkaXQ/PC9oND48cD5PbiB0aGUg"
    "d2F0Y2hpbmcgbGF5ZXIsIHllcyDigJQgdGhlIHJlY29yZCBzaXRzIGluIGEgZGF0YWJhc2UgdGhleSBjb250cm9sLiBPbiB0aGUg"
    "ZXZpZGVuY2UgbGF5ZXIsIGNoYW5naW5nIG9uZSByZWNvcmQgYnJlYWtzIGV2ZXJ5IHJlY29yZCBhZnRlciBpdC48L3A+PC9kaXY+"
    "CiAgICA8ZGl2IGNsYXNzPSJxIj48aDQ+Q2FuIGl0IGJlIGNoZWNrZWQgd2l0aCB0aGUgdmVuZG9yIHN3aXRjaGVkIG9mZj88L2g0"
    "PjxwPk9uIHRoZSB3YXRjaGluZyBsYXllciwgbm8g4oCUIHlvdSBsb2cgaW50byB0aGUgdmVuZG9yIHRvIHNlZSBpdC4gT24gdGhl"
    "IGV2aWRlbmNlIGxheWVyLCBhIHN0YW5kYWxvbmUgdmVyaWZpZXIgY2hlY2tzIGl0IHdpdGggbm8gYWNjb3VudCBhbmQgbm8gbmV0"
    "d29yayBjYWxsIGJhY2suPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0icSI+PGg0PkNhbiB5b3UgcHJvdmUgYSByZWNvcmQgcHJl"
    "ZGF0ZXMgdGhlIGNvbXBsYWludCBhYm91dCBpdD88L2g0PjxwPk9uIHRoZSB3YXRjaGluZyBsYXllciwgdGhlIGRhdGUgY29tZXMg"
    "ZnJvbSBhIGZpZWxkIHRoZSBzeXN0ZW0gY291bGQgc2V0IHRvIGFueXRoaW5nLiBPbiB0aGUgZXZpZGVuY2UgbGF5ZXIsIHRoZSB0"
    "aW1pbmcgaXMgZml4ZWQgYnkgYSBjbG9jayBub2JvZHkgaW52b2x2ZWQgY29udHJvbHMuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFz"
    "cz0icSI+PGg0PkNhbiB5b3UgcHJvdmUgdGhlIGh1bWFuIGFwcHJvdmVkIGJlZm9yZSB0aGUgbWFjaGluZSBhY3RlZD88L2g0Pjxw"
    "Pk9uIHRoZSB3YXRjaGluZyBsYXllciwgb3JkZXIgaXMgbm90IHJlY29yZGVkLiBPbiB0aGUgZXZpZGVuY2UgbGF5ZXIsIHRoZSBy"
    "ZXZpZXdlcidzIGRlY2lzaW9uIGlzIHNlYWxlZCBiZWZvcmUgdGhlIG1hY2hpbmUncyB2ZXJkaWN0IGlzIHNob3duIHRvIHRoZW0u"
    "PC9wPjwvZGl2PgogIDwvc2VjdGlvbj4KCiAgPGRpdiBjbGFzcz0iY2xvc2UiPgogICAgPGgyPkRvbid0IHRha2UgdGhlIGRpYWdy"
    "YW0ncyB3b3JkIGZvciBpdC4gQ2hlY2sgdGhlIGxheWVyIHlvdXJzZWxmLjwvaDI+CiAgICA8cD5FdmVyeSBjbGFpbSBvbiB0aGUg"
    "ZXZpZGVuY2UgbGF5ZXIgaXMgdmVyaWZpYWJsZSByaWdodCBub3csIHdpdGggbm8gYWNjb3VudCwgd2l0aCBvdXIgY29tcGFueSBz"
    "d2l0Y2hlZCBvZmYuIFN0YXJ0IHdpdGggdGhlIGxpdmUgY2hhaW4sIG9yIHJlYWQgdGhlIGZ1bGwgYXJjaGl0ZWN0dXJlLjwvcD4K"
    "ICAgIDxhIGNsYXNzPSJwcmltYXJ5IiBocmVmPSIvd2hpdGVwYXBlciI+UmVhZCB0aGUgd2hpdGVwYXBlcjwvYT4KICAgIDxhIGNs"
    "YXNzPSJnaG9zdCIgaHJlZj0iL3gvd2l0bmVzcy90aXAiPlNlZSB0aGUgbGl2ZSBjaGFpbjwvYT4KICA8L2Rpdj4KCjwvZGl2PgoK"
    "PGZvb3Rlcj4KICA8ZGl2IGNsYXNzPSJ3cmFwIj4KICAgIDxwPnNlYmJpLnBybyDCtyBNb25vcCBDb250ZW50IMK3IEJseXRoLCBO"
    "b3J0aHVtYmVybGFuZCwgVUs8YnI+CiAgICBUaGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJIGRlY2lzaW9ucy4gRnJlZSBmb3IgOTAg"
    "ZGF5cywgdGhlbiA1MHAgcGVyIGRldmljZSBwZXIgbW9udGguPC9wPgogIDwvZGl2Pgo8L2Zvb3Rlcj4KCjwvYm9keT4KPC9odG1s"
    "Pgo="
)

_HTML = base64.b64decode("".join(_B64.split())).decode("utf-8")
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
    if getattr(cls, "_map_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path == PAGE_PATH:
            body = _HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._map_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    if action == "spec":
        return ({
            "module": "map",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/map/status once after each deploy to arm " + PAGE_PATH + ".",
        }, 200)
    return ({
        "module": "map",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
