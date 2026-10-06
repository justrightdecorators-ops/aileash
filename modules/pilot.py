"""
modules/pilot.py  v1.0.0  -  the paid 7-day pilot, and the gateway's free allowance

    Arm:    https://sebbi.pro/x/arm/status
    Page:   https://sebbi.pro/pilot
    Orders: https://sebbi.pro/x/pilot/orders?admin=<ADMIN_PASSWORD>

THE PILOT - money on day one
----------------------------
"Governed in 7 days", £495, paid upfront by card through Stripe Checkout.
The whole journey runs without anyone lifting a finger:

  1. the customer fills in four fields on /pilot and pays on Stripe
  2. back on /pilot/thanks the payment is confirmed with Stripe (and a
     background check confirms any customer who closed the page early)
  3. their API key and private gateway URL are created on the spot and shown,
     and emailed to them; Justin gets an email with the order
  4. their key gets the full gateway for 30 days, not the free allowance

Delivered by Monop Content within 7 days: a setup call, a rule pack for
their use case and a regulator-ready evidence file. Live in 7 days or the
full £495 back. The product's own pricing does not change: the key is an
ordinary key with the usual 90 days free, then 50p per device a month.

THE GATEWAY ALLOWANCE - a new product, so new terms
---------------------------------------------------
The gateway (modules/gateway.py) is free for the first 1,000 calls on a key.
After that a key needs a card on file (the normal 50p per device a month
subscription) or an active pilot. Nothing else about any existing product,
trial or price changes. Calls over the allowance get a clear 402 with the
checkout link, in the provider's own error format.
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
PUBLIC = {("GET", "status"), ("POST", "checkout"), ("GET", "confirm"), ("GET", "orders"), ("GET", "")}

PRICE_PENCE = int(os.environ.get("PILOT_PRICE_PENCE", "49500"))
PILOT_DAYS = 30
GATEWAY_FREE_CALLS = int(os.environ.get("GATEWAY_FREE_CALLS", "1000"))
STRIPE_BASE = os.environ.get("PILOT_STRIPE_BASE", "https://api.stripe.com/v1").rstrip("/")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")
SESSION_RE = re.compile(r"^cs_[A-Za-z0-9_]{8,200}$")

_state = {"pages": False, "gate": False, "worker": False, "orders": 0, "paid": 0, "gated": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


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


def _setup():
    s = _srv()
    with s._db_lock:
        s._conn.execute("CREATE TABLE IF NOT EXISTS pilot_order(session_id TEXT PRIMARY KEY, created REAL, name TEXT,"
                        "email TEXT, company TEXT, website TEXT, notes TEXT, status TEXT, paid_at REAL, amount INTEGER,"
                        "api_key TEXT, gateway_token TEXT, new_key INTEGER, emailed INTEGER DEFAULT 0)")
        s._conn.commit()


def _clean(v, n):
    return re.sub(r"[\x00-\x1f<>]", "", str(v or "")).strip()[:n]


def _stripe(method, endpoint, data=None):
    secret = os.environ.get("STRIPE_SECRET", "")
    if not secret:
        return None
    try:
        req = urllib.request.Request(STRIPE_BASE + endpoint,
                                     data=urllib.parse.urlencode(data).encode() if data else None, method=method,
                                     headers={"Authorization": "Bearer " + secret,
                                              "Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return None
    except Exception as e:
        _state["last_error"] = "stripe: %s" % str(e)[:150]
        return None


# ---------------------------------------------------------------------------
# buying
# ---------------------------------------------------------------------------

def checkout(data):
    name = _clean(data.get("name"), 80)
    email = _clean(data.get("email"), 200).lower()
    company = _clean(data.get("company"), 120)
    website = _clean(data.get("website"), 200)
    notes = _clean(data.get("notes"), 600)
    if not name or not EMAIL_RE.match(email) or not company:
        return {"error": "details_needed", "message": "Your name, work email and company, please."}, 400
    if not os.environ.get("STRIPE_SECRET"):
        return {"error": "payments_unavailable", "message": "Card payments are not switched on yet. Email justrightdecorators@gmail.com and we will invoice you."}, 503
    s = _stripe("POST", "/checkout/sessions", {
        "mode": "payment",
        "customer_email": email,
        "line_items[0][price_data][currency]": "gbp",
        "line_items[0][price_data][unit_amount]": str(PRICE_PENCE),
        "line_items[0][price_data][product_data][name]": "sebbi.pro pilot: governed in 7 days",
        "line_items[0][price_data][product_data][description]": "Gateway live, a rule pack for your use case and a regulator-ready evidence file within 7 days. Live in 7 days or your money back.",
        "line_items[0][quantity]": "1",
        "success_url": SITE + "/pilot/thanks?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": SITE + "/pilot?cancelled=1",
        "metadata[product]": "pilot", "metadata[company]": company,
        "payment_intent_data[description]": "sebbi.pro pilot - " + company})
    if not s or not s.get("url") or not str(s.get("id", "")).startswith("cs_"):
        return {"error": "checkout_failed", "message": ((s or {}).get("error") or {}).get("message", "Stripe did not answer. Try again in a minute.")}, 502
    _db("INSERT OR IGNORE INTO pilot_order(session_id,created,name,email,company,website,notes,status) VALUES(?,?,?,?,?,?,?,'pending')",
        (s["id"], time.time(), name, email, company, website, notes), write=True)
    _state["orders"] += 1
    return {"url": s["url"]}, 200


def _finalise(sid):
    """Confirm a session with Stripe and, once paid, set the customer up. Safe to call repeatedly."""
    row = _db("SELECT session_id,name,email,company,website,notes,status,api_key,gateway_token,new_key FROM pilot_order WHERE session_id=?",
              (sid,), one=True)
    if not row:
        return None
    if row[6] == "paid":
        return row
    st = _stripe("GET", "/checkout/sessions/" + urllib.parse.quote(sid))
    if not st or st.get("payment_status") != "paid" or st.get("id") != sid:
        return row
    srv = _srv()
    name, email, company = row[1], row[2], row[3]
    key, err = srv.create_key(email, "", name, company, "pilot", "aileash", 1)
    new_key = 1
    if not key:
        new_key = 0
        r = _db("SELECT key FROM api_keys WHERE email=? ORDER BY created ASC LIMIT 1", (email,), one=True)
        key = r[0] if r else None
    token = None
    if key:
        try:
            try:
                from modules import gateway as G
            except Exception:
                import gateway as G
            token = G.new_token(key, "pilot")["token"]
        except Exception as e:
            _state["last_error"] = "token: %s" % str(e)[:120]
    _db("UPDATE pilot_order SET status='paid', paid_at=?, amount=?, api_key=?, gateway_token=?, new_key=? WHERE session_id=? AND status!='paid'",
        (time.time(), int(st.get("amount_total") or PRICE_PENCE), key, token, new_key, sid), write=True)
    _state["paid"] += 1
    row = _db("SELECT session_id,name,email,company,website,notes,status,api_key,gateway_token,new_key FROM pilot_order WHERE session_id=?",
              (sid,), one=True)
    threading.Thread(target=_emails, args=(sid,), daemon=True).start()
    return row


def _emails(sid):
    row = _db("SELECT name,email,company,website,notes,api_key,gateway_token,new_key,emailed,amount FROM pilot_order WHERE session_id=?",
              (sid,), one=True)
    if not row or row[8]:
        return
    _db("UPDATE pilot_order SET emailed=1 WHERE session_id=?", (sid,), write=True)
    s = _srv()
    name, email, company, website, notes, key, tok, new_key, _, amount = row
    esc = getattr(s, "esc", lambda x: str(x).replace("<", "&lt;"))
    try:
        s.send_email(getattr(s, "OWNER_EMAIL", "justrightdecorators@gmail.com"), "Monop Content",
                     "PILOT PAID: %s (£%.2f)" % (company, (amount or PRICE_PENCE) / 100.0),
                     "<html><body style='font-family:Arial,sans-serif;padding:20px'><h2>New pilot: %s</h2>"
                     "<p><b>%s</b> &lt;%s&gt;</p><p>Website: %s</p><p>What they run: %s</p>"
                     "<p>Paid £%.2f. Key %s, gateway token issued.</p><p>Deliver within 7 days: setup call, rule pack, "
                     "evidence file.</p></body></html>" % (esc(company), esc(name), esc(email), esc(website), esc(notes),
                                                         (amount or PRICE_PENCE) / 100.0,
                                                         "created" if new_key else "existing, linked"))
    except Exception as e:
        _state["last_error"] = "owner email: %s" % str(e)[:120]
    if new_key and key:
        body = ("<p>Your API key (keep it secret):<br><code>%s</code></p>" % esc(key) +
                ("<p>Your private gateway URL for OpenAI:<br><code>%s/g/%s/openai/v1</code><br>and for Anthropic:<br>"
                 "<code>%s/g/%s/anthropic</code></p>" % (SITE, tok, SITE, tok) if tok else ""))
    else:
        body = "<p>Your pilot is linked to the sebbi.pro key you already have. Your gateway URL is ready at https://sebbi.pro/gateway.</p>"
    try:
        s.send_email(email, name, "Your sebbi.pro pilot is live",
                     "<html><body style='font-family:Arial,sans-serif;padding:20px;color:#222'>"
                     "<h2>Welcome, %s. You're live.</h2>%s"
                     "<p>Change one line in your app - the OpenAI or Anthropic base URL - and every AI call is scored, "
                     "sealed and answered with a receipt you can check against Bitcoin. Steps: https://sebbi.pro/gateway</p>"
                     "<p>We'll be in touch within one working day to book your setup call. Within 7 days you get a rule "
                     "pack for your use case and a regulator-ready evidence file. Live in 7 days or your money back.</p>"
                     "<p>Monop Content &middot; sebbi.pro</p></body></html>" % (esc(name.split()[0] if name else ""), body))
    except Exception as e:
        _state["last_error"] = "customer email: %s" % str(e)[:120]


def _worker():
    while True:
        time.sleep(600)
        try:
            for (sid,) in _db("SELECT session_id FROM pilot_order WHERE status='pending' AND created>?",
                              (time.time() - 86400,)):
                _finalise(sid)
        except Exception as e:
            _state["last_error"] = "worker: %s" % str(e)[:120]


def pilot_active(api_key):
    try:
        r = _db("SELECT MAX(paid_at) FROM pilot_order WHERE api_key=? AND status='paid'", (api_key,), one=True)
        return bool(r and r[0] and time.time() - r[0] < PILOT_DAYS * 86400)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# the gateway allowance (wraps gateway.serve_wire; gateway.py is not edited)
# ---------------------------------------------------------------------------

def _install_gate():
    if _state["gate"]:
        return True
    try:
        try:
            from modules import gateway as G
        except Exception:
            import gateway as G
    except Exception as e:
        _state["last_error"] = "gate: %s" % e
        return False
    if getattr(G, "_pilot_gate", False):
        _state["gate"] = True
        return True
    original = G.serve_wire

    def serve_wire(h):
        try:
            parts = (h.path or "").split("?")[0].split("/")
            token = parts[2] if len(parts) > 2 and parts[2].startswith("gw_") else None
            provider = (parts[3] if token else parts[2]) if len(parts) > 2 else "openai"
            key = None
            if token and G.TOKEN_RE.match(token):
                r = _db("SELECT api_key FROM gateway_token WHERE token=? AND revoked=0", (token,), one=True)
                key = r[0] if r else None
            elif not token:
                key = (h.headers.get("X-Sebbi-Key") or "").strip() or None
            ki = _srv().get_key(key) if key else None
            if ki and not ki[3] and not pilot_active(key):
                used = _db("SELECT COUNT(*) FROM gateway_call WHERE key_hash=?", (G._kh(key),), one=True)[0]
                if used >= GATEWAY_FREE_CALLS:
                    _state["gated"] += 1
                    n = int(h.headers.get("Content-Length") or 0)
                    if 0 < n <= G.MAX_BODY:
                        h.rfile.read(n)
                    url = SITE + "/pricing"
                    try:
                        url = _srv().trial_checkout(key, ki[0], ki[6] or "aileash") or url
                    except Exception:
                        pass
                    return G._err(h, provider if provider in G.UPSTREAM else "openai", 402, "gateway_allowance_used",
                                  "Your %d free gateway calls are used. Add a card to keep going - 50p per device a "
                                  "month: %s" % (GATEWAY_FREE_CALLS, url))
        except Exception as e:
            _state["last_error"] = "gate check: %s" % str(e)[:120]
        return original(h)

    G.serve_wire = serve_wire
    G._pilot_gate = True
    _state["gate"] = True
    return True


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def _N():
    try:
        from modules import notary as N
    except Exception:
        import notary as N
    return N


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _pilot_page():
    N = _N()
    price = "£%d" % (PRICE_PENCE // 100) if PRICE_PENCE % 100 == 0 else "£%.2f" % (PRICE_PENCE / 100.0)
    body = r"""<title>Pilot — governed in 7 days — sebbi.pro</title>
