"""
modules/proveit.py  v1.0.0  -  the Prove-It demand

Arms the demand side of the market. Anyone who has had an automated/AI
decision made about them (loan refused, account banned, claim denied,
content removed, application rejected) can issue a free, timestamped,
chain-sealed DEMAND for the record of that decision - exercising their
existing right to an explanation (UK/EU GDPR Art. 22, EU AI Act Art. 22).

It seals one neutral, true fact: that on a given date a person formally
demanded the record of an automated decision concerning a named company,
citing those rights. It does NOT assert the company did anything wrong.
The company can only answer such a demand if it sealed the decision - so
the demand itself creates the pull to adopt sealing.

New file only. Nothing existing is touched. Seals through the platform's
own s.seal() (append-only), mirroring humankeys.py.

Pages:   https://sebbi.pro/proveit            issue a demand
         https://sebbi.pro/pv/<code>          the public sealed receipt
API:     POST https://sebbi.pro/x/proveit/issue
         GET  https://sebbi.pro/x/proveit/get?code=PRV-XXXX-XXXX
         GET  https://sebbi.pro/x/proveit/status | /spec

Arm with everything:  https://sebbi.pro/x/arm/status
"""

import html as _html
import json
import re
import secrets
import sys
import time
from datetime import datetime, timezone

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec"), ("GET", "get"), ("POST", "issue")}

SITE = "https://sebbi.pro"
OG_IMG = SITE + "/og-cover.png"
CODE_RE = re.compile(r"^PRV-[0-9A-HJ-NP-Z]{4}-[0-9A-HJ-NP-Z]{4}$")
ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O
DOMAIN_RE = re.compile(r"^[a-z0-9.-]{3,120}$")

DECISION_TYPES = [
    "Loan or credit refused", "Account suspended or banned", "Insurance claim denied",
    "Job application rejected", "Content removed or demonetised", "Payment or payout blocked",
    "Benefit or eligibility denied", "Price or limit set automatically", "Other automated decision",
]

_state = {"ready": False, "issued": 0, "last_error": None, "patched": False, "hits": {}}


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "Handler"):
        m = sys.modules.get("server")
    return m


def _setup():
    if _state["ready"]:
        return
    s = _srv()
    with s._db_lock:
        s._conn.execute(
            "CREATE TABLE IF NOT EXISTS proveit_demand("
            "code TEXT PRIMARY KEY, company TEXT, decision_type TEXT, decision_date TEXT,"
            "reference TEXT, legal_basis TEXT, sealed_at REAL, block_index INTEGER, audit_hash TEXT)")
        s._conn.execute("CREATE INDEX IF NOT EXISTS idx_pv_company ON proveit_demand(company)")
        s._conn.commit()
    _state["ready"] = True


def _new_code():
    def grp():
        return "".join(secrets.choice(ALPHABET) for _ in range(4))
    for _ in range(12):
        code = "PRV-%s-%s" % (grp(), grp())
        s = _srv()
        with s._db_lock:
            if not s._conn.execute("SELECT 1 FROM proveit_demand WHERE code=?", (code,)).fetchone():
                return code
    return "PRV-%s-%s" % (grp(), grp())


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _client_ip(h):
    try:
        xf = h.headers.get("X-Forwarded-For", "")
        if xf:
            return xf.split(",")[0].strip()
        return h.client_address[0]
    except Exception:
        return "?"


def _throttled(ip):
    now = time.time()
    hits = _state["hits"]
    window = [t for t in hits.get(ip, []) if now - t < 3600]
    if len(window) >= 10:
        hits[ip] = window
        return True
    window.append(now)
    hits[ip] = window
    return False


def _clean(v, n):
    return (str(v or "").strip())[:n]


