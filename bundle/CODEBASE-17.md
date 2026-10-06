# Codebase — part 17 of 51

Contains:
- `modules/mcp.py`
- `modules/meter.py`
- `modules/monitor.py`
- `modules/mutual.py`
- `modules/network.py`


## `modules/mcp.py`

594 lines, 35400 bytes

```python
"""
modules/mcp.py  v1.0.0  -  sebbi.pro as a connector for Claude, ChatGPT, Cursor and any AI

    Connector URL:  https://sebbi.pro/mcp
    Arm:            https://sebbi.pro/x/arm/status

WHAT IT IS
----------
A Model Context Protocol (MCP) server. Someone adds https://sebbi.pro/mcp to
their AI assistant once, and from then on the assistant can do everything on
sebbi.pro for them, in conversation:

  read what sebbi.pro offers and what it costs
  open an account - after showing the customer the terms and getting a yes,
      which is sealed into the chain as a receipt nobody can argue with
  advise on the right setup for their stack and device, with working code
  fire a test decision and show the sealed block
  write, check and publish Signal Packs
  pull a machine-proof report for any decision
  check a Human Keys proof
  set up billing with a Stripe link

Their AI does the thinking on their account. sebbi.pro only answers the
requests, through the same routes the website uses: /signup, /api/govern,
/x/packs/*, /x/dossier/*, /x/humankeys/*, /create-checkout. Nothing here
bypasses any of them, and no existing file is changed.

THE AGREEMENT
-------------
create_account refuses unless the assistant passes the exact terms_version
it showed the customer and confirms the customer said yes. The agreement is
then sealed: terms version, a fingerprint of the email, the company, which
AI arranged it, and when. The email itself is not written into the chain.

TRANSPORT
---------
Streamable HTTP, JSON responses. POST /mcp with JSON-RPC 2.0: initialize,
tools/list, tools/call, ping. GET /mcp returns a short description.
"""

import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.request

VERSION = "1.0.0"
PROTOCOL = "2025-06-18"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "terms")}

_state = {"installed": False, "calls": 0, "accounts": 0, "last_error": None}
_sessions = {}
_lock = threading.Lock()

TERMS_TEXT = """sebbi.pro (AILeash) by Monop Content - service terms for accounts opened through an AI assistant

1. Free trial. Every product is free for 90 days from the day the account is opened. No card is needed to start.
2. Price after the trial. 50p per unique device per month, billed monthly through Stripe, counted on the real devices that used the API key. There are no tiers and no minimum term.
3. Human Keys. 50p a month for unlimited proofs for individuals; included for businesses within the per-device price.
4. Cancelling. Stop using the key or cancel the Stripe subscription at any time. Nothing further is charged.
5. Your records. Decisions you send are sealed into a tamper-evident chain that cannot be edited afterwards, by you or by us. Personal details should be sent as pseudonymous identifiers.
6. Data protection. https://sebbi.pro/data-protection
7. Full terms of service. https://sebbi.pro/terms - these points summarise them; the full terms apply.
8. Agreement. Opening an account confirms you have read and accept these terms and the full terms of service. The agreement is sealed into the chain with the date, the version of these terms and the AI assistant that arranged it."""

TERMS_VERSION = hashlib.sha256(TERMS_TEXT.encode("utf-8")).hexdigest()[:16]

PRODUCTS = [
    {"name": "AILeash", "what": "Scores every AI decision about a person (loans, payments, bans) in under 30ms - ALLOW, CHALLENGE or BLOCK - and seals it into a chain nobody can edit. Built for EU AI Act Articles 9, 12, 13 and 14.", "url": "https://sebbi.pro/#products"},
    {"name": "Sentinel", "what": "Fraud and anomaly alerts with sealed evidence, emailed the moment something looks wrong.", "url": "https://sebbi.pro/sentinel"},
    {"name": "Guardian", "what": "Child-safety engine for apps with young users: grooming-pattern flagging and a sealed duty-of-care record for the Online Safety Act.", "url": "https://sebbi.pro/guardian-parent"},
    {"name": "SonicBoom", "what": "One line of code adds an audit record to every call to OpenAI, Anthropic, AWS, Azure or Google.", "url": "https://sebbi.pro/sonicboom"},
    {"name": "Sebdog", "what": "The same engine on the customer's own hardware. No data leaves the building.", "url": "https://sebbi.pro/#onprem"},
    {"name": "Token Saver", "what": "Cuts the AI model bill: never pays twice for the same answer and stops runaway agents.", "url": "https://sebbi.pro/tokensaver"},
    {"name": "Signal Packs", "what": "Custom rules on top of the engine, written in plain English and published to an open library.", "url": "https://sebbi.pro/build"},
    {"name": "Human Keys", "what": "Proof a human typed something, live - for review sign-offs and anything that must not be AI-written.", "url": "https://sebbi.pro/keys"},
    {"name": "Machine-proof report", "what": "Everything about one decision - who, why, where from - proven unchanged, ready for an auditor.", "url": "https://sebbi.pro/dossier"},
    {"name": "Agent Passport", "what": "Signed, single-use permission for one AI agent action, checkable offline by the site being acted on.", "url": "https://sebbi.pro/passport"},
]

GOALS = [
    (("loan", "credit", "insur", "bank", "fintech", "payment", "refund", "approve", "decision", "hiring", "recruit", "ban"), ["AILeash", "Machine-proof report", "Human Keys"]),
    (("fraud", "scam", "chargeback", "bot", "takeover"), ["Sentinel", "AILeash"]),
    (("child", "kid", "teen", "school", "game", "chat app", "social"), ["Guardian"]),
    (("cost", "bill", "token", "spend", "budget", "loop", "agent"), ["Token Saver", "Signal Packs"]),
    (("hospital", "nhs", "council", "defence", "defense", "on-prem", "on prem", "air-gap", "sovereign"), ["Sebdog"]),
    (("openai", "anthropic", "claude", "gpt", "aws", "azure", "gemini", "llm"), ["SonicBoom", "AILeash"]),
    (("review", "sign-off", "sign off", "human", "oversight", "article 14"), ["Human Keys", "AILeash"]),
    (("audit", "regulator", "evidence", "court", "insurer", "compliance"), ["Machine-proof report", "AILeash"]),
    (("agent", "autonomous", "mcp"), ["Agent Passport", "Token Saver"]),
]

EV = {"user_id": "customer-42", "action": "refund", "amount": 120, "country": "UK",
      "device_id": "web-7f3a", "anomaly": 0.1, "device_risk": 0.05}


def _snippet(stack, key):
    k = key or "YOUR_API_KEY"
    ev = json.dumps(EV)
    s = (stack or "").lower()
    if any(w in s for w in ("lovable", "bolt", "replit", "cursor", "v0", "webflow", "framer", "no code app", "website", "site")):
        return "prompt", ("Before any important action in this app happens (a payment, refund, account change, approval or anything an AI decides), "
                          "send it to sebbi.pro to be scored and sealed.\n1. Store this secret as SEBBI_API_KEY: %s\n"
                          "2. Create a server-side function that POSTs JSON to https://sebbi.pro/api/govern with the header "
                          "\"Authorization: Bearer <SEBBI_API_KEY>\" and the fields user_id, action, amount, country (2-letter), "
                          "device_id, anomaly (0-1, 0 if unknown), device_risk (0-1, 0 if unknown).\n"
                          "3. ALLOW: carry on. CHALLENGE: ask the user to confirm or send it to a person. BLOCK: stop and show \"This action needs review\".\n"
                          "4. Save audit_hash and block_index from the reply next to the record.\n"
                          "5. Never put the key in browser code." % k)
    if any(w in s for w in ("zapier", "make.com", "make ", "n8n", "no-code", "nocode", "automation")):
        return "settings", ("Method: POST\nURL: https://sebbi.pro/api/govern\nHeaders: Authorization = Bearer %s ; Content-Type = application/json\n"
                            "Body (JSON): %s\nThen add a filter/condition: continue only when decision equals ALLOW." % (k, ev))
    if any(w in s for w in ("node", "javascript", "typescript", "js", "next", "deno", "bun", "edge")):
        return "node", ("const res = await fetch(\"https://sebbi.pro/api/govern\", {\n  method: \"POST\",\n"
                        "  headers: { Authorization: \"Bearer %s\", \"Content-Type\": \"application/json\" },\n"
                        "  body: JSON.stringify(%s)\n});\nconst verdict = await res.json(); // ALLOW | CHALLENGE | BLOCK\n"
                        "if (verdict.decision === \"BLOCK\") throw new Error(\"blocked for review\");" % (k, ev))
    if any(w in s for w in ("curl", "shell", "bash", "any language", "other")):
        return "curl", ("curl -s https://sebbi.pro/api/govern -H \"Authorization: Bearer %s\" "
                        "-H \"Content-Type: application/json\" -d '%s'" % (k, ev))
    return "python", ("import json, urllib.request\n\ndef sebbi(event):\n    req = urllib.request.Request(\"https://sebbi.pro/api/govern\",\n"
                      "        data=json.dumps(event).encode(),\n        headers={\"Authorization\": \"Bearer %s\", \"Content-Type\": \"application/json\"})\n"
                      "    return json.load(urllib.request.urlopen(req, timeout=5))\n\nverdict = sebbi(%s)\n"
                      "if verdict[\"decision\"] == \"BLOCK\":\n    raise PermissionError(\"blocked for review\")" % (k, ev))


# ---------------------------------------------------------------------
# calling the site's own routes
# ---------------------------------------------------------------------

def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _local(method, path, body=None, key=None, ip=None):
    port = getattr(_srv(), "PORT", None) or int(os.environ.get("PORT", 8080))
    headers = {"Content-Type": "application/json", "User-Agent": "sebbi-mcp/" + VERSION}
    if key:
        headers["Authorization"] = "Bearer " + key
    if ip:
        headers["X-Forwarded-For"] = ip
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path),
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {"error": "http_%d" % e.code}
    except Exception as e:
        return 502, {"error": "unreachable", "detail": str(e)[:160]}


def _setup():
    s = _srv()
    with s._db_lock:
        s._conn.execute("CREATE TABLE IF NOT EXISTS mcp_agreement(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                        "email_fp TEXT, company TEXT, terms_version TEXT, agent TEXT, agreed_at REAL,"
                        "block_index INTEGER, audit_hash TEXT, key_fp TEXT)")
        s._conn.commit()


# ---------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------

def _str(v, n=200):
    return str(v or "").strip()[:n]


TOOLS = [
    {"name": "sebbi_overview",
     "description": "What sebbi.pro offers: every product, what it does, its page, and the price. Start here.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sebbi_terms",
     "description": "The service terms and their version. Show these to the customer in full and get a clear yes before calling sebbi_create_account.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sebbi_create_account",
     "description": "Open a sebbi.pro account for the customer and return their API key. Only call after showing sebbi_terms and the customer saying yes. Seals the agreement into the chain.",
     "inputSchema": {"type": "object", "required": ["email", "terms_version", "customer_agreed"],
                     "properties": {"name": {"type": "string"}, "email": {"type": "string"},
                                    "company": {"type": "string"},
                                    "product": {"type": "string", "enum": ["aileash", "sentinel", "sonicboom", "guardian", "tokensaver"]},
                                    "devices": {"type": "integer", "description": "Estimated devices; billing uses the real count"},
                                    "terms_version": {"type": "string", "description": "terms_version from sebbi_terms"},
                                    "customer_agreed": {"type": "boolean", "description": "true only if the customer read the terms and said yes"}}}},
    {"name": "sebbi_setup_advice",
     "description": "Recommend the right sebbi.pro products and give step-by-step setup with working code or a ready prompt, for how the customer builds (Python, Node, Lovable, Zapier, a website builder...) and what they want to achieve.",
     "inputSchema": {"type": "object", "required": ["stack"],
                     "properties": {"stack": {"type": "string", "description": "How they build or what they use, e.g. 'Lovable website', 'Python on AWS', 'Zapier'"},
                                    "goal": {"type": "string", "description": "What they want, e.g. 'prove our loan AI is compliant', 'cut our OpenAI bill'"},
                                    "device": {"type": "string", "description": "Where they are working from, e.g. 'Android phone', 'Mac'"},
                                    "api_key": {"type": "string"}}}},
    {"name": "sebbi_test_decision",
     "description": "Send one real decision through the live engine with the customer's key and show the verdict and the sealed block.",
     "inputSchema": {"type": "object", "required": ["api_key"],
                     "properties": {"api_key": {"type": "string"}, "action": {"type": "string"}, "amount": {"type": "number"},
                                    "country": {"type": "string"}, "user_id": {"type": "string"}}}},
    {"name": "sebbi_pack_reference",
     "description": "How Signal Packs are written: the signals, measurements, flags, operators and verdicts. Read before writing a pack.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "sebbi_check_pack",
     "description": "Check a Signal Pack with the engine's own validator without publishing it.",
     "inputSchema": {"type": "object", "required": ["pack"], "properties": {"pack": {"type": "object"}}}},
    {"name": "sebbi_publish_pack",
     "description": "Publish a Signal Pack to the open library. It is sealed into the chain, dated and credited to its author. Free.",
     "inputSchema": {"type": "object", "required": ["pack"], "properties": {"pack": {"type": "object"}}}},
    {"name": "sebbi_list_packs",
     "description": "Browse the published Signal Pack library.",
     "inputSchema": {"type": "object", "properties": {"vertical": {"type": "string"}}}},
    {"name": "sebbi_decision_report",
     "description": "The machine-proof report for one decision the customer's key sealed: the decision, who sent it, where it came from, and proof it has not changed.",
     "inputSchema": {"type": "object", "required": ["api_key", "block"],
                     "properties": {"api_key": {"type": "string"}, "block": {"type": "integer"}}}},
    {"name": "sebbi_check_human_proof",
     "description": "Look up a Human Keys code (HK-XXXX-XXXX): whether a human typed the text, live, and when.",
     "inputSchema": {"type": "object", "required": ["code"], "properties": {"code": {"type": "string"}}}},
    {"name": "sebbi_billing_link",
     "description": "A secure Stripe link for the customer to add their card and set up the 50p per device subscription.",
     "inputSchema": {"type": "object", "required": ["email"],
                     "properties": {"email": {"type": "string"}, "devices": {"type": "integer"},
                                    "product": {"type": "string"}}}},
    {"name": "sebbi_verify_chain",
     "description": "Re-verify sebbi.pro's whole chain and return its height and tip. Anyone can run this.",
     "inputSchema": {"type": "object", "properties": {}}},
]

INSTRUCTIONS = ("You are connected to sebbi.pro, which scores and seals AI decisions so they can be proven later. "
                "To help someone get set up: call sebbi_overview, ask how they build and what they want, then call "
                "sebbi_setup_advice. Before opening an account, show the full text from sebbi_terms and get a clear yes; "
                "only then call sebbi_create_account with that terms_version. Give the customer their API key and tell "
                "them to keep it secret. Offer sebbi_test_decision so they see their first sealed decision, and "
                "sebbi_billing_link when they want to add a card. Pages you can point them to: https://sebbi.pro/connect, "
                "https://sebbi.pro/build, https://sebbi.pro/keys, https://sebbi.pro/dossier.")


def _call(name, a, ip, agent):
    a = a or {}
    if name == "sebbi_overview":
        return {"products": PRODUCTS,
                "price": "Free for 90 days, then 50p per device per month. No tiers, no sales calls.",
                "start": "Call sebbi_setup_advice with how the customer builds, then sebbi_terms and sebbi_create_account.",
                "pages": {"connect": "https://sebbi.pro/connect", "build_rules": "https://sebbi.pro/build",
                          "human_keys": "https://sebbi.pro/keys", "report": "https://sebbi.pro/dossier",
                          "developers": "https://sebbi.pro/developers"}}, 200
    if name == "sebbi_terms":
        return {"terms_version": TERMS_VERSION, "terms": TERMS_TEXT,
                "how_to_agree": "Show the customer these terms in full. If they say yes, call sebbi_create_account "
                                "with terms_version '%s' and customer_agreed true." % TERMS_VERSION}, 200
    if name == "sebbi_create_account":
        if a.get("customer_agreed") is not True:
            return {"error": "agreement_needed", "message": "Show the customer sebbi_terms and get a clear yes first."}, 400
        if _str(a.get("terms_version")) != TERMS_VERSION:
            return {"error": "terms_changed", "message": "Those are not the current terms. Call sebbi_terms again and show the customer the current version.",
                    "current_version": TERMS_VERSION}, 409
        email = _str(a.get("email"), 190).lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            return {"error": "invalid_email"}, 400
        product = _str(a.get("product"), 20).lower() or "aileash"
        try:
            devices = max(1, min(1000000, int(a.get("devices") or 1)))
        except (TypeError, ValueError):
            devices = 1
        st, d = _local("POST", "/signup", {"name": _str(a.get("name"), 120), "email": email,
                                           "org": _str(a.get("company"), 160), "product": product,
                                           "devices": devices}, ip=ip)
        if st != 200 or not d.get("api_key"):
            err = str(d.get("error") or "")
            if "exists" in err.lower():
                return {"error": "email_exists",
                        "message": "An account already exists for this email. The key is in the welcome email sent when it was opened."}, 409
            return {"error": "signup_failed", "message": err or "The account could not be opened."}, st if st >= 400 else 400
        key = d["api_key"]
        s = _srv()
        ts = time.time()
        email_fp = hashlib.sha256(email.encode()).hexdigest()
        key_fp = hashlib.sha256(key.encode()).hexdigest()[:16]
        receipt = {}
        try:
            out = s.seal({"user_id": "agreement", "action": "terms_agreed", "amount": 0, "country": "UK",
                          "device_id": "mcp", "anomaly": 0, "device_risk": 0},
                         {"decision": "AGREED", "score": 0, "version": VERSION, "timestamp": ts,
                          "terms_version": TERMS_VERSION, "email_fingerprint": email_fp,
                          "company": _str(a.get("company"), 160), "product": product,
                          "arranged_by": agent or "an AI assistant", "key_fingerprint": key_fp,
                          "note": "The customer was shown the terms by their AI assistant and agreed."}, ts)
            receipt = {"block_index": out[1], "audit_hash": out[0],
                       "check": "https://sebbi.pro/x/walk/block?index=%s" % out[1]}
            with s._db_lock:
                s._conn.execute("INSERT INTO mcp_agreement(email_fp,company,terms_version,agent,agreed_at,block_index,audit_hash,key_fp) "
                                "VALUES(?,?,?,?,?,?,?,?)", (email_fp, _str(a.get("company"), 160), TERMS_VERSION,
                                                            agent, ts, out[1], out[0], key_fp))
                s._conn.commit()
        except Exception as e:
            _state["last_error"] = "agreement seal: %s" % e
        _state["accounts"] += 1
        return {"api_key": key, "product": product, "trial_days": d.get("trial_days", 90),
                "referral_code": d.get("ref_code"),
                "agreement": dict(receipt, terms_version=TERMS_VERSION),
                "tell_the_customer": "Your key is ready and also on its way to your inbox with the install guide. Keep it secret. "
                                     "Everything is free for 90 days, then 50p per device per month.",
                "next": "Call sebbi_setup_advice with this api_key for working code, then sebbi_test_decision."}, 200
    if name == "sebbi_setup_advice":
        text = " ".join(_str(a.get(k), 300).lower() for k in ("stack", "goal", "device"))
        picks = []
        for words, prods in GOALS:
            if any(w in text for w in words):
                for p in prods:
                    if p not in picks:
                        picks.append(p)
        if not picks:
            picks = ["AILeash", "Machine-proof report"]
        kind, code = _snippet(a.get("stack"), _str(a.get("api_key"), 120) or None)
        dev = _str(a.get("device"), 80).lower()
        on_phone = any(w in dev for w in ("phone", "android", "iphone", "ios", "mobile", "tablet"))
        steps = []
        if not a.get("api_key"):
            steps.append("Open an account: show the customer sebbi_terms, get a yes, then call sebbi_create_account.")
        if kind == "prompt":
            steps.append("Paste the prompt below into their app builder's chat. It builds a server function that calls sebbi.pro before every important action.")
        elif kind == "settings":
            steps.append("Add an HTTP step in their automation tool with the settings below, then a filter so it only continues on ALLOW.")
        else:
            steps.append("Add the code below where their app makes a decision about a person, before it acts.")
        steps.append("Keep the key in a secret or environment variable, never in browser code.")
        steps.append("Fire sebbi_test_decision to see the first sealed decision.")
        if "Human Keys" in picks:
            steps.append("For human sign-offs, reviewers type their reason at https://sebbi.pro/keys and attach the code to the decision.")
        if "Signal Packs" in picks or "Token Saver" in picks:
            steps.append("Write custom rules with sebbi_pack_reference and sebbi_publish_pack, or at https://sebbi.pro/build.")
        if on_phone:
            steps.append("Everything here works from a phone: the setup page https://sebbi.pro/connect copies each snippet in one tap.")
        return {"recommended": [p for p in PRODUCTS if p["name"] in picks], "steps": steps,
                "format": kind, "code_or_prompt": code,
                "fields": {"user_id": "the person the decision is about (a pseudonymous id)",
                           "action": "what is happening, e.g. refund, loan_approval, account_ban",
                           "amount": "money involved, 0 if none", "country": "2-letter country code",
                           "device_id": "a stable id for the device or session",
                           "anomaly": "0 to 1, the customer's own anomaly signal, 0 if none",
                           "device_risk": "0 to 1, the customer's own device risk, 0 if none"},
                "reply": "decision (ALLOW, CHALLENGE or BLOCK), score, reasons, audit_hash, block_index, receipt_seq"}, 200
    if name == "sebbi_test_decision":
        key = _str(a.get("api_key"), 120)
        if not key:
            return {"error": "api_key_needed"}, 400
        ev = dict(EV)
        ev.update({"action": _str(a.get("action"), 60) or "refund", "user_id": _str(a.get("user_id"), 80) or "customer-42",
                   "country": (_str(a.get("country"), 2) or "UK").upper(), "device_id": "sebbi-mcp-test"})
        try:
            ev["amount"] = float(a.get("amount")) if a.get("amount") is not None else 120
        except (TypeError, ValueError):
            pass
        st, d = _local("POST", "/api/govern", ev, key=key, ip=ip)
        if st == 200 and d.get("block_index"):
            d["check_the_block"] = "https://sebbi.pro/x/walk/block?index=%s" % d["block_index"]
            d["full_report"] = "https://sebbi.pro/dossier?block=%s" % d["block_index"]
        return d, st
    if name == "sebbi_pack_reference":
        st, d = _local("GET", "/x/packs/spec", ip=ip)
        return {"builder_page": "https://sebbi.pro/build", "example": {
            "name": "Stop runaway agents", "author": "Your company", "version": "1.0.0", "vertical": "general",
            "summary": "Catches AI agents stuck in loops before they run up the bill.",
            "rules": [{"when": "loop_count >= 3 and unattended", "then": "block",
                       "why": "An unattended agent sending the same request three times is stuck."},
                      {"when": "burst >= 0.8", "then": "challenge", "why": "A sudden burst looks like a script out of control."}],
            "default": "allow"}, "spec": d}, 200
    if name in ("sebbi_check_pack", "sebbi_publish_pack"):
        if not isinstance(a.get("pack"), dict):
            return {"error": "pack_needed", "message": "Send the pack as an object. See sebbi_pack_reference."}, 400
        path = "/x/packs/validate" if name == "sebbi_check_pack" else "/x/packs/publish"
        st, d = _local("POST", path, {"pack": a["pack"]}, ip=ip)
        if name == "sebbi_publish_pack" and st == 200:
            d["library"] = "https://sebbi.pro/packs.html"
        return d, st
    if name == "sebbi_list_packs":
        v = _str(a.get("vertical"), 30)
        st, d = _local("GET", "/x/packs/list" + ("?vertical=" + v if v else ""), ip=ip)
        return d, st
    if name == "sebbi_decision_report":
        key = _str(a.get("api_key"), 120)
        try:
            b = int(a.get("block"))
        except (TypeError, ValueError):
            return {"error": "block_number_needed"}, 400
        st, d = _local("GET", "/x/dossier/report?block=%d" % b, key=key, ip=ip)
        if st == 200:
            d["printable"] = "https://sebbi.pro/dossier?block=%d" % b
        return d, st
    if name == "sebbi_check_human_proof":
        code = _str(a.get("code"), 20).upper()
        st, d = _local("GET", "/x/humankeys/check?code=" + code, ip=ip)
        return d, st
    if name == "sebbi_billing_link":
        email = _str(a.get("email"), 190).lower()
        try:
            devices = max(1, int(a.get("devices") or 1))
        except (TypeError, ValueError):
            devices = 1
        st, d = _local("POST", "/create-checkout", {"email": email, "devices": devices,
                                                    "product": _str(a.get("product"), 20) or "aileash"}, ip=ip)
        if st == 200:
            d["tell_the_customer"] = "This secure Stripe page sets up the 50p per device per month subscription. Billing follows the real device count."
        elif d.get("error") == "stripe_not_configured":
            d["message"] = "Card payments are not switched on yet; the 90-day free trial carries on as normal."
        return d, st
    if name == "sebbi_verify_chain":
        st, d = _local("GET", "/api/verify-chain", ip=ip)
        return d, st
    return {"error": "unknown_tool"}, 404


# ---------------------------------------------------------------------
# JSON-RPC over HTTP
# ---------------------------------------------------------------------

def _rpc(msg, ip, session):
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
    rid = msg.get("id")
    method = msg.get("method", "")
    p = msg.get("params") or {}
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        info = p.get("clientInfo") or {}
        agent = ("%s %s" % (_str(info.get("name"), 60), _str(info.get("version"), 30))).strip() or None
        with _lock:
            _sessions[session] = {"agent": agent, "at": time.time()}
            if len(_sessions) > 5000:
                for k in sorted(_sessions, key=lambda k: _sessions[k]["at"])[:1000]:
                    _sessions.pop(k, None)
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": p.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "sebbi.pro", "title": "sebbi.pro - seal every AI decision", "version": VERSION},
            "instructions": INSTRUCTIONS}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        agent = (_sessions.get(session) or {}).get("agent")
        try:
            res, st = _call(p.get("name"), p.get("arguments"), ip, agent)
        except Exception as e:
            res, st = {"error": "tool_failed", "detail": str(e)[:200]}, 500
        _state["calls"] += 1
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text", "text": json.dumps(res, indent=1, default=str)}],
            "structuredContent": res if isinstance(res, dict) else {"result": res},
            "isError": st >= 400}}
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found: %s" % method}}


def _client_ip(h):
    xff = h.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    try:
        return str(h.client_address[0])
    except Exception:
        return None


def _cors(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, DELETE")
    h.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")


def _reply(h, status, obj, session=None):
    body = json.dumps(obj).encode() if obj is not None else b""
    h.send_response(status)
    if obj is not None:
        h.send_header("Content-Type", "application/json")
    h.send_header("Content-Length", str(len(body)))
    if session:
        h.send_header("Mcp-Session-Id", session)
    _cors(h)
    h.end_headers()
    if body:
        h.wfile.write(body)


INFO = {"name": "sebbi.pro MCP connector", "version": VERSION, "connector_url": "https://sebbi.pro/mcp",
        "transport": "streamable-http (POST JSON-RPC 2.0)",
        "add_it": {"Claude": "Settings > Connectors > Add custom connector > paste https://sebbi.pro/mcp",
                   "Claude Code": "claude mcp add --transport http sebbi https://sebbi.pro/mcp",
                   "Cursor or VS Code": "one-click from https://sebbi.pro/connect"},
        "tools": [t["name"] for t in TOOLS]}


def _install():
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is None:
        return False
    if getattr(H, "_mcp_patched", False):
        return True
    orig_post, orig_get = H.do_POST, H.do_GET
    orig_opt = getattr(H, "do_OPTIONS", None)
    orig_del = getattr(H, "do_DELETE", None)

    def is_mcp(h):
        return h.path.split("?")[0].rstrip("/") in ("/mcp", "/mcp/sse")

    def do_POST(self):
        if not is_mcp(self):
            return orig_post(self)
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n > 1024 * 1024:
                return _reply(self, 413, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "request too large"}})
            raw = self.rfile.read(n) if n else b""
            msg = json.loads(raw or b"null")
        except Exception:
            return _reply(self, 400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
        session = self.headers.get("Mcp-Session-Id") or ""
        new_session = None
        if isinstance(msg, dict) and msg.get("method") == "initialize":
            session = new_session = secrets.token_hex(16)
        ip = _client_ip(self)
        if isinstance(msg, list):
            out = [r for r in (_rpc(m, ip, session) for m in msg) if r is not None]
            return _reply(self, 200 if out else 202, out or None, new_session)
        r = _rpc(msg, ip, session)
        return _reply(self, 200 if r is not None else 202, r, new_session)

    def do_GET(self):
        if not is_mcp(self):
            return orig_get(self)
        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept:
            return _reply(self, 405, {"error": "this server answers each request directly; open no stream"})
        return _reply(self, 200, INFO)

    def do_OPTIONS(self):
        if is_mcp(self):
            self.send_response(204)
            _cors(self)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if orig_opt:
            return orig_opt(self)
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        if is_mcp(self):
            with _lock:
                _sessions.pop(self.headers.get("Mcp-Session-Id") or "", None)
            return _reply(self, 200, {})
        if orig_del:
            return orig_del(self)
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    H.do_POST, H.do_GET, H.do_OPTIONS, H.do_DELETE = do_POST, do_GET, do_OPTIONS, do_DELETE
    H._mcp_patched = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _setup()
        _state["installed"] = _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % e
    if action == "terms":
        return {"terms_version": TERMS_VERSION, "terms": TERMS_TEXT}, 200
    if action == "spec":
        return INFO, 200
    s = _srv()
    with s._db_lock:
        n = s._conn.execute("SELECT COUNT(*) FROM mcp_agreement").fetchone()[0]
    return {"module": "mcp", "version": VERSION, "armed": _state["installed"],
            "connector_url": "https://sebbi.pro/mcp", "terms_version": TERMS_VERSION,
            "accounts_opened_by_ai": n, "tool_calls_since_start": _state["calls"],
            "tools": [t["name"] for t in TOOLS], "last_error": _state["last_error"]}, 200

```


