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


def test_claim_link_succeeds_once(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    assert db.claim_link(conn, link["token"]) is True
    assert db.claim_link(conn, link["token"]) is False


def test_claim_unknown_token_fails(conn):
    assert db.claim_link(conn, "no-such-token") is False


def test_claim_expired_link_fails(conn):
    link = db.create_link(conn, duration_minutes=-5, label=None)
    assert db.claim_link(conn, link["token"]) is False


def test_revoked_link_cannot_be_claimed_and_is_not_active(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    db.revoke_link(conn, link["id"])
    assert db.list_active_links(conn) == []
    assert db.claim_link(conn, link["token"]) is False


def test_peek_link_is_valid_does_not_consume(conn):
    link = db.create_link(conn, duration_minutes=60, label=None)
    assert db.is_link_valid(conn, link["token"]) is True
    assert db.is_link_valid(conn, link["token"]) is True
    assert db.claim_link(conn, link["token"]) is True


def test_expires_at_matches_duration(conn):
    before = datetime.now(timezone.utc)
    link = db.create_link(conn, duration_minutes=90, label=None)
    expires = datetime.fromisoformat(link["expires_at"])
    delta = expires - before
    assert timedelta(minutes=89) < delta < timedelta(minutes=91)
