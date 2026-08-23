"""
wallet.py - metering gate
=========================
v1.1.0

WHAT THIS IS
------------
The thing that decides whether a decision is allowed to happen, and
seals that decision into the same chain as the decision itself. Spend
record and audit record are one record.

Three ways a call is allowed:

  1. FREE WINDOW  - the key is under 90 days old. Nothing is charged.
  2. SUBSCRIBED   - the device has a live 30-day plan. Nothing is charged.
  3. METERED      - neither of the above. The balance pays per decision
                    and the call is refused at zero.

MONEY
-----
Held as integer millipence. No floats anywhere near a balance.
Settlement is deliberately not implemented. `topup` is a keyed
operation you run by hand after a payment clears. Nothing in this
module talks to a payment provider, and it must not be wired to one
without the duplicate-credit problem being solved first.

THE HALT RULE
-------------
A receipt presented twice halts the whole key with 423 - subscribed
devices included. Not "probably a retry", not "probably a collision".
A person looks at it at /x/wallet/review and clears it. A machine does
not get to decide whether a repeated hash was a replay.

ROUTES
------
  GET  /x/wallet/spec       public
  GET  /x/wallet/status     keyed
  GET  /x/wallet/quote      keyed
  POST /x/wallet/charge     keyed   - the gate
  POST /x/wallet/topup      keyed   - manual credit
  GET  /x/wallet/ledger     keyed
  POST /x/wallet/simulate   keyed   - dry run, spends nothing
  POST /x/wallet/subscribe  keyed
  GET  /x/wallet/devices    keyed
  GET  /x/wallet/review     keyed   - open halts
  POST /x/wallet/clear      keyed   - a person clears a halt
"""

import hashlib
import json
import re
import time

VERSION = "1.1.0"

PUBLIC = {("GET", "spec")}

# ---------------------------------------------------------------- pricing
# 1 penny = 1000 millipence. Change these two lines and nothing else.
MILLIPENCE_PER_PENNY = 1000
DEVICE_PLAN_MILLIPENCE = 50 * MILLIPENCE_PER_PENNY      # 50p
DEVICE_PLAN_DAYS = 30
DECISION_MILLIPENCE = 100                                # 0.1p per decision

FREE_WINDOW_DAYS = 90
FREE_WINDOW_SECONDS = FREE_WINDOW_DAYS * 86400
DAY = 86400

MAX_TOPUP_MILLIPENCE = 500 * 100 * MILLIPENCE_PER_PENNY  # £500 a go
MAX_LEDGER = 200
MAX_DEVICE_ID = 80

HEX64 = re.compile(r"^[0-9a-f]{64}$")
DEVICE_OK = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


# ---------------------------------------------------------------- helpers

def _now():
    return round(time.time(), 3)


def _pence(millipence):
    """For display only. Never used in arithmetic that decides anything."""
    return round(millipence / MILLIPENCE_PER_PENNY, 3)


def _seal(ctx, event, result):
    """
    Write through the server's own seal(). Its signature differs across
    the stack, so try the shapes it has taken rather than assume one.
    """
    fn = ctx.get("seal") if isinstance(ctx, dict) else None
    if not callable(fn):
        return None
    for attempt in (
        lambda: fn(event, result),
        lambda: fn(event=event, result=result),
        lambda: fn(json.dumps({"event": event, "result": result})),
    ):
        try:
            return attempt()
        except TypeError:
            continue
    return None


def _seal_ref(sealed):
    if sealed is None:
        return None
    if isinstance(sealed, str):
        return sealed
    if isinstance(sealed, dict):
        for k in ("audit_hash", "hash", "receipt", "block_hash", "id"):
            if sealed.get(k):
                return str(sealed[k])
    if isinstance(sealed, (int, float)):
        return str(sealed)
    return None


