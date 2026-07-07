"""OAuth redirect URI must follow the real scheme: https behind the proxy, http locally."""

from tests.conftest import ADMIN


def _capture_login_redirect(client, monkeypatch, headers=None):
    from app import admin

    captured = {}

    def fake_authorize_redirect(redirect_uri):
        captured["uri"] = redirect_uri
        return "", 302

    monkeypatch.setattr(admin.oauth.google, "authorize_redirect", fake_authorize_redirect)
    client.get("/admin/login", base_url=ADMIN, headers=headers or {})
    return captured["uri"]


def test_redirect_uri_is_https_behind_proxy(client, monkeypatch):
    uri = _capture_login_redirect(client, monkeypatch, {"X-Forwarded-Proto": "https"})
    assert uri == "https://garage.test/admin/auth/callback"


def test_redirect_uri_is_http_without_proxy(client, monkeypatch):
    uri = _capture_login_redirect(client, monkeypatch)
    assert uri == "http://garage.test/admin/auth/callback"


def test_insecure_http_flag_relaxes_session_cookie(tmp_path):
    from app import create_app

    base = {
        "SECRET_KEY": "s",
        "DB_PATH": str(tmp_path / "a.db"),
        "PUBLIC_HOST": "garage.test",
        "ALLOWED_EMAILS": [],
        "GOOGLE_CLIENT_ID": "x",
        "GOOGLE_CLIENT_SECRET": "y",
        "GATE_OPENER": lambda: None,
    }
    secure_app = create_app(dict(base, DB_PATH=str(tmp_path / "b.db")))
    assert secure_app.config["SESSION_COOKIE_SECURE"] is True

    insecure_app = create_app(dict(base, INSECURE_HTTP=True))
    assert insecure_app.config["SESSION_COOKIE_SECURE"] is False
