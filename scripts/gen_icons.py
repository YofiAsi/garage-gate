"""Generate PWA icons for the Garage Gate app.

Draws the app's red "open" button with a white padlock (the same glyph used on
the confirm page) on the dark app background. Run from the repo root:

    python3 scripts/gen_icons.py

Regenerate whenever the icon design changes.
"""

import math
import os

from PIL import Image, ImageDraw

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "static", "icons")

BG_TOP = (43, 58, 85)     # #2b3a55 – matches base.html radial glow
BG_BASE = (11, 17, 32)    # #0b1120 – app background
RED_LIGHT = (255, 107, 94)  # #ff6b5e
RED_MID = (239, 68, 68)     # #ef4444
RED_DARK = (185, 28, 28)    # #b91c1c


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _radial(size, inner, outer, cx, cy, radius):
    """Cheap radial gradient rendered per-pixel into an RGBA image."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / radius
            px[x, y] = _lerp(inner, outer, min(1.0, d))
    return img


def _padlock(draw, cx, cy, scale, color):
    """Draw the padlock glyph (24x24 viewBox from confirm.html) centred at cx,cy."""
    def sx(v):
        return cx + (v - 12) * scale
    def sy(v):
        return cy + (v - 12) * scale  # glyph spans y 3.5..20.5, centre ~12

    stroke = max(2, round(1.9 * scale))

    # body: rect x=4.5 y=10.5 w=15 h=10 rx=2.5
    draw.rounded_rectangle(
        [sx(4.5), sy(10.5), sx(19.5), sy(20.5)],
        radius=2.5 * scale, fill=color,
    )
    # shackle: arc from (8,10.5) up over a 4-radius semicircle to (16,10.5)
    r = 4 * scale
    ax, ay = sx(12), sy(7.5)
    draw.arc(
        [ax - r, ay - r, ax + r, ay + r],
        start=180, end=360, fill=color, width=stroke,
    )
    # keyhole punched clean through the body so the red button shows through
    kr = 1.5 * scale
    kx, ky = sx(12), sy(15.5)
    draw.ellipse([kx - kr, ky - kr, kx + kr, ky + kr], fill=(0, 0, 0, 0))


def make_icon(size, maskable=False):
    img = _radial(size, BG_TOP, BG_BASE, size * 0.5, -size * 0.2, size * 1.1)

    # button occupies less area on maskable icons so it stays inside the safe zone
    btn_frac = 0.62 if maskable else 0.74
    btn_r = size * btn_frac / 2
    cx = cy = size / 2

    button = _radial(
        size, RED_LIGHT, RED_DARK,
        cx, cy - btn_r * 0.35, btn_r * 1.15,
    ).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse(
        [cx - btn_r, cy - btn_r, cx + btn_r, cy + btn_r], fill=255
    )
    base = img.convert("RGBA")
    base.paste(button, (0, 0), mask)

    # Draw the padlock on its own layer and erase the keyhole to transparent,
    # then composite so the red button shows through the hole.
    lock = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    _padlock(ImageDraw.Draw(lock), cx, cy, btn_r / 14.0, (255, 255, 255))
    base = Image.alpha_composite(base, lock)
    return base.convert("RGB")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    make_icon(192).save(os.path.join(OUT_DIR, "icon-192.png"))
    make_icon(512).save(os.path.join(OUT_DIR, "icon-512.png"))
    make_icon(512, maskable=True).save(os.path.join(OUT_DIR, "icon-maskable-512.png"))
    make_icon(180).save(os.path.join(OUT_DIR, "apple-touch-icon.png"))
    print("Icons written to", os.path.normpath(OUT_DIR))


if __name__ == "__main__":
    main()
