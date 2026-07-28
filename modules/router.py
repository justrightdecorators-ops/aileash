import importlib, sys

_c = {}


def _srv():
    m = sys.modules.get("__main__")
    if hasattr(m, "get_bearer"):
        return m
    return sys.modules.get("server")


def _load(name):
    m = _c.get(name)
    if m is None:
        m = importlib.import_module("modules." + name)
        _c[name] = m
    return m


def route(h, path, data):
    """Dispatch /x/<module>/<action>.

    A module may expose PUBLIC = {("GET","attest"), ...} listing routes that
    need no API key. Everything not listed requires a Bearer key, so the
    default stays closed and a module has to opt a route open deliberately.
    """
    try:
        s = _srv()
        if s is None:
            return {"error": "server_not_found"}, 500

        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path",
                    "expected": "/x/<module>/<action>"}, 404
        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""

        if isinstance(data, dict) and data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}

        try:
            m = _load(name)
        except Exception:
            return {"error": "unknown_module", "module": name}, 404
        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle"}, 500

        method = h.command
        public = getattr(m, "PUBLIC", set())
        is_public = (method, act) in public or (method, "") in public

        a = s.get_bearer(h)
        if is_public:
            # public routes still accept a key if one is sent, they just
            # do not require one. api_key is None when absent.
            if a and not s.get_key(a):
                a = None
        else:
            if not a or not s.get_key(a):
                return {"error": "invalid_api_key"}, 401

        ctx = {"conn": s._conn, "lock": s._db_lock,
               "seal": s.seal, "get_key": s.get_key}
        return m.handle(method, act, data, a, ctx)

    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500
