"""End-to-end check of Spend Gate (modules/spendgate.py). Throwaway copy, no outside network.
Sets an agent's limits, then checks approvals, every refusal reason, one-shot confirm, offline
signature verification, and that the chain stays valid. Proves sebbi.pro holds no funds."""
import fcntl, json, os, random, socket, struct, subprocess, sys, tempfile, time, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
sys.path.insert(0, "modules")
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8897", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(m, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "X-Forwarded-For": "10.2.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    rq = urllib.request.Request("http://127.0.0.1:8897" + path, data=json.dumps(body).encode() if body is not None else None, method=m, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            x = r.read()
            return r.status, (json.loads(x) if x else None)
    except urllib.error.HTTPError as e:
        x = e.read()
        try:
            return e.code, json.loads(x)
        except Exception:
            return e.code, x


SID = {}


def tool(n, a):
    st, d = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": n, "arguments": a}}, {"Mcp-Session-Id": SID["id"]})
    return d["result"]["structuredContent"]


try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a = http_("GET", "/x/arm/status")
    m = [r for r in a["results"] if r["module"] == "spendgate"]
    chk("spendgate arms", m and m[0].get("armed") is not False, m)
    st, s1 = http_("GET", "/x/spendgate/status")
    chk("status: armed, holds no funds", s1["armed"] and s1["holds_funds"] is False, s1)
    import urllib.request as _U
    with _U.urlopen("http://127.0.0.1:8897/spend") as _r:
        _pg = _r.read()
    chk("spend page", _r.status == 200 and b"Spend Gate" in _pg and b"__MAGIC__" not in _pg)

    st, d, h = (lambda r: (r[0], r[1], None))(http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}))
    # grab the session id from headers via a second raw call
    import urllib.request as U
    rq = U.Request("http://127.0.0.1:8897/mcp", data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}).encode(), headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"})
    with U.urlopen(rq) as r:
        SID["id"] = r.headers.get("Mcp-Session-Id")
    t = tool("sebbi_terms", {})
    key = tool("sebbi_create_account", {"name": "Spend Co", "email": "spend@co.co.uk", "terms_version": t["terms_version"], "customer_agreed": True})["api_key"]
    A = {"Authorization": "Bearer " + key}

    st, d = http_("POST", "/x/spendgate/request", {"agent": "bot", "amount": 10, "payee": "AWS"}, A)
    chk("refuses to approve before limits are set", st == 409 and d["error"] == "no_policy", d)

    st, d = http_("POST", "/x/spendgate/policy", {"agent": "bot", "per_tx": 100, "daily": 250, "currency": "GBP", "payees": ["AWS", "OpenAI"]}, A)
    chk("sets the policy", st == 200 and d["ok"] and "£100.00" in d["per_transaction"], d)

    st, ok = http_("POST", "/x/spendgate/request", {"agent": "bot", "amount": 50, "payee": "AWS", "reason": "compute"}, A)
    chk("approves within the limits, signed and sealed", ok["decision"] == "APPROVED" and ok["token"].startswith("sbg1.") and ok["block_index"], ok)
    tok = ok["token"]

    st, over = http_("POST", "/x/spendgate/request", {"agent": "bot", "amount": 500, "payee": "AWS"}, A)
    chk("denies over the per-transaction limit", over["decision"] == "DENIED" and any("per-transaction" in r for r in over["reasons"]), over)
    st, bad = http_("POST", "/x/spendgate/request", {"agent": "bot", "amount": 20, "payee": "DodgyLtd"}, A)
    chk("denies a payee not on the allow-list", bad["decision"] == "DENIED" and any("allow-list" in r for r in bad["reasons"]), bad)

    # verify the approved token with no key (offline-style signature check)
    st, v = http_("GET", "/x/spendgate/verify?token=" + tok)
    chk("verify: valid, spendable, signature checks", v["valid"] and v["spendable"] and v["decision"] == "APPROVED" and v["amount"] == "£50.00", v)
    tampered = tok[:-4] + ("aaaa" if not tok.endswith("aaaa") else "bbbb")
    st, vt = http_("GET", "/x/spendgate/verify?token=" + tampered)
    chk("a tampered token fails the signature", vt.get("valid") is False, vt)

    # confirm one-shot
    st, c1 = http_("POST", "/x/spendgate/confirm", {"token": tok}, A)
    chk("confirm marks it spent", st == 200 and c1["ok"], c1)
    st, c2 = http_("POST", "/x/spendgate/confirm", {"token": tok}, A)
    chk("cannot confirm twice", st == 409 and c2["error"] == "already_confirmed", c2)
    st, v2 = http_("GET", "/x/spendgate/verify?token=" + tok)
    chk("verify shows an already-spent token as not spendable", v2["spendable"] is False and "already spent" in v2.get("problem", ""), v2)

    # daily cap: £50 confirmed + approvals; push past £250
    tot = 50
    denied_on_cap = False
    for i in range(6):
        st, r = http_("POST", "/x/spendgate/request", {"agent": "bot", "amount": 60, "payee": "OpenAI"}, A)
        if r["decision"] == "APPROVED":
            tot += 60
        elif any("daily cap" in x for x in r.get("reasons", [])):
            denied_on_cap = True
            break
    chk("daily cap is enforced across payments", denied_on_cap and tot <= 250 + 60, tot)

    # the AI connector path
    st, tl = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 9, "method": "tools/list"}, {"Mcp-Session-Id": SID["id"]})
    names = [t["name"] for t in tl["result"]["tools"]]
    chk("AI connector lists the three spend tools", {"sebbi_spend_policy", "sebbi_spend_request", "sebbi_spend_verify"} <= set(names), names)
    tool("sebbi_spend_policy", {"api_key": key, "agent": "ai-bot", "per_tx": 30, "daily": 60})
    r = tool("sebbi_spend_request", {"api_key": key, "agent": "ai-bot", "amount": 20, "payee": "Stripe"})
    chk("AI agent gets an approval token", r["decision"] == "APPROVED" and r["token"].startswith("sbg1."), r)
    r2 = tool("sebbi_spend_request", {"api_key": key, "agent": "ai-bot", "amount": 40, "payee": "Stripe"})
    chk("AI agent is refused over its limit", r2["decision"] == "DENIED", r2)
    rv = tool("sebbi_spend_verify", {"token": r["token"]})
    chk("AI can verify a token with no key", rv["valid"] and rv["spendable"], rv)
    o = tool("sebbi_overview", {})
    chk("existing connector tools still work", bool(o.get("products")))

    st, v = http_("GET", "/api/verify-chain")
    chk("chain valid after every spend decision", v.get("valid") is True and v["blocks"] > 0, v)
    st, pk1 = http_("GET", "/x/spendgate/pubkey")
    st, pk2 = http_("GET", "/x/continuity/pubkey")
    chk("signs with the same key as continuity", pk1["public_key"] == pk2["public_key"], (pk1.get("public_key"), pk2.get("public_key")))
finally:
    p.terminate()
print("\n%d passed, %d failed" % (len(P), len(F)))
if F:
    print("".join(open(w + "/l").readlines()[-20:]))
sys.exit(1 if F else 0)
