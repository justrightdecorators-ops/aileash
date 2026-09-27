"""
modules/noexec.py  v1.0.1
The NO-EXEC blind bundle: six real objects from the live system, each one
authentic, each one attached to a claim it may not support.

Arm after each deploy:  https://sebbi.pro/x/noexec/status

    GET /x/noexec/build              mint the six objects on the live chain,
                                     pack them into one bundle, seal the
                                     bundle fingerprint and a salted
                                     commitment to the answer key, and hand
                                     back the links (one build per 10 minutes)
    GET /x/noexec/bundle?id=         the bundle exactly as sent: claims and
                                     objects only, no verdicts, no hints
    GET /x/noexec/reveal?id=&secret= the answer key plus its salt, so anyone
                                     can recompute the sealed commitment
    GET /x/noexec/status             module status

How the six are made (nothing faked, nothing edited afterwards):
  1  a passport minted, then redeemed once, redemption sealed
  2  a passport minted, then its grant revoked, revocation sealed
  3  a passport minted for one site, never presented anywhere
  4  a signed authority proof bundle for an ALLOW evaluation whose grant
     window is fifteen minutes long
  5  the sealed Temporal Standing Test evidence package, run r_72d2d93a5c2a4988
  6  the latest self-proving archive file and the sealed custody count

Built on continuity.py (1.6.0+) and passport.py. Neither is changed.
"""

import hashlib
import importlib
import importlib.util
import json
import os
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.0.1"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "build"), ("GET", "bundle"), ("GET", "reveal")}

SITE = "https://sebbi.pro"
KEY = "noexec-blind-bundle"
GAP = 600
CAP = "noexec.pay"
TAGS = ["noexec"]
AUD = "checkout.sebbi.pro"
AUD_OTHER = "bookings.sebbi.pro"
PARAMS = {"amount": 20}
TST_RUN = "r_72d2d93a5c2a4988"
TST_REVIEW = "https://studio.moralclarity.ai/temporal-standing-test"

_ready = False
_last = [0.0]


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha(obj):
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _block_url(n):
    return SITE + "/x/walk/block?index=%s" % n if n is not None else None


