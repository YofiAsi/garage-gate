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
and put its URL in `.env` as `HA_WEBHOOK_URL`
(e.g. `http://yofiserver:8123/api/webhook/<webhook-id>`). The webhook id is
the secret — it is only ever used server-side.

`yofiserver` is a Tailscale MagicDNS name, not a plain LAN hostname, and HA
was found to be unreachable on the raw LAN IP (connection refused) but
reachable on the Tailscale IP. A container has no Tailscale client of its
own, so `docker-compose.yml` maps that hostname to HA's Tailscale IP
directly via `extra_hosts` — no Tailscale software runs in the container,
this is just a hardcoded private IP, reachable because Dokploy runs on the
same host as Home Assistant. If that IP ever changes, or if this app is
ever deployed on a different machine than the HA host, update (or replace)
that `extra_hosts` entry — check the current IP with `tailscale status` on
the HomeLab server.

**To avoid the Tailscale IP entirely:** try
`HA_WEBHOOK_URL=http://host.docker.internal:8123/api/webhook/<id>` instead.
`docker-compose.yml` already maps `host.docker.internal` to the Docker
bridge gateway. Since HA runs with no `server_host` restriction, it should
also be listening there — this only fails if the host firewall blocks more
than just the LAN interface specifically. If it works, the `yofiserver`
mapping becomes unnecessary; if you get "connection refused" again, revert
to the `yofiserver`/Tailscale-IP URL, which is confirmed working.

### 3. Environment

```
cp .env.example .env   # then fill in the blanks
```

### 4. Deploy with Dokploy

`docker-compose.yml` is the production file — it builds the image, mounts
the `gate-data` volume, and does **not** publish any host port. Dokploy's
Traefik reaches the container over the internal Docker network, so nothing
but Dokploy's own reverse proxy is ever exposed to the internet.

1. In Dokploy, create a **Compose** application pointing at this repo/branch
   (it will use `docker-compose.yml` automatically).
2. Set the env vars from `.env` in Dokploy's environment settings (or point
   it at an env file) — never commit `.env` itself.
3. Add a domain: `garage.asafshilo.com` → service `garage-gate`, container
   port `8000`. Dokploy/Traefik terminates SSL and proxies to that port.

Public links live at `/<token>`, the admin panel at `/admin/`. The SQLite
database lives on the `gate-data` volume (`/data/links.db`), so links
survive redeploys.

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
