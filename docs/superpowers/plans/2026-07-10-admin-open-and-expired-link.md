# Admin Open Button + Expired-Link Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an always-works "open gate" button to the admin panel, and make an expired link land the visitor on the existing invalid page instead of the "משהו השתבש" failure state.

**Architecture:** A new authenticated `POST /admin/open` route calls the existing `GATE_OPENER` directly (no token/expiry), returning bare `204`/`500` for a fetch-driven button. The panel gets a self-contained button + script that shows a spinner (0.5s minimum) then a success/error flash. Feature 2 locks the server's invalid-token contract with a regression test and verifies the public page's client flow lands on `invalid.html`.

**Tech Stack:** Flask (blueprints, Jinja templates), SQLite, vanilla JS, pytest.

## Global Constraints

- Admin routes live under the `/admin` prefix (blueprint `admin`, registered in `app/__init__.py`).
- CSRF for admin POSTs is enforced by `_check_csrf()`, which reads `request.form["csrf_token"]` and compares against `session["csrf_token"]`; a mismatch `abort(400)`s.
- Admin routes require `@login_required`; unauthenticated requests get a `302` redirect to `admin.login`.
- The public invalid page is `app/templates/invalid.html` (Hebrew copy "הלינק לא טוב"); reuse it for all bad-token cases — do NOT add a new "expired" page.
- Gate calls go only through `current_app.config["GATE_OPENER"]()`; a failure is logged with `log.exception(...)`.
- Tests use the fixtures in `tests/conftest.py` (`client`, `app`, `gate` where `gate` is a `FakeGate` with `.calls` and `.fail`), the `login()` helper from `tests/test_admin_auth.py`, and `base_url=ADMIN`/`PUBLIC`.

---

## File Structure

- `app/admin.py` — add `logging` + a `POST /admin/open` route (Feature 1 backend).
- `app/templates/panel.html` — add the open-gate button, its styles, and its script (Feature 1 frontend).
- `app/templates/confirm.html` — verify/harden the client's 404→invalid handling (Feature 2 frontend).
- `tests/test_admin_open.py` — new test module for the admin open route (Feature 1).
- `tests/test_public.py` — add an expired-token POST regression test (Feature 2).

---

## Task 1: Admin `POST /admin/open` route

**Files:**
- Modify: `app/admin.py` (add `import logging`, module `log`, and the `open_gate` view)
- Test: `tests/test_admin_open.py` (create)

**Interfaces:**
- Consumes: `current_app.config["GATE_OPENER"]()` (0-arg callable, raises on failure); `login_required`, `_check_csrf` (already in `app/admin.py`); test helpers `login` (from `tests/test_admin_auth.py`), `get_csrf` (from `tests/test_admin_panel.py`).
- Produces: endpoint `admin.open_gate` at `POST /admin/open` → `204` on success, `500` on gate failure, `400` on bad CSRF, `302` when unauthenticated. Bare bodies (no template).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_admin_open.py`:

```python
from tests.conftest import ADMIN
from tests.test_admin_auth import login
from tests.test_admin_panel import get_csrf


def test_open_calls_gate_and_returns_204(client, gate):
    login(client)
    csrf = get_csrf(client)
    resp = client.post("/admin/open", data={"csrf_token": csrf}, base_url=ADMIN)
    assert resp.status_code == 204
    assert gate.calls == 1


def test_open_requires_auth(client, gate):
    resp = client.post("/admin/open", data={"csrf_token": "x"}, base_url=ADMIN)
    assert resp.status_code == 302
    assert gate.calls == 0


def test_open_rejects_bad_csrf(client, gate):
    login(client)
    get_csrf(client)  # ensures a token exists in session
    resp = client.post("/admin/open", data={"csrf_token": "wrong"}, base_url=ADMIN)
    assert resp.status_code == 400
    assert gate.calls == 0


