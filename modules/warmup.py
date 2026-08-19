"""
modules/warmup.py  v1.0  -  arm every page module in one request

THE PROBLEM THIS ENDS
---------------------
console.py, packconsole.py, peerconsole.py, selfcheck.py and the rest all
install their page by patching do_GET at runtime, and that only happens the
first time their handle() runs. So after every deploy the pages 404 until
somebody happens to hit each module's /x/ route.

Worse, most of those modules only make `status` public. A keyless request to
/x/console/ is rejected by the router before the module is ever imported, so
the obvious way of arming them does not work and looks like a broken site
instead of a cold one.

WHAT THIS DOES
--------------
One public route that imports each page module and calls its handle() once,
which is exactly what installs the patch. Every page comes back in a single
request, with no key.

    GET /x/warmup/all       arm everything, report what happened
    GET /x/warmup/status    what is armed right now, arms nothing
    GET /x/warmup/spec      what this is

POINT RAILWAY AT IT
-------------------
Set the healthcheck path to:

    /x/warmup/all

Railway calls it after every deploy, so the site is armed before anyone
opens it. It always returns 200 as long as the process is up - a module
that fails to arm is reported in the body rather than failing the
healthcheck, because one broken page should not roll back a good deploy.

SAFE TO RUN REPEATEDLY
----------------------
Every module guards its own patch with a `_patched` flag, so a second call
is a no-op. Call it every minute if you like.

ADDING A MODULE
---------------
Put its name in PAGE_MODULES. Nothing else. If the module is not deployed
it is reported as missing and the others still arm.
"""

import importlib
import sys
import time
import traceback

VERSION = "1.0"

PUBLIC = {("GET", "all"), ("GET", "status"), ("GET", "spec"), ("GET", "")}

# Modules that serve an HTML page by patching do_GET at runtime.
# Name only - no path, no .py.
PAGE_MODULES = [
    "console",
    "packconsole",
    "peerconsole",
    "selfcheck",
    "savings",
    "standard",
    "network",
    "demo",
]

# Import prefixes tried in order. Different deployments load modules
# differently and guessing once and failing is how you get a 404 you
# cannot explain.
_PREFIXES = ("modules.", "", "aileash.modules.")

_last_run = {"at": None, "results": None}


def _find(name):
    """Return an already-imported module, or import it. (module, how) or (None, why)."""
    for pre in _PREFIXES:
        mod = sys.modules.get(pre + name)
        if mod is not None:
            return mod, "already imported as " + pre + name
    errors = []
    for pre in _PREFIXES:
        try:
            return importlib.import_module(pre + name), "imported as " + pre + name
        except ImportError as exc:
            errors.append(pre + name + ": " + str(exc))
        except Exception as exc:
            # A real error inside the module - a syntax error, a bad import
            # of its own. Worth reporting properly rather than as "missing",
            # because those look identical from outside and cost hours.
            return None, "FAILED TO LOAD (%s): %s" % (
                type(exc).__name__, str(exc)[:200])
    return None, "not found (" + "; ".join(errors[:1]) + ")"


def _arm(name, ctx):
    """Import a page module and call handle() once, which installs its patch."""
    mod, how = _find(name)
    if mod is None:
        return {"module": name, "armed": False, "detail": how}

    fn = getattr(mod, "handle", None)
    if not callable(fn):
        return {"module": name, "armed": False,
                "detail": "loaded but has no handle()"}

    try:
        body, status = fn("GET", "status", {}, None, ctx)
    except Exception as exc:
        return {"module": name, "armed": False,
                "detail": "handle() raised %s: %s" % (
                    type(exc).__name__, str(exc)[:200]),
                "traceback": traceback.format_exc(limit=3).splitlines()[-3:]}

    body = body if isinstance(body, dict) else {}
    armed = bool(body.get("installed", True))
    out = {"module": name, "armed": armed, "http": status, "load": how}
    for k in ("page", "install_result", "version"):
        if k in body:
            out[k] = body[k]
    if not armed:
        out["detail"] = body.get("install_result") or "reported not installed"
    return out


def _status_only(ctx):
    """What is armed, without arming anything. Read-only."""
    rows = []
    for name in PAGE_MODULES:
        found = None
        for pre in _PREFIXES:
            if (pre + name) in sys.modules:
                found = sys.modules[pre + name]
                break
        if found is None:
            rows.append({"module": name, "loaded": False, "armed": False})
            continue
        flag = getattr(found, "_patched", None)
        armed = bool(flag[0]) if isinstance(flag, list) and flag else None
        rows.append({"module": name, "loaded": True, "armed": armed,
                     "page": getattr(found, "PAGE_PATHS", [None])[0]
                             if hasattr(found, "PAGE_PATHS") else None})
    return rows


def handle(method, action, data, api_key, ctx):
    action = (action or "").strip().lower()

    if method != "GET":
        return {"error": "unknown_action", "action": action,
                "GET": ["all", "status", "spec"]}, 404

    if action == "spec":
        return {
            "module": "warmup",
            "version": VERSION,
            "what_it_is": (
                "Page modules install their route by patching do_GET the "
                "first time they run, so every deploy leaves those pages "
                "404 until something touches each one. This touches all of "
                "them in one public request."),
            "routes": {
                "/x/warmup/all": "arm every page module, report each",
                "/x/warmup/status": "what is armed now, arms nothing",
                "/x/warmup/spec": "this",
            },
            "railway_healthcheck_path": "/x/warmup/all",
            "modules": list(PAGE_MODULES),
            "safe_to_repeat": True,
            "note": ("Always returns 200 while the process is up. A module "
                     "that fails to arm is reported in the body, because one "
                     "bad page should not roll back a good deploy."),
        }, 200

    if action == "status":
        return {"armed_now": _status_only(ctx),
                "last_warmup": _last_run["at"],
                "note": "Read-only. Call /x/warmup/all to actually arm."}, 200

    # "" or "all"
    t0 = time.time()
    results = [_arm(name, ctx) for name in PAGE_MODULES]
    _last_run["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _last_run["results"] = results

    armed = [r["module"] for r in results if r.get("armed")]
    failed = [r for r in results if not r.get("armed")]

    for r in failed:
        print("WARMUP: %s did not arm - %s"
              % (r["module"], r.get("detail", "?")), flush=True)
    print("WARMUP: %d/%d armed in %.0fms"
          % (len(armed), len(results), (time.time() - t0) * 1000), flush=True)

    return {
        "ok": True,
        "armed": len(armed),
        "of": len(results),
        "took_ms": round((time.time() - t0) * 1000, 1),
        "pages_ready": [r.get("page") for r in results
                        if r.get("armed") and r.get("page")],
        "results": results,
        "at": _last_run["at"],
        "note": ("A module listed as not armed is either not deployed or "
                 "raised on load - the detail says which. The rest still "
                 "armed."),
    }, 200
