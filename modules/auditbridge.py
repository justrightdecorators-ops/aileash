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