def _ensure_tables(ctx):
    conn = ctx["conn"]
    with ctx["lock"]:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_balance (
                api_key      TEXT PRIMARY KEY,
                millipence   INTEGER NOT NULL DEFAULT 0,
                updated      REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_ledger (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key      TEXT NOT NULL,
                kind         TEXT NOT NULL,
                millipence   INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                device_id    TEXT,
                receipt      TEXT,
                note         TEXT,
                seal_ref     TEXT,
                created      REAL NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wallet_ledger_key "
            "ON wallet_ledger(api_key, id)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_device (
                api_key      TEXT NOT NULL,
                device_id    TEXT NOT NULL,
                expires      REAL NOT NULL,
                first_seen   REAL NOT NULL,
                PRIMARY KEY (api_key, device_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_receipt (
                api_key      TEXT NOT NULL,
                receipt      TEXT NOT NULL,
                device_id    TEXT,
                created      REAL NOT NULL,
                PRIMARY KEY (api_key, receipt)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wallet_halt (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key      TEXT NOT NULL,
                reason       TEXT NOT NULL,
                receipt      TEXT,
                device_id    TEXT,
                detail       TEXT,
                cleared      INTEGER NOT NULL DEFAULT 0,
                cleared_by   TEXT,
                cleared_note TEXT,
                cleared_at   REAL,
                created      REAL NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wallet_halt_open "
            "ON wallet_halt(api_key, cleared)"
        )
        conn.commit()


def _balance(ctx, api_key):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT millipence FROM wallet_balance WHERE api_key=?",
            (api_key,)
        ).fetchone()
    return int(row[0]) if row else 0


def _write_ledger(ctx, api_key, kind, delta, balance_after,
                  device_id=None, receipt=None, note=None, seal_ref=None):
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO wallet_ledger (api_key, kind, millipence, "
            "balance_after, device_id, receipt, note, seal_ref, created) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (api_key, kind, int(delta), int(balance_after), device_id,
             receipt, note, seal_ref, _now())
        )
        ctx["conn"].commit()


def _key_created(ctx, api_key):
    """
    When was this key made. Read api_keys' real schema rather than
    assume a column name. Returns None if it cannot be determined -
    and None means NO free window, not an unlimited one.
    """
    conn = ctx["conn"]
    try:
        with ctx["lock"]:
            cols = [r[1] for r in
                    conn.execute("PRAGMA table_info(api_keys)").fetchall()]
    except Exception:
        return None
    if not cols:
        return None
    for name in ("created", "created_at", "created_ts", "issued", "ts"):
        if name in cols:
            try:
                with ctx["lock"]:
                    row = conn.execute(
                        "SELECT %s FROM api_keys WHERE key=?" % name,
                        (api_key,)
                    ).fetchone()
            except Exception:
                try:
                    with ctx["lock"]:
                        row = conn.execute(
                            "SELECT %s FROM api_keys WHERE api_key=?" % name,
                            (api_key,)
                        ).fetchone()
                except Exception:
                    return None
            if row and row[0]:
                try:
                    return float(row[0])
                except (TypeError, ValueError):
                    return None
            return None
    return None


def _free_window(ctx, api_key):
    created = _key_created(ctx, api_key)
    if created is None:
        return {"in_free_window": False, "reason": "key age unknown"}
    ends = created + FREE_WINDOW_SECONDS
    remaining = ends - time.time()
    return {
        "in_free_window": remaining > 0,
        "key_created": round(created, 3),
        "free_until": round(ends, 3),
        "days_remaining": round(remaining / DAY, 2) if remaining > 0 else 0,
    }


def _open_halt(ctx, api_key):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id, reason, receipt, device_id, detail, created "
            "FROM wallet_halt WHERE api_key=? AND cleared=0 "
            "ORDER BY id LIMIT 1", (api_key,)
        ).fetchone()
    if not row:
        return None
    return {
        "halt_id": row[0], "reason": row[1], "receipt": row[2],
        "device_id": row[3], "detail": row[4], "since": row[5],
    }


def _halted_response(halt):
    return {
        "allowed": False,
        "halted": True,
        "halt": halt,
        "means": (
            "This key is stopped. A subscribed device does not pass "
            "either. A person has to look at the halt and clear it at "
            "/x/wallet/clear before anything runs again."
        ),
    }, 423


def _device_live(ctx, api_key, device_id):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT expires FROM wallet_device WHERE api_key=? AND device_id=?",
            (api_key, device_id)
        ).fetchone()
    if not row:
        return None
    expires = float(row[0])
    return expires if expires > time.time() else None


