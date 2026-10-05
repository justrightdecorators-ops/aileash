"""End-to-end check of Human Keys (modules/humankeys.py), run by checks.yml in the
no-network sandbox. Boots the real site on a throwaway database, funds a test
wallet, and checks the monthly pass, the rhythm scoring, the refusals, the
check pages and the badge."""
import os, sys, subprocess, time, urllib.request, tempfile, socket, fcntl, struct, json, random, hashlib

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass

os.chdir(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
w = tempfile.mkdtemp()
ADMIN = "test-admin-key-0123456789"
env = dict(os.environ, PORT="8833", DB_PATH=w + "/a.db", ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0",
           CREDITS_ADMIN_KEY=ADMIN)
env.pop("CREDITS_TEST_MODE", None)
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def req(m, u, b=None, raw=False):
    rq = urllib.request.Request("http://127.0.0.1:8833" + u, data=json.dumps(b).encode() if b is not None else None,
                                method=m, headers={"Content-Type": "application/json",
                                                   "X-Forwarded-For": "10.%d.%d.1" % (random.randint(0, 250), random.randint(0, 250))})
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            x = r.read()
            return r.status, (x if raw else json.loads(x or b"{}")), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        x = e.read()
        try:
            return e.code, json.loads(x), None
        except Exception:
            return e.code, x, None


def session(intervals):
    st, ch, _ = req("GET", "/x/humankeys/challenge")
    time.sleep(sum(intervals) / 1000.0 + 1)  # real time must cover the typing claimed
    return ch


try:
    for _ in range(40):
        try:
            if req("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = req("GET", "/x/arm/status")
    hk = [r for r in a["results"] if r["module"] == "humankeys"]
    chk("arms", a["armed"] and hk and hk[0]["armed"], hk)

    viewer = "testviewer123456"
    req("GET", "/c/hello?viewer=" + viewer)
    st, g, _ = req("GET", "/c/grant?key=%s&viewer=%s&pence=100" % (ADMIN, viewer))
    st, h, _ = req("GET", "/c/hello?viewer=" + viewer)
    chk("test wallet funded with 100p", h.get("balance_pence") == 100, (g, h))
    st, ps, _ = req("GET", "/x/humankeys/pass?viewer=" + viewer)
    chk("no pass yet", ps.get("active") is False, ps)

    text = "I am typing this by hand to see whether the proof works, with a few mistakes along the way."
    th = hashlib.sha256(text.encode()).hexdigest()
    random.seed(4)
    human = [max(25, int(random.lognormvariate(5.0, 0.55))) for _ in range(95)] + [3200, 2600]
    counts = {"inserts": 95, "typed_chars": 95, "deletes": 4, "multi_inserts": 0, "multi_chars": 0,
              "paste_events": 0, "paste_chars": 0, "final_length": len(text), "blurs": 0}

    ch = session(human)
    st, d, _ = req("POST", "/x/humankeys/seal", {"challenge": ch["challenge"], "sig": ch["sig"], "text_hash": th,
                                                  "intervals": human, "counts": counts, "viewer": viewer})
    chk("first proof seals", st == 200 and d.get("sealed"), (st, d))
    chk("verdict human typed", d.get("verdict") == "HUMAN_TYPED", d.get("verdict"))
    chk("first proof buys the 50p monthly pass", d.get("pass_purchased_now") is True and d.get("balance_pence") == 50, d)
    code = d.get("code", "")

    pk, sg, bk = "A" * 120, "B" * 88, "C" * 184
    ch = session(human)
    st, dk, _ = req("POST", "/x/humankeys/seal", {"challenge": ch["challenge"], "sig": ch["sig"], "text_hash": th,
                                                   "intervals": human, "counts": counts, "viewer": viewer,
                                                   "pubkey": pk, "owner_sig": sg, "backup_email": "owner@example.org", "backup_code": bk})
    chk("proof carries the owner's device key", st == 200 and dk.get("owner_signed") is True, dk)
    chk("backup code sent to the owner's email", dk.get("backup_emailed") is True, dk)
    st, rk, _ = req("GET", "/x/humankeys/check?code=" + dk.get("code", ""))
    chk("check returns the sealed owner key", rk.get("owner_key") == pk and rk.get("owner_signature") == sg, rk)
    chk("backup code never stored", bk not in json.dumps(rk) and "owner@example.org" not in json.dumps(rk))
    st, ps, _ = req("GET", "/x/humankeys/pass?viewer=" + viewer)
    chk("pass now active", ps.get("active") is True and ps.get("until_uk"), ps)

    ch = session(human)
    st, d2, _ = req("POST", "/x/humankeys/seal", {"challenge": ch["challenge"], "sig": ch["sig"], "text_hash": th,
                                                   "intervals": human, "counts": counts, "viewer": viewer})
    chk("later proofs in the month are free", st == 200 and d2.get("pass_purchased_now") is False and d2.get("balance_pence") == 50, d2)

    st, ch2, _ = req("GET", "/x/humankeys/challenge")
    time.sleep(1)
    st, d3, _ = req("POST", "/x/humankeys/seal", {"challenge": ch2["challenge"], "sig": ch2["sig"], "text_hash": th,
                                                   "intervals": [8] * 95, "counts": counts, "viewer": viewer})
    chk("robot typing flagged mechanical", d3.get("verdict") == "MECHANICAL", d3.get("verdict"))

    empty = "emptywallet12345"
    req("GET", "/c/hello?viewer=" + empty)
    ch = session(human)
    st, d4, _ = req("POST", "/x/humankeys/seal", {"challenge": ch["challenge"], "sig": ch["sig"], "text_hash": th,
                                                   "intervals": human, "counts": counts, "viewer": empty})
    chk("empty wallet asked for the 50p pass", st == 402 and d4.get("reason") == "pass_needed", (st, d4))

    st, r, _ = req("GET", "/x/humankeys/check?code=" + code)
    chk("public check", st == 200 and r.get("text_hash") == th, r)
    chk("no text stored", text not in json.dumps(r))
    st, c, _ = req("POST", "/x/humankeys/compare", {"code": code, "text_hash": th})
    chk("compare matches", c.get("matches") is True, c)
    st, c, _ = req("POST", "/x/humankeys/compare", {"code": code, "text_hash": hashlib.sha256(b"other").hexdigest()})
    chk("compare rejects other text", c.get("matches") is False, c)

    st, ch4, _ = req("GET", "/x/humankeys/challenge")
    st, d5, _ = req("POST", "/x/humankeys/seal", {"challenge": ch4["challenge"], "sig": ch4["sig"], "text_hash": th,
                                                   "intervals": [400] * 95, "counts": counts, "viewer": viewer})
    chk("refuses typing longer than real time", st == 422 and d5.get("verdict") == "REFUSED", (st, d5))
    bad = dict(ch4["challenge"])
    bad["issued"] = bad["issued"] - 3000
    st, d6, _ = req("POST", "/x/humankeys/seal", {"challenge": bad, "sig": ch4["sig"], "text_hash": th,
                                                   "intervals": human, "counts": counts, "viewer": viewer})
    chk("refuses forged challenge", st == 400, (st, d6))
    ch = session(human)
    st, d7, _ = req("POST", "/x/humankeys/seal", {"challenge": ch["challenge"], "sig": ch["sig"], "text_hash": th,
                                                   "intervals": human, "counts": dict(counts, final_length=900), "viewer": viewer})
    chk("refuses text that was never typed", st == 422, (st, d7))

    for u in ["/keys", "/k/", "/k/" + code]:
        st, b, ct = req("GET", u, raw=True)
        chk("page " + u, st == 200 and b"Human" in b, st)
    st, b, ct = req("GET", "/keys", raw=True)
    chk("page says 50p a month", b"50p a month" in b)
    st, b, ct = req("GET", "/k/%s.svg" % code, raw=True)
    chk("badge svg", st == 200 and b"Human typed" in b and "svg" in (ct or ""), (st, ct))
    st, v, _ = req("GET", "/api/verify-chain")
    chk("chain still verifies", v.get("valid") is True, v)
finally:
    p.terminate()
print("\npassed %d, failed %d" % (len(P), len(F)))
if F:
    print(open(w + "/l").read()[-2000:])
sys.exit(1 if F else 0)
