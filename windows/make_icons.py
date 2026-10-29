"""Builds the Windows icons in windows/: AppIcon.ico (Start menu shortcut, from assets/AppIcon.png) and
the tray glyphs in windows/icons/. The glyph is menubar.py's brand_glyph() redrawn with Pillow, same
geometry: the swoosh ring with its two sparkles, the voice wave inside (idle, recording) or a sparkle
(loading, transcribing, cleaning up). Run again only if the logo changes (needs Pillow, not the app):
    python windows/make_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "windows", "icons")
S = 512 / 30              # the glyph is 30x20 pt; drawn on a 30x30 square, 512 px, centred vertically
TRAY_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64)]
COLORS = {"white": (255, 255, 255), "black": (28, 28, 28),       # dark / light taskbar
          "red": (255, 69, 58)}                                   # recording, on either taskbar


def pt(x: float, y: float) -> tuple[float, float]:
    """menubar.py's points (origin bottom left, y up, 30x20) -> pixels (origin top left)."""
    return x * S, (25 - y) * S


def star(cx: float, cy: float, rx: float, ry: float) -> list:
    """menubar.py's _star(): four cubic curves with both control points on the same spot, sampled."""
    k, pts, start = 0.18, [], (cx, cy + ry)
    for x, y, sx, sy in ((cx + rx, cy, 1, 1), (cx, cy - ry, 1, -1), (cx - rx, cy, -1, -1), (cx, cy + ry, -1, 1)):
        c = (cx + sx * rx * k, cy + sy * ry * k)
        for i in range(16):
            t = i / 16
            a, b, d = (1 - t) ** 3, 3 * (1 - t) * t, t ** 3       # cubic with p1 == p2 == c
            pts.append(pt(a * start[0] + b * c[0] + d * x, a * start[1] + b * c[1] + d * y))
        start = (x, y)
    return pts


def glyph(center: str) -> Image.Image:
    """White-on-transparent mask of the glyph, `center` = "wave" or "sparkle"."""
    img = Image.new("L", (512, 512), 0)
    d = ImageDraw.Draw(img)
    (x0, y1), (x1, y0) = pt(1, 4), pt(29, 16)
    d.ellipse((x0, y0, x1, y1), fill=255)
    (x0, y1), (x1, y0) = pt(3.6, 5.6), pt(26.4, 14.4)
    d.ellipse((x0, y0, x1, y1), fill=0)
    for s in [(17.5, 15.6, 1.7, 3.9), (12.5, 4.4, 1.7, 3.9)] + (
            [(15, 10, 2.6, 3.4), (20.4, 11.6, 0.9, 1.3)] if center == "sparkle" else []):
        d.polygon(star(*s), fill=255)
    for a in (math.radians(35), math.radians(215)):                 # the two cuts that make the ring a swoosh
        d.line([pt(15 + 11 * math.cos(a), 10 + 4 * math.sin(a)), pt(15 + 15 * math.cos(a), 10 + 7 * math.sin(a))],
               fill=0, width=round(0.9 * S))
    if center == "wave":
        for i, h in enumerate((2.2, 4.6, 6.6, 4.6, 2.2)):
            (x0, y1), (x1, y0) = pt(15 + (i - 2) * 2.6 - 0.7, 10 - h / 2), pt(15 + (i - 2) * 2.6 + 0.7, 10 + h / 2)
            d.rounded_rectangle((x0, y0, x1, y1), radius=0.7 * S, fill=255)
    return img


def save(mask: Image.Image, color: str, name: str) -> None:
    icon = Image.new("RGBA", mask.size, COLORS[color] + (0,))
    icon.putalpha(mask)
    icon.save(os.path.join(OUT, name), sizes=TRAY_SIZES)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    wave, sparkle = glyph("wave"), glyph("sparkle")
    for color in ("white", "black"):
        save(wave, color, f"idle-{color}.ico")
        save(sparkle, color, f"busy-{color}.ico")
    save(wave, "red", "recording.ico")
    Image.open(os.path.join(ROOT, "assets", "AppIcon.png")).save(
        os.path.join(ROOT, "windows", "AppIcon.ico"), sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    print("wrote windows/AppIcon.ico and windows/icons/*.ico")
