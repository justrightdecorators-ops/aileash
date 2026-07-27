import importlib, server

_c = {}


def route(h, path, data):
    """Dispatches /x/<module>/<action> to modules/<module>.py

    Every module exposes one function:

        def handle(method, action, data, api_key, ctx):
            return payload_dict, status_code

    ctx gives the module the server's shared objects:
        ctx["conn"]    - the sqlite connection
        ctx["lock"]    - the db lock
        ctx["seal"]    - seal(event, result, ts, api_key) -> (hash, index, seq)
        ctx["get_key"] - api key lookup

    server.py never needs changing again. New feature = new file in modules/.
    """
    try:
        a = server.get_bearer(h)
        if not a or not server.get_key(a):
            return {"error": "invalid_api_key"}, 401

        parts = [x for x in path.strip("/").split("/") if x]
        if len(parts) < 2:
            return {"error": "bad_path",
                    "expected": "/x/<module>/<action>"}, 404

        name = parts[1]
        act = parts[2] if len(parts) > 2 else ""

        # GET query strings arrive as {"k": ["v"]} - flatten them
        if isinstance(data, dict) and data and isinstance(list(data.values())[0], list):
            data = {k: v[0] for k, v in data.items()}

        try:
            m = _c.get(name) or importlib.import_module("modules." + name)
            _c[name] = m
        except Exception:
            return {"error": "unknown_module", "module": name}, 404

        if not hasattr(m, "handle"):
            return {"error": "module_has_no_handle", "module": name}, 500

        ctx = {"conn": server._conn,
               "lock": server._db_lock,
               "seal": server.seal,
               "get_key": server.get_key}

        return m.handle(h.command, act, data, a, ctx)

    except Exception as e:
        print("ROUTER ERR: " + str(e), flush=True)
        return {"error": "router_failed", "detail": str(e)}, 500
