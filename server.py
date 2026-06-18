import json, math, time, sqlite3, hashlib, threading
import urllib.request, urllib.parse, os, secrets, smtplib
from email.mime.text import MIMEText
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

STRIPE_SECRET  = os.environ.get("STRIPE_SECRET", "")
BREVO_API_KEY  = os.environ.get("BREVO_API_KEY", "")
PORT           = int(os.environ.get("PORT", 8080))
DB             = "aileash.db"
VERSION        = "4.1.0"
HOST           = os.environ.get("HOST", "https://sebbi.pro")
SAFE_COUNTRIES = {"UK","US","DE","FR","CA","AU","NL","SE","NO","DK","FI","IE","NZ"}
REQUIRED_FIELDS= {"user_id","action","amount","country","device_id","anomaly","device_risk"}
FREE_QUOTA     = 100

RATE_LIMIT_PER_MIN  = 60
RATE_LIMIT_PER_HOUR = 1000
GLOBAL_RATE_PER_SEC = 200

OWNER_NAME  = "Justin Antony Dobson"
OWNER_TITLE = "Owner, Monop Content"
OWNER_EMAIL = "justin@monopcontent.com"
OWNER_PHONE = "07908 269428"

STRIPE_PRICE_ID_AILEASH  = ""
STRIPE_PRICE_ID_GUARDIAN = ""
_db_lock  = threading.Lock()
_load_lock= threading.Lock()
_req_times= deque()
_load_warn= False
_key_windows = defaultdict(lambda: {"min": deque(), "hour": deque()})
_key_lock = threading.Lock()

