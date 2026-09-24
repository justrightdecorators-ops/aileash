# Codebase — part 8 of 41

Contains:
- `modules/dsr.py`
- `modules/earnpage.py`
- `modules/fingerprint.py`


## `modules/dsr.py`

239 lines, 10666 bytes

```python
"""
DSR notary - /x/dsr/<action>

Seals the lifecycle of a data subject request into the MAIN audit chain:
received, assessed, extended, completed. Each is an ordinary block in
audit_log, so /api/verify-chain and the anchor cover them automatically.

The chain never holds the person's identity. The identifier is HMAC'd on
arrival and only the fingerprint is stored - so personal data is deleted in
your own systems as normal, and what remains is a seal resolving to nothing.

Needs DSR_SECRET set in Railway (falls back to LICENCE_SECRET).
Never change it once live - existing fingerprints become unresolvable.

    POST /x/dsr/receive    subject_identifier, kind, channel, note
    POST /x/dsr/assess     request_id, outcome, ground, reasoning, assessed_by
    POST /x/dsr/extend     request_id, reason
    POST /x/dsr/complete   request_id, action_taken, responded_by
    GET  /x/dsr/request?id=DSR-XXXXXXXX
    GET  /x/dsr/overdue
    GET  /x/dsr/list
"""

import hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone

KINDS = {"erasure", "access", "rectification", "objection", "portability", "restriction"}
OUTCOMES = {"granted", "refused", "partial"}
VERSION = "1.0"

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute("CREATE TABLE IF NOT EXISTS dsr_requests(request_id TEXT PRIMARY KEY,api_key TEXT,subject_fp TEXT,kind TEXT,received REAL,deadline REAL,extended INTEGER DEFAULT 0,status TEXT DEFAULT 'open',closed REAL,seal TEXT,block_index INTEGER)")
        ctx["conn"].execute("CREATE INDEX IF NOT EXISTS idx_dsr_key ON dsr_requests(api_key)")
        ctx["conn"].commit()
    _ready = True


def _secret():
    s = os.environ.get("DSR_SECRET", "").strip() or os.environ.get("LICENCE_SECRET", "").strip()
    return s.encode() if s else None


def fingerprint(ident):
    s = _secret()
    if not s:
        return None
    return hmac.new(s, str(ident).strip().lower().encode(), hashlib.sha256).hexdigest()


def _add_months(ts, n):
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    mi = dt.month - 1 + n
    y = dt.year + mi // 12
    m = mi % 12 + 1
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.replace(year=y, month=m, day=min(dt.day, dim)).timestamp()


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _seal_event(ctx, api_key, rid, fp, action, detail):
    ts = time.time()
    ev = {"user_id": "dsr:" + rid, "action": "dsr_" + action, "amount": 0,
          "country": "UK", "device_id": "dsr", "anomaly": 0, "device_risk": 0,
          "subject_fp": fp}
    res = {"decision": "DSR_SEALED", "score": 0, "dsr_action": action,
           "dsr_version": VERSION, "timestamp": ts, "detail": detail,
           "note": "data subject request lifecycle event - no personal data in this block"}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)
    return h, idx, seq, ts


def _lookup(ctx, api_key, rid):
    with ctx["lock"]:
        return ctx["conn"].execute("SELECT subject_fp,kind,received,deadline,extended,status,closed FROM dsr_requests WHERE request_id=? AND api_key=?", (rid, api_key)).fetchone()


def _receive(ctx, api_key, data):
    if not _secret():
        return {"error": "dsr_secret_not_set", "message": "Set DSR_SECRET in Railway."}, 503
    ident = str(data.get("subject_identifier", "")).strip()
    if not ident:
        return {"error": "subject_identifier_required"}, 400
    kind = str(data.get("kind", "erasure")).strip().lower()
    if kind not in KINDS:
        return {"error": "invalid_kind", "allowed": sorted(KINDS)}, 400
    fp = fingerprint(ident)
    rid = "DSR-" + secrets.token_hex(4).upper()
    ts = time.time()
    deadline = _add_months(ts, 1)
    detail = "kind=" + kind + ";channel=" + str(data.get("channel", ""))[:60] + ";note=" + str(data.get("note", ""))[:200]
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, fp, "received", detail)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO dsr_requests(request_id,api_key,subject_fp,kind,received,deadline,extended,status,closed,seal,block_index) VALUES(?,?,?,?,?,?,0,'open',NULL,?,?)",
                            (rid, api_key, fp, kind, ts, deadline, h, idx))
        ctx["conn"].commit()
    return {"request_id": rid, "kind": kind, "subject_fp": fp[:16] + "...",
            "received": _iso(ts), "respond_by": _iso(deadline),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq,
            "message": "Clock started. One calendar month to respond."}, 200


def _assess(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    outcome = str(data.get("outcome", "")).strip().lower()
    if outcome not in OUTCOMES:
        return {"error": "invalid_outcome", "allowed": sorted(OUTCOMES)}, 400
    reasoning = str(data.get("reasoning", "")).strip()
    if not reasoning:
        return {"error": "reasoning_required", "message": "The reasoning is the part examined later. It cannot be blank."}, 400
    detail = ("outcome=" + outcome + ";ground=" + str(data.get("ground", ""))[:120] +
              ";by=" + str(data.get("assessed_by", ""))[:60] + ";reasoning=" + reasoning[:600])
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "assessed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status=? WHERE request_id=? AND api_key=?", ("assessed:" + outcome, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "outcome": outcome, "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _extend(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    if row[4]:
        return {"error": "already_extended", "message": "A request can be extended once."}, 400
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return {"error": "reason_required", "message": "An extension needs a stated reason."}, 400
    old = row[3]
    new = _add_months(old, 2)
    detail = "old_deadline=" + str(_iso(old)) + ";new_deadline=" + str(_iso(new)) + ";reason=" + reason[:300]
    h, idx, seq, ts = _seal_event(ctx, api_key, rid, row[0], "extended", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET deadline=?,extended=1 WHERE request_id=? AND api_key=?", (new, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "was_due": _iso(old), "respond_by": _iso(new),
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _complete(ctx, api_key, data):
    rid = str(data.get("request_id", "")).strip()
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    action = str(data.get("action_taken", "")).strip()
    if not action:
        return {"error": "action_taken_required"}, 400
    ts = time.time()
    in_time = ts <= row[3]
    detail = ("action=" + action[:400] + ";by=" + str(data.get("responded_by", ""))[:60] +
              ";within_deadline=" + ("yes" if in_time else "no"))
    h, idx, seq, _x = _seal_event(ctx, api_key, rid, row[0], "completed", detail)
    with ctx["lock"]:
        ctx["conn"].execute("UPDATE dsr_requests SET status='closed',closed=? WHERE request_id=? AND api_key=?", (ts, rid, api_key))
        ctx["conn"].commit()
    return {"request_id": rid, "closed": _iso(ts), "within_deadline": in_time,
            "audit_hash": h, "block_index": idx, "receipt_seq": seq}, 200


def _timeline(ctx, api_key, rid):
    row = _lookup(ctx, api_key, rid)
    if not row:
        return {"error": "unknown_request_id"}, 404
    with ctx["lock"]:
        blocks = ctx["conn"].execute("SELECT ts,result_json,audit_hash,key_seq FROM audit_log WHERE user_id=? ORDER BY id ASC", ("dsr:" + rid,)).fetchall()
    events = []
    for ts_, res, ah, seq in blocks:
        try:
            r = json.loads(res)
            events.append({"at": _iso(ts_), "event": r.get("dsr_action"),
                           "detail": r.get("detail"), "sealed": ah, "receipt_seq": seq})
        except Exception:
            pass
    return {"request_id": rid, "kind": row[1], "received": _iso(row[2]),
            "respond_by": _iso(row[3]), "extended": bool(row[4]),
            "status": row[5], "closed": _iso(row[6]), "events": events,
            "verify": "/api/verify-chain re-checks these with the rest of the chain"}, 200


def _overdue(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline FROM dsr_requests WHERE api_key=? AND status!='closed' AND deadline<? ORDER BY deadline ASC", (api_key, t)).fetchall()
    return {"count": len(rows),
            "overdue": [{"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                         "was_due": _iso(r[3]), "days_late": round((t - r[3]) / 86400, 1)} for r in rows]}, 200


def _list(ctx, api_key):
    t = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute("SELECT request_id,kind,received,deadline,status,extended FROM dsr_requests WHERE api_key=? ORDER BY received DESC LIMIT 200", (api_key,)).fetchall()
    out = []
    for r in rows:
        out.append({"request_id": r[0], "kind": r[1], "received": _iso(r[2]),
                    "respond_by": _iso(r[3]), "status": r[4], "extended": bool(r[5]),
                    "days_remaining": (round((r[3] - t) / 86400, 1) if r[4] != "closed" else None)})
    return {"count": len(out), "requests": out}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    if method == "POST":
        if action == "receive":
            return _receive(ctx, api_key, data)
        if action == "assess":
            return _assess(ctx, api_key, data)
        if action == "extend":
            return _extend(ctx, api_key, data)
        if action == "complete":
            return _complete(ctx, api_key, data)
    else:
        if action == "overdue":
            return _overdue(ctx, api_key)
        if action == "list":
            return _list(ctx, api_key)
        if action == "request":
            rid = str(data.get("id", "")).strip()
            if not rid:
                return {"error": "id_required"}, 400
            return _timeline(ctx, api_key, rid)
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/earnpage.py`

