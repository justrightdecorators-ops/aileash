"""
modules/cinema.py  v1.2.0
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

VERSION = "1.2.0"

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
    "NDMsMjA4LDI1NSwuMjUpLDAgMzBweCA2MHB4IHJnYmEoMCwwLDAsLjYpO3RyYW5zaXRpb246dHJhbnNmb3JtIC44c30KLnR2Lmlk"
    "bGV7YW5pbWF0aW9uOnN3YXkgOXMgZWFzZS1pbi1vdXQgaW5maW5pdGV9Ci50dmxpbmt7ZGlzcGxheTpibG9jazt0ZXh0LWFsaWdu"
    "OmNlbnRlcjtmb250LXNpemU6MTFweDtjb2xvcjojOGZkMGZmO21hcmdpbi10b3A6OHB4O3RleHQtZGVjb3JhdGlvbjpub25lfQou"
    "dHYuc3BpbnthbmltYXRpb246ZnVsbHNwaW4gMTRzIGxpbmVhciBpbmZpbml0ZX0KQGtleWZyYW1lcyBzd2F5ezAlLDEwMCV7dHJh"
    "bnNmb3JtOnJvdGF0ZVkoLTEwZGVnKSByb3RhdGVYKDNkZWcpfTUwJXt0cmFuc2Zvcm06cm90YXRlWSgxMGRlZykgcm90YXRlWCgt"
    "MmRlZyl9fQpAa2V5ZnJhbWVzIGZ1bGxzcGlue3Rve3RyYW5zZm9ybTpyb3RhdGVZKDM2MGRlZyl9fQoudHYgaWZyYW1le3dpZHRo"
    "OjEwMCU7aGVpZ2h0OjEwMCU7Ym9yZGVyOjA7Ym9yZGVyLXJhZGl1czo0cHg7ZGlzcGxheTpibG9ja30KLmNoYW5ze2Rpc3BsYXk6"
    "ZmxleDtnYXA6NnB4O292ZXJmbG93LXg6YXV0bzttYXgtd2lkdGg6MTAwJTtwYWRkaW5nOjhweCAxMnB4O3Njcm9sbGJhci13aWR0"
    "aDpub25lfQouY2hhbnMgYnV0dG9ue2ZsZXg6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAxLDE2OCw3NiwuMzUpO2JhY2tn"
    "cm91bmQ6cmdiYSgxMywyMCwzNiwuOCk7Y29sb3I6I2U4ZWRmNztib3JkZXItcmFkaXVzOjdweDtwYWRkaW5nOjhweCAxMXB4O2Zv"
    "bnQ6NTAwIDExLjVweCAnSUJNIFBsZXggTW9ubycsbW9ub3NwYWNlO2N1cnNvcjpwb2ludGVyfQouY2hhbnMgYnV0dG9uLm9ue2Jv"
    "cmRlci1jb2xvcjp2YXIoLS1vayk7Y29sb3I6dmFyKC0tb2spfQouZm9vdHtmb250LXNpemU6MTAuNXB4O2NvbG9yOnZhcigtLW11"
    "dGUpO3RleHQtYWxpZ246Y2VudGVyO3BhZGRpbmc6MCAxNnB4IDZweH0KPC9zdHlsZT48L2hlYWQ+PGJvZHk+Cgo8c2VjdGlvbiBj"
    "bGFzcz0idmlldyIgaWQ9ImxvYmJ5Ij4KIDxoZWFkZXI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgQ0lO"
    "RU1BPC9kaXY+PGgxPkFJIGdvdmVybmFuY2UsIG9uIGV2ZXJ5IHNjcmVlbi48L2gxPjxkaXYgY2xhc3M9InN1YiI+RFJBRyBUTyBT"
    "UElOIMK3IFRBUCBBIFNDUkVFTiDCtyBFTlRFUiBUSEUgUk9PTSBUTyBXQVRDSDwvZGl2PjwvaGVhZGVyPgogPGRpdiBjbGFzcz0i"
    "c3RhZ2UiIGlkPSJzdGFnZSI+PGRpdiBjbGFzcz0icmluZyIgaWQ9InJpbmciPjxkaXYgY2xhc3M9ImF4bGUiPjwvZGl2PjwvZGl2"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0ibm93IiBpZD0ibm93Ij48L2Rpdj48ZGl2IGNsYXNzPSJiYXIiIHN0eWxlPSJwYWRkaW5nLWJv"
    "dHRvbTo2cHgiPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0icmVlbFN0ZXAoLTEpIj7il4AgUmVlbDwvYnV0dG9u"
    "PjxzcGFuIGNsYXNzPSJzdWIiIGlkPSJyZWVsTGFiIiBzdHlsZT0iYWxpZ24tc2VsZjpjZW50ZXIiPjwvc3Bhbj48YnV0dG9uIGNs"
    "YXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InJlZWxTdGVwKDEpIj5SZWVsIOKWtjwvYnV0dG9uPjwvZGl2PgogPGRpdiBjbGFzcz0i"
    "Y3Jvd2QiIGlkPSJjcm93ZCI+PC9kaXY+CiA8ZGl2IGNsYXNzPSJiYXIiPjxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0iZW50"
    "ZXIoKSI+RW50ZXIgdGhlIHJvb20g4pa2PC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBvbmNsaWNrPSJhZGRWaWRl"
    "bygpIj4rIEFkZCBhIHZpZGVvPC9idXR0b24+PGEgY2xhc3M9ImJ0biBnaG9zdCIgaHJlZj0iLyIgc3R5bGU9InRleHQtZGVjb3Jh"
    "dGlvbjpub25lIj5Ib21lPC9hPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlvbiBjbGFzcz0idmlldyByb29tIGhpZGRlbiIgaWQ9"
    "InJvb20iPgogPGRpdiBjbGFzcz0iZmxvb3IiPjwvZGl2PgogPGhlYWRlcj48ZGl2IGNsYXNzPSJicmFuZCI+c2ViYmk8Yj4ucHJv"
    "PC9iPiDCtyBUSEUgU0NSRUVOSU5HIFJPT008L2Rpdj48ZGl2IGNsYXNzPSJzdWIiIGlkPSJyb29tTm93Ij48L2Rpdj48L2hlYWRl"
    "cj4KIDxkaXYgY2xhc3M9InR2d3JhcCIgc3R5bGU9ImZsZXgtZGlyZWN0aW9uOmNvbHVtbiI+PGRpdiBjbGFzcz0idHYiIGlkPSJ0"
    "diI+PC9kaXY+PGEgY2xhc3M9InR2bGluayIgaWQ9InR2bGluayIgdGFyZ2V0PSJfYmxhbmsiIHJlbD0ibm9vcGVuZXIiPjwvYT48"
    "L2Rpdj4KIDxkaXYgY2xhc3M9ImNoYW5zIiBpZD0iY2hhbnMiPjwvZGl2PgogPGRpdiBjbGFzcz0iY3Jvd2QiIGlkPSJjcm93ZDIi"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0iYmFyIj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InN0ZXAoLTEpIj7il4Ag"
    "Q2hhbm5lbDwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0ic3RlcCgxKSI+Q2hhbm5lbCDilrY8L2J1"
    "dHRvbj48YnV0dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InRvZ2dsZVNwaW4oKSIgaWQ9InNwaW5CdG4iPlNwaW4gdGhl"
    "IFRWPC9idXR0b24+PGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJsZWF2ZSgpIj5CYWNrIHRvIHRoZSBsb2JieTwvYnV0dG9u"
    "PjwvZGl2PgogPGRpdiBjbGFzcz0iZm9vdCI+VmlkZW9zIHBsYXkgZnJvbSB0aGVpciBvcmlnaW5hbCBjaGFubmVscyBvbiBZb3VU"
    "dWJlLiBzZWJiaS5wcm8gZG9lcyBub3Qgb3duIG9yIGVuZG9yc2UgdGhpcmQtcGFydHkgY29udGVudC48L2Rpdj4KPC9zZWN0aW9u"
    "PgoKPHNjcmlwdD4KKGZ1bmN0aW9uKCl7CnZhciBDSEFOTkVMUz1bCiB7aWQ6ImdNMWRMZHBEUjUwIix0aXRsZToiV2hhdCBJcyBU"
    "cnVzdHdvcnRoeSBBST8iLGNoYW5uZWw6Ik5WSURJQSJ9LAoge2lkOiJmNmR4M1loLVR3dyIsdGl0bGU6IldoYXQgaXMgQUkgZ292"
    "ZXJuYW5jZT8iLGNoYW5uZWw6IklCTSBSZXNlYXJjaCJ9LAoge2lkOiJRMDIwQy1KdzBvOCIsdGl0bGU6IlRoZSBJbXBvcnRhbmNl"
    "IG9mIEFJIEdvdmVybmFuY2UiLGNoYW5uZWw6IklCTSBUZWNobm9sb2d5In0KXTsKdHJ5e3ZhciBzYXZlZD1KU09OLnBhcnNlKGxv"
    "Y2FsU3RvcmFnZS5nZXRJdGVtKCJzZWJiaS5jaW5lbWEiKXx8IltdIik7aWYoQXJyYXkuaXNBcnJheShzYXZlZCkpQ0hBTk5FTFM9"
    "Q0hBTk5FTFMuY29uY2F0KHNhdmVkKX1jYXRjaChlKXt9CnZhciBjdXI9MCxhbmdsZT0wLHZlbD0uMTIsZHJhZz1udWxsLGxhc3RY"
    "PTAsc3Bpbm5pbmc9ZmFsc2UscmVlbD0wLFBFUj0xMDsKdmFyIHJpbmc9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJpbmciKSxu"
    "b3c9ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoIm5vdyIpOwpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmluZyhzKS5yZXBsYWNl"
    "KC9bJjw+Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7"
    "In1bY119KX0KZnVuY3Rpb24gY3Jvd2QoZWwsbil7dmFyIGg9IiI7Zm9yKHZhciBpPTA7aTxuO2krKyloKz0nPGRpdiBjbGFzcz0i"
    "Ym90Ij48ZGl2IGNsYXNzPSJoZWFkIj48ZGl2IGNsYXNzPSJ2aXNvciI+PC9kaXY+PC9kaXY+PGRpdiBjbGFzcz0iYm9keSI+PC9k"
    "aXY+PGRpdiBjbGFzcz0ic2VhdCI+PC9kaXY+PC9kaXY+Jztkb2N1bWVudC5nZXRFbGVtZW50QnlJZChlbCkuaW5uZXJIVE1MPWh9"
    "CmNyb3dkKCJjcm93ZCIsTWF0aC5taW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7Y3Jvd2QoImNyb3dkMiIsTWF0aC5t"
    "aW4oOSxNYXRoLmZsb29yKGlubmVyV2lkdGgvNDgpKSk7CnZhciBWSVM9WyIjYzlhODRjIiwiIzdmZTNiMCIsIiM4ZmQwZmYiLCIj"
    "ZmY4YTgwIiwiI2Q1OWJmZiJdOwpmdW5jdGlvbiB2aXNvcigpe3ZhciBjPVZJU1tjdXIlVklTLmxlbmd0aF07QXJyYXkucHJvdG90"
    "eXBlLmZvckVhY2guY2FsbChkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCIudmlzb3IiKSxmdW5jdGlvbih2KXt2LnN0eWxlLmJh"
    "Y2tncm91bmQ9Yzt2LnN0eWxlLmJveFNoYWRvdz0iMCAwIDhweCAiK2N9KX0KZnVuY3Rpb24gYnVpbGQoKXsKIEFycmF5LnByb3Rv"
    "dHlwZS5mb3JFYWNoLmNhbGwocmluZy5xdWVyeVNlbGVjdG9yQWxsKCIuc2NyZWVuIiksZnVuY3Rpb24ocyl7cy5yZW1vdmUoKX0p"
    "OwogdmFyIHJlZWxzPU1hdGgubWF4KDEsTWF0aC5jZWlsKENIQU5ORUxTLmxlbmd0aC9QRVIpKTtyZWVsPU1hdGgubWluKHJlZWws"
    "cmVlbHMtMSk7CiB2YXIgaXRlbXM9Q0hBTk5FTFMuc2xpY2UocmVlbCpQRVIscmVlbCpQRVIrUEVSKSxiYXNlPXJlZWwqUEVSLG49"
    "TWF0aC5tYXgoaXRlbXMubGVuZ3RoLDUpLHI9TWF0aC5yb3VuZCgxMzUvTWF0aC50YW4oTWF0aC5QSS9uKSkrNDA7CiBmb3IodmFy"
    "IGk9MDtpPG47aSsrKXt2YXIgaz1iYXNlKyhpJWl0ZW1zLmxlbmd0aCksYz1DSEFOTkVMU1trXSxkPWRvY3VtZW50LmNyZWF0ZUVs"
    "ZW1lbnQoImRpdiIpO2QuY2xhc3NOYW1lPSJzY3JlZW4iO2QuZGF0YXNldC5pPWs7CiAgZC5zdHlsZS50cmFuc2Zvcm09InJvdGF0"
    "ZVkoIisoMzYwL24qaSkrImRlZykgdHJhbnNsYXRlWigiK3IrInB4KSI7CiAgZC5pbm5lckhUTUw9JzxpbWcgYWx0PSIiIGxvYWRp"
    "bmc9ImxhenkiIHNyYz0iaHR0cHM6Ly9pbWcueW91dHViZS5jb20vdmkvJytlbmNvZGVVUklDb21wb25lbnQoYy5pZCkrJy9ocWRl"
    "ZmF1bHQuanBnIj48ZGl2IGNsYXNzPSJjaCI+Q0ggJysoaysxKSsnIMK3ICcrZXNjKGMuY2hhbm5lbCkrJzwvZGl2PjxkaXYgY2xh"
    "c3M9ImxhYiI+Jytlc2MoYy50aXRsZSkrJzwvZGl2Pic7CiAgZC5vbmNsaWNrPWZ1bmN0aW9uKCl7cGljaygrdGhpcy5kYXRhc2V0"
    "LmkpfTtyaW5nLmFwcGVuZENoaWxkKGQpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJlZWxMYWIiKS50ZXh0Q29udGVudD0i"
    "UmVlbCAiKyhyZWVsKzEpKyIgb2YgIityZWVscysiIMK3ICIrQ0hBTk5FTFMubGVuZ3RoKyIgdmlkZW9zIjsKIGlmKGN1cjxiYXNl"
    "fHxjdXI+PWJhc2UraXRlbXMubGVuZ3RoKWN1cj1iYXNlO21hcmsoKTtjaGFucygpfQp3aW5kb3cucmVlbFN0ZXA9ZnVuY3Rpb24o"
    "ZCl7dmFyIHJlZWxzPU1hdGgubWF4KDEsTWF0aC5jZWlsKENIQU5ORUxTLmxlbmd0aC9QRVIpKTtyZWVsPShyZWVsK2QrcmVlbHMp"
    "JXJlZWxzO2N1cj1yZWVsKlBFUjtidWlsZCgpfTsKZnVuY3Rpb24gbWFyaygpe0FycmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwo"
    "cmluZy5xdWVyeVNlbGVjdG9yQWxsKCIuc2NyZWVuIiksZnVuY3Rpb24ocyl7cy5jbGFzc0xpc3QudG9nZ2xlKCJvbiIsK3MuZGF0"
    "YXNldC5pPT09Y3VyKX0pOwogdmFyIGM9Q0hBTk5FTFNbY3VyXTtub3cudGV4dENvbnRlbnQ9IkNIICIrKGN1cisxKSsiIMK3ICIr"
    "Yy5jaGFubmVsKyIgwrcgIitjLnRpdGxlO3Zpc29yKCl9CmZ1bmN0aW9uIHBpY2soaSl7Y3VyPWk7bWFyaygpO3ZlbD0uMDN9CmZ1"
    "bmN0aW9uIGxvb3AoKXtpZihkcmFnPT09bnVsbCl7YW5nbGUrPXZlbDt2ZWwrPSggLjEyLXZlbCkqLjAxfXJpbmcuc3R5bGUudHJh"
    "bnNmb3JtPSJyb3RhdGVZKCIrYW5nbGUrImRlZykiO3JlcXVlc3RBbmltYXRpb25GcmFtZShsb29wKX1sb29wKCk7CnZhciBzdD1k"
    "b2N1bWVudC5nZXRFbGVtZW50QnlJZCgic3RhZ2UiKTsKc3QuYWRkRXZlbnRMaXN0ZW5lcigicG9pbnRlcmRvd24iLGZ1bmN0aW9u"
    "KGUpe2RyYWc9ZS5jbGllbnRYO2xhc3RYPWUuY2xpZW50WH0pOwphZGRFdmVudExpc3RlbmVyKCJwb2ludGVybW92ZSIsZnVuY3Rp"
    "b24oZSl7aWYoZHJhZyE9PW51bGwpe3ZhciBkeD1lLmNsaWVudFgtbGFzdFg7YW5nbGUrPWR4Ki40O3ZlbD1keCouNDtsYXN0WD1l"
    "LmNsaWVudFh9fSk7CmFkZEV2ZW50TGlzdGVuZXIoInBvaW50ZXJ1cCIsZnVuY3Rpb24oKXtkcmFnPW51bGx9KTsKd2luZG93LmFk"
    "ZFZpZGVvPWZ1bmN0aW9uKCl7dmFyIHU9cHJvbXB0KCJQYXN0ZSBhIFlvdVR1YmUgbGluayBhYm91dCBBSSBnb3Zlcm5hbmNlOiIp"
    "O2lmKCF1KXJldHVybjsKIHZhciBtPXUubWF0Y2goLyg/OnY9fHlvdXR1XC5iZVwvfGVtYmVkXC98c2hvcnRzXC8pKFtBLVphLXow"
    "LTlfLV17MTF9KS8pO2lmKCFtKXthbGVydCgiVGhhdCBkb2Vzbid0IGxvb2sgbGlrZSBhIFlvdVR1YmUgbGluay4iKTtyZXR1cm59"
    "CiB2YXIgdD1wcm9tcHQoIlRpdGxlIGZvciB0aGlzIHNjcmVlbjoiLCJOZXcgY2hhbm5lbCIpfHwiTmV3IGNoYW5uZWwiLG5jPXBy"
    "b21wdCgiQ2hhbm5lbCBuYW1lOiIsIllvdXIgY2hhbm5lbCIpfHwiWW91ciBjaGFubmVsIjsKIHZhciB2PXtpZDptWzFdLHRpdGxl"
    "OnQuc2xpY2UoMCw2MCksY2hhbm5lbDpuYy5zbGljZSgwLDMwKX07Q0hBTk5FTFMucHVzaCh2KTsKIHRyeXt2YXIgcz1KU09OLnBh"
    "cnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKCJzZWJiaS5jaW5lbWEiKXx8IltdIik7cy5wdXNoKHYpO2xvY2FsU3RvcmFnZS5zZXRJ"
    "dGVtKCJzZWJiaS5jaW5lbWEiLEpTT04uc3RyaW5naWZ5KHMuc2xpY2UoLTIwKSkpfWNhdGNoKGUpe30KIGN1cj1DSEFOTkVMUy5s"
    "ZW5ndGgtMTtyZWVsPU1hdGguZmxvb3IoY3VyL1BFUik7YnVpbGQoKX07CmZ1bmN0aW9uIHR2KCl7dmFyIGM9Q0hBTk5FTFNbY3Vy"
    "XSx0PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0diIpOwogaWYoc3Bpbm5pbmcpe3NwaW5uaW5nPWZhbHNlO3QuY2xhc3NMaXN0"
    "LnJlbW92ZSgic3BpbiIpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzcGluQnRuIikudGV4dENvbnRlbnQ9IlNwaW4gdGhlIFRW"
    "In0KIHQuY2xhc3NMaXN0LnJlbW92ZSgiaWRsZSIpOwogdC5pbm5lckhUTUw9JzxpZnJhbWUgc3JjPSJodHRwczovL3d3dy55b3V0"
    "dWJlLmNvbS9lbWJlZC8nK2VuY29kZVVSSUNvbXBvbmVudChjLmlkKSsnP2F1dG9wbGF5PTEmbXV0ZT0xJnJlbD0wJnBsYXlzaW5s"
    "aW5lPTEmbW9kZXN0YnJhbmRpbmc9MSIgcmVmZXJyZXJwb2xpY3k9InN0cmljdC1vcmlnaW4td2hlbi1jcm9zcy1vcmlnaW4iIGFs"
    "bG93PSJhY2NlbGVyb21ldGVyOyBhdXRvcGxheTsgY2xpcGJvYXJkLXdyaXRlOyBlbmNyeXB0ZWQtbWVkaWE7IGd5cm9zY29wZTsg"
    "cGljdHVyZS1pbi1waWN0dXJlOyB3ZWItc2hhcmU7IGZ1bGxzY3JlZW4iIGFsbG93ZnVsbHNjcmVlbiB0aXRsZT0iJytlc2MoYy50"
    "aXRsZSkrJyI+PC9pZnJhbWU+JzsKIHZhciBhPWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0dmxpbmsiKTthLmhyZWY9Imh0dHBz"
    "Oi8vd3d3LnlvdXR1YmUuY29tL3dhdGNoP3Y9IitlbmNvZGVVUklDb21wb25lbnQoYy5pZCk7YS50ZXh0Q29udGVudD0iUGxheWlu"
    "ZyBtdXRlZCDCtyB0YXAgdGhlIHZpZGVvIHRvIHVubXV0ZSDCtyBvciB3YXRjaCBvbiBZb3VUdWJlIOKGlyI7CiBkb2N1bWVudC5n"
    "ZXRFbGVtZW50QnlJZCgicm9vbU5vdyIpLnRleHRDb250ZW50PSJOT1cgU0hPV0lORyDCtyBDSCAiKyhjdXIrMSkrIiDCtyAiK2Mu"
    "Y2hhbm5lbCsiIMK3ICIrYy50aXRsZTtjaGFucygpO3Zpc29yKCl9CmZ1bmN0aW9uIGNoYW5zKCl7ZG9jdW1lbnQuZ2V0RWxlbWVu"
    "dEJ5SWQoImNoYW5zIikuaW5uZXJIVE1MPUNIQU5ORUxTLm1hcChmdW5jdGlvbihjLGkpe3JldHVybiAnPGJ1dHRvbiBjbGFzcz0i"
    "JysoaT09PWN1cj8ib24iOiIiKSsnIiBkYXRhLWk9IicraSsnIj5DSCAnKyhpKzEpKycgwrcgJytlc2MoYy5jaGFubmVsKSsnPC9i"
    "dXR0b24+J30pLmpvaW4oIiIpOwogQXJyYXkucHJvdG90eXBlLmZvckVhY2guY2FsbChkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxs"
    "KCIjY2hhbnMgYnV0dG9uIiksZnVuY3Rpb24oYil7Yi5vbmNsaWNrPWZ1bmN0aW9uKCl7Y3VyPStiLmRhdGFzZXQuaTtyZWVsPU1h"
    "dGguZmxvb3IoY3VyL1BFUik7dHYoKTtidWlsZCgpfX0pfQp3aW5kb3cuZW50ZXI9ZnVuY3Rpb24oKXtkb2N1bWVudC5nZXRFbGVt"
    "ZW50QnlJZCgibG9iYnkiKS5jbGFzc0xpc3QuYWRkKCJoaWRkZW4iKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicm9vbSIpLmNs"
    "YXNzTGlzdC5yZW1vdmUoImhpZGRlbiIpO3R2KCl9Owp3aW5kb3cubGVhdmU9ZnVuY3Rpb24oKXtkb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgidHYiKS5pbm5lckhUTUw9IiI7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJvb20iKS5jbGFzc0xpc3QuYWRkKCJoaWRk"
    "ZW4iKTtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibG9iYnkiKS5jbGFzc0xpc3QucmVtb3ZlKCJoaWRkZW4iKTttYXJrKCl9Owp3"
    "aW5kb3cuc3RlcD1mdW5jdGlvbihkKXtjdXI9KGN1citkK0NIQU5ORUxTLmxlbmd0aCklQ0hBTk5FTFMubGVuZ3RoO3JlZWw9TWF0"
    "aC5mbG9vcihjdXIvUEVSKTt0digpO2J1aWxkKCl9Owp3aW5kb3cudG9nZ2xlU3Bpbj1mdW5jdGlvbigpe3ZhciB0PWRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJ0diIpO3NwaW5uaW5nPSFzcGlubmluZzsKIGlmKHNwaW5uaW5nKXt0LmlubmVySFRNTD0nPGltZyBh"
    "bHQ9IiIgc3R5bGU9IndpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb3Zlcjtib3JkZXItcmFkaXVzOjRweCIgc3Jj"
    "PSJodHRwczovL2ltZy55b3V0dWJlLmNvbS92aS8nK2VuY29kZVVSSUNvbXBvbmVudChDSEFOTkVMU1tjdXJdLmlkKSsnL2hxZGVm"
    "YXVsdC5qcGciPic7dC5jbGFzc0xpc3QuYWRkKCJzcGluIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInR2bGluayIpLnRleHRD"
    "b250ZW50PSJUaGUgVFYgaXMgc3Bpbm5pbmcgwrcgdGFwIFN0b3Agc3Bpbm5pbmcgdG8gd2F0Y2gifQogZWxzZXt0LmNsYXNzTGlz"
    "dC5yZW1vdmUoInNwaW4iKTt0digpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNwaW5CdG4iKS50ZXh0Q29udGVudD1zcGlu"
    "bmluZz8iU3RvcCBzcGlubmluZyI6IlNwaW4gdGhlIFRWIn07CmJ1aWxkKCk7CmZldGNoKCcveC9jaW5lbWFmZWVkL2xpc3QnLHtj"
    "YWNoZTonbm8tc3RvcmUnfSkudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpe2lmKGQm"
    "JmQudmlkZW9zJiZkLnZpZGVvcy5sZW5ndGgpe3ZhciBleHRyYT1bXTt0cnl7ZXh0cmE9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2Uu"
    "Z2V0SXRlbSgnc2ViYmkuY2luZW1hJyl8fCdbXScpfWNhdGNoKGUpe31DSEFOTkVMUz1kLnZpZGVvcy5jb25jYXQoQXJyYXkuaXNB"
    "cnJheShleHRyYSk/ZXh0cmE6W10pO3JlZWw9MDtjdXI9MDtidWlsZCgpfX0pLmNhdGNoKGZ1bmN0aW9uKCl7fSk7Cn0pKCk7Cjwv"
    "c2NyaXB0PjwvYm9keT48L2h0bWw+Cg=="
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
