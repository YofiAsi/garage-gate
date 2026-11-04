"""Admin / resident / guest permissions, member management and the activity log."""

import re

import pytest

from app import db
from tests.conftest import BASE, make_link
from tests.test_admin_auth import login

ADMIN_EMAIL = "owner@example.com"
RESIDENT = "res@example.com"
GUEST = "guest@example.com"


def add_member(app, email, role):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        db.add_member(conn, email, role, added_by=ADMIN_EMAIL)
        conn.close()


def query(app, sql, params=()):
    conn = db.connect(app.config["DB_PATH"])
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return rows


def csrf(client):
    resp = client.get("/", base_url=BASE)
    assert resp.status_code == 200
    return re.search(rb'name="csrf_token" value="([^"]+)"', resp.data).group(1).decode()


def post(client, path, **data):
    data["csrf_token"] = csrf(client)
    return client.post(path, data=data, base_url=BASE)


def activity(app):
    return query(app, "SELECT * FROM activity ORDER BY id")


@pytest.fixture
def members(app):
    add_member(app, RESIDENT, "resident")
    add_member(app, GUEST, "guest")


# --- guests ---------------------------------------------------------------------


def test_guest_can_open_gate(client, app, gate, members):
    login(client, GUEST)
    assert post(client, "/open").status_code == 204
    assert gate.calls == 1
    assert [(a["actor"], a["action"]) for a in activity(app)] == [(GUEST, "gate_open")]


def test_guest_panel_has_no_link_or_admin_sections(client, members):
    login(client, GUEST)
    html = client.get("/", base_url=BASE).data
    assert b'id="open-btn"' in html
    assert b'id="create-form"' not in html
    assert b"active links" not in html.lower()
    assert b'id="members"' not in html
    assert b'id="activity"' not in html


def test_guest_cannot_create_or_revoke_links(client, app, members):
    login(client, GUEST)
    assert post(client, "/links", amount=1, unit="hours").status_code == 403
    link = make_link(app)
    assert post(client, f"/links/{link['id']}/revoke").status_code == 403
    assert query(app, "SELECT revoked FROM links")[0]["revoked"] == 0


# --- residents ------------------------------------------------------------------


def test_resident_can_create_links_up_to_24_hours(client, app, members):
    login(client, RESIDENT)
    assert post(client, "/links", amount=24, unit="hours").status_code == 200
    assert post(client, "/links", minutes=24 * 60 + 1).status_code == 400
    assert post(client, "/links", amount=25, unit="hours").status_code == 400
    links = query(app, "SELECT created_by FROM links")
    assert links == [{"created_by": RESIDENT}]


def test_admin_is_not_capped_at_24_hours(client, app):
    login(client)
    assert post(client, "/links", amount=48, unit="hours").status_code == 200


def test_resident_sees_and_revokes_only_own_links(client, app, members):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        mine = db.create_link(conn, 60, None, created_by=RESIDENT)
        theirs = db.create_link(conn, 60, None, created_by=ADMIN_EMAIL)
        conn.close()
    login(client, RESIDENT)
    html = client.get("/", base_url=BASE).get_data(as_text=True)
    assert f"/links/{mine['id']}/revoke" in html
    assert f"/links/{theirs['id']}/revoke" not in html
    assert b'id="members"' not in html.encode()

    post(client, f"/links/{theirs['id']}/revoke")
    post(client, f"/links/{mine['id']}/revoke")
    revoked = {r["id"]: r["revoked"] for r in query(app, "SELECT id, revoked FROM links")}
    assert revoked == {mine["id"]: 1, theirs["id"]: 0}


def test_resident_cannot_manage_members(client, app, members):
    login(client, RESIDENT)
    assert post(client, "/members", email="x@example.com", role="guest").status_code == 403
    assert post(client, "/members/remove", email=GUEST).status_code == 403
    assert {m["email"] for m in query(app, "SELECT email FROM members")} == {RESIDENT, GUEST}


# --- admins ---------------------------------------------------------------------


def test_admin_sees_all_links_with_creator(client, app, members):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        db.create_link(conn, 60, None, created_by=RESIDENT)
        conn.close()
    login(client)
    html = client.get("/", base_url=BASE).get_data(as_text=True)
    assert 'class="who">res@example.com' in html


