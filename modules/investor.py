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
