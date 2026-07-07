import re

from tests.conftest import ADMIN, PUBLIC, make_link
from tests.test_admin_auth import login


def get_csrf(client):
    resp = client.get("/", base_url=ADMIN)
    match = re.search(rb'name="csrf_token" value="([^"]+)"', resp.data)
    assert match, "panel must embed a csrf token"
    return match.group(1).decode()


def create_link(client, amount=2, unit="hours", label="guest"):
    return client.post(
        "/links",
        data={"amount": amount, "unit": unit, "label": label, "csrf_token": get_csrf(client)},
        base_url=ADMIN,
        follow_redirects=True,
    )


def test_create_link_shows_public_url_and_appears_in_list(client):
    login(client)
    resp = create_link(client, label="plumber")
    assert resp.status_code == 200
    match = re.search(rb"https://garage\.test/([\w-]+)", resp.data)
    assert match, "panel must show the new public URL"
    token = match.group(1).decode()
    assert b"plumber" in resp.data
    # the link actually works on the public side
    assert b"Open gate" in client.get(f"/{token}", base_url=PUBLIC).data


def test_create_requires_auth(client):
    resp = client.post(
        "/links",
        data={"amount": 1, "unit": "hours", "csrf_token": "x"},
        base_url=ADMIN,
    )
    assert resp.status_code == 302


def test_create_rejects_bad_csrf(client):
    login(client)
    get_csrf(client)  # ensures a token exists in session
    resp = client.post(
        "/links",
        data={"amount": 1, "unit": "hours", "csrf_token": "wrong"},
        base_url=ADMIN,
    )
    assert resp.status_code == 400


def test_revoke_removes_from_list_and_kills_public_link(client, app):
    login(client)
    link = make_link(app, minutes=60)
    csrf = get_csrf(client)
    resp = client.post(
        f"/links/{link['id']}/revoke",
        data={"csrf_token": csrf},
        base_url=ADMIN,
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert link["token"].encode() not in resp.data
    assert b"invalid" in client.get(f"/{link['token']}", base_url=PUBLIC).data.lower()


def test_revoke_requires_auth(client, app):
    link = make_link(app)
    resp = client.post(f"/links/{link['id']}/revoke", data={}, base_url=ADMIN)
    assert resp.status_code == 302
    assert b"Open gate" in client.get(f"/{link['token']}", base_url=PUBLIC).data


def test_minutes_unit_creates_short_expiry(client, app):
    login(client)
    create_link(client, amount=5, unit="minutes", label="quick")
    from app import db

    conn = db.connect(app.config["DB_PATH"])
    row = conn.execute("SELECT created_at, expires_at FROM links WHERE label='quick'").fetchone()
    conn.close()
    from datetime import datetime

    delta = datetime.fromisoformat(row["expires_at"]) - datetime.fromisoformat(row["created_at"])
    assert delta.total_seconds() == 5 * 60