## `modules/meter.py`

281 lines, 10630 bytes

```python
"""
modules/meter.py  v1.0.0
The 50p device meter, done per device per month - without touching server.py.

Armed by https://sebbi.pro/x/meter/status after each deploy, it swaps these
functions inside the running server for new versions (same names, same
callers, nothing in server.py edited):

  record_device(api_key, device_id)
      Counts each distinct device a key sends in a calendar month (UTC), once,
      however many decisions it makes. Resets every month. Reading the count
      is a single-row lookup, so it holds at millions of devices per key.
      The engine (/api/govern) and the plug-in log (public_proof_adapter.py)
      both call this, so one central server acting for 20 million phones is
      billed for 20 million devices.

  device_count(api_key)
      What the key is billed for: the larger of last month's full count and
      this month so far. Growth is billed straight away; a customer who
      shrinks pays less the month after. Used by the trial-end checkout,
      /api/usage and the trial-expired answers.

  sync_stripe_quantities()
      The existing 6-hourly Stripe job now sets each paying subscription to
      device_count() - up or down - so every renewal charges 50p for each
      device actually used.

On first arming, each key's existing all-time device count is carried into
last month, so nobody's bill drops while the monthly count builds up.

Watch for keys stamping one device id on a whole network:
    https://sebbi.pro/admin/meter      (your admin login)
Public summary (no keys shown):
    https://sebbi.pro/x/meter/status
"""

import json
import sys
import threading
import time
from collections import defaultdict

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
RATE_GBP = 0.50
FLAG_EVENTS_PER_DEVICE = 10000
CACHE_MAX = 500000

_srv = None
_armed = False
_patched_http = False
_cache = {}
_lock = threading.Lock()
_events = defaultdict(int)
_orig = {}


def _month(ts=None):
    return time.strftime("%Y-%m", time.gmtime(ts if ts is not None else time.time()))


def _prev_month(ts=None):
    t = time.gmtime(ts if ts is not None else time.time())
    y, m = t.tm_year, t.tm_mon - 1
    if m == 0:
        y, m = y - 1, 12
    return "%04d-%02d" % (y, m)


def _find_server():
    for name in ("__main__", "server"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "record_device") and hasattr(m, "_conn") and hasattr(m, "_db_lock"):
            return m
    return None


# ---------------------------------------------------------------- the meter

def _setup(s):
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS device_month(api_key TEXT,month TEXT,device_id TEXT,first_seen REAL,"
                  "PRIMARY KEY(api_key,month,device_id)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS device_month_count(api_key TEXT,month TEXT,n INTEGER DEFAULT 0,"
                  "PRIMARY KEY(api_key,month)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT)")
        if not c.execute("SELECT 1 FROM config WHERE k='meter_v2_seeded'").fetchone():
            c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) "
                      "SELECT api_key,?,COUNT(*) FROM device_seen GROUP BY api_key", (_prev_month(),))
            c.execute("INSERT OR REPLACE INTO config(k,v) VALUES('meter_v2_seeded',?)", (str(time.time()),))
        c.commit()


def month_count(api_key, month=None):
    s = _srv
    with s._db_lock:
        try:
            r = s._conn.execute("SELECT n FROM device_month_count WHERE api_key=? AND month=?",
                                (api_key, month or _month())).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0


def device_count(api_key):
    """Billable devices: the larger of last month's full count and this month so far."""
    return max(month_count(api_key, _prev_month()), month_count(api_key))


def record_device(api_key, device_id):
    """Count device_id on api_key for this calendar month. Returns the billable count."""
    if not api_key or not device_id:
        return None
    s = _srv
    device_id = str(device_id)[:200]
    mon = _month()
    ck = (api_key, mon, device_id)
    with _lock:
        _events[(api_key, mon)] += 1
        hit = ck in _cache
    if not hit:
        with s._db_lock:
            try:
                c = s._conn
                cur = c.execute("INSERT OR IGNORE INTO device_month(api_key,month,device_id,first_seen) VALUES(?,?,?,?)",
                                (api_key, mon, device_id, time.time()))
                if cur.rowcount == 1:
                    c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) VALUES(?,?,0)", (api_key, mon))
                    c.execute("UPDATE device_month_count SET n=n+1 WHERE api_key=? AND month=?", (api_key, mon))
                    c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                              (api_key, device_id, time.time()))
                c.commit()
            except Exception as e:
                try:
                    s._conn.rollback()
                except Exception:
                    pass
                print("meter record_device err:" + str(e), flush=True)
                return None
        with _lock:
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[ck] = 1
    return device_count(api_key)


def sync_stripe_quantities():
    """Set each paying subscription's quantity to the billable device count, up or down."""
    s = _srv
    if not getattr(s, "STRIPE_SECRET", ""):
        print("QSYNC skip: no STRIPE_SECRET", flush=True)
        return
    with s._db_lock:
        rows = s._conn.execute("SELECT key,email,stripe_sub FROM api_keys WHERE is_paid=1 AND active=1 "
                               "AND stripe_sub!=''").fetchall()
    for key, email, sub_id in rows:
        try:
            n = device_count(key)
            if not n:
                continue
            sub = s.stripe_call("GET", "/subscriptions/" + sub_id)
            if not sub or "items" not in sub:
                print("QSYNC no sub for " + email, flush=True)
                continue
            items = sub["items"].get("data", [])
            if not items:
                continue
            item = items[0]
            current = int(item.get("quantity", 0) or 0)
            if n != current:
                r = s.stripe_call("POST", "/subscription_items/" + item["id"],
                                  {"quantity": str(n), "proration_behavior": "none"})
                if r and "id" in r:
                    print("QSYNC " + email + ": " + str(current) + " -> " + str(n) + " devices", flush=True)
                else:
                    print("QSYNC FAIL " + email, flush=True)
        except Exception as e:
            print("QSYNC ERR " + email + ": " + str(e), flush=True)


def watch(limit=200):
    mon = _month()
    with _lock:
        ev = [(k, n) for (k, m), n in _events.items() if m == mon]
    out = []
    for k, n in ev:
        d = month_count(k) or 1
        out.append({"key_prefix": k[:12], "events_this_month": n, "devices_this_month": d,
                    "events_per_device": round(n / float(d), 1), "flag": n / float(d) >= FLAG_EVENTS_PER_DEVICE})
    out.sort(key=lambda x: -x["events_per_device"])
    return out[:limit]


# ---------------------------------------------------------------- arming

def _arm():
    global _srv, _armed
    s = _find_server()
    if s is None:
        return False
    _srv = s
    _setup(s)
    if not _armed:
        for name in ("record_device", "device_count", "sync_stripe_quantities"):
            _orig.setdefault(name, getattr(s, name, None))
        s.record_device = record_device
        s.device_count = device_count
        s.sync_stripe_quantities = sync_stripe_quantities
        _armed = True
    return True


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
        o = f.f_locals.get("self")
        if o is not None and hasattr(type(o), "do_GET") and hasattr(o, "wfile"):
            return type(o)
        f = f.f_back
    return None


def _install_http(ctx):
    """Serve /admin/meter behind the server's own admin login."""
    global _patched_http
    if _patched_http:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_meter_patched", False):
        _patched_http = True
        return True
    og = cls.do_GET

    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") == "/admin/meter":
            ok = False
            try:
                ok = bool(_srv and _srv.check_admin(self))
            except Exception:
                ok = False
            body = json.dumps({"error": "unauthorized"} if not ok else
                              {"month": _month(), "rate_per_device_gbp": RATE_GBP, "keys": watch(),
                               "flag_rule": "%d or more events per device this month - check the key is sending "
                                            "real device ids" % FLAG_EVENTS_PER_DEVICE}).encode("utf-8")
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return og(self)

    cls.do_GET = do_GET
    cls._meter_patched = True
    _patched_http = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _arm()
    http = _install_http(ctx)
    flags = [w for w in watch() if w["flag"]] if armed else []
    return ({"module": "meter", "version": VERSION, "armed": armed and http,
             "month": _month(), "rate_per_device_gbp": RATE_GBP,
             "rule": "50p per distinct device per calendar month; billed on the larger of last month and this month so far",
             "keys_metered_this_month": len(watch()) if armed else 0,
             "keys_flagged": len(flags),
             "stripe_sync": "every 6 hours, follows the meter up and down"}, 200)

```


