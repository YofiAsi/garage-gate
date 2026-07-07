"""Home Assistant client. The only module that touches HA_TOKEN."""

import requests


def make_gate_opener(config):
    url = f"{config['HA_URL'].rstrip('/')}/api/services/script/turn_on"
    entity = config["HA_SCRIPT_ENTITY"]
    token = config["HA_TOKEN"]

    def open_gate():
        resp = requests.post(
            url,
            json={"entity_id": entity},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()

    return open_gate
