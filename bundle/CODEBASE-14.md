# Codebase — part 14 of 41

Contains:
- `modules/passport.py`
- `modules/passportpage.py`


## `modules/passport.py`

591 lines, 27641 bytes

```python
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
    POST /x/passport/redeem               spend once, sealed            (public)
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

VERSION = "1.0.0"

PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "demo"), ("GET", "verify"),
          ("POST", "verify"), ("POST", "redeem"), ("GET", "sitefile"), ("POST", "mcp"),
          ("GET", "mcp")}

BASE = "https://sebbi.pro/x/passport/"
TOKEN_TAG = "sbp1"
SIG_PREFIX = b"AILEASH-PASSPORT-v1:"
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
        "iat": int(now), "exp": int(expires),
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

    if audience != body.get("aud"):
        reasons = ["issued for %s, presented at %s" % (body.get("aud"), audience)]
        audit_hash, block = _seal(ctx, "passport_refused",
                                  {"passport": pid, "reasons": reasons,
                                   "detail": "pid=%s;wrong_audience" % pid},
                                  "passport-redeem:" + audience[:60])
        with ctx["lock"]:
            ctx["conn"].execute("INSERT INTO passport_use(passport_id,outcome,reasons,at,"
                                "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                                (pid, "refused", _canon(reasons), time.time(), audit_hash, block))
            ctx["conn"].commit()
        return {"redeemed": False, "problems": reasons, "sealed_in_chain": audit_hash,
                "block_index": block}, 409

    # The consequence boundary. continuity re-derives standing, enforces the
    # window, compares the exact parameters, and allows one binding only.
    r, s = C._confirm(ctx, "passport-redeem:" + audience[:60],
                      {"evaluation": body.get("eval"), "action": body.get("act"),
                       "params": params, "outcome": "redeemed@" + audience[:40]})
    bound = bool(r.get("bound"))
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO passport_use(passport_id,outcome,reasons,at,"
                            "audit_hash,block_index) VALUES(?,?,?,?,?,?)",
                            (pid, "redeemed" if bound else "refused",
                             _canon(r.get("problems", [])), time.time(),
                             r.get("sealed_in_chain"), r.get("block_index")))
        ctx["conn"].commit()
    return {"redeemed": bound, "passport": pid, "audience": audience,
            "action": body.get("act"), "problems": r.get("problems", []),
            "standing_at_redemption": r.get("standing_at_bind"),
            "sealed_in_chain": r.get("sealed_in_chain"), "block_index": r.get("block_index"),
            "meaning": ("Bound. The action was authorised by a human-rooted lineage that still "
                        "stood at this instant, on exactly these parameters, once."
                        if bound else
                        "Refused. Do not perform the action. The refusal is sealed.")}, \
        (200 if bound else 409)


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
            "iat": "issued (unix)", "exp": "expires (unix)", "blk": "chain block of the evaluation",
            "nonce": "uniqueness",
        },
        "offline_check": ["split on '.'", "base64url-decode body and signature",
                          "verify Ed25519 over prefix + body bytes with the public key",
                          "check aud is you and exp is in the future"],
        "live_check": BASE + "verify?token=<token>&audience=<you>",
        "redeem": "POST " + BASE + "redeem  {token, audience, params}. Binds once, re-derives "
                  "standing at that instant, compares the exact parameters, seals the outcome.",
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
                  "redeemed": r1["redeemed"], "block": r1.get("block_index")})
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
                  "redeemed": r3["redeemed"], "why": r3.get("problems")})

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
    tally = {k: v for k, v in used}
    cv = getattr(C, "VERSION", "0")
    return {"module": "passport", "version": VERSION, "armed": True,
            "continuity_version": cv,
            "continuity_ready": hasattr(C, "_standing_at_bind"),
            "passports_issued": issued,
            "redeemed": tally.get("redeemed", 0), "refused": tally.get("refused", 0),
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
            "GET": ["status", "spec", "demo", "verify", "sitefile", "mcp"],
            "POST": ["issue", "verify", "redeem", "mcp"]}, 404

```


## `modules/passportpage.py`

477 lines, 42509 bytes

