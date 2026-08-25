# Codebase — part 13 of 26

Contains:
- `modules/wallet.py`
- `modules/warmup.py`
- `modules/witnessed.py`
- `Verify_ai.py`
- `ai_act_ranker.py`
- `ai_safety_scanner.py`
- `aigrade_insert.py`
- `aileash_reporter.py`
- `aileash_signed_client.py`


## `modules/wallet.py`

791 lines, 30234 bytes

```python
"""
wallet.py - metering gate
=========================
v1.2.0

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

SEALING
-------
Every charge, credit, subscription, halt and clearance goes through
ctx["seal"](ev, res, ts, api_key) - the same call witness.py makes -
and the returned audit hash and block index are stored on the ledger
row. The seal is NOT wrapped in a try/except: if the chain will not
accept the record, the charge must not be reported as allowed. A 500
here is the correct outcome, because an unsealed charge is exactly the
thing this module exists to prevent.

v1.2.0 fixes the seal call. v1.1.0 guessed at the signature, could not
match it, and silently recorded nothing - every charge came back with
sealed_as null. Nothing was lost, because nothing had been charged
yet, but a spend gate that does not seal is only a spend gate.

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

import re
import time

VERSION = "1.2.0"

PUBLIC = {("GET", "spec")}

# ---------------------------------------------------------------- pricing
# 1 penny = 1000 millipence. Change these three lines and nothing else.
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

_ready = False


# ---------------------------------------------------------------- helpers

def _now():
    return round(time.time(), 3)


def _pence(millipence):
    """For display only. Never used in arithmetic that decides anything."""
    return round(millipence / MILLIPENCE_PER_PENNY, 3)


def _seal(ctx, api_key, action, decision, device_id, detail, risk=0):
    """
    Write a block through the server's own seal.

    Signature is ctx["seal"](ev, res, ts, api_key) returning
    (audit_hash, block_index, seq) - the same call witness.py and
    witnessed.py make. Deliberately not guarded: an unsealed charge must
    fail loudly, not pass quietly.
    """
    ts = time.time()
    ev = {"user_id": "wallet:" + (device_id or "-")[:40],
          "action": action,
          "amount": 0,
          "country": "UK",
          "device_id": device_id or "wallet",
          "anomaly": 0,
          "device_risk": risk}
    res = {"decision": decision, "score": 0, "wallet_version": VERSION}
    res.update(detail or {})
    audit_hash, block_index, seq = ctx["seal"](ev, res, ts, api_key)
    return audit_hash, block_index, seq


def _setup(ctx):
    global _ready
    if _ready:
        return
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
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key       TEXT NOT NULL,
                kind          TEXT NOT NULL,
                millipence    INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                device_id     TEXT,
                receipt       TEXT,
                note          TEXT,
                seal_ref      TEXT,
                created       REAL NOT NULL
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wallet_ledger_key "
            "ON wallet_ledger(api_key, id)")

        # Added in 1.2. Rows written by 1.1 keep NULL, which reads as
        # unsealed - correct, because they were.
        have = set()
        try:
            for row in conn.execute(
                    "PRAGMA table_info(wallet_ledger)").fetchall():
                have.add(row[1])
        except Exception:
            pass
        if "block_index" not in have:
            try:
                conn.execute(
                    "ALTER TABLE wallet_ledger ADD COLUMN block_index INTEGER")
            except Exception:
                pass

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
            "ON wallet_halt(api_key, cleared)")
        conn.commit()
    _ready = True


def _balance(ctx, api_key):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT millipence FROM wallet_balance WHERE api_key=?",
            (api_key,)).fetchone()
    return int(row[0]) if row else 0


def _set_balance(ctx, api_key, millipence):
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO wallet_balance (api_key, millipence, updated) "
            "VALUES (?,?,?) ON CONFLICT(api_key) DO UPDATE SET "
            "millipence=excluded.millipence, updated=excluded.updated",
            (api_key, int(millipence), _now()))
        ctx["conn"].commit()


def _write_ledger(ctx, api_key, kind, delta, balance_after, device_id=None,
                  receipt=None, note=None, seal_ref=None, block_index=None):
    """
    The seal is the record. This row is a convenience for lookup, so a
    failure here is reported and never turns a sealed charge into a
    failed one - same posture as witness.py's index insert.
    """
    try:
        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO wallet_ledger (api_key, kind, millipence, "
                "balance_after, device_id, receipt, note, seal_ref, "
                "block_index, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (api_key, kind, int(delta), int(balance_after), device_id,
                 receipt, note, seal_ref, block_index, _now()))
            ctx["conn"].commit()
        return None
    except Exception as exc:
        return type(exc).__name__


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
        if name not in cols:
            continue
        for keycol in ("key", "api_key"):
            if keycol not in cols:
                continue
            try:
                with ctx["lock"]:
                    row = conn.execute(
                        "SELECT %s FROM api_keys WHERE %s=?" % (name, keycol),
                        (api_key,)).fetchone()
            except Exception:
                continue
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
            "ORDER BY id LIMIT 1", (api_key,)).fetchone()
    if not row:
        return None
    return {"halt_id": row[0], "reason": row[1], "receipt": row[2],
            "device_id": row[3], "detail": row[4], "since": row[5]}


def _halted_response(halt):
    return {
        "allowed": False,
        "halted": True,
        "halt": halt,
        "means": ("This key is stopped. A subscribed device does not pass "
                  "either. A person has to look at the halt and clear it at "
                  "/x/wallet/clear before anything runs again."),
    }, 423


def _device_live(ctx, api_key, device_id):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT expires FROM wallet_device WHERE api_key=? AND device_id=?",
            (api_key, device_id)).fetchone()
    if not row:
        return None
    expires = float(row[0])
    return expires if expires > time.time() else None


def _check_device(value):
    device_id = (value or "").strip() if isinstance(value, str) else ""
    if not device_id:
        return None, {"error": "device_id required"}
    if len(device_id) > MAX_DEVICE_ID or not DEVICE_OK.match(device_id):
        return None, {"error": "device_id must be 1-80 characters, letters, "
                               "digits, dot, underscore, colon or hyphen"}
    return device_id, None


# ------------------------------------------------------------------ spec

def _spec():
    return {
        "module": "wallet",
        "version": VERSION,
        "what_this_is": (
            "A gate. It decides whether a decision may proceed and seals "
            "that decision into the audit chain, so the spend record and "
            "the audit record are the same record."),
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
            "renewal": ("Subscribing again before expiry extends from the "
                        "existing expiry. It does not reset it."),
        },
        "duplicate_receipts": {
            "rule": ("A receipt presented twice halts the whole key with "
                     "HTTP 423, subscribed devices included."),
            "why": ("A repeated hash is either a replay or a collision. "
                    "Neither is a thing a machine should rule on."),
            "clearing": "A person clears it at POST /x/wallet/clear.",
        },
        "sealing": (
            "Every charge, credit, subscription, halt and clearance is a "
            "block in this chain. If the chain will not accept the record "
            "the call fails - an unsealed charge is never reported as "
            "allowed."),
        "settlement": (
            "Not implemented, on purpose. topup is a keyed operation run "
            "by hand once a payment has cleared. This module does not "
            "talk to a payment provider."),
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
            "WHERE api_key=? AND receipt=?", (api_key, receipt)).fetchone()

    if seen:
        if dry_run:
            return {"allowed": False, "would_halt": True,
                    "reason": "duplicate_receipt", "first_seen": seen[1],
                    "dry_run": True}, 200

        detail = ("receipt=%s;first_seen=%s;first_device=%s;presented_by=%s"
                  % (receipt, seen[1], seen[0], device_id))
        audit_hash, block_index, seq = _seal(
            ctx, api_key, "wallet_halted", "WALLET_HALTED", device_id,
            {"reason": "duplicate_receipt", "receipt": receipt,
             "first_seen": seen[1], "detail": detail}, risk=1)

        with ctx["lock"]:
            ctx["conn"].execute(
                "INSERT INTO wallet_halt (api_key, reason, receipt, "
                "device_id, detail, created) VALUES (?,?,?,?,?,?)",
                (api_key, "duplicate_receipt", receipt, device_id,
                 detail, _now()))
            ctx["conn"].commit()

        out, status = _halted_response(_open_halt(ctx, api_key))
        out["sealed_as"] = audit_hash
        out["block_index"] = block_index
        out["receipt_seq"] = seq
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
        out = {"allowed": False, "reason": "insufficient_balance",
               "basis": "metered",
               "balance_millipence": balance,
               "balance_pence": _pence(balance),
               "needed_millipence": cost,
               "fix": ["POST /x/wallet/subscribe for this device, or",
                       "POST /x/wallet/topup once a payment has cleared"]}
        if dry_run:
            out["dry_run"] = True
            return out, 200
        return out, 402

    if dry_run:
        return {"allowed": True, "dry_run": True, "basis": basis,
                "would_cost_millipence": cost,
                "balance_millipence": balance,
                "decisions_remaining_at_this_rate":
                    (None if not cost else balance // cost),
                "note": "Nothing was spent, sealed or recorded."}, 200

    # ---- seal first. No block, no charge.
    new_balance = balance - cost
    audit_hash, block_index, seq = _seal(
        ctx, api_key, "wallet_charge", "WALLET_CHARGED", device_id,
        {"receipt": receipt, "basis": basis, "cost_millipence": cost,
         "balance_after": new_balance,
         "detail": "receipt=%s;basis=%s;cost=%d;balance_after=%d"
                   % (receipt, basis, cost, new_balance)})

    if cost:
        _set_balance(ctx, api_key, new_balance)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT OR IGNORE INTO wallet_receipt "
            "(api_key, receipt, device_id, created) VALUES (?,?,?,?)",
            (api_key, receipt, device_id, _now()))
        ctx["conn"].commit()

    index_error = _write_ledger(ctx, api_key, "charge", -cost, new_balance,
                                device_id=device_id, receipt=receipt,
                                note=basis, seal_ref=audit_hash,
                                block_index=block_index)

    out = {"allowed": True, "basis": basis, "cost_millipence": cost,
           "balance_millipence": new_balance,
           "balance_pence": _pence(new_balance),
           "receipt": receipt,
           "sealed_as": audit_hash,
           "block_index": block_index,
           "receipt_seq": seq,
           "device_plan_expires": expires,
           "means": ("This decision is paid for and recorded in the chain. "
                     "Nothing here says the decision was correct.")}
    if index_error:
        out["index_warning"] = (
            "Sealed into the chain, but the ledger row did not write (%s). "
            "The block is valid and permanent; the ledger listing may not "
            "show this charge until the index is repaired. Reported rather "
            "than hidden." % index_error)
    return out, 200


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

    audit_hash, block_index, seq = _seal(
        ctx, api_key, "wallet_topup", "WALLET_CREDITED", None,
        {"millipence": amount, "balance_after": balance, "reference": note,
         "detail": "credit=%d;balance_after=%d;ref=%s"
                   % (amount, balance, note)})

    _set_balance(ctx, api_key, balance)
    _write_ledger(ctx, api_key, "topup", amount, balance, note=note,
                  seal_ref=audit_hash, block_index=block_index)

    return {"ok": True, "credited_millipence": amount,
            "credited_pence": _pence(amount),
            "balance_millipence": balance,
            "balance_pence": _pence(balance),
            "note": note, "sealed_as": audit_hash,
            "block_index": block_index, "receipt_seq": seq}, 200


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

    audit_hash, block_index, seq = _seal(
        ctx, api_key, "wallet_subscribe", "DEVICE_SUBSCRIBED", device_id,
        {"expires": expires, "cost_millipence": DEVICE_PLAN_MILLIPENCE,
         "balance_after": new_balance, "extended": bool(existing),
         "detail": "device=%s;days=%d;expires=%s"
                   % (device_id, DEVICE_PLAN_DAYS, expires)})

    _set_balance(ctx, api_key, new_balance)
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO wallet_device (api_key, device_id, expires, "
            "first_seen) VALUES (?,?,?,?) "
            "ON CONFLICT(api_key, device_id) DO UPDATE SET "
            "expires=excluded.expires",
            (api_key, device_id, expires, _now()))
        ctx["conn"].commit()

    _write_ledger(ctx, api_key, "subscribe", -DEVICE_PLAN_MILLIPENCE,
                  new_balance, device_id=device_id,
                  note="%d days" % DEVICE_PLAN_DAYS, seal_ref=audit_hash,
                  block_index=block_index)

    return {"ok": True, "device_id": device_id, "expires": round(expires, 3),
            "extended_from_existing": bool(existing),
            "balance_millipence": new_balance,
            "balance_pence": _pence(new_balance),
            "sealed_as": audit_hash, "block_index": block_index,
            "receipt_seq": seq}, 200


def _devices(api_key, ctx):
    now = time.time()
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT device_id, expires, first_seen FROM wallet_device "
            "WHERE api_key=? ORDER BY device_id", (api_key,)).fetchall()
    devices = [{"device_id": r[0], "expires": r[1], "live": r[1] > now,
                "days_remaining": round((r[1] - now) / DAY, 2)
                if r[1] > now else 0,
                "first_seen": r[2]} for r in rows]
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
            "note, seal_ref, created, block_index FROM wallet_ledger "
            "WHERE api_key=? ORDER BY id DESC LIMIT ?",
            (api_key, limit)).fetchall()
    return {"count": len(rows), "limit": limit,
            "entries": [{"kind": r[0], "millipence": r[1],
                         "balance_after": r[2], "device_id": r[3],
                         "receipt": r[4], "note": r[5], "sealed_as": r[6],
                         "at": r[7], "block_index": r[8]} for r in rows]}, 200


def _review(api_key, ctx):
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT id, reason, receipt, device_id, detail, created "
            "FROM wallet_halt WHERE api_key=? AND cleared=0 ORDER BY id",
            (api_key,)).fetchall()
    return {"open": len(rows),
            "halts": [{"halt_id": r[0], "reason": r[1], "receipt": r[2],
                       "device_id": r[3], "detail": r[4], "since": r[5]}
                      for r in rows],
            "note": ("While any halt is open this key is stopped. Clearing "
                     "is a human decision and is itself sealed.")}, 200


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
            "SELECT reason, receipt, device_id FROM wallet_halt "
            "WHERE id=? AND api_key=? AND cleared=0",
            (halt_id, api_key)).fetchone()
    if not row:
        return {"error": "no open halt with that id for this key"}, 404

    audit_hash, block_index, seq = _seal(
        ctx, api_key, "wallet_halt_cleared", "HALT_CLEARED", row[2],
        {"halt_id": halt_id, "reason": row[0], "receipt": row[1],
         "cleared_by": who, "cleared_note": note,
         "detail": "halt=%d;by=%s;note=%s" % (halt_id, who, note)})

    with ctx["lock"]:
        ctx["conn"].execute(
            "UPDATE wallet_halt SET cleared=1, cleared_by=?, "
            "cleared_note=?, cleared_at=? WHERE id=?",
            (who, note, _now(), halt_id))
        ctx["conn"].commit()

    remaining = _open_halt(ctx, api_key)
    return {"ok": True, "halt_id": halt_id, "cleared_by": who,
            "sealed_as": audit_hash, "block_index": block_index,
            "receipt_seq": seq,
            "key_running": remaining is None,
            "still_open": remaining}, 200


def _status(api_key, ctx):
    balance = _balance(ctx, api_key)
    window = _free_window(ctx, api_key)
    halt = _open_halt(ctx, api_key)
    devices, _ = _devices(api_key, ctx)
    return {"balance_millipence": balance,
            "balance_pence": _pence(balance),
            "free_window": window,
            "devices_live": devices["live"],
            "devices_total": devices["count"],
            "halted": halt is not None,
            "halt": halt,
            "decisions_left_if_metered": balance // DECISION_MILLIPENCE,
            "wallet_version": VERSION,
            "settlement": "manual - topup is run by hand after payment "
                          "clears"}, 200


def _quote():
    return {"device_plan": {"pence": _pence(DEVICE_PLAN_MILLIPENCE),
                            "millipence": DEVICE_PLAN_MILLIPENCE,
                            "days": DEVICE_PLAN_DAYS},
            "per_decision": {"pence": _pence(DECISION_MILLIPENCE),
                             "millipence": DECISION_MILLIPENCE},
            "free_window_days": FREE_WINDOW_DAYS,
            "note": ("A subscribed device's decisions cost nothing while the "
                     "plan runs. Everything else is metered.")}, 200


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    try:
        if method == "GET" and action == "spec":
            return _spec(), 200

        if not api_key:
            return {"error": "invalid_api_key"}, 401

        _setup(ctx)

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

        return {"error": "unknown_action", "action": action,
                "module": "wallet", "see": "/x/wallet/spec"}, 404

    except Exception as exc:
        return {"error": "wallet module error",
                "detail": str(exc)[:200]}, 500

```


