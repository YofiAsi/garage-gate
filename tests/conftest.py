import pytest

from app import create_app, db

BASE = "http://garage.test"
# kept as aliases so tests read clearly: same host, different areas
PUBLIC = BASE
ADMIN = BASE


class FakeGate:
    def __init__(self):
        self.calls = 0
        self.fail = False

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("HA unreachable")


@pytest.fixture
def gate():
    return FakeGate()


@pytest.fixture
def app(tmp_path, gate):
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DB_PATH": str(tmp_path / "links.db"),
            "PUBLIC_HOST": "garage.test",
            "ALLOWED_EMAILS": ["owner@example.com"],
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-client-secret",
            "GATE_OPENER": gate,
        }
    )
    yield app


@pytest.fixture
def client(app):
    return app.test_client()


def make_link(app, minutes=60, label=None):
    with app.app_context():
        conn = db.connect(app.config["DB_PATH"])
        link = db.create_link(conn, duration_minutes=minutes, label=label)
        conn.close()
    return link
