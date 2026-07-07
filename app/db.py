import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
  id INTEGER PRIMARY KEY,
  token TEXT UNIQUE NOT NULL,
  label TEXT,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  revoked INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def _now():
    return datetime.now(timezone.utc)


def create_link(conn, duration_minutes, label):
    token = secrets.token_urlsafe(32)
    created_at = _now()
    expires_at = created_at + timedelta(minutes=duration_minutes)
    cur = conn.execute(
        "INSERT INTO links (token, label, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, label, created_at.isoformat(), expires_at.isoformat()),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "token": token,
        "label": label,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }


_VALID_WHERE = "used_at IS NULL AND revoked = 0 AND expires_at > ?"


def list_active_links(conn):
    rows = conn.execute(
        f"SELECT * FROM links WHERE {_VALID_WHERE} ORDER BY created_at DESC",
        (_now().isoformat(),),
    ).fetchall()
    return [dict(row) for row in rows]


def is_link_valid(conn, token):
    row = conn.execute(
        f"SELECT 1 FROM links WHERE token = ? AND {_VALID_WHERE}",
        (token, _now().isoformat()),
    ).fetchone()
    return row is not None


def claim_link(conn, token):
    """Atomically mark a link used. Returns True only for the first valid claim."""
    now = _now().isoformat()
    cur = conn.execute(
        f"UPDATE links SET used_at = ? WHERE token = ? AND {_VALID_WHERE}",
        (now, token, now),
    )
    conn.commit()
    return cur.rowcount == 1


def revoke_link(conn, link_id):
    conn.execute("UPDATE links SET revoked = 1 WHERE id = ?", (link_id,))
    conn.commit()
