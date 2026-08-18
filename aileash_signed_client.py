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
