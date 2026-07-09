# Admin open button + expired-link handling — design

Date: 2026-07-10

Two independent features for the garage-gate site.

## Feature 1 — Admin direct-open button

An admin logged into the panel needs a one-tap way to open the gate directly,
without creating a link. It always works (no token, no expiry) and gives clear
press feedback.

### Backend

New route in `app/admin.py`:

- `POST /admin/open`, decorated with `@login_required`, calling `_check_csrf()`.
- Calls `current_app.config["GATE_OPENER"]()` directly.
- Returns `204 No Content` on success.
- On a `GATE_OPENER` exception: `log.exception(...)` and return `500` (mirrors the
  public `open_gate` error handling). This is a fetch endpoint — no template.

CSRF: the client sends the existing `csrf_token` as form data, so `_check_csrf()`
(which reads `request.form["csrf_token"]`) is reused unchanged.

### Frontend

A button at the top of the panel card in `app/templates/panel.html`, above the
duration/create form. It is present regardless of the create/result state.

Interaction:

- A normal click (not the public page's long-press).
- On press: disable the button and show a circular spinner.
- The spinner stays until the server responds, with a **0.5s minimum** so it never
  just flashes.
- On success: brief ✓ state, then re-enable. On failure (non-2xx or network error):
  brief error state, then re-enable so the admin can retry.

The button is self-contained (its own small script block), independent of the
create-link and revoke flows already on the page.

## Feature 2 — Expired link lands on the invalid page

When a visitor presses the open button on a link that has since expired, they must
land on the existing invalid page (`invalid.html`, "הלינק לא טוב"), not the
"משהו השתבש" failure state.

Current state: `POST /<token>/open` already returns `invalid.html` with `404` for an
expired/revoked/unknown token (`use_link()` returns `False` → `_invalid()`). The
client JS in `confirm.html` intends to handle this (`resp.status === 404` →
`window.location.reload()`), but the reported behaviour is the `#failed`
("משהו השתבש") state instead.

Plan:

- Drive the real flow during implementation (systematic-debugging) to find exactly
  where an expired token falls through to `#failed`, and fix it so the visitor
  reliably lands on `invalid.html`.
- Reuse `invalid.html` for all bad-token cases (expired, revoked, unknown) — no new
  page.
- Add a regression test so an expired token can't silently start showing the failure
  state again.

## Testing

pytest, matching the existing `tests/` layout:

- `POST /admin/open`: success returns 204 and invokes the gate opener; requires auth
  (redirect when logged out); requires valid CSRF (400 otherwise); returns 500 when
  the gate opener raises.
- Public flow: `POST /<token>/open` on an expired token returns `invalid.html` with
  status 404.

## Out of scope

- No change to link creation, revocation, or the long-press public UX.
- No new "expired" page or copy distinct from the existing invalid page.
