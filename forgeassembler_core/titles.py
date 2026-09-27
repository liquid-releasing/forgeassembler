# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""Render a title card to a transparent PNG.

A title card used to be one line of ffmpeg `drawtext`, which is all a
single-line title needs and nothing a real one does: no subtitle, no
eyebrow, no rule, no mark, and -- the part that actually bit -- no idea
how wide the frame is. drawtext draws what it is given at the size it is
given, so a long title ran off both edges of the output and the only way
to find out was to forge the video and look at it.

So the card is composited instead of drawn: this module renders the
whole card to an RGBA PNG at the output resolution and `concat_video`
overlays that PNG on the bridge. Three things follow, and they are the
reason for the change:

  * The renderer can MEASURE. Every string is fitted to the frame it has
    to live in -- shrunk, then wrapped, then shrunk again -- so a title
    cannot leave the frame no matter how long it is.
  * The card is a picture, so it scales. One spec renders at 1080p or
    4K, and a future side-by-side target renders it twice rather than
    trying to keep drawtext's pixel sizes honest across resolutions.
  * The preview can be the real thing. The UI asks for the same PNG the
    forge will use, so what is on screen is not an approximation of the
    output -- it IS the output.

WHAT THIS MODULE DOES NOT PAINT
-------------------------------
The background. The card's base is the joiner's bridge: a flat colour
(the theme's, so the fades either side land on the same colour and there
is no flash) or a real frame from a neighbouring scene, dimmed. So every
render here is transparent, and `over_frame` says which of the two is
underneath -- it does not change the background, it changes the SCRIM.
Over a flat colour the lower-third gradient can go to solid black
because there is nothing to hide; over a real frame it stops at 70% so
the picture still reads through it. Text over a photograph needs help
that text over a colour does not, and a title that cannot be read is
worse than no title.

The layout geometry is a transcription of the SVG mock in
`ui/web/src/TitleEditor.jsx`, which is where these four layouts were
designed. It is in fractions of the frame (`k = H/1080` for type sizes)
so the same numbers hold at any resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

# ── Vocabulary ────────────────────────────────────────────────────────
# Plain tuples and dicts rather than enums: these cross the CLI boundary
# as JSON strings, and an unknown value has to degrade to the default
# rather than raise -- a project authored by a later build must still
# forge on this one.

LAYOUT_CENTERED = "centered"
LAYOUT_CHAPTER = "chapter"
LAYOUT_LOWER = "lower"
LAYOUT_FULLQUOTE = "fullquote"

TITLE_LAYOUTS: tuple[str, ...] = (
    LAYOUT_CENTERED, LAYOUT_CHAPTER, LAYOUT_LOWER, LAYOUT_FULLQUOTE,
)

LAYOUT_LABELS: dict[str, str] = {
    LAYOUT_CENTERED: "Centered hero",
    LAYOUT_CHAPTER: "Chapter plate",
    LAYOUT_LOWER: "Lower third",
    LAYOUT_FULLQUOTE: "Full quote",
}

LAYOUT_HELP: dict[str, str] = {
    LAYOUT_CENTERED: "Big title in the middle, mark above, rule below.",
    LAYOUT_CHAPTER: "Eyebrow and title against an accent bar, left-aligned.",
    LAYOUT_LOWER: "A title strip along the bottom, like a caption.",
    LAYOUT_FULLQUOTE: "The words fill the frame, attributed underneath.",
}

DEFAULT_LAYOUT = LAYOUT_CENTERED

# `bg` is what the BRIDGE gets painted -- this module never paints it,
# see the docstring. `fg` and `accent` are what this module draws with.
THEMES: dict[str, dict[str, str]] = {
    "dark": {"bg": "#0e1117", "fg": "#fafafa", "accent": "#ff4b4b"},
    "void": {"bg": "#000000", "fg": "#fafafa", "accent": "#ff8c42"},
    "brand": {"bg": "#1a0e1e", "fg": "#fafafa", "accent": "#ff4b4b"},
    "light": {"bg": "#fafafa", "fg": "#0e1117", "accent": "#ff4b4b"},
}
THEME_LABELS: dict[str, str] = {
    "dark": "Dark", "void": "Void", "brand": "Brand", "light": "Light",
}
DEFAULT_THEME = "dark"

GLYPH_NONE = "none"

