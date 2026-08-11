"""Attack it the same way as everything else: from the position of an operator
trying to make a grant look older than it is."""
import hashlib, json, sqlite3, threading, time, sys, types
import witnessed as W

P, F = [], []
def check(n, c, d=""):
    (P if c else F).append(n)
    print(("  ok   " if c else "  FAIL ") + n + (("  -> " + str(d)[:200]) if d and not c else ""))

def make():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    lock = threading.RLock(); n = {"i": 0}
    conn.execute("CREATE TABLE audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,"
                 "ts REAL,user_id TEXT,api_key TEXT,result_json TEXT,audit_hash TEXT)")
    # the real grant table shape, including columns added later
    conn.execute("CREATE TABLE auth_grant(id TEXT PRIMARY KEY,parent TEXT,root TEXT,"
                 "issuer TEXT,subject TEXT,created REAL,digest TEXT,audit_hash TEXT,"
                 "block_index INTEGER,risk_accepted_by TEXT)")
    def seal(ev, res, ts, key):
        n["i"] += 1
        h = hashlib.sha256(json.dumps([ev,res,ts,n["i"]],sort_keys=True,default=str).encode()).hexdigest()
        conn.execute("INSERT INTO audit_log(ts,user_id,api_key,result_json,audit_hash) "
                     "VALUES(?,?,?,?,?)", (ts, ev.get("user_id"), key, json.dumps(res), h))
        conn.commit()
        return h, n["i"], n["i"]
    W._ready = False
    ctx = {"conn": conn, "lock": lock, "seal": seal}
    W._setup(ctx)
    return ctx

def seal_grant(ctx, gid, created):
    h, idx, _ = ctx["seal"]({"user_id": "lin:"+gid}, {"decision":"AUTHORITY_GRANTED","grant":gid}, created, "k")
    with ctx["lock"]:
        ctx["conn"].execute("INSERT INTO auth_grant(id,issuer,subject,created,audit_hash,block_index) "
                            "VALUES(?,?,?,?,?,?)", (gid,"owner@example.com","agent",created,h,idx))
        ctx["conn"].commit()
    return h

def noise(ctx, k=5):
    for i in range(k):
        ctx["seal"]({"user_id":"n%d"%i},{"decision":"ALLOW"},time.time(),"k")