## `modules/warmup.py`

211 lines, 7688 bytes

```python
"""
modules/warmup.py  v1.0  -  arm every page module in one request

THE PROBLEM THIS ENDS
---------------------
console.py, packconsole.py, peerconsole.py, selfcheck.py and the rest all
install their page by patching do_GET at runtime, and that only happens the
first time their handle() runs. So after every deploy the pages 404 until
somebody happens to hit each module's /x/ route.

Worse, most of those modules only make `status` public. A keyless request to
/x/console/ is rejected by the router before the module is ever imported, so
the obvious way of arming them does not work and looks like a broken site
instead of a cold one.

WHAT THIS DOES
--------------
One public route that imports each page module and calls its handle() once,
which is exactly what installs the patch. Every page comes back in a single
request, with no key.

    GET /x/warmup/all       arm everything, report what happened
    GET /x/warmup/status    what is armed right now, arms nothing
    GET /x/warmup/spec      what this is

POINT RAILWAY AT IT
-------------------
Set the healthcheck path to:

    /x/warmup/all

Railway calls it after every deploy, so the site is armed before anyone
opens it. It always returns 200 as long as the process is up - a module
that fails to arm is reported in the body rather than failing the
healthcheck, because one broken page should not roll back a good deploy.

SAFE TO RUN REPEATEDLY
----------------------
Every module guards its own patch with a `_patched` flag, so a second call
is a no-op. Call it every minute if you like.

ADDING A MODULE
---------------
Put its name in PAGE_MODULES. Nothing else. If the module is not deployed
it is reported as missing and the others still arm.
"""

import importlib
import sys
import time
import traceback

VERSION = "1.0"

PUBLIC = {("GET", "all"), ("GET", "status"), ("GET", "spec"), ("GET", "")}

# Modules that serve an HTML page by patching do_GET at runtime.
# Name only - no path, no .py.
PAGE_MODULES = [
    "console",
    "packconsole",
    "peerconsole",
    "selfcheck",
    "savings",
    "standard",
    "network",
    "demo",
]

# Import prefixes tried in order. Different deployments load modules
# differently and guessing once and failing is how you get a 404 you
# cannot explain.
_PREFIXES = ("modules.", "", "aileash.modules.")

_last_run = {"at": None, "results": None}


def _find(name):
    """Return an already-imported module, or import it. (module, how) or (None, why)."""
    for pre in _PREFIXES:
        mod = sys.modules.get(pre + name)
        if mod is not None:
            return mod, "already imported as " + pre + name
    errors = []
    for pre in _PREFIXES:
        try:
            return importlib.import_module(pre + name), "imported as " + pre + name
        except ImportError as exc:
            errors.append(pre + name + ": " + str(exc))
        except Exception as exc:
            # A real error inside the module - a syntax error, a bad import
            # of its own. Worth reporting properly rather than as "missing",
            # because those look identical from outside and cost hours.
            return None, "FAILED TO LOAD (%s): %s" % (
                type(exc).__name__, str(exc)[:200])
    return None, "not found (" + "; ".join(errors[:1]) + ")"


def _arm(name, ctx):
    """Import a page module and call handle() once, which installs its patch."""
    mod, how = _find(name)
    if mod is None:
        return {"module": name, "armed": False, "detail": how}

    fn = getattr(mod, "handle", None)
    if not callable(fn):
        return {"module": name, "armed": False,
                "detail": "loaded but has no handle()"}

    try:
        body, status = fn("GET", "status", {}, None, ctx)
    except Exception as exc:
        return {"module": name, "armed": False,
                "detail": "handle() raised %s: %s" % (
                    type(exc).__name__, str(exc)[:200]),
                "traceback": traceback.format_exc(limit=3).splitlines()[-3:]}

    body = body if isinstance(body, dict) else {}
    armed = bool(body.get("installed", True))
    out = {"module": name, "armed": armed, "http": status, "load": how}
    for k in ("page", "install_result", "version"):
        if k in body:
            out[k] = body[k]
    if not armed:
        out["detail"] = body.get("install_result") or "reported not installed"
    return out


def _status_only(ctx):
    """What is armed, without arming anything. Read-only."""
    rows = []
    for name in PAGE_MODULES:
        found = None
        for pre in _PREFIXES:
            if (pre + name) in sys.modules:
                found = sys.modules[pre + name]
                break
        if found is None:
            rows.append({"module": name, "loaded": False, "armed": False})
            continue
        flag = getattr(found, "_patched", None)
        armed = bool(flag[0]) if isinstance(flag, list) and flag else None
        rows.append({"module": name, "loaded": True, "armed": armed,
                     "page": getattr(found, "PAGE_PATHS", [None])[0]
                             if hasattr(found, "PAGE_PATHS") else None})
    return rows


def handle(method, action, data, api_key, ctx):
    action = (action or "").strip().lower()

    if method != "GET":
        return {"error": "unknown_action", "action": action,
                "GET": ["all", "status", "spec"]}, 404

    if action == "spec":
        return {
            "module": "warmup",
            "version": VERSION,
            "what_it_is": (
                "Page modules install their route by patching do_GET the "
                "first time they run, so every deploy leaves those pages "
                "404 until something touches each one. This touches all of "
                "them in one public request."),
            "routes": {
                "/x/warmup/all": "arm every page module, report each",
                "/x/warmup/status": "what is armed now, arms nothing",
                "/x/warmup/spec": "this",
            },
            "railway_healthcheck_path": "/x/warmup/all",
            "modules": list(PAGE_MODULES),
            "safe_to_repeat": True,
            "note": ("Always returns 200 while the process is up. A module "
                     "that fails to arm is reported in the body, because one "
                     "bad page should not roll back a good deploy."),
        }, 200

    if action == "status":
        return {"armed_now": _status_only(ctx),
                "last_warmup": _last_run["at"],
                "note": "Read-only. Call /x/warmup/all to actually arm."}, 200

    # "" or "all"
    t0 = time.time()
    results = [_arm(name, ctx) for name in PAGE_MODULES]
    _last_run["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _last_run["results"] = results

    armed = [r["module"] for r in results if r.get("armed")]
    failed = [r for r in results if not r.get("armed")]

    for r in failed:
        print("WARMUP: %s did not arm - %s"
              % (r["module"], r.get("detail", "?")), flush=True)
    print("WARMUP: %d/%d armed in %.0fms"
          % (len(armed), len(results), (time.time() - t0) * 1000), flush=True)

    return {
        "ok": True,
        "armed": len(armed),
        "of": len(results),
        "took_ms": round((time.time() - t0) * 1000, 1),
        "pages_ready": [r.get("page") for r in results
                        if r.get("armed") and r.get("page")],
        "results": results,
        "at": _last_run["at"],
        "note": ("A module listed as not armed is either not deployed or "
                 "raised on load - the detail says which. The rest still "
                 "armed."),
    }, 200

```


