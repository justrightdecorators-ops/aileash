import importlib, sys

_c = {}


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def route(h, path, data):
    try:
        s = _srv()
        if s is None:
            return {"error": "server_not_found"}, 500
        a = s.get_bearer(h)
        if not a or not s.get_key(a):
            return {"error": "invalid_api_key"}, 401
        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path"}, 404
        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""
        if data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}
        try:
            m = _c.get(name) or importlib.import_module("modules." + name)
            _c[name] = m
        except Exception:
            return {"error": "unknown_module", "module": name}, 404
        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle"}, 500
        ctx = {"conn": s._conn, "lock": s._db_lock, "seal": s.seal, "get_key": s.get_key}
        return m.handle(h.command, act, data, a, ctx)
    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500
