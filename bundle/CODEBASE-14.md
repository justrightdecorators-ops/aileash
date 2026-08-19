# Codebase — part 14 of 23

Contains:
- `sebdog_licence.py`
- `sebdog_reporter.py`
- `tests/attack_continuity_1.py`
- `tests/attack_continuity_2.py`
- `tests/attack_continuity_3.py`
- `tests/attack_continuity_4.py`
- `tests/attack_continuity_5.py`
- `tests/attack_continuity_6.py`
- `tests/attack_witnessed.py`


## `sebdog_licence.py`

500 lines, 18698 bytes

```python
"""
SEBDOG LICENCE SYSTEM v2.0.0
Air-gapped cryptographic licence tokens for the Sebdog Engine.
Copyright (c) 2026 Justin Antony Dobson / Monop Content, Blyth, UK

WHAT CHANGED IN 2.0, AND WHY IT HAD TO
--------------------------------------
Version 1 signed tokens with HMAC-SHA256. HMAC is symmetric: the same
secret both signs and verifies. So validating a token offline required
that secret to be present on the customer's hardware - and anyone
holding it can mint their own token for any device count, any plan, any
expiry.

Version 1's docstring said the signing secret never leaves sebbi.pro's
servers. With an offline HMAC check, that could not be true. One of the
two claims had to give, and it should not be the one about not shipping
the key.

Version 2 uses Ed25519. The server holds a private seed and signs. The
customer's copy holds only the PUBLIC key, which verifies signatures and
cannot produce one. Offline validation and an unshippable signing key
stop being in conflict, because they are no longer the same key.

    v1  customer holds the minting key   offline validation works
    v2  customer holds a public key      offline validation works

Everything else is unchanged: 7-day grace, local cache, tamper
detection, deterministic payload, constant-time comparison where it
still applies.

NO DEPENDENCY
-------------
Ed25519 is implemented here in pure standard library, the same way it
is in continuity.py and modules/signed.py. Nothing to pip install on a
customer's air-gapped box, which is the entire point of shipping this
rather than a library.

SETTING IT UP, ONCE
-------------------
    python3 sebdog_licence.py --keygen

Put the private seed in a Railway environment variable as
SEBDOG_LICENCE_SEED. Paste the public key into LICENCE_PUBKEY below and
into sebdog_engine.py. The private seed never appears in any file that
ships.

MIGRATING A v1 TOKEN
--------------------
There is no migration and there should not be one. A v1 token was
verifiable by anyone who had the secret, so any v1 token in the wild
should be treated as compromised and reissued. validate_token rejects
v1 tokens by version rather than pretending they are fine.
"""

import base64
import hashlib
import json
import os
import sqlite3
import threading
import time
from typing import Dict, Optional, Tuple

TOKEN_VERSION = "2"
GRACE_SECONDS = 86400 * 7          # 7 days past expiry before a hard block
AUDIT_DB = "sebdog_audit.db"

# The public half of the signing key. Safe to ship, safe to publish, and
# useless for producing a token. Overridable by environment for testing.
LICENCE_PUBKEY = os.environ.get("SEBDOG_LICENCE_PUBKEY", "")


# ==============================================================================
# Ed25519 - RFC 8032, standard library only
#
# Extended coordinates for the scalar multiplication so a verify is
# milliseconds rather than seconds. sign() is here for the server side; a
# customer's deployment only ever calls verify().
# ==============================================================================

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


def public_key(seed: bytes) -> bytes:
    """The 32-byte public key for a 32-byte private seed."""
    a, _ = _secret_scalar(seed)
    return _encodepoint(_scalarmult(_B, a))


def sign(seed: bytes, message: bytes) -> bytes:
    """Server side only. Never called on customer hardware."""
    a, prefix = _secret_scalar(seed)
    pk = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    rp = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(rp + pk + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return rp + s.to_bytes(32, "little")


def verify(pk: bytes, message: bytes, signature: bytes) -> bool:
    """True if the signature is valid. Never raises."""
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


def keygen() -> Tuple[str, str]:
    """(private_seed_hex, public_key_hex). Run once, keep the first secret."""
    seed = os.urandom(32)
    return seed.hex(), public_key(seed).hex()


# ==============================================================================
# TOKEN GENERATION - sebbi.pro only
# ==============================================================================

def generate_token(api_key: str, devices: int, plan: str, email: str,
                   seed: bytes, validity_days: int = 365) -> str:
    """
    Sign an annual licence token.

    seed is the 32-byte Ed25519 private seed, read from the
    SEBDOG_LICENCE_SEED environment variable on the server. It is never
    written to a file that ships and never sent to a customer.
    """
    if isinstance(seed, str):
        seed = bytes.fromhex(seed.strip())
    if len(seed) != 32:
        raise ValueError("seed must be 32 bytes")

    issued = int(time.time())
    payload = json.dumps({
        "v": TOKEN_VERSION,
        "key": api_key,
        "devices": devices,
        "plan": plan,
        "email": email,
        "issued": issued,
        "expires": issued + (validity_days * 86400),
    }, sort_keys=True, separators=(",", ":"))

    sig = sign(seed, payload.encode("utf-8")).hex()
    token = json.dumps({"payload": payload, "sig": sig, "alg": "ed25519"},
                       separators=(",", ":"))
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8")


# ==============================================================================
# TOKEN VALIDATION - customer hardware, no network, public key only
# ==============================================================================

def validate_token(token: str, pubkey=None) -> Tuple[Optional[Dict],
                                                     Optional[str]]:
    """
    Validate a licence token entirely locally.

    pubkey is the 32-byte public key, as hex or bytes. Defaults to
    LICENCE_PUBKEY. It cannot be used to produce a token, so shipping it
    inside the engine costs nothing.

    Returns (licence_data, None) or (None, error_code).

        invalid_format      cannot be decoded
        no_public_key       nothing configured to verify against
        invalid_signature   tampered with, or signed by the wrong key
        version_mismatch    not a v2 token - v1 HMAC tokens land here
        token_expired       past expiry plus the grace period
    """
    if pubkey is None:
        pubkey = LICENCE_PUBKEY
    if isinstance(pubkey, str):
        pubkey = pubkey.strip()
        if not pubkey:
            return None, "no_public_key"
        try:
            pubkey = bytes.fromhex(pubkey)
        except ValueError:
            return None, "no_public_key"
    if not pubkey or len(pubkey) != 32:
        return None, "no_public_key"

    try:
        raw = json.loads(base64.urlsafe_b64decode(token.encode("utf-8")))
        payload_str = raw.get("payload", "")
        sig_hex = raw.get("sig", "")
        if not payload_str or not sig_hex:
            return None, "invalid_format"
        sig = bytes.fromhex(sig_hex)
    except Exception:
        return None, "invalid_format"

    if not verify(pubkey, payload_str.encode("utf-8"), sig):
        return None, "invalid_signature"

    try:
        data = json.loads(payload_str)
    except Exception:
        return None, "invalid_format"

    if data.get("v") != TOKEN_VERSION:
        return None, "version_mismatch"

    if data.get("expires", 0) + GRACE_SECONDS < time.time():
        return None, "token_expired"

    return data, None


def is_in_grace_period(token_data: Dict) -> bool:
    return token_data.get("expires", 0) < time.time()


def days_until_expiry(token_data: Dict) -> int:
    return int((token_data.get("expires", 0) - time.time()) / 86400)


# ==============================================================================
# LOCAL LICENCE STORE
# ==============================================================================

_lock = threading.Lock()


def save_licence_locally(db_path: str, token: str, licence_data: Dict):
    with _lock:
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licence_cache (
                id INTEGER PRIMARY KEY, token TEXT, api_key TEXT,
                devices INTEGER, plan TEXT, email TEXT,
                issued INTEGER, expires INTEGER, cached_at REAL)""")
        conn.execute("DELETE FROM licence_cache")
        conn.execute(
            "INSERT INTO licence_cache(token,api_key,devices,plan,email,"
            "issued,expires,cached_at) VALUES(?,?,?,?,?,?,?,?)",
            (token, licence_data.get("key", ""),
             licence_data.get("devices", 1), licence_data.get("plan", "free"),
             licence_data.get("email", ""), licence_data.get("issued", 0),
             licence_data.get("expires", 0), time.time()))
        conn.commit()
        conn.close()


def load_licence_locally(db_path: str) -> Optional[Tuple[str, Dict]]:
    """Returns (token, data) or None. The token is re-verified by the caller -
    a cached row is a convenience, never an authority."""
    try:
        with _lock:
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT token,api_key,devices,plan,email,issued,expires "
                "FROM licence_cache LIMIT 1").fetchone()
            conn.close()
        if not row:
            return None
        return row[0], {"v": TOKEN_VERSION, "key": row[1], "devices": row[2],
                        "plan": row[3], "email": row[4], "issued": row[5],
                        "expires": row[6]}
    except Exception:
        return None


# ==============================================================================
# STRESS TEST      python3 sebdog_licence.py
# KEY GENERATION   python3 sebdog_licence.py --keygen
# ==============================================================================

if __name__ == "__main__":
    import sys

    if "--keygen" in sys.argv:
        priv, pub = keygen()
        print("PRIVATE SEED - server only, never ships, never leaves Railway")
        print("  SEBDOG_LICENCE_SEED=" + priv)
        print()
        print("PUBLIC KEY - paste into LICENCE_PUBKEY here and in the engine")
        print("  " + pub)
        print()
        print("Losing the private seed means no new tokens can be issued and")
        print("every deployed public key must be replaced. Back it up.")
        sys.exit(0)

    print("SEBDOG LICENCE SYSTEM v2 - Ed25519 - Stress Test")
    print("=" * 62)

    SEED = os.urandom(32)
    PUB = public_key(SEED)
    TEST_KEY = "al_live_" + os.urandom(12).hex()
    PASSES = FAILURES = 0

    def check(name, condition, detail=""):
        global PASSES, FAILURES
        if condition:
            print("  PASS  " + name)
            PASSES += 1
        else:
            print("  FAIL  " + name + " " + str(detail))
            FAILURES += 1

    print("\n[1] Generation and validation")
    token = generate_token(TEST_KEY, 10000, "paid", "test@example.com", SEED)
    data, err = validate_token(token, PUB)
    check("Valid token accepted", err is None, err)
    check("API key preserved", data and data.get("key") == TEST_KEY)
    check("Device count preserved", data and data.get("devices") == 10000)
    check("Plan preserved", data and data.get("plan") == "paid")
    check("Not in grace period", data and not is_in_grace_period(data))
    check("Over 360 days remaining", data and days_until_expiry(data) > 360)
    check("Public key accepted as hex", validate_token(token, PUB.hex())[1] is None)

    print("\n[2] THE POINT OF VERSION 2")
    print("      A customer holds the public key. Can they mint a licence?")
    # Feeding the public key in as a seed does not error - it is 32 bytes,
    # so it derives some other keypair entirely. The property that matters
    # is that whatever comes out does NOT verify against the real key.
    attempt = generate_token(TEST_KEY, 999999, "enterprise",
                             "attacker@example.com", PUB)
    _, err = validate_token(attempt, PUB)
    check("Token minted with the public key does not verify",
          err == "invalid_signature", err)
    check("Public key is not the private seed",
          public_key(PUB) != PUB)
    other_seed = os.urandom(32)
    self_signed = generate_token(TEST_KEY, 999999, "enterprise",
                                 "attacker@example.com", other_seed)
    _, err = validate_token(self_signed, PUB)
    check("Token signed by any other key rejected", err == "invalid_signature")

    print("\n[3] Tamper detection")
    for label, old, new in [("device count", "10000", "99999"),
                            ("plan", "paid", "enterprise"),
                            ("expiry", '"expires"', '"expiries"')]:
        raw = json.loads(base64.urlsafe_b64decode(token))
        raw["payload"] = raw["payload"].replace(old, new)
        bad = base64.urlsafe_b64encode(
            json.dumps(raw, separators=(",", ":")).encode()).decode()
        _, err = validate_token(bad, PUB)
        check("Tampered " + label + " rejected", err == "invalid_signature", err)
    raw = json.loads(base64.urlsafe_b64decode(token))
    raw["sig"] = "00" * 64
    bad = base64.urlsafe_b64encode(
        json.dumps(raw, separators=(",", ":")).encode()).decode()
    check("Zeroed signature rejected",
          validate_token(bad, PUB)[1] == "invalid_signature")

    print("\n[4] Expiry")
    exp = generate_token(TEST_KEY, 100, "paid", "t@e.com", SEED, validity_days=-1)
    d, err = validate_token(exp, PUB)
    check("Recently expired token still runs in grace", err is None and d)
    check("Grace period reported", d and is_in_grace_period(d))
    hard = generate_token(TEST_KEY, 100, "paid", "t@e.com", SEED, validity_days=-9)
    check("Hard expired token rejected",
          validate_token(hard, PUB)[1] == "token_expired")

    print("\n[5] Wrong key")
    check("Unrelated public key rejected",
          validate_token(token, public_key(os.urandom(32)))[1] == "invalid_signature")
    flipped = bytearray(PUB)
    flipped[0] ^= 1
    check("One-bit-flipped public key rejected",
          validate_token(token, bytes(flipped))[1] == "invalid_signature")

    print("\n[6] Malformed input")
    for label, bad_in in [("garbage", "notbase64!!!"), ("empty", ""),
                          ("empty json", base64.urlsafe_b64encode(b"{}").decode())]:
        check(label + " rejected", validate_token(bad_in, PUB)[1] is not None)
    check("Missing public key reported",
          validate_token(token, "")[1] == "no_public_key")

    print("\n[7] v1 tokens are not silently accepted")
    v1_payload = json.dumps({"v": "1", "key": TEST_KEY, "devices": 10,
                             "plan": "paid", "email": "t@e.com",
                             "issued": int(time.time()),
                             "expires": int(time.time()) + 86400},
                            sort_keys=True, separators=(",", ":"))
    v1 = base64.urlsafe_b64encode(json.dumps(
        {"payload": v1_payload, "sig": sign(SEED, v1_payload.encode()).hex()},
        separators=(",", ":")).encode()).decode()
    check("v1 token rejected by version",
          validate_token(v1, PUB)[1] == "version_mismatch")

    print("\n[8] Local cache")
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = f.name
    try:
        d, _ = validate_token(token, PUB)
        save_licence_locally(test_db, token, d)
        cached = load_licence_locally(test_db)
        check("Saved and retrieved", cached is not None)
        check("Cached token re-verifies",
              cached and validate_token(cached[0], PUB)[1] is None)
        check("Cached devices match", cached and cached[1]["devices"] == 10000)
    finally:
        os.unlink(test_db)

    print("\n[9] Performance")
    import timeit
    g = timeit.timeit(lambda: generate_token(TEST_KEY, 1, "paid", "t@e.com",
                                             SEED), number=50) / 50
    v = timeit.timeit(lambda: validate_token(token, PUB), number=50) / 50
    print("      sign   %.1f ms" % (g * 1000))
    print("      verify %.1f ms" % (v * 1000))
    check("Verification under 50ms", v < 0.05)

    print("\n" + "=" * 62)
    print("Results: %d passed, %d failed" % (PASSES, FAILURES))
    print("ALL TESTS PASSED." if not FAILURES else "FAILURES. Do not ship.")
    sys.exit(0 if not FAILURES else 1)

```


