"""
modules/monitor.py  v1.0.0  -  the data behind the admin Monitor

    Arm:    https://sebbi.pro/x/arm/status
    Admin:  https://sebbi.pro/admin   (Monitor tab)
    Data:   GET /x/monitor/all        (admin login token only)

Everything Justin needs on one screen: who signed up, which devices they
linked, what they used, what was downloaded, who visited and from where,
money in, and whether every part of the machine is healthy.

VISITS AND DOWNLOADS
--------------------
server.py does not record visits, so this records them, lightly:
  - page views per path per day, and unique visitors per day. A visitor is a
    salted hash of address + browser + the day, so nobody can be identified
    and the hash changes every day. Bots are counted separately.
  - where visitors came from (the referring site's name only)
  - every download of a tool or verifier, with the time and the same daily hash
Records are buffered in memory and written every 15 seconds, so a page view
never waits on the database. Machine traffic (/x/, /api/, /mcp, /g/) is
counted as a total, not logged.

ACCESS
------
/x/monitor/all answers only to a valid admin login token (the one /admin
gets from /admin/auth). Nothing here writes to the chain.
"""

import hashlib
import hmac
import inspect
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

VERSION = "1.0.0"
PUBLIC = {("GET", "all"), ("GET", "status"), ("GET", "")}
TRIAL_DAYS = 90

DOWNLOAD_RE = re.compile(r"\.(py|zip|tar\.gz|tgz|ots|whl|js|sh|exe|dmg|apk|pdf)$", re.I)
SKIP_PREFIX = ("/x/", "/api/", "/mcp", "/g/", "/c/", "/admin", "/static/", "/favicon", "/robots", "/.well-known/",
               "/sitemap", "/n/", "/k/")
ASSET_RE = re.compile(r"\.(css|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|map|mp4|webm|mp3|txt|xml|json)$", re.I)
BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python-requests|httpx|go-http|headless|scrapy|facebookexternalhit|bingpreview", re.I)

_state = {"installed": False, "writer": False, "last_error": None, "machine_calls": 0, "flushed": 0}
_lock = threading.Lock()
_buf_lock = threading.Lock()
_buf = {"hits": defaultdict(int), "visitors": set(), "bots": defaultdict(int), "refs": defaultdict(int), "downloads": []}
_salt = secrets.token_bytes(16)
_cache = {"chain": None, "chain_at": 0}


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


def _day(ts=None):
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


def _db(sql, args=(), one=False):
    s = _srv()
    with s._db_lock:
        cur = s._conn.execute(sql, args)
        return cur.fetchone() if one else cur.fetchall()


def _q(sql, args=(), default=0):
    try:
        r = _db(sql, args, one=True)
        return r[0] if r and r[0] is not None else default
    except Exception:
        return default


def _setup():
    s = _srv()
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS monitor_hits(day TEXT, path TEXT, n INTEGER, PRIMARY KEY(day, path))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_visitors(day TEXT, vh TEXT, PRIMARY KEY(day, vh))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_bots(day TEXT, n INTEGER, PRIMARY KEY(day))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_refs(day TEXT, host TEXT, n INTEGER, PRIMARY KEY(day, host))")
        c.execute("CREATE TABLE IF NOT EXISTS monitor_download(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, path TEXT,"
                  "vh TEXT, agent TEXT)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mon_dl_ts ON monitor_download(ts)")
        c.commit()


# ---------------------------------------------------------------------------
# recording
# ---------------------------------------------------------------------------

