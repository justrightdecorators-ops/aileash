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