## `sebdog_reporter.py`

217 lines, 8364 bytes

```python
"""
SEBDOG DECISION REPORTER v1.0.0
Generates readable reports from the sebdog audit chain.
Shows exactly why each decision was made.
Copyright (c) 2026 Justin Antony Dobson / Monop Content
"""

import sqlite3, json, time, os
from datetime import datetime

DB_FILE = "sebdog_audit.db"

REASON_EXPLANATIONS = {
    "velocity_spike": "User made more than 10 requests in 60 seconds",
    "high_amount": "Transaction amount exceeded £500",
    "risky_device": "Device risk score above 0.5",
    "behaviour_anomaly": "Behavioural anomaly score above 0.5",
    "country_shift": "Request came from a different country than usual",
    "unsafe_country": "Request came from outside approved country list",
    "low_trust": "User trust score has dropped below 0.4 due to previous decisions",
}

def get_decisions(db_path=DB_FILE, limit=100):
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT ts, user_id, event_json, result_json, audit_hash
        FROM audit_log
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
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
                "audit_hash": row[4]
            })
        except:
            pass
    return results

def format_reason(reason):
    return REASON_EXPLANATIONS.get(reason, reason.replace("_", " ").capitalize())

def decision_color(decision):
    return {"ALLOW": "#00875a", "CHALLENGE": "#b45309", "BLOCK": "#cc0000"}.get(decision, "#555")

def generate_text_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    if not decisions:
        return "No decisions recorded yet."
    
    lines = [
        "SEBDOG DECISION REPORT",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Total decisions shown: {len(decisions)}",
        "=" * 60
    ]
    
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        
        lines.append(f"\n[{ts}] User: {d['user_id']}")
        lines.append(f"Action: {event.get('action','?')} | Country: {event.get('country','?')} | Amount: £{event.get('amount',0)}")
        lines.append(f"Decision: {decision} | Score: {score} | Trust: {result.get('trust',0)}")
        
        if reasons:
            lines.append("Reasons:")
            for r in reasons:
                lines.append(f"  - {format_reason(r)}")
        else:
            lines.append("Reasons: No risk factors detected")
        
        lines.append(f"Audit hash: {d['audit_hash'][:32]}...")
        lines.append("-" * 60)
    
    return "\n".join(lines)

def generate_json_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    report = {
        "generated": datetime.now().isoformat(),
        "total": len(decisions),
        "decisions": []
    }
    for d in decisions:
        result = d["result"]
        event = d["event"]
        reasons = result.get("reasons", [])
        report["decisions"].append({
            "timestamp": datetime.fromtimestamp(d["ts"]).isoformat(),
            "user_id": d["user_id"],
            "action": event.get("action"),
            "country": event.get("country"),
            "amount": event.get("amount"),
            "decision": result.get("decision"),
            "score": result.get("score"),
            "trust": result.get("trust"),
            "reasons": reasons,
            "reasons_explained": [format_reason(r) for r in reasons],
            "audit_hash": d["audit_hash"]
        })
    return json.dumps(report, indent=2)

def generate_html_report(db_path=DB_FILE, limit=100):
    decisions = get_decisions(db_path, limit)
    
    rows = ""
    for d in decisions:
        result = d["result"]
        event = d["event"]
        ts = datetime.fromtimestamp(d["ts"]).strftime('%Y-%m-%d %H:%M:%S')
        decision = result.get("decision", "?")
        score = result.get("score", 0)
        reasons = result.get("reasons", [])
        color = decision_color(decision)
        
        reason_html = ""
        if reasons:
            reason_html = "<ul>" + "".join(f"<li>{format_reason(r)}</li>" for r in reasons) + "</ul>"
        else:
            reason_html = "<span style='color:#888'>No risk factors detected</span>"
        
        rows += f"""
        <tr>
            <td>{ts}</td>
            <td><code>{d['user_id']}</code></td>
            <td>{event.get('action','?')}</td>
            <td>{event.get('country','?')}</td>
            <td>£{event.get('amount',0)}</td>
            <td><strong style="color:{color}">{decision}</strong></td>
            <td>{score}</td>
            <td>{result.get('trust',0)}</td>
            <td>{reason_html}</td>
            <td><code style="font-size:10px">{d['audit_hash'][:16]}...</code></td>
        </tr>"""
    
    allow = sum(1 for d in decisions if d["result"].get("decision") == "ALLOW")
    challenge = sum(1 for d in decisions if d["result"].get("decision") == "CHALLENGE")
    block = sum(1 for d in decisions if d["result"].get("decision") == "BLOCK")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sebdog Decision Report</title>
<style>
body{{font-family:sans-serif;background:#f5f7fa;color:#1a202c;margin:0;padding:20px}}
.header{{background:#0a0f1e;color:#fff;padding:24px 32px;border-radius:8px;margin-bottom:24px}}
.header h1{{margin:0;font-size:24px;color:#c9a84c}}
.header p{{margin:4px 0 0;color:rgba(255,255,255,0.5);font-size:13px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px}}
.stat{{background:#fff;border-radius:8px;padding:16px;text-align:center;border:1px solid #e2e8f0}}
.stat-n{{font-size:32px;font-weight:700}}
.stat-l{{font-size:11px;color:#64748b;margin-top:4px}}
.allow{{color:#00875a}}.challenge{{color:#b45309}}.block{{color:#cc0000}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0}}
th{{background:#0a0f1e;color:#c9a84c;padding:10px 12px;text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:1px}}
td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;font-size:12px;vertical-align:top}}
tr:last-child td{{border:none}}
tr:hover td{{background:#f8fafc}}
ul{{margin:4px 0;padding-left:16px}}
li{{margin:2px 0;color:#64748b}}
code{{background:#f1f5f9;padding:2px 4px;border-radius:3px;font-size:11px}}
</style>
</head>
<body>
<div class="header">
  <h1>Sebdog Decision Report</h1>
  <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Showing last {len(decisions)} decisions &nbsp;|&nbsp; Powered by sebbi.pro</p>
</div>
<div class="stats">
  <div class="stat"><div class="stat-n allow">{allow}</div><div class="stat-l">ALLOWED</div></div>
  <div class="stat"><div class="stat-n challenge">{challenge}</div><div class="stat-l">CHALLENGED</div></div>
  <div class="stat"><div class="stat-n block">{block}</div><div class="stat-l">BLOCKED</div></div>
</div>
<table>
<thead><tr>
  <th>Time</th><th>User</th><th>Action</th><th>Country</th><th>Amount</th>
  <th>Decision</th><th>Score</th><th>Trust</th><th>Reasons</th><th>Audit Hash</th>
</tr></thead>
<tbody>{rows if rows else '<tr><td colspan="10" style="text-align:center;color:#888;padding:32px">No decisions recorded yet</td></tr>'}</tbody>
</table>
</body>
</html>"""
    return html

if __name__ == "__main__":
    import sys
    fmt = sys.argv[1] if len(sys.argv) > 1 else "html"
    db = sys.argv[2] if len(sys.argv) > 2 else DB_FILE
    
    if fmt == "text":
        print(generate_text_report(db))
    elif fmt == "json":
        print(generate_json_report(db))
    else:
        report = generate_html_report(db)
        out = "sebdog_report.html"
        with open(out, "w") as f:
            f.write(report)
        print(f"Report saved to {out}")

```


