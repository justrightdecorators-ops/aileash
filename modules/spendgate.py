"""
modules/spendgate.py  v1.0.0  -  Spend Gate: your AI can't spend without a sign-off

    Arm:     https://sebbi.pro/x/arm/status
    Page:    https://sebbi.pro/spend
    Verify:  https://sebbi.pro/x/spendgate/verify?token=...

WHAT IT IS
----------
An AI agent that wants to spend money - pay an invoice, buy API time, move
funds, place an order - asks sebbi.pro first. sebbi.pro checks the request
against the limits you set for that agent, scores it with the live engine,
seals the decision, and hands back a short SIGNED token:

  APPROVED  a signature naming the exact amount, payee and a few-minute window
  DENIED    a signed refusal, with the reason

Your own payment system (your bank API, Stripe, a crypto wallet, whatever you
already use) releases the money only if the token says APPROVED and the
signature checks out. Over the per-transaction limit, past the daily cap, a
payee you never allowed, or the engine flags it? No signature. No spend.

sebbi.pro IS THE SIGN-OFF, NOT THE WALLET. It never holds your money, never
holds the keys to your money, never touches a bank or a chain balance. It
signs an allow-or-deny decision; your rail enforces it. That keeps you in
full control and keeps sebbi.pro clear of holding client funds.

HOW THE SIGNATURE WORKS
-----------------------
The token is signed with the same Ed25519 key that signs every authority
proof (continuity.py). Anyone can check it with a standard library and the
published key at https://sebbi.pro/x/continuity/pubkey - no call to us, no
trust in us. Every request, approval and refusal is sealed in the chain and
provable against Bitcoin like everything else on sebbi.pro.

ROUTES  (/x/spendgate/<action>)
------
  GET  status, spec, pubkey, verify?token=                         public
  GET  policy?agent=                                               API key - read an agent's limits
  POST policy  {agent, per_tx, daily, currency, payees[]}          API key - set them
  POST request {agent, amount, currency, payee, reason}            API key - ask to spend
  POST confirm {token}                                             API key - mark it actually spent (one-shot)
  GET  grants?agent=                                               API key - recent decisions
Amounts are whole pounds in "amount"/"per_tx"/"daily", or exact pence in
"amount_pence"/"per_tx_pence"/"daily_pence".
"""

import base64
import binascii
import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone

VERSION = "1.0.0"
SITE = "https://sebbi.pro"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "pubkey"), ("GET", "verify"), ("GET", "")}

TOKEN_TAG = "sbg1"
SIG_PREFIX = b"AILEASH-SPENDGATE-v1:"
TTL = int(os.environ.get("SPENDGATE_TTL", "900"))          # a token is spendable for 15 minutes
MAX_PENCE = 10 ** 11                                        # £1,000,000,000 sanity ceiling
AGENT_RE = re.compile(r"^[A-Za-z0-9 ._:-]{1,80}$")
CUR_RE = re.compile(r"^[A-Za-z]{3}$")
PAYEE_RE = re.compile(r"^[A-Za-z0-9 @._:+/-]{1,120}$")

