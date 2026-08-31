# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Cut every app icon from one piece of branding artwork.

    python scripts/make_icons.py [source.png]

Writes the Tauri bundle icons (window, taskbar, installer, Store tiles)
and the web assets the front-end uses (favicon + the in-app mark), all
from `branding/forgeassembler_icon.png` so they cannot drift apart.

Why not `tauri icon`? The artwork is a glowing forge, and its halo fades
to a 2%-opacity fringe that extends a quarter of the way past the
subject. Anything that trims on "any non-transparent pixel" — `tauri
icon` included — sizes the icon to the halo, which lands the subject at
about three quarters the size it should be and reads as a shrunken
taskbar icon. Here the crop ignores the fringe (see ALPHA_FLOOR) so the
subject itself fills the tile.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "branding" / "forgeassembler_icon.png"
TAURI_ICONS = ROOT / "ui" / "web" / "src-tauri" / "icons"
WEB_PUBLIC = ROOT / "ui" / "web" / "public"

# Fraction of the canvas the artwork's longer axis fills. 0.98 leaves a
# whisker of margin so nothing clips against a tile edge, and matches the
# icon this set replaced (which measured 98%).
BLEED = 0.98

# Alpha below this counts as the glow's outer fringe, not as artwork, and
# is cropped away. The halo falls off steeply — every threshold from 8 to
# 128 crops within 5% of the same box — so this is not a delicate number.
# What matters is that it is above zero: at zero the crop follows a
# 2%-opacity haze and the visible subject shrinks by a quarter.
ALPHA_FLOOR = 16

# Square PNGs Tauri's bundler expects, plus the Windows Store tiles.
SQUARE_PNGS: dict[str, int] = {
    "32x32.png": 32,
    "64x64.png": 64,
    "128x128.png": 128,
    "128x128@2x.png": 256,
    "icon.png": 512,
    "Square30x30Logo.png": 30,
    "Square44x44Logo.png": 44,
    "Square71x71Logo.png": 71,
    "Square89x89Logo.png": 89,
    "Square107x107Logo.png": 107,
    "Square142x142Logo.png": 142,
    "Square150x150Logo.png": 150,
    "Square284x284Logo.png": 284,
    "Square310x310Logo.png": 310,
    "StoreLogo.png": 50,
}

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def trim(src: Image.Image) -> Image.Image:
    """The subject alone, with the transparent margin and the glow's
    near-invisible outer fringe cropped away."""
    solid = src.getchannel("A").point(lambda v: 255 if v > ALPHA_FLOOR else 0)
    box = solid.getbbox()
    if box is None:
        raise SystemExit(f"nothing in {src.size} source is more opaque than {ALPHA_FLOOR}")
    return src.crop(box)


def square(art: Image.Image, size: int) -> Image.Image:
    """`art` centered on a transparent square, filling BLEED of it.

    The artwork is taller than it is wide, so height sets the scale and
    the narrow axis keeps its own margin — squashing it to fill both
    axes would distort the mark.
    """
    scale = size * BLEED / max(art.size)
    w, h = max(1, round(art.width * scale)), max(1, round(art.height * scale))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(art.resize((w, h), Image.LANCZOS), ((size - w) // 2, (size - h) // 2))
    return out


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        raise SystemExit(f"no such source image: {source}")

    art = trim(Image.open(source).convert("RGBA"))
    print(f"source {source.name}: artwork is {art.width}x{art.height} after trimming")

    TAURI_ICONS.mkdir(parents=True, exist_ok=True)
    WEB_PUBLIC.mkdir(parents=True, exist_ok=True)

    for name, px in sorted(SQUARE_PNGS.items(), key=lambda kv: kv[1]):
        square(art, px).save(TAURI_ICONS / name, optimize=True)
    print(f"  {len(SQUARE_PNGS)} square PNGs -> {TAURI_ICONS.relative_to(ROOT)}")

    # One multi-resolution .ico: Windows picks the size it needs per
    # surface (16 in the title bar, 32 in the taskbar, 256 in Explorer).
    square(art, 256).save(
        TAURI_ICONS / "icon.ico",
        sizes=[(s, s) for s in ICO_SIZES],
    )
    print(f"  icon.ico with {len(ICO_SIZES)} sizes: {ICO_SIZES}")

    try:
        square(art, 1024).save(TAURI_ICONS / "icon.icns")
        print("  icon.icns (macOS)")
    except Exception as e:  # noqa: BLE001 — Pillow's ICNS writer is platform-picky
        print(f"  icon.icns SKIPPED ({e}); the existing file is left in place")

    # Web assets. The in-app mark keeps the artwork's own aspect and no
    # padding at all, so a `size` prop in the UI means the height you see.
    mark_h = 512
    art.resize((round(art.width * mark_h / art.height), mark_h), Image.LANCZOS).save(
        WEB_PUBLIC / "app-icon.png", optimize=True
    )
    square(art, 180).save(WEB_PUBLIC / "favicon.png", optimize=True)
    square(art, 32).save(WEB_PUBLIC / "favicon-32.png", optimize=True)
    print(f"  app-icon.png + 2 favicons -> {WEB_PUBLIC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
