# Codebase — part 20 of 31

Contains:
- `verify_authority.py`
- `AILeash-API-Reference-v6.4.2.md`
- `LICENCE`
- `README.md`
- `admin.html`
- `ai-standard.html`
- `ai-txt-kit.html`
- `aileash-game.html`
- `aitxt-popup-live.html`


## `verify_authority.py`

596 lines, 22636 bytes

```python
#!/usr/bin/env python3
"""
verify_authority.py  -  check an AILeash authority proof without AILeash

    python3 verify_authority.py proof.json
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify_authority.py -

WHAT THIS IS FOR
----------------
A proof that can only be checked by the party who issued it is not a proof.
This script takes a bundle and reaches its own conclusion using nothing but
the Python standard library. It does not call the issuing system, it does not
import anything you have to install, and it does not take a single field of
the bundle at face value.

It does four separate things, and each one can fail on its own:

  1. SIGNATURE   Ed25519 over the canonical bundle. Confirms the bundle came
                 from the holder of the named key and has not been edited by
                 anybody since.

  2. INTEGRITY   Recomputes every grant digest, the lineage digest and the
                 parameter digest from the fields in front of it. Confirms
                 the bundle is internally consistent with its own contents.

  3. DERIVATION  Re-runs the authority rules from scratch: root issued by a
                 human, an unbroken parent chain, scope covered at every hop,
                 constraints narrowing on every axis, purpose narrowing,
                 validity windows contained, nothing revoked, and the action
                 itself inside the effective limits of the whole lineage.

  4. AGREEMENT   Compares the verdict this script reached with the verdict the
                 bundle claims. Disagreement is reported as a failure of the
                 issuer, not of this script.

WHAT A PASS MEANS
-----------------
That the authority for this action was derivable, at that time, from that
human grant - or, for a refusal, that it genuinely was not, and that the named
grant and invariant really are where it broke.

WHAT A PASS DOES NOT MEAN
-------------------------
That the root grant should ever have been issued. That the parameters describe
something that really happened. That the risk engine was right. Derivation is
not merit and it is not truth.

The risk half of a composed verdict cannot be re-derived here, because that
needs the issuer's scoring engine. Where the bundle's authority verdict is
BLOCK, the composed verdict stands regardless, because the composition takes
the worse of the two.

THE SIGNED MATERIAL
-------------------
Exactly one field is removed before checking: signature. Everything else the
bundle carries, including verify_with, is inside the signature, which is what
the bundle's own instruction says. A verifier that quietly strips more fields
than the published method does is checking a different document from the one
the issuer told the world to check.
"""

import binascii
import hashlib
import json
import sys

GRANT_PREFIX = b"AILEASH-GRANT-v1:"
EVAL_PREFIX = b"AILEASH-AUTHEVAL-v1:"
BUNDLE_PREFIX = b"AILEASH-AUTHORITY-PROOF-v1:"

MAX_DEPTH = 32
RANK = {"ALLOW": 0, "CHALLENGE": 1, "BLOCK": 2}


# ======================================================================
# Ed25519, RFC 8032, standard library only
# ======================================================================

_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _h(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5) % _Q
_BX = _xrecover(_BY)
_B = (_BX % _Q, _BY % _Q, 1, (_BX * _BY) % _Q)
_IDENT = (0, 1, 1, 0)


def _add(p, q):
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = (y1 - x1) * (y2 - x2) % _Q
    b = (y1 + x1) * (y2 + x2) % _Q
    c = t1 * 2 * _D * t2 % _Q
    dd = z1 * 2 * z2 % _Q
    e, f, g, hh = b - a, dd - c, dd + c, b + a
    return (e * f % _Q, g * hh % _Q, f * g % _Q, e * hh % _Q)


def _scalarmult(p, e):
    if e == 0:
        return _IDENT
    q = _scalarmult(p, e // 2)
    q = _add(q, q)
    if e & 1:
        q = _add(q, p)
    return q


def _encodepoint(p):
    x, y, z, _t = p
    zi = _inv(z)
    x, y = x * zi % _Q, y * zi % _Q
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _hint(m):
    h = _h(m)
    return sum(2 ** i * _bit(h, i) for i in range(512))


def _isoncurve(p):
    x, y, z, t = p
    return (z % _Q != 0 and x * y % _Q == z * t % _Q
            and (y * y - x * x - z * z - _D * t * t) % _Q == 0)


def _decodepoint(s):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _xrecover(y)
    if x & 1 != _bit(s, 255):
        x = _Q - x
    p = (x, y, 1, (x * y) % _Q)
    if not _isoncurve(p):
        raise ValueError("point off curve")
    return p


def ed25519_verify(sig, msg, pk):
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        rr = _decodepoint(sig[:32])
        a = _decodepoint(pk)
    except Exception:
        return False
    s = int.from_bytes(sig[32:64], "little")
    if s >= _L:
        return False
    hh = _hint(sig[:32] + pk + msg)
    return _encodepoint(_scalarmult(_B, s)) == _encodepoint(_add(rr, _scalarmult(a, hh)))


# ======================================================================
# the rules, reimplemented from the published spec
# ======================================================================

def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def sha(prefix, text):
    return hashlib.sha256(prefix + text.encode("utf-8")).hexdigest()


def grant_digest(g):
    material = {
        "id": g["id"], "parent": g["parent"], "issuer": g["issuer"],
        "issuer_kind": g["issuer_kind"], "subject": g["subject"],
        "subject_kind": g["subject_kind"], "scope": sorted(g["scope"]),
        "constraints": g["constraints"], "purpose": g["purpose"],
        "purpose_tags": sorted(g["purpose_tags"]),
        "not_before": g["not_before"], "not_after": g["not_after"],
        "depth": g["depth"], "delegations_left": g["delegations_left"],
        "created": g["created"], "risk_accepted_by": g.get("risk_accepted_by"),
    }
    return sha(GRANT_PREFIX, canon(material))


def covers(held, wanted):
    if held == wanted or held == "*":
        return True
    if held.endswith(".*"):
        return wanted == held[:-2] or wanted.startswith(held[:-1])
    return False


def wildcard_breadth(scope, capability):
    best = None
    for held in scope:
        if not covers(held, capability):
            continue
        if held == capability:
            return 0
        width = (capability.count(".") + 2 if held == "*"
                 else capability.count(".") - held[:-2].count("."))
        best = width if best is None else min(best, width)
    return best


def direction(key):
    for p in ("max_", "min_", "allowed_", "denied_", "may_"):
        if key.startswith(p):
            return p
    return None


def num(v):
    if isinstance(v, bool) or v is None:
        raise ValueError("not a number")
    return float(v)


def as_set(v):
    if isinstance(v, (list, tuple, set)):
        return set(v)
    return {v}


def narrower(parent_c, child_c):
    for key in sorted(child_c):
        d = direction(key)
        cval = child_c[key]
        if d is None:
            return False, "constraint '%s' has no narrowing rule" % key
        if key not in parent_c:
            return False, "constraint '%s' is not expressed by the parent" % key
        pval = parent_c[key]
        try:
            if d == "max_" and num(cval) > num(pval):
                return False, "%s raised from %s to %s" % (key, pval, cval)
            if d == "min_" and num(cval) < num(pval):
                return False, "%s lowered from %s to %s" % (key, pval, cval)
            if d == "allowed_" and not as_set(cval) <= as_set(pval):
                return False, "%s adds values the parent does not hold" % key
            if d == "denied_" and not as_set(pval) <= as_set(cval):
                return False, "%s drops values the parent denies" % key
            if d == "may_" and bool(cval) and not bool(pval):
                return False, "%s enabled where the parent withholds it" % key
        except (TypeError, ValueError):
            return False, "constraint '%s' is not comparable" % key
    return True, None


def effective(chain):
    eff = {}
    for g in chain:
        for k, v in g["constraints"].items():
            d = direction(k)
            if k not in eff:
                eff[k] = v
                continue
            cur = eff[k]
            try:
                if d == "max_":
                    eff[k] = min(num(cur), num(v))
                elif d == "min_":
                    eff[k] = max(num(cur), num(v))
                elif d == "allowed_":
                    eff[k] = sorted(as_set(cur) & as_set(v))
                elif d == "denied_":
                    eff[k] = sorted(as_set(cur) | as_set(v))
                elif d == "may_":
                    eff[k] = bool(cur) and bool(v)
            except (TypeError, ValueError):
                eff[k] = v
    return eff


def params_against(params, eff):
    hard, unconstrained = [], []
    for key in sorted(params):
        val = params[key]
        checked = False
        for cname, cval in eff.items():
            d = direction(cname)
            if not d or cname[len(d):] != key:
                continue
            checked = True
            try:
                if d == "max_" and num(val) > num(cval):
                    hard.append("%s=%s exceeds %s=%s" % (key, val, cname, cval))
                elif d == "min_" and num(val) < num(cval):
                    hard.append("%s=%s is below %s=%s" % (key, val, cname, cval))
                elif d == "allowed_" and val not in as_set(cval):
                    hard.append("%s=%s is outside %s" % (key, val, cname))
                elif d == "denied_" and val in as_set(cval):
                    hard.append("%s=%s is denied by %s" % (key, val, cname))
                elif d == "may_" and bool(val) and not bool(cval):
                    hard.append("%s requested where %s withholds it" % (key, cname))
            except (TypeError, ValueError):
                hard.append("%s cannot be compared with %s" % (key, cname))
        if not checked:
            unconstrained.append(key)
    return hard, unconstrained


# ======================================================================
# the four checks
# ======================================================================

class Report(object):
    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, ok, name, detail=""):
        self.rows.append((ok, name, detail))
        if not ok:
            self.failed = True

    def note(self, name, detail=""):
        self.rows.append((None, name, detail))

    def render(self):
        out = []
        for ok, name, detail in self.rows:
            mark = "  ok  " if ok else ("FAIL  " if ok is False else "  --  ")
            out.append(mark + name + (("\n        " + detail) if detail else ""))
        return "\n".join(out)


def check_signature(bundle, rep):
    sig_hex = bundle.get("signature")
    pk_hex = (bundle.get("issued_by") or {}).get("public_key")
    if not sig_hex or not pk_hex:
        rep.add(False, "Signature present", "the bundle carries no signature or no key")
        return
    # Only the signature itself is removed. Every other field the bundle
    # carries is inside the signed material, exactly as the bundle's own
    # verify_with instruction states.
    body = dict(bundle)
    body.pop("signature", None)
    try:
        sig = binascii.unhexlify(sig_hex)
        pk = binascii.unhexlify(pk_hex)
    except Exception:
        rep.add(False, "Signature is readable hex")
        return
    ok = ed25519_verify(sig, BUNDLE_PREFIX + canon(body).encode("utf-8"), pk)
    rep.add(ok, "Ed25519 signature over the canonical bundle",
            "key " + pk_hex[:16] + "…  Verify this key independently at the issuer's "
            "published address before trusting who signed." if ok else
            "the bundle was altered after signing, or it was not signed by this key")


def check_integrity(bundle, rep):
    lineage = bundle.get("lineage") or []
    bad = []
    for g in lineage:
        try:
            if grant_digest(g) != g.get("digest"):
                bad.append(g.get("id"))
        except Exception:
            bad.append(g.get("id"))
    rep.add(not bad, "Every grant digest recomputes from its own fields",
            "" if not bad else "mismatched: " + ", ".join(str(b) for b in bad))

    claimed = (bundle.get("decision") or {}).get("lineage_digest")
    mine = sha(EVAL_PREFIX, canon([g.get("digest") for g in lineage]))
    rep.add(mine == claimed, "Lineage digest matches the ordered path",
            "" if mine == claimed else "computed " + mine[:20] + "… claimed " + str(claimed)[:20] + "…")

    req = bundle.get("request") or {}
    claimed_p = (bundle.get("decision") or {}).get("params_digest")
    mine_p = sha(EVAL_PREFIX, canon({"action": req.get("action"),
                                     "params": req.get("params") or {}}))
    rep.add(mine_p == claimed_p, "Parameter digest matches the request as stated",
            "" if mine_p == claimed_p else "the parameters shown are not the "
            "parameters that were judged")

    # The decision records its own action separately from the request block.
    # Everything downstream - the scope check, the wildcard breadth - is run
    # against the request's action, so if the two ever disagreed this script
    # would be checking one action while the issuer decided another.
    decided_action = (bundle.get("decision") or {}).get("action")
    shown_action = req.get("action")
    rep.add(decided_action == shown_action,
            "The action shown is the action that was decided",
            "" if decided_action == shown_action else
            "the decision names '" + str(decided_action) + "' and the request shows '"
            + str(shown_action) + "' - the bundle describes one action and was judged "
            "on another")


def rederive(bundle, rep):
    """Run the published rules from scratch and reach an independent verdict."""
    lineage = bundle.get("lineage") or []
    decision = bundle.get("decision") or {}
    req = bundle.get("request") or {}
    at = decision.get("evaluated_at_epoch")

    hard, soft = [], []
    broken_at = broken_invariant = None

    def fail(grant, invariant, detail):
        nonlocal broken_at, broken_invariant
        hard.append(detail)
        if broken_at is None:
            broken_at, broken_invariant = grant, invariant

    if not lineage:
        fail(None, "authority_continuity", "the bundle carries no authority path")
    else:
        root = lineage[0]
        if root.get("parent") is not None:
            fail(root["id"], "authority_continuity",
                 "the path does not begin at a parentless root")
        if root.get("issuer_kind") != "human":
            fail(root["id"], "identity_continuity",
                 "the root grant was not issued by a human principal")

        previous = None
        for g in lineage:
            if g.get("revoked_at") is not None:
                fail(g["id"], "authority_continuity",
                     "grant %s was revoked" % g["id"])
            if at is not None:
                if at < g["not_before"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s was not yet valid at the time of the decision" % g["id"])
                if at >= g["not_after"]:
                    fail(g["id"], "temporal_validity",
                         "grant %s had expired at the time of the decision" % g["id"])
            if previous is not None:
                if g.get("parent") != previous.get("id"):
                    fail(g["id"], "authority_continuity",
                         "grant %s does not point at the grant above it" % g["id"])
                missing = [c for c in g["scope"]
                           if not any(covers(p, c) for p in previous["scope"])]
                if missing:
                    fail(g["id"], "boundary_integrity",
                         "%s holds scope its parent does not: %s"
                         % (g["id"], ", ".join(sorted(missing))))
                ok, why = narrower(previous["constraints"], g["constraints"])
                if not ok:
                    fail(g["id"], "boundary_integrity", "%s: %s" % (g["id"], why))
                if not set(g["purpose_tags"]) <= set(previous["purpose_tags"]):
                    fail(g["id"], "intent_continuity",
                         "%s carries purpose tags its parent does not" % g["id"])
                if (g["not_before"] < previous["not_before"]
                        or g["not_after"] > previous["not_after"]):
                    fail(g["id"], "temporal_validity",
                         "%s is valid outside its parent's window" % g["id"])
                if g["depth"] != previous["depth"] + 1:
                    fail(g["id"], "authority_continuity",
                         "%s records a depth inconsistent with its parent" % g["id"])
            previous = g

        if len(lineage) - 1 > MAX_DEPTH:
            fail(lineage[-1]["id"], "boundary_integrity", "delegation depth exceeds the ceiling")

        if not any(g.get("risk_accepted_by") for g in lineage):
            fail(lineage[0]["id"], "identity_continuity",
                 "no grant in this path names who accepted the risk")

        leaf = lineage[-1]
        action = req.get("action")
        params = req.get("params") or {}

        if action and not any(covers(c, action) for c in leaf["scope"]):
            fail(leaf["id"], "boundary_integrity",
                 "action '%s' is outside the scope of the grant exercised" % action)
        elif action:
            breadth = wildcard_breadth(leaf["scope"], action)
            if breadth and breadth >= 2:
                soft.append("action '%s' is only covered by a broad wildcard" % action)

        eff = effective(lineage)
        failures, unconstrained = params_against(params, eff)
        for f in failures:
            fail(leaf["id"], "boundary_integrity", f)
        for u in unconstrained:
            soft.append("parameter '%s' is not constrained anywhere in the path" % u)

        tag = req.get("purpose_tag")
        if tag:
            if tag not in leaf["purpose_tags"]:
                soft.append("declared purpose '%s' is not carried by the grant" % tag)
        else:
            soft.append("the action declared no purpose")

    verdict = "BLOCK" if hard else ("CHALLENGE" if soft else "ALLOW")
    return verdict, hard, soft, broken_at, broken_invariant


def check_agreement(bundle, rep, mine, hard, soft, broken_at, broken_invariant):
    decision = bundle.get("decision") or {}
    claimed = decision.get("authority_verdict") or decision.get("verdict")

    rep.add(mine == claimed,
            "Independently re-derived authority verdict: " + mine,
            "" if mine == claimed else
            "the issuer claims " + str(claimed) + " and this script reaches " + mine +
            " from the same path. One of us is wrong and the rules are published.")

    if mine == "BLOCK":
        same_grant = (broken_at == decision.get("broken_at"))
        same_inv = (broken_invariant == decision.get("broken_invariant"))
        rep.add(same_grant and same_inv,
                "Refusal reproduces at the same grant and invariant",
                ("grant %s, invariant %s" % (broken_at, broken_invariant))
                if same_grant and same_inv else
                "this script breaks at grant %s / %s, the issuer says %s / %s"
                % (broken_at, broken_invariant,
                   decision.get("broken_at"), decision.get("broken_invariant")))
        rep.note("Why authority could not be derived")
        for h in hard:
            rep.note("  " + h)
    elif soft:
        rep.note("Why this could not be settled without a person")
        for x in soft:
            rep.note("  " + x)

    risk = decision.get("risk_verdict")
    if risk and mine != "BLOCK":
        rep.note("Risk verdict reported as " + str(risk) + ", not re-derivable here",
                 "the composed verdict is the worse of the two; the scoring engine "
                 "is not part of this bundle and is not checked by this script")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    raw = sys.stdin.read() if src == "-" else open(src, "r").read()
    try:
        bundle = json.loads(raw)
    except Exception as exc:
        print("Not readable JSON: " + str(exc))
        return 2

    rep = Report()
    print("=" * 66)
    print("AUTHORITY PROOF  ·  independent verification")
    print("=" * 66)
    d = bundle.get("decision") or {}
    print("evaluation   " + str(d.get("evaluation")))
    print("action       " + str((bundle.get("request") or {}).get("action")))
    print("at           " + str(d.get("evaluated_at")))
    print("hops         " + str(max(0, len(bundle.get("lineage") or []) - 1)))
    if bundle.get("lineage"):
        print("authorised   " + str(bundle["lineage"][0].get("issuer")))
        print("executed     " + str(bundle["lineage"][-1].get("subject")))
        acc = [g.get("risk_accepted_by") for g in bundle["lineage"] if g.get("risk_accepted_by")]
        print("risk owner   " + str(acc[-1] if acc else None))
    print("-" * 66)

    check_signature(bundle, rep)
    check_integrity(bundle, rep)
    mine, hard, soft, ba, bi = rederive(bundle, rep)
    check_agreement(bundle, rep, mine, hard, soft, ba, bi)

    print(rep.render())
    print("-" * 66)
    if rep.failed:
        print("RESULT: NOT VERIFIED. Something above did not hold.")
        return 1
    print("RESULT: VERIFIED - " + mine)
    if mine == "BLOCK":
        print("This is a proof that the action was NOT authorised, and where it failed.")
    print("Checked with no network access, no dependencies, and nothing taken on")
    print("the issuer's word except the meaning of their public key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

```


