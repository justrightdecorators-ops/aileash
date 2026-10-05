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