# Marks. Coordinates live in a centred [-1, 1] box and are multiplied by
# the mark's pixel size at draw time, so one definition serves every
# resolution. Transcribed from the SVG path data in TitleEditor.jsx;
# "Q" is a quadratic curve and is flattened to a polyline when drawn.
GLYPH_PATHS: dict[str, tuple[tuple[tuple, ...], ...]] = {
    "anvil": (
        (("M", -0.60, 0.45), ("L", 0.60, 0.45), ("L", 0.45, 0.65),
         ("L", -0.45, 0.65)),
        (("M", -0.42, -0.12), ("L", 0.55, -0.12), ("L", 0.42, 0.18),
         ("L", -0.30, 0.18)),
        (("M", -0.50, -0.12), ("L", -0.30, 0.18), ("L", -0.55, 0.45),
         ("L", -0.70, 0.45), ("L", -0.70, -0.12)),
    ),
    "hammer": (
        (("M", -0.50, -0.45), ("L", 0.50, -0.45), ("L", 0.50, -0.05),
         ("L", -0.50, -0.05)),
        (("M", -0.08, -0.05), ("L", 0.08, -0.05), ("L", 0.05, 0.65),
         ("L", -0.05, 0.65)),
    ),
    "tongs": (
        (("M", -0.55, 0.55), ("Q", -0.65, 0.0, -0.20, -0.30),
         ("L", -0.10, -0.20), ("Q", -0.45, 0.10, -0.30, 0.55)),
        (("M", 0.55, 0.55), ("Q", 0.65, 0.0, 0.20, -0.30),
         ("L", 0.10, -0.20), ("Q", 0.45, 0.10, 0.30, 0.55)),
        (("M", -0.10, -0.20), ("L", 0.10, -0.20), ("L", 0.10, -0.55),
         ("L", -0.10, -0.55)),
    ),
    "oven": (
        (("M", -0.60, -0.50), ("L", 0.60, -0.50), ("L", 0.60, 0.55),
         ("L", -0.60, 0.55)),
        (("M", -0.35, -0.20), ("L", 0.35, -0.20), ("L", 0.35, 0.30),
         ("L", -0.35, 0.30)),
        (("M", -0.50, -0.55), ("L", 0.50, -0.55), ("L", 0.45, -0.65),
         ("L", -0.45, -0.65)),
    ),
    "spark": (
        (("M", 0.0, -0.65), ("L", 0.10, -0.10), ("L", 0.65, 0.0),
         ("L", 0.10, 0.10), ("L", 0.0, 0.65), ("L", -0.10, 0.10),
         ("L", -0.65, 0.0), ("L", -0.10, -0.10)),
    ),
    # A circle is an ellipse, not a polygon; drawn as a special case.
    "circle": (),
}

GLYPHS: tuple[str, ...] = (GLYPH_NONE, *GLYPH_PATHS)

GLYPH_LABELS: dict[str, str] = {
    GLYPH_NONE: "None", "anvil": "Anvil", "hammer": "Hammer",
    "tongs": "Tongs", "oven": "Oven", "spark": "Spark", "circle": "Dot",
}


# ── The spec ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TitleSpec:
    """Everything a title card says, and how it says it.

    Deliberately flat and JSON-shaped: this is what lives in a project's
    joiner params, so it has to survive a round trip through a file
    written by an older or a newer build.
    """

    layout: str = DEFAULT_LAYOUT
    theme: str = DEFAULT_THEME
    title: str = ""
    subtitle: str = ""
    eyebrow: str = ""
    glyph: str = GLYPH_NONE
    font_family: str = ""
    # Empty means "use the theme". An override is for the project whose
    # look the four themes do not cover, not for the common case.
    text_color: str = ""
    accent_color: str = ""

    @staticmethod
    def from_params(params: dict[str, Any] | None) -> "TitleSpec":
        """Read a spec out of joiner params, forgiving everything.

        `text` is accepted as `title`: that was the only field the first
        title card had, and a project saved with it has to keep
        rendering the same words.
        """
        p = params or {}
        title = _as_text(p.get("title")) or _as_text(p.get("text"))
        return TitleSpec(
            layout=_one_of(p.get("layout"), TITLE_LAYOUTS, DEFAULT_LAYOUT),
            theme=_one_of(p.get("theme"), tuple(THEMES), DEFAULT_THEME),
            title=title,
            subtitle=_as_text(p.get("subtitle")),
            eyebrow=_as_text(p.get("eyebrow")),
            glyph=_one_of(p.get("glyph"), GLYPHS, GLYPH_NONE),
            font_family=_as_text(p.get("font_family")),
            text_color=_hex_or_blank(p.get("text_color")),
            accent_color=_hex_or_blank(p.get("accent_color")),
        )

    def theme_colors(self) -> dict[str, str]:
        return THEMES.get(self.theme, THEMES[DEFAULT_THEME])

    def background_color(self) -> str:
        """What the bridge is painted when the card is not on a frame.

        The fades either side land on this colour too, so the card and
        the fade into it cannot disagree and flash.
        """
        return self.theme_colors()["bg"]

    def foreground_color(self) -> str:
        return self.text_color or self.theme_colors()["fg"]

    def accent(self) -> str:
        return self.accent_color or self.theme_colors()["accent"]

    def has_words(self) -> bool:
        """Whether there is anything to render.

        A card with no words at all is a fade with extra steps, and the
        joiner's validator says so rather than spending the user's
        seconds on an empty frame. An eyebrow or a subtitle on its own
        counts: "INTERMISSION" is a legitimate card.
        """
        return bool(self.title or self.subtitle or self.eyebrow)


