# Codebase — part 10 of 39

Contains:
- `modules/investor.py`
- `modules/lineage.py`
- `modules/lineagedesk.py`
- `modules/machine.py`
- `modules/map.py`


## `modules/investor.py`

298 lines, 23897 bytes

```python
"""
modules/investor.py  v1.3.0
Serves the investor / partner page at /investor-prospectus.

Page module, same family as map.py / console.py / network.py: a runtime do_GET
patch puts the page at a clean URL, armed by hitting /x/investor/status once
after each deploy. server.py is never edited. Page is base64-embedded.

v1.3.0 changes, all wording:
  * "externally anchored" and "anchored to a clock nobody controls" replaced
    with per-proof timestamping language. Anchoring is a state each individual
    proof is in, not a property the chain has, and /x/ots/status is where an
    investor will look it up in front of you.
  * the /x/ots/status line now says plainly that submitted is not confirmed.
  * contact address aligned with ai.txt v2.0.
Founding seats language is unchanged, deliberately.

NOTE: investor-prospectus.html also exists at the repo root. Two investor
pages on two paths will drift. Decide which one is canonical and delete the
other.
"""

import base64
import sys

VERSION = "1.3.0"
PAGE_PATH = "/investor-prospectus"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLjAiPgo8dGl0bGU+c2ViYmkucHJv"
    "IOKAlCB0aGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJLiBQYXJ0bmVyIG9wcG9ydHVuaXR5LjwvdGl0bGU+CjxtZXRhIG5hbWU9ImRl"
    "c2NyaXB0aW9uIiBjb250ZW50PSJBIGxpdmUsIHB1YmxpY2x5IHZlcmlmaWFibGUgZXZpZGVuY2UgbGF5ZXIgZm9yIEFJIGRlY2lz"
    "aW9ucy4gQnVpbHQsIHJ1bm5pbmcsIGFuZCBzdHJ1Y3R1cmFsbHkgaW1wb3NzaWJsZSBmb3IgaW5jdW1iZW50cyB0byBjb3B5LiBT"
    "ZWVraW5nIG9uZSBvcGVyYXRpbmcgcGFydG5lciB0byB0YWtlIGl0IGludG8gcmVndWxhdGVkIGVudGVycHJpc2UuIj4KPGxpbmsg"
    "cmVsPSJwcmVjb25uZWN0IiBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9m"
    "b250cy5nb29nbGVhcGlzLmNvbS9jc3MyP2ZhbWlseT1OZXdzcmVhZGVyOm9wc3osd2dodEA2Li43Miw0MDA7Ni4uNzIsNTAwOzYu"
    "LjcyLDYwMDs2Li43Miw3MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2dodEA0MDA7NTAwOzYwMDs3MDAmZmFtaWx5PUlCTStQbGV4"
    "K01vbm86d2dodEA0MDA7NTAwOzYwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7CiAgLS1w"
    "YXBlcjojRkFGQUY2Oy0taW5rOiMxNDE3MUM7LS1pbmstc29mdDojNDU0QjU0Oy0tY2hhaW46IzJFNUU0RTsKICAtLWNoYWluLWxp"
    "Z2h0OiNFNEVDRTg7LS1nb2xkOiM5QTdCMUY7LS1nb2xkLWxpZ2h0OiNGM0VDRDg7LS1saW5lOiNERURCRDE7Cn0KKntib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGluZzowfQpib2R5e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBTYW5zJyxzYW5zLXNl"
    "cmlmO2JhY2tncm91bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1z"
    "bW9vdGhpbmc6YW50aWFsaWFzZWR9CmgxLGgyLGgzLC5kaXNwbGF5e2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJpZjtmb250"
    "LXdlaWdodDo1MDA7bGV0dGVyLXNwYWNpbmc6LTAuMDFlbX0KLm1vbm97Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9z"
    "cGFjZX0KYXtjb2xvcjp2YXIoLS1jaGFpbil9Ci53cmFwe21heC13aWR0aDo3NjBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6MCAy"
    "OHB4fQoKaGVhZGVye3BhZGRpbmc6NTZweCAwIDQwcHg7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgdmFyKC0tbGluZSl9Ci5kb2Mt"
    "bGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzow"
    "LjFlbTt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MjBweDtkaXNw"
    "bGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47ZmxleC13cmFwOndyYXA7Z2FwOjhweH0KaDF7Zm9udC1zaXpl"
    "OmNsYW1wKDM0cHgsNXZ3LDUwcHgpO2xpbmUtaGVpZ2h0OjEuMDg7bWF4LXdpZHRoOjE3Y2g7bWFyZ2luLWJvdHRvbToxOHB4fQou"
    "dGFnbGluZXtmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmstc29mdCk7bWF4LXdpZHRoOjU0Y2h9Ci50YWdsaW5lIGJ7Y29s"
    "b3I6dmFyKC0taW5rKX0KCi5ibG9ja3twb3NpdGlvbjpyZWxhdGl2ZTtwYWRkaW5nOjhweCAwIDQ0cHggMjRweDtib3JkZXItbGVm"
    "dDoxcHggc29saWQgdmFyKC0tbGluZSk7bWFyZ2luLWxlZnQ6NHB4fQouYmxvY2s6bGFzdC1vZi10eXBle2JvcmRlci1sZWZ0OjFw"
    "eCBzb2xpZCB0cmFuc3BhcmVudH0KLmJsb2NrLW51bXtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQt"
    "c2l6ZToxMXB4O2NvbG9yOnZhcigtLWNoYWluKTtsZXR0ZXItc3BhY2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNl"
    "O21hcmdpbi1ib3R0b206MTBweH0KLmJsb2NrIGgye2ZvbnQtc2l6ZToyN3B4O21hcmdpbi1ib3R0b206MTZweDtsaW5lLWhlaWdo"
    "dDoxLjE1fQouYmxvY2sgaDN7Zm9udC1zaXplOjE3cHg7bWFyZ2luOjIycHggMCA4cHh9Ci5ibG9jayBwe2ZvbnQtc2l6ZToxNS41"
    "cHg7Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTRweDttYXgtd2lkdGg6NjBjaH0KLmJsb2NrIHA6bGFzdC1j"
    "aGlsZHttYXJnaW4tYm90dG9tOjB9Ci5ibG9jayB1bHttYXJnaW46MCAwIDE0cHggMThweH0KLmJsb2NrIGxpe2ZvbnQtc2l6ZTox"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tYm90dG9tOjhweDttYXgtd2lkdGg6NThjaH0KLmJsb2NrIGxpIGIsLmJs"
    "b2NrIHAgYntjb2xvcjp2YXIoLS1pbmspfQoKLnByb29mLWdyaWR7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczox"
    "ZnIgMWZyO2dhcDoxNHB4O21hcmdpbi10b3A6MThweH0KQG1lZGlhKG1heC13aWR0aDo1NjBweCl7LnByb29mLWdyaWR7Z3JpZC10"
    "ZW1wbGF0ZS1jb2x1bW5zOjFmcn19Ci5wcm9vZntiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7"
    "cGFkZGluZzoxOHB4IDIwcHg7Ym9yZGVyLXJhZGl1czo0cHh9Ci5wcm9vZi1ue2ZvbnQtZmFtaWx5OidOZXdzcmVhZGVyJyxzZXJp"
    "Zjtmb250LXNpemU6MjZweDtmb250LXdlaWdodDo2MDA7Y29sb3I6dmFyKC0tY2hhaW4pfQoucHJvb2YtbHtmb250LXNpemU6MTIu"
    "NXB4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjNweH0KLnByb29mLXNyY3tmb250LWZhbWlseTonSUJNIFBsZXgg"
    "TW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMHB4O2NvbG9yOiM5OTk7bWFyZ2luLXRvcDo2cHh9CgouY291bnRkb3due2JhY2tn"
    "cm91bmQ6dmFyKC0tZ29sZC1saWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDE1NCwxMjMsMzEsMC4yNSk7Ym9yZGVyLXJhZGl1"
    "czo0cHg7cGFkZGluZzoyMHB4IDI0cHg7bWFyZ2luOjIwcHggMH0KLmNvdW50ZG93bi1sYWJlbHtmb250LWZhbWlseTonSUJNIFBs"
    "ZXggTW9ubycsbW9ub3NwYWNlO2ZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWdvbGQpO3RleHQtdHJhbnNmb3JtOnVwcGVyY2Fz"
    "ZTtsZXR0ZXItc3BhY2luZzowLjA4ZW07bWFyZ2luLWJvdHRvbTo4cHh9Ci5jb3VudGRvd24tZGF5c3tmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjM4cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOnZhcigtLWdvbGQpO2xpbmUtaGVpZ2h0"
    "OjF9Ci5jb3VudGRvd24tc3Vie2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluay1zb2Z0KTttYXJnaW4tdG9wOjZweDtsaW5l"
    "LWhlaWdodDoxLjZ9CgoucHVsbHtib3JkZXItbGVmdDozcHggc29saWQgdmFyKC0tY2hhaW4pO3BhZGRpbmc6NnB4IDAgNnB4IDIw"
    "cHg7bWFyZ2luOjIwcHggMDtmb250LWZhbWlseTonTmV3c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjIycHg7bGluZS1oZWlnaHQ6"
    "MS4zNTtjb2xvcjp2YXIoLS1pbmspfQoKLmFzay1ib3h7YmFja2dyb3VuZDp2YXIoLS1pbmspO2NvbG9yOnZhcigtLXBhcGVyKTti"
    "b3JkZXItcmFkaXVzOjRweDtwYWRkaW5nOjMycHg7bWFyZ2luLXRvcDoyMHB4fQouYXNrLWFtb3VudHtmb250LWZhbWlseTonTmV3"
    "c3JlYWRlcicsc2VyaWY7Zm9udC1zaXplOjQ0cHg7Zm9udC13ZWlnaHQ6NjAwO2NvbG9yOndoaXRlO2xpbmUtaGVpZ2h0OjEuMDV9"
    "Ci5hc2stbGFiZWx7Zm9udC1mYW1pbHk6J0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFjZTtmb250LXNpemU6MTFweDtsZXR0ZXItc3Bh"
    "Y2luZzowLjA4ZW07dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO2NvbG9yOiM4RkE4OUM7bWFyZ2luLWJvdHRvbTo2cHh9Ci5hc2st"
    "Ym94IHB7Zm9udC1zaXplOjE0LjVweDtjb2xvcjojQzdEMkNDO21hcmdpbi10b3A6MTRweDttYXgtd2lkdGg6NTZjaH0KLmFzay1i"
    "b3ggcCBie2NvbG9yOiNmZmZ9CgoudXNlLW9mLWZ1bmRze21hcmdpbi10b3A6MjJweDtkaXNwbGF5OmZsZXg7ZmxleC1kaXJlY3Rp"
    "b246Y29sdW1uO2dhcDoxMHB4fQoudWYtcm93e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGln"
    "bi1pdGVtczpiYXNlbGluZTtwYWRkaW5nLWJvdHRvbToxMHB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwy"
    "NTUsMC4xMik7Zm9udC1zaXplOjE0cHg7Z2FwOjE2cHh9Ci51Zi1yb3c6bGFzdC1jaGlsZHtib3JkZXItYm90dG9tOm5vbmV9Ci51"
    "Zi1yb3cgc3BhbjpmaXJzdC1jaGlsZHtjb2xvcjojQzdEMkNDfQoudWYtcGN0e2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxt"
    "b25vc3BhY2U7Y29sb3I6IzhGQTg5QztmbGV4OjAgMCBhdXRvfQoKLnZlcmlmeS1ib3h7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1s"
    "aWdodCk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMjUpO2JvcmRlci1yYWRpdXM6NHB4O3BhZGRpbmc6MjBweCAy"
    "NHB4O21hcmdpbi10b3A6MThweH0KLnZlcmlmeS1ib3ggaDR7Zm9udC1zaXplOjE1cHg7bWFyZ2luLWJvdHRvbToxMHB4fQoudmVy"
    "aWZ5LWJveCBwe2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1ib3R0b206OHB4fQoudmVyaWZ5LWJveCBjb2Rle2ZvbnQtZmFtaWx5OidJ"
    "Qk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjEyLjVweDtiYWNrZ3JvdW5kOndoaXRlO2JvcmRlcjoxcHggc29saWQg"
    "dmFyKC0tbGluZSk7cGFkZGluZzoycHggN3B4O2JvcmRlci1yYWRpdXM6M3B4O2NvbG9yOnZhcigtLWNoYWluKX0KCi5jb250YWN0"
    "LWJsb2Nre3BhZGRpbmc6NDRweCAwIDY0cHh9Ci5jb250YWN0LWNhcmR7YmFja2dyb3VuZDp2YXIoLS1jaGFpbi1saWdodCk7Ym9y"
    "ZGVyOjFweCBzb2xpZCByZ2JhKDQ2LDk0LDc4LDAuMik7Ym9yZGVyLXJhZGl1czo0cHg7cGFkZGluZzoyOHB4fQouY29udGFjdC1j"
    "YXJkIGgze2ZvbnQtc2l6ZToyMHB4O21hcmdpbi1ib3R0b206MTBweH0KLmNvbnRhY3QtY2FyZCBwe2ZvbnQtc2l6ZToxNC41cHg7"
    "Y29sb3I6dmFyKC0taW5rLXNvZnQpO21hcmdpbi1ib3R0b206MTZweH0KLmNvbnRhY3QtbGlua3N7ZGlzcGxheTpmbGV4O2ZsZXgt"
    "ZGlyZWN0aW9uOmNvbHVtbjtnYXA6NnB4O2ZvbnQtZmFtaWx5OidJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7Zm9udC1zaXplOjE0"
    "cHh9Ci5jb250YWN0LWxpbmtzIGF7Y29sb3I6dmFyKC0tY2hhaW4pO3RleHQtZGVjb3JhdGlvbjpub25lO2ZvbnQtd2VpZ2h0OjUw"
    "MH0KCmZvb3RlcntwYWRkaW5nOjAgMCA0OHB4fQpmb290ZXIgcHtmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsbW9ub3NwYWNl"
    "O2ZvbnQtc2l6ZToxMXB4O2NvbG9yOiM5OTk7bGluZS1oZWlnaHQ6MS44fQoKQG1lZGlhKHByZWZlcnMtcmVkdWNlZC1tb3Rpb246"
    "cmVkdWNlKXsqe3RyYW5zaXRpb246bm9uZSFpbXBvcnRhbnQ7YW5pbWF0aW9uOm5vbmUhaW1wb3J0YW50fX0KPC9zdHlsZT4KPC9o"
    "ZWFkPgo8Ym9keT4KCjxkaXYgY2xhc3M9IndyYXAiPgoKPGhlYWRlcj4KICA8ZGl2IGNsYXNzPSJkb2MtbGFiZWwiPgogICAgPHNw"
    "YW4+UGFydG5lciBPcHBvcnR1bml0eSAmbWlkZG90OyBzZWJiaS5wcm88L3NwYW4+CiAgICA8c3BhbiBpZD0iZG9jLWRhdGUiPiZt"
    "ZGFzaDs8L3NwYW4+CiAgPC9kaXY+CiAgPGgxPlRoZSBldmlkZW5jZSBsYXllciBmb3IgQUkgaXMgYnVpbHQsIGxpdmUsIGFuZCBs"
    "b29raW5nIGZvciBvbmUgcGFydG5lci48L2gxPgogIDxwIGNsYXNzPSJ0YWdsaW5lIj5zZWJiaS5wcm8gaXMgYSBwdWJsaWNseSB2"
    "ZXJpZmlhYmxlIGV2aWRlbmNlIGxheWVyIGZvciBBSSBkZWNpc2lvbnMgJm1kYXNoOyBydW5uaW5nIGluIHByb2R1Y3Rpb24gdG9k"
    "YXksIGNoZWNrYWJsZSBieSBhbnlvbmUgd2l0aCB0aGUgY29tcGFueSBzd2l0Y2hlZCBvZmYuIDxiPlRoZSBoYXJkIHBhcnQgaXMg"
    "ZG9uZS4gV2hhdCdzIGxlZnQgaXMgZGlzdHJpYnV0aW9uLjwvYj48L3A+CjwvaGVhZGVyPgoKPGRpdiBjbGFzcz0iYmxvY2siPgog"
    "IDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDEgJm1kYXNoOyBUaGUgb3Bwb3J0dW5pdHk8L2Rpdj4KICA8aDI+RXZlcnkgQUkgZGVj"
    "aXNpb24gaXMgYWJvdXQgdG8gbmVlZCBldmlkZW5jZS4gQWxtb3N0IG5vdGhpbmcgcHJvZHVjZXMgaXQuPC9oMj4KICA8cD5UaHJl"
    "ZSByZWd1bGF0b3J5IHJlZ2ltZXMgYXJlIGNvbnZlcmdpbmcgb24gdGhlIHNhbWUgZGVtYW5kOiByZWNvcmRzIHRoYXQgc3Vydml2"
    "ZSBzY3J1dGlueS4gVGhlIEVVIEFJIEFjdCwgdGhlIFVLIE9ubGluZSBTYWZldHkgQWN0LCBhbmQgdGhlIDIwMjQgUGF5bWVudCBT"
    "ZXJ2aWNlcyByZWltYnVyc2VtZW50IHJ1bGVzIGFsbCByZXF1aXJlIGFuIG9yZ2FuaXNhdGlvbiB0byBwcm92ZSB3aGF0IGl0cyBz"
    "eXN0ZW1zIGRpZCAmbWRhc2g7IG5vdCBhc3NlcnQgaXQsIHByb3ZlIGl0LjwvcD4KICA8cD5BbG1vc3QgZXZlcnkgb3JnYW5pc2F0"
    "aW9uIG1lZXRzIHRoYXQgZGVtYW5kIHdpdGggZGF0YWJhc2UgbG9ncyB0aGVpciBvd24gdGVhbSBjYW4gZWRpdC4gVGhhdCBpcyBu"
    "b3QgZXZpZGVuY2UsIGFuZCB0aGUgZGF5IGEgcmVndWxhdG9yLCBjb3VydCBvciBjdXN0b21lciBzdG9wcyB0YWtpbmcgdGhlaXIg"
    "d29yZCBmb3IgaXQsIHRoZXkgZGlzY292ZXIgdGhlIGdhcC4gPGI+VGhlIG1hcmtldCB0aGF0IGNsb3NlcyB0aGF0IGdhcCBkb2Vz"
    "IG5vdCByZWFsbHkgZXhpc3QgeWV0LjwvYj4gc2ViYmkucHJvIGlzIGFscmVhZHkgaW4gaXQuPC9wPgoKICA8ZGl2IGNsYXNzPSJw"
    "dWxsIj5BIGxvZyB5b3UgY2FuIGVkaXQgdGVsbHMgcGVvcGxlIHdoYXQgeW91IGN1cnJlbnRseSBjbGFpbSBoYXBwZW5lZC4gSXQg"
    "Y2Fubm90IHRlbGwgdGhlbSBub2JvZHkgY2hhbmdlZCBpdCBzaW5jZS4gT25seSBvbmUgb2YgdGhvc2UgaXMgd29ydGggYW55dGhp"
    "bmcgd2hlbiBpdCBtYXR0ZXJzLjwvZGl2PgoKICA8ZGl2IGNsYXNzPSJjb3VudGRvd24iPgogICAgPGRpdiBjbGFzcz0iY291bnRk"
    "b3duLWxhYmVsIj5VbnRpbCBoaWdoLXJpc2sgQUkgb2JsaWdhdGlvbnMgYXBwbHk8L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNvdW50"
    "ZG93bi1kYXlzIG1vbm8iIGlkPSJjb3VudGRvd24tZGF5cyI+Jm1kYXNoOyBkYXlzPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjb3Vu"
    "dGRvd24tc3ViIj5Db3VudGluZyB0byAyIERlY2VtYmVyIDIwMjcuIFRoZSBldmlkZW5jZSB0aGVzZSBvYmxpZ2F0aW9ucyByZXF1"
    "aXJlIGlzIGhpc3RvcmljYWwgJm1kYXNoOyBpdCBjYW5ub3QgYmUgY3JlYXRlZCBhZnRlciB0aGUgZmFjdC4gRXZlcnkgb3JnYW5p"
    "c2F0aW9uIG5vdCByZWNvcmRpbmcgbm93IGlzIGFjY3J1aW5nIGEgZ2FwIGl0IGNhbiBuZXZlciBmaWxsLiBUaGF0IGlzIHRoZSBi"
    "dXlpbmcgcHJlc3N1cmUsIGFuZCBpdCBvbmx5IGdyb3dzLjwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2Nr"
    "Ij4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPjAyICZtZGFzaDsgV2hhdCBpcyBhbHJlYWR5IGJ1aWx0PC9kaXY+CiAgPGgyPkxp"
    "dmUgaW4gcHJvZHVjdGlvbi4gTm90IGEgZGVjaywgbm90IGEgZGVtby48L2gyPgogIDxwPlRoaXMgcnVucyB0b2RheSwgb24gcmVh"
    "bCBpbmZyYXN0cnVjdHVyZSwgYW5kIGV2ZXJ5IGNsYWltIGJlbG93IGNhbiBiZSB2ZXJpZmllZCBieSBhIHRoaXJkIHBhcnR5IHdp"
    "dGggbm8gYWNjb3VudCBhbmQgbm8gcGVybWlzc2lvbi4gU2l4IHByb2R1Y3RzIG9uIG9uZSBlbmdpbmUsIG9uZSB0YW1wZXItZXZp"
    "ZGVudCBjaGFpbiB1bmRlcm5lYXRoIGFsbCBvZiB0aGVtLjwvcD4KCiAgPGRpdiBjbGFzcz0icHJvb2YtZ3JpZCI+CiAgICA8ZGl2"
    "IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0icHJvb2YtbiBtb25vIj42PC9kaXY+PGRpdiBjbGFzcz0icHJvb2YtbCI+UHJvZHVj"
    "dHMsIG9uZSBlbmdpbmU8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPkFJTGVhc2gsIEd1YXJkaWFuLCBTZW50aW5lbCwgU29u"
    "aWNCb29tLCBTZWJkb2csIFRva2VuIFNhdmVyPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0i"
    "cHJvb2YtbiBtb25vIj5+MjhtczwvZGl2PjxkaXYgY2xhc3M9InByb29mLWwiPk1lZGlhbiBkZWNpc2lvbiB0aW1lPC9kaXY+PGRp"
    "diBjbGFzcz0icHJvb2Ytc3JjIj5EZXRlcm1pbmlzdGljLCBvbiBsaXZlIHRyYWZmaWM8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xh"
    "c3M9InByb29mIj48ZGl2IGNsYXNzPSJwcm9vZi1uIG1vbm8iPlNIQS0yNTY8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1sIj5IYXNo"
    "LWNoYWluZWQsIHRpbWVzdGFtcGVkIHBlciBwcm9vZjwvZGl2PjxkaXYgY2xhc3M9InByb29mLXNyYyI+Q3Jvc3Mtd2l0bmVzc2Vk"
    "IGJ5IGluZGVwZW5kZW50IHN5c3RlbXM8L2Rpdj48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InByb29mIj48ZGl2IGNsYXNzPSJwcm9v"
    "Zi1uIG1vbm8iPlB1YmxpYzwvZGl2PjxkaXYgY2xhc3M9InByb29mLWwiPlZlcmlmaWFibGUgd2l0aCB0aGUgdmVuZG9yIHN3aXRj"
    "aGVkIG9mZjwvZGl2PjxkaXYgY2xhc3M9InByb29mLXNyYyI+U3RhbmRhbG9uZSB2ZXJpZmllciwgbm8gYWNjb3VudDwvZGl2Pjwv"
    "ZGl2PgogIDwvZGl2PgoKICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxOHB4Ij5UaGUgd2hvbGUgcmFuZ2Ugc2hhcmVzIG9uZSBzcGlu"
    "ZTogZXZlcnkgZGVjaXNpb24gc2VhbGVkIGFzIGl0IGhhcHBlbnMsIHN1Ym1pdHRlZCBmb3IgZXh0ZXJuYWwgdGltZXN0YW1waW5n"
    "IHByb29mIGJ5IHByb29mLCBhbmQgd2l0bmVzc2VkIGhvdXJseSBieSBhbiBpbmRlcGVuZGVudCBwbGF0Zm9ybSAmbWRhc2g7IHVu"
    "YXR0ZW5kZWQsIHJ1bm5pbmcgbm93LiBBIHJlZ3VsYXRvciwgYW4gYXVkaXRvciBvciBhIGN1c3RvbWVyIGNoZWNrcyBhbnkgb2Yg"
    "aXQgdGhlbXNlbHZlcy4gVGhhdCBpcyB0aGUgcHJvZHVjdCwgYW5kIGl0IGV4aXN0cy48L3A+CjwvZGl2PgoKPGRpdiBjbGFzcz0i"
    "YmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDMgJm1kYXNoOyBXaHkgaW5jdW1iZW50cyBjYW4ndCBmb2xsb3c8L2Rp"
    "dj4KICA8aDI+VGhlIG1vYXQgaXMgc3RydWN0dXJhbCwgbm90IGEgaGVhZCBzdGFydC48L2gyPgogIDxwPkV2ZXJ5IGxvZ2dpbmcs"
    "IG1vbml0b3JpbmcgYW5kIGF1ZGl0IHBsYXRmb3JtIG9uIHRoZSBtYXJrZXQga2VlcHMgYSByZWNvcmQgaXRzIG93biBjdXN0b21l"
    "ciBjb250cm9scy4gVGhhdCBpcyBub3QgYSBmbGF3IHRoZXkgY2FuIHBhdGNoICZtZGFzaDsgaXQgaXMgdGhlIGZvdW5kYXRpb24g"
    "dGhlaXIgYnVzaW5lc3Mgc3RhbmRzIG9uLiBUbyBtYXRjaCBzZWJiaS5wcm8gdGhleSB3b3VsZCBoYXZlIHRvIGdpdmUgdGhlIGN1"
    "c3RvbWVyIGEgcmVjb3JkIHRoZSBjdXN0b21lciBjYW5ub3QgZWRpdCwgd2hpY2ggYnJlYWtzIHRoZSB0aGluZyB0aGV5IHNlbGwu"
    "PC9wPgogIDx1bD4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIHF1ZXN0aW9uLjwvYj4gIkNhbiB0aGUgcGVvcGxlIGJl"
    "aW5nIGF1ZGl0ZWQgZWRpdCB0aGUgYXVkaXQ/IiBpbmRpY3RzIHRoZWlyIGVudGlyZSBjYXRlZ29yeS4gVGhleSBhbnN3ZXIgbm8g"
    "YnkgYWRtaXR0aW5nIHRoZWlyIGV2aWRlbmNlIHdhcyBuZXZlciBldmlkZW5jZS48L2xpPgogICAgPGxpPjxiPlRoZXkgY2FuJ3Qg"
    "Y29weSB0aGUgdGltZS48L2I+IEFuIHVuYnJva2VuLCBleHRlcm5hbGx5IHdpdG5lc3NlZCByZWNvcmQgaXMgdGhlIG9uZSBpbnB1"
    "dCBub2JvZHkgY2FuIHNob3J0Y3V0LiBUaGUgb25seSB3YXkgdG8gaGF2ZSBsYXN0IHllYXIgY292ZXJlZCB3YXMgdG8gYmUgcmVj"
    "b3JkaW5nIGxhc3QgeWVhci48L2xpPgogICAgPGxpPjxiPlRoZXkgY2FuJ3QgY29weSB0aGUgaG9uZXN0eS48L2I+IEV2ZXJ5IGNv"
    "bXBldGl0b3Igb3ZlcmNsYWltcy4gc2ViYmkucHJvIHB1Ymxpc2hlcyBpdHMgb3duIGxpbWl0cyBvbiBldmVyeSBwYWdlIGFuZCBz"
    "ZWFscyB0aGVtIGludG8gaXRzIG93biBjaGFpbiAmbWRhc2g7IHdoaWNoIGlzIGV4YWN0bHkgdGhlIHByb3BlcnR5IGEgYnV5ZXIg"
    "b2YgZXZpZGVuY2UgaW5mcmFzdHJ1Y3R1cmUgaXMgcGF5aW5nIGZvci48L2xpPgogIDwvdWw+CgogIDxkaXYgY2xhc3M9InZlcmlm"
    "eS1ib3giPgogICAgPGg0PlZlcmlmeSBpdCBiZWZvcmUgeW91IHJlYWQgYW5vdGhlciBsaW5lPC9oND4KICAgIDxwPk5vdGhpbmcg"
    "aGVyZSBhc2tzIHRvIGJlIGJlbGlldmVkLiA8Y29kZT4veC93aXRuZXNzL3RpcDwvY29kZT4gcmV0dXJucyB0aGUgbGl2ZSBjaGFp"
    "biB0aXAuIDxjb2RlPi94L290cy9zdGF0dXM8L2NvZGU+IHNob3dzIHRoZSBzdGF0ZSBvZiBlYWNoIGV4dGVybmFsIHRpbWVzdGFt"
    "cCBwcm9vZiAmbWRhc2g7IHN1Ym1pdHRlZCBpcyBub3QgY29uZmlybWVkLCBhbmQgdGhlIHBhZ2Ugc2F5cyB3aGljaCBpcyB3aGlj"
    "aC4gPGNvZGU+L3gvcm9zdGVyL2xpc3Q8L2NvZGU+IHNob3dzIHRoZSBpbmRlcGVuZGVudCBwbGF0Zm9ybXMgd2l0bmVzc2luZyBp"
    "dC48L3A+CiAgICA8cCBzdHlsZT0ibWFyZ2luLWJvdHRvbTowIj5BbGwgcHVibGljLCBhbGwgbmVlZCBubyBhY2NvdW50LCBhbGwg"
    "YW5zd2VyIHRvIGFueW9uZS4gVGhlIG9mZmxpbmUgdmVyaWZpZXIgcmVhY2hlcyBhIHZlcmRpY3Qgd2l0aCB0aGUgd2lmaSBvZmYu"
    "PC9wPgogIDwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNsYXNzPSJibG9jay1udW0iPjA0ICZtZGFz"
    "aDsgVGhlIGVjb25vbWljczwvZGl2PgogIDxoMj5aZXJvIG1hcmdpbmFsIGNvc3QuIERpc3RyaWJ1dGlvbiBzY2FsZXMgd2l0aG91"
    "dCBoZWFkY291bnQuPC9oMj4KICA8cD5UaGUgc2FtZSBlbmdpbmUgc2VydmVzIG9uZSBjdXN0b21lciBvciB0ZW4gdGhvdXNhbmQg"
    "Jm1kYXNoOyBtYXJnaW5hbCBjb3N0IHBlciBhZGRpdGlvbmFsIGRldmljZSBpcyBlZmZlY3RpdmVseSB6ZXJvLiBUaGF0IG1ha2Vz"
    "IGRpc3RyaWJ1dGlvbiwgbm90IGVuZ2luZWVyaW5nLCB0aGUgZW50aXJlIGdyb3d0aCBsZXZlciwgYW5kIGl0IG1ha2VzIGEgcmVz"
    "ZWxsZXIgY2hhbm5lbCBwdXJlIG1hcmdpbiByYXRoZXIgdGhhbiBhIGNvc3QgbGluZS48L3A+CiAgPHA+PGI+NTBwIHBlciBhY3Rp"
    "dmUgZGV2aWNlIHBlciBtb250aDwvYj4sIG1ldGVyZWQgb24gcmVhbCB1c2FnZS4gUGFydG5lcnMgZW1iZWRkaW5nIHRoZSBwbGF0"
    "Zm9ybSBzZXQgdGhlaXIgb3duIGN1c3RvbWVyIHByaWNlIGFuZCBrZWVwIGV2ZXJ5dGhpbmcgYWJvdmUgdGhlIHBsYXRmb3JtIGZl"
    "ZS4gVGhlIHdpdG5lc3MgbmV0d29yayBzdGF5cyBmcmVlIGFuZCBvcGVuIGJ5IGRlc2lnbiAmbWRhc2g7IGl0IGlzIHRoZSBtZWNo"
    "YW5pc20gdGhhdCBtYWtlcyB0aGUgZXZpZGVuY2UgY3JlZGlibGUsIGFuZCBjaGFyZ2luZyBmb3IgaXQgd291bGQgd2Vha2VuIHRo"
    "ZSB0aGluZyBiZWluZyBzb2xkLjwvcD4KICA8cD5UaGUgcm91dGUgdG8gbWFya2V0IGlzIHRoZSBwbGF0Zm9ybXMsIG5vdCBvbmUg"
    "Y3VzdG9tZXIgYXQgYSB0aW1lLiBPdGhlciBjb21wbGlhbmNlIHBsYXRmb3JtcyBhbHJlYWR5IGhvbGQgcmVsYXRpb25zaGlwcyB3"
    "aXRoIHRoZSBleGFjdCBidXllcnMgd2hvIG5lZWQgdGhpcyBhbmQgYXJlIHVuaWZvcm1seSB3ZWFrIG9uIGV2aWRlbmNlLiBUaGUg"
    "ZW5naW5lIHNpdHMgdW5kZXJuZWF0aCB0aGVpciBwcm9kdWN0IGFzIHRoZSBldmlkZW5jZSBsYXllciB0aGV5IGNhbid0IGJ1aWxk"
    "IHRoZW1zZWx2ZXMuIEZpdmUgZm91bmRpbmcgc2VhdHM7IGZvdXIgYWxyZWFkeSB0YWtlbi48L3A+CjwvZGl2PgoKPGRpdiBjbGFz"
    "cz0iYmxvY2siPgogIDxkaXYgY2xhc3M9ImJsb2NrLW51bSI+MDUgJm1kYXNoOyBUaGUgYXNrPC9kaXY+CiAgPGgyPk9uZSBvcGVy"
    "YXRpbmcgcGFydG5lci4gMzAlIG9mIHRoZSBidXNpbmVzcy48L2gyPgogIDxkaXYgY2xhc3M9ImFzay1ib3giPgogICAgPGRpdiBj"
    "bGFzcz0iYXNrLWxhYmVsIj5PZmZlcmVkPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJhc2stYW1vdW50Ij4zMCUgZm9yIHRoZSByaWdo"
    "dDxicj5vcGVyYXRpbmcgcGFydG5lcjwvZGl2PgogICAgPHA+QnVpbHQgYW5kIHJ1biBhdCBuZWFyLXplcm8gZml4ZWQgY29zdCwg"
    "bGl2ZSBhbmQgcHJvdmVuLiBFdmVyeXRoaW5nIHRoZSBoYXJkIG1vbmV5IHVzdWFsbHkgZnVuZHMgaXMgYWxyZWFkeSBkb25lLiBU"
    "aGUgcGFydG5lciB3aG8gY2FuIG9wZW4gcmVndWxhdGVkIGVudGVycHJpc2UgYW5kIGdvdmVybm1lbnQgJm1kYXNoOyA8Yj5kZWZl"
    "bmNlLCBoZWFsdGhjYXJlLCB0ZWxlY29tbXVuaWNhdGlvbnM8L2I+ICZtZGFzaDsgdGFrZXMgYSBzdWJzdGFudGlhbCBzdGFrZSBp"
    "biBhIHBsYXRmb3JtIHRoYXQgaXMgcmVhZHkgdG8gc2NhbGUgdGhlIGRheSB0aGV5IHdhbGsgaW4uPC9wPgogICAgPGRpdiBjbGFz"
    "cz0idXNlLW9mLWZ1bmRzIj4KICAgICAgPGRpdiBjbGFzcz0idWYtcm93Ij48c3Bhbj5SZWd1bGF0ZWQgZW50ZXJwcmlzZSAmYW1w"
    "OyBnb3Zlcm5tZW50IGNoYW5uZWwgYWNjZXNzPC9zcGFuPjxzcGFuIGNsYXNzPSJ1Zi1wY3QiPmNvcmU8L3NwYW4+PC9kaXY+CiAg"
    "ICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+UmVzZWxsZXIgLyBNU1AgZGlzdHJpYnV0aW9uIGF0IHNjYWxlPC9zcGFuPjxz"
    "cGFuIGNsYXNzPSJ1Zi1wY3QiPmNvcmU8L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+RXh0ZXJu"
    "YWwgc2VjdXJpdHkgYXVkaXQgJmFtcDsgbGVnYWwgcmV2aWV3IG9mIGNsYWltczwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5m"
    "dW5kPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPkluZnJhc3RydWN0dXJlIGhhcmRlbmluZyBm"
    "b3IgZW50ZXJwcmlzZSBsb2FkPC9zcGFuPjxzcGFuIGNsYXNzPSJ1Zi1wY3QiPmZ1bmQ8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4K"
    "ICA8L2Rpdj4KICA8cCBzdHlsZT0ibWFyZ2luLXRvcDoxNnB4Ij5UaGVzZSBhcmUgc2VjdG9ycyB3aGVyZSBldmlkZW5jZSBvYmxp"
    "Z2F0aW9ucyBhcmUgaGFyZGVzdCwgcHJvY3VyZW1lbnQgcnVucyBlaWdodGVlbiBtb250aHMsIGFuZCBhIGZvdW5kZXIgYWxvbmUg"
    "ZG9lcyBub3QgZ2V0IGluIHRoZSByb29tLiBUaGUgZWNvbm9taWNzIHN1aXQgZXhhY3RseSB0aGF0OiBoaWdoLXZhbHVlLCBsb25n"
    "LWN5Y2xlLCBhbmQgc2VydmVkIGJ5IGFuIGVuZ2luZSB0aGF0IGNvc3RzIG5vdGhpbmcgbW9yZSB0byBydW4gYXQgYSB0aG91c2Fu"
    "ZCBjdXN0b21lcnMgdGhhbiBhdCBvbmUuPC9wPgo8L2Rpdj4KCjwvZGl2PgoKPGRpdiBjbGFzcz0iY29udGFjdC1ibG9jayB3cmFw"
    "Ij4KICA8ZGl2IGNsYXNzPSJjb250YWN0LWNhcmQiPgogICAgPGgzPlRhbGsgdG8gdGhlIGZvdW5kZXIgZGlyZWN0bHk8L2gzPgog"
    "ICAgPHA+VGhlIGZ1bGwgdGVjaG5pY2FsIGRlbW9uc3RyYXRpb24gdGFrZXMgZmlmdGVlbiBtaW51dGVzLCBhbmQgZXZlcnkgY2xh"
    "aW0gb24gdGhpcyBwYWdlIGNhbiBiZSB2ZXJpZmllZCBsaXZlIGR1cmluZyBpdC48L3A+CiAgICA8ZGl2IGNsYXNzPSJjb250YWN0"
    "LWxpbmtzIj4KICAgICAgPGEgaHJlZj0ibWFpbHRvOmp1c3RyaWdodGRlY29yYXRvcnNAZ21haWwuY29tIj5qdXN0cmlnaHRkZWNv"
    "cmF0b3JzQGdtYWlsLmNvbTwvYT4KICAgICAgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8iPnNlYmJpLnBybzwvYT4KICAgICAg"
    "PGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8vbWFwIj5zZWJiaS5wcm8vbWFwICZtZGFzaDsgdGhlIHN5c3RlbSwgbWFwcGVkPC9h"
    "PgogICAgICA8YSBocmVmPSJodHRwczovL3NlYmJpLnByby93aGl0ZXBhcGVyIj5zZWJiaS5wcm8vd2hpdGVwYXBlcjwvYT4KICAg"
    "IDwvZGl2PgogIDwvZGl2Pgo8L2Rpdj4KCjxmb290ZXIgY2xhc3M9IndyYXAiPgogIDxwPkp1c3RpbiBBbnRvbnkgRG9ic29uICZt"
    "aWRkb3Q7IE1vbm9wIENvbnRlbnQgJm1pZGRvdDsgQmx5dGgsIE5vcnRodW1iZXJsYW5kLCBVSzxicj4KICBUaGlzIGRvY3VtZW50"
    "IGlzIGEgc3VtbWFyeSBmb3IgaW5mb3JtYXRpb24gYW5kIGRvZXMgbm90IGNvbnN0aXR1dGUgYW4gb2ZmZXIgb2Ygc2VjdXJpdGll"
    "cy4gQWxsIGZpZ3VyZXMgc2hvdWxkIGJlIGluZGVwZW5kZW50bHkgdmVyaWZpZWQgYmVmb3JlIGFueSBpbnZlc3RtZW50IGRlY2lz"
    "aW9uLiBSZWd1bGF0b3J5IGRhdGVzIGFyZSBzdGF0ZWQgYXMgYW1lbmRlZCBieSB0aGUgQUkgT21uaWJ1cyBhbmQgYXJlIHN1Ympl"
    "Y3QgdG8gY2hhbmdlLjwvcD4KPC9mb290ZXI+Cgo8c2NyaXB0PgogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdkb2MtZGF0ZScp"
    "LnRleHRDb250ZW50ID0gbmV3IERhdGUoKS50b0xvY2FsZURhdGVTdHJpbmcoJ2VuLUdCJyx7ZGF5OidudW1lcmljJyxtb250aDon"
    "bG9uZycseWVhcjonbnVtZXJpYyd9KTsKICB2YXIgZGVhZGxpbmUgPSBuZXcgRGF0ZSgnMjAyNy0xMi0wMlQwMDowMDowMFonKTsK"
    "ICB2YXIgbm93ID0gbmV3IERhdGUoKTsKICB2YXIgZGF5cyA9IE1hdGgubWF4KDAsIE1hdGguY2VpbCgoZGVhZGxpbmUgLSBub3cp"
    "IC8gKDEwMDAqNjAqNjAqMjQpKSk7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvdW50ZG93bi1kYXlzJykudGV4dENvbnRl"
    "bnQgPSBkYXlzLnRvTG9jYWxlU3RyaW5nKCkgKyAnIGRheXMnOwo8L3NjcmlwdD4KCjwvYm9keT4KPC9odG1sPgo="
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
            "note": "Hit /x/investor/status once after each deploy to arm " + PAGE_PATH + ".",
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

498 lines, 22905 bytes

```python
import re
import sqlite3
import time
from datetime import datetime, timezone