## `AILeash-API-Reference-v6.4.2.md`

256 lines, 6799 bytes

```markdown
# AILeash v6.4.2 — Complete API Reference

## Core Decision Endpoint

### POST /api/govern
**The engine. Every action scores here.**

Auth: `Bearer YOUR_API_KEY`

**Request:**
```json
{
  "user_id": "string (required)",
  "action": "string (required) — payment/login/message/transfer/checkout/api_call",
  "amount": "number (optional, default 0) — monetary value in GBP",
  "country": "string (required) — ISO 3166-1 alpha-2 code",
  "device_id": "string (required) — unique device identifier",
  "anomaly": "number 0..1 (optional) — behavioural anomaly score",
  "device_risk": "number 0..1 (optional) — device risk score"
}
```

**Response (200 OK):**
```json
{
  "decision": "ALLOW|CHALLENGE|BLOCK",
  "score": 0.0..1.0,
  "trust": 0.05..1.0,
  "reasons": ["velocity_spike", "high_amount", "country_shift"],
  "audit_hash": "sha256_hex_string",
  "block_index": 12345,
  "receipt_seq": 42,
  "timestamp": 1719072000.0,
  "challenge_url": "https://sebbi.pro/verify-challenge?token=...",
  "challenge_expires_in": 900
}
```

**Error responses:**
- `401 Unauthorized` — Missing or invalid API key
- `403 Forbidden` — Account inactive or over quota
- `429 Too Many Requests` — Rate limited
- `503 Service Unavailable` — Server overloaded

---

## Account Management

### POST /api/keys or /signup
**Create a new API key. Instant. No card. No humans in the loop.**

No auth required.

**Request:**
```json
{
  "email": "user@example.com (required)",
  "name": "John Doe (optional)",
  "phone": "+441234567890 (optional)",
  "org": "Acme Corp (optional)",
  "product": "aileash|guardian|sonicboom|sentinel (default: aileash)",
  "devices": 1..1000000 (default: 1),
  "ref_code": "REF-XXXX-1234 (optional)"
}
```

**Response (200 OK):**
```json
{
  "api_key": "al_live_...",
  "email": "user@example.com",
  "product": "aileash",
  "devices": 1,
  "monthly_cost": 0.50,
  "quota": 100,
  "ref_code": "REF-JOHN-5678",
  "badge_id": "abc123def456",
  "message": "100 free decisions. Then 50p per device per month via Stripe."
}
```

---

## Verification & Public Endpoints

### GET /api/spec
**Engine specification. Public. No auth.**

**Response (200 OK):**
```json
{
  "engine": "AILeash v6.4.2",
  "version": "6.4.2",
  "signals": 9,
  "decision_latency_ms": 28,
  "threshold_allow": 0.35,
  "threshold_challenge": 0.70,
  "threshold_block": 1.0,
  "features": ["deterministic scoring", "tamper-evident chain", "real-time alerts", "gapless receipts", "sovereign deployment"]
}
```

### GET /api/verify-chain
**Full audit chain integrity proof. Public. No auth.**

**Response (200 OK):**
```json
{
  "valid": true,
  "blocks": 45678,
  "genesis": "GENESIS",
  "tip": "abc123...",
  "message": "Chain intact. No tampering detected.",
  "verifiable_by": "anyone, anywhere"
}
```

### GET /api/health
**Server health and load. Public. No auth.**

**Response (200 OK):**
```json
{
  "status": "ok",
  "version": "6.4.2",
  "uptime_seconds": 864000,
  "rps": 42,
  "timestamp": 1719072000.0
}
```

---

## Real-time Dashboards

### GET /api/pulse
**Live risk posture. Your current state.**

Auth: `Bearer YOUR_API_KEY`

**Response (200 OK):**
```json
{
  "last_hour": {
    "ALLOW": 486,
    "CHALLENGE": 23,
    "BLOCK": 4
  },
  "recent": [
    {
      "ts": 1719072000,
      "user_id": "u_7f2",
      "action": "payment",
      "decision": "ALLOW",
      "score": 0.12,
      "reasons": [],
      "audit_hash": "abc123..."
    }
  ],
  "chain_tip": "abc123...",
  "message": "All green. Chain tip sealed."
}
```

---

## Billing & Webhooks

### POST /stripe-webhook
**Stripe webhook receiver. Signature verified automatically.**

Supports events:
- `checkout.session.completed` — User upgraded
- `invoice.paid` — Monthly subscription paid
- `customer.subscription.deleted` — User cancelled
- `invoice.payment_failed` — Payment failed

---

## Four Products. One Engine.

### AILeash
- **What:** Every AI decision your platform makes about a person gets scored, explained, and sealed.
- **Who:** Platforms using AI for any regulated decision (lending, hiring, content moderation, fraud, access control).
- **Price:** 50p per device per month + your margin.
- **Free tier:** 100 decisions/month, no card.

### Guardian
- **What:** Free message checker for families. Child pastes a message in, gets instant plain-English assessment against grooming patterns.
- **Who:** Families. Free forever. No card. No catch.
- **Price:** Free. Always.
- **Built for:** ICO Children's Code, Online Safety Act, child safety.

### SonicBoom
- **What:** One line of code. Drops into AWS, Azure, GCP, OpenAI, Anthropic. Adds full compliance audit chain to every call.
- **Who:** Platforms already running AI in the cloud.
- **Price:** 50p per device per month + your margin.
- **Latency:** No impact. Chain sealing is asynchronous.

### Sentinel
- **What:** Fraud and anomaly alerting. Scores unusual patterns (500 messages in a minute, login from new country, velocity spikes) in real-time.
- **Who:** Platforms managing fraud, abuse, takeovers.
- **Price:** 50p per device per month + your margin.
- **Real-time:** Alerts the moment thresholds trip.

---

## The Score Formula (Immutable)

**Raw weighted sum (Σ_raw):**
```
Σ_raw =
  (1 − trust) × 0.30
  + min(velocity_60s / 20, 1) × 0.15
  + min(velocity_5m / 50, 1) × 0.10
  + min(velocity_1h / 200, 1) × 0.10
  + min(ln(1+amount) / ln(1+10000), 1) × 0.15
  + device_risk × 0.10
  + behavioural_anomaly × 0.10
  + country_shift × 0.10
  + unsafe_country × 0.10
```

**Normalization:** the nine weights above sum to 1.20, not 1.0. To keep every signal's *relative* importance exactly as designed while guaranteeing the score behaves as a true 0–1 weighted average (not one that can reach BLOCK-level values from fewer combined signals than intended), divide by the actual weight total before clamping:

```
WEIGHT_TOTAL = 0.30 + 0.15 + 0.10 + 0.10 + 0.15 + 0.10 + 0.10 + 0.10 + 0.10   # = 1.20

score = clamp( Σ_raw / WEIGHT_TOTAL , 0, 1 )

decision = ALLOW if score < 0.35
         = CHALLENGE if score < 0.70
         = BLOCK otherwise
```

No machine learning. No drift. No retraining. Weights are written in code and cannot change without a new release. `WEIGHT_TOTAL` is a fixed constant (1.20) recomputed only if a signal is added, removed, or reweighted in a future release — never at runtime.

---

## Rate Limits

- **Free tier:** 100 decisions/month
- **Paid:** Unlimited (or by plan)
- **Public endpoints:** No rate limit

---

## Documentation

- **Homepage:** https://sebbi.pro
- **Whitepaper:** https://sebbi.pro/whitepaper
- **Developers:** https://sebbi.pro/developers
- **Scanner (free):** https://sebbi.pro/scan
- **Guardian:** https://sebbi.pro/guardian-app
- **Contact:** justrightdecorators@gmail.com

```