## `modules/monitor.py`

480 lines, 22705 bytes

```python
"""
modules/monitor.py  v1.0.0  -  the data behind the admin Monitor

    Arm:    https://sebbi.pro/x/arm/status
    Admin:  https://sebbi.pro/admin   (Monitor tab)
    Data:   GET /x/monitor/all        (admin login token only)

Everything Justin needs on one screen: who signed up, which devices they
linked, what they used, what was downloaded, who visited and from where,
money in, and whether every part of the machine is healthy.

VISITS AND DOWNLOADS
--------------------
server.py does not record visits, so this records them, lightly:
  - page views per path per day, and unique visitors per day. A visitor is a
    salted hash of address + browser + the day, so nobody can be identified
    and the hash changes every day. Bots are counted separately.
  - where visitors came from (the referring site's name only)
  - every download of a tool or verifier, with the time and the same daily hash
Records are buffered in memory and written every 15 seconds, so a page view
never waits on the database. Machine traffic (/x/, /api/, /mcp, /g/) is
counted as a total, not logged.

ACCESS
------
/x/monitor/all answers only to a valid admin login token (the one /admin
gets from /admin/auth). Nothing here writes to the chain.
"""

import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

VERSION = "1.0.0"
PUBLIC = {("GET", "all"), ("GET", "status"), ("GET", "")}
TRIAL_DAYS = 90

DOWNLOAD_RE = re.compile(r"\.(py|zip|tar\.gz|tgz|ots|whl|js|sh|exe|dmg|apk|pdf)$", re.I)
SKIP_PREFIX = ("/x/", "/api/", "/mcp", "/g/", "/c/", "/admin", "/static/", "/favicon", "/robots", "/.well-known/",
               "/sitemap", "/n/", "/k/")
ASSET_RE = re.compile(r"\.(css|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|map|mp4|webm|mp3|txt|xml|json)$", re.I)
BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|httpx|go-http|headless|scrapy|facebookexternalhit|bingpreview", re.I)

_state = {"installed": False, "writer": False, "last_error": None, "machine_calls": 0, "flushed": 0}
_lock = threading.Lock()
_buf_lock = threading.Lock()
_buf = {"hits": defaultdict(int), "visitors": set(), "bots": defaultdict(int), "refs": defaultdict(int), "downloads": []}
_salt = secrets.token_bytes(16)
_cache = {"chain": None, "chain_at": 0}


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _day(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


def _db(sql, args=(), one=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()


def _q(sql, args=(), default=0):
    try:
        r = _db(sql, args, one=True)
        return r[0] if r and r[0] is not None else default
    except Exception:
        return default


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS monitor_hits(day TEXT, path TEXT, n INTEGER, PRIMARY KEY(day, path))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_visitors(day TEXT, vh TEXT, PRIMARY KEY(day, vh))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_bots(day TEXT, n INTEGER, PRIMARY KEY(day))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_refs(day TEXT, host TEXT, n INTEGER, PRIMARY KEY(day, host))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_download(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, path TEXT,"
                  "vh TEXT, agent TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mon_dl_ts ON monitor_download(ts)")
        c.commit()


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------

def _record(h):
    try:
        if getattr(h, "command", "") != "GET":
            return
        path = (getattr(h, "path", "") or "").split("?")[0].split("#")[0] or "/"
        if path.startswith(("/x/", "/api/", "/mcp", "/g/", "/c/")):
            _state["machine_calls"] += 1
            return
        hd = getattr(h, "headers", None)
        if hd is None:
            return
        ua = hd.get("User-Agent", "") or ""
        is_dl = bool(DOWNLOAD_RE.search(path)) and not path.startswith(("/static/",))
        if not is_dl and (path.startswith(SKIP_PREFIX) or ASSET_RE.search(path)):
            return
        day = _day()
        if BOT_RE.search(ua) or not ua:
            with _buf_lock:
                _buf["bots"][day] += 1
            return
        xff = hd.get("X-Forwarded-For", "")
        ip = xff.split(",")[0].strip() if xff else str((getattr(h, "client_address", None) or ["?"])[0])
        vh = hmac.new(_salt, ("%s|%s|%s" % (ip, ua[:200], day)).encode(), hashlib.sha256).hexdigest()[:16]
        ref = ""
        r = hd.get("Referer", "") or ""
        m = re.match(r"https?://([^/:?#]+)", r)
        if m:
            host = m.group(1).lower()
            if not host.endswith("sebbi.pro"):
                ref = host[:80]
        agent = re.sub(r"[^\w .;:/()-]", "", ua)[:80]
        with _buf_lock:
            _buf["hits"][(day, path[:120])] += 1
            _buf["visitors"].add((day, vh))
            if ref:
                _buf["refs"][(day, ref)] += 1
            if is_dl:
                _buf["downloads"].append((time.time(), path[:160], vh, agent))
    except Exception as e:
        _state["last_error"] = "record: %s" % str(e)[:120]


def _flush():
    with _buf_lock:
        hits, vis, bots, refs, dls = (dict(_buf["hits"]), set(_buf["visitors"]), dict(_buf["bots"]),
                                      dict(_buf["refs"]), list(_buf["downloads"]))
        _buf["hits"].clear(); _buf["visitors"].clear(); _buf["bots"].clear(); _buf["refs"].clear(); _buf["downloads"].clear()
    if not (hits or vis or bots or refs or dls):
        return
    s = _srv()
    with s._db_lock:
        c = s._conn
        for (day, path), n in hits.items():
            c.execute("INSERT INTO monitor_hits(day,path,n) VALUES(?,?,?) ON CONFLICT(day,path) DO UPDATE SET n=n+?", (day, path, n, n))
        c.executemany("INSERT OR IGNORE INTO monitor_visitors(day,vh) VALUES(?,?)", list(vis))
        for day, n in bots.items():
            c.execute("INSERT INTO monitor_bots(day,n) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET n=n+?", (day, n, n))
        for (day, host), n in refs.items():
            c.execute("INSERT INTO monitor_refs(day,host,n) VALUES(?,?,?) ON CONFLICT(day,host) DO UPDATE SET n=n+?", (day, host, n, n))
        c.executemany("INSERT INTO monitor_download(ts,path,vh,agent) VALUES(?,?,?,?)", dls)
        c.commit()
    _state["flushed"] += 1


def _writer():
    while True:
        time.sleep(15)
        try:
            _flush()
        except Exception as e:
            _state["last_error"] = "flush: %s" % str(e)[:120]


def _install():
    with _lock:
        if _state["installed"]:
            return True
        H = getattr(_srv(), "Handler", None)
        if H is None:
            return False
        if not getattr(H, "_monitor_patched", False):
            original = H.handle_one_request

            def handle_one_request(self):
                try:
                    original(self)
                finally:
                    _record(self)

            H.handle_one_request = handle_one_request
            H._monitor_patched = True
        if not _state["writer"]:
            _state["writer"] = True
            threading.Thread(target=_writer, name="monitor", daemon=True).start()
        _state["installed"] = True
        return True


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def _handler():
    f = inspect.currentframe()
    try:
        for _ in range(12):
            f = f.f_back
            if f is None:
                break
            h = f.f_locals.get("h") or f.f_locals.get("self")
            if h is not None and hasattr(h, "headers") and hasattr(h, "wfile"):
                return h
    finally:
        del f
    return None


def _is_admin():
    h = _handler()
    s = _srv()
    try:
        return bool(h is not None and s.check_admin(h))
    except Exception:
        return False


def _chain():
    now = time.time()
    if _cache["chain"] is None or now - _cache["chain_at"] > 300:
        try:
            v = _srv().verify_chain()
            _cache["chain"] = {"valid": v.get("valid"), "blocks": v.get("blocks"), "tip": v.get("tip"),
                               "checked_utc": _iso(now)}
        except Exception as e:
            _cache["chain"] = {"valid": None, "error": str(e)[:120]}
        _cache["chain_at"] = now
    return _cache["chain"]


def _mod_state(name):
    m = sys.modules.get("modules." + name) or sys.modules.get(name)
    if not m:
        return {"loaded": False}
    st = getattr(m, "_state", {}) or {}
    return {"loaded": True, "version": getattr(m, "VERSION", None), "last_error": st.get("last_error")}


def snapshot():
    try:
        _flush()
    except Exception:
        pass
    s = _srv()
    now = time.time()
    t0 = now - (now % 86400)
    d7 = now - 7 * 86400
    today = _day()
    days = [_day(now - i * 86400) for i in range(13, -1, -1)]

    # customers
    keys = _db("SELECT key,email,name,org,product,created,is_paid,plan_type,actions_used FROM api_keys ORDER BY created DESC")
    dev_by_key = dict(_db("SELECT api_key, COUNT(*) FROM device_seen GROUP BY api_key"))
    dec_by_key = {}
    last_by_key = {}
    try:
        for k, n, last in _db("SELECT api_key, COUNT(*), MAX(ts) FROM audit_log WHERE api_key IS NOT NULL AND api_key!='' GROUP BY api_key"):
            dec_by_key[k] = n
            last_by_key[k] = last
    except Exception:
        pass
    gw_by_kh = {}
    try:
        gw_by_kh = dict(_db("SELECT key_hash, COUNT(*) FROM gateway_call GROUP BY key_hash"))
    except Exception:
        pass
    pilot_keys = {}
    try:
        for k, paid_at in _db("SELECT api_key, paid_at FROM pilot_order WHERE status='paid'"):
            pilot_keys[k] = paid_at
    except Exception:
        pass
    ai_emails = set()
    try:
        ai_emails = {r[0] for r in _db("SELECT email_fp FROM mcp_agreement")}
    except Exception:
        pass

    def kh(k):
        return hashlib.sha256(("gw|" + k).encode()).hexdigest()[:24]

    customers = []
    mrr = 0.0
    trials_ending = 0
    for k, email, name, org, product, created, paid, plan, used in keys:
        devs = dev_by_key.get(k, 0)
        left = None if paid else int(max(0, (created or now) + TRIAL_DAYS * 86400 - now) // 86400)
        if paid:
            mrr += 0.5 * max(1, devs)
        elif left is not None and left <= 7:
            trials_ending += 1
        efp = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()
        customers.append({"name": name or "", "email": email or "", "org": org or "", "product": product or "",
                          "joined_utc": _iso(created), "paid": bool(paid), "trial_days_left": left, "devices": devs,
                          "decisions": dec_by_key.get(k, 0), "last_active_utc": _iso(last_by_key.get(k)) if last_by_key.get(k) else None,
                          "gateway_calls": gw_by_kh.get(kh(k), 0), "pilot": bool(k in pilot_keys),
                          "via_ai": efp in ai_emails, "key_hint": (k[:10] + "…" + k[-4:]) if k else ""})

    def cnt(sql, a=()):
        return _q(sql, a, 0)

    kpi = {
        "signups_total": len(keys), "signups_today": sum(1 for c in keys if (c[5] or 0) >= t0),
        "signups_7d": sum(1 for c in keys if (c[5] or 0) >= d7), "paying": sum(1 for c in keys if c[6]),
        "trials_ending_7d": trials_ending, "mrr_gbp": round(mrr, 2),
        "devices_total": cnt("SELECT COUNT(*) FROM device_seen"),
        "devices_today": cnt("SELECT COUNT(*) FROM device_seen WHERE first_seen>=?", (t0,)),
        "decisions_total": cnt("SELECT COUNT(*) FROM audit_log"),
        "decisions_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=?", (t0,)),
        "customer_decisions_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=? AND api_key IS NOT NULL AND api_key!=''", (t0,)),
        "blocked_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=? AND result_json LIKE '%\"decision\": \"BLOCK\"%'", (t0,)),
        "visitors_today": cnt("SELECT COUNT(*) FROM monitor_visitors WHERE day=?", (today,)),
        "visitors_7d": cnt("SELECT COUNT(*) FROM monitor_visitors WHERE day>=?", (days[-7],)),
        "page_views_today": cnt("SELECT SUM(n) FROM monitor_hits WHERE day=?", (today,)),
        "bots_today": cnt("SELECT n FROM monitor_bots WHERE day=?", (today,)),
        "downloads_today": cnt("SELECT COUNT(*) FROM monitor_download WHERE ts>=?", (t0,)),
        "downloads_7d": cnt("SELECT COUNT(*) FROM monitor_download WHERE ts>=?", (d7,)),
        "gateway_calls_today": cnt("SELECT COUNT(*) FROM gateway_call WHERE ts>=?", (t0,)),
        "notary_today": cnt("SELECT COUNT(*) FROM notary_leaf WHERE submitted>=? AND who NOT IN ('codebase','humankeys')", (t0,)),
        "human_keys_total": cnt("SELECT COUNT(*) FROM humankeys_proof"),
        "accounts_by_ai": cnt("SELECT COUNT(*) FROM mcp_agreement"),
        "pilots_paid": cnt("SELECT COUNT(*) FROM pilot_order WHERE status='paid'"),
        "pilot_revenue_gbp": round(cnt("SELECT SUM(amount) FROM pilot_order WHERE status='paid'") / 100.0, 2),
        "wallet_topups_gbp": round(cnt("SELECT SUM(pence) FROM credit_payment WHERE status='paid'") / 100.0, 2),
        "messages_7d": cnt("SELECT COUNT(*) FROM contact_log WHERE ts>=?", (d7,)),
        "machine_calls_since_start": _state["machine_calls"],
    }

    # 14-day series
    def series(sql, keyfn=None):
        out = dict.fromkeys(days, 0)
        try:
            for d, n in _db(sql, (days[0],)):
                if d in out:
                    out[d] = n
        except Exception:
            pass
        return [out[d] for d in days]

    ser = {
        "days": days,
        "visitors": series("SELECT day, COUNT(*) FROM monitor_visitors WHERE day>=? GROUP BY day"),
        "signups": series("SELECT strftime('%Y-%m-%d', created, 'unixepoch'), COUNT(*) FROM api_keys WHERE strftime('%Y-%m-%d', created, 'unixepoch')>=? GROUP BY 1"),
        "decisions": series("SELECT strftime('%Y-%m-%d', ts, 'unixepoch'), COUNT(*) FROM audit_log WHERE strftime('%Y-%m-%d', ts, 'unixepoch')>=? GROUP BY 1"),
        "devices": series("SELECT strftime('%Y-%m-%d', first_seen, 'unixepoch'), COUNT(*) FROM device_seen WHERE strftime('%Y-%m-%d', first_seen, 'unixepoch')>=? GROUP BY 1"),
        "downloads": series("SELECT strftime('%Y-%m-%d', ts, 'unixepoch'), COUNT(*) FROM monitor_download WHERE strftime('%Y-%m-%d', ts, 'unixepoch')>=? GROUP BY 1"),
    }

    pages = [{"path": p, "views": n} for p, n in _safe("SELECT path, SUM(n) FROM monitor_hits WHERE day>=? GROUP BY path ORDER BY 2 DESC LIMIT 15", (days[-7],))]
    refs = [{"site": h, "visits": n} for h, n in _safe("SELECT host, SUM(n) FROM monitor_refs WHERE day>=? GROUP BY host ORDER BY 2 DESC LIMIT 12", (days[-7],))]
    downloads = [{"utc": _iso(t), "path": p, "visitor": v[:8], "agent": a} for t, p, v, a in
                 _safe("SELECT ts, path, vh, agent FROM monitor_download ORDER BY ts DESC LIMIT 60")]
    dl_top = [{"path": p, "count": n} for p, n in _safe("SELECT path, COUNT(*) FROM monitor_download GROUP BY path ORDER BY 2 DESC LIMIT 12")]
    email_by_key = {k[0]: k[1] for k in keys}
    devices = [{"utc": _iso(t), "device": (d or "")[:40], "customer": email_by_key.get(k, "?")} for k, d, t in
               _safe("SELECT api_key, device_id, first_seen FROM device_seen ORDER BY first_seen DESC LIMIT 60")]
    messages = [{"utc": _iso(t), "name": n, "email": e, "org": o, "message": (m or "")[:400]} for t, n, e, o, m in
                _safe("SELECT ts, name, email, org, message FROM contact_log ORDER BY ts DESC LIMIT 20")]
    pilots = [{"utc": _iso(c), "name": n, "email": e, "company": co, "status": st, "paid_utc": _iso(p) if p else None,
               "deliver_by_utc": _iso(p + 7 * 86400) if p else None, "amount_gbp": (a or 0) / 100.0} for c, n, e, co, st, p, a in
              _safe("SELECT created, name, email, company, status, paid_at, amount FROM pilot_order ORDER BY created DESC LIMIT 30")]

    # live feed
    feed = []
    for c in customers[:40]:
        feed.append((c["joined_utc"], "signup", "%s signed up%s" % (c["name"] or c["email"], " via an AI assistant" if c["via_ai"] else ""), c["org"] or c["product"]))
    for d in devices[:40]:
        feed.append((d["utc"], "device", "New device linked", "%s · %s" % (d["customer"], d["device"])))
    for d in downloads[:40]:
        feed.append((d["utc"], "download", "Downloaded %s" % d["path"], d["agent"][:40]))
    for m in messages[:10]:
        feed.append((m["utc"], "message", "Message from %s" % (m["name"] or m["email"]), m["message"][:90]))
    for p in pilots[:10]:
        if p["status"] == "paid":
            feed.append((p["paid_utc"], "money", "PILOT PAID £%.0f — %s" % (p["amount_gbp"], p["company"]), p["email"]))
        else:
            feed.append((p["utc"], "checkout", "Pilot checkout started — %s" % p["company"], p["email"]))
    for t, pv, mdl, dec in _safe("SELECT ts, provider, model, decision FROM gateway_call ORDER BY ts DESC LIMIT 20"):
        feed.append((_iso(t), "gateway", "Gateway call %s" % (dec or ""), "%s %s" % (pv, mdl or "")))
    for t, r in _safe("SELECT ts, result_json FROM audit_log WHERE result_json LIKE '%\"decision\": \"BLOCK\"%' ORDER BY id DESC LIMIT 10"):
        feed.append((_iso(t), "block", "Decision BLOCKED", ""))
    for t, e, st, sub in _safe("SELECT at, email, step, subject FROM autopilot_sent WHERE status='sent' ORDER BY at DESC LIMIT 25"):
        feed.append((_iso(t), "autopilot", "Autopilot emailed %s" % e, sub or st))
    feed = [{"utc": a, "kind": b, "title": c, "detail": d} for a, b, c, d in sorted((f for f in feed if f[0]), reverse=True)[:80]]

    # health
    chain = _chain()
    btc = {}
    try:
        r = _db("SELECT MAX(chain_size), MAX(btc_height), MAX(confirmed_at) FROM notary_batch WHERE kind='chain' AND state='confirmed'", one=True)
        last_cp = _q("SELECT MAX(created) FROM notary_batch WHERE kind='chain'")
        btc = {"blocks_in_bitcoin": r[0] or 0, "latest_bitcoin_block": r[1], "last_confirmed_utc": _iso(r[2]) if r[2] else None,
               "last_checkpoint_utc": _iso(last_cp) if last_cp else None,
               "pending": cnt("SELECT COUNT(*) FROM notary_batch WHERE state IN ('new','pending')")}
    except Exception:
        pass
    mods = {n: _mod_state(n) for n in ("notary", "gateway", "pilot", "ratelimit", "humankeys", "mcp", "connect", "dossier",
                                        "heartbeat", "ots", "ainews", "brand", "homelink", "answers", "autopilot", "monitor")}

    # alerts
    alerts = []
    if chain.get("valid") is False:
        alerts.append({"level": "critical", "text": "Chain verification FAILED — open the Chain tab now."})
    for p in pilots:
        if p["status"] == "paid" and p["paid_utc"]:
            due = datetime.strptime(p["deliver_by_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            dleft = (due - now) / 86400
            if dleft > -30:
                alerts.append({"level": "money" if dleft > 2 else "serious",
                               "text": "Pilot for %s — deliver by %s (%s)" % (p["company"], p["deliver_by_utc"][:10],
                                                                            "%.0f days left" % dleft if dleft >= 0 else "OVERDUE")})
    if trials_ending:
        alerts.append({"level": "warning", "text": "%d trial%s end within 7 days — chase for a card." % (trials_ending, "" if trials_ending == 1 else "s")})
    if kpi["messages_7d"]:
        alerts.append({"level": "info", "text": "%d message%s in the last 7 days." % (kpi["messages_7d"], "" if kpi["messages_7d"] == 1 else "s")})
    if btc.get("last_confirmed_utc"):
        age = (now - datetime.strptime(btc["last_confirmed_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()) / 3600
        if age > 12:
            alerts.append({"level": "warning", "text": "No new Bitcoin confirmation for %.0f hours." % age})
    core = ("notary", "gateway", "pilot", "ratelimit", "humankeys", "mcp", "dossier", "heartbeat", "ots", "homelink", "autopilot")
    for n, m in mods.items():
        if n in core and m.get("loaded") and m.get("last_error"):
            alerts.append({"level": "warning", "text": "%s: %s" % (n, str(m["last_error"])[:120])})
    unloaded = [n for n in ("notary", "gateway", "pilot", "ratelimit", "homelink") if not mods[n]["loaded"]]
    if unloaded:
        alerts.append({"level": "serious", "text": "Not armed: %s — tap https://sebbi.pro/x/arm/status" % ", ".join(unloaded)})

    return {"generated_utc": _iso(now), "kpi": kpi, "series": ser, "customers": customers[:300], "devices": devices,
            "downloads": downloads, "downloads_top": dl_top, "pages": pages, "referrers": refs, "messages": messages,
            "pilots": pilots, "feed": feed, "alerts": alerts,
            "health": {"chain": chain, "bitcoin": btc, "modules": mods, "server_version": getattr(s, "VERSION", None)}}


def _safe(sql, args=()):
    try:
        return _db(sql, args)
    except Exception:
        return []


def handle(method, action, data, api_key, ctx):
    try:
        _setup()
        _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:120]
    if action in ("", "status"):
        return {"module": "monitor", "version": VERSION, "armed": _state["installed"], "recording": _state["writer"],
                "flushes": _state["flushed"], "last_error": _state["last_error"],
                "data": "GET /x/monitor/all with the admin login token"}, 200
    if action == "all":
        if not _is_admin():
            return {"error": "admin_only", "message": "Log in at https://sebbi.pro/admin"}, 401
        try:
            return snapshot(), 200
        except Exception as e:
            _state["last_error"] = "snapshot: %s" % str(e)[:150]
            return {"error": "snapshot_failed", "detail": str(e)[:200]}, 500
    return {"error": "unknown_action", "action": action}, 404

```