## `tests/attack_continuity_1.py`

440 lines, 22747 bytes

```python
#!/usr/bin/env python3
"""Attack harness for modules/lineage.py.

Every test is written from the position of an agent that HAS some authority
and is trying to end up with more. Passing means the attack was refused for
the right reason, not merely refused.
"""

import hashlib
import json
import sqlite3
import threading
import time
import sys

import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    chain = {"n": 0, "prev": "0" * 64}

    def seal(ev, res, ts, api_key):
        chain["n"] += 1
        payload = json.dumps([ev, res, ts, api_key, chain["prev"]], sort_keys=True)
        h = hashlib.sha256(payload.encode()).hexdigest()
        chain["prev"] = h
        return h, chain["n"], chain["n"]

    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, condition, detail=""):
    (PASS if condition else FAIL).append(name)
    print(("  ok   " if condition else "  FAIL ") + name + (("  -> " + detail) if detail and not condition else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def exercise(ctx, **kw):
    return lineage._evaluate(ctx, "k", kw)


NOW = time.time()
HOUR = 3600


def base_root(ctx, **over):
    args = dict(
        id="root", issuer="justin@monop", issuer_kind="human",
        subject="orchestrator", subject_kind="agent",
        scope=["payments.refund", "payments.read", "tickets.*"],
        constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"],
                     "denied_country": ["KP"], "may_contact_customer": True},
        purpose="resolve customer refund complaints",
        purpose_tags=["refunds", "support"],
        not_before=NOW - HOUR, not_after=NOW + 10 * HOUR,
        delegations_left=3)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 1. the happy path must actually work ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="refund-agent", scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds under 500", purpose_tags=["refunds"],
      not_before=NOW - HOUR, not_after=NOW + 2 * HOUR, delegations_left=1)
r, code = exercise(ctx, grant="mid", action="payments.refund",
                   params={"amount": 100, "currency": "GBP", "country": "GB",
                           "contact_customer": True},
                   purpose_tag="refunds")
check("a derivable action returns ALLOW", r["verdict"] == "ALLOW", str(r["reasons"]))
check("lineage names the human at the root", r["authorised_by"] == "justin@monop")
check("depth is reported", r["delegation_depth"] == 1)
check("the decision is sealed", bool(r.get("sealed_in_chain")))

print("\n=== 2. orphan root: an agent grants itself authority ===")
ctx = make_ctx()
r, code = issue(ctx, id="self", issuer="rogue-agent", issuer_kind="agent",
                subject="rogue-agent", scope=["payments.refund"],
                constraints={"max_amount": 999999}, purpose="whatever I decide",
                purpose_tags=["anything"], not_after=NOW + HOUR)
check("self-issued root is refused at issue", code == 409 and r.get("error") == "identity_continuity", str(r))

print("\n=== 3. scope escalation in a child ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="wide", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund", "payments.transfer"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": False},
                purpose="sneak in a transfer", purpose_tags=["refunds"],
                not_after=NOW + HOUR, delegations_left=0)
check("scope the parent never held is refused",
      code == 409 and "payments.transfer" in r.get("message", ""), str(r))

print("\n=== 4. constraint loosening ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="rich", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 50000, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="bigger refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("raising a max_ cap is refused", code == 409 and "max_amount" in r.get("message", ""), str(r))

r, code = issue(ctx, id="wide2", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP", "USD"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="new currency", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("adding to an allowed_ set is refused", code == 409 and "USD" in r.get("message", ""), str(r))

r, code = issue(ctx, id="undeny", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": [], "may_contact_customer": True},
                purpose="drop the denylist", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("dropping from a denied_ set is refused", code == 409 and "KP" in r.get("message", ""), str(r))

r, code = issue(ctx, id="newkey", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True,
                             "may_export_data": True},
                purpose="invent a permission", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("introducing a constraint key the parent never expressed is refused",
      code == 409 and "may_export_data" in r.get("message", ""), str(r))

print("\n=== 5. temporal attacks ===")
ctx = make_ctx()
base_root(ctx)
r, code = issue(ctx, id="long", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="rogue", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="outlive the parent", purpose_tags=["refunds"],
                not_before=NOW, not_after=NOW + 100 * HOUR)
check("a child cannot outlive its parent", code == 409 and r.get("error") == "temporal_validity", str(r))

# expired ancestor, live leaf, forced in past the issue check
ctx = make_ctx()
base_root(ctx, not_after=NOW + HOUR)
issue(ctx, id="child", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="agent-b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET not_after=? WHERE id='root'", (NOW - 60,))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="child", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an expired ancestor kills a live leaf", r["verdict"] == "BLOCK", str(r["reasons"]))
check("...and it is reported as tampering, since the row no longer matches its digest",
      r["broken_invariant"] == "evidence_continuity", r["broken_invariant"] or "")

print("\n=== 6. revocation is transitive ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
      subject="b", scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="leaf", parent="mid", issuer="b", issuer_kind="agent",
      subject="c", scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
lineage._revoke(ctx, "k", {"grant": "mid", "reason": "agent compromised"})
r, _ = exercise(ctx, grant="leaf", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("revoking the middle blocks the leaf without touching it", r["verdict"] == "BLOCK")
check("the revoked grant is named", r["broken_at"] == "mid", str(r["broken_at"]))
r2, _ = exercise(ctx, grant="root", action="payments.refund",
                 params={"amount": 10, "currency": "GBP", "country": "GB",
                         "contact_customer": True}, purpose_tag="refunds")
check("revoking a child does not harm the parent", r2["verdict"] == "ALLOW", str(r2["reasons"]))

print("\n=== 7. delegation depth cannot be manufactured ===")
ctx = make_ctx()
base_root(ctx, delegations_left=1)
issue(ctx, id="d1", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=0)
r, code = issue(ctx, id="d2", parent="d1", issuer="b", issuer_kind="agent", subject="c",
                scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("an exhausted delegation budget stops the chain",
      code == 409 and r.get("error") == "delegation_not_permitted", str(r))

ctx = make_ctx()
base_root(ctx, delegations_left=2)
r, code = issue(ctx, id="greedy", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                             "denied_country": ["KP"], "may_contact_customer": True},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR,
                delegations_left=5)
check("a child cannot award itself more onward delegations than remained",
      code == 409, str(r))

print("\n=== 8. tampering with a stored grant ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute(
        "UPDATE auth_grant SET constraints=? WHERE id='mid'",
        (json.dumps({"max_amount": 999999, "allowed_currency": ["GBP", "USD"],
                     "denied_country": [], "may_contact_customer": True},
                    sort_keys=True, separators=(",", ":")),))
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 900000, "currency": "USD", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("editing the database does not widen authority", r["verdict"] == "BLOCK")
check("the tamper is reported as an evidence failure",
      r["broken_invariant"] == "evidence_continuity", str(r["broken_invariant"]))

print("\n=== 9. re-parenting onto a wider ancestor ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="narrow", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 1, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="read only", purpose_tags=["support"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent=NULL WHERE id='narrow'")
    ctx["conn"].commit()
r, _ = exercise(ctx, grant="narrow", action="payments.read",
                params={}, purpose_tag="support")
check("detaching a grant to make it a root fails integrity", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 10. parent cycle ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="a", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 100, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR, delegations_left=1)
issue(ctx, id="b", parent="a", issuer="b", issuer_kind="agent", subject="c",
      scope=["payments.refund"],
      constraints={"max_amount": 50, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET parent='b' WHERE id='a'")
    ctx["conn"].commit()
start = time.time()
r, _ = exercise(ctx, grant="b", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("a parent cycle terminates rather than hangs", time.time() - start < 2)
check("a cycle is BLOCKed as an authority failure", r["verdict"] == "BLOCK")

print("\n=== 11. action parameters beyond the effective constraints ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 501, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
check("an amount over the cap is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "KP",
                        "contact_customer": True}, purpose_tag="refunds")
check("a denied country is BLOCKed", r["verdict"] == "BLOCK", str(r["reasons"]))

print("\n=== 12. uncertainty is challenged, not guessed ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="issue refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="marketing")
check("a purpose the grant does not carry is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True})
check("no declared purpose is CHALLENGED", r["verdict"] == "CHALLENGE", str(r))
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True, "recipient_iban": "GB00XXXX"},
                purpose_tag="refunds")
check("an unconstrained parameter is CHALLENGED, not ignored",
      r["verdict"] == "CHALLENGE" and any("recipient_iban" in x for x in r["reasons"]), str(r))

print("\n=== 13. wildcard breadth ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="root", action="tickets.close.bulk.all",
                params={}, purpose_tag="support")
check("a broad wildcard match is CHALLENGED rather than silently allowed",
      r["verdict"] == "CHALLENGE", str(r))

ctx = make_ctx()
base_root(ctx, scope=["*"], id="star")
r, _ = exercise(ctx, grant="star", action="payments.transfer", params={}, purpose_tag="refunds")
check("a bare * never reaches ALLOW", r["verdict"] == "CHALLENGE", str(r))

print("\n=== 14. no union of grants ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="money", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": False},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
issue(ctx, id="contact", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.read"],
      constraints={"max_amount": 0, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="contact", purpose_tags=["support"], not_after=NOW + HOUR)
r, code = exercise(ctx, grant="money,contact", action="payments.refund",
                   params={"amount": 10, "currency": "GBP", "contact_customer": True},
                   purpose_tag="refunds")
check("two grant ids cannot be combined into one exercise", r["verdict"] == "BLOCK", str(r))
r, _ = exercise(ctx, grant="money", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "contact_customer": True},
                purpose_tag="refunds")
check("the capability from the sibling grant does not leak in", r["verdict"] == "BLOCK",
      str(r["reasons"]))

print("\n=== 15. time of check vs time of use ===")
ctx = make_ctx()
base_root(ctx)
issue(ctx, id="mid", parent="root", issuer="orchestrator", issuer_kind="agent", subject="b",
      scope=["payments.refund"],
      constraints={"max_amount": 500, "allowed_currency": ["GBP"],
                   "denied_country": ["KP"], "may_contact_customer": True},
      purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
r, _ = exercise(ctx, grant="mid", action="payments.refund",
                params={"amount": 10, "currency": "GBP", "country": "GB",
                        "contact_customer": True}, purpose_tag="refunds")
eval_id = r["evaluation"]
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 10, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing exactly what was evaluated binds", c["bound"] is True, str(c))
c, code = lineage._confirm(ctx, "k", {"evaluation": eval_id, "action": "payments.refund",
                                      "params": {"amount": 400, "currency": "GBP",
                                                 "country": "GB", "contact_customer": True}})
check("executing different values than were evaluated is rejected", c["bound"] is False, str(c))
check("the rejected execution is still sealed", bool(c.get("sealed_in_chain")))

with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_eval SET valid_until=? WHERE id=?", (NOW - 1, eval_id))
    ctx["conn"].commit()
c, _ = lineage._confirm(ctx, "k", {"evaluation": eval_id})
check("a banked evaluation cannot be spent after its window", c["bound"] is False, str(c))

print("\n=== 16. a BLOCK is evidence, not silence ===")
ctx = make_ctx()
base_root(ctx)
r, _ = exercise(ctx, grant="nonexistent", action="payments.refund", params={})
check("an unknown grant BLOCKs", r["verdict"] == "BLOCK")
check("the block is sealed in the chain", bool(r.get("sealed_in_chain")))
d, code = lineage._decision(ctx, {"evaluation": r["evaluation"]})
check("the sealed decision is publicly retrievable", code == 200 and d["verdict"] == "BLOCK")

print("\n=== 17. no authority without a stated purpose or an end date ===")
ctx = make_ctx()
r, code = issue(ctx, id="forever", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="anything", purpose_tags=["x"])
check("a grant with no expiry is refused", code == 400 and r.get("error") == "not_after_required")
r, code = issue(ctx, id="vague", issuer="justin@monop", issuer_kind="human", subject="a",
                scope=["payments.refund"], constraints={"max_amount": 1},
                purpose="", purpose_tags=["x"], not_after=NOW + HOUR)
check("a grant with no purpose is refused", code == 400 and r.get("error") == "purpose_required")

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  FAILED: " + f)
    sys.exit(1)

```