def _as_text(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    # Normalise what a Windows text box hands us. A stray CR used to
    # render in drawtext as a tall thin box; here it would become a
    # blank line, which is just as wrong.
    return raw.replace("\r\n", "\n").replace("\r", "\n").strip()


def _one_of(raw: Any, allowed: Sequence[str], default: str) -> str:
    if isinstance(raw, str) and raw.strip() in allowed:
        return raw.strip()
    return default


def _hex_or_blank(raw: Any) -> str:
    """A '#rrggbb' colour, or '' meaning 'not set'."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    v = raw.strip()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) != 7 or not all(c in "0123456789abcdefABCDEF" for c in v[1:]):
        return ""
    return v.lower()


def _rgba(hex_color: str, alpha: float = 1.0) -> tuple[int, int, int, int]:
    """'#rrggbb' plus a multiplier -> an RGBA tuple."""
    v = (hex_color or "#ffffff").lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) not in (6, 8):
        v = "ffffff"
    a = int(v[6:8], 16) if len(v) == 8 else 255
    return (
        int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16),
        int(round(max(0.0, min(1.0, alpha)) * a)),
    )


# ── Fonts ─────────────────────────────────────────────────────────────
# The mock asks for weights 500, 700 and 800, and a filesystem font scan
# gives us faces, not weights. So we guess at the face from the family
# and the weight, and if the family has no bold face we thicken the
# regular one instead. Faux bold is not as good as a real bold, and it
# is a great deal better than a card that ignores the design.

_WEIGHT_SUFFIXES: dict[int, tuple[str, ...]] = {
    800: ("extrabold", "black", "heavy", "bold", "bd", "semibold", "sb"),
    700: ("bold", "bd", "semibold", "sb", "extrabold"),
    500: ("medium", "md", "regular", ""),
    400: ("regular", "", "medium"),
}

# Faces that already carry weight, so no thickening is needed.
_BOLDISH = frozenset({
    "extrabold", "black", "heavy", "bold", "bd", "semibold", "sb",
})

# Tried in order when the project names no font. Inter first because
# that is what the layouts were designed in.
_FALLBACK_FAMILIES: tuple[str, ...] = (
    "Inter", "segoeui", "Segoe UI", "arial", "Helvetica", "DejaVuSans",
)

_JOINERS: tuple[str, ...] = ("-", "", " ", "_")


@lru_cache(maxsize=1)
def _font_index() -> dict[str, str]:
    """Lower-cased font stem -> path. First match wins, as fonts.py does."""
    from .fonts import list_fonts  # noqa: PLC0415  (kept off import time)

    idx: dict[str, str] = {}
    for stem, path in list_fonts():
        idx.setdefault(stem.lower(), path)
    return idx


def _resolve_face(family: str, weight: int) -> tuple[str | None, bool]:
    """Best face for (family, weight) -> (path, needs_faux_bold)."""
    idx = _font_index()
    families = (family,) if family else _FALLBACK_FAMILIES
    for fam in families:
        base = fam.strip().lower()
        if not base:
            continue
        for suffix in _WEIGHT_SUFFIXES.get(weight, ("regular", "")):
            for join in _JOINERS:
                key = f"{base}{join}{suffix}" if suffix else base
                if key in idx:
                    return idx[key], weight >= 700 and suffix not in _BOLDISH
                if not suffix:
                    break  # the bare family needs no joiner loop
        if base in idx:
            return idx[base], weight >= 700
    # Nothing matched at all -- take whatever this machine has, so the
    # card still renders with the right shape and the wrong typeface.
    if idx:
        return next(iter(idx.values())), weight >= 700
    return None, False


@lru_cache(maxsize=256)
def _truetype(path: str | None, size: int):
    from PIL import ImageFont  # noqa: PLC0415

    size = max(1, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow too old for a sized default
        return ImageFont.load_default()


def _face(family: str, weight: int, size: float):
    path, faux = _resolve_face(family, weight)
    return _truetype(path, int(round(size))), faux


def _advance(font, text: str, tracking: float) -> float:
    """Width of `text`, accounting for how it will actually be drawn.

    Tracked text is drawn one character at a time (PIL has no letter
    spacing), which loses kerning, so it must be measured the same way
    or the centring is off by the kerning of the whole string.
    """
    if not text:
        return 0.0
    if not tracking:
        return float(font.getlength(text))
    return sum(font.getlength(c) for c in text) + tracking * (len(text) - 1)


def _draw_line(
    draw, x: float, y: float, text: str, font, fill, align: str,
    tracking: float, faux_bold: bool,
) -> None:
    """One line of text, `y` being its BASELINE (as in the SVG mock)."""
    if not text:
        return
    kwargs: dict[str, Any] = {"fill": fill}
    if faux_bold:
        # A stroke in the fill colour thickens the glyph. 2.2% of the
        # size is about the difference between a regular and a bold.
        stroke = max(1, int(round(getattr(font, "size", 16) * 0.022)))
        kwargs["stroke_width"] = stroke
        kwargs["stroke_fill"] = fill
    if not tracking:
        anchor = {"center": "ms", "right": "rs"}.get(align, "ls")
        draw.text((x, y), text, font=font, anchor=anchor, **kwargs)
        return
    total = _advance(font, text, tracking)
    cx = x - total / 2 if align == "center" else (
        x - total if align == "right" else x
    )
    for ch in text:
        draw.text((cx, y), ch, font=font, anchor="ls", **kwargs)
        cx += font.getlength(ch) + tracking


def _wrap(text: str, font, tracking: float, max_width: float) -> list[str]:
    """Greedy word wrap. Explicit newlines are honoured as hard breaks."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if cur and _advance(font, trial, tracking) > max_width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
            # A single word wider than the frame (a URL, a German noun)
            # has to break mid-word or it runs off the edge.
            while _advance(font, cur, tracking) > max_width and len(cur) > 1:
                cut = len(cur) - 1
                while cut > 1 and _advance(font, cur[:cut], tracking) > max_width:
                    cut -= 1
                lines.append(cur[:cut])
                cur = cur[cut:]
        if cur:
            lines.append(cur)
    return lines


@dataclass(frozen=True)
class _Fitted:
    """A block of text measured and ready to draw."""

    lines: list[str]
    font: Any
    faux_bold: bool
    size: float
    tracking: float

    @property
    def line_height(self) -> float:
        return self.size * 1.15


def _fit(
    text: str, family: str, weight: int, size: float, max_width: float,
    max_lines: int = 1, tracking_em: float = 0.0, min_ratio: float = 0.5,
) -> _Fitted | None:
    """Fit `text` into `max_width` by `max_lines`, shrinking as needed.

    This is the whole point of rendering the card ourselves. Shrink
    first, because a slightly smaller title that reads as one line is
    better than a wrapped one; wrap only once shrinking has gone as far
    as `min_ratio` allows. If even that will not fit, the last line is
    elided -- a card that says "The Long Afternoon of..." is honest,
    whereas one whose words leave the frame looks broken.
    """
    text = (text or "").strip()
    if not text:
        return None
    size = max(4.0, float(size))
    attempt: _Fitted | None = None
    trial = size
    while True:
        font, faux = _face(family, weight, trial)
        tracking = tracking_em * trial
        lines = _wrap(text, font, tracking, max_width)
        attempt = _Fitted(lines, font, faux, trial, tracking)
        if len(lines) <= max_lines:
            return attempt
        if trial <= size * min_ratio:
            break
        trial = max(size * min_ratio, trial * 0.92)

    lines = attempt.lines[:max_lines]
    if lines:
        last = lines[-1].rstrip()
        ellipsis = "…"
        while (
            len(last) > 1
            and _advance(attempt.font, last + ellipsis, attempt.tracking)
            > max_width
        ):
            last = last[:-1].rstrip()
        lines[-1] = last + ellipsis
    return _Fitted(lines, attempt.font, attempt.faux_bold,
                   attempt.size, attempt.tracking)


def _draw_block(
    draw, fitted: _Fitted | None, x: float, last_baseline: float,
    fill, align: str,
) -> float:
    """Draw a fitted block whose LAST baseline sits at `last_baseline`.

    Returns that last baseline, so a caller can stack the next element
    under whatever the block actually took.
    """
    if fitted is None or not fitted.lines:
        return last_baseline
    lh = fitted.line_height
    first = last_baseline - (len(fitted.lines) - 1) * lh
    for i, line in enumerate(fitted.lines):
        _draw_line(draw, x, first + i * lh, line, fitted.font, fill,
                   align, fitted.tracking, fitted.faux_bold)
    return last_baseline


# ── Marks ─────────────────────────────────────────────────────────────

def _flatten(subpath: Sequence[tuple], steps: int = 18) -> list[tuple[float, float]]:
    """Turn one subpath into a polygon, sampling any quadratic curves."""
    pts: list[tuple[float, float]] = []
    cur = (0.0, 0.0)
    for cmd in subpath:
        kind = cmd[0]
        if kind in ("M", "L"):
            cur = (float(cmd[1]), float(cmd[2]))
            pts.append(cur)
        elif kind == "Q":
            cx, cy, x, y = (float(v) for v in cmd[1:5])
            x0, y0 = cur
            for i in range(1, steps + 1):
                t = i / steps
                mt = 1.0 - t
                pts.append((
                    mt * mt * x0 + 2 * mt * t * cx + t * t * x,
                    mt * mt * y0 + 2 * mt * t * cy + t * t * y,
                ))
            cur = (x, y)
    return pts


def _draw_glyph(
    draw, glyph: str, cx: float, cy: float, size: float, fill,
) -> None:
    """A mark centred on (cx, cy), `size` being half its coordinate box."""
    if glyph == GLYPH_NONE or glyph not in GLYPH_PATHS:
        return
    if glyph == "circle":
        r = size * 0.30
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        return
    for subpath in GLYPH_PATHS[glyph]:
        pts = [(cx + x * size, cy + y * size) for x, y in _flatten(subpath)]
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill)


