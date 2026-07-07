from tests.conftest import ADMIN


def login(client, email="owner@example.com"):
    with client.session_transaction(base_url=ADMIN) as sess:
        sess["email"] = email


def test_unauthenticated_admin_is_redirected_to_login(client):
    resp = client.get("/", base_url=ADMIN)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_allowlisted_session_sees_panel(client):
    login(client)
    resp = client.get("/", base_url=ADMIN)
    assert resp.status_code == 200
    assert b"Create link" in resp.data


def test_non_allowlisted_session_is_rejected(client):
    login(client, email="attacker@example.com")
    resp = client.get("/", base_url=ADMIN)
    assert resp.status_code in (302, 403)
    assert b"Create link" not in resp.data


def test_callback_rejects_non_allowlisted_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "attacker@example.com", "email_verified": True}},
    )
    resp = client.get("/auth/callback", base_url=ADMIN)
    assert resp.status_code == 403
    # no session granted
    assert client.get("/", base_url=ADMIN).status_code == 302


def test_callback_rejects_unverified_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "owner@example.com", "email_verified": False}},
    )
    resp = client.get("/auth/callback", base_url=ADMIN)
    assert resp.status_code == 403


def test_callback_grants_session_to_allowlisted_email(client, monkeypatch):
    from app import admin

    monkeypatch.setattr(
        admin.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "Owner@Example.com", "email_verified": True}},
    )
    resp = client.get("/auth/callback", base_url=ADMIN)
    assert resp.status_code == 302
    assert client.get("/", base_url=ADMIN).status_code == 200
