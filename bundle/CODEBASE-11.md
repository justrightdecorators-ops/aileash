# Codebase — part 11 of 45

Contains:
- `modules/humankeys.py`
- `modules/integrity.py`


## `modules/humankeys.py`

779 lines, 41038 bytes

```python
"""
modules/humankeys.py  v1.1.0  -  Human Keys: proof a human typed it

    Page:    https://sebbi.pro/keys
    Check:   https://sebbi.pro/k/<code>
    Arm:     https://sebbi.pro/x/arm/status

WHAT IT DOES
------------
Someone types on the Human Keys page. The page records HOW they type - the
gaps between keystrokes, the corrections, the thinking pauses, whether
anything was pasted - and never WHAT they type. The text is fingerprinted
(SHA-256) on their own device and only the fingerprint is sent.

The rhythm is scored on the server, the fingerprint and the score are sealed
into the chain, and they get a short code like HK-7Q2M-X9KD. Anyone can open
https://sebbi.pro/k/HK-7Q2M-X9KD, paste the text, and see whether it matches
something a human typed, live, on the date shown.

WHY IT CANNOT BE PREPARED IN ADVANCE
------------------------------------
A session starts with a challenge from the server: the latest public beacon
(drand, sealed by the heartbeat module), the current chain tip and a signed
server timestamp. The seal must carry that challenge, and the time the server
saw pass between issuing it and the seal must be at least as long as the
typing the page reports. A typing session cannot claim to be longer than the
real time that passed, and cannot have started before a beacon nobody could
know in advance.

WHAT IT PROVES, PRECISELY
-------------------------
That the text was typed into this page by hand, live, with a human typing
rhythm, and was not pasted or inserted by a program. It cannot see what is
on the typist's screen, so it does not prove the words were their own; the
"composition" signals (corrections, thinking pauses) are reported so a
reader can judge.

PRIVACY
-------
The text never leaves the device. The raw keystroke timings are scored and
thrown away; only summary figures are kept. Nothing identifies the typist.

PRICE
-----
50p a month, unlimited proofs - the same as everything else on sebbi.pro.
The first proof takes 50p from the credit wallet (the same wallet as Monop
Studio, topped up at https://sebbi.pro/credits) and opens a 30-day pass;
every proof in those 30 days is free. Checking a proof is free, always.
Businesses seal with their API key instead - included in the 50p per device
per month they already pay. POST /x/humankeys/seal with "reference" set to
the decision block or case.

ROUTES
------
  GET  /x/humankeys/status            public
  GET  /x/humankeys/spec              public
  GET  /x/humankeys/challenge         public - start a typing session
  POST /x/humankeys/seal              public with a 50p monthly pass, or API key
  GET  /x/humankeys/pass?viewer=      public - is this wallet's pass active
  GET  /x/humankeys/check?code=       public - the sealed record
  POST /x/humankeys/compare           public - {code, text_hash}: does it match
  GET  /keys                          the keyboard
  GET  /k/<code>                      the check page
  GET  /k/<code>.svg                  a badge for the proof
"""

import hashlib
import hmac
import json
import math
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _UK = ZoneInfo("Europe/London")
except Exception:
    _UK = None

VERSION = "1.1.0"
PRICE_PENCE = 50
PASS_DAYS = 30
CHALLENGE_TTL = 4 * 3600
MIN_KEYS = 30
MAX_INTERVALS = 6000

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "challenge"), ("POST", "seal"),
          ("GET", "check"), ("POST", "compare"), ("GET", "pass")}

CODE_RE = re.compile(r"^HK-[A-Z2-9]{4}-[A-Z2-9]{4}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
VIEWER_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_state = {"ready": False, "page": False, "sealed": 0, "last_error": None}
_lock = threading.Lock()
_EPHEMERAL = secrets.token_bytes(32)


# ---------------------------------------------------------------------
# plumbing
# ---------------------------------------------------------------------

def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _secret():
    s = os.environ.get("HUMANKEYS_SECRET") or os.environ.get("LICENCE_SECRET") or ""
    return s.encode() if s else _EPHEMERAL


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _uk(ts):
    try:
        return datetime.fromtimestamp(float(ts), _UK or timezone.utc).strftime("%d %b %Y, %H:%M %Z")
    except Exception:
        return None


def _setup():
    s = _srv()
    with s._db_lock:
        s._conn.execute("CREATE TABLE IF NOT EXISTS humankeys_proof("
                        "code TEXT PRIMARY KEY, text_hash TEXT, verdict TEXT, score REAL,"
                        "summary_json TEXT, challenge_json TEXT, sealed_at REAL,"
                        "block_index INTEGER, audit_hash TEXT, payer TEXT, reference TEXT)")
        s._conn.execute("CREATE INDEX IF NOT EXISTS idx_hk_hash ON humankeys_proof(text_hash)")
        s._conn.execute("CREATE TABLE IF NOT EXISTS humankeys_pass("
                        "viewer TEXT PRIMARY KEY, paid_at REAL, expires REAL, months INTEGER DEFAULT 0)")
        s._conn.commit()


def _arm_credits(ctx):
    """The wallet lives in modules/credits.py. Make sure its /c/ routes are up."""
    try:
        try:
            from modules import credits as C
        except Exception:
            import credits as C
        C.handle("GET", "status", {}, None, ctx)
        return True
    except Exception as e:
        _state["last_error"] = "credits: %s" % e
        return False


def _new_code():
    raw = secrets.token_bytes(8)
    chars = "".join(ALPHABET[b % len(ALPHABET)] for b in raw)
    return "HK-%s-%s" % (chars[:4], chars[4:8])


# ---------------------------------------------------------------------
# challenge
# ---------------------------------------------------------------------

def _beacon():
    s = _srv()
    out = {}
    try:
        with s._db_lock:
            r = s._conn.execute("SELECT source,beacon_round,value,fetched_at FROM heartbeat_tick "
                                "ORDER BY id DESC LIMIT 1").fetchone()
        if r:
            out = {"source": r[0], "round": r[1], "value": r[2], "fetched_utc": _iso(r[3])}
    except Exception:
        pass
    try:
        out["chain_tip"] = s.chain_tip()
    except Exception:
        pass
    return out


def _sign(body):
    return hmac.new(_secret(), json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def _challenge():
    body = {"issued": round(time.time(), 3), "nonce": secrets.token_hex(12), "beacon": _beacon()}
    return {"challenge": body, "sig": _sign(body), "expires_in": CHALLENGE_TTL}


def _check_challenge(ch, sig):
    if not isinstance(ch, dict) or not isinstance(sig, str):
        return False, "challenge missing"
    if not hmac.compare_digest(_sign(ch), sig):
        return False, "challenge not issued by this server"
    age = time.time() - float(ch.get("issued", 0))
    if age < 0 or age > CHALLENGE_TTL:
        return False, "challenge expired - start a new session"
    return True, age


# ---------------------------------------------------------------------
# the rhythm
# ---------------------------------------------------------------------

def score(intervals, counts, server_elapsed):
    """Score a typing session from its timings alone. Returns (verdict, score, summary)."""
    iv = []
    for x in (intervals or [])[:MAX_INTERVALS]:
        try:
            v = float(x)
        except (TypeError, ValueError):
            continue
        if 0 <= v <= 600000:
            iv.append(v)
    c = {k: int(counts.get(k, 0) or 0) for k in
         ("inserts", "deletes", "multi_inserts", "multi_chars", "paste_events", "paste_chars",
          "final_length", "blurs", "typed_chars")}
    typed = max(c["typed_chars"], c["inserts"])
    claimed_ms = sum(iv)
    flags = []

    active = [v for v in iv if v <= 2000]
    pauses = [v for v in iv if v > 2000]
    n = len(active)
    mean = sum(active) / n if n else 0
    sd = math.sqrt(sum((v - mean) ** 2 for v in active) / n) if n else 0
    cv = (sd / mean) if mean else 0
    too_fast = sum(1 for v in active if v < 12)
    minutes = (claimed_ms / 60000.0) if claimed_ms else 0
    cpm = (typed / minutes) if minutes else 0
    corr_ratio = (c["deletes"] / float(typed)) if typed else 0
    paste_share = (c["paste_chars"] / float(c["final_length"])) if c["final_length"] else 0

    # text that appeared from nowhere: final length far beyond what was typed or pasted
    accounted = typed + c["multi_chars"] + c["paste_chars"]
    unaccounted = max(0, c["final_length"] - accounted)

    summary = {
        "keystrokes": typed,
        "corrections": c["deletes"],
        "correction_rate": round(corr_ratio, 3),
        "thinking_pauses": len(pauses),
        "longest_pause_s": round(max(pauses) / 1000.0, 1) if pauses else 0,
        "typing_minutes": round(minutes, 2),
        "chars_per_minute": round(cpm),
        "rhythm_variation": round(cv, 2),
        "word_suggestions_used": c["multi_inserts"],
        "pasted_characters": c["paste_chars"],
        "pasted_share": round(paste_share, 3),
        "final_length": c["final_length"],
        "left_the_page": c["blurs"],
        "server_seconds": round(server_elapsed, 1),
    }

    if server_elapsed + 5 < claimed_ms / 1000.0:
        return "REFUSED", 0.0, dict(summary, reason="The typing reported is longer than the real time that passed since the session started.")
    if unaccounted > max(20, 0.05 * c["final_length"]):
        return "REFUSED", 0.0, dict(summary, reason="Text appeared that was neither typed nor pasted.")
    if typed + c["multi_inserts"] < MIN_KEYS:
        return "TOO_SHORT", 0.0, dict(summary, reason="Type at least %d characters for a proof." % MIN_KEYS)

    s = 1.0
    if cv < 0.18:
        flags.append("rhythm is unnaturally even, like a program")
        s -= 0.6
    elif cv < 0.3:
        flags.append("rhythm is very even")
        s -= 0.2
    if cpm > 1100 and c["multi_inserts"] < typed / 20:
        flags.append("faster than human typing")
        s -= 0.5
    if n and too_fast / float(n) > 0.15:
        flags.append("many keystrokes closer together than fingers can manage")
        s -= 0.4
    if typed >= 200 and c["deletes"] == 0 and not pauses:
        flags.append("no corrections and no pauses over a long text - steady copying")
        s -= 0.15
    s = max(0.0, min(1.0, s))

    composing = 0
    if corr_ratio >= 0.02:
        composing += 1
    if len(pauses) >= max(1, typed // 250):
        composing += 1
    if cv >= 0.6:
        composing += 1
    summary["composition_signals"] = ["weak", "some", "clear", "strong"][composing]
    summary["flags"] = flags

    if s < 0.45:
        verdict = "MECHANICAL"
    elif paste_share > 0.02 or c["paste_events"] > 0:
        verdict = "HUMAN_TYPED_PART_PASTED"
    else:
        verdict = "HUMAN_TYPED"
    return verdict, round(s, 2), summary


VERDICT_TEXT = {
    "HUMAN_TYPED": "Typed by a human, live. Nothing pasted.",
    "HUMAN_TYPED_PART_PASTED": "Typed by a human, live - but part of it was pasted in.",
    "MECHANICAL": "The rhythm does not look like a human typing.",
}


# ---------------------------------------------------------------------
# sealing and payment
# ---------------------------------------------------------------------

def _pass(viewer):
    """(active, expires) for a wallet's monthly pass."""
    s = _srv()
    with s._db_lock:
        r = s._conn.execute("SELECT expires FROM humankeys_pass WHERE viewer=?", (viewer,)).fetchone()
    if r and r[0] > time.time():
        return True, r[0]
    return False, (r[0] if r else None)


def _balance(viewer):
    s = _srv()
    with s._db_lock:
        try:
            r = s._conn.execute("SELECT balance FROM credit_viewer WHERE id=?", (viewer,)).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0


def _buy_pass(viewer):
    """Take 50p and open a 30-day pass. Returns (ok, expires, balance)."""
    s = _srv()
    now = time.time()
    with s._db_lock:
        try:
            cur = s._conn.execute("UPDATE credit_viewer SET balance=balance-?, spent=spent+? "
                                  "WHERE id=? AND balance>=?", (PRICE_PENCE, PRICE_PENCE, viewer, PRICE_PENCE))
            ok = cur.rowcount == 1
        except Exception:
            ok = False
        if ok:
            exp = now + PASS_DAYS * 86400
            s._conn.execute("INSERT INTO humankeys_pass(viewer,paid_at,expires,months) VALUES(?,?,?,1) "
                            "ON CONFLICT(viewer) DO UPDATE SET paid_at=excluded.paid_at, "
                            "expires=excluded.expires, months=months+1", (viewer, now, exp))
        s._conn.commit()
    bal = _balance(viewer)
    if not ok:
        return False, None, bal
    try:
        ev = {"user_id": "humankeys", "action": "monthly_pass", "amount": 0, "country": "UK",
              "device_id": "humankeys", "anomaly": 0, "device_risk": 0}
        s.seal(ev, {"decision": "PASS_PURCHASED", "score": 0, "version": VERSION, "timestamp": now,
                    "price_pence": PRICE_PENCE, "days": PASS_DAYS,
                    "wallet": hashlib.sha256(viewer.encode()).hexdigest()[:16]}, now)
    except Exception as e:
        _state["last_error"] = "pass seal: %s" % e
    return True, now + PASS_DAYS * 86400, bal


def _refund_pass(viewer):
    s = _srv()
    with s._db_lock:
        s._conn.execute("UPDATE credit_viewer SET balance=balance+?, spent=spent-? WHERE id=?",
                        (PRICE_PENCE, PRICE_PENCE, viewer))
        s._conn.execute("UPDATE humankeys_pass SET expires=paid_at WHERE viewer=?", (viewer,))
        s._conn.commit()


def _seal(data, api_key):
    s = _srv()
    data = data or {}
    text_hash = str(data.get("text_hash", "")).strip().lower()
    if not HEX64.match(text_hash):
        return {"error": "text_hash must be the SHA-256 of the text"}, 400
    ok, info = _check_challenge(data.get("challenge"), data.get("sig"))
    if not ok:
        return {"error": "bad_challenge", "message": info}, 400
    elapsed = info
    counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    verdict, sc, summary = score(data.get("intervals") or [], counts, elapsed)
    if verdict in ("REFUSED", "TOO_SHORT"):
        return {"sealed": False, "verdict": verdict, "message": summary.get("reason"), "summary": summary}, 422

    reference = str(data.get("reference", ""))[:120] or None
    viewer = str(data.get("viewer", "")).strip()
    expires = None
    if api_key and s.get_key(api_key):
        payer = "key:" + hashlib.sha256(api_key.encode()).hexdigest()[:16]
        paid = None
        balance = None
    else:
        if not VIEWER_RE.match(viewer):
            return {"error": "wallet_needed", "message": "Top up once at https://sebbi.pro/credits",
                    "price_pence": PRICE_PENCE}, 402
        active, expires = _pass(viewer)
        if active:
            paid, balance = False, _balance(viewer)
        else:
            paid, expires, balance = _buy_pass(viewer)
            if not paid:
                return {"sealed": False, "reason": "pass_needed", "price_pence": PRICE_PENCE,
                        "balance_pence": balance, "topup": "https://sebbi.pro/credits",
                        "message": "Human Keys is 50p a month for unlimited proofs. Top up and seal straight away."}, 402
        payer = "credit:" + hashlib.sha256(viewer.encode()).hexdigest()[:16]

    code = _new_code()
    ch = data.get("challenge")
    ts = time.time()
    event = {"user_id": "humankeys", "action": "human_typed", "amount": 0, "country": "UK",
             "device_id": "humankeys", "anomaly": 0, "device_risk": 0}
    result = {"decision": verdict, "score": sc, "version": VERSION, "timestamp": ts,
              "code": code, "text_hash": text_hash, "summary": summary,
              "session_started_utc": _iso(ch.get("issued")),
              "beacon": (ch.get("beacon") or {}).get("round"),
              "beacon_value": (ch.get("beacon") or {}).get("value"),
              "chain_tip_at_start": (ch.get("beacon") or {}).get("chain_tip"),
              "reference": reference, "pass_purchased": bool(paid)}
    try:
        out = s.seal(event, result, ts)
        h, idx = out[0], out[1]
    except Exception as e:
        if paid:
            _refund_pass(viewer)
        return {"error": "seal_failed", "detail": str(e)[:160]}, 500
    with s._db_lock:
        s._conn.execute("INSERT INTO humankeys_proof VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (code, text_hash, verdict, sc, json.dumps(summary), json.dumps(ch), ts,
                         idx, h, payer, reference))
        s._conn.commit()
    _state["sealed"] += 1
    out = {"sealed": True, "code": code, "verdict": verdict, "verdict_text": VERDICT_TEXT.get(verdict),
           "score": sc, "summary": summary, "block_index": idx, "audit_hash": h,
           "sealed_uk": _uk(ts), "check": "https://sebbi.pro/k/" + code,
           "badge": "https://sebbi.pro/k/%s.svg" % code}
    if balance is not None:
        out["balance_pence"] = balance
    if expires:
        out["pass_until_uk"] = _uk(expires)
        out["pass_purchased_now"] = bool(paid)
    return out, 200


def _record(code):
    s = _srv()
    with s._db_lock:
        r = s._conn.execute("SELECT code,text_hash,verdict,score,summary_json,challenge_json,sealed_at,"
                            "block_index,audit_hash,reference FROM humankeys_proof WHERE code=?",
                            (code,)).fetchone()
    if not r:
        return None
    ch = json.loads(r[5] or "{}")
    return {"code": r[0], "text_hash": r[1], "verdict": r[2], "verdict_text": VERDICT_TEXT.get(r[2]),
            "score": r[3], "summary": json.loads(r[4] or "{}"),
            "session_started_utc": _iso(ch.get("issued")), "sealed_utc": _iso(r[6]), "sealed_uk": _uk(r[6]),
            "beacon": ch.get("beacon"), "block_index": r[7], "audit_hash": r[8], "reference": r[9],
            "verify_block": "https://sebbi.pro/x/walk/block?index=%s" % r[7],
            "check": "https://sebbi.pro/k/" + r[0]}


# ---------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------

def _send(h, body, ctype, status=200):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store" if "json" in ctype else "public, max-age=60")
    h.end_headers()
    h.wfile.write(body)


def _esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _badge(rec):
    ok = rec and rec["verdict"] == "HUMAN_TYPED"
    part = rec and rec["verdict"] == "HUMAN_TYPED_PART_PASTED"
    label = "Human typed" if ok else ("Human typed · part pasted" if part else "Not verified")
    colour = "#2fbf71" if ok else ("#c9a84c" if part else "#9aa0ae")
    code = rec["code"] if rec else "unknown"
    w = 300 if part else 240
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="28" role="img" aria-label="%s %s">'
            '<rect width="%d" height="28" rx="5" fill="#0a0f1e"/><rect x="1" y="1" width="%d" height="26" rx="4" fill="none" stroke="%s" stroke-opacity=".6"/>'
            '<circle cx="15" cy="14" r="5" fill="%s"/>'
            '<text x="27" y="18" fill="#fff" font-family="Verdana,sans-serif" font-size="11.5" font-weight="bold">%s</text>'
            '<text x="%d" y="18" fill="%s" font-family="Verdana,sans-serif" font-size="10.5" text-anchor="end">%s</text></svg>'
            % (w, _esc(label), code, w, w - 2, colour, colour, _esc(label), w - 10, colour, code))


def _install_page():
    if _state["page"]:
        return True
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is None:
        return False
    if getattr(H, "_humankeys_patched", False):
        _state["page"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/")
        if p == "/keys":
            return _send(self, KEYS_PAGE, "text/html; charset=utf-8")
        if p == "/k" or p.startswith("/k/"):
            code = p[3:].upper()
            if code.endswith(".SVG"):
                code = code[:-4]
                rec = _record(code) if CODE_RE.match(code) else None
                return _send(self, _badge(rec), "image/svg+xml")
            if CODE_RE.match(code):
                return _send(self, CHECK_PAGE.replace("__CODE__", code), "text/html; charset=utf-8")
            return _send(self, CHECK_PAGE.replace("__CODE__", ""), "text/html; charset=utf-8")
        return orig(self)

    H.do_GET = do_GET
    H._humankeys_patched = True
    _state["page"] = True
    return True


def arm(ctx=None):
    with _lock:
        _setup()
        _arm_credits(ctx)
        _install_page()
        _state["ready"] = True


# ---------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    data = data or {}
    if action in ("", "status"):
        s = _srv()
        with s._db_lock:
            n = s._conn.execute("SELECT COUNT(*) FROM humankeys_proof").fetchone()[0]
        return {"module": "humankeys", "version": VERSION, "armed": _state["page"],
                "page": "https://sebbi.pro/keys", "proofs_sealed": n, "price": "50p a month, unlimited proofs",
                "last_error": _state["last_error"]}, 200
    if action == "spec":
        return {"module": "humankeys", "version": VERSION,
                "what": "Proof a human typed a text, live. The text never leaves the device; its fingerprint and a score of the typing rhythm are sealed.",
                "price": "50p a month for unlimited proofs, from the credit wallet, or included with an API key. Checking is free.",
                "verdicts": VERDICT_TEXT,
                "routes": {"challenge": "GET https://sebbi.pro/x/humankeys/challenge",
                           "seal": "POST https://sebbi.pro/x/humankeys/seal {challenge, sig, text_hash, intervals, counts, viewer | API key, reference}",
                           "check": "GET https://sebbi.pro/x/humankeys/check?code=HK-XXXX-XXXX",
                           "compare": "POST https://sebbi.pro/x/humankeys/compare {code, text_hash}",
                           "page": "https://sebbi.pro/keys"},
                "text_hash": "SHA-256 of the text as UTF-8, after normalising to NFC, converting line endings to \\n and trimming the ends."}, 200
    if action == "challenge" and method == "GET":
        return _challenge(), 200
    if action == "pass" and method == "GET":
        v = str(data.get("viewer", "")).strip()
        if not VIEWER_RE.match(v):
            return {"error": "viewer needed"}, 400
        active, exp = _pass(v)
        return {"active": active, "until_uk": _uk(exp) if exp else None, "price_pence": PRICE_PENCE,
                "days": PASS_DAYS, "balance_pence": _balance(v)}, 200
    if action == "seal" and method == "POST":
        return _seal(data, api_key)
    if action == "check" and method == "GET":
        code = str(data.get("code", "")).strip().upper()
        rec = _record(code) if CODE_RE.match(code) else None
        return (rec, 200) if rec else ({"error": "no_such_proof", "code": code}, 404)
    if action == "compare" and method == "POST":
        code = str(data.get("code", "")).strip().upper()
        th = str(data.get("text_hash", "")).strip().lower()
        rec = _record(code) if CODE_RE.match(code) else None
        if not rec:
            return {"error": "no_such_proof"}, 404
        return {"code": code, "matches": hmac.compare_digest(rec["text_hash"], th),
                "verdict": rec["verdict"], "verdict_text": rec["verdict_text"], "sealed_uk": rec["sealed_uk"]}, 200
    return {"error": "unknown_action", "spec": "https://sebbi.pro/x/humankeys/spec"}, 404


# ---------------------------------------------------------------------
# page markup
# ---------------------------------------------------------------------

_HEAD = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--gold2:#f0d78a;--ok:#2fbf71;--ok2:#7fe3b0;--err:#ff8a80;--mut:rgba(255,255,255,.62);--line:rgba(201,168,76,.22);
--sans:'IBM Plex Sans',system-ui,sans-serif;--serif:'Newsreader',Georgia,serif;--mono:'IBM Plex Mono',ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--ink);color:#fff;font-family:var(--sans);line-height:1.55;-webkit-font-smoothing:antialiased;padding-bottom:env(safe-area-inset-bottom,0)}
.wrap{max-width:820px;margin:0 auto;padding:0 16px}
.top{border-bottom:1px solid var(--line);padding:14px 0}.top .wrap{display:flex;justify-content:space-between;align-items:baseline}
.brand{font-family:var(--mono);font-size:13px;color:#fff;text-decoration:none}.brand b{color:var(--gold);font-weight:500}
.top a.l{font-family:var(--mono);font-size:12px;color:var(--mut);text-decoration:none}
.hero{padding:38px 0 14px}.kick{font-family:var(--mono);font-size:12px;color:var(--gold);letter-spacing:.08em;margin-bottom:10px}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(34px,7vw,58px);line-height:1.03;margin-bottom:12px}h1 em{color:var(--gold);font-style:italic}
.hero p{color:var(--mut);font-size:16.5px;max-width:58ch}
.card{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:18px;margin:18px 0}
textarea{width:100%;min-height:210px;background:var(--ink);border:1px solid var(--line);border-radius:8px;color:#fff;padding:14px;font-family:var(--sans);font-size:16.5px;line-height:1.6;resize:vertical;outline:none}
textarea:focus{border-color:var(--gold)}
input{width:100%;background:var(--ink);border:1px solid var(--line);border-radius:6px;color:#fff;padding:11px 12px;font-family:var(--mono);font-size:14px}
canvas{width:100%;height:64px;display:block;margin-top:12px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px}
@media(max-width:560px){.stats{grid-template-columns:repeat(2,1fr)}}
.st{background:var(--ink);border:1px solid rgba(255,255,255,.06);border-radius:6px;padding:9px 10px}
.st b{display:block;font-family:var(--mono);font-size:18px;font-weight:500}.st span{font-size:11.5px;color:var(--mut)}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;align-items:center}
.btn{background:var(--gold);color:var(--ink);border:0;border-radius:6px;padding:13px 18px;font-family:var(--mono);font-size:14px;font-weight:500;cursor:pointer;text-decoration:none;display:inline-block}
.btn.g{background:transparent;color:var(--gold);border:1px solid var(--gold)}.btn[disabled]{opacity:.5}
.msg{font-family:var(--mono);font-size:13px;margin-top:10px;min-height:1em}.msg.err{color:var(--err)}.msg.ok{color:var(--ok2)}
.wallet{font-family:var(--mono);font-size:12.5px;color:var(--mut)}
.cert{border:1px solid rgba(47,191,113,.5);background:linear-gradient(160deg,rgba(47,191,113,.10),rgba(16,24,46,1) 60%);border-radius:12px;padding:22px;margin:18px 0}
.cert.part{border-color:rgba(201,168,76,.6);background:linear-gradient(160deg,rgba(201,168,76,.12),rgba(16,24,46,1) 60%)}
.cert.bad{border-color:rgba(255,138,128,.5);background:linear-gradient(160deg,rgba(255,138,128,.10),rgba(16,24,46,1) 60%)}
.seal{display:flex;gap:14px;align-items:center}
.ring{width:54px;height:54px;border-radius:50%;border:2px solid var(--ok);display:flex;align-items:center;justify-content:center;font-size:26px;color:var(--ok);flex:none}
.part .ring{border-color:var(--gold);color:var(--gold)}.bad .ring{border-color:var(--err);color:var(--err)}
.cert h2{font-family:var(--serif);font-weight:500;font-size:26px;line-height:1.15}
.code{font-family:var(--mono);font-size:24px;letter-spacing:.06em;color:var(--gold2);margin:14px 0 4px}
dl{display:grid;grid-template-columns:minmax(120px,170px) 1fr;gap:5px 12px;font-size:14px;margin-top:12px}
dt{color:var(--mut);font-size:13px}dd{font-family:var(--mono);font-size:13px;word-break:break-all}
.how{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:8px 0 18px}@media(max-width:640px){.how{grid-template-columns:1fr}}
.how div{border-top:1px solid var(--line);padding-top:10px}.how b{font-family:var(--mono);font-size:12px;color:var(--gold);letter-spacing:.06em}.how p{color:var(--mut);font-size:14px;margin-top:4px}
footer{border-top:1px solid var(--line);margin-top:30px;padding:20px 0;font-size:12.5px;color:var(--mut)}
footer a{color:var(--gold);text-decoration:none}
</style>"""

KEYS_PAGE = _HEAD + r"""
<title>Human Keys · proof a human typed it</title>
<meta name="description" content="Type it here and get a sealed code that proves a human typed it, live, not pasted or generated. 50p a month, unlimited proofs. Checking is free.">
</head><body>
<div class="top"><div class="wrap"><a class="brand" href="https://sebbi.pro/">AI<b>Leash</b> · Human Keys</a><a class="l" href="https://sebbi.pro/k/">Check a code</a></div></div>
<div class="wrap">
<div class="hero"><div class="kick">HUMAN KEYS</div>
<h1>Proof a human <em>typed it.</em></h1>
<p>Type below. We read the rhythm of your typing, never your words. Seal it and you get one short code that proves a person typed this, live, not pasted and not generated. Anyone can check it, free, forever.</p></div>

<div class="how">
<div><b>01 · TYPE</b><p>Write it here, by hand. Your words stay on your phone.</p></div>
<div><b>02 · SEAL</b><p>The rhythm is scored and sealed with a public clock nobody can predict. 50p a month, as many proofs as you like.</p></div>
<div><b>03 · SHARE</b><p>Put the code or badge under your post, essay, review or sign-off.</p></div>
</div>

<div class="card">
<textarea id="t" placeholder="Start typing…" autocomplete="off" autocorrect="on" spellcheck="true"></textarea>
<canvas id="cv" width="800" height="64"></canvas>
<div class="stats">
<div class="st"><b id="sk">0</b><span>keystrokes</span></div>
<div class="st"><b id="sc">0</b><span>corrections</span></div>
<div class="st"><b id="sp">0</b><span>thinking pauses</span></div>
<div class="st"><b id="sv">0</b><span>pasted characters</span></div>
</div>
<div class="btns"><button class="btn" id="seal" disabled>Seal it</button><span class="wallet" id="wallet">Wallet: …</span><a class="btn g" id="topup" href="https://sebbi.pro/credits" style="display:none">Top up</a></div>
<div class="msg" id="msg"></div>
</div>
<div id="out"></div>
</div>
<footer><div class="wrap">Monop Content · <a href="https://sebbi.pro/x/humankeys/spec">How the proof works</a> · <a href="https://sebbi.pro/k/">Check a code</a></div></footer>
<script>
(function(){
const $=s=>document.querySelector(s);
const t=$('#t'),cv=$('#cv'),cx=cv.getContext('2d');
let ch=null,iv=[],last=0,n={inserts:0,deletes:0,multi_inserts:0,multi_chars:0,paste_events:0,paste_chars:0,blurs:0,typed_chars:0},pauses=0;
let viewer=null;try{viewer=localStorage.getItem('sebbi.viewer')}catch(e){}
if(!viewer){viewer=Array.from(crypto.getRandomValues(new Uint8Array(16))).map(b=>b.toString(16).padStart(2,'0')).join('');try{localStorage.setItem('sebbi.viewer',viewer)}catch(e){}}
function msg(x,c){const m=$('#msg');m.textContent=x;m.className='msg '+(c||'')}
async function start(){try{const r=await fetch('/x/humankeys/challenge');ch=await r.json()}catch(e){msg('Could not reach sebbi.pro. Check your connection.','err')}}
async function wallet(){try{await fetch('/c/hello?viewer='+viewer);const r=await fetch('/x/humankeys/pass?viewer='+viewer);const d=await r.json();const b=d.balance_pence||0;
 if(d.active){$('#wallet').textContent='Unlimited proofs until '+d.until_uk;$('#topup').style.display='none'}
 else{$('#wallet').textContent='50p a month, unlimited proofs · wallet £'+(b/100).toFixed(2);$('#topup').style.display=b<50?'inline-block':'none'}
 return b}catch(e){$('#wallet').textContent='50p a month, unlimited proofs';return 0}}
start();wallet();
function tick(){const now=performance.now();if(last){const g=now-last;iv.push(Math.round(g));if(g>2000)pauses++}last=now;if(iv.length>6000)iv.shift();draw();stats()}
let comp=0;
t.addEventListener('compositionstart',()=>{comp=0});
t.addEventListener('compositionend',()=>{comp=0});
t.addEventListener('beforeinput',e=>{
 const ty=e.inputType||'';
 if(ty==='insertFromPaste'||ty==='insertFromDrop'){return}
 if(ty.startsWith('delete')){n.deletes++;tick();return}
 if(ty==='insertCompositionText'){
  const d=(e.data||'').length;const delta=d-comp;comp=d;
  if(delta<0){n.deletes++}else if(delta===1){n.inserts++;n.typed_chars++}else if(delta>1){n.multi_inserts++;n.multi_chars+=delta}
  tick();return}
 if(ty==='insertText'||ty==='insertReplacementText'||ty==='insertLineBreak'||ty==='insertParagraph'){
  const d=(e.data||'');const len=(ty==='insertLineBreak'||ty==='insertParagraph')?1:Math.max(1,d.length);
  if(len>1){n.multi_inserts++;n.multi_chars+=len}else{n.inserts++;n.typed_chars++}
  tick()}
});
t.addEventListener('paste',e=>{const d=(e.clipboardData&&e.clipboardData.getData('text'))||'';n.paste_events++;n.paste_chars+=d.length;stats()});
t.addEventListener('drop',e=>{n.paste_events++;n.paste_chars+=((e.dataTransfer&&e.dataTransfer.getData('text'))||'').length;stats()});
window.addEventListener('blur',()=>{n.blurs++});
function stats(){$('#sk').textContent=n.typed_chars+n.multi_inserts;$('#sc').textContent=n.deletes;$('#sp').textContent=pauses;$('#sv').textContent=n.paste_chars;
 $('#seal').disabled=(n.typed_chars+n.multi_inserts<30)}
function draw(){const W=cv.width,H=cv.height;cx.clearRect(0,0,W,H);const sl=iv.slice(-120);const bw=W/120;
 sl.forEach((g,i)=>{const v=Math.min(g,1200)/1200;const h=Math.max(2,v*(H-6));cx.fillStyle=g>2000?'#f0d78a':(g<12?'#ff8a80':'#c9a84c');cx.globalAlpha=.35+.65*(i/sl.length);
  cx.fillRect(i*bw+1,H-h,bw-2,h)});cx.globalAlpha=1}
draw();
function norm(s){return s.normalize('NFC').replace(/\r\n?/g,'\n').trim()}
async function sha(s){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('')}
$('#seal').onclick=async()=>{
 const btn=$('#seal');btn.disabled=true;btn.textContent='Sealing…';msg('');
 if(!ch||!ch.sig){await start();if(!ch||!ch.sig){btn.disabled=false;btn.textContent='Seal it';return}}
 const text=norm(t.value);const h=await sha(text);
 const body={challenge:ch.challenge,sig:ch.sig,text_hash:h,intervals:iv,counts:Object.assign({final_length:text.length},n),viewer:viewer};
 try{const r=await fetch('/x/humankeys/seal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();
  if(r.status===402){msg(d.message||'Human Keys is 50p a month for unlimited proofs. Top up first.','err');$('#topup').style.display='inline-block';btn.disabled=false;btn.textContent='Seal it';return}
  if(!r.ok||!d.sealed){msg(d.message||d.error||'Could not seal it.','err');btn.disabled=false;btn.textContent='Seal it';return}
  render(d);wallet();btn.textContent='Sealed';
 }catch(e){msg('Could not reach sebbi.pro.','err');btn.disabled=false;btn.textContent='Seal it'}};
function render(d){const cls=d.verdict==='HUMAN_TYPED'?'':(d.verdict==='HUMAN_TYPED_PART_PASTED'?'part':'bad');const s=d.summary||{};
 const share='✓ Human typed · check it: '+d.check;
 $('#out').innerHTML='<div class="cert '+cls+'"><div class="seal"><div class="ring">'+(cls==='bad'?'!':'✓')+'</div><h2>'+d.verdict_text+'</h2></div>'+
 '<div class="code">'+d.code+'</div><div class="wallet">Sealed '+d.sealed_uk+' · block '+d.block_index+'</div>'+
 '<dl><dt>Keystrokes</dt><dd>'+s.keystrokes+'</dd><dt>Corrections</dt><dd>'+s.corrections+'</dd><dt>Thinking pauses</dt><dd>'+s.thinking_pauses+'</dd><dt>Typing time</dt><dd>'+s.typing_minutes+' min</dd><dt>Composition</dt><dd>'+s.composition_signals+'</dd><dt>Pasted</dt><dd>'+s.pasted_characters+' characters</dd></dl>'+
 '<div class="btns"><button class="btn" id="cp">Copy the proof line</button><a class="btn g" href="'+d.check+'">Open the check page</a>'+(navigator.share?'<button class="btn g" id="sh">Share</button>':'')+'</div>'+
 '<p class="wallet" style="margin-top:10px">Badge for websites: '+d.badge+'</p></div>';
 $('#cp').onclick=()=>{navigator.clipboard.writeText(share);$('#cp').textContent='Copied'};
 const sh=$('#sh');if(sh)sh.onclick=()=>navigator.share({title:'Human typed',text:share,url:d.check});
 $('#out').scrollIntoView({behavior:'smooth'})}
})();
</script></body></html>"""

CHECK_PAGE = _HEAD + r"""
<title>Check a Human Keys proof</title>
<meta name="description" content="Check whether a text was typed by a human, live. Paste it and compare it with the sealed proof. Free.">
</head><body>
<div class="top"><div class="wrap"><a class="brand" href="https://sebbi.pro/">AI<b>Leash</b> · Human Keys</a><a class="l" href="https://sebbi.pro/keys">Make a proof</a></div></div>
<div class="wrap">
<div class="hero"><div class="kick">CHECK A PROOF</div><h1>Was it typed by <em>a human?</em></h1>
<p>Enter the code, then paste the text it came with. The text is checked on your own device. Checking is free.</p></div>
<div class="card"><input id="code" placeholder="HK-XXXX-XXXX" value="__CODE__" autocapitalize="characters">
<div class="btns"><button class="btn" id="look">Look it up</button></div><div class="msg" id="msg"></div></div>
<div id="out"></div>
</div>
<footer><div class="wrap">Monop Content · <a href="https://sebbi.pro/x/humankeys/spec">How the proof works</a> · <a href="https://sebbi.pro/keys">Make your own · 50p a month</a></div></footer>
<script>
(function(){
const $=s=>document.querySelector(s);
function msg(x,c){const m=$('#msg');m.textContent=x;m.className='msg '+(c||'')}
function norm(s){return s.normalize('NFC').replace(/\r\n?/g,'\n').trim()}
async function sha(s){const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));return Array.from(new Uint8Array(b)).map(x=>x.toString(16).padStart(2,'0')).join('')}
const esc=v=>String(v==null?'—':v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let rec=null;
async function look(){const code=$('#code').value.trim().toUpperCase();if(!/^HK-[A-Z2-9]{4}-[A-Z2-9]{4}$/.test(code)){msg('Codes look like HK-7Q2M-X9KD.','err');return}
 msg('Looking it up…');try{const r=await fetch('/x/humankeys/check?code='+code);const d=await r.json();if(!r.ok){msg('No proof with that code.','err');$('#out').innerHTML='';return}
 rec=d;msg('');render()}catch(e){msg('Could not reach sebbi.pro.','err')}}
function render(){const d=rec,s=d.summary||{};const cls=d.verdict==='HUMAN_TYPED'?'':(d.verdict==='HUMAN_TYPED_PART_PASTED'?'part':'bad');
 $('#out').innerHTML='<div class="cert '+cls+'"><div class="seal"><div class="ring">'+(cls==='bad'?'!':'✓')+'</div><h2>'+esc(d.verdict_text)+'</h2></div>'+
 '<div class="code">'+esc(d.code)+'</div><div class="wallet">Sealed '+esc(d.sealed_uk)+' · <a style="color:var(--gold)" href="'+esc(d.verify_block)+'">block '+esc(d.block_index)+'</a></div>'+
 '<dl><dt>Keystrokes</dt><dd>'+esc(s.keystrokes)+'</dd><dt>Corrections</dt><dd>'+esc(s.corrections)+'</dd><dt>Thinking pauses</dt><dd>'+esc(s.thinking_pauses)+'</dd><dt>Typing time</dt><dd>'+esc(s.typing_minutes)+' min</dd><dt>Composition</dt><dd>'+esc(s.composition_signals)+'</dd><dt>Pasted</dt><dd>'+esc(s.pasted_characters)+' characters</dd><dt>Session began</dt><dd>'+esc(d.session_started_utc)+'</dd>'+(d.reference?'<dt>Linked to</dt><dd>'+esc(d.reference)+'</dd>':'')+'</dl>'+
 '<p style="margin-top:16px;color:var(--mut);font-size:14px">Paste the text this code came with:</p><textarea id="txt" style="min-height:140px;margin-top:8px"></textarea>'+
 '<div class="btns"><button class="btn" id="cmp">Check it matches</button></div><div class="msg" id="res"></div></div>';
 $('#cmp').onclick=async()=>{const h=await sha(norm($('#txt').value));const ok=h===d.text_hash;const r=$('#res');
  r.textContent=ok?'✓ Exact match. This is the text that was typed and sealed.':'✗ Not a match. This is not the text that was sealed — even one changed character shows here.';r.className='msg '+(ok?'ok':'err')}}
$('#look').onclick=look;if($('#code').value)look();
})();
</script></body></html>"""

```


