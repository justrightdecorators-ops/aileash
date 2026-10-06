"""End-to-end check of the paid pilot and the gateway's free allowance (modules/pilot.py).
Runs in the no-network sandbox with a stand-in Stripe and a stand-in OpenAI, so no real
card is charged and no real provider is called."""
import fcntl, http.server, json, os, random, socket, struct, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

SESS = {}


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path == "/v1/checkout/sessions":
            if self.headers.get("Authorization") != "Bearer sk_test_fake":
                return self._j(401, {"error": {"message": "bad key"}})
            f = dict(urllib.parse.parse_qsl(body.decode()))
            sid = "cs_test_%06d" % random.randint(0, 999999)
            SESS[sid] = {"form": f, "paid": False}
            return self._j(200, {"id": sid, "url": "https://checkout.stripe.test/" + sid})
        if self.path == "/v1/chat/completions":
            return self._j(200, {"id": "x", "choices": []})
        return self._j(404, {})

    def do_GET(self):
        if self.path.startswith("/v1/checkout/sessions/"):
            sid = urllib.parse.unquote(self.path.rsplit("/", 1)[1])
            if sid not in SESS:
                return self._j(404, {"error": {"message": "no such session"}})
            x = SESS[sid]
            return self._j(200, {"id": sid, "payment_status": "paid" if x["paid"] else "unpaid",
                                 "amount_total": int(x["form"]["line_items[0][price_data][unit_amount]"])})
        return self._j(404, {})


