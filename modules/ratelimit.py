"""
modules/ratelimit.py  v1.0.0  -  per-key limits sized for real traffic

    Arm:     https://sebbi.pro/x/arm/status
    Status:  https://sebbi.pro/x/ratelimit/status

server.py allows 60 decisions a minute and 1,000 an hour per API key. That
suits a trial; an app sending every AI call through the gateway passes it in
seconds. This replaces server.check_rate when the site arms - server.py is
not edited, and the same windows and lock are used, so nothing else changes:

    trial keys  300 a minute,   10,000 an hour
    paid keys   3,000 a minute, 200,000 an hour

Each figure can be changed without a deploy of code, through Railway
variables: RATE_TRIAL_MIN, RATE_TRIAL_HOUR, RATE_PAID_MIN, RATE_PAID_HOUR.
"""

import os
import sys
import threading
import time

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "")}


def _int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


LIMITS = {"trial": (_int("RATE_TRIAL_MIN", 300), _int("RATE_TRIAL_HOUR", 10000)),
          "paid": (_int("RATE_PAID_MIN", 3000), _int("RATE_PAID_HOUR", 200000))}
_paid_cache = {}
_state = {"installed": False, "original": None, "refused": 0, "last_error": None}
_lock = threading.Lock()


def _srv():
    m = sys.modules.get("__main__")
    if not hasattr(m, "get_bearer"):
        m = sys.modules.get("server")
    return m


def _is_paid(s, key):
    hit = _paid_cache.get(key)
    now = time.time()
    if hit and now - hit[1] < 60:
        return hit[0]
    paid = False
    try:
        ki = s.get_key(key)
        paid = bool(ki and ki[3])
    except Exception:
        pass
    if len(_paid_cache) > 20000:
        _paid_cache.clear()
    _paid_cache[key] = (paid, now)
    return paid


def _install():
    with _lock:
        if _state["installed"]:
            return True
        s = _srv()
        if s is None or not hasattr(s, "check_rate") or not hasattr(s, "_key_wins"):
            return False
        if getattr(s.check_rate, "_sebbi_ratelimit", False):
            _state["installed"] = True
            return True
        _state["original"] = s.check_rate

        def check_rate(key):
            per_min, per_hour = LIMITS["paid" if _is_paid(s, key) else "trial"]
            t = time.time()
            with s._key_lock:
                w = s._key_wins[key]
                while w["min"] and w["min"][0] < t - 60:
                    w["min"].popleft()
                while w["hour"] and w["hour"][0] < t - 3600:
                    w["hour"].popleft()
                if len(w["min"]) >= per_min:
                    _state["refused"] += 1
                    return False, "rate_limit_minute"
                if len(w["hour"]) >= per_hour:
                    _state["refused"] += 1
                    return False, "rate_limit_hour"
                w["min"].append(t)
                w["hour"].append(t)
                return True, None

        check_rate._sebbi_ratelimit = True
        s.check_rate = check_rate
        _state["installed"] = True
        return True


def handle(method, action, data, api_key, ctx):
    try:
        _install()
    except Exception as e:
        _state["last_error"] = str(e)[:200]
    return {"module": "ratelimit", "version": VERSION, "armed": _state["installed"],
            "per_key": {"trial": {"per_minute": LIMITS["trial"][0], "per_hour": LIMITS["trial"][1]},
                        "paid": {"per_minute": LIMITS["paid"][0], "per_hour": LIMITS["paid"][1]}},
            "was": {"per_minute": 60, "per_hour": 1000},
            "refused_since_start": _state["refused"], "last_error": _state["last_error"]}, 200