def _scrim(img, y0: float, y1: float, max_alpha: float) -> None:
    """A black gradient from transparent at `y0` to `max_alpha` at `y1`."""
    from PIL import Image  # noqa: PLC0415

    top = max(0, int(round(y0)))
    height = int(round(y1)) - top
    if height <= 0 or max_alpha <= 0:
        return
    ramp = Image.new("L", (1, height))
    peak = max(1, height - 1)
    ramp.putdata([
        int(round(255 * max_alpha * i / peak)) for i in range(height)
    ])
    band = Image.new("RGBA", (img.width, height), (0, 0, 0, 255))
    band.putalpha(ramp.resize((img.width, height)))
    img.alpha_composite(band, (0, top))


# ── The layouts ───────────────────────────────────────────────────────
# Every number here is a fraction of the frame, and `k` scales type with
# the frame height, so one spec renders the same card at any resolution.

def _render_centered(draw, spec, W, H, k, over_frame) -> None:
    fam = spec.font_family
    fg = spec.foreground_color()
    accent = spec.accent()

    glyph_bottom = H * 0.30
    if spec.glyph != GLYPH_NONE:
        glyph_size = k * 110
        _draw_glyph(draw, spec.glyph, W * 0.5, H * 0.30, glyph_size,
                    _rgba(accent))
        glyph_bottom = H * 0.30 + glyph_size * 0.65

    # Three lines, not two: there is room here, and a title that fits is
    # better than one cut off. The ellipsis is the last resort, not the
    # second one.
    title = _fit(spec.title, fam, 800, k * 130, W * 0.86,
                 max_lines=3, tracking_em=-0.025)

    # The elements STACK from here rather than sitting on fixed marks.
    # The mock's positions are where a one-line title lands, and they
    # are the minimum: a title that took three lines pushes the subtitle
    # and the rule down instead of being drawn through them.
    baseline = H * 0.55
    if title:
        lines = len(title.lines)
        lh = title.line_height
        # Grow around the nominal baseline, then keep clear of the mark.
        last = baseline + (lines - 1) * lh / 2
        first = last - (lines - 1) * lh
        if first < glyph_bottom + title.size:
            last = glyph_bottom + title.size + (lines - 1) * lh
        _draw_block(draw, title, W * 0.5, last, _rgba(fg), "center")
        baseline = last

    # The subtitle hangs off what the title actually came out at, not
    # off the nominal size -- a title that shrank should not leave a gap
    # underneath it where the big type would have been.
    bottom = baseline
    sub = _fit(spec.subtitle, fam, 500, k * 36, W * 0.80,
               max_lines=2, tracking_em=0.04)
    if sub:
        sub_last = (
            baseline + (title.size if title else k * 130) * 0.85
            + (len(sub.lines) - 1) * sub.line_height
        )
        _draw_block(draw, sub, W * 0.5, sub_last, _rgba(fg, 0.70), "center")
        bottom = sub_last

    rule_y = max(H * 0.78, bottom + k * 60)
    rule_h = max(1.0, k * 4)
    if rule_y + rule_h < H:
        draw.rectangle(
            [W * 0.42, rule_y, W * 0.58, rule_y + rule_h], fill=_rgba(accent),
        )


