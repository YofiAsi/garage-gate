"""The panel is an installable PWA scoped to the site root."""

import json

from tests.conftest import BASE
from tests.test_admin_auth import login


def test_manifest_is_served_with_correct_type_and_scope(client):
    resp = client.get("/manifest.webmanifest", base_url=BASE)
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"
    data = json.loads(resp.data)
    assert data["start_url"] == "/"
    assert data["scope"] == "/"
    # unchanged id keeps installs from the /admin/ days the same app
    assert data["id"] == "/admin/"
    assert data["display"] == "standalone"
    sizes = {(i["sizes"], i["purpose"]) for i in data["icons"]}
    assert ("192x192", "any") in sizes
    assert ("512x512", "any") in sizes
    assert ("512x512", "maskable") in sizes


def test_service_worker_is_javascript_scoped_to_root(client):
    resp = client.get("/sw.js", base_url=BASE)
    assert resp.status_code == 200
    assert resp.mimetype == "text/javascript"
    assert resp.headers.get("Service-Worker-Allowed") == "/"
    body = resp.get_data(as_text=True)
    # a fetch handler is required for installability, and the cache is versioned
    assert 'addEventListener("fetch"' in body
    assert "gate-" in body


def test_offline_page_renders(client):
    resp = client.get("/offline", base_url=BASE)
    assert resp.status_code == 200
    assert b"offline" in resp.data.lower()


def test_pwa_endpoints_need_no_login(client):
    # browsers fetch these before/without an admin session
    for path in ("/manifest.webmanifest", "/sw.js", "/offline"):
        assert client.get(path, base_url=BASE).status_code == 200


def test_panel_wires_up_the_pwa(client):
    login(client)
    html = client.get("/", base_url=BASE).get_data(as_text=True)
    assert 'rel="manifest"' in html
    assert '"/manifest.webmanifest"' in html
    assert '"/sw.js"' in html
    assert 'scope: "/"' in html
    assert 'name="theme-color"' in html
    assert "apple-touch-icon" in html


def test_icons_exist_as_static_assets(client):
    for name in (
        "icon-192.png",
        "icon-512.png",
        "icon-maskable-512.png",
        "apple-touch-icon.png",
    ):
        resp = client.get(f"/static/icons/{name}", base_url=BASE)
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"


def test_pwa_routes_do_not_shadow_public_token_route(client, app):
    from tests.conftest import make_link

    link = make_link(app)
    assert client.get(f"/{link['token']}", base_url=BASE).status_code == 200
