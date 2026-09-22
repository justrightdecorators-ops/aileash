#!/usr/bin/env python3
"""
sebbi_benchmark.py  -  an honest benchmark
==========================================

Everything this prints was measured on the machine running it, or is labelled
as an estimate. Nothing is typed in by hand to make a comparison look good.

    python3 sebbi_benchmark.py                  local measurements only
    python3 sebbi_benchmark.py --price 3.00     also show cost at YOUR price per 1M tokens
    python3 sebbi_benchmark.py --live           also time real calls to sebbi.pro

What it measures
  1. Exact-match cache      a repeated identical request is served locally,
                            so it sends nothing to the model.
  2. Secret redaction       emails and bearer tokens are masked before a prompt
                            leaves the machine. Wording is never changed.
  3. Signed receipts        each processed request gets an Ed25519 signature.
                            Only the holder of the private key can produce it;
                            anyone with the public key can check it. That is
                            what makes it non-repudiable. (HMAC cannot do this:
                            anyone holding the shared secret can forge it.)
  4. Live round trip        with --live, real timings to sebbi.pro, network included.

What it does NOT claim
  - Token counts are ESTIMATES (about 4 characters per token for English).
    Your provider's own count is the only exact figure.
  - No money is shown unless you give your own contract price with --price.
  - This is a demonstration of the techniques, not the sebbi.pro token saver
    itself, which runs as its own module and customer download.

Standard library only. Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import statistics
import sys
import time
import urllib.request

# ---------------------------------------------------------------- Ed25519 (RFC 8032)
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
_B = (_xrec(_BY), _BY, 1, _xrec(_BY) * _BY % _Q)


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
    return (x, y, 1, x * y % _Q)


def _h(m):
    return int.from_bytes(hashlib.sha512(m).digest(), "little")


def _secret_scalar(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed_public(seed):
    return _enc(_mul(_B, _secret_scalar(seed)[0]))


def ed_sign(seed, msg):
    a, prefix = _secret_scalar(seed)
    pk = _enc(_mul(_B, a))
    r = _h(prefix + msg) % _L
    R = _enc(_mul(_B, r))
    s = (r + _h(R + pk + msg) * a) % _L
    return R + s.to_bytes(32, "little")


def ed_verify(pk, msg, sig):
    try:
        R, A = _dec(sig[:32]), _dec(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    k = _h(sig[:32] + pk + msg) % _L
    return _enc(_mul(_B, s)) == _enc(_add(R, _mul(A, k)))


# ---------------------------------------------------------------- the demo engine
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")
KEYLIKE = re.compile(r"\b(sk|pk|rk)_(live|test)_[A-Za-z0-9]{8,}\b")


def est_tokens(text):
    """Estimate only: about 4 characters per token for English text."""
    return max(1, round(len(text) / 4))


class Engine:
    def __init__(self):
        self.cache = {}
        self.seed = secrets.token_bytes(32)
        self.public_key = ed_public(self.seed)

    def process(self, prompt):
        t0 = time.perf_counter()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if digest in self.cache:
            return {"verdict": "CACHE_HIT", "sent_to_model": "", "request_hash": digest,
                    "ms": (time.perf_counter() - t0) * 1000, "receipt": self.cache[digest]["receipt"]}
        clean = BEARER.sub("Bearer [REDACTED]", prompt)
        clean = KEYLIKE.sub("[REDACTED_KEY]", clean)
        clean = EMAIL.sub("[REDACTED_EMAIL]", clean)
        body = json.dumps({"request": digest,
                           "sent": hashlib.sha256(clean.encode("utf-8")).hexdigest()},
                          sort_keys=True, separators=(",", ":")).encode()
        sig = ed_sign(self.seed, body)
        receipt = {"body": body.decode(), "signature": sig.hex()}
        self.cache[digest] = {"sent": clean, "receipt": receipt}
        return {"verdict": "PROCESSED", "sent_to_model": clean, "request_hash": digest,
                "ms": (time.perf_counter() - t0) * 1000, "receipt": receipt,
                "redactions": prompt != clean}


def timed(fn, n):
    times = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return statistics.median(times), times[max(0, int(len(times) * 0.95) - 1)]


def live(path):
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen("https://sebbi.pro" + path, timeout=15) as r:
            r.read()
            code = r.status
    except Exception as e:
        return None, str(e)[:60]
    return (time.perf_counter() - t0) * 1000, code


def main():
    ap = argparse.ArgumentParser(description="An honest sebbi.pro benchmark")
    ap.add_argument("--price", type=float, help="your contract price in USD per 1M input tokens")
    ap.add_argument("--live", action="store_true", help="also time real calls to sebbi.pro")
    ap.add_argument("--runs", type=int, default=50, help="repetitions per timing (default 50)")
    a = ap.parse_args()

    prompt = ("Please summarise this internal operations brief for our team. "
              "Review all the customer logs attached. "
              "Send the confirmation report to admin.ops@enterprise.com once finished. "
              "Authentication: Bearer sk_live_998877665544332211. "
              "Capture every detail without missing any historical transitions.")
    line = "=" * 64
    print(line + "\n  SEBBI.PRO HONEST BENCHMARK  ·  measured on this machine\n" + line)
    print("  Python %s · %s runs per timing\n" % (sys.version.split()[0], a.runs))

    eng = Engine()
    first = eng.process(prompt)
    print("[1] First request")
    print("    estimated tokens in prompt : ~%d (estimate)" % est_tokens(prompt))
    print("    secrets masked             : %s" % ("yes — email and bearer token" if first["redactions"] else "none found"))
    print("    wording changed            : no (only secrets are masked)")
    print("    sent to model              : %s" % first["sent_to_model"][:70] + "…")

    second = eng.process(prompt)
    print("\n[2] Identical request again")
    print("    verdict                    : %s" % second["verdict"])
    print("    sent to model              : nothing (served from local cache)")
    print("    tokens avoided             : ~%d (estimate; exact figure = your provider's count)" % est_tokens(first["sent_to_model"]))

    body = first["receipt"]["body"].encode()
    sig = bytes.fromhex(first["receipt"]["signature"])
    ok = ed_verify(eng.public_key, body, sig)
    forged = ed_verify(eng.public_key, body.replace(b'"request"', b'"requesT"'), sig)
    print("\n[3] Signed receipt (Ed25519)")
    print("    public key                 : %s…" % eng.public_key.hex()[:32])
    print("    receipt verifies           : %s" % ("YES" if ok else "NO"))
    print("    altered receipt verifies   : %s" % ("YES — PROBLEM" if forged else "NO (tampering detected)"))

    fresh = Engine()
    p_med, p_95 = timed(lambda: fresh.process(prompt + secrets.token_hex(4)), a.runs)
    c_med, c_95 = timed(lambda: eng.process(prompt), a.runs)
    v_med, v_95 = timed(lambda: ed_verify(eng.public_key, body, sig), max(10, a.runs // 5))
    print("\n[4] Measured timings (median / 95th percentile)")
    print("    new request, masked + signed : %.2f ms / %.2f ms" % (p_med, p_95))
    print("    cache hit                    : %.3f ms / %.3f ms" % (c_med, c_95))
    print("    receipt verification         : %.2f ms / %.2f ms" % (v_med, v_95))
    print("    (plain-Python signatures; a native Ed25519 library is faster)")

    if a.price is not None:
        cost = est_tokens(first["sent_to_model"]) * a.price / 1_000_000
        print("\n[5] At YOUR price of $%.2f per 1M input tokens" % a.price)
        print("    this prompt costs about    : $%.6f per call (estimate)" % cost)
        print("    each cache hit avoids      : about $%.6f (estimate)" % cost)

    if a.live:
        print("\n[6] Live round trips to sebbi.pro (network included)")
        for path in ("/x/witness/tip", "/x/continuity/pubkey", "/x/passport/spec"):
            ms, code = live(path)
            print("    %-24s : %s" % (path, ("%.0f ms (HTTP %s)" % (ms, code)) if ms else "failed: %s" % code))

    print("\n" + line)
    print("  Every figure above was measured here or is marked as an estimate.")
    print("  Check any of it: the code is this file, standard library only.")
    print(line)


if __name__ == "__main__":
    main()
