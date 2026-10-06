"""End-to-end check of the MCP connector (modules/mcp.py), acting as an AI assistant
would. Run by checks.yml in the no-network sandbox against a throwaway copy."""
import os, sys, subprocess, time, urllib.request, tempfile, socket, fcntl, struct, json, random

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8877", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []
B = "http://127.0.0.1:8877"


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http(method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "X-Forwarded-For": "10.9.%d.4" % random.randint(0, 250)}
    h.update(headers or {})
    rq = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None), e.headers


SID = {}


def rpc(method, params=None, rid=1):
    hd = {"Mcp-Session-Id": SID["id"]} if SID.get("id") else {}
    return http("POST", "/mcp", {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}, hd)


def tool(name, args=None):
    st, d, _ = rpc("tools/call", {"name": name, "arguments": args or {}}, rid=random.randint(2, 10 ** 6))
    r = d["result"]
    return r["structuredContent"], r["isError"]


try:
    for _ in range(40):
        try:
            if http("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    http("GET", "/x/arm/status")
    st, d, h = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "claude-ai", "version": "1.0"}})
    SID["id"] = h.get("Mcp-Session-Id")
    chk("initialize", st == 200 and d["result"]["serverInfo"]["name"] == "sebbi.pro" and SID["id"], d)
    chk("instructions tell the AI to get agreement", "terms" in d["result"]["instructions"])
    st, d, _ = http("POST", "/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"Mcp-Session-Id": SID["id"]})
    chk("notification accepted", st == 202, st)
    st, d, _ = rpc("tools/list")
    names = [t["name"] for t in d["result"]["tools"]]
    extra = {"sebbi_notarize", "sebbi_notary_receipt", "sebbi_forever_proof", "sebbi_gateway_setup", "sebbi_spend_policy", "sebbi_spend_request", "sebbi_spend_verify"}
    base13 = len([n for n in names if n not in extra])
    chk("13 tools listed (+ notary and gateway tools when those modules are armed)", base13 == 13 and len(names) == len(set(names)), names)
    o, e = tool("sebbi_overview")
    chk("overview lists products and price", not e and len(o["products"]) >= 8 and "50p" in o["price"], o)
    t, e = tool("sebbi_terms")
    ver = t["terms_version"]
    chk("terms with a version", not e and len(ver) == 16 and "90 days" in t["terms"], t)
    r, e = tool("sebbi_create_account", {"email": "ai@example.org", "terms_version": ver, "customer_agreed": False})
    chk("refuses without the customer's yes", e and r.get("error") == "agreement_needed", r)
    r, e = tool("sebbi_create_account", {"email": "ai@example.org", "terms_version": "0000", "customer_agreed": True})
    chk("refuses out-of-date terms", e and r.get("error") == "terms_changed", r)
    acc, e = tool("sebbi_create_account", {"name": "Alex Test", "email": "ai@example.org", "company": "Agent Ltd",
                                           "terms_version": ver, "customer_agreed": True, "devices": 3})
    key = acc.get("api_key")
    chk("opens the account and returns the key", not e and key, acc)
    chk("agreement sealed into the chain", acc.get("agreement", {}).get("block_index"), acc)
    import sqlite3
    row = sqlite3.connect(w + "/a.db").execute("SELECT event_json, result_json FROM audit_log WHERE id=?",
                                                (acc["agreement"]["block_index"],)).fetchone()
    pre = json.dumps(row)
    chk("sealed agreement names the AI and terms, not the email", "claude-ai" in pre and ver in pre and "ai@example.org" not in pre, pre[:300])
    r, e = tool("sebbi_create_account", {"email": "ai@example.org", "terms_version": ver, "customer_agreed": True})
    chk("second account for same email refused clearly", e and r.get("error") == "email_exists", r)
    adv, e = tool("sebbi_setup_advice", {"stack": "Lovable website", "goal": "prove our loan decisions are compliant",
                                         "device": "Android phone", "api_key": key})
    chk("advice: Lovable prompt with the key", not e and adv["format"] == "prompt" and key in adv["code_or_prompt"], adv)
    chk("advice: recommends AILeash for loans", any(x["name"] == "AILeash" for x in adv["recommended"]), adv["recommended"])
    chk("advice: knows they are on a phone", any("phone" in s_ for s_ in adv["steps"]), adv["steps"])
    adv2, e = tool("sebbi_setup_advice", {"stack": "Zapier", "goal": "cut our OpenAI bill"})
    chk("advice: Zapier settings and Token Saver", adv2["format"] == "settings" and any(x["name"] == "Token Saver" for x in adv2["recommended"]), adv2)
    d, e = tool("sebbi_test_decision", {"api_key": key, "action": "loan_approval", "amount": 5000})
    chk("test decision sealed", not e and d.get("block_index") and d.get("decision") in ("ALLOW", "CHALLENGE", "BLOCK"), d)
    rep, e = tool("sebbi_decision_report", {"api_key": key, "block": d["block_index"]})
    chk("machine-proof report for that decision", not e and rep.get("subject", {}).get("block_index") == d["block_index"], str(rep)[:300])
    ref, e = tool("sebbi_pack_reference")
    chk("pack reference", not e and ref.get("example"), ref)
    pk = dict(ref["example"], author="Agent Ltd", name="Agent loop guard")
    c, e = tool("sebbi_check_pack", {"pack": pk})
    chk("pack checks", not e, c)
    pb, e = tool("sebbi_publish_pack", {"pack": pk})
    chk("pack publishes", not e and pb.get("ok"), pb)
    lst, e = tool("sebbi_list_packs")
    chk("library lists packs", not e, str(lst)[:200])
    hp, e = tool("sebbi_check_human_proof", {"code": "HK-AAAA-BBBB"})
    chk("unknown Human Keys code reported as not found", e, hp)
    bl, e = tool("sebbi_billing_link", {"email": "ai@example.org", "devices": 3})
    chk("billing answers (Stripe not set up in a test copy)", bl.get("checkout_url") or bl.get("error") == "stripe_not_configured", bl)
    vc, e = tool("sebbi_verify_chain")
    chk("chain verifies", not e and vc.get("valid") is True, vc)
    st, info, _ = http("GET", "/mcp", headers={"Accept": "application/json"})
    chk("GET /mcp describes the connector", st == 200 and info.get("connector_url") == "https://sebbi.pro/mcp", info)
    st, _, h = http("OPTIONS", "/mcp")
    chk("browser preflight allowed", st == 204 and h.get("Access-Control-Allow-Origin") == "*", st)
    st, d, _ = http("GET", "/mcp")
    chk("stream request politely refused (no stream offered)", st == 405, st)
    st, b, _ = (lambda r: (r.status, r.read(), None))(urllib.request.urlopen(B + "/connect"))
    chk("/connect leads with the AI route", b"Or let your AI do all of it" in b and b"https://sebbi.pro/mcp" in b and b"cursor://" in b)
finally:
    p.terminate()
print("\npassed %d, failed %d" % (len(P), len(F)))
if F:
    print(open(w + "/l").read()[-2500:])
sys.exit(1 if F else 0)
