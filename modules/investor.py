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