def _check_device(value):
    device_id = (value or "").strip() if isinstance(value, str) else ""
    if not device_id:
        return None, {"error": "device_id required"}
    if len(device_id) > MAX_DEVICE_ID or not DEVICE_OK.match(device_id):
        return None, {
            "error": "device_id must be 1-80 characters, letters, digits, "
                     "dot, underscore, colon or hyphen"
        }
    return device_id, None


# ------------------------------------------------------------------ spec

def _spec():
    return {
        "module": "wallet",
        "version": VERSION,
        "what_this_is": (
            "A gate. It decides whether a decision may proceed and seals "
            "that decision into the audit chain, so the spend record and "
            "the audit record are the same record."
        ),
        "allowed_when": [
            "free_window - key under %d days old, nothing charged"
                % FREE_WINDOW_DAYS,
            "subscribed - device has a live %d-day plan, nothing charged"
                % DEVICE_PLAN_DAYS,
            "metered - balance pays per decision, refused at zero",
        ],
        "pricing": {
            "device_plan_pence": _pence(DEVICE_PLAN_MILLIPENCE),
            "device_plan_days": DEVICE_PLAN_DAYS,
            "per_decision_pence": _pence(DECISION_MILLIPENCE),
            "unit": "millipence, integer. 1000 millipence = 1 penny.",
            "renewal": "Subscribing again before expiry extends from the "
                       "existing expiry. It does not reset it.",
        },
        "duplicate_receipts": {
            "rule": "A receipt presented twice halts the whole key with "
                    "HTTP 423, subscribed devices included.",
            "why": "A repeated hash is either a replay or a collision. "
                   "Neither is a thing a machine should rule on.",
            "clearing": "A person clears it at POST /x/wallet/clear.",
        },
        "settlement": (
            "Not implemented, on purpose. topup is a keyed operation run "
            "by hand once a payment has cleared. This module does not "
            "talk to a payment provider."
        ),
        "what_this_does_not_do": [
            "It does not stop a model saying something false. It records "
            "what ran, and refuses to let more run than was paid for.",
            "It does not settle, refund, or invoice.",
        ],
        "routes": {
            "GET  spec": "public",
            "GET  status": "keyed - balance, window, devices, halts",
            "GET  quote": "keyed - current prices",
            "POST charge": "keyed - the gate. device_id, receipt",
            "POST topup": "keyed - millipence, note",
            "GET  ledger": "keyed - limit",
            "POST simulate": "keyed - how far does a runaway loop get",
            "POST subscribe": "keyed - device_id",
            "GET  devices": "keyed",
            "GET  review": "keyed - open halts",
            "POST clear": "keyed - halt_id, cleared_by, note",
        },
    }


# ---------------------------------------------------------------- charge

