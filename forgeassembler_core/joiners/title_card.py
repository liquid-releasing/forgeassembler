# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""TitleCard: a bridge between two sections with a title on it.

A title card IS a fade-to-colour joiner that happens to carry words, so
it inherits the whole of `FadeToBlack` -- the hold, the per-side fades,
the bridge colour -- and adds the card. That inheritance is the point:
the timing semantics of a title are exactly the timing semantics of a
fade, and there is no reason for them to be able to drift apart.

In particular `duration_ms()` is still the HOLD alone. The fades are
applied inside the neighbouring scenes and add nothing to the output,
so a 1s/3s/1s title card lengthens the compilation by three seconds.

What the card LOOKS like is not decided here. This class owns the
timing and the backdrop; `forgeassembler_core.titles` owns the design,
and the params that describe it (`layout`, `theme`, `title`, `subtitle`,
`eyebrow`, `glyph`, the colour overrides) are read straight into a
`TitleSpec`. Keeping the two apart means the renderer can grow a layout
without this file knowing, and the UI asks the renderer what it can do
rather than this file.

Params (in addition to everything FadeToBlack takes)
----------------------------------------------------
- `title`       -- the words on the card. `text` is still accepted, and
                   means the same thing: that was the only field the
                   first version of this joiner had.
- `subtitle`,
  `eyebrow`     -- the smaller lines. Which of them a layout actually
                   draws is the layout's business.
- `layout`      -- one of `titles.TITLE_LAYOUTS`.
- `theme`       -- one of `titles.THEMES`. The theme also decides the
                   bridge colour, so the fades either side land on the
                   same colour as the card and there is no flash.
- `glyph`       -- a mark drawn above the title, where the layout has
                   a place for one.
- `font_family` -- font stem, resolved via `fonts.resolve_font_path`.
                   Falls back to Inter, then to whatever is installed,
                   so a project authored on another machine still
                   renders.
- `text_color`,
  `accent_color`-- override the theme. Empty means "use the theme",
                   which is what almost every card should do.
- `background`  -- a flat colour, or a real frame from the scene either
                   side of the card.