## `tests/attack_continuity_2.py`

228 lines, 10573 bytes

```python
#!/usr/bin/env python3
"""Second wave. The first wave tested the obvious escalations. This one
tests the ones that would survive a code review."""

import hashlib
import json
import sqlite3
import threading
import time
import sys

import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []
NOW = time.time()
HOUR = 3600


def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock()
    n = {"i": 0}

    def seal(ev, res, ts, api_key):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True,
                                         default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx)
    return ctx


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("  -> " + str(detail)[:300]) if detail and not cond else ""))


def issue(ctx, **kw):
    if kw.get("parent") and int(kw.get("delegations_left", 0)) > 0 \
            and not kw.get("risk_accepted_by"):
        kw["risk_accepted_by"] = "owner@example.com"
    return lineage._issue(ctx, "k", kw)


def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund", "payments.read"],
                constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_before=NOW - HOUR, not_after=NOW + 10 * HOUR, delegations_left=10)
    args.update(over)
    return issue(ctx, **args)


print("\n=== 18. double execution against one ALLOW ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
eid = r["evaluation"]
p = {"amount": 100, "currency": "GBP"}
c1, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
c2, _ = lineage._confirm(ctx, "k", {"evaluation": eid, "action": "payments.refund", "params": p})
check("the first execution binds", c1["bound"] is True, c1)
check("the same evaluation cannot be spent twice", c2["bound"] is False, c2)

print("\n=== 19. type confusion in constraints ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 5000, "allowed_currency": "GBP"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "G"},
                                    "purpose_tag": "refunds"})
check("a single character does not satisfy a string-valued allowed_ list",
      r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, code = issue(ctx, id="strnum", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": "50000", "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("a numeric cap passed as a string cannot beat the parent", code == 409, r)

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": "99999", "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a string amount is still compared numerically", r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": True, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a non-numeric amount does not slip through as unconstrained",
      r["verdict"] in ("BLOCK", "CHALLENGE"), r)

print("\n=== 20. capability prefix tricks ===")
ctx = make_ctx()
root(ctx, scope=["payments.refund"])
for probe in ["payments.refunds", "payments.refund.approve", "payments.refundX",
              "Payments.Refund", "payments.refund "]:
    r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": probe,
                                        "params": {}, "purpose_tag": "refunds"})
    check("'%s' is not covered by 'payments.refund'" % probe, r["verdict"] == "BLOCK", r["reasons"])

ctx = make_ctx()
root(ctx, scope=["payments.*"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments2.transfer",
                                    "params": {}, "purpose_tag": "refunds"})
check("'payments.*' does not cover 'payments2.transfer'", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 21. a long but legitimate chain ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 10000, "allowed_currency": ["GBP", "EUR"]},
     delegations_left=12)
parent, cap = "root", 10000
for i in range(10):
    cap = cap // 2
    gid = "d%d" % i
    r, code = issue(ctx, id=gid, parent=parent, issuer="a%d" % i, issuer_kind="agent",
                    subject="a%d" % (i + 1), scope=["payments.refund"],
                    constraints={"max_amount": cap, "allowed_currency": ["GBP"]},
                    purpose="refunds", purpose_tags=["refunds"],
                    not_after=NOW + HOUR, delegations_left=11 - i)
    if code != 200:
        break
    parent = gid
check("ten legitimate narrowing hops are accepted", code == 200 and parent == "d9", r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 5, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("the deep chain still ALLOWs a derivable action", r["verdict"] == "ALLOW", r["reasons"])
check("the effective cap is the tightest in the chain",
      float(r["effective_constraints"]["max_amount"]) == 9, r["effective_constraints"])
check("the human at the root is still named ten hops down",
      r["authorised_by"] == "owner@example.com")
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 10, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("one unit over the deepest cap is BLOCKed", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 22. revoking the root kills the whole tree ===")
lineage._revoke(ctx, "k", {"grant": "root", "reason": "principal withdrew authority"})
r, _ = lineage._evaluate(ctx, "k", {"grant": "d9", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("revoking the root blocks a leaf ten hops away", r["verdict"] == "BLOCK")
check("the root is named as the break point", r["broken_at"] == "root", r["broken_at"])

print("\n=== 23. issuing under a revoked or expired parent ===")
ctx = make_ctx()
root(ctx)
lineage._revoke(ctx, "k", {"grant": "root", "reason": "x"})
r, code = issue(ctx, id="after", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 1, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"], not_after=NOW + HOUR)
check("no new delegation under a revoked parent", code == 409 and r.get("error") == "parent_revoked", r)

print("\n=== 24. duplicate grant id cannot overwrite a grant ===")
ctx = make_ctx()
root(ctx)
r, code = root(ctx, scope=["*"], constraints={"max_amount": 999999})
check("re-issuing an existing id is refused", code == 409 and r.get("error") == "grant_exists", r)

print("\n=== 25. the boundary values themselves ===")
ctx = make_ctx()
root(ctx, constraints={"max_amount": 100, "allowed_currency": ["GBP"]}, delegations_left=2)
r, code = issue(ctx, id="equal", parent="root", issuer="orchestrator", issuer_kind="agent",
                subject="b", scope=["payments.refund"],
                constraints={"max_amount": 100, "allowed_currency": ["GBP"]},
                purpose="refunds", purpose_tags=["refunds"],
                not_after=NOW + 10 * HOUR, delegations_left=1)
check("an equal-not-wider child is accepted", code == 200, r)
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("exactly the cap is allowed", r["verdict"] == "ALLOW", r["reasons"])
r, _ = lineage._evaluate(ctx, "k", {"grant": "equal", "action": "payments.refund",
                                    "params": {"amount": 100.01, "currency": "GBP"},
                                    "purpose_tag": "refunds"})
check("a penny over the cap is blocked", r["verdict"] == "BLOCK", r["reasons"])

print("\n=== 26. a CHALLENGE cannot be executed ===")
ctx = make_ctx()
root(ctx)
r, _ = lineage._evaluate(ctx, "k", {"grant": "root", "action": "payments.refund",
                                    "params": {"amount": 1, "currency": "GBP"}})
check("no declared purpose gives CHALLENGE", r["verdict"] == "CHALLENGE", r["verdict"])
c, code = lineage._confirm(ctx, "k", {"evaluation": r["evaluation"],
                                      "action": "payments.refund",
                                      "params": {"amount": 1, "currency": "GBP"}})
check("a CHALLENGE cannot be bound as an execution", c["bound"] is False, c)

print("\n" + "=" * 60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL:
    print("  FAILED: " + f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_3.py`

