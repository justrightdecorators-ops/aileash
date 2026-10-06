"""
modules/autopilot.py  v1.0.0  -  follows up everyone who comes in, on its own

    Arm:     https://sebbi.pro/x/arm/status
    Admin:   https://sebbi.pro/admin   (Monitor tab -> Autopilot)

Every 30 minutes it looks at who signed up, what they have done, and where
they are in their trial, and sends the one email that moves them on:

  welcome     AI-opened accounts (the MCP connector sends no email itself):
              their key and the one line to change
  day 3       signed up, not one decision yet: the 2-minute setup, or the pilot
  day 7       using it: a Forever Proof of one of their own decisions
  trial -7    seven days left: keep going for 50p a device, with their figure
  trial -1    last day
  trial end   trial over: their chain is safe, one tap to carry on
  pilot +1h   opened the £495 checkout and did not pay
  pilot +24h  second and last reminder

Only people who signed up or started a checkout are ever emailed. Every email
carries an unsubscribe link (and the one-click unsubscribe header mail apps
show), names a real reply address, and includes the customer's own referral
code. Each step goes to each person once, ever. At most one email per person
in 36 hours (pilot reminders apart), 40 per run, 150 a day.

The payment link in trial emails never goes stale: it opens a page here that
makes a fresh Stripe checkout for the real device count at the moment it is
tapped.

Switch: pause and resume from the admin Monitor, or set AUTOPILOT=0 on
Railway. AUTOPILOT_DRY=1 records what it would send without sending.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

VERSION = "1.0.0"
SITE = "https://sebbi.pro"
PUBLIC = {("GET", "status"), ("GET", "queue"), ("GET", "log"), ("POST", "pause"), ("POST", "resume"), ("POST", "run"),
          ("GET", "")}
TRIAL_DAYS = 90
INTERVAL = int(os.environ.get("AUTOPILOT_INTERVAL", "1800"))
PER_RUN = int(os.environ.get("AUTOPILOT_PER_RUN", "40"))
PER_DAY = int(os.environ.get("AUTOPILOT_PER_DAY", "150"))
GAP = 36 * 3600
BREVO = os.environ.get("AUTOPILOT_BREVO_BASE", "https://api.brevo.com/v3").rstrip("/")
SENDER = {"name": "sebbi.pro", "email": "justrightdecorators@gmail.com"}
REPLY_TO = {"name": "Monop Content", "email": "justrightdecorators@gmail.com"}
SKIP_DOMAIN = re.compile(r"@(example\.(com|org|net)|[^@]*\.(test|invalid|example|localhost))$", re.I)
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")

_state = {"ready": False, "worker": False, "paused": os.environ.get("AUTOPILOT", "1") == "0", "runs": 0,
          "sent_since_start": 0, "last_run": None, "last_result": None, "last_error": None, "pages": False}
_lock = threading.Lock()
_run_lock = threading.Lock()
_EPHEMERAL = secrets.token_bytes(32)


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _secret():
    s = os.environ.get("LICENCE_SECRET") or ""
    return s.encode() if s else _EPHEMERAL


def _iso(ts):
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def _db(sql, args=(), one=False, write=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        if write:
            s._conn.commit()
            return cur.lastrowid
        return cur.fetchone() if one else cur.fetchall()


def _safe(sql, args=()):
    try:
        return _db(sql, args)
    except Exception:
        return []


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS autopilot_sent(email TEXT, step TEXT, ref TEXT, at REAL, status TEXT,"
                  "subject TEXT, PRIMARY KEY(email, step, ref))")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ap_at ON autopilot_sent(at)")
        c.execute("CREATE TABLE IF NOT EXISTS autopilot_optout(email TEXT PRIMARY KEY, at REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS autopilot_link(token TEXT PRIMARY KEY, api_key TEXT, created REAL)")
        c.execute("CREATE TABLE IF NOT EXISTS autopilot_meta(k TEXT PRIMARY KEY, v TEXT)")
        c.commit()
    r = _db("SELECT v FROM autopilot_meta WHERE k='paused'", one=True)
    if r is not None and os.environ.get("AUTOPILOT", "1") != "0":
        _state["paused"] = r[0] == "1"


def _set_paused(p):
    _state["paused"] = p
    _db("INSERT OR REPLACE INTO autopilot_meta(k,v) VALUES('paused',?)", ("1" if p else "0",), write=True)


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

def _unsub_token(email):
    return hmac.new(_secret(), ("unsub|" + email.lower()).encode(), hashlib.sha256).hexdigest()[:24]


def unsubscribe_url(email):
    return "%s/unsubscribe?e=%s&t=%s" % (SITE, urllib.parse.quote(email), _unsub_token(email))


def continue_url(api_key):
    r = _db("SELECT token FROM autopilot_link WHERE api_key=?", (api_key,), one=True)
    if r:
        tok = r[0]
    else:
        tok = secrets.token_urlsafe(18)
        _db("INSERT INTO autopilot_link(token,api_key,created) VALUES(?,?,?)", (tok, api_key, time.time()), write=True)
    return "%s/continue?t=%s" % (SITE, tok)


def _referral(key, email, name):
    r = _db("SELECT code FROM referrals WHERE referrer_key=? ORDER BY created LIMIT 1", (key,), one=True)
    if r:
        return r[0]
    try:
        return _srv().create_referral(key, email, name or email.split("@")[0])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# the emails
# ---------------------------------------------------------------------------

def _esc(t):
    return str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap(preheader, heading, paras, cta=None, after=None, email="", ref=None):
    btn = ""
    if cta:
        btn = ('<tr><td style="padding:8px 0 22px"><a href="%s" style="display:inline-block;background:#c9a84c;color:#0a0f1e;'
               'text-decoration:none;font-weight:700;font-size:16px;padding:14px 22px;border-radius:8px">%s</a></td></tr>'
               % (_esc(cta[1]), _esc(cta[0])))
    body = "".join('<p style="margin:0 0 14px;font-size:16px;line-height:1.6;color:#2b2f3a">%s</p>' % p for p in paras)
    tail = "".join('<p style="margin:0 0 12px;font-size:14px;line-height:1.6;color:#555b6b">%s</p>' % p for p in (after or []))
    refline = ""
    if ref:
        refline = ('<p style="margin:0 0 10px;font-size:13px;color:#6b7180">Know someone who should be using this? Your referral '
                   'code is <b style="color:#0a0f1e;font-family:monospace">%s</b> &mdash; they enter it when they sign up and you\'re '
                   'credited for every device they bring.</p>' % _esc(ref))
    return ('<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f3f4f7">'
            '<span style="display:none;max-height:0;overflow:hidden;opacity:0">%s</span>'
            '<table width="100%%" cellpadding="0" cellspacing="0" style="background:#f3f4f7;padding:22px 10px"><tr><td align="center">'
            '<table width="100%%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif">'
            '<tr><td style="background:#0a0f1e;padding:22px 26px;border-bottom:3px solid #c9a84c">'
            '<span style="font-family:Georgia,serif;font-size:24px;color:#ffffff;font-weight:700">sebbi<span style="color:#c9a84c">.pro</span></span></td></tr>'
            '<tr><td style="padding:28px 26px 8px"><h1 style="margin:0 0 16px;font-family:Georgia,serif;font-weight:600;font-size:25px;line-height:1.25;color:#0a0f1e">%s</h1>'
            '%s<table cellpadding="0" cellspacing="0">%s</table>%s</td></tr>'
            '<tr><td style="padding:16px 26px 24px;border-top:1px solid #eceef3">%s'
            '<p style="margin:0;font-size:12px;color:#8a8f9c;line-height:1.6">Monop Content &middot; sebbi.pro &middot; Just reply to this email to reach us.<br>'
            'You\'re getting this because you signed up at sebbi.pro. <a href="%s" style="color:#8a8f9c">Unsubscribe</a></p>'
            '</td></tr></table></td></tr></table></body></html>'
            % (_esc(preheader), heading, body, btn, tail, refline, _esc(unsubscribe_url(email))))


def _text(heading, paras, cta=None, after=None, email="", ref=None):
    strip = lambda h: re.sub(r"<[^>]+>", "", h).replace("&amp;", "&").replace("&mdash;", "-").replace("&pound;", "£").replace("&rsquo;", "'")
    out = [strip(heading), ""] + [strip(p) for p in paras]
    if cta:
        out += ["", "%s: %s" % (cta[0], cta[1])]
    out += [""] + [strip(p) for p in (after or [])]
    if ref:
        out += ["", "Your referral code: %s" % ref]
    out += ["", "Monop Content · sebbi.pro · reply to reach us", "Unsubscribe: %s" % unsubscribe_url(email)]
    return "\n".join(out)


def compose(step, c):
    """Build (subject, html, text) for one step and one customer dict."""
    first = _esc((c.get("name") or "").split()[0]) if c.get("name") else ""
    hi = ("%s, " % first) if first else ""
    E, R = c["email"], c.get("ref")
    if step == "welcome":
        subject = "You're live on sebbi.pro — your key inside"
        head = "You're set up%s." % ((", " + first) if first else "")
        paras = ["Your AI assistant opened your sebbi.pro account. Here's everything in one place.",
                 "<b>Your API key</b> (keep it secret):<br><code style=\"font-size:13px;background:#f3f4f7;padding:6px 8px;border-radius:5px;display:inline-block;word-break:break-all\">%s</code>" % _esc(c["key"]),
                 "<b>The one line to change:</b> point your app's OpenAI or Anthropic base URL at your private sebbi.pro gateway. Every AI call is then scored, sealed and provable against Bitcoin."]
        cta = ("Get your gateway URL", SITE + "/gateway")
        after = ["Rather we did it all for you? <a href=\"%s/pilot\" style=\"color:#8a6f2a\">Governed in 7 days — £495</a>, live in 7 days or your money back." % SITE]
    elif step == "day3":
        subject = "Two minutes to your first sealed AI decision"
        head = "%sone line and you're governed." % (hi.capitalize() if hi else "")
        head = head[0].upper() + head[1:]
        paras = ["You signed up for sebbi.pro a few days ago but haven't sealed a decision yet. Here's the quickest way in:",
                 "1. Get your private gateway URL.<br>2. Paste it as the base URL in your OpenAI or Anthropic code.<br>3. Run your app as normal. Every call is now scored, sealed and written into Bitcoin.",
                 "No SDK, no project. Your provider key stays in your app."]
        cta = ("Do it now — 2 minutes", SITE + "/gateway")
        after = ["Building with Lovable, Zapier, Python or something else? Every stack is covered at <a href=\"%s/connect\" style=\"color:#8a6f2a\">sebbi.pro/connect</a>." % SITE,
                 "Or let us set it up with you: <a href=\"%s/pilot\" style=\"color:#8a6f2a\">governed in 7 days — £495</a>." % SITE]
    elif step == "day7":
        n = int(c.get("decisions") or 0)
        subject = "%s decision%s sealed — check one against Bitcoin" % ("{:,}".format(n), "" if n == 1 else "s")
        head = "Your AI decisions are now provable."
        paras = ["%syou've sealed <b>%s</b> decision%s on sebbi.pro. Each one is chained, witnessed and written into Bitcoin every hour." % (hi.capitalize() if hi else "", "{:,}".format(n), "" if n == 1 else "s"),
                 "Here's the part your customers, auditors and regulators will love: anyone can check one of your decisions against Bitcoin, in their own browser, without trusting you or us."]
        cta = ("Check your latest decision", "%s/forever?block=%s" % (SITE, c.get("last_block") or ""))
        after = ["Send that link to anyone who asks how you govern your AI."]
    elif step in ("trial7", "trial1", "trialend"):
        devs = max(1, int(c.get("devices") or 0))
        cost = "£%.2f" % (devs * 0.5)
        link = c.get("continue_url") or SITE
        if step == "trial7":
            dl = max(2, int(c.get("days_left") or 7))
            subject = "%d days left on your sebbi.pro trial" % dl
            head = "%d days left — keep every decision provable." % dl
            paras = ["%syour free trial ends in %d days. Everything you've sealed stays in your chain and in Bitcoin, whatever you decide." % (hi.capitalize() if hi else "", dl),
                     "To carry on it's 50p per device a month. You're on <b>%d device%s</b>, so that's <b>%s a month</b>. No contract, cancel any time." % (devs, "" if devs == 1 else "s", cost)]
            cta = ("Keep going — %s a month" % cost, link)
        elif step == "trial1":
            subject = "Your sebbi.pro trial ends tomorrow"
            head = "Last day of your free trial."
            paras = ["%syour trial ends tomorrow. After that, new decisions stop being sealed until a card is added." % (hi.capitalize() if hi else ""),
                     "%d device%s at 50p each — <b>%s a month</b>." % (devs, "" if devs == 1 else "s", cost)]
            cta = ("Add a card — 30 seconds", link)
        else:
            subject = "Your trial has ended — your chain is safe"
            head = "Your trial has ended. Nothing is lost."
            paras = ["%syour free trial is over. Every decision you sealed is still in your chain and still provable against Bitcoin." % (hi.capitalize() if hi else ""),
                     "Pick up exactly where you left off for <b>%s a month</b> (%d device%s at 50p)." % (cost, devs, "" if devs == 1 else "s")]
            cta = ("Carry on", link)
        after = ["Questions? Just reply — a person reads every email."]
    elif step in ("pilot1h", "pilot24h"):
        co = _esc(c.get("company") or "your business")
        if step == "pilot1h":
            subject = "Your pilot is one step away"
            head = "%sgoverned in 7 days is one step away." % (hi.capitalize() if hi else "")
            head = head[0].upper() + head[1:]
            paras = ["You started the sebbi.pro pilot for %s but didn't finish checking out. No problem — it takes a minute." % co,
                     "The moment you pay, your API key and gateway are live. Within 7 days: a setup call, rules for your business and a regulator-ready evidence file. Live in 7 days or your money back."]
            cta = ("Finish — £495", SITE + "/pilot")
        else:
            subject = "Still want your AI governed this week?"
            head = "Still want it done this week?"
            paras = ["Yesterday you started the pilot for %s. If now's not the time, no hard feelings — this is the last reminder." % co,
                     "If it is: every AI decision scored, sealed and provable against Bitcoin, set up with you, in 7 days or your money back."]
            cta = ("Start the pilot", SITE + "/pilot")
        after = ["Want to talk it through first? Just reply."]
        R = None
    else:
        raise ValueError(step)
    preheader = re.sub(r"<[^>]+>", "", paras[0])[:110]
    return subject, _wrap(preheader, head, paras, cta, after, E, R), _text(head, paras, cta, after, E, R)


# ---------------------------------------------------------------------------
# who is due
# ---------------------------------------------------------------------------

def _excluded(email):
    s = _srv()
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or SKIP_DOMAIN.search(e):
        return True
    if e == str(getattr(s, "OWNER_EMAIL", "")).lower():
        return True
    return False


def due(now=None, include_test_domains=False):
    now = now or time.time()
    out = []
    optout = {r[0] for r in _safe("SELECT email FROM autopilot_optout")}
    sent = {(r[0], r[1], r[2]) for r in _safe("SELECT email, step, ref FROM autopilot_sent")}
    ai_fps = {r[0] for r in _safe("SELECT email_fp FROM mcp_agreement")}
    pilot_keys = {r[0] for r in _safe("SELECT api_key FROM pilot_order WHERE status='paid'")}
    dec = {}
    for k, n, last in _safe("SELECT api_key, COUNT(*), MAX(id) FROM audit_log WHERE api_key IS NOT NULL AND api_key!='' GROUP BY api_key"):
        dec[k] = (n, last)
    devs = dict(_safe("SELECT api_key, COUNT(*) FROM device_seen GROUP BY api_key"))

    def add(step, ref, c):
        e = c["email"].strip().lower()
        if e in optout or (e, step, ref) in sent:
            return
        if not include_test_domains and _excluded(e):
            return
        c = dict(c, email=e)
        out.append((step, ref, c))

    for key, email, name, org, product, created, paid, active in _safe(
            "SELECT key,email,name,org,product,created,is_paid,active FROM api_keys"):
        if not email or not active:
            continue
        created = created or now
        age = now - created
        n, last = dec.get(key, (0, None))
        c = {"key": key, "email": email, "name": name or "", "org": org or "", "product": product or "aileash",
             "decisions": n, "last_block": last, "devices": devs.get(key, 0)}
        efp = hashlib.sha256(email.strip().lower().encode()).hexdigest()
        if efp in ai_fps and age < 2 * 86400 and key not in pilot_keys:
            add("welcome", key[-12:], c)
        if not paid and n == 0 and 3 * 86400 <= age < 10 * 86400:
            add("day3", key[-12:], c)
        if n > 0 and 7 * 86400 <= age < 14 * 86400:
            add("day7", key[-12:], c)
        if not paid:
            left = created + TRIAL_DAYS * 86400 - now
            c["days_left"] = int(left // 86400) + (1 if left % 86400 else 0)
            if 0 < left <= 7 * 86400 and left > 2 * 86400:
                add("trial7", key[-12:], c)
            elif 0 < left <= 1.5 * 86400:
                add("trial1", key[-12:], c)
            elif -3 * 86400 < left <= 0:
                add("trialend", key[-12:], c)
    for sid, created, name, email, company, status in _safe(
            "SELECT session_id, created, name, email, company, status FROM pilot_order WHERE status!='paid'"):
        if not email:
            continue
        paid_since = _safe("SELECT 1 FROM pilot_order WHERE email=? AND status='paid' AND created>=?", (email, created))
        if paid_since:
            continue
        age = now - (created or now)
        c = {"email": email, "name": name or "", "company": company or ""}
        if 3600 <= age < 20 * 3600:
            add("pilot1h", sid[-16:], c)
        elif 24 * 3600 <= age < 72 * 3600:
            add("pilot24h", sid[-16:], c)
    return out


# ---------------------------------------------------------------------------
# sending
# ---------------------------------------------------------------------------

def _brevo(to_email, to_name, subject, html, text, step):
    key = os.environ.get("BREVO_API_KEY", "").strip()
    if not key:
        return "no_email_key"
    payload = {"sender": SENDER, "replyTo": REPLY_TO, "to": [{"email": to_email, "name": to_name or to_email}],
               "subject": subject, "htmlContent": html, "textContent": text, "tags": ["autopilot", step],
               "headers": {"List-Unsubscribe": "<%s>" % unsubscribe_url(to_email),
                           "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}}
    try:
        req = urllib.request.Request(BREVO + "/smtp/email", data=json.dumps(payload).encode(), method="POST",
                                     headers={"api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return "sent" if 200 <= r.status < 300 else "error_%d" % r.status
    except urllib.error.HTTPError as e:
        return "error_%d" % e.code
    except Exception as e:
        return "error_%s" % type(e).__name__


def run_once(force=False, include_test_domains=False):
    if not _run_lock.acquire(blocking=False):
        return {"busy": True}
    try:
        if _state["paused"] and not force:
            return {"paused": True}
        now = time.time()
        dry = os.environ.get("AUTOPILOT_DRY", "0") == "1"
        today = now - (now % 86400)
        sent_today = _db("SELECT COUNT(*) FROM autopilot_sent WHERE at>=? AND status='sent'", (today,), one=True)[0]
        recent = {r[0]: r[1] for r in _safe("SELECT email, MAX(at) FROM autopilot_sent WHERE status='sent' GROUP BY email")}
        result = {"due": 0, "sent": 0, "dry": 0, "held": 0, "errors": 0, "steps": {}}
        items = due(now, include_test_domains)
        result["due"] = len(items)
        order = {"pilot1h": 0, "pilot24h": 1, "trial1": 2, "trialend": 3, "trial7": 4, "welcome": 5, "day3": 6, "day7": 7}
        items.sort(key=lambda x: order.get(x[0], 9))
        done_this_run = set()
        for step, ref, c in items:
            if result["sent"] + result["dry"] >= PER_RUN or sent_today + result["sent"] >= PER_DAY:
                break
            e = c["email"]
            if not step.startswith("pilot") and (e in done_this_run or (recent.get(e) and now - recent[e] < GAP)):
                result["held"] += 1
                continue
            if step.startswith("trial"):
                c["continue_url"] = continue_url(c["key"])
            if "key" in c:
                c["ref"] = _referral(c["key"], e, c.get("name"))
            subject, html, text = compose(step, c)
            status = "dry" if dry else _brevo(e, c.get("name"), subject, html, text, step)
            if status == "no_email_key":
                result["errors"] += 1
                _state["last_error"] = "BREVO_API_KEY is not set, so nothing can be emailed"
                break
            if status in ("sent", "dry"):
                _db("INSERT OR IGNORE INTO autopilot_sent(email,step,ref,at,status,subject) VALUES(?,?,?,?,?,?)",
                    (e, step, ref, now, status, subject), write=True)
                done_this_run.add(e)
                result["sent" if status == "sent" else "dry"] += 1
                result["steps"][step] = result["steps"].get(step, 0) + 1
            else:
                result["errors"] += 1
                _state["last_error"] = "send %s: %s" % (step, status)
        _state["runs"] += 1
        _state["sent_since_start"] += result["sent"]
        _state["last_run"] = _iso(now)
        _state["last_result"] = result
        return result
    except Exception as e:
        _state["last_error"] = "run: %s" % str(e)[:150]
        return {"error": str(e)[:150]}
    finally:
        _run_lock.release()


def _worker():
    time.sleep(int(os.environ.get("AUTOPILOT_FIRST_DELAY", "600")))
    while True:
        try:
            run_once()
        except Exception as e:
            _state["last_error"] = "worker: %s" % str(e)[:120]
        time.sleep(INTERVAL)


# ---------------------------------------------------------------------------
# pages: unsubscribe, and the payment link that never goes stale
# ---------------------------------------------------------------------------

def _page(title, heading, body, status=200):
    return ('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta name="robots" content="noindex"><title>%s — sebbi.pro</title><style>body{margin:0;background:#0a0f1e;color:#fff;'
            'font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif}.w{max-width:520px;margin:12vh auto;padding:0 18px}'
            '.b{font-family:Georgia,serif;font-size:22px}.b span{color:#c9a84c}h1{font-family:Georgia,serif;font-weight:600;font-size:30px;'
            'margin:28px 0 12px}p{color:rgba(255,255,255,.7);line-height:1.6}a{color:#f0d78a}</style></head><body><div class="w">'
            '<div class="b">sebbi<span>.pro</span></div><h1>%s</h1>%s</div></body></html>' % (_esc(title), heading, body)), status


def _send(h, page):
    body, status = page
    raw = body.encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(raw)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(raw)


def _redirect(h, url):
    h.send_response(302)
    h.send_header("Location", url)
    h.send_header("Content-Length", "0")
    h.send_header("Cache-Control", "no-store")
    h.end_headers()


def _unsubscribe(q):
    e = (q.get("e") or [""])[0].strip().lower()
    t = (q.get("t") or [""])[0]
    if not e or not hmac.compare_digest(t, _unsub_token(e)):
        return _page("Unsubscribe", "That link didn't work.", "<p>Reply to any of our emails and we'll take you off by hand.</p>", 400)
    _db("INSERT OR IGNORE INTO autopilot_optout(email,at) VALUES(?,?)", (e, time.time()), write=True)
    return _page("Unsubscribed", "You're unsubscribed.",
                 "<p>We won't send you follow-up emails again. Your account, key and sealed decisions are untouched.</p>"
                 "<p><a href=\"%s\">Back to sebbi.pro</a></p>" % SITE)


def _continue(h, q):
    t = (q.get("t") or [""])[0]
    r = _db("SELECT api_key FROM autopilot_link WHERE token=?", (t,), one=True) if t else None
    if not r:
        return _send(h, _page("Continue", "That link has expired.", "<p>Reply to our email, or sign in again at <a href=\"%s\">sebbi.pro</a>.</p>" % SITE, 404))
    s = _srv()
    ki = s.get_key(r[0])
    if not ki:
        return _send(h, _page("Continue", "We couldn't find that account.", "<p>Reply to our email and we'll sort it.</p>", 404))
    if ki[3]:
        return _send(h, _page("All set", "You're already paying — thank you.", "<p>Nothing else to do. Every decision keeps sealing.</p>"))
    url = None
    try:
        url = s.trial_checkout(r[0], ki[0], ki[6] or "aileash")
    except Exception as e:
        _state["last_error"] = "continue: %s" % str(e)[:120]
    if url and url.startswith("https://checkout.stripe.com"):
        return _redirect(h, url)
    return _send(h, _page("Continue", "Card payments are briefly unavailable.", "<p>Reply to our email and we'll send a payment link by hand.</p>", 503))


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_autopilot_pages", False):
        _state["pages"] = True
        return True
    orig_get, orig_post = H.do_GET, H.do_POST

    def do_GET(self):
        p, _, q = (self.path or "").partition("?")
        p = p.rstrip("/")
        try:
            if p == "/unsubscribe":
                return _send(self, _unsubscribe(urllib.parse.parse_qs(q)))
            if p == "/continue":
                return _continue(self, urllib.parse.parse_qs(q))
        except Exception as e:
            _state["last_error"] = "page: %s" % str(e)[:120]
        return orig_get(self)

    def do_POST(self):
        p, _, q = (self.path or "").partition("?")
        if p.rstrip("/") == "/unsubscribe":   # mail apps' one-click unsubscribe
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(min(n, 4096))
                return _send(self, _unsubscribe(urllib.parse.parse_qs(q)))
            except Exception as e:
                _state["last_error"] = "unsub: %s" % str(e)[:120]
        return orig_post(self)

    H.do_GET = do_GET
    H.do_POST = do_POST
    H._autopilot_pages = True
    _state["pages"] = True
    return True


# ---------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------

def _is_admin():
    try:
        from modules import monitor as M
    except Exception:
        import monitor as M
    return M._is_admin()


def _queue():
    items = due()
    return [{"step": s, "email": c["email"], "name": c.get("name"), "company": c.get("org") or c.get("company")} for s, r, c in items[:100]]


def _log(limit=100):
    return [{"utc": _iso(a), "email": e, "step": s, "status": st, "subject": sub} for e, s, a, st, sub in
            _safe("SELECT email, step, at, status, subject FROM autopilot_sent ORDER BY at DESC LIMIT ?", (limit,))]


def arm():
    with _lock:
        if not _state["ready"]:
            _setup()
            _state["ready"] = True
        _install_pages()
        if not _state["worker"]:
            _state["worker"] = True
            threading.Thread(target=_worker, name="autopilot", daemon=True).start()


def status():
    t0 = time.time() - time.time() % 86400
    return {"module": "autopilot", "version": VERSION, "armed": _state["pages"], "paused": _state["paused"],
            "email_configured": bool(os.environ.get("BREVO_API_KEY")), "dry_run": os.environ.get("AUTOPILOT_DRY", "0") == "1",
            "every_minutes": INTERVAL // 60, "sent_today": _db("SELECT COUNT(*) FROM autopilot_sent WHERE at>=? AND status='sent'", (t0,), one=True)[0],
            "sent_total": _db("SELECT COUNT(*) FROM autopilot_sent WHERE status='sent'", one=True)[0],
            "unsubscribed": _db("SELECT COUNT(*) FROM autopilot_optout", one=True)[0],
            "last_run": _state["last_run"], "last_result": _state["last_result"], "last_error": _state["last_error"]}


def handle(method, action, data, api_key, ctx):
    try:
        arm()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:150]
    data = data or {}
    if action in ("", "status"):
        return status(), 200
    if not _is_admin():
        return {"error": "admin_only", "message": "Log in at https://sebbi.pro/admin"}, 401
    if action == "queue":
        q = _queue()
        return {"due_now": len(q), "queue": q, "status": status()}, 200
    if action == "log":
        return {"log": _log()}, 200
    if action == "pause" and method == "POST":
        _set_paused(True)
        return {"paused": True}, 200
    if action == "resume" and method == "POST":
        _set_paused(False)
        return {"paused": False}, 200
    if action == "run" and method == "POST":
        return run_once(force=True, include_test_domains=bool(data.get("include_test_domains"))), 200
    return {"error": "unknown_action", "action": action}, 404
