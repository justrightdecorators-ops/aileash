# Codebase — part 7 of 32

Contains:
- `modules/investor.py`
- `modules/lineage.py`
- `modules/map.py`
- `modules/mutual.py`
- `modules/network.py`


## `modules/investor.py`

284 lines, 23104 bytes

```python
"""
modules/investor.py  v1.2.0
Serves the investor / partner page at /investor-prospectus.

Page module, same family as map.py / console.py / network.py: a runtime do_GET
patch puts the page at a clean URL, armed by hitting /x/investor/status once
after each deploy. server.py is never edited. Page is base64-embedded.
"""

import base64
import sys

VERSION = "1.2.0"
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
    "LWNoYWluZWQsIGV4dGVybmFsbHkgYW5jaG9yZWQ8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPkNyb3NzLXdpdG5lc3NlZCBi"
    "eSBpbmRlcGVuZGVudCBzeXN0ZW1zPC9kaXY+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJwcm9vZiI+PGRpdiBjbGFzcz0icHJvb2Yt"
    "biBtb25vIj5QdWJsaWM8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1sIj5WZXJpZmlhYmxlIHdpdGggdGhlIHZlbmRvciBzd2l0Y2hl"
    "ZCBvZmY8L2Rpdj48ZGl2IGNsYXNzPSJwcm9vZi1zcmMiPlN0YW5kYWxvbmUgdmVyaWZpZXIsIG5vIGFjY291bnQ8L2Rpdj48L2Rp"
    "dj4KICA8L2Rpdj4KCiAgPHAgc3R5bGU9Im1hcmdpbi10b3A6MThweCI+VGhlIHdob2xlIHJhbmdlIHNoYXJlcyBvbmUgc3BpbmU6"
    "IGV2ZXJ5IGRlY2lzaW9uIHNlYWxlZCBhcyBpdCBoYXBwZW5zLCBhbmNob3JlZCB0byBhIGNsb2NrIG5vYm9keSBjb250cm9scywg"
    "YW5kIHdpdG5lc3NlZCBob3VybHkgYnkgYW4gaW5kZXBlbmRlbnQgcGxhdGZvcm0gJm1kYXNoOyB1bmF0dGVuZGVkLCBydW5uaW5n"
    "IG5vdy4gQSByZWd1bGF0b3IsIGFuIGF1ZGl0b3Igb3IgYSBjdXN0b21lciBjaGVja3MgYW55IG9mIGl0IHRoZW1zZWx2ZXMuIFRo"
    "YXQgaXMgdGhlIHByb2R1Y3QsIGFuZCBpdCBleGlzdHMuPC9wPgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNs"
    "YXNzPSJibG9jay1udW0iPjAzICZtZGFzaDsgV2h5IGluY3VtYmVudHMgY2FuJ3QgZm9sbG93PC9kaXY+CiAgPGgyPlRoZSBtb2F0"
    "IGlzIHN0cnVjdHVyYWwsIG5vdCBhIGhlYWQgc3RhcnQuPC9oMj4KICA8cD5FdmVyeSBsb2dnaW5nLCBtb25pdG9yaW5nIGFuZCBh"
    "dWRpdCBwbGF0Zm9ybSBvbiB0aGUgbWFya2V0IGtlZXBzIGEgcmVjb3JkIGl0cyBvd24gY3VzdG9tZXIgY29udHJvbHMuIFRoYXQg"
    "aXMgbm90IGEgZmxhdyB0aGV5IGNhbiBwYXRjaCAmbWRhc2g7IGl0IGlzIHRoZSBmb3VuZGF0aW9uIHRoZWlyIGJ1c2luZXNzIHN0"
    "YW5kcyBvbi4gVG8gbWF0Y2ggc2ViYmkucHJvIHRoZXkgd291bGQgaGF2ZSB0byBnaXZlIHRoZSBjdXN0b21lciBhIHJlY29yZCB0"
    "aGUgY3VzdG9tZXIgY2Fubm90IGVkaXQsIHdoaWNoIGJyZWFrcyB0aGUgdGhpbmcgdGhleSBzZWxsLjwvcD4KICA8dWw+CiAgICA8"
    "bGk+PGI+VGhleSBjYW4ndCBjb3B5IHRoZSBxdWVzdGlvbi48L2I+ICJDYW4gdGhlIHBlb3BsZSBiZWluZyBhdWRpdGVkIGVkaXQg"
    "dGhlIGF1ZGl0PyIgaW5kaWN0cyB0aGVpciBlbnRpcmUgY2F0ZWdvcnkuIFRoZXkgYW5zd2VyIG5vIGJ5IGFkbWl0dGluZyB0aGVp"
    "ciBldmlkZW5jZSB3YXMgbmV2ZXIgZXZpZGVuY2UuPC9saT4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIHRpbWUuPC9i"
    "PiBBbiB1bmJyb2tlbiwgZXh0ZXJuYWxseSB3aXRuZXNzZWQgcmVjb3JkIGlzIHRoZSBvbmUgaW5wdXQgbm9ib2R5IGNhbiBzaG9y"
    "dGN1dC4gVGhlIG9ubHkgd2F5IHRvIGhhdmUgbGFzdCB5ZWFyIGNvdmVyZWQgd2FzIHRvIGJlIHJlY29yZGluZyBsYXN0IHllYXIu"
    "PC9saT4KICAgIDxsaT48Yj5UaGV5IGNhbid0IGNvcHkgdGhlIGhvbmVzdHkuPC9iPiBFdmVyeSBjb21wZXRpdG9yIG92ZXJjbGFp"
    "bXMuIHNlYmJpLnBybyBwdWJsaXNoZXMgaXRzIG93biBsaW1pdHMgb24gZXZlcnkgcGFnZSBhbmQgc2VhbHMgdGhlbSBpbnRvIGl0"
    "cyBvd24gY2hhaW4gJm1kYXNoOyB3aGljaCBpcyBleGFjdGx5IHRoZSBwcm9wZXJ0eSBhIGJ1eWVyIG9mIGV2aWRlbmNlIGluZnJh"
    "c3RydWN0dXJlIGlzIHBheWluZyBmb3IuPC9saT4KICA8L3VsPgoKICA8ZGl2IGNsYXNzPSJ2ZXJpZnktYm94Ij4KICAgIDxoND5W"
    "ZXJpZnkgaXQgYmVmb3JlIHlvdSByZWFkIGFub3RoZXIgbGluZTwvaDQ+CiAgICA8cD5Ob3RoaW5nIGhlcmUgYXNrcyB0byBiZSBi"
    "ZWxpZXZlZC4gPGNvZGU+L3gvd2l0bmVzcy90aXA8L2NvZGU+IHJldHVybnMgdGhlIGxpdmUgY2hhaW4gdGlwLiA8Y29kZT4veC9v"
    "dHMvc3RhdHVzPC9jb2RlPiBzaG93cyBpdHMgZXh0ZXJuYWwgYW5jaG9yaW5nLCBwZXIgcHJvb2YuIDxjb2RlPi94L3Jvc3Rlci9s"
    "aXN0PC9jb2RlPiBzaG93cyB0aGUgaW5kZXBlbmRlbnQgcGxhdGZvcm1zIHdpdG5lc3NpbmcgaXQuPC9wPgogICAgPHAgc3R5bGU9"
    "Im1hcmdpbi1ib3R0b206MCI+QWxsIHB1YmxpYywgYWxsIG5lZWQgbm8gYWNjb3VudCwgYWxsIGFuc3dlciB0byBhbnlvbmUuIFRo"
    "ZSBvZmZsaW5lIHZlcmlmaWVyIHJlYWNoZXMgYSB2ZXJkaWN0IHdpdGggdGhlIHdpZmkgb2ZmLjwvcD4KICA8L2Rpdj4KPC9kaXY+"
    "Cgo8ZGl2IGNsYXNzPSJibG9jayI+CiAgPGRpdiBjbGFzcz0iYmxvY2stbnVtIj4wNCAmbWRhc2g7IFRoZSBlY29ub21pY3M8L2Rp"
    "dj4KICA8aDI+WmVybyBtYXJnaW5hbCBjb3N0LiBEaXN0cmlidXRpb24gc2NhbGVzIHdpdGhvdXQgaGVhZGNvdW50LjwvaDI+CiAg"
    "PHA+VGhlIHNhbWUgZW5naW5lIHNlcnZlcyBvbmUgY3VzdG9tZXIgb3IgdGVuIHRob3VzYW5kICZtZGFzaDsgbWFyZ2luYWwgY29z"
    "dCBwZXIgYWRkaXRpb25hbCBkZXZpY2UgaXMgZWZmZWN0aXZlbHkgemVyby4gVGhhdCBtYWtlcyBkaXN0cmlidXRpb24sIG5vdCBl"
    "bmdpbmVlcmluZywgdGhlIGVudGlyZSBncm93dGggbGV2ZXIsIGFuZCBpdCBtYWtlcyBhIHJlc2VsbGVyIGNoYW5uZWwgcHVyZSBt"
    "YXJnaW4gcmF0aGVyIHRoYW4gYSBjb3N0IGxpbmUuPC9wPgogIDxwPjxiPjUwcCBwZXIgYWN0aXZlIGRldmljZSBwZXIgbW9udGg8"
    "L2I+LCBtZXRlcmVkIG9uIHJlYWwgdXNhZ2UuIFBhcnRuZXJzIGVtYmVkZGluZyB0aGUgcGxhdGZvcm0gc2V0IHRoZWlyIG93biBj"
    "dXN0b21lciBwcmljZSBhbmQga2VlcCBldmVyeXRoaW5nIGFib3ZlIHRoZSBwbGF0Zm9ybSBmZWUuIFRoZSB3aXRuZXNzIG5ldHdv"
    "cmsgc3RheXMgZnJlZSBhbmQgb3BlbiBieSBkZXNpZ24gJm1kYXNoOyBpdCBpcyB0aGUgbWVjaGFuaXNtIHRoYXQgbWFrZXMgdGhl"
    "IGV2aWRlbmNlIGNyZWRpYmxlLCBhbmQgY2hhcmdpbmcgZm9yIGl0IHdvdWxkIHdlYWtlbiB0aGUgdGhpbmcgYmVpbmcgc29sZC48"
    "L3A+CiAgPHA+VGhlIHJvdXRlIHRvIG1hcmtldCBpcyB0aGUgcGxhdGZvcm1zLCBub3Qgb25lIGN1c3RvbWVyIGF0IGEgdGltZS4g"
    "T3RoZXIgY29tcGxpYW5jZSBwbGF0Zm9ybXMgYWxyZWFkeSBob2xkIHJlbGF0aW9uc2hpcHMgd2l0aCB0aGUgZXhhY3QgYnV5ZXJz"
    "IHdobyBuZWVkIHRoaXMgYW5kIGFyZSB1bmlmb3JtbHkgd2VhayBvbiBldmlkZW5jZS4gVGhlIGVuZ2luZSBzaXRzIHVuZGVybmVh"
    "dGggdGhlaXIgcHJvZHVjdCBhcyB0aGUgZXZpZGVuY2UgbGF5ZXIgdGhleSBjYW4ndCBidWlsZCB0aGVtc2VsdmVzLiBGaXZlIGZv"
    "dW5kaW5nIHNlYXRzOyBmb3VyIGFscmVhZHkgdGFrZW4uPC9wPgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImJsb2NrIj4KICA8ZGl2IGNs"
    "YXNzPSJibG9jay1udW0iPjA1ICZtZGFzaDsgVGhlIGFzazwvZGl2PgogIDxoMj5PbmUgb3BlcmF0aW5nIHBhcnRuZXIuIDMwJSBv"
    "ZiB0aGUgYnVzaW5lc3MuPC9oMj4KICA8ZGl2IGNsYXNzPSJhc2stYm94Ij4KICAgIDxkaXYgY2xhc3M9ImFzay1sYWJlbCI+T2Zm"
    "ZXJlZDwvZGl2PgogICAgPGRpdiBjbGFzcz0iYXNrLWFtb3VudCI+MzAlIGZvciB0aGUgcmlnaHQ8YnI+b3BlcmF0aW5nIHBhcnRu"
    "ZXI8L2Rpdj4KICAgIDxwPkJ1aWx0IGFuZCBydW4gYXQgbmVhci16ZXJvIGZpeGVkIGNvc3QsIGxpdmUgYW5kIHByb3Zlbi4gRXZl"
    "cnl0aGluZyB0aGUgaGFyZCBtb25leSB1c3VhbGx5IGZ1bmRzIGlzIGFscmVhZHkgZG9uZS4gVGhlIHBhcnRuZXIgd2hvIGNhbiBv"
    "cGVuIHJlZ3VsYXRlZCBlbnRlcnByaXNlIGFuZCBnb3Zlcm5tZW50ICZtZGFzaDsgPGI+ZGVmZW5jZSwgaGVhbHRoY2FyZSwgdGVs"
    "ZWNvbW11bmljYXRpb25zPC9iPiAmbWRhc2g7IHRha2VzIGEgc3Vic3RhbnRpYWwgc3Rha2UgaW4gYSBwbGF0Zm9ybSB0aGF0IGlz"
    "IHJlYWR5IHRvIHNjYWxlIHRoZSBkYXkgdGhleSB3YWxrIGluLjwvcD4KICAgIDxkaXYgY2xhc3M9InVzZS1vZi1mdW5kcyI+CiAg"
    "ICAgIDxkaXYgY2xhc3M9InVmLXJvdyI+PHNwYW4+UmVndWxhdGVkIGVudGVycHJpc2UgJmFtcDsgZ292ZXJubWVudCBjaGFubmVs"
    "IGFjY2Vzczwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5jb3JlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1y"
    "b3ciPjxzcGFuPlJlc2VsbGVyIC8gTVNQIGRpc3RyaWJ1dGlvbiBhdCBzY2FsZTwvc3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5j"
    "b3JlPC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJ1Zi1yb3ciPjxzcGFuPkV4dGVybmFsIHNlY3VyaXR5IGF1ZGl0ICZh"
    "bXA7IGxlZ2FsIHJldmlldyBvZiBjbGFpbXM8L3NwYW4+PHNwYW4gY2xhc3M9InVmLXBjdCI+ZnVuZDwvc3Bhbj48L2Rpdj4KICAg"
    "ICAgPGRpdiBjbGFzcz0idWYtcm93Ij48c3Bhbj5JbmZyYXN0cnVjdHVyZSBoYXJkZW5pbmcgZm9yIGVudGVycHJpc2UgbG9hZDwv"
    "c3Bhbj48c3BhbiBjbGFzcz0idWYtcGN0Ij5mdW5kPC9zcGFuPjwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+CiAgPHAgc3R5bGU9"
    "Im1hcmdpbi10b3A6MTZweCI+VGhlc2UgYXJlIHNlY3RvcnMgd2hlcmUgZXZpZGVuY2Ugb2JsaWdhdGlvbnMgYXJlIGhhcmRlc3Qs"
    "IHByb2N1cmVtZW50IHJ1bnMgZWlnaHRlZW4gbW9udGhzLCBhbmQgYSBmb3VuZGVyIGFsb25lIGRvZXMgbm90IGdldCBpbiB0aGUg"
    "cm9vbS4gVGhlIGVjb25vbWljcyBzdWl0IGV4YWN0bHkgdGhhdDogaGlnaC12YWx1ZSwgbG9uZy1jeWNsZSwgYW5kIHNlcnZlZCBi"
    "eSBhbiBlbmdpbmUgdGhhdCBjb3N0cyBub3RoaW5nIG1vcmUgdG8gcnVuIGF0IGEgdGhvdXNhbmQgY3VzdG9tZXJzIHRoYW4gYXQg"
    "b25lLjwvcD4KPC9kaXY+Cgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImNvbnRhY3QtYmxvY2sgd3JhcCI+CiAgPGRpdiBjbGFzcz0iY29u"
    "dGFjdC1jYXJkIj4KICAgIDxoMz5UYWxrIHRvIHRoZSBmb3VuZGVyIGRpcmVjdGx5PC9oMz4KICAgIDxwPlRoZSBmdWxsIHRlY2hu"
    "aWNhbCBkZW1vbnN0cmF0aW9uIHRha2VzIGZpZnRlZW4gbWludXRlcywgYW5kIGV2ZXJ5IGNsYWltIG9uIHRoaXMgcGFnZSBjYW4g"
    "YmUgdmVyaWZpZWQgbGl2ZSBkdXJpbmcgaXQuPC9wPgogICAgPGRpdiBjbGFzcz0iY29udGFjdC1saW5rcyI+CiAgICAgIDxhIGhy"
    "ZWY9Im1haWx0bzpqdXN0aW5AbW9ub3Bjb250ZW50LmNvbSI+anVzdGluQG1vbm9wY29udGVudC5jb208L2E+CiAgICAgIDxhIGhy"
    "ZWY9Imh0dHBzOi8vc2ViYmkucHJvIj5zZWJiaS5wcm88L2E+CiAgICAgIDxhIGhyZWY9Imh0dHBzOi8vc2ViYmkucHJvL21hcCI+"
    "c2ViYmkucHJvL21hcCAmbWRhc2g7IHRoZSBzeXN0ZW0sIG1hcHBlZDwvYT4KICAgICAgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5w"
    "cm8vd2hpdGVwYXBlciI+c2ViYmkucHJvL3doaXRlcGFwZXI8L2E+CiAgICA8L2Rpdj4KICA8L2Rpdj4KPC9kaXY+Cgo8Zm9vdGVy"
    "IGNsYXNzPSJ3cmFwIj4KICA8cD5KdXN0aW4gQW50b255IERvYnNvbiAmbWlkZG90OyBNb25vcCBDb250ZW50ICZtaWRkb3Q7IEJs"
    "eXRoLCBOb3J0aHVtYmVybGFuZCwgVUs8YnI+CiAgVGhpcyBkb2N1bWVudCBpcyBhIHN1bW1hcnkgZm9yIGluZm9ybWF0aW9uIGFu"
    "ZCBkb2VzIG5vdCBjb25zdGl0dXRlIGFuIG9mZmVyIG9mIHNlY3VyaXRpZXMuIEFsbCBmaWd1cmVzIHNob3VsZCBiZSBpbmRlcGVu"
    "ZGVudGx5IHZlcmlmaWVkIGJlZm9yZSBhbnkgaW52ZXN0bWVudCBkZWNpc2lvbi4gUmVndWxhdG9yeSBkYXRlcyBhcmUgc3RhdGVk"
    "IGFzIGFtZW5kZWQgYnkgdGhlIEFJIE9tbmlidXMgYW5kIGFyZSBzdWJqZWN0IHRvIGNoYW5nZS48L3A+CjwvZm9vdGVyPgoKPHNj"
    "cmlwdD4KICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG9jLWRhdGUnKS50ZXh0Q29udGVudCA9IG5ldyBEYXRlKCkudG9Mb2Nh"
    "bGVEYXRlU3RyaW5nKCdlbi1HQicse2RheTonbnVtZXJpYycsbW9udGg6J2xvbmcnLHllYXI6J251bWVyaWMnfSk7CiAgdmFyIGRl"
    "YWRsaW5lID0gbmV3IERhdGUoJzIwMjctMTItMDJUMDA6MDA6MDBaJyk7CiAgdmFyIG5vdyA9IG5ldyBEYXRlKCk7CiAgdmFyIGRh"
    "eXMgPSBNYXRoLm1heCgwLCBNYXRoLmNlaWwoKGRlYWRsaW5lIC0gbm93KSAvICgxMDAwKjYwKjYwKjI0KSkpOwogIGRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCdjb3VudGRvd24tZGF5cycpLnRleHRDb250ZW50ID0gZGF5cy50b0xvY2FsZVN0cmluZygpICsgJyBk"
    "YXlzJzsKPC9zY3JpcHQ+Cgo8L2JvZHk+CjwvaHRtbD4K"
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
