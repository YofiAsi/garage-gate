from tests.conftest import ADMIN


def login(client, email="owner@example.com"):
    with client.session_transaction(base_url=ADMIN) as sess:
        sess["email"] = email


def test_unauthenticated_admin_is_redirected_to_login(client):
    resp = client.get("/admin/", base_url=ADMIN)
    assert resp.status_code == 302
    assert "/admin/login" in resp.location


def test_allowlisted_session_sees_panel(client):
    login(client)
    resp = client.get("/admin/", base_url=ADMIN)
    assert resp.status_code == 200
    assert b'id="create-form"' in resp.data


def test_non_allowlisted_session_is_rejected(client):
    login(client, email="attacker@example.com")
    resp = client.get("/admin/", base_url=ADMIN)
    assert resp.status_code in (302, 403)
    assert b'id="create-form"' not in resp.data


def test_callback_rejects_non_allowlisted_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "attacker@example.com", "email_verified": True}},
    )
    resp = client.get("/admin/auth/callback", base_url=ADMIN)
    assert resp.status_code == 403
    # no session granted
    assert client.get("/admin/", base_url=ADMIN).status_code == 302


def test_callback_rejects_unverified_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "owner@example.com", "email_verified": False}},
    )
    resp = client.get("/admin/auth/callback", base_url=ADMIN)
    assert resp.status_code == 403


def test_callback_grants_session_to_allowlisted_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "Owner@Example.com", "email_verified": True}},
    )
    resp = client.get("/admin/auth/callback", base_url=ADMIN)
    assert resp.status_code == 302
    assert client.get("/admin/", base_url=ADMIN).status_code == 200


def test_login_session_persists_for_a_week(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from email.utils import parsedate_to_datetime

    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "owner@example.com", "email_verified": True}},
    )
    resp = client.get("/admin/auth/callback", base_url=ADMIN)
    # The session cookie must be permanent (carry an Expires) rather than a
    # per-browser-session cookie, so mobile/PWA clients stay logged in.
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "session=" in set_cookie
    assert "Expires=" in set_cookie
    expires = parsedate_to_datetime(set_cookie.split("Expires=")[1].split(";")[0])
    # ~7 days out (allow a minute of slack for clock/test runtime)
    assert abs((expires - datetime.now(timezone.utc)) - timedelta(days=7)) < timedelta(minutes=1)