_state = {"ready": False, "pages": False, "mcp": False, "last_error": None,
          "requests": 0, "approved": 0, "denied": 0, "confirmed": 0}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _C():
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f.endswith("continuity.py") and hasattr(m, "_keys") and hasattr(m, "_ed_signature"):
            return m
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuity.py")
    spec = importlib.util.spec_from_file_location("spendgate_continuity", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _ctx():
    s = _srv()
    return {"conn": s._conn, "lock": s._db_lock, "seal": s.seal, "get_key": s.get_key}


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _db(sql, args=(), one=False, write=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        if write:
            s._conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS spendgate_policy(api_key TEXT, agent TEXT, per_tx_pence INTEGER,"
                  "daily_pence INTEGER, currency TEXT, payees_json TEXT, updated REAL, PRIMARY KEY(api_key, agent))")
        c.execute("CREATE TABLE IF NOT EXISTS spendgate_grant(id TEXT PRIMARY KEY, api_key TEXT, agent TEXT,"
                  "amount_pence INTEGER, currency TEXT, payee TEXT, reason TEXT, decision TEXT, reasons TEXT,"
                  "issued REAL, expires REAL, token_digest TEXT, block_index INTEGER, audit_hash TEXT,"
                  "confirmed INTEGER DEFAULT 0, confirmed_at REAL)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sg_grant ON spendgate_grant(api_key, agent, issued)")
        c.commit()


# ---------------------------------------------------------------------------
# money helpers
# ---------------------------------------------------------------------------

def _pence(data, whole_key, pence_key):
    if data.get(pence_key) is not None:
        v = data.get(pence_key)
    elif data.get(whole_key) is not None:
        try:
            v = round(float(data.get(whole_key)) * 100)
        except (TypeError, ValueError):
            return None
    else:
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    if v < 0 or v > MAX_PENCE:
        return None
    return v


def _money(pence, currency):
    sym = {"GBP": "£", "USD": "$", "EUR": "€"}.get(currency.upper(), "")
    return "%s%s%s" % (sym, "{:,.2f}".format(pence / 100.0), "" if sym else " " + currency.upper())


# ---------------------------------------------------------------------------
# policy
# ---------------------------------------------------------------------------

def _get_policy(api_key, agent):
    r = _db("SELECT per_tx_pence, daily_pence, currency, payees_json FROM spendgate_policy WHERE api_key=? AND agent=?",
            (api_key, agent), one=True)
    if not r:
        return None
    try:
        payees = json.loads(r[3]) if r[3] else []
    except Exception:
        payees = []
    return {"per_tx_pence": r[0], "daily_pence": r[1], "currency": r[2], "payees": payees}


def set_policy(api_key, data):
    agent = str(data.get("agent", "")).strip()
    if not AGENT_RE.match(agent):
        return {"error": "bad_agent", "message": "Name the agent, e.g. 'billing-bot' or 'buyer-agent-1'."}, 400
    per_tx = _pence(data, "per_tx", "per_tx_pence")
    daily = _pence(data, "daily", "daily_pence")
    if per_tx is None or daily is None:
        return {"error": "limits_required", "message": "Set per_tx and daily (in pounds), the most this agent may spend per payment and per day."}, 400
    currency = str(data.get("currency", "GBP")).strip().upper()
    if not CUR_RE.match(currency):
        currency = "GBP"
    payees = data.get("payees") or []
    if isinstance(payees, str):
        payees = [p.strip() for p in re.split(r"[\n,]+", payees) if p.strip()]
    clean = []
    for p in payees[:200]:
        p = str(p).strip()
        if p and PAYEE_RE.match(p):
            clean.append(p[:120])
    _db("INSERT INTO spendgate_policy(api_key,agent,per_tx_pence,daily_pence,currency,payees_json,updated) "
        "VALUES(?,?,?,?,?,?,?) ON CONFLICT(api_key,agent) DO UPDATE SET per_tx_pence=excluded.per_tx_pence,"
        "daily_pence=excluded.daily_pence,currency=excluded.currency,payees_json=excluded.payees_json,updated=excluded.updated",
        (api_key, agent, per_tx, daily, currency, json.dumps(clean), time.time()), write=True)
    return {"ok": True, "agent": agent, "per_transaction": _money(per_tx, currency), "daily": _money(daily, currency),
            "currency": currency, "allowed_payees": clean or "any (no allow-list set)",
            "note": "Set an allow-list of payees to refuse any payment to anyone else."}, 200


def _spent_today(api_key, agent):
    t0 = time.time() - time.time() % 86400
    r = _db("SELECT COALESCE(SUM(amount_pence),0) FROM spendgate_grant WHERE api_key=? AND agent=? AND decision='APPROVED' "
            "AND issued>=? AND (confirmed=1 OR expires>?)", (api_key, agent, t0, time.time()), one=True)
    return r[0] if r else 0


# ---------------------------------------------------------------------------
# the signed token
# ---------------------------------------------------------------------------

def _sign(body):
    C = _C()
    seed, pk, _ = C._keys(_ctx())
    raw = _canon(body).encode("utf-8")
    sig = C._ed_signature(SIG_PREFIX + raw, seed, pk)
    return "%s.%s.%s" % (TOKEN_TAG, _b64e(raw), _b64e(sig))


def _open(token):
    try:
        tag, b, s = str(token).strip().split(".")
        if tag != TOKEN_TAG:
            return None, "not a sebbi.pro Spend Gate token (expected %s.)" % TOKEN_TAG
        raw, sig = _b64d(b), _b64d(s)
        body = json.loads(raw)
    except Exception:
        return None, "malformed token"
    C = _C()
    _seed, pk, _ = C._keys(_ctx())
    if not C._ed_checkvalid(sig, SIG_PREFIX + raw, pk):
        return None, "signature does not verify against the published key"
    return body, None


def _digest(token):
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# request a spend
# ---------------------------------------------------------------------------

def request(api_key, data):
    agent = str(data.get("agent", "")).strip()
    if not AGENT_RE.match(agent):
        return {"error": "bad_agent", "message": "Name the agent making the payment."}, 400
    amount = _pence(data, "amount", "amount_pence")
    if amount is None or amount <= 0:
        return {"error": "bad_amount", "message": "Send the amount to spend, e.g. {\"amount\": 49.99}."}, 400
    payee = str(data.get("payee", "")).strip()
    if not payee or not PAYEE_RE.match(payee):
        return {"error": "bad_payee", "message": "Name who is being paid."}, 400
    reason = re.sub(r"[\x00-\x1f]", "", str(data.get("reason", "")))[:200]
    currency = str(data.get("currency", "")).strip().upper()
    policy = _get_policy(api_key, agent)
    if not policy:
        return {"error": "no_policy", "message": "No spending limits set for agent '%s'. Set them first: POST "
                "%s/x/spendgate/policy {agent, per_tx, daily}." % (agent, SITE)}, 409
    currency = currency if CUR_RE.match(currency or "") else policy["currency"]
    _state["requests"] += 1

    problems = []
    if amount > policy["per_tx_pence"]:
        problems.append("over the per-transaction limit of %s" % _money(policy["per_tx_pence"], policy["currency"]))
    spent = _spent_today(api_key, agent)
    if spent + amount > policy["daily_pence"]:
        problems.append("would take today's spend past the daily cap of %s (already %s)" %
                        (_money(policy["daily_pence"], policy["currency"]), _money(spent, policy["currency"])))
    if policy["payees"] and payee not in policy["payees"]:
        problems.append("payee '%s' is not on the allow-list" % payee)
    if currency != policy["currency"]:
        problems.append("currency %s does not match the agent's policy currency %s" % (currency, policy["currency"]))

    # risk score through the live engine (this also seals the decision in the chain)
    engine = {}
    block = seal = None
    try:
        s = _srv()
        ev = {"user_id": agent[:120], "action": "agent_spend", "amount": round(amount / 100.0, 2),
              "country": str(data.get("country", "UK")).strip().upper()[:2] or "UK",
              "device_id": ("spend:" + agent)[:120], "anomaly": 0, "device_risk": 0,
              "payee": payee, "currency": currency, "reason": reason, "via": "spendgate/1"}
        res, st = s.govern(ev, api_key)
        if st == 200:
            engine = res
            block, seal = res.get("block_index"), res.get("audit_hash")
            if res.get("decision") == "BLOCK":
                problems.append("the engine blocked this payment (%s)" % ", ".join(res.get("reasons") or []) or "risk")
            elif res.get("decision") == "CHALLENGE":
                problems.append("the engine flagged this payment for human review")
        else:
            return {"error": res.get("error", "engine_error"), "message": res.get("message", "The engine refused the request.")}, st
    except Exception as e:
        _state["last_error"] = "govern: %s" % str(e)[:150]
        problems.append("could not reach the scoring engine")

    gid = "SG-" + secrets.token_hex(8)
    now = time.time()
    decision = "APPROVED" if not problems else "DENIED"
    exp = now + TTL if decision == "APPROVED" else now
    body = {"v": 1, "iss": "sebbi.pro", "grant": gid, "decision": decision, "agent": agent,
            "amount_pence": amount, "currency": currency, "payee": payee,
            "issued": int(now), "expires": int(exp), "block": block}
    if decision == "DENIED":
        body["reasons"] = problems
    token = _sign(body)
    _db("INSERT INTO spendgate_grant(id,api_key,agent,amount_pence,currency,payee,reason,decision,reasons,issued,"
        "expires,token_digest,block_index,audit_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (gid, api_key, agent, amount, currency, payee, reason, decision, json.dumps(problems), now, exp,
         _digest(token), block, seal), write=True)
    _state["approved" if decision == "APPROVED" else "denied"] += 1

    out = {"decision": decision, "grant": gid, "agent": agent, "amount": _money(amount, currency), "payee": payee,
           "token": token, "sealed_in_chain": seal, "block_index": block,
           "verify": "%s/x/spendgate/verify?token=%s" % (SITE, token[:16] + "..."),
           "engine_decision": engine.get("decision")}
    if decision == "APPROVED":
        out["expires_utc"] = _iso(exp)
        out["spend_instruction"] = ("Release the payment only now, and record this token. It is valid once, until "
                                    "%s. Confirm it with POST %s/x/spendgate/confirm once the money has moved." % (_iso(exp), SITE))
        out["message"] = "Approved. %s to %s." % (_money(amount, currency), payee)
    else:
        out["reasons"] = problems
        out["message"] = "Denied: " + "; ".join(problems) + ". Do not release the payment."
    return out, 200


def verify(token):
    body, err = _open(token)
    if err:
        return {"valid": False, "problem": err}, 200
    now = time.time()
    expired = body.get("decision") == "APPROVED" and now > float(body.get("expires", 0))
    g = _db("SELECT decision, confirmed, confirmed_at FROM spendgate_grant WHERE id=?", (body.get("grant"),), one=True)
    out = {"valid": True, "decision": body.get("decision"), "agent": body.get("agent"),
           "amount": _money(int(body.get("amount_pence", 0)), body.get("currency", "GBP")),
           "amount_pence": body.get("amount_pence"), "currency": body.get("currency"), "payee": body.get("payee"),
           "grant": body.get("grant"), "issued_utc": _iso(body.get("issued")), "expires_utc": _iso(body.get("expires")),
           "sealed_block": body.get("block"), "signature": "verified against the published Ed25519 key",
           "pubkey": "%s/x/continuity/pubkey" % SITE}
    if body.get("reasons"):
        out["reasons"] = body["reasons"]
    if body.get("decision") == "APPROVED":
        if expired:
            out["spendable"] = False
            out["problem"] = "this approval has expired - ask again"
        elif g and g[1]:
            out["spendable"] = False
            out["problem"] = "already spent (confirmed %s)" % _iso(g[2])
        else:
            out["spendable"] = True
            out["message"] = "Release this payment. Valid once, until %s." % _iso(body.get("expires"))
    else:
        out["spendable"] = False
    return out, 200


def confirm(api_key, data):
    token = str(data.get("token", "")).strip()
    body, err = _open(token)
    if err:
        return {"error": "bad_token", "problem": err}, 400
    gid = body.get("grant")
    g = _db("SELECT api_key, decision, confirmed, expires FROM spendgate_grant WHERE id=?", (gid,), one=True)
    if not g or g[0] != api_key:
        return {"error": "not_found", "message": "No such grant for this key."}, 404
    if g[1] != "APPROVED":
        return {"error": "not_approved", "message": "That payment was denied; nothing to confirm."}, 409
    if g[2]:
        return {"error": "already_confirmed", "message": "This approval was already spent."}, 409
    if time.time() > float(g[3]):
        return {"error": "expired", "message": "This approval expired before it was spent. Ask again."}, 409
    _db("UPDATE spendgate_grant SET confirmed=1, confirmed_at=? WHERE id=?", (time.time(), gid), write=True)
    _state["confirmed"] += 1
    return {"ok": True, "grant": gid, "message": "Recorded as spent. It cannot be used again."}, 200


def grants(api_key, agent=None):
    if agent:
        rows = _db("SELECT id,agent,amount_pence,currency,payee,decision,issued,confirmed FROM spendgate_grant "
                   "WHERE api_key=? AND agent=? ORDER BY issued DESC LIMIT 100", (api_key, agent))
    else:
        rows = _db("SELECT id,agent,amount_pence,currency,payee,decision,issued,confirmed FROM spendgate_grant "
                   "WHERE api_key=? ORDER BY issued DESC LIMIT 100", (api_key,))
    return {"grants": [{"grant": r[0], "agent": r[1], "amount": _money(r[2], r[3]), "payee": r[4], "decision": r[5],
                        "utc": _iso(r[6]), "spent": bool(r[7])} for r in rows]}, 200


# ---------------------------------------------------------------------------
# AI connector tools
# ---------------------------------------------------------------------------

MCP_TOOLS = [
    {"name": "sebbi_spend_policy",
     "description": "Set the spending limits for an AI agent: the most it may pay in one go and per day, and optionally an "
                    "allow-list of payees. Must be set before the agent can be approved to spend.",
     "inputSchema": {"type": "object", "required": ["api_key", "agent", "per_tx", "daily"],
                     "properties": {"api_key": {"type": "string"}, "agent": {"type": "string"},
                                    "per_tx": {"type": "number", "description": "Max per payment, in pounds"},
                                    "daily": {"type": "number", "description": "Max per day, in pounds"},
                                    "currency": {"type": "string"}, "payees": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "sebbi_spend_request",
     "description": "Ask sebbi.pro to approve a payment before an AI agent makes it. Returns a signed APPROVED or DENIED "
                    "token. Only release the money if it is APPROVED and spendable. sebbi.pro never holds the money.",
     "inputSchema": {"type": "object", "required": ["api_key", "agent", "amount", "payee"],
                     "properties": {"api_key": {"type": "string"}, "agent": {"type": "string"},
                                    "amount": {"type": "number", "description": "Amount in pounds"},
                                    "payee": {"type": "string"}, "reason": {"type": "string"}, "currency": {"type": "string"}}}},
    {"name": "sebbi_spend_verify",
     "description": "Check a Spend Gate token's signature and whether it may still be spent. Anyone can call this; no key needed.",
     "inputSchema": {"type": "object", "required": ["token"], "properties": {"token": {"type": "string"}}}},
]


def _install_mcp():
    if _state["mcp"]:
        return True
    try:
        try:
            from modules import mcp as M
        except Exception:
            import mcp as M
    except Exception as e:
        _state["last_error"] = "mcp: %s" % e
        return False
    if getattr(M, "_spendgate_tools", False):
        _state["mcp"] = True
        return True
    names = {t["name"] for t in M.TOOLS}
    for t in MCP_TOOLS:
        if t["name"] not in names:
            M.TOOLS.append(t)
    original = M._call

    def _call(name, a, ip, agent):
        if name not in ("sebbi_spend_policy", "sebbi_spend_request", "sebbi_spend_verify"):
            return original(name, a, ip, agent)
        a = a or {}
        if name == "sebbi_spend_verify":
            return verify(a.get("token"))
        key = str(a.get("api_key") or "").strip()
        if not key or not _srv().get_key(key):
            return {"error": "invalid_api_key", "message": "Open an account first with sebbi_create_account."}, 401
        if name == "sebbi_spend_policy":
            return set_policy(key, a)
        return request(key, a)

    M._call = _call
    note = (" To stop an AI agent spending without a sign-off: set limits with sebbi_spend_policy, then call "
            "sebbi_spend_request before every payment and release money only on an APPROVED, spendable token.")
    if isinstance(getattr(M, "INSTRUCTIONS", None), str) and note not in M.INSTRUCTIONS:
        M.INSTRUCTIONS = M.INSTRUCTIONS + note
    M._spendgate_tools = True
    _state["mcp"] = True
    return True


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------

def _N():
    try:
        from modules import notary as N
    except Exception:
        import notary as N
    return N


def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "public, max-age=120")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)


def _page():
    N = _N()
    body = r"""<title>Spend Gate — your AI can't spend without a sign-off — sebbi.pro</title>
<meta name="description" content="Your AI agent can't pay a penny without sebbi.pro signing off. Set the limits, it asks before every payment, and you get a signed yes or no — provable against Bitcoin. sebbi.pro is the sign-off, never your wallet.">
</head><body>""" + N._TOP + r"""
<main class="wrap">
<section class="hero">
<div class="kick"><i></i>SPEND GATE · NEW</div>
<h1>Your AI can't spend<br>without a <em>sign-off.</em></h1>
<p>Give an AI agent money to spend and you're trusting it not to go wrong. Spend Gate takes that on trust away. The agent asks sebbi.pro before every payment, it's checked against the limits you set and scored by the engine, and you get back a signed yes or no. Over the limit, wrong payee, acting out of line? No signature. No spend.</p>
<p class="sub" style="margin-top:14px;max-width:60ch"><b>sebbi.pro is the sign-off, never your wallet.</b> It never holds your money or the keys to it. It signs the decision; your own payment system releases the money only if the signature says yes.</p>
</section>

<section class="card" id="try">
<h2>Try it</h2>
<p class="sub">A live agent with a £100-per-payment limit and a £250 daily cap. Paste your sebbi.pro key, or just watch the decisions — every one is sealed and provable.</p>
<div class="row"><input type="text" id="k" placeholder="sebbi.pro API key (needed to set limits and request)" autocomplete="off"></div>
<div class="row"><button class="btn b" id="setup">1 · Set this agent's limits</button><span class="msg" id="m1"></span></div>
<div style="height:1px;background:var(--line);margin:14px 0"></div>
<div class="row" style="align-items:flex-end;gap:14px">
<div style="flex:1;min-width:120px"><label class="sub">Pay how much?</label><input type="number" id="amt" value="50" min="1" step="1"></div>
<div style="flex:2;min-width:160px"><label class="sub">To whom?</label><input type="text" id="pay" value="AWS" placeholder="payee"></div>
</div>
<div class="row"><button class="btn b" id="ask">2 · Ask to spend</button><span class="msg" id="m2"></span></div>
<div id="verdict"></div>
</section>

<section class="card">
<h2>How your code uses it</h2>
<p class="sub">One call before the agent pays. Release the money only on an approved, spendable token.</p>
<pre>POST https://sebbi.pro/x/spendgate/request
{ "api_key": "YOUR_KEY", "agent": "billing-bot",
  "amount": 49.99, "payee": "AWS", "reason": "monthly compute" }

-> { "decision": "APPROVED", "token": "sbg1.…", "expires_utc": "…" }
   release the payment, then POST /x/spendgate/confirm { token }

-> { "decision": "DENIED", "reasons": ["over the per-transaction limit"] }
   do not pay</pre>
<p class="sub" style="margin-top:12px">Anyone can check a token's signature against the published key, with no call to us: <a href="/x/continuity/pubkey">/x/continuity/pubkey</a>. Or let an AI assistant run it all — connect <a href="/connect">https://sebbi.pro/mcp</a> and ask it to gate a payment.</p>
</section>

<section class="card">
<h2>Why it holds</h2>
<div class="how">
<div><b>YOU SET THE RULES</b><p>Per-payment limit, daily cap, an allow-list of who can ever be paid. Per agent.</p></div>
<div><b>IT ASKS FIRST</b><p>Every payment is scored by the live engine and checked against your rules before a penny moves.</p></div>
<div><b>SIGNED YES OR NO</b><p>A short Ed25519-signed token, valid once, for a few minutes. Anyone can verify it.</p></div>
<div><b>SEALED FOREVER</b><p>Every approval and refusal is in the chain and provable against Bitcoin.</p></div>
</div>
</section>
</main>""" + N._FOOT + r"""
<script>
const $=s=>document.querySelector(s);
function esc(t){return String(t==null?'':t).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function post(p,b){const h={'Content-Type':'application/json'};const k=$('#k').value.trim();if(k)h['Authorization']='Bearer '+k;
 const r=await fetch(p,{method:'POST',headers:h,body:JSON.stringify(b)});return[r.status,await r.json()]}
$('#setup').onclick=async()=>{$('#m1').className='msg';$('#m1').textContent='Setting limits…';
 try{const[st,d]=await post('/x/spendgate/policy',{agent:'demo-agent',per_tx:100,daily:250,currency:'GBP',payees:['AWS','OpenAI','Anthropic','Stripe']});
  if(st!==200)throw Error(d.message||d.error);$('#m1').className='msg ok';$('#m1').textContent='Limits set: £100 per payment, £250 a day, payees AWS / OpenAI / Anthropic / Stripe.';}
 catch(e){$('#m1').className='msg err';$('#m1').textContent=e.message}};
$('#ask').onclick=async()=>{$('#m2').className='msg';$('#m2').textContent='Asking sebbi.pro…';$('#verdict').innerHTML='';
 try{const[st,d]=await post('/x/spendgate/request',{agent:'demo-agent',amount:Number($('#amt').value||0),payee:$('#pay').value.trim()||'AWS',reason:'demo'});
  if(st!==200)throw Error(d.message||d.error);$('#m2').textContent='';
  const ok=d.decision==='APPROVED';
  $('#verdict').innerHTML='<div class="verdict'+(ok?'':' bad')+'"><h3>'+(ok?'Approved':'Denied')+' — '+esc(d.amount)+' to '+esc(d.payee)+'</h3><p>'+esc(d.message)+'</p>'+(d.block?'<p class="sub" style="margin-top:8px">Sealed in block '+d.block+' · <a href="/forever?block='+d.block+'">check it against Bitcoin</a></p>':'')+'</div>';}
 catch(e){$('#m2').className='msg err';$('#m2').textContent=e.message}};
</script></body></html>"""
    return N._page(N._HEAD + body)


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_spendgate_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p = (self.path or "").split("?")[0].rstrip("/")
        try:
            if p == "/spend":
                return _send(self, _page(), "text/html; charset=utf-8")
        except Exception as e:
            _state["last_error"] = "page: %s" % str(e)[:150]
        return orig(self)

    H.do_GET = do_GET
    H._spendgate_pages = True
    _state["pages"] = True
    return True


def arm(ctx=None):
    with _lock:
        if not _state["ready"]:
            _setup()
            _state["ready"] = True
        _install_pages()
        try:
            _install_mcp()
        except Exception as e:
            _state["last_error"] = "mcp: %s" % str(e)[:150]


# ---------------------------------------------------------------------------
# router entry
# ---------------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    try:
        arm(ctx)
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:150]
    data = data or {}
    if action in ("", "status"):
        return {"module": "spendgate", "version": VERSION, "armed": _state["pages"], "page": SITE + "/spend",
                "ai_connector_tools": _state["mcp"], "since_start": {k: _state[k] for k in ("requests", "approved", "denied", "confirmed")},
                "holds_funds": False, "last_error": _state["last_error"]}, 200
    if action == "spec":
        return {"module": "spendgate", "version": VERSION,
                "what": "An AI agent must get a signed sign-off from sebbi.pro before it spends. sebbi.pro checks the "
                        "limits you set, scores the payment, seals the decision, and signs APPROVED or DENIED. Your own "
                        "payment system enforces it. sebbi.pro never holds funds or the keys to funds.",
                "token": {"format": "%s.<base64 body>.<base64 Ed25519 signature>" % TOKEN_TAG,
                          "signed_with": "the continuity.py key at %s/x/continuity/pubkey" % SITE,
                          "fields": "v, iss, grant, decision, agent, amount_pence, currency, payee, issued, expires, block",
                          "ttl_seconds": TTL},
                "routes": {"policy": "POST %s/x/spendgate/policy {agent, per_tx, daily, currency, payees[]}" % SITE,
                           "request": "POST %s/x/spendgate/request {agent, amount, payee, reason}" % SITE,
                           "verify": "GET %s/x/spendgate/verify?token=..." % SITE,
                           "confirm": "POST %s/x/spendgate/confirm {token}" % SITE,
                           "grants": "GET %s/x/spendgate/grants?agent=..." % SITE,
                           "pubkey": "%s/x/spendgate/pubkey" % SITE},
                "holds_funds": False}, 200
    if action == "pubkey":
        C = _C()
        _seed, pk, source = C._keys(_ctx())
        return {"algorithm": "Ed25519", "public_key": binascii.hexlify(pk).decode(), "key_source": source,
                "signs": "Spend Gate approval and refusal tokens", "prefix": SIG_PREFIX.decode()}, 200
    if action == "verify":
        return verify(data.get("token"))
    if action == "policy":
        if not api_key:
            return {"error": "api_key_required"}, 401
        if method == "POST":
            return set_policy(api_key, data)
        pol = _get_policy(api_key, str(data.get("agent", "")).strip())
        if not pol:
            return {"error": "no_policy"}, 404
        return {"agent": str(data.get("agent", "")).strip(), "per_transaction": _money(pol["per_tx_pence"], pol["currency"]),
                "daily": _money(pol["daily_pence"], pol["currency"]), "currency": pol["currency"],
                "allowed_payees": pol["payees"] or "any (no allow-list set)"}, 200
    if action == "request" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return request(api_key, data)
    if action == "confirm" and method == "POST":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return confirm(api_key, data)
    if action == "grants":
        if not api_key:
            return {"error": "api_key_required"}, 401
        return grants(api_key, str(data.get("agent", "")).strip() or None)
    return {"error": "unknown_action", "action": action}, 404