def _charge(data, api_key, ctx, dry_run=False):
    device_id, err = _check_device((data or {}).get("device_id"))
    if err:
        return err, 400

    receipt = (data or {}).get("receipt")
    receipt = receipt.strip().lower() if isinstance(receipt, str) else ""
    if not HEX64.match(receipt or ""):
        return {"error": "receipt must be 64 lowercase hex characters",
                "note": "This is the digest of the decision being charged "
                        "for. It is what makes a replay detectable."}, 400

    halt = _open_halt(ctx, api_key)
    if halt:
        return _halted_response(halt)

    # ---- replay check
    with ctx["lock"]:
        seen = ctx["conn"].execute(
            "SELECT device_id, created FROM wallet_receipt "
            "WHERE api_key=? AND receipt=?", (api_key, receipt)
        ).fetchone()

    if seen:
        if dry_run:
            return {
                "allowed": False,
                "would_halt": True,
                "reason": "duplicate_receipt",
                "first_seen": seen[1],
                "dry_run": True,
            }, 200
        detail = json.dumps({
            "first_seen_at": seen[1],
            "first_seen_device": seen[0],
            "presented_again_by": device_id,
        })
        sealed = _seal(ctx, "wallet.halt", {
            "api_key": api_key, "receipt": receipt,
            "reason": "duplicate_receipt", "detail": detail,
        })
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO wallet_halt (api_key, reason, receipt, "
                "device_id, detail, created) VALUES (?,?,?,?,?,?)",
                (api_key, "duplicate_receipt", receipt, device_id,
                 detail, _now())
            )
            ctx["conn"].commit()
        out, status = _halted_response(_open_halt(ctx, api_key))
        out["sealed_as"] = _seal_ref(sealed)
        return out, status

    # ---- work out who pays
    window = _free_window(ctx, api_key)
    expires = _device_live(ctx, api_key, device_id)
    balance = _balance(ctx, api_key)

    if window["in_free_window"]:
        basis, cost = "free_window", 0
    elif expires:
        basis, cost = "subscribed", 0
    else:
        basis, cost = "metered", DECISION_MILLIPENCE

    if cost and balance < cost:
        out = {
            "allowed": False,
            "reason": "insufficient_balance",
            "basis": "metered",
            "balance_millipence": balance,
            "balance_pence": _pence(balance),
            "needed_millipence": cost,
            "fix": ["POST /x/wallet/subscribe for this device, or",
                    "POST /x/wallet/topup once a payment has cleared"],
        }
        if dry_run:
            out["dry_run"] = True
            return out, 200
        return out, 402

    if dry_run:
        return {
            "allowed": True,
            "dry_run": True,
            "basis": basis,
            "would_cost_millipence": cost,
            "balance_millipence": balance,
            "decisions_remaining_at_this_rate": (
                None if not cost else balance // cost),
            "note": "Nothing was spent, sealed or recorded.",
        }, 200

    # ---- commit
    new_balance = balance - cost
    if cost:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO wallet_balance (api_key, millipence, updated) "
                "VALUES (?,?,?) ON CONFLICT(api_key) DO UPDATE SET "
                "millipence=excluded.millipence, updated=excluded.updated",
                (api_key, new_balance, _now())
            )
            ctx["conn"].commit()

    sealed = _seal(ctx, "wallet.charge", {
        "receipt": receipt,
        "device_id": device_id,
        "basis": basis,
        "cost_millipence": cost,
        "balance_after": new_balance,
    })
    seal_ref = _seal_ref(sealed)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO wallet_receipt "
            "(api_key, receipt, device_id, created) VALUES (?,?,?,?)",
            (api_key, receipt, device_id, _now())
        )
        ctx["conn"].commit()

    _write_ledger(ctx, api_key, "charge", -cost, new_balance,
                  device_id=device_id, receipt=receipt, note=basis,
                  seal_ref=seal_ref)

    return {
        "allowed": True,
        "basis": basis,
        "cost_millipence": cost,
        "balance_millipence": new_balance,
        "balance_pence": _pence(new_balance),
        "receipt": receipt,
        "sealed_as": seal_ref,
        "device_plan_expires": expires,
        "means": "This decision is paid for and recorded in the chain. "
                 "Nothing here says the decision was correct.",
    }, 200


# -------------------------------------------------------------- the rest

def _topup(data, api_key, ctx):
    raw = (data or {}).get("millipence")
    try:
        amount = int(raw)
    except (TypeError, ValueError):
        return {"error": "millipence must be a whole number",
                "note": "1000 millipence = 1 penny"}, 400
    if amount <= 0 or amount > MAX_TOPUP_MILLIPENCE:
        return {"error": "millipence out of range",
                "max": MAX_TOPUP_MILLIPENCE}, 400

    note = (data or {}).get("note")
    note = note.strip()[:200] if isinstance(note, str) else None
    if not note:
        return {"error": "note required",
                "why": "Every credit needs a reason recorded - the payment "
                       "reference, invoice number or who authorised it."}, 400

    balance = _balance(ctx, api_key) + amount
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO wallet_balance (api_key, millipence, updated) "
            "VALUES (?,?,?) ON CONFLICT(api_key) DO UPDATE SET "
            "millipence=excluded.millipence, updated=excluded.updated",
            (api_key, balance, _now())
        )
        ctx["conn"].commit()

    sealed = _seal(ctx, "wallet.topup", {
        "millipence": amount, "balance_after": balance, "note": note})
    seal_ref = _seal_ref(sealed)
    _write_ledger(ctx, api_key, "topup", amount, balance,
                  note=note, seal_ref=seal_ref)

    return {"ok": True, "credited_millipence": amount,
            "credited_pence": _pence(amount),
            "balance_millipence": balance,
            "balance_pence": _pence(balance),
            "note": note, "sealed_as": seal_ref}, 200


