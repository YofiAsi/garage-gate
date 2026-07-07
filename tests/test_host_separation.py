"""Everything lives on one domain: admin under /admin, tokens at the root."""

from tests.conftest import BASE, make_link
from tests.test_admin_auth import login


def test_admin_prefix_is_not_treated_as_a_token(client, gate):
    # /admin (no session) must reach the admin area, not the token route
    resp = client.get("/admin/", base_url=BASE)
    assert resp.status_code == 302
    assert "/admin/login" in resp.location
    assert gate.calls == 0


def test_token_route_still_works_at_root(client, app):
    link = make_link(app)
    assert client.get(f"/{link['token']}", base_url=BASE).status_code == 200


def test_admin_area_unreachable_without_session_even_via_token_shape(client):
    # e.g. probing /login should not exist at the root; admin routes only under /admin
    resp = client.get("/login", base_url=BASE)
    assert resp.status_code == 404


def test_panel_link_urls_use_public_host(client):
    login(client)
    from tests.test_admin_panel import create_link

    resp = create_link(client, label="x")
    assert b"https://garage.test/" in resp.data