def _render_chapter(draw, spec, W, H, k, over_frame) -> None:
    fam = spec.font_family
    fg = spec.foreground_color()
    accent = spec.accent()

    x = W * 0.13
    eyebrow = _fit((spec.eyebrow or "CHAPTER").upper(), fam, 700, k * 28,
                   W * 0.80, max_lines=1, tracking_em=0.18)
    _draw_block(draw, eyebrow, x, H * 0.42, _rgba(accent), "left")

    title = _fit(spec.title, fam, 700, k * 110, W * 0.80,
                 max_lines=2, tracking_em=-0.02)
    # Unlike the centred layout, a second line grows DOWNWARD from the
    # first baseline: upward would run into the eyebrow.
    title_baseline = H * 0.58
    if title:
        lines = len(title.lines)
        _draw_block(draw, title, x,
                    title_baseline + (lines - 1) * title.line_height,
                    _rgba(fg), "left")
        title_bottom = title_baseline + (lines - 1) * title.line_height
    else:
        title_bottom = title_baseline

    bottom = title_bottom
    sub = _fit(spec.subtitle, fam, 500, k * 32, W * 0.80,
               max_lines=2, tracking_em=0.0)
    if sub:
        # Below the fixed mark OR below where the title really ended,
        # whichever is lower. A two-line title used to be drawn straight
        # through the subtitle.
        # Clear the title's DESCENDERS, not just its baseline -- at
        # k*110 the gap has to scale with the title, not the subtitle.
        gap = max(sub.size * 1.3, (title.size if title else k * 110) * 0.55)
        sub_y = max(H * 0.68, title_bottom + gap)
        _draw_block(draw, sub, x, sub_y, _rgba(fg, 0.70), "left")
        bottom = sub_y

    # The bar is drawn LAST because it has to span what it marks: the
    # mock's fixed 0.35H-0.65H bar stopped halfway up a two-line title,
    # which reads as a mistake rather than as a rule.
    bar_top = min(H * 0.35, H * 0.42 - k * 28 * 1.4)
    bar_bottom = max(H * 0.65, bottom + k * 14)
    draw.rectangle(
        [W * 0.10, bar_top, W * 0.10 + k * 6, bar_bottom], fill=_rgba(accent),
    )


