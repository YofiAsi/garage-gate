from tests.conftest import ADMIN, PUBLIC, make_link
from tests.test_admin_auth import login


def test_public_token_routes_404_on_admin_host(client, app, gate):
    link = make_link(app)
    assert client.get(f"/{link['token']}", base_url=ADMIN).status_code == 404
    assert client.post(f"/{link['token']}/open", base_url=ADMIN).status_code == 404
    assert gate.calls == 0
    # link untouched
    assert client.get(f"/{link['token']}", base_url=PUBLIC).status_code == 200


def test_admin_routes_404_on_public_host(client):
    assert client.get("/login", base_url=PUBLIC).status_code == 404
    assert client.get("/auth/callback", base_url=PUBLIC).status_code == 404
    assert client.post("/links", base_url=PUBLIC).status_code == 404


def test_admin_panel_404_on_public_host_even_with_session(client):
    login(client)
    assert client.get("/", base_url=PUBLIC).status_code == 404


def test_unknown_host_gets_404(client, app):
    link = make_link(app)
    assert client.get(f"/{link['token']}", base_url="http://evil.test").status_code == 404
