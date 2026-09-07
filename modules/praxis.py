"""
modules/praxis.py  v1.0.1

Outbound submitter for the PRAXIS external-witness observe endpoint (chain 4).

Contract implemented against the SERVED schema route, not prose:
    GET  https://chain4.thepraesidium.ai/api/external-witness/observe/schema
    POST https://chain4.thepraesidium.ai/api/external-witness/observe

Signing:
    preimage  = b"PRAXIS-OBSERVE-v1\\n" + canonical JSON of the envelope
                with the "signature" field REMOVED
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode("utf-8")
    signature = lowercase hex HMAC-SHA256, carried in the body

Secret:
    environment variable PRAXIS_OBSERVE_SECRET
    (never written to a file, never returned by any route)

Routes
    GET  /x/praxis/spec      public   what this module does and how it signs
    GET  /x/praxis/status    public   config check + arms the /praxis page
    GET  /x/praxis/schema    public   fetches THEIR live contract, reports version
    GET  /x/praxis/history   keyed    past attempts from our own chain
    POST /x/praxis/canonical keyed    dry run: envelope, preimage, signature, NO send
    POST /x/praxis/submit    keyed    signs and sends ONE bounded submission

v1.0.1 fixes a real fault found on 7 Sep 2026. _seal called the host seal()
with one argument when it requires three, so every submit reported
sealed:false while the response still said ok:true. A remote call was being
recorded by the peer with no matching entry in our own chain. A failed seal
now makes the whole response ok:false and says so at the top level.
"""

import os
import json
import time
import hmac
import hashlib
import secrets
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

VERSION = "1.0.1"

# ---------------------------------------------------------------- constants

BASE = "https://chain4.thepraesidium.ai"
OBSERVE_URL = BASE + "/api/external-witness/observe"
SCHEMA_URL = BASE + "/api/external-witness/observe/schema"

DOMAIN = b"PRAXIS-OBSERVE-v1\n"
ENVELOPE_SCHEMA = "praxis_external_observe_request_v1"

OUR_PEER_ID = "aileash"
OUR_TIP_URL = "https://sebbi.pro/x/witness/tip"

SECRET_ENV = "PRAXIS_OBSERVE_SECRET"

TIMEOUT = 20
MAX_RESPONSE_BYTES = 262144

PUBLIC = {
    ("GET", "spec"),
    ("GET", "status"),
    ("GET", "schema"),
}


# ---------------------------------------------------------------- helpers

def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256_hex(b):
    return hashlib.sha256(b).hexdigest()


def _secret():
    s = os.environ.get(SECRET_ENV, "")
    return s.strip()


def _fresh_nonce():
    # matches ^[A-Za-z0-9_.:-]{12,128}$
    return secrets.token_hex(20)


def _fresh_idem():
    # matches ^[0-9a-f]{64}(\.attempt-N)?$
    return secrets.token_hex(32)


def _http(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "AILeash-praxis/" + VERSION)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(MAX_RESPONSE_BYTES)
            return r.status, dict(r.headers), raw, None
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read(MAX_RESPONSE_BYTES)
        except Exception:
            pass
        return e.code, dict(getattr(e, "headers", {}) or {}), raw, None
    except Exception as e:
        return 0, {}, b"", "%s: %s" % (type(e).__name__, e)


def _parse_json(raw):
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _build_envelope(tip_digest, witnessed_peer_id, source_url,
                    receipt_digest=None, attempt=None, observed_at=None):
    payload = {
        "witnessed_peer_id": witnessed_peer_id,
        "data_class": "HASH_ONLY",
        "tip_digest": tip_digest,
        "source_url": source_url,
        "observed_at": observed_at or _now_iso(),
    }
    # receipt_digest is OPTIONAL in contract v1_1 and is omitted for a pure
    # chain-tip observation. Never duplicate tip_digest into it.
    if receipt_digest:
        payload["receipt_digest"] = receipt_digest

    key = _fresh_idem()
    if attempt:
        key = "%s.attempt-%s" % (key, attempt)

    return {
        "schema_version": ENVELOPE_SCHEMA,
        "peer_id": OUR_PEER_ID,
        "ts": _now_iso(),
        "nonce": _fresh_nonce(),
        "idempotency_key": key,
        "payload": payload,
    }


