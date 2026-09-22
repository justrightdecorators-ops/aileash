# Codebase — part 20 of 39

Contains:
- `modules/studio.py`
- `modules/tokensaver.py`


## `modules/studio.py`

328 lines, 27911 bytes

```python
"""
modules/studio.py  v1.0.0
Monop Studio at /create: the content creator centre. A demo video plays in a
canvas player, the lock drops at the halfway mark, and one tap unlocks it with
a sealed paid-view receipt. Plus the pricing, the earnings calculator and the
creator control centre. The unlock is a demonstration and takes no payment.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/studio/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk1vbm9wIFN0dWRpbyDigJQgbW9ub3BvbGlzZSB5b3VyIGNvbnRlbnQ8L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlv"
    "biIgY29udGVudD0iUHV0IHlvdXIgdmlkZW8gYmVoaW5kIGEgdGFwLXRvLXBheSBsb2NrLiBWaWV3ZXJzIHBheSBwZW5uaWVzIHRv"
    "IHdhdGNoIHRoZSByZXN0LCB5b3Uga2VlcCBtb3N0IG9mIGl0LCBhbmQgZXZlcnkgcGFpZCB2aWV3IGlzIHNlYWxlZCBvbiBhIHB1"
    "YmxpYyBjaGFpbi4iPgo8bGluayBocmVmPSJodHRwczovL2ZvbnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PUlCTStQbGV4"
    "K01vbm86d2dodEA0MDA7NTAwOzYwMCZmYW1pbHk9SUJNK1BsZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1OZXdzcmVh"
    "ZGVyOm9wc3osd2dodEA2Li43Miw1MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8c3R5bGU+Cjpyb290ey0taW5r"
    "OiMwNTA3MGY7LS1pbmsyOiMwZDE0MjQ7LS1nb2xkOiNjOWE4NGM7LS1vazojN2ZlM2IwOy0tYmx1ZTojOGZkMGZmOy0tcGluazoj"
    "ZDU5YmZmOy0tbXV0ZTojOGE5M2FkOy0tbGluZTpyZ2JhKDIwMSwxNjgsNzYsLjIyKTstLW1vbm86J0lCTSBQbGV4IE1vbm8nLHVp"
    "LW1vbm9zcGFjZSxtb25vc3BhY2U7LS1zYW5zOidJQk0gUGxleCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidO"
    "ZXdzcmVhZGVyJyxHZW9yZ2lhLHNlcmlmfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdlYmtp"
    "dC10YXAtaGlnaGxpZ2h0LWNvbG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6cmFkaWFsLWdyYWRpZW50KGVsbGlwc2Ug"
    "YXQgNTAlIDAlLCMxYTEwMzggMCUsIzA1MDcwZiA2MiUpO2NvbG9yOiNlOGVkZjc7Zm9udC1mYW1pbHk6dmFyKC0tc2Fucyk7bGlu"
    "ZS1oZWlnaHQ6MS42O21pbi1oZWlnaHQ6MTAwdmh9Ci53cmFwe21heC13aWR0aDo5MDBweDttYXJnaW46MCBhdXRvO3BhZGRpbmc6"
    "MCAyMHB4IDcwcHh9Ci50b3B7ZGlzcGxheTpmbGV4O2p1c3RpZnktY29udGVudDpzcGFjZS1iZXR3ZWVuO2FsaWduLWl0ZW1zOmNl"
    "bnRlcjtwYWRkaW5nOmNhbGMoMTRweCArIGVudihzYWZlLWFyZWEtaW5zZXQtdG9wKSkgMCAwfQouYnJhbmR7Zm9udC1mYW1pbHk6"
    "dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEzcHh9LmJyYW5kIGJ7Y29sb3I6dmFyKC0tcGluayk7Zm9udC13ZWlnaHQ6NTAwfQoudG9w"
    "IGF7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tbXV0ZSk7dGV4dC1kZWNvcmF0aW9u"
    "Om5vbmU7bWFyZ2luLWxlZnQ6MTRweH0KLmhlcm97dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzo0MHB4IDAgNHB4fQoua2lja3tm"
    "b250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTEuNXB4O2xldHRlci1zcGFjaW5nOi4yZW07Y29sb3I6dmFyKC0tcGlu"
    "ayl9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsN3Z3LDU4"
    "cHgpO2xpbmUtaGVpZ2h0OjEuMDQ7bWFyZ2luOjEycHggYXV0byAxMnB4O21heC13aWR0aDoxNWNoO2JhY2tncm91bmQ6bGluZWFy"
    "LWdyYWRpZW50KDkwZGVnLCNmZmYsI2Q1OWJmZiA0MCUsI2M5YTg0YyA3MCUsIzdmZTNiMCk7LXdlYmtpdC1iYWNrZ3JvdW5kLWNs"
    "aXA6dGV4dDtiYWNrZ3JvdW5kLWNsaXA6dGV4dDtjb2xvcjp0cmFuc3BhcmVudH0KLmhlcm8gcHtjb2xvcjojYjZjMGQ2O21heC13"
    "aWR0aDo1NmNoO21hcmdpbjowIGF1dG87Zm9udC1zaXplOjE2LjVweH0KLyogcGxheWVyICovCi5wbGF5ZXJ7cG9zaXRpb246cmVs"
    "YXRpdmU7bWFyZ2luOjI2cHggYXV0byAwO21heC13aWR0aDo3MjBweDthc3BlY3QtcmF0aW86MTYvOTtib3JkZXItcmFkaXVzOjE2"
    "cHg7b3ZlcmZsb3c6aGlkZGVuO2JhY2tncm91bmQ6IzAzMDUwYjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JveC1zaGFk"
    "b3c6MCAzMHB4IDcwcHggcmdiYSgwLDAsMCwuNiksMCAwIDUwcHggcmdiYSgyMTMsMTU1LDI1NSwuMTUpfQoucGxheWVyIGNhbnZh"
    "c3t3aWR0aDoxMDAlO2hlaWdodDoxMDAlO2Rpc3BsYXk6YmxvY2t9Ci5wYmFye3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MDtyaWdo"
    "dDowO2JvdHRvbTowO2hlaWdodDo1cHg7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4xMil9Ci5wYmFyIGl7ZGlzcGxheTpi"
    "bG9jaztoZWlnaHQ6MTAwJTt3aWR0aDowO2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLHZhcigtLXBpbmspLHZhcigt"
    "LWdvbGQpLHZhcigtLW9rKSl9Ci5wYnRue3Bvc2l0aW9uOmFic29sdXRlO2xlZnQ6MTJweDtib3R0b206MTRweDtiYWNrZ3JvdW5k"
    "OnJnYmEoNSw3LDE1LC43KTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KTtjb2xvcjojZmZmO2JvcmRlci1y"
    "YWRpdXM6OTk5cHg7d2lkdGg6MzhweDtoZWlnaHQ6MzhweDtmb250LXNpemU6MTRweDtjdXJzb3I6cG9pbnRlcn0KLnB0aW1le3Bv"
    "c2l0aW9uOmFic29sdXRlO3JpZ2h0OjE0cHg7Ym90dG9tOjIwcHg7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtjb2xvcjojY2Zk"
    "NmU2O3RleHQtc2hhZG93OjAgMXB4IDRweCAjMDAwfQoubG9ja3twb3NpdGlvbjphYnNvbHV0ZTtpbnNldDowO2Rpc3BsYXk6bm9u"
    "ZTtmbGV4LWRpcmVjdGlvbjpjb2x1bW47YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7Z2FwOjEwcHg7"
    "dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyNHB4OwogYmFja2dyb3VuZDpyZ2JhKDUsNywxNSwuODIpO2JhY2tkcm9wLWZpbHRl"
    "cjpibHVyKDdweCl9Ci5sb2NrLm9ue2Rpc3BsYXk6ZmxleH0KLmxvY2sgLmlje2ZvbnQtc2l6ZTozMHB4fQoubG9jayBoM3tmb250"
    "LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyMHB4LDR2dywzMHB4KX0KLmxvY2sg"
    "cHtjb2xvcjojYjZjMGQ2O2ZvbnQtc2l6ZToxMy41cHg7bWF4LXdpZHRoOjQwY2h9Ci5wYXl7ZGlzcGxheTppbmxpbmUtZmxleDth"
    "bGlnbi1pdGVtczpjZW50ZXI7Z2FwOjhweDtiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOiMwNTA3MGY7Ym9yZGVyOjA7Ym9y"
    "ZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MTNweCAyMnB4O2ZvbnQ6NjAwIDE0cHggdmFyKC0tbW9ubyk7Y3Vyc29yOnBvaW50ZXI7"
    "Ym94LXNoYWRvdzowIDAgMjhweCByZ2JhKDIwMSwxNjgsNzYsLjQpfQoubWluaXtmb250OjUwMCAxMC41cHggdmFyKC0tbW9ubyk7"
    "Y29sb3I6dmFyKC0tbXV0ZSl9Ci5yZWNlaXB0e2ZvbnQ6NTAwIDExLjVweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1vayl9Ci8q"
    "IHNlY3Rpb25zICovCnNlY3Rpb257cGFkZGluZzo0NHB4IDAgMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1"
    "LC4wNyk7bWFyZ2luLXRvcDo0NHB4fQpoMntmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6"
    "ZTpjbGFtcCgyNXB4LDQuNXZ3LDM2cHgpO21hcmdpbi1ib3R0b206MTBweH0KLmxlYWR7Y29sb3I6I2I2YzBkNjttYXgtd2lkdGg6"
    "NjJjaDttYXJnaW4tYm90dG9tOjE4cHh9Ci5ncmlke2Rpc3BsYXk6Z3JpZDtnYXA6MTJweH1AbWVkaWEobWluLXdpZHRoOjcyMHB4"
    "KXsuZ3JpZC50d297Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnJ9LmdyaWQudGhyZWV7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5z"
    "OnJlcGVhdCgzLDFmcil9fQouY2FyZHtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjgpO2JvcmRlcjoxcHggc29saWQgdmFyKC0t"
    "bGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MThweH0KLmNhcmQgaDN7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2Zv"
    "bnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MjBweDttYXJnaW4tYm90dG9tOjZweH0uY2FyZCBwe2ZvbnQtc2l6ZToxNHB4O2NvbG9y"
    "OiNiNmMwZDZ9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udDo1MDAgMTFweCB2YXIoLS1tb25vKTtsZXR0ZXItc3BhY2luZzouMWVt"
    "O2NvbG9yOnZhcigtLW11dGUpO21hcmdpbjoxMnB4IDAgNHB4fQppbnB1dCxzZWxlY3R7d2lkdGg6MTAwJTtiYWNrZ3JvdW5kOiMw"
    "MzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtjb2xvcjojZmZmO3BhZGRpbmc6MTFw"
    "eDtmb250OjE0cHggdmFyKC0tbW9ubyl9Ci5jYWxjIGJ7Y29sb3I6dmFyKC0tb2spfQoub3V0e21hcmdpbi10b3A6MTRweDtiYWNr"
    "Z3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzoxNHB4"
    "O2ZvbnQ6MTNweCB2YXIoLS1tb25vKTtjb2xvcjojY2ZlNmQ5fQoub3V0IC5iaWd7Zm9udC1zaXplOjI2cHg7Y29sb3I6dmFyKC0t"
    "b2spO2Rpc3BsYXk6YmxvY2s7bWFyZ2luLWJvdHRvbTo0cHh9CnByZXtiYWNrZ3JvdW5kOiMwMzA1MGI7Ym9yZGVyOjFweCBzb2xp"
    "ZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjEycHg7Zm9udDoxMnB4IHZhcigtLW1vbm8pO2NvbG9yOiNj"
    "ZmU2ZDk7b3ZlcmZsb3cteDphdXRvO3doaXRlLXNwYWNlOnByZS13cmFwO3dvcmQtYnJlYWs6YnJlYWstYWxsO21hcmdpbi10b3A6"
    "OHB4fQouYnRue2Rpc3BsYXk6aW5saW5lLWZsZXg7Z2FwOjhweDttYXJnaW4tdG9wOjEycHg7cGFkZGluZzoxMnB4IDE4cHg7Ym9y"
    "ZGVyLXJhZGl1czoxMHB4O2ZvbnQ6NjAwIDEzcHggdmFyKC0tbW9ubyk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7YmFja2dyb3VuZDp2"
    "YXIoLS1waW5rKTtjb2xvcjojMDUwNzBmO2JvcmRlcjowO2N1cnNvcjpwb2ludGVyfQouYnRuLmdob3N0e2JhY2tncm91bmQ6dHJh"
    "bnNwYXJlbnQ7Y29sb3I6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KX0KLnN0ZXBze2NvdW50ZXIt"
    "cmVzZXQ6c30KLnN0cHtkaXNwbGF5OmZsZXg7Z2FwOjE0cHg7cGFkZGluZzoxMnB4IDA7Ym9yZGVyLWJvdHRvbToxcHggc29saWQg"
    "cmdiYSgyNTUsMjU1LDI1NSwuMDYpfQouc3RwIC5ue2ZsZXg6bm9uZTt3aWR0aDozNHB4O2hlaWdodDozNHB4O2JvcmRlci1yYWRp"
    "dXM6NTAlO2JhY2tncm91bmQ6Y29uaWMtZ3JhZGllbnQodmFyKC0tcGluayksdmFyKC0tZ29sZCksdmFyKC0tb2spLHZhcigtLXBp"
    "bmspKTtjb2xvcjojMDUwNzBmO2Rpc3BsYXk6ZmxleDthbGlnbi1pdGVtczpjZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtm"
    "b250OjcwMCAxNHB4IHZhcigtLW1vbm8pfQouc3RwIGg0e2ZvbnQtc2l6ZToxNS41cHh9LnN0cCBwe2ZvbnQtc2l6ZToxMy41cHg7"
    "Y29sb3I6I2I2YzBkNn0KdGFibGV7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2U7bWFyZ2luLXRvcDoxMHB4O2Zv"
    "bnQtc2l6ZToxNHB4fQp0ZCx0aHt0ZXh0LWFsaWduOmxlZnQ7cGFkZGluZzo4cHggNnB4O2JvcmRlci1ib3R0b206MXB4IHNvbGlk"
    "IHJnYmEoMjU1LDI1NSwyNTUsLjA4KX0KdGh7Zm9udDo1MDAgMTAuNXB4IHZhcigtLW1vbm8pO2xldHRlci1zcGFjaW5nOi4xZW07"
    "Y29sb3I6dmFyKC0tbXV0ZSl9CnRkIGJ7Y29sb3I6dmFyKC0tb2spfQoubm90ZXtmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS1t"
    "dXRlKTttYXJnaW4tdG9wOjEwcHh9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0"
    "b3AiPjxkaXYgY2xhc3M9ImJyYW5kIj5tb25vcDxiPiBzdHVkaW88L2I+IMK3IGJ5IHNlYmJpLnBybzwvZGl2PjxuYXY+PGEgaHJl"
    "Zj0iLyI+SG9tZTwvYT48YSBocmVmPSIvdG9vbHMiPlRvb2xzPC9hPjxhIGhyZWY9Ii9zdGFydCI+U3RhcnQ8L2E+PC9uYXY+PC9k"
    "aXY+Cgo8ZGl2IGNsYXNzPSJoZXJvIj48ZGl2IGNsYXNzPSJraWNrIj5NT05PUE9MSVNFIFlPVVIgQ09OVEVOVDwvZGl2Pgo8aDE+"
    "WW91ciB2aWRlby4gWW91ciBsb2NrLiBZb3VyIG1vbmV5LjwvaDE+CjxwPkdpdmUgYXdheSB0aGUgZmlyc3QgaGFsZi4gTG9jayB0"
    "aGUgcmVzdCBiZWhpbmQgYSB0YXAuIFZpZXdlcnMgcGF5IHBlbm5pZXMsIHlvdSBrZWVwIG1vc3Qgb2YgaXQsIGFuZCBldmVyeSBw"
    "YWlkIHZpZXcgaXMgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluIHNvIHlvdXIgbnVtYmVycyBjYW4gYmUgcHJvdmVkLCBub3QganVz"
    "dCBjbGFpbWVkLjwvcD48L2Rpdj4KCjxkaXYgY2xhc3M9InBsYXllciIgaWQ9InBsYXllciI+CiA8Y2FudmFzIGlkPSJjdiIgd2lk"
    "dGg9IjEyODAiIGhlaWdodD0iNzIwIj48L2NhbnZhcz4KIDxidXR0b24gY2xhc3M9InBidG4iIGlkPSJwYiI+4pa2PC9idXR0b24+"
    "PGRpdiBjbGFzcz0icHRpbWUiIGlkPSJwdCI+MDowMCAvIDA6Mzg8L2Rpdj4KIDxkaXYgY2xhc3M9InBiYXIiPjxpIGlkPSJwZiI+"
    "PC9pPjwvZGl2PgogPGRpdiBjbGFzcz0ibG9jayIgaWQ9ImxvY2siPgogIDxkaXYgY2xhc3M9ImljIj7wn5SSPC9kaXY+CiAgPGgz"
    "IGlkPSJsb2NrSCI+MTBwIHRvIHdhdGNoIHRoZSByZXN0PC9oMz4KICA8cCBpZD0ibG9ja1AiPllvdSd2ZSBoYWQgdGhlIGZyZWUg"
    "aGFsZi4gVW5sb2NrIHRoZSBmdWxsIHZpZGVvIGZvciAxMHAsIHN0cmFpZ2h0IGZyb20geW91ciBiYWxhbmNlLCBvbmUgdGFwLjwv"
    "cD4KICA8YnV0dG9uIGNsYXNzPSJwYXkiIGlkPSJwYXlCdG4iPlVubG9jayBmb3IgMTBwPC9idXR0b24+CiAgPGRpdiBjbGFzcz0i"
    "bWluaSI+RGVtbyBvbmx5IOKAlCBubyBwYXltZW50IGlzIHRha2VuPC9kaXY+CiAgPGRpdiBjbGFzcz0icmVjZWlwdCIgaWQ9InJj"
    "cHQiPjwvZGl2PgogPC9kaXY+CjwvZGl2Pgo8ZGl2IGNsYXNzPSJub3RlIiBzdHlsZT0idGV4dC1hbGlnbjpjZW50ZXIiPlRhcCBw"
    "bGF5LiBUaGUgbG9jayBkcm9wcyBpbiBhdCB0aGUgaGFsZndheSBtYXJrLCBleGFjdGx5IGFzIHlvdXIgdmlld2VycyB3b3VsZCBz"
    "ZWUgaXQuPC9kaXY+Cgo8c2VjdGlvbiBpZD0iaG93Ij4KIDxoMj5Ib3cgY3JlYXRvcnMgbWFrZSBtb25leTwvaDI+CiA8ZGl2IGNs"
    "YXNzPSJzdGVwcyI+CiAgPGRpdiBjbGFzcz0ic3RwIj48ZGl2IGNsYXNzPSJuIj4xPC9kaXY+PGRpdj48aDQ+VXBsb2FkIG9yIGxp"
    "bmsgeW91ciB2aWRlbzwvaDQ+PHA+QW55dGhpbmcgeW91IG93bi4gWW91IGNob29zZSB3aGVyZSB0aGUgZnJlZSBwYXJ0IGVuZHM6"
    "IDMwIHNlY29uZHMsIGhhbGYsIG9yIHRoZSBmaXJzdCBjaGFwdGVyLjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzdHAi"
    "PjxkaXYgY2xhc3M9Im4iPjI8L2Rpdj48ZGl2PjxoND5TZXQgeW91ciBwcmljZTwvaDQ+PHA+RnJvbSA1cCB0byDCozUgYSB2aWV3"
    "LiBUZW4gcGVuY2UgaXMgdGhlIHN3ZWV0IHNwb3Q6IHNtYWxsIGVub3VnaCB0aGF0IG5vYm9keSB0aGlua3MgdHdpY2UsIGJpZyBl"
    "bm91Z2ggdG8gYWRkIHVwLjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJzdHAiPjxkaXYgY2xhc3M9Im4iPjM8L2Rpdj48"
    "ZGl2PjxoND5TaGFyZSBpdCBhbnl3aGVyZTwvaDQ+PHA+T25lIGxpbmssIG9uZSBlbWJlZC4gUG9zdCBpdCBvbiB5b3VyIG93biBm"
    "ZWVkcywgeW91ciBzaXRlLCBhbnl3aGVyZS4gVGhlIGxvY2sgdHJhdmVscyB3aXRoIGl0LjwvcD48L2Rpdj48L2Rpdj4KICA8ZGl2"
    "IGNsYXNzPSJzdHAiPjxkaXYgY2xhc3M9Im4iPjQ8L2Rpdj48ZGl2PjxoND5HZXQgcGFpZCwgYW5kIGdldCBwcm9vZjwvaDQ+PHA+"
    "WW91ciBzaGFyZSBsYW5kcyBpbiB5b3VyIGJhbGFuY2UuIEV2ZXJ5IHBhaWQgdmlldyBpcyBzZWFsZWQgb24gdGhlIGNoYWluIHdp"
    "dGggYSBibG9jayBudW1iZXIsIHNvIHlvdXIgdmlldyBjb3VudCBpcyBldmlkZW5jZSwgbm90IGEgY2xhaW0uPC9wPjwvZGl2Pjwv"
    "ZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJwcmljZSI+CiA8aDI+V2hhdCBpdCBjb3N0czwvaDI+CiA8cCBj"
    "bGFzcz0ibGVhZCI+U2ltcGxlIGFuZCB0aGUgc2FtZSBmb3IgZXZlcnlvbmUuPC9wPgogPGRpdiBjbGFzcz0iZ3JpZCB0d28iPgog"
    "IDxkaXYgY2xhc3M9ImNhcmQiPjxoMz41MHAgcGVyIHZpZGVvLCBwZXIgbW9udGg8L2gzPjxwPlRoYXQncyB0aGUga2VlcC1pdC1s"
    "b2NrZWQgZmVlLiBTdG9wIHBheWluZyBhbmQgdGhlIGxvY2sgbGlmdHM7IHRoZSB2aWRlbyBzdGF5cyB5b3VycyBhbmQgdGhlIG1v"
    "bmV5IHlvdSd2ZSBtYWRlIHN0YXlzIHlvdXJzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+WW91IGtlZXAgN3Ag"
    "b2YgZXZlcnkgMTBwPC9oMz48cD5UaHJlZSBwZW5jZSBvZiBlYWNoIHVubG9jayBjb3ZlcnMgdGhlIGxvY2ssIHRoZSBwYXltZW50"
    "IGFuZCB0aGUgc2VhbGVkIHJlY2VpcHQuIE9uIGEgMTBwIHZpZXcgeW91IHRha2UgNzAlLjwvcD48L2Rpdj4KIDwvZGl2PgogPHRh"
    "YmxlPjx0cj48dGg+WW91ciBwcmljZTwvdGg+PHRoPllvdSBrZWVwPC90aD48dGg+c2ViYmkucHJvPC90aD48dGg+MSwwMDAgdmll"
    "d3M8L3RoPjwvdHI+CiA8dHI+PHRkPjVwPC90ZD48dGQ+PGI+My41cDwvYj48L3RkPjx0ZD4xLjVwPC90ZD48dGQ+PGI+wqMzNTwv"
    "Yj48L3RkPjwvdHI+CiA8dHI+PHRkPjEwcDwvdGQ+PHRkPjxiPjdwPC9iPjwvdGQ+PHRkPjNwPC90ZD48dGQ+PGI+wqM3MDwvYj48"
    "L3RkPjwvdHI+CiA8dHI+PHRkPjI1cDwvdGQ+PHRkPjxiPjE3LjVwPC9iPjwvdGQ+PHRkPjcuNXA8L3RkPjx0ZD48Yj7CozE3NTwv"
    "Yj48L3RkPjwvdHI+CiA8dHI+PHRkPjUwcDwvdGQ+PHRkPjxiPjM1cDwvYj48L3RkPjx0ZD4xNXA8L3RkPjx0ZD48Yj7CozM1MDwv"
    "Yj48L3RkPjwvdHI+PC90YWJsZT4KIDxwIGNsYXNzPSJub3RlIj5WaWV3ZXJzIHRvcCB1cCBhIHNtYWxsIGJhbGFuY2Ugb25jZSBh"
    "bmQgc3BlbmQgaXQgYSB0YXAgYXQgYSB0aW1lIGFjcm9zcyBldmVyeSBsb2NrZWQgdmlkZW8sIHNvIGEgY2FyZCBpcyBjaGFyZ2Vk"
    "IG9uY2UgcmF0aGVyIHRoYW4gb24gZXZlcnkgdmlldy48L3A+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjYWxjIj4KIDxoMj5X"
    "b3JrIG91dCB5b3VyIG1vbnRoPC9oMj4KIDxkaXYgY2xhc3M9ImdyaWQgdHdvIj4KICA8ZGl2IGNsYXNzPSJjYXJkIGNhbGMiPgog"
    "ICA8bGFiZWw+UHJpY2UgcGVyIHZpZXcgKHBlbmNlKTwvbGFiZWw+PGlucHV0IGlkPSJjUHJpY2UiIGlucHV0bW9kZT0iZGVjaW1h"
    "bCIgdmFsdWU9IjEwIj4KICAgPGxhYmVsPlZpZGVvcyB5b3UnbGwgbG9jazwvbGFiZWw+PGlucHV0IGlkPSJjVmlkcyIgaW5wdXRt"
    "b2RlPSJudW1lcmljIiB2YWx1ZT0iNCI+CiAgIDxsYWJlbD5QYWlkIHZpZXdzIHBlciB2aWRlbywgcGVyIG1vbnRoPC9sYWJlbD48"
    "aW5wdXQgaWQ9ImNWaWV3cyIgaW5wdXRtb2RlPSJudW1lcmljIiB2YWx1ZT0iNTAwIj4KICAgPGRpdiBjbGFzcz0ib3V0Ij48c3Bh"
    "biBjbGFzcz0iYmlnIiBpZD0iY091dCI+wqMwPC9zcGFuPnlvdXJzIGFmdGVyIHRoZSBtb250aGx5IGZlZTxkaXYgaWQ9ImNEZXRh"
    "aWwiIHN0eWxlPSJjb2xvcjojOGE5M2FkO21hcmdpbi10b3A6NnB4Ij48L2Rpdj48L2Rpdj4KICA8L2Rpdj4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj48aDM+V2h5IHBlb3BsZSBwYXk8L2gzPjxwPk5vYm9keSBwYXlzIMKjNSBmb3IgYSB2aWRlbyB0aGV5IGhhdmVuJ3Qg"
    "c2Vlbi4gQWxtb3N0IGV2ZXJ5Ym9keSB0YXBzIDEwcCBvbmNlIHRoZXkncmUgaG9va2VkIGhhbGZ3YXkgdGhyb3VnaC4gVGhlIGZy"
    "ZWUgaGFsZiBkb2VzIHRoZSBzZWxsaW5nOyB0aGUgbG9jayBkb2VzIHRoZSBlYXJuaW5nLjwvcD4KICA8cCBzdHlsZT0ibWFyZ2lu"
    "LXRvcDoxMHB4Ij5BbmQgYmVjYXVzZSBldmVyeSB1bmxvY2sgaXMgc2VhbGVkLCB5b3UgY2FuIHNob3cgYSBzcG9uc29yIGEgdmll"
    "dyBjb3VudCB0aGV5IGNhbiB2ZXJpZnkgdGhlbXNlbHZlcy4gTm8gcGxhdGZvcm0gb24gZWFydGggZ2l2ZXMgeW91IHRoYXQuPC9w"
    "PjwvZGl2PgogPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJjZW50cmUiPgogPGgyPllvdXIgY29udHJvbCBjZW50cmU8"
    "L2gyPgogPGRpdiBjbGFzcz0iZ3JpZCB0aHJlZSI+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPkxvY2sgYnVpbGRlcjwvaDM+PHA+"
    "UGljayB0aGUgY3V0LW9mZiBwb2ludCwgdGhlIHByaWNlIGFuZCB0aGUgcG9zdGVyIGZyYW1lLiBQcmV2aWV3IGV4YWN0bHkgd2hh"
    "dCBhIHZpZXdlciBzZWVzLjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+U2hhcmUgcGFjazwvaDM+PHA+T25lIGxp"
    "bmssIG9uZSBlbWJlZCBzbmlwcGV0LCBhbmQgYSByZWFkeS1tYWRlIHRodW1ibmFpbCB3aXRoIHRoZSBwcmljZSBiYWRnZSBidXJu"
    "ZWQgb24uPC9wPjwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPjxoMz5TZWFsZWQgcmVjZWlwdHM8L2gzPjxwPkV2ZXJ5IHBhaWQg"
    "dmlldyB3aXRoIGl0cyBibG9jayBudW1iZXIsIGV4cG9ydGFibGUgZm9yIGEgc3BvbnNvciwgYW4gYWNjb3VudGFudCBvciBhIGNv"
    "dXJ0LjwvcD48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj48aDM+RWFybmluZ3M8L2gzPjxwPkJhbGFuY2UsIHBheW91dHMgYW5k"
    "IHRoZSBmZWUsIHBlciB2aWRlbyBhbmQgcGVyIG1vbnRoLCBubyBndWVzc2luZy48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2Fy"
    "ZCI+PGgzPkNsaXAgY3V0dGVyPC9oMz48cD5DaG9vc2UgdGhlIGZyZWUgdGVhc2VyOiBmaXJzdCAzMCBzZWNvbmRzLCBmaXJzdCBo"
    "YWxmLCBvciBhIG1vbWVudCB5b3UgcGljay48L3A+PC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+PGgzPlByb29mIGJhZGdlPC9o"
    "Mz48cD5QdXQgeW91ciB2ZXJpZmllZCB2aWV3IGNvdW50IG9uIHlvdXIgb3duIHNpdGUsIGxpdmUsIHNvIHNwb25zb3JzIGNhbiBj"
    "aGVjayBpdCB3aXRob3V0IGFza2luZyB5b3UuPC9wPjwvZGl2PgogPC9kaXY+CiA8cHJlPiZsdDshLS0geW91ciBzaGFyZSBzbmlw"
    "cGV0IGxvb2tzIGxpa2UgdGhpcyAtLSZndDsKJmx0O2lmcmFtZSBzcmM9Imh0dHBzOi8vc2ViYmkucHJvL3YvWU9VUl9WSURFT19J"
    "RCIgd2lkdGg9IjEwMCUiIGhlaWdodD0iNDAwIiBhbGxvd2Z1bGxzY3JlZW4mZ3Q7Jmx0Oy9pZnJhbWUmZ3Q7PC9wcmU+CiA8YSBj"
    "bGFzcz0iYnRuIiBocmVmPSJtYWlsdG86anVzdHJpZ2h0ZGVjb3JhdG9yc0BnbWFpbC5jb20/c3ViamVjdD1Nb25vcCUyMFN0dWRp"
    "byUyMC0lMjBlYXJseSUyMGNyZWF0b3IiPkdldCBvbiB0aGUgZmlyc3QgY3JlYXRvciBsaXN0IOKGkjwvYT4KIDxhIGNsYXNzPSJi"
    "dG4gZ2hvc3QiIGhyZWY9Ii9jaW5lbWEiPlNlZSBpdCBpbiB0aGUgY2luZW1hPC9hPgogPHAgY2xhc3M9Im5vdGUiPk1vbm9wIFN0"
    "dWRpbyBpcyBvcGVuaW5nIHRvIGEgZmlyc3QgZ3JvdXAgb2YgY3JlYXRvcnMuIFRoZSBwbGF5ZXIsIHRoZSBsb2NrIGFuZCB0aGUg"
    "c2VhbGVkIHJlY2VpcHRzIGFyZSBidWlsdDsgc2lnbiB1cCBhYm92ZSBhbmQgeW91J2xsIGJlIGluIHRoZSBmaXJzdCByb3VuZC48"
    "L3A+Cjwvc2VjdGlvbj4KPC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewp2YXIgY3Y9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQo"
    "ImN2IiksZz1jdi5nZXRDb250ZXh0KCIyZCIpLFc9MTI4MCxIPTcyMDsKdmFyIERVUj0zOCwgRlJFRT0wLjUsIHQ9MCwgcGxheWlu"
    "Zz1mYWxzZSwgbGFzdD0wLCB1bmxvY2tlZD1mYWxzZTsKdmFyIEdPTEQ9IiNjOWE4NGMiLE9LPSIjN2ZlM2IwIixCTFVFPSIjOGZk"
    "MGZmIixQSU5LPSIjZDU5YmZmIjsKZnVuY3Rpb24gYmcoKXt2YXIgZ3JkPWcuY3JlYXRlTGluZWFyR3JhZGllbnQoMCwwLFcsSCk7"
    "Z3JkLmFkZENvbG9yU3RvcCgwLCIjMGIxMDI2Iik7Z3JkLmFkZENvbG9yU3RvcCgxLCIjMDMwNTBiIik7Zy5maWxsU3R5bGU9Z3Jk"
    "O2cuZmlsbFJlY3QoMCwwLFcsSCk7CiBnLmdsb2JhbEFscGhhPS4yNTtnLnN0cm9rZVN0eWxlPSIjMWQyYTUyIjtnLmxpbmVXaWR0"
    "aD0xO2Zvcih2YXIgeD0wO3g8Vzt4Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbyh4LDApO2cubGluZVRvKHgsSCk7Zy5zdHJv"
    "a2UoKX0KIGZvcih2YXIgeT0wO3k8SDt5Kz02NCl7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygwLHkpO2cubGluZVRvKFcseSk7Zy5z"
    "dHJva2UoKX1nLmdsb2JhbEFscGhhPTF9CmZ1bmN0aW9uIHR4dChzLHksc2l6ZSxjb2wsYWxpZ24pe2cuZmlsbFN0eWxlPWNvbHx8"
    "IiNmZmYiO2cudGV4dEFsaWduPWFsaWdufHwiY2VudGVyIjtnLmZvbnQ9IjYwMCAiK3NpemUrInB4ICdJQk0gUGxleCBTYW5zJyxz"
    "eXN0ZW0tdWksc2Fucy1zZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gc2VyaWYocyx5LHNpemUsY29sKXtnLmZp"
    "bGxTdHlsZT1jb2x8fCIjZmZmIjtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3NpemUrInB4IE5ld3NyZWFkZXIs"
    "R2VvcmdpYSxzZXJpZiI7Zy5maWxsVGV4dChzLFcvMix5KX0KZnVuY3Rpb24gbW9ubyhzLHksc2l6ZSxjb2wpe2cuZmlsbFN0eWxl"
    "PWNvbHx8R09MRDtnLnRleHRBbGlnbj0iY2VudGVyIjtnLmZvbnQ9IjUwMCAiK3NpemUrInB4IHVpLW1vbm9zcGFjZSxNZW5sbyxt"
    "b25vc3BhY2UiO2cuZmlsbFRleHQocyxXLzIseSl9CmZ1bmN0aW9uIGZhZGUoYSl7cmV0dXJuIE1hdGgubWF4KDAsTWF0aC5taW4o"
    "MSxhKSl9CmZ1bmN0aW9uIGJsb2NrKHgseSx3LGgsY29sLGdsb3cpe2cuc2F2ZSgpO2cuc2hhZG93Q29sb3I9Y29sO2cuc2hhZG93"
    "Qmx1cj1nbG93fHwxODtnLmZpbGxTdHlsZT0iIzBkMTQyNCI7Zy5zdHJva2VTdHlsZT1jb2w7Zy5saW5lV2lkdGg9MzsKIGcuYmVn"
    "aW5QYXRoKCk7Zy5yb3VuZFJlY3QoeCx5LHcsaCwxMCk7Zy5maWxsKCk7Zy5zdHJva2UoKTtnLnJlc3RvcmUoKX0KZnVuY3Rpb24g"
    "cm9ib3QoeCx5LHMsY29sKXtnLnNhdmUoKTtnLnRyYW5zbGF0ZSh4LHkpO2cuc2NhbGUocyxzKTtnLmZpbGxTdHlsZT0iI2Q4ZGRl"
    "NiI7CiBnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0yNiwtNzAsNTIsNDAsOCk7Zy5maWxsKCk7Zy5maWxsU3R5bGU9Y29sO2cu"
    "ZmlsbFJlY3QoLTE4LC01OCwzNiw5KTsKIGcuZmlsbFN0eWxlPSIjYzNjOWQ0IjtnLmJlZ2luUGF0aCgpO2cucm91bmRSZWN0KC0z"
    "MiwtMjYsNjQsNTQsMTApO2cuZmlsbCgpOwogZy5maWxsU3R5bGU9IiNhZWI2YzQiO2cuZmlsbFJlY3QoLTI0LDMwLDE4LDQyKTtn"
    "LmZpbGxSZWN0KDYsMzAsMTgsNDIpO2cucmVzdG9yZSgpfQpmdW5jdGlvbiBzY2VuZShpLHApewogaWYoaT09PTApe3ZhciBhPWZh"
    "ZGUocCozKTtnLmdsb2JhbEFscGhhPWE7c2VyaWYoInNlYmJpLnBybyIsSC8yLTQwLDk2LCIjZmZmIik7bW9ubygiUFJPT0YgRk9S"
    "IFRIRSBNQUNISU5FIEFHRSIsSC8yKzMwLDI2LEdPTEQpO2cuZ2xvYmFsQWxwaGE9MTsKICBnLnN0cm9rZVN0eWxlPUdPTEQ7Zy5n"
    "bG9iYWxBbHBoYT1hKi42O2cubGluZVdpZHRoPTI7Zy5iZWdpblBhdGgoKTtnLmFyYyhXLzIsSC8yLTEwLDE4MCtwKjQwLDAsNi4y"
    "ODMpO2cuc3Ryb2tlKCk7Zy5nbG9iYWxBbHBoYT0xfQogZWxzZSBpZihpPT09MSl7dHh0KCJZb3VyIEFJIGp1c3QgZGlkIHNvbWV0"
    "aGluZy4iLDEyMCw1NCk7bW9ubygiV0hPIFNBSUQgSVQgQ09VTEQ/IiwxNzYsMjQsUElOSyk7CiAgcm9ib3QoVy8yLTI2MCxILzIr"
    "MTQwLDEuNixPSyk7CiAgZy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdpZHRoPTQ7Zy5zZXRMaW5lRGFzaChbMTIsMTBdKTtnLmJl"
    "Z2luUGF0aCgpO2cubW92ZVRvKFcvMi0yMDAsSC8yKzQwKTtnLmxpbmVUbyhXLzIrMTYwK3AqODAsSC8yKzQwKTtnLnN0cm9rZSgp"
    "O2cuc2V0TGluZURhc2goW10pOwogIGJsb2NrKFcvMisyMDAsSC8yLTQwLDIyMCwxNjAsR09MRCk7dHh0KCLCozQsMDAwIixILzIr"
    "NTAsNDQsR09MRCk7bW9ubygiUEFZTUVOVCIsSC8yKzkwLDIwLCIjOGE5M2FkIil9CiBlbHNlIGlmKGk9PT0yKXt0eHQoInNlYmJp"
    "LnBybyBjaGVja3MgYXQgdGhlIG1vbWVudCBpdCBoYXBwZW5zLiIsMTEwLDQ2KTsKICB2YXIgbj1NYXRoLmZsb29yKHAqNCkrMSxs"
    "YWJlbHM9WyJIdW1hbiBhdXRob3JpdHk/IiwiU3RpbGwgdmFsaWQgbm93PyIsIlJpZ2h0IGFtb3VudD8iLCJVc2VkIGJlZm9yZT8i"
    "XTsKICBmb3IodmFyIGs9MDtrPDQ7aysrKXt2YXIgb249azxuO2cuZ2xvYmFsQWxwaGE9b24/MTouMjU7YmxvY2soMTgwK2sqMjQw"
    "LDMwMCwyMDAsMTIwLG9uP09LOiIjMzM0Iixvbj8yMjo2KTsKICAgZy5maWxsU3R5bGU9b24/T0s6IiM2NjciO2cudGV4dEFsaWdu"
    "PSJjZW50ZXIiO2cuZm9udD0iNjAwIDIycHggJ0lCTSBQbGV4IFNhbnMnLHNhbnMtc2VyaWYiO2cuZmlsbFRleHQobGFiZWxzW2td"
    "LDI4MCtrKjI0MCwzNTIpOwogICBnLmZvbnQ9IjYwMCAzNHB4IHVpLW1vbm9zcGFjZSxtb25vc3BhY2UiO2cuZmlsbFRleHQob24/"
    "IuKckyI6IsK3IiwyODArayoyNDAsMzk4KTtnLmdsb2JhbEFscGhhPTF9CiAgbW9ubygiTUlMTElTRUNPTkRTIMK3IE5PIFNFQ09O"
    "RCBBSSBNT0RFTCIsNTIwLDI0LEdPTEQpfQogZWxzZSBpZihpPT09Myl7dHh0KCJUaGVuIGl0J3Mgc2VhbGVkLiBGb3JldmVyLiIs"
    "MTEwLDUwKTsKICBmb3IodmFyIGI9MDtiPDY7YisrKXt2YXIgdmlzPXAqNj5iO2lmKCF2aXMpY29udGludWU7YmxvY2soMTIwK2Iq"
    "MTgwLDI4MCwxNTAsMTQwLEdPTEQsMTYpOwogICBtb25vKCIjIisoMjUxMCtiKSwzNTAsMjAsR09MRCk7Zy5zYXZlKCk7Zy50cmFu"
    "c2xhdGUoMTIwK2IqMTgwKzc1LDMzMCk7Zy5maWxsU3R5bGU9T0s7Zy5mb250PSI1MDAgMTVweCB1aS1tb25vc3BhY2UsbW9ub3Nw"
    "YWNlIjsKICAgZy50ZXh0QWxpZ249ImNlbnRlciI7Zy5maWxsVGV4dCgiYTRmOeKApiIrKGIqNysxMSksMCwwKTtnLnJlc3RvcmUo"
    "KTsKICAgaWYoYil7Zy5zdHJva2VTdHlsZT1HT0xEO2cubGluZVdpZHRoPTM7Zy5iZWdpblBhdGgoKTtnLm1vdmVUbygxMjArYiox"
    "ODAtMzAsMzUwKTtnLmxpbmVUbygxMjArYioxODAsMzUwKTtnLnN0cm9rZSgpfX0KICBtb25vKCJDSEFOR0UgT05FIEFORCBFVkVS"
    "WSBPTkUgQUZURVIgSVQgQlJFQUtTIiw1MjAsMjQsIiM4YTkzYWQiKX0KIGVsc2UgaWYoaT09PTQpe3R4dCgiVGltZXN0YW1wZWQg"
    "aW4gQml0Y29pbi4iLDExMCw1MCk7CiAgZy5zYXZlKCk7Zy50cmFuc2xhdGUoVy8yLDM2MCk7Zy5yb3RhdGUocCoxLjYpO2cuc3Ry"
    "b2tlU3R5bGU9IiNmNzkzMWEiO2cubGluZVdpZHRoPTY7Zy5iZWdpblBhdGgoKTtnLmFyYygwLDAsMTEwLDAsNi4yODMpO2cuc3Ry"
    "b2tlKCk7Zy5yZXN0b3JlKCk7CiAgZy5maWxsU3R5bGU9IiNmNzkzMWEiO2cudGV4dEFsaWduPSJjZW50ZXIiO2cuZm9udD0iNjAw"
    "IDkwcHggJ0lCTSBQbGV4IFNhbnMnLHNhbnMtc2VyaWYiO2cuZmlsbFRleHQoIuKCvyIsVy8yLDM5MCk7CiAgbW9ubygiQSBDTE9D"
    "SyBOT0JPRFkgSU5WT0xWRUQgQ09OVFJPTFMiLDUyMCwyNCwiI2Y3OTMxYSIpfQogZWxzZSBpZihpPT09NSl7dHh0KCJIZWxkIGJ5"
    "IHBlb3BsZSB5b3UgZG9uJ3QgY29udHJvbC4iLDExMCw0OCk7CiAgZm9yKHZhciB3PTA7dzw1O3crKyl7dmFyIGFuZz0tTWF0aC5Q"
    "SS8yKyh3LTIpKjAuNSx4PVcvMitNYXRoLmNvcyhhbmcpKjI2MCx5PTQyMCtNYXRoLnNpbihhbmcpKjEyMDsKICAgZy5zdHJva2VT"
    "dHlsZT1CTFVFO2cuZ2xvYmFsQWxwaGE9LjU7Zy5saW5lV2lkdGg9MjtnLmJlZ2luUGF0aCgpO2cubW92ZVRvKFcvMiwzMDApO2cu"
    "bGluZVRvKHgseSk7Zy5zdHJva2UoKTtnLmdsb2JhbEFscGhhPTE7CiAgIGcuZmlsbFN0eWxlPUJMVUU7Zy5iZWdpblBhdGgoKTtn"
    "LmFyYyh4LHksMjIsMCw2LjI4Myk7Zy5maWxsKCl9CiAgYmxvY2soVy8yLTkwLDI0MCwxODAsMTEwLEdPTEQpO21vbm8oIllPVVIg"
    "Q0hBSU4iLDMwNSwyMixHT0xEKTsKICBtb25vKCJJTkRFUEVOREVOVCBXSVRORVNTRVMiLDYwMCwyNCxCTFVFKX0KIGVsc2V7dHh0"
    "KCJFdmVyeSBkZWNpc2lvbi4gUHJvdmFibGUuIixILzItNjAsNjApO21vbm8oIlNFQkJJLlBSTyIsSC8yKzIwLDQwLEdPTEQpO21v"
    "bm8oIkZSRUUgRk9SIDkwIERBWVMgwrcgNTBwIFBFUiBERVZJQ0UiLEgvMis4MCwyMiwiIzhhOTNhZCIpfQp9CmZ1bmN0aW9uIGRy"
    "YXcoKXtiZygpO3ZhciBwZXI9RFVSLzcsaT1NYXRoLm1pbig2LE1hdGguZmxvb3IodC9wZXIpKSxwPSh0LWkqcGVyKS9wZXI7c2Nl"
    "bmUoaSxwKTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwZiIpLnN0eWxlLndpZHRoPSh0L0RVUioxMDApKyIlIjsKIHZhciBt"
    "PU1hdGguZmxvb3IodC82MCkscz1NYXRoLmZsb29yKHQlNjApO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwdCIpLnRleHRDb250"
    "ZW50PW0rIjoiKyhzPDEwPyIwIjoiIikrcysiIC8gMDozOCJ9CmZ1bmN0aW9uIGxvb3Aobm93KXtpZighcGxheWluZylyZXR1cm47"
    "dmFyIGR0PShub3ctbGFzdCkvMTAwMDtsYXN0PW5vdzt0Kz1kdDsKIGlmKCF1bmxvY2tlZCYmdD49RFVSKkZSRUUpe3Q9RFVSKkZS"
    "RUU7cGxheWluZz1mYWxzZTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGIiKS50ZXh0Q29udGVudD0i4pa2Ijtkb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgibG9jayIpLmNsYXNzTGlzdC5hZGQoIm9uIik7ZHJhdygpO3JldHVybn0KIGlmKHQ+PURVUil7dD1EVVI7"
    "cGxheWluZz1mYWxzZTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicGIiKS50ZXh0Q29udGVudD0i4oa7In0KIGRyYXcoKTtyZXF1"
    "ZXN0QW5pbWF0aW9uRnJhbWUobG9vcCl9CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJwYiIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtp"
    "Zih0Pj1EVVIpe3Q9MH1wbGF5aW5nPSFwbGF5aW5nO3RoaXMudGV4dENvbnRlbnQ9cGxheWluZz8i4p2a4p2aIjoi4pa2IjtsYXN0"
    "PXBlcmZvcm1hbmNlLm5vdygpO2lmKHBsYXlpbmcpcmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3ApfTsKZG9jdW1lbnQuZ2V0RWxl"
    "bWVudEJ5SWQoInBheUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXt1bmxvY2tlZD10cnVlOwogdmFyIGJsaz0yNTAwK01hdGguZmxv"
    "b3IoTWF0aC5yYW5kb20oKSo0MDApOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJjcHQiKS5pbm5lckhUTUw9IuKckyBVbmxv"
    "Y2tlZCDCtyBwYWlkIHZpZXcgc2VhbGVkIGluIGJsb2NrICIrYmxrKyIgwrcgY3JlYXRvciBlYXJucyA3cCI7CiB2YXIgc2VsZj10"
    "aGlzO3NlbGYudGV4dENvbnRlbnQ9IlVubG9ja2VkIOKckyI7c2V0VGltZW91dChmdW5jdGlvbigpe2RvY3VtZW50LmdldEVsZW1l"
    "bnRCeUlkKCJsb2NrIikuY2xhc3NMaXN0LnJlbW92ZSgib24iKTsKICBwbGF5aW5nPXRydWU7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5"
    "SWQoInBiIikudGV4dENvbnRlbnQ9IuKdmuKdmiI7bGFzdD1wZXJmb3JtYW5jZS5ub3coKTtyZXF1ZXN0QW5pbWF0aW9uRnJhbWUo"
    "bG9vcCl9LDEyMDApfTsKZHJhdygpOwpmdW5jdGlvbiBjYWxjKCl7dmFyIHA9cGFyc2VGbG9hdChkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgiY1ByaWNlIikudmFsdWUpfHwwLHY9cGFyc2VJbnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWRzIikudmFsdWUp"
    "fHwwLG49cGFyc2VJbnQoZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoImNWaWV3cyIpLnZhbHVlKXx8MDsKIHZhciBrZWVwPXAqMC43"
    "LGdyb3NzPWtlZXAqdipuLzEwMCxmZWU9MC41KnYsbmV0PWdyb3NzLWZlZTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjT3V0"
    "IikudGV4dENvbnRlbnQ9IsKjIisobmV0PjA/bmV0LnRvRml4ZWQoMik6IjAuMDAiKTsKIGRvY3VtZW50LmdldEVsZW1lbnRCeUlk"
    "KCJjRGV0YWlsIikudGV4dENvbnRlbnQ9dipuKyIgcGFpZCB2aWV3cyDDlyAiK2tlZXAudG9GaXhlZCgxKSsicCA9IMKjIitncm9z"
    "cy50b0ZpeGVkKDIpKyIgIMK3ICBtb250aGx5IGxvY2sgZmVlIMKjIitmZWUudG9GaXhlZCgyKX0KWyJjUHJpY2UiLCJjVmlkcyIs"
    "ImNWaWV3cyJdLmZvckVhY2goZnVuY3Rpb24oaWQpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKS5hZGRFdmVudExpc3RlbmVy"
    "KCJpbnB1dCIsY2FsYyl9KTtjYWxjKCk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/create": (_d(_HTML_B64), "text/html; charset=utf-8"),
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
    if getattr(cls, "_studio_patched", False):
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
    cls._studio_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "studio", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/tokensaver.py`

