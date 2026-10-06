"""End-to-end check of the gateway and the AI-Decision-Receipt header (modules/gateway.py).
Runs in the no-network sandbox. Stand-in OpenAI and Anthropic servers run on this machine,
so streaming, blocking, receipts, fingerprints and load are tested without touching the
real providers or the live site."""
import fcntl, hashlib, http.client, http.server, json, os, random, socket, sqlite3, struct, subprocess, sys
import tempfile, threading, time, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, "modules")

HITS = {"openai": 0, "anthropic": 0, "seen": []}
OPENAI_JSON = {"id": "chatcmpl-test", "object": "chat.completion", "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello from the stand-in."}}]}


class Up(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        HITS["seen"].append({k.lower(): v for k, v in self.headers.items()})
        req = json.loads(body or b"{}")
        if self.path == "/v1/chat/completions":
            HITS["openai"] += 1
            if self.headers.get("Authorization") != "Bearer sk-test-123":
                return self._json(401, {"error": {"message": "bad key"}})
            if req.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                for i in range(5):
                    data = ("data: " + json.dumps({"choices": [{"delta": {"content": "tok%d " % i}}]}) + "\n\n").encode()
                    self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
                    self.wfile.flush()
                    time.sleep(0.2)
                end = b"data: [DONE]\n\n"
                self.wfile.write(b"%x\r\n%s\r\n0\r\n\r\n" % (len(end), end))
                return
            return self._json(200, OPENAI_JSON)
        if self.path == "/v1/messages":
            HITS["anthropic"] += 1
            if self.headers.get("x-api-key") != "ant-test-456" or not self.headers.get("anthropic-version"):
                return self._json(401, {"type": "error"})
            return self._json(200, {"id": "msg_test", "type": "message", "content": [{"type": "text", "text": "Hi from stand-in Claude."}]})
        return self._json(404, {})

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


up_o = http.server.ThreadingHTTPServer(("127.0.0.1", 8911), Up)
up_a = http.server.ThreadingHTTPServer(("127.0.0.1", 8912), Up)
for u in (up_o, up_a):
    threading.Thread(target=u.serve_forever, daemon=True).start()

w = tempfile.mkdtemp()
DB = w + "/a.db"
env = dict(os.environ, PORT="8885", DB_PATH=DB, ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0",
           GATEWAY_UPSTREAM_OPENAI="http://127.0.0.1:8911", GATEWAY_UPSTREAM_ANTHROPIC="http://127.0.0.1:8912")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(method, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "X-Forwarded-For": "10.6.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    rq = urllib.request.Request("http://127.0.0.1:8885" + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=90) as r:
            x = r.read()
            return r.status, (x if raw else (json.loads(x) if x else None)), r.headers
    except urllib.error.HTTPError as e:
        x = e.read()
        try:
            return e.code, (x if raw else json.loads(x)), e.headers
        except Exception:
            return e.code, x, e.headers


SID = {}


def rpc(method, params=None):
    hd = {"Mcp-Session-Id": SID["id"]} if SID.get("id") else {}
    return http_("POST", "/mcp", {"jsonrpc": "2.0", "id": random.randint(2, 10 ** 6), "method": method, "params": params or {}}, hd)


def tool(name, args):
    st, d, _ = rpc("tools/call", {"name": name, "arguments": args})
    return d["result"]["structuredContent"], d["result"]["isError"]


def account(email):
    t, _ = tool("sebbi_terms", {})
    a, _ = tool("sebbi_create_account", {"email": email, "terms_version": t["terms_version"], "customer_agreed": True})
    return a["api_key"]


import gateway as G  # noqa: E402  (for parse_receipt)

try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = http_("GET", "/x/arm/status")
    g = [r for r in a["results"] if r["module"] == "gateway"]
    chk("gateway arms", g and g[0].get("armed") is not False, g)
    st, s0, _ = http_("GET", "/x/gateway/status")
    chk("status armed", s0.get("armed") is True, s0)
    for path in ("/gateway", "/standard/ai-decision-receipt"):
        st, b, _ = http_("GET", path, raw=True)
        chk("page " + path, st == 200 and b"</html>" in b and b"__MAGIC__" not in b, st)

    st, d, h = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    SID["id"] = h.get("Mcp-Session-Id")
    key = account("gw1@example.org")
    key2 = account("gw2@example.org")
    chk("two test accounts", key and key2)
    st, tl, _ = rpc("tools/list")
    chk("AI connector lists sebbi_gateway_setup", "sebbi_gateway_setup" in [t["name"] for t in tl["result"]["tools"]])
    gs, e = tool("sebbi_gateway_setup", {"api_key": key, "stack": "Python Anthropic SDK"})
    chk("AI sets up the gateway", not e and gs["token"].startswith("gw_") and "anthropic.Anthropic(base_url=" in gs["change_this_line"], gs)
    st, tk, _ = http_("POST", "/x/gateway/token", {"label": "test"}, {"Authorization": "Bearer " + key})
    tok = tk.get("token")
    chk("gateway token by API", st == 200 and tok and tk["openai_base_url"].endswith("/g/%s/openai/v1" % tok), tk)

    chain_before = http_("GET", "/api/verify-chain")[1]

    # refusals
    st, d, _ = http_("POST", "/g/openai/v1/chat/completions", {"model": "m", "messages": []}, {"Authorization": "Bearer sk-test-123"})
    chk("no sebbi key -> 401 in OpenAI format", st == 401 and d["error"]["code"] == "sebbi_key_required", d)
    st, d, _ = http_("POST", "/g/gw_" + "0" * 32 + "/openai/v1/chat/completions", {"model": "m"}, {"Authorization": "Bearer sk-test-123"})
    chk("unknown token -> 401", st == 401, d)
    st, d, _ = http_("POST", "/g/nope/v1/x", {}, {"X-Sebbi-Key": key})
    chk("unknown provider -> 404", st == 404, d)
    st, d, _ = http_("POST", "/g/openai/v1/../../x/arm/status", {}, {"X-Sebbi-Key": key})
    chk("path tricks refused", st in (400, 404), (st, d))
    chk("refusals never reached the provider", HITS["openai"] == 0, HITS)

    # OpenAI, plain
    prompt = "What is the capital of Northumberland? secret-prompt-marker-77"
    body = json.dumps({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "user": "cust-42"}).encode()
    st, d, hd = http_("POST", "/g/openai/v1/chat/completions", body, {"Authorization": "Bearer sk-test-123", "X-Sebbi-Key": key})
    rc = G.parse_receipt(hd.get("AI-Decision-Receipt"))
    chk("OpenAI call answered exactly", st == 200 and d == OPENAI_JSON, (st, d))
    chk("receipt header", rc.get("v") == 1 and rc.get("issuer") == "sebbi.pro" and rc.get("decision") in ("ALLOW", "CHALLENGE")
        and isinstance(rc.get("block"), int) and rc.get("req") == hashlib.sha256(body).hexdigest()
        and rc.get("verify") == "https://sebbi.pro/forever?block=%d" % rc.get("block"), hd.get("AI-Decision-Receipt"))
    last = HITS["seen"][-1]
    chk("provider key passed through; sebbi key and client IP did not", last.get("authorization") == "Bearer sk-test-123"
        and "x-sebbi-key" not in last and "x-forwarded-for" not in last, last)
    cid = hd.get("AI-Decision-Call")
    ev = sqlite3.connect(DB).execute("SELECT event_json, audit_hash FROM audit_log WHERE id=?", (rc["block"],)).fetchone()
    evj = json.loads(ev[0])
    chk("decision sealed with the request fingerprint, never the prompt", ev[1] == rc["seal"] and evj["request_sha256"] == rc["req"]
        and evj["user_id"] == "cust-42" and evj["model"] == "gpt-4o-mini" and "secret-prompt-marker-77" not in ev[0], evj)

    # OpenAI streaming via token URL
    c = http.client.HTTPConnection("127.0.0.1", 8885, timeout=60)
    sb = json.dumps({"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "stream please"}]}).encode()
    t0 = time.time()
    c.request("POST", "/g/%s/openai/v1/chat/completions" % tok, body=sb, headers={"Authorization": "Bearer sk-test-123", "Content-Type": "application/json"})
    r = c.getresponse()
    first = r.read1(65536)
    t_first = time.time() - t0
    rest = b""
    while True:
        x = r.read1(65536)
        if not x:
            break
        rest += x
    t_all = time.time() - t0
    streamed = first + rest
    chk("streams token by token", r.status == 200 and b"tok0" in first and t_first < 0.6 and t_all > 0.8, (r.status, t_first, t_all, first[:80]))
    chk("whole stream delivered", streamed.count(b"data: ") == 6 and streamed.endswith(b"data: [DONE]\n\n"), streamed[-60:])
    srx = G.parse_receipt(r.getheader("AI-Decision-Receipt"))
    scid = r.getheader("AI-Decision-Call")
    chk("stream carries a receipt", isinstance(srx.get("block"), int) and srx.get("block") != rc["block"], srx)
    time.sleep(1.0)
    st, cr, _ = http_("GET", "/x/gateway/call?id=" + scid)
    chk("call record fingerprints match what was sent and received", st == 200 and cr["request_sha256"] == hashlib.sha256(sb).hexdigest()
        and cr["response_sha256"] == hashlib.sha256(streamed).hexdigest() and cr["decision"] == srx["decision"], cr)
    chk("fingerprints sent to the Bitcoin notary", cr["notary"].get("request", "").startswith("NT-") and cr["notary"].get("response", "").startswith("NT-"), cr["notary"])

    # Anthropic via token
    ab = json.dumps({"model": "claude-x", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}).encode()
    st, d, hd = http_("POST", "/g/%s/anthropic/v1/messages" % tok, ab, {"x-api-key": "ant-test-456", "anthropic-version": "2023-06-01"})
    chk("Anthropic call answered", st == 200 and d.get("id") == "msg_test" and G.parse_receipt(hd.get("AI-Decision-Receipt")).get("block"), (st, d))

    # blocking
    before = HITS["openai"]
    st, d, hd = http_("POST", "/g/openai/v1/chat/completions", body, {"Authorization": "Bearer sk-test-123", "X-Sebbi-Key": key,
                      "X-Sebbi-Country": "KP", "X-Sebbi-Anomaly": "1", "X-Sebbi-Device-Risk": "1", "X-Sebbi-Amount": "1000000",
                      "X-Sebbi-On-Challenge": "block", "X-Sebbi-User": "risky-user"})
    brc = G.parse_receipt(hd.get("AI-Decision-Receipt"))
    chk("risky call stopped before the provider", st == 403 and d["error"]["code"] == "sebbi_blocked" and HITS["openai"] == before
        and brc.get("decision") in ("BLOCK", "CHALLENGE"), (st, d, brc))
    st, bcr, _ = http_("GET", "/x/gateway/call?id=" + hd.get("AI-Decision-Call"))
    chk("blocked call recorded as stopped", bcr.get("stopped_before_provider") is True and bcr.get("response_sha256") is None, bcr)

    # the header on /api/govern
    gev = {"user_id": "u1", "action": "loan_approval", "amount": 100, "country": "UK", "device_id": "d1", "anomaly": 0, "device_risk": 0}
    st, gd, gh = http_("POST", "/api/govern", gev, {"Authorization": "Bearer " + key})
    grc = G.parse_receipt(gh.get("AI-Decision-Receipt"))
    chk("/api/govern answers carry the receipt header", st == 200 and grc.get("block") == gd["block_index"] and grc.get("seal") == gd["audit_hash"]
        and grc.get("decision") == gd["decision"], (gh.get("AI-Decision-Receipt"), gd.get("block_index")))
    chk("/api/govern body unchanged", "decision" in gd and "audit_hash" in gd and "AI-Decision-Receipt" not in json.dumps(gd))
    st, gd2, gh2 = http_("POST", "/api/govern", {"user_id": "u1"}, {"Authorization": "Bearer " + key})
    chk("govern errors get no receipt", st == 400 and not gh2.get("AI-Decision-Receipt"), (st, gh2.get("AI-Decision-Receipt")))
    st, pr, _ = http_("POST", "/x/gateway/parse", {"header": gh.get("AI-Decision-Receipt")})
    chk("parse route", pr["receipt"].get("block") == gd["block_index"], pr)

    # load: 40 concurrent streaming calls on a second key
    res, lock = [], threading.Lock()

    def one(i):
        try:
            cc = http.client.HTTPConnection("127.0.0.1", 8885, timeout=120)
            bb = json.dumps({"model": "m", "stream": True, "messages": [{"role": "user", "content": "load %d" % i}]}).encode()
            t = time.time()
            cc.request("POST", "/g/openai/v1/chat/completions", body=bb, headers={"Authorization": "Bearer sk-test-123", "X-Sebbi-Key": key2, "Content-Type": "application/json"})
            rr = cc.getresponse()
            data = rr.read()
            with lock:
                res.append((rr.status, G.parse_receipt(rr.getheader("AI-Decision-Receipt")).get("block"), data.count(b"data: "), time.time() - t))
        except Exception as ex:
            with lock:
                res.append((0, None, 0, str(ex)))

    ts = [threading.Thread(target=one, args=(i,)) for i in range(40)]
    t0 = time.time()
    [t.start() for t in ts]
    [t.join() for t in ts]
    wall = time.time() - t0
    ok = [x for x in res if x[0] == 200 and x[2] == 6]
    blocks = {x[1] for x in ok}
    times = sorted(x[3] for x in ok)
    print("  note 40 concurrent streams: wall %.2fs, median %.2fs (stand-in takes 1.0s), slowest %.2fs" % (wall, times[len(times) // 2] if times else -1, times[-1] if times else -1))
    chk("40 concurrent streams all delivered", len(ok) == 40, res[:5])
    chk("each one sealed in its own block", len(blocks) == 40, len(blocks))
    chk("gateway adds little delay under load", times and times[len(times) // 2] < 2.5, times[:3])

    chain_after = http_("GET", "/api/verify-chain")[1]
    chk("chain still valid after everything", chain_after.get("valid") is True and chain_after["blocks"] > chain_before["blocks"], (chain_before, chain_after))

    # revoke, then provider down
    st, rv, _ = http_("POST", "/x/gateway/revoke", {"token": tok}, {"Authorization": "Bearer " + key})
    st2, d, _ = http_("POST", "/g/%s/openai/v1/chat/completions" % tok, body, {"Authorization": "Bearer sk-test-123"})
    chk("revoked token stops working", rv.get("revoked") is True and st2 == 401, (rv, st2))
    up_a.shutdown()
    up_a.server_close()
    st, d, hd = http_("POST", "/g/anthropic/v1/messages", ab, {"x-api-key": "ant-test-456", "anthropic-version": "2023-06-01", "X-Sebbi-Key": key})
    chk("provider down -> clean 502 with receipt", st == 502 and d.get("type") == "error" and hd.get("AI-Decision-Receipt"), (st, d))

    st, s1, _ = http_("GET", "/x/gateway/status")
    chk("status counts", s1["since_start"]["forwarded"] >= 43 and s1["since_start"]["blocked"] >= 1 and s1["receipt_header_on_govern"], s1)
    st, o, e = None, *tool("sebbi_overview", {})
    chk("existing connector tools still work", not e and o.get("products"))
finally:
    p.terminate()
    up_o.shutdown()

print("\n%d passed, %d failed" % (len(P), len(F)))
if F:
    print("".join(open(w + "/l").readlines()[-25:]))
sys.exit(1 if F else 0)