def _subscribe(data, api_key, ctx):
    device_id, err = _check_device((data or {}).get("device_id"))
    if err:
        return err, 400

    halt = _open_halt(ctx, api_key)
    if halt:
        return _halted_response(halt)

    balance = _balance(ctx, api_key)
    if balance < DEVICE_PLAN_MILLIPENCE:
        return {"error": "insufficient_balance",
                "needed_millipence": DEVICE_PLAN_MILLIPENCE,
                "needed_pence": _pence(DEVICE_PLAN_MILLIPENCE),
                "balance_millipence": balance}, 402

    now = time.time()
    existing = _device_live(ctx, api_key, device_id)
    base = existing if existing else now          # early renewal extends
    expires = base + DEVICE_PLAN_DAYS * DAY
    new_balance = balance - DEVICE_PLAN_MILLIPENCE

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO wallet_balance (api_key, millipence, updated) "
            "VALUES (?,?,?) ON CONFLICT(api_key) DO UPDATE SET "
            "millipence=excluded.millipence, updated=excluded.updated",
            (api_key, new_balance, _now())
        )
        ctx["conn"].execute(
            "INSERT INTO wallet_device (api_key, device_id, expires, "
            "first_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(api_key, device_id) DO UPDATE SET "
            "expires=excluded.expires",
            (api_key, device_id, expires, _now())
        )
        ctx["conn"].commit()

    sealed = _seal(ctx, "wallet.subscribe", {
        "device_id": device_id, "expires": expires,
        "cost_millipence": DEVICE_PLAN_MILLIPENCE})
    seal_ref = _seal_ref(sealed)
    _write_ledger(ctx, api_key, "subscribe", -DEVICE_PLAN_MILLIPENCE,
                  new_balance, device_id=device_id,
                  note="%d days" % DEVICE_PLAN_DAYS, seal_ref=seal_ref)

    return {"ok": True, "device_id": device_id, "expires": round(expires, 3),
            "extended_from_existing": bool(existing),
            "balance_millipence": new_balance,
            "balance_pence": _pence(new_balance),
            "sealed_as": seal_ref}, 200


def _devices(api_key, ctx):
    now = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT device_id, expires, first_seen FROM wallet_device "
            "WHERE api_key=? ORDER BY device_id", (api_key,)
        ).fetchall()
    devices = [{
        "device_id": r[0],
        "expires": r[1],
        "live": r[1] > now,
        "days_remaining": round((r[1] - now) / DAY, 2) if r[1] > now else 0,
        "first_seen": r[2],
    } for r in rows]
    return {"count": len(devices),
            "live": sum(1 for d in devices if d["live"]),
            "devices": devices}, 200


def _ledger(data, api_key, ctx):
    try:
        limit = int((data or {}).get("limit", 50))
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, MAX_LEDGER))
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT kind, millipence, balance_after, device_id, receipt, "
            "note, seal_ref, created FROM wallet_ledger WHERE api_key=? "
            "ORDER BY id DESC LIMIT ?", (api_key, limit)
        ).fetchall()
    return {"count": len(rows), "limit": limit, "entries": [{
        "kind": r[0], "millipence": r[1], "balance_after": r[2],
        "device_id": r[3], "receipt": r[4], "note": r[5],
        "sealed_as": r[6], "at": r[7]} for r in rows]}, 200


