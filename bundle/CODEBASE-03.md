# Codebase — part 3 of 50

Contains:
- `modules/auditbridge.py`
- `modules/bind.py`
- `modules/binddesk.py`
- `modules/blocks.py`
- `modules/brand.py`


## `modules/auditbridge.py`

490 lines, 27978 bytes

```python
"""
modules/auditbridge.py  v1.0.0
sebbi.pro for auditors: the chain answers inside Excel and Google Sheets.

Page module (runtime do_GET patch, like map.py). Serves:

    /auditors                     the page
    /a/help                       every command, plain text
    /a/verify?hash=H              VERIFIED · block N · time   or   NOT FOUND
    /a/tip                        the latest block
    /a/count?day=YYYY[-MM[-DD]]   records sealed in that period
    /a/btc                        the latest Bitcoin block height and hash
    /a/sample?n=25&btc=HEIGHT     a CSV sample selected by that Bitcoin block's hash
    /a/audit?domain=D             any company's AI integrity level, checked live, sealed
    /a/oscal                      OSCAL assessment results pointing at live proofs

Plain text (one line, or CSV for samples) so spreadsheets read it directly:
    Google Sheets  =IMPORTDATA("https://sebbi.pro/a/verify?hash="&A2)
    Excel          =WEBSERVICE("https://sebbi.pro/a/verify?hash="&A2)

Read-only against the chain, except /a/audit, which runs the existing
integrity checker (that checker seals its own verdicts, one per domain per day).
Armed by /x/auditbridge/status after each deploy.
"""

import base64
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
PAGE = "/auditors"
BASE = "https://sebbi.pro"
MAX_SAMPLE = 200

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij48bWV0YSBuYW1lPSJ2aWV3"
    "cG9ydCIgY29udGVudD0id2lkdGg9ZGV2aWNlLXdpZHRoLGluaXRpYWwtc2NhbGU9MSx2aWV3cG9ydC1maXQ9Y292ZXIiPgo8dGl0"
    "bGU+c2ViYmkucHJvIGZvciBhdWRpdG9ycyDigJQgdGhlIGNoYWluIGluc2lkZSB5b3VyIHNwcmVhZHNoZWV0PC90aXRsZT4KPG1l"
    "dGEgbmFtZT0iZGVzY3JpcHRpb24iIGNvbnRlbnQ9IlR5cGUgYSBmb3JtdWxhIGluIEV4Y2VsIG9yIEdvb2dsZSBTaGVldHMgYW5k"
    "IGV2ZXJ5IHJvdyB2ZXJpZmllcyBpdHNlbGYgYWdhaW5zdCB0aGUgc2ViYmkucHJvIGNoYWluLiBQbHVzIHRoZSBhdWRpdCBzYW1w"
    "bGUgbm9ib2R5IGNob3NlLCBzZWVkZWQgYnkgYSBmdXR1cmUgQml0Y29pbiBibG9jay4iPgo8bGluayBocmVmPSJodHRwczovL2Zv"
    "bnRzLmdvb2dsZWFwaXMuY29tL2NzczI/ZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0QDYuLjcyLDUwMCZmYW1pbHk9SUJNK1Bs"
    "ZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMCZkaXNwbGF5PXN3YXAiIHJl"
    "bD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzBhMGYxZTstLXBhcGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7"
    "LS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0tbXV0ZWQ6IzVBNjI3MDstLXNhbnM6J0lCTSBQbGV4IFNhbnMnLHN5c3RlbS11"
    "aSxzYW5zLXNlcmlmOy0tc2VyaWY6J05ld3NyZWFkZXInLEdlb3JnaWEsc2VyaWY7LS1tb25vOidJQk0gUGxleCBNb25vJyx1aS1t"
    "b25vc3BhY2UsbW9ub3NwYWNlfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjB9Ym9keXtmb250LWZh"
    "bWlseTp2YXIoLS1zYW5zKTtiYWNrZ3JvdW5kOnZhcigtLXBhcGVyKTtjb2xvcjp2YXIoLS1pbmspO2xpbmUtaGVpZ2h0OjEuNn0K"
    "LndyYXB7bWF4LXdpZHRoOjgyMHB4O21hcmdpbjowIGF1dG87cGFkZGluZzowIDIwcHh9LnRvcHtib3JkZXItYm90dG9tOjFweCBz"
    "b2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjE1cHggMH0udG9wIC53cmFwe2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3Bh"
    "Y2UtYmV0d2VlbjtmbGV4LXdyYXA6d3JhcDtnYXA6MTBweH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6"
    "ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0udG9wIGF7Zm9udC1mYW1pbHk6dmFyKC0t"
    "bW9ubyk7Zm9udC1zaXplOjEyLjVweDtjb2xvcjp2YXIoLS1tdXRlZCk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7bWFyZ2luLWxlZnQ6"
    "MTRweH0KLmhlcm97cGFkZGluZzo1MHB4IDAgMjRweH0ua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJw"
    "eDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDdlbTttYXJnaW4tYm90dG9tOjEycHh9Cmgxe2ZvbnQtZmFtaWx5"
    "OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDMycHgsNnZ3LDUycHgpO2xpbmUtaGVpZ2h0OjEu"
    "MDY7bWF4LXdpZHRoOjE3Y2g7bWFyZ2luLWJvdHRvbToxNnB4fS5oZXJvIHB7Zm9udC1zaXplOjE3cHg7Y29sb3I6dmFyKC0tbXV0"
    "ZWQpO21heC13aWR0aDo1OGNofQpzZWN0aW9ue3BhZGRpbmc6MzhweCAwO2JvcmRlci10b3A6MXB4IHNvbGlkIHZhcigtLWxpbmUp"
    "fWgye2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDI0cHgsNHZ3LDM0cHgp"
    "O2xpbmUtaGVpZ2h0OjEuMTU7bWFyZ2luLWJvdHRvbToxMnB4O21heC13aWR0aDoyNGNofQoubGVhZHtjb2xvcjp2YXIoLS1tdXRl"
    "ZCk7bWF4LXdpZHRoOjYyY2g7bWFyZ2luLWJvdHRvbToxOHB4fQouc2hlZXR7YmFja2dyb3VuZDojZmZmO2JvcmRlcjoxcHggc29s"
    "aWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo4cHg7b3ZlcmZsb3c6aGlkZGVuO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2Zv"
    "bnQtc2l6ZToxMnB4fQouc2hlZXQgLmZ4e2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRpbmc6OXB4IDEy"
    "cHg7YmFja2dyb3VuZDojZjNmMmVjO292ZXJmbG93LXg6YXV0bzt3aGl0ZS1zcGFjZTpub3dyYXB9LnNoZWV0IC5meCBie2NvbG9y"
    "OnZhcigtLWdvbGQpfQouc2hlZXQgdGFibGV7d2lkdGg6MTAwJTtib3JkZXItY29sbGFwc2U6Y29sbGFwc2V9LnNoZWV0IHRke2Jv"
    "cmRlci10b3A6MXB4IHNvbGlkICNlZWU7cGFkZGluZzo4cHggMTJweDt3aGl0ZS1zcGFjZTpub3dyYXB9LnNoZWV0IHRkLm9re2Nv"
    "bG9yOnZhcigtLW9rKTtmb250LXdlaWdodDo1MDB9LnNoZWV0IHRkLmJhZHtjb2xvcjojOUMyRjI2O2ZvbnQtd2VpZ2h0OjUwMH0K"
    "LmdyaWR7ZGlzcGxheTpncmlkO2dhcDoxMnB4O2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnJ9QG1lZGlhKG1pbi13aWR0aDo3MDBw"
    "eCl7LmdyaWR7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnJ9fQouY2FyZHtiYWNrZ3JvdW5kOiNmZmY7Ym9yZGVyOjFweCBz"
    "b2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFkaXVzOjhweDtwYWRkaW5nOjE4cHggMjBweH0uY2FyZCAudHtmb250LWZhbWlseTp2"
    "YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDVlbX0uY2FyZCBoM3tm"
    "b250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyMHB4O21hcmdpbjo0cHggMCA2cHh9LmNh"
    "cmQgcHtmb250LXNpemU6MTQuNXB4O2NvbG9yOnZhcigtLW11dGVkKX0KY29kZSxwcmV7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7"
    "Zm9udC1zaXplOjEycHh9cHJle2JhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZThlNmRmO2JvcmRlci1yYWRpdXM6NnB4O3Bh"
    "ZGRpbmc6MTJweCAxNHB4O292ZXJmbG93LXg6YXV0bzttYXJnaW4tdG9wOjhweDt3aGl0ZS1zcGFjZTpwcmV9Ci50cnl7ZGlzcGxh"
    "eTpmbGV4O2dhcDo4cHg7ZmxleC13cmFwOndyYXA7bWFyZ2luLXRvcDoxMnB4fS50cnkgaW5wdXR7ZmxleDoxO21pbi13aWR0aDoy"
    "MDBweDtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxMnB4O2ZvbnQt"
    "ZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4fQouYnRue2JhY2tncm91bmQ6dmFyKC0tZ29sZCk7Y29sb3I6dmFyKC0t"
    "aW5rKTtib3JkZXI6MDtib3JkZXItcmFkaXVzOjZweDtwYWRkaW5nOjExcHggMTZweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtm"
    "b250LXNpemU6MTNweDtmb250LXdlaWdodDo1MDA7Y3Vyc29yOnBvaW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmU7ZGlzcGxheTpp"
    "bmxpbmUtYmxvY2t9CiNvdXR7bWFyZ2luLXRvcDoxMnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxM3B4O2Jh"
    "Y2tncm91bmQ6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTJweDt3"
    "aGl0ZS1zcGFjZTpwcmUtd3JhcDtkaXNwbGF5Om5vbmU7d29yZC1icmVhazpicmVhay1hbGx9CmZvb3Rlcntib3JkZXItdG9wOjFw"
    "eCBzb2xpZCB2YXIoLS1saW5lKTtwYWRkaW5nOjIycHggMCA0NnB4O2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZTox"
    "MS41cHg7Y29sb3I6IzhBOTBBMH0KPC9zdHlsZT48L2hlYWQ+PGJvZHk+CjxoZWFkZXIgY2xhc3M9InRvcCI+PGRpdiBjbGFzcz0i"
    "d3JhcCI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgZm9yIGF1ZGl0b3JzPC9kaXY+PG5hdj48YSBocmVm"
    "PSIvIj5Ib21lPC9hPjxhIGhyZWY9Ii9wcm92ZSI+UHJvb2Y8L2E+PGEgaHJlZj0iL2Evb3NjYWwiPk9TQ0FMPC9hPjwvbmF2Pjwv"
    "ZGl2PjwvaGVhZGVyPgo8ZGl2IGNsYXNzPSJ3cmFwIj4KPGRpdiBjbGFzcz0iaGVybyI+PGRpdiBjbGFzcz0ia2ljayI+VEhFIENI"
    "QUlOLCBJTlNJREUgWU9VUiBTUFJFQURTSEVFVDwvZGl2Pgo8aDE+VHlwZSBhIGZvcm11bGEuIEV2ZXJ5IHJvdyBwcm92ZXMgaXRz"
    "ZWxmLjwvaDE+CjxwPk5vIGxvZ2luLCBubyBwbHVnLWluLCBubyBleHBvcnQgcmVxdWVzdC4gQXVkaXRvcnMgYWxyZWFkeSBsaXZl"
    "IGluIEV4Y2VsIGFuZCBHb29nbGUgU2hlZXRzLiBTbyB0aGUgc2ViYmkucHJvIGNoYWluIG5vdyBhbnN3ZXJzIGZyb20gaW5zaWRl"
    "IGEgY2VsbDogcGFzdGUgYSBjb2x1bW4gb2YgcmVjZWlwdHMsIGRyYWcgb25lIGZvcm11bGEgZG93biwgYW5kIGV2ZXJ5IHJvdyB2"
    "ZXJpZmllcyBpdHNlbGYgbGl2ZSBhZ2FpbnN0IHRoZSBjaGFpbi48L3A+PC9kaXY+Cgo8c2VjdGlvbiBpZD0iYW55b25lIj48aDI+"
    "QXVkaXQgYW55b25lIGluIHRoZSBsYW5kPC9oMj4KPHAgY2xhc3M9ImxlYWQiPlR5cGUgYW55IGNvbXBhbnkncyBkb21haW4uIHNl"
    "YmJpLnBybyBjaGVja3MgdGhlaXIgcHVibGlzaGVkIEFJIGludGVncml0eSBkZWNsYXJhdGlvbiBsaXZlLCB3YWxrcyBhbmQgcmVj"
    "b21wdXRlcyB0aGVpciBjaGFpbiBpZiB0aGV5IGhhdmUgb25lLCByYXRlcyB0aGVtIEwwIHRvIEw0LCBhbmQgc2VhbHMgdGhlIHZl"
    "cmRpY3QgaW50byBvdXIgY2hhaW4gc28gaXQgY2FuIG5ldmVyIGJlIHF1aWV0bHkgY2hhbmdlZC4gTm8gZGVjbGFyYXRpb24gbWVh"
    "bnMgTDAsIGFuZCB0aGF0IGlzIHNlYWxlZCB0b28uPC9wPgo8ZGl2IGNsYXNzPSJ0cnkiPjxpbnB1dCBpZD0iZCIgcGxhY2Vob2xk"
    "ZXI9ImFueS1jb21wYW55LmNvbSI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJnbygnYXVkaXQ/ZG9tYWluPScrZW5jb2Rl"
    "VVJJQ29tcG9uZW50KGQudmFsdWUudHJpbSgpKSkiPkF1ZGl0IHRoZW08L2J1dHRvbj48L2Rpdj4KPHByZT49SU1QT1JUREFUQSgi"
    "aHR0cHM6Ly9zZWJiaS5wcm8vYS9hdWRpdD9kb21haW49IiZhbXA7QTIpPC9wcmU+CjxwIGNsYXNzPSJsZWFkIiBzdHlsZT0ibWFy"
    "Z2luLXRvcDoxMnB4Ij5QdXQgYSBsaXN0IG9mIHlvdXIgc3VwcGxpZXJzIGluIGNvbHVtbiBBIGFuZCBkcmFnLiBFdmVyeSBBSSBz"
    "dXBwbGllciB5b3UgcmVseSBvbiwgcmF0ZWQgYW5kIHNlYWxlZCwgaW4gb25lIHNoZWV0LjwvcD48L3NlY3Rpb24+Cgo8c2VjdGlv"
    "bj48aDI+VmVyaWZ5IGEgd2hvbGUgY29sdW1uIGluIG9uZSBkcmFnPC9oMj4KPHAgY2xhc3M9ImxlYWQiPkVhY2ggY2VsbCBhc2tz"
    "IHRoZSBjaGFpbiBkaXJlY3RseSBhbmQgZ2V0cyBvbmUgcGxhaW4gbGluZSBiYWNrLjwvcD4KPGRpdiBjbGFzcz0ic2hlZXQiPjxk"
    "aXYgY2xhc3M9ImZ4Ij48Yj5meDwvYj4mbmJzcDsgPUlNUE9SVERBVEEoImh0dHBzOi8vc2ViYmkucHJvL2EvdmVyaWZ5P2hhc2g9"
    "IiZhbXA7QTIpPC9kaXY+Cjx0YWJsZT48dHI+PHRkPjRkZmU5NWFi4oCmYzU3NDg4MzQ8L3RkPjx0ZCBjbGFzcz0ib2siPlZFUklG"
    "SUVEIMK3IGJsb2NrIDIzOTggwrcgMjAyNi0wOS0yMVQxNDowMToyMlo8L3RkPjwvdHI+Cjx0cj48dGQ+ZDdlNzIwODDigKZkYTE2"
    "ZmM1Zjk8L3RkPjx0ZCBjbGFzcz0ib2siPlZFUklGSUVEIMK3IGJsb2NrIDIzODcgwrcgMjAyNi0wOS0yMVQxNDowMTowOVo8L3Rk"
    "PjwvdHI+Cjx0cj48dGQ+MDAwMGJhZGPigKYwZmZlZTAwMDwvdGQ+PHRkIGNsYXNzPSJiYWQiPk5PVCBGT1VORCDCtyB0aGlzIGhh"
    "c2ggaXMgbm90IGluIHRoZSBjaGFpbjwvdGQ+PC90cj48L3RhYmxlPjwvZGl2Pgo8cHJlPkdvb2dsZSBTaGVldHM6ICA9SU1QT1JU"
    "REFUQSgiaHR0cHM6Ly9zZWJiaS5wcm8vYS92ZXJpZnk/aGFzaD0iJmFtcDtBMikKRXhjZWwgKFdpbmRvd3MpOiA9V0VCU0VSVklD"
    "RSgiaHR0cHM6Ly9zZWJiaS5wcm8vYS92ZXJpZnk/aGFzaD0iJmFtcDtBMik8L3ByZT4KPGRpdiBjbGFzcz0idHJ5Ij48aW5wdXQg"
    "aWQ9ImgiIHBsYWNlaG9sZGVyPSJwYXN0ZSBhbnkgcmVjZWlwdCBoYXNoIj48YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9Imdv"
    "KCd2ZXJpZnk/aGFzaD0nK2VuY29kZVVSSUNvbXBvbmVudChoLnZhbHVlLnRyaW0oKSkpIj5WZXJpZnk8L2J1dHRvbj48L2Rpdj4K"
    "PGRpdiBpZD0ib3V0Ij48L2Rpdj48L3NlY3Rpb24+Cgo8c2VjdGlvbj48aDI+VGhlIGF1ZGl0IHNhbXBsZSBub2JvZHkgY2hvc2U8"
    "L2gyPgo8cCBjbGFzcz0ibGVhZCI+RXZlcnkgYXVkaXQgdGVzdHMgYSBzYW1wbGUsIGFuZCB0aGUgb2xkIHF1ZXN0aW9uIGlzIHdo"
    "byBwaWNrZWQgaXQuIEhlcmUgdGhlIHJhbmRvbSBzZWVkIGlzIGEgQml0Y29pbiBibG9jayB0aGF0IGhhcyBub3QgYmVlbiBtaW5l"
    "ZCB5ZXQgd2hlbiB5b3UgYXNrLiBOb2JvZHksIG5vdCB0aGUgY29tcGFueSwgbm90IHRoZSBhdWRpdG9yLCBub3Qgc2ViYmkucHJv"
    "LCBjYW4gaW5mbHVlbmNlIGl0LiBXaGVuIHRoZSBibG9jayBsYW5kcywgdGhlIHNhbXBsZSBleGlzdHM7IGJlZm9yZSB0aGVuIGl0"
    "IGNhbm5vdC48L3A+CjxwcmU+PUlNUE9SVERBVEEoImh0dHBzOi8vc2ViYmkucHJvL2Evc2FtcGxlP249MjUmYW1wO2J0Yz08aT5m"
    "dXR1cmUgYmxvY2sgaGVpZ2h0PC9pPiIpPC9wcmU+CjxwIGNsYXNzPSJsZWFkIiBzdHlsZT0ibWFyZ2luLXRvcDoxMnB4Ij5Zb3Ug"
    "Z2V0IGEgQ1NWIG9mIHNhbXBsZWQgcmVjb3Jkcywgc3RyYWlnaHQgaW50byBTaGVldHMsIEV4Y2VsLCBJREVBIG9yIEFDTCwgd2l0"
    "aCB0aGUgQml0Y29pbiBibG9jayBoYXNoIHRoYXQgc2VsZWN0ZWQgdGhlbSwgc28gYW55b25lIGNhbiByZS1ydW4gdGhlIHNlbGVj"
    "dGlvbiBhbmQgZ2V0IHRoZSBzYW1lIHJvd3MuPC9wPgo8ZGl2IGNsYXNzPSJ0cnkiPjxidXR0b24gY2xhc3M9ImJ0biIgb25jbGlj"
    "az0iZ28oJ2J0YycpIj5XaGF0J3MgdGhlIG5leHQgQml0Y29pbiBibG9jaz88L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4iIG9u"
    "Y2xpY2s9ImdvKCdzYW1wbGU/bj0xMCZidGM9bGF0ZXN0JykiPlNhbXBsZSAxMCB1c2luZyB0aGUgbGF0ZXN0IGJsb2NrPC9idXR0"
    "b24+PC9kaXY+PC9zZWN0aW9uPgoKPHNlY3Rpb24+PGgyPkV2ZXJ5IGNvbW1hbmQsIG9uZSBsaW5lIGJhY2s8L2gyPgo8ZGl2IGNs"
    "YXNzPSJncmlkIj4KPGRpdiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idCI+L2EvdmVyaWZ5P2hhc2g9PC9kaXY+PGgzPklzIHRo"
    "aXMgcmVjb3JkIGluIHRoZSBjaGFpbj88L2gzPjxwPlZFUklGSUVEIHdpdGggYmxvY2sgYW5kIHRpbWUsIG9yIE5PVCBGT1VORC48"
    "L3A+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL2F1ZGl0P2RvbWFpbj08L2Rpdj48aDM+QXVkaXQg"
    "YW55IGNvbXBhbnk8L2gzPjxwPlRoZWlyIEFJIGludGVncml0eSBsZXZlbCwgY2hlY2tlZCBsaXZlIGFuZCBzZWFsZWQuPC9wPjwv"
    "ZGl2Pgo8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0Ij4vYS90aXA8L2Rpdj48aDM+V2hlcmUgaXMgdGhlIGNoYWluIG5v"
    "dz88L2gzPjxwPkxhdGVzdCBibG9jaywgaXRzIGhhc2ggYW5kIHdoZW4gaXQgd2FzIHNlYWxlZC48L3A+PC9kaXY+CjxkaXYgY2xh"
    "c3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL2NvdW50P2RheT0yMDI2LTA5LTIxPC9kaXY+PGgzPkhvdyBtYW55IHJlY29yZHMg"
    "dGhhdCBkYXk/PC9oMz48cD5UaGUgY291bnQgZm9yIGFueSBkYXksIG1vbnRoIG9yIHllYXIsIHRvIHJlY29uY2lsZSBhZ2FpbnN0"
    "IHlvdXIgcG9wdWxhdGlvbi48L3A+PC9kaXY+CjxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InQiPi9hL3NhbXBsZT9uPTI1"
    "JmFtcDtidGM9PC9kaXY+PGgzPlRoZSBzYW1wbGUgbm9ib2R5IGNob3NlPC9oMz48cD5TZWVkZWQgYnkgYSBmdXR1cmUgQml0Y29p"
    "biBibG9jay4gUmUtcnVubmFibGUgYnkgYW55b25lLjwvcD48L2Rpdj4KPGRpdiBjbGFzcz0iY2FyZCI+PGRpdiBjbGFzcz0idCI+"
    "L2Evb3NjYWw8L2Rpdj48aDM+T1NDQUwgYXNzZXNzbWVudCByZXN1bHRzPC9oMz48cD5UaGUgVVMgZ292ZXJubWVudCdzIG1hY2hp"
    "bmUgZm9ybWF0IGZvciBhdWRpdCBldmlkZW5jZS4gSW1wb3J0IGl0IGludG8gR1JDIHRvb2xzOyBldmVyeSBmaW5kaW5nIHBvaW50"
    "cyBhdCBhIGxpdmUgcHJvb2YuPC9wPjwvZGl2Pgo8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0Ij4vYS9oZWxwPC9kaXY+"
    "PGgzPkFsbCBjb21tYW5kczwvaDM+PHA+UGxhaW4gdGV4dCwgcmVhZGFibGUgYnkgYW55IHRvb2wsIHNjcmlwdCBvciBBSS48L3A+"
    "PC9kaXY+CjwvZGl2Pjwvc2VjdGlvbj4KCjxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0taW5rKTtjb2xvcjojZmZmO2JvcmRl"
    "ci1yYWRpdXM6MTBweDtwYWRkaW5nOjMwcHggMjRweDttYXJnaW46MzRweCAwIDQ4cHgiPgo8aDIgc3R5bGU9ImNvbG9yOiNmZmYi"
    "PkF1ZGl0b3JzOiBzdG9wIGFza2luZyBmb3Igc2NyZWVuc2hvdHMuPC9oMj4KPHAgc3R5bGU9ImNvbG9yOnJnYmEoMjU1LDI1NSwy"
    "NTUsLjc1KTttYXgtd2lkdGg6NTZjaDttYXJnaW4tYm90dG9tOjE4cHgiPkFzayB0aGUgY2hhaW4uIEl0IGFuc3dlcnMgaW4geW91"
    "ciBvd24gdG9vbHMsIHdpdGggb3VyIHNlcnZlcnMgc3dpdGNoZWQgb2ZmIGZvciBhbnl0aGluZyB5b3UgaGF2ZSBhbHJlYWR5IHZl"
    "cmlmaWVkIG9mZmxpbmUuPC9wPgo8YSBjbGFzcz0iYnRuIiBocmVmPSIjYW55b25lIj5BdWRpdCBhIGNvbXBhbnkgbm93PC9hPiA8"
    "YSBjbGFzcz0iYnRuIiBocmVmPSIvcHJvdmUiIHN0eWxlPSJiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2NvbG9yOiNmZmY7Ym9yZGVy"
    "OjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4zKSI+U2VlIGV2ZXJ5IHByb29mPC9hPjwvZGl2Pgo8L2Rpdj4KPGZvb3Rlcj48"
    "ZGl2IGNsYXNzPSJ3cmFwIj5zZWJiaS5wcm8gwrcgTW9ub3AgQ29udGVudCDCtyBCbHl0aCwgTm9ydGh1bWJlcmxhbmQsIFVLPC9k"
    "aXY+PC9mb290ZXI+CjxzY3JpcHQ+CnZhciBoPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdoJyksbz1kb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgnb3V0Jyk7CmZ1bmN0aW9uIGdvKHEpe28uc3R5bGUuZGlzcGxheT0nYmxvY2snO28udGV4dENvbnRlbnQ9J0Fza2lu"
    "ZyB0aGUgY2hhaW7igKYnO2ZldGNoKCcvYS8nK3Ese2NhY2hlOiduby1zdG9yZSd9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiBy"
    "LnRleHQoKX0pLnRoZW4oZnVuY3Rpb24odCl7by50ZXh0Q29udGVudD10fSkuY2F0Y2goZnVuY3Rpb24oKXtvLnRleHRDb250ZW50"
    "PSdDb3VsZCBub3QgcmVhY2ggdGhlIGNoYWluLid9KX0KPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)
_HTML = base64.b64decode("".join(_HTML_B64.split()))
_patched = False
_ctx = {}
_cols = {}
_btc_cache = {}


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(ts)


def _schema():
    """Find the audit_log column names rather than assuming them."""
    if _cols:
        return _cols
    with _ctx["lock"]:
        rows = _ctx["conn"].execute("PRAGMA table_info(audit_log)").fetchall()
    names = [r[1] for r in rows]
    if not names:
        return {}

    def first(opts):
        for o in opts:
            if o in names:
                return o
        return None
    _cols.update(hash=first(["audit_hash", "hash", "block_hash"]),
                 ts=first(["ts", "timestamp", "created", "time"]),
                 idx=first(["block_index", "idx", "block", "height", "id"]) or "rowid")
    return _cols


def _q(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _period(s):
    s = (s or "").strip()
    try:
        if re.fullmatch(r"\d{4}", s):
            a = datetime(int(s), 1, 1, tzinfo=timezone.utc); b = datetime(int(s) + 1, 1, 1, tzinfo=timezone.utc)
        elif re.fullmatch(r"\d{4}-\d{2}", s):
            y, m = map(int, s.split("-")); a = datetime(y, m, 1, tzinfo=timezone.utc)
            b = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=timezone.utc)
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            a = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc); b = a.fromtimestamp(a.timestamp() + 86400, tz=timezone.utc)
        else:
            return None
    except ValueError:
        return None
    return a.timestamp(), b.timestamp()


def _get(url, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "sebbi-auditbridge/" + VERSION})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(200000).decode("utf-8", "replace").strip()


def _btc(height=None):
    """Bitcoin block (height, hash) from two public explorers; they must agree."""
    key = str(height)
    if key in _btc_cache and (height is not None or time.time() - _btc_cache[key][2] < 60):
        return _btc_cache[key][:2]
    if height is None:
        height = int(_get("https://mempool.space/api/blocks/tip/height"))
    hashes = []
    for url in ("https://mempool.space/api/block-height/%d" % height,
                "https://blockstream.info/api/block-height/%d" % height):
        try:
            hashes.append(_get(url))
        except Exception:
            pass
    good = [h for h in hashes if re.fullmatch(r"[0-9a-f]{64}", h)]
    if not good:
        return height, None
    if len(set(good)) > 1:
        raise ValueError("explorers disagree on block %d" % height)
    _btc_cache[key] = (height, good[0], time.time())
    return height, good[0]


# ---------------------------------------------------------------- commands

def c_help(q):
    return ("sebbi.pro auditor commands (plain text, one line each)\n"
            "/a/verify?hash=H             is this record in the chain\n"
            "/a/tip                       latest block\n"
            "/a/count?day=YYYY[-MM[-DD]]  records in a period\n"
            "/a/btc                       latest Bitcoin block\n"
            "/a/sample?n=25&btc=HEIGHT    sample chosen by a Bitcoin block (CSV)\n"
            "/a/audit?domain=D            any company's AI integrity level, sealed\n"
            "/a/oscal                     OSCAL assessment results\n"
            "Sheets: =IMPORTDATA(\"https://sebbi.pro/a/verify?hash=\"&A2)\n"
            "Excel:  =WEBSERVICE(\"https://sebbi.pro/a/verify?hash=\"&A2)\n"), "text/plain"


def c_verify(q):
    c = _schema()
    h = (q.get("hash") or "").strip().lower()
    if not c.get("hash"):
        return "ERROR · chain table not readable", "text/plain"
    if not re.fullmatch(r"[0-9a-f]{64}", h):
        return "INVALID · a receipt hash is 64 hex characters", "text/plain"
    r = _q("SELECT %s,%s FROM audit_log WHERE %s=? LIMIT 1" % (c["idx"], c["ts"] or "NULL", c["hash"]), (h,))
    if not r:
        return "NOT FOUND · this hash is not in the chain", "text/plain"
    tip = _q("SELECT MAX(%s) FROM audit_log" % c["idx"])[0][0]
    depth = (tip - r[0][0]) if isinstance(tip, int) and isinstance(r[0][0], int) else "?"
    return "VERIFIED · block %s · %s · %s blocks deep" % (r[0][0], _iso(r[0][1]), depth), "text/plain"


def c_tip(q):
    c = _schema()
    r = _q("SELECT %s,%s,%s FROM audit_log ORDER BY %s DESC LIMIT 1" % (c["idx"], c["hash"], c["ts"] or "NULL", c["idx"]))
    if not r:
        return "EMPTY", "text/plain"
    return "TIP · block %s · %s · %s" % (r[0][0], r[0][1], _iso(r[0][2])), "text/plain"


def c_count(q):
    c = _schema()
    p = _period(q.get("day") or q.get("period"))
    if not p or not c.get("ts"):
        return "INVALID · use day=YYYY, YYYY-MM or YYYY-MM-DD", "text/plain"
    n = _q("SELECT COUNT(*) FROM audit_log WHERE %s>=? AND %s<?" % (c["ts"], c["ts"]), p)[0][0]
    return "COUNT · %s · %d records" % (q.get("day") or q.get("period"), n), "text/plain"


def c_btc(q):
    try:
        h, bh = _btc()
    except Exception as e:
        return "ERROR · %s" % e, "text/plain"
    return "BITCOIN · latest block %s · %s · ask for a sample with btc=%d or later" % (h, bh, h + 1), "text/plain"


def c_sample(q):
    c = _schema()
    try:
        n = max(1, min(MAX_SAMPLE, int(q.get("n", 25))))
    except ValueError:
        n = 25
    want = (q.get("btc") or "").strip().lower()
    try:
        height, bh = _btc(None if want in ("", "latest") else int(want))
    except ValueError as e:
        return "ERROR · %s" % e, "text/plain"
    except Exception:
        return "ERROR · could not reach Bitcoin explorers", "text/plain"
    if not bh:
        return ("PENDING · Bitcoin block %s is not mined yet. The sample cannot exist until it is, "
                "so nobody can have chosen it. Ask again after it lands." % height), "text/plain"
    total = _q("SELECT COUNT(*) FROM audit_log")[0][0]
    if not total:
        return "EMPTY", "text/plain"
    picks, seen, i = [], set(), 0
    while len(picks) < min(n, total):
        k = int(hashlib.sha256(("%s:%d" % (bh, i)).encode()).hexdigest(), 16) % total
        i += 1
        if k in seen:
            continue
        seen.add(k)
        r = _q("SELECT %s,%s,%s FROM audit_log ORDER BY %s LIMIT 1 OFFSET ?" % (c["idx"], c["hash"], c["ts"] or "NULL", c["idx"]), (k,))
        if r:
            picks.append((k, r[0]))
    lines = ["position,block,hash,sealed_at,verify"]
    for k, r in sorted(picks):
        lines.append("%d,%s,%s,%s,%s/a/verify?hash=%s" % (k, r[0], r[1], _iso(r[2]), BASE, r[1]))
    lines.append("# selected by Bitcoin block %s hash %s from %d records" % (height, bh, total))
    lines.append("# rule: position_i = int(sha256(blockhash + ':' + i)) mod total, skipping repeats, ordered by chain position")
    return "\n".join(lines) + "\n", "text/csv"


def _integrity():
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("integrity.py") and hasattr(m, "handle"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integrity.py")
    spec = importlib.util.spec_from_file_location("auditbridge_integrity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _find(obj, keys, depth=0):
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and isinstance(obj[k], (str, int)):
                return obj[k]
        for v in obj.values():
            r = _find(v, keys, depth + 1)
            if r is not None:
                return r
    return None


def c_audit(q):
    d = (q.get("domain") or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0]
    if not re.fullmatch(r"[a-z0-9.-]{3,253}", d) or "." not in d:
        return "INVALID · give a domain like example.com", "text/plain"
    try:
        res = _integrity().handle("GET", "check", {"domain": d}, None, _ctx)
        body = res[0] if isinstance(res, tuple) else res
    except Exception as e:
        return "ERROR · checker unavailable: %s" % str(e)[:120], "text/plain"
    lvl = _find(body, ["verified_level", "level", "verdict", "rating", "result"]) or "UNRATED"
    blk = _find(body, ["block_index", "sealed_block", "block"])
    why = _find(body, ["summary", "reason", "message", "note"])
    out = "%s · %s" % (d, lvl)
    if blk is not None:
        out += " · sealed in block %s" % blk
    if why:
        out += " · %s" % str(why)[:160]
    return out + " · full report %s/x/integrity/check?domain=%s" % (BASE, d), "text/plain"


def c_oscal(q):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tip = c_tip(q)[0]
    obs = [("Record integrity", "Every record is SHA-256 hash-chained; any edit breaks all later records.", "/api/verify-chain"),
           ("Append-only log", "RFC 6962 consistency proofs show the log only grows.", "/x/consistency/root"),
           ("Completeness", "Per-period Merkle roots with committed counts; absence is provable.", "/x/complete/periods"),
           ("External time anchor", "Chain tips anchored to Bitcoin via OpenTimestamps.", "/x/ots/latest_confirmed"),
           ("Independent witnessing", "Independent organisations hold and witness chain tips.", "/x/roster/list"),
           ("Custody", "Daily self-proving archive file with a sealed count of independent holders.", "/x/custody/status"),
           ("Authority at the moment of action", "Authority re-derived at the execution boundary; signed proofs.", "/x/continuity/decisions"),
           ("Agent permission", "Signed single-use Agent Passports, redeemed once with standing re-checked.", "/x/passport/status")]
    doc = {"assessment-results": {
        "uuid": hashlib.sha256(("sebbi-oscal:" + now[:10]).encode()).hexdigest()[:32],
        "metadata": {"title": "sebbi.pro live assessment results", "last-modified": now, "version": VERSION,
                     "oscal-version": "1.1.2", "parties": [{"type": "organization", "name": "Monop Content (sebbi.pro)"}]},
        "results": [{"title": "Live machine-verifiable evidence", "start": now,
                     "description": "Each observation links to a public route that returns the evidence itself. " + tip,
                     "observations": [{"title": t, "description": desc, "methods": ["TEST"],
                                       "relevant-evidence": [{"href": BASE + u, "description": "live, no account required"}],
                                       "collected": now} for t, desc, u in obs]}]}}
    return json.dumps(doc, indent=1), "application/json"


CMDS = {"help": c_help, "verify": c_verify, "tip": c_tip, "count": c_count, "btc": c_btc,
        "sample": c_sample, "audit": c_audit, "oscal": c_oscal}


def _send(h, body, ctype, code=200):
    b = body.encode("utf-8") if isinstance(body, str) else body
    h.send_response(code)
    h.send_header("Content-Type", ctype + ("; charset=utf-8" if not ctype.endswith("utf-8") else ""))
    h.send_header("Content-Length", str(len(b)))
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    h.wfile.write(b)


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


def _install(ctx):
    global _patched
    if isinstance(ctx, dict) and "conn" in ctx:
        _ctx.update(ctx)
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_auditbridge_patched", False):
        _patched = True
        return True
    original = cls.do_GET

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        if path == PAGE:
            return _send(self, _HTML, "text/html")
        if path.startswith("/a/") and path[3:] in CMDS:
            if "conn" not in _ctx:
                return _send(self, "NOT ARMED · open /x/auditbridge/status once", "text/plain", 503)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            try:
                body, ctype = CMDS[path[3:]](q)
            except Exception as e:
                body, ctype = "ERROR · %s" % str(e)[:160], "text/plain"
            return _send(self, body, ctype)
        return original(self)

    cls.do_GET = do_GET
    cls._auditbridge_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install(ctx)
    return {"module": "auditbridge", "version": VERSION, "armed": armed,
            "serves": [PAGE] + ["/a/" + k for k in CMDS],
            "page": BASE + PAGE}, 200

```


