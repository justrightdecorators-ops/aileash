import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer

# -----------------------------
# CONFIG
# -----------------------------
STRIPE_SECRET   = os.environ.get("STRIPE_SECRET", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
PORT            = int(os.environ.get("PORT", 8080))
DB              = "aileash.db"
VERSION         = "3.0.0"

SAFE_COUNTRIES  = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS = {"user_id","action","amount","country","device_id","anomaly","device_risk"}

_db_lock = threading.Lock()

# -----------------------------
# DB
# -----------------------------
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT, event_json TEXT, result_json TEXT)")
    conn.commit()
    return conn

_conn = get_conn()

# -----------------------------
# UTIL
# -----------------------------
def now(): return time.time()
def clamp(x,a=0.0,b=1.0): return max(a,min(b,x))
def sha(x): return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()

# -----------------------------
# USER STATE
# -----------------------------
def load_user(uid):
    with _db_lock:
        row=_conn.execute("SELECT trust,last_country FROM users WHERE user_id=?", (uid,)).fetchone()
    return {"trust":row[0] if row else 0.5, "last_country":row[1] if row else None}

def save_user(uid,trust,country):
    with _db_lock:
        _conn.execute(
            "INSERT INTO users(user_id,trust,last_country) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET trust=excluded.trust,last_country=excluded.last_country",
            (uid,trust,country)
        )
        _conn.commit()

# -----------------------------
# RISK ENGINE (UNCHANGED CORE LOGIC STYLE)
# -----------------------------
WINDOW_60S = defaultdict(deque)

def update_window(uid):
    WINDOW_60S[uid].append(now())
    cutoff = now() - 60
    while WINDOW_60S[uid] and WINDOW_60S[uid][0] < cutoff:
        WINDOW_60S[uid].popleft()

def compute_score(s, trust):
    score = 0
    score += (1-trust)*0.3
    score += min(len(WINDOW_60S[s["user_id"]])/20,1)*0.2
    score += min(math.log1p(s["amount"])/10,1)*0.2
    score += s["device_risk"]*0.15
    score += s["anomaly"]*0.15
    if s["country"] not in SAFE_COUNTRIES:
        score += 0.1
    return clamp(score)

def decide(score):
    if score < 0.35: return "ALLOW"
    if score < 0.70: return "CHALLENGE"
    return "BLOCK"

def explain(s):
    r=[]
    if s["device_risk"]>0.5: r.append("risky_device")
    if s["anomaly"]>0.5: r.append("behaviour_anomaly")
    if s["country"] not in SAFE_COUNTRIES: r.append("unsafe_country")
    return r

# -----------------------------
# GOVERN FUNCTION
# -----------------------------
def govern(event):
    missing = REQUIRED_FIELDS - event.keys()
    if missing:
        return {"error": f"Missing fields: {missing}"}

    uid = event["user_id"]
    state = load_user(uid)
    update_window(event)

    score = compute_score(event, state["trust"])
    decision = decide(score)
    reasons = explain(event)

    trust = state["trust"]
    if decision=="ALLOW": trust += (1-trust)*0.01
    elif decision=="CHALLENGE": trust -= trust*0.02
    else: trust -= trust*0.08

    trust = clamp(trust)
    save_user(uid, trust, event["country"])

    return {
        "decision": decision,
        "score": round(score,4),
        "trust": round(trust,4),
        "reasons": reasons,
        "version": VERSION
    }

