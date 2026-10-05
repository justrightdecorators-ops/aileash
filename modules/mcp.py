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
7. Legal notices. https://sebbi.pro/legal.txt and https://sebbi.pro/liability.txt
8. Agreement. Opening an account confirms you have read and accept these terms. The agreement is sealed into the chain with the date, the version of these terms and the AI assistant that arranged it."""

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