1670 lines, 64529 bytes

```python
#!/usr/bin/env python3
"""
modules/tokensaver.py  v2.0.0
sebbi.pro - the token saver

Reached at /x/tokensaver/<action>.

WHAT IT IS
----------
A deterministic gate that sits in front of a model and decides, in
arithmetic alone, whether a request is answered from store, sent to the
model, sent to a cheaper one, held for a person, or refused.

It also tells the caller, on every single request, exactly what in that
request is costing money that it does not need to cost.

Every decision seals into the platform chain. The saving is a receipt,
not a claim.

HOW IT IS BUILT
---------------
Three layers, in this order, because a cost gate that depends entirely
on tuned weights is a cost gate nobody can defend in a meeting.

  Layer 1  HARD RULES
           Absolute, arithmetic, untunable. A budget that is spent is
           spent. A request repeating identically eight times is a
           runaway. These do not consult the score at all.

  Layer 2  THE SCORE
           Nine weighted signals summing to exactly 1.00, split into
           the ones that measure what this request will SPEND and the
           ones that measure whether that spend is WASTE.

  Layer 3  FINDINGS
           Named, itemised waste inside the request, each with a token
           figure attached and each marked exact or estimated. This is
           the part that saves the most money, because it changes what
           the caller sends next time.

THREE TIERS OF CERTAINTY, NEVER MIXED
-------------------------------------
  tokens_not_bought          EXACT. Provider-reported counts on a
                             request that was served from store.
                             This is the only number that goes in a
                             savings total.

  worst_case_tokens_avoided  A CEILING, not a saving. When a request
                             is refused, max_tokens tells you the most
                             it could have cost. Reported separately
                             and never added to the exact figure.

  findings tokens            ESTIMATED where marked. Character counts
                             divided by four. Never enters any total.

Nothing on this page is ever expressed as a percentage saved.

WHAT IT DOES NOT DO
-------------------
- It never calls a model to reach a decision. Every signal is
  arithmetic on the request itself.
- It only serves a stored answer for an IDENTICAL request. Matching
  similar prompts needs an embedding, which is a model call, which
  would defeat the entire point.
- It does not judge whether a stored answer is still correct.
- It does not store answers to requests that asked for varied output,
  unless the caller overrides that deliberately.

MODULE CONTRACT
---------------
handle(method, action, data, api_key, ctx) -> (dict, status)
PUBLIC is a set of (METHOD, action) tuples.
ctx exposes conn, lock and seal.
"""

import hashlib
import inspect
import json
import math
import sqlite3
import threading
import time

VERSION = "2.2.0"

PUBLIC = {
    ("GET", "spec"),
    ("GET", "stats"),
    ("GET", "verify"),
}

# ============================================================ layer 1
# Hard rules. Absolute. Not weights, not tunable by score band.

LOOP_WINDOW = 120          # seconds a repeat still counts as a repeat
LOOP_HARD = 8              # identical repeats in the window = runaway
LOOP_HARD_UNATTENDED = 4   # lower bar when no human is watching
BURST_HARD = 120           # requests in 60s from one key = runaway

# ============================================================ layer 2
# Nine signals. Base weights MUST sum to exactly 1.00.
#
# What this request will SPEND ......................... 0.62
W_EXPOSURE = 0.18   # worst case spend against remaining budget
W_SIZE = 0.14       # prompt characters
W_ASK = 0.14        # max_tokens ceiling the caller authorised
W_DEPTH = 0.10      # conversation turns, re-sent on every call
W_TOOLS = 0.06      # tool definitions, re-sent on every call
#
# Whether that spend is WASTE .......................... 0.38
W_LOOP = 0.16       # the same request going round again
W_BURST = 0.09      # requests in the last 60 seconds
W_GRIND = 0.07      # requests in the last hour
W_NOVELTY = 0.06    # first time this shape has been seen

BASE_SUM = (W_EXPOSURE + W_SIZE + W_ASK + W_DEPTH + W_TOOLS
            + W_LOOP + W_BURST + W_GRIND + W_NOVELTY)

# Sits outside the base sum, deliberately.
W_UNATTENDED = 0.10

BAND_CHALLENGE = 0.55
BAND_BLOCK = 0.80

SAT_LOOP = 5
SAT_BURST = 20
SAT_GRIND = 200
SAT_SIZE = 100_000
SAT_ASK = 8_000
SAT_DEPTH = 40
SAT_TOOLS = 24

# A request only earns the cheap model by being genuinely small.
# Suspicion never routes a request to a weaker model.
CHEAP_MAX_CHARS = 4_000
CHEAP_MAX_TURNS = 6
CHEAP_MAX_ASK = 1_000
CHEAP_MAX_SCORE = 0.30

W60 = 60
W1H = 3600

# ============================================================ layer 3
CTX_KEEP_TURNS = 8          # turns beyond this are flagged as carried
CTX_FLAG_TURNS = 12         # only flag once the conversation is this deep
SYSTEM_FLAG_CHARS = 2_000
CHARS_PER_TOKEN = 4.0       # the estimate, used only in findings

DEFAULT_TTL = 30 * 24 * 3600
MAX_STORED_BYTES = 512 * 1024
MAX_PROMPT_CHARS = 2_000_000

KEYED_FIELDS = (
    "model", "messages", "system", "prompt", "input",
    "temperature", "top_p", "top_k",
    "max_tokens", "max_completion_tokens",
    "stop", "stop_sequences",
    "tools", "tool_choice", "response_format", "seed",
)

VOCABULARY = {
    "SERVE": "answered from an identical earlier request; nothing was bought",
    "ALLOW": "send it to the model as asked",
    "DOWNGRADE": "small and simple enough for the cheap model",
    "CHALLENGE": "hold it for a person before spending",
    "BLOCK": "refused; it never reaches the model, so no completion is paid for",
}

LIMITS = [
    "Matching is exact. A reworded prompt is a different request and goes "
    "to the model.",
    "Savings totals use only token counts the provider itself reported. "
    "Nothing in a total is estimated.",
    "A refused request has a worst case cost, not a known cost. It is "
    "reported separately and never added to the savings total.",
    "Token figures inside findings are estimated from character counts and "
    "are marked as estimates. They never enter a total.",
    "A stored answer is returned unchanged. This module does not judge "
    "whether it is still correct.",
    "No model is called to reach any decision here.",
]


# --------------------------------------------------------------- helpers

def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def _sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _fingerprint(req):
    keyed = {k: req[k] for k in KEYED_FIELDS if k in req}
    return _sha(b"SEBBI-TOKENSAVER-v2\n" + _canonical(keyed))


def _content_chars(v):
    if v is None:
        return 0
    if isinstance(v, str):
        return len(v)
    return len(_canonical(v))


def _prompt_chars(req):
    total = 0
    for key in ("prompt", "input", "system"):
        total += _content_chars(req.get(key))
    msgs = req.get("messages")
    if isinstance(msgs, list):
        for m in msgs:
            total += _content_chars(m.get("content") if isinstance(m, dict) else m)
    tools = req.get("tools")
    if tools is not None:
        total += _content_chars(tools)
    return total


def _est_tokens(chars):
    """Estimate only. Marked as such everywhere it appears."""
    return int(chars / CHARS_PER_TOKEN)


def _ask_ceiling(req):
    """The caller's own authorised output ceiling. Exact, not estimated."""
    v = req.get("max_tokens")
    if v is None:
        v = req.get("max_completion_tokens")
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _shape(req):
    n = len(req.get("messages") or [])
    t = len(req.get("tools") or [])
    band = int(math.log10(max(_prompt_chars(req), 1)) * 2)
    return _sha("%s|%d|%d|%d" % (req.get("model") or "", n, t, band))


def _measure(req):
    """Everything the decision needs, taken from a full request."""
    return {
        "fp": _fingerprint(req),
        "shape": _shape(req),
        "chars": _prompt_chars(req),
        "ask": _ask_ceiling(req),
        "depth": len(req.get("messages") or []),
        "tools": len(req.get("tools") or []),
        "deterministic": _deterministic(req),
        "from_digest": False,
    }


def _measure_from_digest(d):
    """
    The same measurements, supplied by a client that kept its content at
    home. The client is measuring its own spend against its own budget,
    so there is nothing to gain by misreporting.
    """
    if not isinstance(d, dict):
        return None, "digest must be an object"
    fp = d.get("fingerprint")
    if not isinstance(fp, str) or len(fp) != 64:
        return None, "digest needs a 64 character fingerprint"
    try:
        int(fp, 16)
    except ValueError:
        return None, "fingerprint must be hexadecimal"

    def _n(key, cap):
        v = d.get(key, 0)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 0
        return max(0, min(v, cap))

    m = {
        "fp": fp,
        "chars": _n("prompt_characters", MAX_PROMPT_CHARS),
        "ask": _n("max_tokens", 10_000_000),
        "depth": _n("conversation_turns", 100_000),
        "tools": _n("tool_definitions", 100_000),
        "deterministic": bool(d.get("deterministic", True)),
        "from_digest": True,
    }
    band = int(math.log10(max(m["chars"], 1)) * 2)
    m["shape"] = _sha("%s|%d|%d|%d" % (d.get("model") or "", m["depth"],
                                       m["tools"], band))
    return m, None


def _log_scale(value, saturation):
    if value <= 0:
        return 0.0
    if value >= saturation:
        return 1.0
    return math.log1p(value) / math.log1p(saturation)


def _linear(value, saturation):
    if value <= 0:
        return 0.0
    return min(1.0, float(value) / float(saturation))


def _deterministic(req):
    t = req.get("temperature")
    if t is None:
        return True
    try:
        return float(t) == 0.0
    except (TypeError, ValueError):
        return False


def _usage(resp):
    if not isinstance(resp, dict):
        return (None, None)
    u = resp.get("usage")
    if not isinstance(u, dict):
        return (None, None)
    i = u.get("input_tokens", u.get("prompt_tokens"))
    o = u.get("output_tokens", u.get("completion_tokens"))
    try:
        return (int(i) if i is not None else None,
                int(o) if o is not None else None)
    except (TypeError, ValueError):
        return (None, None)


def _money(tokens_in, tokens_out, price_in, price_out):
    if price_in is None and price_out is None:
        return None
    m = 0.0
    if price_in:
        m += (tokens_in or 0) / 1_000_000.0 * price_in
    if price_out:
        m += (tokens_out or 0) / 1_000_000.0 * price_out
    return round(m, 4)


# --------------------------------------------------------------- storage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ts_store (
    api_key       TEXT NOT NULL,
    fp            TEXT NOT NULL,
    model         TEXT,
    response      TEXT NOT NULL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    stored_at     REAL NOT NULL,
    expires_at    REAL,
    hits          INTEGER NOT NULL DEFAULT 0,
    last_hit      REAL,
    PRIMARY KEY (api_key, fp)
);

CREATE TABLE IF NOT EXISTS ts_seen (
    api_key  TEXT NOT NULL,
    fp       TEXT NOT NULL,
    ts       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ts_shape (
    api_key  TEXT NOT NULL,
    shape    TEXT NOT NULL,
    first_ts REAL NOT NULL,
    PRIMARY KEY (api_key, shape)
);

CREATE TABLE IF NOT EXISTS ts_decision (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key     TEXT NOT NULL,
    ts          REAL NOT NULL,
    fp          TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    rule        TEXT,
    score       REAL NOT NULL,
    signals     TEXT NOT NULL,
    exact_in    INTEGER,
    exact_out   INTEGER,
    ceiling_in  INTEGER,
    ceiling_out INTEGER,
    audit_hash  TEXT
);

CREATE TABLE IF NOT EXISTS ts_account (
    api_key    TEXT PRIMARY KEY,
    ceiling    INTEGER NOT NULL DEFAULT 0,
    spent      INTEGER NOT NULL DEFAULT 0,
    price_in   REAL,
    price_out  REAL,
    currency   TEXT,
    updated    REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ts_seen_key ON ts_seen(api_key, ts);
CREATE INDEX IF NOT EXISTS ts_seen_fp ON ts_seen(api_key, fp, ts);
CREATE INDEX IF NOT EXISTS ts_dec_key ON ts_decision(api_key, id);
CREATE INDEX IF NOT EXISTS ts_dec_hash ON ts_decision(audit_hash);
CREATE INDEX IF NOT EXISTS ts_store_exp ON ts_store(expires_at);
"""

_ready = {}


def _init(ctx):
    # Keyed by id, but the connection itself is kept as the value so the
    # id cannot be recycled while we still believe in it.
    k = id(ctx.conn)
    if _ready.get(k) is ctx.conn:
        return
    with ctx.lock:
        ctx.conn.executescript(_SCHEMA)
        ctx.conn.commit()
    _ready[k] = ctx.conn


def _account(ctx, api_key):
    row = ctx.conn.execute(
        "SELECT ceiling, spent, price_in, price_out, currency "
        "FROM ts_account WHERE api_key=?", (api_key,)
    ).fetchone()
    if not row:
        return {"ceiling": 0, "spent": 0, "price_in": None,
                "price_out": None, "currency": None}
    return {"ceiling": row[0], "spent": row[1], "price_in": row[2],
            "price_out": row[3], "currency": row[4]}


def _prune(ctx, api_key, now):
    ctx.conn.execute("DELETE FROM ts_seen WHERE api_key=? AND ts < ?",
                     (api_key, now - W1H))


# ================================================================ layer 3

def _findings(req, loop_n, has_stored, acct):
    """
    Named waste inside this request. Every item carries a token figure
    and says whether that figure is exact or estimated. This never
    feeds a total.
    """
    out = []
    msgs = req.get("messages") or []
    depth = len(msgs)
    tools = req.get("tools") or []
    ask = _ask_ceiling(req)

    # The biggest one in agent systems: the same request going round
    # and nobody recording the answer.
    if loop_n >= 2 and not has_stored:
        out.append({
            "code": "repeating_without_recording",
            "severity": "high",
            "detail": "This exact request has gone out %d times in the last "
                      "%d seconds and no answer has been recorded. Post the "
                      "response back to record and every repeat after that "
                      "costs nothing."
                      % (loop_n, LOOP_WINDOW),
            "tokens": None,
            "certainty": "not counted",
        })

    if not _deterministic(req):
        out.append({
            "code": "varied_output_blocks_reuse",
            "severity": "medium",
            "detail": "temperature is above zero, so this answer cannot be "
                      "safely reused. If this request does not genuinely need "
                      "varied output, setting temperature to zero makes every "
                      "repeat free.",
            "tokens": None,
            "certainty": "not counted",
        })

    if depth > CTX_FLAG_TURNS:
        carried = msgs[:-CTX_KEEP_TURNS] if CTX_KEEP_TURNS < depth else []
        chars = sum(_content_chars(m.get("content") if isinstance(m, dict)
                                   else m) for m in carried)
        out.append({
            "code": "carrying_old_turns",
            "severity": "high" if chars > 20_000 else "medium",
            "detail": "%d turns are being re-sent on every call. The oldest "
                      "%d of them account for roughly the tokens below, paid "
                      "again each time this conversation continues."
                      % (depth, len(carried)),
            "tokens": _est_tokens(chars),
            "certainty": "estimated from character count",
        })

    if tools:
        used = False
        for m in msgs:
            if not isinstance(m, dict):
                continue
            c = m.get("content")
            blob = c if isinstance(c, str) else _canonical(c).decode("utf-8", "ignore")
            if "tool_use" in blob or "tool_call" in blob:
                used = True
                break
        if not used:
            chars = _content_chars(tools)
            out.append({
                "code": "unused_tool_definitions",
                "severity": "high" if chars > 8_000 else "medium",
                "detail": "%d tool definitions are attached and nothing in "
                          "this conversation has called one. They are sent in "
                          "full on every request."
                          % len(tools),
                "tokens": _est_tokens(chars),
                "certainty": "estimated from character count",
            })

    sys_chars = _content_chars(req.get("system"))
    if sys_chars > SYSTEM_FLAG_CHARS and depth > 4:
        out.append({
            "code": "large_system_prompt_resent",
            "severity": "low",
            "detail": "The system prompt is re-sent on every call in this "
                      "conversation. If your provider offers prompt caching, "
                      "this is the block to cache.",
            "tokens": _est_tokens(sys_chars),
            "certainty": "estimated from character count",
        })

    if ask:
        out.append({
            "code": "output_ceiling_authorised",
            "severity": "low",
            "detail": "max_tokens is set to %d, so this single call is "
                      "authorised to buy up to that many output tokens." % ask,
            "tokens": ask,
            "certainty": "exact ceiling set by the caller",
        })

    seen = {}
    for m in msgs:
        if not isinstance(m, dict):
            continue
        k = _sha(_canonical(m.get("content")))
        seen[k] = seen.get(k, 0) + 1
    dupes = sum(n - 1 for n in seen.values() if n > 1)
    if dupes >= 2:
        out.append({
            "code": "duplicate_turns_in_context",
            "severity": "medium",
            "detail": "%d turns inside this conversation are byte-identical "
                      "to an earlier turn. They are being paid for twice."
                      % dupes,
            "tokens": None,
            "certainty": "not counted",
        })

    if acct["ceiling"] and acct["spent"] >= acct["ceiling"] * 0.8:
        out.append({
            "code": "budget_nearly_gone",
            "severity": "high",
            "detail": "This key has used %d of its %d token ceiling."
                      % (acct["spent"], acct["ceiling"]),
            "tokens": None,
            "certainty": "exact, from provider-reported usage",
        })

    return out


# ================================================================ layers 1+2

def _decide(ctx, api_key, m, now, unattended, count_it):
    """
    Takes a measurement bundle from _measure or _measure_from_digest, so
    the same decision runs whether the caller sent the request or kept it
    at home and sent only its shape.

    rule is set only when a hard rule fired, in which case the score is
    still computed and reported but did not decide anything.
    """
    fp = m["fp"]
    shape = m["shape"]
    acct = _account(ctx, api_key)

    loop_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND fp=? AND ts > ?",
        (api_key, fp, now - LOOP_WINDOW)).fetchone()[0]
    burst_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND ts > ?",
        (api_key, now - W60)).fetchone()[0]
    grind_n = ctx.conn.execute(
        "SELECT COUNT(*) FROM ts_seen WHERE api_key=? AND ts > ?",
        (api_key, now - W1H)).fetchone()[0]
    seen_shape = ctx.conn.execute(
        "SELECT 1 FROM ts_shape WHERE api_key=? AND shape=?",
        (api_key, shape)).fetchone()
    has_stored = ctx.conn.execute(
        "SELECT 1 FROM ts_store WHERE api_key=? AND fp=?",
        (api_key, fp)).fetchone() is not None

    chars = m["chars"]
    ask = m["ask"]
    depth = m["depth"]
    tools = m["tools"]

    # Worst case this one call could cost: an exact ceiling on output,
    # an estimate on input. Kept apart accordingly.
    ceiling_out = ask
    est_in = _est_tokens(chars)
    remaining = max(0, acct["ceiling"] - acct["spent"]) if acct["ceiling"] else 0
    if remaining:
        exposure = _linear(est_in + ceiling_out, remaining)
    else:
        exposure = 0.0

    s = {
        "exposure": round(exposure, 4),
        "size": round(_log_scale(chars, SAT_SIZE), 4),
        "ask": round(_log_scale(ask, SAT_ASK), 4),
        "depth": round(_linear(depth, SAT_DEPTH), 4),
        "tools": round(_linear(tools, SAT_TOOLS), 4),
        "loop": round(_linear(loop_n, SAT_LOOP), 4),
        "burst": round(_linear(burst_n, SAT_BURST), 4),
        "grind": round(_linear(grind_n, SAT_GRIND), 4),
        "novelty": 0.0 if seen_shape else 1.0,
    }

    score = (W_EXPOSURE * s["exposure"] + W_SIZE * s["size"]
             + W_ASK * s["ask"] + W_DEPTH * s["depth"]
             + W_TOOLS * s["tools"] + W_LOOP * s["loop"]
             + W_BURST * s["burst"] + W_GRIND * s["grind"]
             + W_NOVELTY * s["novelty"])

    s["unattended"] = bool(unattended)
    if unattended:
        score += W_UNATTENDED
    score = round(min(1.0, score), 4)

    measured = {
        "prompt_characters": chars,
        "estimated_input_tokens": est_in,
        "estimated_input_tokens_note": "estimated from characters, never "
                                       "counted in a savings total",
        "authorised_output_tokens": ceiling_out,
        "conversation_turns": depth,
        "tool_definitions": tools,
        "same_request_in_last_%ds" % LOOP_WINDOW: loop_n,
        "requests_in_last_60s": burst_n,
        "requests_in_last_hour": grind_n,
        "budget_ceiling_tokens": acct["ceiling"],
        "budget_spent_tokens": acct["spent"],
    }

    # ---- layer 1: hard rules, in order, no appeal to the score --------
    rule = None
    verdict = None

    if acct["ceiling"] and acct["spent"] >= acct["ceiling"]:
        rule, verdict = "budget_exhausted", "BLOCK"
    elif acct["ceiling"] and (est_in + ceiling_out) > remaining:
        # An overdraft. Catching this after the fact is too late: the
        # money is already gone. A person may raise the ceiling, so an
        # attended call is held rather than refused.
        rule = "exceeds_remaining_budget"
        verdict = "BLOCK" if unattended else "CHALLENGE"
    elif loop_n >= LOOP_HARD:
        rule, verdict = "runaway_loop", "BLOCK"
    elif unattended and loop_n >= LOOP_HARD_UNATTENDED:
        rule, verdict = "runaway_loop_unattended", "BLOCK"
    elif burst_n >= BURST_HARD:
        rule, verdict = "runaway_burst", "BLOCK"

    # ---- layer 2: the score -------------------------------------------
    if verdict is None:
        if score >= BAND_BLOCK:
            verdict = "BLOCK"
        elif score >= BAND_CHALLENGE:
            verdict = "CHALLENGE"
        elif (score < CHEAP_MAX_SCORE and chars <= CHEAP_MAX_CHARS
              and depth <= CHEAP_MAX_TURNS and ask <= CHEAP_MAX_ASK
              and tools == 0):
            verdict = "DOWNGRADE"
        else:
            verdict = "ALLOW"

    if count_it:
        ctx.conn.execute("INSERT INTO ts_seen (api_key, fp, ts) VALUES (?,?,?)",
                         (api_key, fp, now))
        ctx.conn.execute(
            "INSERT OR IGNORE INTO ts_shape (api_key, shape, first_ts) "
            "VALUES (?,?,?)", (api_key, shape, now))
        _prune(ctx, api_key, now)

    measured["measured_from"] = ("a digest supplied by the client; the "
                                "content stayed on their side"
                                if m.get("from_digest") else
                                "the request body")
    return (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
            est_in, ceiling_out, acct)


def _record_decision(ctx, api_key, fp, verdict, rule, score, signals,
                     ex_in, ex_out, ce_in, ce_out, seal_hash, now):
    """Writes the row and returns its id, so the receipt can be stamped on
    afterwards once the lock has been released."""
    cur = ctx.conn.execute(
        "INSERT INTO ts_decision (api_key, ts, fp, verdict, rule, score, "
        "signals, exact_in, exact_out, ceiling_in, ceiling_out, audit_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (api_key, now, fp, verdict, rule, score,
         json.dumps(signals, sort_keys=True), ex_in, ex_out, ce_in, ce_out,
         seal_hash))
    return cur.lastrowid


def _seal_and_stamp(ctx, event, detail, api_key, decision_id):
    """
    Seal with the lock released, then write the receipt back onto the row
    in a second short lock. Splitting it this way is what keeps the
    platform's non-reentrant lock from deadlocking the request.
    """
    seal = ctx.seal(event, detail, api_key)
    h = seal.get("hash") if isinstance(seal, dict) else None
    if h and decision_id:
        try:
            with ctx.lock:
                ctx.conn.execute(
                    "UPDATE ts_decision SET audit_hash=? WHERE id=?",
                    (h, decision_id))
                ctx.conn.commit()
        except Exception:                        # noqa: BLE001
            pass
    return seal


# --------------------------------------------------------------- actions

def _a_spec():
    return {
        "module": "tokensaver",
        "version": VERSION,
        "what_it_is": "A deterministic gate in front of a model. It decides "
                      "whether a request is answered from store, sent to the "
                      "model, sent to a cheaper model, held for a person, or "
                      "refused. It also names the waste inside every request "
                      "it sees.",
        "model_calls_made_to_reach_a_decision": 0,
        "layers": {
            "1_hard_rules": {
                "why": "A cost gate that depends only on tuned weights is a "
                       "cost gate nobody can defend. These are absolute.",
                "rules": {
                    "budget_exhausted": "spend has reached the key's ceiling",
                    "exceeds_remaining_budget":
                        "this one call could cost more than the budget left. "
                        "Output uses the exact ceiling you set; input is "
                        "estimated from characters, so this rule is "
                        "deliberately cautious. Held for a person when a "
                        "human is declared, refused when one is not.",
                    "runaway_loop": "the same request %d times in %d seconds"
                                    % (LOOP_HARD, LOOP_WINDOW),
                    "runaway_loop_unattended": "the same request %d times in "
                                               "%d seconds with no human "
                                               "declared"
                                               % (LOOP_HARD_UNATTENDED,
                                                  LOOP_WINDOW),
                    "runaway_burst": "%d requests from one key in 60 seconds"
                                     % BURST_HARD,
                },
            },
            "2_the_score": {
                "spend_signals": {
                    "exposure": {"weight": W_EXPOSURE,
                                 "measures": "worst case cost of this call "
                                             "against the budget left"},
                    "size": {"weight": W_SIZE, "saturates_at": SAT_SIZE,
                             "measures": "prompt characters, log scaled"},
                    "ask": {"weight": W_ASK, "saturates_at": SAT_ASK,
                            "measures": "the max_tokens ceiling the caller set"},
                    "depth": {"weight": W_DEPTH, "saturates_at": SAT_DEPTH,
                              "measures": "turns re-sent on every call"},
                    "tools": {"weight": W_TOOLS, "saturates_at": SAT_TOOLS,
                              "measures": "tool definitions re-sent on every call"},
                },
                "waste_signals": {
                    "loop": {"weight": W_LOOP, "saturates_at": SAT_LOOP},
                    "burst": {"weight": W_BURST, "saturates_at": SAT_BURST},
                    "grind": {"weight": W_GRIND, "saturates_at": SAT_GRIND},
                    "novelty": {"weight": W_NOVELTY},
                },
                "spend_weight_total": round(W_EXPOSURE + W_SIZE + W_ASK
                                            + W_DEPTH + W_TOOLS, 4),
                "waste_weight_total": round(W_LOOP + W_BURST + W_GRIND
                                            + W_NOVELTY, 4),
                "base_weights_sum_to": round(BASE_SUM, 4),
                "outside_the_base_sum": {"unattended": W_UNATTENDED},
                "bands": {"CHALLENGE": ">= %.2f" % BAND_CHALLENGE,
                          "BLOCK": ">= %.2f" % BAND_BLOCK},
                "downgrade_is_earned_not_suspected": {
                    "max_score": CHEAP_MAX_SCORE,
                    "max_prompt_characters": CHEAP_MAX_CHARS,
                    "max_turns": CHEAP_MAX_TURNS,
                    "max_output_tokens": CHEAP_MAX_ASK,
                    "tools_allowed": 0,
                    "why": "a suspicious request is never sent to a weaker "
                           "model. Only a genuinely small one is.",
                },
            },
            "3_findings": {
                "why": "The verdict saves money on this call. The findings "
                       "change what the caller sends next time, which saves "
                       "far more.",
                "codes": ["repeating_without_recording",
                          "varied_output_blocks_reuse",
                          "carrying_old_turns",
                          "unused_tool_definitions",
                          "large_system_prompt_resent",
                          "output_ceiling_authorised",
                          "duplicate_turns_in_context",
                          "budget_nearly_gone"],
            },
        },
        "verdict_vocabulary": VOCABULARY,
        "certainty_tiers": {
            "tokens_not_bought": "exact, provider reported, the only figure "
                                 "that enters a savings total",
            "worst_case_tokens_avoided": "a ceiling on what a refused request "
                                         "could have cost, reported separately",
            "findings_tokens": "estimated from characters where marked, never "
                               "entering any total",
        },
        "two_ways_to_call_it": {
            "request": "send the provider request body. This platform sees "
                       "your prompt.",
            "digest": "send only a fingerprint and counts. Your prompts and "
                      "answers never leave your building, the decision is "
                      "identical, and the receipt is the same. The downloaded "
                      "client uses this path by default.",
        },
        "honest_limits": LIMITS,
        "routes": {
            "public": ["spec", "stats", "verify"],
            "keyed": ["estimate", "gate", "record", "ledger", "budget",
                      "prices", "forget"],
        },
    }


def _bundle(data):
    """
    A caller may send the whole request, or only a digest of it. The
    digest path exists so a customer's prompts and answers never leave
    their own building. Returns (measurements, request_or_None, error, code).
    """
    req = data.get("request")
    if isinstance(req, dict):
        if _prompt_chars(req) > MAX_PROMPT_CHARS:
            return None, None, {"error": "request_too_large"}, 413
        return _measure(req), req, None, None

    dig = data.get("digest")
    if dig is not None:
        m, err = _measure_from_digest(dig)
        if err:
            return None, None, {"error": "bad_digest", "detail": err}, 400
        return m, None, None, None

    return None, None, {
        "error": "request_or_digest_required",
        "detail": "send the provider request body under 'request', or a "
                  "content-free digest under 'digest' with fingerprint, "
                  "prompt_characters, max_tokens, conversation_turns, "
                  "tool_definitions and deterministic",
    }, 400


def _digest_findings(m, loop_n, has_stored, acct):
    """
    What can honestly be said when the content stayed at home. Anything
    needing the actual messages is left to the client, which has them.
    """
    out = []
    if loop_n >= 2 and not has_stored:
        out.append({
            "code": "repeating_without_recording",
            "severity": "high",
            "detail": "This exact request has gone out %d times in the last "
                      "%d seconds and no answer has been recorded. Post the "
                      "response back to record and every repeat after that "
                      "costs nothing." % (loop_n, LOOP_WINDOW),
            "tokens": None,
            "certainty": "not counted",
        })
    if not m["deterministic"]:
        out.append({
            "code": "varied_output_blocks_reuse",
            "severity": "medium",
            "detail": "temperature is above zero, so this answer cannot be "
                      "safely reused.",
            "tokens": None,
            "certainty": "not counted",
        })
    if m["depth"] > CTX_FLAG_TURNS:
        out.append({
            "code": "carrying_old_turns",
            "severity": "medium",
            "detail": "%d turns are being re-sent on every call. Your client "
                      "holds the content and can size this exactly."
                      % m["depth"],
            "tokens": None,
            "certainty": "not counted here; the client can measure it",
        })
    if m["ask"]:
        out.append({
            "code": "output_ceiling_authorised",
            "severity": "low",
            "detail": "max_tokens is set to %d, so this call is authorised "
                      "to buy up to that many output tokens." % m["ask"],
            "tokens": m["ask"],
            "certainty": "exact ceiling set by the caller",
        })
    if acct["ceiling"] and acct["spent"] >= acct["ceiling"] * 0.8:
        out.append({
            "code": "budget_nearly_gone",
            "severity": "high",
            "detail": "This key has used %d of its %d token ceiling."
                      % (acct["spent"], acct["ceiling"]),
            "tokens": None,
            "certainty": "exact, from provider-reported usage",
        })
    return out


def _a_estimate(ctx, api_key, data, now):
    """Cost a request and name its waste. Changes nothing, seals nothing."""
    m, req, err, code = _bundle(data)
    if err:
        return err, code

    with ctx.lock:
        (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
         est_in, ceil_out, acct) = _decide(
            ctx, api_key, m, now, bool(data.get("unattended")), False)
        findings = (_findings(req, loop_n, has_stored, acct) if req
                    else _digest_findings(m, loop_n, has_stored, acct))
        stored = has_stored

    money = _money(est_in, ceil_out, acct["price_in"], acct["price_out"])
    out = {
        "would_be": verdict,
        "rule": rule,
        "score": score,
        "signals": s,
        "measured": measured,
        "findings": findings,
        "fingerprint": fp,
        "stored_answer_available": stored,
        "worst_case_cost": {
            "estimated_input_tokens": est_in,
            "authorised_output_tokens": ceil_out,
            "certainty": "input estimated from characters; output is the "
                         "exact ceiling you set",
        },
        "note": "estimate changes nothing, counts towards no velocity window "
                "and seals nothing. Use gate for the real decision.",
    }
    if money is not None:
        out["worst_case_cost"]["money_at_your_prices"] = money
        out["worst_case_cost"]["currency"] = acct["currency"]
    return out, 200


def _a_gate(ctx, api_key, data, now):
    m, req, err, code = _bundle(data)
    if err:
        return err, code

    unattended = bool(data.get("unattended"))
    fp = m["fp"]

    # ---- everything that touches the database, under the lock ----------
    with ctx.lock:
        row = ctx.conn.execute(
            "SELECT response, model, input_tokens, output_tokens, hits, "
            "expires_at FROM ts_store WHERE api_key=? AND fp=?",
            (api_key, fp)).fetchone()

        expired = False
        if row and row[5] is not None and row[5] < now:
            ctx.conn.execute("DELETE FROM ts_store WHERE api_key=? AND fp=?",
                             (api_key, fp))
            expired = True
            row = None

        acct = _account(ctx, api_key)
        budget_gone = bool(acct["ceiling"]) and acct["spent"] >= acct["ceiling"]

        client_held = False
        if row:
            try:
                client_held = (json.loads(row[0]).get("held_by") == "client")
            except (ValueError, AttributeError):
                client_held = False

        served = bool(row) and not budget_gone
        if served:
            ctx.conn.execute(
                "UPDATE ts_store SET hits=hits+1, last_hit=? "
                "WHERE api_key=? AND fp=?", (now, api_key, fp))
            did = _record_decision(
                ctx, api_key, fp, "SERVE",
                "stored_by_client" if client_held else "stored_answer",
                0.0, {"repeat": 1.0}, row[2], row[3], None, None, None, now)
        else:
            (verdict, rule, score, s, measured, fp, shape, loop_n, has_stored,
             est_in, ceil_out, acct) = _decide(ctx, api_key, m, now,
                                               unattended, True)
            findings = (_findings(req, loop_n, has_stored, acct) if req
                        else _digest_findings(m, loop_n, has_stored, acct))
            ce_in = est_in if verdict == "BLOCK" else None
            ce_out = ceil_out if verdict == "BLOCK" else None
            did = _record_decision(ctx, api_key, fp, verdict, rule, score, s,
                                   None, None, ce_in, ce_out, None, now)
        ctx.conn.commit()

    # ---- sealing happens with the lock RELEASED -------------------------
    # The platform's seal takes the same lock, and it is not reentrant.
    # Calling it from inside the block above deadlocks the request.
    if expired:
        ctx.seal("tokensaver_expired",
                 {"module": "tokensaver", "fingerprint": fp}, api_key)

    if served:
        detail = {
            "module": "tokensaver", "verdict": "SERVE", "fingerprint": fp,
            "model": row[1],
            "tokens_not_bought": {"input": row[2], "output": row[3]},
            "usage_reported_by_provider": (row[2] is not None
                                           or row[3] is not None),
            "hit_number": row[4] + 1,
        }
        if client_held:
            detail["content_held_by"] = "client"
        seal = _seal_and_stamp(ctx, "tokensaver_serve", detail, api_key, did)

        known = (row[2] is not None or row[3] is not None)
        out = {
            "verdict": "SERVE",
            "meaning": VOCABULARY["SERVE"],
            "call_the_model": False,
            "fingerprint": fp,
            "tokens_not_bought": {
                "input": row[2], "output": row[3],
                "total": ((row[2] or 0) + (row[3] or 0)) if known else None,
                "certainty": "exact, as reported by the provider on the "
                             "original call" if known else
                             "the provider reported no usage on the original "
                             "call, so this saving is real but its size is "
                             "unknown",
            },
            "hit_number": row[4] + 1,
            "receipt": seal,
        }
        if client_held:
            out["content_held_by"] = "client"
            out["serve_from_your_own_store"] = True
        else:
            out["response"] = json.loads(row[0])
        money = _money(row[2], row[3], acct["price_in"], acct["price_out"])
        if money is not None:
            out["money_not_spent_at_your_prices"] = money
            out["currency"] = acct["currency"]
        return out, 200

    detail = {
        "module": "tokensaver", "verdict": verdict, "rule": rule,
        "score": score, "fingerprint": fp, "signals": s,
        "measured": measured, "findings": [f["code"] for f in findings],
    }
    seal = _seal_and_stamp(ctx, "tokensaver_decision", detail, api_key, did)

    out = {
        "verdict": verdict,
        "meaning": VOCABULARY[verdict],
        "decided_by": ("hard rule: " + rule) if rule else "score",
        "rule": rule,
        "score": score,
        "signals": s,
        "measured": measured,
        "findings": findings,
        "fingerprint": fp,
        "call_the_model": verdict in ("ALLOW", "DOWNGRADE"),
        "use_cheap_model": verdict == "DOWNGRADE",
        "receipt": seal,
    }
    if verdict == "BLOCK":
        money = _money(est_in, ceil_out, acct["price_in"], acct["price_out"])
        out["worst_case_avoided"] = {
            "estimated_input_tokens": est_in,
            "authorised_output_tokens": ceil_out,
            "certainty": "a ceiling, not a saving. Nobody knows what this "
                         "call would actually have cost, so it is reported "
                         "separately and never added to tokens not bought.",
        }
        if money is not None:
            out["worst_case_avoided"]["money_at_your_prices"] = money
    if verdict in ("ALLOW", "DOWNGRADE"):
        out["next"] = ("call the model, then POST the response to "
                       "/x/tokensaver/record so the next identical request "
                       "costs nothing")
    return out, 200


def _a_record(ctx, api_key, data, now):
    req = data.get("request")
    resp = data.get("response")
    dig = data.get("digest")

    # Content-free path: the client stored the answer at home and is only
    # reporting what it cost, so the budget and the totals stay true.
    if not isinstance(req, dict) and isinstance(dig, dict):
        m, err = _measure_from_digest(dig)
        if err:
            return {"error": "bad_digest", "detail": err}, 400
        u = data.get("usage") or {}
        try:
            t_in = (int(u["input_tokens"])
                    if u.get("input_tokens") is not None else None)
            t_out = (int(u["output_tokens"])
                     if u.get("output_tokens") is not None else None)
        except (TypeError, ValueError):
            return {"error": "usage_must_be_whole_numbers"}, 400
        with ctx.lock:
            if t_in is not None or t_out is not None:
                _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
            ctx.conn.execute(
                "INSERT OR REPLACE INTO ts_store (api_key, fp, model, "
                "response, input_tokens, output_tokens, stored_at, "
                "expires_at, hits, last_hit) VALUES (?,?,?,?,?,?,?,?,0,NULL)",
                (api_key, m["fp"], dig.get("model"),
                 json.dumps({"held_by": "client",
                             "note": "the answer is stored on the customer's "
                                     "own machine and never came here"}),
                 t_in, t_out, now, now + DEFAULT_TTL))
            ctx.conn.commit()
        seal = ctx.seal("tokensaver_store", {
            "module": "tokensaver", "fingerprint": m["fp"],
            "model": dig.get("model"), "content_held_by": "client",
            "usage_reported_by_provider": (t_in is not None
                                           or t_out is not None),
            "input_tokens": t_in, "output_tokens": t_out}, api_key)
        return {"stored": True, "fingerprint": m["fp"],
                "content_held_by": "client", "input_tokens": t_in,
                "output_tokens": t_out, "receipt": seal,
                "note": "the cost is on the record here; the answer itself "
                        "stayed on your machine"}, 200

    if not isinstance(req, dict) or not isinstance(resp, dict):
        return {"error": "request_and_response_required",
                "detail": "send request and response, or a digest with usage"}, 400

    body = json.dumps(resp)
    if len(body.encode("utf-8")) > MAX_STORED_BYTES:
        return {"error": "response_too_large",
                "limit_bytes": MAX_STORED_BYTES}, 413

    fp = _fingerprint(req)
    t_in, t_out = _usage(resp)

    if not _deterministic(req) and not data.get("store_varied"):
        with ctx.lock:
            if t_in is not None or t_out is not None:
                _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
            ctx.conn.commit()
        ctx.seal("tokensaver_refused_to_store", {
            "module": "tokensaver", "fingerprint": fp,
            "reason": "temperature above zero; serving a stored answer "
                      "would change how the system behaves"}, api_key)
        return {
            "stored": False,
            "spend_recorded": (t_in is not None or t_out is not None),
            "reason": "temperature is above zero. Serving a stored answer to "
                      "a request that asked for varied output would change "
                      "how your system behaves. Send store_varied true to "
                      "override deliberately.",
        }, 200

    ttl = data.get("ttl_seconds", DEFAULT_TTL)
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = DEFAULT_TTL
    expires = now + ttl if ttl > 0 else None

    with ctx.lock:
        ctx.conn.execute(
            "INSERT OR REPLACE INTO ts_store (api_key, fp, model, response, "
            "input_tokens, output_tokens, stored_at, expires_at, hits, "
            "last_hit) VALUES (?,?,?,?,?,?,?,?,0,NULL)",
            (api_key, fp, req.get("model"), body, t_in, t_out, now, expires))
        if t_in is not None or t_out is not None:
            _spend(ctx, api_key, (t_in or 0) + (t_out or 0), now)
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_store", {
        "module": "tokensaver", "fingerprint": fp, "model": req.get("model"),
        "usage_reported_by_provider": (t_in is not None or t_out is not None),
        "input_tokens": t_in, "output_tokens": t_out}, api_key)

    return {
        "stored": True,
        "fingerprint": fp,
        "usage_reported_by_provider": (t_in is not None or t_out is not None),
        "input_tokens": t_in,
        "output_tokens": t_out,
        "receipt": seal,
        "note": "the next identical request will be served from store and "
                "will buy nothing"
                if (t_in is not None or t_out is not None) else
                "stored, but the provider reported no usage, so future "
                "savings on this request will be real without a known size",
    }, 200


def _spend(ctx, api_key, tokens, now):
    ctx.conn.execute(
        "INSERT INTO ts_account (api_key, ceiling, spent, updated) "
        "VALUES (?,0,?,?) ON CONFLICT(api_key) DO UPDATE SET "
        "spent = spent + ?, updated = ?",
        (api_key, tokens, now, tokens, now))


def _totals(ctx, api_key=None):
    where = "WHERE api_key=?" if api_key else ""
    args = (api_key,) if api_key else ()

    rows = ctx.conn.execute(
        "SELECT hits, input_tokens, output_tokens FROM ts_store " + where,
        args).fetchall()
    exact_in = exact_out = unknown = 0
    for h, i, o in rows:
        if i is None and o is None:
            unknown += h
            continue
        exact_in += (i or 0) * h
        exact_out += (o or 0) * h

    counts = {}
    for v, c in ctx.conn.execute(
            "SELECT verdict, COUNT(*) FROM ts_decision " + where
            + " GROUP BY verdict", args).fetchall():
        counts[v] = c

    crow = ctx.conn.execute(
        "SELECT COALESCE(SUM(ceiling_in),0), COALESCE(SUM(ceiling_out),0) "
        "FROM ts_decision " + (where + " AND " if where else "WHERE ")
        + "verdict='BLOCK'", args).fetchone()

    rules = {}
    for r, c in ctx.conn.execute(
            "SELECT rule, COUNT(*) FROM ts_decision "
            + (where + " AND " if where else "WHERE ")
            + "rule IS NOT NULL GROUP BY rule", args).fetchall():
        rules[r] = c

    total = sum(counts.values())
    served = counts.get("SERVE", 0)

    return {
        "decisions": total,
        "verdicts": counts,
        "hard_rules_fired": rules,
        "serve_rate_percent": round(100.0 * served / total, 2) if total else 0.0,
        "tokens_not_bought": {
            "input": exact_in,
            "output": exact_out,
            "total": exact_in + exact_out,
            "certainty": "exact. Provider-reported counts on requests served "
                         "from store.",
        },
        "worst_case_tokens_avoided": {
            "estimated_input": crow[0],
            "authorised_output": crow[1],
            "certainty": "a ceiling on refused requests, not a saving. Never "
                         "added to tokens not bought.",
        },
        "serves_with_no_usage_reported": unknown,
        "stored_answers": len(rows),
    }


def _a_stats(ctx):
    with ctx.lock:
        t = _totals(ctx)
    t["version"] = VERSION
    t["model_calls_made_to_reach_a_decision"] = 0
    t["note"] = ("No figure here is a percentage saved. Exact savings and "
                 "worst case ceilings are reported apart and never summed.")
    return t, 200


def _a_ledger(ctx, api_key, data, now):
    try:
        limit = min(200, max(1, int(data.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    with ctx.lock:
        rows = ctx.conn.execute(
            "SELECT ts, fp, verdict, rule, score, exact_in, exact_out, "
            "ceiling_in, ceiling_out, audit_hash FROM ts_decision "
            "WHERE api_key=? ORDER BY id DESC LIMIT ?",
            (api_key, limit)).fetchall()
        totals = _totals(ctx, api_key)
        acct = _account(ctx, api_key)

    out = {
        "totals": totals,
        "budget": {
            "ceiling_tokens": acct["ceiling"],
            "spent_tokens": acct["spent"],
            "remaining_tokens": max(0, acct["ceiling"] - acct["spent"])
                                if acct["ceiling"] else None,
            "note": "no ceiling set; set one with budget"
                    if not acct["ceiling"] else None,
        },
        "recent": [{
            "ts": r[0], "fingerprint": r[1], "verdict": r[2], "rule": r[3],
            "score": r[4],
            "tokens_not_bought": ((r[5] or 0) + (r[6] or 0))
                                 if r[2] == "SERVE" else 0,
            "worst_case_avoided": ((r[7] or 0) + (r[8] or 0))
                                  if r[2] == "BLOCK" else 0,
            "receipt": r[9],
        } for r in rows],
    }
    m = _money(totals["tokens_not_bought"]["input"],
               totals["tokens_not_bought"]["output"],
               acct["price_in"], acct["price_out"])
    if m is not None:
        out["money_not_spent_at_your_prices"] = m
        out["currency"] = acct["currency"]
        out["money_note"] = ("calculated only from provider-reported counts "
                             "on requests served from store, at the prices "
                             "you supplied")
    return out, 200


def _a_budget(ctx, api_key, data, now):
    if "ceiling_tokens" not in data:
        return {"error": "ceiling_tokens_required",
                "detail": "the number of tokens this key may spend before "
                          "every request is refused"}, 400
    try:
        ceiling = int(data["ceiling_tokens"])
    except (TypeError, ValueError):
        return {"error": "ceiling_tokens_must_be_a_whole_number"}, 400
    if ceiling < 0:
        return {"error": "ceiling_tokens_must_not_be_negative"}, 400

    reset = bool(data.get("reset_spent"))
    with ctx.lock:
        ctx.conn.execute(
            "INSERT INTO ts_account (api_key, ceiling, spent, updated) "
            "VALUES (?,?,0,?) ON CONFLICT(api_key) DO UPDATE SET "
            "ceiling=?, updated=?", (api_key, ceiling, now, ceiling, now))
        if reset:
            ctx.conn.execute("UPDATE ts_account SET spent=0 WHERE api_key=?",
                             (api_key,))
        acct = _account(ctx, api_key)
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_budget", {
        "module": "tokensaver", "ceiling_tokens": ceiling,
        "spent_reset": reset}, api_key)

    return {"ceiling_tokens": acct["ceiling"], "spent_tokens": acct["spent"],
            "receipt": seal,
            "note": "when spent reaches the ceiling, every request is refused "
                    "before it reaches the model"}, 200


def _a_prices(ctx, api_key, data, now):
    """Prices come from the customer's own contract. Never assumed."""
    pi = data.get("price_per_million_input")
    po = data.get("price_per_million_output")
    if pi is None and po is None:
        return {"error": "prices_required",
                "detail": "send price_per_million_input and/or "
                          "price_per_million_output from your own provider "
                          "contract. Nothing is assumed on your behalf."}, 400
    try:
        pi = float(pi) if pi is not None else None
        po = float(po) if po is not None else None
    except (TypeError, ValueError):
        return {"error": "prices_must_be_numbers"}, 400
    if (pi is not None and pi < 0) or (po is not None and po < 0):
        return {"error": "prices_must_not_be_negative"}, 400

    cur = (data.get("currency") or "").strip()[:8] or None
    with ctx.lock:
        ctx.conn.execute(
            "INSERT INTO ts_account (api_key, ceiling, spent, price_in, "
            "price_out, currency, updated) VALUES (?,0,0,?,?,?,?) "
            "ON CONFLICT(api_key) DO UPDATE SET price_in=?, price_out=?, "
            "currency=?, updated=?",
            (api_key, pi, po, cur, now, pi, po, cur, now))
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_prices", {
        "module": "tokensaver", "price_per_million_input": pi,
        "price_per_million_output": po, "currency": cur}, api_key)

    return {"price_per_million_input": pi, "price_per_million_output": po,
            "currency": cur, "receipt": seal,
            "note": "money figures now appear alongside token figures. They "
                    "are your prices applied to provider-reported counts, "
                    "never an assumption about what you pay."}, 200


def _a_forget(ctx, api_key, data, now):
    fp = data.get("fingerprint")
    req = data.get("request")
    if not fp and isinstance(req, dict):
        fp = _fingerprint(req)
    if not fp:
        return {"error": "fingerprint_or_request_required"}, 400

    with ctx.lock:
        cur = ctx.conn.execute(
            "DELETE FROM ts_store WHERE api_key=? AND fp=?", (api_key, fp))
        removed = cur.rowcount
        ctx.conn.commit()

    seal = ctx.seal("tokensaver_forget", {
        "module": "tokensaver", "fingerprint": fp, "removed": removed},
        api_key)

    return {"removed": removed, "fingerprint": fp, "receipt": seal,
            "note": "the stored answer is gone. Decisions already sealed "
                    "stay sealed."}, 200


def _a_verify(ctx, data):
    h = data.get("receipt") or data.get("hash")
    if not h:
        return {"error": "receipt_required",
                "detail": "pass ?receipt=<chain hash from a decision>"}, 400
    with ctx.lock:
        row = ctx.conn.execute(
            "SELECT ts, verdict, rule, score, exact_in, exact_out, "
            "ceiling_in, ceiling_out, fp FROM ts_decision WHERE audit_hash=?",
            (h,)).fetchone()
    if not row:
        return {"found": False, "receipt": h,
                "note": "no decision on this platform carries that receipt"}, 404
    return {
        "found": True,
        "receipt": h,
        "ts": row[0],
        "verdict": row[1],
        "meaning": VOCABULARY.get(row[1], row[1]),
        "decided_by": ("hard rule: " + row[2]) if row[2] else "score",
        "score": row[3],
        "tokens_not_bought": ((row[4] or 0) + (row[5] or 0))
                             if row[1] == "SERVE" else 0,
        "worst_case_avoided": ((row[6] or 0) + (row[7] or 0))
                              if row[1] == "BLOCK" else 0,
        "fingerprint": row[8],
        "what_this_proves": "that this decision was sealed into the chain "
                            "with these values at this position.",
        "what_this_does_not_prove": "that a stored answer is still correct, "
                                    "or what a refused request would actually "
                                    "have cost.",
    }, 200


# ---------------------------------------------------------------- handler
# ---------------------------------------------------------------- the ctx

def _fallback_conn():
    global _FALLBACK_CONN
    with _FALLBACK_LOCK:
        if _FALLBACK_CONN is None:
            _FALLBACK_CONN = sqlite3.connect("tokensaver.db",
                                             check_same_thread=False)
            _FALLBACK_CONN.execute("PRAGMA journal_mode=WAL")
        return _FALLBACK_CONN


class _Bridge:
    """
    A router may hand a module a context object, or a plain dict. Rather
    than assume which, find what is actually needed: something that can
    run SQL, something that can be held, and something that can seal.

    Anything missing is reported honestly in the response instead of
    being faked.
    """

    def __init__(self, raw):
        self.raw = raw
        self.conn = self._find(
            lambda v: hasattr(v, "execute") and hasattr(v, "commit"),
            ("conn", "db", "_conn", "_db", "database", "sql", "sqlite"))
        self.lock = self._find(
            lambda v: hasattr(v, "acquire") and hasattr(v, "release"),
            ("lock", "db_lock", "_db_lock", "_lock", "mutex"))
        # A sqlite3 Connection is itself callable, so "anything callable"
        # is not a safe test for a seal function - it would quietly pick the
        # database. Require an actual function or method.
        self._seal = self._find(
            lambda v: (inspect.isroutine(v)
                       and v is not self.conn and v is not self.lock),
            ("seal", "seal_fn", "seal_block", "add_block", "chain_seal",
             "append_block"))
        self.notes = []

        if self.conn is None:
            # Last resort so the module still answers rather than 500s.
            self.conn = _fallback_conn()
            self.notes.append("no database was found in the router context, so "
                              "this module opened its own file")
        if self.lock is None:
            self.lock = _FALLBACK_LOCK
            self.notes.append("no lock was found in the router context, so "
                              "this module used its own")
        if self._seal is None:
            self.notes.append("no seal function was found in the router "
                              "context, so decisions are recorded but not "
                              "sealed into the platform chain")

    def _find(self, test, names):
        raw = self.raw
        if isinstance(raw, dict):
            for n in names:                      # preferred names first
                if n in raw and raw[n] is not None:
                    try:
                        if test(raw[n]):
                            return raw[n]
                    except Exception:            # noqa: BLE001
                        pass
            for v in raw.values():               # then anything that fits
                try:
                    if v is not None and test(v):
                        return v
                except Exception:                # noqa: BLE001
                    pass
            return None
        for n in names:
            v = getattr(raw, n, None)
            if v is not None:
                try:
                    if test(v):
                        return v
                except Exception:                # noqa: BLE001
                    pass
        return None

    def seal(self, event, detail, api_key=None):
        """
        MUST NOT be called while holding self.lock. The platform's own seal
        takes that same lock, and it is a plain Lock rather than a reentrant
        one, so calling it from inside a held lock deadlocks the request.
        """
        if self._seal is None:
            return {"sealed": False,
                    "reason": "the platform chain was not reachable from this "
                              "module"}

        ev = {"user_id": "tokensaver", "action": str(event), "amount": 0,
              "country": "UK", "device_id": "module", "anomaly": 0,
              "device_risk": 0}
        now = time.time()

        attempts = (
            lambda: self._seal(ev, detail, now, api_key),
            lambda: self._seal(ev, detail, now),
            lambda: self._seal(event, detail),
            lambda: self._seal({"event": event, "detail": detail}),
        )
        r = None
        last = None
        for call in attempts:
            try:
                r = call()
                break
            except TypeError as e:
                last = e
                continue
            except Exception as e:               # noqa: BLE001
                return {"sealed": False, "reason": str(e)}
        if r is None:
            return {"sealed": False,
                    "reason": "could not match the chain's seal signature: "
                              + str(last)}

        if isinstance(r, dict):
            return r
        if isinstance(r, str):
            return {"hash": r}
        if isinstance(r, (list, tuple)) and r:
            out = {"hash": str(r[0])}
            if len(r) > 1 and r[1] is not None:
                out["block_index"] = r[1]
            if len(r) > 2 and r[2] is not None:
                out["key_seq"] = r[2]
            return out
        return {"sealed": True}


_FALLBACK_LOCK = threading.RLock()
_FALLBACK_CONN = None


def _bridge(raw):
    """
    Built fresh every call on purpose. Caching it by id() is unsafe:
    Python recycles ids once an object is collected, so a cached bridge
    can end up serving a different request's context.
    """
    if isinstance(raw, _Bridge):
        return raw
    return _Bridge(raw)


def handle(method, action, data, api_key, ctx):
    ctx = _bridge(ctx)
    _init(ctx)
    data = data or {}
    now = time.time()

    if method == "GET" and action == "spec":
        sp = _a_spec()
        if ctx.notes:
            sp["wiring_notes"] = ctx.notes
        return sp, 200
    if method == "GET" and action == "stats":
        return _a_stats(ctx)
    if method == "GET" and action == "verify":
        return _a_verify(ctx, data)

    if not api_key:
        return {"error": "key_required"}, 401

    if method == "POST" and action == "estimate":
        return _a_estimate(ctx, api_key, data, now)
    if method == "POST" and action == "gate":
        return _a_gate(ctx, api_key, data, now)
    if method == "POST" and action == "record":
        return _a_record(ctx, api_key, data, now)
    if method == "GET" and action == "ledger":
        return _a_ledger(ctx, api_key, data, now)
    if method == "POST" and action == "budget":
        return _a_budget(ctx, api_key, data, now)
    if method == "POST" and action == "prices":
        return _a_prices(ctx, api_key, data, now)
    if method == "POST" and action == "forget":
        return _a_forget(ctx, api_key, data, now)

    return {"error": "unknown_action",
            "actions": ["spec", "stats", "verify", "estimate", "gate",
                        "record", "ledger", "budget", "prices", "forget"]}, 404

```
