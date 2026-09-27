"""
modules/public_proof_adapter.py  v2.0.0
The public proof log: legacy systems send sebbi.pro the SHA-256 of a state
change, and get back a receipt proving that hash is in an append-only log.

  * An RFC 6962 Merkle tree (the Certificate Transparency construction):
        leaf hash  = SHA-256(0x00 || entry)      entry = the 32-byte state hash
        node hash  = SHA-256(0x01 || left || right)
    so any receipt can be checked by anyone, with any RFC 6962 verifier,
    without trusting this server.
  * Receipts come back straight away: leaf index, tree size, root and the
    inclusion (audit) path.
  * Tree heads are sealed into the sebbi.pro chain on a schedule (every 60s or
    every 1,000 leaves, whichever comes first). That chain is walkable at
    /x/walk and its tip is timestamped in Bitcoin with OpenTimestamps by the
    existing anchor, so a leaf becomes Bitcoin-anchored once a confirmed
    anchored tip is at or after the block that sealed its tree head.
  * Hash-only. No payloads, labels or customer data are sent or stored.
  * Idempotent: the client sends its own id with each hash, so a retry after a
    lost response returns the original leaf instead of adding a duplicate.

Routes (clean /p/ prefix, armed by /x/public_proof_adapter/status):

    POST /p/submit        {"items":[{"hash":"<64 hex>","cid":"<client id>"}]}
                          or {"hash":"<64 hex>"}      needs an API key
    GET  /p/receipt?leaf=N        receipt against the sealed tree head
    GET  /p/proof?leaf=N&size=M   inclusion path at tree size M
    GET  /p/consistency?first=M&second=N   RFC 6962 consistency proof
    GET  /p/sth                   latest sealed tree head + current size
    GET  /p/find?hash=<64 hex>    leaf indexes holding that entry hash
    GET  /p/                      what this log is and how to check it

The customer journey (2.0.0), reached from the "plug in" bubble on the homepage:

    GET  /plugin              the product page: price, sign-up, set-up for Python,
                              JavaScript or any language, account, pricing,
                              receipt checker
    POST /p/signup            {name,email,org} -> a new key on the page and by email
                              (free 90 days; an existing email gets its key re-sent
                              to that inbox only)
    POST /p/account           {key} -> devices this month, bill, trial days, records
    POST /p/pay               {key} -> Stripe checkout for the real device count, or
                              the Stripe billing page for customers already paying
    GET  /p/sebbi_adapter.py  the Python adapter download

Keys are ordinary sebbi.pro keys (server.py's create_key, product "aileash"), so
the trial, the 50p device meter, the Stripe webhook and the 6-hourly quantity
sync all apply exactly as for the engine.

Billing (1.4.0): the same meter as the engine - 50p per device per month.
Each fingerprint can say which device it is about (a phone, terminal, till,
car...), sent as a one-way hash. Every distinct device seen on the key in a
calendar month counts once, through server.py's own record_device(), so a
customer running one central server for 20 million phones is billed for 20
million devices. Fingerprints with no device named count the installation
that sent them. Free for the key's 90-day trial. When a key's trial ends unpaid, /p/submit
answers 402 with the same Stripe checkout the engine gives (server.py's own
trial_checkout, quantity = real devices). Receipts, proofs and every GET route
stay free for good; the client keeps queuing and sends once paid.

The API key goes in the X-Sebbi-Key header (or "key" in the body). Set
ADAPTER_OPEN=1 in Railway to accept submissions without a key (not advised).

Loading: the live server loads modules through modules/router.py and calls
handle(). ALIASES and register(MODULE_MAP) are also provided so a loader that
maps modules by name (e.g. brain.py) can pick it up under "adapter",
"sidecar" or "anchor".

Assumes one server process (as on Railway today). If a second process ever
writes the same database, appends detect it and reload before continuing.
"""

import base64
import hashlib
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.parse

VERSION = "2.0.0"
ALIASES = ["adapter", "sidecar", "anchor"]
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "sth"), ("GET", "proof"),
          ("GET", "receipt"), ("GET", "consistency"), ("GET", "find")}

KEY = "public-proof-adapter"
SITE = "https://sebbi.pro"
MAX_ITEMS = 500
MAX_BODY = 262144
CHECKPOINT_SECONDS = max(10, int(os.environ.get("ADAPTER_CHECKPOINT_SECONDS", "60") or 60))
CHECKPOINT_EVERY = max(1, int(os.environ.get("ADAPTER_CHECKPOINT_EVERY", "1000") or 1000))
OPEN = os.environ.get("ADAPTER_OPEN", "0") == "1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
CID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
SPEC = ("RFC 6962 Merkle tree, SHA-256. leaf_hash = SHA256(0x00 || entry); "
        "node = SHA256(0x01 || left || right); entry = the 32 raw bytes of the submitted hash.")

