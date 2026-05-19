import json
import sqlite3
import hashlib
import time
from datetime import datetime
from collections import Counter
from collections import defaultdict
from collections import deque

DB1 = "aileash.db"
DB2 = "leads.db"
SAFE = {"UK","US","DE","FR","CA","AU"}
W60 = defaultdict(deque)
W5M = defaultdict(deque)
W1H = defaultdict(deque)

def now():
    return time.time()

def clamp(x):
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x

def sha(p):
    s = json.dumps(p, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()

def bar(v, total):
    w = 14
    if total == 0:
        return "." * w
    f = int((v / total) * w)
    return "#" * f + "." * (w - f)

def sep(t):
    print("")
    print("--------------------------------------------------")
    print("  " + t)
    print("--------------------------------------------------")

gc = sqlite3.connect(DB1)
gc.row_factory = sqlite3.Row
gc.execute(
    "CREATE TABLE IF NOT EXISTS users ("
    "user_id TEXT PRIMARY KEY,"
    "trust REAL DEFAULT 0.5,"
    "last_country TEXT)"
)
gc.execute(
    "CREATE TABLE IF NOT EXISTS audit_log ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "ts REAL,"
    "user_id TEXT,"
    "event_json TEXT,"
    "result_json TEXT,"
    "prev_hash TEXT,"
    "audit_hash TEXT UNIQUE)"
)
gc.commit()

def load_user(uid):
    row = gc.execute(
        "SELECT trust, last_country FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    if row:
        return {"trust": row[0], "last_country": row[1]}
    return {"trust": 0.5, "last_country": None}

def save_user(uid, trust, country):
    gc.execute(
        "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?)"
        " ON CONFLICT(user_id) DO UPDATE SET"
        " trust=excluded.trust,"
        " last_country=excluded.last_country",
        (uid, trust, country)
    )
    gc.commit()

def prune(q, s):
    c = now() - s
    while q and q[0] < c:
        q.popleft()

def update_windows(uid):
    t = now()
    W60[uid].append(t)
    W5M[uid].append(t)
    W1H[uid].append(t)
    prune(W60[uid], 60)
    prune(W5M[uid], 300)
    prune(W1H[uid], 3600)

def chain_tip():
    row = gc.execute(
        "SELECT audit_hash FROM audit_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return row[0]
    return "GENESIS"

def do_audit(event, result):
    prev = chain_tip()
    payload = {
        "prev_hash": prev,
        "ts": now(),
        "event": event,
        "result": result
    }
    h = sha(payload)
    gc.execute(
        "INSERT INTO audit_log"
        "(ts,user_id,event_json,result_json,prev_hash,audit_hash)"
        " VALUES(?,?,?,?,?,?)",
        (
            now(),
            event["user_id"],
            json.dumps(event),
            json.dumps(result),
            prev,
            h
        )
    )
    gc.commit()
    return h

def govern(event):
    state = load_user(event["user_id"])
    update_windows(event["user_id"])
    v60 = len(W60[event["user_id"]])
    v5m = len(W5M[event["user_id"]])
    v1h = len(W1H[event["user_id"]])
    country = event.get("country", "UK")
    amount = event.get("amount", 0)
    device_risk = event.get("device_risk", 0.1)
    anomaly = event.get("anomaly", 0.05)
    s = 0.0
    s += (1.0 - state["trust"]) * 0.30
    s += min(v60 / 20.0, 1.0) * 0.15
    s += min(v5m / 50.0, 1.0) * 0.10
    s += min(v1h / 200.0, 1.0) * 0.10
    s += min(amount / 1000.0, 1.0) * 0.15
    s += device_risk * 0.10
    s += anomaly * 0.10
    if state["last_country"] and state["last_country"] != country:
        s += 0.10
    if country not in SAFE:
        s += 0.10
    s = clamp(s)
    if s < 0.35:
        decision = "ALLOW"
    elif s < 0.70:
        decision = "CHALLENGE"
    else:
        decision = "BLOCK"
    reasons = []
    if state["trust"] < 0.4:
        reasons.append("low_trust")
    if v60 > 10:
        reasons.append("velocity_spike")
    if amount > 500:
        reasons.append("high_amount")
    if device_risk > 0.5:
        reasons.append("risky_device")
    if state["last_country"] and state["last_country"] != country:
        reasons.append("country_shift")
    if country not in SAFE:
        reasons.append("unsafe_country")
    if anomaly > 0.5:
        reasons.append("behaviour_anomaly")
    trust = state["trust"]
    if decision == "ALLOW":
        trust += (1.0 - trust) * 0.01
    elif decision == "CHALLENGE":
        trust -= trust * 0.02
    elif decision == "BLOCK":
        trust -= trust * 0.08
    trust = clamp(trust)
    if trust < 0.05:
        trust = 0.05
    save_user(event["user_id"], trust, country)
    result = {
        "decision": decision,
        "score": round(s, 4),
        "trust": round(trust, 4),
        "reasons": reasons
    }
    result["audit_hash"] = do_audit(event, result)
    return result

lc = sqlite3.connect(DB2)
lc.row_factory = sqlite3.Row
lc.execute(
    "CREATE TABLE IF NOT EXISTS leads ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "company TEXT UNIQUE,"
    "contact TEXT,"
    "sector TEXT,"
    "eu_presence INTEGER,"
    "ai_products INTEGER,"
    "has_compliance INTEGER,"
    "company_size TEXT,"
    "score REAL,"
    "decision TEXT,"
    "notes TEXT,"
    "status TEXT DEFAULT 'NEW',"
    "added_ts REAL)"
)
lc.commit()

SECTORS = {
    "fintech": 0.95,
    "healthtech": 0.90,
    "legaltech": 0.85,
    "insurtech": 0.85,
    "govtech": 0.80,
    "edtech": 0.70,
    "saas": 0.65,
    "ecommerce": 0.55,
    "other": 0.40,
}

SIZES = {
    "enterprise": 1.0,
    "scaleup": 0.75,
    "startup": 0.50,
    "solo": 0.20,
}

DAYS_LEFT = max(0.0, (1754006400.0 - now()) / 86400.0)

def score_lead(eu, ai, compliance, sector, size):
    s = 0.0
    if eu:
        s += 0.30
    if ai:
        s += 0.25
    if not compliance:
        s += 0.20
    s += SECTORS.get(sector.lower(), 0.4) * 0.15
    s += SIZES.get(size.lower(), 0.5) * 0.10
    pressure = clamp(1.0 - (DAYS_LEFT / 365.0))
    s += pressure * 0.10
    return clamp(s)

def add_lead(company, contact, sector, eu, ai, compliance, size, notes=""):
    s = score_lead(eu, ai, compliance, sector, size)
    if s >= 0.75:
        decision = "HOT"
    elif s >= 0.50:
        decision = "WARM"
    else:
        decision = "COLD"
    lc.execute(
        "INSERT OR REPLACE INTO leads"
        "(company,contact,sector,eu_presence,ai_products,"
        "has_compliance,company_size,score,decision,notes,status,added_ts)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            company, contact, sector,
            int(eu), int(ai), int(compliance),
            size, round(s, 4), decision,
            notes, "NEW", now()
        )
    )
    lc.commit()
    return s, decision

LEADS = [
    ("FinCore AI",     "compliance@fincoreai.com",   "fintech",    True,  True,  False, "scaleup",    "AI credit scoring. No audit trail."),
    ("MediAgent Ltd",  "cto@mediagent.io",           "healthtech", True,  True,  False, "startup",    "AI triage. GDPR and AI Act exposure."),
    ("LexBot Systems", "cto@lexbot.com",             "legaltech",  True,  True,  False, "scaleup",    "AI contract review. Clients need logs."),
    ("CoverDrive AI",  "compliance@coverdrive.io",   "insurtech",  True,  True,  False, "startup",    "AI underwriting. FCA and AI Act."),
    ("GovLink",        "digital@govlink.gov",        "govtech",    True,  True,  False, "enterprise", "Public sector AI. Highest exposure."),
    ("EduFlow AI",     "cto@eduflow.ai",             "edtech",     False, True,  False, "startup",    "UK only now. EU expansion planned."),
    ("TradeStack",     "engineering@tradestack.com", "fintech",    True,  True,  True,  "enterprise", "Has compliance but likely gaps."),
]

ICONS = {"ALLOW":"[OK]","CHALLENGE":"[??]","BLOCK":"[XX]"}

print("")
print("==================================================")
print("  AILEASH COMPLETE SYSTEM")
print("  by Monopcontent")
print("==================================================")

sep("1 of 3  GOVERNANCE ENGINE")

TEST = [
    {"user_id":"agent_trusted", "action":"data_query",    "amount":10,    "country":"UK", "device_risk":0.05, "anomaly":0.05},
    {"user_id":"agent_trusted", "action":"report_write",  "amount":50,    "country":"UK", "device_risk":0.05, "anomaly":0.05},
    {"user_id":"agent_risky",   "action":"wire_transfer", "amount":18500, "country":"RU", "device_risk":0.72, "anomaly":0.81},
    {"user_id":"agent_shifty",  "action":"data_query",    "amount":200,   "country":"UK", "device_risk":0.20, "anomaly":0.15},
    {"user_id":"agent_shifty",  "action":"data_query",    "amount":200,   "country":"CN", "device_risk":0.20, "anomaly":0.45},
]

print("")
for e in TEST:
    r = govern(e)
    icon = ICONS[r["decision"]]
    reas = ", ".join(r["reasons"]) if r["reasons"] else "none"
    print(
        "  " + icon +
        " " + e["user_id"].ljust(16) +
        " score=" + str(r["score"]) +
        " trust=" + str(r["trust"]) +
        " [" + reas + "]"
    )

total_events = gc.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
tip = chain_tip()
print("")
print("  Audit chain: " + str(total_events) + " entries")
print("  Chain tip  : " + tip[:24] + "...")

sep("2 of 3  LEAD ENGINE")

existing = lc.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
if existing == 0:
    for lead in LEADS:
        add_lead(*lead)

rows = lc.execute(
    "SELECT * FROM leads ORDER BY score DESC"
).fetchall()

total_leads = len(rows)
hot  = sum(1 for r in rows if r["decision"] == "HOT")
warm = sum(1 for r in rows if r["decision"] == "WARM")
cold = sum(1 for r in rows if r["decision"] == "COLD")

print("")
print(
    "  Pipeline: " + str(total_leads) +
    " leads  HOT:" + str(hot) +
    "  WARM:" + str(warm) +
    "  COLD:" + str(cold)
)
print("  Days to deadline: " + str(int(DAYS_LEFT)))
print("")

for r in rows:
    tag = {"HOT":"[HH]","WARM":"[WW]","COLD":"[CC]"}
    print(
        "  " + tag.get(r["decision"],"[--]") +
        " " + r["company"].ljust(20) +
        r["decision"].ljust(7) +
        str(r["score"]).ljust(8) +
        r["contact"]
    )

print("")
print("  CONTACT THESE FIRST:")
print("")
for i, r in enumerate([r for r in rows if r["decision"] == "HOT"], 1):
    print("  " + str(i) + ". " + r["company"])
    print("     Email : " + r["contact"])
    print("     Why   : " + r["notes"])
    print("")

sep("3 of 3  STATUS")

users = gc.execute(
    "SELECT user_id, trust FROM users ORDER BY trust ASC"
).fetchall()
all_r = gc.execute("SELECT result_json FROM audit_log").fetchall()
decisions = Counter()
for row in all_r:
    try:
        d = json.loads(row[0]).get("decision","?")
        decisions[d] += 1
    except Exception:
        pass

print("")
print("  AGENT TRUST:")
for u in users:
    t = u["trust"]
    if t >= 0.6:
        status = "TRUSTED"
    elif t >= 0.35:
        status = "WATCH"
    else:
        status = "FLAGGED"
    print(
        "  " + u["user_id"].ljust(18) +
        str(round(t, 4)).ljust(8) +
        status
    )

print("")
print("  DECISIONS:")
total_d = sum(decisions.values())
for d in ["ALLOW","CHALLENGE","BLOCK"]:
    count = decisions.get(d, 0)
    print(
        "  " + ICONS.get(d,"[  ]") +
        " " + d.ljust(12) +
        str(count).rjust(5) +
        "  " + bar(count, total_d)
    )

print("")
print("==================================================")
print("  DONE")
print("  aileash.db  -- audit log")
print("  leads.db    -- sales pipeline")
print("==================================================")
print("")
