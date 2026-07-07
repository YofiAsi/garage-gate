# garage-gate

Self-hosted temporary-link service for opening a gate through Home Assistant.

- **Public:** `https://garage.asafshilo.com/<token>` shows a hold-to-open
  button; holding it 2 seconds triggers the HA webhook that opens the gate.
  Links can be used any number of times until they expire or are revoked.
  Expired / revoked / unknown tokens all show the same generic
  "link invalid" page.
- **Admin:** `https://garage.asafshilo.com/admin/` — Google login (allowlisted
  emails only) with a form to create links (expiry in minutes/hours, optional
  label) and a list of active links with revoke buttons.

Links expire on their **time limit** (or when revoked from the admin panel);
using a link never invalidates it.

## Setup

### 1. Google OAuth credentials

1. In [Google Cloud Console → APIs & Credentials](https://console.cloud.google.com/apis/credentials),
   create an **OAuth client ID** of type **Web application**.
2. Add the authorized redirect URI: `https://garage.asafshilo.com/admin/auth/callback`
3. Put the client ID and secret in `.env`.

### 2. Home Assistant

Create a webhook-triggered automation in HA that runs the gate-open script,
and put its URL in `.env` as `HA_WEBHOOK_URL`. The webhook id is the secret
— it is only ever used server-side.

Home Assistant's own compose file runs with `network_mode: host` and is
reachable only on its Tailscale interface, not the plain LAN IP (confirmed:
LAN connections are refused, Tailscale connections succeed — this looks like
a deliberate choice, not an oversight). This app's production
`docker-compose.yml` matches `network_mode: host` for the same reason
Dokploy needs it here: it runs on the same physical box as Home Assistant,
so **use `http://localhost:8123/api/webhook/<id>`** — no Tailscale
dependency needed. For local development (a different machine),
`docker-compose.local.yml` instead maps the `yofiserver` Tailscale hostname
directly to its IP via `extra_hosts`, so local dev keeps using
`http://yofiserver:8123/api/webhook/<id>` and can still reach the real
webhook. See `.env.example` for both.

### 3. Environment

```
cp .env.example .env   # then fill in the blanks
```

### 4. Deploy with Dokploy

`docker-compose.yml` is the production file — it builds the image, mounts
the `gate-data` volume, and runs with `network_mode: host` (see above: this
matches Home Assistant's own setup on the same box, and lets the app reach
HA via plain `localhost` with no Tailscale dependency).

1. In Dokploy, create a **Compose** application pointing at this repo/branch
   (it will use `docker-compose.yml` automatically).
2. Set the env vars from `.env` in Dokploy's environment settings (or point
   it at an env file) — never commit `.env` itself.
3. Add a domain: `garage.asafshilo.com` → the app on port `8000`. Because
   `network_mode: host` has no bridge network of its own, Dokploy needs to
   route to this service by host port (e.g. `127.0.0.1:8000`) rather than by
   the usual container-name/bridge-network discovery — check Dokploy's app
   settings for a "host network" toggle if the domain doesn't route
   correctly at first.

Public links live at `/<token>`, the admin panel at `/admin/`. The SQLite
database lives on the `gate-data` volume (`/data/links.db`), so links
survive redeploys.

**Security note:** unlike the previous bridge-network setup, host networking
means gunicorn's port 8000 binds directly on every host interface (LAN,
Tailscale, loopback) — Docker's network isolation no longer hides it. The
admin panel still requires a valid Google-authenticated session either way,
but if you want port 8000 unreachable from the LAN the way HA's port 8123
already is, add the same firewall rule for it that currently protects 8123.

## Development

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
.venv/Scripts/python -m pytest
```

Run the containerized app locally (the production compose file publishes no
port, so pass the local override to reach it from the host):

```
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

This publishes the app at `http://localhost:18000`. `docker-compose.local.yml`
is dev-only and is never picked up by Dokploy (which runs `docker-compose.yml`
alone).

### Testing Google login locally

Add `http://localhost:18000/admin/auth/callback` as an extra authorized
redirect URI in the Google console, set `INSECURE_HTTP=1` in your local
`.env` (never in production), and run the command above. The app builds the
OAuth redirect URI from the request scheme (behind Traefik in production,
`X-Forwarded-Proto` makes it https automatically).

## Notes / limitations

- If the HA call fails, the visitor sees an error page and can try again —
  links are reusable, so a failed attempt doesn't burn the link. A log line
  with the traceback is written server-side.
- No rate limiting in the app; add Traefik middleware later if token probing
  ever becomes a concern (tokens are 256-bit random, so guessing is not
  realistic).