def _load(name, must_have):
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith(os.sep + name + ".py") and all(hasattr(m, a) for a in must_have):
            return m
    pkg = __package__ or ""
    try:
        m = importlib.import_module(pkg + "." + name if pkg else name)
        if all(hasattr(m, a) for a in must_have):
            return m
    except Exception:
        pass
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name + ".py")
    spec = importlib.util.spec_from_file_location("noexec_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _call(name, action, data, ctx):
    """Ask another live module for one of its public answers. Never raises."""
    try:
        m = _load(name, ("handle",))
        out = m.handle("GET", action, data, None, ctx)
        body = out[0] if isinstance(out, tuple) else out
        return body if isinstance(body, dict) else {"raw": str(body)[:4000]}
    except Exception as e:
        return {"unavailable": str(e)[:200]}


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS noexec_bundle(id TEXT PRIMARY KEY,created REAL,"
                  "bundle TEXT,bundle_sha256 TEXT,answer_key TEXT,key_commitment TEXT,"
                  "secret_digest TEXT,audit_hash TEXT,block_index INTEGER)")
        c.commit()
    _ready = True


def _seal(ctx, kind, extra):
    ev = {"user_id": "noexec:" + kind[:20], "action": kind, "amount": 0, "country": "UK",
          "device_id": "noexec", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "noexec_version": VERSION}
    res.update(extra)
    out = ctx["seal"](ev, res, time.time(), KEY)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


def _grant(C, ctx, gid, subject, now):
    g = {"id": gid, "issuer": "justin-dobson", "issuer_kind": "human", "subject": subject,
         "scope": [CAP], "constraints": {"max_amount": 50},
         "purpose": "NO-EXEC blind bundle for independent review", "purpose_tags": TAGS,
         "not_after": now + 900}
    r, s = C._issue(ctx, KEY, g)
    if s != 200:
        raise RuntimeError("grant %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _mint(P, C, ctx, gid, audience):
    r, s = P._mint(ctx, C, KEY, {"grant": gid, "action": CAP, "params": PARAMS,
                                 "purpose_tag": TAGS[0], "audience": audience})
    if s != 200 or not r.get("issued"):
        raise RuntimeError("passport for %s not issued: %s" % (gid, _canon(r)[:300]))
    return r


def _passport_sources(token, gid, issued_block):
    return {"live_check": SITE + "/x/passport/verify?token=" + token,
            "token_format": SITE + "/x/passport/spec",
            "public_key": SITE + "/x/continuity/pubkey",
            "grant_lineage": SITE + "/x/continuity/trace?grant=" + gid,
            "issued_in_block": _block_url(issued_block)}


def _build(ctx):
    now = time.time()
    if now - _last[0] < GAP:
        return {"error": "too_soon", "retry_after_seconds": int(GAP - (now - _last[0]))}, 429
    _last[0] = now
    C = _load("continuity", ("_issue", "_evaluate", "_revoke", "_proof", "_confirm"))
    P = _load("passport", ("_mint", "_redeem", "_check"))
    C._setup(ctx)
    P._setup(ctx)

    tag = uuid.uuid4().hex[:10]
    agent = "agent-" + tag
    cases, key = [], []

    # 1 - the spent passport
    g1 = "nx_%s_1" % tag
    _grant(C, ctx, g1, agent, now)
    p1 = _mint(P, C, ctx, g1, AUD)
    r1, _s = P._redeem(ctx, C, {"token": p1["passport"], "audience": AUD, "params": PARAMS})
    if not r1.get("redeemed"):
        raise RuntimeError("case 1 redemption did not bind: %s" % _canon(r1)[:300])
    cases.append({"case": 1,
                  "claim": "This agent is authorised to perform this action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p1["passport"]},
                  "sources": _passport_sources(p1["passport"], g1, p1.get("block_index"))})
    key.append({"case": 1, "verdict": "NOT PROVEN",
                "what_it_proves": "Authorised once, for %s of %s at %s." % (CAP, _canon(PARAMS), AUD),
                "why_not": "Already redeemed; the redemption is sealed in block %s. Nothing "
                           "authorises a further execution." % r1.get("block_index"),
                "evidence": [_block_url(r1.get("block_index"))]})

    # 2 - the revoked passport
    g2 = "nx_%s_2" % tag
    _grant(C, ctx, g2, agent, now)
    p2 = _mint(P, C, ctx, g2, AUD)
    rv, _s = C._revoke(ctx, KEY, {"grant": g2, "reason": "human withdrew the authority"})
    cases.append({"case": 2,
                  "claim": "This agent was authorised at the moment of action.",
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p2["passport"]},
                  "sources": _passport_sources(p2["passport"], g2, p2.get("block_index"))})
    key.append({"case": 2, "verdict": "NOT PROVEN",
                "what_it_proves": "The signature is genuine and the passport was in date: an "
                                  "offline verifier says VALID.",
                "why_not": "The grant behind it was revoked (block %s) after issue. Standing is "
                           "lost, so no moment of action after that is authorised. Signature "
                           "validity is not standing." % rv.get("block_index"),
                "evidence": [_block_url(rv.get("block_index")),
                             SITE + "/x/continuity/trace?grant=" + g2]})

    # 3 - the misdirected passport (never presented anywhere, so still unspent)
    g3 = "nx_%s_3" % tag
    _grant(C, ctx, g3, agent, now)
    p3 = _mint(P, C, ctx, g3, AUD_OTHER)
    cases.append({"case": 3,
                  "claim": "This agent is authorised to act at %s." % AUD,
                  "presented_at": AUD, "action": CAP, "params": PARAMS,
                  "object": {"passport": p3["passport"]},
                  "sources": _passport_sources(p3["passport"], g3, p3.get("block_index"))})
    key.append({"case": 3, "verdict": "NOT PROVEN",
                "what_it_proves": "Genuine, unspent and unrevoked authority at %s." % AUD_OTHER,
                "why_not": "The passport's audience is %s. It says nothing about %s."
                           % (AUD_OTHER, AUD),
                "evidence": [SITE + "/x/passport/spec"]})

    # 4 - the signed proof of a past ALLOW
    g4 = "nx_%s_4" % tag
    gr4 = _grant(C, ctx, g4, agent, now)
    ev, s = C._evaluate(ctx, KEY, {"grant": g4, "action": CAP, "params": PARAMS,
                                   "purpose_tag": TAGS[0]})
    if s != 200 or ev.get("verdict") != "ALLOW":
        raise RuntimeError("case 4 evaluation was not ALLOW: %s" % _canon(ev)[:300])
    proof, s = C._proof(ctx, {"evaluation": ev["evaluation"]})
    if s != 200:
        raise RuntimeError("case 4 proof not produced: %s" % _canon(proof)[:300])
    cases.append({"case": 4,
                  "claim": "This agent holds this authority.",
                  "object": {"authority_proof": proof},
                  "sources": {"proof": SITE + "/x/continuity/proof?evaluation=" + ev["evaluation"],
                              "public_key": SITE + "/x/continuity/pubkey",
                              "derivation_rules": SITE + "/x/continuity/spec",
                              "grant_lineage": SITE + "/x/continuity/trace?grant=" + g4}})
    key.append({"case": 4, "verdict": "NOT PROVEN",
                "what_it_proves": "Authority stood, and the ALLOW re-derives from the lineage, at "
                                  "%s." % ev.get("evaluated_at", _iso(now)),
                "why_not": "A proof of an instant says nothing about now. The grant's window "
                           "closes at %s; any present-tense claim needs a live standing check."
                           % gr4.get("not_after"),
                "evidence": [SITE + "/x/continuity/trace?grant=" + g4]})

    # 5 - the real test, the narrower finding
    tst = _call("standing", "evidence", {"run": TST_RUN}, ctx)
    cases.append({"case": 5,
                  "claim": "sebbi.pro passed the Temporal Standing Test.",
                  "object": {"evidence_package": tst},
                  "sources": {"evidence": SITE + "/x/standing/evidence?run=" + TST_RUN,
                              "freeze_sealed_in": _block_url(2387),
                              "run_sealed_in": _block_url(2398),
                              "test_definition": TST_REVIEW}})
    key.append({"case": 5, "verdict": "NOT PROVEN",
                "what_it_proves": "A pre-registered run, freeze sealed before execution (block "
                                  "2387 before 2398), both branches recorded as observed.",
                "why_not": "The independent reviewer's finding is narrower than the package's "
                           "own 'PASS': revocation-aware authorisation and execution binding "
                           "ESTABLISHED; temporal standing on external facts (a still-valid "
                           "grant defeated by a change in an authoritative external fact) NOT "
                           "YET ESTABLISHED. The object is authentic; its summary overstates "
                           "what it supports.",
                "evidence": [SITE + "/x/standing/evidence?run=" + TST_RUN, TST_REVIEW]})

    # 6 - the archive with no custodians
    man = _call("archive", "manifest", {}, ctx)
    files = man.get("files") if isinstance(man, dict) else None
    latest = files[0] if isinstance(files, list) and files else man
    cus = _call("custody", "status", {}, ctx)
    cases.append({"case": 6,
                  "claim": "sebbi.pro's record is held independently.",
                  "object": {"archive_file": latest, "custody": cus},
                  "sources": {"archive_manifest": SITE + "/x/archive/manifest",
                              "archive_file": (latest or {}).get("file") if isinstance(latest, dict) else None,
                              "sealed_in": (latest or {}).get("check_block") if isinstance(latest, dict) else None,
                              "custody_count": SITE + "/x/custody/status"}})
    key.append({"case": 6, "verdict": "NOT PROVEN",
                "what_it_proves": "Integrity: the file is content-addressed, sealed in the chain, "
                                  "and its embedded verifier passes.",
                "why_not": "Independence: the sealed custody count of holders other than "
                           "sebbi.pro is %s." % _custody_count(cus),
                "evidence": [SITE + "/x/custody/status"]})

    for c in cases:
        c["object_sha256"] = _sha(c["object"])

    bid = "nx_" + tag
    captured = _iso(time.time())
    bundle = {
        "bundle": bid,
        "format": "noexec-blind-bundle/1",
        "issuer": "sebbi.pro",
        "captured_at": captured,
        "instructions": "Six objects taken from the live system. Each is presented with the "
                        "claim being made with it and nothing else. Fetch every source "
                        "yourself rather than trusting this copy; each object carries the "
                        "SHA-256 of its canonical JSON (keys sorted, separators ',' ':').",
        "format_notes": {
            "passport": "sbp1.<base64url body>.<base64url Ed25519 signature>; the signature "
                        "is over 'AILEASH-PASSPORT-v1:' || body bytes. Passports carry a "
                        "5-minute validity window (exp).",
            "chain_blocks": SITE + "/x/walk/block?index=<n>",
        },
        "cases": cases,
    }
    bundle_sha = _sha(bundle)

    salt = secrets.token_hex(32)
    answer = {"bundle": bid, "bundle_sha256": bundle_sha, "salt": salt, "answers": key}
    commitment = _sha(answer)
    secret = secrets.token_urlsafe(18)
    audit_hash, block = _seal(ctx, "noexec_bundle_committed",
                              {"bundle": bid, "bundle_sha256": bundle_sha,
                               "answer_key_commitment": commitment,
                               "detail": "bundle=%s;sha256=%s;key_commitment=%s"
                                         % (bid, bundle_sha, commitment)})
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO noexec_bundle VALUES(?,?,?,?,?,?,?,?,?)",
                            (bid, time.time(), _canon(bundle), bundle_sha, _canon(answer),
                             commitment, hashlib.sha256(secret.encode()).hexdigest(),
                             audit_hash, block))
        ctx["conn"].commit()
    return {"built": True, "bundle": bid,
            "send_this_link": SITE + "/x/noexec/bundle?id=" + bid,
            "bundle_sha256": bundle_sha,
            "answer_key_commitment": commitment,
            "sealed_in_chain": audit_hash, "block_index": block,
            "check_the_seal": _block_url(block),
            "reveal_later_keep_private": SITE + "/x/noexec/reveal?id=%s&secret=%s" % (bid, secret),
            "note": "Send only the bundle link. Keep the reveal link to yourself until the "
                    "reviewer has published results."}, 200


