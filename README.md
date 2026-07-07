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

### 3. Environment

```
cp .env.example .env   # then fill in the blanks
```

### 4. Deploy with Dokploy

Create a Compose (or Dockerfile) application pointing at this repo, set the
env vars from `.env` in Dokploy's environment settings, and attach the domain
`garage.asafshilo.com` to the service on port 8000. Dokploy/Traefik terminates
SSL; public links live at `/<token>` and the admin panel at `/admin/`.

The SQLite database lives on the `gate-data` volume (`/data/links.db`), so
links survive redeploys.

## Development

```
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
.venv/Scripts/python -m pytest
```

Run locally (needs a filled `.env`; Flask dev server, hostnames won't match —
use the test suite or Docker for realistic behavior):

```
.venv/Scripts/python -m flask --app wsgi run
```

### Testing Google login locally

Add `http://localhost:18000/admin/auth/callback` as an extra authorized
redirect URI in the Google console, set `INSECURE_HTTP=1` in your local
`.env` (never in production), and `docker compose up`. The app builds the
redirect URI from the request scheme (behind Traefik, `X-Forwarded-Proto`
makes it https automatically).

## Notes / limitations

- If the HA call fails after a link was claimed, the link stays consumed
  (visitor sees an error page and can ask you for a new link). A log line
  with the traceback is written.
- No rate limiting in the app; add Traefik middleware later if token probing
  ever becomes a concern (tokens are 256-bit random, so guessing is not
  realistic).
