"""
modules/cinema.py  v1.1.0
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

VERSION = "1.1.0"

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
    "PjwvZGl2PgogPGRpdiBjbGFzcz0ibm93IiBpZD0ibm93Ij48L2Rpdj4KIDxkaXYgY2xhc3M9ImNyb3dkIiBpZD0iY3Jvd2QiPjwv"
    "ZGl2PgogPGRpdiBjbGFzcz0iYmFyIj48YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImVudGVyKCkiPkVudGVyIHRoZSByb29t"
    "IOKWtjwvYnV0dG9uPjxidXR0b24gY2xhc3M9ImJ0biBnaG9zdCIgb25jbGljaz0iYWRkVmlkZW8oKSI+KyBBZGQgYSB2aWRlbzwv"
    "YnV0dG9uPjxhIGNsYXNzPSJidG4gZ2hvc3QiIGhyZWY9Ii8iIHN0eWxlPSJ0ZXh0LWRlY29yYXRpb246bm9uZSI+SG9tZTwvYT48"
    "L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gY2xhc3M9InZpZXcgcm9vbSBoaWRkZW4iIGlkPSJyb29tIj4KIDxkaXYgY2xhc3M9"
    "ImZsb29yIj48L2Rpdj4KIDxoZWFkZXI+PGRpdiBjbGFzcz0iYnJhbmQiPnNlYmJpPGI+LnBybzwvYj4gwrcgVEhFIFNDUkVFTklO"
    "RyBST09NPC9kaXY+PGRpdiBjbGFzcz0ic3ViIiBpZD0icm9vbU5vdyI+PC9kaXY+PC9oZWFkZXI+CiA8ZGl2IGNsYXNzPSJ0dndy"
    "YXAiIHN0eWxlPSJmbGV4LWRpcmVjdGlvbjpjb2x1bW4iPjxkaXYgY2xhc3M9InR2IiBpZD0idHYiPjwvZGl2PjxhIGNsYXNzPSJ0"
    "dmxpbmsiIGlkPSJ0dmxpbmsiIHRhcmdldD0iX2JsYW5rIiByZWw9Im5vb3BlbmVyIj48L2E+PC9kaXY+CiA8ZGl2IGNsYXNzPSJj"
    "aGFucyIgaWQ9ImNoYW5zIj48L2Rpdj4KIDxkaXYgY2xhc3M9ImNyb3dkIiBpZD0iY3Jvd2QyIj48L2Rpdj4KIDxkaXYgY2xhc3M9"
    "ImJhciI+PGJ1dHRvbiBjbGFzcz0iYnRuIGdob3N0IiBvbmNsaWNrPSJzdGVwKC0xKSI+4peAIENoYW5uZWw8L2J1dHRvbj48YnV0"
    "dG9uIGNsYXNzPSJidG4gZ2hvc3QiIG9uY2xpY2s9InN0ZXAoMSkiPkNoYW5uZWwg4pa2PC9idXR0b24+PGJ1dHRvbiBjbGFzcz0i"
    "YnRuIGdob3N0IiBvbmNsaWNrPSJ0b2dnbGVTcGluKCkiIGlkPSJzcGluQnRuIj5TcGluIHRoZSBUVjwvYnV0dG9uPjxidXR0b24g"
    "Y2xhc3M9ImJ0biIgb25jbGljaz0ibGVhdmUoKSI+QmFjayB0byB0aGUgbG9iYnk8L2J1dHRvbj48L2Rpdj4KIDxkaXYgY2xhc3M9"
    "ImZvb3QiPlZpZGVvcyBwbGF5IGZyb20gdGhlaXIgb3JpZ2luYWwgY2hhbm5lbHMgb24gWW91VHViZS4gc2ViYmkucHJvIGRvZXMg"
    "bm90IG93biBvciBlbmRvcnNlIHRoaXJkLXBhcnR5IGNvbnRlbnQuPC9kaXY+Cjwvc2VjdGlvbj4KCjxzY3JpcHQ+CihmdW5jdGlv"
    "bigpewp2YXIgQ0hBTk5FTFM9Wwoge2lkOiJnTTFkTGRwRFI1MCIsdGl0bGU6IldoYXQgSXMgVHJ1c3R3b3J0aHkgQUk/IixjaGFu"
    "bmVsOiJOVklESUEifSwKIHtpZDoiZjZkeDNZaC1Ud3ciLHRpdGxlOiJXaGF0IGlzIEFJIGdvdmVybmFuY2U/IixjaGFubmVsOiJJ"
    "Qk0gUmVzZWFyY2gifSwKIHtpZDoiUTAyMEMtSncwbzgiLHRpdGxlOiJUaGUgSW1wb3J0YW5jZSBvZiBBSSBHb3Zlcm5hbmNlIixj"
    "aGFubmVsOiJJQk0gVGVjaG5vbG9neSJ9Cl07CnRyeXt2YXIgc2F2ZWQ9SlNPTi5wYXJzZShsb2NhbFN0b3JhZ2UuZ2V0SXRlbSgi"
    "c2ViYmkuY2luZW1hIil8fCJbXSIpO2lmKEFycmF5LmlzQXJyYXkoc2F2ZWQpKUNIQU5ORUxTPUNIQU5ORUxTLmNvbmNhdChzYXZl"
    "ZCl9Y2F0Y2goZSl7fQp2YXIgY3VyPTAsYW5nbGU9MCx2ZWw9LjEyLGRyYWc9bnVsbCxsYXN0WD0wLHNwaW5uaW5nPWZhbHNlOwp2"
    "YXIgcmluZz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicmluZyIpLG5vdz1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgibm93Iik7"
    "CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2UoL1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybnsiJiI6"
    "IiZhbXA7IiwiPCI6IiZsdDsiLCI+IjoiJmd0OyIsJyInOiImcXVvdDsifVtjXX0pfQpmdW5jdGlvbiBjcm93ZChlbCxuKXt2YXIg"
    "aD0iIjtmb3IodmFyIGk9MDtpPG47aSsrKWgrPSc8ZGl2IGNsYXNzPSJib3QiPjxkaXYgY2xhc3M9ImhlYWQiPjxkaXYgY2xhc3M9"
    "InZpc29yIj48L2Rpdj48L2Rpdj48ZGl2IGNsYXNzPSJib2R5Ij48L2Rpdj48ZGl2IGNsYXNzPSJzZWF0Ij48L2Rpdj48L2Rpdj4n"
    "O2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKGVsKS5pbm5lckhUTUw9aH0KY3Jvd2QoImNyb3dkIixNYXRoLm1pbig5LE1hdGguZmxv"
    "b3IoaW5uZXJXaWR0aC80OCkpKTtjcm93ZCgiY3Jvd2QyIixNYXRoLm1pbig5LE1hdGguZmxvb3IoaW5uZXJXaWR0aC80OCkpKTsK"
    "dmFyIFZJUz1bIiNjOWE4NGMiLCIjN2ZlM2IwIiwiIzhmZDBmZiIsIiNmZjhhODAiLCIjZDU5YmZmIl07CmZ1bmN0aW9uIHZpc29y"
    "KCl7dmFyIGM9VklTW2N1ciVWSVMubGVuZ3RoXTtBcnJheS5wcm90b3R5cGUuZm9yRWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2Vs"
    "ZWN0b3JBbGwoIi52aXNvciIpLGZ1bmN0aW9uKHYpe3Yuc3R5bGUuYmFja2dyb3VuZD1jO3Yuc3R5bGUuYm94U2hhZG93PSIwIDAg"
    "OHB4ICIrY30pfQpmdW5jdGlvbiBidWlsZCgpewogQXJyYXkucHJvdG90eXBlLmZvckVhY2guY2FsbChyaW5nLnF1ZXJ5U2VsZWN0"
    "b3JBbGwoIi5zY3JlZW4iKSxmdW5jdGlvbihzKXtzLnJlbW92ZSgpfSk7CiB2YXIgbj1NYXRoLm1heChDSEFOTkVMUy5sZW5ndGgs"
    "NSkscj1NYXRoLnJvdW5kKDEzNS9NYXRoLnRhbihNYXRoLlBJL24pKSs0MDsKIGZvcih2YXIgaT0wO2k8bjtpKyspe3ZhciBjPUNI"
    "QU5ORUxTW2klQ0hBTk5FTFMubGVuZ3RoXSxkPWRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoImRpdiIpO2QuY2xhc3NOYW1lPSJzY3Jl"
    "ZW4iO2QuZGF0YXNldC5pPWklQ0hBTk5FTFMubGVuZ3RoOwogIGQuc3R5bGUudHJhbnNmb3JtPSJyb3RhdGVZKCIrKDM2MC9uKmkp"
    "KyJkZWcpIHRyYW5zbGF0ZVooIityKyJweCkiOwogIGQuaW5uZXJIVE1MPSc8aW1nIGFsdD0iIiBzcmM9Imh0dHBzOi8vaW1nLnlv"
    "dXR1YmUuY29tL3ZpLycrZW5jb2RlVVJJQ29tcG9uZW50KGMuaWQpKycvaHFkZWZhdWx0LmpwZyI+PGRpdiBjbGFzcz0iY2giPkNI"
    "ICcrKChpJUNIQU5ORUxTLmxlbmd0aCkrMSkrJyDCtyAnK2VzYyhjLmNoYW5uZWwpKyc8L2Rpdj48ZGl2IGNsYXNzPSJsYWIiPicr"
    "ZXNjKGMudGl0bGUpKyc8L2Rpdj4nOwogIGQub25jbGljaz1mdW5jdGlvbigpe3BpY2soK3RoaXMuZGF0YXNldC5pKX07cmluZy5h"
    "cHBlbmRDaGlsZChkKX0KIG1hcmsoKTtjaGFucygpfQpmdW5jdGlvbiBtYXJrKCl7QXJyYXkucHJvdG90eXBlLmZvckVhY2guY2Fs"
    "bChyaW5nLnF1ZXJ5U2VsZWN0b3JBbGwoIi5zY3JlZW4iKSxmdW5jdGlvbihzKXtzLmNsYXNzTGlzdC50b2dnbGUoIm9uIiwrcy5k"
    "YXRhc2V0Lmk9PT1jdXIpfSk7CiB2YXIgYz1DSEFOTkVMU1tjdXJdO25vdy50ZXh0Q29udGVudD0iQ0ggIisoY3VyKzEpKyIgwrcg"
    "IitjLmNoYW5uZWwrIiDCtyAiK2MudGl0bGU7dmlzb3IoKX0KZnVuY3Rpb24gcGljayhpKXtjdXI9aTttYXJrKCk7dmVsPS4wM30K"
    "ZnVuY3Rpb24gbG9vcCgpe2lmKGRyYWc9PT1udWxsKXthbmdsZSs9dmVsO3ZlbCs9KCAuMTItdmVsKSouMDF9cmluZy5zdHlsZS50"
    "cmFuc2Zvcm09InJvdGF0ZVkoIithbmdsZSsiZGVnKSI7cmVxdWVzdEFuaW1hdGlvbkZyYW1lKGxvb3ApfWxvb3AoKTsKdmFyIHN0"
    "PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJzdGFnZSIpOwpzdC5hZGRFdmVudExpc3RlbmVyKCJwb2ludGVyZG93biIsZnVuY3Rp"
    "b24oZSl7ZHJhZz1lLmNsaWVudFg7bGFzdFg9ZS5jbGllbnRYfSk7CmFkZEV2ZW50TGlzdGVuZXIoInBvaW50ZXJtb3ZlIixmdW5j"
    "dGlvbihlKXtpZihkcmFnIT09bnVsbCl7dmFyIGR4PWUuY2xpZW50WC1sYXN0WDthbmdsZSs9ZHgqLjQ7dmVsPWR4Ki40O2xhc3RY"
    "PWUuY2xpZW50WH19KTsKYWRkRXZlbnRMaXN0ZW5lcigicG9pbnRlcnVwIixmdW5jdGlvbigpe2RyYWc9bnVsbH0pOwp3aW5kb3cu"
    "YWRkVmlkZW89ZnVuY3Rpb24oKXt2YXIgdT1wcm9tcHQoIlBhc3RlIGEgWW91VHViZSBsaW5rIGFib3V0IEFJIGdvdmVybmFuY2U6"
    "Iik7aWYoIXUpcmV0dXJuOwogdmFyIG09dS5tYXRjaCgvKD86dj18eW91dHVcLmJlXC98ZW1iZWRcL3xzaG9ydHNcLykoW0EtWmEt"
    "ejAtOV8tXXsxMX0pLyk7aWYoIW0pe2FsZXJ0KCJUaGF0IGRvZXNuJ3QgbG9vayBsaWtlIGEgWW91VHViZSBsaW5rLiIpO3JldHVy"
    "bn0KIHZhciB0PXByb21wdCgiVGl0bGUgZm9yIHRoaXMgc2NyZWVuOiIsIk5ldyBjaGFubmVsIil8fCJOZXcgY2hhbm5lbCIsbmM9"
    "cHJvbXB0KCJDaGFubmVsIG5hbWU6IiwiWW91ciBjaGFubmVsIil8fCJZb3VyIGNoYW5uZWwiOwogdmFyIHY9e2lkOm1bMV0sdGl0"
    "bGU6dC5zbGljZSgwLDYwKSxjaGFubmVsOm5jLnNsaWNlKDAsMzApfTtDSEFOTkVMUy5wdXNoKHYpOwogdHJ5e3ZhciBzPUpTT04u"
    "cGFyc2UobG9jYWxTdG9yYWdlLmdldEl0ZW0oInNlYmJpLmNpbmVtYSIpfHwiW10iKTtzLnB1c2godik7bG9jYWxTdG9yYWdlLnNl"
    "dEl0ZW0oInNlYmJpLmNpbmVtYSIsSlNPTi5zdHJpbmdpZnkocy5zbGljZSgtMjApKSl9Y2F0Y2goZSl7fQogY3VyPUNIQU5ORUxT"
    "Lmxlbmd0aC0xO2J1aWxkKCl9OwpmdW5jdGlvbiB0digpe3ZhciBjPUNIQU5ORUxTW2N1cl0sdD1kb2N1bWVudC5nZXRFbGVtZW50"
    "QnlJZCgidHYiKTsKIGlmKHNwaW5uaW5nKXtzcGlubmluZz1mYWxzZTt0LmNsYXNzTGlzdC5yZW1vdmUoInNwaW4iKTtkb2N1bWVu"
    "dC5nZXRFbGVtZW50QnlJZCgic3BpbkJ0biIpLnRleHRDb250ZW50PSJTcGluIHRoZSBUViJ9CiB0LmNsYXNzTGlzdC5yZW1vdmUo"
    "ImlkbGUiKTsKIHQuaW5uZXJIVE1MPSc8aWZyYW1lIHNyYz0iaHR0cHM6Ly93d3cueW91dHViZS5jb20vZW1iZWQvJytlbmNvZGVV"
    "UklDb21wb25lbnQoYy5pZCkrJz9hdXRvcGxheT0xJm11dGU9MSZyZWw9MCZwbGF5c2lubGluZT0xJm1vZGVzdGJyYW5kaW5nPTEi"
    "IHJlZmVycmVycG9saWN5PSJzdHJpY3Qtb3JpZ2luLXdoZW4tY3Jvc3Mtb3JpZ2luIiBhbGxvdz0iYWNjZWxlcm9tZXRlcjsgYXV0"
    "b3BsYXk7IGNsaXBib2FyZC13cml0ZTsgZW5jcnlwdGVkLW1lZGlhOyBneXJvc2NvcGU7IHBpY3R1cmUtaW4tcGljdHVyZTsgd2Vi"
    "LXNoYXJlOyBmdWxsc2NyZWVuIiBhbGxvd2Z1bGxzY3JlZW4gdGl0bGU9IicrZXNjKGMudGl0bGUpKyciPjwvaWZyYW1lPic7CiB2"
    "YXIgYT1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgidHZsaW5rIik7YS5ocmVmPSJodHRwczovL3d3dy55b3V0dWJlLmNvbS93YXRj"
    "aD92PSIrZW5jb2RlVVJJQ29tcG9uZW50KGMuaWQpO2EudGV4dENvbnRlbnQ9IlBsYXlpbmcgbXV0ZWQgwrcgdGFwIHRoZSB2aWRl"
    "byB0byB1bm11dGUgwrcgb3Igd2F0Y2ggb24gWW91VHViZSDihpciOwogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInJvb21Ob3ci"
    "KS50ZXh0Q29udGVudD0iTk9XIFNIT1dJTkcgwrcgQ0ggIisoY3VyKzEpKyIgwrcgIitjLmNoYW5uZWwrIiDCtyAiK2MudGl0bGU7"
    "Y2hhbnMoKTt2aXNvcigpfQpmdW5jdGlvbiBjaGFucygpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJjaGFucyIpLmlubmVySFRN"
    "TD1DSEFOTkVMUy5tYXAoZnVuY3Rpb24oYyxpKXtyZXR1cm4gJzxidXR0b24gY2xhc3M9IicrKGk9PT1jdXI/Im9uIjoiIikrJyIg"
    "ZGF0YS1pPSInK2krJyI+Q0ggJysoaSsxKSsnIMK3ICcrZXNjKGMuY2hhbm5lbCkrJzwvYnV0dG9uPid9KS5qb2luKCIiKTsKIEFy"
    "cmF5LnByb3RvdHlwZS5mb3JFYWNoLmNhbGwoZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgiI2NoYW5zIGJ1dHRvbiIpLGZ1bmN0"
    "aW9uKGIpe2Iub25jbGljaz1mdW5jdGlvbigpe2N1cj0rYi5kYXRhc2V0Lmk7dHYoKTttYXJrKCl9fSl9CndpbmRvdy5lbnRlcj1m"
    "dW5jdGlvbigpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJsb2JieSIpLmNsYXNzTGlzdC5hZGQoImhpZGRlbiIpO2RvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJyb29tIikuY2xhc3NMaXN0LnJlbW92ZSgiaGlkZGVuIik7dHYoKX07CndpbmRvdy5sZWF2ZT1mdW5j"
    "dGlvbigpe2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJ0diIpLmlubmVySFRNTD0iIjtkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgi"
    "cm9vbSIpLmNsYXNzTGlzdC5hZGQoImhpZGRlbiIpO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCJsb2JieSIpLmNsYXNzTGlzdC5y"
    "ZW1vdmUoImhpZGRlbiIpO21hcmsoKX07CndpbmRvdy5zdGVwPWZ1bmN0aW9uKGQpe2N1cj0oY3VyK2QrQ0hBTk5FTFMubGVuZ3Ro"
    "KSVDSEFOTkVMUy5sZW5ndGg7dHYoKTttYXJrKCl9Owp3aW5kb3cudG9nZ2xlU3Bpbj1mdW5jdGlvbigpe3ZhciB0PWRvY3VtZW50"
    "LmdldEVsZW1lbnRCeUlkKCJ0diIpO3NwaW5uaW5nPSFzcGlubmluZzsKIGlmKHNwaW5uaW5nKXt0LmlubmVySFRNTD0nPGltZyBh"
    "bHQ9IiIgc3R5bGU9IndpZHRoOjEwMCU7aGVpZ2h0OjEwMCU7b2JqZWN0LWZpdDpjb3Zlcjtib3JkZXItcmFkaXVzOjRweCIgc3Jj"
    "PSJodHRwczovL2ltZy55b3V0dWJlLmNvbS92aS8nK2VuY29kZVVSSUNvbXBvbmVudChDSEFOTkVMU1tjdXJdLmlkKSsnL2hxZGVm"
    "YXVsdC5qcGciPic7dC5jbGFzc0xpc3QuYWRkKCJzcGluIik7ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInR2bGluayIpLnRleHRD"
    "b250ZW50PSJUaGUgVFYgaXMgc3Bpbm5pbmcgwrcgdGFwIFN0b3Agc3Bpbm5pbmcgdG8gd2F0Y2gifQogZWxzZXt0LmNsYXNzTGlz"
    "dC5yZW1vdmUoInNwaW4iKTt0digpfQogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoInNwaW5CdG4iKS50ZXh0Q29udGVudD1zcGlu"
    "bmluZz8iU3RvcCBzcGlubmluZyI6IlNwaW4gdGhlIFRWIn07CmJ1aWxkKCk7Cn0pKCk7Cjwvc2NyaXB0PjwvYm9keT48L2h0bWw+"
    "Cg=="
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