# -----------------------------
# LANDING PAGE (UNCHANGED - YOUR ORIGINAL)
# -----------------------------
LANDING="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AILeash — AI Governance & Compliance Infrastructure</title>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--red:#cc0000;--red2:#990000;--black:#0a0a0a;--white:#fff;--off:#f8f8f8;--border:#e0e0e0;--muted:#666;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',sans-serif;--display:'Bebas Neue',sans-serif}
*{box-sizing:border-box;margin:0;padding:0}html{scroll-behavior:smooth}
body{background:#fff;color:#0a0a0a;font-family:var(--sans);overflow-x:hidden}
nav{position:fixed;top:0;left:0;right:0;z-index:100;background:#fff;border-bottom:3px solid var(--red);padding:0 48px;height:64px;display:flex;align-items:center;justify-content:space-between}
.logo{font-family:var(--display);font-size:28px;letter-spacing:2px}.logo span{color:var(--red)}
.nav-links{display:flex;gap:32px;align-items:center}
.nav-links a{color:var(--muted);text-decoration:none;font-size:14px;font-weight:500;transition:color .2s}.nav-links a:hover{color:var(--red)}
.nav-cta{background:var(--red)!important;color:#fff!important;padding:10px 22px;border-radius:4px;font-weight:700!important;letter-spacing:1px!important;text-transform:uppercase;font-size:13px!important}
.hero{padding:120px 48px 80px;border-bottom:1px solid var(--border)}
.hero-inner{max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 1fr;gap:80px;align-items:center}
.eyebrow{display:inline-flex;align-items:center;gap:8px;background:var(--red);color:#fff;padding:6px 14px;font-family:var(--mono);font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-bottom:24px}
.eyebrow::before{content:'';width:6px;height:6px;background:#fff;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
h1{font-family:var(--display);font-size:clamp(56px,6vw,88px);line-height:.95;letter-spacing:2px;margin-bottom:24px;text-transform:uppercase}
h1 .red{color:var(--red)}
.hero-p{font-size:17px;color:var(--muted);line-height:1.75;margin-bottom:36px;max-width:520px}
.btns{display:flex;gap:14px;flex-wrap:wrap}
.btn-p{background:var(--red);color:#fff;padding:14px 28px;border:none;font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:all .2s;border-radius:4px;display:inline-block}
.btn-p:hover{background:var(--red2)}
.btn-o{background:transparent;color:var(--black);padding:14px 28px;border:2px solid var(--black);font-family:var(--sans);font-weight:700;font-size:14px;letter-spacing:1px;text-transform:uppercase;cursor:pointer;text-decoration:none;transition:all .2s;border-radius:4px;display:inline-block}
.btn-o:hover{background:var(--black);color:#fff}
.pills{display:flex;flex-wrap:wrap;gap:8px;margin-top:28px}
.pill{border:1px solid var(--red);color:var(--red);padding:4px 12px;font-family:var(--mono);font-size:11px;border-radius:2px}
.terminal{background:#0a0a0a;border-radius:8px;overflow:hidden;font-family:var(--mono);font-size:13px;box-shadow:8px 8px 0 var(--red)}
.term-bar{background:#1a1a1a;padding:12px 16px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #333}
.dot{width:10px;height:10px;border-radius:50%}.dr{background:#ff5f56}.dy{background:#ffbd2e}.dg{background:#27c93f}
.tlbl{margin-left:auto;font-size:10px;color:#666;letter-spacing:2px;text-transform:uppercase}
.term-body{padding:24px;line-height:2.2;color:#ccc}
.tc{color:#555}.tk{color:#79b8ff}.tv{color:#f0c674}.ts{color:#9ecbff}.tb{color:#ff3b5c;font-weight:700}
</style>
</head>
<body>
<nav>
  <div class="logo">AI<span>Leash</span></div>
</nav>

<section class="hero">
  <div class="hero-inner">
    <div>
      <div class="eyebrow">EU AI Act — Enforcement August 2026</div>
      <h1>AI Governance<br><span class="red">Infrastructure</span></h1>
      <p class="hero-p">AILeash is a real-time AI action governance engine.</p>
    </div>

    <div class="terminal">
      <div class="term-bar">
        <div class="dot dr"></div><div class="dot dy"></div><div class="dot dg"></div>
        <div class="tlbl">AILeash v3.0</div>
      </div>
      <div class="term-body">
        <div class="tc">// engine online</div>
      </div>
    </div>

  </div>
</section>
</body>
</html>
"""

# -----------------------------
# HTTP HANDLER
# -----------------------------
class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self.send_html(LANDING)
        elif self.path == "/health":
            self.send_json({"ok": True, "version": VERSION})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/govern":
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            result = govern(data)
            self.send_json(result)
        else:
            self.send_json({"error": "not found"}, 404)

    def send_json(self, obj, status=200):
        b = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def send_html(self, html):
        b = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers()
        self.wfile.write(b)

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    print("AILeash running:", PORT)
    HTTPServer(("", PORT), Handler).serve_forever()