## `modules/bind.py`

733 lines, 35203 bytes

```python
#!/usr/bin/env python3
"""modules/bind.py - the signed lane.

A peer signs their own submission with a credential, so binding rests on
possession of a secret rather than on a fetcher reaching a url.

v1.2.0 - block indices now carry their chain epoch.

A block_index on its own is not a reference. The chain restarted from
genesis on 7 September 2026, and an index issued before that became wrong
in the last day - not dangling, but resolving to a real, correctly-sealed
block belonging to someone else, as the chain grew past it. A dangling
pointer announces itself. A pointer that quietly lands on another party's
record does not.

So: every row this module writes from now on records the genesis hash of
the chain it was sealed under, and every route publishing an index says
which epoch it belongs to and whether that epoch is still current. Rows
written before this version have no epoch recorded and cannot be given
one retroactively - inventing it would be the same fault one step back -
so they publish as epoch unknown with the index marked unresolvable
against this chain. Raised by Ishaan (Shango MID), whose own rule is that
a grant carries the epoch it was decided under and is refused when the
epoch has moved.

    POST /x/bind/issue      issue a credential for a name   (operator key)
    POST /x/bind/claim      seal a dated claim marker       (operator key)
    POST /x/bind/revoke     revoke a credential             (operator key)
    POST /x/bind/submit     signed tip submission           (signature only)
    GET  /x/bind/name       binding state and history       (public)
    GET  /x/bind/conflicts  every contested name            (public)
    GET  /x/bind/spec       how to sign, in full            (public)
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone

VERSION = "1.2.0"

PUBLIC = {("GET", "name"), ("GET", "conflicts"), ("GET", "spec")}

SIG_PREFIX = b"AILEASH-BIND-v1:"
CLOCK_SKEW = 300
NONCE_KEEP = 3600

RESET_DATE = "2026-09-07"

SECRET_SCOPE = (
    "A credential is a shared secret. Holding it proves the submitter had "
    "the secret, and nothing more. This platform holds a copy, so it does "
    "not exclude the operator. Anyone the secret has been shown to - a "
    "screenshot, a paste into another tool, a colleague - holds it too, and "
    "this lane cannot tell them apart. To exclude the operator, use the "
    "Ed25519 lane at /x/signed/enroll, where the private half never leaves "
    "the peer.")

EPOCH_VOCABULARY = {
    "what_an_epoch_is":
        "The genesis hash of the chain a block index was issued under. An "
        "index without it is not a reference: this chain restarted from "
        "genesis on " + RESET_DATE + ", and an index from before that now "
        "resolves to a real, correctly-sealed block belonging to someone "
        "else. Published so a stale pointer is detectably stale rather "
        "than quietly wrong.",
    "current":
        "Issued under the chain this deployment is serving now. The index "
        "resolves to the block it was issued against.",
    "retired":
        "Issued under an earlier chain. The number may still resolve here, "
        "but to a DIFFERENT block. Do not follow it.",
    "unknown":
        "Recorded before this module stored epochs, so the chain it was "
        "issued under is not known. It cannot be resolved against this "
        "chain and no epoch can be assigned to it after the fact.",
}

_ready = False
_genesis_cache = {"hash": None, "blocks": 0}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS bind_credential("
                  "key_id TEXT PRIMARY KEY,name TEXT NOT NULL,secret TEXT NOT NULL,"
                  "issued_to TEXT,issued REAL,revoked REAL,revoke_reason TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_claim("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "claimant TEXT,claimed_at REAL,note TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_submission("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,"
                  "tip TEXT,key_id TEXT,ts REAL,nonce TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_nonce("
                  "nonce TEXT PRIMARY KEY,ts REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS bind_seq("
                  "name TEXT PRIMARY KEY,seq INTEGER DEFAULT 0)")
        # v1.2.0. Added rather than backfilled: a row written before this
        # version has no epoch and must not be given one now.
        for table in ("bind_credential", "bind_claim", "bind_submission"):
            try:
                c.execute("ALTER TABLE %s ADD COLUMN chain_epoch TEXT" % table)
            except Exception:
                pass
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_name ON bind_submission(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bind_claim ON bind_claim(name)")
        c.commit()
    _ready = True


def _genesis(ctx):
    """The current chain's genesis hash, read from audit_log itself.

    Cached against the block count so it costs one cheap query per change.
    Returns None if it cannot be read, and a None epoch is recorded as
    unknown rather than guessed.
    """
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT COUNT(*) FROM audit_log").fetchone()
            blocks = int(row[0]) if row else 0
            if _genesis_cache["hash"] and _genesis_cache["blocks"] == blocks:
                return _genesis_cache["hash"]
            g = ctx["conn"].execute(
                "SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT 1"
            ).fetchone()
        h = g[0] if g else None
        _genesis_cache["hash"] = h
        _genesis_cache["blocks"] = blocks
        return h
    except Exception:
        return None


def _ref(ctx, block_index, stored_epoch):
    """A block index published with the epoch it was issued under."""
    current = _genesis(ctx)
    if not stored_epoch:
        state = "unknown"
    elif current and stored_epoch == current:
        state = "current"
    else:
        state = "retired"
    out = {"block_index": block_index,
           "chain_epoch": stored_epoch,
           "epoch_state": state,
           "current_chain_epoch": current,
           "meaning": EPOCH_VOCABULARY[state]}
    if state == "current":
        out["resolve_at"] = ("https://sebbi.pro/x/walk/block?index=%s"
                             % block_index)
    else:
        out["do_not_resolve"] = (
            "This number may still return a block on this chain. It would "
            "be a different block. Nothing here points at it.")
    return out


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), default=str)


def _clean_name(n):
    n = str(n or "").strip().lower()[:120]
    return "".join(ch for ch in n if ch.isalnum() or ch in ".-_/:")


def _sig(secret, name, tip, ts, nonce):
    material = SIG_PREFIX + _canon({"name": name, "tip": tip,
                                    "ts": int(ts), "nonce": nonce}).encode("utf-8")
    return hmac.new(bytes.fromhex(secret), material, hashlib.sha256).hexdigest()


def _latest_seq(ctx, name):
    try:
        with ctx["lock"]:
            row = ctx["conn"].execute(
                "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _issue(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400
    to = str(data.get("issued_to", "")).strip()[:200] or None

    with ctx["lock"]:
        live = ctx["conn"].execute(
            "SELECT key_id FROM bind_credential WHERE name=? AND revoked IS NULL",
            (name,)).fetchone()
    if live and not data.get("replace"):
        return {"error": "credential_already_issued", "name": name,
                "key_id": live[0],
                "message": "A live credential exists for this name. Send "
                           "replace true to revoke it and issue another, which "
                           "is itself sealed."}, 409

    secret = secrets.token_hex(32)
    key_id = "bk_" + secrets.token_hex(8)
    now = time.time()
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "credential_issued",
          "amount": 0, "country": "UK", "device_id": "bind",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "CREDENTIAL_ISSUED", "score": 0, "bind_version": VERSION,
           "name": name, "key_id": key_id, "issued_to": to,
           "secret_sealed": False, "chain_epoch": epoch,
           "detail": "name=%s;key_id=%s;issued_to=%s" % (name, key_id, to)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        if live:
            ctx["conn"].execute(
                "UPDATE bind_credential SET revoked=?, revoke_reason=? "
                "WHERE key_id=?", (now, "replaced by " + key_id, live[0]))
        ctx["conn"].execute(
            "INSERT INTO bind_credential(key_id,name,secret,issued_to,issued,"
            "audit_hash,block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (key_id, name, secret, to, now, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "key_id": key_id, "secret": secret,
            "issued_to": to, "issued_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "current_submission_seq": _latest_seq(ctx, name),
            "send_this_once": ("The secret is shown here and nowhere else. It "
                               "is not sealed into the chain and cannot be "
                               "recovered - if it is lost, revoke and reissue."),
            "how_to_sign": "/x/bind/spec",
            "what_it_proves": ("Possession of this secret. It does not prove "
                               "domain ownership and this platform does not "
                               "check that."),
            "secret_scope": SECRET_SCOPE,
            "note_on_sequence": ("current_submission_seq is where this name's "
                                 "receipt numbering stands. Reissuing a "
                                 "credential does not reset it - the sequence "
                                 "belongs to the name's submission history, "
                                 "not to the key."),
            "replaced": live[0] if live else None}, 200


def _claim(ctx, api_key, data):
    name = _clean_name(data.get("name"))
    claimant = str(data.get("claimant", "")).strip()[:200]
    if not name or not claimant:
        return {"error": "name_and_claimant_required"}, 400
    note = str(data.get("note", "")).strip()[:500] or None
    now = time.time()
    epoch = _genesis(ctx)

    ev = {"user_id": "bind:" + name[:40], "action": "name_claimed", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "NAME_CLAIMED", "score": 0, "bind_version": VERSION,
           "name": name, "claimant": claimant, "note": note,
           "chain_epoch": epoch,
           "detail": "name=%s;claimant=%s" % (name, claimant)}
    h, idx, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO bind_claim(name,claimant,claimed_at,note,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?)",
            (name, claimant, now, note, h, idx, epoch))
        ctx["conn"].commit()

    return {"name": name, "claimant": claimant, "claimed_at": _iso(now),
            "sealed_in_chain": h, "receipt_seq": seq,
            "sealed_at": _ref(ctx, idx, epoch),
            "what_this_is": ("A dated marker, not a binding. Anyone can still "
                             "submit under this name - but their block is "
                             "provably later than this one, and the conflict "
                             "is public."),
            "what_this_is_not": ("Proof that the claimant owns the name, and "
                                 "not a substitute for a credential.")}, 200


def _revoke(ctx, api_key, data):
    key_id = str(data.get("key_id", "")).strip()
    if not key_id:
        return {"error": "key_id_required"}, 400
    reason = str(data.get("reason", "")).strip()[:300] or "not stated"
    now = time.time()

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT name, revoked FROM bind_credential WHERE key_id=?",
            (key_id,)).fetchone()
    if not row:
        return {"error": "unknown_key_id"}, 404
    if row[1]:
        return {"error": "already_revoked", "revoked_at": _iso(row[1])}, 409

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + row[0][:40], "action": "credential_revoked",
          "amount": 0, "country": "UK", "device_id": "bind", "anomaly": 0,
          "device_risk": 1}
    res = {"decision": "CREDENTIAL_REVOKED", "score": 0, "name": row[0],
           "key_id": key_id, "reason": reason, "chain_epoch": epoch,
           "detail": "key_id=%s;reason=%s" % (key_id, reason)}
    h, idx, _ = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE bind_credential SET revoked=?, revoke_reason=? WHERE key_id=?",
            (now, reason, key_id))
        ctx["conn"].commit()

    return {"key_id": key_id, "name": row[0], "revoked_at": _iso(now),
            "reason": reason, "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "note": "Submissions already bound stay bound. Revocation stops "
                    "future ones and does not rewrite the past."}, 200


def _submit(ctx, data):
    name = _clean_name(data.get("name"))
    tip = str(data.get("tip", "")).strip().lower()
    key_id = str(data.get("key_id", "")).strip()
    sig = str(data.get("signature", "")).strip().lower()
    nonce = str(data.get("nonce", "")).strip()[:80]
    try:
        ts = int(data.get("ts", 0))
    except (TypeError, ValueError):
        ts = 0

    missing = [k for k, v in (("name", name), ("tip", tip), ("key_id", key_id),
                              ("signature", sig), ("nonce", nonce)) if not v]
    if missing or not ts:
        return {"error": "incomplete_submission",
                "missing": missing + ([] if ts else ["ts"]),
                "how_to_sign": "/x/bind/spec"}, 400
    if len(tip) != 64:
        return {"error": "tip_must_be_64_hex"}, 400

    now = time.time()
    if abs(now - ts) > CLOCK_SKEW:
        return {"error": "timestamp_outside_window",
                "your_ts": ts, "our_ts": int(now),
                "window_seconds": CLOCK_SKEW,
                "why": "a signature valid forever is a signature that can be "
                       "replayed forever"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT secret, revoked, issued_to FROM bind_credential "
            "WHERE key_id=? AND name=?", (key_id, name)).fetchone()
        used = ctx["conn"].execute(
            "SELECT 1 FROM bind_nonce WHERE nonce=?", (nonce,)).fetchone()

    if not cred:
        return {"error": "no_credential_for_that_name_and_key"}, 401
    if cred[1]:
        return {"error": "credential_revoked", "revoked_at": _iso(cred[1])}, 401
    if used:
        return {"error": "nonce_already_used",
                "why": "each signature may be presented once"}, 409

    expected = _sig(cred[0], name, tip, ts, nonce)
    if not hmac.compare_digest(expected, sig):
        return {"error": "signature_did_not_verify",
                "check": "/x/bind/spec sets out the exact bytes signed"}, 401

    epoch = _genesis(ctx)
    ev = {"user_id": "bind:" + name[:40], "action": "signed_tip", "amount": 0,
          "country": "UK", "device_id": "bind", "anomaly": 0, "device_risk": 0}
    res = {"decision": "TIP_BOUND", "score": 0, "bind_version": VERSION,
           "name": name, "tip": tip, "key_id": key_id, "binding": "signature",
           "chain_epoch": epoch,
           "detail": "name=%s;tip=%s;key_id=%s" % (name, tip, key_id)}

    try:
        h, idx, key_seq = ctx["seal"](ev, res, now, None)
    except Exception as exc:
        return {"ok": False, "bound": False, "error": "seal_failed",
                "detail": "Your signature verified, but the audit chain did "
                          "not seal the submission, so there is no receipt to "
                          "give you. This is a fault on this deployment and "
                          "not a problem with your submission.",
                "seal_error": "%s: %s" % (type(exc).__name__, str(exc)[:300]),
                "recorded": False,
                "retry": "Nothing was written. Your nonce is unused and the "
                         "identical submission can be resent once this is "
                         "fixed.",
                "name": name, "tip": tip}, 500
    if not h:
        return {"ok": False, "bound": False, "error": "seal_incomplete",
                "detail": "The audit chain returned no hash, so nothing was "
                          "sealed and no receipt exists. Fault on this "
                          "deployment.",
                "recorded": False, "name": name, "tip": tip}, 500

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO bind_seq(name,seq) VALUES(?,0)", (name,))
        ctx["conn"].execute(
            "UPDATE bind_seq SET seq = COALESCE(seq,0) + 1 WHERE name=?", (name,))
        srow = ctx["conn"].execute(
            "SELECT seq FROM bind_seq WHERE name=?", (name,)).fetchone()
        receipt_seq = int(srow[0]) if srow and srow[0] is not None else None

        ctx["conn"].execute(
            "INSERT INTO bind_submission(name,tip,key_id,ts,nonce,audit_hash,"
            "block_index,chain_epoch) VALUES(?,?,?,?,?,?,?,?)",
            (name, tip, key_id, now, nonce, h, idx, epoch))
        ctx["conn"].execute("INSERT OR IGNORE INTO bind_nonce(nonce,ts) "
                            "VALUES(?,?)", (nonce, now))
        ctx["conn"].execute("DELETE FROM bind_nonce WHERE ts < ?",
                            (now - NONCE_KEEP,))
        ctx["conn"].commit()

    return {"bound": True, "name": name, "tip": tip, "key_id": key_id,
            "sealed_in_chain": h,
            "sealed_at": _ref(ctx, idx, epoch),
            "receipt_seq": receipt_seq,
            "receipt_seq_scope": "per-name",
            "key_seq": key_seq,
            "binding": "signature",
            "gapless": ("receipt_seq increments by exactly one for each "
                        "accepted submission under this name. Two receipts "
                        "numbered N and N+2 prove a third exists and you did "
                        "not receive it. The current highest is published at "
                        "/x/bind/name?name=" + name + " so the check does not "
                        "depend on asking us."),
            "key_seq_note": ("The server-wide per-API-key sequence, null on "
                             "this lane and always will be. That counter lives "
                             "on an api_key and this lane authenticates by "
                             "signature with no key to count against. Returned "
                             "rather than omitted so the absence is visible "
                             "instead of inferred."),
            "what_this_proves": ("that a holder of the credential issued for "
                                 "this name submitted this tip, and that the "
                                 "submission has not been altered since it was "
                                 "signed"),
            "what_this_does_not_prove": ("which holder. The secret is shared, "
                                         "so this does not exclude the "
                                         "operator or anyone else it has been "
                                         "disclosed to. It also does not prove "
                                         "domain ownership, or that anything "
                                         "in their chain is true"),
            "secret_scope": SECRET_SCOPE,
            "check_it": "/x/bind/name?name=" + name}, 200


def _name(ctx, data):
    name = _clean_name(data.get("name"))
    if not name:
        return {"error": "name_required"}, 400

    with ctx["lock"]:
        cred = ctx["conn"].execute(
            "SELECT key_id, issued, revoked, issued_to, block_index, "
            "chain_epoch FROM bind_credential WHERE name=? ORDER BY issued DESC",
            (name,)).fetchall()
        claims = ctx["conn"].execute(
            "SELECT claimant, claimed_at, note, block_index, chain_epoch "
            "FROM bind_claim WHERE name=? ORDER BY claimed_at ASC",
            (name,)).fetchall()
        subs = ctx["conn"].execute(
            "SELECT tip, key_id, ts, block_index, chain_epoch "
            "FROM bind_submission WHERE name=? ORDER BY ts DESC LIMIT 20",
            (name,)).fetchall()

    live = [c for c in cred if not c[2]]
    state = ("bound" if live else
             "claimed" if claims else
             "unbound")

    out = {
        "name": name,
        "state": state,
        "lane": "signed (credential). The open lane records a separate "
                "address-level binding, published per entry on "
                "/x/roster/list. The two answer different questions and can "
                "differ without either being wrong.",
        "latest_receipt_seq": _latest_seq(ctx, name),
        "credential": ({"key_id": live[0][0], "issued_at": _iso(live[0][1]),
                        "issued_to": live[0][3],
                        "sealed_at": _ref(ctx, live[0][4], live[0][5])}
                       if live else None),
        "claims": [{"claimant": c[0], "claimed_at": _iso(c[1]), "note": c[2],
                    "sealed_at": _ref(ctx, c[3], c[4])} for c in claims],
        "signed_submissions": [{"tip": s[0], "key_id": s[1], "at": _iso(s[2]),
                                "sealed_at": _ref(ctx, s[3], s[4])}
                               for s in subs],
        "revoked_credentials": [{"key_id": c[0], "revoked_at": _iso(c[2]),
                                 "sealed_at": _ref(ctx, c[4], c[5])}
                                for c in cred if c[2]],
        "chain_epoch": EPOCH_VOCABULARY,
    }
    out["receipt_seq_note"] = (
        "latest_receipt_seq is the highest receipt number issued under this "
        "name. A holder whose own highest receipt is lower than this has not "
        "received one of them, and can say exactly how many. Public on "
        "purpose - a gap you can only see from the inside is not evidence of "
        "anything.")
    if state == "bound":
        out["meaning"] = ("A live credential exists for this name, and every "
                          "submission under it carries a signature made with "
                          "that credential. A submission establishes that "
                          "SOMEONE holding the secret sent it - not which "
                          "holder, and not that the holder is the party the "
                          "name names.")
        out["secret_scope"] = SECRET_SCOPE
    elif state == "claimed":
        out["meaning"] = ("Claimed but not bound. The dated claim above is in "
                          "the chain, so a competing submission would be "
                          "provably later - but nothing prevents one being "
                          "made. Issue a credential to close that.")
        out["flag"] = "claimable"
    else:
        out["meaning"] = ("Nobody holds a credential for this name and nobody "
                          "has claimed it. It is claimable by anyone.")
        out["flag"] = "claimable"
    out["what_binding_never_proves"] = (
        "domain ownership. A credential is a shared secret; it makes a name "
        "unstealable by a third party on this network, not a claim honest, "
        "and not unsubmittable by the operator.")
    return out, 200


def _conflicts(ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT claimant) FROM bind_claim "
            "GROUP BY name HAVING COUNT(DISTINCT claimant) > 1").fetchall()
        keys = ctx["conn"].execute(
            "SELECT name, COUNT(DISTINCT key_id) FROM bind_credential "
            "WHERE revoked IS NULL GROUP BY name "
            "HAVING COUNT(DISTINCT key_id) > 1").fetchall()
    return {"contested_claims": [{"name": r[0], "claimants": r[1]} for r in rows],
            "names_with_multiple_live_credentials":
                [{"name": k[0], "credentials": k[1]} for k in keys],
            "note": ("A conflict is recorded, not arbitrated. This platform "
                     "does not decide who owns a name and should not.")}, 200


def _spec(ctx):
    return {
        "bind_version": VERSION,
        "why_it_exists": ("Name binding used to depend on a fetcher reaching a "
                          "URL and parsing JSON. A reachable page serving HTML "
                          "did not bind, an unbound name was claimable by "
                          "anyone, and the failure text asserted the URL was "
                          "unreachable when the check had only established the "
                          "response was not JSON. This lane removes the fetcher "
                          "from the trust path."),
        "signing": {
            "material": "AILEASH-BIND-v1: || canonical JSON of "
                        "{name, tip, ts, nonce}, keys sorted, separators "
                        "(',',':'), UTF-8",
            "algorithm": "HMAC-SHA256, secret as raw bytes from the hex issued",
            "signature": "lower-case hex digest",
            "ts": "unix seconds, must be within %d seconds of ours" % CLOCK_SKEW,
            "nonce": "any string, once only, remembered for %d seconds"
                     % NONCE_KEEP,
        },
        "worked_example": {
            "1": "material = b'AILEASH-BIND-v1:' + "
                 '\'{"name":"example.com","nonce":"abc123",'
                 '"tip":"<64 hex>","ts":1787000000}\'.encode()',
            "2": "signature = hmac.new(bytes.fromhex(secret), material, "
                 "hashlib.sha256).hexdigest()",
            "3": "POST /x/bind/submit with name, tip, ts, nonce, key_id, signature",
            "note": "the JSON in step 1 has its keys sorted, which is why "
                    "nonce appears before tip",
        },
        "secret_scope": SECRET_SCOPE,
        "block_indices": dict(
            EPOCH_VOCABULARY,
            current_chain_epoch=_genesis(ctx),
            shape="Every index is published as an object - block_index, "
                  "chain_epoch, epoch_state, current_chain_epoch - never as "
                  "a bare number. A bare number cannot be checked for "
                  "staleness by whoever receives it.",
            rows_before_1_2_0="Recorded without an epoch and published as "
                              "unknown. No epoch is assigned to them now: "
                              "guessing one would be the same fault the "
                              "field exists to prevent.",
        ),
        "on_acceptance": {
            "receipt_seq": ("An integer, never null, incremented by exactly "
                            "one for each accepted submission UNDER THIS NAME "
                            "on this lane. Issued inside the same lock that "
                            "writes the record. Two receipts numbered N and "
                            "N+2 prove a third exists that you did not "
                            "receive. The current highest is published at "
                            "/x/bind/name."),
            "receipt_seq_scope": {
                "values": ["per-peer", "per-name", "per-chain"],
                "per-peer": "issued per registered peer_id. /x/peer/submit.",
                "per-name": "issued per bound name. /x/bind/submit.",
                "per-chain": "issued per enrolled chain name. /x/signed/submit.",
                "why_it_is_here": "The three signed lanes each count within "
                                  "their own scope, so a receipt carries the "
                                  "scope of its own sequence. The set is "
                                  "closed: a value outside this list is an "
                                  "error on our side.",
                "not_comparable_across_scopes": "Two receipts with different "
                                                "scopes are counting different "
                                                "things.",
            },
            "sealed_at": ("Where the submission landed in the chain, as an "
                          "epoch-qualified reference rather than a bare "
                          "index. See block_indices."),
            "key_seq": ("The server-wide per-API-key sequence, null on this "
                        "lane and always will be. That counter lives on an "
                        "api_key and this lane authenticates by signature "
                        "with no key to count against. Returned rather than "
                        "omitted so the absence is visible."),
            "sequence_survives_rotation": ("Reissuing or revoking a credential "
                                           "does not reset the sequence, so a "
                                           "rotation cannot be used to erase a "
                                           "gap."),
            "seal_failure": ("If the audit chain does not seal your "
                             "submission, you get 500 seal_failed and nothing "
                             "is recorded - no nonce, no sequence number, no "
                             "receipt. Resend the identical submission once "
                             "the fault is fixed."),
        },
        "what_a_signed_binding_proves": (
            "that a holder of the credential issued for that name submitted, "
            "and that the submission is unaltered since signing"),
        "what_it_does_not_prove": [
            "which holder. The secret is shared, so this does not exclude the "
            "operator or anyone it has been disclosed to.",
            "domain ownership - not checked, not implied",
            "that the submitter is who the name suggests",
            "that anything in their chain is true",
        ],
        "claims": ("A name with no credential can be given a dated claim "
                   "marker. That is not a binding. It means a later competing "
                   "submission is provably second and the conflict is public."),
        "conflicts": ("Recorded at /x/bind/conflicts and never arbitrated here. "
                      "A network that lets its operator decide who owns a name "
                      "has replaced one trusted party with another."),
        "honest_limits": [
            "A credential is a shared secret. This platform holds a copy, so "
            "in principle it could sign on a peer's behalf - which is why the "
            "public-key lane at /x/signed/enroll is the right end state and "
            "this is the interim.",
            "A secret that has been screenshotted, pasted into another tool or "
            "shown to a colleague is held by more parties than two, and this "
            "lane cannot tell them apart. Revoke and reissue, or move to the "
            "key lane.",
            "Revoking a credential stops future submissions and does not "
            "unbind past ones.",
            "An index recorded before 1.2.0 cannot be resolved against this "
            "chain and will never be resolvable. The epoch it was issued "
            "under was not recorded and cannot honestly be reconstructed.",
            "Nothing here checks DNS, TLS or WHOIS.",
            "receipt_seq proves you are missing a receipt. It does not prove "
            "why, and cannot distinguish a lost response from one never sent.",
        ],
        "changed_in_1_2_0": [
            "Block indices now travel with the genesis hash of the chain "
            "they were issued under, and every route publishing one reports "
            "whether that epoch is current, retired or unknown. Before this, "
            "an index issued under the pre-7-September chain was published "
            "as a bare number; once the chain grew past it, it resolved to a "
            "real, correctly-sealed block belonging to a different party. A "
            "dangling pointer is visibly broken - a pointer that resolves to "
            "someone else's record is not. Raised by Ishaan (Shango MID).",
            "Rows written before this version have no epoch and publish as "
            "unknown, marked unresolvable against this chain. They are not "
            "backfilled.",
            "The sealing path is unchanged except that chain_epoch now "
            "appears in the sealed result of new blocks.",
        ],
        "changed_in_1_1_2": [
            "The bound-state text no longer says only the holder can submit. "
            "SECRET_SCOPE appears wherever a secret is issued, used or "
            "reported. Raised by Ishaan (Shango MID).",
        ],
        "changed_in_1_1_1": [
            "receipt_seq_scope is a bare token from a closed set. Asked for "
            "by Philip Pinol (PRAXIS).",
        ],
        "changed_in_1_1": [
            "receipt_seq is a real per-name gapless sequence issued by this "
            "module, not the api_key counter that was always null here.",
            "A failed seal returns 500 and records nothing.",
        ],
    }, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec(ctx)
        if action == "name":
            return _name(ctx, data)
        if action == "conflicts":
            return _conflicts(ctx)

    if method == "POST":
        if action == "submit":
            return _submit(ctx, data)
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "issue":
            return _issue(ctx, api_key, data)
        if action == "claim":
            return _claim(ctx, api_key, data)
        if action == "revoke":
            return _revoke(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "name", "conflicts"],
            "POST": ["issue", "claim", "revoke", "submit"]}, 404

```


