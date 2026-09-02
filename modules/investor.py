"""
modules/investor.py  v1.1.0
Serves the investor investor page at /investor-investor.

Page module, same family as console.py / network.py / packconsole.py: a runtime
do_GET patch puts a full HTML page at a clean URL. Armed by hitting
/x/investor/status once after each deploy. server.py is never edited.

The handler class is discovered at call time from the live request handler that
the router passes in ctx, falling back to a stack walk, so this does not depend
on the exact ctx key name. The page is base64-embedded so no character in the
HTML can break the Python string; it is decoded once at import.
"""

import base64
import sys

VERSION = "1.1.0"
PAGE_PATH = "/investor-prospectus"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+U2ViYmkucHJv"
    "IOKAlCBTZWVkIFJvdW5kIFByb3NwZWN0dXM8L3RpdGxlPgo8bGluayByZWw9InByZWNvbm5lY3QiIGhyZWY9Imh0dHBzOi8vZm9u"
    "dHMuZ29vZ2xlYXBpcy5jb20iPgo8bGluayBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PU5l"
    "d3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDQwMDs2Li43Miw1MDA7Ni4uNzIsNjAwOzYuLjcyLDcwMCZmYW1pbHk9SUJNK1BsZXgr"
    "U2Fuczp3Z2h0QDQwMDs1MDA7NjAwOzcwMCZmYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs1MDA7NjAwJmRpc3BsYXk9c3dh"
    "cCIgcmVsPSJzdHlsZXNoZWV0Ij4KPHN0eWxlPgo6cm9vdHsKICAtLXBhcGVyOiNGQUZBRjY7LS1pbms6IzE0MTcxQzstLWluay1z"
    "b2Z0OiM0NTRCNTQ7LS1jaGFpbjojMkU1RTRFOwogIC0tY2hhaW4tbGlnaHQ6I0U0RUNFODstLWFsZXJ0OiM5QzJGMjY7LS1hbGVy"
    "dC1saWdodDojRjVFNkUzOy0tbGluZTojREVEQkQxOwp9Cip7Ym94LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3BhZGRpbmc6"
    "MH0KYm9keXtmb250LWZhbWlseTonSUJNIFBsZXggU2Fucycsc2Fucy1zZXJpZjtiYWNrZ3JvdW5kOnZhcigtLXBhcGVyKTtjb2xv"
    "cjp2YXIoLS1pbmspO2xpbmUtaGVpZ2h0OjEuNjstd2Via2l0LWZvbnQtc21vb3RoaW5nOmFudGlhbGlhc2VkfQpoMSxoMixoMywu"
    "ZGlzcGxheXtmb250LWZhbWlseTonTmV3c3JlYWRlcicsc2VyaWY7Zm9udC13ZWlnaHQ6NTAwO2xldHRlci1zcGFjaW5nOi0wLjAx"
    "ZW19Ci5tb25ve2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2V9CmF7Y29sb3I6dmFyKC0tY2hhaW4pfQoud3Jh"
    "cHttYXgtd2lkdGg6NzYwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjAgMjhweH0KCmhlYWRlcntwYWRkaW5nOjU2cHggMCA0MHB4"
    "O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpfQouZG9jLWxhYmVse2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25v"
    "Jyxtb25vc3BhY2U7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MC4xZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2Nv"
    "bG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tYm90dG9tOjIwcHg7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1i"
    "ZXR3ZWVuO2ZsZXgtd3JhcDp3cmFwO2dhcDo4cHh9Cmgxe2ZvbnQtc2l6ZTpjbGFtcCgzNHB4LDV2dyw0OHB4KTtsaW5lLWhlaWdo"
    "dDoxLjE7bWF4LXdpZHRoOjE2Y2g7bWFyZ2luLWJvdHRvbToxNnB4fQoudGFnbGluZXtmb250LXNpemU6MTdweDtjb2xvcjp2YXIo"
    "LS1pbmstc29mdCk7bWF4LXdpZHRoOjUyY2h9CgouYmxvY2t7cG9zaXRpb246cmVsYXRpdmU7cGFkZGluZzo4cHggMCA0NHB4IDI0"
    "cHg7Ym9yZGVyLWxlZnQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpO21hcmdpbi1sZWZ0OjRweH0KLmJsb2NrOmxhc3Qtb2YtdHlwZXti"
    "b3JkZXItbGVmdDoxcHggc29saWQgdHJhbnNwYXJlbnR9Ci5ibG9jay1udW17Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1v"
    "bm9zcGFjZTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1jaGFpbik7bGV0dGVyLXNwYWNpbmc6MC4wOGVtO3RleHQtdHJhbnNm"
    "b3JtOnVwcGVyY2FzZTttYXJnaW4tYm90dG9tOjEwcHh9Ci5ibG9jayBoMntmb250LXNpemU6MjZweDttYXJnaW4tYm90dG9tOjE2"
    "cHh9Ci5ibG9jayBoM3tmb250LXNpemU6MTdweDttYXJnaW46MjJweCAwIDhweH0KLmJsb2NrIHB7Zm9udC1zaXplOjE1LjVweDtj"
    "b2xvcjp2YXIoLS1pbmstc29mdCk7bWFyZ2luLWJvdHRvbToxNHB4O21heC13aWR0aDo2MGNofQouYmxvY2sgcDpsYXN0LWNoaWxk"
    "e21hcmdpbi1ib3R0b206MH0KLmJsb2NrIHVse21hcmdpbjowIDAgMTRweCAxOHB4fQouYmxvY2sgbGl7Zm9udC1zaXplOjE1cHg7"
    "Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206OHB4O21heC13aWR0aDo1OGNofQouYmxvY2sgbGkgYiwuYmxvY2sg"
    "cCBie2NvbG9yOnZhcigtLWluayl9CgouZGF0ZXN7YmFja2dyb3VuZDp3aGl0ZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "O2JvcmRlci1yYWRpdXM6NHB4O21hcmdpbjoyMHB4IDA7b3ZlcmZsb3c6aGlkZGVufQouZGF0ZS1yb3d7ZGlzcGxheTpncmlkO2dy"
    "aWQtdGVtcGxhdGUtY29sdW1uczoxMzBweCAxZnI7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9Ci5kYXRlLXJv"
    "dzpsYXN0LWNoaWxke2JvcmRlci1ib3R0b206bm9uZX0KLmRhdGUtcm93LmhlYWR7YmFja2dyb3VuZDp2YXIoLS1pbmspfQouZGF0"
    "ZS1yb3cuaGVhZCAuZGQsLmRhdGUtcm93LmhlYWQgLmR3e2NvbG9yOndoaXRlO2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxt"
    "b25vc3BhY2U7Zm9udC1zaXplOjEwLjVweDtsZXR0ZXItc3BhY2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlfQou"
    "ZGR7cGFkZGluZzoxMnB4IDE2cHg7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTIuNXB4"
    "O2ZvbnQtd2VpZ2h0OjYwMDtib3JkZXItcmlnaHQ6MXB4IHNvbGlkIHZhcigtLWxpbmUpfQouZHd7cGFkZGluZzoxMnB4IDE2cHg7"
    "Zm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO2xpbmUtaGVpZ2h0OjEuNTV9Ci5kdyBie2NvbG9yOnZhcigtLWlu"
    "ayl9Ci5kYXRlLXJvdy5rZXkgLmRke2NvbG9yOnZhcigtLWFsZXJ0KX0KQG1lZGlhKG1heC13aWR0aDo1NjBweCl7LmRhdGUtcm93"
    "e2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9LmRke2JvcmRlci1yaWdodDpub25lO3BhZGRpbmctYm90dG9tOjB9fQoKLmNvdW50"
    "ZG93bntiYWNrZ3JvdW5kOnZhcigtLWFsZXJ0LWxpZ2h0KTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMTU2LDQ3LDM4LDAuMik7Ym9y"
    "ZGVyLXJhZGl1czo0cHg7cGFkZGluZzoyMHB4IDI0cHg7bWFyZ2luOjIwcHggMH0KLmNvdW50ZG93bi1sYWJlbHtmb250LWZhbWls"
    "eTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWFsZXJ0KTt0ZXh0LXRyYW5zZm9y"
    "bTp1cHBlcmNhc2U7bGV0dGVyLXNwYWNpbmc6MC4wOGVtO21hcmdpbi1ib3R0b206OHB4fQouY291bnRkb3duLWRheXN7Zm9udC1m"
    "YW1pbHk6J05ld3NyZWFkZXInLHNlcmlmO2ZvbnQtc2l6ZTozOHB4O2ZvbnQtd2VpZ2h0OjYwMDtjb2xvcjp2YXIoLS1hbGVydCk7"
    "bGluZS1oZWlnaHQ6MX0KLmNvdW50ZG93bi1zdWJ7Zm9udC1zaXplOjEzcHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi10"
    "b3A6NnB4O2xpbmUtaGVpZ2h0OjEuNn0KCi5wcm9vZi1ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZy"
    "IDFmcjtnYXA6MTRweDttYXJnaW4tdG9wOjE4cHh9CkBtZWRpYShtYXgtd2lkdGg6NTYwcHgpey5wcm9vZi1ncmlke2dyaWQtdGVt"
    "cGxhdGUtY29sdW1uczoxZnJ9fQoucHJvb2Z7YmFja2dyb3VuZDp3aGl0ZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO3Bh"
    "ZGRpbmc6MThweCAyMHB4O2JvcmRlci1yYWRpdXM6NHB4fQoucHJvb2Ytbntmb250LWZhbWlseTonTmV3c3JlYWRlcicsc2VyaWY7"
    "Zm9udC1zaXplOjI2cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLWNoYWluKX0KLnByb29mLWx7Zm9udC1zaXplOjEyLjVw"
    "eDtjb2xvcjp2YXIoLS1pbmstc29mdCk7bWFyZ2luLXRvcDozcHh9Ci5wcm9vZi1zcmN7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1v"
    "bm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTBweDtjb2xvcjojOTk5O21hcmdpbi10b3A6NnB4fQoKLnN0YXR1cy1saXN0e21hcmdp"
    "bi10b3A6MTZweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rpb246Y29sdW1uO2dhcDowfQouc3RhdHVzLXJvd3tkaXNwbGF5OmZs"
    "ZXg7YWxpZ24taXRlbXM6ZmxleC1zdGFydDtnYXA6MTJweDtwYWRkaW5nOjExcHggMDtib3JkZXItYm90dG9tOjFweCBzb2xpZCB2"
    "YXIoLS1saW5lKX0KLnN0YXR1cy1yb3c6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci5zdGF0dXMtaWNvbntmb250LWZh"
    "bWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMnB4O2ZvbnQtd2VpZ2h0OjYwMDtmbGV4LXNocmluazow"
    "O3dpZHRoOjIwcHg7cGFkZGluZy10b3A6MnB4fQouc3RhdHVzLWljb24ueWVze2NvbG9yOnZhcigtLWNoYWluKX0KLnN0YXR1cy1p"
    "Y29uLm5ve2NvbG9yOnZhcigtLWFsZXJ0KX0KLnN0YXR1cy10ZXh0IHN0cm9uZ3tjb2xvcjp2YXIoLS1pbmspO2ZvbnQtd2VpZ2h0"
    "OjYwMH0KLnN0YXR1cy10ZXh0IHNwYW57Y29sb3I6dmFyKC0taW5rLXNvZnQpO2ZvbnQtc2l6ZToxNC41cHh9CgouYXNrLWJveHti"
    "YWNrZ3JvdW5kOnZhcigtLWluayk7Y29sb3I6dmFyKC0tcGFwZXIpO2JvcmRlci1yYWRpdXM6NHB4O3BhZGRpbmc6MzJweDttYXJn"
    "aW4tdG9wOjIwcHh9Ci5hc2stYW1vdW50e2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJpZjtmb250LXNpemU6NDRweDtmb250"
    "LXdlaWdodDo2MDA7Y29sb3I6d2hpdGV9Ci5hc2stbGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtm"
    "b250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM4RkE4OUM7"
    "bWFyZ2luLWJvdHRvbTo2cHh9Ci51c2Utb2YtZnVuZHN7bWFyZ2luLXRvcDoyNHB4O2Rpc3BsYXk6ZmxleDtmbGV4LWRpcmVjdGlv"
    "bjpjb2x1bW47Z2FwOjEwcHh9Ci51Zi1yb3d7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWdu"
    "LWl0ZW1zOmJhc2VsaW5lO3BhZGRpbmctYm90dG9tOjEwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1"
    "NSwwLjEyKTtmb250LXNpemU6MTRweH0KLnVmLXJvdzpsYXN0LWNoaWxke2JvcmRlci1ib3R0b206bm9uZX0KLnVmLXBjdHtmb250"
    "LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2NvbG9yOiM4RkE4OUN9Cgoucmlzay1ib3h7YmFja2dyb3VuZDp3aGl0"
    "ZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1sZWZ0OjNweCBzb2xpZCB2YXIoLS1hbGVydCk7cGFkZGluZzoy"
    "MHB4IDI0cHg7Ym9yZGVyLXJhZGl1czoycHg7bWFyZ2luLXRvcDoxNnB4fQoucmlzay1ib3ggaDR7Zm9udC1zaXplOjE0cHg7bWFy"
    "Z2luLWJvdHRvbTo4cHg7Y29sb3I6dmFyKC0taW5rKX0KLnJpc2stYm94IHB7Zm9udC1zaXplOjEzLjVweDtjb2xvcjp2YXIoLS1p"
    "bmstc29mdCk7bWFyZ2luLWJvdHRvbTo4cHh9Ci5yaXNrLWJveCBwOmxhc3QtY2hpbGR7bWFyZ2luLWJvdHRvbTowfQoKLnZlcmlm"
    "eS1ib3h7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1saWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMjUpO2Jv"
    "cmRlci1yYWRpdXM6NHB4O3BhZGRpbmc6MjBweCAyNHB4O21hcmdpbi10b3A6MThweH0KLnZlcmlmeS1ib3ggaDR7Zm9udC1zaXpl"
    "OjE1cHg7bWFyZ2luLWJvdHRvbToxMHB4fQoudmVyaWZ5LWJveCBwe2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1ib3R0b206OHB4fQou"
    "dmVyaWZ5LWJveCBjb2Rle2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjEyLjVweDtiYWNr"
    "Z3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoycHggN3B4O2JvcmRlci1yYWRpdXM6M3B4"
    "O2NvbG9yOnZhcigtLWNoYWluKX0KCi5jb250YWN0LWJsb2Nre3BhZGRpbmc6NDRweCAwIDY0cHh9Ci5jb250YWN0LWNhcmR7YmFj"
    "a2dyb3VuZDp2YXIoLS1jaGFpbi1saWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMik7Ym9yZGVyLXJhZGl1"
    "czo0cHg7cGFkZGluZzoyOHB4fQouY29udGFjdC1jYXJkIGgze2ZvbnQtc2l6ZToyMHB4O21hcmdpbi1ib3R0b206MTBweH0KLmNv"
    "bnRhY3QtY2FyZCBwe2ZvbnQtc2l6ZToxNC41cHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTZweH0KLmNv"
    "bnRhY3QtbGlua3N7ZGlzcGxheTpmbGV4O2ZsZXgtZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4O2ZvbnQtZmFtaWx5OidJQk0gUGxl"
    "eCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjE0cHh9Ci5jb250YWN0LWxpbmtzIGF7Y29sb3I6dmFyKC0tY2hhaW4pO3RleHQt"
    "ZGVjb3JhdGlvbjpub25lO2ZvbnQtd2VpZ2h0OjUwMH0KCmZvb3RlcntwYWRkaW5nOjAgMCA0OHB4fQpmb290ZXIgcHtmb250LWZh"
    "bWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiM5OTk7bGluZS1oZWlnaHQ6MS44fQoK"
    "QG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246cmVkdWNlKXsqe3RyYW5zaXRpb246bm9uZSFpbXBvcnRhbnQ7YW5pbWF0aW9u"
    "Om5vbmUhaW1wb3J0YW50fX0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9IndyYXAiPgoKPGhlYWRlcj4KICA8"
    "ZGl2IGNsYXNzPSJkb2MtbGFiZWwiPgogICAgPHNwYW4+U2VlZCBSb3VuZCBQcm9zcGVjdHVzICZtaWRkb3Q7IHYyLjA8L3NwYW4+"
    "CiAgICA8c3BhbiBpZD0iZG9jLWRhdGUiPiZtZGFzaDs8L3NwYW4+CiAgPC9kaXY+CiAgPGgxPkNvbXBsaWFuY2UgZXZpZGVuY2Ug"
    "Y2Fubm90IGJlIGJhY2stZmlsbGVkLiBUaGF0IGlzIHRoZSB3aG9sZSBidXNpbmVzcy48L2gxPgogIDxwIGNsYXNzPSJ0YWdsaW5l"
    "Ij5TZWJiaS5wcm8gLyBBSUxlYXNoICZtZGFzaDsgYSBsaXZlLCBwdWJsaWNseSB2ZXJpZmlhYmxlIGV2aWRlbmNlIGxheWVyIGZv"
    "ciBBSSBkZWNpc2lvbnMuIFByZS1yZXZlbnVlLiBTb2xvLWJ1aWx0LiBSYWlzaW5nICZwb3VuZDs1MDAsMDAwIHRvIGdvIGZ1bGwt"
    "dGltZSBhbmQgY29udmVydCBhIHdvcmtpbmcgcGxhdGZvcm0gaW50byBhIHBheWluZyBvbmUuPC9wPgo8L2hlYWRlcj4KCjxkaXYg"
    "Y2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPkJsb2NrIDAxICZtZGFzaDsgVGhlIERlYWRsaW5lLCBTdGF0"
    "ZWQgQ29ycmVjdGx5PC9kaXY+CiAgPGgyPk5vdCBvbmUgZGF0ZS4gRm91ciAmbWRhc2g7IGFuZCB0aGUgaW1wb3J0YW50IG9uZSBp"
    "cyAyMDI3LjwvaDI+CiAgPHA+TW9zdCBwaXRjaGVzIGluIHRoaXMgY2F0ZWdvcnkgcXVvdGUgYSBzaW5nbGUgRVUgQUkgQWN0IGRl"
    "YWRsaW5lLiBUaGF0IGlzIHdyb25nLCBhbmQgYW55IGludmVzdG9yIHdobyBjaGVja3Mgd2lsbCBmaW5kIGl0IHdyb25nLiBUaGUg"
    "ZGF0ZXMgbW92ZWQgdW5kZXIgdGhlIEFJIE9tbmlidXMsIGFuZCB0aGV5IG1vdmVkIGRpZmZlcmVudGx5IGZvciBkaWZmZXJlbnQg"
    "ZHV0aWVzLjwvcD4KCiAgPGRpdiBjbGFzcz0iZGF0ZXMiPgogICAgPGRpdiBjbGFzcz0iZGF0ZS1yb3cgaGVhZCI+PGRpdiBjbGFz"
    "cz0iZGQiPkRhdGU8L2Rpdj48ZGl2IGNsYXNzPSJkdyI+V2hhdCBhcHBsaWVzPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJk"
    "YXRlLXJvdyI+PGRpdiBjbGFzcz0iZGQiPjIgQXVnIDIwMjY8L2Rpdj48ZGl2IGNsYXNzPSJkdyI+PGI+VHJhbnNwYXJlbmN5IGR1"
    "dGllcy48L2I+IERpc2Nsb3NlIEFJIGludGVyYWN0aW9uLCBtYXJrIEFJLWdlbmVyYXRlZCBjb250ZW50IG1hY2hpbmUtcmVhZGFi"
    "bHksIGRpc2Nsb3NlIGRlZXBmYWtlcy4gQ29tbWlzc2lvbiBlbmZvcmNlbWVudCBwb3dlcnMgb3ZlciBnZW5lcmFsLXB1cnBvc2Ug"
    "bW9kZWxzIGJlZ2luLjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0iZGF0ZS1yb3ciPjxkaXYgY2xhc3M9ImRkIj4yIERlYyAy"
    "MDI2PC9kaXY+PGRpdiBjbGFzcz0iZHciPjxiPkNvbnRlbnQtbWFya2luZyBncmFjZSBwZXJpb2QgZW5kczwvYj4gJm1kYXNoOyBj"
    "dXQgZnJvbSBzaXggbW9udGhzIHRvIHRocmVlLiBQcm9oaWJpdGlvbiBvbiBBSS1nZW5lcmF0ZWQgTkNJSSBhbmQgQ1NBTSB0YWtl"
    "cyBlZmZlY3QuPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJkYXRlLXJvdyBrZXkiPjxkaXYgY2xhc3M9ImRkIj4yIERlYyAy"
    "MDI3PC9kaXY+PGRpdiBjbGFzcz0iZHciPjxiPkhpZ2gtcmlzayBkdXRpZXMsIHN0YW5kYWxvbmUgc3lzdGVtczwvYj4gJm1kYXNo"
    "OyBBcnRpY2xlcyA5LCAxMiwgMTMsIDE0LiBEZWxheWVkIGZyb20gQXVndXN0IDIwMjYuIDxiPlRoaXMgaXMgdGhlIGNvbW1lcmNp"
    "YWxseSByZWxldmFudCBkYXRlLjwvYj48L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImRhdGUtcm93Ij48ZGl2IGNsYXNzPSJk"
    "ZCI+MiBBdWcgMjAyODwvZGl2PjxkaXYgY2xhc3M9ImR3Ij48Yj5IaWdoLXJpc2sgZHV0aWVzIGZvciBBSSBlbWJlZGRlZCBpbiBw"
    "cm9kdWN0cy48L2I+PC9kaXY+PC9kaXY+CiAgPC9kaXY+CgogIDxwPkZpbmVzIHJlYWNoIDMlIG9mIGdsb2JhbCBhbm51YWwgdHVy"
    "bm92ZXIgb3IgJmV1cm87MTVtLCB3aGljaGV2ZXIgaXMgaGlnaGVyLCBwZXIgdmlvbGF0aW9uLjwvcD4KCiAgPGgzPldoeSBhIGRl"
    "bGF5IGlzIGEgbWFya2V0LCBub3QgYSBwcm9ibGVtPC9oMz4KICA8cD5UaGUgZGVsYXkgcmVhZHMgbGlrZSBicmVhdGhpbmcgcm9v"
    "bSBhbmQgaXMgdGhlIG9wcG9zaXRlLiA8Yj5UaGUgZXZpZGVuY2UgdGhvc2Ugb2JsaWdhdGlvbnMgcmVxdWlyZSBpcyBoaXN0b3Jp"
    "Y2FsLjwvYj4gSW4gRGVjZW1iZXIgMjAyNyBhbiBhdWRpdG9yIGFza3Mgd2hhdCBhIHN5c3RlbSBkZWNpZGVkIGluIDIwMjYgYW5k"
    "IHdoeS4gVGhhdCByZWNvcmQgZWl0aGVyIGV4aXN0cyBvciBpdCBkb2VzIG5vdCwgYW5kIGl0IGNhbm5vdCBiZSByZWNvbnN0cnVj"
    "dGVkIGFmdGVyd2FyZHMuPC9wPgogIDxwPkV2ZXJ5IG1vbnRoIGJldHdlZW4gbm93IGFuZCB0aGVuIGlzIGEgbW9udGggb2YgZXZp"
    "ZGVuY2Ugbm9ib2R5IGlzIGNvbGxlY3RpbmcuIFRoZSBhZGRyZXNzYWJsZSBtb21lbnQgaXMgbm90IHRoZSBkZWFkbGluZSAmbWRh"
    "c2g7IGl0IGlzIG5vdy48L3A+CgogIDxkaXYgY2xhc3M9ImNvdW50ZG93biI+CiAgICA8ZGl2IGNsYXNzPSJjb3VudGRvd24tbGFi"
    "ZWwiPlRpbWUgdG8gaGlnaC1yaXNrIG9ibGlnYXRpb25zPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjb3VudGRvd24tZGF5cyBtb25v"
    "IiBpZD0iY291bnRkb3duLWRheXMiPiZtZGFzaDsgZGF5czwvZGl2PgogICAgPGRpdiBjbGFzcz0iY291bnRkb3duLXN1YiI+Q2Fs"
    "Y3VsYXRlZCBhZ2FpbnN0IDIgRGVjZW1iZXIgMjAyNy4gRXZlcnkgZGF5IG9mIGl0IGlzIGEgZGF5IG9mIHVucmVjb3ZlcmFibGUg"
    "ZXZpZGVuY2UgZm9yIGFueSBvcmdhbmlzYXRpb24gbm90IHlldCByZWNvcmRpbmcuPC9kaXY+CiAgPC9kaXY+CjwvZGl2PgoKPGRp"
    "diBjbGFzcz0iYmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+QmxvY2sgMDIgJm1kYXNoOyBXaGF0IElzIEFjdHVhbGx5"
    "IEJ1aWx0PC9kaXY+CiAgPGgyPkxpdmUgaW4gcHJvZHVjdGlvbi4gVmVyaWZpYWJsZSB3aXRob3V0IGFza2luZyB1cy48L2gyPgog"
    "IDxwPlNlYmJpLnBybyBydW5zIGluIHByb2R1Y3Rpb24gb24gUmFpbHdheSB0b2RheS4gSXQgaXMgbm90IGEgZGVjayBhbmQgbm90"
    "IGEgZGVtbyBlbnZpcm9ubWVudDogYSBkZXRlcm1pbmlzdGljIGRlY2lzaW9uIGVuZ2luZSwgYSB0YW1wZXItZXZpZGVudCBhdWRp"
    "dCBjaGFpbiwgZXh0ZXJuYWwgdGltZXN0YW1waW5nLCBhbmQgYW4gZXh0ZW5zaWJsZSBtb2R1bGUgbGF5ZXIgJm1kYXNoOyBhbGwg"
    "b2YgaXQgY2hlY2thYmxlIGJ5IGEgdGhpcmQgcGFydHkgd2l0aCBubyBhY2NvdW50IGFuZCBubyBwZXJtaXNzaW9uLjwvcD4KCiAg"
    "PGRpdiBjbGFzcz0icHJvb2YtZ3JpZCI+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+CiAgICAgIDxkaXYgY2xhc3M9InByb29mLW4g"
    "bW9ubyI+MjhtczwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwcm9vZi1sIj5NZWRpYW4gZGVjaXNpb24gdGltZTwvZGl2PgogICAg"
    "ICA8ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPk1lYXN1cmVkIG9uIGxpdmUgcHJvZHVjdGlvbiB0cmFmZmljPC9kaXY+CiAgICA8L2Rp"
    "dj4KICAgIDxkaXYgY2xhc3M9InByb29mIj4KICAgICAgPGRpdiBjbGFzcz0icHJvb2YtbiBtb25vIj5TSEEtMjU2PC9kaXY+CiAg"
    "ICAgIDxkaXYgY2xhc3M9InByb29mLWwiPkhhc2gtY2hhaW5lZCBhdWRpdCBsZWRnZXI8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0i"
    "cHJvb2Ytc3JjIj5UYW1wZXItZXZpZGVudCBieSBjb25zdHJ1Y3Rpb248L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBjbGFzcz0i"
    "cHJvb2YiPgogICAgICA8ZGl2IGNsYXNzPSJwcm9vZi1uIG1vbm8iPjk8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icHJvb2YtbCI+"
    "TGl2ZSBjYXBhYmlsaXR5IG1vZHVsZXM8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icHJvb2Ytc3JjIj5BZGRlZCB3aXRob3V0IHRv"
    "dWNoaW5nIHRoZSBjb3JlIHNlcnZlcjwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+CiAgICAgIDxkaXYg"
    "Y2xhc3M9InByb29mLW4gbW9ubyI+NDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwcm9vZi1sIj5Qcm9kdWN0czogQUlMZWFzaCwg"
    "R3VhcmRpYW4sIFNvbmljQm9vbSwgU2VudGluZWw8L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0icHJvb2Ytc3JjIj5TaGFyZWQgZW5n"
    "aW5lLCBzaGFyZWQgYXVkaXQgY2hhaW48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2PgoKICA8aDM+V2hhdCB3YXMgYWRkZWQgaW4g"
    "dGhlIG1vc3QgcmVjZW50IGJ1aWxkIGN5Y2xlPC9oMz4KICA8dWw+CiAgICA8bGk+PGI+SHVtYW4gb3ZlcnNpZ2h0LCBjb21taXQt"
    "YmVmb3JlLXJldmVhbC48L2I+IFRoZSByZXZpZXdlcidzIGRlY2lzaW9uIGlzIHNlYWxlZCBiZWZvcmUgdGhlIG1hY2hpbmUncyB2"
    "ZXJkaWN0IGlzIGRpc2Nsb3NlZCB0byB0aGVtLCB3aXRoIGR3ZWxsIHRpbWUgYW5kIGRpdmVyZ2VuY2UgcmF0ZSByZWNvcmRlZC4g"
    "VGhpcyBpcyB0aGUgZmlyc3QgbWVjaGFuaXNtIGluIHRoZSBjYXRlZ29yeSB0aGF0IGRpc3Rpbmd1aXNoZXMgaW5kZXBlbmRlbnQg"
    "anVkZ2VtZW50IGZyb20gYSBydWJiZXIgc3RhbXAuPC9saT4KICAgIDxsaT48Yj5NdXR1YWwgd2l0bmVzc2luZy48L2I+IFBsYXRm"
    "b3JtcyBzZWFsIGVhY2ggb3RoZXIncyBjaGFpbiB0aXBzLCBzbyBvbmUgb3BlcmF0b3IncyBoaXN0b3J5IHNpdHMgaW5zaWRlIGNo"
    "YWlucyB0aGV5IGRvIG5vdCBjb250cm9sLiBSZXdyaXRpbmcgeW91ciBvd24gcGFzdCBiZWNvbWVzIGEgY29uc3BpcmFjeSBiZXR3"
    "ZWVuIGNvbXBldGl0b3JzIHJhdGhlciB0aGFuIGEgZGF0YWJhc2Ugb3BlcmF0aW9uLjwvbGk+CiAgICA8bGk+PGI+UmVjb25jaWxp"
    "YXRpb24uPC9iPiBTZWFsZWQgcmVjb3JkcyBhcmUgdGVzdGVkIGFnYWluc3QgdGhlIG9wZXJhdG9yJ3Mgb3duIGxpdmUgc3lzdGVt"
    "LCB3aXRoIHRoZSBzYW1wbGUgZGVyaXZlZCBmcm9tIHRoZSBjdXJyZW50IGNoYWluIHRpcCBhbmQgc2VhbGVkIGJlZm9yZSBhbnkg"
    "ZGF0YSBpcyByZXF1ZXN0ZWQgJm1kYXNoOyBzbyB0aGUgc2FtcGxlIGNhbm5vdCBiZSBjaG9zZW4gdG8gZmxhdHRlci48L2xpPgog"
    "ICAgPGxpPjxiPkRlY2xhcmF0aW9ucy48L2I+IEFuIG9wZXJhdG9yIHB1Ymxpc2hlcyB0aGUgcnVsZXMgdGhlaXIgZGVjaXNpb25z"
    "IG11c3Qgc2F0aXNmeTsgdGhlIHJ1bGVzIGFyZSBzZWFsZWQgYmVmb3JlIHRoZSByZWNvcmRzIHRoZXkganVkZ2UsIGFuZCBldmVy"
    "eSB2ZXJzaW9uIGlzIHJldGFpbmVkLCBzbyBhIHN0YW5kYXJkIGNhbm5vdCBiZSBxdWlldGx5IGxvb3NlbmVkLjwvbGk+CiAgICA8"
    "bGk+PGI+Q29uZm9ybWFuY2UgdGVzdGluZy48L2I+IFByb2JlcyB3aXRoIGRlbGliZXJhdGVseSB3cm9uZyB2ZXJkaWN0cywgYnJl"
    "YWR0aCBtZWFzdXJlbWVudCBvbiB0aGUgd2l0bmVzcyBuZXR3b3JrLCBhbmQgcGVyLXJ1bGUgc3RyZW5ndGggc2NvcmluZyAmbWRh"
    "c2g7IHRoZSBpbnN0cnVtZW50IHRoYXQgZGV0ZWN0cyB0aGUgcGxhdGZvcm0ncyBvd24gZmFpbHVyZSBtb2Rlcy48L2xpPgogICAg"
    "PGxpPjxiPkRhdGEgc3ViamVjdCByZXF1ZXN0IG5vdGFyeS48L2I+IFRoZSBlcmFzdXJlIGFuZCBhY2Nlc3MgbGlmZWN5Y2xlIHNl"
    "YWxlZCB3aXRob3V0IHRoZSBjaGFpbiBldmVyIGhvbGRpbmcgdGhlIHN1YmplY3QncyBpZGVudGl0eS48L2xpPgogIDwvdWw+Cjwv"
    "ZGl2PgoKPGRpdiBjbGFzcz0iYmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+QmxvY2sgMDMgJm1kYXNoOyBUaGUgRGlm"
    "ZmVyZW50aWF0b3I8L2Rpdj4KICA8aDI+RXZlcnkgY2xhaW0gY2FycmllcyBpdHMgb3duIGxpbWl0LjwvaDI+CiAgPHA+VGhlIHB1"
    "Ymxpc2hlZCB3aGl0ZXBhcGVyIGNvbnRhaW5zIGEgc2VjdGlvbiBsaXN0aW5nIHdoYXQgdGhlIHBsYXRmb3JtIDxiPmNhbm5vdDwv"
    "Yj4gZG8gJm1kYXNoOyBzaXh0ZWVuIG51bWJlcmVkIGxpbWl0YXRpb25zIGF0IHByZXNlbnQuIFdpdG5lc3NpbmcgcHJvdmVzIGEg"
    "dGlwIGV4aXN0ZWQsIG5vdCB0aGF0IGl0cyBjb250ZW50cyBhcmUgdHJ1ZS4gUmVjb25jaWxpYXRpb24gcHJvdmVzIGNvbnNpc3Rl"
    "bmN5LCBub3QgdHJ1dGguIE92ZXJzaWdodCBzZWFsaW5nIHByb3ZlcyBvcmRlciwgbm90IHRob3VnaHQuPC9wPgogIDxwPk5vIGNv"
    "bXBldGl0b3IgaW4gdGhpcyBjYXRlZ29yeSBwdWJsaXNoZXMgdGhhdCBsaXN0LiBJdCByZWFkcyBsaWtlIGEgd2Vha25lc3MgYW5k"
    "IGZ1bmN0aW9ucyBhcyB0aGUgb3Bwb3NpdGU6IGEgYnV5ZXIgZXZhbHVhdGluZyBjb21wbGlhbmNlIGluZnJhc3RydWN0dXJlIGlz"
    "IHRyeWluZyB0byB3b3JrIG91dCB3aGljaCB2ZW5kb3IgaXMgb3ZlcnN0YXRpbmcuIEEgdmVuZG9yIHdobyBuYW1lcyB0aGVpciBv"
    "d24gY2VpbGluZyBmaXJzdCBpcyB0aGUgb25lIHdobyBzdXJ2aXZlcyBkdWUgZGlsaWdlbmNlLjwvcD4KICA8cD5JdCBpcyBhbHNv"
    "IGRlZmVuc2libGUgY29tbWVyY2lhbGx5LiBUaGUgbGltaXRzIGFyZSBzdHJ1Y3R1cmFsIHJhdGhlciB0aGFuIGZpeGFibGUsIHNv"
    "IGEgY29tcGV0aXRvciBjYW5ub3Qgc2ltcGx5IGNsb3NlIHRoZW0gJm1kYXNoOyB0aGV5IGNhbiBvbmx5IG1hdGNoIHRoZSBob25l"
    "c3R5LCB3aGljaCBjb3N0cyB0aGVtIHRoZWlyIGV4aXN0aW5nIG1hcmtldGluZy48L3A+CgogIDxkaXYgY2xhc3M9InZlcmlmeS1i"
    "b3giPgogICAgPGg0PlZlcmlmeSB0aGUgdGVjaG5pY2FsIGNsYWltcyBiZWZvcmUgcmVhZGluZyBmdXJ0aGVyPC9oND4KICAgIDxw"
    "Pk5vdGhpbmcgaGVyZSByZXF1aXJlcyB0cnVzdGluZyB0aGUgZG9jdW1lbnQuIDxjb2RlPi9hcGkvdmVyaWZ5LWNoYWluPC9jb2Rl"
    "PiByZWNvbXB1dGVzIHRoZSBlbnRpcmUgY2hhaW4gYW5kIHJlcG9ydHMgd2hldGhlciBpdCBpcyBpbnRhY3QuIDxjb2RlPi9hcGkv"
    "YW5jaG9yLXN0YXR1czwvY29kZT4gcmV0dXJucyB0aGUgbGl2ZSBjaGFpbiB0aXAsIGl0cyBPcGVuVGltZXN0YW1wcyBwcm9vZiBh"
    "bmQgdGhlIG51bWJlciBvZiBpbmRlcGVuZGVudCBjYWxlbmRhciBzZXJ2ZXJzIHRoYXQgaGF2ZSBzdGFtcGVkIGl0LiA8Y29kZT4v"
    "eC93aXRuZXNzL2F0dGVzdDwvY29kZT4gYW5zd2VycyB3aGV0aGVyIGEgZ2l2ZW4gcGVlciB0aXAgd2FzIHdpdG5lc3NlZCBhbmQg"
    "d2hlbi48L3A+CiAgICA8cCBzdHlsZT0ibWFyZ2luLWJvdHRvbTowIj5BbGwgdGhyZWUgYXJlIHB1YmxpYywgbmVlZCBubyBhY2Nv"
    "dW50LCBhbmQgYW5zd2VyIHRvIGFueW9uZS48L3A+CiAgPC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0iYmxvY2siPgogIDxkaXYg"
    "Y2xhc3M9ImJsb2NrLW51bSI+QmxvY2sgMDQgJm1kYXNoOyBXaGVyZSBUaGluZ3MgQWN0dWFsbHkgU3RhbmQ8L2Rpdj4KICA8aDI+"
    "VG9sZCBzdHJhaWdodCwgbm90IHNwdW4uPC9oMj4KICA8cD5UZWNobmljYWwgYW5kIHJlZ3VsYXRvcnkgY3JlZGliaWxpdHkgbm93"
    "LiBDb21tZXJjaWFsIHRyYWN0aW9uIHN0aWxsIGFoZWFkLiBUaGF0IGlzIHRoZSBob25lc3QgcGljdHVyZSBhbmQgaXQgaXMgcHJl"
    "Y2lzZWx5IHdoeSB0aGlzIGlzIGEgc2VlZCByb3VuZCByYXRoZXIgdGhhbiBhIGxhdGVyIG9uZS48L3A+CiAgPGRpdiBjbGFzcz0i"
    "c3RhdHVzLWxpc3QiPgogICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFzcz0ic3RhdHVzLWljb24geWVzIj5ZRVM8"
    "L2Rpdj48ZGl2IGNsYXNzPSJzdGF0dXMtdGV4dCI+PHN0cm9uZz5QbGF0Zm9ybSBsaXZlIGluIHByb2R1Y3Rpb248L3N0cm9uZz4g"
    "Jm1kYXNoOyA8c3Bhbj5yZWFsIGluZnJhc3RydWN0dXJlLCBwdWJsaWNseSB2ZXJpZmlhYmxlLCBub3QgYSBkZW1vIGVudmlyb25t"
    "ZW50PC9zcGFuPjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFzcz0ic3RhdHVzLWljb24g"
    "eWVzIj5ZRVM8L2Rpdj48ZGl2IGNsYXNzPSJzdGF0dXMtdGV4dCI+PHN0cm9uZz5PZmNvbSBzdWJtaXNzaW9uIGFja25vd2xlZGdl"
    "ZDwvc3Ryb25nPiAmbWRhc2g7IDxzcGFuPndoaXRlcGFwZXIgc3VibWl0dGVkIHRvIHRoZSBBZGRpdGlvbmFsIFNhZmV0eSBNZWFz"
    "dXJlcyBjb25zdWx0YXRpb24sIHdpdGggcHVibGljYXRpb24gY29uc2VudCBncmFudGVkPC9zcGFuPjwvZGl2PjwvZGl2PgogICAg"
    "PGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFzcz0ic3RhdHVzLWljb24geWVzIj5ZRVM8L2Rpdj48ZGl2IGNsYXNzPSJz"
    "dGF0dXMtdGV4dCI+PHN0cm9uZz5BbiBvcmdhbmlzYXRpb24gYWN0aXZlbHkgdGVzdGluZyB0aGUgQVBJPC9zdHJvbmc+ICZtZGFz"
    "aDsgPHNwYW4+YSBzaWduZWQtdXAgYWNjb3VudCBoYXMgcHV0IGxpdmUgY2FsbHMgdGhyb3VnaCB0aGUgZW5naW5lPC9zcGFuPjwv"
    "ZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFzcz0ic3RhdHVzLWljb24geWVzIj5ZRVM8L2Rp"
    "dj48ZGl2IGNsYXNzPSJzdGF0dXMtdGV4dCI+PHN0cm9uZz5JbmJvdW5kIGludGVyZXN0IGZyb20gdGhlIHNlY3Rvcjwvc3Ryb25n"
    "PiAmbWRhc2g7IDxzcGFuPmluY2x1ZGluZyBhIGJvYXJkLWxldmVsIGNvbnRhY3QgaW4gcmVndWxhdGVkIGZpbmFuY2lhbCBzZXJ2"
    "aWNlcywgYW5kIHByb2ZpbGUtbGV2ZWwgaW50ZXJlc3QgZnJvbSBhIGNvbXBldGluZyBnb3Zlcm5hbmNlIHBsYXRmb3JtPC9zcGFu"
    "PjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFzcz0ic3RhdHVzLWljb24gbm8iPk5PPC9k"
    "aXY+PGRpdiBjbGFzcz0ic3RhdHVzLXRleHQiPjxzdHJvbmc+UGF5aW5nIGN1c3RvbWVyczwvc3Ryb25nPiAmbWRhc2g7IDxzcGFu"
    "Pm5vbmUgY29uZmlybWVkLiBUaGlzIGlzIHRoZSBnYXAgdGhlIHJhaXNlIGNsb3NlcywgYW5kIGl0IHNob3VsZCBiZSByZWFkIGFz"
    "IHRoZSBjZW50cmFsIHJpc2suPC9zcGFuPjwvZGl2PjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RhdHVzLXJvdyI+PGRpdiBjbGFz"
    "cz0ic3RhdHVzLWljb24gbm8iPk5PPC9kaXY+PGRpdiBjbGFzcz0ic3RhdHVzLXRleHQiPjxzdHJvbmc+RXh0ZXJuYWwgc2VjdXJp"
    "dHkgYXVkaXQ8L3N0cm9uZz4gJm1kYXNoOyA8c3Bhbj5ub3QgeWV0IGNvbW1pc3Npb25lZC4gQnVkZ2V0ZWQgd2l0aGluIHRoaXMg"
    "cm91bmQuPC9zcGFuPjwvZGl2PjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNsYXNz"
    "PSJibG9jay1udW0iPkJsb2NrIDA1ICZtZGFzaDsgUm91dGUgdG8gUmV2ZW51ZTwvZGl2PgogIDxoMj5TZWxsIHRvIHRoZSBwbGF0"
    "Zm9ybXMsIG5vdCBvbmUgY3VzdG9tZXIgYXQgYSB0aW1lLjwvaDI+CiAgPHA+VHdlbnR5IG1vbnRocyBvZiBkaXJlY3Qgc2VsbGlu"
    "ZyBwcm9kdWNlZCBubyByZXZlbnVlLiBUaGUgZGlhZ25vc2lzIGlzIG5vdCB0aGUgcHJvZHVjdDogY29tcGxpYW5jZSBpbmZyYXN0"
    "cnVjdHVyZSBpcyBib3VnaHQgb24gYSB0cmlnZ2VyICZtZGFzaDsgYW4gYXVkaXQsIGEgcmVndWxhdG9yIGxldHRlciwgYSBjdXN0"
    "b21lciBxdWVzdGlvbm5haXJlICZtZGFzaDsgYW5kIGEgc2luZ2xlIGZvdW5kZXIgY2Fubm90IGJlIGluIGZyb250IG9mIGVub3Vn"
    "aCB0cmlnZ2VyZWQgYnV5ZXJzIHRvIG1ha2UgZGlyZWN0IHNhbGVzIHdvcmsuPC9wPgogIDxwPlRoZSBjdXJyZW50IHN0cmF0ZWd5"
    "IGludmVydHMgaXQuIE90aGVyIGNvbXBsaWFuY2UgcGxhdGZvcm1zIGFscmVhZHkgaG9sZCByZWxhdGlvbnNoaXBzIHdpdGggdHJp"
    "Z2dlcmVkIGJ1eWVycyBhbmQgYXJlIHVuaWZvcm1seSB3ZWFrIG9uIGV2aWRlbmNlLiBUaGUgZW5naW5lIGlzIG9mZmVyZWQgdG8g"
    "dGhlbSBhcyBhbiBldmlkZW5jZSBsYXllciBiZW5lYXRoIHRoZWlyIG93biBwcm9kdWN0LCBhdCA1MHAgcGVyIGRldmljZSBwZXIg"
    "bW9udGgsIHdoaWNoIHRoZXkgbWFyayB1cC48L3A+CiAgPHVsPgogICAgPGxpPjxiPkZvdW5kaW5nIGNvaG9ydCBvZiB0d2VudHkg"
    "cGxhdGZvcm1zPC9iPiAmbWRhc2g7IGZyZWUgaW50ZWdyYXRpb24sIHByaWNpbmcgbG9ja2VkLCBhIHNheSBpbiB0aGUgc3BlY2lm"
    "aWNhdGlvbiwgYW5kIHRoZSBsaXZlIHZlcmlmaWNhdGlvbiBtYXJrIGZvciB0aGVpciBvd24gc2l0ZS48L2xpPgogICAgPGxpPjxi"
    "PkNvbXBvdW5kaW5nIGVmZmVjdDwvYj4gJm1kYXNoOyBlYWNoIGludGVncmF0aW5nIHBsYXRmb3JtIHN0cmVuZ3RoZW5zIHRoZSB3"
    "aXRuZXNzIG5ldHdvcmsgZm9yIHRoZSBvdGhlcnMsIHNvIGVhcmx5IHBhcnRpY2lwYW50cyBnYWluIGZyb20gbGF0ZXIgb25lcyBq"
    "b2luaW5nLjwvbGk+CiAgICA8bGk+PGI+VGhlIHN0YW5kYXJkIGFzIHRoZSBsb25nIGdhbWU8L2I+ICZtZGFzaDsgd2hvZXZlciB3"
    "cml0ZXMgdGhlIGludGVncmF0aW9uIHNwZWNpZmljYXRpb24gdGhlIG1hcmtldCBhZG9wdHMgaG9sZHMgYSBwb3NpdGlvbiBubyBm"
    "ZWF0dXJlIGNhbiBkaXNsb2RnZS48L2xpPgogIDwvdWw+CiAgPHA+VGhpcyBpcyBhIGRpc3RyaWJ1dGlvbiB0aGVzaXMgcmF0aGVy"
    "IHRoYW4gYSBwcm9kdWN0IHRoZXNpcywgYW5kIGl0IGlzIHRoZSByZWFzb24gdGhlIHJhaXNlIGZ1bmRzIHNhbGVzIGNhcGFjaXR5"
    "IGFoZWFkIG9mIGVuZ2luZWVyaW5nLjwvcD4KPC9kaXY+Cgo8ZGl2IGNsYXNzPSJibG9jayI+CiAgPGRpdiBjbGFzcz0iYmxvY2st"
    "bnVtIj5CbG9jayAwNiAmbWRhc2g7IFRoZSBBc2s8L2Rpdj4KICA8aDI+JnBvdW5kOzUwMCwwMDAuIEEgc3BlY2lmaWMgcGxhbiwg"
    "bm90IGEgcGxhY2Vob2xkZXIuPC9oMj4KICA8cD5BIHByZS1yZXZlbnVlIHNlZWQgcm91bmQuIFRoZSBtb25leSBmdW5kcyB0aGUg"
    "Z2FwIGJldHdlZW4gYSB3b3JraW5nIHBsYXRmb3JtIGFuZCBhIHByb3ZlbiBvbmU6IGdvaW5nIGZ1bGwtdGltZSwgbGFuZGluZyB0"
    "aGUgZm91bmRpbmcgY29ob3J0LCBhbmQgYnVpbGRpbmcgdGhlIGV2aWRlbmNlIGJhc2UgYSBsYXJnZXIgcm91bmQgd291bGQgcmVx"
    "dWlyZS48L3A+CiAgPGRpdiBjbGFzcz0iYXNrLWJveCI+CiAgICA8ZGl2IGNsYXNzPSJhc2stbGFiZWwiPlJhaXNpbmc8L2Rpdj4K"
    "ICAgIDxkaXYgY2xhc3M9ImFzay1hbW91bnQiPiZwb3VuZDs1MDAsMDAwPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJ1c2Utb2YtZnVu"
    "ZHMiPgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPkZvdW5kZXIgc2FsYXJ5IChmdWxsLXRpbWUpPC9zcGFuPjxzcGFu"
    "IGNsYXNzPSJ1Zi1wY3QiPn4yNSU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+Rmlyc3QgdGVj"
    "aG5pY2FsL3NhbGVzIGhpcmU8L3NwYW4+PHNwYW4gY2xhc3M9InVmLXBjdCI+fjMwJTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBj"
    "bGFzcz0idWYtcm93Ij48c3Bhbj5FeHRlcm5hbCBzZWN1cml0eSBhdWRpdCwgbGVnYWwgcmV2aWV3IG9mIGNsYWltcyBhbmQgY29u"
    "dHJhY3RzPC9zcGFuPjxzcGFuIGNsYXNzPSJ1Zi1wY3QiPn4xNSU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InVmLXJv"
    "dyI+PHNwYW4+SW5mcmFzdHJ1Y3R1cmUgc2NhbGluZyBhbmQgcmVkdW5kYW5jeTwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5+"
    "MTUlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPlJ1bndheSBidWZmZXIgKDE4IG1vbnRocyk8"
    "L3NwYW4+PHNwYW4gY2xhc3M9InVmLXBjdCI+fjE1JTwvc3Bhbj48L2Rpdj4KICAgIDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxk"
    "aXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPkJsb2NrIDA3ICZtZGFzaDsgUmlzaywgTmFtZWQgUGxh"
    "aW5seTwvZGl2PgogIDxoMj5XaGF0IGNvdWxkIGdvIHdyb25nLjwvaDI+CiAgPGRpdiBjbGFzcz0icmlzay1ib3giPgogICAgPGg0"
    "Pk5vIGN1c3RvbWVycyB5ZXQ8L2g0PgogICAgPHA+VGhlIGNlbnRyYWwgY29tbWVyY2lhbCByaXNrLCBhbmQgaXQgaGFzIHBlcnNp"
    "c3RlZCBmb3IgdHdlbnR5IG1vbnRocy4gVGhlIHBsYXRmb3JtIHN0cmF0ZWd5IGlzIGEgcmVzcG9uc2UgdG8gdGhhdCwgbm90IGEg"
    "aGVkZ2UgYWdhaW5zdCBpdC4gSWYgdGhlIGZvdW5kaW5nIGNvaG9ydCBkb2VzIG5vdCBmaWxsLCB0aGUgdGhlc2lzIGlzIHdyb25n"
    "IGFuZCBzaG91bGQgYmUgdHJlYXRlZCBhcyBzdWNoLjwvcD4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJyaXNrLWJveCI+CiAgICA8"
    "aDQ+U29sby1idWlsdCwgc2luZ2xlIHBvaW50IG9mIGZhaWx1cmU8L2g0PgogICAgPHA+RGVlcCBmb3VuZGVyIGtub3dsZWRnZSwg"
    "YnV0IGtleS1wZXJzb24gZGVwZW5kZW5jeSBhbmQgbm8gZXh0ZXJuYWwgY29kZSByZXZpZXcgdG8gZGF0ZS4gUGFydCBvZiB0aGlz"
    "IHJhaXNlIGlzIGhpcmluZyBhbmQgY29tbWlzc2lvbmluZyBhbiBhdWRpdCBzcGVjaWZpY2FsbHkgdG8gcmVkdWNlIGJvdGguPC9w"
    "PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InJpc2stYm94Ij4KICAgIDxoND5JbmZyYXN0cnVjdHVyZSBjb25jZW50cmF0aW9uPC9o"
    "ND4KICAgIDxwPlNpbmdsZSBob3N0aW5nIHByb3ZpZGVyLCBzaW5nbGUgcmVwbGljYSwgU1FMaXRlLiBBZGVxdWF0ZSBhdCBjdXJy"
    "ZW50IGxvYWQgYW5kIGluYWRlcXVhdGUgYXQgc2NhbGUuIEJ1ZGdldGVkIHdpdGhpbiB0aGlzIHJvdW5kIGFuZCBzdGF0ZWQgaGVy"
    "ZSByYXRoZXIgdGhhbiBkaXNjb3ZlcmVkIGxhdGVyLjwvcD4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJyaXNrLWJveCI+CiAgICA8"
    "aDQ+UmVndWxhdG9yeSB0aW1pbmc8L2g0PgogICAgPHA+VGhlIGhpZ2gtcmlzayBkZWFkbGluZSBoYXMgYWxyZWFkeSBtb3ZlZCBv"
    "bmNlLiBJdCBjb3VsZCBtb3ZlIGFnYWluLCB3aGljaCB3b3VsZCBleHRlbmQgdGhlIHNhbGVzIGN5Y2xlLiBUaGUgaGlzdG9yaWNh"
    "bC1ldmlkZW5jZSBhcmd1bWVudCBob2xkcyByZWdhcmRsZXNzIG9mIHRoZSBkYXRlLCBidXQgdGhlIHVyZ2VuY3kgZG9lcyBub3Qu"
    "PC9wPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9InJpc2stYm94Ij4KICAgIDxoND5Db21wZXRpdGl2ZSBjYXRlZ29yeTwvaDQ+CiAg"
    "ICA8cD5BSSBjb21wbGlhbmNlIHRvb2xpbmcgaXMgYW4gYWN0aXZlIHNwYWNlIHdpdGggd2VsbC1mdW5kZWQgZW50cmFudHMuIERp"
    "ZmZlcmVudGlhdGlvbiByZXN0cyBvbiB0aGUgdmVyaWZpYWJsZSBldmlkZW5jZSBsYXllciBhbmQgb24gcHVibGlzaGVkIGxpbWl0"
    "YXRpb25zLCBub3Qgb24gYmVpbmcgZmlyc3QuPC9wPgogIDwvZGl2Pgo8L2Rpdj4KCjwvZGl2PgoKPGRpdiBjbGFzcz0iY29udGFj"
    "dC1ibG9jayB3cmFwIj4KICA8ZGl2IGNsYXNzPSJjb250YWN0LWNhcmQiPgogICAgPGgzPkdldCBpbiB0b3VjaCBkaXJlY3RseTwv"
    "aDM+CiAgICA8cD5IYXBweSB0byB3YWxrIHRocm91Z2ggdGhlIHBsYXRmb3JtIGxpdmUsIHNoYXJlIHRoZSBPZmNvbSBzdWJtaXNz"
    "aW9uLCBvciBnbyBkZWVwZXIgb24gdGhlIGNoYWluIGFyY2hpdGVjdHVyZSBhbmQgdGhlIHdpdG5lc3MgbW9kZWwuPC9wPgogICAg"
    "PGRpdiBjbGFzcz0iY29udGFjdC1saW5rcyI+CiAgICAgIDxhIGhyZWY9Im1haWx0bzpqdXN0cmlnaHRkZWNvcmF0b3JzQGdtYWls"
    "LmNvbSI+anVzdHJpZ2h0ZGVjb3JhdG9yc0BnbWFpbC5jb208L2E+CiAgICAgIDxhIGhyZWY9InRlbDowNzkwODI2OTQyOCI+MDc5"
    "MDggMjY5NDI4PC9hPgogICAgICA8YSBocmVmPSJodHRwczovL3NlYmJpLnBybyI+c2ViYmkucHJvPC9hPgogICAgICA8YSBocmVm"
    "PSJodHRwczovL3NlYmJpLnByby93aGl0ZXBhcGVyIj5zZWJiaS5wcm8vd2hpdGVwYXBlcjwvYT4KICAgIDwvZGl2PgogIDwvZGl2"
    "Pgo8L2Rpdj4KCjxmb290ZXIgY2xhc3M9IndyYXAiPgogIDxwPkp1c3RpbiBBbnRvbnkgRG9ic29uICZtaWRkb3Q7IE1vbm9wIENv"
    "bnRlbnQgJm1pZGRvdDsgQmx5dGgsIE5vcnRodW1iZXJsYW5kLCBVSzxicj4KICBUaGlzIGRvY3VtZW50IGlzIGEgc3VtbWFyeSBm"
    "b3IgaW5mb3JtYXRpb25hbCBwdXJwb3NlcyBhbmQgZG9lcyBub3QgY29uc3RpdHV0ZSBhbiBvZmZlciBvZiBzZWN1cml0aWVzLiBB"
    "bGwgZmlndXJlcyBhcmUgc3RhdGVkIGFzIG9mIHRoZSBkYXRlIGFib3ZlIGFuZCBzaG91bGQgYmUgaW5kZXBlbmRlbnRseSB2ZXJp"
    "ZmllZCBiZWZvcmUgYW55IGludmVzdG1lbnQgZGVjaXNpb24uIFJlZ3VsYXRvcnkgZGF0ZXMgYXJlIHN0YXRlZCBhcyBhbWVuZGVk"
    "IGJ5IHRoZSBBSSBPbW5pYnVzIGFuZCBhcmUgc3ViamVjdCB0byBmdXJ0aGVyIGNoYW5nZS48L3A+CjwvZm9vdGVyPgoKPHNjcmlw"
    "dD4KICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG9jLWRhdGUnKS50ZXh0Q29udGVudCA9IG5ldyBEYXRlKCkudG9Mb2NhbGVE"
    "YXRlU3RyaW5nKCdlbi1HQicse2RheTonbnVtZXJpYycsbW9udGg6J2xvbmcnLHllYXI6J251bWVyaWMnfSk7CiAgdmFyIGRlYWRs"
    "aW5lID0gbmV3IERhdGUoJzIwMjctMTItMDJUMDA6MDA6MDBaJyk7CiAgdmFyIG5vdyA9IG5ldyBEYXRlKCk7CiAgdmFyIGRheXMg"
    "PSBNYXRoLm1heCgwLCBNYXRoLmNlaWwoKGRlYWRsaW5lIC0gbm93KSAvICgxMDAwKjYwKjYwKjI0KSkpOwogIGRvY3VtZW50Lmdl"
    "dEVsZW1lbnRCeUlkKCdjb3VudGRvd24tZGF5cycpLnRleHRDb250ZW50ID0gZGF5cy50b0xvY2FsZVN0cmluZygpICsgJyBkYXlz"
    "JzsKPC9zY3JpcHQ+Cgo8L2JvZHk+CjwvaHRtbD4K"
)

_HTML = base64.b64decode("".join(_B64.split())).decode("utf-8")
_patched = False


def _find_handler_class(ctx):
    """
    Find the BaseHTTPRequestHandler subclass to patch, without assuming a ctx
    key name. Try common ctx keys first, then walk the stack for a live handler.
    """
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    # Fallback: walk the call stack for the handler instance serving this call.
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
    if getattr(cls, "_investor_patched", False):
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
    cls._investor_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)

    if action == "spec":
        return ({
            "module": "investor",
            "version": VERSION,
            "serves": PAGE_PATH,
            "public": [["GET", "status"], ["GET", "spec"]],
            "note": "Hit /x/investor/status once after each deploy to arm "
                    + PAGE_PATH + ".",
        }, 200)

    return ({
        "module": "investor",
        "version": VERSION,
        "serves": PAGE_PATH,
        "armed": armed,
        "page_bytes": len(_HTML),
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