def _letter(company, dtype, ddate, ref, code):
    date_line = ddate or "[date of the decision]"
    ref_line = ("\nMy reference: %s" % ref) if ref else ""
    return (
        "To the Data Protection Officer / Compliance Team at %s,\n\n"
        "RE: Request for the record and explanation of an automated decision\n\n"
        "On or around %s an automated or AI-assisted decision was made concerning me: "
        "\"%s\".%s\n\n"
        "I am exercising my right to obtain meaningful information about, and to contest, "
        "a decision based solely on automated processing, under Article 22 of the UK/EU GDPR "
        "and the transparency and human-oversight requirements of the EU AI Act (Articles 13, 14 "
        "and 22 where applicable).\n\n"
        "Please provide, within one month:\n"
        "  1. Confirmation of whether the decision was wholly or partly automated;\n"
        "  2. The record of the decision as it stood at the time it was made, including the "
        "inputs and the logic involved;\n"
        "  3. Meaningful information about how the decision was reached; and\n"
        "  4. How I may request human review and contest the outcome.\n\n"
        "This request has been independently time-stamped and sealed as a tamper-evident record "
        "at %s/pv/%s, so the date it was made is a matter of public proof.\n\n"
        "I look forward to your response within the statutory period.\n\n"
        "Yours faithfully,\n[Your name]"
    ) % (company, date_line, dtype, ref_line, SITE, code)


def _issue(data, h):
    _setup()
    ip = _client_ip(h) if h is not None else "?"
    if ip and ip != "?" and _throttled(ip):
        return {"error": "rate_limited", "message": "A few demands at a time, please. Try again shortly."}, 429
    data = data or {}
    company = _clean(data.get("company"), 120)
    if not company:
        return {"error": "company_required", "message": "Name the company or its website."}, 400
    dtype = _clean(data.get("decision_type"), 120) or "Other automated decision"
    ddate = _clean(data.get("decision_date"), 40)
    ref = _clean(data.get("reference"), 120) or None
    legal = "UK/EU GDPR Art.22; EU AI Act Art.13/14/22"
    code = _new_code()
    ts = time.time()
    event = {"user_id": "proveit", "action": "decision_record_demanded", "amount": 0,
             "country": "UK", "device_id": "proveit", "anomaly": 0, "device_risk": 0}
    result = {"decision": "DEMAND_ISSUED", "score": 0, "version": VERSION, "timestamp": ts,
              "code": code, "company": company, "decision_type": dtype,
              "decision_date": ddate or None, "reference": ref, "legal_basis": legal,
              "note": "A person demanded the record of an automated decision. Not an allegation of wrongdoing."}
    s = _srv()
    try:
        out = s.seal(event, result, ts)
        ahash, idx = out[0], out[1]
    except Exception as e:
        _state["last_error"] = "seal: %s" % str(e)[:160]
        return {"error": "seal_failed", "detail": str(e)[:160]}, 500
    with s._db_lock:
        s._conn.execute("INSERT INTO proveit_demand(code,company,decision_type,decision_date,"
                        "reference,legal_basis,sealed_at,block_index,audit_hash) VALUES(?,?,?,?,?,?,?,?,?)",
                        (code, company, dtype, ddate, ref, legal, ts, idx, ahash))
        s._conn.commit()
    _state["issued"] += 1
    return {"issued": True, "code": code, "company": company, "decision_type": dtype,
            "decision_date": ddate or None, "reference": ref, "legal_basis": legal,
            "sealed_utc": _iso(ts), "block_index": idx, "audit_hash": ahash,
            "receipt": "%s/pv/%s" % (SITE, code),
            "verify": "%s/x/proveit/get?code=%s" % (SITE, code),
            "letter": _letter(company, dtype, ddate, ref, code)}, 200


def _get(code):
    _setup()
    code = (code or "").strip().upper()
    if not CODE_RE.match(code):
        return {"error": "bad_code"}, 400
    s = _srv()
    with s._db_lock:
        r = s._conn.execute("SELECT code,company,decision_type,decision_date,reference,legal_basis,"
                            "sealed_at,block_index,audit_hash FROM proveit_demand WHERE code=?",
                            (code,)).fetchone()
    if not r:
        return {"found": False, "code": code}, 404
    return {"found": True, "code": r[0], "company": r[1], "decision_type": r[2],
            "decision_date": r[3], "reference": r[4], "legal_basis": r[5],
            "sealed_utc": _iso(r[6]), "block_index": r[7], "audit_hash": r[8],
            "receipt": "%s/pv/%s" % (SITE, r[0]),
            "note": "A person demanded the record of this automated decision. This is not an allegation of wrongdoing."}, 200


