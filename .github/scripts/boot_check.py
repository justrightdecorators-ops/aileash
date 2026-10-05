#!/usr/bin/env python3
"""
boot_check.py - start the real site on a throwaway database and check it works.

Run by .github/workflows/checks.yml on every push. It answers one question
before anybody opens the live site: does this commit boot, arm every module,
and serve its pages?

SAFETY FIRST
------------
Some modules start background jobs that talk to the outside world - peer
witnessing, timestamping, archiving. A test copy must never do that: it would
hand real peers a fake chain under our name. So this script refuses to run
unless it is inside a sandbox with NO outside network (the workflow starts it
with `unshare -n`). If it can reach the internet, it stops before booting.

It never touches the live site, the live database or any secret.
"""
import fcntl
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PORT = 8765
BASE = "http://127.0.0.1:%d" % PORT

# Pages and routes the live site promises. Each must answer 200 on a fresh boot.
PAGES = [
    "/",
    "/api/health",
    "/api/verify-chain",
    "/api/stats",
    "/api/anchor-status",
    "/x/arm/status",
    "/x/consistency/root",
    "/x/roster/list",
    "/x/ots/status",
    "/x/witness/tip",
    "/x/replay/fingerprint",
    "/x/continuity/spec",
    "/x/tokensaver/spec",
    "/.well-known/ordering-test.json",
    "/self-check",
    "/witness",
    "/passport",
    "/pack",
    "/whitepaper",
    "/developers",
    "/tokensaver",
    "/scan",
    "/verify-authority.py",
    "/dossier",
    "/x/dossier/status",
    "/x/dossier/spec",
    "/keys",
    "/k/",
    "/x/humankeys/status",
    "/x/humankeys/spec",
    "/x/humankeys/challenge",
    "/x/brand/status",
    "/connect",
    "/build",
    "/x/connect/status",
]


def loopback_up():
    """Bring the loopback interface up inside a fresh network namespace."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        flags = 0x1 | 0x8 | 0x40  # UP | LOOPBACK | RUNNING
        fcntl.ioctl(s, 0x8914, struct.pack("16sH14s", b"lo", flags, b""))
        s.close()
    except Exception as e:
        print("note: could not raise loopback (%s) - may already be up" % e)


def outside_reachable():
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            socket.create_connection((host, 443), timeout=3).close()
            return True
        except OSError:
            pass
    return False


def get(path, timeout=30):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "boot-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode()


def main():
    loopback_up()
    if outside_reachable():
        print("STOP: this sandbox can reach the internet. Refusing to boot a test")
        print("copy that could talk to real peers. Run it under `unshare -n`.")
        return 2

    work = tempfile.mkdtemp(prefix="sebbi-boot-")
    env = dict(os.environ)
    env.update({
        "PORT": str(PORT),
        "DB_PATH": os.path.join(work, "aileash.db"),
        "ANCHOR_DIR": os.path.join(work, "anchors"),
        "OTS_AUTO_UPGRADE": "0",
        "HOST": BASE,
    })
    for k in ("STRIPE_SECRET", "STRIPE_WEBHOOK_SECRET", "BREVO_API_KEY",
              "ADMIN_PASSWORD", "LICENCE_SECRET"):
        env.pop(k, None)

    log_path = os.path.join(work, "server.log")
    log = open(log_path, "w")
    proc = subprocess.Popen([sys.executable, "server.py"], cwd=ROOT, env=env,
                            stdout=log, stderr=subprocess.STDOUT)
    failures = []
    try:
        started = time.time()
        while time.time() - started < 45:
            if proc.poll() is not None:
                failures.append("server.py exited during boot (code %s)" % proc.returncode)
                break
            code, _ = get("/api/health", timeout=3)
            if code == 200:
                break
            time.sleep(1)
        else:
            failures.append("server did not answer /api/health within 45s")

        if not failures:
            print("booted in %.1fs" % (time.time() - started))
            code, body = get("/x/arm/status", timeout=120)
            try:
                arm = json.loads(body)
            except Exception:
                arm = {}
            if code != 200 or not arm:
                failures.append("/x/arm/status answered %s" % code)
            else:
                print("armed %s modules, %s failed, in %ss" % (
                    arm.get("modules_armed"), arm.get("modules_failed"), arm.get("seconds")))
                for r in arm.get("results", []):
                    if r.get("armed") is False:
                        failures.append("module %s did not arm: %s" % (
                            r.get("module") or r.get("name"), r.get("error", "no reason given")))

            for path in PAGES:
                code, body = get(path)
                ok = code == 200
                print(("  ok   " if ok else "  FAIL ") + path + ("" if ok else "  -> %s" % code))
                if not ok:
                    failures.append("%s answered %s" % (path, code))

            code, body = get("/api/verify-chain")
            try:
                if json.loads(body).get("valid") is not True:
                    failures.append("fresh chain does not verify")
            except Exception:
                failures.append("/api/verify-chain did not return JSON")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        log.close()

    print()
    if failures:
        print("BOOT CHECK FAILED - %d problem(s):" % len(failures))
        for f in failures:
            print("  - " + f)
        print("\nlast lines of the server log:")
        with open(log_path) as f:
            print("".join(f.readlines()[-40:]))
        return 1
    print("BOOT CHECK PASSED - the site boots, arms and serves every page listed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
