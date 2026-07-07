import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.ha import make_gate_opener


class RecordingHandler(BaseHTTPRequestHandler):
    requests = []
    status = 200

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        RecordingHandler.requests.append({"path": self.path})
        self.send_response(RecordingHandler.status)
        self.end_headers()

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


def make_opener(base_url):
    return make_gate_opener({"HA_WEBHOOK_URL": f"{base_url}/api/webhook/secret-hook-id"})


def test_posts_to_webhook(ha_server):
    url, handler = ha_server
    make_opener(url)()
    assert handler.requests == [{"path": "/api/webhook/secret-hook-id"}]


def test_raises_on_ha_error_status(ha_server):
    url, handler = ha_server
    handler.status = 500
    with pytest.raises(Exception):
        make_opener(url)()


def test_raises_when_ha_unreachable():
    opener = make_opener("http://127.0.0.1:1")  # nothing listens here
    with pytest.raises(Exception):
        opener()
