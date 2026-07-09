from tests.conftest import ADMIN
from tests.test_admin_auth import login
from tests.test_admin_panel import get_csrf


def test_open_calls_gate_and_returns_204(client, gate):
    login(client)
    csrf = get_csrf(client)
    resp = client.post("/admin/open", data={"csrf_token": csrf}, base_url=ADMIN)
    assert resp.status_code == 204
    assert gate.calls == 1


def test_open_requires_auth(client, gate):
    resp = client.post("/admin/open", data={"csrf_token": "x"}, base_url=ADMIN)
    assert resp.status_code == 302
    assert gate.calls == 0


def test_open_rejects_bad_csrf(client, gate):
    login(client)
    get_csrf(client)  # ensures a token exists in session
    resp = client.post("/admin/open", data={"csrf_token": "wrong"}, base_url=ADMIN)
    assert resp.status_code == 400
    assert gate.calls == 0


def test_open_returns_500_when_gate_fails(client, gate):
    login(client)
    gate.fail = True
    csrf = get_csrf(client)
    resp = client.post("/admin/open", data={"csrf_token": csrf}, base_url=ADMIN)
    assert resp.status_code == 500
    assert gate.calls == 1


def test_panel_renders_open_button(client):
    login(client)
    resp = client.get("/admin/", base_url=ADMIN)
    assert resp.status_code == 200
    assert b'id="admin-open-btn"' in resp.data
