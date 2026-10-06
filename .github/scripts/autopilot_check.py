"""Check the autopilot follow-ups (modules/autopilot.py). Throwaway copy, no outside network,
a stand-in Brevo catches every email. Seeds customers at each stage and checks the right
email goes to the right person, once, with a working unsubscribe."""
import fcntl, http.server, json, os, random, socket, sqlite3, struct, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
MAIL = []


class Brevo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if self.path == "/v3/smtp/email" and self.headers.get("api-key") == "brevo-test":
            MAIL.append(body)
            raw = b'{"messageId":"x"}'
            self.send_response(201)
        else:
            raw = b'{}'
            self.send_response(401)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


fake = http.server.ThreadingHTTPServer(("127.0.0.1", 8931), Brevo)
threading.Thread(target=fake.serve_forever, daemon=True).start()
w = tempfile.mkdtemp()
DB = w + "/a.db"
env = dict(os.environ, PORT="8895", DB_PATH=DB, ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0", ADMIN_PASSWORD="ap-test-pw",
           BREVO_API_KEY="brevo-test", AUTOPILOT_BREVO_BASE="http://127.0.0.1:8931/v3", AUTOPILOT_FIRST_DELAY="100000")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(m, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "X-Forwarded-For": "10.3.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    rq = urllib.request.Request("http://127.0.0.1:8895" + path, data=json.dumps(body).encode() if body is not None else None, method=m, headers=h)
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


def seed_key(email, name, days_ago, paid=0):
    k = "al_live_" + os.urandom(24).hex()
    c = sqlite3.connect(DB, timeout=30)
    c.execute("INSERT INTO api_keys(key,email,name,org,product,created,active,is_paid,plan_type) VALUES(?,?,?,?,?,?,1,?,?)",
              (k, email, name, name.split()[-1] + " Ltd", "aileash", time.time() - days_ago * 86400, paid, "trial"))
    c.commit(); c.close()
    return k


try:
    for _ in range(60):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = http_("GET", "/x/arm/status")
    m = [r for r in a["results"] if r["module"] == "autopilot"]
    chk("autopilot arms", m and m[0].get("armed") is not False, m)
    st, s1, _ = http_("GET", "/x/autopilot/status")
    chk("status: armed, email configured, not paused", s1["armed"] and s1["email_configured"] and not s1["paused"], s1)

    st, d, h = http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
    sid = {"Mcp-Session-Id": h.get("Mcp-Session-Id")}

    def tool(n, a):
        return http_("POST", "/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": n, "arguments": a}}, sid)[1]["result"]["structuredContent"]
    t = tool("sebbi_terms", {})
    ai_key = tool("sebbi_create_account", {"name": "Ada Agent", "email": "ada@agentco.co.uk", "company": "AgentCo", "terms_version": t["terms_version"], "customer_agreed": True})["api_key"]
    k3 = seed_key("dan@stuck.co.uk", "Dan Stuck", 4)
    k7 = seed_key("vi@using.co.uk", "Vi Using", 8)
    for i in range(3):
        http_("POST", "/api/govern", {"user_id": "u%d" % i, "action": "x", "amount": 1, "country": "UK", "device_id": "dev-%d" % i, "anomaly": 0, "device_risk": 0}, {"Authorization": "Bearer " + k7})
    kt7 = seed_key("tess@ending.co.uk", "Tess Ending", 85)
    kt1 = seed_key("tom@tomorrow.co.uk", "Tom Tomorrow", 89.2)
    kte = seed_key("eve@ended.co.uk", "Eve Ended", 91)
    seed_key("pat@paying.co.uk", "Pat Paying", 85, paid=1)
    seed_key("x@example.org", "Test Person", 4)
    c = sqlite3.connect(DB, timeout=30)
    c.execute("INSERT INTO pilot_order(session_id,created,name,email,company,status) VALUES(?,?,?,?,?, 'pending')", ("cs_test_aaaaaaaaaaaa1", time.time() - 2 * 3600, "Pia One", "pia@pilotone.co.uk", "PilotOne"))
    c.execute("INSERT INTO pilot_order(session_id,created,name,email,company,status) VALUES(?,?,?,?,?, 'pending')", ("cs_test_bbbbbbbbbbbb2", time.time() - 30 * 3600, "Quinn Two", "quinn@pilottwo.co.uk", "PilotTwo"))
    c.commit(); c.close()

    st, q, _ = http_("GET", "/x/autopilot/queue")
    chk("queue is admin only", st == 401, st)
    st, tok, _ = http_("POST", "/admin/auth", {"password": "ap-test-pw"})
    A = {"Authorization": "Bearer " + tok["token"]}
    st, q, _ = http_("GET", "/x/autopilot/queue", headers=A)
    steps = {x["email"]: x["step"] for x in q["queue"]}
    want = {"ada@agentco.co.uk": "welcome", "dan@stuck.co.uk": "day3", "vi@using.co.uk": "day7", "tess@ending.co.uk": "trial7",
            "tom@tomorrow.co.uk": "trial1", "eve@ended.co.uk": "trialend", "pia@pilotone.co.uk": "pilot1h", "quinn@pilottwo.co.uk": "pilot24h"}
    chk("each person is due the right email", all(steps.get(e) == s for e, s in want.items()), steps)
    chk("paying customers and test addresses are left alone", "pat@paying.co.uk" not in steps and "x@example.org" not in steps, steps)

    st, r, _ = http_("POST", "/x/autopilot/run", {}, A)
    got = {m["to"][0]["email"]: m for m in MAIL}
    chk("eight emails sent, one each", st == 200 and r.get("sent") == 8 and len(MAIL) == 8 and set(got) == set(want), (r, list(got)))
    chk("welcome carries the AI customer's key", ai_key in got["ada@agentco.co.uk"]["htmlContent"], got["ada@agentco.co.uk"]["subject"])
    chk("day 7 links a Forever Proof of their own decision", "/forever?block=" in got["vi@using.co.uk"]["htmlContent"] and "3 decisions sealed" in got["vi@using.co.uk"]["subject"], got["vi@using.co.uk"]["subject"])
    chk("trial email shows real days left and their cost", got["tess@ending.co.uk"]["subject"].startswith("5 days left") and "£0.50 a month" in got["tess@ending.co.uk"]["htmlContent"], got["tess@ending.co.uk"]["subject"])
    chk("every email: unsubscribe header, plain text, reply-to, referral code (customers)",
        all(m["headers"]["List-Unsubscribe"].startswith("<https://sebbi.pro/unsubscribe?e=") and m["textContent"] and m["replyTo"]["email"] for m in MAIL)
        and "REF-" in got["dan@stuck.co.uk"]["htmlContent"] and "REF-" not in got["pia@pilotone.co.uk"]["htmlContent"], MAIL[0].get("headers"))
    chk("nothing broken in the email text", all("{" not in m["subject"] and "None" not in m["textContent"] for m in MAIL), [m["subject"] for m in MAIL])

    st, r2, _ = http_("POST", "/x/autopilot/run", {}, A)
    chk("second run sends nothing: each step once, ever", r2.get("sent") == 0 and len(MAIL) == 8, r2)

    un = got["dan@stuck.co.uk"]["headers"]["List-Unsubscribe"][1:-1].replace("https://sebbi.pro", "")
    st, pg, _ = http_("GET", un, raw=True)
    chk("unsubscribe link works", st == 200 and b"unsubscribed" in pg, (st, pg[:200]))
    st, pg, _ = http_("GET", "/unsubscribe?e=dan@stuck.co.uk&t=forged", raw=True)
    chk("forged unsubscribe refused", st == 400)
    cont = [l for l in got["tom@tomorrow.co.uk"]["textContent"].split() if "/continue?t=" in l][0].replace("https://sebbi.pro", "")
    st, pg, _ = http_("GET", cont, raw=True)
    chk("payment link opens (no Stripe in the test, so it says so cleanly)", st in (302, 503) and (st == 302 or b"unavailable" in pg), st)
    st, pg, _ = http_("GET", "/continue?t=nope", raw=True)
    chk("unknown payment link handled", st == 404)

    st, r3, _ = http_("POST", "/x/autopilot/pause", {}, A)
    st, s2, _ = http_("GET", "/x/autopilot/status")
    chk("pause works and survives", s2["paused"] is True, s2)
    http_("POST", "/x/autopilot/resume", {}, A)
    st, s3, _ = http_("GET", "/x/autopilot/status")
    chk("resume works", s3["paused"] is False and s3["sent_total"] == 8 and s3["unsubscribed"] == 1, s3)
    st, lg, _ = http_("GET", "/x/autopilot/log", headers=A)
    chk("log for the admin page", len(lg["log"]) == 8, lg)
    st, mon, _ = http_("GET", "/x/monitor/all", headers=A)
    chk("monitor live feed shows the emails", sum(1 for f in mon["feed"] if f["kind"] == "autopilot") == 8, [f["kind"] for f in mon["feed"]][:12])
    st, v, _ = http_("GET", "/api/verify-chain")
    chk("chain valid", v.get("valid") is True)
finally:
    p.terminate()
    fake.shutdown()
print("\n%d passed, %d failed" % (len(P), len(F)))
if F:
    print("".join(open(w + "/l").readlines()[-20:]))
sys.exit(1 if F else 0)