## `modules/integrity.py`

1487 lines, 65650 bytes

```python
"""
modules/integrity.py  v1.4.4  -  the AI Integrity Declaration, a public checker,
                              and a sealed public register of verdicts

Serves the open standard that rates every AI deployment from L0_DIARY
(no checkable record) up to L4_OVERSIGHT_VERIFIED, and checks any domain
against it. Reads only. Seals nothing, writes nothing, creates no tables.
Every route is public.

Routes:
  https://sebbi.pro/x/integrity/status                    what this is
  https://sebbi.pro/x/integrity/declaration               the standard, as JSON
  https://sebbi.pro/x/integrity/self                      sebbi.pro's own declaration
  https://sebbi.pro/x/integrity/check?domain=example.com  rate any domain
  https://sebbi.pro/x/integrity/register                  every sealed verdict

v1.4: THE CHECKER'S OWN VERDICTS ARE NOW EVIDENCE.
Every fresh verdict is sealed into the sebbi.pro chain as a public block,
so a rating cannot be quietly changed later - not by the domain rated, and
not by sebbi.pro.

v1.4.3: THE REQUEST IS SEALED TOO, BEFORE THE CHECK RUNS.
A sealed verdict proves what the checker said, not what it left unsaid: an
inconvenient result could simply go unsealed, and from outside, silence and
never-asked look the same. Now the request is sealed first. A domain that
was asked about and has no verdict after it shows up in the register as
exactly that. (Raised by Richard Whitney, MIRegistry.) The register lists the latest sealed verdict per domain,
each with the block that holds it. A checker that rates others by whether
their records can be altered now holds its own ratings to the same rule.

HOW THE CHECKER DECIDES
It looks for a declaration at https://<domain>/.well-known/ai-integrity.json,
then https://<domain>/x/integrity/self. None found: L0_DIARY.
It never takes the declaration's word. It walks the declared chain and
recomputes every public block itself, asks each declared witness for its
tip, and opens each anchor proof. A level is awarded only when every check
that level needs has passed. Claiming more than that is OVERCLAIMED.

Human-oversight checks (INV-005, INV-006) cannot be tested from outside yet,
so this checker never awards L4. It says so rather than guessing.

SAFETY
The checker fetches addresses taken from other people's declarations, so
it only fetches https on port 443, refuses redirects, refuses any host that
resolves to a private, loopback or internal address, caps every response
size and every timeout, and caps the number of fetches per check.
"""

import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

VERSION = "1.4.4"
BASE = "https://sebbi.pro/x/integrity/"

PUBLIC = {("GET", "status"), ("GET", "declaration"), ("GET", "spec"),
          ("GET", "self"), ("GET", "check"), ("GET", "register")}

# ---------------------------------------------------------------- the standard

DECLARATION = json.loads(r'''{
  "spec": "ai-integrity-declaration",
  "version": "1.0.4",
  "declaration_id": "DEC-2026-AI-INTEGRITY",
  "status": "open_standard",
  "published": "2026-09-19",
  "issuer": {
    "name": "Monop Content",
    "product": "sebbi.pro",
    "url": "https://sebbi.pro"
  },
  "principle": "A record kept only by the party it describes is a diary, not evidence. Any AI deployment can be checked against this standard by anyone, without an account, a key, or permission.",
  "scope": "Autonomous agents and AI systems that make or support decisions affecting people, money, access or safety.",
  "maps_to": [
    {
      "framework": "EU AI Act",
      "provisions": [
        "Article 12 record-keeping",
        "Article 14 human oversight"
      ]
    },
    {
      "framework": "UK Online Safety Act 2023",
      "provisions": [
        "record-keeping and review duties"
      ]
    },
    {
      "framework": "ICO Age Appropriate Design Code",
      "provisions": [
        "data minimisation",
        "transparency"
      ]
    }
  ],
  "related": {
    "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
    "relationship": "The Ordering Test lists which checks a vendor supports and which anyone can run without an account. This declaration turns those checks into levels, so every AI deployment gets a rating whether or not it publishes."
  },
  "discovery": {
    "paths": [
      "/.well-known/ai-integrity.json",
      "/x/integrity/self"
    ],
    "rule": "Every AI deployment is rated. A verifier looks for a declaration at each path in order, over HTTPS, on the deployment's own domain. A deployment with no declaration at any of these paths is rated L0_DIARY. Absence is itself the result.",
    "absence_verdict": "L0_DIARY"
  },
  "levels": {
    "L0_DIARY": {
      "badge": "GREY",
      "meaning": "No public, independently checkable record. The operator's word is the only evidence.",
      "requires": []
    },
    "L1_SEALED": {
      "badge": "BRONZE",
      "meaning": "Every decision is sealed into a public append-only chain that anyone can walk and recompute.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-007"
      ]
    },
    "L2_WITNESSED": {
      "badge": "SILVER",
      "meaning": "Independent parties hold the chain's fingerprints, so the operator cannot rewrite history unnoticed.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-007"
      ]
    },
    "L3_ANCHORED": {
      "badge": "GOLD",
      "meaning": "The chain is also anchored to a public timestamp no single party controls.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-007"
      ]
    },
    "L4_OVERSIGHT_VERIFIED": {
      "badge": "GOLD_LIVE_VERIFIED",
      "meaning": "Human oversight is itself provable: reviewers commit before seeing the machine, and rubber-stamping is detected.",
      "requires": [
        "INV-001",
        "INV-002",
        "INV-003",
        "INV-004",
        "INV-005",
        "INV-006",
        "INV-007"
      ]
    }
  },
  "invariants": {
    "INV-001-SEALED-CHAIN": {
      "requirement": "Every decision is sealed at the moment it is made, with what it rested on, into an append-only hash chain.",
      "test": "Fetch the declared walk endpoint. Starting from genesis, recompute every public block from the served preimage and confirm each block names its parent.",
      "pass": "All public blocks recompute; all links unbroken; the tip reached equals the tip published.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-002-FINGERPRINTS-ONLY": {
      "requirement": "Raw prompts, documents and personal data stay with their owner. Only fingerprints are published. Short or guessable personal values are salted or keyed before hashing.",
      "test": "Inspect public blocks. No raw personal data, secrets or credentials appear. The declaration states the hashing method for personal values.",
      "pass": "No raw personal data in any public block; method declared.",
      "fail_verdict": "L0_DIARY"
    },
    "INV-003-INDEPENDENT-WITNESS": {
      "requirement": "At least one party independent of the operator holds the chain's tip. The declaration states how many independent parties would have to collude or fail at the same time for the history to be rewritten unnoticed.",
      "independence": "A witness is independent when the operator cannot alter, delete or withhold the witness's record of the tip. Payment does not by itself break independence; control does. Any commercial relationship between operator and witness is disclosed in the declaration.",
      "witness_strength": {
        "sealed": "The witness sealed the tip inside its own hash chain, and the checker recomputed that block and found the tip in it.",
        "bound": "The witness recorded the tip against a position in its own anchored chain, which dates the record but does not seal it.",
        "listed": "The witness publishes the tip, with nothing in its own chain binding the record.",
        "note": "Strength is reported for every passing witness. It does not yet change the level; it will be graded from 1.1.0. A witness can climb from listed to bound to sealed, and the declaration shows which it is."
      },
      "test": "Query each declared witness. Its recorded tip must appear in the operator's chain at the position it claims.",
      "pass": "At least one independent witness confirms; the collusion threshold is disclosed.",
      "fail_verdict": "L1_SEALED"
    },
    "INV-004-PUBLIC-TIME-ANCHOR": {
      "requirement": "Chain tips are anchored to a public timestamp no single party controls, such as OpenTimestamps on Bitcoin.",
      "test": "Verify the anchor proof offline against the tip it names.",
      "pass": "Proof commits to a tip present in the chain.",
      "fail_verdict": "L2_WITNESSED"
    },
    "INV-005-COMMIT-BEFORE-REVEAL": {
      "requirement": "Where a human reviews an AI decision, the reviewer's verdict is sealed before the machine's verdict is shown to them.",
      "test": "For each reviewed case, the reviewer's sealed commitment sits in an earlier block than the reveal of the machine verdict.",
      "pass": "Every reviewed case shows commit before reveal.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-006-ANTI-RUBBER-STAMP": {
      "requirement": "Review behaviour that indicates rubber-stamping is detected and sealed.",
      "parameters": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98,
        "window": "rolling 30 days, per reviewer"
      },
      "test": "Any reviewer approving in under minimum_review_seconds, or agreeing with the machine more often than maximum_agreement_rate across the window, has a flag sealed into the chain.",
      "pass": "Flags are raised and sealed whenever the thresholds are crossed; the thresholds in use are declared.",
      "fail_verdict": "L3_ANCHORED"
    },
    "INV-007-DISCLOSED-DISCONTINUITY": {
      "requirement": "Where the chain is reset, or the meaning of a field or the referent of an identifier changes after records using it have been sealed, the change is sealed into the record itself with the date it took effect. Records sealed under the earlier meaning remain valid under that meaning and are never silently repaired.",
      "test": "Every discontinuity or change of meaning is disclosed either as a block sealed in the chain, or in the declaration with the kind of change and the evidence a verifier can use to detect it. Where the checker can detect a discontinuity itself (for example records sealed long after the window they cover), an undisclosed one fails.",
      "detection_rule": "A discontinuity that is detected rather than asserted states the rule that detected it (for example \"createdAt - rangeEnd > 2 hours\"), so any verifier can recount it and get the same number. Where a rule is declared, the checker applies that rule rather than its own and reports whether it reproduces the declared count. In 1.0.3 a missing rule is reported; from 1.1.0 it fails.",
      "detection_rule_location": "Inside the discontinuity it describes: discontinuities[].detection_rule, beside that entry's own counts (checkpoints, through_seq). A rule anywhere else is not read.",
      "pass": "Every discontinuity is disclosed in the chain.",
      "fail_verdict": "L0_DIARY"
    }
  },
  "verifier_rules": [
    "Never accept an operator's own statement that its record is valid. Recompute.",
    "A verifier assigns the highest level whose every required invariant passes.",
    "If a declaration claims a higher level than verification supports, the verdict is OVERCLAIMED, shown alongside the verified level.",
    "A declaration that cannot be fetched, or cannot be parsed, is rated L0_DIARY."
  ],
  "declaration_template": {
    "spec": "ai-integrity-declaration",
    "version": "1.0.0",
    "organisation": "",
    "system": "",
    "claimed_level": "",
    "chain": {
      "walk_endpoint": "",
      "genesis_hash": "",
      "seal_method_url": ""
    },
    "personal_data_hashing": "",
    "witnesses": [
      {
        "name": "",
        "tip_endpoint": ""
      }
    ],
    "collusion_threshold": 0,
    "anchor": {
      "method": "",
      "proof_endpoint": ""
    },
    "oversight": {
      "commit_before_reveal": false,
      "anti_rubber_stamp": {
        "minimum_review_seconds": 1.5,
        "maximum_agreement_rate": 0.98
      }
    },
    "discontinuities": [
      {
        "date": "",
        "disclosure_block": "",
        "kind": "",
        "detail": ""
      }
    ],
    "known_gaps": []
  },
  "not_yet_rated": {
    "availability": "Every level answers 'has this been altered'. None yet answers 'will this still be served'. Until a level for availability is defined, declare availability limits in known_gaps."
  },
  "reference_implementation": {
    "name": "sebbi.pro",
    "walk": "https://sebbi.pro/x/walk/status",
    "method": "https://sebbi.pro/x/walk/spec",
    "genesis": "https://sebbi.pro/x/walk/genesis",
    "discontinuity_example": "https://sebbi.pro/x/walk/block?index=2013"
  },
  "changelog": [
    {
      "version": "1.0.1",
      "date": "2026-09-20",
      "change": "Added /x/integrity/self as a second discovery path, for deployments whose server cannot serve /.well-known. Added the public checker."
    },
    {
      "version": "1.0.4",
      "date": "2026-09-20",
      "change": "Fixed where detection_rule lives: inside its discontinuity, beside the counts it produces. Where a rule is declared, the checker now reports the count under that rule first and its own default second, instead of leading with its default. Check requests are now sealed before the check runs, so a request with no verdict after it is visible in the register. Both raised by Richard Whitney (MIRegistry)."
    },
    {
      "version": "1.0.3",
      "date": "2026-09-20",
      "change": "detection_rule for detected discontinuities, applied by the checker to recount the declared figure. Witness strength (sealed, bound, listed) reported for every witness. Both raised by Richard Whitney (MIRegistry). Every fresh checker verdict is now sealed into the sebbi.pro chain and listed in a public register, so ratings themselves cannot be quietly altered."
    },
    {
      "version": "1.0.2",
      "date": "2026-09-20",
      "change": "Defined witness independence (control, not payment). INV-007 accepts discontinuities disclosed in the declaration with detection evidence, and fails undisclosed ones the checker can detect. Added known_gaps and the unrated availability axis. All three raised by Richard Whitney (MIRegistry) while writing the first external declaration."
    }
  ],
  "public_checker": "https://sebbi.pro/x/integrity/check?domain=example.com",
  "public_register": "https://sebbi.pro/x/integrity/register"
}''')

_CANONICAL = json.dumps(DECLARATION, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False)
DECLARATION_SHA256 = hashlib.sha256(_CANONICAL.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------- our own declaration
#
# sebbi.pro's own claim. Kept honest: it claims only what the checker can
# confirm today. To move up a level, add a witness below - an address run
# by someone else that returns the sebbi.pro tip they hold - and raise
# claimed_level only once the checker agrees.

SELF_WITNESSES = [
    {"name": "MIR (MIRegistry)",
     "tip_endpoint": "https://mir.events/v1/transparency/held/tips?peer=sebbi",
     "note": "MIR records each sebbi.pro tip it observes against its own "
             "anchored chain position and never refreshes an entry. As MIR "
             "states in its own payload, these observations are bound to an "
             "anchored MIR tip, not sealed inside MIR's merkle root."},
]

SELF = {
    "spec": "ai-integrity-declaration",
    "version": "1.0.3",
    "organisation": "Monop Content",
    "system": "sebbi.pro",
    "claimed_level": "L3_ANCHORED",
    "chain": {
        "walk_endpoint": "https://sebbi.pro/x/walk/blocks",
        "genesis_hash": "534f9e5cefb1a48566674911262151f34eedc1e6840a094d9465af4d846972c6",
        "seal_method_url": "https://sebbi.pro/x/walk/spec",
    },
    "personal_data_hashing": "Customer decisions are never published. Blocks sealed under a customer key, from non-public sources, or carrying anything secret-shaped are served without payload; only their hash and link are public.",
    "witnesses": SELF_WITNESSES,
    "collusion_threshold": 1,
    "collusion_note": "One: only witnesses a machine can verify are counted. Other chains witness sebbi.pro but do not yet publish a list the checker can read, so they are not counted.",
    "held_for_others": "https://sebbi.pro/x/held/peers",
    "anchor": {
        "method": "OpenTimestamps on Bitcoin",
        "proof_endpoint": "https://sebbi.pro/x/ots/latest_confirmed",
        "status_url": "https://sebbi.pro/x/ots/status",
        "note": "Tips are stamped hourly. proof_endpoint always serves the newest proof that is confirmed in Bitcoin and whose tip is a block in the current chain. Anchoring is not claimed until the checker verifies it.",
    },
    "oversight": {
        "commit_before_reveal": True,
        "demonstration": "https://sebbi.pro/x/demo/review",
        "anti_rubber_stamp": {"minimum_review_seconds": 1.5,
                              "maximum_agreement_rate": 0.98},
    },
    "discontinuities": [
        {"date": "2026-09-07", "disclosure_block": 2013, "kind": "chain_reset",
         "detail": "The chain restarted from genesis. The reset is sealed in block 2013; block indexes quoted before that date belong to the earlier chain."},
    ],
    "known_gaps": [
        "Availability: every level answers 'has this been altered', none yet answers 'will this still be served'. A reader currently depends on sebbi.pro continuing to serve these endpoints.",
        "Anchoring: tips are stamped to Bitcoin hourly and confirm a few hours later, so the newest hour or so rests on witnessing until its proof confirms.",
    ],
}

# ---------------------------------------------------------------- safe fetching

FETCH_TIMEOUT = 8
MAX_DECL_BYTES = 262144
MAX_PAGE_BYTES = 8 * 1024 * 1024
MAX_FETCHES = 45
WALK_PAGE = 500
WALK_MAX_BLOCKS = 20000
CHECK_BUDGET_SECONDS = 60
CACHE_SECONDS = 600
USER_AGENT = "sebbi-integrity-checker/1.4.4 (+https://sebbi.pro/x/integrity/status)"

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home",
                     ".corp", ".intranet", ".arpa")

_cache = {}
_cache_lock = threading.Lock()
_running = threading.BoundedSemaphore(2)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code,
                                     "redirect refused", headers, fp)


_OPENER = urllib.request.build_opener(_NoRedirect)


class _Budget(object):
    def __init__(self):
        self.fetches = 0
        self.deadline = time.time() + CHECK_BUDGET_SECONDS

    def spend(self):
        self.fetches += 1
        if self.fetches > MAX_FETCHES:
            raise RuntimeError("fetch limit reached")
        if time.time() > self.deadline:
            raise RuntimeError("time limit reached")


def _clean_domain(raw):
    d = str(raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split("?")[0].split("#")[0]
    if "@" in d or ":" in d:
        return None
    d = d.rstrip(".")
    if not _HOST_RE.match(d):
        return None
    if d == "localhost" or d.endswith(_BLOCKED_SUFFIXES):
        return None
    return d


def _host_is_public(host):
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "does not resolve"
    if not infos:
        return False, "does not resolve"
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False, "unreadable address"
        if (ip.is_private or ip.is_loopback or ip.is_link_local or
                ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False, "resolves to a non-public address"
    return True, None


def _safe_url(url):
    try:
        p = urllib.parse.urlsplit(str(url))
    except Exception:
        return None, "unreadable address"
    if p.scheme != "https":
        return None, "only https addresses are fetched"
    if p.port not in (None, 443):
        return None, "only port 443 is fetched"
    if p.username or p.password:
        return None, "addresses with credentials are refused"
    host = _clean_domain(p.hostname or "")
    if not host:
        return None, "not a public domain name"
    ok, why = _host_is_public(host)
    if not ok:
        return None, why
    return urllib.parse.urlunsplit(("https", host, p.path or "/", p.query, "")), None


def _fetch_raw(url, budget, max_bytes=MAX_DECL_BYTES, accept="application/json"):
    """Returns (bytes, error). Never raises."""
    safe, why = _safe_url(url)
    if not safe:
        return None, why
    try:
        budget.spend()
    except RuntimeError as exc:
        return None, str(exc)
    req = urllib.request.Request(safe, headers={
        "User-Agent": USER_AGENT, "Accept": accept})
    try:
        with _OPENER.open(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        return None, "HTTP %s" % exc.code
    except Exception as exc:
        return None, "could not fetch (%s)" % exc.__class__.__name__
    if len(raw) > max_bytes:
        return None, "response too large"
    return raw, None


def _fetch_json(url, budget, max_bytes=MAX_DECL_BYTES, allow_text=False):
    """Returns (data, error). Never raises.

    allow_text: if the response is not JSON (an ordinary web page), return
    {"_text": <page text>} instead of an error, so a witness can publish its
    record as a normal page."""
    raw, err = _fetch_raw(url, budget, max_bytes)
    if err:
        return None, err
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text), None
    except Exception:
        if allow_text:
            return {"_text": text}, None
        return None, "not valid JSON"


# ---------------------------------------------------------------- checks

_HEX64 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")
WITNESS_MAX_BYTES = 2 * 1024 * 1024
_SECRET_SHAPES = [
    ("api key", re.compile(r"\b(?:al|sb|se)_live_[0-9a-f]{16,}")),
    ("api key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("cloud key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("access token", re.compile(r"\b(?:ghp|gho|xox[abp])[_-][A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"BEGIN [A-Z ]*PRIVATE KEY")),
    ("email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
]


_ZERO64 = "0" * 64
BACKFILL_HOURS = 6

_RULE_RE = re.compile(
    r"createdAt\s*-\s*rangeEnd\s*(>=|>)\s*([0-9]+(?:\.[0-9]+)?)\s*"
    r"(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", re.I)


def _parse_rule(text):
    """'createdAt - rangeEnd > 2 hours' -> (op, seconds) or None."""
    m = _RULE_RE.search(str(text or ""))
    if not m:
        return None
    n = float(m.group(2))
    unit = m.group(3).lower()
    mult = 3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1
    return m.group(1), n * mult


def _recount(meta, op, seconds):
    count, through = 0, None
    for seq in sorted(meta):
        cp = meta[seq]
        c, r = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if c is None or r is None:
            continue
        lag = c - r
        if (lag >= seconds) if op == ">=" else (lag > seconds):
            count += 1
            through = seq
    return count, through


def _iso_ts(v):
    try:
        return time.mktime(time.strptime(str(v)[:19], "%Y-%m-%dT%H:%M:%S")) \
            - time.timezone
    except Exception:
        return None


def _walk(endpoint, budget):
    """Walk a declared chain and recompute it.

    Two published formats are understood:
      blocks       the sebbi.pro walk format (https://sebbi.pro/x/walk/spec)
      checkpoints  the MIR checkpoint format (seq/tip/prevTip, newest first)
    The format is detected from what the endpoint serves, never assumed."""
    first, err = _fetch_json(endpoint, budget, MAX_PAGE_BYTES)
    if err:
        out = _empty_walk(endpoint)
        out["first_problem"] = "could not read walk endpoint: %s" % err
        return out, {}, {}, {}
    if isinstance(first, dict) and isinstance(first.get("checkpoints"), list):
        return _walk_checkpoints(endpoint, first, budget)
    if isinstance(first, dict) and isinstance(first.get("blocks"), list):
        return _walk_blocks(endpoint, budget)
    out = _empty_walk(endpoint)
    out["first_problem"] = ("endpoint serves neither the blocks nor the "
                            "checkpoints walk format")
    return out, {}, {}, {}


def _empty_walk(endpoint):
    return {"endpoint": endpoint, "format": None, "blocks": 0,
            "public_recomputed": 0, "withheld_linkage_only": 0,
            "complete": False, "genesis_prev_is_GENESIS": None,
            "first_problem": None, "tip": None}


def _walk_blocks(endpoint, budget):
    out = _empty_walk(endpoint)
    out["format"] = "blocks"
    hashes = {}
    public_text = {}
    prev = "GENESIS"
    after = 0
    base = endpoint.split("?")[0]
    while True:
        url = "%s?after=%d&limit=%d" % (base, after, WALK_PAGE)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page after block %d: %s" % (after, err))
            break
        blocks = page.get("blocks") if isinstance(page, dict) else None
        if not isinstance(blocks, list):
            out["first_problem"] = "endpoint does not serve the walk format"
            break
        if after == 0:
            first_prev = page.get("previous_audit_hash")
            out["genesis_prev_is_GENESIS"] = (first_prev == "GENESIS")
        for b in blocks:
            idx = b.get("block_index")
            h = str(b.get("audit_hash") or "")
            if "preimage" in b:
                pre = b.get("preimage")
                if not isinstance(pre, str) or \
                        hashlib.sha256(pre.encode("utf-8")).hexdigest() != h:
                    out["first_problem"] = out["first_problem"] or (
                        "block %s does not recompute" % idx)
                try:
                    stated_prev = json.loads(pre).get("prev_hash")
                except Exception:
                    stated_prev = None
                out["public_recomputed"] += 1
                public_text[idx] = pre
            else:
                stated_prev = b.get("prev_hash")
                out["withheld_linkage_only"] += 1
            if stated_prev != prev:
                out["first_problem"] = out["first_problem"] or (
                    "block %s does not link to the block before it" % idx)
            prev = h
            hashes[h] = idx
            out["blocks"] += 1
        if out["blocks"] >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d blocks; the checker walks at most %d"
                % (out["blocks"], WALK_MAX_BLOCKS))
            break
        if not page.get("has_more"):
            out["complete"] = True
            break
        nxt = page.get("next_after")
        if not isinstance(nxt, int) or nxt <= after:
            out["first_problem"] = out["first_problem"] or "paging did not advance"
            break
        after = nxt
    out["tip"] = prev if out["blocks"] else None
    return out, hashes, public_text, {}


def _walk_checkpoints(endpoint, first, budget):
    """MIR format: tip = sha256(seq:rangeStart:rangeEnd:eventCount:
    merkleRoot:prevTip), newest first, paged backwards with beforeSeq."""
    out = _empty_walk(endpoint)
    out["format"] = "checkpoints"
    base = endpoint.split("?")[0]
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(endpoint).query))
    limit = q.get("limit", "200")
    rows = {}
    page = first
    while True:
        cps = page.get("checkpoints") if isinstance(page, dict) else None
        if not isinstance(cps, list) or not cps:
            break
        for cp in cps:
            try:
                rows[int(cp.get("seq"))] = cp
            except (TypeError, ValueError):
                out["first_problem"] = out["first_problem"] or \
                    "a checkpoint has no readable seq"
        lowest = min(int(c.get("seq")) for c in cps
                     if str(c.get("seq", "")).lstrip("-").isdigit())
        if lowest <= 0:
            break
        if len(rows) >= WALK_MAX_BLOCKS:
            out["first_problem"] = out["first_problem"] or (
                "stopped at %d checkpoints; the checker walks at most %d"
                % (len(rows), WALK_MAX_BLOCKS))
            break
        url = "%s?limit=%s&beforeSeq=%d" % (base, limit, lowest)
        page, err = _fetch_json(url, budget, MAX_PAGE_BYTES)
        if err:
            out["first_problem"] = out["first_problem"] or (
                "could not read page before seq %d: %s" % (lowest, err))
            break

    hashes, public_text, meta = {}, {}, {}
    backfilled, backfill_through = 0, None
    prev = _ZERO64
    seqs = sorted(rows)
    if seqs and seqs[0] != 0:
        out["first_problem"] = out["first_problem"] or \
            "walk did not reach genesis (seq 0)"
    for n, seq in enumerate(seqs):
        cp = rows[seq]
        if n and seq != seqs[n - 1] + 1:
            out["first_problem"] = out["first_problem"] or \
                "gap in seq before %d" % seq
        tip = str(cp.get("tip") or "").lower()
        pre = ":".join([str(seq), str(cp.get("rangeStart")),
                        str(cp.get("rangeEnd")), str(cp.get("eventCount")),
                        str(cp.get("merkleRoot")), str(cp.get("prevTip"))])
        if hashlib.sha256(pre.encode("utf-8")).hexdigest() != tip:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not recompute" % seq
        if str(cp.get("prevTip") or "").lower() != prev:
            out["first_problem"] = out["first_problem"] or \
                "checkpoint %d does not link to the one before it" % seq
        if seq == 0:
            out["genesis_prev_is_GENESIS"] = \
                (str(cp.get("prevTip") or "") == _ZERO64)
        created, rend = _iso_ts(cp.get("createdAt")), _iso_ts(cp.get("rangeEnd"))
        if created is not None and rend is not None and \
                created - rend > BACKFILL_HOURS * 3600:
            backfilled += 1
            backfill_through = seq
        prev = tip
        hashes[tip] = seq
        public_text[seq] = json.dumps(cp, sort_keys=True)
        meta[seq] = cp
        out["public_recomputed"] += 1
        out["blocks"] += 1
    out["complete"] = bool(seqs) and seqs[0] == 0 and not out["first_problem"]
    out["tip"] = prev if seqs else None
    out["backfill_detected"] = {
        "checkpoints": backfilled, "through_seq": backfill_through,
        "rule": "checker default: sealed more than %d hours after the window "
                "it covers" % BACKFILL_HOURS,
        "note": "Where the declaration states its own detection_rule, the "
                "count under that rule is in INV-007."}
    return out, hashes, public_text, meta


def _hex_values(obj, found=None):
    found = found if found is not None else set()
    if isinstance(obj, dict):
        for v in obj.values():
            _hex_values(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _hex_values(v, found)
    elif isinstance(obj, str):
        for m in _HEX64.findall(obj.lower()):
            found.add(m)
    return found


def _anchor_check(proof_endpoint, hashes, budget, meta=None):
    if not proof_endpoint:
        return "fail", "no anchor proof address declared"
    tip, raw = None, None
    if "{seq}" in proof_endpoint:
        done = [sq for sq, cp in (meta or {}).items()
                if str(cp.get("otsStatus")) in ("upgraded", "confirmed")]
        if not done:
            return "fail", "no checkpoint is marked as anchored"
        seq = max(done)
        tip = str(meta[seq].get("tip") or "").lower()
        raw, err = _fetch_raw(proof_endpoint.replace("{seq}", str(seq)),
                              budget, MAX_DECL_BYTES, "*/*")
        if err:
            return "fail", "could not read anchor proof: %s" % err
        if raw[:1] in (b"{", b"["):
            try:
                data = json.loads(raw.decode("utf-8"))
                import base64
                raw = base64.b64decode(data.get("ots_base64") or "")
            except Exception:
                return "fail", "anchor proof could not be read"
    else:
        data, err = _fetch_json(proof_endpoint, budget)
        if err:
            return "fail", "could not read anchor proof: %s" % err
        tip = str(data.get("tip") or "").lower() if isinstance(data, dict) else ""
        b64 = data.get("ots_base64") if isinstance(data, dict) else None
        if not b64:
            return "fail", "no proof bytes served (expected ots_base64)"
        import base64
        try:
            raw = base64.b64decode(b64)
        except Exception:
            return "fail", "anchor proof could not be read"
    if not tip or tip not in hashes:
        return "fail", "the anchored tip is not in the walked chain"
    try:
        from opentimestamps.core.serialize import BytesDeserializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
        from opentimestamps.core.notary import BitcoinBlockHeaderAttestation
    except Exception:
        return "untested", "proof reader not available on this checker"
    try:
        det = DetachedTimestampFile.deserialize(BytesDeserializationContext(raw))
    except Exception:
        return "fail", "anchor proof could not be read"
    tb = bytes.fromhex(tip)
    candidates = (hashlib.sha256(tb).digest(), tb,
                  hashlib.sha256(tip.encode("ascii")).digest())
    if det.file_digest not in candidates:
        return "fail", "anchor proof is for a different value than the tip it names"
    heights = []

    def walk(ts):
        for att in ts.attestations:
            if isinstance(att, BitcoinBlockHeaderAttestation):
                heights.append(att.height)
        for _, sub in ts.ops.items():
            walk(sub)
    try:
        walk(det.timestamp)
    except Exception:
        return "fail", "anchor proof could not be walked"
    if not heights:
        return "fail", "anchor proof is still pending, not yet in Bitcoin"
    return "pass", ("proof commits a chain tip to Bitcoin block %s; the block "
                    "header itself is not re-checked here - run ots verify "
                    "to confirm against Bitcoin" % min(heights))


def _is_declaration(data):
    spec = str(data.get("spec") or "")
    return spec == "ai-integrity-declaration" or \
        spec.rstrip("/").endswith("/x/integrity/declaration")


def _witness_strength(data, held, budget):
    """sealed / bound / listed - how the witness binds its record."""
    rows = []
    if isinstance(data, dict):
        for key in ("tips", "held", "observations", "entries"):
            if isinstance(data.get(key), list):
                rows = data[key]
                break
    row = None
    for r in rows:
        if isinstance(r, dict) and \
                str(r.get("peer_tip") or r.get("tip") or "").lower() in held:
            row = r
            break
    if row is None:
        return {"grade": "listed",
                "why": "tip found on the witness's page; no binding record read"}
    tip = str(row.get("peer_tip") or row.get("tip") or "").lower()
    blk_url, blk_hash = row.get("check_block"), row.get("sealed_block_hash")
    if blk_url and blk_hash:
        page, err = _fetch_json(blk_url, budget)
        blk = page.get("block") if isinstance(page, dict) else None
        pre = blk.get("preimage") if isinstance(blk, dict) else None
        if isinstance(pre, str) and tip in pre.lower() and \
                hashlib.sha256(pre.encode("utf-8")).hexdigest() == \
                str(blk_hash).lower():
            return {"grade": "sealed",
                    "why": "the witness's own block was recomputed and "
                           "contains the tip",
                    "witness_block": blk_url}
        return {"grade": "listed",
                "why": "a sealed block was claimed but could not be "
                       "recomputed here (%s)" % (err or "mismatch")}
    if row.get("our_tip_at_observation") or row.get("witness_tip_at_observation"):
        return {"grade": "bound",
                "why": "recorded against a position in the witness's own "
                       "anchored chain; dated, not sealed"}
    return {"grade": "listed",
            "why": "published with nothing binding it in the witness's chain"}


_ORDER = ["L0_DIARY", "L1_SEALED", "L2_WITNESSED", "L3_ANCHORED",
          "L4_OVERSIGHT_VERIFIED"]


def _check(domain):
    budget = _Budget()
    result = {"domain": domain, "checked_at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "checker_version": VERSION,
        "standard": BASE + "declaration"}

    decl, found_at, tried = None, None, []
    for path in DECLARATION["discovery"]["paths"]:
        url = "https://%s%s" % (domain, path)
        data, err = _fetch_json(url, budget)
        tried.append({"url": url, "result": err or "found"})
        if data is not None and isinstance(data, dict) and \
                _is_declaration(data):
            decl, found_at = data, url
            break
        if data is not None and not err:
            tried[-1]["result"] = "not an ai-integrity-declaration"
    result["looked_at"] = tried

    if decl is None:
        result.update({
            "verified_level": "L0_DIARY", "badge": "GREY",
            "verdict": "No declaration found. Under the standard, silence is "
                       "a rating: L0_DIARY, the operator's word is the only "
                       "evidence.",
            "how_to_improve": "Publish a declaration at https://%s/.well-known/"
                              "ai-integrity.json using the declaration_template "
                              "in %s" % (domain, BASE + "declaration")})
        return result

    result["declaration_url"] = found_at
    result["declaration_sha256"] = hashlib.sha256(json.dumps(
        decl, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode("utf-8")).hexdigest()
    claimed = str(decl.get("claimed_level") or "")
    result["claimed_level"] = claimed or None
    checks = {}

    # INV-001 and INV-007 need the chain.
    chain = decl.get("chain") or {}
    endpoint = chain.get("walk_endpoint")
    hashes, public_text, walk, meta = {}, {}, None, {}
    if not endpoint:
        checks["INV-001"] = {"result": "fail", "why": "no walk_endpoint declared"}
    else:
        walk, hashes, public_text, meta = _walk(endpoint, budget)
        ok = (walk["complete"] and walk["blocks"] > 0 and
              walk["genesis_prev_is_GENESIS"] and not walk["first_problem"])
        genesis_ok = True
        declared_genesis = str(chain.get("genesis_hash") or "").lower()
        if declared_genesis and hashes:
            first = min(hashes.items(), key=lambda kv: kv[1] if isinstance(kv[1], int) else 0)
            genesis_ok = (first[0] == declared_genesis)
        checks["INV-001"] = {
            "result": "pass" if (ok and genesis_ok) else "fail",
            "why": walk["first_problem"] or (
                None if genesis_ok else "declared genesis_hash is not the first block"),
            "walk": walk}

    # INV-002: no secret-shaped or personal values in public blocks.
    hits = []
    for idx, text in public_text.items():
        for label, rx in _SECRET_SHAPES:
            if rx.search(text):
                hits.append({"block_index": idx, "found": label})
                break
        if len(hits) >= 10:
            break
    if not decl.get("personal_data_hashing"):
        checks["INV-002"] = {"result": "fail",
                             "why": "personal_data_hashing not declared"}
    elif not public_text:
        checks["INV-002"] = {"result": "fail",
                             "why": "no public records to inspect"}
    elif hits:
        checks["INV-002"] = {"result": "fail",
                             "why": "public blocks contain values that look "
                                    "personal or secret (values not repeated here)",
                             "blocks": hits}
    else:
        checks["INV-002"] = {"result": "pass",
                             "why": "%d public blocks inspected; nothing "
                                    "personal or secret-shaped found"
                                    % len(public_text)}

    # INV-007: every discontinuity is disclosed - sealed in the chain, or
    # declared with the evidence to detect it - and anything the checker
    # can detect for itself must have been declared.
    discs = decl.get("discontinuities") or []
    missing, sealed, declared = [], 0, []
    for disc in discs:
        if not isinstance(disc, dict):
            missing.append(str(disc))
            continue
        blk = disc.get("disclosure_block")
        if blk not in (None, ""):
            try:
                blk = int(blk)
            except (TypeError, ValueError):
                missing.append(str(blk))
                continue
            if blk in public_text:
                sealed += 1
            else:
                missing.append(str(blk))
        elif disc.get("kind") and disc.get("detail"):
            declared.append(str(disc.get("kind")))
        else:
            missing.append("an entry with neither a disclosure_block nor kind and detail")
    undisclosed = None
    bf = (walk or {}).get("backfill_detected") or {}
    if bf.get("checkpoints"):
        claimed_bf = [d for d in discs if isinstance(d, dict) and
                      "backfill" in str(d.get("kind", "")).lower()]
        if not claimed_bf:
            undisclosed = ("%d checkpoints were sealed long after the window "
                           "they cover, and no backfill is declared"
                           % bf["checkpoints"])
    if checks["INV-001"]["result"] != "pass":
        checks["INV-007"] = {"result": "fail", "why": "chain could not be verified"}
    elif missing:
        checks["INV-007"] = {"result": "fail",
                             "why": "declared disclosures not found: %s"
                                    % ", ".join(missing)}
    elif undisclosed:
        checks["INV-007"] = {"result": "fail", "why": undisclosed}
    else:
        parts = []
        if sealed:
            parts.append("%d sealed in the chain" % sealed)
        if declared:
            parts.append("%d declared with detection evidence (%s)"
                         % (len(declared), ", ".join(declared)))
        checks["INV-007"] = {
            "result": "pass",
            "why": ("discontinuities disclosed: " + "; ".join(parts))
                   if parts else "no discontinuities declared, and none detected"}
        checker_default = None
        if bf.get("checkpoints"):
            checker_default = {
                "backfilled_checkpoints": bf["checkpoints"],
                "through_seq": bf["through_seq"],
                "rule": str(bf.get("rule")),
                "note": "The checker's own threshold, used only when no rule "
                        "is declared. Shown for comparison."}
        recounts = []
        for d in discs:
            if not isinstance(d, dict) or \
                    "backfill" not in str(d.get("kind", "")).lower():
                continue
            rule_text = d.get("detection_rule") or d.get("detectionRule")
            entry = {"kind": d.get("kind"), "declared_rule": rule_text,
                     "declared_count": d.get("checkpoints") or d.get("count"),
                     "declared_through_seq": d.get("through_seq")}
            parsed = _parse_rule(rule_text) if rule_text else None
            if not rule_text:
                entry["result"] = "rule_missing"
                entry["note"] = ("No detection_rule declared. Reported in "
                                 "1.0.3; from 1.1.0 this fails.")
            elif not parsed or not meta:
                entry["result"] = "rule_unreadable"
                entry["note"] = ("The declared rule could not be applied "
                                 "automatically. Reported, not failed.")
            else:
                n, through = _recount(meta, parsed[0], parsed[1])
                entry["recounted_under_declared_rule"] = n
                entry["recounted_through_seq"] = through
                try:
                    ok = int(entry["declared_count"]) == n
                except (TypeError, ValueError):
                    ok = None
                entry["reproduces"] = ok
                entry["result"] = ("reproduced" if ok else
                                   "differs" if ok is False else "recounted")
            recounts.append(entry)
        applied = [r for r in recounts
                   if r.get("result") in ("reproduced", "differs", "recounted")]
        if applied:
            a = applied[0]
            checks["INV-007"]["independently_detected"] = {
                "backfilled_checkpoints": a.get("recounted_under_declared_rule"),
                "through_seq": a.get("recounted_through_seq"),
                "rule": "declared: " + str(a.get("declared_rule")),
                "reproduces_declared_count": a.get("reproduces"),
                "note": "Recounted by the checker from createdAt against "
                        "rangeEnd, under the rule the declaration states. "
                        "Nothing taken on trust."}
            if checker_default:
                checks["INV-007"]["checker_default_for_comparison"] = checker_default
        elif checker_default:
            checks["INV-007"]["independently_detected"] = checker_default
        if recounts:
            checks["INV-007"]["detection_rule_recount"] = recounts

    # INV-003: at least one declared witness holds a tip that is in our chain.
    witnesses = decl.get("witnesses") or []
    witness_results = []
    for w in witnesses[:5]:
        if not isinstance(w, dict) or not w.get("tip_endpoint"):
            continue
        data, err = _fetch_json(w.get("tip_endpoint"), budget,
                                WITNESS_MAX_BYTES, allow_text=True)
        if err:
            witness_results.append({"name": w.get("name"), "result": "fail",
                                    "why": err})
            continue
        held = _hex_values(data) & set(hashes.keys())
        entry = {
            "name": w.get("name"),
            "url": w.get("tip_endpoint"),
            "result": "pass" if held else "fail",
            "why": "publishes %d hash(es) that are blocks in the chain"
                   % len(held) if held else
                   "published no value found in the chain"}
        if held:
            entry["matched_blocks"] = sorted(
                hashes[h] for h in held if isinstance(hashes.get(h), int))[-5:]
            entry["witness_strength"] = _witness_strength(data, held, budget)
        witness_results.append(entry)
    if any(r["result"] == "pass" for r in witness_results):
        checks["INV-003"] = {"result": "pass", "witnesses": witness_results,
                             "collusion_threshold_declared":
                                 decl.get("collusion_threshold"),
                             "note": "Independence of each witness is as "
                                     "declared; the checker confirms they "
                                     "hold the tip, not who runs them."}
    else:
        checks["INV-003"] = {"result": "fail",
                             "why": "no declared witness confirmed a tip in "
                                    "the chain" if witness_results else
                                    "no witnesses declared",
                             "witnesses": witness_results}

    # INV-004: an anchor proof committing a chain tip to Bitcoin.
    anchor = decl.get("anchor") or {}
    res, why = _anchor_check(anchor.get("proof_endpoint"), hashes, budget, meta)
    checks["INV-004"] = {"result": res, "why": why}

    # INV-005 / INV-006 cannot be tested from outside yet.
    for inv in ("INV-005", "INV-006"):
        checks[inv] = {"result": "untested",
                       "why": "human-oversight checks cannot yet be tested "
                              "from outside; this checker never awards L4"}

    level = "L0_DIARY"
    for name in _ORDER[1:]:
        needs = [r.split("-")[0] + "-" + r.split("-")[1]
                 for r in DECLARATION["levels"][name]["requires"]]
        if all(checks.get(n, {}).get("result") == "pass" for n in needs):
            level = name
        else:
            break

    if decl.get("known_gaps"):
        result["known_gaps_declared"] = decl.get("known_gaps")
    result["checks"] = checks
    result["verified_level"] = level
    result["badge"] = DECLARATION["levels"][level]["badge"]
    if claimed in _ORDER and _ORDER.index(claimed) > _ORDER.index(level):
        result["verdict"] = "OVERCLAIMED: declares %s, verifies as %s." % (claimed, level)
        result["overclaimed"] = True
    else:
        result["verdict"] = "Verifies as %s." % level
        result["overclaimed"] = False
    result["rule"] = ("Nothing in the declaration was taken on trust. Every "
                      "pass above was recomputed or fetched by this checker.")
    return result


VERDICT_USER = "system_integrity_verdict"
VERDICT_RESEAL_SECONDS = 24 * 3600
VERDICT_MAX_PER_HOUR = 30
_seal_times = []
_seal_lock = threading.Lock()


def _verdict_fingerprint(out):
    return (out.get("verified_level"), out.get("claimed_level"),
            out.get("overclaimed"), bool(out.get("error")))


def _verdict_ref(idx, h):
    return {"block_index": idx, "audit_hash": h,
            "check_block": ("https://sebbi.pro/x/walk/block?index=%s" % idx)
            if idx is not None else None}


def _already_sealed(conn, domain, fp, now):
    """The chain itself is the memory: find a verdict for this domain,
    sealed today (UTC), with the same outcome. Per UTC day, like requests,
    so each day's first request is always followed by a verdict."""
    rows = conn.execute(
        "SELECT id, audit_hash, result_json FROM audit_log "
        "WHERE user_id = ? AND ts >= ? ORDER BY id DESC LIMIT 200",
        (VERDICT_USER, now - (now % 86400))).fetchall()
    for idx, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        if r.get("domain") != domain:
            continue
        if (r.get("verified_level"), r.get("claimed_level"),
                r.get("overclaimed")) == fp[:3]:
            return _verdict_ref(idx, h)
        return None   # latest verdict for this domain differs: reseal
    return None


REQUEST_USER = "system_integrity_request"


def _claim(conn, domain, day, key, now):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
        "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
        "PRIMARY KEY (domain, day, verdict))")
    cur = conn.execute(
        "INSERT OR IGNORE INTO integrity_verdict_claims "
        "(domain, day, verdict, claimed_at) VALUES (?, ?, ?, ?)",
        (domain, day, key, now))
    conn.commit()
    return cur.rowcount == 1


def _seal_request(domain, ctx):
    """Seal that a check was asked for, before it runs. Once per domain per
    UTC day, so the chain shows every domain that was asked about - and the
    register can show any request with no verdict after it."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    now = time.time()
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    with lock:
        won = _claim(conn, domain, day, "__request__", now)
        if not won:
            r = conn.execute(
                "SELECT id, audit_hash FROM audit_log WHERE user_id = ? AND "
                "ts > ? AND result_json LIKE ? ORDER BY id DESC LIMIT 1",
                (REQUEST_USER, now - 86400,
                 '%"domain": "' + domain + '"%')).fetchone()
            ref = _verdict_ref(r[0], r[1]) if r else {}
            return dict(ref, sealed_now=False)
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; request not sealed"}
        _seal_times.append(now)
    event = {"user_id": REQUEST_USER, "action": "integrity_check_requested",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "REQUESTED", "score": 0, "domain": domain,
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "requested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(now)),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, "__request__"))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _seal_verdict(domain, out, ctx):
    """Seal a verdict into the chain at most once per domain per UTC day,
    unless the verdict changes.

    v1.4 kept that limit in server memory, so a server running several
    copies of itself sealed once per copy. v1.4.1 asks the chain first,
    then claims the seal in a table every copy shares, so only one copy
    can seal a given verdict on a given day."""
    seal = (ctx or {}).get("seal")
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if not callable(seal) or conn is None or lock is None:
        return None
    if out.get("error"):
        # A check that failed to run has no verdict to seal. Its request is
        # already sealed, so the register shows it as asked and unanswered.
        return {"sealed_now": False,
                "note": "the check did not complete, so no verdict was sealed; "
                        "the request stays on record without one"}
    now = time.time()
    fp = _verdict_fingerprint(out)
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    claim = json.dumps(list(fp))
    with lock:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS integrity_verdict_claims ("
            "domain TEXT, day TEXT, verdict TEXT, claimed_at REAL, "
            "PRIMARY KEY (domain, day, verdict))")
        ref = _already_sealed(conn, domain, fp, now)
        if ref:
            conn.commit()
            return dict(ref, sealed_now=False)
        won = _claim(conn, domain, day, claim, now)
    if not won:
        return {"sealed_now": False,
                "note": "this verdict was already sealed today"}
    with _seal_lock:
        while _seal_times and now - _seal_times[0] > 3600:
            _seal_times.pop(0)
        if len(_seal_times) >= VERDICT_MAX_PER_HOUR:
            return {"sealed_now": False,
                    "note": "hourly sealing limit reached; verdict not sealed"}
        _seal_times.append(now)
    walk = ((out.get("checks") or {}).get("INV-001") or {}).get("walk") or {}
    event = {"user_id": VERDICT_USER, "action": "integrity_verdict",
             "amount": 0, "country": "UK", "device_id": "checker",
             "anomaly": 0, "device_risk": 0}
    result = {"decision": "VERDICT", "score": 0, "domain": domain,
              "verified_level": out.get("verified_level"),
              "badge": out.get("badge"),
              "claimed_level": out.get("claimed_level"),
              "overclaimed": out.get("overclaimed"),
              "declaration_url": out.get("declaration_url"),
              "declaration_sha256": out.get("declaration_sha256"),
              "chain_tip_reached": walk.get("tip"),
              "blocks_walked": walk.get("blocks"),
              "checker_version": VERSION,
              "standard_version": DECLARATION.get("version"),
              "checked_at": out.get("checked_at"),
              "timestamp": now}
    try:
        res = seal(event, result, now)
    except Exception as exc:
        with lock:
            conn.execute("DELETE FROM integrity_verdict_claims WHERE "
                         "domain = ? AND day = ? AND verdict = ?",
                         (domain, day, claim))
            conn.commit()
        return {"sealed_now": False, "note": "could not seal: %s" % exc}
    if isinstance(res, (list, tuple)):
        h, idx = res[0], (res[1] if len(res) > 1 else None)
    elif isinstance(res, dict):
        h = res.get("audit_hash") or res.get("hash")
        idx = res.get("block_index") or res.get("index")
    else:
        h, idx = res, None
    return dict(_verdict_ref(idx, h), sealed_now=True)


def _register(data, ctx):
    conn, lock = (ctx or {}).get("conn"), (ctx or {}).get("lock")
    if conn is None or lock is None:
        return {"ok": False, "error": "register_unavailable"}, 503
    with lock:
        rows = conn.execute(
            "SELECT id, ts, audit_hash, result_json FROM audit_log "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 2000",
            (VERDICT_USER,)).fetchall()
    with lock:
        req_rows = conn.execute(
            "SELECT id, ts, result_json FROM audit_log WHERE user_id = ? "
            "ORDER BY id DESC LIMIT 2000", (REQUEST_USER,)).fetchall()
    last_request = {}
    for ridx, rts, rj in req_rows:
        try:
            d = json.loads(rj).get("domain")
        except Exception:
            continue
        if d and d not in last_request:
            last_request[d] = (ridx, rts)
    latest = {}
    history = {}
    for idx, ts, h, rj in rows:
        try:
            r = json.loads(rj)
        except Exception:
            continue
        d = r.get("domain")
        if not d:
            continue
        history[d] = history.get(d, 0) + 1
        if d in latest:
            continue
        latest[d] = {"domain": d, "verified_level": r.get("verified_level"),
                     "badge": r.get("badge"),
                     "claimed_level": r.get("claimed_level"),
                     "overclaimed": r.get("overclaimed"),
                     "checked_at": r.get("checked_at"),
                     "sealed_in_block": idx, "sealed_block_hash": h,
                     "check_block": "https://sebbi.pro/x/walk/block?index=%d" % idx,
                     "check_now": BASE + "check?domain=" + d}
    order = {n: i for i, n in enumerate(_ORDER)}
    entries = sorted(latest.values(), key=lambda e: (
        -order.get(e.get("verified_level"), -1), e["domain"]))
    for e in entries:
        e["verdicts_sealed"] = history.get(e["domain"], 0)
        lr = last_request.get(e["domain"])
        if lr:
            e["last_request_block"] = lr[0]
    unanswered = []
    for d, (ridx, rts) in sorted(last_request.items()):
        v = latest.get(d)
        if v is None or v["sealed_in_block"] < ridx:
            # a verdict sealed earlier the same day still answers a request
            # sealed later only if the verdict was unchanged; show it anyway
            # so a reader can judge, and say which case it is.
            unanswered.append({
                "domain": d, "request_block": ridx,
                "check_request": "https://sebbi.pro/x/walk/block?index=%d" % ridx,
                "latest_verdict_block": v["sealed_in_block"] if v else None,
                "reading": ("an unchanged verdict sealed earlier the same day "
                            "stands for this request") if v else
                           "asked about, and no verdict has been sealed"})
    return {"ok": True, "register": "AI Integrity Declaration - sealed verdicts",
            "standard": BASE + "declaration",
            "domains": len(entries), "entries": entries,
            "requests_without_a_later_verdict": unanswered,
            "what_this_is": "The latest verdict the checker sealed for each "
                            "domain, highest level first. Every row points "
                            "at the public block that holds it, so no rating "
                            "here can be changed after it was given - by the "
                            "domain, or by sebbi.pro. Every request is sealed "
                            "before its check runs, so a question that was "
                            "asked and never answered is visible below the "
                            "list, not hidden by it."}, 200


def _check_route(data, ctx=None):
    domain = _clean_domain((data or {}).get("domain"))
    if not domain:
        return {"ok": False, "error": "domain_required",
                "example": BASE + "check?domain=example.com",
                "detail": "Give a public domain name, e.g. domain=example.com"}, 400
    now = time.time()
    with _cache_lock:
        hit = _cache.get(domain)
        if hit and now - hit[0] < CACHE_SECONDS:
            out = dict(hit[1])
            out["cached_seconds_ago"] = int(now - hit[0])
            return out, 200
    if not _running.acquire(blocking=False):
        return {"ok": False, "error": "busy",
                "detail": "Two checks are already running. Try again in a "
                          "minute."}, 429
    request = _seal_request(domain, ctx)
    try:
        out = _check(domain)
    except Exception as exc:
        out = {"domain": domain, "verified_level": "L0_DIARY", "badge": "GREY",
               "error": "check_failed", "detail": str(exc)[:200]}
    finally:
        _running.release()
    out["ok"] = True
    if request:
        out["request_sealed"] = request
    sealed = _seal_verdict(domain, out, ctx)
    if sealed:
        out["verdict_sealed"] = sealed
    with _cache_lock:
        _cache[domain] = (time.time(), out)
        if len(_cache) > 500:
            oldest = sorted(_cache.items(), key=lambda kv: kv[1][0])[:100]
            for k, _ in oldest:
                _cache.pop(k, None)
    return out, 200


def _status():
    return {
        "ok": True,
        "module": "integrity",
        "version": VERSION,
        "standard": DECLARATION.get("spec"),
        "standard_version": DECLARATION.get("version"),
        "declaration_id": DECLARATION.get("declaration_id"),
        "declaration_sha256": DECLARATION_SHA256,
        "levels": list(DECLARATION.get("levels", {}).keys()),
        "invariants": list(DECLARATION.get("invariants", {}).keys()),
        "links": {
            "declaration": BASE + "declaration",
            "check_any_domain": BASE + "check?domain=example.com",
            "sebbi_self_declaration": BASE + "self",
            "check_sebbi": BASE + "check?domain=sebbi.pro",
            "register": BASE + "register",
            "ordering_test": "https://sebbi.pro/.well-known/ordering-test.json",
        },
        "how_to_adopt": "Publish your own filled-in declaration_template at "
                        "/.well-known/ai-integrity.json on your own domain, "
                        "then check it at " + BASE + "check?domain=yourdomain",
        "hash_note": "declaration_sha256 is SHA-256 of the declaration as "
                     "compact JSON with sorted keys, so anyone can confirm "
                     "the text they are reading is the text published.",
    }


def handle(method, action, data, api_key, ctx):
    data = data or {}
    if isinstance(data.get("domain"), list):
        data = dict(data)
        data["domain"] = data["domain"][0] if data["domain"] else ""
    if method == "GET" and action in ("status", "spec", ""):
        return _status(), 200
    if method == "GET" and action == "declaration":
        return DECLARATION, 200
    if method == "GET" and action == "self":
        return SELF, 200
    if method == "GET" and action == "check":
        return _check_route(data, ctx)
    if method == "GET" and action == "register":
        return _register(data, ctx)
    return {"ok": False, "error": "unknown_action",
            "get": sorted(a for m, a in PUBLIC if m == "GET"),
            "post": []}, 404

```