## `modules/binddesk.py`

312 lines, 13381 bytes

```python
#!/usr/bin/env python3
"""
modules/binddesk.py  -  buttons for the signed lane

modules/bind.py is the engine. It answers POST requests with a key, which is
correct and completely unusable from a phone: a browser address bar can only
send GET, and nothing in it can attach an Authorization header.

So this is the page. Paste the key once, tap a button. Same routes underneath,
nothing new in the trust path.

Served at /bind-desk by the same runtime do_GET patch console.py uses. The
page holds nothing - the key is typed in, kept in the tab, and sent on each
request. Every route it calls checks that key itself.

PUBLIC is empty. Nothing here is reachable without a key except the page
itself, and the page is inert until one is pasted into it.
"""

import sys

VERSION = "1.1"

# ("GET", "status") is public on purpose. The page is installed by a runtime
# patch that only runs once this module is touched, and every other route here
# needs a key - which locked the operator out of their own page, because a
# browser cannot send an Authorization header. The status route reveals only
# that the desk exists and where the page is.
PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/bind-desk", "/bind-desk.html", "/binddesk")
_patched = [False]


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>Bind desk</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0f1e;color:#e8ecf5;font-family:ui-monospace,Menlo,monospace;
 font-size:14px;line-height:1.55;padding:0 0 80px}
.w{max-width:620px;margin:0 auto;padding:22px 16px}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;margin-bottom:4px}
.sub{color:#6b7894;font-size:12.5px;margin-bottom:22px}
h2{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#c9a84c;
 margin:0 0 12px}
label{display:block;font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#6b7894;margin:12px 0 6px}
input{width:100%;background:#131b2e;border:1px solid #223052;color:#e8ecf5;
 font-family:inherit;font-size:14px;padding:12px;border-radius:4px;outline:none}
input:focus{border-color:#c9a84c}
button{width:100%;background:#c9a84c;color:#0a0f1e;border:0;border-radius:4px;
 padding:14px;font-family:inherit;font-weight:700;font-size:14px;margin-top:12px;
 cursor:pointer}
button:active{opacity:.8}
button.q{background:transparent;color:#8f98ad;border:1px solid #223052;font-weight:400}
button.danger{background:transparent;color:#ff8a80;border:1px solid #4a2422;font-weight:400}
.card{background:#131b2e;border:1px solid #223052;border-radius:7px;
 padding:18px;margin:16px 0}
.note{color:#6b7894;font-size:11.5px;line-height:1.6;margin-top:10px}
.out{margin-top:12px;font-size:12px;white-space:pre-wrap;word-break:break-all;
 background:#080c16;border:1px solid #223052;border-radius:4px;padding:12px;
 max-height:320px;overflow:auto}
.ok{color:#7fe3b0}.bad{color:#ff8a80}.warn{color:#c9a84c}
.secret{background:#0f1c15;border:1px solid #2c5c44;border-radius:5px;
 padding:14px;margin-top:12px}
.secret .lbl{font-size:10px;letter-spacing:.16em;text-transform:uppercase;
 color:#7fe3b0;margin-bottom:6px}
.secret .val{font-size:13px;color:#7fe3b0;word-break:break-all;line-height:1.8}
.secret .warnline{color:#c9a84c;font-size:11.5px;margin-top:10px;line-height:1.6}
.step{display:inline-block;background:#223052;color:#8f98ad;border-radius:3px;
 padding:2px 8px;font-size:11px;margin-bottom:10px}
</style></head><body><div class="w">

<h1>Bind desk</h1>
<p class="sub">Names on the witness network. Your key stays in this tab.</p>

<div class="card">
  <label for="k">Your API key</label>
  <input id="k" type="password" placeholder="paste it here" autocomplete="off">
  <p class="note">Typed once, used by every button below. Nothing is stored.</p>
</div>

<div class="card">
  <span class="step">STEP 1</span>
  <h2>Claim a name</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">Puts a dated marker in
  the chain. Does not stop anyone else submitting — but theirs is provably
  later. Do this first if the name is exposed.</p>
  <label for="cn">Name</label>
  <input id="cn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="cc">Who is claiming it</label>
  <input id="cc" placeholder="Ishaan">
  <label for="cnote">Note (optional)</label>
  <input id="cnote" placeholder="pending credential">
  <button onclick="doClaim()">Seal the claim</button>
  <div id="o-claim"></div>
</div>

<div class="card">
  <span class="step">STEP 2</span>
  <h2>Issue a credential</h2>
  <p class="note" style="margin-top:0;margin-bottom:4px">This is the real fix.
  Once issued, only the holder of the secret can submit under that name.</p>
  <label for="in">Name</label>
  <input id="in" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <label for="ito">Issued to</label>
  <input id="ito" placeholder="Ishaan">
  <button onclick="doIssue(false)">Issue it</button>
  <button class="q" onclick="doIssue(true)">Replace the existing one</button>
  <div id="o-issue"></div>
</div>

<div class="card">
  <h2>Check a name</h2>
  <label for="qn">Name</label>
  <input id="qn" placeholder="shango.in" autocapitalize="off" autocorrect="off">
  <button class="q" onclick="doLook()">Look it up</button>
  <button class="q" onclick="doConflicts()">Show every contested name</button>
  <div id="o-look"></div>
</div>

<div class="card">
  <h2>Revoke a credential</h2>
  <label for="rk">Key id</label>
  <input id="rk" placeholder="bk_..." autocapitalize="off" autocorrect="off">
  <label for="rr">Reason</label>
  <input id="rr" placeholder="rotating">
  <button class="danger" onclick="doRevoke()">Revoke</button>
  <p class="note">Stops future submissions. Anything already bound stays bound.</p>
  <div id="o-revoke"></div>
</div>

</div>
<script>
var $=function(i){return document.getElementById(i)};
function key(){var k=$('k').value.trim();return k||null}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function show(id,cls,txt){$(id).innerHTML='<div class="out '+cls+'">'+esc(txt)+'</div>'}
function shown(id,html){$(id).innerHTML=html}

async function call(path,method,body){
  var k=key();
  if(!k){return {status:0,data:{error:'paste your key at the top first'}}}
  var o={method:method,headers:{'Authorization':'Bearer '+k}};
  if(body){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body)}
  try{
    var r=await fetch(path,o);
    var d; try{d=await r.json()}catch(e){d={error:'unreadable response'}}
    return {status:r.status,data:d};
  }catch(e){return {status:0,data:{error:'could not reach the server'}}}
}

async function doClaim(){
  var n=$('cn').value.trim(), c=$('cc').value.trim();
  if(!n||!c){show('o-claim','bad','Fill in the name and who is claiming it.');return}
  show('o-claim','','Sealing...');
  var r=await call('/x/bind/claim','POST',{name:n,claimant:c,note:$('cnote').value.trim()});
  if(r.status!==200){show('o-claim','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-claim','ok','CLAIMED\\n\\nname     '+r.data.name
    +'\\nclaimant '+r.data.claimant
    +'\\nsealed   '+r.data.sealed_in_chain
    +'\\nblock    '+r.data.block_index
    +'\\n\\nThis is a dated marker, not a binding. Do step 2.');
}

async function doIssue(replace){
  var n=$('in').value.trim(), t=$('ito').value.trim();
  if(!n){show('o-issue','bad','Enter the name.');return}
  show('o-issue','','Issuing...');
  var r=await call('/x/bind/issue','POST',{name:n,issued_to:t,replace:!!replace});
  if(r.status===409){
    show('o-issue','warn','A credential already exists for '+n
      +'.\\n\\nUse "Replace the existing one" if you mean to revoke it and issue another.');
    return;
  }
  if(r.status!==200){show('o-issue','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  shown('o-issue','<div class="secret">'
    +'<div class="lbl">send both of these to them privately</div>'
    +'<div class="val">key_id&nbsp;&nbsp;'+esc(r.data.key_id)+'</div>'
    +'<div class="val">secret&nbsp;&nbsp;'+esc(r.data.secret)+'</div>'
    +'<div class="warnline">The secret is shown here once and is not stored '
    +'anywhere. Copy it now. If it is lost you have to revoke and reissue.</div>'
    +'<div class="warnline">Do not send it over LinkedIn or anywhere public.</div>'
    +'</div>'
    +'<div class="out ok">sealed  '+esc(r.data.sealed_in_chain)
    +'\\nblock   '+esc(r.data.block_index)+'</div>');
}

async function doLook(){
  var n=$('qn').value.trim();
  if(!n){show('o-look','bad','Enter a name.');return}
  show('o-look','','Looking...');
  var r=await call('/x/bind/name?name='+encodeURIComponent(n),'GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'not found');return}
  var d=r.data;
  var cls = d.state==='bound' ? 'ok' : 'warn';
  var t='STATE   '+d.state.toUpperCase()+'\\n\\n'+d.meaning+'\\n';
  if(d.credential){t+='\\nkey_id     '+d.credential.key_id
    +'\\nissued to  '+(d.credential.issued_to||'-')
    +'\\nissued at  '+d.credential.issued_at;}
  if(d.claims&&d.claims.length){t+='\\n\\nCLAIMS';
    d.claims.forEach(function(c){t+='\\n  '+c.claimant+'  '+c.claimed_at
      +'  block '+c.block_index;});}
  if(d.signed_submissions&&d.signed_submissions.length){
    t+='\\n\\nSIGNED SUBMISSIONS  '+d.signed_submissions.length;
    d.signed_submissions.slice(0,5).forEach(function(s){
      t+='\\n  '+s.at+'  block '+s.block_index;});}
  show('o-look',cls,t);
}

async function doConflicts(){
  show('o-look','','Checking...');
  var r=await call('/x/bind/conflicts','GET');
  if(r.status!==200){show('o-look','bad',r.data.error||'failed');return}
  var d=r.data, t='';
  if(!d.contested_claims.length && !d.names_with_multiple_live_credentials.length){
    t='No contested names.';
  } else {
    d.contested_claims.forEach(function(c){t+='CONTESTED  '+c.name+'  ('+c.claimants+' claimants)\\n'});
    d.names_with_multiple_live_credentials.forEach(function(c){
      t+='MULTIPLE CREDENTIALS  '+c.name+'  ('+c.credentials+')\\n'});
  }
  show('o-look', t==='No contested names.'?'ok':'warn', t+'\\n\\n'+d.note);
}

async function doRevoke(){
  var k=$('rk').value.trim();
  if(!k){show('o-revoke','bad','Enter the key id.');return}
  show('o-revoke','','Revoking...');
  var r=await call('/x/bind/revoke','POST',{key_id:k,reason:$('rr').value.trim()});
  if(r.status!==200){show('o-revoke','bad',r.data.error||JSON.stringify(r.data,null,1));return}
  show('o-revoke','ok','REVOKED\\n\\nname    '+r.data.name
    +'\\nkey_id  '+r.data.key_id
    +'\\nsealed  '+r.data.sealed_in_chain
    +'\\n\\n'+r.data.note);
}
</script></body></html>"""


def _install():
    if _patched[0]:
        return "already installed"
    m = sys.modules.get("__main__")
    srv = m if (m is not None and hasattr(m, "get_bearer")) else sys.modules.get("server")
    if srv is None:
        return "no server"
    H = getattr(srv, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_binddesk_patched", False):
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
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Robots-Tag", "noindex, nofollow")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._binddesk_patched = True
    _patched[0] = True
    print("BINDDESK: /bind-desk installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    state = _install()
    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {"binddesk_version": VERSION,
                "installed": bool(_patched[0]),
                "install_result": state,
                "page": "/bind-desk",
                "engine": "/x/bind/spec",
                "what_it_does": ("Buttons for the signed lane. Claim a name, "
                                 "issue a credential, look one up, revoke one. "
                                 "The page sends the same POST requests the "
                                 "engine already accepts."),
                "note": "The page is not public in any useful sense - it is "
                        "inert until a key is pasted into it, and every route "
                        "it calls checks that key."}, 200

    if not api_key:
        return {"error": "invalid_api_key",
                "note": "Use the page at /bind-desk."}, 401

    return {"error": "unknown_action", "GET": ["status"]}, 404

```