def test_open_returns_500_when_gate_fails(client, gate):
    login(client)
    gate.fail = True
    csrf = get_csrf(client)
    resp = client.post("/admin/open", data={"csrf_token": csrf}, base_url=ADMIN)
    assert resp.status_code == 500
    assert gate.calls == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_admin_open.py -v`
Expected: FAIL — the four tests fail (404 Not Found, since `/admin/open` does not exist yet).

- [ ] **Step 3: Add logging to `app/admin.py`**

At the top of `app/admin.py`, add the stdlib import alongside the existing `import hmac` / `import secrets`:

```python
import hmac
import logging
import secrets
```

Immediately after `bp = Blueprint("admin", __name__)` and `oauth = OAuth()`, add:

```python
log = logging.getLogger(__name__)
```

- [ ] **Step 4: Add the route to `app/admin.py`**

Append this view (e.g. after `revoke_link`):

```python
@bp.post("/open")
@login_required
def open_gate():
    _check_csrf()
    try:
        current_app.config["GATE_OPENER"]()
    except Exception:
        log.exception("Home Assistant gate call failed")
        return "", 500
    return "", 204
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_admin_open.py -v`
Expected: PASS — all four tests pass.

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS — the whole suite is green.

- [ ] **Step 7: Commit**

```bash
git add app/admin.py tests/test_admin_open.py
git commit -m "Add authenticated /admin/open route for direct gate opening"
```

---

## Task 2: Admin panel open-gate button

**Files:**
- Modify: `app/templates/panel.html` (add button markup in `{% block body %}`, styles in `{% block style %}`, script in `{% block scripts %}`)
- Test: `tests/test_admin_open.py` (add one render assertion)

**Interfaces:**
- Consumes: `admin.open_gate` (`POST /admin/open`, form field `csrf_token`, returns `204`/`500`); `csrf_token` is already passed to `panel.html` by `_render_panel`.
- Produces: a `#admin-open-btn` button carrying `data-csrf="{{ csrf_token }}"`, present in both the create and result states of the panel.

- [ ] **Step 1: Write the failing render test**

Add to `tests/test_admin_open.py`:

```python
from tests.test_admin_panel import get_csrf as _get_csrf  # noqa: F401  (already imported above)


def test_panel_renders_open_button(client):
    login(client)
    resp = client.get("/admin/", base_url=ADMIN)
    assert resp.status_code == 200
    assert b'id="admin-open-btn"' in resp.data
```

Note: `login` and `ADMIN` are already imported at the top of the module from Task 1; do not duplicate those imports. The `_get_csrf` alias line above is unnecessary — omit it and just add the single `test_panel_renders_open_button` function.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_admin_open.py::test_panel_renders_open_button -v`
Expected: FAIL — `id="admin-open-btn"` is not in the panel HTML.

- [ ] **Step 3: Add the button markup to `app/templates/panel.html`**

Inside `{% block body %}`, immediately after `<main class="wide">` and before the existing `<section class="panel-card">`, insert:

```html
  <section class="panel-card open-now">
    <button id="admin-open-btn" class="open-btn" type="button"
            data-csrf="{{ csrf_token }}" aria-label="Open the gate now">
      <span class="open-spinner" aria-hidden="true"></span>
      <span class="open-check" aria-hidden="true">✓</span>
      <span class="open-cross" aria-hidden="true">✕</span>
      <span class="open-label">Open gate</span>
    </button>
  </section>