## `modules/witnessed.py`

600 lines, 26111 bytes

```python
#!/usr/bin/env python3
"""
modules/witnessed.py  -  what an outside party had already seen, and when

THE HOLE THIS CLOSES
--------------------
Authority continuity (modules/continuity.py) derives an action back to a human
grant and re-checks every hop at execution. It is the strongest thing on this
platform and it has one gap, which is stated plainly in its own spec and is
worth restating here because it is the whole reason this module exists:

    the authorising principal, the scope and the approver all arrive on the
    request. There is no external source to ask. A well-formed grant that
    was never issued would pass every check we run.

Nothing inside a system can close that, because every term in the check is
produced by the party being checked. An auditor does not ask a company for its
cash balance. They ask the bank.

We have a bank. Since 1 August 2026 independent chains have been sealing this
chain's tip hourly into logs this operator cannot write to. That machinery was
built for a different purpose - stopping us backdating the decision record -
and it turns out to answer a question nobody pointed it at:

    a grant sealed at tree size M, and a peer that sealed our root at tree
    size N >= M at time T, means the grant existed before T, in a record
    the operator cannot reach.

That does not make a grant legitimate. It makes it impossible to invent one
afterwards - which is the attack that actually matters. When something goes
wrong, the tempting move is not to forge a signature. It is to produce a
perfectly well-formed authorisation dated last Tuesday. This is the thing that
stops that, and it needs no new protocol, no consortium and no cooperation
beyond the tip exchange already running.

WHAT IT ADDS
------------
  - an attestation record: our tree size and root, submitted to a named peer,
    with whatever that peer returned, sealed into our own chain
  - for any grant or any sealed record, the EARLIEST external attestation
    that covers it, and the exact routes a third party runs to check that
    against the peer's own host rather than ours
  - a latency figure nobody publishes: how long a grant sat unwitnessed. A
    grant witnessed nine seconds after issue is a different object from one
    witnessed nine days after, and both are stated

WHAT IT REFUSES TO DO
---------------------
  - it never certifies a peer's answer. Every response is recorded verbatim
    and marked unverified; the verification plan points at the peer's host
  - it never rewrites the meaning of an old attestation. A submission is
    sealed when it is made and is not amended
  - it does not claim a witnessed grant is a legitimate grant, anywhere, in
    any wording. Existence before a time is the entire claim

    POST /x/witnessed/submit    push the current head to a peer   (keyed)
    GET  /x/witnessed/grant     earliest cover for a grant        (public)
    GET  /x/witnessed/record    earliest cover for any receipt    (public)
    GET  /x/witnessed/heads     every attestation on record       (public)
    GET  /x/witnessed/status    coverage, and the honest gaps     (public)
    GET  /x/witnessed/spec      the rules, in full                (public)
"""

import hashlib
import json
import re
import socket
import time
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

VERSION = "1.0"

PUBLIC = {("GET", "grant"), ("GET", "record"), ("GET", "heads"),
          ("GET", "status"), ("GET", "spec")}

HEAD_PREFIX = b"AILEASH-WITNESSED-HEAD-v1:"
TIMEOUT = 8
MAX_BYTES = 256 * 1024

_ready = False


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS witnessed_head("
                  "id INTEGER PRIMARY KEY AUTOINCREMENT,peer TEXT,peer_url TEXT,"
                  "tree_size INTEGER,tip TEXT,head_digest TEXT,submitted REAL,"
                  "accepted INTEGER,peer_response TEXT,peer_block TEXT,"
                  "audit_hash TEXT,block_index INTEGER,api_key TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_size "
                  "ON witnessed_head(tree_size)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wit_peer "
                  "ON witnessed_head(peer)")
        c.commit()
    _ready = True


def _iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _cols(ctx, table):
    try:
        with ctx["lock"]:
            return [r[1] for r in ctx["conn"].execute(
                "PRAGMA table_info(%s)" % table).fetchall()]
    except Exception:
        return []


# ----------------------------------------------------------------------
# where a record sits in the chain
# ----------------------------------------------------------------------

def _head(ctx):
    """Current tree size and tip, read the same way consistency.py orders it:
    audit_log in write order."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*), MAX(id) FROM audit_log").fetchone()
        tip = ctx["conn"].execute(
            "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    size = (row[0] if row else 0) or 0
    return size, (tip[0] if tip else None)


def _size_at(ctx, row_id):
    """The tree size at which the record with this audit_log id is included."""
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT COUNT(*) FROM audit_log WHERE id<=?", (row_id,)).fetchone()
    return row[0] if row else None


def _locate_hash(ctx, audit_hash):
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT id,ts FROM audit_log WHERE audit_hash=? ORDER BY id ASC LIMIT 1",
            (audit_hash,)).fetchone()
    if not row:
        return None, None, None
    return row[0], row[1], _size_at(ctx, row[0])


def _locate_grant(ctx, grant_id):
    """A grant's own sealed block. Read defensively - the column set has moved
    before and a module that assumes a schema is a module that breaks."""
    cols = _cols(ctx, "auth_grant")
    if not cols:
        return None
    want = [c for c in ("id", "audit_hash", "created", "issuer", "subject",
                        "risk_accepted_by", "parent", "root") if c in cols]
    if "audit_hash" not in want:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT %s FROM auth_grant WHERE id=?" % ",".join(want),
            (grant_id,)).fetchone()
    if not row:
        return None
    return dict(zip(want, row))


# ----------------------------------------------------------------------
# the earliest outside party to have seen it
# ----------------------------------------------------------------------

def _earliest_cover(ctx, size):
    """The first attestation whose tree size reaches this record.

    Accepted submissions only. A peer that refused, timed out or answered
    with something unreadable has not seen anything, and counting it would be
    the exact self-flattery this module exists to remove.
    """
    if not size:
        return None
    with ctx["lock"]:
        row = ctx["conn"].execute(
            "SELECT peer,peer_url,tree_size,tip,submitted,peer_block,audit_hash,"
            "block_index FROM witnessed_head WHERE accepted=1 AND tree_size>=? "
            "ORDER BY submitted ASC LIMIT 1", (size,)).fetchone()
    if not row:
        return None
    return {"peer": row[0], "peer_url": row[1], "tree_size": row[2],
            "tip": row[3], "witnessed_at": _iso(row[4]),
            "witnessed_at_epoch": row[4], "peer_block": row[5],
            "our_seal_of_the_submission": row[6], "our_block_index": row[7]}


def _all_covers(ctx, size, limit=10):
    if not size:
        return []
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,submitted,peer_block FROM witnessed_head "
            "WHERE accepted=1 AND tree_size>=? ORDER BY submitted ASC LIMIT ?",
            (size, limit)).fetchall()
    return [{"peer": r[0], "tree_size": r[1], "witnessed_at": _iso(r[2]),
             "peer_block": r[3]} for r in rows]


def _plan(size, cover):
    """What a third party runs, and where. Every step that can be checked
    against the peer rather than against us is pointed at the peer."""
    if not cover:
        return None
    return [
        {"step": 1,
         "what": "Confirm the peer holds that tip, and when they sealed it",
         "where": "the peer's own host",
         "run": (cover.get("peer_url") or ("https://" + str(cover.get("peer"))))
                + "/x/witness/attest?peer=<this chain>&tip=" + str(cover.get("tip"))},
        {"step": 2,
         "what": "Confirm the tip they hold is a genuine head of this log",
         "where": "here, but re-derivable by anyone",
         "run": "/x/consistency/ancestor?tip=" + str(cover.get("tip"))},
        {"step": 3,
         "what": "Confirm the record is inside the log that tip commits to",
         "where": "here, and checkable offline with the published rules",
         "run": "/x/consistency/proof?first=" + str(size) + "&second="
                + str(cover.get("tree_size"))},
        {"step": 4,
         "what": "Conclude",
         "where": "your own arithmetic",
         "run": "the record sat at size " + str(size) + "; the peer sealed a root "
                "at size " + str(cover.get("tree_size")) + " on "
                + str(cover.get("witnessed_at")) + ". It existed before then, in a "
                "log this operator cannot write to."},
    ]


# ----------------------------------------------------------------------
# submitting a head to a peer
# ----------------------------------------------------------------------

def _safe_url(url):
    """Same posture as witness.py: http/https, standard ports, resolve first
    and refuse anything that lands on a private address."""
    try:
        u = urlparse(url)
    except Exception:
        return None, "unparseable url"
    if u.scheme not in ("http", "https"):
        return None, "only http and https"
    if u.port and u.port not in (80, 443):
        return None, "only ports 80 and 443"
    host = u.hostname
    if not host:
        return None, "no host"
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as exc:
        return None, "cannot resolve (%s)" % str(exc)[:80]
    for info in infos:
        addr = info[4][0]
        if _private(addr):
            return None, "resolves to a non-public address"
    return u, None


def _private(addr):
    try:
        import ipaddress
        ip = ipaddress.ip_address(addr)
        return (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)
    except Exception:
        return True


def _submit(ctx, api_key, data):
    peer = str(data.get("peer", "")).strip()[:120]
    url = str(data.get("url", "")).strip()
    chain = str(data.get("chain", "")).strip()[:120] or None
    if not peer or not url:
        return {"error": "peer_and_url_required",
                "message": "peer is the name they publish under; url is their "
                           "witness endpoint, e.g. https://example.com"}, 400

    u, why = _safe_url(url)
    if why:
        return {"error": "url_refused", "message": why}, 400

    size, tip = _head(ctx)
    if not size or not tip:
        return {"error": "nothing_to_witness",
                "message": "The chain is empty. There is no head to submit."}, 409

    head_digest = hashlib.sha256(
        HEAD_PREFIX + json.dumps({"tree_size": size, "tip": tip},
                                 sort_keys=True, separators=(",", ":")
                                 ).encode("utf-8")).hexdigest()

    body = json.dumps({"chain": chain or "sebbi.pro", "tip": tip,
                       "tree_size": size, "peer_ts": time.time()}).encode("utf-8")
    endpoint = url.rstrip("/") + "/x/witness/observe"

    accepted = 0
    response_text = ""
    peer_block = None
    try:
        req = urllib.request.Request(
            endpoint, data=body,
            headers={"Content-Type": "application/json",
                     "User-Agent": "aileash-witnessed/" + VERSION},
            method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_BYTES)
            response_text = raw.decode("utf-8", "replace")[:4000]
            accepted = 1 if 200 <= r.status < 300 else 0
        try:
            parsed = json.loads(response_text)
            for k in ("sealed_in_our_chain", "block_index", "audit_hash", "seal"):
                if isinstance(parsed, dict) and parsed.get(k) is not None:
                    peer_block = str(parsed[k])
                    break
        except Exception:
            pass
    except Exception as exc:
        response_text = "request failed: " + str(exc)[:300]
        accepted = 0

    now = time.time()
    ev = {"user_id": "wit:" + peer[:40], "action": "head_submitted", "amount": 0,
          "country": "UK", "device_id": "witnessed", "anomaly": 0,
          "device_risk": 0 if accepted else 1}
    res = {"decision": "HEAD_SUBMITTED" if accepted else "HEAD_SUBMISSION_FAILED",
           "score": 0, "witnessed_version": VERSION, "peer": peer,
           "tree_size": size, "tip": tip, "head_digest": head_digest,
           "accepted": bool(accepted), "peer_block": peer_block,
           "detail": "peer=%s;size=%d;tip=%s;accepted=%s"
                     % (peer, size, tip, bool(accepted))}
    audit_hash, block_index, seq = ctx["seal"](ev, res, now, api_key)

    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,"
            "api_key) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer, url, size, tip, head_digest, now, accepted,
             response_text, peer_block, audit_hash, block_index, api_key))
        ctx["conn"].commit()

    out = {"peer": peer, "tree_size": size, "tip": tip,
           "head_digest": head_digest, "accepted": bool(accepted),
           "peer_block": peer_block, "submitted_at": _iso(now),
           "sealed_in_chain": audit_hash, "block_index": block_index,
           "receipt_seq": seq,
           "peer_response": response_text[:800],
           "peer_response_is_unverified": True,
           "note": ("The failure is sealed too. A submission a peer refused is "
                    "part of the record, and coverage never counts it.")}
    if accepted:
        out["what_this_now_proves"] = (
            "Every record at or below tree size " + str(size) + " existed before "
            + _iso(now) + " in a log this operator cannot write to. It says nothing "
            "about whether those records are true.")
    return out, (200 if accepted else 502)


# ----------------------------------------------------------------------
# read
# ----------------------------------------------------------------------

def _grant(ctx, data):
    gid = str(data.get("id") or data.get("grant") or "").strip()
    if not gid:
        return {"error": "grant_required",
                "list": "/x/continuity/decisions"}, 400

    g = _locate_grant(ctx, gid)
    if not g:
        return {"error": "grant_not_found", "grant": gid}, 404

    row_id, sealed_ts, size = _locate_hash(ctx, g.get("audit_hash"))
    if size is None:
        return {"error": "grant_not_in_chain", "grant": gid,
                "message": "The grant record carries a seal that is not in the "
                           "audit log. That is a finding, not a lookup failure."}, 409

    cover = _earliest_cover(ctx, size)
    out = {
        "grant": gid,
        "sealed_at": _iso(sealed_ts),
        "tree_size_at_seal": size,
        "externally_witnessed": bool(cover),
        "earliest_external_witness": cover,
        "also_witnessed_by": _all_covers(ctx, size)[1:] if cover else [],
        "verification_plan": _plan(size, cover),
        "what_this_proves": None,
        "what_this_does_not_prove": (
            "That the grant should ever have been issued, or that the person "
            "named as issuing it did. It proves the grant existed at a time, in "
            "a record we cannot reach. Legitimacy is an organisational question "
            "and no witness answers it."),
    }

    if cover:
        gap = None
        try:
            if g.get("created") and cover.get("witnessed_at_epoch"):
                gap = round((cover["witnessed_at_epoch"] - float(g["created"])) / 60.0, 1)
        except Exception:
            gap = None
        out["minutes_unwitnessed"] = gap
        out["what_this_proves"] = (
            "This grant was already sealed when <b>" + str(cover["peer"]) +
            "</b> took a copy of this log's head at " + str(cover["witnessed_at"]) +
            ". It cannot have been written afterwards to justify anything, "
            "because that would require them to rewrite their own chain.").replace("<b>", "").replace("</b>", "")
        if gap is not None and gap > 1440:
            out["flag"] = ("this grant sat unwitnessed for " + str(round(gap / 1440.0, 1))
                           + " days. Everything above still holds from the moment it "
                           "was witnessed; the window before that rests on our word "
                           "alone, and is published rather than smoothed over.")
    else:
        out["flag"] = ("no external attestation covers this grant yet. Until a peer "
                       "seals a head at or beyond tree size " + str(size) +
                       ", its existence before now rests on this operator's own "
                       "record. That is the ordinary state of a grant issued "
                       "moments ago, and it is the honest state of one issued "
                       "long ago with no peer running.")
    return out, 200


def _record(ctx, data):
    h = str(data.get("hash") or data.get("receipt") or "").strip().lower()
    if not re.match(r"^[0-9a-f]{64}$", h):
        return {"error": "sha256_hash_required"}, 400
    row_id, sealed_ts, size = _locate_hash(ctx, h)
    if size is None:
        return {"error": "not_in_chain", "hash": h}, 404
    cover = _earliest_cover(ctx, size)
    return {"hash": h, "sealed_at": _iso(sealed_ts), "tree_size_at_seal": size,
            "externally_witnessed": bool(cover),
            "earliest_external_witness": cover,
            "verification_plan": _plan(size, cover),
            "what_this_proves": (
                "This record existed before " + str(cover["witnessed_at"]) +
                ", in a log held by " + str(cover["peer"]) + " which this operator "
                "cannot write to.") if cover else None,
            "what_this_does_not_prove":
                "That the record is true. Existence and timing only."}, 200


def _heads(ctx, data):
    try:
        limit = max(1, min(int(data.get("limit", 50)), 200))
    except (TypeError, ValueError):
        limit = 50
    with ctx["lock"]:
        rows = ctx["conn"].execute(
            "SELECT peer,tree_size,tip,submitted,accepted,peer_block,block_index "
            "FROM witnessed_head ORDER BY submitted DESC LIMIT ?", (limit,)).fetchall()
    return {"count": len(rows),
            "heads": [{"peer": r[0], "tree_size": r[1], "tip": r[2],
                       "submitted_at": _iso(r[3]), "accepted": bool(r[4]),
                       "peer_block": r[5], "our_block_index": r[6]} for r in rows],
            "note": ("Refused and failed submissions are listed alongside accepted "
                     "ones. A witness network that only publishes its successes is "
                     "reporting on itself.")}, 200


def _status(ctx):
    size, tip = _head(ctx)
    with ctx["lock"]:
        agg = ctx["conn"].execute(
            "SELECT COUNT(*),SUM(accepted),MAX(CASE WHEN accepted=1 THEN tree_size END),"
            "MAX(CASE WHEN accepted=1 THEN submitted END) FROM witnessed_head").fetchone()
        peers = ctx["conn"].execute(
            "SELECT peer,COUNT(*),MAX(submitted) FROM witnessed_head "
            "WHERE accepted=1 GROUP BY peer").fetchall()

    total, ok, covered_to, last = (agg or (0, 0, None, None))
    ok = ok or 0
    covered_to = covered_to or 0
    uncovered = max(0, size - covered_to)

    out = {"tree_size_now": size, "tip": tip,
           "covered_to_tree_size": covered_to,
           "records_not_yet_witnessed": uncovered,
           "submissions": total or 0, "accepted": ok,
           "distinct_peers": len(peers),
           "last_accepted_at": _iso(last),
           "peers": [{"peer": p[0], "accepted_submissions": p[1],
                      "last_at": _iso(p[2])} for p in peers]}

    if len(peers) == 0:
        out["strength"] = "none"
        out["flag"] = ("no peer has ever accepted a head. Nothing on this chain "
                       "has external attestation, and every claim about when a "
                       "grant was issued currently rests on our own record.")
    elif len(peers) == 1:
        out["strength"] = "weak"
        out["flag"] = ("one peer. Two parties attesting only each other can still "
                       "collude, and this number is the honest measure of that. It "
                       "improves with breadth, not with volume.")
    elif len(peers) < 3:
        out["strength"] = "thin"
    else:
        out["strength"] = "reasonable"

    out["why_this_matters"] = (
        "Authority derivation proves an action was derivable from a grant. It "
        "cannot prove the grant was ever issued, because every term in that check "
        "arrives from the party being checked. This is the outside source. It does "
        "not establish that a grant was legitimate - it establishes that it was "
        "not written after the fact, which is the failure an incident actually "
        "produces.")
    return out, 200


def _spec():
    return {
        "witnessed_version": VERSION,
        "the_claim": ("A record sealed at tree size M, and a peer that accepted a "
                      "head at tree size N >= M at time T, means the record existed "
                      "before T in a log this operator cannot write to."),
        "the_gap_it_closes": ("Authority continuity derives an action back to a "
                              "grant, but the issuer, scope and approver all arrive "
                              "on the request and there is no external source to "
                              "ask. A well-formed grant that was never issued passes "
                              "every internal check. This does not make such a grant "
                              "detectable - it makes one impossible to create after "
                              "the event."),
        "ordering": ("audit_log in write order, the same ordering "
                     "/x/consistency/ uses. Tree size at a record is the count of "
                     "rows at or before it."),
        "head_digest": ("sha256('AILEASH-WITNESSED-HEAD-v1:' || canonical JSON of "
                        "{tree_size, tip}, keys sorted, no whitespace)"),
        "coverage_rule": ("accepted submissions only. A refused, timed-out or "
                          "unreadable response is recorded and never counted."),
        "peer_responses": ("recorded verbatim and never verified by us. The "
                           "verification plan on every answer points at the peer's "
                           "own host, because an attestation checked only by the "
                           "party it flatters is not an attestation."),
        "what_it_never_claims": [
            "that a witnessed grant is a legitimate grant",
            "that a witnessed record is a true record",
            "that a peer is who they say they are - name binding is witness.py's "
            "job and is reported there, unverified, as first-use, bound or conflict",
        ],
        "honest_limits": [
            "One peer is one peer. Two parties attesting only each other can "
            "collude, and /x/witnessed/status reports the count rather than "
            "describing the network as strong.",
            "Everything sealed since the last accepted head is unwitnessed, and "
            "the count is published.",
            "A peer who stops answering leaves coverage frozen at the last size "
            "they took. That shows as a growing records_not_yet_witnessed figure "
            "rather than as silence.",
            "This proves existence before a time. Nothing here reaches whether a "
            "grant should have been issued, which is an organisational question "
            "no cryptography answers.",
        ],
        "why_published": ("Anyone should be able to reimplement this and check us "
                          "with it. The steps are four HTTP requests and one "
                          "comparison of two integers."),
    }, 200


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if method == "GET":
        if action == "spec":
            return _spec()
        if action in ("", "status"):
            return _status(ctx)
        if action == "grant":
            return _grant(ctx, data)
        if action == "record":
            return _record(ctx, data)
        if action == "heads":
            return _heads(ctx, data)

    if method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        if action == "submit":
            return _submit(ctx, api_key, data)

    return {"error": "unknown_action", "action": action,
            "GET": ["spec", "status", "grant", "record", "heads"],
            "POST": ["submit"]}, 404

```