114 lines, 5626 bytes

```python
#!/usr/bin/env python3
"""Third wave: concurrency, and reconstruction from evidence alone."""
import hashlib, json, sqlite3, threading, time, sys
import continuity as lineage
# --- stand-in for the deployed engine ---------------------------------
import types as _types
_ENGINE = {"verdict": "ALLOW"}

def install_engine(verdict="ALLOW", raises=False, shape="dict"):
    _ENGINE["verdict"] = verdict
    mod = _types.ModuleType("server")
    mod.get_bearer = lambda *a, **k: None
    def score_event(event):
        if raises:
            raise RuntimeError("engine down")
        if shape == "dict":
            return {"decision": _ENGINE["verdict"], "score": 0.1}
        if shape == "tuple":
            return (_ENGINE["verdict"], 0.1)
        return _ENGINE["verdict"]
    mod.score_event = score_event
    sys.modules["server"] = mod

def remove_engine():
    sys.modules.pop("server", None)

install_engine("ALLOW")


PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    def seal(ev, res, ts, k):
        with lock:
            n["i"] += 1
            return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    lineage._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    lineage._setup(ctx); return ctx

def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:250]) if d and not c else ""))

print("\n=== 27. concurrent execution of one ALLOW ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
    subject="agent",scope=["payments.refund"],constraints={"max_amount":5000},
    purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":100},"purpose_tag":"refunds"})
eid = r["evaluation"]; results = []
def race():
    c,_ = lineage._confirm(ctx,"k",{"evaluation":eid,"action":"payments.refund","params":{"amount":100}})
    results.append(c["bound"])
ts = [threading.Thread(target=race) for _ in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
check("exactly one of eight concurrent executions binds", results.count(True) == 1, results)
with ctx["lock"]:
    rows = ctx["conn"].execute("SELECT COUNT(*) FROM auth_exec WHERE eval_id=? AND outcome<>'rejected'",(eid,)).fetchone()
check("only one accepted binding exists in storage", rows[0] == 1, rows)

print("\n=== 28. reconstruct the whole story from the sealed record ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="orchestrator",scope=["payments.*"],constraints={"max_amount":5000},
    purpose="close the refund backlog",purpose_tags=["refunds"],
    not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="orchestrator",issuer_kind="agent",
    subject="refund-bot",scope=["payments.refund"],constraints={"max_amount":200},
    purpose="issue small refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":150},"purpose_tag":"refunds"})
t,code = lineage._trace(ctx,{"grant":"m"})
check("the trace names who authorised it", t["authorised_by"] == "owner@example.com")
check("the trace names who held it at execution", t["holder"] == "refund-bot")
check("the trace shows what changed at each hop",
      t["lineage"][0]["scope"] == ["payments.*"] and t["lineage"][1]["scope"] == ["payments.refund"])
check("the effective constraint is the narrowest, not the granted one",
      float(t["effective_constraints"]["max_amount"]) == 200, t["effective_constraints"])
d,code = lineage._decision(ctx,{"evaluation":r["evaluation"]})
check("the decision is retrievable without a key and matches", d["verdict"] == r["verdict"])
check("the decision carries the lineage digest", d["lineage_digest"] == r["lineage_digest"])
check("every hop carries its own block index",
      all(h["block_index"] for h in t["lineage"]))

print("\n=== 29. widening midway is visible in the trace, not just blocked ===")
ctx = make_ctx()
lineage._issue(ctx,"k",dict(id="r",issuer="owner@example.com",issuer_kind="human",
    subject="a",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=2))
lineage._issue(ctx,"k",dict(id="m",parent="r",issuer="a",issuer_kind="agent",
    subject="b",scope=["payments.refund"],constraints={"max_amount":100},
    purpose="p",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=1,
    risk_accepted_by="owner@example.com"))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET constraints=? WHERE id='m'",
        (json.dumps({"max_amount":100000},sort_keys=True,separators=(",",":")),))
    ctx["conn"].commit()
t,_ = lineage._trace(ctx,{"grant":"m"})
check("the trace flags the altered hop by name",
      t["lineage"][1]["integrity"] == "FAILED" and t["lineage"][0]["integrity"] == "ok", t["lineage"])
r,_ = lineage._evaluate(ctx,"k",{"grant":"m","action":"payments.refund",
    "params":{"amount":50},"purpose_tag":"refunds"})
check("and the exercise names the exact grant that broke", r["broken_at"] == "m", r["broken_at"])

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_4.py`

