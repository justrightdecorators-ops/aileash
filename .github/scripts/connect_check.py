"""End-to-end check of /connect, /build and the homepage strip (modules/connect.py),
run by checks.yml in the no-network sandbox."""
import os, sys, subprocess, time, urllib.request, tempfile, socket, fcntl, struct, json, random

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8844", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def req(m, u, b=None, key=None, raw=False):
    h = {"Content-Type": "application/json", "X-Forwarded-For": "10.%d.%d.2" % (random.randint(0, 250), random.randint(0, 250))}
    if key:
        h["Authorization"] = "Bearer " + key
    rq = urllib.request.Request("http://127.0.0.1:8844" + u, data=json.dumps(b).encode() if b is not None else None, method=m, headers=h)
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            x = r.read()
            return r.status, (x if raw else json.loads(x or b"{}")), r.headers
    except urllib.error.HTTPError as e:
        x = e.read()
        try:
            return e.code, json.loads(x), None
        except Exception:
            return e.code, x, None


TEMPLATES = {
    "Stop runaway agents": [("loop_count >= 3 and unattended", "block"), ("loop_count >= 3", "challenge"), ("burst >= 0.8", "challenge")],
    "Guard the budget": [("exposure >= 0.7", "challenge"), ("size < 0.2 and tools == 0 and deterministic", "downgrade")],
    "Careful when nobody's watching": [("unattended and score >= 0.6", "block"), ("unattended and novelty >= 0.8", "challenge")],
}
try:
    for _ in range(40):
        try:
            if req("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = req("GET", "/x/arm/status")
    cn = [r for r in a["results"] if r["module"] == "connect"]
    chk("arms", a.get("armed") and cn and cn[0].get("armed"), cn)
    for u, t in (("/connect", b"Plug your AI into"), ("/build", b"Write the rules")):
        st, b, h = req("GET", u, raw=True)
        chk("page " + u, st == 200 and t in b and int(h.get("Content-Length")) == len(b), st)
    st, b, h = req("GET", "/", raw=True)
    chk("homepage strip added once", b.count(b'class="sbx"') == 1, b.count(b'class="sbx"'))
    chk("homepage length correct", int(h.get("Content-Length")) == len(b))
    chk("AI Business feature linked", b"aibusiness.vc/startups/sebbi-aileash-justin-dobson-seal-every-ai-decision" in b)
    chk("homepage still branded (no town)", b"Blyth" not in b)
    st, b, h = req("GET", "/developers", raw=True)
    chk("strip only on the homepage", b'class="sbx"' not in b)
    for name, rules in TEMPLATES.items():
        m = {"name": name, "author": "Connect check", "version": "1.0.0", "vertical": "general", "summary": "test",
             "rules": [{"when": w_, "then": t, "why": "because"} for w_, t in rules], "default": "allow"}
        st, d, _ = req("POST", "/x/packs/validate", {"pack": m})
        chk("builder template validates: " + name, st == 200 and d.get("ok") is not False and not d.get("error"), d)
    st, d, _ = req("POST", "/x/packs/publish", {"pack": m})
    chk("builder publishes to the library", st == 200 and d.get("ok"), d)
    st, k, _ = req("POST", "/signup", {"name": "Connect Check", "email": "connect@example.org", "org": "Check Ltd", "product": "aileash", "devices": 1})
    key = k.get("api_key")
    chk("connect page gets a key", bool(key), k)
    st, g, _ = req("POST", "/api/govern", {"user_id": "customer-42", "action": "refund", "amount": 120, "country": "UK",
                                           "device_id": "sebbi-connect-test", "anomaly": 0.1, "device_risk": 0.05}, key=key)
    chk("connect test decision seals", st == 200 and g.get("block_index") and g.get("decision") in ("ALLOW", "CHALLENGE", "BLOCK"), g)
    st, v, _ = req("GET", "/api/verify-chain")
    chk("chain still verifies", v.get("valid") is True, v)
finally:
    p.terminate()
print("\npassed %d, failed %d" % (len(P), len(F)))
if F:
    print(open(w + "/l").read()[-2000:])
sys.exit(1 if F else 0)