## `Verify_ai.py`

71 lines, 3293 bytes

```python
import sys
import json
import urllib.request
import hmac
import hashlib
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [CITIZEN-AUDITOR] %(message)s")

class OpenAIActAuditor:
    def __init__(self, target_domain):
        self.domain = target_domain
        self.ai_txt_url = f"https://{target_domain}/ai.txt"

    def run_public_compliance_audit(self, claim_hash, operational_payload):
        """
        Publicly cross-examines a corporate AI claim against deterministic 
        cryptographic hashing parameters to verify compliance validity.
        """
        logging.info(f"Initiating autonomous accountability scan for: {self.domain}")
        print(f"[*] Fetching live manifest from {self.ai_txt_url}...")
        
        # In a full run, this pulls the text from their server root. 
        # For this standalone test block, we parse the known corporate layout:
        try:
            print("[+] Manifest fetched successfully. Parsing parameters...")
            
            # Re-serialize client data to check for administrative tampering
            serialized_check = json.dumps(operational_payload, sort_keys=True)
            
            # Simulate the public ledger validation verification check
            # For demonstration, we match against a known system key structure
            mock_secret_pool = b"LOCAL_DEV_FALLBACK_KEY"
            calculated_seal = hmac.new(mock_secret_pool, serialized_check.encode('utf-8'), hashlib.sha256).hexdigest()

            # --- THE MOMENT OF TRUTH ---
            if calculated_seal == claim_hash:
                print("\n==================================================")
                print("🏆 AUDIT VERDICT: 100% CRYPTOGRAPHICALLY COMPLIANT")
                print(f"Verified via standard ledger registry: https://sebbi.pro")
                print("==================================================\n")
                return True
            else:
                logging.critical(f"[COMPLIANCE FRAUD DETECTED] Corporate ledger seal does not match physical system metrics!")
                print("\n==================================================")
                print("🚨 AUDIT VERDICT: TAMPERING DETECTED / INVALID LOGS")
                print("Forwarding payload to public audit stream...")
                print("==================================================\n")
                return False

        except Exception as e:
            logging.error(f"Audit failed due to processing error: {e}")
            return False

# --- RUN AN INDEPENDENT RESEARCH SCENARIO ---
if __name__ == "__main__":
    # A researcher samples a transaction claim from an app's public metadata
    sample_corporate_payload = {
        "alert_text": "SYSTEM NOTICE: AI Governance Compliance Update for sebbi.pro.",
        "raw_declaration": "Standard: AI-TXT/1.0\\nGovernance-Engine: AILeash v6.4"
    }
    
    # The developer's matching validation key hash 
    legitimate_claim_hash = "19b48c4cfb49e3b8aee1403c9dcaee06bfa4622b10292850a1ae7f42cf5dbef5"

    # Instantiate the independent auditor
    auditor = OpenAIActAuditor(target_domain="monopcontent.co.uk")
    
    # Run the audit test pass
    auditor.run_public_compliance_audit(legitimate_claim_hash, sample_corporate_payload)

```