<meta name="description" content="Every AI decision your business makes, scored, sealed and provable against Bitcoin — live in 7 days, with a regulator-ready evidence file. __PRICE__, or your money back.">
</head><body>""" + N._TOP + r"""
<main class="wrap">
<section class="hero"><div class="kick"><i></i>PILOT · __PRICE__ · LIVE IN 7 DAYS</div>
<h1>Governed in <em>7 days.</em></h1>
<p>Every AI call your business makes — scored before it leaves, stopped when it should be, sealed and provable against Bitcoin. We set it up with you, write the rules for your use case, and hand you the evidence file a regulator or client will ask for. Live in 7 days or your money back.</p>
</section>
<section class="card"><h2>What you get</h2>
<div class="how">
<div><b>TODAY</b><p>Your API key and private gateway URL the moment you pay. Change one line and you're governed.</p></div>
<div><b>DAY 1–2</b><p>A setup call with us. We connect your apps and agents, whatever you build with.</p></div>
<div><b>DAY 3–5</b><p>A rule pack written for your business — what to allow, challenge and block.</p></div>
<div><b>DAY 7</b><p>Your evidence file: sealed decisions, Forever Proofs against Bitcoin and an EU AI Act gap scan.</p></div>
</div>
<p class="sub">Then carry on as normal: your key keeps the usual 90 days free, then 50p per device a month. No contract.</p></section>
<section class="card" id="buy"><h2>Start now · __PRICE__</h2>
<div style="display:grid;gap:10px">
<input type="text" id="n" placeholder="Your name" autocomplete="name">
<input type="text" id="e" placeholder="Work email" autocomplete="email" inputmode="email">
<input type="text" id="c" placeholder="Company" autocomplete="organization">
<input type="text" id="w" placeholder="Website (optional)" autocomplete="url">
<textarea id="t" placeholder="What AI do you run? e.g. a chatbot on our site, loan decisions, an agent that books jobs (optional)" style="min-height:80px"></textarea>
</div>
<div class="row"><button class="btn b" id="go">Pay __PRICE__ securely</button><span class="msg" id="m"></span></div>
<p class="sub" style="margin-top:10px">Card payment by Stripe. Live in 7 days or the full __PRICE__ back. One payment, nothing else to pay for the pilot.</p></section>
<section class="card"><h2>Why now</h2>
<p class="sub">Regulators, insurers and enterprise buyers are starting to ask one question: can you prove what your AI decided? After this week, you can — to anyone, against Bitcoin, without them trusting you or us.</p>
<div class="row"><a class="btn g" href="/forever">See a proof verify</a><a class="btn g" href="/gateway">How the gateway works</a></div></section>
</main>""" + N._FOOT + r"""
<script>
const $=s=>document.querySelector(s);
if(new URLSearchParams(location.search).get('cancelled')){$('#m').className='msg';$('#m').textContent='Payment cancelled — nothing was charged.'}
$('#go').onclick=async()=>{$('#go').disabled=true;$('#m').className='msg';$('#m').textContent='Opening secure checkout…';
 try{const r=await fetch('/x/pilot/checkout',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('#n').value,email:$('#e').value,company:$('#c').value,website:$('#w').value,notes:$('#t').value})});
  const j=await r.json();if(!r.ok)throw Error(j.message||j.error);location.href=j.url}
 catch(e){$('#m').className='msg err';$('#m').textContent=e.message;$('#go').disabled=false}};
