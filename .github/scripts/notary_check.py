"""End-to-end check of the Bitcoin Notary, Forever Proofs and Human Keys in Bitcoin
(modules/notary.py + forever_verify.py). Run by checks.yml in the no-network
sandbox against a throwaway copy of the site.

A stand-in OpenTimestamps calendar and block explorer run on this machine, so the
whole path - fingerprint, batch, calendar, Bitcoin confirmation, Forever Proof,
offline verifier and the in-browser verifier - is exercised without touching the
real calendars, the real Bitcoin network or the live site.

It also proves the module never writes to the chain: the chain's block count and
validity are compared before and after every notary operation."""
import base64, fcntl, hashlib, http.server, json, os, random, socket, sqlite3, struct, subprocess, sys, tempfile
import threading, time, urllib.request

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", 0x49, b""))
except Exception:
    pass
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
import forever_verify as FV  # noqa: E402

# ---------------------------------------------------------------- stand-in calendar + explorer
CAL = "http://127.0.0.1:8902"
FAKE = {"confirm": False, "commit": {}, "blocks": {}, "height": 860000}


def _pending_ts(digest):
    nonce = os.urandom(16)
    commitment = hashlib.sha256(digest + nonce).digest()
    FAKE["commit"][commitment.hex()] = None
    t = FV.Timestamp(digest)
    t2 = FV.Timestamp(digest + nonce)
    t3 = FV.Timestamp(commitment)
    t3.attestations.append((FV.TAG_PENDING, FV.pending_payload(CAL)))
    t2.ops.append(((FV.OP_SHA256, b""), t3))
    t.ops.append(((FV.OP_APPEND, nonce), t2))
    return t.serialize()


