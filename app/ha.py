"""Home Assistant client. The webhook URL (its id is a secret) never leaves this module."""

import requests


def make_gate_opener(config):
    url = config["HA_WEBHOOK_URL"]

    def open_gate():
        resp = requests.post(url, timeout=10)
        resp.raise_for_status()

    return open_gate