def _sign(envelope, secret):
    unsigned = {k: v for k, v in envelope.items() if k != "signature"}
    canonical = _canonical(unsigned)
    preimage = DOMAIN + canonical
    sig = hmac.new(secret.encode("utf-8"), preimage, hashlib.sha256).hexdigest()
    return canonical, preimage, sig


def _validate(tip_digest, witnessed_peer_id, source_url, receipt_digest):
    import re
    if not re.fullmatch(r"[0-9a-f]{64}", tip_digest or ""):
        return "tip_digest must be 64 lowercase hex characters"
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{2,63}", witnessed_peer_id or ""):
        return "witnessed_peer_id must match ^[a-z][a-z0-9_.:-]{2,63}$"
    if not (source_url or "").startswith("https://") or (source_url or "").count("/") < 3:
        return "source_url must be an https URL with a path"
    if len(source_url) > 512:
        return "source_url exceeds 512 characters"
    if receipt_digest and not re.fullmatch(r"[0-9a-f]{64}", receipt_digest):
        return "receipt_digest, if supplied, must be 64 lowercase hex characters"
    if receipt_digest and receipt_digest == tip_digest:
        return "receipt_digest must not duplicate tip_digest"
    return None


def _record_seal_result(out, res):
    """Read whatever the host seal() handed back."""
    if isinstance(res, dict):
        out["audit_hash"] = (res.get("audit_hash") or res.get("hash")
                             or res.get("seal") or res.get("block_hash"))
        out["block_index"] = res.get("block_index") or res.get("index")
    elif isinstance(res, str):
        out["audit_hash"] = res
    out["sealed"] = bool(out["audit_hash"])
    return out


def _seal(ctx, event):
    """Seal into our own chain.

    The host seal() takes three positional arguments (event, result, ts).
    v1.0.0 called it with one and every submit failed silently. We try the
    three-argument form first and fall back only if the host is older, and
    we record which call shape worked so this is never guesswork again.
    """
    out = {"sealed": False, "audit_hash": None, "error": None,
           "call_shape": None}
    sealer = ctx.get("seal")
    if not sealer:
        out["error"] = "no seal function in ctx"
        return out

    result_value = event.get("result") or "sent"
    ts_value = event.get("ts") or _now_iso()

    attempts = [
        ("seal(event, result, ts)", lambda: sealer(event, result_value, ts_value)),
        ("seal(event, result)", lambda: sealer(event, result_value)),
        ("seal(event)", lambda: sealer(event)),
    ]

    errors = []
    for shape, call in attempts:
        try:
            res = call()
        except TypeError as e:
            errors.append("%s -> TypeError: %s" % (shape, e))
            continue
        except Exception as e:
            out["error"] = "%s -> %s: %s" % (shape, type(e).__name__, e)
            out["call_shape"] = shape
            return out
        out["call_shape"] = shape
        _record_seal_result(out, res)
        if not out["sealed"]:
            out["error"] = "seal returned no hash"
        return out

    out["error"] = "no accepted call shape; " + " | ".join(errors)
    return out


