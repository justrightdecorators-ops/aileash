# Codebase — part 7 of 30

Contains:
- `modules/investor.py`
- `modules/lineage.py`
- `modules/mutual.py`
- `modules/network.py`


## `modules/investor.py`

384 lines, 32871 bytes

```python
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

```


## `modules/lineage.py`

330 lines, 15462 bytes

```python
import re
import time
from datetime import datetime, timezone

VERSION = "1.1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec")}

OUR_CHAIN_NAME = "aileash"
DEFAULT_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS lineage_edge("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,"
                  "child_chain TEXT,child_receipt TEXT,"
                  "parent_chain TEXT,parent_receipt TEXT,parent_base TEXT,"
                  "role TEXT,note TEXT,declared REAL,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_child "
                  "ON lineage_edge(child_receipt)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lin_parent "
                  "ON lineage_edge(parent_receipt)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lin_unique "
                  "ON lineage_edge(child_receipt,parent_chain,parent_receipt)")
        c.commit()
    _ready = True


def _get_base_url(ctx):
    if isinstance(ctx, dict):
        base = ctx.get("base_url") or (ctx.get("config") or {}).get("base_url")
        if base:
            return str(base).rstrip("/")
    return DEFAULT_BASE


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _clean_chain(value):
    value = str(value or "").strip().lower()
    return value[:80] if value else ""


def _exists_locally(ctx, receipt):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1", (receipt,)).fetchone()
        return bool(row)
    except Exception:
        return False


def _verification_plan(chain, receipt, base=None, our_base=DEFAULT_BASE):
    root = (base or our_base).rstrip("/") if chain != OUR_CHAIN_NAME else our_base
    if chain != OUR_CHAIN_NAME and not base:
        return {
            "chain": chain, "receipt": receipt,
            "status": "external, no address declared",
            "how_to_check": "Ask that chain's operator for their public witness and consistency "
                            "routes, or look for their name at %s/x/witness/peers - if we have "
                            "ever witnessed them, the address we fetched from is recorded "
                            "there." % our_base,
        }
    return {
        "chain": chain, "receipt": receipt, "base": root,
        "on_their_chain": "%s/x/consistency/ancestor?tip=%s" % (root, receipt),
        "nothing_was_omitted": "%s/x/complete/periods" % root,
        "who_witnesses_them": "%s/x/witness/peers" % root,
        "did_we_witness_them": "%s/x/witness/attest?peer=%s&tip=%s" % (our_base, chain, receipt),
        "note": "Run these against their host, not ours. If their answers and ours disagree, "
                "that disagreement is the finding.",
    }


def _declare(ctx, api_key, data):
    our_base = _get_base_url(ctx)
    child = str(data.get("receipt", data.get("child", ""))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(data.get("chain") or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs", "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared = []
    for item in inputs:
        if not isinstance(item, dict):
            return {"error": "bad_input", "message": "each input must be an object"}, 400
        parent = str(item.get("receipt", "")).strip().lower()
        if not HEX64.match(parent):
            return {"error": "bad_input_receipt",
                    "message": "every input needs a 64 character hex receipt"}, 400
        parent_chain = _clean_chain(item.get("chain") or OUR_CHAIN_NAME)
        if parent_chain == child_chain and parent == child:
            return {"error": "self_reference",
                    "message": "a decision cannot be its own input"}, 400
        role = str(item.get("role", "input")).strip().lower()
        if role not in ROLES:
            role = "other"
        base = str(item.get("base", item.get("url", "")) or "").strip()[:300]
        note = str(item.get("note", "") or "").strip()[:200]
        prepared.append((parent_chain, parent, base, role, note))

    now = time.time()
    summary = ";".join("%s/%s:%s" % (c, r[:12], role) for c, r, _b, role, _n in prepared)
    ev = {"user_id": "lin:" + child[:16], "action": "lineage_declared", "amount": 0,
          "country": "UK", "device_id": "lineage", "anomaly": 0, "device_risk": 0}
    res = {"decision": "LINEAGE_SEALED", "score": 0, "lineage_version": VERSION,
           "child_chain": child_chain, "child_receipt": child,
           "input_count": len(prepared),
           "detail": "child=%s;inputs=%s" % (child, summary)}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    written, duplicates = 0, 0
    with ctx["lock"]:
        for parent_chain, parent, base, role, note in prepared:
            try:
                ctx["conn"].execute(
                    "INSERT INTO lineage_edge(api_key,child_chain,child_receipt,parent_chain,"
                    "parent_receipt,parent_base,role,note,declared,audit_hash,block_index) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (api_key, child_chain, child, parent_chain, parent, base or None,
                     role, note or None, now, audit_hash, block_index))
                written += 1
            except Exception:
                duplicates += 1
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (our_base, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (our_base, child)}, 200


def _walk(ctx, start, depth, upstream):
    our_base = _get_base_url(ctx)
    seen = {start}
    nodes, edges, frontier = [], [], []
    queue = [(start, 0)]
    truncated = False

    while queue:
        receipt, level = queue.pop(0)
        if level >= depth or len(nodes) >= MAX_NODES:
            if queue or level >= depth:
                truncated = truncated or bool(queue)
            continue

        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)
        for row in rows:
            if upstream:
                chain, other, base, role, note, declared, sealed = row
            else:
                chain, other, role, declared, sealed = row
                base, note = None, None

            edges.append({
                "from": other if upstream else receipt,
                "to": receipt if upstream else other,
                "role": role, "note": note,
                "declared_at": _iso(declared),
                "declaration_sealed_as": sealed,
                "chain": chain,
            })

            local = (chain == OUR_CHAIN_NAME) and _exists_locally(ctx, other)
            if not local:
                if not any(f["receipt"] == other for f in frontier):
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base, our_base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base, our_base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated


def _trace(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)
    our_base = _get_base_url(ctx)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [],
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "lineage_version": VERSION,
            "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base),
            "how_to_verify_this": "Every node carries the routes to check it on its own chain. "
                                  "Nothing here asks you to take our word for a hop, including "
                                  "the hops on our own chain.",
            "what_an_edge_is": "A sealed, dated claim by the declaring party that these inputs "
                               "fed that decision. Sealing makes it non-repudiable, not true.",
            "frontier_note": "External entries are named but not resolved here. Run their "
                             "verification plans against their own hosts - that is what makes "
                             "the graph checkable without a shared database."}, 200


def _impact(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated = _walk(ctx, receipt, depth, upstream=False)
    affected = len(nodes)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": affected, "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "lineage_version": VERSION,
            "what_this_is_for": "If this input is retracted, wrong, or overturned, these are the "
                                "decisions that declared a dependency on it. This is the answer "
                                "to the first question asked after any upstream failure, and it "
                                "normally takes weeks of email to assemble incompletely.",
            "corrective_action": "The list is itself sealed and dated, so the scope of a recall "
                                 "can be shown to have been determined honestly rather than "
                                 "narrowed to suit.",
            "limits": "Only covers dependencies that were declared. A downstream party who "
                      "declared nothing does not appear - which is a fact about them rather "
                      "than a gap here."}, 200


def _receipt(ctx, data):
    receipt = str(data.get("receipt", "")).strip().lower()
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    our_base = _get_base_url(ctx)
    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "verify": _verification_plan(r[0], r[1], r[2], our_base=our_base)} for r in rows]

    return {
        "format": "aileash-portable-receipt",
        "lineage_version": VERSION,
        "chain": OUR_CHAIN_NAME,
        "receipt": receipt,
        "inputs": inputs,
        "verify_this_decision": {
            "still_on_our_chain": "%s/x/consistency/ancestor?tip=%s" % (our_base, receipt),
            "our_log_is_append_only": "%s/x/consistency/proof" % our_base,
            "nothing_was_left_out": "%s/x/complete/periods" % our_base,
            "who_witnesses_us": "%s/x/witness/peers" % our_base,
            "our_current_tip": "%s/x/witness/tip" % our_base,
            "the_engine_reproduces": "%s/x/replay/spec" % our_base,
            "trace_upstream": "%s/x/lineage/trace?receipt=%s" % (our_base, receipt),
        },
        "offline_verifier": "aileash_verify.py - one file, no dependencies, no network. Save "
                            "this document and check it on your own machine, today or in four "
                            "years.",
        "what_you_can_establish": [
            "this decision is in a log that has not been rewritten",
            "that log is witnessed by parties we do not control",
            "the period it sits in declared its total before anyone asked",
            "the same inputs still produce the same verdict",
            "and what fed it, hop by hop, across every company involved",
        ],
        "what_you_cannot": "That the decision was right, or that the inputs were honest. "
                           "Cryptography establishes what happened and when. It does not "
                           "establish that what happened was correct, and anybody telling you "
                           "otherwise is selling something.",
        "send_this_on": "Attach it to the output it describes. Whoever receives it can verify "
                        "without an account, without contacting us, and without trusting anyone "
                        "in the chain including the sender.",
    }, 200

```


