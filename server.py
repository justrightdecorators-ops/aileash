import hashlib
import secrets
import sqlite3
import time
import os
import smtplib
from email.mime.text import MIMEText
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DB_PATH = os.getenv("DB_PATH", "aileash.db")
ADMIN_KEY = os.getenv("ADMIN_KEY", secrets.token_hex(32))
FREE_TIER_LIMIT = 1000
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "hello@monopcontent.com")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
        tier TEXT DEFAULT 'free', usage_count INTEGER DEFAULT 0,
        created_at REAL NOT NULL, active INTEGER DEFAULT 1)""")
    c.execute("""CREATE TABLE IF NOT EXISTS trust_scores (
        agent_id TEXT PRIMARY KEY, score REAL DEFAULT 0.5,
        total_reqs INTEGER DEFAULT 0, blocks INTEGER DEFAULT 0,
        updated_at REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS velocity (
        agent_id TEXT NOT NULL, ts REAL NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_vel ON velocity(agent_id, ts)")
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,
        api_key TEXT NOT NULL, agent_id TEXT NOT NULL, action TEXT NOT NULL,
        score REAL NOT NULL, decision TEXT NOT NULL, amount REAL,
        country TEXT, anomaly REAL, device_risk REAL,
        entry_hash TEXT NOT NULL, prev_hash TEXT NOT NULL)""")
    conn.commit()
    conn.close()
    print(f"[AILeash] Ready. ADMIN_KEY={ADMIN_KEY}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="AILeash", version="2.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    ms = int((time.time() - start) * 1000)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {request.method} {request.url.path} -> {response.status_code} ({ms}ms)")
    return response

def send_key_email(to_email: str, api_key: str):
    if not SMTP_HOST:
        print(f"[AILeash] No SMTP. Key for {to_email}: {api_key}")
        return
    try:
        body = f"Welcome to AILeash.\n\nYour API key: {api_key}\n\nFree tier: {FREE_TIER_LIMIT} requests.\n\nPOST /govern with header x-api-key: {api_key}\n\nMonopcontent | hello@monopcontent.com"
        msg = MIMEText(body)
        msg["Subject"] = "Your AILeash API Key"
        msg["From"] = FROM_EMAIL
        msg["To"] = to_email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(FROM_EMAIL, to_email, msg.as_string())
    except Exception as e:
        print(f"[AILeash] Email error: {e}")

def get_key_record(api_key: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM api_keys WHERE key=? AND active=1", (api_key,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return dict(row)

def check_and_increment(api_key: str, tier: str, usage_count: int):
    if tier == "free" and usage_count >= FREE_TIER_LIMIT:
        raise HTTPException(status_code=402, detail="Free tier limit reached. Upgrade at $99/month.")
    conn = get_db()
    conn.execute("UPDATE api_keys SET usage_count=usage_count+1 WHERE key=?", (api_key,))
    conn.commit()
    conn.close()

HIGH_RISK = {"RU", "KP", "IR", "SY", "BY"}

def get_trust(agent_id: str) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM trust_scores WHERE agent_id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"agent_id": agent_id, "score": 0.5, "total_reqs": 0, "blocks": 0}

def update_trust(agent_id: str, decision: str):
    conn = get_db()
    now = time.time()
    row = conn.execute("SELECT * FROM trust_scores WHERE agent_id=?", (agent_id,)).fetchone()
    if row:
        score = row["score"]
        total = row["total_reqs"] + 1
        blocks = row["blocks"] + (1 if decision == "BLOCK" else 0)
        if decision == "ALLOW": score = min(1.0, score + 0.01)
        elif decision == "CHALLENGE": score = max(0.0, score - 0.05)
        else: score = max(0.0, score - 0.15)
        conn.execute("UPDATE trust_scores SET score=?,total_reqs=?,blocks=?,updated_at=? WHERE agent_id=?",
                     (score, total, blocks, now, agent_id))
    else:
        conn.execute("INSERT INTO trust_scores VALUES (?,0.5,1,?,?)",
                     (agent_id, 1 if decision == "BLOCK" else 0, now))
    conn.commit()
    conn.close()

def get_velocity(agent_id: str) -> float:
    now = time.time()
    conn = get_db()
    conn.execute("INSERT INTO velocity VALUES (?,?)", (agent_id, now))
    conn.commit()
    w1 = conn.execute("SELECT COUNT(*) FROM velocity WHERE agent_id=? AND ts>?", (agent_id, now-60)).fetchone()[0]
    w2 = conn.execute("SELECT COUNT(*) FROM velocity WHERE agent_id=? AND ts>?", (agent_id, now-300)).fetchone()[0]
    w3 = conn.execute("SELECT COUNT(*) FROM velocity WHERE agent_id=? AND ts>?", (agent_id, now-3600)).fetchone()[0]
    conn.execute("DELETE FROM velocity WHERE agent_id=? AND ts<?", (agent_id, now-3600))
    conn.commit()
    conn.close()
    score = 0.0
    if w1 > 10: score += 0.4
    elif w1 > 5: score += 0.2
    if w2 > 30: score += 0.3
    elif w2 > 15: score += 0.15
    if w3 > 200: score += 0.3
    elif w3 > 100: score += 0.15
    return min(1.0, score)

def compute_score(amount, device_risk, anomaly, country, trust, velocity) -> float:
    base = 0.0
    if amount > 10000: base += 0.35
    elif amount > 5000: base += 0.2
    elif amount > 1000: base += 0.1
    base += device_risk * 0.2
    base += anomaly * 0.25
    if country.upper() in HIGH_RISK: base += 0.2
    base += velocity * 0.15
    base += (0.5 - trust["score"]) * 0.1
    return round(min(1.0, max(0.0, base)), 4)

def score_to_decision(score: float) -> str:
    if score < 0.30: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def get_prev_hash() -> str:
    conn = get_db()
    row = conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return row["entry_hash"] if row else "0" * 64

def write_audit(api_key, agent_id, action, score, decision, amount, country, anomaly, device_risk) -> str:
    now = time.time()
    prev = get_prev_hash()
    entry_hash = hashlib.sha256(f"{now}{api_key}{agent_id}{action}{score}{decision}{prev}".encode()).hexdigest()
    conn = get_db()
    conn.execute("INSERT INTO audit_log (ts,api_key,agent_id,action,score,decision,amount,country,anomaly,device_risk,entry_hash,prev_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (now, api_key, agent_id, action, score, decision, amount, country, anomaly, device_risk, entry_hash, prev))
    conn.commit()
    conn.close()
    return entry_hash

class SignupRequest(BaseModel):
    email: str

class GovernRequest(BaseModel):
    action: str
    amount: float = 0.0
    device_risk: float = 0.0
    anomaly: float = 0.0
    country: str = "US"
    agent_id: Optional[str] = "default"

LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AILeash — AI Action Firewall</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#f0f0f0;font-family:'Courier New',monospace;line-height:1.6}
.bar{background:#ff3c00;color:#fff;text-align:center;padding:12px;font-size:13px;font-weight:700;letter-spacing:2px}
nav{display:flex;justify-content:space-between;align-items:center;padding:24px 48px;border-bottom:1px solid #1a1a1a}
.logo{font-size:20px;font-weight:700;letter-spacing:4px}
.hero{padding:120px 48px 80px;max-width:900px}
.hero h1{font-size:clamp(36px,6vw,72px);font-weight:700;line-height:1.1;margin-bottom:24px}
.hero p{font-size:18px;color:#888;max-width:600px;margin-bottom:48px}
.stats{display:flex;gap:48px;margin-bottom:80px;padding:0 48px}
.stat{border-left:2px solid #ff3c00;padding-left:16px}
.stat-n{font-size:32px;font-weight:700}
.stat-l{font-size:12px;color:#666;letter-spacing:2px}
section{padding:80px 48px;border-top:1px solid #1a1a1a}
section h2{font-size:11px;color:#ff3c00;letter-spacing:4px;margin-bottom:48px}
.decisions{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-bottom:48px}
.decision{padding:32px;border:1px solid #1a1a1a}
.decision .range{font-size:24px;font-weight:700;margin-bottom:8px}
.allow{color:#00ff88}.challenge{color:#ffaa00}.block{color:#ff3c00}
.code{background:#111;border:1px solid #1a1a1a;padding:32px;font-size:13px;overflow-x:auto;margin:24px 0}
.code pre{color:#888;line-height:2}
.code .key{color:#ff3c00}.code .val{color:#00ff88}.code .res{color:#ffaa00}
.compliance{display:grid;grid-template-columns:repeat(2,1fr);gap:24px}
.comp-block{padding:32px;border:1px solid #1a1a1a}
.comp-block h3{font-size:13px;letter-spacing:2px;margin-bottom:16px;color:#ff3c00}
.comp-block p{font-size:13px;color:#666;line-height:2}
.pricing{text-align:center;padding:80px 48px}
.pricing h2{font-size:11px;color:#ff3c00;letter-spacing:4px;margin-bottom:16px}
.price{font-size:72px;font-weight:700;margin:24px 0}
.price span{font-size:20px;color:#666}
.features{list-style:none;margin:32px auto;max-width:400px;text-align:left}
.features li{padding:8px 0;border-bottom:1px solid #1a1a1a;font-size:14px;color:#888}
.features li::before{content:"+ ";color:#ff3c00}
.signup-form{max-width:480px;margin:32px auto 0}
.signup-form input{width:100%;padding:16px;background:#111;border:1px solid #333;color:#f0f0f0;font-family:'Courier New',monospace;font-size:14px;margin-bottom:12px}
.signup-form input:focus{outline:none;border-color:#ff3c00}
.signup-form button{width:100%;padding:16px;background:#ff3c00;color:#fff;border:none;font-family:'Courier New',monospace;font-size:14px;font-weight:700;letter-spacing:2px;cursor:pointer}
.signup-form button:hover{background:#cc3000}
#signup-msg{margin-top:12px;font-size:13px;text-align:center}
.faq{padding:80px 48px;border-top:1px solid #1a1a1a}
.faq h2{font-size:11px;color:#ff3c00;letter-spacing:4px;margin-bottom:48px}
.faq-item{padding:24px 0;border-bottom:1px solid #1a1a1a}
.faq-item h3{font-size:14px;margin-bottom:8px}
.faq-item p{font-size:13px;color:#666}
footer{padding:48px;border-top:1px solid #1a1a1a;display:flex;justify-content:space-between;font-size:12px;color:#444}
@media(max-width:768px){
nav{padding:16px 24px}.hero{padding:60px 24px 40px}
.stats{padding:0 24px;gap:24px;flex-wrap:wrap}
section{padding:48px 24px}.decisions{grid-template-columns:1fr}
.compliance{grid-template-columns:1fr}.pricing{padding:48px 24px}
.faq{padding:48px 24px}footer{padding:24px;flex-direction:column;gap:8px}}
</style>
</head>
<body>
<div class="bar">EU AI ACT ENFORCEMENT: 2 AUGUST 2026 &nbsp;|&nbsp; FINES UP TO 35 MILLION EUROS</div>
<nav><div class="logo">AILEASH</div><div style="font-size:12px;color:#666">by Monopcontent</div></nav>
<div class="hero">
<h1>AI ACTION<br>FIREWALL</h1>
<p>Stop unsafe AI actions before they execute. Risk scored. Governed. Audited. Block high-risk actions before they cause damage.</p>
<a href="#pricing" style="display:inline-block;padding:16px 32px;background:#ff3c00;color:#fff;text-decoration:none;font-weight:700;letter-spacing:2px;font-size:13px">START FOR $99/MONTH</a>
</div>
<div class="stats">
<div class="stat"><div class="stat-n">0</div><div class="stat-l">DEPENDENCIES</div></div>
<div class="stat"><div class="stat-n">2 min</div><div class="stat-l">TO DEPLOY</div></div>
<div class="stat"><div class="stat-n">100%</div><div class="stat-l">AUDIT COVERAGE</div></div>
<div class="stat"><div class="stat-n">35M</div><div class="stat-l">MAX EU FINE</div></div>
</div>
<section>
<h2>// WHAT IT DOES</h2>
<div class="decisions">
<div class="decision"><div class="range allow">0.00-0.29</div><div style="font-weight:700;margin:8px 0">ALLOW</div><div style="font-size:13px;color:#666">Safe. Passes through. Logged.</div></div>
<div class="decision"><div class="range challenge">0.30-0.69</div><div style="font-weight:700;margin:8px 0">CHALLENGE</div><div style="font-size:13px;color:#666">Elevated risk. Flagged for review.</div></div>
<div class="decision"><div class="range block">0.70-1.00</div><div style="font-weight:700;margin:8px 0">BLOCK</div><div style="font-size:13px;color:#666">High risk. Stopped before execution.</div></div>
</div>
</section>
<section>
<h2>// COMPLIANCE</h2>
<div class="compliance">
<div class="comp-block"><h3>EU AI ACT 2026</h3><p>Article 9 — Risk management<br>Article 12 — Lifecycle logging<br>Article 13 — Transparency<br>Article 14 — Human oversight</p></div>
<div class="comp-block"><h3>UK AI FRAMEWORK</h3><p>Explainable decision output<br>Full audit trail<br>Human oversight built in<br>Risk-based governance</p></div>
<div class="comp-block"><h3>US STATE LEGISLATION</h3><p>Colorado SB 205<br>California AB 2013<br>SEC AI guidance<br>FTC AI fairness</p></div>
<div class="comp-block"><h3>AUDIT CHAIN</h3><p>SHA-256 chained<br>Tamper-evident<br>Regulator-ready<br>Every decision linked</p></div>
</div>
</section>
<div class="pricing" id="pricing">
<h2>// PRICING</h2>
<div class="price">$99<span>/month</span></div>
<p style="color:#666;font-size:13px">Free tier: 1000 requests. No card required.</p>
<ul class="features">
<li>Unlimited governed requests</li>
<li>Real-time risk scoring</li>
<li>SHA-256 chained audit log</li>
<li>ALLOW / CHALLENGE / BLOCK</li>
<li>Trust engine and velocity detection</li>
<li>EU AI Act Articles 9 12 13 14</li>
<li>Flask and FastAPI middleware</li>
<li>Email support</li>
<li>Cancel anytime</li>
</ul>
<div class="signup-form">
<input type="email" id="email-input" placeholder="cto@yourcompany.com">
<button onclick="doSignup()">START FOR $99/MONTH</button>
<div id="signup-msg"></div>
</div>
</div>
<div class="faq">
<h2>// FAQ</h2>
<div class="faq-item"><h3>How does the free tier work?</h3><p>Enter your email and get an API key immediately. Free tier includes 1000 governed requests. After that upgrade to Pro for $99/month.</p></div>
<div class="faq-item"><h3>Do I need to change my existing code?</h3><p>Minimal changes. Add one API call before each AI action executes. Check the decision. Act accordingly.</p></div>
<div class="faq-item"><h3>How is this different from monitoring tools?</h3><p>Other tools detect. AILeash prevents. It intercepts the action before your code executes it.</p></div>
<div class="faq-item"><h3>Does this make me EU AI Act compliant?</h3><p>AILeash implements core technical requirements of Articles 9, 12, 13, and 14. Consult qualified legal counsel for your specific obligations.</p></div>
</div>
<footer>
<div>AILeash by Monopcontent | Built for the AI Act.</div>
<div>hello@monopcontent.com | Not a substitute for legal advice.</div>
</footer>
<script>
async function doSignup() {
  const email = document.getElementById('email-input').value.trim();
  const msg = document.getElementById('signup-msg');
  if (!email || !email.includes('@')) {
    msg.style.color = '#ff3c00';
    msg.textContent = 'Please enter a valid email address.';
    return;
  }
  msg.style.color = '#888';
  msg.textContent = 'Processing...';
  try {
    const res = await fetch('/signup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email})
    });
    const data = await res.json();
    if (res.ok) {
      msg.style.color = '#00ff88';
      msg.textContent = 'API key created. Check your email.';
    } else {
      msg.style.color = '#ff3c00';
      msg.textContent = data.detail || 'Something went wrong.';
    }
  } catch(e) {
    msg.style.color = '#ff3c00';
    msg.textContent = 'Connection error. Try again.';
  }
}
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content=LANDING_PAGE)

@app.get("/health")
def health():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}

@app.post("/signup")
def signup(req: SignupRequest):
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email required")
    conn = get_db()
    existing = conn.execute("SELECT key FROM api_keys WHERE email=?", (email,)).fetchone()
    if existing:
        conn.close()
        send_key_email(email, existing["key"])
        return {"message": "Key resent to your email.", "tier": "free", "free_requests": FREE_TIER_LIMIT}
    api_key = "al_" + secrets.token_urlsafe(32)
    conn.execute("INSERT INTO api_keys (key,email,tier,usage_count,created_at,active) VALUES (?,?,?,?,?,?)",
                 (api_key, email, "free", 0, time.time(), 1))
    conn.commit()
    conn.close()
    send_key_email(email, api_key)
    return {"message": "API key created. Check your email.", "api_key": api_key, "tier": "free", "free_requests": FREE_TIER_LIMIT}

@app.post("/govern")
def govern(req: GovernRequest, x_api_key: str = Header(...)):
    record = get_key_record(x_api_key)
    check_and_increment(x_api_key, record["tier"], record["usage_count"])
    trust = get_trust(req.agent_id)
    velocity = get_velocity(req.agent_id)
    score = compute_score(req.amount, req.device_risk, req.anomaly, req.country, trust, velocity)
    decision = score_to_decision(score)
    entry_hash = write_audit(x_api_key, req.agent_id, req.action, score, decision, req.amount, req.country, req.anomaly, req.device_risk)
    update_trust(req.agent_id, decision)
    remaining = max(0, FREE_TIER_LIMIT - record["usage_count"] - 1) if record["tier"] == "free" else None
    return {"decision": decision, "score": score, "agent_id": req.agent_id,
            "trust_score": round(trust["score"], 4), "velocity_risk": round(velocity, 4),
            "audit_hash": entry_hash, "ts": datetime.now(timezone.utc).isoformat(), "requests_remaining": remaining}

@app.get("/audit/chain")
def audit_chain(limit: int = 50, x_api_key: str = Header(...)):
    get_key_record(x_api_key)
    conn = get_db()
    rows = conn.execute("SELECT * FROM audit_log WHERE api_key=? ORDER BY id DESC LIMIT ?", (x_api_key, limit)).fetchall()
    conn.close()
    return {"total": len(rows), "entries": [dict(r) for r in rows]}

@app.get("/audit/verify")
def audit_verify(x_api_key: str = Header(...)):
    get_key_record(x_api_key)
    conn = get_db()
    rows = conn.execute("SELECT * FROM audit_log WHERE api_key=? ORDER BY id ASC", (x_api_key,)).fetchall()
    conn.close()
    if not rows:
        return {"valid": True, "entries_checked": 0, "message": "No entries yet"}
    prev = "0" * 64
    broken_at = None
    for row in rows:
        expected = hashlib.sha256(f"{row['ts']}{row['api_key']}{row['agent_id']}{row['action']}{row['score']}{row['decision']}{prev}".encode()).hexdigest()
        if expected != row["entry_hash"]:
            broken_at = row["id"]
            break
        prev = row["entry_hash"]
    return {"valid": broken_at is None, "entries_checked": len(rows),
            "message": "Chain intact" if broken_at is None else f"Chain broken at entry {broken_at}"}

@app.get("/usage")
def usage(x_api_key: str = Header(...)):
    record = get_key_record(x_api_key)
    used = record["usage_count"]
    tier = record["tier"]
    limit = FREE_TIER_LIMIT if tier == "free" else None
    return {"email": record["email"], "tier": tier, "usage_count": used,
            "limit": limit, "remaining": max(0, limit - used) if limit else "unlimited"}

@app.post("/admin/upgrade")
def admin_upgrade(email: str, x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Admin only")
    conn = get_db()
    result = conn.execute("UPDATE api_keys SET tier='pro' WHERE email=?", (email,))
    conn.commit()
    conn.close()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Email not found")
    return {"message": f"{email} upgraded to pro"}

@app.get("/admin/users")
def admin_users(x_api_key: str = Header(...)):
    if not secrets.compare_digest(x_api_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Admin only")
    conn = get_db()
    rows = conn.execute("SELECT email,tier,usage_count,created_at,active FROM api_keys ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"total": len(rows), "users": [dict(r) for r in rows]}
