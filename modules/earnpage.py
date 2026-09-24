"""
modules/earnpage.py  v1.0.0
The creator's withdrawal page at /earn, plus a "My earnings" button on the
homepage.

  /earn   claim a creator name (get a private key), see earnings and paid
          unlocks, link a bank through Stripe, withdraw to it, and see every
          past withdrawal with its proof in the chain.

Talks to modules/credits.py (v1.2.0 or later) over /c/creator/.

The homepage button is added to the page served at / as it goes out, so
index.html and homelink.py are not touched.

Page module, same family as creditspage.py: a runtime do_GET patch.
Armed by /x/earnpage/status after each deploy.
"""

import base64
import io
import re
import sys

VERSION = "1.0.0"

_HTML_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPk15IGVhcm5pbmdzIOKAlCBNb25vcCBTdHVkaW88L3RpdGxlPgo8bWV0YSBuYW1lPSJkZXNjcmlwdGlvbiIgY29udGVudD0i"
    "WW91ciBNb25vcCBTdHVkaW8gZWFybmluZ3MuIEV2ZXJ5IHVubG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgc3RyYWlnaHQgdG8g"
    "eW91ciBiYW5rLiI+CjxsaW5rIGhyZWY9Imh0dHBzOi8vZm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9VW5ib3VuZGVk"
    "OndnaHRANjAwOzgwMCZmYW1pbHk9RmlndHJlZTp3Z2h0QDUwMDs3MDAmZGlzcGxheT1zd2FwIiByZWw9InN0eWxlc2hlZXQiPgo8"
    "c3R5bGU+Cjpyb290ey0tYmc6IzJiM2JmZjstLWRlZXA6IzExMTY1ZTstLXBpbms6I2ZmM2Q4YjstLXN1bjojZmZlMTRkOy0tbWlu"
    "dDojM2RmZmIyOy0td2hpdGU6I2ZmZjstLXNvZnQ6cmdiYSgyNTUsMjU1LDI1NSwuNzgpOwotLWQ6J1VuYm91bmRlZCcsJ0FyaWFs"
    "IEJsYWNrJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXQ6J0ZpZ3RyZWUnLHN5c3RlbS11aSwtYXBwbGUtc3lzdGVtLCdTZWdvZSBV"
    "SScsc2Fucy1zZXJpZn0KQG1lZGlhIChwcmVmZXJzLWNvbG9yLXNjaGVtZTogZGFyayl7OnJvb3Q6bm90KFtkYXRhLXRoZW1lPSJs"
    "aWdodCJdKXstLWJnOiMyYjNiZmZ9fQo6cm9vdFtkYXRhLXRoZW1lPSJkYXJrIl17LS1iZzojMmIzYmZmfQo6cm9vdHtib3gtc2l6"
    "aW5nOmJvcmRlci1ib3g7cGFkZGluZy10b3A6ZW52KHNhZmUtYXJlYS1pbnNldC10b3AsMHB4KTtwYWRkaW5nLWJvdHRvbTplbnYo"
    "c2FmZS1hcmVhLWluc2V0LWJvdHRvbSwwcHgpfQpodG1se3Njcm9sbC1wYWRkaW5nLXRvcDplbnYoc2FmZS1hcmVhLWluc2V0LXRv"
    "cCwwcHgpfQoqe2JveC1zaXppbmc6Ym9yZGVyLWJveDttYXJnaW46MDtwYWRkaW5nOjA7LXdlYmtpdC10YXAtaGlnaGxpZ2h0LWNv"
    "bG9yOnRyYW5zcGFyZW50fQpib2R5e2JhY2tncm91bmQ6dmFyKC0tYmcpO2NvbG9yOnZhcigtLXdoaXRlKTtmb250LWZhbWlseTp2"
    "YXIoLS10KTtsaW5lLWhlaWdodDoxLjU7bWluLWhlaWdodDoxMDAlfQoud3JhcHttYXgtd2lkdGg6NTYwcHg7bWFyZ2luOjAgYXV0"
    "bztwYWRkaW5nOjE4cHggMjBweCA2MHB4fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2Vlbjth"
    "bGlnbi1pdGVtczpjZW50ZXI7Zm9udC13ZWlnaHQ6NzAwfQoudG9wIGF7Y29sb3I6dmFyKC0td2hpdGUpO3RleHQtZGVjb3JhdGlv"
    "bjpub25lO29wYWNpdHk6Ljg1O21hcmdpbi1sZWZ0OjE2cHg7Zm9udC1zaXplOjE0cHh9Ci5icmFuZHtmb250LWZhbWlseTp2YXIo"
    "LS1kKTtmb250LXNpemU6MTVweH0KaDF7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFt"
    "cCgzMHB4LDguNXZ3LDQ2cHgpO2xpbmUtaGVpZ2h0OjEuMDI7bWFyZ2luOjI2cHggMCAxMHB4fQoudGFne2Rpc3BsYXk6aW5saW5l"
    "LWJsb2NrO3BhZGRpbmc6LjA1ZW0gLjNlbTtib3JkZXItcmFkaXVzOi4xOGVtO3RyYW5zZm9ybTpyb3RhdGUoLTJkZWcpO2JhY2tn"
    "cm91bmQ6dmFyKC0tcGluayl9CnAubGVhZHtjb2xvcjp2YXIoLS1zb2Z0KTtmb250LXNpemU6MTdweDttYXgtd2lkdGg6NDRjaH0K"
    "LmNhcmR7YmFja2dyb3VuZDp2YXIoLS1kZWVwKTtib3JkZXItcmFkaXVzOjIycHg7cGFkZGluZzoyMnB4O21hcmdpbi10b3A6MThw"
    "eH0KLmNhcmQgaDJ7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC1zaXplOjE5cHg7bWFyZ2luLWJvdHRvbTo4cHh9Ci5jYXJkIHB7"
    "Y29sb3I6dmFyKC0tc29mdCk7Zm9udC1zaXplOjE1cHh9CmxhYmVse2Rpc3BsYXk6YmxvY2s7Zm9udC13ZWlnaHQ6NzAwO2ZvbnQt"
    "c2l6ZToxNHB4O21hcmdpbjoxNHB4IDAgNnB4fQppbnB1dHt3aWR0aDoxMDAlO3BhZGRpbmc6MTVweCAxNnB4O2JvcmRlci1yYWRp"
    "dXM6MTRweDtib3JkZXI6MDtmb250OjcwMCAxN3B4IHZhcigtLXQpO2NvbG9yOnZhcigtLWRlZXApO2JhY2tncm91bmQ6I2ZmZn0K"
    "aW5wdXQ6Zm9jdXN7b3V0bGluZTozcHggc29saWQgdmFyKC0tc3VuKX0KYnV0dG9uLC5idG57ZGlzcGxheTppbmxpbmUtYmxvY2s7"
    "d2lkdGg6MTAwJTttYXJnaW4tdG9wOjE0cHg7cGFkZGluZzoxNnB4IDE4cHg7Ym9yZGVyLXJhZGl1czo5OTlweDtib3JkZXI6MDtj"
    "dXJzb3I6cG9pbnRlcjsKIGZvbnQ6ODAwIDE2cHggdmFyKC0tZCk7YmFja2dyb3VuZDp2YXIoLS1zdW4pO2NvbG9yOiMxYTEzMDA7"
    "dGV4dC1hbGlnbjpjZW50ZXI7dGV4dC1kZWNvcmF0aW9uOm5vbmV9CmJ1dHRvbjpmb2N1cy12aXNpYmxlLC5idG46Zm9jdXMtdmlz"
    "aWJsZXtvdXRsaW5lOjNweCBzb2xpZCAjZmZmO291dGxpbmUtb2Zmc2V0OjNweH0KYnV0dG9uLnBpbmt7YmFja2dyb3VuZDp2YXIo"
    "LS1waW5rKTtjb2xvcjojZmZmfQpidXR0b24uZ2hvc3R7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlcjoy"
    "cHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuNCl9CmJ1dHRvbjpkaXNhYmxlZHtvcGFjaXR5Oi40NTtjdXJzb3I6bm90LWFsbG93"
    "ZWR9Ci5iYWx7Zm9udC1mYW1pbHk6dmFyKC0tZCk7Zm9udC13ZWlnaHQ6ODAwO2ZvbnQtc2l6ZTpjbGFtcCg1NHB4LDE3dncsODhw"
    "eCk7bGluZS1oZWlnaHQ6MTtjb2xvcjp2YXIoLS1zdW4pO21hcmdpbjo2cHggMCA0cHg7Zm9udC12YXJpYW50LW51bWVyaWM6dGFi"
    "dWxhci1udW1zfQoucm93e2Rpc3BsYXk6ZmxleDtnYXA6MTBweH0ucm93Pip7ZmxleDoxfQouc3RhdHtiYWNrZ3JvdW5kOnJnYmEo"
    "MjU1LDI1NSwyNTUsLjA4KTtib3JkZXItcmFkaXVzOjE2cHg7cGFkZGluZzoxMnB4IDE0cHh9Ci5zdGF0IGJ7ZGlzcGxheTpibG9j"
    "aztmb250LWZhbWlseTp2YXIoLS1kKTtmb250LXNpemU6MjJweH0uc3RhdCBzcGFue2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigt"
    "LXNvZnQpfQoua2V5Ym94e21hcmdpbi10b3A6MTJweDtiYWNrZ3JvdW5kOiNmZmY7Y29sb3I6dmFyKC0tZGVlcCk7Ym9yZGVyLXJh"
    "ZGl1czoxNHB4O3BhZGRpbmc6MTRweDtmb250OjcwMCAxNHB4IHVpLW1vbm9zcGFjZSxNZW5sbyxtb25vc3BhY2U7d29yZC1icmVh"
    "azpicmVhay1hbGx9Ci5tc2d7bWFyZ2luLXRvcDoxNHB4O3BhZGRpbmc6MTRweCAxNnB4O2JvcmRlci1yYWRpdXM6MTRweDtiYWNr"
    "Z3JvdW5kOnJnYmEoMjU1LDI1NSwyNTUsLjEyKTtmb250LXdlaWdodDo3MDA7ZGlzcGxheTpub25lfQoubXNnLm9ue2Rpc3BsYXk6"
    "YmxvY2t9Lm1zZy5nb29ke2JhY2tncm91bmQ6dmFyKC0tbWludCk7Y29sb3I6IzA3MzAxZn0ubXNnLmJhZHtiYWNrZ3JvdW5kOnZh"
    "cigtLXBpbmspfQouc3RhdGV7ZGlzcGxheTpmbGV4O2FsaWduLWl0ZW1zOmNlbnRlcjtnYXA6MTBweDtmb250LXdlaWdodDo3MDA7"
    "bWFyZ2luLXRvcDo2cHh9Ci5kb3R7d2lkdGg6MTJweDtoZWlnaHQ6MTJweDtib3JkZXItcmFkaXVzOjUwJTtiYWNrZ3JvdW5kOnZh"
    "cigtLXN1bik7ZmxleDpub25lfS5kb3Qub2t7YmFja2dyb3VuZDp2YXIoLS1taW50KX0KLmxpc3QgZGl2e2Rpc3BsYXk6ZmxleDtq"
    "dXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtwYWRkaW5nOjEwcHggMDtib3JkZXItdG9wOjFweCBzb2xpZCByZ2JhKDI1NSwy"
    "NTUsMjU1LC4xMik7Zm9udC1zaXplOjE1cHh9Ci5saXN0IGF7Y29sb3I6dmFyKC0tbWludCl9Ci5zbWFsbHtmb250LXNpemU6MTNw"
    "eDtjb2xvcjp2YXIoLS1zb2Z0KTttYXJnaW4tdG9wOjEwcHh9Ci5zbWFsbCBhe2NvbG9yOiNmZmZ9CltoaWRkZW5de2Rpc3BsYXk6"
    "bm9uZSFpbXBvcnRhbnR9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0b3AiPjxk"
    "aXYgY2xhc3M9ImJyYW5kIj5Nb25vcCBTdHVkaW88L2Rpdj48bmF2PjxhIGhyZWY9Ii9jcmVhdGUiPlN0dWRpbzwvYT48YSBocmVm"
    "PSIvY2luZW1hIj5DaW5lbWE8L2E+PGEgaHJlZj0iLyI+SG9tZTwvYT48L25hdj48L2Rpdj4KCjxzZWN0aW9uIGlkPSJqb2luIiBo"
    "aWRkZW4+CiAgPGgxPkdldCBwYWlkIGZvciA8c3BhbiBjbGFzcz0idGFnIj55b3VyIHZpZGVvcy48L3NwYW4+PC9oMT4KICA8cCBj"
    "bGFzcz0ibGVhZCI+Q2xhaW0geW91ciBjcmVhdG9yIG5hbWUsIGxvY2sgeW91ciB2aWRlb3Mgd2l0aCBpdCwgYW5kIGV2ZXJ5IHVu"
    "bG9jayBwYXlzIHlvdSA3cC4gV2l0aGRyYXcgdG8geW91ciBiYW5rIHdoZW5ldmVyIHlvdSBsaWtlLjwvcD4KICA8ZGl2IGNsYXNz"
    "PSJjYXJkIj4KICAgIDxoMj5DbGFpbSB5b3VyIGNyZWF0b3IgbmFtZTwvaDI+CiAgICA8cD5Vc2UgZXhhY3RseSB0aGlzIG5hbWUg"
    "aW4gdGhlIHN0dWRpbyB3aGVuIHlvdSBsb2NrIGEgdmlkZW8uIFRoYXQncyBob3cgeW91ciBlYXJuaW5ncyBmaW5kIHlvdS48L3A+"
    "CiAgICA8bGFiZWwgZm9yPSJuYW1lIj5DcmVhdG9yIG5hbWU8L2xhYmVsPgogICAgPGlucHV0IGlkPSJuYW1lIiBtYXhsZW5ndGg9"
    "IjQwIiBhdXRvY29tcGxldGU9Im9mZiIgcGxhY2Vob2xkZXI9ImUuZy4gS2lja2ZsaXBLYWkiPgogICAgPGJ1dHRvbiBpZD0iam9p"
    "bkJ0biI+Q2xhaW0gbXkgbmFtZTwvYnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgPGgyPkFscmVhZHkg"
    "aGF2ZSBhIGtleT88L2gyPgogICAgPHA+U2lnbiBpbiBvbiB0aGlzIGRldmljZSB3aXRoIHRoZSBrZXkgeW91IHNhdmVkLjwvcD4K"
    "ICAgIDxsYWJlbCBmb3I9ImtleUluIj5Zb3VyIGtleTwvbGFiZWw+CiAgICA8aW5wdXQgaWQ9ImtleUluIiBhdXRvY29tcGxldGU9"
    "Im9mZiIgcGxhY2Vob2xkZXI9ImNrX+KApiI+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImtleUJ0biI+U2lnbiBpbjwv"
    "YnV0dG9uPgogIDwvZGl2PgogIDxkaXYgY2xhc3M9Im1zZyIgaWQ9ImpvaW5Nc2ciPjwvZGl2Pgo8L3NlY3Rpb24+Cgo8c2VjdGlv"
    "biBpZD0ic2F2ZWQiIGhpZGRlbj4KICA8aDE+U2F2ZSA8c3BhbiBjbGFzcz0idGFnIj55b3VyIGtleS48L3NwYW4+PC9oMT4KICA8"
    "cCBjbGFzcz0ibGVhZCI+VGhpcyBrZXkgaXMgaG93IHlvdSB3aXRoZHJhdyB5b3VyIG1vbmV5LiBJdCdzIHNhdmVkIG9uIHRoaXMg"
    "cGhvbmUsIGJ1dCBrZWVwIGEgY29weSBzb21ld2hlcmUgc2FmZS4gSWYgeW91IGxvc2UgaXQsIG5vYm9keSBjYW4gZ2V0IHlvdXIg"
    "ZWFybmluZ3MgYmFjay48L3A+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDIgaWQ9InNhdmVkTmFtZSI+PC9oMj4KICAgIDxk"
    "aXYgY2xhc3M9ImtleWJveCIgaWQ9InNhdmVkS2V5Ij48L2Rpdj4KICAgIDxidXR0b24gaWQ9ImNvcHlCdG4iPkNvcHkgbXkga2V5"
    "PC9idXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJnaG9zdCIgaWQ9ImRvbmVCdG4iPkkndmUgc2F2ZWQgaXQ8L2J1dHRvbj4KICA8"
    "L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9ImRhc2giIGhpZGRlbj4KICA8aDEgaWQ9ImhlbGxvIj5Zb3VyIGVhcm5pbmdz"
    "PC9oMT4KICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgIDxwPlJlYWR5IHRvIHdpdGhkcmF3PC9wPgogICAgPGRpdiBjbGFzcz0iYmFs"
    "IiBpZD0iYmFsIj7CozAuMDA8L2Rpdj4KICAgIDxkaXYgY2xhc3M9InJvdyIgc3R5bGU9Im1hcmdpbi10b3A6MTJweCI+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiIGlkPSJ2aWV3cyI+MDwvYj48c3Bhbj5wYWlkIHVubG9ja3M8L3NwYW4+PC9kaXY+CiAgICAg"
    "IDxkaXYgY2xhc3M9InN0YXQiPjxiPjdwPC9iPjxzcGFuPnBlciB1bmxvY2s8L3NwYW4+PC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rp"
    "dj4KICA8ZGl2IGNsYXNzPSJjYXJkIiBpZD0icGF5Q2FyZCI+CiAgICA8aDI+V2l0aGRyYXcgdG8geW91ciBiYW5rPC9oMj4KICAg"
    "IDxkaXYgY2xhc3M9InN0YXRlIj48c3BhbiBjbGFzcz0iZG90IiBpZD0iZG90Ij48L3NwYW4+PHNwYW4gaWQ9InN0YXRlVGV4dCI+"
    "Q2hlY2tpbmfigKY8L3NwYW4+PC9kaXY+CiAgICA8YnV0dG9uIGlkPSJzZXR1cEJ0biIgaGlkZGVuPlNldCB1cCBwYXlvdXRzPC9i"
    "dXR0b24+CiAgICA8YnV0dG9uIGNsYXNzPSJwaW5rIiBpZD0id2l0aGRyYXdCdG4iIGhpZGRlbj5XaXRoZHJhdzwvYnV0dG9uPgog"
    "ICAgPGJ1dHRvbiBjbGFzcz0iZ2hvc3QiIGlkPSJzdHJpcGVCdG4iIGhpZGRlbj5PcGVuIG15IFN0cmlwZSBhY2NvdW50PC9idXR0"
    "b24+CiAgICA8cCBjbGFzcz0ic21hbGwiIGlkPSJwYXlOb3RlIj5QYXlvdXRzIGdvIHRocm91Z2ggU3RyaXBlLCBzdHJhaWdodCB0"
    "byB5b3VyIGJhbmsuIFVuZGVyIDE4PyBBIHBhcmVudCBvciBndWFyZGlhbiBzZXRzIHRoaXMgdXAgd2l0aCB0aGVpciBkZXRhaWxz"
    "LjwvcD4KICA8L2Rpdj4KICA8ZGl2IGNsYXNzPSJtc2ciIGlkPSJkYXNoTXNnIj48L2Rpdj4KICA8ZGl2IGNsYXNzPSJjYXJkIj4K"
    "ICAgIDxoMj5QYXN0IHdpdGhkcmF3YWxzPC9oMj4KICAgIDxkaXYgY2xhc3M9Imxpc3QiIGlkPSJsaXN0Ij48cD5Ob25lIHlldC48"
    "L3A+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICA8aDI+TG9jayBhIHZpZGVvPC9oMj4KICAgIDxwPklu"
    "IHRoZSBzdHVkaW8sIHB1dCA8YiBpZD0ibmFtZUhpbnQiPjwvYj4gYXMgdGhlIGNyZWF0b3IgbmFtZSBzbyBldmVyeSB1bmxvY2sg"
    "cGF5cyB5b3UuPC9wPgogICAgPGEgY2xhc3M9ImJ0biIgaHJlZj0iL2NyZWF0ZSI+T3BlbiB0aGUgc3R1ZGlvPC9hPgogIDwvZGl2"
    "PgogIDxwIGNsYXNzPSJzbWFsbCI+U2lnbmVkIGluIG9uIHRoaXMgZGV2aWNlLiA8YSBocmVmPSIjIiBpZD0ib3V0QnRuIj5TaWdu"
    "IG91dDwvYT48L3A+Cjwvc2VjdGlvbj4KPC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewoidXNlIHN0cmljdCI7CnZhciBBUEk9"
    "Ii9jL2NyZWF0b3IvIiwgSz0ic2ViYmkuY3JlYXRvciI7CmZ1bmN0aW9uICQoaSl7cmV0dXJuIGRvY3VtZW50LmdldEVsZW1lbnRC"
    "eUlkKGkpfQpmdW5jdGlvbiBsb2FkKCl7dHJ5e3JldHVybiBKU09OLnBhcnNlKGxvY2FsU3RvcmFnZS5nZXRJdGVtKEspfHwibnVs"
    "bCIpfWNhdGNoKGUpe3JldHVybiBudWxsfX0KZnVuY3Rpb24gc2F2ZSh2KXt0cnl7bG9jYWxTdG9yYWdlLnNldEl0ZW0oSyxKU09O"
    "LnN0cmluZ2lmeSh2KSl9Y2F0Y2goZSl7fX0KZnVuY3Rpb24gZ2JwKHApe3A9cHx8MDtyZXR1cm4gIsKjIitNYXRoLmZsb29yKHAv"
    "MTAwKSsiLiIrKCIwIisocCUxMDApKS5zbGljZSgtMil9CmZ1bmN0aW9uIGVzYyhzKXtyZXR1cm4gU3RyaW5nKHMpLnJlcGxhY2Uo"
    "L1smPD4iXS9nLGZ1bmN0aW9uKGMpe3JldHVybiB7IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7"
    "In1bY119KX0KZnVuY3Rpb24gc2F5KGlkLHRleHQsa2luZCl7dmFyIG09JChpZCk7bS5jbGFzc05hbWU9Im1zZyBvbiIrKGtpbmQ/"
    "IiAiK2tpbmQ6IiIpO20udGV4dENvbnRlbnQ9dGV4dH0KZnVuY3Rpb24gcG9zdCh3aGF0LGJvZHkpe3JldHVybiBmZXRjaChBUEkr"
    "d2hhdCx7bWV0aG9kOiJQT1NUIixoZWFkZXJzOnsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiJ9LGJvZHk6SlNPTi5z"
    "dHJpbmdpZnkoYm9keSl9KQogLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpLnRoZW4oZnVuY3Rpb24oZCl7ZC5fb2s9"
    "ci5vaztyZXR1cm4gZH0pfSl9CmZ1bmN0aW9uIHZpZXcodil7WyJqb2luIiwic2F2ZWQiLCJkYXNoIl0uZm9yRWFjaChmdW5jdGlv"
    "bihzKXskKHMpLmhpZGRlbj0ocyE9PXYpfSk7d2luZG93LnNjcm9sbFRvKDAsMCl9CnZhciBtZT1sb2FkKCksIGRhdGE9bnVsbDsK"
    "CmZ1bmN0aW9uIHJlZnJlc2goKXsKICByZXR1cm4gcG9zdCgibWUiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXsKICAg"
    "IGlmKCFkLl9vayl7IGlmKGQuZXJyb3I9PT0iYmFkX2tleSIpe21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIik7c2F5KCJq"
    "b2luTXNnIiwiVGhhdCBrZXkgd2Fzbid0IHJlY29nbmlzZWQuIFNpZ24gaW4gYWdhaW4uIiwiYmFkIil9IHJldHVybiB9CiAgICBk"
    "YXRhPWQ7IHZpZXcoImRhc2giKTsKICAgICQoImhlbGxvIikudGV4dENvbnRlbnQ9IkhpICIrZC5uYW1lOwogICAgJCgibmFtZUhp"
    "bnQiKS50ZXh0Q29udGVudD1kLm5hbWU7CiAgICAkKCJiYWwiKS50ZXh0Q29udGVudD1nYnAoZC5iYWxhbmNlX3BlbmNlKTsKICAg"
    "ICQoInZpZXdzIikudGV4dENvbnRlbnQ9KGQucGFpZF92aWV3c3x8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUdCIik7CiAgICB2YXIg"
    "c2I9JCgic2V0dXBCdG4iKSx3Yj0kKCJ3aXRoZHJhd0J0biIpLHN0PSQoInN0cmlwZUJ0biIpLGRvdD0kKCJkb3QiKSx0eD0kKCJz"
    "dGF0ZVRleHQiKTsKICAgIHNiLmhpZGRlbj13Yi5oaWRkZW49c3QuaGlkZGVuPXRydWU7ZG90LmNsYXNzTmFtZT0iZG90IjsKICAg"
    "IGlmKCFkLnBheW91dHNfcmVhZHlfb25fc2l0ZSl7dHgudGV4dENvbnRlbnQ9IlBheW91dHMgYXJlIGJlaW5nIHN3aXRjaGVkIG9u"
    "LiBZb3VyIGVhcm5pbmdzIGFyZSBzYWZlIG9uIHlvdXIgYmFsYW5jZS4ifQogICAgZWxzZSBpZighZC5iYW5rX2xpbmtlZCl7dHgu"
    "dGV4dENvbnRlbnQ9Ik5vIGJhbmsgbGlua2VkIHlldC4iO3NiLmhpZGRlbj1mYWxzZTtzYi50ZXh0Q29udGVudD0iU2V0IHVwIHBh"
    "eW91dHMifQogICAgZWxzZSBpZighZC5wYXlvdXRzX2VuYWJsZWQpe3R4LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/"
    "IlN0cmlwZSBpcyBjaGVja2luZyB5b3VyIGRldGFpbHMuIjoiU2V0dXAgbm90IGZpbmlzaGVkLiI7c2IuaGlkZGVuPWZhbHNlO3Ni"
    "LnRleHRDb250ZW50PWQuZGV0YWlsc19zdWJtaXR0ZWQ/IkNoZWNrIG15IGRldGFpbHMiOiJGaW5pc2ggc2V0dXAifQogICAgZWxz"
    "ZXsKICAgICAgZG90LmNsYXNzTmFtZT0iZG90IG9rIjt0eC50ZXh0Q29udGVudD0iQmFuayBsaW5rZWQuIFJlYWR5IHRvIHBheSBv"
    "dXQuIjtzdC5oaWRkZW49ZmFsc2U7d2IuaGlkZGVuPWZhbHNlOwogICAgICBpZihkLmJhbGFuY2VfcGVuY2U+PWQubWluX3dpdGhk"
    "cmF3X3BlbmNlKXt3Yi5kaXNhYmxlZD1mYWxzZTt3Yi50ZXh0Q29udGVudD0iV2l0aGRyYXcgIitnYnAoZC5iYWxhbmNlX3BlbmNl"
    "KX0KICAgICAgZWxzZXt3Yi5kaXNhYmxlZD10cnVlO3diLnRleHRDb250ZW50PSJXaXRoZHJhdyBmcm9tICIrZ2JwKGQubWluX3dp"
    "dGhkcmF3X3BlbmNlKX0KICAgIH0KICAgIHZhciBMPSQoImxpc3QiKTsKICAgIGlmKCFkLnBheW91dHN8fCFkLnBheW91dHMubGVu"
    "Z3RoKXtMLmlubmVySFRNTD0iPHA+Tm9uZSB5ZXQuPC9wPiJ9CiAgICBlbHNle0wuaW5uZXJIVE1MPWQucGF5b3V0cy5tYXAoZnVu"
    "Y3Rpb24ocCl7CiAgICAgIHZhciB3aGVuPXAuYXQuc2xpY2UoMCwxMCksIHM9cC5zdGF0dXM9PT0ic2VudCI/IlNlbnQiOihwLnN0"
    "YXR1cz09PSJmYWlsZWQiPyJEaWRuJ3QgZ28gdGhyb3VnaCwgcmV0dXJuZWQiOiJTZW5kaW5nIik7CiAgICAgIHZhciBwcm9vZj1w"
    "LmJsb2NrX2luZGV4IT1udWxsPycgwrcgPGEgaHJlZj0iaHR0cHM6Ly9zZWJiaS5wcm8veC93YWxrL2Jsb2NrP2luZGV4PScrcC5i"
    "bG9ja19pbmRleCsnIj5wcm9vZjwvYT4nOiIiOwogICAgICByZXR1cm4gIjxkaXY+PHNwYW4+Iit3aGVuKyIgwrcgIitzK3Byb29m"
    "KyI8L3NwYW4+PGI+IitnYnAocC5wZW5jZSkrIjwvYj48L2Rpdj4ifSkuam9pbigiIil9CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtz"
    "YXkoImRhc2hNc2ciLCJDb3VsZG4ndCByZWFjaCBzZWJiaS5wcm8uIENoZWNrIHlvdXIgY29ubmVjdGlvbi4iLCJiYWQiKX0pOwp9"
    "CgpmdW5jdGlvbiBnb1N0cmlwZSgpewogIHNheSgiZGFzaE1zZyIsIk9wZW5pbmcgU3RyaXBl4oCmIik7CiAgcG9zdCgiY29ubmVj"
    "dCIse2tleTptZS5rZXl9KS50aGVuKGZ1bmN0aW9uKGQpeyBpZihkLnVybCl7bG9jYXRpb24uaHJlZj1kLnVybH0gZWxzZSBzYXko"
    "ImRhc2hNc2ciLGQubWVzc2FnZXx8IkNvdWxkbid0IG9wZW4gU3RyaXBlIGp1c3Qgbm93LiIsImJhZCIpIH0pCiAgLmNhdGNoKGZ1"
    "bmN0aW9uKCl7c2F5KCJkYXNoTXNnIiwiQ291bGRuJ3QgcmVhY2ggc2ViYmkucHJvLiIsImJhZCIpfSk7Cn0KCiQoImpvaW5CdG4i"
    "KS5vbmNsaWNrPWZ1bmN0aW9uKCl7CiAgdmFyIG49JCgibmFtZSIpLnZhbHVlLnRyaW0oKTsgaWYobi5sZW5ndGg8Myl7c2F5KCJq"
    "b2luTXNnIiwiUGljayBhIG5hbWUgb2YgYXQgbGVhc3QgMyBsZXR0ZXJzIG9yIG51bWJlcnMuIiwiYmFkIik7cmV0dXJufQogIHRo"
    "aXMuZGlzYWJsZWQ9dHJ1ZTt2YXIgYj10aGlzOwogIHBvc3QoImpvaW4iLHtuYW1lOm59KS50aGVuKGZ1bmN0aW9uKGQpe2IuZGlz"
    "YWJsZWQ9ZmFsc2U7CiAgICBpZighZC5fb2spe3NheSgiam9pbk1zZyIsZC5tZXNzYWdlfHwiQ291bGRuJ3QgY2xhaW0gdGhhdCBu"
    "YW1lLiIsImJhZCIpO3JldHVybn0KICAgIG1lPXtrZXk6ZC5rZXksbmFtZTpkLm5hbWUsaWQ6ZC5jcmVhdG9yX2lkfTtzYXZlKG1l"
    "KTsKICAgICQoInNhdmVkTmFtZSIpLnRleHRDb250ZW50PWQubmFtZTskKCJzYXZlZEtleSIpLnRleHRDb250ZW50PWQua2V5O3Zp"
    "ZXcoInNhdmVkIik7CiAgfSkuY2F0Y2goZnVuY3Rpb24oKXtiLmRpc2FibGVkPWZhbHNlO3NheSgiam9pbk1zZyIsIkNvdWxkbid0"
    "IHJlYWNoIHNlYmJpLnByby4iLCJiYWQiKX0pOwp9OwokKCJrZXlCdG4iKS5vbmNsaWNrPWZ1bmN0aW9uKCl7dmFyIGs9JCgia2V5"
    "SW4iKS52YWx1ZS50cmltKCk7aWYoIWspcmV0dXJuO21lPXtrZXk6a307c2F2ZShtZSk7cmVmcmVzaCgpfTsKJCgiY29weUJ0biIp"
    "Lm9uY2xpY2s9ZnVuY3Rpb24oKXt2YXIgaz1tZSYmbWUua2V5O2lmKCFrKXJldHVybjsKICAobmF2aWdhdG9yLmNsaXBib2FyZD9u"
    "YXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChrKTpQcm9taXNlLnJlamVjdCgpKS50aGVuKGZ1bmN0aW9uKCl7JCgiY29weUJ0"
    "biIpLnRleHRDb250ZW50PSJDb3BpZWQifSxmdW5jdGlvbigpeyQoImNvcHlCdG4iKS50ZXh0Q29udGVudD0iUHJlc3MgYW5kIGhv"
    "bGQgdGhlIGtleSB0byBjb3B5IGl0In0pfTsKJCgiZG9uZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtyZWZyZXNoKCl9OwokKCJz"
    "ZXR1cEJ0biIpLm9uY2xpY2s9Z29TdHJpcGU7CiQoInN0cmlwZUJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oKXtwb3N0KCJkYXNoYm9h"
    "cmQiLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtpZihkLnVybClsb2NhdGlvbi5ocmVmPWQudXJsO2Vsc2Ugc2F5KCJk"
    "YXNoTXNnIixkLm1lc3NhZ2V8fCJDb3VsZG4ndCBvcGVuIFN0cmlwZS4iLCJiYWQiKX0pfTsKJCgid2l0aGRyYXdCdG4iKS5vbmNs"
    "aWNrPWZ1bmN0aW9uKCl7CiAgdmFyIGI9dGhpcztiLmRpc2FibGVkPXRydWU7Yi50ZXh0Q29udGVudD0iU2VuZGluZ+KApiI7CiAg"
    "cG9zdCgid2l0aGRyYXciLHtrZXk6bWUua2V5fSkudGhlbihmdW5jdGlvbihkKXtzYXkoImRhc2hNc2ciLGQubWVzc2FnZXx8KGQu"
    "cGFpZD8iU2VudC4iOiJEaWRuJ3QgZ28gdGhyb3VnaC4iKSxkLnBhaWQ/Imdvb2QiOiJiYWQiKTtyZWZyZXNoKCl9KQogIC5jYXRj"
    "aChmdW5jdGlvbigpe3NheSgiZGFzaE1zZyIsIkNvdWxkbid0IHJlYWNoIHNlYmJpLnByby4gTm90aGluZyB3YXMgdGFrZW4gZnJv"
    "bSB5b3VyIGJhbGFuY2UuIiwiYmFkIik7cmVmcmVzaCgpfSk7Cn07CiQoIm91dEJ0biIpLm9uY2xpY2s9ZnVuY3Rpb24oZSl7ZS5w"
    "cmV2ZW50RGVmYXVsdCgpO21lPW51bGw7c2F2ZShudWxsKTt2aWV3KCJqb2luIil9OwoKdmFyIHE9bG9jYXRpb24uc2VhcmNoOwpp"
    "ZihtZSYmbWUua2V5KXsKICByZWZyZXNoKCkudGhlbihmdW5jdGlvbigpewogICAgaWYoL1s/Jl1yZXRyeT0xLy50ZXN0KHEpKSBn"
    "b1N0cmlwZSgpOwogICAgZWxzZSBpZigvWz8mXWNvbm5lY3RlZD0xLy50ZXN0KHEpKSBzYXkoImRhc2hNc2ciLCJUaGFua3MuIFN0"
    "cmlwZSBoYXMgeW91ciBkZXRhaWxzLiBJdCBjYW4gdGFrZSBhIGZldyBtaW51dGVzIGZvciB0aGVtIHRvIGJlIGNoZWNrZWQuIiwi"
    "Z29vZCIpOwogICAgdHJ5e2hpc3RvcnkucmVwbGFjZVN0YXRlKG51bGwsIiIsbG9jYXRpb24ucGF0aG5hbWUpfWNhdGNoKGUpe30K"
    "ICB9KTsKfSBlbHNlIHZpZXcoImpvaW4iKTsKfSkoKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/earn": (_d(_HTML_B64), "text/html; charset=utf-8"),
}