def _render_lower(img, draw, spec, W, H, k, over_frame) -> None:
    fam = spec.font_family
    accent = spec.accent()
    # Over a real frame the scrim stops short so the picture still
    # reads through it; over a flat colour there is nothing to hide.
    _scrim(img, H * 0.55, H, 0.70 if over_frame else 1.0)

    draw.rectangle(
        [W * 0.08, H * 0.75, W * 0.08 + k * 6, H * 0.89], fill=_rgba(accent),
    )

    # A lower third is white-on-dark by construction: it sits on its own
    # gradient, so the theme's foreground would be wrong on a light
    # theme -- #0e1117 text on a black scrim is invisible.
    fg = "#fafafa"
    x = W * 0.10
    title = _fit(spec.title, fam, 700, k * 76, W * 0.84,
                 max_lines=2, tracking_em=-0.01)
    _draw_block(draw, title, x, H * 0.85, _rgba(fg), "left")

    sub = _fit(spec.subtitle, fam, 500, k * 28, W * 0.84,
               max_lines=1, tracking_em=0.02)
    _draw_block(draw, sub, x, H * 0.91, _rgba(fg, 0.70), "left")


def _render_fullquote(img, draw, spec, W, H, k, over_frame) -> None:
    fam = spec.font_family
    if over_frame:
        # The whole frame pushed back, because the words are everywhere.
        img.alpha_composite(
            _flat(img.width, img.height, (0, 0, 0, int(round(255 * 0.4)))),
        )
    fg = "#fafafa" if over_frame else spec.foreground_color()

    title = _fit(spec.title, fam, 800, k * 96, W * 0.85,
                 max_lines=5, tracking_em=-0.025)
    if title:
        lh = title.line_height
        # Centred on the middle of the frame, however many lines it took.
        last = H * 0.5 + ((len(title.lines) - 1) * lh) / 2
        _draw_block(draw, title, W * 0.5, last, _rgba(fg), "center")

    # Only attribute what the user actually wrote. The mock filled this
    # in with "anonymous", which is a word nobody asked for appearing in
    # their output.
    if spec.subtitle:
        attribution = "— " + spec.subtitle.lower()
        sub = _fit(attribution, fam, 500, k * 32, W * 0.80,
                   max_lines=1, tracking_em=0.04)
        _draw_block(draw, sub, W * 0.5, H * 0.92, _rgba(fg, 0.60), "center")


