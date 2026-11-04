from datetime import datetime, timedelta, timezone

import pytest

from app import db


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(str(tmp_path / "links.db"))
    db.init_schema(connection)
    yield connection
    connection.close()


def test_create_link_returns_unguessable_token(conn):
    link = db.create_link(conn, duration_minutes=60, label="plumber")
    assert len(link["token"]) >= 32
    assert link["label"] == "plumber"


def test_created_link_is_active(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    active = db.list_active_links(conn)
    assert [l["token"] for l in active] == [link["token"]]


def test_expired_link_is_not_active(conn):
    db.create_link(conn, duration_minutes=-5, label=None)
    assert db.list_active_links(conn) == []


def test_use_link_is_repeatable_until_expiry(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    assert db.use_link(conn, link["token"]) is not None
    assert db.use_link(conn, link["token"]) is not None
    assert db.use_link(conn, link["token"]) is not None


def test_used_link_stays_active_and_valid(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    db.use_link(conn, link["token"])
    assert [l["token"] for l in db.list_active_links(conn)] == [link["token"]]
    assert db.is_link_valid(conn, link["token"]) is not None


def test_use_unknown_token_fails(conn):
    assert db.use_link(conn, "no-such-token") is None


def test_use_expired_link_fails(conn):
    link = db.create_link(conn, duration_minutes=-5, label=None)
    assert db.use_link(conn, link["token"]) is None


def test_revoked_link_cannot_be_used_and_is_not_active(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    db.revoke_link(conn, link["id"])
    assert db.list_active_links(conn) == []
    assert db.use_link(conn, link["token"]) is None


def test_expires_at_matches_duration(conn):
    before = datetime.now(timezone.utc)
    link = db.create_link(conn, duration_minutes=90, label=None)
    expires = datetime.fromisoformat(link["expires_at"])
    delta = expires - before
    assert timedelta(minutes=89) < delta < timedelta(minutes=91)


def test_init_schema_migrates_links_without_created_by(tmp_path):
    path = str(tmp_path / "old.db")
    old = db.connect(path)
    old.executescript(
        "CREATE TABLE links (id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL,"
        " label TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,"
        " used_at TEXT, revoked INTEGER NOT NULL DEFAULT 0);"
    )
    old.close()

    conn = db.connect(path)
    db.init_schema(conn)
    db.init_schema(conn)  # idempotent
    link = db.create_link(conn, 60, None, created_by="a@example.com")
    assert db.list_active_links(conn, created_by="a@example.com")[0]["id"] == link["id"]
    conn.close()