def _custody_count(cus):
    if not isinstance(cus, dict):
        return "unavailable"
    for k in ("independent_holders_today", "independent_holders", "holders_today", "count",
              "independent"):
        if k in cus:
            return cus[k]
    for v in cus.values():
        if isinstance(v, dict):
            for k in ("independent_holders", "count", "holders"):
                if k in v:
                    return v[k]
    return "as sealed at " + SITE + "/x/custody/status"


def _query(ctx):
    """Read the query string straight off the request, whatever the router passed."""
    try:
        h = ctx.get("handler") if isinstance(ctx, dict) else None
        path = getattr(h, "path", "") or ""
        if "?" in path:
            from urllib.parse import parse_qs
            return {k: v[0] for k, v in parse_qs(path.split("?", 1)[1]).items()}
    except Exception:
        pass
    return {}


def _q(data, k):
    v = data.get(k, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v).strip()


def _get(ctx, bid):
    with ctx["lock"]:
        return ctx["conn"].execute(
            "SELECT id,created,bundle,bundle_sha256,answer_key,key_commitment,secret_digest,"
            "audit_hash,block_index FROM noexec_bundle WHERE id=?", (bid,)).fetchone()


def _bundle(ctx, data):
    row = _get(ctx, _q(data, "id"))
    if not row:
        return {"error": "bundle_not_found"}, 404
    return {"bundle": json.loads(row[2]), "bundle_sha256": row[3],
            "answer_key_commitment": row[5],
            "commitment_sealed_in_chain": row[7], "commitment_block": _block_url(row[8]),
            "commitment_rule": "SHA-256 of the canonical JSON of the answer key, which includes "
                               "this bundle's SHA-256 and a random salt. It was sealed before "
                               "this bundle was sent and will be revealed after review."}, 200