# ---------------------------------------------------------------- pages
_CSS = """
*{margin:0;padding:0;box-sizing:border-box}body{background:#05070f;color:#eaf0fb;
font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;line-height:1.5;
background-image:radial-gradient(120% 80% at 50% -10%,rgba(37,52,110,.5),rgba(5,7,15,0) 55%),radial-gradient(90% 60% at 50% 120%,rgba(201,168,76,.08),rgba(5,7,15,0) 60%)}
.wrap{max-width:680px;margin:0 auto;padding:40px 20px 80px}
a{color:#f0d78a}.mut{color:#8b94ab}.gold{color:#f0d78a}
.kick{font:600 11px/1 'IBM Plex Mono',monospace;letter-spacing:.3em;color:#c9a84c;text-transform:uppercase}
h1{font:700 clamp(28px,6vw,40px)/1.08 Inter,sans-serif;letter-spacing:-.02em;margin:14px 0 10px;
background:linear-gradient(92deg,#fff,#f0d78a 55%,#4fd6e0);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.lead{font-size:16px;color:#c2cbe0;margin-bottom:26px}
label{display:block;font:600 12px/1 'IBM Plex Mono',monospace;letter-spacing:.08em;color:#9aa4bd;margin:18px 0 7px;text-transform:uppercase}
input,select,textarea{width:100%;background:rgba(10,15,30,.7);border:1px solid rgba(255,255,255,.14);color:#eaf0fb;
padding:13px 15px;border-radius:9px;font:400 15px Inter,sans-serif;outline:none}
input:focus,select:focus{border-color:#c9a84c}
.btn{display:inline-block;margin-top:24px;background:linear-gradient(180deg,#f0d78a,#c9a84c);color:#140d00;
border:0;border-radius:10px;padding:15px 26px;font:700 15px Inter,sans-serif;cursor:pointer;width:100%;
box-shadow:0 8px 26px rgba(201,168,76,.3)}
.card{background:rgba(10,15,30,.6);border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:24px;margin-top:22px}
.row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:14px}
.row:last-child{border:0}.row .k{color:#8b94ab}.row .v{text-align:right;font-weight:600}
.badge{display:inline-flex;align-items:center;gap:8px;border:1px solid rgba(95,227,161,.4);background:rgba(95,227,161,.1);
color:#8ff0bf;border-radius:999px;padding:8px 15px;font:700 13px Inter;letter-spacing:.02em}
.dot{width:9px;height:9px;border-radius:50%;background:#5fe3a1;box-shadow:0 0 10px #5fe3a1}
textarea{min-height:230px;font:13px/1.55 'IBM Plex Mono',monospace;white-space:pre}
.copy{background:rgba(255,255,255,.08);color:#eaf0fb;border:1px solid rgba(255,255,255,.16);border-radius:8px;
padding:10px 16px;font:600 13px Inter;cursor:pointer;margin-top:10px}
.foot{margin-top:40px;font-size:12px;color:#5f6b85;border-top:1px solid rgba(255,255,255,.07);padding-top:18px}
.cta{display:block;margin-top:14px;background:rgba(201,168,76,.12);border:1px solid rgba(201,168,76,.35);
border-radius:10px;padding:16px;text-decoration:none;color:#f0d78a;font-weight:600}
.err{color:#ff9a9a;margin-top:14px}
"""


def _head(title, desc, canonical):
    t, d = _html.escape(title), _html.escape(desc)
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>" + t + "</title>"
        "<meta name=description content='" + d + "'>"
        "<meta id='sebbi-og' property='og:type' content='website'>"
        "<meta property='og:site_name' content='sebbi.pro'>"
        "<meta property='og:title' content='" + t + "'>"
        "<meta property='og:description' content='" + d + "'>"
        "<meta property='og:image' content='" + OG_IMG + "'>"
        "<meta property='og:url' content='" + _html.escape(canonical) + "'>"
        "<meta name='twitter:card' content='summary_large_image'>"
        "<meta name='twitter:image' content='" + OG_IMG + "'>"
        "<link rel=canonical href='" + _html.escape(canonical) + "'>"
        "<style>" + _CSS + "</style></head><body><div class=wrap>"
    )


