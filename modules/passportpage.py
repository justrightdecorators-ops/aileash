"""
modules/passportpage.py  v1.0.0
Serves the Agent Passport page at /passport.

Page module, same family as map.py / console.py / network.py: a runtime
do_GET patch puts a full HTML page at a clean URL. Armed by hitting
/x/passportpage/status once after each deploy. server.py is never edited.
The page is base64-embedded so no character in the HTML can break the
Python string. The live demo on the page calls /x/passport/demo.
"""

import base64
import sys

VERSION = "1.0.0"
PAGE_PATH = "/passport"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIi"
    "Pgo8dGl0bGU+QWdlbnQgUGFzc3BvcnQg4oCUIHNlYmJpLnBybzwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBjb250"
    "ZW50PSJFdmVyeSBBSSBhZ2VudCBuZWVkcyBhIHBhc3Nwb3J0LiBTaWduZWQsIHNpbmdsZS11c2UgcGVybWlzc2lvbiBmb3IgQUkg"
    "YWN0aW9ucywgY2hlY2tlZCBhdCB0aGUgbW9tZW50IG9mIGFjdGlvbiwgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluLiI+CjxsaW5r"
    "IHJlbD0icHJlY29ubmVjdCIgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbSI+CjxsaW5rIGhyZWY9Imh0dHBzOi8v"
    "Zm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNDAwOzYuLjcyLDUwMCZm"
    "YW1pbHk9SUJNK1BsZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMCZkaXNw"
    "bGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzBhMGYxZTstLWluazI6IzEwMTgyZTstLXBh"
    "cGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7LS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0tb2tiZzojRTRFQ0U4Oy0td2Fy"
    "bjojOUMyRjI2Oy0td2FybmJnOiNGNUU2RTM7LS1tdXRlZDojNUE2MjcwOy0tZmFpbnQ6IzhBOTBBMDsKLS1zYW5zOidJQk0gUGxl"
    "eCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidOZXdzcmVhZGVyJyxHZW9yZ2lhLHNlcmlmOy0tbW9ubzonSUJN"
    "IFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZX0KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGlu"
    "ZzowfQpib2R5e2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2JhY2tncm91bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7"
    "bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50aWFsaWFzZWR9Ci53cmFwe21heC13aWR0aDo4MjBweDtt"
    "YXJnaW46MCBhdXRvO3BhZGRpbmc6MCAyMnB4fQoudG9we2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRp"
    "bmc6MTZweCAwfQoudG9wIC53cmFwe2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVt"
    "czpiYXNlbGluZTtnYXA6MTJweDtmbGV4LXdyYXA6d3JhcH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6"
    "ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBuYXYgYXtmb250LWZhbWlseTp2"
    "YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LWRlY29yYXRpb246bm9uZTttYXJnaW4t"
    "bGVmdDoxNHB4fQouaGVyb3twYWRkaW5nOjU0cHggMCAyNnB4fQoua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNp"
    "emU6MTJweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDZlbTttYXJnaW4tYm90dG9tOjE0cHh9Ci5oZXJvIGgx"
    "e2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNnZ3LDU2cHgpO2xp"
    "bmUtaGVpZ2h0OjEuMDU7bWF4LXdpZHRoOjE1Y2g7bWFyZ2luLWJvdHRvbToxOHB4fQouaGVybyBwe2ZvbnQtc2l6ZToxNy41cHg7"
    "Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo1NmNofQouY3Rhe2Rpc3BsYXk6aW5saW5lLWJsb2NrO21hcmdpbjoyNnB4IDEy"
    "cHggMCAwO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxNHB4O3RleHQtZGVjb3JhdGlvbjpub25lO2JvcmRlci1y"
    "YWRpdXM6NXB4O3BhZGRpbmc6MTNweCAyMHB4O2N1cnNvcjpwb2ludGVyO2JvcmRlcjowfQouY3RhLmdvbGR7YmFja2dyb3VuZDp2"
    "YXIoLS1nb2xkKTtjb2xvcjp2YXIoLS1pbmspO2ZvbnQtd2VpZ2h0OjUwMH0KLmN0YS5naG9zdHtib3JkZXI6MXB4IHNvbGlkIHZh"
    "cigtLWxpbmUpO2NvbG9yOnZhcigtLWluayk7YmFja2dyb3VuZDojZmZmfQouc3RhdHN7ZGlzcGxheTpmbGV4O2dhcDoyMnB4O2Zs"
    "ZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6MzBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2"
    "YXIoLS1mYWludCl9Ci5zdGF0cyBie2NvbG9yOnZhcigtLWluayk7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToxNXB4O2Rpc3Bs"
    "YXk6YmxvY2t9CnNlY3Rpb257cGFkZGluZzo0MHB4IDA7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tbGluZSl9Cmgye2ZvbnQt"
    "ZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDI2cHgsNC4ydncsMzZweCk7bGluZS1o"
    "ZWlnaHQ6MS4xMjttYXJnaW4tYm90dG9tOjE0cHg7bWF4LXdpZHRoOjIyY2h9Ci5sZWFke2NvbG9yOnZhcigtLW11dGVkKTttYXgt"
    "d2lkdGg6NjBjaDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGVwc3tkaXNwbGF5OmdyaWQ7Z2FwOjE0cHh9Ci5zdGVwe2JhY2tncm91"
    "bmQ6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6N3B4O3BhZGRpbmc6MjBweCAyMnB4fQou"
    "c3RlcCAubntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3Bh"
    "Y2luZzouMDVlbX0KLnN0ZXAgaDN7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MjFw"
    "eDttYXJnaW46NHB4IDAgNnB4fQouc3RlcCBwe2ZvbnQtc2l6ZToxNC44cHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQouZGFya3tiYWNr"
    "Z3JvdW5kOnZhcigtLWluayk7Y29sb3I6I2ZmZjtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzozMHB4IDI0cHg7Ym9yZGVyOjJw"
    "eCBzb2xpZCB2YXIoLS1nb2xkKX0KLmRhcmsgaDJ7Y29sb3I6I2ZmZn0uZGFyayAubGVhZHtjb2xvcjpyZ2JhKDI1NSwyNTUsMjU1"
    "LC43Mil9CiNzdG9yeXttYXJnaW4tdG9wOjE4cHg7ZGlzcGxheTpncmlkO2dhcDo4cHh9Ci5yb3d7ZGlzcGxheTpmbGV4O2dhcDox"
    "MnB4O2FsaWduLWl0ZW1zOmZsZXgtc3RhcnQ7YmFja2dyb3VuZDp2YXIoLS1pbmsyKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAx"
    "LDE2OCw3NiwuMTgpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxNHB4O2ZvbnQtc2l6ZToxNHB4O29wYWNpdHk6MDt0"
    "cmFuc2Zvcm06dHJhbnNsYXRlWSg2cHgpO3RyYW5zaXRpb246YWxsIC4zNXN9Ci5yb3cuc2hvd3tvcGFjaXR5OjE7dHJhbnNmb3Jt"
    "Om5vbmV9Ci5yb3cgLmlje2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O21pbi13aWR0aDo2NnB4O3RleHQt"
    "YWxpZ246Y2VudGVyO3BhZGRpbmc6MnB4IDZweDtib3JkZXItcmFkaXVzOjNweH0KLmljLnBhc3N7YmFja2dyb3VuZDojMTczOTJh"
    "O2NvbG9yOiM3ZmUzYjB9LmljLnN0b3B7YmFja2dyb3VuZDojM2QxYTE3O2NvbG9yOiNmZjhhODB9LmljLmluZm97YmFja2dyb3Vu"
    "ZDojMmEyYTFhO2NvbG9yOnZhcigtLWdvbGQpfQoucm93IC53aHl7ZGlzcGxheTpibG9jaztmb250LWZhbWlseTp2YXIoLS1tb25v"
    "KTtmb250LXNpemU6MTEuNXB4O2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsLjUpO21hcmdpbi10b3A6M3B4O3dvcmQtYnJlYWs6YnJl"
    "YWstd29yZH0KI3ZlcmRpY3R7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0tZ29sZCk7"
    "bWFyZ2luLXRvcDoxNnB4O21pbi1oZWlnaHQ6MjBweH0KLnJ1bntiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOnZhcigtLWlu"
    "ayl9Ci5ncmlkMntkaXNwbGF5OmdyaWQ7Z2FwOjE0cHg7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn0KQG1lZGlhKG1pbi13aWR0"
    "aDo3MDBweCl7LmdyaWQye2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyfX0KLmNhcmR7YmFja2dyb3VuZDojZmZmO2JvcmRl"
    "cjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo3cHg7cGFkZGluZzoyMHB4IDIycHh9Ci5jYXJkIC50YWd7Zm9u"
    "dC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tZmFpbnQpO2xldHRlci1zcGFjaW5nOi4wNWVt"
    "fQouY2FyZCBoM3tmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyMHB4O21hcmdpbjo0"
    "cHggMCA2cHh9Ci5jYXJkIHB7Zm9udC1zaXplOjE0LjVweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbToxMHB4fQou"
    "Y2FyZCBhe2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMi41cHg7Y29sb3I6dmFyKC0taW5rKTt3b3JkLWJyZWFr"
    "OmJyZWFrLWFsbH0KcHJle2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZThlNmRmO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8p"
    "O2ZvbnQtc2l6ZToxMnB4O2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTRweDtvdmVyZmxvdy14OmF1dG87bWFyZ2luLXRvcDo4"
    "cHh9Ci5jbG9zZXtiYWNrZ3JvdW5kOnZhcigtLWluayk7Y29sb3I6I2ZmZjtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzozMnB4"
    "IDI0cHg7bWFyZ2luOjM2cHggMCA1MHB4fQouY2xvc2UgaDJ7Y29sb3I6I2ZmZn0uY2xvc2UgcHtjb2xvcjpyZ2JhKDI1NSwyNTUs"
    "MjU1LC43NSk7bWF4LXdpZHRoOjU2Y2h9CmZvb3Rlcntib3JkZXItdG9wOjFweCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjIy"
    "cHggMCA0NnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMS41cHg7Y29sb3I6dmFyKC0tZmFpbnQpfQpAbWVk"
    "aWEocHJlZmVycy1yZWR1Y2VkLW1vdGlvbjpyZWR1Y2Upeyp7dHJhbnNpdGlvbjpub25lIWltcG9ydGFudH19Cjwvc3R5bGU+Cjwv"
    "aGVhZD4KPGJvZHk+CjxoZWFkZXIgY2xhc3M9InRvcCI+PGRpdiBjbGFzcz0id3JhcCI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJp"
    "PGI+LnBybzwvYj48L2Rpdj4KPG5hdj48YSBocmVmPSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9tYXAiPk1hcDwvYT48YSBocmVmPSIv"
    "d2hpdGVwYXBlciI+V2hpdGVwYXBlcjwvYT48L25hdj48L2Rpdj48L2hlYWRlcj4KCjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNs"
    "YXNzPSJoZXJvIj4KICA8ZGl2IGNsYXNzPSJraWNrIj5BR0VOVCBQQVNTUE9SVDwvZGl2PgogIDxoMT5FdmVyeSBBSSBhZ2VudCBu"
    "b3cgbmVlZHMgYSBwYXNzcG9ydC48L2gxPgogIDxwPkFJIGFnZW50cyBwYXksIGJvb2ssIHNlbmQgYW5kIGNoYW5nZSByZWNvcmRz"
    "IG9uIHRoZWlyIG93bi4gVGhlIEFnZW50IFBhc3Nwb3J0IGxldHMgYW55IHNpdGUga25vdywgaW4gbWlsbGlzZWNvbmRzLCB0aGF0"
    "IGEgcmVhbCBwZXJzb24gYXV0aG9yaXNlZCB0aGUgYWN0aW9uLCB0aGF0IHRoZSBhdXRob3JpdHkgc3RpbGwgc3RhbmRzIHJpZ2h0"
    "IG5vdywgYW5kIHRoYXQgaXQgY2FuIGhhcHBlbiBleGFjdGx5IG9uY2UuPC9wPgogIDxidXR0b24gY2xhc3M9ImN0YSBnb2xkIiBv"
    "bmNsaWNrPSJydW5EZW1vKCkiPlJ1biBpdCBsaXZlPC9idXR0b24+CiAgPGEgY2xhc3M9ImN0YSBnaG9zdCIgaHJlZj0iI3NpdGVz"
    "Ij5SZXF1aXJlIGl0IG9uIHlvdXIgc2l0ZTwvYT4KICA8ZGl2IGNsYXNzPSJzdGF0cyI+PGRpdj48YiBpZD0icy1pc3N1ZWQiPuKA"
    "lDwvYj5wYXNzcG9ydHMgaXNzdWVkPC9kaXY+PGRpdj48YiBpZD0icy1yZWQiPuKAlDwvYj5yZWRlZW1lZDwvZGl2PjxkaXY+PGIg"
    "aWQ9InMtcmVmIj7igJQ8L2I+cmVmdXNlZCBhbmQgc2VhbGVkPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNlY3Rpb24+CiAgPGgyPlRo"
    "cmVlIHN0ZXBzLiBObyB0cnVzdCByZXF1aXJlZC48L2gyPgogIDxkaXYgY2xhc3M9InN0ZXBzIj4KICAgIDxkaXYgY2xhc3M9InN0"
    "ZXAiPjxkaXYgY2xhc3M9Im4iPjAxIMK3IFRIRSBBR0VOVCBBU0tTPC9kaXY+PGgzPkF1dGhvcml0eSB0cmFjZWQgYmFjayB0byBh"
    "IGh1bWFuPC9oMz48cD5CZWZvcmUgYWN0aW5nLCB0aGUgYWdlbnQgYXNrcyBzZWJiaS5wcm8uIFRoZSBhdXRob3JpdHkgaXMgd2Fs"
    "a2VkIGJhY2sgdG8gdGhlIHBlcnNvbiB3aG8gZ3JhbnRlZCBpdCwgZXZlcnkgbGluayBjaGVja2VkLCBhbmQgYSBzaWduZWQgcGFz"
    "c3BvcnQgaXNzdWVkIGZvciBvbmUgYWN0aW9uLCBhdCBvbmUgc2l0ZSwgZm9yIG9uZSBhbW91bnQsIGZvciBtaW51dGVzLjwvcD48"
    "L2Rpdj4KICAgIDxkaXYgY2xhc3M9InN0ZXAiPjxkaXYgY2xhc3M9Im4iPjAyIMK3IFRIRSBTSVRFIENIRUNLUzwvZGl2PjxoMz5W"
    "ZXJpZmllZCBpbiBtaWxsaXNlY29uZHMsIG9mZmxpbmU8L2gzPjxwPlRoZSBzaXRlIGNoZWNrcyB0aGUgc2lnbmF0dXJlIHdpdGgg"
    "YSBzdGFuZGFyZCBsaWJyYXJ5IGluIGFueSBsYW5ndWFnZS4gTm90aGluZyB0byBpbnN0YWxsLCBubyBhY2NvdW50LCBubyBjYWxs"
    "IGhvbWUuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+MDMgwrcgVEhFIEFDVElPTiBCSU5E"
    "UzwvZGl2PjxoMz5SZS1jaGVja2VkIGF0IHRoZSBtb21lbnQgaXQgaGFwcGVuczwvaDM+PHA+VGhlIHNpdGUgcmVkZWVtcyB0aGUg"
    "cGFzc3BvcnQuIFJpZ2h0IHRoZW4sIHNlYmJpLnBybyBjb25maXJtcyB0aGUgaHVtYW4ncyBhdXRob3JpdHkgc3RpbGwgc3RhbmRz"
    "LCB0aGUgYW1vdW50IG1hdGNoZXMsIGFuZCBpdCBoYXMgbmV2ZXIgYmVlbiB1c2VkLiBUaGVuIGl0IGJpbmRzLCBvbmNlLCBhbmQg"
    "dGhlIG91dGNvbWUgaXMgc2VhbGVkLjwvcD48L2Rpdj4KICA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gc3R5bGU9ImJvcmRl"
    "ci10b3A6MCI+CjxkaXYgY2xhc3M9ImRhcmsiPgogIDxoMj5XYXRjaCBpdCBydW4gb24gcHJvZHVjdGlvbi48L2gyPgogIDxwIGNs"
    "YXNzPSJsZWFkIj5PbmUgdGFwIHJ1bnMgdGhlIHdob2xlIHN0b3J5IGxpdmU6IGEgcmVhbCBncmFudCwgcmVhbCBwYXNzcG9ydHMs"
    "IHJlYWwgcmVkZW1wdGlvbnMgYW5kIHJlYWwgcmVmdXNhbHMsIGVhY2ggc2VhbGVkIGludG8gdGhlIHB1YmxpYyBjaGFpbi48L3A+"
    "CiAgPGJ1dHRvbiBjbGFzcz0iY3RhIHJ1biIgaWQ9InJ1bmJ0biIgb25jbGljaz0icnVuRGVtbygpIj5SdW4gdGhlIGxpdmUgZGVt"
    "bzwvYnV0dG9uPgogIDxkaXYgaWQ9InN0b3J5Ij48L2Rpdj4KICA8ZGl2IGlkPSJ2ZXJkaWN0Ij48L2Rpdj4KPC9kaXY+Cjwvc2Vj"
    "dGlvbj4KCjxzZWN0aW9uPgogIDxoMj5XaGF0IGEgcGFzc3BvcnQgcmVmdXNlczwvaDI+CiAgPHAgY2xhc3M9ImxlYWQiPkEgc3Rv"
    "bGVuLCByZXBsYXllZCwgcmUtYWltZWQgb3IgZWRpdGVkIHBhc3Nwb3J0IGlzIHdvcnRobGVzcy4gRXZlcnkgcmVmdXNhbCBpcyB3"
    "cml0dGVuIHRvIHRoZSBjaGFpbiwgc28gYW4gYWdlbnQgY2FuIGV2ZW4gcHJvdmUgaXQgd2FzIDxiPm5vdDwvYj4gYWxsb3dlZC48"
    "L3A+CiAgPGRpdiBjbGFzcz0ic3RlcHMiPgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+UkVQTEFZPC9kaXY+"
    "PHA+U3BlbnQgb25jZS4gVGhlIHNlY29uZCBhdHRlbXB0IGlzIHJlZnVzZWQuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3Rl"
    "cCI+PGRpdiBjbGFzcz0ibiI+UkVWT0tFRCBBIFNFQ09ORCBBR088L2Rpdj48cD5TdGlsbCBzaWduZWQsIHN0aWxsIGluIGRhdGUs"
    "IGFuZCBzdGlsbCByZWZ1c2VkLCBiZWNhdXNlIHRoZSBodW1hbiBwdWxsZWQgdGhlIGF1dGhvcml0eS48L3A+PC9kaXY+CiAgICA8"
    "ZGl2IGNsYXNzPSJzdGVwIj48ZGl2IGNsYXNzPSJuIj5XUk9ORyBTSVRFPC9kaXY+PHA+QSBwYXNzcG9ydCBpcyBvbmx5IGdvb2Qg"
    "d2hlcmUgaXQgd2FzIGlzc3VlZCBmb3IuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+RURJ"
    "VEVEIEFNT1VOVDwvZGl2PjxwPkF1dGhvcmlzZWQgZm9yIDIwLCBwcmVzZW50ZWQgZm9yIDQ5LiBSZWZ1c2VkLjwvcD48L2Rpdj4K"
    "ICA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9InNpdGVzIj4KICA8aDI+QnVpbHQgZm9yIGJvdGggc2lkZXMgb2YgdGhl"
    "IGFjdGlvbjwvaDI+CiAgPGRpdiBjbGFzcz0iZ3JpZDIiPgogICAgPGRpdiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idGFnIj5G"
    "T1IgV0VCU0lURVMgJmFtcDsgQVBJUzwvZGl2PjxoMz5SZXF1aXJlIGl0IHdpdGggb25lIGZpbGU8L2gzPjxwPkhvc3Qgb25lIHNt"
    "YWxsIGZpbGUgYW5kIGV2ZXJ5IGFnZW50IGtub3dzIHdoaWNoIGFjdGlvbnMgbmVlZCBhIHBhc3Nwb3J0LiBObyBwYXNzcG9ydCwg"
    "bm8gYWN0aW9uLjwvcD4KICAgICAgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9zaXRlZmlsZT9kb21haW49"
    "eW91ci5zaXRlJnJlcXVpcmU9cGF5bWVudHMuKiI+R2VuZXJhdGUgeW91ciBmaWxlPC9hPjwvZGl2PgogICAgPGRpdiBjbGFzcz0i"
    "Y2FyZCI+PGRpdiBjbGFzcz0idGFnIj5GT1IgQUkgQUdFTlRTPC9kaXY+PGgzPkEgdG9vbCwgdGhyb3VnaCBNQ1A8L2gzPjxwPkFn"
    "ZW50cyByZXF1ZXN0LCBjaGVjayBhbmQgcmVkZWVtIHBhc3Nwb3J0cyBhcyB0b29scy4gV29ya3Mgd2l0aCBldmVyeSBtb2RlbCBm"
    "cm9tIGV2ZXJ5IHZlbmRvci48L3A+CiAgICAgIDxhIGhyZWY9Imh0dHBzOi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvbWNwIj5odHRw"
    "czovL3NlYmJpLnByby94L3Bhc3Nwb3J0L21jcDwvYT48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRh"
    "ZyI+Rk9SIENPTVBMSUFOQ0U8L2Rpdj48aDM+UHJvb2YsIG5vdCBsb2dzPC9oMz48cD5XaG8gYXV0aG9yaXNlZCBpdCwgd2hvIGFj"
    "dGVkLCB3aG8gYWNjZXB0cyB0aGUgcmlzaywgYW5kIHdoZXRoZXIgaXQgc3RpbGwgc3Rvb2QgYXQgdGhhdCBpbnN0YW50LiBTZWFs"
    "ZWQsIGFuY2hvcmVkIHRvIEJpdGNvaW4sIHdpdG5lc3NlZCBpbmRlcGVuZGVudGx5LjwvcD4KICAgICAgPGEgaHJlZj0iaHR0cHM6"
    "Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L2RlY2lzaW9ucyI+U2VlIHJlYWwgc2VhbGVkIGRlY2lzaW9uczwvYT48L2Rpdj4KICAg"
    "IDxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRhZyI+Rk9SIERFVkVMT1BFUlM8L2Rpdj48aDM+QW4gb3BlbiB0b2tlbiBm"
    "b3JtYXQ8L2gzPjxwPkVkMjU1MTksIGNhbm9uaWNhbCBKU09OLCBvbmUgcHJlZml4LiBWZXJpZnkgaXQgeW91cnNlbGYgYW5kIGRp"
    "c2FncmVlIHdpdGggdXMuPC9wPgogICAgICA8YSBocmVmPSJodHRwczovL3NlYmJpLnByby94L3Bhc3Nwb3J0L3NwZWMiPlJlYWQg"
    "dGhlIHNwZWM8L2E+PC9kaXY+CiAgPC9kaXY+CjxwcmU+QWdlbnQtUGFzc3BvcnQ6IHNicDEuZXlKaFkzUWlPaUprWlcxdkxuQmhl"
    "U0lzSW1GMVpDSTZJbk5vYjNBdeKApjwvcHJlPgo8L3NlY3Rpb24+Cgo8ZGl2IGNsYXNzPSJjbG9zZSI+CiAgPGgyPklmIHlvdXIg"
    "YWdlbnRzIHRvdWNoIG1vbmV5LCByZWNvcmRzIG9yIGN1c3RvbWVycywgdGhpcyBpcyBmb3IgeW91LjwvaDI+CiAgPHA+RnJlZSBm"
    "b3IgOTAgZGF5cywgdGhlbiA1MHAgcGVyIGRldmljZSBwZXIgbW9udGguIFRlbGwgdXMgd2hhdCB5b3VyIGFnZW50cyBkbyBhbmQg"
    "d2UnbGwgc2hvdyB5b3UgaG93IHRoZSBwYXNzcG9ydCBwbHVncyBpbnRvIHlvdXIgc3RhY2suPC9wPgogIDxhIGNsYXNzPSJjdGEg"
    "Z29sZCIgaHJlZj0ibWFpbHRvOmp1c3RyaWdodGRlY29yYXRvcnNAZ21haWwuY29tP3N1YmplY3Q9QWdlbnQlMjBQYXNzcG9ydCI+"
    "VGFsayB0byB1czwvYT4KICA8YSBjbGFzcz0iY3RhIGdob3N0IiBocmVmPSIvbWFwIiBzdHlsZT0iYmFja2dyb3VuZDp0cmFuc3Bh"
    "cmVudDtjb2xvcjojZmZmO2JvcmRlci1jb2xvcjpyZ2JhKDI1NSwyNTUsMjU1LC4zKSI+U2VlIHdoZXJlIGl0IHNpdHM8L2E+Cjwv"
    "ZGl2Pgo8L2Rpdj4KCjxmb290ZXI+PGRpdiBjbGFzcz0id3JhcCI+c2ViYmkucHJvIMK3IE1vbm9wIENvbnRlbnQgwrcgQmx5dGgs"
    "IE5vcnRodW1iZXJsYW5kLCBVSzxicj5UaGUgdHJ1c3QgbGF5ZXIgYmV0d2VlbiBtYWNoaW5lcyB0aGF0IGFjdCBhbmQgdGhlIHdv"
    "cmxkIHRoZXkgYWN0IG9uLjwvZGl2PjwvZm9vdGVyPgoKPHNjcmlwdD4KZnVuY3Rpb24gZXNjKHMpe3JldHVybiBTdHJpbmcocz09"
    "bnVsbD8nJzpzKS5yZXBsYWNlKC9bJjw+Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57JyYnOicmYW1wOycsJzwnOicmbHQ7JywnPic6"
    "JyZndDsnLCciJzonJnF1b3Q7J31bY119KX0KZnVuY3Rpb24gc3RhdHMoKXtmZXRjaCgnL3gvcGFzc3BvcnQvc3RhdHVzJykudGhl"
    "bihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpewogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "J3MtaXNzdWVkJykudGV4dENvbnRlbnQ9ZC5wYXNzcG9ydHNfaXNzdWVkO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLXJlZCcp"
    "LnRleHRDb250ZW50PWQucmVkZWVtZWQ7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtcmVmJykudGV4dENvbnRlbnQ9ZC5yZWZ1"
    "c2VkfSkuY2F0Y2goZnVuY3Rpb24oKXt9KX0Kc3RhdHMoKTsKZnVuY3Rpb24gcnVuRGVtbygpewogdmFyIGJveD1kb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgnc3RvcnknKSx2PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJkaWN0JyksYj1kb2N1bWVudC5nZXRF"
    "bGVtZW50QnlJZCgncnVuYnRuJyk7CiBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCcuZGFyaycpLnNjcm9sbEludG9WaWV3KHtiZWhh"
    "dmlvcjonc21vb3RoJ30pOwogYm94LmlubmVySFRNTD0nJzt2LnRleHRDb250ZW50PSdSdW5uaW5nIG9uIHByb2R1Y3Rpb27igKYn"
    "O2IuZGlzYWJsZWQ9dHJ1ZTsKIGZldGNoKCcveC9wYXNzcG9ydC9kZW1vJykudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29u"
    "KCl9KS50aGVuKGZ1bmN0aW9uKGQpewogIGlmKGQuZXJyb3I9PT0ndG9vX3Nvb24nKXt2LnRleHRDb250ZW50PSdTb21lb25lIGp1"
    "c3QgcmFuIGl0LiBUcnkgYWdhaW4gaW4gJytkLnJldHJ5X2FmdGVyX3NlY29uZHMrJyBzZWNvbmRzLic7Yi5kaXNhYmxlZD1mYWxz"
    "ZTtyZXR1cm59CiAgaWYoIWQuc3Rvcnkpe3YudGV4dENvbnRlbnQ9J0RlbW8gdW5hdmFpbGFibGUgcmlnaHQgbm93Lic7Yi5kaXNh"
    "YmxlZD1mYWxzZTtyZXR1cm59CiAgZC5zdG9yeS5mb3JFYWNoKGZ1bmN0aW9uKHMsaSl7CiAgIHZhciBraW5kPSdpbmZvJyxsYWJl"
    "bD0nU0VBTEVEJzsKICAgaWYocy5yZWRlZW1lZD09PXRydWV8fHMudmFsaWQ9PT10cnVlfHxzLmlzc3VlZD09PXRydWUpe2tpbmQ9"
    "J3Bhc3MnO2xhYmVsPXMucmVkZWVtZWQ9PT10cnVlPydCT1VORCc6KHMudmFsaWQ9PT10cnVlPydWQUxJRCc6J0lTU1VFRCcpfQog"
    "ICBpZihzLnJlZGVlbWVkPT09ZmFsc2V8fHMudmFsaWQ9PT1mYWxzZXx8cy5pc3N1ZWQ9PT1mYWxzZSl7a2luZD0nc3RvcCc7bGFi"
    "ZWw9J1JFRlVTRUQnfQogICB2YXIgd2h5PXMud2h5JiZzLndoeS5sZW5ndGg/JzxzcGFuIGNsYXNzPSJ3aHkiPicrZXNjKHMud2h5"
    "WzBdKSsnPC9zcGFuPic6Jyc7CiAgIHZhciBlbD1kb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTtlbC5jbGFzc05hbWU9J3Jv"
    "dyc7CiAgIGVsLmlubmVySFRNTD0nPHNwYW4gY2xhc3M9ImljICcra2luZCsnIj4nK2xhYmVsKyc8L3NwYW4+PGRpdj4nK2VzYyhz"
    "LmFjdCkrd2h5Kyc8L2Rpdj4nOwogICBib3guYXBwZW5kQ2hpbGQoZWwpO3NldFRpbWVvdXQoZnVuY3Rpb24oKXtlbC5jbGFzc0xp"
    "c3QuYWRkKCdzaG93Jyl9LDE2MCppKzYwKX0pOwogIHNldFRpbWVvdXQoZnVuY3Rpb24oKXt2LnRleHRDb250ZW50PWQucmVzdWx0"
    "PT09J0FMTCBURU4gQkVIQVZFRCc/J+KckyBBbGwgdGVuIGJlaGF2ZWQuIEV2ZXJ5IHN0ZXAgaXMgb24gdGhlIGNoYWluLic6ZC5y"
    "ZXN1bHQ7Yi5kaXNhYmxlZD1mYWxzZTtzdGF0cygpfSwxNjAqZC5zdG9yeS5sZW5ndGgrMzAwKTsKIH0pLmNhdGNoKGZ1bmN0aW9u"
    "KCl7di50ZXh0Q29udGVudD0nQ291bGQgbm90IHJlYWNoIHRoZSBkZW1vLic7Yi5kaXNhYmxlZD1mYWxzZX0pOwp9Cjwvc2NyaXB0"
    "Pgo8L2JvZHk+CjwvaHRtbD4K"
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
    if getattr(cls, "_passportpage_patched", False):
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
    cls._passportpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    if action == "spec":
        return ({
            "module": "passportpage",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/passportpage/status once after each deploy to arm " + PAGE_PATH + ".",
        }, 200)
    return ({
        "module": "passportpage",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
