#!/usr/bin/env python3
"""
modules/passport.py  -  the Agent Passport
==========================================

An AI agent that wants to act somewhere - pay, book, send, change a record -
asks sebbi.pro first. sebbi.pro derives its authority from a human grant,
checks nothing upstream has been revoked or expired, and hands back a
PASSPORT: a short signed token naming exactly what may be done, where, and
for how long.

The site the agent is acting on does not have to trust the agent, the model,
or the company that built it. It checks the passport:

  OFFLINE   verify the Ed25519 signature against the published key. No call
            to sebbi.pro, nothing installed, milliseconds.
  LIVE      ask sebbi.pro whether the authority behind it still stands at
            this instant - revocation, expiry, integrity, the whole lineage.
  REDEEM    spend it. Once. Against the exact parameters it was issued for.
            Standing is re-derived at the moment of redemption, so a passport
            whose authority was pulled a second ago does not bind. The
            redemption, or the refusal, is sealed in the chain.

The forcing does not come from controlling the AI. Nobody can. It comes from
the other side: a site publishes one small file saying which actions need a
passport, and an agent without one is simply not served. That works for
every model from every vendor, and no AI company controls it.

Machine-native from the ground up:
  - one public discovery document a site hosts (the "actions.txt" of agents)
  - a token any language can verify with a standard Ed25519 library
  - an MCP endpoint, so an agent requests and checks passports as tools

Built entirely on continuity.py (v1.6.0+). No second authority system, no
second chain, no second key: the passport is signed with the same key that
signs authority proofs, and every step is sealed into the same chain.

    GET  /x/passport/status               module status                 (public)
    GET  /x/passport/spec                 token format, offline rules   (public)
    GET  /x/passport/demo                 full live story in one tap    (public)
    GET  /x/passport/verify?token=&audience=   offline + live check     (public)
    POST /x/passport/redeem               spend once, sealed, and hand back a
                                          signed redemption receipt     (public)
    GET  /x/passport/receipt?pid=         the signed receipts for a passport
    GET  /x/passport/receipt?receipt=     check a receipt offline + against the chain
    GET  /x/passport/sitefile?domain=&require=  the file a site hosts   (public)
    POST /x/passport/issue                mint a passport               (keyed)
    POST /x/passport/mcp                  MCP JSON-RPC endpoint         (public;
                                          request tool needs a bearer key)
"""

import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone

VERSION = "1.1.0"

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "demo"), ("GET", "verify"),
          ("POST", "verify"), ("POST", "redeem"), ("GET", "sitefile"), ("POST", "mcp"),
          ("GET", "mcp"), ("GET", "receipt"), ("POST", "receipt")}

BASE = "https://sebbi.pro/x/passport/"
TOKEN_TAG = "sbp1"
SIG_PREFIX = b"AILEASH-PASSPORT-v1:"
RECEIPT_TAG = "sbr1"
RECEIPT_PREFIX = b"AILEASH-PASSPORT-RECEIPT-v1:"   # a receipt can never pass as a passport
MCP_PROTOCOL = "2025-06-18"

DEMO_KEY = "public-passport-demo"
DEMO_GAP = 60            # seconds between demo runs
DEMO_PER_DAY = 40

