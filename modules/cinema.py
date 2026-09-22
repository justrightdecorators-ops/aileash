"""
modules/cinema.py  v1.0.0
The sebbi.pro Cinema at /cinema. A spinning axle of screens, each a channel of
AI governance videos; robots in the audience; a screening room with a spinning
TV and a channel bar. Videos play from their original YouTube channels.
To add a permanent channel, add a line to CHANNELS in the page (base64 below
is generated from cinema.html); visitors can also add their own on their device.

Page module, same family as map.py and passportpage.py: a runtime do_GET
patch. Armed by /x/cinema/status after each deploy.
Everything is base64-embedded so no character can break the Python string.
"""

import base64
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPnNlYmJpLnBybyBDaW5lbWEg4oCUIEFJIGdvdmVybmFuY2Ugb24gZXZlcnkgc2NyZWVuPC90aXRsZT4KPG1ldGEgbmFtZT0i"
    "ZGVzY3JpcHRpb24iIGNvbnRlbnQ9IlNwaW4gdGhlIHNjcmVlbnMsIHBpY2sgYSBjaGFubmVsLCBhbmQgd2F0Y2ggQUkgZ292ZXJu"
    "YW5jZSBleHBsYWluZWQsIGluIHRoZSBzZWJiaS5wcm8gY2luZW1hLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xl"
    "YXBpcy5jb20vY3NzMj9mYW1pbHk9SUJNK1BsZXgrTW9ubzp3Z2h0QDQwMDs1MDAmZmFtaWx5PU5ld3NyZWFkZXI6b3Bzeix3Z2h0"
    "QDYuLjcyLDUwMCZkaXNwbGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzA1MDcwZjstLWlu"
    "azI6IzBkMTQyNDstLWdvbGQ6I2M5YTg0YzstLW9rOiM3ZmUzYjA7LS1ibHVlOiM4ZmQwZmY7LS1tdXRlOiM4YTkzYWR9Cip7Ym94"
    "LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3BhZGRpbmc6MDstd2Via2l0LXRhcC1oaWdobGlnaHQtY29sb3I6dHJhbnNwYXJl"
    "bnR9Cmh0bWwsYm9keXtoZWlnaHQ6MTAwJTtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAzMCUsIzEx"
    "MWEzMyAwJSwjMDUwNzBmIDcwJSk7Y29sb3I6I2U4ZWRmNztmb250LWZhbWlseTonSUJNIFBsZXggTW9ubycsdWktbW9ub3NwYWNl"
    "LG1vbm9zcGFjZTtvdmVyZmxvdzpoaWRkZW59Ci52aWV3e3Bvc2l0aW9uOmZpeGVkO2luc2V0OjA7ZGlzcGxheTpmbGV4O2ZsZXgt"
    "ZGlyZWN0aW9uOmNvbHVtbjthbGlnbi1pdGVtczpjZW50ZXI7dHJhbnNpdGlvbjpvcGFjaXR5IC42c30KLmhpZGRlbntvcGFjaXR5"
    "OjA7cG9pbnRlci1ldmVudHM6bm9uZX0KaGVhZGVye3dpZHRoOjEwMCU7cGFkZGluZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVh"
    "LWluc2V0LXRvcCkpIDE2cHggMDt0ZXh0LWFsaWduOmNlbnRlcn0KLmJyYW5ke2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11"
    "dGUpfS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KaDF7Zm9udC1mYW1pbHk6J05ld3NyZWFkZXIn"
    "LEdlb3JnaWEsc2VyaWY7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZTpjbGFtcCgyOHB4LDZ2dyw0NnB4KTttYXJnaW46NnB4IDAg"
    "MnB4O2JhY2tncm91bmQ6bGluZWFyLWdyYWRpZW50KDkwZGVnLCNjOWE4NGMsIzdmZTNiMCwjOGZkMGZmKTstd2Via2l0LWJhY2tn"
    "cm91bmQtY2xpcDp0ZXh0O2JhY2tncm91bmQtY2xpcDp0ZXh0O2NvbG9yOnRyYW5zcGFyZW50fQouc3Vie2ZvbnQtc2l6ZToxMS41"
    "cHg7Y29sb3I6dmFyKC0tbXV0ZSk7bGV0dGVyLXNwYWNpbmc6LjA2ZW19Ci8qIHRoZSBzcGlubmluZyBheGxlICovCi5zdGFnZXtm"
    "bGV4OjE7d2lkdGg6MTAwJTtwZXJzcGVjdGl2ZToxMTAwcHg7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtqdXN0aWZ5"
    "LWNvbnRlbnQ6Y2VudGVyO3RvdWNoLWFjdGlvbjpwYW4teX0KLnJpbmd7cG9zaXRpb246cmVsYXRpdmU7d2lkdGg6MjQwcHg7aGVp"
    "Z2h0OjE1MHB4O3RyYW5zZm9ybS1zdHlsZTpwcmVzZXJ2ZS0zZH0KLnNjcmVlbntwb3NpdGlvbjphYnNvbHV0ZTtpbnNldDowO2Jv"
    "cmRlci1yYWRpdXM6MTBweDtvdmVyZmxvdzpoaWRkZW47YmFja2dyb3VuZDojMGIxMjI0O2JvcmRlcjoxLjVweCBzb2xpZCByZ2Jh"
    "KDIwMSwxNjgsNzYsLjQ1KTtib3gtc2hhZG93OjAgMCAzMHB4IHJnYmEoMTQzLDIwOCwyNTUsLjE4KTtiYWNrZmFjZS12aXNpYmls"
    "aXR5OmhpZGRlbjtjdXJzb3I6cG9pbnRlcjt0cmFuc2l0aW9uOmJvcmRlci1jb2xvciAuM3MsYm94LXNoYWRvdyAuM3N9Ci5zY3Jl"
    "ZW4gaW1ne3dpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb3ZlcjtvcGFjaXR5Oi44NX0KLnNjcmVlbiAubGFie3Bv"
    "c2l0aW9uOmFic29sdXRlO2xlZnQ6MDtyaWdodDowO2JvdHRvbTowO3BhZGRpbmc6MThweCA5cHggN3B4O2ZvbnQtc2l6ZToxMC41"
    "cHg7YmFja2dyb3VuZDpsaW5lYXItZ3JhZGllbnQodHJhbnNwYXJlbnQscmdiYSg1LDcsMTUsLjkyKSl9Ci5zY3JlZW4gLmNoe3Bv"
    "c2l0aW9uOmFic29sdXRlO3RvcDo3cHg7bGVmdDo4cHg7Zm9udC1zaXplOjkuNXB4O2xldHRlci1zcGFjaW5nOi4xZW07Y29sb3I6"
    "dmFyKC0tZ29sZCk7YmFja2dyb3VuZDpyZ2JhKDUsNywxNSwuNzUpO3BhZGRpbmc6MnB4IDZweDtib3JkZXItcmFkaXVzOjNweH0K"
    "LnNjcmVlbi5vbntib3JkZXItY29sb3I6dmFyKC0tb2spO2JveC1zaGFkb3c6MCAwIDQwcHggcmdiYSgxMjcsMjI3LDE3NiwuNDUp"
    "fQouYXhsZXtwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0OjUwJTt0b3A6NTAlO3dpZHRoOjZweDtoZWlnaHQ6MjQwcHg7bWFyZ2luOi0x"
    "MjBweCAwIDAgLTNweDtiYWNrZ3JvdW5kOmxpbmVhci1ncmFkaWVudCgjYzlhODRjLCM1YTRhMWMpO2JvcmRlci1yYWRpdXM6M3B4"
    "O3RyYW5zZm9ybTp0cmFuc2xhdGVaKDApO2JveC1zaGFkb3c6MCAwIDE2cHggcmdiYSgyMDEsMTY4LDc2LC41KX0KLyogcm9ib3Qg"
    "YXVkaWVuY2UgKi8KLmNyb3dke2Rpc3BsYXk6ZmxleDtnYXA6NnB4O2p1c3RpZnktY29udGVudDpjZW50ZXI7bWFyZ2luLWJvdHRv"
    "bTo4cHg7aGVpZ2h0Ojc0cHg7YWxpZ24taXRlbXM6ZmxleC1lbmR9Ci5ib3R7d2lkdGg6NDBweDtoZWlnaHQ6NjZweDtwb3NpdGlv"
    "bjpyZWxhdGl2ZTthbmltYXRpb246Ym9iIDNzIGVhc2UtaW4tb3V0IGluZmluaXRlfQouYm90Om50aC1jaGlsZCgybil7YW5pbWF0"
    "aW9uLWRlbGF5Oi42c30uYm90Om50aC1jaGlsZCgzbil7YW5pbWF0aW9uLWRlbGF5OjEuMXN9CkBrZXlmcmFtZXMgYm9iezUwJXt0"
    "cmFuc2Zvcm06dHJhbnNsYXRlWSgtMnB4KX19Ci5ib3QgLmhlYWR7cG9zaXRpb246YWJzb2x1dGU7dG9wOjA7bGVmdDo5cHg7d2lk"
    "dGg6MjJweDtoZWlnaHQ6MThweDtib3JkZXItcmFkaXVzOjVweDtiYWNrZ3JvdW5kOiNkOGRkZTZ9Ci5ib3QgLnZpc29ye3Bvc2l0"
    "aW9uOmFic29sdXRlO3RvcDo2cHg7bGVmdDozcHg7d2lkdGg6MTZweDtoZWlnaHQ6NXB4O2JvcmRlci1yYWRpdXM6MnB4O2JhY2tn"
    "cm91bmQ6dmFyKC0tZ29sZCk7Ym94LXNoYWRvdzowIDAgOHB4IHZhcigtLWdvbGQpO3RyYW5zaXRpb246YmFja2dyb3VuZCAuNHMs"
    "Ym94LXNoYWRvdyAuNHN9Ci5ib3QgLmJvZHl7cG9zaXRpb246YWJzb2x1dGU7dG9wOjIwcHg7bGVmdDo2cHg7d2lkdGg6MjhweDto"
    "ZWlnaHQ6MjRweDtib3JkZXItcmFkaXVzOjVweDtiYWNrZ3JvdW5kOiNjM2M5ZDR9Ci5ib3QgLnNlYXR7cG9zaXRpb246YWJzb2x1"
    "dGU7Ym90dG9tOjA7bGVmdDowO3dpZHRoOjQwcHg7aGVpZ2h0OjI0cHg7Ym9yZGVyLXJhZGl1czo2cHggNnB4IDNweCAzcHg7YmFj"
    "a2dyb3VuZDojMWIyMzM2O2JvcmRlci10b3A6MnB4IHNvbGlkICMyYTM1NTJ9Ci5ub3d7Zm9udC1zaXplOjEycHg7dGV4dC1hbGln"
    "bjpjZW50ZXI7bWluLWhlaWdodDoxOHB4O21hcmdpbi1ib3R0b206OHB4O2NvbG9yOnZhcigtLW9rKTtwYWRkaW5nOjAgMTJweH0K"
    "LmJhcntkaXNwbGF5OmZsZXg7Z2FwOjhweDtmbGV4LXdyYXA6d3JhcDtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3BhZGRpbmc6MCAx"
    "MnB4IGNhbGMoMTZweCArIGVudihzYWZlLWFyZWEtaW5zZXQtYm90dG9tKSl9Ci5idG57Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czo4"
    "cHg7cGFkZGluZzoxMXB4IDE1cHg7Zm9udDo1MDAgMTIuNXB4ICdJQk0gUGxleCBNb25vJyxtb25vc3BhY2U7YmFja2dyb3VuZDp2"
    "YXIoLS1nb2xkKTtjb2xvcjojMDUwNzBmO2N1cnNvcjpwb2ludGVyfQouYnRuLmdob3N0e2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7"
    "Y29sb3I6I2U4ZWRmNztib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjI1KX0KLyogdGhlIHJvb20gKi8KLnJvb217"
    "cGVyc3BlY3RpdmU6OTAwcHh9Ci5mbG9vcntwb3NpdGlvbjphYnNvbHV0ZTtsZWZ0Oi01MCU7cmlnaHQ6LTUwJTtib3R0b206LTEw"
    "JTtoZWlnaHQ6NjAlO2JhY2tncm91bmQ6cmVwZWF0aW5nLWxpbmVhci1ncmFkaWVudCg5MGRlZyxyZ2JhKDIwMSwxNjgsNzYsLjE4"
    "KSAwIDFweCx0cmFuc3BhcmVudCAxcHggNjBweCkscmVwZWF0aW5nLWxpbmVhci1ncmFkaWVudCgwZGVnLHJnYmEoMjAxLDE2OCw3"
    "NiwuMTgpIDAgMXB4LHRyYW5zcGFyZW50IDFweCA2MHB4KTt0cmFuc2Zvcm06cm90YXRlWCg3MmRlZyk7dHJhbnNmb3JtLW9yaWdp"
    "bjpib3R0b207cG9pbnRlci1ldmVudHM6bm9uZX0KLnR2d3JhcHtmbGV4OjE7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRl"
    "cjtqdXN0aWZ5LWNvbnRlbnQ6Y2VudGVyO3dpZHRoOjEwMCU7cGVyc3BlY3RpdmU6MTAwMHB4fQoudHZ7d2lkdGg6bWluKDkydncs"
    "NzIwcHgpO2FzcGVjdC1yYXRpbzoxNi85O2JvcmRlci1yYWRpdXM6MTRweDtiYWNrZ3JvdW5kOiMwMDA7Ym9yZGVyOjEwcHggc29s"
    "aWQgIzFiMjMzNjtvdXRsaW5lOjJweCBzb2xpZCByZ2JhKDIwMSwxNjgsNzYsLjUpO2JveC1zaGFkb3c6MCAwIDYwcHggcmdiYSgx"
    "NDMsMjA4LDI1NSwuMjUpLDAgMzBweCA2MHB4IHJnYmEoMCwwLDAsLjYpO3RyYW5zZm9ybS1zdHlsZTpwcmVzZXJ2ZS0zZDthbmlt"
    "YXRpb246c3dheSA5cyBlYXNlLWluLW91dCBpbmZpbml0ZX0KLnR2LnNwaW57YW5pbWF0aW9uOmZ1bGxzcGluIDE0cyBsaW5lYXIg"
    "aW5maW5pdGV9CkBrZXlmcmFtZXMgc3dheXswJSwxMDAle3RyYW5zZm9ybTpyb3RhdGVZKC0xMGRlZykgcm90YXRlWCgzZGVnKX01"
    "MCV7dHJhbnNmb3JtOnJvdGF0ZVkoMTBkZWcpIHJvdGF0ZVgoLTJkZWcpfX0KQGtleWZyYW1lcyBmdWxsc3Bpbnt0b3t0cmFuc2Zv"
    "cm06cm90YXRlWSgzNjBkZWcpfX0KLnR2IGlmcmFtZXt3aWR0aDoxMDAlO2hlaWdodDoxMDAlO2JvcmRlcjowO2JvcmRlci1yYWRp"
    "dXM6NHB4O2Rpc3BsYXk6YmxvY2t9Ci5jaGFuc3tkaXNwbGF5OmZsZXg7Z2FwOjZweDtvdmVyZmxvdy14OmF1dG87bWF4LXdpZHRo"
    "OjEwMCU7cGFkZGluZzo4cHggMTJweDtzY3JvbGxiYXItd2lkdGg6bm9uZX0KLmNoYW5zIGJ1dHRvbntmbGV4Om5vbmU7Ym9yZGVy"
    "OjFweCBzb2xpZCByZ2JhKDIwMSwxNjgsNzYsLjM1KTtiYWNrZ3JvdW5kOnJnYmEoMTMsMjAsMzYsLjgpO2NvbG9yOiNlOGVkZjc7"
    "Ym9yZGVyLXJhZGl1czo3cHg7cGFkZGluZzo4cHggMTFweDtmb250OjUwMCAxMS41cHggJ0lCTSBQbGV4IE1vbm8nLG1vbm9zcGFj"
    "ZTtjdXJzb3I6cG9pbnRlcn0KLmNoYW5zIGJ1dHRvbi5vbntib3JkZXItY29sb3I6dmFyKC0tb2spO2NvbG9yOnZhcigtLW9rKX0K"
    "LmZvb3R7Zm9udC1zaXplOjEwLjVweDtjb2xvcjp2YXIoLS1tdXRlKTt0ZXh0LWFsaWduOmNlbnRlcjtwYWRkaW5nOjAgMTZweCA2"
    "cHh9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PgoKPHNlY3Rpb24gY2xhc3M9InZpZXciIGlkPSJsb2JieSI+CiA8aGVhZGVyPjxkaXYg"
    "Y2xhc3M9ImJyYW5kIj5zZWJiaTxiPi5wcm88L2I+IMK3IENJTkVNQTwvZGl2PjxoMT5BSSBnb3Zlcm5hbmNlLCBvbiBldmVyeSBz"
    "Y3JlZW4uPC9oMT48ZGl2IGNsYXNzPSJzdWIiPkRSQUcgVE8gU1BJTiDCtyBUQVAgQSBTQ1JFRU4gwrcgRU5URVIgVEhFIFJPT00g"
    "VE8gV0FUQ0g8L2Rpdj48L2hlYWRlcj4KIDxkaXYgY2xhc3M9InN0YWdlIiBpZD0ic3RhZ2UiPjxkaXYgY2xhc3M9InJpbmciIGlk"
    "PSJyaW5nIj48ZGl2IGNsYXNzPSJheGxlIj48L2Rpdj48L2Rpdj48L2Rpdj4KIDxkaXYgY2xhc3M9Im5vdyIgaWQ9Im5vdyI+PC9k"
    "aXY+CiA8ZGl2IGNsYXNzPSJjcm93ZCIgaWQ9ImNyb3dkIj48L2Rpdj4KIDxkaXYgY2xhc3M9ImJhciI+PGJ1dHRvbiBjbGFzcz0i"
    "YnRuIiBvbmNsaWNrPSJlbnRlcigpIj5FbnRlciB0aGUgcm9vbSDilrY8L2J1dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3Qi"
    "IG9uY2xpY2s9ImFkZFZpZGVvKCkiPisgQWRkIGEgdmlkZW88L2J1dHRvbj48YSBjbGFzcz0iYnRuIGdob3N0IiBocmVmPSIvIiBz"
    "dHlsZT0idGV4dC1kZWNvcmF0aW9uOm5vbmUiPkhvbWU8L2E+PC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGNsYXNzPSJ2aWV3"
    "IHJvb20gaGlkZGVuIiBpZD0icm9vbSI+CiA8ZGl2IGNsYXNzPSJmbG9vciI+PC9kaXY+CiA8aGVhZGVyPjxkaXYgY2xhc3M9ImJy"
    "YW5kIj5zZWJiaTxiPi5wcm88L2I+IMK3IFRIRSBTQ1JFRU5JTkcgUk9PTTwvZGl2PjxkaXYgY2xhc3M9InN1YiIgaWQ9InJvb21O"
    "b3ciPjwvZGl2PjwvaGVhZGVyPgogPGRpdiBjbGFzcz0idHZ3cmFwIj48ZGl2IGNsYXNzPSJ0diIgaWQ9InR2Ij48L2Rpdj48L2Rp"
    "dj4KIDxkaXYgY2xhc3M9ImNoYW5zIiBpZD0iY2hhbnMiPjwvZGl2PgogPGRpdiBjbGFzcz0iY3Jvd2QiIGlkPSJjcm93ZDIiPjwv"
    "ZGl2PgogPGRpdiBjbGFzcz0iYmFyIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InN0ZXAoLTEpIj7il4AgQ2hh"
    "bm5lbDwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0ic3RlcCgxKSI+Q2hhbm5lbCDilrY8L2J1dHRv"
    "bj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InRvZ2dsZVNwaW4oKSIgaWQ9InNwaW5CdG4iPlNwaW4gdGhlIFRW"
    "PC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJsZWF2ZSgpIj5CYWNrIHRvIHRoZSBsb2JieTwvYnV0dG9uPjwv"
    "ZGl2PgogPGRpdiBjbGFzcz0iZm9vdCI+VmlkZW9zIHBsYXkgZnJvbSB0aGVpciBvcmlnaW5hbCBjaGFubmVscyBvbiBZb3VUdWJl"
    "LiBzZWJiaS5wcm8gZG9lcyBub3Qgb3duIG9yIGVuZG9yc2UgdGhpcmQtcGFydHkgY29udGVudC48L2Rpdj4KPC9zZWN0aW9uPgoK"
    "PHNjcmlwdD4KKGZ1bmN0aW9uKCl7CnZhciBDSEFOTkVMUz1bCiB7aWQ6ImdNMWRMZHBEUjUwIix0aXRsZToiV2hhdCBJcyBUcnVz"
    "dHdvcnRoeSBBST8iLGNoYW5uZWw6Ik5WSURJQSJ9LAoge2lkOiJmNmR4M1loLVR3dyIsdGl0bGU6IldoYXQgaXMgQUkgZ292ZXJu"
    "YW5jZT8iLGNoYW5uZWw6IklCTSBSZXNlYXJjaCJ9LAoge2lkOiJRMDIwQy1KdzBvOCIsdGl0bGU6IlRoZSBJbXBvcnRhbmNlIG9m"
    "IEFJIEdvdmVybmFuY2UiLGNoYW5uZWw6IklCTSBUZWNobm9sb2d5In0KXTsKdHJ5e3ZhciBzYXZlZD1KU09OLnBhcnNlKGxvY2Fs"
    "U3RvcmFnZS5nZXRJdGVtKCJzZWJiaS5jaW5lbWEiKXx8IltdIik7aWYoQXJyYXkuaXNBcnJheShzYXZlZCkpQ0hBTk5FTFM9Q0hB"
    "Tk5FTFMuY29uY2F0KHNhdmVkKX1jYXRjaChlKXt9CnZhciBjdXI9MCxhbmdsZT0wLHZlbD0uMTIsZHJhZz1udWxsLGxhc3RYPTAs"
    "c3Bpbm5pbmc9ZmFsc2U7CnZhciByaW5nPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJyaW5nIiksbm93PWRvY3VtZW50LmdldEVs"
    "ZW1lbnRCeUlkKCJub3ciKTsKZnVuY3Rpb24gZXNjKHMpe3JldHVybiBTdHJpbmcocykucmVwbGFjZSgvWyY8PiJdL2csZnVuY3Rp"
    "b24oYyl7cmV0dXJueyImIjoiJmFtcDsiLCI8IjoiJmx0OyIsIj4iOiImZ3Q7IiwnIic6IiZxdW90OyJ9W2NdfSl9CmZ1bmN0aW9u"
    "IGNyb3dkKGVsLG4pe3ZhciBoPSIiO2Zvcih2YXIgaT0wO2k8bjtpKyspaCs9JzxkaXYgY2xhc3M9ImJvdCI+PGRpdiBjbGFzcz0i"
    "aGVhZCI+PGRpdiBjbGFzcz0idmlzb3IiPjwvZGl2PjwvZGl2PjxkaXYgY2xhc3M9ImJvZHkiPjwvZGl2PjxkaXYgY2xhc3M9InNl"
    "YXQiPjwvZGl2PjwvZGl2Pic7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoZWwpLmlubmVySFRNTD1ofQpjcm93ZCgiY3Jvd2QiLE1h"
    "dGgubWluKDksTWF0aC5mbG9vcihpbm5lcldpZHRoLzQ4KSkpO2Nyb3dkKCJjcm93ZDIiLE1hdGgubWluKDksTWF0aC5mbG9vcihp"
    "bm5lcldpZHRoLzQ4KSkpOwp2YXIgVklTPVsiI2M5YTg0YyIsIiM3ZmUzYjAiLCIjOGZkMGZmIiwiI2ZmOGE4MCIsIiNkNTliZmYi"
    "XTsKZnVuY3Rpb24gdmlzb3IoKXt2YXIgYz1WSVNbY3VyJVZJUy5sZW5ndGhdO0FycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwo"
    "ZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgiLnZpc29yIiksZnVuY3Rpb24odil7di5zdHlsZS5iYWNrZ3JvdW5kPWM7di5zdHls"
    "ZS5ib3hTaGFkb3c9IjAgMCA4cHggIitjfSl9CmZ1bmN0aW9uIGJ1aWxkKCl7CiBBcnJheS5wcm90b3R5cGUuZm9yRWFjaC5jYWxs"
    "KHJpbmcucXVlcnlTZWxlY3RvckFsbCgiLnNjcmVlbiIpLGZ1bmN0aW9uKHMpe3MucmVtb3ZlKCl9KTsKIHZhciBuPU1hdGgubWF4"
    "KENIQU5ORUxTLmxlbmd0aCw1KSxyPU1hdGgucm91bmQoMTM1L01hdGgudGFuKE1hdGguUEkvbikpKzQwOwogZm9yKHZhciBpPTA7"
    "aTxuO2krKyl7dmFyIGM9Q0hBTk5FTFNbaSVDSEFOTkVMUy5sZW5ndGhdLGQ9ZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgiZGl2Iik7"
    "ZC5jbGFzc05hbWU9InNjcmVlbiI7ZC5kYXRhc2V0Lmk9aSVDSEFOTkVMUy5sZW5ndGg7CiAgZC5zdHlsZS50cmFuc2Zvcm09InJv"
    "dGF0ZVkoIisoMzYwL24qaSkrImRlZykgdHJhbnNsYXRlWigiK3IrInB4KSI7CiAgZC5pbm5lckhUTUw9JzxpbWcgYWx0PSIiIHNy"
    "Yz0iaHR0cHM6Ly9pbWcueW91dHViZS5jb20vdmkvJytlbmNvZGVVUklDb21wb25lbnQoYy5pZCkrJy9ocWRlZmF1bHQuanBnIj48"
    "ZGl2IGNsYXNzPSJjaCI+Q0ggJysoKGklQ0hBTk5FTFMubGVuZ3RoKSsxKSsnIMK3ICcrZXNjKGMuY2hhbm5lbCkrJzwvZGl2Pjxk"
    "aXYgY2xhc3M9ImxhYiI+Jytlc2MoYy50aXRsZSkrJzwvZGl2Pic7CiAgZC5vbmNsaWNrPWZ1bmN0aW9uKCl7cGljaygrdGhpcy5k"
    "YXRhc2V0LmkpfTtyaW5nLmFwcGVuZENoaWxkKGQpfQogbWFyaygpO2NoYW5zKCl9CmZ1bmN0aW9uIG1hcmsoKXtBcnJheS5wcm90"
    "b3R5cGUuZm9yRWFjaC5jYWxsKHJpbmcucXVlcnlTZWxlY3RvckFsbCgiLnNjcmVlbiIpLGZ1bmN0aW9uKHMpe3MuY2xhc3NMaXN0"
    "LnRvZ2dsZSgib24iLCtzLmRhdGFzZXQuaT09PWN1cil9KTsKIHZhciBjPUNIQU5ORUxTW2N1cl07bm93LnRleHRDb250ZW50PSJD"
    "SCAiKyhjdXIrMSkrIiDCtyAiK2MuY2hhbm5lbCsiIMK3ICIrYy50aXRsZTt2aXNvcigpfQpmdW5jdGlvbiBwaWNrKGkpe2N1cj1p"
    "O21hcmsoKTt2ZWw9LjAzfQpmdW5jdGlvbiBsb29wKCl7aWYoZHJhZz09PW51bGwpe2FuZ2xlKz12ZWw7dmVsKz0oIC4xMi12ZWwp"
    "Ki4wMX1yaW5nLnN0eWxlLnRyYW5zZm9ybT0icm90YXRlWSgiK2FuZ2xlKyJkZWcpIjtyZXF1ZXN0QW5pbWF0aW9uRnJhbWUobG9v"
    "cCl9bG9vcCgpOwp2YXIgc3Q9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInN0YWdlIik7CnN0LmFkZEV2ZW50TGlzdGVuZXIoInBv"
    "aW50ZXJkb3duIixmdW5jdGlvbihlKXtkcmFnPWUuY2xpZW50WDtsYXN0WD1lLmNsaWVudFh9KTsKYWRkRXZlbnRMaXN0ZW5lcigi"
    "cG9pbnRlcm1vdmUiLGZ1bmN0aW9uKGUpe2lmKGRyYWchPT1udWxsKXt2YXIgZHg9ZS5jbGllbnRYLWxhc3RYO2FuZ2xlKz1keCou"
    "NDt2ZWw9ZHgqLjQ7bGFzdFg9ZS5jbGllbnRYfX0pOwphZGRFdmVudExpc3RlbmVyKCJwb2ludGVydXAiLGZ1bmN0aW9uKCl7ZHJh"
    "Zz1udWxsfSk7CndpbmRvdy5hZGRWaWRlbz1mdW5jdGlvbigpe3ZhciB1PXByb21wdCgiUGFzdGUgYSBZb3VUdWJlIGxpbmsgYWJv"
    "dXQgQUkgZ292ZXJuYW5jZToiKTtpZighdSlyZXR1cm47CiB2YXIgbT11Lm1hdGNoKC8oPzp2PXx5b3V0dVwuYmVcL3xlbWJlZFwv"
    "fHNob3J0c1wvKShbQS1aYS16MC05Xy1dezExfSkvKTtpZighbSl7YWxlcnQoIlRoYXQgZG9lc24ndCBsb29rIGxpa2UgYSBZb3VU"
    "dWJlIGxpbmsuIik7cmV0dXJufQogdmFyIHQ9cHJvbXB0KCJUaXRsZSBmb3IgdGhpcyBzY3JlZW46IiwiTmV3IGNoYW5uZWwiKXx8"
    "Ik5ldyBjaGFubmVsIixuYz1wcm9tcHQoIkNoYW5uZWwgbmFtZToiLCJZb3VyIGNoYW5uZWwiKXx8IllvdXIgY2hhbm5lbCI7CiB2"
    "YXIgdj17aWQ6bVsxXSx0aXRsZTp0LnNsaWNlKDAsNjApLGNoYW5uZWw6bmMuc2xpY2UoMCwzMCl9O0NIQU5ORUxTLnB1c2godik7"
    "CiB0cnl7dmFyIHM9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2UuZ2V0SXRlbSgic2ViYmkuY2luZW1hIil8fCJbXSIpO3MucHVzaCh2"
    "KTtsb2NhbFN0b3JhZ2Uuc2V0SXRlbSgic2ViYmkuY2luZW1hIixKU09OLnN0cmluZ2lmeShzLnNsaWNlKC0yMCkpKX1jYXRjaChl"
    "KXt9CiBjdXI9Q0hBTk5FTFMubGVuZ3RoLTE7YnVpbGQoKX07CmZ1bmN0aW9uIHR2KCl7dmFyIGM9Q0hBTk5FTFNbY3VyXTtkb2N1"
    "bWVudC5nZXRFbGVtZW50QnlJZCgidHYiKS5pbm5lckhUTUw9JzxpZnJhbWUgc3JjPSJodHRwczovL3d3dy55b3V0dWJlLW5vY29v"
    "a2llLmNvbS9lbWJlZC8nK2VuY29kZVVSSUNvbXBvbmVudChjLmlkKSsnP2F1dG9wbGF5PTEmcmVsPTAmcGxheXNpbmxpbmU9MSIg"
    "YWxsb3c9ImF1dG9wbGF5OyBlbmNyeXB0ZWQtbWVkaWE7IHBpY3R1cmUtaW4tcGljdHVyZTsgZnVsbHNjcmVlbiIgYWxsb3dmdWxs"
    "c2NyZWVuIHRpdGxlPSInK2VzYyhjLnRpdGxlKSsnIj48L2lmcmFtZT4nOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJvb21O"
    "b3ciKS50ZXh0Q29udGVudD0iTk9XIFNIT1dJTkcgwrcgQ0ggIisoY3VyKzEpKyIgwrcgIitjLmNoYW5uZWwrIiDCtyAiK2MudGl0"
    "bGU7Y2hhbnMoKTt2aXNvcigpfQpmdW5jdGlvbiBjaGFucygpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjaGFucyIpLmlubmVy"
    "SFRNTD1DSEFOTkVMUy5tYXAoZnVuY3Rpb24oYyxpKXtyZXR1cm4gJzxidXR0b24gY2xhc3M9IicrKGk9PT1jdXI/Im9uIjoiIikr"
    "JyIgZGF0YS1pPSInK2krJyI+Q0ggJysoaSsxKSsnIMK3ICcrZXNjKGMuY2hhbm5lbCkrJzwvYnV0dG9uPid9KS5qb2luKCIiKTsK"
    "IEFycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwoZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgiI2NoYW5zIGJ1dHRvbiIpLGZ1"
    "bmN0aW9uKGIpe2Iub25jbGljaz1mdW5jdGlvbigpe2N1cj0rYi5kYXRhc2V0Lmk7dHYoKTttYXJrKCl9fSl9CndpbmRvdy5lbnRl"
    "cj1mdW5jdGlvbigpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJsb2JieSIpLmNsYXNzTGlzdC5hZGQoImhpZGRlbiIpO2RvY3Vt"
    "ZW50LmdldEVsZW1lbnRCeUlkKCJyb29tIikuY2xhc3NMaXN0LnJlbW92ZSgiaGlkZGVuIik7dHYoKX07CndpbmRvdy5sZWF2ZT1m"
    "dW5jdGlvbigpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0diIpLmlubmVySFRNTD0iIjtkb2N1bWVudC5nZXRFbGVtZW50QnlJ"
    "ZCgicm9vbSIpLmNsYXNzTGlzdC5hZGQoImhpZGRlbiIpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJsb2JieSIpLmNsYXNzTGlz"
    "dC5yZW1vdmUoImhpZGRlbiIpO21hcmsoKX07CndpbmRvdy5zdGVwPWZ1bmN0aW9uKGQpe2N1cj0oY3VyK2QrQ0hBTk5FTFMubGVu"
    "Z3RoKSVDSEFOTkVMUy5sZW5ndGg7dHYoKTttYXJrKCl9Owp3aW5kb3cudG9nZ2xlU3Bpbj1mdW5jdGlvbigpe3NwaW5uaW5nPSFz"
    "cGlubmluZztkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidHYiKS5jbGFzc0xpc3QudG9nZ2xlKCJzcGluIixzcGlubmluZyk7ZG9j"
    "dW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNwaW5CdG4iKS50ZXh0Q29udGVudD1zcGlubmluZz8iU3RvcCBzcGlubmluZyI6IlNwaW4g"
    "dGhlIFRWIn07CmJ1aWxkKCk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/cinema": (_d(_HTML_B64), "text/html; charset=utf-8"),
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
    if getattr(cls, "_cinema_patched", False):
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
    cls._cinema_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "cinema", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys())}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