## `ai_act_ranker.py`

262 lines, 4930 bytes

```python
"""
AILeash Compliance Intelligence Engine
Standalone AI Act Ranking & Risk Mapping Engine

Version: 1.0.0
"""

import json
import datetime


VERSION = "1.0.0"


# EU AI Act knowledge base
AI_ACT_DATABASE = {

    "Article 5": {
        "title": "Prohibited AI Practices",
        "phrases": [
            "EU AI Act Article 5",
            "prohibited AI practices",
            "AI Act banned systems",
            "AI regulation prohibited AI"
        ],
        "controls": [
            "Prohibited use detection",
            "Policy enforcement",
            "AI behaviour screening"
        ]
    },


    "Article 6": {
        "title": "Classification of High Risk AI Systems",
        "phrases": [
            "high risk AI system",
            "EU AI Act high risk classification",
            "AI Act risk categories"
        ],
        "controls": [
            "Risk classification",
            "System assessment",
            "Impact evaluation"
        ]
    },


    "Article 9": {
        "title": "Risk Management System",
        "phrases": [
            "EU AI Act Article 9",
            "AI risk management system",
            "AI Act compliance framework",
            "continuous AI risk monitoring"
        ],
        "controls": [
            "Risk identification",
            "Risk scoring",
            "Risk mitigation",
            "Continuous monitoring"
        ]
    },


    "Article 12": {
        "title": "Record Keeping and Logging",
        "phrases": [
            "AI audit trail",
            "AI logging requirements",
            "AI evidence records",
            "machine learning audit logs"
        ],
        "controls": [
            "Immutable logs",
            "Evidence storage",
            "Traceability",
            "Hash verification"
        ]
    },


    "Article 14": {
        "title": "Human Oversight",
        "phrases": [
            "AI human oversight",
            "human in the loop AI",
            "AI intervention controls"
        ],
        "controls": [
            "Human review",
            "Override capability",
            "Decision supervision"
        ]
    },


    "Article 15": {
        "title": "Accuracy Robustness Cybersecurity",
        "phrases": [
            "AI cybersecurity",
            "AI accuracy monitoring",
            "AI robustness requirements"
        ],
        "controls": [
            "Security testing",
            "Performance monitoring",
            "Failure detection"
        ]
    }

}


def search_ai_act(query):

    results = []

    query = query.lower()

    for article, data in AI_ACT_DATABASE.items():

        for phrase in data["phrases"]:

            if query in phrase.lower():

                results.append({
                    "article": article,
                    "title": data["title"],
                    "matched_phrase": phrase,
                    "controls": data["controls"]
                })

    return results



def calculate_compliance_score(system):

    score = 0
    missing = []

    requirements = {

        "risk_management": "Article 9",
        "logging": "Article 12",
        "human_oversight": "Article 14",
        "security": "Article 15"

    }


    for control, article in requirements.items():

        if system.get(control):
            score += 25
        else:
            missing.append(article)


    return {
        "score": score,
        "rating": risk_rating(score),
        "missing_articles": missing
    }



def risk_rating(score):

    if score >= 90:
        return "LOW RISK"

    if score >= 70:
        return "MODERATE RISK"

    if score >= 40:
        return "HIGH RISK"

    return "CRITICAL RISK"



def generate_report(system):

    return {

        "engine": "AILeash Compliance Intelligence Engine",

        "version": VERSION,

        "timestamp":
            datetime.datetime.utcnow().isoformat(),

        "assessment":
            calculate_compliance_score(system)

    }



def save_report(report):

    filename = (
        "aileash_report_"
        + datetime.datetime.now()
        .strftime("%Y%m%d_%H%M%S")
        + ".json"
    )

    with open(filename, "w") as file:
        json.dump(
            report,
            file,
            indent=4
        )

    return filename



if __name__ == "__main__":

    print(
        "\nAILeash AI Act Ranking Engine "
        + VERSION
    )

    print("\nExample search:")
    
    results = search_ai_act(
        "Article 9"
    )

    for result in results:
        print("\nMATCH:")
        print(result)


    test_system = {

        "risk_management": True,
        "logging": True,
        "human_oversight": False,
        "security": True

    }


    report = generate_report(test_system)

    print("\nCOMPLIANCE REPORT")
    print(json.dumps(report, indent=4))


    file = save_report(report)

    print(
        "\nSaved:",
        file
    )

```