## `LICENCE`

22 lines, 1074 bytes

```
MIT License

Copyright (c) 2026 Monop (Blyth, UK)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

```


## `README.md`

277 lines, 15728 bytes

```markdown
<div align="center">

```
        ┌─────────────────────────────────────────────────┐
        │   s e b b i . p r o                              │
        │                                                  │
        │   O N E   C H A I N .   E V E R Y   P R O O F .   │
        └─────────────────────────────────────────────────┘
```

### The tamper-evident evidence layer for AI decisions, payments, and records.

*Every event sealed into a hash chain at the moment it happens —*
*the decision, **and the basis it rested on** — unalterable by anyone. Including us.*

<br>

[![live](https://img.shields.io/badge/live-sebbi.pro-c9a84c?style=for-the-badge)](https://sebbi.pro)
[![verify the chain](https://img.shields.io/badge/verify_the_chain-open_endpoint-7fe3b0?style=for-the-badge)](https://sebbi.pro/api/verify-chain)
[![seal something free](https://img.shields.io/badge/seal_something-free,_no_account-7cc8ff?style=for-the-badge)](https://sebbi.pro/seal)

**[Try it](https://sebbi.pro/seal)** · **[Verify it](https://sebbi.pro/verify)** · **[Read the code](https://sebbi.pro/brain)** · **[Developer docs](https://sebbi.pro/developers)** · **[Whitepaper](https://sebbi.pro/whitepaper)**

</div>

---

> ### *A system that does not trust its own creator*
> ### *is the only kind whose records qualify as evidence.*

---

## Don't read about it. Watch it work.

Here is a **real** four-block chain. Every hash below is reproducible — same inputs, same seals, forever. Copy the recipe at the bottom and compute them yourself.

```
  #   EVENT                             RESULT      SEAL (SHA-256, truncated)
  ─────────────────────────────────────────────────────────────────────────
  1   system_regmap                     ALLOW       411ffd9a31a3d9f4…
  2   seal_post: quarterly_report.pdf   NOTARISED   c7309616a9e92bc7…
  3   govern: payment 9000 GBP          BLOCK       293181a2bc2dab88…
  4   brain: approve supplier 88        ALLOW       6abba40eb964959e…
  ─────────────────────────────────────────────────────────────────────────
  genesis  9fd06d6fdc19761d…                         tip  6abba40eb964959e…
```

Now watch someone try to cover up that blocked £9,000 payment by flipping block 3 from **BLOCK** to **ALLOW**:

```
  block 3 altered  →  tip becomes  5e15bc5710426088…   ❌  ≠ 6abba40eb964959e…
```

**The tip changed. The forgery is exposed instantly, by arithmetic, to anyone — no account, no trust required.** That is the entire product in six lines. Everything below is detail.

<details>
<summary><b>▸ Reproduce every hash yourself (10 lines of Python)</b></summary>

```python
import hashlib, json
seal = lambda prev, ts, ev, res, basis: hashlib.sha256(
    json.dumps({"prev":prev,"ts":ts,"event":ev,"result":res,"basis":basis},
               sort_keys=True).encode()).hexdigest()

prev = hashlib.sha256(b"AILEASH_BRAIN_GENESIS|sebbi.pro|v5").hexdigest()
chain = [("system_regmap","ALLOW","regmap-v7"),
         ("seal_post: quarterly_report.pdf","NOTARISED","NO_BASIS"),
         ("govern: payment 9000 GBP","BLOCK","invoice_4471|regmap-v7"),
         ("brain: approve supplier 88","ALLOW","invoice_4471|regmap-v7")]
ts = 1752940000
for ev,res,basis in chain:
    prev = seal(prev, ts, ev, res, basis); ts += 3600
    print(prev[:16], "…", ev)
# final line prints the tip: 6abba40eb964959e …
```
Change one character of one event and every seal after it changes. That's the whole idea.
</details>

---

## Why this exists

Every system keeps logs. Logs live in databases. Databases can be edited — by an attacker, an insider, or the operator itself. So an ordinary log only ever says *"this is what we currently claim happened."* It can never say *"and nobody changed it since."*

Nobody notices the difference — until a regulator, a court, an insurer, or a customer asks for **proof**. Then *"our system recorded it"* and *"here is proof it wasn't changed"* become two very different sentences. Only the second carries weight.

**sebbi.pro produces the second sentence — automatically, as a by-product of your system doing its normal work.**

---

## The chain, in one formula

```
seal(n) = SHA-256( seal(n−1) · timestamp · event · result · basis )
```

| Property | What it means |
|---|---|
| **Tamper-evident** | Each seal contains its predecessor. Alter history → every later seal fails, publicly. |
| **Gapless receipts** | Every decision gets a sequence number in the same transaction. Edited records break the chain; **missing** records break the sequence. |
| **Truncation-evident** | The tip is anchored per-write. Chop blocks off the end → the anchor breaks. |
| **Basis-sealed** | Not just *what* was decided — *what it rested on*: sources, versions, ruleset. Same block. |
| **Jurisdiction-tagged** | Every decision sealed with the regulatory frameworks that applied to it at that moment. |
| **Fast** | Score + decide + seal + respond inline, **~28 ms** median. |
| **Crash-safe** | WAL journaling, full-sync commits, single-lock seal path, no race window, daily backups. |

> **The one honest boundary, stated up front:** basis-sealing proves **what** a decision relied on — not that it was **correct**. Cryptography verifies integrity, never truth. Any product claiming to prove correctness is misdescribing what maths can do. We won't.

---

## The products — one chain underneath all of them

| | Product | What it does | Access |
|---|---|---|---|
| 🧠 | **Brain** | Instruction gate for AI. Blocks prompt injection, exfiltration, compliance-bypass, child-safety and destruction patterns — with unicode/obfuscation defences — and seals every decision + basis. Pure Python, runs on your machine. | **Free download** |
| ⚡ | **SonicBoom** | Decision engine. Any event scored in ~28ms: ALLOW / CHALLENGE / BLOCK, plain-English reasons, sealed before it replies. Per-user trust learned over time — lost 8× faster than earned, so burst attacks destroy their own standing. Hosted human-oversight challenge flow, itself sealed. | API key |
| 🔐 | **Delegation layer** | Signed authority tokens (who may approve, to what limit, until when — the grant itself sealed), provider-agnostic KYC result sealing (outcome provable, zero personal data held), and per-decision jurisdiction tagging. Article 14 human oversight as engineering. | API key |
| 🛡️ | **Sentinel** | Fraud pattern + velocity detection: credential stuffing, card testing, country-jump takeovers. Flags sealed as evidence. | API key |
| 👁️ | **Guardian** | Child-safety flags: grooming patterns (secrecy, isolation, channel-moving). Content never stored — only fingerprints. Every flag sealed for parents, platforms, authorities. | Platform |
| 📝 | **Post Notary** | Prove exact text existed on a date, unchanged. | **Free, no account** |
| 🆔 | **Identity Notary** | Prove a profile is the genuine original — kills impersonation. | **Free, no account** |
| 💷 | **Payment Notary** | Stop invoice/APP fraud. Seal real bank details once; payers verify a code before funds move. MISMATCH → payment stops. The check itself is sealed. | **Free, no account** |

**Privacy by design:** the notaries fingerprint content *locally*. Your content never leaves your device — only the 64-character hash is sealed. The KYC sealer keeps only the SHA-256 of the provider reference — never the document.

---

## The open standard — `ai.txt`

Like `robots.txt` for crawlers and `security.txt` for researchers — **`ai.txt`** is a public, machine-readable declaration of how your AI is governed: decision model, audit method, regulations designed toward, human override. Its companion **`comply.txt`** declares the rulebook every instruction is subject to.

Declarations are claims. **Sealing them into the chain makes them provable** — and their history tamper-evident.

```
  declaration  →  rulebook  →  enforcement
     ai.txt        comply.txt      brain.py
     "we claim"    "the rules"     "the code that proves it"
```

Publish yours at `/.well-known/ai.txt`. Read [ours](https://sebbi.pro/.well-known/ai.txt).

---

## The stack — how it all fits

```
  DECLARATION    ai.txt · comply.txt     what we claim, publicly
       │
  GATE           Brain                   instructions checked before the AI acts
       │
  DELEGATION     authority · identity ·  who may act, who they legally are,
                 jurisdiction            which rules governed the moment
       │
  DECISION       SonicBoom               every event: allow / challenge / block
       │
  DETECTION      Sentinel · Guardian     attack patterns · child-safety patterns
       │
  PUBLIC ACCESS  the Notaries            the same chain, free, for anyone
       │
       ▼
  ╔══════════════════════════════════════════════════════════════════╗
  ║  EVIDENCE     the hash chain                                      ║
  ║               everything above seals into here —                 ║
  ║               action + basis + receipt · gapless · anchored ·    ║
  ║               publicly verifiable · unalterable by anyone        ║
  ╚══════════════════════════════════════════════════════════════════╝
```

**Evidence accrues as a by-product of the system working.** Nobody remembers to log anything. Nobody compiles an audit file before an inspection. The proof exists because the system ran — equally trustworthy whether the operator is honest or not. Which is the only kind of trustworthy that counts.

---

## Integrate in minutes

```python
# ── Notary: seal anything, free, no key. Content stays on your machine. ──
import hashlib, requests
fp = hashlib.sha256(content.encode()).hexdigest()
requests.post("https://sebbi.pro/api/post/seal", json={"fingerprint": fp})
#   → { sealed, seal, block_index, code }   ← keep the code; anyone can verify it

# ── Decision engine: score + seal an event (API key) ──
requests.post("https://sebbi.pro/api/govern",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","action":"payment","amount":9000,
        "country":"UK","device_id":"d1","anomaly":0,"device_risk":0})
#   → ALLOW / CHALLENGE / BLOCK · reasons · jurisdiction tag · sealed hash · receipt_seq

# ── Delegated authority: grant sealed, enforcement deterministic ──
tok = requests.post("https://sebbi.pro/api/authority/issue",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","role":"payments_approver",
        "max_amount":5000,"ttl_hours":24}).json()["authority_token"]
#   include as "authority_token" in govern events — over-limit or expired
#   authority escalates the verdict with the reason sealed

# ── KYC result: outcome provable, zero personal data held ──
requests.post("https://sebbi.pro/api/identity/kyc-seal",
  headers={"Authorization":"Bearer YOUR_KEY"},
  json={"user_id":"u1","provider":"onfido","verified":True,
        "reference":"chk_9f2"})
#   → only the SHA-256 of the reference is stored — never the document

# ── Brain: gate an instruction and seal its basis (free, local) ──
from brain import BrainGovernor
BrainGovernor().evaluate("approve payment to supplier 88", basis={
  "sources":["invoice_4471.pdf"], "source_versions":["sha256:ab12…"],
  "ruleset":"AI-TXT/1.0 + EU-AI-Act-2024/1689", "ruleset_version":"regmap-v7"})
```

Full reference → **[sebbi.pro/developers](https://sebbi.pro/developers)**

---

## What this evidences — stated precisely

A versioned, hash-sealed **regulation map** links each capability to the obligations it helps evidence: EU AI Act record-keeping, transparency & human-oversight (Articles 9, 12, 13, 14 — delegated-authority tokens directly supporting Article 14's attributable human oversight), UK Online Safety Act duty-of-care documentation, ICO Children's Code. Jurisdiction tagging extends this to the per-decision level: every sealed block records which frameworks applied at the moment of decision.

These tools help you **evidence** your obligations — tamper-evident, explainable, independently verifiable records of what your systems decided and why. **They do not, on their own, make you compliant. No software does. Anyone who says otherwise is selling you something.**

---

## Honest limits — because the whole product is honesty

- **Sealing proves integrity, not truth** — exact content, exact time, unchanged. Not that it was true or agreed to.
- **Basis-sealing proves what was relied on, not that it was right** — cryptography can't verify the real world.
- **Authority tokens prove the grant, not the wisdom** — who was empowered, to what limit, until when. Not that granting it was a good idea.
- **Jurisdiction tagging records applicable frameworks; it does not decide law** — courts do that. It is a versioned, sealed lookup — nothing grander, deliberately.
- **Brain's filter is a first line, not a wall** — known patterns caught; novel phrasing can pass. The guarantee is the sealed record.
- **Fingerprints match exact content** — a re-encoded copy or paraphrase won't match.
- **We evidence compliance; we don't confer it.**

*A vendor who states their limits is giving you the strongest available evidence of how they'll behave when it matters.*

---

## Deployment & pricing

- **Cloud** — a few lines against the hosted API. Notaries and Brain free forever.
- **Sovereign** — the whole engine inside your own network. Offline HMAC-signed 365-day licences, no phone-home, air-gap ready.
- **50p per active device / month.** Partners set their own pricing above the platform fee.

## Investors

The whitepaper carries a dedicated investor section — market timing (EU AI Act, August 2026), the metered per-device model, the moat, and the stage stated honestly: **[sebbi.pro/whitepaper](https://sebbi.pro/whitepaper)** · justin@monopcontent.com

---

<div align="center">

## Check us. Don't trust us.

*That's not a slogan. It's the design requirement — and the only standard by which an evidence layer should ever be judged.*

**[Verify the chain now →](https://sebbi.pro/api/verify-chain)**

<br>

```
  Built by Justin Dobson · Monop Content · Blyth, Northumberland, UK
  Solo-built, from scratch, on a phone —
  because the evidence layer wasn't going to build itself.