293 lines, 21176 bytes

```python
"""
modules/earnpage.py  v1.0.1
The creator's withdrawal page at /earn, plus a "My earnings" button on the
homepage.

  /earn   claim a creator name (get a private key), see earnings and paid
          unlocks, link a bank through Stripe, withdraw to it, and see every
          past withdrawal with its proof in the chain.

Talks to modules/credits.py (v1.2.0 or later) over /c/creator/.

1.0.1: no longer touches the homepage at all. The homepage belongs to
index.html and homelink.py; the My earnings button goes in homelink.py.

Page module, same family as creditspage.py: a runtime do_GET patch.
Armed by /x/earnpage/status after each deploy.
"""

import base64
import io
import re
import sys

VERSION = "1.0.1"

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
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._earnpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({"module": "earnpage", "version": VERSION, "armed": armed,
             "serves": sorted(_FILES.keys()), "homepage_button": False}, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```


## `modules/fingerprint.py`

550 lines, 22358 bytes

```python
"""
modules/fingerprint.py  -  is somebody else running my scoring function?

THE IDEA
--------
The scoring engine is deterministic. Identical inputs give an identical score,
every time, forever. That is a compliance property - and it is also a
signature.

So: fire a fixed battery of carefully chosen inputs at any scoring endpoint,
fire the same battery at our own, and compare the two sets of numbers.

  identical across 24 varied vectors        it is this function
  identical shape, different scale          it is this function, reweighted
  same ordering, different curve            similar design, not this code
  unrelated                                 unrelated

WHY THE VECTORS ARE CHOSEN THE WAY THEY ARE
-------------------------------------------
Random inputs would only catch a straight copy. These are picked to probe the
specific design decisions in the function, because those are what survive
someone renaming things or nudging a weight:

  saturation points   velocity terms saturate at different counts per window,
                      so a burst and a grind separate. Vectors sit either side
                      of each saturation point.
  curve shape         amount is log-scaled, so small sums move the score far
                      more than large ones. Vectors walk that curve.
  normalisation       the continuous weights sum to 1.00 and the boolean
                      geography terms sit outside it. Vectors isolate that.
  asymmetry           trust contributes inversely and dominates. Vectors sweep
                      trust alone with everything else held flat.

A copy that renamed every field and changed nothing else matches exactly. A
copy that shifted the weights still tracks the shape, because the saturation
points and the log curve are structural rather than parametric.

WHAT IT CANNOT DO
-----------------
It only sees endpoints it can reach. A private product behind a key with no
free tier is invisible to this, and no amount of cleverness changes that.

It also proves similarity, never theft. Two people can converge on similar
weights honestly. What this produces is a dated, sealed measurement - which is
evidence, not a verdict, and the distinction matters if it is ever put in
front of anyone.

EVERY RUN IS SEALED
-------------------
The probe, the target, the vectors and the result all go into the chain. So a
comparison run today is provable as having been run today, rather than
assembled afterwards to fit an argument.

ROUTES  (all keyed - this is not a public toy)
----------------------------------------------
  POST /x/fingerprint/self      score the battery on our own engine
  POST /x/fingerprint/probe     url, plus optional field mapping. Compare.
  GET  /x/fingerprint/history   previous probes and their verdicts
  GET  /x/fingerprint/vectors   the battery itself
  GET  /x/fingerprint/spec      what a verdict means and does not mean
"""

import ipaddress
import json
import math
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = set()          # nothing public. deliberately.

FETCH_TIMEOUT = 10
MAX_BYTES = 200000
POLITE_DELAY = 0.4      # do not hammer somebody else's server
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = (80, 443)

# Where the live scorer might be found. Same approach as replay.py - look it
# up at runtime, never import server.py.
SCORER_NAMES = ["score_event", "score", "_score_event"]

_ready = False


# ----------------------------------------------------------------------
# the battery
# ----------------------------------------------------------------------
# Each vector is (label, signals). Signals use the engine's own internal
# names; the probe maps them to whatever the target calls things.

def _v(trust=0.5, v60=0, v5m=0, v1h=0, amount=0.0,
       device_risk=0.0, anomaly=0.0, country_shift=False, unsafe_country=False):
    return {"trust": trust, "v60": v60, "v5m": v5m, "v1h": v1h,
            "amount": amount, "device_risk": device_risk, "anomaly": anomaly,
            "country_shift": country_shift, "unsafe_country": unsafe_country}


VECTORS = [
    # --- trust sweep, everything else flat. Isolates the dominant term.
    ("trust-000", _v(trust=0.00)),
    ("trust-025", _v(trust=0.25)),
    ("trust-050", _v(trust=0.50)),
    ("trust-075", _v(trust=0.75)),
    ("trust-100", _v(trust=1.00)),

    # --- velocity: either side of each window's saturation point.
    ("v60-under",   _v(v60=10)),
    ("v60-at",      _v(v60=20)),
    ("v60-over",    _v(v60=40)),      # saturated: must equal v60-at
    ("v5m-under",   _v(v5m=25)),
    ("v5m-at",      _v(v5m=50)),
    ("v5m-over",    _v(v5m=100)),     # saturated
    ("v1h-under",   _v(v1h=100)),
    ("v1h-at",      _v(v1h=200)),
    ("v1h-over",    _v(v1h=400)),     # saturated

    # --- burst vs grind: same total actions, different distribution.
    ("burst",       _v(v60=20, v5m=20, v1h=20)),
    ("grind",       _v(v60=1,  v5m=8,  v1h=200)),

    # --- amount: walks the log curve. Small steps low, big steps high.
    ("amt-10",      _v(amount=10.0)),
    ("amt-100",     _v(amount=100.0)),
    ("amt-1000",    _v(amount=1000.0)),
    ("amt-10000",   _v(amount=10000.0)),
    ("amt-50000",   _v(amount=50000.0)),   # saturated

    # --- the boolean geography terms, isolated.
    ("geo-shift",   _v(country_shift=True)),
    ("geo-unsafe",  _v(unsafe_country=True)),
    ("geo-both",    _v(country_shift=True, unsafe_country=True)),

    # --- the other two continuous signals.
    ("dev-risk",    _v(device_risk=1.0)),
    ("anomaly",     _v(anomaly=1.0)),

    # --- everything at once. Tests the clamp and the normalisation.
    ("max-all",     _v(trust=0.0, v60=40, v5m=100, v1h=400, amount=50000.0,
                       device_risk=1.0, anomaly=1.0,
                       country_shift=True, unsafe_country=True)),
    ("min-all",     _v(trust=1.0)),
]

# Default mapping from our internal signal names to a target's request body.
DEFAULT_FIELDS = {
    "trust": "trust", "v60": "v60", "v5m": "v5m", "v1h": "v1h",
    "amount": "amount", "device_risk": "device_risk", "anomaly": "anomaly",
    "country_shift": "country_shift", "unsafe_country": "unsafe_country",
}
SCORE_KEYS = ["score", "risk_score", "value", "result", "rating", "confidence"]


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        ctx["conn"].execute(
            "CREATE TABLE IF NOT EXISTS fingerprint_probe("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,api_key TEXT,target TEXT,"
            "ran REAL,vectors INTEGER,answered INTEGER,exact INTEGER,"
            "verdict TEXT,correlation REAL,detail TEXT,audit_hash TEXT,"
            "block_index INTEGER)")
        ctx["conn"].execute(
            "CREATE INDEX IF NOT EXISTS idx_fp_target ON fingerprint_probe(target)")
        ctx["conn"].commit()
    _ready = True


# ----------------------------------------------------------------------
# our own engine
# ----------------------------------------------------------------------

def _find_scorer():
    for modname in ("__main__", "server"):
        mod = sys.modules.get(modname)
        if not mod:
            continue
        for name in SCORER_NAMES:
            fn = getattr(mod, name, None)
            if callable(fn):
                return fn, modname + "." + name
    return None, None


def _score_locally():
    """Run the battery through the live engine. Returns (scores, source, error)."""
    fn, where = _find_scorer()
    if not fn:
        return None, None, ("could not find the scoring function at runtime - "
                            "add its name to SCORER_NAMES")
    out = []
    for label, signals in VECTORS:
        try:
            result = fn(dict(signals))
            score = result[0] if isinstance(result, (tuple, list)) else result
            out.append((label, round(float(score), 6)))
        except Exception as exc:
            return None, where, "scorer raised on %s: %s" % (label, exc)
    return out, where, None


# ----------------------------------------------------------------------
# reaching a target - same guards as witness.py
# ----------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _url_allowed(url):
    if not url or not isinstance(url, str) or len(url) > 500:
        return False, "no usable url"
    try:
        parts = urlparse(url.strip())
    except Exception:
        return False, "unparseable url"
    if parts.scheme not in ALLOWED_SCHEMES:
        return False, "scheme not allowed"
    host = parts.hostname
    if not host:
        return False, "no host in url"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        return False, "port not allowed"
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        return False, "could not resolve host (%s)" % type(exc).__name__
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "address is not publicly routable"
    return True, None


def _post(url, body, headers=None):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", "Accept": "application/json",
         "User-Agent": "aileash-fingerprint/%s" % VERSION}
    if headers:
        h.update(headers)
    request = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with _opener.open(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(MAX_BYTES)
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(MAX_BYTES)
        except Exception:
            raw = b""
        status = exc.code
    except Exception as exc:
        return 0, "unreachable (%s)" % type(exc).__name__
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return status, raw.decode("utf-8", "replace")[:300]


def _extract_score(payload, key_hint=None):
    """Pull a 0..1 style number out of whatever came back."""
    if isinstance(payload, (int, float)):
        return float(payload)
    if not isinstance(payload, dict):
        return None
    keys = ([key_hint] if key_hint else []) + SCORE_KEYS
    for k in keys:
        if k and k in payload:
            v = payload[k]
            if isinstance(v, (int, float)):
                return float(v)
            try:
                return float(str(v).strip())
            except (TypeError, ValueError):
                pass
    # one level down
    for v in payload.values():
        if isinstance(v, dict):
            found = _extract_score(v, key_hint)
            if found is not None:
                return found
    return None


# ----------------------------------------------------------------------
# comparison
# ----------------------------------------------------------------------

def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def _rank(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for position, index in enumerate(order):
        ranks[index] = float(position)
    return ranks


def _compare(ours, theirs):
    """ours/theirs are lists of (label, score). theirs may contain None."""
    paired = [(l, o, t) for (l, o), (_, t) in zip(ours, theirs) if t is not None]
    answered = len(paired)
    if answered < 3:
        return {"verdict": "INCONCLUSIVE", "answered": answered,
                "why": "too few vectors came back to compare anything"}

    a = [p[1] for p in paired]
    b = [p[2] for p in paired]
    exact = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 1e-6)
    close = sum(1 for i in range(answered) if abs(a[i] - b[i]) < 0.01)
    pearson = _pearson(a, b)
    spearman = _pearson(_rank(a), _rank(b))

    # a linear fit: are they our scores, scaled and shifted?
    ma, mb = sum(a) / answered, sum(b) / answered
    va = sum((x - ma) ** 2 for x in a)
    slope = (sum((a[i] - ma) * (b[i] - mb) for i in range(answered)) / va) if va > 0 else None
    intercept = (mb - slope * ma) if slope is not None else None
    residual = None
    if slope is not None:
        residual = max(abs(b[i] - (slope * a[i] + intercept)) for i in range(answered))

    if exact == answered:
        verdict = "IDENTICAL"
        why = ("Every vector matched to six decimal places. Two independently "
               "written scoring functions do not do this.")
    elif exact >= answered * 0.8:
        verdict = "IDENTICAL"
        why = ("%d of %d vectors matched exactly. The rest are consistent with "
               "a small local change on top of the same function." % (exact, answered))
    elif residual is not None and residual < 0.02 and pearson and pearson > 0.99:
        verdict = "DERIVED"
        why = ("Not identical, but every score fits ours scaled by %.3f and "
               "shifted by %.3f, within %.4f. That is this function reweighted, "
               "not a different one." % (slope, intercept, residual))
    elif spearman is not None and spearman > 0.95:
        verdict = "SAME SHAPE"
        why = ("Different numbers, but the same ordering across the battery "
               "(rank correlation %.3f). Consistent with the same design - the "
               "same saturation points and the same curve - rather than the "
               "same code." % spearman)
    elif pearson is not None and pearson > 0.8:
        verdict = "SIMILAR"
        why = ("Correlated (%.3f) but not tightly. Risk scorers tend to agree "
               "roughly on what looks risky, so this is weak on its own." % pearson)
    else:
        verdict = "UNRELATED"
        why = "No meaningful relationship to our scoring."

    return {
        "verdict": verdict, "why": why,
        "vectors": len(ours), "answered": answered,
        "exact_matches": exact, "within_0.01": close,
        "correlation": round(pearson, 4) if pearson is not None else None,
        "rank_correlation": round(spearman, 4) if spearman is not None else None,
        "best_fit": ({"scale": round(slope, 4), "shift": round(intercept, 4),
                      "worst_residual": round(residual, 5)}
                     if slope is not None else None),
        "per_vector": [{"vector": p[0], "ours": p[1], "theirs": p[2],
                        "delta": round(p[2] - p[1], 6)} for p in paired],
    }


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

def _self(ctx, api_key):
    scores, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503
    return {"source": where, "vectors": len(scores),
            "scores": [{"vector": l, "score": s} for l, s in scores],
            "note": ("This is the baseline every probe is compared against. It "
                     "reveals outputs, never weights.")}, 200


def _probe(ctx, api_key, data):
    url = str(data.get("url", "")).strip()
    ok, why = _url_allowed(url)
    if not ok:
        return {"error": "bad_target", "message": why}, 400

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    mapping = dict(DEFAULT_FIELDS)
    mapping.update({k: str(v) for k, v in fields.items() if isinstance(v, str)})
    score_key = data.get("score_key")
    extra = data.get("body") if isinstance(data.get("body"), dict) else {}
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    headers = {str(k)[:60]: str(v)[:300] for k, v in list(headers.items())[:8]}

    ours, where, error = _score_locally()
    if error:
        return {"error": "scorer_unavailable", "message": error}, 503

    theirs = []
    failures = []
    for label, signals in VECTORS:
        body = dict(extra)
        for internal, external in mapping.items():
            body[external] = signals[internal]
        status, payload = _post(url, body, headers)
        if status < 200 or status >= 300:
            theirs.append((label, None))
            if len(failures) < 5:
                failures.append({"vector": label, "http": status,
                                 "response": payload if isinstance(payload, (dict, list))
                                 else str(payload)[:200]})
        else:
            theirs.append((label, _extract_score(payload, score_key)))
        time.sleep(POLITE_DELAY)

    result = _compare(ours, theirs)
    ts = time.time()

    detail = ("target=" + url + ";verdict=" + result["verdict"] +
              ";exact=" + str(result.get("exact_matches", 0)) +
              "/" + str(result.get("answered", 0)))
    ev = {"user_id": "fp:" + urlparse(url).hostname, "action": "fingerprint_probe",
          "amount": 0, "country": "UK", "device_id": "fingerprint",
          "anomaly": 0, "device_risk": 0}
    res = {"decision": "FINGERPRINT_" + result["verdict"].replace(" ", "_"),
           "score": 0, "fingerprint_version": VERSION, "target": url,
           "timestamp": ts, "detail": detail}
    h, idx, seq = ctx["seal"](ev, res, ts, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO fingerprint_probe(api_key,target,ran,vectors,answered,"
            "exact,verdict,correlation,detail,audit_hash,block_index)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (api_key, url, ts, result.get("vectors"), result.get("answered"),
             result.get("exact_matches"), result["verdict"],
             result.get("correlation"), detail, h, idx))
        ctx["conn"].commit()

    out = dict(result)
    out.update({
        "target": url,
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
        "sealed": {"receipt": h, "block_index": idx, "receipt_seq": seq},
        "what_this_is": ("A dated, sealed measurement of similarity. It is "
                         "evidence, not an accusation, and it does not "
                         "establish that anything was copied."),
    })
    if failures:
        out["failures"] = failures
        out["failure_note"] = ("Some vectors were rejected. If the target wants "
                               "different field names, pass a \"fields\" map and "
                               "run it again.")
    return out, 200


def _history(ctx, api_key):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT target,ran,verdict,exact,answered,correlation,audit_hash,block_index"
            " FROM fingerprint_probe WHERE api_key=? ORDER BY id DESC LIMIT 100",
            (api_key,)).fetchall()
    return {"probes": [{
        "target": r[0],
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(r[1])),
        "verdict": r[2], "exact_matches": r[3], "answered": r[4],
        "correlation": r[5], "receipt": r[6], "block_index": r[7],
    } for r in rows], "count": len(rows)}, 200


def _vectors():
    return {"count": len(VECTORS),
            "vectors": [{"label": l, "signals": s} for l, s in VECTORS],
            "why_these": ("Chosen to sit either side of each saturation point, "
                          "to walk the amount curve, and to isolate each term. "
                          "Random inputs would only catch a straight copy.")}, 200


def _spec():
    return {
        "module": "fingerprint", "version": VERSION,
        "question_it_answers": "Is this endpoint running my scoring function?",
        "verdicts": {
            "IDENTICAL": "Every vector matches. Independently written functions do not do this.",
            "DERIVED": "Not identical, but every score is ours scaled and shifted. Reweighted, not rewritten.",
            "SAME SHAPE": "Different numbers, same ordering. Same design decisions, probably not the same code.",
            "SIMILAR": "Loosely correlated. Weak - risk scorers broadly agree on what looks risky.",
            "UNRELATED": "No meaningful relationship.",
            "INCONCLUSIVE": "Too few vectors came back.",
        },
        "limits": [
            "Only reaches endpoints it can reach. A private product with no free tier is invisible to this.",
            "Proves similarity, never theft. Two people can converge honestly.",
            "A target that rate limits, randomises or rounds heavily will read as INCONCLUSIVE rather than clean.",
        ],
        "every_run_is_sealed": ("The probe, the target and the result go into the "
                                "chain, so a comparison run today is provable as "
                                "having been run today."),
        "manners": "One request per vector with a %.1fs gap. It is a measurement, not a load test." % POLITE_DELAY,
    }, 200


def handle(method, action, data, api_key, ctx):
    # key first, before anything touches the database
    if not api_key:
        return {"error": "invalid_api_key"}, 401
    _setup(ctx)
    action = (action or "").strip("/").lower()

    if method == "POST":
        if action == "self":
            return _self(ctx, api_key)
        if action == "probe":
            return _probe(ctx, api_key, data)
        return {"error": "unknown_action", "action": action,
                "POST": ["self", "probe"]}, 404

    if action in ("", "spec"):
        return _spec()
    if action == "history":
        return _history(ctx, api_key)
    if action == "vectors":
        return _vectors()
    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "history", "vectors"]}, 404

```