_BUTTON = (
    b'<a id="sebbi-earn-btn" href="/earn" style="position:fixed;right:14px;'
    b'bottom:calc(16px + env(safe-area-inset-bottom,0px));z-index:2147483000;'
    b'display:flex;align-items:center;gap:8px;padding:12px 16px;border-radius:999px;'
    b'background:#ffe14d;color:#1a1300;font:800 14px system-ui,-apple-system,Segoe UI,sans-serif;'
    b'text-decoration:none;box-shadow:0 6px 20px rgba(0,0,0,.35)">'
    b'<span style="display:grid;place-items:center;width:24px;height:24px;border-radius:50%;'
    b'background:#ff3d8b;color:#fff;font-size:13px">&pound;</span>My earnings</a>'
)

_HOME_PATHS = ("/", "/index.html")
_patched = False


def _inject(raw):
    """Add the button to a captured homepage response. Returns raw unchanged if unsure."""
    try:
        sep = raw.find(b"\r\n\r\n")
        if sep < 0:
            return raw
        head, body = raw[:sep], raw[sep + 4:]
        low = head.lower()
        if b"text/html" not in low or b"content-encoding" in low or b"transfer-encoding" in low:
            return raw
        if b"sebbi-earn-btn" in body:
            return raw
        i = body.lower().rfind(b"</body>")
        if i < 0:
            return raw
        body = body[:i] + _BUTTON + body[i:]
        if re.search(rb"(?im)^content-length:", head):
            head = re.sub(rb"(?im)^(content-length:)\s*\d+", b"\\g<1> " + str(len(body)).encode(), head)
        return head + b"\r\n\r\n" + body
    except Exception:
        return raw


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
    if getattr(cls, "_earnpage_patched", False):
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
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path in _HOME_PATHS:
            real = self.wfile
            buf = io.BytesIO()
            self.wfile = buf
            try:
                original_do_GET(self)
                try:
                    self.flush_headers()
                except Exception:
                    pass
            finally:
                self.wfile = real
            real.write(_inject(buf.getvalue()))
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._earnpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "earnpage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys()), "homepage_button": True}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}