_PAGE_B64 = (
    "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz0iZW4iPjxoZWFkPjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0idmll"
    "d3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCxpbml0aWFsLXNjYWxlPTEsdmlld3BvcnQtZml0PWNvdmVyIj4KPHRp"
    "dGxlPlBsdWcgaW4g4oCUIHNlYmJpLnBybzwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBjb250ZW50PSJUd28gbGlu"
    "ZXMgYW5kIGV2ZXJ5IGNoYW5nZSB5b3VyIHN5c3RlbSBtYWtlcyBnZXRzIGEgcmVjZWlwdCBhbnlvbmUgY2FuIGNoZWNrLiA1MHAg"
    "cGVyIGRldmljZSBwZXIgbW9udGgsIGZyZWUgZm9yIDkwIGRheXMuIj4KPGxpbmsgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVh"
    "cGlzLmNvbS9jc3MyP2ZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMDs2MDAmZmFtaWx5PUlCTStQbGV4K1NhbnM6d2do"
    "dEA0MDA7NTAwOzYwMCZmYW1pbHk9TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNTAwJmRpc3BsYXk9c3dhcCIgcmVsPSJzdHls"
    "ZXNoZWV0Ij4KPHN0eWxlPgo6cm9vdHstLWluazojMDUwNzBmOy0tZ29sZDojYzlhODRjOy0tb2s6IzdmZTNiMDstLWJsdWU6Izhm"
    "ZDBmZjstLW11dGU6IzhhOTNhZDstLWJhZDojZmY4YTgwOy0tbGluZTpyZ2JhKDE0MywyMDgsMjU1LC4yMik7Ci0tbW9ubzonSUJN"
    "IFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZTstLXNhbnM6J0lCTSBQbGV4IFNhbnMnLHN5c3RlbS11aSxzYW5zLXNl"
    "cmlmOy0tc2VyaWY6J05ld3NyZWFkZXInLEdlb3JnaWEsc2VyaWZ9Cip7Ym94LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3Bh"
    "ZGRpbmc6MDstd2Via2l0LXRhcC1oaWdobGlnaHQtY29sb3I6dHJhbnNwYXJlbnR9Cmh0bWx7c2Nyb2xsLWJlaGF2aW9yOnNtb290"
    "aDtzY3JvbGwtcGFkZGluZy10b3A6MTZweH0KYm9keXtiYWNrZ3JvdW5kOnJhZGlhbC1ncmFkaWVudChlbGxpcHNlIGF0IDUwJSAw"
    "JSwjMTAyMzNlLCMwNTA3MGYgNjIlKTtjb2xvcjojZThlZGY3O2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2xpbmUtaGVpZ2h0OjEu"
    "NjttaW4taGVpZ2h0OjEwMHZofQoud3JhcHttYXgtd2lkdGg6NzYwcHg7bWFyZ2luOjAgYXV0bztwYWRkaW5nOjAgMjBweCA4MHB4"
    "fQoudG9we2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVtczpjZW50ZXI7cGFkZGlu"
    "ZzpjYWxjKDE0cHggKyBlbnYoc2FmZS1hcmVhLWluc2V0LXRvcCkpIDAgMH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8p"
    "O2ZvbnQtc2l6ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWJsdWUpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBhe2ZvbnQtZmFt"
    "aWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO3RleHQtZGVjb3JhdGlvbjpub25lO21hcmdp"
    "bi1sZWZ0OjE0cHh9Cmgxe2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDMy"
    "cHgsN3Z3LDU0cHgpO2xpbmUtaGVpZ2h0OjEuMDg7bWFyZ2luOjMwcHggMCAxMnB4fQpoMntmb250LWZhbWlseTp2YXIoLS1zZXJp"
    "Zik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyNHB4O21hcmdpbjowIDAgOHB4fQpwLmxlYWR7Y29sb3I6I2I2YzBkNjtmb250"
    "LXNpemU6MTdweDttYXgtd2lkdGg6NTRjaH0KLmp1bXB7ZGlzcGxheTpmbGV4O2ZsZXgtd3JhcDp3cmFwO2dhcDo4cHg7bWFyZ2lu"
    "LXRvcDoxOHB4fQouanVtcCBhe2ZvbnQ6NTAwIDEycHggdmFyKC0tbW9ubyk7Y29sb3I6I2NmZDhlYTt0ZXh0LWRlY29yYXRpb246"
    "bm9uZTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjE2KTtib3JkZXItcmFkaXVzOjk5OXB4O3BhZGRpbmc6N3B4"
    "IDEycHh9Ci5wcmljZXtkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2dhcDoxNHB4O2ZsZXgtd3JhcDp3cmFwO21hcmdp"
    "bjoyMHB4IDAgNHB4O3BhZGRpbmc6MTZweCAxOHB4O2JvcmRlci1yYWRpdXM6MTZweDtiYWNrZ3JvdW5kOnJnYmEoMTQzLDIwOCwy"
    "NTUsLjA4KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpfQoucHJpY2UgYntmb250OjYwMCA0MHB4IHZhcigtLW1vbm8pO2Nv"
    "bG9yOnZhcigtLW9rKTtsaW5lLWhlaWdodDoxfS5wcmljZSBzcGFue2ZvbnQ6NTAwIDEzcHgvMS40IHZhcigtLW1vbm8pO2NvbG9y"
    "OiNjZmQ4ZWE7ZmxleDoxO21pbi13aWR0aDoxNTBweH0KLmxpdmV7ZGlzcGxheTpmbGV4O2dhcDoxMHB4O21hcmdpbjoxNHB4IDAg"
    "NHB4O2ZsZXgtd3JhcDp3cmFwfQouc3RhdHtmbGV4OjE7bWluLXdpZHRoOjE0MHB4O2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwu"
    "ODUpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czoxNHB4O3BhZGRpbmc6MTRweCAxNnB4fQouc3Rh"
    "dCBie2Rpc3BsYXk6YmxvY2s7Zm9udDo2MDAgMjRweCB2YXIoLS1tb25vKTtjb2xvcjp2YXIoLS1vayk7Zm9udC12YXJpYW50LW51"
    "bWVyaWM6dGFidWxhci1udW1zfQouc3RhdCBzcGFue2ZvbnQ6NTAwIDEycHggdmFyKC0tbW9ubyk7Y29sb3I6dmFyKC0tbXV0ZSl9"
    "Ci5jYXJke2JhY2tncm91bmQ6cmdiYSgxMywyMCwzNiwuOCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1saW5lKTtib3JkZXItcmFk"
    "aXVzOjE2cHg7cGFkZGluZzoyMHB4O21hcmdpbi10b3A6MTZweH0KLmNhcmQuaGl7Ym9yZGVyLWNvbG9yOnJnYmEoMTI3LDIyNywx"
    "NzYsLjUpO2JveC1zaGFkb3c6MCAwIDMwcHggcmdiYSgxMjcsMjI3LDE3NiwuMDgpfQouY2FyZCBwe2NvbG9yOiNiNmMwZDY7Zm9u"
    "dC1zaXplOjE1cHh9Ci50YWd7ZGlzcGxheTppbmxpbmUtYmxvY2s7Zm9udDo2MDAgMTFweCB2YXIoLS1tb25vKTtjb2xvcjojMDUw"
    "NzBmO2JhY2tncm91bmQ6dmFyKC0tYmx1ZSk7Ym9yZGVyLXJhZGl1czo2cHg7cGFkZGluZzoycHggN3B4O21hcmdpbi1ib3R0b206"
    "OHB4fQpwcmV7bWFyZ2luLXRvcDoxMnB4O2JhY2tncm91bmQ6IzAzMDUwYjtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwy"
    "NTUsLjA4KTtib3JkZXItcmFkaXVzOjEycHg7cGFkZGluZzoxNHB4IDE2cHg7b3ZlcmZsb3cteDphdXRvO2ZvbnQ6MTNweC8xLjYg"
    "dmFyKC0tbW9ubyk7Y29sb3I6I2RmZThmNX0KcHJlIC5je2NvbG9yOnZhcigtLW11dGUpfXByZSAua3tjb2xvcjp2YXIoLS1ibHVl"
    "KX1wcmUgLnN7Y29sb3I6dmFyKC0tb2spfQoudGFic3tkaXNwbGF5OmZsZXg7Z2FwOjZweDttYXJnaW4tdG9wOjE0cHg7ZmxleC13"
    "cmFwOndyYXB9Ci50YWJzIGJ1dHRvbntmb250OjYwMCAxMi41cHggdmFyKC0tbW9ubyk7cGFkZGluZzo4cHggMTJweDtib3JkZXIt"
    "cmFkaXVzOjlweDtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjE2KTtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2Nv"
    "bG9yOiNjZmQ4ZWE7Y3Vyc29yOnBvaW50ZXJ9Ci50YWJzIGJ1dHRvblthcmlhLXNlbGVjdGVkPXRydWVde2JhY2tncm91bmQ6dmFy"
    "KC0tYmx1ZSk7Y29sb3I6IzA1MDcwZjtib3JkZXItY29sb3I6dmFyKC0tYmx1ZSl9Ci5wYW5lW2hpZGRlbl17ZGlzcGxheTpub25l"
    "fQouc3RlcHN7Y291bnRlci1yZXNldDpzO2xpc3Qtc3R5bGU6bm9uZTttYXJnaW4tdG9wOjEwcHh9Ci5zdGVwcyBsaXtjb3VudGVy"
    "LWluY3JlbWVudDpzO3Bvc2l0aW9uOnJlbGF0aXZlO3BhZGRpbmc6MTBweCAwIDEwcHggNDBweDtib3JkZXItdG9wOjFweCBzb2xp"
    "ZCByZ2JhKDI1NSwyNTUsMjU1LC4wNik7Y29sb3I6I2NmZDhlYTtmb250LXNpemU6MTVweH0KLnN0ZXBzIGxpOmZpcnN0LWNoaWxk"
    "e2JvcmRlci10b3A6MH0KLnN0ZXBzIGxpOmJlZm9yZXtjb250ZW50OmNvdW50ZXIocyk7cG9zaXRpb246YWJzb2x1dGU7bGVmdDow"
    "O3RvcDoxMHB4O3dpZHRoOjI2cHg7aGVpZ2h0OjI2cHg7Ym9yZGVyLXJhZGl1czo4cHg7YmFja2dyb3VuZDp2YXIoLS1ibHVlKTtj"
    "b2xvcjojMDUwNzBmO2ZvbnQ6NjAwIDEzcHggdmFyKC0tbW9ubyk7ZGlzcGxheTpncmlkO3BsYWNlLWl0ZW1zOmNlbnRlcn0KY29k"
    "ZXt3b3JkLWJyZWFrOmJyZWFrLWFsbDtmb250OjEzcHggdmFyKC0tbW9ubyk7YmFja2dyb3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4w"
    "Nik7cGFkZGluZzoxcHggNnB4O2JvcmRlci1yYWRpdXM6NXB4O2NvbG9yOiNlOGVkZjd9Ci5idG5ze2Rpc3BsYXk6ZmxleDtmbGV4"
    "LXdyYXA6d3JhcDtnYXA6MTBweDttYXJnaW4tdG9wOjE2cHh9Ci5idG57ZGlzcGxheTppbmxpbmUtZmxleDthbGlnbi1pdGVtczpj"
    "ZW50ZXI7anVzdGlmeS1jb250ZW50OmNlbnRlcjtnYXA6OHB4O3BhZGRpbmc6MTNweCAxOHB4O2JvcmRlci1yYWRpdXM6MTJweDtm"
    "b250OjYwMCAxMy41cHggdmFyKC0tbW9ubyk7dGV4dC1kZWNvcmF0aW9uOm5vbmU7YmFja2dyb3VuZDp2YXIoLS1ibHVlKTtjb2xv"
    "cjojMDUwNzBmO2JvcmRlcjowO2N1cnNvcjpwb2ludGVyfQouYnRuLm9re2JhY2tncm91bmQ6dmFyKC0tb2spfS5idG4uZ2hvc3R7"
    "YmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1NSwuMjQpfQou"
    "YnRuOmRpc2FibGVke29wYWNpdHk6LjU7Y3Vyc29yOndhaXR9Ci5idG46Zm9jdXMtdmlzaWJsZSxpbnB1dDpmb2N1cy12aXNpYmxl"
    "LC50YWJzIGJ1dHRvbjpmb2N1cy12aXNpYmxle291dGxpbmU6MnB4IHNvbGlkIHZhcigtLW9rKTtvdXRsaW5lLW9mZnNldDozcHh9"
    "Ci5ncmlke2Rpc3BsYXk6Z3JpZDtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyO2dhcDoxMnB4O21hcmdpbi10b3A6MTJweH0KQG1l"
    "ZGlhKG1pbi13aWR0aDo2MjBweCl7LmdyaWR7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnJ9fQouZ3JpZCBkaXZ7YmFja2dy"
    "b3VuZDpyZ2JhKDI1NSwyNTUsMjU1LC4wMyk7Ym9yZGVyOjFweCBzb2xpZCByZ2JhKDI1NSwyNTUsMjU1LC4wNyk7Ym9yZGVyLXJh"
    "ZGl1czoxMnB4O3BhZGRpbmc6MTRweH0KLmdyaWQgYntkaXNwbGF5OmJsb2NrO2ZvbnQ6NjAwIDE0cHggdmFyKC0tbW9ubyk7Y29s"
    "b3I6I2ZmZjttYXJnaW4tYm90dG9tOjRweH0uZ3JpZCBzcGFue2ZvbnQtc2l6ZToxNHB4O2NvbG9yOiNiNmMwZDZ9Ci5mb3Jte2Rp"
    "c3BsYXk6Z3JpZDtnYXA6MTBweDttYXJnaW4tdG9wOjE0cHh9CmxhYmVsLmZ7ZGlzcGxheTpibG9jaztmb250OjUwMCAxMnB4IHZh"
    "cigtLW1vbm8pO2NvbG9yOnZhcigtLW11dGUpO21hcmdpbi1ib3R0b206NHB4fQppbnB1dHt3aWR0aDoxMDAlO21pbi13aWR0aDow"
    "O3BhZGRpbmc6MTNweCAxNHB4O2JvcmRlci1yYWRpdXM6MTJweDtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjU1LDI1NSwyNTUsLjE4"
    "KTtiYWNrZ3JvdW5kOiMwMzA1MGI7Y29sb3I6I2ZmZjtmb250OjE1cHggdmFyKC0tc2Fucyl9CmlucHV0Lm1vbm97Zm9udDoxNHB4"
    "LzEuNSB2YXIoLS1tb25vKX0KW2hpZGRlbl17ZGlzcGxheTpub25lIWltcG9ydGFudH0KLnJvd3tkaXNwbGF5OmZsZXg7Z2FwOjEw"
    "cHg7bWFyZ2luLXRvcDoxMnB4fS5yb3cgaW5wdXR7ZmxleDoxfQoub3V0e21hcmdpbi10b3A6MTRweDtmb250OjEzLjVweC8xLjYg"
    "dmFyKC0tbW9ubyk7Y29sb3I6I2NmZTZkOTtkaXNwbGF5Om5vbmU7d29yZC1icmVhazpicmVhay13b3JkfQoub3V0Lm9ue2Rpc3Bs"
    "YXk6YmxvY2t9LnBhc3N7Y29sb3I6dmFyKC0tb2spO2ZvbnQtd2VpZ2h0OjYwMH0uZmFpbHtjb2xvcjp2YXIoLS1iYWQpO2ZvbnQt"
    "d2VpZ2h0OjYwMH0KLm91dCBhe2NvbG9yOnZhcigtLWJsdWUpfS5vdXQgYS5idG57Y29sb3I6IzA1MDcwZn0ub3V0IGEuYnRuLmdo"
    "b3N0e2NvbG9yOiNmZmZ9Ci5rZXlib3h7bWFyZ2luLXRvcDoxMHB4O2JhY2tncm91bmQ6I2ZmZjtjb2xvcjojMDUwNzBmO2JvcmRl"
    "ci1yYWRpdXM6MTJweDtwYWRkaW5nOjE0cHg7Zm9udDo2MDAgMTRweCB2YXIoLS1tb25vKTt3b3JkLWJyZWFrOmJyZWFrLWFsbH0K"
    "LmFjY3R7ZGlzcGxheTpncmlkO2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyO2dhcDoxMHB4O21hcmdpbi10b3A6MTRweH0K"
    "LmFjY3QgZGl2e2JhY2tncm91bmQ6cmdiYSgyNTUsMjU1LDI1NSwuMDQpO2JvcmRlcjoxcHggc29saWQgcmdiYSgyNTUsMjU1LDI1"
    "NSwuMDgpO2JvcmRlci1yYWRpdXM6MTJweDtwYWRkaW5nOjEycHh9Ci5hY2N0IGJ7ZGlzcGxheTpibG9jaztmb250OjYwMCAyMnB4"
    "IHZhcigtLW1vbm8pO2NvbG9yOnZhcigtLW9rKX0uYWNjdCBzcGFue2ZvbnQ6NTAwIDEycHggdmFyKC0tbW9ubyk7Y29sb3I6dmFy"
    "KC0tbXV0ZSl9Ci5jYWxje21hcmdpbi10b3A6MTRweDtmb250OjE1cHggdmFyKC0tbW9ubyk7Y29sb3I6I2NmZDhlYX0uY2FsYyBs"
    "YWJlbHtkaXNwbGF5OmJsb2NrO2ZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLW11dGUpO21hcmdpbi1ib3R0b206NnB4fQouY2Fs"
    "YyBpbnB1dHtwYWRkaW5nOjA7Ym9yZGVyOjA7YmFja2dyb3VuZDpub25lO2FjY2VudC1jb2xvcjojOGZkMGZmfS5jYWxjIGJ7Y29s"
    "b3I6dmFyKC0tb2spfQouc21hbGx7Zm9udC1zaXplOjEzcHghaW1wb3J0YW50O2NvbG9yOnZhcigtLW11dGUpIWltcG9ydGFudDtt"
    "YXJnaW4tdG9wOjEwcHh9Cjwvc3R5bGU+PC9oZWFkPjxib2R5PjxkaXYgY2xhc3M9IndyYXAiPgo8ZGl2IGNsYXNzPSJ0b3AiPjxk"
    "aXYgY2xhc3M9ImJyYW5kIj5zZWJiaTxiPi5wcm88L2I+IMK3IFBMVUcgSU48L2Rpdj48bmF2PjxhIGhyZWY9IiNhY2NvdW50Ij5B"
    "Y2NvdW50PC9hPjxhIGhyZWY9Ii9wcm92ZSI+UHJvb2Y8L2E+PGEgaHJlZj0iLyI+SG9tZTwvYT48L25hdj48L2Rpdj4KCjxoMT5L"
    "ZWVwIHlvdXIgc3lzdGVtLjxicj5BZGQgdGhlIHByb29mLjwvaDE+CjxwIGNsYXNzPSJsZWFkIj5Ud28gbGluZXMgYW5kIGV2ZXJ5"
    "IGNoYW5nZSB5b3VyIHN5c3RlbSBtYWtlcyBnZXRzIGEgcmVjZWlwdCBhbnlvbmUgY2FuIGNoZWNrLiBTYW1lIGRhdGFiYXNlLCBz"
    "YW1lIGNvZGUsIHNhbWUgc2VydmVycy4gT25seSBhIGZpbmdlcnByaW50IHRyYXZlbHM7IHlvdXIgZGF0YSBzdGF5cyBleGFjdGx5"
    "IHdoZXJlIGl0IGlzLjwvcD4KPGRpdiBjbGFzcz0icHJpY2UiPjxiPjUwcDwvYj48c3Bhbj5wZXIgZGV2aWNlIHBlciBtb250aDxi"
    "cj5ldmVyeSBwaG9uZSwgdGlsbCBvciBtYWNoaW5lIHlvdSByZWNvcmQgZm9yPGJyPmZyZWUgZm9yIHlvdXIgZmlyc3QgOTAgZGF5"
    "czwvc3Bhbj48YSBjbGFzcz0iYnRuIG9rIiBocmVmPSIja2V5Ij5HZXQgeW91ciBmcmVlIGtleTwvYT48L2Rpdj4KPGRpdiBjbGFz"
    "cz0ianVtcCI+PGEgaHJlZj0iI2tleSI+MSDCtyBHZXQgYSBrZXk8L2E+PGEgaHJlZj0iI2luc3RhbGwiPjIgwrcgUGx1ZyBpbjwv"
    "YT48YSBocmVmPSIjYWNjb3VudCI+MyDCtyBZb3VyIGFjY291bnQ8L2E+PGEgaHJlZj0iI3ByaWNlIj5QcmljaW5nPC9hPjxhIGhy"
    "ZWY9IiNjaGVjayI+Q2hlY2sgYSByZWNlaXB0PC9hPjwvZGl2Pgo8ZGl2IGNsYXNzPSJsaXZlIiBpZD0ibGl2ZSI+CiA8ZGl2IGNs"
    "YXNzPSJzdGF0Ij48YiBpZD0ic2l6ZSI+4oCUPC9iPjxzcGFuPmVudHJpZXMgaW4gdGhlIHB1YmxpYyBsb2c8L3NwYW4+PC9kaXY+"
    "CiA8ZGl2IGNsYXNzPSJzdGF0Ij48YiBpZD0ic2VhbGVkIj7igJQ8L2I+PHNwYW4+bGFzdCBzZWFsZWQgaW4gY2hhaW4gYmxvY2s8"
    "L3NwYW4+PC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0iY2FyZCBoaSIgaWQ9ImtleSI+CiA8c3BhbiBjbGFzcz0idGFnIj5TVEVQ"
    "IDE8L3NwYW4+CiA8aDI+R2V0IHlvdXIgZnJlZSBrZXk8L2gyPgogPHA+RnJlZSBmb3IgOTAgZGF5cywgbm8gY2FyZC4gWW91ciBr"
    "ZXkgYXBwZWFycyBoZXJlIGFuZCBpcyBlbWFpbGVkIHRvIHlvdS48L3A+CiA8ZGl2IGNsYXNzPSJmb3JtIiBpZD0ic3VGb3JtIj4K"
    "ICA8ZGl2PjxsYWJlbCBjbGFzcz0iZiIgZm9yPSJzdU5hbWUiPllvdXIgbmFtZTwvbGFiZWw+PGlucHV0IGlkPSJzdU5hbWUiIGF1"
    "dG9jb21wbGV0ZT0ibmFtZSI+PC9kaXY+CiAgPGRpdj48bGFiZWwgY2xhc3M9ImYiIGZvcj0ic3VFbWFpbCI+V29yayBlbWFpbDwv"
    "bGFiZWw+PGlucHV0IGlkPSJzdUVtYWlsIiB0eXBlPSJlbWFpbCIgYXV0b2NvbXBsZXRlPSJlbWFpbCIgaW5wdXRtb2RlPSJlbWFp"
    "bCI+PC9kaXY+CiAgPGRpdj48bGFiZWwgY2xhc3M9ImYiIGZvcj0ic3VPcmciPkNvbXBhbnk8L2xhYmVsPjxpbnB1dCBpZD0ic3VP"
    "cmciIGF1dG9jb21wbGV0ZT0ib3JnYW5pemF0aW9uIj48L2Rpdj4KICA8YnV0dG9uIGNsYXNzPSJidG4gb2siIGlkPSJzdUdvIj5H"
    "ZXQgbXkga2V5PC9idXR0b24+CiA8L2Rpdj4KIDxkaXYgY2xhc3M9Im91dCIgaWQ9InN1T3V0Ij48L2Rpdj4KPC9kaXY+Cgo8ZGl2"
    "IGNsYXNzPSJjYXJkIiBpZD0iaW5zdGFsbCI+CiA8c3BhbiBjbGFzcz0idGFnIj5TVEVQIDI8L3NwYW4+CiA8aDI+UGx1ZyBpdCBp"
    "bjwvaDI+CiA8cD5QaWNrIHlvdXIgbGFuZ3VhZ2UuIFB5dGhvbiBnZXRzIHRoZSByZWFkeS1tYWRlIGFkYXB0ZXI7IGFueXRoaW5n"
    "IGVsc2UgdGFsa3MgdG8gdGhlIGxvZyBkaXJlY3RseS48L3A+CiA8ZGl2IGNsYXNzPSJ0YWJzIiByb2xlPSJ0YWJsaXN0Ij4KICA8"
    "YnV0dG9uIHJvbGU9InRhYiIgYXJpYS1zZWxlY3RlZD0idHJ1ZSIgZGF0YS1wPSJweSI+UHl0aG9uPC9idXR0b24+CiAgPGJ1dHRv"
    "biByb2xlPSJ0YWIiIGFyaWEtc2VsZWN0ZWQ9ImZhbHNlIiBkYXRhLXA9ImpzIj5KYXZhU2NyaXB0PC9idXR0b24+CiAgPGJ1dHRv"
    "biByb2xlPSJ0YWIiIGFyaWEtc2VsZWN0ZWQ9ImZhbHNlIiBkYXRhLXA9ImFueSI+QW55IGxhbmd1YWdlPC9idXR0b24+CiA8L2Rp"
    "dj4KIDxkaXYgY2xhc3M9InBhbmUiIGlkPSJwLXB5Ij4KICA8b2wgY2xhc3M9InN0ZXBzIj4KICAgPGxpPkRvd25sb2FkIDxiPnNl"
    "YmJpX2FkYXB0ZXIucHk8L2I+IGFuZCBwdXQgaXQgbmV4dCB0byB5b3VyIGNvZGUuIE5vdGhpbmcgZWxzZSB0byBpbnN0YWxsLjwv"
    "bGk+CiAgIDxsaT5TZXQgeW91ciBrZXk6IDxjb2RlPlNFQkJJX0FQSV9LRVk9PHNwYW4gY2xhc3M9ImtmaWxsIj55b3VyLWtleTwv"
    "c3Bhbj48L2NvZGU+PC9saT4KICAgPGxpPkFkZCB0aGUgbGluZSBhYm92ZSBhbnkgZnVuY3Rpb24gdGhhdCBjaGFuZ2VzIHNvbWV0"
    "aGluZyBpbXBvcnRhbnQsIGFuZCBuYW1lIHRoZSBkZXZpY2UgaXQgaXMgYWJvdXQuPC9saT4KICA8L29sPgo8cHJlPjxzcGFuIGNs"
    "YXNzPSJrIj5mcm9tPC9zcGFuPiBzZWJiaV9hZGFwdGVyIDxzcGFuIGNsYXNzPSJrIj5pbXBvcnQ8L3NwYW4+IGFuY2hvcl9zdGF0"
    "ZQo8c3BhbiBjbGFzcz0iayI+QGFuY2hvcl9zdGF0ZTwvc3Bhbj4oPHNwYW4gY2xhc3M9InMiPiJvcmRlcnMudXBkYXRlIjwvc3Bh"
    "bj4sIGRldmljZT08c3BhbiBjbGFzcz0icyI+ImhhbmRzZXQiPC9zcGFuPikKPHNwYW4gY2xhc3M9ImsiPmRlZjwvc3Bhbj4gdXBk"
    "YXRlX29yZGVyKG9yZGVyX2lkLCBzdGF0dXMsIGhhbmRzZXQpOgogICAgLi4uICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "PHNwYW4gY2xhc3M9ImMiPiMgeW91ciBjb2RlLCB1bmNoYW5nZWQ8L3NwYW4+CiAgICA8c3BhbiBjbGFzcz0iayI+cmV0dXJuPC9z"
    "cGFuPiB7PHNwYW4gY2xhc3M9InMiPiJvcmRlcl9pZCI8L3NwYW4+OiBvcmRlcl9pZCwgPHNwYW4gY2xhc3M9InMiPiJzdGF0dXMi"
    "PC9zcGFuPjogc3RhdHVzfTwvcHJlPgogIDxwIGNsYXNzPSJzbWFsbCI+SXQgd29ya3MgaW4gdGhlIGJhY2tncm91bmQ6IHlvdXIg"
    "YXBwIG5ldmVyIHdhaXRzLCBrZWVwcyBnb2luZyBpZiB0aGUgbmV0d29yayBkcm9wcywgYW5kIGNoZWNrcyBldmVyeSByZWNlaXB0"
    "IGl0c2VsZi4gTG9nZ2VycywgYXN5bmMgY29kZSBhbmQgb25lLW9mZiByZWNvcmRzIHdvcmsgdG9vOyB0aGUgZmlsZSBleHBsYWlu"
    "cyBlYWNoLjwvcD4KICA8ZGl2IGNsYXNzPSJidG5zIj48YSBjbGFzcz0iYnRuIiBocmVmPSIvcC9zZWJiaV9hZGFwdGVyLnB5IiBk"
    "b3dubG9hZD5Eb3dubG9hZCBzZWJiaV9hZGFwdGVyLnB5PC9hPjwvZGl2PgogPC9kaXY+CiA8ZGl2IGNsYXNzPSJwYW5lIiBpZD0i"
    "cC1qcyIgaGlkZGVuPgo8cHJlPjxzcGFuIGNsYXNzPSJjIj4vLyBOb2RlIDE4KyA6IGZpbmdlcnByaW50IGEgY2hhbmdlIGFuZCBs"
    "b2cgaXQ8L3NwYW4+CjxzcGFuIGNsYXNzPSJrIj5pbXBvcnQ8L3NwYW4+IHsgY3JlYXRlSGFzaCwgcmFuZG9tVVVJRCB9IDxzcGFu"
    "IGNsYXNzPSJrIj5mcm9tPC9zcGFuPiA8c3BhbiBjbGFzcz0icyI+Im5vZGU6Y3J5cHRvIjwvc3Bhbj47CjxzcGFuIGNsYXNzPSJr"
    "Ij5jb25zdDwvc3Bhbj4gc2hhID0gcyA9Jmd0OyBjcmVhdGVIYXNoKDxzcGFuIGNsYXNzPSJzIj4ic2hhMjU2Ijwvc3Bhbj4pLnVw"
    "ZGF0ZShzKS5kaWdlc3QoPHNwYW4gY2xhc3M9InMiPiJoZXgiPC9zcGFuPik7CjxzcGFuIGNsYXNzPSJrIj5jb25zdDwvc3Bhbj4g"
    "c3RhdGUgPSBKU09OLnN0cmluZ2lmeSh7IG9yZGVyX2lkOiA8c3BhbiBjbGFzcz0icyI+NDI8L3NwYW4+LCBzdGF0dXM6IDxzcGFu"
    "IGNsYXNzPSJzIj4icGFpZCI8L3NwYW4+IH0pOwo8c3BhbiBjbGFzcz0iayI+YXdhaXQ8L3NwYW4+IGZldGNoKDxzcGFuIGNsYXNz"
    "PSJzIj4iaHR0cHM6Ly9zZWJiaS5wcm8vcC9zdWJtaXQiPC9zcGFuPiwgewogIG1ldGhvZDogPHNwYW4gY2xhc3M9InMiPiJQT1NU"
    "Ijwvc3Bhbj4sCiAgaGVhZGVyczogeyA8c3BhbiBjbGFzcz0icyI+IkNvbnRlbnQtVHlwZSI8L3NwYW4+OiA8c3BhbiBjbGFzcz0i"
    "cyI+ImFwcGxpY2F0aW9uL2pzb24iPC9zcGFuPiwgPHNwYW4gY2xhc3M9InMiPiJYLVNlYmJpLUtleSI8L3NwYW4+OiA8c3BhbiBj"
    "bGFzcz0icyI+IjxzcGFuIGNsYXNzPSJrZmlsbCI+eW91ci1rZXk8L3NwYW4+Ijwvc3Bhbj4gfSwKICBib2R5OiBKU09OLnN0cmlu"
    "Z2lmeSh7IGl0ZW1zOiBbeyBoYXNoOiBzaGEoc3RhdGUpLCBjaWQ6IHJhbmRvbVVVSUQoKSwKICAgICAgICAgICAgICAgICAgICAg"
    "ICAgICAgICAgICAgICBkZXZpY2U6IHNoYSg8c3BhbiBjbGFzcz0icyI+IklNRUktMzU2OTM4MDM1NjQzODA5Ijwvc3Bhbj4pLnNs"
    "aWNlKDxzcGFuIGNsYXNzPSJzIj4wPC9zcGFuPiwgPHNwYW4gY2xhc3M9InMiPjMyPC9zcGFuPikgfV0gfSkKfSk7PC9wcmU+CiAg"
    "PHAgY2xhc3M9InNtYWxsIj5TZW5kIHRoZSA8Yj5jaWQ8L2I+IHlvdSBjaG9vc2Ugd2l0aCBlYWNoIHJlY29yZDogaWYgYSByZXF1"
    "ZXN0IGlzIHJldHJpZWQsIHRoZSBsb2cgcmV0dXJucyB0aGUgb3JpZ2luYWwgZW50cnkgaW5zdGVhZCBvZiBhIGR1cGxpY2F0ZS48"
    "L3A+CiA8L2Rpdj4KIDxkaXYgY2xhc3M9InBhbmUiIGlkPSJwLWFueSIgaGlkZGVuPgo8cHJlPmN1cmwgaHR0cHM6Ly9zZWJiaS5w"
    "cm8vcC9zdWJtaXQgXAogIC1IIDxzcGFuIGNsYXNzPSJzIj4iWC1TZWJiaS1LZXk6IDxzcGFuIGNsYXNzPSJrZmlsbCI+eW91ci1r"
    "ZXk8L3NwYW4+Ijwvc3Bhbj4gXAogIC1IIDxzcGFuIGNsYXNzPSJzIj4iQ29udGVudC1UeXBlOiBhcHBsaWNhdGlvbi9qc29uIjwv"
    "c3Bhbj4gXAogIC1kIDxzcGFuIGNsYXNzPSJzIj4neyJpdGVtcyI6W3siaGFzaCI6IiZsdDtzaGEyNTYgb2YgeW91ciByZWNvcmQm"
    "Z3Q7IiwiY2lkIjoib3JkZXItNDItdjMiLCJkZXZpY2UiOiJ0aWxsLTQifV19Jzwvc3Bhbj48L3ByZT4KICA8cCBjbGFzcz0ic21h"
    "bGwiPlVwIHRvIDUwMCByZWNvcmRzIHBlciByZXF1ZXN0LiA8Yj5oYXNoPC9iPjogNjQtY2hhcmFjdGVyIFNIQS0yNTYgb2YgdGhl"
    "IHJlY29yZC4gPGI+Y2lkPC9iPjogeW91ciBvd24gaWQgZm9yIGl0LiA8Yj5kZXZpY2U8L2I+OiB3aGF0IGl0IGlzIGFib3V0ICho"
    "YXNoIGl0IGZpcnN0IGlmIGl0IGlzIHBlcnNvbmFsKS4gVGhlIGFuc3dlciBob2xkcyBhIHJlY2VpcHQgZm9yIGVhY2ggcmVjb3Jk"
    "LCBjaGVja2FibGUgd2l0aCBhbnkgUkZDIDY5NjIgdmVyaWZpZXIuPC9wPgogPC9kaXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0iY2Fy"
    "ZCIgaWQ9ImFjY291bnQiPgogPHNwYW4gY2xhc3M9InRhZyI+U1RFUCAzPC9zcGFuPgogPGgyPllvdXIgYWNjb3VudDwvaDI+CiA8"
    "cD5EZXZpY2VzIHRoaXMgbW9udGgsIHlvdXIgYmlsbCwgeW91ciB0cmlhbCBhbmQgaG93IG11Y2ggeW91IGhhdmUgbG9nZ2VkLiBQ"
    "YXkgaGVyZSB3aGVuZXZlciB5b3UgYXJlIHJlYWR5LjwvcD4KIDxkaXYgY2xhc3M9InJvdyI+PGlucHV0IGlkPSJhY0tleSIgY2xh"
    "c3M9Im1vbm8iIHBsYWNlaG9sZGVyPSJZb3VyIGtleSIgYXV0b2NvbXBsZXRlPSJvZmYiIGFyaWEtbGFiZWw9IllvdXIga2V5Ij48"
    "YnV0dG9uIGNsYXNzPSJidG4iIGlkPSJhY0dvIj5PcGVuPC9idXR0b24+PC9kaXY+CiA8ZGl2IGlkPSJhY0JvZHkiIGhpZGRlbj4K"
    "ICA8ZGl2IGNsYXNzPSJhY2N0Ij4KICAgPGRpdj48YiBpZD0iYURldiI+4oCUPC9iPjxzcGFuPmRldmljZXMgdGhpcyBtb250aDwv"
    "c3Bhbj48L2Rpdj4KICAgPGRpdj48YiBpZD0iYUJpbGwiPuKAlDwvYj48c3Bhbj5tb250aGx5IGJpbGw8L3NwYW4+PC9kaXY+CiAg"
    "IDxkaXY+PGIgaWQ9ImFUcmlhbCI+4oCUPC9iPjxzcGFuIGlkPSJhVHJpYWxMIj50cmlhbDwvc3Bhbj48L2Rpdj4KICAgPGRpdj48"
    "YiBpZD0iYUxvZyI+4oCUPC9iPjxzcGFuPnJlY29yZHMgbG9nZ2VkPC9zcGFuPjwvZGl2PgogIDwvZGl2PgogIDxkaXYgY2xhc3M9"
    "ImJ0bnMiPjxidXR0b24gY2xhc3M9ImJ0biBvayIgaWQ9ImFjUGF5Ij5QYXkgbm93PC9idXR0b24+PGEgY2xhc3M9ImJ0biBnaG9z"
    "dCIgaHJlZj0iL3Avc2ViYmlfYWRhcHRlci5weSIgZG93bmxvYWQ+RG93bmxvYWQgYWRhcHRlcjwvYT48L2Rpdj4KIDwvZGl2Pgog"
    "PGRpdiBjbGFzcz0ib3V0IiBpZD0iYWNPdXQiPjwvZGl2Pgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImNhcmQiPgogPGgyPkJ1aWx0IGZv"
    "ciB0aGUgcmVjb3JkcyB0aGF0IG1hdHRlcjwvaDI+CiA8ZGl2IGNsYXNzPSJncmlkIj4KICA8ZGl2PjxiPlBheW1lbnRzICZhbXA7"
    "IGJhbGFuY2VzPC9iPjxzcGFuPkV2ZXJ5IGRlYml0LCBjcmVkaXQgYW5kIHJlZnVuZCBjYXJyaWVzIGl0cyBvd24gcmVjZWlwdC4g"
    "UHJvdmUgd2hhdCBhIGJhbGFuY2Ugd2FzLCBhbmQgd2hlbi48L3NwYW4+PC9kaXY+CiAgPGRpdj48Yj5BSSBkZWNpc2lvbnM8L2I+"
    "PHNwYW4+RmluZ2VycHJpbnQgd2hhdCB0aGUgbW9kZWwgZGVjaWRlZCwgdGhlIG1vbWVudCBpdCBkZWNpZGVzLiBUaGUgRVUgQUkg"
    "QWN0IGFza3MgZm9yIGV4YWN0bHkgdGhpcyByZWNvcmQuPC9zcGFuPjwvZGl2PgogIDxkaXY+PGI+Q2FsbHMsIG9yZGVycyAmYW1w"
    "OyBzdG9jazwvYj48c3Bhbj5FdmVyeSBzdGF0dXMgY2hhbmdlIG9uIHRoZSByZWNvcmQsIGluIG9yZGVyLCBwcm92YWJsZSB0byBh"
    "IGN1c3RvbWVyLCBzdXBwbGllciwgcmVndWxhdG9yIG9yIGNvdXJ0Ljwvc3Bhbj48L2Rpdj4KICA8ZGl2PjxiPkhlYWx0aCAmYW1w"
    "OyBsZWdhbCBmaWxlczwvYj48c3Bhbj5Qcm92ZSBhIHJlY29yZCBoYXNuJ3QgY2hhbmdlZCBzaW5jZSB0aGUgZGF5IGl0IHdhcyB3"
    "cml0dGVuLCB3aXRob3V0IGV2ZXIgc2VuZGluZyB0aGUgcmVjb3JkIGFueXdoZXJlLjwvc3Bhbj48L2Rpdj4KICA8ZGl2PjxiPkxv"
    "Z3MgJmFtcDsgYXVkaXQgdHJhaWxzPC9iPjxzcGFuPlBsdWcgaXQgaW50byB5b3VyIGV4aXN0aW5nIGxvZ2dlciBhbmQgZXZlcnkg"
    "bGluZSBiZWNvbWVzIGV2aWRlbmNlIG5vYm9keSBjYW4gcXVpZXRseSBlZGl0Ljwvc3Bhbj48L2Rpdj4KICA8ZGl2PjxiPkFueXRo"
    "aW5nIHlvdSdkIGRlZmVuZDwvYj48c3Bhbj5JZiB5b3UnZCBldmVyIG5lZWQgdG8gc2hvdyB3aGF0IHlvdXIgc3lzdGVtIGRpZCwg"
    "YW5kIHdoZW4sIGl0IGJlbG9uZ3MgaGVyZS48L3NwYW4+PC9kaXY+CiA8L2Rpdj4KPC9kaXY+Cgo8ZGl2IGNsYXNzPSJjYXJkIiBp"
    "ZD0icHJpY2UiPgogPGgyPk9uZSBwcmljZSBwZXIgZGV2aWNlLCBob3dldmVyIG11Y2ggaXQgcmVjb3JkczwvaDI+CiA8cD5FdmVy"
    "eSBwaG9uZSwgdGlsbCwgdGVybWluYWwgb3IgbWFjaGluZSB5b3VyIHN5c3RlbSByZWNvcmRzIGZvciBpcyBvbmUgZGV2aWNlLCBj"
    "b3VudGVkIG9uY2UgYSBtb250aCwgd2hldGhlciBpdCBtYWtlcyB0ZW4gY2hhbmdlcyBvciB0ZW4gbWlsbGlvbi4gUnVuIGl0IG9u"
    "IG9uZSBzZXJ2ZXIgb3IgYSB0aG91c2FuZDogdGhlIGNvdW50IGlzIHRoZSBkZXZpY2VzLCBub3QgdGhlIHNlcnZlcnMuPC9wPgog"
    "PGRpdiBjbGFzcz0iY2FsYyI+PGxhYmVsIGZvcj0iZGV2Ij5EZXZpY2VzPC9sYWJlbD48aW5wdXQgaWQ9ImRldiIgdHlwZT0icmFu"
    "Z2UiIG1pbj0iMCIgbWF4PSIxMDAiIHZhbHVlPSIzMCIgYXJpYS1sYWJlbD0iRGV2aWNlcyI+PGRpdj48YiBpZD0iZGV2biI+MjA8"
    "L2I+IGRldmljZXMgPSA8YiBpZD0iY29zdCI+wqMxMC4wMDwvYj4gYSBtb250aDwvZGl2PjwvZGl2PgogPHAgY2xhc3M9InNtYWxs"
    "Ij5Gcm9tIG9uZSBkZXZpY2UgdG8gdGVuIG1pbGxpb24uIEZyZWUgZm9yIHRoZSBmaXJzdCA5MCBkYXlzLCBubyBjYXJkIHRvIHN0"
    "YXJ0LiBSZWNlaXB0cyBhbmQgcHJvb2ZzIHN0YXkgeW91cnMgZm9yIGdvb2QuPC9wPgo8L2Rpdj4KCjxkaXYgY2xhc3M9ImNhcmQi"
    "PgogPGgyPldoYXQgeW91IGdldDwvaDI+CiA8ZGl2IGNsYXNzPSJncmlkIj4KICA8ZGl2PjxiPk5ldmVyIHNsb3dzIHlvdSBkb3du"
    "PC9iPjxzcGFuPlJlY29yZHMgcXVldWUgb24geW91ciBvd24gbWFjaGluZSBhbmQgc2VuZCBpbiB0aGUgYmFja2dyb3VuZC4gWW91"
    "ciBhcHAgbmV2ZXIgd2FpdHMgb24gdGhlIG5ldHdvcmsuPC9zcGFuPjwvZGl2PgogIDxkaXY+PGI+S2VlcHMgZ29pbmcgb2ZmbGlu"
    "ZTwvYj48c3Bhbj5JZiBzZWJiaS5wcm8gY2FuJ3QgYmUgcmVhY2hlZCwgZXZlcnl0aGluZyB3YWl0cyBzYWZlbHkgYW5kIHNlbmRz"
    "IGluIG9yZGVyIHdoZW4gaXQncyBiYWNrLiBOb3RoaW5nIGxvc3QsIG5vdGhpbmcgZG91YmxlZC48L3NwYW4+PC9kaXY+CiAgPGRp"
    "dj48Yj5DaGVja3MgdGhlIGFuc3dlcjwvYj48c3Bhbj5FdmVyeSByZWNlaXB0IGlzIHZlcmlmaWVkIG9uIHlvdXIgc2lkZSB0aGUg"
    "bW9tZW50IGl0IGFycml2ZXMsIHNvIHlvdSdyZSBub3QgdGFraW5nIG91ciB3b3JkIGZvciBpdC48L3NwYW4+PC9kaXY+CiAgPGRp"
    "dj48Yj5BbmNob3JlZCBpbiBCaXRjb2luPC9iPjxzcGFuPlRoZSBsb2cgaXMgc2VhbGVkIGludG8gdGhlIHNlYmJpLnBybyBjaGFp"
    "biBldmVyeSBtaW51dGUsIGFuZCB0aGUgY2hhaW4gaXMgdGltZXN0YW1wZWQgaW4gQml0Y29pbi48L3NwYW4+PC9kaXY+CiAgPGRp"
    "dj48Yj5TdGFuZGFyZCBwcm9vZnM8L2I+PHNwYW4+VGhlIHNhbWUgTWVya2xlLXRyZWUgcmVjZWlwdHMgdGhhdCBzZWN1cmUgd2Vi"
    "IGNlcnRpZmljYXRlcyAoUkZDIDY5NjIpLiBBbnkgY29tcGF0aWJsZSBjaGVja2VyIGNhbiB2ZXJpZnkgdGhlbS48L3NwYW4+PC9k"
    "aXY+CiAgPGRpdj48Yj5Qcml2YXRlIGJ5IGRlc2lnbjwvYj48c3Bhbj5Pbmx5IGZpbmdlcnByaW50cyBhcmUgc2VudC4gRGV2aWNl"
    "IG5hbWVzIGFyZSBvbmUtd2F5IGhhc2hlZCBiZWZvcmUgdGhleSBsZWF2ZSB5b3VyIG1hY2hpbmUuPC9zcGFuPjwvZGl2PgogPC9k"
    "aXY+CjwvZGl2PgoKPGRpdiBjbGFzcz0iY2FyZCIgaWQ9ImNoZWNrIj4KIDxoMj5DaGVjayBhIHJlY2VpcHQ8L2gyPgogPHA+VHlw"
    "ZSBhbiBlbnRyeSBudW1iZXIuIFlvdXIgYnJvd3NlciBmZXRjaGVzIHRoZSByZWNlaXB0IGFuZCBjaGVja3MgdGhlIG1hdGhzIGl0"
    "c2VsZi48L3A+CiA8ZGl2IGNsYXNzPSJyb3ciPjxpbnB1dCBpZD0ibGVhZiIgaW5wdXRtb2RlPSJudW1lcmljIiBwbGFjZWhvbGRl"
    "cj0iRW50cnkgbnVtYmVyLCBlLmcuIDAiIGFyaWEtbGFiZWw9IkVudHJ5IG51bWJlciI+PGJ1dHRvbiBjbGFzcz0iYnRuIiBpZD0i"
    "Z28iPkNoZWNrPC9idXR0b24+PC9kaXY+CiA8ZGl2IGNsYXNzPSJvdXQiIGlkPSJvdXQiPjwvZGl2Pgo8L2Rpdj4KPHAgY2xhc3M9"
    "InNtYWxsIiBzdHlsZT0ibWFyZ2luLXRvcDoyMnB4Ij5RdWVzdGlvbnM6IDxhIGhyZWY9Im1haWx0bzpqdXN0cmlnaHRkZWNvcmF0"
    "b3JzQGdtYWlsLmNvbSIgc3R5bGU9ImNvbG9yOiM4ZmQwZmYiPmp1c3RyaWdodGRlY29yYXRvcnNAZ21haWwuY29tPC9hPjwvcD4K"
    "PC9kaXY+CjxzY3JpcHQ+CihmdW5jdGlvbigpewoidXNlIHN0cmljdCI7CmZ1bmN0aW9uICQoaSl7cmV0dXJuIGRvY3VtZW50Lmdl"
    "dEVsZW1lbnRCeUlkKGkpfQpmdW5jdGlvbiBlc2Mocyl7cmV0dXJuIFN0cmluZyhzKS5yZXBsYWNlKC9bJjw+Il0vZyxmdW5jdGlv"
    "bihjKXtyZXR1cm57IiYiOiImYW1wOyIsIjwiOiImbHQ7IiwiPiI6IiZndDsiLCciJzoiJnF1b3Q7In1bY119KX0KZnVuY3Rpb24g"
    "cG9zdChwLGIpe3JldHVybiBmZXRjaChwLHttZXRob2Q6IlBPU1QiLGhlYWRlcnM6eyJDb250ZW50LVR5cGUiOiJhcHBsaWNhdGlv"
    "bi9qc29uIn0sYm9keTpKU09OLnN0cmluZ2lmeShiKX0pLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuIHIuanNvbigpLnRoZW4oZnVu"
    "Y3Rpb24oZCl7ZC5fY29kZT1yLnN0YXR1cztyZXR1cm4gZH0pfSl9CmZ1bmN0aW9uIHNheShpZCxodG1sKXt2YXIgbz0kKGlkKTtv"
    "LmNsYXNzTmFtZT0ib3V0IG9uIjtvLmlubmVySFRNTD1odG1sfQp2YXIgS0VZPSJzZWJiaS5wbHVnaW4ua2V5IjsKZnVuY3Rpb24g"
    "c2F2ZWQoKXt0cnl7cmV0dXJuIGxvY2FsU3RvcmFnZS5nZXRJdGVtKEtFWSl8fCIifWNhdGNoKGUpe3JldHVybiIifX0KZnVuY3Rp"
    "b24gcmVtZW1iZXIoayl7dHJ5e2xvY2FsU3RvcmFnZS5zZXRJdGVtKEtFWSxrKX1jYXRjaChlKXt9ZmlsbChrKX0KZnVuY3Rpb24g"
    "ZmlsbChrKXtpZighaylyZXR1cm47W10uZm9yRWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoIi5rZmlsbCIpLGZ1"
    "bmN0aW9uKGUpe2UudGV4dENvbnRlbnQ9a30pOyQoImFjS2V5IikudmFsdWU9a30KZmlsbChzYXZlZCgpKTsKCi8qIHRhYnMgKi8K"
    "W10uZm9yRWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoIi50YWJzIGJ1dHRvbiIpLGZ1bmN0aW9uKGIpe2Iub25j"
    "bGljaz1mdW5jdGlvbigpewogW10uZm9yRWFjaC5jYWxsKGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoIi50YWJzIGJ1dHRvbiIp"
    "LGZ1bmN0aW9uKHgpe3guc2V0QXR0cmlidXRlKCJhcmlhLXNlbGVjdGVkIix4PT09Yj8idHJ1ZSI6ImZhbHNlIik7JCgicC0iK3gu"
    "ZGF0YXNldC5wKS5oaWRkZW49KHghPT1iKX0pfX0pOwoKLyogc2lnbi11cCAqLwokKCJzdUdvIikub25jbGljaz1mdW5jdGlvbigp"
    "ewogdmFyIGI9dGhpcyxuYW1lPSQoInN1TmFtZSIpLnZhbHVlLnRyaW0oKSxlbWFpbD0kKCJzdUVtYWlsIikudmFsdWUudHJpbSgp"
    "LG9yZz0kKCJzdU9yZyIpLnZhbHVlLnRyaW0oKTsKIGlmKCFlbWFpbHx8ZW1haWwuaW5kZXhPZigiQCIpPDEpe3NheSgic3VPdXQi"
    "LCc8c3BhbiBjbGFzcz0iZmFpbCI+RW50ZXIgeW91ciBlbWFpbC48L3NwYW4+Jyk7cmV0dXJufQogYi5kaXNhYmxlZD10cnVlO3Nh"
    "eSgic3VPdXQiLCJDcmVhdGluZyB5b3VyIGtleeKApiIpOwogcG9zdCgiL3Avc2lnbnVwIix7bmFtZTpuYW1lLGVtYWlsOmVtYWls"
    "LG9yZzpvcmd9KS50aGVuKGZ1bmN0aW9uKGQpe2IuZGlzYWJsZWQ9ZmFsc2U7CiAgaWYoZC5rZXkpe3JlbWVtYmVyKGQua2V5KTsk"
    "KCJzdUZvcm0iKS5oaWRkZW49dHJ1ZTsKICAgc2F5KCJzdU91dCIsJzxzcGFuIGNsYXNzPSJwYXNzIj5Zb3VyIGtleSBpcyByZWFk"
    "eTwvc3Bhbj4uIEl0IGlzIGVtYWlsZWQgdG8geW91IHRvby48ZGl2IGNsYXNzPSJrZXlib3giPicrZXNjKGQua2V5KSsnPC9kaXY+"
    "JysKICAgICc8ZGl2IGNsYXNzPSJidG5zIj48YSBjbGFzcz0iYnRuIiBocmVmPSIvcC9zZWJiaV9hZGFwdGVyLnB5IiBkb3dubG9h"
    "ZD5Eb3dubG9hZCB0aGUgYWRhcHRlcjwvYT48YSBjbGFzcz0iYnRuIGdob3N0IiBocmVmPSIjaW5zdGFsbCI+UGx1ZyBpdCBpbjwv"
    "YT48L2Rpdj4nKwogICAgJzxwIGNsYXNzPSJzbWFsbCI+RnJlZSB1bnRpbCAnK2VzYyhkLnRyaWFsX2VuZHMpKycuIEtlZXAgdGhp"
    "cyBrZXkgcHJpdmF0ZS48L3A+Jyk7cmVmcmVzaEFjY291bnQoKX0KICBlbHNlIHNheSgic3VPdXQiLCc8c3BhbiBjbGFzcz0iZmFp"
    "bCI+Jytlc2MoZC5tZXNzYWdlfHwiQ291bGRuJ3QgY3JlYXRlIGEga2V5IGp1c3Qgbm93LiIpKyc8L3NwYW4+Jyk7CiB9KS5jYXRj"
    "aChmdW5jdGlvbigpe2IuZGlzYWJsZWQ9ZmFsc2U7c2F5KCJzdU91dCIsJzxzcGFuIGNsYXNzPSJmYWlsIj5Db3VsZG5cJ3QgcmVh"
    "Y2ggc2ViYmkucHJvLjwvc3Bhbj4nKX0pfTsKCi8qIGFjY291bnQgKi8KZnVuY3Rpb24gbW9uZXkocCl7cmV0dXJuIsKjIisocCku"
    "dG9Mb2NhbGVTdHJpbmcoImVuLUdCIix7bWluaW11bUZyYWN0aW9uRGlnaXRzOjIsbWF4aW11bUZyYWN0aW9uRGlnaXRzOjJ9KX0K"
    "ZnVuY3Rpb24gcmVmcmVzaEFjY291bnQoKXsKIHZhciBrPSQoImFjS2V5IikudmFsdWUudHJpbSgpO2lmKCFrKXJldHVybjsKIHBv"
    "c3QoIi9wL2FjY291bnQiLHtrZXk6a30pLnRoZW4oZnVuY3Rpb24oZCl7CiAgaWYoZC5lcnJvcil7JCgiYWNCb2R5IikuaGlkZGVu"
    "PXRydWU7c2F5KCJhY091dCIsJzxzcGFuIGNsYXNzPSJmYWlsIj4nK2VzYyhkLm1lc3NhZ2V8fCJUaGF0IGtleSB3YXNuJ3QgcmVj"
    "b2duaXNlZC4iKSsnPC9zcGFuPicpO3JldHVybn0KICByZW1lbWJlcihrKTskKCJhY0JvZHkiKS5oaWRkZW49ZmFsc2U7JCgiYWNP"
    "dXQiKS5jbGFzc05hbWU9Im91dCI7CiAgJCgiYURldiIpLnRleHRDb250ZW50PShkLmRldmljZXNfdGhpc19tb250aHx8MCkudG9M"
    "b2NhbGVTdHJpbmcoImVuLUdCIik7CiAgJCgiYUJpbGwiKS50ZXh0Q29udGVudD1tb25leShkLm1vbnRobHlfYmlsbF9nYnB8fDAp"
    "OwogICQoImFMb2ciKS50ZXh0Q29udGVudD0oZC5yZWNvcmRzX2xvZ2dlZHx8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUdCIik7CiAg"
    "aWYoZC5wYWlkKXskKCJhVHJpYWwiKS50ZXh0Q29udGVudD0iUGFpZCI7JCgiYVRyaWFsTCIpLnRleHRDb250ZW50PSJhY2NvdW50"
    "IjskKCJhY1BheSIpLnRleHRDb250ZW50PSJNYW5hZ2UgYmlsbGluZyJ9CiAgZWxzZSBpZihkLmluX3RyaWFsKXskKCJhVHJpYWwi"
    "KS50ZXh0Q29udGVudD1kLnRyaWFsX2RheXNfbGVmdDskKCJhVHJpYWxMIikudGV4dENvbnRlbnQ9ImZyZWUgZGF5cyBsZWZ0Ijsk"
    "KCJhY1BheSIpLnRleHRDb250ZW50PSJQYXkgbm93In0KICBlbHNleyQoImFUcmlhbCIpLnRleHRDb250ZW50PSJFbmRlZCI7JCgi"
    "YVRyaWFsTCIpLnRleHRDb250ZW50PSJ0cmlhbCAtIHBheSB0byBjb250aW51ZSI7JCgiYWNQYXkiKS50ZXh0Q29udGVudD0iUGF5"
    "IG5vdyB0byBjb250aW51ZSJ9CiB9KS5jYXRjaChmdW5jdGlvbigpe3NheSgiYWNPdXQiLCc8c3BhbiBjbGFzcz0iZmFpbCI+Q291"
    "bGRuXCd0IHJlYWNoIHNlYmJpLnByby48L3NwYW4+Jyl9KX0KJCgiYWNHbyIpLm9uY2xpY2s9cmVmcmVzaEFjY291bnQ7JCgiYWNL"
    "ZXkiKS5hZGRFdmVudExpc3RlbmVyKCJrZXlkb3duIixmdW5jdGlvbihlKXtpZihlLmtleT09PSJFbnRlciIpcmVmcmVzaEFjY291"
    "bnQoKX0pOwokKCJhY1BheSIpLm9uY2xpY2s9ZnVuY3Rpb24oKXt2YXIgYj10aGlzO2IuZGlzYWJsZWQ9dHJ1ZTsKIHBvc3QoIi9w"
    "L3BheSIse2tleTokKCJhY0tleSIpLnZhbHVlLnRyaW0oKX0pLnRoZW4oZnVuY3Rpb24oZCl7Yi5kaXNhYmxlZD1mYWxzZTsKICBp"
    "ZihkLnVybCl7bG9jYXRpb24uaHJlZj1kLnVybH1lbHNlIHNheSgiYWNPdXQiLCc8c3BhbiBjbGFzcz0iZmFpbCI+Jytlc2MoZC5t"
    "ZXNzYWdlfHwiUGF5bWVudHMgYXJlbid0IGF2YWlsYWJsZSBqdXN0IG5vdy4iKSsnPC9zcGFuPicpfSkKIC5jYXRjaChmdW5jdGlv"
    "bigpe2IuZGlzYWJsZWQ9ZmFsc2U7c2F5KCJhY091dCIsJzxzcGFuIGNsYXNzPSJmYWlsIj5Db3VsZG5cJ3QgcmVhY2ggc2ViYmku"
    "cHJvLjwvc3Bhbj4nKX0pfTsKaWYoc2F2ZWQoKSlyZWZyZXNoQWNjb3VudCgpOwoKLyogcHJpY2luZyAqLwp2YXIgZHY9JCgiZGV2"
    "Iik7ZnVuY3Rpb24gcHJpY2UoKXt2YXIgdj0rZHYudmFsdWUsbj1NYXRoLm1heCgxLE1hdGgucm91bmQoTWF0aC5wb3coMTAsdi8x"
    "MDAqNykpKTsKIG49bjwxMDA/bjoobjwxMDAwMD9NYXRoLnJvdW5kKG4vMTApKjEwOk1hdGgucm91bmQobi8xMDAwKSoxMDAwKTsK"
    "ICQoImRldm4iKS50ZXh0Q29udGVudD1uLnRvTG9jYWxlU3RyaW5nKCJlbi1HQiIpOyQoImNvc3QiKS50ZXh0Q29udGVudD1tb25l"
    "eShuKjAuNSl9CmR2LmFkZEV2ZW50TGlzdGVuZXIoImlucHV0IixwcmljZSk7cHJpY2UoKTsKCi8qIGxpdmUgbG9nICovCmZldGNo"
    "KCIvcC9zdGgiLHtjYWNoZToibm8tc3RvcmUifSkudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0"
    "aW9uKGQpewogJCgic2l6ZSIpLnRleHRDb250ZW50PShkLnRyZWVfc2l6ZXx8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUdCIik7CiB2"
    "YXIgcz1kLmxhdGVzdF9zZWFsZWRfdHJlZV9oZWFkOyQoInNlYWxlZCIpLnRleHRDb250ZW50PXMmJnMuYmxvY2tfaW5kZXghPW51"
    "bGw/cy5ibG9ja19pbmRleDoi4oCUIn0pLmNhdGNoKGZ1bmN0aW9uKCl7fSk7CgovKiByZWNlaXB0IGNoZWNrLCBpbiB0aGUgYnJv"
    "d3NlciAqLwpmdW5jdGlvbiBoZXgyYihoKXt2YXIgYT1uZXcgVWludDhBcnJheShoLmxlbmd0aC8yKTtmb3IodmFyIGk9MDtpPGEu"
    "bGVuZ3RoO2krKylhW2ldPXBhcnNlSW50KGguc3Vic3RyKGkqMiwyKSwxNik7cmV0dXJuIGF9CmZ1bmN0aW9uIGIyaGV4KGIpe3Jl"
    "dHVybiBBcnJheS5wcm90b3R5cGUubWFwLmNhbGwobmV3IFVpbnQ4QXJyYXkoYiksZnVuY3Rpb24oeCl7cmV0dXJuKCIwIit4LnRv"
    "U3RyaW5nKDE2KSkuc2xpY2UoLTIpfSkuam9pbigiIil9CmZ1bmN0aW9uIGNhdCgpe3ZhciBuPTAsaTtmb3IoaT0wO2k8YXJndW1l"
    "bnRzLmxlbmd0aDtpKyspbis9YXJndW1lbnRzW2ldLmxlbmd0aDt2YXIgbz1uZXcgVWludDhBcnJheShuKSxwPTA7Zm9yKGk9MDtp"
    "PGFyZ3VtZW50cy5sZW5ndGg7aSsrKXtvLnNldChhcmd1bWVudHNbaV0scCk7cCs9YXJndW1lbnRzW2ldLmxlbmd0aH1yZXR1cm4g"
    "b30KZnVuY3Rpb24gSChiKXtyZXR1cm4gY3J5cHRvLnN1YnRsZS5kaWdlc3QoIlNIQS0yNTYiLGIpLnRoZW4oZnVuY3Rpb24oZCl7"
    "cmV0dXJuIG5ldyBVaW50OEFycmF5KGQpfSl9CmZ1bmN0aW9uIHZlcmlmeShlbnRyeSxpZHgsc2l6ZSxwYXRoLHJvb3QpewogaWYo"
    "aWR4PDB8fGlkeD49c2l6ZSlyZXR1cm4gUHJvbWlzZS5yZXNvbHZlKGZhbHNlKTsKIHZhciBmbj1pZHgsc249c2l6ZS0xOwogcmV0"
    "dXJuIEgoY2F0KG5ldyBVaW50OEFycmF5KFswXSksaGV4MmIoZW50cnkpKSkudGhlbihmdW5jdGlvbihyKXsKICB2YXIgY2hhaW49"
    "UHJvbWlzZS5yZXNvbHZlKHIpLGJhZD1mYWxzZTsKICBwYXRoLmZvckVhY2goZnVuY3Rpb24ocGgpe2NoYWluPWNoYWluLnRoZW4o"
    "ZnVuY3Rpb24ocil7dmFyIHA9aGV4MmIocGgpO2lmKHNuPT09MCl7YmFkPXRydWU7cmV0dXJuIHJ9dmFyIHByOwogICBpZigoZm4m"
    "MSl8fGZuPT09c24pe3ByPUgoY2F0KG5ldyBVaW50OEFycmF5KFsxXSkscCxyKSk7aWYoIShmbiYxKSl7d2hpbGUoIShmbiYxKSYm"
    "Zm4hPT0wKXtmbj4+PTE7c24+Pj0xfX19CiAgIGVsc2UgcHI9SChjYXQobmV3IFVpbnQ4QXJyYXkoWzFdKSxyLHApKTtmbj4+PTE7"
    "c24+Pj0xO3JldHVybiBwcn0pfSk7CiAgcmV0dXJuIGNoYWluLnRoZW4oZnVuY3Rpb24ocil7cmV0dXJuICFiYWQmJnNuPT09MCYm"
    "YjJoZXgocik9PT1yb290fSl9KX0KZnVuY3Rpb24gcnVuKCl7dmFyIG49cGFyc2VJbnQoJCgibGVhZiIpLnZhbHVlLDEwKTsKIGlm"
    "KGlzTmFOKG4pfHxuPDApe3NheSgib3V0IiwiVHlwZSBhbiBlbnRyeSBudW1iZXIgKDAgb3IgbW9yZSkuIik7cmV0dXJufQogc2F5"
    "KCJvdXQiLCJGZXRjaGluZyBlbnRyeSAiK24rIuKApiIpOwogZmV0Y2goIi9wL3JlY2VpcHQ/bGVhZj0iK24se2NhY2hlOiJuby1z"
    "dG9yZSJ9KS50aGVuKGZ1bmN0aW9uKHIpe3JldHVybiByLmpzb24oKX0pLnRoZW4oZnVuY3Rpb24oZCl7CiAgaWYoZC5lcnJvcil7"
    "c2F5KCJvdXQiLCJObyBlbnRyeSAiK24rIiB5ZXQuIik7cmV0dXJufQogIHJldHVybiB2ZXJpZnkoZC5lbnRyeV9oYXNoLGQubGVh"
    "Zl9pbmRleCxkLnRyZWVfc2l6ZSxkLmF1ZGl0X3BhdGgsZC5yb290KS50aGVuKGZ1bmN0aW9uKG9rKXt2YXIgY3A9ZC5jaGVja3Bv"
    "aW50OwogICBzYXkoIm91dCIsKG9rPyc8c3BhbiBjbGFzcz0icGFzcyI+UEFTUzwvc3Bhbj4gY2hlY2tlZCBpbiB5b3VyIGJyb3dz"
    "ZXI6IGVudHJ5ICc6JzxzcGFuIGNsYXNzPSJmYWlsIj5GQUlMPC9zcGFuPiB0aGUgbWF0aHMgZG9lcyBub3QgYWRkIHVwIGZvciBl"
    "bnRyeSAnKStuKwogICAiIGlzIGluIHRoZSBsb2cgb2YgIitkLnRyZWVfc2l6ZSsiIGVudHJpZXMuPGJyPkZpbmdlcnByaW50OiAi"
    "K2VzYyhkLmVudHJ5X2hhc2gpKyI8YnI+Um9vdDogIitlc2MoZC5yb290KSsKICAgKGNwJiZjcC5ibG9ja19pbmRleCE9bnVsbD8n"
    "PGJyPlNlYWxlZCBpbiBjaGFpbiBibG9jayA8YSBocmVmPSIveC93YWxrL2Jsb2NrP2luZGV4PScrY3AuYmxvY2tfaW5kZXgrJyI+"
    "JytjcC5ibG9ja19pbmRleCsiPC9hPiI6Ijxicj5TZWFsaW5nIGludG8gdGhlIGNoYWluIHdpdGhpbiB0aGUgbWludXRlLiIpKX0p"
    "CiB9KS5jYXRjaChmdW5jdGlvbigpe3NheSgib3V0IiwiQ291bGRuJ3QgcmVhY2ggdGhlIGxvZy4iKX0pfQokKCJnbyIpLm9uY2xp"
    "Y2s9cnVuOyQoImxlYWYiKS5hZGRFdmVudExpc3RlbmVyKCJrZXlkb3duIixmdW5jdGlvbihlKXtpZihlLmtleT09PSJFbnRlciIp"
    "cnVuKCl9KTsKfSkoKTsKPC9zY3JpcHQ+PC9ib2R5PjwvaHRtbD4K"
)
_ADAPTER_B64 = (
    "IiIiCnNlYmJpX2FkYXB0ZXIucHkgIHYxLjEuMCAtIGRyb3AtaW4gc3RhdGUgYW5jaG9yaW5nIGZvciBsZWdhY3kgYXBwbGljYXRp"
    "b25zLgoKWW91ciBhcHBsaWNhdGlvbiBrZWVwcyBpdHMgZGF0YWJhc2UsIGl0cyBsb2dpYyBhbmQgaXRzIGluZnJhc3RydWN0dXJl"
    "LiBUaGlzCmZpbGUgc2l0cyBiZXNpZGUgaXQ6IGV2ZXJ5IHN0YXRlIGNoYW5nZSB5b3UgcG9pbnQgaXQgYXQgaXMgdHVybmVkIGlu"
    "dG8gYQpTSEEtMjU2IGZpbmdlcnByaW50LCBxdWV1ZWQgbG9jYWxseSwgYW5kIHNlbnQgaW4gdGhlIGJhY2tncm91bmQgdG8gdGhl"
    "CnNlYmJpLnBybyBwdWJsaWMgcHJvb2YgbG9nLCB3aGljaCByZXR1cm5zIGEgcmVjZWlwdCBwcm92aW5nIHRoZSBmaW5nZXJwcmlu"
    "dAppcyBpbiBhbiBhcHBlbmQtb25seSBSRkMgNjk2MiBNZXJrbGUgdHJlZSB3aG9zZSB0cmVlIGhlYWRzIGFyZSBzZWFsZWQgaW50"
    "byB0aGUKc2ViYmkucHJvIGNoYWluIGFuZCB0aW1lc3RhbXBlZCBpbiBCaXRjb2luLgoKT25seSB0aGUgZmluZ2VycHJpbnQgbGVh"
    "dmVzIHlvdXIgbWFjaGluZS4gVGhlIGRhdGEgaXRzZWxmIG5ldmVyIGRvZXMuCgpUV08gTElORVMKLS0tLS0tLS0tCiAgICBleHBv"
    "cnQgU0VCQklfQVBJX0tFWT15b3VyLWtleSAgICAgICAgICAob25jZSwgaW4gdGhlIGVudmlyb25tZW50KQoKICAgIGZyb20gc2Vi"
    "YmlfYWRhcHRlciBpbXBvcnQgYW5jaG9yX3N0YXRlCiAgICBAYW5jaG9yX3N0YXRlKCJvcmRlcnMudXBkYXRlIikKICAgIGRlZiB1"
    "cGRhdGVfb3JkZXIob3JkZXJfaWQsIHN0YXR1cyk6CiAgICAgICAgLi4uICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "IyB1bmNoYW5nZWQKICAgICAgICByZXR1cm4geyJvcmRlcl9pZCI6IG9yZGVyX2lkLCAic3RhdHVzIjogc3RhdHVzfQoKTmFtZSB0"
    "aGUgZGV2aWNlIGVhY2ggY2hhbmdlIGlzIGFib3V0IChhIHBob25lLCB0aWxsLCB0ZXJtaW5hbCwgY2FyKSBhbmQgaXQgaXMKbWV0"
    "ZXJlZCBwZXIgZGV2aWNlLCB0aGUgc2FtZSBhcyB0aGUgc2ViYmkucHJvIGVuZ2luZToKCiAgICBAYW5jaG9yX3N0YXRlKCJjYWxs"
    "cy5yb3V0ZSIsIGRldmljZT0iaGFuZHNldF9pZCIpICAgICMgYSBmaWVsZCBpbiB0aGUgcmVzdWx0CiAgICBAYW5jaG9yX3N0YXRl"
    "KCJwb3Muc2FsZSIsIGRldmljZT1sYW1iZGEgcmVzdWx0LCBhcmdzLCBrd2FyZ3M6IHJlc3VsdFsidGlsbCJdKQogICAgcmVjb3Jk"
    "KHsiYWNjb3VudCI6IDQyLCAiYmFsYW5jZSI6IDEyNTB9LCBkZXZpY2U9IklNRUktMzUuLi4iKQoKRGV2aWNlIG5hbWVzIGFyZSBv"
    "bmUtd2F5IGhhc2hlZCBvbiB5b3VyIG1hY2hpbmUgYmVmb3JlIHRoZXkgYXJlIHNlbnQuCgpUaGUgcmV0dXJuIHZhbHVlIGlzIGZp"
    "bmdlcnByaW50ZWQgYWZ0ZXIgdGhlIGZ1bmN0aW9uIHN1Y2NlZWRzLiBUaGUgY2FsbCBpcwpuZXZlciBzbG93ZWQgZG93biBieSB0"
    "aGUgbmV0d29yayBhbmQgbmV2ZXIgZmFpbHMgYmVjYXVzZSBvZiB0aGlzIGZpbGU6CmZpbmdlcnByaW50cyBnbyBpbnRvIGEgbG9j"
    "YWwgYXBwZW5kLW9ubHkgcXVldWUgKHNxbGl0ZSkgYW5kIGEgYmFja2dyb3VuZAp0aHJlYWQgc2VuZHMgdGhlbS4gSWYgc2ViYmku"
    "cHJvIGlzIHVucmVhY2hhYmxlIHRoZXkgd2FpdCwgYW5kIGFyZSBzZW50IHdoZW4gaXQKY29tZXMgYmFjaywgaW4gb3JkZXIsIHdp"
    "dGggbm8gZHVwbGljYXRlcy4KCk9USEVSIFdBWVMgSU4KLS0tLS0tLS0tLS0tLQogICAgZnJvbSBzZWJiaV9hZGFwdGVyIGltcG9y"
    "dCByZWNvcmQsIEFuY2hvckxvZ0hhbmRsZXIKICAgIHJlY29yZCh7ImFjY291bnQiOiA0MiwgImJhbGFuY2UiOiAxMjUwfSkgICAg"
    "ICAgICAgIyBhbnl3aGVyZSwgcmV0dXJucyB0aGUgaGFzaAogICAgbG9nZ2luZy5nZXRMb2dnZXIoInBheW1lbnRzIikuYWRkSGFu"
    "ZGxlcihBbmNob3JMb2dIYW5kbGVyKCkpICAgIyBldmVyeSBsb2cgbGluZQoKICAgIEBhbmNob3Jfc3RhdGUoImxlZGdlci5wb3N0"
    "IiwgY2FwdHVyZT0iYXJncyIpICAgICAgIyBmaW5nZXJwcmludCB0aGUgaW5wdXRzIGluc3RlYWQKICAgIEBhbmNob3Jfc3RhdGUo"
    "InVzZXIuc2F2ZSIsIGV4dHJhY3Q9bGFtYmRhIHJlc3VsdCwgYXJncywga3dhcmdzOiByZXN1bHQudG9fZGljdCgpKQoKQXN5bmMg"
    "ZnVuY3Rpb25zIHdvcmsgdGhlIHNhbWUgd2F5LgoKQ0hFQ0tJTkcKLS0tLS0tLS0KICAgIHB5dGhvbiBzZWJiaV9hZGFwdGVyLnB5"
    "IHN0YXR1cyAgICAgICAgICAgIHF1ZXVlIGFuZCByZWNlaXB0IGNvdW50cwogICAgcHl0aG9uIHNlYmJpX2FkYXB0ZXIucHkgZmx1"
    "c2ggICAgICAgICAgICAgc2VuZCB3aGF0IGlzIHdhaXRpbmcsIG5vdwogICAgcHl0aG9uIHNlYmJpX2FkYXB0ZXIucHkgcmVjZWlw"
    "dCA8aGFzaD4gICAgdGhlIHJlY2VpcHQgZm9yIG9uZSBmaW5nZXJwcmludAogICAgcHl0aG9uIHNlYmJpX2FkYXB0ZXIucHkgdmVy"
    "aWZ5ICAgICAgICAgICAgcmUtY2hlY2sgZXZlcnkgc3RvcmVkIHJlY2VpcHQgbG9jYWxseQogICAgcHl0aG9uIHNlYmJpX2FkYXB0"
    "ZXIucHkgaGFzaCAnPGpzb24+JyAgICAgZmluZ2VycHJpbnQgYSBKU09OIHZhbHVlIGV4YWN0bHkgYXMgdGhlIGFkYXB0ZXIgd291"
    "bGQKCkV2ZXJ5IHJlY2VpcHQgaXMgY2hlY2tlZCBvbiBhcnJpdmFsIHdpdGggYW4gUkZDIDY5NjIgaW5jbHVzaW9uIGNoZWNrLCBz"
    "byB0aGUKc2VydmVyJ3MgYW5zd2VyIGlzIHZlcmlmaWVkLCBub3QgdHJ1c3RlZC4gQSByZWNlaXB0IHRoYXQgZmFpbHMgdGhlIGNo"
    "ZWNrIGlzCmtlcHQgKGFzIGV2aWRlbmNlKSBhbmQgZmxhZ2dlZC4KCkZJTkdFUlBSSU5UIFJVTEUgKHNvIGFueW9uZSBjYW4gcmVj"
    "b21wdXRlIGl0KQotLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KU0hBLTI1NiBvdmVyIGNhbm9u"
    "aWNhbCBKU09OOiBrZXlzIHNvcnRlZCwgc2VwYXJhdG9ycyAiLCIgYW5kICI6IiwgVVRGLTgsIG5vCmV4dHJhIHdoaXRlc3BhY2Uu"
    "IGRhdGV0aW1lL2RhdGUgLT4gSVNPIDg2MDEgc3RyaW5nLCBEZWNpbWFsIC0+IHN0cmluZywKYnl0ZXMgLT4gaGV4LCBzZXQgLT4g"
    "c29ydGVkIGxpc3QsIFVVSUQgLT4gc3RyaW5nLCBkYXRhY2xhc3MgLT4gaXRzIGZpZWxkcywKb2JqZWN0cyB3aXRoIHRvX2RpY3Qo"
    "KS9fYXNkaWN0KCkgLT4gdGhhdC4gRmxvYXRzIHVzZSBQeXRob24ncyByZXByLiBBbnl0aGluZwplbHNlIGlzIHJlZnVzZWQgKGFu"
    "ZCBsb2dnZWQpIHJhdGhlciB0aGFuIGd1ZXNzZWQgYXQgLSBwYXNzIGV4dHJhY3Q9IGZvciB0aG9zZS4KClBSSUNFCi0tLS0tCkZy"
    "ZWUgZm9yIDkwIGRheXMgb24gYSBuZXcgc2ViYmkucHJvIGtleSwgdGhlbiA1MHAgcGVyIGRldmljZSBwZXIgbW9udGg6CmV2ZXJ5"
    "IGRpc3RpbmN0IGRldmljZSB5b3VyIHJlY29yZHMgYXJlIGFib3V0LCBjb3VudGVkIG9uY2UgaW4gYSBjYWxlbmRhcgptb250aCBo"
    "b3dldmVyIG1hbnkgY2hhbmdlcyBpdCBtYWtlcy4gUmVjb3JkcyB3aXRoIG5vIGRldmljZSBuYW1lZCBjb3VudCB0aGUKbWFjaGlu"
    "ZSBydW5uaW5nIHRoaXMgZmlsZS4KClNFVFRJTkdTIChlbnZpcm9ubWVudCBvciBBbmNob3IoLi4uKSBhcmd1bWVudHMpCi0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBTRUJCSV9BUElfS0VZICAgICAgICB5b3VyIGtl"
    "eSAod2l0aG91dCBpdCwgZmluZ2VycHJpbnRzIHF1ZXVlIGFuZCB3YWl0KQogICAgU0VCQklfRU5EUE9JTlQgICAgICAgZGVmYXVs"
    "dCBodHRwczovL3NlYmJpLnBybwogICAgU0VCQklfREIgICAgICAgICAgICAgZGVmYXVsdCAuL3NlYmJpX2FuY2hvci5kYgogICAg"
    "U0VCQklfREVWSUNFX0lEICAgICAgbmFtZSB0aGlzIG1hY2hpbmUgeW91cnNlbGYgKGRlZmF1bHQ6IG1hZGUgb25jZSBhbmQga2Vw"
    "dCBpbiBTRUJCSV9EQikKICAgIFNFQkJJX0RJU0FCTEVEPTEgICAgIHJlY29yZCBub3RoaW5nIChraWxsIHN3aXRjaCkKClN0YW5k"
    "YXJkIGxpYnJhcnkgb25seS4gUHl0aG9uIDMuOCsuCiIiIgoKaW1wb3J0IGFzeW5jaW8KaW1wb3J0IGF0ZXhpdAppbXBvcnQgZGF0"
    "YWNsYXNzZXMKaW1wb3J0IGRhdGV0aW1lCmltcG9ydCBkZWNpbWFsCmltcG9ydCBmdW5jdG9vbHMKaW1wb3J0IGhhc2hsaWIKaW1w"
    "b3J0IGluc3BlY3QKaW1wb3J0IGpzb24KaW1wb3J0IGxvZ2dpbmcKaW1wb3J0IG9zCmltcG9ydCBzcWxpdGUzCmltcG9ydCBzeXMK"
    "aW1wb3J0IHRocmVhZGluZwppbXBvcnQgdGltZQppbXBvcnQgdXJsbGliLmVycm9yCmltcG9ydCB1cmxsaWIucmVxdWVzdAppbXBv"
    "cnQgdXVpZAoKX192ZXJzaW9uX18gPSAiMS4xLjAiCl9fYWxsX18gPSBbImFuY2hvcl9zdGF0ZSIsICJyZWNvcmQiLCAiQW5jaG9y"
    "IiwgIkFuY2hvckxvZ0hhbmRsZXIiLCAiY2Fub25pY2FsX2pzb24iLCAic3RhdGVfaGFzaCIsCiAgICAgICAgICAgInZlcmlmeV9p"
    "bmNsdXNpb24iLCAidmVyaWZ5X2NvbnNpc3RlbmN5IiwgImdldF9kZWZhdWx0Il0KCmxvZyA9IGxvZ2dpbmcuZ2V0TG9nZ2VyKCJz"
    "ZWJiaV9hZGFwdGVyIikKCgojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0t"
    "LS0tLS0tLS0gZmluZ2VycHJpbnRzCgpkZWYgX2RlZmF1bHQobyk6CiAgICBpZiBpc2luc3RhbmNlKG8sIChkYXRldGltZS5kYXRl"
    "dGltZSwgZGF0ZXRpbWUuZGF0ZSwgZGF0ZXRpbWUudGltZSkpOgogICAgICAgIHJldHVybiBvLmlzb2Zvcm1hdCgpCiAgICBpZiBp"
    "c2luc3RhbmNlKG8sIGRlY2ltYWwuRGVjaW1hbCk6CiAgICAgICAgcmV0dXJuIHN0cihvKQogICAgaWYgaXNpbnN0YW5jZShvLCAo"
    "Ynl0ZXMsIGJ5dGVhcnJheSwgbWVtb3J5dmlldykpOgogICAgICAgIHJldHVybiBieXRlcyhvKS5oZXgoKQogICAgaWYgaXNpbnN0"
    "YW5jZShvLCAoc2V0LCBmcm96ZW5zZXQpKToKICAgICAgICByZXR1cm4gc29ydGVkKG8sIGtleT1sYW1iZGEgeDogY2Fub25pY2Fs"
    "X2pzb24oeCkpCiAgICBpZiBpc2luc3RhbmNlKG8sIHV1aWQuVVVJRCk6CiAgICAgICAgcmV0dXJuIHN0cihvKQogICAgaWYgZGF0"
    "YWNsYXNzZXMuaXNfZGF0YWNsYXNzKG8pIGFuZCBub3QgaXNpbnN0YW5jZShvLCB0eXBlKToKICAgICAgICByZXR1cm4gZGF0YWNs"
    "YXNzZXMuYXNkaWN0KG8pCiAgICBmb3IgYXR0ciBpbiAoInRvX2RpY3QiLCAiX2FzZGljdCIpOgogICAgICAgIGZuID0gZ2V0YXR0"
    "cihvLCBhdHRyLCBOb25lKQogICAgICAgIGlmIGNhbGxhYmxlKGZuKToKICAgICAgICAgICAgcmV0dXJuIGZuKCkKICAgIHJhaXNl"
    "IFR5cGVFcnJvcigiY2Fubm90IGZpbmdlcnByaW50ICVzIC0gcGFzcyBleHRyYWN0PSB0byBjaG9vc2Ugd2hhdCB0byByZWNvcmQi"
    "ICUgdHlwZShvKS5fX25hbWVfXykKCgpkZWYgY2Fub25pY2FsX2pzb24ob2JqKToKICAgICIiIlRoZSBleGFjdCBieXRlcyB0aGUg"
    "ZmluZ2VycHJpbnQgaXMgdGFrZW4gb3Zlci4iIiIKICAgIHJldHVybiBqc29uLmR1bXBzKG9iaiwgc29ydF9rZXlzPVRydWUsIHNl"
    "cGFyYXRvcnM9KCIsIiwgIjoiKSwgZW5zdXJlX2FzY2lpPUZhbHNlLAogICAgICAgICAgICAgICAgICAgICAgYWxsb3dfbmFuPUZh"
    "bHNlLCBkZWZhdWx0PV9kZWZhdWx0KS5lbmNvZGUoInV0Zi04IikKCgpkZWYgc3RhdGVfaGFzaChvYmopOgogICAgIiIiU0hBLTI1"
    "NiBvZiBjYW5vbmljYWwgSlNPTiwgYXMgNjQgbG93ZXJjYXNlIGhleCBjaGFyYWN0ZXJzLiIiIgogICAgcmV0dXJuIGhhc2hsaWIu"
    "c2hhMjU2KGNhbm9uaWNhbF9qc29uKG9iaikpLmhleGRpZ2VzdCgpCgoKIyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tIFJGQyA2OTYyIGNoZWNrcwoKZGVmIF9oKGIpOgogICAgcmV0dXJuIGhh"
    "c2hsaWIuc2hhMjU2KGIpLmRpZ2VzdCgpCgoKZGVmIGxlYWZfaGFzaChlbnRyeV9oZXgpOgogICAgcmV0dXJuIF9oKGIiXHgwMCIg"
    "KyBieXRlcy5mcm9taGV4KGVudHJ5X2hleCkpLmhleCgpCgoKZGVmIHZlcmlmeV9pbmNsdXNpb24oZW50cnlfaGV4LCBpbmRleCwg"
    "dHJlZV9zaXplLCBwYXRoLCByb290KToKICAgICIiIlJGQyA5MTYyIHNlY3Rpb24gMi4xLjMuMjogaXMgZW50cnkgYXQgYGluZGV4"
    "YCBpbiB0aGUgdHJlZSBvZiBgdHJlZV9zaXplYCB3aXRoIGByb290YD8iIiIKICAgIHRyeToKICAgICAgICBpbmRleCwgdHJlZV9z"
    "aXplID0gaW50KGluZGV4KSwgaW50KHRyZWVfc2l6ZSkKICAgICAgICBpZiBpbmRleCA8IDAgb3IgaW5kZXggPj0gdHJlZV9zaXpl"
    "OgogICAgICAgICAgICByZXR1cm4gRmFsc2UKICAgICAgICBmbiwgc24gPSBpbmRleCwgdHJlZV9zaXplIC0gMQogICAgICAgIHIg"
    "PSBfaChiIlx4MDAiICsgYnl0ZXMuZnJvbWhleChlbnRyeV9oZXgpKQogICAgICAgIGZvciBwX2hleCBpbiBwYXRoOgogICAgICAg"
    "ICAgICBwID0gYnl0ZXMuZnJvbWhleChwX2hleCkKICAgICAgICAgICAgaWYgc24gPT0gMDoKICAgICAgICAgICAgICAgIHJldHVy"
    "biBGYWxzZQogICAgICAgICAgICBpZiAoZm4gJiAxKSBvciBmbiA9PSBzbjoKICAgICAgICAgICAgICAgIHIgPSBfaChiIlx4MDEi"
    "ICsgcCArIHIpCiAgICAgICAgICAgICAgICBpZiBub3QgKGZuICYgMSk6CiAgICAgICAgICAgICAgICAgICAgd2hpbGUgbm90IChm"
    "biAmIDEpIGFuZCBmbiAhPSAwOgogICAgICAgICAgICAgICAgICAgICAgICBmbiA+Pj0gMQogICAgICAgICAgICAgICAgICAgICAg"
    "ICBzbiA+Pj0gMQogICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgciA9IF9oKGIiXHgwMSIgKyByICsgcCkKICAgICAg"
    "ICAgICAgZm4gPj49IDEKICAgICAgICAgICAgc24gPj49IDEKICAgICAgICByZXR1cm4gc24gPT0gMCBhbmQgciA9PSBieXRlcy5m"
    "cm9taGV4KHJvb3QpCiAgICBleGNlcHQgKFZhbHVlRXJyb3IsIFR5cGVFcnJvcik6CiAgICAgICAgcmV0dXJuIEZhbHNlCgoKZGVm"
    "IHZlcmlmeV9jb25zaXN0ZW5jeShmaXJzdCwgc2Vjb25kLCBmaXJzdF9yb290LCBzZWNvbmRfcm9vdCwgcHJvb2YpOgogICAgIiIi"
    "UkZDIDkxNjIgc2VjdGlvbiAyLjEuNC4yOiBpcyB0aGUgdHJlZSBvZiBzaXplIGBzZWNvbmRgIGFuIGFwcGVuZC1vbmx5IGV4dGVu"
    "c2lvbiBvZiBgZmlyc3RgPyIiIgogICAgdHJ5OgogICAgICAgIGZpcnN0LCBzZWNvbmQgPSBpbnQoZmlyc3QpLCBpbnQoc2Vjb25k"
    "KQogICAgICAgIGZyX2IsIHNyX2IgPSBieXRlcy5mcm9taGV4KGZpcnN0X3Jvb3QpLCBieXRlcy5mcm9taGV4KHNlY29uZF9yb290"
    "KQogICAgICAgIHBhdGggPSBbYnl0ZXMuZnJvbWhleChwKSBmb3IgcCBpbiBwcm9vZl0KICAgICAgICBpZiBmaXJzdCA9PSBzZWNv"
    "bmQ6CiAgICAgICAgICAgIHJldHVybiBub3QgcGF0aCBhbmQgZnJfYiA9PSBzcl9iCiAgICAgICAgaWYgZmlyc3QgPCAxIG9yIGZp"
    "cnN0ID4gc2Vjb25kIG9yIG5vdCBwYXRoOgogICAgICAgICAgICByZXR1cm4gRmFsc2UKICAgICAgICBpZiBmaXJzdCAmIChmaXJz"
    "dCAtIDEpID09IDA6CiAgICAgICAgICAgIHBhdGggPSBbZnJfYl0gKyBwYXRoCiAgICAgICAgZm4sIHNuID0gZmlyc3QgLSAxLCBz"
    "ZWNvbmQgLSAxCiAgICAgICAgd2hpbGUgZm4gJiAxOgogICAgICAgICAgICBmbiA+Pj0gMQogICAgICAgICAgICBzbiA+Pj0gMQog"
    "ICAgICAgIGZyID0gc3IgPSBwYXRoWzBdCiAgICAgICAgZm9yIGMgaW4gcGF0aFsxOl06CiAgICAgICAgICAgIGlmIHNuID09IDA6"
    "CiAgICAgICAgICAgICAgICByZXR1cm4gRmFsc2UKICAgICAgICAgICAgaWYgKGZuICYgMSkgb3IgZm4gPT0gc246CiAgICAgICAg"
    "ICAgICAgICBmciA9IF9oKGIiXHgwMSIgKyBjICsgZnIpCiAgICAgICAgICAgICAgICBzciA9IF9oKGIiXHgwMSIgKyBjICsgc3Ip"
    "CiAgICAgICAgICAgICAgICBpZiBub3QgKGZuICYgMSk6CiAgICAgICAgICAgICAgICAgICAgd2hpbGUgbm90IChmbiAmIDEpIGFu"
    "ZCBmbiAhPSAwOgogICAgICAgICAgICAgICAgICAgICAgICBmbiA+Pj0gMQogICAgICAgICAgICAgICAgICAgICAgICBzbiA+Pj0g"
    "MQogICAgICAgICAgICBlbHNlOgogICAgICAgICAgICAgICAgc3IgPSBfaChiIlx4MDEiICsgc3IgKyBjKQogICAgICAgICAgICBm"
    "biA+Pj0gMQogICAgICAgICAgICBzbiA+Pj0gMQogICAgICAgIHJldHVybiBmciA9PSBmcl9iIGFuZCBzciA9PSBzcl9iIGFuZCBz"
    "biA9PSAwCiAgICBleGNlcHQgKFZhbHVlRXJyb3IsIFR5cGVFcnJvcik6CiAgICAgICAgcmV0dXJuIEZhbHNlCgoKZGVmIGRldmlj"
    "ZV90b2tlbihkZXZpY2UpOgogICAgIiIiT25lLXdheSBkZXZpY2UgbmFtZSBzZW50IGZvciBtZXRlcmluZzogdGhlIHNhbWUgZGV2"
    "aWNlIGFsd2F5cyBnaXZlcyB0aGUgc2FtZSB0b2tlbi4iIiIKICAgIGlmIGRldmljZSBpcyBOb25lIG9yIGRldmljZSA9PSAiIjoK"
    "ICAgICAgICByZXR1cm4gTm9uZQogICAgcmV0dXJuICJkXyIgKyBoYXNobGliLnNoYTI1NigoInNlYmJpLWRldmljZToiICsgc3Ry"
    "KGRldmljZSkpLmVuY29kZSgidXRmLTgiKSkuaGV4ZGlnZXN0KClbOjMyXQoKCiMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLSB0aGUgc2lkZWNhcgoKY2xhc3MgQW5jaG9yKG9iamVjdCk6CiAg"
    "ICAiIiJMb2NhbCBhcHBlbmQtb25seSBxdWV1ZSArIGJhY2tncm91bmQgc2VuZGVyLiBTYWZlIGFjcm9zcyB0aHJlYWRzLCBwcm9j"
    "ZXNzZXMgYW5kIGZvcmtzLiIiIgoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCBhcGlfa2V5PU5vbmUsIGVuZHBvaW50PU5vbmUsIGRi"
    "X3BhdGg9Tm9uZSwgYmF0Y2hfc2l6ZT0yMDAsCiAgICAgICAgICAgICAgICAgZmx1c2hfaW50ZXJ2YWw9Mi4wLCB0aW1lb3V0PTEw"
    "LjAsIGNoZWNrX2NoYWluPVRydWUsIHN0YXJ0PVRydWUpOgogICAgICAgIHNlbGYuYXBpX2tleSA9IChhcGlfa2V5IGlmIGFwaV9r"
    "ZXkgaXMgbm90IE5vbmUgZWxzZSBvcy5lbnZpcm9uLmdldCgiU0VCQklfQVBJX0tFWSIsICIiKSkuc3RyaXAoKQogICAgICAgIHNl"
    "bGYuZW5kcG9pbnQgPSAoZW5kcG9pbnQgb3Igb3MuZW52aXJvbi5nZXQoIlNFQkJJX0VORFBPSU5UIiwgImh0dHBzOi8vc2ViYmku"
    "cHJvIikpLnJzdHJpcCgiLyIpCiAgICAgICAgc2VsZi5kYl9wYXRoID0gZGJfcGF0aCBvciBvcy5lbnZpcm9uLmdldCgiU0VCQklf"
    "REIiLCAic2ViYmlfYW5jaG9yLmRiIikKICAgICAgICBzZWxmLmJhdGNoX3NpemUgPSBtYXgoMSwgbWluKDUwMCwgaW50KGJhdGNo"
    "X3NpemUpKSkKICAgICAgICBzZWxmLmZsdXNoX2ludGVydmFsID0gZmxvYXQoZmx1c2hfaW50ZXJ2YWwpCiAgICAgICAgc2VsZi50"
    "aW1lb3V0ID0gZmxvYXQodGltZW91dCkKICAgICAgICBzZWxmLmNoZWNrX2NoYWluID0gYm9vbChjaGVja19jaGFpbikKICAgICAg"
    "ICBzZWxmLmRpc2FibGVkID0gb3MuZW52aXJvbi5nZXQoIlNFQkJJX0RJU0FCTEVEIiwgIjAiKSA9PSAiMSIKICAgICAgICBzZWxm"
    "Ll9hdXRvc3RhcnQgPSBzdGFydAogICAgICAgIHNlbGYuX3dhcm5lZF9ub19rZXkgPSBGYWxzZQogICAgICAgIGlmIG5vdCBzZWxm"
    "LmVuZHBvaW50LnN0YXJ0c3dpdGgoImh0dHBzOi8vIikgYW5kICIxMjcuMC4wLjEiIG5vdCBpbiBzZWxmLmVuZHBvaW50IFwKICAg"
    "ICAgICAgICAgICAgIGFuZCAibG9jYWxob3N0IiBub3QgaW4gc2VsZi5lbmRwb2ludDoKICAgICAgICAgICAgbG9nLndhcm5pbmco"
    "InNlYmJpX2FkYXB0ZXI6IGVuZHBvaW50ICVzIGlzIG5vdCBodHRwcyIsIHNlbGYuZW5kcG9pbnQpCiAgICAgICAgc2VsZi5faW5p"
    "dF9wcm9jZXNzKCkKCiAgICAjIC0tIHByb2Nlc3MtbG9jYWwgc3RhdGUgKHJlYnVpbHQgYWZ0ZXIgZm9yaykgLS0KICAgIGRlZiBf"
    "aW5pdF9wcm9jZXNzKHNlbGYpOgogICAgICAgIHNlbGYuX3BpZCA9IG9zLmdldHBpZCgpCiAgICAgICAgc2VsZi5fd2lkID0gIiVk"
    "LSVzIiAlIChzZWxmLl9waWQsIHV1aWQudXVpZDQoKS5oZXhbOjhdKQogICAgICAgIHNlbGYuX2xrID0gdGhyZWFkaW5nLkxvY2so"
    "KQogICAgICAgIHNlbGYuX3dha2UgPSB0aHJlYWRpbmcuRXZlbnQoKQogICAgICAgIHNlbGYuX3N0b3AgPSB0aHJlYWRpbmcuRXZl"
    "bnQoKQogICAgICAgIHNlbGYuX2JhY2tvZmYgPSAwLjAKICAgICAgICBzZWxmLl90cmllZCA9IHt9CiAgICAgICAgc2VsZi5fZGIg"
    "PSBzcWxpdGUzLmNvbm5lY3Qoc2VsZi5kYl9wYXRoLCB0aW1lb3V0PTMwLCBpc29sYXRpb25fbGV2ZWw9Tm9uZSwgY2hlY2tfc2Ft"
    "ZV90aHJlYWQ9RmFsc2UpCiAgICAgICAgc2VsZi5fZGIuZXhlY3V0ZSgiUFJBR01BIGpvdXJuYWxfbW9kZT1XQUwiKQogICAgICAg"
    "IHNlbGYuX2RiLmV4ZWN1dGUoIlBSQUdNQSBzeW5jaHJvbm91cz1OT1JNQUwiKQogICAgICAgIHNlbGYuX2RiLmV4ZWN1dGUoIkNS"
    "RUFURSBUQUJMRSBJRiBOT1QgRVhJU1RTIGVudHJpZXMoc2VxIElOVEVHRVIgUFJJTUFSWSBLRVkgQVVUT0lOQ1JFTUVOVCwiCiAg"
    "ICAgICAgICAgICAgICAgICAgICAgICAiY2lkIFRFWFQgVU5JUVVFIE5PVCBOVUxMLGhhc2ggVEVYVCBOT1QgTlVMTCxsYWJlbCBU"
    "RVhULGNyZWF0ZWQgUkVBTCkiKQogICAgICAgIHNlbGYuX2RiLmV4ZWN1dGUoIkNSRUFURSBUQUJMRSBJRiBOT1QgRVhJU1RTIHJl"
    "Y2VpcHRzKGlkIElOVEVHRVIgUFJJTUFSWSBLRVkgQVVUT0lOQ1JFTUVOVCwiCiAgICAgICAgICAgICAgICAgICAgICAgICAiY2lk"
    "IFRFWFQgTk9UIE5VTEwsbGVhZl9pbmRleCBJTlRFR0VSLHJlY2VpcHQgVEVYVCx2ZXJpZmllZCBJTlRFR0VSLCIKICAgICAgICAg"
    "ICAgICAgICAgICAgICAgICJjaGVja3BvaW50ZWQgSU5URUdFUiBERUZBVUxUIDAsaW5fY2hhaW4gSU5URUdFUixyZWNlaXZlZCBS"
    "RUFMKSIpCiAgICAgICAgc2VsZi5fZGIuZXhlY3V0ZSgiQ1JFQVRFIElOREVYIElGIE5PVCBFWElTVFMgcmVjZWlwdHNfY2lkIE9O"
    "IHJlY2VpcHRzKGNpZCkiKQogICAgICAgIHNlbGYuX2RiLmV4ZWN1dGUoIkNSRUFURSBJTkRFWCBJRiBOT1QgRVhJU1RTIGVudHJp"
    "ZXNfaGFzaCBPTiBlbnRyaWVzKGhhc2gpIikKICAgICAgICBzZWxmLl9kYi5leGVjdXRlKCJDUkVBVEUgVEFCTEUgSUYgTk9UIEVY"
    "SVNUUyBjbGFpbXMoY2lkIFRFWFQgUFJJTUFSWSBLRVksd29ya2VyIFRFWFQsdW50aWwgUkVBTCkiKQogICAgICAgIHNlbGYuX2Ri"
    "LmV4ZWN1dGUoIkNSRUFURSBUQUJMRSBJRiBOT1QgRVhJU1RTIG1ldGEoayBURVhUIFBSSU1BUlkgS0VZLHYgVEVYVCkiKQogICAg"
    "ICAgIHRyeToKICAgICAgICAgICAgc2VsZi5fZGIuZXhlY3V0ZSgiQUxURVIgVEFCTEUgZW50cmllcyBBREQgQ09MVU1OIGRldmlj"
    "ZSBURVhUIikKICAgICAgICBleGNlcHQgc3FsaXRlMy5PcGVyYXRpb25hbEVycm9yOgogICAgICAgICAgICBwYXNzCiAgICAgICAg"
    "c2VsZi5fZGIuZXhlY3V0ZSgiSU5TRVJUIE9SIElHTk9SRSBJTlRPIG1ldGEoayx2KSBWQUxVRVMoJ2RldmljZScsPykiLCAoImRl"
    "dl8iICsgdXVpZC51dWlkNCgpLmhleFs6MjBdLCkpCiAgICAgICAgc2VsZi5kZXZpY2UgPSAob3MuZW52aXJvbi5nZXQoIlNFQkJJ"
    "X0RFVklDRV9JRCIsICIiKS5zdHJpcCgpWzo2MF0gb3IKICAgICAgICAgICAgICAgICAgICAgICBzZWxmLl9kYi5leGVjdXRlKCJT"
    "RUxFQ1QgdiBGUk9NIG1ldGEgV0hFUkUgaz0nZGV2aWNlJyIpLmZldGNob25lKClbMF0pCiAgICAgICAgc2VsZi5fdGhyZWFkID0g"
    "Tm9uZQogICAgICAgIGlmIHNlbGYuX2F1dG9zdGFydDoKICAgICAgICAgICAgc2VsZi5fc3RhcnRfdGhyZWFkKCkKCiAgICBkZWYg"
    "X2Vuc3VyZV9wcm9jZXNzKHNlbGYpOgogICAgICAgIGlmIG9zLmdldHBpZCgpICE9IHNlbGYuX3BpZDoKICAgICAgICAgICAgc2Vs"
    "Zi5faW5pdF9wcm9jZXNzKCkKCiAgICBkZWYgX3N0YXJ0X3RocmVhZChzZWxmKToKICAgICAgICBpZiBzZWxmLl90aHJlYWQgYW5k"
    "IHNlbGYuX3RocmVhZC5pc19hbGl2ZSgpOgogICAgICAgICAgICByZXR1cm4KICAgICAgICBzZWxmLl90aHJlYWQgPSB0aHJlYWRp"
    "bmcuVGhyZWFkKHRhcmdldD1zZWxmLl9ydW4sIG5hbWU9InNlYmJpLWFuY2hvciIsIGRhZW1vbj1UcnVlKQogICAgICAgIHNlbGYu"
    "X3RocmVhZC5zdGFydCgpCgogICAgIyAtLSByZWNvcmRpbmcgKGhvc3Qgc2lkZTogbG9jYWwgb25seSwgbmV2ZXIgcmFpc2VzKSAt"
    "LQogICAgZGVmIHJlY29yZChzZWxmLCBwYXlsb2FkLCBsYWJlbD1Ob25lLCBkZXZpY2U9Tm9uZSk6CiAgICAgICAgIiIiRmluZ2Vy"
    "cHJpbnQgYHBheWxvYWRgIGFuZCBxdWV1ZSBpdC4gYGRldmljZWAgbmFtZXMgd2hhdCBpdCBpcyBhYm91dCAocGhvbmUsIHRpbGwu"
    "Li4pLgogICAgICAgIFJldHVybnMgdGhlIGhhc2gsIG9yIE5vbmUgaWYgaXQgY291bGQgbm90IGJlIHJlY29yZGVkLiIiIgogICAg"
    "ICAgIGlmIHNlbGYuZGlzYWJsZWQ6CiAgICAgICAgICAgIHJldHVybiBOb25lCiAgICAgICAgdHJ5OgogICAgICAgICAgICByZXR1"
    "cm4gc2VsZi5yZWNvcmRfaGFzaChzdGF0ZV9oYXNoKHBheWxvYWQpLCBsYWJlbD1sYWJlbCwgZGV2aWNlPWRldmljZSkKICAgICAg"
    "ICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgICAgIGxvZy53YXJuaW5nKCJzZWJiaV9hZGFwdGVyOiBub3QgcmVjb3Jk"
    "ZWQgKCVzKSIsIGUpCiAgICAgICAgICAgIHJldHVybiBOb25lCgogICAgZGVmIHJlY29yZF9oYXNoKHNlbGYsIGhhc2hfaGV4LCBs"
    "YWJlbD1Ob25lLCBkZXZpY2U9Tm9uZSk6CiAgICAgICAgIiIiUXVldWUgYSBmaW5nZXJwcmludCB5b3UgY29tcHV0ZWQgeW91cnNl"
    "bGYgKDY0IGhleCBjaGFyYWN0ZXJzKS4iIiIKICAgICAgICBpZiBzZWxmLmRpc2FibGVkOgogICAgICAgICAgICByZXR1cm4gTm9u"
    "ZQogICAgICAgIHRyeToKICAgICAgICAgICAgaCA9IHN0cihoYXNoX2hleCkuc3RyaXAoKS5sb3dlcigpCiAgICAgICAgICAgIGlm"
    "IGxlbihoKSAhPSA2NCBvciBhbnkoY2ggbm90IGluICIwMTIzNDU2Nzg5YWJjZGVmIiBmb3IgY2ggaW4gaCk6CiAgICAgICAgICAg"
    "ICAgICByYWlzZSBWYWx1ZUVycm9yKCJoYXNoIG11c3QgYmUgNjQgaGV4IGNoYXJhY3RlcnMiKQogICAgICAgICAgICBzZWxmLl9l"
    "bnN1cmVfcHJvY2VzcygpCiAgICAgICAgICAgIHdpdGggc2VsZi5fbGs6CiAgICAgICAgICAgICAgICBzZWxmLl9kYi5leGVjdXRl"
    "KCJJTlNFUlQgSU5UTyBlbnRyaWVzKGNpZCxoYXNoLGxhYmVsLGNyZWF0ZWQsZGV2aWNlKSBWQUxVRVMoPyw/LD8sPyw/KSIsCiAg"
    "ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICh1dWlkLnV1aWQ0KCkuaGV4LCBoLCAoc3RyKGxhYmVsKVs6MTIwXSBpZiBs"
    "YWJlbCBlbHNlIE5vbmUpLCB0aW1lLnRpbWUoKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGRldmljZV90b2tl"
    "bihkZXZpY2UpKSkKICAgICAgICAgICAgc2VsZi5fd2FrZS5zZXQoKQogICAgICAgICAgICByZXR1cm4gaAogICAgICAgIGV4Y2Vw"
    "dCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgbG9nLndhcm5pbmcoInNlYmJpX2FkYXB0ZXI6IG5vdCByZWNvcmRlZCAoJXMp"
    "IiwgZSkKICAgICAgICAgICAgcmV0dXJuIE5vbmUKCiAgICAjIC0tIGxvb2t1cHMgLS0KICAgIGRlZiByZWNlaXB0KHNlbGYsIGhh"
    "c2hfaGV4KToKICAgICAgICAiIiJMYXRlc3QgcmVjZWlwdCBmb3IgYSBmaW5nZXJwcmludCAodGhlIG1vc3QgcmVjZW50IGVudHJ5"
    "IHdpdGggdGhhdCBoYXNoKSwgb3IgTm9uZS4iIiIKICAgICAgICBzZWxmLl9lbnN1cmVfcHJvY2VzcygpCiAgICAgICAgd2l0aCBz"
    "ZWxmLl9sazoKICAgICAgICAgICAgcm93ID0gc2VsZi5fZGIuZXhlY3V0ZSgKICAgICAgICAgICAgICAgICJTRUxFQ1Qgci5yZWNl"
    "aXB0LHIudmVyaWZpZWQsci5jaGVja3BvaW50ZWQsci5pbl9jaGFpbixlLmxhYmVsLGUuY3JlYXRlZCBGUk9NIGVudHJpZXMgZSAi"
    "CiAgICAgICAgICAgICAgICAiSk9JTiByZWNlaXB0cyByIE9OIHIuY2lkPWUuY2lkIFdIRVJFIGUuaGFzaD0/IE9SREVSIEJZIGUu"
    "c2VxIERFU0MsIHIuaWQgREVTQyBMSU1JVCAxIiwKICAgICAgICAgICAgICAgIChzdHIoaGFzaF9oZXgpLmxvd2VyKCksKSkuZmV0"
    "Y2hvbmUoKQogICAgICAgIGlmIG5vdCByb3c6CiAgICAgICAgICAgIHJldHVybiBOb25lCiAgICAgICAgcmVjID0ganNvbi5sb2Fk"
    "cyhyb3dbMF0pCiAgICAgICAgcmVjWyJ2ZXJpZmllZF9sb2NhbGx5Il0gPSBib29sKHJvd1sxXSkKICAgICAgICByZWNbImNoZWNr"
    "cG9pbnRlZCJdID0gYm9vbChyb3dbMl0pCiAgICAgICAgcmVjWyJ0cmVlX2hlYWRfc2Vlbl9pbl9jaGFpbiJdID0gTm9uZSBpZiBy"
    "b3dbM10gaXMgTm9uZSBlbHNlIGJvb2wocm93WzNdKQogICAgICAgIHJlY1sibGFiZWwiXSA9IHJvd1s0XQogICAgICAgIHJldHVy"
    "biByZWMKCiAgICBkZWYgY291bnRzKHNlbGYpOgogICAgICAgIHNlbGYuX2Vuc3VyZV9wcm9jZXNzKCkKICAgICAgICB3aXRoIHNl"
    "bGYuX2xrOgogICAgICAgICAgICBjID0gc2VsZi5fZGIKICAgICAgICAgICAgdG90YWwgPSBjLmV4ZWN1dGUoIlNFTEVDVCBDT1VO"
    "VCgqKSBGUk9NIGVudHJpZXMiKS5mZXRjaG9uZSgpWzBdCiAgICAgICAgICAgIHNlbnQgPSBjLmV4ZWN1dGUoIlNFTEVDVCBDT1VO"
    "VChESVNUSU5DVCBjaWQpIEZST00gcmVjZWlwdHMiKS5mZXRjaG9uZSgpWzBdCiAgICAgICAgICAgIGNwID0gYy5leGVjdXRlKCJT"
    "RUxFQ1QgQ09VTlQoRElTVElOQ1QgY2lkKSBGUk9NIHJlY2VpcHRzIFdIRVJFIGNoZWNrcG9pbnRlZD0xIikuZmV0Y2hvbmUoKVsw"
    "XQogICAgICAgICAgICBiYWQgPSBjLmV4ZWN1dGUoIlNFTEVDVCBDT1VOVChESVNUSU5DVCBjaWQpIEZST00gcmVjZWlwdHMgV0hF"
    "UkUgdmVyaWZpZWQ9MCIpLmZldGNob25lKClbMF0KICAgICAgICByZXR1cm4geyJyZWNvcmRlZCI6IHRvdGFsLCAicmVjZWlwdGVk"
    "Ijogc2VudCwgIndhaXRpbmciOiB0b3RhbCAtIHNlbnQsCiAgICAgICAgICAgICAgICAic2VhbGVkX2luX2NoYWluIjogY3AsICJm"
    "YWlsZWRfbG9jYWxfY2hlY2siOiBiYWR9CgogICAgZGVmIHBlbmRpbmcoc2VsZik6CiAgICAgICAgcmV0dXJuIHNlbGYuY291bnRz"
    "KClbIndhaXRpbmciXQoKICAgICMgLS0gbmV0d29yayAtLQogICAgZGVmIF9odHRwKHNlbGYsIG1ldGhvZCwgcGF0aCwgYm9keT1O"
    "b25lKToKICAgICAgICBkYXRhID0ganNvbi5kdW1wcyhib2R5KS5lbmNvZGUoInV0Zi04IikgaWYgYm9keSBpcyBub3QgTm9uZSBl"
    "bHNlIE5vbmUKICAgICAgICByZXEgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KHNlbGYuZW5kcG9pbnQgKyBwYXRoLCBkYXRhPWRh"
    "dGEsIG1ldGhvZD1tZXRob2QpCiAgICAgICAgcmVxLmFkZF9oZWFkZXIoIkNvbnRlbnQtVHlwZSIsICJhcHBsaWNhdGlvbi9qc29u"
    "IikKICAgICAgICByZXEuYWRkX2hlYWRlcigiVXNlci1BZ2VudCIsICJzZWJiaS1hZGFwdGVyLyIgKyBfX3ZlcnNpb25fXykKICAg"
    "ICAgICBpZiBzZWxmLmFwaV9rZXk6CiAgICAgICAgICAgIHJlcS5hZGRfaGVhZGVyKCJYLVNlYmJpLUtleSIsIHNlbGYuYXBpX2tl"
    "eSkKICAgICAgICB0cnk6CiAgICAgICAgICAgIHdpdGggdXJsbGliLnJlcXVlc3QudXJsb3BlbihyZXEsIHRpbWVvdXQ9c2VsZi50"
    "aW1lb3V0KSBhcyByOgogICAgICAgICAgICAgICAgcmV0dXJuIHIuc3RhdHVzLCBqc29uLmxvYWRzKHIucmVhZCgpLmRlY29kZSgi"
    "dXRmLTgiKSBvciAie30iKQogICAgICAgIGV4Y2VwdCB1cmxsaWIuZXJyb3IuSFRUUEVycm9yIGFzIGU6CiAgICAgICAgICAgIHRy"
    "eToKICAgICAgICAgICAgICAgIHJldHVybiBlLmNvZGUsIGpzb24ubG9hZHMoZS5yZWFkKCkuZGVjb2RlKCJ1dGYtOCIpIG9yICJ7"
    "fSIpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICByZXR1cm4gZS5jb2RlLCB7fQoKICAgIGRl"
    "ZiBfY2xhaW0oc2VsZiwgbik6CiAgICAgICAgbm93ID0gdGltZS50aW1lKCkKICAgICAgICB3aXRoIHNlbGYuX2xrOgogICAgICAg"
    "ICAgICBjID0gc2VsZi5fZGIKICAgICAgICAgICAgYy5leGVjdXRlKCJCRUdJTiBJTU1FRElBVEUiKQogICAgICAgICAgICB0cnk6"
    "CiAgICAgICAgICAgICAgICByb3dzID0gYy5leGVjdXRlKAogICAgICAgICAgICAgICAgICAgICJTRUxFQ1QgZS5jaWQsZS5oYXNo"
    "LGUuZGV2aWNlIEZST00gZW50cmllcyBlIFdIRVJFIE5PVCBFWElTVFMgKFNFTEVDVCAxIEZST00gcmVjZWlwdHMgciBXSEVSRSBy"
    "LmNpZD1lLmNpZCkgIgogICAgICAgICAgICAgICAgICAgICJBTkQgTk9UIEVYSVNUUyAoU0VMRUNUIDEgRlJPTSBjbGFpbXMgayBX"
    "SEVSRSBrLmNpZD1lLmNpZCBBTkQgay51bnRpbD4/IEFORCBrLndvcmtlcjw+PykgIgogICAgICAgICAgICAgICAgICAgICJPUkRF"
    "UiBCWSBlLnNlcSBMSU1JVCA/IiwgKG5vdywgc2VsZi5fd2lkLCBuKSkuZmV0Y2hhbGwoKQogICAgICAgICAgICAgICAgZm9yIGNp"
    "ZCwgXywgXyBpbiByb3dzOgogICAgICAgICAgICAgICAgICAgIGMuZXhlY3V0ZSgiSU5TRVJUIE9SIFJFUExBQ0UgSU5UTyBjbGFp"
    "bXMoY2lkLHdvcmtlcix1bnRpbCkgVkFMVUVTKD8sPyw/KSIsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIChjaWQsIHNl"
    "bGYuX3dpZCwgbm93ICsgbWF4KDYwLjAsIHNlbGYudGltZW91dCAqIDMpKSkKICAgICAgICAgICAgICAgIGMuZXhlY3V0ZSgiQ09N"
    "TUlUIikKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIGMuZXhlY3V0ZSgiUk9MTEJBQ0siKQog"
    "ICAgICAgICAgICAgICAgcmFpc2UKICAgICAgICByZXR1cm4gcm93cwoKICAgIGRlZiBfcmVsZWFzZShzZWxmLCBjaWRzKToKICAg"
    "ICAgICB3aXRoIHNlbGYuX2xrOgogICAgICAgICAgICBzZWxmLl9kYi5leGVjdXRlbWFueSgiREVMRVRFIEZST00gY2xhaW1zIFdI"
    "RVJFIGNpZD0/IEFORCB3b3JrZXI9PyIsIFsoYywgc2VsZi5fd2lkKSBmb3IgYyBpbiBjaWRzXSkKCiAgICBkZWYgX3N0b3JlKHNl"
    "bGYsIGNpZCwgcmVjLCBjaGVja3BvaW50ZWQ9RmFsc2UsIGluX2NoYWluPU5vbmUpOgogICAgICAgIG9rID0gdmVyaWZ5X2luY2x1"
    "c2lvbihyZWMuZ2V0KCJlbnRyeV9oYXNoIiwgIiIpLCByZWMuZ2V0KCJsZWFmX2luZGV4IiwgLTEpLCByZWMuZ2V0KCJ0cmVlX3Np"
    "emUiLCAwKSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgcmVjLmdldCgiYXVkaXRfcGF0aCIsIFtdKSwgcmVjLmdldCgi"
    "cm9vdCIsICIiKSkKICAgICAgICBpZiBjaGVja3BvaW50ZWQgYW5kIG9rIGFuZCByZWMuZ2V0KCJjaGVja3BvaW50Iik6CiAgICAg"
    "ICAgICAgIG9rID0gcmVjWyJjaGVja3BvaW50Il0uZ2V0KCJyb290IikgPT0gcmVjLmdldCgicm9vdCIpCiAgICAgICAgaWYgbm90"
    "IG9rOgogICAgICAgICAgICBsb2cuZXJyb3IoInNlYmJpX2FkYXB0ZXI6IHJlY2VpcHQgZm9yIGxlYWYgJXMgRkFJTEVEIHRoZSBs"
    "b2NhbCBpbmNsdXNpb24gY2hlY2sgLSBrZXB0IGFuZCBmbGFnZ2VkIiwKICAgICAgICAgICAgICAgICAgICAgIHJlYy5nZXQoImxl"
    "YWZfaW5kZXgiKSkKICAgICAgICB3aXRoIHNlbGYuX2xrOgogICAgICAgICAgICBzZWxmLl9kYi5leGVjdXRlKCJJTlNFUlQgSU5U"
    "TyByZWNlaXB0cyhjaWQsbGVhZl9pbmRleCxyZWNlaXB0LHZlcmlmaWVkLGNoZWNrcG9pbnRlZCxpbl9jaGFpbixyZWNlaXZlZCkg"
    "IgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICJWQUxVRVMoPyw/LD8sPyw/LD8sPykiLAogICAgICAgICAgICAgICAgICAg"
    "ICAgICAgICAgIChjaWQsIHJlYy5nZXQoImxlYWZfaW5kZXgiKSwganNvbi5kdW1wcyhyZWMsIHNvcnRfa2V5cz1UcnVlKSwgMSBp"
    "ZiBvayBlbHNlIDAsCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIDEgaWYgY2hlY2twb2ludGVkIGVsc2UgMCwgaW5fY2hh"
    "aW4sIHRpbWUudGltZSgpKSkKICAgICAgICByZXR1cm4gb2sKCiAgICBkZWYgX3NlbmRfYmF0Y2goc2VsZik6CiAgICAgICAgIiIi"
    "U2VuZCBvbmUgYmF0Y2guIFJldHVybnMgbnVtYmVyIHJlY2VpcHRlZDsgcmFpc2VzIG9uIG5ldHdvcmsgZmFpbHVyZS4iIiIKICAg"
    "ICAgICBpZiBub3Qgc2VsZi5hcGlfa2V5OgogICAgICAgICAgICBpZiBub3Qgc2VsZi5fd2FybmVkX25vX2tleToKICAgICAgICAg"
    "ICAgICAgIGxvZy53YXJuaW5nKCJzZWJiaV9hZGFwdGVyOiBTRUJCSV9BUElfS0VZIG5vdCBzZXQgLSBmaW5nZXJwcmludHMgYXJl"
    "IHF1ZXVlZCBsb2NhbGx5IGFuZCB3aWxsICIKICAgICAgICAgICAgICAgICAgICAgICAgICAgICJiZSBzZW50IG9uY2UgaXQgaXMi"
    "KQogICAgICAgICAgICAgICAgc2VsZi5fd2FybmVkX25vX2tleSA9IFRydWUKICAgICAgICAgICAgcmV0dXJuIDAKICAgICAgICBy"
    "b3dzID0gc2VsZi5fY2xhaW0oc2VsZi5iYXRjaF9zaXplKQogICAgICAgIGlmIG5vdCByb3dzOgogICAgICAgICAgICByZXR1cm4g"
    "MAogICAgICAgIHdhbnRlZCA9IHtjaWQ6IGggZm9yIGNpZCwgaCwgXyBpbiByb3dzfQogICAgICAgIGl0ZW1zID0gW10KICAgICAg"
    "ICBmb3IgY2lkLCBoLCBkZXYgaW4gcm93czoKICAgICAgICAgICAgaXQgPSB7Imhhc2giOiBoLCAiY2lkIjogY2lkfQogICAgICAg"
    "ICAgICBpZiBkZXY6CiAgICAgICAgICAgICAgICBpdFsiZGV2aWNlIl0gPSBkZXYKICAgICAgICAgICAgaXRlbXMuYXBwZW5kKGl0"
    "KQogICAgICAgIHRyeToKICAgICAgICAgICAgY29kZSwgb3V0ID0gc2VsZi5faHR0cCgiUE9TVCIsICIvcC9zdWJtaXQiLCB7ImRl"
    "dmljZSI6IHNlbGYuZGV2aWNlLCAiaXRlbXMiOiBpdGVtc30pCiAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAg"
    "c2VsZi5fcmVsZWFzZShsaXN0KHdhbnRlZCkpCiAgICAgICAgICAgIHJhaXNlCiAgICAgICAgaWYgY29kZSAhPSAyMDA6CiAgICAg"
    "ICAgICAgIHNlbGYuX3JlbGVhc2UobGlzdCh3YW50ZWQpKQogICAgICAgICAgICBpZiBjb2RlID09IDQwMjoKICAgICAgICAgICAg"
    "ICAgIGxvZy53YXJuaW5nKCJzZWJiaV9hZGFwdGVyOiB5b3VyIGZyZWUgdHJpYWwgaGFzIGVuZGVkIC0gZmluZ2VycHJpbnRzIGFy"
    "ZSBxdWV1ZWQgc2FmZWx5IGFuZCB3aWxsICIKICAgICAgICAgICAgICAgICAgICAgICAgICAgICJzZW5kIG9uY2UgdGhlIGtleSBp"
    "cyBwYWlkOiAlcyIsIG91dC5nZXQoImNoZWNrb3V0X3VybCIsICJodHRwczovL3NlYmJpLnByby9zdGFydCIpKQogICAgICAgICAg"
    "ICByYWlzZSBJT0Vycm9yKCJzZWJiaS5wcm8gYW5zd2VyZWQgJXM6ICVzIiAlIChjb2RlLCBvdXQuZ2V0KCJlcnJvciIpIG9yIG91"
    "dC5nZXQoIm1lc3NhZ2UiKSBvciAiIikpCiAgICAgICAgZG9uZSA9IDAKICAgICAgICBmb3IgcmVjIGluIG91dC5nZXQoInJlY2Vp"
    "cHRzIikgb3IgW106CiAgICAgICAgICAgIGNpZCA9IHJlYy5nZXQoImNpZCIpCiAgICAgICAgICAgIGlmIGNpZCBub3QgaW4gd2Fu"
    "dGVkOgogICAgICAgICAgICAgICAgY29udGludWUKICAgICAgICAgICAgaWYgcmVjLmdldCgiZXJyb3IiKToKICAgICAgICAgICAg"
    "ICAgIGxvZy5lcnJvcigic2ViYmlfYWRhcHRlcjogZW50cnkgJXMgcmVmdXNlZDogJXMiLCBjaWQsIHJlY1siZXJyb3IiXSkKICAg"
    "ICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGlmIHJlYy5nZXQoImVudHJ5X2hhc2giKSAhPSB3YW50ZWRbY2lkXToK"
    "ICAgICAgICAgICAgICAgIGxvZy5lcnJvcigic2ViYmlfYWRhcHRlcjogc2VydmVyIHJldHVybmVkIGEgZGlmZmVyZW50IGhhc2gg"
    "Zm9yICVzIC0gbm90IHN0b3JlZCIsIGNpZCkKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIHNlbGYuX3N0b3Jl"
    "KGNpZCwgcmVjKQogICAgICAgICAgICBkb25lICs9IDEKICAgICAgICBzZWxmLl9yZWxlYXNlKGxpc3Qod2FudGVkKSkKICAgICAg"
    "ICByZXR1cm4gZG9uZQoKICAgIGRlZiBfdXBncmFkZShzZWxmLCBsaW1pdD01MCk6CiAgICAgICAgIiIiRmV0Y2ggc2VhbGVkIHJl"
    "Y2VpcHRzIGZvciBsZWF2ZXMgd2hvc2UgdHJlZSBoZWFkIHNob3VsZCBub3cgYmUgaW4gdGhlIGNoYWluLiIiIgogICAgICAgIGN1"
    "dG9mZiA9IHRpbWUudGltZSgpIC0gMzAKICAgICAgICB3aXRoIHNlbGYuX2xrOgogICAgICAgICAgICByb3dzID0gc2VsZi5fZGIu"
    "ZXhlY3V0ZSgKICAgICAgICAgICAgICAgICJTRUxFQ1Qgci5jaWQsci5sZWFmX2luZGV4IEZST00gcmVjZWlwdHMgciBXSEVSRSBy"
    "LnZlcmlmaWVkPTEgQU5EIHIucmVjZWl2ZWQ8PyBBTkQgIgogICAgICAgICAgICAgICAgIk5PVCBFWElTVFMgKFNFTEVDVCAxIEZS"
    "T00gcmVjZWlwdHMgcjIgV0hFUkUgcjIuY2lkPXIuY2lkIEFORCByMi5jaGVja3BvaW50ZWQ9MSkgIgogICAgICAgICAgICAgICAg"
    "IkdST1VQIEJZIHIuY2lkIE9SREVSIEJZIE1JTihyLmlkKSBMSU1JVCA/IiwgKGN1dG9mZiwgbGltaXQpKS5mZXRjaGFsbCgpCiAg"
    "ICAgICAgYmxvY2tzID0ge30KICAgICAgICBub3cgPSB0aW1lLnRpbWUoKQogICAgICAgIGZvciBjaWQsIGlkeCBpbiByb3dzOgog"
    "ICAgICAgICAgICBpZiBub3cgLSBzZWxmLl90cmllZC5nZXQoY2lkLCAwKSA8IDMwOgogICAgICAgICAgICAgICAgY29udGludWUK"
    "ICAgICAgICAgICAgc2VsZi5fdHJpZWRbY2lkXSA9IG5vdwogICAgICAgICAgICBjb2RlLCByZWMgPSBzZWxmLl9odHRwKCJHRVQi"
    "LCAiL3AvcmVjZWlwdD9sZWFmPSVkIiAlIGlkeCkKICAgICAgICAgICAgaWYgY29kZSAhPSAyMDAgb3Igbm90IHJlYy5nZXQoImNo"
    "ZWNrcG9pbnQiKToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIGluX2NoYWluID0gTm9uZQogICAgICAgICAg"
    "ICBpZiBzZWxmLmNoZWNrX2NoYWluOgogICAgICAgICAgICAgICAgYmxrID0gcmVjWyJjaGVja3BvaW50Il0uZ2V0KCJibG9ja19p"
    "bmRleCIpCiAgICAgICAgICAgICAgICBpZiBibGsgbm90IGluIGJsb2NrczoKICAgICAgICAgICAgICAgICAgICB0cnk6CiAgICAg"
    "ICAgICAgICAgICAgICAgICAgIF8sIGJvZHkgPSBzZWxmLl9odHRwKCJHRVQiLCAiL3gvd2Fsay9ibG9jaz9pbmRleD0lcyIgJSBi"
    "bGspCiAgICAgICAgICAgICAgICAgICAgICAgIGJsb2Nrc1tibGtdID0ganNvbi5kdW1wcyhib2R5KQogICAgICAgICAgICAgICAg"
    "ICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgICAgICAgICAgICAgIGJsb2Nrc1tibGtdID0gTm9uZQogICAgICAgICAg"
    "ICAgICAgaWYgYmxvY2tzW2Jsa10gaXMgbm90IE5vbmU6CiAgICAgICAgICAgICAgICAgICAgaW5fY2hhaW4gPSAxIGlmIHJlY1si"
    "Y2hlY2twb2ludCJdLmdldCgicm9vdCIsICJ+IikgaW4gYmxvY2tzW2Jsa10gZWxzZSAwCiAgICAgICAgICAgICAgICAgICAgaWYg"
    "bm90IGluX2NoYWluOgogICAgICAgICAgICAgICAgICAgICAgICBsb2cuZXJyb3IoInNlYmJpX2FkYXB0ZXI6IHRyZWUgaGVhZCBm"
    "b3IgbGVhZiAlcyBub3QgZm91bmQgaW4gY2hhaW4gYmxvY2sgJXMiLCBpZHgsIGJsaykKICAgICAgICAgICAgc2VsZi5fc3RvcmUo"
    "Y2lkLCByZWMsIGNoZWNrcG9pbnRlZD1UcnVlLCBpbl9jaGFpbj1pbl9jaGFpbikKICAgICAgICAgICAgc2VsZi5fdHJpZWQucG9w"
    "KGNpZCwgTm9uZSkKCiAgICBkZWYgZmx1c2goc2VsZiwgdGltZW91dD0zMC4wKToKICAgICAgICAiIiJTZW5kIGV2ZXJ5dGhpbmcg"
    "d2FpdGluZywgbm93LiBSZXR1cm5zIGhvdyBtYW55IHdlcmUgcmVjZWlwdGVkLiBOZXZlciByYWlzZXMuIiIiCiAgICAgICAgc2Vs"
    "Zi5fZW5zdXJlX3Byb2Nlc3MoKQogICAgICAgIGVuZCwgc2VudCA9IHRpbWUudGltZSgpICsgdGltZW91dCwgMAogICAgICAgIHdo"
    "aWxlIHRpbWUudGltZSgpIDwgZW5kOgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBuID0gc2VsZi5fc2VuZF9iYXRj"
    "aCgpCiAgICAgICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgICAgIGxvZy53YXJuaW5nKCJzZWJiaV9h"
    "ZGFwdGVyOiBmbHVzaCBzdG9wcGVkICglcyk7IGVudHJpZXMgc3RheSBxdWV1ZWQiLCBlKQogICAgICAgICAgICAgICAgYnJlYWsK"
    "ICAgICAgICAgICAgc2VudCArPSBuCiAgICAgICAgICAgIGlmIG4gPT0gMDoKICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAg"
    "cmV0dXJuIHNlbnQKCiAgICBkZWYgX3J1bihzZWxmKToKICAgICAgICB3aGlsZSBub3Qgc2VsZi5fc3RvcC5pc19zZXQoKToKICAg"
    "ICAgICAgICAgc2VsZi5fd2FrZS53YWl0KHNlbGYuX2JhY2tvZmYgb3Igc2VsZi5mbHVzaF9pbnRlcnZhbCkKICAgICAgICAgICAg"
    "c2VsZi5fd2FrZS5jbGVhcigpCiAgICAgICAgICAgIGlmIHNlbGYuX3N0b3AuaXNfc2V0KCk6CiAgICAgICAgICAgICAgICBicmVh"
    "awogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICB3aGlsZSBzZWxmLl9zZW5kX2JhdGNoKCkgPj0gc2VsZi5iYXRjaF9z"
    "aXplOgogICAgICAgICAgICAgICAgICAgIHBhc3MKICAgICAgICAgICAgICAgIHNlbGYuX3VwZ3JhZGUoKQogICAgICAgICAgICAg"
    "ICAgc2VsZi5fYmFja29mZiA9IDAuMAogICAgICAgICAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgICAgICAgICBz"
    "ZWxmLl9iYWNrb2ZmID0gbWluKDMwMC4wLCBtYXgoMi4wLCBzZWxmLl9iYWNrb2ZmICogMikpCiAgICAgICAgICAgICAgICBsb2cu"
    "aW5mbygic2ViYmlfYWRhcHRlcjogc2ViYmkucHJvIHVucmVhY2hhYmxlICglcyk7IHJldHJ5aW5nIGluICVkcyIsIGUsIHNlbGYu"
    "X2JhY2tvZmYpCgogICAgZGVmIGNsb3NlKHNlbGYsIGZsdXNoX3RpbWVvdXQ9Mi4wKToKICAgICAgICB0cnk6CiAgICAgICAgICAg"
    "IGlmIGZsdXNoX3RpbWVvdXQ6CiAgICAgICAgICAgICAgICBzZWxmLmZsdXNoKHRpbWVvdXQ9Zmx1c2hfdGltZW91dCkKICAgICAg"
    "ICBmaW5hbGx5OgogICAgICAgICAgICBzZWxmLl9zdG9wLnNldCgpCiAgICAgICAgICAgIHNlbGYuX3dha2Uuc2V0KCkKCgojIC0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0gdGhlIGRlZmF1bHQg"
    "aW5zdGFuY2UKCl9kZWZhdWx0X2FuY2hvciA9IE5vbmUKX2RlZmF1bHRfbG9jayA9IHRocmVhZGluZy5Mb2NrKCkKCgpkZWYgZ2V0"
    "X2RlZmF1bHQoKToKICAgIGdsb2JhbCBfZGVmYXVsdF9hbmNob3IKICAgIGlmIF9kZWZhdWx0X2FuY2hvciBpcyBOb25lOgogICAg"
    "ICAgIHdpdGggX2RlZmF1bHRfbG9jazoKICAgICAgICAgICAgaWYgX2RlZmF1bHRfYW5jaG9yIGlzIE5vbmU6CiAgICAgICAgICAg"
    "ICAgICBfZGVmYXVsdF9hbmNob3IgPSBBbmNob3IoKQogICAgICAgICAgICAgICAgYXRleGl0LnJlZ2lzdGVyKF9kZWZhdWx0X2Fu"
    "Y2hvci5jbG9zZSkKICAgIHJldHVybiBfZGVmYXVsdF9hbmNob3IKCgpkZWYgcmVjb3JkKHBheWxvYWQsIGxhYmVsPU5vbmUsIGFu"
    "Y2hvcj1Ob25lLCBkZXZpY2U9Tm9uZSk6CiAgICAiIiJGaW5nZXJwcmludCBhbmQgcXVldWUgYW55IEpTT04tYWJsZSB2YWx1ZS4g"
    "UmV0dXJucyB0aGUgaGFzaC4gTmV2ZXIgcmFpc2VzLiIiIgogICAgdHJ5OgogICAgICAgIHJldHVybiAoYW5jaG9yIG9yIGdldF9k"
    "ZWZhdWx0KCkpLnJlY29yZChwYXlsb2FkLCBsYWJlbD1sYWJlbCwgZGV2aWNlPWRldmljZSkKICAgIGV4Y2VwdCBFeGNlcHRpb24g"
    "YXMgZToKICAgICAgICBsb2cud2FybmluZygic2ViYmlfYWRhcHRlcjogbm90IHJlY29yZGVkICglcykiLCBlKQogICAgICAgIHJl"
    "dHVybiBOb25lCgoKZGVmIGFuY2hvcl9zdGF0ZShsYWJlbD1Ob25lLCBjYXB0dXJlPSJyZXN1bHQiLCBleHRyYWN0PU5vbmUsIGFu"
    "Y2hvcj1Ob25lLCBkZXZpY2U9Tm9uZSk6CiAgICAiIiJEZWNvcmF0b3IuIEFmdGVyIHRoZSB3cmFwcGVkIGZ1bmN0aW9uIHN1Y2Nl"
    "ZWRzLCBmaW5nZXJwcmludCBpdHMgc3RhdGUgYW5kIHF1ZXVlIGl0LgoKICAgIGNhcHR1cmU6ICAicmVzdWx0IiAoZGVmYXVsdCkg"
    "LSB0aGUgcmV0dXJuIHZhbHVlCiAgICAgICAgICAgICAgImFyZ3MiICAgICAgICAgICAgIC0gdGhlIGFyZ3VtZW50cyBpdCB3YXMg"
    "Y2FsbGVkIHdpdGgKICAgICAgICAgICAgICAiYm90aCIgICAgICAgICAgICAgLSB7ImFyZ3MiOiAuLi4sICJrd2FyZ3MiOiAuLi4s"
    "ICJyZXN1bHQiOiAuLi59CiAgICBleHRyYWN0OiAgZihyZXN1bHQsIGFyZ3MsIGt3YXJncykgLT4gdGhlIHZhbHVlIHRvIGZpbmdl"
    "cnByaW50IChvdmVycmlkZXMgY2FwdHVyZSkKICAgIGRldmljZTogICB3aGF0IHRoZSBjaGFuZ2UgaXMgYWJvdXQsIGZvciB0aGUg"
    "cGVyLWRldmljZSBtZXRlcjogYSBmaWVsZCBuYW1lIGluIHRoZSByZXN1bHQKICAgICAgICAgICAgICAob3IgYSBrZXl3b3JkIGFy"
    "Z3VtZW50KSwgb3IgZihyZXN1bHQsIGFyZ3MsIGt3YXJncykgLT4gZGV2aWNlIG5hbWUKICAgIFRoZSB3cmFwcGVkIGZ1bmN0aW9u"
    "J3MgYmVoYXZpb3VyLCByZXR1cm4gdmFsdWUgYW5kIGV4Y2VwdGlvbnMgYXJlIHVuY2hhbmdlZC4KICAgICIiIgogICAgaWYgY2Fs"
    "bGFibGUobGFiZWwpIGFuZCBub3QgaXNpbnN0YW5jZShsYWJlbCwgc3RyKToKICAgICAgICByZXR1cm4gYW5jaG9yX3N0YXRlKCko"
    "bGFiZWwpCgogICAgZGVmIGRlY28oZm4pOgogICAgICAgIG5hbWUgPSBsYWJlbCBvciBnZXRhdHRyKGZuLCAiX19xdWFsbmFtZV9f"
    "IiwgZ2V0YXR0cihmbiwgIl9fbmFtZV9fIiwgImNhbGwiKSkKCiAgICAgICAgZGVmIF9zdGF0ZShhcmdzLCBrd2FyZ3MsIHJlc3Vs"
    "dCk6CiAgICAgICAgICAgIGlmIGV4dHJhY3QgaXMgbm90IE5vbmU6CiAgICAgICAgICAgICAgICByZXR1cm4gZXh0cmFjdChyZXN1"
    "bHQsIGFyZ3MsIGt3YXJncykKICAgICAgICAgICAgaWYgY2FwdHVyZSA9PSAiYXJncyI6CiAgICAgICAgICAgICAgICByZXR1cm4g"
    "eyJhcmdzIjogbGlzdChhcmdzKSwgImt3YXJncyI6IGt3YXJnc30KICAgICAgICAgICAgaWYgY2FwdHVyZSA9PSAiYm90aCI6CiAg"
    "ICAgICAgICAgICAgICByZXR1cm4geyJhcmdzIjogbGlzdChhcmdzKSwgImt3YXJncyI6IGt3YXJncywgInJlc3VsdCI6IHJlc3Vs"
    "dH0KICAgICAgICAgICAgcmV0dXJuIHJlc3VsdAoKICAgICAgICBkZWYgX2RldmljZShhcmdzLCBrd2FyZ3MsIHJlc3VsdCk6CiAg"
    "ICAgICAgICAgIGlmIGRldmljZSBpcyBOb25lOgogICAgICAgICAgICAgICAgcmV0dXJuIE5vbmUKICAgICAgICAgICAgaWYgY2Fs"
    "bGFibGUoZGV2aWNlKToKICAgICAgICAgICAgICAgIHJldHVybiBkZXZpY2UocmVzdWx0LCBhcmdzLCBrd2FyZ3MpCiAgICAgICAg"
    "ICAgIGlmIGlzaW5zdGFuY2UocmVzdWx0LCBkaWN0KSBhbmQgZGV2aWNlIGluIHJlc3VsdDoKICAgICAgICAgICAgICAgIHJldHVy"
    "biByZXN1bHRbZGV2aWNlXQogICAgICAgICAgICBpZiBkZXZpY2UgaW4ga3dhcmdzOgogICAgICAgICAgICAgICAgcmV0dXJuIGt3"
    "YXJnc1tkZXZpY2VdCiAgICAgICAgICAgIHJldHVybiBnZXRhdHRyKHJlc3VsdCwgZGV2aWNlLCBOb25lKQoKICAgICAgICBkZWYg"
    "X2FuY2hvcihhcmdzLCBrd2FyZ3MsIHJlc3VsdCk6CiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIHRyeToKICAgICAg"
    "ICAgICAgICAgICAgICBkZXYgPSBfZGV2aWNlKGFyZ3MsIGt3YXJncywgcmVzdWx0KQogICAgICAgICAgICAgICAgZXhjZXB0IEV4"
    "Y2VwdGlvbjoKICAgICAgICAgICAgICAgICAgICBkZXYgPSBOb25lCiAgICAgICAgICAgICAgICByZWNvcmQoX3N0YXRlKGFyZ3Ms"
    "IGt3YXJncywgcmVzdWx0KSwgbGFiZWw9bmFtZSwgYW5jaG9yPWFuY2hvciwgZGV2aWNlPWRldikKICAgICAgICAgICAgZXhjZXB0"
    "IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgICAgICAgICAgbG9nLndhcm5pbmcoInNlYmJpX2FkYXB0ZXI6ICVzIG5vdCByZWNvcmRl"
    "ZCAoJXMpIiwgbmFtZSwgZSkKCiAgICAgICAgaWYgaW5zcGVjdC5pc2Nvcm91dGluZWZ1bmN0aW9uKGZuKToKICAgICAgICAgICAg"
    "QGZ1bmN0b29scy53cmFwcyhmbikKICAgICAgICAgICAgYXN5bmMgZGVmIGF3cmFwcGVyKCphcmdzLCAqKmt3YXJncyk6CiAgICAg"
    "ICAgICAgICAgICByZXN1bHQgPSBhd2FpdCBmbigqYXJncywgKiprd2FyZ3MpCiAgICAgICAgICAgICAgICBfYW5jaG9yKGFyZ3Ms"
    "IGt3YXJncywgcmVzdWx0KQogICAgICAgICAgICAgICAgcmV0dXJuIHJlc3VsdAogICAgICAgICAgICByZXR1cm4gYXdyYXBwZXIK"
    "CiAgICAgICAgQGZ1bmN0b29scy53cmFwcyhmbikKICAgICAgICBkZWYgd3JhcHBlcigqYXJncywgKiprd2FyZ3MpOgogICAgICAg"
    "ICAgICByZXN1bHQgPSBmbigqYXJncywgKiprd2FyZ3MpCiAgICAgICAgICAgIF9hbmNob3IoYXJncywga3dhcmdzLCByZXN1bHQp"
    "CiAgICAgICAgICAgIHJldHVybiByZXN1bHQKICAgICAgICByZXR1cm4gd3JhcHBlcgogICAgcmV0dXJuIGRlY28KCgpjbGFzcyBB"
    "bmNob3JMb2dIYW5kbGVyKGxvZ2dpbmcuSGFuZGxlcik6CiAgICAiIiJGaW5nZXJwcmludHMgZXZlcnkgbG9nIHJlY29yZCBpdCBz"
    "ZWVzOiBsb2dnZXIsIGxldmVsLCBtZXNzYWdlIGFuZCB0aW1lLiIiIgoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCBhbmNob3I9Tm9u"
    "ZSwgbGV2ZWw9bG9nZ2luZy5JTkZPKToKICAgICAgICBsb2dnaW5nLkhhbmRsZXIuX19pbml0X18oc2VsZiwgbGV2ZWwpCiAgICAg"
    "ICAgc2VsZi5fYW5jaG9yID0gYW5jaG9yCgogICAgZGVmIGVtaXQoc2VsZiwgcmVjKToKICAgICAgICBpZiByZWMubmFtZS5zdGFy"
    "dHN3aXRoKCJzZWJiaV9hZGFwdGVyIik6CiAgICAgICAgICAgIHJldHVybgogICAgICAgIHRyeToKICAgICAgICAgICAgcmVjb3Jk"
    "KHsibG9nZ2VyIjogcmVjLm5hbWUsICJsZXZlbCI6IHJlYy5sZXZlbG5hbWUsICJtZXNzYWdlIjogcmVjLmdldE1lc3NhZ2UoKSwK"
    "ICAgICAgICAgICAgICAgICAgICAidGltZSI6IHJvdW5kKHJlYy5jcmVhdGVkLCA2KX0sIGxhYmVsPSJsb2c6IiArIHJlYy5uYW1l"
    "LCBhbmNob3I9c2VsZi5fYW5jaG9yKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBhc3MKCgojIC0tLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0gY29tbWFuZCBsaW5lCgpk"
    "ZWYgX21haW4oYXJndik6CiAgICBsb2dnaW5nLmJhc2ljQ29uZmlnKGxldmVsPWxvZ2dpbmcuSU5GTywgZm9ybWF0PSIlKG1lc3Nh"
    "Z2UpcyIpCiAgICBjbWQgPSBhcmd2WzFdIGlmIGxlbihhcmd2KSA+IDEgZWxzZSAic3RhdHVzIgogICAgaWYgY21kID09ICJoYXNo"
    "IiBhbmQgbGVuKGFyZ3YpID4gMjoKICAgICAgICBwcmludChzdGF0ZV9oYXNoKGpzb24ubG9hZHMoYXJndlsyXSkpKQogICAgICAg"
    "IHJldHVybiAwCiAgICBhID0gQW5jaG9yKHN0YXJ0PUZhbHNlKQogICAgaWYgY21kID09ICJzdGF0dXMiOgogICAgICAgIHByaW50"
    "KGpzb24uZHVtcHMoZGljdChhLmNvdW50cygpLCBlbmRwb2ludD1hLmVuZHBvaW50LCBkYj1hLmRiX3BhdGgsIGRldmljZT1hLmRl"
    "dmljZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAga2V5X3NldD1ib29sKGEuYXBpX2tleSkpLCBpbmRlbnQ9MikpCiAg"
    "ICBlbGlmIGNtZCA9PSAiZmx1c2giOgogICAgICAgIHByaW50KCJyZWNlaXB0ZWQgJWQiICUgYS5mbHVzaCh0aW1lb3V0PTEyMCkp"
    "CiAgICAgICAgYS5fdXBncmFkZShsaW1pdD01MDApCiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyhhLmNvdW50cygpLCBpbmRlbnQ9"
    "MikpCiAgICBlbGlmIGNtZCA9PSAicmVjZWlwdCIgYW5kIGxlbihhcmd2KSA+IDI6CiAgICAgICAgcHJpbnQoanNvbi5kdW1wcyhh"
    "LnJlY2VpcHQoYXJndlsyXSksIGluZGVudD0yKSkKICAgIGVsaWYgY21kID09ICJ2ZXJpZnkiOgogICAgICAgIHdpdGggYS5fbGs6"
    "CiAgICAgICAgICAgIHJvd3MgPSBhLl9kYi5leGVjdXRlKCJTRUxFQ1QgcmVjZWlwdCBGUk9NIHJlY2VpcHRzIikuZmV0Y2hhbGwo"
    "KQogICAgICAgIGdvb2QgPSBzdW0oMSBmb3IgKHIsKSBpbiByb3dzIGlmIChsYW1iZGEgZDogdmVyaWZ5X2luY2x1c2lvbihkLmdl"
    "dCgiZW50cnlfaGFzaCIsICIiKSwgZC5nZXQoImxlYWZfaW5kZXgiLCAtMSksCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "ICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBkLmdldCgidHJlZV9zaXplIiwgMCksIGQuZ2V0KCJhdWRp"
    "dF9wYXRoIiwgW10pLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "ICAgICAgICAgZC5nZXQoInJvb3QiLCAiIikpKShqc29uLmxvYWRzKHIpKSkKICAgICAgICBwcmludCgiJWQgb2YgJWQgc3RvcmVk"
    "IHJlY2VpcHRzIHBhc3MgdGhlIFJGQyA2OTYyIGluY2x1c2lvbiBjaGVjayIgJSAoZ29vZCwgbGVuKHJvd3MpKSkKICAgIGVsc2U6"
    "CiAgICAgICAgcHJpbnQoX19kb2NfXykKICAgIHJldHVybiAwCgoKaWYgX19uYW1lX18gPT0gIl9fbWFpbl9fIjoKICAgIHN5cy5l"
    "eGl0KF9tYWluKHN5cy5hcmd2KSkK"
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    "/plugin": (_d(_PAGE_B64), "text/html; charset=utf-8", None),
    "/p/sebbi_adapter.py": (_d(_ADAPTER_B64), "text/x-python; charset=utf-8", "sebbi_adapter.py"),
}

