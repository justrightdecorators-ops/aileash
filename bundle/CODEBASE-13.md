# Codebase — part 13 of 27

Contains:
- `modules/verifier.py`
- `modules/wallet.py`
- `modules/warmup.py`


## `modules/verifier.py`

717 lines, 26299 bytes

```python
#!/usr/bin/env python3
"""
modules/verifier.py  -  hand the verifier out at a URL

WHY THIS EXISTS
---------------
A proof that can only be checked by the party who issued it is not a proof.
So the proof bundles at /x/continuity/proof are useless unless somebody can
easily get hold of something that checks them, and telling people to clone a
repository is a gate.

This serves the standalone verifier as a plain file:

    curl -sO https://sebbi.pro/verify-authority.py
    curl -s "https://sebbi.pro/x/continuity/proof?evaluation=e_..." \\
        | python3 verify-authority.py -

The script it hands out has no dependencies and makes no network calls. It
checks the Ed25519 signature, recomputes every digest, re-runs the whole
derivation from the published rules, and reaches its own verdict - then says
so if that verdict disagrees with ours.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not phone home, and this module records nothing about who downloaded
it. A verification tool that reports back to the party being verified is not
a verification tool.

    GET /verify-authority.py   the script
    GET /x/verifier/status     what is installed, and the script's digest
"""

import hashlib
import sys

VERSION = "1.1"

PUBLIC = {("GET", "status")}

# Deliberately NOT "/verify" - that is the sealed-post verification page and
# this module would silently hijack it, handing a visitor a Python download
# where they expected a page. A route grab is a bug even when the code works.
FILE_PATHS = ("/verify-authority.py", "/verify_authority.py")

_patched = [False]


SCRIPT = r'''#!/usr/bin/env python3
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
    body = dict(bundle)
    body.pop("signature", None)
    body.pop("verify_with", None)
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
'''


def _digest():
    return hashlib.sha256(SCRIPT.encode("utf-8")).hexdigest()


def _srv():
    m = sys.modules.get("__main__")
    if m is not None and hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_verifier_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"

        if p in FILE_PATHS:
            body = SCRIPT.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition",
                                 'attachment; filename="verify-authority.py"')
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        return original(self)

    H.do_GET = do_GET
    H._verifier_patched = True
    _patched[0] = True
    print("VERIFIER: /verify-authority.py installed", flush=True)
    return "installed"


def handle(method, action, data, api_key, ctx):
    s = _srv()
    if s is None:
        return {"error": "server_not_found"}, 500

    state = "already installed" if _patched[0] else None
    if not _patched[0]:
        try:
            state = _install(s)
        except Exception as exc:
            print("VERIFIER: patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    action = (action or "").strip("/").lower()

    if method == "GET" and action in ("", "status"):
        return {
            "installed": bool(_patched[0]),
            "install_result": state,
            "module_version": VERSION,
            "serving": list(FILE_PATHS),
            "script_bytes": len(SCRIPT),
            "script_sha256": _digest(),
            "how_to_use": [
                "curl -sO https://sebbi.pro/verify-authority.py",
                "curl -s 'https://sebbi.pro/x/continuity/proof?evaluation=<id>' "
                "| python3 verify-authority.py -",
            ],
            "dependencies": "none - Python standard library only",
            "network": "the script makes no network calls and reports nothing back. "
                       "A verification tool that phones home to the party being "
                       "verified is not a verification tool.",
            "note": "Check script_sha256 against the file you downloaded. And read it "
                    "before you run it, as you would with anything else handed to you "
                    "by the party you are checking.",
        }, 200

    return {"error": "unknown_action", "action": action, "GET": ["status"]}, 404

```


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
