"""Check the admin Monitor (modules/monitor.py + the Monitor tab in admin.html).
Throwaway copy, no outside network. Signs up, links devices, visits pages, downloads
a tool, then checks the monitor sees all of it - and only answers to an admin token."""
import fcntl, json, os, random, socket, struct, subprocess, sys, tempfile, time, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8893", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0",
           ADMIN_PASSWORD="monitor-test-pw")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36"


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(m, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": UA,
         "X-Forwarded-For": "10.4.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    rq = urllib.request.Request("http://127.0.0.1:8893" + path, data=json.dumps(body).encode() if body is not None else None, method=m, headers=h)
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


try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = http_("GET", "/x/arm/status")
    m = [r for r in a["results"] if r["module"] == "monitor"]
    chk("monitor arms", m and m[0].get("armed") is not False, m)
    st, d, h = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    sid = {"Mcp-Session-Id": h.get("Mcp-Session-Id")}

    def tool(n, a):
        return http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": n, "arguments": a}}, sid)[1]["result"]["structuredContent"]
    t = tool("sebbi_terms", {})
    key = tool("sebbi_create_account", {"name": "Morgan Lead", "email": "lead@example.org", "company": "Lead Ltd", "terms_version": t["terms_version"], "customer_agreed": True})["api_key"]
    for dv in ("phone-1", "laptop-2", "till-3"):
        http_("POST", "/api/govern", {"user_id": "u", "action": "x", "amount": 1, "country": "UK", "device_id": dv, "anomaly": 0, "device_risk": 0}, {"Authorization": "Bearer " + key})
    vis = "10.77.1.1"
    for path in ("/", "/pilot", "/gateway", "/bitcoin"):
        http_("GET", path, headers={"X-Forwarded-For": vis, "Referer": "https://www.linkedin.com/feed/"}, raw=True)
    http_("GET", "/forever-verify.py", headers={"X-Forwarded-For": vis}, raw=True)
    http_("GET", "/pilot", headers={"User-Agent": "Googlebot/2.1", "X-Forwarded-For": "10.9.9.9"}, raw=True)

    st, d, _ = http_("GET", "/x/monitor/all")
    chk("refuses without an admin token", st == 401, (st, d))
    st, d, _ = http_("GET", "/x/monitor/all", headers={"Authorization": "Bearer " + key})
    chk("refuses a customer API key", st == 401, st)
    st, tok, _ = http_("POST", "/admin/auth", {"password": "monitor-test-pw"})
    T = tok["token"]
    st, d, _ = http_("GET", "/x/monitor/all", headers={"Authorization": "Bearer " + T})
    chk("admin token gets the snapshot", st == 200 and "kpi" in d, (st, str(d)[:300]))
    k = d["kpi"]
    c = [x for x in d["customers"] if x["email"] == "lead@example.org"]
    chk("sees the signup, with company, devices and decisions", c and c[0]["org"] == "Lead Ltd" and c[0]["devices"] == 3 and c[0]["decisions"] >= 3
        and c[0]["via_ai"] is True and c[0]["trial_days_left"] in (89, 90), c)
    chk("signups and devices today", k["signups_today"] >= 1 and k["devices_today"] >= 3, k)
    chk("counts the visitor once, not the bot", k["visitors_today"] >= 1 and k["bots_today"] >= 1, k)
    chk("records the download", k["downloads_today"] >= 1 and any(x["path"] == "/forever-verify.py" for x in d["downloads"]), d["downloads"][:3])
    chk("top pages and referrers", any(x["path"] == "/pilot" for x in d["pages"]) and any(x["site"] == "www.linkedin.com" for x in d["referrers"]), (d["pages"][:5], d["referrers"]))
    chk("14-day series", len(d["series"]["days"]) == 14 and d["series"]["signups"][-1] >= 1 and d["series"]["devices"][-1] >= 3, d["series"])
    chk("live feed has the signup and devices", any(f["kind"] == "signup" for f in d["feed"]) and any(f["kind"] == "device" for f in d["feed"]), d["feed"][:4])
    chk("health: chain valid, modules armed", d["health"]["chain"]["valid"] is True and d["health"]["modules"]["notary"]["loaded"], d["health"]["chain"])
    chk("visitor identity never stored", "10.77.1.1" not in json.dumps(d) and UA not in json.dumps(d))
    st, page, _ = http_("GET", "/admin", raw=True)
    chk("admin page has the Monitor tab first and every old tab", st == 200 and page.find(b"show('monitor',this)") < page.find(b"show('blocks',this)")
        and all(t in page for t in (b"show('routes'", b"show('chain'", b"show('network'", b"show('traffic'", b"show('customers'", b"show('contacts'", b"show('referrals'")), st)
    st, v, _ = http_("GET", "/api/verify-chain")
    chk("chain valid", v.get("valid") is True)
finally:
    p.terminate()
print("\n%d passed, %d failed" % (len(P), len(F)))
sys.exit(1 if F else 0)