107 lines, 4723 bytes

```python
#!/usr/bin/env python3
"""Fourth wave: does it actually compose with the existing engine, and can
either side be bypassed by the other?"""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600
STATE = {"verdict": "ALLOW", "raises": False, "shape": "dict", "seen": []}

def install(verdict="ALLOW", raises=False, shape="dict"):
    STATE.update(verdict=verdict, raises=raises, shape=shape)
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    def score_event(event):
        STATE["seen"].append(event)
        if STATE["raises"]: raise RuntimeError("engine down")
        if STATE["shape"] == "dict": return {"decision": STATE["verdict"], "score": 0.42}
        if STATE["shape"] == "tuple": return (STATE["verdict"], 0.42)
        if STATE["shape"] == "junk": return {"nothing": "useful"}
        return STATE["verdict"]
    m.score_event = score_event
    sys.modules["server"] = m

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def setup():
    ctx = make_ctx()
    C._issue(ctx,"k",dict(id="root",issuer="owner@example.com",issuer_kind="human",
        subject="agent",scope=["payments.refund"],
        constraints={"max_amount":5000,"allowed_currency":["GBP"]},
        purpose="refunds",purpose_tags=["refunds"],not_after=NOW+HOUR,delegations_left=0))
    return ctx

def run(ctx, amount=100):
    return C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
        "params":{"amount":amount,"currency":"GBP"},"purpose_tag":"refunds"})[0]

print("\n=== 30. the engine is actually consulted ===")
install("ALLOW"); STATE["seen"] = []
r = run(setup())
check("a clean authority plus a clean engine is ALLOW", r["verdict"]=="ALLOW", r)
check("the engine was called with the real action and amount",
      STATE["seen"] and STATE["seen"][-1]["action"]=="payments.refund"
      and STATE["seen"][-1]["amount"]==100, STATE["seen"][-1] if STATE["seen"] else None)
check("both components are reported separately",
      r["authority_verdict"]=="ALLOW" and r["risk_verdict"]=="ALLOW", r)

print("\n=== 31. neither side can wave the other through ===")
install("BLOCK")
r = run(setup())
check("perfect authority does not survive an engine BLOCK", r["verdict"]=="BLOCK", r)
check("the authority component still reads ALLOW underneath it",
      r["authority_verdict"]=="ALLOW", r)
install("CHALLENGE")
r = run(setup())
check("an engine CHALLENGE lifts a clean authority to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW")
ctx = setup()
r = C._evaluate(ctx,"k",{"grant":"root","action":"payments.transfer",
    "params":{"amount":1},"purpose_tag":"refunds"})[0]
check("a clean engine does not confer authority nobody granted", r["verdict"]=="BLOCK", r)
check("and the engine is not even asked once authority has failed",
      r["risk_engine"]["available"] is False, r["risk_engine"])

print("\n=== 32. a missing or broken engine is not an ALLOW ===")
install("ALLOW", raises=True)
r = run(setup())
check("an engine that throws downgrades ALLOW to CHALLENGE", r["verdict"]=="CHALLENGE", r)
install("ALLOW", shape="junk")
r = run(setup())
check("an unreadable engine response downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
sys.modules.pop("server", None); sys.modules.pop("__main__", None)
r = run(setup())
check("no engine present downgrades to CHALLENGE", r["verdict"]=="CHALLENGE", r)
check("the reason names the missing engine",
      any("risk engine" in x for x in r["reasons"]), r["reasons"])

print("\n=== 33. it reads the engine's other return shapes ===")
for shape in ("dict","tuple","str"):
    install("BLOCK", shape=shape)
    r = run(setup())
    check("a %s return shape is understood" % shape, r["verdict"]=="BLOCK", r["risk_engine"])

print("\n=== 34. an engine BLOCK cannot be executed ===")
install("BLOCK")
ctx = setup(); r = run(ctx)
c,_ = C._confirm(ctx,"k",{"evaluation":r["evaluation"],"action":"payments.refund",
    "params":{"amount":100,"currency":"GBP"}})
check("execution is refused when the engine blocked", c["bound"] is False, c)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_5.py`

116 lines, 5639 bytes