## `modules/blocks.py`

397 lines, 15562 bytes

```python
"""
modules/blocks.py  v1.0.1
=========================
Paged reads of the audit chain, for the command centre.

WHY THIS EXISTS
---------------
/admin/audit calls verify_chain() on every single request. That rewalks and
rehashes every block in the chain while holding the database lock, so the
cost of asking for twenty rows is the cost of re-verifying the whole log.
On a single replica that hold is long enough for Railway to decide the app
has stopped responding, and the container gets killed -- which also wipes
the in-memory admin tokens, so the next call comes back 401.

This module does the one thing the block view actually needs: read rows.
No verification, no rehashing, no full-table walk. Verification stays where
it belongs, on its own route, run deliberately.

WHAT IT ADDS
------------
offset. /admin/audit has no offset and caps at 1000, so nothing older than
the newest thousand blocks could ever be reached. This pages through the
entire chain, oldest to newest or newest to oldest, in small bites.

v1.0.1 -- THE COMMENT WAS WRONG, SO THE CODE IS NOW RIGHT
---------------------------------------------------------
v1.0 said column names were read from the live schema so a future ALTER TABLE
could not silently break it. They were not. The SELECT was hardcoded and rows
were unpacked by position, r[0] through r[5], with the discovered column set
passed into the row shaper and never used. Renaming or reordering a column
would have 500'd every route.

Now it genuinely does what it said: PRAGMA table_info picks the real column
names once, each candidate is resolved against what actually exists, rows come
back as dicts keyed by name, and a missing column is reported in /status
instead of surfacing as a query error later. Same discipline complete.py uses.

ROUTES
------
  GET  /x/blocks/status                       module state, row count, schema
  GET  /x/blocks/list?limit=&offset=&order=   a page of blocks
  GET  /x/blocks/get?seq=                     one block in full
  GET  /x/blocks/around?seq=&span=            a window either side of a block
  GET  /x/blocks/links?limit=&offset=         link check over a page only
  GET  /x/blocks/spec                         what this serves

Every route is keyed. Audit rows are not public.

LINK CHECKING
-------------
/links checks prev_hash against the preceding row's audit_hash across the
page you asked for, and nothing else. It reports which pairs it compared so
a caller can never mistake a clean page for a clean chain. Whole-chain
verification is /api/verify-chain and is deliberately not duplicated here.
"""

import json

VERSION = "1.0.1"

# Nothing here is public. Audit rows are customer data.
PUBLIC = set()

MAX_LIMIT = 200          # a page, not a dump
DEFAULT_LIMIT = 50
MAX_SPAN = 100

# What this module needs, and the column names it will accept for each. The
# first name that exists in the live table wins. Nothing is assumed.
WANTED = {
    "seq": ["id", "rowid", "block_index", "seq"],
    "ts": ["ts", "timestamp", "created", "time"],
    "user_id": ["user_id", "subject", "customer_id"],
    "result": ["result_json", "result", "payload", "event_json"],
    "prev_hash": ["prev_hash", "previous_hash", "prev"],
    "audit_hash": ["audit_hash", "hash", "seal"],
}

_schema = {"resolved": None, "missing": None, "columns": None}


def _ctx_get(ctx, name):
    """ctx may be an object with attributes or a plain dict, depending on how
    the router builds it. Take either rather than assuming."""
    v = getattr(ctx, name, None)
    if v is None and isinstance(ctx, dict):
        v = ctx.get(name)
    return v


class _NoLock(object):
    """Used only if the router hands us no lock, so a missing lock degrades
    to running without one instead of raising on entry."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _one(v):
    """A query value can arrive as a string or as a one-item list, depending
    on how the querystring was parsed. Take either."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else ""
    return v


def _cols(conn):
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()]
    except Exception:
        return []


def _resolve(conn):
    """Work out, once, which real column serves each role. Cached because the
    schema does not change between requests, re-derived if it ever comes back
    empty so a transient failure does not stick."""
    if _schema["resolved"]:
        return _schema["resolved"], _schema["missing"]
    cols = _cols(conn)
    lower = {c.lower(): c for c in cols}
    resolved, missing = {}, []
    for role, candidates in WANTED.items():
        hit = None
        for cand in candidates:
            if cand.lower() in lower:
                hit = lower[cand.lower()]
                break
        if hit:
            resolved[role] = hit
        else:
            missing.append(role)
    if resolved:
        _schema["resolved"] = resolved
        _schema["missing"] = missing
        _schema["columns"] = cols
    return resolved, missing


def _select(resolved, roles):
    """Build a SELECT from real column names, aliased to the role names, so
    rows come back keyed by role and never by position."""
    parts = ["%s AS %s" % (resolved[r], r) for r in roles if r in resolved]
    return "SELECT " + ",".join(parts) + " FROM audit_log"


def _dicts(cur):
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _int(data, name, default, lo, hi):
    try:
        v = int(_one(data.get(name, default)))
    except Exception:
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _str(data, name, default=""):
    v = _one(data.get(name, default))
    return "" if v is None else str(v).strip()


def _shape(d):
    """One row, from a dict keyed by role. Missing roles come back as None
    rather than raising, so a partial schema degrades instead of failing."""
    out = {
        "seq": d.get("seq"),
        "ts": d.get("ts"),
        "user_id": d.get("user_id"),
        "prev_hash": d.get("prev_hash"),
        "audit_hash": d.get("audit_hash"),
    }
    raw = d.get("result")
    try:
        res = json.loads(raw) if raw else {}
    except Exception:
        res = {}
    if isinstance(res, dict):
        out["decision"] = res.get("decision", res.get("result", ""))
        out["score"] = res.get("score", "")
        rs = res.get("reasons", [])
        out["reasons"] = rs if isinstance(rs, list) else ([str(rs)] if rs else [])
    else:
        out["decision"] = ""
        out["score"] = ""
        out["reasons"] = []
    return out


ROLES = ["seq", "ts", "user_id", "result", "prev_hash", "audit_hash"]


def handle(method, action, data, api_key, ctx):
    if not isinstance(data, dict):
        data = {}

    conn = _ctx_get(ctx, "conn")
    lock = _ctx_get(ctx, "lock") or _NoLock()
    if conn is None:
        return {"error": "no database handle on ctx",
                "ctx_type": type(ctx).__name__}, 500

    with lock:
        resolved, missing = _resolve(conn)
    if not resolved or "seq" not in resolved or "audit_hash" not in resolved:
        return {"error": "audit_log schema not recognised",
                "columns_found": _schema.get("columns") or _cols(conn),
                "roles_missing": missing,
                "note": ("This module maps roles onto real column names. Add the "
                         "actual name to WANTED rather than assuming a shape.")}, 500

    SEL = _select(resolved, ROLES)
    idc = resolved["seq"]
    hashc = resolved["audit_hash"]
    prevc = resolved.get("prev_hash")

    # ---------------------------------------------------------------- status
    if action == "status":
        with lock:
            try:
                n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
                lo = conn.execute("SELECT MIN(%s) FROM audit_log" % idc).fetchone()[0]
                hi = conn.execute("SELECT MAX(%s) FROM audit_log" % idc).fetchone()[0]
            except Exception as e:
                return {"error": "audit_log unreadable: " + str(e)}, 500
        return {
            "module": "blocks",
            "version": VERSION,
            "rows": n,
            "lowest_seq": lo,
            "highest_seq": hi,
            "schema_columns": _schema.get("columns"),
            "role_mapping": resolved,
            "roles_missing": missing,
            "has_api_key_column": "api_key" in [c.lower() for c in (_schema.get("columns") or [])],
            "max_limit": MAX_LIMIT,
            "note": "reads only. no chain verification happens on this route.",
        }, 200

    # ------------------------------------------------------------------ list
    if action == "list":
        limit = _int(data, "limit", DEFAULT_LIMIT, 1, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        order = _str(data, "order", "desc").lower()
        order = "ASC" if order == "asc" else "DESC"
        filt = _str(data, "api_key", "")
        has_key_col = "api_key" in [c.lower() for c in (_schema.get("columns") or [])]

        with lock:
            try:
                if filt and has_key_col:
                    cur = conn.execute(
                        SEL + " WHERE api_key=? ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (filt, limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute(
                        "SELECT COUNT(*) FROM audit_log WHERE api_key=?", (filt,)).fetchone()[0]
                else:
                    cur = conn.execute(
                        SEL + " ORDER BY %s %s LIMIT ? OFFSET ?" % (idc, order),
                        (limit, offset))
                    recs = [_shape(d) for d in _dicts(cur)]
                    total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            except Exception as e:
                return {"error": "query failed: " + str(e)}, 500

        return {
            "blocks": recs,
            "count": len(recs),
            "total": total,
            "limit": limit,
            "offset": offset,
            "order": order.lower(),
            "has_more": (offset + len(recs)) < total,
            "next_offset": offset + len(recs),
            "filtered_by_key": bool(filt and has_key_col),
            "filter_ignored": bool(filt and not has_key_col) or None,
        }, 200

    # ------------------------------------------------------------------- get
    if action == "get":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        with lock:
            cur = conn.execute(SEL + " WHERE %s=?" % idc, (seq,))
            rows = _dicts(cur)
            if not rows:
                return {"error": "no block with that seq", "seq": seq}, 404
            below = conn.execute(
                "SELECT %s,%s FROM audit_log WHERE %s<? ORDER BY %s DESC LIMIT 1"
                % (idc, hashc, idc, idc), (seq,)).fetchone()
        block = _shape(rows[0])
        if below and prevc:
            block["links_to"] = below[0]
            block["link_holds"] = (str(block.get("prev_hash") or "") == str(below[1] or ""))
            block["expected_prev"] = below[1]
        elif not prevc:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "this table has no prev_hash column, so no link can be checked"
        else:
            block["links_to"] = None
            block["link_holds"] = None
            block["note"] = "oldest row in the table; nothing beneath it to link to"
        return {"block": block}, 200

    # ---------------------------------------------------------------- around
    if action == "around":
        try:
            seq = int(_one(data.get("seq", 0)))
        except Exception:
            return {"error": "seq must be a number"}, 400
        span = _int(data, "span", 10, 1, MAX_SPAN)
        with lock:
            cur = conn.execute(
                SEL + " WHERE %s BETWEEN ? AND ? ORDER BY %s DESC" % (idc, idc),
                (seq - span, seq + span))
            rows = _dicts(cur)
        return {
            "centre": seq,
            "span": span,
            "blocks": [_shape(d) for d in rows],
        }, 200

    # ----------------------------------------------------------------- links
    if action == "links":
        if not prevc:
            return {"error": "no prev_hash column in this table",
                    "note": "there is no link to check without one"}, 400
        limit = _int(data, "limit", DEFAULT_LIMIT, 2, MAX_LIMIT)
        offset = _int(data, "offset", 0, 0, 10000000)
        with lock:
            rows = conn.execute(
                "SELECT %s,%s,%s FROM audit_log ORDER BY %s DESC LIMIT ? OFFSET ?"
                % (idc, prevc, hashc, idc), (limit, offset)).fetchall()
        broken = []
        for i in range(len(rows) - 1):
            newer, older = rows[i], rows[i + 1]
            if str(newer[1] or "") != str(older[2] or ""):
                broken.append({
                    "between": newer[0],
                    "and": older[0],
                    "expected_prev": older[2],
                    "found_prev": newer[1],
                })
        checked = max(0, len(rows) - 1)
        return {
            "pairs_checked": checked,
            "broken": broken,
            "clean": len(broken) == 0,
            "range": {"newest_seq": rows[0][0] if rows else None,
                      "oldest_seq": rows[-1][0] if rows else None},
            "scope": ("this page only. a clean page is not a clean chain — "
                      "whole-chain verification is /api/verify-chain"),
        }, 200

    # ------------------------------------------------------------------ spec
    if action == "spec":
        return {
            "module": "blocks",
            "version": VERSION,
            "purpose": ("paged reads of audit_log for the operator block view, "
                        "without re-verifying the whole chain on every request"),
            "auth": "every route requires a key",
            "schema_handling": ("column names are resolved against PRAGMA "
                                "table_info at first use and rows are read by "
                                "name, so a renamed column is reported in "
                                "/status rather than breaking a query"),
            "role_mapping": resolved,
            "routes": {
                "GET status": "row count, lowest and highest seq, resolved column names",
                "GET list": "limit (max %d), offset, order=asc|desc, api_key" % MAX_LIMIT,
                "GET get": "seq — one block, plus whether its link to the row below holds",
                "GET around": "seq, span (max %d) — a window either side" % MAX_SPAN,
                "GET links": "limit, offset — link check across that page only",
            },
            "deliberately_not_here": [
                "whole-chain verification — that is /api/verify-chain",
                "writes of any kind",
                "any public route",
            ],
        }, 200

    return {"error": "unknown_action", "action": action,
            "available": ["GET status", "GET list", "GET get",
                          "GET around", "GET links", "GET spec"]}, 404

```


