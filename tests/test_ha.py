import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.ha import make_gate_opener


class RecordingHandler(BaseHTTPRequestHandler):
    requests = []
    status = 200

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        RecordingHandler.requests.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization"),
                "body": json.loads(body) if body else None,
            }
        )
        self.send_response(RecordingHandler.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"[]")

    def log_message(self, *args):
        pass


@pytest.fixture
def ha_server():
    RecordingHandler.requests = []
    RecordingHandler.status = 200
    server = HTTPServer(("127.0.0.1", 0), RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", RecordingHandler
    server.shutdown()


def make_opener(url):
    return make_gate_opener(
        {
            "HA_URL": url,
            "HA_TOKEN": "secret-ha-token",
            "HA_SCRIPT_ENTITY": "script.open_gate",
        }
    )


def test_calls_ha_script_turn_on_with_bearer_token(ha_server):
    url, handler = ha_server
    make_opener(url)()
    assert len(handler.requests) == 1
    req = handler.requests[0]
    assert req["path"] == "/api/services/script/turn_on"
    assert req["auth"] == "Bearer secret-ha-token"
    assert req["body"] == {"entity_id": "script.open_gate"}


def test_raises_on_ha_error_status(ha_server):
    url, handler = ha_server
    handler.status = 500
    with pytest.raises(Exception):
        make_opener(url)()


def test_raises_when_ha_unreachable():
    opener = make_opener("http://127.0.0.1:1")  # nothing listens here
    with pytest.raises(Exception):
        opener()