def _form_page():
    opts = "".join("<option>" + _html.escape(x) + "</option>" for x in DECISION_TYPES)
    return (_head("Prove It - demand the record of an AI decision - sebbi.pro",
                  "Had an automated decision made about you? Issue a free, time-stamped, chain-sealed demand for its record - your right under GDPR Art.22 and the EU AI Act.",
                  SITE + "/proveit") +
        "<div class=kick>&#9876;&nbsp; YOUR RIGHT TO AN EXPLANATION</div>"
        "<h1>Make them prove the decision.</h1>"
        "<p class=lead>An AI or automated system made a decision about you &mdash; a refusal, a ban, a denial? "
        "You have the right to the record and the reasoning. Issue a free demand. We seal it into Bitcoin so "
        "the date you asked can never be denied, and hand you a letter to send.</p>"
        "<div id=form>"
        "<label>The company (name or website)</label>"
        "<input id=company placeholder='e.g. acme-bank.com' autocomplete=off>"
        "<label>What was the decision?</label>"
        "<select id=dtype>" + opts + "</select>"
        "<label>When did it happen? (optional)</label>"
        "<input id=ddate placeholder='e.g. 3 October 2026' autocomplete=off>"
        "<label>Your reference (optional, shown on the record)</label>"
        "<input id=ref placeholder='e.g. case #, or leave blank' autocomplete=off>"
        "<button class=btn id=go>Seal my demand &rarr;</button>"
        "<div class=err id=err></div>"
        "</div>"
        "<div id=out></div>"
        "<div class=foot>We seal one fact: that you demanded this record, and when. That is true and neutral &mdash; "
        "it is not an allegation that the company did anything wrong. It does not constitute legal advice. "
        "Your demand is public at its receipt link; we do not publish your identity.</div>"
        "<script>" + _FORM_JS + "</script></div></body></html>")


_FORM_JS = r"""
var $=function(i){return document.getElementById(i)};
$('go').onclick=function(){
  var company=$('company').value.trim();
  if(!company){$('err').textContent='Enter the company name or website.';return;}
  $('go').disabled=true;$('go').textContent='Sealing…';$('err').textContent='';
  fetch('/x/proveit/issue',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({company:company,decision_type:$('dtype').value,decision_date:$('ddate').value.trim(),reference:$('ref').value.trim()})})
  .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}})})
  .then(function(x){
    if(!x.ok||!x.j.issued){$('err').textContent=(x.j&&x.j.message)||'Could not seal right now. Try again.';$('go').disabled=false;$('go').textContent='Seal my demand →';return;}
    var j=x.j;$('form').style.display='none';
    var esc=function(s){return (s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
    var h='<div class=badge><span class=dot></span>DEMAND SEALED</div>'
      +'<div class=card><div class=row><span class=k>Company</span><span class=v>'+esc(j.company)+'</span></div>'
      +'<div class=row><span class=k>Decision</span><span class=v>'+esc(j.decision_type)+'</span></div>'
      +(j.decision_date?'<div class=row><span class=k>When</span><span class=v>'+esc(j.decision_date)+'</span></div>':'')
      +'<div class=row><span class=k>Sealed</span><span class=v>'+esc(j.sealed_utc)+'</span></div>'
      +'<div class=row><span class=k>Chain block</span><span class=v>#'+j.block_index+'</span></div>'
      +'<div class=row><span class=k>Receipt</span><span class=v><a href="/pv/'+j.code+'">'+j.code+'</a></span></div></div>'
      +'<label>Your letter &mdash; copy it and email the company</label>'
      +'<textarea id=letter readonly>'+esc(j.letter)+'</textarea>'
      +'<button class=copy id=cp>Copy the letter</button>'
      +'<a class=cta href="/pv/'+j.code+'">Share your sealed receipt &rarr;</a>';
    $('out').innerHTML=h;
    $('cp').onclick=function(){var t=$('letter');t.select();try{document.execCommand('copy')}catch(e){};
      navigator.clipboard&&navigator.clipboard.writeText(t.value);$('cp').textContent='Copied ✓';};
    window.scrollTo(0,0);
  }).catch(function(){$('err').textContent='Network error. Try again.';$('go').disabled=false;$('go').textContent='Seal my demand →';});
};
"""


