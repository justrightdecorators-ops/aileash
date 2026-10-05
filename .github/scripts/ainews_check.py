"""End-to-end check of the AI news ticker (modules/ainews.py) and the terms page, run by
checks.yml in the no-network sandbox. Feeds are supplied as local RSS and Atom files."""
import os, sys, subprocess, time, urllib.request, tempfile, socket, fcntl, struct, json, random
from email.utils import formatdate

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
feeds = os.path.join(w, "feeds")
os.makedirs(feeds)
now = time.time()
rss = "<?xml version='1.0'?><rss><channel>" + "".join(
    "<item><title>%s</title><link>https://news.test/%d</link><pubDate>%s</pubDate></item>" % (t, i, formatdate(now - i * 600))
    for i, t in enumerate(["OpenAI ships a new model for agents", "Anthropic expands Claude for enterprises",
                           "EU AI Act guidance published for high-risk systems", "Local council approves new bus lane",
                           "Nvidia reports record data centre demand for AI chips", "Football transfer window closes"])) + "</channel></rss>"
atom = ("<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'>"
        "<entry><title>Google DeepMind unveils Gemini research agent</title><link rel='alternate' href='https://news.test/atom1'/>"
        "<updated>%s</updated></entry><entry><title>Old AI story from last month</title><link href='https://news.test/old'/>"
        "<updated>2026-08-01T10:00:00Z</updated></entry></feed>") % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 300))
open(os.path.join(feeds, "feed_0.xml"), "w").write(rss)
open(os.path.join(feeds, "feed_1.xml"), "w").write(atom)
open(os.path.join(feeds, "feed_2.xml"), "w").write("this is not xml")
env = dict(os.environ, PORT="8888", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", AINEWS_FEED_DIR=feeds)
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def get(u):
    rq = urllib.request.Request("http://127.0.0.1:8888" + u, headers={"X-Forwarded-For": "10.7.%d.5" % random.randint(0, 250)})
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


try:
    for _ in range(40):
        try:
            if get("/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    get("/x/arm/status")
    time.sleep(2)
    st, b, _ = get("/x/ainews/feed")
    d = json.loads(b)
    titles = [x["title"] for x in d["stories"]]
    chk("reads RSS and Atom, keeps only AI stories", d["count"] == 5 and "Football transfer window closes" not in titles
        and "Local council approves new bus lane" not in titles, titles)
    chk("drops stories older than three days", "Old AI story from last month" not in titles, titles)
    chk("newest first", titles[0] == "OpenAI ships a new model for agents" or titles[0].startswith("Google DeepMind"), titles)
    chk("a broken feed does not stop the others", d["count"] == 5)
    for path in ("/", "/developers", "/connect", "/keys"):
        st, b, h = get(path)
        chk("ticker on " + path, st == 200 and b.count(b"<!--sebbi-ainews-->") == 1 and int(h["Content-Length"]) == len(b), (st, b.count(b"<!--sebbi-ainews-->")))
    st, b, h = get("/")
    chk("headlines link to the publisher", b"https://news.test/0" in b and b"target=\"_blank\"" in b)
    chk("homepage still has homelink and strip", b"<!--sebbi-homelink-->" in b and b'class="sbx"' in b)
    for path in ("/terms", "/admin", "/console"):
        st, b, h = get(path)
        chk("no ticker on " + path, b"<!--sebbi-ainews-->" not in b, st)
    st, b, h = get("/api/verify-chain")
    chk("data responses untouched", b"sebbi-ainews" not in b and json.loads(b).get("valid") is True)
    st, b, h = get("/terms")
    chk("terms page serves", st == 200 and b"Terms of" in b and b"50p per unique device per month" in b, st)
    chk("terms keep the legal name", b"Justin Antony Dobson, trading as Monop Content" in b)
    st, b, h = get("/x/mcp/terms")
    chk("AI connector terms point to the full terms", b"https://sebbi.pro/terms" in b)
finally:
    p.terminate()
print("\npassed %d, failed %d" % (len(P), len(F)))
if F:
    print(open(w + "/l").read()[-2000:])
sys.exit(1 if F else 0)