def _review(api_key, ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT id, reason, receipt, device_id, detail, created "
            "FROM wallet_halt WHERE api_key=? AND cleared=0 ORDER BY id",
            (api_key,)
        ).fetchall()
    return {
        "open": len(rows),
        "halts": [{"halt_id": r[0], "reason": r[1], "receipt": r[2],
                   "device_id": r[3], "detail": r[4], "since": r[5]}
                  for r in rows],
        "note": "While any halt is open this key is stopped. Clearing is a "
                "human decision and is itself sealed.",
    }, 200


def _clear(data, api_key, ctx):
    try:
        halt_id = int((data or {}).get("halt_id"))
    except (TypeError, ValueError):
        return {"error": "halt_id required"}, 400

    who = (data or {}).get("cleared_by")
    who = who.strip()[:120] if isinstance(who, str) else None
    note = (data or {}).get("note")
    note = note.strip()[:300] if isinstance(note, str) else None
    if not who or not note:
        return {"error": "cleared_by and note both required",
                "why": "A halt is cleared by a named person giving a "
                       "reason. Both are sealed."}, 400

    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT reason, receipt FROM wallet_halt "
            "WHERE id=? AND api_key=? AND cleared=0", (halt_id, api_key)
        ).fetchone()
    if not row:
        return {"error": "no open halt with that id for this key"}, 404

    sealed = _seal(ctx, "wallet.halt_cleared", {
        "halt_id": halt_id, "reason": row[0], "receipt": row[1],
        "cleared_by": who, "note": note})
    seal_ref = _seal_ref(sealed)

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE wallet_halt SET cleared=1, cleared_by=?, "
            "cleared_note=?, cleared_at=? WHERE id=?",
            (who, note, _now(), halt_id)
        )
        ctx["conn"].commit()

    remaining = _open_halt(ctx, api_key)
    return {"ok": True, "halt_id": halt_id, "cleared_by": who,
            "sealed_as": seal_ref,
            "key_running": remaining is None,
            "still_open": remaining}, 200


def _status(api_key, ctx):
    balance = _balance(ctx, api_key)
    window = _free_window(ctx, api_key)
    halt = _open_halt(ctx, api_key)
    devices, _ = _devices(api_key, ctx)
    return {
        "balance_millipence": balance,
        "balance_pence": _pence(balance),
        "free_window": window,
        "devices_live": devices["live"],
        "devices_total": devices["count"],
        "halted": halt is not None,
        "halt": halt,
        "decisions_left_if_metered": balance // DECISION_MILLIPENCE,
        "settlement": "manual - topup is run by hand after payment clears",
    }, 200


def _quote():
    return {
        "device_plan": {"pence": _pence(DEVICE_PLAN_MILLIPENCE),
                        "millipence": DEVICE_PLAN_MILLIPENCE,
                        "days": DEVICE_PLAN_DAYS},
        "per_decision": {"pence": _pence(DECISION_MILLIPENCE),
                         "millipence": DECISION_MILLIPENCE},
        "free_window_days": FREE_WINDOW_DAYS,
        "note": "A subscribed device's decisions cost nothing while the "
                "plan runs. Everything else is metered.",
    }, 200


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action == "spec":
            return _spec(), 200

        if not api_key:
            return {"error": "key required"}, 401

        _ensure_tables(ctx)

        if method == "GET":
            if action == "status":
                return _status(api_key, ctx)
            if action == "quote":
                return _quote()
            if action == "ledger":
                return _ledger(data, api_key, ctx)
            if action == "devices":
                return _devices(api_key, ctx)
            if action == "review":
                return _review(api_key, ctx)

        if method == "POST":
            if action == "charge":
                return _charge(data, api_key, ctx, dry_run=False)
            if action == "simulate":
                return _charge(data, api_key, ctx, dry_run=True)
            if action == "topup":
                return _topup(data, api_key, ctx)
            if action == "subscribe":
                return _subscribe(data, api_key, ctx)
            if action == "clear":
                return _clear(data, api_key, ctx)

        return {"error": "unknown action", "module": "wallet",
                "see": "/x/wallet/spec"}, 404

    except Exception as exc:
        return {"error": "wallet module error",
                "detail": str(exc)[:200]}, 500