_ready = False
_last_demo = [0.0]


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _continuity():
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("continuity.py") and hasattr(m, "_confirm") and hasattr(m, "_evaluate"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuity.py")
    spec = importlib.util.spec_from_file_location("passport_continuity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _setup(ctx):
    global _ready
    if _ready:
        return
    with ctx["lock"]:
        c = ctx["conn"]
        c.execute("CREATE TABLE IF NOT EXISTS passport(id TEXT PRIMARY KEY,evaluation TEXT,"
                  "grant_id TEXT,audience TEXT,action TEXT,params_digest TEXT,"
                  "lineage_digest TEXT,issued REAL,expires REAL,token_digest TEXT,"
                  "audit_hash TEXT,block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS passport_use(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                  "passport_id TEXT,outcome TEXT,reasons TEXT,at REAL,audit_hash TEXT,"
                  "block_index INTEGER)")
        c.execute("CREATE TABLE IF NOT EXISTS passport_receipt(id INTEGER PRIMARY KEY "
                  "AUTOINCREMENT,passport_id TEXT,outcome TEXT,receipt TEXT,digest TEXT,"
                  "at_ms INTEGER,block_index INTEGER)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_psp_receipt ON passport_receipt(passport_id)")
        c.execute("CREATE TABLE IF NOT EXISTS passport_demo(id INTEGER PRIMARY KEY "
                  "AUTOINCREMENT,at REAL)")
        c.commit()
    _ready = True


def _seal(ctx, kind, res_extra, key):
    now = time.time()
    ev = {"user_id": "psp:" + kind[:24], "action": kind, "amount": 0, "country": "UK",
          "device_id": "passport", "anomaly": 0, "device_risk": 0}
    res = {"decision": kind.upper(), "score": 0, "passport_version": VERSION}
    res.update(res_extra)
    out = ctx["seal"](ev, res, now, key)
    if isinstance(out, (list, tuple)):
        return out[0], (out[1] if len(out) > 1 else None)
    return out, None


# ----------------------------------------------------------------------
# the token
# ----------------------------------------------------------------------

def _sign(ctx, C, body):
    seed, pk, _src = C._keys(ctx)
    raw = _canon(body).encode("utf-8")
    sig = C._ed_signature(SIG_PREFIX + raw, seed, pk)
    return "%s.%s.%s" % (TOKEN_TAG, _b64e(raw), _b64e(sig))


def _open(ctx, C, token):
    """Offline check only: format and signature. Returns (body, problems)."""
    try:
        tag, b, s = str(token).strip().split(".")
        if tag != TOKEN_TAG:
            return None, ["not a sebbi.pro passport (expected prefix %s.)" % TOKEN_TAG]
        raw, sig = _b64d(b), _b64d(s)
        body = json.loads(raw)
    except Exception:
        return None, ["malformed token"]
    _seed, pk, _src = C._keys(ctx)
    if not C._ed_checkvalid(sig, SIG_PREFIX + raw, pk):
        return body, ["signature does not verify against the published key"]
    return body, []


def _mint(ctx, C, api_key, data):
    """Evaluate through continuity, and only on ALLOW issue a passport."""
    audience = str(data.get("audience", "")).strip().lower()
    if not audience or not C.ID_RE.match(audience):
        return {"error": "audience_required",
                "message": "Name the site or service the action is for, e.g. shop.example.com. "
                           "A passport is only good at the audience it names."}, 400
    ev, status = C._evaluate(ctx, api_key, {"grant": data.get("grant"),
                                            "action": data.get("action"),
                                            "params": data.get("params") or {},
                                            "purpose_tag": data.get("purpose_tag")})
    if status != 200:
        return ev, status
    if ev["verdict"] != "ALLOW":
        return {"issued": False, "verdict": ev["verdict"], "reasons": ev["reasons"],
                "evaluation": ev["evaluation"],
                "proof_of_refusal": "https://sebbi.pro/x/continuity/proof?evaluation="
                                    + ev["evaluation"],
                "note": "No passport. The refusal is sealed and provable, which is the "
                        "point: an agent can show it was NOT authorised."}, 200

    now = time.time()
    try:
        expires = datetime.fromisoformat(ev["valid_until"]).timestamp()
    except Exception:
        expires = now + 300
    pid = "p_" + uuid.uuid4().hex[:20]
    body = {
        "v": 1, "pid": pid, "iss": "sebbi.pro",
        "aud": audience,
        "act": ev["action"],
        "pd": ev["params_digest"],
        "grant": ev["grant"],
        "ld": ev["lineage_digest"],
        "eval": ev["evaluation"],
        "by": ev["authorised_by"],
        "agent": ev["executed_by"],
        "risk": ev["risk_accepted_by"],
        "iat": int(now), "iat_ms": int(now * 1000), "exp": int(expires),
        "blk": ev.get("block_index"),
        "nonce": uuid.uuid4().hex[:16],
    }
    token = _sign(ctx, C, body)
    tdig = hashlib.sha256(token.encode()).hexdigest()
    audit_hash, block = _seal(ctx, "passport_issued",
                              {"passport": pid, "evaluation": ev["evaluation"],
                               "audience": audience, "token_digest": tdig,
                               "detail": "pid=%s;aud=%s;eval=%s;token=%s"
                                         % (pid, audience, ev["evaluation"], tdig)}, api_key)
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO passport VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (pid, ev["evaluation"], ev["grant"], audience, ev["action"],
                             ev["params_digest"], ev["lineage_digest"], now, expires, tdig,
                             audit_hash, block))
        ctx["conn"].commit()
    return {"issued": True, "passport": token, "pid": pid, "audience": audience,
            "action": ev["action"], "expires_at": _iso(expires),
            "authorised_by": ev["authorised_by"], "agent": ev["executed_by"],
            "risk_accepted_by": ev["risk_accepted_by"],
            "sealed_in_chain": audit_hash, "block_index": block,
            "verify": BASE + "verify?token=" + token,
            "present_it": "Send it to the site in the header  Agent-Passport: <token>"}, 200


def _check(ctx, C, token, audience=None):
    """Offline + live. Never seals - checking is free and unlimited in spirit."""
    body, problems = _open(ctx, C, token)
    out = {"offline": {"signature": "ok" if body and not problems else "FAILED"}}
    if body is None or problems:
        out["valid"] = False
        out["problems"] = problems
        return out, body
    now = time.time()
    if now > body.get("exp", 0):
        problems.append("expired at %s" % _iso(body.get("exp")))
    if audience and audience.strip().lower() != body.get("aud"):
        problems.append("issued for %s, presented at %s" % (body.get("aud"), audience))
    out["offline"]["expiry"] = "ok" if now <= body.get("exp", 0) else "EXPIRED"

    standing, lineage = C._standing_at_bind(ctx, body.get("grant"), body.get("ld"), now)
    with ctx["lock"]:
        spent = ctx["conn"].execute(
            "SELECT confirmed FROM auth_exec WHERE eval_id=? AND outcome<>'rejected' "
            "LIMIT 1", (body.get("eval"),)).fetchone()
    if spent:
        problems.append("already redeemed at %s" % _iso(spent[0]))
    problems.extend(standing)
    out["live"] = {"standing": "holds" if not standing else "LOST",
                   "checked_at": _iso(now), "lineage": lineage,
                   "redeemed": bool(spent)}
    out["valid"] = not problems
    out["problems"] = problems
    out["passport"] = body
    return out, body


def _rev_head(ctx):
    """Where the revocation log stood just before a decision was taken.

    continuity re-reads revocations after this point, so everything up to and
    including this entry was certainly in front of the decision. Order is then
    proven by chain position, not by comparing two clocks.
    """
    with ctx["lock"]:
        row = ctx["conn"].execute("SELECT id,block_index FROM auth_revoke "
                                  "ORDER BY id DESC LIMIT 1").fetchone()
    return {"entries_read_through": row[0] if row else 0,
            "last_revocation_block": row[1] if row else None}


def _lineage_revocations(ctx, C, grant_id):
    out = []
    chain, _err = C._walk(ctx, grant_id) if grant_id else (None, None)
    for g in chain or []:
        rev = C._revocation(ctx, g["id"])
        out.append({"grant": g["id"],
                    "revoked": bool(rev),
                    "revocation_block": rev["block_index"] if rev else None,
                    "revoked_at_ms": int(rev["revoked_ts"] * 1000) if rev else None})
    return out


def _ms(iso_text, fallback):
    try:
        return int(datetime.fromisoformat(iso_text).timestamp() * 1000)
    except Exception:
        return int(fallback * 1000)


CHECKS = ["signature", "audience", "expiry", "single_use", "exact_parameters",
          "lineage_integrity", "lineage_revocation", "lineage_validity_window",
          "lineage_unchanged_since_evaluation"]


def _receipt(ctx, C, token, body, audience, outcome, problems, decided_ms,
             block, audit_hash, seq, rev_head, params):
    """A signed, self-contained record of one redemption decision.

    It answers the three questions an outside auditor asks of any "it was
    still valid when used" claim:
      A  which exact event    - passport, token digest, site, action, parameters
      B  in what order        - chain block of this decision against the chain
                                block of every revocation in the lineage
      C  what was checked     - the complete, closed list of conditions redemption
                                depends on, each with its result
    """
    pd = hashlib.sha256(C.EVAL_PREFIX + _canon(
        {"action": body.get("act"), "params": params}).encode("utf-8")).hexdigest() \
        if hasattr(C, "EVAL_PREFIX") else None
    lineage = _lineage_revocations(ctx, C, body.get("grant"))
    order = []
    for item in lineage:
        rb = item["revocation_block"]
        if rb is None:
            rel = "no revocation recorded"
        elif block is not None and rb < block:
            rel = "revocation sealed BEFORE this decision"
        else:
            rel = "revocation sealed AFTER this decision"
        order.append(dict(item, relation=rel))
    results = {k: "pass" for k in CHECKS}
    for msg in (x.lower() for x in problems if x):
        if "presented at" in msg:
            results["audience"] = "fail"
        elif "evaluation expired" in msg:
            results["expiry"] = "fail"
        elif "already bound" in msg or "concurrent request" in msg:
            results["single_use"] = "fail"
        elif "parameters do not match" in msg:
            results["exact_parameters"] = "fail"
        elif "no longer matches" in msg:
            results["lineage_integrity"] = "fail"
        elif "was revoked" in msg:
            results["lineage_revocation"] = "fail"
        elif "not valid until" in msg or ("grant" in msg and "expired at" in msg):
            results["lineage_validity_window"] = "fail"
        elif ("lineage is not the one" in msg or "does not terminate" in msg
              or "grant not found" in msg or "walk limit" in msg):
            results["lineage_unchanged_since_evaluation"] = "fail"
        else:
            results.setdefault("other", []).append(msg)
    if outcome == "refused" and results["audience"] == "fail":
        # A wrong-site refusal stops before the live checks run.
        for k in CHECKS[2:]:
            results[k] = "not reached"
    r = {
        "v": 1, "kind": "passport_redemption_receipt", "iss": "sebbi.pro",
        "pid": body.get("pid"),
        "token_digest": hashlib.sha256(token.encode()).hexdigest(),
        "presented_at": audience, "passport_audience": body.get("aud"),
        "action": body.get("act"), "evaluation": body.get("eval"),
        "params_digest_presented": pd, "params_digest_authorised": body.get("pd"),
        "outcome": outcome, "problems": problems,
        "decided_at_ms": decided_ms,
        "clock": "server UTC system clock. Order is proven by chain position, not by clock.",
        "chain": {"block": block, "audit_hash": audit_hash, "seq": seq},
        "revocation_log": rev_head,
        "lineage_order": order,
        "checks": results,
        "completeness": "These are all the conditions a sebbi.pro passport redemption "
                        "depends on. Nothing else is consulted and nothing else can "
                        "change the outcome.",
        "nonce": uuid.uuid4().hex[:16],
    }
    raw = _canon(r).encode("utf-8")
    seed, pk, _src = C._keys(ctx)
    sig = C._ed_signature(RECEIPT_PREFIX + raw, seed, pk)
    tok = "%s.%s.%s" % (RECEIPT_TAG, _b64e(raw), _b64e(sig))
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO passport_receipt(passport_id,outcome,receipt,digest,"
                            "at_ms,block_index) VALUES(?,?,?,?,?,?)",
                            (body.get("pid"), outcome, tok,
                             hashlib.sha256(tok.encode()).hexdigest(), decided_ms, block))
        ctx["conn"].commit()
    return tok, r


def _redeem(ctx, C, data):
    token = str(data.get("token") or data.get("passport") or "").strip()
    audience = str(data.get("audience", "")).strip().lower()
    params = data.get("params") or {}
    if not token or not audience:
        return {"error": "token_and_audience_required"}, 400
    body, problems = _open(ctx, C, token)
    if body is None or problems:
        return {"redeemed": False, "problems": problems}, 409
    pid = body.get("pid")
    rev_head = _rev_head(ctx)

    if audience != body.get("aud"):
        now = time.time()
        reasons = ["issued for %s, presented at %s" % (body.get("aud"), audience)]
        audit_hash, block = _seal(ctx, "passport_refused",
                                  {"passport": pid, "reasons": reasons,
                                   "detail": "pid=%s;wrong_audience" % pid},
                                  "passport-redeem:" + audience[:60])
        with ctx["lock"]:
            ctx["conn"].execute("INSERT INTO passport_use(passport_id,outcome,reasons,at,"
                                "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                                (pid, "refused", _canon(reasons), now, audit_hash, block))
            ctx["conn"].commit()
        tok, rc = _receipt(ctx, C, token, body, audience, "refused", reasons,
                           int(now * 1000), block, audit_hash, None, rev_head, params)
        return {"redeemed": False, "problems": reasons, "sealed_in_chain": audit_hash,
                "block_index": block, "receipt": tok, "receipt_body": rc,
                "check_receipt": BASE + "receipt?receipt=" + tok}, 409

    # The consequence boundary. continuity re-derives standing, enforces the
    # window, compares the exact parameters, and allows one binding only.
    t0 = time.time()
    r, s = C._confirm(ctx, "passport-redeem:" + audience[:60],
                      {"evaluation": body.get("eval"), "action": body.get("act"),
                       "params": params, "outcome": "redeemed@" + audience[:40]})
    bound = bool(r.get("bound"))
    probs = r.get("problems", []) or ([r.get("error")] if r.get("error") else [])
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO passport_use(passport_id,outcome,reasons,at,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (pid, "redeemed" if bound else "refused",
                             _canon(probs), time.time(),
                             r.get("sealed_in_chain"), r.get("block_index")))
        ctx["conn"].commit()
    decided_ms = _ms((r.get("standing_at_bind") or {}).get("checked_at"), t0)
    tok, rc = _receipt(ctx, C, token, body, audience, "redeemed" if bound else "refused",
                       probs, decided_ms, r.get("block_index"), r.get("sealed_in_chain"),
                       r.get("receipt_seq"), rev_head, params)
    return {"redeemed": bound, "passport": pid, "audience": audience,
            "action": body.get("act"), "problems": probs,
            "standing_at_redemption": r.get("standing_at_bind"),
            "sealed_in_chain": r.get("sealed_in_chain"), "block_index": r.get("block_index"),
            "receipt": tok, "receipt_body": rc,
            "check_receipt": BASE + "receipt?receipt=" + tok,
            "meaning": ("Bound. The action was authorised by a human-rooted lineage that still "
                        "stood at this instant, on exactly these parameters, once."
                        if bound else
                        "Refused. Do not perform the action. The refusal is sealed.")}, \
        (200 if bound else 409)


def _receipt_check(ctx, C, data):
    tok = str(data.get("receipt", "")).strip()
    pid = str(data.get("pid", "")).strip()
    if not tok and (not pid or not pid.startswith("p_")):
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT passport_id,outcome,receipt FROM passport_receipt "
                                       "ORDER BY id DESC LIMIT 5").fetchall()
        return {"what_this_is": "Every passport redemption on sebbi.pro, accepted or refused, "
                                "gets a signed receipt. Tap any link below to check one.",
                "latest": [{"passport": r[0], "outcome": r[1],
                            "check_this_receipt": BASE + "receipt?receipt=" + r[2],
                            "every_receipt_for_this_passport": BASE + "receipt?pid=" + r[0]}
                           for r in rows]}, 200
    if pid and not tok:
        with ctx["lock"]:
            rows = ctx["conn"].execute("SELECT receipt FROM passport_receipt WHERE "
                                       "passport_id=? ORDER BY id ASC", (pid,)).fetchall()
        return {"passport": pid, "receipts": [x[0] for x in rows],
                "count": len(rows),
                "check_one": BASE + "receipt?receipt=<receipt>"}, 200
    try:
        tag, b, sg = tok.split(".")
        if tag != RECEIPT_TAG:
            raise ValueError
        raw, sig = _b64d(b), _b64d(sg)
        body = json.loads(raw)
    except Exception:
        return {"valid": False, "problems": ["not a sebbi.pro redemption receipt "
                                             "(expected prefix %s.)" % RECEIPT_TAG]}, 200
    _seed, pk, _src = C._keys(ctx)
    if not C._ed_checkvalid(sig, RECEIPT_PREFIX + raw, pk):
        return {"valid": False, "problems": ["signature does not verify against the "
                                             "published key"]}, 200
    with ctx["lock"]:
        known = ctx["conn"].execute("SELECT 1 FROM passport_receipt WHERE digest=?",
                                    (hashlib.sha256(tok.encode()).hexdigest(),)).fetchone()
    return {"valid": True, "signature": "ok", "issued_by_this_server": bool(known),
            "receipt": body,
            "public_key": "https://sebbi.pro/x/continuity/pubkey",
            "check_offline": "Ed25519 over 'AILEASH-PASSPORT-RECEIPT-v1:' || the body bytes",
            "check_chain": "Block %s should carry audit hash %s"
                           % ((body.get("chain") or {}).get("block"),
                              (body.get("chain") or {}).get("audit_hash"))}, 200


def _sitefile(data):
    domain = str(data.get("domain", "your.site")).strip().lower() or "your.site"
    req = str(data.get("require", "payments.*")).strip()
    require = [x.strip() for x in req.split(",") if x.strip()]
    doc = {
        "agent_passport": {
            "version": 1,
            "audience": domain,
            "required_for": require,
            "issuer": "sebbi.pro",
            "public_key": "https://sebbi.pro/x/continuity/pubkey",
            "verify": BASE + "verify",
            "redeem": BASE + "redeem",
            "header": "Agent-Passport",
            "live_standing_required": True,
            "single_use": True,
            "spec": BASE + "spec",
        }
    }
    return {"host_this_at": "https://%s/.well-known/agent-passport.json" % domain,
            "file": doc,
            "what_it_does": "Tells every AI agent that these actions need a passport. An "
                            "agent without one is not served. Your server checks the "
                            "signature offline and redeems it once at the moment of action."}, 200


def _spec(C):
    return {
        "passport_version": VERSION,
        "token": "sbp1.<base64url(canonical JSON body)>.<base64url(Ed25519 signature)>",
        "signature": "Ed25519 over 'AILEASH-PASSPORT-v1:' || the exact body bytes",
        "public_key": "https://sebbi.pro/x/continuity/pubkey",
        "body_fields": {
            "pid": "passport id", "iss": "issuer", "aud": "the one site it is good at",
            "act": "the capability", "pd": "digest of {action, params} it was issued for",
            "grant": "grant exercised", "ld": "lineage digest at issue",
            "eval": "sealed evaluation id", "by": "human who authorised",
            "agent": "who acts", "risk": "who accepts the risk",
            "iat": "issued (unix seconds)", "iat_ms": "issued (unix milliseconds)",
            "exp": "expires (unix)", "blk": "chain block of the evaluation",
            "nonce": "uniqueness",
        },
        "offline_check": ["split on '.'", "base64url-decode body and signature",
                          "verify Ed25519 over prefix + body bytes with the public key",
                          "check aud is you and exp is in the future"],
        "live_check": BASE + "verify?token=<token>&audience=<you>",
        "redeem": "POST " + BASE + "redeem  {token, audience, params}. Binds once, re-derives "
                  "standing at that instant, compares the exact parameters, seals the outcome.",
        "receipt": {
            "format": "sbr1.<base64url(canonical JSON body)>.<base64url(Ed25519 signature)>",
            "signature": "Ed25519 over 'AILEASH-PASSPORT-RECEIPT-v1:' || the body bytes, same "
                         "published key. The different prefix means a receipt can never be "
                         "passed off as a passport.",
            "answers": {"A_which_event": "pid, token_digest, presented_at, action, parameter "
                                         "digests presented and authorised",
                        "B_what_order": "chain block of this decision against the chain block "
                                        "of every revocation in the lineage, plus how far the "
                                        "revocation log had been read before deciding",
                        "C_what_was_checked": "the closed list of every condition redemption "
                                              "depends on, each with its result"},
            "check": BASE + "receipt?receipt=<receipt>",
            "list": BASE + "receipt?pid=<passport id>",
        },
        "discovery": BASE + "sitefile?domain=<your.site>&require=payments.*,records.write",
        "mcp": BASE + "mcp",
        "requires_continuity": ">= 1.6.0",
        "continuity_version": getattr(C, "VERSION", None),
    }, 200


# ----------------------------------------------------------------------
# the demo - the whole story in one tap
# ----------------------------------------------------------------------

def _demo(ctx, C):
    now = time.time()
    if now - _last_demo[0] < DEMO_GAP:
        return {"error": "too_soon", "retry_after_seconds": int(DEMO_GAP - (now - _last_demo[0]))}, 429
    with ctx["lock"]:
        n = ctx["conn"].execute("SELECT COUNT(*) FROM passport_demo WHERE at>?",
                                (now - 86400,)).fetchone()[0]
    if n >= DEMO_PER_DAY:
        return {"error": "daily_limit"}, 429
    _last_demo[0] = now
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO passport_demo(at) VALUES(?)", (now,))
        ctx["conn"].commit()

    tag = uuid.uuid4().hex[:10]
    aud = "shop.demo.sebbi.pro"
    params = {"amount": 20}
    story = []

    def grant(gid):
        g = {"id": gid, "issuer": "demo-human", "issuer_kind": "human",
             "subject": "demo-agent-" + tag, "scope": ["demo.pay"],
             "constraints": {"max_amount": 50}, "purpose": "demo purchase",
             "purpose_tags": ["demo"], "not_after": now + 900}
        return C._issue(ctx, DEMO_KEY, g)[0]

    def ask(gid):
        return _mint(ctx, C, DEMO_KEY, {"grant": gid, "action": "demo.pay", "params": params,
                                        "purpose_tag": "demo", "audience": aud})[0]

    # Act 1 - a human authorises, the agent gets a passport, the shop accepts it once.
    g1 = "demo_" + tag + "_1"
    gr = grant(g1)
    story.append({"act": "1. A human grants an agent authority to pay up to 50",
                  "grant": g1, "block": gr.get("block_index")})
    p1 = ask(g1)
    story.append({"act": "2. The agent asks for a passport to pay 20 at " + aud,
                  "issued": p1.get("issued"), "passport": p1.get("passport"),
                  "block": p1.get("block_index")})
    if not p1.get("issued"):
        return {"demo": "stopped", "why": "no passport issued", "story": story,
                "detail": p1}, 200
    chk, _b = _check(ctx, C, p1["passport"], aud)
    story.append({"act": "3. The shop checks it (signature offline, standing live)",
                  "valid": chk["valid"], "problems": chk["problems"]})
    r1 = _redeem(ctx, C, {"token": p1["passport"], "audience": aud, "params": params})[0]
    story.append({"act": "4. The shop redeems it at the moment of payment",
                  "redeemed": r1["redeemed"], "block": r1.get("block_index"),
                  "signed_receipt": r1.get("receipt"),
                  "check_this_receipt": r1.get("check_receipt"),
                  "every_receipt_for_this_passport": BASE + "receipt?pid=" + str(r1.get("passport"))})
    r2 = _redeem(ctx, C, {"token": p1["passport"], "audience": aud, "params": params})[0]
    story.append({"act": "5. Someone replays the same passport",
                  "redeemed": r2["redeemed"], "why": r2.get("problems")})

    # Act 2 - a valid passport, then the human pulls the authority.
    g2 = "demo_" + tag + "_2"
    grant(g2)
    p2 = ask(g2)
    story.append({"act": "6. A second passport is issued - valid, unexpired",
                  "issued": p2.get("issued")})
    rv = C._revoke(ctx, DEMO_KEY, {"grant": g2, "reason": "demo: human pulls authority"})[0]
    story.append({"act": "7. The human revokes the agent's authority",
                  "block": rv.get("block_index")})
    r3 = _redeem(ctx, C, {"token": p2.get("passport", ""), "audience": aud,
                          "params": params})[0]
    story.append({"act": "8. The agent tries to spend the still-signed passport",
                  "redeemed": r3["redeemed"], "why": r3.get("problems"),
                  "order": [x.get("relation") for x in
                            (r3.get("receipt_body") or {}).get("lineage_order", [])],
                  "signed_receipt": r3.get("receipt"),
                  "check_this_receipt": r3.get("check_receipt")})

    # Act 3 - the wrong door, and a tampered amount.
    g3 = "demo_" + tag + "_3"
    grant(g3)
    p3 = ask(g3)
    r4 = _redeem(ctx, C, {"token": p3.get("passport", ""), "audience": "evil.example.com",
                          "params": params})[0]
    story.append({"act": "9. The passport is presented at a different site",
                  "redeemed": r4["redeemed"], "why": r4.get("problems")})
    r5 = _redeem(ctx, C, {"token": p3.get("passport", ""), "audience": aud,
                          "params": {"amount": 49}})[0]
    story.append({"act": "10. At the right site, but for 49 instead of 20",
                  "redeemed": r5["redeemed"], "why": r5.get("problems")})

    held = (r1["redeemed"] and not r2["redeemed"] and not r3["redeemed"]
            and not r4["redeemed"] and not r5["redeemed"])
    return {"demo": "Agent Passport - live on production, every step sealed",
            "result": "ALL TEN BEHAVED" if held else "SOMETHING DID NOT BEHAVE - see story",
            "one_line": "The payment happened once, where it was meant to, for the amount "
                        "authorised, while the human's authority stood. Every other attempt "
                        "was refused and the refusal is on the chain.",
            "story": story,
            "make_your_site_require_it": BASE + "sitefile?domain=your.site&require=payments.*",
            "spec": BASE + "spec"}, 200


# ----------------------------------------------------------------------
# MCP - agents use passports as tools
# ----------------------------------------------------------------------

_TOOLS = [
    {"name": "passport_request",
     "description": "Request a signed Agent Passport before taking an action. Returns a "
                    "token to present to the site, or a sealed refusal. Needs a sebbi.pro "
                    "API key as Authorization: Bearer.",
     "inputSchema": {"type": "object", "required": ["grant", "action", "audience"],
                     "properties": {"grant": {"type": "string"}, "action": {"type": "string"},
                                    "audience": {"type": "string"},
                                    "params": {"type": "object"},
                                    "purpose_tag": {"type": "string"}}}},
    {"name": "passport_verify",
     "description": "Check a passport: signature, expiry, audience, and whether the "
                    "authority behind it still stands right now.",
     "inputSchema": {"type": "object", "required": ["token"],
                     "properties": {"token": {"type": "string"},
                                    "audience": {"type": "string"}}}},
    {"name": "passport_redeem",
     "description": "Spend a passport once at the moment of action. Refused if authority "
                    "was revoked, it expired, the site or parameters differ, or it was used.",
     "inputSchema": {"type": "object", "required": ["token", "audience"],
                     "properties": {"token": {"type": "string"},
                                    "audience": {"type": "string"},
                                    "params": {"type": "object"}}}},
    {"name": "passport_sitefile",
     "description": "Generate the discovery file a site hosts to require passports.",
     "inputSchema": {"type": "object",
                     "properties": {"domain": {"type": "string"},
                                    "require": {"type": "string"}}}},
]


def _mcp(ctx, C, api_key, data):
    rid = data.get("id")
    method = data.get("method", "")
    p = data.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}, 200

    if method == "initialize":
        return ok({"protocolVersion": p.get("protocolVersion") or MCP_PROTOCOL,
                   "capabilities": {"tools": {}},
                   "serverInfo": {"name": "sebbi-passport", "version": VERSION},
                   "instructions": "Before any consequential action, call passport_request "
                                   "and present the token to the site. No passport, no action."})
    if method in ("notifications/initialized", "ping"):
        return ok({})
    if method == "tools/list":
        return ok({"tools": _TOOLS})
    if method == "tools/call":
        name = p.get("name")
        a = p.get("arguments") or {}
        if name == "passport_request":
            if not api_key:
                res, st = {"error": "needs Authorization: Bearer <sebbi.pro key>"}, 401
            else:
                res, st = _mint(ctx, C, api_key, a)
        elif name == "passport_verify":
            res, _b = _check(ctx, C, a.get("token", ""), a.get("audience"))
            st = 200
        elif name == "passport_redeem":
            res, st = _redeem(ctx, C, a)
        elif name == "passport_sitefile":
            res, st = _sitefile(a)
        else:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": "unknown tool"}}, 200
        return ok({"content": [{"type": "text", "text": json.dumps(res, default=str)}],
                   "isError": st >= 400})
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": "method not found"}}, 200