def _flat(w: int, h: int, rgba: tuple[int, int, int, int]):
    from PIL import Image  # noqa: PLC0415

    return Image.new("RGBA", (w, h), rgba)


_RENDERERS = {
    LAYOUT_CENTERED: lambda img, draw, s, W, H, k, of: _render_centered(
        draw, s, W, H, k, of),
    LAYOUT_CHAPTER: lambda img, draw, s, W, H, k, of: _render_chapter(
        draw, s, W, H, k, of),
    LAYOUT_LOWER: _render_lower,
    LAYOUT_FULLQUOTE: _render_fullquote,
}


# ── Public entry point ────────────────────────────────────────────────

def render_title_png(
    spec: TitleSpec, width: int, height: int, out_path,
    over_frame: bool = False,
) -> str:
    """Render `spec` to a transparent PNG at `width` x `height`.

    Returns the path written. The background is NOT painted -- see the
    module docstring; `over_frame` selects the scrim, not the backdrop.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    W = max(2, int(width))
    H = max(2, int(height))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    k = H / 1080.0

    # No words, no card. Without this the furniture -- the rule, the
    # accent bar, the scrim -- would draw on its own, which is how you
    # get a three-second hold on a single red line and no explanation.
    # `_build_title_cards` skips these too; this keeps the preview
    # honest about what the forge will do.
    if spec.has_words():
        renderer = _RENDERERS.get(spec.layout, _RENDERERS[DEFAULT_LAYOUT])
        renderer(img, draw, spec, W, H, k, over_frame)

    out = str(out_path)
    img.save(out, format="PNG")
    return out


def title_catalog() -> dict[str, Any]:
    """The layouts, themes and marks, for the UI to draw its pickers.

    Served from here rather than hardcoded in the UI for the reason
    `list-joiners` exists: the engine decides what it can render, and a
    picker offering a layout the engine has never heard of is a bug
    waiting for a user to find it.
    """
    return {
        "layouts": [
            {
                "id": layout,
                "label": LAYOUT_LABELS[layout],
                "help": LAYOUT_HELP[layout],
            }
            for layout in TITLE_LAYOUTS
        ],
        "themes": [
            {
                "id": name,
                "label": THEME_LABELS.get(name, name.title()),
                **colors,
            }
            for name, colors in THEMES.items()
        ],
        "glyphs": [
            {"id": glyph, "label": GLYPH_LABELS.get(glyph, glyph)}
            for glyph in GLYPHS
        ],
        "defaults": {
            "layout": DEFAULT_LAYOUT,
            "theme": DEFAULT_THEME,
            "glyph": GLYPH_NONE,
        },
    }