# ============================================================================
# DATABASE
# ============================================================================
def get_conn():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, trust REAL DEFAULT 0.5, last_country TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, user_id TEXT,
        event_json TEXT, result_json TEXT, prev_hash TEXT, audit_hash TEXT UNIQUE)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        key TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT, org TEXT,
        org_type TEXT, product TEXT DEFAULT 'aileash', devices INTEGER DEFAULT 1,
        stripe_customer TEXT, stripe_sub TEXT, actions_used INTEGER DEFAULT 0,
        created REAL, active INTEGER DEFAULT 1, is_paid INTEGER DEFAULT 0,
        free_quota INTEGER DEFAULT 100, plan_type TEXT DEFAULT 'free')""")
    conn.execute("""CREATE TABLE IF NOT EXISTS config (k TEXT PRIMARY KEY, v TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS load_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, rps REAL, note TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS contact_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, name TEXT,
        email TEXT, phone TEXT, org TEXT, message TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key_email ON api_keys(email)")
    conn.commit()
    return conn

_conn = get_conn()

# ============================================================================
# LOAD TRACKING
# ============================================================================
def track_request():
    global _load_warn
    t = time.time()
    with _load_lock:
        _req_times.append(t)
        cutoff = t - 1.0
        while _req_times and _req_times[0] < cutoff:
            _req_times.popleft()
        rps = len(_req_times)
        if rps > GLOBAL_RATE_PER_SEC and not _load_warn:
            _load_warn = True
            try:
                _conn.execute("INSERT INTO load_log(ts,rps,note) VALUES(?,?,?)", (t,rps,"THROTTLE_ENGAGED"))
                _conn.commit()
            except Exception: pass
            print(f"LOAD WARNING: {rps} req/s", flush=True)
        elif rps < GLOBAL_RATE_PER_SEC * 0.7 and _load_warn:
            _load_warn = False
            print(f"LOAD CLEAR: {rps} req/s", flush=True)
        return rps

def is_overloaded():
    with _load_lock: return _load_warn

def get_rps():
    t = time.time()
    with _load_lock: return sum(1 for x in _req_times if x >= t - 1.0)

# ============================================================================
# RATE LIMITING
# ============================================================================
def check_rate_limit(key):
    t = time.time()
    with _key_lock:
        w = _key_windows[key]
        while w["min"]  and w["min"][0]  < t - 60:   w["min"].popleft()
        while w["hour"] and w["hour"][0] < t - 3600: w["hour"].popleft()
        if len(w["min"])  >= RATE_LIMIT_PER_MIN:
            return False, "rate_limit_minute", f"Max {RATE_LIMIT_PER_MIN} requests/minute."
        if len(w["hour"]) >= RATE_LIMIT_PER_HOUR:
            return False, "rate_limit_hour", f"Max {RATE_LIMIT_PER_HOUR} requests/hour."
        w["min"].append(t); w["hour"].append(t)
        return True, None, None

# ============================================================================
# EMAIL — BREVO / SMTP / FILE FALLBACK
# ============================================================================
def send_email(to_email, to_name, subject, html_body):
    """Send an email using Brevo (preferred), then SMTP if configured, otherwise save to disk as a fallback.
    Returns True on success, False on failure. Logs actions with EMAIL SENT / EMAIL SAVED / EMAIL ERROR messages.
    """
    # Prefer Brevo if API key is present
    if BREVO_API_KEY:
        payload = json.dumps({
            "sender":   {"name": "AILeash Platform", "email": "noreply@monopcontent.com"},
            "to":       [{"email": to_email, "name": to_name}],
            "subject":  subject,
            "htmlContent": html_body
        }).encode()
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=payload,
            headers={
                "api-key":      BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept":       "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                print(f"EMAIL SENT: {to_email}", flush=True)
                return True
        except Exception as e:
            print(f"EMAIL ERROR (brevo): {e}", flush=True)
            # fall through to SMTP/file fallback

    # Try SMTP if configured
    SMTP_HOST = os.environ.get('SMTP_HOST','').strip()
    if SMTP_HOST:
        try:
            SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
            SMTP_USER = os.environ.get('SMTP_USER', '')
            SMTP_PASS = os.environ.get('SMTP_PASS', '')
            SMTP_FROM = os.environ.get('SMTP_FROM', 'noreply@monopcontent.com')
            msg = MIMEText(html_body, 'html')
            msg['Subject'] = subject
            msg['From'] = SMTP_FROM
            msg['To'] = to_email
            s = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            try:
                s.starttls()
            except Exception:
                pass
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(SMTP_FROM, [to_email], msg.as_string())
            s.quit()
            print(f"EMAIL SENT: {to_email}", flush=True)
            return True
        except Exception as e:
            print(f"EMAIL ERROR (smtp): {e}", flush=True)
            # fall through to file fallback

    # File fallback: save rendered HTML to disk so emails are inspectable
    EMAIL_LOG_DIR = os.environ.get('EMAIL_LOG_DIR', './emails')
    try:
        os.makedirs(EMAIL_LOG_DIR, exist_ok=True)
        safe_email = to_email.replace('@', '_at_').replace('/', '_')
        fname = f"welcome-{int(time.time())}-{safe_email}.html"
        path = os.path.join(EMAIL_LOG_DIR, fname)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(html_body)
        print(f"EMAIL SAVED: {path}", flush=True)
        return True
    except Exception as e:
        print(f"EMAIL ERROR (file): {e}", flush=True)
        return False


def send_welcome_email(name, email, product, api_key, devices, monthly):
    product_name = "AILeash Guardian" if product == "guardian" else "AILeash"
    endpoint     = f"{HOST}/api/govern"
    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><style>
body{{font-family:'DM Sans',Arial,sans-serif;background:#f5f7fa;margin:0;padding:0}}
.wrap{{max-width:580px;margin:40px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08)}}
.hdr{{background:#0a0f1e;padding:32px 36px;border-bottom:4px solid #c9a84c}}
.hdr-logo{{font-size:22px;color:#fff;font-weight:900;letter-spacing:1px}}.hdr-logo span{{color:#c9a84c}}
.hdr-sub{{font-size:12px;color:rgba(255,255,255,0.4);margin-top:4px;font-family:monospace;letter-spacing:2px;text-transform:uppercase}}
.body{{padding:36px}}
.greeting{{font-size:20px;font-weight:700;color:#0a0f1e;margin-bottom:8px}}
.intro{{font-size:14px;color:#64748b;line-height:1.7;margin-bottom:28px}}
.key-box{{background:#0a0f1e;border-radius:6px;padding:20px;margin-bottom:24px}}
.key-lbl{{font-family:monospace;font-size:10px;color:#c9a84c;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px}}
.key-val{{font-family:monospace;font-size:12px;color:#00ff88;word-break:break-all;line-height:1.6}}
.billing{{background:#f5f7fa;border:1px solid #e2e8f0;border-radius:6px;padding:16px;margin-bottom:24px;font-size:13px;color:#64748b;line-height:1.7}}
.billing strong{{color:#0a0f1e}}
.code-box{{background:#0a0f1e;border-radius:6px;padding:20px;margin-bottom:24px}}
.code-lbl{{font-family:monospace;font-size:10px;color:rgba(255,255,255,0.3);letter-spacing:2px;text-transform:uppercase;margin-bottom:10px}}
.code{{font-family:monospace;font-size:12px;color:#ccc;line-height:2}}
.code em{{color:#79b8ff;font-style:normal}}
.code .gr{{color:#00ff88}}
.footer-txt{{font-size:12px;color:#94a3b8;text-align:center;margin-top:28px;line-height:1.7}}
.footer-txt a{{color:#c9a84c;text-decoration:none}}
</style></head>
<body>
<div class="wrap">
  <div class="hdr">
    <div class="hdr-logo">AILeash <span>Platform</span></div>
    <div class="hdr-sub">{product_name} &mdash; Key Created</div>
  </div>
  <div class="body">
    <div class="greeting">Welcome{', ' + name.split()[0] if name.strip() else ''}.</div>
    <p class="intro">Your {product_name} API key is ready. You have 100 free decisions to start &mdash; no card required. After your trial, billing is &pound;{monthly:.2f}/month for {devices} dev[...]</p>
    <div class="key-box">
      <div class="key-lbl">Your API Key &mdash; Save This Now</div>
      <div class="key-val">{api_key}</div>
    </div>
    <div class="billing">
      <strong>Billing summary</strong><br>
      Product: {product_name}<br>
      Devices: {devices}<br>
      Monthly total: &pound;{monthly:.2f}<br>
      Free decisions remaining: 100
    </div>
    <div class="code-box">
      <div class="code-lbl">Quick Start &mdash; curl</div>
      <div class="code">
        <em>POST</em> {endpoint}<br>
        Authorization: Bearer <em>{api_key[:20]}...</em><br>
        Content-Type: application/json<br><br>
        <span class="gr">Response: ALLOW / CHALLENGE / BLOCK</span><br>
        + SHA-256 audit hash on every decision
      </div>
    </div>
    <p class="intro" style="margin-bottom:8px">Questions? Reply to this email or contact us directly:</p>
    <p class="intro"><strong>{OWNER_NAME}</strong> &mdash; {OWNER_TITLE}<br>
    <a href="mailto:{OWNER_EMAIL}" style="color:#c9a84c">{OWNER_EMAIL}</a> &mdash; {OWNER_PHONE}</p>
  </div>
  <div class="footer-txt">
    &copy; 2026 Monop Content &middot; Blyth, UK<br>
    <a href="{HOST}">sebbi.pro</a> &mdash; EU AI Act &middot; Online Safety Act &middot; ICO Children's Code
  </div>
</div>
</body></html>"""
    send_email(email, name, f"Your {product_name} API Key", html)

def send_contact_notification(name, email, phone, org, message):
    html = f"""
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;padding:20px;color:#333">
<h2 style="color:#0a0f1e">New Contact Form Submission</h2>
<p><strong>Name:</strong> {name}</p>
<p><strong>Email:</strong> {email}</p>
<p><strong>Phone:</strong> {phone}</p>
<p><strong>Organisation:</strong> {org}</p>
<p><strong>Message:</strong><br>{message}</p>
<hr><p style="color:#999;font-size:12px">AILeash Platform &mdash; sebbi.pro</p>
</body></html>"""
    send_email(OWNER_EMAIL, OWNER_NAME, f"New Contact: {name}", html)

# ============================================================================
# STRIPE
# ============================================================================
def stripe_call(method, endpoint, data=None):
    if not STRIPE_SECRET: return None
    url  = "https://api.stripe.com/v1" + endpoint
    hdrs = {"Authorization": "Bearer " + STRIPE_SECRET, "Content-Type": "application/x-www-form-urlencoded"}
    body = urllib.parse.urlencode(data).encode() if data else None
    req  = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:    return json.loads(e.read())
        except: return None
    except Exception as e:
        print(f"Stripe error: {e}", flush=True); return None

# ... rest of server.py unchanged ...