## `modules/mutual.py`

543 lines, 19704 bytes

```python
#!/usr/bin/env python3
"""
modules/mutual.py  -  the outbound half of mutual witnessing
============================================================

Why this exists
---------------
modules/witness.py RECEIVES. Other chains hand us their tips and we seal
them. Nothing in the platform currently SENDS our tip anywhere, so right
now we witness other people and nobody witnesses us. This module is the
missing direction.

Drop it in as modules/mutual.py. The router picks it up automatically -
no edits to server.py.

Routes
------
  POST /x/mutual/push      send our current tip to every configured peer
  POST /x/mutual/pull      fetch every peer's tip and seal it into our chain
  POST /x/mutual/sync      pull then push (this is the one to schedule)
  GET  /x/mutual/peers     the configured peers and what happened last time
  GET  /x/mutual/status    last run, next run, whether the timer is alive

Important design note
---------------------
This module does not touch the database or import anything from server.py.
It talks HTTP to routes that are already public - ours and theirs. That
means it cannot corrupt anything, it works no matter how seal() changes,
and every action it takes is one an outsider could audit for themselves.

To read our own tip it calls our own public /x/witness/tip.
To seal a peer's tip it calls our own public /x/witness/observe, which is
already built to record exactly that. So a peer tip we pull is recorded by
the same code path as a peer tip that was pushed to us.

FETCH-ONLY PEERS (added 1.2)
----------------------------
observe_url is now OPTIONAL. A peer with a tip_url and no observe_url is
fetch-only: we read and seal their tip, and we do not try to push ours.

That is a real configuration, not a broken one. Two current cases:

  A peer whose outbound submission lane is deliberately closed during
  staging. They serve a tip for us to read; their recorder never reaches
  out. Serving a file is not outbound submission.

  A peer whose tip is a static JSON file with no server behind it. They
  push to us on their own schedule and there is nothing on their side to
  POST to. Perfectly valid node.

Before 1.2 push_one read peer["observe_url"] unconditionally, so adding a
fetch-only peer would have raised KeyError on every cycle - inside a
background thread with a bare except, so it would have failed silently and
taken the whole sync with it.

CONCURRENCY - read this before changing it
------------------------------------------
A sync cycle makes two kinds of call, and they are treated differently on
purpose.

  OUTBOUND to other people's hosts (reading their tip, pushing ours) runs
  in parallel. These are the slow ones - we are waiting on somebody else's
  server, and there is no reason to wait on them one at a time. Fifty peers
  now costs roughly what the slowest single peer costs, instead of the sum
  of all fifty.

  INBOUND to our own server (sealing what we pulled) stays sequential. Our
  own process is handling those requests, and firing a burst of them at
  ourselves while we are mid-cycle is asking for trouble - a queue behind a
  single replica at best. The sealing is fast and local anyway, so there is
  nothing to gain by parallelising it and a real risk in doing so.

So: fetch everything at once, then seal one at a time.

BEFORE THIS WORKS
-----------------
1. "observe" must be in the PUBLIC set of modules/witness.py. If it is not,
   this module gets a 401 from our own server, same as Red Flag AI Pro did.
2. After every deploy, the first /x/ request must be a GET - that is what
   installs the POST branch. Opening /x/mutual/peers in a browser does it.
"""

import json
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

VERSION = "1.2"

# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------

# The router reads a set of (METHOD, action) tuples. Anything not listed
# here needs an API key - default is closed.
#
# peers and status are read-only. An outsider being able to see who we
# witness with, and whether it is actually running, is the entire point.
#
# push, pull and sync stay keyed - they cause outbound traffic and are not
# left open to anonymous callers.
PUBLIC = {("GET", "peers"), ("GET", "status")}


# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------

# Our own public witness routes. Left as full URLs on purpose so this
# module never has to guess its own host.
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"
OUR_OBSERVE_URL = "https://sebbi.pro/x/witness/observe"

# The name we go by when we hand our tip to someone else.
OUR_CHAIN_NAME = "aileash"

# Everyone we witness with. Add a dict per chain.
#   name         what we file their tips under
#   tip_url      where we GET their current tip          REQUIRED
#   observe_url  where we POST ours so they record it    OPTIONAL
#
# Omit observe_url for a fetch-only peer - see the note at the top. It is
# not an oversight and the module will not complain about it; /x/mutual/peers
# reports the direction for each so it is visible rather than assumed.
PEERS = [
    {
        "name": "red-flag-ai-pro",
        "tip_url": "https://www.redflagaipro.com/api/witness/tip",
        "observe_url": "https://www.redflagaipro.com/api/witness/anchor",
    },
    {
        # Simon. Serves a static JSON file regenerated on his side, and
        # pushes to us on his own systemd timer at :23. Nothing to POST to.
        "name": "flavorflowstrategy.uk",
        "tip_url": "https://www.flavorflowstrategy.uk/witness.json",
    },
    {
        # PRAXIS / Praesidium, chain 4. Read-only, hash-only, currently
        # SYNTHETIC_STAGING and regenerating every ten minutes, so expect
        # liveness "live" rather than "self-consistent" - the tip moves
        # between their generating it and our fetching it. That is the
        # normal case for a working chain, not a failure.
        #
        # Their outbound submission lane is deliberately closed through
        # staging, so no observe_url. They also run a signed lane at
        # /x/peer/submit under peer_id praesidium when they are ready.
        "name": "praesidium",
        "tip_url": "https://chain4.thepraesidium.ai/api/witness/tip",
    },
]

# Field names to send when pushing our tip. If a peer wants different
# names, give that peer its own "keys" dict and it will be used instead.
DEFAULT_PUSH_KEYS = {
    "chain": "chain",
    "tip": "tip",
    "count": "count",
    "ts": "ts",
    "url": "url",
}

# Where peers can read our tip, included in what we push.
OUR_PUBLIC_URL = "https://sebbi.pro/x/witness/tip"

# Background timer. Set ENABLED to False if you would rather drive it
# yourself by hitting /x/mutual/sync.
AUTO_SYNC_ENABLED = True
AUTO_SYNC_SECONDS = 3600

TIMEOUT_SECONDS = 20

# How many peers we talk to at once. Above this they queue, which is fine -
# it stops a large network spawning a thread per peer. Eight slow peers at
# 20s each still finishes in 20s; forty finishes in about a minute worst
# case, and only if every one of them times out.
MAX_PARALLEL_PEERS = 8

# ----------------------------------------------------------------------
# state - deliberately in memory only, this is not evidence
# ----------------------------------------------------------------------

_state = {
    "last_run": None,
    "last_result": None,
    "runs": 0,
    "timer_started": False,
}
_lock = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _reply(payload, status=200):
    """The router expects (payload, status) back from handle()."""
    return payload, status


def _in_parallel(function, items):
    """Run function over items concurrently, preserving input order.

    Used only for calls that leave our server. Anything hitting our own
    process goes through a plain loop instead - see the note at the top.
    """
    if not items:
        return []
    if len(items) == 1:
        return [function(items[0])]
    workers = min(len(items), MAX_PARALLEL_PEERS)
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix="mutual-peer") as pool:
        return list(pool.map(function, items))


# ----------------------------------------------------------------------
# http
# ----------------------------------------------------------------------

def _http(url, payload=None):
    """POST if payload given, else GET. Returns (status, parsed_or_text)."""
    data = None
    headers = {"Accept": "application/json",
               "User-Agent": "aileash-mutual/%s" % VERSION}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", "replace")
            status = response.getcode()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        status = exc.code
    except urllib.error.URLError as exc:
        return 0, "unreachable: %s" % exc.reason
    except Exception as exc:
        return 0, "failed: %s" % exc
    try:
        return status, json.loads(body)
    except ValueError:
        return status, body


# Field names a tip can arrive under. Different implementations name it
# differently and being strict about a name we never published is a bug in
# the receiver, not in the peer. Order is preference, not importance.
TIP_FIELDS = ("tip", "hash", "head", "tip_sha256", "root", "current_tip",
              "chain_tip", "latest")

HEIGHT_FIELDS = ("height", "count", "entries", "tree_size", "size")


def _extract_tip(body):
    """Pull (tip, height) out of whatever shape a tip route returns."""
    if not isinstance(body, dict):
        return None, None
    tip = None
    for field in TIP_FIELDS:
        value = body.get(field)
        if isinstance(value, str) and value.strip():
            tip = value.strip()
            break
    height = None
    for field in HEIGHT_FIELDS:
        if field in body:
            height = body.get(field)
            break
    return tip, height


# ----------------------------------------------------------------------
# the two directions
# ----------------------------------------------------------------------

def our_tip():
    status, body = _http(OUR_TIP_URL)
    if status != 200:
        return None, None, "our own tip route answered %s: %s" % (status, str(body)[:200])
    tip, height = _extract_tip(body)
    if not tip:
        return None, None, "no tip field in our own reply: %s" % str(body)[:200]
    return tip, height, None


def push_one(peer, tip, height):
    """Hand our tip to one peer so they record it. Outbound only.

    A peer with no observe_url is fetch-only by configuration. Say so and
    move on rather than treating it as a failure - and never index the key
    blindly, which is what 1.1 did.
    """
    observe_url = peer.get("observe_url")
    if not observe_url:
        return {
            "peer": peer["name"],
            "direction": "push",
            "skipped": True,
            "ok": True,
            "reason": "fetch-only peer - no observe_url configured",
            "note": ("We read and seal their tip. They do not accept a push, "
                     "either because their outbound lane is closed or because "
                     "their tip is a static file. Not an error."),
        }

    keys = peer.get("keys", DEFAULT_PUSH_KEYS)
    values = {
        "chain": OUR_CHAIN_NAME,
        "tip": tip,
        "count": height,
        "ts": _now(),
        "url": OUR_PUBLIC_URL,
    }
    payload = {keys.get(k, k): v for k, v in values.items()}
    status, body = _http(observe_url, payload)
    result = {
        "peer": peer["name"],
        "direction": "push",
        "url": observe_url,
        "http": status,
        "ok": 200 <= status < 300,
        "response": body if isinstance(body, (dict, list)) else str(body)[:300],
    }
    if status == 401 or status == 403:
        result["hint"] = "they want auth on that route, or it is not in their public set"
    elif status == 404:
        result["hint"] = "wrong path - check observe_url for this peer"
    elif status == 0:
        result["hint"] = "could not reach them at all"
    return result


def fetch_one(peer):
    """Read one peer's current tip. Outbound only - no sealing here.

    Returns a dict that either carries a tip ready to seal, or an error
    already shaped like a result so it can be returned to the caller as is.
    """
    status, body = _http(peer["tip_url"])
    if status != 200:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": body if isinstance(body, (dict, list)) else str(body)[:300],
            "hint": "could not read their tip",
        }

    tip, height = _extract_tip(body)
    if not tip:
        return {
            "peer": peer["name"], "direction": "pull", "url": peer["tip_url"],
            "http": status, "ok": False, "_failed": True,
            "response": str(body)[:300],
            "hint": ("no tip field in their reply - add the field name to "
                     "TIP_FIELDS. Currently accepted: " + ", ".join(TIP_FIELDS)),
        }

    return {
        "peer": peer["name"], "url": peer["tip_url"],
        "tip": tip, "height": height, "_failed": False,
        "fetched_at": time.time(),
    }


def seal_one(fetched):
    """Seal one already-fetched peer tip into our chain.

    Goes through our own public observe route so a tip we pulled is
    recorded by exactly the same code path as a tip somebody pushed to us.
    Called in a plain loop, never in parallel - this hits our own server.

    Field names must match what modules/witness.py reads out of the body:
    chain, tip, peer_ts, url. The url is what makes the observation
    checkable by a third party rather than taken on our word - it is the
    address we just fetched this tip from.
    """
    seal_status, seal_body = _http(OUR_OBSERVE_URL, {
        "chain": fetched["peer"],
        "tip": fetched["tip"],
        "peer_ts": fetched["fetched_at"],
        "url": fetched["url"],
    })

    out = {
        "peer": fetched["peer"],
        "direction": "pull",
        "their_tip": fetched["tip"],
        "their_height": fetched["height"],
        "sealed_http": seal_status,
        "ok": 200 <= seal_status < 300,
        "response": seal_body if isinstance(seal_body, (dict, list)) else str(seal_body)[:300],
    }
    if seal_status in (401, 403):
        out["hint"] = "our own observe route rejected us - check PUBLIC in modules/witness.py"
    return out


def do_push():
    tip, height, error = our_tip()
    if error:
        return {"ok": False, "error": error}

    # Outbound to everyone at once.
    results = _in_parallel(lambda peer: push_one(peer, tip, height), PEERS)

    return {
        "ok": True,
        "our_tip": tip,
        "our_height": height,
        "pushed_to": len([r for r in results if not r.get("skipped")]),
        "fetch_only": len([r for r in results if r.get("skipped")]),
        "results": results,
    }


def do_pull():
    # Phase one: read every peer's tip at the same time. This is the slow
    # part and none of it touches us.
    fetched = _in_parallel(fetch_one, PEERS)

    # Phase two: seal what came back, one at a time, into our own chain.
    results = []
    for item in fetched:
        if item.get("_failed"):
            item.pop("_failed", None)
            results.append(item)
            continue
        results.append(seal_one(item))

    return {"ok": True, "results": results}


def do_sync():
    """Pull first, then push. That order matters: the tip we hand out then
    already contains the tips we just took in, so the two chains interlock
    rather than merely sitting alongside each other."""
    started = time.time()
    pulled = do_pull()
    pushed = do_push()
    result = {
        "ran_at": _now(),
        "took_seconds": round(time.time() - started, 2),
        "peers": len(PEERS),
        "pull": pulled,
        "push": pushed,
        "ok": bool(pulled.get("ok")) and bool(pushed.get("ok")),
    }
    with _lock:
        _state["last_run"] = result["ran_at"]
        _state["last_result"] = result
        _state["runs"] += 1
    return result


# ----------------------------------------------------------------------
# background timer
# ----------------------------------------------------------------------

def _loop():
    # Let the server finish coming up before the first run.
    time.sleep(45)
    while True:
        try:
            do_sync()
        except Exception:
            pass
        time.sleep(AUTO_SYNC_SECONDS)


def _start_timer():
    with _lock:
        if _state["timer_started"] or not AUTO_SYNC_ENABLED:
            return
        _state["timer_started"] = True
    thread = threading.Thread(target=_loop, name="mutual-sync", daemon=True)
    thread.start()


_start_timer()


# ----------------------------------------------------------------------
# router entry point
# ----------------------------------------------------------------------

def handle(method, action, data, api_key, ctx):
    action = (action or "").strip("/").lower()

    if method == "GET":
        if action == "peers":
            return _reply({
                "chain": OUR_CHAIN_NAME,
                "version": VERSION,
                "peers": [
                    {"name": p["name"],
                     "tip_url": p["tip_url"],
                     "observe_url": p.get("observe_url"),
                     "direction": ("both" if p.get("observe_url")
                                   else "fetch-only")}
                    for p in PEERS
                ],
                "parallel_fetch": MAX_PARALLEL_PEERS,
                "tip_fields_accepted": list(TIP_FIELDS),
                "note": ("Witnessing is only mutual if both columns are live. "
                         "A fetch-only peer is one we read and seal but who "
                         "does not accept a push - either their outbound lane "
                         "is closed or their tip is a static file. Both are "
                         "valid; the direction is published rather than "
                         "implied."),
            })
        if action == "status":
            with _lock:
                return _reply({
                    "version": VERSION,
                    "auto_sync": AUTO_SYNC_ENABLED,
                    "interval_seconds": AUTO_SYNC_SECONDS,
                    "timer_running": _state["timer_started"],
                    "parallel_fetch": MAX_PARALLEL_PEERS,
                    "runs": _state["runs"],
                    "last_run": _state["last_run"],
                    "last_result": _state["last_result"],
                })

    if method == "POST":
        if action == "push":
            return _reply(do_push())
        if action == "pull":
            return _reply(do_pull())
        if action == "sync":
            return _reply(do_sync())

    return _reply({
        "error": "unknown action",
        "GET": ["peers", "status"],
        "POST": ["push", "pull", "sync"],
    }, 404)

```


