from tests.conftest import PUBLIC, make_link


def get_page(client, token):
    return client.get(f"/{token}", base_url=PUBLIC)


def post_open(client, token):
    return client.post(f"/{token}/open", base_url=PUBLIC)


def test_valid_token_shows_confirm_button_without_consuming(client, app, gate):
    link = make_link(app)
    resp = get_page(client, link["token"])
    assert resp.status_code == 200
    assert "ללחוץ אאאארוך".encode() in resp.data
    assert gate.calls == 0
    # still valid after GET
    assert get_page(client, link["token"]).status_code == 200


def test_post_opens_gate_once(client, app, gate):
    link = make_link(app)
    resp = post_open(client, link["token"])
    assert resp.status_code == 200
    assert "תודווווות".encode() in resp.data
    assert gate.calls == 1


def test_second_post_is_invalid_and_does_not_open(client, app, gate):
    link = make_link(app)
    post_open(client, link["token"])
    resp = post_open(client, link["token"])
    assert gate.calls == 1
    assert "הלינק לא טוב".encode() in resp.data


def test_invalid_reasons_are_indistinguishable(client, app, gate):
    expired = make_link(app, minutes=-5)
    used = make_link(app)
    post_open(client, used["token"])

    bodies = {
        get_page(client, "nonexistent-token").data,
        get_page(client, expired["token"]).data,
        get_page(client, used["token"]).data,
    }
    statuses = {
        get_page(client, "nonexistent-token").status_code,
        get_page(client, expired["token"]).status_code,
        get_page(client, used["token"]).status_code,
    }
    assert len(bodies) == 1
    assert len(statuses) == 1


def test_post_on_invalid_token_does_not_open(client, gate):
    resp = post_open(client, "nonexistent-token")
    assert gate.calls == 0
    assert "הלינק לא טוב".encode() in resp.data


def test_ha_failure_shows_error_not_confirmation(client, app, gate):
    link = make_link(app)
    gate.fail = True
    resp = post_open(client, link["token"])
    assert resp.status_code == 500
    assert "תודווווות".encode() not in resp.data
    assert "השתבש".encode() in resp.data