## `modules/brand.py`

217 lines, 8075 bytes

```python
"""
modules/brand.py  v1.0.0  -  one brand on every page: Monop Content

    Arm:  https://sebbi.pro/x/brand/status   (also armed by /x/arm/status)

The pages carry the founder's name and town in footers, taglines, buttons and
form placeholders. This presents them as Monop Content instead, without
editing a single page file: every HTML response is rewritten on its way out
of the server, whichever file or module produced it.

HOW
---
It wraps the request handler's handle_one_request, so it sits outside every
page patch whatever order modules were armed in. The response is held only
until its headers show what it is: anything that is not HTML (JSON, images,
video, downloads, event streams) is passed straight through untouched and
unbuffered. HTML is rewritten and its Content-Length corrected.

LEFT AS THEY ARE, ON PURPOSE
----------------------------
  /terms, /data-protection, /risk-policy, /human-oversight   the law and auditors
      expect the privacy notice and policies to name who is responsible
  /investor-prospectus                                investors expect the founder
  /admin, /console and other operator screens         your own tools

To switch it off without a deploy: https://sebbi.pro/x/brand/off
(back on with /x/brand/on). Both need your API key.
"""

import sys
import threading

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec")}

# Longest and most specific first, so a shorter rule never splits a longer one.
RULES = [
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, Northumberland, UK &middot; ",
     "&copy; 2026 Monop Content &middot; "),
    ("&copy; 2026 Monop Content &middot; Justin Antony Dobson &middot; Blyth, UK", "&copy; 2026 Monop Content"),
    ("built by Monop Content in Blyth, United Kingdom", "built by Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content · Blyth, Northumberland, UK", "Monop Content"),
    ("Monop Content &middot; Blyth, Northumberland", "Monop Content"),
    ("Monop Content &middot; Blyth, UK", "Monop Content"),
    ("Monop Content · Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth, UK", "Monop Content"),
    ("Monop Content, Blyth", "Monop Content"),
    (" &middot; Blyth, Northumberland, UK", ""),
    (" &middot; Blyth, UK", ""),
    (" · Blyth, UK", ""),
    (" &middot; Justin Antony Dobson", ""),
    (" · Justin Antony Dobson", ""),
    ("Contact Justin at Monop Content", "Contact Monop Content"),
    ("Contact Justin", "Contact us"),
    ("talk to Justin", "talk to us"),
    ("Justin has been notified", "Our team has been notified"),
    ('placeholder="Justin Antony Dobson"', 'placeholder="Your full name"'),
    ('placeholder="Justin"', 'placeholder="First name"'),
    ("Building tamper-evident AI compliance from Blyth.", "Building tamper-evident AI compliance."),
]
RULES_B = [(a.encode("utf-8"), b.encode("utf-8")) for a, b in RULES]

SKIP_PATHS = ("/terms", "/data-protection", "/risk-policy", "/human-oversight", "/investor-prospectus",
              "/admin", "/console", "/peers", "/pack", "/lineage-desk")

_state = {"installed": False, "on": True, "rewritten": 0, "replacements": 0, "last_error": None}
_lock = threading.Lock()


def rewrite(body):
    n = 0
    for old, new in RULES_B:
        if old in body:
            n += body.count(old)
            body = body.replace(old, new)
    return body, n


class _Out(object):
    """Stands in for wfile for one request. Passes non-HTML straight through."""

    def __init__(self, real):
        self.real = real
        self.buf = bytearray()
        self.mode = None  # None = reading headers, "pass", "html"

    def write(self, data):
        if self.mode == "pass":
            return self.real.write(data)
        self.buf += data
        if self.mode is None:
            end = self.buf.find(b"\r\n\r\n")
            if end < 0:
                if len(self.buf) > 65536:
                    self._go_pass()
                return len(data)
            head = bytes(self.buf[:end]).lower()
            if b"content-type: text/html" in head and b"content-encoding" not in head:
                self.mode = "html"
            else:
                self._go_pass()
        elif len(self.buf) > 8 * 1024 * 1024:
            self._go_pass()  # an enormous page is sent as it is rather than held
        return len(data)

    def _go_pass(self):
        self.mode = "pass"
        if self.buf:
            self.real.write(bytes(self.buf))
        self.buf = bytearray()

    def flush(self):
        if self.mode == "pass":
            try:
                self.real.flush()
            except Exception:
                pass

    @property
    def closed(self):
        return getattr(self.real, "closed", False)

    def __getattr__(self, name):
        return getattr(self.real, name)

    def finish(self):
        if self.mode == "pass" or not self.buf:
            return
        raw = bytes(self.buf)
        self.buf = bytearray()
        end = raw.find(b"\r\n\r\n")
        if self.mode != "html" or end < 0:
            self.real.write(raw)
            return
        head, body = raw[:end], raw[end + 4:]
        new_body, n = rewrite(body)
        if n:
            lines = head.split(b"\r\n")
            lines = [l for l in lines if not l.lower().startswith(b"content-length:")]
            lines.append(b"Content-Length: " + str(len(new_body)).encode())
            head = b"\r\n".join(lines)
            _state["rewritten"] += 1
            _state["replacements"] += n
        self.real.write(head + b"\r\n\r\n" + new_body)
        try:
            self.real.flush()
        except Exception:
            pass


def _handler_class():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return getattr(m, "Handler", None)


def _install():
    with _lock:
        if _state["installed"]:
            return True
        H = _handler_class()
        if H is None:
            return False
        if getattr(H, "_brand_patched", False):
            _state["installed"] = True
            return True
        original = H.handle_one_request

        def handle_one_request(self):
            if not _state["on"]:
                return original(self)
            real = self.wfile
            out = _Out(real)
            self.wfile = out
            try:
                original(self)
            finally:
                self.wfile = real
                try:
                    path = (getattr(self, "path", "") or "").split("?")[0]
                    if path.startswith(SKIP_PATHS) and out.mode == "html":
                        out.mode = "pass_html"
                        real.write(bytes(out.buf))
                        out.buf = bytearray()
                    out.finish()
                except Exception as e:
                    _state["last_error"] = str(e)[:200]
                    try:
                        if out.buf:
                            real.write(bytes(out.buf))
                    except Exception:
                        pass

        H.handle_one_request = handle_one_request
        H._brand_patched = True
        _state["installed"] = True
        return True


def handle(method, action, data, api_key, ctx):
    armed = _install()
    if action in ("off", "on"):
        if not api_key:
            return {"error": "api_key_required"}, 401
        _state["on"] = action == "on"
    if action == "spec":
        return {"module": "brand", "version": VERSION,
                "what": "Every HTML page presented as Monop Content, rewritten as it is served. No page file is edited.",
                "rules": [{"from": a, "to": b} for a, b in RULES],
                "left_as_they_are": list(SKIP_PATHS)}, 200
    return {"module": "brand", "version": VERSION, "armed": armed, "on": _state["on"],
            "pages_rewritten": _state["rewritten"], "replacements": _state["replacements"],
            "left_as_they_are": list(SKIP_PATHS), "last_error": _state["last_error"]}, 200

```
