#!/usr/bin/env python3
"""
sebbi_site.py  -  require an Agent Passport on your site in one line
====================================================================

    from sebbi_site import accept

    def handle_payment(request):
        passport = accept(request.headers, audience="shop.example.com",
                          action="payments.send",
                          params={"amount": request.json["amount"]})
        # Reaching here means: a human authorised this agent, that authority
        # still stands at this instant, the amount is exactly what was
        # authorised, and this passport has never been used. Do the action.
        ...

accept() does two things:

  1. CHECK, on your own server. The Ed25519 signature is verified against
     sebbi.pro's published key, plus expiry, site and action. Nothing is sent
     anywhere for this step. A forged, expired or misdirected passport is
     turned away before sebbi.pro is ever asked.
  2. REDEEM, at the moment of action. sebbi.pro re-checks the human's
     authority right now, compares the exact parameters, and lets the passport
     bind once. The outcome is sealed in a public chain.

Anything wrong raises PassportRejected - do not perform the action.

For a fully offline signature check, set SEBBI_PUBKEY to the hex key from
https://sebbi.pro/x/continuity/pubkey. Otherwise it is fetched once and cached.

Standard library only. One file. Python 3.8+.

Command line:
    python sebbi_site.py check <token> [audience]
"""

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

__version__ = "1.0.0"

BASE = os.environ.get("SEBBI_BASE", "https://sebbi.pro").rstrip("/")
HEADER = "Agent-Passport"
PREFIX = b"AILEASH-PASSPORT-v1:"
TIMEOUT = 10


class PassportRejected(Exception):
    """Do not perform the action. .reasons lists why."""

    def __init__(self, reasons, sealed=None):
        self.reasons = reasons if isinstance(reasons, list) else [str(reasons)]
        self.sealed = sealed
        super().__init__("; ".join(self.reasons))


# ---------------------------------------------------------------- Ed25519
# RFC 8032 verification, standard library only, so there is nothing to install.

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrec(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q:
        x = x * _I % _Q
    if x % 2:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_BX = _xrec(_BY)
_B = (_BX, _BY, 1, _BX * _BY % _Q)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    d = z1 * 2 * z2 % _Q
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _mul(p, n):
    r = (0, 1, 1, 0)
    while n:
        if n & 1:
            r = _add(r, p)
        p = _add(p, p)
        n >>= 1
    return r


def _enc(p):
    x, y, z, _ = p
    zi = _inv(z)
    x, y = x * zi % _Q, y * zi % _Q
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _dec(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrec(y)
    if (x & 1) != (s[31] >> 7):
        x = _Q - x
    p = (x, y, 1, x * y % _Q)
    x, y, z, t = p
    if (y * y - x * x - z * z - _D * t * t) % _Q:
        raise ValueError("point off curve")
    return p


def _verify(sig, msg, pk):
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        r, a = _dec(sig[:32]), _dec(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + pk + msg).digest(), "little") % _L
    return _enc(_mul(_B, s)) == _enc(_add(r, _mul(a, h)))


# ---------------------------------------------------------------- passport

_key_cache = {}


def public_key():
    env = os.environ.get("SEBBI_PUBKEY", "").strip()
    if env:
        return bytes.fromhex(env)
    if "pk" not in _key_cache:
        try:
            with urllib.request.urlopen(BASE + "/x/continuity/pubkey", timeout=TIMEOUT) as r:
                _key_cache["pk"] = bytes.fromhex(json.loads(r.read())["public_key"])
        except Exception as e:
            raise PassportRejected("could not load sebbi.pro public key: %s" % e)
    return _key_cache["pk"]


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def check(token, audience, action=None):
    """Offline check. Returns the passport body or raises PassportRejected."""
    try:
        tag, b, s = str(token).strip().split(".")
        if tag != "sbp1":
            raise ValueError
        raw, sig = _b64d(b), _b64d(s)
        body = json.loads(raw)
    except Exception:
        raise PassportRejected("missing or malformed passport")
    if not _verify(sig, PREFIX + raw, public_key()):
        raise PassportRejected("signature does not verify - forged or altered")
    problems = []
    if time.time() > body.get("exp", 0):
        problems.append("expired")
    if body.get("aud") != audience.strip().lower():
        problems.append("issued for %s, not %s" % (body.get("aud"), audience))
    if action and body.get("act") != action:
        problems.append("issued for action %s, not %s" % (body.get("act"), action))
    if problems:
        raise PassportRejected(problems)
    return body


def redeem(token, audience, params=None):
    """Spend it once, at the moment of action. Returns sebbi.pro's sealed answer."""
    req = urllib.request.Request(
        BASE + "/x/passport/redeem", method="POST",
        data=json.dumps({"token": token, "audience": audience.strip().lower(),
                         "params": params or {}}).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "User-Agent": "sebbi-site/" + __version__})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            res = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read())
        except Exception:
            raise PassportRejected("sebbi.pro answered %d" % e.code)
    except Exception as e:
        raise PassportRejected("could not reach sebbi.pro to redeem: %s" % e)
    if not res.get("redeemed"):
        raise PassportRejected(res.get("problems") or ["refused"], res.get("sealed_in_chain"))
    return res


def accept(headers_or_token, audience, action=None, params=None):
    """Check then redeem. Returns the passport body. Raises PassportRejected."""
    token = headers_or_token
    if not isinstance(token, str):
        get = getattr(headers_or_token, "get", None)
        token = (get(HEADER) or get(HEADER.lower()) or "") if get else ""
    body = check(token, audience, action)
    res = redeem(token, audience, params)
    body["sealed_in_chain"] = res.get("sealed_in_chain")
    body["block_index"] = res.get("block_index")
    return body


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "check":
        print("usage: python sebbi_site.py check <token> [audience]")
        sys.exit(2)
    try:
        aud = sys.argv[3] if len(sys.argv) > 3 else json.loads(_b64d(sys.argv[2].split(".")[1]))["aud"]
        t0 = time.perf_counter()
        body = check(sys.argv[2], aud)
        print("VALID (%.1f ms) - %s at %s, expires %s" % ((time.perf_counter() - t0) * 1000,
              body["act"], body["aud"], time.ctime(body["exp"])))
    except PassportRejected as e:
        print("REJECTED - %s" % e)
        sys.exit(1)
