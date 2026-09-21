"""
modules/armall.py  v1.0.0
One tap arms every page module after a deploy.

    GET /x/armall/status

Railway restarts the server on every deploy, and every page module (the ones
that serve their own URL through a do_GET patch - /passport, /map, /witness,
the homepage button, the consoles...) goes quiet until its status route is
hit. This module finds every file in modules/ that installs a do_GET patch
and arms it, in one request, and reports what it armed.

It only touches page modules, and only by calling their own status route -
exactly what tapping each one by hand does. Nothing else in modules/ is run.
New page modules are picked up automatically: no list to maintain.

Point Railway's healthcheck at /x/armall/status and every deploy arms itself.
"""

import importlib.util
import os
import sys

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.splitext(os.path.basename(__file__))[0]


def _is_page_module(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except Exception:
        return False
    return ".do_GET = " in src and "def handle(" in src


def _load(name, path):
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", "") or ""
        if f and os.path.abspath(f) == path and hasattr(m, "handle"):
            return m
    spec = importlib.util.spec_from_file_location("armall_" + name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def handle(method, action, data, api_key, ctx):
    armed, failed = {}, {}
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        name = fn[:-3]
        if name == SELF:
            continue
        path = os.path.join(HERE, fn)
        if not _is_page_module(path):
            continue
        try:
            mod = _load(name, path)
            res = mod.handle("GET", "status", {}, None, ctx)
            body = res[0] if isinstance(res, tuple) else res
            ok = body.get("armed", True) if isinstance(body, dict) else True
            (armed if ok else failed)[name] = (body.get("serves") if isinstance(body, dict)
                                               else None) or "armed"
        except Exception as e:
            failed[name] = str(e)[:160]
    return {"module": "armall", "version": VERSION,
            "armed": armed, "failed": failed,
            "count": len(armed),
            "all_ok": not failed,
            "tip": "Set Railway's healthcheck path to /x/armall/status and deploys arm "
                   "themselves."}, 200
