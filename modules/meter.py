"""
modules/meter.py  v1.0.0
The 50p device meter, done per device per month - without touching server.py.

Armed by https://sebbi.pro/x/meter/status after each deploy, it swaps these
functions inside the running server for new versions (same names, same
callers, nothing in server.py edited):

  record_device(api_key, device_id)
      Counts each distinct device a key sends in a calendar month (UTC), once,
      however many decisions it makes. Resets every month. Reading the count
      is a single-row lookup, so it holds at millions of devices per key.
      The engine (/api/govern) and the plug-in log (public_proof_adapter.py)
      both call this, so one central server acting for 20 million phones is
      billed for 20 million devices.

  device_count(api_key)
      What the key is billed for: the larger of last month's full count and
      this month so far. Growth is billed straight away; a customer who
      shrinks pays less the month after. Used by the trial-end checkout,
      /api/usage and the trial-expired answers.

  sync_stripe_quantities()
      The existing 6-hourly Stripe job now sets each paying subscription to
      device_count() - up or down - so every renewal charges 50p for each
      device actually used.

On first arming, each key's existing all-time device count is carried into
last month, so nobody's bill drops while the monthly count builds up.

Watch for keys stamping one device id on a whole network:
    https://sebbi.pro/admin/meter      (your admin login)
Public summary (no keys shown):
    https://sebbi.pro/x/meter/status
"""

import json
import sys
import threading
import time
from collections import defaultdict

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}
RATE_GBP = 0.50
FLAG_EVENTS_PER_DEVICE = 10000
CACHE_MAX = 500000

_srv = None
_armed = False
_patched_http = False
_cache = {}
_lock = threading.Lock()
_events = defaultdict(int)
_orig = {}


def _month(ts=None):
    return time.strftime("%Y-%m", time.gmtime(ts if ts is not None else time.time()))


def _prev_month(ts=None):
    t = time.gmtime(ts if ts is not None else time.time())
    y, m = t.tm_year, t.tm_mon - 1
    if m == 0:
        y, m = y - 1, 12
    return "%04d-%02d" % (y, m)


def _find_server():
    for name in ("__main__", "server"):
        m = sys.modules.get(name)
        if m is not None and hasattr(m, "record_device") and hasattr(m, "_conn") and hasattr(m, "_db_lock"):
            return m
    return None


# ---------------------------------------------------------------- the meter

def _setup(s):
    with s._db_lock:
        c = s._conn
        c.execute("CREATE TABLE IF NOT EXISTS device_month(api_key TEXT,month TEXT,device_id TEXT,first_seen REAL,"
                  "PRIMARY KEY(api_key,month,device_id)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS device_month_count(api_key TEXT,month TEXT,n INTEGER DEFAULT 0,"
                  "PRIMARY KEY(api_key,month)) WITHOUT ROWID")
        c.execute("CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY,v TEXT)")
        if not c.execute("SELECT 1 FROM config WHERE k='meter_v2_seeded'").fetchone():
            c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) "
                      "SELECT api_key,?,COUNT(*) FROM device_seen GROUP BY api_key", (_prev_month(),))
            c.execute("INSERT OR REPLACE INTO config(k,v) VALUES('meter_v2_seeded',?)", (str(time.time()),))
        c.commit()


def month_count(api_key, month=None):
    s = _srv
    with s._db_lock:
        try:
            r = s._conn.execute("SELECT n FROM device_month_count WHERE api_key=? AND month=?",
                                (api_key, month or _month())).fetchone()
            return r[0] if r else 0
        except Exception:
            return 0


def device_count(api_key):
    """Billable devices: the larger of last month's full count and this month so far."""
    return max(month_count(api_key, _prev_month()), month_count(api_key))


def record_device(api_key, device_id):
    """Count device_id on api_key for this calendar month. Returns the billable count."""
    if not api_key or not device_id:
        return None
    s = _srv
    device_id = str(device_id)[:200]
    mon = _month()
    ck = (api_key, mon, device_id)
    with _lock:
        _events[(api_key, mon)] += 1
        hit = ck in _cache
    if not hit:
        with s._db_lock:
            try:
                c = s._conn
                cur = c.execute("INSERT OR IGNORE INTO device_month(api_key,month,device_id,first_seen) VALUES(?,?,?,?)",
                                (api_key, mon, device_id, time.time()))
                if cur.rowcount == 1:
                    c.execute("INSERT OR IGNORE INTO device_month_count(api_key,month,n) VALUES(?,?,0)", (api_key, mon))
                    c.execute("UPDATE device_month_count SET n=n+1 WHERE api_key=? AND month=?", (api_key, mon))
                    c.execute("INSERT OR IGNORE INTO device_seen(api_key,device_id,first_seen) VALUES(?,?,?)",
                              (api_key, device_id, time.time()))
                c.commit()
            except Exception as e:
                try:
                    s._conn.rollback()
                except Exception:
                    pass
                print("meter record_device err:" + str(e), flush=True)
                return None
        with _lock:
            if len(_cache) >= CACHE_MAX:
                _cache.clear()
            _cache[ck] = 1
    return device_count(api_key)