_ctx = {}
_ready = False
_patched = False
_loaded = False
_leaves = []            # leaf hashes (bytes), index = leaf index
_cache = {}             # (start, size) -> hash, for complete power-of-two subtrees
_tree_lock = threading.Lock()
_cp_lock = threading.Lock()
_loop_started = False


# ---------------------------------------------------------------- RFC 6962

def _h(b):
    return hashlib.sha256(b).digest()


def _leaf_hash(entry):
    return _h(b"\x00" + entry)


def _node(left, right):
    return _h(b"\x01" + left + right)


def _split(n):
    """Largest power of two strictly less than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _mth(start, n):
    """Merkle Tree Hash of leaves[start:start+n]."""
    if n == 0:
        return _h(b"")
    if n == 1:
        return _leaves[start]
    full = n >= 16 and (n & (n - 1)) == 0
    if full:
        hit = _cache.get((start, n))
        if hit is not None:
            return hit
    k = _split(n)
    out = _node(_mth(start, k), _mth(start + k, n - k))
    if full:
        _cache[(start, n)] = out
    return out


def _path(m, start, n):
    """Audit path for leaf m within leaves[start:start+n]."""
    if n <= 1:
        return []
    k = _split(n)
    if m < k:
        return _path(m, start, k) + [_mth(start + k, n - k)]
    return _path(m - k, start + k, n - k) + [_mth(start, k)]


def _subproof(m, start, n, b):
    if m == n:
        return [] if b else [_mth(start, n)]
    k = _split(n)
    if m <= k:
        return _subproof(m, start, k, b) + [_mth(start + k, n - k)]
    return _subproof(m - k, start + k, n - k, False) + [_mth(start, k)]


def _consistency(m, n):
    if m <= 0 or m >= n:
        return []
    return _subproof(m, 0, n, True)


# ---------------------------------------------------------------- storage

def _setup():
    global _ready
    if _ready or "conn" not in _ctx:
        return
    with _ctx["lock"]:
        c = _ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS ppa_leaf(idx INTEGER PRIMARY KEY,entry_hash TEXT NOT NULL,"
                  "leaf_hash TEXT NOT NULL,client TEXT,cid TEXT,ts REAL,UNIQUE(client,cid))")
        c.execute("CREATE INDEX IF NOT EXISTS ppa_leaf_entry ON ppa_leaf(entry_hash)")
        c.execute("CREATE TABLE IF NOT EXISTS ppa_sth(tree_size INTEGER PRIMARY KEY,root TEXT NOT NULL,"
                  "ts REAL,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _reload_locked(c):
    """Rebuild the in-memory tree from the database. Caller holds _ctx['lock']."""
    rows = c.execute("SELECT idx,leaf_hash FROM ppa_leaf ORDER BY idx").fetchall()
    fresh = []
    for i, (idx, lh) in enumerate(rows):
        if idx != i:
            raise RuntimeError("leaf index gap at %d" % i)
        fresh.append(bytes.fromhex(lh))
    _cache.clear()
    _leaves[:] = fresh


def _load():
    global _loaded
    if _loaded:
        return
    with _tree_lock:
        if _loaded:
            return
        with _ctx["lock"]:
            _reload_locked(_ctx["conn"])
        _loaded = True


def _seal(kind, detail, extra):
    ev = {"user_id": "ppa:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "public-proof-adapter", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "adapter_version": VERSION, "detail": detail}
    res.update(extra or {})
    out = _ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _sth_rows(sql, args=()):
    with _ctx["lock"]:
        return _ctx["conn"].execute(sql, args).fetchall()


def _latest_sth():
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth ORDER BY tree_size DESC LIMIT 1")
    return _sth_dict(r[0]) if r else None


def _covering_sth(idx):
    r = _sth_rows("SELECT tree_size,root,ts,audit_hash,block_index FROM ppa_sth WHERE tree_size>? "
                  "ORDER BY tree_size ASC LIMIT 1", (idx,))
    return _sth_dict(r[0]) if r else None


def _sth_dict(r):
    return {"tree_size": r[0], "root": r[1],
            "sealed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[2] or 0)),
            "audit_hash": r[3], "block_index": r[4],
            "walk": SITE + "/x/walk/block?index=%s" % r[4] if r[4] is not None else None,
            "ts": r[2] or 0}


# ---------------------------------------------------------------- appends and checkpoints

def _append(client, items):
    """items: list of (entry_hex, cid or None). Returns list of (idx, entry_hex, replayed, error)."""
    for attempt in range(3):
        out = []
        with _ctx["lock"]:
            c = _ctx["conn"]
            top = c.execute("SELECT COALESCE(MAX(idx),-1) FROM ppa_leaf").fetchone()[0]
            if top + 1 != len(_leaves):
                _reload_locked(c)
            start_len = len(_leaves)
            try:
                for eh, cid in items:
                    if cid:
                        row = c.execute("SELECT idx,entry_hash FROM ppa_leaf WHERE client=? AND cid=?",
                                        (client, cid)).fetchone()
                        if row:
                            if row[1] != eh:
                                out.append((None, eh, False, "cid_reused_for_a_different_hash"))
                            else:
                                out.append((row[0], eh, True, None))
                            continue
                    idx = len(_leaves)
                    lh = _leaf_hash(bytes.fromhex(eh))
                    c.execute("INSERT INTO ppa_leaf(idx,entry_hash,leaf_hash,client,cid,ts) VALUES(?,?,?,?,?,?)",
                              (idx, eh, lh.hex(), client, cid or None, time.time()))
                    _leaves.append(lh)
                    out.append((idx, eh, False, None))
                c.commit()
                return out
            except sqlite3.IntegrityError:
                c.rollback()
                del _leaves[start_len:]
                _reload_locked(c)
            except Exception:
                c.rollback()
                del _leaves[start_len:]
                raise
    raise RuntimeError("could not append after retries")


def _checkpoint(force=False):
    """Seal the current tree head into the chain if it is due. Never runs twice at once."""
    if "conn" not in _ctx or not _cp_lock.acquire(blocking=False):
        return None
    try:
        _load()
        n = len(_leaves)
        last = _latest_sth()
        last_size = last["tree_size"] if last else 0
        if n == 0 or n == last_size:
            return last
        due = force or (n - last_size) >= CHECKPOINT_EVERY or \
            (time.time() - (last["ts"] if last else 0)) >= CHECKPOINT_SECONDS
        if not due:
            return last
        root = _mth(0, n).hex()
        ah, blk = _seal("tree_head", "size=%d;root=%s" % (n, root),
                        {"tree_size": n, "root": root, "prev_tree_size": last_size,
                         "log": "sebbi public proof log", "spec": "RFC6962-SHA256"})
        with _ctx["lock"]:
            _ctx["conn"].execute("INSERT OR IGNORE INTO ppa_sth(tree_size,root,ts,audit_hash,block_index) "
                                 "VALUES(?,?,?,?,?)", (n, root, time.time(), ah, blk))
            _ctx["conn"].commit()
        return _latest_sth()
    finally:
        _cp_lock.release()


def _loop():
    while True:
        time.sleep(10)
        try:
            _checkpoint()
        except Exception as e:
            print("public_proof_adapter checkpoint: " + str(e)[:160], flush=True)


def _start_loop():
    global _loop_started
    if _loop_started:
        return
    _loop_started = True
    threading.Thread(target=_loop, name="ppa-checkpoint", daemon=True).start()


# ---------------------------------------------------------------- receipts

def _anchoring_note(cp):
    if not cp:
        return ("pending: this leaf is covered by the next tree head, sealed into the chain within about "
                "%d seconds. Fetch /p/receipt?leaf=N again after that." % CHECKPOINT_SECONDS)
    return ("tree head sealed in chain block %s. The chain tip is timestamped in Bitcoin via OpenTimestamps; "
            "once a confirmed anchored tip is at or after that block, this leaf is Bitcoin-anchored. "
            "Check: %s/x/ots/latest_confirmed" % (cp["block_index"], SITE))


def _receipt(idx, size=None):
    _load()
    n = len(_leaves)
    if idx < 0 or idx >= n:
        return None
    with _ctx["lock"]:
        row = _ctx["conn"].execute("SELECT entry_hash FROM ppa_leaf WHERE idx=?", (idx,)).fetchone()
    cp = _covering_sth(idx) if size is None else None
    tsize = size if size is not None else (cp["tree_size"] if cp else n)
    tsize = max(idx + 1, min(tsize, n))
    root = _mth(0, tsize).hex()
    rec = {"log": "sebbi.pro public proof log", "spec": SPEC,
           "entry_hash": row[0] if row else None, "leaf_index": idx,
           "leaf_hash": _leaves[idx].hex(), "tree_size": tsize, "root": root,
           "audit_path": [p.hex() for p in _path(idx, 0, tsize)],
           "checkpoint": None, "anchoring": _anchoring_note(cp)}
    if cp:
        c2 = dict(cp)
        c2.pop("ts", None)
        c2["root_matches"] = (cp["root"] == root)
        rec["checkpoint"] = c2
    return rec


# ---------------------------------------------------------------- commands

def _meter(key, devices):
    """Count each distinct device on the key's monthly meter - the engine's own record_device()."""
    key = str(key or "").strip()
    devices = [d for d in dict.fromkeys(devices) if d and CID_RE.match(d)]
    if not key or not devices:
        return None
    rd = _server_fn("record_device")
    n = None
    for d in devices:
        dev_id = "adapter:" + d
        if rd:
            try:
                n = rd(key, dev_id)
                continue
            except Exception:
                pass
        try:
            with _ctx["lock"]:
                c = _ctx["conn"]
                c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                          (key, dev_id, time.time()))
                c.commit()
                n = c.execute("SELECT COUNT(*) FROM device_seen WHERE api_key=?", (key,)).fetchone()[0]
        except Exception:
            try:
                _ctx["conn"].rollback()
            except Exception:
                pass
    return n


TRIAL_DAYS = 90


def _server_fn(name):
    """Borrow a function from the running server (server.py) if it is there."""
    for modname in ("__main__", "server"):
        m = sys.modules.get(modname)
        fn = getattr(m, name, None) if m else None
        if callable(fn):
            return fn
    return None


def _trial_gate(key):
    """None if the key may submit; otherwise the same 402 answer the engine gives at trial end."""
    try:
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT email,is_paid,created,product FROM api_keys WHERE key=?",
                                       (key,)).fetchone()
    except Exception:
        return None
    if not row:
        return None
    email, is_paid, created, product = row
    ts = _server_fn("trial_state")
    in_trial = ts(created, is_paid)[0] if ts else (bool(is_paid) or time.time() - (created or 0) <= TRIAL_DAYS * 86400)
    if in_trial:
        return None
    dc = _server_fn("device_count")
    tc = _server_fn("trial_checkout")
    try:
        devices = dc(key) if dc else None
    except Exception:
        devices = None
    try:
        url = tc(key, email, product or "aileash") if tc else SITE + "/#signup"
    except Exception:
        url = SITE + "/#signup"
    return {"error": "trial_expired",
            "message": "Your 90-day free trial has ended. Your receipts, proofs and queued fingerprints are "
                       "untouched - pay to continue exactly where you left off. The bill is 50p for each real "
                       "device that used your key.",
            "billable_devices": devices, "rate_per_device_gbp": 0.50, "checkout_url": url}


def _client_for(key):
    key = str(key or "").strip()
    if key:
        try:
            with _ctx["lock"]:
                row = _ctx["conn"].execute("SELECT active FROM api_keys WHERE key=?", (key,)).fetchone()
        except Exception:
            row = None
        if row and row[0] in (1, None):
            return "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return "open" if OPEN else None


# ---------------------------------------------------------------- sign-up, account, payment

_signups = {}
_signup_lock = threading.Lock()
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


def _esc(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _welcome_html(name, key, trial_ends):
    k = _esc(key)
    return ("<div style='font-family:Arial,sans-serif;max-width:560px;color:#1f2937'>"
            "<h2 style='color:#0b1220'>Your sebbi.pro plug-in key</h2>"
            "<p>Hi " + _esc(name or "there") + ", your key is below. Keep it private.</p>"
            "<p style='font-family:monospace;font-size:15px;background:#f1f5f9;padding:12px;border-radius:8px;"
            "word-break:break-all'>" + k + "</p>"
            "<h3>Plug it in</h3><ol>"
            "<li>Download the adapter: <a href='" + SITE + "/p/sebbi_adapter.py'>" + SITE + "/p/sebbi_adapter.py</a></li>"
            "<li>Set <code>SEBBI_API_KEY=" + k + "</code></li>"
            "<li>Add <code>@anchor_state(\"orders.update\", device=\"handset\")</code> above any function "
            "that changes something important.</li></ol>"
            "<p>Other languages, your account and your bill: <a href='" + SITE + "/plugin'>" + SITE + "/plugin</a></p>"
            "<p><b>Free until " + _esc(trial_ends) + "</b>, then 50p per device per month - every phone, till "
            "or machine you record for, counted once a month.</p>"
            "<p style='color:#64748b;font-size:13px'>Questions: justrightdecorators@gmail.com</p></div>")


def _send_mail(to, name, subject, html):
    fn = _server_fn("send_email")
    if fn:
        threading.Thread(target=fn, args=(to, name or "", subject, html), daemon=True).start()
        return True
    return False


def _trial_end(created):
    return time.strftime("%d %B %Y", time.gmtime((created or time.time()) + TRIAL_DAYS * 86400))


def c_signup(q, body, key, ip=""):
    email = str(body.get("email") or "").strip().lower()
    name = str(body.get("name") or "").strip()[:80]
    org = str(body.get("org") or "").strip()[:120]
    if not EMAIL_RE.match(email):
        return {"error": "invalid_email", "message": "Please enter a valid email address."}, 400
    now = time.time()
    with _signup_lock:
        hits = [t for t in _signups.get(ip, []) if now - t < 3600]
        if len(hits) >= 5:
            return {"error": "slow_down", "message": "Too many sign-ups from here. Try again in an hour."}, 429
        hits.append(now)
        _signups[ip] = hits
    create = _server_fn("create_key")
    if not create:
        return {"error": "unavailable", "message": "Sign-up isn't available just now."}, 503
    new_key, err = create(email, "", name, org, "plugin", "aileash", 1)
    if err == "email_exists":
        with _ctx["lock"]:
            row = _ctx["conn"].execute("SELECT key,name,created FROM api_keys WHERE email=? AND product='aileash'",
                                       (email,)).fetchone()
        if row:
            _send_mail(email, row[1] or name, "Your sebbi.pro key", _welcome_html(row[1] or name, row[0], _trial_end(row[2])))
        return {"error": "email_exists",
                "message": "That email already has a sebbi.pro key. We've emailed it to you - the same key works here."}, 409
    if err or not new_key:
        return {"error": err or "failed", "message": "Couldn't create a key just now."}, 400
    ends = _trial_end(now)
    _send_mail(email, name, "Your sebbi.pro plug-in key", _welcome_html(name, new_key, ends))
    _send_mail("justrightdecorators@gmail.com", "sebbi.pro", "New plug-in sign-up: " + (org or email),
               "<p>New plug-in customer: " + _esc(name) + " &middot; " + _esc(email) + " &middot; " + _esc(org) + "</p>")
    return {"key": new_key, "trial_ends": ends, "rate_per_device_gbp": 0.50}, 200


def _key_row(key):
    key = str(key or "").strip()
    if not key:
        return None
    try:
        with _ctx["lock"]:
            return _ctx["conn"].execute("SELECT email,is_paid,created,product,stripe_customer,active FROM api_keys "
                                        "WHERE key=?", (key,)).fetchone()
    except Exception:
        return None


def _devices_this_month(key):
    m = sys.modules.get("modules.meter") or sys.modules.get("meter")
    if m is not None and hasattr(m, "month_count"):
        try:
            return m.month_count(key)
        except Exception:
            pass
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else 0
    except Exception:
        return 0


def _billable(key):
    dc = _server_fn("device_count")
    try:
        return dc(key) if dc else _devices_this_month(key)
    except Exception:
        return _devices_this_month(key)


def c_account(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    ts = _server_fn("trial_state")
    in_trial, left = ts(created, is_paid) if ts else (time.time() - (created or 0) <= TRIAL_DAYS * 86400,
                                                       max(0, TRIAL_DAYS - int((time.time() - (created or 0)) // 86400)))
    billable = _billable(key)
    client = "k_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    rows = _sth_rows("SELECT COUNT(*) FROM ppa_leaf WHERE client=?", (client,))
    return {"email_hint": (email[:2] + "***" + email[email.find("@"):]) if email and "@" in email else "",
            "paid": bool(is_paid), "in_trial": bool(in_trial) and not is_paid,
            "trial_days_left": None if is_paid else left, "trial_ends": _trial_end(created),
            "devices_this_month": _devices_this_month(key), "billable_devices": billable,
            "monthly_bill_gbp": round(billable * 0.50, 2), "rate_per_device_gbp": 0.50,
            "records_logged": rows[0][0] if rows else 0, "active": bool(active)}, 200


def c_pay(q, body, key):
    key = str(body.get("key") or key or "").strip()
    row = _key_row(key)
    if not row:
        return {"error": "bad_key", "message": "That key wasn't recognised."}, 404
    email, is_paid, created, product, cust, active = row
    if is_paid and cust:
        call = _server_fn("stripe_call")
        r = call("POST", "/billing_portal/sessions", {"customer": cust, "return_url": SITE + "/plugin#account"}) if call else None
        if r and r.get("url"):
            return {"url": r["url"]}, 200
        return {"error": "portal_unavailable", "message": "Your account is paid. To change billing, email "
                                                         "justrightdecorators@gmail.com."}, 200
    tc = _server_fn("trial_checkout")
    if not tc:
        return {"error": "unavailable", "message": "Payments aren't available just now."}, 503
    try:
        url = tc(key, email, product or "aileash")
    except Exception:
        url = None
    if not url or "stripe.com" not in url:
        return {"error": "unavailable", "message": "Payments aren't available just now - try again shortly."}, 503
    return {"url": url}, 200


def c_submit(q, body, key):
    client = _client_for(key)
    if not client:
        return {"error": "api_key_required",
                "message": "Send your sebbi.pro API key in the X-Sebbi-Key header."}, 401
    if client != "open":
        gate = _trial_gate(str(key).strip())
        if gate:
            return gate, 402
    raw = body.get("items")
    if raw is None and body.get("hashes") is not None:
        raw = [{"hash": h} for h in body.get("hashes") or []]
    if raw is None and body.get("hash") is not None:
        raw = [{"hash": body.get("hash"), "cid": body.get("cid")}]
    if not isinstance(raw, list) or not raw:
        return {"error": "nothing_to_submit", "message": 'Send {"items":[{"hash":"<64 hex>","cid":"..."}]}'}, 400
    if len(raw) > MAX_ITEMS:
        return {"error": "too_many", "max_items": MAX_ITEMS}, 413
    items, bad, devs = [], [], []
    install = str(body.get("device") or "").strip()
    for i, it in enumerate(raw):
        it = it if isinstance(it, dict) else {"hash": it}
        h = str(it.get("hash") or "").strip().lower()
        cid = str(it.get("cid") or "").strip() or None
        dev = str(it.get("device") or "").strip() or install
        if not HEX64.match(h):
            bad.append({"position": i, "error": "hash must be 64 hex characters (SHA-256)"})
        elif cid and not CID_RE.match(cid):
            bad.append({"position": i, "error": "cid must be 1-80 letters, numbers, _ . : -"})
        elif dev and not CID_RE.match(dev):
            bad.append({"position": i, "error": "device must be 1-80 letters, numbers, _ . : -"})
        else:
            items.append((h, cid))
            devs.append(dev)
    if bad:
        return {"error": "bad_items", "items": bad}, 400
    _load()
    devices = _meter(key, devs) if client != "open" else None
    placed = _append(client, items)
    n = len(_leaves)
    last = _latest_sth()
    if n - (last["tree_size"] if last else 0) >= CHECKPOINT_EVERY:
        threading.Thread(target=_checkpoint, daemon=True).start()
    receipts = []
    for (idx, eh, replayed, err), (_, cid) in zip(placed, items):
        if err:
            receipts.append({"cid": cid, "entry_hash": eh, "error": err})
            continue
        r = _receipt(idx, size=n)
        r["cid"] = cid
        r["replayed"] = replayed
        r["anchoring"] = _anchoring_note(None)
        receipts.append(r)
    return {"accepted": sum(1 for r in receipts if "error" not in r), "tree_size": n,
            "devices_this_month": devices,
            "root": _mth(0, n).hex(), "receipts": receipts}, 200


def _int(q, name, default=None):
    try:
        return int(str(q.get(name, default)))
    except (TypeError, ValueError):
        return None


def c_receipt(q, body, key):
    idx = _int(q, "leaf")
    if idx is None:
        return {"error": "leaf needed"}, 400
    r = _receipt(idx)
    return (r, 200) if r else ({"error": "no such leaf"}, 404)


def c_proof(q, body, key):
    idx, size =