```

[LinkedIn](https://www.linkedin.com/in/justin-dobson-037721217) · [sebbi.pro](https://sebbi.pro)

</div>

<!--
Keywords: tamper-evident audit trail · AI governance · AI compliance evidence ·
EU AI Act record keeping · hash chain audit log · APP fraud prevention ·
invoice verification · prompt injection defence · AI decision audit ·
delegated authority tokens · KYC evidence sealing · jurisdiction tagging ·
ai.txt standard · comply.txt · cryptographic proof of action · immutable audit log ·
agentic AI governance · sovereign AI deployment · SonicBoom · Brain · Sentinel · Guardian
-->

```


## `admin.html`

212 lines, 12327 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>sebbi.pro - Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#fff;line-height:1.5}
.wrap{max-width:1000px;margin:0 auto;padding:20px}
h1{font-size:22px;font-weight:800;margin-bottom:4px}h1 span{color:#c9a84c}
.sub{color:#8a90a6;font-size:13px;margin-bottom:20px}
/* login */
#login{max-width:360px;margin:80px auto;text-align:center}
#login input{width:100%;padding:14px;border-radius:10px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:16px;margin:12px 0}
button{background:#c9a84c;color:#0a0f1e;border:none;border-radius:10px;padding:13px 22px;font-weight:800;cursor:pointer;font-size:15px;width:100%}
button.small{width:auto;padding:8px 16px;font-size:13px}
.err{color:#ff7b6e;font-size:13px;margin-top:8px;min-height:18px}
/* dashboard */
#dash{display:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.stat{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:16px}
.stat .big{font-size:26px;font-weight:800;color:#c9a84c}
.stat .lab{font-size:11px;color:#8a90a6;text-transform:uppercase;letter-spacing:1px;margin-top:4px}
.stat.good .big{color:#7fe3b0}.stat.bad .big{color:#ff7b6e}
.tabs{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.tab{background:#111a30;border:1px solid #232d4a;color:#8a90a6;padding:9px 16px;border-radius:8px;cursor:pointer;font-size:13px;font-weight:600}
.tab.on{background:#c9a84c;color:#0a0f1e;border-color:#c9a84c}
.panel{display:none}.panel.on{display:block}
.card{background:#111a30;border:1px solid #232d4a;border-radius:12px;padding:14px;margin-bottom:10px;font-size:14px}
.card .top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:6px}
.card .nm{font-weight:700}
.card .meta{color:#8a90a6;font-size:12px}
.badge{font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700;text-transform:uppercase}
.badge.paid{background:#0d2018;color:#7fe3b0;border:1px solid #1fae79}
.badge.free{background:#1a1206;color:#c9a84c;border:1px solid #c9a84c}
.stripe-link{color:#7fe3b0;font-size:12px;text-decoration:none;font-family:monospace}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}
.mono{font-family:monospace;font-size:12px;color:#8a90a6;word-break:break-all}
.empty{color:#5a6178;text-align:center;padding:30px;font-size:14px}
a.ext{display:inline-block;background:#0d2018;border:1px solid #1fae79;color:#7fe3b0;padding:10px 16px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600;margin-bottom:16px}
</style>
</head>
<body>
<div class="wrap">

  <div id="login">
    <h1>sebbi<span>.pro</span> admin</h1>
    <div class="sub">Private control panel</div>
    <input id="pw" type="password" placeholder="Admin password" onkeydown="if(event.key==='Enter')doLogin()">
    <button onclick="doLogin()">Log in</button>
    <div class="err" id="loginerr"></div>
  </div>

  <div id="dash">
    <div class="bar">
      <div><h1>sebbi<span>.pro</span> admin</h1><div class="sub">Everything Stripe doesn't show you</div></div>
      <button class="small" onclick="logout()">Log out</button>
    </div>

    <a class="ext" href="https://dashboard.stripe.com" target="_blank" rel="noopener">Open Stripe dashboard for payments, revenue &amp; billing addresses &rarr;</a>

    <div class="stats" id="statgrid"></div>

    <div class="tabs">
      <div class="tab on" onclick="show('customers',this)">Customers &amp; leads</div>
      <div class="tab" onclick="show('contacts',this)">Contact messages</div>
      <div class="tab" onclick="show('referrals',this)">Referrals</div>
      <div class="tab" onclick="show('audit',this)">Audit records</div>
    </div>

    <div class="panel on" id="p-customers"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-contacts"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-referrals"><div class="empty">Loading...</div></div>
    <div class="panel" id="p-audit">
      <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;align-items:center">
        <input id="auditkey" placeholder="Filter by API key (optional)" style="flex:1;min-width:180px;padding:10px;border-radius:8px;border:1px solid #2a3350;background:#0b1226;color:#fff;font-size:13px">
        <button class="small" onclick="loadAudit()">Search</button>
        <button class="small" onclick="verifyChain()" style="background:#1fae79">Verify chain</button>
        <button class="small" onclick="exportAudit()" style="background:#0d2018;color:#7fe3b0;border:1px solid #1fae79">Export</button>
      </div>
      <div id="auditchain" style="font-family:monospace;font-size:12px;color:#7fe3b0;margin-bottom:12px"></div>
      <div id="auditlist"><div class="empty">Loading...</div></div>
    </div>
  </div>

</div>
<script>
var TOKEN="";
function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
function when(ts){if(!ts)return"";try{return new Date(ts*1000).toLocaleString()}catch(e){return""}}

async function doLogin(){
  var pw=document.getElementById("pw").value;
  document.getElementById("loginerr").textContent="";
  try{
    var r=await fetch("/admin/auth",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:pw})});
    var d=await r.json();
    if(d.token){TOKEN=d.token;document.getElementById("login").style.display="none";document.getElementById("dash").style.display="block";loadAll();}
    else if(d.error==="admin_disabled"){document.getElementById("loginerr").textContent="Admin password not set. Add ADMIN_PASSWORD in Railway variables.";}
    else if(d.error==="too_many_attempts"){document.getElementById("loginerr").textContent="Too many attempts. Wait a minute.";}
    else{document.getElementById("loginerr").textContent="Wrong password.";}
  }catch(e){document.getElementById("loginerr").textContent="Connection error.";}
}
function logout(){TOKEN="";document.getElementById("dash").style.display="none";document.getElementById("login").style.display="block";document.getElementById("pw").value="";}

async function api(path){
  var r=await fetch(path,{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:"{}"});
  return await r.json();
}

async function loadAll(){
  // stats
  try{
    var s=await api("/admin/stats");
    document.getElementById("statgrid").innerHTML=
      stat(s.total_keys,"Total signups")+
      stat(s.paid_keys,"Paying",  "good")+
      stat((s.total_keys||0)-(s.paid_keys||0),"Free / leads")+
      stat(s.audit_blocks,"Audit blocks")+
      stat(s.chain_valid?"OK":"BROKEN","Chain",s.chain_valid?"good":"bad");
  }catch(e){}
  loadCustomers();loadContacts();loadReferrals();loadAudit();
}
function stat(v,l,cls){return '<div class="stat '+(cls||"")+'"><div class="big">'+esc(v)+'</div><div class="lab">'+esc(l)+'</div></div>';}

async function loadCustomers(){
  try{
    var d=await api("/admin/keys");var ks=d.keys||[];
    if(!ks.length){document.getElementById("p-customers").innerHTML='<div class="empty">No signups yet.</div>';return;}
    var h="";
    ks.forEach(function(k){
      var paid=k.is_paid==1;
      h+='<div class="card"><div class="top"><span class="nm">'+esc(k.name||"(no name)")+' <span class="meta">'+esc(k.org||"")+'</span></span>'
        +'<span class="badge '+(paid?"paid":"free")+'">'+(paid?"paying":"free")+'</span></div>'
        +'<div class="meta">'+esc(k.email||"")+' &middot; '+esc(k.product||"")+' &middot; '+esc(k.devices||0)+' devices &middot; used '+esc(k.actions_used||0)+'/'+esc(k.free_quota||0)+'</div>'
        +'<div class="meta">Joined '+when(k.created)+'</div>'
        +(k.key?'<div class="mono">'+esc(k.key)+'</div>':'')
        +'</div>';
    });
    document.getElementById("p-customers").innerHTML=h;
  }catch(e){document.getElementById("p-customers").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadContacts(){
  try{
    var d=await api("/admin/contacts");var cs=d.contacts||[];
    if(!cs.length){document.getElementById("p-contacts").innerHTML='<div class="empty">No messages yet.</div>';return;}
    var h="";
    cs.forEach(function(c){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(c.name||"(no name)")+'</span><span class="meta">'+when(c.ts)+'</span></div>'
        +'<div class="meta">'+esc(c.email||"")+(c.phone?' &middot; '+esc(c.phone):'')+(c.org?' &middot; '+esc(c.org):'')+'</div>'
        +'<div style="margin-top:6px">'+esc(c.message||"")+'</div></div>';
    });
    document.getElementById("p-contacts").innerHTML=h;
  }catch(e){document.getElementById("p-contacts").innerHTML='<div class="empty">Could not load.</div>';}
}

async function loadReferrals(){
  try{
    var d=await api("/admin/referrals");var rs=d.referrals||[];
    if(!rs.length){document.getElementById("p-referrals").innerHTML='<div class="empty">No referrals yet.</div>';return;}
    var h="";
    rs.forEach(function(r){
      h+='<div class="card"><div class="top"><span class="nm">'+esc(r.referrer_name||"(no name)")+' <span class="meta">'+esc(r.code||"")+'</span></span>'
        +'<span class="badge paid">&pound;'+((r.earnings_pence||0)/100).toFixed(2)+'</span></div>'
        +'<div class="meta">'+esc(r.referrer_email||"")+' &middot; '+esc(r.devices_referred||0)+' devices referred</div></div>';
    });
    document.getElementById("p-referrals").innerHTML=h;
  }catch(e){document.getElementById("p-referrals").innerHTML='<div class="empty">Could not load.</div>';}
}

var LAST_AUDIT=[];
async function loadAudit(){
  try{
    var key=document.getElementById("auditkey").value.trim();
    var r=await fetch("/admin/audit",{method:"POST",headers:{"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json"},body:JSON.stringify({limit:500,api_key:key})});
    var d=await r.json();LAST_AUDIT=d.records||[];
    document.getElementById("auditchain").innerHTML=(d.chain_valid?"CHAIN INTACT":"CHAIN BROKEN")+" &middot; "+esc(d.chain_blocks)+" blocks &middot; tip "+esc(String(d.chain_tip||"").slice(0,24))+"...";
    if(!LAST_AUDIT.length){document.getElementById("auditlist").innerHTML='<div class="empty">No sealed records'+(key?" for that key":"")+' yet.</div>';return;}
    var h="";
    LAST_AUDIT.forEach(function(a){
      var dec=esc(a.decision||"");
      var col=dec==="BLOCK"?"#ff7b6e":dec==="CHALLENGE"?"#c9a84c":"#7fe3b0";
      h+='<div class="card"><div class="top"><span class="nm">#'+esc(a.seq)+' <span style="color:'+col+'">'+dec+'</span></span><span class="meta">'+when(a.ts)+'</span></div>'
        +'<div class="meta">user: '+esc(a.user_id||"-")+(a.score!==""?' &middot; score '+esc(a.score):'')+(a.reasons&&a.reasons.length?' &middot; '+esc(a.reasons.join(", ")):'')+'</div>'
        +'<div class="mono" style="margin-top:6px">seal: '+esc(String(a.audit_hash||"").slice(0,40))+'...</div>'
        +'<div class="mono">prev: '+esc(String(a.prev_hash||"").slice(0,40))+'...</div></div>';
    });
    document.getElementById("auditlist").innerHTML=h;
  }catch(e){document.getElementById("auditlist").innerHTML='<div class="empty">Could not load audit records.</div>';}
}
async function verifyChain(){
  try{
    var r=await fetch("/api/verify-chain");var d=await r.json();
    document.getElementById("auditchain").innerHTML=(d.valid?"VERIFIED - CHAIN INTACT":"WARNING - CHAIN BROKEN")+" &middot; "+esc(d.blocks)+" blocks &middot; "+esc(d.message||"");
  }catch(e){}
}
function exportAudit(){
  var blob=new Blob([JSON.stringify(LAST_AUDIT,null,2)],{type:"application/json"});
  var url=URL.createObjectURL(blob);var a=document.createElement("a");
  a.href=url;a.download="sebbi-audit-export-"+Date.now()+".json";a.click();URL.revokeObjectURL(url);
}
function show(name,el){
  document.querySelectorAll(".tab").forEach(function(t){t.className="tab";});el.className="tab on";
  document.querySelectorAll(".panel").forEach(function(p){p.className="panel";});
  document.getElementById("p-"+name).className="panel on";
}
</script>
</body>
</html>

```


## `ai-standard.html`

97 lines, 4847 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0f1e">
<title>ai.txt - Free Download</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#e8e8f0;min-height:100vh;display:flex;flex-direction:column}
nav{border-bottom:1px solid #1e2a45;padding:16px 20px}
nav a{color:#c9a84c;text-decoration:none;font-family:monospace;font-size:14px}
.wrap{flex:1;display:flex;align-items:center;justify-content:center;padding:30px 20px}
.card{max-width:560px;width:100%;background:#0d1428;border:1px solid #1e2a45;border-radius:16px;padding:36px 28px;text-align:center}
h1{font-size:32px;font-weight:800;margin-bottom:14px;line-height:1.15}
h1 span{color:#c9a84c}
p{color:#8a90a6;font-size:15px;line-height:1.7;margin-bottom:14px}
p b{color:#e8e8f0}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;width:100%;background:#c9a84c;color:#0a0f1e;padding:18px;border-radius:10px;font-weight:800;font-size:17px;border:none;cursor:pointer;font-family:inherit;margin:20px 0 10px}
.sub{font-family:monospace;font-size:12px;color:#7fe3b0;margin-bottom:24px}
.steps{text-align:left;background:#0b1226;border:1px solid #1e2a45;border-radius:10px;padding:18px 20px;margin-top:8px}
.steps li{color:#8a90a6;font-size:14px;margin:10px 0 10px 6px;line-height:1.6}
.steps li b{color:#c9a84c}
.back{margin-top:22px}
.back a{color:#c9a84c;text-decoration:none;font-size:14px;font-weight:600}
footer{border-top:1px solid #1e2a45;padding:20px;text-align:center;color:#5a6178;font-size:12px}
footer a{color:#c9a84c;text-decoration:none}
</style>
</head>
<body>
<nav><a href="/">&larr; AILeash</a></nav>
<div class="wrap">
  <div class="card">
    <h1>Download <span>ai.txt</span> &mdash; free</h1>
    <div class="sub">NO KEY &middot; NO ACCOUNT &middot; NO COST</div>
    <p>ai.txt is the free, open standard for declaring how your AI is governed. Download the file, and it shows your system exactly what it needs to become compliant.</p>
    <button class="btn" onclick="downloadIt()">&#8681; Download ai.txt free</button>
    <ul class="steps">
      <li><b>1.</b> Tap download &mdash; the file saves as ai.txt</li>
      <li><b>2.</b> Fill in your details, put it on your domain at yourdomain.com/ai.txt</li>
      <li><b>3.</b> Want it verified and provable? <b><a href="/" style="color:#c9a84c">Come back to AILeash</a></b> to seal it into a tamper-evident chain.</li>
    </ul>
    <div class="back"><a href="/ai.txt">See the live ai.txt &rarr;</a></div>
  </div>
</div>
<footer>ai.txt is a free, open standard by <a href="/">Monop Content</a> &middot; Blyth, UK &middot; <a href="/ai.txt">reference</a></footer>
<script>
var AITXT = [
"# ============================================================================",
"# ai.txt - AI Governance Declaration  (AI-TXT/1.0)",
"# A free, open standard. Copy this to the root of your domain as /ai.txt",
"# Replace the values below with your own. Delete any line that does not apply.",
"# No key, no account, no permission, no cost. Just publish it.",
"# See it live: https://sebbi.pro/ai.txt",
"# ============================================================================",
"",
"Standard: AI-TXT/1.0",
"Operator: YOUR COMPANY NAME",
"Operator-Location: YOUR CITY, COUNTRY",
"Contact: you@yourdomain.com",
"Last-Updated: 2026-01-01",
"",
"# --- How your AI makes decisions ---",
"Decision-Model: describe it (deterministic rules / ML model / human-in-loop)",
"Decision-Outcomes: ALLOW, REVIEW, BLOCK",
"Human-Override: yes / no",
"Plain-Language-Reasons: yes / no",
"",
"# --- Your audit record (how you prove what happened) ---",
"Audit-Chain: describe it (SHA-256 hash chain / signed logs / none)",
"Chain-Property: tamper-evident / tamper-resistant / none",
"Verify-Endpoint: https://yourdomain.com/your-verify-url",
"",
"# --- Regulations you are designing towards ---",
"Regulation: EU AI Act 2024/1689",
"Regulation: UK Online Safety Act 2023",
"",
"# --- Optional: public status surfaces ---",
"Live-Status: https://yourdomain.com/health",
"Whitepaper: https://yourdomain.com/whitepaper",
"",
"# ============================================================================",
"# ai.txt is a free, open standard. Publish yours, share it, build on it.",
"# ============================================================================"
].join("\n");
function downloadIt(){
  var blob = new Blob([AITXT], {type:"text/plain"});
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url; a.download = "ai.txt";
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
</script>
</body>
</html>

```


## `ai-txt-kit.html`

86 lines, 6554 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0f1e">
<title>ai.txt Starter Kit &mdash; publish AI governance free in 5 minutes</title>
<meta name="description" content="Publish an ai.txt on your own domain, free. Copy the template, add the badge, make it provable. No key, no account.">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#0a0f1e;color:#e8e8f0;line-height:1.6}
.mono{font-family:"JetBrains Mono",ui-monospace,Menlo,monospace}
nav{position:sticky;top:0;z-index:10;background:rgba(10,15,30,.94);backdrop-filter:blur(10px);border-bottom:1px solid #1e2a45;padding:0 20px;height:54px;display:flex;align-items:center;justify-content:space-between}
nav a.logo{display:flex;align-items:center;gap:8px;color:#c9a84c;text-decoration:none;font-family:"JetBrains Mono",monospace;font-size:13px}
nav .links a{color:#8a90a6;text-decoration:none;font-size:13px;margin-left:16px}
.wrap{max-width:760px;margin:0 auto;padding:44px 20px 90px}
.eyebrow{font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#c9a84c;margin-bottom:12px}
h1{font-size:34px;font-weight:800;letter-spacing:-.02em;line-height:1.1;margin-bottom:14px}
h1 span{color:#c9a84c}
.lede{color:#8a90a6;font-size:16px;margin-bottom:8px}
.free{display:inline-block;background:rgba(0,229,160,.1);border:1px solid #00b87d;color:#7fe3b0;font-family:"JetBrains Mono",monospace;font-size:12px;padding:5px 12px;border-radius:5px;margin:14px 0 30px}
h2{font-size:20px;font-weight:700;margin:40px 0 8px;padding-top:26px;border-top:1px solid #1e2a45}
.step-n{font-family:"JetBrains Mono",monospace;color:#c9a84c;font-size:13px}
p{color:#8a90a6;margin-bottom:14px}
p b{color:#e8e8f0}
.box{background:#0b1226;border:1px solid #1e2a45;border-radius:10px;padding:18px;margin:16px 0;font-family:"JetBrains Mono",monospace;font-size:12.5px;color:#7fe3b0;white-space:pre-wrap;word-break:break-word;line-height:1.8;overflow-x:auto}
.btn{display:inline-flex;align-items:center;gap:8px;background:#c9a84c;color:#0a0f1e;padding:12px 22px;border-radius:8px;font-weight:800;font-size:14px;text-decoration:none;border:none;cursor:pointer;font-family:inherit}
.btn.ghost{background:transparent;border:1px solid #2a3350;color:#e8e8f0}
.btnrow{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.badge-demo{display:inline-flex;align-items:center;gap:8px;background:#111a30;border:1px solid #c9a84c;border-radius:8px;padding:8px 14px;font-family:"JetBrains Mono",monospace;font-size:12px;color:#c9a84c;text-decoration:none}
.badge-demo svg{flex-shrink:0}
.onramp{background:linear-gradient(135deg,rgba(0,229,160,.06),rgba(201,168,76,.05));border:1px solid #00b87d;border-radius:12px;padding:24px;margin-top:30px}
.onramp h3{color:#7fe3b0;font-size:16px;margin-bottom:8px}
.onramp p{color:#a9b0c4}
.copied{color:#7fe3b0;font-size:12px;margin-left:10px;opacity:0;transition:opacity .2s}
.copied.show{opacity:1}
footer{border-top:1px solid #1e2a45;padding:26px 20px;text-align:center;color:#5a6178;font-size:12px}
footer a{color:#c9a84c;text-decoration:none}
</style>
</head>
<body>
<nav>
  <a class="logo" href="/"><svg width="18" height="18" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="2.6" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.1" fill="#c9a84c"/></svg>AILeash</a>
  <div class="links"><a href="/ai.txt">Spec</a><a href="/whitepaper">Whitepaper</a></div>
</nav>
<div class="wrap">
  <div class="eyebrow">// ai.txt starter kit</div>
  <h1>Publish AI governance on your own site. <span>Free.</span></h1>
  <p class="lede">ai.txt is the robots.txt of AI governance: one small file at your domain root that declares how your AI is governed and where anyone can verify it. Here is everything you need to publish one in about five minutes.</p>
  <div class="free">FREE STANDARD &middot; NO KEY &middot; NO ACCOUNT &middot; NO PERMISSION</div>

  <h2><span class="step-n">01 /</span> Grab the template</h2>
  <p>A ready-to-fill ai.txt with every line commented. Download it, or read the live example on our own domain.</p>
  <div class="btnrow">
    <a class="btn" href="/ai-txt-template.txt" download="ai.txt">&#8681; Download template</a>
    <a class="btn ghost" href="/ai.txt" target="_blank">Read a live example</a>
  </div>

  <h2><span class="step-n">02 /</span> Fill it in and publish</h2>
  <p>Replace the example values with your own facts. <b>Delete any line you cannot back with a real verify endpoint</b> &mdash; an honest short ai.txt beats an aspirational long one. Then upload it to the root of your domain so it lives at:</p>
  <div class="box">https://yourdomain.com/ai.txt</div>
  <p>That is the whole spec. One file, at the root, readable by anyone &mdash; a regulator, a partner, or another machine deciding whether to trust you.</p>

  <h2><span class="step-n">03 /</span> Add the badge</h2>
  <p>Show visitors and crawlers that you have declared your AI governance. Copy this HTML onto your site &mdash; it renders a small badge linking to your ai.txt:</p>
  <p>Preview:</p>
  <a class="badge-demo" href="/ai.txt"><svg width="14" height="14" viewBox="0 0 32 32"><circle cx="16" cy="16" r="13.5" fill="none" stroke="#c9a84c" stroke-width="3" stroke-dasharray="66 20" stroke-linecap="round" transform="rotate(-50 16 16)"/><circle cx="26.5" cy="7" r="3.4" fill="#c9a84c"/></svg>AI-Governed &middot; ai.txt</a>
  <div class="box" id="badge">&lt;a href="/ai.txt" style="display:inline-flex;align-items:center;gap:6px;font-family:monospace;font-size:12px;color:#c9a84c;text-decoration:none;border:1px solid #c9a84c;border-radius:6px;padding:6px 10px"&gt;AI-Governed &middot; ai.txt&lt;/a&gt;</div>
  <button class="btn ghost" onclick="copyBadge()">Copy badge HTML<span class="copied" id="cp">copied</span></button>

</div>
</div>
<footer>
  ai.txt (AI-TXT/1.0) is a free, open standard by <a href="/">Monop Content</a> &middot; Blyth, UK &middot; <a href="/ai.txt">spec</a> &middot; <a href="/comply.txt">comply.txt</a>
</footer>
<script>
function copyBadge(){
  var t=document.getElementById('badge').textContent;
  navigator.clipboard.writeText(t).then(function(){
    var c=document.getElementById('cp');c.classList.add('show');setTimeout(function(){c.classList.remove('show')},1500);
  });
}
</script>
</body>
</html>

```


## `aileash-game.html`

665 lines, 26104 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#05070f">
<meta name="robots" content="noindex">
<title>AILeash — Deep Run</title>
<style>
:root{--ink:#05070f;--ink2:#0d1424;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80;--mute:#7d89a8;
  --line:rgba(201,168,76,.22)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;margin:0;overflow:hidden;background:#05070f;color:#e8edf7;
  font-family:"Inter","Helvetica Neue",Helvetica,Arial,sans-serif;overscroll-behavior:none}
.num{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-variant-numeric:tabular-nums}
#wrap{position:fixed;inset:0}
canvas{display:block;width:100%;height:100%;touch-action:none}

#hud{position:absolute;left:0;right:0;top:0;z-index:10;display:flex;align-items:flex-start;
  gap:16px;padding:10px 14px;padding-top:calc(10px + env(safe-area-inset-top));
  pointer-events:none}
#hud .cell{display:flex;flex-direction:column;gap:1px}
#hud .k{font-size:9px;letter-spacing:.1em;color:var(--mute)}
#hud .v{font-size:15px;font-weight:700;text-shadow:0 0 10px rgba(0,0,0,.9)}
#combo{color:var(--gold)}
#right{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:5px}
#hull{width:88px;height:7px;border:1px solid rgba(201,168,76,.5);border-radius:3px;overflow:hidden}
#hullF{height:100%;width:100%;background:linear-gradient(90deg,#ff8a80,#7fe3b0);
  transition:width .2s}
#sector{font-size:9px;letter-spacing:.1em;color:var(--mute)}

.screen{position:absolute;inset:0;z-index:20;display:none;flex-direction:column;
  align-items:center;justify-content:center;gap:16px;padding:28px 22px;text-align:center;
  background:rgba(5,7,15,.93);overflow-y:auto}
.screen.on{display:flex}
h1{margin:0;font-size:36px;font-weight:800;letter-spacing:-.02em;line-height:1}
h1 span{color:var(--gold)}
h2{margin:0;font-size:22px;font-weight:700}
p.lede{margin:0;max-width:32ch;font-size:14px;line-height:1.55;color:#b6c0d6}
.btn{border:0;border-radius:11px;padding:15px 32px;font-size:15px;font-weight:700;
  background:var(--gold);color:#05070f;cursor:pointer;min-width:210px}
.btn.ghost{background:transparent;color:var(--gold);border:1.5px solid var(--line)}
.stats{display:flex;gap:28px;justify-content:center;flex-wrap:wrap}
.stats .k{font-size:9px;letter-spacing:.1em;color:var(--mute)}
.stats .v{font-size:26px;font-weight:700}
#lv{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;width:100%;max-width:280px}
#lv button{aspect-ratio:1;border-radius:8px;border:1px solid var(--line);cursor:pointer;
  background:rgba(255,255,255,.03);color:#c3cbdd;font-size:14px;font-weight:700;
  font-family:ui-monospace,monospace}
#lv button.done{background:rgba(201,168,76,.16);color:var(--gold);border-color:var(--gold)}
#lv button.lock{opacity:.25;cursor:not-allowed}
#flash{position:absolute;left:0;right:0;top:30%;z-index:15;text-align:center;
  font-size:19px;font-weight:700;pointer-events:none;opacity:0;transition:opacity .35s;
  text-shadow:0 0 16px rgba(0,0,0,.9)}
#hint{position:absolute;left:0;right:0;bottom:calc(12px + env(safe-area-inset-bottom));
  z-index:10;text-align:center;font-size:11px;letter-spacing:.05em;color:var(--mute);
  pointer-events:none}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>
</head>
<body>
<div id="wrap">
<canvas id="cv"></canvas>

<div id="hud">
  <div class="cell"><div class="k">SCORE</div><div class="v num" id="hScore">0</div></div>
  <div class="cell"><div class="k">SECTOR</div><div class="v num" id="hLevel">1</div></div>
  <div class="cell"><div class="k">COMBO</div><div class="v num" id="combo">x1</div></div>
  <div id="right">
    <div id="hull"><div id="hullF"></div></div>
    <div id="sector">HULL</div>
  </div>
</div>

<div id="flash"></div>
<div id="hint">Drag to fly</div>

<div class="screen on" id="scTitle">
  <h1>AI<span>Leash</span></h1>
  <h2>Deep Run</h2>
  <p class="lede">Ten sectors, out past the rings and back. Drag to fly your ship — the guns fire themselves. Don't let them reach you.</p>
  <button class="btn" id="bStart">Launch</button>
  <button class="btn ghost" id="bPick">Choose a sector</button>
  <p class="lede" style="font-size:11.5px" id="bestLine"></p>
</div>

<div class="screen" id="scPick">
  <h2>Choose a sector</h2>
  <p class="lede" id="pickSub"></p>
  <div id="lv"></div>
  <button class="btn ghost" id="bBack">Back</button>
</div>

<div class="screen" id="scNext">
  <h2 id="nextTitle">Sector clear</h2>
  <div class="stats">
    <div><div class="k">SCORE</div><div class="v num" id="nScore">0</div></div>
    <div><div class="k">KILLS</div><div class="v num" id="nKills">0</div></div>
  </div>
  <p class="lede" id="nextNote"></p>
  <button class="btn" id="bNext">Next sector</button>
  <button class="btn ghost" id="bQuit">Back to start</button>
</div>

<div class="screen" id="scOver">
  <h2>Hull breached</h2>
  <div class="stats">
    <div><div class="k">SCORE</div><div class="v num" id="oScore">0</div></div>
    <div><div class="k">SECTOR</div><div class="v num" id="oLevel">1</div></div>
    <div><div class="k">KILLS</div><div class="v num" id="oKills">0</div></div>
  </div>
  <p class="lede" id="overNote"></p>
  <button class="btn" id="bRetry">Fly it again</button>
  <button class="btn ghost" id="bHome">Back to start</button>
</div>
</div>

<script>
(function(){
"use strict";

var cv=document.getElementById("cv"),ctx=cv.getContext("2d");
var W=0,H=0,dpr=1,CX=0,CY=0,F=460,MAXLV=10;

/* ---------- sectors ---------- */
var SECTORS=[
 {name:"Rings of Saturn", sky:"#0a1020", planet:"saturn",  count:26, speed:340, fire:0.30, mix:["scout","scout","hulk"]},
 {name:"Ochre Belt",      sky:"#120c14", planet:"rust",    count:30, speed:380, fire:0.45, mix:["scout","hulk","mine"]},
 {name:"Blue Giant",      sky:"#08111f", planet:"ice",     count:34, speed:420, fire:0.60, mix:["scout","darter","hulk"]},
 {name:"Ash Field",       sky:"#0d0d12", planet:"moon",    count:38, speed:455, fire:0.75, mix:["darter","mine","hulk"]},
 {name:"Green Drift",     sky:"#07130f", planet:"jade",    count:42, speed:490, fire:0.90, mix:["scout","darter","turret"]},
 {name:"Inner Rings",     sky:"#0a1020", planet:"saturn",  count:46, speed:525, fire:1.05, mix:["darter","hulk","turret"]},
 {name:"Crimson Reach",   sky:"#140a0d", planet:"ember",   count:50, speed:560, fire:1.20, mix:["darter","mine","turret"]},
 {name:"Shattered Moon",  sky:"#0b0e16", planet:"moon",    count:54, speed:600, fire:1.35, mix:["hulk","turret","darter"]},
 {name:"The Long Dark",   sky:"#050710", planet:"void",    count:60, speed:640, fire:1.55, mix:["darter","turret","mine","hulk"]},
 {name:"The Nest",        sky:"#12070c", planet:"ember",   count:26, speed:600, fire:1.30, mix:["darter","turret"], boss:true}
];

/* ---------- enemies ---------- */
var TYPE={
 scout: {hp:1,pts:60, r:26,col:"#7fe3b0",spd:1.00,sway:1.0,shoot:0.5},
 darter:{hp:1,pts:110,r:22,col:"#8fd0ff",spd:1.55,sway:2.2,shoot:0.7},
 hulk:  {hp:4,pts:220,r:44,col:"#c9a84c",spd:0.72,sway:0.4,shoot:0.8},
 mine:  {hp:1,pts:90, r:24,col:"#ff8a80",spd:0.85,sway:0.0,shoot:0.0},
 turret:{hp:2,pts:170,r:30,col:"#f5c26b",spd:0.80,sway:0.7,shoot:2.0}
};

/* ---------- state ---------- */
var level=1,cfg=SECTORS[0],running=false,paused=true;
var score=0,kills=0,hull=100,streak=0,mult=1;
var stars=[],dust=[],foes=[],bolts=[],flak=[],pops=[],rocks=[];
var boss=null,spawned=0,spawnT=0,shotT=0,shake=0,warp=0,last=0;
var ship={x:0,y:0,tx:0,ty:0,roll:0,inv:0};
var prog=load();

function load(){try{var r=localStorage.getItem("aileash.deeprun");
  return r?JSON.parse(r):{lv:0,best:0};}catch(e){return{lv:0,best:0};}}
function save(){try{localStorage.setItem("aileash.deeprun",JSON.stringify(prog));}catch(e){}}
function clamp(v,a,b){return v<a?a:(v>b?b:v);}
function rnd(a,b){return a+Math.random()*(b-a);}
function pick(a){return a[(Math.random()*a.length)|0];}

function resize(){
  dpr=Math.min(window.devicePixelRatio||1,2);
  W=window.innerWidth;H=window.innerHeight;CX=W/2;CY=H*0.46;
  cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  F=Math.max(380,Math.min(W,H)*1.15);
}
window.addEventListener("resize",resize);
window.addEventListener("orientationchange",function(){setTimeout(resize,200);});

/* ---------- projection ---------- */
function proj(x,y,z){
  var s=F/z;
  return {x:CX+(x-ship.x*0.45)*s, y:CY+(y-ship.y*0.45)*s, s:s};
}

/* ---------- world build ---------- */
function fieldInit(){
  stars=[];dust=[];rocks=[];
  for(var i=0;i<190;i++)
    stars.push({x:rnd(-2600,2600),y:rnd(-1800,1800),z:rnd(60,3600),b:rnd(0.35,1)});
  for(i=0;i<70;i++)
    dust.push({x:rnd(-1400,1400),y:rnd(-900,900),z:rnd(60,2400)});
  if(cfg.planet==="saturn"||cfg.planet==="moon"){
    for(i=0;i<26;i++)
      rocks.push({x:rnd(-1600,1600),y:rnd(-700,700),z:rnd(400,3400),r:rnd(6,26),sp:rnd(0.5,1.2)});
  }
}

function build(n){
  level=n;cfg=SECTORS[n-1];
  foes=[];bolts=[];flak=[];pops=[];boss=null;
  spawned=0;spawnT=0.8;shotT=0;shake=0;warp=1.1;
  ship.x=0;ship.y=0;ship.tx=0;ship.ty=0;ship.roll=0;ship.inv=1.4;
  fieldInit();
  if(cfg.boss) boss={hp:150,max:150,x:0,y:-40,z:1500,t:0,ph:0,r:190};
  document.body.style.background=cfg.sky;
}

/* ---------- spawning ---------- */
function spawnFoe(){
  var t=pick(cfg.mix),d=TYPE[t];
  foes.push({t:t,hp:d.hp,r:d.r,col:d.col,
    x:rnd(-460,460),y:rnd(-320,300),z:rnd(2400,3000),
    ph:rnd(0,6.3),fire:rnd(0.8,2.6),dead:false});
  spawned++;
}

/* ---------- feedback ---------- */
var flashEl=document.getElementById("flash"),flashT=0;
function say(t,c){flashEl.textContent=t;flashEl.style.color=c||"#c9a84c";
  flashEl.style.opacity="1";flashT=1.1;}
function pop(x,y,z,col,n){
  for(var i=0;i<n;i++)
    pops.push({x:x,y:y,z:z,vx:rnd(-160,160),vy:rnd(-160,160),vz:rnd(-90,140),
      life:1,col:col});
}

/* ---------- loop ---------- */
function step(t){
  if(!running)return;
  var dt=Math.min((t-last)/1000,0.05);last=t;
  if(!paused)update(dt);
  render(dt);
  requestAnimationFrame(step);
}

function update(dt){
  var sp=cfg.speed*(warp>0?2.6:1);
  if(warp>0)warp-=dt;
  if(shake>0)shake-=dt*3;
  if(ship.inv>0)ship.inv-=dt;
  if(flashT>0){flashT-=dt;if(flashT<=0)flashEl.style.opacity="0";}

  /* ship easing + bank */
  ship.x+=(ship.tx-ship.x)*Math.min(1,dt*9);
  ship.y+=(ship.ty-ship.y)*Math.min(1,dt*9);
  ship.roll+=(clamp((ship.tx-ship.x)*0.004,-0.42,0.42)-ship.roll)*Math.min(1,dt*6);

  /* starfield */
  var i,o;
  for(i=0;i<stars.length;i++){o=stars[i];o.z-=sp*0.9*dt;
    if(o.z<40){o.z=3600;o.x=rnd(-2600,2600);o.y=rnd(-1800,1800);}}
  for(i=0;i<dust.length;i++){o=dust[i];o.z-=sp*1.6*dt;
    if(o.z<40){o.z=2400;o.x=rnd(-1400,1400);o.y=rnd(-900,900);}}
  for(i=0;i<rocks.length;i++){o=rocks[i];o.z-=sp*o.sp*dt;
    if(o.z<40){o.z=3400;o.x=rnd(-1600,1600);o.y=rnd(-700,700);}}

  /* spawn */
  if(spawned<cfg.count){
    spawnT-=dt;
    if(spawnT<=0){spawnFoe();spawnT=rnd(0.34,0.92)*(1-Math.min(0.4,level*0.03));}
  }

  /* guns */
  shotT-=dt;
  if(shotT<=0 && warp<=0){
    bolts.push({x:ship.x-30,y:ship.y+8,z:70,vx:0,vy:0});
    bolts.push({x:ship.x+30,y:ship.y+8,z:70,vx:0,vy:0});
    shotT=0.15;
  }

  /* foes */
  for(i=foes.length-1;i>=0;i--){
    var f=foes[i];
    if(f.dead){foes.splice(i,1);continue;}
    var d=TYPE[f.t];
    f.z-=sp*d.spd*dt;
    f.ph+=dt*1.7;
    if(d.sway){f.x+=Math.sin(f.ph)*d.sway*46*dt;f.y+=Math.cos(f.ph*0.7)*d.sway*26*dt;}
    if(f.t==="mine"){f.x+=(ship.x-f.x)*0.28*dt;f.y+=(ship.y-f.y)*0.28*dt;}
    /* they shoot */
    if(d.shoot>0 && f.z<2100){
      f.fire-=dt*d.shoot*cfg.fire;
      if(f.fire<=0){
        f.fire=rnd(1.1,2.6);
        var ax=(ship.x-f.x),ay=(ship.y-f.y);
        flak.push({x:f.x,y:f.y,z:f.z,vx:ax*0.30,vy:ay*0.30});
      }
    }
    if(f.z<52){
      var near=Math.abs(f.x-ship.x)<f.r+34 && Math.abs(f.y-ship.y)<f.r+30;
      if(near) damage(f.t==="mine"?22:15);
      else {streak=0;mult=1;}
      pop(f.x,f.y,90,f.col,near?18:5);
      f.dead=true;
    }
  }

  /* boss */
  if(boss){
    boss.t+=dt;
    boss.z=520+Math.sin(boss.t*0.4)*180;
    boss.x=Math.sin(boss.t*0.55)*300;
    boss.y=-40+Math.cos(boss.t*0.8)*70;
    boss.ph-=dt;
    if(boss.ph<=0){
      boss.ph=rnd(0.35,0.8);
      for(var k=-2;k<=2;k++)
        flak.push({x:boss.x+k*40,y:boss.y+40,z:boss.z,
          vx:(ship.x-boss.x)*0.3+k*30,vy:(ship.y-boss.y)*0.3});
    }
  }

  /* our bolts */
  for(i=bolts.length-1;i>=0;i--){
    var b=bolts[i];b.z+=1900*dt;
    if(b.z>3200){bolts.splice(i,1);streak=0;mult=1;continue;}
    var hit=false;
    for(var j=0;j<foes.length;j++){
      var g=foes[j];if(g.dead)continue;
      if(Math.abs(b.z-g.z)<70 && Math.abs(b.x-g.x)<g.r+16 && Math.abs(b.y-g.y)<g.r+16){
        g.hp--;pop(g.x,g.y,g.z,g.col,4);
        if(g.hp<=0)killFoe(g);
        hit=true;break;
      }
    }
    if(hit){bolts.splice(i,1);continue;}
    if(boss && Math.abs(b.z-boss.z)<110 &&
       Math.abs(b.x-boss.x)<boss.r && Math.abs(b.y-boss.y)<boss.r*0.55){
      boss.hp--;score+=6*mult;pop(b.x,b.y,b.z,"#ff8a80",3);bolts.splice(i,1);
      if(boss.hp<=0){
        score+=4000;kills++;pop(boss.x,boss.y,boss.z,"#ff8a80",120);
        shake=1.4;boss=null;say("Nest destroyed","#c9a84c");
      }
    }
  }

  /* their flak */
  for(i=flak.length-1;i>=0;i--){
    var fl=flak[i];fl.z-=(sp*0.9+520)*dt;fl.x+=fl.vx*dt;fl.y+=fl.vy*dt;
    if(fl.z<44){
      if(Math.abs(fl.x-ship.x)<38 && Math.abs(fl.y-ship.y)<32) damage(9);
      flak.splice(i,1);
    }
  }

  /* debris */
  for(i=pops.length-1;i>=0;i--){
    var p=pops[i];
    p.x+=p.vx*dt;p.y+=p.vy*dt;p.z+=p.vz*dt-sp*dt;p.life-=dt*1.25;
    if(p.life<=0||p.z<20)pops.splice(i,1);
  }

  hud();
  if(spawned>=cfg.count && foes.length===0 && !boss && flashT<=0) clear();
}

function killFoe(g){
  g.dead=true;kills++;streak++;
  mult=Math.min(6,1+Math.floor(streak/6));
  var depth=1+Math.min(1.2,g.z/2200);
  score+=Math.round(TYPE[g.t].pts*mult*depth);
  pop(g.x,g.y,g.z,g.col,20);
}

function damage(n){
  if(ship.inv>0)return;
  hull-=n;streak=0;mult=1;shake=1;ship.inv=0.7;
  document.getElementById("hullF").style.width=Math.max(0,hull)+"%";
  if(hull<=0)over();
}

/* ---------- render ---------- */
function render(dt){
  ctx.save();
  if(shake>0)ctx.translate(rnd(-5,5)*shake,rnd(-5,5)*shake);

  ctx.fillStyle=cfg.sky;ctx.fillRect(-8,-8,W+16,H+16);
  drawBackdrop();

  /* stars */
  for(var i=0;i<stars.length;i++){
    var s=stars[i],p=proj(s.x,s.y,s.z);
    if(p.x<-40||p.x>W+40||p.y<-40||p.y>H+40)continue;
    var a=Math.min(1,s.b*(1-s.z/3600)+0.12), sz=Math.max(0.6,p.s*1.6);
    ctx.globalAlpha=a;ctx.fillStyle="#dfe8ff";
    if(warp>0){ctx.fillRect(p.x,p.y,sz,sz+warp*26*p.s*10);}
    else ctx.fillRect(p.x,p.y,sz,sz);
  }
  ctx.globalAlpha=1;

  /* dust streaks give the sense of speed */
  ctx.strokeStyle="rgba(180,205,255,.30)";ctx.lineWidth=1;
  for(i=0;i<dust.length;i++){
    var d=dust[i],a1=proj(d.x,d.y,d.z),a2=proj(d.x,d.y,d.z+120);
    if(a1.x<-30||a1.x>W+30)continue;
    ctx.beginPath();ctx.moveTo(a1.x,a1.y);ctx.lineTo(a2.x,a2.y);ctx.stroke();
  }

  /* asteroid chunks */
  for(i=0;i<rocks.length;i++){
    var r=rocks[i],rp=proj(r.x,r.y,r.z),rr=r.r*rp.s;
    if(rr<0.4||rp.x<-60||rp.x>W+60)continue;
    ctx.globalAlpha=Math.min(1,1.4-r.z/3400);
    ctx.fillStyle="#3b3f4d";
    ctx.beginPath();ctx.arc(rp.x,rp.y,rr,0,6.284);ctx.fill();
    ctx.fillStyle="#4b5060";
    ctx.beginPath();ctx.arc(rp.x-rr*0.3,rp.y-rr*0.3,rr*0.55,0,6.284);ctx.fill();
  }
  ctx.globalAlpha=1;

  /* everything with depth, far to near */
  var list=[];
  for(i=0;i<foes.length;i++)list.push({k:"f",o:foes[i],z:foes[i].z});
  if(boss)list.push({k:"B",o:boss,z:boss.z});
  for(i=0;i<pops.length;i++)list.push({k:"p",o:pops[i],z:pops[i].z});
  for(i=0;i<flak.length;i++)list.push({k:"x",o:flak[i],z:flak[i].z});
  for(i=0;i<bolts.length;i++)list.push({k:"b",o:bolts[i],z:bolts[i].z});
  list.sort(function(a,b){return b.z-a.z;});

  for(i=0;i<list.length;i++){
    var it=list[i],o=it.o,p=proj(o.x,o.y,o.z);
    if(o.z<30)continue;
    if(it.k==="f")drawFoe(o,p);
    else if(it.k==="B")drawBoss(o,p);
    else if(it.k==="p"){
      ctx.globalAlpha=Math.max(0,o.life);ctx.fillStyle=o.col;
      var ps=Math.max(1,4*p.s);ctx.fillRect(p.x,p.y,ps,ps);ctx.globalAlpha=1;
    }
    else if(it.k==="x"){
      var xs=Math.max(2,9*p.s);
      ctx.fillStyle="#ff8a80";
      ctx.beginPath();ctx.arc(p.x,p.y,xs,0,6.284);ctx.fill();
      ctx.globalAlpha=.35;ctx.beginPath();ctx.arc(p.x,p.y,xs*2.1,0,6.284);ctx.fill();
      ctx.globalAlpha=1;
    }
    else{
      var q=proj(o.x,o.y,o.z-150);
      ctx.strokeStyle="#9ff3c8";ctx.lineWidth=Math.max(1.2,3*p.s);ctx.lineCap="round";
      ctx.beginPath();ctx.moveTo(q.x,q.y);ctx.lineTo(p.x,p.y);ctx.stroke();
    }
  }

  drawShip();
  ctx.restore();
}

function drawBackdrop(){
  var t=performance.now()/1000;
  var px=CX-ship.x*0.14, py=CY-ship.y*0.10;
  var k=cfg.planet;

  if(k==="void"){
    var neb=ctx.createRadialGradient(px+W*0.2,py-H*0.1,10,px+W*0.2,py-H*0.1,W*0.7);
    neb.addColorStop(0,"rgba(60,40,90,.30)");neb.addColorStop(1,"rgba(5,7,15,0)");
    ctx.fillStyle=neb;ctx.fillRect(0,0,W,H);
    return;
  }

  var R=Math.min(W,H)*(k==="saturn"?0.42:0.34);
  var cxp=px+W*0.24, cyp=py-H*0.16;

  var body={saturn:["#e6d3a3","#9c8352"],rust:["#c97b4a","#5d2f1c"],
    ice:["#9ad4ff","#2b5b86"],moon:["#c9ccd6","#4a4e5c"],
    jade:["#8fe0b4","#27604a"],ember:["#ff9a7a","#6d2222"]}[k]||["#c9ccd6","#4a4e5c"];

  if(k==="saturn"){ ctx.save();ctx.translate(cxp,cyp);ctx.rotate(-0.42);
    ctx.strokeStyle="rgba(214,193,150,.55)";ctx.lineWidth=R*0.16;
    ctx.beginPath();ctx.ellipse(0,0,R*1.75,R*0.42,0,Math.PI,Math.PI*2);ctx.stroke();
    ctx.restore(); }

  var g=ctx.createRadialGradient(cxp-R*0.35,cyp-R*0.35,R*0.1,cxp,cyp,R);
  g.addColorStop(0,body[0]);g.addColorStop(1,body[1]);
  ctx.fillStyle=g;ctx.beginPath();ctx.arc(cxp,cyp,R,0,6.284);ctx.fill();

  if(k==="moon"){
    ctx.fillStyle="rgba(0,0,0,.16)";
    for(var i=0;i<7;i++){
      var a=i*1.4+1, rr=R*(0.08+((i*37)%11)/60);
      ctx.beginPath();ctx.arc(cxp+Math.cos(a)*R*0.5,cyp+Math.sin(a)*R*0.45,rr,0,6.284);ctx.fill();
    }
  }
  if(k==="saturn"||k==="jade"||k==="rust"){
    ctx.globalAlpha=.18;ctx.fillStyle="rgba(0,0,0,.6)";
    for(var b=0;b<4;b++){
      ctx.beginPath();
      ctx.ellipse(cxp,cyp-R*0.5+b*R*0.34+Math.sin(t*0.2+b)*3,R*0.92,R*0.075,0,0,6.284);
      ctx.fill();
    }
    ctx.globalAlpha=1;
  }
  ctx.fillStyle="rgba(5,7,15,.55)";
  ctx.beginPath();ctx.arc(cxp+R*0.30,cyp+R*0.12,R,0,6.284);ctx.fill();

  if(k==="saturn"){ ctx.save();ctx.translate(cxp,cyp);ctx.rotate(-0.42);
    ctx.strokeStyle="rgba(232,214,175,.75)";ctx.lineWidth=R*0.16;
    ctx.beginPath();ctx.ellipse(0,0,R*1.75,R*0.42,0,0,Math.PI);ctx.stroke();
    ctx.strokeStyle="rgba(232,214,175,.30)";ctx.lineWidth=R*0.05;
    ctx.beginPath();ctx.ellipse(0,0,R*2.05,R*0.50,0,0,Math.PI);ctx.stroke();
    ctx.restore(); }
}

function drawFoe(f,p){
  var r=f.r*p.s;
  if(r<0.6)return;
  ctx.globalAlpha=Math.min(1,(3000-f.z)/700+0.25);
  if(f.t==="mine"){
    ctx.strokeStyle=f.col;ctx.lineWidth=Math.max(1,r*0.16);
    for(var i=0;i<8;i++){var a=i*0.785+f.ph;
      ctx.beginPath();ctx.moveTo(p.x+Math.cos(a)*r*0.6,p.y+Math.sin(a)*r*0.6);
      ctx.lineTo(p.x+Math.cos(a)*r*1.25,p.y+Math.sin(a)*r*1.25);ctx.stroke();}
    ctx.fillStyle=f.col;ctx.beginPath();ctx.arc(p.x,p.y,r*0.6,0,6.284);ctx.fill();
  }else{
    ctx.fillStyle=f.col;
    ctx.beginPath();
    ctx.moveTo(p.x,p.y+r*0.9);
    ctx.lineTo(p.x+r*1.15,p.y-r*0.5);
    ctx.lineTo(p.x+r*0.4,p.y-r*0.15);
    ctx.lineTo(p.x-r*0.4,p.y-r*0.15);
    ctx.lineTo(p.x-r*1.15,p.y-r*0.5);
    ctx.closePath();ctx.fill();
    ctx.fillStyle="rgba(5,7,15,.75)";
    ctx.beginPath();ctx.arc(p.x,p.y+r*0.05,r*0.3,0,6.284);ctx.fill();
    if(f.t==="hulk"){ctx.strokeStyle="rgba(5,7,15,.6)";ctx.lineWidth=Math.max(1,r*0.12);
      ctx.beginPath();ctx.moveTo(p.x-r,p.y-r*0.42);ctx.lineTo(p.x+r,p.y-r*0.42);ctx.stroke();}
    ctx.fillStyle="rgba(255,255,255,.65)";
    ctx.fillRect(p.x-r*0.12,p.y-r*0.62,r*0.24,r*0.2);
  }
  ctx.globalAlpha=1;
}

function drawBoss(b,p){
  var r=b.r*p.s;
  ctx.fillStyle="#7a2230";
  ctx.beginPath();ctx.ellipse(p.x,p.y,r,r*0.44,0,0,6.284);ctx.fill();
  ctx.fillStyle="#ff8a80";
  ctx.beginPath();ctx.ellipse(p.x,p.y-r*0.12,r*0.62,r*0.30,0,0,6.284);ctx.fill();
  ctx.fillStyle="#05070f";
  for(var i=-2;i<=2;i++)ctx.fillRect(p.x+i*r*0.24-r*0.05,p.y+r*0.12,r*0.1,r*0.12);
  var bw=Math.min(W*0.6,r*1.6);
  ctx.fillStyle="rgba(255,255,255,.18)";ctx.fillRect(p.x-bw/2,p.y-r*0.62,bw,5);
  ctx.fillStyle="#ff8a80";ctx.fillRect(p.x-bw/2,p.y-r*0.62,bw*(b.hp/b.max),5);
}

function drawShip(){
  var sx=CX+ship.x*0.55, sy=H-72+ship.y*0.18;
  if(ship.inv>0 && ((ship.inv*14)|0)%2)return;
  ctx.save();ctx.translate(sx,sy);ctx.rotate(ship.roll);
  ctx.fillStyle="rgba(245,194,107,.9)";
  ctx.fillRect(-13,16,7,10+Math.random()*13);
  ctx.fillRect(6,16,7,10+Math.random()*13);
  ctx.fillStyle="#c9a84c";
  ctx.beginPath();
  ctx.moveTo(0,-26);ctx.lineTo(15,6);ctx.lineTo(40,18);ctx.lineTo(34,24);
  ctx.lineTo(9,20);ctx.lineTo(-9,20);ctx.lineTo(-34,24);ctx.lineTo(-40,18);
  ctx.lineTo(-15,6);ctx.closePath();ctx.fill();
  ctx.fillStyle="#0d1424";
  ctx.beginPath();ctx.moveTo(0,-16);ctx.lineTo(7,4);ctx.lineTo(-7,4);ctx.closePath();ctx.fill();
  ctx.fillStyle="#7fe3b0";ctx.fillRect(-2.5,-10,5,9);
  ctx.restore();
}

/* ---------- hud ---------- */
function hud(){
  document.getElementById("hScore").textContent=score;
  document.getElementById("hLevel").textContent=level;
  document.getElementById("combo").textContent="x"+mult;
}

/* ---------- flow ---------- */
function show(id){
  ["scTitle","scPick","scNext","scOver"].forEach(function(s){
    document.getElementById(s).classList.toggle("on",s===id);});
  paused=!!id;
  document.getElementById("hint").style.opacity=id?"0":"1";
}
function startLevel(n){
  resize();build(n);hud();show(null);
  document.getElementById("hullF").style.width=hull+"%";
  if(!running){running=true;last=performance.now();requestAnimationFrame(step);}
  say(cfg.name,"#c9a84c");
}
function startRun(n){score=0;kills=0;hull=100;streak=0;mult=1;startLevel(n);}

function clear(){
  paused=true;
  if(level>(prog.lv||0))prog.lv=level;
  if(score>(prog.best||0))prog.best=score;
  save();
  hull=Math.min(100,hull+18);
  document.getElementById("hullF").style.width=hull+"%";
  document.getElementById("nScore").textContent=score;
  document.getElementById("nKills").textContent=kills;
  if(level>=MAXLV){
    document.getElementById("nextTitle").textContent="You made it back";
    document.getElementById("nextNote").textContent="All ten sectors run. Best score "+prog.best+".";
    document.getElementById("bNext").textContent="Back to start";
  }else{
    document.getElementById("nextTitle").textContent=cfg.name+" clear";
    document.getElementById("nextNote").textContent=
      level===9?"Sector 10 is the Nest. Something big is waiting.":
      "Hull patched. Next sector runs faster.";
    document.getElementById("bNext").textContent="Sector "+(level+1);
  }
  show("scNext");
}
function over(){
  paused=true;running=false;
  if(score>(prog.best||0)){prog.best=score;save();}
  document.getElementById("oScore").textContent=score;
  document.getElementById("oLevel").textContent=level;
  document.getElementById("oKills").textContent=kills;
  document.getElementById("overNote").textContent="Best score so far "+(prog.best||0)+".";
  show("scOver");
}

/* ---------- input ---------- */
var drag=false,ox=0,oy=0,sx0=0,sy0=0;
function pt(e){var t=e.touches?e.touches[0]:e;return {x:t.clientX,y:t.clientY};}
cv.addEventListener("touchstart",function(e){
  drag=true;var p=pt(e);ox=p.x;oy=p.y;sx0=ship.tx;sy0=ship.ty;},{passive:false});
cv.addEventListener("touchmove",function(e){
  if(!drag||paused)return;var p=pt(e);
  ship.tx=clamp(sx0+(p.x-ox)*1.7,-430,430);
  ship.ty=clamp(sy0+(p.y-oy)*1.4,-260,240);
  if(e.cancelable)e.preventDefault();},{passive:false});
cv.addEventListener("touchend",function(){drag=false;});
cv.addEventListener("mousedown",function(e){drag=true;var p=pt(e);ox=p.x;oy=p.y;
  sx0=ship.tx;sy0=ship.ty;});
window.addEventListener("mousemove",function(e){
  if(!drag||paused)return;var p=pt(e);
  ship.tx=clamp(sx0+(p.x-ox)*1.7,-430,430);
  ship.ty=clamp(sy0+(p.y-oy)*1.4,-260,240);});
window.addEventListener("mouseup",function(){drag=false;});
window.addEventListener("keydown",function(e){
  if(e.key==="ArrowLeft")ship.tx=clamp(ship.tx-46,-430,430);
  if(e.key==="ArrowRight")ship.tx=clamp(ship.tx+46,-430,430);
  if(e.key==="ArrowUp")ship.ty=clamp(ship.ty-40,-260,240);
  if(e.key==="ArrowDown")ship.ty=clamp(ship.ty+40,-260,240);
});

/* ---------- menus ---------- */
document.getElementById("bStart").onclick=function(){startRun(1);};
document.getElementById("bPick").onclick=function(){grid();show("scPick");};
document.getElementById("bBack").onclick=function(){show("scTitle");};
document.getElementById("bQuit").onclick=function(){running=false;show("scTitle");};
document.getElementById("bHome").onclick=function(){show("scTitle");};
document.getElementById("bRetry").onclick=function(){startRun(level);};
document.getElementById("bNext").onclick=function(){
  if(level>=MAXLV){running=false;show("scTitle");}else startLevel(level+1);};

function grid(){
  var g=document.getElementById("lv"),best=prog.lv||0,s="";
  document.getElementById("pickSub").textContent=best+" of "+MAXLV+" cleared";
  for(var i=1;i<=MAXLV;i++){
    var c=i<=best?"done":(i<=best+1?"":"lock");
    s+='<button class="'+c+'" data-n="'+i+'">'+i+'</button>';
  }
  g.innerHTML=s;
  Array.prototype.forEach.call(g.querySelectorAll("button"),function(b){
    if(b.classList.contains("lock"))return;
    b.onclick=function(){startRun(parseInt(b.dataset.n,10));};});
}

document.getElementById("bestLine").textContent=
  prog.best?"Best score "+prog.best+" — "+(prog.lv||0)+" of 10 sectors":"";
resize();cfg=SECTORS[0];fieldInit();hud();render(0);
})();
</script>
</body>
</html>

```


## `aitxt-popup-live.html`

165 lines, 7279 bytes

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ai.txt Live Compliance Widget — Preview</title>
<style>
  body{margin:0;background:#e8e6df;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;min-height:100vh;}
  .demo-note{position:fixed;top:16px;left:16px;right:16px;background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;font-size:13px;color:#555;max-width:560px;margin:0 auto;text-align:center;z-index:2;}
</style>
</head>
<body>
<div class="demo-note">This page has no ai.txt, so the badge will honestly say "not found." Click it to see the real check running live.</div>

<!-- ============================================================
     THE DELIVERABLE: one script tag. Paste into any site.
     On load, it actually fetches /ai.txt from that same domain
     and reports the true result — nothing hardcoded, nothing faked.
============================================================= -->
<script>
(function(){
  var CSS = `
    #aitxt-badge{
      position:fixed;bottom:20px;right:20px;z-index:999998;
      background:#0a0f1e;color:#8b93ac;border:1px solid #232c48;
      font-family:'SF Mono','JetBrains Mono',Consolas,monospace;
      font-size:12px;padding:10px 16px;border-radius:999px;cursor:pointer;
      box-shadow:0 4px 18px rgba(0,0,0,.25);display:flex;align-items:center;gap:8px;
      transition:transform .15s ease;
    }
    #aitxt-badge:hover{transform:translateY(-2px);}
    #aitxt-badge .dot{width:7px;height:7px;border-radius:50%;background:#8b93ac;flex-shrink:0;transition:background .2s ease;}
    #aitxt-badge .dot.ok{background:#7fe3b0;}
    #aitxt-badge .dot.warn{background:#ff8a80;}
    #aitxt-badge .dot.checking{background:#c9a84c;animation:aitxt-pulse 1s ease-in-out infinite;}
    @keyframes aitxt-pulse{50%{opacity:.3;}}
    #aitxt-overlay{
      position:fixed;inset:0;background:rgba(10,15,30,.6);z-index:999999;
      display:none;align-items:center;justify-content:center;padding:20px;
    }
    #aitxt-overlay.open{display:flex;}
    #aitxt-modal{
      background:#10182e;border:1px solid #232c48;border-radius:12px;
      max-width:420px;width:100%;color:#e7ebf5;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;
      overflow:hidden;
    }
    #aitxt-modal .aitxt-head{padding:20px 22px 0;}
    #aitxt-modal .aitxt-eyebrow{
      font-family:'SF Mono',Consolas,monospace;font-size:11px;letter-spacing:.1em;
      text-transform:uppercase;color:#c9a84c;margin-bottom:10px;
    }
    #aitxt-modal h3{margin:0 0 8px;font-size:19px;line-height:1.3;}
    #aitxt-modal p{margin:0 0 18px;font-size:13.5px;line-height:1.55;color:#8b93ac;}
    #aitxt-modal .aitxt-body{padding:0 22px 22px;}
    #aitxt-modal .aitxt-status{
      display:flex;align-items:center;gap:8px;padding:12px 14px;
      background:#161f38;border:1px solid #232c48;border-radius:8px;margin-bottom:16px;
      font-family:'SF Mono',Consolas,monospace;font-size:12px;
    }
    #aitxt-modal .aitxt-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
    #aitxt-modal .aitxt-dot.ok{background:#7fe3b0;}
    #aitxt-modal .aitxt-dot.warn{background:#ff8a80;}
    #aitxt-modal .aitxt-dot.checking{background:#c9a84c;animation:aitxt-pulse 1s ease-in-out infinite;}
    #aitxt-modal .aitxt-status.ok span.label{color:#7fe3b0;}
    #aitxt-modal .aitxt-status.warn span.label{color:#ff8a80;}
    #aitxt-modal .aitxt-status.checking span.label{color:#c9a84c;}
    #aitxt-modal a.aitxt-cta{
      display:block;text-align:center;background:#c9a84c;color:#0a0f1e;
      font-weight:600;font-size:14px;padding:11px;border-radius:7px;
      text-decoration:none;margin-bottom:10px;
    }
    #aitxt-modal button.aitxt-close{
      display:block;width:100%;background:transparent;border:1px solid #232c48;
      color:#8b93ac;font-size:13px;padding:10px;border-radius:7px;cursor:pointer;
    }
  `;
  var style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  var badge = document.createElement('div');
  badge.id = 'aitxt-badge';
  badge.innerHTML = '<span class="dot checking"></span><span class="label">Checking AI governance…</span>';
  document.body.appendChild(badge);

  var overlay = document.createElement('div');
  overlay.id = 'aitxt-overlay';
  overlay.innerHTML = `
    <div id="aitxt-modal">
      <div class="aitxt-head">
        <div class="aitxt-eyebrow">ai.txt · sebbi.pro</div>
        <h3>AI governance declaration</h3>
        <p>ai.txt is a plain-text file — like robots.txt — that states how this site's AI systems are governed. This check looked for it at the domain root, live, just now.</p>
      </div>
      <div class="aitxt-body">
        <div class="aitxt-status checking" id="aitxt-modal-status">
          <span class="aitxt-dot checking"></span>
          <span class="label">Checking…</span>
        </div>
        <a class="aitxt-cta" href="https://sebbi.pro" target="_blank" id="aitxt-cta">Generate ai.txt — free</a>
        <button class="aitxt-close">Close</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  var badgeDot = badge.querySelector('.dot');
  var badgeLabel = badge.querySelector('.label');
  var modalStatus = overlay.querySelector('#aitxt-modal-status');
  var modalDot = modalStatus.querySelector('.aitxt-dot');
  var modalLabel = modalStatus.querySelector('.label');
  var cta = overlay.querySelector('#aitxt-cta');

  function setState(state, text, modalText){
    badgeDot.className = 'dot ' + state;
    badgeLabel.textContent = text;
    modalStatus.className = 'aitxt-status ' + state;
    modalDot.className = 'aitxt-dot ' + state;
    modalLabel.textContent = modalText;
    if(state === 'ok'){
      cta.textContent = 'View declaration';
    } else {
      cta.textContent = 'Generate ai.txt — free';
    }
  }

  // The real check — looks for ai.txt on this exact page's own domain.
  // Checks the standard /.well-known/ai.txt location first, then falls
  // back to /ai.txt at root. Same-origin, no backend needed, and it
  // can't be faked by hardcoding a result: it either finds the file or
  // it doesn't.
  function checkPath(path){
    return fetch(path, {method:'GET', cache:'no-store'})
      .then(function(res){ return res.ok ? path : null; })
      .catch(function(){ return null; });
  }

  Promise.all([
    checkPath('/.well-known/ai.txt'),
    checkPath('/ai.txt')
  ]).then(function(results){
    var foundAt = results.find(function(p){ return p !== null; });
    if(foundAt){
      setState('ok', 'AI governance declared', 'ai.txt found at ' + foundAt);
    } else {
      setState('warn', 'No ai.txt found', 'No ai.txt file found at this domain');
    }
  });

  badge.addEventListener('click', function(){ overlay.classList.add('open'); });
  overlay.addEventListener('click', function(e){
    if(e.target === overlay) overlay.classList.remove('open');
  });
  overlay.querySelector('.aitxt-close').addEventListener('click', function(){
    overlay.classList.remove('open');
  });
})();
</script>
<!-- ============================================================
     END OF SNIPPET
============================================================= -->

</body>
</html>

```
