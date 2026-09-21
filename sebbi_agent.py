#!/usr/bin/env python3
"""
sebbi_agent.py  -  give any AI agent an Agent Passport in one line
==================================================================

    from sebbi_agent import needs_passport

    @needs_passport("payments.send", audience="shop.example.com",
                    grant="g_your_grant_id", params=["amount"])
    def pay(amount, passport=None):
        # passport is a signed token. Send it with the request:
        #   headers = {"Agent-Passport": passport}
        ...

    pay(amount=20)

Before the function runs, sebbi.pro traces the agent's authority back to the
human who granted it and issues a passport for exactly this action, at this
site, with these parameters. If sebbi.pro refuses, the function never runs and
PassportRefused is raised with the reasons and a link to the sealed refusal.

Fails closed: if sebbi.pro cannot be reached, the action does not happen.

Needs your sebbi.pro API key in the SEBBI_KEY environment variable.
Standard library only. One file. Python 3.8+.

Command line:
    python sebbi_agent.py request --grant G --action payments.send \\
        --audience shop.example.com --params '{"amount": 20}'
"""

import functools
import inspect
import json
import os
import sys
import threading
import urllib.error
import urllib.request

__version__ = "1.0.0"

BASE = os.environ.get("SEBBI_BASE", "https://sebbi.pro").rstrip("/")
HEADER = "Agent-Passport"
TIMEOUT = 10

_local = threading.local()


class PassportError(Exception):
    """Base class. The action did not happen."""


class PassportRefused(PassportError):
    """sebbi.pro evaluated the request and did not issue a passport."""

    def __init__(self, verdict, reasons, proof=None):
        self.verdict, self.reasons, self.proof = verdict, reasons, proof
        msg = "%s: %s" % (verdict, "; ".join(reasons) if reasons else "no reason given")
        if proof:
            msg += " (sealed refusal: %s)" % proof
        super().__init__(msg)


class PassportUnavailable(PassportError):
    """sebbi.pro could not be reached or answered with an error. Fails closed."""


def _post(path, body, key):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key,
                 "User-Agent": "sebbi-agent/" + __version__})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode("utf-8"))
        except Exception:
            detail = {"error": "http_%d" % e.code}
        raise PassportUnavailable("sebbi.pro answered %d: %s" % (e.code, detail))
    except Exception as e:
        raise PassportUnavailable("could not reach sebbi.pro: %s" % e)


def request_passport(grant, action, audience, params=None, purpose_tag=None, key=None):
    """Ask sebbi.pro for a passport. Returns the token string or raises."""
    key = key or os.environ.get("SEBBI_KEY", "")
    if not key:
        raise PassportUnavailable("set SEBBI_KEY to your sebbi.pro API key")
    res = _post("/x/passport/issue", {"grant": grant, "action": action,
                                     "audience": audience, "params": params or {},
                                     "purpose_tag": purpose_tag}, key)
    if res.get("issued"):
        return res["passport"]
    if "verdict" in res:
        raise PassportRefused(res["verdict"], res.get("reasons", []),
                              res.get("proof_of_refusal"))
    raise PassportUnavailable("unexpected answer: %s" % res)


def current_passport():
    """The passport for the action currently running inside @needs_passport."""
    return getattr(_local, "token", None)


def headers(token=None):
    """HTTP headers to send with the action."""
    return {HEADER: token or current_passport() or ""}


def needs_passport(action, audience, grant=None, params=None, purpose_tag=None, key=None):
    """Decorator. The wrapped function runs only if a passport is issued.

    params: list of argument names whose values define the action, e.g.
            ["amount", "currency"]. The site must redeem with the same values,
            so a passport for 20 cannot be spent on 49.
    grant:  the grant id. Can also be passed at call time as grant=...
    The token is handed to the function as passport=... if it accepts that
    argument, and is always available through current_passport().
    """
    names = list(params or [])

    def wrap(fn):
        sig = inspect.signature(fn)
        takes_passport = "passport" in sig.parameters

        @functools.wraps(fn)
        def inner(*args, **kwargs):
            g = kwargs.pop("grant", None) if "grant" not in sig.parameters else kwargs.get("grant")
            g = g or grant or os.environ.get("SEBBI_GRANT")
            if not g:
                raise PassportUnavailable("no grant id: pass grant=... or set SEBBI_GRANT")
            bound = sig.bind_partial(*args, **kwargs)
            bound.apply_defaults()
            p = {n: bound.arguments[n] for n in names if n in bound.arguments}
            token = request_passport(g, action, audience, p, purpose_tag, key)
            if takes_passport:
                kwargs["passport"] = token
            _local.token = token
            try:
                return fn(*args, **kwargs)
            finally:
                _local.token = None
        return inner
    return wrap


def _cli(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="sebbi_agent")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("request")
    r.add_argument("--grant", required=True)
    r.add_argument("--action", required=True)
    r.add_argument("--audience", required=True)
    r.add_argument("--params", default="{}")
    r.add_argument("--purpose", default=None)
    a = ap.parse_args(argv)
    if a.cmd != "request":
        ap.print_help()
        return 2
    try:
        print(request_passport(a.grant, a.action, a.audience, json.loads(a.params), a.purpose))
        return 0
    except PassportError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