## `modules/mutual.py`

543 lines, 19704 bytes

```python
#!/usr/bin/env python3
"""
modules/mutual.py  -  the outbound half of mutual witnessing
============================================================

Why this exists
---------------
modules/witness.py RECEIVES. Other chains hand us their tips and we seal
them. Nothing in the platform currently SENDS our tip anywhere, so right
now we witness other people and nobody witnesses us. This module is the
missing direction.

Drop it in as modules/mutual.py. The router picks it up automatically -
no edits to server.py.

Routes
------
  POST /x/mutual/push      send our current tip to every configured peer
  POST /x/mutual/pull      fetch every peer's tip and seal it into our chain
  POST /x/mutual/sync      pull then push (this is the one to schedule)
  GET  /x/mutual/peers     the configured peers and what happened last time
  GET  /x/mutual/status    last run, next run, whether the timer is alive

Important design note
---------------------
This module does not touch the database or import anything from server.py.
It talks HTTP to routes that are already public - ours and theirs. That
means it cannot corrupt anything, it works no matter how seal() changes,
and every action it takes is one an outsider could audit for themselves.

To read our own tip it calls our own public /x/witness/tip.
To seal a peer's tip it calls our own public /x/witness/observe, which is
already built to record exactly that. So a peer tip we pull is recorded by
the same code path as a peer tip that was pushed to us.

FETCH-ONLY PEERS (added 1.2)
----------------------------
observe_url is now OPTIONAL. A peer with a tip_url and no observe_url is
fetch-only: we read and seal their tip, and we do not try to push ours.

That is a real configuration, not a broken one. Two current cases:

  A peer whose outbound submission lane is deliberately closed during
  staging. They serve a tip for us to read; their recorder never reaches
  out. Serving a file is not outbound submission.

  A peer whose tip is a static JSON file with no server behind it. They
  push to us on their own schedule and there is nothing on their side to
  POST to. Perfectly valid node.

Before 1.2 push_one read peer["observe_url"] unconditionally, so adding a
fetch-only peer would have raised KeyError on every cycle - inside a
background thread with a bare except, so it would have failed silently and
taken the whole sync with it.

CONCURRENCY - read this before changing it
------------------------------------------
A sync cycle makes two kinds of call, and they are treated differently on
purpose.

  OUTBOUND to other people's hosts (reading their tip, pushing ours) runs
  in parallel. These are the slow ones - we are waiting on somebody else's
  server, and there is no reason to wait on them one at a time. Fifty peers
  now costs roughly what the slowest single peer costs, instead of the sum
  of all fifty.

  INBOUND to our own server (sealing what we pulled) stays sequential. Our
  own process is handling those requests, and firing a burst of them at
  ourselves while we are mid-cycle is asking for trouble - a queue behind a
  single replica at best. The sealing is fast and local anyway, so there is
  nothing to gain by parallelising it and a real risk in doing so.

So: fetch everything at once, then seal one at a time.

BEFORE THIS WORKS
-----------------
1. "observe" must be in the PUBLIC set of modules/witness.py. If it is not,
   this module gets a 401 from our own server, same as Red Flag AI Pro did.
2. After every deploy, the first /x/ request must be a GET - that is what
   installs the POST branch. Opening /x/mutual/peers in a browser does it.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

VERSION = "1.2"

# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------

# The router reads a set of (METHOD, action) tuples. Anything not listed
# here needs an API key - default is closed.
#
# peers and status are read-only. An outsider being able to see who we
# witness with, and whether it is actually running, is the entire point.
#
# push, pull and sync stay keyed - they cause outbound traffic and are not
# left open to anonymous callers.
PUBLIC = {("GET", "peers"), ("GET", "status")}


# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

# Our own public witness routes. Left as full URLs on purpose so this
# module never has to guess its own host.
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"
OUR_OBSERVE_URL = "https://sebbi.pro/x/witness/observe"

# The name we go by when we hand our tip to someone else.
OUR_CHAIN_NAME = "aileash"

# Everyone we witness with. Add a dict per chain.
#   name         what we file their tips under
#   tip_url      where we GET their current tip          REQUIRED
#   observe_url  where we POST ours so they record it    OPTIONAL
#
# Omit observe_url for a fetch-only peer - see the note at the top. It is
# not an oversight and the module will not complain about it; /x/mutual/peers
# reports the direction for each so it is visible rather than assumed.
PEERS = [
    {
        "name": "red-flag-ai-pro",
        "tip_url": "https://www.redflagaipro.com/api/witness/tip",
        "observe_url": "https://www.redflagaipro.com/api/witness/anchor",
    },
    {
        # Simon. Serves a static JSON file regenerated on his side, and
        # pushes to us on his own systemd timer at :23. Nothing to POST to.
        "name": "flavorflowstrategy.uk",
        "tip_url": "https://www.flavorflowstrategy.uk/witness.json",
    },
    {
        # PRAXIS / Praesidium, chain 4. Read-only, hash-only, currently
        # SYNTHETIC_STAGING and regenerating every ten minutes, so expect
        # liveness "live" rather than "self-consistent" - the tip moves
        # between their generating it and our fetching it. That is the
        # normal case for a working chain, not a failure.
        #
        # Their outbound submission lane is deliberately closed through
        # staging, so no observe_url. They also run a signed lane at
        # /x/peer/submit under peer_id praesidium when they are ready.
        "name": "praesidium",
        "tip_url": "https://chain4.thepraesidium.ai/api/witness/tip",
    },
]

# Field names to send when pushing our tip. If a peer wants different
# names, give that peer its own "keys" dict and it will be used instead.
DEFAULT_PUSH_KEYS = {
    "chain": "chain",
    "tip": "tip",
    "count": "count",
    "ts": "ts",
    "url": "url",
}

# Where peers can read our tip, included in what we push.
OUR_PUBLIC_URL = "https://sebbi.pro/x/witness/tip"

# Background timer. Set ENABLED to False if you would rather drive it
# yourself by hitting /x/mutual/sync.
AUTO_SYNC_ENABLED = True
AUTO_SYNC_SECONDS = 3600

TIMEOUT_SECONDS = 20

# How many peers we talk to at once. Above this they queue, which is fine -
# it stops a large network spawning a thread per peer. Eight slow peers at
# 20s each still finishes in 20s; forty finishes in about a minute worst
# case, and only if every one of them times out.
MAX_PARALLEL_PEERS = 8

# ----------------------------------------------------------------------
# state - deliberately in memory only, this is not evidence
# ----------------------------------------------------------------------

_state = {
    "last_run": None,
    "last_result": None,
    "runs": 0,
    "timer_started": False,
}
_lock = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _reply(payload, status=200):
    """The router expects (payload, status) back from handle()."""
    return payload, status


def _in_parallel(function, items):
    """Run function over items concurrently, preserving input order.

    Used only for calls that leave our server. Anything hitting our own
    process goes through a plain loop instead - see the note at the top.
    """
    if not items:
        return []
    if len(items) == 1:
        return [function(items[0])]
    workers = min(len(items), MAX_PARALLEL_PEERS)
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="mutual-peer") as pool:
        return list(pool.map(function, items))


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------

def _http(url, payload=None):
    """POST if payload given, else GET. Returns (status, parsed_or_text)."""
    data = None
    headers = {"Accept": "application/json",
               "User-Agent": "aileash-mutual/%s" % VERSION}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        status = exc.code
    except urllib.error.URLError as exc:
        return 0, "unreachable: %s" % exc.reason
    except Exception as exc:
        return 0, "failed: %s" % exc
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


# Field names a tip can arrive under. Different implementations name it
# differently and being strict about a name we never published is a bug in
# the receiver, not in the peer. Order is preference, not importance.
TIP_FIELDS = ("tip", "hash", "head", "tip_sha256", "root", "current_tip",
              "chain_tip", "latest")

HEIGHT_FIELDS = ("height", "count", "entries", "tree_size", "size")


def _extract_tip(body):
    """Pull (tip, height) out of whatever shape a tip route returns."""
    if not isinstance(body, dict):
        return None, None
    tip = None
    for field in TIP_FIELDS:
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            tip = value.strip()
            break
    height = None
    for field in HEIGHT_FIELDS:
        if field in body:
            height = body.get(field)
            break
    return tip, height


# ----------------------------------------------------------------------
# the two directions
# ----------------------------------------------------------------------

def our_tip():
    status, body = _http(OUR_TIP_URL)
    if status != 200:
        return None, None, "our own tip route answered %s: %s" % (status, str(body)[:200])
    tip, height = _extract_tip(body)
    if not tip:
        return None, None, "no tip field in our own reply: %s" % str(body)[:200]
    return tip, height, None


def push_one(peer, tip, height):
    """Hand our tip to one peer so they record it. Outbound only.

    A peer with no observe_url is fetch-only by configuration. Say so and
    move on rather than treating it as a failure - and never index the key
    blindly, which is what 1.1 did.
    """
    observe_url = peer.get("observe_url")
    if not observe_url:
        return {
            "peer": peer["name"],
            "direction": "push",
            "skipped": True,
            "ok": True,
            "reason": "fetch-only peer - no observe_url configured",
            "note": ("We read and seal their tip. They do not accept a push, "
                     "either because their outbound lane is closed or because "
                     "their tip is a static file. Not an error."),
        }

    keys = peer.get("keys", DEFAULT_PUSH_KEYS)
    values = {
        "chain": OUR_CHAIN_NAME,
        "tip": tip,
        "count": height,
        "ts": _now(),
        "url": OUR_PUBLIC_URL,
    }
    payload = {keys.get(k, k): v for k, v in values.items()}
    status, body = _http(observe_url, payload)
    result = {
        "peer": peer["name"],
        "direction": "push",
        "url": observe_url,
        "http": status,
        "ok": 200 <= status < 300,
        "response": body if isinstance(body, (dict, list)) else str(body)[:300],
    }
    if status == 401 or status == 403:
        result["hint"] = "they want auth on that route, or it is not in their public set"
    elif status == 404:
        result["hint"] = "wrong path - check observe_url for this peer"
    elif status == 0:
        result["hint"] = "could not reach them at all"
    return result


def fetch_one(peer):
    """Read one peer's current tip. Outbound only - no sealing here.

    Returns a dict that either carries a tip ready to seal, or an error
    already shaped like a result so it can be returned to the caller as is.
    """
    status, body = _http(peer["tip_url"])
    if status != 200:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": body if isinstance(body, (dict, list)) else str(body)[:300],
            "hint": "could not read their tip",
        }

    tip, height = _extract_tip(body)
    if not tip:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": str(body)[:300],
            "hint": ("no tip field in their reply - add the field name to "
                     "TIP_FIELDS. Currently accepted: " + ", ".join(TIP_FIELDS)),
        }

    return {
        "peer": peer["name"], "url": peer["tip_url"],
        "tip": tip, "height": height, "_failed": False,
        "fetched_at": time.time(),
    }


def seal_one(fetched):
    """Seal one already-fetched peer tip into our chain.

    Goes through our own public observe route so a tip we pulled is
    recorded by exactly the same code path as a tip somebody pushed to us.
    Called in a plain loop, never in parallel - this hits our own server.

    Field names must match what modules/witness.py reads out of the body:
    chain, tip, peer_ts, url. The url is what makes the observation
    checkable by a third party rather than taken on our word - it is the
    address we just fetched this tip from.
    """
    seal_status, seal_body = _http(OUR_OBSERVE_URL, {
        "chain": fetched["peer"],
        "tip": fetched["tip"],
        "peer_ts": fetched["fetched_at"],
        "url": fetched["url"],
    })

    out = {
        "peer": fetched["peer"],
        "direction": "pull",
        "their_tip": fetched["tip"],
        "their_height": fetched["height"],
        "sealed_http": seal_status,
        "ok": 200 <= seal_status < 300,
        "response": seal_body if isinstance(seal_body, (dict, list)) else str(seal_body)[:300],
    }
    if seal_status in (401, 403):
        out["hint"] = "our own observe route rejected us - check PUBLIC in modules/witness.py"
    return out


def do_push():
    tip, height, error = our_tip()
    if error:
        return {"ok": False, "error": error}

    # Outbound to everyone at once.
    results = _in_parallel(lambda peer: push_one(peer, tip, height), PEERS)

    return {
        "ok": True,
        "our_tip": tip,
        "our_height": height,
        "pushed_to": len([r for r in results if not r.get("skipped")]),
        "fetch_only": len([r for r in results if r.get("skipped")]),
        "results": results,
    }


def do_pull():
    # Phase one: read every peer's tip at the same time. This is the slow
    # part and none of it touches us.
    fetched = _in_parallel(fetch_one, PEERS)

    # Phase two: seal what came back, one at a time, into our own chain.
    results = []
    for item in fetched:
        if item.get("_failed"):
            item.pop("_failed", None)
            results.append(item)
            continue
        results.append(seal_one(item))

    return {"ok": True, "results": results}


def do_sync():
    """Pull first, then push. That order matters: the tip we hand out then
    already contains the tips we just took in, so the two chains interlock
    rather than merely sitting alongside each other."""
    started = time.time()
    pulled = do_pull()
    pushed = do_push()
    result = {
        "ran_at": _now(),
        "took_seconds": round(time.time() - started, 2),
        "peers": len(PEERS),
        "pull": pulled,
        "push": pushed,
        "ok": bool(pulled.get("ok")) and bool(pushed.get("ok")),
    }
    with _lock:
        _state["last_run"] = result["ran_at"]
        _state["last_result"] = result
        _state["runs"] += 1
    return result


# ----------------------------------------------------------------------
# background timer
# ----------------------------------------------------------------------

def _loop():
    # Let the server finish coming up before the first run.
    time.sleep(45)
    while True:
        try:
            do_sync()
        except Exception:
            pass
        time.sleep(AUTO_SYNC_SECONDS)


def _start_timer():
    with _lock:
        if _state["timer_started"] or not AUTO_SYNC_ENABLED:
            return
        _state["timer_started"] = True
    thread = threading.Thread(target=_loop, name="mutual-sync", daemon=True)
    thread.start()


_start_timer()


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()

    if method == "GET":
        if action == "peers":
            return _reply({
                "chain": OUR_CHAIN_NAME,
                "version": VERSION,
                "peers": [
                    {"name": p["name"],
                     "tip_url": p["tip_url"],
                     "observe_url": p.get("observe_url"),
                     "direction": ("both" if p.get("observe_url")
                                   else "fetch-only")}
                    for p in PEERS
                ],
                "parallel_fetch": MAX_PARALLEL_PEERS,
                "tip_fields_accepted": list(TIP_FIELDS),
                "note": ("Witnessing is only mutual if both columns are live. "
                         "A fetch-only peer is one we read and seal but who "
                         "does not accept a push - either their outbound lane "
                         "is closed or their tip is a static file. Both are "
                         "valid; the direction is published rather than "
                         "implied."),
            })
        if action == "status":
            with _lock:
                return _reply({
                    "version": VERSION,
                    "auto_sync": AUTO_SYNC_ENABLED,
                    "interval_seconds": AUTO_SYNC_SECONDS,
                    "timer_running": _state["timer_started"],
                    "parallel_fetch": MAX_PARALLEL_PEERS,
                    "runs": _state["runs"],
                    "last_run": _state["last_run"],
                    "last_result": _state["last_result"],
                })

    if method == "POST":
        if action == "push":
            return _reply(do_push())
        if action == "pull":
            return _reply(do_pull())
        if action == "sync":
            return _reply(do_sync())

    return _reply({
        "error": "unknown action",
        "GET": ["peers", "status"],
        "POST": ["push", "pull", "sync"],
    }, 404)

```