"""

from __future__ import annotations

from typing import Any

from ..titles import (
    GLYPH_LABELS,
    GLYPHS,
    LAYOUT_LABELS,
    THEME_LABELS,
    THEMES,
    TITLE_LAYOUTS,
    DEFAULT_LAYOUT,
    DEFAULT_THEME,
    GLYPH_NONE,
    TitleSpec,
)
from .fade_to_black import FadeToBlack

BACKGROUND_COLOR = "color"
BACKGROUND_PREV = "previous_last_frame"
BACKGROUND_NEXT = "next_first_frame"
BACKGROUNDS = (BACKGROUND_COLOR, BACKGROUND_PREV, BACKGROUND_NEXT)

# Text over a real frame needs the frame pushed back to stay readable.
#
# 0.25 rather than the 0.45 this started at, for two reasons found in a
# real forge: the filter was brightening rather than darkening, so no
# value here had ever been judged on what it actually did; and the
# layouts now lay a scrim behind their own words, which is where
# legibility is really won. A global dim this side of subtle is enough
# once the words defend themselves, and it leaves the user's picture
# looking like their picture.
DEFAULT_BACKGROUND_DIM = 0.25


class TitleCard(FadeToBlack):
    joiner_type = "title_card"
    display_name = "Title card"
    description = (
        "A title card between two sections. The previous scene fades "
        "out, the card holds for `duration_s` seconds while the title "
        "is on screen, then the next scene fades in. Audio is silent "
        "across the card."
    )

    # A title wants long enough to read. The bare fade defaults to 5s of
    # hold; a card carrying a few words reads comfortably in three.
    DEFAULT_DURATION_S: float = 3.0

    # ── The design ────────────────────────────────────────────────
    def title_spec(self) -> TitleSpec:
        """This card's design, as the renderer wants it.

        NOT called `spec`: `Joiner.spec()` is a classmethod describing
        the joiner TYPE to the catalog, and an instance method of the
        same name would shadow it -- `all_specs()` calls `cls.spec()`
        with no arguments and would have raised on this class alone.
        """
        return TitleSpec.from_params(self.params)

    def text(self) -> str:
        """The card's main words.

        Kept because `concat_video` and the validator both ask "does
        this card say anything", and because the first version of this
        joiner had nothing else.
        """
        return self.title_spec().title

    def font_family(self) -> str:
        return self.title_spec().font_family

    def color(self) -> str:
        """The bridge colour.

        Overridden to follow the THEME. The card is composited onto this
        colour and the fades either side land on it, so if it disagreed
        with the theme's background every title card would open and
        close with a flash of the wrong colour.

        An explicit `color` param still wins -- someone deliberately
        putting a dark card between two scenes on a light theme is
        making a choice, not a mistake.
        """
        if isinstance(self.params.get("color"), str) and self.params["color"].strip():
            return super().color()
        return self.title_spec().background_color()

    # ── The backdrop ──────────────────────────────────────────────
    def background(self) -> str:
        """What the card sits on: a flat colour, or a real frame.

        `previous_last_frame` / `next_first_frame` take a picture from
        the neighbouring scene instead of a solid bridge, so the card
        reads as part of the film rather than an interruption. The frame
        chosen is the last (or first) NON-BLANK one: scenes routinely
        start and end on black, and a black frame is just a slower way
        of getting the flat colour back.
        """
        raw = self.params.get("background", BACKGROUND_COLOR)
        raw = raw.strip() if isinstance(raw, str) else ""
        return raw if raw in BACKGROUNDS else BACKGROUND_COLOR

    def over_frame(self) -> bool:
        """Whether the card is composited over a picture.

        The renderer needs this: it decides how hard the scrim behind
        the words has to work, not what is behind them.
        """
        return self.background() != BACKGROUND_COLOR

    def background_dim(self) -> float:
        """How far to darken a frame background, 0..1.

        Text over a solid colour is legible by construction; text over a
        real frame is not, and a title that cannot be read is worse than
        no title. Defaults to a little under half.
        """
        raw = self.params.get("background_dim", DEFAULT_BACKGROUND_DIM)
        try:
            v = float(raw)
        except (TypeError, ValueError):
            return DEFAULT_BACKGROUND_DIM
        return max(0.0, min(1.0, v))

    # ── Validation ────────────────────────────────────────────────
    def validate(self) -> list[str]:
        errors = [
            # The parent's messages name FadeToBlack; say what the user
            # actually picked.
            e.replace("FadeToBlack", "Title card")
            for e in super().validate()
        ]
        if not self.title_spec().has_words():
            errors.append(
                "A title card needs something to say -- a title, a "
                "subtitle or an eyebrow. Without any of them it is just "
                "a fade to colour.",
            )
        if self._duration_s() <= 0:
            errors.append(
                "A title card needs duration_s > 0, or there is no "
                "frame for the title to appear on.",
            )
        return errors

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        schema = dict(super().params_schema())
        schema["duration_s"] = {
            **schema["duration_s"],
            "default": cls.DEFAULT_DURATION_S,
            "help": "How long the card holds on screen. The title is "
                    "visible for this whole time.",
        }
        schema["title"] = {
            "type": "str",
            "default": "",
            "label": "Title",
            "help": "The words on the card. Line breaks are kept, and "
                    "a title too long for the frame is shrunk and "
                    "wrapped rather than cropped.",
        }
        schema["subtitle"] = {
            "type": "str",
            "default": "",
            "label": "Subtitle",
            "help": "The smaller line under the title.",
        }
        schema["eyebrow"] = {
            "type": "str",
            "default": "",
            "label": "Eyebrow",
            "help": "A short label above the title, drawn in the accent "
                    "colour. Used by the chapter layout.",
        }
        schema["layout"] = {
            "type": "enum",
            "default": DEFAULT_LAYOUT,
            "options": list(TITLE_LAYOUTS),
            "labels": dict(LAYOUT_LABELS),
            "label": "Layout",
            "help": "How the card is arranged.",
        }
        schema["theme"] = {
            "type": "enum",
            "default": DEFAULT_THEME,
            "options": list(THEMES),
            "labels": dict(THEME_LABELS),
            "label": "Theme",
            "help": "The card's colours. Also sets the bridge colour, "
                    "so the fades either side match the card.",
        }
        schema["glyph"] = {
            "type": "enum",
            "default": GLYPH_NONE,
            "options": list(GLYPHS),
            "labels": dict(GLYPH_LABELS),
            "label": "Mark",
            "help": "A small mark above the title, where the layout "
                    "has a place for one.",
        }
        schema["font_family"] = {
            "type": "font",
            "default": "",
            "label": "Font",
            "help": "Font stem. Falls back to Inter, then to the first "
                    "installed font, when unset or missing here.",
        }
        schema["background"] = {
            "type": "enum",
            "default": BACKGROUND_COLOR,
            "options": list(BACKGROUNDS),
            "label": "Card background",
            "help": "A flat colour, or the last non-blank frame of the "
                    "previous scene / the first non-blank frame of the "
                    "next one.",
        }
        schema["background_dim"] = {
            "type": "float",
            "default": DEFAULT_BACKGROUND_DIM,
            "min": 0.0,
            "max": 1.0,
            "label": "Darken background",
            "help": "How far to push a frame background back so the "
                    "title stays readable. Ignored for a flat colour.",
        }
        schema["text_color"] = {
            "type": "color",
            "default": "",
            "label": "Text colour",
            "help": "Overrides the theme's text colour. Leave empty to "
                    "use the theme.",
        }
        schema["accent_color"] = {
            "type": "color",
            "default": "",
            "label": "Accent colour",
            "help": "Overrides the theme's accent, used for the mark, "
                    "the rule and the eyebrow. Leave empty to use the "
                    "theme.",
        }
        return schema