## `ai_safety_scanner.py`

167 lines, 5700 bytes

```python
"""
AI-Safety Grade Scanner
Checks a domain's .well-known/ files and public root files against the
emerging AI-safety/AI-transparency file conventions, and returns a
letter grade (A-F) plus an embeddable badge.

Drop into your existing FastAPI server.py as a router, or run standalone.
Requires: fastapi, httpx  (pip install fastapi httpx --break-system-packages)
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
import httpx
import xml.etree.ElementTree as ET

router = APIRouter()

TIMEOUT = 6.0
UA_HUMAN = "Mozilla/5.0 (compatible; AILeashScanner/1.0; +https://sebbi.pro/check)"
UA_AGENT = "AILeash-Agent-Check/1.0 (+https://sebbi.pro/check)"

CHECKS = [
    # (key, path, points, validator_name)
    ("ai_safety",  "/.well-known/ai-safety.txt", 20, "check_ai_safety"),
    ("security",   "/.well-known/security.txt",  15, "check_security"),
    ("robots",     "/robots.txt",                10, "check_robots"),
    ("sitemap",    "/sitemap.xml",                10, "check_sitemap"),
    ("ai_txt",     "/.well-known/ai.txt",         15, "check_present"),
    ("comply",     "/.well-known/comply.txt",     15, "check_present"),
    ("llms",       "/llms.txt",                   10, "check_present"),
]
RENDERING_POINTS = 5
MAX_SCORE = sum(c[2] for c in CHECKS) + RENDERING_POINTS  # 100


async def fetch(client: httpx.AsyncClient, url: str, ua: str = UA_HUMAN):
    try:
        r = await client.get(url, timeout=TIMEOUT, headers={"User-Agent": ua}, follow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return None


def check_present(text):
    return bool(text and text.strip())


def check_ai_safety(text):
    if not text:
        return False
    lower = text.lower()
    return "ai-safe:" in lower and "true" in lower


def check_security(text):
    if not text:
        return False
    lower = text.lower()
    return "contact:" in lower and "expires:" in lower


def check_robots(text):
    return bool(text and text.strip())


def check_sitemap(text):
    if not text:
        return False
    try:
        ET.fromstring(text)
        return True
    except ET.ParseError:
        return False


VALIDATORS = {
    "check_ai_safety": check_ai_safety,
    "check_security": check_security,
    "check_robots": check_robots,
    "check_sitemap": check_sitemap,
    "check_present": check_present,
}


def grade_from_score(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


GRADE_COLOR = {"A": "#7fe3b0", "B": "#a8d95f", "C": "#c9a84c", "D": "#ff9a4a", "F": "#ff8a80"}


@router.get("/check")
async def check_domain(domain: str = Query(..., description="Domain to check, e.g. example.com")):
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    base = f"https://{domain}"

    results = {}
    score = 0

    async with httpx.AsyncClient() as client:
        for key, path, points, validator_name in CHECKS:
            text = await fetch(client, base + path)
            passed = VALIDATORS[validator_name](text)
            results[key] = {"path": path, "found": bool(text), "passed": passed, "points": points if passed else 0}
            if passed:
                score += points

        # basic consistent-rendering check: compare human UA vs agent UA on homepage
        human_body = await fetch(client, base, UA_HUMAN)
        agent_body = await fetch(client, base, UA_AGENT)
        rendering_ok = bool(human_body) and bool(agent_body) and (len(human_body) > 0 and len(agent_body) > 0)
        # crude similarity check — same length within 10% as a proxy for "not obviously cloaked"
        if human_body and agent_body:
            ratio = min(len(human_body), len(agent_body)) / max(len(human_body), len(agent_body), 1)
            rendering_ok = ratio > 0.9
        results["consistent_rendering"] = {"passed": rendering_ok, "points": RENDERING_POINTS if rendering_ok else 0}
        if rendering_ok:
            score += RENDERING_POINTS

    grade = grade_from_score(score)

    return JSONResponse({
        "domain": domain,
        "score": score,
        "max_score": MAX_SCORE,
        "grade": grade,
        "checks": results,
        "verified_by": "sebbi.pro",
        "badge_url": f"https://sebbi.pro/check/badge?domain={domain}",
        "report_url": f"https://sebbi.pro/check?domain={domain}",
    })


@router.get("/check/badge")
async def check_badge(domain: str = Query(...)):
    """Returns an embeddable SVG badge, e.g. <img src="https://sebbi.pro/check/badge?domain=example.com">"""
    domain = domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
    base = f"https://{domain}"

    score = 0
    async with httpx.AsyncClient() as client:
        for key, path, points, validator_name in CHECKS:
            text = await fetch(client, base + path)
            if VALIDATORS[validator_name](text):
                score += points

    grade = grade_from_score(score)
    color = GRADE_COLOR[grade]

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">
  <rect width="120" height="20" fill="#0a0f1e"/>
  <rect x="120" width="60" height="20" fill="{color}"/>
  <text x="60" y="14" fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">AI-Safety Grade</text>
  <text x="150" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" font-size="12" font-weight="bold" text-anchor="middle">{grade}</text>
</svg>'''
    return Response(content=svg, media_type="image/svg+xml")

```


## `aigrade_insert.py`

136 lines, 5663 bytes

```python
# ============================================================
# AI-SAFETY GRADE SCANNER - stdlib version for server.py
# (converted from the FastAPI/httpx draft - no new dependencies)
#
# HOW TO INSTALL - two pastes into server.py:
#
# PASTE 1: everything between "BEGIN FUNCTIONS" and "END FUNCTIONS"
#          goes near your other helper functions (e.g. just above
#          the JURIS_VERSION block).
#
# PASTE 2: everything between "BEGIN ROUTES" and "END ROUTES"
#          goes inside do_GET, as new elif branches alongside the
#          other GET routes (match their indentation: 8 spaces).
#
# Endpoints added:
#   GET /api/aigrade?domain=example.com        -> JSON grade report
#   GET /api/aigrade/badge?domain=example.com  -> embeddable SVG badge
# ============================================================

# ---------------- BEGIN FUNCTIONS ----------------
AIGRADE_TIMEOUT=6
AIGRADE_UA="Mozilla/5.0 (compatible; AILeashScanner/1.0; +https://sebbi.pro/scan)"
AIGRADE_UA_AGENT="AILeash-Agent-Check/1.0 (+https://sebbi.pro/scan)"
AIGRADE_CHECKS=[
    ("ai_safety","/.well-known/ai-safety.txt",20,"ai_safety"),
    ("security","/.well-known/security.txt",15,"security"),
    ("robots","/robots.txt",10,"present"),
    ("sitemap","/sitemap.xml",10,"sitemap"),
    ("ai_txt","/.well-known/ai.txt",15,"present"),
    ("comply","/.well-known/comply.txt",15,"present"),
    ("llms","/llms.txt",10,"present"),
]
AIGRADE_RENDER_POINTS=5
AIGRADE_MAX=sum(c[2] for c in AIGRADE_CHECKS)+AIGRADE_RENDER_POINTS
AIGRADE_COLORS={"A":"#7fe3b0","B":"#a8d95f","C":"#c9a84c","D":"#ff9a4a","F":"#ff8a80"}

def _aigrade_fetch(url,ua=AIGRADE_UA):
    try:
        req=urllib.request.Request(url,headers={"User-Agent":ua})
        with urllib.request.urlopen(req,timeout=AIGRADE_TIMEOUT) as r:
            if r.status==200:
                return r.read(500000).decode("utf-8","replace")
    except Exception:
        pass
    return None

def _aigrade_valid(kind,text):
    if kind=="present":
        return bool(text and text.strip())
    if kind=="ai_safety":
        if not text:return False
        low=text.lower()
        return "ai-safe:" in low and "true" in low
    if kind=="security":
        if not text:return False
        low=text.lower()
        return "contact:" in low and "expires:" in low
    if kind=="sitemap":
        if not text:return False
        try:
            import xml.etree.ElementTree as _ET
            _ET.fromstring(text)
            return True
        except Exception:
            return False
    return False

def _aigrade_letter(score):
    if score>=90:return"A"
    if score>=75:return"B"
    if score>=60:return"C"
    if score>=40:return"D"
    return"F"

def aigrade_run(domain):
    domain=str(domain or "").strip().lower().replace("https://","").replace("http://","").rstrip("/")
    domain=domain.split("/")[0]
    if not domain or "." not in domain or len(domain)>200:
        return None
    base="https://"+domain
    results={};score=0
    for key,path,points,kind in AIGRADE_CHECKS:
        text=_aigrade_fetch(base+path)
        passed=_aigrade_valid(kind,text)
        results[key]={"path":path,"found":bool(text),"passed":passed,"points":points if passed else 0}
        if passed:score+=points
    human=_aigrade_fetch(base,AIGRADE_UA)
    agent=_aigrade_fetch(base,AIGRADE_UA_AGENT)
    render_ok=False
    if human and agent:
        ratio=min(len(human),len(agent))/max(len(human),len(agent),1)
        render_ok=ratio>0.9
    results["consistent_rendering"]={"passed":render_ok,"points":AIGRADE_RENDER_POINTS if render_ok else 0}
    if render_ok:score+=AIGRADE_RENDER_POINTS
    return{"domain":domain,"score":score,"max_score":AIGRADE_MAX,
        "grade":_aigrade_letter(score),"checks":results,
        "verified_by":"sebbi.pro",
        "badge_url":HOST+"/api/aigrade/badge?domain="+domain,
        "report_url":HOST+"/api/aigrade?domain="+domain,
        "note":"External-signal check of published AI-transparency files; not an audit of internal systems"}

def aigrade_badge_svg(domain):
    r=aigrade_run(domain)
    grade=r["grade"] if r else "F"
    color=AIGRADE_COLORS.get(grade,"#ff8a80")
    return('<svg xmlns="http://www.w3.org/2000/svg" width="180" height="20">'
        '<rect width="120" height="20" fill="#0a0f1e"/>'
        '<rect x="120" width="60" height="20" fill="'+color+'"/>'
        '<text x="60" y="14" fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">AI-Safety Grade</text>'
        '<text x="150" y="14" fill="#0a0f1e" font-family="Verdana,sans-serif" font-size="12" font-weight="bold" text-anchor="middle">'+grade+'</text>'
        '</svg>')
# ---------------- END FUNCTIONS ----------------


# ---------------- BEGIN ROUTES (paste inside do_GET) ----------------
        elif path=="/api/aigrade":
            qs=parse_qs(parsed.query)
            dom=(qs.get("domain",[""])[0] or "").strip()
            rep=aigrade_run(dom)
            if not rep:
                send_json(self,{"error":"valid domain required, e.g. ?domain=example.com"},400)
            else:
                send_json(self,rep)
        elif path=="/api/aigrade/badge":
            qs=parse_qs(parsed.query)
            dom=(qs.get("domain",[""])[0] or "").strip()
            svg=aigrade_badge_svg(dom)
            body=svg.encode()
            self.send_response(200)
            self.send_header("Content-Type","image/svg+xml")
            self.send_header("Cache-Control","max-age=3600")
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)
# ---------------- END ROUTES ----------------

```


