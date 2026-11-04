"""Everything lives on one domain at the root: the panel at /, tokens at /<token>."""

import re

from tests.conftest import BASE, make_link
from tests.test_admin_auth import login


def test_root_without_session_redirects_to_login(client, gate):
    resp = client.get("/", base_url=BASE)
    assert resp.status_code == 302
    assert resp.location.endswith("/login")
    assert gate.calls == 0


def test_root_serves_panel_with_session(client):
    login(client)
    assert client.get("/", base_url=BASE).status_code == 200


def test_old_admin_urls_redirect_to_root(client):
    for path in ("/admin", "/admin/", "/admin/links", "/admin/login"):
        resp = client.get(path, base_url=BASE)
        assert resp.status_code == 302, path
        # relative, so a misdetected request scheme can't produce a bad URL
        assert resp.headers["Location"] == "/", path


def test_old_admin_service_worker_unregisters_itself(client):
    resp = client.get("/admin/sw.js", base_url=BASE)
    assert resp.status_code == 200
    assert resp.mimetype == "text/javascript"
    assert "unregister()" in resp.get_data(as_text=True)


def test_token_route_still_works_at_root(client, app):
    link = make_link(app)
    assert client.get(f"/{link['token']}", base_url=BASE).status_code == 200


def test_panel_routes_are_not_treated_as_tokens(client, gate):
    # unauthenticated POSTs to panel routes go to login, never the token route
    for path in ("/open", "/links", "/members"):
        resp = client.post(path, data={}, base_url=BASE)
        assert resp.status_code == 302, path
    assert gate.calls == 0


def test_panel_link_urls_use_request_host(client):
    login(client)
    from tests.test_admin_panel import create_link

    resp = create_link(client)
    assert b"http://garage.test/" in resp.data


def test_panel_link_urls_follow_localhost(client):
    LOCAL = "http://localhost:18000"
    with client.session_transaction(base_url=LOCAL) as sess:
        sess["email"] = "owner@example.com"

    resp = client.get("/", base_url=LOCAL)
    match = re.search(rb'name="csrf_token" value="([^"]+)"', resp.data)
    csrf = match.group(1).decode()

    resp = client.post(
        "/links",
        data={"amount": 1, "unit": "hours", "csrf_token": csrf},
        base_url=LOCAL,
    )
    assert b"http://localhost:18000/" in resp.data