def test_admin_adds_member_who_can_then_log_in(client, app, monkeypatch):
    from app import panel

    login(client)
    resp = post(client, "/members", email="  New@Example.com ", role="guest")
    assert resp.status_code == 200
    assert b"new@example.com" in resp.data
    assert query(app, "SELECT email, role FROM members") == [
        {"email": "new@example.com", "role": "guest"}
    ]

    other = app.test_client()
    monkeypatch.setattr(
        panel.oauth.google,
        "authorize_access_token",
        lambda: {"userinfo": {"email": "new@example.com", "email_verified": True}},
    )
    assert other.get("/auth/callback", base_url=BASE).status_code == 302
    assert other.get("/", base_url=BASE).status_code == 200


@pytest.mark.parametrize(
    "email,role",
    [("not-an-email", "guest"), ("x@example.com", "admin"), (ADMIN_EMAIL, "guest")],
)
def test_add_member_rejects_bad_input(client, email, role):
    login(client)
    assert post(client, "/members", email=email, role=role).status_code == 400


def test_admin_can_change_member_role(client, app, members):
    login(client)
    post(client, "/members", email=GUEST, role="resident")
    roles = {m["email"]: m["role"] for m in query(app, "SELECT * FROM members")}
    assert roles[GUEST] == "resident"


def test_removing_resident_revokes_links_and_access(client, app, members):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        link = db.create_link(conn, 60, None, created_by=RESIDENT)
        conn.close()
    resident = app.test_client()
    login(resident, RESIDENT)
    assert resident.get("/", base_url=BASE).status_code == 200

    login(client)
    assert post(client, "/members/remove", email=RESIDENT).status_code == 200

    assert query(app, "SELECT revoked FROM links WHERE id = ?", (link["id"],))[0]["revoked"] == 1
    # the existing session is rejected on its very next request
    assert resident.get("/", base_url=BASE).status_code == 302
    assert client.get(f"/{link['token']}", base_url=BASE).status_code == 404


def test_env_admin_cannot_be_removed_in_ui(client):
    login(client)
    post(client, "/members/remove", email=ADMIN_EMAIL)
    assert client.get("/", base_url=BASE).status_code == 200


def test_non_member_is_rejected(client):
    login(client, "stranger@example.com")
    assert client.get("/", base_url=BASE).status_code == 302


# --- activity log ---------------------------------------------------------------


def test_activity_log_records_everything_and_is_admin_only(client, app, gate, members):
    login(client, RESIDENT)
    resp = post(client, "/links", amount=2, unit="hours")
    token = re.search(rb"http://garage\.test/([\w-]+)</code>", resp.data).group(1).decode()
    link_id = query(app, "SELECT id FROM links")[0]["id"]
    post(client, "/open")

    # a visitor using the shared link is attributed to the link's creator
    app.test_client().post(f"/{token}/open", base_url=BASE)
    assert gate.calls == 2

    login(client)  # switch to admin
    post(client, f"/links/{link_id}/revoke")
    post(client, "/members", email="new@example.com", role="guest")
    post(client, "/members/remove", email="new@example.com")

    rows = [(a["actor"], a["action"], a["link_id"]) for a in activity(app)]
    assert rows == [
        (RESIDENT, "link_create", link_id),
        (RESIDENT, "gate_open", None),
        (RESIDENT, "link_open", link_id),
        (ADMIN_EMAIL, "link_revoke", link_id),
        (ADMIN_EMAIL, "member_add", None),
        (ADMIN_EMAIL, "member_remove", None),
    ]

    html = client.get("/", base_url=BASE).get_data(as_text=True)
    assert 'id="activity"' in html
    assert f"gate opened via their link #{link_id}" in html
    assert "created link" in html and "(2 hours)" in html


def test_failed_gate_open_is_logged_as_failed(client, app, gate):
    gate.fail = True
    login(client)
    assert post(client, "/open").status_code == 500
    assert activity(app)[0]["detail"] == "failed"


def test_logout_clears_session(client):
    login(client)
    assert post(client, "/logout").status_code == 200
    assert client.get("/", base_url=BASE).status_code == 302