```python
#!/usr/bin/env python3
"""Fifth wave: risk acceptance. Who put their name to this capability
existing at all - separately from who granted it and who holds it."""
import hashlib, json, sqlite3, threading, time, sys, types
import continuity as C

PASS, FAIL = [], []
NOW, HOUR = time.time(), 3600

def install():
    m = types.ModuleType("server")
    m.get_bearer = lambda *a, **k: None
    m.score_event = lambda e: {"decision": "ALLOW", "score": 0.1}
    sys.modules["server"] = m
install()

def make_ctx():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i":0}
    def seal(ev,res,ts,k):
        n["i"] += 1
        return hashlib.sha256(json.dumps([ev,res,ts],sort_keys=True,default=str).encode()).hexdigest(), n["i"], n["i"]
    C._ready = False
    ctx = {"conn":conn,"lock":lock,"seal":seal}; C._setup(ctx); return ctx

def check(n,c,d=""):
    (PASS if c else FAIL).append(n)
    print(("  ok   " if c else "  FAIL ")+n+(("  -> "+str(d)[:250]) if d and not c else ""))

def root(ctx, **over):
    args = dict(id="root", issuer="owner@example.com", issuer_kind="human",
                subject="orchestrator", scope=["payments.refund"],
                constraints={"max_amount":5000}, purpose="refunds",
                purpose_tags=["refunds"], not_after=NOW+HOUR, delegations_left=3)
    args.update(over)
    return C._issue(ctx,"k",args)

print("\n=== 35. a root accepts its own risk by default ===")
ctx = make_ctx()
r, code = root(ctx)
check("a root grant records an acceptor without being asked",
      code == 200 and r["risk_accepted_by"] == "owner@example.com", r)
r2, _ = root(ctx, id="root2", risk_accepted_by="risk.officer@example.com")
check("a root can name someone other than the issuer",
      r2["risk_accepted_by"] == "risk.officer@example.com", r2)

print("\n=== 36. switching on onward delegation needs a name ===")
ctx = make_ctx(); root(ctx)
r, code = C._issue(ctx,"k",dict(id="deleg", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1))
check("a delegable child with no acceptor is refused",
      code == 409 and r.get("error") == "risk_acceptance_required", r)

r, code = C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
check("a non-delegable child inherits the acceptor above it", code == 200, r)

r, code = C._issue(ctx,"k",dict(id="deleg2", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=1, risk_accepted_by="head.of.ops@example.com"))
check("a delegable child with a named acceptor is accepted", code == 200, r)

print("\n=== 37. the decision names the accountable person ===")
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("an evaluation reports who accepts the risk",
      e["risk_accepted_by"] == "owner@example.com", e.get("risk_accepted_by"))
check("...separately from who authorised it and who executed it",
      e["authorised_by"] == "owner@example.com" and e["executed_by"] == "b", e)

e2, _ = C._evaluate(ctx,"k",{"grant":"deleg2","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("the nearest acceptor wins, not the root one",
      e2["risk_accepted_by"] == "head.of.ops@example.com", e2.get("risk_accepted_by"))

t, _ = C._trace(ctx,{"grant":"deleg2"})
check("the trace shows the acceptor at each hop",
      t["risk_accepted_by"] == "head.of.ops@example.com" and
      t["lineage"][0]["risk_accepted_by"] == "owner@example.com", t)

print("\n=== 38. an unaccepted lineage cannot act ===")
ctx = make_ctx(); root(ctx)
C._issue(ctx,"k",dict(id="leaf", parent="root", issuer="orchestrator",
    issuer_kind="agent", subject="b", scope=["payments.refund"],
    constraints={"max_amount":100}, purpose="refunds", purpose_tags=["refunds"],
    not_after=NOW+HOUR, delegations_left=0))
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by=NULL")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"leaf","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("stripping every acceptor blocks the action", e["verdict"] == "BLOCK", e["reasons"])
check("...and says an incident would have no accountable person",
      any("accountable" in x for x in e["reasons"]), e["reasons"])

print("\n=== 39. the acceptor cannot be swapped after the fact ===")
ctx = make_ctx(); root(ctx, risk_accepted_by="risk.officer@example.com")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET risk_accepted_by='someone.else@example.com' WHERE id='root'")
    ctx["conn"].commit()
e, _ = C._evaluate(ctx,"k",{"grant":"root","action":"payments.refund",
    "params":{"amount":10},"purpose_tag":"refunds"})
check("editing who accepted the risk fails the digest", e["verdict"] == "BLOCK", e["reasons"])
check("...reported as an evidence failure, naming the grant",
      e["broken_invariant"] == "evidence_continuity" and e["broken_at"] == "root", e)

print("\n" + "="*60)
print("passed %d, failed %d" % (len(PASS), len(FAIL)))
for f in FAIL: print("  FAILED: "+f)
sys.exit(1 if FAIL else 0)

```


## `tests/attack_continuity_6.py`

92 lines, 3965 bytes

```python
"""End to end: issue, delegate, exercise, export a proof, verify it elsewhere,
then try to forge one."""
import hashlib, json, sqlite3, threading, time, sys, types, subprocess, copy
import continuity as C

m = types.ModuleType("server")
m.get_bearer = lambda *a, **k: None
m.score_event = lambda e: 0.12          # bare score, like the real engine
sys.modules["server"] = m

conn = sqlite3.connect(":memory:", check_same_thread=False)
lock = threading.RLock(); n = {"i": 0}
def seal(ev, res, ts, k):
    n["i"] += 1
    return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True, default=str).encode()).hexdigest(), n["i"], n["i"]
ctx = {"conn": conn, "lock": lock, "seal": seal}
C._ready = False; C._setup(ctx)

NOW, HOUR = time.time(), 3600
C._issue(ctx, "k", dict(id="root", issuer="justin@monopcontent.com", issuer_kind="human",
    subject="orchestrator", scope=["payments.refund", "payments.read"],
    constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
    purpose="resolve customer refund complaints", purpose_tags=["refunds", "support"],
    not_after=NOW + 10 * HOUR, delegations_left=2))
C._issue(ctx, "k", dict(id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
    subject="refund-agent", scope=["payments.refund"],
    constraints={"max_amount": 200, "allowed_currency": ["GBP"]},
    purpose="issue small refunds", purpose_tags=["refunds"],
    not_after=NOW + 2 * HOUR, delegations_left=0))

def run(params, tag="refunds", action="payments.refund"):
    r, _ = C._evaluate(ctx, "k", {"grant": "mid", "action": action,
                                  "params": params, "purpose_tag": tag})
    return r

allow = run({"amount": 150, "currency": "GBP"})
block = run({"amount": 900, "currency": "GBP"})
print("allow verdict:", allow["verdict"], "| block verdict:", block["verdict"],
      "->", block["broken_invariant"])

def bundle_for(ev):
    b, code = C._proof(ctx, {"evaluation": ev})
    assert code == 200, b
    return b

for label, ev in (("ALLOW", allow["evaluation"]), ("BLOCK", block["evaluation"])):
    b = bundle_for(ev)
    open("/tmp/%s.json" % label, "w").write(json.dumps(b, indent=1))
    print("\n" + "#" * 66 + "\n# %s bundle\n" % label + "#" * 66)
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/%s.json" % label],
                         capture_output=True, text=True)
    print(out.stdout.strip()); print("exit:", out.returncode)

print("\n" + "#" * 66 + "\n# forgeries\n" + "#" * 66)
good = json.load(open("/tmp/BLOCK.json"))

def forge(name, mutate):
    b = copy.deepcopy(good)
    mutate(b)
    open("/tmp/forged.json", "w").write(json.dumps(b))
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/forged.json"],
                         capture_output=True, text=True)
    caught = out.returncode != 0
    line = [l for l in out.stdout.splitlines() if l.startswith("FAIL")]
    print(("  ok   " if caught else "  MISS ") + name)
    for l in line[:2]:
        print("         " + l.strip())

def flip_verdict(b):
    b["decision"]["verdict"] = "ALLOW"; b["decision"]["authority_verdict"] = "ALLOW"
def raise_cap(b):
    pass_idx = 1
    b["lineage"][1]["constraints"]["max_amount"] = 100000
def widen_scope(b):
    b["lineage"][1]["scope"] = ["payments.refund", "payments.transfer"]
def swap_human(b):
    b["lineage"][0]["issuer_kind"] = "agent"
def change_params(b):
    b["request"]["params"]["amount"] = 1
def drop_acceptor(b):
    for g in b["lineage"]: g["risk_accepted_by"] = None
def restamp(b):
    b["decision"]["evaluated_at_epoch"] = NOW + 9 * HOUR

forge("claimed ALLOW on a bundle that blocks", flip_verdict)
forge("cap raised inside the lineage", raise_cap)
forge("scope widened inside the lineage", widen_scope)
forge("root demoted from human", swap_human)
forge("parameters swapped after the fact", change_params)
forge("risk acceptor stripped", drop_acceptor)
forge("timestamp moved past the leaf's expiry", restamp)

```


