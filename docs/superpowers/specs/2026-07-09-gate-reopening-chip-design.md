# "לא נפתח?" Reopening Chip — Design

## Problem

After a user long-presses the big red button and the gate command succeeds, the
confirm page swaps to the `#success` stage showing "תודווווות" with confetti.
If the gate didn't actually open (e.g. the physical gate missed the signal),
the user is stuck on the thank-you screen with no way to retry short of
reloading or re-opening the link.

## Solution

Add a small, low-emphasis chip button labeled **"לא נפתח?"** to the `#success`
stage. Tapping it resets the page back to the `#ready` stage so the user can
long-press the button and re-issue the open command.

This is safe because `db.use_link` records `used_at` but does **not** invalidate
the link — the token stays valid until it expires or is revoked. Re-posting to
`/{{ token }}/open` therefore succeeds again with no reload.

## Scope

Single-file, client-side change to `app/templates/confirm.html`. No changes to
`public.py`, `db.py`, or any server route.

## Behavior

- The chip appears below the "תודווווות" heading inside `#success`.
- On tap ("reset in place"):
  - Hide `#success`, show `#ready`.
  - Reset button state: `opened = false`, `btn.disabled = false`, remove the
    `holding` class, clear the ring progress (`--p = 0`).
  - Stop and clear the confetti canvas so it doesn't keep animating over the
    ready stage.
- The user can then long-press again exactly as the first time.

## Design details

- **Confetti reset:** confetti currently runs its own `requestAnimationFrame`
  loop with a 4-second refill window and no external stop handle. Introduce a
  cancel flag (or store the raf id / a `confettiActive` boolean) so the reset
  can halt the loop and clear the canvas immediately.
- **Styling:** a quiet pill/text chip (muted color, small font, subtle border),
  visually subordinate to the celebratory heading — an escape hatch, not a
  primary action. Reuse existing CSS variables/theme from `base.html`.

## Out of scope

- No server-side retry limits or logging changes.
- No change to the `#failed` stage (it already leaves `#ready` reset paths
  untouched; retry-from-failure is a separate concern if ever wanted).

## Testing

Existing tests cover the server routes and link reuse
(`tests/test_public.py`). This change is purely presentational/client-side;
verify manually in the preview by opening a link, completing a long-press,
tapping the chip, and confirming the ready stage returns and a second
long-press opens the gate again.