def _record(h):
    try:
        if getattr(h, "command", "") != "GET":
            return
        path = (getattr(h, "path", "") or "").split("?")[0].split("#")[0] or "/"
        if path.startswith(("/x/", "/api/", "/mcp", "/g/", "/c/")):
            _state["machine_calls"] += 1
            return
        hd = getattr(h, "headers", None)
        if hd is None:
            return
        ua = hd.get("User-Agent", "") or ""
        is_dl = bool(DOWNLOAD_RE.search(path)) and not path.startswith(("/static/",))
        if not is_dl and (path.startswith(SKIP_PREFIX) or ASSET_RE.search(path)):
            return
        day = _day()
        if BOT_RE.search(ua) or not ua:
            with _buf_lock:
                _buf["bots"][day] += 1
            return
        xff = hd.get("X-Forwarded-For", "")
        ip = xff.split(",")[0].strip() if xff else str((getattr(h, "client_address", None) or ["?"])[0])
        vh = hmac.new(_salt, ("%s|%s|%s" % (ip, ua[:200], day)).encode(), hashlib.sha256).hexdigest()[:16]
        ref = ""
        r = hd.get("Referer", "") or ""
        m = re.match(r"https?://([^/:?#]+)", r)
        if m:
            host = m.group(1).lower()
            if not host.endswith("sebbi.pro"):
                ref = host[:80]
        agent = re.sub(r"[^\w .;:/()-]", "", ua)[:80]
        with _buf_lock:
            _buf["hits"][(day, path[:120])] += 1
            _buf["visitors"].add((day, vh))
            if ref:
                _buf["refs"][(day, ref)] += 1
            if is_dl:
                _buf["downloads"].append((time.time(), path[:160], vh, agent))
    except Exception as e:
        _state["last_error"] = "record: %s" % str(e)[:120]


def _flush():
    with _buf_lock:
        hits, vis, bots, refs, dls = (dict(_buf["hits"]), set(_buf["visitors"]), dict(_buf["bots"]),
                                      dict(_buf["refs"]), list(_buf["downloads"]))
        _buf["hits"].clear(); _buf["visitors"].clear(); _buf["bots"].clear(); _buf["refs"].clear(); _buf["downloads"].clear()
    if not (hits or vis or bots or refs or dls):
        return
    s = _srv()
    with s._db_lock:
        c = s._conn
        for (day, path), n in hits.items():
            c.execute("INSERT INTO monitor_hits(day,path,n) VALUES(?,?,?) ON CONFLICT(day,path) DO UPDATE SET n=n+?", (day, path, n, n))
        c.executemany("INSERT OR IGNORE INTO monitor_visitors(day,vh) VALUES(?,?)", list(vis))
        for day, n in bots.items():
            c.execute("INSERT INTO monitor_bots(day,n) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET n=n+?", (day, n, n))
        for (day, host), n in refs.items():
            c.execute("INSERT INTO monitor_refs(day,host,n) VALUES(?,?,?) ON CONFLICT(day,host) DO UPDATE SET n=n+?", (day, host, n, n))
        c.executemany("INSERT INTO monitor_download(ts,path,vh,agent) VALUES(?,?,?,?)", dls)
        c.commit()
    _state["flushed"] += 1


def _writer():
    while True:
        time.sleep(15)
        try:
            _flush()
        except Exception as e:
            _state["last_error"] = "flush: %s" % str(e)[:120]


def _install():
    with _lock:
        if _state["installed"]:
            return True
        H = getattr(_srv(), "Handler", None)
        if H is None:
            return False
        if not getattr(H, "_monitor_patched", False):
            original = H.handle_one_request

            def handle_one_request(self):
                try:
                    original(self)
                finally:
                    _record(self)

            H.handle_one_request = handle_one_request
            H._monitor_patched = True
        if not _state["writer"]:
            _state["writer"] = True
            threading.Thread(target=_writer, name="monitor", daemon=True).start()
        _state["installed"] = True
        return True


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def _handler():
    f = inspect.currentframe()
    try:
        for _ in range(12):
            f = f.f_back
            if f is None:
                break
            h = f.f_locals.get("h") or f.f_locals.get("self")
            if h is not None and hasattr(h, "headers") and hasattr(h, "wfile"):
                return h
    finally:
        del f
    return None


def _is_admin():
    h = _handler()
    s = _srv()
    try:
        return bool(h is not None and s.check_admin(h))
    except Exception:
        return False


