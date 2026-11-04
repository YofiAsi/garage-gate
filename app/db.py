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
  revoked INTEGER NOT NULL DEFAULT 0,
  created_by TEXT
);
CREATE TABLE IF NOT EXISTS members (
  email TEXT PRIMARY KEY,
  role TEXT NOT NULL CHECK (role IN ('resident', 'guest')),
  added_by TEXT,
  added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  actor TEXT,
  action TEXT NOT NULL,
  link_id INTEGER,
  detail TEXT
);
"""

MEMBER_ROLES = ("resident", "guest")


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    # Databases created before roles existed lack links.created_by.
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(links)")}
    if "created_by" not in cols:
        conn.execute("ALTER TABLE links ADD COLUMN created_by TEXT")
    conn.commit()


def _now():
    return datetime.now(timezone.utc)


# --- links -------------------------------------------------------------------


def create_link(conn, duration_minutes, label, created_by=None):
    token = secrets.token_urlsafe(32)
    created_at = _now()
    expires_at = created_at + timedelta(minutes=duration_minutes)
    cur = conn.execute(
        "INSERT INTO links (token, label, created_at, expires_at, created_by)"
        " VALUES (?, ?, ?, ?, ?)",
        (token, label, created_at.isoformat(), expires_at.isoformat(), created_by),
    )
    conn.commit()
    return {
        "id": cur.lastrowid,
        "token": token,
        "label": label,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "created_by": created_by,
    }


_VALID_WHERE = "revoked = 0 AND expires_at > ?"


def list_active_links(conn, created_by=None):
    """Active links, newest first. Pass created_by to see only that user's."""
    sql = f"SELECT * FROM links WHERE {_VALID_WHERE}"
    params = [_now().isoformat()]
    if created_by is not None:
        sql += " AND created_by = ?"
        params.append(created_by)
    rows = conn.execute(sql + " ORDER BY created_at DESC", params).fetchall()
    return [dict(row) for row in rows]


def is_link_valid(conn, token):
    row = conn.execute(
        f"SELECT 1 FROM links WHERE token = ? AND {_VALID_WHERE}",
        (token, _now().isoformat()),
    ).fetchone()
    return row is not None


def use_link(conn, token):
    """Record a use (used_at = last use) without invalidating the link.
    Returns the link row (dict) iff the link is currently valid, else None."""
    now = _now().isoformat()
    cur = conn.execute(
        f"UPDATE links SET used_at = ? WHERE token = ? AND {_VALID_WHERE}",
        (now, token, now),
    )
    conn.commit()
    if cur.rowcount != 1:
        return None
    row = conn.execute("SELECT * FROM links WHERE token = ?", (token,)).fetchone()
    return dict(row)


def revoke_link(conn, link_id, created_by=None):
    """Revoke a link. With created_by, only revokes it if that user made it.
    Returns True iff a link was revoked."""
    sql = "UPDATE links SET revoked = 1 WHERE id = ? AND revoked = 0"
    params = [link_id]
    if created_by is not None:
        sql += " AND created_by = ?"
        params.append(created_by)
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount == 1


# --- members (residents and guests; admins come from ALLOWED_EMAILS) ---------


def get_member_role(conn, email):
    row = conn.execute("SELECT role FROM members WHERE email = ?", (email,)).fetchone()
    return row["role"] if row else None


def list_members(conn):
    rows = conn.execute("SELECT * FROM members ORDER BY role, email").fetchall()
    return [dict(row) for row in rows]


def add_member(conn, email, role, added_by):
    """Add a member, or change an existing member's role."""
    if role not in MEMBER_ROLES:
        raise ValueError(role)
    conn.execute(
        "INSERT INTO members (email, role, added_by, added_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(email) DO UPDATE SET role = excluded.role",
        (email, role, added_by, _now().isoformat()),
    )
    if role == "guest":
        # guests can't hold links; drop any left over from a resident role
        _revoke_links_by(conn, email)
    conn.commit()


def remove_member(conn, email):
    """Remove a member and revoke every link they created.
    Returns True iff the member existed."""
    cur = conn.execute("DELETE FROM members WHERE email = ?", (email,))
    _revoke_links_by(conn, email)
    conn.commit()
    return cur.rowcount == 1


def _revoke_links_by(conn, email):
    conn.execute(
        "UPDATE links SET revoked = 1 WHERE created_by = ? AND revoked = 0", (email,)
    )


# --- activity log --------------------------------------------------------------


def log_activity(conn, actor, action, link_id=None, detail=None):
    conn.execute(
        "INSERT INTO activity (at, actor, action, link_id, detail) VALUES (?, ?, ?, ?, ?)",
        (_now().isoformat(), actor, action, link_id, detail),
    )
    conn.commit()


def list_activity(conn, limit=200):
    rows = conn.execute(
        "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]
