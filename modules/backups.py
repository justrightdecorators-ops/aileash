# modules/backups.py
"""
modules/backups.py  v1.1  —  READ-ONLY backup finder

Lists what is sitting in the data volume so you can see, from a phone,
whether daily database backups exist and what dates they carry.

WHAT CHANGED IN v1.1, AND WHY
-----------------------------
v1.0 was PUBLIC and took a caller-supplied `dir` parameter. Together that let
anyone on the internet list any readable directory on the server - /etc, /app,
/root, the lot - and read back file names, sizes and timestamps with no key.
That is a free map of the deployment, handed to whoever asks.

  * every route is now KEYED. PUBLIC is empty.
  * the `dir` parameter is gone. Only the fixed candidate list below is read,
    and a path outside it cannot be reached through this module at all.

Still true, and still the point: this module only READS. It lists file names,
sizes and modified times. It opens nothing, writes nothing, deletes nothing,
and never touches the database or the chain.

REMOVE IT WHEN YOU ARE DONE
---------------------------
This was written during a chain break to find a backup. That job is over. A
route that enumerates the filesystem should not live in a deployment
permanently, even keyed. Delete the file once you no longer need it.

Route:
  GET /x/backups/list    keyed - list the known data locations
"""

import os
import time

VERSION = "1.1.0"

# Nothing here is public. Filesystem layout is not customer-facing.
PUBLIC = set()

# Fixed list. Not caller-supplied, deliberately: a directory parameter on a
# filesystem lister is a directory traversal with extra steps.
CANDIDATE_DIRS = [
    "/data",
    "/data/backups",
    "/data/anchors",
    "/data/backup",
    "/app",
    "/app/data",
]

# File types worth flagging as likely a database or a backup.
DB_HINTS = (".db", ".sqlite", ".sqlite3", ".bak", ".backup", ".dump", ".gz", ".zip")


def _iso(ts):
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(ts))
    except Exception:
        return str(ts)


def _human(n):
    try:
        n = float(n)
    except Exception:
        return str(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "%.1f %s" % (n, unit)
        n /= 1024
    return "%.1f TB" % n


def _list_dir(path):
    """Read-only listing of one directory. Never raises out."""
    out = {"dir": path, "exists": False, "files": []}
    try:
        if not os.path.isdir(path):
            return out
        out["exists"] = True
        entries = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
                is_dir = os.path.isdir(full)
                entries.append({
                    "name": name,
                    "is_dir": is_dir,
                    "size": None if is_dir else st.st_size,
                    "size_h": "" if is_dir else _human(st.st_size),
                    "modified": _iso(st.st_mtime),
                    "mtime": st.st_mtime,
                    "looks_like_backup": (not is_dir) and name.lower().endswith(DB_HINTS),
                })
            except Exception as e:  # noqa: BLE001
                entries.append({"name": name, "error": type(e).__name__})
        entries.sort(key=lambda e: e.get("mtime", 0), reverse=True)
        out["files"] = entries
        out["count"] = len(entries)
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__ + ": " + str(e)
    return out


def handle(method, action, data, api_key, ctx):
    if not api_key:
        return {"error": "api_key_required",
                "message": "This module lists server filesystem contents. "
                           "It is operator-only."}, 401

    if method != "GET" or action not in ("", "list"):
        return {"error": "GET /x/backups/list only", "version": VERSION}, 404

    seen = set()
    result = []
    for d in CANDIDATE_DIRS:
        if not d or d in seen:
            continue
        seen.add(d)
        result.append(_list_dir(d))

    likely = []
    for block in result:
        for f in block.get("files", []):
            if f.get("looks_like_backup"):
                likely.append({
                    "dir": block["dir"],
                    "name": f["name"],
                    "size": f.get("size_h"),
                    "modified": f.get("modified"),
                })
    likely.sort(key=lambda x: x.get("modified", ""), reverse=True)

    return {
        "version": VERSION,
        "read_only": True,
        "keyed": True,
        "note": ("This module only lists files in a fixed set of data "
                 "directories. It cannot write, delete, or touch the database "
                 "or the chain, and it cannot be pointed at any other path."),
        "likely_backups": likely,
        "likely_backups_count": len(likely),
        "directories_checked": result,
        "remove_when_done": ("This exists to find a backup during an incident. "
                             "Delete the module once you have found what you need "
                             "rather than leaving a filesystem lister deployed."),
    }, 200