def _confirmed_ts(commitment):
    if FAKE["commit"].get(commitment.hex()) is None:
        FAKE["height"] += 1
        FAKE["commit"][commitment.hex()] = FAKE["height"]
    h = FAKE["height"] if FAKE["commit"][commitment.hex()] is None else FAKE["commit"][commitment.hex()]
    pre = hashlib.sha256(str(h).encode()).digest()
    m1 = pre + commitment
    m2 = hashlib.sha256(m1).digest()
    m3 = hashlib.sha256(m2).digest()          # the "block Merkle root", internal order
    FAKE["blocks"][h] = {"merkle_root": m3[::-1].hex(), "hash": hashlib.sha256(b"blk" + m3).hexdigest(), "timestamp": 1760000000 + h}
    t = FV.Timestamp(commitment)
    a = FV.Timestamp(m1)
    b = FV.Timestamp(m2)
    c = FV.Timestamp(m3)
    c.attestations.append((FV.TAG_BITCOIN, FV._w_varuint(h)))
    b.ops.append(((FV.OP_SHA256, b""), c))
    a.ops.append(((FV.OP_SHA256, b""), b))
    t.ops.append(((FV.OP_PREPEND, pre), a))
    return t.serialize()


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _out(self, code, body, ctype="application/octet-stream"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        d = self.rfile.read(n)
        if self.path == "/digest" and len(d) == 32:
            return self._out(200, _pending_ts(d))
        return self._out(400, b"")

    def do_GET(self):
        p = self.path
        if p.startswith("/timestamp/"):
            c = p.split("/")[-1]
            if c in FAKE["commit"] and FAKE["confirm"]:
                return self._out(200, _confirmed_ts(bytes.fromhex(c)))
            return self._out(404, b"Pending confirmation in Bitcoin blockchain")
        for base in ("/api", "/api2"):
            if p.startswith(base + "/block-height/"):
                h = int(p.split("/")[-1])
                if h in FAKE["blocks"]:
                    return self._out(200, FAKE["blocks"][h]["hash"].encode(), "text/plain")
                return self._out(404, b"")
            if p.startswith(base + "/block/"):
                bh = p.split("/")[-1]
                for h, b in FAKE["blocks"].items():
                    if b["hash"] == bh:
                        return self._out(200, json.dumps({"merkle_root": b["merkle_root"], "timestamp": b["timestamp"], "height": h}).encode(), "application/json")
                return self._out(404, b"")
        return self._out(404, b"")


fake = http.server.ThreadingHTTPServer(("127.0.0.1", 8902), Fake)
threading.Thread(target=fake.serve_forever, daemon=True).start()
EXPL = [CAL + "/api", CAL + "/api2"]

# ---------------------------------------------------------------- the site
w = tempfile.mkdtemp()
DB = w + "/a.db"
env = dict(os.environ, PORT="8879", DB_PATH=DB, ANCHOR_DIR=w + "/x", OTS_AUTO_UPGRADE="0",
           NOTARY_AUTO="0", NOTARY_CALENDARS=CAL, NOTARY_EXPLORERS=",".join(EXPL), NOTARY_CAL_PAUSE="0")
p = subprocess.Popen([sys.executable, "server.py"], env=env, stdout=open(w + "/l", "w"), stderr=subprocess.STDOUT)
P, F = [], []
B = "http://127.0.0.1:8879"


def chk(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + ("" if c else "  -> " + str(d)[:400]))


def http_(method, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "X-Forwarded-For": "10.7.%d.%d" % (random.randint(0, 250), random.randint(1, 250))}
    h.update(headers or {})
    rq = urllib.request.Request(B + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
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


def chain_state():
    st, v, _ = http_("GET", "/api/verify-chain")
    return v.get("blocks"), v.get("tip"), v.get("valid")


def sql(q, a=()):
    c = sqlite3.connect(DB, timeout=30)
    try:
        r = c.execute(q, a).fetchall()
        c.commit()
        return r
    finally:
        c.close()


try:
    for _ in range(40):
        try:
            if http_("GET", "/api/health")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    st, a, _ = http_("GET", "/x/arm/status")
    nt = [r for r in a["results"] if r["module"] == "notary"]
    chk("notary arms", nt and nt[0].get("armed") is not False, nt)

    # an account, some decisions, a Human Keys record
    st, d, h = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    SID["id"] = h.get("Mcp-Session-Id")
    t, _ = tool("sebbi_terms", {})
    acc, e = tool("sebbi_create_account", {"name": "N Test", "email": "notary@example.org", "terms_version": t["terms_version"], "customer_agreed": True})
    key = acc.get("api_key")
    chk("test account", key, acc)
    blocks = []
    for i in range(5):
        r, e = tool("sebbi_test_decision", {"api_key": key, "action": "loan_approval", "amount": 1000 + i})
        blocks.append(r.get("block_index"))
    chk("five decisions sealed", all(blocks), blocks)

    st, s, _ = http_("GET", "/x/humankeys/status")
    hk_code, hk_text = "HK-TEST-2345", "Typed by hand for the notary check."
    hk_hash = FV.human_text_hash(hk_text)
    sql("INSERT INTO humankeys_proof(code,text_hash,verdict,score,summary_json,challenge_json,sealed_at,block_index,audit_hash,payer,reference) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (hk_code, hk_hash, "HUMAN_TYPED", 0.9, "{}", "{}", time.time(), None, None, "test", None))

    # pages
    for path in ("/bitcoin", "/forever", "/n/", "/n/NT-AAAA-BBBB"):
        st, body, hd = http_("GET", path, raw=True)
        chk("page %s" % path, st == 200 and b"</html>" in body and b"__MAGIC__" not in body, st)
    st, body, hd = http_("GET", "/forever-verify.py", raw=True)
    chk("verifier download", st == 200 and b"def check(" in body and "attachment" in (hd.get("Content-Disposition") or ""), st)
    st, old, _ = http_("GET", "/notary", raw=True)
    chk("existing /notary page still served by server.py", st == 200 and b"/x/notary/" not in old and b"Prove it existed" not in old, old[:200])
    st, disc, _ = http_("GET", "/.well-known/sebbi-notary.json")
    chk("discovery document", st == 200 and disc.get("proof_format") == "sebbi-forever-proof/1", disc)
    st, home, _ = http_("GET", "/", raw=True)
    i_ntx, i_sbx = home.find(b'class="ntx"'), home.find(b'class="sbx"')
    chk("homepage Bitcoin strip", i_ntx > 0 and home.count(b'class="ntx"') == 1, i_ntx)
    chk("homepage feature strip still there, below", i_sbx < 0 or i_sbx > i_ntx, (i_ntx, i_sbx))
    chk("homepage buttons: Bitcoin Notary and Forever Proof", home.count(b'href="/bitcoin" style=') == 1 and b'href="/forever" style=' in home
        and home.find(b'href="/bitcoin" style=') < home.find(b'<a href="/dossier" style='), home.count(b'href="/bitcoin"'))
    st, kp, _ = http_("GET", "/k/" + hk_code, raw=True)
    chk("Human Keys page shows the Bitcoin panel", st == 200 and b'id="ntxhk"' in kp, st)
    st, kp2, _ = http_("GET", "/keys", raw=True)
    chk("keyboard page left alone", b'id="ntxhk"' not in kp2)

    # refusals
    st, d, _ = http_("POST", "/x/notary/stamp", {"digests": ["nothex"]})
    chk("refuses a bad fingerprint", st == 400 and d["error"] == "bad_digest", d)
    st, d, _ = http_("POST", "/x/notary/stamp", {"digests": ["a" * 64] * 1001})
    chk("refuses too many at once", st == 413, st)
    st, d, _ = http_("POST", "/x/notary/stamp", {})
    chk("refuses an empty request", st == 400, d)
    st, d, _ = http_("GET", "/x/notary/run")
    chk("worker needs a key", st == 401, st)

    before = chain_state()

    # stamp
    files = [b"contract version 7", b"model card Q3", os.urandom(5000)]
    digests = [hashlib.sha256(f).hexdigest() for f in files]
    st, d, _ = http_("POST", "/x/notary/stamp", {"digests": digests, "label": "<b>Board pack</b>"})
    chk("three fingerprints received", st == 200 and len(d.get("receipts", [])) == 3, d)
    codes = [r["code"] for r in d["receipts"]]
    chk("label cleaned", d.get("label") == "bBoard pack/b", d.get("label"))
    st, r, _ = http_("GET", "/x/notary/receipt?code=" + codes[0])
    chk("queued before the batch", r.get("state") == "queued", r)
    st, lk, _ = http_("GET", "/x/notary/lookup?digest=" + digests[1])
    chk("lookup by fingerprint", lk.get("found") == 1 and lk["receipts"][0]["code"] == codes[1], lk)
    st, d, _ = http_("POST", "/x/notary/stamp", {"digest": digests[0]}, {"Authorization": "Bearer " + key})
    chk("keyed stamp", st == 200, d)

    # batch and send
    st, run, _ = http_("POST", "/x/notary/run", {}, {"Authorization": "Bearer " + key})
    chk("worker batches and sends", st == 200 and run.get("batched") and run.get("checkpoint") and run.get("sent", 0) >= 2, run)
    st, r, _ = http_("GET", "/x/notary/receipt?code=" + codes[0])
    chk("pending after sending", r.get("state") == "pending" and r["batch"]["calendars"] == 1, r)
    st, bund, _ = http_("GET", "/x/notary/bundle?code=" + codes[0])
    rep = FV.check(bund, explorers=EXPL)
    chk("pending proof checks as pending", rep.get("pending") and not rep["ok"], rep)
    st, hk, _ = http_("GET", "/x/notary/hk?code=" + hk_code)
    chk("Human Keys proof joined the batch", hk.get("state") == "pending", hk)

    # Bitcoin confirms
    FAKE["confirm"] = True
    st, run, _ = http_("POST", "/x/notary/run", {}, {"Authorization": "Bearer " + key})
    chk("worker upgrades to confirmed", st == 200 and "confirmed" in run.get("upgraded", {}).values(), run)
    st, r, _ = http_("GET", "/x/notary/receipt?code=" + codes[0])
    chk("receipt in Bitcoin", r.get("state") == "confirmed" and r["batch"]["bitcoin"]["height"] > 860000
        and len(r["batch"]["bitcoin"]["checked_with"]) == 2, r)
    st, svg, hd = http_("GET", "/n/%s.svg" % codes[0], raw=True)
    chk("badge shows the block", st == 200 and b"block 86" in svg and "svg" in hd.get("Content-Type", ""), svg[:200])

    st, bund, _ = http_("GET", "/x/notary/bundle?code=" + codes[2])
    rep = FV.check(bund, explorers=EXPL)
    chk("Forever Proof verifies offline", rep["ok"] and rep["bitcoin_block"]["height"] > 860000, rep)
    rep = FV.check(bund, explorers=EXPL, file_bytes=files[2])
    chk("with the original file", rep["ok"], rep)
    rep = FV.check(bund, explorers=EXPL, file_bytes=b"a different file")
    chk("a different file fails", not rep["ok"], rep["steps"][-1])
    bad = json.loads(json.dumps(bund))
    if bad["merkle"]["path"]:
        bad["merkle"]["path"][0] = "00" * 32
    else:
        bad["merkle"]["root"] = "00" * 32
    chk("a tampered path fails", not FV.check(bad, explorers=EXPL)["ok"])
    bad = json.loads(json.dumps(bund))
    bad["subject"]["digest"] = "ab" * 32
    bad["leaf"] = FV.notary_leaf("ab" * 32)
    chk("a swapped fingerprint fails", not FV.check(bad, explorers=EXPL)["ok"])
    chk("a wrong block root fails", not FV.check(bund, merkle_root="11" * 32)["ok"])
    pf = os.path.join(w, "p.json")
    json.dump(bund, open(pf, "w"))
    open(os.path.join(w, "f.bin"), "wb").write(files[2])
    cli = subprocess.run([sys.executable, "forever_verify.py", pf, "--file", os.path.join(w, "f.bin")]
                         + sum([["--explorer", e] for e in EXPL], []), capture_output=True, text=True, timeout=60)
    chk("command-line verifier", cli.returncode == 0 and "VERIFIED" in cli.stdout, cli.stdout + cli.stderr)
    st, sv, _ = http_("POST", "/x/notary/verify", {"bundle": bund})
    chk("server-side verify route", st == 200 and sv.get("ok"), sv)
    op, dg, ts = FV.parse_detached(base64.b64decode(bund["bitcoin"]["proof_ots_base64"]))
    chk("stored proof is standard OpenTimestamps", dg.hex() == bund["merkle"]["root"]
        and FV.serialize_detached(dg, ts) == base64.b64decode(bund["bitcoin"]["proof_ots_base64"]))

    # Human Keys
    st, hb, _ = http_("GET", "/x/notary/bundle?code=" + hk_code)
    rep = FV.check(hb, explorers=EXPL, text="  " + hk_text + "\r\n")
    chk("Human Keys Forever Proof with the text", rep["ok"] and hb["subject"]["verdict"] == "HUMAN_TYPED", rep)
    chk("wrong text fails", not FV.check(hb, explorers=EXPL, text="Something else")["ok"])

    # chain blocks
    st, cb, _ = http_("GET", "/x/notary/bundle?block=%d" % blocks[2])
    rep = FV.check(cb, explorers=EXPL)
    chk("chain block Forever Proof", st == 200 and rep["ok"] and "block_content" not in cb["subject"], (st, rep))
    st, cbk, _ = http_("GET", "/x/notary/bundle?block=%d" % blocks[2], headers={"Authorization": "Bearer " + key})
    bc = cbk["subject"].get("block_content")
    chk("owner gets the block itself, and it hashes to the chain", bc and FV.chain_block_hash(bc) == cbk["subject"]["audit_hash"], cbk["subject"])
    chk("verifier re-hashes the owner's block", FV.check(cbk, explorers=EXPL, block=bc)["ok"])
    st, cps, _ = http_("GET", "/x/notary/checkpoints")
    cp = cps["checkpoints"][0]
    hashes = [r[0] for r in sql("SELECT audit_hash FROM audit_log ORDER BY id ASC LIMIT ?", (cp["chain_size"],))]
    chk("checkpoint root rebuilt independently", FV.merkle_root_of([FV.leaf_hash(x) for x in hashes]).hex() == cp["root"], cp)
    st, cr, _ = http_("GET", "/x/consistency/root")
    if cr.get("tree_size") == cp["chain_size"]:
        chk("checkpoint root equals the public consistency root", cr["root"] == cp["root"], (cr, cp))

    after = chain_state()
    chk("CHAIN UNTOUCHED: same blocks, same tip, still valid", before == after and after[2] is True, (before, after))
    cols = [r[1] for r in sql("PRAGMA table_info(audit_log)")]
    chk("chain table structure unchanged", cols[:7] == ["id", "ts", "user_id", "event_json", "result_json", "prev_hash", "audit_hash"], cols)

    # the browser verifier, run in Node with the explorers pointed at the stand-in
    page = http_("GET", "/forever", raw=True)[1].decode()
    js = page[page.index("const FV=(()=>{"):page.index("return{check,sha256hex,norm,hex}})();") + len("return{check,sha256hex,norm,hex}})();")]
    harness = ("const realFetch=fetch;globalThis.fetch=(u,o)=>realFetch(String(u).replace('https://mempool.space/api','%s').replace('https://blockstream.info/api','%s'),o);\n"
               % (EXPL[0], EXPL[1])) + js + """
const b=JSON.parse(require('fs').readFileSync(process.argv[2],'utf8'));const steps=[];
(async()=>{const r=await FV.check(b,(n,ok,d)=>steps.push([n,ok,d]),{});
const bad=JSON.parse(JSON.stringify(b));bad.merkle.root='00'.repeat(32);const r2=await FV.check(bad,()=>{},{});
console.log(JSON.stringify({ok:r.ok,height:r.height,bad:r2.ok,steps}))})().catch(e=>{console.log(JSON.stringify({err:String(e)}))})"""
    jf = os.path.join(w, "v.js")
    open(jf, "w").write(harness)
    try:
        nd = subprocess.run(["node", jf, pf], capture_output=True, text=True, timeout=60)
        out = json.loads(nd.stdout.strip().splitlines()[-1])
        chk("browser verifier agrees", out.get("ok") is True and out.get("height") == bund["bitcoin"]["heights"][0] and out.get("bad") is False, nd.stdout + nd.stderr)
    except FileNotFoundError:
        print("  note node not installed - browser verifier not run")

    # every file of the code
    st, cbx, _ = http_("GET", "/x/notary/codebase")
    paths = {f["path"] for f in cbx.get("files", [])}
    chk("every code file sealed", {"server.py", "modules/notary.py", "forever_verify.py"} <= paths and cbx["files_sealed"] >= 100, len(paths))
    chk("no data or secrets read", not any(x.endswith((".db", ".pem", ".key")) or "/.git/" in "/" + x or x.startswith(".env") for x in paths),
        [x for x in paths if x.endswith(".db")])
    chk("codebase snapshot", cbx.get("snapshot", {}).get("files") == cbx["files_sealed"], cbx.get("snapshot"))
    st, man, _ = http_("GET", "/bitcoin/code/manifest.txt", raw=True)
    line = [l for l in man.decode().splitlines() if l.endswith("  forever_verify.py")]
    chk("manifest matches the real file", line and line[0].split()[0] == hashlib.sha256(open("forever_verify.py", "rb").read()).hexdigest()
        and hashlib.sha256(man).hexdigest() == cbx["snapshot"]["digest"], line)
    fv = [f for f in cbx["files"] if f["path"] == "forever_verify.py"][0]
    chk("code file confirmed in Bitcoin", fv["state"] == "confirmed" and fv["bitcoin_block"], fv)
    st, cbund, _ = http_("GET", "/x/notary/bundle?code=" + fv["code"])
    chk("code file Forever Proof against the real file", FV.check(cbund, explorers=EXPL, file_bytes=open("forever_verify.py", "rb").read())["ok"])
    st, pg, _ = http_("GET", "/bitcoin/code", raw=True)
    chk("code page", st == 200 and b"Every file" in pg, st)
    st, r2, _ = http_("POST", "/x/notary/run", {}, {"Authorization": "Bearer " + key})
    chk("unchanged files are not sealed twice", r2.get("codebase", {}).get("new_or_changed") == 0 and r2["codebase"]["snapshot"] == "unchanged", r2.get("codebase"))

    # AI connector tools
    st, tl, _ = rpc("tools/list")
    names = [t["name"] for t in tl["result"]["tools"]]
    chk("AI connector lists the three notary tools", {"sebbi_notarize", "sebbi_notary_receipt", "sebbi_forever_proof"} <= set(names)
        and len(names) >= 16, names)
    st, ini, _ = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t2", "version": "1"}})
    chk("connector instructions mention the notary once", ini["result"]["instructions"].count("sebbi_notarize") == 1, ini)
    r, e = tool("sebbi_notarize", {"digests": [hashlib.sha256(b"via ai").hexdigest()], "label": "From an AI"})
    chk("AI notarises", not e and r.get("received") == 1 and r["receipts"][0]["code"].startswith("NT-"), r)
    r2, e = tool("sebbi_notary_receipt", {"code": r["receipts"][0]["code"]})
    chk("AI reads the receipt", not e and r2.get("state") == "queued", r2)
    r3, e = tool("sebbi_forever_proof", {"block": blocks[1]})
    chk("AI gets a chain Forever Proof", not e and FV.check(r3, explorers=EXPL)["ok"], r3.get("error"))
    r4, e = tool("sebbi_notarize", {"digests": ["bad"]})
    chk("AI refused a bad fingerprint", e and r4.get("error") == "bad_digest", r4)
    r5, e = tool("sebbi_overview", {})
    chk("existing connector tools still work", not e and r5.get("products"), r5)

    # daily limit
    st, d, _ = http_("POST", "/x/notary/stamp", {"digests": [hashlib.sha256(str(i).encode()).hexdigest() for i in range(400)]},
                     {"X-Forwarded-For": "10.250.250.250"})
    st2, d2, _ = http_("POST", "/x/notary/stamp", {"digests": [hashlib.sha256(str(i).encode()).hexdigest() for i in range(200)]},
                       {"X-Forwarded-For": "10.250.250.250"})
    chk("free daily limit per visitor", st == 200 and st2 == 429, (st, st2))
    st, stt, _ = http_("GET", "/x/notary/status")
    chk("status", st == 200 and stt["writes_to_chain"] is False and stt["batches_in_bitcoin"] >= 2, stt)
finally:
    p.terminate()
    fake.shutdown()

print()
print("%d passed, %d failed" % (len(P), len(F)))
if F:
    print("server log tail:")
    print("".join(open(w + "/l").readlines()[-30:]))
sys.exit(1 if F else 0)