http.server.ThreadingHTTPServer.request_queue_size = 64
fake = http.server.ThreadingHTTPServer(("127.0.0.1", 8921), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()

w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8889", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0",
           STRIPE_SECRET="sk_test_fake", PILOT_STRIPE_BASE="http://127.0.0.1:8921/v1", GATEWAY_FREE_CALLS="3",
           GATEWAY_UPSTREAM_OPENAI="http://127.0.0.1:8921", ADMIN_PASSWORD="admin-test-pw")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(m, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "X-Forwarded-For": "10.5.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    rq = urllib.request.Request("http://127.0.0.1:8889" + path, data=data, method=m, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            x = r.read()
            return r.status, (x if raw else (json.loads(x) if x else None)), r.headers
    except urllib.error.HTTPError as e:
        x = e.read()
        try:
            return e.code, (x if raw else json.loads(x)), e.headers
        except Exception:
            return e.code, x, e.headers


SID = {}


def tool(n, a):
    st, d, _ = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": n, "arguments": a}}, {"Mcp-Session-Id": SID["id"]})
    return d["result"]["structuredContent"]


try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = http_("GET", "/x/arm/status")
    m = [r for r in a["results"] if r["module"] == "pilot"]
    chk("pilot arms", m and m[0].get("armed") is not False, m)
    st, s1, _ = http_("GET", "/x/pilot/status")
    chk("status: payments on, £495, 3 free calls (test setting)", s1["armed"] and s1["payments_on"] and s1["price_gbp"] == 495.0 and s1["gateway_free_calls"] == 3, s1)
    st, pg, _ = http_("GET", "/pilot", raw=True)
    chk("pilot page", st == 200 and b"Governed in" in pg and b"\xc2\xa3495" in pg, st)
    st, home, _ = http_("GET", "/", raw=True)
    chk("homepage pilot button", b'href="/pilot" style=' in home)

    # gateway allowance on an ordinary trial key
    st, d, h = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    SID["id"] = h.get("Mcp-Session-Id")
    t = tool("sebbi_terms", {})
    key = tool("sebbi_create_account", {"email": "buyer@example.org", "terms_version": t["terms_version"], "customer_agreed": True})["api_key"]
    codes = []
    for i in range(4):
        st, d, _ = http_("POST", "/g/openai/v1/chat/completions", {"model": "m", "messages": []}, {"X-Sebbi-Key": key, "Authorization": "Bearer sk-x"})
        codes.append(st)
    chk("free allowance, then a clear 402", codes == [200, 200, 200, 402], codes)
    chk("402 says how to keep going, in OpenAI format", d["error"]["code"] == "gateway_allowance_used" and "50p per device" in d["error"]["message"], d)
    st, g, _ = http_("POST", "/api/govern", {"user_id": "u", "action": "x", "amount": 1, "country": "UK", "device_id": "d", "anomaly": 0, "device_risk": 0}, {"Authorization": "Bearer " + key})
    chk("existing products untouched: /api/govern still free on the trial", st == 200 and "decision" in g, (st, g))

    # buying the pilot
    st, d, _ = http_("POST", "/x/pilot/checkout", {"name": "Alex"})
    chk("checkout needs details", st == 400, d)
    st, d, _ = http_("POST", "/x/pilot/checkout", {"name": "Alex Buyer", "email": "buyer@example.org", "company": "Buyer Ltd <script>", "notes": "chatbot"})
    sid = d.get("url", "").rsplit("/", 1)[-1]
    chk("checkout opens Stripe for £495 in GBP", st == 200 and sid in SESS and SESS[sid]["form"]["line_items[0][price_data][unit_amount]"] == "49500"
        and SESS[sid]["form"]["line_items[0][price_data][currency]"] == "gbp" and SESS[sid]["form"]["mode"] == "payment", d)
    st, th, _ = http_("GET", "/pilot/thanks?session_id=" + sid, raw=True)
    chk("unpaid session waits, shows no key", st == 200 and b"Confirming your payment" in th and b"al_live_" not in th, th[:200])
    SESS[sid]["paid"] = True
    st, th, _ = http_("GET", "/pilot/thanks?session_id=" + sid, raw=True)
    chk("paid: live, existing key linked (email already had one)", st == 200 and b"live." in th and b"linked to the sebbi.pro key you already have" in th, th[-600:])
    codes = [http_("POST", "/g/openai/v1/chat/completions", {"model": "m"}, {"X-Sebbi-Key": key, "Authorization": "Bearer sk-x"})[0] for _ in range(3)]
    chk("pilot lifts the gateway allowance", codes == [200, 200, 200], codes)

    # a brand-new buyer gets a key and gateway URL on the spot
    st, d, _ = http_("POST", "/x/pilot/checkout", {"name": "Sam New", "email": "new@example.org", "company": "New Co"})
    sid2 = d["url"].rsplit("/", 1)[-1]
    SESS[sid2]["paid"] = True
    st, th, _ = http_("GET", "/pilot/thanks?session_id=" + sid2, raw=True)
    txt = th.decode()
    chk("new buyer: key and gateway URL shown", "al_live_" in txt and "/g/gw_" in txt and "/openai/v1" in txt, txt[-800:])
    newkey = txt.split("al_live_")[1][:48]
    gw = txt.split("/g/gw_")[1][:32]
    st, d, hd = http_("POST", "/g/gw_%s/openai/v1/chat/completions" % gw, {"model": "m"}, {"Authorization": "Bearer sk-x"})
    chk("their gateway URL works straight away", st == 200 and hd.get("AI-Decision-Receipt"), (st, d))
    st, th2, _ = http_("GET", "/pilot/thanks?session_id=" + sid2, raw=True)
    chk("revisiting the page does not create a second key", th2.decode().count("al_live_") == 1 and txt.split("al_live_")[1][:48] in th2.decode())
    st, d, _ = http_("GET", "/pilot/thanks?session_id=cs_test_nope00", raw=True)
    chk("unknown order handled", st == 200 and b"couldn" in d)

    st, o, _ = http_("GET", "/x/pilot/orders?admin=wrong")
    chk("orders are admin only", st == 403)
    st, o, _ = http_("GET", "/x/pilot/orders?admin=admin-test-pw")
    chk("orders list for Justin", st == 200 and o["paid_total_gbp"] == 990.0 and all("<" not in x["company"] for x in o["orders"]), o)
    st, v, _ = http_("GET", "/api/verify-chain")
    chk("chain valid", v.get("valid") is True, v)
finally:
    p.terminate()
    fake.shutdown()

print("\n%d passed, %d failed" % (len(P), len(F)))
if F:
    print("".join(open(w + "/l").readlines()[-20:]))
sys.exit(1 if F else 0)