# ----------------------------------------------------------------------

def _status(ctx, C):
    with ctx["lock"]:
        issued = ctx["conn"].execute("SELECT COUNT(*) FROM passport").fetchone()[0]
        used = ctx["conn"].execute("SELECT outcome,COUNT(*) FROM passport_use "
                                   "GROUP BY outcome").fetchall()
        receipts = ctx["conn"].execute("SELECT COUNT(*) FROM passport_receipt").fetchone()[0]
    tally = {k: v for k, v in used}
    cv = getattr(C, "VERSION", "0")
    return {"module": "passport", "version": VERSION, "armed": True,
            "continuity_version": cv,
            "continuity_ready": hasattr(C, "_standing_at_bind"),
            "passports_issued": issued,
            "redeemed": tally.get("redeemed", 0), "refused": tally.get("refused", 0),
            "signed_receipts": receipts,
            "demo": BASE + "demo", "spec": BASE + "spec",
            "sitefile": BASE + "sitefile?domain=your.site&require=payments.*",
            "mcp": BASE + "mcp"}, 200


def handle(method, action, data, api_key, ctx):
    C = _continuity()
    C._setup(ctx)
    _setup(ctx)
    action = (action or "").strip("/").lower()
    data = data or {}

    if not hasattr(C, "_standing_at_bind") and action not in ("status", "spec"):
        return {"error": "continuity_too_old",
                "message": "Passport needs continuity.py 1.6.0 or later."}, 503

    if action == "status":
        return _status(ctx, C)
    if action == "spec":
        return _spec(C)
    if action == "sitefile":
        return _sitefile(data)
    if action == "demo" and method == "GET":
        return _demo(ctx, C)
    if action == "verify":
        res, _b = _check(ctx, C, data.get("token", ""), data.get("audience"))
        return res, 200
    if action == "redeem" and method == "POST":
        return _redeem(ctx, C, data)
    if action == "receipt":
        return _receipt_check(ctx, C, data)
    if action == "mcp":
        if method == "GET":
            return {"mcp": "POST JSON-RPC 2.0 here", "tools": [t["name"] for t in _TOOLS],
                    "server": "sebbi-passport", "version": VERSION}, 200
        return _mcp(ctx, C, api_key, data)
    if action == "issue" and method == "POST":
        if not api_key:
            return {"error": "invalid_api_key"}, 401
        return _mint(ctx, C, api_key, data)

    return {"error": "unknown_action",
            "GET": ["status", "spec", "demo", "verify", "sitefile", "mcp", "receipt"],
            "POST": ["issue", "verify", "redeem", "mcp", "receipt"]}, 404