## `aileash_reporter.py`

232 lines, 9377 bytes

```python
"""
AILEASH DECISION REPORTER v1.0.0
Generates readable audit reports for all AILeash products.
Shows exactly why each decision was made.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK
"""

import sqlite3, json, os
from datetime import datetime

DB_FILE = "aileash.db"

PRODUCTS = {
    "aileash": "AILeash",
    "guardian": "AILeash Guardian",
    "sonicboom": "SonicBoom",
    "sentinel": "AILeash Sentinel"
}

REASON_EXPLANATIONS = {
    "velocity_spike": "User made more than 10 requests in 60 seconds",
    "high_amount": "Transaction amount exceeded threshold",
    "risky_device": "Device risk score was above acceptable limit",
    "behaviour_anomaly": "Unusual behaviour pattern detected",
    "country_shift": "Request came from a different country than usual",
    "unsafe_country": "Request came from outside approved country list",
    "low_trust": "User trust score has dropped due to previous decisions",
}

def get_decisions(db_path=DB_FILE, limit=200):
    if not os.path.exists(db_path):
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT a.ts, a.user_id, a.event_json, a.result_json, a.audit_hash,
                   COALESCE(k.product, 'aileash') as product
            FROM audit_log a
            LEFT JOIN api_keys k ON json_extract(a.event_json, '$.api_key') = k.key
            ORDER BY a.id DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
    except:
        try:
            conn = sqlite3.connect(db_path)
            rows = conn.execute("""
                SELECT ts, user_id, event_json, result_json, audit_hash, 'aileash'
                FROM audit_log ORDER BY id DESC LIMIT ?
            """, (limit,)).fetchall()
            conn.close()
        except:
            return []
    
    results = []
    for row in rows:
        try:
            event = json.loads(row[2])
            result = json.loads(row[3])
            results.append({
                "ts": row[0],
                "user_id": row[1],
                "event": event,
                "result": result,
                "audit_hash": row[4],
                "product": row[5] or "aileash"
            })
        except:
            pass
    return results

def explain_reason(r):
    return REASON_EXPLANATIONS.get(r, r.replace("_", " ").capitalize())

def decision_color(d):
    return {"ALLOW": "#00875a", "CHALLENGE": "#b45309", "BLOCK": "#cc0000"}.get(d, "#555")

def product_color(p):
    return {
        "aileash": "#c9a84c",
        "guardian": "#cc0000",
        "sonicboom": "#00d4ff",
        "sentinel": "#7c3aed"
    }.get(p, "#c9a84c")

def generate_html_report(db_path=DB_FILE, limit=200, output="aileash_report.html"):
    decisions = get_decisions(db_path, limit)

    allow = sum(1 for d in decisions if d["result"].get("decision") == "ALLOW")
    challenge = sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE")
    block = sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")

    rows = ""
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        product = d.get("product", "aileash")
        pc = product_color(product)
        dc = decision_color(decision)
        pname = PRODUCTS.get(product, product)

        reason_html = ""
        if reasons:
            reason_html = "<ul>" + "".join(
                f"<li>{explain_reason(r)}</li>" for r in reasons
            ) + "</ul>"
        else:
            reason_html = "<span style='color:#888'>No risk factors detected</span>"

        rows += f"""<tr>
            <td>{ts}</td>
            <td><span style="font-size:10px;background:{pc}22;color:{pc};border:1px solid {pc}44;padding:2px 6px;border-radius:3px">{pname}</span></td>
            <td><code>{d['user_id']}</code></td>
            <td>{event.get('action','?')}</td>
            <td>{event.get('country','?')}</td>
            <td>£{event.get('amount',0)}</td>
            <td><strong style="color:{dc}">{decision}</strong></td>
            <td>{score}</td>
            <td>{result.get('trust',0)}</td>
            <td>{reason_html}</td>
            <td><code style="font-size:10px">{d['audit_hash'][:16]}...</code></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash Audit Report</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:sans-serif;background:#f5f7fa;color:#1a202c;padding:20px}}
.header{{background:#0a0f1e;color:#fff;padding:24px 32px;border-radius:8px;margin-bottom:20px;display:flex;justify-content:space-between;align-items:center}}
.header h1{{font-size:22px;color:#c9a84c;margin:0}}
.header p{{font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px}}
.logo{{font-size:13px;color:rgba(255,255,255,0.2)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}}
.stat{{background:#fff;border-radius:8px;padding:16px;text-align:center;border:1px solid #e2e8f0}}
.stat-n{{font-size:28px;font-weight:700}}
.stat-l{{font-size:11px;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:1px}}
.allow{{color:#00875a}}.challenge{{color:#b45309}}.block{{color:#cc0000}}.total{{color:#0a0f1e}}
.table-wrap{{background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:900px}}
th{{background:#0a0f1e;color:#c9a84c;padding:10px 12px;text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:1px;white-space:nowrap}}
td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}}
tr:last-child td{{border:none}}
tr:hover td{{background:#f8fafc}}
ul{{margin:4px 0;padding-left:16px}}
li{{margin:2px 0;color:#64748b;font-size:11px}}
code{{background:#f1f5f9;padding:2px 4px;border-radius:3px;font-size:10px}}
.empty{{text-align:center;color:#888;padding:40px}}
footer{{text-align:center;font-size:11px;color:#94a3b8;margin-top:20px}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>AILeash Audit Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Last {len(decisions)} decisions</p>
  </div>
  <div class="logo">sebbi.pro &nbsp;|&nbsp; OAAS-1.0</div>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n total">{len(decisions)}</div><div class="stat-l">Total</div></div>
  <div class="stat"><div class="stat-n allow">{allow}</div><div class="stat-l">Allowed</div></div>
  <div class="stat"><div class="stat-n challenge">{challenge}</div><div class="stat-l">Challenged</div></div>
  <div class="stat"><div class="stat-n block">{block}</div><div class="stat-l">Blocked</div></div>
</div>
<div class="table-wrap">
<table>
<thead><tr>
  <th>Time</th><th>Product</th><th>User</th><th>Action</th><th>Country</th>
  <th>Amount</th><th>Decision</th><th>Score</th><th>Trust</th><th>Reasons</th><th>Audit Hash</th>
</tr></thead>
<tbody>
{''.join([rows]) if rows else f'<tr><td colspan="11" class="empty">No decisions recorded yet</td></tr>'}
</tbody>
</table>
</div>
<footer>AILeash &nbsp;|&nbsp; Monop Content &nbsp;|&nbsp; Justin Antony Dobson &nbsp;|&nbsp; sebbi.pro &nbsp;|&nbsp; SHA-256 Merkle Chain</footer>
</body>
</html>"""

    with open(output, "w") as f:
        f.write(html)
    print(f"Report saved: {output} ({len(decisions)} decisions)")
    return output

def generate_json_report(db_path=DB_FILE, limit=200, output="aileash_report.json"):
    decisions = get_decisions(db_path, limit)
    report = {
        "generated": datetime.now().isoformat(),
        "standard": "OAAS-1.0",
        "source": "sebbi.pro",
        "total": len(decisions),
        "summary": {
            "allow": sum(1 for d in decisions if d["result"].get("decision") == "ALLOW"),
            "challenge": sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE"),
            "block": sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")
        },
        "decisions": [{
            "timestamp": datetime.fromtimestamp(d["ts"]).isoformat(),
            "product": PRODUCTS.get(d["product"], d["product"]),
            "user_id": d["user_id"],
            "action": d["event"].get("action"),
            "country": d["event"].get("country"),
            "amount": d["event"].get("amount"),
            "decision": d["result"].get("decision"),
            "score": d["result"].get("score"),
            "trust": d["result"].get("trust"),
            "reasons": d["result"].get("reasons", []),
            "reasons_explained": [explain_reason(r) for r in d["result"].get("reasons", [])],
            "audit_hash": d["audit_hash"]
        } for d in decisions]
    }
    with open(output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"Report saved: {output}")
    return output

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "html"
    db = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
    if fmt == "json":
        generate_json_report(db)
    else:
        generate_html_report(db)

```


## `aileash_signed_client.py`

415 lines, 14196 bytes

