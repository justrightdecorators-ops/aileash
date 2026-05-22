import sqlite3
import time
import json

DB = "aileash.db"


def get_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            user TEXT,
            event TEXT,
            decision TEXT,
            score REAL
        )
    """)

    conn.commit()
    return conn


_db = None


def db():
    global _db
    if _db is None:
        _db = get_db()
    return _db


def log(user, event, decision, score):
    db().execute(
        "INSERT INTO audit(ts, user, event, decision, score) VALUES(?,?,?,?,?)",
        (time.time(), user, json.dumps(event), decision, score)
    )
    db().commit()


def recent(limit=50):
    rows = db().execute(
        "SELECT * FROM audit ORDER BY id DESC LIMIT ?",
        (limit,)
    ).fetchall()

    return [dict(r) for r in rows]


def count_for_user(user):
    row = db().execute(
        "SELECT COUNT(*) FROM audit WHERE user=?",
        (user,)
    ).fetchone()

    return row[0]
