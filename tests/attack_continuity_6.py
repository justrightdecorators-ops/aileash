"""End to end: issue, delegate, exercise, export a proof, verify it elsewhere,
then try to forge one."""
import hashlib, json, sqlite3, threading, time, sys, types, subprocess, copy
import continuity as C

m = types.ModuleType("server")
m.get_bearer = lambda *a, **k: None
m.score_event = lambda e: 0.12          # bare score, like the real engine
sys.modules["server"] = m

conn = sqlite3.connect(":memory:", check_same_thread=False)
lock = threading.RLock(); n = {"i": 0}
def seal(ev, res, ts, k):
    n["i"] += 1
    return hashlib.sha256(json.dumps([ev, res, ts], sort_keys=True, default=str).encode()).hexdigest(), n["i"], n["i"]
ctx = {"conn": conn, "lock": lock, "seal": seal}
C._ready = False; C._setup(ctx)

NOW, HOUR = time.time(), 3600
C._issue(ctx, "k", dict(id="root", issuer="justin@monopcontent.com", issuer_kind="human",
    subject="orchestrator", scope=["payments.refund", "payments.read"],
    constraints={"max_amount": 5000, "allowed_currency": ["GBP", "EUR"]},
    purpose="resolve customer refund complaints", purpose_tags=["refunds", "support"],
    not_after=NOW + 10 * HOUR, delegations_left=2))
C._issue(ctx, "k", dict(id="mid", parent="root", issuer="orchestrator", issuer_kind="agent",
    subject="refund-agent", scope=["payments.refund"],
    constraints={"max_amount": 200, "allowed_currency": ["GBP"]},
    purpose="issue small refunds", purpose_tags=["refunds"],
    not_after=NOW + 2 * HOUR, delegations_left=0))

def run(params, tag="refunds", action="payments.refund"):
    r, _ = C._evaluate(ctx, "k", {"grant": "mid", "action": action,
                                  "params": params, "purpose_tag": tag})
    return r

allow = run({"amount": 150, "currency": "GBP"})
block = run({"amount": 900, "currency": "GBP"})
print("allow verdict:", allow["verdict"], "| block verdict:", block["verdict"],
      "->", block["broken_invariant"])

def bundle_for(ev):
    b, code = C._proof(ctx, {"evaluation": ev})
    assert code == 200, b
    return b

for label, ev in (("ALLOW", allow["evaluation"]), ("BLOCK", block["evaluation"])):
    b = bundle_for(ev)
    open("/tmp/%s.json" % label, "w").write(json.dumps(b, indent=1))
    print("\n" + "#" * 66 + "\n# %s bundle\n" % label + "#" * 66)
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/%s.json" % label],
                         capture_output=True, text=True)
    print(out.stdout.strip()); print("exit:", out.returncode)

print("\n" + "#" * 66 + "\n# forgeries\n" + "#" * 66)
good = json.load(open("/tmp/BLOCK.json"))

def forge(name, mutate):
    b = copy.deepcopy(good)
    mutate(b)
    open("/tmp/forged.json", "w").write(json.dumps(b))
    out = subprocess.run([sys.executable, "verify_authority.py", "/tmp/forged.json"],
                         capture_output=True, text=True)
    caught = out.returncode != 0
    line = [l for l in out.stdout.splitlines() if l.startswith("FAIL")]
    print(("  ok   " if caught else "  MISS ") + name)
    for l in line[:2]:
        print("         " + l.strip())

def flip_verdict(b):
    b["decision"]["verdict"] = "ALLOW"; b["decision"]["authority_verdict"] = "ALLOW"
def raise_cap(b):
    pass_idx = 1
    b["lineage"][1]["constraints"]["max_amount"] = 100000
def widen_scope(b):
    b["lineage"][1]["scope"] = ["payments.refund", "payments.transfer"]
def swap_human(b):
    b["lineage"][0]["issuer_kind"] = "agent"
def change_params(b):
    b["request"]["params"]["amount"] = 1
def drop_acceptor(b):
    for g in b["lineage"]: g["risk_accepted_by"] = None
def restamp(b):
    b["decision"]["evaluated_at_epoch"] = NOW + 9 * HOUR

forge("claimed ALLOW on a bundle that blocks", flip_verdict)
forge("cap raised inside the lineage", raise_cap)
forge("scope widened inside the lineage", widen_scope)
forge("root demoted from human", swap_human)
forge("parameters swapped after the fact", change_params)
forge("risk acceptor stripped", drop_acceptor)
forge("timestamp moved past the leaf's expiry", restamp)