def sync_stripe_quantities():
    """Set each paying subscription's quantity to the billable device count, up or down."""
    s = _srv
    if not getattr(s, "STRIPE_SECRET", ""):
        print("QSYNC skip: no STRIPE_SECRET", flush=True)
        return
    with s._db_lock:
        rows = s._conn.execute("SELECT key,email,stripe_sub FROM api_keys WHERE is_paid=1 AND active=1 "
                               "AND stripe_sub!=''").fetchall()
    for key, email, sub_id in rows:
        try:
            n = device_count(key)
            if not n:
                continue
            sub = s.stripe_call("GET", "/subscriptions/" + sub_id)
            if not sub or "items" not in sub:
                print("QSYNC no sub for " + email, flush=True)
                continue
            items = sub["items"].get("data", [])
            if not items:
                continue
            item = items[0]
            current = int(item.get("quantity", 0) or 0)
            if n != current:
                r = s.stripe_call("POST", "/subscription_items/" + item["id"],
                                  {"quantity": str(n), "proration_behavior": "none"})
                if r and "id" in r:
                    print("QSYNC " + email + ": " + str(current) + " -> " + str(n) + " devices", flush=True)
                else:
                    print("QSYNC FAIL " + email, flush=True)
        except Exception as e:
            print("QSYNC ERR " + email + ": " + str(e), flush=True)


def watch(limit=200):
    mon = _month()
    with _lock:
        ev = [(k, n) for (k, m), n in _events.items() if m == mon]
    out = []
    for k, n in ev:
        d = month_count(k) or 1
        out.append({"key_prefix": k[:12], "events_this_month": n, "devices_this_month": d,
                    "events_per_device": round(n / float(d), 1), "flag": n / float(d) >= FLAG_EVENTS_PER_DEVICE})
    out.sort(key=lambda x: -x["events_per_device"])
    return out[:limit]


# ---------------------------------------------------------------- arming

def _arm():
    global _srv, _armed
    s = _find_server()
    if s is None:
        return False
    _srv = s
    _setup(s)
    if not _armed:
        for name in ("record_device", "device_count", "sync_stripe_quantities"):
            _orig.setdefault(name, getattr(s, name, None))
        s.record_device = record_device
        s.device_count = device_count
        s.sync_stripe_quantities = sync_stripe_quantities
        _armed = True
    return True


def _find_handler_class(ctx):
    if isinstance(ctx, dict):
        for k in ("handler_class", "handler", "Handler", "h", "request_handler"):
            v = ctx.get(k)
            if v is None:
                continue
            cls = v if isinstance(v, type) else type(v)
            if hasattr(cls, "do_GET"):
                return cls
    f = sys._getframe()
    while f is not None:
        o = f.f_locals.get("self")
        if o is not None and hasattr(type(o), "do_GET") and hasattr(o, "wfile"):
            return type(o)
        f = f.f_back
    return None


def _install_http(ctx):
    """Serve /admin/meter behind the server's own admin login."""
    global _patched_http
    if _patched_http:
        return True
    cls = _find_handler_class(ctx)
    if cls is None:
        return False
    if getattr(cls, "_meter_patched", False):
        _patched_http = True
        return True
    og = cls.do_GET

    def do_GET(self):
        if self.path.split("?")[0].rstrip("/") == "/admin/meter":
            ok = False
            try:
                ok = bool(_srv and _srv.check_admin(self))
            except Exception:
                ok = False
            body = json.dumps({"error": "unauthorized"} if not ok else
                              {"month": _month(), "rate_per_device_gbp": RATE_GBP, "keys": watch(),
                               "flag_rule": "%d or more events per device this month - check the key is sending "
                                            "real device ids" % FLAG_EVENTS_PER_DEVICE}).encode("utf-8")
            self.send_response(200 if ok else 401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        return og(self)

    cls.do_GET = do_GET
    cls._meter_patched = True
    _patched_http = True
    return True


def handle(method, action, data, api_key, ctx):
    armed = _arm()
    http = _install_http(ctx)
    flags = [w for w in watch() if w["flag"]] if armed else []
    return ({"module": "meter", "version": VERSION, "armed": armed and http,
             "month": _month(), "rate_per_device_gbp": RATE_GBP,
             "rule": "50p per distinct device per calendar month; billed on the larger of last month and this month so far",
             "keys_metered_this_month": len(watch()) if armed else 0,
             "keys_flagged": len(flags),
             "stripe_sync": "every 6 hours, follows the meter up and down"}, 200)