```

- [ ] **Step 4: Add the button styles to `app/templates/panel.html`**

Inside `{% block style %}`, at the end (before `{% endblock %}`), add:

```css
    .open-now { display: grid; }
    .open-btn {
      position: relative;
      display: flex; align-items: center; justify-content: center; gap: 0.6rem;
      width: 100%; font: inherit; font-weight: 650; font-size: 1.05rem; cursor: pointer;
      color: #fff; border: 0; border-radius: 12px; padding: 1rem;
      background: radial-gradient(circle at 50% 30%, #ff6b5e 0%, #ef4444 55%, #b91c1c 100%);
      box-shadow: 0 6px 16px rgba(239, 68, 68, 0.28);
      transition: transform 0.1s, filter 0.15s;
    }
    .open-btn:active { transform: scale(0.98); filter: brightness(0.96); }
    .open-btn:disabled { cursor: default; }
    .open-btn.ok { background: linear-gradient(180deg, #34d399, #059669); }
    .open-btn.err { background: linear-gradient(180deg, #f87171, #b91c1c); }

    .open-spinner, .open-check, .open-cross { display: none; }
    .open-btn.busy .open-label { visibility: hidden; }
    .open-btn.busy .open-spinner {
      display: block; position: absolute;
      width: 1.4rem; height: 1.4rem; border-radius: 50%;
      border: 3px solid rgba(255, 255, 255, 0.35); border-top-color: #fff;
      animation: open-spin 0.7s linear infinite;
    }
    .open-btn.ok .open-label, .open-btn.err .open-label { visibility: hidden; }
    .open-btn.ok .open-check,
    .open-btn.err .open-cross { display: block; position: absolute; font-size: 1.4rem; }
    @keyframes open-spin { to { transform: rotate(360deg); } }
```

- [ ] **Step 5: Add the button script to `app/templates/panel.html`**

Inside `{% block scripts %}`, add a new `<script>` block (after the existing one, before `{% endblock %}`):

```html
<script>
  (function () {
    var btn = document.getElementById("admin-open-btn");
    if (!btn) return;
    var MIN_MS = 500;   // keep the spinner visible at least this long
    var FLASH_MS = 1200; // how long the ✓ / ✕ result stays before reset

    btn.addEventListener("click", async function () {
      if (btn.disabled) return;
      btn.disabled = true;
      btn.classList.remove("ok", "err");
      btn.classList.add("busy");
      var started = performance.now();
      var ok = false;
      try {
        var body = new FormData();
        body.append("csrf_token", btn.dataset.csrf);
        var resp = await fetch("/admin/open", { method: "POST", body: body });
        ok = resp.ok;
      } catch (e) { /* network failure -> treated as error */ }
      var elapsed = performance.now() - started;
      if (elapsed < MIN_MS) {
        await new Promise(function (r) { setTimeout(r, MIN_MS - elapsed); });
      }
      btn.classList.remove("busy");
      btn.classList.add(ok ? "ok" : "err");
      setTimeout(function () {
        btn.classList.remove("ok", "err");
        btn.disabled = false;
      }, FLASH_MS);
    });
  })();
</script>
```

- [ ] **Step 6: Run the render test + full suite**

Run: `python -m pytest tests/test_admin_open.py -v && python -m pytest -q`
Expected: PASS — including `test_panel_renders_open_button`.

- [ ] **Step 7: Verify in the browser**

Start the app (see the repo README / `wsgi.py`; a dev run is `flask --app wsgi run` with the test-style env, or use the preview tooling). Log into `/admin/`, click **Open gate**, and confirm: the spinner shows for ≥0.5s, then a green ✓ flash, then the button re-enables; the `FakeGate`/HA receives one call. Then force a failure (e.g. temporarily point `HA_WEBHOOK_URL` at an unreachable URL) and confirm the button flashes red ✕ and re-enables.

- [ ] **Step 8: Commit**

```bash
git add app/templates/panel.html tests/test_admin_open.py
git commit -m "Add admin panel open-gate button with spinner feedback"
```

---

## Task 3: Expired link lands on the invalid page

**Files:**
- Test: `tests/test_public.py` (add an expired-token POST regression test)
- Modify (only if reproduction requires it): `app/templates/confirm.html` (client 404→invalid handling in `openGate`)

**Interfaces:**
- Consumes: `POST /<token>/open` → `public.open_gate`, which returns `invalid.html` with status `404` for an expired/revoked/unknown token (`db.use_link` returns `False` → `_invalid()`); `make_link(app, minutes=-5)` creates an already-expired link; `gate.calls`.
- Produces: locked server contract (expired token POST → 404 + `invalid.html`, gate not called) and a public page whose client flow lands the visitor on the invalid page rather than the `#failed` ("משהו השתבש") state.

- [ ] **Step 1: Reproduce the reported behavior (systematic-debugging)**

Use superpowers:systematic-debugging. Drive the real client flow with the preview browser:
1. Create a valid link (admin panel) and open its public URL — the long-press button renders.
2. Invalidate the token behind the open page: revoke it from the admin panel (revoked tokens are treated the same as expired by `use_link`), OR create a link with a very short duration and wait it out.
3. Long-press the button and observe. Capture what the visitor sees (invalid page vs. "משהו השתבש") and the `POST /<token>/open` response status via the network panel.

Record the finding: the server should return `404` with `invalid.html`; the client's `openGate` handles `resp.status === 404` by calling `window.location.reload()`, which should re-render the invalid page. Confirm whether the visitor actually lands there.

- [ ] **Step 2: Write the failing/locking server-contract test**

Add to `tests/test_public.py`:

```python
def test_post_on_expired_token_shows_invalid_page(client, app, gate):
    link = make_link(app, minutes=-5)  # already expired
    resp = post_open(client, link["token"])
    assert resp.status_code == 404
    assert gate.calls == 0
    assert "הלינק לא טוב".encode() in resp.data
```

- [ ] **Step 3: Run the test**

Run: `python -m pytest tests/test_public.py::test_post_on_expired_token_shows_invalid_page -v`
Expected: PASS if the server contract already holds (the existing `_invalid()` returns 404 + `invalid.html`). This test locks that contract against regressions. If it FAILS, the server side is the bug — fix `public.open_gate`/`_invalid` so an expired token returns `invalid.html` with 404 and does not call the gate, then re-run to green.

- [ ] **Step 4: Fix the client handling if Step 1 showed the failure state**

If (and only if) Step 1 showed the visitor landing on "משהו השתבש" for an invalidated token, harden `openGate` in `app/templates/confirm.html` so the 404 case deterministically shows the invalid page. Replace the invalid branch:

```javascript
    } else if (invalid) {
      window.location.reload(); // server renders the generic invalid page
    } else {
```

with a full navigation to the token page (a fresh GET the server renders as `invalid.html`), which does not depend on reload/cache semantics:

```javascript
    } else if (invalid) {
      // token no longer valid — load the page fresh so the server renders
      // the generic invalid page instead of leaving the user on this one
      window.location.assign(window.location.pathname);
    } else {
```

If Step 1 showed it already lands on the invalid page correctly, make no client change — the regression test in Step 2 is the deliverable.

- [ ] **Step 5: Re-verify the full flow in the browser**

Repeat the Step 1 reproduction end-to-end and confirm the visitor now lands on the invalid page ("הלינק לא טוב"), with no "משהו השתבש".

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — whole suite green.

- [ ] **Step 7: Commit**

```bash
git add tests/test_public.py app/templates/confirm.html
git commit -m "Lock expired-link flow: land on invalid page, not error state"
```

Note: if Step 4 made no change to `confirm.html`, drop it from the `git add` (commit only `tests/test_public.py`).

---

## Final verification

- [ ] **Run the entire test suite**

Run: `python -m pytest -q`
Expected: PASS — all tests green, including the new `tests/test_admin_open.py` and the expired-token test.

- [ ] **Manual smoke (browser)**

Admin panel: **Open gate** button works with spinner + success/error flash. Public: an invalidated link's button press lands on the invalid page.

---

## Self-Review Notes

- **Spec coverage:** Feature 1 backend → Task 1; Feature 1 frontend → Task 2; Feature 2 (reuse invalid page, fix flow, regression test) → Task 3. Testing section → tests in Tasks 1–3. All spec sections covered.
- **CSRF:** button sends `csrf_token` as form data; `_check_csrf()` reads `request.form["csrf_token"]` — consistent.
- **Types/names:** endpoint `admin.open_gate` at `/admin/open`; button id `admin-open-btn`; helpers `login`/`get_csrf` used as they exist in the test suite.