```python
"""
modules/passportpage.py  v1.1.0
Serves the Agent Passport page at /passport, and the Passport Kit downloads
at /passport/sebbi_agent.py and /passport/sebbi_site.py.

Page module, same family as map.py / console.py / network.py: a runtime
do_GET patch puts full pages at clean URLs. Armed by hitting
/x/passportpage/status once after each deploy. server.py is never edited.
Everything is base64-embedded so no character can break the Python string.
The live demo on the page calls /x/passport/demo.
"""

import base64
import sys

VERSION = "1.1.0"
PAGE_PATH = "/passport"

_B64 = (
    "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPG1ldGEgbmFtZT0i"
    "dmlld3BvcnQiIGNvbnRlbnQ9IndpZHRoPWRldmljZS13aWR0aCwgaW5pdGlhbC1zY2FsZT0xLCB2aWV3cG9ydC1maXQ9Y292ZXIi"
    "Pgo8dGl0bGU+QWdlbnQgUGFzc3BvcnQg4oCUIHNlYmJpLnBybzwvdGl0bGU+CjxtZXRhIG5hbWU9ImRlc2NyaXB0aW9uIiBjb250"
    "ZW50PSJFdmVyeSBBSSBhZ2VudCBuZWVkcyBhIHBhc3Nwb3J0LiBTaWduZWQsIHNpbmdsZS11c2UgcGVybWlzc2lvbiBmb3IgQUkg"
    "YWN0aW9ucywgY2hlY2tlZCBhdCB0aGUgbW9tZW50IG9mIGFjdGlvbiwgc2VhbGVkIG9uIGEgcHVibGljIGNoYWluLiI+CjxsaW5r"
    "IHJlbD0icHJlY29ubmVjdCIgaHJlZj0iaHR0cHM6Ly9mb250cy5nb29nbGVhcGlzLmNvbSI+CjxsaW5rIGhyZWY9Imh0dHBzOi8v"
    "Zm9udHMuZ29vZ2xlYXBpcy5jb20vY3NzMj9mYW1pbHk9TmV3c3JlYWRlcjpvcHN6LHdnaHRANi4uNzIsNDAwOzYuLjcyLDUwMCZm"
    "YW1pbHk9SUJNK1BsZXgrU2Fuczp3Z2h0QDQwMDs1MDA7NjAwJmZhbWlseT1JQk0rUGxleCtNb25vOndnaHRANDAwOzUwMCZkaXNw"
    "bGF5PXN3YXAiIHJlbD0ic3R5bGVzaGVldCI+CjxzdHlsZT4KOnJvb3R7LS1pbms6IzBhMGYxZTstLWluazI6IzEwMTgyZTstLXBh"
    "cGVyOiNGQUZBRjY7LS1saW5lOiNERURCRDE7LS1nb2xkOiNjOWE4NGM7LS1vazojMkU3RDU3Oy0tb2tiZzojRTRFQ0U4Oy0td2Fy"
    "bjojOUMyRjI2Oy0td2FybmJnOiNGNUU2RTM7LS1tdXRlZDojNUE2MjcwOy0tZmFpbnQ6IzhBOTBBMDsKLS1zYW5zOidJQk0gUGxl"
    "eCBTYW5zJyxzeXN0ZW0tdWksc2Fucy1zZXJpZjstLXNlcmlmOidOZXdzcmVhZGVyJyxHZW9yZ2lhLHNlcmlmOy0tbW9ubzonSUJN"
    "IFBsZXggTW9ubycsdWktbW9ub3NwYWNlLG1vbm9zcGFjZX0KKntib3gtc2l6aW5nOmJvcmRlci1ib3g7bWFyZ2luOjA7cGFkZGlu"
    "ZzowfQpib2R5e2ZvbnQtZmFtaWx5OnZhcigtLXNhbnMpO2JhY2tncm91bmQ6dmFyKC0tcGFwZXIpO2NvbG9yOnZhcigtLWluayk7"
    "bGluZS1oZWlnaHQ6MS42Oy13ZWJraXQtZm9udC1zbW9vdGhpbmc6YW50aWFsaWFzZWR9Ci53cmFwe21heC13aWR0aDo4MjBweDtt"
    "YXJnaW46MCBhdXRvO3BhZGRpbmc6MCAyMnB4fQoudG9we2JvcmRlci1ib3R0b206MXB4IHNvbGlkIHZhcigtLWxpbmUpO3BhZGRp"
    "bmc6MTZweCAwfQoudG9wIC53cmFwe2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjthbGlnbi1pdGVt"
    "czpiYXNlbGluZTtnYXA6MTJweDtmbGV4LXdyYXA6d3JhcH0KLmJyYW5ke2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6"
    "ZToxM3B4fS5icmFuZCBie2NvbG9yOnZhcigtLWdvbGQpO2ZvbnQtd2VpZ2h0OjUwMH0KLnRvcCBuYXYgYXtmb250LWZhbWlseTp2"
    "YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLW11dGVkKTt0ZXh0LWRlY29yYXRpb246bm9uZTttYXJnaW4t"
    "bGVmdDoxNHB4fQouaGVyb3twYWRkaW5nOjU0cHggMCAyNnB4fQoua2lja3tmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNp"
    "emU6MTJweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3BhY2luZzouMDZlbTttYXJnaW4tYm90dG9tOjE0cHh9Ci5oZXJvIGgx"
    "e2ZvbnQtZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDM0cHgsNnZ3LDU2cHgpO2xp"
    "bmUtaGVpZ2h0OjEuMDU7bWF4LXdpZHRoOjE1Y2g7bWFyZ2luLWJvdHRvbToxOHB4fQouaGVybyBwe2ZvbnQtc2l6ZToxNy41cHg7"
    "Y29sb3I6dmFyKC0tbXV0ZWQpO21heC13aWR0aDo1NmNofQouY3Rhe2Rpc3BsYXk6aW5saW5lLWJsb2NrO21hcmdpbjoyNnB4IDEy"
    "cHggMCAwO2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxNHB4O3RleHQtZGVjb3JhdGlvbjpub25lO2JvcmRlci1y"
    "YWRpdXM6NXB4O3BhZGRpbmc6MTNweCAyMHB4O2N1cnNvcjpwb2ludGVyO2JvcmRlcjowfQouY3RhLmdvbGR7YmFja2dyb3VuZDp2"
    "YXIoLS1nb2xkKTtjb2xvcjp2YXIoLS1pbmspO2ZvbnQtd2VpZ2h0OjUwMH0KLmN0YS5naG9zdHtib3JkZXI6MXB4IHNvbGlkIHZh"
    "cigtLWxpbmUpO2NvbG9yOnZhcigtLWluayk7YmFja2dyb3VuZDojZmZmfQouc3RhdHN7ZGlzcGxheTpmbGV4O2dhcDoyMnB4O2Zs"
    "ZXgtd3JhcDp3cmFwO21hcmdpbi10b3A6MzBweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTJweDtjb2xvcjp2"
    "YXIoLS1mYWludCl9Ci5zdGF0cyBie2NvbG9yOnZhcigtLWluayk7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToxNXB4O2Rpc3Bs"
    "YXk6YmxvY2t9CnNlY3Rpb257cGFkZGluZzo0MHB4IDA7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tbGluZSl9Cmgye2ZvbnQt"
    "ZmFtaWx5OnZhcigtLXNlcmlmKTtmb250LXdlaWdodDo1MDA7Zm9udC1zaXplOmNsYW1wKDI2cHgsNC4ydncsMzZweCk7bGluZS1o"
    "ZWlnaHQ6MS4xMjttYXJnaW4tYm90dG9tOjE0cHg7bWF4LXdpZHRoOjIyY2h9Ci5sZWFke2NvbG9yOnZhcigtLW11dGVkKTttYXgt"
    "d2lkdGg6NjBjaDttYXJnaW4tYm90dG9tOjIycHh9Ci5zdGVwc3tkaXNwbGF5OmdyaWQ7Z2FwOjE0cHh9Ci5zdGVwe2JhY2tncm91"
    "bmQ6I2ZmZjtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWxpbmUpO2JvcmRlci1yYWRpdXM6N3B4O3BhZGRpbmc6MjBweCAyMnB4fQou"
    "c3RlcCAubntmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkKTtsZXR0ZXItc3Bh"
    "Y2luZzouMDVlbX0KLnN0ZXAgaDN7Zm9udC1mYW1pbHk6dmFyKC0tc2VyaWYpO2ZvbnQtd2VpZ2h0OjUwMDtmb250LXNpemU6MjFw"
    "eDttYXJnaW46NHB4IDAgNnB4fQouc3RlcCBwe2ZvbnQtc2l6ZToxNC44cHg7Y29sb3I6dmFyKC0tbXV0ZWQpfQouZGFya3tiYWNr"
    "Z3JvdW5kOnZhcigtLWluayk7Y29sb3I6I2ZmZjtib3JkZXItcmFkaXVzOjEwcHg7cGFkZGluZzozMHB4IDI0cHg7Ym9yZGVyOjJw"
    "eCBzb2xpZCB2YXIoLS1nb2xkKX0KLmRhcmsgaDJ7Y29sb3I6I2ZmZn0uZGFyayAubGVhZHtjb2xvcjpyZ2JhKDI1NSwyNTUsMjU1"
    "LC43Mil9CiNzdG9yeXttYXJnaW4tdG9wOjE4cHg7ZGlzcGxheTpncmlkO2dhcDo4cHh9Ci5yb3d7ZGlzcGxheTpmbGV4O2dhcDox"
    "MnB4O2FsaWduLWl0ZW1zOmZsZXgtc3RhcnQ7YmFja2dyb3VuZDp2YXIoLS1pbmsyKTtib3JkZXI6MXB4IHNvbGlkIHJnYmEoMjAx"
    "LDE2OCw3NiwuMTgpO2JvcmRlci1yYWRpdXM6NnB4O3BhZGRpbmc6MTFweCAxNHB4O2ZvbnQtc2l6ZToxNHB4O29wYWNpdHk6MDt0"
    "cmFuc2Zvcm06dHJhbnNsYXRlWSg2cHgpO3RyYW5zaXRpb246YWxsIC4zNXN9Ci5yb3cuc2hvd3tvcGFjaXR5OjE7dHJhbnNmb3Jt"
    "Om5vbmV9Ci5yb3cgLmlje2ZvbnQtZmFtaWx5OnZhcigtLW1vbm8pO2ZvbnQtc2l6ZToxMnB4O21pbi13aWR0aDo2NnB4O3RleHQt"
    "YWxpZ246Y2VudGVyO3BhZGRpbmc6MnB4IDZweDtib3JkZXItcmFkaXVzOjNweH0KLmljLnBhc3N7YmFja2dyb3VuZDojMTczOTJh"
    "O2NvbG9yOiM3ZmUzYjB9LmljLnN0b3B7YmFja2dyb3VuZDojM2QxYTE3O2NvbG9yOiNmZjhhODB9LmljLmluZm97YmFja2dyb3Vu"
    "ZDojMmEyYTFhO2NvbG9yOnZhcigtLWdvbGQpfQoucm93IC53aHl7ZGlzcGxheTpibG9jaztmb250LWZhbWlseTp2YXIoLS1tb25v"
    "KTtmb250LXNpemU6MTEuNXB4O2NvbG9yOnJnYmEoMjU1LDI1NSwyNTUsLjUpO21hcmdpbi10b3A6M3B4O3dvcmQtYnJlYWs6YnJl"
    "YWstd29yZH0KI3ZlcmRpY3R7Zm9udC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0tZ29sZCk7"
    "bWFyZ2luLXRvcDoxNnB4O21pbi1oZWlnaHQ6MjBweH0KLnJ1bntiYWNrZ3JvdW5kOnZhcigtLWdvbGQpO2NvbG9yOnZhcigtLWlu"
    "ayl9Ci5ncmlkMntkaXNwbGF5OmdyaWQ7Z2FwOjE0cHg7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmcn0KQG1lZGlhKG1pbi13aWR0"
    "aDo3MDBweCl7LmdyaWQye2dyaWQtdGVtcGxhdGUtY29sdW1uczoxZnIgMWZyfX0KLmNhcmR7YmFja2dyb3VuZDojZmZmO2JvcmRl"
    "cjoxcHggc29saWQgdmFyKC0tbGluZSk7Ym9yZGVyLXJhZGl1czo3cHg7cGFkZGluZzoyMHB4IDIycHh9Ci5jYXJkIC50YWd7Zm9u"
    "dC1mYW1pbHk6dmFyKC0tbW9ubyk7Zm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tZmFpbnQpO2xldHRlci1zcGFjaW5nOi4wNWVt"
    "fQouY2FyZCBoM3tmb250LWZhbWlseTp2YXIoLS1zZXJpZik7Zm9udC13ZWlnaHQ6NTAwO2ZvbnQtc2l6ZToyMHB4O21hcmdpbjo0"
    "cHggMCA2cHh9Ci5jYXJkIHB7Zm9udC1zaXplOjE0LjVweDtjb2xvcjp2YXIoLS1tdXRlZCk7bWFyZ2luLWJvdHRvbToxMHB4fQou"
    "Y2FyZCBwcmV7bWFyZ2luOjEwcHggMCAwfS5jYXJkIGEuY3Rhe2NvbG9yOnZhcigtLWluayk7d29yZC1icmVhazpub3JtYWx9LmNh"
    "cmQgYXtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTIuNXB4O2NvbG9yOnZhcigtLWluayk7d29yZC1icmVhazpi"
    "cmVhay1hbGx9CnByZXtiYWNrZ3JvdW5kOnZhcigtLWluayk7Y29sb3I6I2U4ZTZkZjtmb250LWZhbWlseTp2YXIoLS1tb25vKTtm"
    "b250LXNpemU6MTJweDtib3JkZXItcmFkaXVzOjZweDtwYWRkaW5nOjE0cHg7b3ZlcmZsb3cteDphdXRvO21hcmdpbi10b3A6OHB4"
    "fQouY2xvc2V7YmFja2dyb3VuZDp2YXIoLS1pbmspO2NvbG9yOiNmZmY7Ym9yZGVyLXJhZGl1czoxMHB4O3BhZGRpbmc6MzJweCAy"
    "NHB4O21hcmdpbjozNnB4IDAgNTBweH0KLmNsb3NlIGgye2NvbG9yOiNmZmZ9LmNsb3NlIHB7Y29sb3I6cmdiYSgyNTUsMjU1LDI1"
    "NSwuNzUpO21heC13aWR0aDo1NmNofQpmb290ZXJ7Ym9yZGVyLXRvcDoxcHggc29saWQgdmFyKC0tbGluZSk7cGFkZGluZzoyMnB4"
    "IDAgNDZweDtmb250LWZhbWlseTp2YXIoLS1tb25vKTtmb250LXNpemU6MTEuNXB4O2NvbG9yOnZhcigtLWZhaW50KX0KQG1lZGlh"
    "KHByZWZlcnMtcmVkdWNlZC1tb3Rpb246cmVkdWNlKXsqe3RyYW5zaXRpb246bm9uZSFpbXBvcnRhbnR9fQo8L3N0eWxlPgo8L2hl"
    "YWQ+Cjxib2R5Pgo8aGVhZGVyIGNsYXNzPSJ0b3AiPjxkaXYgY2xhc3M9IndyYXAiPjxkaXYgY2xhc3M9ImJyYW5kIj5zZWJiaTxi"
    "Pi5wcm88L2I+PC9kaXY+CjxuYXY+PGEgaHJlZj0iLyI+SG9tZTwvYT48YSBocmVmPSIja2l0Ij5LaXQ8L2E+PGEgaHJlZj0iL21h"
    "cCI+TWFwPC9hPjxhIGhyZWY9Ii93aGl0ZXBhcGVyIj5XaGl0ZXBhcGVyPC9hPjwvbmF2PjwvZGl2PjwvaGVhZGVyPgoKPGRpdiBj"
    "bGFzcz0id3JhcCI+CjxkaXYgY2xhc3M9Imhlcm8iPgogIDxkaXYgY2xhc3M9ImtpY2siPkFHRU5UIFBBU1NQT1JUPC9kaXY+CiAg"
    "PGgxPkV2ZXJ5IEFJIGFnZW50IG5vdyBuZWVkcyBhIHBhc3Nwb3J0LjwvaDE+CiAgPHA+QUkgYWdlbnRzIHBheSwgYm9vaywgc2Vu"
    "ZCBhbmQgY2hhbmdlIHJlY29yZHMgb24gdGhlaXIgb3duLiBUaGUgQWdlbnQgUGFzc3BvcnQgbGV0cyBhbnkgc2l0ZSBrbm93LCBp"
    "biBtaWxsaXNlY29uZHMsIHRoYXQgYSByZWFsIHBlcnNvbiBhdXRob3Jpc2VkIHRoZSBhY3Rpb24sIHRoYXQgdGhlIGF1dGhvcml0"
    "eSBzdGlsbCBzdGFuZHMgcmlnaHQgbm93LCBhbmQgdGhhdCBpdCBjYW4gaGFwcGVuIGV4YWN0bHkgb25jZS48L3A+CiAgPGJ1dHRv"
    "biBjbGFzcz0iY3RhIGdvbGQiIG9uY2xpY2s9InJ1bkRlbW8oKSI+UnVuIGl0IGxpdmU8L2J1dHRvbj4KICA8YSBjbGFzcz0iY3Rh"
    "IGdob3N0IiBocmVmPSIja2l0Ij5HZXQgdGhlIGtpdDwvYT4KICA8ZGl2IGNsYXNzPSJzdGF0cyI+PGRpdj48YiBpZD0icy1pc3N1"
    "ZWQiPuKAlDwvYj5wYXNzcG9ydHMgaXNzdWVkPC9kaXY+PGRpdj48YiBpZD0icy1yZWQiPuKAlDwvYj5yZWRlZW1lZDwvZGl2Pjxk"
    "aXY+PGIgaWQ9InMtcmVmIj7igJQ8L2I+cmVmdXNlZCBhbmQgc2VhbGVkPC9kaXY+PC9kaXY+CjwvZGl2PgoKPHNlY3Rpb24+CiAg"
    "PGgyPlRocmVlIHN0ZXBzLiBObyB0cnVzdCByZXF1aXJlZC48L2gyPgogIDxkaXYgY2xhc3M9InN0ZXBzIj4KICAgIDxkaXYgY2xh"
    "c3M9InN0ZXAiPjxkaXYgY2xhc3M9Im4iPjAxIMK3IFRIRSBBR0VOVCBBU0tTPC9kaXY+PGgzPkF1dGhvcml0eSB0cmFjZWQgYmFj"
    "ayB0byBhIGh1bWFuPC9oMz48cD5CZWZvcmUgYWN0aW5nLCB0aGUgYWdlbnQgYXNrcyBzZWJiaS5wcm8uIFRoZSBhdXRob3JpdHkg"
    "aXMgd2Fsa2VkIGJhY2sgdG8gdGhlIHBlcnNvbiB3aG8gZ3JhbnRlZCBpdCwgZXZlcnkgbGluayBjaGVja2VkLCBhbmQgYSBzaWdu"
    "ZWQgcGFzc3BvcnQgaXNzdWVkIGZvciBvbmUgYWN0aW9uLCBhdCBvbmUgc2l0ZSwgZm9yIG9uZSBhbW91bnQsIGZvciBtaW51dGVz"
    "LjwvcD48L2Rpdj4KICAgIDxkaXYgY2xhc3M9InN0ZXAiPjxkaXYgY2xhc3M9Im4iPjAyIMK3IFRIRSBTSVRFIENIRUNLUzwvZGl2"
    "PjxoMz5WZXJpZmllZCBpbiBtaWxsaXNlY29uZHMsIG9mZmxpbmU8L2gzPjxwPlRoZSBzaXRlIGNoZWNrcyB0aGUgc2lnbmF0dXJl"
    "IHdpdGggYSBzdGFuZGFyZCBsaWJyYXJ5IGluIGFueSBsYW5ndWFnZS4gTm90aGluZyB0byBpbnN0YWxsLCBubyBhY2NvdW50LCBu"
    "byBjYWxsIGhvbWUuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+MDMgwrcgVEhFIEFDVElP"
    "TiBCSU5EUzwvZGl2PjxoMz5SZS1jaGVja2VkIGF0IHRoZSBtb21lbnQgaXQgaGFwcGVuczwvaDM+PHA+VGhlIHNpdGUgcmVkZWVt"
    "cyB0aGUgcGFzc3BvcnQuIFJpZ2h0IHRoZW4sIHNlYmJpLnBybyBjb25maXJtcyB0aGUgaHVtYW4ncyBhdXRob3JpdHkgc3RpbGwg"
    "c3RhbmRzLCB0aGUgYW1vdW50IG1hdGNoZXMsIGFuZCBpdCBoYXMgbmV2ZXIgYmVlbiB1c2VkLiBUaGVuIGl0IGJpbmRzLCBvbmNl"
    "LCBhbmQgdGhlIG91dGNvbWUgaXMgc2VhbGVkLjwvcD48L2Rpdj4KICA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gc3R5bGU9"
    "ImJvcmRlci10b3A6MCI+CjxkaXYgY2xhc3M9ImRhcmsiPgogIDxoMj5XYXRjaCBpdCBydW4gb24gcHJvZHVjdGlvbi48L2gyPgog"
    "IDxwIGNsYXNzPSJsZWFkIj5PbmUgdGFwIHJ1bnMgdGhlIHdob2xlIHN0b3J5IGxpdmU6IGEgcmVhbCBncmFudCwgcmVhbCBwYXNz"
    "cG9ydHMsIHJlYWwgcmVkZW1wdGlvbnMgYW5kIHJlYWwgcmVmdXNhbHMsIGVhY2ggc2VhbGVkIGludG8gdGhlIHB1YmxpYyBjaGFp"
    "bi48L3A+CiAgPGJ1dHRvbiBjbGFzcz0iY3RhIHJ1biIgaWQ9InJ1bmJ0biIgb25jbGljaz0icnVuRGVtbygpIj5SdW4gdGhlIGxp"
    "dmUgZGVtbzwvYnV0dG9uPgogIDxkaXYgaWQ9InN0b3J5Ij48L2Rpdj4KICA8ZGl2IGlkPSJ2ZXJkaWN0Ij48L2Rpdj4KPC9kaXY+"
    "Cjwvc2VjdGlvbj4KCjxzZWN0aW9uPgogIDxoMj5XaGF0IGEgcGFzc3BvcnQgcmVmdXNlczwvaDI+CiAgPHAgY2xhc3M9ImxlYWQi"
    "PkEgc3RvbGVuLCByZXBsYXllZCwgcmUtYWltZWQgb3IgZWRpdGVkIHBhc3Nwb3J0IGlzIHdvcnRobGVzcy4gRXZlcnkgcmVmdXNh"
    "bCBpcyB3cml0dGVuIHRvIHRoZSBjaGFpbiwgc28gYW4gYWdlbnQgY2FuIGV2ZW4gcHJvdmUgaXQgd2FzIDxiPm5vdDwvYj4gYWxs"
    "b3dlZC48L3A+CiAgPGRpdiBjbGFzcz0ic3RlcHMiPgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+UkVQTEFZ"
    "PC9kaXY+PHA+U3BlbnQgb25jZS4gVGhlIHNlY29uZCBhdHRlbXB0IGlzIHJlZnVzZWQuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFz"
    "cz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+UkVWT0tFRCBBIFNFQ09ORCBBR088L2Rpdj48cD5TdGlsbCBzaWduZWQsIHN0aWxsIGlu"
    "IGRhdGUsIGFuZCBzdGlsbCByZWZ1c2VkLCBiZWNhdXNlIHRoZSBodW1hbiBwdWxsZWQgdGhlIGF1dGhvcml0eS48L3A+PC9kaXY+"
    "CiAgICA8ZGl2IGNsYXNzPSJzdGVwIj48ZGl2IGNsYXNzPSJuIj5XUk9ORyBTSVRFPC9kaXY+PHA+QSBwYXNzcG9ydCBpcyBvbmx5"
    "IGdvb2Qgd2hlcmUgaXQgd2FzIGlzc3VlZCBmb3IuPC9wPjwvZGl2PgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0i"
    "biI+RURJVEVEIEFNT1VOVDwvZGl2PjxwPkF1dGhvcmlzZWQgZm9yIDIwLCBwcmVzZW50ZWQgZm9yIDQ5LiBSZWZ1c2VkLjwvcD48"
    "L2Rpdj4KICA8L2Rpdj4KPC9zZWN0aW9uPgoKPHNlY3Rpb24gaWQ9ImtpdCI+CiAgPGgyPkdldCB0aGUga2l0LiBPbmUgbGluZSBv"
    "biBlYWNoIHNpZGUuPC9oMj4KICA8cCBjbGFzcz0ibGVhZCI+VHdvIHNpbmdsZSBmaWxlcywgc3RhbmRhcmQgUHl0aG9uLCBub3Ro"
    "aW5nIHRvIGluc3RhbGwuIFRlc3RlZCBlbmQgdG8gZW5kOiB0aGUgb2ZmbGluZSBwYXNzcG9ydCBjaGVjayBydW5zIGluIGFib3V0"
    "IDUgbWlsbGlzZWNvbmRzLjwvcD4KICA8ZGl2IGNsYXNzPSJncmlkMiI+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNz"
    "PSJ0YWciPkZPUiBBR0VOVCBCVUlMREVSUyDCtyBzZWJiaV9hZ2VudC5weTwvZGl2PjxoMz5Zb3VyIGFnZW50IGNhcnJpZXMgYSBw"
    "YXNzcG9ydDwvaDM+PHA+UHV0IG9uZSBsaW5lIGFib3ZlIGFueSBhY3Rpb24uIFRoZSBwYXNzcG9ydCBpcyBmZXRjaGVkIGJlZm9y"
    "ZSBpdCBydW5zLiBJZiBzZWJiaS5wcm8gcmVmdXNlcywgdGhlIGFjdGlvbiBuZXZlciBoYXBwZW5zLjwvcD4KPHByZT5AbmVlZHNf"
    "cGFzc3BvcnQoInBheW1lbnRzLnNlbmQiLAogICAgYXVkaWVuY2U9InNob3AuZXhhbXBsZS5jb20iLAogICAgcGFyYW1zPVsiYW1v"
    "dW50Il0pCmRlZiBwYXkoYW1vdW50LCBwYXNzcG9ydD1Ob25lKToKICAgIC4uLjwvcHJlPgogICAgICA8YSBjbGFzcz0iY3RhIGdv"
    "bGQiIHN0eWxlPSJtYXJnaW4tdG9wOjE0cHgiIGhyZWY9Ii9wYXNzcG9ydC9zZWJiaV9hZ2VudC5weSIgZG93bmxvYWQ+RG93bmxv"
    "YWQgc2ViYmlfYWdlbnQucHk8L2E+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0YWciPkZPUiBXRUJT"
    "SVRFUyAmYW1wOyBBUElTIMK3IHNlYmJpX3NpdGUucHk8L2Rpdj48aDM+WW91ciBzaXRlIGNoZWNrcyBldmVyeSBhZ2VudDwvaDM+"
    "PHA+T25lIGxpbmUgYmVmb3JlIGFueSBhY3Rpb24gYW4gYWdlbnQgYXNrcyBmb3IuIFRoZSBzaWduYXR1cmUgaXMgY2hlY2tlZCBv"
    "biB5b3VyIG93biBzZXJ2ZXIsIHRoZW4gdGhlIHBhc3Nwb3J0IGlzIHNwZW50IG9uY2UgYXQgdGhlIG1vbWVudCBvZiBhY3Rpb24u"
    "PC9wPgo8cHJlPnBhc3Nwb3J0ID0gYWNjZXB0KHJlcXVlc3QuaGVhZGVycywKICAgIGF1ZGllbmNlPSJzaG9wLmV4YW1wbGUuY29t"
    "IiwKICAgIHBhcmFtcz17ImFtb3VudCI6IGFtb3VudH0pCiMgc3RpbGwgaGVyZSA9IHNhZmUgdG8gYWN0PC9wcmU+CiAgICAgIDxh"
    "IGNsYXNzPSJjdGEgZ29sZCIgc3R5bGU9Im1hcmdpbi10b3A6MTRweCIgaHJlZj0iL3Bhc3Nwb3J0L3NlYmJpX3NpdGUucHkiIGRv"
    "d25sb2FkPkRvd25sb2FkIHNlYmJpX3NpdGUucHk8L2E+PC9kaXY+CiAgPC9kaXY+CiAgPGRpdiBjbGFzcz0ic3RlcHMiIHN0eWxl"
    "PSJtYXJnaW4tdG9wOjE0cHgiPgogICAgPGRpdiBjbGFzcz0ic3RlcCI+PGRpdiBjbGFzcz0ibiI+VEVTVEVEIEVORCBUTyBFTkQ8"
    "L2Rpdj48cD5QYWlkIDIwIGluIG9uZSBsaW5lOiBib3VuZC4gUmVwbGF5ZWQ6IHJlamVjdGVkLiBBc2tlZCBmb3IgNTAwIG9uIGEg"
    "MTAwIGxpbWl0OiByZWZ1c2VkIGJlZm9yZSBhIHBhc3Nwb3J0IGV4aXN0ZWQuIFdyb25nIHNpdGUsIHRhbXBlcmVkIHRva2VuLCAy"
    "MCBlZGl0ZWQgdG8gOTk6IGFsbCByZWplY3RlZC48L3A+PC9kaXY+CiAgPC9kaXY+Cjwvc2VjdGlvbj4KCjxzZWN0aW9uIGlkPSJz"
    "aXRlcyI+CiAgPGgyPkJ1aWx0IGZvciBib3RoIHNpZGVzIG9mIHRoZSBhY3Rpb248L2gyPgogIDxkaXYgY2xhc3M9ImdyaWQyIj4K"
    "ICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRhZyI+Rk9SIFdFQlNJVEVTICZhbXA7IEFQSVM8L2Rpdj48aDM+UmVx"
    "dWlyZSBpdCB3aXRoIG9uZSBmaWxlPC9oMz48cD5Ib3N0IG9uZSBzbWFsbCBmaWxlIGFuZCBldmVyeSBhZ2VudCBrbm93cyB3aGlj"
    "aCBhY3Rpb25zIG5lZWQgYSBwYXNzcG9ydC4gTm8gcGFzc3BvcnQsIG5vIGFjdGlvbi48L3A+CiAgICAgIDxhIGhyZWY9Imh0dHBz"
    "Oi8vc2ViYmkucHJvL3gvcGFzc3BvcnQvc2l0ZWZpbGU/ZG9tYWluPXlvdXIuc2l0ZSZyZXF1aXJlPXBheW1lbnRzLioiPkdlbmVy"
    "YXRlIHlvdXIgZmlsZTwvYT48L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImNhcmQiPjxkaXYgY2xhc3M9InRhZyI+Rk9SIEFJIEFHRU5U"
    "UzwvZGl2PjxoMz5BIHRvb2wsIHRocm91Z2ggTUNQPC9oMz48cD5BZ2VudHMgcmVxdWVzdCwgY2hlY2sgYW5kIHJlZGVlbSBwYXNz"
    "cG9ydHMgYXMgdG9vbHMuIFdvcmtzIHdpdGggZXZlcnkgbW9kZWwgZnJvbSBldmVyeSB2ZW5kb3IuPC9wPgogICAgICA8YSBocmVm"
    "PSJodHRwczovL3NlYmJpLnByby94L3Bhc3Nwb3J0L21jcCI+aHR0cHM6Ly9zZWJiaS5wcm8veC9wYXNzcG9ydC9tY3A8L2E+PC9k"
    "aXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0YWciPkZPUiBDT01QTElBTkNFPC9kaXY+PGgzPlByb29mLCBu"
    "b3QgbG9nczwvaDM+PHA+V2hvIGF1dGhvcmlzZWQgaXQsIHdobyBhY3RlZCwgd2hvIGFjY2VwdHMgdGhlIHJpc2ssIGFuZCB3aGV0"
    "aGVyIGl0IHN0aWxsIHN0b29kIGF0IHRoYXQgaW5zdGFudC4gU2VhbGVkLCBhbmNob3JlZCB0byBCaXRjb2luLCB3aXRuZXNzZWQg"
    "aW5kZXBlbmRlbnRseS48L3A+CiAgICAgIDxhIGhyZWY9Imh0dHBzOi8vc2ViYmkucHJvL3gvY29udGludWl0eS9kZWNpc2lvbnMi"
    "PlNlZSByZWFsIHNlYWxlZCBkZWNpc2lvbnM8L2E+PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIj48ZGl2IGNsYXNzPSJ0YWci"
    "PkZPUiBERVZFTE9QRVJTPC9kaXY+PGgzPkFuIG9wZW4gdG9rZW4gZm9ybWF0PC9oMz48cD5FZDI1NTE5LCBjYW5vbmljYWwgSlNP"
    "Tiwgb25lIHByZWZpeC4gVXNlIG91ciBraXQgb3IgYW55IEVkMjU1MTkgbGlicmFyeSBpbiBhbnkgbGFuZ3VhZ2UuPC9wPgogICAg"
    "ICA8YSBocmVmPSJodHRwczovL3NlYmJpLnByby94L3Bhc3Nwb3J0L3NwZWMiPlJlYWQgdGhlIHNwZWM8L2E+PC9kaXY+CiAgPC9k"
    "aXY+CjxwcmU+QWdlbnQtUGFzc3BvcnQ6IHNicDEuZXlKaFkzUWlPaUprWlcxdkxuQmhlU0lzSW1GMVpDSTZJbk5vYjNBdeKApjwv"
    "cHJlPgo8L3NlY3Rpb24+Cgo8ZGl2IGNsYXNzPSJjbG9zZSI+CiAgPGgyPklmIHlvdXIgYWdlbnRzIHRvdWNoIG1vbmV5LCByZWNv"
    "cmRzIG9yIGN1c3RvbWVycywgdGhpcyBpcyBmb3IgeW91LjwvaDI+CiAgPHA+RnJlZSBmb3IgOTAgZGF5cywgdGhlbiA1MHAgcGVy"
    "IGRldmljZSBwZXIgbW9udGguIFRlbGwgdXMgd2hhdCB5b3VyIGFnZW50cyBkbyBhbmQgd2UnbGwgc2hvdyB5b3UgaG93IHRoZSBw"
    "YXNzcG9ydCBwbHVncyBpbnRvIHlvdXIgc3RhY2suPC9wPgogIDxhIGNsYXNzPSJjdGEgZ29sZCIgaHJlZj0ibWFpbHRvOmp1c3Ry"
    "aWdodGRlY29yYXRvcnNAZ21haWwuY29tP3N1YmplY3Q9QWdlbnQlMjBQYXNzcG9ydCI+VGFsayB0byB1czwvYT4KICA8YSBjbGFz"
    "cz0iY3RhIGdob3N0IiBocmVmPSIvbWFwIiBzdHlsZT0iYmFja2dyb3VuZDp0cmFuc3BhcmVudDtjb2xvcjojZmZmO2JvcmRlci1j"
    "b2xvcjpyZ2JhKDI1NSwyNTUsMjU1LC4zKSI+U2VlIHdoZXJlIGl0IHNpdHM8L2E+CjwvZGl2Pgo8L2Rpdj4KCjxmb290ZXI+PGRp"
    "diBjbGFzcz0id3JhcCI+c2ViYmkucHJvIMK3IE1vbm9wIENvbnRlbnQgwrcgQmx5dGgsIE5vcnRodW1iZXJsYW5kLCBVSzxicj5U"
    "aGUgdHJ1c3QgbGF5ZXIgYmV0d2VlbiBtYWNoaW5lcyB0aGF0IGFjdCBhbmQgdGhlIHdvcmxkIHRoZXkgYWN0IG9uLjwvZGl2Pjwv"
    "Zm9vdGVyPgoKPHNjcmlwdD4KZnVuY3Rpb24gZXNjKHMpe3JldHVybiBTdHJpbmcocz09bnVsbD8nJzpzKS5yZXBsYWNlKC9bJjw+"
    "Il0vZyxmdW5jdGlvbihjKXtyZXR1cm57JyYnOicmYW1wOycsJzwnOicmbHQ7JywnPic6JyZndDsnLCciJzonJnF1b3Q7J31bY119"
    "KX0KZnVuY3Rpb24gc3RhdHMoKXtmZXRjaCgnL3gvcGFzc3BvcnQvc3RhdHVzJykudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5q"
    "c29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpewogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtaXNzdWVkJykudGV4dENvbnRlbnQ9"
    "ZC5wYXNzcG9ydHNfaXNzdWVkO2RvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLXJlZCcpLnRleHRDb250ZW50PWQucmVkZWVtZWQ7"
    "ZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtcmVmJykudGV4dENvbnRlbnQ9ZC5yZWZ1c2VkfSkuY2F0Y2goZnVuY3Rpb24oKXt9"
    "KX0Kc3RhdHMoKTsKZnVuY3Rpb24gcnVuRGVtbygpewogdmFyIGJveD1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RvcnknKSx2"
    "PWRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZXJkaWN0JyksYj1kb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncnVuYnRuJyk7CiBk"
    "b2N1bWVudC5xdWVyeVNlbGVjdG9yKCcuZGFyaycpLnNjcm9sbEludG9WaWV3KHtiZWhhdmlvcjonc21vb3RoJ30pOwogYm94Lmlu"
    "bmVySFRNTD0nJzt2LnRleHRDb250ZW50PSdSdW5uaW5nIG9uIHByb2R1Y3Rpb27igKYnO2IuZGlzYWJsZWQ9dHJ1ZTsKIGZldGNo"
    "KCcveC9wYXNzcG9ydC9kZW1vJykudGhlbihmdW5jdGlvbihyKXtyZXR1cm4gci5qc29uKCl9KS50aGVuKGZ1bmN0aW9uKGQpewog"
    "IGlmKGQuZXJyb3I9PT0ndG9vX3Nvb24nKXt2LnRleHRDb250ZW50PSdTb21lb25lIGp1c3QgcmFuIGl0LiBUcnkgYWdhaW4gaW4g"
    "JytkLnJldHJ5X2FmdGVyX3NlY29uZHMrJyBzZWNvbmRzLic7Yi5kaXNhYmxlZD1mYWxzZTtyZXR1cm59CiAgaWYoIWQuc3Rvcnkp"
    "e3YudGV4dENvbnRlbnQ9J0RlbW8gdW5hdmFpbGFibGUgcmlnaHQgbm93Lic7Yi5kaXNhYmxlZD1mYWxzZTtyZXR1cm59CiAgZC5z"
    "dG9yeS5mb3JFYWNoKGZ1bmN0aW9uKHMsaSl7CiAgIHZhciBraW5kPSdpbmZvJyxsYWJlbD0nU0VBTEVEJzsKICAgaWYocy5yZWRl"
    "ZW1lZD09PXRydWV8fHMudmFsaWQ9PT10cnVlfHxzLmlzc3VlZD09PXRydWUpe2tpbmQ9J3Bhc3MnO2xhYmVsPXMucmVkZWVtZWQ9"
    "PT10cnVlPydCT1VORCc6KHMudmFsaWQ9PT10cnVlPydWQUxJRCc6J0lTU1VFRCcpfQogICBpZihzLnJlZGVlbWVkPT09ZmFsc2V8"
    "fHMudmFsaWQ9PT1mYWxzZXx8cy5pc3N1ZWQ9PT1mYWxzZSl7a2luZD0nc3RvcCc7bGFiZWw9J1JFRlVTRUQnfQogICB2YXIgd2h5"
    "PXMud2h5JiZzLndoeS5sZW5ndGg/JzxzcGFuIGNsYXNzPSJ3aHkiPicrZXNjKHMud2h5WzBdKSsnPC9zcGFuPic6Jyc7CiAgIHZh"
    "ciBlbD1kb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTtlbC5jbGFzc05hbWU9J3Jvdyc7CiAgIGVsLmlubmVySFRNTD0nPHNw"
    "YW4gY2xhc3M9ImljICcra2luZCsnIj4nK2xhYmVsKyc8L3NwYW4+PGRpdj4nK2VzYyhzLmFjdCkrd2h5Kyc8L2Rpdj4nOwogICBi"
    "b3guYXBwZW5kQ2hpbGQoZWwpO3NldFRpbWVvdXQoZnVuY3Rpb24oKXtlbC5jbGFzc0xpc3QuYWRkKCdzaG93Jyl9LDE2MCppKzYw"
    "KX0pOwogIHNldFRpbWVvdXQoZnVuY3Rpb24oKXt2LnRleHRDb250ZW50PWQucmVzdWx0PT09J0FMTCBURU4gQkVIQVZFRCc/J+Kc"
    "kyBBbGwgdGVuIGJlaGF2ZWQuIEV2ZXJ5IHN0ZXAgaXMgb24gdGhlIGNoYWluLic6ZC5yZXN1bHQ7Yi5kaXNhYmxlZD1mYWxzZTtz"
    "dGF0cygpfSwxNjAqZC5zdG9yeS5sZW5ndGgrMzAwKTsKIH0pLmNhdGNoKGZ1bmN0aW9uKCl7di50ZXh0Q29udGVudD0nQ291bGQg"
    "bm90IHJlYWNoIHRoZSBkZW1vLic7Yi5kaXNhYmxlZD1mYWxzZX0pOwp9Cjwvc2NyaXB0Pgo8L2JvZHk+CjwvaHRtbD4K"
)

_AGENT_B64 = (
    "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiIKc2ViYmlfYWdlbnQucHkgIC0gIGdpdmUgYW55IEFJIGFnZW50IGFuIEFnZW50IFBh"
    "c3Nwb3J0IGluIG9uZSBsaW5lCj09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09"
    "PT09PT09PT09PQoKICAgIGZyb20gc2ViYmlfYWdlbnQgaW1wb3J0IG5lZWRzX3Bhc3Nwb3J0CgogICAgQG5lZWRzX3Bhc3Nwb3J0"
    "KCJwYXltZW50cy5zZW5kIiwgYXVkaWVuY2U9InNob3AuZXhhbXBsZS5jb20iLAogICAgICAgICAgICAgICAgICAgIGdyYW50PSJn"
    "X3lvdXJfZ3JhbnRfaWQiLCBwYXJhbXM9WyJhbW91bnQiXSkKICAgIGRlZiBwYXkoYW1vdW50LCBwYXNzcG9ydD1Ob25lKToKICAg"
    "ICAgICAjIHBhc3Nwb3J0IGlzIGEgc2lnbmVkIHRva2VuLiBTZW5kIGl0IHdpdGggdGhlIHJlcXVlc3Q6CiAgICAgICAgIyAgIGhl"
    "YWRlcnMgPSB7IkFnZW50LVBhc3Nwb3J0IjogcGFzc3BvcnR9CiAgICAgICAgLi4uCgogICAgcGF5KGFtb3VudD0yMCkKCkJlZm9y"
    "ZSB0aGUgZnVuY3Rpb24gcnVucywgc2ViYmkucHJvIHRyYWNlcyB0aGUgYWdlbnQncyBhdXRob3JpdHkgYmFjayB0byB0aGUKaHVt"
    "YW4gd2hvIGdyYW50ZWQgaXQgYW5kIGlzc3VlcyBhIHBhc3Nwb3J0IGZvciBleGFjdGx5IHRoaXMgYWN0aW9uLCBhdCB0aGlzCnNp"
    "dGUsIHdpdGggdGhlc2UgcGFyYW1ldGVycy4gSWYgc2ViYmkucHJvIHJlZnVzZXMsIHRoZSBmdW5jdGlvbiBuZXZlciBydW5zIGFu"
    "ZApQYXNzcG9ydFJlZnVzZWQgaXMgcmFpc2VkIHdpdGggdGhlIHJlYXNvbnMgYW5kIGEgbGluayB0byB0aGUgc2VhbGVkIHJlZnVz"
    "YWwuCgpGYWlscyBjbG9zZWQ6IGlmIHNlYmJpLnBybyBjYW5ub3QgYmUgcmVhY2hlZCwgdGhlIGFjdGlvbiBkb2VzIG5vdCBoYXBw"
    "ZW4uCgpOZWVkcyB5b3VyIHNlYmJpLnBybyBBUEkga2V5IGluIHRoZSBTRUJCSV9LRVkgZW52aXJvbm1lbnQgdmFyaWFibGUuClN0"
    "YW5kYXJkIGxpYnJhcnkgb25seS4gT25lIGZpbGUuIFB5dGhvbiAzLjgrLgoKQ29tbWFuZCBsaW5lOgogICAgcHl0aG9uIHNlYmJp"
    "X2FnZW50LnB5IHJlcXVlc3QgLS1ncmFudCBHIC0tYWN0aW9uIHBheW1lbnRzLnNlbmQgXFwKICAgICAgICAtLWF1ZGllbmNlIHNo"
    "b3AuZXhhbXBsZS5jb20gLS1wYXJhbXMgJ3siYW1vdW50IjogMjB9JwoiIiIKCmltcG9ydCBmdW5jdG9vbHMKaW1wb3J0IGluc3Bl"
    "Y3QKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmltcG9ydCBzeXMKaW1wb3J0IHRocmVhZGluZwppbXBvcnQgdXJsbGliLmVycm9yCmlt"
    "cG9ydCB1cmxsaWIucmVxdWVzdAoKX192ZXJzaW9uX18gPSAiMS4wLjAiCgpCQVNFID0gb3MuZW52aXJvbi5nZXQoIlNFQkJJX0JB"
    "U0UiLCAiaHR0cHM6Ly9zZWJiaS5wcm8iKS5yc3RyaXAoIi8iKQpIRUFERVIgPSAiQWdlbnQtUGFzc3BvcnQiClRJTUVPVVQgPSAx"
    "MAoKX2xvY2FsID0gdGhyZWFkaW5nLmxvY2FsKCkKCgpjbGFzcyBQYXNzcG9ydEVycm9yKEV4Y2VwdGlvbik6CiAgICAiIiJCYXNl"
    "IGNsYXNzLiBUaGUgYWN0aW9uIGRpZCBub3QgaGFwcGVuLiIiIgoKCmNsYXNzIFBhc3Nwb3J0UmVmdXNlZChQYXNzcG9ydEVycm9y"
    "KToKICAgICIiInNlYmJpLnBybyBldmFsdWF0ZWQgdGhlIHJlcXVlc3QgYW5kIGRpZCBub3QgaXNzdWUgYSBwYXNzcG9ydC4iIiIK"
    "CiAgICBkZWYgX19pbml0X18oc2VsZiwgdmVyZGljdCwgcmVhc29ucywgcHJvb2Y9Tm9uZSk6CiAgICAgICAgc2VsZi52ZXJkaWN0"
    "LCBzZWxmLnJlYXNvbnMsIHNlbGYucHJvb2YgPSB2ZXJkaWN0LCByZWFzb25zLCBwcm9vZgogICAgICAgIG1zZyA9ICIlczogJXMi"
    "ICUgKHZlcmRpY3QsICI7ICIuam9pbihyZWFzb25zKSBpZiByZWFzb25zIGVsc2UgIm5vIHJlYXNvbiBnaXZlbiIpCiAgICAgICAg"
    "aWYgcHJvb2Y6CiAgICAgICAgICAgIG1zZyArPSAiIChzZWFsZWQgcmVmdXNhbDogJXMpIiAlIHByb29mCiAgICAgICAgc3VwZXIo"
    "KS5fX2luaXRfXyhtc2cpCgoKY2xhc3MgUGFzc3BvcnRVbmF2YWlsYWJsZShQYXNzcG9ydEVycm9yKToKICAgICIiInNlYmJpLnBy"
    "byBjb3VsZCBub3QgYmUgcmVhY2hlZCBvciBhbnN3ZXJlZCB3aXRoIGFuIGVycm9yLiBGYWlscyBjbG9zZWQuIiIiCgoKZGVmIF9w"
    "b3N0KHBhdGgsIGJvZHksIGtleSk6CiAgICByZXEgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KAogICAgICAgIEJBU0UgKyBwYXRo"
    "LCBkYXRhPWpzb24uZHVtcHMoYm9keSkuZW5jb2RlKCJ1dGYtOCIpLCBtZXRob2Q9IlBPU1QiLAogICAgICAgIGhlYWRlcnM9eyJD"
    "b250ZW50LVR5cGUiOiAiYXBwbGljYXRpb24vanNvbiIsICJBdXRob3JpemF0aW9uIjogIkJlYXJlciAiICsga2V5LAogICAgICAg"
    "ICAgICAgICAgICJVc2VyLUFnZW50IjogInNlYmJpLWFnZW50LyIgKyBfX3ZlcnNpb25fX30pCiAgICB0cnk6CiAgICAgICAgd2l0"
    "aCB1cmxsaWIucmVxdWVzdC51cmxvcGVuKHJlcSwgdGltZW91dD1USU1FT1VUKSBhcyByOgogICAgICAgICAgICByZXR1cm4ganNv"
    "bi5sb2FkcyhyLnJlYWQoKS5kZWNvZGUoInV0Zi04IikpCiAgICBleGNlcHQgdXJsbGliLmVycm9yLkhUVFBFcnJvciBhcyBlOgog"
    "ICAgICAgIHRyeToKICAgICAgICAgICAgZGV0YWlsID0ganNvbi5sb2FkcyhlLnJlYWQoKS5kZWNvZGUoInV0Zi04IikpCiAgICAg"
    "ICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgZGV0YWlsID0geyJlcnJvciI6ICJodHRwXyVkIiAlIGUuY29kZX0KICAg"
    "ICAgICByYWlzZSBQYXNzcG9ydFVuYXZhaWxhYmxlKCJzZWJiaS5wcm8gYW5zd2VyZWQgJWQ6ICVzIiAlIChlLmNvZGUsIGRldGFp"
    "bCkpCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGU6CiAgICAgICAgcmFpc2UgUGFzc3BvcnRVbmF2YWlsYWJsZSgiY291bGQgbm90"
    "IHJlYWNoIHNlYmJpLnBybzogJXMiICUgZSkKCgpkZWYgcmVxdWVzdF9wYXNzcG9ydChncmFudCwgYWN0aW9uLCBhdWRpZW5jZSwg"
    "cGFyYW1zPU5vbmUsIHB1cnBvc2VfdGFnPU5vbmUsIGtleT1Ob25lKToKICAgICIiIkFzayBzZWJiaS5wcm8gZm9yIGEgcGFzc3Bv"
    "cnQuIFJldHVybnMgdGhlIHRva2VuIHN0cmluZyBvciByYWlzZXMuIiIiCiAgICBrZXkgPSBrZXkgb3Igb3MuZW52aXJvbi5nZXQo"
    "IlNFQkJJX0tFWSIsICIiKQogICAgaWYgbm90IGtleToKICAgICAgICByYWlzZSBQYXNzcG9ydFVuYXZhaWxhYmxlKCJzZXQgU0VC"
    "QklfS0VZIHRvIHlvdXIgc2ViYmkucHJvIEFQSSBrZXkiKQogICAgcmVzID0gX3Bvc3QoIi94L3Bhc3Nwb3J0L2lzc3VlIiwgeyJn"
    "cmFudCI6IGdyYW50LCAiYWN0aW9uIjogYWN0aW9uLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgImF1ZGll"
    "bmNlIjogYXVkaWVuY2UsICJwYXJhbXMiOiBwYXJhbXMgb3Ige30sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg"
    "ICAicHVycG9zZV90YWciOiBwdXJwb3NlX3RhZ30sIGtleSkKICAgIGlmIHJlcy5nZXQoImlzc3VlZCIpOgogICAgICAgIHJldHVy"
    "biByZXNbInBhc3Nwb3J0Il0KICAgIGlmICJ2ZXJkaWN0IiBpbiByZXM6CiAgICAgICAgcmFpc2UgUGFzc3BvcnRSZWZ1c2VkKHJl"
    "c1sidmVyZGljdCJdLCByZXMuZ2V0KCJyZWFzb25zIiwgW10pLAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICByZXMuZ2V0"
    "KCJwcm9vZl9vZl9yZWZ1c2FsIikpCiAgICByYWlzZSBQYXNzcG9ydFVuYXZhaWxhYmxlKCJ1bmV4cGVjdGVkIGFuc3dlcjogJXMi"
    "ICUgcmVzKQoKCmRlZiBjdXJyZW50X3Bhc3Nwb3J0KCk6CiAgICAiIiJUaGUgcGFzc3BvcnQgZm9yIHRoZSBhY3Rpb24gY3VycmVu"
    "dGx5IHJ1bm5pbmcgaW5zaWRlIEBuZWVkc19wYXNzcG9ydC4iIiIKICAgIHJldHVybiBnZXRhdHRyKF9sb2NhbCwgInRva2VuIiwg"
    "Tm9uZSkKCgpkZWYgaGVhZGVycyh0b2tlbj1Ob25lKToKICAgICIiIkhUVFAgaGVhZGVycyB0byBzZW5kIHdpdGggdGhlIGFjdGlv"
    "bi4iIiIKICAgIHJldHVybiB7SEVBREVSOiB0b2tlbiBvciBjdXJyZW50X3Bhc3Nwb3J0KCkgb3IgIiJ9CgoKZGVmIG5lZWRzX3Bh"
    "c3Nwb3J0KGFjdGlvbiwgYXVkaWVuY2UsIGdyYW50PU5vbmUsIHBhcmFtcz1Ob25lLCBwdXJwb3NlX3RhZz1Ob25lLCBrZXk9Tm9u"
    "ZSk6CiAgICAiIiJEZWNvcmF0b3IuIFRoZSB3cmFwcGVkIGZ1bmN0aW9uIHJ1bnMgb25seSBpZiBhIHBhc3Nwb3J0IGlzIGlzc3Vl"
    "ZC4KCiAgICBwYXJhbXM6IGxpc3Qgb2YgYXJndW1lbnQgbmFtZXMgd2hvc2UgdmFsdWVzIGRlZmluZSB0aGUgYWN0aW9uLCBlLmcu"
    "CiAgICAgICAgICAgIFsiYW1vdW50IiwgImN1cnJlbmN5Il0uIFRoZSBzaXRlIG11c3QgcmVkZWVtIHdpdGggdGhlIHNhbWUgdmFs"
    "dWVzLAogICAgICAgICAgICBzbyBhIHBhc3Nwb3J0IGZvciAyMCBjYW5ub3QgYmUgc3BlbnQgb24gNDkuCiAgICBncmFudDogIHRo"
    "ZSBncmFudCBpZC4gQ2FuIGFsc28gYmUgcGFzc2VkIGF0IGNhbGwgdGltZSBhcyBncmFudD0uLi4KICAgIFRoZSB0b2tlbiBpcyBo"
    "YW5kZWQgdG8gdGhlIGZ1bmN0aW9uIGFzIHBhc3Nwb3J0PS4uLiBpZiBpdCBhY2NlcHRzIHRoYXQKICAgIGFyZ3VtZW50LCBhbmQg"
    "aXMgYWx3YXlzIGF2YWlsYWJsZSB0aHJvdWdoIGN1cnJlbnRfcGFzc3BvcnQoKS4KICAgICIiIgogICAgbmFtZXMgPSBsaXN0KHBh"
    "cmFtcyBvciBbXSkKCiAgICBkZWYgd3JhcChmbik6CiAgICAgICAgc2lnID0gaW5zcGVjdC5zaWduYXR1cmUoZm4pCiAgICAgICAg"
    "dGFrZXNfcGFzc3BvcnQgPSAicGFzc3BvcnQiIGluIHNpZy5wYXJhbWV0ZXJzCgogICAgICAgIEBmdW5jdG9vbHMud3JhcHMoZm4p"
    "CiAgICAgICAgZGVmIGlubmVyKCphcmdzLCAqKmt3YXJncyk6CiAgICAgICAgICAgIGcgPSBrd2FyZ3MucG9wKCJncmFudCIsIE5v"
    "bmUpIGlmICJncmFudCIgbm90IGluIHNpZy5wYXJhbWV0ZXJzIGVsc2Uga3dhcmdzLmdldCgiZ3JhbnQiKQogICAgICAgICAgICBn"
    "ID0gZyBvciBncmFudCBvciBvcy5lbnZpcm9uLmdldCgiU0VCQklfR1JBTlQiKQogICAgICAgICAgICBpZiBub3QgZzoKICAgICAg"
    "ICAgICAgICAgIHJhaXNlIFBhc3Nwb3J0VW5hdmFpbGFibGUoIm5vIGdyYW50IGlkOiBwYXNzIGdyYW50PS4uLiBvciBzZXQgU0VC"
    "QklfR1JBTlQiKQogICAgICAgICAgICBib3VuZCA9IHNpZy5iaW5kX3BhcnRpYWwoKmFyZ3MsICoqa3dhcmdzKQogICAgICAgICAg"
    "ICBib3VuZC5hcHBseV9kZWZhdWx0cygpCiAgICAgICAgICAgIHAgPSB7bjogYm91bmQuYXJndW1lbnRzW25dIGZvciBuIGluIG5h"
    "bWVzIGlmIG4gaW4gYm91bmQuYXJndW1lbnRzfQogICAgICAgICAgICB0b2tlbiA9IHJlcXVlc3RfcGFzc3BvcnQoZywgYWN0aW9u"
    "LCBhdWRpZW5jZSwgcCwgcHVycG9zZV90YWcsIGtleSkKICAgICAgICAgICAgaWYgdGFrZXNfcGFzc3BvcnQ6CiAgICAgICAgICAg"
    "ICAgICBrd2FyZ3NbInBhc3Nwb3J0Il0gPSB0b2tlbgogICAgICAgICAgICBfbG9jYWwudG9rZW4gPSB0b2tlbgogICAgICAgICAg"
    "ICB0cnk6CiAgICAgICAgICAgICAgICByZXR1cm4gZm4oKmFyZ3MsICoqa3dhcmdzKQogICAgICAgICAgICBmaW5hbGx5OgogICAg"
    "ICAgICAgICAgICAgX2xvY2FsLnRva2VuID0gTm9uZQogICAgICAgIHJldHVybiBpbm5lcgogICAgcmV0dXJuIHdyYXAKCgpkZWYg"
    "X2NsaShhcmd2KToKICAgIGltcG9ydCBhcmdwYXJzZQogICAgYXAgPSBhcmdwYXJzZS5Bcmd1bWVudFBhcnNlcihwcm9nPSJzZWJi"
    "aV9hZ2VudCIpCiAgICBzdWIgPSBhcC5hZGRfc3VicGFyc2VycyhkZXN0PSJjbWQiKQogICAgciA9IHN1Yi5hZGRfcGFyc2VyKCJy"
    "ZXF1ZXN0IikKICAgIHIuYWRkX2FyZ3VtZW50KCItLWdyYW50IiwgcmVxdWlyZWQ9VHJ1ZSkKICAgIHIuYWRkX2FyZ3VtZW50KCIt"
    "LWFjdGlvbiIsIHJlcXVpcmVkPVRydWUpCiAgICByLmFkZF9hcmd1bWVudCgiLS1hdWRpZW5jZSIsIHJlcXVpcmVkPVRydWUpCiAg"
    "ICByLmFkZF9hcmd1bWVudCgiLS1wYXJhbXMiLCBkZWZhdWx0PSJ7fSIpCiAgICByLmFkZF9hcmd1bWVudCgiLS1wdXJwb3NlIiwg"
    "ZGVmYXVsdD1Ob25lKQogICAgYSA9IGFwLnBhcnNlX2FyZ3MoYXJndikKICAgIGlmIGEuY21kICE9ICJyZXF1ZXN0IjoKICAgICAg"
    "ICBhcC5wcmludF9oZWxwKCkKICAgICAgICByZXR1cm4gMgogICAgdHJ5OgogICAgICAgIHByaW50KHJlcXVlc3RfcGFzc3BvcnQo"
    "YS5ncmFudCwgYS5hY3Rpb24sIGEuYXVkaWVuY2UsIGpzb24ubG9hZHMoYS5wYXJhbXMpLCBhLnB1cnBvc2UpKQogICAgICAgIHJl"
    "dHVybiAwCiAgICBleGNlcHQgUGFzc3BvcnRFcnJvciBhcyBlOgogICAgICAgIHByaW50KCJSRUZVU0VEOiAlcyIgJSBlLCBmaWxl"
    "PXN5cy5zdGRlcnIpCiAgICAgICAgcmV0dXJuIDEKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgogICAgc3lzLmV4aXQoX2Ns"
    "aShzeXMuYXJndlsxOl0pKQo="
)

_SITE_B64 = (
    "IyEvdXNyL2Jpbi9lbnYgcHl0aG9uMwoiIiIKc2ViYmlfc2l0ZS5weSAgLSAgcmVxdWlyZSBhbiBBZ2VudCBQYXNzcG9ydCBvbiB5"
    "b3VyIHNpdGUgaW4gb25lIGxpbmUKPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09"
    "PT09PT09PT09PT09PT0KCiAgICBmcm9tIHNlYmJpX3NpdGUgaW1wb3J0IGFjY2VwdAoKICAgIGRlZiBoYW5kbGVfcGF5bWVudChy"
    "ZXF1ZXN0KToKICAgICAgICBwYXNzcG9ydCA9IGFjY2VwdChyZXF1ZXN0LmhlYWRlcnMsIGF1ZGllbmNlPSJzaG9wLmV4YW1wbGUu"
    "Y29tIiwKICAgICAgICAgICAgICAgICAgICAgICAgICBhY3Rpb249InBheW1lbnRzLnNlbmQiLAogICAgICAgICAgICAgICAgICAg"
    "ICAgICAgIHBhcmFtcz17ImFtb3VudCI6IHJlcXVlc3QuanNvblsiYW1vdW50Il19KQogICAgICAgICMgUmVhY2hpbmcgaGVyZSBt"
    "ZWFuczogYSBodW1hbiBhdXRob3Jpc2VkIHRoaXMgYWdlbnQsIHRoYXQgYXV0aG9yaXR5CiAgICAgICAgIyBzdGlsbCBzdGFuZHMg"
    "YXQgdGhpcyBpbnN0YW50LCB0aGUgYW1vdW50IGlzIGV4YWN0bHkgd2hhdCB3YXMKICAgICAgICAjIGF1dGhvcmlzZWQsIGFuZCB0"
    "aGlzIHBhc3Nwb3J0IGhhcyBuZXZlciBiZWVuIHVzZWQuIERvIHRoZSBhY3Rpb24uCiAgICAgICAgLi4uCgphY2NlcHQoKSBkb2Vz"
    "IHR3byB0aGluZ3M6CgogIDEuIENIRUNLLCBvbiB5b3VyIG93biBzZXJ2ZXIuIFRoZSBFZDI1NTE5IHNpZ25hdHVyZSBpcyB2ZXJp"
    "ZmllZCBhZ2FpbnN0CiAgICAgc2ViYmkucHJvJ3MgcHVibGlzaGVkIGtleSwgcGx1cyBleHBpcnksIHNpdGUgYW5kIGFjdGlvbi4g"
    "Tm90aGluZyBpcyBzZW50CiAgICAgYW55d2hlcmUgZm9yIHRoaXMgc3RlcC4gQSBmb3JnZWQsIGV4cGlyZWQgb3IgbWlzZGlyZWN0"
    "ZWQgcGFzc3BvcnQgaXMKICAgICB0dXJuZWQgYXdheSBiZWZvcmUgc2ViYmkucHJvIGlzIGV2ZXIgYXNrZWQuCiAgMi4gUkVERUVN"
    "LCBhdCB0aGUgbW9tZW50IG9mIGFjdGlvbi4gc2ViYmkucHJvIHJlLWNoZWNrcyB0aGUgaHVtYW4ncwogICAgIGF1dGhvcml0eSBy"
    "aWdodCBub3csIGNvbXBhcmVzIHRoZSBleGFjdCBwYXJhbWV0ZXJzLCBhbmQgbGV0cyB0aGUgcGFzc3BvcnQKICAgICBiaW5kIG9u"
    "Y2UuIFRoZSBvdXRjb21lIGlzIHNlYWxlZCBpbiBhIHB1YmxpYyBjaGFpbi4KCkFueXRoaW5nIHdyb25nIHJhaXNlcyBQYXNzcG9y"
    "dFJlamVjdGVkIC0gZG8gbm90IHBlcmZvcm0gdGhlIGFjdGlvbi4KCkZvciBhIGZ1bGx5IG9mZmxpbmUgc2lnbmF0dXJlIGNoZWNr"
    "LCBzZXQgU0VCQklfUFVCS0VZIHRvIHRoZSBoZXgga2V5IGZyb20KaHR0cHM6Ly9zZWJiaS5wcm8veC9jb250aW51aXR5L3B1Ymtl"
    "eS4gT3RoZXJ3aXNlIGl0IGlzIGZldGNoZWQgb25jZSBhbmQgY2FjaGVkLgoKU3RhbmRhcmQgbGlicmFyeSBvbmx5LiBPbmUgZmls"
    "ZS4gUHl0aG9uIDMuOCsuCgpDb21tYW5kIGxpbmU6CiAgICBweXRob24gc2ViYmlfc2l0ZS5weSBjaGVjayA8dG9rZW4+IFthdWRp"
    "ZW5jZV0KIiIiCgppbXBvcnQgYmFzZTY0CmltcG9ydCBoYXNobGliCmltcG9ydCBqc29uCmltcG9ydCBvcwppbXBvcnQgc3lzCmlt"
    "cG9ydCB0aW1lCmltcG9ydCB1cmxsaWIuZXJyb3IKaW1wb3J0IHVybGxpYi5yZXF1ZXN0CgpfX3ZlcnNpb25fXyA9ICIxLjAuMCIK"
    "CkJBU0UgPSBvcy5lbnZpcm9uLmdldCgiU0VCQklfQkFTRSIsICJodHRwczovL3NlYmJpLnBybyIpLnJzdHJpcCgiLyIpCkhFQURF"
    "UiA9ICJBZ2VudC1QYXNzcG9ydCIKUFJFRklYID0gYiJBSUxFQVNILVBBU1NQT1JULXYxOiIKVElNRU9VVCA9IDEwCgoKY2xhc3Mg"
    "UGFzc3BvcnRSZWplY3RlZChFeGNlcHRpb24pOgogICAgIiIiRG8gbm90IHBlcmZvcm0gdGhlIGFjdGlvbi4gLnJlYXNvbnMgbGlz"
    "dHMgd2h5LiIiIgoKICAgIGRlZiBfX2luaXRfXyhzZWxmLCByZWFzb25zLCBzZWFsZWQ9Tm9uZSk6CiAgICAgICAgc2VsZi5yZWFz"
    "b25zID0gcmVhc29ucyBpZiBpc2luc3RhbmNlKHJlYXNvbnMsIGxpc3QpIGVsc2UgW3N0cihyZWFzb25zKV0KICAgICAgICBzZWxm"
    "LnNlYWxlZCA9IHNlYWxlZAogICAgICAgIHN1cGVyKCkuX19pbml0X18oIjsgIi5qb2luKHNlbGYucmVhc29ucykpCgoKIyAtLS0t"
    "LS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tIEVkMjU1MTkKIyBSRkMg"
    "ODAzMiB2ZXJpZmljYXRpb24sIHN0YW5kYXJkIGxpYnJhcnkgb25seSwgc28gdGhlcmUgaXMgbm90aGluZyB0byBpbnN0YWxsLgoK"
    "X1EgPSAyICoqIDI1NSAtIDE5Cl9MID0gMiAqKiAyNTIgKyAyNzc0MjMxNzc3NzM3MjM1MzUzNTg1MTkzNzc5MDg4MzY0ODQ5Mwpf"
    "RCA9IC0xMjE2NjUgKiBwb3coMTIxNjY2LCBfUSAtIDIsIF9RKSAlIF9RCl9JID0gcG93KDIsIChfUSAtIDEpIC8vIDQsIF9RKQoK"
    "CmRlZiBfaW52KHgpOgogICAgcmV0dXJuIHBvdyh4LCBfUSAtIDIsIF9RKQoKCmRlZiBfeHJlYyh5KToKICAgIHh4ID0gKHkgKiB5"
    "IC0gMSkgKiBfaW52KF9EICogeSAqIHkgKyAxKQogICAgeCA9IHBvdyh4eCwgKF9RICsgMykgLy8gOCwgX1EpCiAgICBpZiAoeCAq"
    "IHggLSB4eCkgJSBfUToKICAgICAgICB4ID0geCAqIF9JICUgX1EKICAgIGlmIHggJSAyOgogICAgICAgIHggPSBfUSAtIHgKICAg"
    "IHJldHVybiB4CgoKX0JZID0gNCAqIF9pbnYoNSkgJSBfUQpfQlggPSBfeHJlYyhfQlkpCl9CID0gKF9CWCwgX0JZLCAxLCBfQlgg"
    "KiBfQlkgJSBfUSkKCgpkZWYgX2FkZChwLCBxKToKICAgIHgxLCB5MSwgejEsIHQxID0gcAogICAgeDIsIHkyLCB6MiwgdDIgPSBx"
    "CiAgICBhID0gKHkxIC0geDEpICogKHkyIC0geDIpICUgX1EKICAgIGIgPSAoeTEgKyB4MSkgKiAoeTIgKyB4MikgJSBfUQogICAg"
    "YyA9IHQxICogMiAqIF9EICogdDIgJSBfUQogICAgZCA9IHoxICogMiAqIHoyICUgX1EKICAgIGUsIGYsIGcsIGggPSBiIC0gYSwg"
    "ZCAtIGMsIGQgKyBjLCBiICsgYQogICAgcmV0dXJuIChlICogZiAlIF9RLCBnICogaCAlIF9RLCBmICogZyAlIF9RLCBlICogaCAl"
    "IF9RKQoKCmRlZiBfbXVsKHAsIG4pOgogICAgciA9ICgwLCAxLCAxLCAwKQogICAgd2hpbGUgbjoKICAgICAgICBpZiBuICYgMToK"
    "ICAgICAgICAgICAgciA9IF9hZGQociwgcCkKICAgICAgICBwID0gX2FkZChwLCBwKQogICAgICAgIG4gPj49IDEKICAgIHJldHVy"
    "biByCgoKZGVmIF9lbmMocCk6CiAgICB4LCB5LCB6LCBfID0gcAogICAgemkgPSBfaW52KHopCiAgICB4LCB5ID0geCAqIHppICUg"
    "X1EsIHkgKiB6aSAlIF9RCiAgICByZXR1cm4gKHkgfCAoKHggJiAxKSA8PCAyNTUpKS50b19ieXRlcygzMiwgImxpdHRsZSIpCgoK"
    "ZGVmIF9kZWMocyk6CiAgICB5ID0gaW50LmZyb21fYnl0ZXMocywgImxpdHRsZSIpICYgKCgxIDw8IDI1NSkgLSAxKQogICAgeCA9"
    "IF94cmVjKHkpCiAgICBpZiAoeCAmIDEpICE9IChzWzMxXSA+PiA3KToKICAgICAgICB4ID0gX1EgLSB4CiAgICBwID0gKHgsIHks"
    "IDEsIHggKiB5ICUgX1EpCiAgICB4LCB5LCB6LCB0ID0gcAogICAgaWYgKHkgKiB5IC0geCAqIHggLSB6ICogeiAtIF9EICogdCAq"
    "IHQpICUgX1E6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigicG9pbnQgb2ZmIGN1cnZlIikKICAgIHJldHVybiBwCgoKZGVmIF92"
    "ZXJpZnkoc2lnLCBtc2csIHBrKToKICAgIGlmIGxlbihzaWcpICE9IDY0IG9yIGxlbihwaykgIT0gMzI6CiAgICAgICAgcmV0dXJu"
    "IEZhbHNlCiAgICB0cnk6CiAgICAgICAgciwgYSA9IF9kZWMoc2lnWzozMl0pLCBfZGVjKHBrKQogICAgZXhjZXB0IEV4Y2VwdGlv"
    "bjoKICAgICAgICByZXR1cm4gRmFsc2UKICAgIHMgPSBpbnQuZnJvbV9ieXRlcyhzaWdbMzI6XSwgImxpdHRsZSIpCiAgICBpZiBz"
    "ID49IF9MOgogICAgICAgIHJldHVybiBGYWxzZQogICAgaCA9IGludC5mcm9tX2J5dGVzKGhhc2hsaWIuc2hhNTEyKHNpZ1s6MzJd"
    "ICsgcGsgKyBtc2cpLmRpZ2VzdCgpLCAibGl0dGxlIikgJSBfTAogICAgcmV0dXJuIF9lbmMoX211bChfQiwgcykpID09IF9lbmMo"
    "X2FkZChyLCBfbXVsKGEsIGgpKSkKCgojIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0t"
    "LS0tLS0tLS0tLS0tLS0gcGFzc3BvcnQKCl9rZXlfY2FjaGUgPSB7fQoKCmRlZiBwdWJsaWNfa2V5KCk6CiAgICBlbnYgPSBvcy5l"
    "bnZpcm9uLmdldCgiU0VCQklfUFVCS0VZIiwgIiIpLnN0cmlwKCkKICAgIGlmIGVudjoKICAgICAgICByZXR1cm4gYnl0ZXMuZnJv"
    "bWhleChlbnYpCiAgICBpZiAicGsiIG5vdCBpbiBfa2V5X2NhY2hlOgogICAgICAgIHRyeToKICAgICAgICAgICAgd2l0aCB1cmxs"
    "aWIucmVxdWVzdC51cmxvcGVuKEJBU0UgKyAiL3gvY29udGludWl0eS9wdWJrZXkiLCB0aW1lb3V0PVRJTUVPVVQpIGFzIHI6CiAg"
    "ICAgICAgICAgICAgICBfa2V5X2NhY2hlWyJwayJdID0gYnl0ZXMuZnJvbWhleChqc29uLmxvYWRzKHIucmVhZCgpKVsicHVibGlj"
    "X2tleSJdKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb24gYXMgZToKICAgICAgICAgICAgcmFpc2UgUGFzc3BvcnRSZWplY3RlZCgi"
    "Y291bGQgbm90IGxvYWQgc2ViYmkucHJvIHB1YmxpYyBrZXk6ICVzIiAlIGUpCiAgICByZXR1cm4gX2tleV9jYWNoZVsicGsiXQoK"
    "CmRlZiBfYjY0ZChzKToKICAgIHJldHVybiBiYXNlNjQudXJsc2FmZV9iNjRkZWNvZGUocyArICI9IiAqICgtbGVuKHMpICUgNCkp"
    "CgoKZGVmIGNoZWNrKHRva2VuLCBhdWRpZW5jZSwgYWN0aW9uPU5vbmUpOgogICAgIiIiT2ZmbGluZSBjaGVjay4gUmV0dXJucyB0"
    "aGUgcGFzc3BvcnQgYm9keSBvciByYWlzZXMgUGFzc3BvcnRSZWplY3RlZC4iIiIKICAgIHRyeToKICAgICAgICB0YWcsIGIsIHMg"
    "PSBzdHIodG9rZW4pLnN0cmlwKCkuc3BsaXQoIi4iKQogICAgICAgIGlmIHRhZyAhPSAic2JwMSI6CiAgICAgICAgICAgIHJhaXNl"
    "IFZhbHVlRXJyb3IKICAgICAgICByYXcsIHNpZyA9IF9iNjRkKGIpLCBfYjY0ZChzKQogICAgICAgIGJvZHkgPSBqc29uLmxvYWRz"
    "KHJhdykKICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgcmFpc2UgUGFzc3BvcnRSZWplY3RlZCgibWlzc2luZyBvciBtYWxm"
    "b3JtZWQgcGFzc3BvcnQiKQogICAgaWYgbm90IF92ZXJpZnkoc2lnLCBQUkVGSVggKyByYXcsIHB1YmxpY19rZXkoKSk6CiAgICAg"
    "ICAgcmFpc2UgUGFzc3BvcnRSZWplY3RlZCgic2lnbmF0dXJlIGRvZXMgbm90IHZlcmlmeSAtIGZvcmdlZCBvciBhbHRlcmVkIikK"
    "ICAgIHByb2JsZW1zID0gW10KICAgIGlmIHRpbWUudGltZSgpID4gYm9keS5nZXQoImV4cCIsIDApOgogICAgICAgIHByb2JsZW1z"
    "LmFwcGVuZCgiZXhwaXJlZCIpCiAgICBpZiBib2R5LmdldCgiYXVkIikgIT0gYXVkaWVuY2Uuc3RyaXAoKS5sb3dlcigpOgogICAg"
    "ICAgIHByb2JsZW1zLmFwcGVuZCgiaXNzdWVkIGZvciAlcywgbm90ICVzIiAlIChib2R5LmdldCgiYXVkIiksIGF1ZGllbmNlKSkK"
    "ICAgIGlmIGFjdGlvbiBhbmQgYm9keS5nZXQoImFjdCIpICE9IGFjdGlvbjoKICAgICAgICBwcm9ibGVtcy5hcHBlbmQoImlzc3Vl"
    "ZCBmb3IgYWN0aW9uICVzLCBub3QgJXMiICUgKGJvZHkuZ2V0KCJhY3QiKSwgYWN0aW9uKSkKICAgIGlmIHByb2JsZW1zOgogICAg"
    "ICAgIHJhaXNlIFBhc3Nwb3J0UmVqZWN0ZWQocHJvYmxlbXMpCiAgICByZXR1cm4gYm9keQoKCmRlZiByZWRlZW0odG9rZW4sIGF1"
    "ZGllbmNlLCBwYXJhbXM9Tm9uZSk6CiAgICAiIiJTcGVuZCBpdCBvbmNlLCBhdCB0aGUgbW9tZW50IG9mIGFjdGlvbi4gUmV0dXJu"
    "cyBzZWJiaS5wcm8ncyBzZWFsZWQgYW5zd2VyLiIiIgogICAgcmVxID0gdXJsbGliLnJlcXVlc3QuUmVxdWVzdCgKICAgICAgICBC"
    "QVNFICsgIi94L3Bhc3Nwb3J0L3JlZGVlbSIsIG1ldGhvZD0iUE9TVCIsCiAgICAgICAgZGF0YT1qc29uLmR1bXBzKHsidG9rZW4i"
    "OiB0b2tlbiwgImF1ZGllbmNlIjogYXVkaWVuY2Uuc3RyaXAoKS5sb3dlcigpLAogICAgICAgICAgICAgICAgICAgICAgICAgInBh"
    "cmFtcyI6IHBhcmFtcyBvciB7fX0pLmVuY29kZSgidXRmLTgiKSwKICAgICAgICBoZWFkZXJzPXsiQ29udGVudC1UeXBlIjogImFw"
    "cGxpY2F0aW9uL2pzb24iLAogICAgICAgICAgICAgICAgICJVc2VyLUFnZW50IjogInNlYmJpLXNpdGUvIiArIF9fdmVyc2lvbl9f"
    "fSkKICAgIHRyeToKICAgICAgICB3aXRoIHVybGxpYi5yZXF1ZXN0LnVybG9wZW4ocmVxLCB0aW1lb3V0PVRJTUVPVVQpIGFzIHI6"
    "CiAgICAgICAgICAgIHJlcyA9IGpzb24ubG9hZHMoci5yZWFkKCkpCiAgICBleGNlcHQgdXJsbGliLmVycm9yLkhUVFBFcnJvciBh"
    "cyBlOgogICAgICAgIHRyeToKICAgICAgICAgICAgcmVzID0ganNvbi5sb2FkcyhlLnJlYWQoKSkKICAgICAgICBleGNlcHQgRXhj"
    "ZXB0aW9uOgogICAgICAgICAgICByYWlzZSBQYXNzcG9ydFJlamVjdGVkKCJzZWJiaS5wcm8gYW5zd2VyZWQgJWQiICUgZS5jb2Rl"
    "KQogICAgZXhjZXB0IEV4Y2VwdGlvbiBhcyBlOgogICAgICAgIHJhaXNlIFBhc3Nwb3J0UmVqZWN0ZWQoImNvdWxkIG5vdCByZWFj"
    "aCBzZWJiaS5wcm8gdG8gcmVkZWVtOiAlcyIgJSBlKQogICAgaWYgbm90IHJlcy5nZXQoInJlZGVlbWVkIik6CiAgICAgICAgcmFp"
    "c2UgUGFzc3BvcnRSZWplY3RlZChyZXMuZ2V0KCJwcm9ibGVtcyIpIG9yIFsicmVmdXNlZCJdLCByZXMuZ2V0KCJzZWFsZWRfaW5f"
    "Y2hhaW4iKSkKICAgIHJldHVybiByZXMKCgpkZWYgYWNjZXB0KGhlYWRlcnNfb3JfdG9rZW4sIGF1ZGllbmNlLCBhY3Rpb249Tm9u"
    "ZSwgcGFyYW1zPU5vbmUpOgogICAgIiIiQ2hlY2sgdGhlbiByZWRlZW0uIFJldHVybnMgdGhlIHBhc3Nwb3J0IGJvZHkuIFJhaXNl"
    "cyBQYXNzcG9ydFJlamVjdGVkLiIiIgogICAgdG9rZW4gPSBoZWFkZXJzX29yX3Rva2VuCiAgICBpZiBub3QgaXNpbnN0YW5jZSh0"
    "b2tlbiwgc3RyKToKICAgICAgICBnZXQgPSBnZXRhdHRyKGhlYWRlcnNfb3JfdG9rZW4sICJnZXQiLCBOb25lKQogICAgICAgIHRv"
    "a2VuID0gKGdldChIRUFERVIpIG9yIGdldChIRUFERVIubG93ZXIoKSkgb3IgIiIpIGlmIGdldCBlbHNlICIiCiAgICBib2R5ID0g"
    "Y2hlY2sodG9rZW4sIGF1ZGllbmNlLCBhY3Rpb24pCiAgICByZXMgPSByZWRlZW0odG9rZW4sIGF1ZGllbmNlLCBwYXJhbXMpCiAg"
    "ICBib2R5WyJzZWFsZWRfaW5fY2hhaW4iXSA9IHJlcy5nZXQoInNlYWxlZF9pbl9jaGFpbiIpCiAgICBib2R5WyJibG9ja19pbmRl"
    "eCJdID0gcmVzLmdldCgiYmxvY2tfaW5kZXgiKQogICAgcmV0dXJuIGJvZHkKCgppZiBfX25hbWVfXyA9PSAiX19tYWluX18iOgog"
    "ICAgaWYgbGVuKHN5cy5hcmd2KSA8IDMgb3Igc3lzLmFyZ3ZbMV0gIT0gImNoZWNrIjoKICAgICAgICBwcmludCgidXNhZ2U6IHB5"
    "dGhvbiBzZWJiaV9zaXRlLnB5IGNoZWNrIDx0b2tlbj4gW2F1ZGllbmNlXSIpCiAgICAgICAgc3lzLmV4aXQoMikKICAgIHRyeToK"
    "ICAgICAgICBhdWQgPSBzeXMuYXJndlszXSBpZiBsZW4oc3lzLmFyZ3YpID4gMyBlbHNlIGpzb24ubG9hZHMoX2I2NGQoc3lzLmFy"
    "Z3ZbMl0uc3BsaXQoIi4iKVsxXSkpWyJhdWQiXQogICAgICAgIHQwID0gdGltZS5wZXJmX2NvdW50ZXIoKQogICAgICAgIGJvZHkg"
    "PSBjaGVjayhzeXMuYXJndlsyXSwgYXVkKQogICAgICAgIHByaW50KCJWQUxJRCAoJS4xZiBtcykgLSAlcyBhdCAlcywgZXhwaXJl"
    "cyAlcyIgJSAoKHRpbWUucGVyZl9jb3VudGVyKCkgLSB0MCkgKiAxMDAwLAogICAgICAgICAgICAgIGJvZHlbImFjdCJdLCBib2R5"
    "WyJhdWQiXSwgdGltZS5jdGltZShib2R5WyJleHAiXSkpKQogICAgZXhjZXB0IFBhc3Nwb3J0UmVqZWN0ZWQgYXMgZToKICAgICAg"
    "ICBwcmludCgiUkVKRUNURUQgLSAlcyIgJSBlKQogICAgICAgIHN5cy5leGl0KDEpCg=="
)


def _d(b):
    return base64.b64decode("".join(b.split()))


_FILES = {
    PAGE_PATH: (_d(_B64), "text/html; charset=utf-8", None),
    PAGE_PATH + "/sebbi_agent.py": (_d(_AGENT_B64), "text/plain; charset=utf-8", "sebbi_agent.py"),
    PAGE_PATH + "/sebbi_site.py": (_d(_SITE_B64), "text/plain; charset=utf-8", "sebbi_site.py"),
}
_patched = False


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        s = f.f_locals.get("self")
        if s is not None and hasattr(type(s), "do_GET") and hasattr(s, "wfile"):
            return type(s)
        f = f.f_back
    return None


def _install_page(ctx):
    global _patched
    if _patched:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_passportpage_patched", False):
        _patched = True
        return True

    original_do_GET = cls.do_GET

    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0].rstrip("/") or "/"
        hit = _FILES.get(path)
        if hit:
            body, ctype, fname = hit
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if fname:
                self.send_header("Content-Disposition", 'inline; filename="%s"' % fname)
            self.end_headers()
            self.wfile.write(body)
            return
        return original_do_GET(self)

    cls.do_GET = do_GET
    cls._passportpage_patched = True
    _patched = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _install_page(ctx)
    return ({
        "module": "passportpage",
        "version": VERSION,
        "serves": sorted(_FILES.keys()),
        "armed": armed,
        "bytes": {k: len(v[0]) for k, v in _FILES.items()},
        "note": "Hit /x/passportpage/status once after each deploy to arm these pages.",
    }, 200)


PUBLIC = {("GET", "status"), ("GET", "spec")}

```