## `tests/attack_witnessed.py`

160 lines, 7875 bytes

```python
"""Attack it the same way as everything else: from the position of an operator
trying to make a grant look older than it is."""
import hashlib, json, sqlite3, threading, time, sys, types
import witnessed as W

P, F = [], []
def check(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:200]) if d and not c else ""))

def make():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    conn.execute("CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "ts REAL,user_id TEXT,api_key TEXT,result_json TEXT,audit_hash TEXT)")
    # the real grant table shape, including columns added later
    conn.execute("CREATE TABLE auth_grant(id TEXT PRIMARY KEY,parent TEXT,root TEXT,"
                 "issuer TEXT,subject TEXT,created REAL,digest TEXT,audit_hash TEXT,"
                 "block_index INTEGER,risk_accepted_by TEXT)")
    def seal(ev, res, ts, key):
        n["i"] += 1
        h = hashlib.sha256(json.dumps([ev,res,ts,n["i"]],sort_keys=True,default=str).encode()).hexdigest()
        conn.execute("INSERT INTO audit_log(ts,user_id,api_key,result_json,audit_hash) "
                     "VALUES(?,?,?,?,?)", (ts, ev.get("user_id"), key, json.dumps(res), h))
        conn.commit()
        return h, n["i"], n["i"]
    W._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    W._setup(ctx)
    return ctx

def seal_grant(ctx, gid, created):
    h, idx, _ = ctx["seal"]({"user_id": "lin:"+gid}, {"decision":"AUTHORITY_GRANTED","grant":gid}, created, "k")
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO auth_grant(id,issuer,subject,created,audit_hash,block_index) "
                            "VALUES(?,?,?,?,?,?)", (gid,"owner@example.com","agent",created,h,idx))
        ctx["conn"].commit()
    return h

def noise(ctx, k=5):
    for i in range(k):
        ctx["seal"]({"user_id":"n%d"%i},{"decision":"ALLOW"},time.time(),"k")

def record_head(ctx, peer, accepted=1, when=None, size=None, tip=None):
    """Insert an attestation directly, standing in for a live peer."""
    s, t = W._head(ctx)
    when = when or time.time()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,api_key)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer,"https://%s"%peer, size or s, tip or t,"d",when,accepted,"{}","b1","ah",1,"k"))
        ctx["conn"].commit()

NOW = time.time()

print("\n=== 1. a grant witnessed after issue ===")
ctx = make()
noise(ctx, 3)
g = seal_grant(ctx, "root", NOW - 3600)
noise(ctx, 4)
record_head(ctx, "redflagai.pro", when=NOW - 1800)
r, code = W._grant(ctx, {"id": "root"})
check("witnessed grant reports externally_witnessed", code==200 and r["externally_witnessed"], r)
check("names the peer and the time", r["earliest_external_witness"]["peer"]=="redflagai.pro", r)
check("gives a four-step plan pointed at the peer",
      len(r["verification_plan"])==4 and "attest" in r["verification_plan"][0]["run"], r["verification_plan"][0])
check("states what it does not prove", "should ever have been issued" in r["what_this_does_not_prove"])
check("reports how long it sat unwitnessed", r["minutes_unwitnessed"] is not None, r.get("minutes_unwitnessed"))

print("\n=== 2. THE ATTACK: a grant back-dated after the fact ===")
# operator invents a root grant now, and writes created= last week
ctx = make()
noise(ctx, 3)
record_head(ctx, "redflagai.pro", when=NOW - 86400)      # peer saw the log yesterday
forged = seal_grant(ctx, "forged", NOW - 7*86400)        # grant CLAIMS to be a week old
r, code = W._grant(ctx, {"id": "forged"})
check("a grant sealed after the last witness is NOT covered", not r["externally_witnessed"], r)
check("and says so plainly rather than staying quiet", "rests on this operator's own record" in r.get("flag",""), r.get("flag"))
# now a peer witnesses; from here it is covered, but only from here
record_head(ctx, "redflagai.pro", when=NOW)
r2, _ = W._grant(ctx, {"id": "forged"})
check("after a later witness it becomes covered", r2["externally_witnessed"])
gapdays = round(r2["minutes_unwitnessed"]/1440.0, 1)
check("the seven-day claim-to-witness gap is published, not hidden",
      r2.get("flag") and "days" in r2["flag"] and gapdays >= 6.9, {"gap_days":gapdays,"flag":r2.get("flag")})

print("\n=== 3. coverage counts only what a peer accepted ===")
ctx = make()
noise(ctx, 2); g = seal_grant(ctx, "g1", NOW); noise(ctx, 2)
record_head(ctx, "peer-that-refused", accepted=0)
r, _ = W._grant(ctx, {"id": "g1"})
check("a refused submission gives no coverage", not r["externally_witnessed"], r.get("earliest_external_witness"))
h, _ = W._heads(ctx, {})
check("but the refusal is still on the public record", h["count"]==1 and h["heads"][0]["accepted"] is False, h)

print("\n=== 4. a head that predates the grant does not cover it ===")
ctx = make()
record_head(ctx, "early-peer", when=NOW-9999)   # size 0
noise(ctx, 3)
seal_grant(ctx, "later", NOW)
r, _ = W._grant(ctx, {"id": "later"})
check("an earlier, smaller head cannot reach a later record", not r["externally_witnessed"], r)

print("\n=== 5. the earliest witness wins, not the most convenient ===")
ctx = make()
noise(ctx, 2); seal_grant(ctx, "g", NOW - 600); noise(ctx, 2)
record_head(ctx, "second-peer", when=NOW - 100)
record_head(ctx, "first-peer",  when=NOW - 400)
r, _ = W._grant(ctx, {"id": "g"})
check("earliest accepted attestation is the one reported",
      r["earliest_external_witness"]["peer"]=="first-peer", r["earliest_external_witness"])
check("the others are listed too", any(c["peer"]=="second-peer" for c in r["also_witnessed_by"]), r["also_witnessed_by"])

print("\n=== 6. status is honest about thin networks ===")
ctx = make(); noise(ctx, 3)
s, _ = W._status(ctx)
check("no peers at all reports strength none", s["strength"]=="none" and "rests on our own record" in s["flag"], s)
record_head(ctx, "only-peer")
s, _ = W._status(ctx)
check("one peer reports weak and names collusion", s["strength"]=="weak" and "collude" in s["flag"], s)
for p in ("p2","p3"): record_head(ctx, p)
s, _ = W._status(ctx)
check("three peers reports reasonable", s["strength"]=="reasonable", s)
noise(ctx, 6)
s, _ = W._status(ctx)
check("records sealed since the last head are counted as unwitnessed",
      s["records_not_yet_witnessed"]==6, s)

print("\n=== 7. tampering with the grant row ===")
ctx = make(); noise(ctx,2); seal_grant(ctx,"t",NOW); record_head(ctx,"peer")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET audit_hash='0'*64 WHERE id='t'")
    ctx["conn"].commit()
r, code = W._grant(ctx, {"id":"t"})
check("a grant whose seal is not in the log is a finding, not a 404",
      code==409 and "finding" in r.get("message",""), (code, r))

print("\n=== 8. url safety on submit ===")
ctx = make(); noise(ctx,2)
for bad, why in [("http://127.0.0.1/x","loopback"),("http://10.0.0.5/x","private"),
                 ("ftp://example.com","scheme"),("https://example.com:8443/x","port")]:
    r, code = W._submit(ctx, "k", {"peer":"p","url":bad})
    check("refuses %s" % why, code==400 and r.get("error")=="url_refused", (bad,code,r))

print("\n=== 9. any sealed record, not just grants ===")
ctx = make(); noise(ctx,2)
h,_ ,_ = ctx["seal"]({"user_id":"x"},{"decision":"ALLOW"},NOW,"k")
noise(ctx,1); record_head(ctx,"peer")
r, code = W._record(ctx, {"hash": h})
check("a decision receipt gets the same treatment", code==200 and r["externally_witnessed"], r)
r, code = W._record(ctx, {"hash": "zz"})
check("a malformed hash is refused", code==400, (code,r))

print("\n" + "="*62)
print("passed %d, failed %d" % (len(P), len(F)))
for f in F: print("  FAILED: " + f)
sys.exit(1 if F else 0)

```