VERSION = "1.4"
HEX64 = re.compile(r"^[0-9a-f]{64}$")

PUBLIC = {("GET", "trace"), ("GET", "impact"), ("GET", "receipt"),
          ("GET", "spec"), ("GET", "status"), ("GET", "health")}

OUR_CHAIN_NAME = "aileash"
DEFAULT_BASE = "https://sebbi.pro"

MAX_INPUTS = 50
DEFAULT_DEPTH = 3
MAX_DEPTH = 6
MAX_NODES = 400
ROLES = ("input", "model", "data", "policy", "document", "upstream-decision",
         "supplier", "other")
ACTIONS = ("status", "health", "spec", "trace", "impact", "receipt", "declare")

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


def _one(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else ""
    return value


def _depth_arg(data):
    raw = _one((data or {}).get("depth", DEFAULT_DEPTH))
    try:
        depth = int(str(raw).strip())
    except Exception:
        depth = DEFAULT_DEPTH
    if depth < 1:
        depth = 1
    if depth > MAX_DEPTH:
        depth = MAX_DEPTH
    return depth


def _receipt_arg(data):
    return str(_one((data or {}).get("receipt", ""))).strip().lower()


def _exists_locally(ctx, receipt):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT 1 FROM audit_log WHERE audit_hash=? LIMIT 1",
            (receipt,)).fetchone()
    return bool(row)