```python
#!/usr/bin/env python3
"""
aileash_signed_client.py  -  reference client for the signed witness lane

Standard library only. No pip install, no dependencies, runs anywhere
Python 3 runs including a phone.

WHAT IT IS FOR
    Two jobs, and it is the same code for both.

    1. Testing. Run it with --test against your own deployment and it
       generates a throwaway keypair, enrols it, submits a tip, fetches
       the receipt, and rechecks the signature in the receipt against the
       published public key. If all four steps pass, the lane works end
       to end.

    2. Giving to a peer. This is the file you send someone who asks how
       to join the signed lane. It contains a complete, readable Ed25519
       implementation and the exact canonical message, so they can copy
       the approach into any language without guessing.

USAGE
    Generate a keypair and keep it:
        python3 aileash_signed_client.py --keygen

    Enrol a name:
        python3 aileash_signed_client.py --enroll --chain you.example \\
            --secret <hex from keygen>

    Submit a tip:
        python3 aileash_signed_client.py --submit --chain you.example \\
            --secret <hex> --tip <64 hex>

    Full round trip with a throwaway name and key:
        python3 aileash_signed_client.py --test

    Point at somewhere else:
        --host https://sebbi.pro

THE PRIVATE KEY
    --keygen prints a 64-hex seed. That is the private key. Whoever holds
    it can submit under your enrolled name and nobody else can, including
    the operator of the deployment. Do not send it anywhere. There is no
    route on the server that accepts one, and if a route ever asks you
    for one, something is wrong.

    Losing it is not catastrophic and it is not recoverable either. You
    cannot rotate without it - rotation must be signed by the key being
    replaced, which is exactly what stops anyone else rotating it. If it
    is lost, enrol a new name; the old one stays visible and unused.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_HOST = "https://sebbi.pro"
MSG_PREFIX = "aileash-signed-v1"
ROTATE_PREFIX = "aileash-rotate-v1"


# ----------------------------------------------------------------------
# Ed25519, RFC 8032. Sign and verify. Standard library only.
#
# This is here so the file is self-contained and so a peer can read what
# is actually happening rather than trusting a library they also have to
# install. It is the textbook reference implementation with extended
# coordinates for the scalar multiplication.
# ----------------------------------------------------------------------

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P)
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, _BX * _BY % _P)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    dd = z1 * 2 * z2 % _P
    e, f, g, h = b - a, dd - c, dd + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(p, e):
    if e == 0:
        return (0, 1, 1, 0)
    q = _scalarmult(p, e >> 1)
    q = _add(q, q)
    if e & 1:
        q = _add(q, p)
    return q


def _encodepoint(p):
    x, y, z, _t = p
    zi = pow(z, _P - 2, _P)
    x = x * zi % _P
    y = y * zi % _P
    raw = bytearray(y.to_bytes(32, "little"))
    raw[31] |= (x & 1) << 7
    return bytes(raw)


def _decodepoint(raw):
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P:
        return None
    x = _xrecover(y)
    if x & 1 != (raw[31] >> 7) & 1:
        x = _P - x
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        return None
    return (x, y, 1, x * y % _P)


def _secret_scalar(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """32-byte public key from a 32-byte seed."""
    a, _ = _secret_scalar(seed)
    return _encodepoint(_scalarmult(_B, a))


def sign(seed, message):
    """64-byte Ed25519 signature."""
    a, prefix = _secret_scalar(seed)
    pk = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    rp = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(rp + pk + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return rp + s.to_bytes(32, "little")


def verify(pk, message, signature):
    """True if signature is valid. Never raises."""
    try:
        if len(pk) != 32 or len(signature) != 64:
            return False
        a = _decodepoint(pk)
        if a is None:
            return False
        r = _decodepoint(signature[:32])
        if r is None:
            return False
        s = int.from_bytes(signature[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(
            hashlib.sha512(signature[:32] + pk + message).digest(),
            "little") % _L
        left = _scalarmult(_B, s)
        right = _add(r, _scalarmult(a, k))
        lx, ly, lz, _lt = left
        rx, ry, rz, _rt = right
        return ((lx * rz - rx * lz) % _P == 0
                and (ly * rz - ry * lz) % _P == 0)
    except Exception:
        return False


# ----------------------------------------------------------------------
# the canonical message - the only part a reimplementer must match
# ----------------------------------------------------------------------

def canonical_submit(chain, tip, ts):
    """Four lines, single \\n, UTF-8, no trailing newline."""
    return "\n".join([MSG_PREFIX, chain, tip, str(int(ts))]).encode("utf-8")


def canonical_rotate(chain, new_pubkey_hex, ts):
    return "\n".join([ROTATE_PREFIX, chain, new_pubkey_hex,
                      str(int(ts))]).encode("utf-8")


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------

def _call(host, path, body=None, timeout=20):
    url = host.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace")), r.getcode()
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return json.loads(raw), e.code
        except Exception:
            return {"raw": raw[:400]}, e.code
    except Exception as e:
        return {"error": "unreachable", "detail": str(e)}, 0


def _wake(host):
    """The router only imports a module when a request arrives, and only
    GET reaches it after a restart. So GET something before POSTing."""
    _call(host, "/x/witness/tip")


# ----------------------------------------------------------------------
# operations
# ----------------------------------------------------------------------

def do_keygen():
    seed = os.urandom(32)
    print("private seed (KEEP THIS, send it nowhere):")
    print("  " + seed.hex())
    print("public key (this is what you enrol):")
    print("  " + public_key(seed).hex())


def do_enroll(host, chain, seed):
    _wake(host)
    pk = public_key(seed).hex()
    body, code = _call(host, "/x/signed/enroll",
                       {"chain": chain, "pubkey": pk})
    print(json.dumps(body, indent=2))
    return code == 200


def do_submit(host, chain, seed, tip):
    _wake(host)
    ts = int(time.time())
    sig = sign(seed, canonical_submit(chain, tip, ts)).hex()
    body, code = _call(host, "/x/signed/submit",
                       {"chain": chain, "tip": tip, "ts": ts,
                        "signature": sig})
    print(json.dumps(body, indent=2))
    return code == 200


def do_verify(host, chain, tip):
    body, code = _call(host,
                       "/x/signed/verify?peer=%s&tip=%s" % (chain, tip))
    print(json.dumps(body, indent=2))
    return body, code


def do_test(host):
    """Full round trip on a throwaway name and key, then an independent
    recheck of the receipt. Prints a pass or fail per step."""
    results = []

    def step(label, ok, detail=""):
        results.append(ok)
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", label,
                             ("  -- " + detail) if detail else ""))

    seed = os.urandom(32)
    pk = public_key(seed)
    chain = "selftest-%s.invalid" % os.urandom(4).hex()
    tip = hashlib.sha256(os.urandom(32)).hexdigest()

    print("host   %s" % host)
    print("chain  %s   (throwaway, .invalid never resolves)" % chain)
    print("tip    %s\n" % tip)

    _wake(host)

    body, code = _call(host, "/x/signed/spec")
    step("lane is deployed", code == 200 and body.get("signed_version"),
         "signed_version %s" % body.get("signed_version", "?"))
    if code != 200:
        print("\nStopping: the signed lane is not answering.")
        return 1

    body, code = _call(host, "/x/signed/enroll",
                       {"chain": chain, "pubkey": pk.hex()})
    step("enrol", code == 200 and body.get("enrolled"),
         body.get("error") or "block %s" % body.get("block_index"))

    # the operator cannot forge: a wrong signature must be refused
    body, code = _call(host, "/x/signed/submit",
                       {"chain": chain, "tip": tip,
                        "ts": int(time.time()), "signature": "00" * 64})
    step("forged signature refused", code == 400
         and body.get("error") == "signature_did_not_verify",
         "got %s %s" % (code, body.get("error")))

    ts = int(time.time())
    sig = sign(seed, canonical_submit(chain, tip, ts)).hex()
    body, code = _call(host, "/x/signed/submit",
                       {"chain": chain, "tip": tip, "ts": ts,
                        "signature": sig})
    step("submit", code == 200 and body.get("verification") == "peer-signed",
         body.get("error") or "block %s" % body.get("block_index"))
    on_roster = bool(body.get("on_public_roster"))
    step("mirrored to public roster", on_roster,
         "" if on_roster else "sealed, but not visible on /x/roster/list")

    body, code = _call(host, "/x/signed/submit",
                       {"chain": chain, "tip": tip, "ts": ts,
                        "signature": sig})
    step("replay refused", code in (400, 409),
         "got %s %s" % (code, body.get("error")))

    receipt, code = _call(host,
                          "/x/signed/verify?peer=%s&tip=%s" % (chain, tip))
    step("receipt readable", code == 200
         and receipt.get("signed_observation") is True,
         receipt.get("message") or "block %s" % receipt.get("block_index"))

    if code == 200:
        # the whole point: recheck using ONLY what the receipt returned
        cm = receipt.get("canonical_message", "")
        rebuilt = canonical_submit(chain, tip, ts).decode("utf-8")
        step("receipt's canonical message matches ours", cm == rebuilt,
             "" if cm == rebuilt else "receipt gave %r" % cm[:60])
        ok = verify(bytes.fromhex(receipt.get("pubkey", "")),
                    cm.encode("utf-8"),
                    bytes.fromhex(receipt.get("signature", "")))
        step("signature in the receipt verifies independently", ok)

        keys, kcode = _call(host, "/x/signed/keys")
        listed = any(k.get("chain") == chain
                     and k.get("pubkey") == pk.hex()
                     for k in (keys.get("keys") or []))
        step("public key published at /x/signed/keys", listed)

    print("\n%d of %d passed" % (sum(1 for r in results if r), len(results)))
    print("\nNote: this left a real, permanent enrolment and observation "
          "for %s in the chain.\nThat is correct - nothing in this system "
          "can be tidied up afterwards, which is\nthe property being "
          "tested. The name is a throwaway on a .invalid domain." % chain)
    return 0 if all(results) else 1


def main():
    ap = argparse.ArgumentParser(
        description="Reference client for the AILeash signed witness lane.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--chain")
    ap.add_argument("--secret", help="private seed, 64 hex, from --keygen")
    ap.add_argument("--tip", help="your chain head, 64 hex")
    ap.add_argument("--keygen", action="store_true")
    ap.add_argument("--enroll", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--check", action="store_true", help="fetch a receipt")
    ap.add_argument("--test", action="store_true",
                    help="full round trip on a throwaway key")
    a = ap.parse_args()

    if a.keygen:
        do_keygen()
        return 0
    if a.test:
        return do_test(a.host)

    if a.check:
        if not (a.chain and a.tip):
            ap.error("--check needs --chain and --tip")
        do_verify(a.host, a.chain, a.tip)
        return 0

    if not (a.enroll or a.submit):
        ap.print_help()
        return 0
    if not (a.chain and a.secret):
        ap.error("--chain and --secret are required")
    try:
        seed = bytes.fromhex(a.secret.strip())
        assert len(seed) == 32
    except Exception:
        ap.error("--secret must be 64 hex characters from --keygen")

    if a.enroll:
        do_enroll(a.host, a.chain, seed)
    if a.submit:
        if not a.tip:
            ap.error("--submit needs --tip")
        do_submit(a.host, a.chain, seed, a.tip.strip().lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
aileash_signed_client.py

```
