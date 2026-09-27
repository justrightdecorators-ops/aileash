"""
modules/arm.py  v1.0.0
One tap arms everything:  https://sebbi.pro/x/arm/status

Every Railway deploy clears the page hooks that modules add. This finds every
module in the modules folder by itself - including any added later, so it
never needs updating - and arms each one in the right order:

    meter first (so the device meter is counting straight away),
    everything else,
    homelink and earnpage last (they wrap the homepage).

It answers with each module's name, version and whether it armed, so one
look tells you the whole site is up. A module that fails is reported and
skipped; it never stops the others.
"""

import importlib
import os
import time

VERSION = "1.0.0"
PUBLIC = {("GET", "status"), ("GET", "spec")}

FIRST = ["meter"]
LAST = ["homelink", "earnpage"]
SKIP = {"arm", "router", "armall", "__init__"}


def _names():
    here = os.path.dirname(os.path.abspath(__file__))
    found = sorted(f[:-3] for f in os.listdir(here)
                   if f.endswith(".py") and not f.startswith("_") and f[:-3] not in SKIP)
    middle = [n for n in found if n not in FIRST and n not in LAST]
    return [n for n in FIRST if n in found] + middle + [n for n in LAST if n in found]


def _load(name):
    pkg = __package__ or ""
    return importlib.import_module(pkg + "." + name if pkg else name)


def handle(method, action, data, api_key, ctx):
    started = time.time()
    results, ok, failed = [], 0, 0
    for name in _names():
        entry = {"module": name}
        try:
            mod = _load(name)
            fn = getattr(mod, "handle", None)
            if not callable(fn):
                entry["armed"] = None
                entry["note"] = "no status route"
            else:
                out = fn("GET", "status", {}, None, ctx)
                body = out[0] if isinstance(out, tuple) else out
                body = body if isinstance(body, dict) else {}
                entry["version"] = body.get("version")
                entry["armed"] = body.get("armed", True)
            if entry.get("armed") is False:
                failed += 1
            else:
                ok += 1
        except Exception as e:
            entry["armed"] = False
            entry["error"] = str(e)[:160]
            failed += 1
        results.append(entry)
    return ({"module": "arm", "version": VERSION, "armed": failed == 0,
             "modules_armed": ok, "modules_failed": failed,
             "seconds": round(time.time() - started, 2),
             "results": results}, 200)