def _parents(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT parent_chain,parent_receipt,parent_base,role,note,declared,audit_hash "
            "FROM lineage_edge WHERE child_receipt=? ORDER BY id", (receipt,)).fetchall()


def _children(ctx, receipt):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT child_chain,child_receipt,role,declared,audit_hash "
            "FROM lineage_edge WHERE parent_receipt=? ORDER BY id", (receipt,)).fetchall()


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
    child = str(_one(data.get("receipt", data.get("child", "")))).strip().lower()
    if not HEX64.match(child):
        return {"error": "receipt_required",
                "message": "The audit hash of the decision whose inputs you are declaring."}, 400

    child_chain = _clean_chain(_one(data.get("chain")) or OUR_CHAIN_NAME)
    inputs = data.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        return {"error": "inputs_required",
                "message": "A list of what fed this decision. Each entry needs a receipt, and a "
                           "chain if it came from someone else.",
                "example": {"receipt": "<64 hex>", "inputs": [
                    {"chain": "supplier-name", "receipt": "<64 hex>", "role": "data",
                     "base": "https://supplier.example"}]}}, 400
    if len(inputs) > MAX_INPUTS:
        return {"error": "too_many_inputs",
                "message": "at most %d per declaration" % MAX_INPUTS}, 400

    if child_chain == OUR_CHAIN_NAME and not _exists_locally(ctx, child):
        return {"error": "unknown_receipt",
                "message": "That receipt is not in this chain. Declaring inputs for a decision "
                           "we never sealed would put an unverifiable node in the graph."}, 404

    prepared, pairs = [], set()
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
        if (parent_chain, parent) in pairs:
            return {"error": "duplicate_input",
                    "message": "the same chain and receipt appears twice in one declaration"}, 400
        pairs.add((parent_chain, parent))
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

    try:
        audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)
    except Exception as exc:
        return {"error": "seal_failed", "message": str(exc),
                "what_happened": "Nothing was written. The declaration is not recorded and the "
                                 "identical request can be sent again."}, 500
    if not audit_hash:
        return {"error": "seal_failed", "message": "seal returned no audit hash",
                "what_happened": "Nothing was written. The declaration is not recorded and the "
                                 "identical request can be sent again."}, 500

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
            except sqlite3.IntegrityError:
                duplicates += 1
            except Exception as exc:
                ctx["conn"].rollback()
                return {"error": "edge_write_failed", "message": str(exc),
                        "sealed_in_chain": audit_hash, "block_index": block_index,
                        "what_happened": "The declaration was sealed but the edges were not "
                                         "stored. The seal stands as a dated record of the "
                                         "attempt; resend to store the edges."}, 500
        ctx["conn"].commit()

    return {"child_chain": child_chain, "child_receipt": child,
            "edges_recorded": written, "already_declared": duplicates,
            "declared_at": _iso(now),
            "sealed_in_chain": audit_hash, "block_index": block_index, "receipt_seq": seq,
            "lineage_version": VERSION,
            "already_declared_means": "Refused by the unique index because this exact child, "
                                      "chain and parent were declared before. Any other write "
                                      "failure is an error, not a duplicate.",
            "what_this_does": "The declaration is now a chain entry. It cannot be removed "
                              "without breaking every block after it, and it cannot be added "
                              "later without the timestamp showing when.",
            "trace": "%s/x/lineage/trace?receipt=%s" % (our_base, child),
            "portable_receipt": "%s/x/lineage/receipt?receipt=%s" % (our_base, child)}, 200