def _receipt_page(code):
    code = _html.escape((code or "").upper())
    return (_head("Sealed demand " + code + " - sebbi.pro",
                  "A time-stamped, chain-sealed demand for the record of an automated decision. Verify it against Bitcoin, without trusting anyone.",
                  SITE + "/pv/" + code) +
        "<div class=kick>&#9876;&nbsp; SEALED DEMAND</div>"
        "<h1>A decision record was demanded.</h1>"
        "<div id=out><p class=mut>Loading the sealed record…</p></div>"
        "<div class=foot>This records only that a demand was made, and when &mdash; a neutral, true fact, not an "
        "allegation of wrongdoing. Verify the seal yourself at <a href='/forever'>/forever</a>.</div>"
        "<script>var CODE='" + code + "';" + _RECEIPT_JS + "</script></div></body></html>")


_RECEIPT_JS = r"""
var esc=function(s){return (''+(s==null?'':s)).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})};
fetch('/x/proveit/get?code='+encodeURIComponent(CODE)).then(function(r){return r.json()}).then(function(j){
  var o=document.getElementById('out');
  if(!j.found){o.innerHTML='<p class=mut>No sealed demand found for '+esc(CODE)+'.</p>';return;}
  o.innerHTML='<div class=card>'
    +'<div class=row><span class=k>Company</span><span class=v>'+esc(j.company)+'</span></div>'
    +'<div class=row><span class=k>Decision</span><span class=v>'+esc(j.decision_type)+'</span></div>'
    +(j.decision_date?'<div class=row><span class=k>When</span><span class=v>'+esc(j.decision_date)+'</span></div>':'')
    +(j.reference?'<div class=row><span class=k>Reference</span><span class=v>'+esc(j.reference)+'</span></div>':'')
    +'<div class=row><span class=k>Legal basis</span><span class=v>'+esc(j.legal_basis)+'</span></div>'
    +'<div class=row><span class=k>Sealed</span><span class=v>'+esc(j.sealed_utc)+'</span></div>'
    +'<div class=row><span class=k>Chain block</span><span class=v>#'+esc(j.block_index)+'</span></div>'
    +'<div class=row><span class=k>Audit hash</span><span class=v style="font:11px monospace;word-break:break-all">'+esc((j.audit_hash||'').slice(0,32))+'…</span></div>'
    +'</div>'
    +'<a class=cta href="/connect">Is this your company? Answer with sealed proof &rarr;</a>'
    +'<a class=cta href="/proveit">Had an AI decision made about you? Demand its record &rarr;</a>';
}).catch(function(){document.getElementById('out').innerHTML='<p class=mut>Could not load the record right now.</p>';});
"""


def _send_html(h, body):
    data = body.encode("utf-8")
    h.send_response(200)
    h.send_header("Content-Type", "text/html; charset=utf-8")
    h.send_header("Content-Length", str(len(data)))
    h.end_headers()
    if getattr(h, "command", "GET") != "HEAD":
        h.wfile.write(data)


def _install():
    s = _srv()
    H = getattr(s, "Handler", None)
    if H is None:
        return False
    if getattr(H, "_proveit_patched", False):
        return True
    orig = H.do_GET

    def do_GET(self):
        p = self.path.split("?")[0].rstrip("/") or "/"
        if p == "/proveit":
            return _send_html(self, _form_page())
        if p.startswith("/pv/"):
            code = p[4:]
            return _send_html(self, _receipt_page(code))
        return orig(self)

    H.do_GET = do_GET
    H._proveit_patched = True
    _state["patched"] = True
    return True


def handle(method, action, data, api_key, ctx):
    try:
        _setup()
        _state["patched"] = _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:160]
    h = None
    if isinstance(ctx, dict):
        h = ctx.get("handler") or ctx.get("h")
    if action == "issue" and method == "POST":
        return _issue(data, h)
    if action == "get":
        code = (data or {}).get("code") if isinstance(data, dict) else None
        if isinstance(code, list):
            code = code[0] if code else None
        return _get(code)
    if action == "spec":
        return {"module": "proveit", "version": VERSION, "page": SITE + "/proveit",
                "decision_types": DECISION_TYPES, "legal": "GDPR Art.22; EU AI Act Art.13/14/22"}, 200
    return ({"module": "proveit", "version": VERSION, "armed": _state["patched"],
             "page": SITE + "/proveit", "demands_issued": _state["issued"],
             "last_error": _state["last_error"]}, 200)
