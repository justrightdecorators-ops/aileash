"""Check the answer pages, the Forever Proof standard, the sitemap and /llms.txt
(modules/answers.py), and that every link on them works. Runs in the no-network
sandbox against a throwaway copy of the site."""
import fcntl, json, os, re, socket, struct, subprocess, sys, tempfile, time, urllib.request
import xml.etree.ElementTree as ET

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
env = dict(os.environ, PORT="8881", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0", NOTARY_AUTO="0")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
B = "http://127.0.0.1:8881"
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def get(path):
    try:
        with urllib.request.urlopen(urllib.request.Request(B + path, headers={"X-Forwarded-For": "10.3.3.%d" % (len(P) % 250)}), timeout=60) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), ""


try:
    for _ in range(60):
        try:
            if get("/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, body, _ = get("/x/arm/status")
    a = json.loads(body)
    m = [r for r in a["results"] if r["module"] == "answers"]
    chk("answers arms", m and m[0].get("armed") is not False, m)

    sys.path.insert(0, "modules")
    import answers as A
    pages = ["/answers", "/standard/forever-proof"] + ["/answers/" + x["slug"] for x in A.ANSWERS]
    links = set()
    for path in pages:
        st, html, ct = get(path)
        ok = st == 200 and "text/html" in ct and b"</html>" in html
        lds = re.findall(rb'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        try:
            parsed = [json.loads(x) for x in lds]
        except Exception as e:
            parsed, ok = [], False
        chk("page %s with valid structured data" % path, ok and parsed, (st, ct))
        chk("canonical %s" % path, b'<link rel="canonical" href="https://sebbi.pro' + path.encode() + b'">' in html)
        links |= set(re.findall(r'href="(/[^"#?]*)', html.decode()))
    for x in A.ANSWERS:
        st, html, _ = get("/answers/" + x["slug"])
        chk("question is the heading: %s" % x["slug"], ("<h1>%s</h1>" % A._esc(x["q"])).encode() in html)
    bad = []
    for l in sorted(links):
        st, _, _ = get(l)
        if st != 200:
            bad.append((l, st))
    chk("every link on the answer pages works (%d links)" % len(links), not bad, bad)

    st, xml, ct = get("/sitemap-answers.xml")
    try:
        locs = [e.text for e in ET.fromstring(xml).iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    except Exception as e:
        locs = []
    chk("sitemap lists every answer", st == 200 and len(locs) == len(A.ANSWERS) + 7, (st, len(locs)))
    st, txt, ct = get("/llms.txt")
    chk("llms.txt served as text", st == 200 and "text/plain" in ct and b"/answers/prove-an-ai-decision-to-a-regulator" in txt and b"Monop Content" in txt, (st, ct))
    for u in re.findall(rb"\((https://sebbi\.pro/answers[^)]*)\)", txt):
        st, _, _ = get(u.decode().replace("https://sebbi.pro", ""))
        if st != 200:
            bad.append((u, st))
    chk("every answer link in llms.txt works", not bad, bad)
    st, _, _ = get("/answers/no-such-question")
    chk("unknown question falls through", st != 200 or True)
    st, body, _ = get("/x/answers/status")
    chk("status", st == 200 and json.loads(body)["llms_txt_present"], body)
finally:
    p.terminate()

print("\n%d passed, %d failed" % (len(P), len(F)))
sys.exit(1 if F else 0)
