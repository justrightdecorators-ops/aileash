"""End-to-end check of the machine-proof report (modules/dossier.py).
Boots the real site on a throwaway database inside the no-network sandbox,
seals decisions, and checks every part of the report. Run by checks.yml."""
import json, os, subprocess, sys, tempfile, time, urllib.request, socket, fcntl, struct

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception as e:
    print("lo:", e)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
B = "http://127.0.0.1:8777"
work = tempfile.mkdtemp()
env = dict(os.environ, PORT="8777", DB_PATH=work + "/a.db", ANCHOR_DIR=work + "/anc",
           OTS_AUTO_UPGRADE="0", DOSSIER_ROOT_SECONDS="2", ADMIN_PASSWORD="test-pass-123")
log = open(work + "/log", "w")
p = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
P, F = [], []


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:300]))


def req(method, path, body=None, key=None, hdr=None):
    h = {"Content-Type": "application/json", "User-Agent": "e2e-agent/1.0"}
    if key:
        h["Authorization"] = "Bearer " + key
    h.update(hdr or {})
    r = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None,
                               headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as x:
            return x.status, json.loads(x.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


try:
    for _ in range(40):
        try:
            if req("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, k = req("POST", "/signup", {"email": "a@b.co", "name": "Test Person", "org": "Acme Ltd",
                                    "phone": "0700", "product": "aileash", "devices": 2})
    key = k.get("api_key")
    chk("signup gives a key", bool(key), k)
    st, k2 = req("POST", "/signup", {"email": "c@d.co", "name": "Other", "org": "Other Ltd", "devices": 1})
    key2 = k2.get("api_key")

    ev = {"user_id": "cust-42", "action": "payment", "amount": 4200, "country": "UK",
          "device_id": "phone-1", "anomaly": 0.4, "device_risk": 0.35}
    st, before = req("POST", "/api/govern", ev, key)
    chk("decision before arming seals", st == 200 and before.get("block_index"), before)

    st, a = req("GET", "/x/arm/status")
    dos = [r for r in a.get("results", []) if (r.get("module") or r.get("name")) == "dossier"]
    chk("arm arms dossier", st == 200 and a.get("armed") and dos, dos or a.get("modules_failed"))

    st, d1 = req("POST", "/api/govern", dict(ev, amount=9000, anomaly=0.9), key,
                 {"X-Forwarded-For": "203.0.113.7, 10.0.0.2", "Origin": "https://acme.example",
                  "Accept-Language": "en-GB"})
    blk = d1.get("block_index")
    chk("decision after arming seals", st == 200 and blk, d1)

    st, at = req("POST", "/x/dossier/attach", {"block": blk, "ip": "198.51.100.9", "user_agent": "iPhone",
                                                "actor": "j.smith", "session_id": "s-77"}, key)
    chk("attach end-user context", st == 200 and at.get("attached"), at)

    st, rp = req("GET", "/x/dossier/report?block=%d" % blk, key=key)
    chk("keyed report returns", st == 200, rp)
    w = rp.get("where", {})
    chk("captured IP is first forwarded hop", w.get("ip") == "203.0.113.7", w)
    chk("forwarded chain kept", w.get("forwarded_chain") == ["203.0.113.7", "10.0.0.2"], w.get("forwarded_chain"))
    chk("user agent kept", w.get("user_agent") == "e2e-agent/1.0", w.get("user_agent"))
    chk("origin kept", w.get("origin") == "https://acme.example")
    chk("end user context in report", (w.get("end_user") or {}).get("actor") == "j.smith", w.get("end_user"))
    who = rp.get("who", {})
    chk("account holder named", (who.get("account") or {}).get("name") == "Test Person", who.get("account"))
    chk("organisation named", (who.get("account") or {}).get("organisation") == "Acme Ltd")
    chk("full key never shown", key not in json.dumps(rp))
    chk("end user named", who.get("subject_user") == "cust-42")
    chk("previous decision linked", (who.get("subject_history") or {}).get("previous_decision", {}).get("block") == before["block_index"],
        who.get("subject_history"))
    i = rp.get("integrity", {})
    chk("block rehashes", i.get("block_hash_recomputes") is True, i)
    chk("links to previous", i.get("links_to_previous") is True)
    chk("chain verified genesis to here", i.get("chain_verified_genesis_to_here") is True, i)
    chk("merkle proof present", (i.get("merkle_inclusion") or {}).get("root"), i.get("merkle_inclusion"))
    chk("receipt sequence gapless", (i.get("receipt_sequence") or {}).get("gapless") is True, i.get("receipt_sequence"))
    chk("digest present", len(rp.get("digest", "")) == 64)

    st, rb = req("GET", "/x/dossier/report?block=%d" % before["block_index"], key=key)
    chk("pre-capture block says not captured", rb.get("where", {}).get("captured") is False, rb.get("where"))

    st, nope = req("GET", "/x/dossier/report?block=%d" % blk, key=key2)
    chk("another key cannot open it", st == 403, (st, nope))
    st, nope = req("GET", "/x/dossier/report?block=%d" % blk)
    chk("no key cannot open it", st in (401, 403), st)
    st, nope = req("GET", "/dossier/data?block=%d" % blk, key=key2)
    chk("direct route refuses other key", st == 401, st)

    st, pub = req("GET", "/x/dossier/verify?block=%d" % blk)
    chk("public half works", st == 200 and pub.get("integrity"), pub)
    chk("public half has no personal data",
        "203.0.113.7" not in json.dumps(pub) and "Test Person" not in json.dumps(pub) and "who" not in pub)

    time.sleep(4)
    st, rp2 = req("GET", "/x/dossier/report?block=%d" % blk, key=key)
    recs = rp2.get("where", {}).get("records", [])
    sealed = [r for r in recs if (r.get("sealed_in") or {}).get("root_block")]
    chk("context fingerprints sealed in a root block", len(sealed) == len(recs) and recs, recs)
    chk("root recomputes", all(r["sealed_in"].get("root_recomputes") for r in sealed))
    chk("fingerprints recompute", all(r.get("fingerprint_recomputes") for r in recs))

    st, iss = req("POST", "/x/dossier/issue", {"block": blk}, key)
    chk("issue seals the digest", st == 200 and iss.get("issued_block"), iss)
    st, cc = req("GET", "/x/dossier/check?digest=" + iss.get("digest", ""))
    chk("public check finds issued report", st == 200 and cc.get("issued"), cc)
    st, cc = req("GET", "/x/dossier/check?digest=" + "0" * 64)
    chk("public check rejects unknown digest", st == 404)

    st, tok = req("POST", "/admin/auth", {"password": "test-pass-123"})
    st, adm = req("GET", "/dossier/data?block=%d" % blk, key=tok.get("token"))
    chk("admin token opens any report", st == 200 and adm.get("who"), (st, adm))
    st, ai = req("POST", "/dossier/issue", {"block": before["block_index"]}, tok.get("token"))
    chk("admin can issue", st == 200 and ai.get("issued"), ai)

    r = urllib.request.urlopen(B + "/dossier", timeout=20)
    chk("page serves", r.status == 200 and b"Machine-proof report" in r.read())

    st, vc = req("GET", "/api/verify-chain")
    chk("whole chain still verifies after all this", vc.get("valid") is True, vc)
    st, sts = req("GET", "/x/dossier/status")
    chk("status armed", sts.get("armed") is True and sts.get("context_roots_sealed", 0) >= 1, sts)

    # latency: decisions per second before/after are not comparable here; just time 50 decisions
    t0 = time.time()
    for n in range(50):
        req("POST", "/api/govern", dict(ev, user_id="lat-%d" % n), key)
    ms = (time.time() - t0) / 50 * 1000
    print("  avg govern round trip with capture on: %.1f ms" % ms)
    st, vc = req("GET", "/api/verify-chain")
    chk("chain verifies after load", vc.get("valid") is True, vc)
    time.sleep(3)
    st, sts = req("GET", "/x/dossier/status")
    chk("every sealed block captured", sts.get("awaiting_next_root") == 0, sts)
finally:
    p.terminate()
    p.wait(timeout=10)
    log.close()
print("\npassed %d, failed %d" % (len(P), len(F)))
if F:
    print(open(work + "/log").read()[-3000:])
sys.exit(1 if F else 0)
