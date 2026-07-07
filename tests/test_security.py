"""The HA webhook URL (its id is the secret) must never appear in anything a visitor sees."""

from app import create_app, db
from tests.test_ha import ha_server  # noqa: F401  (fixture)

SECRET_HOOK = "secret-hook-id"


def test_webhook_id_never_in_public_responses(tmp_path, ha_server):  # noqa: F811
    url, handler = ha_server
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DB_PATH": str(tmp_path / "links.db"),
            "PUBLIC_HOST": "garage.test",
            "ALLOWED_EMAILS": ["owner@example.com"],
            "HA_WEBHOOK_URL": f"{url}/api/webhook/{SECRET_HOOK}",
        }
    )
    client = app.test_client()
    conn = db.connect(app.config["DB_PATH"])
    link = db.create_link(conn, duration_minutes=60, label=None)
    conn.close()

    responses = [
        client.get(f"/{link['token']}", base_url="http://garage.test"),
        client.post(f"/{link['token']}/open", base_url="http://garage.test"),
        client.get(f"/{link['token']}", base_url="http://garage.test"),
    ]
    # the gate really was triggered through the real HA client
    assert len(handler.requests) == 1

    for resp in responses:
        assert SECRET_HOOK.encode() not in resp.data
        for name, value in resp.headers:
            assert SECRET_HOOK not in name and SECRET_HOOK not in value
