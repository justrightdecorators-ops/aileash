# modules/backups.py
"""
modules/backups.py  —  READ-ONLY backup finder

Lists what is sitting in the data volume so you can see, from a phone,
whether daily database backups exist and what dates they carry.

SAFETY: this module only READS the filesystem. It lists file names, sizes
and modified times. It opens nothing, writes nothing, deletes nothing, and
never touches the database or the chain. There is no action here that can
change any state. It exists purely so you can find your backups before
deciding anything.

Route:
  GET /x/backups/list            list files in the likely data locations
  GET /x/backups/list?dir=/data  list a specific directory you name

Public GET so you can open it in a browser. It reveals file names and
sizes on the server volume and nothing else; remove the module once you
have found what you need.
"""

import os
import time

VERSION = "1.0.0"
PUBLIC = {("GET", "list")}

# Places a SQLite deployment on Railway commonly keeps its data and backups.
# The volume is normally mounted at /data (that is where the OTS anchors live).
CANDIDATE_DIRS = [
    "/data",
    "/data/backups",
    "/data/anchors",
    "/data/backup",
    ".",
    "/app",
    "/app/data",
    os.environ.get("DATA_DIR", "") or "/data",
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
        # newest first — the most recent backup is what you want
        entries.sort(key=lambda e: e.get("mtime", 0), reverse=True)
        out["files"] = entries
        out["count"] = len(entries)
    except Exception as e:  # noqa: BLE001
        out["error"] = type(e).__name__ + ": " + str(e)
    return out


def handle(method, action, data, api_key, ctx):
    if method != "GET" or action != "list":
        return {"error": "GET /x/backups/list only", "version": VERSION}, 404

    data = data or {}
    asked = data.get("dir") if isinstance(data, dict) else None

    if asked:
        result = [_list_dir(str(asked))]
    else:
        seen = set()
        result = []
        for d in CANDIDATE_DIRS:
            if not d or d in seen:
                continue
            seen.add(d)
            result.append(_list_dir(d))

    # pull out anything that looks like a backup, across everything listed,
    # so it is obvious at a glance
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
        "note": "This module only lists files. It cannot write, delete, or touch "
                "the database or the chain. Remove it once you have found your backups.",
        "likely_backups": likely,
        "likely_backups_count": len(likely),
        "directories_checked": result,
        "next": "If you see a .db/.sqlite/.bak dated BEFORE the chain broke, that is "
                "your intact chain. Do not delete anything. Tell me the exact "
                "filename and date and we work out the restore safely.",
    }, 200
