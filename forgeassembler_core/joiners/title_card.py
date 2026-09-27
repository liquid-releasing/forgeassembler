# Copyright (c) 2026 Liquid Releasing. Licensed under the MIT License.

"""TitleCard: a solid-colour bridge with text drawn on it.

A title card IS a fade-to-colour joiner that happens to carry words, so
it inherits the whole of `FadeToBlack` — the hold, the per-side fades,
the bridge colour — and adds the text. That inheritance is the point:
the timing semantics of a title are exactly the timing semantics of a
fade, and there is no reason for them to be able to drift apart.

In particular `duration_ms()` is still the HOLD alone. The fades are
applied inside the neighbouring scenes and add nothing to the output,
so a 1s/3s/1s title card lengthens the compilation by three seconds.

Params (in addition to everything FadeToBlack takes)
----------------------------------------------------
- `text`         — the words on the card. Required; a title card with
                   nothing to say is a plain fade, and the validator
                   says so rather than silently rendering an empty
                   frame the user paid three seconds for.
- `font_family`  — font stem, resolved via `fonts.resolve_font_path`.
                   Falls back to the first installed font, matching
                   what section text overlays already do, so a project
                   authored on another machine still renders.
- `font_size`    — points. Default 96, which is legible at 1080p and
                   still reasonable when the output is 4K.
- `text_color`   — hex. Default white, since the default bridge is
                   black.
"""

from __future__ import annotations

from typing import Any

from .fade_to_black import FadeToBlack

DEFAULT_TEXT_COLOR = "#ffffff"
DEFAULT_FONT_SIZE = 96


class TitleCard(FadeToBlack):
    joiner_type = "title_card"
    display_name = "Title card"
    description = (
        "A solid-colour bridge with a title drawn on it. The previous "
        "scene fades out, the card holds for `duration_s` seconds "
        "while the text is on screen, then the next scene fades in. "
        "Audio is silent across the card."
    )

    # A title wants long enough to read. The bare fade defaults to 5s
    # of hold; a card carrying a few words reads comfortably in three.
    DEFAULT_DURATION_S: float = 3.0

    def text(self) -> str:
        """The words on the card, or '' when there are none."""
        raw = self.params.get("text", "")
        return raw.strip() if isinstance(raw, str) else ""

    def font_family(self) -> str:
        raw = self.params.get("font_family", "")
        return raw.strip() if isinstance(raw, str) else ""

    def font_size(self) -> int:
        try:
            v = int(float(self.params.get("font_size", DEFAULT_FONT_SIZE)))
        except (TypeError, ValueError):
            return DEFAULT_FONT_SIZE
        # A zero or negative size makes ffmpeg refuse the whole filter
        # graph rather than clamp — see the drawtext notes in filters.py.
        return v if v > 0 else DEFAULT_FONT_SIZE

    def text_color(self) -> str:
        raw = self.params.get("text_color", DEFAULT_TEXT_COLOR)
        if not isinstance(raw, str) or not raw:
            return DEFAULT_TEXT_COLOR
        raw = raw.strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        if len(raw) != 7 or not all(c in "0123456789abcdefABCDEF" for c in raw[1:]):
            return DEFAULT_TEXT_COLOR
        return raw.lower()

    def validate(self) -> list[str]:
        errors = [
            # The parent's messages name FadeToBlack; say what the user
            # actually picked.
            e.replace("FadeToBlack", "Title card")
            for e in super().validate()
        ]
        if not self.text():
            errors.append(
                "A title card needs `text` — without it, it is just a "
                "fade to colour.",
            )
        if self._duration_s() <= 0:
            errors.append(
                "A title card needs duration_s > 0, or there is no "
                "frame for the text to appear on.",
            )
        return errors

    @classmethod
    def params_schema(cls) -> dict[str, Any]:
        schema = dict(super().params_schema())
        schema["duration_s"] = {
            **schema["duration_s"],
            "default": cls.DEFAULT_DURATION_S,
            "help": "How long the card holds on screen. The text is "
                    "visible for this whole time.",
        }
        schema["text"] = {
            "type": "str",
            "default": "",
            "label": "Title",
            "help": "The words on the card. Line breaks are kept.",
        }
        schema["font_family"] = {
            "type": "font",
            "default": "",
            "label": "Font",
            "help": "Font stem. Falls back to the first installed font "
                    "when unset or missing on this machine.",
        }
        schema["font_size"] = {
            "type": "int",
            "default": DEFAULT_FONT_SIZE,
            "min": 8,
            "max": 400,
            "label": "Font size",
            "help": "Points, against the output resolution.",
        }
        schema["text_color"] = {
            "type": "color",
            "default": DEFAULT_TEXT_COLOR,
            "label": "Text colour",
            "help": "Hex colour of the words (e.g. '#ffffff').",
        }
        return schema