def _walk(ctx, start, depth, upstream):
    our_base = _get_base_url(ctx)
    seen = {start}
    nodes, edges, frontier = [], [], []
    frontier_keys = set()
    queue = [(start, 0)]
    truncated = False
    node_cap_hit = False

    while queue:
        receipt, level = queue.pop(0)
        rows = _parents(ctx, receipt) if upstream else _children(ctx, receipt)

        if level >= depth:
            if rows:
                truncated = True
            continue
        if len(nodes) >= MAX_NODES:
            if rows:
                truncated = True
                node_cap_hit = True
            continue

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
                if (chain, other) not in frontier_keys:
                    frontier_keys.add((chain, other))
                    frontier.append({"chain": chain, "receipt": other, "depth": level + 1,
                                     "verify": _verification_plan(chain, other, base, our_base)})
                continue

            if other in seen:
                continue
            seen.add(other)
            if len(nodes) >= MAX_NODES:
                truncated = True
                node_cap_hit = True
                continue
            nodes.append({"chain": chain, "receipt": other, "depth": level + 1,
                          "verify": _verification_plan(chain, other, base, our_base)})
            queue.append((other, level + 1))

    return nodes, edges, frontier, truncated, node_cap_hit


def _truncation_note(truncated, node_cap_hit, depth):
    if not truncated:
        return None
    if node_cap_hit:
        return ("Stopped at the %d node ceiling. More declared hops exist beyond what is "
                "listed here." % MAX_NODES)
    return ("Stopped at depth %d. Nodes at that edge have further declared hops that were not "
            "followed - raise depth (max %d) to see them." % (depth, MAX_DEPTH))


