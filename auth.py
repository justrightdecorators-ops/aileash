import hashlib
import time

_keys = {}

def generate_key(email, plan="free"):
    raw = email + str(time.time()) + "aileash_secret_2026"
    key = "al_" + hashlib.sha256(raw.encode()).hexdigest()[:32]
    _keys[key] = {"email": email, "plan": plan, "created": time.time()}
    return key

def validate_key(key):
    return _keys.get(key)

def upgrade_key(key):
    if key in _keys:
        _keys[key]["plan"] = "paid"
        return True
    return False

def get_plan(key):
    user = _keys.get(key)
    if not user:
        return None
    return user.get("plan", "free")

def total_keys():
    return len(_keys)

def total_paid():
    return sum(1 for u in _keys.values() if u.get("plan") == "paid")
