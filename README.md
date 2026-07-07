# garage-gate

Self-hosted temporary-link service for opening a gate through Home Assistant.

- **Public:** `https://garage.asafshilo.com/<token>` shows an "Open gate" button.
  Tapping it consumes the single-use link and triggers the HA script that opens
  the gate. Expired / used / revoked / unknown tokens all show the same generic
  "link invalid" page.
- **Admin:** `https://admin.asafshilo.com/` — Google login (allowlisted emails
  only) with a form to create links (expiry in minutes/hours, optional label)
  and a list of active links with revoke buttons.

Links expire on **first use or the time limit, whichever comes first**.
Visiting a link (GET) does *not* consume it — only tapping the button does —
so WhatsApp/Telegram link previews can't burn a token.

## Setup

### 1. Google OAuth credentials

1. In [Google Cloud Console → APIs & Credentials](https://console.cloud.google.com/apis/credentials),
   create an **OAuth client ID** of type **Web application**.
2. Add the authorized redirect URI: `https://admin.asafshilo.com/auth/callback`
3. Put the client ID and secret in `.env`.

### 2. Home Assistant

Create a long-lived access token (HA → your profile → Security) and put it in
`.env` as `HA_TOKEN`, together with `HA_URL` (reachable from the container) and
the script entity id (`HA_SCRIPT_ENTITY`).

### 3. Environment

```
cp .env.example .env   # then fill in the blanks
```

### 4. Deploy with Dokploy

Create a Compose (or Dockerfile) application pointing at this repo, set the
env vars from `.env` in Dokploy's environment settings, and attach **both**
domains to the service on port 8000:

- `garage.asafshilo.com`
- `admin.asafshilo.com`

Dokploy/Traefik terminates SSL for both; the app decides which routes each
hostname may reach (`PUBLIC_HOST` / `ADMIN_HOST`). Requests for the wrong
host get a 404.

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

## Notes / limitations

- If the HA call fails after a link was claimed, the link stays consumed
  (visitor sees an error page and can ask you for a new link). A log line
  with the traceback is written.
- No rate limiting in the app; add Traefik middleware later if token probing
  ever becomes a concern (tokens are 256-bit random, so guessing is not
  realistic).