# ---------------------------------------------------------------- page

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>PRAXIS submit</title>
<style>
:root{--ink:#0a0f1e;--ink2:#10182e;--gold:#c9a84c;--ok:#7fe3b0;--err:#ff8a80}
*{box-sizing:border-box}
body{margin:0;padding:16px;background:var(--ink);color:#e8ecf5;
     font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1{font-size:18px;margin:0 0 4px;color:var(--gold)}
p.sub{margin:0 0 18px;color:#8b96ad;font-size:13px}
label{display:block;margin:12px 0 4px;font-size:12px;color:#8b96ad;
      text-transform:uppercase;letter-spacing:.06em}
input{width:100%;padding:11px;background:var(--ink2);border:1px solid #24304e;
      border-radius:8px;color:#e8ecf5;font:14px monospace}
input:focus{outline:none;border-color:var(--gold)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
button{flex:1;min-width:120px;padding:13px;border:0;border-radius:8px;
       background:var(--gold);color:#0a0f1e;font-weight:600;font-size:15px}
button.alt{background:var(--ink2);color:#e8ecf5;border:1px solid #24304e}
button:disabled{opacity:.45}
pre{margin-top:16px;padding:12px;background:var(--ink2);border:1px solid #24304e;
    border-radius:8px;white-space:pre-wrap;word-break:break-all;
    font:12px/1.45 monospace;max-height:60vh;overflow:auto}
.ok{color:var(--ok)}.err{color:var(--err)}
</style></head><body>

<h1>PRAXIS observe &mdash; chain 4</h1>
<p class="sub">Signs one bounded submission and sends it. Fresh ts, nonce and
idempotency key every press.</p>

<label>API key</label>
<input id="key" type="password" placeholder="AILeash API key" autocomplete="off">

<label>Tip digest (64 hex)</label>
<input id="tip" placeholder="press Load tip">

<label>Witnessed peer id</label>
<input id="wpid" value="aileash">

<label>Source URL</label>
<input id="src" value="https://sebbi.pro/x/witness/tip">

<label>Attempt marker (optional)</label>
<input id="att" placeholder="leave blank for a first attempt">

<div class="row">
  <button class="alt" onclick="loadTip()">Load tip</button>
  <button class="alt" onclick="theirSchema()">Their schema</button>
</div>
<div class="row">
  <button class="alt" onclick="go('canonical')">Dry run</button>
  <button onclick="send()">Send</button>
</div>

<pre id="out">Ready.</pre>

<script>
var out = document.getElementById('out');
function show(t, cls){ out.className = cls || ''; out.textContent = t; }
function val(id){ return document.getElementById(id).value.trim(); }

function loadTip(){
  show('Loading our tip...');
  fetch('/x/witness/tip').then(function(r){ return r.json(); }).then(function(j){
    var t = j.tip || j.hash || j.head || j.chain_tip || j.latest || '';
    document.getElementById('tip').value = t;
    show('Tip loaded.\\n\\n' + JSON.stringify(j, null, 2), 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function theirSchema(){
  show('Fetching their live contract...');
  fetch('/x/praxis/schema').then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.receipt_digest_required ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function body(){
  return {
    tip_digest: val('tip'),
    witnessed_peer_id: val('wpid'),
    source_url: val('src'),
    attempt: val('att') || null
  };
}

function go(action){
  var k = val('key');
  if(!k){ show('API key required.', 'err'); return; }
  show('Working...');
  fetch('/x/praxis/' + action, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + k },
    body: JSON.stringify(body())
  }).then(function(r){ return r.json(); }).then(function(j){
    show(JSON.stringify(j, null, 2), j.ok === false ? 'err' : 'ok');
  }).catch(function(e){ show('Failed: ' + e, 'err'); });
}

function send(){
  if(!confirm('Send one bounded submission to chain 4 now?')) return;
  go('submit');
}
</script>
</body></html>"""


def _install_page():
    """Serve /praxis by wrapping the running handler's do_GET, once."""
    for mod in list(sys.modules.values()):
        if mod is None:
            continue
        try:
            names = dir(mod)
        except Exception:
            continue
        for name in names:
            try:
                obj = getattr(mod, name, None)
            except Exception:
                continue
            if not isinstance(obj, type):
                continue
            if not (hasattr(obj, "do_GET") and hasattr(obj, "do_POST")):
                continue
            if getattr(obj, "_praxis_patched", False):
                return True
            original = obj.do_GET

            def patched(self, _original=original):
                try:
                    path = self.path.split("?")[0].rstrip("/")
                except Exception:
                    path = ""
                if path == "/praxis":
                    data = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("X-Robots-Tag", "noindex")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                return _original(self)

            obj.do_GET = patched
            obj._praxis_patched = True
            return True
    return False


# ---------------------------------------------------------------- actions

def _spec():
    return {
        "module": "praxis",
        "version": VERSION,
        "what_this_is": (
            "Outbound submitter for the PRAXIS external-witness observe "
            "endpoint. One bounded submission per press. This module sends; "
            "it does not receive."
        ),
        "target": {"observe": OBSERVE_URL, "schema": SCHEMA_URL},
        "signing": {
            "algorithm": "hmac-sha256",
            "domain": "PRAXIS-OBSERVE-v1\\n",
            "canonicalization": "sort_keys=true, separators=(',',':'), ensure_ascii=true, utf-8",
            "preimage": "domain bytes + canonical JSON of the envelope with 'signature' removed",
            "signature_encoding": "lowercase hex",
            "auth_transport": "body, not headers",
        },
        "payload_policy": (
            "receipt_digest is optional under their contract v1_1 and is "
            "omitted for a pure chain-tip observation. It is never filled "
            "with a duplicate of tip_digest or a placeholder."
        ),
        "freshness": "fresh ts, fresh nonce and a fresh idempotency key on every submit",
        "seal_policy": (
            "a submit that reaches the peer but fails to seal into our own "
            "chain returns ok:false with seal_failed true. The send is still "
            "reported in full, because it happened and the peer may hold a "
            "durable record of it."
        ),
        "not_claimed": [
            "this lane is one-directional and does not establish mutual witnessing",
            "their acceptance is a transport and signature outcome, not verification "
            "of anything in our chain",
        ],
        "routes": {
            "public": ["GET spec", "GET status", "GET schema"],
            "keyed": ["GET history", "POST canonical", "POST submit"],
        },
    }


def _status():
    installed = _install_page()
    s = _secret()
    return {
        "module": "praxis",
        "version": VERSION,
        "page": "/praxis",
        "page_installed": installed,
        "peer_id": OUR_PEER_ID,
        "secret_configured": bool(s),
        "secret_env": SECRET_ENV,
        "secret_length": len(s) if s else 0,
        "target": OBSERVE_URL,
        "note": (
            "secret_configured false means the environment variable is not set "
            "on this replica; the secret itself is never returned by any route"
        ),
    }


def _their_schema():
    code, headers, raw, err = _http("GET", SCHEMA_URL)
    if err:
        return {"ok": False, "error": "fetch_failed", "detail": err}, 502
    doc = _parse_json(raw)
    if doc is None:
        return {"ok": False, "error": "unparseable", "status": code}, 502

    req = (((doc.get("request_schema") or {}).get("properties") or {})
           .get("payload") or {})
    required = req.get("required") or []
    hdr = {}
    for k, v in (headers or {}).items():
        if k.lower().startswith("x-praxis") or k.lower() == "cache-control":
            hdr[k.lower()] = v

    return {
        "ok": True,
        "fetched_at": _now_iso(),
        "http_status": code,
        "contract_version": doc.get("schema_version"),
        "payload_required": required,
        "receipt_digest_required": "receipt_digest" in required,
        "canonicalization": ((doc.get("signing") or {}).get("canonicalization")),
        "domain": ((doc.get("signing") or {}).get("domain")),
        "clock_skew_seconds": ((doc.get("freshness") or {}).get("clock_skew_seconds")),
        "headers": hdr,
        "body_sha256": _sha256_hex(raw),
    }, 200


def _canonical_action(data):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig

    return {
        "ok": True,
        "dry_run": True,
        "sent": False,
        "envelope": signed,
        "canonical_json": canonical.decode("utf-8"),
        "canonical_sha256": _sha256_hex(canonical),
        "preimage_sha256": _sha256_hex(preimage),
        "signature": sig,
        "note": "nothing was sent; ts, nonce and idempotency_key here are "
                "single-use and will be regenerated on an actual submit",
    }, 200


def _submit(data, ctx):
    tip = (data.get("tip_digest") or "").strip().lower()
    wpid = (data.get("witnessed_peer_id") or OUR_PEER_ID).strip().lower()
    src = (data.get("source_url") or OUR_TIP_URL).strip()
    rcpt = (data.get("receipt_digest") or "").strip().lower() or None
    attempt = data.get("attempt") or None

    bad = _validate(tip, wpid, src, rcpt)
    if bad:
        return {"ok": False, "error": "invalid_input", "detail": bad}, 400

    secret = _secret()
    if not secret:
        return {"ok": False, "error": "secret_unconfigured",
                "detail": "set %s in the environment" % SECRET_ENV}, 503

    env = _build_envelope(tip, wpid, src, rcpt, attempt)
    canonical, preimage, sig = _sign(env, secret)
    signed = dict(env)
    signed["signature"] = sig
    wire = _canonical(signed)

    started = time.time()
    code, headers, raw, err = _http("POST", OBSERVE_URL, wire)
    took = round(time.time() - started, 3)

    parsed = _parse_json(raw)
    transport_ok = err is None and code in (200, 202)
    result = {
        "ok": transport_ok,
        "sent": err is None,
        "took_seconds": took,
        "http_status": code,
        "transport_error": err,
        "request": {
            "idempotency_key": env["idempotency_key"],
            "nonce": env["nonce"],
            "ts": env["ts"],
            "peer_id": env["peer_id"],
            "payload": env["payload"],
            "signature": sig,
            "canonical_sha256": _sha256_hex(canonical),
            "wire_sha256": _sha256_hex(wire),
            "wire_bytes": len(wire),
        },
        "response": {
            "body": parsed,
            "raw_sha256": _sha256_hex(raw) if raw else None,
            "raw_bytes": len(raw),
            "raw_text": (raw.decode("utf-8", "replace")[:4000] if raw else None),
        },
    }

    if isinstance(parsed, dict):
        result["their_error"] = parsed.get("error")
        result["their_accepted"] = parsed.get("accepted")
        result["their_replayed"] = parsed.get("replayed")
        result["their_request_digest"] = parsed.get("request_digest")
        result["their_durable_event_recorded"] = parsed.get("durable_event_recorded")
        result["their_accepted_decision_recorded"] = parsed.get(
            "accepted_decision_recorded")

    event = {
        "user_id": "praxis:" + OUR_PEER_ID,
        "event": "praxis_observe_submit",
        "kind": "praxis_observe_submit",
        "ts": _now_iso(),
        "target": OBSERVE_URL,
        "idempotency_key": env["idempotency_key"],
        "request_wire_sha256": result["request"]["wire_sha256"],
        "http_status": code,
        "response_sha256": result["response"]["raw_sha256"],
        "their_error": result.get("their_error"),
        "their_accepted": result.get("their_accepted"),
        "result": "sent" if err is None else "transport_error",
    }
    result["our_seal"] = _seal(ctx, event)

    # A send that the peer accepted but our own chain has no entry for is a
    # failure of this deployment, not a success. Say so at the top level.
    if not result["our_seal"].get("sealed"):
        result["ok"] = False
        result["seal_failed"] = True
        result["seal_failed_note"] = (
            "the submission reached the peer but was NOT sealed into our "
            "chain. The peer may hold a durable record with no counterpart "
            "here. Do not treat this submission as evidenced on our side."
        )

    if not transport_ok:
        status = 502 if err else 200
    elif not result["our_seal"].get("sealed"):
        status = 500
    else:
        status = 200
    return result, status


def _history(ctx, data):
    limit = 20
    try:
        limit = max(1, min(100, int(data.get("limit") or 20)))
    except Exception:
        pass
    rows = []
    try:
        conn = ctx.get("conn")
        lock = ctx.get("lock")
        sql = ("SELECT rowid, * FROM audit_log "
               "WHERE user_id = ? ORDER BY rowid DESC LIMIT ?")
        if lock:
            with lock:
                cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            cur = conn.execute(sql, ("praxis:" + OUR_PEER_ID, limit))
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        return {"ok": False, "error": "query_failed",
                "detail": "%s: %s" % (type(e).__name__, e)}, 500
    return {"ok": True, "count": len(rows), "rows": rows}, 200


# ---------------------------------------------------------------- router

def handle(method, action, data, api_key, ctx):
    data = data or {}

    if method == "GET" and action == "spec":
        return _spec(), 200

    if method == "GET" and action == "status":
        return _status(), 200

    if method == "GET" and action == "schema":
        return _their_schema()

    if method == "GET" and action == "history":
        return _history(ctx, data)

    if method == "POST" and action == "canonical":
        return _canonical_action(data)

    if method == "POST" and action == "submit":
        return _submit(data, ctx)

    return {"ok": False, "error": "unknown_action", "action": action,
            "available": ["spec", "status", "schema", "history",
                          "canonical", "submit"]}, 404
