# garage-gate

Self-hosted temporary-link service for opening a gate through Home Assistant.

- **Public:** `https://garage.asafshilo.com/<token>` shows a hold-to-open
  button; holding it 2 seconds triggers the HA webhook that opens the gate.
  Links can be used any number of times until they expire or are revoked.
  Expired / revoked / unknown tokens all show the same generic
  "link invalid" page.
- **Admin:** `https://garage.asafshilo.com/admin/` — Google login (allowlisted
  emails only) with a form to create links (expiry in minutes/hours, optional
  label) and a list of active links with revoke buttons. The admin panel is an
  installable **PWA** (see below), so it can live on the owner's home screen as
  a one-tap gate remote.

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
(e.g. `http://host.docker.internal:8123/api/webhook/<webhook-id>`). The
webhook id is the secret — it is only ever used server-side.

This requires no Tailscale dependency. HA runs with `network_mode: host` and
no `http: server_host` restriction, so it listens on `0.0.0.0:8123` and
accepts connections on every host address, including the Docker bridge
gateway that `host.docker.internal` resolves to.

What does block a container is **ufw**, whose default INPUT policy denies
traffic arriving from Docker bridges. Because it drops rather than rejects,
the symptom is a silent timeout, not "connection refused". The host needs
one rule:

```bash
sudo ufw allow from 10.77.0.0/24 to any port 8123 proto tcp
```

That matches on **source address**, which is why `docker-compose.yml` pins
this app's network to `10.77.0.0/24` instead of letting Docker auto-assign a
`/16` from `172.16.0.0/12`. An auto-assigned subnet (and the `br-<netid>`
bridge name that goes with it) can change whenever the stack is recreated,
which would silently stop the rule from matching. **The pinned subnet and
the ufw rule must be kept in sync**, and the rule is scoped to this app
alone — no other container on the host can reach HA on 8123.

If the gate stops opening after a redeploy, check that the rule's subnet
still matches the compose file before looking anywhere else. To confirm the
path end to end:

```bash
docker exec <garage-gate-container> \
  python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8123/', timeout=5).status)"
```

A timeout means the firewall; a refusal would mean HA itself is not
listening. Note that a container's packet to HA's Tailscale IP leaves via
its bridge gateway and arrives on a Docker bridge, *not* on `tailscale0`, so
allowing `tailscale0` in ufw does nothing for container traffic.

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

## PWA (installable admin app)

The admin panel is a Progressive Web App scoped to `/admin/`, so the owner can
"Add to Home Screen" and launch it standalone (no browser chrome) as a quick
gate remote. It is made up of:

- `GET /admin/manifest.webmanifest` — the web app manifest (name, icons,
  `standalone` display, `start_url`/`scope` = `/admin/`, brand colors).
- `GET /admin/sw.js` — a service worker (scope `/admin/`) that precaches the
  icons and an offline page, serves navigations network-first, and falls back
  to `GET /admin/offline` when there's no connection. Opening the gate always
  hits the network, so nothing gate-related is served stale from cache.
- Icons under `app/static/icons/` generated by `scripts/gen_icons.py`
  (needs Pillow). Rerun that script and bump `PWA_VERSION` in `app/admin.py`
  whenever the shell (manifest, icons, or worker) changes so clients refresh.

The manifest, worker, and offline page are intentionally unauthenticated; the
panel itself still requires a Google login.

## Notes / limitations

- If the HA call fails, the visitor sees an error page and can try again —
  links are reusable, so a failed attempt doesn't burn the link. A log line
  with the traceback is written server-side.
- No rate limiting in the app; add Traefik middleware later if token probing
  ever becomes a concern (tokens are 256-bit random, so guessing is not
  realistic).