def _reveal(ctx, data):
    row = _get(ctx, _q(data, "id"))
    if not row:
        return {"error": "bundle_not_found"}, 404
    secret = _q(data, "secret")
    if not secret or hashlib.sha256(secret.encode()).hexdigest() != row[6]:
        return {"error": "not_yet_revealed"}, 403
    answer = json.loads(row[4])
    return {"answer_key": answer, "recomputed_commitment": _sha(answer),
            "sealed_commitment": row[5], "matches": _sha(answer) == row[5],
            "sealed_in": _block_url(row[8])}, 200


def handle(method, action, data, api_key, ctx):
    _setup(ctx)
    action = (action or "").strip("/")
    data = dict(data or {})
    if "?" in action:
        from urllib.parse import parse_qs
        action, qs = action.split("?", 1)
        for k, v in parse_qs(qs).items():
            data.setdefault(k, v[0])
    for k, v in _query(ctx).items():
        if not _q(data, k):
            data[k] = v
    action = action.strip("/").lower()
    if action in ("status", "spec", ""):
        with ctx["lock"]:
            n = ctx["conn"].execute("SELECT COUNT(*) FROM noexec_bundle").fetchone()[0]
            last = ctx["conn"].execute("SELECT id,block_index FROM noexec_bundle ORDER BY created "
                                       "DESC LIMIT 3").fetchall()
        return {"module": "noexec", "version": VERSION, "armed": True, "bundles_built": n,
                "latest": [{"bundle": r[0], "link": SITE + "/x/noexec/bundle?id=" + r[0],
                            "sealed_block": r[1]} for r in last],
                "build": SITE + "/x/noexec/build"}, 200
    if action == "build":
        try:
            return _build(ctx)
        except Exception as e:
            _last[0] = 0.0
            return {"built": False, "error": str(e)[:500]}, 500
    if action == "bundle":
        return _bundle(ctx, data)
    if action == "reveal":
        return _reveal(ctx, data)
    return {"error": "unknown_action", "GET": ["status", "build", "bundle", "reveal"]}, 404