## `modules/network.py`

487 lines, 19842 bytes

```python
"""
modules/network.py  -  serves the public witness network page

WHY THIS IS A MODULE AND NOT A TEMPLATE
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it - it would arrive as a JSON string. So this does the
same thing router.py already does for POST: it patches the request handler at
runtime, adds a branch for the page path, and leaves every other path exactly
as it was. The patch is idempotent and lives in memory, so a restart reverts it.

THE SAME CATCH AS THE POST PATCH
--------------------------------
A module is only imported when a request reaches the router. So after every
deploy, one request to /x/network/status has to arrive before /witness works.
Opening /x/network/status in a browser does it. Until then the page path falls
through to whatever the server did before, which is a 404 - not an error page,
just the old behaviour.

If you would rather not patch anything, the same HTML works as a plain file in
static/. This exists because the page then lives with the module it describes
rather than drifting away from it.

ROUTES
------
  GET /witness            the page
  GET /witness.html       same page
  GET /x/network/status   whether the patch is installed (public)

The page itself holds no data. It reads /x/witness/tip and /x/witness/peers
from the browser, same as any other visitor would, so it cannot show anything
a stranger could not verify for themselves.
"""

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/witness", "/witness.html", "/network")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The witness network — AILeash</title>
<meta name="description" content="Two independent platforms recording each other's records, hourly. Checkable by anyone, without an account.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,600&family=Inter+Tight:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#E9EDE4;
  --paper-deep:#DFE5D8;
  --ink:#18241F;
  --ink-soft:#4A5A52;
  --rule:#BFCCBF;
  --rule-strong:#9AAC9C;
  --stamp:#7C2B38;
  --verdigris:#2F6B5E;
  --amber:#9A6B1F;
  --gutter:#CBD6C8;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--paper);
  color:var(--ink);
  font-family:"Inter Tight",system-ui,sans-serif;
  font-size:17px;
  line-height:1.6;
  /* ruled paper, faint */
  background-image:repeating-linear-gradient(
    to bottom,
    transparent 0 31px,
    rgba(154,172,156,.20) 31px 32px
  );
}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}

/* ---------- masthead ---------- */
.masthead{padding:52px 0 30px;border-bottom:2px solid var(--ink)}
.eyebrow{
  font-family:"IBM Plex Mono",monospace;
  font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink-soft);margin:0 0 18px;
}
h1{
  font-family:Fraunces,Georgia,serif;
  font-weight:600;font-size:clamp(2.5rem,7.5vw,4.6rem);
  line-height:1.02;letter-spacing:-.02em;margin:0 0 20px;
}
h1 em{font-style:italic;font-weight:300}
.standfirst{font-size:clamp(1.05rem,2.4vw,1.28rem);max-width:40ch;color:var(--ink-soft);margin:0}

/* ---------- the spread ---------- */
.spread{
  margin:44px 0 8px;
  border:1px solid var(--rule-strong);
  background:rgba(255,255,255,.4);
}
.spread-head{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule-strong);
}
.spread-head div{
  font-family:"IBM Plex Mono",monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  padding:12px 16px;color:var(--ink-soft);
}
.spread-head .mid{text-align:center;background:var(--gutter);color:var(--ink)}
.spread-head .right{text-align:right}
.folio{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule);
}
.folio:last-child{border-bottom:0}
.side{padding:20px 16px;min-width:0}
.side.right{text-align:right}
.mid{
  background:var(--gutter);
  display:flex;align-items:center;justify-content:center;
  font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-soft);
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
}
.chain-name{
  font-family:Fraunces,Georgia,serif;font-size:1.35rem;font-weight:600;
  margin:0 0 4px;letter-spacing:-.01em;
}
.role{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-soft);margin:0 0 14px}
.hash{
  font-family:"IBM Plex Mono",monospace;font-size:12.5px;
  word-break:break-all;color:var(--ink);margin:0 0 3px;line-height:1.45;
}
.hash-label{font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 5px}
.meta{font-size:14px;color:var(--ink-soft);margin:12px 0 0}
.meta b{color:var(--ink);font-weight:600}

/* ---------- stamp ---------- */
.stamp{
  display:inline-block;margin-top:16px;padding:6px 13px 5px;
  border:2.5px solid var(--stamp);color:var(--stamp);
  font-family:"IBM Plex Mono",monospace;font-weight:500;
  font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  transform:rotate(-3.5deg);opacity:.9;
}
.stamp.press{animation:press .5s cubic-bezier(.2,1.5,.4,1) both}
@keyframes press{
  0%{opacity:0;transform:rotate(-3.5deg) scale(1.5)}
  70%{opacity:.95;transform:rotate(-3.5deg) scale(.97)}
  100%{opacity:.9;transform:rotate(-3.5deg) scale(1)}
}
.stamp.live{border-color:var(--verdigris);color:var(--verdigris)}
.stamp.weak{border-color:var(--amber);color:var(--amber)}
.stamp.flag{background:var(--stamp);color:var(--paper)}

/* ---------- sections ---------- */
section{padding:56px 0;border-top:1px solid var(--rule-strong)}
h2{
  font-family:Fraunces,Georgia,serif;font-weight:600;
  font-size:clamp(1.6rem,4vw,2.3rem);letter-spacing:-.015em;
  margin:0 0 8px;line-height:1.15;
}
.sec-note{color:var(--ink-soft);max-width:56ch;margin:0 0 30px}
p{max-width:62ch}

.defs{display:grid;gap:0;border-top:1px solid var(--rule)}
.def{
  display:grid;grid-template-columns:170px 1fr;gap:20px;
  padding:15px 0;border-bottom:1px solid var(--rule);
}
.def dt{
  font-family:"IBM Plex Mono",monospace;font-size:12px;
  letter-spacing:.1em;text-transform:uppercase;padding-top:3px;
}
.def dd{margin:0;color:var(--ink-soft)}
.dot{display:inline-block;width:8px;height:8px;margin-right:8px;border-radius:50%;vertical-align:middle}
.dot.ok{background:var(--stamp)}
.dot.mid-c{background:var(--verdigris)}
.dot.weak{background:var(--amber)}

.limits li{max-width:62ch;margin-bottom:13px;color:var(--ink-soft)}
.limits b{color:var(--ink)}

pre{
  font-family:"IBM Plex Mono",monospace;font-size:13px;line-height:1.7;
  background:var(--ink);color:var(--paper);padding:20px;overflow-x:auto;
  border:0;margin:22px 0;
}
pre .k{color:#9FC6B4}
code{font-family:"IBM Plex Mono",monospace;font-size:.92em}

.links{list-style:none;padding:0;margin:24px 0 0}
.links li{border-bottom:1px solid var(--rule);padding:13px 0}
.links a{
  font-family:"IBM Plex Mono",monospace;font-size:13.5px;
  color:var(--ink);text-decoration:none;word-break:break-all;
  display:flex;justify-content:space-between;gap:16px;align-items:baseline;
}
.links a:hover,.links a:focus-visible{color:var(--stamp)}
.links span{color:var(--ink-soft);font-family:"Inter Tight",sans-serif;
  font-size:13px;flex:0 0 auto;text-align:right}

footer{padding:40px 0 70px;color:var(--ink-soft);font-size:14px}
footer a{color:var(--ink)}

.loading,.errbox{
  font-family:"IBM Plex Mono",monospace;font-size:13px;
  color:var(--ink-soft);padding:26px 16px;
}
.errbox b{display:block;color:var(--ink);margin-bottom:6px;font-family:"Inter Tight",sans-serif;font-size:15px}

a:focus-visible,button:focus-visible{outline:2.5px solid var(--stamp);outline-offset:3px}

@media (max-width:760px){
  body{background-image:none}
  .spread-head,.folio{grid-template-columns:1fr}
  .spread-head .mid,.folio .mid{
    border-left:0;border-right:0;
    border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
    padding:7px 0;text-align:center;
  }
  .spread-head .right,.side.right{text-align:left}
  .spread-head div{padding:9px 14px}
  .def{grid-template-columns:1fr;gap:5px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>
</head>
<body>

<div class="wrap">

  <header class="masthead">
    <p class="eyebrow">AILeash · the witness network</p>
    <h1>Two ledgers.<br><em>Neither one is the authority.</em></h1>
    <p class="standfirst">Independent platforms record each other's records, every hour. You can check it yourself, right now, without an account.</p>
  </header>

  <div class="spread" id="spread">
    <div class="spread-head">
      <div>This chain</div>
      <div class="mid">Exchange</div>
      <div class="right">Recorded by</div>
    </div>
    <div id="folios">
      <div class="loading">Reading the ledger…</div>
    </div>
  </div>

  <section>
    <h2>Why this exists</h2>
    <p class="sec-note">Every platform that sells you an audit trail also holds it.</p>
    <p>A hash chain stops anyone else altering the record. It does not stop the operator rebuilding the whole thing and presenting the result as history. Anchoring the chain externally narrows that down — you can't rewrite anything older than your last anchor — and it still leaves the keeper and the checker as the same party.</p>
    <p>Nothing you build alone closes that. Somebody outside has to be holding a copy.</p>
    <p>So each platform here takes the fingerprint of the others' records and seals it into its own. To rewrite your past now, everyone holding a copy would have to rewrite theirs in step, and re-obtain external timestamps that were issued days ago. The second half is the part that can't be done.</p>
  </section>

  <section>
    <h2>What the marks mean</h2>
    <p class="sec-note">Two checks run on every submission. Neither can reject one — everything gets sealed. What changes is how strong we say the claim is.</p>

    <dl class="defs">
      <div class="def"><dt><span class="dot ok"></span>Confirmed</dt><dd>We fetched the address given and it served exactly the tip that was submitted.</dd></div>
      <div class="def"><dt><span class="dot mid-c"></span>Live</dt><dd>The address served a valid but different tip. A working chain moves between submitting and our looking — normal, not a failure.</dd></div>
      <div class="def"><dt><span class="dot weak"></span>Self-declared</dt><dd>No address given, or we couldn't reach it. Taken on their word, and marked as such.</dd></div>
      <div class="def"><dt>First-use</dt><dd>First time this name appeared. It's now bound to the address it came from.</dd></div>
      <div class="def"><dt>Bound</dt><dd>Same address as the first time this name appeared. The same operator, consistently.</dd></div>
      <div class="def"><dt>Conflict</dt><dd>This name has been submitted from a different address than the one it was first bound to. Still sealed, permanently flagged. Operators do move hosts — but you get to see it and decide.</dd></div>
    </dl>
  </section>

  <section>
    <h2>What this does not prove</h2>
    <p class="sec-note">Said plainly, because the value of the rest depends on it.</p>
    <ul class="limits">
      <li><b>It doesn't prove a record was true when it was written.</b> Nothing can. No system reaches back to verify what someone was thinking or whether the data going in was honest. This proves what was recorded, when, and that it hasn't changed since.</li>
      <li><b>It doesn't prove identity.</b> A name is self-declared. Checking the address proves someone runs a live chain producing that data — not that they're who they say. Binding a name to its first address is what makes a change visible.</li>
      <li><b>Two platforms checking each other isn't much of a network.</b> The strength comes from breadth. This gets meaningfully harder to bend with every chain that joins, and not before.</li>
      <li><b>A participant can go quiet.</b> Nobody can force anyone to keep publishing. Gaps show up as stale or silent rather than disappearing, which is the point.</li>
    </ul>
  </section>

  <section>
    <h2>Joining</h2>
    <p class="sec-note">Chains submit their current head to the network and record the heads of others in return.</p>
    <pre><span class="k">POST</span> https://sebbi.pro/x/witness/observe
<span class="k">Content-Type:</span> application/json

{
  "chain": "your-chain-name",
  "tip":   "&lt;64 hex characters — your current chain head&gt;",
  "url":   "https://yoursite/your/tip",
  "ts":    "2026-08-02T14:00:00Z"
}</pre>
    <p><code>url</code> is the address we fetch to check your tip independently — it's the difference between confirmed and self-declared. <code>ts</code> is optional, epoch or ISO.</p>
    <p>Running a chain in the other direction, recording ours as we record yours, is what makes it mutual rather than us keeping a list. If you operate a platform in this space and you're willing to have your history held somewhere you don't control, message me and we'll talk through it and what it costs.</p>
  </section>

  <section>
    <h2>Check it yourself</h2>
    <p class="sec-note">Nothing here needs a login. Open any of these.</p>
    <ul class="links">
      <li><a href="/x/witness/tip">/x/witness/tip<span>our current head</span></a></li>
      <li><a href="/x/witness/peers">/x/witness/peers<span>everyone we record</span></a></li>
      <li><a href="/api/verify-chain">/api/verify-chain<span>chain checked end to end</span></a></li>
      <li><a href="/api/anchor-status">/api/anchor-status<span>the external timestamp</span></a></li>
    </ul>
  </section>

  <footer>
    <p>Sealed records and their attestations are held by each participating platform independently. AILeash operates one chain in this network; it does not run the network. — <a href="https://sebbi.pro">sebbi.pro</a></p>
  </footer>

</div>

<script>
(function(){
  var folios = document.getElementById('folios');

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function stampFor(liveness, nameStatus){
    var cls = 'stamp press', text = String(liveness || 'unchecked');
    if (liveness === 'confirmed') cls += '';
    else if (liveness === 'live') cls += ' live';
    else cls += ' weak';
    if (nameStatus === 'conflict'){ cls += ' flag'; text = 'conflict'; }
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }

  function ago(hours){
    if (hours == null) return 'unknown';
    if (hours < 1) return 'within the hour';
    if (hours < 2) return 'an hour ago';
    if (hours < 48) return Math.round(hours) + ' hours ago';
    return Math.round(hours / 24) + ' days ago';
  }

  function render(ours, peers){
    if (!peers || !peers.length){
      folios.innerHTML = '<div class="errbox"><b>No chains recorded yet.</b>' +
        'Nothing has been submitted to this chain. The first tip posted to ' +
        '/x/witness/observe appears here.</div>';
      return;
    }
    var html = '';
    peers.forEach(function(p){
      html += '<div class="folio">' +
        '<div class="side">' +
          '<p class="chain-name">' + esc(ours.name) + '</p>' +
          '<p class="role">head of chain · height ' + esc(ours.height) + '</p>' +
          '<p class="hash-label">Current tip</p>' +
          '<p class="hash">' + esc(ours.tip) + '</p>' +
          '<p class="meta">Sealed <b>' + esc(ours.sealed) + '</b></p>' +
        '</div>' +
        '<div class="mid">↔</div>' +
        '<div class="side right">' +
          '<p class="chain-name">' + esc(p.peer) + '</p>' +
          '<p class="role">' + esc(p.observations) + ' observations · ' +
              esc(p.distinct_tips) + ' distinct tips</p>' +
          '<p class="hash-label">Name bound to</p>' +
          '<p class="hash">' + esc(p.bound_to || 'no address supplied') + '</p>' +
          '<p class="meta">Last recorded <b>' + esc(ago(p.hours_since_last)) + '</b> · ' +
              esc(p.name_status || 'unchecked') + '</p>' +
          stampFor(p.liveness, p.name_status) +
        '</div>' +
      '</div>';
    });
    folios.innerHTML = html;
  }

  function failed(){
    folios.innerHTML = '<div class="errbox"><b>The ledger did not answer.</b>' +
      'The endpoints are public, so you can try them directly: ' +
      '<a href="/x/witness/peers">/x/witness/peers</a></div>';
  }

  Promise.all([
    fetch('/x/witness/tip').then(function(r){ return r.json(); }),
    fetch('/x/witness/peers').then(function(r){ return r.json(); })
  ]).then(function(res){
    var tip = res[0] || {}, peers = res[1] || {};
    render({
      name: 'aileash',
      tip: tip.tip || 'unavailable',
      height: tip.height == null ? '—' : tip.height,
      sealed: tip.sealed_at ? new Date(tip.sealed_at).toUTCString().replace(' GMT','  UTC') : 'unknown'
    }, peers.peers || []);
  }).catch(failed);
})();
</script>

</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    """Add a page branch to do_GET at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_page_patched", False):
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
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._page_patched = True
    _patched[0] = True
    print("NETWORK: /witness page branch installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("NETWORK: page patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/witness",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": "The page reads /x/witness/tip and /x/witness/peers from the browser. It holds no data of its own.",
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404

```