def record_head(ctx, peer, accepted=1, when=None, size=None, tip=None):
    """Insert an attestation directly, standing in for a live peer."""
    s, t = W._head(ctx)
    when = when or time.time()
    with ctx["lock"]:
        ctx["conn"].execute(
            "INSERT INTO witnessed_head(peer,peer_url,tree_size,tip,head_digest,"
            "submitted,accepted,peer_response,peer_block,audit_hash,block_index,api_key)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (peer,"https://%s"%peer, size or s, tip or t,"d",when,accepted,"{}","b1","ah",1,"k"))
        ctx["conn"].commit()

NOW = time.time()

print("\n=== 1. a grant witnessed after issue ===")
ctx = make()
noise(ctx, 3)
g = seal_grant(ctx, "root", NOW - 3600)
noise(ctx, 4)
record_head(ctx, "redflagai.pro", when=NOW - 1800)
r, code = W._grant(ctx, {"id": "root"})
check("witnessed grant reports externally_witnessed", code==200 and r["externally_witnessed"], r)
check("names the peer and the time", r["earliest_external_witness"]["peer"]=="redflagai.pro", r)
check("gives a four-step plan pointed at the peer",
      len(r["verification_plan"])==4 and "attest" in r["verification_plan"][0]["run"], r["verification_plan"][0])
check("states what it does not prove", "should ever have been issued" in r["what_this_does_not_prove"])
check("reports how long it sat unwitnessed", r["minutes_unwitnessed"] is not None, r.get("minutes_unwitnessed"))

print("\n=== 2. THE ATTACK: a grant back-dated after the fact ===")
# operator invents a root grant now, and writes created= last week
ctx = make()
noise(ctx, 3)
record_head(ctx, "redflagai.pro", when=NOW - 86400)      # peer saw the log yesterday
forged = seal_grant(ctx, "forged", NOW - 7*86400)        # grant CLAIMS to be a week old
r, code = W._grant(ctx, {"id": "forged"})
check("a grant sealed after the last witness is NOT covered", not r["externally_witnessed"], r)
check("and says so plainly rather than staying quiet", "rests on this operator's own record" in r.get("flag",""), r.get("flag"))
# now a peer witnesses; from here it is covered, but only from here
record_head(ctx, "redflagai.pro", when=NOW)
r2, _ = W._grant(ctx, {"id": "forged"})
check("after a later witness it becomes covered", r2["externally_witnessed"])
gapdays = round(r2["minutes_unwitnessed"]/1440.0, 1)
check("the seven-day claim-to-witness gap is published, not hidden",
      r2.get("flag") and "days" in r2["flag"] and gapdays >= 6.9, {"gap_days":gapdays,"flag":r2.get("flag")})

print("\n=== 3. coverage counts only what a peer accepted ===")
ctx = make()
noise(ctx, 2); g = seal_grant(ctx, "g1", NOW); noise(ctx, 2)
record_head(ctx, "peer-that-refused", accepted=0)
r, _ = W._grant(ctx, {"id": "g1"})
check("a refused submission gives no coverage", not r["externally_witnessed"], r.get("earliest_external_witness"))
h, _ = W._heads(ctx, {})
check("but the refusal is still on the public record", h["count"]==1 and h["heads"][0]["accepted"] is False, h)

print("\n=== 4. a head that predates the grant does not cover it ===")
ctx = make()
record_head(ctx, "early-peer", when=NOW-9999)   # size 0
noise(ctx, 3)
seal_grant(ctx, "later", NOW)
r, _ = W._grant(ctx, {"id": "later"})
check("an earlier, smaller head cannot reach a later record", not r["externally_witnessed"], r)

print("\n=== 5. the earliest witness wins, not the most convenient ===")
ctx = make()
noise(ctx, 2); seal_grant(ctx, "g", NOW - 600); noise(ctx, 2)
record_head(ctx, "second-peer", when=NOW - 100)
record_head(ctx, "first-peer",  when=NOW - 400)
r, _ = W._grant(ctx, {"id": "g"})
check("earliest accepted attestation is the one reported",
      r["earliest_external_witness"]["peer"]=="first-peer", r["earliest_external_witness"])
check("the others are listed too", any(c["peer"]=="second-peer" for c in r["also_witnessed_by"]), r["also_witnessed_by"])

print("\n=== 6. status is honest about thin networks ===")
ctx = make(); noise(ctx, 3)
s, _ = W._status(ctx)
check("no peers at all reports strength none", s["strength"]=="none" and "rests on our own record" in s["flag"], s)
record_head(ctx, "only-peer")
s, _ = W._status(ctx)
check("one peer reports weak and names collusion", s["strength"]=="weak" and "collude" in s["flag"], s)
for p in ("p2","p3"): record_head(ctx, p)
s, _ = W._status(ctx)
check("three peers reports reasonable", s["strength"]=="reasonable", s)
noise(ctx, 6)
s, _ = W._status(ctx)
check("records sealed since the last head are counted as unwitnessed",
      s["records_not_yet_witnessed"]==6, s)

print("\n=== 7. tampering with the grant row ===")
ctx = make(); noise(ctx,2); seal_grant(ctx,"t",NOW); record_head(ctx,"peer")
with ctx["lock"]:
    ctx["conn"].execute("UPDATE auth_grant SET audit_hash='0'*64 WHERE id='t'")
    ctx["conn"].commit()
r, code = W._grant(ctx, {"id":"t"})
check("a grant whose seal is not in the log is a finding, not a 404",
      code==409 and "finding" in r.get("message",""), (code, r))

print("\n=== 8. url safety on submit ===")
ctx = make(); noise(ctx,2)
for bad, why in [("http://127.0.0.1/x","loopback"),("http://10.0.0.5/x","private"),
                 ("ftp://example.com","scheme"),("https://example.com:8443/x","port")]:
    r, code = W._submit(ctx, "k", {"peer":"p","url":bad})
    check("refuses %s" % why, code==400 and r.get("error")=="url_refused", (bad,code,r))

print("\n=== 9. any sealed record, not just grants ===")
ctx = make(); noise(ctx,2)
h,_ ,_ = ctx["seal"]({"user_id":"x"},{"decision":"ALLOW"},NOW,"k")
noise(ctx,1); record_head(ctx,"peer")
r, code = W._record(ctx, {"hash": h})
check("a decision receipt gets the same treatment", code==200 and r["externally_witnessed"], r)
r, code = W._record(ctx, {"hash": "zz"})
check("a malformed hash is refused", code==400, (code,r))

print("\n" + "="*62)
print("passed %d, failed %d" % (len(P), len(F)))
for f in F: print("  FAILED: " + f)
sys.exit(1 if F else 0)