def _chain():
    now = time.time()
    if _cache["chain"] is None or now - _cache["chain_at"] > 300:
        try:
            v = _srv().verify_chain()
            _cache["chain"] = {"valid": v.get("valid"), "blocks": v.get("blocks"), "tip": v.get("tip"),
                               "checked_utc": _iso(now)}
        except Exception as e:
            _cache["chain"] = {"valid": None, "error": str(e)[:120]}
        _cache["chain_at"] = now
    return _cache["chain"]


def _mod_state(name):
    m = sys.modules.get("modules." + name) or sys.modules.get(name)
    if not m:
        return {"loaded": False}
    st = getattr(m, "_state", {}) or {}
    return {"loaded": True, "version": getattr(m, "VERSION", None), "last_error": st.get("last_error")}


def snapshot():
    try:
        _flush()
    except Exception:
        pass
    s = _srv()
    now = time.time()
    t0 = now - (now % 86400)
    d7 = now - 7 * 86400
    today = _day()
    days = [_day(now - i * 86400) for i in range(13, -1, -1)]

    # customers
    keys = _db("SELECT key,email,name,org,product,created,is_paid,plan_type,actions_used FROM api_keys ORDER BY created DESC")
    dev_by_key = dict(_db("SELECT api_key, COUNT(*) FROM device_seen GROUP BY api_key"))
    dec_by_key = {}
    last_by_key = {}
    try:
        for k, n, last in _db("SELECT api_key, COUNT(*), MAX(ts) FROM audit_log WHERE api_key IS NOT NULL AND api_key!='' GROUP BY api_key"):
            dec_by_key[k] = n
            last_by_key[k] = last
    except Exception:
        pass
    gw_by_kh = {}
    try:
        gw_by_kh = dict(_db("SELECT key_hash, COUNT(*) FROM gateway_call GROUP BY key_hash"))
    except Exception:
        pass
    pilot_keys = {}
    try:
        for k, paid_at in _db("SELECT api_key, paid_at FROM pilot_order WHERE status='paid'"):
            pilot_keys[k] = paid_at
    except Exception:
        pass
    ai_emails = set()
    try:
        ai_emails = {r[0] for r in _db("SELECT email_fp FROM mcp_agreement")}
    except Exception:
        pass

    def kh(k):
        return hashlib.sha256(("gw|" + k).encode()).hexdigest()[:24]

    customers = []
    mrr = 0.0
    trials_ending = 0
    for k, email, name, org, product, created, paid, plan, used in keys:
        devs = dev_by_key.get(k, 0)
        left = None if paid else int(max(0, (created or now) + TRIAL_DAYS * 86400 - now) // 86400)
        if paid:
            mrr += 0.5 * max(1, devs)
        elif left is not None and left <= 7:
            trials_ending += 1
        efp = hashlib.sha256((email or "").strip().lower().encode()).hexdigest()
        customers.append({"name": name or "", "email": email or "", "org": org or "", "product": product or "",
                          "joined_utc": _iso(created), "paid": bool(paid), "trial_days_left": left, "devices": devs,
                          "decisions": dec_by_key.get(k, 0), "last_active_utc": _iso(last_by_key.get(k)) if last_by_key.get(k) else None,
                          "gateway_calls": gw_by_kh.get(kh(k), 0), "pilot": bool(k in pilot_keys),
                          "via_ai": efp in ai_emails, "key_hint": (k[:10] + "…" + k[-4:]) if k else ""})

    def cnt(sql, a=()):
        return _q(sql, a, 0)

    kpi = {
        "signups_total": len(keys), "signups_today": sum(1 for c in keys if (c[5] or 0) >= t0),
        "signups_7d": sum(1 for c in keys if (c[5] or 0) >= d7), "paying": sum(1 for c in keys if c[6]),
        "trials_ending_7d": trials_ending, "mrr_gbp": round(mrr, 2),
        "devices_total": cnt("SELECT COUNT(*) FROM device_seen"),
        "devices_today": cnt("SELECT COUNT(*) FROM device_seen WHERE first_seen>=?", (t0,)),
        "decisions_total": cnt("SELECT COUNT(*) FROM audit_log"),
        "decisions_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=?", (t0,)),
        "customer_decisions_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=? AND api_key IS NOT NULL AND api_key!=''", (t0,)),
        "blocked_today": cnt("SELECT COUNT(*) FROM audit_log WHERE ts>=? AND result_json LIKE '%\"decision\": \"BLOCK\"%'", (t0,)),
        "visitors_today": cnt("SELECT COUNT(*) FROM monitor_visitors WHERE day=?", (today,)),
        "visitors_7d": cnt("SELECT COUNT(*) FROM monitor_visitors WHERE day>=?", (days[-7],)),
        "page_views_today": cnt("SELECT SUM(n) FROM monitor_hits WHERE day=?", (today,)),
        "bots_today": cnt("SELECT n FROM monitor_bots WHERE day=?", (today,)),
        "downloads_today": cnt("SELECT COUNT(*) FROM monitor_download WHERE ts>=?", (t0,)),
        "downloads_7d": cnt("SELECT COUNT(*) FROM monitor_download WHERE ts>=?", (d7,)),
        "gateway_calls_today": cnt("SELECT COUNT(*) FROM gateway_call WHERE ts>=?", (t0,)),
        "notary_today": cnt("SELECT COUNT(*) FROM notary_leaf WHERE submitted>=? AND who NOT IN ('codebase','humankeys')", (t0,)),
        "human_keys_total": cnt("SELECT COUNT(*) FROM humankeys_proof"),
        "accounts_by_ai": cnt("SELECT COUNT(*) FROM mcp_agreement"),
        "pilots_paid": cnt("SELECT COUNT(*) FROM pilot_order WHERE status='paid'"),
        "pilot_revenue_gbp": round(cnt("SELECT SUM(amount) FROM pilot_order WHERE status='paid'") / 100.0, 2),
        "wallet_topups_gbp": round(cnt("SELECT SUM(pence) FROM credit_payment WHERE status='paid'") / 100.0, 2),
        "messages_7d": cnt("SELECT COUNT(*) FROM contact_log WHERE ts>=?", (d7,)),
        "machine_calls_since_start": _state["machine_calls"],
    }

    # 14-day series
    def series(sql, keyfn=None):
        out = dict.fromkeys(days, 0)
        try:
            for d, n in _db(sql, (days[0],)):
                if d in out:
                    out[d] = n
        except Exception:
            pass
        return [out[d] for d in days]

    ser = {
        "days": days,
        "visitors": series("SELECT day, COUNT(*) FROM monitor_visitors WHERE day>=? GROUP BY day"),
        "signups": series("SELECT strftime('%Y-%m-%d', created, 'unixepoch'), COUNT(*) FROM api_keys WHERE strftime('%Y-%m-%d', created, 'unixepoch')>=? GROUP BY 1"),
        "decisions": series("SELECT strftime('%Y-%m-%d', ts, 'unixepoch'), COUNT(*) FROM audit_log WHERE strftime('%Y-%m-%d', ts, 'unixepoch')>=? GROUP BY 1"),
        "devices": series("SELECT strftime('%Y-%m-%d', first_seen, 'unixepoch'), COUNT(*) FROM device_seen WHERE strftime('%Y-%m-%d', first_seen, 'unixepoch')>=? GROUP BY 1"),
        "downloads": series("SELECT strftime('%Y-%m-%d', ts, 'unixepoch'), COUNT(*) FROM monitor_download WHERE strftime('%Y-%m-%d', ts, 'unixepoch')>=? GROUP BY 1"),
    }

    pages = [{"path": p, "views": n} for p, n in _safe("SELECT path, SUM(n) FROM monitor_hits WHERE day>=? GROUP BY path ORDER BY 2 DESC LIMIT 15", (days[-7],))]
    refs = [{"site": h, "visits": n} for h, n in _safe("SELECT host, SUM(n) FROM monitor_refs WHERE day>=? GROUP BY host ORDER BY 2 DESC LIMIT 12", (days[-7],))]
    downloads = [{"utc": _iso(t), "path": p, "visitor": v[:8], "agent": a} for t, p, v, a in
                 _safe("SELECT ts, path, vh, agent FROM monitor_download ORDER BY ts DESC LIMIT 60")]
    dl_top = [{"path": p, "count": n} for p, n in _safe("SELECT path, COUNT(*) FROM monitor_download GROUP BY path ORDER BY 2 DESC LIMIT 12")]
    email_by_key = {k[0]: k[1] for k in keys}
    devices = [{"utc": _iso(t), "device": (d or "")[:40], "customer": email_by_key.get(k, "?")} for k, d, t in
               _safe("SELECT api_key, device_id, first_seen FROM device_seen ORDER BY first_seen DESC LIMIT 60")]
    messages = [{"utc": _iso(t), "name": n, "email": e, "org": o, "message": (m or "")[:400]} for t, n, e, o, m in
                _safe("SELECT ts, name, email, org, message FROM contact_log ORDER BY ts DESC LIMIT 20")]
    pilots = [{"utc": _iso(c), "name": n, "email": e, "company": co, "status": st, "paid_utc": _iso(p) if p else None,
               "deliver_by_utc": _iso(p + 7 * 86400) if p else None, "amount_gbp": (a or 0) / 100.0} for c, n, e, co, st, p, a in
              _safe("SELECT created, name, email, company, status, paid_at, amount FROM pilot_order ORDER BY created DESC LIMIT 30")]

    # live feed
    feed = []
    for c in customers[:40]:
        feed.append((c["joined_utc"], "signup", "%s signed up%s" % (c["name"] or c["email"], " via an AI assistant" if c["via_ai"] else ""), c["org"] or c["product"]))
    for d in devices[:40]:
        feed.append((d["utc"], "device", "New device linked", "%s · %s" % (d["customer"], d["device"])))
    for d in downloads[:40]:
        feed.append((d["utc"], "download", "Downloaded %s" % d["path"], d["agent"][:40]))
    for m in messages[:10]:
        feed.append((m["utc"], "message", "Message from %s" % (m["name"] or m["email"]), m["message"][:90]))
    for p in pilots[:10]:
        if p["status"] == "paid":
            feed.append((p["paid_utc"], "money", "PILOT PAID £%.0f — %s" % (p["amount_gbp"], p["company"]), p["email"]))
        else:
            feed.append((p["utc"], "checkout", "Pilot checkout started — %s" % p["company"], p["email"]))
    for t, pv, mdl, dec in _safe("SELECT ts, provider, model, decision FROM gateway_call ORDER BY ts DESC LIMIT 20"):
        feed.append((_iso(t), "gateway", "Gateway call %s" % (dec or ""), "%s %s" % (pv, mdl or "")))
    for t, r in _safe("SELECT ts, result_json FROM audit_log WHERE result_json LIKE '%\"decision\": \"BLOCK\"%' ORDER BY id DESC LIMIT 10"):
        feed.append((_iso(t), "block", "Decision BLOCKED", ""))
    feed = [{"utc": a, "kind": b, "title": c, "detail": d} for a, b, c, d in sorted((f for f in feed if f[0]), reverse=True)[:80]]

    # health
    chain = _chain()
    btc = {}
    try:
        r = _db("SELECT MAX(chain_size), MAX(btc_height), MAX(confirmed_at) FROM notary_batch WHERE kind='chain' AND state='confirmed'", one=True)
        last_cp = _q("SELECT MAX(created) FROM notary_batch WHERE kind='chain'")
        btc = {"blocks_in_bitcoin": r[0] or 0, "latest_bitcoin_block": r[1], "last_confirmed_utc": _iso(r[2]) if r[2] else None,
               "last_checkpoint_utc": _iso(last_cp) if last_cp else None,
               "pending": cnt("SELECT COUNT(*) FROM notary_batch WHERE state IN ('new','pending')")}
    except Exception:
        pass
    mods = {n: _mod_state(n) for n in ("notary", "gateway", "pilot", "ratelimit", "humankeys", "mcp", "connect", "dossier",
                                        "heartbeat", "ots", "ainews", "brand", "homelink", "answers")}

    # alerts
    alerts = []
    if chain.get("valid") is False:
        alerts.append({"level": "critical", "text": "Chain verification FAILED — open the Chain tab now."})
    for p in pilots:
        if p["status"] == "paid" and p["paid_utc"]:
            due = datetime.strptime(p["deliver_by_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
            dleft = (due - now) / 86400
            if dleft > -30:
                alerts.append({"level": "money" if dleft > 2 else "serious",
                               "text": "Pilot for %s — deliver by %s (%s)" % (p["company"], p["deliver_by_utc"][:10],
                                                                            "%.0f days left" % dleft if dleft >= 0 else "OVERDUE")})
    if trials_ending:
        alerts.append({"level": "warning", "text": "%d trial%s end within 7 days — chase for a card." % (trials_ending, "" if trials_ending == 1 else "s")})
    if kpi["messages_7d"]:
        alerts.append({"level": "info", "text": "%d message%s in the last 7 days." % (kpi["messages_7d"], "" if kpi["messages_7d"] == 1 else "s")})
    if btc.get("last_confirmed_utc"):
        age = (now - datetime.strptime(btc["last_confirmed_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()) / 3600
        if age > 12:
            alerts.append({"level": "warning", "text": "No new Bitcoin confirmation for %.0f hours." % age})
    core = ("notary", "gateway", "pilot", "ratelimit", "humankeys", "mcp", "dossier", "heartbeat", "ots", "homelink")
    for n, m in mods.items():
        if n in core and m.get("loaded") and m.get("last_error"):
            alerts.append({"level": "warning", "text": "%s: %s" % (n, str(m["last_error"])[:120])})
    unloaded = [n for n in ("notary", "gateway", "pilot", "ratelimit", "homelink") if not mods[n]["loaded"]]
    if unloaded:
        alerts.append({"level": "serious", "text": "Not armed: %s — tap https://sebbi.pro/x/arm/status" % ", ".join(unloaded)})

    return {"generated_utc": _iso(now), "kpi": kpi, "series": ser, "customers": customers[:300], "devices": devices,
            "downloads": downloads, "downloads_top": dl_top, "pages": pages, "referrers": refs, "messages": messages,
            "pilots": pilots, "feed": feed, "alerts": alerts,
            "health": {"chain": chain, "bitcoin": btc, "modules": mods, "server_version": getattr(s, "VERSION", None)}}


def _safe(sql, args=()):
    try:
        return _db(sql, args)
    except Exception:
        return []


def handle(method, action, data, api_key, ctx):
    try:
        _setup()
        _install()
    except Exception as e:
        _state["last_error"] = "arm: %s" % str(e)[:120]
    if action in ("", "status"):
        return {"module": "monitor", "version": VERSION, "armed": _state["installed"], "recording": _state["writer"],
                "flushes": _state["flushed"], "last_error": _state["last_error"],
                "data": "GET /x/monitor/all with the admin login token"}, 200
    if action == "all":
        if not _is_admin():
            return {"error": "admin_only", "message": "Log in at https://sebbi.pro/admin"}, 401
        try:
            return snapshot(), 200
        except Exception as e:
            _state["last_error"] = "snapshot: %s" % str(e)[:150]
            return {"error": "snapshot_failed", "detail": str(e)[:200]}, 500
    return {"error": "unknown_action", "action": action}, 404