</script></body></html>"""
    return N._page(N._HEAD + body.replace("__PRICE__", price))


def _thanks_page(sid):
    N = _N()
    row = _finalise(sid) if SESSION_RE.match(sid or "") else None
    if not row:
        inner = '<h1>We couldn\'t find that order</h1><p>If you paid, don\'t worry — check your email, or contact justrightdecorators@gmail.com.</p>'
    elif row[6] != "paid":
        inner = ('<h1>Confirming your payment…</h1><p>Stripe hasn\'t confirmed it yet. This page refreshes itself; you\'ll '
                 'also get an email the moment it lands.</p><script>setTimeout(()=>location.reload(),5000)</script>')
    else:
        key, tok, new_key = row[7], row[8], row[9]
        if new_key and key:
            creds = ("<h2>Your API key</h2><p class='sub'>Keep it secret. We've emailed it to you too.</p><pre>%s</pre>" % _esc(key) +
                     ("<h2>Change one line</h2><p class='sub'>Use this as the base URL in your OpenAI or Anthropic SDK:</p>"
                      "<pre>OpenAI:    %s/g/%s/openai/v1\nAnthropic: %s/g/%s/anthropic</pre>" % (SITE, tok, SITE, tok) if tok else ""))
        else:
            creds = "<p class='sub'>Your pilot is linked to the sebbi.pro key you already have. Get your gateway URL at <a href='/gateway'>sebbi.pro/gateway</a>.</p>"
        inner = ("<h1>You're <em>live.</em></h1><p>Thank you, %s. Payment received.</p></section><section class='card'>%s"
                 "<h2>What happens next</h2><p class='sub'>We'll contact you within one working day to book your setup call. "
                 "Within 7 days: your rule pack and your evidence file. Live in 7 days or your money back.</p>"
                 "<div class='row'><a class='btn b' href='/gateway'>Gateway steps</a><a class='btn g' href='/forever'>See a proof verify</a></div>"
                 % (_esc(row[1].split()[0] if row[1] else ""), creds))
    body = ("<title>Your pilot — sebbi.pro</title><meta name='robots' content='noindex'></head><body>" + N._TOP +
            "<main class='wrap'><section class='hero'><div class='kick'><i></i>PILOT</div>" + inner + "</section></main>" + N._FOOT + "</body></html>")
    return N._page(N._HEAD + body)


def _send(h, body, ctype):
    if isinstance(body, str):
        body = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.send_header("Cache-Control", "no-store")
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(body)


def _install_pages():
    if _state["pages"]:
        return True
    H = getattr(_srv(), "Handler", None)
    if H is None:
        return False
    if getattr(H, "_pilot_pages", False):
        _state["pages"] = True
        return True
    orig = H.do_GET

    def do_GET(self):
        p, _, q = (self.path or "").partition("?")
        p = p.rstrip("/")
        try:
            if p == "/pilot":
                return _send(self, _pilot_page(), "text/html; charset=utf-8")
            if p == "/pilot/thanks":
                sid = (urllib.parse.parse_qs(q).get("session_id") or [""])[0]
                return _send(self, _thanks_page(sid), "text/html; charset=utf-8")
        except Exception as e:
            _state["last_error"] = "page: %s" % str(e)[:150]
        return orig(self)

    H.do_GET = do_GET
    H._pilot_pages = True
    _state["pages"] = True
    return True


def arm():
    with _lock:
        _setup()
        _install_pages()
        _install_gate()
        if not _state["worker"]:
            _state["worker"] = True
            threading.Thread(target=_worker, name="pilot", daemon=True).start()


def handle(method, action, data, api_key, ctx):
    try:
        arm()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:150]
    data = data or {}
    if action in ("", "status"):
        return {"module": "pilot", "version": VERSION, "armed": _state["pages"] and _state["gate"],
                "page": SITE + "/pilot", "price_gbp": PRICE_PENCE / 100.0, "payments_on": bool(os.environ.get("STRIPE_SECRET")),
                "gateway_free_calls": GATEWAY_FREE_CALLS, "checkouts_started": _state["orders"],
                "paid_since_start": _state["paid"], "gateway_calls_held_for_card": _state["gated"],
                "last_error": _state["last_error"]}, 200
    if action == "checkout" and method == "POST":
        return checkout(data)
    if action == "confirm":
        sid = str(data.get("session_id", ""))
        if not SESSION_RE.match(sid):
            return {"error": "bad_session"}, 400
        row = _finalise(sid)
        return ({"status": row[6]} if row else {"error": "not_found"}), (200 if row else 404)
    if action == "orders":
        pw = os.environ.get("ADMIN_PASSWORD", "")
        if not pw or not hmac.compare_digest(str(data.get("admin", "")), pw):
            return {"error": "admin_only"}, 403
        rows = _db("SELECT session_id,created,name,email,company,website,notes,status,paid_at,amount FROM pilot_order ORDER BY created DESC LIMIT 200")
        return {"orders": [{"session": r[0][:14] + "…", "created_utc": _iso(r[1]), "name": r[2], "email": r[3],
                            "company": r[4], "website": r[5], "notes": r[6], "status": r[7],
                            "paid_utc": _iso(r[8]) if r[8] else None, "amount_gbp": (r[9] or 0) / 100.0} for r in rows],
                "paid_total_gbp": sum((r[9] or 0) for r in rows if r[7] == "paid") / 100.0}, 200
    return {"error": "unknown_action", "action": action}, 404