## `modules/network.py`

487 lines, 19842 bytes

```python
"""
modules/network.py  -  serves the public witness network page

WHY THIS IS A MODULE AND NOT A TEMPLATE
---------------------------------------
The router hands whatever handle() returns to send_json, so a module cannot
return HTML through it - it would arrive as a JSON string. So this does the
same thing router.py already does for POST: it patches the request handler at
runtime, adds a branch for the page path, and leaves every other path exactly
as it was. The patch is idempotent and lives in memory, so a restart reverts it.

THE SAME CATCH AS THE POST PATCH
--------------------------------
A module is only imported when a request reaches the router. So after every
deploy, one request to /x/network/status has to arrive before /witness works.
Opening /x/network/status in a browser does it. Until then the page path falls
through to whatever the server did before, which is a 404 - not an error page,
just the old behaviour.

If you would rather not patch anything, the same HTML works as a plain file in
static/. This exists because the page then lives with the module it describes
rather than drifting away from it.

ROUTES
------
  GET /witness            the page
  GET /witness.html       same page
  GET /x/network/status   whether the patch is installed (public)

The page itself holds no data. It reads /x/witness/tip and /x/witness/peers
from the browser, same as any other visitor would, so it cannot show anything
a stranger could not verify for themselves.
"""

import sys

VERSION = "1.0"

PUBLIC = {("GET", "status")}

PAGE_PATHS = ("/witness", "/witness.html", "/network")

_patched = [False]


PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The witness network — AILeash</title>
<meta name="description" content="Two independent platforms recording each other's records, hourly. Checkable by anyone, without an account.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,600&family=Inter+Tight:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#E9EDE4;
  --paper-deep:#DFE5D8;
  --ink:#18241F;
  --ink-soft:#4A5A52;
  --rule:#BFCCBF;
  --rule-strong:#9AAC9C;
  --stamp:#7C2B38;
  --verdigris:#2F6B5E;
  --amber:#9A6B1F;
  --gutter:#CBD6C8;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;
  background:var(--paper);
  color:var(--ink);
  font-family:"Inter Tight",system-ui,sans-serif;
  font-size:17px;
  line-height:1.6;
  /* ruled paper, faint */
  background-image:repeating-linear-gradient(
    to bottom,
    transparent 0 31px,
    rgba(154,172,156,.20) 31px 32px
  );
}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}

/* ---------- masthead ---------- */
.masthead{padding:52px 0 30px;border-bottom:2px solid var(--ink)}
.eyebrow{
  font-family:"IBM Plex Mono",monospace;
  font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink-soft);margin:0 0 18px;
}
h1{
  font-family:Fraunces,Georgia,serif;
  font-weight:600;font-size:clamp(2.5rem,7.5vw,4.6rem);
  line-height:1.02;letter-spacing:-.02em;margin:0 0 20px;
}
h1 em{font-style:italic;font-weight:300}
.standfirst{font-size:clamp(1.05rem,2.4vw,1.28rem);max-width:40ch;color:var(--ink-soft);margin:0}

/* ---------- the spread ---------- */
.spread{
  margin:44px 0 8px;
  border:1px solid var(--rule-strong);
  background:rgba(255,255,255,.4);
}
.spread-head{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule-strong);
}
.spread-head div{
  font-family:"IBM Plex Mono",monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  padding:12px 16px;color:var(--ink-soft);
}
.spread-head .mid{text-align:center;background:var(--gutter);color:var(--ink)}
.spread-head .right{text-align:right}
.folio{
  display:grid;grid-template-columns:1fr 92px 1fr;
  border-bottom:1px solid var(--rule);
}
.folio:last-child{border-bottom:0}
.side{padding:20px 16px;min-width:0}
.side.right{text-align:right}
.mid{
  background:var(--gutter);
  display:flex;align-items:center;justify-content:center;
  font-family:"IBM Plex Mono",monospace;font-size:11px;color:var(--ink-soft);
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
}
.chain-name{
  font-family:Fraunces,Georgia,serif;font-size:1.35rem;font-weight:600;
  margin:0 0 4px;letter-spacing:-.01em;
}
.role{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--ink-soft);margin:0 0 14px}
.hash{
  font-family:"IBM Plex Mono",monospace;font-size:12.5px;
  word-break:break-all;color:var(--ink);margin:0 0 3px;line-height:1.45;
}
.hash-label{font-family:"IBM Plex Mono",monospace;font-size:10.5px;
  letter-spacing:.12em;text-transform:uppercase;color:var(--ink-soft);margin:0 0 5px}
.meta{font-size:14px;color:var(--ink-soft);margin:12px 0 0}
.meta b{color:var(--ink);font-weight:600}

/* ---------- stamp ---------- */
.stamp{
  display:inline-block;margin-top:16px;padding:6px 13px 5px;
  border:2.5px solid var(--stamp);color:var(--stamp);
  font-family:"IBM Plex Mono",monospace;font-weight:500;
  font-size:12px;letter-spacing:.16em;text-transform:uppercase;
  transform:rotate(-3.5deg);opacity:.9;
}
.stamp.press{animation:press .5s cubic-bezier(.2,1.5,.4,1) both}
@keyframes press{
  0%{opacity:0;transform:rotate(-3.5deg) scale(1.5)}
  70%{opacity:.95;transform:rotate(-3.5deg) scale(.97)}
  100%{opacity:.9;transform:rotate(-3.5deg) scale(1)}
}
.stamp.live{border-color:var(--verdigris);color:var(--verdigris)}
.stamp.weak{border-color:var(--amber);color:var(--amber)}
.stamp.flag{background:var(--stamp);color:var(--paper)}

/* ---------- sections ---------- */
section{padding:56px 0;border-top:1px solid var(--rule-strong)}
h2{
  font-family:Fraunces,Georgia,serif;font-weight:600;
  font-size:clamp(1.6rem,4vw,2.3rem);letter-spacing:-.015em;
  margin:0 0 8px;line-height:1.15;
}
.sec-note{color:var(--ink-soft);max-width:56ch;margin:0 0 30px}
p{max-width:62ch}

.defs{display:grid;gap:0;border-top:1px solid var(--rule)}
.def{
  display:grid;grid-template-columns:170px 1fr;gap:20px;
  padding:15px 0;border-bottom:1px solid var(--rule);
}
.def dt{
  font-family:"IBM Plex Mono",monospace;font-size:12px;
  letter-spacing:.1em;text-transform:uppercase;padding-top:3px;
}
.def dd{margin:0;color:var(--ink-soft)}
.dot{display:inline-block;width:8px;height:8px;margin-right:8px;border-radius:50%;vertical-align:middle}
.dot.ok{background:var(--stamp)}
.dot.mid-c{background:var(--verdigris)}
.dot.weak{background:var(--amber)}

.limits li{max-width:62ch;margin-bottom:13px;color:var(--ink-soft)}
.limits b{color:var(--ink)}

pre{
  font-family:"IBM Plex Mono",monospace;font-size:13px;line-height:1.7;
  background:var(--ink);color:var(--paper);padding:20px;overflow-x:auto;
  border:0;margin:22px 0;
}
pre .k{color:#9FC6B4}
code{font-family:"IBM Plex Mono",monospace;font-size:.92em}

.links{list-style:none;padding:0;margin:24px 0 0}
.links li{border-bottom:1px solid var(--rule);padding:13px 0}
.links a{
  font-family:"IBM Plex Mono",monospace;font-size:13.5px;
  color:var(--ink);text-decoration:none;word-break:break-all;
  display:flex;justify-content:space-between;gap:16px;align-items:baseline;
}
.links a:hover,.links a:focus-visible{color:var(--stamp)}
.links span{color:var(--ink-soft);font-family:"Inter Tight",sans-serif;
  font-size:13px;flex:0 0 auto;text-align:right}

footer{padding:40px 0 70px;color:var(--ink-soft);font-size:14px}
footer a{color:var(--ink)}

.loading,.errbox{
  font-family:"IBM Plex Mono",monospace;font-size:13px;
  color:var(--ink-soft);padding:26px 16px;
}
.errbox b{display:block;color:var(--ink);margin-bottom:6px;font-family:"Inter Tight",sans-serif;font-size:15px}

a:focus-visible,button:focus-visible{outline:2.5px solid var(--stamp);outline-offset:3px}

@media (max-width:760px){
  body{background-image:none}
  .spread-head,.folio{grid-template-columns:1fr}
  .spread-head .mid,.folio .mid{
    border-left:0;border-right:0;
    border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
    padding:7px 0;text-align:center;
  }
  .spread-head .right,.side.right{text-align:left}
  .spread-head div{padding:9px 14px}
  .def{grid-template-columns:1fr;gap:5px}
}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
}
</style>
</head>
<body>

<div class="wrap">

  <header class="masthead">
    <p class="eyebrow">AILeash · the witness network</p>
    <h1>Two ledgers.<br><em>Neither one is the authority.</em></h1>
    <p class="standfirst">Independent platforms record each other's records, every hour. You can check it yourself, right now, without an account.</p>
  </header>

  <div class="spread" id="spread">
    <div class="spread-head">
      <div>This chain</div>
      <div class="mid">Exchange</div>
      <div class="right">Recorded by</div>
    </div>
    <div id="folios">
      <div class="loading">Reading the ledger…</div>
    </div>
  </div>

  <section>
    <h2>Why this exists</h2>
    <p class="sec-note">Every platform that sells you an audit trail also holds it.</p>
    <p>A hash chain stops anyone else altering the record. It does not stop the operator rebuilding the whole thing and presenting the result as history. Anchoring the chain externally narrows that down — you can't rewrite anything older than your last anchor — and it still leaves the keeper and the checker as the same party.</p>
    <p>Nothing you build alone closes that. Somebody outside has to be holding a copy.</p>
    <p>So each platform here takes the fingerprint of the others' records and seals it into its own. To rewrite your past now, everyone holding a copy would have to rewrite theirs in step, and re-obtain external timestamps that were issued days ago. The second half is the part that can't be done.</p>
  </section>

  <section>
    <h2>What the marks mean</h2>
    <p class="sec-note">Two checks run on every submission. Neither can reject one — everything gets sealed. What changes is how strong we say the claim is.</p>

    <dl class="defs">
      <div class="def"><dt><span class="dot ok"></span>Confirmed</dt><dd>We fetched the address given and it served exactly the tip that was submitted.</dd></div>
      <div class="def"><dt><span class="dot mid-c"></span>Live</dt><dd>The address served a valid but different tip. A working chain moves between submitting and our looking — normal, not a failure.</dd></div>
      <div class="def"><dt><span class="dot weak"></span>Self-declared</dt><dd>No address given, or we couldn't reach it. Taken on their word, and marked as such.</dd></div>
      <div class="def"><dt>First-use</dt><dd>First time this name appeared. It's now bound to the address it came from.</dd></div>
      <div class="def"><dt>Bound</dt><dd>Same address as the first time this name appeared. The same operator, consistently.</dd></div>
      <div class="def"><dt>Conflict</dt><dd>This name has been submitted from a different address than the one it was first bound to. Still sealed, permanently flagged. Operators do move hosts — but you get to see it and decide.</dd></div>
    </dl>
  </section>

  <section>
    <h2>What this does not prove</h2>
    <p class="sec-note">Said plainly, because the value of the rest depends on it.</p>
    <ul class="limits">
      <li><b>It doesn't prove a record was true when it was written.</b> Nothing can. No system reaches back to verify what someone was thinking or whether the data going in was honest. This proves what was recorded, when, and that it hasn't changed since.</li>
      <li><b>It doesn't prove identity.</b> A name is self-declared. Checking the address proves someone runs a live chain producing that data — not that they're who they say. Binding a name to its first address is what makes a change visible.</li>
      <li><b>Two platforms checking each other isn't much of a network.</b> The strength comes from breadth. This gets meaningfully harder to bend with every chain that joins, and not before.</li>
      <li><b>A participant can go quiet.</b> Nobody can force anyone to keep publishing. Gaps show up as stale or silent rather than disappearing, which is the point.</li>
    </ul>
  </section>

  <section>
    <h2>Joining</h2>
    <p class="sec-note">Chains submit their current head to the network and record the heads of others in return.</p>
    <pre><span class="k">POST</span> https://sebbi.pro/x/witness/observe
<span class="k">Content-Type:</span> application/json

{
  "chain": "your-chain-name",
  "tip":   "&lt;64 hex characters — your current chain head&gt;",
  "url":   "https://yoursite/your/tip",
  "ts":    "2026-08-02T14:00:00Z"
}</pre>
    <p><code>url</code> is the address we fetch to check your tip independently — it's the difference between confirmed and self-declared. <code>ts</code> is optional, epoch or ISO.</p>
    <p>Running a chain in the other direction, recording ours as we record yours, is what makes it mutual rather than us keeping a list. If you operate a platform in this space and you're willing to have your history held somewhere you don't control, message me and we'll talk through it and what it costs.</p>
  </section>

  <section>
    <h2>Check it yourself</h2>
    <p class="sec-note">Nothing here needs a login. Open any of these.</p>
    <ul class="links">
      <li><a href="/x/witness/tip">/x/witness/tip<span>our current head</span></a></li>
      <li><a href="/x/witness/peers">/x/witness/peers<span>everyone we record</span></a></li>
      <li><a href="/api/verify-chain">/api/verify-chain<span>chain checked end to end</span></a></li>
      <li><a href="/api/anchor-status">/api/anchor-status<span>the external timestamp</span></a></li>
    </ul>
  </section>

  <footer>
    <p>Sealed records and their attestations are held by each participating platform independently. AILeash operates one chain in this network; it does not run the network. — <a href="https://sebbi.pro">sebbi.pro</a></p>
  </footer>

</div>

<script>
(function(){
  var folios = document.getElementById('folios');

  function esc(s){
    return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function stampFor(liveness, nameStatus){
    var cls = 'stamp press', text = String(liveness || 'unchecked');
    if (liveness === 'confirmed') cls += '';
    else if (liveness === 'live') cls += ' live';
    else cls += ' weak';
    if (nameStatus === 'conflict'){ cls += ' flag'; text = 'conflict'; }
    return '<span class="' + cls + '">' + esc(text) + '</span>';
  }

  function ago(hours){
    if (hours == null) return 'unknown';
    if (hours < 1) return 'within the hour';
    if (hours < 2) return 'an hour ago';
    if (hours < 48) return Math.round(hours) + ' hours ago';
    return Math.round(hours / 24) + ' days ago';
  }

  function render(ours, peers){
    if (!peers || !peers.length){
      folios.innerHTML = '<div class="errbox"><b>No chains recorded yet.</b>' +
        'Nothing has been submitted to this chain. The first tip posted to ' +
        '/x/witness/observe appears here.</div>';
      return;
    }
    var html = '';
    peers.forEach(function(p){
      html += '<div class="folio">' +
        '<div class="side">' +
          '<p class="chain-name">' + esc(ours.name) + '</p>' +
          '<p class="role">head of chain · height ' + esc(ours.height) + '</p>' +
          '<p class="hash-label">Current tip</p>' +
          '<p class="hash">' + esc(ours.tip) + '</p>' +
          '<p class="meta">Sealed <b>' + esc(ours.sealed) + '</b></p>' +
        '</div>' +
        '<div class="mid">↔</div>' +
        '<div class="side right">' +
          '<p class="chain-name">' + esc(p.peer) + '</p>' +
          '<p class="role">' + esc(p.observations) + ' observations · ' +
              esc(p.distinct_tips) + ' distinct tips</p>' +
          '<p class="hash-label">Name bound to</p>' +
          '<p class="hash">' + esc(p.bound_to || 'no address supplied') + '</p>' +
          '<p class="meta">Last recorded <b>' + esc(ago(p.hours_since_last)) + '</b> · ' +
              esc(p.name_status || 'unchecked') + '</p>' +
          stampFor(p.liveness, p.name_status) +
        '</div>' +
      '</div>';
    });
    folios.innerHTML = html;
  }

  function failed(){
    folios.innerHTML = '<div class="errbox"><b>The ledger did not answer.</b>' +
      'The endpoints are public, so you can try them directly: ' +
      '<a href="/x/witness/peers">/x/witness/peers</a></div>';
  }

  Promise.all([
    fetch('/x/witness/tip').then(function(r){ return r.json(); }),
    fetch('/x/witness/peers').then(function(r){ return r.json(); })
  ]).then(function(res){
    var tip = res[0] || {}, peers = res[1] || {};
    render({
      name: 'aileash',
      tip: tip.tip || 'unavailable',
      height: tip.height == null ? '—' : tip.height,
      sealed: tip.sealed_at ? new Date(tip.sealed_at).toUTCString().replace(' GMT','  UTC') : 'unknown'
    }, peers.peers || []);
  }).catch(failed);
})();
</script>

</body>
</html>
"""


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _install(s):
    """Add a page branch to do_GET at runtime. Idempotent and reversible."""
    if _patched[0]:
        return "already installed"
    H = getattr(s, "Handler", None)
    if H is None or not hasattr(H, "do_GET"):
        return "no handler"
    if getattr(H, "_page_patched", False):
        _patched[0] = True
        return "already installed"

    original = H.do_GET

    def do_GET(self):
        try:
            from urllib.parse import urlparse
            p = urlparse(self.path).path.rstrip("/") or "/"
        except Exception:
            p = self.path or "/"
        if p in PAGE_PATHS:
            body = PAGE.encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return
        return original(self)

    H.do_GET = do_GET
    H._page_patched = True
    _patched[0] = True
    print("NETWORK: /witness page branch installed at runtime", flush=True)
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
            print("NETWORK: page patch failed - " + str(exc), flush=True)
            state = "failed: " + str(exc)

    if method == "GET" and (action or "") in ("", "status"):
        return {
            "page": "/witness",
            "installed": bool(_patched[0]),
            "install_result": state,
            "paths": list(PAGE_PATHS),
            "version": VERSION,
            "note": "The page reads /x/witness/tip and /x/witness/peers from the browser. It holds no data of its own.",
        }, 200

    return {"error": "unknown_action", "action": action,
            "GET": ["status"]}, 404

```