def _trace(ctx, data):
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)
    our_base = _get_base_url(ctx)

    nodes, edges, frontier, truncated, cap = _walk(ctx, receipt, depth, upstream=True)
    if not edges:
        return {"receipt": receipt, "direction": "upstream", "nodes": [], "edges": [],
                "external_frontier": [], "truncated": False,
                "lineage_version": VERSION,
                "what_this_means": "No inputs have been declared for this decision. That is not "
                                   "the same as it having none - it means nobody said. "
                                   "Undeclared lineage is where a trail goes dark, and the party "
                                   "who did not declare is the one to ask.",
                "self": _verification_plan(OUR_CHAIN_NAME, receipt, our_base=our_base)}, 200

    return {"receipt": receipt, "direction": "upstream", "depth_searched": depth,
            "nodes": nodes, "edges": edges, "external_frontier": frontier,
            "truncated": truncated,
            "truncation_note": _truncation_note(truncated, cap, depth),
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
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    depth = _depth_arg(data)

    nodes, edges, frontier, truncated, cap = _walk(ctx, receipt, depth, upstream=False)
    return {"receipt": receipt, "direction": "downstream", "depth_searched": depth,
            "affected_decisions": len(nodes), "nodes": nodes, "edges": edges,
            "external_frontier": frontier, "truncated": truncated,
            "truncation_note": _truncation_note(truncated, cap, depth),
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


def _portable_receipt(ctx, data):
    receipt = _receipt_arg(data)
    if not HEX64.match(receipt):
        return {"error": "receipt_required"}, 400
    if not _exists_locally(ctx, receipt):
        return {"error": "unknown_receipt",
                "message": "Not a decision sealed in this chain."}, 404

    our_base = _get_base_url(ctx)
    rows = _parents(ctx, receipt)
    inputs = [{"chain": r[0], "receipt": r[1], "role": r[3],
               "declared_at": _iso(r[5]), "declaration_sealed_as": r[6],
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
            "walk_the_whole_chain": "%s/x/walk/status" % our_base,
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


def _status(ctx):
    our_base = _get_base_url(ctx)
    with ctx["lock"]:
        edges = ctx["conn"].execute("SELECT COUNT(*) FROM lineage_edge").fetchone()[0]
        children = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT child_receipt) FROM lineage_edge").fetchone()[0]
        external = ctx["conn"].execute(
            "SELECT COUNT(DISTINCT parent_chain) FROM lineage_edge "
            "WHERE parent_chain<>?", (OUR_CHAIN_NAME,)).fetchone()[0]
    return {"module": "lineage", "lineage_version": VERSION, "ok": True,
            "edges_declared": edges, "decisions_with_inputs": children,
            "external_chains_referenced": external,
            "spec": "%s/x/lineage/spec" % our_base}, 200


def _spec(ctx):
    our_base = _get_base_url(ctx)
    return {
        "module": "lineage", "lineage_version": VERSION,
        "what_it_does": "Records, as sealed chain entries, which decisions fed which other "
                        "decisions - across companies, without a shared database.",
        "routes": {
            "GET %s/x/lineage/status" % our_base: "counts, public",
            "GET %s/x/lineage/spec" % our_base: "this document, public",
            "GET %s/x/lineage/trace?receipt=<64hex>&depth=3" % our_base:
                "what fed this decision, public",
            "GET %s/x/lineage/impact?receipt=<64hex>&depth=3" % our_base:
                "what this decision fed, public",
            "GET %s/x/lineage/receipt?receipt=<64hex>" % our_base:
                "portable receipt for one decision, public",
            "POST %s/x/lineage/declare" % our_base:
                "declare inputs, requires an API key",
        },
        "declare_body": {"receipt": "<64 hex>", "chain": "aileash (optional)",
                         "inputs": [{"chain": "supplier-name", "receipt": "<64 hex>",
                                     "role": "data", "base": "https://supplier.example",
                                     "note": "optional, 200 chars"}]},
        "roles": list(ROLES),
        "limits": {"inputs_per_declaration": MAX_INPUTS, "default_depth": DEFAULT_DEPTH,
                   "max_depth": MAX_DEPTH, "max_nodes": MAX_NODES},
        "what_a_declaration_is": "A sealed, dated claim by the declaring party. Sealing makes it "
                                 "non-repudiable, not true.",
        "duplicates": "A repeat of the same child, chain and parent is refused by a unique index "
                      "and reported as already_declared. Any other write failure is an error.",
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    method = str(method or "GET").upper()
    action = str(action or "status").strip().lower().strip("/")
    data = data if isinstance(data, dict) else {}

    if action in ("", "index"):
        action = "status"

    if (method, action) not in PUBLIC and not api_key:
        return {"error": "api_key_required",
                "message": "Declaring lineage needs a key. Reading it never does."}, 401

    if action in ("status", "health"):
        return _status(ctx)
    if action == "spec":
        return _spec(ctx)
    if action == "trace":
        return _trace(ctx, data)
    if action == "impact":
        return _impact(ctx, data)
    if action == "receipt":
        return _portable_receipt(ctx, data)
    if action == "declare":
        if method == "GET":
            return {"error": "post_required",
                    "message": "Send this as POST with a JSON body and an API key.",
                    "spec": "%s/x/lineage/spec" % _get_base_url(ctx)}, 405
        return _declare(ctx, api_key, data)

    return {"error": "unknown_action", "action": action, "method": method,
            "known_actions": list(ACTIONS),
            "spec": "%s/x/lineage/spec" % _get_base_url(ctx)}, 404

```


## `modules/lineagedesk.py`

215 lines, 7806 bytes

```python
"""
Lineage desk - a keyed page at /lineage-desk.

Exists because lineage declare is POST-with-a-key, and a phone browser address
bar can send neither. Own _lineagedesk_patched attribute so it composes with
console.py, packconsole.py, peerconsole.py and binddesk.py.

Arm after every deploy by hitting /x/lineagedesk/status.
"""

VERSION = "1.0"

PUBLIC = {("GET", "status"), ("GET", "health"), ("GET", "spec")}

_patched = [False]

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lineage desk</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;padding:16px;background:#f5f5f5;color:#111}
h1{font-size:20px;margin:0 0 4px}
p.sub{margin:0 0 16px;color:#555;font-size:14px}
label{display:block;margin:12px 0 4px;font-size:14px;font-weight:500}
input,textarea,select{width:100%;padding:10px;font-size:15px;border:1px solid #ccc;
border-radius:6px;box-sizing:border-box;font-family:inherit}
textarea{min-height:90px;font-family:ui-monospace,monospace;font-size:13px}
button{width:100%;padding:12px;margin-top:12px;font-size:15px;font-weight:500;
border:0;border-radius:6px;background:#1a1a1a;color:#fff}
button.alt{background:#fff;color:#1a1a1a;border:1px solid #ccc}
.row{display:flex;gap:8px}
.row button{flex:1}
pre{background:#fff;border:1px solid #ddd;border-radius:6px;padding:12px;
white-space:pre-wrap;word-break:break-all;font-size:12px;margin-top:16px}
.card{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px;margin-bottom:16px}
small{color:#666;font-size:12px}
</style>
</head>
<body>
<h1>Lineage desk</h1>
<p class="sub">Declare what fed a decision, and read it back.</p>

<div class="card">
<label>API key</label>
<input id="key" type="password" placeholder="paste your key" autocomplete="off">
<small>Kept in this page only. Never sent anywhere but sebbi.pro.</small>
</div>

<div class="card">
<label>Decision receipt (the child, 64 hex)</label>
<input id="child" placeholder="audit hash of the decision" autocomplete="off">

<label>Input chain</label>
<input id="pchain" placeholder="aileash, mir, supplier-name" value="aileash" autocomplete="off">

<label>Input receipt (the parent, 64 hex)</label>
<input id="parent" placeholder="audit hash of what fed it" autocomplete="off">

<label>Role</label>
<select id="role">
<option>input</option><option>model</option><option>data</option>
<option>policy</option><option>document</option><option>upstream-decision</option>
<option>supplier</option><option>other</option>
</select>

<label>Their base address (optional)</label>
<input id="pbase" placeholder="https://supplier.example" autocomplete="off">

<label>Note (optional)</label>
<input id="note" placeholder="200 characters" autocomplete="off">

<button onclick="declareOne()">Declare this input</button>
</div>

<div class="card">
<label>Or paste a full declaration body</label>
<textarea id="raw" placeholder='{"receipt":"...","inputs":[{"chain":"mir","receipt":"..."}]}'></textarea>
<button class="alt" onclick="declareRaw()">Declare from JSON</button>
</div>

<div class="card">
<label>Read it back</label>
<div class="row">
<button class="alt" onclick="read('trace')">Trace up</button>
<button class="alt" onclick="read('impact')">Impact down</button>
</div>
<button class="alt" onclick="read('receipt')">Portable receipt</button>
<button class="alt" onclick="status()">Module status</button>
</div>

<pre id="out">Ready.</pre>

<script>
function val(id){return document.getElementById(id).value.trim();}
function show(o){document.getElementById('out').textContent =
  typeof o === 'string' ? o : JSON.stringify(o, null, 2);}

function post(body){
  var k = val('key');
  if(!k){show('Paste your API key first.');return;}
  show('Sending...');
  fetch('/x/lineage/declare', {
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+k},
    body:JSON.stringify(body)
  }).then(function(r){return r.json().then(function(j){
      return {http:r.status, response:j};});})
    .then(show).catch(function(e){show('Failed: '+e);});
}

function declareOne(){
  var child = val('child'), parent = val('parent');
  if(child.length !== 64){show('The decision receipt must be 64 hex characters.');return;}
  if(parent.length !== 64){show('The input receipt must be 64 hex characters.');return;}
  var item = {chain: val('pchain') || 'aileash', receipt: parent, role: val('role')};
  if(val('pbase')) item.base = val('pbase');
  if(val('note')) item.note = val('note');
  post({receipt: child, inputs: [item]});
}

function declareRaw(){
  var t = val('raw');
  if(!t){show('Nothing to send.');return;}
  var body;
  try{body = JSON.parse(t);}catch(e){show('That is not valid JSON: '+e);return;}
  post(body);
}

function read(action){
  var r = val('child');
  if(r.length !== 64){show('Put a 64 hex receipt in the decision receipt box.');return;}
  show('Reading...');
  fetch('/x/lineage/'+action+'?receipt='+encodeURIComponent(r))
    .then(function(x){return x.json();}).then(show)
    .catch(function(e){show('Failed: '+e);});
}

function status(){
  show('Reading...');
  fetch('/x/lineage/status').then(function(x){return x.json();})
    .then(show).catch(function(e){show('Failed: '+e);});
}
</script>
</body>
</html>"""


def _install_page(ctx):
    if _patched[0]:
        return "already installed"
    import sys
    s = sys.modules.get("__main__")
    if s is None or not hasattr(s, "get_bearer"):
        s = sys.modules.get("server")
    if s is None:
        return "server not found"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_lineagedesk_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path
        except Exception:
            p = self.path or ""
        if p.rstrip("/") == "/lineage-desk":
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return original(self)

    H.do_GET = do_GET
    H._lineagedesk_patched = True
    _patched[0] = True
    print("LINEAGEDESK: /lineage-desk installed at runtime", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    action = str(action or "status").strip().lower().strip("/")
    result = _install_page(ctx)

    if action in ("", "status", "health", "index"):
        return {"module": "lineagedesk", "version": VERSION, "ok": True,
                "page_install": result,
                "page": "https://sebbi.pro/lineage-desk",
                "note": "Hit this route after every deploy to arm the page."}, 200

    if action == "spec":
        return {"module": "lineagedesk", "version": VERSION,
                "what_it_does": "Serves a keyed page at /lineage-desk so lineage declarations "
                                "can be made from a phone, where a browser address bar cannot "
                                "send a POST or an Authorization header.",
                "page": "https://sebbi.pro/lineage-desk",
                "arm": "https://sebbi.pro/x/lineagedesk/status",
                "calls": ["POST /x/lineage/declare",
                          "GET /x/lineage/trace", "GET /x/lineage/impact",
                          "GET /x/lineage/receipt", "GET /x/lineage/status"]}, 200

    return {"error": "unknown_action", "action": action,
            "known_actions": ["status", "spec"]}, 404

```


## `modules/machine.py`

658 lines, 27386 bytes

```python
"""
modules/machine.py  v1.0.3  -  the machine

Ask it in a web address. It goes out to the internet, does the work, and
answers in data anyone - person or program - can check.

    https://sebbi.pro/x/machine/ask?q=find 35ff59fa
    https://sebbi.pro/x/machine/ask?q=bitcoin
    https://sebbi.pro/x/machine/ask?q=verify today
    https://sebbi.pro/x/machine/ask?q=block 2013
    https://sebbi.pro/x/machine/ask?q=check openai.com
    https://sebbi.pro/x/machine/ask?q=archive today
    https://sebbi.pro/x/machine/ask?q=witness
    https://sebbi.pro/x/machine/ask?q=walk
    https://sebbi.pro/x/machine/help

Every command is also its own route (/x/machine/find?sha256=..., etc).

Every answer carries:
  sources   - each thing it fetched, with the SHA-256 of what came back
  evidence  - what it computed from that
  check_it_yourself - how to redo the same work without this machine

The machine reads and checks. It never changes anything. All routes public.
"""

import base64
import gzip
import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.0.3"
SITE = "https://sebbi.pro"
BASE = SITE + "/x/machine/"
UA = "sebbi-machine/1.0.3 (+https://sebbi.pro/x/machine/help)"
TIMEOUT = 30
MAX_BYTES = 96 * 1024 * 1024
EXPLORERS = [
    ("mempool.space", "https://mempool.space/api"),
    ("blockstream.info", "https://blockstream.info/api"),
]

PUBLIC = {("GET", a) for a in (
    "help", "ask", "find", "verify", "bitcoin", "block", "check",
    "archive", "witness", "walk", "register", "status", "spec")}

_busy = threading.BoundedSemaphore(3)


# ---------------------------------------------------------------- fetching

class _Trail(object):
    """Every fetch is recorded with the hash of what came back."""

    def __init__(self):
        self.sources = []

    def get(self, url, max_bytes=MAX_BYTES, accept="application/json"):
        t0 = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read(max_bytes + 1)
                final = resp.geturl()
        except urllib.error.HTTPError as exc:
            self.sources.append({"url": url, "result": "HTTP %s" % exc.code})
            raise
        except Exception as exc:
            self.sources.append({"url": url, "result": "unreachable (%s)"
                                 % exc.__class__.__name__})
            raise
        if len(raw) > max_bytes:
            self.sources.append({"url": url, "result": "too large"})
            raise ValueError("response too large")
        compressed = raw[:2] == b"\x1f\x8b"
        if compressed:
            # Archives keep a page exactly as it was sent - often zipped.
            raw = gzip.decompress(raw)
        self.sources.append({"url": url, "final_url": final,
                             "was_compressed": compressed,
                             "bytes": len(raw),
                             "sha256": hashlib.sha256(raw).hexdigest(),
                             "ms": int((time.time() - t0) * 1000)})
        return raw

    def json(self, url, **kw):
        return json.loads(self.get(url, **kw).decode("utf-8"))

    def text(self, url):
        return self.get(url, accept="text/plain").decode("utf-8").strip()


def _public_https(url):
    """For addresses a caller supplies: https, port 443, public host only."""
    try:
        p = urllib.parse.urlsplit(url)
    except Exception:
        return False
    if p.scheme != "https" or p.port not in (None, 443) or not p.hostname:
        return False
    if p.username or p.password:
        return False
    try:
        for info in socket.getaddrinfo(p.hostname, 443,
                                       proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            if (ip.is_private or ip.is_loopback or ip.is_link_local or
                    ip.is_reserved or ip.is_multicast or ip.is_unspecified):
                return False
    except Exception:
        return False
    return True


def _canonical_sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")
                          ).hexdigest()


def _answer(command, answer, evidence, trail, check, ok=True, **extra):
    out = {"ok": ok, "machine": VERSION, "command": command,
           "answer": answer, "evidence": evidence,
           "sources": trail.sources, "check_it_yourself": check,
           "answered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    out.update(extra)
    return out


# ---------------------------------------------------------------- the chain

def _recompute(blocks, prev="GENESIS"):
    problems, public, withheld = [], 0, 0
    for b in blocks:
        h = b.get("audit_hash")
        if "preimage" in b:
            pre = b["preimage"]
            if hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                problems.append("block %s does not recompute" % b.get("block_index"))
            try:
                stated = json.loads(pre).get("prev_hash")
            except Exception:
                stated = None
            public += 1
        else:
            stated = b.get("prev_hash")
            withheld += 1
        if stated != prev:
            problems.append("block %s does not link to the block before it"
                            % b.get("block_index"))
        prev = h
    return {"blocks": len(blocks), "recomputed_from_own_text": public,
            "linkage_only": withheld, "tip": prev,
            "problems": problems[:20]}


def _walk_all(trail):
    blocks, after = [], 0
    while True:
        page = trail.json("%s/x/walk/blocks?after=%d&limit=500" % (SITE, after))
        blocks.extend(page.get("blocks") or [])
        if not page.get("has_more"):
            return blocks
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            raise ValueError("walk paging did not advance")
        after = nxt


def cmd_walk(q):
    t = _Trail()
    blocks = _walk_all(t)
    r = _recompute(blocks)
    ok = not r["problems"]
    return _answer(
        "walk",
        "Walked all %d blocks from genesis to tip and recomputed them: %s."
        % (r["blocks"], "PASS" if ok else "FAIL"),
        r, t,
        ["Fetch https://sebbi.pro/x/walk/blocks?after=0&limit=500 and each "
         "next page", "For every block with a preimage: SHA-256 it, compare "
         "with audit_hash, and check its prev_hash is the block before",
         "Method: https://sebbi.pro/x/walk/spec"], ok=ok)


def cmd_block(q):
    t = _Trail()
    try:
        n = int(q.get("n") or q.get("index"))
    except (TypeError, ValueError):
        return _answer("block", "Give a block number, e.g. block 2013.", {},
                       t, [], ok=False)
    data = t.json("%s/x/walk/block?index=%d" % (SITE, n))
    b = data.get("block") or {}
    ev = {"block_index": n, "audit_hash": b.get("audit_hash"),
          "previous_block_hash": data.get("previous_audit_hash")}
    if "preimage" in b:
        pre = b["preimage"]
        ev["recomputed_hash"] = hashlib.sha256(pre.encode("utf-8")).hexdigest()
        ev["matches"] = ev["recomputed_hash"] == b.get("audit_hash")
        try:
            ev["sealed_text"] = json.loads(pre)
            ev["links_to_previous"] = (ev["sealed_text"].get("prev_hash") ==
                                       data.get("previous_audit_hash"))
        except Exception:
            pass
        ans = ("Block %d recomputes from its own sealed text and links to the "
               "block before it." % n) if ev.get("matches") and \
            ev.get("links_to_previous") else "Block %d does NOT check out." % n
        ok = bool(ev.get("matches") and ev.get("links_to_previous"))
    else:
        ev["withheld_reason"] = b.get("withheld_reason")
        ev["links_to_previous"] = b.get("prev_hash") == data.get("previous_audit_hash")
        ans = ("Block %d is withheld from public view (%s); its link to the "
               "block before it checks out." % (n, b.get("withheld_reason")))
        ok = bool(ev["links_to_previous"])
    return _answer("block", ans, ev, t,
                   ["Open https://sebbi.pro/x/walk/block?index=%d" % n,
                    "SHA-256 the preimage text; it must equal audit_hash"],
                   ok=ok)


# ---------------------------------------------------------------- archive files

def _manifest(t):
    return t.json(SITE + "/x/archive/manifest").get("files") or []


def _resolve_file(t, ref):
    """ref: 'today', 'latest', a date, or a fingerprint or its prefix."""
    files = _manifest(t)
    ref = (ref or "latest").strip().lower()
    if ref in ("today", "latest", ""):
        return files[0] if files else None
    for f in files:
        if f.get("date") == ref:
            return f
        if len(ref) >= 8 and str(f.get("sha256", "")).startswith(ref):
            return f
    return None


def _wayback_captures(t, target):
    """Every capture the Internet Archive holds of an address, newest first.
    Uses the capture index; falls back to the availability lookup."""
    try:
        rows = t.json("https://web.archive.org/cdx/search/cdx?url=" +
                      urllib.parse.quote(target, safe="") +
                      "&output=json&filter=statuscode:200&limit=-10")
        stamps = [r[1] for r in rows[1:] if len(r) > 1]
        if stamps:
            return sorted(stamps, reverse=True)
    except Exception:
        pass
    try:
        avail = t.json("https://archive.org/wayback/available?url=" +
                       urllib.parse.quote(target, safe=""))
        snap = (avail.get("archived_snapshots") or {}).get("closest") or {}
        if snap.get("available"):
            return [re.sub(r"[^0-9]", "", str(snap.get("timestamp", "")))]
        return []
    except Exception:
        return None


def cmd_find(q):
    """Hunt for copies of an archive file across the internet, and prove
    each one is the sealed file."""
    t = _Trail()
    ref = q.get("sha256") or q.get("ref") or "latest"
    f = _resolve_file(t, ref)
    if not f:
        return _answer("find", "No sealed file matches '%s'." % ref, {}, t,
                       ["List every sealed file: https://sebbi.pro/x/archive/manifest"],
                       ok=False)
    sha = f["sha256"]
    file_url = "%s/x/archive/file?sha256=%s" % (SITE, sha)
    copies = []

    # 1. the operator's own server
    try:
        body = json.loads(t.get(file_url).decode("utf-8"))
        got = _canonical_sha(body)
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "fingerprint": got, "is_the_sealed_file": got == sha})
    except Exception:
        copies.append({"where": "sebbi.pro (the operator)", "url": file_url,
                       "found": False})

    # 2. the Internet Archive - independent, owes nothing to the operator
    stamps = _wayback_captures(t, file_url)
    if stamps is None:
        copies.append({"where": "Internet Archive (independent)",
                       "found": None, "note": "archive could not be asked"})
    elif not stamps:
        copies.append({"where": "Internet Archive (independent)",
                       "found": False,
                       "archive_it_now": "https://web.archive.org/save/" + file_url,
                       "note": "Not archived yet. Opening archive_it_now "
                               "from any phone or browser makes an "
                               "independent copy."})
    else:
        best = None
        for stamp in stamps[:3]:
            raw_url = "https://web.archive.org/web/%sid_/%s" % (stamp, file_url)
            try:
                body = json.loads(t.get(raw_url).decode("utf-8"))
                got = _canonical_sha(body)
                best = {"where": "Internet Archive (independent)",
                        "url": "https://web.archive.org/web/%s/%s" % (stamp, file_url),
                        "raw_copy": raw_url, "captured": stamp,
                        "fingerprint": got, "is_the_sealed_file": got == sha,
                        "captures_listed": len(stamps)}
                if got == sha:
                    break
            except Exception:
                best = best or {"where": "Internet Archive (independent)",
                                "found": True, "captured": stamp,
                                "note": "capture listed but could not be read"}
        copies.append(best)

    # 3. registered holders (custody) - read if the module exists
    try:
        holders = t.json(SITE + "/x/custody/holders").get("holders") or []
        for h in holders:
            copies.append({"where": h.get("name") or "holder",
                           "url": h.get("url"),
                           "fingerprint": h.get("last_fingerprint"),
                           "is_the_sealed_file": h.get("last_fingerprint") == sha,
                           "last_verified": h.get("last_verified")})
    except Exception:
        pass

    verified = [c for c in copies if c.get("is_the_sealed_file")]
    independent = [c for c in verified if "operator" not in c["where"]]
    return _answer(
        "find",
        "Found %d verified cop%s of file %s… (%d independent of sebbi.pro)."
        % (len(verified), "y" if len(verified) == 1 else "ies", sha[:12],
           len(independent)),
        {"file": {"date": f.get("date"), "sha256": sha,
                  "sealed_in_block": f.get("sealed_in_block"),
                  "check_block": f.get("check_block")},
         "copies": copies}, t,
        ["Take any copy's raw bytes, parse the JSON, re-serialise it with "
         "sorted keys and no spaces, SHA-256 it",
         "It must equal the fingerprint sealed in block %s" % f.get("sealed_in_block"),
         "Then run the checker inside the file: python3 -c \"import json,sys;"
         "exec(json.load(open(sys.argv[1]))['verifier_py'])\" FILE.json"])


def cmd_verify(q):
    """Verify a whole archive file here: fingerprint, every block, every link."""
    t = _Trail()
    url = q.get("url")
    sealed = {f["sha256"]: f for f in _manifest(t)}
    if url:
        if not _public_https(url):
            return _answer("verify", "Only public https addresses are fetched.",
                           {}, t, [], ok=False)
        where = url
    else:
        f = _resolve_file(t, q.get("sha256") or q.get("ref") or "latest")
        if not f:
            return _answer("verify", "No sealed file matches that.", {}, t,
                           [], ok=False)
        where = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"])
    body = json.loads(t.get(where).decode("utf-8"))
    fp = _canonical_sha(body)
    chain = (body.get("chain") or {})
    r = _recompute(chain.get("blocks") or [])
    checks = {
        "fingerprint": fp,
        "fingerprint_is_sealed": fp in sealed,
        "sealed_in_block": (sealed.get(fp) or {}).get("sealed_in_block"),
        "chain": r,
        "tip_matches_declared": r["tip"] == chain.get("tip"),
        "genesis_matches_declared": bool(chain.get("blocks")) and
        chain["blocks"][0].get("audit_hash") == chain.get("genesis_hash"),
        "previous_file": body.get("previous_file_sha256"),
    }
    ok = (checks["fingerprint_is_sealed"] and not r["problems"] and
          checks["tip_matches_declared"] and checks["genesis_matches_declared"])
    return _answer(
        "verify",
        "%s: file %s… is %s, and its %d blocks %s." % (
            "PASS" if ok else "FAIL", fp[:12],
            "a sealed file" if checks["fingerprint_is_sealed"] else "NOT a sealed file",
            r["blocks"], "all check out" if not r["problems"] else "do not all check out"),
        checks, t,
        ["The same checks run with nothing from us: the program is inside the "
         "file. python3 -c \"import json,sys;exec(json.load(open(sys.argv[1]))"
         "['verifier_py'])\" FILE.json"], ok=ok)


def cmd_archive(q):
    """Ask the Internet Archive to take an independent copy, and hand back
    a one-tap link that works from any phone if it refuses a server."""
    t = _Trail()
    what = (q.get("what") or "today").strip().lower()
    if what in ("today", "latest", "file"):
        f = _resolve_file(t, "latest")
        target = "%s/x/archive/file?sha256=%s" % (SITE, f["sha256"]) if f else None
    elif what.startswith("block"):
        n = re.sub(r"[^0-9]", "", what)
        target = "%s/x/walk/block?index=%s" % (SITE, n) if n else None
    elif what in ("chain", "genesis"):
        target = SITE + "/x/walk/genesis"
    elif what in ("register", "ratings"):
        target = SITE + "/x/integrity/register"
    else:
        target = None
    if not target:
        return _answer("archive", "Say what to archive: today, block 2013, "
                       "genesis or register.", {}, t, [], ok=False)
    tap = "https://web.archive.org/save/" + target
    result = None
    try:
        t.get(tap, accept="*/*", max_bytes=4 * 1024 * 1024)
        result = "the archive accepted the request from this server"
    except Exception:
        result = ("the archive turned this server away, as it often does "
                  "with cloud servers - the one-tap link below works from "
                  "any phone or browser")
    return _answer(
        "archive",
        "Archive request for %s: %s." % (target, result),
        {"target": target, "one_tap_archive": tap,
         "then_find_it": BASE + "find?ref=latest"}, t,
        ["Open one_tap_archive on your own device", "Then ask the machine to "
         "find it: https://sebbi.pro/x/machine/ask?q=find today"])


# ---------------------------------------------------------------- bitcoin

def cmd_bitcoin(q):
    """Follow the chain's anchor all the way into Bitcoin, and check it
    against two independent Bitcoin explorers."""
    t = _Trail()
    a = t.json(SITE + "/x/ots/latest_confirmed")
    if not a.get("ok"):
        return _answer("bitcoin", "No confirmed Bitcoin proof yet.", a, t, [],
                       ok=False)
    tip = str(a.get("tip") or "").lower()
    ev = {"chain_tip": tip, "tip_is_block": a.get("tip_is_block"),
          "stamp_id": a.get("stamp_id")}
    attest = []
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(
            base64.b64decode(a["ots_base64"])))
        tb = bytes.fromhex(tip)
        forms = {
            "sha256 of the tip's bytes": hashlib.sha256(tb).digest(),
            "the tip's bytes directly": tb,
            "sha256 of the tip as text": hashlib.sha256(tip.encode("ascii")).digest(),
            "sha256 of the tip as a line of text":
                hashlib.sha256((tip + "\n").encode("ascii")).digest(),
        }
        match = [name for name, d in forms.items() if det.file_digest == d]
        ev["proof_is_for_this_tip"] = bool(match)
        ev["proof_commits_to"] = match[0] if match else None
        for msg, att in det.timestamp.all_attestations():
            if isinstance(att, BitcoinBlockHeaderAttestation):
                attest.append((att.height, msg[::-1].hex()))
    except ImportError:
        ev["note"] = "proof reader not installed on this server"
    except Exception as exc:
        ev["note"] = "proof could not be read: %s" % exc.__class__.__name__
    if not attest:
        heights = a.get("bitcoin_block_heights") or []
        attest = [(h, None) for h in heights]
    results = []
    for height, expected_root in attest[:2]:
        row = {"bitcoin_block": height,
               "proof_computes_merkle_root": expected_root, "explorers": []}
        for name, api in EXPLORERS:
            try:
                bh = t.text("%s/block-height/%d" % (api, height))
                blk = t.json("%s/block/%s" % (api, bh))
                row["explorers"].append({
                    "explorer": name, "block_hash": bh,
                    "merkle_root": blk.get("merkle_root"),
                    "time": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(blk.get("timestamp", 0))),
                    "matches_proof": (expected_root is not None and
                                      blk.get("merkle_root") == expected_root)})
            except Exception:
                row["explorers"].append({"explorer": name,
                                         "result": "unreachable"})
        roots = set(e.get("merkle_root") for e in row["explorers"]
                    if e.get("merkle_root"))
        row["explorers_agree"] = len(roots) == 1
        row["proof_lands_on_block"] = bool(expected_root) and \
            roots == {expected_root}
        results.append(row)
    ev["bitcoin"] = results
    ok = bool(results) and all(r.get("proof_lands_on_block") for r in results) \
        and ev.get("proof_is_for_this_tip", False)
    first = results[0] if results else {}
    when = next((e.get("time") for e in first.get("explorers", [])
                 if e.get("time")), None)
    return _answer(
        "bitcoin",
        ("The chain tip at block %s is committed in Bitcoin block %s (%s). "
         "The proof lands exactly on that block's merkle root, and two "
         "independent explorers agree on it." % (
             a.get("tip_is_block"), first.get("bitcoin_block"), when))
        if ok else "The Bitcoin proof could not be fully confirmed; see evidence.",
        ev, t,
        ["Download the proof: https://sebbi.pro/x/ots/latest_confirmed "
         "(ots_base64)", "Run: ots verify, which checks the same merkle root "
         "against your own Bitcoin node",
         "Or open the block on mempool.space and blockstream.info and compare "
         "its merkle root with proof_computes_merkle_root"], ok=ok)


# ---------------------------------------------------------------- others

def cmd_check(q):
    t = _Trail()
    d = (q.get("domain") or "").strip().lower()
    if not d:
        return _answer("check", "Give a domain, e.g. check openai.com.", {}, t,
                       [], ok=False)
    r = t.json(SITE + "/x/integrity/check?domain=" + urllib.parse.quote(d))
    return _answer(
        "check", "%s verifies as %s (%s)." % (d, r.get("verified_level"),
                                              r.get("badge")),
        {k: r.get(k) for k in ("domain", "verified_level", "badge",
                               "claimed_level", "overclaimed", "verdict",
                               "request_sealed", "verdict_sealed")}, t,
        ["Full result: https://sebbi.pro/x/integrity/check?domain=" + d,
         "The verdict is sealed in the block shown; recompute it with "
         "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_witness(q):
    t = _Trail()
    held = t.json("https://mir.events/v1/transparency/held/tips?peer=sebbi")
    tips = [e.get("peer_tip") for e in (held.get("tips") or []) if e.get("peer_tip")]
    found = []
    blocks = _walk_all(t)
    index = {b["audit_hash"]: b.get("block_index") for b in blocks}
    for tip in tips:
        if tip in index:
            found.append(index[tip])
    return _answer(
        "witness",
        "MIR, an independent chain, holds %d of sebbi.pro's tips; %d are "
        "blocks in the chain as served today." % (len(tips), len(found)),
        {"witness": "MIR (MIRegistry)", "tips_held": len(tips),
         "matched_blocks": sorted(found)[-20:]}, t,
        ["Fetch https://mir.events/v1/transparency/held/tips?peer=sebbi",
         "Look each peer_tip up in the walk; every match is a block MIR holds"])


def cmd_register(q):
    t = _Trail()
    r = t.json(SITE + "/x/integrity/register")
    rows = [{"domain": e.get("domain"), "level": e.get("verified_level"),
             "badge": e.get("badge"), "sealed_in_block": e.get("sealed_in_block")}
            for e in r.get("entries") or []]
    return _answer("register", "%d domains rated; every rating is sealed."
                   % len(rows), {"entries": rows}, t,
                   ["Recompute any rating's block: "
                    "https://sebbi.pro/x/machine/ask?q=block <number>"])


def cmd_help(q):
    ex = lambda s: BASE + "ask?q=" + urllib.parse.quote(s)
    return {"ok": True, "machine": VERSION,
            "what": "Ask in a web address. The machine goes out to the "
                    "internet, does the work, and answers with its sources "
                    "and a way to check the answer without it.",
            "commands": {
                "find <fingerprint|today|date>": ex("find today"),
                "verify <fingerprint|today>": ex("verify today"),
                "bitcoin": ex("bitcoin"),
                "block <number>": ex("block 2013"),
                "walk": ex("walk"),
                "check <domain>": ex("check openai.com"),
                "witness": ex("witness"),
                "archive <today|block N|genesis|register>": ex("archive today"),
                "register": ex("register"),
            },
            "rule": "The machine reads and checks. It never changes anything."}


COMMANDS = {"find": cmd_find, "verify": cmd_verify, "bitcoin": cmd_bitcoin,
            "block": cmd_block, "walk": cmd_walk, "check": cmd_check,
            "witness": cmd_witness, "archive": cmd_archive,
            "register": cmd_register, "help": cmd_help}


def _parse(text):
    text = str(text or "").strip()
    # Clean copy-pasted Markdown link syntax or attached URLs
    text = re.sub(r'\]?https?://\S+', '', text).strip()
    text = re.sub(r'^[\[\(\s]+|[\]\)\s]+$', '', text)

    words = text.split()
    if not words:
        return "help", {}
    cmd = words[0].lower()
    arg = " ".join(words[1:]).strip()
    q = {}
    if cmd in ("find", "verify"):
        q["ref"] = arg or "latest"
    elif cmd == "block":
        q["n"] = arg
    elif cmd == "check":
        q["domain"] = arg
    elif cmd == "archive":
        q["what"] = arg or "today"
    return cmd, q


def handle(method, action, data, api_key, ctx):
    q = {}
    for k, v in (data or {}).items():
        q[k] = v[0] if isinstance(v, list) and v else v
    action = action or "help"
    if action == "ask":
        action, parsed = _parse(q.get("q"))
        q.update(parsed)
    if action in ("status", "spec"):
        action = "help"
    fn = COMMANDS.get(action)
    if not fn:
        out = cmd_help(q)
        out.update({"ok": False, "error": "unknown command: %s" % action})
        return out, 404
    if action == "help":
        return fn(q), 200
    if not _busy.acquire(timeout=20):
        return {"ok": False, "error": "busy",
                "detail": "Three commands are running. Try again shortly."}, 429
    try:
        out = fn(q)
        return out, 200
    except Exception as exc:
        return {"ok": False, "command": action,
                "error": "%s: %s" % (exc.__class__.__name__, str(exc)[:200])}, 502
    finally:
        _busy.release()

```


## `modules/map.py`

238 lines, 17926 bytes

```python
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

```
