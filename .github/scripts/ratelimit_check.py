"""Check modules/ratelimit.py: per-key limits are raised from 60 a minute, and still enforced.
Boots a throwaway copy with RATE_TRIAL_MIN=120 in the no-network sandbox."""
import fcntl, json, os, random, socket, struct, subprocess, sys, tempfile, time, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8887", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0",
           RATE_TRIAL_MIN="120")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def http_(m, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "X-Forwarded-For": "10.8.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    rq = urllib.request.Request("http://127.0.0.1:8887" + path, data=json.dumps(body).encode() if body is not None else None, method=m, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}"), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    http_("GET", "/x/arm/status")
    st, s1, _ = http_("GET", "/x/ratelimit/status")
    chk("armed with the configured limit", s1.get("armed") and s1["per_key"]["trial"]["per_minute"] == 120, s1)
    st, d, h = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
                     {"Accept": "application/json, text/event-stream"})
    sid = {"Mcp-Session-Id": h.get("Mcp-Session-Id"), "Accept": "application/json, text/event-stream"}

    def tool(n, a):
        st, d, _ = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": n, "arguments": a}}, sid)
        return d["result"]["structuredContent"]
    t = tool("sebbi_terms", {})
    key = tool("sebbi_create_account", {"email": "rl@example.org", "terms_version": t["terms_version"], "customer_agreed": True})["api_key"]
    ev = {"user_id": "u", "action": "x", "amount": 1, "country": "UK", "device_id": "d", "anomaly": 0, "device_risk": 0}
    codes = [http_("POST", "/api/govern", ev, {"Authorization": "Bearer " + key})[0] for _ in range(121)]
    chk("well past the old 60-a-minute limit", codes[:120].count(200) == 120, codes.count(200))
    chk("and still enforced at the new limit", codes[120] == 429, codes[115:])
    st, v, _ = http_("GET", "/api/verify-chain")
    chk("chain valid", v.get("valid") is True, v)
finally:
    p.terminate()
print("\n%d passed, %d failed" % (len(P), len(F)))
sys.exit(1 if F else 0)
